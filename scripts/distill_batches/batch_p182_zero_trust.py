"""Zero-trust security: mTLS everywhere, SPIFFE/SPIRE identity, OPA/Rego policies, network segmentation, identity-aware proxies."""

PAIRS = [
    (
        "security/zero-trust-mtls-service-mesh",
        "How do I implement mutual TLS (mTLS) across all microservices in a zero-trust architecture? Show how to set up certificate management, enforce mTLS at the application level in Python, and handle certificate rotation.",
        '''Mutual TLS (mTLS) is the cornerstone of zero-trust networking -- every service must prove its identity via X.509 certificates, and every connection is encrypted and authenticated in both directions. Here is a production-grade approach:

## Architecture Overview

| Component | Role |
|---|---|
| Root CA | Offline root certificate authority |
| Intermediate CA | Online CA for issuing short-lived service certs |
| SPIFFE/SPIRE | Automated identity issuance and rotation |
| mTLS Enforcer | Sidecar or library enforcing mutual authentication |
| Certificate Store | Vault or SPIRE agent socket for cert delivery |

## Certificate Authority and mTLS Rotation System

```python
#!/usr/bin/env python3
"""
Zero-trust mTLS certificate management system.
Uses step-ca as the intermediate CA and provides
automatic certificate rotation for Python services.
"""

import ssl
import json
import asyncio
import hashlib
import logging
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
import aiohttp
import aiofiles

logger = logging.getLogger(__name__)


@dataclass
class CertificateBundle:
    """Holds a service mTLS certificate bundle."""
    cert_pem: bytes
    key_pem: bytes
    ca_bundle_pem: bytes
    serial_number: str
    not_after: datetime
    spiffe_id: str

    @property
    def time_to_expiry(self) -> timedelta:
        return self.not_after - datetime.now(timezone.utc)

    @property
    def needs_rotation(self) -> bool:
        return self.time_to_expiry < timedelta(hours=6)


@dataclass
class MTLSConfig:
    """Configuration for mTLS enforcement."""
    ca_cert_path: str
    trust_domain: str = "hiveai.prod"
    cert_ttl: str = "12h"
    step_ca_url: str = "https://ca.internal:9443"
    provisioner_name: str = "service-provisioner"
    provisioner_password_file: str = "/run/secrets/ca-password"
    allowed_spiffe_ids: list[str] = field(default_factory=list)
    min_tls_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1_3


class CertificateRotator:
    """Manages automatic certificate issuance and rotation."""

    def __init__(self, config: MTLSConfig, service_name: str):
        self.config = config
        self.service_name = service_name
        self.spiffe_id = f"spiffe://{config.trust_domain}/service/{service_name}"
        self._current_bundle: Optional[CertificateBundle] = None
        self._rotation_task: Optional[asyncio.Task] = None
        self._cert_dir = Path(tempfile.mkdtemp(prefix=f"mtls-{service_name}-"))
        self._callbacks: list = []

    async def start(self) -> CertificateBundle:
        """Issue initial certificate and start rotation loop."""
        self._current_bundle = await self._issue_certificate()
        self._rotation_task = asyncio.create_task(self._rotation_loop())
        logger.info(
            "mTLS initialized for %s (SPIFFE: %s, expires: %s)",
            self.service_name, self.spiffe_id,
            self._current_bundle.not_after.isoformat(),
        )
        return self._current_bundle

    async def stop(self):
        """Stop rotation and securely wipe temp certs."""
        if self._rotation_task:
            self._rotation_task.cancel()
            try:
                await self._rotation_task
            except asyncio.CancelledError:
                pass
        for f in self._cert_dir.iterdir():
            f.write_bytes(b"\\x00" * f.stat().st_size)
            f.unlink()
        self._cert_dir.rmdir()

    def on_rotation(self, callback):
        self._callbacks.append(callback)

    async def _issue_certificate(self) -> CertificateBundle:
        """Issue a new certificate from step-ca."""
        key = ec.generate_private_key(ec.SECP256R1())
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, self.service_name),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "HiveAI"),
            ]))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.UniformResourceIdentifier(self.spiffe_id),
                    x509.DNSName(f"{self.service_name}.svc.cluster.local"),
                ]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        csr_path = self._cert_dir / "service.csr"
        async with aiofiles.open(csr_path, "wb") as f:
            await f.write(csr.public_bytes(serialization.Encoding.PEM))

        cert_path = self._cert_dir / "service.crt"
        subprocess.run([
            "step", "ca", "sign",
            "--ca-url", self.config.step_ca_url,
            "--provisioner", self.config.provisioner_name,
            "--provisioner-password-file", self.config.provisioner_password_file,
            "--not-after", self.config.cert_ttl,
            str(csr_path), str(cert_path),
        ], capture_output=True, text=True, check=True, timeout=30)

        async with aiofiles.open(cert_path, "rb") as f:
            cert_pem = await f.read()
        cert = x509.load_pem_x509_certificate(cert_pem)
        async with aiofiles.open(self.config.ca_cert_path, "rb") as f:
            ca_bundle = await f.read()

        return CertificateBundle(
            cert_pem=cert_pem, key_pem=key_pem, ca_bundle_pem=ca_bundle,
            serial_number=format(cert.serial_number, "x"),
            not_after=cert.not_valid_after_utc, spiffe_id=self.spiffe_id,
        )

    async def _rotation_loop(self):
        while True:
            try:
                await asyncio.sleep(60)
                if self._current_bundle and self._current_bundle.needs_rotation:
                    old = self._current_bundle.serial_number
                    self._current_bundle = await self._issue_certificate()
                    logger.info("Cert rotated: %s -> %s", old,
                                self._current_bundle.serial_number)
                    for cb in self._callbacks:
                        await cb(self._current_bundle)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Rotation failed, retry in 30s")
                await asyncio.sleep(30)

    @property
    def bundle(self) -> Optional[CertificateBundle]:
        return self._current_bundle


class MTLSServer:
    """Creates mTLS-enforced SSL contexts with SPIFFE validation."""

    def __init__(self, config: MTLSConfig, rotator: CertificateRotator):
        self.config = config
        self.rotator = rotator

    def create_server_context(self) -> ssl.SSLContext:
        bundle = self.rotator.bundle
        if not bundle:
            raise RuntimeError("No certificate bundle available")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = self.config.min_tls_version
        ctx.load_cert_chain(
            certfile=self._write_temp(bundle.cert_pem, "srv.crt"),
            keyfile=self._write_temp(bundle.key_pem, "srv.key"),
        )
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cadata=bundle.ca_bundle_pem.decode())
        ctx.set_ciphers("TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256")
        return ctx

    def verify_peer_spiffe_id(self, peer_cert_der: bytes) -> str:
        cert = x509.load_der_x509_certificate(peer_cert_der)
        try:
            san = cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            uris = san.value.get_values_for_type(
                x509.UniformResourceIdentifier)
        except x509.ExtensionNotFound:
            raise PermissionError("No SAN extension in peer cert")
        spiffe_ids = [u for u in uris if u.startswith("spiffe://")]
        if not spiffe_ids:
            raise PermissionError("No SPIFFE ID in peer certificate")
        peer = spiffe_ids[0]
        if self.config.allowed_spiffe_ids and peer not in self.config.allowed_spiffe_ids:
            raise PermissionError(f"SPIFFE ID {peer} not in allowlist")
        if not peer.startswith(f"spiffe://{self.config.trust_domain}/"):
            raise PermissionError(f"SPIFFE ID {peer} outside trust domain")
        return peer

    def _write_temp(self, data: bytes, name: str) -> str:
        p = Path(tempfile.gettempdir()) / f"mtls-{name}"
        p.write_bytes(data)
        return str(p)
```

## Key Patterns

- **Short-lived certificates**: 12h TTL with 50% lifetime rotation threshold eliminates revocation list complexity
- **SPIFFE identity**: Every service gets a URI-based identity embedded in the certificate SAN
- **No plaintext ever**: TLS 1.3 minimum with strict cipher suite selection
- **Automated rotation**: Background task continuously monitors and renews before expiry
- **Peer validation**: Beyond TLS handshake, explicitly verify the peer SPIFFE ID against an allowlist
- **Secure cleanup**: Private keys are zeroed out before deletion'''
    ),
    (
        "security/zero-trust-opa-rego-policies",
        "Show me how to build an Open Policy Agent (OPA) policy engine for zero-trust authorization. Include Rego policies for service-to-service auth, RBAC, and API endpoint protection, plus a Python integration layer.",
        '''Open Policy Agent (OPA) is the standard for policy-as-code in zero-trust architectures. Policies are written in Rego and evaluated by OPA as a sidecar or library.

## Architecture

| Layer | Component | Policy Type |
|---|---|---|
| Network | Envoy external authz | Service identity verification |
| Application | OPA sidecar | RBAC + attribute-based access |
| Data | Row-level security | Tenant isolation |
| API | Gateway policy | Rate limiting + endpoint protection |

## Rego Policies and Python Integration

```python
#!/usr/bin/env python3
"""
OPA policy engine integration for zero-trust authorization.
Includes Rego policy definitions and async Python client.

Rego policy (deploy to OPA as policy/authz/main.rego):

    package authz
    import rego.v1

    default allow := false

    allow if {
        valid_identity
        authorized_service
        permitted_action
        not rate_limited
    }

    valid_identity if {
        spiffe_id := input.identity.spiffe_id
        startswith(spiffe_id, "spiffe://hiveai.prod/")
        not blocked_identity(spiffe_id)
    }

    blocked_identity(id) if {
        some blocked in data.blocked_identities
        blocked == id
    }

    authorized_service if {
        caller := extract_service_name(input.identity.spiffe_id)
        target := input.target.service
        some rule in data.service_auth_matrix
        rule.caller == caller
        rule.target == target
    }

    extract_service_name(spiffe_id) := name if {
        parts := split(spiffe_id, "/")
        name := parts[count(parts) - 1]
    }

    permitted_action if {
        some role in input.identity.roles
        some perm in data.rbac.role_permissions[role]
        perm.resource == input.target.resource
        perm.action == input.action
    }

    rate_limited if {
        caller := extract_service_name(input.identity.spiffe_id)
        tier := data.service_tiers[caller]
        limit := data.rate_limits[tier]
        input.request_count_last_minute > limit
    }

    reasons contains msg if {
        not valid_identity
        msg := "Invalid or missing SPIFFE identity"
    }
"""

import json
import time
import asyncio
import hashlib
import logging
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field
import aiohttp
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class PolicyDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class AuthzInput:
    """Structured input document for OPA evaluation."""
    identity: dict
    target: dict
    action: str
    context: dict = field(default_factory=dict)
    request_count_last_minute: int = 0

    def to_dict(self) -> dict:
        return {
            "identity": self.identity,
            "target": self.target,
            "action": self.action,
            "context": self.context,
            "request_count_last_minute": self.request_count_last_minute,
        }


@dataclass
class AuthzResult:
    """Result from OPA policy evaluation."""
    decision: PolicyDecision
    reasons: list[str] = field(default_factory=list)
    evaluation_time_ms: float = 0.0

    @property
    def allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW


class OPAClient:
    """Async client for OPA sidecar with caching and fail-closed semantics."""

    def __init__(
        self,
        opa_url: str = "http://localhost:8181",
        policy_path: str = "v1/data/authz",
        timeout: float = 0.5,
        cache_ttl: int = 30,
    ):
        self.opa_url = opa_url.rstrip("/")
        self.policy_path = policy_path
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, AuthzResult]] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._metrics = {"total": 0, "allowed": 0, "denied": 0, "errors": 0}

    async def start(self):
        self._session = aiohttp.ClientSession(timeout=self.timeout)

    async def stop(self):
        if self._session:
            await self._session.close()

    async def evaluate(self, authz_input: AuthzInput) -> AuthzResult:
        start = time.monotonic()
        self._metrics["total"] += 1

        cache_key = hashlib.sha256(
            json.dumps(authz_input.to_dict(), sort_keys=True).encode()
        ).hexdigest()
        cached = self._cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < self.cache_ttl:
            return cached[1]

        try:
            url = f"{self.opa_url}/{self.policy_path}"
            async with self._session.post(
                url, json={"input": authz_input.to_dict()}
            ) as resp:
                if resp.status != 200:
                    self._metrics["errors"] += 1
                    return AuthzResult(
                        decision=PolicyDecision.DENY,
                        reasons=["Policy engine unavailable -- fail closed"],
                    )
                body = await resp.json()
                result_data = body.get("result", {})
                decision = (
                    PolicyDecision.ALLOW
                    if result_data.get("allow", False)
                    else PolicyDecision.DENY
                )
                elapsed = (time.monotonic() - start) * 1000
                result = AuthzResult(
                    decision=decision,
                    reasons=result_data.get("reasons", []),
                    evaluation_time_ms=elapsed,
                )
                key = "allowed" if decision == PolicyDecision.ALLOW else "denied"
                self._metrics[key] += 1
                self._cache[cache_key] = (time.monotonic(), result)
                return result
        except asyncio.TimeoutError:
            self._metrics["errors"] += 1
            return AuthzResult(
                decision=PolicyDecision.DENY,
                reasons=["Policy evaluation timeout -- fail closed"],
            )


class ZeroTrustMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware enforcing OPA zero-trust policies on every request."""

    def __init__(self, app, opa_client: OPAClient, service_name: str):
        super().__init__(app)
        self.opa = opa_client
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next):
        peer_cert = request.scope.get("transport", {}).get("peercert")
        if not peer_cert:
            return JSONResponse({"error": "mTLS required"}, status_code=401)

        spiffe_id = self._extract_spiffe_id(peer_cert)
        roles = [r.strip() for r in request.headers.get("X-Roles", "").split(",") if r.strip()]

        authz_input = AuthzInput(
            identity={"spiffe_id": spiffe_id, "roles": roles, "attributes": {}},
            target={
                "service": self.service_name,
                "resource": request.url.path,
                "endpoint": f"{request.method} {request.url.path}",
            },
            action=self._method_to_action(request.method),
            context={
                "source_ip": request.client.host if request.client else "",
                "user_agent": request.headers.get("user-agent", ""),
            },
        )

        result = await self.opa.evaluate(authz_input)
        if not result.allowed:
            logger.warning("DENIED: %s -> %s %s (%s)",
                spiffe_id, request.method, request.url.path, result.reasons)
            return JSONResponse(
                {"error": "Forbidden", "reasons": result.reasons}, status_code=403)

        response = await call_next(request)
        response.headers["X-Policy-Eval-Ms"] = f"{result.evaluation_time_ms:.1f}"
        return response

    @staticmethod
    def _method_to_action(method: str) -> str:
        return {"GET": "read", "HEAD": "read", "POST": "write",
                "PUT": "write", "PATCH": "write", "DELETE": "delete"
                }.get(method.upper(), "read")

    @staticmethod
    def _extract_spiffe_id(peer_cert: dict) -> str:
        for san_type, san_value in peer_cert.get("subjectAltName", []):
            if san_type == "URI" and san_value.startswith("spiffe://"):
                return san_value
        raise PermissionError("No SPIFFE ID in client certificate")
```

## Key Patterns

- **Default deny**: Every Rego policy starts with `default allow := false`
- **Fail closed**: If OPA is unreachable or times out, the request is denied
- **Layered policies**: Identity verification, service auth matrix, and RBAC composed together
- **Decision caching**: Short-TTL cache prevents OPA from becoming a bottleneck
- **Structured deny reasons**: Every denial carries reasons for debugging and audit
- **Time-window restrictions**: Service calls can be restricted to specific hours'''
    ),
    (
        "security/zero-trust-network-segmentation",
        "How do I implement microsegmentation and network policies for zero-trust in Kubernetes? Show fine-grained Cilium network policies with L7 awareness and a Python policy generator from service dependency graphs.",
        '''Microsegmentation in Kubernetes means every pod-to-pod communication is explicitly allowed by policy. Cilium provides identity-based network policies that use eBPF for L7 awareness beyond simple IP-based rules.

## Network Policy Architecture

| Layer | Tool | Scope |
|---|---|---|
| L3/L4 | Kubernetes NetworkPolicy | Namespace + label selectors |
| L3-L7 | CiliumNetworkPolicy | HTTP path/method, DNS, identity |
| Cluster mesh | CiliumClusterwidePolicy | Cross-cluster segmentation |
| External | Egress gateway | Controlled internet access |

## Cilium Policy Generator

```python
#!/usr/bin/env python3
"""
Network segmentation policy manager for zero-trust Kubernetes.
Generates, validates, and applies Cilium network policies
based on a service dependency graph.
"""

import json
import yaml
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ServiceEndpoint:
    """Defines an allowed endpoint on a service."""
    port: int
    protocol: str = "TCP"
    http_rules: list[dict] = field(default_factory=list)


@dataclass
class ServiceDependency:
    """Declares that source depends on target."""
    source: str
    source_namespace: str
    target: str
    target_namespace: str
    endpoints: list[ServiceEndpoint]
    bidirectional: bool = False


@dataclass
class SegmentationConfig:
    """Full network segmentation configuration."""
    trust_domain: str
    services: dict[str, dict]
    dependencies: list[ServiceDependency]
    dns_allowed_patterns: list[str] = field(default_factory=list)
    external_egress_services: list[dict] = field(default_factory=list)


class NetworkPolicyGenerator:
    """Generates Cilium network policies from a dependency graph."""

    def __init__(self, config: SegmentationConfig):
        self.config = config

    def generate_all(self) -> list[dict]:
        """Generate default deny + per-service allow policies."""
        policies = [self._default_deny_policy()]
        ingress_map: dict[str, list] = {}
        egress_map: dict[str, list] = {}

        for dep in self.config.dependencies:
            egress_map.setdefault(dep.source, []).append(dep)
            ingress_map.setdefault(dep.target, []).append(dep)
            if dep.bidirectional:
                reverse = ServiceDependency(
                    source=dep.target, source_namespace=dep.target_namespace,
                    target=dep.source, target_namespace=dep.source_namespace,
                    endpoints=dep.endpoints)
                egress_map.setdefault(dep.target, []).append(reverse)

        all_services = set()
        for dep in self.config.dependencies:
            all_services.add((dep.source, dep.source_namespace))
            all_services.add((dep.target, dep.target_namespace))

        for svc, ns in all_services:
            policies.append(self._service_policy(
                svc, ns,
                ingress_deps=ingress_map.get(svc, []),
                egress_deps=egress_map.get(svc, [])))
        return policies

    def _default_deny_policy(self) -> dict:
        return {
            "apiVersion": "cilium.io/v2",
            "kind": "CiliumClusterwideNetworkPolicy",
            "metadata": {"name": "default-deny-all"},
            "spec": {
                "description": "Zero trust: deny all by default",
                "endpointSelector": {},
                "ingress": [{"fromEntities": ["health"]}],
                "egress": [
                    {"toEntities": ["health"]},
                    {"toEndpoints": [{"matchLabels": {
                        "k8s:io.kubernetes.pod.namespace": "kube-system",
                        "k8s:k8s-app": "kube-dns"}}],
                     "toPorts": [{"ports": [
                        {"port": "53", "protocol": "UDP"},
                        {"port": "53", "protocol": "TCP"}]}]},
                ],
            },
        }

    def _service_policy(self, svc_name, namespace, ingress_deps, egress_deps):
        labels = self.config.services.get(svc_name, {"app": svc_name})
        spec = {
            "description": f"Auto-generated policy for {svc_name}",
            "endpointSelector": {"matchLabels": labels},
        }
        if ingress_deps:
            rules = []
            for dep in ingress_deps:
                src = dict(self.config.services.get(dep.source, {"app": dep.source}))
                src["k8s:io.kubernetes.pod.namespace"] = dep.source_namespace
                rule = {"fromEndpoints": [{"matchLabels": src}]}
                if dep.endpoints:
                    rule["toPorts"] = self._build_ports(dep.endpoints)
                rules.append(rule)
            spec["ingress"] = rules
        if egress_deps:
            rules = []
            for dep in egress_deps:
                tgt = dict(self.config.services.get(dep.target, {"app": dep.target}))
                tgt["k8s:io.kubernetes.pod.namespace"] = dep.target_namespace
                rule = {"toEndpoints": [{"matchLabels": tgt}]}
                if dep.endpoints:
                    rule["toPorts"] = self._build_ports(dep.endpoints)
                rules.append(rule)
            spec["egress"] = rules

        return {
            "apiVersion": "cilium.io/v2",
            "kind": "CiliumNetworkPolicy",
            "metadata": {"name": f"{svc_name}-policy", "namespace": namespace},
            "spec": spec,
        }

    @staticmethod
    def _build_ports(endpoints: list[ServiceEndpoint]) -> list[dict]:
        result = []
        for ep in endpoints:
            entry = {"ports": [{"port": str(ep.port), "protocol": ep.protocol}]}
            if ep.http_rules:
                entry["rules"] = {"http": ep.http_rules}
            result.append(entry)
        return result

    def validate_no_cycles(self) -> list[str]:
        """Detect circular dependencies in the service graph."""
        graph: dict[str, set[str]] = {}
        for dep in self.config.dependencies:
            graph.setdefault(dep.source, set()).add(dep.target)
        issues, visited, stack = [], set(), set()

        def dfs(node, path):
            visited.add(node)
            stack.add(node)
            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path + [neighbor])
                elif neighbor in stack:
                    cycle = path[path.index(neighbor):] + [neighbor]
                    issues.append(f"Circular: {' -> '.join(cycle)}")
            stack.discard(node)

        for n in graph:
            if n not in visited:
                dfs(n, [n])
        return issues

    def write_policies(self, output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for policy in self.generate_all():
            path = output_dir / f"{policy['metadata']['name']}.yaml"
            with open(path, "w") as f:
                yaml.dump(policy, f, default_flow_style=False, sort_keys=False)
            written.append(path)
        return written

    def apply_policies(self, output_dir: Path, dry_run: bool = True):
        for path in self.write_policies(output_dir):
            cmd = ["kubectl", "apply", "-f", str(path)]
            if dry_run:
                cmd.append("--dry-run=server")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("Failed: %s: %s", path, result.stderr)
            else:
                logger.info("Applied: %s %s", path, "(dry-run)" if dry_run else "")
```

## Key Patterns

- **Default deny everywhere**: Cluster-wide deny-all is the foundation; every service needs explicit rules
- **L7 awareness**: Cilium policies specify HTTP methods and paths, not just ports
- **Identity-based over IP-based**: Policies use pod labels, not ephemeral CIDRs
- **Dependency graph driven**: Policies generated from a declarative graph, reducing errors
- **Cycle detection**: Circular dependencies flagged as security concerns
- **DNS egress control**: External DNS restricted to kube-dns, preventing tunneling'''
    ),
    (
        "security/zero-trust-spiffe-spire-identity",
        "Explain how to deploy SPIFFE/SPIRE for workload identity in a zero-trust environment. Show SPIRE configuration, workload registration, and how to consume SVIDs from Python for both HTTP and gRPC.",
        '''SPIFFE and SPIRE provide automatic, cryptographic identity to every workload without relying on network location or static secrets. Every workload gets a SPIFFE Verifiable Identity Document (SVID).

## SPIFFE/SPIRE Architecture

| Component | Role |
|---|---|
| SPIRE Server | Central authority, issues SVIDs, manages registrations |
| SPIRE Agent | Node-level daemon, attests workloads, caches SVIDs |
| Workload API | Unix domain socket for SVID delivery |
| Trust Bundle | Root certificates for trust domain federation |

## Python SVID Consumer and SPIRE Config

```python
#!/usr/bin/env python3
"""
SPIFFE Workload API client for Python services.
Consumes X.509 SVIDs from the SPIRE agent for mTLS
in both HTTP and gRPC contexts.

Deploy with SPIRE server config:
  server.conf:
    trust_domain = "hiveai.prod"
    default_x509_svid_ttl = "4h"
    default_jwt_svid_ttl = "1h"
    ca_ttl = "168h"

  Registration entry (via ClusterSPIFFEID CRD):
    spiffeIDTemplate: spiffe://hiveai.prod/service/<name>
    podSelector: {matchLabels: {app: <name>}}
    x509SVIDTTL: "4h"
"""

import ssl
import grpc
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass
from datetime import datetime, timezone

from pyspiffe.workloadapi.default_workload_api_client import DefaultWorkloadApiClient
from pyspiffe.bundle.x509_bundle.x509_bundle_set import X509BundleSet
from pyspiffe.svid.x509_svid import X509Svid
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)
SPIRE_AGENT_SOCKET = "unix:///run/spire/sockets/agent.sock"


@dataclass
class WorkloadIdentity:
    """Represents the current workload identity from SPIRE."""
    spiffe_id: str
    x509_svid: X509Svid
    trust_bundles: X509BundleSet
    cert_chain_pem: bytes
    private_key_pem: bytes
    trust_bundle_pem: bytes
    not_after: datetime

    @property
    def is_expiring_soon(self) -> bool:
        remaining = self.not_after - datetime.now(timezone.utc)
        return remaining.total_seconds() < 1800


class SpiffeIdentityManager:
    """Manages SPIFFE identity lifecycle for a workload."""

    def __init__(self, socket_path: str = SPIRE_AGENT_SOCKET,
                 expected_spiffe_id: Optional[str] = None):
        self.socket_path = socket_path
        self.expected_spiffe_id = expected_spiffe_id
        self._client: Optional[DefaultWorkloadApiClient] = None
        self._identity: Optional[WorkloadIdentity] = None
        self._watch_task: Optional[asyncio.Task] = None
        self._rotation_callbacks: list[Callable] = []

    async def start(self) -> WorkloadIdentity:
        """Connect to SPIRE agent and fetch initial SVID."""
        self._client = DefaultWorkloadApiClient(spiffe_socket=self.socket_path)
        svid = self._client.fetch_x509_svid()
        self._identity = self._process_svid(svid)

        if self.expected_spiffe_id:
            actual = str(self._identity.spiffe_id)
            if actual != self.expected_spiffe_id:
                raise RuntimeError(f"Expected {self.expected_spiffe_id}, got {actual}")

        logger.info("Identity established: %s (expires: %s)",
                     self._identity.spiffe_id,
                     self._identity.not_after.isoformat())
        self._watch_task = asyncio.create_task(self._watch_updates())
        return self._identity

    async def stop(self):
        if self._watch_task:
            self._watch_task.cancel()
        if self._client:
            self._client.close()

    def on_rotation(self, cb: Callable[[WorkloadIdentity], Awaitable[None]]):
        self._rotation_callbacks.append(cb)

    @property
    def identity(self) -> Optional[WorkloadIdentity]:
        return self._identity

    def create_ssl_context(self, server_side: bool = False) -> ssl.SSLContext:
        """Create SSL context from current SVID for HTTP mTLS."""
        if not self._identity:
            raise RuntimeError("Identity not established")
        if server_side:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        cert_f = self._write_temp(self._identity.cert_chain_pem, "cert.pem")
        key_f = self._write_temp(self._identity.private_key_pem, "key.pem")
        ctx.load_cert_chain(certfile=cert_f, keyfile=key_f)
        ca_f = self._write_temp(self._identity.trust_bundle_pem, "ca.pem")
        ctx.load_verify_locations(cafile=ca_f)
        return ctx

    def create_grpc_credentials(self) -> grpc.ChannelCredentials:
        """Create gRPC channel credentials from current SVID."""
        if not self._identity:
            raise RuntimeError("Identity not established")
        return grpc.ssl_channel_credentials(
            root_certificates=self._identity.trust_bundle_pem,
            private_key=self._identity.private_key_pem,
            certificate_chain=self._identity.cert_chain_pem)

    def create_grpc_server_credentials(self) -> grpc.ServerCredentials:
        """Create gRPC server credentials requiring client certs."""
        if not self._identity:
            raise RuntimeError("Identity not established")
        return grpc.ssl_server_credentials(
            [(self._identity.private_key_pem, self._identity.cert_chain_pem)],
            root_certificates=self._identity.trust_bundle_pem,
            require_client_auth=True)

    def _process_svid(self, svid: X509Svid) -> WorkloadIdentity:
        cert = svid.leaf
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        chain_pem = cert_pem
        for inter in svid.cert_chain[1:]:
            chain_pem += inter.public_bytes(serialization.Encoding.PEM)
        key_pem = svid.private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())
        bundles = self._client.fetch_x509_bundles()
        trust_pem = b""
        for bundle in bundles.bundles.values():
            for auth in bundle.x509_authorities:
                trust_pem += auth.public_bytes(serialization.Encoding.PEM)
        return WorkloadIdentity(
            spiffe_id=str(svid.spiffe_id), x509_svid=svid,
            trust_bundles=bundles, cert_chain_pem=chain_pem,
            private_key_pem=key_pem, trust_bundle_pem=trust_pem,
            not_after=cert.not_valid_after_utc)

    async def _watch_updates(self):
        while True:
            try:
                await asyncio.sleep(60)
                if self._identity and self._identity.is_expiring_soon:
                    svid = self._client.fetch_x509_svid()
                    self._identity = self._process_svid(svid)
                    logger.info("SVID rotated: %s (expires: %s)",
                        self._identity.spiffe_id,
                        self._identity.not_after.isoformat())
                    for cb in self._rotation_callbacks:
                        await cb(self._identity)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("SVID watch error")
                await asyncio.sleep(10)

    @staticmethod
    def _write_temp(data: bytes, name: str) -> str:
        p = Path(tempfile.mkdtemp()) / name
        p.write_bytes(data)
        return str(p)
```

## Key Patterns

- **Workload attestation**: SPIRE verifies identity via Kubernetes API (pod labels, SA, namespace) -- no static secrets
- **Short-lived SVIDs**: 4h X.509, 30min JWT TTLs minimize blast radius of compromise
- **Automatic rotation**: SPIRE agent pushes new SVIDs; app watches and updates SSL contexts
- **Trust domain federation**: Multiple clusters federate trust bundles for cross-domain mTLS
- **Expected identity validation**: Apps assert their own SPIFFE ID at startup to detect misconfiguration
- **Multi-protocol support**: Same SVID produces contexts for HTTP, gRPC client, and gRPC server'''
    ),
    (
        "security/zero-trust-identity-aware-proxy",
        "How do I build an identity-aware proxy (IAP) for zero-trust access to internal services? Show OIDC authentication, encrypted sessions in Redis, context-aware policy enforcement, and structured audit logging.",
        '''An identity-aware proxy sits in front of internal services and enforces authentication at the network edge, replacing VPN-based access with per-request identity verification (the BeyondCorp model).

## IAP Architecture

| Component | Function |
|---|---|
| Identity Provider | OAuth2/OIDC (Okta, Azure AD, Google) |
| IAP Proxy | Reverse proxy with auth enforcement |
| Policy Engine | OPA for fine-grained access decisions |
| Session Store | Redis for encrypted session tokens |
| Audit Logger | Every access attempt logged |

## Identity-Aware Proxy Implementation

```python
#!/usr/bin/env python3
"""
Identity-Aware Proxy for zero-trust access to internal services.
BeyondCorp-style per-request authentication and authorization.
"""

import json
import time
import secrets
import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
import httpx
import redis.asyncio as aioredis
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse

logger = logging.getLogger(__name__)


@dataclass
class IAPConfig:
    oidc_issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    session_ttl: int = 3600
    session_cookie_name: str = "__iap_session"
    session_encryption_key: str = ""
    service_routes: dict[str, str] = field(default_factory=dict)
    opa_url: str = "http://opa.internal:8181"
    allowed_email_domains: list[str] = field(default_factory=list)
    mfa_required: bool = True


@dataclass
class UserContext:
    sub: str
    email: str
    name: str
    groups: list[str]
    mfa_verified: bool
    device_id: Optional[str]
    device_trust_level: str
    session_start: datetime
    source_ip: str
    user_agent: str

    def to_headers(self) -> dict[str, str]:
        return {
            "X-IAP-User-Email": self.email,
            "X-IAP-User-Id": self.sub,
            "X-IAP-User-Name": self.name,
            "X-IAP-User-Groups": ",".join(self.groups),
            "X-IAP-MFA-Verified": str(self.mfa_verified).lower(),
            "X-IAP-Device-Trust": self.device_trust_level,
            "X-IAP-Session-Start": self.session_start.isoformat(),
        }


class SessionStore:
    """Encrypted session storage backed by Redis."""

    def __init__(self, redis_client: aioredis.Redis, encryption_key: str):
        self.redis = redis_client
        self.fernet = Fernet(encryption_key.encode())

    async def create(self, user_ctx: UserContext, ttl: int) -> str:
        session_id = secrets.token_urlsafe(32)
        data = json.dumps({
            "sub": user_ctx.sub, "email": user_ctx.email,
            "name": user_ctx.name, "groups": user_ctx.groups,
            "mfa_verified": user_ctx.mfa_verified,
            "device_id": user_ctx.device_id,
            "device_trust_level": user_ctx.device_trust_level,
            "session_start": user_ctx.session_start.isoformat(),
            "source_ip": user_ctx.source_ip,
            "user_agent": user_ctx.user_agent,
        })
        encrypted = self.fernet.encrypt(data.encode())
        await self.redis.setex(f"iap:session:{session_id}", ttl, encrypted)
        return session_id

    async def get(self, session_id: str) -> Optional[UserContext]:
        encrypted = await self.redis.get(f"iap:session:{session_id}")
        if not encrypted:
            return None
        try:
            data = json.loads(self.fernet.decrypt(encrypted))
            return UserContext(
                sub=data["sub"], email=data["email"], name=data["name"],
                groups=data["groups"], mfa_verified=data["mfa_verified"],
                device_id=data.get("device_id"),
                device_trust_level=data.get("device_trust_level", "unknown"),
                session_start=datetime.fromisoformat(data["session_start"]),
                source_ip=data["source_ip"], user_agent=data["user_agent"])
        except Exception:
            await self.redis.delete(f"iap:session:{session_id}")
            return None

    async def revoke(self, session_id: str):
        await self.redis.delete(f"iap:session:{session_id}")


class OIDCAuthenticator:
    def __init__(self, config: IAPConfig):
        self.config = config
        self._oidc_config: Optional[dict] = None
        self._jwks_client: Optional[jwt.PyJWKClient] = None

    async def initialize(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.config.oidc_issuer}/.well-known/openid-configuration")
            self._oidc_config = resp.json()
        self._jwks_client = jwt.PyJWKClient(self._oidc_config["jwks_uri"])

    def get_auth_url(self, state: str, nonce: str) -> str:
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "scope": "openid email profile groups",
            "redirect_uri": self.config.redirect_uri,
            "state": state, "nonce": nonce, "prompt": "consent",
        }
        if self.config.mfa_required:
            params["acr_values"] = "urn:mfa"
        return f"{self._oidc_config['authorization_endpoint']}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self._oidc_config["token_endpoint"], data={
                "grant_type": "authorization_code", "code": code,
                "redirect_uri": self.config.redirect_uri,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret})
            resp.raise_for_status()
            return resp.json()

    def validate_id_token(self, id_token: str, nonce: str) -> dict:
        key = self._jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(id_token, key.key,
            algorithms=["RS256", "ES256"],
            audience=self.config.client_id,
            issuer=self.config.oidc_issuer,
            options={"require": ["exp", "iat", "nonce", "sub", "email"]})
        if claims.get("nonce") != nonce:
            raise ValueError("Nonce mismatch")
        if self.config.allowed_email_domains:
            domain = claims["email"].split("@")[-1]
            if domain not in self.config.allowed_email_domains:
                raise PermissionError(f"Domain {domain} not allowed")
        return claims


class AuditLogger:
    """Structured audit logging for all proxy access decisions."""

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def log_access(self, user_ctx: Optional[UserContext],
                         request: Request, decision: str,
                         reason: str = "", backend: str = ""):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "iap_access",
            "user_email": user_ctx.email if user_ctx else "anonymous",
            "source_ip": request.client.host if request.client else "",
            "method": request.method,
            "path": str(request.url.path),
            "decision": decision, "reason": reason,
            "backend": backend,
            "mfa_verified": str(user_ctx.mfa_verified) if user_ctx else "false",
        }
        await self.redis.xadd("iap:audit:stream", entry, maxlen=1_000_000)
        logger.info("IAP %s: %s %s -> %s (%s)",
            decision, entry["user_email"],
            f"{request.method} {request.url.path}", backend, reason)
```

## Key Patterns

- **Every request authenticated**: No VPN trust -- each request carries verified identity
- **Encrypted sessions**: Fernet-encrypted in Redis, not in browser cookies
- **Context-aware access**: Device trust, MFA status, source IP all factor into decisions
- **Downstream propagation**: Authenticated context injected as signed headers for backends
- **Structured audit trail**: Every access attempt logged to Redis stream for compliance
- **CSRF protection**: OIDC state parameter prevents cross-site request forgery'''
    ),
    (
        "security/zero-trust-continuous-verification",
        "How do I implement continuous verification in a zero-trust architecture? Show real-time risk scoring, behavioral anomaly detection, and dynamic access tier adjustment during active sessions.",
        '''Continuous verification means trust is never assumed and is re-evaluated throughout a session. Instead of binary allow/deny at login, access is dynamically adjusted based on ongoing behavioral signals.

## Continuous Verification Architecture

| Component | Purpose |
|---|---|
| Risk Engine | Real-time risk score calculation |
| Behavioral Analyzer | Detects anomalous patterns |
| Device Posture Checker | Validates endpoint compliance |
| Step-Up Auth Trigger | Forces re-auth on risk increase |
| Session Degrader | Reduces permissions without full logout |

## Risk-Based Continuous Verification Engine

```python
#!/usr/bin/env python3
"""
Continuous verification engine for zero-trust architecture.
Re-evaluates trust in real-time based on behavioral signals,
device posture, and contextual risk factors.
"""

import time
import asyncio
import logging
from enum import Enum
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from collections import deque
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AccessTier(Enum):
    FULL = "full"
    STANDARD = "standard"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"


RISK_ACCESS_MAP = {
    RiskLevel.LOW: AccessTier.FULL,
    RiskLevel.MEDIUM: AccessTier.STANDARD,
    RiskLevel.HIGH: AccessTier.RESTRICTED,
    RiskLevel.CRITICAL: AccessTier.BLOCKED,
}


@dataclass
class DevicePosture:
    """Current device security posture."""
    device_id: str
    os_version: str
    patch_level: str
    disk_encrypted: bool
    firewall_enabled: bool
    antivirus_active: bool
    screen_lock_enabled: bool
    jailbroken: bool
    last_check: datetime
    mdm_compliant: bool

    @property
    def posture_score(self) -> float:
        """0.0 = worst, 1.0 = best."""
        score = 0.0
        checks = [
            (self.disk_encrypted, 0.2),
            (self.firewall_enabled, 0.15),
            (self.antivirus_active, 0.15),
            (self.screen_lock_enabled, 0.1),
            (not self.jailbroken, 0.2),
            (self.mdm_compliant, 0.2),
        ]
        for passed, weight in checks:
            if passed:
                score += weight
        staleness = (datetime.now(timezone.utc) - self.last_check).total_seconds()
        if staleness > 3600:
            score *= max(0.5, 1.0 - (staleness - 3600) / 86400)
        return round(score, 3)


@dataclass
class BehavioralSignals:
    """Behavioral signals for anomaly detection."""
    request_timestamps: deque = field(default_factory=lambda: deque(maxlen=1000))
    endpoints_accessed: deque = field(default_factory=lambda: deque(maxlen=500))
    source_ips: set = field(default_factory=set)
    geolocations: list = field(default_factory=list)
    failed_auth_attempts: int = 0
    unusual_hour_requests: int = 0

    def record_request(self, endpoint: str, source_ip: str, geo: str):
        self.request_timestamps.append(time.monotonic())
        self.endpoints_accessed.append(endpoint)
        self.source_ips.add(source_ip)
        if geo and (not self.geolocations or self.geolocations[-1] != geo):
            self.geolocations.append(geo)
        hour = datetime.now(timezone.utc).hour
        if hour < 6 or hour > 22:
            self.unusual_hour_requests += 1

    @property
    def requests_per_minute(self) -> float:
        if len(self.request_timestamps) < 2:
            return 0.0
        now = time.monotonic()
        return len([t for t in self.request_timestamps if now - t < 60])

    @property
    def impossible_travel(self) -> bool:
        if len(self.geolocations) < 2:
            return False
        return len(set(self.geolocations[-5:])) > 2

    @property
    def ip_diversity_score(self) -> float:
        return min(1.0, max(0, len(self.source_ips) - 1) / 4.0)


@dataclass
class SessionRiskContext:
    session_id: str
    user_id: str
    device: DevicePosture
    behavior: BehavioralSignals
    current_risk: RiskLevel = RiskLevel.LOW
    current_access: AccessTier = AccessTier.FULL
    risk_score: float = 0.0
    last_evaluation: Optional[datetime] = None
    step_up_completed: bool = False
    eval_count: int = 0


class ContinuousVerificationEngine:
    """Real-time risk evaluation and access tier management."""

    def __init__(self, redis_client: aioredis.Redis,
                 eval_interval: float = 30.0,
                 threshold_medium: float = 0.3,
                 threshold_high: float = 0.6,
                 threshold_critical: float = 0.85):
        self.redis = redis_client
        self.eval_interval = eval_interval
        self.thresholds = {
            RiskLevel.MEDIUM: threshold_medium,
            RiskLevel.HIGH: threshold_high,
            RiskLevel.CRITICAL: threshold_critical,
        }
        self._sessions: dict[str, SessionRiskContext] = {}
        self._callbacks: dict[str, list[Callable]] = {
            "risk_change": [], "access_degraded": [],
            "session_blocked": [], "step_up_required": [],
        }
        self._eval_task: Optional[asyncio.Task] = None

    def on(self, event: str, callback: Callable):
        self._callbacks.setdefault(event, []).append(callback)

    async def start(self):
        self._eval_task = asyncio.create_task(self._evaluation_loop())
        logger.info("Continuous verification engine started (interval=%ss)",
                     self.eval_interval)

    async def stop(self):
        if self._eval_task:
            self._eval_task.cancel()

    def register_session(self, ctx: SessionRiskContext):
        self._sessions[ctx.session_id] = ctx

    def record_request(self, session_id: str, endpoint: str,
                       source_ip: str, geo: str = "") -> AccessTier:
        ctx = self._sessions.get(session_id)
        if not ctx:
            return AccessTier.BLOCKED
        ctx.behavior.record_request(endpoint, source_ip, geo)
        return ctx.current_access

    async def evaluate_session(self, session_id: str) -> SessionRiskContext:
        ctx = self._sessions[session_id]
        old_risk, old_access = ctx.current_risk, ctx.current_access

        components = {
            "device_posture": (1.0 - ctx.device.posture_score) * 0.25,
            "request_rate": min(1.0, ctx.behavior.requests_per_minute / 100) * 0.15,
            "impossible_travel": (1.0 if ctx.behavior.impossible_travel else 0.0) * 0.25,
            "ip_diversity": ctx.behavior.ip_diversity_score * 0.15,
            "failed_auth": min(1.0, ctx.behavior.failed_auth_attempts / 5) * 0.1,
            "unusual_hours": min(1.0, ctx.behavior.unusual_hour_requests / 10) * 0.1,
        }
        ctx.risk_score = round(min(1.0, max(0.0, sum(components.values()))), 4)

        if ctx.risk_score >= self.thresholds[RiskLevel.CRITICAL]:
            ctx.current_risk = RiskLevel.CRITICAL
        elif ctx.risk_score >= self.thresholds[RiskLevel.HIGH]:
            ctx.current_risk = RiskLevel.HIGH
        elif ctx.risk_score >= self.thresholds[RiskLevel.MEDIUM]:
            ctx.current_risk = RiskLevel.MEDIUM
        else:
            ctx.current_risk = RiskLevel.LOW

        ctx.current_access = RISK_ACCESS_MAP[ctx.current_risk]

        # Step-up auth can recover one tier
        if ctx.step_up_completed and ctx.current_access != AccessTier.BLOCKED:
            tiers = list(AccessTier)
            idx = tiers.index(ctx.current_access)
            if idx > 0:
                ctx.current_access = tiers[idx - 1]

        ctx.last_evaluation = datetime.now(timezone.utc)
        ctx.eval_count += 1

        await self.redis.hset(f"cv:session:{session_id}", mapping={
            "risk_score": str(ctx.risk_score),
            "risk_level": ctx.current_risk.value,
            "access_tier": ctx.current_access.value,
        })
        await self.redis.expire(f"cv:session:{session_id}", 7200)

        # Fire callbacks
        if ctx.current_risk != old_risk:
            for cb in self._callbacks.get("risk_change", []):
                await cb(ctx, old_risk, ctx.current_risk, components)
        if ctx.current_access == AccessTier.BLOCKED:
            for cb in self._callbacks.get("session_blocked", []):
                await cb(ctx)
        if (ctx.current_risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)
                and not ctx.step_up_completed):
            for cb in self._callbacks.get("step_up_required", []):
                await cb(ctx)
        return ctx

    async def _evaluation_loop(self):
        while True:
            try:
                await asyncio.sleep(self.eval_interval)
                for sid in list(self._sessions):
                    try:
                        await self.evaluate_session(sid)
                    except Exception:
                        logger.exception("Eval failed for %s", sid)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Evaluation loop error")
                await asyncio.sleep(5)
```

## Key Patterns

- **Never trust, always verify**: Every 30s all sessions are re-evaluated against current signals
- **Graceful degradation**: Access degrades through tiers (full -> standard -> restricted -> blocked)
- **Composite risk scoring**: Device posture, behavior, geography, and auth failures weighted together
- **Step-up authentication**: Users complete additional MFA to recover one access tier
- **Impossible travel detection**: Rapid geolocation changes flag credential compromise
- **Cross-instance state**: Risk scores persisted in Redis for consistency across proxy instances'''
    ),
]
