"""Networking — HTTP/2, TLS, DNS, and protocol patterns."""

PAIRS = [
    (
        "networking/http-advanced",
        "Show advanced HTTP patterns: HTTP/2 multiplexing, connection pooling, retry strategies, and caching headers.",
        '''Advanced HTTP patterns:

```python
import httpx
import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# --- HTTP/2 client with connection pooling ---

class APIClient:
    """Production HTTP client with connection pooling, retries, and timeouts."""

    def __init__(self, base_url: str, token: str = None,
                 max_connections: int = 100,
                 max_keepalive: int = 20):
        self.base_url = base_url.rstrip("/")

        # Connection pool limits
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
            keepalive_expiry=30,
        )

        # Timeout configuration
        timeout = httpx.Timeout(
            connect=5.0,    # Connection timeout
            read=30.0,      # Read timeout
            write=10.0,     # Write timeout
            pool=10.0,      # Pool checkout timeout
        )

        headers = {"User-Agent": "MyApp/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            http2=True,              # Enable HTTP/2 multiplexing
            limits=limits,
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
        )

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self._request("POST", path, **kwargs)

    async def _request(self, method: str, path: str,
                       retries: int = 3, **kwargs) -> httpx.Response:
        """Request with exponential backoff retry."""
        last_error = None

        for attempt in range(retries):
            try:
                response = await self._client.request(method, path, **kwargs)

                # Retry on server errors
                if response.status_code >= 500 and attempt < retries - 1:
                    delay = min(2 ** attempt * 0.5, 10)
                    logger.warning(
                        "Server error %d, retry %d/%d in %.1fs",
                        response.status_code, attempt + 1, retries, delay
                    )
                    await asyncio.sleep(delay)
                    continue

                # Retry on rate limit
                if response.status_code == 429:
                    retry_after = float(
                        response.headers.get("Retry-After", 2 ** attempt)
                    )
                    logger.warning("Rate limited, waiting %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response

            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_error = e
                if attempt < retries - 1:
                    delay = min(2 ** attempt, 10)
                    logger.warning("Request failed, retry in %.1fs: %s",
                                 delay, e)
                    await asyncio.sleep(delay)

        raise last_error or httpx.RequestError("All retries exhausted")

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# --- Concurrent requests with HTTP/2 multiplexing ---

async def fetch_many(client: APIClient, paths: list[str],
                     max_concurrent: int = 10) -> list[dict]:
    """Fetch multiple URLs concurrently with semaphore."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(path: str) -> dict:
        async with semaphore:
            response = await client.get(path)
            return response.json()

    tasks = [fetch_one(path) for path in paths]
    return await asyncio.gather(*tasks, return_exceptions=True)


# --- Cache-aware client ---

class CachingClient:
    """HTTP client that respects cache headers."""

    def __init__(self, client: APIClient):
        self.client = client
        self._cache: dict[str, tuple[Any, float, str]] = {}  # url -> (data, expires, etag)

    async def get_cached(self, path: str) -> Any:
        # Check local cache
        if path in self._cache:
            data, expires, etag = self._cache[path]
            if time.time() < expires:
                return data  # Cache hit

            # Conditional request with ETag
            headers = {"If-None-Match": etag} if etag else {}
            response = await self.client.get(path, headers=headers)
            if response.status_code == 304:
                return data  # Not modified

        else:
            response = await self.client.get(path)

        # Parse cache headers
        data = response.json()
        cache_control = response.headers.get("Cache-Control", "")
        etag = response.headers.get("ETag", "")

        max_age = 0
        for directive in cache_control.split(","):
            directive = directive.strip()
            if directive.startswith("max-age="):
                max_age = int(directive.split("=")[1])

        if max_age > 0 or etag:
            self._cache[path] = (data, time.time() + max_age, etag)

        return data
```

HTTP patterns:
1. **HTTP/2 multiplexing** — `http2=True` sends concurrent requests over single connection
2. **Connection pooling** — `Limits()` configures pool size and keepalive
3. **Separate timeouts** — connect, read, write, pool each configurable
4. **Exponential backoff** — retry on 5xx/429 with increasing delays
5. **ETag + 304** — conditional requests avoid re-downloading unchanged data'''
    ),
    (
        "networking/tls-certificates",
        "Show TLS and certificate patterns: certificate generation, mTLS, certificate pinning, and ACME/Let's Encrypt.",
        '''TLS and certificate patterns:

```python
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from datetime import datetime, timedelta, timezone
import ssl
import ipaddress


# --- Generate self-signed certificate ---

def generate_self_signed_cert(
    common_name: str = "localhost",
    san_dns: list[str] = None,
    san_ips: list[str] = None,
    days: int = 365,
) -> tuple[bytes, bytes]:
    """Generate self-signed certificate + private key."""

    # Generate key (ECDSA P-256 — modern, fast)
    key = ec.generate_private_key(ec.SECP256R1())

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Development"),
    ])

    # Subject Alternative Names
    san_list = [x509.DNSName(common_name)]
    for dns in (san_dns or []):
        san_list.append(x509.DNSName(dns))
    for ip in (san_ips or ["127.0.0.1"]):
        san_list.append(x509.IPAddress(ipaddress.ip_address(ip)))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=days))
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    return cert_pem, key_pem


# --- Generate CA + server certificate ---

def generate_ca_and_server_cert(
    ca_name: str = "My CA",
    server_name: str = "api.example.com",
):
    """Generate CA certificate and sign a server certificate."""

    # CA key and cert
    ca_key = rsa.generate_private_key(65537, 4096)
    ca_name_obj = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, ca_name),
    ])

    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name_obj)
        .issuer_name(ca_name_obj)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # Server key and CSR
    server_key = ec.generate_private_key(ec.SECP256R1())

    server_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, server_name),
        ]))
        .issuer_name(ca_name_obj)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(server_name),
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())  # Signed by CA
    )

    return ca_cert, ca_key, server_cert, server_key


# --- mTLS SSL context ---

def create_mtls_server_context(
    cert_file: str,
    key_file: str,
    ca_file: str,
) -> ssl.SSLContext:
    """Create SSL context for mTLS server."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_file, key_file)
    ctx.load_verify_locations(ca_file)
    ctx.verify_mode = ssl.CERT_REQUIRED  # Require client cert
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20")
    return ctx

def create_mtls_client_context(
    cert_file: str,
    key_file: str,
    ca_file: str,
) -> ssl.SSLContext:
    """Create SSL context for mTLS client."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_cert_chain(cert_file, key_file)
    ctx.load_verify_locations(ca_file)
    ctx.check_hostname = True
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


# --- Certificate pinning ---

def verify_certificate_pin(
    cert_der: bytes,
    expected_pin: str,
) -> bool:
    """Verify certificate matches pinned SHA-256 hash."""
    import hashlib
    import base64
    actual_pin = base64.b64encode(
        hashlib.sha256(cert_der).digest()
    ).decode()
    return actual_pin == expected_pin
```

TLS patterns:
1. **ECDSA P-256** — modern key type (smaller + faster than RSA 2048)
2. **SAN required** — browsers require SubjectAlternativeName, CN alone isn't enough
3. **mTLS** — `CERT_REQUIRED` on server verifies client certificates
4. **TLS 1.2 minimum** — disable TLS 1.0/1.1 (deprecated)
5. **Certificate pinning** — SHA-256 hash of cert prevents MITM with rogue CAs'''
    ),
    (
        "networking/dns-resolution",
        "Show DNS patterns: resolution, caching, service discovery, and DNS-over-HTTPS.",
        '''DNS and service discovery patterns:

```python
import socket
import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
import struct

logger = logging.getLogger(__name__)


# --- DNS resolution with caching ---

@dataclass
class DNSRecord:
    hostname: str
    addresses: list[str]
    ttl: int
    resolved_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.resolved_at + self.ttl


class DNSCache:
    """Thread-safe DNS cache with TTL."""

    def __init__(self):
        self._cache: dict[str, DNSRecord] = {}

    def get(self, hostname: str) -> Optional[DNSRecord]:
        record = self._cache.get(hostname)
        if record and not record.is_expired:
            return record
        return None

    def put(self, hostname: str, addresses: list[str], ttl: int = 300):
        self._cache[hostname] = DNSRecord(
            hostname=hostname,
            addresses=addresses,
            ttl=ttl,
        )

    def evict_expired(self):
        self._cache = {
            k: v for k, v in self._cache.items()
            if not v.is_expired
        }


class Resolver:
    """Async DNS resolver with caching and round-robin."""

    def __init__(self, cache_ttl: int = 300):
        self.cache = DNSCache()
        self.cache_ttl = cache_ttl
        self._round_robin: dict[str, int] = {}

    async def resolve(self, hostname: str, port: int = 443) -> str:
        """Resolve hostname to IP with caching and round-robin."""
        record = self.cache.get(hostname)
        if record:
            return self._next_address(hostname, record.addresses)

        # Resolve asynchronously
        loop = asyncio.get_event_loop()
        try:
            results = await loop.getaddrinfo(
                hostname, port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
            addresses = list(set(r[4][0] for r in results))
            self.cache.put(hostname, addresses, self.cache_ttl)
            return self._next_address(hostname, addresses)

        except socket.gaierror as e:
            logger.error("DNS resolution failed for %s: %s", hostname, e)
            raise

    def _next_address(self, hostname: str, addresses: list[str]) -> str:
        """Round-robin across resolved addresses."""
        idx = self._round_robin.get(hostname, 0)
        address = addresses[idx % len(addresses)]
        self._round_robin[hostname] = idx + 1
        return address


# --- Service discovery pattern ---

@dataclass
class ServiceEndpoint:
    host: str
    port: int
    weight: int = 1
    priority: int = 0
    healthy: bool = True
    metadata: dict = field(default_factory=dict)


class ServiceRegistry:
    """Simple service registry with health checking."""

    def __init__(self):
        self._services: dict[str, list[ServiceEndpoint]] = {}
        self._watchers: dict[str, list] = {}

    def register(self, service_name: str, endpoint: ServiceEndpoint):
        """Register a service endpoint."""
        if service_name not in self._services:
            self._services[service_name] = []
        self._services[service_name].append(endpoint)
        self._notify_watchers(service_name)

    def deregister(self, service_name: str, host: str, port: int):
        """Remove a service endpoint."""
        if service_name in self._services:
            self._services[service_name] = [
                ep for ep in self._services[service_name]
                if not (ep.host == host and ep.port == port)
            ]
            self._notify_watchers(service_name)

    def discover(self, service_name: str) -> list[ServiceEndpoint]:
        """Get healthy endpoints for a service."""
        endpoints = self._services.get(service_name, [])
        healthy = [ep for ep in endpoints if ep.healthy]

        # Sort by priority, then weighted random
        healthy.sort(key=lambda ep: ep.priority)
        return healthy

    def watch(self, service_name: str, callback):
        """Watch for service changes."""
        if service_name not in self._watchers:
            self._watchers[service_name] = []
        self._watchers[service_name].append(callback)

    def _notify_watchers(self, service_name: str):
        endpoints = self.discover(service_name)
        for callback in self._watchers.get(service_name, []):
            callback(service_name, endpoints)


# Usage:
# registry = ServiceRegistry()
# registry.register("user-service", ServiceEndpoint("10.0.1.1", 8080))
# registry.register("user-service", ServiceEndpoint("10.0.1.2", 8080))
# endpoints = registry.discover("user-service")


# --- Health check integration ---

async def health_check_loop(registry: ServiceRegistry,
                             interval: float = 10.0):
    """Periodically check health of all registered services."""
    import httpx

    while True:
        for name, endpoints in registry._services.items():
            for ep in endpoints:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(
                            f"http://{ep.host}:{ep.port}/health"
                        )
                        ep.healthy = resp.status_code == 200
                except Exception:
                    ep.healthy = False

        await asyncio.sleep(interval)
```

DNS/service discovery patterns:
1. **DNS caching** — cache resolved addresses with TTL to reduce lookups
2. **Round-robin** — rotate across resolved IPs for client-side load balancing
3. **Service registry** — register/discover/watch pattern for microservices
4. **Health checking** — periodically verify endpoint health
5. **Async resolution** — `getaddrinfo` in event loop avoids blocking'''
    ),
]
"""
