PAIRS = [
    (
        "api-design/rest-best-practices-versioning",
        r"""Explain REST API best practices including resource naming conventions, HTTP method semantics, status code usage, pagination strategies, and API versioning approaches with their trade-offs for production systems.""",
        r"""## REST API Design: Best Practices, Versioning, and Production Patterns

Designing a **REST API** that stands the test of time requires deliberate choices about resource naming, HTTP semantics, pagination, error handling, and versioning. A **common mistake** is treating REST as simply "HTTP endpoints that return JSON" — however, the constraints REST imposes (statelessness, uniform interface, resource orientation) exist **because** they enable scalability, cacheability, and independent evolution of client and server.

### Resource Naming and URL Structure

**Best practice**: use plural nouns for collections, nest resources to express ownership, and keep URLs shallow (max 2-3 levels deep).

```python
from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime

app = FastAPI(title="Resource Design Patterns")

# Good: plural nouns, consistent hierarchy
# GET    /api/v2/organizations/{org_id}/projects
# POST   /api/v2/organizations/{org_id}/projects
# GET    /api/v2/projects/{project_id}           # shortcut for known IDs
# PATCH  /api/v2/projects/{project_id}
# DELETE /api/v2/projects/{project_id}

# Pitfall: verb-based URLs like /api/getUsers or /api/createProject
# Pitfall: deeply nested /orgs/{id}/teams/{id}/projects/{id}/tasks/{id}/comments

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    # HATEOAS links for discoverability
    links: dict[str, str]

class PaginatedResponse(BaseModel):
    data: list[ProjectResponse]
    pagination: dict  # cursor info
    links: dict[str, Optional[str]]  # prev, next, first, last

# Proper HTTP method semantics
@app.post("/api/v2/organizations/{org_id}/projects",
          status_code=201,
          response_model=ProjectResponse)
async def create_project(
    org_id: str = Path(..., description="Organization identifier"),
    body: ProjectCreate = ...,
):
    # 201 Created with Location header — best practice
    # Returns the created resource in the body
    project_id = "proj_" + generate_id()
    return ProjectResponse(
        id=project_id,
        name=body.name,
        description=body.description,
        status=ProjectStatus.DRAFT,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        links={
            "self": f"/api/v2/projects/{project_id}",
            "organization": f"/api/v2/organizations/{org_id}",
            "tasks": f"/api/v2/projects/{project_id}/tasks",
        }
    )
```

### HTTP Status Codes: Semantic Precision

**Therefore**, choosing the right status code communicates intent without clients needing to parse error bodies:

- **200 OK** — successful GET, PUT, PATCH
- **201 Created** — successful POST that creates a resource
- **204 No Content** — successful DELETE or PUT with no body
- **400 Bad Request** — validation failure, malformed input
- **401 Unauthorized** — missing or invalid authentication
- **403 Forbidden** — authenticated but insufficient permissions
- **404 Not Found** — resource doesn't exist
- **409 Conflict** — duplicate creation, version conflict
- **422 Unprocessable Entity** — semantically invalid (valid JSON but wrong business logic)
- **429 Too Many Requests** — rate limited, include Retry-After header

### Pagination: Cursor vs Offset

The **trade-off** between offset-based and cursor-based pagination is critical for large datasets:

```python
from typing import Optional
from base64 import b64encode, b64decode
import json

class CursorPaginator:
    # Cursor-based pagination — best practice for large/dynamic datasets
    # because offset pagination breaks when items are inserted/deleted
    # between page fetches (items get skipped or duplicated)

    def __init__(self, default_limit: int = 20, max_limit: int = 100):
        self.default_limit = default_limit
        self.max_limit = max_limit

    def encode_cursor(self, sort_key: str, sort_value, item_id: str) -> str:
        # Encode cursor as opaque base64 token
        # Clients should never parse cursors — they are an implementation detail
        payload = json.dumps({
            "k": sort_key,
            "v": str(sort_value),
            "id": item_id,
        })
        return b64encode(payload.encode()).decode()

    def decode_cursor(self, cursor: str) -> dict:
        try:
            payload = b64decode(cursor.encode()).decode()
            return json.loads(payload)
        except Exception:
            raise ValueError("Invalid cursor")

    def build_query(self, cursor: Optional[str], sort_key: str = "created_at"):
        # Keyset pagination: WHERE (created_at, id) > (cursor_val, cursor_id)
        # This is O(1) seek regardless of page depth
        # however offset pagination degrades to O(n) for deep pages
        if cursor is None:
            return {"sort": sort_key, "direction": "desc", "filter": None}

        decoded = self.decode_cursor(cursor)
        return {
            "sort": sort_key,
            "direction": "desc",
            "filter": {
                "field": decoded["k"],
                "value": decoded["v"],
                "tie_breaker_id": decoded["id"],
            }
        }

    def build_response(self, items: list, limit: int, base_url: str) -> dict:
        has_more = len(items) > limit
        page_items = items[:limit]

        next_cursor = None
        if has_more and page_items:
            last = page_items[-1]
            next_cursor = self.encode_cursor("created_at", last["created_at"], last["id"])

        return {
            "data": page_items,
            "pagination": {
                "has_more": has_more,
                "next_cursor": next_cursor,
                "limit": limit,
            },
            "links": {
                "next": f"{base_url}?cursor={next_cursor}&limit={limit}" if next_cursor else None,
            }
        }

# Offset pagination — simpler but with pitfalls
# GET /api/v2/projects?offset=40&limit=20
# Common mistake: allowing unbounded offset values that cause full table scans
# Trade-off: offset is simpler for UIs with page numbers, cursor is better for infinite scroll
```

### API Versioning Strategies

```python
from fastapi import FastAPI, Request, Header
from typing import Optional

# Strategy 1: URL path versioning (most common, explicit)
# GET /api/v1/users  → old format
# GET /api/v2/users  → new format with breaking changes
# Best practice because: obvious, cacheable, easy to route

app_v1 = FastAPI(prefix="/api/v1")
app_v2 = FastAPI(prefix="/api/v2")

# Strategy 2: Header-based versioning
# GET /api/users  with Accept: application/vnd.myapi.v2+json
# Trade-off: cleaner URLs but harder to test in browser, harder to cache

async def get_api_version(
    accept: Optional[str] = Header(None),
    x_api_version: Optional[str] = Header(None, alias="X-API-Version"),
) -> int:
    # Check custom header first, then Accept header
    if x_api_version:
        return int(x_api_version)
    if accept and "vnd.myapi.v" in accept:
        # Parse version from Accept: application/vnd.myapi.v2+json
        import re
        match = re.search(r"vnd\.myapi\.v(\d+)", accept)
        if match:
            return int(match.group(1))
    return 2  # Default to latest

# Strategy 3: Query parameter versioning
# GET /api/users?version=2
# Pitfall: easy to forget, pollutes query string

# Strategy 4: Additive changes only (best for longevity)
# Never remove fields, only add new ones
# Use feature flags instead of versions
class UserResponseV1(BaseModel):
    id: str
    name: str
    email: str

class UserResponseV2(UserResponseV1):
    # V2 adds fields but doesn't remove any
    avatar_url: Optional[str] = None
    preferences: dict = {}
    # Deprecated fields marked explicitly
    class Config:
        json_schema_extra = {
            "deprecated_fields": ["name"],  # Split into first_name + last_name
            "sunset_date": "2026-06-01",
        }

# Sunset headers for deprecation communication
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class DeprecationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.url.path.startswith("/api/v1"):
            response.headers["Sunset"] = "Sat, 01 Jun 2026 00:00:00 GMT"
            response.headers["Deprecation"] = "true"
            response.headers["Link"] = '</api/v2>; rel="successor-version"'
        return response
```

### Error Response Design

A **best practice** is standardizing error responses across all endpoints so clients can handle errors uniformly:

```python
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: str
    code: str

class ErrorResponse(BaseModel):
    error: str  # machine-readable error type
    message: str  # human-readable description
    status: int
    details: list[ErrorDetail] = []
    request_id: str
    docs_url: Optional[str] = None

# Consistent error handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ERROR_CODE_MAP.get(exc.status_code, "unknown_error"),
            message=str(exc.detail),
            status=exc.status_code,
            request_id=request.state.request_id,
            docs_url=f"https://docs.api.example.com/errors/{exc.status_code}",
        ).model_dump(),
    )

ERROR_CODE_MAP = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
}
```

### Key Takeaways

- **Resource naming** should use plural nouns and shallow nesting — **because** deep hierarchies couple URL structure to data model
- **Cursor pagination** is superior for dynamic datasets — **however** offset pagination is simpler when total count and page numbers are needed
- **URL path versioning** is the most practical — the **trade-off** is URL proliferation vs. the clarity it provides
- A **common mistake** is inconsistent error formats — standardize with a single ErrorResponse schema
- **Best practice**: always include deprecation headers (Sunset, Link) when sunsetting API versions
- **Pitfall**: designing RPC-style endpoints (POST /doAction) instead of resource-oriented ones — REST's power comes from its uniform interface constraint
"""
    ),
    (
        "api-design/graphql-deep-dive",
        r"""Explain GraphQL API design including schema-first development, resolver patterns, N+1 problem solutions with DataLoader, pagination with connections, authorization strategies, and performance optimization techniques.""",
        r"""## GraphQL API Design: Schema-First Development, DataLoaders, and Production Patterns

**GraphQL** fundamentally changes the API contract by giving clients the power to request exactly the data they need. **However**, this flexibility introduces challenges around performance, authorization, and complexity that require careful architectural decisions. The **trade-off** is clear: GraphQL eliminates over/under-fetching but demands more server-side sophistication.

### Schema-First Design

**Best practice**: define your schema before writing resolvers. The schema is the API contract and should be designed for client needs, not database structure.

```python
import strawberry
from strawberry.types import Info
from typing import Optional
from datetime import datetime
from enum import Enum

# Schema-first: define types that match client needs
# Common mistake: mirroring database tables 1:1 in your GraphQL schema

@strawberry.enum
class ProjectStatus(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"

@strawberry.type
class User:
    id: strawberry.ID
    username: str
    display_name: str
    avatar_url: Optional[str]

    @strawberry.field
    async def projects(
        self,
        info: Info,
        status: Optional[ProjectStatus] = None,
        first: int = 10,
        after: Optional[str] = None,
    ) -> "ProjectConnection":
        # Lazy-loaded relationship with pagination
        # This is where DataLoader becomes critical
        loader = info.context["project_loader"]
        return await loader.load_for_user(self.id, status, first, after)

    @strawberry.field
    async def total_projects(self, info: Info) -> int:
        loader = info.context["count_loader"]
        return await loader.load(self.id)

@strawberry.type
class Project:
    id: strawberry.ID
    name: str
    description: Optional[str]
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    @strawberry.field
    async def owner(self, info: Info) -> User:
        # DataLoader prevents N+1 when listing projects
        loader = info.context["user_loader"]
        return await loader.load(self.owner_id)

    @strawberry.field
    async def collaborators(self, info: Info) -> list[User]:
        loader = info.context["collaborators_loader"]
        return await loader.load(self.id)

# Relay-style connection for cursor pagination
@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str]
    end_cursor: Optional[str]

@strawberry.type
class ProjectEdge:
    cursor: str
    node: Project

@strawberry.type
class ProjectConnection:
    edges: list[ProjectEdge]
    page_info: PageInfo
    total_count: int
```

### The N+1 Problem and DataLoader

The **N+1 problem** is the most critical **pitfall** in GraphQL. When you query a list of projects and each project resolves its owner, a naive implementation makes 1 query for projects + N queries for owners. **Therefore**, DataLoader is essential.

```python
from strawberry.dataloader import DataLoader
from typing import Sequence
from collections import defaultdict

class UserBatchLoader:
    # DataLoader batches individual load(id) calls into a single batch query
    # This transforms N+1 queries into exactly 2 queries
    # because DataLoader collects all IDs requested in a single event loop tick

    def __init__(self, db_session):
        self.db = db_session
        self.loader = DataLoader(load_fn=self.batch_load)

    async def batch_load(self, user_ids: list[str]) -> list[User]:
        # Single query for all requested users
        # CRITICAL: return results in the SAME ORDER as input keys
        # Common mistake: returning results in arbitrary order breaks DataLoader

        rows = await self.db.fetch_all(
            ("SELECT id, username, display_name, avatar_url "
             "FROM users WHERE id = ANY($1)"),
            [user_ids]
        )

        # Build lookup map for O(1) access
        user_map = {row["id"]: row for row in rows}

        # Must return in exact order of input, with None for missing
        return [
            User(**user_map[uid]) if uid in user_map else None
            for uid in user_ids
        ]

    async def load(self, user_id: str) -> Optional[User]:
        return await self.loader.load(user_id)

class ProjectBatchLoader:
    # More complex loader: batching by parent ID with filtering
    def __init__(self, db_session):
        self.db = db_session

    async def load_for_user(
        self,
        user_id: str,
        status: Optional[ProjectStatus],
        first: int,
        after: Optional[str],
    ) -> ProjectConnection:
        # Build cursor-based query
        params = [user_id, first + 1]  # fetch one extra for has_next_page
        conditions = ["owner_id = $1"]

        if status:
            conditions.append(f"status = ${len(params) + 1}")
            params.append(status.value)

        if after:
            cursor_data = decode_cursor(after)
            conditions.append(
                f"(created_at, id) < (${len(params)+1}, ${len(params)+2})"
            )
            params.extend([cursor_data["created_at"], cursor_data["id"]])

        where_clause = " AND ".join(conditions)
        query = (
            "SELECT * FROM projects "
            f"WHERE {where_clause} "
            "ORDER BY created_at DESC, id DESC "
            f"LIMIT ${len(params)}"
        )
        # Pitfall: not parameterizing LIMIT — always parameterize all values

        rows = await self.db.fetch_all(query, params)
        has_next = len(rows) > first
        items = rows[:first]

        edges = [
            ProjectEdge(
                cursor=encode_cursor(row["created_at"], row["id"]),
                node=Project(**row),
            )
            for row in items
        ]

        return ProjectConnection(
            edges=edges,
            page_info=PageInfo(
                has_next_page=has_next,
                has_previous_page=after is not None,
                start_cursor=edges[0].cursor if edges else None,
                end_cursor=edges[-1].cursor if edges else None,
            ),
            total_count=await self._count(user_id, status),
        )
```

### Authorization in GraphQL

**Best practice**: implement authorization at the resolver/field level, not at the query entry point, **because** the same type can be reached through multiple query paths.

```python
import strawberry
from functools import wraps
from typing import Any
from strawberry.types import Info
from enum import Enum

class Permission(Enum):
    READ_PROJECT = "read:project"
    WRITE_PROJECT = "write:project"
    ADMIN = "admin"

def require_permission(*permissions: Permission):
    # Field-level authorization decorator
    # Trade-off: field-level auth is more granular but adds overhead per field
    # however, it prevents authorization bypass through different query paths
    def decorator(resolver):
        @wraps(resolver)
        async def wrapper(self, info: Info, **kwargs) -> Any:
            user = info.context.get("current_user")
            if not user:
                raise PermissionError("Authentication required")

            user_perms = set(user.get("permissions", []))
            required = set(p.value for p in permissions)

            if not required.issubset(user_perms):
                # Best practice: return None or filtered results
                # instead of throwing errors for list fields
                # because partial data is often better than total failure
                missing = required - user_perms
                raise PermissionError(f"Missing permissions: {missing}")

            return await resolver(self, info, **kwargs)
        return wrapper
    return decorator

# Query complexity analysis to prevent abuse
class ComplexityAnalyzer:
    # GraphQL's flexibility means clients can craft expensive queries
    # Common mistake: not limiting query depth or complexity
    # Pitfall: a query like { users { projects { tasks { comments { author { projects ... }}}}}}

    def __init__(self, max_depth: int = 10, max_complexity: int = 1000):
        self.max_depth = max_depth
        self.max_complexity = max_complexity

    def estimate_complexity(self, query_ast, variables: dict) -> int:
        # Each field = 1 point, list fields multiply by estimated count
        # Nested connections multiply: users(50) -> projects(20) = 1000
        return self._walk_selections(query_ast.definitions[0].selection_set, 0)

    def _walk_selections(self, selection_set, depth: int) -> int:
        if depth > self.max_depth:
            raise ValueError(f"Query depth {depth} exceeds max {self.max_depth}")

        cost = 0
        if selection_set is None:
            return 1

        for field in selection_set.selections:
            field_cost = 1
            # Connection fields have a multiplier
            multiplier = self._get_multiplier(field)
            if field.selection_set:
                child_cost = self._walk_selections(field.selection_set, depth + 1)
                field_cost = multiplier * child_cost
            cost += field_cost

        return cost

    def _get_multiplier(self, field) -> int:
        # Check for first/last pagination args
        for arg in (field.arguments or []):
            if arg.name.value in ("first", "last"):
                return int(arg.value.value)
        # Default list multiplier
        return 10
```

### Key Takeaways

- **Schema-first development** decouples API design from implementation — design for client needs, not database structure
- The **N+1 problem** is GraphQL's biggest **pitfall** — **DataLoader** is non-negotiable in production because it batches individual loads into bulk queries
- **Cursor-based pagination** with Relay connections is the **best practice** — however, it's more complex than simple offset pagination
- **Field-level authorization** prevents security bypass through alternative query paths — a **common mistake** is only checking permissions at the query root
- **Query complexity analysis** is essential **because** GraphQL's flexibility lets clients craft arbitrarily expensive queries — **therefore** set depth limits and complexity budgets
- The **trade-off** with GraphQL is between client flexibility and server complexity — for simple CRUD APIs, REST may actually be more appropriate
"""
    ),
    (
        "api-design/message-queue-patterns",
        r"""Explain message queue architecture patterns including publish-subscribe with topic routing, competing consumers, dead letter queues, exactly-once delivery semantics, and implementation patterns using RabbitMQ and Redis Streams.""",
        r"""## Message Queue Architecture: Pub/Sub, Competing Consumers, and Delivery Guarantees

**Message queues** decouple producers from consumers, enabling asynchronous processing, load leveling, and system resilience. **However**, the apparent simplicity of "put message on queue, consumer picks it up" hides significant complexity around delivery guarantees, ordering, and failure handling. Understanding these patterns is critical **because** incorrect message handling leads to data loss, duplicate processing, or infinite retry loops.

### Publish-Subscribe with Topic Routing

The **pub/sub pattern** allows messages to fan out to multiple consumers, each receiving a copy. The **trade-off** is between simple fanout (every subscriber gets everything) and topic-based routing (subscribers filter by interest).

```python
import aio_pika
import json
from dataclasses import dataclass, asdict
from typing import Callable, Awaitable
from datetime import datetime

@dataclass
class Event:
    event_type: str
    payload: dict
    timestamp: str
    correlation_id: str
    source: str

class TopicPublisher:
    # Topic exchange routes messages based on routing key patterns
    # Routing key: "order.created.us-east" matches "order.created.*" and "order.#"
    # Best practice: use dot-separated hierarchical routing keys

    def __init__(self, connection_url: str, exchange_name: str = "events"):
        self.connection_url = connection_url
        self.exchange_name = exchange_name
        self._connection = None
        self._channel = None
        self._exchange = None

    async def connect(self):
        self._connection = await aio_pika.connect_robust(self.connection_url)
        self._channel = await self._connection.channel()
        # Durable exchange survives broker restarts
        self._exchange = await self._channel.declare_exchange(
            self.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

    async def publish(self, event: Event, routing_key: str):
        # Persistent messages survive broker restarts
        # Common mistake: using transient delivery mode for important messages
        message = aio_pika.Message(
            body=json.dumps(asdict(event)).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
            message_id=event.correlation_id,
            timestamp=datetime.utcnow(),
            headers={
                "x-event-type": event.event_type,
                "x-source": event.source,
            },
        )
        await self._exchange.publish(message, routing_key=routing_key)

class TopicSubscriber:
    # Each subscriber declares its own queue bound to routing key patterns
    # Multiple patterns can be bound to one queue

    def __init__(self, connection_url: str, exchange_name: str = "events"):
        self.connection_url = connection_url
        self.exchange_name = exchange_name
        self.handlers: dict[str, Callable] = {}

    async def subscribe(
        self,
        queue_name: str,
        routing_patterns: list[str],
        handler: Callable[[Event], Awaitable[None]],
        prefetch_count: int = 10,
    ):
        connection = await aio_pika.connect_robust(self.connection_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=prefetch_count)

        exchange = await channel.declare_exchange(
            self.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        # Durable queue with dead letter exchange for failed messages
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": f"{self.exchange_name}.dlx",
                "x-dead-letter-routing-key": f"dead.{queue_name}",
                "x-message-ttl": 86400000,  # 24h TTL
            },
        )

        # Bind queue to each routing pattern
        for pattern in routing_patterns:
            await queue.bind(exchange, routing_key=pattern)

        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process(requeue=False):
                # requeue=False sends to DLX on failure instead of requeuing
                # Pitfall: requeue=True causes infinite retry loops
                event_data = json.loads(message.body)
                event = Event(**event_data)
                await handler(event)

        await queue.consume(process_message)
```

### Competing Consumers Pattern

When multiple consumer instances share a queue, the broker distributes messages across them. This enables horizontal scaling of processing. **However**, ordering guarantees are lost with competing consumers.

```python
import asyncio
from typing import Optional
import redis.asyncio as redis

class RedisStreamConsumerGroup:
    # Redis Streams provide a log-based message queue with consumer groups
    # Each message is delivered to exactly one consumer in the group
    # Unacknowledged messages can be claimed by other consumers (failover)

    def __init__(self, redis_url: str, stream: str, group: str, consumer: str):
        self.redis_url = redis_url
        self.stream = stream
        self.group = group
        self.consumer = consumer
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        self._redis = redis.from_url(self.redis_url)
        # Create consumer group if not exists
        # Best practice: start from '0' to process all existing messages
        # or '$' to only process new messages
        try:
            await self._redis.xgroup_create(
                self.stream, self.group, id="0", mkstream=True
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise  # Group already exists is OK

    async def produce(self, data: dict, max_len: int = 100000) -> str:
        # MAXLEN with ~ (approximate) for efficient trimming
        # Trade-off: exact MAXLEN is slower because it scans the entire stream
        msg_id = await self._redis.xadd(
            self.stream, data, maxlen=max_len, approximate=True
        )
        return msg_id

    async def consume(
        self,
        handler,
        batch_size: int = 10,
        block_ms: int = 5000,
    ):
        # '>' means read only new messages not yet delivered to this group
        # Therefore, each message is delivered to exactly one consumer
        while True:
            try:
                messages = await self._redis.xreadgroup(
                    groupname=self.group,
                    consumername=self.consumer,
                    streams={self.stream: ">"},
                    count=batch_size,
                    block=block_ms,
                )

                if not messages:
                    continue

                for stream_name, stream_messages in messages:
                    for msg_id, data in stream_messages:
                        try:
                            await handler(msg_id, data)
                            # Acknowledge after successful processing
                            await self._redis.xack(self.stream, self.group, msg_id)
                        except Exception as e:
                            # Don't ack — message stays in pending list
                            # Another consumer can claim it later
                            print(f"Failed to process {msg_id}: {e}")

            except Exception as e:
                print(f"Consumer error: {e}")
                await asyncio.sleep(1)

    async def claim_stale_messages(self, min_idle_ms: int = 60000, count: int = 10):
        # Claim messages that have been pending too long
        # This handles consumer crashes — best practice for reliability
        # because without claiming, messages from dead consumers are never processed

        claimed = await self._redis.xautoclaim(
            self.stream, self.group, self.consumer,
            min_idle_time=min_idle_ms, start_id="0-0", count=count,
        )
        return claimed
```

### Dead Letter Queues and Retry Strategies

A **dead letter queue** (DLQ) captures messages that cannot be processed after exhausting retries. **Therefore**, every production queue should have a DLQ configured.

```python
import json
import time
from dataclasses import dataclass
from typing import Optional, Callable

@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0
    exponential_base: float = 2.0
    # Jitter prevents thundering herd when many messages retry simultaneously
    jitter: bool = True

class RetryableConsumer:
    # Implements exponential backoff retry with dead letter handling
    # Common mistake: immediate retries without backoff overwhelm downstream systems

    def __init__(self, policy: RetryPolicy):
        self.policy = policy

    def calculate_delay(self, attempt: int) -> float:
        # Exponential backoff: 1s, 2s, 4s, 8s, ... capped at max_delay
        delay = self.policy.base_delay_seconds * (
            self.policy.exponential_base ** attempt
        )
        delay = min(delay, self.policy.max_delay_seconds)

        if self.policy.jitter:
            import random
            # Full jitter: uniform random between 0 and calculated delay
            # Best practice because it decorrelates retry storms
            delay = random.uniform(0, delay)

        return delay

    async def process_with_retry(
        self,
        message: dict,
        handler: Callable,
        publish_to_dlq: Callable,
        publish_delayed: Callable,
    ):
        attempt = message.get("_retry_count", 0)

        try:
            await handler(message)
        except Exception as e:
            if attempt >= self.policy.max_retries:
                # Exhausted retries — send to dead letter queue
                # Include failure context for debugging
                await publish_to_dlq({
                    **message,
                    "_dlq_reason": str(e),
                    "_dlq_timestamp": time.time(),
                    "_total_attempts": attempt + 1,
                    "_original_timestamp": message.get("timestamp"),
                })
                return

            # Schedule retry with backoff
            delay = self.calculate_delay(attempt)
            retry_message = {
                **message,
                "_retry_count": attempt + 1,
                "_next_retry_at": time.time() + delay,
            }
            await publish_delayed(retry_message, delay_seconds=delay)

    async def reprocess_dlq(
        self,
        dlq_consumer,
        main_publisher,
        filter_fn: Optional[Callable] = None,
    ):
        # Pitfall: blindly replaying all DLQ messages without fixing root cause
        # Best practice: filter and selectively replay
        async for message in dlq_consumer.drain():
            if filter_fn and not filter_fn(message):
                continue
            # Reset retry count for reprocessing
            clean_msg = {
                k: v for k, v in message.items()
                if not k.startswith("_dlq_") and k != "_retry_count"
            }
            await main_publisher.publish(clean_msg)
```

### Key Takeaways

- **Pub/sub with topic routing** enables flexible message fan-out — use hierarchical routing keys (e.g., `order.created.region`) **because** they support wildcard subscriptions
- **Competing consumers** scale horizontally but sacrifice ordering — **therefore** use partition keys when ordering matters (Redis Streams, Kafka partitions)
- **Dead letter queues** are non-negotiable in production — a **common mistake** is not configuring DLQs and losing failed messages
- **Exponential backoff with jitter** prevents retry storms — **however** each retry mechanism adds latency to the system
- **Best practice**: always acknowledge messages after processing, not before — **pitfall** is acknowledging before processing and losing messages on crash
- The **trade-off** between at-least-once and exactly-once delivery: at-least-once is simpler but requires idempotent consumers; exactly-once requires transactional outbox or similar patterns
"""
    ),
    (
        "api-design/vector-database-patterns",
        r"""Explain vector database architecture including embedding storage, approximate nearest neighbor search algorithms like HNSW and IVF, hybrid search combining dense vectors with sparse BM25, index tuning strategies, and production deployment patterns.""",
        r"""## Vector Database Architecture: Embeddings, ANN Search, and Hybrid Retrieval

**Vector databases** have become foundational infrastructure for AI applications, powering semantic search, RAG pipelines, recommendation systems, and anomaly detection. **However**, the apparent simplicity of "store vectors, find similar ones" masks significant engineering challenges around index construction, search quality, scaling, and the critical **trade-off** between recall accuracy and query latency.

### Embedding Storage and Index Fundamentals

The core operation is **approximate nearest neighbor (ANN) search**: given a query vector, find the k most similar vectors from billions of stored vectors. Exact search is O(n) per query, which is prohibitive at scale. **Therefore**, we use specialized index structures that trade perfect recall for dramatically faster search.

```python
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
import heapq

@dataclass
class VectorRecord:
    id: str
    vector: np.ndarray
    metadata: dict = field(default_factory=dict)
    sparse_vector: Optional[dict] = None  # For hybrid search

class HNSWIndex:
    # Hierarchical Navigable Small World graph
    # Best practice for most use cases: high recall, fast search
    # Trade-off: higher memory usage (stores graph edges) vs. IVF

    def __init__(
        self,
        dim: int,
        M: int = 16,           # max connections per node per layer
        ef_construction: int = 200,  # search width during construction
        max_layers: int = 6,
    ):
        self.dim = dim
        self.M = M
        self.ef_construction = ef_construction
        self.max_layers = max_layers
        self.vectors: dict[str, np.ndarray] = {}
        # Graph: layer -> node_id -> set of neighbor_ids
        self.graph: list[dict[str, set]] = [dict() for _ in range(max_layers)]
        self.entry_point: Optional[str] = None
        self.node_layer: dict[str, int] = {}  # max layer for each node

    def _distance(self, a: np.ndarray, b: np.ndarray) -> float:
        # Cosine distance = 1 - cosine_similarity
        # Common mistake: using L2 distance with unnormalized embeddings
        # because most embedding models produce normalized vectors
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 1.0
        return 1.0 - np.dot(a, b) / (norm_a * norm_b)

    def _select_layer(self) -> int:
        # Random layer assignment with exponential decay
        # Higher layers are sparser — this creates the hierarchical structure
        import random
        ml = 1.0 / np.log(self.M)
        layer = int(-np.log(random.uniform(0, 1)) * ml)
        return min(layer, self.max_layers - 1)

    def _search_layer(
        self,
        query: np.ndarray,
        entry_point: str,
        ef: int,
        layer: int,
    ) -> list[tuple[float, str]]:
        # Greedy search with beam width ef
        # Larger ef = better recall but slower search
        visited = {entry_point}
        candidates = []  # min-heap by distance
        results = []     # max-heap by negative distance (keep worst at top)

        dist = self._distance(query, self.vectors[entry_point])
        heapq.heappush(candidates, (dist, entry_point))
        heapq.heappush(results, (-dist, entry_point))

        while candidates:
            c_dist, c_id = heapq.heappop(candidates)
            # If closest candidate is farther than worst result, stop
            if c_dist > -results[0][0]:
                break

            for neighbor_id in self.graph[layer].get(c_id, set()):
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)

                n_dist = self._distance(query, self.vectors[neighbor_id])

                if len(results) < ef or n_dist < -results[0][0]:
                    heapq.heappush(candidates, (n_dist, neighbor_id))
                    heapq.heappush(results, (-n_dist, neighbor_id))
                    if len(results) > ef:
                        heapq.heappop(results)

        return [(-d, nid) for d, nid in sorted(results, reverse=True)]

    def search(self, query: np.ndarray, k: int = 10, ef: int = 50) -> list[tuple[float, str]]:
        # Start from top layer, greedily descend to layer 0
        # Pitfall: setting ef < k gives fewer results than requested
        if self.entry_point is None:
            return []

        ef = max(ef, k)  # ef must be >= k
        current = self.entry_point
        entry_layer = self.node_layer[current]

        # Traverse top layers with ef=1 (greedy)
        for layer in range(entry_layer, 0, -1):
            results = self._search_layer(query, current, ef=1, layer=layer)
            current = results[0][1]  # closest node

        # Search bottom layer with full ef
        results = self._search_layer(query, current, ef=ef, layer=0)
        return results[:k]
```

### IVF (Inverted File Index) for Large-Scale Search

When the dataset exceeds what HNSW can hold in memory, **IVF** partitions vectors into clusters using k-means. At query time, only the closest clusters are searched. The **trade-off** is lower memory usage but potentially lower recall.

```python
from sklearn.cluster import MiniBatchKMeans

class IVFIndex:
    # Inverted File Index: partition space into Voronoi cells
    # Best practice for billion-scale datasets with quantization (IVF-PQ)

    def __init__(self, dim: int, n_clusters: int = 1024, n_probe: int = 10):
        self.dim = dim
        self.n_clusters = n_clusters
        self.n_probe = n_probe  # how many clusters to search
        self.kmeans = MiniBatchKMeans(n_clusters=n_clusters, batch_size=10000)
        self.inverted_lists: dict[int, list[tuple[str, np.ndarray]]] = {}
        self.is_trained = False

    def train(self, vectors: np.ndarray):
        # Train centroids on a representative sample
        # Common mistake: training on a biased subset
        # Best practice: use at least 30 * n_clusters training vectors
        self.kmeans.fit(vectors)
        self.is_trained = True
        self.inverted_lists = {i: [] for i in range(self.n_clusters)}

    def add(self, id: str, vector: np.ndarray):
        if not self.is_trained:
            raise RuntimeError("Must train index before adding vectors")
        # Assign vector to nearest centroid
        cluster = int(self.kmeans.predict(vector.reshape(1, -1))[0])
        self.inverted_lists[cluster].append((id, vector))

    def search(self, query: np.ndarray, k: int = 10) -> list[tuple[float, str]]:
        # Find n_probe closest centroids
        # Trade-off: higher n_probe = better recall but slower search
        # therefore tune n_probe based on recall@k requirements
        distances = self.kmeans.transform(query.reshape(1, -1))[0]
        closest_clusters = np.argsort(distances)[:self.n_probe]

        candidates = []
        for cluster_id in closest_clusters:
            for doc_id, vec in self.inverted_lists[int(cluster_id)]:
                dist = 1.0 - np.dot(query, vec) / (
                    np.linalg.norm(query) * np.linalg.norm(vec)
                )
                candidates.append((dist, doc_id))

        candidates.sort()
        return candidates[:k]
```

### Hybrid Search: Dense + Sparse

Pure vector search misses exact keyword matches; pure BM25 misses semantic similarity. **Therefore**, hybrid search combining both is the **best practice** for production RAG systems.

```python
from typing import NamedTuple

class SearchResult(NamedTuple):
    id: str
    score: float
    dense_score: float
    sparse_score: float

class HybridSearcher:
    # Combines dense (vector) and sparse (BM25/TF-IDF) search
    # because neither alone captures all relevant documents
    # Pitfall: naive score combination without normalization

    def __init__(self, dense_index, sparse_index, alpha: float = 0.7):
        self.dense_index = dense_index
        self.sparse_index = sparse_index
        self.alpha = alpha  # weight for dense scores (1-alpha for sparse)

    def search(
        self,
        query_embedding: np.ndarray,
        query_text: str,
        k: int = 10,
        dense_k: int = 50,
        sparse_k: int = 50,
    ) -> list[SearchResult]:
        # Retrieve candidates from both indexes (over-fetch for fusion)
        dense_results = self.dense_index.search(query_embedding, k=dense_k)
        sparse_results = self.sparse_index.search(query_text, k=sparse_k)

        # Reciprocal Rank Fusion (RRF) — robust fusion method
        # RRF is preferred over score normalization because
        # it doesn't require comparable score distributions
        rrf_scores = {}
        rrf_constant = 60  # standard constant

        for rank, (score, doc_id) in enumerate(dense_results):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + (
                self.alpha / (rrf_constant + rank + 1)
            )

        for rank, (score, doc_id) in enumerate(sparse_results):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + (
                (1 - self.alpha) / (rrf_constant + rank + 1)
            )

        # Build result list with component scores
        dense_map = {did: s for s, did in dense_results}
        sparse_map = {did: s for s, did in sparse_results}

        results = [
            SearchResult(
                id=doc_id,
                score=rrf_score,
                dense_score=dense_map.get(doc_id, 0.0),
                sparse_score=sparse_map.get(doc_id, 0.0),
            )
            for doc_id, rrf_score in rrf_scores.items()
        ]

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    def calibrate_alpha(
        self,
        eval_queries: list[tuple[np.ndarray, str, set]],
        alpha_range: list[float] = None,
    ) -> float:
        # Find optimal alpha by evaluating on labeled queries
        # Best practice: tune alpha per query type or domain
        if alpha_range is None:
            alpha_range = [i/10 for i in range(11)]

        best_alpha = 0.5
        best_recall = 0.0

        for alpha in alpha_range:
            self.alpha = alpha
            total_recall = 0.0
            for emb, text, relevant_ids in eval_queries:
                results = self.search(emb, text, k=10)
                retrieved = {r.id for r in results}
                recall = len(retrieved & relevant_ids) / len(relevant_ids)
                total_recall += recall
            avg_recall = total_recall / len(eval_queries)
            if avg_recall > best_recall:
                best_recall = avg_recall
                best_alpha = alpha

        self.alpha = best_alpha
        return best_alpha
```

### Key Takeaways

- **HNSW** is the go-to index for most use cases — **however** it requires more memory than IVF because it stores graph edges alongside vectors
- **IVF with product quantization** (IVF-PQ) scales to billions of vectors — the **trade-off** is lower recall vs. dramatically less memory
- **Hybrid search** combining dense vectors with sparse BM25 is **best practice** for production RAG — **because** neither modality alone captures all relevant documents
- **Reciprocal Rank Fusion** is preferred over score normalization — a **common mistake** is directly combining scores from different scales
- **Pitfall**: not tuning search parameters (ef, n_probe, alpha) — recall can vary 20-30% based on these settings
- **Therefore**, always benchmark with domain-specific queries and tune parameters for your recall@k requirements
"""
    ),
    (
        "api-design/webhook-design-patterns",
        r"""Explain webhook architecture design including reliable delivery with retry policies, signature verification for security, idempotency handling, fan-out patterns, and implementation of both webhook provider and consumer sides.""",
        r"""## Webhook Architecture: Reliable Delivery, Security, and Production Patterns

**Webhooks** invert the traditional polling model by having servers push events to registered endpoints. This is essential for real-time integrations, **however** building a reliable webhook system is surprisingly complex. The **trade-off** is between simplicity (fire-and-forget HTTP POST) and reliability (guaranteed delivery with ordering). Production webhook systems must handle endpoint failures, replay attacks, payload verification, and idempotent processing.

### Webhook Provider: Reliable Delivery

**Best practice**: separate event generation from delivery using a transactional outbox pattern. This ensures events are never lost even if the delivery system fails.

```python
import hashlib
import hmac
import json
import time
import asyncio
import httpx
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta
from enum import Enum

class DeliveryStatus(Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD = "dead"  # exhausted all retries

@dataclass
class WebhookEvent:
    id: str
    event_type: str
    payload: dict
    created_at: float = field(default_factory=time.time)

@dataclass
class WebhookSubscription:
    id: str
    url: str
    secret: str  # shared secret for HMAC signing
    events: list[str]  # event types to subscribe to
    active: bool = True
    failure_count: int = 0
    disabled_at: Optional[float] = None

@dataclass
class DeliveryAttempt:
    id: str
    event_id: str
    subscription_id: str
    status: DeliveryStatus
    attempt_number: int
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    next_retry_at: Optional[float] = None
    duration_ms: Optional[float] = None

class WebhookDeliveryEngine:
    # Handles reliable delivery with exponential backoff
    # Common mistake: using synchronous delivery in the request path
    # because slow/failing endpoints would block the entire application

    RETRY_DELAYS = [60, 300, 1800, 7200, 43200]  # 1m, 5m, 30m, 2h, 12h
    MAX_RETRIES = 5
    TIMEOUT_SECONDS = 30
    # Disable subscription after this many consecutive failures
    CIRCUIT_BREAKER_THRESHOLD = 50

    def __init__(self, db, signing_key_prefix: str = "whsec_"):
        self.db = db
        self.signing_key_prefix = signing_key_prefix

    def sign_payload(self, payload_bytes: bytes, secret: str, timestamp: int) -> str:
        # Standard webhook signature: HMAC-SHA256 of timestamp.payload
        # Timestamp prevents replay attacks
        # Best practice: include timestamp in both header and signed content
        message = f"{timestamp}.".encode() + payload_bytes
        signature = hmac.new(
            secret.encode(),
            message,
            hashlib.sha256,
        ).hexdigest()
        return f"v1={signature}"

    async def deliver(self, event: WebhookEvent, subscription: WebhookSubscription) -> DeliveryAttempt:
        payload_bytes = json.dumps(event.payload, default=str).encode()
        timestamp = int(time.time())
        signature = self.sign_payload(payload_bytes, subscription.secret, timestamp)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-ID": event.id,
            "X-Webhook-Timestamp": str(timestamp),
            "X-Webhook-Signature": signature,
            # Idempotency key so consumers can deduplicate
            "X-Webhook-Idempotency-Key": f"{event.id}:{subscription.id}",
            "User-Agent": "HiveAI-Webhooks/1.0",
        }

        start = time.monotonic()
        attempt = DeliveryAttempt(
            id=generate_id(),
            event_id=event.id,
            subscription_id=subscription.id,
            status=DeliveryStatus.PENDING,
            attempt_number=subscription.failure_count + 1,
        )

        try:
            async with httpx.AsyncClient() as client:
                # Pitfall: not setting timeouts — hanging endpoints block workers
                response = await client.post(
                    subscription.url,
                    content=payload_bytes,
                    headers=headers,
                    timeout=self.TIMEOUT_SECONDS,
                    # Don't follow redirects — security risk
                    follow_redirects=False,
                )
            attempt.status_code = response.status_code
            attempt.response_body = response.text[:1000]  # truncate
            attempt.duration_ms = (time.monotonic() - start) * 1000

            if 200 <= response.status_code < 300:
                attempt.status = DeliveryStatus.DELIVERED
                subscription.failure_count = 0
            else:
                attempt.status = DeliveryStatus.FAILED
                subscription.failure_count += 1
                attempt.next_retry_at = self._next_retry_time(subscription.failure_count)

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            attempt.status = DeliveryStatus.FAILED
            attempt.response_body = str(e)
            attempt.duration_ms = (time.monotonic() - start) * 1000
            subscription.failure_count += 1
            attempt.next_retry_at = self._next_retry_time(subscription.failure_count)

        # Circuit breaker: disable after too many failures
        if subscription.failure_count >= self.CIRCUIT_BREAKER_THRESHOLD:
            subscription.active = False
            subscription.disabled_at = time.time()
            attempt.status = DeliveryStatus.DEAD

        return attempt

    def _next_retry_time(self, failure_count: int) -> Optional[float]:
        if failure_count > self.MAX_RETRIES:
            return None
        delay = self.RETRY_DELAYS[min(failure_count - 1, len(self.RETRY_DELAYS) - 1)]
        # Add jitter to prevent thundering herd
        import random
        jitter = random.uniform(0, delay * 0.1)
        return time.time() + delay + jitter
```

### Webhook Consumer: Verification and Idempotency

On the receiving side, consumers must verify signatures, handle duplicates, and process events idempotently.

```python
import hashlib
import hmac
import time
import json
from typing import Optional, Callable, Awaitable
from functools import wraps
from fastapi import FastAPI, Request, HTTPException, Header

app = FastAPI()

class WebhookVerifier:
    # Verifies webhook signatures to prevent spoofing
    # Common mistake: not verifying signatures — any attacker can POST to your endpoint
    # Pitfall: using simple string comparison (timing attack vulnerable)

    TIMESTAMP_TOLERANCE = 300  # 5 minutes

    def __init__(self, secret: str):
        self.secret = secret

    def verify(
        self,
        payload: bytes,
        signature_header: str,
        timestamp_header: str,
    ) -> bool:
        # Step 1: Check timestamp to prevent replay attacks
        try:
            timestamp = int(timestamp_header)
        except (ValueError, TypeError):
            return False

        if abs(time.time() - timestamp) > self.TIMESTAMP_TOLERANCE:
            return False  # Stale webhook, possible replay

        # Step 2: Compute expected signature
        message = f"{timestamp}.".encode() + payload
        expected = hmac.new(
            self.secret.encode(), message, hashlib.sha256
        ).hexdigest()
        expected_sig = f"v1={expected}"

        # Step 3: Constant-time comparison prevents timing attacks
        # Therefore, always use hmac.compare_digest, never ==
        return hmac.compare_digest(expected_sig, signature_header)

class IdempotentProcessor:
    # Ensures each webhook event is processed exactly once
    # because webhook providers may retry delivery, sending duplicates
    # Best practice: use the idempotency key provided by the sender

    def __init__(self, redis_client, ttl_hours: int = 72):
        self.redis = redis_client
        self.ttl = ttl_hours * 3600

    async def process_once(
        self,
        idempotency_key: str,
        handler: Callable[..., Awaitable],
        *args,
        **kwargs,
    ):
        # Atomic check-and-set with Redis
        lock_key = f"webhook:idempotency:{idempotency_key}"

        # NX = only set if not exists, EX = TTL
        acquired = await self.redis.set(lock_key, "processing", nx=True, ex=self.ttl)

        if not acquired:
            # Already processed or in progress
            status = await self.redis.get(lock_key)
            if status == b"completed":
                return {"status": "duplicate", "message": "Already processed"}
            elif status == b"processing":
                return {"status": "duplicate", "message": "Processing in progress"}
            # If status is "failed", allow retry
            if status != b"failed":
                return {"status": "duplicate"}

        try:
            result = await handler(*args, **kwargs)
            await self.redis.set(lock_key, "completed", ex=self.ttl)
            return result
        except Exception as e:
            await self.redis.set(lock_key, "failed", ex=self.ttl)
            raise

# Putting it together: webhook endpoint
verifier = WebhookVerifier(secret="whsec_your_secret_here")

@app.post("/webhooks/events")
async def receive_webhook(
    request: Request,
    x_webhook_signature: str = Header(...),
    x_webhook_timestamp: str = Header(...),
    x_webhook_idempotency_key: str = Header(...),
):
    body = await request.body()

    # Verify signature
    if not verifier.verify(body, x_webhook_signature, x_webhook_timestamp):
        # Return 401 — however some providers expect 200 even on failure
        # Pitfall: returning detailed error messages helps attackers
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = json.loads(body)
    # Process idempotently and return 200 quickly
    # Best practice: acknowledge receipt, process asynchronously
    # because slow processing causes the provider to retry
    await enqueue_for_processing(event, x_webhook_idempotency_key)

    return {"status": "accepted"}
```

### Key Takeaways

- **Transactional outbox** ensures webhook events are never lost — a **common mistake** is generating events outside the database transaction
- **HMAC-SHA256 signatures** with timestamps prevent spoofing and replay attacks — **therefore** always verify on the consumer side with constant-time comparison
- **Exponential backoff** with jitter prevents thundering herd on retries — the **trade-off** is between fast delivery and overwhelming failing endpoints
- **Circuit breakers** disable subscriptions after sustained failures — **because** continuing to retry dead endpoints wastes resources
- **Idempotent processing** is essential for consumers — **however** implementing it correctly requires atomic check-and-set (Redis NX) not simple database lookups
- **Best practice**: acknowledge webhooks immediately (return 200) and process asynchronously — **pitfall** is doing heavy processing synchronously, causing timeout retries
"""
    ),
]
