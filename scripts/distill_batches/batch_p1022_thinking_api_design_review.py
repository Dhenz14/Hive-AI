"""Thinking-trace code review pairs: API design (REST, GraphQL, rate limiting, pagination, webhooks)."""

PAIRS = [
    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
import traceback

app = Flask(__name__)

@app.errorhandler(Exception)
def handle_error(e):
    if isinstance(e, HTTPException):
        return jsonify({"error": str(e)}), e.code
    traceback.print_exc()
    return jsonify({"error": str(e)}), 500

@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    user = db.find_user(user_id)
    if not user:
        return jsonify({"message": "not found"}), 404
    return jsonify(user)

@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.json
    if not data.get("email"):
        return jsonify({"status": "error", "reason": "email required"}), 400
    try:
        user = db.create_user(data)
        return jsonify(user), 200
    except db.DuplicateError:
        return jsonify({"msg": "already exists"}), 409

@app.route("/api/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    db.delete_user(user_id)
    return "", 204

@app.route("/api/orders")
def list_orders():
    orders = db.get_all_orders()
    if len(orders) == 0:
        return jsonify({"error": "no orders found"}), 404
    return jsonify(orders)
```''',
        r'''<think>
Let me look at this Flask API and check the response formats across endpoints. Something already looks off at a glance...

Okay, I'm going through each endpoint's error response, and every single one uses a different format. The global handler uses `{"error": "..."}`. The GET user 404 returns `{"message": "not found"}`. The POST user 400 returns `{"status": "error", "reason": "email required"}`. The 409 uses `{"msg": "already exists"}`. And the orders endpoint uses `{"error": "no orders found"}`. That's five different keys for error messages: `error`, `message`, `reason`, `msg`, `status`. A client trying to parse errors would need to check for every possible key. This is a maintenance nightmare.

Now let me check the HTTP status codes. The `create_user` endpoint returns 200 on successful creation. But wait -- for resource creation, the correct code is 201 Created, and ideally with a Location header pointing to the new resource. That's a REST convention violation.

Hmm, something more fundamental bothers me about `list_orders`. It returns 404 when there are no orders. But an empty collection is not "not found" -- the resource `/api/orders` exists, it just contains zero items. 404 means the resource itself doesn't exist. The correct response is 200 with an empty array `[]`. Returning 404 for empty results confuses clients that use status codes for routing logic.

Let me check the error handler more carefully. `return jsonify({"error": str(e)}), 500` -- this returns the exception message to the client for ALL unhandled errors. That could leak database connection strings, SQL fragments, file paths, or ORM stack traces. The traceback.print_exc() for logging is fine, but `str(e)` should never go to the client in production. Return a generic "internal server error" message instead.

Oh, I also noticed a subtle bug. `request.json` returns None if the Content-Type header is not application/json. Then `data.get("email")` tries to call .get() on None, which raises AttributeError. So sending a request with the wrong Content-Type crashes the endpoint instead of returning a helpful 415 or 400.

There's also `delete_user` which doesn't check if the user exists before deleting. If `db.delete_user` silently succeeds on nonexistent IDs, the client gets a 204 for a no-op. That could be acceptable for idempotent deletes, actually -- but the question is whether the caller wants to know if the resource was already gone.

Priority: (1) standardize error response format across all endpoints, (2) stop leaking exception details in 500 responses, (3) fix the incorrect status codes, especially the 404 for empty collections.
</think>

## Code Review

### Critical Issues

**Inconsistent error response format (Severity: High)**

Every endpoint returns errors differently:
```python
{"error": "..."}           # global handler
{"message": "not found"}   # GET user
{"status": "error", "reason": "email required"}  # POST user validation
{"msg": "already exists"}  # POST user conflict
```

API clients cannot reliably parse errors. They have to check `error`, `message`, `reason`, `msg`, and `status` — and hope new endpoints don't invent more keys. A consistent envelope is essential.

**Internal details leaked in 500 errors (Severity: High)**

```python
return jsonify({"error": str(e)}), 500
```

For unhandled exceptions, `str(e)` can contain database connection strings, SQL fragments, file paths, or ORM internals. This is information disclosure — attackers use these details to craft further attacks.

**Wrong HTTP semantics (Severity: Medium)**

- `list_orders` returns 404 for empty results. An empty collection is a valid 200 response, not "not found." 404 means the URL itself doesn't resolve to a resource.
- `create_user` returns 200 instead of 201 Created.
- No `Location` header on resource creation.

### Reliability

`request.json` returns `None` when Content-Type is not `application/json`. The next line `data.get("email")` raises `AttributeError: 'NoneType' object has no attribute 'get'`, producing an unhelpful 500 error instead of a clear 400.

### Refactored Code

```python
from flask import Flask, jsonify, request, url_for
from werkzeug.exceptions import HTTPException
import logging
import uuid

app = Flask(__name__)
logger = logging.getLogger(__name__)


# --- Consistent error response builder ---

def error_response(status_code: int, message: str, details: dict = None):
    """All errors follow the same structure. Always."""
    body = {
        "error": {
            "code": status_code,
            "message": message,
        }
    }
    if details:
        body["error"]["details"] = details
    return jsonify(body), status_code


@app.before_request
def attach_request_id():
    """Attach unique ID for tracing across logs and responses."""
    request.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))


