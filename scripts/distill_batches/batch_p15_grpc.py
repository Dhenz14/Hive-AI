"""p15 grpc"""

PAIRS = [
    (
        "networking/grpc-fundamentals",
        "Explain gRPC fundamentals including Protocol Buffers, service definition, the four communication patterns (unary, server streaming, client streaming, bidirectional), interceptors/middleware, error handling, and deadline propagation. Include Python examples with grpcio.",
        '''gRPC is a high-performance RPC framework that uses HTTP/2 for transport and Protocol Buffers for serialization. It's the standard for inter-service communication in microservice architectures where REST's overhead is too high.

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
            status=orders_pb2.ORDER_STATUS_SUBMITTED,'''
    ),
    (
        "networking/message-queues-patterns",
        "Explain message queue patterns including point-to-point vs pub-sub, exactly-once delivery, dead letter queues, message ordering, idempotent consumers, and backpressure handling. Compare Kafka, RabbitMQ, and Redis Streams for different use cases.",
        '''Message queues decouple producers from consumers, enabling asynchronous processing, load leveling, and fault tolerance. The choice of queue system and patterns depends on your consistency and ordering requirements.

### Messaging Patterns

```
Point-to-Point (Queue):
  Producer -> [Queue] -> Consumer
  Each message is processed by exactly ONE consumer
  Use for: task distribution, work queues

Publish-Subscribe (Topic):
  Producer -> [Topic] -> Consumer A
                    -> Consumer B
                    -> Consumer C
  Each message goes to ALL subscribers
  Use for: event broadcasting, notifications

Consumer Group (Kafka-style):
  Producer -> [Topic/Partition 0] -> Consumer Group A, Consumer 1
                                 -> Consumer Group B, Consumer 1
           -> [Topic/Partition 1] -> Consumer Group A, Consumer 2
                                 -> Consumer Group B, Consumer 2
  Messages partitioned for parallel processing within a group
  Use for: high-throughput event processing
```

### Idempotent Consumers

The most important pattern -- process messages safely even if delivered more than once:

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
            ex=int(self.ttl.total_seconds()),'''
    ),
    (
        "x-max-length",
        "} )",
        '''channel.confirm_delivery()
channel.basic_publish(
    exchange="",
    routing_key="orders",
    body=json.dumps(order_event),
    properties=pika.BasicProperties(
        delivery_mode=2,  # Persistent
        content_type="application/json",
        message_id=str(uuid4()),'''
    ),
    (
        "payment-svc",
        "{'orders': '>'} count=10, block=5000 ) for stream, msgs in (messages or []): for msg_id, data in msgs: process_order(json.loads(data[b'event'])) r.xack('orders', 'payment-svc', msg_id)",
        '''### Choosing the Right System

| Requirement | Kafka | RabbitMQ | Redis Streams |
|-------------|-------|----------|---------------|
| Throughput | 1M+ msg/s | 50K msg/s | 100K msg/s |
| Ordering | Per-partition | Per-queue | Global |
| Replay | Yes (log-based) | No | Limited |
| Routing | Topic-based | Complex (exchanges) | Simple |
| Latency | ~5ms | ~1ms | ~0.5ms |
| Persistence | Excellent | Good | Good |
| Operations | Complex | Moderate | Simple |

**Message queue principles**: (1) Always design idempotent consumers -- at-least-once delivery is the practical reality, (2) Use dead letter queues for messages that can't be processed, (3) Partition by entity ID for ordering (e.g., all events for order-123 go to the same partition), (4) Set message TTLs to prevent unbounded queue growth, (5) Monitor consumer lag -- growing lag means consumers can't keep up.'''
    ),
    (
        "security/oauth2-oidc-deep-dive",
        "Explain OAuth 2.0 and OpenID Connect in depth including authorization code flow with PKCE, token types (access, refresh, ID), JWT structure and validation, token introspection, scopes and claims, and secure implementation patterns for SPAs and APIs.",
        '''OAuth 2.0 handles **authorization** (what can you access?) while OpenID Connect (OIDC) adds **authentication** (who are you?) on top. Understanding both is essential for building secure applications.

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
        code_challenge=code_challenge,'''
    ),
    (
        "code_challenge_method",
        "} url = f'{auth_endpoint}?{urllib.parse.urlencode(params)} return url, state",
        '''pkce = generate_pkce()
auth_url, state = build_authorization_url(
    auth_endpoint="https://auth.example.com/authorize",
    client_id="my-app",
    redirect_uri="https://myapp.com/callback",
    pkce=pkce,
    scopes=["openid", "profile", "email", "orders:read"],'''
    ),
    (
        "code_verifier",
        "} if client_secret: data['client_secret'] = client_secret async with httpx.AsyncClient() as client: response = await client.post(token_endpoint, data=data) response.raise_for_status() return response.json()",
        '''# {
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
                options={'''
    ),
    (
        "require",
        "} ) return payload except jwt.ExpiredSignatureError: raise TokenValidationError('Token has expired') except jwt.InvalidIssuerError: raise TokenValidationError('Invalid token issuer') except jwt.InvalidAudienceError: raise TokenValidationError('Invalid token audience') except jwt.InvalidTokenError as e: raise TokenValidationError(f'Invalid token: {e}') class TokenValidationError(Exception): pass",
        '''### Scope-Based Authorization

```python
from functools import wraps
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer()
validator = JWTValidator(
    issuer="https://auth.example.com",
    audience="https://api.example.com",
    jwks_uri="https://auth.example.com/.well-known/jwks.json",'''
    ),
    (
        "client_id",
        "} ) if response.status_code == 401:",
        '''self._refresh_token = None
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

**OAuth2/OIDC security rules**: (1) Always use PKCE -- even for confidential clients (defense in depth), (2) Validate JWTs with the issuer's public keys (JWKS), never skip verification, (3) Store refresh tokens securely -- they're equivalent to long-lived credentials, (4) Use short-lived access tokens (5-15 min) with refresh token rotation, (5) Check scopes for authorization -- don't rely solely on authentication, (6) Validate `iss`, `aud`, `exp`, and `nonce` claims on every token.'''
    ),
]
