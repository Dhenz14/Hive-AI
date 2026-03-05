"""
Batch P4 — API Protocols: GraphQL, gRPC, REST, WebSocket, rate limiting.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. GraphQL Server Design ---
    (
        "graphql_server_design_strawberry",
        "Explain GraphQL server design in depth — schema-first vs code-first approaches, resolver "
        "architecture, DataLoader pattern for solving the N+1 query problem, real-time subscriptions, "
        "and how to build a production GraphQL API using Strawberry in Python with proper typing, "
        "authentication, pagination, and error handling.",
        """\
# GraphQL Server Design: Schema-First vs Code-First with Strawberry

## Why GraphQL Over REST?

GraphQL solves fundamental problems with REST APIs: **over-fetching** (getting 50 fields when
you need 3), **under-fetching** (needing 5 REST calls to assemble one view), and **API
versioning hell** (maintaining v1, v2, v3 endpoints). Instead of the server dictating response
shapes, the **client declares exactly what it needs**.

```
REST approach for a user profile page:
  GET /api/users/123          → { id, name, email, bio, avatar, ... 47 more fields }
  GET /api/users/123/posts    → [{ id, title, body, ... }]
  GET /api/users/123/followers → [{ id, name, ... }]
  = 3 round trips, massive over-fetching

GraphQL approach:
  POST /graphql
  query { user(id: 123) { name, avatar, posts(first: 5) { title }, followersCount } }
  = 1 round trip, exact data needed
```

However, GraphQL introduces its own **trade-offs**: caching is harder (no HTTP cache keys),
file uploads require workarounds, and the N+1 query problem is more severe because the
client controls traversal depth.

## Schema-First vs Code-First

There are two fundamental approaches to defining a GraphQL schema, and the choice has deep
implications for team workflow and type safety.

**Schema-first** (SDL-first) means writing the `.graphql` schema files by hand, then
generating or wiring resolvers to match. Tools like Apollo Server and Ariadne use this.
The **best practice** is schema-first when your schema is a contract between frontend and
backend teams — designers can review the schema without reading Python code.

**Code-first** means defining your schema in the host language (Python, TypeScript), and the
SDL is generated automatically. Strawberry, Graphene, and Nexus use this approach. The
advantage is **type safety** — because the schema is defined in Python with type hints, your
IDE catches errors that schema-first only catches at runtime.

```python
# Schema-first with Ariadne — schema and code are separate
# schema.graphql
"""
type User {
    id: ID!
    name: String!
    email: String!
    posts(first: Int = 10, after: String): PostConnection!
}

type Query {
    user(id: ID!): User
    users(filter: UserFilter): [User!]!
}
"""

# resolvers.py — must manually keep in sync with schema
# Common mistake: schema says `posts` returns PostConnection
# but resolver returns a plain list — silent runtime error
```

```python
# Code-first with Strawberry — schema IS the code
import strawberry
from typing import Optional
from datetime import datetime


@strawberry.type
class User:
    id: strawberry.ID
    name: str
    email: str
    created_at: datetime

    @strawberry.field
    async def posts(
        self,
        info: strawberry.types.Info,
        first: int = 10,
        after: Optional[str] = None,
    ) -> "PostConnection":
        """Fetch user's posts with cursor pagination."""
        loader = info.context["post_loader"]
        return await loader.load_posts_for_user(self.id, first, after)
```

The **common mistake** with code-first is treating it as "just define some classes." You must
still think carefully about your schema design — nullability, connections, input types — because
the code IS the contract.

## DataLoader: Solving the N+1 Problem

The N+1 problem is GraphQL's most critical **pitfall**. When a client queries a list of users
with their posts, a naive implementation makes 1 query for the user list, then N queries for
each user's posts. With 100 users, that is 101 database queries.

```python
from strawberry.dataloader import DataLoader
from typing import List, Dict
from collections import defaultdict

import strawberry
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


class PostLoader:
    """Batch loader that collapses N+1 queries into batch queries.

    The DataLoader pattern works by:
    1. Collecting all .load(key) calls within a single event loop tick
    2. Calling the batch function ONCE with all collected keys
    3. Returning results matched by key order

    Therefore, 100 users each requesting their posts results in
    exactly ONE query: SELECT * FROM posts WHERE user_id IN (...)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._loader = DataLoader(load_fn=self._batch_load_posts)

    async def _batch_load_posts(
        self, user_ids: List[strawberry.ID]
    ) -> List[List["Post"]]:
        # Single query for ALL requested user_ids
        stmt = select(PostModel).where(
            PostModel.user_id.in_([int(uid) for uid in user_ids])
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        # Group by user_id — MUST return results in same order as keys
        posts_by_user: Dict[int, List[Post]] = defaultdict(list)
        for row in rows:
            posts_by_user[row.user_id].append(
                Post(id=strawberry.ID(str(row.id)), title=row.title, body=row.body)
            )

        # Return in exact order of input keys
        return [posts_by_user.get(int(uid), []) for uid in user_ids]

    async def load(self, user_id: strawberry.ID) -> List["Post"]:
        return await self._loader.load(user_id)
```

**Best practice**: Create a new DataLoader instance **per request**, not globally. DataLoaders
cache results within a request, and reusing across requests means stale data. Strawberry's
context hook is the right place to create them.

## Production Server with Authentication and Pagination

```python
import strawberry
from strawberry.fastapi import GraphQLRouter
from strawberry.permission import BasePermission
from strawberry.types import Info
from typing import Optional, List, Generic, TypeVar
from datetime import datetime
from fastapi import FastAPI, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# --- Authentication Permission ---

class IsAuthenticated(BasePermission):
    message = "User is not authenticated"

    async def has_permission(
        self, source, info: Info, **kwargs
    ) -> bool:
        request: Request = info.context["request"]
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return False
        user = await verify_jwt_token(token)
        if user is None:
            return False
        info.context["current_user"] = user
        return True


# --- Cursor Pagination (Relay-style) ---

T = TypeVar("T")


@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str]
    end_cursor: Optional[str]


@strawberry.type
class Edge(Generic[T]):
    node: T
    cursor: str


@strawberry.type
class Connection(Generic[T]):
    edges: List[Edge[T]]
    page_info: PageInfo
    total_count: int


# --- Domain Types ---

@strawberry.type
class Post:
    id: strawberry.ID
    title: str
    body: str
    created_at: datetime
    author_id: strawberry.ID


@strawberry.type
class User:
    id: strawberry.ID
    name: str
    email: str
    created_at: datetime

    @strawberry.field
    async def posts(
        self, info: Info, first: int = 10, after: Optional[str] = None
    ) -> Connection[Post]:
        """Paginated posts using DataLoader + cursor pagination."""
        loader = info.context["post_loader"]
        return await loader.load_posts_for_user(self.id, first, after)


@strawberry.input
class CreateUserInput:
    name: str
    email: str
    password: str


@strawberry.type
class CreateUserPayload:
    user: Optional[User]
    errors: List[str]


# --- Query and Mutation ---

@strawberry.type
class Query:
    @strawberry.field(permission_classes=[IsAuthenticated])
    async def me(self, info: Info) -> User:
        """Return the currently authenticated user."""
        current_user = info.context["current_user"]
        return User(
            id=strawberry.ID(str(current_user.id)),
            name=current_user.name,
            email=current_user.email,
            created_at=current_user.created_at,
        )

    @strawberry.field
    async def user(self, info: Info, id: strawberry.ID) -> Optional[User]:
        """Fetch a single user by ID."""
        db: AsyncSession = info.context["db"]
        user_model = await db.get(UserModel, int(id))
        if user_model is None:
            return None
        return User(
            id=strawberry.ID(str(user_model.id)),
            name=user_model.name,
            email=user_model.email,
            created_at=user_model.created_at,
        )

    @strawberry.field
    async def users(
        self, info: Info, first: int = 20, after: Optional[str] = None
    ) -> Connection[User]:
        """Paginated list of all users."""
        db: AsyncSession = info.context["db"]
        return await paginate_query(
            db, select(UserModel), first, after, model_to_user
        )


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_user(
        self, info: Info, input: CreateUserInput
    ) -> CreateUserPayload:
        """Create a new user with validation."""
        db: AsyncSession = info.context["db"]
        errors: List[str] = []

        if len(input.name) < 2:
            errors.append("Name must be at least 2 characters")
        if "@" not in input.email:
            errors.append("Invalid email format")
        if len(input.password) < 8:
            errors.append("Password must be at least 8 characters")

        if errors:
            return CreateUserPayload(user=None, errors=errors)

        user_model = UserModel(
            name=input.name,
            email=input.email,
            password_hash=hash_password(input.password),
        )
        db.add(user_model)
        await db.commit()
        await db.refresh(user_model)

        return CreateUserPayload(
            user=User(
                id=strawberry.ID(str(user_model.id)),
                name=user_model.name,
                email=user_model.email,
                created_at=user_model.created_at,
            ),
            errors=[],
        )


# --- Subscriptions ---

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def post_created(
        self, info: Info, user_id: Optional[strawberry.ID] = None
    ):
        """Real-time subscription for new posts via async generator."""
        import asyncio

        pubsub = info.context["pubsub"]
        async for event in pubsub.subscribe("post_created"):
            post = event["post"]
            if user_id is None or post.author_id == user_id:
                yield post


# --- Application Wiring ---

engine = create_async_engine("postgresql+asyncpg://localhost/myapp", pool_size=20)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_context(request: Request) -> dict:
    """Create per-request context with fresh DataLoaders and DB session."""
    db = SessionLocal()
    return {
        "request": request,
        "db": db,
        "post_loader": PostLoader(db),
        "pubsub": get_pubsub_instance(),
    }


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
)

graphql_app = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI(title="GraphQL API")
app.include_router(graphql_app, prefix="/graphql")
```

## Testing GraphQL Resolvers

```python
import pytest
from strawberry.test import GraphQLTestClient
from httpx import AsyncClient


@pytest.fixture
async def test_client(app):
    """Create a test client with a test database session."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_query_user(test_client):
    query = """
        query GetUser($id: ID!) {
            user(id: $id) {
                id
                name
                email
                posts(first: 5) {
                    edges { node { title } }
                    pageInfo { hasNextPage }
                    totalCount
                }
            }
        }
    """
    response = await test_client.post(
        "/graphql",
        json={"query": query, "variables": {"id": "1"}},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user"]["name"] == "Alice"
    assert len(data["user"]["posts"]["edges"]) <= 5


@pytest.mark.asyncio
async def test_create_user_validation(test_client):
    mutation = """
        mutation CreateUser($input: CreateUserInput!) {
            createUser(input: $input) {
                user { id name }
                errors
            }
        }
    """
    response = await test_client.post(
        "/graphql",
        json={
            "query": mutation,
            "variables": {"input": {"name": "A", "email": "bad", "password": "short"}},
        },
    )
    data = response.json()["data"]["createUser"]
    assert data["user"] is None
    assert len(data["errors"]) >= 2  # name too short + password too short


@pytest.mark.asyncio
async def test_dataloader_batching(test_client, caplog):
    """Verify that DataLoader batches N+1 into a single query."""
    query = """
        query {
            users(first: 50) {
                edges {
                    node {
                        name
                        posts(first: 3) { edges { node { title } } }
                    }
                }
            }
        }
    """
    import logging
    with caplog.at_level(logging.DEBUG, logger="sqlalchemy.engine"):
        response = await test_client.post("/graphql", json={"query": query})

    assert response.status_code == 200
    # Count SQL queries — should be 2 (users + batched posts), not 51
    sql_queries = [r for r in caplog.records if "SELECT" in r.message]
    assert len(sql_queries) <= 3, f"N+1 detected: {len(sql_queries)} queries"
```

