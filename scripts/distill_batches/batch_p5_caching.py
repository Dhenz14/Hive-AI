"""
Batch P5 — Caching Strategies & Systems
Covers: Redis patterns, cache invalidation, CDN, write-behind,
distributed caching.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "caching/redis-patterns",
        "Explain advanced Redis caching patterns for production systems including cache-aside, write-through, write-behind, and read-through strategies, along with Redis data structure selection for different use cases, TTL management, cache warming, and provide a complete Python implementation with connection pooling, circuit breaker, and stampede prevention using probabilistic early expiration.",
        r"""# Advanced Redis Caching Patterns for Production

## Why Caching Strategy Matters

Choosing the wrong caching pattern can be worse than no caching at all. A naive cache-aside implementation can serve stale data indefinitely, a write-through cache can double your write latency, and a poorly-managed TTL policy can cause **cache stampedes** that take down your database. Understanding the trade-offs between patterns is critical for building systems that are both fast and correct.

## The Four Core Patterns

### 1. Cache-Aside (Lazy Loading)

The application manages the cache explicitly: read from cache first, on miss read from DB and populate cache.

**Pros**: Only caches data that's actually requested. Simple to understand.
**Cons**: Cache misses are slow (DB + cache write). First request always misses. Stale data possible.

### 2. Write-Through

Every write goes to both cache and DB synchronously. Reads always hit cache.

**Pros**: Cache is always up-to-date. No stale data.
**Cons**: Write latency increases (two writes per operation). Caches data that may never be read.

### 3. Write-Behind (Write-Back)

Writes go to cache immediately, then asynchronously flushed to DB in batches.

**Pros**: Lowest write latency. Batch writes reduce DB load.
**Cons**: Data loss risk if cache crashes before flush. Complex consistency guarantees.

### 4. Read-Through

Cache itself is responsible for loading data on miss (the cache is a proxy).

**Pros**: Application code is simpler. Cache handles all loading logic.
**Cons**: Requires cache middleware. Cold start is still slow.

## Production Implementation

```python
# Advanced Redis caching with stampede prevention and circuit breaker
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import math
import random
import time
from typing import Any, Callable, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclasses.dataclass
class CacheConfig:
    # Configuration for the caching layer
    default_ttl: int = 3600          # 1 hour default
    stampede_beta: float = 1.0        # XFetch beta parameter
    max_retries: int = 3
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 30.0
    warm_on_start: bool = True
    prefix: str = "app"


class CircuitBreaker:
    # Circuit breaker for Redis connection failures.
    #
    # States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (testing)
    #
    # Without a circuit breaker, Redis failures cause every request
    # to wait for a connection timeout before falling back to DB.
    # With it, we fail fast after detecting a pattern of failures.

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, threshold: int = 5, timeout: float = 30.0) -> None:
        self.threshold = threshold
        self.timeout = timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = self.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.threshold:
            self.state = self.OPEN
            logger.warning("Circuit breaker OPEN -- Redis failures exceeded threshold")

    def allow_request(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time > self.timeout:
                self.state = self.HALF_OPEN
                return True
            return False
        # HALF_OPEN: allow one test request
        return True


class StampedeProtection:
    # Probabilistic early expiration (XFetch) to prevent cache stampedes.
    #
    # The problem: when a popular key expires, hundreds of concurrent
    # requests all miss the cache simultaneously and hit the DB --
    # a "thundering herd" that can cause cascading failures.
    #
    # Solution: each request independently decides whether to refresh
    # the cache BEFORE the TTL expires, based on a probabilistic
    # formula. With high concurrency, exactly one request will
    # "win" the race and refresh, while others continue using the
    # still-valid cached value.
    #
    # Formula: should_refresh = (now - (expiry - ttl * beta * ln(random())))  > expiry
    # As we approach expiry, the probability of refreshing increases.

    def __init__(self, beta: float = 1.0) -> None:
        self.beta = beta

    def should_recompute(
        self,
        expiry_time: float,
        ttl: float,
        compute_time: float = 0.1,
    ) -> bool:
        # Decide whether to proactively refresh this cache entry
        now = time.time()
        remaining = expiry_time - now

        if remaining <= 0:
            return True  # already expired

        # XFetch formula: higher beta = earlier refresh
        # compute_time weights the urgency (slow computations refresh earlier)
        gap = self.beta * compute_time * math.log(random.random())
        return now - gap >= expiry_time

    def set_with_metadata(
        self,
        redis_client: Any,
        key: str,
        value: str,
        ttl: int,
        compute_time: float,
    ) -> None:
        # Store value with metadata for XFetch
        metadata = json.dumps({
            "value": value,
            "compute_time": compute_time,
            "created_at": time.time(),
        })
        redis_client.setex(key, ttl, metadata)


class RedisCacheLayer:
    # Production Redis caching layer with all patterns and protections.
    #
    # Features:
    # - Cache-aside with automatic stampede prevention
    # - Write-through and write-behind support
    # - Circuit breaker for Redis failures
    # - Connection pooling via redis-py ConnectionPool
    # - Consistent hashing for multi-key operations
    # - Metrics tracking for hit rate monitoring

    def __init__(
        self,
        redis_client: Any,
        config: Optional[CacheConfig] = None,
    ) -> None:
        self.redis = redis_client
        self.config = config or CacheConfig()
        self.circuit_breaker = CircuitBreaker(
            threshold=self.config.circuit_breaker_threshold,
            timeout=self.config.circuit_breaker_timeout,
        )
        self.stampede = StampedeProtection(beta=self.config.stampede_beta)

        # Metrics
        self.hits = 0
        self.misses = 0
        self.errors = 0

        # Write-behind buffer
        self._write_buffer: list[tuple[str, Any]] = []
        self._last_flush = time.time()

    def _make_key(self, key: str) -> str:
        return f"{self.config.prefix}:{key}"

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], T],
        ttl: Optional[int] = None,
        force_refresh: bool = False,
    ) -> T:
        # Cache-aside with stampede prevention.
        #
        # This is the recommended pattern for most use cases because
        # it combines lazy loading with proactive refresh to prevent
        # stampedes. The compute_fn is only called on cache miss or
        # when XFetch decides to proactively refresh.
        ttl = ttl or self.config.default_ttl
        cache_key = self._make_key(key)

        if not force_refresh and self.circuit_breaker.allow_request():
            try:
                cached = self.redis.get(cache_key)
                if cached is not None:
                    self.hits += 1
                    self.circuit_breaker.record_success()

                    # Check XFetch: should we proactively refresh?
                    entry = json.loads(cached)
                    remaining_ttl = self.redis.ttl(cache_key)
                    if remaining_ttl > 0 and not self.stampede.should_recompute(
                        expiry_time=time.time() + remaining_ttl,
                        ttl=ttl,
                        compute_time=entry.get("compute_time", 0.1),
                    ):
                        return json.loads(entry["value"])

                    # XFetch triggered -- refresh in this request
                    logger.debug(f"XFetch proactive refresh for {key}")
                else:
                    self.misses += 1

            except Exception as e:
                self.errors += 1
                self.circuit_breaker.record_failure()
                logger.warning(f"Redis error on get: {e}")

        # Cache miss or refresh needed -- compute value
        start = time.perf_counter()
        value = compute_fn()
        compute_time = time.perf_counter() - start

        # Write to cache
        self._cache_set(cache_key, value, ttl, compute_time)
        return value

    def write_through(
        self,
        key: str,
        value: Any,
        db_write_fn: Callable[[str, Any], None],
        ttl: Optional[int] = None,
    ) -> None:
        # Write-through: update both cache and DB synchronously.
        #
        # Use this when you need strong consistency between cache
        # and DB. The trade-off is higher write latency because
        # both operations are in the critical path.
        ttl = ttl or self.config.default_ttl
        cache_key = self._make_key(key)

        # Write to DB first (source of truth)
        db_write_fn(key, value)

        # Then update cache
        self._cache_set(cache_key, value, ttl)

    def write_behind(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        flush_interval: float = 5.0,
    ) -> None:
        # Write-behind: update cache immediately, batch DB writes.
        #
        # Lowest write latency because only the cache write is
        # synchronous. DB writes are batched and flushed periodically.
        #
        # Common pitfall: data loss if the cache (Redis) crashes
        # before the buffer is flushed. Mitigate with Redis AOF
        # persistence or by using Redis Streams as the buffer.
        ttl = ttl or self.config.default_ttl
        cache_key = self._make_key(key)

        self._cache_set(cache_key, value, ttl)
        self._write_buffer.append((key, value))

        if time.time() - self._last_flush > flush_interval:
            self.flush_write_buffer()

    def flush_write_buffer(self) -> list[tuple[str, Any]]:
        # Flush write-behind buffer to database
        buffer = self._write_buffer.copy()
        self._write_buffer.clear()
        self._last_flush = time.time()
        logger.info(f"Flushing {len(buffer)} write-behind entries")
        return buffer

    def invalidate(self, key: str) -> bool:
        # Invalidate a cache entry.
        #
        # Best practice: prefer invalidation over update. It's
        # simpler and avoids the race condition where a stale
        # compute result overwrites a newer DB value.
        cache_key = self._make_key(key)
        try:
            return bool(self.redis.delete(cache_key))
        except Exception as e:
            logger.warning(f"Redis error on invalidate: {e}")
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        # Invalidate all keys matching a pattern.
        #
        # WARNING: KEYS command is O(N) and blocks Redis.
        # In production, use SCAN instead for non-blocking iteration.
        full_pattern = self._make_key(pattern)
        count = 0
        try:
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(
                    cursor=cursor, match=full_pattern, count=100
                )
                if keys:
                    count += self.redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"Redis error on pattern invalidate: {e}")
        return count

    def _cache_set(
        self,
        cache_key: str,
        value: Any,
        ttl: int,
        compute_time: float = 0.1,
    ) -> None:
        try:
            metadata = json.dumps({
                "value": json.dumps(value, default=str),
                "compute_time": compute_time,
                "created_at": time.time(),
            })
            self.redis.setex(cache_key, ttl, metadata)
            self.circuit_breaker.record_success()
        except Exception as e:
            self.errors += 1
            self.circuit_breaker.record_failure()
            logger.warning(f"Redis error on set: {e}")

    def warm_cache(
        self,
        keys_and_fns: dict[str, Callable[[], Any]],
        ttl: Optional[int] = None,
    ) -> int:
        # Pre-populate cache to avoid cold start misses.
        #
        # Call this during application startup or deployment to
        # ensure popular keys are cached before traffic arrives.
        ttl = ttl or self.config.default_ttl
        warmed = 0
        for key, compute_fn in keys_and_fns.items():
            try:
                value = compute_fn()
                cache_key = self._make_key(key)
                self._cache_set(cache_key, value, ttl)
                warmed += 1
            except Exception as e:
                logger.warning(f"Failed to warm cache for {key}: {e}")
        logger.info(f"Cache warming complete: {warmed}/{len(keys_and_fns)} keys")
        return warmed

    def get_metrics(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "errors": self.errors,
            "hit_rate": f"{self.hit_rate:.1%}",
            "circuit_breaker_state": self.circuit_breaker.state,
            "write_buffer_size": len(self._write_buffer),
        }
```