@app.after_request
def add_response_headers(response):
    response.headers["X-Request-ID"] = request.request_id
    return response


@app.errorhandler(HTTPException)
def handle_http_error(e):
    return error_response(e.code, e.description)


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    logger.exception("Unhandled error [%s]: %s", request.request_id, e)
    # NEVER return str(e) to client — it leaks internals
    return error_response(500, "An internal error occurred. Reference: " + request.request_id)


@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    user = db.find_user(user_id)
    if not user:
        return error_response(404, f"User {user_id} not found")
    return jsonify({"data": user})


@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True)
    if data is None:
        return error_response(400, "Request body must be valid JSON",
                              {"content_type": "Expected application/json"})

    # Validate required fields
    validation_errors = {}
    if not data.get("email"):
        validation_errors["email"] = "is required"
    if not data.get("name"):
        validation_errors["name"] = "is required"
    if validation_errors:
        return error_response(400, "Validation failed", validation_errors)

    try:
        user = db.create_user(data)
    except db.DuplicateError:
        return error_response(409, "A user with this email already exists")

    response = jsonify({"data": user})
    response.status_code = 201
    response.headers["Location"] = url_for("get_user", user_id=user["id"], _external=True)
    return response


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    user = db.find_user(user_id)
    if not user:
        return error_response(404, f"User {user_id} not found")
    db.delete_user(user_id)
    return "", 204


@app.route("/api/orders")
def list_orders():
    orders = db.get_all_orders()
    # Empty collection is valid — NOT a 404
    return jsonify({
        "data": orders,
        "count": len(orders),
    })
```

### Key Changes Summary

| Before | After |
|--------|-------|
| 5 different error formats (`error`, `message`, `reason`, `msg`) | Single `error_response()` with consistent `{"error": {"code", "message"}}` |
| `str(e)` leaked in 500 responses | Generic message + request ID for log correlation |
| Empty orders list returns 404 | Returns 200 with empty `data: []` |
| POST returns 200 | Returns 201 with `Location` header |
| `request.json` crashes on non-JSON body | `request.get_json(silent=True)` + null check |
| No request tracing | Request ID in header and error responses |
| No logging | Structured logging with request ID |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
import graphene
from graphene_django import DjangoObjectType
from myapp.models import User, Post, Comment

class CommentType(DjangoObjectType):
    class Meta:
        model = Comment

class PostType(DjangoObjectType):
    class Meta:
        model = Post
    comments = graphene.List(CommentType)

    def resolve_comments(self, info):
        return Comment.objects.filter(post=self)

class UserType(DjangoObjectType):
    class Meta:
        model = User
    posts = graphene.List(PostType)

    def resolve_posts(self, info):
        return Post.objects.filter(author=self)

class Query(graphene.ObjectType):
    users = graphene.List(UserType)
    user = graphene.Field(UserType, id=graphene.Int(required=True))

    def resolve_users(self, info):
        return User.objects.all()

    def resolve_user(self, info, id):
        return User.objects.get(pk=id)
```''',
        r'''<think>
Okay, this is a Graphene-Django GraphQL schema. Let me think about what a malicious client could do with this...

My first concern is query depth. There's no depth limiting configured. If Comment has an `author` field (which DjangoObjectType auto-exposes all model fields), a client could write a deeply nested query: users -> posts -> comments -> author -> posts -> comments -> author -> ... That's potentially infinite recursion. Even without actual cycles, a query requesting all users with all their posts and all comments on each post could generate a massive result set.

Let me estimate the query count. `resolve_users` returns all users with no limit. For each user, `resolve_posts` fires a separate query. For each post, `resolve_comments` fires yet another. So with 100 users, 10 posts each, 5 comments each: 1 + 100 + 1000 = 1101 database queries for a single GraphQL request. That's the N+1 problem at two levels.

Wait, but the query count isn't even the worst part. The response size could be enormous. If there are 100K users in the database, `resolve_users` returns ALL of them. With nested posts and comments, the response could be gigabytes. This is a denial-of-service vector -- an attacker doesn't need to flood with requests, just send one carefully crafted deep query.

