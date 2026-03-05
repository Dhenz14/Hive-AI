PAIRS = [
    (
        "graphql/schema-federation-microservices",
        r"""Explain Apollo Federation v2 for GraphQL microservices architecture, including @key, @requires, and @external directives, entity resolution across subgraphs, subgraph composition strategies, and best practices for splitting a monolithic schema into federated services.""",
        r"""## Apollo Federation v2: Schema Federation and Microservices Composition

Building a **GraphQL API** that spans multiple microservices is one of the most impactful architectural decisions a team can make. **Apollo Federation v2** provides a declarative, standards-based approach to composing multiple **subgraph** schemas into a single **supergraph** that clients query through a **router**. The key insight is that each service owns its slice of the graph, and the federation runtime handles stitching entity references across service boundaries — **because** no single team should need to understand the entire schema to ship features.

### Why Federation Over Schema Stitching

A **common mistake** is to conflate Federation with older schema-stitching approaches. Schema stitching requires a centralized gateway that manually merges types, which becomes a bottleneck as the number of services grows. Federation, **however**, inverts control: each subgraph declares what it contributes and what it needs from other subgraphs, and the router uses a **query plan** to orchestrate fetches automatically. **Therefore**, teams can deploy independently without coordinating schema merges.

### Core Directives: @key, @requires, @external

The three foundational directives define how entities are identified, how fields from foreign subgraphs are referenced, and how computed fields declare their data dependencies.

```python
# subgraph_users.py — User service subgraph
# Uses ariadne for schema-first federation

from ariadne import QueryType, ObjectType, make_executable_schema
from ariadne.asgi import GraphQL

# Federation schema definition for the Users subgraph
USER_SCHEMA = '''
    extend schema @link(url: "https://specs.apollo.dev/federation/v2.3",
                        import: ["@key", "@shareable"])

    type Query {
        user(id: ID!): User
        users(limit: Int = 10, offset: Int = 0): [User!]!
    }

    # @key declares the primary key for entity resolution
    # Multiple @key directives allow resolution by different fields
    type User @key(fields: "id") @key(fields: "email") {
        id: ID!
        email: String!
        displayName: String!
        avatarUrl: String
        createdAt: DateTime!
    }

    scalar DateTime
'''

query = QueryType()
user_type = ObjectType("User")

USERS_DB: dict[str, dict] = {
    "u-1": {"id": "u-1", "email": "alice@example.com",
            "displayName": "Alice", "avatarUrl": None,
            "createdAt": "2024-01-15T10:00:00Z"},
    "u-2": {"id": "u-2", "email": "bob@example.com",
            "displayName": "Bob", "avatarUrl": "/avatars/bob.png",
            "createdAt": "2024-02-20T14:30:00Z"},
}

@query.field("user")
def resolve_user(_, info, id: str):
    return USERS_DB.get(id)

@query.field("users")
def resolve_users(_, info, limit: int = 10, offset: int = 0):
    all_users = list(USERS_DB.values())
    return all_users[offset:offset + limit]

# Entity resolver — called by the router when another subgraph
# references a User by its @key fields
def resolve_user_reference(representations: list[dict]) -> list[dict | None]:
    results = []
    for ref in representations:
        if "id" in ref:
            results.append(USERS_DB.get(ref["id"]))
        elif "email" in ref:
            match = next((u for u in USERS_DB.values()
                          if u["email"] == ref["email"]), None)
            results.append(match)
        else:
            results.append(None)
    return results
```

Now the **Reviews subgraph** extends the `User` type with fields it owns, using `@external` to reference foreign fields and `@requires` to declare computed-field dependencies:

```python
# subgraph_reviews.py — Reviews service subgraph

from dataclasses import dataclass, field
from typing import Optional

# Federation schema for Reviews subgraph
REVIEW_SCHEMA = '''
    extend schema @link(url: "https://specs.apollo.dev/federation/v2.3",
                        import: ["@key", "@requires", "@external", "@provides"])

    type Query {
        reviews(productId: ID!): [Review!]!
        topReviewers(limit: Int = 5): [User!]!
    }

    # Extend User from Users subgraph — add review-related fields
    type User @key(fields: "id") {
        id: ID!
        # @external marks fields owned by another subgraph
        # We need displayName to compute reviewSignature
        displayName: String! @external
        reviews: [Review!]!
        averageRating: Float
        # @requires tells the router to fetch displayName from Users
        # subgraph BEFORE calling this resolver
        reviewSignature: String! @requires(fields: "displayName")
    }

    type Review @key(fields: "id") {
        id: ID!
        body: String!
        rating: Int!
        author: User!
        product: Product!
        createdAt: DateTime!
    }

    # Stub type — we only reference Product by key
    type Product @key(fields: "id") {
        id: ID!
    }

    scalar DateTime
'''

@dataclass
class ReviewRecord:
    id: str
    body: str
    rating: int
    author_id: str
    product_id: str
    created_at: str

# In-memory store for demonstration
REVIEWS: list[ReviewRecord] = [
    ReviewRecord("r-1", "Excellent product!", 5, "u-1", "p-100", "2024-03-01T09:00:00Z"),
    ReviewRecord("r-2", "Decent but overpriced.", 3, "u-2", "p-100", "2024-03-02T11:00:00Z"),
    ReviewRecord("r-3", "Would buy again.", 4, "u-1", "p-200", "2024-03-05T16:00:00Z"),
]

def resolve_user_reviews(user_ref: dict) -> list[dict]:
    user_id = user_ref["id"]
    return [r.__dict__ for r in REVIEWS if r.author_id == user_id]

def resolve_review_signature(user_ref: dict) -> str:
    # @requires(fields: "displayName") guarantees displayName is populated
    # by the router before this resolver is called
    display_name = user_ref["displayName"]
    review_count = sum(1 for r in REVIEWS if r.author_id == user_ref["id"])
    return f"{display_name} ({review_count} reviews)"
```

### Subgraph Composition and the Router

The **supergraph schema** is produced by running `rover supergraph compose` or by Apollo GraphOS managed federation. The router reads this composed schema and builds **query plans** — a DAG of fetches that minimizes network round-trips.

```python
# composition_config.yaml parsed by rover CLI
# rover supergraph compose --config composition_config.yaml > supergraph.graphql

# Best practice: run composition in CI to catch breaking changes early
# Pitfall: deploying a subgraph change that breaks composition will
# take down the entire supergraph if you skip CI validation

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

class SubgraphConfig(NamedTuple):
    name: str
    url: str
    schema_path: Path

SUBGRAPHS: list[SubgraphConfig] = [
    SubgraphConfig("users", "http://users-svc:4001/graphql",
                   Path("schemas/users.graphql")),
    SubgraphConfig("reviews", "http://reviews-svc:4002/graphql",
                   Path("schemas/reviews.graphql")),
    SubgraphConfig("products", "http://products-svc:4003/graphql",
                   Path("schemas/products.graphql")),
]

def validate_composition(subgraphs: list[SubgraphConfig]) -> bool:
    # Generate supergraph config YAML
    config_lines = ["federation_version: =2.3", "subgraphs:"]
    for sg in subgraphs:
        config_lines.append(f"  {sg.name}:")
        config_lines.append(f"    routing_url: {sg.url}")
        config_lines.append(f"    schema:")
        config_lines.append(f"      file: {sg.schema_path}")

    config_path = Path("/tmp/supergraph-config.yaml")
    config_path.write_text("\n".join(config_lines))

    result = subprocess.run(
        ["rover", "supergraph", "compose", "--config", str(config_path)],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        print(f"Composition FAILED:\n{result.stderr}", file=sys.stderr)
        return False

    # Write composed supergraph for the router
    Path("supergraph.graphql").write_text(result.stdout)
    print(f"Composition succeeded — {len(result.stdout)} chars")
    return True

def run_schema_checks(subgraph: SubgraphConfig, graph_ref: str) -> bool:
    # Best practice: run schema checks against production traffic
    # to detect breaking changes before deployment
    result = subprocess.run(
        ["rover", "subgraph", "check", graph_ref,
         "--name", subgraph.name,
         "--schema", str(subgraph.schema_path)],
        capture_output=True, text=True
    )
    return result.returncode == 0
```

### Best Practices for Splitting a Monolithic Schema

**Best practice** number one: split by **domain boundary**, not by type. A `User` type might have fields contributed by authentication, billing, social, and notification services. Each service extends `User` with the fields it owns. **Therefore**, the type definition is distributed, but ownership is clear.

**Pitfall**: creating "thin" subgraphs that own only one or two types leads to excessive inter-service chatter. Group related types together — a "commerce" subgraph might own `Order`, `LineItem`, `Payment`, and `Refund` because they share a transactional boundary.

**Best practice** number two: use `@provides` to reduce round-trips. If the Reviews subgraph already has the author's `displayName` cached locally, it can declare `@provides(fields: "displayName")` on the `Review.author` field, allowing the router to skip a fetch to the Users subgraph.

### Trade-offs and Considerations

The **trade-off** with federation is operational complexity: you now have N+1 services to deploy (N subgraphs plus the router), composition validation in CI, and distributed tracing requirements. **However**, the benefits — independent deployability, team autonomy, and schema-as-contract — outweigh the costs for organizations with more than two or three backend teams.

## Summary / Key Takeaways

- **@key** identifies entities across subgraph boundaries and enables the router to resolve cross-service references.
- **@external** and **@requires** let a subgraph declare dependencies on fields owned by other subgraphs, and the router orchestrates fetches automatically.
- Always validate **composition in CI** before deploying subgraph changes — a broken compose takes down the entire API.
- Split schemas by **domain boundary**, not by individual type, to minimize inter-service chatter.
- Use **@provides** to short-circuit unnecessary fetches when a subgraph already has the data locally.
- The fundamental **trade-off** is operational complexity versus team autonomy — federation pays off at scale but may be premature for small teams.
"""
    ),
    (
        "graphql/subscriptions-websocket-pubsub",
        r"""How do GraphQL subscriptions work with WebSocket transport and pub/sub backends? Explain the subscription lifecycle, connection protocols, implementing subscriptions with Redis pub/sub for horizontal scaling, subscription filtering, and best practices for managing connection state.""",
        r"""## GraphQL Subscriptions: WebSocket Transport, Pub/Sub, and Scalable Real-Time APIs

**GraphQL subscriptions** enable servers to push data to clients in real time, completing the trifecta of query (read), mutation (write), and subscription (stream). Unlike queries and mutations which follow a request-response cycle, subscriptions establish a **persistent connection** — typically over WebSockets — through which the server emits events as they occur. This is essential **because** modern applications demand real-time features like chat, notifications, live dashboards, and collaborative editing without resorting to polling.

### The Subscription Protocol: graphql-ws vs subscriptions-transport-ws

A **common mistake** is confusing the two WebSocket sub-protocols. The legacy `subscriptions-transport-ws` protocol (used by older Apollo Client) is deprecated. The modern standard is `graphql-ws` (maintained by Denis Badurina), which uses the `graphql-transport-ws` sub-protocol. **Therefore**, always use the `graphql-ws` library on both server and client.

The connection lifecycle follows these phases:

1. **ConnectionInit** — client sends authentication payload
2. **ConnectionAck** — server validates and acknowledges
3. **Subscribe** — client sends subscription operation
4. **Next** — server pushes data events
5. **Complete** — either side terminates the subscription
6. **Ping/Pong** — keepalive mechanism

```python
# subscription_server.py — GraphQL subscriptions with Strawberry and WebSockets

import asyncio
from typing import AsyncGenerator, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import strawberry
from strawberry.types import Info
from strawberry.subscriptions import GRAPHQL_TRANSPORT_WS_PROTOCOL

# Domain types
@strawberry.enum
class MessageType(Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    SYSTEM = "SYSTEM"

@strawberry.type
class ChatMessage:
    id: str
    channel_id: str
    author_id: str
    content: str
    message_type: MessageType
    timestamp: datetime

@strawberry.input
class MessageFilter:
    channel_id: str
    message_types: Optional[list[MessageType]] = None
    exclude_authors: Optional[list[str]] = None

# In-process pub/sub for single-instance use
@dataclass
class InMemoryPubSub:
    # Maps channel names to sets of subscriber queues
    _subscribers: dict[str, set[asyncio.Queue]] = field(default_factory=dict)

    async def publish(self, channel: str, message: ChatMessage) -> int:
        queues = self._subscribers.get(channel, set())
        for q in queues:
            await q.put(message)
        return len(queues)

    async def subscribe(self, channel: str) -> AsyncGenerator[ChatMessage, None]:
        queue: asyncio.Queue[ChatMessage] = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(channel, set()).add(queue)
        try:
            while True:
                message = await queue.get()
                yield message
        finally:
            # Cleanup on disconnect — best practice
            self._subscribers[channel].discard(queue)
            if not self._subscribers[channel]:
                del self._subscribers[channel]

pubsub = InMemoryPubSub()

@strawberry.type
class Query:
    @strawberry.field
    def health(self) -> str:
        return "ok"

@strawberry.type
class Mutation:
    @strawberry.mutation
    async def send_message(
        self,
        channel_id: str,
        author_id: str,
        content: str,
        message_type: MessageType = MessageType.TEXT,
    ) -> ChatMessage:
        msg = ChatMessage(
            id=f"msg-{datetime.utcnow().timestamp()}",
            channel_id=channel_id,
            author_id=author_id,
            content=content,
            message_type=message_type,
            timestamp=datetime.utcnow(),
        )
        await pubsub.publish(f"chat:{channel_id}", msg)
        return msg

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def on_message(
        self,
        info: Info,
        filter: MessageFilter,
    ) -> AsyncGenerator[ChatMessage, None]:
        # Subscribe to the channel's event stream
        async for message in pubsub.subscribe(f"chat:{filter.channel_id}"):
            # Apply server-side filtering — best practice to reduce
            # unnecessary data sent over the wire
            if filter.message_types and message.message_type not in filter.message_types:
                continue
            if filter.exclude_authors and message.author_id in filter.exclude_authors:
                continue
            yield message

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
)
```

### Scaling Subscriptions with Redis Pub/Sub

The in-memory approach above breaks when you scale horizontally — **because** a message published on server A will not reach subscribers connected to server B. **Therefore**, you need an external pub/sub broker. Redis is the most common choice due to its low latency and built-in pub/sub support.

```python
# redis_pubsub.py — Redis-backed pub/sub for horizontal scaling

import asyncio
import json
from typing import AsyncGenerator
from dataclasses import dataclass

import redis.asyncio as aioredis

@dataclass
class RedisPubSub:
    redis_url: str = "redis://localhost:6379"
    _redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(
            self.redis_url,
            decode_responses=True,
            max_connections=50,
        )

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()

    async def publish(self, channel: str, data: dict) -> int:
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        payload = json.dumps(data, default=str)
        return await self._redis.publish(channel, payload)

    async def subscribe(self, channel: str) -> AsyncGenerator[dict, None]:
        if not self._redis:
            raise RuntimeError("Not connected to Redis")

        # Each subscriber gets its own connection — required because
        # Redis pub/sub puts the connection in subscriber mode
        sub_conn = aioredis.from_url(self.redis_url, decode_responses=True)
        psub = sub_conn.pubsub()
        await psub.subscribe(channel)

        try:
            async for raw_message in psub.listen():
                if raw_message["type"] == "message":
                    data = json.loads(raw_message["data"])
                    yield data
        finally:
            await psub.unsubscribe(channel)
            await psub.aclose()
            await sub_conn.aclose()

    async def psubscribe(self, pattern: str) -> AsyncGenerator[dict, None]:
        # Pattern subscriptions — e.g., "chat:*" for all channels
        # Trade-off: more flexible but higher Redis CPU usage
        if not self._redis:
            raise RuntimeError("Not connected to Redis")

        sub_conn = aioredis.from_url(self.redis_url, decode_responses=True)
        psub = sub_conn.pubsub()
        await psub.psubscribe(pattern)

        try:
            async for raw_message in psub.listen():
                if raw_message["type"] == "pmessage":
                    data = json.loads(raw_message["data"])
                    yield data
        finally:
            await psub.punsubscribe(pattern)
            await psub.aclose()
            await sub_conn.aclose()


# Connection lifecycle management with authentication
class SubscriptionConnectionManager:
    # Tracks active connections for monitoring and graceful shutdown

    def __init__(self, pubsub: RedisPubSub, max_connections: int = 10000):
        self._pubsub = pubsub
        self._max_connections = max_connections
        self._active: dict[str, dict] = {}  # connection_id -> metadata

    async def on_connect(self, connection_id: str, auth_payload: dict) -> bool:
        if len(self._active) >= self._max_connections:
            return False  # Reject — backpressure

        # Validate auth token from ConnectionInit payload
        token = auth_payload.get("authorization", "")
        user_id = await self._validate_token(token)
        if not user_id:
            return False

        self._active[connection_id] = {
            "user_id": user_id,
            "connected_at": asyncio.get_event_loop().time(),
            "subscriptions": set(),
        }
        return True

    async def on_disconnect(self, connection_id: str) -> None:
        self._active.pop(connection_id, None)

    async def _validate_token(self, token: str) -> str | None:
        # Best practice: validate JWT or session token
        # Pitfall: skipping auth on WebSocket connections
        if token.startswith("Bearer "):
            return "validated-user-id"
        return None
```

### Subscription Filtering Best Practices

**Best practice**: always filter on the server side, not the client. Sending all events to every subscriber and letting the client discard irrelevant ones wastes bandwidth and exposes data the user should not see. Use **topic-based filtering** (subscribe to specific Redis channels) combined with **payload filtering** (check fields after deserialization) for defense in depth.

```python
# subscription_filter.py — Server-side subscription filtering engine

from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field

@dataclass
class SubscriptionFilter:
    # Composable filter predicates for subscription events
    channel_pattern: str
    predicates: list[Callable[[dict[str, Any]], bool]] = field(default_factory=list)

    def matches(self, event: dict[str, Any]) -> bool:
        # All predicates must pass — AND semantics
        return all(pred(event) for pred in self.predicates)

    def add_field_filter(self, field_name: str, allowed_values: set[str]) -> "SubscriptionFilter":
        # Best practice: validate filter fields against the schema
        # to prevent clients from filtering on nonexistent fields
        self.predicates.append(
            lambda evt, f=field_name, v=allowed_values: evt.get(f) in v
        )
        return self

    def add_exclude_filter(self, field_name: str, excluded_values: set[str]) -> "SubscriptionFilter":
        self.predicates.append(
            lambda evt, f=field_name, v=excluded_values: evt.get(f) not in v
        )
        return self


async def filtered_subscribe(
    pubsub: "RedisPubSub",
    sub_filter: SubscriptionFilter,
) -> "AsyncGenerator[dict, None]":
    # Combines topic-level and payload-level filtering
    # Topic-level: only subscribe to relevant Redis channels
    # Payload-level: apply predicates after deserialization
    async for event in pubsub.subscribe(sub_filter.channel_pattern):
        if sub_filter.matches(event):
            yield event
        # Events that don't match are silently dropped — therefore
        # the client only receives relevant data, saving bandwidth
```

### Trade-offs: WebSockets vs SSE

The **trade-off** between WebSockets and Server-Sent Events (SSE) is worth considering. SSE is simpler (HTTP-based, no special proxy config), supports automatic reconnection, and works through most CDNs. **However**, SSE is unidirectional — the client cannot send messages back over the same connection. For GraphQL subscriptions where the client only needs to receive updates after the initial subscribe message, SSE (used by the newer `graphql-sse` protocol) can be a better fit, especially behind HTTP/2.

## Summary / Key Takeaways

- Use the modern **graphql-ws** (`graphql-transport-ws`) protocol, not the deprecated `subscriptions-transport-ws`.
- **Always authenticate** during `ConnectionInit` — a **pitfall** is leaving WebSocket endpoints open without token validation.
- For horizontal scaling, use **Redis pub/sub** or a similar broker so events reach subscribers on any server instance.
- Apply **server-side filtering** to minimize data transfer and prevent information leakage.
- Consider **SSE** for simpler deployments where bidirectional communication is not required — the **trade-off** is simplicity versus flexibility.
- Implement **backpressure** and connection limits to prevent resource exhaustion from too many concurrent subscriptions.
"""
    ),
    (
        "graphql/caching-strategies-persisted-queries",
        r"""What are the best caching strategies for GraphQL APIs? Cover normalized client-side caching, CDN response caching, persisted queries, automatic persisted queries (APQ), cache invalidation patterns, and the trade-offs between different caching layers for GraphQL performance optimization.""",
        r"""## GraphQL Caching Strategies: From Client Normalization to CDN Edge Caching

Caching in **GraphQL** is fundamentally harder than in REST **because** GraphQL uses a single endpoint with POST requests carrying arbitrary query shapes in the body. Traditional HTTP caching relies on URL-based cache keys, which works beautifully for REST's resource-oriented URLs but breaks down when every request hits `/graphql`. **Therefore**, GraphQL caching requires a layered strategy spanning client-side normalization, server-side response caching, CDN integration, and persisted queries.

### Layer 1: Normalized Client-Side Caching

The most impactful caching layer is the **normalized cache** in the client. Libraries like Apollo Client and urql decompose query responses into individual objects, store them by a unique key (typically `__typename:id`), and automatically update all queries referencing the same entity when a mutation returns updated data.

```python
# Demonstrating normalized cache concepts with a Python implementation
# to illustrate what Apollo Client does internally

from typing import Any, Optional
from dataclasses import dataclass, field
import hashlib
import json

@dataclass
class CacheEntry:
    data: dict[str, Any]
    refs: set[str] = field(default_factory=set)  # entity keys this entry depends on

class NormalizedCache:
    # Simulates what Apollo Client's InMemoryCache does

    def __init__(self) -> None:
        self._entities: dict[str, dict[str, Any]] = {}  # "User:u-1" -> field data
        self._queries: dict[str, CacheEntry] = {}  # query hash -> result + deps

    def _entity_key(self, typename: str, entity_id: str) -> str:
        return f"{typename}:{entity_id}"

    def _query_key(self, query: str, variables: dict) -> str:
        raw = json.dumps({"q": query, "v": variables}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def write_query(self, query: str, variables: dict,
                    data: dict[str, Any]) -> None:
        # Normalize: extract entities and replace with references
        refs: set[str] = set()
        normalized = self._normalize(data, refs)
        qkey = self._query_key(query, variables)
        self._queries[qkey] = CacheEntry(data=normalized, refs=refs)

    def _normalize(self, obj: Any, refs: set[str]) -> Any:
        if isinstance(obj, dict):
            if "__typename" in obj and "id" in obj:
                key = self._entity_key(obj["__typename"], obj["id"])
                refs.add(key)
                # Store entity fields in the normalized store
                self._entities[key] = {
                    k: self._normalize(v, refs) for k, v in obj.items()
                }
                # Replace with a reference
                return {"__ref": key}
            return {k: self._normalize(v, refs) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._normalize(item, refs) for item in obj]
        return obj

    def read_query(self, query: str, variables: dict) -> Optional[dict]:
        qkey = self._query_key(query, variables)
        entry = self._queries.get(qkey)
        if entry is None:
            return None
        # Denormalize: resolve references back to entity data
        return self._denormalize(entry.data)

    def _denormalize(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            if "__ref" in obj:
                entity = self._entities.get(obj["__ref"])
                if entity:
                    return self._denormalize(entity)
                return None
            return {k: self._denormalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._denormalize(item) for item in obj]
        return obj

    def evict(self, typename: str, entity_id: str) -> int:
        # Cache invalidation — evict an entity and all queries referencing it
        key = self._entity_key(typename, entity_id)
        self._entities.pop(key, None)
        evicted = 0
        for qkey, entry in list(self._queries.items()):
            if key in entry.refs:
                del self._queries[qkey]
                evicted += 1
        return evicted
```

### Layer 2: Server-Side Response Caching

On the server, you can cache **full responses** keyed by the query document and variables. This works best for **public, non-personalized** data. The **trade-off** is that full-response caching ignores the normalized structure — if one entity in a large response changes, the entire cached response is invalidated.

```python
# server_cache.py — Response-level caching with scope-aware TTLs

import hashlib
import json
import time
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum

import redis.asyncio as aioredis

class CacheScope(Enum):
    PUBLIC = "PUBLIC"      # Shared across all users, safe for CDN
    PRIVATE = "PRIVATE"    # Per-user, never CDN-cached
    NO_CACHE = "NO_CACHE"  # Never cached

@dataclass
class CacheHint:
    max_age: int  # seconds
    scope: CacheScope

class GraphQLResponseCache:
    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._redis_url = redis_url

    async def connect(self) -> None:
        self._redis = aioredis.from_url(self._redis_url)

    def _cache_key(self, query: str, variables: dict,
                   user_id: Optional[str], scope: CacheScope) -> str:
        # Best practice: include user_id in key for PRIVATE scope
        key_parts = {"query": query, "variables": variables}
        if scope == CacheScope.PRIVATE and user_id:
            key_parts["user"] = user_id
        raw = json.dumps(key_parts, sort_keys=True)
        digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
        return f"gql:resp:{digest}"

    async def get(self, query: str, variables: dict,
                  user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        if not self._redis:
            return None
        # Try PUBLIC first, then PRIVATE
        for scope in (CacheScope.PUBLIC, CacheScope.PRIVATE):
            key = self._cache_key(query, variables, user_id, scope)
            cached = await self._redis.get(key)
            if cached:
                return json.loads(cached)
        return None

    async def set(self, query: str, variables: dict,
                  response: dict[str, Any], hint: CacheHint,
                  user_id: Optional[str] = None) -> None:
        if not self._redis or hint.scope == CacheScope.NO_CACHE:
            return
        key = self._cache_key(query, variables, user_id, hint.scope)
        await self._redis.setex(key, hint.max_age, json.dumps(response))

    async def invalidate_by_type(self, typename: str) -> int:
        # Pitfall: this requires maintaining a reverse index
        # from typenames to cache keys — common mistake is to skip this
        # and end up serving stale data after mutations
        if not self._redis:
            return 0
        pattern = f"gql:dep:{typename}:*"
        count = 0
        async for key in self._redis.scan_iter(match=pattern):
            cache_keys = await self._redis.smembers(key)
            if cache_keys:
                await self._redis.delete(*cache_keys)
                count += len(cache_keys)
            await self._redis.delete(key)
        return count
```

### Layer 3: Persisted Queries and APQ

**Persisted queries** replace the full query document with a hash, reducing payload size and enabling GET-based CDN caching. **Automatic Persisted Queries (APQ)** negotiate this automatically: the client sends a hash first, and if the server does not recognize it, the client retries with the full query, which the server then stores for future requests.

```python
# apq.py — Automatic Persisted Queries implementation

import hashlib
from typing import Optional
from dataclasses import dataclass

@dataclass
class APQStore:
    # Best practice: use Redis or similar shared store for multi-instance
    _store: dict[str, str]  # hash -> query document

    def __init__(self) -> None:
        self._store = {}

    def compute_hash(self, query: str) -> str:
        # APQ uses SHA-256 by convention
        return hashlib.sha256(query.strip().encode()).hexdigest()

    def get_query(self, query_hash: str) -> Optional[str]:
        return self._store.get(query_hash)

    def register_query(self, query: str) -> str:
        query_hash = self.compute_hash(query)
        self._store[query_hash] = query
        return query_hash

    def handle_request(self, body: dict) -> dict:
        extensions = body.get("extensions", {})
        persisted = extensions.get("persistedQuery", {})
        query_hash = persisted.get("sha256Hash")
        query = body.get("query")

        if query_hash and not query:
            # Client sent hash only — look up
            stored = self.get_query(query_hash)
            if stored is None:
                # Tell client to retry with full query
                return {"errors": [{"message": "PersistedQueryNotFound",
                                    "extensions": {"code": "PERSISTED_QUERY_NOT_FOUND"}}]}
            return {"query": stored, "variables": body.get("variables", {})}

        if query_hash and query:
            # Client sent both — register and proceed
            actual_hash = self.compute_hash(query)
            if actual_hash != query_hash:
                return {"errors": [{"message": "Hash mismatch",
                                    "extensions": {"code": "PERSISTED_QUERY_HASH_MISMATCH"}}]}
            self.register_query(query)
            return {"query": query, "variables": body.get("variables", {})}

        # No APQ — regular request
        return {"query": query, "variables": body.get("variables", {})}

# CDN integration — with APQ + GET, queries become cacheable URLs:
# GET /graphql?extensions={"persistedQuery":{"sha256Hash":"abc123","version":1}}
# The CDN caches this like any other GET request.
# Trade-off: only works for queries, not mutations.
# Best practice: set Cache-Control headers based on schema-level cache hints.
```

### Cache Invalidation Patterns

Cache invalidation is the hardest problem in caching. For GraphQL, three patterns dominate:

1. **TTL-based**: simple but risks serving stale data within the TTL window
2. **Mutation-triggered**: after a mutation resolves, evict or update cached entries for affected types
3. **Event-driven**: use database change-data-capture (CDC) to invalidate caches reactively

**Best practice**: combine TTL as a safety net with mutation-triggered invalidation for correctness. **However**, event-driven invalidation is required when data changes outside the GraphQL layer (e.g., batch jobs, admin panels).

## Summary / Key Takeaways

- **Normalized client caching** (Apollo Client, urql) is the highest-impact optimization — it eliminates redundant network requests and keeps the UI consistent across components.
- **Server response caching** works well for public data but requires a reverse index for type-based invalidation — a **common mistake** is skipping this index and serving stale data.
- **APQ** reduces payload sizes and enables GET-based **CDN caching**, turning GraphQL performance characteristics closer to REST for read-heavy workloads.
- The fundamental **trade-off** is freshness versus performance: aggressive caching improves latency but risks stale data. Layer your caches and choose TTLs carefully.
- **Pitfall**: caching authenticated/personalized responses in a shared cache (CDN or public Redis). Always scope private data to the individual user.
- Mutation-triggered invalidation combined with TTL fallbacks provides the best balance of correctness and simplicity for most applications.
"""
    ),
    (
        "graphql/error-handling-result-pattern",
        r"""How should errors be handled in GraphQL APIs? Explain the union-based result type pattern, error classification with extensions, partial error handling, the trade-offs between error unions and top-level errors, and client-side error handling strategies with typed error responses.""",
        r"""## GraphQL Error Handling: Union Types, Result Patterns, and Typed Error Strategies

Error handling in **GraphQL** is one of the most under-designed aspects of many APIs. The default approach — returning errors in the top-level `errors` array — has significant limitations **because** these errors are untyped, hard to distinguish programmatically, and provide no schema-level contract for what can go wrong. **Therefore**, production-grade GraphQL APIs should adopt **union-based result types** (the "Result pattern") that make errors first-class citizens in the schema, enabling type-safe error handling on the client.

### The Problem with Top-Level Errors

By default, GraphQL returns errors like this:

```json
{
  "data": { "createUser": null },
  "errors": [
    {
      "message": "Email already exists",
      "locations": [{ "line": 2, "column": 3 }],
      "path": ["createUser"],
      "extensions": { "code": "DUPLICATE_EMAIL" }
    }
  ]
}
```

The **pitfall** is that `message` is a free-form string, `extensions.code` is not enforced by the schema, and the client has no way to know — from the schema alone — what error codes a particular mutation might return. **However**, union types solve this by encoding errors directly in the schema.

### The Result Pattern with Union Types

```python
# schema.py — Union-based error handling with Strawberry

import strawberry
from typing import Annotated, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

# Base error interface — all domain errors implement this
@strawberry.interface
class UserError:
    message: str
    code: str
    # Best practice: include a machine-readable path to the field
    # that caused the error, enabling client-side form validation
    field: str | None = None

# Specific error types — each is part of the schema contract
@strawberry.type
class ValidationError(UserError):
    message: str
    code: str = "VALIDATION_ERROR"
    field: str | None = None
    constraint: str | None = None  # e.g., "min_length:3"

@strawberry.type
class DuplicateError(UserError):
    message: str
    code: str = "DUPLICATE"
    field: str | None = None
    existing_id: str | None = None  # helps client navigate to existing

@strawberry.type
class NotFoundError(UserError):
    message: str
    code: str = "NOT_FOUND"
    field: str | None = None
    resource_type: str = ""
    resource_id: str = ""

@strawberry.type
class ForbiddenError(UserError):
    message: str
    code: str = "FORBIDDEN"
    field: str | None = None
    required_permission: str | None = None

# Success types carry the actual data
@strawberry.type
class User:
    id: str
    email: str
    display_name: str
    created_at: datetime

@strawberry.type
class CreateUserSuccess:
    user: User

# The Result union — client MUST handle all variants
CreateUserResult = Annotated[
    Union[CreateUserSuccess, ValidationError, DuplicateError, ForbiddenError],
    strawberry.union("CreateUserResult"),
]

@strawberry.type
class UpdateUserSuccess:
    user: User

UpdateUserResult = Annotated[
    Union[UpdateUserSuccess, ValidationError, NotFoundError, ForbiddenError],
    strawberry.union("UpdateUserResult"),
]
```

### Implementing Resolvers with the Result Pattern

```python
# resolvers.py — Mutation resolvers returning typed results

import re
from typing import Optional

@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_user(
        self,
        email: str,
        display_name: str,
        password: str,
    ) -> CreateUserResult:  # Return type is the union
        # Validation — return specific error types
        errors = validate_create_user(email, display_name, password)
        if errors:
            return errors[0]  # Return first validation error

        # Check for duplicates
        existing = await user_repo.find_by_email(email)
        if existing:
            return DuplicateError(
                message=f"A user with email '{email}' already exists",
                field="email",
                existing_id=existing.id,
            )

        # Authorization check
        if not current_user_can_create_users():
            return ForbiddenError(
                message="You do not have permission to create users",
                required_permission="users:create",
            )

        # Happy path — create and return success
        user = await user_repo.create(
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
        )
        return CreateUserSuccess(user=user)


def validate_create_user(
    email: str, display_name: str, password: str
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        errors.append(ValidationError(
            message="Invalid email format",
            field="email",
            constraint="email_format",
        ))
    if len(display_name) < 2:
        errors.append(ValidationError(
            message="Display name must be at least 2 characters",
            field="displayName",
            constraint="min_length:2",
        ))
    if len(password) < 8:
        errors.append(ValidationError(
            message="Password must be at least 8 characters",
            field="password",
            constraint="min_length:8",
        ))
    return errors

# Placeholder implementations for demonstration
class UserRepo:
    async def find_by_email(self, email: str) -> Optional[User]:
        return None
    async def create(self, **kwargs) -> User:
        return User(id="u-new", email=kwargs["email"],
                    display_name=kwargs["display_name"],
                    created_at=datetime.utcnow())

user_repo = UserRepo()

def current_user_can_create_users() -> bool:
    return True

def hash_password(pw: str) -> str:
    return f"hashed:{pw}"
```

### Client-Side Handling with Typed Fragments

The power of union-based errors becomes clear on the client side. Using `__typename` discrimination, the client can exhaustively handle all cases:

```python
# client_handler.py — Demonstrating typed client-side error handling

from dataclasses import dataclass
from typing import Protocol

# The GraphQL query using inline fragments on the union
CREATE_USER_MUTATION = '''
mutation CreateUser($email: String!, $displayName: String!, $password: String!) {
    createUser(email: $email, displayName: $displayName, password: $password) {
        __typename
        ... on CreateUserSuccess {
            user {
                id
                email
                displayName
            }
        }
        ... on ValidationError {
            message
            field
            constraint
        }
        ... on DuplicateError {
            message
            field
            existingId
        }
        ... on ForbiddenError {
            message
            requiredPermission
        }
    }
}
'''

class ErrorHandler(Protocol):
    def on_validation_error(self, message: str, field: str | None) -> None: ...
    def on_duplicate_error(self, message: str, existing_id: str | None) -> None: ...
    def on_forbidden_error(self, message: str) -> None: ...

def handle_create_user_result(
    result: dict,
    handler: ErrorHandler,
) -> str | None:
    # Returns user ID on success, None on handled error
    data = result.get("data", {}).get("createUser", {})
    typename = data.get("__typename")

    if typename == "CreateUserSuccess":
        return data["user"]["id"]
    elif typename == "ValidationError":
        handler.on_validation_error(data["message"], data.get("field"))
        return None
    elif typename == "DuplicateError":
        handler.on_duplicate_error(data["message"], data.get("existingId"))
        return None
    elif typename == "ForbiddenError":
        handler.on_forbidden_error(data["message"])
        return None
    else:
        raise ValueError(f"Unexpected result type: {typename}")
```

### Error Classification: Domain vs Infrastructure

A critical distinction is between **domain errors** (invalid input, duplicate, not found) and **infrastructure errors** (database down, timeout, internal bug). Domain errors belong in the union result type **because** they are expected, recoverable, and part of the API contract. Infrastructure errors should remain in the top-level `errors` array **because** they are unexpected, typically not recoverable by the client, and should not pollute the schema.

**Best practice**: use `extensions.code` in top-level errors for infrastructure error classification (e.g., `INTERNAL_SERVER_ERROR`, `RATE_LIMITED`, `SERVICE_UNAVAILABLE`), and use union types for domain error classification.

### Partial Errors in Queries

For queries that fetch lists, partial errors are a **trade-off**. You can return `null` for failed items with errors in the top-level array, or use a result wrapper per item. **However**, the result-per-item approach is more explicit and avoids the ambiguity of `null` (does null mean "not found" or "error fetching"?).

### Trade-offs: Union Errors vs Top-Level Errors

Using union types for every operation adds schema complexity. **Common mistake**: applying the result pattern to simple queries where a `null` return with a top-level error is perfectly adequate. Reserve union-based results for **mutations** and **queries with complex failure modes**. Simple queries (e.g., `user(id: ID!): User`) can return `null` with a top-level `NOT_FOUND` error without losing clarity.

## Summary / Key Takeaways

- **Top-level errors** are untyped and not part of the schema contract — they work for infrastructure errors but fail for domain-specific error handling.
- The **Result pattern** using union types (`CreateUserResult = Success | ValidationError | DuplicateError`) makes errors first-class schema citizens, enabling exhaustive client-side handling.
- **Separate domain errors from infrastructure errors**: domain errors go in unions, infrastructure errors stay in the top-level `errors` array.
- **Best practice**: include `field` paths on validation errors so clients can display errors next to the correct form field.
- The **trade-off** is schema complexity — apply the result pattern to mutations and complex queries, not to every field in the schema.
- **Pitfall**: returning HTTP 200 with errors in the body confuses monitoring tools. Use `extensions.code` consistently so observability platforms can classify error rates accurately.
"""
    ),
    (
        "graphql/code-generation-type-safety",
        r"""How does GraphQL code generation work for achieving end-to-end type safety? Explain schema-first vs code-first approaches, generating typed operations and hooks from queries, fragment colocation patterns, and the trade-offs between different codegen strategies for TypeScript and Python GraphQL projects.""",
        r"""## GraphQL Code Generation: End-to-End Type Safety from Schema to Client

One of GraphQL's most powerful properties is that the **schema is a typed contract** — and with code generation, you can propagate those types all the way from the server's schema definition through to the client's query results, eliminating an entire class of runtime errors. **Because** the schema describes every type, field, argument, and relationship, codegen tools can automatically produce server-side resolvers, client-side query types, and even full SDK functions — making it practically impossible to reference a field that does not exist or pass an argument of the wrong type.

### Schema-First vs Code-First: The Foundational Choice

The first decision is whether the **SDL file** (Schema Definition Language) is the source of truth, or whether the schema is derived from code (decorators, classes, or functions).

**Schema-first** means you write `.graphql` files and generate code from them. This is the dominant approach in the JavaScript/TypeScript ecosystem (Apollo, GraphQL Yoga, Pothos via SDL export). The **trade-off** is that SDL files are easy to read and review in PRs, but keeping resolvers in sync with the schema requires tooling.

**Code-first** means you define types in your programming language and the schema is generated automatically. Libraries like **Strawberry** (Python), **TypeGraphQL** (TypeScript), and **Nexus** (TypeScript) take this approach. The **trade-off** is that you get compile-time safety on the server for free, but the SDL becomes a derived artifact that is harder to review independently.

```python
# schema_first_example.py — Schema-first with Ariadne (Python)

from ariadne import QueryType, MutationType, make_executable_schema
from ariadne.asgi import GraphQL
from typing import Any

# The SDL is the source of truth
TYPE_DEFS = '''
    type Query {
        user(id: ID!): User
        users(filter: UserFilter, pagination: PaginationInput): UserConnection!
    }

    type Mutation {
        createUser(input: CreateUserInput!): CreateUserResult!
    }

    type User {
        id: ID!
        email: String!
        displayName: String!
        posts(first: Int = 10): [Post!]!
    }

    type Post {
        id: ID!
        title: String!
        body: String!
        author: User!
    }

    input UserFilter {
        search: String
        role: UserRole
    }

    input PaginationInput {
        first: Int = 20
        after: String
    }

    input CreateUserInput {
        email: String!
        displayName: String!
    }

    type CreateUserResult {
        user: User
        errors: [UserError!]!
    }

    type UserError {
        message: String!
        field: String
    }

    type UserConnection {
        edges: [UserEdge!]!
        pageInfo: PageInfo!
        totalCount: Int!
    }

    type UserEdge {
        node: User!
        cursor: String!
    }

    type PageInfo {
        hasNextPage: Boolean!
        endCursor: String
    }

    enum UserRole {
        ADMIN
        USER
        MODERATOR
    }
'''

# Resolvers must match the schema exactly — pitfall: typos are silent errors
# Best practice: use codegen to generate resolver type stubs
query = QueryType()
mutation = MutationType()

@query.field("user")
async def resolve_user(_, info, id: str) -> dict[str, Any] | None:
    return await info.context["user_repo"].find(id)

@query.field("users")
async def resolve_users(_, info, filter=None, pagination=None) -> dict:
    repo = info.context["user_repo"]
    first = (pagination or {}).get("first", 20)
    after = (pagination or {}).get("after")
    return await repo.paginated_list(filter=filter, first=first, after=after)

schema = make_executable_schema(TYPE_DEFS, query, mutation)
```

Now compare the **code-first** approach:

```python
# code_first_example.py — Code-first with Strawberry (Python)
# The schema is derived from Python types — therefore, type mismatches
# are caught by mypy/pyright at development time, not at runtime

import strawberry
from typing import Optional
from datetime import datetime
from enum import Enum

@strawberry.enum
class UserRole(Enum):
    ADMIN = "ADMIN"
    USER = "USER"
    MODERATOR = "MODERATOR"

@strawberry.input
class UserFilter:
    search: Optional[str] = None
    role: Optional[UserRole] = None

@strawberry.input
class PaginationInput:
    first: int = 20
    after: Optional[str] = None

@strawberry.input
class CreateUserInput:
    email: str
    display_name: str

@strawberry.type
class UserError:
    message: str
    field: Optional[str] = None

@strawberry.type
class User:
    id: strawberry.ID
    email: str
    display_name: str
    role: UserRole

    @strawberry.field
    async def posts(self, first: int = 10) -> list["Post"]:
        # Resolver is a method on the type — type-safe by construction
        return await post_repo.find_by_author(self.id, limit=first)

@strawberry.type
class Post:
    id: strawberry.ID
    title: str
    body: str
    author: User

@strawberry.type
class PageInfo:
    has_next_page: bool
    end_cursor: Optional[str] = None

@strawberry.type
class UserEdge:
    node: User
    cursor: str

@strawberry.type
class UserConnection:
    edges: list[UserEdge]
    page_info: PageInfo
    total_count: int

@strawberry.type
class CreateUserResult:
    user: Optional[User] = None
    errors: list[UserError] = strawberry.field(default_factory=list)

@strawberry.type
class Query:
    @strawberry.field
    async def user(self, id: strawberry.ID) -> Optional[User]:
        return await user_repo.find(str(id))

    @strawberry.field
    async def users(
        self,
        filter: Optional[UserFilter] = None,
        pagination: Optional[PaginationInput] = None,
    ) -> UserConnection:
        p = pagination or PaginationInput()
        return await user_repo.paginated_list(filter=filter, first=p.first, after=p.after)

@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_user(self, input: CreateUserInput) -> CreateUserResult:
        # Validation, creation, etc.
        if not input.email or "@" not in input.email:
            return CreateUserResult(errors=[UserError(message="Invalid email", field="email")])
        user = await user_repo.create(email=input.email, display_name=input.display_name)
        return CreateUserResult(user=user)

schema = strawberry.Schema(query=Query, mutation=Mutation)
# schema.as_str() produces the SDL — derived from code, not handwritten

# Placeholder
class PostRepo:
    async def find_by_author(self, author_id, limit=10):
        return []

class UserRepo:
    async def find(self, id):
        return None
    async def paginated_list(self, **kwargs):
        return UserConnection(edges=[], page_info=PageInfo(has_next_page=False), total_count=0)
    async def create(self, **kwargs):
        return User(id=strawberry.ID("u-new"), email=kwargs["email"],
                    display_name=kwargs["display_name"], role=UserRole.USER)

post_repo = PostRepo()
user_repo = UserRepo()
```

### Client-Side Code Generation

On the client, tools like **GraphQL Code Generator** (for TypeScript) and **ariadne-codegen** (for Python) read your `.graphql` operation files and produce fully typed functions, hooks, or classes.

```python
# codegen_config.py — Configuration for ariadne-codegen (Python client)
# Generates typed client from .graphql operation files

# ariadne-codegen config (pyproject.toml section):
# [tool.ariadne-codegen]
# schema_path = "schema.graphql"
# queries_path = "operations/"
# target_package_name = "graphql_client"
# async_client = true

# Example operation file: operations/get_user.graphql
# query GetUser($id: ID!) {
#     user(id: $id) {
#         ...UserFields
#     }
# }
#
# fragment UserFields on User {
#     id
#     email
#     displayName
#     posts(first: 5) {
#         ...PostSummary
#     }
# }
#
# fragment PostSummary on Post {
#     id
#     title
# }

# The codegen produces typed classes like:
from dataclasses import dataclass
from typing import Optional

@dataclass
class PostSummary:
    id: str
    title: str

@dataclass
class UserFields:
    id: str
    email: str
    display_name: str
    posts: list[PostSummary]

@dataclass
class GetUserResponse:
    user: Optional[UserFields]

# And a typed client method:
class GraphQLClient:
    async def get_user(self, id: str) -> GetUserResponse:
        # Auto-generated — sends the query and deserializes into typed dataclass
        # Common mistake: manually writing these types instead of generating them
        ...
```

### Fragment Colocation

**Best practice**: colocate GraphQL fragments with the components that use them. Each component declares the data it needs via a fragment, and parent components compose these fragments into full queries. This ensures that adding a field to a component's fragment automatically propagates to the query, and codegen regenerates the types.

**However**, the **trade-off** with fragment colocation is that deeply nested component trees can produce very large queries with many fragments. **Therefore**, monitor query complexity and consider fragment deduplication in your codegen pipeline.

### Trade-offs Between Codegen Strategies

| Strategy | Pros | Cons |
|----------|------|------|
| Schema-first + codegen | Clean SDL, easy PR review, language-agnostic | Must keep resolvers in sync manually |
| Code-first | Compile-time server safety, single source of truth | SDL is derived, harder to review schema changes |
| Client codegen | Eliminates runtime type errors, autocompletion | Build step required, stale types if not regenerated |
| No codegen | Simpler build, no tooling setup | Runtime errors, no type safety, slower development |

**Best practice**: regardless of server approach, always use client-side codegen. The cost (a build step) is trivial compared to the benefit (zero runtime type errors in data access code). Generate types in CI and fail the build if the schema and operations diverge.

## Summary / Key Takeaways

- **Schema-first** vs **code-first** is a fundamental architectural choice: schema-first provides a clean, reviewable contract while code-first gives compile-time server safety — the **trade-off** depends on team preferences and language ecosystem.
- **Client-side codegen** (GraphQL Code Generator, ariadne-codegen) eliminates an entire class of runtime errors by producing typed query results, and should be considered a **best practice** for any production GraphQL project.
- **Fragment colocation** ensures components declare their own data requirements, making refactoring safe and preventing over- or under-fetching.
- **Common mistake**: skipping codegen on the client "to avoid complexity" and then spending hours debugging misspelled field names and wrong variable types at runtime.
- **Pitfall**: not regenerating types after schema changes — always run codegen in CI and fail the build on mismatches.
- The combination of a **typed schema**, **typed resolvers** (code-first or generated stubs), and **typed client operations** (codegen) creates an end-to-end type-safe data pipeline where errors are caught at build time rather than in production.
"""
    ),
]
