PAIRS = [
    (
        "networking/load-balancing-algorithms",
        r"""Explain load balancing algorithms including round-robin, weighted round-robin, least connections, consistent hashing, IP hash, and least response time. Compare L4 vs L7 load balancing, health checking, and sticky sessions.""",
        r"""## Load Balancing Algorithms: From Round-Robin to Consistent Hashing

Load balancers distribute traffic across multiple backend servers. The algorithm choice determines fairness, performance, and behavior under failure.

### Algorithm Implementations

```python
import random
import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Backend:
    host: str
    port: int
    weight: int = 1
    healthy: bool = True
    active_connections: int = 0
    avg_response_ms: float = 0
    total_requests: int = 0


class RoundRobinBalancer:
    """Simple round-robin: equal distribution regardless of server capacity."""
    def __init__(self, backends: list[Backend]):
        self.backends = backends
        self._index = 0

    def next(self) -> Optional[Backend]:
        healthy = [b for b in self.backends if b.healthy]
        if not healthy:
            return None
        backend = healthy[self._index % len(healthy)]
        self._index += 1
        return backend


class WeightedRoundRobinBalancer:
    """Weighted round-robin: distribute proportionally to weight."""
    def __init__(self, backends: list[Backend]):
        self.backends = backends
        self._current_weights = [0] * len(backends)

    def next(self) -> Optional[Backend]:
        healthy = [(i, b) for i, b in enumerate(self.backends) if b.healthy]
        if not healthy:
            return None

        total = sum(b.weight for _, b in healthy)

        # Smooth weighted round-robin (Nginx algorithm)
        best_idx = -1
        best_weight = -1

        for i, backend in healthy:
            self._current_weights[i] += backend.weight
            if self._current_weights[i] > best_weight:
                best_weight = self._current_weights[i]
                best_idx = i

        self._current_weights[best_idx] -= total
        return self.backends[best_idx]


class LeastConnectionsBalancer:
    """Route to the server with fewest active connections."""
    def __init__(self, backends: list[Backend]):
        self.backends = backends

    def next(self) -> Optional[Backend]:
        healthy = [b for b in self.backends if b.healthy]
        if not healthy:
            return None

        # Weight-adjusted: connections / weight
        return min(
            healthy,
            key=lambda b: b.active_connections / max(b.weight, 1)
        )


class IPHashBalancer:
    """Route based on client IP — same client always hits same server."""
    def __init__(self, backends: list[Backend]):
        self.backends = backends

    def next(self, client_ip: str) -> Optional[Backend]:
        healthy = [b for b in self.backends if b.healthy]
        if not healthy:
            return None

        h = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        return healthy[h % len(healthy)]


class LeastResponseTimeBalancer:
    """Route to server with fastest recent response times."""
    def __init__(self, backends: list[Backend]):
        self.backends = backends

    def next(self) -> Optional[Backend]:
        healthy = [b for b in self.backends if b.healthy]
        if not healthy:
            return None

        # Combine response time and connection count
        return min(
            healthy,
            key=lambda b: b.avg_response_ms * (b.active_connections + 1)
        )

    def record_response(self, backend: Backend, response_ms: float):
        """EWMA of response times."""
        alpha = 0.3  # Smoothing factor
        backend.avg_response_ms = (
            alpha * response_ms + (1 - alpha) * backend.avg_response_ms
        )
```

### L4 vs L7 Load Balancing

```python
# L4 (Transport Layer): works with TCP/UDP packets
# - Decisions based on: IP address, port number
# - Cannot inspect HTTP headers, URLs, cookies
# - Very fast: no payload inspection
# - Use for: TCP services, databases, non-HTTP protocols
# Examples: AWS NLB, HAProxy (TCP mode), Linux IPVS

# L7 (Application Layer): works with HTTP requests
# - Decisions based on: URL path, headers, cookies, request body
# - Can do: URL-based routing, header injection, SSL termination
# - Slower: must parse HTTP
# - Use for: web applications, API gateways, microservices
# Examples: AWS ALB, Nginx, HAProxy (HTTP mode), Envoy


class L7Router:
    """L7 load balancer with path-based routing."""

    def __init__(self):
        self.routes: list[tuple[str, list[Backend]]] = []
        self.default_backends: list[Backend] = []

    def add_route(self, path_prefix: str, backends: list[Backend]):
        self.routes.append((path_prefix, backends))

    def route(self, request_path: str, headers: dict) -> Optional[Backend]:
        """Route based on URL path and headers."""
        # Path-based routing
        for prefix, backends in self.routes:
            if request_path.startswith(prefix):
                healthy = [b for b in backends if b.healthy]
                if healthy:
                    # Sticky sessions via cookie
                    session_cookie = headers.get("cookie", "")
                    if "srv_id=" in session_cookie:
                        srv_id = session_cookie.split("srv_id=")[1].split(";")[0]
                        for b in healthy:
                            if f"{b.host}:{b.port}" == srv_id:
                                return b

                    return min(healthy, key=lambda b: b.active_connections)

        # Default backends
        healthy = [b for b in self.default_backends if b.healthy]
        return healthy[0] if healthy else None
```

### Health Checking

```python
import asyncio
import aiohttp


class HealthChecker:
    """Active health checking for backend servers."""

    def __init__(
        self,
        backends: list[Backend],
        check_interval: float = 5.0,
        check_path: str = "/health",
        timeout: float = 2.0,
        unhealthy_threshold: int = 3,
        healthy_threshold: int = 2,
    ):
        self.backends = backends
        self.check_interval = check_interval
        self.check_path = check_path
        self.timeout = timeout
        self.unhealthy_threshold = unhealthy_threshold
        self.healthy_threshold = healthy_threshold
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._success_counts: dict[str, int] = defaultdict(int)

    async def start(self):
        while True:
            await asyncio.gather(*[
                self._check_backend(b) for b in self.backends
            ])
            await asyncio.sleep(self.check_interval)

    async def _check_backend(self, backend: Backend):
        key = f"{backend.host}:{backend.port}"
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{backend.host}:{backend.port}{self.check_path}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status == 200:
                        self._failure_counts[key] = 0
                        self._success_counts[key] += 1
                        if (not backend.healthy and
                                self._success_counts[key] >= self.healthy_threshold):
                            backend.healthy = True
                            print(f"Backend {key} is now HEALTHY")
                    else:
                        raise Exception(f"Status {resp.status}")
        except Exception:
            self._success_counts[key] = 0
            self._failure_counts[key] += 1
            if (backend.healthy and
                    self._failure_counts[key] >= self.unhealthy_threshold):
                backend.healthy = False
                print(f"Backend {key} is now UNHEALTHY")
```

**Load balancing selection guide**: (1) **Round-robin** for homogeneous servers with similar capacity, (2) **Weighted round-robin** when servers have different capacities, (3) **Least connections** for varying request durations (long-lived connections), (4) **IP hash** when you need session affinity without cookies, (5) **L4** for raw throughput and non-HTTP protocols, **L7** for HTTP routing and content-based decisions."""
    ),
    (
        "networking/http2-http3-protocols",
        r"""Explain HTTP/2 and HTTP/3 protocols including multiplexing, server push, header compression (HPACK/QPACK), stream prioritization, HTTP/3's use of QUIC over UDP, 0-RTT connection establishment, and migration considerations.""",
        r"""## HTTP/2 and HTTP/3: Multiplexing, QUIC, and Protocol Evolution

HTTP/2 and HTTP/3 solve fundamental performance limitations of HTTP/1.1. Understanding their differences helps you optimize web application performance.

### HTTP/1.1 Limitations

```
HTTP/1.1 problems:
1. Head-of-line blocking: one slow response blocks all others on the connection
2. No multiplexing: one request per TCP connection at a time
3. Redundant headers: same headers sent with every request (~500-800 bytes)
4. No server push: server can't proactively send resources

Workarounds (all add complexity):
- Connection pooling (6-8 connections per domain)
- Domain sharding (cdn1.example.com, cdn2.example.com)
- Sprite sheets, CSS/JS bundling
- Cookie-free domains for static assets
```

### HTTP/2: Binary Multiplexing

```python
# HTTP/2 key concepts:

# 1. BINARY FRAMING: requests/responses are split into binary frames
# Frame: [Length(3) | Type(1) | Flags(1) | StreamID(4) | Payload]
# Types: DATA, HEADERS, PRIORITY, RST_STREAM, SETTINGS, PUSH_PROMISE, etc.

# 2. STREAMS: multiple concurrent request/response exchanges on ONE connection
# Each stream has a unique ID (odd = client-initiated, even = server-initiated)

# 3. MULTIPLEXING: frames from different streams interleave freely
# Connection:  [H:1][D:3][H:5][D:1][D:3][D:5][D:1]...
# (Headers for stream 1, Data for stream 3, Headers for stream 5, etc.)

# 4. HPACK header compression: maintain a dynamic table of headers
# First request: ":method: GET", ":path: /api/users" → 50 bytes
# Second request: same headers → 2 bytes (just table indices!)

# Python example: making HTTP/2 requests
import httpx

async def http2_requests():
    """HTTP/2 multiplexes all requests on a single TCP connection."""
    async with httpx.AsyncClient(http2=True) as client:
        # These all share one TCP connection with multiplexed streams
        responses = await asyncio.gather(
            client.get("https://api.example.com/users"),
            client.get("https://api.example.com/products"),
            client.get("https://api.example.com/orders"),
        )
        return [r.json() for r in responses]
        # HTTP/1.1 would need 3 separate connections
        # HTTP/2 uses 1 connection with 3 interleaved streams
```

### HTTP/3: QUIC over UDP

```
HTTP/3 improvements over HTTP/2:

1. NO TCP HEAD-OF-LINE BLOCKING
   HTTP/2 problem: one lost TCP packet blocks ALL streams (TCP is ordered)
   HTTP/3 solution: QUIC provides per-stream ordering over UDP
   Lost packet on stream 3? Only stream 3 waits, others continue.

2. FASTER CONNECTION ESTABLISHMENT
   TCP + TLS 1.3: 2 round trips (TCP handshake + TLS handshake)
   QUIC: 1 round trip (handshake + crypto in parallel)
   QUIC 0-RTT: 0 round trips for repeat connections!

3. CONNECTION MIGRATION
   TCP: connection dies when IP changes (WiFi → cellular)
   QUIC: connection ID survives network changes

4. BUILT-IN ENCRYPTION
   QUIC mandates TLS 1.3 — no unencrypted HTTP/3 exists

Connection establishment comparison:
┌──────────────────────────────────────────────┐
│ HTTP/1.1 + TLS 1.2:  3 RTT before first byte │
│   RTT 1: TCP SYN/ACK                         │
│   RTT 2: TLS ClientHello/ServerHello         │
│   RTT 3: TLS Finished + HTTP Request         │
│                                                │
│ HTTP/2 + TLS 1.3:    2 RTT before first byte  │
│   RTT 1: TCP SYN/ACK                         │
│   RTT 2: TLS 1.3 (1-RTT) + HTTP/2 Request   │
│                                                │
│ HTTP/3 (QUIC):       1 RTT before first byte   │
│   RTT 1: QUIC handshake (crypto + connection)  │
│                                                │
│ HTTP/3 (0-RTT):      0 RTT before first byte   │
│   Send request with initial QUIC packet!       │
│   (Resumed connections with cached credentials)│
└──────────────────────────────────────────────┘
```

### Server Configuration

```nginx
# Nginx HTTP/2 configuration
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;

    ssl_certificate /etc/ssl/certs/example.com.pem;
    ssl_certificate_key /etc/ssl/private/example.com.key;

    # HTTP/2 tuning
    http2_max_concurrent_streams 128;
    http2_max_field_size 8k;
    http2_max_header_size 32k;

    # Enable server push
    location /app {
        http2_push /static/app.css;
        http2_push /static/app.js;
        proxy_pass http://backend;
    }
}

# Nginx HTTP/3 configuration (1.25+)
server {
    listen 443 ssl;
    listen 443 quic reuseport;
    listen [::]:443 ssl;
    listen [::]:443 quic reuseport;

    http2 on;
    http3 on;

    ssl_certificate /etc/ssl/certs/example.com.pem;
    ssl_certificate_key /etc/ssl/private/example.com.key;

    # Advertise HTTP/3 support
    add_header Alt-Svc 'h3=":443"; ma=86400';

    ssl_protocols TLSv1.3;  # Required for HTTP/3
}
```

### Migration Considerations

```python
# Server-side checklist for HTTP/2 adoption:
# ✓ TLS is required (HTTP/2 is effectively HTTPS-only)
# ✓ Remove domain sharding (one connection is better)
# ✓ Stop bundling/concatenating — multiplexing eliminates the need
# ✓ Use server push for critical CSS/JS (or preload hints)
# ✓ Test with HTTP/2-aware load testing tools

# HTTP/3 adoption checklist:
# ✓ Ensure UDP 443 is not blocked by firewalls
# ✓ Add Alt-Svc header to advertise HTTP/3 support
# ✓ Keep HTTP/2 as fallback (not all clients support HTTP/3)
# ✓ Monitor QUIC performance — some networks throttle UDP
# ✓ Test connection migration (mobile users switching networks)

# Feature detection in applications
async def check_protocol(url: str) -> str:
    async with httpx.AsyncClient(http2=True) as client:
        response = await client.get(url)
        return response.http_version  # "HTTP/1.1", "HTTP/2", or "HTTP/3"
```

**Protocol selection**: (1) HTTP/2 is a no-brainer upgrade — enable it on all HTTPS servers, (2) HTTP/3 provides the most benefit on high-latency or lossy networks (mobile, satellite), (3) Remove HTTP/1.1 performance hacks (domain sharding, bundling) when moving to HTTP/2, (4) Always keep HTTP/2 fallback when enabling HTTP/3 — UDP is sometimes blocked, (5) 0-RTT in HTTP/3 is transformative for mobile UX — connections survive network switches."""
    ),
    (
        "networking/dns-internals",
        r"""Explain DNS internals including the resolution process, record types (A, AAAA, CNAME, MX, TXT, SRV, NS, SOA), DNS caching and TTL, DNSSEC, common DNS patterns for service discovery, and debugging with dig/nslookup.""",
        r"""## DNS Internals: Resolution, Record Types, and Service Discovery

DNS is the internet's phone book — translating human-readable names to IP addresses. Understanding DNS deeply helps with debugging connectivity, configuring services, and designing distributed systems.

### The Resolution Process

```
User types: www.example.com

1. Browser cache → OS cache → Router cache (check local caches first)

2. Recursive resolver (ISP or 8.8.8.8):
   "I'll find the answer for you"

3. Root nameserver (.)
   "I don't know example.com, but .com is handled by these servers"
   Returns: NS records for .com TLD servers

4. TLD nameserver (.com)
   "I don't know www.example.com, but example.com is handled by these servers"
   Returns: NS records for example.com authoritative servers

5. Authoritative nameserver (ns1.example.com)
   "www.example.com is at 93.184.216.34"
   Returns: A record with IP address

6. Recursive resolver caches the result (for TTL duration)
   Returns answer to client
```

### Record Types

```bash
# A record: name → IPv4 address
example.com.  A  93.184.216.34

# AAAA record: name → IPv6 address
example.com.  AAAA  2606:2800:220:1:248:1893:25c8:1946

# CNAME record: alias → canonical name
www.example.com.  CNAME  example.com.
# CNAME creates an alias; the resolver follows the chain
# IMPORTANT: CNAME cannot coexist with other records at same name

# MX record: mail routing (with priority)
example.com.  MX  10 mail1.example.com.
example.com.  MX  20 mail2.example.com.
# Lower priority number = preferred server

# TXT record: arbitrary text (verification, SPF, DKIM)
example.com.  TXT  "v=spf1 include:_spf.google.com ~all"
example.com.  TXT  "google-site-verification=abc123"

# SRV record: service discovery
_http._tcp.example.com.  SRV  10 60 80 web1.example.com.
# Format: priority weight port target
# Used for: SIP, XMPP, LDAP, and custom service discovery

# NS record: delegate authority to nameservers
example.com.  NS  ns1.example.com.
example.com.  NS  ns2.example.com.

# SOA record: zone authority information
example.com.  SOA  ns1.example.com. admin.example.com. (
    2024030101  ; Serial number
    3600        ; Refresh interval
    900         ; Retry interval
    604800      ; Expire time
    86400       ; Minimum TTL
)

# CAA record: which CAs can issue certificates
example.com.  CAA  0 issue "letsencrypt.org"
```

### Debugging DNS

```bash
# dig — the gold standard DNS debugging tool
dig example.com A                    # Query A record
dig example.com AAAA                 # Query IPv6
dig example.com MX                   # Query mail servers
dig example.com ANY                  # Query all records
dig @8.8.8.8 example.com            # Use specific resolver
dig +trace example.com               # Show full resolution chain
dig +short example.com               # Just the answer
dig +norecurse @a.root-servers.net . NS  # Query root directly

# Reverse DNS lookup
dig -x 93.184.216.34

# Check all nameservers for consistency
dig example.com NS +short | while read ns; do
    echo "=== $ns ==="
    dig @$ns example.com A +short
done

# nslookup (simpler but less powerful)
nslookup example.com
nslookup -type=MX example.com

# Check DNS propagation
# After changing a record, query multiple resolvers:
for resolver in 8.8.8.8 1.1.1.1 9.9.9.9; do
    echo "=== $resolver ==="
    dig @$resolver example.com A +short
done
```

### DNS Patterns for Service Discovery

```python
import dns.resolver


class DNSServiceDiscovery:
    """Service discovery using DNS SRV records."""

    def __init__(self, domain: str):
        self.domain = domain

    def discover(self, service: str, protocol: str = "tcp") -> list[dict]:
        """Discover service instances via SRV records."""
        name = f"_{service}._{protocol}.{self.domain}"
        try:
            answers = dns.resolver.resolve(name, "SRV")
            instances = [
                {
                    "host": str(rdata.target).rstrip("."),
                    "port": rdata.port,
                    "priority": rdata.priority,
                    "weight": rdata.weight,
                }
                for rdata in answers
            ]
            # Sort by priority, then weighted random within priority
            instances.sort(key=lambda x: x["priority"])
            return instances
        except dns.resolver.NXDOMAIN:
            return []

    def get_config(self, key: str) -> str:
        """Read configuration from TXT records."""
        name = f"{key}.config.{self.domain}"
        try:
            answers = dns.resolver.resolve(name, "TXT")
            return str(answers[0]).strip('"')
        except dns.resolver.NXDOMAIN:
            return ""


# Usage:
discovery = DNSServiceDiscovery("internal.example.com")

# Find all API server instances
api_servers = discovery.discover("api", "tcp")
# Returns: [{"host": "api1.internal.example.com", "port": 8080, ...}, ...]

# DNS records:
# _api._tcp.internal.example.com. SRV 10 50 8080 api1.internal.example.com.
# _api._tcp.internal.example.com. SRV 10 50 8080 api2.internal.example.com.
# _api._tcp.internal.example.com. SRV 20 100 8080 api3.internal.example.com.
```

### DNS Caching and TTL

```python
# TTL (Time To Live) controls how long resolvers cache records

# Short TTL (60s):
# ✓ Fast failover (change takes effect in 1 minute)
# ✗ More DNS queries, higher latency
# Use for: load-balanced services, blue-green deployments

# Long TTL (3600s+):
# ✓ Fewer DNS queries, lower latency
# ✗ Slow failover (old IP cached for up to 1 hour)
# Use for: stable services, CDN endpoints

# Migration strategy: lower TTL before a migration
# Normal:    example.com.  3600  A  1.2.3.4
# Pre-migration: lower to 60s, wait for old TTL to expire
# Migration: change to new IP
# Post-migration: raise TTL back to 3600s

# Application-level DNS caching
import socket
from functools import lru_cache
import time


class DNSCache:
    """Application-level DNS cache with TTL."""

    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._cache: dict[str, tuple[str, float]] = {}

    def resolve(self, hostname: str) -> str:
        now = time.time()
        if hostname in self._cache:
            ip, expiry = self._cache[hostname]
            if now < expiry:
                return ip

        ip = socket.gethostbyname(hostname)
        self._cache[hostname] = (ip, now + self.ttl)
        return ip
```

**DNS best practices**: (1) Use short TTLs (60-300s) for services that need fast failover, (2) Lower TTLs BEFORE a migration, wait for old TTL to expire, then make the change, (3) Use SRV records for internal service discovery — they include port and priority, (4) Always configure both A and AAAA records for IPv4/IPv6 dual-stack, (5) Use `dig +trace` to debug resolution failures — it shows exactly where in the chain things break."""
    ),
    (
        "networking/tls-ssl-fundamentals",
        r"""Explain TLS/SSL fundamentals including the TLS 1.3 handshake, certificate chain validation, cipher suites, certificate pinning, mutual TLS (mTLS) for service-to-service auth, and common TLS misconfigurations to avoid.""",
        r"""## TLS Fundamentals: Handshake, Certificates, and mTLS

TLS (Transport Layer Security) encrypts network communication. Understanding TLS is essential for securing web applications and debugging connectivity issues.

### TLS 1.3 Handshake

```
TLS 1.3 completes in 1 RTT (down from 2 in TLS 1.2):

Client                              Server
  │                                    │
  │──── ClientHello ──────────────────→│  (supported ciphers, key share)
  │                                    │
  │←─── ServerHello ──────────────────│  (chosen cipher, key share)
  │←─── EncryptedExtensions ──────────│
  │←─── Certificate ──────────────────│  (server's cert chain)
  │←─── CertificateVerify ───────────│  (proof server owns the cert)
  │←─── Finished ─────────────────────│
  │                                    │
  │──── Finished ──────────────────────→│
  │                                    │
  │←──── Application Data ────────────→│  (encrypted!)
  │                                    │

Key improvements in TLS 1.3:
- 1-RTT handshake (was 2-RTT in TLS 1.2)
- 0-RTT resumption for repeat connections
- Removed insecure algorithms (RC4, SHA-1, RSA key exchange)
- Forward secrecy is mandatory (ephemeral Diffie-Hellman)
- Encrypted more of the handshake (even cert is encrypted)
```

### Certificate Chain Validation

```python
import ssl
import socket
from datetime import datetime, timezone
from dataclasses import dataclass


@dataclass
class CertInfo:
    subject: str
    issuer: str
    not_before: datetime
    not_after: datetime
    san: list[str]  # Subject Alternative Names
    serial: str


def inspect_certificate(hostname: str, port: int = 443) -> CertInfo:
    """Fetch and inspect a server's TLS certificate."""
    context = ssl.create_default_context()

    with socket.create_connection((hostname, port)) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
            cert = ssock.getpeercert()

            # Extract Subject Alternative Names
            san = []
            for type_name, value in cert.get("subjectAltName", []):
                san.append(f"{type_name}:{value}")

            subject = dict(x[0] for x in cert["subject"])
            issuer = dict(x[0] for x in cert["issuer"])

            return CertInfo(
                subject=subject.get("commonName", ""),
                issuer=issuer.get("organizationName", ""),
                not_before=datetime.strptime(
                    cert["notBefore"], "%b %d %H:%M:%S %Y %Z"
                ),
                not_after=datetime.strptime(
                    cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                ),
                san=san,
                serial=cert.get("serialNumber", ""),
            )


# Certificate chain:
# 1. Leaf certificate: your domain (example.com)
#    Signed by: Intermediate CA
# 2. Intermediate CA: Let's Encrypt R3
#    Signed by: Root CA
# 3. Root CA: ISRG Root X1
#    Self-signed, pre-installed in browsers/OS trust stores

# Validation steps:
# 1. Is the certificate expired? (check notBefore/notAfter)
# 2. Does the hostname match? (check SAN/CN)
# 3. Is the chain valid? (each cert signed by the next)
# 4. Is the root CA trusted? (in the trust store)
# 5. Is the cert revoked? (check CRL/OCSP)
```

### Mutual TLS (mTLS) for Service-to-Service

```python
import ssl
import aiohttp


def create_mtls_context(
    ca_cert: str,
    client_cert: str,
    client_key: str,
) -> ssl.SSLContext:
    """Create SSL context for mutual TLS."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    # Load CA certificate for verifying the server
    context.load_verify_locations(ca_cert)

    # Load client certificate and key for authenticating to the server
    context.load_cert_chain(certfile=client_cert, keyfile=client_key)

    # Enforce TLS 1.2+
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    # Verify server certificate
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED

    return context


async def mtls_request(url: str, mtls_context: ssl.SSLContext):
    """Make an HTTP request with mutual TLS."""
    connector = aiohttp.TCPConnector(ssl=mtls_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url) as response:
            return await response.json()


# Server-side mTLS verification
def create_server_mtls_context(
    server_cert: str,
    server_key: str,
    client_ca: str,
) -> ssl.SSLContext:
    """Server SSL context that requires client certificates."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=server_cert, keyfile=server_key)

    # Require client certificate
    context.load_verify_locations(client_ca)
    context.verify_mode = ssl.CERT_REQUIRED  # Reject clients without valid cert

    return context


# mTLS benefits for microservices:
# 1. Mutual authentication: both sides verify identity
# 2. Encrypted communication: protects data in transit
# 3. No passwords/tokens: identity is the certificate
# 4. Automatic rotation: certificates have short lifetimes
# Used by: service meshes (Istio, Linkerd), Kubernetes pod-to-pod
```

### Common Misconfigurations

```bash
# Test TLS configuration
# Use testssl.sh for comprehensive analysis
./testssl.sh example.com

# Common issues:

# 1. Missing intermediate certificates
# Browser shows "certificate not trusted" even with valid cert
# Fix: include the full chain in your server config
openssl s_client -connect example.com:443 -showcerts
# Should show 2-3 certificates (leaf + intermediates)

# 2. Expired certificates
openssl x509 -in cert.pem -noout -dates
# notBefore=Jan  1 00:00:00 2024 GMT
# notAfter=Mar 31 00:00:00 2024 GMT

# 3. Hostname mismatch
openssl x509 -in cert.pem -noout -text | grep -A1 "Subject Alternative Name"
# Should include your domain

# 4. Weak cipher suites
# TLS 1.3 only supports strong ciphers (AES-GCM, ChaCha20)
# But TLS 1.2 allows weak ones — restrict to:
# TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
# TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
# TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256

# 5. Missing HSTS header
# Add: Strict-Transport-Security: max-age=31536000; includeSubDomains

# 6. Not supporting TLS 1.3
# Check: openssl s_client -connect example.com:443 -tls1_3
```

```python
# Certificate monitoring
async def check_cert_expiry(hostname: str) -> dict:
    """Monitor certificate expiration."""
    info = inspect_certificate(hostname)
    now = datetime.now(timezone.utc)
    days_left = (info.not_after.replace(tzinfo=timezone.utc) - now).days

    return {
        "hostname": hostname,
        "subject": info.subject,
        "issuer": info.issuer,
        "expires": info.not_after.isoformat(),
        "days_left": days_left,
        "warning": days_left < 30,
        "critical": days_left < 7,
    }
```

**TLS best practices**: (1) Use TLS 1.3 wherever possible — it's faster and more secure, (2) Always include the full certificate chain — missing intermediates cause intermittent failures, (3) Automate certificate renewal (Let's Encrypt + certbot), (4) Use mTLS for service-to-service communication in microservices, (5) Monitor certificate expiry — expired certs cause outages that are hard to debug under pressure."""
    ),
]
