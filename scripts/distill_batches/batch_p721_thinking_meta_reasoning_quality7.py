"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 7)
Mixed remaining scenarios to complete Phase 3B.
"""

PAIRS = [
    (
        "thinking/meta-reasoning-sync-vs-async-python",
        r'''For a web API that handles 100 concurrent users making database queries, compare:

Sync (Flask + gunicorn):
```python
from flask import Flask
app = Flask(__name__)

@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    user = db.session.query(User).get(user_id)
    return jsonify(user.to_dict())

# gunicorn -w 4 --threads 4 app:app  (16 threads total)
```

Async (FastAPI + uvicorn):
```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    user = await async_db.get(User, user_id)
    return user.to_dict()

# uvicorn app:app --workers 4
```

Which handles 100 concurrent users better?''',
        r'''<think>
For a web API doing database queries with 100 concurrent users.

**Flask + gunicorn (sync):**
- 4 workers × 4 threads = 16 concurrent requests
- Request 17-100 must wait in queue
- Each thread blocks while waiting for DB response
- Thread overhead: ~8MB per thread (stack), so 16 threads = ~128MB
- Simple to write and debug
- Can handle 100 concurrent if DB queries are fast (~10ms each)

**FastAPI + uvicorn (async):**
- 4 workers, each with an event loop
- Each event loop handles many concurrent requests
- While awaiting DB, event loop serves other requests
- Memory: ~1KB per coroutine vs ~8MB per thread
- Can handle thousands of concurrent connections
- Requires async DB driver (asyncpg, aiosqlite)
- More complex debugging (async stack traces)

**For 100 concurrent users doing DB queries:**
If DB queries take ~10ms:
- Sync: 16 threads × 100 queries/sec = 1,600 req/sec throughput
- Async: effectively unlimited concurrent requests, ~4,000+ req/sec

If DB queries take ~100ms:
- Sync: 16 threads × 10 queries/sec = 160 req/sec. With 100 concurrent, response time degrades.
- Async: 100 concurrent requests wait on DB without blocking threads. Throughput limited by DB pool, not threads.

**Winner:** For 100 concurrent users, async (FastAPI) handles concurrency more efficiently. But Flask with enough threads (gunicorn --threads 100) can also handle it — just less memory-efficiently.

The practical difference depends on DB query latency. For very fast queries (<5ms), both handle 100 users fine. For slow queries (>50ms), async has a clear advantage.
</think>

**FastAPI (async) handles high concurrency more efficiently — 100 concurrent users is where async starts showing advantages.**

### Evaluation

| Axis | Flask (sync) | FastAPI (async) |
|------|-------------|----------------|
| 100 concurrent requests | Need 100 threads | 1 event loop handles all |
| Memory per connection | ~8MB (thread stack) | ~1KB (coroutine) |
| Throughput (slow DB) | Limited by thread count | Limited by DB pool |
| Code complexity | Simple (synchronous) | Moderate (async/await) |
| Debugging | Standard stack traces | Async traces (harder) |
| Ecosystem maturity | Very mature | Mature (growing fast) |
| Auto-docs | Manual (Swagger plugin) | Built-in (OpenAPI) |

### The concurrency math
```
DB query latency: 50ms

Flask (16 threads):
  Max concurrent: 16
  Throughput: 16 / 0.05s = 320 req/sec
  Request 17-100: queued → increased latency

FastAPI (async, 50 DB pool):
  Max concurrent: 50 (DB pool limit)
  Throughput: 50 / 0.05s = 1,000 req/sec
  All 100 requests handled without thread exhaustion
```

### When sync Flask is fine
- Low concurrency (< 20 concurrent users)
- Fast DB queries (< 10ms)
- Simple CRUD without external API calls
- Team unfamiliar with async

### When async FastAPI is better
- High concurrency (100+ concurrent users)
- Slow operations (external API calls, slow queries)
- WebSocket support needed
- Type safety and auto-docs valued

### The reasoning pattern
The sync/async choice depends on concurrency level and I/O latency. For low concurrency with fast I/O, sync is simpler with equivalent performance. For high concurrency or slow I/O, async uses resources far more efficiently. The crossover point is roughly where concurrent connections exceed your thread count.'''
    ),
    (
        "thinking/meta-reasoning-rbac-vs-abac",
        r'''For access control in an enterprise application, compare:

RBAC (Role-Based Access Control):
```python
ROLES = {
    "admin": ["read", "write", "delete", "manage_users"],
    "editor": ["read", "write"],
    "viewer": ["read"],
}

def check_permission(user, action):
    return action in ROLES.get(user.role, [])
```

ABAC (Attribute-Based Access Control):
```python
def check_permission(user, action, resource):
    # Rule 1: Admins can do anything
    if user.role == "admin":
        return True
    # Rule 2: Users can only edit their own resources
    if action == "write" and resource.owner_id != user.id:
        return False
    # Rule 3: Department heads can manage department resources
    if action == "manage" and user.is_department_head and resource.department == user.department:
        return True
    # Rule 4: Resources marked confidential require clearance level 3+
    if resource.classification == "confidential" and user.clearance_level < 3:
        return False
    return action in ROLES.get(user.role, [])
```

Which is better for enterprise access control?''',
        r'''<think>
Let me evaluate both for enterprise use.

**RBAC:**
Simple: users have roles, roles have permissions. Easy to understand, audit, and implement.

But it CANNOT express:
- "Users can only edit THEIR OWN documents" (needs resource context)
- "Managers can approve expenses under $5000" (needs attribute comparison)
- "Interns can't access confidential data" (needs classification attribute)
- "Employees can only access data during business hours" (needs time context)

For these, you need either hundreds of roles ("editor-own-documents", "editor-department-documents", "editor-confidential-clearance-3") or a different model.

**ABAC:**
Can express any rule based on:
- Subject attributes (user role, department, clearance level)
- Resource attributes (owner, department, classification)
- Action attributes (read, write, delete)
- Context attributes (time, IP address, location)

But it's more complex: rules can interact, debugging "why was access denied?" is harder, and the rule engine itself needs careful testing.

**For enterprise:**
Enterprises have complex access patterns:
- Multi-department data segregation
- Confidentiality levels
- Self-service vs managed resources
- Regulatory compliance (data residency, access logging)

Pure RBAC requires an explosion of roles. ABAC handles these naturally.

**Winner:** ABAC for enterprise. But start with RBAC for simple cases and add attribute-based rules as needed. Most systems use a hybrid.
</think>

**ABAC is better for enterprise — it handles the complex access patterns (ownership, department segregation, classification levels) that RBAC can't express without role explosion.**

### Evaluation

| Axis | RBAC | ABAC |
|------|------|------|
| Simplicity | ✓ Simple roles | Complex rules |
| "Own resources only" | ✗ Can't express | ✓ `resource.owner == user.id` |
| Department isolation | ✗ Needs per-dept roles | ✓ `resource.dept == user.dept` |
| Classification levels | ✗ Needs per-level roles | ✓ `user.clearance >= resource.level` |
| Auditing | Easy (list role members) | Complex (trace rule evaluation) |
| Debugging | Clear (role has/doesn't have permission) | Hard ("which rule denied?") |
| Role explosion | ✗ At scale | N/A |

### The role explosion problem
```
Simple RBAC: 3 roles (admin, editor, viewer)

Enterprise RBAC:
  admin, editor, viewer,
  editor-finance, editor-engineering, editor-hr,
  editor-finance-confidential, editor-engineering-confidential,
  editor-finance-own-only, editor-engineering-own-only,
  viewer-finance, viewer-engineering, viewer-hr,
  ...
  → 50+ roles, unmanageable!

ABAC: 5 rules handle all of the above
```

### Best practice: hybrid approach
```python
def check_permission(user, action, resource):
    # Layer 1: RBAC base permissions
    base_allowed = action in ROLES.get(user.role, [])
    if not base_allowed:
        return False

    # Layer 2: ABAC refinements
    if resource.classification == "confidential" and user.clearance_level < 3:
        return False
    if action in ("write", "delete") and resource.owner_id != user.id:
        if not user.is_department_head:
            return False
        if resource.department != user.department:
            return False

    return True
```

### The reasoning pattern
Access control complexity should match organizational complexity. Small teams with flat structure → RBAC is sufficient. Enterprises with departments, clearance levels, and resource ownership → ABAC or hybrid. Start simple (RBAC), add attribute-based rules when you encounter access patterns that RBAC can't express without role explosion.'''
    ),
    (
        "thinking/meta-reasoning-typed-vs-untyped-python",
        r'''Compare these approaches for a Python codebase:

No type hints:
```python
def process_order(order, discount_code=None):
    total = sum(item['price'] * item['qty'] for item in order['items'])
    if discount_code:
        discount = get_discount(discount_code)
        total *= (1 - discount)
    return {'total': round(total, 2), 'items': len(order['items'])}
```

Full type hints:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class OrderItem:
    product_id: int
    price: float
    qty: int

@dataclass
class Order:
    items: list[OrderItem]
    customer_id: int

@dataclass
class OrderResult:
    total: float
    item_count: int

def process_order(order: Order, discount_code: Optional[str] = None) -> OrderResult:
    total = sum(item.price * item.qty for item in order.items)
    if discount_code:
        discount: float = get_discount(discount_code)
        total *= (1 - discount)
    return OrderResult(total=round(total, 2), item_count=len(order.items))
```

Is the typing overhead worth it?''',
        r'''<think>
Let me evaluate for a production Python codebase.

**Untyped:**
Pros:
- Less code
- Faster to write initially
- More flexible (duck typing)
- Pythonic "ask forgiveness not permission"

Cons:
- No IDE autocomplete for function parameters
- No compile-time error checking
- `order['items']` could be misspelled as `order['itmes']` → runtime KeyError
- Must read implementation to understand expected input
- Documentation: must write docstrings to explain parameter shapes
- Refactoring: changing structure requires finding all callers manually

**Typed:**
Pros:
- IDE autocomplete: `order.` shows all available fields
- mypy catches errors before runtime: wrong field name, wrong type
- Self-documenting: signature tells you exactly what to pass
- Refactoring: rename a field → mypy shows all places that need updating
- Dataclasses: validation, immutability, __eq__, __repr__ for free

Cons:
- More code upfront (dataclass definitions)
- Type hints can be verbose for complex types
- Runtime doesn't enforce types (mypy is static analysis only)
- Learning curve for advanced types (Generic, Protocol, TypeVar)

**For production code:**
The typed version catches more bugs, is easier to maintain, and serves as documentation. The extra code for dataclasses is a one-time cost that pays off across every function that uses them.

**Winner:** Typed, for any production codebase beyond a quick script. The typing overhead is an investment that reduces bugs, improves IDE support, and makes refactoring safer.

BUT: don't type EVERYTHING. Focus types on:
- Function signatures (parameters and return types)
- Data structures (dataclasses for domain objects)
- Complex logic (where type errors are likely)

Skip types for:
- Local variables (mypy infers them)
- Simple scripts
- Test code (usually)
</think>

**Type hints are worth it for production code — they catch bugs before runtime, enable IDE support, and serve as documentation.**

### Evaluation

| Axis | Untyped | Typed |
|------|---------|-------|
| Bug detection | Runtime only | mypy + runtime |
| IDE autocomplete | Limited | Full (fields, methods) |
| Documentation | Must write separately | Self-documenting |
| Refactoring safety | Must find callers manually | mypy shows all breakages |
| Code volume | Less | ~30% more (upfront) |
| Development speed (initial) | Faster | Slightly slower |
| Development speed (ongoing) | Slower (debugging) | Faster (fewer bugs) |

### What typing catches
```python
# Untyped: these bugs are only caught at RUNTIME
order['itmes']           # KeyError (typo in key)
process_order("not_an_order")  # AttributeError later
item.pice * item.qty     # AttributeError (typo in field)

# Typed: caught by mypy BEFORE running
order.itmes              # error: "Order" has no attribute "itmes"
process_order("not_an_order")  # error: expected Order, got str
item.pice * item.qty     # error: "OrderItem" has no attribute "pice"
```

### The pragmatic approach: type where it matters
```python
# DO type: function signatures, data structures
def process_order(order: Order, discount: str | None = None) -> OrderResult: ...

# DO type: complex data structures
@dataclass
class Order:
    items: list[OrderItem]
    customer_id: int

# DON'T type: obvious local variables (mypy infers)
total = 0.0  # mypy knows this is float
items = []   # mypy infers list type from usage

# DON'T type: simple scripts and one-off scripts
```

### The reasoning pattern
Type systems trade upfront verbosity for long-term safety. For short-lived scripts, types aren't worth it. For production codebases that are maintained for years by multiple developers, types pay for themselves quickly by preventing bugs, enabling refactoring, and eliminating "what does this function expect?" questions. Focus typing on boundaries (function signatures, data structures) where the cost-benefit ratio is highest.'''
    ),
    (
        "thinking/meta-reasoning-queue-vs-cron",
        r'''For processing email notifications asynchronously, compare:

Task queue (Celery):
```python
from celery import Celery

app = Celery('tasks', broker='redis://localhost:6379')

@app.task
def send_notification_email(user_id, template, data):
    user = get_user(user_id)
    html = render_template(template, **data)
    send_email(user.email, html)

# Usage: called from web request
send_notification_email.delay(user.id, "welcome", {"name": user.name})
```

Cron job:
```python
# run_notifications.py — runs every minute via cron
def process_pending_notifications():
    pending = db.query(Notification).filter(
        Notification.status == 'pending'
    ).limit(100).all()

    for notification in pending:
        user = get_user(notification.user_id)
        html = render_template(notification.template, **notification.data)
        send_email(user.email, html)
        notification.status = 'sent'
        db.commit()
```

Which is better for sending notification emails?''',
        r'''<think>
For sending notification emails asynchronously.

**Task queue (Celery):**
Pros:
- Near-instant: task picked up within milliseconds of dispatch
- Scalable: add more workers for more throughput
- Retry logic built-in: automatic retry on failure
- Priority queues: urgent notifications processed first
- Result tracking: know when task completed
- Composable: chain tasks, fan-out, callbacks

Cons:
- Infrastructure: need Redis/RabbitMQ broker + worker processes
- Complexity: another service to deploy and monitor
- Debugging: tasks run in separate process (harder to debug)
- Worker management: must keep workers running (supervisor/systemd)

**Cron job:**
Pros:
- Simple: just a script that runs periodically
- No infrastructure: runs on existing server
- Easy to understand and debug
- Database-backed: notifications are persisted (survives restarts)

Cons:
- Latency: up to 60 seconds delay (cron interval)
- Batching: processes 100 at a time, may fall behind
- No parallelism: single process (unless you add complexity)
- No retry: failed emails need manual re-processing
- No priority: all notifications processed in order

**For notification emails:**
- Welcome emails: users expect within seconds → Celery
- Daily digest: can wait → Cron
- Password reset: users expect immediately → Celery
- Marketing emails: scheduled → Cron

Most user-triggered notifications need near-instant delivery. Cron's 60-second delay is noticeable and unprofessional.

**Winner:** Celery for user-triggered notifications. Cron for batch/scheduled operations. Many systems use both.
</think>

**Celery for user-triggered notifications (need near-instant delivery), cron for batch/scheduled jobs. Most apps need both.**

### Evaluation

| Axis | Task queue (Celery) | Cron job |
|------|-------------------|---------|
| Latency | Milliseconds | Up to 60 seconds |
| Retry on failure | Built-in (auto-retry) | Must implement |
| Scalability | Add workers | Single process |
| Infrastructure | Redis/RabbitMQ + workers | None extra |
| Complexity | Medium | Low |
| Priority handling | Priority queues | First-come only |
| Throughput | Parallel workers | Sequential |

### The latency difference users notice
```
Celery: User signs up → welcome email in <1 second ✓
Cron:   User signs up → welcome email in up to 60 seconds ✗

Celery: User resets password → token email in <1 second ✓
Cron:   User resets password → waiting... waiting... up to 60s ✗
```

### Best practice: use both
```python
# Celery: user-triggered, needs to be fast
@celery.task(max_retries=3, default_retry_delay=60)
def send_welcome_email(user_id):
    # ...

@celery.task
def send_password_reset(user_id, token):
    # ...

# Cron: batch/scheduled, can be slow
# 0 8 * * * python manage.py send_daily_digest
# 0 * * * * python manage.py retry_failed_notifications
```

### The reasoning pattern
Async processing strategy depends on latency requirements. Real-time notifications (user-triggered) → task queue. Batch processing (reports, digests, cleanup) → cron/scheduled jobs. Don't use cron for user-facing async operations where latency matters, and don't use a full task queue for simple periodic jobs.'''
    ),
    (
        "thinking/meta-reasoning-grpc-vs-rest-microservices",
        r'''For communication between internal microservices, compare:

REST:
```python
# Service A calls Service B
response = requests.post(
    "http://user-service:8080/api/users",
    json={"name": "Alice", "email": "alice@test.com"}
)
user = response.json()
```

gRPC:
```protobuf
// user.proto
service UserService {
    rpc CreateUser (CreateUserRequest) returns (User);
}
message CreateUserRequest {
    string name = 1;
    string email = 2;
}
message User {
    int32 id = 1;
    string name = 2;
    string email = 3;
}
```
```python
# Service A calls Service B
response = user_stub.CreateUser(
    user_pb2.CreateUserRequest(name="Alice", email="alice@test.com")
)
```

Which is better for internal microservice communication?''',
        r'''<think>
For INTERNAL microservice communication (not external/public).

**REST:**
Pros:
- Universal: every language, tool, and developer knows REST
- Human-readable: JSON is easy to debug (curl, browser, Postman)
- Flexible: easy to add fields, versioning
- Simple: no code generation, no proto files

Cons:
- Text-based (JSON): larger payloads, slower serialization
- No schema enforcement: callers can send wrong types
- HTTP overhead: headers, content negotiation
- No streaming (without additional setup)
- No type safety across services

**gRPC:**
Pros:
- Binary protocol (protobuf): 5-10x smaller payloads, faster serialization
- Schema-defined (proto files): type safety across services
- Code generation: client/server stubs auto-generated
- Streaming: bidirectional streaming built-in
- HTTP/2: multiplexing, header compression
- Performance: significantly faster than REST for high-throughput

Cons:
- Not human-readable: binary format, can't curl
- Proto file management: must share and version .proto files
- Tooling: less universal than REST tooling
- Learning curve: protobuf, code generation, gRPC concepts
- Browser support: limited (needs grpc-web proxy)

**For internal microservice communication:**
- Services talk to each other frequently (high throughput)
- Schema enforcement prevents integration bugs
- Performance matters for service-to-service calls
- Not exposed to external developers (human readability less important)
- Binary protocol reduces network bandwidth between services

**Winner:** gRPC for internal microservice communication where performance and type safety matter. REST for external/public APIs. Many systems use gRPC internally and REST externally.
</think>

**gRPC for internal services — the type safety, performance, and streaming capabilities justify the complexity for service-to-service communication.**

### Evaluation

| Axis | REST (JSON/HTTP) | gRPC (protobuf/HTTP2) |
|------|-----------------|----------------------|
| Payload size | Larger (JSON text) | 5-10x smaller (binary) |
| Serialization speed | Slower | 5-10x faster |
| Type safety | None (JSON has no schema) | Full (proto schema) |
| Code generation | Manual | Auto-generated stubs |
| Streaming | Awkward (SSE/WebSocket) | Native bidirectional |
| Human readability | ✓ (curl-friendly) | ✗ (binary) |
| Debugging | Easy (JSON in browser) | Needs special tools |
| Browser support | ✓ Native | ✗ (needs proxy) |
| Learning curve | Low | Medium |

### Performance comparison (1000 req/sec)
```
REST/JSON:
  Serialization: ~50μs per message
  Payload: ~500 bytes
  Network: 500KB/sec
  Total latency: ~5ms per call

gRPC/protobuf:
  Serialization: ~5μs per message
  Payload: ~50 bytes
  Network: 50KB/sec
  Total latency: ~1ms per call
```

### The pattern: gRPC inside, REST outside
```
[Mobile App] → REST/JSON → [API Gateway]
                              ↓
[Web App]   → REST/JSON → [API Gateway]
                              ↓ gRPC
                         [User Service] ←gRPC→ [Order Service]
                              ↓ gRPC
                         [Payment Service] ←gRPC→ [Notification Service]
```

### When REST is better for internal
- Small team (< 5 services, gRPC overhead not justified)
- Low throughput (REST performance is fine)
- Debugging priority (need to inspect payloads easily)
- Team unfamiliar with gRPC

### The reasoning pattern
Internal service communication has different requirements than external APIs. Externally: human readability, discoverability, and simplicity matter. Internally: type safety, performance, and streaming matter. Choose the protocol that matches the communication boundary: REST for human-facing, gRPC for machine-to-machine.'''
    ),
    (
        "thinking/meta-reasoning-password-manager-vs-env",
        r'''For managing secrets in a production deployment, compare:

Environment variables:
```bash
export DATABASE_URL="postgres://user:pass@db.prod.com/myapp"
export API_KEY="sk_live_abc123"
export JWT_SECRET="super-secret-key"
```

Secret manager (AWS Secrets Manager):
```python
import boto3
import json

client = boto3.client('secretsmanager')

def get_secret(name):
    response = client.get_secret_value(SecretId=name)
    return json.loads(response['SecretString'])

db_config = get_secret('myapp/database')
api_key = get_secret('myapp/api-key')
```

Which is better for production secrets?''',
        r'''<think>
For production secret management.

**Environment variables:**
Pros:
- Simple: set in deployment config, read with `os.environ`
- 12-Factor compliant
- No additional service dependency
- Works everywhere

Cons:
- Visible to any process: `ps aux` or `/proc/*/environ` can expose them
- No audit trail: no record of who accessed what secret
- No rotation: changing a secret requires redeploying all services
- No encryption at rest: secrets stored in plain text in deployment config
- Leaked in logs: libraries might log env vars accidentally
- No versioning: can't roll back to previous secret value

**Secret manager (AWS Secrets Manager, Vault, etc.):**
Pros:
- Encrypted at rest: secrets stored encrypted
- Audit trail: every access is logged
- Rotation: automatic key rotation possible
- Access control: IAM policies control who can read which secrets
- Versioning: can roll back to previous secret versions
- Cross-service: centralized secret management
- Dynamic secrets: generate temporary credentials on demand

Cons:
- Additional service dependency (if it's down, your app can't get secrets)
- Network latency: API call to retrieve secrets
- Cost: AWS Secrets Manager is $0.40/secret/month
- Complexity: more infrastructure to manage
- Cold start: first request needs secret fetch

**For production:**
At scale, the audit trail, rotation, and access control of a secret manager become essential:
- "Who accessed the database password?" → audit log
- "Database password was leaked" → rotate without redeploying
- "New employee starts" → grant access via IAM, not sharing env files

**Winner:** Secret manager for production at any meaningful scale. Environment variables for development and small projects.
</think>

**Secret managers are better for production — they provide audit trails, rotation, and access control that environment variables can't.**

### Evaluation

| Axis | Environment variables | Secret manager |
|------|----------------------|----------------|
| Encryption at rest | ✗ (plain text) | ✓ (encrypted) |
| Audit trail | ✗ | ✓ (every access logged) |
| Secret rotation | Requires redeploy | Automatic, no downtime |
| Access control | All-or-nothing (if on server) | Per-secret IAM policies |
| Versioning | ✗ | ✓ (rollback possible) |
| Complexity | Zero | Medium |
| Cost | Free | ~$0.40/secret/month |
| Dependencies | None | Cloud service |

### The rotation problem
```bash
# Environment variables: rotate database password
1. Change password in database
2. Update env var in ALL deployment configs
3. Restart ALL services (downtime!)
4. Hope you didn't miss any service

# Secret manager: rotate database password
1. Update secret in Secrets Manager
2. Services fetch new value on next request
3. Zero downtime, zero coordination
```

### The audit problem
```
"Someone leaked our API key. Who had access?"

Env vars: "Uh... anyone with SSH access to any server? All CI/CD logs?"
Secret Manager: "Here's the audit log — 3 services and 2 developers accessed it in the last 30 days."
```

### When env vars are fine
- Local development
- Small projects (1-2 services)
- Non-sensitive configuration
- Short-lived deployments (dev/staging)

### The reasoning pattern
Secret management strategy should match the risk profile. Small personal projects → env vars are fine. Production systems with multiple services, compliance requirements, or sensitive data → secret managers provide the audit, rotation, and access control that env vars can't. The $0.40/secret/month cost is negligible compared to the cost of a secret management incident.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