## Summary and Key Takeaways

**Schema-first vs code-first** is not a universal answer — use schema-first when the GraphQL
schema serves as a contract across teams (frontend/backend/mobile), and use code-first with
Strawberry when you want **compile-time type safety** and your Python types are the source of
truth. The common mistake is choosing based on preference rather than team structure.

**DataLoader is non-negotiable** in production GraphQL. Without it, a query traversing
relationships generates O(N*M) database queries. The best practice is one DataLoader instance
per request (to avoid cross-request caching), with batch functions that maintain key ordering.

**Subscriptions** use async generators in Strawberry, backed by a pub/sub system (Redis,
PostgreSQL LISTEN/NOTIFY, or in-memory for development). The trade-off is that WebSocket-based
subscriptions require sticky sessions or a shared pub/sub backend in multi-server deployments.

**Pagination** should always use Relay-style cursor pagination (Connection/Edge/PageInfo) rather
than offset-based pagination. Cursors are stable under inserts and perform better because the
database uses index seeks rather than offset scans. However, cursor pagination cannot support
"jump to page 47" — therefore, use offset pagination only when random page access is a hard
requirement from the product team.
"""
    ),
    # --- 2. gRPC Service Design ---
    (
        "grpc_service_design_python",
        "Explain gRPC service design in depth — protobuf schema design, the four streaming patterns "
        "(unary, server streaming, client streaming, bidirectional), interceptors for auth and "
        "logging, and how to build a production Python gRPC server with health checking, reflection, "
        "graceful shutdown, error handling, and comprehensive testing.",
        """\
# gRPC Service Design: High-Performance RPC with Protocol Buffers

## Why gRPC Over REST?

gRPC uses **HTTP/2** and **Protocol Buffers** to achieve performance that REST+JSON simply
cannot match. The key advantages are:

```
REST + JSON:
  - Text-based serialization (JSON): ~3-10x larger than binary
  - HTTP/1.1: one request per TCP connection (or limited pipelining)
  - No built-in streaming: requires WebSocket bolt-on
  - Schema is optional (OpenAPI): runtime errors

gRPC + Protobuf:
  - Binary serialization: 3-10x smaller, 5-100x faster to parse
  - HTTP/2 multiplexing: many requests over one TCP connection
  - Built-in streaming: server, client, and bidirectional
  - Schema is mandatory (.proto): compile-time type safety
```

However, gRPC has **trade-offs**: it is harder to debug (binary protocol), browser support
requires grpc-web proxy, and the tooling ecosystem is smaller than REST. The **best practice**
is gRPC for internal service-to-service communication and REST/GraphQL for external APIs.

## Protobuf Schema Design

```protobuf
// service.proto — the single source of truth for your API contract
syntax = "proto3";

package orderservice.v1;

option go_package = "github.com/myorg/orderservice/v1;orderservicev1";
option java_package = "com.myorg.orderservice.v1";

import "google/protobuf/timestamp.proto";
import "google/protobuf/field_mask.proto";
import "google/protobuf/empty.proto";

// --- Domain Messages ---

enum OrderStatus {
    ORDER_STATUS_UNSPECIFIED = 0;  // Always have UNSPECIFIED as 0
    ORDER_STATUS_PENDING = 1;
    ORDER_STATUS_CONFIRMED = 2;
    ORDER_STATUS_SHIPPED = 3;
    ORDER_STATUS_DELIVERED = 4;
    ORDER_STATUS_CANCELLED = 5;
}

message Address {
    string street = 1;
    string city = 2;
    string state = 3;
    string zip_code = 4;
    string country = 5;
}

message OrderItem {
    string product_id = 1;
    string product_name = 2;
    int32 quantity = 3;
    // Use integer cents to avoid floating point — common mistake is using float
    int64 price_cents = 4;
}

message Order {
    string id = 1;
    string customer_id = 2;
    repeated OrderItem items = 3;
    OrderStatus status = 4;
    Address shipping_address = 5;
    int64 total_cents = 6;
    google.protobuf.Timestamp created_at = 7;
    google.protobuf.Timestamp updated_at = 8;
    map<string, string> metadata = 9;  // Extensible key-value pairs
}

// --- Request/Response Messages ---
// Best practice: dedicated request/response per RPC, never reuse domain objects

message CreateOrderRequest {
    string customer_id = 1;
    repeated OrderItem items = 2;
    Address shipping_address = 3;
    map<string, string> metadata = 4;
    // Idempotency key prevents duplicate orders on retry
    string idempotency_key = 5;
}

message CreateOrderResponse {
    Order order = 1;
}

message GetOrderRequest {
    string order_id = 1;
}

message GetOrderResponse {
    Order order = 1;
}

message ListOrdersRequest {
    string customer_id = 1;
    int32 page_size = 2;
    string page_token = 3;  // Cursor for pagination
    OrderStatus status_filter = 4;
}

message ListOrdersResponse {
    repeated Order orders = 1;
    string next_page_token = 2;
    int32 total_count = 3;
}

message UpdateOrderRequest {
    Order order = 1;
    google.protobuf.FieldMask update_mask = 2;  // Partial updates
}

message OrderEvent {
    string order_id = 1;
    OrderStatus old_status = 2;
    OrderStatus new_status = 3;
    google.protobuf.Timestamp timestamp = 4;
    string reason = 5;
}

// --- Service Definition with all four streaming patterns ---

service OrderService {
    // Unary: single request, single response
    rpc CreateOrder(CreateOrderRequest) returns (CreateOrderResponse);
    rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);

    // Server streaming: single request, stream of responses
    // Use case: watch order status changes in real time
    rpc WatchOrder(GetOrderRequest) returns (stream OrderEvent);

    // Client streaming: stream of requests, single response
    // Use case: bulk import orders from CSV upload
    rpc BulkCreateOrders(stream CreateOrderRequest) returns (ListOrdersResponse);

    // Bidirectional streaming: both sides stream simultaneously
    // Use case: real-time order processing pipeline
    rpc ProcessOrders(stream CreateOrderRequest) returns (stream OrderEvent);
}
```

## Python gRPC Server Implementation

```python
"""Production gRPC server with health checking, reflection, and interceptors."""

import asyncio
import logging
import signal
import time
import uuid
from typing import AsyncIterator, Optional
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

# Generated from protobuf — run: python -m grpc_tools.protoc ...
import order_service_pb2 as pb2
import order_service_pb2_grpc as pb2_grpc

from google.protobuf.timestamp_pb2 import Timestamp

logger = logging.getLogger(__name__)


class OrderServicer(pb2_grpc.OrderServiceServicer):
    """Implementation of the OrderService gRPC service.

    Each RPC method corresponds to a service definition in the .proto file.
    The servicer handles business logic and delegates to a repository layer
    for persistence.
    """

    def __init__(self, repository, event_bus):
        self.repo = repository
        self.event_bus = event_bus

    async def CreateOrder(
        self,
        request: pb2.CreateOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb2.CreateOrderResponse:
        """Unary RPC: create a single order with idempotency."""
        # Check idempotency key to prevent duplicate orders
        if request.idempotency_key:
            existing = await self.repo.get_by_idempotency_key(
                request.idempotency_key
            )
            if existing:
                return pb2.CreateOrderResponse(order=existing.to_proto())

        # Validate request
        if not request.items:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Order must contain at least one item",
            )

        if not request.shipping_address.street:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Shipping address is required",
            )

        # Calculate total
        total_cents = sum(
            item.price_cents * item.quantity for item in request.items
        )

        order = await self.repo.create(
            customer_id=request.customer_id,
            items=list(request.items),
            shipping_address=request.shipping_address,
            total_cents=total_cents,
            metadata=dict(request.metadata),
            idempotency_key=request.idempotency_key,
        )

        # Publish event for subscribers
        await self.event_bus.publish("order_created", order)

        # Set response metadata
        await context.send_initial_metadata([
            ("x-order-id", order.id),
            ("x-request-id", str(uuid.uuid4())),
        ])

        return pb2.CreateOrderResponse(order=order.to_proto())

    async def WatchOrder(
        self,
        request: pb2.GetOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[pb2.OrderEvent]:
        """Server streaming RPC: yield order events as they occur."""
        order = await self.repo.get(request.order_id)
        if order is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Order {request.order_id} not found",
            )

        # Subscribe to events for this specific order
        async for event in self.event_bus.subscribe(
            f"order:{request.order_id}"
        ):
            if context.cancelled():
                logger.info(f"Client cancelled watch for {request.order_id}")
                break
            yield event.to_proto()

    async def BulkCreateOrders(
        self,
        request_iterator: AsyncIterator[pb2.CreateOrderRequest],
        context: grpc.aio.ServicerContext,
    ) -> pb2.ListOrdersResponse:
        """Client streaming RPC: receive stream of orders, return summary."""
        orders = []
        error_count = 0

        async for request in request_iterator:
            try:
                total_cents = sum(
                    item.price_cents * item.quantity for item in request.items
                )
                order = await self.repo.create(
                    customer_id=request.customer_id,
                    items=list(request.items),
                    shipping_address=request.shipping_address,
                    total_cents=total_cents,
                    metadata=dict(request.metadata),
                    idempotency_key=request.idempotency_key,
                )
                orders.append(order)
            except Exception as e:
                logger.warning(f"Failed to create order: {e}")
                error_count += 1

        return pb2.ListOrdersResponse(
            orders=[o.to_proto() for o in orders],
            total_count=len(orders),
        )

    async def ProcessOrders(
        self,
        request_iterator: AsyncIterator[pb2.CreateOrderRequest],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[pb2.OrderEvent]:
        """Bidirectional streaming: process orders and yield events live."""
        async for request in request_iterator:
            if context.cancelled():
                break
            try:
                total_cents = sum(
                    item.price_cents * item.quantity for item in request.items
                )
                order = await self.repo.create(
                    customer_id=request.customer_id,
                    items=list(request.items),
                    shipping_address=request.shipping_address,
                    total_cents=total_cents,
                    metadata=dict(request.metadata),
                    idempotency_key=request.idempotency_key,
                )
                # Yield creation event immediately
                ts = Timestamp()
                ts.GetCurrentTime()
                yield pb2.OrderEvent(
                    order_id=order.id,
                    old_status=pb2.ORDER_STATUS_UNSPECIFIED,
                    new_status=pb2.ORDER_STATUS_PENDING,
                    timestamp=ts,
                    reason="Order created via bulk processing",
                )
            except Exception as e:
                logger.error(f"ProcessOrders error: {e}")
                await context.send_initial_metadata([
                    ("x-error", str(e)),
                ])
```

## Interceptors for Authentication and Logging

