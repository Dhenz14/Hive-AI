"""API gateway patterns — rate limiting, request transformation, authentication middleware, circuit breaking, request aggregation."""

PAIRS = [
    (
        "api-gateway/rate-limiting",
        "Implement token bucket and sliding window rate limiting algorithms in Python for an API gateway, with per-client limits, burst handling, and Redis-backed distributed state.",
        '''Token bucket and sliding window rate limiters for API gateway:

```python
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: float          # Unix timestamp when bucket refills
    retry_after: float = 0   # seconds until next allowed request


class RateLimiter(ABC):
    @abstractmethod
    async def check(self, key: str) -> RateLimitResult:
        ...


# ── Token Bucket ──────────────────────────────────────────────────

class TokenBucketLimiter(RateLimiter):
    """Token bucket rate limiter backed by Redis.

    Tokens refill at a constant rate. Bursts are allowed up to
    the bucket capacity. Implemented with a single Lua script
    for atomic check-and-decrement.
    """

    LUA_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])   -- tokens per second
    local now = tonumber(ARGV[3])
    local requested = tonumber(ARGV[4])

    -- Get current state
    local bucket = redis.call("HMGET", key, "tokens", "last_refill")
    local tokens = tonumber(bucket[1])
    local last_refill = tonumber(bucket[2])

    -- Initialize if new bucket
    if tokens == nil then
        tokens = capacity
        last_refill = now
    end

    -- Refill tokens based on elapsed time
    local elapsed = math.max(0, now - last_refill)
    tokens = math.min(capacity, tokens + elapsed * refill_rate)

    local allowed = 0
    local remaining = tokens

    if tokens >= requested then
        tokens = tokens - requested
        allowed = 1
        remaining = tokens
    end

    -- Save state with TTL (auto-cleanup inactive buckets)
    redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
    redis.call("EXPIRE", key, math.ceil(capacity / refill_rate) + 10)

    -- Calculate reset time (when bucket will be full)
    local deficit = capacity - tokens
    local reset_in = deficit / refill_rate

    return {allowed, math.floor(remaining), tostring(now + reset_in)}
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        capacity: int = 100,
        refill_rate: float = 10.0,    # tokens per second
        key_prefix: str = "ratelimit:tb",
    ) -> None:
        self._redis = redis_client
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._prefix = key_prefix
        self._script_sha: str | None = None

    async def _ensure_script(self) -> str:
        if self._script_sha is None:
            self._script_sha = await self._redis.script_load(self.LUA_SCRIPT)
        return self._script_sha

    async def check(self, key: str, tokens: int = 1) -> RateLimitResult:
        sha = await self._ensure_script()
        now = time.time()

        result = await self._redis.evalsha(
            sha, 1, f"{self._prefix}:{key}",
            str(self._capacity),
            str(self._refill_rate),
            str(now),
            str(tokens),
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2])

        retry_after = 0.0
        if not allowed:
            retry_after = max(0, tokens / self._refill_rate)

        return RateLimitResult(
            allowed=allowed,
            limit=self._capacity,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
        )


# ── Sliding Window Log ────────────────────────────────────────────

class SlidingWindowLogLimiter(RateLimiter):
    """Sliding window log rate limiter using Redis sorted sets.

    Tracks exact timestamps of each request. Most accurate but
    higher memory usage (stores each request timestamp).
    """

    LUA_SCRIPT = """
    local key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local window_ms = tonumber(ARGV[2])
    local now_ms = tonumber(ARGV[3])
    local request_id = ARGV[4]

    -- Remove expired entries
    local window_start = now_ms - window_ms
    redis.call("ZREMRANGEBYSCORE", key, "-inf", window_start)

    -- Count current requests in window
    local current = redis.call("ZCARD", key)

    if current < limit then
        -- Add this request
        redis.call("ZADD", key, now_ms, request_id)
        redis.call("PEXPIRE", key, window_ms + 1000)
        return {1, limit - current - 1}
    end

    -- Get oldest entry to calculate reset time
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    local reset_ms = 0
    if #oldest > 0 then
        reset_ms = tonumber(oldest[2]) + window_ms
    end

    return {0, 0, tostring(reset_ms)}
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        limit: int = 100,
        window_seconds: float = 60.0,
        key_prefix: str = "ratelimit:sw",
    ) -> None:
        self._redis = redis_client
        self._limit = limit
        self._window_ms = int(window_seconds * 1000)
        self._prefix = key_prefix
        self._script_sha: str | None = None

    async def _ensure_script(self) -> str:
        if self._script_sha is None:
            self._script_sha = await self._redis.script_load(self.LUA_SCRIPT)
        return self._script_sha

    async def check(self, key: str) -> RateLimitResult:
        import uuid
        sha = await self._ensure_script()
        now_ms = int(time.time() * 1000)
        request_id = f"{now_ms}:{uuid.uuid4().hex[:8]}"

        result = await self._redis.evalsha(
            sha, 1, f"{self._prefix}:{key}",
            str(self._limit),
            str(self._window_ms),
            str(now_ms),
            request_id,
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2]) / 1000 if len(result) > 2 else time.time() + self._window_ms / 1000

        return RateLimitResult(
            allowed=allowed,
            limit=self._limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=max(0, reset_at - time.time()) if not allowed else 0,
        )


# ── Sliding Window Counter (memory-efficient) ────────────────────

class SlidingWindowCounterLimiter(RateLimiter):
    """Sliding window counter — hybrid of fixed window and sliding log.

    Uses two fixed windows and interpolates the count based on
    the position within the current window. Good balance of
    accuracy and memory efficiency.
    """

    LUA_SCRIPT = """
    local key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])      -- window size in seconds
    local now = tonumber(ARGV[3])

    -- Calculate current and previous window keys
    local current_window = math.floor(now / window)
    local prev_window = current_window - 1

    local curr_key = key .. ":" .. current_window
    local prev_key = key .. ":" .. prev_window

    -- Get counts
    local curr_count = tonumber(redis.call("GET", curr_key) or "0")
    local prev_count = tonumber(redis.call("GET", prev_key) or "0")

    -- Weight previous window by overlap percentage
    local elapsed_in_window = now - (current_window * window)
    local weight = 1 - (elapsed_in_window / window)
    local estimated = prev_count * weight + curr_count

    if estimated < limit then
        -- Increment current window
        redis.call("INCR", curr_key)
        redis.call("EXPIRE", curr_key, window * 2 + 1)
        local remaining = math.floor(limit - estimated - 1)
        return {1, math.max(0, remaining)}
    end

    -- Calculate when enough of the previous window will have rolled off
    local needed = estimated - limit + 1
    local wait = (needed / prev_count) * window
    local reset_at = now + math.max(0, wait)

    return {0, 0, tostring(reset_at)}
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        limit: int = 100,
        window_seconds: int = 60,
        key_prefix: str = "ratelimit:swc",
    ) -> None:
        self._redis = redis_client
        self._limit = limit
        self._window = window_seconds
        self._prefix = key_prefix
        self._script_sha: str | None = None

    async def _ensure_script(self) -> str:
        if self._script_sha is None:
            self._script_sha = await self._redis.script_load(self.LUA_SCRIPT)
        return self._script_sha

    async def check(self, key: str) -> RateLimitResult:
        sha = await self._ensure_script()
        now = time.time()

        result = await self._redis.evalsha(
            sha, 1, f"{self._prefix}:{key}",
            str(self._limit),
            str(self._window),
            str(now),
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2]) if len(result) > 2 else now + self._window

        return RateLimitResult(
            allowed=allowed,
            limit=self._limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=max(0, reset_at - now) if not allowed else 0,
        )


# ── Multi-tier rate limiting ─────────────────────────────────────

class MultiTierRateLimiter:
    """Apply multiple rate limits simultaneously.

    Example tiers:
      - 10 requests/second (burst protection)
      - 100 requests/minute (sustained rate)
      - 5000 requests/hour (quota)
    """

    def __init__(self, limiters: list[tuple[str, RateLimiter]]) -> None:
        self._limiters = limiters  # (name, limiter) pairs

    async def check(self, key: str) -> tuple[bool, dict[str, RateLimitResult]]:
        results = {}
        all_allowed = True

        for name, limiter in self._limiters:
            result = await limiter.check(key)
            results[name] = result
            if not result.allowed:
                all_allowed = False
                break  # fail fast on first limit hit

        return all_allowed, results


# ── FastAPI middleware integration ────────────────────────────────

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies rate limiting to all requests."""

    def __init__(self, app: Any, limiter: RateLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    def _get_client_key(self, request: Request) -> str:
        # Prefer API key, fall back to IP
        api_key = request.headers.get("x-api-key", "")
        if api_key:
            return f"apikey:{api_key}"
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        client = request.client
        return f"ip:{client.host}" if client else "ip:unknown"

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        key = self._get_client_key(request)
        result = await self._limiter.check(key)

        # Always include rate limit headers
        headers = {
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(result.reset_at)),
        }

        if not result.allowed:
            headers["Retry-After"] = str(int(result.retry_after) + 1)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests",
                    "retry_after": result.retry_after,
                },
                headers=headers,
            )

        response = await call_next(request)
        for k, v in headers.items():
            response.headers[k] = v
        return response
```

Rate limiting algorithms comparison:

| Algorithm | Accuracy | Memory | Burst handling | Complexity |
|---|---|---|---|---|
| Token bucket | Good | O(1) | Allows controlled bursts | Low |
| Sliding window log | Exact | O(N) per key | Strict limit | Medium |
| Sliding window counter | Approximate | O(1) | Smoothed bursts | Medium |
| Fixed window | Inexact at boundaries | O(1) | 2x burst at boundary | Low |
| Leaky bucket | Exact | O(1) | No bursts, smooth rate | Low |

Key patterns:
- **Lua scripts** ensure atomic check-and-update in Redis
- **Multi-tier limits** enforce both burst and sustained rate limits
- **Standard headers** (X-RateLimit-*, Retry-After) per IETF draft
- **Key strategy**: API key > forwarded IP > client IP
- **TTL on Redis keys** prevents memory leaks for inactive clients
'''
    ),
    (
        "api-gateway/request-transformation",
        "Build a request/response transformation pipeline for an API gateway that handles header injection, body mapping, field filtering, protocol translation, and response shaping.",
        '''Request/response transformation pipeline for an API gateway:

```python
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response


# ── Transformation primitives ─────────────────────────────────────

@dataclass
class TransformContext:
    """Shared context available to all transforms in the pipeline."""
    request_method: str
    request_path: str
    request_headers: dict[str, str]
    request_body: dict[str, Any] | None
    response_status: int = 0
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.monotonic)


class RequestTransform(ABC):
    """Base class for request transformations."""

    @abstractmethod
    async def transform_request(
        self, ctx: TransformContext,
    ) -> TransformContext:
        ...


class ResponseTransform(ABC):
    """Base class for response transformations."""

    @abstractmethod
    async def transform_response(
        self, ctx: TransformContext,
    ) -> TransformContext:
        ...


# ── Header transforms ────────────────────────────────────────────

class InjectHeaders(RequestTransform):
    """Add or override request headers before forwarding to upstream."""

    def __init__(self, headers: dict[str, str | Callable[[], str]]) -> None:
        self._headers = headers

    async def transform_request(self, ctx: TransformContext) -> TransformContext:
        for key, value in self._headers.items():
            if callable(value):
                ctx.request_headers[key] = value()
            else:
                ctx.request_headers[key] = value
        return ctx


class StripHeaders(RequestTransform):
    """Remove sensitive headers before forwarding to upstream."""

    def __init__(self, headers: list[str]) -> None:
        self._headers = {h.lower() for h in headers}

    async def transform_request(self, ctx: TransformContext) -> TransformContext:
        ctx.request_headers = {
            k: v for k, v in ctx.request_headers.items()
            if k.lower() not in self._headers
        }
        return ctx


class CORSHeaders(ResponseTransform):
    """Add CORS headers to responses."""

    def __init__(
        self,
        allowed_origins: list[str] = ["*"],
        allowed_methods: list[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allowed_headers: list[str] = ["Content-Type", "Authorization"],
        max_age: int = 86400,
    ) -> None:
        self._origins = allowed_origins
        self._methods = allowed_methods
        self._headers = allowed_headers
        self._max_age = max_age

    async def transform_response(self, ctx: TransformContext) -> TransformContext:
        origin = ctx.request_headers.get("origin", "")
        if "*" in self._origins or origin in self._origins:
            ctx.response_headers["Access-Control-Allow-Origin"] = (
                origin if origin in self._origins else "*"
            )
        ctx.response_headers["Access-Control-Allow-Methods"] = ", ".join(self._methods)
        ctx.response_headers["Access-Control-Allow-Headers"] = ", ".join(self._headers)
        ctx.response_headers["Access-Control-Max-Age"] = str(self._max_age)
        return ctx


# ── Body transforms ──────────────────────────────────────────────

class FieldMapping(RequestTransform):
    """Rename fields in the request body.

    Useful for adapting client-facing API schema to
    upstream service\'s internal schema.
    """

    def __init__(self, mappings: dict[str, str]) -> None:
        self._mappings = mappings   # {source_field: target_field}

    async def transform_request(self, ctx: TransformContext) -> TransformContext:
        if not ctx.request_body:
            return ctx

        new_body = {}
        for key, value in ctx.request_body.items():
            mapped_key = self._mappings.get(key, key)
            new_body[mapped_key] = value

        ctx.request_body = new_body
        return ctx


class FieldFilter(ResponseTransform):
    """Filter response fields based on a whitelist or client request.

    Supports the `?fields=name,email,id` query parameter pattern.
    """

    def __init__(self, default_fields: set[str] | None = None) -> None:
        self._default_fields = default_fields

    async def transform_response(self, ctx: TransformContext) -> TransformContext:
        if not ctx.response_body or not isinstance(ctx.response_body, dict):
            return ctx

        # Check if client requested specific fields
        requested = ctx.metadata.get("requested_fields")
        fields = requested or self._default_fields

        if fields:
            if isinstance(ctx.response_body, list):
                ctx.response_body = [
                    {k: v for k, v in item.items() if k in fields}
                    for item in ctx.response_body
                ]
            elif isinstance(ctx.response_body, dict):
                ctx.response_body = {
                    k: v for k, v in ctx.response_body.items()
                    if k in fields
                }

        return ctx


class ResponseEnvelope(ResponseTransform):
    """Wrap responses in a standard envelope format."""

    async def transform_response(self, ctx: TransformContext) -> TransformContext:
        elapsed_ms = (time.monotonic() - ctx.start_time) * 1000
        ctx.response_body = {
            "success": 200 <= ctx.response_status < 400,
            "data": ctx.response_body,
            "metadata": {
                "request_id": ctx.metadata.get("request_id", ""),
                "duration_ms": round(elapsed_ms, 1),
                "timestamp": time.time(),
            },
        }
        return ctx


class PaginationTransform(ResponseTransform):
    """Transform array responses into paginated format with cursors."""

    def __init__(self, default_page_size: int = 20, max_page_size: int = 100) -> None:
        self._default_size = default_page_size
        self._max_size = max_page_size

    async def transform_response(self, ctx: TransformContext) -> TransformContext:
        if not isinstance(ctx.response_body, list):
            return ctx

        page_size = min(
            int(ctx.metadata.get("page_size", self._default_size)),
            self._max_size,
        )
        cursor = ctx.metadata.get("cursor", 0)

        items = ctx.response_body
        page = items[cursor:cursor + page_size]
        has_more = len(items) > cursor + page_size

        ctx.response_body = {
            "items": page,
            "pagination": {
                "page_size": page_size,
                "has_more": has_more,
                "next_cursor": cursor + page_size if has_more else None,
                "total": len(items),
            },
        }
        return ctx


# ── URL rewriting ─────────────────────────────────────────────────

class URLRewriter(RequestTransform):
    """Rewrite request paths for upstream routing.

    Maps external-facing paths to internal service paths.
    Supports regex patterns with capture groups.
    """

    def __init__(self, rules: list[tuple[str, str]]) -> None:
        self._rules = [(re.compile(pattern), replacement) for pattern, replacement in rules]

    async def transform_request(self, ctx: TransformContext) -> TransformContext:
        for pattern, replacement in self._rules:
            new_path, count = pattern.subn(replacement, ctx.request_path)
            if count > 0:
                ctx.metadata["original_path"] = ctx.request_path
                ctx.request_path = new_path
                break
        return ctx


# ── Transformation pipeline ───────────────────────────────────────

class TransformPipeline:
    """Ordered pipeline of request and response transforms.

    Request transforms run in order before forwarding.
    Response transforms run in reverse order after receiving.
    """

    def __init__(self) -> None:
        self._request_transforms: list[RequestTransform] = []
        self._response_transforms: list[ResponseTransform] = []

    def add_request_transform(self, transform: RequestTransform) -> TransformPipeline:
        self._request_transforms.append(transform)
        return self

    def add_response_transform(self, transform: ResponseTransform) -> TransformPipeline:
        self._response_transforms.append(transform)
        return self

    async def process_request(self, ctx: TransformContext) -> TransformContext:
        for transform in self._request_transforms:
            ctx = await transform.transform_request(ctx)
        return ctx

    async def process_response(self, ctx: TransformContext) -> TransformContext:
        for transform in reversed(self._response_transforms):
            ctx = await transform.transform_response(ctx)
        return ctx


# ── Usage: configure pipeline for a route ─────────────────────────

def create_order_pipeline() -> TransformPipeline:
    import uuid
    return (
        TransformPipeline()
        # Request transforms
        .add_request_transform(StripHeaders([
            "x-internal-token", "x-debug-mode",
        ]))
        .add_request_transform(InjectHeaders({
            "X-Request-ID": lambda: str(uuid.uuid4()),
            "X-Gateway-Version": "2.0",
            "X-Forwarded-Proto": "https",
        }))
        .add_request_transform(URLRewriter([
            (r"^/api/v2/orders/(.+)/items$", r"/internal/orders/\\1/line-items"),
            (r"^/api/v2/orders$", r"/internal/orders"),
        ]))
        .add_request_transform(FieldMapping({
            "order_items": "line_items",
            "customer_name": "buyer_name",
        }))
        # Response transforms
        .add_response_transform(FieldFilter())
        .add_response_transform(CORSHeaders(allowed_origins=["https://app.example.com"]))
        .add_response_transform(ResponseEnvelope())
    )
```

Transformation pipeline architecture:

| Phase | Direction | Transforms run | Order |
|---|---|---|---|
| Pre-flight | Request | Strip headers, inject headers, URL rewrite | Forward |
| Body mapping | Request | Field rename, body restructure | Forward |
| Post-upstream | Response | Filter fields, paginate | Reverse |
| Envelope | Response | Wrap in standard format, add metadata | Reverse |

Key design decisions:
- **Pipeline pattern** makes transforms composable and testable in isolation
- **Reverse execution** for response transforms matches middleware conventions
- **Lazy callables** for headers (e.g., UUID generation) run at transform time
- **Context object** carries state through the entire pipeline
- **URL rewriting with regex** supports versioned and restructured routes
'''
    ),
    (
        "api-gateway/auth-middleware",
        "Build authentication middleware for an API gateway supporting JWT, API key, and OAuth2 with role-based access control, token caching, and multiple auth strategies.",
        '''API gateway authentication middleware with JWT, API key, and RBAC:

```python
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
import jwt
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("gateway.auth")


class AuthResult(str, Enum):
    AUTHENTICATED = "authenticated"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"


@dataclass
class Identity:
    """Authenticated identity with claims and permissions."""
    subject: str               # user ID or service ID
    auth_method: str           # "jwt", "api_key", "oauth2"
    roles: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    claims: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = ""
    expires_at: float = 0      # Unix timestamp


@dataclass
class AuthDecision:
    result: AuthResult
    identity: Identity | None = None
    error: str = ""


# ── Token cache ───────────────────────────────────────────────────

class TokenCache:
    """LRU cache for validated tokens to avoid repeated verification.

    Caches the Identity result for a token hash. TTL ensures tokens
    are re-validated periodically.
    """

    def __init__(self, max_size: int = 10_000, ttl_seconds: int = 300) -> None:
        self._cache: dict[str, tuple[Identity, float]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()[:32]

    async def get(self, token: str) -> Identity | None:
        key = self._hash_token(token)
        entry = self._cache.get(key)
        if entry is None:
            return None
        identity, cached_at = entry
        if time.time() - cached_at > self._ttl:
            async with self._lock:
                self._cache.pop(key, None)
            return None
        return identity

    async def put(self, token: str, identity: Identity) -> None:
        key = self._hash_token(token)
        async with self._lock:
            if len(self._cache) >= self._max_size:
                # Evict oldest entry
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[key] = (identity, time.time())

    async def invalidate(self, token: str) -> None:
        key = self._hash_token(token)
        async with self._lock:
            self._cache.pop(key, None)


# ── Authentication strategies ─────────────────────────────────────

class AuthStrategy(ABC):
    """Base class for authentication strategies."""

    @abstractmethod
    async def authenticate(self, request: Request) -> AuthDecision:
        ...

    @abstractmethod
    def can_handle(self, request: Request) -> bool:
        ...


class JWTAuthStrategy(AuthStrategy):
    """JWT Bearer token authentication.

    Supports RS256 (asymmetric) with JWKS endpoint for key rotation,
    and HS256 (symmetric) for service-to-service auth.
    """

    def __init__(
        self,
        jwks_url: str | None = None,
        secret: str | None = None,
        audience: str = "",
        issuer: str = "",
        algorithms: list[str] | None = None,
    ) -> None:
        self._jwks_url = jwks_url
        self._secret = secret
        self._audience = audience
        self._issuer = issuer
        self._algorithms = algorithms or ["RS256"]
        self._jwks_cache: dict[str, Any] = {}
        self._jwks_cache_time: float = 0

    def can_handle(self, request: Request) -> bool:
        auth = request.headers.get("authorization", "")
        return auth.lower().startswith("bearer ")

    async def authenticate(self, request: Request) -> AuthDecision:
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:]  # strip "Bearer "

        try:
            if self._jwks_url:
                signing_key = await self._get_signing_key(token)
                payload = jwt.decode(
                    token,
                    signing_key,
                    algorithms=self._algorithms,
                    audience=self._audience or None,
                    issuer=self._issuer or None,
                )
            else:
                payload = jwt.decode(
                    token,
                    self._secret,
                    algorithms=["HS256"],
                    audience=self._audience or None,
                )

            identity = Identity(
                subject=payload.get("sub", ""),
                auth_method="jwt",
                roles=payload.get("roles", []),
                permissions=set(payload.get("permissions", [])),
                claims=payload,
                tenant_id=payload.get("tenant_id", ""),
                expires_at=payload.get("exp", 0),
            )
            return AuthDecision(result=AuthResult.AUTHENTICATED, identity=identity)

        except jwt.ExpiredSignatureError:
            return AuthDecision(result=AuthResult.UNAUTHORIZED, error="Token expired")
        except jwt.InvalidTokenError as e:
            return AuthDecision(result=AuthResult.UNAUTHORIZED, error=f"Invalid token: {e}")

    async def _get_signing_key(self, token: str) -> Any:
        """Fetch JWKS and find the matching key for the token."""
        # Cache JWKS for 1 hour
        if time.time() - self._jwks_cache_time > 3600 or not self._jwks_cache:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self._jwks_url)
                self._jwks_cache = resp.json()
                self._jwks_cache_time = time.time()

        from jwt import PyJWKClient
        jwk_client = PyJWKClient(self._jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        return signing_key.key


class APIKeyStrategy(AuthStrategy):
    """API key authentication via header or query parameter."""

    def __init__(
        self,
        key_lookup: dict[str, dict[str, Any]] | None = None,
        header_name: str = "x-api-key",
        query_param: str = "api_key",
    ) -> None:
        self._keys = key_lookup or {}
        self._header = header_name
        self._query_param = query_param

    def can_handle(self, request: Request) -> bool:
        return bool(
            request.headers.get(self._header)
            or request.query_params.get(self._query_param)
        )

    async def authenticate(self, request: Request) -> AuthDecision:
        api_key = (
            request.headers.get(self._header)
            or request.query_params.get(self._query_param, "")
        )

        # Hash the key for lookup (keys stored hashed in production)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_info = self._keys.get(key_hash) or self._keys.get(api_key)

        if not key_info:
            return AuthDecision(result=AuthResult.UNAUTHORIZED, error="Invalid API key")

        if key_info.get("revoked"):
            return AuthDecision(result=AuthResult.UNAUTHORIZED, error="API key revoked")

        identity = Identity(
            subject=key_info.get("client_id", ""),
            auth_method="api_key",
            roles=key_info.get("roles", []),
            permissions=set(key_info.get("permissions", [])),
            tenant_id=key_info.get("tenant_id", ""),
        )
        return AuthDecision(result=AuthResult.AUTHENTICATED, identity=identity)


# ── Role-based access control ─────────────────────────────────────

@dataclass
class RoutePolicy:
    path_pattern: str       # regex pattern
    methods: list[str]      # HTTP methods
    required_roles: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    allow_unauthenticated: bool = False


class RBACEnforcer:
    """Enforce role and permission requirements per route."""

    def __init__(self, policies: list[RoutePolicy]) -> None:
        import re
        self._policies = [
            (re.compile(p.path_pattern), p) for p in policies
        ]

    def check(
        self,
        method: str,
        path: str,
        identity: Identity | None,
    ) -> AuthDecision:
        for pattern, policy in self._policies:
            if pattern.match(path) and method.upper() in policy.methods:
                if policy.allow_unauthenticated:
                    return AuthDecision(result=AuthResult.AUTHENTICATED)

                if identity is None:
                    return AuthDecision(
                        result=AuthResult.UNAUTHORIZED,
                        error="Authentication required",
                    )

                # Check roles
                if policy.required_roles:
                    if not any(r in identity.roles for r in policy.required_roles):
                        return AuthDecision(
                            result=AuthResult.FORBIDDEN,
                            error=f"Required roles: {policy.required_roles}",
                        )

                # Check permissions
                if policy.required_permissions:
                    missing = set(policy.required_permissions) - identity.permissions
                    if missing:
                        return AuthDecision(
                            result=AuthResult.FORBIDDEN,
                            error=f"Missing permissions: {missing}",
                        )

                return AuthDecision(
                    result=AuthResult.AUTHENTICATED,
                    identity=identity,
                )

        # No matching policy — deny by default
        if identity:
            return AuthDecision(result=AuthResult.AUTHENTICATED, identity=identity)
        return AuthDecision(result=AuthResult.UNAUTHORIZED, error="No matching policy")


# ── Gateway auth middleware ───────────────────────────────────────

class GatewayAuthMiddleware:
    """Starlette middleware combining multiple auth strategies with RBAC."""

    PUBLIC_PATHS = frozenset({"/health", "/ready", "/metrics", "/docs", "/openapi.json"})

    def __init__(
        self,
        strategies: list[AuthStrategy],
        rbac: RBACEnforcer,
        cache: TokenCache | None = None,
    ) -> None:
        self._strategies = strategies
        self._rbac = rbac
        self._cache = cache or TokenCache()

    async def __call__(self, request: Request, call_next: Any) -> Any:
        # Skip auth for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Try each auth strategy
        identity: Identity | None = None
        for strategy in self._strategies:
            if strategy.can_handle(request):
                decision = await strategy.authenticate(request)
                if decision.result == AuthResult.AUTHENTICATED:
                    identity = decision.identity
                    break
                elif decision.result == AuthResult.UNAUTHORIZED:
                    return JSONResponse(
                        status_code=401,
                        content={"error": "unauthorized", "message": decision.error},
                        headers={"WWW-Authenticate": "Bearer"},
                    )

        # RBAC check
        rbac_decision = self._rbac.check(
            request.method, request.url.path, identity,
        )

        if rbac_decision.result == AuthResult.UNAUTHORIZED:
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized", "message": rbac_decision.error},
            )
        if rbac_decision.result == AuthResult.FORBIDDEN:
            return JSONResponse(
                status_code=403,
                content={"error": "forbidden", "message": rbac_decision.error},
            )

        # Inject identity into request state
        request.state.identity = identity
        response = await call_next(request)

        # Add identity headers for upstream services
        if identity:
            response.headers["X-Auth-Subject"] = identity.subject
            response.headers["X-Auth-Roles"] = ",".join(identity.roles)

        return response
```

Authentication strategy comparison:

| Strategy | Use case | Token lifetime | Revocation |
|---|---|---|---|
| JWT (RS256) | User-facing APIs | Short (15min) | JWKS rotation + deny list |
| JWT (HS256) | Service-to-service | Medium (1hr) | Secret rotation |
| API key | Third-party integrations | Long-lived | Immediate (DB lookup) |
| OAuth2 + introspection | Delegated auth | Variable | Token introspection endpoint |

Key patterns:
- **Strategy pattern** makes auth methods pluggable and composable
- **Token cache** avoids repeated JWKS fetches and JWT verification
- **RBAC enforcer** separates authorization from authentication
- **Deny by default** when no policy matches a route
- **Public paths** bypass auth entirely (health checks, docs)
- **Identity propagation** via headers to upstream services
'''
    ),
    (
        "api-gateway/circuit-breaking",
        "Implement a circuit breaker for an API gateway with half-open state, error rate tracking, configurable thresholds, and per-route circuit management.",
        '''API gateway circuit breaker with error rate tracking and per-route management:

```python
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import httpx

logger = logging.getLogger("gateway.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"          # normal operation
    OPEN = "open"              # failing — reject requests
    HALF_OPEN = "half_open"    # testing recovery


@dataclass
class CircuitConfig:
    """Configuration for a circuit breaker instance."""
    failure_threshold: int = 5         # failures to open circuit
    success_threshold: int = 3         # successes in half-open to close
    error_rate_threshold: float = 0.5  # 50% error rate to open
    window_size: int = 20              # rolling window of requests
    open_timeout: float = 30.0         # seconds before half-open
    half_open_max_calls: int = 3       # max concurrent calls in half-open
    timeout: float = 10.0              # request timeout in seconds
    # Status codes that count as failures
    failure_status_codes: frozenset[int] = frozenset({500, 502, 503, 504})
    # Exceptions that count as failures
    failure_exceptions: tuple[type, ...] = (
        httpx.TimeoutException,
        httpx.ConnectError,
        ConnectionError,
    )


@dataclass
class CircuitMetrics:
    """Tracks request outcomes in a rolling window."""
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    state_changes: int = 0
    # Rolling window of recent outcomes (True=success, False=failure)
    window: deque[bool] = field(default_factory=lambda: deque(maxlen=20))

    @property
    def error_rate(self) -> float:
        if not self.window:
            return 0.0
        failures = sum(1 for x in self.window if not x)
        return failures / len(self.window)


class CircuitBreaker:
    """Circuit breaker with error rate and consecutive failure tracking.

    State transitions:
      CLOSED -> OPEN:      error rate > threshold OR consecutive failures > threshold
      OPEN -> HALF_OPEN:   after open_timeout elapses
      HALF_OPEN -> CLOSED: consecutive successes >= success_threshold
      HALF_OPEN -> OPEN:   any failure in half-open
    """

    def __init__(self, name: str, config: CircuitConfig | None = None) -> None:
        self.name = name
        self.config = config or CircuitConfig()
        self.state = CircuitState.CLOSED
        self.metrics = CircuitMetrics(
            window=deque(maxlen=self.config.window_size),
        )
        self._opened_at: float = 0
        self._half_open_calls: int = 0
        self._lock = asyncio.Lock()

    @property
    def is_available(self) -> bool:
        """Check if the circuit allows requests."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.config.open_timeout:
                return True  # transition to half-open on next call
            return False
        # HALF_OPEN: limited concurrent calls
        return self._half_open_calls < self.config.half_open_max_calls

    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a function through the circuit breaker."""
        async with self._lock:
            if not self.is_available:
                raise CircuitOpenError(
                    f"Circuit \\'{self.name}\\' is OPEN. "
                    f"Retry after {self.config.open_timeout}s"
                )

            if self.state == CircuitState.OPEN:
                # Transition to half-open
                self._transition_to(CircuitState.HALF_OPEN)

            if self.state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout,
            )
            await self._on_success()
            return result
        except self.config.failure_exceptions as e:
            await self._on_failure()
            raise
        except asyncio.TimeoutError:
            await self._on_failure()
            raise

    async def record_response(self, status_code: int) -> None:
        """Record an HTTP response status code."""
        if status_code in self.config.failure_status_codes:
            await self._on_failure()
        else:
            await self._on_success()

    async def _on_success(self) -> None:
        async with self._lock:
            self.metrics.total_successes += 1
            self.metrics.total_requests += 1
            self.metrics.consecutive_successes += 1
            self.metrics.consecutive_failures = 0
            self.metrics.last_success_time = time.monotonic()
            self.metrics.window.append(True)

            if self.state == CircuitState.HALF_OPEN:
                if self.metrics.consecutive_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    async def _on_failure(self) -> None:
        async with self._lock:
            self.metrics.total_failures += 1
            self.metrics.total_requests += 1
            self.metrics.consecutive_failures += 1
            self.metrics.consecutive_successes = 0
            self.metrics.last_failure_time = time.monotonic()
            self.metrics.window.append(False)

            if self.state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                self._transition_to(CircuitState.OPEN)
            elif self.state == CircuitState.CLOSED:
                should_open = (
                    self.metrics.consecutive_failures >= self.config.failure_threshold
                    or (len(self.metrics.window) >= self.config.window_size
                        and self.metrics.error_rate >= self.config.error_rate_threshold)
                )
                if should_open:
                    self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self.state
        self.state = new_state
        self.metrics.state_changes += 1

        if new_state == CircuitState.OPEN:
            self._opened_at = time.monotonic()
            self._half_open_calls = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self.metrics.consecutive_successes = 0
        elif new_state == CircuitState.CLOSED:
            self.metrics.consecutive_failures = 0
            self._half_open_calls = 0

        logger.warning(
            f"Circuit \\'{self.name}\\' transitioned: {old_state.value} -> {new_state.value}"
        )

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "error_rate": round(self.metrics.error_rate, 3),
            "total_requests": self.metrics.total_requests,
            "total_failures": self.metrics.total_failures,
            "consecutive_failures": self.metrics.consecutive_failures,
            "state_changes": self.metrics.state_changes,
        }


class CircuitOpenError(Exception):
    pass


# ── Per-route circuit breaker registry ────────────────────────────

class CircuitBreakerRegistry:
    """Manages circuit breakers for different upstream services/routes.

    Each upstream gets its own circuit breaker with independent
    state tracking. This prevents one failing service from
    affecting requests to healthy services.
    """

    def __init__(self, default_config: CircuitConfig | None = None) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._default_config = default_config or CircuitConfig()
        self._route_configs: dict[str, CircuitConfig] = {}

    def configure_route(self, route: str, config: CircuitConfig) -> None:
        self._route_configs[route] = config

    def get(self, route: str) -> CircuitBreaker:
        if route not in self._breakers:
            config = self._route_configs.get(route, self._default_config)
            self._breakers[route] = CircuitBreaker(route, config)
        return self._breakers[route]

    def get_all_status(self) -> list[dict[str, Any]]:
        return [cb.get_status() for cb in self._breakers.values()]

    async def reset(self, route: str) -> bool:
        cb = self._breakers.get(route)
        if cb:
            async with cb._lock:
                cb._transition_to(CircuitState.CLOSED)
                cb.metrics = CircuitMetrics(
                    window=deque(maxlen=cb.config.window_size),
                )
            return True
        return False


# ── Gateway proxy with circuit breaking ───────────────────────────

class GatewayProxy:
    """HTTP reverse proxy with per-route circuit breaking."""

    def __init__(
        self,
        registry: CircuitBreakerRegistry,
        fallback_handler: Callable | None = None,
    ) -> None:
        self._registry = registry
        self._fallback = fallback_handler
        self._client = httpx.AsyncClient(follow_redirects=False)

    async def forward(
        self,
        route: str,
        upstream_url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> httpx.Response | dict:
        cb = self._registry.get(route)

        try:
            response = await cb.call(
                self._do_request,
                upstream_url, method, headers, body,
            )
            await cb.record_response(response.status_code)
            return response

        except CircuitOpenError:
            if self._fallback:
                return await self._fallback(route, upstream_url)
            return {
                "error": "service_unavailable",
                "message": f"Circuit breaker open for route \\'{route}\\'",
                "retry_after": cb.config.open_timeout,
            }

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if self._fallback:
                return await self._fallback(route, upstream_url)
            raise

    async def _do_request(
        self,
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> httpx.Response:
        return await self._client.request(
            method=method,
            url=url,
            headers=headers,
            content=body,
        )
```

Circuit breaker state machine:

| Current state | Condition | Next state | Action |
|---|---|---|---|
| CLOSED | Error rate > threshold | OPEN | Reject all requests |
| CLOSED | Consecutive failures > N | OPEN | Reject all requests |
| OPEN | Timeout elapsed | HALF_OPEN | Allow limited probe requests |
| HALF_OPEN | Probe succeeds (N times) | CLOSED | Resume normal operation |
| HALF_OPEN | Any probe fails | OPEN | Reset timeout, reject again |

Key patterns:
- **Per-route isolation**: One failing upstream does not affect others
- **Rolling window**: Error rate calculated over last N requests, not lifetime
- **Dual trigger**: Opens on either high error rate or consecutive failures
- **Fallback handler**: Return cached/default response when circuit is open
- **Manual reset**: Admin API to force-close a circuit after fixing upstream
'''
    ),
    (
        "api-gateway/request-aggregation",
        "Implement request aggregation (API composition) for an API gateway that fans out to multiple microservices, merges responses, and handles partial failures.",
        '''API gateway request aggregation with fan-out, merging, and partial failure handling:

```python
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import httpx

logger = logging.getLogger("gateway.aggregation")


class FetchStatus(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"    # dependency failed


@dataclass
class ServiceCall:
    """Definition of a single upstream service call."""
    name: str
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    timeout: float = 5.0
    required: bool = True       # fail entire request if this fails
    depends_on: list[str] = field(default_factory=list)
    transform: Callable[[Any], Any] | None = None  # post-process response
    fallback: Any = None        # default value on failure
    cache_ttl: int = 0          # cache response for N seconds


@dataclass
class ServiceResult:
    name: str
    status: FetchStatus
    data: Any = None
    status_code: int = 0
    duration_ms: float = 0
    error: str = ""


@dataclass
class AggregatedResponse:
    success: bool
    data: dict[str, Any]
    metadata: AggregationMetadata
    partial: bool = False       # True if some optional calls failed


@dataclass
class AggregationMetadata:
    total_calls: int
    successful: int
    failed: int
    total_duration_ms: float
    individual: list[dict[str, Any]]


class RequestAggregator:
    """Aggregates responses from multiple upstream services.

    Features:
    - Parallel fan-out for independent calls
    - Dependency ordering (call B after A completes)
    - Partial failure handling (required vs optional calls)
    - Per-call timeouts and fallbacks
    - Response transformation and merging
    - Simple in-memory caching
    """

    def __init__(self, overall_timeout: float = 15.0) -> None:
        self._overall_timeout = overall_timeout
        self._client = httpx.AsyncClient()
        self._cache: dict[str, tuple[Any, float]] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def aggregate(
        self,
        calls: list[ServiceCall],
        context: dict[str, Any] | None = None,
    ) -> AggregatedResponse:
        """Execute all service calls and merge responses.

        Calls are grouped by dependency level and executed in parallel
        within each level.
        """
        start = time.monotonic()
        results: dict[str, ServiceResult] = {}
        context = context or {}

        # Build dependency graph and execution levels
        levels = self._build_execution_levels(calls)

        try:
            async with asyncio.timeout(self._overall_timeout):
                for level in levels:
                    # Check if any required dependency failed
                    level_calls = []
                    for call in level:
                        deps_ok = all(
                            results.get(dep, ServiceResult(dep, FetchStatus.SUCCESS)).status
                            == FetchStatus.SUCCESS
                            for dep in call.depends_on
                        )
                        if deps_ok:
                            level_calls.append(call)
                        else:
                            results[call.name] = ServiceResult(
                                name=call.name,
                                status=FetchStatus.SKIPPED,
                                error="Dependency failed",
                            )

                    # Execute all calls in this level concurrently
                    if level_calls:
                        level_results = await asyncio.gather(
                            *(self._execute_call(call, results, context) for call in level_calls),
                            return_exceptions=True,
                        )
                        for call, result in zip(level_calls, level_results):
                            if isinstance(result, Exception):
                                results[call.name] = ServiceResult(
                                    name=call.name,
                                    status=FetchStatus.ERROR,
                                    error=str(result),
                                    data=call.fallback,
                                )
                            else:
                                results[call.name] = result

        except asyncio.TimeoutError:
            # Mark remaining calls as timed out
            for call in calls:
                if call.name not in results:
                    results[call.name] = ServiceResult(
                        name=call.name,
                        status=FetchStatus.TIMEOUT,
                        error="Overall aggregation timeout",
                        data=call.fallback,
                    )

        return self._build_response(calls, results, start)

    async def _execute_call(
        self,
        call: ServiceCall,
        previous_results: dict[str, ServiceResult],
        context: dict[str, Any],
    ) -> ServiceResult:
        """Execute a single upstream service call."""
        start = time.monotonic()

        # Check cache first
        if call.cache_ttl > 0:
            cached = self._get_cached(call.url)
            if cached is not None:
                return ServiceResult(
                    name=call.name,
                    status=FetchStatus.SUCCESS,
                    data=cached,
                    duration_ms=0,
                )

        # Interpolate URL with context and previous results
        url = self._interpolate_url(call.url, previous_results, context)

        try:
            response = await asyncio.wait_for(
                self._client.request(
                    method=call.method,
                    url=url,
                    headers=call.headers,
                    json=call.body if call.body else None,
                ),
                timeout=call.timeout,
            )

            elapsed = (time.monotonic() - start) * 1000

            if response.status_code >= 400:
                return ServiceResult(
                    name=call.name,
                    status=FetchStatus.ERROR,
                    data=call.fallback,
                    status_code=response.status_code,
                    duration_ms=elapsed,
                    error=f"HTTP {response.status_code}",
                )

            data = response.json()

            # Apply transform if provided
            if call.transform:
                data = call.transform(data)

            # Cache if configured
            if call.cache_ttl > 0:
                self._set_cached(call.url, data, call.cache_ttl)

            return ServiceResult(
                name=call.name,
                status=FetchStatus.SUCCESS,
                data=data,
                status_code=response.status_code,
                duration_ms=elapsed,
            )

        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            return ServiceResult(
                name=call.name,
                status=FetchStatus.TIMEOUT,
                data=call.fallback,
                duration_ms=elapsed,
                error=f"Timeout after {call.timeout}s",
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return ServiceResult(
                name=call.name,
                status=FetchStatus.ERROR,
                data=call.fallback,
                duration_ms=elapsed,
                error=str(e),
            )

    def _build_execution_levels(
        self, calls: list[ServiceCall],
    ) -> list[list[ServiceCall]]:
        """Topological sort of calls by dependencies into execution levels."""
        call_map = {c.name: c for c in calls}
        levels: list[list[ServiceCall]] = []
        assigned: set[str] = set()

        while len(assigned) < len(calls):
            current_level = []
            for call in calls:
                if call.name in assigned:
                    continue
                # All dependencies must be assigned to previous levels
                if all(dep in assigned for dep in call.depends_on):
                    current_level.append(call)
            if not current_level:
                # Circular dependency — add remaining calls
                current_level = [c for c in calls if c.name not in assigned]
            for c in current_level:
                assigned.add(c.name)
            levels.append(current_level)

        return levels

    def _build_response(
        self,
        calls: list[ServiceCall],
        results: dict[str, ServiceResult],
        start: float,
    ) -> AggregatedResponse:
        total_duration = (time.monotonic() - start) * 1000
        successful = sum(1 for r in results.values() if r.status == FetchStatus.SUCCESS)
        failed = sum(1 for r in results.values() if r.status != FetchStatus.SUCCESS)

        # Check if any required call failed
        required_failure = any(
            results[c.name].status != FetchStatus.SUCCESS
            for c in calls
            if c.required
        )

        # Merge all data into a single response
        merged_data = {}
        for name, result in results.items():
            if result.data is not None:
                merged_data[name] = result.data

        individual = [
            {
                "service": r.name,
                "status": r.status.value,
                "duration_ms": round(r.duration_ms, 1),
                "error": r.error or None,
            }
            for r in results.values()
        ]

        return AggregatedResponse(
            success=not required_failure,
            data=merged_data,
            partial=failed > 0 and not required_failure,
            metadata=AggregationMetadata(
                total_calls=len(calls),
                successful=successful,
                failed=failed,
                total_duration_ms=round(total_duration, 1),
                individual=individual,
            ),
        )

    def _interpolate_url(
        self,
        url: str,
        results: dict[str, ServiceResult],
        context: dict[str, Any],
    ) -> str:
        """Replace {placeholders} in URLs with values from context or previous results."""
        import re
        def replacer(match: re.Match) -> str:
            key = match.group(1)
            if "." in key:
                service, field_name = key.split(".", 1)
                result = results.get(service)
                if result and isinstance(result.data, dict):
                    return str(result.data.get(field_name, match.group(0)))
            return str(context.get(key, match.group(0)))
        return re.sub(r"\\{(\\w+(?:\\.\\w+)?)\\}", replacer, url)

    def _get_cached(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry and time.time() < entry[1]:
            return entry[0]
        return None

    def _set_cached(self, key: str, data: Any, ttl: int) -> None:
        self._cache[key] = (data, time.time() + ttl)


# ── Usage: product detail page aggregation ────────────────────────

async def get_product_page(product_id: str) -> AggregatedResponse:
    aggregator = RequestAggregator(overall_timeout=10.0)

    calls = [
        ServiceCall(
            name="product",
            url=f"http://product-service/api/products/{product_id}",
            required=True,
        ),
        ServiceCall(
            name="inventory",
            url=f"http://inventory-service/api/stock/{product_id}",
            required=False,
            fallback={"in_stock": True, "quantity": None},
            timeout=3.0,
        ),
        ServiceCall(
            name="reviews",
            url=f"http://review-service/api/reviews?product_id={product_id}&limit=5",
            required=False,
            fallback={"reviews": [], "average_rating": None},
            timeout=3.0,
            cache_ttl=300,  # cache reviews for 5 minutes
        ),
        ServiceCall(
            name="recommendations",
            url="http://rec-service/api/recommendations?product_id={product.id}&category={product.category}",
            required=False,
            depends_on=["product"],  # needs product data first
            fallback={"items": []},
            timeout=2.0,
        ),
        ServiceCall(
            name="pricing",
            url=f"http://pricing-service/api/prices/{product_id}",
            required=True,
            timeout=3.0,
        ),
    ]

    result = await aggregator.aggregate(calls, context={"product_id": product_id})
    await aggregator.close()
    return result
```

Aggregation patterns and trade-offs:

| Pattern | Latency | Complexity | Failure handling |
|---|---|---|---|
| Sequential | Sum of all calls | Low | Fail-fast or continue |
| Parallel fan-out | Max of all calls | Medium | Partial success possible |
| DAG (dependency levels) | Max per level, sum of levels | High | Skip dependents on failure |
| Scatter-gather | Max of all calls | Medium | Return first N responses |

Key design decisions:
- **Dependency DAG**: Topological sort determines execution order
- **URL interpolation**: Dynamic URLs from previous call results
- **Required vs optional**: Required failures abort; optional use fallbacks
- **Per-call timeouts**: Independent from overall aggregation timeout
- **Response merging**: Each service result keyed by name in final response
- **Caching**: Per-call TTL for data that changes infrequently
'''
    ),
]
"""
