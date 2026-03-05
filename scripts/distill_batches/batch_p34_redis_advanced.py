"""Redis advanced — data structures, Lua scripting, pub/sub, and caching patterns."""

PAIRS = [
    (
        "databases/redis-data-structures",
        "Show Redis data structure patterns: sorted sets for leaderboards, streams for event logs, HyperLogLog for counting, and Bloom filters.",
        '''Redis data structures beyond simple key-value:

```python
import redis.asyncio as redis
import json
import time
from typing import Optional

class RedisPatterns:
    def __init__(self, client: redis.Redis):
        self.r = client

    # --- Sorted Set: Leaderboard ---

    async def update_score(self, board: str, user_id: str, score: float):
        """Add/update score in leaderboard."""
        await self.r.zadd(f"leaderboard:{board}", {user_id: score})

    async def increment_score(self, board: str, user_id: str, delta: float):
        return await self.r.zincrby(f"leaderboard:{board}", delta, user_id)

    async def get_top(self, board: str, count: int = 10) -> list[dict]:
        """Top N with scores (highest first)."""
        results = await self.r.zrevrange(
            f"leaderboard:{board}", 0, count - 1, withscores=True
        )
        return [
            {"user_id": uid, "score": score, "rank": i + 1}
            for i, (uid, score) in enumerate(results)
        ]

    async def get_rank(self, board: str, user_id: str) -> dict | None:
        """Get user's rank and score."""
        rank = await self.r.zrevrank(f"leaderboard:{board}", user_id)
        if rank is None:
            return None
        score = await self.r.zscore(f"leaderboard:{board}", user_id)
        return {"user_id": user_id, "rank": rank + 1, "score": score}

    async def get_around_user(self, board: str, user_id: str,
                               count: int = 5) -> list[dict]:
        """Get users around a specific user's rank."""
        rank = await self.r.zrevrank(f"leaderboard:{board}", user_id)
        if rank is None:
            return []
        start = max(0, rank - count // 2)
        end = start + count - 1
        results = await self.r.zrevrange(
            f"leaderboard:{board}", start, end, withscores=True
        )
        return [
            {"user_id": uid, "score": score, "rank": start + i + 1}
            for i, (uid, score) in enumerate(results)
        ]

    # --- Stream: Event log ---

    async def add_event(self, stream: str, event: dict,
                        maxlen: int = 10000) -> str:
        """Append event to stream with automatic trimming."""
        event_id = await self.r.xadd(
            f"stream:{stream}",
            event,
            maxlen=maxlen,
            approximate=True,  # ~ for performance
        )
        return event_id

    async def read_events(self, stream: str, last_id: str = "0",
                           count: int = 100) -> list[dict]:
        """Read events after a given ID."""
        results = await self.r.xrange(
            f"stream:{stream}", min=last_id, count=count
        )
        return [
            {"id": eid, **{k: v for k, v in data.items()}}
            for eid, data in results
        ]

    async def create_consumer_group(self, stream: str, group: str):
        try:
            await self.r.xgroup_create(
                f"stream:{stream}", group, id="0", mkstream=True
            )
        except redis.ResponseError:
            pass  # Group already exists

    async def consume_group(self, stream: str, group: str,
                             consumer: str, count: int = 10):
        """Consumer group: each message processed by ONE consumer."""
        results = await self.r.xreadgroup(
            group, consumer,
            {f"stream:{stream}": ">"},
            count=count,
            block=5000,
        )
        if not results:
            return []
        return [
            {"id": eid, **{k: v for k, v in data.items()}}
            for _, messages in results
            for eid, data in messages
        ]

    async def ack_event(self, stream: str, group: str, event_id: str):
        await self.r.xack(f"stream:{stream}", group, event_id)

    # --- HyperLogLog: Approximate counting ---

    async def track_unique_visitor(self, page: str, visitor_id: str):
        """Count unique visitors with O(1) memory per page."""
        await self.r.pfadd(f"visitors:{page}", visitor_id)

    async def get_unique_count(self, page: str) -> int:
        return await self.r.pfcount(f"visitors:{page}")

    async def merge_counts(self, dest: str, *pages: str):
        """Merge multiple HyperLogLogs for total uniques."""
        keys = [f"visitors:{p}" for p in pages]
        await self.r.pfmerge(f"visitors:{dest}", *keys)
        return await self.r.pfcount(f"visitors:{dest}")

    # --- Bitmap: Feature flags / presence ---

    async def set_feature_flag(self, feature: str, user_id: int,
                                enabled: bool):
        await self.r.setbit(f"feature:{feature}", user_id, int(enabled))

    async def check_feature(self, feature: str, user_id: int) -> bool:
        return bool(await self.r.getbit(f"feature:{feature}", user_id))

    async def feature_user_count(self, feature: str) -> int:
        return await self.r.bitcount(f"feature:{feature}")

    # --- Hash: Object storage ---

    async def save_session(self, session_id: str, data: dict,
                            ttl: int = 3600):
        key = f"session:{session_id}"
        await self.r.hset(key, mapping=data)
        await self.r.expire(key, ttl)

    async def get_session(self, session_id: str) -> dict | None:
        data = await self.r.hgetall(f"session:{session_id}")
        return data if data else None

    async def update_session_field(self, session_id: str,
                                    field: str, value: str):
        await self.r.hset(f"session:{session_id}", field, value)
```

Data structure selection:
- **String** — cache, counters, simple values
- **Hash** — objects, sessions, user profiles
- **List** — queues, recent items
- **Set** — unique tags, relationships, intersection/union
- **Sorted Set** — leaderboards, priority queues, time-series
- **Stream** — event log, consumer groups, audit trail
- **HyperLogLog** — unique counting (0.81% error, 12KB max)
- **Bitmap** — feature flags, daily active users, presence'''
    ),
    (
        "databases/redis-lua-caching",
        "Show Redis Lua scripting and advanced caching: atomic operations, distributed locks, cache stampede prevention, and cache-aside pattern.",
        '''Redis Lua scripts and production caching patterns:

```python
import redis.asyncio as redis
import hashlib
import json
import asyncio
from typing import Callable, Optional, Any
from functools import wraps
import time

# --- Lua scripts for atomic operations ---

# Atomic rate limiter (sliding window)
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Remove old entries
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current requests
local count = redis.call('ZCARD', key)

if count < limit then
    -- Add this request
    redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
    redis.call('EXPIRE', key, window)
    return {1, limit - count - 1}  -- allowed, remaining
else
    return {0, 0}  -- denied, 0 remaining
end
"""

# Compare-and-swap (optimistic locking)
CAS_SCRIPT = """
local key = KEYS[1]
local expected = ARGV[1]
local new_value = ARGV[2]
local ttl = tonumber(ARGV[3])

local current = redis.call('GET', key)
if current == expected then
    if ttl > 0 then
        redis.call('SET', key, new_value, 'EX', ttl)
    else
        redis.call('SET', key, new_value)
    end
    return 1
end
return 0
"""

class CacheService:
    def __init__(self, client: redis.Redis):
        self.r = client
        self._rate_limit_sha = None
        self._cas_sha = None

    async def init_scripts(self):
        self._rate_limit_sha = await self.r.script_load(RATE_LIMIT_SCRIPT)
        self._cas_sha = await self.r.script_load(CAS_SCRIPT)

    # --- Rate limiting ---

    async def check_rate_limit(self, key: str, limit: int,
                                window: int) -> tuple[bool, int]:
        now = int(time.time() * 1000)
        result = await self.r.evalsha(
            self._rate_limit_sha, 1,
            f"ratelimit:{key}", window * 1000, limit, now,
        )
        return bool(result[0]), int(result[1])

    # --- Distributed lock ---

    async def acquire_lock(self, name: str, ttl: int = 10) -> str | None:
        """Non-blocking distributed lock with TTL."""
        import secrets
        token = secrets.token_hex(16)
        acquired = await self.r.set(
            f"lock:{name}", token, nx=True, ex=ttl
        )
        return token if acquired else None

    async def release_lock(self, name: str, token: str) -> bool:
        """Release lock only if we own it (CAS)."""
        script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        result = await self.r.eval(script, 1, f"lock:{name}", token)
        return bool(result)

    # --- Cache-aside with stampede prevention ---

    async def get_or_set(
        self, key: str, factory: Callable[[], Any],
        ttl: int = 300, lock_ttl: int = 10,
    ) -> Any:
        """Cache-aside with lock to prevent stampede."""
        # Try cache
        cached = await self.r.get(f"cache:{key}")
        if cached is not None:
            return json.loads(cached)

        # Acquire lock to prevent stampede
        lock_token = await self.acquire_lock(f"cache_lock:{key}", lock_ttl)

        if lock_token:
            try:
                # Double-check after acquiring lock
                cached = await self.r.get(f"cache:{key}")
                if cached is not None:
                    return json.loads(cached)

                # Compute value
                value = await factory() if asyncio.iscoroutinefunction(factory) else factory()

                # Store in cache
                await self.r.set(
                    f"cache:{key}", json.dumps(value, default=str),
                    ex=ttl,
                )
                return value
            finally:
                await self.release_lock(f"cache_lock:{key}", lock_token)
        else:
            # Another process is computing; wait and retry
            for _ in range(50):
                await asyncio.sleep(0.2)
                cached = await self.r.get(f"cache:{key}")
                if cached is not None:
                    return json.loads(cached)
            # Timeout: compute ourselves
            value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
            return value

    # --- Cache decorator ---

    def cached(self, ttl: int = 300, prefix: str = ""):
        """Decorator for caching function results."""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Build cache key from function name + args
                parts = [prefix or func.__name__]
                parts.extend(str(a) for a in args)
                parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                key = hashlib.md5(":".join(parts).encode()).hexdigest()

                return await self.get_or_set(
                    f"{func.__name__}:{key}",
                    lambda: func(*args, **kwargs),
                    ttl=ttl,
                )
            return wrapper
        return decorator

    # --- Cache invalidation ---

    async def invalidate_pattern(self, pattern: str):
        """Delete all keys matching pattern."""
        async for key in self.r.scan_iter(f"cache:{pattern}*", count=100):
            await self.r.delete(key)

    async def invalidate_tags(self, *tags: str):
        """Tag-based invalidation: delete all keys with given tags."""
        for tag in tags:
            keys = await self.r.smembers(f"tag:{tag}")
            if keys:
                await self.r.delete(*keys)
            await self.r.delete(f"tag:{tag}")

    async def set_with_tags(self, key: str, value: Any,
                             tags: list[str], ttl: int = 300):
        """Set value and associate with tags for invalidation."""
        full_key = f"cache:{key}"
        pipe = self.r.pipeline()
        pipe.set(full_key, json.dumps(value, default=str), ex=ttl)
        for tag in tags:
            pipe.sadd(f"tag:{tag}", full_key)
            pipe.expire(f"tag:{tag}", ttl + 60)
        await pipe.execute()


# Usage:
# cache = CacheService(redis_client)
# await cache.init_scripts()
#
# @cache.cached(ttl=60)
# async def get_user_profile(user_id: int):
#     return await db.fetch_user(user_id)
#
# # Invalidate on update
# await cache.invalidate_pattern(f"get_user_profile:*")
```

Patterns:
1. **Lua scripts** — atomic multi-step operations (rate limiting, CAS)
2. **Distributed lock** — prevent concurrent writes, with auto-expiry
3. **Stampede prevention** — lock + double-check before computing
4. **Tag-based invalidation** — associate cache entries with tags for bulk clear
5. **Cache decorator** — transparent caching with auto key generation'''
    ),
]
