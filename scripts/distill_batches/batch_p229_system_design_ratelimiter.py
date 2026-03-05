"""Rate limiter and quota system design — token bucket, sliding window, distributed rate limiting, quota management, and client retry patterns."""

PAIRS = [
    (
        "system-design/rate-limit-algorithms",
        "Implement token bucket and sliding window rate limiting algorithms with comparison of trade-offs.",
        '''Token bucket and sliding window rate limiting algorithms:

```python
# --- rate_limiters.py --- Core rate limiting algorithms ---

from __future__ import annotations

import time
import threading
import logging
from dataclasses import dataclass
from typing import Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    limit: int                    # maximum requests in window
    remaining: int                # requests remaining
    reset_at: float               # Unix timestamp when window resets
    retry_after: Optional[float] = None  # seconds until next allowed request


class RateLimiter(ABC):
    """Abstract base for rate limiters."""

    @abstractmethod
    def allow(self, key: str) -> RateLimitResult:
        """Check if a request is allowed."""
        ...

    @abstractmethod
    def reset(self, key: str) -> None:
        """Reset rate limit state for a key."""
        ...


class TokenBucketLimiter(RateLimiter):
    """Token Bucket algorithm.

    Tokens are added at a constant rate. Each request consumes one token.
    If no tokens remain, the request is rejected.

    Properties:
    - Allows bursts up to bucket capacity
    - Smooths out request rate over time
    - Memory: O(1) per key (only stores tokens + timestamp)

    Analogy: A bucket that fills with tokens at a steady rate.
    You can spend tokens (make requests) as fast as you want,
    but you can only have at most `capacity` tokens saved up.
    """

    def __init__(self, rate: float, capacity: int):
        """
        Args:
            rate: Tokens added per second (e.g., 10 = 10 req/s)
            capacity: Maximum tokens (burst size)
        """
        self.rate = rate
        self.capacity = capacity
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_time)
        self._lock = threading.Lock()

    def allow(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Check if request is allowed, consuming tokens if so."""
        with self._lock:
            now = time.time()

            if key in self._buckets:
                current_tokens, last_time = self._buckets[key]
            else:
                current_tokens, last_time = float(self.capacity), now

            # Add tokens based on elapsed time
            elapsed = now - last_time
            current_tokens = min(
                self.capacity,
                current_tokens + elapsed * self.rate,
            )

            if current_tokens >= tokens:
                # Allow: consume tokens
                current_tokens -= tokens
                self._buckets[key] = (current_tokens, now)

                return RateLimitResult(
                    allowed=True,
                    limit=self.capacity,
                    remaining=int(current_tokens),
                    reset_at=now + (self.capacity - current_tokens) / self.rate,
                )
            else:
                # Reject: not enough tokens
                self._buckets[key] = (current_tokens, now)
                wait_time = (tokens - current_tokens) / self.rate

                return RateLimitResult(
                    allowed=False,
                    limit=self.capacity,
                    remaining=0,
                    reset_at=now + wait_time,
                    retry_after=wait_time,
                )

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)


class FixedWindowLimiter(RateLimiter):
    """Fixed Window algorithm.

    Divides time into fixed windows. Counts requests per window.
    Resets count at the start of each window.

    Properties:
    - Simple and memory-efficient
    - Can allow 2x burst at window boundaries
    - O(1) per key
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: dict[str, tuple[int, int]] = {}  # key -> (count, window_id)
        self._lock = threading.Lock()

    def allow(self, key: str) -> RateLimitResult:
        with self._lock:
            now = time.time()
            window_id = int(now // self.window_seconds)
            window_end = (window_id + 1) * self.window_seconds

            if key in self._windows:
                count, stored_window = self._windows[key]
                if stored_window != window_id:
                    # New window — reset counter
                    count = 0
            else:
                count = 0

            if count < self.max_requests:
                count += 1
                self._windows[key] = (count, window_id)
                return RateLimitResult(
                    allowed=True,
                    limit=self.max_requests,
                    remaining=self.max_requests - count,
                    reset_at=window_end,
                )
            else:
                self._windows[key] = (count, window_id)
                return RateLimitResult(
                    allowed=False,
                    limit=self.max_requests,
                    remaining=0,
                    reset_at=window_end,
                    retry_after=window_end - now,
                )

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)


class SlidingWindowLogLimiter(RateLimiter):
    """Sliding Window Log algorithm.

    Maintains a log of all request timestamps in the window.
    Most accurate but highest memory usage.

    Properties:
    - Perfectly accurate (no boundary issues)
    - Memory: O(N) per key (stores all timestamps)
    - Slower for high-volume keys
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._logs: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> RateLimitResult:
        with self._lock:
            now = time.time()
            window_start = now - self.window_seconds

            if key not in self._logs:
                self._logs[key] = []

            # Remove expired entries
            self._logs[key] = [
                ts for ts in self._logs[key] if ts > window_start
            ]

            count = len(self._logs[key])

            if count < self.max_requests:
                self._logs[key].append(now)
                return RateLimitResult(
                    allowed=True,
                    limit=self.max_requests,
                    remaining=self.max_requests - count - 1,
                    reset_at=self._logs[key][0] + self.window_seconds if self._logs[key] else now + self.window_seconds,
                )
            else:
                oldest = self._logs[key][0]
                return RateLimitResult(
                    allowed=False,
                    limit=self.max_requests,
                    remaining=0,
                    reset_at=oldest + self.window_seconds,
                    retry_after=oldest + self.window_seconds - now,
                )

    def reset(self, key: str) -> None:
        with self._lock:
            self._logs.pop(key, None)


class SlidingWindowCounterLimiter(RateLimiter):
    """Sliding Window Counter algorithm (hybrid).

    Combines fixed window efficiency with sliding window accuracy.
    Uses weighted average of current and previous window counts.

    Properties:
    - Good accuracy (no 2x burst problem)
    - O(1) memory per key
    - Best trade-off for most systems
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # key -> (prev_count, curr_count, curr_window_id)
        self._counters: dict[str, tuple[int, int, int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> RateLimitResult:
        with self._lock:
            now = time.time()
            window_id = int(now // self.window_seconds)
            window_start = window_id * self.window_seconds
            window_elapsed = now - window_start
            window_weight = window_elapsed / self.window_seconds

            if key in self._counters:
                prev_count, curr_count, stored_window = self._counters[key]
                if stored_window == window_id:
                    pass  # same window
                elif stored_window == window_id - 1:
                    prev_count = curr_count
                    curr_count = 0
                else:
                    prev_count = 0
                    curr_count = 0
            else:
                prev_count = 0
                curr_count = 0

            # Weighted estimate of requests in the sliding window
            estimated = prev_count * (1 - window_weight) + curr_count

            if estimated < self.max_requests:
                curr_count += 1
                self._counters[key] = (prev_count, curr_count, window_id)
                remaining = max(0, int(self.max_requests - estimated - 1))
                return RateLimitResult(
                    allowed=True,
                    limit=self.max_requests,
                    remaining=remaining,
                    reset_at=window_start + self.window_seconds,
                )
            else:
                self._counters[key] = (prev_count, curr_count, window_id)
                return RateLimitResult(
                    allowed=False,
                    limit=self.max_requests,
                    remaining=0,
                    reset_at=window_start + self.window_seconds,
                    retry_after=window_start + self.window_seconds - now,
                )

    def reset(self, key: str) -> None:
        with self._lock:
            self._counters.pop(key, None)
```

```python
# --- comparison.py --- Algorithm comparison and selection ---

from dataclasses import dataclass


@dataclass
class AlgorithmProfile:
    name: str
    memory_per_key: str
    accuracy: str
    burst_behavior: str
    best_for: str


ALGORITHM_COMPARISON = [
    AlgorithmProfile(
        name="Token Bucket",
        memory_per_key="O(1) — 2 floats",
        accuracy="High",
        burst_behavior="Allows bursts up to capacity, then smooths",
        best_for="API rate limiting with burst tolerance",
    ),
    AlgorithmProfile(
        name="Fixed Window",
        memory_per_key="O(1) — 1 int + 1 int",
        accuracy="Medium — 2x burst at boundaries",
        burst_behavior="Can allow 2x at window boundary",
        best_for="Simple counters, low-precision limits",
    ),
    AlgorithmProfile(
        name="Sliding Window Log",
        memory_per_key="O(N) — N timestamps",
        accuracy="Perfect",
        burst_behavior="No boundary issues",
        best_for="Low-volume, high-accuracy (payments, auth)",
    ),
    AlgorithmProfile(
        name="Sliding Window Counter",
        memory_per_key="O(1) — 3 values",
        accuracy="High (weighted estimate)",
        burst_behavior="Smooth, no boundary spikes",
        best_for="General-purpose API rate limiting",
    ),
    AlgorithmProfile(
        name="Leaky Bucket",
        memory_per_key="O(1) — queue depth",
        accuracy="High",
        burst_behavior="Smooths all bursts (constant output rate)",
        best_for="Traffic shaping, network queues",
    ),
]
```

```python
# --- example_usage.py --- Using rate limiters ---

from rate_limiters import (
    TokenBucketLimiter,
    SlidingWindowCounterLimiter,
    RateLimitResult,
)


# Token bucket: 100 requests per second, burst of 200
api_limiter = TokenBucketLimiter(rate=100, capacity=200)

# Sliding window: 1000 requests per hour
hourly_limiter = SlidingWindowCounterLimiter(
    max_requests=1000, window_seconds=3600
)


def handle_request(user_id: str) -> dict:
    """Check rate limit before processing request."""
    # Check per-second rate
    result = api_limiter.allow(f"user:{user_id}")
    if not result.allowed:
        return {
            "error": "rate_limited",
            "retry_after": result.retry_after,
            "limit": result.limit,
            "remaining": result.remaining,
        }

    # Check hourly quota
    hourly_result = hourly_limiter.allow(f"user:{user_id}:hourly")
    if not hourly_result.allowed:
        return {
            "error": "quota_exceeded",
            "retry_after": hourly_result.retry_after,
        }

    # Process request...
    return {"status": "ok", "remaining": result.remaining}
```

| Algorithm | Memory | Accuracy | Burst | Complexity | Recommendation |
|-----------|--------|----------|-------|------------|---------------|
| Token Bucket | O(1) | High | Controlled bursts | Low | Default for APIs |
| Fixed Window | O(1) | Medium | 2x at boundary | Lowest | Simple counters |
| Sliding Log | O(N) | Perfect | None | Medium | Low-volume, precise |
| Sliding Counter | O(1) | High | Minimal | Low | Best general-purpose |
| Leaky Bucket | O(1) | High | None (smoothed) | Low | Traffic shaping |

Key patterns:
1. Token bucket is the most common choice — it allows controlled bursts and smooth rate limiting
2. Sliding window counter is the best trade-off between accuracy and memory efficiency
3. Fixed window has a 2x burst problem at boundaries — avoid for precise rate limiting
4. Sliding window log is perfectly accurate but uses O(N) memory per key — use for low-volume
5. Choose based on requirements: burst tolerance (token bucket), accuracy (sliding log), memory (counter)'''
    ),
    (
        "system-design/distributed-rate-limiting",
        "Design a distributed rate limiter using Redis with atomic operations, cluster-safe algorithms, and failover strategies.",
        '''Distributed rate limiting with Redis:

```python
# --- redis_rate_limiter.py --- Redis-backed distributed rate limiter ---

from __future__ import annotations

import time
import logging
from typing import Optional
from dataclasses import dataclass

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: float
    retry_after: Optional[float] = None


class RedisTokenBucket:
    """Distributed token bucket using Redis + Lua script.

    Lua scripts execute atomically in Redis, ensuring
    consistency across multiple application servers.
    """

    # Lua script for atomic token bucket operation
    LUA_SCRIPT = """
    local key = KEYS[1]
    local rate = tonumber(ARGV[1])          -- tokens per second
    local capacity = tonumber(ARGV[2])      -- max tokens
    local now = tonumber(ARGV[3])           -- current time
    local requested = tonumber(ARGV[4])     -- tokens to consume

    -- Get current state
    local data = redis.call('HMGET', key, 'tokens', 'last_time')
    local tokens = tonumber(data[1])
    local last_time = tonumber(data[2])

    -- Initialize if new key
    if tokens == nil then
        tokens = capacity
        last_time = now
    end

    -- Add tokens based on elapsed time
    local elapsed = math.max(0, now - last_time)
    tokens = math.min(capacity, tokens + elapsed * rate)

    local allowed = 0
    local remaining = tokens

    if tokens >= requested then
        tokens = tokens - requested
        allowed = 1
        remaining = tokens
    end

    -- Update state
    redis.call('HMSET', key, 'tokens', tokens, 'last_time', now)
    redis.call('EXPIRE', key, math.ceil(capacity / rate) + 10)

    local reset_at = now + (capacity - tokens) / rate

    return {allowed, math.floor(remaining), tostring(reset_at)}
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        rate: float,
        capacity: int,
        prefix: str = "rl:",
    ):
        self.redis = redis_client
        self.rate = rate
        self.capacity = capacity
        self.prefix = prefix
        self._script_sha: Optional[str] = None

    async def _ensure_script(self) -> str:
        """Load Lua script into Redis (cached)."""
        if not self._script_sha:
            self._script_sha = await self.redis.script_load(self.LUA_SCRIPT)
        return self._script_sha

    async def allow(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Check rate limit atomically via Lua script."""
        sha = await self._ensure_script()
        now = time.time()
        redis_key = f"{self.prefix}{key}"

        try:
            result = await self.redis.evalsha(
                sha,
                1,           # number of keys
                redis_key,   # KEYS[1]
                str(self.rate),
                str(self.capacity),
                str(now),
                str(tokens),
            )

            allowed = bool(result[0])
            remaining = int(result[1])
            reset_at = float(result[2])

            return RateLimitResult(
                allowed=allowed,
                limit=self.capacity,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=None if allowed else max(0, reset_at - now),
            )

        except redis.exceptions.NoScriptError:
            # Script evicted from cache — reload
            self._script_sha = None
            return await self.allow(key, tokens)


class RedisSlidingWindowCounter:
    """Distributed sliding window counter using Redis sorted sets.

    Uses ZRANGEBYSCORE to count requests in the sliding window.
    Atomic via Lua script.
    """

    LUA_SCRIPT = """
    local key = KEYS[1]
    local max_requests = tonumber(ARGV[1])
    local window_seconds = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local request_id = ARGV[4]

    local window_start = now - window_seconds

    -- Remove expired entries
    redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

    -- Count current entries
    local count = redis.call('ZCARD', key)

    if count < max_requests then
        -- Add this request
        redis.call('ZADD', key, now, request_id)
        redis.call('EXPIRE', key, window_seconds + 10)

        return {1, max_requests - count - 1, tostring(now + window_seconds)}
    else
        -- Get oldest entry to calculate retry_after
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local reset_at = now + window_seconds

        if #oldest > 0 then
            reset_at = tonumber(oldest[2]) + window_seconds
        end

        return {0, 0, tostring(reset_at)}
    end
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        max_requests: int,
        window_seconds: int,
        prefix: str = "rl:sw:",
    ):
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.prefix = prefix
        self._script_sha: Optional[str] = None

    async def _ensure_script(self) -> str:
        if not self._script_sha:
            self._script_sha = await self.redis.script_load(self.LUA_SCRIPT)
        return self._script_sha

    async def allow(self, key: str) -> RateLimitResult:
        """Check sliding window rate limit."""
        import uuid
        sha = await self._ensure_script()
        now = time.time()
        redis_key = f"{self.prefix}{key}"
        request_id = f"{now}:{uuid.uuid4().hex[:8]}"

        try:
            result = await self.redis.evalsha(
                sha,
                1,
                redis_key,
                str(self.max_requests),
                str(self.window_seconds),
                str(now),
                request_id,
            )

            allowed = bool(result[0])
            remaining = int(result[1])
            reset_at = float(result[2])

            return RateLimitResult(
                allowed=allowed,
                limit=self.max_requests,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=None if allowed else max(0, reset_at - now),
            )
        except redis.exceptions.NoScriptError:
            self._script_sha = None
            return await self.allow(key)
```

```python
# --- failover.py --- Rate limiter failover strategies ---

from __future__ import annotations

import logging
import time
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class ResilientRateLimiter:
    """Rate limiter with failover for Redis outages.

    Strategies when Redis is down:
    1. Allow all (fail open) — risk of overload but no user impact
    2. Deny all (fail closed) — safe but blocks users
    3. Local fallback — use in-memory limiter temporarily
    4. Circuit breaker — switch to local after N failures
    """

    def __init__(
        self,
        primary: RedisTokenBucket,
        local_fallback: TokenBucketLimiter,
        fail_open: bool = True,
        circuit_break_threshold: int = 5,
        circuit_break_duration: float = 30.0,
    ):
        self.primary = primary
        self.fallback = local_fallback
        self.fail_open = fail_open
        self.circuit_break_threshold = circuit_break_threshold
        self.circuit_break_duration = circuit_break_duration

        self._failure_count = 0
        self._circuit_open_until: float = 0

    async def allow(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Check rate limit with automatic failover."""
        # Check circuit breaker
        if time.time() < self._circuit_open_until:
            logger.debug("Circuit open — using local fallback")
            return self.fallback.allow(key, tokens)

        try:
            result = await self.primary.allow(key, tokens)
            self._failure_count = 0  # reset on success
            return result

        except redis.exceptions.ConnectionError as e:
            self._failure_count += 1
            logger.warning(
                f"Redis connection error ({self._failure_count}): {e}"
            )

            if self._failure_count >= self.circuit_break_threshold:
                self._circuit_open_until = (
                    time.time() + self.circuit_break_duration
                )
                logger.warning(
                    f"Circuit breaker OPEN for {self.circuit_break_duration}s"
                )

            # Failover
            if self.fail_open:
                logger.info("Fail open: allowing request")
                return RateLimitResult(
                    allowed=True,
                    limit=self.primary.capacity,
                    remaining=-1,  # unknown
                    reset_at=0,
                )
            else:
                return self.fallback.allow(key, tokens)

        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            if self.fail_open:
                return RateLimitResult(
                    allowed=True, limit=0, remaining=-1, reset_at=0,
                )
            return self.fallback.allow(key, tokens)


# --- Multi-level rate limiter ---

class MultiLevelLimiter:
    """Apply multiple rate limits simultaneously.

    Example: 10 req/s AND 1000 req/hour AND 10000 req/day
    """

    def __init__(self, limiters: list[tuple[str, RateLimiter]]):
        """Args: list of (name, limiter) tuples."""
        self.limiters = limiters

    async def allow(self, key: str) -> RateLimitResult:
        """Check all levels — reject if ANY level is exceeded."""
        results = []

        for name, limiter in self.limiters:
            full_key = f"{key}:{name}"
            if hasattr(limiter, 'allow') and asyncio.iscoroutinefunction(limiter.allow):
                result = await limiter.allow(full_key)
            else:
                result = limiter.allow(full_key)
            results.append((name, result))

            if not result.allowed:
                logger.debug(f"Rate limited by {name}: {key}")
                return result

        # All passed — return the result with the lowest remaining
        min_result = min(results, key=lambda x: x[1].remaining)
        return min_result[1]


import asyncio
```

```python
# --- middleware.py --- FastAPI rate limiting middleware ---

from fastapi import FastAPI, Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import time


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    def __init__(
        self,
        app: FastAPI,
        limiter: ResilientRateLimiter,
        key_func=None,
    ):
        super().__init__(app)
        self.limiter = limiter
        self.key_func = key_func or self._default_key

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/readiness"):
            return await call_next(request)

        # Determine rate limit key
        key = self.key_func(request)

        # Check rate limit
        result = await self.limiter.allow(key)

        if not result.allowed:
            return Response(
                content='{"error": "rate_limited", "retry_after": '
                        f'{result.retry_after:.1f}}}',
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": str(result.remaining),
                    "X-RateLimit-Reset": str(int(result.reset_at)),
                    "Retry-After": str(int(result.retry_after or 1)),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to all responses
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))

        return response

    @staticmethod
    def _default_key(request: Request) -> str:
        """Default key: API key or IP address."""
        # Prefer API key for authenticated requests
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"apikey:{api_key}"

        # Fall back to IP for unauthenticated
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"
```

| Failover Strategy | Risk | Availability | Use when |
|------------------|------|-------------|----------|
| Fail open | Overload if prolonged | Highest | User-facing APIs (prefer availability) |
| Fail closed | Users blocked | Lowest | Security-critical (auth, payments) |
| Local fallback | Inconsistent across servers | Medium | Good default for most APIs |
| Circuit breaker | Brief exposure | High | Combines fail-open with auto-recovery |

Key patterns:
1. Use Redis Lua scripts for atomic rate limit operations across multiple servers
2. Implement circuit breaker pattern to fall back to local limiter when Redis is down
3. Apply multi-level rate limiting (per-second AND per-hour) for both burst and sustained control
4. Always return rate limit headers (`X-RateLimit-*`) on every response, not just rejections
5. Key by API key for authenticated requests, by IP for unauthenticated requests'''
    ),
    (
        "system-design/api-quota-management",
        "Design an API quota management system with tier-based limits, usage tracking, and quota enforcement.",
        '''API quota management with tier-based limits and usage tracking:

```python
# --- quota_manager.py --- API quota management system ---

from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Any
from dataclasses import dataclass, field

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class QuotaPeriod(Enum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


@dataclass
class QuotaLimit:
    """A single quota limit."""
    name: str                     # "api_calls", "storage_mb", "webhooks"
    limit: int                    # maximum allowed
    period: QuotaPeriod           # reset period
    overage_allowed: bool = False # allow overage with surcharge?
    overage_rate: Decimal = Decimal("0")  # cost per overage unit


@dataclass
class TierConfig:
    """Rate/quota limits for a pricing tier."""
    tier_id: str                  # "free", "pro", "enterprise"
    display_name: str
    quotas: dict[str, QuotaLimit] # quota_name -> limit
    rate_limits: dict[str, tuple[int, int]]  # endpoint -> (requests, seconds)
    features: set[str]            # enabled features


# Tier configurations
TIERS: dict[str, TierConfig] = {
    "free": TierConfig(
        tier_id="free",
        display_name="Free",
        quotas={
            "api_calls": QuotaLimit("api_calls", 1000, QuotaPeriod.DAY),
            "storage_mb": QuotaLimit("storage_mb", 100, QuotaPeriod.MONTH),
            "webhooks": QuotaLimit("webhooks", 5, QuotaPeriod.MONTH),
        },
        rate_limits={
            "default": (10, 1),          # 10 req/s
            "/api/search": (5, 1),       # 5 req/s
            "/api/export": (1, 60),      # 1 req/min
        },
        features={"basic_api", "dashboard"},
    ),
    "pro": TierConfig(
        tier_id="pro",
        display_name="Pro",
        quotas={
            "api_calls": QuotaLimit("api_calls", 50000, QuotaPeriod.DAY),
            "storage_mb": QuotaLimit("storage_mb", 10000, QuotaPeriod.MONTH),
            "webhooks": QuotaLimit("webhooks", 100, QuotaPeriod.MONTH),
        },
        rate_limits={
            "default": (100, 1),         # 100 req/s
            "/api/search": (50, 1),
            "/api/export": (10, 60),
        },
        features={"basic_api", "dashboard", "webhooks", "analytics", "export"},
    ),
    "enterprise": TierConfig(
        tier_id="enterprise",
        display_name="Enterprise",
        quotas={
            "api_calls": QuotaLimit(
                "api_calls", 1000000, QuotaPeriod.DAY,
                overage_allowed=True, overage_rate=Decimal("0.001"),
            ),
            "storage_mb": QuotaLimit(
                "storage_mb", 100000, QuotaPeriod.MONTH,
                overage_allowed=True, overage_rate=Decimal("0.10"),
            ),
            "webhooks": QuotaLimit("webhooks", 1000, QuotaPeriod.MONTH),
        },
        rate_limits={
            "default": (1000, 1),        # 1000 req/s
            "/api/search": (500, 1),
            "/api/export": (100, 60),
        },
        features={"basic_api", "dashboard", "webhooks", "analytics", "export",
                  "sso", "audit_log", "sla", "dedicated_support"},
    ),
}


@dataclass
class QuotaUsage:
    """Current usage for a quota."""
    quota_name: str
    limit: int
    used: int
    remaining: int
    period: QuotaPeriod
    period_start: datetime
    period_end: datetime
    overage: int = 0
    overage_cost: Decimal = Decimal("0")


class QuotaManager:
    """Track and enforce API quotas."""

    def __init__(self, redis_client: redis.Redis, db):
        self.redis = redis_client
        self.db = db

    async def check_quota(
        self,
        org_id: str,
        quota_name: str,
        amount: int = 1,
    ) -> tuple[bool, QuotaUsage]:
        """Check if an operation is within quota.

        Returns (allowed, usage).
        """
        tier = await self._get_tier(org_id)
        quota_limit = tier.quotas.get(quota_name)

        if not quota_limit:
            logger.warning(f"Unknown quota: {quota_name}")
            return True, QuotaUsage(
                quota_name=quota_name, limit=0, used=0, remaining=0,
                period=QuotaPeriod.DAY,
                period_start=datetime.utcnow(), period_end=datetime.utcnow(),
            )

        # Get current usage
        period_key = self._period_key(org_id, quota_name, quota_limit.period)
        current_usage = await self.redis.get(period_key)
        used = int(current_usage) if current_usage else 0

        period_start, period_end = self._period_bounds(quota_limit.period)

        remaining = max(0, quota_limit.limit - used)
        allowed = used + amount <= quota_limit.limit

        # Check overage
        overage = 0
        overage_cost = Decimal("0")
        if not allowed and quota_limit.overage_allowed:
            allowed = True  # allow with overage
            overage = max(0, (used + amount) - quota_limit.limit)
            overage_cost = Decimal(str(overage)) * quota_limit.overage_rate

        usage = QuotaUsage(
            quota_name=quota_name,
            limit=quota_limit.limit,
            used=used,
            remaining=remaining,
            period=quota_limit.period,
            period_start=period_start,
            period_end=period_end,
            overage=overage,
            overage_cost=overage_cost,
        )

        return allowed, usage

    async def consume(
        self,
        org_id: str,
        quota_name: str,
        amount: int = 1,
    ) -> QuotaUsage:
        """Consume quota units (call after successful operation)."""
        tier = await self._get_tier(org_id)
        quota_limit = tier.quotas[quota_name]

        period_key = self._period_key(org_id, quota_name, quota_limit.period)
        ttl = self._period_ttl(quota_limit.period)

        # Atomic increment
        new_count = await self.redis.incrby(period_key, amount)
        if new_count == amount:
            # First usage in this period — set TTL
            await self.redis.expire(period_key, ttl)

        period_start, period_end = self._period_bounds(quota_limit.period)

        return QuotaUsage(
            quota_name=quota_name,
            limit=quota_limit.limit,
            used=new_count,
            remaining=max(0, quota_limit.limit - new_count),
            period=quota_limit.period,
            period_start=period_start,
            period_end=period_end,
        )

    async def get_all_usage(self, org_id: str) -> list[QuotaUsage]:
        """Get usage for all quotas for an organization."""
        tier = await self._get_tier(org_id)
        usage_list = []

        for quota_name, quota_limit in tier.quotas.items():
            _, usage = await self.check_quota(org_id, quota_name, amount=0)
            usage_list.append(usage)

        return usage_list

    async def _get_tier(self, org_id: str) -> TierConfig:
        """Get tier config for an organization."""
        tier_id = await self.redis.get(f"org:{org_id}:tier")
        if not tier_id:
            tier_id = await self.db.fetch_val(
                "SELECT tier FROM organizations WHERE id = :id",
                {"id": org_id},
            )
            if tier_id:
                await self.redis.set(
                    f"org:{org_id}:tier",
                    tier_id if isinstance(tier_id, str) else tier_id.decode(),
                    ex=300,
                )
        tier_str = tier_id.decode() if isinstance(tier_id, bytes) else (tier_id or "free")
        return TIERS.get(tier_str, TIERS["free"])

    def _period_key(self, org_id: str, quota_name: str, period: QuotaPeriod) -> str:
        now = datetime.utcnow()
        if period == QuotaPeriod.MINUTE:
            suffix = now.strftime("%Y%m%d%H%M")
        elif period == QuotaPeriod.HOUR:
            suffix = now.strftime("%Y%m%d%H")
        elif period == QuotaPeriod.DAY:
            suffix = now.strftime("%Y%m%d")
        else:
            suffix = now.strftime("%Y%m")
        return f"quota:{org_id}:{quota_name}:{suffix}"

    def _period_ttl(self, period: QuotaPeriod) -> int:
        return {
            QuotaPeriod.MINUTE: 120,
            QuotaPeriod.HOUR: 7200,
            QuotaPeriod.DAY: 172800,
            QuotaPeriod.MONTH: 2678400 + 86400,
        }[period]

    def _period_bounds(self, period: QuotaPeriod) -> tuple[datetime, datetime]:
        now = datetime.utcnow()
        if period == QuotaPeriod.DAY:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == QuotaPeriod.HOUR:
            start = now.replace(minute=0, second=0, microsecond=0)
            end = start + timedelta(hours=1)
        elif period == QuotaPeriod.MONTH:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now.month == 12:
                end = start.replace(year=now.year + 1, month=1)
            else:
                end = start.replace(month=now.month + 1)
        else:
            start = now.replace(second=0, microsecond=0)
            end = start + timedelta(minutes=1)
        return start, end
```

```python
# --- quota_api.py --- Usage API endpoints ---

from fastapi import FastAPI, Depends, HTTPException


@app.get("/api/usage")
async def get_usage(org_id: str = Depends(get_org_id)):
    """Get current usage for all quotas."""
    quota_mgr = get_quota_manager()
    usage_list = await quota_mgr.get_all_usage(org_id)

    return {
        "quotas": [
            {
                "name": u.quota_name,
                "limit": u.limit,
                "used": u.used,
                "remaining": u.remaining,
                "period": u.period.value,
                "period_start": u.period_start.isoformat(),
                "period_end": u.period_end.isoformat(),
                "usage_pct": round(u.used / u.limit * 100, 1) if u.limit > 0 else 0,
                "overage": u.overage,
                "overage_cost": str(u.overage_cost),
            }
            for u in usage_list
        ],
    }


# Alert when approaching quota
async def check_quota_alerts(org_id: str) -> None:
    """Send alerts when usage approaches limits."""
    quota_mgr = get_quota_manager()
    usage_list = await quota_mgr.get_all_usage(org_id)

    for usage in usage_list:
        pct = usage.used / usage.limit * 100 if usage.limit > 0 else 0

        if pct >= 100:
            await send_alert(org_id, f"Quota exceeded: {usage.quota_name}")
        elif pct >= 90:
            await send_alert(org_id, f"Quota at 90%: {usage.quota_name}")
        elif pct >= 75:
            await send_alert(org_id, f"Quota at 75%: {usage.quota_name}")
```

| Tier | API calls/day | Rate limit | Storage | Webhooks |
|------|-------------|-----------|---------|----------|
| Free | 1,000 | 10 req/s | 100 MB | 5 |
| Pro | 50,000 | 100 req/s | 10 GB | 100 |
| Enterprise | 1,000,000+ | 1,000 req/s | 100 GB+ | 1,000 |

Key patterns:
1. Define quotas per tier with separate limits for different resource types
2. Use Redis INCRBY with TTL for atomic, self-expiring quota counters
3. Support overage for enterprise tiers (bill for extra usage instead of blocking)
4. Alert users at 75%, 90%, and 100% of quota usage
5. Expose usage via API so customers can monitor their consumption'''
    ),
    (
        "system-design/rate-limit-headers-retry",
        "Show rate limit HTTP headers and client-side retry patterns including exponential backoff and request queuing.",
        '''Rate limit headers and client retry patterns:

```python
# --- headers.py --- Standard rate limit response headers ---

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RateLimitHeaders:
    """Standard rate limit headers (IETF draft-ietf-httpapi-ratelimit-headers).

    These headers tell clients:
    - How many requests they can make (limit)
    - How many they have left (remaining)
    - When the window resets (reset)
    - How long to wait if limited (retry-after)
    """

    @staticmethod
    def build(
        limit: int,
        remaining: int,
        reset_at: float,
        retry_after: Optional[float] = None,
        policy: Optional[str] = None,
    ) -> dict[str, str]:
        """Build rate limit response headers.

        Standard headers:
        - X-RateLimit-Limit: max requests in window
        - X-RateLimit-Remaining: requests left in window
        - X-RateLimit-Reset: Unix timestamp when window resets
        - Retry-After: seconds to wait (only on 429 responses)

        IETF draft headers (newer):
        - RateLimit-Limit: same as X-RateLimit-Limit
        - RateLimit-Remaining: same as X-RateLimit-Remaining
        - RateLimit-Reset: seconds until reset (not timestamp)
        - RateLimit-Policy: describes the policy (e.g., "100;w=3600")
        """
        headers = {
            # Legacy headers (widely supported)
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, remaining)),
            "X-RateLimit-Reset": str(int(reset_at)),

            # IETF draft headers
            "RateLimit-Limit": str(limit),
            "RateLimit-Remaining": str(max(0, remaining)),
            "RateLimit-Reset": str(max(0, int(reset_at - datetime.utcnow().timestamp()))),
        }

        if retry_after is not None:
            headers["Retry-After"] = str(max(1, int(retry_after)))

        if policy:
            headers["RateLimit-Policy"] = policy
            # Example: "100;w=3600" means 100 requests per 3600 seconds

        return headers

    @staticmethod
    def error_body(
        limit: int,
        remaining: int,
        reset_at: float,
        retry_after: float,
        message: str = "Rate limit exceeded",
    ) -> dict:
        """Standard error response body for 429 responses."""
        return {
            "error": {
                "type": "rate_limit_exceeded",
                "message": message,
                "limit": limit,
                "remaining": remaining,
                "reset_at": int(reset_at),
                "reset_at_iso": datetime.fromtimestamp(reset_at).isoformat(),
                "retry_after_seconds": max(1, int(retry_after)),
            },
        }
```

```python
# --- retry_client.py --- Client-side retry with rate limit awareness ---

from __future__ import annotations

import time
import random
import logging
from typing import Optional, Any
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 5
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    retry_on_status: set[int] = None

    def __post_init__(self):
        if self.retry_on_status is None:
            self.retry_on_status = {429, 500, 502, 503, 504}


class RateLimitAwareClient:
    """HTTP client that respects rate limit headers and retries intelligently."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        retry_config: Optional[RetryConfig] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.config = retry_config or RetryConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

        # Track rate limit state from response headers
        self._rate_limit: Optional[int] = None
        self._rate_remaining: Optional[int] = None
        self._rate_reset: Optional[float] = None

    def request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> requests.Response:
        """Make a request with automatic retry on rate limiting."""
        url = f"{self.base_url}{path}"

        for attempt in range(self.config.max_retries + 1):
            # Pre-check: if we know we're rate limited, wait first
            if self._rate_remaining is not None and self._rate_remaining <= 0:
                wait_time = self._time_until_reset()
                if wait_time > 0:
                    logger.info(
                        f"Pre-emptive wait: {wait_time:.1f}s "
                        f"(rate limit depleted)"
                    )
                    time.sleep(min(wait_time, self.config.max_backoff_seconds))

            try:
                response = self.session.request(method, url, **kwargs)

                # Update rate limit state from headers
                self._update_rate_limit(response)

                if response.status_code == 429:
                    # Rate limited — use Retry-After header
                    retry_after = self._get_retry_after(response)
                    if attempt < self.config.max_retries:
                        logger.warning(
                            f"Rate limited (429). Retry in {retry_after:.1f}s "
                            f"(attempt {attempt + 1}/{self.config.max_retries})"
                        )
                        time.sleep(retry_after)
                        continue
                    else:
                        logger.error("Rate limited: max retries exceeded")
                        response.raise_for_status()

                if response.status_code in self.config.retry_on_status:
                    if attempt < self.config.max_retries:
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(
                            f"Server error {response.status_code}. "
                            f"Retry in {backoff:.1f}s"
                        )
                        time.sleep(backoff)
                        continue

                return response

            except requests.exceptions.ConnectionError:
                if attempt < self.config.max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(f"Connection error. Retry in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                raise

        raise Exception("Max retries exceeded")

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def _update_rate_limit(self, response: requests.Response) -> None:
        """Update internal rate limit state from response headers."""
        headers = response.headers

        limit = headers.get("X-RateLimit-Limit")
        remaining = headers.get("X-RateLimit-Remaining")
        reset_at = headers.get("X-RateLimit-Reset")

        if limit:
            self._rate_limit = int(limit)
        if remaining:
            self._rate_remaining = int(remaining)
        if reset_at:
            self._rate_reset = float(reset_at)

    def _get_retry_after(self, response: requests.Response) -> float:
        """Get wait time from Retry-After header or calculate backoff."""
        retry_after = response.headers.get("Retry-After")

        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        # Fall back to reset time
        if self._rate_reset:
            wait = self._rate_reset - time.time()
            if wait > 0:
                return min(wait, self.config.max_backoff_seconds)

        return self.config.initial_backoff_seconds

    def _time_until_reset(self) -> float:
        """Calculate time until rate limit window resets."""
        if self._rate_reset:
            return max(0, self._rate_reset - time.time())
        return 0

    def _calculate_backoff(self, attempt: int) -> float:
        """Exponential backoff with optional jitter."""
        backoff = self.config.initial_backoff_seconds * (
            self.config.backoff_multiplier ** attempt
        )
        backoff = min(backoff, self.config.max_backoff_seconds)

        if self.config.jitter:
            backoff = backoff * (0.5 + random.random())

        return backoff

    @property
    def rate_limit_info(self) -> dict:
        """Current rate limit state."""
        return {
            "limit": self._rate_limit,
            "remaining": self._rate_remaining,
            "reset_at": self._rate_reset,
            "depleted": (
                self._rate_remaining is not None
                and self._rate_remaining <= 0
            ),
        }
```

```python
# --- request_queue.py --- Client-side request queuing ---

from __future__ import annotations

import asyncio
import time
import logging
from typing import Any, Callable, Awaitable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class RequestQueue:
    """Client-side request queue that respects rate limits.

    Instead of immediate retry on 429, queue requests and
    drain at the allowed rate.
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        requests_per_second: float = 10.0,
    ):
        self.max_concurrent = max_concurrent
        self.rps = requests_per_second
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._interval = 1.0 / requests_per_second
        self._last_request_time: float = 0
        self._lock = asyncio.Lock()

    async def execute(
        self,
        func: Callable[..., Awaitable[Any]],
        *args,
        **kwargs,
    ) -> Any:
        """Execute a function with rate-limited concurrency."""
        async with self._semaphore:
            # Ensure minimum interval between requests
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_request_time
                if elapsed < self._interval:
                    await asyncio.sleep(self._interval - elapsed)
                self._last_request_time = time.monotonic()

            return await func(*args, **kwargs)

    async def execute_batch(
        self,
        func: Callable[..., Awaitable[Any]],
        items: list[Any],
    ) -> list[Any]:
        """Execute a function for each item with rate limiting.

        Returns results in the same order as items.
        """
        tasks = [
            self.execute(func, item) for item in items
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)


# Usage:
# queue = RequestQueue(max_concurrent=5, requests_per_second=10)
#
# async def fetch_user(user_id):
#     async with httpx.AsyncClient() as client:
#         response = await client.get(f"https://api.example.com/users/{user_id}")
#         return response.json()
#
# # Process 1000 users without hitting rate limits
# results = await queue.execute_batch(fetch_user, user_ids)
```

| Header | Standard | Value | Purpose |
|--------|----------|-------|---------|
| `X-RateLimit-Limit` | De facto | Integer | Max requests in window |
| `X-RateLimit-Remaining` | De facto | Integer | Requests left in window |
| `X-RateLimit-Reset` | De facto | Unix timestamp | When window resets |
| `Retry-After` | RFC 7231 | Seconds or HTTP date | When to retry (on 429) |
| `RateLimit-Limit` | IETF draft | Integer | Same as X-RateLimit-Limit |
| `RateLimit-Remaining` | IETF draft | Integer | Same as X-RateLimit-Remaining |
| `RateLimit-Reset` | IETF draft | Seconds until reset | Relative, not absolute |
| `RateLimit-Policy` | IETF draft | "100;w=3600" | Policy description |

Key patterns:
1. Always include rate limit headers on ALL responses, not just 429 errors
2. Use `Retry-After` header on 429 responses to tell clients exactly when to retry
3. Clients should pre-check `X-RateLimit-Remaining` and throttle proactively at 0
4. Use exponential backoff with jitter to prevent thundering herd on retry
5. For bulk operations, use a client-side request queue to stay within rate limits automatically'''
    ),
]