```python
import time
import grpc
from typing import Callable, Any


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """Server interceptor that validates JWT tokens on every request.

    Interceptors are the gRPC equivalent of middleware — they wrap every
    RPC call. This is the best practice for cross-cutting concerns like
    auth, logging, and metrics because it keeps business logic clean.
    """

    OPEN_METHODS = {
        "/grpc.health.v1.Health/Check",
        "/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo",
    }

    def __init__(self, auth_service):
        self.auth_service = auth_service

    async def intercept_service(
        self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails
    ) -> Any:
        method = handler_call_details.method

        # Skip auth for health checks and reflection
        if method in self.OPEN_METHODS:
            return await continuation(handler_call_details)

        # Extract token from metadata
        metadata = dict(handler_call_details.invocation_metadata or [])
        token = metadata.get("authorization", "").replace("Bearer ", "")

        if not token:
            raise grpc.aio.AbortError(
                grpc.StatusCode.UNAUTHENTICATED,
                "Missing authorization token",
            )

        user = await self.auth_service.verify_token(token)
        if user is None:
            raise grpc.aio.AbortError(
                grpc.StatusCode.UNAUTHENTICATED,
                "Invalid or expired token",
            )

        # Attach user to context for downstream use
        handler_call_details.invocation_metadata.append(
            ("x-user-id", str(user.id))
        )

        return await continuation(handler_call_details)


class LoggingInterceptor(grpc.aio.ServerInterceptor):
    """Logs every RPC with method name, duration, and status code."""

    async def intercept_service(
        self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails
    ) -> Any:
        method = handler_call_details.method
        start_time = time.perf_counter()

        try:
            response = await continuation(handler_call_details)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"gRPC OK | {method} | {duration_ms:.1f}ms"
            )
            return response
        except grpc.aio.AbortError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                f"gRPC ERROR | {method} | {duration_ms:.1f}ms | {e.code()}: {e.details()}"
            )
            raise


class MetricsInterceptor(grpc.aio.ServerInterceptor):
    """Collects Prometheus metrics for each RPC call."""

    def __init__(self):
        from prometheus_client import Counter, Histogram

        self.request_count = Counter(
            "grpc_requests_total",
            "Total gRPC requests",
            ["method", "status"],
        )
        self.request_duration = Histogram(
            "grpc_request_duration_seconds",
            "gRPC request duration",
            ["method"],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0],
        )

    async def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method
        start = time.perf_counter()
        try:
            response = await continuation(handler_call_details)
            self.request_count.labels(method=method, status="OK").inc()
            return response
        except grpc.aio.AbortError as e:
            self.request_count.labels(method=method, status=e.code().name).inc()
            raise
        finally:
            self.request_duration.labels(method=method).observe(
                time.perf_counter() - start
            )
```

## Server Bootstrap with Health Checking and Reflection

```python
async def serve(port: int = 50051) -> None:
    """Start the gRPC server with health checking, reflection, and graceful shutdown."""
    # Create interceptor chain — order matters
    auth_svc = AuthService()
    interceptors = [
        MetricsInterceptor(),
        LoggingInterceptor(),
        AuthInterceptor(auth_svc),
    ]

    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=interceptors,
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),   # 50MB
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", True),
        ],
    )

    # Register service
    repo = OrderRepository()
    event_bus = EventBus()
    pb2_grpc.add_OrderServiceServicer_to_server(
        OrderServicer(repo, event_bus), server
    )

    # Health checking — required for Kubernetes readiness probes
    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    await health_servicer.set(
        "orderservice.v1.OrderService",
        health_pb2.HealthCheckResponse.SERVING,
    )

    # Reflection — allows grpcurl and other tools to discover services
    SERVICE_NAMES = (
        pb2.DESCRIPTOR.services_by_name["OrderService"].full_name,
        reflection.SERVICE_NAME,
        health.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await server.start()

    # Graceful shutdown on SIGTERM/SIGINT
    async def shutdown(sig):
        logger.info(f"Received {sig}, shutting down gracefully...")
        await health_servicer.set(
            "orderservice.v1.OrderService",
            health_pb2.HealthCheckResponse.NOT_SERVING,
        )
        # Grace period: stop accepting new requests, finish in-flight
        await server.stop(grace=30)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(s))
        )

    await server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
```

## Testing gRPC Services

```python
import pytest
import grpc
from grpc import aio as grpc_aio

import order_service_pb2 as pb2
import order_service_pb2_grpc as pb2_grpc


@pytest.fixture
async def grpc_channel():
    """Create an in-process gRPC channel for testing."""
    server = grpc_aio.server()
    repo = InMemoryOrderRepository()
    event_bus = InMemoryEventBus()
    pb2_grpc.add_OrderServiceServicer_to_server(
        OrderServicer(repo, event_bus), server
    )
    port = server.add_insecure_port("[::]:0")  # Random available port
    await server.start()

    channel = grpc_aio.insecure_channel(f"localhost:{port}")
    yield channel

    await channel.close()
    await server.stop(0)


@pytest.fixture
def stub(grpc_channel):
    return pb2_grpc.OrderServiceStub(grpc_channel)


@pytest.mark.asyncio
async def test_create_order(stub):
    """Test unary RPC for order creation."""
    request = pb2.CreateOrderRequest(
        customer_id="cust-1",
        items=[
            pb2.OrderItem(
                product_id="prod-1",
                product_name="Widget",
                quantity=2,
                price_cents=1999,
            )
        ],
        shipping_address=pb2.Address(
            street="123 Main St", city="Springfield", state="IL",
            zip_code="62701", country="US",
        ),
        idempotency_key="test-key-1",
    )
    response = await stub.CreateOrder(request)
    assert response.order.id
    assert response.order.total_cents == 3998
    assert response.order.status == pb2.ORDER_STATUS_PENDING


@pytest.mark.asyncio
async def test_idempotency(stub):
    """Verify that duplicate idempotency keys return the same order."""
    request = pb2.CreateOrderRequest(
        customer_id="cust-1",
        items=[pb2.OrderItem(product_id="p1", product_name="X", quantity=1, price_cents=100)],
        shipping_address=pb2.Address(street="1 St", city="C", state="S", zip_code="0", country="US"),
        idempotency_key="dup-key",
    )
    resp1 = await stub.CreateOrder(request)
    resp2 = await stub.CreateOrder(request)
    assert resp1.order.id == resp2.order.id  # Same order returned


@pytest.mark.asyncio
async def test_server_streaming(stub):
    """Test server streaming RPC for order watching."""
    # Create an order first
    create_req = pb2.CreateOrderRequest(
        customer_id="cust-2",
        items=[pb2.OrderItem(product_id="p1", product_name="X", quantity=1, price_cents=500)],
        shipping_address=pb2.Address(street="1 St", city="C", state="S", zip_code="0", country="US"),
    )
    order_resp = await stub.CreateOrder(create_req)
    order_id = order_resp.order.id

    # Watch for events — read first event with timeout
    watch_req = pb2.GetOrderRequest(order_id=order_id)
    call = stub.WatchOrder(watch_req)
    # Cancel after first event in test
    call.cancel()


@pytest.mark.asyncio
async def test_invalid_request(stub):
    """Test error handling for invalid requests."""
    request = pb2.CreateOrderRequest(
        customer_id="cust-1",
        items=[],  # Empty items — should fail
        shipping_address=pb2.Address(street="1 St", city="C", state="S", zip_code="0", country="US"),
    )
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.CreateOrder(request)
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
```

## Summary and Key Takeaways

**Protobuf schema design** is the foundation of a good gRPC service. The best practice is
to use dedicated request/response messages per RPC (never reuse domain messages as requests),
always start enums with `UNSPECIFIED = 0`, use `int64` cents for money (not `float`), and
include `FieldMask` for partial updates. A common mistake is using `float` or `double` for
currency, which causes rounding errors that compound across transactions.

**The four streaming patterns** serve distinct use cases: unary for simple request-response,
server streaming for real-time feeds and event watching, client streaming for bulk uploads,
and bidirectional streaming for interactive pipelines. The trade-off with streaming is
complexity — you must handle cancellation, backpressure, and partial failures that do not
exist in unary calls.

**Interceptors** are the gRPC equivalent of middleware and should handle all cross-cutting
concerns (auth, logging, metrics, tracing). Because interceptors form a chain, order matters:
metrics should be outermost (to capture all requests including auth failures), then logging,
then auth. The pitfall is putting auth logic in individual RPCs, which leads to inconsistent
enforcement and security gaps.

**Health checking and reflection** are essential for production. Kubernetes uses gRPC health
checks for readiness probes, and reflection enables `grpcurl` for debugging. However, the
common mistake is forgetting to update the health status to `NOT_SERVING` during graceful
shutdown, causing the load balancer to continue routing traffic to a shutting-down server.
Therefore, always set NOT_SERVING before calling `server.stop()` with a grace period.
"""
    ),
    # --- 3. REST API Design Best Practices ---
    (
        "rest_api_design_fastapi",
        "Explain REST API design best practices in depth — HATEOAS and hypermedia controls, "
        "versioning strategies (URL path vs header vs query parameter), pagination approaches "
        "(cursor-based vs offset-based), filtering and sorting, standardized error responses "
        "(RFC 7807), OpenAPI specification, and a complete FastAPI implementation demonstrating "
        "all these patterns with proper validation and testing.",
        """\
# REST API Design Best Practices: From Theory to FastAPI Implementation

## The REST Maturity Model

Most APIs that call themselves "REST" are actually just HTTP-based RPC. Leonard Richardson's
maturity model defines four levels:

```
Level 0: Single endpoint, POST everything (SOAP, XML-RPC)
Level 1: Resources with unique URIs (/users/123, /orders/456)
Level 2: HTTP verbs used correctly (GET reads, POST creates, PUT replaces, PATCH updates)
Level 3: HATEOAS — responses include links to related actions and resources
```

Most production APIs are Level 2. Level 3 (HATEOAS) is controversial — the **trade-off** is
that it makes APIs self-discoverable and evolvable (clients follow links instead of
hardcoding URLs), but it adds payload size and implementation complexity. The **best practice**
is to implement HATEOAS for public APIs that evolve independently from clients, and skip it
for internal microservice APIs where tight coupling is acceptable.

## HATEOAS: Hypermedia as the Engine of Application State

```json
{
    "id": "ord-123",
    "status": "confirmed",
    "total_cents": 4999,
    "items": [{"product_id": "prod-1", "quantity": 2}],
    "_links": {
        "self": {"href": "/api/v1/orders/ord-123"},
        "cancel": {"href": "/api/v1/orders/ord-123/cancel", "method": "POST"},
        "items": {"href": "/api/v1/orders/ord-123/items"},
        "customer": {"href": "/api/v1/customers/cust-456"},
        "invoice": {"href": "/api/v1/orders/ord-123/invoice", "type": "application/pdf"}
    },
    "_embedded": {
        "shipping": {
            "carrier": "FedEx",
            "tracking_number": "789012",
            "_links": {
                "track": {"href": "https://fedex.com/track/789012"}
            }
        }
    }
}
```

The key insight is that the **links change based on state**. A shipped order would NOT include
a `cancel` link because cancellation is no longer valid. This means the client never needs to
hardcode business rules about which operations are available — it reads them from the response.

## Versioning Strategies

