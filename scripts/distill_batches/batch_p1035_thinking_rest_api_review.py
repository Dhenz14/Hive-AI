r"""Thinking-trace pairs: REST API design code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this REST API design and identify issues:

```python
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

app = FastAPI()

class Product(BaseModel):
    id: int
    name: str
    price: float
    category: str
    created: datetime

@app.get("/getProducts")
def get_products(
    category: str = None,
    minPrice: float = None,
    maxPrice: float = None,
    sortBy: str = "name",
    sortOrder: str = "asc",
    pageNum: int = 1,
    pageSize: int = 100,
):
    pass

@app.get("/getProduct/{id}")
def get_product(id: int):
    pass

@app.post("/createProduct")
def create_product(product: Product):
    pass

@app.post("/updateProduct/{id}")
def update_product(id: int, product: Product):
    pass

@app.get("/deleteProduct/{id}")
def delete_product(id: int):
    pass

@app.get("/searchProducts")
def search_products(q: str):
    pass

@app.post("/products/bulk-create")
def bulk_create(products: List[Product]):
    pass

@app.get("/products/{id}/getReviews")
def get_reviews(id: int, page: int = 1):
    pass

@app.post("/products/{id}/addReview")
def add_review(id: int, review: dict):
    pass

@app.get("/api/v1/categories")
def get_categories():
    pass

@app.get("/products/export")
def export_products(format: str = "csv"):
    pass

@app.post("/products/import")
def import_products(file: bytes):
    pass
```''', r'''<think>
Let me review this REST API design for naming conventions, HTTP methods, pagination, error handling, and versioning.

1. Endpoint naming:
- Uses verbs in URLs: /getProducts, /createProduct, /deleteProduct, /getReviews, /addReview. REST uses nouns. The HTTP method indicates the action.
- Inconsistent casing: /getProducts (camelCase), /products/bulk-create (kebab-case), /api/v1/categories (different path structure).
- Inconsistent nesting: some endpoints start with /, others with /products/{id}/, one with /api/v1/.

2. HTTP methods:
- POST for update instead of PUT/PATCH: /updateProduct uses POST.
- GET for delete: /deleteProduct/{id} uses GET. DELETE should be a GET request NEVER. Using GET means crawlers, prefetch, and browser navigation can accidentally delete products.
- POST for /addReview instead of POST /products/{id}/reviews.

3. Pagination:
- Default pageSize=100 is too large. Typical defaults are 20-50.
- No maximum pageSize limit. Client can request pageSize=1000000.
- No total count in response for building pagination UI.
- No cursor-based pagination option for large datasets.

4. Versioning:
- Only /api/v1/categories has a version prefix. All other endpoints are unversioned. Inconsistent.

5. Response format:
- No standard response envelope. Some endpoints return items directly, others unknown.
- No standard error response format.

6. Query parameters:
- camelCase: minPrice, maxPrice, sortBy, sortOrder, pageNum, pageSize. REST convention is snake_case or lowercase.
- sortBy accepts any string with no validation.

7. Input validation:
- create_product and update_product use the full Product model including id. The client should not supply id for creation.
- add_review accepts dict with no validation.
- bulk_create has no size limit.
- export takes format as a string with no validation.

8. /searchProducts vs /getProducts:
- Search is a separate endpoint from list, but they serve similar purposes. Search should be a query parameter on the list endpoint.

Let me write the review.
</think>

## Code Review: REST API Design

### HIGH - Incorrect HTTP Methods

**HM1: GET used for deletion (Severity: CRITICAL)**
```python
@app.get("/deleteProduct/{id}")
def delete_product(id: int):
```
GET requests must be safe and idempotent. Using GET for deletion means browser prefetch, web crawlers, and link previews can accidentally delete products. Use DELETE:
```python
@app.delete("/products/{id}")
```

**HM2: POST used for update (Severity: HIGH)**
`/updateProduct` uses POST instead of PUT (full replacement) or PATCH (partial update). Correct:
```python
@app.put("/products/{id}")    # full update
@app.patch("/products/{id}")  # partial update
```

### HIGH - Verbs in URLs

**VB1: URLs contain action verbs (Severity: HIGH)**
REST URLs should be nouns (resources), with HTTP methods as verbs:

| Current | Correct |
|---------|---------|
| GET /getProducts | GET /products |
| POST /createProduct | POST /products |
| GET /deleteProduct/{id} | DELETE /products/{id} |
| POST /updateProduct/{id} | PUT /products/{id} |
| GET /searchProducts | GET /products?q=... |
| POST /products/{id}/addReview | POST /products/{id}/reviews |
| GET /products/{id}/getReviews | GET /products/{id}/reviews |

### HIGH - Inconsistent Versioning

**VER1: Only one endpoint has version prefix (Severity: HIGH)**
`/api/v1/categories` is the only versioned endpoint. All others lack versioning. When breaking changes are needed, there is no migration path. All endpoints should share a version prefix: `/api/v1/products`, `/api/v1/categories`.

### MEDIUM - Pagination Issues

**PG1: Default page size too large (Severity: MEDIUM)**
`pageSize: int = 100` is excessive. Default to 20-50. Add a maximum cap:
```python
pageSize: int = Query(default=20, le=100)
```

**PG2: No total count in response (Severity: MEDIUM)**
Clients cannot build pagination UI without knowing the total number of items. Return metadata:
```json
{
  "items": [...],
  "total": 1234,
  "page": 1,
  "page_size": 20,
  "pages": 62
}
```

### MEDIUM - Input Validation

**IV1: Full Product model for creation (Severity: MEDIUM)**
`create_product(product: Product)` includes `id` and `created`, which should be server-generated. Create separate DTOs:
```python
class ProductCreate(BaseModel):
    name: str
    price: float
    category: str

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
```

**IV2: Review accepts untyped dict (Severity: MEDIUM)**
`add_review(review: dict)` has no schema validation. Define a ReviewCreate model.

### MEDIUM - Search as Separate Endpoint

**SE1: Search duplicates list functionality (Severity: MEDIUM)**
`/searchProducts` and `/getProducts` both return filtered products. Merge search into the list endpoint with a query parameter:
```python
@app.get("/products")
def list_products(q: Optional[str] = None, category: Optional[str] = None, ...):
```

### LOW - Naming Conventions

**NC1: Inconsistent parameter casing (Severity: LOW)**
`minPrice`, `maxPrice`, `sortBy`, `pageNum` use camelCase. REST convention typically uses snake_case: `min_price`, `max_price`, `sort_by`, `page`. Choose one convention and apply consistently.'''),

    ("thinking/code-review", r'''Review this REST API error handling and identify issues:

```python
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import traceback
import logging

app = FastAPI()
logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "path": str(request.url),
            "method": request.method,
        }
    )

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="not found")
    return user

@app.post("/users")
async def create_user(user: dict):
    try:
        result = db.create_user(user)
        return {"id": result.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/users/{user_id}")
async def update_user(user_id: int, data: dict):
    try:
        db.update_user(user_id, data)
        return {"status": "ok"}
    except ValueError as e:
        return {"error": str(e)}
    except KeyError:
        raise HTTPException(status_code=404)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")

@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    db.delete_user(user_id)
    return {"deleted": True}

@app.post("/orders")
async def create_order(order: dict):
    if not order.get("items"):
        return JSONResponse(status_code=400, content={"msg": "no items"})
    if not order.get("user_id"):
        raise HTTPException(400, "missing user_id")
    try:
        result = process_order(order)
    except InsufficientStockError as e:
        raise HTTPException(422, detail={"code": "STOCK", "message": str(e)})
    except PaymentError as e:
        raise HTTPException(402, detail=str(e))
    return result
```''', r'''<think>
Let me review this error handling code.

1. Global exception handler leaks internals:
- Returns traceback to the client. This exposes file paths, code structure, and potentially sensitive data (database queries, API keys in connection strings).
- Returns the full request URL which may contain sensitive query parameters.

2. Inconsistent error response formats:
- get_user: {"detail": "not found"} (HTTPException default)
- create_user: {"detail": "error message"} (HTTPException)
- update_user on ValueError: {"error": "message"} (200 status with error!)
- create_order no items: {"msg": "no items"} (JSONResponse)
- create_order stock: {"detail": {"code": "STOCK", "message": "..."}} (nested)
- create_order payment: {"detail": "message"} (string)
- Five different error response formats.

3. update_user returns 200 with error body:
- `except ValueError as e: return {"error": str(e)}` returns HTTP 200 with an error message in the body. Clients checking status codes will think the request succeeded.

4. Catching Exception broadly:
- create_user catches all exceptions and returns 400. A database connection error (500) gets reported as a bad request (400). Only catch expected exceptions.

5. delete_user has no error handling:
- If the user does not exist, db.delete_user might throw or silently do nothing. Either way, the response is {"deleted": True} even if nothing was deleted. Should check existence and return 404.

6. No standard error schema:
- Each endpoint invents its own error format. Clients cannot programmatically parse errors.

7. HTTPException without detail:
- `raise HTTPException(status_code=404)` has no detail message. The client gets {"detail": "Not Found"} (the default HTTP reason phrase), which is not helpful.

8. Status codes:
- 422 for insufficient stock is reasonable (Unprocessable Entity).
- 402 (Payment Required) for payment errors is technically correct but rarely used.

Let me write the review.
</think>

## Code Review: REST API Error Handling

### CRITICAL - Traceback Leaked to Clients

**TL1: Stack trace in error response (Severity: CRITICAL)**
```python
content={
    "error": str(exc),
    "traceback": traceback.format_exc(),
    "path": str(request.url),
}
```
The global exception handler sends the full Python traceback to the client, exposing file paths, code structure, and potentially sensitive data (database connection strings, internal IPs). Log the traceback server-side, return a generic message:
```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
    )
```

### HIGH - 200 Status with Error Body

**SE1: update_user returns success status for errors (Severity: HIGH)**
```python
except ValueError as e:
    return {"error": str(e)}  # HTTP 200!
```
This returns HTTP 200 (success) with an error message in the body. Any client checking `response.ok` or status codes treats this as success. Always use appropriate HTTP status codes for errors.

### HIGH - Inconsistent Error Format

**IF1: Five different error response shapes (Severity: HIGH)**
The API uses multiple incompatible error formats:
- `{"detail": "not found"}` (FastAPI default)
- `{"error": "message"}` (custom)
- `{"msg": "no items"}` (custom)
- `{"detail": {"code": "STOCK", "message": "..."}}` (nested)
- `{"detail": "message"}` (string)

Clients cannot parse errors reliably. Define a standard error schema:
```python
class ErrorResponse(BaseModel):
    error: ErrorDetail

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None

# Usage:
return JSONResponse(status_code=400, content={
    "error": {"code": "VALIDATION_ERROR", "message": "Items are required"}
})
```

### HIGH - Broad Exception Catching

**BC1: create_user treats all errors as 400 (Severity: HIGH)**
```python
except Exception as e:
    raise HTTPException(status_code=400, detail=str(e))
```
A database connection error, timeout, or internal server error is reported as a client error (400 Bad Request). Catch only expected exceptions:
```python
except ValidationError as e:
    raise HTTPException(status_code=400, detail=str(e))
except IntegrityError:
    raise HTTPException(status_code=409, detail="User already exists")
# Let other exceptions propagate to the global handler (500)
```

### MEDIUM - delete_user Always Returns Success

**DS1: Deletion of non-existent resource returns 200 (Severity: MEDIUM)**
```python
@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    db.delete_user(user_id)
    return {"deleted": True}
```
If the user does not exist, the response still claims deletion succeeded. Check the result:
```python
deleted = db.delete_user(user_id)
if not deleted:
    raise HTTPException(status_code=404, detail="User not found")
return Response(status_code=204)  # No Content
```

### MEDIUM - Missing Error Detail

**MD1: HTTPException without helpful message (Severity: MEDIUM)**
```python
raise HTTPException(status_code=404)
```
Returns the generic HTTP reason phrase "Not Found". Include context: `detail="User not found"`.

### LOW - No Input Validation Model

**IV1: Using dict instead of Pydantic models (Severity: LOW)**
Both create_user and create_order accept `dict` with manual validation. Use Pydantic models for automatic validation and consistent error responses.'''),

    ("thinking/code-review", r'''Review this REST API versioning and pagination design and identify issues:

```python
from fastapi import FastAPI, Query, Header, Request
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
import math

app = FastAPI()

class PaginatedResponse(BaseModel):
    items: list
    page: int
    total: int

@app.get("/api/v1/articles")
async def list_articles_v1(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=1000),
    author: Optional[str] = None,
    tag: Optional[str] = None,
    sort: str = Query("created_at"),
    order: str = Query("desc"),
):
    offset = (page - 1) * limit
    query = build_query(author=author, tag=tag, sort=sort, order=order)
    articles = db.execute(query, offset=offset, limit=limit)
    total = db.count(query)
    return PaginatedResponse(items=articles, page=page, total=total)

@app.get("/api/v2/articles")
async def list_articles_v2(
    cursor: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    author: Optional[str] = None,
    tag: Optional[str] = None,
):
    if cursor:
        articles = db.find_after(cursor, limit=limit + 1)
    else:
        articles = db.find_all(limit=limit + 1)

    has_more = len(articles) > limit
    if has_more:
        articles = articles[:limit]
        next_cursor = articles[-1]["id"]
    else:
        next_cursor = None

    return {
        "items": articles,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }

@app.get("/api/v1/articles/{id}")
async def get_article_v1(id: int):
    return db.get_article(id)

@app.get("/api/v2/articles/{id}")
async def get_article_v2(id: int, request: Request):
    article = db.get_article(id)
    accept = request.headers.get("accept", "application/json")
    if "application/xml" in accept:
        return XMLResponse(article)
    return article

def api_version(request: Request):
    version = request.headers.get("X-API-Version", "1")
    return int(version)

@app.get("/articles")
async def list_articles(request: Request):
    version = api_version(request)
    if version == 1:
        return await list_articles_v1()
    elif version == 2:
        return await list_articles_v2()
    else:
        return JSONResponse(status_code=400, content={"error": "Unsupported version"})
```''', r'''<think>
Let me review the versioning and pagination design.

1. Three different versioning strategies:
- URL path versioning: /api/v1/ and /api/v2/
- Header-based versioning: X-API-Version header
- Content negotiation: Accept header for response format
Using all three is confusing. Pick one strategy and use it consistently.

2. The /articles endpoint (header-based) calls the v1/v2 functions without passing parameters. This will fail because list_articles_v1 expects query parameters that are not forwarded.

3. Pagination inconsistency:
- v1 uses offset-based pagination (page + limit)
- v2 uses cursor-based pagination
These are fundamentally different approaches. Migrating from v1 to v2 requires clients to change their pagination logic entirely.

4. Offset pagination issues (v1):
- limit can be up to 1000. For deep pages (page=10000, limit=100), the database must scan and skip 999,900 rows. This becomes very slow.
- COUNT query runs on every request alongside the main query. For large tables, COUNT is expensive.
- PaginatedResponse uses `items: list` (untyped).
- No next/previous page links (HATEOAS).

5. Cursor pagination issues (v2):
- The cursor is just the article ID. If articles are sorted by anything other than ID, the cursor logic is wrong. The cursor needs to encode the sort criteria.
- No backward pagination (previous page).

6. sort parameter in v1:
- sort accepts any string. No validation against allowed columns. SQL injection risk if using raw queries.
- v2 does not support sorting at all.

7. Content negotiation in v2:
- get_article_v2 checks Accept header for XML support. This is content negotiation, not versioning. Mixing it with URL versioning is confusing.
- XMLResponse is used but not imported or defined.

8. The unversioned /articles endpoint:
- Duplicates functionality of versioned endpoints.
- Calling list_articles_v1() without arguments passes no query parameters (uses defaults only). The request's actual query parameters are ignored.

Let me write the review.
</think>

## Code Review: REST API Versioning and Pagination

### HIGH - Three Conflicting Versioning Strategies

**VS1: URL, header, and content negotiation mixed (Severity: HIGH)**
The API uses:
- URL path: `/api/v1/articles`, `/api/v2/articles`
- Header: `X-API-Version` on `/articles`
- Content negotiation: `Accept` header in v2 detail

Pick one strategy. URL path versioning is most common and easiest for clients:
```
/api/v1/articles
/api/v2/articles
```
Remove the unversioned `/articles` endpoint and the header-based routing.

### HIGH - Header Router Drops Query Parameters

**QP1: list_articles does not forward parameters (Severity: HIGH)**
```python
@app.get("/articles")
async def list_articles(request: Request):
    version = api_version(request)
    if version == 1:
        return await list_articles_v1()  # no args!
```
`list_articles_v1` expects `page`, `limit`, `author`, etc. from FastAPI's dependency injection. Calling it directly with no arguments uses only defaults -- the request's actual query parameters are ignored. This endpoint is broken.

### HIGH - Offset Pagination Performance

**OP1: Deep page queries are slow (Severity: HIGH)**
```python
offset = (page - 1) * limit
```
With `page=10000, limit=20`, the database scans and discards 199,980 rows to return 20. On a table with millions of rows, this takes seconds. For deep pagination, use cursor-based approach (as v2 does) or enforce a maximum page number.

**OP2: COUNT on every request (Severity: MEDIUM)**
`db.count(query)` runs a full table scan on every paginated request to get the total. For large tables, this is expensive. Cache the count or use an estimate.

### HIGH - Unvalidated Sort Parameter

**SP1: Sort accepts arbitrary strings (Severity: HIGH)**
```python
sort: str = Query("created_at")
```
If `build_query` interpolates this into SQL, it is a SQL injection vector. Even without injection, invalid column names cause database errors. Validate against an allowlist:
```python
ALLOWED_SORTS = {"created_at", "title", "author", "updated_at"}
if sort not in ALLOWED_SORTS:
    raise HTTPException(400, f"Invalid sort field. Allowed: {ALLOWED_SORTS}")
```

### MEDIUM - Cursor Does Not Encode Sort Criteria

**CR1: Cursor assumes ID ordering (Severity: MEDIUM)**
```python
next_cursor = articles[-1]["id"]
# ...
articles = db.find_after(cursor, limit=limit + 1)
```
The cursor is a raw article ID, implying `WHERE id > cursor` ordering. If articles are sorted by date or title, the cursor produces incorrect results. Encode the sort field's value in the cursor:
```python
import base64, json
next_cursor = base64.b64encode(json.dumps({
    "id": articles[-1]["id"],
    "created_at": articles[-1]["created_at"],
}).encode()).decode()
```

### MEDIUM - Untyped PaginatedResponse

**UR1: items field loses type information (Severity: MEDIUM)**
```python
class PaginatedResponse(BaseModel):
    items: list  # untyped
```
The items field accepts anything. Use a generic:
```python
from typing import Generic, TypeVar
T = TypeVar('T')
class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    page: int
    total: int
    pages: int
```

### MEDIUM - No Pagination Links

**PL1: No next/prev URLs in response (Severity: MEDIUM)**
Neither v1 nor v2 includes links to adjacent pages. Clients must construct URLs themselves. Include HATEOAS-style links:
```json
{
  "items": [...],
  "links": {
    "next": "/api/v1/articles?page=3&limit=20",
    "prev": "/api/v1/articles?page=1&limit=20"
  }
}
```

### LOW - Excessive Limit

**EL1: v1 allows limit up to 1000 (Severity: LOW)**
`le=1000` is too generous. Most clients need 20-100 items. Cap at 100 and document the limit.'''),

    ("thinking/code-review", r'''Review this REST API filtering design and identify issues:

```python
from fastapi import FastAPI, Query, Depends
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date
from enum import Enum

app = FastAPI()

class SortField(str, Enum):
    name = "name"
    price = "price"
    created = "created_at"
    rating = "avg_rating"

class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

class ProductFilter:
    def __init__(
        self,
        search: Optional[str] = Query(None, min_length=1, max_length=200),
        category: Optional[str] = None,
        categories: Optional[str] = Query(None, description="Comma-separated"),
        min_price: Optional[float] = Query(None, ge=0),
        max_price: Optional[float] = Query(None, ge=0),
        in_stock: Optional[bool] = None,
        created_after: Optional[date] = None,
        created_before: Optional[date] = None,
        tags: Optional[str] = Query(None, description="Comma-separated"),
        rating_min: Optional[float] = Query(None, ge=0, le=5),
        sort: SortField = SortField.created,
        order: SortOrder = SortOrder.desc,
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100),
    ):
        self.search = search
        self.category = category
        self.categories = categories.split(",") if categories else None
        self.min_price = min_price
        self.max_price = max_price
        self.in_stock = in_stock
        self.created_after = created_after
        self.created_before = created_before
        self.tags = tags.split(",") if tags else None
        self.rating_min = rating_min
        self.sort = sort
        self.order = order
        self.page = page
        self.per_page = per_page

@app.get("/api/v1/products")
async def list_products(filters: ProductFilter = Depends()):
    query = Product.query

    if filters.search:
        query = query.filter(
            Product.name.ilike(f"%{filters.search}%") |
            Product.description.ilike(f"%{filters.search}%")
        )
    if filters.category:
        query = query.filter(Product.category == filters.category)
    if filters.categories:
        query = query.filter(Product.category.in_(filters.categories))
    if filters.min_price is not None:
        query = query.filter(Product.price >= filters.min_price)
    if filters.max_price is not None:
        query = query.filter(Product.price <= filters.max_price)
    if filters.in_stock is not None:
        query = query.filter(Product.stock > 0 if filters.in_stock else Product.stock == 0)
    if filters.created_after:
        query = query.filter(Product.created_at >= filters.created_after)
    if filters.created_before:
        query = query.filter(Product.created_at <= filters.created_before)
    if filters.tags:
        for tag in filters.tags:
            query = query.filter(Product.tags.contains([tag]))
    if filters.rating_min is not None:
        query = query.filter(Product.avg_rating >= filters.rating_min)

    total = query.count()
    query = query.order_by(
        getattr(Product, filters.sort.value).desc()
        if filters.order == SortOrder.desc
        else getattr(Product, filters.sort.value).asc()
    )
    offset = (filters.page - 1) * filters.per_page
    products = query.offset(offset).limit(filters.per_page).all()

    return {
        "items": products,
        "total": total,
        "page": filters.page,
        "per_page": filters.per_page,
        "pages": -(-total // filters.per_page),
    }
```''', r'''<think>
Let me review this filtering design.

1. Good practices:
- Enum for sort fields prevents arbitrary column names
- Query validators with ge, le, min_length, max_length
- Dependency injection pattern for filters
- Proper pagination metadata in response

2. Duplicate category filters:
- Both `category` (single) and `categories` (comma-separated) exist. If both are provided, they are both applied with AND logic, which is confusing. The single category filter is redundant since categories can handle a single value.

3. Comma-separated query parameters:
- `categories` and `tags` use comma-separated strings. This is workable but has edge cases: what if a tag contains a comma? The split fails. Consider using repeated query parameters: `?tag=python&tag=web` which FastAPI supports as `tags: List[str] = Query(None)`.

4. Price range validation:
- min_price and max_price each validate ge=0, but there is no validation that min_price <= max_price. A request with min_price=100&max_price=10 returns no results without explanation.

5. Date range:
- Same issue: created_after and created_before have no cross-validation.

6. Search with ILIKE:
- `f"%{filters.search}%"` with ILIKE works but has performance issues. Leading wildcard (%) prevents index usage. For large tables, this is a full table scan.
- Special characters like % and _ in the search term are not escaped, affecting the LIKE pattern.

7. Tag filtering:
- `for tag in filters.tags: query = query.filter(Product.tags.contains([tag]))` applies AND logic across tags. Finding products with ALL specified tags may not be what users expect (OR is more common for tag filtering).

8. Count query:
- `total = query.count()` runs before pagination. With complex filters, this COUNT can be slow. Consider caching or using an approximate count.

9. Sort by avg_rating:
- If avg_rating is a computed field (not stored), sorting by it requires a subquery or join, which can be very slow on large datasets.

These are relatively minor issues -- the overall design is solid.

Let me write the review.
</think>

## Code Review: REST API Filtering Design

### Overall Assessment
This is a well-structured filtering implementation. The use of Depends() for filter injection, enums for sort fields, and pagination metadata are all good practices. The issues below are refinements rather than critical problems.

### MEDIUM - Duplicate Category Parameters

**DC1: Single and multi-category filters overlap (Severity: MEDIUM)**
```python
category: Optional[str] = None,
categories: Optional[str] = Query(None, description="Comma-separated"),
```
If both are provided (`?category=books&categories=toys,games`), both filters apply with AND logic, returning products that are simultaneously in "books" AND in ("toys", "games") -- which returns nothing. Remove `category` and use `categories` for both single and multi-value:
```python
categories: Optional[List[str]] = Query(None)
# Usage: ?categories=books or ?categories=books&categories=toys
```

### MEDIUM - Comma-Separated Values Fragile

**CSV1: Tags/categories with commas break splitting (Severity: MEDIUM)**
`categories.split(",")` breaks if a category name contains a comma. Use FastAPI's native list query support:
```python
tags: Optional[List[str]] = Query(None)
# Client sends: ?tags=python&tags=web&tags=api
```
This is cleaner and handles special characters correctly.

### MEDIUM - No Cross-Field Validation

**CF1: min_price can exceed max_price (Severity: MEDIUM)**
A request with `min_price=100&max_price=10` returns zero results with no error. Validate:
```python
if self.min_price is not None and self.max_price is not None:
    if self.min_price > self.max_price:
        raise HTTPException(400, "min_price cannot exceed max_price")
```
Same for `created_after` and `created_before`.

### MEDIUM - LIKE Pattern Injection

**LP1: Special characters in search affect LIKE pattern (Severity: MEDIUM)**
```python
Product.name.ilike(f"%{filters.search}%")
```
If the user searches for `100%_off`, the `%` and `_` are LIKE wildcards, matching unexpected patterns. Escape special characters:
```python
from sqlalchemy import func
escaped = filters.search.replace('%', '\\%').replace('_', '\\_')
query = query.filter(Product.name.ilike(f"%{escaped}%", escape='\\'))
```

### MEDIUM - Tag Filter Uses AND Logic

**TL1: Multiple tags require ALL to match (Severity: MEDIUM)**
```python
for tag in filters.tags:
    query = query.filter(Product.tags.contains([tag]))
```
This finds products with ALL specified tags (AND). Most users expect "products with ANY of these tags" (OR). Document clearly or provide a parameter to choose:
```python
tag_mode: str = Query("any", regex="^(any|all)$")
```

### LOW - Leading Wildcard Performance

**WC1: ILIKE with leading % prevents index usage (Severity: LOW)**
`%search_term%` forces a full table scan regardless of indexes. For large tables (millions of rows), search becomes slow. Consider:
- Full-text search (PostgreSQL tsvector, Elasticsearch)
- Trigram indexes (pg_trgm extension)
- Only trailing wildcard for prefix searches

### LOW - Count Query Performance

**CQ1: COUNT runs on every request (Severity: LOW)**
`query.count()` with complex filters can be slow. For large datasets, consider:
- Caching the total with a short TTL
- Using `EXPLAIN` estimated row counts
- Returning total only on the first page request'''),

    ("thinking/code-review", r'''Review this REST API response design and identify issues:

```python
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
import json

app = FastAPI()

class SuccessResponse(BaseModel):
    success: bool = True
    data: Any
    message: str = "OK"
    timestamp: datetime = Field(default_factory=datetime.now)

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    code: int
    timestamp: datetime = Field(default_factory=datetime.now)

@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    user = await fetch_user(user_id)
    if not user:
        return ErrorResponse(error="User not found", code=404)
    return SuccessResponse(data=user)

@app.get("/api/users")
async def list_users():
    users = await fetch_all_users()
    return SuccessResponse(data=users, message=f"Found {len(users)} users")

@app.post("/api/users")
async def create_user(data: dict):
    user = await save_user(data)
    return SuccessResponse(data=user, message="User created")

@app.get("/api/products")
async def list_products():
    products = await fetch_products()
    return {
        "success": True,
        "data": [p.dict() for p in products],
        "count": len(products),
    }

@app.get("/api/orders/{order_id}")
async def get_order(order_id: int):
    order = await fetch_order(order_id)
    return {
        "order": order.dict(),
        "items": [item.dict() for item in order.items],
        "total": order.total,
        "status": order.status,
    }

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int):
    deleted = await remove_user(user_id)
    if deleted:
        return Response(status_code=204)
    return SuccessResponse(data=None, message="Nothing to delete")

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.2.3"}
```''', r'''<think>
Let me review this REST API response design.

1. The wrapper pattern (SuccessResponse/ErrorResponse):
- Using a `success` boolean alongside HTTP status codes is redundant. HTTP already has status codes for this purpose. A 200 response is by definition successful.
- The `data: Any` field loses all type information. OpenAPI docs will show `Any` instead of the actual schema.
- Wrapping every response in `{"success": true, "data": {...}}` adds overhead and makes the API harder to use. Most modern APIs return the resource directly.

2. ErrorResponse returns HTTP 200:
- `return ErrorResponse(error="User not found", code=404)` returns an ErrorResponse object with a code field of 404, but the HTTP status code is 200 (the default). The client receives a 200 response claiming "User not found". Must use JSONResponse with proper status:
```python
return JSONResponse(status_code=404, content=ErrorResponse(...).dict())
```

3. Inconsistent response formats:
- get_user/list_users: Use SuccessResponse wrapper
- list_products: Uses a custom dict with "count" field
- get_order: No wrapper, nested structure
- health: Plain dict
- Four different response shapes.

4. delete_user:
- Returns 204 (No Content) when deleted -- good.
- Returns 200 with SuccessResponse when not deleted -- bad. "Nothing to delete" with HTTP 200 suggests success. Should be 404.

5. Timestamp in every response:
- Adding a timestamp to every response is unusual. It increases payload size and is redundant since HTTP responses have a Date header.

6. list_products calls p.dict():
- Manually calling .dict() suggests Pydantic v1. In v2, it is .model_dump(). Also, if the response_model were set properly, FastAPI handles serialization automatically.

7. No HATEOAS links:
- Responses do not include links to related resources. For example, a user response could include a link to their orders.

Let me write the review.
</think>

## Code Review: REST API Response Design

### CRITICAL - Error Response Returns HTTP 200

**ER1: ErrorResponse has correct code field but wrong HTTP status (Severity: CRITICAL)**
```python
@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    if not user:
        return ErrorResponse(error="User not found", code=404)
```
This returns HTTP 200 with `{"success": false, "error": "User not found", "code": 404}`. The HTTP status code is 200 (success), but the body says 404. Clients checking HTTP status see success. Use proper HTTP status:
```python
raise HTTPException(status_code=404, detail="User not found")
# or:
return JSONResponse(status_code=404, content={"error": "User not found"})
```

### HIGH - Redundant Wrapper Pattern

**WP1: SuccessResponse duplicates HTTP semantics (Severity: HIGH)**
```python
class SuccessResponse(BaseModel):
    success: bool = True
    data: Any
```
The `success` field is redundant with HTTP status codes. A 200 response is by definition successful. The wrapper adds payload overhead and makes the API non-standard. Most modern APIs return the resource directly:
```python
@app.get("/api/users/{user_id}")
async def get_user(user_id: int) -> User:
    user = await fetch_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user  # FastAPI serializes directly
```

**WP2: data: Any destroys OpenAPI documentation (Severity: HIGH)**
`data: Any` means the OpenAPI schema shows no structure for the response body. Clients and code generators get no type information. Use specific response models:
```python
@app.get("/api/users/{user_id}", response_model=User)
```

### HIGH - Inconsistent Response Formats

**IF1: Four different response shapes (Severity: HIGH)**
- `/api/users/{id}`: `{"success": true, "data": {...}, "message": "OK"}`
- `/api/products`: `{"success": true, "data": [...], "count": 5}`
- `/api/orders/{id}`: `{"order": {...}, "items": [...], "total": 99.99}`
- `/api/health`: `{"status": "ok", "version": "1.2.3"}`

Clients cannot write generic response handling. Choose one pattern:
- **Option A (recommended)**: Return resources directly. GET /users/1 returns `{user fields}`. GET /users returns `[{user fields}]`.
- **Option B**: Consistent envelope: `{"data": ..., "meta": {...}}` for all endpoints.

### MEDIUM - delete_user Inconsistent

**DL1: Non-deletion returns 200 success (Severity: MEDIUM)**
```python
if deleted:
    return Response(status_code=204)
return SuccessResponse(data=None, message="Nothing to delete")
```
When the user does not exist, this returns 200 with "Nothing to delete" instead of 404 "Not found". Idempotent DELETE should return 204 even if already deleted, or 404 if never existed.

### LOW - Unnecessary Timestamp

**TS1: Response timestamp adds no value (Severity: LOW)**
```python
timestamp: datetime = Field(default_factory=datetime.now)
```
Every response includes a timestamp. HTTP responses already have a `Date` header. This adds bytes to every response with no client use case. Remove unless specifically required.

### LOW - No Links to Related Resources

**LK1: No HATEOAS or resource links (Severity: LOW)**
Responses do not include links to related resources. A user response could include:
```json
{
  "id": 1,
  "name": "Alice",
  "_links": {
    "orders": "/api/users/1/orders",
    "profile": "/api/users/1/profile"
  }
}
```
This improves API discoverability and reduces client-side URL construction.'''),
]
