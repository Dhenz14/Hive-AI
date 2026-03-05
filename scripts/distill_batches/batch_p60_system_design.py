"""System design — distributed systems, scalability, and architecture patterns."""

PAIRS = [
    (
        "system-design/load-balancing",
        "Show load balancing patterns: algorithms, health checks, session affinity, and connection draining.",
        '''Load balancing patterns:

```python
# --- Load balancing algorithms ---

import random
import hashlib
import bisect
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol
import time
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class Backend:
    host: str
    port: int
    weight: int = 1
    healthy: bool = True
    active_connections: int = 0
    last_health_check: float = 0


class LoadBalancer(Protocol):
    def select(self, backends: list[Backend], key: str = "") -> Backend: ...


class RoundRobin:
    """Simple round-robin selection."""
    def __init__(self):
        self._index = 0

    def select(self, backends: list[Backend], key: str = "") -> Backend:
        healthy = [b for b in backends if b.healthy]
        if not healthy:
            raise NoHealthyBackendError("No healthy backends")
        backend = healthy[self._index % len(healthy)]
        self._index += 1
        return backend


class WeightedRoundRobin:
    """Weighted round-robin using smooth algorithm."""
    def __init__(self):
        self._current_weights: dict[str, int] = {}

    def select(self, backends: list[Backend], key: str = "") -> Backend:
        healthy = [b for b in backends if b.healthy]
        if not healthy:
            raise NoHealthyBackendError("No healthy backends")

        total = sum(b.weight for b in healthy)
        best = None

        for b in healthy:
            k = f"{b.host}:{b.port}"
            self._current_weights[k] = (
                self._current_weights.get(k, 0) + b.weight
            )
            if best is None or self._current_weights[k] > self._current_weights.get(
                f"{best.host}:{best.port}", 0
            ):
                best = b

        best_key = f"{best.host}:{best.port}"
        self._current_weights[best_key] -= total
        return best


class LeastConnections:
    """Route to backend with fewest active connections."""
    def select(self, backends: list[Backend], key: str = "") -> Backend:
        healthy = [b for b in backends if b.healthy]
        if not healthy:
            raise NoHealthyBackendError("No healthy backends")
        return min(healthy, key=lambda b: b.active_connections / b.weight)


class ConsistentHash:
    """Consistent hashing with virtual nodes."""
    def __init__(self, replicas: int = 150):
        self.replicas = replicas
        self._ring: list[tuple[int, str]] = []
        self._nodes: dict[str, Backend] = {}

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_backend(self, backend: Backend):
        node_key = f"{backend.host}:{backend.port}"
        self._nodes[node_key] = backend
        for i in range(self.replicas):
            h = self._hash(f"{node_key}:{i}")
            bisect.insort(self._ring, (h, node_key))

    def remove_backend(self, backend: Backend):
        node_key = f"{backend.host}:{backend.port}"
        self._nodes.pop(node_key, None)
        self._ring = [(h, n) for h, n in self._ring if n != node_key]

    def select(self, backends: list[Backend], key: str = "") -> Backend:
        if not self._ring:
            raise NoHealthyBackendError("No backends in ring")
        h = self._hash(key or str(random.random()))
        idx = bisect.bisect_left(self._ring, (h,))
        if idx >= len(self._ring):
            idx = 0
        _, node_key = self._ring[idx]
        return self._nodes[node_key]


# --- Health checker ---

class HealthChecker:
    """Background health checking with circuit breaker."""

    def __init__(self, backends: list[Backend],
                 interval: float = 10.0,
                 timeout: float = 5.0,
                 unhealthy_threshold: int = 3,
                 healthy_threshold: int = 2):
        self.backends = backends
        self.interval = interval
        self.timeout = timeout
        self.unhealthy_threshold = unhealthy_threshold
        self.healthy_threshold = healthy_threshold
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._success_counts: dict[str, int] = defaultdict(int)

    async def check_backend(self, backend: Backend) -> bool:
        import httpx
        key = f"{backend.host}:{backend.port}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"http://{backend.host}:{backend.port}/health"
                )
                if response.status_code == 200:
                    self._success_counts[key] += 1
                    self._failure_counts[key] = 0
                    if self._success_counts[key] >= self.healthy_threshold:
                        if not backend.healthy:
                            logger.info("Backend %s is now healthy", key)
                        backend.healthy = True
                    return True
        except Exception:
            pass

        self._failure_counts[key] += 1
        self._success_counts[key] = 0
        if self._failure_counts[key] >= self.unhealthy_threshold:
            if backend.healthy:
                logger.warning("Backend %s marked unhealthy", key)
            backend.healthy = False
        return False

    async def run(self):
        while True:
            tasks = [self.check_backend(b) for b in self.backends]
            await asyncio.gather(*tasks)
            await asyncio.sleep(self.interval)


# --- Connection draining ---

class DrainingProxy:
    """Graceful connection draining on backend removal."""

    def __init__(self, drain_timeout: float = 30.0):
        self.drain_timeout = drain_timeout
        self._draining: set[str] = set()

    async def drain_backend(self, backend: Backend):
        """Stop sending new requests, wait for existing to finish."""
        key = f"{backend.host}:{backend.port}"
        self._draining.add(key)
        backend.healthy = False  # Stop new connections

        deadline = time.time() + self.drain_timeout
        while backend.active_connections > 0 and time.time() < deadline:
            await asyncio.sleep(1)
            logger.info("Draining %s: %d connections remaining",
                       key, backend.active_connections)

        self._draining.discard(key)
        logger.info("Backend %s drained", key)
```

Load balancing patterns:
1. **Weighted round-robin** — distribute proportionally to backend capacity
2. **Least connections** — route to least-loaded backend (weighted)
3. **Consistent hashing** — sticky routing with minimal redistribution on changes
4. **Health checks** — thresholds prevent flapping (3 failures to mark unhealthy)
5. **Connection draining** — graceful removal waits for in-flight requests'''
    ),
    (
        "system-design/distributed-cache",
        "Show distributed caching patterns: cache-aside, write-through, invalidation, and multi-layer cache.",
        '''Distributed caching patterns:

```python
import json
import hashlib
import asyncio
import logging
import time
from typing import Any, Callable, Optional
from functools import wraps
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# --- Multi-layer cache ---

class CacheLayer:
    """Abstract cache layer."""
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: Any, ttl: int = 300): ...
    async def delete(self, key: str): ...
    async def exists(self, key: str) -> bool: ...


class LocalCache(CacheLayer):
    """In-process LRU cache (L1)."""
    def __init__(self, max_size: int = 1000):
        from collections import OrderedDict
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size

    async def get(self, key: str) -> Any:
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                self._cache.move_to_end(key)
                return value
            del self._cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: int = 300):
        if len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (value, time.time() + ttl)

    async def delete(self, key: str):
        self._cache.pop(key, None)


class RedisCache(CacheLayer):
    """Redis cache (L2)."""
    def __init__(self, redis):
        self._redis = redis

    async def get(self, key: str) -> Any:
        data = await self._redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def set(self, key: str, value: Any, ttl: int = 300):
        await self._redis.set(key, json.dumps(value), ex=ttl)

    async def delete(self, key: str):
        await self._redis.delete(key)


class MultiLayerCache:
    """L1 (local) + L2 (Redis) cache."""

    def __init__(self, l1: LocalCache, l2: RedisCache):
        self.l1 = l1
        self.l2 = l2

    async def get(self, key: str) -> Any:
        # Try L1 first (fastest)
        value = await self.l1.get(key)
        if value is not None:
            return value

        # Try L2
        value = await self.l2.get(key)
        if value is not None:
            await self.l1.set(key, value, ttl=60)  # Shorter TTL for L1
            return value

        return None

    async def set(self, key: str, value: Any, ttl: int = 300):
        await asyncio.gather(
            self.l1.set(key, value, min(ttl, 60)),
            self.l2.set(key, value, ttl),
        )

    async def delete(self, key: str):
        await asyncio.gather(
            self.l1.delete(key),
            self.l2.delete(key),
        )


# --- Cache-aside with stampede prevention ---

class CacheAside:
    """Cache-aside pattern with singleflight (stampede prevention)."""

    def __init__(self, cache: MultiLayerCache):
        self.cache = cache
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_or_fetch(self, key: str, fetcher: Callable,
                           ttl: int = 300) -> Any:
        # Try cache
        value = await self.cache.get(key)
        if value is not None:
            return value

        # Singleflight: only one caller fetches, others wait
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:
            # Double-check after acquiring lock
            value = await self.cache.get(key)
            if value is not None:
                return value

            # Fetch from source
            value = await fetcher()
            await self.cache.set(key, value, ttl)
            return value

    async def invalidate(self, key: str):
        await self.cache.delete(key)


# --- Cache key generation ---

def cache_key(*parts: str, prefix: str = "cache") -> str:
    """Generate consistent cache key."""
    raw = ":".join(str(p) for p in parts)
    return f"{prefix}:{raw}"

def cache_key_hash(*parts: str, prefix: str = "cache") -> str:
    """Hash-based key for complex inputs."""
    raw = ":".join(str(p) for p in parts)
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


# --- Decorator for caching ---

def cached(ttl: int = 300, prefix: str = "fn"):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, *args, **kwargs):
            key = cache_key(prefix, fn.__name__,
                           *[str(a) for a in args],
                           *[f"{k}={v}" for k, v in sorted(kwargs.items())])
            return await self._cache.get_or_fetch(
                key, lambda: fn(self, *args, **kwargs), ttl
            )
        return wrapper
    return decorator


# Usage:
# class UserService:
#     def __init__(self, db, cache):
#         self._cache = CacheAside(cache)
#
#     @cached(ttl=300, prefix="user")
#     async def get_user(self, user_id: str):
#         return await self.db.fetch_user(user_id)
#
#     async def update_user(self, user_id: str, data: dict):
#         await self.db.update_user(user_id, data)
#         await self._cache.invalidate(cache_key("user", "get_user", user_id))
```

Caching patterns:
1. **Multi-layer** — L1 (in-process, microseconds) + L2 (Redis, milliseconds)
2. **Singleflight/stampede prevention** — one goroutine fetches, others wait
3. **Cache-aside** — read-through with explicit invalidation on writes
4. **Shorter L1 TTL** — local cache stale risk mitigated by shorter expiry
5. **Consistent key generation** — deterministic keys for cache hits across instances'''
    ),
    (
        "system-design/message-queue",
        "Show message queue patterns: pub/sub, work queues, dead letter queues, exactly-once processing, and backpressure.",
        '''Message queue patterns:

```python
import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Any
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


# --- Message structure ---

@dataclass
class Message:
    id: str
    topic: str
    body: dict
    headers: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    attempt: int = 0
    max_retries: int = 3


# --- Work queue with acknowledgment ---

class WorkQueue:
    """Reliable work queue with visibility timeout and DLQ."""

    def __init__(self, redis, queue_name: str,
                 visibility_timeout: int = 30,
                 max_retries: int = 3):
        self.redis = redis
        self.queue = f"queue:{queue_name}"
        self.processing = f"processing:{queue_name}"
        self.dlq = f"dlq:{queue_name}"
        self.visibility_timeout = visibility_timeout
        self.max_retries = max_retries

    async def enqueue(self, message: Message):
        """Add message to queue."""
        await self.redis.lpush(
            self.queue,
            json.dumps({
                "id": message.id,
                "body": message.body,
                "headers": message.headers,
                "timestamp": message.timestamp,
                "attempt": 0,
            })
        )

    async def dequeue(self, timeout: int = 5) -> Message | None:
        """Atomically move message to processing set."""
        result = await self.redis.brpoplpush(
            self.queue, self.processing, timeout=timeout
        )
        if result is None:
            return None

        data = json.loads(result)
        data["attempt"] += 1

        # Set visibility timeout
        await self.redis.zadd(
            f"{self.processing}:timeouts",
            {result: time.time() + self.visibility_timeout}
        )

        return Message(
            id=data["id"],
            topic=self.queue,
            body=data["body"],
            headers=data.get("headers", {}),
            attempt=data["attempt"],
        )

    async def ack(self, message: Message):
        """Acknowledge successful processing."""
        raw = await self._find_in_processing(message.id)
        if raw:
            await self.redis.lrem(self.processing, 1, raw)

    async def nack(self, message: Message):
        """Negative acknowledge — retry or DLQ."""
        raw = await self._find_in_processing(message.id)
        if not raw:
            return

        await self.redis.lrem(self.processing, 1, raw)

        if message.attempt >= self.max_retries:
            logger.warning("Message %s exceeded retries, moving to DLQ",
                          message.id)
            await self.redis.lpush(self.dlq, raw)
        else:
            # Re-enqueue with backoff delay
            delay = 2 ** message.attempt
            await asyncio.sleep(delay)
            data = json.loads(raw)
            data["attempt"] = message.attempt
            await self.redis.lpush(self.queue, json.dumps(data))

    async def requeue_stuck(self):
        """Requeue messages past visibility timeout."""
        now = time.time()
        stuck = await self.redis.zrangebyscore(
            f"{self.processing}:timeouts", 0, now
        )
        for raw in stuck:
            await self.redis.lrem(self.processing, 1, raw)
            await self.redis.lpush(self.queue, raw)
            await self.redis.zrem(f"{self.processing}:timeouts", raw)
            logger.info("Requeued stuck message")


# --- Consumer with backpressure ---

class Consumer:
    """Message consumer with concurrency control and backpressure."""

    def __init__(self, queue: WorkQueue,
                 handler: Callable,
                 concurrency: int = 10):
        self.queue = queue
        self.handler = handler
        self.semaphore = asyncio.Semaphore(concurrency)
        self._running = True

    async def start(self):
        """Main consumer loop."""
        tasks = set()

        while self._running:
            # Backpressure: wait if at max concurrency
            await self.semaphore.acquire()

            msg = await self.queue.dequeue(timeout=2)
            if msg is None:
                self.semaphore.release()
                continue

            task = asyncio.create_task(self._process(msg))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

        # Wait for in-flight tasks on shutdown
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _process(self, msg: Message):
        try:
            await self.handler(msg)
            await self.queue.ack(msg)
        except Exception as e:
            logger.error("Failed to process %s: %s", msg.id, e)
            await self.queue.nack(msg)
        finally:
            self.semaphore.release()

    def stop(self):
        self._running = False


# --- Idempotent processing ---

class IdempotentProcessor:
    """Ensure exactly-once processing using message ID dedup."""

    def __init__(self, redis, ttl: int = 86400):
        self.redis = redis
        self.ttl = ttl

    async def process_if_new(self, message: Message,
                              handler: Callable) -> bool:
        """Process only if message hasn't been processed before."""
        key = f"processed:{message.id}"

        # Atomic check-and-set
        was_set = await self.redis.set(key, "1", nx=True, ex=self.ttl)
        if not was_set:
            logger.info("Duplicate message %s, skipping", message.id)
            return False

        try:
            await handler(message)
            return True
        except Exception:
            # Remove dedup key so message can be retried
            await self.redis.delete(key)
            raise
```

Message queue patterns:
1. **Visibility timeout** — message hidden from other consumers during processing
2. **Dead letter queue** — messages exceeding retry limit moved for investigation
3. **Backpressure** — semaphore limits concurrent processing to prevent overload
4. **Idempotent processing** — Redis `SET NX` dedup key ensures exactly-once
5. **Graceful shutdown** — stop accepting new messages, drain in-flight tasks'''
    ),
]
"""
