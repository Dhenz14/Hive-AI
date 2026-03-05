"""API design: REST maturity, GraphQL schema design, versioning strategies, pagination patterns."""

PAIRS = [
    (
        "api-design/rest-maturity",
        "How do I build a REST API that follows Richardson Maturity Model Level 3 (HATEOAS) with proper resource design, status codes, and hypermedia controls in FastAPI?",
        '''The Richardson Maturity Model defines four levels of REST API design. Level 3 (HATEOAS) is the highest, where responses include hypermedia links that guide clients through available actions. Here is a complete implementation.

```python
"""REST API at Richardson Maturity Level 3 with HATEOAS in FastAPI."""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Self
from enum import Enum

from fastapi import FastAPI, HTTPException, Request, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict, model_validator


# ── Hypermedia Link Models ─────────────────────────────────────

class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class Link(BaseModel):
    """RFC 8288 Web Linking representation."""
    href: str
    rel: str
    method: HttpMethod = HttpMethod.GET
    title: str | None = None
    type: str = "application/json"

    model_config = ConfigDict(use_enum_values=True)


class HATEOASMixin(BaseModel):
    """Mixin to add hypermedia links to any response."""
    _links: dict[str, Link] = {}

    def add_link(self, rel: str, href: str, method: HttpMethod = HttpMethod.GET, title: str | None = None) -> Self:
        if not hasattr(self, '_link_store'):
            object.__setattr__(self, '_link_store', {})
        self._link_store[rel] = Link(href=href, rel=rel, method=method, title=title)
        return self

    def model_dump(self, **kwargs) -> dict:
        data = super().model_dump(**kwargs)
        if hasattr(self, '_link_store'):
            data["_links"] = {k: v.model_dump() for k, v in self._link_store.items()}
        return data


# ── Domain Models ──────────────────────────────────────────────

class OrderStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=100)
    unit_price: float = Field(gt=0)


class OrderCreate(BaseModel):
    customer_id: str
    items: list[OrderItemCreate] = Field(min_length=1)
    shipping_address: str
    notes: str = ""


class OrderUpdate(BaseModel):
    shipping_address: str | None = None
    notes: str | None = None


class OrderItem(BaseModel):
    product_id: str
    quantity: int
    unit_price: float
    subtotal: float


class OrderResponse(BaseModel):
    """Order resource with HATEOAS links."""
    id: str
    customer_id: str
    status: OrderStatus
    items: list[OrderItem]
    total: float
    shipping_address: str
    notes: str
    created_at: str
    updated_at: str
    _links: dict[str, Any] = {}

    @classmethod
    def with_links(
        cls, order: dict, base_url: str
    ) -> dict[str, Any]:
        data = cls.model_validate(order).model_dump()
        order_url = f"{base_url}/orders/{order['id']}"

        links: dict[str, Any] = {
            "self": Link(
                href=order_url, rel="self",
                title="This order",
            ).model_dump(),
            "collection": Link(
                href=f"{base_url}/orders", rel="collection",
                title="All orders",
            ).model_dump(),
            "customer": Link(
                href=f"{base_url}/customers/{order['customer_id']}",
                rel="customer", title="Order customer",
            ).model_dump(),
        }

        # Add state-dependent action links
        status = order["status"]
        if status == "draft":
            links["confirm"] = Link(
                href=f"{order_url}/confirm", rel="confirm",
                method=HttpMethod.POST,
                title="Confirm this order",
            ).model_dump()
            links["update"] = Link(
                href=order_url, rel="update",
                method=HttpMethod.PATCH,
                title="Update this order",
            ).model_dump()
            links["cancel"] = Link(
                href=f"{order_url}/cancel", rel="cancel",
                method=HttpMethod.POST,
                title="Cancel this order",
            ).model_dump()
        elif status == "confirmed":
            links["cancel"] = Link(
                href=f"{order_url}/cancel", rel="cancel",
                method=HttpMethod.POST,
                title="Cancel this order",
            ).model_dump()
        elif status == "shipped":
            links["track"] = Link(
                href=f"{order_url}/tracking", rel="track",
                title="Track shipment",
            ).model_dump()

        data["_links"] = links
        return data


class PaginatedResponse(BaseModel):
    """Paginated collection with navigation links."""
    data: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    _links: dict[str, Any] = {}

    @classmethod
    def build(
        cls, items: list[dict], total: int,
        page: int, page_size: int, base_url: str,
    ) -> dict[str, Any]:
        last_page = max(1, (total + page_size - 1) // page_size)

        links = {
            "self": Link(
                href=f"{base_url}?page={page}&page_size={page_size}",
                rel="self",
            ).model_dump(),
            "first": Link(
                href=f"{base_url}?page=1&page_size={page_size}",
                rel="first",
            ).model_dump(),
            "last": Link(
                href=f"{base_url}?page={last_page}&page_size={page_size}",
                rel="last",
            ).model_dump(),
        }
        if page > 1:
            links["prev"] = Link(
                href=f"{base_url}?page={page-1}&page_size={page_size}",
                rel="prev",
            ).model_dump()
        if page < last_page:
            links["next"] = Link(
                href=f"{base_url}?page={page+1}&page_size={page_size}",
                rel="next",
            ).model_dump()

        return {
            "data": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "_links": links,
        }


# ── API Application ───────────────────────────────────────────

app = FastAPI(
    title="Orders API",
    version="1.0.0",
    description="REST Level 3 API with HATEOAS",
)

# In-memory store for demo
ORDERS: dict[str, dict] = {}


def get_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/api/v1"


@app.post(
    "/api/v1/orders",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
)
async def create_order(order: OrderCreate, request: Request):
    base_url = get_base_url(request)
    now = datetime.now(timezone.utc).isoformat()
    order_id = str(uuid.uuid4())

    record = {
        "id": order_id,
        "customer_id": order.customer_id,
        "status": OrderStatus.DRAFT,
        "items": [
            {**item.model_dump(), "subtotal": item.quantity * item.unit_price}
            for item in order.items
        ],
        "total": sum(i.quantity * i.unit_price for i in order.items),
        "shipping_address": order.shipping_address,
        "notes": order.notes,
        "created_at": now,
        "updated_at": now,
    }
    ORDERS[order_id] = record

    response_data = OrderResponse.with_links(record, base_url)
    return JSONResponse(
        content=response_data,
        status_code=201,
        headers={"Location": f"{base_url}/orders/{order_id}"},
    )


@app.get("/api/v1/orders", response_model=None)
async def list_orders(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: OrderStatus | None = Query(None, alias="status"),
    customer_id: str | None = None,
):
    base_url = get_base_url(request)
    filtered = list(ORDERS.values())

    if status_filter:
        filtered = [o for o in filtered if o["status"] == status_filter]
    if customer_id:
        filtered = [o for o in filtered if o["customer_id"] == customer_id]

    total = len(filtered)
    start = (page - 1) * page_size
    page_items = filtered[start : start + page_size]

    items_with_links = [
        OrderResponse.with_links(o, base_url) for o in page_items
    ]

    return PaginatedResponse.build(
        items_with_links, total, page, page_size,
        f"{base_url}/orders",
    )


@app.get("/api/v1/orders/{order_id}", response_model=None)
async def get_order(order_id: str, request: Request):
    base_url = get_base_url(request)
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "OrderNotFound",
                "message": f"Order {order_id} not found",
                "_links": {
                    "collection": Link(
                        href=f"{base_url}/orders",
                        rel="collection",
                    ).model_dump(),
                },
            },
        )
    return OrderResponse.with_links(order, base_url)


@app.post(
    "/api/v1/orders/{order_id}/confirm",
    response_model=None,
)
async def confirm_order(order_id: str, request: Request):
    base_url = get_base_url(request)
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] != OrderStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "InvalidStateTransition",
                "message": f"Cannot confirm order in '{order['status']}' status",
                "allowed_from": ["draft"],
            },
        )

    order["status"] = OrderStatus.CONFIRMED
    order["updated_at"] = datetime.now(timezone.utc).isoformat()
    return OrderResponse.with_links(order, base_url)


@app.post(
    "/api/v1/orders/{order_id}/cancel",
    response_model=None,
)
async def cancel_order(order_id: str, request: Request):
    base_url = get_base_url(request)
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    cancellable = {OrderStatus.DRAFT, OrderStatus.CONFIRMED}
    if order["status"] not in cancellable:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "InvalidStateTransition",
                "message": f"Cannot cancel order in '{order['status']}' status",
            },
        )

    order["status"] = OrderStatus.CANCELLED
    order["updated_at"] = datetime.now(timezone.utc).isoformat()
    return OrderResponse.with_links(order, base_url)
```

Richardson Maturity Model levels:

| Level | Name | Description | Example |
|-------|------|-------------|---------|
| 0 | Swamp of POX | Single endpoint, RPC-style | POST /api with action in body |
| 1 | Resources | Multiple URIs for resources | /orders, /orders/123 |
| 2 | HTTP Verbs | Correct use of GET/POST/PUT/DELETE | GET /orders, POST /orders |
| 3 | HATEOAS | Hypermedia controls in responses | _links with available actions |

Key patterns:
- Include _links in every response to guide API consumers to available actions
- State-dependent links: only show "confirm" when order is in "draft" status
- Use proper HTTP status codes: 201 Created with Location header, 409 Conflict for invalid state transitions
- Paginated collections include first/last/prev/next navigation links
- Error responses include links to help clients recover (e.g., link to collection)
- Keep resource URLs stable -- clients follow links, not hard-coded paths
'''
    ),
    (
        "api-design/graphql-schema",
        "How do I design a production GraphQL schema with proper type design, relay-style pagination, dataloaders for N+1 prevention, and input validation using Strawberry?",
        '''A well-designed GraphQL schema uses relay-style connections for pagination, input types for mutations, dataloaders to prevent N+1 queries, and proper error handling. Here is a complete Strawberry implementation.

```python
"""Production GraphQL API with Strawberry, dataloaders, and relay pagination."""

from __future__ import annotations
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any, Optional, Generic, TypeVar
from enum import Enum
from dataclasses import dataclass

import strawberry
from strawberry.types import Info
from strawberry.dataloader import DataLoader
from strawberry.relay import Node, NodeID, Connection, Edge
from strawberry.scalars import JSON
from strawberry.permission import BasePermission
from strawberry.schema.config import StrawberryConfig
import asyncpg


# ── Custom Scalars and Enums ───────────────────────────────────

@strawberry.enum
class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@strawberry.enum
class SortDirection(Enum):
    ASC = "asc"
    DESC = "desc"


# ── Permission Classes ─────────────────────────────────────────

class IsAuthenticated(BasePermission):
    message = "Authentication required"

    async def has_permission(
        self, source: Any, info: Info, **kwargs
    ) -> bool:
        return info.context.get("user") is not None


class IsAdmin(BasePermission):
    message = "Admin access required"

    async def has_permission(
        self, source: Any, info: Info, **kwargs
    ) -> bool:
        user = info.context.get("user")
        return user is not None and user.get("role") == "admin"


# ── Relay Connection Types ─────────────────────────────────────

@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: str | None = None
    end_cursor: str | None = None


T = TypeVar("T")


@strawberry.type
class ConnectionEdge(Generic[T]):
    node: T
    cursor: str


@strawberry.type
class PaginatedConnection(Generic[T]):
    edges: list[ConnectionEdge[T]]
    page_info: PageInfo
    total_count: int


# ── Domain Types ───────────────────────────────────────────────

@strawberry.type
class Customer:
    id: strawberry.ID
    name: str
    email: str
    created_at: datetime

    @strawberry.field
    async def orders(
        self,
        info: Info,
        first: int = 10,
        after: str | None = None,
        status: OrderStatus | None = None,
    ) -> PaginatedConnection[Order]:
        """Fetch customer's orders with cursor pagination."""
        repo = info.context["order_repo"]
        return await repo.get_orders_by_customer(
            customer_id=str(self.id),
            first=first,
            after=after,
            status=status,
        )

    @strawberry.field
    async def total_spent(self, info: Info) -> float:
        repo = info.context["order_repo"]
        return await repo.get_customer_total_spent(str(self.id))


@strawberry.type
class Product:
    id: strawberry.ID
    name: str
    price: float
    description: str
    in_stock: bool

    @strawberry.field
    async def reviews(
        self, info: Info, first: int = 5
    ) -> list[Review]:
        loader = info.context["review_loader"]
        return await loader.load(str(self.id))


@strawberry.type
class OrderItem:
    product: Product
    quantity: int
    unit_price: float

    @strawberry.field
    def subtotal(self) -> float:
        return self.quantity * self.unit_price


@strawberry.type
class Order:
    id: strawberry.ID
    status: OrderStatus
    total: float
    shipping_address: str
    created_at: datetime
    updated_at: datetime

    @strawberry.field
    async def customer(self, info: Info) -> Customer:
        loader = info.context["customer_loader"]
        return await loader.load(str(self._customer_id))

    @strawberry.field
    async def items(self, info: Info) -> list[OrderItem]:
        loader = info.context["order_items_loader"]
        return await loader.load(str(self.id))


@strawberry.type
class Review:
    id: strawberry.ID
    rating: int
    comment: str
    author_name: str
    created_at: datetime


# ── Input Types ────────────────────────────────────────────────

@strawberry.input
class CreateOrderInput:
    customer_id: strawberry.ID
    items: list[OrderItemInput]
    shipping_address: str
    notes: str = ""


@strawberry.input
class OrderItemInput:
    product_id: strawberry.ID
    quantity: int


@strawberry.input
class OrderFilterInput:
    status: OrderStatus | None = None
    min_total: float | None = None
    max_total: float | None = None
    customer_id: strawberry.ID | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


@strawberry.input
class OrderSortInput:
    field: str = "created_at"
    direction: SortDirection = SortDirection.DESC


# ── Mutation Payloads (Union Error Handling) ───────────────────

@strawberry.type
class CreateOrderSuccess:
    order: Order


@strawberry.type
class ValidationError:
    field: str
    message: str


@strawberry.type
class InsufficientStockError:
    product_id: str
    requested: int
    available: int


CreateOrderResult = strawberry.union(
    "CreateOrderResult",
    types=[CreateOrderSuccess, ValidationError, InsufficientStockError],
)


@strawberry.type
class CancelOrderSuccess:
    order: Order


@strawberry.type
class OrderNotFoundError:
    order_id: str
    message: str = "Order not found"


@strawberry.type
class InvalidStateError:
    current_status: str
    message: str


CancelOrderResult = strawberry.union(
    "CancelOrderResult",
    types=[CancelOrderSuccess, OrderNotFoundError, InvalidStateError],
)


# ── DataLoader Factory ────────────────────────────────────────

class DataLoaderFactory:
    """Creates dataloaders to prevent N+1 queries."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    def customer_loader(self) -> DataLoader[str, Customer]:
        async def load_customers(ids: list[str]) -> list[Customer]:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM customers WHERE id = ANY($1::uuid[])",
                    ids,
                )
            by_id = {str(r["id"]): r for r in rows}
            return [
                Customer(
                    id=strawberry.ID(id),
                    name=by_id[id]["name"],
                    email=by_id[id]["email"],
                    created_at=by_id[id]["created_at"],
                )
                if id in by_id else None
                for id in ids
            ]
        return DataLoader(load_fn=load_customers)

    def order_items_loader(self) -> DataLoader[str, list[OrderItem]]:
        async def load_items(
            order_ids: list[str],
        ) -> list[list[OrderItem]]:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT oi.*, p.name, p.description, p.in_stock
                    FROM order_items oi
                    JOIN products p ON oi.product_id = p.id
                    WHERE oi.order_id = ANY($1::uuid[])""",
                    order_ids,
                )
            grouped: dict[str, list[OrderItem]] = {
                oid: [] for oid in order_ids
            }
            for r in rows:
                oid = str(r["order_id"])
                if oid in grouped:
                    grouped[oid].append(OrderItem(
                        product=Product(
                            id=strawberry.ID(str(r["product_id"])),
                            name=r["name"],
                            price=r["unit_price"],
                            description=r["description"],
                            in_stock=r["in_stock"],
                        ),
                        quantity=r["quantity"],
                        unit_price=r["unit_price"],
                    ))
            return [grouped[oid] for oid in order_ids]
        return DataLoader(load_fn=load_items)

    def review_loader(self) -> DataLoader[str, list[Review]]:
        async def load_reviews(
            product_ids: list[str],
        ) -> list[list[Review]]:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM reviews "
                    "WHERE product_id = ANY($1::uuid[]) "
                    "ORDER BY created_at DESC LIMIT 10",
                    product_ids,
                )
            grouped: dict[str, list[Review]] = {
                pid: [] for pid in product_ids
            }
            for r in rows:
                pid = str(r["product_id"])
                if pid in grouped:
                    grouped[pid].append(Review(
                        id=strawberry.ID(str(r["id"])),
                        rating=r["rating"],
                        comment=r["comment"],
                        author_name=r["author_name"],
                        created_at=r["created_at"],
                    ))
            return [grouped[pid] for pid in product_ids]
        return DataLoader(load_fn=load_reviews)


# ── Query Root ─────────────────────────────────────────────────

@strawberry.type
class Query:
    @strawberry.field(permission_classes=[IsAuthenticated])
    async def orders(
        self,
        info: Info,
        first: int = 20,
        after: str | None = None,
        filter: OrderFilterInput | None = None,
        sort: OrderSortInput | None = None,
    ) -> PaginatedConnection[Order]:
        repo = info.context["order_repo"]
        return await repo.get_orders(
            first=first, after=after,
            filter=filter, sort=sort,
        )

    @strawberry.field
    async def order(
        self, info: Info, id: strawberry.ID
    ) -> Order | None:
        loader = info.context["order_loader"]
        return await loader.load(str(id))


# ── Mutation Root ──────────────────────────────────────────────

@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsAuthenticated])
    async def create_order(
        self, info: Info, input: CreateOrderInput
    ) -> CreateOrderResult:
        repo = info.context["order_repo"]
        try:
            order = await repo.create_order(input)
            return CreateOrderSuccess(order=order)
        except StockError as e:
            return InsufficientStockError(
                product_id=e.product_id,
                requested=e.requested,
                available=e.available,
            )

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    async def cancel_order(
        self, info: Info, order_id: strawberry.ID, reason: str = ""
    ) -> CancelOrderResult:
        repo = info.context["order_repo"]
        order = await repo.get_order(str(order_id))
        if not order:
            return OrderNotFoundError(order_id=str(order_id))
        if order.status not in (OrderStatus.PENDING, OrderStatus.CONFIRMED):
            return InvalidStateError(
                current_status=order.status.value,
                message=f"Cannot cancel {order.status.value} order",
            )
        updated = await repo.cancel_order(str(order_id), reason)
        return CancelOrderSuccess(order=updated)


class StockError(Exception):
    def __init__(self, product_id: str, requested: int, available: int):
        self.product_id = product_id
        self.requested = requested
        self.available = available


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    config=StrawberryConfig(auto_camel_case=True),
)
```

GraphQL design patterns comparison:

| Pattern | Purpose | Trade-off |
|---------|---------|-----------|
| Relay Connections | Cursor pagination | More complex than offset |
| DataLoaders | Batch N+1 queries | Per-request lifecycle needed |
| Union errors | Typed error responses | More schema types |
| Input types | Mutation arguments | Extra type definitions |
| Permission classes | Field-level auth | Must handle in every resolver |
| Enums for status | Type-safe filtering | Schema changes for new states |

Key patterns:
- Use DataLoaders for every relationship field to eliminate N+1 queries
- Return union types from mutations for type-safe error handling instead of throwing
- Use cursor-based pagination (Relay connections) for stable pagination under concurrent writes
- Define separate input types for create/update operations
- Apply permission classes at the field level for fine-grained authorization
- Keep resolvers thin -- delegate to repository/service layer for business logic
'''
    ),
    (
        "api-design/versioning",
        "What are the best strategies for API versioning, and how do I implement them with backward-compatible changes and deprecation?",
        '''API versioning ensures clients can evolve independently from the server. The right strategy depends on your API type, client ecosystem, and deployment model. Here are all major approaches implemented.

```python
"""API versioning strategies with FastAPI."""

from __future__ import annotations
import warnings
from datetime import datetime, date, timezone
from typing import Any, Callable
from functools import wraps
from enum import Enum

from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.routing import APIRouter, APIRoute
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ── Strategy 1: URL Path Versioning ────────────────────────────

app = FastAPI(title="Versioned API")

v1_router = APIRouter(prefix="/api/v1", tags=["v1"])
v2_router = APIRouter(prefix="/api/v2", tags=["v2"])


# V1 models
class UserResponseV1(BaseModel):
    id: str
    name: str  # Full name as single field
    email: str
    created_at: str


# V2 models (breaking change: split name into first/last)
class UserResponseV2(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime


# V1 keeps working with the old schema
@v1_router.get("/users/{user_id}")
async def get_user_v1(user_id: str) -> UserResponseV1:
    user = await fetch_user(user_id)
    return UserResponseV1(
        id=user["id"],
        name=f"{user['first_name']} {user['last_name']}",
        email=user["email"],
        created_at=user["created_at"].isoformat(),
    )


# V2 uses the new schema
@v2_router.get("/users/{user_id}")
async def get_user_v2(user_id: str) -> UserResponseV2:
    user = await fetch_user(user_id)
    return UserResponseV2(**user)


app.include_router(v1_router)
app.include_router(v2_router)


# ── Strategy 2: Header-Based Versioning ────────────────────────

class VersionHeaderMiddleware(BaseHTTPMiddleware):
    """Route requests based on Accept-Version header."""

    SUPPORTED_VERSIONS = {"1", "2", "3"}
    DEFAULT_VERSION = "3"

    async def dispatch(self, request: Request, call_next):
        version = request.headers.get(
            "accept-version",
            request.headers.get("api-version", self.DEFAULT_VERSION),
        )

        if version not in self.SUPPORTED_VERSIONS:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "UnsupportedVersion",
                    "message": f"Version '{version}' is not supported",
                    "supported": sorted(self.SUPPORTED_VERSIONS),
                },
            )

        request.state.api_version = int(version)
        response = await call_next(request)
        response.headers["X-API-Version"] = version
        return response


def version_gate(min_version: int = 1, max_version: int | None = None):
    """Dependency that checks API version range."""
    async def check_version(request: Request):
        version = getattr(request.state, "api_version", 1)
        if version < min_version:
            raise HTTPException(
                status_code=400,
                detail=f"This endpoint requires API version >= {min_version}",
            )
        if max_version and version > max_version:
            raise HTTPException(
                status_code=410,
                detail=f"This endpoint was removed in version {max_version + 1}",
            )
        return version
    return Depends(check_version)


# ── Strategy 3: Content Negotiation (Accept Header) ───────────

MEDIA_TYPE_V1 = "application/vnd.myapi.v1+json"
MEDIA_TYPE_V2 = "application/vnd.myapi.v2+json"


def negotiate_version(accept: str = Header("application/json")) -> int:
    """Parse version from Accept media type."""
    if "vnd.myapi.v2" in accept:
        return 2
    if "vnd.myapi.v1" in accept:
        return 1
    return 2  # Default to latest


# ── Strategy 4: Additive Versioning (No Breaking Changes) ─────

class AdditiveVersioning:
    """Evolve API without breaking changes using additive patterns."""

    @staticmethod
    def add_field_with_default():
        """New fields always have defaults -- old clients ignore them."""

        class UserV1(BaseModel):
            id: str
            name: str
            email: str

        class UserV1_1(UserV1):
            """V1.1 -- added avatar, old clients still work."""
            avatar_url: str | None = None
            phone: str | None = None
            preferences: dict[str, Any] = Field(default_factory=dict)

        return UserV1_1

    @staticmethod
    def polymorphic_responses():
        """Use discriminated unions for evolving response types."""

        class BaseNotification(BaseModel):
            id: str
            type: str
            message: str
            created_at: datetime

        class EmailNotification(BaseNotification):
            type: str = "email"
            subject: str
            recipient: str

        class PushNotification(BaseNotification):
            type: str = "push"
            device_token: str
            badge_count: int = 0

        # New types can be added without breaking existing clients
        class SMSNotification(BaseNotification):
            type: str = "sms"
            phone_number: str

        return EmailNotification, PushNotification, SMSNotification


# ── Deprecation Framework ─────────────────────────────────────

class DeprecationInfo(BaseModel):
    deprecated: bool = True
    sunset_date: str
    migration_guide: str
    replacement_endpoint: str | None = None


def deprecated_endpoint(
    sunset_date: str,
    replacement: str | None = None,
    message: str = "This endpoint is deprecated",
):
    """Decorator that adds deprecation headers to responses."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            response = await func(*args, **kwargs)

            # If it's a dict or Pydantic model, wrap in JSONResponse
            if isinstance(response, BaseModel):
                data = response.model_dump(mode="json")
            elif isinstance(response, dict):
                data = response
            else:
                return response

            json_response = JSONResponse(content=data)
            json_response.headers["Deprecation"] = "true"
            json_response.headers["Sunset"] = sunset_date
            json_response.headers["Link"] = (
                f'<{replacement}>; rel="successor-version"'
                if replacement else ""
            )
            json_response.headers["X-Deprecation-Notice"] = message
            return json_response

        wrapper._deprecated = DeprecationInfo(
            sunset_date=sunset_date,
            migration_guide=message,
            replacement_endpoint=replacement,
        )
        return wrapper
    return decorator


# ── Version Router with Auto-Documentation ────────────────────

class VersionedAPI:
    """Manages multiple API versions with lifecycle tracking."""

    def __init__(self, app: FastAPI):
        self.app = app
        self.versions: dict[int, APIRouter] = {}
        self.deprecations: dict[int, dict] = {}

    def version(
        self,
        number: int,
        deprecated: bool = False,
        sunset_date: str | None = None,
    ) -> APIRouter:
        router = APIRouter(
            prefix=f"/api/v{number}",
            tags=[f"v{number}"],
        )
        self.versions[number] = router

        if deprecated and sunset_date:
            self.deprecations[number] = {
                "deprecated": True,
                "sunset_date": sunset_date,
            }

        return router

    def mount_all(self) -> None:
        for version, router in sorted(self.versions.items()):
            self.app.include_router(router)

        # Auto-generate version discovery endpoint
        @self.app.get("/api/versions")
        async def list_versions():
            return {
                "versions": [
                    {
                        "version": v,
                        "url": f"/api/v{v}",
                        "status": (
                            "deprecated"
                            if v in self.deprecations
                            else "active"
                        ),
                        **(self.deprecations.get(v, {})),
                    }
                    for v in sorted(self.versions.keys())
                ],
                "latest": max(self.versions.keys()),
            }


# Usage
versioned = VersionedAPI(app)

v1 = versioned.version(1, deprecated=True, sunset_date="2026-06-01")
v2 = versioned.version(2)
v3 = versioned.version(3)

versioned.mount_all()


async def fetch_user(user_id: str) -> dict:
    """Stub for user fetching."""
    return {
        "id": user_id,
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com",
        "avatar_url": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
```

API versioning strategy comparison:

| Strategy | Discoverability | Caching | Simplicity | Client Impact |
|----------|----------------|---------|------------|---------------|
| URL Path (/v1/) | High | Easy | Highest | URL changes |
| Header (Accept-Version) | Low | Harder | Medium | Header management |
| Content-Type (vnd.api.v1+json) | Low | Complex | Lower | Accept header |
| Query Param (?version=1) | Medium | Varies | High | Query string |
| Additive (no versioning) | N/A | Easy | Highest | None |

Key patterns:
- Prefer additive changes (new optional fields) over breaking changes whenever possible
- URL path versioning is simplest and most widely adopted for public APIs
- Always set Deprecation, Sunset, and Link headers on deprecated endpoints
- Provide a /versions discovery endpoint listing all active and deprecated versions
- Support at least N-1 versions to give clients time to migrate
- Use the Sunset header (RFC 8594) with a concrete date for deprecation timelines
- Run both old and new versions in parallel during migration periods
'''
    ),
    (
        "api-design/pagination",
        "What are the different pagination patterns for APIs, and how do I implement cursor-based, offset-based, and keyset pagination with proper performance characteristics?",
        '''Pagination is critical for API performance. The right strategy depends on your dataset characteristics, client needs, and whether data changes during pagination. Here are all three approaches implemented and compared.

```python
"""Pagination strategies: offset, cursor, and keyset for FastAPI + PostgreSQL."""

from __future__ import annotations
import base64
import json
from datetime import datetime, timezone
from typing import Any, TypeVar, Generic
from dataclasses import dataclass

from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field
import asyncpg


app = FastAPI(title="Pagination Patterns")
T = TypeVar("T")


# ── Shared Response Models ─────────────────────────────────────

class PageMeta(BaseModel):
    total_count: int | None = None  # Not always available
    page_size: int
    has_next: bool
    has_previous: bool


class OffsetPageMeta(PageMeta):
    page: int
    total_pages: int


class CursorPageMeta(PageMeta):
    next_cursor: str | None = None
    prev_cursor: str | None = None


class PaginatedResponse(BaseModel):
    data: list[dict[str, Any]]
    meta: dict[str, Any]
    links: dict[str, str | None]


# ── Strategy 1: Offset-Based Pagination ────────────────────────

class OffsetPaginator:
    """Traditional offset/limit pagination.

    Pros: Simple, clients can jump to any page.
    Cons: Slow on large tables (OFFSET scans rows), inconsistent
          under concurrent writes (items can shift).
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def paginate(
        self,
        table: str,
        page: int = 1,
        page_size: int = 20,
        where: str = "",
        params: list[Any] | None = None,
        order_by: str = "created_at DESC",
    ) -> PaginatedResponse:
        params = params or []
        offset = (page - 1) * page_size

        async with self.pool.acquire() as conn:
            # Count total (expensive for large tables)
            count_sql = f"SELECT COUNT(*) FROM {table}"
            if where:
                count_sql += f" WHERE {where}"
            total = await conn.fetchval(count_sql, *params)

            # Fetch page
            data_sql = (
                f"SELECT * FROM {table}"
                f"{' WHERE ' + where if where else ''} "
                f"ORDER BY {order_by} "
                f"LIMIT ${ len(params) + 1} OFFSET ${len(params) + 2}"
            )
            rows = await conn.fetch(
                data_sql, *params, page_size, offset
            )

        total_pages = max(1, (total + page_size - 1) // page_size)
        base = f"/api/items?page_size={page_size}"

        return PaginatedResponse(
            data=[dict(r) for r in rows],
            meta=OffsetPageMeta(
                total_count=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ).model_dump(),
            links={
                "self": f"{base}&page={page}",
                "first": f"{base}&page=1",
                "last": f"{base}&page={total_pages}",
                "next": f"{base}&page={page+1}" if page < total_pages else None,
                "prev": f"{base}&page={page-1}" if page > 1 else None,
            },
        )


# ── Strategy 2: Cursor-Based Pagination ────────────────────────

class CursorPaginator:
    """Opaque cursor pagination (Relay-style).

    Pros: Stable under concurrent writes, consistent ordering.
    Cons: No random page access, cursor is opaque.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @staticmethod
    def encode_cursor(values: dict) -> str:
        raw = json.dumps(values, default=str, sort_keys=True)
        return base64.urlsafe_b64encode(raw.encode()).decode()

    @staticmethod
    def decode_cursor(cursor: str) -> dict:
        try:
            raw = base64.urlsafe_b64decode(cursor.encode()).decode()
            return json.loads(raw)
        except Exception:
            raise HTTPException(
                status_code=400, detail="Invalid cursor"
            )

    async def paginate(
        self,
        table: str,
        first: int = 20,
        after: str | None = None,
        before: str | None = None,
        order_field: str = "created_at",
        order_dir: str = "DESC",
        where: str = "",
        params: list[Any] | None = None,
    ) -> PaginatedResponse:
        params = params or []
        conditions = [where] if where else []
        idx = len(params) + 1

        if after:
            cursor_data = self.decode_cursor(after)
            cursor_val = cursor_data[order_field]
            cursor_id = cursor_data["id"]

            if order_dir == "DESC":
                conditions.append(
                    f"({order_field}, id) < (${idx}, ${idx+1})"
                )
            else:
                conditions.append(
                    f"({order_field}, id) > (${idx}, ${idx+1})"
                )
            params.extend([cursor_val, cursor_id])
            idx += 2

        where_clause = " AND ".join(conditions)
        if where_clause:
            where_clause = f"WHERE {where_clause}"

        # Fetch one extra to determine has_next
        fetch_limit = first + 1

        sql = (
            f"SELECT * FROM {table} {where_clause} "
            f"ORDER BY {order_field} {order_dir}, id {order_dir} "
            f"LIMIT ${idx}"
        )
        params.append(fetch_limit)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        has_next = len(rows) > first
        items = [dict(r) for r in rows[:first]]

        # Build cursors
        next_cursor = None
        if has_next and items:
            last = items[-1]
            next_cursor = self.encode_cursor({
                order_field: str(last[order_field]),
                "id": str(last["id"]),
            })

        prev_cursor = None
        if after and items:
            first_item = items[0]
            prev_cursor = self.encode_cursor({
                order_field: str(first_item[order_field]),
                "id": str(first_item["id"]),
            })

        return PaginatedResponse(
            data=items,
            meta=CursorPageMeta(
                page_size=first,
                has_next=has_next,
                has_previous=after is not None,
                next_cursor=next_cursor,
                prev_cursor=prev_cursor,
            ).model_dump(),
            links={
                "next": (
                    f"/api/items?first={first}&after={next_cursor}"
                    if next_cursor else None
                ),
                "prev": (
                    f"/api/items?first={first}&before={prev_cursor}"
                    if prev_cursor else None
                ),
            },
        )


# ── Strategy 3: Keyset Pagination ──────────────────────────────

class KeysetPaginator:
    """Keyset (seek) pagination using WHERE clause.

    Pros: O(1) performance regardless of page depth, stable.
    Cons: Requires a unique, sortable column (or composite).
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def paginate(
        self,
        table: str,
        page_size: int = 20,
        after_id: str | None = None,
        after_timestamp: str | None = None,
        direction: str = "next",
    ) -> PaginatedResponse:
        conditions = []
        params: list[Any] = []
        idx = 1

        if after_timestamp and after_id:
            if direction == "next":
                conditions.append(
                    f"(created_at, id) < (${idx}, ${idx+1})"
                )
            else:
                conditions.append(
                    f"(created_at, id) > (${idx}, ${idx+1})"
                )
            params.extend([after_timestamp, after_id])
            idx += 2

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        order = "DESC" if direction == "next" else "ASC"
        fetch_limit = page_size + 1

        sql = (
            f"SELECT * FROM {table} {where} "
            f"ORDER BY created_at {order}, id {order} "
            f"LIMIT ${idx}"
        )
        params.append(fetch_limit)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        # Reverse if going backwards
        items = [dict(r) for r in rows]
        if direction == "prev":
            items.reverse()

        has_more = len(items) > page_size
        items = items[:page_size]

        # Build next/prev keys
        links: dict[str, str | None] = {"next": None, "prev": None}
        if has_more and items:
            last = items[-1]
            links["next"] = (
                f"/api/items?page_size={page_size}"
                f"&after_id={last['id']}"
                f"&after_timestamp={last['created_at'].isoformat()}"
            )
        if items:
            first_item = items[0]
            links["prev"] = (
                f"/api/items?page_size={page_size}"
                f"&after_id={first_item['id']}"
                f"&after_timestamp={first_item['created_at'].isoformat()}"
                f"&direction=prev"
            )

        return PaginatedResponse(
            data=items,
            meta=PageMeta(
                page_size=page_size,
                has_next=has_more if direction == "next" else True,
                has_previous=after_id is not None,
            ).model_dump(),
            links=links,
        )


# ── API Routes ─────────────────────────────────────────────────

@app.get("/api/v1/items/offset")
async def list_items_offset(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    paginator = OffsetPaginator(app.state.pool)
    return await paginator.paginate("items", page, page_size)


@app.get("/api/v1/items/cursor")
async def list_items_cursor(
    first: int = Query(20, ge=1, le=100),
    after: str | None = None,
):
    paginator = CursorPaginator(app.state.pool)
    return await paginator.paginate("items", first=first, after=after)


@app.get("/api/v1/items/keyset")
async def list_items_keyset(
    page_size: int = Query(20, ge=1, le=100),
    after_id: str | None = None,
    after_timestamp: str | None = None,
    direction: str = "next",
):
    paginator = KeysetPaginator(app.state.pool)
    return await paginator.paginate(
        "items", page_size,
        after_id=after_id,
        after_timestamp=after_timestamp,
        direction=direction,
    )
```

Pagination strategy comparison:

| Strategy | Performance at Depth | Consistency | Random Access | Complexity |
|----------|---------------------|-------------|---------------|------------|
| Offset (LIMIT/OFFSET) | O(N) degrades | Unstable | Yes (any page) | Lowest |
| Cursor (opaque) | O(1) constant | Stable | No | Medium |
| Keyset (seek) | O(1) constant | Stable | No | Medium |
| Hybrid (offset + keyset) | O(1) for deep | Mostly stable | First pages | Highest |

When to use each:

| Scenario | Best Strategy |
|----------|---------------|
| Small datasets (<10K rows) | Offset |
| Social feeds, infinite scroll | Cursor |
| Analytics dashboards | Offset with count cache |
| Real-time data, high write rate | Keyset |
| Public APIs | Cursor (stable contract) |

Key patterns:
- Offset pagination: simple but degrades at deep pages -- OFFSET 1000000 scans all rows
- Cursor pagination: encode sort values into an opaque cursor for stable, O(1) pagination
- Keyset pagination: use WHERE (col, id) > (val, last_id) instead of OFFSET for constant time
- Always fetch N+1 rows to determine has_next without a separate COUNT query
- Include navigation links in every paginated response for discoverability
- Set a maximum page_size (e.g., 100) to prevent clients from requesting too much data
'''
    ),
]