Hmm, I should also check what fields are being exposed. DjangoObjectType with no `fields` restriction auto-exposes EVERY model field. That could include email addresses, phone numbers, password hashes, internal flags -- whatever is on the User model. There's no `info.context.user` check either, so any anonymous client can query this data.

Graphene-Django has tools to fix the N+1 problem -- DjangoListField and dataloaders -- but they're not being used here. For pagination, the relay-style connection pattern with cursor-based pagination would be the GraphQL-idiomatic solution. And they need graphene-django's built-in query depth/cost analysis, or a library like graphql-depth-limit.

There's also a subtle error handling issue: `User.objects.get(pk=id)` raises DoesNotExist if the ID is invalid, which becomes a 500 error. Should return None instead and let the client handle it gracefully.

Priority: (1) unbounded depth is the DoS vector -- needs depth limiting immediately, (2) N+1 queries will crush the database under any real load, (3) field restrictions to prevent leaking sensitive data.
</think>

## Code Review

### Critical Issues

**Unbounded query depth — denial of service (Severity: Critical)**

There is no depth or complexity limit on queries. A malicious client can craft a deeply nested query that causes exponential database queries and memory usage:

```graphql
{ users { posts { comments { post { comments { post { ... } } } } } } }
```

Even moderate nesting is dangerous: querying 1000 users with 50 posts each with 20 comments produces millions of rows. This is a well-known GraphQL attack vector.

**N+1 queries (Severity: High)**

Each resolver fires an independent database query per parent object:
- 1 query for users
- N queries for posts (one per user)
- N*M queries for comments (one per post)

For 100 users with 10 posts each: 1 + 100 + 1000 = 1,101 database queries for a single GraphQL request.

**All model fields auto-exposed (Severity: High)**

`DjangoObjectType` with no `fields` restriction exposes every model field, including `password`, `last_login`, `email`, or any other sensitive column. This is an information disclosure vulnerability.

### Missing Functionality

- No pagination: `User.objects.all()` returns the entire table
- No authorization: anyone can query all user data
- `User.objects.get(pk=id)` raises 500 on missing users instead of returning null

### Refactored Code

```python
import graphene
from graphene_django import DjangoObjectType, DjangoListField
from graphql import GraphQLError
from promise import Promise
from promise.dataloader import DataLoader
from myapp.models import User, Post, Comment


# --- DataLoaders to batch N+1 queries ---

class PostsByUserLoader(DataLoader):
    def batch_load_fn(self, user_ids):
        posts = Post.objects.filter(author_id__in=user_ids)
        posts_by_user = {uid: [] for uid in user_ids}
        for post in posts:
            posts_by_user[post.author_id].append(post)
        return Promise.resolve([posts_by_user[uid] for uid in user_ids])


class CommentsByPostLoader(DataLoader):
    def batch_load_fn(self, post_ids):
        comments = Comment.objects.filter(post_id__in=post_ids)
        comments_by_post = {pid: [] for pid in post_ids}
        for comment in comments:
            comments_by_post[comment.post_id].append(comment)
        return Promise.resolve([comments_by_post[pid] for pid in post_ids])


# --- Types with EXPLICIT field lists ---

class CommentType(DjangoObjectType):
    class Meta:
        model = Comment
        fields = ('id', 'text', 'created_at')  # explicit — no sensitive fields leaked


class PostType(DjangoObjectType):
    class Meta:
        model = Post
        fields = ('id', 'title', 'body', 'created_at')

    comments = graphene.List(CommentType)

    def resolve_comments(self, info):
        return info.context.comments_loader.load(self.id)


class UserType(DjangoObjectType):
    class Meta:
        model = User
        fields = ('id', 'username', 'display_name')  # NOT email, password, etc.

    posts = graphene.List(PostType)

    def resolve_posts(self, info):
        return info.context.posts_loader.load(self.id)


class Query(graphene.ObjectType):
    users = graphene.List(
        UserType,
        first=graphene.Int(default_value=20),
        offset=graphene.Int(default_value=0),
    )
    user = graphene.Field(UserType, id=graphene.Int(required=True))

    def resolve_users(self, info, first, offset):
        # Cap page size to prevent huge responses
        first = min(first, 100)
        return User.objects.all()[offset:offset + first]

    def resolve_user(self, info, id):
        try:
            return User.objects.get(pk=id)
        except User.DoesNotExist:
            return None  # GraphQL convention: return null, not an error


# --- Middleware for depth limiting ---

class DepthLimitMiddleware:
    """Reject queries deeper than max_depth to prevent abuse."""

    def __init__(self, max_depth=5):
        self.max_depth = max_depth

    def resolve(self, next, root, info, **args):
        # Check depth from the field's AST path
        depth = 0
        node = info.field_nodes[0]
        while node:
            depth += 1
            selections = getattr(node.selection_set, 'selections', None)
            if selections:
                node = selections[0]  # check deepest branch
            else:
                node = None

        if depth > self.max_depth:
            raise GraphQLError(
                f"Query exceeds maximum depth of {self.max_depth}"
            )
        return next(root, info, **args)


# --- Schema setup with dataloaders injected per-request ---

schema = graphene.Schema(query=Query)

# In your Django view / middleware, attach loaders to request context:
# class GraphQLView:
#     def get_context(self, request):
#         request.posts_loader = PostsByUserLoader()
#         request.comments_loader = CommentsByPostLoader()
#         return request
```

