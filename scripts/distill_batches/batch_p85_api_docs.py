"""API documentation — OpenAPI, Swagger, and API design patterns."""

PAIRS = [
    (
        "api/openapi-design",
        "Show OpenAPI specification patterns: schema definitions, endpoints, authentication, and code generation.",
        '''OpenAPI specification patterns:

```yaml
# openapi.yaml
openapi: "3.1.0"
info:
  title: Order Management API
  version: "2.0.0"
  description: |
    REST API for managing orders and customers.

    ## Authentication
    All endpoints require Bearer token authentication.
  contact:
    email: api-support@example.com
  license:
    name: MIT

servers:
  - url: https://api.example.com/v2
    description: Production
  - url: https://staging-api.example.com/v2
    description: Staging

# Reusable security scheme
security:
  - BearerAuth: []

paths:
  /orders:
    get:
      operationId: listOrders
      summary: List orders with filtering
      tags: [Orders]
      parameters:
        - name: status
          in: query
          schema:
            $ref: '#/components/schemas/OrderStatus'
        - name: customer_id
          in: query
          schema:
            type: string
            format: uuid
        - $ref: '#/components/parameters/PageSize'
        - $ref: '#/components/parameters/PageCursor'
      responses:
        '200':
          description: Paginated list of orders
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderList'
          headers:
            X-Total-Count:
              schema:
                type: integer
        '401':
          $ref: '#/components/responses/Unauthorized'

    post:
      operationId: createOrder
      summary: Create a new order
      tags: [Orders]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
            examples:
              simple:
                summary: Simple order
                value:
                  customer_id: "550e8400-e29b-41d4-a716-446655440000"
                  items:
                    - product_id: "prod-001"
                      quantity: 2
      responses:
        '201':
          description: Order created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '422':
          $ref: '#/components/responses/ValidationError'

  /orders/{orderId}:
    get:
      operationId: getOrder
      summary: Get order by ID
      tags: [Orders]
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Order details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '404':
          $ref: '#/components/responses/NotFound'

components:
  # --- Schemas ---
  schemas:
    Order:
      type: object
      required: [id, customer_id, status, items, created_at]
      properties:
        id:
          type: string
          format: uuid
          readOnly: true
        customer_id:
          type: string
          format: uuid
        status:
          $ref: '#/components/schemas/OrderStatus'
        items:
          type: array
          items:
            $ref: '#/components/schemas/OrderItem'
          minItems: 1
        total:
          type: number
          format: double
          readOnly: true
        created_at:
          type: string
          format: date-time
          readOnly: true

    OrderItem:
      type: object
      required: [product_id, quantity]
      properties:
        product_id:
          type: string
        quantity:
          type: integer
          minimum: 1
          maximum: 999
        unit_price:
          type: number
          format: double

    OrderStatus:
      type: string
      enum: [pending, confirmed, shipped, delivered, cancelled]

    CreateOrderRequest:
      type: object
      required: [customer_id, items]
      properties:
        customer_id:
          type: string
          format: uuid
        items:
          type: array
          items:
            $ref: '#/components/schemas/OrderItem'
          minItems: 1

    OrderList:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/Order'
        next_cursor:
          type: string
          nullable: true
        has_more:
          type: boolean

    Error:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
        message:
          type: string
        details:
          type: array
          items:
            type: object
            properties:
              field:
                type: string
              message:
                type: string

  # --- Reusable parameters ---
  parameters:
    PageSize:
      name: limit
      in: query
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
    PageCursor:
      name: cursor
      in: query
      schema:
        type: string
      description: Cursor for next page

  # --- Reusable responses ---
  responses:
    Unauthorized:
      description: Authentication required
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
    ValidationError:
      description: Validation failed
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'

  # --- Security ---
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

OpenAPI patterns:
1. **`$ref` components** — reusable schemas, parameters, and responses
2. **`readOnly` fields** — distinguish create request from response shape
3. **`operationId`** — unique ID for code generation (client SDK method names)
4. **Cursor pagination** — `next_cursor` + `has_more` instead of offset
5. **`examples`** — request/response examples for documentation and mocking'''
    ),
    (
        "api/rest-design",
        "Show REST API design patterns: versioning, pagination, error responses, HATEOAS, and rate limiting.",
        '''REST API design patterns:

```python
from fastapi import FastAPI, Query, HTTPException, Request, Response
from pydantic import BaseModel, Field
from typing import Annotated
from enum import Enum
import time


app = FastAPI(title="API Design Patterns")


# --- Consistent error response ---

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: list[dict] = []
    request_id: str = ""


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return Response(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail if isinstance(exc.detail, str) else "error",
            message=str(exc.detail),
            request_id=request.headers.get("x-request-id", ""),
        ).model_dump_json(),
        media_type="application/json",
    )


# --- Cursor-based pagination ---

class PaginatedResponse(BaseModel):
    items: list
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None  # Optional: expensive for large datasets


@app.get("/api/v2/orders")
async def list_orders(
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: str | None = None,
):
    """Cursor-based pagination (not offset — stable under inserts/deletes)."""
    query = "SELECT * FROM orders"
    params = []

    if cursor:
        # Cursor encodes: last_id for stable pagination
        import base64
        last_id = base64.b64decode(cursor).decode()
        query += " WHERE id > %s"
        params.append(last_id)

    if status:
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY id LIMIT %s"
    params.append(limit + 1)  # Fetch one extra to check has_more

    rows = await db.fetch(query, *params)
    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        import base64
        next_cursor = base64.b64encode(items[-1]["id"].encode()).decode()

    return PaginatedResponse(
        items=items, next_cursor=next_cursor, has_more=has_more,
    )


# --- API versioning ---

# Option 1: URL path versioning (most common)
# /api/v1/orders, /api/v2/orders

# Option 2: Header versioning
# Accept: application/vnd.myapi.v2+json

from fastapi import APIRouter

v1 = APIRouter(prefix="/api/v1", tags=["v1"])
v2 = APIRouter(prefix="/api/v2", tags=["v2"])

@v1.get("/orders")
async def list_orders_v1():
    """V1: returns flat list."""
    return [{"id": "1", "total": 99.99}]

@v2.get("/orders")
async def list_orders_v2():
    """V2: returns paginated envelope."""
    return {"items": [{"id": "1", "total": 99.99}], "has_more": False}

app.include_router(v1)
app.include_router(v2)


# --- Rate limiting headers ---

@app.middleware("http")
async def rate_limit_headers(request: Request, call_next):
    response = await call_next(request)

    # Standard rate limit headers
    response.headers["X-RateLimit-Limit"] = "100"
    response.headers["X-RateLimit-Remaining"] = "95"
    response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 3600)

    # Retry-After for 429 responses
    if response.status_code == 429:
        response.headers["Retry-After"] = "60"

    return response


# --- Idempotency key ---

@app.post("/api/v2/payments")
async def create_payment(
    request: Request,
    payment: dict,
):
    """Idempotent POST — safe to retry."""
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header required")

    # Check if already processed
    existing = await db.get_by_idempotency_key(idempotency_key)
    if existing:
        return existing  # Return cached response

    result = await process_payment(payment)
    await db.save_with_idempotency_key(idempotency_key, result)
    return result


# --- Resource naming conventions ---

# GOOD:
# GET    /api/v2/orders              → List orders
# POST   /api/v2/orders              → Create order
# GET    /api/v2/orders/{id}         → Get order
# PATCH  /api/v2/orders/{id}         → Partial update
# DELETE /api/v2/orders/{id}         → Delete order
# GET    /api/v2/orders/{id}/items   → List order items (sub-resource)
# POST   /api/v2/orders/{id}/cancel  → Action (verb as sub-resource)

# BAD:
# GET /api/getOrders
# POST /api/deleteOrder
# GET /api/order_list
```

REST API design patterns:
1. **Cursor pagination** — stable under concurrent inserts, encode last_id
2. **Consistent error envelope** — `{error, message, details, request_id}`
3. **Idempotency keys** — safe POST retries for payments/mutations
4. **Rate limit headers** — `X-RateLimit-Remaining` + `Retry-After`
5. **URL versioning** — `/api/v2/` is simplest, most widely supported'''
    ),
]
"""
