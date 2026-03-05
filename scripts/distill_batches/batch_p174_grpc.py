"""gRPC patterns — protobuf services, streaming (server/client/bidi), interceptors, health checks, gRPC-web gateway, load balancing."""

PAIRS = [
    (
        "grpc/protobuf-service-definitions",
        "Show how to define gRPC services with Protocol Buffers and implement them in Python, including request/response messages, enums, oneof fields, and service methods.",
        '''gRPC service definitions with Protocol Buffers and Python implementation:

```protobuf
// order_service.proto
syntax = "proto3";

package ordering.v1;

import "google/protobuf/timestamp.proto";
import "google/protobuf/field_mask.proto";
import "google/protobuf/wrappers.proto";

option go_package = "github.com/myco/ordering/v1;orderingv1";

// ── Messages ─────────────────────────────────────────────────────

enum OrderStatus {
    ORDER_STATUS_UNSPECIFIED = 0;
    ORDER_STATUS_PENDING = 1;
    ORDER_STATUS_CONFIRMED = 2;
    ORDER_STATUS_SHIPPED = 3;
    ORDER_STATUS_DELIVERED = 4;
    ORDER_STATUS_CANCELLED = 5;
}

message Money {
    string currency_code = 1;    // ISO 4217
    int64 units = 2;             // whole units
    int32 nanos = 3;             // nano units (10^-9)
}

message Address {
    string street = 1;
    string city = 2;
    string state = 3;
    string postal_code = 4;
    string country_code = 5;
}

message OrderItem {
    string product_id = 1;
    string name = 2;
    int32 quantity = 3;
    Money unit_price = 4;
}

message Order {
    string order_id = 1;
    string customer_id = 2;
    repeated OrderItem items = 3;
    OrderStatus status = 4;
    Money total = 5;
    Address shipping_address = 6;
    google.protobuf.Timestamp created_at = 7;
    google.protobuf.Timestamp updated_at = 8;

    oneof payment {
        CreditCardPayment credit_card = 9;
        BankTransferPayment bank_transfer = 10;
    }
}

message CreditCardPayment {
    string token = 1;
    string last_four = 2;
}

message BankTransferPayment {
    string routing_number = 1;
    string account_last_four = 2;
}

// ── Request/Response ─────────────────────────────────────────────

message CreateOrderRequest {
    string customer_id = 1;
    repeated OrderItem items = 2;
    Address shipping_address = 3;
    oneof payment {
        CreditCardPayment credit_card = 4;
        BankTransferPayment bank_transfer = 5;
    }
}

message CreateOrderResponse {
    Order order = 1;
}

message GetOrderRequest {
    string order_id = 1;
    google.protobuf.FieldMask field_mask = 2;
}

message ListOrdersRequest {
    string customer_id = 1;
    int32 page_size = 2;
    string page_token = 3;
    OrderStatus status_filter = 4;
}

message ListOrdersResponse {
    repeated Order orders = 1;
    string next_page_token = 2;
    int32 total_count = 3;
}

message UpdateOrderStatusRequest {
    string order_id = 1;
    OrderStatus new_status = 2;
    google.protobuf.StringValue reason = 3;
}

// ── Service Definition ───────────────────────────────────────────

service OrderService {
    rpc CreateOrder(CreateOrderRequest) returns (CreateOrderResponse);
    rpc GetOrder(GetOrderRequest) returns (Order);
    rpc ListOrders(ListOrdersRequest) returns (ListOrdersResponse);
    rpc UpdateOrderStatus(UpdateOrderStatusRequest) returns (Order);
    rpc StreamOrderUpdates(GetOrderRequest) returns (stream Order);
}
```

```python
# order_service_impl.py — Python server implementation
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import grpc
from google.protobuf import field_mask_pb2, timestamp_pb2

# Generated stubs (from: python -m grpc_tools.protoc ...)
from ordering.v1 import order_service_pb2 as pb2
from ordering.v1 import order_service_pb2_grpc as pb2_grpc


class OrderServiceImpl(pb2_grpc.OrderServiceServicer):
    """gRPC service implementation for order management."""

    def __init__(self) -> None:
        self._orders: dict[str, pb2.Order] = {}
        self._subscribers: dict[str, list[grpc.aio.ServicerContext]] = {}

    async def CreateOrder(
        self,
        request: pb2.CreateOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb2.CreateOrderResponse:
        # Validate required fields
        if not request.customer_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "customer_id is required",
            )
        if not request.items:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "at least one item is required",
            )

        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        now = timestamp_pb2.Timestamp()
        now.FromDatetime(datetime.now(timezone.utc))

        # Calculate total
        total_units = sum(
            item.unit_price.units * item.quantity for item in request.items
        )

        order = pb2.Order(
            order_id=order_id,
            customer_id=request.customer_id,
            items=list(request.items),
            status=pb2.ORDER_STATUS_PENDING,
            total=pb2.Money(currency_code="USD", units=total_units),
            shipping_address=request.shipping_address,
            created_at=now,
            updated_at=now,
        )

        # Copy the oneof payment field
        payment_field = request.WhichOneof("payment")
        if payment_field == "credit_card":
            order.credit_card.CopyFrom(request.credit_card)
        elif payment_field == "bank_transfer":
            order.bank_transfer.CopyFrom(request.bank_transfer)

        self._orders[order_id] = order

        # Set response metadata
        await context.send_initial_metadata([
            ("x-order-id", order_id),
        ])

        return pb2.CreateOrderResponse(order=order)

    async def GetOrder(
        self,
        request: pb2.GetOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb2.Order:
        order = self._orders.get(request.order_id)
        if not order:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Order {request.order_id} not found",
            )

        # Apply field mask if specified
        if request.HasField("field_mask") and request.field_mask.paths:
            filtered = pb2.Order()
            request.field_mask.MergeMessage(order, filtered)
            return filtered

        return order

    async def ListOrders(
        self,
        request: pb2.ListOrdersRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb2.ListOrdersResponse:
        orders = [
            o for o in self._orders.values()
            if o.customer_id == request.customer_id
            and (request.status_filter == pb2.ORDER_STATUS_UNSPECIFIED
                 or o.status == request.status_filter)
        ]

        page_size = request.page_size or 20
        start = 0
        if request.page_token:
            start = int(request.page_token)

        page = orders[start:start + page_size]
        next_token = str(start + page_size) if start + page_size < len(orders) else ""

        return pb2.ListOrdersResponse(
            orders=page,
            next_page_token=next_token,
            total_count=len(orders),
        )

    async def StreamOrderUpdates(
        self,
        request: pb2.GetOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[pb2.Order]:
        """Server-streaming: push order status changes to the client."""
        order_id = request.order_id
        if order_id not in self._orders:
            await context.abort(grpc.StatusCode.NOT_FOUND, "Order not found")

        # Send current state immediately
        yield self._orders[order_id]

        # Then stream updates as they happen
        import asyncio
        queue: asyncio.Queue[pb2.Order] = asyncio.Queue()
        self._subscribers.setdefault(order_id, []).append(queue)

        try:
            while not context.cancelled():
                try:
                    updated = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield updated
                except asyncio.TimeoutError:
                    # Send heartbeat (same order, no change)
                    yield self._orders[order_id]
        finally:
            self._subscribers[order_id].remove(queue)
```

Best practices for protobuf service design:

| Practice | Rationale |
|---|---|
| Use wrapper types for optional scalars | Distinguish "not set" from zero/empty |
| Always include `_UNSPECIFIED = 0` enum | Protobuf default; detect missing values |
| Use `FieldMask` for partial reads/updates | Reduce bandwidth, support sparse updates |
| Paginate with opaque `page_token` | Cursor-based is more efficient than offset |
| Use `oneof` for mutually exclusive fields | Type-safe polymorphism in messages |
| Version packages (`v1`, `v2`) | Non-breaking evolution path |
| Set `go_package` / language options | Multi-language codegen compatibility |

Key patterns:
- Generate stubs with `python -m grpc_tools.protoc --python_out=. --grpc_python_out=. --pyi_out=. -I. order_service.proto`
- Use `grpc.aio` for async server/client (the modern Python gRPC API)
- Always validate inputs and return proper gRPC status codes
- Use `context.abort()` rather than raising exceptions directly
'''
    ),
    (
        "grpc/streaming-patterns",
        "Implement all four gRPC streaming patterns in Python: unary, server streaming, client streaming, and bidirectional streaming with proper error handling and flow control.",
        '''All four gRPC streaming patterns with error handling and flow control:

```protobuf
// analytics_service.proto
syntax = "proto3";
package analytics.v1;

import "google/protobuf/timestamp.proto";

message Event {
    string event_id = 1;
    string user_id = 2;
    string event_type = 3;
    map<string, string> properties = 4;
    google.protobuf.Timestamp timestamp = 5;
}

message EventAck {
    string event_id = 1;
    bool accepted = 2;
    string reason = 3;
}

message MetricQuery {
    string metric_name = 1;
    google.protobuf.Timestamp start = 2;
    google.protobuf.Timestamp end = 3;
    int32 interval_seconds = 4;
}

message MetricPoint {
    google.protobuf.Timestamp timestamp = 1;
    double value = 2;
    map<string, string> labels = 3;
}

message ChatMessage {
    string session_id = 1;
    string sender = 2;
    string content = 3;
    google.protobuf.Timestamp sent_at = 4;
}

message BatchResult {
    int32 total_received = 1;
    int32 total_accepted = 2;
    int32 total_rejected = 3;
}

service AnalyticsService {
    // Unary RPC
    rpc RecordEvent(Event) returns (EventAck);
    // Server streaming
    rpc StreamMetrics(MetricQuery) returns (stream MetricPoint);
    // Client streaming
    rpc BatchIngest(stream Event) returns (BatchResult);
    // Bidirectional streaming
    rpc LiveChat(stream ChatMessage) returns (stream ChatMessage);
}
```

```python
# streaming_impl.py — all four gRPC streaming patterns
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import AsyncIterator

import grpc
from google.protobuf import timestamp_pb2

from analytics.v1 import analytics_pb2 as pb2
from analytics.v1 import analytics_pb2_grpc as pb2_grpc


class AnalyticsServiceImpl(pb2_grpc.AnalyticsServiceServicer):
    """Demonstrates all four gRPC communication patterns."""

    def __init__(self) -> None:
        self._events: list[pb2.Event] = []
        self._chat_rooms: dict[str, list[asyncio.Queue]] = defaultdict(list)

    # ── 1. Unary RPC ──────────────────────────────────────────────

    async def RecordEvent(
        self,
        request: pb2.Event,
        context: grpc.aio.ServicerContext,
    ) -> pb2.EventAck:
        """Simple request-response."""
        if not request.event_type:
            return pb2.EventAck(
                event_id=request.event_id,
                accepted=False,
                reason="event_type is required",
            )

        self._events.append(request)

        # Set trailing metadata with processing info
        await context.set_trailing_metadata([
            ("x-processing-time-ms", "2"),
        ])

        return pb2.EventAck(event_id=request.event_id, accepted=True)

    # ── 2. Server Streaming ───────────────────────────────────────

    async def StreamMetrics(
        self,
        request: pb2.MetricQuery,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[pb2.MetricPoint]:
        """Server pushes a stream of metric data points to the client.

        Handles client cancellation and implements backpressure
        by checking context.cancelled() between sends.
        """
        import math
        import random

        start_ts = request.start.ToDatetime().timestamp()
        end_ts = request.end.ToDatetime().timestamp()
        interval = request.interval_seconds or 60

        current = start_ts
        points_sent = 0

        while current <= end_ts:
            # Check if client cancelled the stream
            if context.cancelled():
                return

            ts = timestamp_pb2.Timestamp()
            ts.FromDatetime(datetime.fromtimestamp(current, tz=timezone.utc))

            # Simulate metric data with some noise
            base_value = 50.0 + 30.0 * math.sin(current / 3600)
            noise = random.gauss(0, 5)

            yield pb2.MetricPoint(
                timestamp=ts,
                value=base_value + noise,
                labels={"metric": request.metric_name, "source": "stream"},
            )

            points_sent += 1
            current += interval

            # Flow control: yield to event loop every 100 points
            if points_sent % 100 == 0:
                await asyncio.sleep(0)

        # Set trailing metadata after stream completes
        await context.set_trailing_metadata([
            ("x-points-sent", str(points_sent)),
        ])

    # ── 3. Client Streaming ───────────────────────────────────────

    async def BatchIngest(
        self,
        request_iterator: AsyncIterator[pb2.Event],
        context: grpc.aio.ServicerContext,
    ) -> pb2.BatchResult:
        """Client streams events; server responds with a summary.

        Implements backpressure by processing at server\'s pace.
        Handles errors gracefully without dropping the entire batch.
        """
        total = 0
        accepted = 0
        rejected = 0

        try:
            async for event in request_iterator:
                total += 1

                # Validate each event
                if not event.event_type or not event.user_id:
                    rejected += 1
                    continue

                # Check size limits
                if len(event.properties) > 50:
                    rejected += 1
                    continue

                self._events.append(event)
                accepted += 1

                # Periodically flush / yield control
                if total % 1000 == 0:
                    await asyncio.sleep(0)

        except grpc.aio.AioRpcError as e:
            # Client may disconnect mid-stream
            await context.set_trailing_metadata([
                ("x-error", str(e.code())),
            ])

        return pb2.BatchResult(
            total_received=total,
            total_accepted=accepted,
            total_rejected=rejected,
        )

    # ── 4. Bidirectional Streaming ────────────────────────────────

    async def LiveChat(
        self,
        request_iterator: AsyncIterator[pb2.ChatMessage],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[pb2.ChatMessage]:
        """Bidirectional streaming: real-time chat.

        Client sends messages, server broadcasts to all participants
        in the same session. Each participant has a queue for
        incoming messages.
        """
        my_queue: asyncio.Queue[pb2.ChatMessage] = asyncio.Queue(maxsize=100)
        session_id: str | None = None

        async def read_from_client() -> None:
            nonlocal session_id
            try:
                async for msg in request_iterator:
                    if session_id is None:
                        session_id = msg.session_id
                        self._chat_rooms[session_id].append(my_queue)

                    # Broadcast to all participants in the session
                    for queue in self._chat_rooms.get(msg.session_id, []):
                        if queue is not my_queue:
                            try:
                                queue.put_nowait(msg)
                            except asyncio.QueueFull:
                                pass  # drop message if consumer is too slow
            except Exception:
                pass

        # Start reading client messages in the background
        reader_task = asyncio.create_task(read_from_client())

        try:
            while not context.cancelled():
                try:
                    msg = await asyncio.wait_for(my_queue.get(), timeout=30.0)
                    yield msg
                except asyncio.TimeoutError:
                    # Send keepalive
                    ts = timestamp_pb2.Timestamp()
                    ts.FromDatetime(datetime.now(timezone.utc))
                    yield pb2.ChatMessage(
                        session_id=session_id or "",
                        sender="system",
                        content="keepalive",
                        sent_at=ts,
                    )
        finally:
            reader_task.cancel()
            if session_id and my_queue in self._chat_rooms.get(session_id, []):
                self._chat_rooms[session_id].remove(my_queue)


# ── Client usage examples ─────────────────────────────────────────

async def client_examples() -> None:
    channel = grpc.aio.insecure_channel("localhost:50051")
    stub = pb2_grpc.AnalyticsServiceStub(channel)

    # Server streaming — consume with async for
    query = pb2.MetricQuery(metric_name="cpu_usage", interval_seconds=60)
    async for point in stub.StreamMetrics(query):
        print(f"Metric: {point.value:.2f} at {point.timestamp}")
        if point.value > 95:
            break  # client can cancel early

    # Client streaming — send batch
    async def event_generator():
        for i in range(1000):
            yield pb2.Event(
                event_id=f"evt-{i}",
                user_id="user-123",
                event_type="page_view",
            )

    result = await stub.BatchIngest(event_generator())
    print(f"Batch: {result.total_accepted}/{result.total_received} accepted")

    # Bidi streaming — chat
    async def chat_sender():
        yield pb2.ChatMessage(session_id="room-1", sender="alice", content="Hello!")
        await asyncio.sleep(1)
        yield pb2.ChatMessage(session_id="room-1", sender="alice", content="Anyone here?")

    async for reply in stub.LiveChat(chat_sender()):
        print(f"{reply.sender}: {reply.content}")

    await channel.close()
```

gRPC streaming patterns comparison:

| Pattern | Client sends | Server sends | Use case |
|---|---|---|---|
| Unary | 1 message | 1 message | CRUD, simple queries |
| Server stream | 1 message | N messages | Metrics feed, log tailing |
| Client stream | N messages | 1 message | Batch upload, file upload |
| Bidi stream | N messages | N messages | Chat, real-time sync |

Flow control best practices:
- Check `context.cancelled()` in server streams to stop early
- Use `asyncio.Queue(maxsize=N)` for backpressure in bidi streams
- Yield to event loop periodically in tight loops (`await asyncio.sleep(0)`)
- Set trailing metadata with stream statistics for observability
- Handle `grpc.aio.AioRpcError` for client disconnects mid-stream
'''
    ),
    (
        "grpc/interceptors-middleware",
        "Implement gRPC interceptors in Python for logging, authentication, rate limiting, and error handling that work with both unary and streaming RPCs.",
        '''gRPC interceptors for logging, auth, rate limiting, and error handling:

```python
from __future__ import annotations

import asyncio
import time
import logging
from collections import defaultdict
from typing import Any, Callable

import grpc
from grpc import aio as grpc_aio

logger = logging.getLogger("grpc.interceptors")


# ── Logging interceptor ──────────────────────────────────────────

class LoggingInterceptor(grpc_aio.ServerInterceptor):
    """Logs all RPC calls with timing, status, and metadata."""

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        method = handler_call_details.method
        start = time.monotonic()

        logger.info(
            "gRPC call started",
            extra={"method": method, "metadata": dict(handler_call_details.invocation_metadata or [])},
        )

        handler = await continuation(handler_call_details)
        if handler is None:
            return handler

        # Wrap the handler to capture response timing
        if handler.unary_unary:
            original = handler.unary_unary

            async def logged_unary(request, context):
                try:
                    response = await original(request, context)
                    elapsed = (time.monotonic() - start) * 1000
                    logger.info(
                        "gRPC call completed",
                        extra={"method": method, "elapsed_ms": f"{elapsed:.1f}", "status": "OK"},
                    )
                    return response
                except Exception as e:
                    elapsed = (time.monotonic() - start) * 1000
                    logger.error(
                        "gRPC call failed",
                        extra={"method": method, "elapsed_ms": f"{elapsed:.1f}", "error": str(e)},
                    )
                    raise

            return grpc.unary_unary_rpc_method_handler(
                logged_unary,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler


# ── Authentication interceptor ────────────────────────────────────

class AuthInterceptor(grpc_aio.ServerInterceptor):
    """JWT/API key authentication interceptor.

    Checks the 'authorization' metadata header and injects
    the authenticated user into the context.
    """

    # Methods that don\'t require authentication
    PUBLIC_METHODS = frozenset({
        "/grpc.health.v1.Health/Check",
        "/grpc.reflection.v1.ServerReflection/ServerReflectionInfo",
    })

    def __init__(self, validate_token: Callable[[str], dict | None]) -> None:
        self._validate = validate_token

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        method = handler_call_details.method

        if method in self.PUBLIC_METHODS:
            return await continuation(handler_call_details)

        # Extract token from metadata
        metadata = dict(handler_call_details.invocation_metadata or [])
        auth_header = metadata.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            # Return an error handler
            async def unauthenticated(request, context):
                await context.abort(
                    grpc.StatusCode.UNAUTHENTICATED,
                    "Missing or invalid authorization header",
                )
            handler = await continuation(handler_call_details)
            if handler and handler.unary_unary:
                return grpc.unary_unary_rpc_method_handler(
                    unauthenticated,
                    request_deserializer=handler.request_deserializer,
                    response_serializer=handler.response_serializer,
                )
            return handler

        token = auth_header[7:]
        user_info = self._validate(token)
        if user_info is None:
            async def forbidden(request, context):
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    "Invalid or expired token",
                )
            handler = await continuation(handler_call_details)
            if handler and handler.unary_unary:
                return grpc.unary_unary_rpc_method_handler(
                    forbidden,
                    request_deserializer=handler.request_deserializer,
                    response_serializer=handler.response_serializer,
                )
            return handler

        # Inject user info into context via metadata
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler

        if handler.unary_unary:
            original = handler.unary_unary

            async def authed_unary(request, context):
                context.user_info = user_info  # type: ignore[attr-defined]
                await context.send_initial_metadata([
                    ("x-user-id", user_info.get("sub", "")),
                ])
                return await original(request, context)

            return grpc.unary_unary_rpc_method_handler(
                authed_unary,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler


# ── Rate limiting interceptor ─────────────────────────────────────

class TokenBucketRateLimiter:
    """Thread-safe token bucket for rate limiting."""

    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate          # tokens per second
        self.burst = burst        # max tokens
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_refill = now

            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False


class RateLimitInterceptor(grpc_aio.ServerInterceptor):
    """Per-client rate limiting using token bucket."""

    def __init__(self, rate: float = 100, burst: int = 200) -> None:
        self._limiters: dict[str, TokenBucketRateLimiter] = defaultdict(
            lambda: TokenBucketRateLimiter(rate, burst)
        )

    def _get_client_key(self, metadata: dict[str, str]) -> str:
        return metadata.get("x-client-id", metadata.get("x-forwarded-for", "unknown"))

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        metadata = dict(handler_call_details.invocation_metadata or [])
        client_key = self._get_client_key(metadata)
        limiter = self._limiters[client_key]

        if not await limiter.acquire():
            async def rate_limited(request, context):
                await context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    f"Rate limit exceeded for client '{client_key}'",
                )
            handler = await continuation(handler_call_details)
            if handler and handler.unary_unary:
                return grpc.unary_unary_rpc_method_handler(
                    rate_limited,
                    request_deserializer=handler.request_deserializer,
                    response_serializer=handler.response_serializer,
                )
            return handler

        return await continuation(handler_call_details)


# ── Error handling interceptor ────────────────────────────────────

class ErrorHandlingInterceptor(grpc_aio.ServerInterceptor):
    """Catches unhandled exceptions and maps them to gRPC status codes."""

    EXCEPTION_MAP: dict[type, grpc.StatusCode] = {
        ValueError: grpc.StatusCode.INVALID_ARGUMENT,
        KeyError: grpc.StatusCode.NOT_FOUND,
        PermissionError: grpc.StatusCode.PERMISSION_DENIED,
        NotImplementedError: grpc.StatusCode.UNIMPLEMENTED,
        TimeoutError: grpc.StatusCode.DEADLINE_EXCEEDED,
    }

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler

        if handler.unary_unary:
            original = handler.unary_unary

            async def safe_unary(request, context):
                try:
                    return await original(request, context)
                except grpc_aio.AioRpcError:
                    raise  # already a gRPC error
                except Exception as e:
                    status = self.EXCEPTION_MAP.get(
                        type(e), grpc.StatusCode.INTERNAL
                    )
                    logger.exception(f"Unhandled error in {handler_call_details.method}")
                    await context.abort(status, str(e))

            return grpc.unary_unary_rpc_method_handler(
                safe_unary,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler


# ── Server setup with interceptor chain ───────────────────────────

async def serve() -> None:
    def validate_jwt(token: str) -> dict | None:
        # Replace with real JWT validation
        if token == "test-token":
            return {"sub": "user-123", "role": "admin"}
        return None

    server = grpc_aio.server(
        interceptors=[
            ErrorHandlingInterceptor(),
            LoggingInterceptor(),
            AuthInterceptor(validate_jwt),
            RateLimitInterceptor(rate=100, burst=200),
        ],
    )
    # Add your service implementations here
    # pb2_grpc.add_OrderServiceServicer_to_server(OrderServiceImpl(), server)

    server.add_insecure_port("[::]:50051")
    await server.start()
    await server.wait_for_termination()
```

Interceptor execution order and responsibilities:

| Interceptor | Layer | Purpose |
|---|---|---|
| ErrorHandling | Outermost | Catch unhandled exceptions, map to gRPC status |
| Logging | Second | Record timing, method, status for observability |
| Auth | Third | Validate tokens, inject user context |
| RateLimit | Innermost | Protect resources from abuse |

Key patterns:
- Interceptors form a chain; outermost wraps innermost
- Use `continuation()` to pass to the next interceptor
- Map Python exceptions to gRPC status codes at the boundary
- Public methods (health checks, reflection) should bypass auth
- Rate limiters should key on client identity, not just IP
'''
    ),
    (
        "grpc/health-checks",
        "Implement gRPC health checking with the standard health service protocol, including dependency checks, graceful shutdown, and Kubernetes integration.",
        '''gRPC health checking with dependency monitoring and graceful shutdown:

```python
from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Coroutine

import grpc
from grpc import aio as grpc_aio
from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_health.v1.health import HealthServicer

logger = logging.getLogger("grpc.health")


class DependencyStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class DependencyCheck:
    name: str
    check_fn: Callable[[], Coroutine[Any, Any, DependencyStatus]]
    critical: bool = True     # if critical, unhealthy = NOT_SERVING
    timeout: float = 5.0      # seconds
    last_status: DependencyStatus = DependencyStatus.HEALTHY
    consecutive_failures: int = 0
    max_failures: int = 3     # failures before marking unhealthy


@dataclass
class HealthState:
    overall: health_pb2.HealthCheckResponse.ServingStatus = (
        health_pb2.HealthCheckResponse.SERVING
    )
    dependencies: dict[str, DependencyStatus] = field(default_factory=dict)


class EnhancedHealthServicer(health_pb2_grpc.HealthServicer):
    """Enhanced gRPC health service with dependency monitoring.

    Implements the standard grpc.health.v1.Health protocol plus
    background dependency checking and graceful shutdown support.
    """

    def __init__(
        self,
        check_interval: float = 10.0,
        shutdown_grace_period: float = 15.0,
    ) -> None:
        self._check_interval = check_interval
        self._shutdown_grace = shutdown_grace_period
        self._dependencies: list[DependencyCheck] = []
        self._service_statuses: dict[str, health_pb2.HealthCheckResponse.ServingStatus] = {}
        self._watchers: dict[str, list[asyncio.Queue]] = {}
        self._state = HealthState()
        self._running = False
        self._shutting_down = False

    # ── Dependency registration ───────────────────────────────────

    def add_dependency(
        self,
        name: str,
        check_fn: Callable[[], Coroutine[Any, Any, DependencyStatus]],
        critical: bool = True,
        timeout: float = 5.0,
    ) -> None:
        self._dependencies.append(DependencyCheck(
            name=name,
            check_fn=check_fn,
            critical=critical,
            timeout=timeout,
        ))

    # ── Standard health check RPCs ────────────────────────────────

    async def Check(
        self,
        request: health_pb2.HealthCheckRequest,
        context: grpc_aio.ServicerContext,
    ) -> health_pb2.HealthCheckResponse:
        service = request.service

        if service == "":
            # Overall health
            return health_pb2.HealthCheckResponse(status=self._state.overall)

        status = self._service_statuses.get(service)
        if status is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Unknown service: {service}",
            )

        return health_pb2.HealthCheckResponse(status=status)

    async def Watch(
        self,
        request: health_pb2.HealthCheckRequest,
        context: grpc_aio.ServicerContext,
    ) -> AsyncIterator[health_pb2.HealthCheckResponse]:
        """Stream health status changes for a service."""
        service = request.service
        queue: asyncio.Queue = asyncio.Queue()
        self._watchers.setdefault(service, []).append(queue)

        try:
            # Send current status immediately
            current = self._service_statuses.get(
                service,
                self._state.overall if service == "" else health_pb2.HealthCheckResponse.SERVICE_UNKNOWN,
            )
            yield health_pb2.HealthCheckResponse(status=current)

            while not context.cancelled():
                try:
                    new_status = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield health_pb2.HealthCheckResponse(status=new_status)
                except asyncio.TimeoutError:
                    continue

        finally:
            self._watchers[service].remove(queue)

    # ── Background health monitoring ──────────────────────────────

    async def start_monitoring(self) -> None:
        self._running = True
        while self._running:
            await self._check_all_dependencies()
            await asyncio.sleep(self._check_interval)

    async def _check_all_dependencies(self) -> None:
        has_critical_failure = False

        for dep in self._dependencies:
            try:
                status = await asyncio.wait_for(
                    dep.check_fn(),
                    timeout=dep.timeout,
                )
                dep.last_status = status
                if status == DependencyStatus.HEALTHY:
                    dep.consecutive_failures = 0
                else:
                    dep.consecutive_failures += 1
            except (asyncio.TimeoutError, Exception) as e:
                dep.consecutive_failures += 1
                dep.last_status = DependencyStatus.UNHEALTHY
                logger.warning(f"Health check failed for {dep.name}: {e}")

            self._state.dependencies[dep.name] = dep.last_status

            if dep.critical and dep.consecutive_failures >= dep.max_failures:
                has_critical_failure = True

        # Update overall status
        old_status = self._state.overall
        if self._shutting_down:
            new_status = health_pb2.HealthCheckResponse.NOT_SERVING
        elif has_critical_failure:
            new_status = health_pb2.HealthCheckResponse.NOT_SERVING
        else:
            new_status = health_pb2.HealthCheckResponse.SERVING

        if new_status != old_status:
            self._state.overall = new_status
            await self._notify_watchers("", new_status)
            logger.info(f"Health status changed: {old_status} -> {new_status}")

    async def _notify_watchers(self, service: str, status: int) -> None:
        for queue in self._watchers.get(service, []):
            try:
                queue.put_nowait(status)
            except asyncio.QueueFull:
                pass

    # ── Graceful shutdown ─────────────────────────────────────────

    async def graceful_shutdown(self, server: grpc_aio.Server) -> None:
        """Graceful shutdown sequence:
        1. Mark as NOT_SERVING (load balancer stops sending traffic)
        2. Wait grace period for in-flight requests
        3. Stop the server
        """
        logger.info("Starting graceful shutdown")
        self._shutting_down = True

        # Step 1: Tell load balancers we are going away
        self._state.overall = health_pb2.HealthCheckResponse.NOT_SERVING
        await self._notify_watchers(
            "", health_pb2.HealthCheckResponse.NOT_SERVING,
        )

        # Step 2: Wait for in-flight requests to drain
        logger.info(f"Draining for {self._shutdown_grace}s")
        await asyncio.sleep(self._shutdown_grace)

        # Step 3: Stop accepting new RPCs, wait for remaining
        self._running = False
        await server.stop(grace=5.0)
        logger.info("Server stopped")


# ── Server setup with health checks ──────────────────────────────

async def create_server() -> None:
    health = EnhancedHealthServicer(check_interval=10.0)

    # Register dependency checks
    async def check_database() -> DependencyStatus:
        # Replace with real DB ping
        return DependencyStatus.HEALTHY

    async def check_redis() -> DependencyStatus:
        # Replace with real Redis ping
        return DependencyStatus.HEALTHY

    async def check_external_api() -> DependencyStatus:
        # Non-critical: degraded performance but still functional
        return DependencyStatus.HEALTHY

    health.add_dependency("postgres", check_database, critical=True)
    health.add_dependency("redis", check_redis, critical=True)
    health.add_dependency("payment-api", check_external_api, critical=False)

    # Register known services
    health._service_statuses["ordering.v1.OrderService"] = (
        health_pb2.HealthCheckResponse.SERVING
    )

    server = grpc_aio.server()
    health_pb2_grpc.add_HealthServicer_to_server(health, server)
    server.add_insecure_port("[::]:50051")
    await server.start()

    # Start health monitoring in background
    monitor_task = asyncio.create_task(health.start_monitoring())

    # Handle SIGTERM for graceful shutdown
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(
        signal.SIGTERM,
        lambda: asyncio.create_task(health.graceful_shutdown(server)),
    )

    await server.wait_for_termination()
    monitor_task.cancel()
```

```yaml
# Kubernetes gRPC health check configuration
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  template:
    spec:
      containers:
      - name: order-service
        ports:
        - containerPort: 50051
        # gRPC native health check (K8s 1.24+)
        livenessProbe:
          grpc:
            port: 50051
            service: ""           # overall health
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          grpc:
            port: 50051
            service: "ordering.v1.OrderService"
          periodSeconds: 5
        startupProbe:
          grpc:
            port: 50051
          failureThreshold: 30
          periodSeconds: 2
      # For K8s < 1.24, use grpc-health-probe binary
      # livenessProbe:
      #   exec:
      #     command: ["grpc-health-probe", "-addr=:50051"]
```

Health check architecture:

| Component | Role |
|---|---|
| `Check` RPC | Synchronous point-in-time status query |
| `Watch` RPC | Stream status changes to load balancers |
| Dependency checks | Background monitoring of DB, cache, APIs |
| Graceful shutdown | NOT_SERVING -> drain -> stop sequence |
| K8s probes | Liveness (restart), readiness (traffic), startup (init) |

Shutdown sequence:
1. Receive SIGTERM from Kubernetes
2. Set status to NOT_SERVING via health service
3. Load balancer\'s Watch stream sees change, stops routing
4. Wait grace period for in-flight requests to complete
5. Call `server.stop(grace=5)` for final cleanup
'''
    ),
    (
        "grpc/load-balancing",
        "Show gRPC client-side load balancing with service discovery, round-robin, weighted routing, and connection management in Python.",
        '''gRPC client-side load balancing with service discovery and routing:

```python
from __future__ import annotations

import asyncio
import random
import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence

import grpc
from grpc import aio as grpc_aio

logger = logging.getLogger("grpc.lb")


# ── Service discovery ─────────────────────────────────────────────

@dataclass
class ServiceEndpoint:
    host: str
    port: int
    weight: int = 100
    region: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    healthy: bool = True

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class ServiceRegistry:
    """Service discovery abstraction.

    In production, back this with Consul, etcd, or DNS SRV records.
    """

    def __init__(self) -> None:
        self._services: dict[str, list[ServiceEndpoint]] = {}
        self._watchers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def register(self, service: str, endpoint: ServiceEndpoint) -> None:
        self._services.setdefault(service, []).append(endpoint)
        self._notify(service)

    def deregister(self, service: str, address: str) -> None:
        endpoints = self._services.get(service, [])
        self._services[service] = [e for e in endpoints if e.address != address]
        self._notify(service)

    def get_endpoints(self, service: str) -> list[ServiceEndpoint]:
        return [e for e in self._services.get(service, []) if e.healthy]

    async def watch(self, service: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._watchers[service].append(queue)
        return queue

    def _notify(self, service: str) -> None:
        endpoints = self.get_endpoints(service)
        for queue in self._watchers.get(service, []):
            try:
                queue.put_nowait(endpoints)
            except asyncio.QueueFull:
                pass


# ── Load balancing policies ───────────────────────────────────────

class LoadBalancer:
    """Base class for load balancing policies."""

    def pick(self, endpoints: Sequence[ServiceEndpoint]) -> ServiceEndpoint | None:
        raise NotImplementedError


class RoundRobinBalancer(LoadBalancer):
    """Simple round-robin selection."""

    def __init__(self) -> None:
        self._index = 0

    def pick(self, endpoints: Sequence[ServiceEndpoint]) -> ServiceEndpoint | None:
        if not endpoints:
            return None
        endpoint = endpoints[self._index % len(endpoints)]
        self._index += 1
        return endpoint


class WeightedRoundRobinBalancer(LoadBalancer):
    """Weighted round-robin using smooth weighted selection (Nginx-style)."""

    def __init__(self) -> None:
        self._current_weights: dict[str, int] = {}

    def pick(self, endpoints: Sequence[ServiceEndpoint]) -> ServiceEndpoint | None:
        if not endpoints:
            return None

        total_weight = sum(e.weight for e in endpoints)

        # Initialize or adjust current weights
        for e in endpoints:
            if e.address not in self._current_weights:
                self._current_weights[e.address] = 0
            self._current_weights[e.address] += e.weight

        # Pick the one with the highest current weight
        best: ServiceEndpoint | None = None
        best_weight = -1
        for e in endpoints:
            if self._current_weights[e.address] > best_weight:
                best = e
                best_weight = self._current_weights[e.address]

        if best:
            self._current_weights[best.address] -= total_weight

        return best


class LatencyAwareBalancer(LoadBalancer):
    """Pick the endpoint with the lowest observed P50 latency.

    Uses exponential moving average to track latency.
    """

    EMA_ALPHA = 0.3

    def __init__(self) -> None:
        self._latencies: dict[str, float] = {}

    def record_latency(self, address: str, latency_ms: float) -> None:
        if address not in self._latencies:
            self._latencies[address] = latency_ms
        else:
            self._latencies[address] = (
                self.EMA_ALPHA * latency_ms
                + (1 - self.EMA_ALPHA) * self._latencies[address]
            )

    def pick(self, endpoints: Sequence[ServiceEndpoint]) -> ServiceEndpoint | None:
        if not endpoints:
            return None

        # For new endpoints without latency data, give them a chance
        unknown = [e for e in endpoints if e.address not in self._latencies]
        if unknown:
            return random.choice(unknown)

        return min(endpoints, key=lambda e: self._latencies.get(e.address, float("inf")))


# ── Smart gRPC channel pool ──────────────────────────────────────

class GrpcChannelPool:
    """Manages a pool of gRPC channels with load balancing.

    Features:
    - Automatic channel creation per endpoint
    - Connection health monitoring
    - Graceful channel cycling
    """

    def __init__(
        self,
        registry: ServiceRegistry,
        service_name: str,
        balancer: LoadBalancer | None = None,
        channel_options: list[tuple[str, Any]] | None = None,
        use_tls: bool = False,
    ) -> None:
        self._registry = registry
        self._service_name = service_name
        self._balancer = balancer or RoundRobinBalancer()
        self._channels: dict[str, grpc_aio.Channel] = {}
        self._channel_options = channel_options or [
            ("grpc.keepalive_time_ms", 30_000),
            ("grpc.keepalive_timeout_ms", 10_000),
            ("grpc.keepalive_permit_without_calls", 1),
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.max_connection_idle_ms", 300_000),
        ]
        self._use_tls = use_tls

    def _get_or_create_channel(self, endpoint: ServiceEndpoint) -> grpc_aio.Channel:
        addr = endpoint.address
        if addr not in self._channels:
            if self._use_tls:
                credentials = grpc.ssl_channel_credentials()
                channel = grpc_aio.secure_channel(
                    addr, credentials, options=self._channel_options,
                )
            else:
                channel = grpc_aio.insecure_channel(
                    addr, options=self._channel_options,
                )
            self._channels[addr] = channel
        return self._channels[addr]

    def get_channel(self) -> grpc_aio.Channel:
        """Get a channel to a healthy endpoint using the configured balancer."""
        endpoints = self._registry.get_endpoints(self._service_name)
        if not endpoints:
            raise RuntimeError(f"No healthy endpoints for {self._service_name}")

        endpoint = self._balancer.pick(endpoints)
        if not endpoint:
            raise RuntimeError("Load balancer returned no endpoint")

        return self._get_or_create_channel(endpoint)

    async def close_all(self) -> None:
        for channel in self._channels.values():
            await channel.close()
        self._channels.clear()

    async def remove_endpoint(self, address: str) -> None:
        channel = self._channels.pop(address, None)
        if channel:
            await channel.close()


# ── Usage: resilient gRPC client ──────────────────────────────────

async def resilient_call_example() -> None:
    registry = ServiceRegistry()
    registry.register("order-service", ServiceEndpoint("10.0.1.1", 50051, weight=100))
    registry.register("order-service", ServiceEndpoint("10.0.1.2", 50051, weight=100))
    registry.register("order-service", ServiceEndpoint("10.0.1.3", 50051, weight=50))

    balancer = WeightedRoundRobinBalancer()
    pool = GrpcChannelPool(registry, "order-service", balancer)

    max_retries = 3
    for attempt in range(max_retries):
        channel = pool.get_channel()
        try:
            # stub = pb2_grpc.OrderServiceStub(channel)
            # response = await stub.GetOrder(request, timeout=5.0)
            break
        except grpc_aio.AioRpcError as e:
            if e.code() in (
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
            ):
                logger.warning(f"Attempt {attempt + 1} failed: {e.code()}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(0.1 * (2 ** attempt))
            else:
                raise  # non-retriable error

    await pool.close_all()
```

Load balancing strategies comparison:

| Strategy | Best for | Weakness |
|---|---|---|
| Round-robin | Uniform workloads | Ignores endpoint capacity differences |
| Weighted round-robin | Heterogeneous capacity | Requires manual weight tuning |
| Least connections | Variable request durations | Needs connection tracking |
| Latency-aware | Latency-sensitive apps | Cold start bias, feedback loops |
| Random | Simplicity, large clusters | Uneven distribution at small scale |

gRPC channel best practices:
- Reuse channels across stubs (channels multiplex over HTTP/2)
- Configure keepalive to detect dead connections behind NAT/LB
- Use `max_connection_idle_ms` to close stale channels
- Implement retry with exponential backoff for UNAVAILABLE errors
- Monitor `grpc_client_handled_total` for per-endpoint error rates
'''
    ),
]
