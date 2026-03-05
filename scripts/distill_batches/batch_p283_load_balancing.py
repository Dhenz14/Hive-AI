"""Load balancing and service discovery — strategies, health checks, routing."""

PAIRS = [
    (
        "architecture/load-balancing",
        "Show load balancing algorithms: round robin, weighted, least connections, consistent hashing, and health-aware routing.",
        '''Load balancing strategies:

```python
import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Optional
from bisect import bisect_right


@dataclass
class Backend:
    id: str
    host: str
    port: int
    weight: int = 1
    healthy: bool = True
    active_connections: int = 0
    last_health_check: float = 0
    response_time_ms: float = 0


class RoundRobinBalancer:
    def __init__(self, backends: list[Backend]):
        self.backends = backends
        self.index = 0

    def next(self) -> Optional[Backend]:
        healthy = [b for b in self.backends if b.healthy]
        if not healthy:
            return None
        backend = healthy[self.index % len(healthy)]
        self.index += 1
        return backend


class WeightedRoundRobin:
    """Weighted round robin — higher weight = more traffic."""
    def __init__(self, backends: list[Backend]):
        self.backends = backends
        self.current_weights = [0] * len(backends)

    def next(self) -> Optional[Backend]:
        healthy = [(i, b) for i, b in enumerate(self.backends) if b.healthy]
        if not healthy:
            return None
        total = sum(b.weight for _, b in healthy)
        for i, b in healthy:
            self.current_weights[i] += b.weight
        max_idx = max(healthy, key=lambda x: self.current_weights[x[0]])[0]
        self.current_weights[max_idx] -= total
        return self.backends[max_idx]


class LeastConnections:
    def __init__(self, backends: list[Backend]):
        self.backends = backends

    def next(self) -> Optional[Backend]:
        healthy = [b for b in self.backends if b.healthy]
        if not healthy:
            return None
        return min(healthy, key=lambda b: b.active_connections)


class ConsistentHashRing:
    """Consistent hashing — minimize redistribution on backend changes."""
    def __init__(self, backends: list[Backend], replicas: int = 150):
        self.ring: list[tuple[int, Backend]] = []
        self.replicas = replicas
        for backend in backends:
            self.add(backend)
        self.ring.sort(key=lambda x: x[0])

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add(self, backend: Backend):
        for i in range(self.replicas):
            h = self._hash(f"{backend.id}:{i}")
            self.ring.append((h, backend))
        self.ring.sort(key=lambda x: x[0])

    def remove(self, backend_id: str):
        self.ring = [(h, b) for h, b in self.ring if b.id != backend_id]

    def get(self, key: str) -> Optional[Backend]:
        if not self.ring:
            return None
        h = self._hash(key)
        hashes = [r[0] for r in self.ring]
        idx = bisect_right(hashes, h) % len(self.ring)
        # Find next healthy backend
        for _ in range(len(self.ring)):
            backend = self.ring[idx][1]
            if backend.healthy:
                return backend
            idx = (idx + 1) % len(self.ring)
        return None


class HealthChecker:
    """Active health checking for backends."""

    def __init__(self, backends: list[Backend], interval: float = 10,
                 unhealthy_threshold: int = 3, healthy_threshold: int = 2):
        self.backends = backends
        self.interval = interval
        self.unhealthy_threshold = unhealthy_threshold
        self.healthy_threshold = healthy_threshold
        self.consecutive_failures: dict[str, int] = {}
        self.consecutive_successes: dict[str, int] = {}

    async def check_backend(self, backend: Backend) -> bool:
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://{backend.host}:{backend.port}/health",
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def run_checks(self):
        for backend in self.backends:
            healthy = await self.check_backend(backend)
            backend.last_health_check = time.time()

            if healthy:
                self.consecutive_failures[backend.id] = 0
                self.consecutive_successes[backend.id] = (
                    self.consecutive_successes.get(backend.id, 0) + 1
                )
                if (not backend.healthy and
                    self.consecutive_successes[backend.id] >= self.healthy_threshold):
                    backend.healthy = True
            else:
                self.consecutive_successes[backend.id] = 0
                self.consecutive_failures[backend.id] = (
                    self.consecutive_failures.get(backend.id, 0) + 1
                )
                if (backend.healthy and
                    self.consecutive_failures[backend.id] >= self.unhealthy_threshold):
                    backend.healthy = False
```

Key patterns:
1. **Round robin** — simplest; equal distribution; good when backends are identical
2. **Weighted** — proportional distribution; heavier backends get more traffic
3. **Least connections** — route to least busy; adapts to different request durations
4. **Consistent hashing** — same key → same backend; adding/removing only redistributes 1/N keys
5. **Health checks** — consecutive threshold prevents flapping; unhealthy backends skipped'''
    ),
    (
        "architecture/service-discovery",
        "Show service discovery patterns: client-side discovery, service registry, DNS-based, and sidecar proxy.",
        '''Service discovery patterns:

```python
import time
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ServiceInstance:
    service_name: str
    instance_id: str
    host: str
    port: int
    metadata: dict = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    healthy: bool = True


class ServiceRegistry:
    """Central service registry for service discovery."""

    def __init__(self, heartbeat_ttl: float = 30):
        self.services: dict[str, dict[str, ServiceInstance]] = {}
        self.heartbeat_ttl = heartbeat_ttl

    def register(self, instance: ServiceInstance):
        self.services.setdefault(instance.service_name, {})[instance.instance_id] = instance

    def deregister(self, service_name: str, instance_id: str):
        if service_name in self.services:
            self.services[service_name].pop(instance_id, None)

    def heartbeat(self, service_name: str, instance_id: str):
        instance = self.services.get(service_name, {}).get(instance_id)
        if instance:
            instance.last_heartbeat = time.time()
            instance.healthy = True

    def discover(self, service_name: str, tags: dict = None) -> list[ServiceInstance]:
        """Get healthy instances of a service."""
        instances = self.services.get(service_name, {}).values()
        now = time.time()

        healthy = []
        for inst in instances:
            if now - inst.last_heartbeat > self.heartbeat_ttl:
                inst.healthy = False
                continue
            if tags:
                if not all(inst.metadata.get(k) == v for k, v in tags.items()):
                    continue
            if inst.healthy:
                healthy.append(inst)

        return healthy

    def resolve(self, service_name: str) -> Optional[ServiceInstance]:
        """Get one healthy instance (random selection)."""
        healthy = self.discover(service_name)
        return random.choice(healthy) if healthy else None


class ClientSideDiscovery:
    """Client discovers and load-balances across instances."""

    def __init__(self, registry: ServiceRegistry):
        self.registry = registry
        self.cache: dict[str, tuple[list, float]] = {}
        self.cache_ttl = 10  # seconds

    def get_instance(self, service_name: str) -> ServiceInstance:
        # Check local cache
        if service_name in self.cache:
            instances, cached_at = self.cache[service_name]
            if time.time() - cached_at < self.cache_ttl:
                healthy = [i for i in instances if i.healthy]
                if healthy:
                    return random.choice(healthy)

        # Refresh from registry
        instances = self.registry.discover(service_name)
        self.cache[service_name] = (instances, time.time())

        if not instances:
            raise ServiceUnavailable(f"No instances of {service_name}")
        return random.choice(instances)

    async def call(self, service_name: str, path: str, **kwargs):
        instance = self.get_instance(service_name)
        url = f"http://{instance.host}:{instance.port}{path}"
        import httpx
        async with httpx.AsyncClient() as client:
            return await client.request(url=url, **kwargs)


class ServiceUnavailable(Exception):
    pass
```

Key patterns:
1. **Service registry** — central database of all service instances; heartbeat-based health
2. **Client-side discovery** — client queries registry, caches results, selects instance
3. **Heartbeat TTL** — instances must send periodic heartbeats; stale entries marked unhealthy
4. **Tag-based filtering** — discover by metadata (region, version, canary)
5. **Local cache** — avoid hammering registry; refresh every N seconds'''
    ),
]
"""
