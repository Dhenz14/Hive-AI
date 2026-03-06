"""Phase 1X: Foundation Thinking — Architecture Patterns (Part 5)

Five training pairs on architecture: rate limiting design (token bucket,
sliding window), circuit breaker patterns, CQRS/event sourcing, deployment
strategy, and state management.
"""

PAIRS = [
    (
        "thinking/arch-rate-limiting",
        r'''We need to add rate limiting to our API. Requirements:
- 100 requests per minute per user
- 1000 requests per minute globally
- Burst-friendly (allow short bursts if user has been idle)
- Must work across multiple server instances
- Return meaningful headers (X-RateLimit-Remaining, Retry-After)

Current setup: 4 FastAPI instances behind nginx, Redis available.

What rate limiting algorithm should we use and how do we implement it?''',
        r'''<think>
Let me evaluate the rate limiting algorithms against the requirements:

**Fixed Window Counter:**
- Simple: count requests in the current minute
- Problem: boundary burst -- 100 requests at 0:59 + 100 at 1:00 = 200 in 2 seconds
- Not burst-friendly in the right way

**Sliding Window Log:**
- Store timestamp of every request, count those within the window
- Accurate, but O(n) storage per user (up to 100 entries)
- Expensive Redis operations (sorted sets)

**Sliding Window Counter:**
- Hybrid: use two fixed windows and weight by time position
- Good accuracy, O(1) storage per user
- Decent compromise

**Token Bucket:**
- Tokens added at steady rate, consumed per request
- Naturally burst-friendly (idle users accumulate tokens)
- O(1) storage (just token count + last refill time)
- Maps directly to the "burst-friendly" requirement

**Leaky Bucket:**
- Smooth output rate, queues requests
- Not burst-friendly -- that's the opposite of what we want

Token bucket is the best fit because:
1. Burst-friendly by design (accumulate tokens during idle)
2. O(1) storage in Redis (2 fields per user)
3. Simple to implement atomically with Lua script
4. Easy to compute remaining tokens for headers

For the global limit, a separate token bucket with higher capacity.

For multi-instance: Redis with atomic Lua script. Each request:
1. Read current tokens + last_refill_time
2. Calculate tokens to add based on elapsed time
3. If tokens available, consume one and return success
4. All in one atomic Lua script to avoid race conditions

Headers:
- X-RateLimit-Limit: 100
- X-RateLimit-Remaining: tokens left
- X-RateLimit-Reset: epoch time when bucket is full
- Retry-After: seconds until at least 1 token available (if rate limited)
</think>

**Token bucket** is the best fit. It's naturally burst-friendly (idle users accumulate tokens), O(1) storage, and easy to implement atomically in Redis.

**Algorithm:** Each user has a bucket with capacity 100. Tokens refill at 100/60 = 1.667 tokens/second. On each request, consume 1 token. If empty, reject.

```python
# rate_limiter.py
import time
import redis
from dataclasses import dataclass
from typing import Optional

@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    reset_at: float        # epoch when bucket is full
    retry_after: Optional[float]  # seconds until 1 token (if limited)

class TokenBucketLimiter:
    # Lua script runs atomically in Redis -- no race conditions
    LUA_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])  -- tokens per second
    local now = tonumber(ARGV[3])
    local requested = tonumber(ARGV[4])

    local data = redis.call('HMGET', key, 'tokens', 'last_refill')
    local tokens = tonumber(data[1])
    local last_refill = tonumber(data[2])

    -- Initialize if new bucket
    if tokens == nil then
        tokens = capacity
        last_refill = now
    end

    -- Refill tokens based on elapsed time
    local elapsed = now - last_refill
    local new_tokens = elapsed * refill_rate
    tokens = math.min(capacity, tokens + new_tokens)
    last_refill = now

    local allowed = 0
    local remaining = tokens

    if tokens >= requested then
        tokens = tokens - requested
        remaining = tokens
        allowed = 1
    end

    -- Store updated state
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) + 10)

    return {allowed, math.floor(remaining), tostring(tokens)}
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._script = self.redis.register_script(self.LUA_SCRIPT)

    def check(
        self,
        key: str,
        capacity: int = 100,
        refill_rate: float = 1.667,  # tokens per second (100/60)
    ) -> RateLimitResult:
        now = time.time()
        result = self._script(
            keys=[f"rl:{key}"],
            args=[capacity, refill_rate, now, 1],
        )
        allowed = bool(result[0])
        remaining = int(result[1])
        exact_tokens = float(result[2])

        # Calculate when bucket will be full
        time_to_full = (capacity - exact_tokens) / refill_rate
        reset_at = now + time_to_full

        # Calculate retry-after if limited
        retry_after = None
        if not allowed:
            retry_after = max(0.1, (1 - exact_tokens) / refill_rate)

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            limit=capacity,
            reset_at=reset_at,
            retry_after=retry_after,
        )


# FastAPI middleware
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI()
limiter = TokenBucketLimiter(redis.Redis())

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Per-user limit
    user_id = request.headers.get("X-User-ID", request.client.host)
    user_result = limiter.check(
        key=f"user:{user_id}",
        capacity=100,
        refill_rate=100 / 60,  # 100 per minute
    )

    # Global limit
    global_result = limiter.check(
        key="global",
        capacity=1000,
        refill_rate=1000 / 60,
    )

    if not user_result.allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after": user_result.retry_after},
            headers={
                "X-RateLimit-Limit": str(user_result.limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(int(user_result.retry_after + 0.5)),
            },
        )

    if not global_result.allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Service busy", "retry_after": global_result.retry_after},
            headers={"Retry-After": str(int(global_result.retry_after + 0.5))},
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(user_result.limit)
    response.headers["X-RateLimit-Remaining"] = str(user_result.remaining)
    response.headers["X-RateLimit-Reset"] = str(int(user_result.reset_at))
    return response
```

**Why token bucket over alternatives:**
- **Fixed window:** Has boundary-burst problem (200 requests in 2 seconds across window boundaries)
- **Sliding window log:** Stores every request timestamp -- O(n) storage, expensive sorted set operations
- **Leaky bucket:** Smooths traffic but is NOT burst-friendly -- opposite of the requirement
- **Token bucket:** Naturally allows bursts up to capacity, refills steadily, O(1) storage'''
    ),
    (
        "thinking/arch-circuit-breaker",
        r'''Our microservice calls a payment provider that occasionally has outages (2-3 times per month, lasting 5-30 minutes). During outages, our service queues up thousands of requests, all time out after 30 seconds, and users get terrible experience. We need a circuit breaker.

Current code:

import requests

class PaymentClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    def charge(self, amount: float, card_token: str) -> dict:
        resp = requests.post(
            f"{self.base_url}/v1/charges",
            json={"amount": amount, "source": card_token},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

Design and implement a circuit breaker pattern for this.''',
        r'''<think>
The circuit breaker pattern has three states:

1. **CLOSED** (normal): Requests flow through. Track failures. If failures exceed threshold, open the circuit.
2. **OPEN** (failing fast): All requests immediately fail without calling the downstream. After a timeout, move to half-open.
3. **HALF-OPEN** (testing): Allow ONE request through. If it succeeds, close the circuit. If it fails, re-open.

Key parameters:
- `failure_threshold`: Number of consecutive failures before opening (e.g., 5)
- `recovery_timeout`: How long to stay open before trying half-open (e.g., 30 seconds)
- `success_threshold`: Number of successes in half-open before fully closing (e.g., 2)

For payments specifically:
- We should NOT retry charges (double-charging risk)
- On circuit open, return a clear "service unavailable" error so the UI can show "try again later"
- Log state transitions for alerting
- Consider: what counts as a "failure"? HTTP 5xx and timeouts, NOT 4xx (which are our bugs)

Implementation considerations:
- Thread-safe (web server handles concurrent requests)
- The state should be per-client, not global (we might have multiple payment providers)
- For multi-instance: could use Redis for shared state, but local state is often good enough (each instance independently detects outages)

Let me also think about the sliding window for failure counting vs consecutive failures:
- Consecutive failures: simpler, but one success resets the count (could keep circuit closed too long during partial outages)
- Sliding window: count failures in last N seconds. More robust for intermittent failures.

I'll implement sliding window with a deque of recent results.
</think>

Here's a circuit breaker implementation with three states, sliding window failure detection, and payment-specific safety:

```python
import time
import threading
import logging
from enum import Enum
from collections import deque
from typing import Optional, Callable
import requests

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"        # normal operation
    OPEN = "open"            # failing fast
    HALF_OPEN = "half_open"  # testing recovery

class CircuitOpenError(Exception):
    """Raised when circuit is open -- request was NOT sent."""
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Circuit open. Retry after {retry_after:.0f}s")

class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,     # failures to trip
        recovery_timeout: float = 30,   # seconds before half-open
        success_threshold: int = 2,     # successes to close
        window_size: float = 60,        # sliding window in seconds
        is_failure: Optional[Callable] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.window_size = window_size
        self.is_failure = is_failure or self._default_is_failure

        self._state = CircuitState.CLOSED
        self._failures = deque()       # timestamps of recent failures
        self._last_failure_time = 0.0
        self._half_open_successes = 0
        self._lock = threading.Lock()

    @staticmethod
    def _default_is_failure(exc: Exception) -> bool:
        """Only count server errors and timeouts, not client errors."""
        if isinstance(exc, requests.exceptions.Timeout):
            return True
        if isinstance(exc, requests.exceptions.ConnectionError):
            return True
        if isinstance(exc, requests.exceptions.HTTPError):
            return exc.response.status_code >= 500
        return False

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_successes = 0
                    logger.info(f"[{self.name}] Circuit HALF_OPEN -- testing recovery")
            return self._state

    def _prune_old_failures(self, now: float):
        cutoff = now - self.window_size
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _record_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failures.clear()
                    logger.info(f"[{self.name}] Circuit CLOSED -- recovered")

    def _record_failure(self):
        with self._lock:
            now = time.monotonic()
            self._failures.append(now)
            self._prune_old_failures(now)
            self._last_failure_time = now

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(f"[{self.name}] Circuit OPEN -- half-open test failed")
            elif len(self._failures) >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[{self.name}] Circuit OPEN -- "
                    f"{len(self._failures)} failures in {self.window_size}s window"
                )

    def call(self, func, *args, **kwargs):
        """Execute func through the circuit breaker."""
        state = self.state  # property checks for OPEN -> HALF_OPEN transition

        if state == CircuitState.OPEN:
            retry_after = (
                self.recovery_timeout
                - (time.monotonic() - self._last_failure_time)
            )
            raise CircuitOpenError(retry_after=max(0, retry_after))

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as exc:
            if self.is_failure(exc):
                self._record_failure()
            raise


# Payment client with circuit breaker
class PaymentClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.session = requests.Session()
        self.circuit = CircuitBreaker(
            name="payment-provider",
            failure_threshold=5,
            recovery_timeout=30,
            success_threshold=2,
        )

    def charge(self, amount: float, card_token: str) -> dict:
        def _do_charge():
            resp = self.session.post(
                f"{self.base_url}/v1/charges",
                json={"amount": amount, "source": card_token},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,  # 5s not 30s -- fail fast
            )
            resp.raise_for_status()
            return resp.json()

        try:
            return self.circuit.call(_do_charge)
        except CircuitOpenError:
            # Return a clear error -- do NOT retry charges
            return {
                "status": "unavailable",
                "message": "Payment service temporarily unavailable. "
                           "Your card was NOT charged. Please try again shortly.",
            }
```

**State diagram:**
```
CLOSED --[5 failures in 60s]--> OPEN --[30s elapsed]--> HALF_OPEN
  ^                                                        |
  |----[2 successes]--------<------------------------------+
                                                           |
  OPEN <---[1 failure]-------------------------------------+
```

**Key design decisions:**
- Sliding window (not consecutive count) to catch intermittent failures
- Only 5xx and timeouts trip the breaker, not 4xx client errors
- 5-second timeout instead of 30 (fail fast)
- NEVER retry payment charges (double-charge risk)
- Circuit is local per instance (no Redis needed -- each instance detects independently)'''
    ),
    (
        "thinking/arch-cqrs-event-sourcing",
        r'''We're building an e-commerce order system. Requirements:
- Full audit trail of every state change
- Ability to reconstruct order state at any point in time
- Separate read models optimized for different queries (admin dashboard, customer order history, shipping fulfillment)
- Handle 10k orders/hour

Current design is a single orders table with status column that gets updated in place. We lose history every time status changes.

Should we use CQRS with event sourcing? Show the core design.''',
        r'''<think>
Let me evaluate whether CQRS + event sourcing is the right fit:

Requirements check:
1. Full audit trail -- event sourcing gives this naturally (events are immutable, never deleted)
2. Reconstruct state at any point in time -- replay events up to that timestamp
3. Multiple read models -- CQRS separates reads from writes, each read model is optimized for its query pattern
4. 10k orders/hour -- ~3 orders/second. This is very manageable for event sourcing.

Alternatives:
- Just add an audit log table alongside the orders table. Simpler but doesn't give time-travel reconstruction or optimized read models.
- Temporal tables (SQL Server / MariaDB feature). Gives some time-travel but not multiple read models.

CQRS + event sourcing IS the right fit here. The requirements specifically call for its strengths.

Core design:
1. **Command side:** Accept commands (PlaceOrder, ShipOrder, etc.), validate, produce events
2. **Event store:** Append-only store of events, partitioned by aggregate (order) ID
3. **Read side:** Event handlers that project events into denormalized read models

Key aggregates:
- Order (main aggregate)

Events:
- OrderPlaced(order_id, customer_id, items, timestamp)
- OrderConfirmed(order_id, timestamp)
- PaymentReceived(order_id, amount, payment_id, timestamp)
- OrderShipped(order_id, tracking_number, timestamp)
- OrderDelivered(order_id, timestamp)
- OrderCancelled(order_id, reason, timestamp)
- ItemRefunded(order_id, item_id, amount, timestamp)

Read models:
1. CustomerOrderView -- optimized for "my orders" page
2. AdminDashboardView -- aggregated stats, recent orders
3. FulfillmentView -- orders ready to ship, shipping status

Let me design the core classes.
</think>

Yes, CQRS + event sourcing is an excellent fit for these exact requirements. Here's the core design:

```python
# domain/events.py -- Immutable event definitions
from dataclasses import dataclass, field
from datetime import datetime
from typing import List
import uuid

@dataclass(frozen=True)
class DomainEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    aggregate_id: str = ""
    version: int = 0  # optimistic concurrency

@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    customer_id: str = ""
    items: tuple = ()  # ((product_id, qty, price), ...)
    shipping_address: str = ""

@dataclass(frozen=True)
class PaymentReceived(DomainEvent):
    amount: float = 0.0
    payment_id: str = ""

@dataclass(frozen=True)
class OrderShipped(DomainEvent):
    tracking_number: str = ""
    carrier: str = ""

@dataclass(frozen=True)
class OrderDelivered(DomainEvent):
    pass

@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    reason: str = ""


# domain/order.py -- Aggregate: enforces business rules
class Order:
    """Event-sourced aggregate. State is rebuilt from events."""

    def __init__(self, order_id: str):
        self.id = order_id
        self.version = 0
        self.status = "new"
        self.customer_id = None
        self.items = ()
        self.total = 0.0
        self.paid = 0.0
        self._pending_events: list = []

    # --- Command handlers (validate + produce events) ---

    def place(self, customer_id, items, shipping_address):
        if self.status != "new":
            raise ValueError(f"Cannot place order in status: {self.status}")
        if not items:
            raise ValueError("Order must have at least one item")

        self._apply(OrderPlaced(
            aggregate_id=self.id,
            customer_id=customer_id,
            items=tuple(items),
            shipping_address=shipping_address,
        ))

    def receive_payment(self, amount, payment_id):
        if self.status != "placed":
            raise ValueError(f"Cannot pay for order in status: {self.status}")
        if amount < self.total:
            raise ValueError(f"Insufficient payment: {amount} < {self.total}")

        self._apply(PaymentReceived(
            aggregate_id=self.id,
            amount=amount,
            payment_id=payment_id,
        ))

    def ship(self, tracking_number, carrier):
        if self.status != "paid":
            raise ValueError(f"Cannot ship order in status: {self.status}")

        self._apply(OrderShipped(
            aggregate_id=self.id,
            tracking_number=tracking_number,
            carrier=carrier,
        ))

    def cancel(self, reason):
        if self.status in ("delivered", "cancelled"):
            raise ValueError(f"Cannot cancel order in status: {self.status}")

        self._apply(OrderCancelled(
            aggregate_id=self.id,
            reason=reason,
        ))

    # --- Event applicators (update state, NO validation) ---

    def _apply(self, event):
        self._on(event)
        self._pending_events.append(event)

    def _on(self, event):
        """Mutate state based on event type."""
        self.version += 1
        if isinstance(event, OrderPlaced):
            self.status = "placed"
            self.customer_id = event.customer_id
            self.items = event.items
            self.total = sum(qty * price for _, qty, price in event.items)
        elif isinstance(event, PaymentReceived):
            self.status = "paid"
            self.paid = event.amount
        elif isinstance(event, OrderShipped):
            self.status = "shipped"
        elif isinstance(event, OrderDelivered):
            self.status = "delivered"
        elif isinstance(event, OrderCancelled):
            self.status = "cancelled"

    @classmethod
    def from_events(cls, order_id: str, events: list) -> "Order":
        """Reconstruct state by replaying events."""
        order = cls(order_id)
        for event in events:
            order._on(event)
        return order

    @classmethod
    def at_time(cls, order_id: str, events: list, as_of: datetime) -> "Order":
        """Reconstruct state at a specific point in time."""
        order = cls(order_id)
        for event in events:
            if event.timestamp <= as_of:
                order._on(event)
        return order


# infrastructure/event_store.py -- Append-only event persistence
import json

class EventStore:
    """Append-only event store with optimistic concurrency."""

    def __init__(self, db):
        self.db = db

    def save_events(self, aggregate_id: str, events: list,
                    expected_version: int):
        """Atomic append with optimistic concurrency check."""
        with self.db.transaction() as txn:
            current = txn.execute(
                "SELECT MAX(version) FROM events WHERE aggregate_id = %s",
                (aggregate_id,)
            ).scalar() or 0

            if current != expected_version:
                raise ConcurrencyError(
                    f"Expected version {expected_version}, got {current}"
                )

            for i, event in enumerate(events):
                txn.execute(
                    "INSERT INTO events "
                    "(event_id, aggregate_id, version, event_type, data, timestamp) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (event.event_id, aggregate_id,
                     expected_version + i + 1,
                     type(event).__name__,
                     json.dumps(event.__dict__),
                     event.timestamp),
                )

    def load_events(self, aggregate_id: str) -> list:
        rows = self.db.execute(
            "SELECT event_type, data FROM events "
            "WHERE aggregate_id = %s ORDER BY version",
            (aggregate_id,)
        ).fetchall()
        return [self._deserialize(row) for row in rows]


# read_models/projections.py -- Separate read models
class CustomerOrderProjection:
    """Denormalized view for 'My Orders' page."""

    def handle(self, event):
        if isinstance(event, OrderPlaced):
            self.db.upsert("customer_orders", {
                "order_id": event.aggregate_id,
                "customer_id": event.customer_id,
                "status": "placed",
                "item_count": len(event.items),
                "total": sum(q * p for _, q, p in event.items),
                "placed_at": event.timestamp,
            })
        elif isinstance(event, OrderShipped):
            self.db.update("customer_orders",
                {"order_id": event.aggregate_id},
                {"status": "shipped", "tracking": event.tracking_number})

class FulfillmentProjection:
    """View for warehouse: what needs to ship?"""

    def handle(self, event):
        if isinstance(event, PaymentReceived):
            self.db.insert("fulfillment_queue", {
                "order_id": event.aggregate_id,
                "status": "ready_to_ship",
                "paid_at": event.timestamp,
            })
        elif isinstance(event, OrderShipped):
            self.db.update("fulfillment_queue",
                {"order_id": event.aggregate_id},
                {"status": "shipped", "shipped_at": event.timestamp})
```

**Architecture overview:**
```
Commands --> Order Aggregate --> Events --> Event Store (append-only)
                                  |
                                  +--> CustomerOrderProjection --> customer_orders table
                                  +--> FulfillmentProjection   --> fulfillment_queue table
                                  +--> AdminDashboardProjection --> dashboard_stats table
```

**Why this fits your requirements:**
- **Audit trail:** Events are immutable, never deleted -- complete history
- **Time travel:** `Order.at_time()` replays events up to any timestamp
- **Multiple read models:** Each projection builds its own denormalized table
- **10k orders/hour:** Event sourcing handles this easily; read models can be eventually consistent'''
    ),
    (
        "thinking/arch-deployment-strategy",
        r'''We need to deploy a critical update to our payment processing service. It handles $2M/day in transactions across 12 instances behind a load balancer. Current deployment is "stop all, deploy, start all" which causes 2-3 minutes of downtime.

Requirements:
- Zero downtime
- Ability to roll back within 60 seconds if problems detected
- The update includes a database migration (adding a nullable column)
- Must not lose any in-flight transactions during deploy
- Monitoring integration to auto-detect failures

What deployment strategy should we use?''',
        r'''<think>
Let me evaluate deployment strategies for this critical payment service:

**Blue-Green:**
- Two identical environments (blue = current, green = new)
- Switch traffic all at once via load balancer
- Rollback: switch back to blue
- Problem: database migrations are shared -- can't easily "unswitch" if migration is destructive
- Good: instant rollback for stateless services

**Canary:**
- Deploy to 1-2 instances first, monitor, then gradually roll out
- If canary fails, only affects a small % of traffic
- Rollback: just redeploy old version to canary instances
- Best for detecting problems before full rollout

**Rolling update:**
- Update instances one at a time
- Always have most instances running old or new version
- Slower rollback (have to re-roll through all instances)

For a payment service handling $2M/day, I'd use **canary deployment** because:
1. Limits blast radius (if canary fails, only ~8% of traffic affected = 1/12 instances)
2. Real production traffic validation before full rollout
3. Combined with the nullable column migration, both old and new code can coexist

Database migration strategy: Since we're adding a nullable column, this is backward-compatible. The old code simply ignores the new column. This is the "expand-contract" pattern:
1. EXPAND: Add nullable column (both old and new code work)
2. MIGRATE: Deploy new code that reads/writes the new column
3. CONTRACT: (later) Remove old code that doesn't use the column

For in-flight transactions: We need connection draining. When removing an instance from the load balancer, let existing requests complete (drain) before stopping the instance.

The deployment pipeline:
1. Run DB migration (add nullable column) -- safe, non-breaking
2. Deploy canary (1-2 instances) with connection draining
3. Monitor canary for 5-10 minutes (error rates, latency, transaction success rate)
4. If canary healthy, proceed with rolling update of remaining instances
5. If canary unhealthy, rollback canary instances immediately

Auto-rollback criteria:
- Error rate > 1% (baseline is ~0.1%)
- P99 latency > 2x baseline
- Transaction success rate drops below 99.5%
- Any 5xx responses
</think>

**Use canary deployment with rolling rollout.** This is the safest strategy for a $2M/day payment service because it limits blast radius while validating with real traffic.

**Phase 1: Database migration (before any code deploy)**
```sql
-- Safe: nullable column, no default, no lock on existing rows
ALTER TABLE transactions ADD COLUMN risk_score DECIMAL(5,2) NULL;

-- Add index concurrently (no table lock in Postgres)
CREATE INDEX CONCURRENTLY idx_transactions_risk_score
ON transactions(risk_score) WHERE risk_score IS NOT NULL;
```
Both old and new code work with this schema. Old code ignores the column. New code writes to it.

**Phase 2: Canary deployment pipeline**
```yaml
# deployment-pipeline.yaml (conceptual)
stages:
  - name: pre-flight
    steps:
      - run_db_migration       # Phase 1 above
      - verify_migration       # confirm column exists
      - snapshot_baseline       # record current error rate, latency, throughput

  - name: canary
    instances: 1               # 1 of 12 = ~8% of traffic
    steps:
      - drain_connections:     # let in-flight requests complete
          timeout: 30s
      - deploy_new_version
      - health_check:
          endpoint: /health
          timeout: 10s
          retries: 3
      - add_to_load_balancer
      - monitor:
          duration: 10m
          auto_rollback_if:
            error_rate: "> 1%"
            p99_latency: "> 2x baseline"
            transaction_success: "< 99.5%"

  - name: rolling_rollout
    batch_size: 2              # 2 instances at a time
    steps:
      - drain_connections:
          timeout: 30s
      - deploy_new_version
      - health_check
      - add_to_load_balancer
      - monitor:
          duration: 2m
          auto_rollback_if: same_as_canary

  - name: verification
    steps:
      - full_smoke_test
      - compare_metrics_to_baseline
      - notify_team: "Deploy complete"
```

**Connection draining implementation:**
```python
# In your service startup/shutdown
import signal
import asyncio

class GracefulShutdown:
    def __init__(self, app):
        self.app = app
        self.shutting_down = False
        self.active_requests = 0
        self._lock = asyncio.Lock()

    async def start_shutdown(self):
        self.shutting_down = True
        # Tell load balancer we're going away
        self.app.health_status = "draining"

        # Wait for in-flight requests (max 30 seconds)
        for _ in range(300):
            if self.active_requests == 0:
                break
            await asyncio.sleep(0.1)

        # Force shutdown after timeout
        await self.app.shutdown()

    async def middleware(self, request, handler):
        if self.shutting_down:
            # Reject NEW requests during drain
            return Response(status=503,
                          headers={"Retry-After": "5"})
        async with self._lock:
            self.active_requests += 1
        try:
            return await handler(request)
        finally:
            async with self._lock:
                self.active_requests -= 1
```

**Rollback decision matrix:**

| Signal | Threshold | Action | Time to detect |
|---|---|---|---|
| 5xx error rate | > 1% for 1 min | Auto-rollback canary | ~60s |
| P99 latency | > 2x baseline for 2 min | Auto-rollback canary | ~120s |
| Transaction failures | > 0.5% for 1 min | Auto-rollback ALL | ~60s |
| Health check failure | 3 consecutive | Auto-rollback instance | ~30s |
| Manual trigger | Engineer decision | Rollback all | ~10s |

**Rollback procedure (under 60 seconds):**
1. Remove canary/new instances from load balancer (instant)
2. Drain connections on new instances (10-30s)
3. Redeploy old version to affected instances (15-20s)
4. Health check + re-add to LB (5-10s)
5. DB migration stays (it's backward-compatible)

**Key principle: Expand-Contract for database changes.**
Never deploy destructive migrations alongside code changes. The sequence is always: expand schema -> deploy new code -> contract schema (weeks later).'''
    ),
    (
        "thinking/arch-state-management",
        r'''We're building a complex React + Python backend application for project management. The frontend has deeply nested state that's causing bugs:

// Current frontend state (simplified)
const [project, setProject] = useState(null);
const [tasks, setTasks] = useState([]);
const [selectedTask, setSelectedTask] = useState(null);
const [filters, setFilters] = useState({status: 'all', assignee: 'all'});
const [isEditing, setIsEditing] = useState(false);
const [pendingChanges, setPendingChanges] = useState({});
const [syncStatus, setSyncStatus] = useState('idle');
const [undoStack, setUndoStack] = useState([]);
const [notifications, setNotifications] = useState([]);

Problems we're hitting:
1. State updates race with server sync -- user edits get overwritten
2. Undo is brittle and frequently breaks
3. Filter changes cause unnecessary re-renders of the entire task list
4. Optimistic updates sometimes show stale data
5. Two users editing the same task see conflicts

How should we redesign the state management?''',
        r'''<think>
Let me analyze each problem and design a solution:

1. **Race conditions with server sync:** This is an optimistic concurrency problem. Need version numbers or timestamps on entities, and conflict resolution.

2. **Brittle undo:** The undo stack stores... what? If it stores snapshots, it's wasteful. If it stores diffs/commands, it needs to be synchronized with the server state. Command pattern is better.

3. **Unnecessary re-renders:** Multiple useState hooks cause any state change to potentially re-render. Need to separate concerns -- memoization, selectors, or a state management library.

4. **Optimistic updates showing stale data:** Related to #1. Need to track which changes are "pending" vs "confirmed" and reconcile when server responds.

5. **Multi-user conflicts:** Need real-time sync (WebSockets) and conflict resolution strategy (last-write-wins, operational transform, or CRDTs).

Architecture proposal:

**Frontend:**
- Use a reducer pattern (useReducer or Zustand) with distinct slices
- Command pattern for mutations (supports undo/redo)
- Optimistic updates with pending state tracking
- WebSocket for real-time sync

**Backend:**
- Event-based API: clients send commands, server returns events
- Version-based conflict detection (ETag / version column)
- Server-sent events or WebSocket for push updates

Let me design this properly.
</think>

The root cause is mixing UI state, domain state, and sync state in flat useState hooks. Here's a layered redesign:

**Layer 1: Normalized domain state with version tracking**
```typescript
// store/taskStore.ts -- using Zustand for simplicity
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';

interface Task {
  id: string;
  title: string;
  status: string;
  assignee: string;
  version: number;       // server version for conflict detection
  updatedAt: string;
}

interface TaskStore {
  // Normalized entities (like a client-side DB)
  tasks: Record<string, Task>;

  // Pending optimistic updates (not yet confirmed by server)
  pending: Record<string, Partial<Task>>;

  // Confirmed server state for conflict resolution
  serverState: Record<string, Task>;

  // Actions
  applyOptimisticUpdate: (taskId: string, changes: Partial<Task>) => void;
  confirmUpdate: (taskId: string, serverTask: Task) => void;
  rejectUpdate: (taskId: string) => void;
  receiveServerUpdate: (task: Task) => void;
}

const useTaskStore = create<TaskStore>()(
  immer((set, get) => ({
    tasks: {},
    pending: {},
    serverState: {},

    applyOptimisticUpdate: (taskId, changes) => {
      set((state) => {
        // Save current state for potential rollback
        if (!state.pending[taskId]) {
          state.serverState[taskId] = { ...state.tasks[taskId] };
        }
        // Apply optimistically
        state.pending[taskId] = {
          ...(state.pending[taskId] || {}),
          ...changes,
        };
        Object.assign(state.tasks[taskId], changes);
      });
    },

    confirmUpdate: (taskId, serverTask) => {
      set((state) => {
        state.tasks[taskId] = serverTask;
        delete state.pending[taskId];
        delete state.serverState[taskId];
      });
    },

    rejectUpdate: (taskId) => {
      set((state) => {
        // Rollback to server state
        if (state.serverState[taskId]) {
          state.tasks[taskId] = state.serverState[taskId];
        }
        delete state.pending[taskId];
        delete state.serverState[taskId];
      });
    },

    receiveServerUpdate: (task) => {
      set((state) => {
        if (state.pending[task.id]) {
          // Conflict: we have pending local changes
          // Keep local changes, but update serverState for diff
          state.serverState[task.id] = task;
        } else {
          // No conflict: apply server update directly
          state.tasks[task.id] = task;
        }
      });
    },
  }))
);
```

**Layer 2: Command pattern for undo/redo**
```typescript
// store/commandStore.ts
interface Command {
  id: string;
  type: string;
  taskId: string;
  before: Partial<Task>;  // state before change
  after: Partial<Task>;   // state after change
  timestamp: number;
}

interface CommandStore {
  undoStack: Command[];
  redoStack: Command[];
  execute: (cmd: Omit<Command, 'id' | 'timestamp'>) => void;
  undo: () => void;
  redo: () => void;
}

const useCommandStore = create<CommandStore>()((set, get) => ({
  undoStack: [],
  redoStack: [],

  execute: (cmd) => {
    const full: Command = {
      ...cmd,
      id: crypto.randomUUID(),
      timestamp: Date.now(),
    };
    // Apply the change
    useTaskStore.getState().applyOptimisticUpdate(cmd.taskId, cmd.after);
    // Send to server
    syncToServer(full);

    set((state) => ({
      undoStack: [...state.undoStack, full],
      redoStack: [],  // clear redo on new action
    }));
  },

  undo: () => {
    const { undoStack } = get();
    const cmd = undoStack[undoStack.length - 1];
    if (!cmd) return;

    // Apply reverse
    useTaskStore.getState().applyOptimisticUpdate(cmd.taskId, cmd.before);
    syncToServer({ ...cmd, after: cmd.before, type: `undo_${cmd.type}` });

    set((state) => ({
      undoStack: state.undoStack.slice(0, -1),
      redoStack: [...state.redoStack, cmd],
    }));
  },

  redo: () => {
    const { redoStack } = get();
    const cmd = redoStack[redoStack.length - 1];
    if (!cmd) return;

    useTaskStore.getState().applyOptimisticUpdate(cmd.taskId, cmd.after);
    syncToServer(cmd);

    set((state) => ({
      redoStack: state.redoStack.slice(0, -1),
      undoStack: [...state.undoStack, cmd],
    }));
  },
}));
```

**Layer 3: Separated UI state (prevents cross-contamination)**
```typescript
// store/uiStore.ts -- pure UI state, no domain data
const useUIStore = create((set) => ({
  selectedTaskId: null as string | null,
  isEditing: false,
  filters: { status: 'all', assignee: 'all' },
  syncStatus: 'idle' as 'idle' | 'syncing' | 'error',

  setSelectedTask: (id: string | null) => set({ selectedTaskId: id }),
  setEditing: (v: boolean) => set({ isEditing: v }),
  setFilter: (key: string, value: string) =>
    set((s) => ({ filters: { ...s.filters, [key]: value } })),
}));
```

**Layer 4: Derived state with memoized selectors (fixes re-renders)**
```typescript
// selectors.ts -- memoized, only re-render when output changes
import { useMemo } from 'react';

function useFilteredTasks() {
  const tasks = useTaskStore((s) => s.tasks);
  const pending = useTaskStore((s) => s.pending);
  const filters = useUIStore((s) => s.filters);

  return useMemo(() => {
    return Object.values(tasks).filter((task) => {
      if (filters.status !== 'all' && task.status !== filters.status)
        return false;
      if (filters.assignee !== 'all' && task.assignee !== filters.assignee)
        return false;
      return true;
    }).map((task) => ({
      ...task,
      isPending: task.id in pending,  // visual indicator
    }));
  }, [tasks, pending, filters]);
}
```

**Backend: Version-based conflict detection**
```python
# Python backend endpoint
@app.patch("/tasks/{task_id}")
async def update_task(task_id: str, update: TaskUpdate):
    async with db.transaction() as txn:
        current = await txn.get_task_for_update(task_id)

        if current.version != update.expected_version:
            # Conflict! Return both versions for client resolution
            return JSONResponse(status_code=409, content={
                "error": "conflict",
                "server_version": current.dict(),
                "your_changes": update.dict(),
            })

        current.apply(update.changes)
        current.version += 1
        await txn.save(current)

        # Broadcast to other connected clients
        await websocket_manager.broadcast(task_id, {
            "type": "task_updated",
            "task": current.dict(),
        })

        return current.dict()
```

**How this fixes each problem:**
1. **Race conditions:** Version numbers detect conflicts; optimistic updates show immediately, rollback on rejection
2. **Brittle undo:** Command pattern stores before/after snapshots, independent of server state
3. **Unnecessary re-renders:** Zustand selectors only trigger re-renders when selected slice changes; memoized filtered list
4. **Stale optimistic data:** Pending state tracked separately; server confirmations reconcile automatically
5. **Multi-user conflicts:** WebSocket pushes updates; version check prevents silent overwrites; 409 response enables merge UI'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