```
1. URL Path Versioning (most common):
   /api/v1/users  →  /api/v2/users
   Pros: Obvious, cache-friendly, easy to route
   Cons: Not really "RESTful" (same resource, different URIs)

2. Header Versioning:
   Accept: application/vnd.myapi.v2+json
   Pros: Clean URIs, semantically correct
   Cons: Harder to test (curl requires custom headers), invisible in logs

3. Query Parameter:
   /api/users?version=2
   Pros: Easy to use, visible
   Cons: Pollutes query string, optional versions cause ambiguity

Best practice: URL path versioning for public APIs (simplicity wins),
header versioning for internal APIs where clients are controlled.
Common mistake: versioning individual endpoints instead of the entire API.
```

## Pagination: Cursor vs Offset

```
Offset-based:  GET /api/v1/users?offset=100&limit=20
  SQL: SELECT * FROM users ORDER BY id LIMIT 20 OFFSET 100
  Pros: Simple, supports "jump to page N"
  Cons: O(offset) cost, inconsistent with concurrent inserts/deletes
  Pitfall: offset=1000000 scans 1M rows to skip them

Cursor-based:  GET /api/v1/users?after=usr_abc123&limit=20
  SQL: SELECT * FROM users WHERE id > 'usr_abc123' ORDER BY id LIMIT 20
  Pros: O(1) seek via index, stable under concurrent modifications
  Cons: Cannot jump to page N, cursor must encode sort order
  Best practice: Use for feeds, timelines, any dataset with frequent writes
```

## Complete FastAPI Implementation

```python
"""Production REST API with HATEOAS, versioning, pagination, and RFC 7807 errors."""

from __future__ import annotations

import math
import base64
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, List, Optional, TypeVar
from uuid import uuid4

from fastapi import FastAPI, Query, Path, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr, field_validator


# --- RFC 7807 Problem Details Error Response ---

class ProblemDetail(BaseModel):
    """RFC 7807 standardized error response.

    This format is the best practice for REST API errors because it
    provides machine-readable error types (URIs), human-readable detail,
    and extensible fields for validation errors.
    """
    type: str = Field(
        default="about:blank",
        description="URI identifying the problem type",
    )
    title: str = Field(description="Short human-readable summary")
    status: int = Field(description="HTTP status code")
    detail: str = Field(description="Human-readable explanation")
    instance: Optional[str] = Field(
        default=None, description="URI of the specific occurrence"
    )
    errors: Optional[List[dict]] = Field(
        default=None, description="Validation errors for 422 responses"
    )


class ProblemDetailException(Exception):
    """Raise this to return RFC 7807 error responses."""

    def __init__(self, status_code: int, title: str, detail: str, **kwargs):
        self.status_code = status_code
        self.body = ProblemDetail(
            type=f"https://api.example.com/problems/{title.lower().replace(' ', '-')}",
            title=title,
            status=status_code,
            detail=detail,
            **kwargs,
        )


# --- HATEOAS Link Models ---

class Link(BaseModel):
    href: str
    method: str = "GET"
    type: str = "application/json"


class HATEOASMixin(BaseModel):
    links: dict[str, Link] = Field(default_factory=dict, alias="_links")

    model_config = {"populate_by_name": True}


# --- Cursor Pagination ---

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response with cursor navigation and HATEOAS links."""
    data: List[T]
    pagination: dict = Field(description="Pagination metadata")
    _links: dict[str, Link] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        limit: int,
        cursor: Optional[str],
        request: Request,
        resource_path: str,
    ) -> "PaginatedResponse[T]":
        has_next = len(items) > limit
        display_items = items[:limit]

        next_cursor = None
        if has_next and display_items:
            last_item = display_items[-1]
            cursor_data = {"id": getattr(last_item, "id", str(len(display_items)))}
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(cursor_data).encode()
            ).decode()

        base_url = str(request.base_url).rstrip("/")
        links = {
            "self": Link(href=f"{base_url}{resource_path}?limit={limit}"),
        }
        if next_cursor:
            links["next"] = Link(
                href=f"{base_url}{resource_path}?limit={limit}&after={next_cursor}"
            )
        if cursor:
            links["first"] = Link(href=f"{base_url}{resource_path}?limit={limit}")

        return cls(
            data=display_items,
            pagination={
                "total": total,
                "limit": limit,
                "has_next": has_next,
                "next_cursor": next_cursor,
            },
            _links=links,
        )


# --- Domain Models ---

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItemCreate(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: int = Field(gt=0, le=1000)
    price_cents: int = Field(gt=0)


class OrderCreate(BaseModel):
    customer_id: str = Field(min_length=1)
    items: List[OrderItemCreate] = Field(min_length=1)
    shipping_address: str = Field(min_length=5)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("items")
    @classmethod
    def validate_items(cls, v):
        if len(v) > 100:
            raise ValueError("Maximum 100 items per order")
        return v


class OrderUpdate(BaseModel):
    """Partial update — all fields optional."""
    shipping_address: Optional[str] = Field(default=None, min_length=5)
    metadata: Optional[dict[str, str]] = None


class OrderResponse(BaseModel):
    id: str
    customer_id: str
    items: List[OrderItemCreate]
    status: OrderStatus
    total_cents: int
    shipping_address: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)
    _links: dict[str, Link] = Field(default_factory=dict)

    def with_links(self, base_url: str) -> "OrderResponse":
        """Add HATEOAS links based on current order state."""
        self._links = {
            "self": Link(href=f"{base_url}/api/v1/orders/{self.id}"),
            "items": Link(href=f"{base_url}/api/v1/orders/{self.id}/items"),
            "customer": Link(href=f"{base_url}/api/v1/customers/{self.customer_id}"),
        }

        # State-dependent links — the key HATEOAS pattern
        if self.status == OrderStatus.PENDING:
            self._links["confirm"] = Link(
                href=f"{base_url}/api/v1/orders/{self.id}/confirm",
                method="POST",
            )
            self._links["cancel"] = Link(
                href=f"{base_url}/api/v1/orders/{self.id}/cancel",
                method="POST",
            )
        elif self.status == OrderStatus.CONFIRMED:
            self._links["ship"] = Link(
                href=f"{base_url}/api/v1/orders/{self.id}/ship",
                method="POST",
            )
            self._links["cancel"] = Link(
                href=f"{base_url}/api/v1/orders/{self.id}/cancel",
                method="POST",
            )
        elif self.status == OrderStatus.SHIPPED:
            self._links["track"] = Link(
                href=f"{base_url}/api/v1/orders/{self.id}/tracking",
            )

        return self

    model_config = {"populate_by_name": True}
```

## API Routes with Filtering and Sorting

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["orders"])


