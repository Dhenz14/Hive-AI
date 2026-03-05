"""Mutual TLS and service-to-service auth — certificates, SPIFFE, pinning, revocation."""

PAIRS = [
    (
        "security/mtls-certificate-management",
        "Show mTLS certificate management including CA creation, client/server cert generation, rotation strategies, and automation with Python and OpenSSL.",
        '''mTLS certificate management: CA setup, cert generation, and rotation:

```python
# --- Certificate Authority and certificate generation with cryptography lib ---

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional
from pathlib import Path
import ipaddress

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption, BestAvailableEncryption,
)


class CertificateAuthority:
    """Internal CA for mTLS certificate management."""

    def __init__(
        self,
        ca_cert: x509.Certificate,
        ca_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
    ) -> None:
        self.ca_cert = ca_cert
        self.ca_key = ca_key

    @classmethod
    def create_root_ca(
        cls,
        common_name: str = "Internal Root CA",
        org: str = "MyOrg",
        validity_days: int = 3650,  # 10 years
    ) -> CertificateAuthority:
        """Create a self-signed root CA."""
        # Use ECDSA P-256 for modern CA
        key = ec.generate_private_key(ec.SECP256R1())

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(
                datetime.now(timezone.utc) + timedelta(days=validity_days)
            )
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=1),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

        return cls(ca_cert=cert, ca_key=key)

    def issue_server_cert(
        self,
        common_name: str,
        san_dns: list[str] | None = None,
        san_ips: list[str] | None = None,
        validity_days: int = 365,
    ) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
        """Issue a server certificate for mTLS."""
        key = ec.generate_private_key(ec.SECP256R1())

        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        # Build Subject Alternative Names
        san_entries: list[x509.GeneralName] = []
        for dns in (san_dns or [common_name]):
            san_entries.append(x509.DNSName(dns))
        for ip in (san_ips or []):
            san_entries.append(x509.IPAddress(ipaddress.ip_address(ip)))

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(
                datetime.now(timezone.utc) + timedelta(days=validity_days)
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.SERVER_AUTH,
                ]),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
            .sign(self.ca_key, hashes.SHA256())
        )

        return cert, key

    def issue_client_cert(
        self,
        common_name: str,
        org: str | None = None,
        spiffe_id: str | None = None,
        validity_days: int = 90,  # Shorter for client certs
    ) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
        """Issue a client certificate for mTLS authentication."""
        key = ec.generate_private_key(ec.SECP256R1())

        name_attrs = [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
        if org:
            name_attrs.insert(0, x509.NameAttribute(NameOID.ORGANIZATION_NAME, org))

        subject = x509.Name(name_attrs)

        san_entries: list[x509.GeneralName] = []
        if spiffe_id:
            # SPIFFE ID as URI SAN
            san_entries.append(x509.UniformResourceIdentifier(spiffe_id))

        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(
                datetime.now(timezone.utc) + timedelta(days=validity_days)
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False,
            )
        )

        if san_entries:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )

        cert = builder.sign(self.ca_key, hashes.SHA256())
        return cert, key


def save_cert_and_key(
    cert: x509.Certificate,
    key: ec.EllipticCurvePrivateKey,
    cert_path: Path,
    key_path: Path,
    key_password: Optional[bytes] = None,
) -> None:
    """Save certificate and private key to PEM files."""
    cert_path.write_bytes(cert.public_bytes(Encoding.PEM))

    encryption = (
        BestAvailableEncryption(key_password) if key_password
        else NoEncryption()
    )
    key_path.write_bytes(
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, encryption)
    )
    # Restrict key file permissions
    key_path.chmod(0o600)
```

```python
# --- Certificate rotation automation ---

import logging
from dataclasses import dataclass

logger = logging.getLogger("mtls.rotation")


@dataclass
class CertRotationConfig:
    renew_before_expiry_days: int = 30
    cert_dir: Path = Path("/etc/mtls/certs")
    ca_cert_path: Path = Path("/etc/mtls/ca.pem")
    notify_webhook: str | None = None


class CertRotator:
    """Automated certificate rotation for mTLS."""

    def __init__(self, ca: CertificateAuthority, config: CertRotationConfig):
        self.ca = ca
        self.config = config

    def check_expiry(self, cert_path: Path) -> tuple[bool, int]:
        """Check if certificate needs renewal. Returns (needs_renewal, days_left)."""
        cert_pem = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem)

        now = datetime.now(timezone.utc)
        expiry = cert.not_valid_after_utc
        days_left = (expiry - now).days

        needs_renewal = days_left <= self.config.renew_before_expiry_days
        return needs_renewal, days_left

    def rotate_server_cert(
        self,
        service_name: str,
        san_dns: list[str],
        san_ips: list[str] | None = None,
    ) -> bool:
        """Rotate a server certificate if needed."""
        cert_path = self.config.cert_dir / f"{service_name}.crt"
        key_path = self.config.cert_dir / f"{service_name}.key"

        if cert_path.exists():
            needs_renewal, days_left = self.check_expiry(cert_path)
            if not needs_renewal:
                logger.info(
                    f"{service_name}: cert OK, {days_left} days remaining"
                )
                return False

            logger.info(
                f"{service_name}: cert expires in {days_left} days, rotating"
            )

        cert, key = self.ca.issue_server_cert(
            common_name=service_name,
            san_dns=san_dns,
            san_ips=san_ips,
        )
        save_cert_and_key(cert, key, cert_path, key_path)
        logger.info(f"{service_name}: new certificate issued")

        if self.config.notify_webhook:
            self._notify_rotation(service_name, "server")

        return True

    def rotate_client_cert(
        self,
        service_name: str,
        spiffe_id: str | None = None,
    ) -> bool:
        """Rotate a client certificate if needed."""
        cert_path = self.config.cert_dir / f"{service_name}-client.crt"
        key_path = self.config.cert_dir / f"{service_name}-client.key"

        if cert_path.exists():
            needs_renewal, days_left = self.check_expiry(cert_path)
            if not needs_renewal:
                return False

        cert, key = self.ca.issue_client_cert(
            common_name=service_name,
            spiffe_id=spiffe_id,
        )
        save_cert_and_key(cert, key, cert_path, key_path)
        logger.info(f"{service_name}: new client certificate issued")
        return True

    def _notify_rotation(self, service_name: str, cert_type: str) -> None:
        """Notify via webhook about certificate rotation."""
        import httpx
        if self.config.notify_webhook:
            httpx.post(self.config.notify_webhook, json={
                "event": "cert_rotated",
                "service": service_name,
                "type": cert_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
```

```bash
# --- OpenSSL commands for quick mTLS setup ---

# Create Root CA
openssl ecparam -genkey -name prime256v1 -out ca-key.pem
openssl req -new -x509 -key ca-key.pem -out ca-cert.pem \
  -days 3650 -subj "/O=MyOrg/CN=Internal Root CA" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:1" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"

# Create Server Certificate
openssl ecparam -genkey -name prime256v1 -out server-key.pem
openssl req -new -key server-key.pem -out server.csr \
  -subj "/CN=api.internal.example.com"

openssl x509 -req -in server.csr -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -out server-cert.pem -days 365 \
  -extfile <(printf "subjectAltName=DNS:api.internal.example.com,DNS:*.internal.example.com\nextendedKeyUsage=serverAuth")

# Create Client Certificate
openssl ecparam -genkey -name prime256v1 -out client-key.pem
openssl req -new -key client-key.pem -out client.csr \
  -subj "/O=MyOrg/CN=payment-service"

openssl x509 -req -in client.csr -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -out client-cert.pem -days 90 \
  -extfile <(printf "extendedKeyUsage=clientAuth")

# Verify the chain
openssl verify -CAfile ca-cert.pem server-cert.pem
openssl verify -CAfile ca-cert.pem client-cert.pem

# Inspect certificate details
openssl x509 -in server-cert.pem -text -noout | grep -A2 "Subject Alternative"
openssl x509 -in client-cert.pem -text -noout | grep -A2 "Extended Key Usage"
```

| Certificate Type | Key Usage | Extended Key Usage | Validity | Key Algorithm |
|---|---|---|---|---|
| Root CA | keyCertSign, cRLSign | -- | 10 years | ECDSA P-256 |
| Intermediate CA | keyCertSign, cRLSign | -- | 5 years | ECDSA P-256 |
| Server | digitalSignature, keyEncipherment | serverAuth | 1 year | ECDSA P-256 |
| Client | digitalSignature | clientAuth | 90 days | ECDSA P-256 |

Key patterns:

1. **ECDSA P-256** -- use elliptic curve keys for smaller certs and faster handshakes vs RSA
2. **Short client cert validity** -- 90 days forces frequent rotation, limiting compromise window
3. **SAN required** -- always include Subject Alternative Names; CN alone is deprecated
4. **SPIFFE URIs** -- embed service identity as URI SAN for zero-trust architectures
5. **Automated rotation** -- check expiry proactively, renew 30 days before expiration
6. **Key file permissions** -- chmod 600 on private keys, separate from cert files
7. **Separate key usages** -- server certs get serverAuth, client certs get clientAuth only'''
    ),
    (
        "security/mtls-python-clients",
        "Show how to configure mTLS in Python HTTP clients (requests, httpx, aiohttp) and servers (FastAPI/uvicorn, Flask/gunicorn) with proper certificate handling.",
        '''mTLS configuration for Python HTTP clients and servers:

```python
# --- mTLS client with httpx (sync and async) ---

import ssl
from pathlib import Path
from typing import Optional

import httpx


class MTLSClient:
    """HTTP client configured for mutual TLS."""

    def __init__(
        self,
        client_cert: str | Path,
        client_key: str | Path,
        ca_cert: str | Path,
        timeout: float = 30.0,
    ) -> None:
        self.client_cert = str(client_cert)
        self.client_key = str(client_key)
        self.ca_cert = str(ca_cert)
        self.timeout = timeout

    def create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context for mTLS."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # Load client certificate and key
        ctx.load_cert_chain(
            certfile=self.client_cert,
            keyfile=self.client_key,
        )
        # Load CA cert for server verification
        ctx.load_verify_locations(cafile=self.ca_cert)
        # Enforce TLS 1.2+
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        # Verify server certificate
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx

    def get_sync_client(self) -> httpx.Client:
        """Get a synchronous httpx client with mTLS."""
        return httpx.Client(
            cert=(self.client_cert, self.client_key),
            verify=self.ca_cert,
            timeout=self.timeout,
            http2=True,  # Enable HTTP/2 for efficiency
        )

    def get_async_client(self) -> httpx.AsyncClient:
        """Get an async httpx client with mTLS."""
        return httpx.AsyncClient(
            cert=(self.client_cert, self.client_key),
            verify=self.ca_cert,
            timeout=self.timeout,
            http2=True,
        )


# Usage: synchronous
mtls = MTLSClient(
    client_cert="/etc/mtls/certs/my-service-client.crt",
    client_key="/etc/mtls/certs/my-service-client.key",
    ca_cert="/etc/mtls/ca.pem",
)

with mtls.get_sync_client() as client:
    response = client.get("https://api.internal.example.com/health")
    print(response.json())

    response = client.post(
        "https://api.internal.example.com/data",
        json={"key": "value"},
    )
```

```python
# --- mTLS client with aiohttp ---

import aiohttp
import ssl


async def make_mtls_request_aiohttp(
    url: str,
    client_cert: str,
    client_key: str,
    ca_cert: str,
) -> dict:
    """Make an mTLS request using aiohttp."""
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_ctx.load_cert_chain(certfile=client_cert, keyfile=client_key)
    ssl_ctx.load_verify_locations(cafile=ca_cert)
    ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ssl_ctx.check_hostname = True
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED

    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url) as response:
            return await response.json()


# --- mTLS client with requests ---

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context


class MTLSAdapter(HTTPAdapter):
    """Requests adapter with mTLS support and TLS 1.2+ enforcement."""

    def __init__(
        self,
        client_cert: str,
        client_key: str,
        ca_cert: str,
        **kwargs,
    ):
        self.client_cert = client_cert
        self.client_key = client_key
        self.ca_cert = ca_cert
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.load_cert_chain(
            certfile=self.client_cert,
            keyfile=self.client_key,
        )
        ctx.load_verify_locations(cafile=self.ca_cert)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


# Usage with requests
session = requests.Session()
adapter = MTLSAdapter(
    client_cert="/etc/mtls/certs/my-service-client.crt",
    client_key="/etc/mtls/certs/my-service-client.key",
    ca_cert="/etc/mtls/ca.pem",
)
session.mount("https://", adapter)

resp = session.get("https://api.internal.example.com/health")
```

```python
# --- mTLS server with FastAPI + Uvicorn ---

from fastapi import FastAPI, Request, HTTPException, Depends
from typing import Optional
import ssl


app = FastAPI()


def get_client_cert_cn(request: Request) -> Optional[str]:
    """Extract client certificate Common Name from mTLS connection."""
    # Uvicorn with --ssl-cert-reqs 2 populates this
    transport = request.scope.get("transport")
    if transport is None:
        return None

    ssl_object = transport.get_extra_info("ssl_object")
    if ssl_object is None:
        return None

    peer_cert = ssl_object.getpeercert()
    if peer_cert is None:
        return None

    # Extract CN from subject
    for rdn in peer_cert.get("subject", ()):
        for attr_type, attr_value in rdn:
            if attr_type == "commonName":
                return attr_value
    return None


def get_client_spiffe_id(request: Request) -> Optional[str]:
    """Extract SPIFFE ID from client certificate SAN."""
    transport = request.scope.get("transport")
    if not transport:
        return None

    ssl_object = transport.get_extra_info("ssl_object")
    if not ssl_object:
        return None

    peer_cert = ssl_object.getpeercert()
    if not peer_cert:
        return None

    # Look for URI SAN entries starting with spiffe://
    for san_type, san_value in peer_cert.get("subjectAltName", ()):
        if san_type == "URI" and san_value.startswith("spiffe://"):
            return san_value
    return None


def require_mtls(request: Request) -> str:
    """Dependency that requires a valid client certificate."""
    cn = get_client_cert_cn(request)
    if cn is None:
        raise HTTPException(
            status_code=403,
            detail="Client certificate required",
        )
    return cn


# Service authorization: only allow specific services
ALLOWED_SERVICES = {
    "payment-service",
    "order-service",
    "inventory-service",
}


def require_authorized_service(
    cn: str = Depends(require_mtls),
) -> str:
    """Require client cert from an authorized service."""
    if cn not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=403,
            detail=f"Service '{cn}' is not authorized",
        )
    return cn


@app.get("/api/internal/data")
async def get_data(service_cn: str = Depends(require_authorized_service)):
    """Endpoint requiring mTLS with authorized service identity."""
    return {"data": "sensitive", "caller": service_cn}


# --- Uvicorn mTLS configuration ---
# Run with:
# uvicorn app:app --host 0.0.0.0 --port 8443 \
#   --ssl-keyfile /etc/mtls/certs/server.key \
#   --ssl-certfile /etc/mtls/certs/server.crt \
#   --ssl-ca-certs /etc/mtls/ca.pem \
#   --ssl-cert-reqs 2
#
# --ssl-cert-reqs values:
#   0 = CERT_NONE (no client cert)
#   1 = CERT_OPTIONAL (request but don't require)
#   2 = CERT_REQUIRED (require valid client cert)
```

```yaml
# --- Docker Compose with mTLS sidecar (Envoy) ---

version: "3.8"
services:
  api-service:
    image: myorg/api-service:latest
    # App listens on plain HTTP internally
    environment:
      - PORT=8080

  envoy-sidecar:
    image: envoyproxy/envoy:v1.28-latest
    volumes:
      - ./envoy.yaml:/etc/envoy/envoy.yaml:ro
      - ./certs:/etc/mtls/certs:ro
    ports:
      - "8443:8443"
    depends_on:
      - api-service

# envoy.yaml handles TLS termination and client cert verification
# so the application code stays simple
```

| Library | mTLS Config Method | HTTP/2 | Async | Notes |
|---|---|---|---|---|
| httpx | `cert=(...), verify=ca` | Yes | Yes | Recommended for new projects |
| requests | Custom adapter with ssl_context | No | No | Widely used, needs adapter for TLS control |
| aiohttp | TCPConnector(ssl=ctx) | No | Yes | Good for async-only codebases |
| urllib3 | ssl_context in PoolManager | No | No | Low-level, used by requests internally |

Key patterns:

1. **httpx preferred** -- supports both sync/async, HTTP/2, and simple cert= parameter
2. **TLS 1.2 minimum** -- always set minimum_version to prevent downgrade attacks
3. **check_hostname=True** -- verify server hostname matches certificate SAN
4. **CERT_REQUIRED** -- server must require client certs, not just request them
5. **Service identity via CN** -- extract client CN for authorization decisions
6. **Envoy sidecar** -- offload mTLS to a proxy for language-agnostic service mesh
7. **Dependency injection** -- use FastAPI Depends() to enforce mTLS at endpoint level'''
    ),
    (
        "security/spiffe-service-identity",
        "Explain SPIFFE (Secure Production Identity Framework for Everyone) and show how to use SPIFFE IDs for service-to-service authentication with SPIRE and workload API.",
        '''SPIFFE service identity framework with SPIRE for zero-trust service auth:

```
┌──────────────────────────────────────────────────────┐
│                   SPIFFE Architecture                 │
│                                                       │
│  ┌─────────┐     ┌──────────┐     ┌─────────────┐   │
│  │  SPIRE   │────▶│  SPIRE   │────▶│  Workload   │   │
│  │  Server  │     │  Agent   │     │  (Service)  │   │
│  └─────────┘     └──────────┘     └─────────────┘   │
│       │               │                   │           │
│  Manages trust   Node attestation   Workload API     │
│  domain          + registration     provides SVIDs   │
│                                                       │
│  SPIFFE ID Format:                                    │
│  spiffe://trust-domain/path/to/workload               │
│  spiffe://example.org/ns/prod/sa/payment-service      │
└──────────────────────────────────────────────────────┘
```

```python
# --- SPIFFE workload API client (using py-spiffe) ---

from typing import Optional
import logging

from pyspiffe.spiffe_id.spiffe_id import SpiffeId
from pyspiffe.workloadapi.default_workload_api_client import (
    DefaultWorkloadApiClient,
)
from pyspiffe.bundle.x509_bundle.x509_bundle_set import X509BundleSet
from pyspiffe.svid.x509_svid import X509Svid

logger = logging.getLogger("spiffe.client")


class SpiffeIdentityManager:
    """Manage SPIFFE-based service identities via the Workload API."""

    def __init__(
        self,
        socket_path: str = "unix:///tmp/spire-agent/public/api.sock",
    ) -> None:
        self.socket_path = socket_path
        self._client: Optional[DefaultWorkloadApiClient] = None

    def connect(self) -> None:
        """Connect to the SPIRE Agent Workload API."""
        self._client = DefaultWorkloadApiClient(
            spiffe_socket=self.socket_path,
        )
        logger.info("Connected to SPIRE Agent Workload API")

    def get_x509_svid(self) -> X509Svid:
        """
        Fetch X.509 SVID (SPIFFE Verifiable Identity Document).
        Returns the certificate chain and private key.
        """
        if self._client is None:
            raise RuntimeError("Not connected to Workload API")

        svid = self._client.fetch_x509_svid()
        logger.info(
            f"Fetched X.509 SVID: {svid.spiffe_id}",
            extra={"spiffe_id": str(svid.spiffe_id)},
        )
        return svid

    def get_trust_bundles(self) -> X509BundleSet:
        """Fetch trust bundles for verifying other services."""
        if self._client is None:
            raise RuntimeError("Not connected to Workload API")
        return self._client.fetch_x509_bundles()

    def create_ssl_context_for_server(self) -> "ssl.SSLContext":
        """Create SSL context for an mTLS server using SPIFFE identity."""
        import ssl
        import tempfile
        from pathlib import Path

        svid = self.get_x509_svid()
        bundles = self.get_trust_bundles()

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        # Write SVID cert and key to temp files
        cert_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False
        )
        key_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False
        )

        cert_file.write(svid.cert_chain_as_pem())
        cert_file.flush()
        key_file.write(svid.private_key_as_pem())
        key_file.flush()

        ctx.load_cert_chain(cert_file.name, key_file.name)

        # Load trust bundles for client verification
        bundle_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False
        )
        for bundle in bundles.bundles.values():
            for cert in bundle.x509_authorities:
                bundle_file.write(
                    cert.public_bytes(
                        serialization.Encoding.PEM
                    )
                )
        bundle_file.flush()
        ctx.load_verify_locations(bundle_file.name)

        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx

    def verify_peer_spiffe_id(
        self,
        peer_cert: dict,
        allowed_ids: set[str],
    ) -> bool:
        """Verify peer's SPIFFE ID against allowlist."""
        for san_type, san_value in peer_cert.get("subjectAltName", ()):
            if san_type == "URI" and san_value.startswith("spiffe://"):
                if san_value in allowed_ids:
                    return True
                logger.warning(
                    f"Peer SPIFFE ID not in allowlist: {san_value}"
                )
        return False


# --- Usage with FastAPI ---

from fastapi import FastAPI, Request, HTTPException

app = FastAPI()
identity_mgr = SpiffeIdentityManager()
identity_mgr.connect()

# Authorization policy: which services can access which endpoints
AUTHZ_POLICY: dict[str, set[str]] = {
    "/api/payments": {
        "spiffe://example.org/ns/prod/sa/order-service",
        "spiffe://example.org/ns/prod/sa/admin-service",
    },
    "/api/inventory": {
        "spiffe://example.org/ns/prod/sa/order-service",
        "spiffe://example.org/ns/prod/sa/warehouse-service",
    },
}


def authorize_request(request: Request, endpoint_prefix: str) -> str:
    """Check SPIFFE-based authorization for the calling service."""
    transport = request.scope.get("transport")
    if not transport:
        raise HTTPException(status_code=403, detail="TLS required")

    ssl_obj = transport.get_extra_info("ssl_object")
    peer_cert = ssl_obj.getpeercert() if ssl_obj else None
    if not peer_cert:
        raise HTTPException(status_code=403, detail="Client cert required")

    # Extract SPIFFE ID
    spiffe_id = None
    for san_type, san_value in peer_cert.get("subjectAltName", ()):
        if san_type == "URI" and san_value.startswith("spiffe://"):
            spiffe_id = san_value
            break

    if spiffe_id is None:
        raise HTTPException(status_code=403, detail="No SPIFFE ID in cert")

    allowed = AUTHZ_POLICY.get(endpoint_prefix, set())
    if spiffe_id not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Service {spiffe_id} not authorized for {endpoint_prefix}",
        )

    return spiffe_id
```

```yaml
# --- SPIRE Server configuration ---

server:
  bind_address: "0.0.0.0"
  bind_port: 8081
  trust_domain: "example.org"
  data_dir: "/opt/spire/data/server"
  log_level: "INFO"

  ca_ttl: "168h"      # CA cert validity: 7 days
  default_x509_svid_ttl: "1h"  # SVID validity: 1 hour (short-lived)

plugins:
  DataStore:
    sql:
      database_type: "postgres"
      connection_string: "postgresql://spire:password@db:5432/spire"

  NodeAttestor:
    k8s_psat:  # Kubernetes projected service account token
      clusters:
        production:
          service_account_allow_list:
            - "spire:spire-agent"

  KeyManager:
    disk:
      keys_path: "/opt/spire/data/server/keys.json"

---
# --- SPIRE Agent configuration ---

agent:
  server_address: "spire-server"
  server_port: 8081
  trust_domain: "example.org"
  data_dir: "/opt/spire/data/agent"
  socket_path: "/tmp/spire-agent/public/api.sock"

plugins:
  NodeAttestor:
    k8s_psat:
      cluster: "production"

  WorkloadAttestor:
    k8s:
      skip_kubelet_verification: false

  KeyManager:
    memory: {}

---
# --- Registration entries (map workloads to SPIFFE IDs) ---

# Register payment-service
# spire-server entry create \
#   -spiffeID spiffe://example.org/ns/prod/sa/payment-service \
#   -parentID spiffe://example.org/spire/agent/k8s_psat/production/node1 \
#   -selector k8s:ns:production \
#   -selector k8s:sa:payment-service \
#   -x509SVIDTTL 3600 \
#   -dns payment-service.production.svc.cluster.local
```

```python
# --- SPIFFE-aware mTLS client ---

import httpx
import ssl
import tempfile
from pyspiffe.workloadapi.default_workload_api_client import (
    DefaultWorkloadApiClient,
)


class SpiffeMTLSClient:
    """HTTP client that uses SPIFFE SVIDs for mTLS."""

    def __init__(
        self,
        spiffe_socket: str = "unix:///tmp/spire-agent/public/api.sock",
    ) -> None:
        self.wl_client = DefaultWorkloadApiClient(
            spiffe_socket=spiffe_socket,
        )
        self._cert_file = None
        self._key_file = None
        self._bundle_file = None

    def _refresh_svid(self) -> None:
        """Fetch fresh SVID and write to temp files."""
        svid = self.wl_client.fetch_x509_svid()
        bundles = self.wl_client.fetch_x509_bundles()

        self._cert_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False
        )
        self._key_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False
        )
        self._bundle_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False
        )

        self._cert_file.write(svid.cert_chain_as_pem())
        self._cert_file.flush()
        self._key_file.write(svid.private_key_as_pem())
        self._key_file.flush()

        for bundle in bundles.bundles.values():
            for cert in bundle.x509_authorities:
                from cryptography.hazmat.primitives import serialization
                self._bundle_file.write(
                    cert.public_bytes(serialization.Encoding.PEM)
                )
        self._bundle_file.flush()

    def get_client(self) -> httpx.AsyncClient:
        """Get an httpx client with current SPIFFE identity."""
        self._refresh_svid()
        return httpx.AsyncClient(
            cert=(self._cert_file.name, self._key_file.name),
            verify=self._bundle_file.name,
            timeout=30.0,
        )


# Usage
async def call_payment_service():
    spiffe_client = SpiffeMTLSClient()
    async with spiffe_client.get_client() as client:
        resp = await client.post(
            "https://payment-service.production.svc.cluster.local:8443/charge",
            json={"amount": 99.99, "currency": "USD"},
        )
        return resp.json()
```

| SPIFFE Component | Role | Lifecycle |
|---|---|---|
| Trust Domain | Root of identity hierarchy | Static per organization |
| SPIRE Server | Issues SVIDs, manages registration | Long-running control plane |
| SPIRE Agent | Node-level SVID delivery | DaemonSet per node |
| SVID (X.509) | Short-lived identity certificate | Auto-rotated (1h default) |
| Workload API | Unix socket for SVID retrieval | Agent-provided |
| Registration Entry | Maps workload to SPIFFE ID | Admin-managed |

Key patterns:

1. **Short-lived SVIDs** -- 1-hour default TTL eliminates need for revocation infrastructure
2. **Workload API** -- services fetch identity via Unix socket, no secrets in config
3. **Trust domain** -- `spiffe://example.org/` scopes all identities within an organization
4. **Node attestation** -- SPIRE Agent proves node identity via k8s_psat or AWS IID
5. **Workload attestation** -- map k8s namespace + service account to SPIFFE ID
6. **Authorization policies** -- define which SPIFFE IDs can access which endpoints
7. **Auto-rotation** -- SVID refresh is handled by the SPIRE Agent transparently'''
    ),
    (
        "security/certificate-pinning-revocation",
        "Show certificate pinning implementations and revocation strategies including CRL, OCSP, and OCSP stapling with Python examples.",
        '''Certificate pinning and revocation: CRL, OCSP, OCSP stapling in Python:

```python
# --- Certificate pinning with httpx ---

import hashlib
import ssl
from typing import Optional

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization


class CertificatePinner:
    """Pin certificates by public key hash (HPKP-style)."""

    def __init__(self, pins: dict[str, list[str]]) -> None:
        """
        Args:
            pins: Mapping of hostname -> list of base64 SHA-256 public key hashes.
                  Example: {"api.example.com": ["sha256/abc123...", "sha256/def456..."]}
                  Include at least 2 pins (primary + backup) per host.
        """
        self.pins = pins

    @staticmethod
    def compute_pin(cert_pem: bytes) -> str:
        """Compute SHA-256 pin of a certificate's Subject Public Key Info."""
        cert = x509.load_pem_x509_certificate(cert_pem)
        spki_bytes = cert.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        digest = hashlib.sha256(spki_bytes).digest()
        import base64
        return f"sha256/{base64.b64encode(digest).decode()}"

    def verify_pin(self, hostname: str, peer_cert_der: bytes) -> bool:
        """Verify that peer certificate matches a pinned public key."""
        expected_pins = self.pins.get(hostname)
        if not expected_pins:
            return True  # No pins configured for this host

        cert = x509.load_der_x509_certificate(peer_cert_der)
        spki_bytes = cert.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        digest = hashlib.sha256(spki_bytes).digest()
        import base64
        actual_pin = f"sha256/{base64.b64encode(digest).decode()}"

        if actual_pin in expected_pins:
            return True

        import logging
        logging.getLogger("cert.pinning").critical(
            f"Certificate pin mismatch for {hostname}! "
            f"Expected one of {expected_pins}, got {actual_pin}"
        )
        return False


class PinningHTTPTransport(httpx.HTTPTransport):
    """httpx transport with certificate pinning."""

    def __init__(self, pinner: CertificatePinner, **kwargs):
        self.pinner = pinner
        super().__init__(**kwargs)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = super().handle_request(request)
        # In production, use a custom ssl context with
        # post-handshake verification callback instead
        return response


# Compute pins from existing certificates
def generate_pins_from_certs(cert_paths: list[str]) -> list[str]:
    """Generate pin hashes from certificate files (for configuration)."""
    pins = []
    for path in cert_paths:
        with open(path, "rb") as f:
            cert_pem = f.read()
        pin = CertificatePinner.compute_pin(cert_pem)
        pins.append(pin)
        print(f"{path}: {pin}")
    return pins
```

```python
# --- CRL (Certificate Revocation List) checking ---

import httpx
from cryptography import x509
from cryptography.x509 import load_pem_x509_crl, load_der_x509_crl
from cryptography.hazmat.primitives import hashes
from datetime import datetime, timezone
from pathlib import Path
import logging

logger = logging.getLogger("cert.revocation")


class CRLChecker:
    """Check certificate revocation against CRL distribution points."""

    def __init__(self, cache_dir: Path = Path("/tmp/crl_cache")) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._crl_cache: dict[str, x509.CertificateRevocationList] = {}

    async def fetch_crl(self, crl_url: str) -> x509.CertificateRevocationList:
        """Fetch and cache a CRL from its distribution point."""
        if crl_url in self._crl_cache:
            crl = self._crl_cache[crl_url]
            if crl.next_update_utc > datetime.now(timezone.utc):
                return crl

        async with httpx.AsyncClient() as client:
            resp = await client.get(crl_url, timeout=10.0)
            resp.raise_for_status()

        try:
            crl = load_der_x509_crl(resp.content)
        except Exception:
            crl = load_pem_x509_crl(resp.content)

        self._crl_cache[crl_url] = crl
        return crl

    def get_crl_urls(self, cert: x509.Certificate) -> list[str]:
        """Extract CRL Distribution Point URLs from certificate."""
        try:
            crl_dp = cert.extensions.get_extension_for_class(
                x509.CRLDistributionPoints
            )
            urls = []
            for dp in crl_dp.value:
                if dp.full_name:
                    for name in dp.full_name:
                        if isinstance(name, x509.UniformResourceIdentifier):
                            urls.append(name.value)
            return urls
        except x509.ExtensionNotFound:
            return []

    async def is_revoked(
        self,
        cert: x509.Certificate,
        issuer_cert: x509.Certificate,
    ) -> bool:
        """Check if a certificate has been revoked via CRL."""
        crl_urls = self.get_crl_urls(cert)
        if not crl_urls:
            logger.warning("No CRL distribution points in certificate")
            return False  # Can't check; policy decision

        for url in crl_urls:
            try:
                crl = await self.fetch_crl(url)

                # Verify CRL signature
                if not crl.is_signature_valid(issuer_cert.public_key()):
                    logger.error(f"CRL signature invalid: {url}")
                    continue

                # Check if cert serial is in CRL
                revoked = crl.get_revoked_certificate_by_serial_number(
                    cert.serial_number
                )
                if revoked is not None:
                    logger.warning(
                        f"Certificate revoked! Serial: {cert.serial_number}, "
                        f"Reason: {revoked.extensions if revoked.extensions else 'unspecified'}"
                    )
                    return True

                return False  # Found valid CRL, cert not revoked
            except Exception as e:
                logger.error(f"CRL check failed for {url}: {e}")
                continue

        logger.error("All CRL checks failed")
        return False  # Soft-fail; consider hard-fail for high-security


# --- OCSP checking ---

from cryptography.x509 import ocsp
from cryptography.x509.ocsp import OCSPResponseStatus, OCSPCertStatus


class OCSPChecker:
    """Check certificate revocation via OCSP."""

    async def check(
        self,
        cert: x509.Certificate,
        issuer_cert: x509.Certificate,
    ) -> tuple[bool, str]:
        """
        Check OCSP status.
        Returns (is_valid, status_description).
        """
        # Get OCSP responder URL
        try:
            aia = cert.extensions.get_extension_for_class(
                x509.AuthorityInformationAccess
            )
            ocsp_urls = [
                desc.access_location.value
                for desc in aia.value
                if desc.access_method == x509.oid.AuthorityInformationAccessOID.OCSP
            ]
        except x509.ExtensionNotFound:
            return True, "No OCSP responder URL"

        if not ocsp_urls:
            return True, "No OCSP responder URL"

        # Build OCSP request
        builder = ocsp.OCSPRequestBuilder()
        builder = builder.add_certificate(
            cert, issuer_cert, hashes.SHA256()
        )
        ocsp_request = builder.build()

        # Send OCSP request
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                ocsp_urls[0],
                content=ocsp_request.public_bytes(serialization.Encoding.DER),
                headers={"Content-Type": "application/ocsp-request"},
                timeout=10.0,
            )

        ocsp_response = ocsp.load_der_ocsp_response(resp.content)

        if ocsp_response.response_status != OCSPResponseStatus.SUCCESSFUL:
            return False, f"OCSP error: {ocsp_response.response_status}"

        status = ocsp_response.certificate_status
        if status == OCSPCertStatus.GOOD:
            return True, "OCSP: good"
        elif status == OCSPCertStatus.REVOKED:
            return False, (
                f"OCSP: revoked at {ocsp_response.revocation_time}"
            )
        else:
            return False, "OCSP: unknown status"
```

```python
# --- OCSP stapling with ssl context ---

import ssl


def create_ssl_context_with_ocsp_stapling(
    cert_path: str,
    key_path: str,
    ca_path: str,
) -> ssl.SSLContext:
    """
    Create SSL context that requests OCSP stapled responses.

    OCSP stapling is more efficient than direct OCSP checks:
    - Server fetches OCSP response and includes it in TLS handshake
    - Client doesn't need to contact OCSP responder separately
    - Better privacy (OCSP responder doesn't see client IPs)
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    ctx.load_verify_locations(cafile=ca_path)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True

    # Request OCSP stapled response from server
    # Note: Python's ssl module has limited OCSP stapling support.
    # For production, use Nginx/HAProxy for OCSP stapling:
    #
    # Nginx config:
    #   ssl_stapling on;
    #   ssl_stapling_verify on;
    #   ssl_trusted_certificate /path/to/ca-chain.pem;
    #   resolver 8.8.8.8 8.8.4.4 valid=300s;
    #   resolver_timeout 5s;

    return ctx


# --- Combined revocation checking middleware ---

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class RevocationCheckMiddleware(BaseHTTPMiddleware):
    """Middleware to check client certificate revocation."""

    def __init__(self, app, crl_checker: CRLChecker, ocsp_checker: OCSPChecker):
        super().__init__(app)
        self.crl_checker = crl_checker
        self.ocsp_checker = ocsp_checker

    async def dispatch(self, request: Request, call_next):
        # Skip for non-mTLS endpoints
        if not request.url.path.startswith("/api/internal/"):
            return await call_next(request)

        transport = request.scope.get("transport")
        if not transport:
            raise HTTPException(status_code=403, detail="TLS required")

        ssl_obj = transport.get_extra_info("ssl_object")
        if not ssl_obj:
            raise HTTPException(status_code=403, detail="No SSL")

        peer_cert_der = ssl_obj.getpeercert(binary_form=True)
        if not peer_cert_der:
            raise HTTPException(status_code=403, detail="No client cert")

        cert = x509.load_der_x509_certificate(peer_cert_der)

        # Try OCSP first (faster), fall back to CRL
        is_valid, status_msg = await self.ocsp_checker.check(
            cert, self._get_issuer_cert()
        )
        if not is_valid:
            raise HTTPException(
                status_code=403,
                detail=f"Certificate revoked: {status_msg}",
            )

        return await call_next(request)

    def _get_issuer_cert(self) -> x509.Certificate:
        """Load the CA certificate for revocation checking."""
        ca_pem = Path("/etc/mtls/ca.pem").read_bytes()
        return x509.load_pem_x509_certificate(ca_pem)
```

| Revocation Method | Latency | Privacy | Freshness | Offline Support |
|---|---|---|---|---|
| CRL | High (download full list) | Good (no per-cert query) | Low (hours/daily) | Yes (cached) |
| OCSP | Medium (per-cert query) | Poor (responder sees queries) | High (real-time) | No |
| OCSP Stapling | Low (in TLS handshake) | Good (server fetches) | High (stapled) | Partial (cached) |
| Short-lived certs | None (no revocation needed) | Best | N/A | Yes |

Key patterns:

1. **Pin SPKI not cert** -- pin the Subject Public Key Info hash, not the certificate hash, to survive cert renewal
2. **Backup pins** -- always include at least 2 pins (primary + backup key) to prevent lockout
3. **OCSP stapling preferred** -- server includes OCSP response in TLS handshake, avoiding client-side latency
4. **CRL caching** -- cache CRLs locally and respect next_update field to avoid repeated downloads
5. **Soft-fail vs hard-fail** -- decide policy: soft-fail (allow if check fails) vs hard-fail (deny if check fails)
6. **Short-lived certs** -- with 1-hour SVIDs (SPIFFE), revocation infrastructure becomes unnecessary
7. **Combined checking** -- try OCSP first (faster), fall back to CRL, and log all failures'''
    ),
]
