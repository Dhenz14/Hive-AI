"""p20 networking"""

PAIRS = [
    (
        "networking/load-balancing-algorithms",
        "Explain load balancing algorithms including round-robin, weighted round-robin, least connections, consistent hashing, IP hash, and least response time. Compare L4 vs L7 load balancing, health checking, and sticky sessions.",
        '''Load balancers distribute traffic across multiple backend servers. The algorithm choice determines fairness, performance, and behavior under failure.

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
            key=lambda b: b.active_connections / max(b.weight, 1)'''
    ),
    (
        "networking/http2-http3-protocols",
        "Explain HTTP/2 and HTTP/3 protocols including multiplexing, server push, header compression (HPACK/QPACK), stream prioritization, HTTP/3's use of QUIC over UDP, 0-RTT connection establishment, and migration considerations.",
        '''HTTP/2 and HTTP/3 solve fundamental performance limitations of HTTP/1.1. Understanding their differences helps you optimize web application performance.

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
# First request: ":method: GET", ":path: /api/users" -> 50 bytes
# Second request: same headers -> 2 bytes (just table indices!)

# Python example: making HTTP/2 requests
import httpx

async def http2_requests():
    """HTTP/2 multiplexes all requests on a single TCP connection."""
    async with httpx.AsyncClient(http2=True) as client:
        # These all share one TCP connection with multiplexed streams
        responses = await asyncio.gather(
            client.get("https://api.example.com/users"),
            client.get("https://api.example.com/products"),
            client.get("https://api.example.com/orders"),'''
    ),
    (
        "networking/dns-internals",
        "Explain DNS internals including the resolution process, record types (A, AAAA, CNAME, MX, TXT, SRV, NS, SOA), DNS caching and TTL, DNSSEC, common DNS patterns for service discovery, and debugging with dig/nslookup.",
        '''DNS is the internet's phone book -- translating human-readable names to IP addresses. Understanding DNS deeply helps with debugging connectivity, configuring services, and designing distributed systems.

### The Resolution Process

```
User types: www.example.com

1. Browser cache -> OS cache -> Router cache (check local caches first)

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
# A record: name -> IPv4 address
example.com.  A  93.184.216.34

# AAAA record: name -> IPv6 address
example.com.  AAAA  2606:2800:220:1:248:1893:25c8:1946

# CNAME record: alias -> canonical name
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
    86400       ; Minimum TTL'''
    ),
    (
        "weight",
        "} for rdata in answers ]",
        '''instances.sort(key=lambda x: x["priority"])
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

**DNS best practices**: (1) Use short TTLs (60-300s) for services that need fast failover, (2) Lower TTLs BEFORE a migration, wait for old TTL to expire, then make the change, (3) Use SRV records for internal service discovery -- they include port and priority, (4) Always configure both A and AAAA records for IPv4/IPv6 dual-stack, (5) Use `dig +trace` to debug resolution failures -- it shows exactly where in the chain things break.'''
    ),
    (
        "networking/tls-ssl-fundamentals",
        "Explain TLS/SSL fundamentals including the TLS 1.3 handshake, certificate chain validation, cipher suites, certificate pinning, mutual TLS (mTLS) for service-to-service auth, and common TLS misconfigurations to avoid.",
        '''TLS (Transport Layer Security) encrypts network communication. Understanding TLS is essential for securing web applications and debugging connectivity issues.

### TLS 1.3 Handshake

```
TLS 1.3 completes in 1 RTT (down from 2 in TLS 1.2):

Client                              Server
  │                                    │
  │──── ClientHello ──────────────────->│  (supported ciphers, key share)
  │                                    │
  │←─── ServerHello ──────────────────│  (chosen cipher, key share)
  │←─── EncryptedExtensions ──────────│
  │←─── Certificate ──────────────────│  (server's cert chain)
  │←─── CertificateVerify ───────────│  (proof server owns the cert)
  │←─── Finished ─────────────────────│
  │                                    │
  │──── Finished ──────────────────────->│
  │                                    │
  │←──── Application Data ────────────->│  (encrypted!)
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
                    cert["notBefore"], "%b %d %H:%M:%S %Y %Z"'''
    ),
    (
        "critical",
        "}",
        '''**TLS best practices**: (1) Use TLS 1.3 wherever possible -- it's faster and more secure, (2) Always include the full certificate chain -- missing intermediates cause intermittent failures, (3) Automate certificate renewal (Let's Encrypt + certbot), (4) Use mTLS for service-to-service communication in microservices, (5) Monitor certificate expiry -- expired certs cause outages that are hard to debug under pressure.'''
    ),
]
