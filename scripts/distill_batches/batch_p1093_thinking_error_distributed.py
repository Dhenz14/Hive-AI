"""Thinking-trace pairs: distributed system error handling."""

PAIRS = [
    (
        "thinking/error-handling",
        r'''How do I implement the Saga pattern for distributed transactions? I have a microservices architecture where an order involves: payment service, inventory service, and shipping service. If any step fails, I need to compensate the previous successful steps.''',
        r'''<think>
The Saga pattern handles distributed transactions by breaking them into a sequence of local transactions, each with a compensating action (undo). There are two types:
1. Choreography: each service publishes events that trigger the next step
2. Orchestration: a central coordinator manages the saga steps

I initially considered choreography since it is more decoupled, but wait -- with choreography, no single service has visibility into the overall transaction state. Debugging a failed order means tracing events across three services. For this example, orchestration is clearer because a central coordinator owns the saga state and can log every step.

The saga steps are:
1. Reserve inventory -> compensate: release inventory
2. Charge payment -> compensate: refund payment
3. Create shipment -> compensate: cancel shipment

Hmm, the order matters here. Should payment come before inventory reservation? If we charge first and then inventory reservation fails, we need to refund -- which could take days to process. Actually, reserving inventory first is cheaper to compensate (just release the hold), so it should come before payment. Therefore the current ordering is correct.

If any step fails, run compensating actions for all previously successful steps in reverse order. But what if a compensation itself fails? That is the tricky part -- compensation failures need their own retry mechanism, since leaving a partial transaction is worse than the original failure.
</think>

The Saga pattern manages distributed transactions through a sequence of local transactions with compensating actions. Here is an orchestrator-based implementation:

```python
import asyncio
import uuid
import time
import logging
from typing import Callable, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SagaStepStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"


@dataclass
class SagaStep:
    """A single step in a saga with its compensating action."""
    name: str
    action: Callable            # Forward action
    compensation: Callable      # Undo action
    status: SagaStepStatus = SagaStepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None


class SagaExecutionError(Exception):
    """Raised when a saga fails and compensation is needed."""
    def __init__(self, message, failed_step, compensation_errors=None):
        super().__init__(message)
        self.failed_step = failed_step
        self.compensation_errors = compensation_errors or []


class SagaOrchestrator:
    """Orchestrate a sequence of distributed transactions."""

    def __init__(self, name: str):
        self.name = name
        self.saga_id = str(uuid.uuid4())[:8]
        self.steps: list[SagaStep] = []
        self.context: dict = {}  # Shared context between steps

    def add_step(
        self,
        name: str,
        action: Callable,
        compensation: Callable,
    ) -> "SagaOrchestrator":
        """Add a step with its compensating action."""
        self.steps.append(SagaStep(
            name=name, action=action, compensation=compensation,
        ))
        return self

    async def execute(self) -> dict:
        """Execute the saga. If any step fails, compensate in reverse."""
        logger.info("[Saga %s/%s] Starting", self.name, self.saga_id)
        completed_steps = []

        for step in self.steps:
            logger.info("[Saga %s] Step: %s", self.saga_id, step.name)
            try:
                # Execute the forward action
                if asyncio.iscoroutinefunction(step.action):
                    step.result = await step.action(self.context)
                else:
                    step.result = step.action(self.context)

                step.status = SagaStepStatus.COMPLETED
                completed_steps.append(step)
                logger.info("[Saga %s] Step '%s' completed", self.saga_id, step.name)

            except Exception as e:
                step.status = SagaStepStatus.FAILED
                step.error = str(e)
                logger.error(
                    "[Saga %s] Step '%s' FAILED: %s",
                    self.saga_id, step.name, e,
                )

                # Compensate all completed steps in reverse order
                comp_errors = await self._compensate(completed_steps)

                raise SagaExecutionError(
                    f"Saga '{self.name}' failed at step '{step.name}': {e}",
                    failed_step=step.name,
                    compensation_errors=comp_errors,
                ) from e

        logger.info("[Saga %s] All steps completed successfully", self.saga_id)
        return self.context

    async def _compensate(self, completed_steps: list[SagaStep]) -> list[str]:
        """Run compensating actions in reverse order."""
        errors = []
        for step in reversed(completed_steps):
            step.status = SagaStepStatus.COMPENSATING
            logger.info("[Saga %s] Compensating: %s", self.saga_id, step.name)

            try:
                if asyncio.iscoroutinefunction(step.compensation):
                    await step.compensation(self.context)
                else:
                    step.compensation(self.context)

                step.status = SagaStepStatus.COMPENSATED
                logger.info("[Saga %s] Compensated: %s", self.saga_id, step.name)

            except Exception as e:
                step.status = SagaStepStatus.COMPENSATION_FAILED
                error_msg = f"Compensation failed for '{step.name}': {e}"
                errors.append(error_msg)
                logger.critical("[Saga %s] %s", self.saga_id, error_msg)
                # Continue compensating remaining steps even if one fails

        return errors


# ============================================================
# USAGE: Order processing saga
# ============================================================

async def create_order_saga(order_data: dict) -> dict:
    """Process an order across multiple services using a saga."""

    saga = SagaOrchestrator("create-order")

    # Step 1: Reserve inventory
    async def reserve_inventory(ctx):
        result = await inventory_service.reserve(
            items=order_data["items"],
        )
        ctx["reservation_id"] = result["reservation_id"]
        return result

    async def release_inventory(ctx):
        await inventory_service.release(
            reservation_id=ctx["reservation_id"],
        )

    # Step 2: Process payment
    async def charge_payment(ctx):
        result = await payment_service.charge(
            customer_id=order_data["customer_id"],
            amount=order_data["total"],
            idempotency_key=f"order-{saga.saga_id}",
        )
        ctx["payment_id"] = result["payment_id"]
        return result

    async def refund_payment(ctx):
        await payment_service.refund(
            payment_id=ctx["payment_id"],
            reason="Order saga compensation",
        )

    # Step 3: Create shipment
    async def create_shipment(ctx):
        result = await shipping_service.create_shipment(
            items=order_data["items"],
            address=order_data["shipping_address"],
        )
        ctx["shipment_id"] = result["shipment_id"]
        return result

    async def cancel_shipment(ctx):
        await shipping_service.cancel(
            shipment_id=ctx["shipment_id"],
        )

    # Build the saga
    saga.add_step("reserve_inventory", reserve_inventory, release_inventory)
    saga.add_step("charge_payment", charge_payment, refund_payment)
    saga.add_step("create_shipment", create_shipment, cancel_shipment)

    try:
        result = await saga.execute()
        # Save the order with all service IDs
        order = await db.create_order({
            "customer_id": order_data["customer_id"],
            "items": order_data["items"],
            "reservation_id": result["reservation_id"],
            "payment_id": result["payment_id"],
            "shipment_id": result["shipment_id"],
            "status": "confirmed",
        })
        return {"status": "success", "order": order}

    except SagaExecutionError as e:
        logger.error("Order saga failed: %s", e)
        if e.compensation_errors:
            # Compensation also failed -- needs manual intervention
            logger.critical(
                "MANUAL INTERVENTION NEEDED: %s",
                e.compensation_errors,
            )
            alert_ops_team(saga.saga_id, e.compensation_errors)

        return {
            "status": "failed",
            "error": str(e),
            "failed_step": e.failed_step,
        }
```

**Saga pattern key points:**
1. Each step has a forward action and a compensating (undo) action
2. On failure, compensate all completed steps **in reverse order**
3. Compensating actions must be **idempotent** (safe to retry)
4. If compensation fails, alert for manual intervention
5. Use idempotency keys to prevent duplicate charges/reservations
6. Log every step for audit trail and debugging''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement idempotency in API endpoints? I want to ensure that retried requests (due to network failures) do not cause duplicate side effects like double charges or duplicate record creation.''',
        r'''<think>
Idempotency means the same request can be safely retried without changing the result. There are several approaches:
1. Idempotency keys: client sends a unique key, server stores the result and returns it on retry
2. Natural idempotency: design operations to be naturally idempotent (e.g., SET vs INCREMENT)
3. Conditional operations: use IF-NOT-EXISTS or version checks
4. Request deduplication: store processed request IDs

My first thought was to just use natural idempotency everywhere (make all operations use SET semantics). But wait -- not all operations can be made naturally idempotent. An "add item to cart" is inherently non-idempotent because the user might intentionally add the same item twice. You cannot tell a duplicate request from an intentional repeat without an external key.

I considered using request hashing (hash of the request body) as a deduplication key, but actually that fails for the same reason -- two intentional identical requests produce the same hash. Therefore the idempotency key approach, where the client generates a unique key per intended operation, is the most general solution. Stripe uses this pattern (Idempotency-Key header), and it handles both accidental retries and intentional duplicates correctly.

Hmm, one subtlety: how long should the server store idempotency keys? Forever would waste storage. Since retries typically happen within minutes, a TTL of 24-48 hours is practical.
</think>

Idempotency ensures retried requests produce the same result without duplicate side effects. Here is a comprehensive implementation:

```python
import uuid
import time
import json
import hashlib
import logging
from typing import Optional, Any
from functools import wraps
from fastapi import FastAPI, Request, Response, Header, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
app = FastAPI()


# ============================================================
# IDEMPOTENCY KEY STORE
# ============================================================

class IdempotencyStore:
    """Store and retrieve idempotency results.
    In production, use Redis or a database.
    """

    def __init__(self, ttl: int = 86400):
        self._store = {}  # key -> (response, created_at)
        self.ttl = ttl

    def get(self, key: str) -> Optional[dict]:
        """Get a stored response for an idempotency key."""
        entry = self._store.get(key)
        if entry is None:
            return None
        response, created_at = entry
        if time.time() - created_at > self.ttl:
            del self._store[key]
            return None
        return response

    def set(self, key: str, response: dict):
        """Store a response for an idempotency key."""
        self._store[key] = (response, time.time())

    def lock(self, key: str) -> bool:
        """Try to acquire a lock for processing.
        Returns True if lock acquired, False if already processing.
        """
        lock_key = f"lock:{key}"
        if lock_key in self._store:
            _, locked_at = self._store[lock_key]
            if time.time() - locked_at < 30:  # Lock timeout
                return False
        self._store[lock_key] = (True, time.time())
        return True

    def unlock(self, key: str):
        lock_key = f"lock:{key}"
        self._store.pop(lock_key, None)


idem_store = IdempotencyStore(ttl=86400)


# ============================================================
# IDEMPOTENCY MIDDLEWARE
# ============================================================

def idempotent(func):
    """Decorator that makes an endpoint idempotent via Idempotency-Key header."""

    @wraps(func)
    async def wrapper(*args, idempotency_key: Optional[str] = Header(None), **kwargs):
        if idempotency_key is None:
            # No idempotency key -- process normally
            return await func(*args, **kwargs)

        # Check if we already processed this key
        existing = idem_store.get(idempotency_key)
        if existing is not None:
            logger.info(
                "Returning cached response for key: %s",
                idempotency_key,
            )
            return JSONResponse(
                content=existing["body"],
                status_code=existing["status_code"],
                headers={"X-Idempotency-Replayed": "true"},
            )

        # Try to acquire processing lock
        if not idem_store.lock(idempotency_key):
            raise HTTPException(
                status_code=409,
                detail="Request with this idempotency key is already being processed",
            )

        try:
            # Process the request
            response = await func(*args, **kwargs)

            # Store the result
            if isinstance(response, JSONResponse):
                body = json.loads(response.body)
                status = response.status_code
            elif isinstance(response, dict):
                body = response
                status = 200
            else:
                body = response
                status = 200

            idem_store.set(idempotency_key, {
                "body": body,
                "status_code": status,
            })

            return response

        except HTTPException:
            raise  # Do not cache client errors
        except Exception as e:
            # Do NOT cache server errors -- allow retry
            logger.error("Request failed (not cached): %s", e)
            raise
        finally:
            idem_store.unlock(idempotency_key)

    return wrapper


# ============================================================
# USAGE: Idempotent payment endpoint
# ============================================================

@app.post("/api/payments")
@idempotent
async def create_payment(request: Request):
    body = await request.json()

    # Process payment
    payment = await payment_service.charge(
        customer_id=body["customer_id"],
        amount=body["amount"],
        currency=body["currency"],
    )

    return {
        "payment_id": payment["id"],
        "status": payment["status"],
        "amount": body["amount"],
    }

# Client usage:
# POST /api/payments
# Headers: Idempotency-Key: <unique-uuid>
# Body: {"customer_id": "C1", "amount": 99.99, "currency": "USD"}
#
# If the network fails and client retries with the same Idempotency-Key,
# the server returns the cached response without charging again.


# ============================================================
# NATURAL IDEMPOTENCY PATTERNS
# ============================================================

# PATTERN 1: Use PUT with specific ID instead of POST
# Idempotent by design -- creating the same resource twice
# just overwrites with the same data.

@app.put("/api/orders/{order_id}")
async def create_or_update_order(order_id: str, request: Request):
    body = await request.json()
    # Upsert: insert or update
    order = await db.upsert_order(order_id, body)
    return order

# PATTERN 2: Conditional creation with IF-NOT-EXISTS

async def create_user_idempotent(email: str, data: dict):
    """Create user only if they do not already exist."""
    try:
        existing = await db.get_user_by_email(email)
        if existing:
            return existing  # Already exists -- return existing
    except NotFoundError:
        pass

    return await db.create_user({**data, "email": email})

# PATTERN 3: Version-based updates (optimistic locking)

@app.put("/api/accounts/{account_id}/balance")
async def update_balance(account_id: str, request: Request):
    body = await request.json()
    expected_version = body["version"]
    new_balance = body["balance"]

    # Only update if version matches
    updated = await db.execute(
        """
        UPDATE accounts
        SET balance = $1, version = version + 1
        WHERE id = $2 AND version = $3
        RETURNING *
        """,
        new_balance, account_id, expected_version,
    )

    if not updated:
        raise HTTPException(
            status_code=409,
            detail="Account was modified by another request",
        )

    return updated

# PATTERN 4: Content-based deduplication

def compute_request_fingerprint(body: dict) -> str:
    """Generate a deterministic fingerprint for deduplication."""
    canonical = json.dumps(body, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

**Idempotency implementation rules:**
1. Cache successful responses, NOT errors (allow retrying failures)
2. Use a TTL on cached responses (24 hours is typical)
3. Lock during processing to prevent concurrent duplicate execution
4. Return HTTP 409 if the same key is being processed concurrently
5. Add `X-Idempotency-Replayed: true` header so clients know it is a cached response
6. The client generates the idempotency key (UUID), not the server''',
    ),
    (
        "thinking/error-handling",
        r'''How do I achieve exactly-once semantics in a distributed system? Is it even possible? What practical approaches come closest?''',
        r'''<think>
True exactly-once semantics are impossible in distributed systems (due to the Two Generals Problem and network partitions). Could we use two-phase commit to guarantee it? Hmm, 2PC can ensure atomicity across participants, but it blocks if the coordinator crashes, and it does not survive network partitions. Therefore it is not practical for microservices that need to stay available.

However, we can achieve "effectively exactly-once" through:

1. At-least-once delivery + idempotent processing = effectively exactly-once
2. Transactional outbox pattern
3. Log-based messaging (Kafka with transactions)
4. Two-phase commit (limited, not recommended for microservices)

I initially thought Kafka transactions gave true exactly-once, but actually Kafka's "exactly-once" only applies within Kafka itself (producer to broker to consumer). Once the consumer performs a side effect (like writing to a database), you are back to needing idempotent processing. Therefore the practical approach is: accept that messages may be delivered more than once, and make processing idempotent. The guarantee becomes: "every message is processed at least once, but the effect is applied exactly once."

Wait -- there is an additional nuance. At-least-once delivery itself requires persistent acknowledgment. If the consumer crashes after processing but before acknowledging, the message is redelivered. Since the processing was idempotent, the redelivery produces no duplicate side effects.
</think>

True exactly-once semantics are theoretically impossible in distributed systems (Two Generals Problem). However, you can achieve **effectively exactly-once** through idempotent processing:

```python
import asyncio
import json
import time
import uuid
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ============================================================
# THE REALITY: Exactly-once = At-least-once + Idempotent processing
# ============================================================

# You CANNOT prevent duplicate delivery in a distributed system.
# But you CAN prevent duplicate EFFECTS by making processing idempotent.

# ============================================================
# PATTERN 1: Transactional Outbox
# ============================================================
# Instead of: "write to DB, then publish message" (two systems, no atomicity)
# Do: "write to DB AND outbox table in one transaction, then publish from outbox"

class TransactionalOutbox:
    """Write business data and outbox messages in a single DB transaction."""

    def __init__(self, db):
        self.db = db

    async def execute_with_outbox(self, business_query, message):
        """Execute a business operation and queue a message atomically."""
        async with self.db.transaction() as tx:
            # Step 1: Execute business logic
            await tx.execute(business_query)

            # Step 2: Write message to outbox table (SAME transaction)
            await tx.execute(
                """
                INSERT INTO outbox (id, topic, payload, created_at, status)
                VALUES ($1, $2, $3, $4, 'pending')
                """,
                str(uuid.uuid4()),
                message["topic"],
                json.dumps(message["payload"]),
                time.time(),
            )
            # Both succeed or both fail -- atomic!

    async def publish_pending(self, publisher):
        """Background task: publish pending outbox messages."""
        while True:
            messages = await self.db.fetch(
                """
                SELECT id, topic, payload FROM outbox
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT 100
                FOR UPDATE SKIP LOCKED
                """
            )

            for msg in messages:
                try:
                    await publisher.publish(
                        topic=msg["topic"],
                        payload=json.loads(msg["payload"]),
                        message_id=msg["id"],  # For consumer dedup
                    )
                    await self.db.execute(
                        "UPDATE outbox SET status = 'published' WHERE id = $1",
                        msg["id"],
                    )
                except Exception as e:
                    logger.warning("Failed to publish %s: %s", msg["id"], e)
                    # Will retry on next iteration

            await asyncio.sleep(1)  # Poll interval


# ============================================================
# PATTERN 2: Idempotent Consumer
# ============================================================

class IdempotentConsumer:
    """Process messages exactly once using a processed-messages table."""

    def __init__(self, db, consumer_group: str):
        self.db = db
        self.consumer_group = consumer_group

    async def process_message(self, message_id: str, handler, payload: dict):
        """Process a message idempotently."""

        # Check if already processed
        existing = await self.db.fetchrow(
            """
            SELECT id FROM processed_messages
            WHERE message_id = $1 AND consumer_group = $2
            """,
            message_id, self.consumer_group,
        )

        if existing:
            logger.info("Skipping duplicate message: %s", message_id)
            return  # Already processed

        # Process in a transaction with the dedup record
        async with self.db.transaction() as tx:
            # Execute the business logic
            result = await handler(payload, tx)

            # Record that we processed this message
            await tx.execute(
                """
                INSERT INTO processed_messages
                (message_id, consumer_group, processed_at, result)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (message_id, consumer_group) DO NOTHING
                """,
                message_id,
                self.consumer_group,
                time.time(),
                json.dumps(result) if result else None,
            )

        return result


# ============================================================
# PATTERN 3: Event Sourcing for exactly-once state changes
# ============================================================

@dataclass
class Event:
    event_id: str
    aggregate_id: str
    event_type: str
    payload: dict
    version: int
    timestamp: float

class EventSourcedAggregate:
    """Event-sourced entity with exactly-once state changes."""

    def __init__(self, aggregate_id: str):
        self.id = aggregate_id
        self.version = 0
        self.state = {}
        self._pending_events = []

    def apply_event(self, event: Event):
        """Apply an event to update state (must be idempotent)."""
        if event.event_type == "OrderCreated":
            self.state = {
                "status": "created",
                "items": event.payload["items"],
                "total": event.payload["total"],
            }
        elif event.event_type == "OrderPaid":
            self.state["status"] = "paid"
            self.state["payment_id"] = event.payload["payment_id"]
        elif event.event_type == "OrderShipped":
            self.state["status"] = "shipped"
            self.state["tracking"] = event.payload["tracking_number"]

        self.version = event.version

    async def save_events(self, db):
        """Save pending events with optimistic locking."""
        for event in self._pending_events:
            try:
                await db.execute(
                    """
                    INSERT INTO events (event_id, aggregate_id, event_type,
                                       payload, version, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    event.event_id,
                    event.aggregate_id,
                    event.event_type,
                    json.dumps(event.payload),
                    event.version,
                    event.timestamp,
                )
            except Exception as e:
                if "unique_violation" in str(e):
                    # Duplicate event -- already saved (idempotent)
                    logger.info("Event %s already saved", event.event_id)
                else:
                    raise
        self._pending_events.clear()

    @classmethod
    async def load(cls, db, aggregate_id: str) -> "EventSourcedAggregate":
        """Rebuild state by replaying events."""
        agg = cls(aggregate_id)
        events = await db.fetch(
            """
            SELECT * FROM events
            WHERE aggregate_id = $1
            ORDER BY version
            """,
            aggregate_id,
        )
        for row in events:
            event = Event(
                event_id=row["event_id"],
                aggregate_id=row["aggregate_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
                version=row["version"],
                timestamp=row["timestamp"],
            )
            agg.apply_event(event)
        return agg

# ============================================================
# SUMMARY: Achieving effectively exactly-once
# ============================================================

# 1. Producer side:
#    - Use Transactional Outbox to atomically save data + message
#    - Include a unique message ID with every message
#
# 2. Consumer side:
#    - Store processed message IDs in a dedup table
#    - Process + dedup-record in a single transaction
#    - Make all handlers idempotent
#
# 3. State management:
#    - Use Event Sourcing for fully auditable state changes
#    - Use optimistic locking (version checks) for updates
#
# 4. Infrastructure:
#    - Use Kafka with transactions for log-based exactly-once
#    - Use SQS FIFO with dedup IDs for message-level dedup
```

**The practical formula:**
- **Exactly-once = At-least-once delivery + Idempotent processing**
- Use the Transactional Outbox for reliable event publishing
- Use an idempotent consumer with a dedup table for reliable processing
- Accept that true exactly-once across distributed systems is impossible; design for idempotency instead''',
    ),
    (
        "thinking/error-handling",
        r'''How do I handle distributed transaction failures when there is no central coordinator? I have microservices that communicate through events and need to maintain data consistency.''',
        r'''<think>
Without a central coordinator, we use choreography-based sagas where each service:
1. Listens for events from other services
2. Performs its local transaction
3. Publishes success/failure events
4. Handles compensation events from other services

I considered whether orchestration would be simpler here, but the question specifically asks for no central coordinator. Choreography is more resilient to single points of failure since there is no coordinator to crash, but it is harder to reason about because the saga logic is spread across services.

Key challenges:
- Event ordering -- could be solved with sequence numbers, but wait, in a distributed system clocks are unreliable. Actually, causal ordering (each event references the event it responds to) is more practical than total ordering.
- Lost events -- need durable messaging with at-least-once delivery
- Duplicate events -- therefore every event handler must be idempotent
- Partial failures during compensation -- hmm, what if the compensation event itself is lost? The service that needs to compensate will never know. This is why choreography requires a dead letter queue and monitoring to detect stuck sagas.

Let me provide a practical implementation using an event-driven approach.
</think>

Choreography-based sagas use events to coordinate distributed transactions without a central coordinator. Each service reacts to events and publishes results:

```python
import asyncio
import json
import time
import uuid
import logging
from typing import Callable, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# ============================================================
# EVENT BUS (simplified - use Kafka/RabbitMQ in production)
# ============================================================

class EventBus:
    """Simple event bus for demonstration."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable):
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, payload: dict):
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "payload": payload,
            "timestamp": time.time(),
        }
        logger.info("Event published: %s", event_type)
        for handler in self._handlers.get(event_type, []):
            try:
                await handler(event)
            except Exception as e:
                logger.error("Handler failed for %s: %s", event_type, e)

bus = EventBus()

# ============================================================
# SERVICE 1: Order Service
# ============================================================

class OrderService:
    """Initiates the order saga by publishing OrderCreated."""

    def __init__(self, db, event_bus):
        self.db = db
        self.bus = event_bus
        # Listen for downstream events
        self.bus.subscribe("PaymentCompleted", self.on_payment_completed)
        self.bus.subscribe("PaymentFailed", self.on_payment_failed)
        self.bus.subscribe("InventoryReserved", self.on_inventory_reserved)
        self.bus.subscribe("InventoryFailed", self.on_inventory_failed)
        self.bus.subscribe("ShipmentCreated", self.on_shipment_created)

    async def create_order(self, order_data: dict) -> dict:
        """Start the order saga."""
        order_id = str(uuid.uuid4())
        await self.db.insert("orders", {
            "id": order_id,
            "status": "pending",
            "saga_state": "started",
            **order_data,
        })

        # Trigger the saga by publishing the first event
        await self.bus.publish("OrderCreated", {
            "order_id": order_id,
            "customer_id": order_data["customer_id"],
            "items": order_data["items"],
            "total": order_data["total"],
        })

        return {"order_id": order_id, "status": "pending"}

    async def on_payment_completed(self, event):
        order_id = event["payload"]["order_id"]
        await self.db.update("orders", order_id, {
            "saga_state": "payment_completed",
            "payment_id": event["payload"]["payment_id"],
        })
        logger.info("Order %s: payment completed", order_id)

    async def on_payment_failed(self, event):
        order_id = event["payload"]["order_id"]
        await self.db.update("orders", order_id, {
            "status": "failed",
            "saga_state": "payment_failed",
            "failure_reason": event["payload"]["reason"],
        })
        # Trigger compensation: release inventory
        await self.bus.publish("OrderCancelled", {
            "order_id": order_id,
            "reason": "payment_failed",
        })

    async def on_inventory_reserved(self, event):
        order_id = event["payload"]["order_id"]
        await self.db.update("orders", order_id, {
            "saga_state": "inventory_reserved",
        })

    async def on_inventory_failed(self, event):
        order_id = event["payload"]["order_id"]
        await self.db.update("orders", order_id, {
            "status": "failed",
            "saga_state": "inventory_failed",
        })
        # Trigger compensation: refund payment
        await self.bus.publish("OrderCancelled", {
            "order_id": order_id,
            "reason": "inventory_unavailable",
        })

    async def on_shipment_created(self, event):
        order_id = event["payload"]["order_id"]
        await self.db.update("orders", order_id, {
            "status": "confirmed",
            "saga_state": "completed",
            "tracking_number": event["payload"]["tracking"],
        })


# ============================================================
# SERVICE 2: Inventory Service
# ============================================================

class InventoryService:
    def __init__(self, db, event_bus):
        self.db = db
        self.bus = event_bus
        self.bus.subscribe("OrderCreated", self.on_order_created)
        self.bus.subscribe("OrderCancelled", self.on_order_cancelled)

    async def on_order_created(self, event):
        """Reserve inventory when an order is created."""
        order_id = event["payload"]["order_id"]
        items = event["payload"]["items"]

        try:
            # Idempotent: check if already reserved
            existing = await self.db.get("reservations", order_id)
            if existing:
                logger.info("Inventory already reserved for %s", order_id)
                return

            # Reserve each item
            for item in items:
                available = await self.db.get_stock(item["product_id"])
                if available < item["quantity"]:
                    raise ValueError(
                        f"Insufficient stock for {item['product_id']}"
                    )
                await self.db.decrement_stock(
                    item["product_id"], item["quantity"]
                )

            await self.db.insert("reservations", {
                "order_id": order_id,
                "items": items,
                "status": "reserved",
            })

            await self.bus.publish("InventoryReserved", {
                "order_id": order_id,
            })

        except Exception as e:
            await self.bus.publish("InventoryFailed", {
                "order_id": order_id,
                "reason": str(e),
            })

    async def on_order_cancelled(self, event):
        """Release inventory when order is cancelled (compensation)."""
        order_id = event["payload"]["order_id"]
        reservation = await self.db.get("reservations", order_id)
        if reservation and reservation["status"] == "reserved":
            for item in reservation["items"]:
                await self.db.increment_stock(
                    item["product_id"], item["quantity"]
                )
            await self.db.update("reservations", order_id, {
                "status": "released",
            })
            logger.info("Inventory released for order %s", order_id)


# ============================================================
# SERVICE 3: Payment Service
# ============================================================

class PaymentService:
    def __init__(self, db, event_bus):
        self.db = db
        self.bus = event_bus
        self.bus.subscribe("InventoryReserved", self.on_inventory_reserved)
        self.bus.subscribe("OrderCancelled", self.on_order_cancelled)

    async def on_inventory_reserved(self, event):
        """Charge payment after inventory is reserved."""
        order_id = event["payload"]["order_id"]

        try:
            # Idempotent check
            existing = await self.db.get("payments", order_id)
            if existing:
                return

            payment_id = str(uuid.uuid4())
            # In production: call payment gateway with idempotency key
            await self.db.insert("payments", {
                "id": payment_id,
                "order_id": order_id,
                "status": "charged",
            })

            await self.bus.publish("PaymentCompleted", {
                "order_id": order_id,
                "payment_id": payment_id,
            })

        except Exception as e:
            await self.bus.publish("PaymentFailed", {
                "order_id": order_id,
                "reason": str(e),
            })

    async def on_order_cancelled(self, event):
        """Refund payment when order is cancelled (compensation)."""
        order_id = event["payload"]["order_id"]
        payment = await self.db.get("payments", order_id)
        if payment and payment["status"] == "charged":
            await self.db.update("payments", order_id, {
                "status": "refunded",
            })
            logger.info("Payment refunded for order %s", order_id)
```

**Choreography saga rules:**
1. Every handler must be **idempotent** (check before processing)
2. Every successful step publishes a success event
3. Every failure publishes a failure event
4. Compensation handlers react to cancellation events
5. Track saga state in each service for debugging
6. Use a dead letter queue for events that repeatedly fail''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement the transactional outbox pattern to reliably publish events from my service without losing messages when the message broker is down or the process crashes?''',
        r'''<think>
The transactional outbox pattern solves the dual-write problem:
1. You need to update a database AND publish an event
2. If you do them separately, one can fail while the other succeeds
3. Solution: write the event to an "outbox" table in the SAME database transaction
4. A separate process reads the outbox and publishes to the message broker
5. This guarantees at-least-once delivery

My first thought was "why not just publish the event first, then update the database?" But wait -- if the database write fails after the event is published, consumers act on an event that never actually happened. That is worse than the reverse (database updated, event not published), because at least a missing event can be detected and replayed. Therefore writing to the outbox within the same transaction is the correct approach.

I considered using CDC (change data capture, e.g., Debezium reading the database WAL) instead of polling the outbox table. CDC avoids the polling overhead and catches changes immediately, but it adds operational complexity (another infrastructure component). For most systems, polling every few seconds is simpler and good enough. Actually, the choice depends on latency requirements -- if you need sub-second event propagation, CDC is worth the complexity; otherwise polling is fine.

Key implementation concerns:
- Outbox table schema
- Polling vs CDC for reading the outbox
- Ordering guarantees -- hmm, polling with multiple publisher instances could deliver events out of order. Therefore either use a single publisher or partition events by aggregate ID.
- Cleanup of processed outbox entries
- Handling publisher failures (retry, idempotency)
</think>

The transactional outbox pattern guarantees reliable event publishing by writing events to a database table within the same transaction as your data change. A separate publisher process forwards them to the message broker. Here is a complete implementation:

```python
import json
import time
import uuid
import threading
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from datetime import datetime, timedelta

logger = logging.getLogger("outbox")


# ============================================================
# OUTBOX TABLE SCHEMA (SQL)
# ============================================================

OUTBOX_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type  VARCHAR(255) NOT NULL,   -- e.g., 'Order', 'Payment'
    aggregate_id    VARCHAR(255) NOT NULL,   -- e.g., 'order-123'
    event_type      VARCHAR(255) NOT NULL,   -- e.g., 'OrderCreated'
    payload         JSONB NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMP NULL,          -- NULL = not yet published
    retry_count     INT NOT NULL DEFAULT 0,
    last_error      TEXT NULL
);

CREATE INDEX idx_outbox_unpublished
    ON outbox (created_at)
    WHERE published_at IS NULL;
"""


# ============================================================
# OUTBOX WRITER (USED IN YOUR SERVICE CODE)
# ============================================================

@dataclass
class OutboxEntry:
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


class OutboxWriter:
    """Writes events to the outbox table within an existing transaction.

    Usage:
        with db.transaction() as tx:
            tx.execute("INSERT INTO orders ...", order_data)
            outbox.write(tx, OutboxEntry(
                aggregate_type="Order",
                aggregate_id=order_id,
                event_type="OrderCreated",
                payload={"order_id": order_id, "amount": 99.99},
            ))
        # Both the order INSERT and the outbox INSERT commit
        # atomically. If either fails, both roll back.
    """

    def write(self, transaction, entry: OutboxEntry):
        """Write an outbox entry within the given transaction."""
        transaction.execute(
            """
            INSERT INTO outbox (id, aggregate_type, aggregate_id,
                                event_type, payload, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (entry.id, entry.aggregate_type, entry.aggregate_id,
             entry.event_type, json.dumps(entry.payload)),
        )


# ============================================================
# OUTBOX PUBLISHER (SEPARATE PROCESS/THREAD)
# ============================================================

class OutboxPublisher:
    """Polls the outbox table and publishes events to the message broker.

    Runs as a background thread or separate process.
    Guarantees at-least-once delivery.
    """

    def __init__(self, db_pool, message_broker,
                 poll_interval: float = 1.0,
                 batch_size: int = 100,
                 max_retries: int = 5):
        self._db = db_pool
        self._broker = message_broker
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Outbox publisher started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10.0)
        logger.info("Outbox publisher stopped")

    def _run(self):
        while self._running:
            try:
                published = self._poll_and_publish()
                if published == 0:
                    time.sleep(self._poll_interval)
            except Exception as exc:
                logger.error(f"Outbox publisher error: {exc}")
                time.sleep(self._poll_interval * 5)

    def _poll_and_publish(self) -> int:
        """Fetch unpublished entries and publish them."""
        conn = self._db.getconn()
        try:
            cursor = conn.cursor()

            # Lock rows to prevent duplicate publishing
            # by concurrent publisher instances
            cursor.execute(
                """
                SELECT id, aggregate_type, aggregate_id,
                       event_type, payload
                FROM outbox
                WHERE published_at IS NULL
                  AND retry_count < %s
                ORDER BY created_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (self._max_retries, self._batch_size),
            )
            rows = cursor.fetchall()

            if not rows:
                conn.commit()
                return 0

            published_ids = []
            failed_ids = []

            for row in rows:
                entry_id, agg_type, agg_id, event_type, payload = row
                topic = f"{agg_type}.{event_type}"

                try:
                    self._broker.publish(
                        topic=topic,
                        key=agg_id,
                        value=json.dumps({
                            "event_id": entry_id,
                            "event_type": event_type,
                            "aggregate_type": agg_type,
                            "aggregate_id": agg_id,
                            "payload": payload if isinstance(payload, dict)
                                       else json.loads(payload),
                            "published_at": time.time(),
                        }),
                    )
                    published_ids.append(entry_id)
                except Exception as exc:
                    logger.warning(
                        f"Failed to publish outbox entry {entry_id}: {exc}"
                    )
                    failed_ids.append((entry_id, str(exc)))

            # Mark published entries
            if published_ids:
                cursor.execute(
                    """
                    UPDATE outbox
                    SET published_at = NOW()
                    WHERE id = ANY(%s)
                    """,
                    (published_ids,),
                )

            # Increment retry count for failed entries
            for entry_id, error in failed_ids:
                cursor.execute(
                    """
                    UPDATE outbox
                    SET retry_count = retry_count + 1,
                        last_error = %s
                    WHERE id = %s
                    """,
                    (error, entry_id),
                )

            conn.commit()
            logger.info(
                f"Published {len(published_ids)} events, "
                f"{len(failed_ids)} failed"
            )
            return len(published_ids)

        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.putconn(conn)


# ============================================================
# OUTBOX CLEANUP (CRON JOB)
# ============================================================

class OutboxCleaner:
    """Periodically removes old published entries."""

    def __init__(self, db_pool, retention_hours: int = 72):
        self._db = db_pool
        self._retention_hours = retention_hours

    def clean(self) -> int:
        conn = self._db.getconn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM outbox
                WHERE published_at IS NOT NULL
                  AND published_at < NOW() - INTERVAL '%s hours'
                """,
                (self._retention_hours,),
            )
            deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Cleaned {deleted} old outbox entries")
            return deleted
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.putconn(conn)

    def find_stuck(self) -> list[dict]:
        """Find entries that exceeded max retries (need manual attention)."""
        conn = self._db.getconn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, aggregate_type, aggregate_id,
                       event_type, retry_count, last_error, created_at
                FROM outbox
                WHERE published_at IS NULL
                  AND retry_count >= 5
                ORDER BY created_at
                """,
            )
            return [
                {
                    "id": row[0],
                    "aggregate": f"{row[1]}:{row[2]}",
                    "event_type": row[3],
                    "retries": row[4],
                    "last_error": row[5],
                    "created_at": str(row[6]),
                }
                for row in cursor.fetchall()
            ]
        finally:
            self._db.putconn(conn)


# ============================================================
# USAGE IN SERVICE CODE
# ============================================================

# outbox = OutboxWriter()
#
# def create_order(order_data: dict) -> dict:
#     order_id = str(uuid.uuid4())
#
#     with db.transaction() as tx:
#         # Data write and event write in the SAME transaction
#         tx.execute(
#             "INSERT INTO orders (id, customer_id, amount, status) "
#             "VALUES (%s, %s, %s, %s)",
#             (order_id, order_data["customer_id"],
#              order_data["amount"], "created"),
#         )
#
#         outbox.write(tx, OutboxEntry(
#             aggregate_type="Order",
#             aggregate_id=order_id,
#             event_type="OrderCreated",
#             payload={
#                 "order_id": order_id,
#                 "customer_id": order_data["customer_id"],
#                 "amount": order_data["amount"],
#             },
#         ))
#         # BOTH commit together or BOTH roll back
#
#     return {"order_id": order_id}
```

**Why the outbox pattern works:**

1. **Atomic writes**: the event and the data change are in the same DB transaction -- impossible to have one without the other
2. **At-least-once delivery**: the publisher retries until the broker acknowledges -- events may be delivered more than once, so consumers must be idempotent
3. **Survives crashes**: if the publisher crashes, unpublished entries remain in the outbox and are picked up on restart
4. **Survives broker downtime**: events queue up in the outbox table until the broker comes back
5. **FOR UPDATE SKIP LOCKED**: multiple publisher instances can run concurrently without duplicating work
6. **Cleanup**: old published entries are periodically deleted to prevent unbounded table growth''',
    ),
]
