"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 2/5)
Distributed systems patterns: consensus, consistency, partitioning, replication."""

PAIRS = [
    (
        "thinking/distributed-cap-theorem",
        "Our team is choosing between different database setups for our e-commerce platform. Someone mentioned the CAP theorem. Can you explain it with practical examples of when to choose what?",
        r'''<think>
CAP theorem: in a distributed system, you can only guarantee 2 of 3:
- Consistency: every read receives the most recent write
- Availability: every request receives a response
- Partition tolerance: system works despite network failures

In practice, network partitions WILL happen, so you're really choosing between:
- CP: consistent but may be unavailable during partition (traditional RDBMS with sync replication)
- AP: available but may return stale data during partition (Cassandra, DynamoDB)

The nuance: CAP is about behavior DURING a network partition. When everything is fine, you get all three.

Let me give practical examples for e-commerce.
</think>

## CAP Theorem in Practice

Network partitions **will** happen, so you're really choosing:

```
During a network split, pick one:
  CP → Refuse to serve (unavailable) until consistency is restored
  AP → Serve possibly stale data (available) but may be inconsistent
```

## E-Commerce Decision Guide

### Inventory/Payments → CP (Consistency)
```
Scenario: User buys the last item
  Network partition happens between servers

  CP (correct): "Sorry, can't process right now" → User retries later
  AP (dangerous): Both servers say "1 left" → Oversold! Two customers, one item

  Use: PostgreSQL with synchronous replication
  Accept: Brief unavailability during partition
```

### Product Catalog → AP (Availability)
```
Scenario: Product description updated
  Network partition happens

  AP (fine): Some users see old description for a few seconds
  CP (bad): Entire catalog goes down while syncing

  Use: Redis cache, CDN, eventually consistent reads
  Accept: Stale product info for a few seconds
```

### Shopping Cart → AP (Availability)
```
Scenario: User adds item to cart
  Network partition happens

  AP (fine): Cart might show slightly outdated state
  CP (bad): "Can't add to cart right now" → User leaves

  Use: DynamoDB or Redis with eventual consistency
  Accept: Rare cart conflicts (resolve with "last write wins" or merge)
```

## Practical Architecture

```
┌─────────────────────────────────────┐
│           E-Commerce App            │
├──────────┬──────────┬───────────────┤
│ Payments │ Inventory│ Catalog/Cart  │
│   (CP)   │   (CP)   │    (AP)       │
│ PostgreSQL│ PostgreSQL│ Redis/Dynamo │
│ sync repl│ row locks │ async repl   │
└──────────┴──────────┴───────────────┘
```

**Rule**: CP for money and inventory (correctness matters more than speed). AP for everything else (availability matters more than perfect consistency).

Most real systems use **CP for writes, AP for reads** — the same data can be read from a cache (AP) but written to a primary database (CP).'''
    ),
    (
        "thinking/distributed-eventual-consistency",
        "We split our monolith into microservices. Now when an order is placed, the Inventory service and the Notification service need to be updated. Sometimes the inventory is decremented but the email never sends, or vice versa. How do we keep them in sync?",
        r'''<think>
This is the distributed transaction problem. You can't use a regular database transaction across microservices.

Solutions:
1. Saga pattern (choreography or orchestration)
2. Transactional Outbox pattern (reliable event publishing)
3. Change Data Capture (CDC)

The transactional outbox is the most practical for most teams. The key insight: write the event to an outbox table in the SAME transaction as the business operation, then a separate process publishes it.
</think>

You've hit the **distributed transaction problem** — you can't wrap two microservices in one database transaction. Use the **Transactional Outbox Pattern**:

## The Problem

```
Order Service:
  1. Save order to DB          ✓ Success
  2. Call Inventory API         ✓ Success
  3. Call Notification API      ✗ Network timeout!

  Result: Order saved, inventory decremented, but no email sent.
  Even worse: if step 2 fails after step 1, you have an order with no inventory deduction.
```

## The Fix: Transactional Outbox

```python
# Order Service — write event to outbox in SAME transaction as order
def create_order(user_id, items):
    with db.transaction():
        # Business operation
        order = Order.create(user_id=user_id, items=items)

        # Write events to outbox (same transaction = atomic)
        OutboxEvent.create(
            aggregate_id=order.id,
            event_type='order.created',
            payload=json.dumps({
                'order_id': order.id,
                'user_id': user_id,
                'items': [{'product_id': i.product_id, 'qty': i.qty} for i in items],
            }),
        )

    return order
    # If the transaction fails, BOTH the order AND the event are rolled back
    # If it succeeds, BOTH are committed
```

```python
# Outbox publisher — separate process reads outbox and publishes to message broker
def publish_outbox_events():
    """Runs periodically (every 1-5 seconds)."""
    events = OutboxEvent.query.filter_by(published=False).limit(100).all()

    for event in events:
        try:
            message_broker.publish(
                topic=event.event_type,
                message=event.payload,
            )
            event.published = True
            event.published_at = datetime.utcnow()
            db.session.commit()
        except Exception:
            logger.exception(f"Failed to publish event {event.id}")
            # Will retry on next cycle
```

```python
# Inventory Service — consumes events
@message_broker.subscribe('order.created')
def handle_order_created(event):
    data = json.loads(event.payload)
    for item in data['items']:
        decrement_stock(item['product_id'], item['qty'])

# Notification Service — consumes same events
@message_broker.subscribe('order.created')
def handle_order_created(event):
    data = json.loads(event.payload)
    send_order_confirmation(data['user_id'], data['order_id'])
```

## Why This Works

```
1. Order + Event saved atomically (one transaction)
2. Publisher reads outbox, publishes to broker
3. If publisher crashes → restarts and retries unpublished events
4. If consumer crashes → message broker redelivers
5. Consumers must be idempotent (handle duplicate deliveries)
```

## Making Consumers Idempotent

```python
@message_broker.subscribe('order.created')
def handle_order_created(event):
    # Check if already processed
    if ProcessedEvent.exists(event_id=event.id):
        return  # Already handled, skip

    decrement_stock(event.data['product_id'], event.data['qty'])

    # Mark as processed
    ProcessedEvent.create(event_id=event.id)
```

**Key insight**: The outbox table turns a distributed transaction problem into a reliable message delivery problem.'''
    ),
    (
        "thinking/distributed-idempotency",
        "Our payment API sometimes charges customers twice when there's a network timeout. The client retries the request but the first request actually succeeded. How do I prevent double charges?",
        r'''<think>
Idempotency — making it safe to retry operations. The standard solution is an idempotency key:
1. Client generates a unique key for each logical operation
2. Server checks if it's seen this key before
3. If yes, return the cached result without re-executing
4. If no, execute and store the result

This is how Stripe handles payment idempotency.
</think>

Use **idempotency keys** — the industry standard (used by Stripe, PayPal, etc.):

## How It Works

```
Client → Server: POST /charge {amount: $50, idempotency_key: "abc-123"}
Server: Never seen "abc-123" → process charge → save result → return 200

Client timeout → retry:
Client → Server: POST /charge {amount: $50, idempotency_key: "abc-123"}
Server: Already processed "abc-123" → return cached result → 200

Result: Charged exactly once, client got a response.
```

## Implementation

```python
from functools import wraps

def idempotent(func):
    """Decorator that makes an endpoint idempotent."""
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        idempotency_key = request.headers.get('Idempotency-Key')
        if not idempotency_key:
            return func(request, *args, **kwargs)  # No key = no idempotency

        # Check for existing result
        cached = IdempotencyRecord.query.filter_by(
            key=idempotency_key
        ).first()

        if cached:
            if cached.status == 'processing':
                return Response({'error': 'Request in progress'}, status=409)
            return Response(
                json.loads(cached.response_body),
                status=cached.response_status,
            )

        # Lock and process
        record = IdempotencyRecord.create(
            key=idempotency_key,
            status='processing',
            request_hash=hash_request(request),
        )

        try:
            response = func(request, *args, **kwargs)
            record.status = 'completed'
            record.response_body = json.dumps(response.data)
            record.response_status = response.status_code
            record.save()
            return response
        except Exception as e:
            record.status = 'failed'
            record.error = str(e)
            record.save()
            raise

    return wrapper

# Usage
@app.post('/api/charges')
@idempotent
def create_charge(request):
    result = payment_gateway.charge(
        amount=request.data['amount'],
        card=request.data['card_token'],
    )
    return Response({'charge_id': result.id}, status=201)
```

## Database Schema

```sql
CREATE TABLE idempotency_records (
    key VARCHAR(255) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,  -- 'processing', 'completed', 'failed'
    request_hash VARCHAR(64),
    response_body TEXT,
    response_status INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    -- Auto-expire old records
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '24 hours'
);

CREATE INDEX idx_idempotency_expires ON idempotency_records(expires_at);
```

## Client Side

```python
import uuid

def charge_with_retry(amount, card_token, max_retries=3):
    idempotency_key = str(uuid.uuid4())  # Generate ONCE per logical operation

    for attempt in range(max_retries):
        try:
            response = requests.post('/api/charges',
                json={'amount': amount, 'card_token': card_token},
                headers={'Idempotency-Key': idempotency_key},
                timeout=10,
            )
            return response.json()
        except requests.Timeout:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue  # Retry with SAME key
            raise
```

**Critical**: The client must reuse the same idempotency key for retries. A new key = a new operation.'''
    ),
    (
        "thinking/distributed-circuit-breaker",
        "When our downstream Payment API goes down, our entire application hangs because every request waits for the payment timeout (30s). How do we handle downstream failures gracefully?",
        r'''<think>
Circuit breaker pattern — detect downstream failures early and fail fast instead of waiting for timeouts. Three states:
1. Closed (normal): requests pass through
2. Open (failure detected): requests fail immediately
3. Half-Open (testing recovery): let a few requests through to check if the service is back

This prevents cascading failures — instead of 100 requests all waiting 30s, the circuit opens and they fail instantly.
</think>

Use a **circuit breaker** — fail fast instead of waiting for timeouts:

```
Normal:          Circuit CLOSED → requests pass through
Failures pile up: Circuit OPENS  → requests fail immediately (no timeout)
After cooldown:  Circuit HALF-OPEN → test with one request
Service back:    Circuit CLOSES → back to normal
```

## Implementation

```python
import time
import threading
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=30, expected_exceptions=(Exception,)):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._lock = threading.Lock()

    @property
    def state(self):
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time > self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    def call(self, func, *args, **kwargs):
        current_state = self.state

        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpen(
                f"Circuit breaker is open. Retry after {self.recovery_timeout}s"
            )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exceptions as e:
            self._on_failure()
            raise

    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN

# Usage
payment_breaker = CircuitBreaker(
    failure_threshold=5,     # Open after 5 failures
    recovery_timeout=30,     # Try again after 30 seconds
    expected_exceptions=(TimeoutError, ConnectionError),
)

def charge_customer(amount, card_token):
    try:
        return payment_breaker.call(
            payment_api.charge, amount=amount, card_token=card_token
        )
    except CircuitBreakerOpen:
        # Graceful degradation
        queue_for_later(amount, card_token)
        return {'status': 'queued', 'message': 'Payment will be processed shortly'}
```

## With pybreaker Library

```python
import pybreaker

payment_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=30,
    listeners=[pybreaker.CircuitBreakerListener()],
)

@payment_breaker
def charge_customer(amount, card_token):
    return payment_api.charge(amount=amount, card_token=card_token)
```

## Combining with Fallbacks

```python
@app.post('/api/checkout')
def checkout(order):
    try:
        payment = charge_customer(order.total, order.card_token)
        order.payment_id = payment.id
        order.status = 'paid'
    except CircuitBreakerOpen:
        order.status = 'payment_pending'
        task_queue.enqueue(retry_payment, order.id)
        # User sees: "Order received, payment processing"
    except PaymentDeclined:
        order.status = 'payment_failed'
        # User sees: "Payment declined, please try another card"

    order.save()
    return order
```

**Without circuit breaker**: 100 requests × 30s timeout = 50 minutes of wasted server time.
**With circuit breaker**: 5 failures detected, circuit opens, 95 requests fail in <1ms each.'''
    ),
    (
        "thinking/distributed-retry-strategies",
        "Our service calls external APIs that sometimes fail. We added retries but now we're getting rate-limited and making the problem worse. How do I implement retries properly?",
        r'''<think>
Naive retries make things worse because:
1. Immediate retries flood a struggling service
2. All clients retry at the same time (thundering herd)
3. No backoff = constant load even during outage

Proper retry strategy:
1. Exponential backoff (wait longer between each retry)
2. Jitter (randomize wait time to spread out retries)
3. Maximum retry limit
4. Only retry on retryable errors (5xx, timeout — NOT 4xx)
5. Circuit breaker to stop retrying after persistent failure
</think>

## The Retry Strategy That Won't Make Things Worse

### Naive Retry (BAD)

```python
# This DDOS's the failing service
def call_api(url):
    for _ in range(10):
        try:
            return requests.get(url, timeout=5)
        except Exception:
            pass  # Immediate retry, no backoff
```

### Exponential Backoff with Jitter (GOOD)

```python
import random
import time
from functools import wraps

def retry(
    max_retries=3,
    base_delay=1,
    max_delay=60,
    retryable_exceptions=(ConnectionError, TimeoutError),
    retryable_status_codes=(502, 503, 504, 429),
):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    response = func(*args, **kwargs)

                    if hasattr(response, 'status_code'):
                        if response.status_code in retryable_status_codes:
                            if attempt < max_retries:
                                delay = _calculate_delay(attempt, base_delay, max_delay)

                                # Respect Retry-After header
                                retry_after = response.headers.get('Retry-After')
                                if retry_after:
                                    delay = max(delay, int(retry_after))

                                time.sleep(delay)
                                continue
                        if response.status_code >= 400:
                            return response  # 4xx = client error, don't retry

                    return response

                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = _calculate_delay(attempt, base_delay, max_delay)
                        time.sleep(delay)

            raise last_exception or Exception("Max retries exceeded")

        return wrapper
    return decorator

def _calculate_delay(attempt, base_delay, max_delay):
    # Exponential backoff: 1s, 2s, 4s, 8s...
    delay = base_delay * (2 ** attempt)
    # Cap at max_delay
    delay = min(delay, max_delay)
    # Add jitter: randomize between 0 and delay
    delay = delay * random.uniform(0.5, 1.0)
    return delay

# Usage
@retry(max_retries=3, base_delay=1, max_delay=30)
def fetch_user_data(user_id):
    return requests.get(
        f'https://api.example.com/users/{user_id}',
        timeout=10,
    )
```

### With tenacity Library (Production)

```python
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=1, max=60, jitter=2),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    before_sleep=lambda state: logger.warning(
        f"Retry {state.attempt_number} for {state.fn.__name__}"
    ),
)
def call_payment_api(amount, token):
    response = requests.post(
        'https://api.stripe.com/v1/charges',
        data={'amount': amount, 'source': token},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
```

## What to Retry vs Not Retry

| Retry | Don't Retry |
|-------|-------------|
| 500, 502, 503, 504 | 400 Bad Request |
| 429 Too Many Requests | 401 Unauthorized |
| Connection timeout | 403 Forbidden |
| DNS resolution failure | 404 Not Found |
| Connection reset | 422 Validation Error |

**Never retry** non-idempotent operations (POST creating resources) unless you have idempotency keys.'''
    ),
    (
        "thinking/distributed-event-sourcing-intro",
        "What's event sourcing and when should I use it instead of a regular CRUD database?",
        r'''<think>
Event sourcing: instead of storing the current state, store the sequence of events that led to the current state. Like a bank ledger vs a balance.

When to use:
- Audit trail is critical (finance, healthcare)
- Need to reconstruct state at any point in time
- Complex business logic with many state transitions
- Need to replay events (debugging, analytics)

When NOT to use:
- Simple CRUD apps
- When current state is all you need
- Small teams (adds complexity)

Let me explain with a practical example.
</think>

## Event Sourcing vs CRUD

**CRUD**: Store current state, overwrite on changes.
```
Account table: {id: 1, balance: 150, last_updated: "2024-01-15"}
```
Question: How did we get to $150? No idea. History is lost.

**Event Sourcing**: Store the sequence of events.
```
Events:
  1. AccountOpened    {amount: 0}
  2. MoneyDeposited   {amount: 500}
  3. MoneyWithdrawn   {amount: 200}
  4. MoneyDeposited   {amount: 100}
  5. MoneyWithdrawn   {amount: 250}
Current balance: 0 + 500 - 200 + 100 - 250 = $150
```

## Implementation

```python
# Events are immutable facts
@dataclass(frozen=True)
class AccountOpened:
    account_id: str
    owner: str
    timestamp: datetime

@dataclass(frozen=True)
class MoneyDeposited:
    account_id: str
    amount: Decimal
    description: str
    timestamp: datetime

@dataclass(frozen=True)
class MoneyWithdrawn:
    account_id: str
    amount: Decimal
    description: str
    timestamp: datetime

# Aggregate rebuilds state from events
class BankAccount:
    def __init__(self, account_id: str):
        self.id = account_id
        self.balance = Decimal(0)
        self.is_open = False
        self._events = []

    def apply(self, event):
        """Apply an event to update state."""
        match event:
            case AccountOpened():
                self.is_open = True
            case MoneyDeposited():
                self.balance += event.amount
            case MoneyWithdrawn():
                self.balance -= event.amount

    def deposit(self, amount, description):
        if not self.is_open:
            raise AccountClosed()
        event = MoneyDeposited(
            account_id=self.id,
            amount=amount,
            description=description,
            timestamp=datetime.utcnow(),
        )
        self.apply(event)
        self._events.append(event)  # Uncommitted events

    def withdraw(self, amount, description):
        if self.balance < amount:
            raise InsufficientFunds()
        event = MoneyWithdrawn(
            account_id=self.id,
            amount=amount,
            description=description,
            timestamp=datetime.utcnow(),
        )
        self.apply(event)
        self._events.append(event)

# Event store
class EventStore:
    def save(self, aggregate):
        for event in aggregate._events:
            db.execute(
                "INSERT INTO events (aggregate_id, event_type, data, timestamp) "
                "VALUES (%s, %s, %s, %s)",
                (event.account_id, type(event).__name__,
                 json.dumps(asdict(event)), event.timestamp),
            )
        aggregate._events.clear()

    def load(self, account_id) -> BankAccount:
        events = db.query(
            "SELECT * FROM events WHERE aggregate_id = %s ORDER BY timestamp",
            (account_id,),
        )
        account = BankAccount(account_id)
        for event_row in events:
            event = deserialize_event(event_row)
            account.apply(event)
        return account
```

## When to Use Event Sourcing

| Use It | Don't Use It |
|--------|-------------|
| Financial systems (audit trail) | Simple CRUD apps |
| Order processing (state machines) | Blog/CMS |
| Regulatory compliance | Prototype/MVP |
| Need time-travel debugging | Small team (<3 devs) |
| Complex domain with business events | When current state is enough |

**Default**: Start with CRUD. Add event sourcing only when you need audit trails or temporal queries.'''
    ),
    (
        "thinking/distributed-message-queue-selection",
        "We need a message queue for our microservices. Should we use RabbitMQ, Kafka, Redis Streams, or SQS? We have 3 services that need to communicate asynchronously.",
        r'''<think>
Quick comparison:
- RabbitMQ: Traditional message broker, great for task queues, routing, pub/sub. Good default choice.
- Kafka: Event streaming, high throughput, replay-able log. Best for event sourcing, analytics, high volume.
- Redis Streams: Lightweight, already using Redis. Good for simple pub/sub.
- SQS: AWS managed, zero ops. Best if you're all-in on AWS.

For 3 services communicating asynchronously, the complexity of Kafka is probably overkill. RabbitMQ or SQS is the right choice for most small teams.
</think>

## Decision Matrix

| Factor | RabbitMQ | Kafka | Redis Streams | SQS |
|--------|----------|-------|---------------|-----|
| Complexity | Medium | High | Low | Low |
| Throughput | 10K msg/s | 1M msg/s | 100K msg/s | 10K msg/s |
| Message replay | No | Yes | Limited | No |
| Ordering | Per-queue | Per-partition | Per-stream | Best-effort |
| Ops burden | Medium | High | Low (if using Redis) | Zero |
| Best for | Task queues | Event streaming | Simple pub/sub | AWS apps |

## For Your 3-Service Setup

### If you're on AWS → SQS

```python
import boto3

sqs = boto3.client('sqs')

# Producer
sqs.send_message(
    QueueUrl='https://sqs.../order-events',
    MessageBody=json.dumps({'order_id': 123, 'event': 'created'}),
    MessageGroupId='order-123',  # FIFO ordering
)

# Consumer
while True:
    messages = sqs.receive_messages(QueueUrl='...', MaxNumberOfMessages=10, WaitTimeSeconds=20)
    for msg in messages:
        process(json.loads(msg['Body']))
        sqs.delete_message(QueueUrl='...', ReceiptHandle=msg['ReceiptHandle'])
```

Zero ops, pay per message, auto-scaling.

### If self-hosted → RabbitMQ

```python
import pika

# Producer
connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()
channel.exchange_declare(exchange='orders', exchange_type='topic')
channel.basic_publish(
    exchange='orders',
    routing_key='order.created',
    body=json.dumps({'order_id': 123}),
)

# Consumer (Inventory Service)
channel.queue_declare(queue='inventory-updates')
channel.queue_bind(queue='inventory-updates', exchange='orders', routing_key='order.created')
channel.basic_consume(queue='inventory-updates', on_message_callback=handle_order)
channel.start_consuming()
```

### If already using Redis → Redis Streams

```python
import redis

r = redis.Redis()

# Producer
r.xadd('orders', {'event': 'created', 'order_id': '123', 'data': json.dumps(...)})

# Consumer group (each service gets each message exactly once)
r.xgroup_create('orders', 'inventory-service', id='0', mkstream=True)

while True:
    messages = r.xreadgroup('inventory-service', 'worker-1', {'orders': '>'}, count=10, block=5000)
    for stream, msgs in messages:
        for msg_id, data in msgs:
            process(data)
            r.xack('orders', 'inventory-service', msg_id)
```

## My Recommendation

**3 services, small team**: Use **SQS** (if AWS) or **Redis Streams** (if self-hosted with existing Redis). Don't use Kafka unless you need event replay or >100K messages/second.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
