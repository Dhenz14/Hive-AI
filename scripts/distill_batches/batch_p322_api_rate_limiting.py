"""Rate limiting implementations — token bucket, leaky bucket, sliding window, distributed (Redis), adaptive."""

PAIRS = [
    (
        "rate-limiting/token-bucket-implementation",
        "Implement a production-quality token bucket rate limiter in Python with burst support, async compatibility, and per-key tracking.",
        '''Production token bucket rate limiter with burst support and async compatibility:

```python
# --- token_bucket.py --- Thread-safe token bucket rate limiter ---

from __future__ import annotations

import asyncio
import time
import threading
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict


@dataclass
class BucketConfig:
    """Configuration for a token bucket."""
    rate: float         # Tokens per second (sustained rate)
    burst: int          # Maximum tokens (burst capacity)
    initial: int | None = None  # Initial tokens (defaults to burst)

    def __post_init__(self):
        if self.initial is None:
            self.initial = self.burst


@dataclass
class BucketState:
    """Mutable state of a single token bucket."""
    tokens: float
    last_refill: float = field(default_factory=time.monotonic)
    total_allowed: int = 0
    total_denied: int = 0


class TokenBucketLimiter:
    """
    Token bucket rate limiter with:
    - Configurable rate and burst capacity
    - Per-key buckets (e.g., per user, per IP)
    - Thread-safe operation
    - Lazy refill (no background thread)
    - Wait/retry support with computed delay
    - Bucket cleanup for stale entries
    """

    def __init__(self, default_config: BucketConfig) -> None:
        self._default_config = default_config
        self._overrides: dict[str, BucketConfig] = {}
        self._buckets: dict[str, BucketState] = {}
        self._lock = threading.Lock()
        self._stale_threshold = 3600.0  # Clean up buckets idle for 1 hour

    def configure_key(self, key: str, config: BucketConfig) -> None:
        """Override rate limit config for a specific key."""
        self._overrides[key] = config

    def _get_config(self, key: str) -> BucketConfig:
        return self._overrides.get(key, self._default_config)

    def _get_or_create_bucket(self, key: str) -> BucketState:
        if key not in self._buckets:
            config = self._get_config(key)
            self._buckets[key] = BucketState(tokens=float(config.initial or config.burst))
        return self._buckets[key]

    def _refill(self, bucket: BucketState, config: BucketConfig) -> None:
        """Lazily refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            new_tokens = elapsed * config.rate
            bucket.tokens = min(bucket.tokens + new_tokens, float(config.burst))
            bucket.last_refill = now

    def allow(self, key: str = "__default__", cost: int = 1) -> bool:
        """
        Check if request is allowed and consume tokens.
        Returns True if allowed, False if rate limited.
        """
        with self._lock:
            config = self._get_config(key)
            bucket = self._get_or_create_bucket(key)
            self._refill(bucket, config)

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                bucket.total_allowed += 1
                return True
            else:
                bucket.total_denied += 1
                return False

    def wait_time(self, key: str = "__default__", cost: int = 1) -> float:
        """
        Calculate how long to wait before tokens are available.
        Returns 0.0 if request can proceed immediately.
        """
        with self._lock:
            config = self._get_config(key)
            bucket = self._get_or_create_bucket(key)
            self._refill(bucket, config)

            if bucket.tokens >= cost:
                return 0.0
            deficit = cost - bucket.tokens
            return deficit / config.rate

    async def allow_async(self, key: str = "__default__", cost: int = 1) -> bool:
        """Async version — awaits if rate limited (blocking with backoff)."""
        wait = self.wait_time(key, cost)
        if wait > 0:
            await asyncio.sleep(wait)
        return self.allow(key, cost)

    def get_stats(self, key: str = "__default__") -> dict[str, Any]:
        """Get rate limiter stats for a key."""
        with self._lock:
            config = self._get_config(key)
            bucket = self._get_or_create_bucket(key)
            self._refill(bucket, config)
            return {
                "tokens_remaining": round(bucket.tokens, 2),
                "burst_capacity": config.burst,
                "rate_per_second": config.rate,
                "total_allowed": bucket.total_allowed,
                "total_denied": bucket.total_denied,
                "utilization": round(
                    bucket.total_denied / max(bucket.total_allowed + bucket.total_denied, 1), 3
                ),
            }

    def cleanup_stale(self) -> int:
        """Remove buckets that haven't been used recently."""
        now = time.monotonic()
        with self._lock:
            stale_keys = [
                key for key, bucket in self._buckets.items()
                if now - bucket.last_refill > self._stale_threshold
            ]
            for key in stale_keys:
                del self._buckets[key]
            return len(stale_keys)

    def reset(self, key: str) -> None:
        """Reset a specific bucket to full capacity."""
        with self._lock:
            if key in self._buckets:
                config = self._get_config(key)
                self._buckets[key] = BucketState(tokens=float(config.burst))


# ---- FastAPI middleware integration ----

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware using token bucket."""

    def __init__(self, app, limiter: TokenBucketLimiter, key_func=None):
        super().__init__(app)
        self.limiter = limiter
        self.key_func = key_func or self._default_key

    @staticmethod
    def _default_key(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        key = self.key_func(request)
        stats = self.limiter.get_stats(key)

        if not self.limiter.allow(key):
            retry_after = self.limiter.wait_time(key)
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": round(retry_after, 2)},
                headers={
                    "Retry-After": str(int(retry_after) + 1),
                    "X-RateLimit-Limit": str(stats["burst_capacity"]),
                    "X-RateLimit-Remaining": str(int(stats["tokens_remaining"])),
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(stats["burst_capacity"])
        response.headers["X-RateLimit-Remaining"] = str(int(stats["tokens_remaining"]))
        return response
```

Key design decisions:

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| Refill strategy | Lazy (on access) | No background thread needed |
| Thread safety | `threading.Lock` | Simple, correct for sync code |
| Per-key buckets | `dict[str, BucketState]` | Independent limits per user/IP |
| Burst handling | `tokens <= burst` cap | Allow short bursts above sustained rate |
| Stale cleanup | Periodic sweep | Prevent memory leak for ephemeral keys |
| Cost parameter | Configurable per request | Heavy endpoints consume more tokens |

- Token bucket allows **bursts** up to `burst` tokens, then throttles to `rate` tokens/second
- `wait_time()` enables **cooperative rate limiting** — caller knows exactly how long to wait
- Middleware returns standard `429 Too Many Requests` with `Retry-After` and `X-RateLimit-*` headers
'''
    ),
    (
        "rate-limiting/sliding-window-log-counter",
        "Implement both sliding window log and sliding window counter rate limiters in Python and compare their memory and accuracy tradeoffs.",
        '''Sliding window log and sliding window counter rate limiters with comparison:

```python
# --- sliding_window.py --- Sliding window rate limiters ---

from __future__ import annotations

import time
import threading
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any


class SlidingWindowLog:
    """
    Sliding window log rate limiter.
    Stores exact timestamp of every request.

    Pros: Perfectly accurate, no boundary issues
    Cons: O(n) memory per key where n = max_requests
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._logs: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str = "__default__") -> bool:
        now = time.monotonic()
        with self._lock:
            if key not in self._logs:
                self._logs[key] = deque()

            log = self._logs[key]

            # Remove timestamps outside the window
            cutoff = now - self._window
            while log and log[0] <= cutoff:
                log.popleft()

            if len(log) < self._max_requests:
                log.append(now)
                return True
            return False

    def remaining(self, key: str = "__default__") -> int:
        now = time.monotonic()
        with self._lock:
            log = self._logs.get(key, deque())
            cutoff = now - self._window
            active = sum(1 for t in log if t > cutoff)
            return max(0, self._max_requests - active)

    def reset_time(self, key: str = "__default__") -> float:
        """Seconds until the oldest request in the window expires."""
        with self._lock:
            log = self._logs.get(key, deque())
            if not log or len(log) < self._max_requests:
                return 0.0
            oldest = log[0]
            return max(0.0, self._window - (time.monotonic() - oldest))


class SlidingWindowCounter:
    """
    Sliding window counter rate limiter.
    Uses weighted combination of current and previous window counts.

    Pros: O(1) memory per key, constant-time operations
    Cons: Approximate (can allow up to ~15% more requests at boundaries)
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._counters: dict[str, _WindowCounterState] = {}
        self._lock = threading.Lock()

    def _get_state(self, key: str) -> _WindowCounterState:
        if key not in self._counters:
            self._counters[key] = _WindowCounterState(
                window_size=self._window,
            )
        return self._counters[key]

    def allow(self, key: str = "__default__") -> bool:
        now = time.monotonic()
        with self._lock:
            state = self._get_state(key)
            state.advance_window(now)

            # Weighted count: previous window's count * overlap fraction + current count
            elapsed_in_current = now - state.current_window_start
            overlap_fraction = max(0.0, 1.0 - elapsed_in_current / self._window)
            weighted_count = (
                state.previous_count * overlap_fraction + state.current_count
            )

            if weighted_count < self._max_requests:
                state.current_count += 1
                state.total_allowed += 1
                return True
            else:
                state.total_denied += 1
                return False

    def get_weighted_count(self, key: str = "__default__") -> float:
        now = time.monotonic()
        with self._lock:
            state = self._get_state(key)
            state.advance_window(now)
            elapsed = now - state.current_window_start
            overlap = max(0.0, 1.0 - elapsed / self._window)
            return state.previous_count * overlap + state.current_count


@dataclass
class _WindowCounterState:
    """Internal state for a single key in the sliding window counter."""
    window_size: float
    current_window_start: float = field(default_factory=time.monotonic)
    current_count: int = 0
    previous_count: int = 0
    total_allowed: int = 0
    total_denied: int = 0

    def advance_window(self, now: float) -> None:
        """Roll windows forward if time has passed."""
        windows_passed = int((now - self.current_window_start) / self.window_size)
        if windows_passed >= 2:
            # Skipped more than one full window
            self.previous_count = 0
            self.current_count = 0
            self.current_window_start = now - (now % self.window_size)
        elif windows_passed == 1:
            self.previous_count = self.current_count
            self.current_count = 0
            self.current_window_start += self.window_size


class MultiTierLimiter:
    """
    Combine multiple rate limiters for tiered limiting.
    Example: 10/second AND 1000/hour AND 10000/day.
    All tiers must allow the request.
    """

    def __init__(self) -> None:
        self._tiers: list[tuple[str, SlidingWindowCounter]] = []

    def add_tier(
        self, name: str, max_requests: int, window_seconds: float
    ) -> MultiTierLimiter:
        self._tiers.append((name, SlidingWindowCounter(max_requests, window_seconds)))
        return self

    def allow(self, key: str = "__default__") -> tuple[bool, str | None]:
        """
        Check all tiers. Returns (allowed, denied_tier_name).
        If allowed, denied_tier_name is None.
        """
        for name, limiter in self._tiers:
            if not limiter.allow(key):
                return False, name
        return True, None

    def get_status(self, key: str = "__default__") -> dict[str, Any]:
        return {
            name: {
                "weighted_count": round(limiter.get_weighted_count(key), 1),
                "max_requests": limiter._max_requests,
                "window_seconds": limiter._window,
            }
            for name, limiter in self._tiers
        }


# ---- Comparison and benchmarking ----

def benchmark_limiters():
    """Compare accuracy and performance of different approaches."""
    import random

    results = {}

    for LimiterClass, name in [
        (SlidingWindowLog, "SlidingWindowLog"),
        (SlidingWindowCounter, "SlidingWindowCounter"),
    ]:
        limiter = LimiterClass(max_requests=100, window_seconds=1.0)
        allowed = 0
        denied = 0
        start = time.monotonic()

        for _ in range(200):
            if limiter.allow("test"):
                allowed += 1
            else:
                denied += 1
            time.sleep(0.001)  # ~1ms between requests

        elapsed = time.monotonic() - start
        results[name] = {
            "allowed": allowed,
            "denied": denied,
            "elapsed": round(elapsed, 3),
            "effective_rate": round(allowed / elapsed, 1),
        }

    return results
```

Comparison of sliding window approaches:

| Property | Window Log | Window Counter |
|----------|-----------|----------------|
| Memory per key | O(max_requests) | O(1) — two counters |
| Accuracy | Exact | ~85-100% accurate |
| Time complexity | O(1) amortized | O(1) |
| Boundary behavior | Smooth | Can overshoot at boundaries |
| Best for | Small limits, need precision | High-volume, many keys |

- **Sliding window log** stores every timestamp and purges expired ones — perfect accuracy but memory-heavy
- **Sliding window counter** uses weighted average of current and previous window — constant memory but approximate
- **Multi-tier limiter** enforces multiple rate windows simultaneously (e.g., 10/s AND 1000/hr)
'''
    ),
    (
        "rate-limiting/distributed-redis-rate-limiter",
        "Implement a distributed rate limiter using Redis with Lua scripts for atomic operations, supporting sliding window and token bucket algorithms.",
        '''Distributed rate limiter using Redis with atomic Lua scripts:

```python
# --- redis_rate_limiter.py --- Distributed rate limiting with Redis ---

from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# ---- Lua scripts for atomic Redis operations ----

# Sliding window counter using sorted sets
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local max_requests = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local member = ARGV[4]

-- Remove expired entries
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current entries
local count = redis.call('ZCARD', key)

if count < max_requests then
    -- Add new entry with timestamp as score
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, math.ceil(window * 1000))
    return {1, max_requests - count - 1, 0}  -- allowed, remaining, retry_after
else
    -- Get oldest entry to calculate retry_after
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 0
    if #oldest > 0 then
        retry_after = window - (now - tonumber(oldest[2]))
    end
    return {0, 0, math.ceil(retry_after * 1000)}  -- denied, remaining, retry_after_ms
end
"""

# Token bucket using hash
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])          -- tokens per second
local burst = tonumber(ARGV[2])         -- max tokens
local now = tonumber(ARGV[3])           -- current time (float seconds)
local cost = tonumber(ARGV[4])          -- tokens to consume

-- Get current state
local tokens = tonumber(redis.call('HGET', key, 'tokens') or burst)
local last_refill = tonumber(redis.call('HGET', key, 'last_refill') or now)

-- Refill tokens
local elapsed = math.max(0, now - last_refill)
tokens = math.min(burst, tokens + elapsed * rate)

local allowed = 0
local retry_after = 0

if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
else
    retry_after = math.ceil((cost - tokens) / rate * 1000)  -- ms
end

-- Update state
redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
redis.call('PEXPIRE', key, math.ceil(burst / rate * 1000) + 1000)  -- TTL = time to fill bucket + 1s

return {allowed, math.floor(tokens), retry_after}
"""

# Fixed window counter
FIXED_WINDOW_LUA = """
local key = KEYS[1]
local max_requests = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('PEXPIRE', key, window_ms)
end

if count <= max_requests then
    return {1, max_requests - count, 0}
else
    local ttl = redis.call('PTTL', key)
    return {0, 0, ttl}
end
"""


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    remaining: int
    retry_after_ms: int
    key: str
    algorithm: str

    @property
    def retry_after_seconds(self) -> float:
        return self.retry_after_ms / 1000.0

    def headers(self) -> dict[str, str]:
        """Standard rate limit response headers."""
        return {
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(time.time() + self.retry_after_seconds)),
            "Retry-After": str(max(1, self.retry_after_ms // 1000)) if not self.allowed else "0",
        }


class DistributedRateLimiter:
    """
    Distributed rate limiter using Redis for shared state.

    Features:
    - Atomic operations via Lua scripts (no race conditions)
    - Multiple algorithm support (sliding window, token bucket, fixed window)
    - Automatic key expiry (no manual cleanup)
    - Pipeline support for checking multiple limits
    - Cluster-compatible
    """

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis = redis.from_url(redis_url, decode_responses=False)
        self._scripts: dict[str, Any] = {}

    async def _ensure_scripts(self) -> None:
        """Register Lua scripts with Redis."""
        if not self._scripts:
            self._scripts["sliding_window"] = self._redis.register_script(SLIDING_WINDOW_LUA)
            self._scripts["token_bucket"] = self._redis.register_script(TOKEN_BUCKET_LUA)
            self._scripts["fixed_window"] = self._redis.register_script(FIXED_WINDOW_LUA)

    async def check_sliding_window(
        self,
        key: str,
        max_requests: int,
        window_seconds: float,
    ) -> RateLimitResult:
        """Check rate limit using sliding window log algorithm."""
        await self._ensure_scripts()
        now = time.time()
        member = f"{now}:{id(key)}"  # Unique member for sorted set

        result = await self._scripts["sliding_window"](
            keys=[f"rl:sw:{key}"],
            args=[window_seconds, max_requests, now, member],
        )

        allowed, remaining, retry_after_ms = int(result[0]), int(result[1]), int(result[2])
        return RateLimitResult(
            allowed=bool(allowed),
            remaining=remaining,
            retry_after_ms=retry_after_ms,
            key=key,
            algorithm="sliding_window",
        )

    async def check_token_bucket(
        self,
        key: str,
        rate: float,
        burst: int,
        cost: int = 1,
    ) -> RateLimitResult:
        """Check rate limit using token bucket algorithm."""
        await self._ensure_scripts()
        now = time.time()

        result = await self._scripts["token_bucket"](
            keys=[f"rl:tb:{key}"],
            args=[rate, burst, now, cost],
        )

        allowed, remaining, retry_after_ms = int(result[0]), int(result[1]), int(result[2])
        return RateLimitResult(
            allowed=bool(allowed),
            remaining=remaining,
            retry_after_ms=retry_after_ms,
            key=key,
            algorithm="token_bucket",
        )

    async def check_fixed_window(
        self,
        key: str,
        max_requests: int,
        window_seconds: float,
    ) -> RateLimitResult:
        """Check rate limit using fixed window counter."""
        await self._ensure_scripts()
        window_ms = int(window_seconds * 1000)
        # Include window boundary in key for automatic rotation
        window_id = int(time.time() / window_seconds)
        full_key = f"rl:fw:{key}:{window_id}"

        result = await self._scripts["fixed_window"](
            keys=[full_key],
            args=[max_requests, window_ms],
        )

        allowed, remaining, retry_after_ms = int(result[0]), int(result[1]), int(result[2])
        return RateLimitResult(
            allowed=bool(allowed),
            remaining=remaining,
            retry_after_ms=retry_after_ms,
            key=key,
            algorithm="fixed_window",
        )

    async def check_multi(
        self,
        checks: list[dict[str, Any]],
    ) -> list[RateLimitResult]:
        """
        Check multiple rate limits in parallel using pipeline.
        All checks must pass for the request to be allowed.
        """
        results = []
        for check in checks:
            algo = check.pop("algorithm")
            if algo == "sliding_window":
                r = await self.check_sliding_window(**check)
            elif algo == "token_bucket":
                r = await self.check_token_bucket(**check)
            elif algo == "fixed_window":
                r = await self.check_fixed_window(**check)
            else:
                raise ValueError(f"Unknown algorithm: {algo}")
            results.append(r)
        return results

    async def close(self) -> None:
        await self._redis.aclose()


# ---- FastAPI integration ----

from fastapi import FastAPI, Request, HTTPException, Depends

app = FastAPI()
limiter = DistributedRateLimiter("redis://localhost:6379")


async def rate_limit_dependency(request: Request) -> RateLimitResult:
    """FastAPI dependency for rate limiting."""
    client_ip = request.headers.get("x-forwarded-for", request.client.host)
    result = await limiter.check_token_bucket(
        key=f"api:{client_ip}",
        rate=10.0,     # 10 requests/second sustained
        burst=50,      # 50 request burst
    )
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail={"error": "Rate limit exceeded", "retry_after": result.retry_after_seconds},
            headers=result.headers(),
        )
    return result


@app.get("/api/resource")
async def get_resource(rl: RateLimitResult = Depends(rate_limit_dependency)):
    return {"data": "ok", "rate_limit_remaining": rl.remaining}
```

Distributed rate limiting considerations:

| Aspect | Lua Script | Pipeline | MULTI/EXEC |
|--------|-----------|----------|------------|
| Atomicity | Full (single eval) | No | Yes, but watch/retry |
| Performance | 1 RTT | 1 RTT, multiple ops | 2+ RTT |
| Cluster support | Yes (single key) | Yes | Limited |
| Complexity | Medium | Low | High |

- **Lua scripts** execute atomically on a single Redis node — no race conditions
- **Key expiry** (PEXPIRE) ensures automatic cleanup without cron jobs
- **Sorted sets** for sliding window: members scored by timestamp, range-removed on check
- **Hash** for token bucket: stores tokens + last_refill, computed server-side
- **Redis Cluster**: works as long as all keys for one rate limit are on the same shard (use hash tags)
'''
    ),
    (
        "rate-limiting/adaptive-rate-limiting",
        "Implement an adaptive rate limiter that dynamically adjusts limits based on server load, error rates, and response times.",
        '''Adaptive rate limiter with dynamic limit adjustment based on system health:

```python
# --- adaptive_limiter.py --- Load-aware adaptive rate limiting ---

from __future__ import annotations

import time
import math
import logging
import threading
from dataclasses import dataclass, field
from collections import deque
from typing import Any, Callable
from enum import Enum, auto

logger = logging.getLogger(__name__)


class SystemHealth(Enum):
    """System health levels for adaptive limiting."""
    HEALTHY = auto()
    DEGRADED = auto()
    CRITICAL = auto()
    OVERLOADED = auto()


@dataclass
class HealthMetrics:
    """Observed system health metrics."""
    error_rate: float = 0.0           # 0.0 - 1.0
    p99_latency_ms: float = 0.0      # 99th percentile latency
    cpu_utilization: float = 0.0      # 0.0 - 1.0
    memory_utilization: float = 0.0   # 0.0 - 1.0
    active_connections: int = 0
    queue_depth: int = 0


@dataclass
class AdaptiveConfig:
    """Configuration for adaptive rate limiting."""
    base_rate: float = 100.0          # Base requests/second
    min_rate: float = 10.0            # Floor rate (never go below)
    max_rate: float = 500.0           # Ceiling rate (never go above)

    # Health thresholds
    error_rate_degraded: float = 0.01   # 1% errors -> degraded
    error_rate_critical: float = 0.05   # 5% errors -> critical
    error_rate_overload: float = 0.10   # 10% errors -> overloaded

    latency_degraded_ms: float = 500    # 500ms P99 -> degraded
    latency_critical_ms: float = 2000   # 2s P99 -> critical
    latency_overload_ms: float = 5000   # 5s P99 -> overloaded

    cpu_degraded: float = 0.70
    cpu_critical: float = 0.85
    cpu_overload: float = 0.95

    # Adjustment parameters
    recovery_rate: float = 0.1          # Rate increase factor per interval
    reduction_rate: float = 0.5         # Rate decrease factor on degradation
    evaluation_interval: float = 5.0    # Seconds between adjustments
    smoothing_factor: float = 0.3       # EWMA smoothing (0 = ignore new, 1 = use only new)


class MetricsCollector:
    """Collects and aggregates request metrics for health assessment."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        self._latencies: deque[tuple[float, float]] = deque()  # (timestamp, latency_ms)
        self._errors: deque[tuple[float, bool]] = deque()      # (timestamp, is_error)
        self._lock = threading.Lock()

    def record_request(self, latency_ms: float, is_error: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            self._latencies.append((now, latency_ms))
            self._errors.append((now, is_error))
            self._cleanup(now)

    def _cleanup(self, now: float) -> None:
        cutoff = now - self._window
        while self._latencies and self._latencies[0][0] < cutoff:
            self._latencies.popleft()
        while self._errors and self._errors[0][0] < cutoff:
            self._errors.popleft()

    def get_error_rate(self) -> float:
        with self._lock:
            if not self._errors:
                return 0.0
            errors = sum(1 for _, is_err in self._errors if is_err)
            return errors / len(self._errors)

    def get_p99_latency(self) -> float:
        with self._lock:
            if not self._latencies:
                return 0.0
            sorted_lats = sorted(lat for _, lat in self._latencies)
            idx = int(len(sorted_lats) * 0.99)
            return sorted_lats[min(idx, len(sorted_lats) - 1)]

    def get_request_count(self) -> int:
        with self._lock:
            return len(self._latencies)


class AdaptiveRateLimiter:
    """
    Rate limiter that dynamically adjusts limits based on:
    - Error rates (5xx responses)
    - Response latency (P99)
    - CPU/memory utilization

    Uses AIMD (Additive Increase, Multiplicative Decrease):
    - Healthy: gradually increase rate toward max
    - Degraded/Critical: immediately cut rate
    - Recovery: slowly restore rate as health improves
    """

    def __init__(
        self,
        config: AdaptiveConfig,
        system_metrics_fn: Callable[[], HealthMetrics] | None = None,
    ) -> None:
        self._config = config
        self._current_rate = config.base_rate
        self._metrics = MetricsCollector()
        self._system_metrics_fn = system_metrics_fn
        self._health = SystemHealth.HEALTHY
        self._smoothed_rate = config.base_rate
        self._last_evaluation = time.monotonic()
        self._lock = threading.Lock()

        # History for observability
        self._rate_history: deque[tuple[float, float, str]] = deque(maxlen=1000)

        # Token bucket for actual enforcement
        self._tokens = float(config.base_rate)
        self._last_refill = time.monotonic()

    def _assess_health(self) -> SystemHealth:
        """Determine system health from collected metrics."""
        c = self._config
        error_rate = self._metrics.get_error_rate()
        p99 = self._metrics.get_p99_latency()

        # Get system metrics if available
        sys_metrics = self._system_metrics_fn() if self._system_metrics_fn else HealthMetrics()

        # Check overload conditions
        if (
            error_rate >= c.error_rate_overload
            or p99 >= c.latency_overload_ms
            or sys_metrics.cpu_utilization >= c.cpu_overload
        ):
            return SystemHealth.OVERLOADED

        if (
            error_rate >= c.error_rate_critical
            or p99 >= c.latency_critical_ms
            or sys_metrics.cpu_utilization >= c.cpu_critical
        ):
            return SystemHealth.CRITICAL

        if (
            error_rate >= c.error_rate_degraded
            or p99 >= c.latency_degraded_ms
            or sys_metrics.cpu_utilization >= c.cpu_degraded
        ):
            return SystemHealth.DEGRADED

        return SystemHealth.HEALTHY

    def _adjust_rate(self) -> None:
        """AIMD-style rate adjustment based on system health."""
        c = self._config
        old_health = self._health
        self._health = self._assess_health()

        if self._health == SystemHealth.HEALTHY:
            # Additive increase: slowly recover toward max
            target = min(self._current_rate * (1 + c.recovery_rate), c.max_rate)
        elif self._health == SystemHealth.DEGRADED:
            # Mild reduction
            target = max(self._current_rate * 0.8, c.min_rate)
        elif self._health == SystemHealth.CRITICAL:
            # Multiplicative decrease
            target = max(self._current_rate * c.reduction_rate, c.min_rate)
        else:  # OVERLOADED
            # Emergency: drop to minimum
            target = c.min_rate

        # EWMA smoothing to avoid oscillation
        self._smoothed_rate = (
            c.smoothing_factor * target
            + (1 - c.smoothing_factor) * self._smoothed_rate
        )
        self._current_rate = max(c.min_rate, min(c.max_rate, self._smoothed_rate))

        # Log adjustment
        if old_health != self._health:
            logger.warning(
                "Health changed: %s -> %s, rate adjusted: %.1f req/s",
                old_health.name, self._health.name, self._current_rate,
            )

        self._rate_history.append((time.time(), self._current_rate, self._health.name))

    def _refill_tokens(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._tokens + elapsed * self._current_rate,
            self._current_rate * 2,  # Burst = 2x current rate
        )
        self._last_refill = now

    def allow(self, cost: int = 1) -> bool:
        """Check if request is allowed under current adaptive rate."""
        with self._lock:
            now = time.monotonic()

            # Periodically re-evaluate rate
            if now - self._last_evaluation >= self._config.evaluation_interval:
                self._adjust_rate()
                self._last_evaluation = now

            self._refill_tokens()

            if self._tokens >= cost:
                self._tokens -= cost
                return True
            return False

    def record_response(self, latency_ms: float, is_error: bool = False) -> None:
        """Record a completed request for health assessment."""
        self._metrics.record_request(latency_ms, is_error)

    @property
    def current_rate(self) -> float:
        return self._current_rate

    @property
    def health(self) -> SystemHealth:
        return self._health

    def get_status(self) -> dict[str, Any]:
        return {
            "current_rate": round(self._current_rate, 1),
            "health": self._health.name,
            "error_rate": round(self._metrics.get_error_rate(), 4),
            "p99_latency_ms": round(self._metrics.get_p99_latency(), 1),
            "request_count_1m": self._metrics.get_request_count(),
            "config": {
                "base_rate": self._config.base_rate,
                "min_rate": self._config.min_rate,
                "max_rate": self._config.max_rate,
            },
        }


# ---- FastAPI integration with response tracking ----

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class AdaptiveRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: AdaptiveRateLimiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        if not self.limiter.allow():
            return Response(
                content='{"error": "Service is rate limited due to high load"}',
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "Retry-After": "5",
                    "X-RateLimit-Health": self.limiter.health.name,
                },
            )

        start = time.monotonic()
        try:
            response = await call_next(request)
            latency_ms = (time.monotonic() - start) * 1000
            is_error = response.status_code >= 500
            self.limiter.record_response(latency_ms, is_error)
            response.headers["X-RateLimit-Rate"] = str(int(self.limiter.current_rate))
            response.headers["X-RateLimit-Health"] = self.limiter.health.name
            return response
        except Exception:
            latency_ms = (time.monotonic() - start) * 1000
            self.limiter.record_response(latency_ms, is_error=True)
            raise
```

Adaptive rate limiting strategy:

| Health State | Error Rate | P99 Latency | Action | Rate Multiplier |
|-------------|-----------|-------------|--------|----------------|
| HEALTHY | < 1% | < 500ms | Additive increase | x1.1 per interval |
| DEGRADED | 1-5% | 500ms-2s | Mild reduction | x0.8 |
| CRITICAL | 5-10% | 2-5s | Multiplicative decrease | x0.5 |
| OVERLOADED | > 10% | > 5s | Emergency floor | -> min_rate |

Key patterns:

- **AIMD** (Additive Increase, Multiplicative Decrease) — same algorithm as TCP congestion control
- **EWMA smoothing** prevents oscillation between health states
- **Response tracking** feeds back into health assessment — closed-loop control
- **Floor rate** ensures service never drops to zero (always allows some traffic)
- **Health headers** (`X-RateLimit-Health`) inform clients of system status
'''
    ),
    (
        "rate-limiting/leaky-bucket-queue",
        "Implement a leaky bucket rate limiter that smooths bursty traffic into a constant output rate, with queue overflow handling and async processing.",
        '''Leaky bucket with queue-based traffic smoothing and async drain:

```python
# --- leaky_bucket.py --- Queue-based leaky bucket for traffic smoothing ---

from __future__ import annotations

import asyncio
import logging
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar, Generic

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class LeakyBucketConfig:
    """Configuration for leaky bucket."""
    rate: float            # Requests drained per second (constant output rate)
    capacity: int          # Maximum queue depth (bucket size)
    overflow_strategy: str = "reject"  # "reject" | "drop_oldest" | "drop_newest"


@dataclass
class QueuedRequest(Generic[T]):
    """A request waiting in the leaky bucket queue."""
    payload: T
    enqueued_at: float = field(default_factory=time.monotonic)
    deadline: float | None = None  # Max time to wait in queue

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.enqueued_at

    @property
    def is_expired(self) -> bool:
        if self.deadline is None:
            return False
        return time.monotonic() > self.deadline


class LeakyBucket(Generic[T]):
    """
    Leaky bucket rate limiter with queue semantics.

    Unlike token bucket (which allows bursts), leaky bucket
    enforces a perfectly constant output rate by queuing requests
    and draining them at a fixed interval.

    Features:
    - Constant output rate regardless of input burst pattern
    - Configurable queue overflow strategies
    - Deadline-based request expiry
    - Metrics and monitoring
    """

    def __init__(self, config: LeakyBucketConfig) -> None:
        self._config = config
        self._queue: deque[QueuedRequest[T]] = deque(maxlen=None)  # We manage capacity manually
        self._lock = threading.Lock()
        self._drain_interval = 1.0 / config.rate  # Seconds between drains
        self._stats = {
            "enqueued": 0,
            "drained": 0,
            "rejected": 0,
            "expired": 0,
            "dropped": 0,
        }

    def enqueue(
        self,
        payload: T,
        deadline_seconds: float | None = None,
    ) -> bool:
        """
        Add a request to the bucket queue.
        Returns True if accepted, False if rejected (queue full).
        """
        with self._lock:
            # Check capacity
            if len(self._queue) >= self._config.capacity:
                if self._config.overflow_strategy == "reject":
                    self._stats["rejected"] += 1
                    return False
                elif self._config.overflow_strategy == "drop_oldest":
                    dropped = self._queue.popleft()
                    self._stats["dropped"] += 1
                    logger.debug("Dropped oldest request (age=%.2fs)", dropped.age_seconds)
                elif self._config.overflow_strategy == "drop_newest":
                    # Don't enqueue the new request
                    self._stats["dropped"] += 1
                    return False

            deadline = None
            if deadline_seconds is not None:
                deadline = time.monotonic() + deadline_seconds

            self._queue.append(QueuedRequest(payload=payload, deadline=deadline))
            self._stats["enqueued"] += 1
            return True

    def drain_one(self) -> QueuedRequest[T] | None:
        """
        Remove and return the next request from the queue.
        Skips expired requests.
        """
        with self._lock:
            while self._queue:
                request = self._queue.popleft()
                if request.is_expired:
                    self._stats["expired"] += 1
                    logger.debug("Skipped expired request (age=%.2fs)", request.age_seconds)
                    continue
                self._stats["drained"] += 1
                return request
            return None

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    @property
    def is_full(self) -> bool:
        return len(self._queue) >= self._config.capacity

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "queue_depth": self.queue_depth,
            "capacity": self._config.capacity,
            "drain_rate": self._config.rate,
            "utilization": round(self.queue_depth / max(self._config.capacity, 1), 3),
        }


class AsyncLeakyBucketProcessor(Generic[T]):
    """
    Async processor that drains the leaky bucket at a constant rate
    and processes each request through a handler function.
    """

    def __init__(
        self,
        bucket: LeakyBucket[T],
        handler: Callable[[T], Awaitable[Any]],
        *,
        error_handler: Callable[[T, Exception], Awaitable[None]] | None = None,
        max_concurrent: int = 1,
    ) -> None:
        self._bucket = bucket
        self._handler = handler
        self._error_handler = error_handler
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running = False
        self._task: asyncio.Task | None = None
        self._processed = 0
        self._errors = 0

    async def start(self) -> None:
        """Start the drain loop."""
        self._running = True
        self._task = asyncio.create_task(self._drain_loop())
        logger.info(
            "Leaky bucket processor started (rate=%.1f/s, concurrency=%d)",
            self._bucket._config.rate, self._max_concurrent,
        )

    async def stop(self, drain_remaining: bool = True) -> None:
        """Stop the processor, optionally draining remaining items."""
        self._running = False
        if drain_remaining:
            while self._bucket.queue_depth > 0:
                await self._process_next()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(
            "Processor stopped. Processed=%d, Errors=%d",
            self._processed, self._errors,
        )

    async def _drain_loop(self) -> None:
        """Main drain loop — processes at constant rate."""
        interval = 1.0 / self._bucket._config.rate
        while self._running:
            start = time.monotonic()
            await self._process_next()
            # Sleep for remaining interval to maintain constant rate
            elapsed = time.monotonic() - start
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def _process_next(self) -> None:
        """Process the next request from the queue."""
        request = self._bucket.drain_one()
        if request is None:
            await asyncio.sleep(0.01)  # Brief sleep when queue is empty
            return

        async with self._semaphore:
            try:
                await self._handler(request.payload)
                self._processed += 1
            except Exception as e:
                self._errors += 1
                logger.error("Handler error: %s", e)
                if self._error_handler:
                    await self._error_handler(request.payload, e)


# ---- Comparison: Token Bucket vs Leaky Bucket ----

class TokenVsLeakyDemo:
    """Demonstrate the difference in output patterns."""

    @staticmethod
    async def demo():
        # Token bucket: allows bursts
        from token_bucket import TokenBucketLimiter, BucketConfig

        tb = TokenBucketLimiter(BucketConfig(rate=5.0, burst=20))

        # Leaky bucket: constant output
        lb = LeakyBucket[str](LeakyBucketConfig(rate=5.0, capacity=20))
        processor = AsyncLeakyBucketProcessor(
            lb,
            handler=lambda x: asyncio.sleep(0),  # no-op handler
        )
        await processor.start()

        # Simulate burst of 20 requests
        burst_results_tb = []
        burst_results_lb = []

        for i in range(20):
            # Token bucket: all 20 pass immediately (burst capacity)
            burst_results_tb.append(tb.allow("test"))
            # Leaky bucket: all 20 queued, drained at 5/second
            burst_results_lb.append(lb.enqueue(f"request-{i}"))

        print(f"Token bucket: {sum(burst_results_tb)}/20 passed immediately")
        print(f"Leaky bucket: {sum(burst_results_lb)}/20 queued, draining at 5/s")
        print(f"Leaky bucket drain time: {20 / 5.0}s for all 20")

        await processor.stop()
```

Token bucket vs leaky bucket comparison:

| Aspect | Token Bucket | Leaky Bucket |
|--------|-------------|-------------|
| Burst handling | Allows bursts up to bucket capacity | Smooths all bursts to constant rate |
| Output pattern | Bursty (follows input, up to limit) | Constant (always at drain rate) |
| Queue | No queue (immediate accept/reject) | Queue with FIFO processing |
| Latency | Zero (instant decision) | Queue wait time |
| Use case | API rate limiting | Traffic shaping, request smoothing |
| Downstream impact | Downstream sees bursts | Downstream sees constant load |
| Memory | O(1) per key | O(capacity) per queue |

When to use each:

- **Token bucket**: API rate limiting where bursts are acceptable (most common)
- **Leaky bucket**: When downstream systems need constant, predictable load (e.g., database writes, external API calls)
- **Sliding window**: When you need precise counting within a time window
- **Adaptive**: When system load varies and fixed limits would be too conservative or too aggressive
'''
    ),
]