### Key Changes Summary

| Before | After |
|--------|-------|
| No depth limit — unbounded nesting | `DepthLimitMiddleware` caps at 5 levels |
| N+1 queries (1101 for 100 users) | DataLoaders batch into 3 queries total |
| All model fields auto-exposed | Explicit `fields` tuple — no password/email leaks |
| `User.objects.all()` — unbounded | `first`/`offset` pagination, capped at 100 |
| `User.objects.get()` raises 500 | Returns `None` on missing user |
| No query cost analysis | Depth checking middleware |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
import time
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)
rate_limits = {}  # {ip: [timestamp, timestamp, ...]}
LIMIT = 100
WINDOW = 60  # seconds

def check_rate_limit(ip: str) -> bool:
    now = time.time()
    if ip not in rate_limits:
        rate_limits[ip] = []

    # Clean old entries
    rate_limits[ip] = [t for t in rate_limits[ip] if now - t < WINDOW]

    if len(rate_limits[ip]) >= LIMIT:
        return False

    rate_limits[ip].append(now)
    return True

@app.before_request
def rate_limiter():
    ip = request.remote_addr
    if not check_rate_limit(ip):
        return jsonify({"error": "rate limit exceeded"}), 429
```''',
        r'''<think>
Let me think about this rate limiter carefully. It's using an in-memory dict to track timestamps per IP with a sliding window approach. At first glance the logic seems reasonable, but let me think about what happens under concurrency...

Flask with a multi-threaded WSGI server (like gunicorn with threads) will have multiple threads accessing `rate_limits` simultaneously. The check_rate_limit function does a read-modify-write sequence: read the current count, decide if it's under the limit, then append a new timestamp. But there's no locking, so:

1. Thread A reads: 99 entries (under limit of 100)
2. Thread B reads: 99 entries (also under limit)
3. Thread A appends -> 100 entries, allows request
4. Thread B appends -> 101 entries, also allows request

So both threads get through even though the limit was 100. The race window is actually quite wide because of the list comprehension cleanup step between the read and the write. And this happens exactly when rate limiting matters most -- under heavy load from the same IP.

But wait, there's an even more fundamental issue I should consider. What if you're running gunicorn with multiple worker processes? Each worker has its own copy of the `rate_limits` dict. An attacker hitting different workers gets N times the rate limit. With 4 workers, that's 400 requests per window instead of 100. In production, rate limiting HAS to use a shared store like Redis to work across processes.

Now let me think about memory. Every unique IP gets a key in the dict that's never removed. The cleanup inside check_rate_limit removes old timestamps from the list, but the dict key with an empty list persists forever. If this runs behind a CDN or serves many mobile clients, you'll accumulate millions of IP keys over days, each with empty lists consuming memory. That's a slow leak.

Hmm, there's also a practical issue I almost missed: `request.remote_addr` behind a reverse proxy (nginx, CloudFlare) returns the proxy's IP, not the client's. So every client in the world shares the same rate limit bucket. One heavy user triggers the limit for everyone. Should use X-Forwarded-For or X-Real-IP, but even those can be spoofed.

Priority: (1) the race condition defeats the entire purpose of the limiter, (2) single-process storage makes it useless in production deployments, (3) the memory leak will eventually crash long-running services.
</think>

## Code Review

### Critical Issues

**Race condition — rate limit bypass (Severity: Critical)**

The `rate_limits` dict is shared mutable state accessed from multiple threads without synchronization. The check-then-append sequence is not atomic:

```python
if len(rate_limits[ip]) >= LIMIT:  # Thread A: 99 < 100, proceed
    return False
