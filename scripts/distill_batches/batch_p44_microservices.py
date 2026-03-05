"""Microservices — service communication, gRPC, event-driven architecture, and deployment patterns."""

PAIRS = [
    (
        "architecture/microservice-communication",
        "Show microservice communication patterns: synchronous vs async, API gateway, service mesh, and event-driven architecture.",
        '''Microservice communication patterns:

```python
# --- API Gateway pattern ---

from fastapi import FastAPI, Request, HTTPException
import httpx
from typing import Optional
import asyncio

app = FastAPI()

# Service registry
SERVICES = {
    "users": "http://users-service:8001",
    "orders": "http://orders-service:8002",
    "products": "http://products-service:8003",
    "payments": "http://payments-service:8004",
}

class ServiceClient:
    """HTTP client for inter-service communication."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=3.0),
            limits=httpx.Limits(max_connections=100),
        )

    async def call(self, service: str, method: str, path: str,
                   headers: dict = None, **kwargs) -> httpx.Response:
        base_url = SERVICES.get(service)
        if not base_url:
            raise HTTPException(502, f"Unknown service: {service}")

        # Propagate tracing headers
        fwd_headers = {}
        if headers:
            for h in ["X-Request-ID", "X-Trace-ID", "Authorization"]:
                if h in headers:
                    fwd_headers[h] = headers[h]

        try:
            response = await self.client.request(
                method, f"{base_url}{path}",
                headers=fwd_headers, **kwargs,
            )
            return response
        except httpx.TimeoutException:
            raise HTTPException(504, f"Service timeout: {service}")
        except httpx.ConnectError:
            raise HTTPException(502, f"Service unavailable: {service}")

service_client = ServiceClient()

# API Gateway aggregation
@app.get("/api/dashboard/{user_id}")
async def user_dashboard(user_id: str, request: Request):
    """Aggregate data from multiple services."""
    headers = dict(request.headers)

    # Fan-out: call services concurrently
    async with asyncio.TaskGroup() as tg:
        user_task = tg.create_task(
            service_client.call("users", "GET", f"/users/{user_id}", headers)
        )
        orders_task = tg.create_task(
            service_client.call("orders", "GET", f"/orders?user_id={user_id}", headers)
        )

    user = user_task.result().json()
    orders = orders_task.result().json()

    return {
        "user": user,
        "orders": orders["items"][:5],
        "order_count": orders["total"],
    }


# --- Event-driven communication ---

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import json

class EventType(str, Enum):
    ORDER_CREATED = "order.created"
    ORDER_PAID = "order.paid"
    ORDER_SHIPPED = "order.shipped"
    ORDER_CANCELLED = "order.cancelled"
    USER_REGISTERED = "user.registered"
    INVENTORY_LOW = "inventory.low"

@dataclass
class DomainEvent:
    event_type: EventType
    aggregate_id: str
    data: dict
    metadata: dict = field(default_factory=dict)
    event_id: str = ""
    timestamp: str = ""
    version: int = 1

    def __post_init__(self):
        if not self.event_id:
            import uuid
            self.event_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

class EventBus:
    """Publish events to message broker."""

    def __init__(self, publisher):
        self.publisher = publisher
        self.handlers: dict[str, list] = {}

    async def publish(self, event: DomainEvent):
        """Publish event to broker (Kafka, RabbitMQ, etc)."""
        await self.publisher.send(
            topic=event.event_type.value,
            key=event.aggregate_id,
            value=json.dumps(asdict(event)),
        )

    def subscribe(self, event_type: EventType):
        """Decorator to register event handler."""
        def decorator(handler):
            self.handlers.setdefault(event_type.value, []).append(handler)
            return handler
        return decorator

    async def handle(self, event_data: dict):
        event_type = event_data.get("event_type")
        handlers = self.handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event_data)
            except Exception as e:
                logger.error("Handler failed: %s: %s", handler.__name__, e)

event_bus = EventBus(kafka_producer)

# --- Service: Order Service publishes events ---
class OrderService:
    async def create_order(self, user_id: str, items: list) -> dict:
        order = await self.repo.create(user_id=user_id, items=items)

        await event_bus.publish(DomainEvent(
            event_type=EventType.ORDER_CREATED,
            aggregate_id=order["id"],
            data={
                "user_id": user_id,
                "items": items,
                "total": order["total"],
            },
        ))
        return order

# --- Service: Inventory Service consumes events ---
@event_bus.subscribe(EventType.ORDER_CREATED)
async def reserve_inventory(event: dict):
    for item in event["data"]["items"]:
        await inventory_repo.reserve(
            product_id=item["product_id"],
            quantity=item["quantity"],
        )

# --- Service: Notification Service consumes events ---
@event_bus.subscribe(EventType.ORDER_CREATED)
async def send_order_confirmation(event: dict):
    user = await user_client.get_user(event["data"]["user_id"])
    await email_service.send(
        to=user["email"],
        template="order_confirmation",
        data=event["data"],
    )
```

Communication patterns:
1. **Synchronous (HTTP/gRPC)** — request/response, simple, higher coupling
2. **Async (events)** — publish/subscribe, decoupled, eventual consistency
3. **API Gateway** — single entry point, aggregation, auth, rate limiting
4. **Saga** — coordinate multi-service transactions with compensating actions
5. **CQRS** — separate read/write models for different optimization'''
    ),
    (
        "architecture/grpc-patterns",
        "Show gRPC patterns in Python: service definition, streaming, interceptors, and health checking.",
        '''gRPC service patterns in Python:

```protobuf
// user_service.proto
syntax = "proto3";
package userservice;

service UserService {
    // Unary RPC
    rpc GetUser (GetUserRequest) returns (User);
    rpc CreateUser (CreateUserRequest) returns (User);
    rpc ListUsers (ListUsersRequest) returns (ListUsersResponse);

    // Server streaming
    rpc WatchUserUpdates (WatchRequest) returns (stream UserEvent);

    // Client streaming
    rpc BulkCreateUsers (stream CreateUserRequest) returns (BulkCreateResponse);

    // Bidirectional streaming
    rpc Chat (stream ChatMessage) returns (stream ChatMessage);
}

message User {
    string id = 1;
    string name = 2;
    string email = 3;
    int64 created_at = 4;
}

message GetUserRequest {
    string id = 1;
}

message CreateUserRequest {
    string name = 1;
    string email = 2;
}

message ListUsersRequest {
    int32 page_size = 1;
    string page_token = 2;
}

message ListUsersResponse {
    repeated User users = 1;
    string next_page_token = 2;
    int32 total_count = 3;
}
```

```python
# --- gRPC server implementation ---

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from concurrent import futures
import user_service_pb2 as pb2
import user_service_pb2_grpc as pb2_grpc

class UserServicer(pb2_grpc.UserServiceServicer):
    def __init__(self, repo):
        self.repo = repo

    async def GetUser(self, request, context):
        user = await self.repo.get_by_id(request.id)
        if not user:
            context.abort(grpc.StatusCode.NOT_FOUND, f"User {request.id} not found")
        return pb2.User(
            id=user.id, name=user.name,
            email=user.email, created_at=int(user.created_at.timestamp()),
        )

    async def CreateUser(self, request, context):
        try:
            user = await self.repo.create(name=request.name, email=request.email)
            return pb2.User(id=user.id, name=user.name, email=user.email)
        except ValueError as e:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))

    async def ListUsers(self, request, context):
        page_size = min(request.page_size or 20, 100)
        users, next_token, total = await self.repo.list_paginated(
            page_size=page_size, page_token=request.page_token,
        )
        return pb2.ListUsersResponse(
            users=[pb2.User(id=u.id, name=u.name, email=u.email) for u in users],
            next_page_token=next_token,
            total_count=total,
        )

    async def WatchUserUpdates(self, request, context):
        """Server streaming: send updates as they happen."""
        async for event in self.repo.watch_changes():
            if context.cancelled():
                break
            yield pb2.UserEvent(
                event_type=event.type,
                user=pb2.User(id=event.user.id, name=event.user.name),
            )


# --- Interceptors (middleware) ---

class LoggingInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method
        start = time.perf_counter()
        try:
            response = await continuation(handler_call_details)
            duration = time.perf_counter() - start
            logger.info("gRPC %s completed in %.3fs", method, duration)
            return response
        except Exception as e:
            duration = time.perf_counter() - start
            logger.error("gRPC %s failed in %.3fs: %s", method, duration, e)
            raise

class AuthInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata)
        token = metadata.get("authorization", "").replace("Bearer ", "")
        if not token:
            raise grpc.aio.AbortError(grpc.StatusCode.UNAUTHENTICATED, "Missing token")
        # Validate token...
        return await continuation(handler_call_details)


# --- Server setup ---

async def serve():
    server = grpc.aio.server(
        interceptors=[LoggingInterceptor(), AuthInterceptor()],
        options=[
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
        ],
    )

    pb2_grpc.add_UserServiceServicer_to_server(UserServicer(repo), server)

    # Health check
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("UserService", health_pb2.HealthCheckResponse.SERVING)

    server.add_insecure_port("[::]:50051")
    await server.start()
    await server.wait_for_termination()
```

gRPC vs REST:
- **gRPC** — binary (protobuf), strong typing, streaming, code generation
- **REST** — JSON, universal, browser-friendly, simpler tooling
- Use gRPC for: internal services, high throughput, streaming, strict contracts
- Use REST for: public APIs, browser clients, simple CRUD'''
    ),
    (
        "architecture/event-sourcing-cqrs",
        "Show event sourcing and CQRS patterns: event store, projections, snapshots, and read model optimization.",
        '''Event sourcing and CQRS implementation:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from abc import ABC, abstractmethod
import json
import uuid

# --- Events ---

@dataclass(frozen=True)
class Event:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    aggregate_id: str = ""
    version: int = 0

@dataclass(frozen=True)
class AccountCreated(Event):
    owner_name: str = ""
    initial_balance: float = 0.0

@dataclass(frozen=True)
class MoneyDeposited(Event):
    amount: float = 0.0
    description: str = ""

@dataclass(frozen=True)
class MoneyWithdrawn(Event):
    amount: float = 0.0
    description: str = ""

@dataclass(frozen=True)
class AccountClosed(Event):
    reason: str = ""


# --- Aggregate ---

class BankAccount:
    """Event-sourced aggregate."""

    def __init__(self):
        self.id = ""
        self.owner = ""
        self.balance = 0.0
        self.is_closed = False
        self.version = 0
        self._pending_events: list[Event] = []

    # Commands (validate and produce events)
    def create(self, account_id: str, owner: str, initial_balance: float):
        if initial_balance < 0:
            raise ValueError("Initial balance cannot be negative")
        self._apply(AccountCreated(
            aggregate_id=account_id,
            owner_name=owner,
            initial_balance=initial_balance,
        ))

    def deposit(self, amount: float, description: str = ""):
        if self.is_closed:
            raise ValueError("Account is closed")
        if amount <= 0:
            raise ValueError("Deposit must be positive")
        self._apply(MoneyDeposited(
            aggregate_id=self.id, amount=amount, description=description,
        ))

    def withdraw(self, amount: float, description: str = ""):
        if self.is_closed:
            raise ValueError("Account is closed")
        if amount <= 0:
            raise ValueError("Withdrawal must be positive")
        if self.balance < amount:
            raise ValueError(f"Insufficient funds: {self.balance} < {amount}")
        self._apply(MoneyWithdrawn(
            aggregate_id=self.id, amount=amount, description=description,
        ))

    # Event handlers (update state)
    def _apply(self, event: Event):
        self._handle(event)
        self.version += 1
        self._pending_events.append(event)

    def _handle(self, event: Event):
        if isinstance(event, AccountCreated):
            self.id = event.aggregate_id
            self.owner = event.owner_name
            self.balance = event.initial_balance
        elif isinstance(event, MoneyDeposited):
            self.balance += event.amount
        elif isinstance(event, MoneyWithdrawn):
            self.balance -= event.amount
        elif isinstance(event, AccountClosed):
            self.is_closed = True

    # Rebuild from event history
    @classmethod
    def from_events(cls, events: list[Event]) -> "BankAccount":
        account = cls()
        for event in events:
            account._handle(event)
            account.version += 1
        return account

    def get_pending_events(self) -> list[Event]:
        events = self._pending_events[:]
        self._pending_events.clear()
        return events


# --- Event Store ---

class EventStore:
    def __init__(self, db):
        self.db = db

    async def save_events(self, aggregate_id: str, events: list[Event],
                          expected_version: int):
        """Save events with optimistic concurrency."""
        current = await self.db.fetchval(
            "SELECT MAX(version) FROM events WHERE aggregate_id = $1",
            aggregate_id,
        )
        if (current or 0) != expected_version:
            raise ConcurrencyError(
                f"Expected version {expected_version}, got {current}"
            )

        for i, event in enumerate(events):
            await self.db.execute("""
                INSERT INTO events (event_id, aggregate_id, event_type, version, data, timestamp)
                VALUES ($1, $2, $3, $4, $5, $6)
            """,
                event.event_id, aggregate_id,
                type(event).__name__,
                expected_version + i + 1,
                json.dumps(self._serialize(event)),
                event.timestamp,
            )

    async def get_events(self, aggregate_id: str,
                          after_version: int = 0) -> list[Event]:
        rows = await self.db.fetch("""
            SELECT * FROM events
            WHERE aggregate_id = $1 AND version > $2
            ORDER BY version
        """, aggregate_id, after_version)
        return [self._deserialize(row) for row in rows]


# --- CQRS: Separate read model ---

class AccountReadModel:
    """Optimized read model, updated by event projections."""

    async def project_event(self, event: Event):
        """Update read model from event."""
        if isinstance(event, AccountCreated):
            await self.db.execute("""
                INSERT INTO account_summary (id, owner, balance, status, created_at)
                VALUES ($1, $2, $3, 'active', $4)
            """, event.aggregate_id, event.owner_name,
                 event.initial_balance, event.timestamp)

        elif isinstance(event, (MoneyDeposited, MoneyWithdrawn)):
            delta = event.amount if isinstance(event, MoneyDeposited) else -event.amount
            await self.db.execute("""
                UPDATE account_summary
                SET balance = balance + $1, updated_at = $2
                WHERE id = $3
            """, delta, event.timestamp, event.aggregate_id)

    async def get_summary(self, account_id: str) -> dict:
        return await self.db.fetchrow(
            "SELECT * FROM account_summary WHERE id = $1", account_id
        )

    async def get_rich_accounts(self, min_balance: float) -> list:
        return await self.db.fetch(
            "SELECT * FROM account_summary WHERE balance >= $1 ORDER BY balance DESC",
            min_balance,
        )
```

Event sourcing benefits:
1. **Full audit trail** — every state change is recorded
2. **Time travel** — reconstruct state at any point in time
3. **Event replay** — rebuild read models, fix bugs retroactively
4. **CQRS** — optimize reads and writes independently
5. **Decoupling** — services react to events, not direct calls'''
    ),
]
"""
