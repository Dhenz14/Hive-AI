"""Phase 1D: Foundation Thinking — Architecture & Design (Part 1/4)
System design, microservices, API design, distributed systems basics."""

PAIRS = [
    (
        "thinking/arch-monolith-to-microservices",
        "Our monolithic Django app has 200K lines of code. Deployments take 45 minutes, one bug in the payment module brought down the entire app, and teams step on each other's code. Management wants to 'go microservices.' What should we actually do?",
        r'''<think>
Let me think about this carefully rather than jumping to "yes, microservices."

**Current pain points:**
1. Long deployments (45 min)
2. Single point of failure (payment bug → whole app down)
3. Team coupling (stepping on each other's code)

**Would microservices solve these?**
1. Deployments: Yes, smaller services deploy faster independently
2. Fault isolation: Yes, payment service failure doesn't bring down user auth
3. Team independence: Yes, teams own their services

**But microservices introduce NEW problems:**
1. Network calls instead of function calls → latency, failure modes
2. Distributed transactions → eventual consistency, saga patterns
3. Service discovery, load balancing, circuit breakers
4. Debugging is 10x harder (distributed tracing needed)
5. Data consistency across services
6. Operational overhead: deploy pipelines × N, monitoring × N, on-call × N
7. Testing is much harder (integration tests across services)

**For a 200K line Django app, the right progression is:**
1. First: modularize the monolith (Django apps with clean boundaries)
2. Then: identify the modules with DIFFERENT scaling/deployment needs
3. Extract only those as services
4. Keep everything else as a well-structured monolith

**The "Strangler Fig" approach:**
Don't rewrite. Gradually extract services around the monolith, one at a time.

**What should be extracted first?**
- Payment: critical, needs fault isolation, different compliance requirements
- Maybe: notification system (can be async, different scaling profile)
- NOT: user auth (everything depends on it — extracting it creates coupling)
</think>

Don't do a big-bang rewrite to microservices. That's the #1 way companies waste years of engineering effort. Here's the pragmatic approach:

## Phase 1: Modularize the Monolith (Weeks, Not Months)

```
myapp/
├── core/           # Shared models, auth, middleware
├── payments/       # Clean interface, no direct imports from other modules
├── orders/         # Depends on payments via defined interface
├── notifications/  # Async, loosely coupled
├── catalog/        # Product data
└── users/          # Auth, profiles
```

Define **explicit interfaces** between Django apps:
```python
# payments/services.py — the ONLY way other modules interact with payments
class PaymentService:
    def charge(self, user_id: int, amount: Decimal, idempotency_key: str) -> PaymentResult:
        ...
    def refund(self, payment_id: str) -> RefundResult:
        ...

# orders/views.py — uses the interface, not internal payment models
from payments.services import PaymentService

def create_order(request):
    payment = PaymentService().charge(
        user_id=request.user.id,
        amount=order.total,
        idempotency_key=f'order-{order.id}',
    )
```

## Phase 2: Extract What NEEDS Extraction (Months)

Only extract services that have **different operational requirements**:

| Module | Extract? | Reason |
|--------|----------|--------|
| Payments | Yes | Fault isolation, PCI compliance, independent scaling |
| Notifications | Yes | Async, different scaling profile, can lag |
| User Auth | No | Everything depends on it — keep in monolith |
| Catalog | Maybe later | Only if read scaling is needed |
| Orders | No | Tightly coupled to everything else |

## Phase 3: Strangler Fig Migration

```
[Client] → [API Gateway]
                ├── /api/payments/* → Payment Service (new)
                ├── /api/notifications/* → Notification Service (new)
                └── /* → Monolith (everything else)
```

Extract one service at a time. The monolith shrinks gradually. If an extraction goes wrong, the route falls back to the monolith.

**The rule: microservices are a solution to organizational scaling problems, not technical ones.** If you have 3 teams, you need at most 3-5 services, not 50.'''
    ),
    (
        "thinking/arch-event-driven-vs-request-response",
        "An e-commerce system processes orders. When an order is placed, it needs to: (1) charge payment, (2) update inventory, (3) send confirmation email, (4) update analytics, (5) notify the warehouse. Currently all 5 operations are in one synchronous API call that takes 3 seconds. Design a better architecture.",
        r'''<think>
Currently: one synchronous call does all 5 operations sequentially. Problems:
- Slow (3 seconds for the user to wait)
- One failure blocks everything (email service down → order fails)
- Tightly coupled (order service knows about email, analytics, warehouse)
- Can't scale operations independently

**Which operations MUST be synchronous?**
- Payment: YES — user needs to know if payment succeeded
- Inventory: YES — need to confirm stock is available before charging

**Which can be asynchronous?**
- Email: Can be sent seconds later
- Analytics: Can be processed later
- Warehouse notification: Can be queued

**Architecture: Synchronous for critical path, events for the rest**

1. Order API synchronously charges payment + reserves inventory
2. On success, publishes an "OrderPlaced" event
3. Independent consumers handle email, analytics, warehouse

This is the event-driven approach. Benefits:
- User gets response in <500ms (only payment + inventory)
- Email service outage doesn't affect orders
- New consumers can be added without changing the order service
- Each consumer scales independently
</think>

## Architecture: Sync Critical Path + Async Events

```
User → Order API → [1. Charge Payment] ← Synchronous (user waits)
                  → [2. Reserve Inventory] ← Synchronous
                  → [3. Publish "OrderPlaced" event] ← Async
                  → Response: "Order confirmed!"

"OrderPlaced" Event →  [Email Consumer]     → Send confirmation
                    →  [Analytics Consumer]  → Update dashboards
                    →  [Warehouse Consumer]  → Create pick list
                    →  [Future Consumer]     → (add without code change)
```

## Implementation

```python
# Order service — only does what the user must wait for
@app.route('/api/orders', methods=['POST'])
async def create_order(request):
    order = Order.from_request(request)

    # Synchronous: user must wait for these
    payment = await payment_service.charge(order.user_id, order.total)
    if not payment.success:
        return jsonify(error='Payment failed'), 402

    inventory = await inventory_service.reserve(order.items)
    if not inventory.success:
        await payment_service.refund(payment.id)
        return jsonify(error='Out of stock'), 409

    order.save()

    # Asynchronous: publish event, don't wait for consumers
    await event_bus.publish('OrderPlaced', {
        'order_id': order.id,
        'user_id': order.user_id,
        'items': order.items,
        'total': order.total,
    })

    return jsonify(order_id=order.id), 201  # ~500ms instead of 3s

# Email consumer — independent, can fail without affecting orders
@consumer('OrderPlaced')
async def send_confirmation(event):
    user = await user_service.get(event['user_id'])
    await email.send(
        to=user.email,
        template='order_confirmation',
        data=event,
    )

# Analytics consumer — independent
@consumer('OrderPlaced')
async def update_analytics(event):
    await analytics.track('purchase', amount=event['total'])

# Warehouse consumer — independent
@consumer('OrderPlaced')
async def notify_warehouse(event):
    await warehouse.create_pick_list(event['order_id'], event['items'])
```

**Response time:** 3s → 500ms
**Coupling:** Order service doesn't know about email, analytics, or warehouse
**Resilience:** Email outage doesn't block orders
**Extensibility:** Add new consumers (fraud detection, loyalty points) without changing order code'''
    ),
    (
        "thinking/arch-api-gateway-pattern",
        "Our mobile app makes 7 API calls to different microservices on every screen load. Each call has auth overhead, and the chatty protocol causes poor performance on mobile networks:\n\n```javascript\n// Mobile app — 7 parallel HTTP calls per screen\nconst [user, orders, recommendations, notifications, \n       cart, wishlist, recentlyViewed] = await Promise.all([\n    fetch('/api/users/me'),\n    fetch('/api/orders?limit=5'),\n    fetch('/api/recommendations'),\n    fetch('/api/notifications/unread'),\n    fetch('/api/cart'),\n    fetch('/api/wishlist'),\n    fetch('/api/recently-viewed'),\n]);\n```\n\nDesign a better approach.",
        r'''<think>
Problems with chatty API from mobile:
1. 7 HTTP connections — each has TCP + TLS handshake overhead
2. Each request carries auth headers, cookies, etc.
3. Mobile networks have high latency — 7 sequential round trips if not HTTP/2
4. If any one call fails, the screen is partially broken
5. Over-fetching — mobile probably doesn't need all fields from each endpoint

Solutions:
1. BFF (Backend for Frontend) — aggregate calls server-side
2. GraphQL — client specifies exactly what it needs
3. API Gateway with request aggregation
</think>

## Solution: BFF (Backend for Frontend)

A server-side aggregation layer that combines multiple service calls into one optimized response for each client type:

```python
# BFF endpoint — one call returns everything the mobile home screen needs
@app.route('/api/mobile/home')
@login_required
async def mobile_home():
    user_id = current_user.id

    # Server-side parallel calls (fast internal network, not mobile network)
    user, orders, recs, notifs, cart, wishlist, recent = await asyncio.gather(
        user_service.get_profile(user_id),
        order_service.get_recent(user_id, limit=5),
        rec_service.get_for_user(user_id, limit=10),
        notif_service.get_unread_count(user_id),
        cart_service.get_summary(user_id),
        wishlist_service.get_count(user_id),
        recently_viewed.get(user_id, limit=8),
    )

    # Return only what mobile needs (trimmed fields)
    return jsonify({
        'user': {'name': user.name, 'avatar': user.avatar_url},
        'recent_orders': [{'id': o.id, 'status': o.status, 'total': o.total} for o in orders],
        'recommendations': [{'id': r.id, 'name': r.name, 'image': r.image} for r in recs],
        'unread_notifications': notifs,
        'cart_count': cart.item_count,
        'wishlist_count': wishlist,
        'recently_viewed': [{'id': r.id, 'image': r.image} for r in recent],
    })
```

```javascript
// Mobile app — ONE call
const homeData = await fetch('/api/mobile/home');
```

**Before:** 7 HTTP calls over mobile network (~200ms latency each) = 1.4s+
**After:** 1 HTTP call over mobile (~200ms) + server parallel calls (~50ms) = 250ms

**Benefits:**
- **One round trip** instead of seven
- **Trimmed responses** — mobile gets only the fields it needs
- **Server-side resilience** — BFF can return partial data if one service is slow
- **Separate BFFs** for mobile vs web vs partner API — each optimized for its client'''
    ),
    (
        "thinking/arch-cqrs-read-write-separation",
        "Our application has very different read and write patterns. Writes are complex business logic (validations, calculations, event publishing). Reads are simple but need to join 5 tables and serve 100x more traffic than writes. The same model serves both:\n\n```python\nclass Order(db.Model):\n    # 30 columns, complex relationships\n    id = db.Column(db.Integer, primary_key=True)\n    user_id = db.Column(db.ForeignKey('users.id'))\n    items = db.relationship('OrderItem', backref='order')\n    payments = db.relationship('Payment', backref='order')\n    # ... 25 more columns and relationships\n\n# Write: complex validation and business logic\ndef create_order(data):\n    # 200 lines of validation, inventory checks, payment, events\n    ...\n\n# Read: simple query but needs 5 JOINs, called 100x more\ndef get_order_summary(order_id):\n    return Order.query.options(\n        joinedload('items'),\n        joinedload('items.product'),\n        joinedload('payments'),\n        joinedload('user'),\n    ).get(order_id)\n```",
        r'''<think>
The problem: one model serves both complex writes and high-volume reads. The read model needs JOINs across 5 tables on every request. The write model has complex business logic that makes the read model bloated.

CQRS (Command Query Responsibility Segregation) separates the write model (commands) from the read model (queries). The write side handles business logic with a normalized model. The read side has denormalized views optimized for queries.

This is valuable when:
- Reads and writes have very different patterns (100:1 ratio)
- Read queries require complex JOINs
- Write logic is complex and benefits from a rich domain model
- Read and write models need to scale independently
</think>

## CQRS: Separate Read and Write Models

### Write Side (Commands)
```python
# Rich domain model with business logic
class OrderAggregate:
    def create(self, user_id, items, payment_method):
        # Complex validation
        self._validate_inventory(items)
        self._validate_user_credit(user_id)
        self._calculate_taxes(items)
        self._apply_discounts(items)

        # Persist to normalized tables
        order = Order(user_id=user_id, status='pending', ...)
        for item in items:
            order.items.append(OrderItem(product_id=item.id, ...))
        db.session.add(order)

        # Charge payment
        payment = PaymentService.charge(user_id, order.total)
        order.payments.append(payment)

        db.session.commit()

        # Publish event to update read model
        event_bus.publish('OrderCreated', order.to_event())
        return order.id
```

### Read Side (Queries)
```python
# Denormalized read model — one table, no JOINs
class OrderSummaryView(db.Model):
    __tablename__ = 'order_summaries'  # Materialized/denormalized table
    order_id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String)
    user_email = db.Column(db.String)
    item_count = db.Column(db.Integer)
    total = db.Column(db.Numeric)
    status = db.Column(db.String)
    items_json = db.Column(db.JSON)  # Pre-serialized items
    created_at = db.Column(db.DateTime)

# Read: single table lookup, no JOINs, <1ms
def get_order_summary(order_id):
    return OrderSummaryView.query.get(order_id)

# Event handler keeps read model in sync
@consumer('OrderCreated')
def update_order_summary(event):
    summary = OrderSummaryView(
        order_id=event['order_id'],
        user_name=event['user_name'],
        item_count=len(event['items']),
        total=event['total'],
        status='confirmed',
        items_json=event['items'],
    )
    db.session.merge(summary)
    db.session.commit()
```

**Benefits:**
- Reads: 1 table, 0 JOINs, scales to millions of reads
- Writes: rich domain model, complex logic is clean
- Scale independently: read replicas for queries, write optimized for consistency
- Read model is eventually consistent (typically <100ms lag)'''
    ),
    (
        "thinking/arch-circuit-breaker-pattern",
        "When our payment service goes down, our order service keeps trying to call it, causing cascading timeouts across the entire system. Orders queue up, memory fills, and eventually all services crash. Design a resilience pattern.",
        r'''<think>
Cascading failure pattern:
1. Payment service goes down
2. Order service calls payment, waits for timeout (5-30 seconds)
3. Thread/connection pool fills with waiting requests
4. Order service can't process any requests (even non-payment ones)
5. Services that depend on order service start timing out
6. Cascade continues until everything is down

The circuit breaker pattern prevents this by "breaking the circuit" when a service is failing. Like an electrical circuit breaker — it trips to prevent damage.

States: CLOSED (normal), OPEN (failing, reject immediately), HALF-OPEN (testing recovery)
</think>

## Circuit Breaker Pattern

```python
import time
import threading
from enum import Enum
from dataclasses import dataclass, field

class State(Enum):
    CLOSED = "closed"        # Normal — requests flow through
    OPEN = "open"            # Tripped — fail immediately
    HALF_OPEN = "half_open"  # Testing — allow one probe request

@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5        # Failures before opening
    recovery_timeout: float = 30.0    # Seconds before trying again
    success_threshold: int = 3        # Successes to close from half-open

    _state: State = State.CLOSED
    _failure_count: int = 0
    _success_count: int = 0
    _last_failure_time: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def call(self, func, *args, fallback=None, **kwargs):
        with self._lock:
            if self._state == State.OPEN:
                if time.time() - self._last_failure_time > self.recovery_timeout:
                    self._state = State.HALF_OPEN
                    self._success_count = 0
                else:
                    if fallback:
                        return fallback()
                    raise CircuitOpenError(f'{self.name} circuit is OPEN')

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            if fallback:
                return fallback()
            raise

    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            if self._state == State.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = State.CLOSED  # Recovered!

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = State.OPEN

# Usage
payment_breaker = CircuitBreaker('payment-service', failure_threshold=5)

def create_order(order_data):
    try:
        payment = payment_breaker.call(
            payment_service.charge,
            order_data['amount'],
            fallback=lambda: QueuedPayment(order_data),  # Graceful degradation
        )
    except CircuitOpenError:
        # Payment service is down — queue the order for later processing
        return queue_order_for_retry(order_data)

    return confirm_order(order_data, payment)
```

**The three states:**
1. **CLOSED** — requests flow normally. Failures counted.
2. **OPEN** — all requests fail immediately (no waiting for timeout). After recovery_timeout, transitions to HALF-OPEN.
3. **HALF-OPEN** — allows a few probe requests. If they succeed, circuit closes. If they fail, circuit opens again.

**Without circuit breaker:** Payment down → 1000 threads waiting 30s each → memory exhaustion → cascade
**With circuit breaker:** Payment down → 5 failures → circuit opens → instant failure response → system stays healthy'''
    ),
    (
        "thinking/arch-saga-pattern-distributed-transactions",
        "An order process spans 3 services: Payment, Inventory, and Shipping. If shipping fails after payment and inventory succeed, how do we handle the rollback? We can't use a database transaction across services.",
        r'''<think>
Distributed transactions across microservices. Traditional 2-phase commit (2PC) doesn't work well in microservices — it's slow, requires all services to be available, and creates tight coupling.

The Saga pattern manages distributed transactions as a sequence of local transactions, each with a compensating action (undo).

Two types:
1. Choreography: services publish events, each reacts independently
2. Orchestration: a central coordinator tells each service what to do

For an order process, orchestration is usually cleaner because it's easier to reason about the flow and handle compensations.
</think>

## Saga Pattern with Orchestration

```python
class OrderSaga:
    """Orchestrates the distributed order process with compensations."""

    def __init__(self, order_data):
        self.order_data = order_data
        self.payment_id = None
        self.reservation_id = None
        self.shipment_id = None

    async def execute(self):
        try:
            # Step 1: Charge payment
            self.payment_id = await payment_service.charge(
                self.order_data['user_id'],
                self.order_data['total'],
            )

            # Step 2: Reserve inventory
            self.reservation_id = await inventory_service.reserve(
                self.order_data['items'],
            )

            # Step 3: Create shipment
            self.shipment_id = await shipping_service.create(
                self.order_data['address'],
                self.order_data['items'],
            )

            return {'status': 'completed', 'order_id': self.order_data['id']}

        except ShippingError:
            # Shipping failed — compensate steps 1 and 2
            await self._compensate_from('shipping')
            return {'status': 'failed', 'reason': 'Shipping unavailable'}

        except InventoryError:
            # Inventory failed — compensate step 1 only
            await self._compensate_from('inventory')
            return {'status': 'failed', 'reason': 'Out of stock'}

        except PaymentError:
            # Payment failed — nothing to compensate
            return {'status': 'failed', 'reason': 'Payment declined'}

    async def _compensate_from(self, failed_step):
        """Run compensating actions in reverse order."""
        compensations = {
            'shipping': [
                ('inventory', self._release_inventory),
                ('payment', self._refund_payment),
            ],
            'inventory': [
                ('payment', self._refund_payment),
            ],
        }

        for step_name, compensate_fn in compensations.get(failed_step, []):
            try:
                await compensate_fn()
            except Exception as e:
                # Compensation failed — log for manual intervention
                logger.error(f'Compensation failed for {step_name}: {e}')
                await alert_ops_team(self.order_data['id'], step_name, e)

    async def _refund_payment(self):
        if self.payment_id:
            await payment_service.refund(self.payment_id)

    async def _release_inventory(self):
        if self.reservation_id:
            await inventory_service.release(self.reservation_id)
```

**Saga flow:**
```
Success: Payment ✓ → Inventory ✓ → Shipping ✓ → Done
Ship fail: Payment ✓ → Inventory ✓ → Shipping ✗ → Release Inventory → Refund Payment
Inv fail:  Payment ✓ → Inventory ✗ → Refund Payment
Pay fail:  Payment ✗ → Done (nothing to compensate)
```

**Key principles:**
1. Each step has a **compensating action** (undo)
2. Compensations run in **reverse order**
3. Compensations must be **idempotent** (safe to retry)
4. Failed compensations trigger **alerts** for manual resolution'''
    ),
    (
        "thinking/arch-rate-limiter-design",
        "Design a rate limiter for an API that handles 10,000 requests/second across 20 server instances. Requirements: 100 requests per user per minute, fair across all servers, minimal latency impact.",
        r'''<think>
Requirements:
- 100 req/user/min across 20 servers
- Must be distributed (all servers share the same limits)
- Low latency (can't add >5ms to each request)
- 10K req/sec total throughput

Options:
1. Token bucket — smooth rate, allows bursts
2. Sliding window counter — accurate, simple
3. Sliding window log — most accurate, most memory

For distributed rate limiting, need a shared store. Redis is the standard choice:
- INCR + EXPIRE for fixed window (simple)
- Sorted set for sliding window log (accurate but memory-heavy)
- Lua script for atomic sliding window counter (best balance)

The sliding window counter is the best balance: accurate enough, low memory, atomic with Lua.
</think>

## Sliding Window Counter with Redis

```python
import time
import redis

r = redis.Redis()

# Lua script for atomic rate check (runs on Redis server — no race conditions)
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Remove entries outside the window
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current entries
local count = redis.call('ZCARD', key)

if count < limit then
    -- Under limit: add this request
    redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
    redis.call('EXPIRE', key, window)
    return {1, limit - count - 1}  -- allowed, remaining
else
    return {0, 0}  -- rejected, 0 remaining
end
"""

_script = None

def get_script():
    global _script
    if _script is None:
        _script = r.register_script(RATE_LIMIT_SCRIPT)
    return _script

def check_rate_limit(user_id: str, limit: int = 100, window: int = 60) -> tuple[bool, int]:
    """Returns (allowed, remaining_requests)."""
    key = f'ratelimit:{user_id}'
    now = time.time()

    result = get_script()(keys=[key], args=[window, limit, now])
    allowed = bool(result[0])
    remaining = int(result[1])
    return allowed, remaining

# Middleware
@app.before_request
def rate_limit():
    user_id = get_user_id_from_request()  # API key, IP, or user ID
    allowed, remaining = check_rate_limit(user_id)

    if not allowed:
        response = jsonify(error='Rate limit exceeded')
        response.status_code = 429
        response.headers['Retry-After'] = '60'
        response.headers['X-RateLimit-Remaining'] = '0'
        return response

    # Add headers to the eventual response
    @after_this_request
    def add_headers(response):
        response.headers['X-RateLimit-Limit'] = '100'
        response.headers['X-RateLimit-Remaining'] = str(remaining)
        return response
```

**Why sliding window counter:**
- **Atomic** — Lua script runs on Redis server, no race conditions
- **Distributed** — all 20 servers share the same Redis
- **Accurate** — sorted set provides true sliding window (not fixed windows)
- **Low latency** — single Redis call (~1ms)
- **Memory** — ~100 entries per user per minute, auto-cleaned'''
    ),
    (
        "thinking/arch-database-per-service",
        "Our microservices share one PostgreSQL database. Service A can read and modify Service B's tables directly. This causes tight coupling, schema migration conflicts, and one slow query from Service A locks tables that Service B needs. Should each service have its own database?",
        r'''<think>
Shared database between microservices is an anti-pattern because:
1. Services are coupled through the schema — changing a table affects multiple services
2. Schema migrations require coordinating all services
3. One service's expensive queries affect others (resource contention)
4. Services can bypass each other's business logic by directly modifying tables
5. Effectively, it's a distributed monolith with extra network hops

Database-per-service:
- Each service owns its data
- Communication through APIs, not shared tables
- But: cross-service queries become harder (no JOINs across services)
- Need to handle data duplication and eventual consistency
</think>

**Yes, but migrate incrementally.** A shared database between microservices is a distributed monolith — you get all the downsides of both architectures.

## Migration Strategy

### Step 1: Schema Ownership (No new code changes)
```sql
-- Assign schemas to services
CREATE SCHEMA orders_svc;
CREATE SCHEMA users_svc;
CREATE SCHEMA payments_svc;

-- Move tables to their owning schema
ALTER TABLE orders SET SCHEMA orders_svc;
ALTER TABLE users SET SCHEMA users_svc;
ALTER TABLE payments SET SCHEMA payments_svc;

-- Service B can't directly access Service A's tables
REVOKE ALL ON SCHEMA orders_svc FROM payments_service_user;
```

### Step 2: API Boundaries (Replace direct DB queries)
```python
# BEFORE: Payment service directly queries user table
def get_user_billing(user_id):
    return db.execute('SELECT * FROM users WHERE id = ?', (user_id,))

# AFTER: Payment service calls User service API
def get_user_billing(user_id):
    return user_service.get_billing_info(user_id)
```

### Step 3: Separate Databases (When ready)
```python
# Each service has its own connection
# Order Service
order_db = create_engine('postgresql://order-db/orders')

# User Service
user_db = create_engine('postgresql://user-db/users')

# For cross-service data needs: event-driven sync
@consumer('UserUpdated')
def sync_user_cache(event):
    # Payment service keeps a local cache of user billing info
    cache.set(f'user:{event["user_id"]}:billing', event['billing_info'])
```

**The key trade-off:** you lose cross-service JOINs. Replace them with:
1. **API calls** for real-time lookups
2. **Event-driven sync** for frequently accessed data
3. **Materialized views** in a read-only analytics DB for reporting'''
    ),
    (
        "thinking/arch-idempotency-design",
        "Payment processing occasionally double-charges customers when the network hiccups. The client retries after a timeout, but the first request actually succeeded:\n\n```\nClient → Payment API → [charge card] → Response lost → Client retries → [charge card AGAIN]\n```\n\nDesign an idempotent payment system.",
        r'''<think>
Idempotency means performing an operation multiple times produces the same result as performing it once. For payments: charge once, even if the request is sent 5 times.

The standard approach: idempotency keys. The client generates a unique key per intended operation. The server uses this key to detect and deduplicate retries.
</think>

## Idempotent Payment with Idempotency Keys

```python
@app.route('/api/payments', methods=['POST'])
def create_payment():
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify(error='Idempotency-Key header required'), 400

    # Check if this key was already processed
    existing = db.execute(
        'SELECT result FROM idempotency_keys WHERE key = ? AND user_id = ?',
        (idempotency_key, current_user.id)
    ).fetchone()

    if existing:
        # Return the SAME response as the first request
        return jsonify(json.loads(existing['result'])), 200

    # Lock the key to prevent concurrent duplicates
    try:
        db.execute(
            'INSERT INTO idempotency_keys (key, user_id, status, created_at) '
            'VALUES (?, ?, ?, NOW())',
            (idempotency_key, current_user.id, 'processing')
        )
        db.commit()
    except IntegrityError:
        # Another request with this key is being processed right now
        return jsonify(error='Request in progress'), 409

    try:
        # Process the payment (only happens ONCE per key)
        result = payment_processor.charge(
            user_id=current_user.id,
            amount=request.json['amount'],
            method=request.json['payment_method'],
        )

        # Store the result for future retries
        db.execute(
            'UPDATE idempotency_keys SET status = ?, result = ? WHERE key = ?',
            ('completed', json.dumps(result), idempotency_key)
        )
        db.commit()

        return jsonify(result), 201

    except Exception as e:
        # Allow retry if processing failed
        db.execute(
            'DELETE FROM idempotency_keys WHERE key = ?',
            (idempotency_key,)
        )
        db.commit()
        raise
```

```python
# Client side
import uuid

def charge_customer(amount):
    idempotency_key = str(uuid.uuid4())  # Unique per operation
    for attempt in range(3):
        try:
            resp = session.post('/api/payments', json={'amount': amount},
                              headers={'Idempotency-Key': idempotency_key})
            return resp.json()
        except Timeout:
            continue  # Retry with SAME key — server deduplicates
```

**Key design points:**
1. Client generates the key — same key for all retries of the same operation
2. Server stores the key + result — retries get the original response
3. Key is scoped to user — prevents cross-user conflicts
4. Failed operations delete the key — allows genuine retry
5. Keys expire after 24h — cleanup old entries'''
    ),
    (
        "thinking/arch-service-mesh-when",
        "Our team is adding Istio to our Kubernetes cluster because 'everyone uses service meshes.' We have 8 microservices and 3 developers. Is this the right decision?",
        r'''<think>
A service mesh (Istio, Linkerd) adds a sidecar proxy to every pod. It handles:
- mTLS between services
- Traffic routing and load balancing
- Circuit breaking
- Observability (distributed tracing, metrics)
- Rate limiting, retries

But it adds:
- Massive operational complexity
- 30-50% memory overhead per pod (Envoy sidecars)
- Latency overhead (extra network hop through proxy)
- Debugging difficulty (another layer to troubleshoot)
- Learning curve — Istio's configuration is notoriously complex

For 8 services and 3 developers? Almost certainly overkill. They'll spend more time managing the mesh than building features.

When IS a service mesh justified?
- 50+ services with complex routing needs
- Strict mTLS requirements across all services
- Multiple teams needing consistent observability
- Canary/blue-green deployments at service level
</think>

**No.** For 8 services and 3 developers, a service mesh is massive overkill. You'll spend more time managing Istio than building product.

## What You Actually Need vs What Istio Provides

| Need | Without Mesh | With Istio |
|------|-------------|------------|
| Service-to-service auth | Kubernetes NetworkPolicy + internal tokens | mTLS (automatic but complex config) |
| Observability | Prometheus + Grafana (you need this anyway) | Built-in (but still needs Prometheus) |
| Circuit breaking | Library-level (tenacity, httpx retry) | Envoy config YAML |
| Load balancing | Kubernetes Service (built-in) | Envoy (more features, more complexity) |

## The Cost of Istio

- **Memory:** +100-200MB per pod (Envoy sidecar × 8 services = 1.6GB)
- **Latency:** +2-5ms per hop (sidecar proxy)
- **Complexity:** Istio CRDs, VirtualServices, DestinationRules, PeerAuthentications
- **Debugging:** "Is the bug in my code, the sidecar, or the control plane?"
- **Upgrades:** Istio upgrades are notoriously painful

## What to Do Instead

```yaml
# Simple Kubernetes NetworkPolicy — restricts which services can talk
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-service
spec:
  podSelector:
    matchLabels:
      app: payment-service
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: order-service  # Only order-service can call payment
```

**Rule of thumb:** Consider a service mesh when you have 50+ services, 10+ teams, and dedicated platform engineers. For 8 services and 3 devs, use library-level patterns (retries, circuit breakers) and Kubernetes-native features.'''
    ),
    (
        "thinking/arch-caching-strategy-layers",
        "An e-commerce product page needs to load product details, reviews (from another service), pricing (dynamic), and inventory status. Each has different freshness requirements. Design a multi-layer caching strategy.",
        r'''<think>
Different data has different caching characteristics:
- Product details: changes rarely, cacheable for hours
- Reviews: changes occasionally, cacheable for minutes
- Pricing: changes frequently (flash sales), short cache or no cache
- Inventory: changes constantly (every purchase), very short cache or real-time

Need a multi-layer caching strategy:
1. CDN/Edge cache for static assets
2. Application-level cache (Redis) for shared data
3. In-process cache for hot data
4. Different TTLs per data type
</think>

## Multi-Layer Caching with Per-Data TTLs

```python
from cachetools import TTLCache
import redis
import json

# Layer 1: In-process cache (fastest, per-instance)
L1_CACHE = TTLCache(maxsize=1000, ttl=10)  # 10-second local cache

# Layer 2: Redis (shared across instances)
r = redis.Redis()

# Layer 3: Database (source of truth)

CACHE_CONFIG = {
    'product_details': {'l1_ttl': 60, 'l2_ttl': 3600},   # Rarely changes
    'reviews':         {'l1_ttl': 30, 'l2_ttl': 300},     # Changes occasionally
    'pricing':         {'l1_ttl': 5,  'l2_ttl': 30},      # Changes often
    'inventory':       {'l1_ttl': 2,  'l2_ttl': 10},      # Changes constantly
}

def cached_get(data_type: str, key: str, fetch_fn):
    config = CACHE_CONFIG[data_type]
    cache_key = f'{data_type}:{key}'

    # L1: In-process (0.001ms)
    if cache_key in L1_CACHE:
        return L1_CACHE[cache_key]

    # L2: Redis (1ms)
    cached = r.get(cache_key)
    if cached:
        data = json.loads(cached)
        L1_CACHE[cache_key] = data  # Populate L1
        return data

    # L3: Database/Service (50-200ms)
    data = fetch_fn()
    r.setex(cache_key, config['l2_ttl'], json.dumps(data))
    L1_CACHE[cache_key] = data
    return data

# Usage
def get_product_page(product_id):
    details = cached_get('product_details', product_id,
                         lambda: product_service.get(product_id))

    reviews = cached_get('reviews', product_id,
                         lambda: review_service.get(product_id))

    pricing = cached_get('pricing', product_id,
                         lambda: pricing_service.get(product_id))

    inventory = cached_get('inventory', product_id,
                           lambda: inventory_service.check(product_id))

    return {**details, 'reviews': reviews, 'price': pricing, 'stock': inventory}
```

**Cache invalidation on writes:**
```python
def update_product_price(product_id, new_price):
    db.update_price(product_id, new_price)
    # Invalidate cache — next read will fetch fresh data
    r.delete(f'pricing:{product_id}')
    # Also publish event for other instances' L1 caches
    r.publish('cache_invalidation', f'pricing:{product_id}')
```

**Freshness per data type:**
| Data | L1 TTL | L2 TTL | Staleness OK? |
|------|--------|--------|--------------|
| Product details | 60s | 1 hour | Yes — descriptions rarely change |
| Reviews | 30s | 5 min | Yes — new reviews appear within minutes |
| Pricing | 5s | 30s | Somewhat — flash sales need quick propagation |
| Inventory | 2s | 10s | Barely — overselling is bad |'''
    ),
    (
        "thinking/arch-12-factor-app-checklist",
        "We're deploying a new Python web app to Kubernetes. Review this setup against the Twelve-Factor App methodology and identify violations:\n\n```python\n# config.py\nDATABASE_URL = 'postgresql://user:pass@db.prod:5432/myapp'\nREDIS_URL = 'redis://cache.prod:6379'\nSECRET_KEY = 'hardcoded-secret-key-2024'\nLOG_FILE = '/var/log/myapp/app.log'\n\n# app.py\nimport logging\nfh = logging.FileHandler(LOG_FILE)  # Writes to local file\nlogger.addHandler(fh)\n\n# deploy.sh\nssh prod-server 'cd /opt/myapp && git pull && pip install -r requirements.txt && systemctl restart myapp'\n\n# Background jobs run in the same process\nimport threading\ndef background_worker():\n    while True:\n        process_queue()\n        time.sleep(5)\nthreading.Thread(target=background_worker, daemon=True).start()\n```",
        r'''<think>
Twelve-Factor violations:

1. **Config** (Factor III): Hardcoded config in source code. Should use env vars.
2. **Backing services** (Factor IV): DB/Redis URLs hardcoded, not swappable.
3. **Build, release, run** (Factor V): `git pull && pip install` on prod mixes build and run.
4. **Processes** (Factor VI): Background worker thread shares process. Should be separate process.
5. **Logs** (Factor XI): Logging to files. Should log to stdout.
6. **Dependencies** (Factor II): `pip install` on prod server, not a built artifact.
</think>

## Twelve-Factor Violations Found

| Factor | Violation | Fix |
|--------|-----------|-----|
| III. Config | Hardcoded DB URL, secrets | Environment variables |
| V. Build/Release/Run | `git pull && pip install` on prod | Docker image build → deploy |
| VI. Processes | Background worker thread in web process | Separate worker process |
| XI. Logs | Writing to log files | Log to stdout, let platform handle |
| II. Dependencies | Installing deps at deploy time | Baked into Docker image |

## Fixed Version

```python
# config.py — all config from environment
import os

DATABASE_URL = os.environ['DATABASE_URL']
REDIS_URL = os.environ['REDIS_URL']
SECRET_KEY = os.environ['SECRET_KEY']
# No LOG_FILE — logs go to stdout

# app.py — log to stdout
import logging
import sys

logging.basicConfig(
    stream=sys.stdout,  # stdout, not a file
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    level=logging.INFO,
)
```

```dockerfile
# Dockerfile — immutable build artifact
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
```

```yaml
# kubernetes deployment — separate web and worker processes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  template:
    spec:
      containers:
        - name: web
          image: myapp:v1.2.3
          command: ["gunicorn", "app:app"]
          envFrom:
            - secretRef:
                name: app-secrets
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker
spec:
  template:
    spec:
      containers:
        - name: worker
          image: myapp:v1.2.3  # Same image, different command
          command: ["python", "-m", "worker"]
```

**Key principles:** config from environment, logs to stdout, build once/deploy many, separate process types.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
