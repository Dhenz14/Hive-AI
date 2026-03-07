"""
Ambiguous request handling pairs - vague API requests
"""

pairs = [
    {
        "instruction": r'''Build an API for our application.''',
        "output": r'''<think>
"Build an API" -- an API for what? What resources/entities does it need to expose? What operations? Who are the consumers -- a frontend app, mobile app, third-party developers? What's the tech stack preference? REST, GraphQL, gRPC? What are the data models? This is essentially asking me to build the entire backend without telling me what the product does. I need way more context.
</think>

Building an API requires understanding what it does. A few questions:

1. **What does the application do?** What are the core entities? (e.g., users, products, orders, messages)
2. **Who consumes the API?** Your own frontend, a mobile app, third-party developers, or all three?
3. **Tech stack preference?** Language and framework? (Python/FastAPI, Node/Express, Go, etc.)
4. **Do you have a database schema already?** That usually defines the API shape.

Here's a well-structured API starter assuming a Python/FastAPI backend with common patterns -- adapt the resources to your domain:

```python
# main.py -- API entry point
from fastapi import FastAPI
from app.routes import users, products, orders
from app.middleware import error_handler

app = FastAPI(
    title="Your App API",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI at /docs
)

app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(products.router, prefix="/api/v1/products", tags=["Products"])
app.include_router(orders.router, prefix="/api/v1/orders", tags=["Orders"])

app.add_exception_handler(Exception, error_handler)


# app/schemas.py -- request/response models
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    name: str

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    created_at: datetime

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    per_page: int
    pages: int


# app/routes/users.py -- resource endpoints following REST conventions
from fastapi import APIRouter, HTTPException, Depends, Query

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """List all users with pagination."""
    total = await db.count(User)
    users = await db.query(User).offset((page - 1) * per_page).limit(per_page).all()
    return PaginatedResponse(
        items=[UserResponse.from_orm(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db=Depends(get_db)):
    """Get a single user by ID."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(data: UserCreate, db=Depends(get_db)):
    """Create a new user."""
    user = User(**data.dict())
    db.add(user)
    await db.commit()
    return user

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, data: UserCreate, db=Depends(get_db)):
    """Update an existing user."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for key, value in data.dict().items():
        setattr(user, key, value)
    await db.commit()
    return user

@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db=Depends(get_db)):
    """Delete a user."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
```

This gives you versioned endpoints, input validation, pagination, proper HTTP status codes, and auto-generated docs. Tell me what your application does and I'll define the actual resources and endpoints.'''
    },
    {
        "instruction": r'''The API needs versioning. Add it.''',
        "output": r'''<think>
"API needs versioning" -- there are several approaches: URL path versioning (/api/v1/...), header versioning (Accept: application/vnd.myapp.v1+json), query parameter versioning (?version=1), or content negotiation. Each has trade-offs. I don't know the framework, whether they have existing consumers to maintain backward compatibility with, or how often the API changes. URL versioning is most common and easiest -- I should recommend that but ask about their constraints.
</think>

A few things to clarify about your versioning needs:

1. **Why do you need versioning?** Breaking changes coming, or proactive future-proofing?
2. **How many consumers?** Internal frontend only, or external developers who can't update immediately?
3. **What framework?** The implementation varies.

There are three common approaches. Here's each with trade-offs:

```python
# APPROACH 1: URL path versioning (most common, recommended for most APIs)
# /api/v1/users, /api/v2/users
# Pros: simple, visible, easy to route, easy to deprecate
# Cons: duplicates route definitions

from fastapi import FastAPI, APIRouter

app = FastAPI()

# v1 routes
v1 = APIRouter(prefix="/api/v1")

@v1.get("/users/{user_id}")
async def get_user_v1(user_id: int):
    user = await fetch_user(user_id)
    return {
        "id": user.id,
        "name": user.name,
        # v1 returns email as a flat field
        "email": user.email,
    }

# v2 routes (breaking change: email is now nested in a contact object)
v2 = APIRouter(prefix="/api/v2")

@v2.get("/users/{user_id}")
async def get_user_v2(user_id: int):
    user = await fetch_user(user_id)
    return {
        "id": user.id,
        "name": user.name,
        # v2 breaking change: contact is an object
        "contact": {
            "email": user.email,
            "phone": user.phone,
        },
    }

app.include_router(v1)
app.include_router(v2)


# APPROACH 2: Header-based versioning
# Same URL, version in Accept header: Accept: application/vnd.myapp.v2+json
# Pros: clean URLs, proper HTTP semantics
# Cons: harder to test (can't just change the URL), less discoverable

from fastapi import Header, HTTPException

@app.get("/api/users/{user_id}")
async def get_user(user_id: int, accept: str = Header("application/vnd.myapp.v1+json")):
    user = await fetch_user(user_id)
    if "v2" in accept:
        return {"id": user.id, "contact": {"email": user.email}}
    return {"id": user.id, "email": user.email}


# APPROACH 3: Shared logic with version-specific serializers (avoids duplication)
# Best when versions differ only in response shape, not business logic

class UserSerializerV1:
    @staticmethod
    def serialize(user):
        return {"id": user.id, "name": user.name, "email": user.email}

class UserSerializerV2:
    @staticmethod
    def serialize(user):
        return {"id": user.id, "name": user.name, "contact": {"email": user.email, "phone": user.phone}}

SERIALIZERS = {"v1": UserSerializerV1, "v2": UserSerializerV2}

@app.get("/api/{version}/users/{user_id}")
async def get_user(version: str, user_id: int):
    if version not in SERIALIZERS:
        raise HTTPException(404, f"API version '{version}' not found")
    user = await fetch_user(user_id)
    return SERIALIZERS[version].serialize(user)
```

My recommendation: start with URL path versioning (Approach 1) -- it's the most widely used, easiest to understand, and simplest to maintain. Only introduce a new version when you have a breaking change, not for every update. Tell me your framework and I'll set it up properly.'''
    },
    {
        "instruction": r'''Handle errors better in our API. Right now it just returns 500.''',
        "output": r'''<think>
"Handle errors better" -- so they're getting generic 500 errors instead of meaningful error responses. This could be due to unhandled exceptions, no error middleware, or catch-all exception handlers that swallow details. I should ask what framework they're using, but the general approach is the same: structured error responses with appropriate HTTP status codes and consistent format.
</think>

A quick question: What framework are you using? (FastAPI, Flask, Express, Django?)

Regardless, here's the pattern for good API error handling. The goal is: every error returns a consistent JSON structure with an appropriate HTTP status code:

```python
# Assuming FastAPI -- adapt for your framework

# Step 1: Define custom exception classes for your domain
class AppError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, status_code: int = 400, error_code: str = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        super().__init__(message)

class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id):
        super().__init__(
            message=f"{resource} with id '{resource_id}' not found",
            status_code=404,
        )

class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)

class AuthorizationError(AppError):
    def __init__(self, message: str = "You do not have permission to perform this action"):
        super().__init__(message=message, status_code=403)


# Step 2: Register global error handlers
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
import traceback

logger = logging.getLogger(__name__)
app = FastAPI()

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    """Handle known application errors with proper status codes."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
        },
    )

@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Catch-all for unexpected errors. Log details, return generic message."""
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method, request.url.path, str(exc), traceback.format_exc()
    )
    # Don't expose internal details to the client
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred. Please try again later.",
        },
    )


# Step 3: Use meaningful exceptions in your route handlers
@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User", user_id)  # -> 404 with clear message
    return user

@app.post("/api/orders")
async def create_order(data: dict):
    if not data.get("items"):
        raise ValidationError("Order must contain at least one item")  # -> 422
    # ...
```

```text
Consistent error response format:
{
    "error": "NotFoundError",      // machine-readable error code
    "message": "User with id '42' not found"  // human-readable message
}

HTTP status code mapping:
400 - Bad request (malformed input)
401 - Unauthorized (not logged in)
403 - Forbidden (logged in but not allowed)
404 - Not found
409 - Conflict (duplicate, version mismatch)
422 - Validation error (input is well-formed but invalid)
429 - Rate limited
500 - Internal server error (unexpected, always log these)
```

This pattern ensures clients always get structured, actionable error responses instead of raw 500s. Share your framework and I'll adapt the code.'''
    },
    {
        "instruction": r'''Add pagination to the API.''',
        "output": r'''<think>
"Add pagination" -- offset-based or cursor-based? What endpoints need it? What's the default page size? Do they need sorting options? What framework and ORM are they using? Offset pagination is simpler but has performance issues on large datasets. Cursor pagination is better at scale but more complex. I should ask about the scale and provide both options.
</think>

A couple things to decide:

1. **Which endpoints?** All list endpoints, or specific ones?
2. **How much data?** Under 100k records, offset pagination is fine. Over 1M records, cursor-based is better for performance.
3. **Do you need sorting?** If users can sort by different fields, pagination needs to account for that.

Here are both approaches -- pick the one that fits your scale:

```python
# === OPTION A: Offset pagination (simple, good for < 100k records) ===
from fastapi import Query
from pydantic import BaseModel
from typing import Generic, TypeVar, List
from math import ceil

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int

    @classmethod
    def create(cls, items, total, page, per_page):
        return cls(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=ceil(total / per_page) if per_page > 0 else 0,
        )

@app.get("/api/products")
async def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    db=Depends(get_db),
):
    # Count total
    total = await db.scalar(select(func.count(Product.id)))

    # Fetch page
    sort_column = getattr(Product, sort_by, Product.created_at)
    sort_dir = sort_column.asc() if order == "asc" else sort_column.desc()

    products = await db.scalars(
        select(Product)
        .order_by(sort_dir)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    return Page.create(
        items=[p.to_dict() for p in products],
        total=total,
        page=page,
        per_page=per_page,
    )

# Response: GET /api/products?page=2&per_page=10
# {
#     "items": [...],
#     "total": 247,
#     "page": 2,
#     "per_page": 10,
#     "pages": 25
# }


# === OPTION B: Cursor pagination (better for large datasets) ===
# Uses an opaque cursor instead of page numbers
# No COUNT query needed (which is slow on large tables)

import base64

@app.get("/api/events")
async def list_events(
    cursor: str = Query(None, description="Pagination cursor from previous response"),
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    query = select(Event).order_by(Event.id.desc()).limit(limit + 1)

    if cursor:
        # Decode cursor to get the last seen ID
        last_id = int(base64.b64decode(cursor).decode())
        query = query.where(Event.id < last_id)

    results = list(await db.scalars(query))

    # If we got limit+1 results, there are more pages
    has_next = len(results) > limit
    if has_next:
        results = results[:limit]

    next_cursor = None
    if has_next and results:
        next_cursor = base64.b64encode(str(results[-1].id).encode()).decode()

    return {
        "items": [e.to_dict() for e in results],
        "next_cursor": next_cursor,
        "has_next": has_next,
    }

# Response: GET /api/events?limit=20
# {
#     "items": [...],
#     "next_cursor": "MTIzNA==",
#     "has_next": true
# }
# Next page: GET /api/events?limit=20&cursor=MTIzNA==
```

Use Option A for admin panels, dashboards, and smaller datasets where users need "go to page 5." Use Option B for feeds, timelines, and large datasets where users just scroll forward. Tell me which endpoints need pagination and I'll implement it.'''
    },
    {
        "instruction": r'''Make the API faster.''',
        "output": r'''<think>
"Make the API faster" -- which endpoints? All of them? What are the current response times? What's the bottleneck -- database queries, external service calls, computation, serialization, network? What framework and database? Without knowing which endpoints are slow and why, I can only give generic optimization advice. Same problem as "my app is slow" but specifically about the API layer.
</think>

To optimize effectively, I need to understand:

1. **Which endpoints are slow?** Specific routes and their current response times?
2. **What's the bottleneck?** Database queries, external API calls, computation, or large payloads?
3. **What's the stack?** Framework, database, caching layer?

Here's a top-to-bottom optimization approach for APIs, ordered by typical impact:

```python
# Step 0: Measure first -- add timing middleware
import time
from fastapi import Request

@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Response-Time"] = f"{elapsed_ms:.0f}ms"
    if elapsed_ms > 200:
        print(f"SLOW: {request.method} {request.url.path} -- {elapsed_ms:.0f}ms")
    return response


# Optimization 1: Database query optimization (usually the biggest win)

# BAD: N+1 queries
@app.get("/api/orders")
async def list_orders():
    orders = await db.scalars(select(Order).limit(50))
    result = []
    for order in orders:
        customer = await db.get(Customer, order.customer_id)  # N extra queries!
        result.append({**order.to_dict(), "customer_name": customer.name})
    return result

# GOOD: Single query with join
@app.get("/api/orders")
async def list_orders():
    orders = await db.scalars(
        select(Order).options(joinedload(Order.customer)).limit(50)
    )
    return [
        {**o.to_dict(), "customer_name": o.customer.name}
        for o in orders
    ]


# Optimization 2: Response caching for read-heavy endpoints
import hashlib
from fastapi.responses import JSONResponse

CACHE = {}  # Use Redis in production

def cached(ttl_seconds=60):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{hashlib.md5(str(kwargs).encode()).hexdigest()}"
            cached_value = CACHE.get(cache_key)
            if cached_value and time.time() < cached_value["expires"]:
                return cached_value["data"]
            result = await func(*args, **kwargs)
            CACHE[cache_key] = {"data": result, "expires": time.time() + ttl_seconds}
            return result
        return wrapper
    return decorator

@app.get("/api/categories")
@cached(ttl_seconds=300)
async def list_categories():
    return await db.scalars(select(Category).order_by(Category.name))


# Optimization 3: Return only what the client needs
# BAD: return entire objects with all fields
# GOOD: use response_model to limit fields

class OrderSummary(BaseModel):
    id: int
    status: str
    total: float
    created_at: datetime

@app.get("/api/orders", response_model=list[OrderSummary])
async def list_orders():
    # Only SELECT the columns you need
    return await db.scalars(
        select(Order.id, Order.status, Order.total, Order.created_at).limit(50)
    )


# Optimization 4: Compress responses
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # compress responses > 1KB
```

```text
API speed checklist (in order of typical impact):
1. Fix N+1 database queries (often 10-100x improvement)
2. Add database indexes for filtered/sorted queries
3. Cache expensive, rarely-changing responses
4. Return only needed fields (not SELECT *)
5. Add pagination (don't return 10k rows)
6. Enable gzip compression
7. Use async I/O for external service calls
8. Add connection pooling
```

Run the timing middleware for a day, then share the slowest endpoints and I'll optimize them specifically.'''
    },
]
