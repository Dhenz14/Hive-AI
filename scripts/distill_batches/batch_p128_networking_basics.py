"""Networking — DNS, HTTP/2, TLS, and network debugging patterns."""

PAIRS = [
    (
        "devops/dns-patterns",
        "Show DNS patterns: record types, DNS-based service discovery, and troubleshooting.",
        '''DNS patterns and service discovery:

```bash
# --- DNS record types ---

# A record: domain -> IPv4
# myapp.com.    IN  A    93.184.216.34

# AAAA record: domain -> IPv6
# myapp.com.    IN  AAAA 2606:2800:220:1:248:1893:25c8:1946

# CNAME record: alias -> canonical name
# www.myapp.com.  IN  CNAME  myapp.com.
# api.myapp.com.  IN  CNAME  myapp-api.us-east-1.elb.amazonaws.com.

# MX record: mail server
# myapp.com.    IN  MX  10 mail1.myapp.com.
# myapp.com.    IN  MX  20 mail2.myapp.com.

# TXT record: verification, SPF, DKIM
# myapp.com.    IN  TXT  "v=spf1 include:_spf.google.com ~all"

# SRV record: service discovery
# _http._tcp.myapp.com.  IN  SRV  10 60 8080 server1.myapp.com.
# _http._tcp.myapp.com.  IN  SRV  10 40 8080 server2.myapp.com.


# --- DNS troubleshooting ---

# Basic lookup
dig myapp.com
dig myapp.com A +short         # Just the IP
dig myapp.com MX +short        # Mail servers

# Trace resolution path
dig myapp.com +trace

# Query specific nameserver
dig @8.8.8.8 myapp.com

# Reverse lookup
dig -x 93.184.216.34

# Check all record types
dig myapp.com ANY +noall +answer

# Check TTL (time to live)
dig myapp.com A +noall +answer
# myapp.com. 300 IN A 93.184.216.34  (TTL = 300 seconds)

# nslookup alternative
nslookup myapp.com 8.8.8.8

# Check DNS propagation
dig myapp.com @ns1.myapp.com    # Primary NS
dig myapp.com @8.8.8.8          # Google DNS
dig myapp.com @1.1.1.1          # Cloudflare DNS
```

```python
# --- DNS-based service discovery (Python) ---

import socket
import dns.resolver  # dnspython library


def discover_service(service_name: str, domain: str) -> list[dict]:
    """Discover services via DNS SRV records."""
    srv_name = f"_{service_name}._tcp.{domain}"

    try:
        answers = dns.resolver.resolve(srv_name, "SRV")
    except dns.resolver.NXDOMAIN:
        return []

    services = []
    for rdata in answers:
        services.append({
            "host": str(rdata.target).rstrip("."),
            "port": rdata.port,
            "priority": rdata.priority,
            "weight": rdata.weight,
        })

    # Sort by priority (lower = preferred), then weight (higher = preferred)
    services.sort(key=lambda s: (s["priority"], -s["weight"]))
    return services


def health_check_dns(domain: str) -> dict:
    """Check DNS health for a domain."""
    results = {}

    for record_type in ["A", "AAAA", "MX", "NS", "TXT"]:
        try:
            answers = dns.resolver.resolve(domain, record_type)
            results[record_type] = [str(r) for r in answers]
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            results[record_type] = []
        except Exception as e:
            results[record_type] = f"Error: {e}"

    return results


# --- Simple service registry ---

class ServiceRegistry:
    """In-memory service registry with health checking."""

    def __init__(self):
        self._services: dict[str, list[dict]] = {}

    def register(self, name: str, host: str, port: int, metadata: dict = None):
        if name not in self._services:
            self._services[name] = []

        instance = {
            "host": host,
            "port": port,
            "metadata": metadata or {},
            "healthy": True,
        }
        self._services[name].append(instance)

    def deregister(self, name: str, host: str, port: int):
        if name in self._services:
            self._services[name] = [
                s for s in self._services[name]
                if not (s["host"] == host and s["port"] == port)
            ]

    def discover(self, name: str) -> list[dict]:
        """Get healthy instances of a service."""
        return [
            s for s in self._services.get(name, [])
            if s["healthy"]
        ]

    async def health_check_all(self):
        """Check health of all registered services."""
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, instances in self._services.items():
                for instance in instances:
                    url = f"http://{instance['host']}:{instance['port']}/health"
                    try:
                        resp = await client.get(url)
                        instance["healthy"] = resp.status_code == 200
                    except httpx.RequestError:
                        instance["healthy"] = False
```

DNS patterns:
1. **SRV records** — service discovery with host, port, priority, and weight
2. **`dig +trace`** — trace full DNS resolution path for debugging
3. **Multiple record types** — A (IPv4), AAAA (IPv6), CNAME (alias), MX (mail)
4. **TTL awareness** — understand caching duration when changing DNS records
5. **Health-checked registry** — periodically verify service instances are alive'''
    ),
]
"""
