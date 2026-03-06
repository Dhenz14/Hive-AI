"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 7)

Distributed transactions: saga pattern, two-phase commit (2PC), idempotency keys,
and exactly-once semantics in distributed systems.
"""

PAIRS = [
    (
        "thinking/concurrency-saga-pattern",
        r'''We're building an e-commerce checkout that spans 3 services: OrderService,
PaymentService, and InventoryService. Currently we use a distributed transaction
that often times out:

```python
def checkout(cart):
    tx = DistributedTransaction()
    try:
        tx.begin()
        order = OrderService.create_order(cart, tx)
        PaymentService.charge(cart.total, tx)
        InventoryService.reserve(cart.items, tx)
        tx.commit()  # 2PC commit — often times out
    except Exception:
        tx.rollback()
        raise
```

The 2PC commit blocks all three services for 5-10 seconds. How do we replace this
with a saga pattern?''',
        r'''<think>
Two-phase commit (2PC) problems:
1. Blocking — all participants lock resources until coordinator decides
2. Single point of failure — if coordinator crashes between prepare and commit, participants are stuck
3. Latency — round trips between coordinator and all participants
4. Availability — any participant being down blocks the whole transaction

Saga pattern replaces a single distributed transaction with a sequence of local
transactions, each with a compensating action for rollback.

Two saga styles:
1. **Choreography** — each service publishes events, next service reacts
2. **Orchestration** — a central saga orchestrator coordinates steps

For 3 services, orchestration is cleaner. Each step has:
- Forward action (local transaction)
- Compensating action (undo on failure)

Order: CreateOrder -> ChargePayment -> ReserveInventory
Compensate: CancelOrder <- RefundPayment <- ReleaseInventory

Key: each step must be idempotent (safe to retry) and the compensating actions must
be semantically correct (refund, not "undo charge").
</think>

## Saga Orchestrator Pattern

```python
import enum
import uuid
from dataclasses import dataclass, field

class SagaState(enum.Enum):
    STARTED = "started"
    ORDER_CREATED = "order_created"
    PAYMENT_CHARGED = "payment_charged"
    INVENTORY_RESERVED = "inventory_reserved"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    FAILED = "failed"

@dataclass
class SagaContext:
    saga_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: SagaState = SagaState.STARTED
    order_id: str = None
    payment_id: str = None
    reservation_id: str = None
    error: str = None

class CheckoutSaga:
    """Orchestrator for the checkout saga."""

    def __init__(self, order_svc, payment_svc, inventory_svc):
        self.order_svc = order_svc
        self.payment_svc = payment_svc
        self.inventory_svc = inventory_svc

        # Define steps: (forward_action, compensating_action)
        self.steps = [
            (self._create_order, self._cancel_order),
            (self._charge_payment, self._refund_payment),
            (self._reserve_inventory, self._release_inventory),
        ]

    async def execute(self, cart) -> SagaContext:
        ctx = SagaContext()
        completed_steps = []

        for forward, compensate in self.steps:
            try:
                await forward(ctx, cart)
                completed_steps.append(compensate)
            except Exception as e:
                ctx.error = str(e)
                ctx.state = SagaState.COMPENSATING
                # Compensate in reverse order
                for comp in reversed(completed_steps):
                    try:
                        await comp(ctx)
                    except Exception as comp_err:
                        # Log and continue — compensation must be best-effort
                        log.error(f"Compensation failed: {comp_err}")
                ctx.state = SagaState.FAILED
                return ctx

        ctx.state = SagaState.COMPLETED
        return ctx

    async def _create_order(self, ctx, cart):
        ctx.order_id = await self.order_svc.create(
            cart, idempotency_key=ctx.saga_id
        )
        ctx.state = SagaState.ORDER_CREATED

    async def _cancel_order(self, ctx):
        await self.order_svc.cancel(ctx.order_id)

    async def _charge_payment(self, ctx, cart):
        ctx.payment_id = await self.payment_svc.charge(
            cart.total, idempotency_key=f"{ctx.saga_id}-pay"
        )
        ctx.state = SagaState.PAYMENT_CHARGED

    async def _refund_payment(self, ctx):
        await self.payment_svc.refund(ctx.payment_id)

    async def _reserve_inventory(self, ctx, cart):
        ctx.reservation_id = await self.inventory_svc.reserve(
            cart.items, idempotency_key=f"{ctx.saga_id}-inv"
        )
        ctx.state = SagaState.INVENTORY_RESERVED

    async def _release_inventory(self, ctx):
        await self.inventory_svc.release(ctx.reservation_id)
```

**Key differences from 2PC:**
| Aspect | 2PC | Saga |
|--------|-----|------|
| Isolation | Full (locks held) | Partial (intermediate states visible) |
| Blocking | Yes (all participants) | No (each step is local) |
| Rollback | Atomic | Compensating transactions |
| Availability | Lowest participant | Each step independent |
| Complexity | Protocol-level | Application-level |'''
    ),
    (
        "thinking/concurrency-idempotency-keys",
        r'''Our payment API sometimes double-charges customers when retries happen:

```python
@app.post("/api/charge")
async def charge(request: ChargeRequest):
    # Check balance
    account = await db.get_account(request.user_id)
    if account.balance < request.amount:
        raise HTTPException(400, "Insufficient funds")

    # Deduct and record
    await db.execute(
        "UPDATE accounts SET balance = balance - $1 WHERE user_id = $2",
        request.amount, request.user_id,
    )
    await db.execute(
        "INSERT INTO transactions (user_id, amount, type) VALUES ($1, $2, 'charge')",
        request.user_id, request.amount,
    )
    return {"status": "charged", "new_balance": account.balance - request.amount}
```

Client retries on timeout, and the charge happens twice. How do we make this idempotent?''',
        r'''<think>
The problem: if the client sends the same charge request twice (due to timeout + retry),
the server processes it twice because it has no way to know it already handled that request.

Idempotency key approach:
1. Client sends a unique idempotency key with each logical request
2. Server stores the key and its result
3. On duplicate key, server returns the stored result without re-executing

Implementation considerations:
- The idempotency key check and the actual operation must be in the SAME database transaction
- Otherwise there's a race: two requests with same key arrive simultaneously, both check
  "key not seen", both proceed
- Key storage needs TTL (don't keep forever)
- The response must be stored too, so we can return the same response on retry

Also, the original code has a TOCTOU race: check balance, then deduct. Between check and
deduct, another request could also pass the check. Need to use a conditional update:
  UPDATE accounts SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1
</think>

## Fix: Idempotency Keys with Atomic Operations

```python
import hashlib
from datetime import datetime, timedelta

@app.post("/api/charge")
async def charge(request: ChargeRequest):
    # Client MUST provide idempotency key
    idem_key = request.idempotency_key
    if not idem_key:
        raise HTTPException(400, "idempotency_key required")

    async with db.transaction() as tx:
        # 1. Check for existing result with this key
        existing = await tx.fetchrow(
            "SELECT response_body, status_code FROM idempotency_keys "
            "WHERE key = $1 AND created_at > $2 FOR UPDATE",
            idem_key,
            datetime.utcnow() - timedelta(hours=24),
        )
        if existing:
            # Already processed — return stored result
            return JSONResponse(
                content=json.loads(existing["response_body"]),
                status_code=existing["status_code"],
            )

        # 2. Lock the idempotency key (prevent concurrent duplicates)
        await tx.execute(
            "INSERT INTO idempotency_keys (key, status, created_at) "
            "VALUES ($1, 'processing', NOW())",
            idem_key,
        )

        # 3. Atomic balance deduction (no TOCTOU race)
        result = await tx.fetchrow(
            "UPDATE accounts SET balance = balance - $1 "
            "WHERE user_id = $2 AND balance >= $1 "
            "RETURNING balance",
            request.amount, request.user_id,
        )
        if not result:
            response = {"status": "failed", "error": "Insufficient funds"}
            status_code = 400
        else:
            # 4. Record the transaction
            await tx.execute(
                "INSERT INTO transactions "
                "(user_id, amount, type, idempotency_key) "
                "VALUES ($1, $2, 'charge', $3)",
                request.user_id, request.amount, idem_key,
            )
            response = {
                "status": "charged",
                "new_balance": float(result["balance"]),
            }
            status_code = 200

        # 5. Store the response for future duplicate requests
        await tx.execute(
            "UPDATE idempotency_keys "
            "SET status = 'completed', response_body = $1, status_code = $2 "
            "WHERE key = $3",
            json.dumps(response), status_code, idem_key,
        )

    return JSONResponse(content=response, status_code=status_code)
```

**Client side:**

```python
async def charge_with_retry(amount, user_id, max_retries=3):
    idem_key = str(uuid.uuid4())  # one key per logical operation
    for attempt in range(max_retries):
        try:
            resp = await client.post("/api/charge", json={
                "amount": amount,
                "user_id": user_id,
                "idempotency_key": idem_key,  # same key on retry!
            })
            return resp.json()
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # exponential backoff
```

**Critical points:**
- Idempotency check + operation in same DB transaction = atomic
- `FOR UPDATE` prevents race between concurrent duplicate requests
- `WHERE balance >= $1` eliminates the TOCTOU bug
- 24-hour TTL on keys prevents unbounded storage growth'''
    ),
    (
        "thinking/concurrency-two-phase-commit",
        r'''We need to keep data consistent between our PostgreSQL database and Elasticsearch
index. Currently writes succeed in Postgres but sometimes fail in ES, leaving them
out of sync:

```python
async def create_product(product: Product):
    # Step 1: Write to Postgres
    await db.execute(
        "INSERT INTO products (id, name, price) VALUES ($1, $2, $3)",
        product.id, product.name, product.price,
    )

    # Step 2: Index in Elasticsearch
    await es.index(
        index="products",
        id=product.id,
        document=product.dict(),
    )
    # If step 2 fails, Postgres has the data but ES doesn't!
```

What are the patterns for keeping two data stores consistent?''',
        r'''<think>
This is the dual-write problem. Writing to two systems without coordination means
either can fail independently.

Options:
1. **2PC** — both systems participate in a transaction. ES doesn't support 2PC though.
2. **Transactional outbox** — write to Postgres + an outbox table in one transaction,
   then a separate process reads the outbox and updates ES. This is the most reliable.
3. **CDC (Change Data Capture)** — use Postgres WAL/logical replication to stream
   changes to ES via Debezium or similar.
4. **Event sourcing** — write events to an event store, project to both Postgres and ES.

Transactional outbox is the most practical:
- Single Postgres transaction writes both the product AND an outbox event
- A poller or CDC reader picks up outbox events and sends to ES
- If ES write fails, retry from outbox
- Outbox events are processed at-least-once, so ES indexing must be idempotent (it is — upsert by ID)
</think>

## Pattern: Transactional Outbox

```python
# Step 1: Write data + outbox event in ONE transaction
async def create_product(product: Product):
    async with db.transaction() as tx:
        await tx.execute(
            "INSERT INTO products (id, name, price) VALUES ($1, $2, $3)",
            product.id, product.name, product.price,
        )
        # Outbox event in the SAME transaction
        await tx.execute(
            "INSERT INTO outbox_events "
            "(id, aggregate_type, aggregate_id, event_type, payload, created_at) "
            "VALUES ($1, 'product', $2, 'product_created', $3, NOW())",
            str(uuid.uuid4()), product.id, json.dumps(product.dict()),
        )
    # Both writes succeed or both fail — atomically consistent

# Step 2: Background worker processes outbox events
class OutboxProcessor:
    def __init__(self, db, es):
        self.db = db
        self.es = es

    async def run(self):
        """Poll outbox and relay events to Elasticsearch."""
        while True:
            async with self.db.transaction() as tx:
                # Fetch unprocessed events (with row lock)
                events = await tx.fetch(
                    "SELECT * FROM outbox_events "
                    "WHERE processed_at IS NULL "
                    "ORDER BY created_at "
                    "LIMIT 100 "
                    "FOR UPDATE SKIP LOCKED"
                )

                for event in events:
                    try:
                        await self._handle_event(event)
                        await tx.execute(
                            "UPDATE outbox_events SET processed_at = NOW() "
                            "WHERE id = $1",
                            event["id"],
                        )
                    except Exception as e:
                        await tx.execute(
                            "UPDATE outbox_events "
                            "SET retry_count = retry_count + 1, "
                            "    last_error = $1 "
                            "WHERE id = $2",
                            str(e), event["id"],
                        )

            await asyncio.sleep(1)  # poll interval

    async def _handle_event(self, event):
        payload = json.loads(event["payload"])
        if event["event_type"] == "product_created":
            # ES index is idempotent by document ID — safe to retry
            await self.es.index(
                index="products",
                id=event["aggregate_id"],
                document=payload,
            )
        elif event["event_type"] == "product_updated":
            await self.es.update(
                index="products",
                id=event["aggregate_id"],
                doc=payload,
            )
```

```sql
-- Outbox table schema
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(50) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    retry_count INT DEFAULT 0,
    last_error TEXT
);

CREATE INDEX idx_outbox_unprocessed
    ON outbox_events (created_at)
    WHERE processed_at IS NULL;
```

**Why this works:**
- **Atomicity**: Product + outbox event are in one Postgres transaction
- **Reliability**: If ES is down, events queue up in the outbox
- **Idempotency**: ES index by ID is naturally idempotent
- **Ordering**: Events processed in created_at order
- **Scalability**: `FOR UPDATE SKIP LOCKED` allows multiple processor instances'''
    ),
    (
        "thinking/concurrency-exactly-once-kafka",
        r'''Our Kafka consumer processes payment events but sometimes processes the same
event twice, causing duplicate charges:

```python
from kafka import KafkaConsumer

consumer = KafkaConsumer(
    'payment-events',
    group_id='payment-processor',
    auto_offset_reset='earliest',
    enable_auto_commit=True,
)

for message in consumer:
    event = json.loads(message.value)
    process_payment(event)  # may take 5-10 seconds
    # auto-commit happens periodically in background
```

If the consumer crashes after process_payment() but before auto-commit, the event
gets reprocessed on restart. How do we achieve exactly-once processing?''',
        r'''<think>
The problem: auto-commit runs on a timer (default 5 seconds). If the consumer crashes
after processing but before the next auto-commit, the offset isn't saved. On restart,
the consumer re-reads and reprocesses those events.

Exactly-once in distributed systems is really "effectively once" — achieved through
at-least-once delivery + idempotent processing.

Approaches:
1. **Manual offset commit after processing** — at-least-once (still needs idempotency)
2. **Transactional outbox + idempotency** — store offset and result in same DB transaction
3. **Kafka transactions** — produce-consume in a Kafka transaction (for Kafka-to-Kafka only)

The most robust: store the consumer offset in the SAME database transaction as the
business logic. When we restart, we read our last committed offset from the DB and
seek to it. This gives us exactly-once because:
- If DB commit succeeds, offset is saved — won't reprocess
- If DB commit fails, offset isn't saved — will reprocess (which is fine, it's a retry)
</think>

## Exactly-Once via Idempotent Consumer + Transactional Offset Storage

```python
from kafka import KafkaConsumer, TopicPartition

class ExactlyOnceConsumer:
    def __init__(self, topic, group_id, db):
        self.db = db
        self.consumer = KafkaConsumer(
            bootstrap_servers='kafka:9092',
            group_id=group_id,
            enable_auto_commit=False,  # we manage offsets ourselves
            auto_offset_reset='earliest',
        )
        self.topic = topic
        self.consumer.subscribe([topic])

    async def run(self):
        # On startup, seek to last committed offset from our DB
        await self._seek_to_stored_offsets()

        for message in self.consumer:
            await self._process_exactly_once(message)

    async def _seek_to_stored_offsets(self):
        """Load offsets from DB instead of Kafka __consumer_offsets."""
        self.consumer.poll(0)  # trigger partition assignment
        for tp in self.consumer.assignment():
            offset = await self.db.fetchval(
                "SELECT committed_offset FROM consumer_offsets "
                "WHERE topic = $1 AND partition_num = $2 AND group_id = $3",
                tp.topic, tp.partition, self.consumer.config['group_id'],
            )
            if offset is not None:
                self.consumer.seek(tp, offset + 1)

    async def _process_exactly_once(self, message):
        event = json.loads(message.value)
        event_id = event.get("event_id")

        async with self.db.transaction() as tx:
            # 1. Idempotency check: have we seen this event?
            already = await tx.fetchval(
                "SELECT 1 FROM processed_events WHERE event_id = $1",
                event_id,
            )
            if already:
                # Already processed — just update offset and skip
                await self._store_offset(tx, message)
                return

            # 2. Process the business logic (within the transaction)
            await self._handle_payment(tx, event)

            # 3. Record that we processed this event
            await tx.execute(
                "INSERT INTO processed_events (event_id, processed_at) "
                "VALUES ($1, NOW())",
                event_id,
            )

            # 4. Store offset in the SAME transaction
            await self._store_offset(tx, message)

        # Transaction committed = event processed + offset saved atomically

    async def _store_offset(self, tx, message):
        await tx.execute(
            "INSERT INTO consumer_offsets "
            "(topic, partition_num, group_id, committed_offset) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (topic, partition_num, group_id) "
            "DO UPDATE SET committed_offset = $4",
            message.topic, message.partition,
            self.consumer.config['group_id'], message.offset,
        )

    async def _handle_payment(self, tx, event):
        await tx.execute(
            "INSERT INTO payments (payment_id, user_id, amount, status) "
            "VALUES ($1, $2, $3, 'completed')",
            event["payment_id"], event["user_id"], event["amount"],
        )
```

```sql
CREATE TABLE consumer_offsets (
    topic VARCHAR(255),
    partition_num INT,
    group_id VARCHAR(255),
    committed_offset BIGINT,
    PRIMARY KEY (topic, partition_num, group_id)
);

CREATE TABLE processed_events (
    event_id VARCHAR(255) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL
);
-- Periodically purge old entries:
-- DELETE FROM processed_events WHERE processed_at < NOW() - INTERVAL '7 days';
```

**Why this is exactly-once:**
1. Business logic + offset commit in one DB transaction
2. If transaction commits: event processed, offset saved — won't reprocess
3. If transaction fails: neither saved — will retry (safe due to idempotency check)
4. Idempotency check catches edge cases (e.g., Kafka rebalance delivers same event to new consumer)'''
    ),
    (
        "thinking/concurrency-distributed-lock",
        r'''We run 5 instances of our billing service. A cron job triggers all 5 at midnight
to generate monthly invoices. Without coordination, all 5 generate duplicate invoices:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=0)
async def generate_monthly_invoices():
    customers = await db.fetch("SELECT id FROM customers WHERE active = true")
    for customer in customers:
        invoice = await create_invoice(customer['id'])
        await send_invoice_email(invoice)
```

All 5 instances run this at midnight. How do we ensure only one instance runs the job?''',
        r'''<think>
This is the distributed mutex / leader election problem. We need exactly one instance
to run the job, even though all 5 are identically configured.

Options:
1. **Database advisory lock** — PostgreSQL pg_advisory_lock, simple and reliable
2. **Redis distributed lock (Redlock)** — SET NX with expiry
3. **ZooKeeper / etcd lease** — strong consistency, more infrastructure
4. **Designate one instance** — simplest but no failover

For a cron job, a database advisory lock is the simplest since we already have Postgres.
The pattern:
1. Try to acquire lock (non-blocking)
2. If acquired, run the job, then release
3. If not acquired, skip (another instance is running it)

Important considerations:
- Lock must have a TTL / expiry in case the holder crashes
- The lock ID should be deterministic (same job = same lock ID)
- Need to handle the case where the job takes longer than the lock TTL
- Idempotency as a safety net (in case lock fails and two instances run)

Redis SET NX is popular for this:
  SET lock:monthly-invoices <instance-id> NX PX 300000
  - NX = only set if not exists
  - PX 300000 = expire after 5 minutes
</think>

## Solution 1: PostgreSQL Advisory Lock

```python
import hashlib

def job_lock_id(job_name: str) -> int:
    """Deterministic lock ID from job name."""
    return int(hashlib.md5(job_name.encode()).hexdigest()[:15], 16)

@scheduler.scheduled_job('cron', hour=0)
async def generate_monthly_invoices():
    lock_id = job_lock_id("monthly-invoices")

    # Try to acquire (non-blocking)
    acquired = await db.fetchval(
        "SELECT pg_try_advisory_lock($1)", lock_id
    )
    if not acquired:
        logger.info("Another instance is running monthly invoices, skipping.")
        return

    try:
        customers = await db.fetch(
            "SELECT id FROM customers WHERE active = true"
        )
        for customer in customers:
            invoice = await create_invoice(customer['id'])
            await send_invoice_email(invoice)
        logger.info(f"Generated {len(customers)} invoices.")
    finally:
        await db.execute("SELECT pg_advisory_unlock($1)", lock_id)
```

## Solution 2: Redis Distributed Lock

```python
import redis.asyncio as redis
import uuid
import asyncio

class DistributedLock:
    def __init__(self, redis_client, name: str, ttl: int = 300):
        self.redis = redis_client
        self.name = f"lock:{name}"
        self.ttl = ttl
        self.token = str(uuid.uuid4())

    async def acquire(self) -> bool:
        return await self.redis.set(
            self.name, self.token, nx=True, px=self.ttl * 1000
        )

    async def release(self):
        # Only release if we still own the lock (Lua for atomicity)
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        await self.redis.eval(script, 1, self.name, self.token)

    async def extend(self, extra_ttl: int = None):
        """Extend lock TTL if job is still running."""
        ttl = extra_ttl or self.ttl
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("pexpire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        await self.redis.eval(script, 1, self.name, self.token, ttl * 1000)

    async def __aenter__(self):
        if not await self.acquire():
            raise LockNotAcquired(f"Could not acquire lock {self.name}")
        return self

    async def __aexit__(self, *exc):
        await self.release()

redis_client = redis.Redis(host='redis', port=6379)

@scheduler.scheduled_job('cron', hour=0)
async def generate_monthly_invoices():
    lock = DistributedLock(redis_client, "monthly-invoices", ttl=600)
    try:
        async with lock:
            customers = await db.fetch(
                "SELECT id FROM customers WHERE active = true"
            )
            for customer in customers:
                invoice = await create_invoice(customer['id'])
                await send_invoice_email(invoice)
    except LockNotAcquired:
        logger.info("Another instance holds the lock, skipping.")
```

**Safety net:** Even with locking, make `create_invoice` idempotent:

```python
async def create_invoice(customer_id: str):
    # Idempotency: check if invoice for this month already exists
    existing = await db.fetchval(
        "SELECT id FROM invoices "
        "WHERE customer_id = $1 AND period = date_trunc('month', NOW())",
        customer_id,
    )
    if existing:
        return existing  # already created

    return await db.fetchval(
        "INSERT INTO invoices (customer_id, period, amount) "
        "VALUES ($1, date_trunc('month', NOW()), $2) RETURNING id",
        customer_id, await calculate_amount(customer_id),
    )
```

**Lock comparison:**

| Method | Consistency | Complexity | Failure Mode |
|--------|-----------|-----------|-------------|
| PG advisory lock | Strong (single DB) | Low | Lock released on disconnect |
| Redis SET NX | Best-effort | Medium | TTL expiry if holder crashes |
| Redlock (multi-node) | Stronger | High | Tolerates Redis node failures |
| etcd lease | Strong (Raft consensus) | High | Lease expires on failure |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