rate_limits[ip].append(now)         # Thread A and B both append
```

Under concurrent load from the same IP, multiple threads read the count before any of them write. The rate limit can be exceeded significantly. This fails precisely when it matters most — during an attack with many concurrent requests.

**Single-process limitation (Severity: High)**

With multiple WSGI workers (standard production deployment), each worker has its own independent `rate_limits` dict. An attacker hitting 4 workers effectively gets 4x the rate limit. Rate limiting must use a shared store like Redis.

**Unbounded memory growth (Severity: Medium)**

Old timestamps are cleaned from lists, but IP keys are never removed. After days of operation behind a NAT gateway or CDN, millions of IP keys accumulate with empty lists.

### Missing Features

- `request.remote_addr` behind a proxy returns the proxy IP — all clients share one bucket
- No `Retry-After` header tells clients when to retry
- No per-endpoint rate limits (login needs stricter limits than read endpoints)
- No way to whitelist internal IPs

### Refactored Code

```python
import time
import logging
from flask import Flask, request, jsonify, g

logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Production rate limiter using Redis ---

import redis

redis_client = redis.Redis.from_url(
    "redis://localhost:6379/1",
    decode_responses=True,
    socket_connect_timeout=1,
)

DEFAULT_LIMIT = 100
DEFAULT_WINDOW = 60
STRICT_LIMIT = 10  # for sensitive endpoints like login


