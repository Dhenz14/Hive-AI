"""API patterns — API gateway, versioning, pagination, and rate limiting."""

PAIRS = [
    (
        "api/pagination-patterns",
        "Show API pagination patterns: cursor-based, offset-based, keyset, and comparison of approaches.",
        '''API pagination patterns:

```python
from dataclasses import dataclass
from typing import TypeVar, Generic
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
import base64
import json

app = FastAPI()
T = TypeVar("T")


# --- Paginated response model ---

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


# --- Offset pagination (simple, but slow for large offsets) ---

@app.get("/api/v1/users")
async def list_users_offset(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * page_size

    # SQL: SELECT * FROM users ORDER BY id LIMIT $1 OFFSET $2
    users = await db.fetch_all(
        "SELECT * FROM users ORDER BY id LIMIT $1 OFFSET $2",
        page_size, offset,
    )
    total = await db.fetch_val("SELECT COUNT(*) FROM users")

    return PaginatedResponse(
        items=users,
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


# --- Cursor-based pagination (efficient for large datasets) ---

class CursorResponse(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None
    prev_cursor: str | None
    has_more: bool


def encode_cursor(data: dict) -> str:
    """Encode cursor data as base64 string."""
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

def decode_cursor(cursor: str) -> dict:
    """Decode cursor string to data."""
    try:
        return json.loads(base64.urlsafe_b64decode(cursor).decode())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


@app.get("/api/v1/posts")
async def list_posts_cursor(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    direction: str = Query("next", regex="^(next|prev)$"),
):
    """Cursor-based pagination using (created_at, id) as cursor."""
    if cursor:
        cursor_data = decode_cursor(cursor)
        created_at = cursor_data["created_at"]
        last_id = cursor_data["id"]

        if direction == "next":
            # Forward: get items AFTER cursor
            posts = await db.fetch_all("""
                SELECT * FROM posts
                WHERE (created_at, id) < ($1, $2)
                ORDER BY created_at DESC, id DESC
                LIMIT $3
            """, created_at, last_id, limit + 1)
        else:
            # Backward: get items BEFORE cursor
            posts = await db.fetch_all("""
                SELECT * FROM posts
                WHERE (created_at, id) > ($1, $2)
                ORDER BY created_at ASC, id ASC
                LIMIT $3
            """, created_at, last_id, limit + 1)
            posts.reverse()
    else:
        # First page
        posts = await db.fetch_all("""
            SELECT * FROM posts
            ORDER BY created_at DESC, id DESC
            LIMIT $1
        """, limit + 1)

    has_more = len(posts) > limit
    posts = posts[:limit]

    next_cursor = None
    prev_cursor = None

    if posts:
        if has_more:
            last = posts[-1]
            next_cursor = encode_cursor({
                "created_at": last["created_at"].isoformat(),
                "id": last["id"],
            })
        if cursor:
            first = posts[0]
            prev_cursor = encode_cursor({
                "created_at": first["created_at"].isoformat(),
                "id": first["id"],
            })

    return CursorResponse(
        items=posts,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        has_more=has_more,
    )


# --- Keyset pagination (seek method) ---

@app.get("/api/v1/products")
async def list_products_keyset(
    after_id: int | None = None,
    after_price: float | None = None,
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("price", regex="^(price|name|created_at)$"),
):
    """Keyset pagination — deterministic, no skipped/duplicate rows."""
    if after_price is not None and after_id is not None:
        products = await db.fetch_all("""
            SELECT * FROM products
            WHERE (price, id) > ($1, $2)
            ORDER BY price ASC, id ASC
            LIMIT $3
        """, after_price, after_id, limit)
    else:
        products = await db.fetch_all("""
            SELECT * FROM products
            ORDER BY price ASC, id ASC
            LIMIT $1
        """, limit)

    return {
        "items": products,
        "next": {
            "after_price": products[-1]["price"],
            "after_id": products[-1]["id"],
        } if products else None,
    }
```

Pagination patterns:
1. **Offset** — simple (`LIMIT/OFFSET`), but O(n) skip cost for large pages
2. **Cursor-based** — opaque base64 cursor, O(1) seek, stable during inserts
3. **Keyset** — `WHERE (col, id) > (last_val, last_id)`, no skipped rows
4. **`limit + 1` trick** — fetch one extra to determine `has_more` without COUNT
5. **Compound sort key** — always include `id` as tiebreaker for deterministic ordering'''
    ),
    (
        "api/rate-limiting-advanced",
        "Show advanced rate limiting patterns: sliding window, token bucket, distributed limiting with Redis.",
        '''Advanced rate limiting patterns:

```python
import time
import asyncio
from dataclasses import dataclass
from typing import Callable
from fastapi import FastAPI, Request, HTTPException, Response
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as redis


# --- Sliding window counter (Redis) ---

class SlidingWindowRateLimiter:
    """Rate limit using sliding window counter in Redis.

    More accurate than fixed windows — no burst at window boundaries.
    """

    def __init__(self, redis_client: redis.Redis, window_seconds: int, max_requests: int):
        self.redis = redis_client
        self.window = window_seconds
        self.max_requests = max_requests

    async def is_allowed(self, key: str) -> tuple[bool, dict]:
        """Check if request is allowed. Returns (allowed, info)."""
        now = time.time()
        window_start = now - self.window
        pipe_key = f"ratelimit:{key}"

        async with self.redis.pipeline(transaction=True) as pipe:
            # Remove expired entries
            pipe.zremrangebyscore(pipe_key, 0, window_start)
            # Count current window
            pipe.zcard(pipe_key)
            # Add current request
            pipe.zadd(pipe_key, {str(now): now})
            # Set expiry on the key
            pipe.expire(pipe_key, self.window)

            results = await pipe.execute()

        current_count = results[1]
        allowed = current_count < self.max_requests

        if not allowed:
            # Remove the request we just added
            await self.redis.zrem(pipe_key, str(now))

        remaining = max(0, self.max_requests - current_count - (1 if allowed else 0))

        # Calculate reset time
        if not allowed:
            oldest = await self.redis.zrange(pipe_key, 0, 0, withscores=True)
            reset_at = oldest[0][1] + self.window if oldest else now + self.window
        else:
            reset_at = now + self.window

        return allowed, {
            "limit": self.max_requests,
            "remaining": remaining,
            "reset": int(reset_at),
            "retry_after": int(reset_at - now) if not allowed else 0,
        }


# --- Token bucket (burst-friendly) ---

class TokenBucketLimiter:
    """Token bucket allows bursts up to bucket size, refills at steady rate."""

    def __init__(self, redis_client: redis.Redis, rate: float, burst: int):
        self.redis = redis_client
        self.rate = rate      # Tokens per second
        self.burst = burst    # Max tokens (bucket size)

    async def is_allowed(self, key: str, tokens: int = 1) -> tuple[bool, dict]:
        bucket_key = f"bucket:{key}"
        now = time.time()

        # Lua script for atomic token bucket
        lua_script = """
        local key = KEYS[1]
        local rate = tonumber(ARGV[1])
        local burst = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local requested = tonumber(ARGV[4])

        local data = redis.call('hmget', key, 'tokens', 'last_time')
        local tokens = tonumber(data[1]) or burst
        local last_time = tonumber(data[2]) or now

        -- Add tokens based on elapsed time
        local elapsed = now - last_time
        tokens = math.min(burst, tokens + elapsed * rate)

        local allowed = 0
        if tokens >= requested then
            tokens = tokens - requested
            allowed = 1
        end

        redis.call('hmset', key, 'tokens', tokens, 'last_time', now)
        redis.call('expire', key, math.ceil(burst / rate) * 2)

        return {allowed, math.floor(tokens)}
        """

        result = await self.redis.eval(
            lua_script, 1, bucket_key,
            self.rate, self.burst, now, tokens,
        )

        allowed = bool(result[0])
        remaining = int(result[1])

        return allowed, {
            "limit": self.burst,
            "remaining": remaining,
            "retry_after": int(1 / self.rate) if not allowed else 0,
        }


# --- FastAPI rate limit middleware ---

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: SlidingWindowRateLimiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        # Rate limit by IP (or API key, user ID, etc.)
        client_ip = request.client.host
        key = f"ip:{client_ip}"

        # Different limits for different endpoints
        if request.url.path.startswith("/api/auth/login"):
            key = f"login:{client_ip}"
            # Use stricter limiter for login

        allowed, info = await self.limiter.is_allowed(key)

        if not allowed:
            return Response(
                content='{"error": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(info["reset"]),
                    "Retry-After": str(info["retry_after"]),
                },
            )

        response = await call_next(request)

        # Add rate limit headers to all responses
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response


# --- Setup ---

app = FastAPI()
redis_client = redis.Redis(host="localhost", port=6379)

# 100 requests per minute per IP
limiter = SlidingWindowRateLimiter(redis_client, window_seconds=60, max_requests=100)
app.add_middleware(RateLimitMiddleware, limiter=limiter)
```

Rate limiting patterns:
1. **Sliding window** — Redis sorted set tracks exact request timestamps
2. **Token bucket** — allows bursts up to bucket size, steady refill rate
3. **Lua script** — atomic Redis operations prevent race conditions
4. **`X-RateLimit-*` headers** — standard headers communicate limits to clients
5. **`Retry-After`** — tells clients exactly when to retry after 429'''
    ),
]
"""
