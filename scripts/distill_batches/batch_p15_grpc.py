PAIRS = [
    (
        "networking/grpc-fundamentals",
        r"""Explain gRPC fundamentals including Protocol Buffers, service definition, the four communication patterns (unary, server streaming, client streaming, bidirectional), interceptors/middleware, error handling, and deadline propagation. Include Python examples with grpcio.""",
        r"""## gRPC Fundamentals: Protocol Buffers, Streaming, and Production Patterns

gRPC is a high-performance RPC framework that uses HTTP/2 for transport and Protocol Buffers for serialization. It's the standard for inter-service communication in microservice architectures where REST's overhead is too high.

### Protocol Buffers (Protobuf)

Define your service contract as a `.proto` file:

```protobuf
// service.proto
syntax = "proto3";

package orders.v1;

import "google/protobuf/timestamp.proto";

// Service definition
service OrderService {
    // Unary: one request, one response
    rpc CreateOrder(CreateOrderRequest) returns (CreateOrderResponse);
    rpc GetOrder(GetOrderRequest) returns (Order);

    // Server streaming: one request, stream of responses
    rpc WatchOrderStatus(WatchOrderRequest) returns (stream OrderStatusUpdate);

    // Client streaming: stream of requests, one response
    rpc BatchCreateOrders(stream CreateOrderRequest) returns (BatchCreateResponse);

    // Bidirectional streaming: both sides stream
    rpc OrderChat(stream OrderMessage) returns (stream OrderMessage);
}

message CreateOrderRequest {
    string customer_id = 1;
    repeated OrderItem items = 2;
    ShippingAddress shipping_address = 3;
}

message CreateOrderResponse {
    string order_id = 1;
    double total = 2;
    OrderStatus status = 3;
}

message Order {
    string order_id = 1;
    string customer_id = 2;
    repeated OrderItem items = 3;
    double total = 4;
    OrderStatus status = 5;
    google.protobuf.Timestamp created_at = 6;
}

message OrderItem {
    string product_id = 1;
    int32 quantity = 2;
    double unit_price = 3;
}

message ShippingAddress {
    string street = 1;
    string city = 2;
    string state = 3;
    string zip_code = 4;
}

enum OrderStatus {
    ORDER_STATUS_UNSPECIFIED = 0;
    ORDER_STATUS_DRAFT = 1;
    ORDER_STATUS_SUBMITTED = 2;
    ORDER_STATUS_PAID = 3;
    ORDER_STATUS_SHIPPED = 4;
}

message GetOrderRequest {
    string order_id = 1;
}

message WatchOrderRequest {
    string order_id = 1;
}

message OrderStatusUpdate {
    string order_id = 1;
    OrderStatus previous_status = 2;
    OrderStatus new_status = 3;
    google.protobuf.Timestamp updated_at = 4;
}

message BatchCreateResponse {
    int32 created_count = 1;
    repeated string order_ids = 2;
}

message OrderMessage {
    string order_id = 1;
    string sender = 2;
    string content = 3;
}
```

### Server Implementation

```python
# server.py
import grpc
from concurrent import futures
import asyncio
from uuid import uuid4
from datetime import datetime

import orders_pb2
import orders_pb2_grpc


class OrderServicer(orders_pb2_grpc.OrderServiceServicer):
    """gRPC service implementation."""

    def __init__(self):
        self.orders = {}  # In-memory for demo
        self.watchers = {}  # order_id -> list of queues

    def CreateOrder(self, request, context):
        """Unary RPC: create a single order."""
        order_id = str(uuid4())

        # Validate
        if not request.items:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Order must have at least one item")
            return orders_pb2.CreateOrderResponse()

        total = sum(item.unit_price * item.quantity for item in request.items)

        order = orders_pb2.Order(
            order_id=order_id,
            customer_id=request.customer_id,
            items=request.items,
            total=total,
            status=orders_pb2.ORDER_STATUS_SUBMITTED,
        )
        self.orders[order_id] = order

        return orders_pb2.CreateOrderResponse(
            order_id=order_id,
            total=total,
            status=orders_pb2.ORDER_STATUS_SUBMITTED,
        )

    def GetOrder(self, request, context):
        """Unary RPC with error handling."""
        order = self.orders.get(request.order_id)
        if not order:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Order {request.order_id} not found")
            return orders_pb2.Order()
        return order

    def WatchOrderStatus(self, request, context):
        """Server streaming: push status updates to client."""
        import queue
        import time

        order_id = request.order_id
        if order_id not in self.orders:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Order {order_id} not found")
            return

        # Register a watcher queue
        q = queue.Queue()
        self.watchers.setdefault(order_id, []).append(q)

        try:
            while context.is_active():
                try:
                    update = q.get(timeout=1.0)
                    yield update
                except queue.Empty:
                    continue
        finally:
            self.watchers[order_id].remove(q)

    def BatchCreateOrders(self, request_iterator, context):
        """Client streaming: receive multiple orders, return summary."""
        created_ids = []

        for request in request_iterator:
            order_id = str(uuid4())
            total = sum(
                item.unit_price * item.quantity for item in request.items
            )
            order = orders_pb2.Order(
                order_id=order_id,
                customer_id=request.customer_id,
                total=total,
                status=orders_pb2.ORDER_STATUS_SUBMITTED,
            )
            self.orders[order_id] = order
            created_ids.append(order_id)

        return orders_pb2.BatchCreateResponse(
            created_count=len(created_ids),
            order_ids=created_ids,
        )

    def OrderChat(self, request_iterator, context):
        """Bidirectional streaming: real-time order discussion."""
        for message in request_iterator:
            # Echo back with server processing
            response = orders_pb2.OrderMessage(
                order_id=message.order_id,
                sender="server",
                content=f"Received: {message.content}",
            )
            yield response


def serve():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 5000),
        ],
    )
    orders_pb2_grpc.add_OrderServiceServicer_to_server(
        OrderServicer(), server
    )
    server.add_insecure_port("[::]:50051")
    server.start()
    print("Server started on port 50051")
    server.wait_for_termination()
```

### Client Implementation

```python
# client.py
import grpc
import orders_pb2
import orders_pb2_grpc


def create_channel(target: str = "localhost:50051") -> grpc.Channel:
    """Create a gRPC channel with proper options."""
    options = [
        ("grpc.keepalive_time_ms", 30000),
        ("grpc.keepalive_timeout_ms", 5000),
        ("grpc.enable_retries", 1),
        ("grpc.service_config", '{"retryPolicy": {'
         '"maxAttempts": 3, "initialBackoff": "0.1s",'
         '"maxBackoff": "1s", "backoffMultiplier": 2,'
         '"retryableStatusCodes": ["UNAVAILABLE"]}}'),
    ]
    return grpc.insecure_channel(target, options=options)


def demo_unary():
    """Unary call with deadline."""
    with create_channel() as channel:
        stub = orders_pb2_grpc.OrderServiceStub(channel)

        request = orders_pb2.CreateOrderRequest(
            customer_id="cust-123",
            items=[
                orders_pb2.OrderItem(
                    product_id="prod-1", quantity=2, unit_price=29.99
                ),
            ],
            shipping_address=orders_pb2.ShippingAddress(
                street="123 Main St", city="Seattle",
                state="WA", zip_code="98101",
            ),
        )

        try:
            # Set deadline (timeout)
            response = stub.CreateOrder(
                request, timeout=5.0  # 5 second deadline
            )
            print(f"Created order: {response.order_id}, total: {response.total}")
        except grpc.RpcError as e:
            print(f"RPC failed: {e.code()} - {e.details()}")


def demo_server_streaming():
    """Consume server stream."""
    with create_channel() as channel:
        stub = orders_pb2_grpc.OrderServiceStub(channel)

        request = orders_pb2.WatchOrderRequest(order_id="order-123")

        try:
            for update in stub.WatchOrderStatus(request, timeout=60.0):
                print(f"Status update: {update.new_status}")
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                print("Watch timed out")
            else:
                raise


def demo_client_streaming():
    """Send a stream of orders."""
    with create_channel() as channel:
        stub = orders_pb2_grpc.OrderServiceStub(channel)

        def order_generator():
            for i in range(10):
                yield orders_pb2.CreateOrderRequest(
                    customer_id=f"cust-{i}",
                    items=[orders_pb2.OrderItem(
                        product_id=f"prod-{i}",
                        quantity=1,
                        unit_price=19.99,
                    )],
                )

        response = stub.BatchCreateOrders(order_generator())
        print(f"Created {response.created_count} orders")
```

### Interceptors (Middleware)

```python
import time
import logging
import grpc

logger = logging.getLogger(__name__)


class LoggingInterceptor(grpc.UnaryUnaryClientInterceptor):
    """Client-side logging interceptor."""

    def intercept_unary_unary(self, continuation, client_call_details, request):
        method = client_call_details.method
        start = time.monotonic()

        response = continuation(client_call_details, request)

        elapsed = (time.monotonic() - start) * 1000
        logger.info(f"gRPC {method} completed in {elapsed:.1f}ms")

        return response


class AuthInterceptor(grpc.ServerInterceptor):
    """Server-side authentication interceptor."""

    def __init__(self, valid_tokens: set):
        self.valid_tokens = valid_tokens

    def intercept_service(self, continuation, handler_call_details):
        # Extract metadata
        metadata = dict(handler_call_details.invocation_metadata)
        token = metadata.get("authorization", "")

        if not token.startswith("Bearer "):
            return self._unauthenticated()

        token_value = token[7:]
        if token_value not in self.valid_tokens:
            return self._unauthenticated()

        return continuation(handler_call_details)

    def _unauthenticated(self):
        def abort(ignored_request, context):
            context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Invalid or missing authentication token"
            )
        return grpc.unary_unary_rpc_method_handler(abort)


# Apply interceptors
channel = grpc.intercept_channel(
    grpc.insecure_channel("localhost:50051"),
    LoggingInterceptor(),
)

server = grpc.server(
    futures.ThreadPoolExecutor(max_workers=10),
    interceptors=[AuthInterceptor({"valid-token-123"})],
)
```

### Error Handling and Status Codes

```python
# gRPC status codes (map to HTTP):
# OK (200)              - Success
# CANCELLED (499)       - Client cancelled
# INVALID_ARGUMENT (400)- Bad request
# NOT_FOUND (404)       - Resource not found
# ALREADY_EXISTS (409)  - Conflict
# PERMISSION_DENIED (403)- Forbidden
# UNAUTHENTICATED (401) - No/invalid auth
# RESOURCE_EXHAUSTED(429)- Rate limited
# UNAVAILABLE (503)     - Service down
# DEADLINE_EXCEEDED (504)- Timeout
# INTERNAL (500)        - Server error
# UNIMPLEMENTED (501)   - Not implemented

# Rich error details
from google.protobuf import any_pb2
from google.rpc import status_pb2, error_details_pb2

def set_rich_error(context, code, message, violations=None):
    """Set detailed error information."""
    status = status_pb2.Status(
        code=code.value[0],
        message=message,
    )

    if violations:
        bad_request = error_details_pb2.BadRequest()
        for field, desc in violations:
            violation = bad_request.field_violations.add()
            violation.field = field
            violation.description = desc

        detail = any_pb2.Any()
        detail.Pack(bad_request)
        status.details.append(detail)

    context.abort_with_status(
        rpc_status.to_status(status)
    )
```

**gRPC vs REST decision**: (1) Use gRPC for internal service-to-service communication — 2-10x faster than JSON/REST, (2) Use REST for public APIs — browser compatibility and wider tooling, (3) Server streaming replaces WebSockets for server push, (4) Bidirectional streaming for real-time collaboration features, (5) Always set deadlines — gRPC propagates them across service boundaries automatically."""
    ),
    (
        "networking/message-queues-patterns",
        r"""Explain message queue patterns including point-to-point vs pub-sub, exactly-once delivery, dead letter queues, message ordering, idempotent consumers, and backpressure handling. Compare Kafka, RabbitMQ, and Redis Streams for different use cases.""",
        r"""## Message Queue Patterns: Delivery Guarantees, Ordering, and System Selection

Message queues decouple producers from consumers, enabling asynchronous processing, load leveling, and fault tolerance. The choice of queue system and patterns depends on your consistency and ordering requirements.

### Messaging Patterns

```
Point-to-Point (Queue):
  Producer → [Queue] → Consumer
  Each message is processed by exactly ONE consumer
  Use for: task distribution, work queues

Publish-Subscribe (Topic):
  Producer → [Topic] → Consumer A
                    → Consumer B
                    → Consumer C
  Each message goes to ALL subscribers
  Use for: event broadcasting, notifications

Consumer Group (Kafka-style):
  Producer → [Topic/Partition 0] → Consumer Group A, Consumer 1
                                 → Consumer Group B, Consumer 1
           → [Topic/Partition 1] → Consumer Group A, Consumer 2
                                 → Consumer Group B, Consumer 2
  Messages partitioned for parallel processing within a group
  Use for: high-throughput event processing
```

### Idempotent Consumers

The most important pattern — process messages safely even if delivered more than once:

```python
import hashlib
import json
from datetime import datetime, timedelta


class IdempotentConsumer:
    """Ensures each message is processed exactly once."""

    def __init__(self, redis_client, ttl_hours: int = 24):
        self.redis = redis_client
        self.ttl = timedelta(hours=ttl_hours)

    def process_if_new(self, message_id: str, handler, message: dict) -> bool:
        """Process message only if not already processed."""
        dedup_key = f"processed:{message_id}"

        # Atomic check-and-set
        was_set = self.redis.set(
            dedup_key, "1",
            nx=True,  # Only set if not exists
            ex=int(self.ttl.total_seconds()),
        )

        if not was_set:
            # Already processed
            return False

        try:
            handler(message)
            return True
        except Exception:
            # Processing failed — remove dedup key so retry works
            self.redis.delete(dedup_key)
            raise

    @staticmethod
    def generate_idempotency_key(message: dict) -> str:
        """Generate a deterministic key from message content."""
        content = json.dumps(message, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# Usage:
consumer = IdempotentConsumer(redis_client)

def handle_payment(message: dict):
    """This handler might be called multiple times for the same message."""
    # With idempotent consumer wrapper, it executes only once
    charge_customer(message["customer_id"], message["amount"])

# Even if message arrives 3 times, payment happens once
for msg in queue.consume():
    consumer.process_if_new(msg.id, handle_payment, msg.body)
```

### Dead Letter Queues (DLQ)

Handle messages that repeatedly fail processing:

```python
class MessageProcessor:
    """Process messages with retry and dead letter queue."""

    def __init__(self, main_queue, dlq, max_retries: int = 3):
        self.main_queue = main_queue
        self.dlq = dlq
        self.max_retries = max_retries

    async def process_loop(self):
        while True:
            message = await self.main_queue.receive()
            if not message:
                await asyncio.sleep(1)
                continue

            retry_count = message.metadata.get("retry_count", 0)

            try:
                await self.handle(message)
                await self.main_queue.acknowledge(message.id)
            except TransientError:
                # Transient failure — retry with backoff
                if retry_count < self.max_retries:
                    message.metadata["retry_count"] = retry_count + 1
                    delay = 2 ** retry_count  # Exponential backoff
                    await self.main_queue.requeue(message, delay_seconds=delay)
                else:
                    # Max retries exceeded — send to DLQ
                    await self.dlq.send(message, reason="max_retries_exceeded")
                    await self.main_queue.acknowledge(message.id)
            except PermanentError as e:
                # Permanent failure — DLQ immediately
                await self.dlq.send(message, reason=str(e))
                await self.main_queue.acknowledge(message.id)

    async def handle(self, message):
        """Override in subclass."""
        raise NotImplementedError


# DLQ processor — manual review or automated recovery
class DLQProcessor:
    def __init__(self, dlq, main_queue):
        self.dlq = dlq
        self.main_queue = main_queue

    async def replay_all(self):
        """Replay DLQ messages back to main queue."""
        while True:
            message = await self.dlq.receive()
            if not message:
                break
            # Reset retry count
            message.metadata["retry_count"] = 0
            message.metadata["replayed_from_dlq"] = True
            await self.main_queue.send(message)
            await self.dlq.acknowledge(message.id)
```

### Comparison: Kafka vs RabbitMQ vs Redis Streams

```python
# KAFKA: High-throughput, ordered, persistent log
# Best for: Event streaming, analytics pipelines, audit logs
# Ordering: Per-partition guaranteed
# Delivery: At-least-once (exactly-once with transactions)
# Retention: Time or size-based (can keep forever)

from confluent_kafka import Producer, Consumer

# Producer
producer = Producer({"bootstrap.servers": "localhost:9092"})
producer.produce(
    topic="orders",
    key=order.customer_id.encode(),  # Partition key for ordering
    value=json.dumps(order_event).encode(),
)
producer.flush()

# Consumer (with consumer group)
consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "payment-service",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,  # Manual commit for at-least-once
})
consumer.subscribe(["orders"])

while True:
    msg = consumer.poll(timeout=1.0)
    if msg and not msg.error():
        process_order(json.loads(msg.value()))
        consumer.commit(msg)  # Commit after processing


# RABBITMQ: Feature-rich, flexible routing, traditional queue
# Best for: Task queues, complex routing, request-reply
# Ordering: Per-queue FIFO
# Delivery: At-least-once (with publisher confirms + consumer acks)
# Retention: Until consumed (or TTL)

import pika

connection = pika.BlockingConnection(
    pika.ConnectionParameters("localhost")
)
channel = connection.channel()

# Declare with dead letter exchange
channel.queue_declare(
    queue="orders",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "dlx",
        "x-message-ttl": 300000,  # 5 min TTL
        "x-max-length": 100000,   # Max queue size
    },
)

# Publish with confirmation
channel.confirm_delivery()
channel.basic_publish(
    exchange="",
    routing_key="orders",
    body=json.dumps(order_event),
    properties=pika.BasicProperties(
        delivery_mode=2,  # Persistent
        content_type="application/json",
        message_id=str(uuid4()),
    ),
)

# Consume with manual ack
def callback(ch, method, properties, body):
    try:
        process_order(json.loads(body))
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        ch.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=False,  # Send to DLQ instead
        )

channel.basic_qos(prefetch_count=10)  # Backpressure
channel.basic_consume(queue="orders", on_message_callback=callback)


# REDIS STREAMS: Lightweight, built-in, good for moderate throughput
# Best for: Simple event streaming, real-time notifications
# Ordering: Global order within a stream
# Delivery: At-least-once (with consumer groups + ack)
# Retention: Configurable maxlen or time-based

import redis

r = redis.Redis()

# Produce
r.xadd("orders", {"event": json.dumps(order_event)}, maxlen=100000)

# Consumer group
r.xgroup_create("orders", "payment-svc", id="0", mkstream=True)

while True:
    messages = r.xreadgroup(
        "payment-svc", "worker-1",
        {"orders": ">"},
        count=10, block=5000,
    )
    for stream, msgs in (messages or []):
        for msg_id, data in msgs:
            process_order(json.loads(data[b"event"]))
            r.xack("orders", "payment-svc", msg_id)
```

### Choosing the Right System

| Requirement | Kafka | RabbitMQ | Redis Streams |
|-------------|-------|----------|---------------|
| Throughput | 1M+ msg/s | 50K msg/s | 100K msg/s |
| Ordering | Per-partition | Per-queue | Global |
| Replay | Yes (log-based) | No | Limited |
| Routing | Topic-based | Complex (exchanges) | Simple |
| Latency | ~5ms | ~1ms | ~0.5ms |
| Persistence | Excellent | Good | Good |
| Operations | Complex | Moderate | Simple |

**Message queue principles**: (1) Always design idempotent consumers — at-least-once delivery is the practical reality, (2) Use dead letter queues for messages that can't be processed, (3) Partition by entity ID for ordering (e.g., all events for order-123 go to the same partition), (4) Set message TTLs to prevent unbounded queue growth, (5) Monitor consumer lag — growing lag means consumers can't keep up."""
    ),
    (
        "security/oauth2-oidc-deep-dive",
        r"""Explain OAuth 2.0 and OpenID Connect in depth including authorization code flow with PKCE, token types (access, refresh, ID), JWT structure and validation, token introspection, scopes and claims, and secure implementation patterns for SPAs and APIs.""",
        r"""## OAuth 2.0 and OpenID Connect: Authorization Flows, JWT, and Secure Implementation

OAuth 2.0 handles **authorization** (what can you access?) while OpenID Connect (OIDC) adds **authentication** (who are you?) on top. Understanding both is essential for building secure applications.

### Authorization Code Flow with PKCE

The recommended flow for all clients (SPAs, mobile, server-side):

```python
import hashlib
import base64
import secrets
import urllib.parse
from dataclasses import dataclass


@dataclass
class PKCEChallenge:
    code_verifier: str
    code_challenge: str
    code_challenge_method: str = "S256"


def generate_pkce() -> PKCEChallenge:
    """Generate PKCE code verifier and challenge."""
    # Random 43-128 character string
    code_verifier = secrets.token_urlsafe(32)

    # SHA-256 hash of verifier, base64url-encoded
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    return PKCEChallenge(
        code_verifier=code_verifier,
        code_challenge=code_challenge,
    )


def build_authorization_url(
    auth_endpoint: str,
    client_id: str,
    redirect_uri: str,
    pkce: PKCEChallenge,
    scopes: list[str] = None,
) -> tuple[str, str]:
    """Build the authorization URL. Returns (url, state)."""
    state = secrets.token_urlsafe(16)  # CSRF protection
    nonce = secrets.token_urlsafe(16)  # Replay protection

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes or ["openid", "profile", "email"]),
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": pkce.code_challenge_method,
    }

    url = f"{auth_endpoint}?{urllib.parse.urlencode(params)}"
    return url, state


# Step 1: Generate PKCE and redirect user to auth server
pkce = generate_pkce()
auth_url, state = build_authorization_url(
    auth_endpoint="https://auth.example.com/authorize",
    client_id="my-app",
    redirect_uri="https://myapp.com/callback",
    pkce=pkce,
    scopes=["openid", "profile", "email", "orders:read"],
)
# Store state and code_verifier in session (server) or sessionStorage (SPA)
# Redirect user to auth_url
```

```python
# Step 2: Handle the callback — exchange code for tokens
import httpx


async def exchange_code_for_tokens(
    token_endpoint: str,
    code: str,
    code_verifier: str,
    client_id: str,
    redirect_uri: str,
    client_secret: str = None,  # Only for confidential clients
) -> dict:
    """Exchange authorization code for tokens."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,  # PKCE proof
    }
    if client_secret:
        data["client_secret"] = client_secret

    async with httpx.AsyncClient() as client:
        response = await client.post(token_endpoint, data=data)
        response.raise_for_status()
        return response.json()

    # Returns:
    # {
    #   "access_token": "eyJhbG...",   # For API calls
    #   "token_type": "Bearer",
    #   "expires_in": 3600,
    #   "refresh_token": "dGhpcy...",  # For getting new access tokens
    #   "id_token": "eyJhbG...",       # OIDC: user identity (JWT)
    #   "scope": "openid profile email orders:read"
    # }
```

### JWT Structure and Validation

```python
import jwt
import httpx
from datetime import datetime, timezone
from typing import Optional


class JWTValidator:
    """Validate JWT access tokens and ID tokens."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_uri: str,
    ):
        self.issuer = issuer
        self.audience = audience
        self.jwks_uri = jwks_uri
        self._jwks_cache = None
        self._jwks_cache_time = 0

    async def _get_signing_keys(self) -> dict:
        """Fetch JWKS (JSON Web Key Set) from auth server."""
        import time
        now = time.time()
        if self._jwks_cache and now - self._jwks_cache_time < 3600:
            return self._jwks_cache

        async with httpx.AsyncClient() as client:
            response = await client.get(self.jwks_uri)
            self._jwks_cache = response.json()
            self._jwks_cache_time = now
            return self._jwks_cache

    async def validate_token(self, token: str) -> dict:
        """Validate and decode a JWT token."""
        # Step 1: Decode header without verification to get key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            raise TokenValidationError("Token missing 'kid' header")

        # Step 2: Get the signing key from JWKS
        jwks = await self._get_signing_keys()
        signing_key = None
        for key in jwks.get("keys", []):
            if key["kid"] == kid:
                signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                break

        if not signing_key:
            raise TokenValidationError(f"Unknown signing key: {kid}")

        # Step 3: Verify and decode
        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "require": ["exp", "iss", "aud", "sub"],
                },
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise TokenValidationError("Token has expired")
        except jwt.InvalidIssuerError:
            raise TokenValidationError("Invalid token issuer")
        except jwt.InvalidAudienceError:
            raise TokenValidationError("Invalid token audience")
        except jwt.InvalidTokenError as e:
            raise TokenValidationError(f"Invalid token: {e}")


class TokenValidationError(Exception):
    pass
```

### Scope-Based Authorization

```python
from functools import wraps
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer()
validator = JWTValidator(
    issuer="https://auth.example.com",
    audience="https://api.example.com",
    jwks_uri="https://auth.example.com/.well-known/jwks.json",
)


def require_scopes(*required_scopes: str):
    """Decorator to enforce scope-based access control."""
    async def verify(
        credentials: HTTPAuthorizationCredentials = Security(security),
    ) -> dict:
        token = credentials.credentials
        payload = await validator.validate_token(token)

        # Check scopes
        token_scopes = set(payload.get("scope", "").split())
        missing = set(required_scopes) - token_scopes

        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required scopes: {missing}",
                headers={"WWW-Authenticate": f'Bearer scope="{" ".join(required_scopes)}"'},
            )

        return payload

    return verify


# Usage in FastAPI routes
@app.get("/api/orders")
async def list_orders(
    user: dict = Depends(require_scopes("orders:read")),
):
    user_id = user["sub"]
    return await get_orders_for_user(user_id)


@app.delete("/api/orders/{order_id}")
async def cancel_order(
    order_id: str,
    user: dict = Depends(require_scopes("orders:write", "orders:delete")),
):
    return await cancel_order_for_user(user["sub"], order_id)
```

### Token Refresh

```python
class TokenManager:
    """Manage access and refresh tokens."""

    def __init__(self, token_endpoint: str, client_id: str):
        self.token_endpoint = token_endpoint
        self.client_id = client_id
        self._access_token = None
        self._refresh_token = None
        self._expires_at = 0

    async def get_access_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        import time
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token  # Still valid (with 60s buffer)

        if self._refresh_token:
            await self._refresh()
        else:
            raise AuthenticationRequired("No refresh token available")

        return self._access_token

    async def _refresh(self):
        """Use refresh token to get new access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self.client_id,
                },
            )

            if response.status_code == 401:
                # Refresh token expired/revoked
                self._refresh_token = None
                raise AuthenticationRequired("Refresh token expired")

            response.raise_for_status()
            tokens = response.json()

            import time
            self._access_token = tokens["access_token"]
            self._expires_at = time.time() + tokens["expires_in"]

            # Rotation: auth server may issue new refresh token
            if "refresh_token" in tokens:
                self._refresh_token = tokens["refresh_token"]
```

**OAuth2/OIDC security rules**: (1) Always use PKCE — even for confidential clients (defense in depth), (2) Validate JWTs with the issuer's public keys (JWKS), never skip verification, (3) Store refresh tokens securely — they're equivalent to long-lived credentials, (4) Use short-lived access tokens (5-15 min) with refresh token rotation, (5) Check scopes for authorization — don't rely solely on authentication, (6) Validate `iss`, `aud`, `exp`, and `nonce` claims on every token."""
    ),
]