def get_client_ip() -> str:
    """Get real client IP, respecting reverse proxy headers.
    IMPORTANT: Only trust X-Forwarded-For if you control the proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First IP in chain is the original client
        return forwarded.split(",")[0].strip()
    return request.remote_addr


def check_rate_limit(key: str, limit: int, window: int) -> tuple[bool, dict]:
    """Sliding window rate limiter using Redis sorted sets.
    Atomic — no race conditions even across multiple workers.

    Returns (allowed, info_dict).
    """
    now = time.time()
    pipeline = redis_client.pipeline(transaction=True)

    try:
        # All operations are atomic within the pipeline
        pipeline.zremrangebyscore(key, 0, now - window)  # clean old entries
        pipeline.zadd(key, {f"{now}": now})               # add current request
        pipeline.zcard(key)                                # count entries
        pipeline.expire(key, window + 1)                   # auto-cleanup key
        results = pipeline.execute()

        current_count = results[2]
        allowed = current_count <= limit
        remaining = max(0, limit - current_count)

        # Calculate retry-after if limited
        if not allowed:
            oldest = redis_client.zrange(key, 0, 0, withscores=True)
            retry_after = int(oldest[0][1] + window - now) + 1 if oldest else window
        else:
            retry_after = 0

        return allowed, {
            "limit": limit,
            "remaining": remaining,
            "retry_after": retry_after,
            "window": window,
        }

    except redis.ConnectionError:
        # If Redis is down, ALLOW requests (fail open) but log warning
        logger.warning("Redis unavailable for rate limiting")
        return True, {"limit": limit, "remaining": -1, "retry_after": 0, "window": window}


# Endpoint-specific limits
RATE_LIMIT_OVERRIDES = {
    "/api/auth/login": (STRICT_LIMIT, 300),     # 10 per 5 minutes
    "/api/auth/register": (STRICT_LIMIT, 3600), # 10 per hour
}

WHITELIST_IPS = {"127.0.0.1", "::1"}


@app.before_request
def rate_limiter():
    ip = get_client_ip()

    if ip in WHITELIST_IPS:
        return None

    # Check for endpoint-specific limits
    limit, window = RATE_LIMIT_OVERRIDES.get(
        request.path, (DEFAULT_LIMIT, DEFAULT_WINDOW)
    )

    key = f"ratelimit:{ip}:{request.path}"
    allowed, info = check_rate_limit(key, limit, window)

    # Always set rate limit headers (even when allowed)
    g.rate_limit_info = info

    if not allowed:
        logger.warning("Rate limited: %s on %s", ip, request.path)
        response = jsonify({"error": "Rate limit exceeded. Try again later."})
        response.status_code = 429
        response.headers["Retry-After"] = str(info["retry_after"])
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = "0"
        return response


@app.after_request
def add_rate_limit_headers(response):
    info = getattr(g, "rate_limit_info", None)
    if info:
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Window"] = str(info["window"])
    return response
```

### Key Changes Summary

| Before | After |
|--------|-------|
| Python dict — race condition under threads | Redis sorted set — atomic pipeline, no races |
| Single-process only | Shared Redis — works across all workers |
| Unbounded memory growth | `expire()` auto-cleans Redis keys |
| `request.remote_addr` (proxy IP) | `X-Forwarded-For` parsing for real client IP |
| No `Retry-After` header | `Retry-After` + `X-RateLimit-*` headers |
| Same limit for all endpoints | Per-endpoint overrides (strict for login) |
| Hard failure if store is down | Fail-open with logging if Redis unavailable |
| No IP whitelist | `WHITELIST_IPS` for internal traffic |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
from fastapi import FastAPI, Query
from typing import Optional

app = FastAPI()

@app.get("/api/items")
async def list_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
):
    offset = (page - 1) * per_page
    query = db.query(Item)
    if category:
        query = query.filter(Item.category == category)
    total = query.count()
    items = query.order_by(Item.id).offset(offset).limit(per_page).all()
    return {
        "items": [item.to_dict() for item in items],
        "page": page,
        "per_page": per_page,
        "total": total,
    }
```''',
        r'''<think>
This looks like a standard offset/limit pagination endpoint. At first glance it seems fine -- but offset pagination has a well-known fundamental flaw that I need to think through.

Let me walk through a concrete scenario. A user is viewing page 2 (offset=20, limit=20). While they're reading, a new item gets inserted that sorts before position 20. Now all items shift forward by one position. The item that was at position 20 is now at position 21. When the user clicks to page 3 (offset=40), they see that item again -- a duplicate. Conversely, if an item was deleted while they were browsing, they miss one entirely.

Is this always a problem? For a product catalog that changes once a day, it's probably acceptable. But for a social feed, activity stream, or any real-time data, the user experience gets visibly corrupted. Cursor-based pagination (keyset pagination) solves this by saying "give me items after this ID" instead of "give me items starting at position N."

Now let me think about performance. What happens when a user paginates deep into the results? `OFFSET 1000000 LIMIT 20` -- the database can't just jump to row 1,000,000. It has to scan from the beginning, skipping 1 million rows. So page 1 takes 5ms, page 1000 takes 500ms, page 50000 takes 25 seconds. Response time degrades linearly with depth.

Hmm, there's another performance concern. `query.count()` runs a separate COUNT query on every single page request. On a large table with complex filters, that count query alone can take seconds. For many applications, you don't actually need an exact total. A `has_next` flag (fetch limit+1 items, check if you got one extra) is much cheaper and often sufficient for the UI.

Wait, I should also check whether the count query and the data query can interfere with each other. They use the same SQLAlchemy query object. Depending on the version and session state, calling count() might mutate the query in a way that affects the subsequent slice. That's a subtle bug if it happens.

The response is also missing useful pagination metadata -- no prev/next links, no has_next flag, no total_pages. The client has to calculate everything manually.

Priority: (1) the offset pagination correctness issue on live data, (2) performance degradation at high offsets, (3) expensive COUNT query on every page load.
</think>

## Code Review

### Critical Issues

**Offset pagination causes duplicates and missed items (Severity: High)**

When data changes between page requests (inserts, deletes, reordering), offset-based pagination produces incorrect results:

1. User fetches page 2 (offset=20)
2. A new item is inserted at position 5
3. All subsequent items shift right by 1
4. User fetches page 3 (offset=40) — the item that was at position 39 is now at position 40, so they see it again (duplicate)

For live data (feeds, logs, queues), this is a real bug. Users see duplicates or miss items entirely. The fix is cursor-based (keyset) pagination.

**Performance degrades linearly with page depth (Severity: Medium)**

`OFFSET 100000 LIMIT 20` scans 100,020 rows internally. Page 5000 is orders of magnitude slower than page 1. This is a well-known database limitation — offset cannot "skip" rows, it must scan them.

### Missing Pagination Metadata

- No `has_next` / `has_previous` flags
- No total page count
- No navigation links (prev/next URLs)
- `query.count()` on every request is expensive on large tables

### Refactored Code

```python
from fastapi import FastAPI, Query, Request
from typing import Optional
from urllib.parse import urlencode

app = FastAPI()


@app.get("/api/items")
async def list_items(
    request: Request,
    cursor: Optional[str] = Query(None, description="Cursor from previous response"),
    per_page: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
):
    """Cursor-based pagination. Stable results even when data changes."""
    query = db.query(Item)
    if category:
        query = query.filter(Item.category == category)

    # Cursor-based: fetch items after the cursor ID
    if cursor:
        try:
            cursor_id = int(cursor)
        except ValueError:
            return {"error": "Invalid cursor"}, 400
        query = query.filter(Item.id > cursor_id)

    # Fetch one extra to detect if there's a next page
    items = query.order_by(Item.id).limit(per_page + 1).all()

    has_next = len(items) > per_page
    items = items[:per_page]  # trim the extra

    # Build cursor for next page
    next_cursor = str(items[-1].id) if items and has_next else None

    # Build navigation links
    base_url = str(request.url).split("?")[0]
    links = {}
    if next_cursor:
        params = {"cursor": next_cursor, "per_page": per_page}
        if category:
            params["category"] = category
        links["next"] = f"{base_url}?{urlencode(params)}"

    return {
        "data": [item.to_dict() for item in items],
        "pagination": {
            "per_page": per_page,
            "has_next": has_next,
            "next_cursor": next_cursor,
            "links": links,
        },
    }


# If you MUST support offset pagination (e.g., admin UI with page numbers),
# at least add caching and limits:

@app.get("/api/items/browse")
async def browse_items(
    page: int = Query(1, ge=1, le=1000),  # cap maximum page depth
    per_page: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
):
    """Offset pagination for admin UI. Capped at page 1000."""
    offset = (page - 1) * per_page
    query = db.query(Item)
    if category:
        query = query.filter(Item.category == category)

    # Avoid expensive COUNT on every request — cache or estimate
    total = query.count()  # consider caching this value

    items = query.order_by(Item.id).offset(offset).limit(per_page).all()

    total_pages = -(-total // per_page)  # ceiling division

    return {
        "data": [item.to_dict() for item in items],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
    }
```

### Key Changes Summary

| Before | After |
|--------|-------|
| Offset pagination — duplicates on data changes | Cursor-based: `WHERE id > cursor` — stable results |
| `OFFSET 100000` scans 100K rows | `WHERE id > X` uses index — constant time at any depth |
| No `has_next` flag | Fetch N+1, check if extra exists |
| No navigation links | `links.next` with full URL |
| No page depth limit | Offset variant capped at page 1000 |
| Count query on every request | Acknowledged as a cost, suggested caching |
| Items wrapped in top-level key | `data` + `pagination` structured response |

### When to Use Each Pattern

| Pattern | Good For | Bad For |
|---------|----------|---------|
| Cursor (keyset) | Feeds, logs, real-time data, infinite scroll | "Jump to page 50" UI |
| Offset | Admin tables, small datasets, page-number UI | Deep pages, live data |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
import hmac
import hashlib
import json
from flask import Flask, request, jsonify

app = Flask(__name__)
WEBHOOK_SECRET = "whsec_abc123xyz"

@app.route("/webhooks/payment", methods=["POST"])
def handle_payment_webhook():
    payload = request.data
    signature = request.headers.get("X-Signature")

    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if signature != expected:
        return jsonify({"error": "invalid signature"}), 401

    event = json.loads(payload)

    if event["type"] == "payment.completed":
        order = db.get_order(event["data"]["order_id"])
        order.status = "paid"
        order.payment_id = event["data"]["payment_id"]
        db.save(order)

        # Send confirmation email
        email_service.send_receipt(order.user.email, order)

    elif event["type"] == "payment.failed":
        order = db.get_order(event["data"]["order_id"])
        order.status = "payment_failed"
        db.save(order)

    elif event["type"] == "refund.completed":
        order = db.get_order(event["data"]["order_id"])
        order.status = "refunded"
        db.save(order)

    return jsonify({"received": True}), 200
```''',
        r'''<think>
Let me think about this webhook handler. It receives payment events, verifies an HMAC signature, and processes the event by updating order status and sending emails.

My first concern is idempotency. Webhook providers like Stripe retry deliveries when they don't get a 2xx response in time. So I need to ask: what happens if this handler receives the same event twice?

Let me trace through a scenario. A "payment.completed" event comes in, the handler updates the order to "paid" and sends a receipt email. Then the provider retries (maybe the 200 response was lost). The handler processes it again -- sends another receipt email. That's annoying but not catastrophic. But now consider a worse case: an order was "refunded", and then an old "payment.completed" webhook gets retried due to a network hiccup. The handler blindly sets the status back to "paid". A refunded order now appears as paid. That's a state machine violation that could cause real financial issues.

Now let me check the signature verification. `if signature != expected` -- hmm, the `!=` operator on strings short-circuits on the first differing byte. An attacker could theoretically determine the correct signature one byte at a time by measuring response time differences. This is a known timing attack. Should use `hmac.compare_digest()` which does constant-time comparison.

Wait, there's also the webhook secret hardcoded as `WEBHOOK_SECRET = "whsec_abc123xyz"`. That's in source code, which means it ends up in version control. If the repo is compromised, an attacker can forge valid webhook payloads.

Let me think about the processing flow too. The handler does database updates AND sends emails synchronously before returning 200. If the email service takes 5 seconds, the webhook provider might time out at 3 seconds and retry. Now you have two concurrent invocations processing the same event. The best practice for webhooks is: verify the signature, store the event, return 200 immediately, then process asynchronously via a task queue.

One more thing -- `db.get_order(order_id)` could return None if the order doesn't exist. Then `order.status = "paid"` raises AttributeError. And there's no state machine enforcement -- the handler doesn't check the current state before transitioning. "Completed" events should only transition orders from "pending" to "paid", not from "refunded" to "paid".

Priority: (1) idempotency with event deduplication and state machine checks, (2) constant-time signature comparison, (3) async processing to avoid timeout-retry loops.
</think>

## Code Review

### Critical Issues

**No idempotency — duplicate processing on retry (Severity: Critical)**

Webhook providers retry on timeout or non-2xx responses. Without idempotency, the same event is processed multiple times:
- Duplicate emails to customers
- State machine violations: a retried "payment.completed" overwrites a "refunded" status

There is no event ID tracking, no deduplication, no state machine enforcement.

**Timing attack on signature comparison (Severity: High)**

```python
if signature != expected:
```

Python's `!=` for strings short-circuits on the first differing byte. An attacker can brute-force the signature one byte at a time by measuring response time differences. Use `hmac.compare_digest()` for constant-time comparison.

**Synchronous processing causes retry loops (Severity: High)**

Database updates and email sending happen before returning 200. If `email_service.send_receipt` takes 5+ seconds, the webhook provider times out and retries. The retry triggers another email send, which times out again. This creates an infinite loop of retries and duplicate emails.

### Other Issues

- Hardcoded webhook secret in source code
- `db.get_order()` may return `None` — causes `AttributeError` crash
- No logging of received events
- No state machine validation (can go from "refunded" back to "paid")

### Refactored Code

```python
import hmac
import hashlib
import json
import logging
import os
from flask import Flask, request, jsonify

app = Flask(__name__)
logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

# Valid state transitions — enforce order lifecycle
VALID_TRANSITIONS = {
    "pending":        {"paid", "payment_failed"},
    "paid":           {"refunded"},
    "payment_failed": {"paid"},  # retry payment allowed
    # "refunded" is terminal — no transitions out
}


def verify_signature(payload: bytes, signature: str) -> bool:
    """Constant-time HMAC verification."""
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


@app.route("/webhooks/payment", methods=["POST"])
def handle_payment_webhook():
    payload = request.data
    signature = request.headers.get("X-Signature", "")

    if not verify_signature(payload, signature):
        logger.warning("Invalid webhook signature from %s", request.remote_addr)
        return jsonify({"error": "invalid signature"}), 401

    event = json.loads(payload)
    event_id = event.get("id")
    event_type = event.get("type")

    logger.info("Webhook received: %s (id=%s)", event_type, event_id)

    # --- Idempotency check: skip if already processed ---
    if event_id and db.webhook_event_exists(event_id):
        logger.info("Duplicate webhook %s, skipping", event_id)
        return jsonify({"received": True, "status": "duplicate"}), 200

    # Return 200 immediately, process async to avoid provider timeouts
    # In a simple setup, process inline but AFTER recording the event
    try:
        _process_event(event)
    except Exception:
        logger.exception("Failed to process webhook %s", event_id)
        # Still return 200 — we recorded the event, will retry from our side
        # Returning 500 would cause the provider to retry (and we'd get duplicates)

    # Record event as processed (idempotency key)
    if event_id:
        db.record_webhook_event(event_id, event_type, payload.decode())

    return jsonify({"received": True}), 200


def _process_event(event: dict):
    """Process webhook event with state machine enforcement."""
    event_type = event["type"]
    data = event["data"]

    order = db.get_order(data.get("order_id"))
    if order is None:
        logger.error("Order %s not found for event %s", data.get("order_id"), event_type)
        return

    EVENT_TO_STATUS = {
        "payment.completed": "paid",
        "payment.failed": "payment_failed",
        "refund.completed": "refunded",
    }

    new_status = EVENT_TO_STATUS.get(event_type)
    if not new_status:
        logger.info("Unhandled event type: %s", event_type)
        return

    # Enforce state machine — prevent invalid transitions
    allowed = VALID_TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        logger.warning(
            "Invalid transition for order %s: %s -> %s (ignoring)",
            order.id, order.status, new_status,
        )
        return

    order.status = new_status
    if event_type == "payment.completed":
        order.payment_id = data.get("payment_id")
    db.save(order)

    logger.info("Order %s: %s -> %s", order.id, order.status, new_status)

    # Queue email asynchronously — don't block webhook response
    if event_type == "payment.completed":
        email_queue.enqueue(
            "send_receipt",
            order_id=order.id,
            idempotency_key=f"receipt-{order.id}-{event['id']}",
        )
```

### Key Changes Summary

| Before | After |
|--------|-------|
| No idempotency — duplicates on retry | Event ID recorded; duplicates detected and skipped |
| `signature != expected` (timing attack) | `hmac.compare_digest()` (constant-time) |
| No state machine — "refunded" can revert to "paid" | `VALID_TRANSITIONS` dict enforces lifecycle |
| Sync email blocks response → provider timeout → retry loop | Email queued asynchronously |
| `db.get_order()` crashes on None | Null check with error logging |
| Hardcoded webhook secret | `os.environ["WEBHOOK_SECRET"]` |
| No logging | Event receipt, processing, and errors all logged |
| Returns 500 on processing error → provider retries | Always returns 200 after recording event |
'''),
]
