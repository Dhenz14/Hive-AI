"""p14 redis patterns"""

PAIRS = [
    (
        "databases/redis-data-structures",
        "Explain Redis data structures beyond simple key-value including Sorted Sets for leaderboards, Streams for event sourcing, HyperLogLog for cardinality estimation, Bitmaps for feature flags, and Pub/Sub patterns. Include practical Python implementations.",
        '''Redis is often reduced to "a cache," but its data structures solve problems that would require multiple external systems. Understanding when to use each structure is the key to effective Redis usage.

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
            self.key, 0, count - 1, withscores=True'''
    ),
    (
        "timestamp",
        "} return self.r.xadd(self.stream, entry, maxlen=100000) def create_consumer_group(self, group: str, start_id: str = '0'):",
        '''self.r.xgroup_create(self.stream, group, id=start_id, mkstream=True)
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
            block=block_ms,'''
    ),
    (
        "databases/redis-caching-patterns",
        "Explain Redis caching patterns including cache-aside, write-through, write-behind, cache invalidation strategies, distributed locking with Redlock, and cache stampede prevention. Include Python implementations with proper error handling.",
        '''Caching is simple in concept but notoriously hard to get right. The problems aren't in reading from cache -- they're in keeping the cache consistent with the source of truth and handling failure modes.

### Cache-Aside (Lazy Loading)

The most common pattern -- application manages cache explicitly:

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
            json.dumps(value, default=str),'''
    ),
    (
        "timestamp",
        "}))",
        '''### Distributed Locking with Redlock

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
            # SET NX with expiry -- atomic acquire
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
            # we'll recompute early -- spreading the load
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
            # Another process is recomputing -- serve stale if available
            if raw:
                return json.loads(raw)["value"]
            # No stale data, must wait
            time.sleep(0.5)
            return self.get_or_set_protected(key, factory, ttl, beta)

        try:
            start = time.time()
            value = factory()
            delta = time.time() - start  # Track computation time

            entry = {'''
    ),
    (
        "delta",
        "} self.r.setex( f'c:{key}' ttl + 60,  # Extra buffer for stale serving json.dumps(entry, default=str) ) return value finally: self.lock.release(f'recompute:{key}', token)",
        '''**Caching rules**: (1) Cache-aside is the safest default -- application controls consistency, (2) Always set TTL -- unbounded caches grow until OOM, (3) Invalidate on write, don't wait for TTL -- users expect immediate consistency, (4) Use distributed locks for expensive recomputations -- prevent stampede, (5) Cache failures should degrade to slower DB queries, never errors -- Redis down shouldn't mean app down.'''
    ),
    (
        "databases/redis-operational-patterns",
        "Explain Redis operational patterns including memory management and eviction policies, persistence options (RDB vs AOF), replication and sentinel for HA, key naming conventions, and monitoring with INFO and SLOWLOG.",
        '''Running Redis in production requires understanding memory management, data durability options, and monitoring. These operational patterns prevent data loss and performance degradation.

### Memory Management and Eviction

```bash
# Set maximum memory
# redis.conf
maxmemory 2gb

# Eviction policies (what to delete when memory is full):
maxmemory-policy allkeys-lru  # Evict least recently used (recommended for cache)

# Policy options:
# noeviction        -- Return errors on writes (safe for data stores)
# allkeys-lru       -- Evict LRU keys from all keys (best for cache)
# allkeys-lfu       -- Evict least frequently used (better for skewed access)
# volatile-lru      -- Evict LRU from keys with TTL set
# volatile-ttl      -- Evict keys with shortest TTL
# allkeys-random    -- Random eviction (unpredictable, rarely used)
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

        result = {'''
    ),
    (
        "fragmentation_ratio",
        "} if max_mem > 0: utilization = used / max_mem result['utilization'] = utilization result['warning'] = utilization > self.warning_pct else: result['utilization'] = None result['warning'] = False return result def get_big_keys_sample(self, count: int = 10) -> list:",
        '''cursor = 0

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
# RDB (Redis Database Backup) -- point-in-time snapshots
# Pros: compact, fast restart, good for backups
# Cons: data loss between snapshots (up to 5 min)
save 900 1     # Save if at least 1 key changed in 900 seconds
save 300 10    # Save if at least 10 keys changed in 300 seconds
save 60 10000  # Save if at least 10000 keys changed in 60 seconds

# AOF (Append Only File) -- logs every write operation
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
            # Memory'''
    ),
    (
        "command",
        "str(arg) for arg in entry['command'][:5] ) } for entry in entries ] def get_client_stats(self) -> list:",
        '''by_name = {}
        for c in clients:
            name = c.get("name", "unnamed")
            if name not in by_name:
                by_name[name] = {"count": 0, "idle_total": 0}
            by_name[name]["count"] += 1
            by_name[name]["idle_total"] += c.get("idle", 0)

        return [
            {'''
    ),
    (
        "avg_idle_sec",
        "} for name, stats in sorted( by_name.items() key=lambda x: x[1]['count'] reverse=True ) ]",
        '''monitor = RedisMonitor(r)
health = monitor.health_check()
if health["alerts"]:
    for alert in health["alerts"]:
        print(f"ALERT: {alert}")
```

**Operational checklist**: (1) Always set `maxmemory` and `maxmemory-policy` -- unbounded Redis will eat all RAM, (2) Use both RDB + AOF persistence unless it's a pure cache, (3) Monitor hit rate -- below 80% means your cache isn't effective, (4) Monitor fragmentation ratio -- above 1.5 means wasted memory (restart to defragment), (5) Use SLOWLOG to find expensive commands -- O(N) commands on large collections are the usual suspects.'''
    ),
]
