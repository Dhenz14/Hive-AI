"""Caching: cache-aside, write-through, write-behind, distributed cache (Redis), cache invalidation."""

PAIRS = [
    (
        "caching/cache-aside-pattern",
        "How do I implement the cache-aside (lazy loading) pattern in Python with Redis, including TTL management, cache stampede prevention, and serialization?",
        '''Cache-aside is the most common caching pattern. The application checks the cache first, and on a miss, fetches from the database and populates the cache. Here is a production implementation with stampede prevention.

```python
"""Cache-aside pattern with Redis, stampede prevention, and monitoring."""

import json
import time
import hashlib
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable, TypeVar
from dataclasses import dataclass, field
from functools import wraps
from enum import Enum

import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CacheResult(str, Enum):
    HIT = "hit"
    MISS = "miss"
    STALE = "stale"
    ERROR = "error"


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    errors: int = 0
    stale_served: int = 0
    stampede_prevented: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class CacheSerializer:
    """Handles serialization/deserialization for cache values."""

    @staticmethod
    def serialize(value: Any) -> str:
        if isinstance(value, BaseModel):
            return value.model_dump_json()
        return json.dumps(value, default=str)

    @staticmethod
    def deserialize(raw: str, model_cls: type | None = None) -> Any:
        if model_cls and issubclass(model_cls, BaseModel):
            return model_cls.model_validate_json(raw)
        return json.loads(raw)


class CacheAside:
    """Production cache-aside implementation with Redis."""

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "cache",
        default_ttl: int = 300,
        stale_ttl: int = 60,
        lock_ttl: int = 10,
    ):
        self.redis = redis_client
        self.prefix = prefix
        self.default_ttl = default_ttl
        self.stale_ttl = stale_ttl
        self.lock_ttl = lock_ttl
        self.stats = CacheStats()
        self.serializer = CacheSerializer()

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self.prefix}:lock:{key}"

    def _stale_key(self, key: str) -> str:
        return f"{self.prefix}:stale:{key}"

    async def get(
        self,
        key: str,
        model_cls: type | None = None,
    ) -> tuple[Any | None, CacheResult]:
        """Get value from cache, returning (value, result_type)."""
        try:
            cache_key = self._key(key)
            raw = await self.redis.get(cache_key)

            if raw is not None:
                self.stats.hits += 1
                return self.serializer.deserialize(raw, model_cls), CacheResult.HIT

            self.stats.misses += 1
            return None, CacheResult.MISS

        except Exception as exc:
            self.stats.errors += 1
            logger.warning("Cache get error for %s: %s", key, exc)
            return None, CacheResult.ERROR

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """Set value in cache with TTL."""
        try:
            cache_key = self._key(key)
            stale_key = self._stale_key(key)
            serialized = self.serializer.serialize(value)
            ttl = ttl or self.default_ttl

            pipe = self.redis.pipeline()
            pipe.setex(cache_key, ttl, serialized)
            # Keep stale copy for serving during refresh
            pipe.setex(stale_key, ttl + self.stale_ttl, serialized)
            await pipe.execute()

        except Exception as exc:
            logger.warning("Cache set error for %s: %s", key, exc)

    async def delete(self, key: str) -> None:
        """Invalidate cache entry."""
        try:
            pipe = self.redis.pipeline()
            pipe.delete(self._key(key))
            pipe.delete(self._stale_key(key))
            pipe.delete(self._lock_key(key))
            await pipe.execute()
        except Exception as exc:
            logger.warning("Cache delete error for %s: %s", key, exc)

    async def get_or_set(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
        ttl: int | None = None,
        model_cls: type | None = None,
    ) -> Any:
        """Cache-aside: get from cache or fetch and cache."""
        # 1. Try cache
        value, result = await self.get(key, model_cls)
        if result == CacheResult.HIT:
            return value

        # 2. Cache miss -- prevent stampede with distributed lock
        lock_key = self._lock_key(key)
        acquired = await self.redis.set(
            lock_key, "1", nx=True, ex=self.lock_ttl
        )

        if not acquired:
            # Another process is fetching; serve stale if available
            stale = await self.redis.get(self._stale_key(key))
            if stale:
                self.stats.stale_served += 1
                self.stats.stampede_prevented += 1
                return self.serializer.deserialize(stale, model_cls)

            # No stale data; wait briefly for the other process
            for _ in range(5):
                await asyncio.sleep(0.1)
                value, result = await self.get(key, model_cls)
                if result == CacheResult.HIT:
                    return value

        try:
            # 3. Fetch from source
            value = await fetcher()
            # 4. Populate cache
            await self.set(key, value, ttl)
            return value
        finally:
            await self.redis.delete(lock_key)

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern."""
        full_pattern = self._key(pattern)
        count = 0
        async for key in self.redis.scan_iter(match=full_pattern):
            await self.redis.delete(key)
            count += 1
        return count


# ── Decorator for Method-Level Caching ─────────────────────────

def cached(
    key_template: str,
    ttl: int = 300,
    model_cls: type | None = None,
):
    """Decorator for cache-aside on async functions.

    Usage:
        @cached("user:{user_id}", ttl=600, model_cls=UserModel)
        async def get_user(self, user_id: str) -> UserModel:
            return await self.db.fetch_user(user_id)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self_or_first, *args, **kwargs):
            # Build cache key from function arguments
            import inspect
            sig = inspect.signature(func)
            bound = sig.bind(self_or_first, *args, **kwargs)
            bound.apply_defaults()
            cache_key = key_template.format(**bound.arguments)

            cache: CacheAside = getattr(
                self_or_first, "cache", None
            )
            if cache is None:
                return await func(self_or_first, *args, **kwargs)

            return await cache.get_or_set(
                key=cache_key,
                fetcher=lambda: func(self_or_first, *args, **kwargs),
                ttl=ttl,
                model_cls=model_cls,
            )
        return wrapper
    return decorator


# ── Usage Example ──────────────────────────────────────────────

class UserService:
    def __init__(self, db, cache: CacheAside):
        self.db = db
        self.cache = cache

    @cached("user:{user_id}", ttl=600)
    async def get_user(self, user_id: str) -> dict:
        return await self.db.fetch_one(
            "SELECT * FROM users WHERE id = $1", user_id
        )

    @cached("user:{user_id}:orders", ttl=120)
    async def get_user_orders(self, user_id: str) -> list:
        return await self.db.fetch_all(
            "SELECT * FROM orders WHERE customer_id = $1 "
            "ORDER BY created_at DESC LIMIT 50", user_id,
        )

    async def update_user(self, user_id: str, data: dict) -> dict:
        result = await self.db.execute(
            "UPDATE users SET name=$2, email=$3 WHERE id=$1",
            user_id, data["name"], data["email"],
        )
        # Invalidate related caches
        await self.cache.delete(f"user:{user_id}")
        await self.cache.invalidate_pattern(f"user:{user_id}:*")
        return result
```

Cache-aside flow:

| Step | Action | On Hit | On Miss |
|------|--------|--------|---------|
| 1 | Check cache | Return cached value | Continue to step 2 |
| 2 | Acquire lock | N/A | Lock acquired or serve stale |
| 3 | Fetch from DB | N/A | Execute query |
| 4 | Populate cache | N/A | SET with TTL |
| 5 | Release lock | N/A | DELETE lock key |

Key patterns:
- Always check cache first, then DB, then populate cache (lazy loading)
- Use distributed locks (SETNX) to prevent cache stampedes when many requests miss simultaneously
- Keep stale copies with extended TTL to serve during refresh (stale-while-revalidate)
- Use pipeline (multi) for atomic cache + stale key updates
- Track hit/miss/error rates as metrics for cache tuning
- Invalidate on write operations and cascade to related cache keys with pattern matching
'''
    ),
    (
        "caching/write-through-write-behind",
        "How do I implement write-through and write-behind caching patterns in Python, and when should I use each?",
        '''Write-through writes to both cache and database synchronously, guaranteeing consistency. Write-behind (write-back) writes to cache immediately and asynchronously flushes to the database, trading consistency for lower latency.

```python
"""Write-through and write-behind caching implementations."""

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from datetime import datetime, timezone

import redis.asyncio as redis
import asyncpg

logger = logging.getLogger(__name__)


# ── Write-Through Cache ───────────────────────────────────────

class WriteThroughCache:
    """Writes to cache and database synchronously.

    Guarantees: Cache always reflects DB state.
    Trade-off: Higher write latency (DB + cache on every write).
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        pool: asyncpg.Pool,
        prefix: str = "wt",
        ttl: int = 3600,
    ):
        self.redis = redis_client
        self.pool = pool
        self.prefix = prefix
        self.ttl = ttl

    def _key(self, entity: str, entity_id: str) -> str:
        return f"{self.prefix}:{entity}:{entity_id}"

    async def read(
        self, entity: str, entity_id: str
    ) -> dict | None:
        """Read from cache first, fallback to DB."""
        cache_key = self._key(entity, entity_id)
        raw = await self.redis.get(cache_key)

        if raw:
            return json.loads(raw)

        # Cache miss -- read from DB and populate
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT * FROM {entity} WHERE id = $1", entity_id
            )

        if row:
            data = dict(row)
            await self.redis.setex(
                cache_key, self.ttl, json.dumps(data, default=str)
            )
            return data
        return None

    async def write(
        self, entity: str, entity_id: str, data: dict
    ) -> dict:
        """Write to DB first, then cache (synchronous)."""
        cache_key = self._key(entity, entity_id)

        # Build upsert query
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ", ".join(f"${i+1}" for i in range(len(values)))
        col_list = ", ".join(columns)
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in columns if c != "id"
        )

        async with self.pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {entity} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT (id) DO UPDATE SET {updates}",
                *values,
            )

        # Then update cache (after DB succeeds)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.setex(
            cache_key, self.ttl, json.dumps(data, default=str)
        )

        logger.debug("Write-through: %s/%s written", entity, entity_id)
        return data

    async def delete(self, entity: str, entity_id: str) -> None:
        """Delete from DB first, then cache."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"DELETE FROM {entity} WHERE id = $1", entity_id
            )
        await self.redis.delete(self._key(entity, entity_id))


# ── Write-Behind (Write-Back) Cache ───────────────────────────

@dataclass
class PendingWrite:
    entity: str
    entity_id: str
    data: dict
    timestamp: float = field(default_factory=time.monotonic)
    attempts: int = 0


class WriteBehindCache:
    """Writes to cache immediately, flushes to DB asynchronously.

    Guarantees: Low write latency, eventual consistency.
    Trade-off: Data loss risk if process crashes before flush.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        pool: asyncpg.Pool,
        prefix: str = "wb",
        ttl: int = 3600,
        flush_interval: float = 1.0,
        batch_size: int = 50,
        max_retries: int = 3,
    ):
        self.redis = redis_client
        self.pool = pool
        self.prefix = prefix
        self.ttl = ttl
        self.flush_interval = flush_interval
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._pending: deque[PendingWrite] = deque()
        self._flush_task: asyncio.Task | None = None
        self._running = False
        self._dirty_keys_set = f"{prefix}:dirty"

    def _key(self, entity: str, entity_id: str) -> str:
        return f"{self.prefix}:{entity}:{entity_id}"

    async def start(self) -> None:
        """Start the background flush loop."""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("Write-behind flush loop started")

    async def stop(self) -> None:
        """Stop the flush loop and drain remaining writes."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        # Final flush
        await self._flush_batch()
        logger.info("Write-behind stopped, %d pending", len(self._pending))

    async def read(
        self, entity: str, entity_id: str
    ) -> dict | None:
        """Read from cache (includes pending writes)."""
        cache_key = self._key(entity, entity_id)
        raw = await self.redis.get(cache_key)
        if raw:
            return json.loads(raw)
        return None

    async def write(
        self, entity: str, entity_id: str, data: dict
    ) -> dict:
        """Write to cache immediately, queue DB write."""
        cache_key = self._key(entity, entity_id)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # 1. Write to cache immediately (fast path)
        serialized = json.dumps(data, default=str)
        pipe = self.redis.pipeline()
        pipe.setex(cache_key, self.ttl, serialized)
        # Track dirty keys for crash recovery
        pipe.sadd(
            self._dirty_keys_set,
            json.dumps({"entity": entity, "id": entity_id}),
        )
        await pipe.execute()

        # 2. Queue for async DB write
        self._pending.append(PendingWrite(
            entity=entity,
            entity_id=entity_id,
            data=data,
        ))

        return data

    async def _flush_loop(self) -> None:
        """Background loop that flushes pending writes to DB."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                if self._pending:
                    await self._flush_batch()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Flush loop error")

    async def _flush_batch(self) -> None:
        """Flush a batch of pending writes to the database."""
        if not self._pending:
            return

        batch: list[PendingWrite] = []
        while self._pending and len(batch) < self.batch_size:
            batch.append(self._pending.popleft())

        # Group by entity for batch upsert
        by_entity: dict[str, list[PendingWrite]] = {}
        for pw in batch:
            by_entity.setdefault(pw.entity, []).append(pw)

        failed: list[PendingWrite] = []

        for entity, writes in by_entity.items():
            try:
                async with self.pool.acquire() as conn:
                    async with conn.transaction():
                        for pw in writes:
                            columns = list(pw.data.keys())
                            values = list(pw.data.values())
                            placeholders = ", ".join(
                                f"${i+1}" for i in range(len(values))
                            )
                            col_list = ", ".join(columns)
                            updates = ", ".join(
                                f"{c} = EXCLUDED.{c}"
                                for c in columns if c != "id"
                            )

                            await conn.execute(
                                f"INSERT INTO {entity} ({col_list}) "
                                f"VALUES ({placeholders}) "
                                f"ON CONFLICT (id) DO UPDATE SET {updates}",
                                *values,
                            )

                # Remove from dirty set
                pipe = self.redis.pipeline()
                for pw in writes:
                    pipe.srem(
                        self._dirty_keys_set,
                        json.dumps({"entity": entity, "id": pw.entity_id}),
                    )
                await pipe.execute()

                logger.debug(
                    "Flushed %d writes for %s", len(writes), entity
                )
            except Exception as exc:
                logger.error(
                    "Flush failed for %s: %s", entity, exc
                )
                for pw in writes:
                    pw.attempts += 1
                    if pw.attempts < self.max_retries:
                        failed.append(pw)
                    else:
                        logger.error(
                            "Permanently failed write: %s/%s after %d attempts",
                            pw.entity, pw.entity_id, pw.attempts,
                        )

        # Re-queue failed writes
        for pw in failed:
            self._pending.appendleft(pw)

    async def recover_dirty(self) -> int:
        """Recover writes from dirty set after crash."""
        dirty = await self.redis.smembers(self._dirty_keys_set)
        count = 0
        for raw in dirty:
            info = json.loads(raw)
            cache_key = self._key(info["entity"], info["id"])
            cached = await self.redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                self._pending.append(PendingWrite(
                    entity=info["entity"],
                    entity_id=info["id"],
                    data=data,
                ))
                count += 1
        if count:
            logger.info("Recovered %d dirty writes", count)
            await self._flush_batch()
        return count


# ── Refresh-Ahead Cache ───────────────────────────────────────

class RefreshAheadCache:
    """Proactively refreshes cache entries before they expire.

    Prevents cache misses entirely for hot keys.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "ra",
        ttl: int = 300,
        refresh_threshold: float = 0.8,
    ):
        self.redis = redis_client
        self.prefix = prefix
        self.ttl = ttl
        self.refresh_at = int(ttl * refresh_threshold)
        self._refresh_tasks: dict[str, asyncio.Task] = {}

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
    ) -> Any:
        cache_key = self._key(key)
        raw = await self.redis.get(cache_key)

        if raw:
            # Check remaining TTL
            remaining = await self.redis.ttl(cache_key)
            threshold = self.ttl - self.refresh_at

            if remaining > 0 and remaining < threshold:
                # Schedule background refresh
                if key not in self._refresh_tasks:
                    self._refresh_tasks[key] = asyncio.create_task(
                        self._refresh(key, fetcher)
                    )

            return json.loads(raw)

        # Cache miss -- fetch synchronously
        value = await fetcher()
        await self.redis.setex(
            cache_key, self.ttl, json.dumps(value, default=str)
        )
        return value

    async def _refresh(
        self, key: str, fetcher: Callable[[], Awaitable[Any]]
    ) -> None:
        try:
            value = await fetcher()
            await self.redis.setex(
                self._key(key), self.ttl,
                json.dumps(value, default=str),
            )
            logger.debug("Refresh-ahead: refreshed %s", key)
        except Exception:
            logger.warning("Refresh-ahead failed for %s", key)
        finally:
            self._refresh_tasks.pop(key, None)
```

Caching pattern comparison:

| Pattern | Write Latency | Read Latency | Consistency | Data Loss Risk |
|---------|--------------|-------------|-------------|----------------|
| Cache-Aside | N/A (no cache write on write) | Low (on hit) | Manual invalidation | None |
| Write-Through | Higher (DB + cache) | Low | Strong | None |
| Write-Behind | Lowest (cache only) | Low | Eventual | Yes (crash) |
| Refresh-Ahead | N/A | Lowest (always warm) | Eventual | None |

Key patterns:
- Write-through: write DB first, then cache -- if cache write fails, data is still safe in DB
- Write-behind: write cache first, batch-flush to DB -- track dirty keys for crash recovery
- Use a dirty key set in Redis to recover unwritten data after process crashes
- Write-behind batches reduce DB load but risk data loss during outages
- Refresh-ahead eliminates cache misses for hot keys by refreshing before TTL expires
- Choose based on your consistency requirements and acceptable write latency
'''
    ),
    (
        "caching/distributed-cache-redis",
        "How do I implement a distributed caching layer with Redis, including multi-level caching (L1/L2), cache warming, and proper connection management?",
        '''A multi-level cache combines a fast in-process L1 cache with a shared Redis L2 cache for optimal performance. L1 eliminates network roundtrips for hot keys, while L2 provides shared state across instances.

```python
"""Multi-level distributed cache with L1 (in-process) + L2 (Redis)."""

import asyncio
import json
import time
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Generic, TypeVar
from threading import Lock

import redis.asyncio as redis
from redis.asyncio.sentinel import Sentinel

logger = logging.getLogger(__name__)
T = TypeVar("T")


# ── L1: In-Process LRU Cache ──────────────────────────────────

class L1Cache:
    """Thread-safe in-process LRU cache with TTL."""

    def __init__(self, max_size: int = 1000, default_ttl: float = 60.0):
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None

            value, expires_at = self._store[key]
            if time.monotonic() > expires_at:
                del self._store[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._store.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        ttl = ttl or self._default_ttl
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, time.monotonic() + ttl)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._store),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0,
        }


# ── L2: Redis Distributed Cache ───────────────────────────────

class L2Cache:
    """Redis-backed distributed cache with connection pooling."""

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "l2",
        default_ttl: int = 300,
    ):
        self.redis = redis_client
        self.prefix = prefix
        self.default_ttl = default_ttl

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Any | None:
        raw = await self.redis.get(self._key(key))
        if raw:
            return json.loads(raw)
        return None

    async def set(
        self, key: str, value: Any, ttl: int | None = None
    ) -> None:
        ttl = ttl or self.default_ttl
        serialized = json.dumps(value, default=str)
        await self.redis.setex(self._key(key), ttl, serialized)

    async def delete(self, key: str) -> None:
        await self.redis.delete(self._key(key))

    async def mget(self, keys: list[str]) -> dict[str, Any]:
        if not keys:
            return {}
        cache_keys = [self._key(k) for k in keys]
        values = await self.redis.mget(cache_keys)
        result = {}
        for key, raw in zip(keys, values):
            if raw:
                result[key] = json.loads(raw)
        return result

    async def mset(
        self, items: dict[str, Any], ttl: int | None = None
    ) -> None:
        ttl = ttl or self.default_ttl
        pipe = self.redis.pipeline()
        for key, value in items.items():
            pipe.setex(
                self._key(key), ttl, json.dumps(value, default=str)
            )
        await pipe.execute()


# ── Multi-Level Cache ──────────────────────────────────────────

class MultiLevelCache:
    """L1 (in-process) + L2 (Redis) multi-level cache."""

    def __init__(
        self,
        l2_redis: redis.Redis,
        l1_max_size: int = 1000,
        l1_ttl: float = 30.0,
        l2_ttl: int = 300,
        prefix: str = "ml",
    ):
        self.l1 = L1Cache(max_size=l1_max_size, default_ttl=l1_ttl)
        self.l2 = L2Cache(l2_redis, prefix=prefix, default_ttl=l2_ttl)
        self._pubsub = l2_redis.pubsub()
        self._invalidation_channel = f"{prefix}:invalidate"
        self._listener_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start listening for cross-instance invalidation."""
        await self._pubsub.subscribe(self._invalidation_channel)
        self._listener_task = asyncio.create_task(
            self._listen_invalidations()
        )

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        await self._pubsub.unsubscribe(self._invalidation_channel)

    async def get(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]] | None = None,
        l1_ttl: float | None = None,
        l2_ttl: int | None = None,
    ) -> Any | None:
        # Level 1: In-process check (no network call)
        value = self.l1.get(key)
        if value is not None:
            return value

        # Level 2: Redis check
        value = await self.l2.get(key)
        if value is not None:
            self.l1.set(key, value, l1_ttl)
            return value

        # Both miss: fetch from source
        if fetcher:
            value = await fetcher()
            if value is not None:
                await self.set(key, value, l1_ttl, l2_ttl)
            return value

        return None

    async def set(
        self,
        key: str,
        value: Any,
        l1_ttl: float | None = None,
        l2_ttl: int | None = None,
    ) -> None:
        self.l1.set(key, value, l1_ttl)
        await self.l2.set(key, value, l2_ttl)

    async def delete(self, key: str) -> None:
        """Delete from both levels and notify other instances."""
        self.l1.delete(key)
        await self.l2.delete(key)
        # Publish invalidation for other instances
        await self.l2.redis.publish(
            self._invalidation_channel, key
        )

    async def _listen_invalidations(self) -> None:
        """Listen for invalidation messages from other instances."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    key = message["data"]
                    if isinstance(key, bytes):
                        key = key.decode()
                    self.l1.delete(key)
                    logger.debug("L1 invalidated via pub/sub: %s", key)
        except asyncio.CancelledError:
            pass

    @property
    def stats(self) -> dict:
        return {"l1": self.l1.stats}


# ── Redis Connection Factory ──────────────────────────────────

class RedisConnectionFactory:
    """Creates Redis connections with proper pooling and failover."""

    @staticmethod
    async def create_standalone(
        url: str = "redis://localhost:6379",
        max_connections: int = 20,
        socket_timeout: float = 5.0,
        decode_responses: bool = True,
    ) -> redis.Redis:
        pool = redis.ConnectionPool.from_url(
            url,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=3.0,
            retry_on_timeout=True,
            decode_responses=decode_responses,
        )
        client = redis.Redis(connection_pool=pool)
        await client.ping()
        return client

    @staticmethod
    async def create_sentinel(
        sentinels: list[tuple[str, int]],
        master_name: str = "mymaster",
        password: str | None = None,
        db: int = 0,
    ) -> redis.Redis:
        sentinel = Sentinel(
            sentinels,
            socket_timeout=5.0,
            password=password,
        )
        master = sentinel.master_for(
            master_name,
            redis_class=redis.Redis,
            db=db,
            decode_responses=True,
        )
        await master.ping()
        return master

    @staticmethod
    async def create_cluster(
        nodes: list[dict[str, Any]],
    ) -> redis.RedisCluster:
        client = redis.RedisCluster(
            startup_nodes=[
                redis.cluster.ClusterNode(**n) for n in nodes
            ],
            decode_responses=True,
            skip_full_coverage_check=True,
        )
        await client.ping()
        return client


# ── Cache Warmer ───────────────────────────────────────────────

class CacheWarmer:
    """Pre-populates cache with frequently accessed data."""

    def __init__(self, cache: MultiLevelCache):
        self.cache = cache
        self._warmers: list[tuple[str, Callable]] = []

    def register(
        self,
        name: str,
        fetcher: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        """Register a data source for warming."""
        self._warmers.append((name, fetcher))

    async def warm_all(self) -> dict[str, int]:
        """Run all registered warmers."""
        results = {}
        for name, fetcher in self._warmers:
            try:
                data = await fetcher()
                for key, value in data.items():
                    await self.cache.set(key, value)
                results[name] = len(data)
                logger.info("Warmed %d keys for %s", len(data), name)
            except Exception:
                logger.exception("Warmer %s failed", name)
                results[name] = 0
        return results

    async def warm_on_schedule(
        self, interval_seconds: int = 300
    ) -> None:
        """Periodically warm the cache."""
        while True:
            await self.warm_all()
            await asyncio.sleep(interval_seconds)
```

Multi-level cache architecture:

| Level | Storage | Latency | Shared | Capacity |
|-------|---------|---------|--------|----------|
| L1 | In-process dict | ~1us | No (per instance) | Small (1K-10K keys) |
| L2 | Redis | ~1ms | Yes (all instances) | Large (millions) |
| L3 (source) | PostgreSQL | ~5-50ms | Yes | Unlimited |

Key patterns:
- L1 eliminates network calls for the hottest keys (microsecond access)
- L2 provides shared state across application instances via Redis
- Use Redis pub/sub for cross-instance L1 invalidation when data changes
- Keep L1 TTL short (30s) to limit staleness, L2 TTL longer (5min)
- Cache warmers pre-populate keys during startup or on schedule
- Use Redis Sentinel or Cluster for high availability in production
- Connection pooling (max_connections) prevents creating too many TCP connections
'''
    ),
    (
        "caching/cache-invalidation",
        "What are the best strategies for cache invalidation, and how do I implement tag-based invalidation, event-driven invalidation, and TTL-based expiration?",
        '''Cache invalidation is famously one of the hardest problems in computer science. Here are battle-tested strategies ranging from simple TTL to sophisticated tag-based and event-driven invalidation.

```python
"""Cache invalidation strategies: TTL, tag-based, event-driven, versioned."""

import asyncio
import json
import time
import hashlib
import logging
from typing import Any, Callable, Awaitable
from dataclasses import dataclass

import redis.asyncio as redis

logger = logging.getLogger(__name__)


# ── Strategy 1: Tag-Based Invalidation ─────────────────────────

class TagBasedCache:
    """Cache with tag-based invalidation.

    Each cache entry can be tagged with multiple tags. Invalidating
    a tag removes all entries associated with it.

    Example: tag "user:123" on all caches related to user 123.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "tbc",
        default_ttl: int = 300,
    ):
        self.redis = redis_client
        self.prefix = prefix
        self.default_ttl = default_ttl

    def _key(self, key: str) -> str:
        return f"{self.prefix}:data:{key}"

    def _tag_key(self, tag: str) -> str:
        return f"{self.prefix}:tag:{tag}"

    def _tags_for_key(self, key: str) -> str:
        return f"{self.prefix}:key_tags:{key}"

    async def get(self, key: str) -> Any | None:
        raw = await self.redis.get(self._key(key))
        if raw is None:
            return None
        return json.loads(raw)

    async def set(
        self,
        key: str,
        value: Any,
        tags: list[str] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Set a cache entry with optional tags."""
        ttl = ttl or self.default_ttl
        cache_key = self._key(key)
        serialized = json.dumps(value, default=str)

        pipe = self.redis.pipeline()
        pipe.setex(cache_key, ttl, serialized)

        if tags:
            # Store the key in each tag's set
            for tag in tags:
                pipe.sadd(self._tag_key(tag), key)
                pipe.expire(self._tag_key(tag), ttl + 60)

            # Store which tags this key belongs to
            pipe.sadd(self._tags_for_key(key), *tags)
            pipe.expire(self._tags_for_key(key), ttl + 60)

        await pipe.execute()

    async def invalidate_tag(self, tag: str) -> int:
        """Invalidate all cache entries with a given tag."""
        tag_key = self._tag_key(tag)
        keys = await self.redis.smembers(tag_key)

        if not keys:
            return 0

        pipe = self.redis.pipeline()
        for key in keys:
            if isinstance(key, bytes):
                key = key.decode()
            pipe.delete(self._key(key))
            pipe.delete(self._tags_for_key(key))
        pipe.delete(tag_key)
        await pipe.execute()

        count = len(keys)
        logger.info("Invalidated %d entries for tag '%s'", count, tag)
        return count

    async def invalidate_tags(self, tags: list[str]) -> int:
        """Invalidate multiple tags at once."""
        total = 0
        for tag in tags:
            total += await self.invalidate_tag(tag)
        return total


# Usage example:
# await cache.set(
#     "user:123:profile", user_data,
#     tags=["user:123", "profiles"]
# )
# await cache.set(
#     "user:123:orders", orders,
#     tags=["user:123", "orders"]
# )
# # Invalidate everything related to user 123:
# await cache.invalidate_tag("user:123")


# ── Strategy 2: Version-Based Invalidation ─────────────────────

class VersionedCache:
    """Cache using version numbers for instant invalidation.

    Instead of deleting keys, increment a version counter.
    Old cached data becomes unreachable with the new version.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "vc",
        default_ttl: int = 300,
    ):
        self.redis = redis_client
        self.prefix = prefix
        self.default_ttl = default_ttl

    def _version_key(self, namespace: str) -> str:
        return f"{self.prefix}:ver:{namespace}"

    async def _get_version(self, namespace: str) -> int:
        ver = await self.redis.get(self._version_key(namespace))
        return int(ver) if ver else 0

    def _data_key(self, namespace: str, key: str, version: int) -> str:
        return f"{self.prefix}:{namespace}:v{version}:{key}"

    async def get(self, namespace: str, key: str) -> Any | None:
        version = await self._get_version(namespace)
        data_key = self._data_key(namespace, key, version)
        raw = await self.redis.get(data_key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(
        self, namespace: str, key: str, value: Any,
        ttl: int | None = None,
    ) -> None:
        ttl = ttl or self.default_ttl
        version = await self._get_version(namespace)
        data_key = self._data_key(namespace, key, version)
        await self.redis.setex(
            data_key, ttl, json.dumps(value, default=str)
        )

    async def invalidate_namespace(self, namespace: str) -> int:
        """Increment version -- all old keys become unreachable."""
        new_version = await self.redis.incr(
            self._version_key(namespace)
        )
        logger.info(
            "Namespace '%s' bumped to version %d",
            namespace, new_version,
        )
        return new_version


# ── Strategy 3: Event-Driven Invalidation ──────────────────────

@dataclass
class InvalidationEvent:
    entity_type: str
    entity_id: str
    action: str  # "created", "updated", "deleted"
    related_tags: list[str]
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class EventDrivenInvalidator:
    """Invalidates cache entries based on domain events."""

    def __init__(
        self,
        redis_client: redis.Redis,
        cache: TagBasedCache,
    ):
        self.redis = redis_client
        self.cache = cache
        self._rules: dict[str, list[Callable]] = {}
        self._channel = "cache:invalidation"

    def on_change(
        self,
        entity_type: str,
        handler: Callable[[InvalidationEvent], Awaitable[None]],
    ) -> None:
        """Register an invalidation handler for an entity type."""
        self._rules.setdefault(entity_type, []).append(handler)

    async def notify(self, event: InvalidationEvent) -> None:
        """Process an invalidation event."""
        # Invalidate by tags
        if event.related_tags:
            await self.cache.invalidate_tags(event.related_tags)

        # Run custom handlers
        handlers = self._rules.get(event.entity_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Invalidation handler failed for %s",
                    event.entity_type,
                )

        # Publish for distributed invalidation
        await self.redis.publish(
            self._channel,
            json.dumps({
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "action": event.action,
                "tags": event.related_tags,
                "timestamp": event.timestamp,
            }),
        )

    async def listen(self) -> None:
        """Listen for invalidation events from other instances."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self._channel)

        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                event = InvalidationEvent(
                    entity_type=data["entity_type"],
                    entity_id=data["entity_id"],
                    action=data["action"],
                    related_tags=data["tags"],
                    timestamp=data["timestamp"],
                )
                # Only run tag invalidation (not handlers, to avoid loops)
                if event.related_tags:
                    await self.cache.invalidate_tags(event.related_tags)


# ── Strategy 4: Content-Hash Invalidation ──────────────────────

class ContentHashCache:
    """Cache using content hashes -- automatically invalidates
    when content changes.

    The cache key includes a hash of the query/parameters,
    and a version derived from the last modification timestamp.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "chc",
        default_ttl: int = 3600,
    ):
        self.redis = redis_client
        self.prefix = prefix
        self.default_ttl = default_ttl

    def _content_key(
        self, entity: str, query_hash: str, mod_time: str
    ) -> str:
        return f"{self.prefix}:{entity}:{query_hash}:{mod_time}"

    @staticmethod
    def hash_query(query: str, params: tuple) -> str:
        raw = f"{query}:{json.dumps(params, default=str)}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    async def get_with_etag(
        self,
        entity: str,
        query: str,
        params: tuple,
        get_mod_time: Callable[[], Awaitable[str]],
    ) -> tuple[Any | None, str]:
        """Get cached result, using modification time as version."""
        mod_time = await get_mod_time()
        query_hash = self.hash_query(query, params)
        key = self._content_key(entity, query_hash, mod_time)

        raw = await self.redis.get(key)
        if raw:
            return json.loads(raw), mod_time
        return None, mod_time

    async def set_with_etag(
        self,
        entity: str,
        query: str,
        params: tuple,
        mod_time: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        query_hash = self.hash_query(query, params)
        key = self._content_key(entity, query_hash, mod_time)
        ttl = ttl or self.default_ttl
        await self.redis.setex(
            key, ttl, json.dumps(value, default=str)
        )


# ── Putting It All Together ────────────────────────────────────

class CacheManager:
    """Unified cache manager with multiple invalidation strategies."""

    def __init__(self, redis_client: redis.Redis):
        self.tag_cache = TagBasedCache(redis_client)
        self.versioned_cache = VersionedCache(redis_client)
        self.invalidator = EventDrivenInvalidator(
            redis_client, self.tag_cache
        )
        self._setup_invalidation_rules()

    def _setup_invalidation_rules(self) -> None:
        async def on_user_change(event: InvalidationEvent):
            await self.versioned_cache.invalidate_namespace(
                f"user:{event.entity_id}"
            )

        async def on_order_change(event: InvalidationEvent):
            await self.versioned_cache.invalidate_namespace("orders")

        self.invalidator.on_change("user", on_user_change)
        self.invalidator.on_change("order", on_order_change)

    async def on_entity_updated(
        self, entity_type: str, entity_id: str, action: str = "updated"
    ) -> None:
        """Call this when any entity is modified."""
        await self.invalidator.notify(InvalidationEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            related_tags=[
                f"{entity_type}:{entity_id}",
                entity_type,
            ],
        ))
```

Cache invalidation strategy comparison:

| Strategy | Complexity | Precision | Latency | Best For |
|----------|-----------|-----------|---------|----------|
| TTL-based | Lowest | Coarse | Zero (auto) | Frequently refreshed data |
| Tag-based | Medium | Fine | Low | Related entity graphs |
| Version-based | Low | Namespace | Instant | Bulk invalidation |
| Event-driven | Higher | Precise | Low | Microservices |
| Content-hash | Medium | Exact | Zero (auto) | Query result caching |

Key patterns:
- TTL is your safety net -- always set a TTL even with explicit invalidation
- Tag-based invalidation groups related cache entries so one change cascades correctly
- Version-based invalidation is instant: increment a counter and all old keys are orphaned
- Event-driven invalidation uses pub/sub for cross-instance cache coherence
- Content-hash caching uses modification timestamps as part of the key -- no explicit invalidation needed
- Combine strategies: use tags for precision and TTL as a fallback for missed invalidations
'''
    ),
]
