"""API design — REST best practices, versioning, pagination, and rate limiting."""

PAIRS = [
    (
        "api/rest-design",
        "Show REST API design patterns: resource naming, HTTP methods, status codes, error responses, and HATEOAS.",
        '''REST API design best practices:

```python
from fastapi import FastAPI, HTTPException, Query, Path, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum

app = FastAPI(title="API Design Patterns")


# --- Resource naming conventions ---

# Good: plural nouns, hierarchical
# GET    /api/v1/users                  — List users
# POST   /api/v1/users                  — Create user
# GET    /api/v1/users/{id}             — Get user
# PUT    /api/v1/users/{id}             — Replace user
# PATCH  /api/v1/users/{id}             — Partial update
# DELETE /api/v1/users/{id}             — Delete user
# GET    /api/v1/users/{id}/orders      — User's orders (sub-resource)
# POST   /api/v1/users/{id}/orders      — Create order for user

# Bad:
# GET /api/getUser          — verb in URL
# POST /api/createUser      — CRUD in URL
# GET /api/user             — singular


# --- Request/Response models ---

class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="user", pattern="^(user|admin|moderator)$")

class UserUpdate(BaseModel):
    """All fields optional for PATCH."""
    email: Optional[EmailStr] = None
    name: Optional[str] = Field(None, min_length=1, max_length=100)

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Consistent error response ---

class ErrorResponse(BaseModel):
    error: str        # Machine-readable code
    message: str      # Human-readable message
    details: Optional[list[dict]] = None  # Field-level errors
    request_id: str = ""

# Standard error responses:
# 400 Bad Request       — invalid input, validation errors
# 401 Unauthorized      — missing or invalid auth
# 403 Forbidden         — authenticated but not authorized
# 404 Not Found         — resource doesn't exist
# 409 Conflict          — duplicate email, version conflict
# 422 Unprocessable     — valid JSON but business rule violation
# 429 Too Many Requests — rate limited
# 500 Internal Error    — server error (never expose internals)

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if isinstance(exc.detail, str) else "error",
            "message": str(exc.detail),
            "request_id": request.state.request_id,
        },
    )


# --- Proper HTTP status codes ---

@app.post("/api/v1/users", status_code=201, response_model=UserResponse)
async def create_user(data: UserCreate):
    """201 Created with Location header."""
    user = await user_service.create(data)
    return user

@app.get("/api/v1/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str = Path(pattern="^[a-zA-Z0-9-]+$")):
    """200 OK or 404 Not Found."""
    user = await user_service.find_by_id(user_id)
    if not user:
        raise HTTPException(404, detail="User not found")
    return user

@app.patch("/api/v1/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, data: UserUpdate):
    """200 OK with updated resource."""
    user = await user_service.update(user_id, data.model_dump(exclude_unset=True))
    return user

@app.delete("/api/v1/users/{user_id}", status_code=204)
async def delete_user(user_id: str):
    """204 No Content on success."""
    await user_service.delete(user_id)


# --- Filtering, sorting, searching ---

class SortField(str, Enum):
    name = "name"
    created_at = "created_at"
    email = "email"

class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

@app.get("/api/v1/users", response_model=list[UserResponse])
async def list_users(
    # Filtering
    role: Optional[str] = Query(None, description="Filter by role"),
    search: Optional[str] = Query(None, description="Search name/email"),
    created_after: Optional[datetime] = Query(None),
    created_before: Optional[datetime] = Query(None),
    # Sorting
    sort_by: SortField = Query(SortField.created_at),
    sort_order: SortOrder = Query(SortOrder.desc),
    # Pagination (cursor-based)
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
):
    """List users with filtering, sorting, pagination."""
    return await user_service.list(
        role=role, search=search,
        created_after=created_after, created_before=created_before,
        sort_by=sort_by, sort_order=sort_order,
        limit=limit, cursor=cursor,
    )


# --- Idempotency key ---

@app.post("/api/v1/payments")
async def create_payment(
    data: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Idempotent POST — same key returns same result."""
    # Check if we've seen this key before
    existing = await cache.get(f"idempotency:{idempotency_key}")
    if existing:
        return JSONResponse(content=existing, status_code=200)

    result = await payment_service.create(data)
    await cache.set(f"idempotency:{idempotency_key}", result, ttl=86400)
    return JSONResponse(content=result, status_code=201)
```

REST API rules:
1. **Nouns, not verbs** — resources are things, HTTP methods are actions
2. **Consistent status codes** — 201 for create, 204 for delete, 4xx for client errors
3. **Cursor pagination** — stable, efficient for large datasets (not offset/limit)
4. **Idempotency keys** — safe retries for POST/payment endpoints
5. **Error format** — consistent structure with machine-readable code + human message'''
    ),
    (
        "api/pagination-patterns",
        "Show API pagination patterns: cursor-based, offset, keyset, and response envelope formats.",
        '''API pagination patterns:

```python
from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Optional, Generic, TypeVar
from datetime import datetime
import base64
import json

app = FastAPI()
T = TypeVar("T")


# --- Response envelope ---

class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: dict

    @classmethod
    def create(cls, items: list, has_next: bool, has_prev: bool,
               cursor: Optional[str] = None, total: Optional[int] = None):
        pagination = {
            "has_next": has_next,
            "has_previous": has_prev,
        }
        if cursor:
            pagination["next_cursor"] = cursor
        if total is not None:
            pagination["total"] = total
        return cls(data=items, pagination=pagination)


# --- Cursor-based pagination (recommended) ---

def encode_cursor(data: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(data).encode()
    ).decode()

def decode_cursor(cursor: str) -> dict:
    return json.loads(
        base64.urlsafe_b64decode(cursor.encode())
    )


@app.get("/api/v1/orders")
async def list_orders(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    status: Optional[str] = None,
):
    """Cursor-based pagination using composite key."""
    query = {}
    if status:
        query["status"] = status

    if cursor:
        decoded = decode_cursor(cursor)
        # Composite cursor: (created_at, id) for stable ordering
        query["$or"] = [
            {"created_at": {"$lt": decoded["created_at"]}},
            {
                "created_at": decoded["created_at"],
                "_id": {"$lt": decoded["id"]},
            },
        ]

    orders = await db.orders.find(query).sort(
        [("created_at", -1), ("_id", -1)]
    ).limit(limit + 1).to_list()

    has_next = len(orders) > limit
    orders = orders[:limit]

    next_cursor = None
    if has_next and orders:
        last = orders[-1]
        next_cursor = encode_cursor({
            "created_at": last["created_at"].isoformat(),
            "id": str(last["_id"]),
        })

    return {
        "data": [serialize_order(o) for o in orders],
        "pagination": {
            "has_next": has_next,
            "next_cursor": next_cursor,
            "limit": limit,
        },
    }


# --- Keyset pagination (SQL) ---

@app.get("/api/v1/products")
async def list_products(
    limit: int = Query(20, ge=1, le=100),
    after_id: Optional[int] = Query(None),
    after_price: Optional[float] = Query(None),
    sort_by: str = Query("price"),
):
    """Keyset pagination for SQL databases."""
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    # Keyset condition
    if after_price is not None and after_id is not None:
        query += " AND (price > $1 OR (price = $1 AND id > $2))"
        params.extend([after_price, after_id])

    query += f" ORDER BY price ASC, id ASC LIMIT ${len(params) + 1}"
    params.append(limit + 1)

    rows = await db.fetch(query, *params)
    has_next = len(rows) > limit
    rows = rows[:limit]

    return {
        "data": rows,
        "pagination": {
            "has_next": has_next,
            "next": {
                "after_price": rows[-1]["price"] if has_next else None,
                "after_id": rows[-1]["id"] if has_next else None,
            } if has_next else None,
        },
    }


# --- Offset pagination (simple but less efficient) ---

@app.get("/api/v1/search")
async def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Offset pagination — OK for search results, bad for large datasets."""
    offset = (page - 1) * per_page

    total = await db.products.count_documents({"$text": {"$search": q}})
    items = await db.products.find(
        {"$text": {"$search": q}},
        {"score": {"$meta": "textScore"}},
    ).sort(
        [("score", {"$meta": "textScore"})]
    ).skip(offset).limit(per_page).to_list()

    total_pages = (total + per_page - 1) // per_page

    return {
        "data": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
    }
```

Pagination patterns:
1. **Cursor-based** — most efficient, stable with concurrent writes (recommended for APIs)
2. **Keyset** — SQL version of cursor pagination (WHERE + ORDER BY)
3. **Offset** — simple but slow for deep pages and unstable with inserts
4. **Composite cursors** — use (sort_field, id) for deterministic ordering
5. **Fetch limit+1** — simple way to detect if next page exists'''
    ),
    (
        "api/rate-limiting",
        "Show API rate limiting patterns: token bucket, sliding window, per-user limits, and response headers.",
        '''API rate limiting patterns:

```python
import time
import redis
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.base import BaseHTTPMiddleware
from typing import Optional
import hashlib

app = FastAPI()


# --- Token bucket algorithm ---

class TokenBucket:
    """Rate limit using token bucket in Redis."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def allow(self, key: str, max_tokens: int,
              refill_rate: float, refill_interval: float = 1.0) -> dict:
        """
        Check if request is allowed.
        max_tokens: bucket capacity
        refill_rate: tokens added per interval
        refill_interval: seconds between refills
        """
        now = time.time()
        bucket_key = f"ratelimit:{key}"

        # Lua script for atomic token bucket
        script = """
        local key = KEYS[1]
        local max_tokens = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local refill_interval = tonumber(ARGV[3])
        local now = tonumber(ARGV[4])

        local bucket = redis.call('hmget', key, 'tokens', 'last_refill')
        local tokens = tonumber(bucket[1]) or max_tokens
        local last_refill = tonumber(bucket[2]) or now

        -- Refill tokens
        local elapsed = now - last_refill
        local refills = math.floor(elapsed / refill_interval)
        if refills > 0 then
            tokens = math.min(max_tokens, tokens + refills * refill_rate)
            last_refill = last_refill + refills * refill_interval
        end

        local allowed = tokens >= 1
        if allowed then
            tokens = tokens - 1
        end

        redis.call('hmset', key, 'tokens', tokens, 'last_refill', last_refill)
        redis.call('expire', key, math.ceil(max_tokens / refill_rate * refill_interval) + 10)

        return {allowed and 1 or 0, math.floor(tokens), math.ceil((1 - tokens) / refill_rate * refill_interval)}
        """

        result = self.redis.eval(
            script, 1, bucket_key,
            max_tokens, refill_rate, refill_interval, now,
        )

        return {
            "allowed": bool(result[0]),
            "remaining": int(result[1]),
            "retry_after": max(0, int(result[2])) if not result[0] else 0,
        }


# --- Sliding window counter ---

class SlidingWindow:
    """Rate limit using sliding window in Redis."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def allow(self, key: str, max_requests: int, window_seconds: int) -> dict:
        now = time.time()
        window_key = f"ratelimit:sw:{key}"

        pipe = self.redis.pipeline()
        # Remove old entries
        pipe.zremrangebyscore(window_key, 0, now - window_seconds)
        # Count current window
        pipe.zcard(window_key)
        # Add current request
        pipe.zadd(window_key, {f"{now}:{id(now)}": now})
        # Set expiry
        pipe.expire(window_key, window_seconds)
        results = pipe.execute()

        current_count = results[1]
        allowed = current_count < max_requests

        if not allowed:
            # Remove the request we just added
            self.redis.zremrangebyscore(window_key, now, now)

        return {
            "allowed": allowed,
            "remaining": max(0, max_requests - current_count - (1 if allowed else 0)),
            "reset": int(now) + window_seconds,
            "limit": max_requests,
        }


# --- Rate limit middleware ---

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_client):
        super().__init__(app)
        self.limiter = TokenBucket(redis_client)
        self.tiers = {
            "free": {"max_tokens": 60, "refill_rate": 1},      # 60/min
            "pro": {"max_tokens": 600, "refill_rate": 10},     # 600/min
            "enterprise": {"max_tokens": 6000, "refill_rate": 100},
        }

    async def dispatch(self, request: Request, call_next):
        # Identify client
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            client_id = hashlib.sha256(api_key.encode()).hexdigest()[:16]
            tier = await get_tier_for_key(api_key)
        else:
            client_id = request.client.host
            tier = "free"

        # Check rate limit
        config = self.tiers.get(tier, self.tiers["free"])
        key = f"{client_id}:{request.url.path}"
        result = self.limiter.allow(key, **config)

        # Set standard rate limit headers
        response_headers = {
            "X-RateLimit-Limit": str(config["max_tokens"]),
            "X-RateLimit-Remaining": str(result["remaining"]),
        }

        if not result["allowed"]:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded. Retry after {result['retry_after']}s",
                    "retry_after": result["retry_after"],
                },
                headers={
                    **response_headers,
                    "Retry-After": str(result["retry_after"]),
                },
            )

        response = await call_next(request)
        for key, value in response_headers.items():
            response.headers[key] = value
        return response
```

Rate limiting patterns:
1. **Token bucket** — smooth rate limiting with burst allowance
2. **Sliding window** — exact count within rolling time window
3. **Tiered limits** — different limits for free/pro/enterprise
4. **Standard headers** — `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`
5. **Per-endpoint** — different limits for read vs write endpoints'''
    ),
]
"""
