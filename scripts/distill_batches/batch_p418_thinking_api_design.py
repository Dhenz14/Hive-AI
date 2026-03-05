"""Thinking-trace pairs: REST API design decisions and error handling."""

PAIRS = [
    (
        "thinking/api-pagination-design",
        "We need to add pagination to our API that returns a list of products. The table has 2 million rows. Users might filter by category, price range, or search query. What pagination strategy should we use?",
        r'''<think>
There are three main pagination strategies. Let me evaluate each against the constraints.

**The constraints:**
- 2M rows
- Filterable by category, price range, search query
- Need to support client-side paging (page forward/back, possibly jump to page N)

**Strategy 1: Offset/Limit (traditional)**
```
GET /products?page=1&per_page=20
→ SELECT * FROM products LIMIT 20 OFFSET 0

GET /products?page=100&per_page=20
→ SELECT * FROM products LIMIT 20 OFFSET 1980
```

Pros:
- Simple to implement and understand
- Client can jump to any page directly
- Total count is easy: `SELECT COUNT(*)`

Cons:
- **OFFSET is slow for large values.** `OFFSET 1,000,000` means the DB reads and discards 1M rows before returning 20. On 2M rows, page 100,000 takes seconds.
- **Inconsistent results on concurrent writes.** If a row is inserted before the current offset while paginating, the next page will duplicate a row. If a row is deleted, a row is skipped.

Performance: O(offset + limit). Page 1 is fast, page 100,000 is slow.

**Strategy 2: Cursor-based (keyset pagination)**
```
GET /products?limit=20
→ Returns items + next_cursor = "eyJpZCI6MjB9" (base64 encoded {id: 20})

GET /products?limit=20&after=eyJpZCI6MjB9
→ SELECT * FROM products WHERE id > 20 ORDER BY id LIMIT 20
```

Pros:
- **Constant performance.** `WHERE id > 20 LIMIT 20` is always fast regardless of how deep you've paginated. Index scan, no discarded rows.
- **Consistent results.** New inserts don't shift pages. No duplicates or skips.
- Scales perfectly to billions of rows.

Cons:
- **Can't jump to arbitrary pages.** No "page 50 of 200". Only next/previous.
- **Complex with multi-column sorting.** If sorting by price then ID:
  ```sql
  WHERE (price > :last_price) OR (price = :last_price AND id > :last_id)
  ```
  This gets hairy with 3+ sort columns.
- No total count (expensive on 2M rows anyway).

**Strategy 3: Cursor + total count with estimate**
Combine cursor pagination with an approximate total:
```sql
-- Fast approximate count (milliseconds on 2M rows)
SELECT reltuples AS estimate FROM pg_class WHERE relname = 'products';
```
This gives a "~2,034,000 products" estimate without scanning the table.

**Considering the specific requirements:**

The user wants filtering by category, price, and search. This means:
1. The cursor must encode the current sort position, not just the ID
2. Filters change the result set — cursor must be stable within a filter context
3. Search (full-text) might change relevance scores between requests

For a product catalog:
- **Category filter:** `WHERE category_id = 5 AND id > cursor ORDER BY id LIMIT 20` — works great with cursor
- **Price range:** `WHERE price BETWEEN 10 AND 50 AND id > cursor ORDER BY id LIMIT 20` — works
- **Price sort:** `WHERE (price > :last_price OR (price = :last_price AND id > :last_id)) ORDER BY price, id LIMIT 20` — works but cursor encodes two values
- **Search query:** full-text search results are scored. Cursor on score is unstable (scores change). Offset is actually better here, or use search engine pagination (Elasticsearch's `search_after`).

**My recommendation:**
- Cursor-based for the default listing and category/price filters
- Offset-based as fallback for search queries (search results are typically <1000 anyway)
- Approximate total count from `pg_class` statistics

Let me design the response format.
</think>

### Recommendation: Cursor-based pagination with offset fallback for search

Offset pagination breaks at scale (page 100,000 scans 2M rows). Cursor pagination is O(1) regardless of depth.

### Response format

```json
{
  "data": [
    {"id": 21, "name": "Widget", "price": 9.99, "category": "tools"},
    {"id": 22, "name": "Gadget", "price": 14.99, "category": "electronics"}
  ],
  "pagination": {
    "next_cursor": "eyJpZCI6NDAsInByaWNlIjo5Ljk5fQ==",
    "prev_cursor": "eyJpZCI6MjEsInByaWNlIjo5Ljk5fQ==",
    "has_next": true,
    "has_prev": true,
    "total_estimate": 2034000
  }
}
```

### Implementation

```python
import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

@dataclass
class CursorPage:
    items: list
    next_cursor: Optional[str]
    prev_cursor: Optional[str]
    has_next: bool
    has_prev: bool
    total_estimate: int

def encode_cursor(values: dict) -> str:
    """Encode cursor values to opaque string."""
    return base64.urlsafe_b64encode(json.dumps(values).encode()).decode()

def decode_cursor(cursor: str) -> dict:
    """Decode cursor string to values."""
    return json.loads(base64.urlsafe_b64decode(cursor))


async def list_products(
    db,
    limit: int = 20,
    after: str = None,
    before: str = None,
    sort_by: str = 'id',
    category: str = None,
    min_price: float = None,
    max_price: float = None,
) -> CursorPage:
    """Cursor-paginated product listing."""

    # Validate sort column (whitelist to prevent injection)
    allowed_sorts = {'id', 'price', 'name', 'created_at'}
    if sort_by not in allowed_sorts:
        sort_by = 'id'

    # Build WHERE clauses
    conditions = []
    params = {}

    if category:
        conditions.append("category = :category")
        params['category'] = category
    if min_price is not None:
        conditions.append("price >= :min_price")
        params['min_price'] = min_price
    if max_price is not None:
        conditions.append("price <= :max_price")
        params['max_price'] = max_price

    # Cursor condition (keyset pagination)
    if after:
        cursor = decode_cursor(after)
        if sort_by == 'id':
            conditions.append("id > :cursor_id")
            params['cursor_id'] = cursor['id']
        else:
            # Multi-column cursor: (sort_col, id) for deterministic ordering
            conditions.append(
                f"({sort_by} > :cursor_val OR "
                f"({sort_by} = :cursor_val AND id > :cursor_id))"
            )
            params['cursor_val'] = cursor[sort_by]
            params['cursor_id'] = cursor['id']

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Fetch limit+1 to check if there's a next page
    query = f"""
        SELECT * FROM products
        {where}
        ORDER BY {sort_by}, id
        LIMIT :limit
    """
    params['limit'] = limit + 1

    rows = await db.fetch_all(query, params)
    has_next = len(rows) > limit
    items = rows[:limit]

    # Build cursors
    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = encode_cursor({'id': last['id'], sort_by: last[sort_by]})

    prev_cursor = None
    if after and items:
        first = items[0]
        prev_cursor = encode_cursor({'id': first['id'], sort_by: first[sort_by]})

    # Approximate total (fast, no full scan)
    total = await db.fetch_val(
        "SELECT reltuples::int FROM pg_class WHERE relname = 'products'"
    )

    return CursorPage(
        items=items,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        has_next=has_next,
        has_prev=after is not None,
        total_estimate=total,
    )
```

### API endpoints

```python
@app.get('/api/products')
async def get_products(
    limit: int = Query(20, ge=1, le=100),
    after: str = Query(None),
    sort: str = Query('id'),
    category: str = Query(None),
    min_price: float = Query(None),
    max_price: float = Query(None),
):
    page = await list_products(
        db, limit=limit, after=after, sort_by=sort,
        category=category, min_price=min_price, max_price=max_price,
    )
    return {
        'data': page.items,
        'pagination': {
            'next_cursor': page.next_cursor,
            'prev_cursor': page.prev_cursor,
            'has_next': page.has_next,
            'has_prev': page.has_prev,
            'total_estimate': page.total_estimate,
        }
    }
```

### Performance comparison at 2M rows

```
Offset page 1:        0.5ms   (OFFSET 0)
Offset page 1000:     120ms   (OFFSET 20,000)
Offset page 50,000:   2,800ms (OFFSET 1,000,000)
Offset page 100,000:  5,200ms (OFFSET 2,000,000)

Cursor any page:       0.5ms  (always index scan, no discarded rows)
```'''
    ),
    (
        "thinking/api-error-handling",
        "How should I structure error responses in my REST API? Right now we just return `{'error': 'something went wrong'}` with status 500.",
        r'''<think>
Good error responses serve three audiences:
1. Frontend developers who need to show appropriate UI
2. API consumers who need to handle errors programmatically
3. Backend developers debugging issues

The current response fails all three:
- Frontend can't tell a validation error from a server crash
- API consumers can't parse a free-text string reliably
- No details for debugging

**What a good error response needs:**

1. **HTTP status code** — the right one, not always 500
2. **Error type/code** — machine-readable string for programmatic handling
3. **Human message** — for display or debugging
4. **Field-specific errors** — for validation (which field, what's wrong)
5. **Request ID** — for correlating with server logs
6. **NO stack traces in production** — security risk (leaks internal paths, versions)

**Standard formats:**

RFC 7807 (Problem Details for HTTP APIs):
```json
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation Error",
  "status": 422,
  "detail": "The request body contains invalid fields",
  "instance": "/orders/12345"
}
```

This is a good standard but I find the `type` URI often goes to a 404. And `instance` is rarely useful. Let me design something practical.

**My approach: structured errors with error codes**

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid request parameters",
    "details": [
      {"field": "email", "code": "invalid_format", "message": "Must be a valid email"},
      {"field": "age", "code": "out_of_range", "message": "Must be between 0 and 150"}
    ]
  },
  "request_id": "req_abc123"
}
```

The `code` field is the key. Frontend can switch on it:
```javascript
if (error.code === 'validation_error') showFieldErrors(error.details);
else if (error.code === 'not_found') showNotFound();
else showGenericError(error.message);
```

**HTTP status code mapping:**

- 400 Bad Request: malformed JSON, missing required fields
- 401 Unauthorized: no auth token, expired token
- 403 Forbidden: valid auth but insufficient permissions
- 404 Not Found: resource doesn't exist
- 409 Conflict: duplicate entry, version conflict
- 422 Unprocessable Entity: valid JSON but business rule violation
- 429 Too Many Requests: rate limited
- 500 Internal Server Error: unexpected server error (never expose details)
- 503 Service Unavailable: DB down, dependency down

**Common mistake: using 200 for errors.**
Some APIs return `{"status": 200, "error": "not found"}`. This breaks HTTP clients, caches, and monitoring tools that rely on status codes.

**Common mistake: inconsistent format.**
Some endpoints return `{"error": "msg"}`, others return `{"message": "msg"}`, others return `{"errors": ["msg"]}`. Pick one format and use it everywhere.
</think>

### Error response format

Every error should follow the same structure. This lets clients handle errors with one code path.

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid request parameters",
    "details": [
      {"field": "email", "code": "invalid_format", "message": "Must be a valid email address"},
      {"field": "age", "code": "out_of_range", "message": "Must be between 0 and 150"}
    ]
  },
  "request_id": "req_7f2a9bc3"
}
```

- `code`: Machine-readable, stable across versions. Clients switch on this.
- `message`: Human-readable, can change. Display to users or log for debugging.
- `details`: Optional, for validation errors. Lists per-field issues.
- `request_id`: Correlates with server logs.

### Implementation

```python
from dataclasses import dataclass, field
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uuid

app = FastAPI()

# --- Error types ---

@dataclass
class FieldError:
    field: str
    code: str
    message: str

@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: list[FieldError] = field(default_factory=list)

class NotFoundError(AppError):
    def __init__(self, resource: str, id: str):
        super().__init__(
            code='not_found',
            message=f'{resource} {id} not found',
            status_code=404,
        )

class ValidationError(AppError):
    def __init__(self, fields: list[FieldError]):
        super().__init__(
            code='validation_error',
            message='Invalid request parameters',
            status_code=422,
            details=fields,
        )

class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(code='conflict', message=message, status_code=409)

class ForbiddenError(AppError):
    def __init__(self, message: str = 'Insufficient permissions'):
        super().__init__(code='forbidden', message=message, status_code=403)

class RateLimitError(AppError):
    def __init__(self, retry_after: int):
        super().__init__(
            code='rate_limited',
            message=f'Too many requests. Retry after {retry_after} seconds',
            status_code=429,
        )
        self.retry_after = retry_after


# --- Request ID middleware ---

@app.middleware('http')
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get('X-Request-ID', f'req_{uuid.uuid4().hex[:12]}')
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers['X-Request-ID'] = request_id
    return response


# --- Global error handler ---

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    body = {
        'error': {
            'code': exc.code,
            'message': exc.message,
        },
        'request_id': getattr(request.state, 'request_id', None),
    }
    if exc.details:
        body['error']['details'] = [
            {'field': d.field, 'code': d.code, 'message': d.message}
            for d in exc.details
        ]

    headers = {}
    if isinstance(exc, RateLimitError):
        headers['Retry-After'] = str(exc.retry_after)

    return JSONResponse(body, status_code=exc.status_code, headers=headers)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Catch-all: never expose internal details to clients."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.exception(f"Unhandled error [request_id={request_id}]")

    return JSONResponse(
        {
            'error': {
                'code': 'internal_error',
                'message': 'An unexpected error occurred',
            },
            'request_id': request_id,
        },
        status_code=500,
    )


# --- Usage in endpoints ---

@app.post('/api/orders')
async def create_order(request: Request):
    data = await request.json()

    # Validation
    errors = []
    if not data.get('product_id'):
        errors.append(FieldError('product_id', 'required', 'Product ID is required'))
    if data.get('quantity', 0) < 1:
        errors.append(FieldError('quantity', 'out_of_range', 'Must be at least 1'))
    if errors:
        raise ValidationError(errors)

    # Business logic
    product = await db.get_product(data['product_id'])
    if not product:
        raise NotFoundError('Product', data['product_id'])
    if product.stock < data['quantity']:
        raise ConflictError(f'Only {product.stock} items in stock')

    order = await db.create_order(data)
    return {'data': order}
```

### HTTP status code cheat sheet

| Code | When to use | Error code |
|------|------------|------------|
| 400 | Malformed JSON, wrong content type | `bad_request` |
| 401 | No token, expired token | `unauthorized` |
| 403 | Valid token, wrong permissions | `forbidden` |
| 404 | Resource doesn't exist | `not_found` |
| 409 | Duplicate, version conflict | `conflict` |
| 422 | Valid JSON, business rule violation | `validation_error` |
| 429 | Rate limited | `rate_limited` |
| 500 | Bug in your code | `internal_error` |
| 503 | Dependency down | `service_unavailable` |

### Client-side handling

```javascript
async function apiCall(url, options) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const body = await resp.json();
    const err = body.error;

    switch (err.code) {
      case 'validation_error':
        // Show field-specific errors in the form
        err.details.forEach(d => showFieldError(d.field, d.message));
        break;
      case 'not_found':
        router.push('/404');
        break;
      case 'unauthorized':
        router.push('/login');
        break;
      case 'rate_limited':
        const retry = resp.headers.get('Retry-After');
        showToast(`Too many requests. Try again in ${retry}s`);
        break;
      default:
        showToast(err.message);
    }
    throw err;
  }
  return resp.json();
}
```'''
    ),
    (
        "thinking/api-versioning",
        "Our API has been running for 2 years with no versioning. Now we need to make breaking changes (renaming fields, changing response structures). We have about 200 active API consumers. How do we handle this?",
        r'''<think>
This is a real-world problem that many teams face. Let me think through the options.

**Current state:**
- Unversioned API running for 2 years
- 200 active consumers (significant — can't just break them)
- Need breaking changes (field renames, structure changes)

**Versioning strategies:**

**1. URL path versioning: `/v1/products`, `/v2/products`**
Pros:
- Extremely clear which version is being used
- Easy to route at the load balancer/reverse proxy level
- Easy to deprecate (just shut down `/v1/` after migration period)

Cons:
- Resource URLs change (breaks bookmarks, webhooks)
- Clients need to update all URLs
- Tempting to let old versions rot (both still need maintenance)

**2. Header versioning: `Accept: application/vnd.myapi.v2+json`**
Pros:
- URLs stay the same (clean REST)
- Version is metadata about the representation, not the resource

Cons:
- Invisible — harder to debug, test, share
- Can't test in a browser (can't set headers)
- Load balancer routing is harder

**3. Query parameter: `/products?version=2`**
Pros:
- Simple to implement and test
- URLs are mostly stable

Cons:
- Pollutes the query string
- Easy to forget, leading to unversioned calls

**4. Per-field versioning / gradual migration**
Instead of versioning the whole API, deprecate individual fields:
```json
{
  "name": "Widget",
  "product_name": "Widget",   // New field (same value during migration)
  "price": 9.99,              // Unchanged
  "category_id": 5,           // New field
  "category": 5               // Deprecated (was ambiguous: ID or name?)
}
```

Return both old and new fields simultaneously. Consumers migrate field by field. After 6 months, remove deprecated fields.

**For this situation (200 consumers, no existing versioning):**

I'd recommend: **URL path versioning + Strangler Fig migration pattern**.

Here's my reasoning:
1. The API has NO versioning at all — we need to introduce it with minimal disruption
2. 200 consumers means a long migration period (months)
3. We need both versions to run simultaneously
4. URL path is the most visible/debuggable approach

**Migration plan:**

Phase 1: Version the existing API
- Current unversioned API at `/products` becomes `/v1/products`
- Keep `/products` as an alias for `/v1/products` (don't break existing consumers)
- Communicate to all 200 consumers: "pin to `/v1/` to avoid surprises"

Phase 2: Build v2 alongside v1
- New endpoints at `/v2/products` with breaking changes
- v1 and v2 share the same database and business logic
- Only the API layer (serialization, field names) differs

Phase 3: Migrate consumers
- Document all breaking changes
- Provide migration guide with before/after examples
- Set a sunset date for v1 (e.g., 6 months from v2 launch)
- Add `Sunset` and `Deprecation` headers to v1 responses

Phase 4: Decommission v1
- After sunset date, v1 returns 410 Gone
- Remove v1 code

**Key architecture decision: how to share code between v1 and v2?**

Bad: copy-paste the entire codebase
Good: shared service layer with versioned serializers

```
v1 routes → v1 serializer → shared service → DB
v2 routes → v2 serializer → shared service → DB
```

The service layer returns internal objects. The serializer converts to the API response format. Only the serializer is version-specific.
</think>

### Strategy: URL path versioning + Strangler Fig migration

With 200 active consumers and no existing versioning, you need a gradual, visible, and reversible approach.

### 4-phase migration plan

```
Phase 1 (Week 1-2):     Version the existing API
Phase 2 (Week 3-6):     Build v2 alongside v1
Phase 3 (Month 2-6):    Migrate consumers
Phase 4 (Month 7):      Decommission v1
```

### Architecture: shared services, versioned serializers

```
     ┌─ /v1/products → v1_serializer ─┐
     │                                  ├→ ProductService → DB
     └─ /v2/products → v2_serializer ─┘
```

```python
# --- Shared service (version-agnostic) ---

class ProductService:
    """Business logic — no API format concerns."""
    async def get_product(self, product_id: int) -> Product:
        return await self.db.get_product(product_id)

    async def list_products(self, filters) -> list[Product]:
        return await self.db.query_products(filters)


# --- Version-specific serializers ---

class ProductV1Serializer:
    """v1 format: flat structure, 'category' is the ID (legacy confusion)."""
    def serialize(self, product: Product) -> dict:
        return {
            'id': product.id,
            'name': product.name,
            'category': product.category_id,     # Ambiguous: ID, not name
            'price': float(product.price),        # Float, not string
            'in_stock': product.stock > 0,        # Boolean
        }

class ProductV2Serializer:
    """v2 format: nested structure, clear naming, string decimals."""
    def serialize(self, product: Product) -> dict:
        return {
            'id': product.id,
            'name': product.name,
            'category': {                         # Nested object (clear)
                'id': product.category_id,
                'name': product.category_name,
            },
            'price': {                            # String decimal (precise)
                'amount': str(product.price),
                'currency': product.currency,
            },
            'inventory': {                        # Richer info
                'in_stock': product.stock > 0,
                'quantity': product.stock,
            },
        }


# --- Versioned routes ---

v1 = APIRouter(prefix='/v1')
v2 = APIRouter(prefix='/v2')
service = ProductService()

@v1.get('/products/{product_id}')
async def get_product_v1(product_id: int):
    product = await service.get_product(product_id)
    if not product:
        raise NotFoundError('Product', product_id)
    return ProductV1Serializer().serialize(product)

@v2.get('/products/{product_id}')
async def get_product_v2(product_id: int):
    product = await service.get_product(product_id)
    if not product:
        raise NotFoundError('Product', product_id)
    return ProductV2Serializer().serialize(product)


# --- Backward compatibility: unversioned → v1 ---

@app.get('/products/{product_id}')
async def get_product_unversioned(product_id: int):
    """Legacy route — alias to v1."""
    return await get_product_v1(product_id)

app.include_router(v1)
app.include_router(v2)
```

### Deprecation headers on v1 responses

```python
@v1.middleware('http')
async def add_deprecation_headers(request, call_next):
    response = await call_next(request)
    response.headers['Deprecation'] = 'true'
    response.headers['Sunset'] = 'Sat, 05 Sep 2026 00:00:00 GMT'
    response.headers['Link'] = '</v2/docs>; rel="successor-version"'
    return response
```

### Migration guide for consumers

```markdown
## Breaking Changes in v2

| v1 field | v2 field | Change |
|----------|----------|--------|
| `category` (int) | `category.id` (int) | Nested under object |
| — | `category.name` (string) | New field |
| `price` (float) | `price.amount` (string) | String for precision |
| — | `price.currency` (string) | New field |
| `in_stock` (bool) | `inventory.in_stock` (bool) | Moved to inventory object |
| — | `inventory.quantity` (int) | New field |

## Migration steps
1. Update your base URL from `/products` to `/v1/products` (no behavior change)
2. Update to `/v2/products` and adjust your parsing
3. v1 will return 410 Gone after September 5, 2026
```

### Monitoring the migration

```python
# Track v1 vs v2 usage to know when it's safe to decommission
@app.middleware('http')
async def track_version_usage(request, call_next):
    response = await call_next(request)
    version = 'v2' if request.url.path.startswith('/v2') else 'v1'
    metrics.increment(f'api.requests.{version}', tags={
        'consumer': request.headers.get('X-API-Key', 'unknown'),
        'endpoint': request.url.path,
    })
    return response
```

When v1 traffic hits zero (or only inactive consumers remain), decommission.'''
    ),
]