class OrderSortField(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    TOTAL = "total_cents"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


@router.get("/orders", response_model=PaginatedResponse[OrderResponse])
async def list_orders(
    request: Request,
    # Cursor pagination
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    after: Optional[str] = Query(default=None, description="Cursor for next page"),
    # Filtering
    status: Optional[OrderStatus] = Query(default=None, description="Filter by status"),
    customer_id: Optional[str] = Query(default=None, description="Filter by customer"),
    min_total: Optional[int] = Query(default=None, ge=0, description="Min total in cents"),
    max_total: Optional[int] = Query(default=None, ge=0, description="Max total in cents"),
    created_after: Optional[datetime] = Query(default=None, description="Filter by date"),
    # Sorting
    sort_by: OrderSortField = Query(default=OrderSortField.CREATED_AT),
    sort_order: SortOrder = Query(default=SortOrder.DESC),
    # Dependencies
    db: AsyncSession = Depends(get_db),
):
    """List orders with cursor pagination, filtering, and sorting.

    Supports multiple filter parameters that are AND-combined.
    Cursor pagination is stable under concurrent writes.
    """
    # Decode cursor
    cursor_data = None
    if after:
        try:
            cursor_data = json.loads(base64.urlsafe_b64decode(after))
        except Exception:
            raise ProblemDetailException(
                status_code=400,
                title="Invalid Cursor",
                detail="The 'after' cursor is malformed or expired",
            )

    # Build query with filters
    query = select(OrderModel)

    if status:
        query = query.where(OrderModel.status == status.value)
    if customer_id:
        query = query.where(OrderModel.customer_id == customer_id)
    if min_total is not None:
        query = query.where(OrderModel.total_cents >= min_total)
    if max_total is not None:
        query = query.where(OrderModel.total_cents <= max_total)
    if created_after:
        query = query.where(OrderModel.created_at >= created_after)

    # Apply cursor (seek-based pagination)
    if cursor_data:
        query = query.where(OrderModel.id > cursor_data["id"])

    # Count total (without cursor/limit)
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Apply sorting and limit
    sort_col = getattr(OrderModel, sort_by.value)
    if sort_order == SortOrder.DESC:
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    query = query.limit(limit + 1)  # +1 to detect next page

    result = await db.execute(query)
    orders = result.scalars().all()

    base_url = str(request.base_url).rstrip("/")
    items = [
        OrderResponse.model_validate(o).with_links(base_url)
        for o in orders
    ]

    return PaginatedResponse.create(
        items=items,
        total=total,
        limit=limit,
        cursor=after,
        request=request,
        resource_path="/api/v1/orders",
    )


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    request: Request,
    body: OrderCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new order. Returns 201 with Location header."""
    total_cents = sum(item.price_cents * item.quantity for item in body.items)

    order = OrderModel(
        id=f"ord-{uuid4().hex[:12]}",
        customer_id=body.customer_id,
        items=[item.model_dump() for item in body.items],
        status=OrderStatus.PENDING.value,
        total_cents=total_cents,
        shipping_address=body.shipping_address,
        metadata=body.metadata,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    base_url = str(request.base_url).rstrip("/")
    response_data = OrderResponse.model_validate(order).with_links(base_url)

    response = JSONResponse(
        content=response_data.model_dump(by_alias=True),
        status_code=201,
        headers={"Location": f"/api/v1/orders/{order.id}"},
    )
    return response


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    request: Request,
    order_id: str = Path(description="Order ID"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single order with HATEOAS links."""
    order = await db.get(OrderModel, order_id)
    if not order:
        raise ProblemDetailException(
            status_code=404,
            title="Order Not Found",
            detail=f"No order exists with ID '{order_id}'",
            instance=f"/api/v1/orders/{order_id}",
        )
    base_url = str(request.base_url).rstrip("/")
    return OrderResponse.model_validate(order).with_links(base_url)


@router.patch("/orders/{order_id}", response_model=OrderResponse)
async def update_order(
    request: Request,
    body: OrderUpdate,
    order_id: str = Path(description="Order ID"),
    db: AsyncSession = Depends(get_db),
):
    """Partial update using PATCH — only provided fields are updated."""
    order = await db.get(OrderModel, order_id)
    if not order:
        raise ProblemDetailException(
            status_code=404,
            title="Order Not Found",
            detail=f"No order exists with ID '{order_id}'",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(order, field, value)

    order.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)

    base_url = str(request.base_url).rstrip("/")
    return OrderResponse.model_validate(order).with_links(base_url)
```

## Application Wiring and Error Handlers

```python
app = FastAPI(
    title="Order Service API",
    version="1.0.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ProblemDetailException)
async def problem_detail_handler(request: Request, exc: ProblemDetailException):
    """Return RFC 7807 Problem Detail JSON for all errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


@app.exception_handler(422)
async def validation_error_handler(request: Request, exc):
    """Convert Pydantic validation errors to RFC 7807 format."""
    return JSONResponse(
        status_code=422,
        content=ProblemDetail(
            type="https://api.example.com/problems/validation-error",
            title="Validation Error",
            status=422,
            detail="Request body failed validation",
            errors=[
                {"field": e["loc"][-1], "message": e["msg"]}
                for e in exc.errors()
            ],
        ).model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


app.include_router(router)
```

## Testing REST Endpoints

```python
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_order(client):
    response = await client.post("/api/v1/orders", json={
        "customer_id": "cust-1",
        "items": [{"product_id": "p1", "quantity": 2, "price_cents": 1999}],
        "shipping_address": "123 Main St, Springfield, IL 62701",
    })
    assert response.status_code == 201
    assert "Location" in response.headers
    data = response.json()
    assert data["total_cents"] == 3998
    assert data["status"] == "pending"
    # HATEOAS: pending order should have confirm and cancel links
    assert "confirm" in data["_links"]
    assert "cancel" in data["_links"]


@pytest.mark.asyncio
async def test_cursor_pagination(client):
    # Create 25 orders
    for i in range(25):
        await client.post("/api/v1/orders", json={
            "customer_id": "cust-1",
            "items": [{"product_id": f"p{i}", "quantity": 1, "price_cents": 100}],
            "shipping_address": "123 Main St, Springfield, IL 62701",
        })

    # First page
    resp1 = await client.get("/api/v1/orders?limit=10")
    assert resp1.status_code == 200
    page1 = resp1.json()
    assert len(page1["data"]) == 10
    assert page1["pagination"]["has_next"] is True

    # Second page via cursor
    next_cursor = page1["pagination"]["next_cursor"]
    resp2 = await client.get(f"/api/v1/orders?limit=10&after={next_cursor}")
    page2 = resp2.json()
    assert len(page2["data"]) == 10

    # Verify no overlap between pages
    ids_page1 = {o["id"] for o in page1["data"]}
    ids_page2 = {o["id"] for o in page2["data"]}
    assert ids_page1.isdisjoint(ids_page2)


@pytest.mark.asyncio
async def test_rfc7807_error(client):
    response = await client.get("/api/v1/orders/nonexistent")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    data = response.json()
    assert data["type"].startswith("https://")
    assert data["title"] == "Order Not Found"
    assert data["status"] == 404


@pytest.mark.asyncio
async def test_filtering(client):
    response = await client.get(
        "/api/v1/orders?status=pending&min_total=1000&sort_by=total_cents&sort_order=desc"
    )
    assert response.status_code == 200
    data = response.json()["data"]
    # Verify all returned orders match filters
    for order in data:
        assert order["status"] == "pending"
        assert order["total_cents"] >= 1000
    # Verify descending sort
    totals = [o["total_cents"] for o in data]
    assert totals == sorted(totals, reverse=True)
```

## Summary and Key Takeaways

**HATEOAS** makes APIs self-documenting and evolvable — clients discover available actions from
response links rather than hardcoding URLs. The **best practice** is state-dependent links
(a shipped order does not show a cancel link). However, the trade-off is increased payload size
and implementation effort, therefore reserve full HATEOAS for public APIs with many client
teams.

**Versioning** should use URL path (`/api/v1/`) for public APIs because simplicity and
visibility outweigh REST purity. The **common mistake** is versioning individual endpoints
rather than the entire API surface, which creates a combinatorial nightmare.

**Cursor pagination** is strictly superior to offset pagination for any dataset with concurrent
writes. The pitfall with offset is that inserting or deleting rows shifts the offset window,
causing duplicate or missing items. Cursors use index seeks which are O(1) regardless of
position. However, cursor pagination cannot support "jump to page N" — therefore, use offset
only when random page access is a hard product requirement.

**RFC 7807 Problem Details** should be the standard error format for every REST API. It
provides machine-readable `type` URIs, human-readable `detail`, and extensible fields for
validation errors. The common mistake is returning plain text errors or inconsistent JSON
structures across endpoints — standardizing on RFC 7807 makes client error handling uniform.
"""
    ),
    # --- 4. WebSocket Real-Time Systems ---
    (
        "websocket_realtime_systems_python",
        "Explain WebSocket real-time system design in depth — connection lifecycle management, "
        "heartbeat and automatic reconnection strategies, pub/sub room-based messaging, binary "
        "protocol design with message framing, and build a production Python asyncio WebSocket "
        "server with connection registry, room management, backpressure handling, and tests.",
        """\
# WebSocket Real-Time Systems: Connection Management to Binary Protocols

## Why WebSockets Over HTTP Polling?

WebSockets provide **full-duplex, persistent connections** between client and server. Unlike
HTTP (request-response), either side can send messages at any time without waiting. This
eliminates the fundamental inefficiency of polling.

```
HTTP Polling (every 1 second):
  Client: GET /messages → 200 "no new messages"  (wasted request)
  Client: GET /messages → 200 "no new messages"  (wasted request)
  Client: GET /messages → 200 "1 new message"    (1 second latency)
  = 60 requests/minute per client, most returning nothing
  = 60,000 requests/minute for 1,000 clients

WebSocket:
  Client: WS handshake → upgrade to WebSocket
  Server: (sends message when available) → 0ms latency
  = 1 connection per client, messages pushed instantly
  = 1,000 persistent connections, zero polling waste
```

However, WebSockets have **trade-offs**: they are stateful (harder to scale horizontally),
bypass HTTP caching, and require explicit handling of disconnection, reconnection, and
backpressure. The **common mistake** is treating WebSockets like HTTP — fire and forget — when
they actually require careful lifecycle management.

## Connection Lifecycle and Heartbeat

A production WebSocket system must handle five states: **connecting**, **open**, **closing**,
**closed**, and **reconnecting**. The most critical concern is detecting dead connections —
because TCP does not detect half-open connections quickly, a client can appear connected even
though the network path is broken.

```
Heartbeat Protocol:
  Server sends:  PING (every 30s)
  Client replies: PONG (within 10s)
  If no PONG:    Server closes connection, cleans up resources

  Client sends:  PING (every 25s, offset from server)
  Server replies: PONG (within 10s)
  If no PONG:    Client starts reconnection with exponential backoff
```

The **best practice** is bidirectional heartbeats — the server pings clients (to detect dead
clients and free resources), and clients ping the server (to detect network failures and
trigger reconnection). Using only server-side pings is a pitfall because clients never
discover that their connection is broken until they try to send data.

## Production WebSocket Server

```python
"""Production asyncio WebSocket server with rooms, heartbeat, and backpressure."""

import asyncio
import json
import logging
import struct
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Dict, Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


# --- Connection Registry ---

@dataclass
class Connection:
    """Represents a single WebSocket client connection.

    Tracks metadata needed for connection management: unique ID,
    authentication state, room membership, and heartbeat timing.
    """
    ws: WebSocketServerProtocol
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    rooms: Set[str] = field(default_factory=set)
    connected_at: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.time)
    send_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    _send_task: Optional[asyncio.Task] = field(default=None, repr=False)

    @property
    def is_alive(self) -> bool:
        """Connection is alive if we received a pong within the last 60 seconds."""
        return (time.time() - self.last_pong) < 60

    @property
    def latency_ms(self) -> float:
        """Approximate latency based on last ping-pong round trip."""
        return (time.time() - self.last_pong) * 1000


class ConnectionRegistry:
    """Thread-safe registry of all active WebSocket connections.

    Provides O(1) lookup by connection ID and by user ID, and O(1) room
    membership queries. This is essential for scaling — without proper
    indexing, broadcasting to a room of 10,000 users requires scanning
    all connections.
    """

    def __init__(self):
        self._connections: Dict[str, Connection] = {}
        self._by_user: Dict[str, Set[str]] = {}  # user_id -> conn_ids
        self._by_room: Dict[str, Set[str]] = {}  # room -> conn_ids
        self._lock = asyncio.Lock()

    async def add(self, conn: Connection) -> None:
        async with self._lock:
            self._connections[conn.id] = conn
            if conn.user_id:
                self._by_user.setdefault(conn.user_id, set()).add(conn.id)

    async def remove(self, conn_id: str) -> Optional[Connection]:
        async with self._lock:
            conn = self._connections.pop(conn_id, None)
            if conn is None:
                return None
            # Clean up user index
            if conn.user_id and conn.user_id in self._by_user:
                self._by_user[conn.user_id].discard(conn.id)
                if not self._by_user[conn.user_id]:
                    del self._by_user[conn.user_id]
            # Clean up room memberships
            for room in conn.rooms:
                if room in self._by_room:
                    self._by_room[room].discard(conn.id)
                    if not self._by_room[room]:
                        del self._by_room[room]
            return conn

    async def join_room(self, conn_id: str, room: str) -> bool:
        async with self._lock:
            conn = self._connections.get(conn_id)
            if conn is None:
                return False
            conn.rooms.add(room)
            self._by_room.setdefault(room, set()).add(conn_id)
            return True

    async def leave_room(self, conn_id: str, room: str) -> bool:
        async with self._lock:
            conn = self._connections.get(conn_id)
            if conn is None:
                return False
            conn.rooms.discard(room)
            if room in self._by_room:
                self._by_room[room].discard(conn_id)
                if not self._by_room[room]:
                    del self._by_room[room]
            return True

    def get_room_connections(self, room: str) -> list[Connection]:
        """Get all connections in a room — O(room_size), not O(total_connections)."""
        conn_ids = self._by_room.get(room, set())
        return [self._connections[cid] for cid in conn_ids if cid in self._connections]

    @property
    def count(self) -> int:
        return len(self._connections)

    def get_room_count(self, room: str) -> int:
        return len(self._by_room.get(room, set()))
```

## Pub/Sub Room Management and Broadcasting

```python
class MessageBroker:
    """In-process pub/sub broker for room-based messaging.

    For multi-server deployments, replace this with Redis Pub/Sub or
    similar. The interface stays the same — that is the key abstraction
    boundary.
    """

    def __init__(self, registry: ConnectionRegistry):
        self.registry = registry
        self._handlers: Dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable) -> None:
        """Register an event handler."""
        self._handlers.setdefault(event, []).append(handler)

    async def broadcast_to_room(
        self,
        room: str,
        message: dict,
        exclude: Optional[str] = None,
    ) -> int:
        """Send message to all connections in a room.

        Returns the number of successful sends. Uses backpressure-aware
        sending — if a client's queue is full, we drop the message for
        that client rather than blocking the entire broadcast.
        """
        connections = self.registry.get_room_connections(room)
        sent = 0
        payload = json.dumps(message)

        for conn in connections:
            if conn.id == exclude:
                continue
            try:
                # Non-blocking put — drop if queue is full (backpressure)
                conn.send_queue.put_nowait(payload)
                sent += 1
            except asyncio.QueueFull:
                logger.warning(
                    f"Dropping message for {conn.id}: send queue full "
                    f"(backpressure). This indicates a slow consumer."
                )

        return sent

    async def send_to_user(self, user_id: str, message: dict) -> int:
        """Send a message to all connections belonging to a specific user."""
        conn_ids = self.registry._by_user.get(user_id, set())
        sent = 0
        payload = json.dumps(message)

        for conn_id in conn_ids:
            conn = self.registry._connections.get(conn_id)
            if conn:
                try:
                    conn.send_queue.put_nowait(payload)
                    sent += 1
                except asyncio.QueueFull:
                    logger.warning(f"Queue full for user {user_id} conn {conn_id}")

        return sent


# --- WebSocket Server ---

class WebSocketServer:
    """Production WebSocket server with lifecycle management.

    Handles authentication, room management, heartbeat, and graceful
    shutdown. Each connection gets a dedicated send task for backpressure.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.registry = ConnectionRegistry()
        self.broker = MessageBroker(self.registry)
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._server = None

    async def start(self) -> None:
        """Start the WebSocket server and heartbeat loop."""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._server = await websockets.serve(
            self._handler,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10,
            max_size=1024 * 1024,  # 1MB max message size
            max_queue=64,
            compression="deflate",
        )
        logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Graceful shutdown: notify clients, close connections, stop server."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        # Notify all clients of shutdown
        for conn in list(self.registry._connections.values()):
            try:
                await conn.ws.close(1001, "Server shutting down")
            except Exception:
                pass

        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handler(self, ws: WebSocketServerProtocol) -> None:
        """Main connection handler — runs for the lifetime of each connection."""
        conn = Connection(ws=ws)

        try:
            # Phase 1: Authentication
            auth_msg = await asyncio.wait_for(ws.recv(), timeout=10)
            auth_data = json.loads(auth_msg)
            user_id = await self._authenticate(auth_data)
            if user_id is None:
                await ws.close(4001, "Authentication failed")
                return

            conn.user_id = user_id
            await self.registry.add(conn)
            logger.info(f"Connection {conn.id} authenticated as user {user_id}")

            # Start dedicated send task for this connection
            conn._send_task = asyncio.create_task(
                self._send_loop(conn)
            )

            # Send welcome message
            await ws.send(json.dumps({
                "type": "connected",
                "connection_id": conn.id,
                "server_time": time.time(),
            }))

            # Phase 2: Message loop
            async for raw_message in ws:
                try:
                    message = json.loads(raw_message)
                    await self._handle_message(conn, message)
                except json.JSONDecodeError:
                    await ws.send(json.dumps({
                        "type": "error",
                        "detail": "Invalid JSON",
                    }))
                except Exception as e:
                    logger.exception(f"Error handling message from {conn.id}: {e}")
                    await ws.send(json.dumps({
                        "type": "error",
                        "detail": str(e),
                    }))

        except websockets.ConnectionClosed as e:
            logger.info(f"Connection {conn.id} closed: {e.code} {e.reason}")
        except asyncio.TimeoutError:
            logger.warning(f"Connection {conn.id} auth timeout")
            await ws.close(4002, "Authentication timeout")
        finally:
            # Cleanup
            if conn._send_task:
                conn._send_task.cancel()
            await self.registry.remove(conn.id)
            logger.info(
                f"Connection {conn.id} cleaned up. "
                f"Active connections: {self.registry.count}"
            )

    async def _send_loop(self, conn: Connection) -> None:
        """Dedicated send loop — drains the connection's send queue.

        Separating send from receive prevents a slow send from blocking
        message reception. This is the key pattern for backpressure handling.
        """
        try:
            while True:
                message = await conn.send_queue.get()
                try:
                    await conn.ws.send(message)
                except websockets.ConnectionClosed:
                    break
        except asyncio.CancelledError:
            pass

    async def _handle_message(self, conn: Connection, message: dict) -> None:
        """Route incoming messages by type."""
        msg_type = message.get("type")

        if msg_type == "join_room":
            room = message["room"]
            await self.registry.join_room(conn.id, room)
            await self.broker.broadcast_to_room(room, {
                "type": "user_joined",
                "user_id": conn.user_id,
                "room": room,
                "member_count": self.registry.get_room_count(room),
            })

        elif msg_type == "leave_room":
            room = message["room"]
            await self.registry.leave_room(conn.id, room)
            await self.broker.broadcast_to_room(room, {
                "type": "user_left",
                "user_id": conn.user_id,
                "room": room,
                "member_count": self.registry.get_room_count(room),
            })

        elif msg_type == "room_message":
            room = message["room"]
            if room not in conn.rooms:
                await conn.ws.send(json.dumps({
                    "type": "error",
                    "detail": f"Not a member of room {room}",
                }))
                return
            await self.broker.broadcast_to_room(room, {
                "type": "room_message",
                "room": room,
                "sender": conn.user_id,
                "content": message["content"],
                "timestamp": time.time(),
            }, exclude=conn.id)

        elif msg_type == "pong":
            conn.last_pong = time.time()

        else:
            await conn.ws.send(json.dumps({
                "type": "error",
                "detail": f"Unknown message type: {msg_type}",
            }))

    async def _authenticate(self, auth_data: dict) -> Optional[str]:
        """Verify authentication token. Returns user_id or None."""
        token = auth_data.get("token")
        if not token:
            return None
        # In production, verify JWT or session token
        return await verify_auth_token(token)

    async def _heartbeat_loop(self) -> None:
        """Periodically check all connections and remove dead ones."""
        while True:
            await asyncio.sleep(30)
            dead_connections = []

            for conn_id, conn in list(self.registry._connections.items()):
                if not conn.is_alive:
                    dead_connections.append(conn_id)
                else:
                    try:
                        await conn.ws.send(json.dumps({"type": "ping"}))
                    except Exception:
                        dead_connections.append(conn_id)

            for conn_id in dead_connections:
                conn = await self.registry.remove(conn_id)
                if conn:
                    try:
                        await conn.ws.close(4003, "Heartbeat timeout")
                    except Exception:
                        pass
                    logger.info(f"Removed dead connection {conn_id}")
```

## Binary Protocol Design

```python
class MessageType(IntEnum):
    """Binary message types for high-performance protocols.

    Using binary protocols instead of JSON reduces message size by 3-10x
    and parsing time by 10-100x. The trade-off is debugging difficulty
    and client complexity.
    """
    PING = 0x01
    PONG = 0x02
    AUTH = 0x10
    AUTH_OK = 0x11
    AUTH_FAIL = 0x12
    JOIN_ROOM = 0x20
    LEAVE_ROOM = 0x21
    ROOM_MSG = 0x30
    DIRECT_MSG = 0x31
    ERROR = 0xFF


class BinaryProtocol:
    """Compact binary message framing protocol.

    Frame format:
    +--------+--------+--------+------------------+
    | Type   | Flags  | Length | Payload          |
    | 1 byte | 1 byte | 4 bytes| variable         |
    +--------+--------+--------+------------------+

    Flags:
      bit 0: compressed (payload is zlib-compressed)
      bit 1: fragmented (more fragments follow)
      bit 2: binary payload (vs UTF-8 text)
    """

    HEADER_FORMAT = "!BBL"  # type(1) + flags(1) + length(4) = 6 bytes
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    FLAG_COMPRESSED = 0x01
    FLAG_FRAGMENTED = 0x02
    FLAG_BINARY = 0x04

    @staticmethod
    def encode(
        msg_type: MessageType,
        payload: bytes,
        compress: bool = False,
    ) -> bytes:
        """Encode a message into the binary frame format."""
        import zlib

        flags = 0
        if compress and len(payload) > 128:
            payload = zlib.compress(payload, level=6)
            flags |= BinaryProtocol.FLAG_COMPRESSED

        header = struct.pack(
            BinaryProtocol.HEADER_FORMAT,
            msg_type,
            flags,
            len(payload),
        )
        return header + payload

    @staticmethod
    def decode(data: bytes) -> tuple[MessageType, int, bytes]:
        """Decode a binary frame. Returns (type, flags, payload)."""
        import zlib

        if len(data) < BinaryProtocol.HEADER_SIZE:
            raise ValueError(
                f"Frame too short: {len(data)} < {BinaryProtocol.HEADER_SIZE}"
            )

        msg_type, flags, length = struct.unpack(
            BinaryProtocol.HEADER_FORMAT,
            data[:BinaryProtocol.HEADER_SIZE],
        )
        payload = data[BinaryProtocol.HEADER_SIZE:BinaryProtocol.HEADER_SIZE + length]

        if len(payload) != length:
            raise ValueError(f"Payload truncated: expected {length}, got {len(payload)}")

        if flags & BinaryProtocol.FLAG_COMPRESSED:
            payload = zlib.decompress(payload)

        return MessageType(msg_type), flags, payload

    @staticmethod
    def encode_room_message(room: str, sender: str, content: str) -> bytes:
        """Encode a room message with structured binary payload."""
        room_bytes = room.encode("utf-8")
        sender_bytes = sender.encode("utf-8")
        content_bytes = content.encode("utf-8")

        # Sub-frame: room_len(2) + room + sender_len(2) + sender + content
        payload = (
            struct.pack("!H", len(room_bytes)) + room_bytes
            + struct.pack("!H", len(sender_bytes)) + sender_bytes
            + content_bytes
        )
        return BinaryProtocol.encode(
            MessageType.ROOM_MSG, payload, compress=len(payload) > 256
        )
```

## Testing WebSocket Systems

```python
import pytest
import asyncio
import json
import websockets


@pytest.fixture
async def ws_server():
    """Start a test WebSocket server on a random port."""
    server = WebSocketServer(host="127.0.0.1", port=0)
    await server.start()
    # Get the actual port
    port = server._server.sockets[0].getsockname()[1]
    yield server, port
    await server.stop()


async def connect_and_auth(port: int, token: str = "valid-token") -> websockets.WebSocketClientProtocol:
    """Helper: connect and authenticate."""
    ws = await websockets.connect(f"ws://127.0.0.1:{port}")
    await ws.send(json.dumps({"token": token}))
    response = json.loads(await ws.recv())
    assert response["type"] == "connected"
    return ws


@pytest.mark.asyncio
async def test_connection_lifecycle(ws_server):
    server, port = ws_server
    ws = await connect_and_auth(port)
    assert server.registry.count == 1
    await ws.close()
    await asyncio.sleep(0.1)
    assert server.registry.count == 0


@pytest.mark.asyncio
async def test_room_messaging(ws_server):
    server, port = ws_server
    ws1 = await connect_and_auth(port, "token-alice")
    ws2 = await connect_and_auth(port, "token-bob")

    # Both join same room
    await ws1.send(json.dumps({"type": "join_room", "room": "general"}))
    await ws2.send(json.dumps({"type": "join_room", "room": "general"}))
    # Consume join notifications
    await ws1.recv()  # bob joined (or alice joined)
    await ws2.recv()

    # Alice sends message
    await ws1.send(json.dumps({
        "type": "room_message", "room": "general", "content": "Hello!",
    }))

    # Bob receives it
    msg = json.loads(await asyncio.wait_for(ws2.recv(), timeout=2))
    assert msg["type"] == "room_message"
    assert msg["content"] == "Hello!"
    assert msg["room"] == "general"

    await ws1.close()
    await ws2.close()


@pytest.mark.asyncio
async def test_auth_failure(ws_server):
    _, port = ws_server
    ws = await websockets.connect(f"ws://127.0.0.1:{port}")
    await ws.send(json.dumps({"token": "invalid"}))
    with pytest.raises(websockets.ConnectionClosed) as exc_info:
        await ws.recv()
    assert exc_info.value.code == 4001


@pytest.mark.asyncio
async def test_binary_protocol():
    """Test binary encode/decode round-trip."""
    original = b"Hello, binary world!"
    encoded = BinaryProtocol.encode(MessageType.ROOM_MSG, original)
    msg_type, flags, payload = BinaryProtocol.decode(encoded)
    assert msg_type == MessageType.ROOM_MSG
    assert payload == original

    # Test with compression
    large_payload = b"x" * 1000
    encoded_compressed = BinaryProtocol.encode(
        MessageType.ROOM_MSG, large_payload, compress=True
    )
    assert len(encoded_compressed) < len(large_payload)  # Compressed is smaller
    _, flags, decoded = BinaryProtocol.decode(encoded_compressed)
    assert decoded == large_payload
```

## Summary and Key Takeaways

**Connection lifecycle management** is the most critical aspect of WebSocket systems. Every
connection must be tracked in a registry with O(1) lookup by ID, user, and room. The
**common mistake** is forgetting to clean up on disconnection — leaked connections accumulate
and exhaust server memory. Therefore, always use try/finally blocks and remove connections
from all indexes on disconnect.

**Heartbeat must be bidirectional** — server pings detect dead clients (freeing resources),
and client pings detect network failures (triggering reconnection). The **best practice** is
a 30-second interval with a 10-second timeout, and exponential backoff on reconnection
(1s, 2s, 4s, 8s... capped at 30s). A pitfall is using only WebSocket protocol-level pings
without application-level pings, because some proxies and load balancers strip WebSocket
control frames.

**Backpressure handling** prevents slow consumers from blocking the entire system. The pattern
is a per-connection send queue with a size limit — when the queue is full, messages are dropped
for that connection rather than blocking the broadcast. The trade-off is message loss for slow
clients, but the alternative (blocking) causes cascading failures across all clients.

**Binary protocols** reduce bandwidth 3-10x compared to JSON, which matters at scale (10,000+
connections). However, the trade-off is debugging difficulty — you cannot read binary frames
in browser dev tools. The best practice is to support both JSON (development/debugging) and
binary (production) modes, switching based on a connection parameter.
"""
    ),
    # --- 5. API Rate Limiting and Throttling ---
    (
        "api_rate_limiting_throttling",
        "Explain API rate limiting and throttling in depth — token bucket and sliding window "
        "algorithms, distributed rate limiting with Redis, per-user and per-endpoint quotas, "
        "graceful degradation strategies, and build a complete Python middleware implementation "
        "for FastAPI with multiple rate limit tiers, Redis backend, and comprehensive testing.",
        """\
# API Rate Limiting and Throttling: Protecting Services at Scale

## Why Rate Limiting is Non-Negotiable

Every production API needs rate limiting. Without it, a single misbehaving client — whether
malicious or buggy — can overwhelm your service and cause cascading failures for all users.
Rate limiting is not just about security; it is about **reliability** and **fairness**.

```
Without rate limiting:
  Normal client:    100 req/s  → 200ms response time
  Buggy client:  50,000 req/s  → All clients get 5000ms+ or timeouts
  Result: One client takes down the entire service

With rate limiting:
  Normal client:    100 req/s  → 200ms response time (allowed)
  Buggy client:  50,000 req/s  → 429 Too Many Requests after 1000 req/s
  Result: Buggy client is throttled, all others unaffected
```

## Token Bucket Algorithm

The token bucket is the most widely used rate limiting algorithm because it allows **bursts**
while enforcing a sustained rate. It works like a bucket that holds tokens: each request
consumes one token, and tokens refill at a fixed rate.

```
Token Bucket (capacity=10, refill_rate=5/sec):

  t=0.0:  bucket=[10 tokens]  →  request: consume 1  →  [9 tokens]  ✓
  t=0.0:  bucket=[9 tokens]   →  burst of 9 requests  →  [0 tokens]  ✓
  t=0.0:  bucket=[0 tokens]   →  request: NO tokens   →  429 ✗
  t=0.2:  bucket=[1 token]    →  1 token refilled (5/sec × 0.2s)
  t=1.0:  bucket=[5 tokens]   →  5 tokens refilled (5/sec × 1s)

The beauty: allows bursts up to capacity, but sustained rate = refill_rate
```

The **trade-off** compared to fixed windows is complexity — token bucket requires tracking
the last refill time and calculating fractional refills. However, it avoids the "boundary
burst" problem where fixed windows allow 2x the rate at window boundaries.

## Sliding Window Algorithm

The sliding window avoids both the boundary burst problem and the burst-allowance of token
bucket. It counts requests in a moving time window, providing the smoothest rate enforcement.

```
Sliding Window (limit=100 per minute):

  Window = [now - 60s, now]
  Requests in window: counted in real time
  New request: if count < 100 → allow, else → 429

  Practical implementation uses a weighted combination of current and
  previous window counts to avoid storing every timestamp:

  current_window_count = 40 (we're 30s into current minute)
  previous_window_count = 80
  weight = (60 - 30) / 60 = 0.5  (50% of previous window overlaps)
  estimated_count = 40 + (80 × 0.5) = 80
  80 < 100 → allowed
```

## Complete Rate Limiter Implementation

```python
"""Production rate limiter with multiple algorithms and Redis backend."""

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

import redis.asyncio as redis


@dataclass
class RateLimitResult:
    """Result of a rate limit check.

    Provides all information needed for response headers:
    - allowed: whether the request should proceed
    - limit: the total quota for this window
    - remaining: requests remaining in this window
    - retry_after: seconds until the client can retry (if denied)
    - reset_at: Unix timestamp when the window resets
    """
    allowed: bool
    limit: int
    remaining: int
    retry_after: Optional[float] = None
    reset_at: Optional[float] = None


class RateLimiter(ABC):
    """Abstract base class for rate limiting algorithms."""

    @abstractmethod
    async def check(self, key: str) -> RateLimitResult:
        """Check if a request is allowed for the given key."""
        ...

    @abstractmethod
    async def reset(self, key: str) -> None:
        """Reset the rate limit for a key (e.g., after payment)."""
        ...


class TokenBucketLimiter(RateLimiter):
    """Token bucket rate limiter with Redis backend.

    Uses a single Redis hash per key to store bucket state, with atomic
    Lua script execution to prevent race conditions in distributed
    deployments. This is the best practice for distributed rate limiting
    because Lua scripts execute atomically on the Redis server.
    """

    # Lua script for atomic token bucket check-and-consume
    LUA_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local ttl = tonumber(ARGV[4])

    -- Get current bucket state
    local tokens = tonumber(redis.call('HGET', key, 'tokens'))
    local last_refill = tonumber(redis.call('HGET', key, 'last_refill'))

    -- Initialize if first request
    if tokens == nil then
        tokens = capacity
        last_refill = now
    end

    -- Calculate refilled tokens
    local elapsed = now - last_refill
    local refilled = elapsed * refill_rate
    tokens = math.min(capacity, tokens + refilled)
    last_refill = now

    -- Try to consume one token
    local allowed = 0
    if tokens >= 1 then
        tokens = tokens - 1
        allowed = 1
    end

    -- Save state
    redis.call('HSET', key, 'tokens', tokens)
    redis.call('HSET', key, 'last_refill', last_refill)
    redis.call('EXPIRE', key, ttl)

    -- Calculate retry_after if denied
    local retry_after = 0
    if allowed == 0 then
        retry_after = (1 - tokens) / refill_rate
    end

    return {allowed, math.floor(tokens), retry_after * 1000}
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        capacity: int = 100,
        refill_rate: float = 10.0,  # tokens per second
        key_prefix: str = "ratelimit:tb",
    ):
        self.redis = redis_client
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.key_prefix = key_prefix
        self._script = None

    async def _get_script(self):
        if self._script is None:
            self._script = self.redis.register_script(self.LUA_SCRIPT)
        return self._script

    async def check(self, key: str) -> RateLimitResult:
        full_key = f"{self.key_prefix}:{key}"
        script = await self._get_script()
        now = time.time()

        result = await script(
            keys=[full_key],
            args=[self.capacity, self.refill_rate, now, 3600],
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        retry_after_ms = float(result[2])

        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=remaining,
            retry_after=retry_after_ms / 1000 if not allowed else None,
            reset_at=now + (self.capacity - remaining) / self.refill_rate,
        )

    async def reset(self, key: str) -> None:
        await self.redis.delete(f"{self.key_prefix}:{key}")


class SlidingWindowLimiter(RateLimiter):
    """Sliding window rate limiter using Redis sorted sets.

    Each request is stored as a member in a sorted set with the timestamp
    as the score. To check the rate, we count members within the window.
    Old entries are pruned on each check.

    The trade-off vs token bucket: more accurate rate enforcement (no bursts),
    but higher Redis memory usage (stores every request timestamp).
    """

    LUA_SCRIPT = """
    local key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local member = ARGV[4]

    -- Remove entries outside the window
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

    -- Count current entries
    local count = redis.call('ZCARD', key)

    if count < limit then
        -- Add new entry
        redis.call('ZADD', key, now, member)
        redis.call('EXPIRE', key, math.ceil(window))
        return {1, limit - count - 1, 0}
    else
        -- Get oldest entry to calculate retry_after
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local retry_after = 0
        if #oldest > 0 then
            retry_after = (tonumber(oldest[2]) + window - now) * 1000
        end
        return {0, 0, retry_after}
    end
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        limit: int = 100,
        window_seconds: float = 60.0,
        key_prefix: str = "ratelimit:sw",
    ):
        self.redis = redis_client
        self.limit = limit
        self.window = window_seconds
        self.key_prefix = key_prefix
        self._script = None

    async def _get_script(self):
        if self._script is None:
            self._script = self.redis.register_script(self.LUA_SCRIPT)
        return self._script

    async def check(self, key: str) -> RateLimitResult:
        full_key = f"{self.key_prefix}:{key}"
        script = await self._get_script()
        now = time.time()
        member = f"{now}:{id(asyncio.current_task())}"

        result = await script(
            keys=[full_key],
            args=[self.limit, self.window, now, member],
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        retry_after_ms = float(result[2])

        return RateLimitResult(
            allowed=allowed,
            limit=self.limit,
            remaining=remaining,
            retry_after=retry_after_ms / 1000 if not allowed else None,
            reset_at=now + self.window,
        )

    async def reset(self, key: str) -> None:
        await self.redis.delete(f"{self.key_prefix}:{key}")
```

## FastAPI Middleware with Per-User Quotas and Tiered Limits

```python
"""FastAPI rate limiting middleware with tiered per-user quotas."""

from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from dataclasses import dataclass
from typing import Callable, Dict, Optional
import redis.asyncio as redis


@dataclass
class RateLimitTier:
    """Rate limit configuration for a user tier.

    Different tiers allow different quotas — free users get basic limits,
    paid users get higher limits, and internal services get the highest.
    """
    name: str
    requests_per_second: float
    burst_capacity: int
    daily_quota: int
    per_endpoint_limits: Dict[str, int]  # endpoint pattern -> per-minute limit


# Define tiers
TIERS: Dict[str, RateLimitTier] = {
    "free": RateLimitTier(
        name="free",
        requests_per_second=5,
        burst_capacity=20,
        daily_quota=1_000,
        per_endpoint_limits={
            "/api/v1/search": 10,       # 10/min for expensive search
            "/api/v1/export": 2,        # 2/min for heavy exports
            "default": 60,             # 60/min for everything else
        },
    ),
    "pro": RateLimitTier(
        name="pro",
        requests_per_second=50,
        burst_capacity=200,
        daily_quota=100_000,
        per_endpoint_limits={
            "/api/v1/search": 120,
            "/api/v1/export": 30,
            "default": 600,
        },
    ),
    "internal": RateLimitTier(
        name="internal",
        requests_per_second=500,
        burst_capacity=2000,
        daily_quota=10_000_000,
        per_endpoint_limits={
            "default": 6000,
        },
    ),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Multi-layer rate limiting middleware.

    Applies three layers of rate limiting:
    1. Global: token bucket per user (burst + sustained rate)
    2. Per-endpoint: sliding window per user per endpoint
    3. Daily quota: simple counter per user per day

    This layered approach is the best practice because it prevents both
    burst abuse and sustained abuse while allowing different limits for
    different endpoint costs.
    """

    # Paths exempt from rate limiting
    EXEMPT_PATHS = {"/health", "/metrics", "/api/v1/docs", "/api/v1/openapi.json"}

    def __init__(self, app: FastAPI, redis_url: str = "redis://localhost:6379"):
        super().__init__(app)
        self.redis_pool = redis.from_url(redis_url, decode_responses=True)
        self._limiters: Dict[str, TokenBucketLimiter] = {}
        self._endpoint_limiters: Dict[str, SlidingWindowLimiter] = {}

    def _get_tier_limiter(self, tier: RateLimitTier) -> TokenBucketLimiter:
        """Get or create a token bucket limiter for a tier."""
        if tier.name not in self._limiters:
            self._limiters[tier.name] = TokenBucketLimiter(
                redis_client=self.redis_pool,
                capacity=tier.burst_capacity,
                refill_rate=tier.requests_per_second,
                key_prefix=f"ratelimit:global:{tier.name}",
            )
        return self._limiters[tier.name]

    def _get_endpoint_limiter(
        self, tier: RateLimitTier, endpoint: str
    ) -> SlidingWindowLimiter:
        """Get or create a sliding window limiter for a tier+endpoint."""
        limit = tier.per_endpoint_limits.get(
            endpoint, tier.per_endpoint_limits["default"]
        )
        cache_key = f"{tier.name}:{endpoint}:{limit}"

        if cache_key not in self._endpoint_limiters:
            self._endpoint_limiters[cache_key] = SlidingWindowLimiter(
                redis_client=self.redis_pool,
                limit=limit,
                window_seconds=60,
                key_prefix=f"ratelimit:endpoint:{tier.name}",
            )
        return self._endpoint_limiters[cache_key]

    async def _identify_client(self, request: Request) -> Tuple[str, RateLimitTier]:
        """Extract client identity and tier from the request.

        Priority: API key → JWT user → IP address.
        Common mistake: using only IP, which fails behind NATs and proxies.
        """
        # Check API key first
        api_key = request.headers.get("X-API-Key")
        if api_key:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
            tier_name = await self.redis_pool.get(f"apikey:tier:{key_hash}")
            if tier_name and tier_name in TIERS:
                return f"key:{key_hash}", TIERS[tier_name]

        # Check JWT token
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            # In production, decode and verify the JWT
            token = auth[7:]
            user_id = await decode_jwt_user_id(token)
            if user_id:
                tier_name = await self.redis_pool.get(f"user:tier:{user_id}")
                return f"user:{user_id}", TIERS.get(tier_name or "free", TIERS["free"])

        # Fall back to IP address
        client_ip = request.headers.get(
            "X-Forwarded-For", request.client.host
        ).split(",")[0].strip()
        return f"ip:{client_ip}", TIERS["free"]

    async def _check_daily_quota(
        self, client_id: str, tier: RateLimitTier
    ) -> RateLimitResult:
        """Check and increment the daily request counter."""
        import datetime

        today = datetime.date.today().isoformat()
        key = f"ratelimit:daily:{client_id}:{today}"

        count = await self.redis_pool.incr(key)
        if count == 1:
            # Set expiry on first request of the day
            await self.redis_pool.expire(key, 86400)

        remaining = max(0, tier.daily_quota - count)
        allowed = count <= tier.daily_quota

        return RateLimitResult(
            allowed=allowed,
            limit=tier.daily_quota,
            remaining=remaining,
            retry_after=None if allowed else 86400.0,
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply multi-layer rate limiting to each request."""
        path = request.url.path

        # Skip exempt paths
        if path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Identify client and tier
        client_id, tier = await self._identify_client(request)

        # Layer 1: Global token bucket (burst + sustained rate)
        global_limiter = self._get_tier_limiter(tier)
        global_result = await global_limiter.check(client_id)

        if not global_result.allowed:
            return self._rate_limit_response(global_result, "global")

        # Layer 2: Per-endpoint sliding window
        endpoint_limiter = self._get_endpoint_limiter(tier, path)
        endpoint_key = f"{client_id}:{path}"
        endpoint_result = await endpoint_limiter.check(endpoint_key)

        if not endpoint_result.allowed:
            return self._rate_limit_response(endpoint_result, "endpoint")

        # Layer 3: Daily quota
        daily_result = await self._check_daily_quota(client_id, tier)
        if not daily_result.allowed:
            return self._rate_limit_response(daily_result, "daily")

        # Request allowed — add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(global_result.limit)
        response.headers["X-RateLimit-Remaining"] = str(global_result.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(global_result.reset_at or 0))
        response.headers["X-RateLimit-Daily-Remaining"] = str(daily_result.remaining)
        return response

    def _rate_limit_response(
        self, result: RateLimitResult, layer: str
    ) -> JSONResponse:
        """Return a standardized 429 response with retry information."""
        return JSONResponse(
            status_code=429,
            content={
                "type": "https://api.example.com/problems/rate-limit-exceeded",
                "title": "Rate Limit Exceeded",
                "status": 429,
                "detail": (
                    f"You have exceeded the {layer} rate limit. "
                    f"Please retry after {result.retry_after:.1f} seconds."
                ),
                "limit": result.limit,
                "remaining": result.remaining,
                "retry_after": result.retry_after,
            },
            headers={
                "Retry-After": str(int(result.retry_after or 1)),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
            },
        )


# --- Application Setup ---

app = FastAPI(title="Rate Limited API")
app.add_middleware(RateLimitMiddleware, redis_url="redis://localhost:6379")


@app.get("/api/v1/data")
async def get_data():
    return {"message": "This endpoint is rate limited"}


@app.get("/api/v1/search")
async def search(q: str):
    """Expensive search endpoint with lower rate limits."""
    return {"results": [], "query": q}
```

## Testing Rate Limiters

```python
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch

import redis.asyncio as redis
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def redis_client():
    """Connect to a test Redis instance."""
    client = redis.from_url("redis://localhost:6379/15", decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def token_bucket(redis_client):
    return TokenBucketLimiter(
        redis_client=redis_client,
        capacity=10,
        refill_rate=5.0,
        key_prefix="test:tb",
    )


@pytest.fixture
async def sliding_window(redis_client):
    return SlidingWindowLimiter(
        redis_client=redis_client,
        limit=5,
        window_seconds=10.0,
        key_prefix="test:sw",
    )


@pytest.mark.asyncio
async def test_token_bucket_allows_burst(token_bucket):
    """Token bucket should allow bursts up to capacity."""
    results = []
    for _ in range(10):
        result = await token_bucket.check("user-1")
        results.append(result.allowed)

    assert all(results), "All 10 requests should be allowed (bucket capacity = 10)"

    # 11th request should be denied
    result = await token_bucket.check("user-1")
    assert not result.allowed
    assert result.retry_after > 0


@pytest.mark.asyncio
async def test_token_bucket_refills(token_bucket):
    """After draining the bucket, tokens should refill over time."""
    # Drain the bucket
    for _ in range(10):
        await token_bucket.check("user-2")

    # Wait for 1 second — should refill 5 tokens (rate = 5/sec)
    await asyncio.sleep(1.1)

    results = []
    for _ in range(5):
        result = await token_bucket.check("user-2")
        results.append(result.allowed)

    assert all(results), "5 tokens should have refilled after 1 second"


@pytest.mark.asyncio
async def test_sliding_window_enforces_limit(sliding_window):
    """Sliding window should enforce the limit within the time window."""
    # Use all 5 requests
    for i in range(5):
        result = await sliding_window.check("user-3")
        assert result.allowed, f"Request {i+1} of 5 should be allowed"

    # 6th request should be denied
    result = await sliding_window.check("user-3")
    assert not result.allowed
    assert result.remaining == 0
    assert result.retry_after > 0


@pytest.mark.asyncio
async def test_per_user_isolation(token_bucket):
    """Rate limits should be independent per user."""
    # Drain user-a's bucket
    for _ in range(10):
        await token_bucket.check("user-a")

    result_a = await token_bucket.check("user-a")
    assert not result_a.allowed

    # user-b should be unaffected
    result_b = await token_bucket.check("user-b")
    assert result_b.allowed
    assert result_b.remaining == 9


@pytest.mark.asyncio
async def test_middleware_returns_429():
    """Integration test: verify middleware returns 429 with correct headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Send many rapid requests
        responses = []
        for _ in range(50):
            resp = await client.get("/api/v1/data")
            responses.append(resp)

        # Some should be 429
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, "At least one request should be rate limited"

        # Check 429 response format
        limited = next(r for r in responses if r.status_code == 429)
        assert "Retry-After" in limited.headers
        body = limited.json()
        assert body["status"] == 429
        assert "retry_after" in body


@pytest.mark.asyncio
async def test_middleware_rate_limit_headers():
    """Verify rate limit headers are present on successful responses."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/data")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers


@pytest.mark.asyncio
async def test_reset_clears_limit(token_bucket):
    """Resetting a key should restore full quota."""
    # Drain the bucket
    for _ in range(10):
        await token_bucket.check("user-reset")

    result = await token_bucket.check("user-reset")
    assert not result.allowed

    # Reset
    await token_bucket.reset("user-reset")

    # Should have full capacity again
    result = await token_bucket.check("user-reset")
    assert result.allowed
    assert result.remaining == 9
```

## Summary and Key Takeaways

**Token bucket** is the best general-purpose rate limiting algorithm because it naturally
allows bursts (up to bucket capacity) while enforcing a sustained rate (refill rate). The
**common mistake** is using fixed window counters, which allow 2x the intended rate at window
boundaries — a client can send 100 requests at 11:59:59 and 100 more at 12:00:01, getting
200 requests in 2 seconds despite a 100/minute limit.

**Distributed rate limiting with Redis** is essential for multi-server deployments. The
**best practice** is atomic Lua scripts — they execute on the Redis server as a single
operation, preventing race conditions where two servers both read "99 remaining" and both
allow a request, resulting in 101 total. The pitfall is using separate GET/SET commands,
which create a time-of-check-to-time-of-use (TOCTOU) race.

**Per-user tiered quotas** require identifying clients accurately. The priority should be
API key (most reliable), then JWT token, then IP address. The common mistake is using only
IP-based rate limiting, which fails behind corporate NATs (thousands of users share one IP)
and allows bypassing via rotating IPs. Therefore, always prefer authenticated identity over
network identity.

**Response headers** (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`) are
critical for client-side handling. Well-behaved clients use these headers to self-throttle
before hitting 429 errors. The trade-off is that these headers leak your rate limit
configuration to potential attackers, but transparency for legitimate clients outweighs the
risk. The best practice is to always return `Retry-After` on 429 responses — without it,
clients resort to arbitrary backoff strategies that waste both client and server resources.
"""
    ),
]