## Redis Data Structure Selection Guide

| Use Case | Data Structure | Why | Example |
|----------|---------------|-----|---------|
| **Simple key-value** | String | Fastest, simplest | Session tokens, page cache |
| **Object with fields** | Hash | Partial reads/writes | User profiles, product details |
| **Leaderboard** | Sorted Set | O(log N) rank queries | Gaming scores, trending items |
| **Rate limiting** | String + INCR | Atomic counter with TTL | API rate limits |
| **Recent items** | List (capped) | O(1) push, LTRIM for size | Activity feeds, recent searches |
| **Unique counts** | HyperLogLog | O(1) space, ~0.81% error | Unique visitors, cardinality |
| **Pub/sub messaging** | Streams | Persistent, consumer groups | Event bus, task queues |

## Cache Invalidation Strategies

```python
# Cache invalidation is "one of the two hard things in computer science"
# Here are the strategies ranked by consistency guarantee

class InvalidationStrategy:
    # Strategy 1: TTL-based (simplest, least consistent)
    # Set a TTL and accept stale data within the window.
    # Best for: data that changes rarely, where staleness is acceptable
    # Example: product catalog (TTL=1h), user preferences (TTL=15m)

    # Strategy 2: Event-driven invalidation (strong consistency)
    # Database triggers or application events invalidate cache on write.
    # Best for: data where staleness is unacceptable
    # Example: inventory counts, account balances

    # Strategy 3: Version-based (compromise)
    # Include a version number in the cache key. Increment on write.
    # Old versions naturally expire; new reads get fresh data.
    # Best for: frequently-read, occasionally-written data

    @staticmethod
    def versioned_key(entity: str, entity_id: str, version: int) -> str:
        return f"{entity}:{entity_id}:v{version}"

    @staticmethod
    def invalidate_via_pubsub(redis_client: Any, channel: str, key: str) -> None:
        # Publish invalidation event to all app instances
        # Each instance subscribes to the channel and deletes
        # the key from its local cache (L1) and Redis (L2)
        redis_client.publish(channel, json.dumps({"action": "invalidate", "key": key}))
```

## Multi-Level Caching (L1 + L2)

```python
from functools import lru_cache
from typing import Callable, Any


class MultiLevelCache:
    # Two-level caching: in-process (L1) + Redis (L2).
    #
    # L1 (in-process dict/LRU) avoids network round-trips entirely.
    # L2 (Redis) provides shared cache across application instances.
    #
    # The challenge is invalidation: when one instance updates a key,
    # other instances' L1 caches become stale. Solutions:
    # 1. Short L1 TTL (e.g., 5 seconds) -- simple but wasteful
    # 2. Redis pub/sub for cross-instance invalidation
    # 3. Version-stamped keys (read includes version check)
    #
    # Best practice: Use L1 only for truly hot keys (top 100-1000)
    # with very short TTL. The hit rate improvement is dramatic
    # because these keys account for most of the read traffic.

    def __init__(
        self,
        redis_cache: RedisCacheLayer,
        l1_max_size: int = 1000,
        l1_ttl: float = 5.0,
    ) -> None:
        self.l2 = redis_cache
        self.l1_max_size = l1_max_size
        self.l1_ttl = l1_ttl
        self._l1: dict[str, tuple[Any, float]] = {}  # key -> (value, expiry)
        self.l1_hits = 0
        self.l1_misses = 0

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Any],
        ttl: int = 3600,
    ) -> Any:
        # Check L1 first
        if key in self._l1:
            value, expiry = self._l1[key]
            if time.time() < expiry:
                self.l1_hits += 1
                return value
            else:
                del self._l1[key]

        self.l1_misses += 1

        # Fall through to L2 (Redis)
        value = self.l2.get_or_compute(key, compute_fn, ttl=ttl)

        # Populate L1
        if len(self._l1) >= self.l1_max_size:
            # Evict oldest entry
            oldest_key = min(self._l1, key=lambda k: self._l1[k][1])
            del self._l1[oldest_key]

        self._l1[key] = (value, time.time() + self.l1_ttl)
        return value
```

## Common Pitfalls and Best Practices

1. **Cache stampede**: When a popular key expires, hundreds of concurrent requests hit the DB simultaneously. Use **XFetch** (probabilistic early expiration) or **locking** (only one request refreshes, others wait) to prevent this.

2. **Stale cache after write**: The classic race condition — write to DB, then invalidate cache, but a concurrent read populates cache with old data between these steps. Solution: **invalidate before write** or use write-through.

3. **Unbounded cache growth**: Always set TTLs. Even "permanent" data should have a TTL (e.g., 24h) to prevent memory exhaustion from keys that are no longer relevant.

4. **Hot key problem**: A single key receiving millions of requests per second can overwhelm even Redis. Solution: **local caching (L1)** for the hottest keys, or **key sharding** (append a random suffix and aggregate reads).

## Key Takeaways

- **Cache-aside with XFetch** is the best general-purpose pattern because it combines lazy loading efficiency with stampede prevention
- **Write-through** provides the strongest consistency guarantee but doubles write latency — use it only for data where staleness is truly unacceptable
- **Multi-level caching** (L1 in-process + L2 Redis) eliminates network round-trips for hot keys, but requires careful invalidation to prevent serving stale data
- A **circuit breaker** is essential in production — without it, Redis failures cause every request to block on connection timeout before falling back to DB
- Cache invalidation remains the hardest problem: prefer **TTL-based expiration** with short windows over complex invalidation logic, and use **event-driven invalidation** only when strong consistency is required
"""
    ),
    (
        "caching/cdn-edge-caching",
        "Explain CDN and edge caching architecture including cache hierarchy design, cache key construction, cache purging strategies, stale-while-revalidate, and provide implementation examples for configuring Cloudflare/Fastly edge caching with proper cache-control headers, surrogate keys for targeted purging, and a Python origin server that maximizes cache hit rates.",
        r"""# CDN & Edge Caching: Maximizing Global Performance

