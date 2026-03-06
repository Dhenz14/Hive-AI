PAIRS = [
    ("projects/rate-limiter", r'''<think>
Token bucket is the most common rate limiting algorithm. It allows bursts
up to the bucket size while maintaining a steady average rate.
I need to implement it thread-safe with atomic operations.
</think>
Build a rate limiter with token bucket algorithm, thread safety, and configurable refill rates.''', r'''import time
import threading
from typing import Optional, Tuple


class TokenBucket:
    """Thread-safe token bucket rate limiter.

    Allows bursts up to the bucket capacity while maintaining
    a steady average request rate over time.
    """

    def __init__(self, rate: float, capacity: int):
        self._rate = rate  # tokens per second
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens. Returns True if allowed."""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """Block until tokens are available or timeout expires."""
        deadline = time.monotonic() + timeout if timeout else None

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                # Calculate wait time for enough tokens
                deficit = tokens - self._tokens
                wait_time = deficit / self._rate

            if deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                wait_time = min(wait_time, remaining)

            time.sleep(wait_time)

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def reset(self) -> None:
        with self._lock:
            self._tokens = float(self._capacity)
            self._last_refill = time.monotonic()


class SlidingWindowCounter:
    """Sliding window rate limiter using fixed window counters.

    More memory-efficient than a true sliding window log,
    while providing better accuracy than a fixed window.
    """

    def __init__(self, limit: int, window_seconds: float):
        self._limit = limit
        self._window = window_seconds
        self._current_count = 0
        self._previous_count = 0
        self._current_window_start = 0.0
        self._lock = threading.Lock()

    def _get_window_start(self, now: float) -> float:
        return now - (now % self._window)

    def acquire(self) -> bool:
        """Try to acquire a slot. Returns True if allowed."""
        now = time.monotonic()
        with self._lock:
            window_start = self._get_window_start(now)

            if window_start != self._current_window_start:
                elapsed_windows = (window_start - self._current_window_start) / self._window
                if elapsed_windows >= 2:
                    self._previous_count = 0
                    self._current_count = 0
                else:
                    self._previous_count = self._current_count
                    self._current_count = 0
                self._current_window_start = window_start

            # Calculate weighted count
            window_elapsed = now - window_start
            weight = 1.0 - (window_elapsed / self._window)
            estimated = self._previous_count * weight + self._current_count

            if estimated >= self._limit:
                return False

            self._current_count += 1
            return True

    def get_remaining(self) -> int:
        """Get approximate remaining requests in the current window."""
        now = time.monotonic()
        with self._lock:
            window_start = self._get_window_start(now)
            window_elapsed = now - window_start
            weight = 1.0 - (window_elapsed / self._window)
            estimated = self._previous_count * weight + self._current_count
            return max(0, int(self._limit - estimated))

    def get_reset_time(self) -> float:
        """Get seconds until the current window resets."""
        now = time.monotonic()
        window_start = self._get_window_start(now)
        return self._window - (now - window_start)


class RateLimiter:
    """High-level rate limiter with multiple algorithm support."""

    def __init__(
        self,
        algorithm: str = "token_bucket",
        rate: float = 10.0,
        capacity: int = 20,
        window: float = 60.0,
    ):
        if algorithm == "token_bucket":
            self._impl = TokenBucket(rate=rate, capacity=capacity)
        elif algorithm == "sliding_window":
            self._impl = SlidingWindowCounter(limit=capacity, window_seconds=window)
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        self._algorithm = algorithm

    def allow(self, tokens: int = 1) -> bool:
        return self._impl.acquire(tokens) if hasattr(self._impl, 'acquire') else self._impl.acquire()

    def check(self) -> dict:
        """Get current rate limit status."""
        if isinstance(self._impl, TokenBucket):
            return {
                "allowed": True,
                "remaining": int(self._impl.available_tokens),
                "algorithm": self._algorithm,
            }
        elif isinstance(self._impl, SlidingWindowCounter):
            return {
                "allowed": True,
                "remaining": self._impl.get_remaining(),
                "reset_in": f"{self._impl.get_reset_time():.1f}s",
                "algorithm": self._algorithm,
            }
        return {}
'''),
    ("projects/rate-limiter", r'''Implement per-user rate limiting with configurable limits per user tier and IP-based fallback.''', r'''import time
import threading
from typing import Dict, Optional, Tuple
from collections import defaultdict


class UserTier:
    """Rate limit configuration per user tier."""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"

    LIMITS = {
        "free": {"rate": 1.0, "capacity": 10, "daily_limit": 100},
        "basic": {"rate": 5.0, "capacity": 20, "daily_limit": 1000},
        "pro": {"rate": 20.0, "capacity": 50, "daily_limit": 10000},
        "enterprise": {"rate": 100.0, "capacity": 200, "daily_limit": 100000},
    }


class PerUserRateLimiter:
    """Rate limiter with per-user buckets and tier-based limits."""

    def __init__(self, default_tier: str = UserTier.FREE):
        self._default_tier = default_tier
        self._user_tiers: Dict[str, str] = {}
        self._user_buckets: Dict[str, dict] = {}
        self._ip_buckets: Dict[str, dict] = {}
        self._daily_counts: Dict[str, int] = {}
        self._daily_reset: float = 0.0
        self._lock = threading.Lock()

    def set_user_tier(self, user_id: str, tier: str) -> None:
        """Set the rate limit tier for a user."""
        self._user_tiers[user_id] = tier

    def _get_bucket(self, key: str, tier: str) -> dict:
        """Get or create a token bucket for a key."""
        if key not in self._user_buckets:
            limits = UserTier.LIMITS.get(tier, UserTier.LIMITS[UserTier.FREE])
            self._user_buckets[key] = {
                "tokens": float(limits["capacity"]),
                "capacity": limits["capacity"],
                "rate": limits["rate"],
                "last_refill": time.monotonic(),
            }
        return self._user_buckets[key]

    def _refill_bucket(self, bucket: dict) -> None:
        now = time.monotonic()
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(
            bucket["capacity"],
            bucket["tokens"] + elapsed * bucket["rate"]
        )
        bucket["last_refill"] = now

    def _check_daily_reset(self) -> None:
        """Reset daily counters if a new day has started."""
        now = time.time()
        day_start = now - (now % 86400)
        if day_start > self._daily_reset:
            self._daily_counts.clear()
            self._daily_reset = day_start

    def check_rate_limit(
        self,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[bool, dict]:
        """Check if a request is allowed.

        Returns (allowed, headers_dict) where headers_dict contains
        rate limit headers for the response.
        """
        with self._lock:
            self._check_daily_reset()

            key = user_id or ip_address or "anonymous"
            tier = self._user_tiers.get(key, self._default_tier)
            limits = UserTier.LIMITS.get(tier, UserTier.LIMITS[UserTier.FREE])

            # Check daily limit
            daily_count = self._daily_counts.get(key, 0)
            if daily_count >= limits["daily_limit"]:
                return False, {
                    "X-RateLimit-Limit": str(limits["daily_limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(self._daily_reset + 86400)),
                    "Retry-After": str(int(self._daily_reset + 86400 - time.time())),
                }

            # Check token bucket
            bucket = self._get_bucket(key, tier)
            self._refill_bucket(bucket)

            if bucket["tokens"] < 1:
                wait_time = (1 - bucket["tokens"]) / bucket["rate"]
                return False, {
                    "X-RateLimit-Limit": str(limits["capacity"]),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(int(wait_time) + 1),
                }

            bucket["tokens"] -= 1
            self._daily_counts[key] = daily_count + 1

            return True, {
                "X-RateLimit-Limit": str(limits["capacity"]),
                "X-RateLimit-Remaining": str(int(bucket["tokens"])),
                "X-RateLimit-Daily-Remaining": str(limits["daily_limit"] - daily_count - 1),
            }

    def get_user_status(self, user_id: str) -> dict:
        """Get detailed rate limit status for a user."""
        tier = self._user_tiers.get(user_id, self._default_tier)
        limits = UserTier.LIMITS.get(tier, UserTier.LIMITS[UserTier.FREE])
        daily_count = self._daily_counts.get(user_id, 0)

        bucket = self._user_buckets.get(user_id)
        tokens = 0
        if bucket:
            self._refill_bucket(bucket)
            tokens = int(bucket["tokens"])

        return {
            "user_id": user_id,
            "tier": tier,
            "burst_remaining": tokens,
            "burst_limit": limits["capacity"],
            "daily_used": daily_count,
            "daily_limit": limits["daily_limit"],
            "rate_per_second": limits["rate"],
        }

    def cleanup_idle(self, max_idle_seconds: float = 3600) -> int:
        """Remove buckets for users who have been idle."""
        now = time.monotonic()
        removed = 0
        with self._lock:
            idle_keys = [
                k for k, b in self._user_buckets.items()
                if (now - b["last_refill"]) > max_idle_seconds
            ]
            for key in idle_keys:
                del self._user_buckets[key]
                removed += 1
        return removed
'''),
    ("projects/rate-limiter", r'''<think>
Distributed rate limiting across multiple server instances requires
a shared state store like Redis. I need to implement atomic operations
using Redis Lua scripts to avoid race conditions.
</think>
Implement distributed rate limiting using Redis with atomic Lua scripts for multi-instance deployments.''', r'''import time
from typing import Optional, Tuple


# Redis Lua scripts for atomic rate limiting operations
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local bucket = redis.call('hmget', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

-- Refill tokens
local elapsed = now - last_refill
tokens = math.min(capacity, tokens + elapsed * rate)

-- Check if request is allowed
if tokens >= requested then
    tokens = tokens - requested
    redis.call('hmset', key, 'tokens', tokens, 'last_refill', now)
    redis.call('expire', key, math.ceil(capacity / rate) * 2)
    return {1, math.floor(tokens)}
else
    redis.call('hmset', key, 'tokens', tokens, 'last_refill', now)
    redis.call('expire', key, math.ceil(capacity / rate) * 2)
    local wait_time = (requested - tokens) / rate
    return {0, math.ceil(wait_time * 1000)}
end
"""

SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Remove expired entries
redis.call('zremrangebyscore', key, '-inf', now - window)

-- Count current entries
local count = redis.call('zcard', key)

if count < limit then
    redis.call('zadd', key, now, now .. ':' .. math.random(1000000))
    redis.call('expire', key, math.ceil(window) + 1)
    return {1, limit - count - 1}
else
    -- Get the oldest entry to calculate reset time
    local oldest = redis.call('zrange', key, 0, 0, 'WITHSCORES')
    local reset_at = 0
    if oldest[2] then
        reset_at = tonumber(oldest[2]) + window - now
    end
    return {0, math.ceil(reset_at * 1000)}
end
"""


class DistributedRateLimiter:
    """Distributed rate limiter using Redis for shared state."""

    def __init__(
        self,
        redis_client,
        key_prefix: str = "ratelimit",
        algorithm: str = "token_bucket",
    ):
        self._redis = redis_client
        self._prefix = key_prefix
        self._algorithm = algorithm
        self._scripts = {}
        self._register_scripts()

    def _register_scripts(self) -> None:
        """Register Lua scripts with Redis."""
        self._scripts["token_bucket"] = self._redis.register_script(TOKEN_BUCKET_LUA)
        self._scripts["sliding_window"] = self._redis.register_script(SLIDING_WINDOW_LUA)

    def _make_key(self, identifier: str) -> str:
        return f"{self._prefix}:{identifier}"

    def check(
        self,
        identifier: str,
        rate: float = 10.0,
        capacity: int = 20,
        window: float = 60.0,
        cost: int = 1,
    ) -> Tuple[bool, dict]:
        """Check if a request is allowed.

        Args:
            identifier: User ID, IP, or API key
            rate: Tokens per second (token bucket)
            capacity: Max tokens / max requests per window
            window: Window size in seconds (sliding window)
            cost: Number of tokens to consume

        Returns:
            (allowed, info_dict)
        """
        key = self._make_key(identifier)
        now = time.time()

        if self._algorithm == "token_bucket":
            result = self._scripts["token_bucket"](
                keys=[key],
                args=[capacity, rate, now, cost],
            )
            allowed = bool(result[0])
            if allowed:
                remaining = result[1]
                return True, {
                    "remaining": remaining,
                    "limit": capacity,
                }
            else:
                retry_ms = result[1]
                return False, {
                    "remaining": 0,
                    "limit": capacity,
                    "retry_after_ms": retry_ms,
                }

        elif self._algorithm == "sliding_window":
            result = self._scripts["sliding_window"](
                keys=[key],
                args=[capacity, window, now],
            )
            allowed = bool(result[0])
            if allowed:
                return True, {
                    "remaining": result[1],
                    "limit": capacity,
                    "window": window,
                }
            else:
                return False, {
                    "remaining": 0,
                    "limit": capacity,
                    "retry_after_ms": result[1],
                }

        raise ValueError(f"Unknown algorithm: {self._algorithm}")

    def reset(self, identifier: str) -> None:
        """Reset rate limit state for an identifier."""
        key = self._make_key(identifier)
        self._redis.delete(key)

    def get_status(self, identifier: str) -> dict:
        """Get current rate limit status without consuming tokens."""
        key = self._make_key(identifier)
        if self._algorithm == "token_bucket":
            data = self._redis.hgetall(key)
            if not data:
                return {"status": "no_data"}
            return {
                "tokens": float(data.get(b"tokens", 0)),
                "last_refill": float(data.get(b"last_refill", 0)),
            }
        elif self._algorithm == "sliding_window":
            now = time.time()
            count = self._redis.zcount(key, now - 60, now)
            return {"current_count": count}
        return {}


class RateLimitMiddleware:
    """ASGI middleware for rate limiting HTTP requests."""

    def __init__(self, app, limiter: DistributedRateLimiter, rate: float = 10.0, capacity: int = 20):
        self._app = app
        self._limiter = limiter
        self._rate = rate
        self._capacity = capacity

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # Extract identifier (IP or auth token)
        client = scope.get("client", ("0.0.0.0", 0))
        identifier = client[0]

        for header_name, header_value in scope.get("headers", []):
            if header_name == b"authorization":
                identifier = header_value.decode()[:64]
                break

        allowed, info = self._limiter.check(
            identifier, rate=self._rate, capacity=self._capacity
        )

        if not allowed:
            # Return 429 Too Many Requests
            retry_after = str(info.get("retry_after_ms", 1000) // 1000 + 1)
            response_headers = [
                (b"content-type", b"application/json"),
                (b"retry-after", retry_after.encode()),
                (b"x-ratelimit-limit", str(self._capacity).encode()),
                (b"x-ratelimit-remaining", b"0"),
            ]
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": response_headers,
            })
            import json
            body = json.dumps({"error": "Rate limit exceeded", "retry_after": int(retry_after)})
            await send({"type": "http.response.body", "body": body.encode()})
            return

        # Add rate limit headers to response
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-ratelimit-limit", str(self._capacity).encode()))
                headers.append((b"x-ratelimit-remaining", str(info.get("remaining", 0)).encode()))
                message["headers"] = headers
            await send(message)

        await self._app(scope, receive, send_with_headers)
'''),
    ("projects/rate-limiter", r'''Implement burst handling with leaky bucket and adaptive rate limiting that adjusts based on server load.''', r'''import time
import threading
import math
from typing import Callable, Dict, Optional


class LeakyBucket:
    """Leaky bucket rate limiter that smooths out burst traffic.

    Unlike token bucket, leaky bucket processes requests at a fixed rate,
    queuing excess requests up to the bucket capacity.
    """

    def __init__(self, rate: float, capacity: int):
        self._rate = rate  # requests per second (leak rate)
        self._capacity = capacity
        self._water = 0.0  # current water level
        self._last_leak = time.monotonic()
        self._lock = threading.Lock()

    def _leak(self) -> None:
        """Drain water based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_leak
        leaked = elapsed * self._rate
        self._water = max(0.0, self._water - leaked)
        self._last_leak = now

    def acquire(self) -> bool:
        """Try to add a request. Returns True if the bucket has capacity."""
        with self._lock:
            self._leak()
            if self._water < self._capacity:
                self._water += 1
                return True
            return False

    def get_wait_time(self) -> float:
        """Get time to wait before next request would be accepted."""
        with self._lock:
            self._leak()
            if self._water < self._capacity:
                return 0.0
            overflow = self._water - self._capacity + 1
            return overflow / self._rate

    @property
    def current_level(self) -> float:
        with self._lock:
            self._leak()
            return self._water

    @property
    def utilization(self) -> float:
        return min(1.0, self.current_level / self._capacity)


class AdaptiveRateLimiter:
    """Rate limiter that adjusts its limits based on server load.

    Increases limits when the server is healthy, decreases when
    under pressure, using an AIMD (Additive Increase, Multiplicative
    Decrease) approach similar to TCP congestion control.
    """

    def __init__(
        self,
        initial_rate: float = 100.0,
        min_rate: float = 10.0,
        max_rate: float = 1000.0,
        increase_step: float = 5.0,
        decrease_factor: float = 0.5,
        check_interval: float = 10.0,
    ):
        self._current_rate = initial_rate
        self._min_rate = min_rate
        self._max_rate = max_rate
        self._increase_step = increase_step
        self._decrease_factor = decrease_factor
        self._check_interval = check_interval
        self._bucket = LeakyBucket(rate=initial_rate, capacity=int(initial_rate * 2))
        self._lock = threading.Lock()
        self._health_checker: Optional[Callable] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._adjustment_history: list = []

    def set_health_checker(self, checker: Callable[[], float]) -> None:
        """Set a function that returns server health (0.0 to 1.0)."""
        self._health_checker = checker

    def start(self) -> None:
        """Start adaptive adjustment loop."""
        self._running = True
        self._thread = threading.Thread(target=self._adjust_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def acquire(self) -> bool:
        """Try to acquire a request slot."""
        return self._bucket.acquire()

    def _adjust_loop(self) -> None:
        """Periodically adjust rate based on health."""
        while self._running:
            time.sleep(self._check_interval)
            if self._health_checker:
                health = self._health_checker()
                self._adjust_rate(health)

    def _adjust_rate(self, health: float) -> None:
        """Adjust rate based on health score.

        health > 0.8: increase rate (additive)
        health < 0.5: decrease rate (multiplicative)
        """
        with self._lock:
            old_rate = self._current_rate

            if health > 0.8:
                # Server is healthy - increase rate
                self._current_rate = min(
                    self._max_rate,
                    self._current_rate + self._increase_step,
                )
            elif health < 0.5:
                # Server is under pressure - decrease rate
                self._current_rate = max(
                    self._min_rate,
                    self._current_rate * self._decrease_factor,
                )
            elif health < 0.3:
                # Server is critically loaded - aggressive decrease
                self._current_rate = max(
                    self._min_rate,
                    self._current_rate * 0.25,
                )

            if self._current_rate != old_rate:
                self._bucket = LeakyBucket(
                    rate=self._current_rate,
                    capacity=int(self._current_rate * 2),
                )
                self._adjustment_history.append({
                    "timestamp": time.time(),
                    "health": health,
                    "old_rate": old_rate,
                    "new_rate": self._current_rate,
                })
                # Keep only last 100 adjustments
                if len(self._adjustment_history) > 100:
                    self._adjustment_history = self._adjustment_history[-100:]

    @property
    def current_rate(self) -> float:
        return self._current_rate

    def get_stats(self) -> dict:
        return {
            "current_rate": self._current_rate,
            "min_rate": self._min_rate,
            "max_rate": self._max_rate,
            "bucket_utilization": f"{self._bucket.utilization * 100:.1f}%",
            "recent_adjustments": self._adjustment_history[-5:],
        }


class CompositeLimiter:
    """Combines multiple rate limiters (all must allow for request to proceed)."""

    def __init__(self):
        self._limiters: Dict[str, object] = {}

    def add(self, name: str, limiter) -> "CompositeLimiter":
        self._limiters[name] = limiter
        return self

    def acquire(self) -> bool:
        """Check all limiters. All must allow for the request to proceed."""
        results = {}
        for name, limiter in self._limiters.items():
            results[name] = limiter.acquire()

        return all(results.values())

    def get_status(self) -> dict:
        status = {}
        for name, limiter in self._limiters.items():
            if hasattr(limiter, "get_stats"):
                status[name] = limiter.get_stats()
            elif hasattr(limiter, "current_level"):
                status[name] = {"level": limiter.current_level}
        return status
'''),
    ("projects/rate-limiter", r'''Implement a rate limit response handler with proper HTTP headers, retry-after calculation, and client-side backoff.''', r'''import time
import random
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    remaining: int
    limit: int
    reset_at: float
    retry_after: Optional[float] = None
    tier: str = ""

    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP response headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at)),
        }
        if self.retry_after is not None:
            headers["Retry-After"] = str(int(self.retry_after) + 1)
        return headers

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "limit": self.limit,
            "reset_at": self.reset_at,
            "retry_after": self.retry_after,
        }


class RateLimitResponseHandler:
    """Handles rate limit responses with proper headers and error bodies."""

    def __init__(self):
        self._on_limited_callbacks: list = []
        self._exempt_paths: set = set()

    def add_exempt_path(self, path: str) -> None:
        """Add a path that should bypass rate limiting."""
        self._exempt_paths.add(path)

    def is_exempt(self, path: str) -> bool:
        return path in self._exempt_paths

    def on_limited(self, callback: Callable) -> None:
        """Register a callback when a request is rate limited."""
        self._on_limited_callbacks.append(callback)

    def build_error_response(self, result: RateLimitResult) -> dict:
        """Build a JSON error response for rate limited requests."""
        response = {
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after": result.retry_after,
                "limit": result.limit,
                "remaining": 0,
            }
        }

        for callback in self._on_limited_callbacks:
            try:
                callback(result)
            except Exception:
                pass

        return response


class ClientBackoff:
    """Client-side backoff strategy for handling rate limit responses."""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        max_retries: int = 5,
        jitter: bool = True,
    ):
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._max_retries = max_retries
        self._jitter = jitter
        self._attempt = 0
        self._total_wait = 0.0

    def get_delay(self, retry_after: Optional[float] = None) -> float:
        """Calculate the delay before the next retry."""
        if retry_after is not None and retry_after > 0:
            delay = retry_after
        else:
            delay = self._base_delay * (2 ** self._attempt)
            delay = min(delay, self._max_delay)

        if self._jitter:
            delay = delay * (0.5 + random.random())

        return delay

    def should_retry(self) -> bool:
        """Check if we should retry."""
        return self._attempt < self._max_retries

    def wait_and_retry(self, retry_after: Optional[float] = None) -> bool:
        """Wait the appropriate time and return whether to retry."""
        if not self.should_retry():
            return False

        delay = self.get_delay(retry_after)
        self._attempt += 1
        self._total_wait += delay

        logger.info(f"Rate limited. Waiting {delay:.1f}s (attempt {self._attempt}/{self._max_retries})")
        time.sleep(delay)
        return True

    def reset(self) -> None:
        """Reset backoff state after a successful request."""
        self._attempt = 0
        self._total_wait = 0.0

    @property
    def stats(self) -> dict:
        return {
            "attempts": self._attempt,
            "total_wait_seconds": f"{self._total_wait:.1f}",
            "max_retries": self._max_retries,
        }


def rate_limited_request(
    request_func: Callable,
    max_retries: int = 5,
    base_delay: float = 1.0,
) -> Any:
    """Execute a request with automatic retry on rate limiting.

    The request_func should return (status_code, headers, body).
    If status is 429, automatically backs off and retries.
    """
    backoff = ClientBackoff(base_delay=base_delay, max_retries=max_retries)

    while True:
        status, headers, body = request_func()

        if status != 429:
            backoff.reset()
            return status, headers, body

        retry_after = None
        if "Retry-After" in headers:
            try:
                retry_after = float(headers["Retry-After"])
            except (ValueError, TypeError):
                pass

        if not backoff.wait_and_retry(retry_after):
            logger.error("Max retries exceeded for rate-limited request")
            return status, headers, body
'''),
]
