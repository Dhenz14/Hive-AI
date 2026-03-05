"""Networking — gRPC services, message formats, and API gateway patterns."""

PAIRS = [
    (
        "api/grpc-service",
        "Show gRPC service patterns: service definition, server implementation, client usage, and streaming.",
        '''gRPC service patterns:

```protobuf
// --- Proto definition ---
// user_service.proto

syntax = "proto3";
package users.v1;

import "google/protobuf/timestamp.proto";
import "google/protobuf/field_mask.proto";
import "google/protobuf/empty.proto";

service UserService {
  // Unary RPCs
  rpc GetUser(GetUserRequest) returns (User);
  rpc CreateUser(CreateUserRequest) returns (User);
  rpc UpdateUser(UpdateUserRequest) returns (User);
  rpc DeleteUser(DeleteUserRequest) returns (google.protobuf.Empty);

  // Server streaming
  rpc ListUsers(ListUsersRequest) returns (stream User);

  // Client streaming
  rpc BatchCreateUsers(stream CreateUserRequest) returns (BatchCreateResponse);

  // Bidirectional streaming
  rpc Chat(stream ChatMessage) returns (stream ChatMessage);
}

message User {
  string id = 1;
  string name = 2;
  string email = 3;
  UserRole role = 4;
  google.protobuf.Timestamp created_at = 5;
  map<string, string> metadata = 6;
}

enum UserRole {
  USER_ROLE_UNSPECIFIED = 0;
  USER_ROLE_ADMIN = 1;
  USER_ROLE_USER = 2;
  USER_ROLE_VIEWER = 3;
}

message GetUserRequest {
  string id = 1;
}

message CreateUserRequest {
  string name = 1;
  string email = 2;
  UserRole role = 3;
}

message UpdateUserRequest {
  string id = 1;
  User user = 2;
  google.protobuf.FieldMask update_mask = 3;
}

message DeleteUserRequest {
  string id = 1;
}

message ListUsersRequest {
  int32 page_size = 1;
  string page_token = 2;
  string filter = 3;
}

message BatchCreateResponse {
  int32 created_count = 1;
  repeated string failed_emails = 2;
}

message ChatMessage {
  string user_id = 1;
  string content = 2;
  google.protobuf.Timestamp timestamp = 3;
}
```

```python
# --- Server implementation ---

import grpc
from concurrent import futures
import user_service_pb2
import user_service_pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp


class UserServicer(user_service_pb2_grpc.UserServiceServicer):

    def __init__(self, db):
        self.db = db

    def GetUser(self, request, context):
        user = self.db.get(request.id)
        if not user:
            context.abort(grpc.StatusCode.NOT_FOUND, f"User {request.id} not found")
        return self._to_proto(user)

    def CreateUser(self, request, context):
        # Validate
        if not request.email:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Email is required")

        user = self.db.create(
            name=request.name,
            email=request.email,
            role=request.role,
        )
        return self._to_proto(user)

    def ListUsers(self, request, context):
        """Server streaming — yield users one by one."""
        users = self.db.list(
            page_size=request.page_size or 100,
            page_token=request.page_token,
        )
        for user in users:
            yield self._to_proto(user)

    def BatchCreateUsers(self, request_iterator, context):
        """Client streaming — receive batch of users."""
        created = 0
        failed = []
        for request in request_iterator:
            try:
                self.db.create(name=request.name, email=request.email)
                created += 1
            except Exception:
                failed.append(request.email)

        return user_service_pb2.BatchCreateResponse(
            created_count=created,
            failed_emails=failed,
        )

    def _to_proto(self, user_dict):
        ts = Timestamp()
        ts.FromDatetime(user_dict["created_at"])
        return user_service_pb2.User(
            id=user_dict["id"],
            name=user_dict["name"],
            email=user_dict["email"],
            role=user_dict.get("role", 0),
            created_at=ts,
        )


def serve():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
        ],
    )
    user_service_pb2_grpc.add_UserServiceServicer_to_server(
        UserServicer(db), server,
    )
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()


# --- Client usage ---

def client_example():
    channel = grpc.insecure_channel("localhost:50051")
    stub = user_service_pb2_grpc.UserServiceStub(channel)

    # Unary call
    user = stub.GetUser(user_service_pb2.GetUserRequest(id="user-1"))
    print(f"Got user: {user.name}")

    # Server streaming
    for user in stub.ListUsers(user_service_pb2.ListUsersRequest(page_size=10)):
        print(f"User: {user.name}")

    # With timeout and metadata
    try:
        user = stub.GetUser(
            user_service_pb2.GetUserRequest(id="user-1"),
            timeout=5.0,
            metadata=[("authorization", "Bearer token123")],
        )
    except grpc.RpcError as e:
        print(f"Error: {e.code()} - {e.details()}")
```

gRPC patterns:
1. **Proto3 schema** — type-safe contract between client and server
2. **`context.abort()`** — return proper gRPC status codes on errors
3. **Server streaming** — `yield` responses for large result sets
4. **Client streaming** — batch operations via `request_iterator`
5. **`FieldMask`** — partial updates specify which fields to change'''
    ),
    (
        "patterns/event-driven",
        "Show event-driven architecture patterns: event bus, domain events, event sourcing lite, and CQRS.",
        '''Event-driven architecture patterns:

```python
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any
from datetime import datetime, timezone
from collections import defaultdict
import asyncio
import json
import uuid
import logging

logger = logging.getLogger(__name__)


# --- Domain events ---

@dataclass(frozen=True)
class DomainEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    aggregate_id: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


# Specific events
@dataclass(frozen=True)
class OrderCreated(DomainEvent):
    event_type: str = "order.created"

@dataclass(frozen=True)
class OrderPaid(DomainEvent):
    event_type: str = "order.paid"

@dataclass(frozen=True)
class OrderShipped(DomainEvent):
    event_type: str = "order.shipped"

@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    event_type: str = "order.cancelled"


# --- Event dispatcher ---

EventHandler = Callable[[DomainEvent], Awaitable[None]]

class EventDispatcher:
    """In-process event dispatcher with async handlers."""

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []

    def subscribe(self, event_type: str, handler: EventHandler):
        """Subscribe to specific event type."""
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler):
        """Subscribe to all events."""
        self._global_handlers.append(handler)

    async def dispatch(self, event: DomainEvent):
        """Dispatch event to all matching handlers."""
        handlers = (
            self._handlers.get(event.event_type, [])
            + self._global_handlers
        )

        if not handlers:
            logger.warning("No handlers for event: %s", event.event_type)
            return

        results = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Handler %d failed for %s: %s",
                    i, event.event_type, result,
                )

    async def dispatch_many(self, events: list[DomainEvent]):
        """Dispatch multiple events in order."""
        for event in events:
            await self.dispatch(event)


# --- Aggregate with domain events ---

class Order:
    """Aggregate that collects domain events."""

    def __init__(self, order_id: str, customer_id: str):
        self.id = order_id
        self.customer_id = customer_id
        self.status = "draft"
        self.total = 0.0
        self._events: list[DomainEvent] = []

    def place(self, items: list[dict]):
        self.total = sum(i["price"] * i["qty"] for i in items)
        self.status = "placed"
        self._events.append(OrderCreated(
            aggregate_id=self.id,
            data={"customer_id": self.customer_id, "total": self.total},
        ))

    def pay(self, payment_id: str):
        if self.status != "placed":
            raise ValueError(f"Cannot pay order in status {self.status}")
        self.status = "paid"
        self._events.append(OrderPaid(
            aggregate_id=self.id,
            data={"payment_id": payment_id, "total": self.total},
        ))

    def cancel(self, reason: str):
        if self.status in ("shipped", "delivered"):
            raise ValueError("Cannot cancel shipped order")
        self.status = "cancelled"
        self._events.append(OrderCancelled(
            aggregate_id=self.id,
            data={"reason": reason},
        ))

    def collect_events(self) -> list[DomainEvent]:
        events = self._events[:]
        self._events.clear()
        return events


# --- Event handlers (side effects) ---

async def send_order_confirmation(event: DomainEvent):
    """Send email when order is created."""
    logger.info("Sending confirmation for order %s", event.aggregate_id)

async def update_inventory(event: DomainEvent):
    """Reserve inventory when order is paid."""
    logger.info("Reserving inventory for order %s", event.aggregate_id)

async def log_event(event: DomainEvent):
    """Audit log — records all events."""
    logger.info("EVENT: %s %s %s",
                event.event_type, event.aggregate_id, event.data)


# --- Wire up ---

dispatcher = EventDispatcher()
dispatcher.subscribe("order.created", send_order_confirmation)
dispatcher.subscribe("order.paid", update_inventory)
dispatcher.subscribe_all(log_event)


# --- Usage in application service ---

class OrderService:
    def __init__(self, repo, dispatcher: EventDispatcher):
        self.repo = repo
        self.dispatcher = dispatcher

    async def place_order(self, customer_id: str, items: list[dict]) -> Order:
        order = Order(str(uuid.uuid4()), customer_id)
        order.place(items)
        await self.repo.save(order)

        # Dispatch events after successful persistence
        events = order.collect_events()
        await self.dispatcher.dispatch_many(events)

        return order
```

Event-driven patterns:
1. **Domain events** — immutable facts about what happened in the domain
2. **Aggregate events** — collect events during mutation, dispatch after save
3. **`subscribe()` + `dispatch()`** — decouple side effects from business logic
4. **`subscribe_all()`** — cross-cutting concerns (audit logging, metrics)
5. **Events after persistence** — dispatch only after DB commit succeeds'''
    ),
    (
        "api/json-schema",
        "Show JSON Schema patterns: validation, complex types, conditional schemas, and code generation.",
        '''JSON Schema patterns:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://api.example.com/schemas/order.json",
  "title": "Order",
  "description": "E-commerce order schema",
  "type": "object",

  "required": ["id", "customer_id", "items", "status"],

  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique order identifier"
    },
    "customer_id": {
      "type": "string",
      "format": "uuid"
    },
    "status": {
      "type": "string",
      "enum": ["draft", "pending", "confirmed", "shipped", "delivered", "cancelled"]
    },
    "items": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/OrderItem" }
    },
    "total": {
      "type": "number",
      "minimum": 0,
      "description": "Computed total in USD"
    },
    "shipping_address": {
      "$ref": "#/$defs/Address"
    },
    "metadata": {
      "type": "object",
      "additionalProperties": { "type": "string" },
      "maxProperties": 10
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "notes": {
      "type": ["string", "null"],
      "maxLength": 500
    }
  },

  "additionalProperties": false,

  "$defs": {
    "OrderItem": {
      "type": "object",
      "required": ["product_id", "quantity", "unit_price"],
      "properties": {
        "product_id": { "type": "string" },
        "quantity": {
          "type": "integer",
          "minimum": 1,
          "maximum": 9999
        },
        "unit_price": {
          "type": "number",
          "minimum": 0,
          "exclusiveMinimum": 0
        },
        "discount_percent": {
          "type": "number",
          "minimum": 0,
          "maximum": 100,
          "default": 0
        }
      },
      "additionalProperties": false
    },

    "Address": {
      "type": "object",
      "required": ["street", "city", "country"],
      "properties": {
        "street": { "type": "string", "minLength": 1 },
        "city": { "type": "string", "minLength": 1 },
        "state": { "type": "string" },
        "zip": {
          "type": "string",
          "pattern": "^[0-9]{5}(-[0-9]{4})?$"
        },
        "country": {
          "type": "string",
          "minLength": 2,
          "maxLength": 2,
          "description": "ISO 3166-1 alpha-2 code"
        }
      }
    }
  },

  "if": {
    "properties": {
      "status": { "const": "shipped" }
    }
  },
  "then": {
    "required": ["shipping_address"]
  }
}
```

```python
# --- Python validation with jsonschema ---

import jsonschema
import json
from pathlib import Path


def validate_order(order: dict) -> list[str]:
    """Validate order against JSON Schema."""
    schema = json.loads(Path("schemas/order.json").read_text())

    validator = jsonschema.Draft202012Validator(schema)
    errors = []

    for error in sorted(validator.iter_errors(order), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.path) or "(root)"
        errors.append(f"{path}: {error.message}")

    return errors


# --- Generate Pydantic models from schema ---

# pip install datamodel-code-generator
# datamodel-codegen --input schemas/order.json --output models/order.py
```

JSON Schema patterns:
1. **`$ref` + `$defs`** — reusable sub-schemas (Address, OrderItem)
2. **`format`** — semantic validation: uuid, email, date-time, uri
3. **`pattern`** — regex for structured strings (zip codes, phone numbers)
4. **`if`/`then`** — conditional requirements (shipped orders need address)
5. **`additionalProperties: false`** — reject unknown fields strictly'''
    ),
]