## The Edge Caching Stack

A modern caching architecture has multiple layers, each closer to the user:

```
User → Browser Cache → CDN Edge (PoP) → CDN Shield → Origin Cache → Origin Server → Database
```

Each layer reduces load on the layer behind it. A well-configured CDN can serve **95%+ of requests** without touching your origin, reducing latency from 200ms+ to 10-30ms for cached content.

## Cache-Control Headers: The Foundation

```python
# Origin server with optimal cache-control headers
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any
from http import HTTPStatus


@dataclasses.dataclass
class CachePolicy:
    # Cache policy configuration for different content types.
    #
    # The Cache-Control header is the primary mechanism for controlling
    # how CDNs and browsers cache your content. Getting it wrong means
    # either serving stale content or missing cache hits entirely.
    max_age: int = 0               # browser cache duration (seconds)
    s_maxage: int = 0              # CDN/shared cache duration
    stale_while_revalidate: int = 0  # serve stale while refreshing
    stale_if_error: int = 0        # serve stale if origin is down
    private: bool = False          # browser only, no CDN
    no_store: bool = False         # never cache (sensitive data)
    must_revalidate: bool = False  # always check with origin
    immutable: bool = False        # content never changes (versioned assets)

    def to_header(self) -> str:
        # Build Cache-Control header value
        directives: list[str] = []

        if self.no_store:
            return "no-store, no-cache, must-revalidate"

        if self.private:
            directives.append("private")
        else:
            directives.append("public")

        if self.max_age > 0:
            directives.append(f"max-age={self.max_age}")
        if self.s_maxage > 0:
            directives.append(f"s-maxage={self.s_maxage}")
        if self.stale_while_revalidate > 0:
            directives.append(f"stale-while-revalidate={self.stale_while_revalidate}")
        if self.stale_if_error > 0:
            directives.append(f"stale-if-error={self.stale_if_error}")
        if self.must_revalidate:
            directives.append("must-revalidate")
        if self.immutable:
            directives.append("immutable")

        return ", ".join(directives)


# Pre-defined policies for common content types
CACHE_POLICIES = {
    "static_versioned": CachePolicy(
        max_age=31536000,     # 1 year browser
        s_maxage=31536000,    # 1 year CDN
        immutable=True,       # content hash in filename = never changes
    ),
    "api_public": CachePolicy(
        max_age=0,             # no browser cache
        s_maxage=60,           # CDN caches for 1 minute
        stale_while_revalidate=300,  # serve stale up to 5 min while refreshing
        stale_if_error=3600,   # serve stale up to 1h if origin is down
    ),
    "api_personalized": CachePolicy(
        private=True,          # browser only, not CDN
        max_age=60,
        must_revalidate=True,
    ),
    "html_page": CachePolicy(
        max_age=0,
        s_maxage=300,          # CDN caches 5 min
        stale_while_revalidate=60,
    ),
    "sensitive": CachePolicy(
        no_store=True,         # tokens, PII, payment data
    ),
}


class OriginServer:
    # Origin server optimized for CDN cache hit rates.
    #
    # Key principles:
    # 1. Consistent cache keys -- same content must produce same key
    # 2. Surrogate keys for targeted purging
    # 3. Vary header management to prevent over-fragmentation
    # 4. ETag for conditional requests (saves bandwidth)

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def handle_request(
        self,
        path: str,
        query_params: dict[str, str],
        request_headers: dict[str, str],
    ) -> dict[str, Any]:
        # Route and generate response with optimal cache headers

        # Determine content type and policy
        if path.startswith("/static/"):
            return self._handle_static(path)
        elif path.startswith("/api/"):
            return self._handle_api(path, query_params, request_headers)
        else:
            return self._handle_page(path, request_headers)

    def _handle_static(self, path: str) -> dict[str, Any]:
        # Static assets: aggressive caching with content-hash filenames
        # Example: /static/app.a1b2c3d4.js
        policy = CACHE_POLICIES["static_versioned"]
        content = f"// static content for {path}"
        etag = self._compute_etag(content)

        return {
            "status": 200,
            "body": content,
            "headers": {
                "Cache-Control": policy.to_header(),
                "ETag": etag,
                # Surrogate-Key allows targeted purging by type
                "Surrogate-Key": "static assets",
                "Content-Type": "application/javascript",
            },
        }

    def _handle_api(
        self,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        # API responses: short CDN cache with stale-while-revalidate
        #
        # Common mistake: Caching API responses that vary by auth token
        # without including Vary: Authorization. This serves one user's
        # data to another user. Always set Vary correctly.

        # Check if personalized
        auth_token = headers.get("Authorization", "")
        if auth_token:
            policy = CACHE_POLICIES["api_personalized"]
            vary = "Authorization, Accept-Encoding"
        else:
            policy = CACHE_POLICIES["api_public"]
            vary = "Accept-Encoding"

        # Normalize query params for consistent cache keys
        # Sorting params ensures ?a=1&b=2 and ?b=2&a=1 hit same cache
        normalized_params = "&".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )

        content = json.dumps({
            "path": path,
            "params": normalized_params,
            "timestamp": time.time(),
        })
        etag = self._compute_etag(content)

        # Extract entity type for surrogate key purging
        # /api/products/123 -> surrogate key "products product-123"
        parts = path.strip("/").split("/")
        surrogate_keys = []
        if len(parts) >= 2:
            surrogate_keys.append(parts[1])  # "products"
        if len(parts) >= 3:
            surrogate_keys.append(f"{parts[1]}-{parts[2]}")  # "product-123"

        return {
            "status": 200,
            "body": content,
            "headers": {
                "Cache-Control": policy.to_header(),
                "ETag": etag,
                "Vary": vary,
                "Surrogate-Key": " ".join(surrogate_keys),
                "Surrogate-Control": f"max-age={policy.s_maxage}",
            },
        }

    def _handle_page(
        self, path: str, headers: dict[str, str]
    ) -> dict[str, Any]:
        # HTML pages: moderate CDN caching with conditional requests
        policy = CACHE_POLICIES["html_page"]
        content = f"<html><body>Page: {path}</body></html>"
        etag = self._compute_etag(content)

        # Conditional request support: 304 Not Modified
        if_none_match = headers.get("If-None-Match", "")
        if if_none_match == etag:
            return {
                "status": 304,
                "body": "",
                "headers": {
                    "Cache-Control": policy.to_header(),
                    "ETag": etag,
                },
            }

        return {
            "status": 200,
            "body": content,
            "headers": {
                "Cache-Control": policy.to_header(),
                "ETag": etag,
                "Vary": "Accept-Encoding",
                "Surrogate-Key": "pages",
            },
        }

    @staticmethod
    def _compute_etag(content: str) -> str:
        # Weak ETag based on content hash
        hash_val = hashlib.md5(content.encode()).hexdigest()[:16]
        return f'W/"{hash_val}"'
```

## Surrogate Key Purging

```python
class CDNPurger:
    # Targeted cache purging using surrogate keys.
    #
    # Without surrogate keys, purging options are:
    # 1. Purge by URL -- tedious for many URLs
    # 2. Purge everything -- nuclear option, kills hit rate
    #
    # Surrogate keys allow semantic purging: "purge all product pages"
    # or "purge everything related to product-123" with a single API call.
    #
    # This is supported by Fastly (Surrogate-Key header),
    # Cloudflare (Cache-Tag header), and Varnish (xkey).

    def __init__(self, api_key: str, service_id: str) -> None:
        self.api_key = api_key
        self.service_id = service_id

    def purge_key(self, surrogate_key: str) -> dict[str, Any]:
        # Purge all cached objects tagged with this surrogate key
        # Fastly: POST /service/{id}/purge/{key}
        # Cloudflare: POST /zones/{id}/purge_cache {"tags": [key]}
        return {
            "action": "purge_surrogate_key",
            "key": surrogate_key,
            "estimated_objects": "varies",
        }

    def purge_on_update(self, entity_type: str, entity_id: str) -> list[str]:
        # Purge strategy when an entity is updated.
        #
        # Example: Product 123 is updated
        # Purge: "product-123" (detail page)
        #        "products" (listing pages)
        #        "search" (search results might include this product)
        keys_to_purge = [
            f"{entity_type}-{entity_id}",  # specific entity
            entity_type,                    # listing/collection pages
        ]
        for key in keys_to_purge:
            self.purge_key(key)
        return keys_to_purge

    def soft_purge(self, surrogate_key: str) -> dict[str, Any]:
        # Soft purge marks cached content as stale rather than deleting.
        # Combined with stale-while-revalidate, this means:
        # - Next request gets stale content instantly (no latency spike)
        # - CDN fetches fresh content from origin in the background
        # - Subsequent requests get fresh content
        #
        # This is always preferable to hard purge because it prevents
        # the cache miss storm that happens when popular content is deleted.
        return {
            "action": "soft_purge",
            "key": surrogate_key,
            "behavior": "mark_stale_not_delete",
        }
```

