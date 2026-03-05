"""gRPC advanced patterns — bidirectional streaming, interceptors, gRPC-web gateway, load balancing and service discovery."""

PAIRS = [
    (
        "distributed/grpc-bidirectional-streaming",
        "Show gRPC bidirectional streaming in Python: real-time chat, progress reporting, and flow control with proper error handling.",
        '''gRPC bidirectional streaming patterns:

```protobuf
// chat.proto — bidirectional streaming service definition

syntax = "proto3";

package chat;

service ChatService {
    // Unary
    rpc GetRoom (GetRoomRequest) returns (Room);

    // Server streaming: subscribe to messages
    rpc Subscribe (SubscribeRequest) returns (stream ChatMessage);

    // Client streaming: upload file in chunks
    rpc UploadFile (stream FileChunk) returns (UploadResponse);

    // Bidirectional streaming: real-time chat
    rpc Chat (stream ChatMessage) returns (stream ChatMessage);

    // Bidirectional: progress tracking
    rpc ProcessBatch (stream BatchItem) returns (stream ProgressUpdate);
}

message ChatMessage {
    string room_id = 1;
    string user_id = 2;
    string content = 3;
    int64 timestamp = 4;
    MessageType type = 5;

    enum MessageType {
        TEXT = 0;
        JOIN = 1;
        LEAVE = 2;
        TYPING = 3;
    }
}

message SubscribeRequest {
    string room_id = 1;
    string user_id = 2;
}

message GetRoomRequest {
    string room_id = 1;
}

message Room {
    string room_id = 1;
    string name = 2;
    repeated string members = 3;
}

message FileChunk {
    string filename = 1;
    bytes data = 2;
    int32 chunk_index = 3;
    int32 total_chunks = 4;
}

message UploadResponse {
    string file_id = 1;
    int64 total_bytes = 2;
    bool success = 3;
}

message BatchItem {
    string item_id = 1;
    bytes payload = 2;
}

message ProgressUpdate {
    string item_id = 1;
    float progress = 2;   // 0.0 - 1.0
    string status = 3;
    string error = 4;
}
```

```python
# ── Server implementation ─────────────────────────────────────────

from __future__ import annotations

import asyncio
import time
import logging
from collections import defaultdict
from typing import AsyncIterator

import grpc

# Generated from proto:
# python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat.proto
from chat_pb2 import (
    ChatMessage, Room, GetRoomRequest,
    SubscribeRequest, UploadResponse, FileChunk,
    BatchItem, ProgressUpdate,
)
from chat_pb2_grpc import ChatServiceServicer, add_ChatServiceServicer_to_server

logger = logging.getLogger(__name__)


class ChatRoom:
    """In-memory chat room with subscriber management."""

    def __init__(self, room_id: str, name: str) -> None:
        self.room_id = room_id
        self.name = name
        self.members: set[str] = set()
        self._subscribers: dict[str, asyncio.Queue[ChatMessage]] = {}

    async def subscribe(self, user_id: str) -> asyncio.Queue[ChatMessage]:
        queue: asyncio.Queue[ChatMessage] = asyncio.Queue(maxsize=100)
        self._subscribers[user_id] = queue
        self.members.add(user_id)
        return queue

    def unsubscribe(self, user_id: str) -> None:
        self._subscribers.pop(user_id, None)
        self.members.discard(user_id)

    async def broadcast(self, message: ChatMessage) -> None:
        for uid, queue in self._subscribers.items():
            if uid != message.user_id:
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    logger.warning(f"Queue full for {uid}, dropping message")


class ChatServiceImpl(ChatServiceServicer):
    def __init__(self) -> None:
        self._rooms: dict[str, ChatRoom] = {}

    def _get_or_create_room(self, room_id: str) -> ChatRoom:
        if room_id not in self._rooms:
            self._rooms[room_id] = ChatRoom(room_id, f"Room {room_id}")
        return self._rooms[room_id]

    async def GetRoom(
        self,
        request: GetRoomRequest,
        context: grpc.aio.ServicerContext,
    ) -> Room:
        room = self._get_or_create_room(request.room_id)
        return Room(
            room_id=room.room_id,
            name=room.name,
            members=list(room.members),
        )

    async def Subscribe(
        self,
        request: SubscribeRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[ChatMessage]:
        """Server streaming: push messages to subscriber."""
        room = self._get_or_create_room(request.room_id)
        queue = await room.subscribe(request.user_id)

        try:
            while not context.cancelled():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield msg
                except asyncio.TimeoutError:
                    # Send keepalive / heartbeat
                    continue
        finally:
            room.unsubscribe(request.user_id)

    async def Chat(
        self,
        request_iterator: AsyncIterator[ChatMessage],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[ChatMessage]:
        """Bidirectional streaming: real-time chat."""
        room: ChatRoom | None = None
        queue: asyncio.Queue[ChatMessage] | None = None
        user_id: str = ""

        async def read_messages() -> None:
            nonlocal room, queue, user_id
            async for msg in request_iterator:
                if room is None:
                    room = self._get_or_create_room(msg.room_id)
                    user_id = msg.user_id
                    queue = await room.subscribe(user_id)

                await room.broadcast(msg)

        # Start reading in background
        read_task = asyncio.create_task(read_messages())

        try:
            # Wait for first message to set up room
            while queue is None and not context.cancelled():
                await asyncio.sleep(0.01)

            if queue is None:
                return

            # Yield messages from the room
            while not context.cancelled():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield msg
                except asyncio.TimeoutError:
                    if read_task.done():
                        break
        finally:
            read_task.cancel()
            if room and user_id:
                room.unsubscribe(user_id)

    async def ProcessBatch(
        self,
        request_iterator: AsyncIterator[BatchItem],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[ProgressUpdate]:
        """Bidirectional: process items and stream progress."""
        async for item in request_iterator:
            # Simulate processing with progress updates
            for step in range(5):
                await asyncio.sleep(0.1)
                yield ProgressUpdate(
                    item_id=item.item_id,
                    progress=(step + 1) / 5.0,
                    status="processing" if step < 4 else "completed",
                )
```

```python
# ── Client implementation ─────────────────────────────────────────

import grpc
from chat_pb2 import ChatMessage, SubscribeRequest, BatchItem
from chat_pb2_grpc import ChatServiceStub


async def chat_client_example() -> None:
    """Bidirectional streaming client."""
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = ChatServiceStub(channel)

        # ── Bidirectional chat ────────────────────────────────

        async def message_generator() -> AsyncIterator[ChatMessage]:
            """Generate outgoing messages."""
            messages = [
                ChatMessage(
                    room_id="room-1",
                    user_id="alice",
                    content="Hello everyone!",
                    timestamp=int(time.time()),
                    type=ChatMessage.TEXT,
                ),
                ChatMessage(
                    room_id="room-1",
                    user_id="alice",
                    content="How's it going?",
                    timestamp=int(time.time()),
                    type=ChatMessage.TEXT,
                ),
            ]
            for msg in messages:
                yield msg
                await asyncio.sleep(1)

        # Start bidirectional stream
        stream = stub.Chat(message_generator())

        # Read incoming messages
        async for response in stream:
            print(
                f"[{response.user_id}]: {response.content}"
            )

        # ── Batch processing with progress ────────────────────

        async def batch_generator() -> AsyncIterator[BatchItem]:
            for i in range(10):
                yield BatchItem(
                    item_id=f"item-{i}",
                    payload=f"data-{i}".encode(),
                )
                await asyncio.sleep(0.05)

        progress_stream = stub.ProcessBatch(batch_generator())
        async for update in progress_stream:
            print(
                f"  {update.item_id}: "
                f"{update.progress:.0%} - {update.status}"
            )


# ── Server startup ───────────────────────────────────────────────

async def serve() -> None:
    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", True),
            ("grpc.max_connection_idle_ms", 300000),
        ],
    )
    add_ChatServiceServicer_to_server(ChatServiceImpl(), server)
    server.add_insecure_port("[::]:50051")

    await server.start()
    logger.info("gRPC server started on :50051")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
```

| Streaming Type | Client | Server | Use Case |
|---|---|---|---|
| Unary | 1 request | 1 response | Simple RPC calls |
| Server streaming | 1 request | N responses | Subscriptions, feeds |
| Client streaming | N requests | 1 response | File upload, batching |
| Bidirectional | N requests | N responses | Chat, progress, sync |

Key patterns:
1. Use `asyncio.Queue` for fan-out to multiple subscribers on server side.
2. Client streaming uses `async def generator()` yielding request messages.
3. Bidirectional streams need a background task to read while writing.
4. Always check `context.cancelled()` in server loops for clean shutdown.
5. Set `keepalive_time_ms` to detect dead connections through proxies/LBs.
6. Use `maxsize` on queues to apply backpressure and prevent OOM.'''
    ),
    (
        "distributed/grpc-interceptors-middleware",
        "Show gRPC interceptors and middleware in Python: authentication, logging, metrics, error handling, and retry interceptors.",
        '''gRPC interceptors and middleware:

```python
from __future__ import annotations

import asyncio
import logging
import time
import traceback
from typing import Any, Callable

import grpc
from grpc import aio as grpc_aio

logger = logging.getLogger(__name__)


# ── Server interceptors ──────────────────────────────────────────

class AuthInterceptor(grpc_aio.ServerInterceptor):
    """JWT authentication interceptor."""

    def __init__(self, jwt_secret: str, exclude_methods: set[str] | None = None) -> None:
        self._jwt_secret = jwt_secret
        self._exclude = exclude_methods or set()

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        method = handler_call_details.method
        handler = await continuation(handler_call_details)

        # Skip auth for excluded methods (e.g., health check)
        if method in self._exclude:
            return handler

        # Extract token from metadata
        metadata = dict(handler_call_details.invocation_metadata or [])
        token = metadata.get("authorization", "")

        if not token.startswith("Bearer "):
            # Return error handler
            return self._unauthenticated_handler(handler)

        try:
            import jwt
            payload = jwt.decode(
                token[7:], self._jwt_secret, algorithms=["HS256"]
            )
            # Store user info in context (via metadata)
            # Actual implementation would use context locals
        except Exception:
            return self._unauthenticated_handler(handler)

        return handler

    def _unauthenticated_handler(
        self, original_handler: grpc.RpcMethodHandler
    ) -> grpc.RpcMethodHandler:
        async def abort_unary(request, context):
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Invalid or missing authentication token",
            )

        async def abort_stream(request_iterator, context):
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Invalid or missing authentication token",
            )

        if original_handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(abort_unary)
        elif original_handler.unary_stream:
            return grpc.unary_stream_rpc_method_handler(abort_unary)
        elif original_handler.stream_unary:
            return grpc.stream_unary_rpc_method_handler(abort_stream)
        else:
            return grpc.stream_stream_rpc_method_handler(abort_stream)


class LoggingInterceptor(grpc_aio.ServerInterceptor):
    """Request/response logging with timing."""

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        method = handler_call_details.method
        start = time.monotonic()

        logger.info(f"gRPC request: {method}")

        try:
            handler = await continuation(handler_call_details)
            elapsed = (time.monotonic() - start) * 1000
            logger.info(f"gRPC response: {method} ({elapsed:.1f}ms)")
            return handler
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                f"gRPC error: {method} ({elapsed:.1f}ms) - {e}"
            )
            raise


class ErrorHandlingInterceptor(grpc_aio.ServerInterceptor):
    """Catch unhandled exceptions and return proper gRPC status."""

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler

        # Wrap the actual handler
        if handler.unary_unary:
            original = handler.unary_unary

            async def safe_unary(request, context):
                try:
                    return await original(request, context)
                except grpc_aio.AbortError:
                    raise  # don't catch intentional aborts
                except ValueError as e:
                    await context.abort(
                        grpc.StatusCode.INVALID_ARGUMENT, str(e)
                    )
                except PermissionError as e:
                    await context.abort(
                        grpc.StatusCode.PERMISSION_DENIED, str(e)
                    )
                except KeyError as e:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND, f"Not found: {e}"
                    )
                except Exception as e:
                    logger.error(f"Unhandled error: {traceback.format_exc()}")
                    await context.abort(
                        grpc.StatusCode.INTERNAL,
                        "Internal server error",
                    )

            return grpc.unary_unary_rpc_method_handler(
                safe_unary,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler
```

```python
# ── Client interceptors ──────────────────────────────────────────

class AuthClientInterceptor(
    grpc_aio.UnaryUnaryClientInterceptor,
    grpc_aio.UnaryStreamClientInterceptor,
    grpc_aio.StreamUnaryClientInterceptor,
    grpc_aio.StreamStreamClientInterceptor,
):
    """Add auth token to all outgoing requests."""

    def __init__(self, token_provider: Callable[[], str]) -> None:
        self._token_provider = token_provider

    def _add_auth_metadata(
        self, client_call_details: grpc.aio.ClientCallDetails
    ) -> grpc.aio.ClientCallDetails:
        metadata = list(client_call_details.metadata or [])
        metadata.append(
            ("authorization", f"Bearer {self._token_provider()}")
        )
        return grpc.aio.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        new_details = self._add_auth_metadata(client_call_details)
        return await continuation(new_details, request)

    async def intercept_unary_stream(self, continuation, client_call_details, request):
        new_details = self._add_auth_metadata(client_call_details)
        return await continuation(new_details, request)

    async def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        new_details = self._add_auth_metadata(client_call_details)
        return await continuation(new_details, request_iterator)

    async def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
        new_details = self._add_auth_metadata(client_call_details)
        return await continuation(new_details, request_iterator)


class RetryInterceptor(grpc_aio.UnaryUnaryClientInterceptor):
    """Automatic retry for idempotent RPCs with exponential backoff."""

    RETRYABLE_CODES = {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
    }

    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff: float = 0.1,
        max_backoff: float = 5.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._multiplier = backoff_multiplier

    async def intercept_unary_unary(
        self, continuation, client_call_details, request
    ):
        backoff = self._initial_backoff

        for attempt in range(self._max_retries + 1):
            try:
                response = await continuation(client_call_details, request)
                return response
            except grpc_aio.AioRpcError as e:
                if (
                    e.code() not in self.RETRYABLE_CODES
                    or attempt == self._max_retries
                ):
                    raise
                logger.warning(
                    f"Retry {attempt + 1}/{self._max_retries}: "
                    f"{e.code().name}"
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * self._multiplier, self._max_backoff)

        raise RuntimeError("Should not reach here")
```

```python
# ── Metrics interceptor (Prometheus) ──────────────────────────────

from prometheus_client import Counter, Histogram, Gauge

grpc_requests_total = Counter(
    "grpc_server_requests_total",
    "Total gRPC requests",
    ["method", "status"],
)
grpc_request_duration = Histogram(
    "grpc_server_request_duration_seconds",
    "gRPC request duration",
    ["method"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0],
)
grpc_active_requests = Gauge(
    "grpc_server_active_requests",
    "Currently active gRPC requests",
    ["method"],
)


class MetricsInterceptor(grpc_aio.ServerInterceptor):
    """Prometheus metrics for gRPC server."""

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        method = handler_call_details.method
        handler = await continuation(handler_call_details)

        if handler is None or not handler.unary_unary:
            return handler

        original = handler.unary_unary

        async def instrumented(request, context):
            grpc_active_requests.labels(method=method).inc()
            start = time.monotonic()
            status = "OK"
            try:
                result = await original(request, context)
                return result
            except grpc_aio.AbortError as e:
                status = context.code().name if context.code() else "UNKNOWN"
                raise
            except Exception:
                status = "INTERNAL"
                raise
            finally:
                elapsed = time.monotonic() - start
                grpc_requests_total.labels(method=method, status=status).inc()
                grpc_request_duration.labels(method=method).observe(elapsed)
                grpc_active_requests.labels(method=method).dec()

        return grpc.unary_unary_rpc_method_handler(
            instrumented,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )


# ── Assembling server with interceptors ───────────────────────────

async def create_server() -> grpc_aio.Server:
    server = grpc_aio.server(
        interceptors=[
            MetricsInterceptor(),
            LoggingInterceptor(),
            AuthInterceptor(
                jwt_secret="my-secret",
                exclude_methods={"/grpc.health.v1.Health/Check"},
            ),
            ErrorHandlingInterceptor(),
        ],
    )
    return server


# ── Assembling client with interceptors ───────────────────────────

def create_channel(target: str, token: str) -> grpc_aio.Channel:
    return grpc_aio.insecure_channel(
        target,
        interceptors=[
            AuthClientInterceptor(lambda: token),
            RetryInterceptor(max_retries=3),
        ],
    )
```

| Interceptor | Side | Purpose | Order |
|---|---|---|---|
| `MetricsInterceptor` | Server | Prometheus metrics | First (outermost) |
| `LoggingInterceptor` | Server | Request/response logging | Second |
| `AuthInterceptor` | Server | JWT validation | Third |
| `ErrorHandlingInterceptor` | Server | Exception → gRPC status | Last (innermost) |
| `AuthClientInterceptor` | Client | Add auth metadata | First |
| `RetryInterceptor` | Client | Retry with backoff | After auth |

Key patterns:
1. Server interceptors execute **outermost first** -- put metrics before auth.
2. Client interceptors run in order: auth adds token, then retry wraps the call.
3. Map Python exceptions to gRPC status codes in `ErrorHandlingInterceptor`.
4. Retry only **idempotent** operations and only **retryable** status codes.
5. Use `continuation` pattern to chain interceptors (like middleware).
6. Always re-raise `AbortError` -- it means intentional abort, not an exception.'''
    ),
    (
        "distributed/grpc-web-gateway",
        "Show gRPC-web and gateway patterns: Envoy proxy configuration, grpc-gateway for REST translation, and browser client integration.",
        '''gRPC-web and gateway patterns:

```python
# ── grpc-gateway: REST to gRPC translation ───────────────────────
# This uses google.api.http annotations in proto files

# service.proto with REST annotations:
PROTO_WITH_HTTP = """
syntax = "proto3";

package api.v1;

import "google/api/annotations.proto";
import "google/protobuf/empty.proto";
import "google/protobuf/field_mask.proto";

service UserService {
    // Maps to: GET /v1/users/{user_id}
    rpc GetUser (GetUserRequest) returns (User) {
        option (google.api.http) = {
            get: "/v1/users/{user_id}"
        };
    }

    // Maps to: GET /v1/users
    rpc ListUsers (ListUsersRequest) returns (ListUsersResponse) {
        option (google.api.http) = {
            get: "/v1/users"
        };
    }

    // Maps to: POST /v1/users (body is the User message)
    rpc CreateUser (CreateUserRequest) returns (User) {
        option (google.api.http) = {
            post: "/v1/users"
            body: "user"
        };
    }

    // Maps to: PATCH /v1/users/{user.user_id}
    rpc UpdateUser (UpdateUserRequest) returns (User) {
        option (google.api.http) = {
            patch: "/v1/users/{user.user_id}"
            body: "user"
        };
    }

    // Maps to: DELETE /v1/users/{user_id}
    rpc DeleteUser (DeleteUserRequest) returns (google.protobuf.Empty) {
        option (google.api.http) = {
            delete: "/v1/users/{user_id}"
        };
    }
}

message User {
    string user_id = 1;
    string name = 2;
    string email = 3;
    string role = 4;
}

message GetUserRequest {
    string user_id = 1;
}

message ListUsersRequest {
    int32 page_size = 1;
    string page_token = 2;
    string filter = 3;
}

message ListUsersResponse {
    repeated User users = 1;
    string next_page_token = 2;
    int32 total_count = 3;
}

message CreateUserRequest {
    User user = 1;
}

message UpdateUserRequest {
    User user = 1;
    google.protobuf.FieldMask update_mask = 2;
}

message DeleteUserRequest {
    string user_id = 1;
}
"""
```

```yaml
# ── Envoy proxy configuration for gRPC-web ───────────────────────
# envoy.yaml

static_resources:
  listeners:
    - name: listener_0
      address:
        socket_address:
          address: 0.0.0.0
          port_value: 8080
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: ingress_http
                codec_type: AUTO

                route_config:
                  name: local_route
                  virtual_hosts:
                    - name: backend
                      domains: ["*"]
                      routes:
                        # gRPC-web routes
                        - match:
                            prefix: "/api.v1."
                          route:
                            cluster: grpc_backend
                            timeout: 30s
                            max_stream_duration:
                              grpc_timeout_header_max: 30s

                        # REST gateway routes
                        - match:
                            prefix: "/v1/"
                          route:
                            cluster: grpc_gateway
                            timeout: 30s

                      cors:
                        allow_origin_string_match:
                          - prefix: "http://localhost"
                          - exact: "https://myapp.com"
                        allow_methods: "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                        allow_headers: "content-type, x-grpc-web, authorization, x-user-agent"
                        expose_headers: "grpc-status, grpc-message"
                        max_age: "86400"

                http_filters:
                  # gRPC-web filter: translates gRPC-web to gRPC
                  - name: envoy.filters.http.grpc_web
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.grpc_web.v3.GrpcWeb

                  # CORS filter
                  - name: envoy.filters.http.cors
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors

                  # Router
                  - name: envoy.filters.http.router
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

  clusters:
    - name: grpc_backend
      type: STRICT_DNS
      lb_policy: ROUND_ROBIN
      typed_extension_protocol_options:
        envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
          "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
          explicit_http_config:
            http2_protocol_options: {}
      load_assignment:
        cluster_name: grpc_backend
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: grpc-server
                      port_value: 50051

    - name: grpc_gateway
      type: STRICT_DNS
      lb_policy: ROUND_ROBIN
      load_assignment:
        cluster_name: grpc_gateway
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: grpc-gateway
                      port_value: 8081
```

```python
# ── Python gRPC-web compatible server with connect-python ─────────
# Alternative: use grpclib which supports grpc-web natively

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="gRPC Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://myapp.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST-to-gRPC translation layer ───────────────────────────────

import grpc
from user_pb2 import (
    User, GetUserRequest, ListUsersRequest,
    CreateUserRequest, UpdateUserRequest, DeleteUserRequest,
)
from user_pb2_grpc import UserServiceStub


def get_grpc_channel() -> grpc.aio.Channel:
    return grpc.aio.insecure_channel("localhost:50051")


@app.get("/v1/users/{user_id}")
async def get_user(user_id: str) -> dict[str, Any]:
    async with get_grpc_channel() as channel:
        stub = UserServiceStub(channel)
        try:
            user = await stub.GetUser(
                GetUserRequest(user_id=user_id)
            )
            return {
                "user_id": user.user_id,
                "name": user.name,
                "email": user.email,
                "role": user.role,
            }
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                from fastapi import HTTPException
                raise HTTPException(404, "User not found")
            raise


@app.get("/v1/users")
async def list_users(
    page_size: int = 20,
    page_token: str = "",
    filter: str = "",
) -> dict[str, Any]:
    async with get_grpc_channel() as channel:
        stub = UserServiceStub(channel)
        response = await stub.ListUsers(
            ListUsersRequest(
                page_size=page_size,
                page_token=page_token,
                filter=filter,
            )
        )
        return {
            "users": [
                {
                    "user_id": u.user_id,
                    "name": u.name,
                    "email": u.email,
                }
                for u in response.users
            ],
            "next_page_token": response.next_page_token,
            "total_count": response.total_count,
        }


@app.post("/v1/users", status_code=201)
async def create_user(request: Request) -> dict[str, Any]:
    body = await request.json()
    async with get_grpc_channel() as channel:
        stub = UserServiceStub(channel)
        user = await stub.CreateUser(
            CreateUserRequest(
                user=User(
                    name=body["name"],
                    email=body["email"],
                    role=body.get("role", "member"),
                )
            )
        )
        return {
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
        }


# ── gRPC status code to HTTP status code mapping ─────────────────

GRPC_TO_HTTP: dict[grpc.StatusCode, int] = {
    grpc.StatusCode.OK: 200,
    grpc.StatusCode.CANCELLED: 499,
    grpc.StatusCode.INVALID_ARGUMENT: 400,
    grpc.StatusCode.NOT_FOUND: 404,
    grpc.StatusCode.ALREADY_EXISTS: 409,
    grpc.StatusCode.PERMISSION_DENIED: 403,
    grpc.StatusCode.UNAUTHENTICATED: 401,
    grpc.StatusCode.RESOURCE_EXHAUSTED: 429,
    grpc.StatusCode.FAILED_PRECONDITION: 400,
    grpc.StatusCode.UNAVAILABLE: 503,
    grpc.StatusCode.DEADLINE_EXCEEDED: 504,
    grpc.StatusCode.INTERNAL: 500,
    grpc.StatusCode.UNIMPLEMENTED: 501,
}
```

| Approach | Protocol | Browser Support | Streaming | Complexity |
|---|---|---|---|---|
| gRPC-web + Envoy | HTTP/1.1 | Yes (via Envoy) | Server only | Medium |
| grpc-gateway | REST/JSON | Yes (native HTTP) | No | Medium |
| Connect protocol | HTTP/1.1 + HTTP/2 | Yes (native) | Full | Low |
| Manual REST wrapper | REST/JSON | Yes | No | High (but flexible) |
| gRPCurl (debugging) | gRPC native | CLI only | Full | None |

Key patterns:
1. **Envoy gRPC-web filter** translates HTTP/1.1 browser requests to HTTP/2 gRPC.
2. **grpc-gateway** generates REST endpoints from proto annotations (`google.api.http`).
3. Map gRPC status codes to HTTP status codes for REST consumers.
4. Always configure **CORS** in Envoy or the gateway for browser access.
5. Use the **Connect protocol** (connectrpc.com) as a modern alternative to gRPC-web.
6. Proto annotations (`get`, `post`, `body`) define the REST API shape declaratively.'''
    ),
    (
        "distributed/grpc-load-balancing-discovery",
        "Show gRPC load balancing and service discovery: client-side balancing, xDS protocol, health checking, and integration with Consul/Kubernetes.",
        '''gRPC load balancing and service discovery:

```python
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Sequence

import grpc
from grpc import aio as grpc_aio

logger = logging.getLogger(__name__)


# ── Service registry abstraction ──────────────────────────────────

@dataclass
class ServiceInstance:
    host: str
    port: int
    service_name: str
    metadata: dict[str, str] = field(default_factory=dict)
    healthy: bool = True
    weight: int = 100

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class ServiceRegistry:
    """Abstract service registry interface."""

    async def register(self, instance: ServiceInstance) -> None:
        raise NotImplementedError

    async def deregister(self, instance: ServiceInstance) -> None:
        raise NotImplementedError

    async def discover(self, service_name: str) -> list[ServiceInstance]:
        raise NotImplementedError

    async def watch(
        self, service_name: str, callback: Any
    ) -> None:
        raise NotImplementedError


# ── Consul-based service discovery ────────────────────────────────

import httpx


class ConsulServiceRegistry(ServiceRegistry):
    """Service discovery using HashiCorp Consul."""

    def __init__(self, consul_url: str = "http://localhost:8500") -> None:
        self._url = consul_url
        self._client = httpx.AsyncClient(base_url=consul_url)

    async def register(self, instance: ServiceInstance) -> None:
        await self._client.put(
            "/v1/agent/service/register",
            json={
                "ID": f"{instance.service_name}-{instance.host}-{instance.port}",
                "Name": instance.service_name,
                "Address": instance.host,
                "Port": instance.port,
                "Meta": instance.metadata,
                "Check": {
                    "GRPC": instance.address,
                    "Interval": "10s",
                    "Timeout": "5s",
                    "DeregisterCriticalServiceAfter": "60s",
                },
                "Weights": {"Passing": instance.weight, "Warning": 1},
            },
        )
        logger.info(f"Registered {instance.service_name} at {instance.address}")

    async def deregister(self, instance: ServiceInstance) -> None:
        service_id = f"{instance.service_name}-{instance.host}-{instance.port}"
        await self._client.put(f"/v1/agent/service/deregister/{service_id}")
        logger.info(f"Deregistered {service_id}")

    async def discover(self, service_name: str) -> list[ServiceInstance]:
        response = await self._client.get(
            f"/v1/health/service/{service_name}",
            params={"passing": "true"},
        )
        entries = response.json()
        return [
            ServiceInstance(
                host=entry["Service"]["Address"],
                port=entry["Service"]["Port"],
                service_name=service_name,
                metadata=entry["Service"].get("Meta", {}),
                healthy=True,
                weight=entry["Service"].get("Weights", {}).get("Passing", 100),
            )
            for entry in entries
        ]

    async def watch(
        self, service_name: str, callback: Any
    ) -> None:
        """Long-poll Consul for service changes."""
        index = "0"
        while True:
            try:
                response = await self._client.get(
                    f"/v1/health/service/{service_name}",
                    params={"passing": "true", "index": index, "wait": "30s"},
                    timeout=35.0,
                )
                new_index = response.headers.get("X-Consul-Index", "0")
                if new_index != index:
                    index = new_index
                    instances = await self.discover(service_name)
                    await callback(instances)
            except Exception as e:
                logger.error(f"Watch error: {e}")
                await asyncio.sleep(5)

    async def close(self) -> None:
        await self._client.aclose()
```

```python
# ── Client-side load balancing ────────────────────────────────────

class LoadBalancer:
    """Base load balancer interface."""

    def pick(self, instances: list[ServiceInstance]) -> ServiceInstance | None:
        raise NotImplementedError


class RoundRobinBalancer(LoadBalancer):
    """Simple round-robin load balancer."""

    def __init__(self) -> None:
        self._index = 0

    def pick(self, instances: list[ServiceInstance]) -> ServiceInstance | None:
        healthy = [i for i in instances if i.healthy]
        if not healthy:
            return None
        instance = healthy[self._index % len(healthy)]
        self._index += 1
        return instance


class WeightedRoundRobinBalancer(LoadBalancer):
    """Weighted round-robin based on instance weights."""

    def __init__(self) -> None:
        self._current_weight = 0
        self._index = 0

    def pick(self, instances: list[ServiceInstance]) -> ServiceInstance | None:
        healthy = [i for i in instances if i.healthy]
        if not healthy:
            return None

        # Smooth weighted round-robin
        total_weight = sum(i.weight for i in healthy)
        best: ServiceInstance | None = None
        best_weight = -1

        for inst in healthy:
            inst._effective_weight = getattr(inst, "_effective_weight", inst.weight)
            inst._current_weight = getattr(inst, "_current_weight", 0) + inst._effective_weight

            if inst._current_weight > best_weight:
                best_weight = inst._current_weight
                best = inst

        if best:
            best._current_weight -= total_weight

        return best


class LeastConnectionsBalancer(LoadBalancer):
    """Pick instance with fewest active connections."""

    def __init__(self) -> None:
        self._connections: dict[str, int] = {}

    def pick(self, instances: list[ServiceInstance]) -> ServiceInstance | None:
        healthy = [i for i in instances if i.healthy]
        if not healthy:
            return None
        return min(
            healthy,
            key=lambda i: self._connections.get(i.address, 0),
        )

    def connect(self, address: str) -> None:
        self._connections[address] = self._connections.get(address, 0) + 1

    def disconnect(self, address: str) -> None:
        if address in self._connections:
            self._connections[address] = max(0, self._connections[address] - 1)


# ── gRPC channel pool with service discovery ─────────────────────

class GrpcChannelPool:
    """Manages gRPC channels with service discovery and load balancing."""

    def __init__(
        self,
        registry: ServiceRegistry,
        service_name: str,
        balancer: LoadBalancer | None = None,
        channel_options: list[tuple[str, Any]] | None = None,
    ) -> None:
        self._registry = registry
        self._service_name = service_name
        self._balancer = balancer or RoundRobinBalancer()
        self._options = channel_options or [
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.enable_retries", 1),
        ]
        self._channels: dict[str, grpc_aio.Channel] = {}
        self._instances: list[ServiceInstance] = []

    async def start(self) -> None:
        """Start watching for service changes."""
        self._instances = await self._registry.discover(self._service_name)
        asyncio.create_task(
            self._registry.watch(self._service_name, self._on_instances_changed)
        )

    async def _on_instances_changed(
        self, instances: list[ServiceInstance]
    ) -> None:
        """Handle service instance changes."""
        old_addrs = {i.address for i in self._instances}
        new_addrs = {i.address for i in instances}

        # Close channels to removed instances
        for addr in old_addrs - new_addrs:
            channel = self._channels.pop(addr, None)
            if channel:
                await channel.close()
                logger.info(f"Closed channel to removed instance: {addr}")

        self._instances = instances
        logger.info(
            f"Service {self._service_name}: {len(instances)} instances"
        )

    def get_channel(self) -> grpc_aio.Channel:
        """Get a channel to a healthy instance."""
        instance = self._balancer.pick(self._instances)
        if not instance:
            raise RuntimeError(
                f"No healthy instances for {self._service_name}"
            )

        if instance.address not in self._channels:
            self._channels[instance.address] = grpc_aio.insecure_channel(
                instance.address, options=self._options
            )

        return self._channels[instance.address]

    async def close(self) -> None:
        for channel in self._channels.values():
            await channel.close()
        self._channels.clear()
```

```python
# ── Kubernetes-native service discovery ───────────────────────────

# With K8s, you can use DNS-based or headless service discovery

K8S_CHANNEL_EXAMPLES = """
# Option 1: K8s Service DNS (server-side LB via kube-proxy)
channel = grpc.aio.insecure_channel(
    "my-grpc-service.default.svc.cluster.local:50051"
)

# Option 2: Headless service + client-side LB
# Uses dns:/// resolver for client-side round-robin
channel = grpc.aio.insecure_channel(
    "dns:///my-grpc-service-headless.default.svc.cluster.local:50051",
    options=[
        ("grpc.service_config", json.dumps({
            "loadBalancingConfig": [{"round_robin": {}}],
            "methodConfig": [{
                "name": [{}],
                "retryPolicy": {
                    "maxAttempts": 3,
                    "initialBackoff": "0.1s",
                    "maxBackoff": "5s",
                    "backoffMultiplier": 2,
                    "retryableStatusCodes": [
                        "UNAVAILABLE",
                        "DEADLINE_EXCEEDED",
                    ],
                },
            }],
        })),
    ],
)
"""


# ── Health checking (gRPC health protocol) ────────────────────────

from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_health.v1.health import HealthServicer


async def setup_health_check(
    server: grpc_aio.Server,
    services: list[str],
) -> HealthServicer:
    """Add gRPC health checking service."""
    health_servicer = HealthServicer()

    # Set all services as serving
    for service_name in services:
        await health_servicer.set(
            service_name,
            health_pb2.HealthCheckResponse.SERVING,
        )

    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    return health_servicer


# Client-side health check
async def check_health(channel: grpc_aio.Channel, service: str = "") -> bool:
    stub = health_pb2_grpc.HealthStub(channel)
    try:
        response = await stub.Check(
            health_pb2.HealthCheckRequest(service=service),
            timeout=5.0,
        )
        return response.status == health_pb2.HealthCheckResponse.SERVING
    except grpc_aio.AioRpcError:
        return False


# ── Complete server setup example ─────────────────────────────────

async def start_server_with_discovery(
    host: str = "0.0.0.0",
    port: int = 50051,
    consul_url: str = "http://localhost:8500",
) -> None:
    server = grpc_aio.server()

    # Add your services
    # add_UserServiceServicer_to_server(UserServiceImpl(), server)

    # Add health checking
    health = await setup_health_check(server, ["api.v1.UserService"])

    server.add_insecure_port(f"{host}:{port}")
    await server.start()

    # Register with Consul
    registry = ConsulServiceRegistry(consul_url)
    instance = ServiceInstance(
        host=host,
        port=port,
        service_name="user-service",
        metadata={"version": "1.0.0", "region": "us-east-1"},
    )
    await registry.register(instance)

    try:
        await server.wait_for_termination()
    finally:
        await health.set(
            "api.v1.UserService",
            health_pb2.HealthCheckResponse.NOT_SERVING,
        )
        await asyncio.sleep(5)  # drain period
        await registry.deregister(instance)
```

| LB Strategy | Distribution | Stickiness | Best For |
|---|---|---|---|
| Round-robin | Even | None | Homogeneous instances |
| Weighted round-robin | By weight | None | Mixed-capacity instances |
| Least connections | Adaptive | None | Varying request durations |
| Random | Statistical | None | Simple, low-overhead |
| Consistent hashing | Key-based | Per-key | Caching, session affinity |
| Pick-first (gRPC default) | Single server | Full | Single-server setups |

Key patterns:
1. Use **client-side load balancing** with `dns:///` resolver for gRPC headless services.
2. Register gRPC **health checking** service for L7 load balancers and readiness probes.
3. **Consul watch** with long-polling updates the channel pool on instance changes.
4. Drain connections before deregistering: set health to `NOT_SERVING`, wait, then deregister.
5. Use `grpc.service_config` JSON for built-in retry policy and load balancing.
6. For Kubernetes, headless services + `dns:///` gives client-side LB without a sidecar.'''
    ),
]
"""
