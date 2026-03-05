PAIRS = [
    (
        "databases/redis-data-structures",
        r"""Explain Redis data structures beyond simple key-value including Sorted Sets for leaderboards, Streams for event sourcing, HyperLogLog for cardinality estimation, Bitmaps for feature flags, and Pub/Sub patterns. Include practical Python implementations.""",
        r"""## Redis Data Structures: Sorted Sets, Streams, HyperLogLog, and Beyond

Redis is often reduced to "a cache," but its data structures solve problems that would require multiple external systems. Understanding when to use each structure is the key to effective Redis usage.

### Sorted Sets for Leaderboards and Rankings

Sorted sets combine set uniqueness with score-based ordering. Operations are O(log N):

```python
import redis
from datetime import datetime, timezone
from typing import Optional


class Leaderboard:
    """Real-time leaderboard using Redis sorted sets."""

    def __init__(self, client: redis.Redis, name: str):
        self.r = client
        self.key = f"leaderboard:{name}"

    def update_score(self, user_id: str, score: float):
        """Add or update a user's score."""
        self.r.zadd(self.key, {user_id: score})

    def increment_score(self, user_id: str, delta: float) -> float:
        """Atomically increment a score. Returns new score."""
        return self.r.zincrby(self.key, delta, user_id)

    def get_rank(self, user_id: str) -> Optional[int]:
        """Get user's rank (0-indexed, highest score = rank 0)."""
        rank = self.r.zrevrank(self.key, user_id)
        return rank  # None if user not found

    def get_top(self, count: int = 10) -> list[tuple[str, float]]:
        """Get top N users with scores."""
        return self.r.zrevrange(
            self.key, 0, count - 1, withscores=True
        )

    def get_around_user(self, user_id: str, count: int = 5) -> list:
        """Get users around a specific user (for context)."""
        rank = self.r.zrevrank(self.key, user_id)
        if rank is None:
            return []
        start = max(0, rank - count // 2)
        end = rank + count // 2
        return self.r.zrevrange(self.key, start, end, withscores=True)

    def get_score(self, user_id: str) -> Optional[float]:
        return self.r.zscore(self.key, user_id)

    def total_players(self) -> int:
        return self.r.zcard(self.key)


# Usage
r = redis.Redis(decode_responses=True)
lb = Leaderboard(r, "weekly")
lb.update_score("alice", 1500)
lb.update_score("bob", 1350)
lb.increment_score("alice", 50)  # Alice now at 1550
top_10 = lb.get_top(10)
# [('alice', 1550.0), ('bob', 1350.0)]
```

### Streams for Event Sourcing

Redis Streams are an append-only log with consumer groups — like a lightweight Kafka:

```python
import redis
import json
from dataclasses import dataclass, asdict
from typing import Optional
import time


@dataclass
class Event:
    type: str
    data: dict
    timestamp: float = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class EventStream:
    """Event sourcing with Redis Streams and consumer groups."""

    def __init__(self, client: redis.Redis, stream: str):
        self.r = client
        self.stream = stream

    def publish(self, event: Event) -> str:
        """Publish an event. Returns the event ID."""
        entry = {
            "type": event.type,
            "data": json.dumps(event.data),
            "timestamp": str(event.timestamp),
        }
        return self.r.xadd(self.stream, entry, maxlen=100000)

    def create_consumer_group(self, group: str, start_id: str = "0"):
        """Create a consumer group (idempotent)."""
        try:
            self.r.xgroup_create(self.stream, group, id=start_id, mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    def consume(
        self,
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[tuple[str, Event]]:
        """Read new events from the consumer group."""
        results = self.r.xreadgroup(
            group, consumer,
            {self.stream: ">"},  # ">" means only new messages
            count=count,
            block=block_ms,
        )
        if not results:
            return []

        events = []
        for stream_name, messages in results:
            for msg_id, fields in messages:
                event = Event(
                    type=fields["type"],
                    data=json.loads(fields["data"]),
                    timestamp=float(fields["timestamp"]),
                )
                events.append((msg_id, event))
        return events

    def acknowledge(self, group: str, *message_ids: str):
        """Acknowledge processed messages."""
        self.r.xack(self.stream, group, *message_ids)

    def get_pending(self, group: str) -> list:
        """Get messages that were delivered but not acknowledged."""
        return self.r.xpending_range(
            self.stream, group, min="-", max="+", count=100
        )

    def claim_stale(
        self, group: str, consumer: str, min_idle_ms: int = 60000
    ) -> list:
        """Claim messages that another consumer failed to process."""
        pending = self.r.xpending_range(
            self.stream, group, min="-", max="+", count=10
        )
        stale_ids = [
            p["message_id"] for p in pending
            if p["time_since_delivered"] > min_idle_ms
        ]
        if not stale_ids:
            return []
        return self.r.xclaim(
            self.stream, group, consumer,
            min_idle_time=min_idle_ms,
            message_ids=stale_ids,
        )


# Usage:
stream = EventStream(r, "orders")
stream.create_consumer_group("payment-processors")

# Publisher
stream.publish(Event("order.created", {"order_id": "123", "total": 99.99}))

# Consumer (run in a loop)
events = stream.consume("payment-processors", "worker-1")
for msg_id, event in events:
    process_payment(event)
    stream.acknowledge("payment-processors", msg_id)
```

### HyperLogLog for Cardinality Estimation

Count unique items with O(1) memory (~12KB regardless of set size):

```python
class UniqueVisitorCounter:
    """Count unique visitors with HyperLogLog — O(1) memory."""

    def __init__(self, client: redis.Redis):
        self.r = client

    def record_visit(self, page: str, visitor_id: str):
        key = f"visitors:{page}:{self._today()}"
        self.r.pfadd(key, visitor_id)
        # Set expiry for auto-cleanup
        self.r.expire(key, 86400 * 7)  # Keep 7 days

    def unique_visitors(self, page: str, date: str = None) -> int:
        date = date or self._today()
        return self.r.pfcount(f"visitors:{page}:{date}")

    def unique_visitors_range(self, page: str, dates: list[str]) -> int:
        """Merge multiple days for total unique visitors."""
        keys = [f"visitors:{page}:{d}" for d in dates]
        # Merge into temporary key
        tmp_key = f"visitors:{page}:merged:{hash(tuple(dates))}"
        self.r.pfmerge(tmp_key, *keys)
        count = self.r.pfcount(tmp_key)
        self.r.delete(tmp_key)
        return count

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# Usage:
counter = UniqueVisitorCounter(r)
# Record 1 million visits
for visitor_id in range(1_000_000):
    counter.record_visit("/home", f"user-{visitor_id % 50000}")

# Approximate count (within 0.81% error)
print(counter.unique_visitors("/home"))  # ~50000
# Memory used: ~12KB (vs ~400KB for a Set of 50K strings)
```

### Bitmaps for Feature Flags and Presence

```python
class FeatureFlags:
    """Bit-level feature flags — millions of users in bytes."""

    def __init__(self, client: redis.Redis):
        self.r = client

    def enable(self, feature: str, user_id: int):
        self.r.setbit(f"feature:{feature}", user_id, 1)

    def disable(self, feature: str, user_id: int):
        self.r.setbit(f"feature:{feature}", user_id, 0)

    def is_enabled(self, feature: str, user_id: int) -> bool:
        return bool(self.r.getbit(f"feature:{feature}", user_id))

    def enabled_count(self, feature: str) -> int:
        """Count users with this feature enabled."""
        return self.r.bitcount(f"feature:{feature}")

    def users_with_all(self, *features: str) -> int:
        """Count users that have ALL features enabled (AND)."""
        dest = f"feature:intersection:{':'.join(features)}"
        keys = [f"feature:{f}" for f in features]
        self.r.bitop("AND", dest, *keys)
        count = self.r.bitcount(dest)
        self.r.delete(dest)
        return count


# Usage:
flags = FeatureFlags(r)
flags.enable("dark_mode", user_id=42)
flags.enable("dark_mode", user_id=100)
flags.enable("beta_ui", user_id=42)

# Check flag
flags.is_enabled("dark_mode", 42)  # True

# Count: how many users have dark_mode?
flags.enabled_count("dark_mode")  # 2

# Memory: 1 million users = 125KB per feature
# (1 bit per user, vs 8+ bytes per user in a Set)
```

### Rate Limiting with Sliding Window

```python
class SlidingWindowRateLimiter:
    """Rate limiter using sorted sets for precise sliding windows."""

    def __init__(self, client: redis.Redis):
        self.r = client

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, remaining)."""
        now = time.time()
        window_start = now - window_seconds
        pipe_key = f"ratelimit:{key}"

        # Use pipeline for atomicity
        pipe = self.r.pipeline()
        # Remove entries outside the window
        pipe.zremrangebyscore(pipe_key, 0, window_start)
        # Count entries in window
        pipe.zcard(pipe_key)
        # Add current request
        pipe.zadd(pipe_key, {f"{now}:{id(now)}": now})
        # Set expiry
        pipe.expire(pipe_key, window_seconds)
        results = pipe.execute()

        current_count = results[1]  # Count before adding
        remaining = max(0, max_requests - current_count - 1)
        allowed = current_count < max_requests

        if not allowed:
            # Remove the entry we just added
            self.r.zremrangebyscore(pipe_key, now, now)

        return allowed, remaining


# Usage:
limiter = SlidingWindowRateLimiter(r)
allowed, remaining = limiter.is_allowed(
    key=f"api:{user_id}",
    max_requests=100,
    window_seconds=60,
)
if not allowed:
    raise RateLimitExceeded(f"Rate limit exceeded. Try again later.")
```

**Redis data structure selection guide**: (1) **Strings**: simple cache, counters, locks, (2) **Sorted Sets**: leaderboards, priority queues, time-based windowing, (3) **Streams**: event sourcing, message queues with consumer groups, (4) **HyperLogLog**: unique counting (visitors, IPs) with ~0.8% error, (5) **Bitmaps**: boolean flags per user/entity — extreme memory efficiency, (6) **Hashes**: object storage, session data — avoid thousands of individual keys."""
    ),
    (
        "databases/redis-caching-patterns",
        r"""Explain Redis caching patterns including cache-aside, write-through, write-behind, cache invalidation strategies, distributed locking with Redlock, and cache stampede prevention. Include Python implementations with proper error handling.""",
        r"""## Redis Caching Patterns: Cache-Aside, Invalidation, Locks, and Stampede Prevention

Caching is simple in concept but notoriously hard to get right. The problems aren't in reading from cache — they're in keeping the cache consistent with the source of truth and handling failure modes.

### Cache-Aside (Lazy Loading)

The most common pattern — application manages cache explicitly:

```python
import redis
import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps


class CacheAside:
    """Cache-aside pattern with serialization and TTL."""

    def __init__(self, client: redis.Redis, prefix: str = "cache"):
        self.r = client
        self.prefix = prefix

    def get(self, key: str) -> Optional[Any]:
        raw = self.r.get(f"{self.prefix}:{key}")
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, key: str, value: Any, ttl: int = 300):
        self.r.setex(
            f"{self.prefix}:{key}",
            ttl,
            json.dumps(value, default=str),
        )

    def delete(self, key: str):
        self.r.delete(f"{self.prefix}:{key}")

    def get_or_set(
        self,
        key: str,
        factory: Callable,
        ttl: int = 300,
    ) -> Any:
        """Cache-aside in one call."""
        value = self.get(key)
        if value is not None:
            return value

        # Cache miss — fetch from source
        value = factory()
        if value is not None:
            self.set(key, value, ttl)
        return value


# Decorator version
def cached(cache: CacheAside, ttl: int = 300, key_prefix: str = ""):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from function name and arguments
            key_parts = [key_prefix or func.__qualname__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = hashlib.md5(
                ":".join(key_parts).encode()
            ).hexdigest()

            return cache.get_or_set(
                cache_key,
                lambda: func(*args, **kwargs),
                ttl,
            )
        wrapper.invalidate = lambda *a, **kw: cache.delete(
            hashlib.md5(":".join(
                [key_prefix or func.__qualname__] +
                [str(x) for x in a] +
                [f"{k}={v}" for k, v in sorted(kw.items())]
            ).encode()).hexdigest()
        )
        return wrapper
    return decorator


# Usage:
cache = CacheAside(redis.Redis(decode_responses=True))

@cached(cache, ttl=600)
def get_user_profile(user_id: int) -> dict:
    return db.query("SELECT * FROM users WHERE id = %s", user_id)

profile = get_user_profile(42)  # Cache miss → DB query
profile = get_user_profile(42)  # Cache hit
get_user_profile.invalidate(42)  # Clear cache
```

### Write-Through Cache

Updates go to both cache and database atomically:

```python
class WriteThroughCache:
    """Write-through: updates go to cache AND DB together."""

    def __init__(self, client: redis.Redis, db, prefix: str = "wt"):
        self.r = client
        self.db = db
        self.prefix = prefix

    async def get(self, entity: str, entity_id: str) -> Optional[dict]:
        key = f"{self.prefix}:{entity}:{entity_id}"
        cached = self.r.get(key)
        if cached:
            return json.loads(cached)

        # Cache miss: load from DB and populate cache
        record = await self.db.fetch_one(entity, entity_id)
        if record:
            self.r.setex(key, 3600, json.dumps(record, default=str))
        return record

    async def update(self, entity: str, entity_id: str, data: dict):
        """Update DB and cache together."""
        key = f"{self.prefix}:{entity}:{entity_id}"

        # Update DB first (source of truth)
        await self.db.update(entity, entity_id, data)

        # Then update cache
        # If cache update fails, it'll be stale but self-correcting
        # (TTL will expire, next read repopulates)
        try:
            record = await self.db.fetch_one(entity, entity_id)
            self.r.setex(key, 3600, json.dumps(record, default=str))
        except redis.RedisError:
            # Cache failure is acceptable — DB is the source of truth
            self.r.delete(key)  # Better to miss than serve stale data

    async def delete(self, entity: str, entity_id: str):
        key = f"{self.prefix}:{entity}:{entity_id}"
        await self.db.delete(entity, entity_id)
        self.r.delete(key)
```

### Cache Invalidation Strategies

```python
class CacheInvalidator:
    """Multiple invalidation strategies."""

    def __init__(self, client: redis.Redis):
        self.r = client

    # Strategy 1: Tag-based invalidation
    def set_with_tags(self, key: str, value: Any, tags: list[str], ttl: int = 300):
        pipe = self.r.pipeline()
        pipe.setex(f"c:{key}", ttl, json.dumps(value, default=str))
        for tag in tags:
            pipe.sadd(f"tag:{tag}", key)
            pipe.expire(f"tag:{tag}", ttl * 2)
        pipe.execute()

    def invalidate_tag(self, tag: str):
        """Invalidate all cache entries with this tag."""
        keys = self.r.smembers(f"tag:{tag}")
        if keys:
            pipe = self.r.pipeline()
            for key in keys:
                pipe.delete(f"c:{key}")
            pipe.delete(f"tag:{tag}")
            pipe.execute()

    # Strategy 2: Version-based invalidation
    def get_versioned(self, entity: str, entity_id: str) -> Optional[dict]:
        version = self.r.get(f"ver:{entity}") or "0"
        key = f"c:{entity}:{entity_id}:v{version}"
        raw = self.r.get(key)
        return json.loads(raw) if raw else None

    def bump_version(self, entity: str):
        """Increment version — all old cache entries become unreachable."""
        self.r.incr(f"ver:{entity}")

    # Strategy 3: Event-driven invalidation
    def publish_invalidation(self, entity: str, entity_id: str):
        """Publish cache invalidation event to all app instances."""
        self.r.publish("cache_invalidation", json.dumps({
            "entity": entity,
            "id": entity_id,
            "timestamp": time.time(),
        }))
```

### Distributed Locking with Redlock

```python
import redis
import uuid
import time


class DistributedLock:
    """Redis-based distributed lock (single instance)."""

    def __init__(self, client: redis.Redis):
        self.r = client

    def acquire(
        self,
        name: str,
        timeout: float = 10.0,
        blocking_timeout: float = 5.0,
    ) -> Optional[str]:
        """Acquire a distributed lock. Returns token or None."""
        token = str(uuid.uuid4())
        key = f"lock:{name}"
        end_time = time.monotonic() + blocking_timeout

        while time.monotonic() < end_time:
            # SET NX with expiry — atomic acquire
            if self.r.set(key, token, nx=True, ex=int(timeout)):
                return token
            time.sleep(0.05)  # Brief wait before retry

        return None  # Failed to acquire

    def release(self, name: str, token: str) -> bool:
        """Release lock only if we hold it (compare-and-delete)."""
        key = f"lock:{name}"
        # Lua script for atomic compare-and-delete
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        return bool(self.r.eval(script, 1, key, token))

    def extend(self, name: str, token: str, additional_time: float) -> bool:
        """Extend lock TTL if we still hold it."""
        key = f"lock:{name}"
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("pexpire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        return bool(self.r.eval(
            script, 1, key, token, int(additional_time * 1000)
        ))


# Context manager wrapper
from contextlib import contextmanager

@contextmanager
def distributed_lock(redis_client, name, timeout=10, blocking=5):
    lock = DistributedLock(redis_client)
    token = lock.acquire(name, timeout, blocking)
    if token is None:
        raise LockAcquisitionError(f"Could not acquire lock: {name}")
    try:
        yield token
    finally:
        lock.release(name, token)


# Usage:
with distributed_lock(r, "process-payments-batch"):
    process_pending_payments()
```

### Cache Stampede Prevention

When a popular cache key expires, hundreds of requests simultaneously hit the database:

```python
class StampedeProtectedCache:
    """Cache with stampede prevention using probabilistic early expiry."""

    def __init__(self, client: redis.Redis):
        self.r = client
        self.lock = DistributedLock(client)

    def get_or_set_protected(
        self,
        key: str,
        factory: Callable,
        ttl: int = 300,
        beta: float = 1.0,
    ) -> Any:
        """XFetch algorithm: probabilistic early recomputation."""
        raw = self.r.get(f"c:{key}")

        if raw:
            entry = json.loads(raw)
            value = entry["value"]
            expiry = entry["expiry"]
            delta = entry["delta"]  # Time to recompute

            # Probabilistic early expiry (XFetch)
            # As we approach expiry, there's an increasing chance
            # we'll recompute early — spreading the load
            now = time.time()
            remaining = expiry - now
            if remaining > 0:
                # Random chance of early recompute, increases as expiry nears
                import random, math
                threshold = delta * beta * math.log(random.random())
                if remaining + threshold > 0:
                    return value  # Serve from cache, no recompute

        # Cache miss or probabilistic early recompute
        # Use lock to prevent stampede
        token = self.lock.acquire(f"recompute:{key}", timeout=30, blocking_timeout=2)

        if token is None:
            # Another process is recomputing — serve stale if available
            if raw:
                return json.loads(raw)["value"]
            # No stale data, must wait
            time.sleep(0.5)
            return self.get_or_set_protected(key, factory, ttl, beta)

        try:
            start = time.time()
            value = factory()
            delta = time.time() - start  # Track computation time

            entry = {
                "value": value,
                "expiry": time.time() + ttl,
                "delta": delta,
            }
            self.r.setex(
                f"c:{key}",
                ttl + 60,  # Extra buffer for stale serving
                json.dumps(entry, default=str),
            )
            return value
        finally:
            self.lock.release(f"recompute:{key}", token)
```

**Caching rules**: (1) Cache-aside is the safest default — application controls consistency, (2) Always set TTL — unbounded caches grow until OOM, (3) Invalidate on write, don't wait for TTL — users expect immediate consistency, (4) Use distributed locks for expensive recomputations — prevent stampede, (5) Cache failures should degrade to slower DB queries, never errors — Redis down shouldn't mean app down."""
    ),
    (
        "databases/redis-operational-patterns",
        r"""Explain Redis operational patterns including memory management and eviction policies, persistence options (RDB vs AOF), replication and sentinel for HA, key naming conventions, and monitoring with INFO and SLOWLOG.""",
        r"""## Redis Operational Patterns: Memory, Persistence, HA, and Monitoring

Running Redis in production requires understanding memory management, data durability options, and monitoring. These operational patterns prevent data loss and performance degradation.

### Memory Management and Eviction

```bash
# Set maximum memory
# redis.conf
maxmemory 2gb

# Eviction policies (what to delete when memory is full):
maxmemory-policy allkeys-lru  # Evict least recently used (recommended for cache)

# Policy options:
# noeviction        — Return errors on writes (safe for data stores)
# allkeys-lru       — Evict LRU keys from all keys (best for cache)
# allkeys-lfu       — Evict least frequently used (better for skewed access)
# volatile-lru      — Evict LRU from keys with TTL set
# volatile-ttl      — Evict keys with shortest TTL
# allkeys-random    — Random eviction (unpredictable, rarely used)
```

```python
class MemoryAwareCache:
    """Cache that monitors and adapts to memory pressure."""

    def __init__(self, client: redis.Redis, warning_pct: float = 0.85):
        self.r = client
        self.warning_pct = warning_pct

    def check_memory(self) -> dict:
        info = self.r.info("memory")
        used = info["used_memory"]
        max_mem = info.get("maxmemory", 0)

        result = {
            "used_bytes": used,
            "used_human": info["used_memory_human"],
            "max_bytes": max_mem,
            "fragmentation_ratio": info["mem_fragmentation_ratio"],
        }

        if max_mem > 0:
            utilization = used / max_mem
            result["utilization"] = utilization
            result["warning"] = utilization > self.warning_pct
        else:
            result["utilization"] = None
            result["warning"] = False

        return result

    def get_big_keys_sample(self, count: int = 10) -> list:
        """Find large keys using SCAN (non-blocking)."""
        big_keys = []
        cursor = 0

        for _ in range(100):  # Limit iterations
            cursor, keys = self.r.scan(cursor, count=100)
            for key in keys:
                try:
                    mem = self.r.memory_usage(key)
                    if mem and mem > 1024:  # > 1KB
                        big_keys.append({"key": key, "bytes": mem})
                except redis.ResponseError:
                    continue
            if cursor == 0:
                break

        big_keys.sort(key=lambda x: x["bytes"], reverse=True)
        return big_keys[:count]
```

### Persistence: RDB vs AOF

```bash
# RDB (Redis Database Backup) — point-in-time snapshots
# Pros: compact, fast restart, good for backups
# Cons: data loss between snapshots (up to 5 min)
save 900 1     # Save if at least 1 key changed in 900 seconds
save 300 10    # Save if at least 10 keys changed in 300 seconds
save 60 10000  # Save if at least 10000 keys changed in 60 seconds

# AOF (Append Only File) — logs every write operation
# Pros: minimal data loss (1 second with everysec)
# Cons: larger files, slower restart
appendonly yes
appendfsync everysec  # Sync to disk every second (recommended)
# Options: always (safest, slowest), everysec (good tradeoff), no (OS decides)

# AOF rewrite: compact the AOF file periodically
auto-aof-rewrite-percentage 100   # Rewrite when AOF doubles
auto-aof-rewrite-min-size 64mb    # Minimum size before rewrite

# RECOMMENDED: Use both RDB + AOF
# Redis uses AOF for recovery (more complete)
# RDB for backups (compact, fast to transfer)
```

### Key Naming Conventions

```python
# Consistent, hierarchical key naming:
# pattern: {entity}:{id}:{field}

# Examples:
"user:42:profile"          # User profile hash
"user:42:sessions"         # User's active sessions set
"order:abc123:status"      # Order status
"cache:api:v2:/users/42"   # API response cache
"lock:payment:order-789"   # Distributed lock
"ratelimit:api:user:42"    # Rate limit counter
"queue:emails:pending"     # Queue (list or stream)
"feature:dark_mode"        # Feature flag bitmap
"stats:daily:2024-03-01"   # Daily statistics

# Key design rules:
# 1. Use colons as separators (Redis convention)
# 2. Start with entity type
# 3. Keep keys under 100 bytes
# 4. Use consistent prefixes for SCAN patterns
# 5. Include version if schema might change: "user:v2:42:profile"
```

### Monitoring with INFO and SLOWLOG

```python
class RedisMonitor:
    """Production Redis monitoring."""

    def __init__(self, client: redis.Redis):
        self.r = client

    def health_check(self) -> dict:
        """Comprehensive health check."""
        info = self.r.info()

        return {
            # Memory
            "memory_used_mb": info["used_memory"] / 1024 / 1024,
            "memory_fragmentation": info["mem_fragmentation_ratio"],
            # Performance
            "ops_per_sec": info["instantaneous_ops_per_sec"],
            "hit_rate": self._hit_rate(info),
            # Connections
            "connected_clients": info["connected_clients"],
            "blocked_clients": info["blocked_clients"],
            # Persistence
            "rdb_last_save_status": info.get("rdb_last_bgsave_status"),
            "aof_last_write_status": info.get("aof_last_write_status"),
            # Replication
            "role": info["role"],
            "connected_slaves": info.get("connected_slaves", 0),
            # Alerts
            "alerts": self._check_alerts(info),
        }

    def _hit_rate(self, info: dict) -> float:
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        return hits / total if total > 0 else 0.0

    def _check_alerts(self, info: dict) -> list:
        alerts = []
        if info["mem_fragmentation_ratio"] > 1.5:
            alerts.append("High memory fragmentation (>1.5)")
        if info.get("blocked_clients", 0) > 0:
            alerts.append(f"{info['blocked_clients']} blocked clients")
        hit_rate = self._hit_rate(info)
        if hit_rate < 0.8 and hit_rate > 0:
            alerts.append(f"Low cache hit rate: {hit_rate:.1%}")
        return alerts

    def get_slow_queries(self, count: int = 10) -> list:
        """Get recent slow queries from SLOWLOG."""
        entries = self.r.slowlog_get(count)
        return [
            {
                "id": entry["id"],
                "timestamp": entry["start_time"],
                "duration_us": entry["duration"],
                "duration_ms": entry["duration"] / 1000,
                "command": " ".join(
                    str(arg) for arg in entry["command"][:5]
                ),
            }
            for entry in entries
        ]

    def get_client_stats(self) -> list:
        """Analyze connected clients."""
        clients = self.r.client_list()
        by_name = {}
        for c in clients:
            name = c.get("name", "unnamed")
            if name not in by_name:
                by_name[name] = {"count": 0, "idle_total": 0}
            by_name[name]["count"] += 1
            by_name[name]["idle_total"] += c.get("idle", 0)

        return [
            {
                "name": name,
                "connections": stats["count"],
                "avg_idle_sec": stats["idle_total"] / stats["count"],
            }
            for name, stats in sorted(
                by_name.items(),
                key=lambda x: x[1]["count"],
                reverse=True,
            )
        ]


# Periodic monitoring
monitor = RedisMonitor(r)
health = monitor.health_check()
if health["alerts"]:
    for alert in health["alerts"]:
        print(f"ALERT: {alert}")
```

**Operational checklist**: (1) Always set `maxmemory` and `maxmemory-policy` — unbounded Redis will eat all RAM, (2) Use both RDB + AOF persistence unless it's a pure cache, (3) Monitor hit rate — below 80% means your cache isn't effective, (4) Monitor fragmentation ratio — above 1.5 means wasted memory (restart to defragment), (5) Use SLOWLOG to find expensive commands — O(N) commands on large collections are the usual suspects."""
    ),
]