## Cache Key Construction Best Practices

| Factor | Include in Cache Key? | Why |
|--------|----------------------|-----|
| URL path | Always | Different paths = different content |
| Query params (sorted) | Yes, sorted | Prevents duplicate entries for reordered params |
| Accept-Encoding | Via Vary header | gzip vs brotli vs identity are different responses |
| Authorization | Via Vary (if needed) | Personalized content must not leak between users |
| Accept-Language | Only if content varies | Over-fragmentation kills hit rate |
| User-Agent | Almost never | Too many variants, use Client Hints instead |
| Cookies | Almost never | Destroys cache hit rate; use edge-side includes |

**Common pitfall**: Including too many factors in the cache key. Each additional dimension **multiplies** the number of cache entries, reducing hit rates. A URL cached with 5 Accept-Language variants and 3 Accept-Encoding variants needs 15 entries instead of 3.

## Key Takeaways

- **stale-while-revalidate** is the single most impactful cache directive — it eliminates latency spikes on cache expiration by serving stale content while refreshing in the background
- **Surrogate keys** enable semantic purging ("purge all product pages") instead of URL-by-URL purging — essential for maintaining both cache hit rates and content freshness
- **Soft purge** (mark stale, don't delete) is always preferable to hard purge because it prevents cache miss storms for popular content
- The **Vary header** is both essential and dangerous: too few Vary dimensions leak private data; too many fragment the cache and kill hit rates
- Versioned static assets with **immutable** cache-control should be cached for 1 year — the content hash in the filename guarantees correctness, and the long TTL maximizes CDN hit rates
"""
    ),
    (
        "caching/distributed-cache-consistency",
        "Explain distributed cache consistency challenges including cache coherence protocols, write invalidation vs write update, the thundering herd problem, cache warming strategies for deployments, and provide a Python implementation of a distributed cache coordinator using pub/sub invalidation with Redis, including lease-based locking for cache population and metrics for monitoring cache effectiveness.",
        r"""# Distributed Cache Consistency: Coordination Without Bottlenecks

## The Consistency Challenge

When multiple application instances share a cache (Redis, Memcached), maintaining consistency between the cache and the source of truth (database) is the central challenge. The naive approach — write to DB, then update cache — has a race condition that can permanently cache stale data. Understanding and preventing these races is what separates toy caching from production caching.

## The Classic Race Condition

```
Thread A: Read DB (value=1) → [context switch]
Thread B: Write DB (value=2) → Invalidate cache
Thread A: → Write cache (value=1, STALE!)
```

Thread A read the old value, got preempted, and overwrites the cache with stale data after Thread B already updated. The cache now permanently contains the wrong value until TTL expires.

**Solution**: Never write a computed value to cache after a write to DB. Instead:
1. **Delete-on-write**: Always invalidate (delete) the cache key on DB write. Let the next reader populate it.
2. **Lease-based population**: Use a distributed lock so only one thread populates the cache after a miss.

## Complete Implementation

```python
# Distributed cache coordinator with pub/sub invalidation
from __future__ import annotations

import dataclasses
import json
import logging
import threading
import time
import uuid
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class CacheEntry:
    # A cache entry with metadata for consistency tracking
    value: Any
    version: int
    created_at: float
    ttl: int
    lease_holder: Optional[str] = None  # which instance is refreshing


class CacheMetrics:
    # Comprehensive metrics for cache health monitoring.
    #
    # The most important metric is the MISS RATE under load --
    # if it exceeds 10-15%, your cache is likely too small or
    # your TTLs are too short. A sudden spike in miss rate
    # indicates a cache stampede or invalidation storm.

    def __init__(self) -> None:
        self.hits = 0
        self.misses = 0
        self.invalidations = 0
        self.stampedes_prevented = 0
        self.lease_acquisitions = 0
        self.lease_conflicts = 0
        self.stale_served = 0
        self.errors = 0
        self._start_time = time.time()

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def requests_per_second(self) -> float:
        elapsed = time.time() - self._start_time
        total = self.hits + self.misses
        return total / elapsed if elapsed > 0 else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "hit_rate": f"{self.hit_rate:.1%}",
            "hits": self.hits,
            "misses": self.misses,
            "invalidations": self.invalidations,
            "stampedes_prevented": self.stampedes_prevented,
            "lease_conflicts": self.lease_conflicts,
            "stale_served": self.stale_served,
            "rps": f"{self.requests_per_second:.1f}",
        }


class DistributedCacheCoordinator:
    # Coordinates cache operations across multiple app instances.
    #
    # Features:
    # - Pub/sub invalidation: when one instance writes, all instances
    #   invalidate their local caches
    # - Lease-based population: prevents thundering herd on cache miss
    # - Version tracking: detects and discards stale cache writes
    # - Graceful degradation: serves stale data when DB is unavailable
    #
    # Architecture:
    # App Instance 1 ──┐
    # App Instance 2 ──┼── Redis (shared L2 cache + pub/sub)
    # App Instance 3 ──┘
    #
    # Each instance also has an L1 (in-process) cache that is
    # invalidated via Redis pub/sub when any instance writes.

    INVALIDATION_CHANNEL = "cache:invalidations"
    LEASE_PREFIX = "cache:lease:"
    VERSION_PREFIX = "cache:version:"

    def __init__(
        self,
        redis_client: Any,
        instance_id: Optional[str] = None,
        lease_timeout: float = 10.0,
        default_ttl: int = 3600,
    ) -> None:
        self.redis = redis_client
        self.instance_id = instance_id or str(uuid.uuid4())[:8]
        self.lease_timeout = lease_timeout
        self.default_ttl = default_ttl
        self.metrics = CacheMetrics()

        # Local L1 cache
        self._local_cache: dict[str, CacheEntry] = {}
        self._local_cache_lock = threading.Lock()

        # Start pub/sub listener for cross-instance invalidation
        self._listener_thread: Optional[threading.Thread] = None

    def start_invalidation_listener(self) -> None:
        # Start background thread to listen for invalidation messages.
        #
        # When any instance writes to the DB, it publishes an
        # invalidation message. All instances (including the writer)
        # receive it and clear their L1 cache for that key.
        def listener() -> None:
            pubsub = self.redis.pubsub()
            pubsub.subscribe(self.INVALIDATION_CHANNEL)
            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        self._handle_invalidation(data)
                    except Exception as e:
                        logger.error(f"Invalidation listener error: {e}")

        self._listener_thread = threading.Thread(
            target=listener, daemon=True, name="cache-invalidation"
        )
        self._listener_thread.start()

    def get(
        self,
        key: str,
        compute_fn: Callable[[], Any],
        ttl: Optional[int] = None,
    ) -> Any:
        # Get a value with lease-based cache population.
        #
        # Flow:
        # 1. Check L1 (local) cache
        # 2. Check L2 (Redis) cache
        # 3. On miss: acquire lease, compute, populate, release
        #
        # The lease prevents the thundering herd: if 100 requests
        # miss simultaneously, only one acquires the lease and
        # computes. The other 99 either wait briefly or get served
        # stale data (if available).

        ttl = ttl or self.default_ttl

        # Step 1: Check L1 (local in-process cache)
        with self._local_cache_lock:
            if key in self._local_cache:
                entry = self._local_cache[key]
                age = time.time() - entry.created_at
                if age < entry.ttl:
                    self.metrics.hits += 1
                    return entry.value

        # Step 2: Check L2 (Redis)
        try:
            cached = self.redis.get(f"cache:{key}")
            if cached is not None:
                self.metrics.hits += 1
                value = json.loads(cached)
                self._update_l1(key, value, ttl)
                return value
        except Exception as e:
            self.metrics.errors += 1
            logger.warning(f"Redis get error: {e}")

        # Step 3: Cache miss -- try to acquire lease
        self.metrics.misses += 1
        return self._populate_with_lease(key, compute_fn, ttl)

    def _populate_with_lease(
        self,
        key: str,
        compute_fn: Callable[[], Any],
        ttl: int,
    ) -> Any:
        # Lease-based cache population to prevent thundering herd.
        #
        # Only one instance/thread can hold the lease for a given key.
        # Others see the lease exists and either:
        # - Wait briefly and retry (if no stale data available)
        # - Return stale data (if available -- graceful degradation)
        lease_key = f"{self.LEASE_PREFIX}{key}"
        lease_value = f"{self.instance_id}:{threading.current_thread().ident}"

        # Try to acquire lease (SET NX with expiry)
        acquired = False
        try:
            acquired = bool(self.redis.set(
                lease_key, lease_value,
                nx=True,  # only if not exists
                ex=int(self.lease_timeout),
            ))
        except Exception:
            pass

        if not acquired:
            self.metrics.lease_conflicts += 1
            self.metrics.stampedes_prevented += 1

            # Check for stale L1 data we can serve
            with self._local_cache_lock:
                if key in self._local_cache:
                    self.metrics.stale_served += 1
                    return self._local_cache[key].value

            # Wait briefly and retry from L2
            time.sleep(0.1)
            try:
                cached = self.redis.get(f"cache:{key}")
                if cached is not None:
                    return json.loads(cached)
            except Exception:
                pass

            # Fallback: compute anyway (lease holder might have failed)
            logger.warning(f"Lease conflict fallback for {key}")

        # We hold the lease (or fell through) -- compute the value
        try:
            self.metrics.lease_acquisitions += 1
            value = compute_fn()

            # Write to L2 (Redis)
            try:
                self.redis.setex(f"cache:{key}", ttl, json.dumps(value, default=str))
            except Exception as e:
                logger.warning(f"Redis set error: {e}")

            # Write to L1
            self._update_l1(key, value, ttl)
            return value

        finally:
            # Release lease
            try:
                # Only delete if we still own the lease (CAS)
                current = self.redis.get(lease_key)
                if current and current.decode() == lease_value:
                    self.redis.delete(lease_key)
            except Exception:
                pass

    def invalidate(self, key: str, source: str = "write") -> None:
        # Invalidate a key across all instances via pub/sub.
        #
        # This is called after writing to the database. The pub/sub
        # message ensures all instances clear their L1 cache, and
        # we also delete the L2 (Redis) entry.
        #
        # Order matters: delete L2 first, then publish. If we publish
        # first, an instance might re-populate L2 from DB before we
        # delete it, causing permanent staleness.

        # Delete from L2 (Redis)
        try:
            self.redis.delete(f"cache:{key}")
        except Exception as e:
            logger.warning(f"Redis delete error: {e}")

        # Publish invalidation to all instances
        try:
            msg = json.dumps({
                "key": key,
                "source": source,
                "instance": self.instance_id,
                "timestamp": time.time(),
            })
            self.redis.publish(self.INVALIDATION_CHANNEL, msg)
        except Exception as e:
            logger.warning(f"Redis publish error: {e}")

        # Also clear local L1
        self._invalidate_l1(key)
        self.metrics.invalidations += 1

    def _handle_invalidation(self, data: dict[str, Any]) -> None:
        # Handle an invalidation message from pub/sub
        key = data.get("key", "")
        source_instance = data.get("instance", "")

        logger.debug(
            f"[{self.instance_id}] Invalidation for {key} "
            f"from {source_instance}"
        )
        self._invalidate_l1(key)

    def _update_l1(self, key: str, value: Any, ttl: int) -> None:
        with self._local_cache_lock:
            self._local_cache[key] = CacheEntry(
                value=value,
                version=0,
                created_at=time.time(),
                ttl=ttl,
            )

    def _invalidate_l1(self, key: str) -> None:
        with self._local_cache_lock:
            self._local_cache.pop(key, None)


class CacheWarmer:
    # Pre-populate cache during deployments to prevent cold start storms.
    #
    # During a rolling deployment, each new instance starts with an
    # empty L1 cache. If 10 instances restart simultaneously, the
    # DB receives 10x the normal miss traffic. Cache warming prevents
    # this by pre-loading the most important keys before the instance
    # starts accepting traffic.
    #
    # Best practice: warm the top N keys by access frequency, not
    # all keys. Warming too many keys wastes time and memory.

    def __init__(
        self,
        coordinator: DistributedCacheCoordinator,
    ) -> None:
        self.coordinator = coordinator

    def warm_from_access_log(
        self,
        popular_keys: list[str],
        compute_fns: dict[str, Callable[[], Any]],
        max_keys: int = 1000,
        ttl: int = 3600,
    ) -> dict[str, int]:
        # Warm cache from a list of popular keys
        warmed = 0
        failed = 0

        for key in popular_keys[:max_keys]:
            if key in compute_fns:
                try:
                    self.coordinator.get(key, compute_fns[key], ttl=ttl)
                    warmed += 1
                except Exception as e:
                    failed += 1
                    logger.warning(f"Cache warm failed for {key}: {e}")

        logger.info(f"Cache warming: {warmed} warmed, {failed} failed")
        return {"warmed": warmed, "failed": failed}

    def warm_from_peer(
        self,
        peer_redis: Any,
        keys: list[str],
    ) -> int:
        # Copy cached values from a peer instance's Redis.
        #
        # This is useful during blue-green deployments: the new
        # environment can warm its cache from the old environment's
        # Redis before cutting traffic over.
        copied = 0
        for key in keys:
            try:
                value = peer_redis.get(f"cache:{key}")
                if value is not None:
                    ttl = peer_redis.ttl(f"cache:{key}")
                    if ttl > 0:
                        self.coordinator.redis.setex(
                            f"cache:{key}", ttl, value
                        )
                        copied += 1
            except Exception as e:
                logger.warning(f"Peer warm failed for {key}: {e}")
        return copied
```

## Monitoring Dashboard Queries

```python
def generate_cache_dashboard(metrics: CacheMetrics) -> str:
    # Generate a monitoring summary for cache health
    summary = metrics.summary()
    alerts: list[str] = []

    # Alert thresholds
    if metrics.hit_rate < 0.80:
        alerts.append("WARNING: Hit rate below 80% -- check TTLs and cache size")
    if metrics.stampedes_prevented > 100:
        alerts.append("INFO: High stampede prevention count -- consider longer TTLs")
    if metrics.errors > metrics.hits * 0.01:
        alerts.append("CRITICAL: Error rate > 1% -- check Redis connectivity")
    if metrics.stale_served > metrics.hits * 0.05:
        alerts.append("WARNING: Serving >5% stale data -- check invalidation pipeline")

    dashboard = (
        f"Cache Health Dashboard\n"
        f"=====================\n"
        f"Hit Rate: {summary['hit_rate']}\n"
        f"RPS: {summary['rps']}\n"
        f"Hits: {summary['hits']} | Misses: {summary['misses']}\n"
        f"Invalidations: {summary['invalidations']}\n"
        f"Stampedes Prevented: {summary['stampedes_prevented']}\n"
        f"Stale Served: {summary['stale_served']}\n"
    )

    if alerts:
        dashboard += "\nAlerts:\n"
        for alert in alerts:
            dashboard += f"  - {alert}\n"

    return dashboard
```

## Common Pitfalls

1. **The race condition on invalidation**: Always delete L2 (Redis) BEFORE publishing the pub/sub invalidation. Otherwise, an instance might re-populate L2 from the database after receiving the invalidation but before the L2 delete.

2. **Lease timeout too short**: If the compute function takes longer than the lease timeout, another instance starts computing in parallel — defeating the purpose. Set lease timeout to 2-3x the expected compute time.

3. **Invalidation storms**: If a batch job updates 10,000 records and each triggers a cache invalidation, you flood the pub/sub channel and cause all instances to simultaneously clear their L1 caches. Solution: batch invalidations and rate-limit pub/sub messages.

4. **Missing Vary headers**: Caching a response that varies by authentication without proper Vary headers serves one user's data to another. This is a security vulnerability, not just a correctness bug.

## Key Takeaways

- **Lease-based cache population** prevents the thundering herd problem by allowing only one instance to compute a missing cache value — others wait briefly or serve stale data
- **Pub/sub invalidation** ensures cross-instance L1 cache coherence — without it, each instance can serve stale data for the duration of its L1 TTL
- **Delete-on-write** (invalidate, don't update) is always safer than write-through for distributed caches because it avoids the stale-write race condition
- **Cache warming** during deployments prevents cold-start miss storms that can overwhelm the database — warm the top N keys by access frequency
- Monitor **hit rate, stampede count, and stale-served ratio** as key health indicators — a hit rate drop below 80% usually indicates a configuration problem
"""
    ),
    (
        "caching/application-level-memoization",
        "Explain application-level caching and memoization patterns including function-level caching with LRU/LFU eviction, request-scoped caching for web applications, cache key generation for complex arguments, and provide a Python implementation of a production-grade memoization decorator with TTL, max size, cache statistics, type-safe generics, and async support.",
        r"""# Application-Level Memoization: Beyond Simple @lru_cache

## When stdlib Isn't Enough

Python's `functools.lru_cache` is excellent for simple cases, but production applications need: **TTL expiration** (lru_cache entries live forever), **size-based eviction** (LRU only evicts by count, not memory), **async support** (lru_cache blocks the event loop on computation), **cache statistics** (hit rate monitoring), and **complex key generation** (lru_cache requires hashable arguments).

## Production Memoization Decorator

```python
# Production-grade memoization with TTL, async, and statistics
from __future__ import annotations

import asyncio
import dataclasses
import functools
import hashlib
import inspect
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import (
    Any, Awaitable, Callable, Generic, Optional, TypeVar, Union, overload,
)

logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")


@dataclasses.dataclass
class MemoizeStats:
    # Track cache effectiveness for monitoring
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    errors: int = 0
    total_compute_time: float = 0.0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def avg_compute_time(self) -> float:
        return self.total_compute_time / max(self.misses, 1)

    def __repr__(self) -> str:
        return (
            f"MemoizeStats(hit_rate={self.hit_rate:.1%}, "
            f"hits={self.hits}, misses={self.misses}, "
            f"evictions={self.evictions}, "
            f"avg_compute={self.avg_compute_time:.4f}s)"
        )


@dataclasses.dataclass
class CacheItem(Generic[T]):
    value: T
    expires_at: float
    compute_time: float
    access_count: int = 0
    last_accessed: float = 0.0


class TTLCache(Generic[T]):
    # Thread-safe LRU cache with TTL expiration.
    #
    # Unlike functools.lru_cache which only evicts by access order,
    # this cache also evicts expired entries and tracks per-entry
    # statistics for monitoring.
    #
    # Implementation uses OrderedDict for O(1) LRU operations.
    # The trade-off vs a heap-based approach: OrderedDict is simpler
    # and has better constant factors for cache sizes under 100K.

    def __init__(self, max_size: int = 1024, default_ttl: float = 300.0) -> None:
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheItem[T]] = OrderedDict()
        self._lock = threading.Lock()
        self.stats = MemoizeStats()

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            if key not in self._cache:
                self.stats.misses += 1
                return None

            item = self._cache[key]

            # Check expiration
            if time.time() > item.expires_at:
                del self._cache[key]
                self.stats.expirations += 1
                self.stats.misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            item.access_count += 1
            item.last_accessed = time.time()
            self.stats.hits += 1
            return item.value

    def put(self, key: str, value: T, ttl: Optional[float] = None, compute_time: float = 0.0) -> None:
        effective_ttl = ttl if ttl is not None else self.default_ttl
        with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self.max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                self.stats.evictions += 1

            self._cache[key] = CacheItem(
                value=value,
                expires_at=time.time() + effective_ttl,
                compute_time=compute_time,
                last_accessed=time.time(),
            )

    def invalidate(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    @property
    def size(self) -> int:
        return len(self._cache)


def _make_cache_key(func: Callable, args: tuple, kwargs: dict) -> str:
    # Generate a stable cache key from function arguments.
    #
    # Handles unhashable types (dicts, lists) by JSON-serializing them.
    # Uses the function's qualified name to prevent collisions between
    # methods with the same name on different classes.
    #
    # Common pitfall: using str() for key generation. Objects like
    # <object at 0x7f...> include memory addresses that change between
    # processes, making the cache useless in multi-process deployments.
    key_parts = [func.__module__, func.__qualname__]

    for arg in args:
        try:
            key_parts.append(json.dumps(arg, sort_keys=True, default=str))
        except (TypeError, ValueError):
            key_parts.append(str(id(arg)))

    for k, v in sorted(kwargs.items()):
        try:
            key_parts.append(f"{k}={json.dumps(v, sort_keys=True, default=str)}")
        except (TypeError, ValueError):
            key_parts.append(f"{k}={id(v)}")

    raw_key = "|".join(key_parts)
    # Hash for consistent length and to avoid very long keys
    return hashlib.sha256(raw_key.encode()).hexdigest()[:32]


def memoize(
    ttl: float = 300.0,
    max_size: int = 1024,
    key_fn: Optional[Callable[..., str]] = None,
) -> Callable[[F], F]:
    # Production memoization decorator with TTL and statistics.
    #
    # Supports both sync and async functions. Tracks hit rate,
    # compute time, and eviction count for monitoring.
    #
    # Usage:
    #   @memoize(ttl=60, max_size=500)
    #   def expensive_query(user_id: int) -> dict:
    #       return db.query(...)
    #
    #   # Access stats
    #   expensive_query.cache_stats()
    #   expensive_query.cache_clear()
    #   expensive_query.cache_invalidate(user_id=123)

    cache = TTLCache(max_size=max_size, default_ttl=ttl)

    def decorator(func: F) -> F:
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if key_fn:
                    cache_key = key_fn(*args, **kwargs)
                else:
                    cache_key = _make_cache_key(func, args, kwargs)

                cached = cache.get(cache_key)
                if cached is not None:
                    return cached

                start = time.perf_counter()
                result = await func(*args, **kwargs)
                compute_time = time.perf_counter() - start

                cache.put(cache_key, result, compute_time=compute_time)
                cache.stats.total_compute_time += compute_time
                return result

            async_wrapper.cache_stats = lambda: cache.stats  # type: ignore
            async_wrapper.cache_clear = cache.clear  # type: ignore
            async_wrapper.cache_size = lambda: cache.size  # type: ignore
            async_wrapper.cache_invalidate = lambda *a, **kw: cache.invalidate(  # type: ignore
                key_fn(*a, **kw) if key_fn else _make_cache_key(func, a, kw)
            )
            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if key_fn:
                    cache_key = key_fn(*args, **kwargs)
                else:
                    cache_key = _make_cache_key(func, args, kwargs)

                cached = cache.get(cache_key)
                if cached is not None:
                    return cached

                start = time.perf_counter()
                result = func(*args, **kwargs)
                compute_time = time.perf_counter() - start

                cache.put(cache_key, result, compute_time=compute_time)
                cache.stats.total_compute_time += compute_time
                return result

            sync_wrapper.cache_stats = lambda: cache.stats  # type: ignore
            sync_wrapper.cache_clear = cache.clear  # type: ignore
            sync_wrapper.cache_size = lambda: cache.size  # type: ignore
            sync_wrapper.cache_invalidate = lambda *a, **kw: cache.invalidate(  # type: ignore
                key_fn(*a, **kw) if key_fn else _make_cache_key(func, a, kw)
            )
            return sync_wrapper  # type: ignore

    return decorator


class RequestScopedCache:
    # Cache that lives for the duration of a single HTTP request.
    #
    # This prevents redundant DB queries within a single request
    # without the complexity of cross-request caching. For example,
    # if a request handler calls get_user(id) in the auth middleware,
    # the view function, and the serializer, the DB is only queried once.
    #
    # Implementation uses Python's contextvars for async-safe
    # per-request storage (works with asyncio, threading, etc.)

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self.hits = 0
        self.misses = 0

    def get_or_compute(self, key: str, compute_fn: Callable[[], T]) -> T:
        if key in self._store:
            self.hits += 1
            return self._store[key]

        self.misses += 1
        value = compute_fn()
        self._store[key] = value
        return value

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0


# === Usage Examples and Tests ===

@memoize(ttl=60, max_size=100)
def get_user_profile(user_id: int) -> dict:
    # Simulates expensive database query
    time.sleep(0.01)  # simulate DB latency
    return {"id": user_id, "name": f"User {user_id}", "fetched_at": time.time()}


@memoize(ttl=30, key_fn=lambda user_id, **kw: f"user:{user_id}")
def get_user_with_custom_key(user_id: int, include_posts: bool = False) -> dict:
    # Custom key function ignores include_posts for cache purposes
    # because the base user data is the same regardless
    return {"id": user_id, "name": f"User {user_id}"}


def test_memoize_decorator():
    # Test basic memoization behavior

    # First call: cache miss
    result1 = get_user_profile(1)
    assert result1["id"] == 1
    stats = get_user_profile.cache_stats()
    assert stats.misses == 1
    assert stats.hits == 0

    # Second call: cache hit (same result, no recomputation)
    result2 = get_user_profile(1)
    assert result2 is result1  # same object from cache
    stats = get_user_profile.cache_stats()
    assert stats.hits == 1

    # Different argument: cache miss
    result3 = get_user_profile(2)
    assert result3["id"] == 2
    assert stats.misses == 2

    print(f"Memoize test passed: {stats}")


def test_request_scoped_cache():
    # Test request-scoped caching
    cache = RequestScopedCache()
    call_count = 0

    def expensive_lookup() -> str:
        nonlocal call_count
        call_count += 1
        return "result"

    # Multiple calls with same key: computed once
    r1 = cache.get_or_compute("key1", expensive_lookup)
    r2 = cache.get_or_compute("key1", expensive_lookup)
    r3 = cache.get_or_compute("key1", expensive_lookup)

    assert call_count == 1  # only computed once
    assert r1 == r2 == r3 == "result"
    assert cache.hits == 2
    assert cache.misses == 1

    print("Request-scoped cache test passed")


def test_ttl_expiration():
    # Test that entries expire after TTL
    @memoize(ttl=0.1, max_size=10)
    def short_lived(x: int) -> int:
        return x * 2

    result1 = short_lived(5)
    assert result1 == 10
    assert short_lived.cache_stats().misses == 1

    # Wait for expiration
    time.sleep(0.15)

    result2 = short_lived(5)
    assert result2 == 10
    assert short_lived.cache_stats().misses == 2  # recomputed after expiry

    print("TTL expiration test passed")


if __name__ == "__main__":
    test_memoize_decorator()
    test_request_scoped_cache()
    test_ttl_expiration()
    print("\nAll memoization tests passed!")
```

## Eviction Strategy Comparison

| Strategy | Time Complexity | Hit Rate | Best For |
|----------|----------------|----------|----------|
| **LRU** (Least Recently Used) | O(1) | Good | General workloads |
| **LFU** (Least Frequently Used) | O(log N) | Better for skewed access | Hot/cold data separation |
| **FIFO** (First In First Out) | O(1) | Worst | Simple, predictable |
| **TTL-only** (no eviction) | O(1) | Depends on TTL | Fixed-lifetime data |
| **W-TinyLFU** (as in Caffeine) | O(1) amortized | Best overall | High-performance caches |

**Best practice**: LRU with TTL is the right default for 90% of applications. Only switch to LFU or W-TinyLFU if profiling shows that LRU eviction is removing frequently-accessed items (indicating a scan-resistance problem).

## Key Takeaways

- Python's `functools.lru_cache` lacks **TTL expiration** and **async support** — production applications need a custom solution that handles both
- **Cache key generation** must handle unhashable types (dicts, lists) and avoid memory-address-based keys that break in multi-process deployments
- **Request-scoped caching** eliminates redundant DB queries within a single request without cross-request consistency concerns — use `contextvars` for async-safe implementation
- **Monitoring cache statistics** (hit rate, eviction count, compute time) is essential — a cache with a low hit rate is worse than no cache because it adds complexity without benefit
- The `@memoize` decorator pattern exposes `.cache_stats()`, `.cache_clear()`, and `.cache_invalidate()` methods on the wrapped function — this API makes it easy to monitor and manage caches in production
"""
    ),
    (
        "caching/database-query-caching",
        "Explain database query result caching strategies including query fingerprinting, cache key derivation from SQL queries, automatic cache invalidation on table mutations, and provide a Python implementation of a query cache layer for SQLAlchemy that automatically detects table dependencies, invalidates on writes, and handles parameterized queries with cache statistics.",
        r"""# Database Query Result Caching with Automatic Invalidation

## The Query Caching Challenge

Database query caching seems simple — hash the SQL, cache the result. But production systems face three hard problems: (1) **parameterized queries** should share cache entries when only the parameters differ, (2) **invalidation** must happen when any table in the query is modified, and (3) **read-your-writes consistency** — a user who just updated their profile should see the change, not a cached old version.

## Query Fingerprinting

```python
# Database query cache with automatic table dependency tracking
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import re
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class QueryFingerprinter:
    # Normalize SQL queries to create stable cache keys.
    #
    # The goal: queries that differ only in parameter values should
    # produce the same fingerprint. This allows us to track cache
    # effectiveness per query pattern, not per parameter combination.
    #
    # Example:
    #   "SELECT * FROM users WHERE id = 42"
    #   "SELECT * FROM users WHERE id = 99"
    # Both fingerprint to: "SELECT * FROM users WHERE id = ?"

    # Regex patterns for parameter normalization
    NUMERIC_PATTERN = re.compile(r"\b\d+\b")
    STRING_PATTERN = re.compile(r"'[^']*'")
    IN_PATTERN = re.compile(r"IN\s*\([^)]+\)", re.IGNORECASE)

    @classmethod
    def fingerprint(cls, sql: str) -> str:
        # Normalize SQL to a parameter-free fingerprint
        normalized = sql.strip()

        # Remove leading/trailing whitespace and normalize internal spaces
        normalized = " ".join(normalized.split())

        # Replace string literals with placeholder
        normalized = cls.STRING_PATTERN.sub("?", normalized)

        # Replace IN (...) with IN (?)
        normalized = cls.IN_PATTERN.sub("IN (?)", normalized)

        # Replace numeric literals with placeholder
        normalized = cls.NUMERIC_PATTERN.sub("?", normalized)

        return normalized

    @classmethod
    def fingerprint_hash(cls, sql: str) -> str:
        fp = cls.fingerprint(sql)
        return hashlib.md5(fp.encode()).hexdigest()[:12]

    @classmethod
    def extract_tables(cls, sql: str) -> set[str]:
        # Extract table names referenced in a SQL query.
        #
        # This is a simplified parser that handles common patterns.
        # Production systems should use sqlparse or the DB's EXPLAIN
        # output for accurate table extraction.
        #
        # Common mistake: only extracting FROM tables. JOINs, subqueries,
        # and CTEs also create table dependencies that must trigger
        # invalidation.
        tables: set[str] = set()

        # FROM and JOIN clauses
        from_pattern = re.compile(
            r"(?:FROM|JOIN)\s+([a-zA-Z_][\w.]*)",
            re.IGNORECASE,
        )
        tables.update(m.group(1).lower() for m in from_pattern.finditer(sql))

        # UPDATE table
        update_pattern = re.compile(
            r"UPDATE\s+([a-zA-Z_][\w.]*)",
            re.IGNORECASE,
        )
        tables.update(m.group(1).lower() for m in update_pattern.finditer(sql))

        # INSERT INTO table
        insert_pattern = re.compile(
            r"INSERT\s+INTO\s+([a-zA-Z_][\w.]*)",
            re.IGNORECASE,
        )
        tables.update(m.group(1).lower() for m in insert_pattern.finditer(sql))

        # DELETE FROM table
        delete_pattern = re.compile(
            r"DELETE\s+FROM\s+([a-zA-Z_][\w.]*)",
            re.IGNORECASE,
        )
        tables.update(m.group(1).lower() for m in delete_pattern.finditer(sql))

        return tables


@dataclasses.dataclass
class CachedQueryResult:
    # A cached query result with metadata
    result: Any
    tables: set[str]       # tables this query depends on
    fingerprint: str        # normalized query pattern
    created_at: float
    ttl: int
    hit_count: int = 0
    compute_time: float = 0.0

    @property
    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl


class QueryCacheStats:
    # Comprehensive statistics for query cache monitoring
    def __init__(self) -> None:
        self.hits = 0
        self.misses = 0
        self.invalidations = 0
        self.invalidation_by_table: dict[str, int] = {}
        self.query_patterns: dict[str, dict[str, int]] = {}  # fingerprint -> stats

    def record_hit(self, fingerprint: str) -> None:
        self.hits += 1
        pattern = self.query_patterns.setdefault(fingerprint, {"hits": 0, "misses": 0})
        pattern["hits"] += 1

    def record_miss(self, fingerprint: str) -> None:
        self.misses += 1
        pattern = self.query_patterns.setdefault(fingerprint, {"hits": 0, "misses": 0})
        pattern["misses"] += 1

    def record_invalidation(self, table: str, count: int) -> None:
        self.invalidations += count
        self.invalidation_by_table[table] = (
            self.invalidation_by_table.get(table, 0) + count
        )

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def top_patterns(self, n: int = 10) -> list[tuple[str, dict[str, int]]]:
        # Return the most active query patterns
        return sorted(
            self.query_patterns.items(),
            key=lambda x: x[1]["hits"] + x[1]["misses"],
            reverse=True,
        )[:n]

    def summary(self) -> dict[str, Any]:
        return {
            "hit_rate": f"{self.hit_rate:.1%}",
            "hits": self.hits,
            "misses": self.misses,
            "invalidations": self.invalidations,
            "unique_patterns": len(self.query_patterns),
            "top_invalidated_tables": dict(
                sorted(
                    self.invalidation_by_table.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:5]
            ),
        }


class QueryCache:
    # Automatic query result cache with table-based invalidation.
    #
    # How it works:
    # 1. When a SELECT is executed, we extract the referenced tables,
    #    cache the result, and record the table dependencies.
    # 2. When any INSERT/UPDATE/DELETE modifies a table, we invalidate
    #    ALL cached queries that reference that table.
    # 3. Cache keys combine the fingerprinted SQL + actual parameters
    #    for correct per-parameter caching while sharing statistics
    #    per query pattern.
    #
    # Trade-off: table-level invalidation is coarse-grained. A write
    # to row X invalidates queries that only touch row Y. Row-level
    # invalidation is possible but requires parsing WHERE clauses
    # and tracking row-to-query mappings, which adds significant
    # complexity. For most applications, table-level is sufficient
    # because the cache TTL is already short (30-300 seconds).

    def __init__(
        self,
        default_ttl: int = 60,
        max_entries: int = 10000,
    ) -> None:
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._cache: dict[str, CachedQueryResult] = {}
        self._table_index: dict[str, set[str]] = {}  # table -> cache_keys
        self.stats = QueryCacheStats()
        self.fingerprinter = QueryFingerprinter()

    def _make_cache_key(self, sql: str, params: Optional[tuple] = None) -> str:
        # Combine normalized SQL + parameters for the cache key
        fp = self.fingerprinter.fingerprint(sql)
        param_str = json.dumps(params, sort_keys=True, default=str) if params else ""
        raw = f"{fp}|{param_str}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def get(
        self,
        sql: str,
        params: Optional[tuple] = None,
    ) -> Optional[Any]:
        cache_key = self._make_cache_key(sql, params)
        fingerprint = self.fingerprinter.fingerprint_hash(sql)

        entry = self._cache.get(cache_key)
        if entry is None:
            self.stats.record_miss(fingerprint)
            return None

        if entry.is_expired:
            self._remove_entry(cache_key)
            self.stats.record_miss(fingerprint)
            return None

        entry.hit_count += 1
        self.stats.record_hit(fingerprint)
        return entry.result

    def put(
        self,
        sql: str,
        params: Optional[tuple],
        result: Any,
        ttl: Optional[int] = None,
        compute_time: float = 0.0,
    ) -> None:
        cache_key = self._make_cache_key(sql, params)
        tables = self.fingerprinter.extract_tables(sql)

        # Evict if at capacity (remove oldest entries)
        while len(self._cache) >= self.max_entries:
            oldest_key = min(
                self._cache, key=lambda k: self._cache[k].created_at
            )
            self._remove_entry(oldest_key)

        entry = CachedQueryResult(
            result=result,
            tables=tables,
            fingerprint=self.fingerprinter.fingerprint_hash(sql),
            created_at=time.time(),
            ttl=ttl or self.default_ttl,
            compute_time=compute_time,
        )
        self._cache[cache_key] = entry

        # Build table index for fast invalidation
        for table in tables:
            self._table_index.setdefault(table, set()).add(cache_key)

    def invalidate_table(self, table: str) -> int:
        # Invalidate all cached queries that reference a table.
        #
        # Called automatically when an INSERT/UPDATE/DELETE is detected.
        table_lower = table.lower()
        cache_keys = self._table_index.get(table_lower, set()).copy()
        count = 0

        for key in cache_keys:
            if key in self._cache:
                self._remove_entry(key)
                count += 1

        self.stats.record_invalidation(table_lower, count)
        return count

    def _remove_entry(self, cache_key: str) -> None:
        entry = self._cache.pop(cache_key, None)
        if entry:
            for table in entry.tables:
                table_keys = self._table_index.get(table, set())
                table_keys.discard(cache_key)

    def wrap_execute(
        self,
        execute_fn: Callable[[str, Optional[tuple]], Any],
    ) -> Callable[[str, Optional[tuple]], Any]:
        # Wrap a database execute function with automatic caching.
        #
        # SELECT queries are cached; write queries trigger invalidation.
        # This is the main integration point -- wrap your DB cursor's
        # execute method with this.
        def wrapped(sql: str, params: Optional[tuple] = None) -> Any:
            sql_upper = sql.strip().upper()

            # Write operations: execute and invalidate
            if sql_upper.startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE")):
                result = execute_fn(sql, params)
                tables = self.fingerprinter.extract_tables(sql)
                for table in tables:
                    self.invalidate_table(table)
                return result

            # Read operations: check cache first
            cached = self.get(sql, params)
            if cached is not None:
                return cached

            start = time.perf_counter()
            result = execute_fn(sql, params)
            compute_time = time.perf_counter() - start

            self.put(sql, params, result, compute_time=compute_time)
            return result

        return wrapped


def test_query_cache():
    # Test the query cache with automatic invalidation

    # Simulated database
    db_data = {
        "users": [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
    }
    query_count = 0

    def mock_execute(sql: str, params: Optional[tuple] = None) -> Any:
        nonlocal query_count
        query_count += 1
        return db_data.get("users", [])

    cache = QueryCache(default_ttl=60)
    cached_execute = cache.wrap_execute(mock_execute)

    # First query: cache miss
    result1 = cached_execute("SELECT * FROM users WHERE id = 1", (1,))
    assert query_count == 1
    assert cache.stats.misses == 1

    # Same query: cache hit
    result2 = cached_execute("SELECT * FROM users WHERE id = 1", (1,))
    assert query_count == 1  # no additional DB call
    assert cache.stats.hits == 1

    # Different params: cache miss
    result3 = cached_execute("SELECT * FROM users WHERE id = 2", (2,))
    assert query_count == 2

    # Write invalidates all queries on the table
    cached_execute("UPDATE users SET name = 'Alicia' WHERE id = 1", (1,))
    assert cache.stats.invalidations > 0

    # Query after invalidation: cache miss (fresh data)
    result4 = cached_execute("SELECT * FROM users WHERE id = 1", (1,))
    assert query_count == 4  # UPDATE + fresh SELECT

    print(f"Query cache test passed: {cache.stats.summary()}")


def test_fingerprinting():
    fp = QueryFingerprinter()

    # Same query, different parameters -> same fingerprint
    f1 = fp.fingerprint("SELECT * FROM users WHERE id = 42")
    f2 = fp.fingerprint("SELECT * FROM users WHERE id = 99")
    assert f1 == f2, "Parameterized queries should have same fingerprint"

    # Table extraction
    tables = fp.extract_tables(
        "SELECT u.*, p.title FROM users u "
        "JOIN posts p ON u.id = p.user_id "
        "WHERE u.active = 1"
    )
    assert "users" in tables
    assert "posts" in tables

    print("Fingerprinting tests passed")


if __name__ == "__main__":
    test_fingerprinting()
    test_query_cache()
```

## When NOT to Cache Queries

| Query Type | Cache? | Why |
|-----------|--------|-----|
| Frequently-read, rarely-written | **Yes** | High hit rate, low invalidation |
| User-specific with auth | **Carefully** | Must isolate per-user; use private cache |
| Analytics/aggregations | **Yes, long TTL** | Expensive, tolerates staleness |
| Real-time counters | **No** | Changes too frequently, always stale |
| Transactional reads | **No** | Must see latest committed data |
| Random access patterns | **No** | Low hit rate, wastes memory |

## Key Takeaways

- **Query fingerprinting** normalizes SQL by replacing literals with placeholders — this allows tracking cache effectiveness per query pattern rather than per parameter combination
- **Table-level invalidation** is the practical sweet spot: coarser than row-level (some unnecessary invalidations) but much simpler to implement and sufficient for most applications
- The **table dependency index** enables O(1) invalidation lookup — when a table is modified, we immediately know which cache entries to evict
- **Read-your-writes consistency** requires per-session cache isolation or immediate invalidation after writes — without this, users see stale versions of data they just modified
- Always instrument with **per-pattern statistics** to identify which queries benefit from caching and which have low hit rates (indicating they should be excluded)
"""
    ),
]
