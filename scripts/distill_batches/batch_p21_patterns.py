PAIRS = [
    (
        "architecture/saga-pattern",
        r"""Explain the Saga pattern for distributed transactions including choreography vs orchestration, compensating transactions, failure handling, idempotency requirements, and implementing sagas with an event-driven approach. Include Python examples.""",
        r"""## Saga Pattern: Managing Distributed Transactions Without 2PC

In microservice architectures, a single business operation often spans multiple services. Traditional ACID transactions don't work across service boundaries. Sagas break a transaction into a sequence of local transactions, each with a compensating action for rollback.

### Choreography: Event-Driven Sagas

Each service listens for events and decides what to do next:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone


class SagaStatus(Enum):
    STARTED = "started"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    FAILED = "failed"


@dataclass
class SagaEvent:
    saga_id: UUID
    event_type: str
    service: str
    data: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Order Creation Saga (Choreography):
# 1. OrderService: Create order (PENDING)
# 2. PaymentService: Reserve payment → OrderPaymentReserved
# 3. InventoryService: Reserve stock → OrderStockReserved
# 4. OrderService: Confirm order → OrderConfirmed
#
# Compensation on failure:
# If InventoryService fails: PaymentService releases payment
# If PaymentService fails: OrderService cancels order


class OrderSagaParticipant:
    """Each service is a saga participant that handles events."""

    async def handle_order_created(self, event: SagaEvent):
        """PaymentService handles OrderCreated."""
        try:
            await self.reserve_payment(
                order_id=event.data["order_id"],
                amount=event.data["total"],
                customer_id=event.data["customer_id"],
            )
            await self.publish(SagaEvent(
                saga_id=event.saga_id,
                event_type="PaymentReserved",
                service="payment",
                data={"order_id": event.data["order_id"], "payment_id": "pay-123"},
            ))
        except InsufficientFundsError:
            await self.publish(SagaEvent(
                saga_id=event.saga_id,
                event_type="PaymentFailed",
                service="payment",
                data={"order_id": event.data["order_id"], "reason": "insufficient_funds"},
            ))

    async def handle_payment_failed(self, event: SagaEvent):
        """OrderService handles PaymentFailed — compensate."""
        await self.cancel_order(event.data["order_id"])
        await self.publish(SagaEvent(
            saga_id=event.saga_id,
            event_type="OrderCancelled",
            service="order",
            data=event.data,
        ))
```

### Orchestration: Central Coordinator

A saga orchestrator manages the sequence and compensation:

```python
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class SagaStep:
    name: str
    action: Callable  # The forward action
    compensation: Callable  # The rollback action
    completed: bool = False


class SagaOrchestrator:
    """Central saga coordinator that manages step execution."""

    def __init__(self, saga_id: UUID = None):
        self.saga_id = saga_id or uuid4()
        self.steps: list[SagaStep] = []
        self.completed_steps: list[SagaStep] = []
        self.status = SagaStatus.STARTED

    def add_step(self, name: str, action: Callable, compensation: Callable):
        self.steps.append(SagaStep(name, action, compensation))

    async def execute(self, context: dict) -> dict:
        """Execute saga steps in order, compensate on failure."""
        for step in self.steps:
            try:
                print(f"Executing step: {step.name}")
                result = await step.action(context)
                context.update(result or {})
                step.completed = True
                self.completed_steps.append(step)
            except Exception as e:
                print(f"Step {step.name} failed: {e}")
                self.status = SagaStatus.COMPENSATING
                await self._compensate(context)
                self.status = SagaStatus.FAILED
                raise SagaFailedError(
                    f"Saga {self.saga_id} failed at {step.name}: {e}",
                    compensated_steps=[s.name for s in self.completed_steps],
                )

        self.status = SagaStatus.COMPLETED
        return context

    async def _compensate(self, context: dict):
        """Run compensating transactions in reverse order."""
        for step in reversed(self.completed_steps):
            try:
                print(f"Compensating step: {step.name}")
                await step.compensation(context)
            except Exception as e:
                # Compensation failure is serious — log and alert
                print(f"CRITICAL: Compensation failed for {step.name}: {e}")
                # In production: send to dead letter queue for manual resolution


# Usage: Order Creation Saga
async def create_order_saga(order_data: dict):
    saga = SagaOrchestrator()

    saga.add_step(
        name="create_order",
        action=lambda ctx: create_order(ctx),
        compensation=lambda ctx: cancel_order(ctx["order_id"]),
    )

    saga.add_step(
        name="reserve_payment",
        action=lambda ctx: reserve_payment(ctx["order_id"], ctx["total"]),
        compensation=lambda ctx: release_payment(ctx["payment_id"]),
    )

    saga.add_step(
        name="reserve_inventory",
        action=lambda ctx: reserve_inventory(ctx["order_id"], ctx["items"]),
        compensation=lambda ctx: release_inventory(ctx["reservation_id"]),
    )

    saga.add_step(
        name="confirm_order",
        action=lambda ctx: confirm_order(ctx["order_id"]),
        compensation=lambda ctx: None,  # No compensation needed (already confirmed)
    )

    return await saga.execute(order_data)
```

### Idempotent Operations

Every saga step must be idempotent — safe to retry:

```python
class IdempotentSagaStep:
    """Wrapper ensuring saga steps are idempotent."""

    def __init__(self, store):
        self.store = store  # Redis or database

    async def execute_once(
        self,
        saga_id: UUID,
        step_name: str,
        action: Callable,
        context: dict,
    ) -> dict:
        """Execute action only if not already completed."""
        key = f"saga:{saga_id}:step:{step_name}"

        # Check if already executed
        existing = await self.store.get(key)
        if existing:
            return existing  # Return cached result

        # Execute and record
        result = await action(context)
        await self.store.set(key, result, ttl=86400)  # 24h retention
        return result
```

**Saga pattern guidelines**: (1) **Choreography** for simple sagas with few steps — each service is autonomous, (2) **Orchestration** for complex sagas with many steps — centralized control, easier to understand, (3) Every step MUST have a compensating transaction, (4) Every step MUST be idempotent — network retries will happen, (5) Compensation failures need manual resolution — have monitoring and dead-letter queues, (6) Prefer orchestration in practice — choreography becomes hard to trace as sagas grow."""
    ),
    (
        "architecture/outbox-pattern",
        r"""Explain the Transactional Outbox pattern for reliable event publishing including the problem it solves (dual writes), implementation with polling and CDC, Debezium integration, and guaranteeing at-least-once delivery.""",
        r"""## Transactional Outbox: Reliable Event Publishing Without Dual Writes

The outbox pattern solves a fundamental problem in event-driven architectures: how to atomically update a database AND publish an event, when the database and message broker are separate systems.

### The Dual Write Problem

```python
# THE PROBLEM: This code has a race condition
async def create_order(order_data: dict):
    # Step 1: Save to database
    order = await db.save(order_data)

    # Step 2: Publish event
    await message_broker.publish("order.created", order)

    # What if the app crashes between Step 1 and Step 2?
    # → Order exists in DB but event never published
    # → Downstream services never know about the order

    # What if we reverse the order?
    # → Event published but DB save fails
    # → Downstream services process a phantom order

    # What if we use a transaction?
    # → Database transaction can't span the message broker
    # → They're different systems!
```

### The Outbox Pattern Solution

```python
import json
from uuid import uuid4
from datetime import datetime, timezone


class OutboxRepository:
    """Write events to an outbox table within the same DB transaction."""

    def __init__(self, db):
        self.db = db

    async def create_order_with_event(self, order_data: dict) -> dict:
        """Atomically create order AND outbox event in ONE transaction."""
        async with self.db.transaction():
            # Step 1: Save the order
            order = await self.db.execute(
                """INSERT INTO orders (id, customer_id, total, status)
                VALUES ($1, $2, $3, 'created')
                RETURNING *""",
                uuid4(), order_data["customer_id"], order_data["total"],
            )

            # Step 2: Write event to outbox table (SAME transaction!)
            await self.db.execute(
                """INSERT INTO outbox
                (id, aggregate_type, aggregate_id, event_type, payload, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)""",
                uuid4(),
                "Order",
                order["id"],
                "order.created",
                json.dumps({
                    "order_id": str(order["id"]),
                    "customer_id": order_data["customer_id"],
                    "total": float(order_data["total"]),
                }),
                datetime.now(timezone.utc),
            )

            return order
        # Both writes succeed or both fail — ACID guarantees!


# Outbox table schema:
# CREATE TABLE outbox (
#     id UUID PRIMARY KEY,
#     aggregate_type TEXT NOT NULL,
#     aggregate_id UUID NOT NULL,
#     event_type TEXT NOT NULL,
#     payload JSONB NOT NULL,
#     created_at TIMESTAMPTZ NOT NULL,
#     published_at TIMESTAMPTZ NULL,
#     retries INT DEFAULT 0
# );
# CREATE INDEX idx_outbox_unpublished ON outbox (created_at)
#     WHERE published_at IS NULL;
```

### Outbox Relay: Polling Publisher

```python
import asyncio
import json


class OutboxRelay:
    """Polls the outbox table and publishes events to message broker."""

    def __init__(self, db, message_broker, poll_interval: float = 1.0):
        self.db = db
        self.broker = message_broker
        self.poll_interval = poll_interval

    async def start(self):
        """Run the relay loop."""
        while True:
            published = await self._publish_pending()
            if published == 0:
                await asyncio.sleep(self.poll_interval)

    async def _publish_pending(self) -> int:
        """Publish pending outbox events."""
        # Fetch unpublished events (with lock to prevent duplicates)
        events = await self.db.fetch(
            """SELECT * FROM outbox
            WHERE published_at IS NULL
            ORDER BY created_at
            LIMIT 100
            FOR UPDATE SKIP LOCKED""",
        )

        published = 0
        for event in events:
            try:
                # Publish to message broker
                await self.broker.publish(
                    topic=event["event_type"],
                    key=str(event["aggregate_id"]),
                    value=event["payload"],
                    headers={
                        "event_id": str(event["id"]),
                        "aggregate_type": event["aggregate_type"],
                    },
                )

                # Mark as published
                await self.db.execute(
                    "UPDATE outbox SET published_at = NOW() WHERE id = $1",
                    event["id"],
                )
                published += 1

            except Exception as e:
                # Increment retry count, will be retried next poll
                await self.db.execute(
                    """UPDATE outbox SET retries = retries + 1
                    WHERE id = $1""",
                    event["id"],
                )
                print(f"Failed to publish event {event['id']}: {e}")

        return published

    async def cleanup(self, max_age_days: int = 7):
        """Remove old published events."""
        await self.db.execute(
            """DELETE FROM outbox
            WHERE published_at IS NOT NULL
            AND published_at < NOW() - INTERVAL '%s days'""",
            max_age_days,
        )
```

### CDC-Based Outbox (Debezium)

Change Data Capture reads the database's transaction log directly — no polling needed:

```json
// Debezium connector configuration
{
    "name": "outbox-connector",
    "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "database.hostname": "postgres",
        "database.port": "5432",
        "database.user": "debezium",
        "database.password": "secret",
        "database.dbname": "myapp",
        "table.include.list": "public.outbox",
        "transforms": "outbox",
        "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter",
        "transforms.outbox.table.field.event.id": "id",
        "transforms.outbox.table.field.event.key": "aggregate_id",
        "transforms.outbox.table.field.event.type": "event_type",
        "transforms.outbox.table.field.event.payload": "payload",
        "transforms.outbox.route.topic.replacement": "${routedByValue}",
        "transforms.outbox.table.expand.json.payload": "true"
    }
}
```

```
CDC approach:

Database WAL (Write-Ahead Log)
    │
    └──→ Debezium reads WAL changes
            │
            └──→ Publishes to Kafka topics

Advantages over polling:
1. Real-time: no polling delay
2. No database load: reads WAL, not the table
3. Guaranteed ordering: WAL is strictly ordered
4. No missed events: WAL is the source of truth

Disadvantages:
1. More infrastructure (Debezium, Kafka Connect)
2. WAL access requires database configuration
3. More complex monitoring
```

### Guarantees

```
Outbox pattern guarantees:

1. AT-LEAST-ONCE delivery:
   - The outbox relay might publish an event, crash before marking
     it as published, and re-publish on restart
   - Consumers MUST be idempotent

2. ORDERING within an aggregate:
   - Events for the same aggregate_id are published in order
   - Events across different aggregates have no ordering guarantee

3. NO DATA LOSS:
   - Events are durably stored in the database
   - Even if the message broker is down, events accumulate
     in the outbox and are published when it recovers
```

**Outbox pattern rules**: (1) Always write to the outbox in the SAME transaction as the business data, (2) Consumers must be idempotent — at-least-once delivery means duplicates, (3) Use CDC (Debezium) for production if you need real-time and can manage the infrastructure, (4) Use polling for simpler setups — it's reliable and easy to debug, (5) Clean up published events periodically — the outbox table shouldn't grow unboundedly."""
    ),
    (
        "architecture/event-driven-architecture",
        r"""Explain event-driven architecture patterns including event notification, event-carried state transfer, event sourcing, CQRS integration, designing event schemas, event versioning, and choosing between sync and async communication.""",
        r"""## Event-Driven Architecture: Patterns, Schema Design, and Communication Trade-offs

Event-driven architecture (EDA) decouples services by having them communicate through events rather than direct API calls. The choice of event pattern dramatically affects system coupling, complexity, and data consistency.

### Three Event Patterns

```python
# 1. EVENT NOTIFICATION
# "Something happened" — minimal data, consumer fetches details if needed
# Low coupling, but causes "event chasing" (callback to source for data)

class OrderCreatedNotification:
    """Thin event: just the ID and type."""
    event_type = "order.created"
    order_id: str
    timestamp: str
    # Consumer must call OrderService API to get order details

# 2. EVENT-CARRIED STATE TRANSFER
# "Something happened, and here's all the data you need"
# Higher coupling (shared schema), but no callbacks needed

class OrderCreatedFull:
    """Fat event: includes all relevant data."""
    event_type = "order.created"
    order_id: str
    customer_id: str
    customer_email: str  # Denormalized for consumers
    items: list[dict]
    total: float
    shipping_address: dict
    timestamp: str
    # Consumer has everything it needs — no API calls back

# 3. EVENT SOURCING
# "Here's the state change itself" — events ARE the data
# See CQRS/Event Sourcing section for details
```

### Event Schema Design

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from uuid import uuid4
import json


@dataclass
class EventEnvelope:
    """Standard event envelope — consistent across all events."""
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    event_version: int = 1
    source: str = ""  # Which service produced this
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    correlation_id: str = ""  # For tracing across services
    causation_id: str = ""  # What caused this event
    data: dict = field(default_factory=dict)  # Event payload
    metadata: dict = field(default_factory=dict)  # Non-business context

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, raw: str) -> "EventEnvelope":
        return cls(**json.loads(raw))


# Good event naming:
# Past tense: OrderCreated, PaymentProcessed, InventoryReserved
# Domain language: not "OrderTableRowInserted"
# Specific: OrderShipped, not OrderUpdated

# Good event design principles:
# 1. Events are IMMUTABLE — never change a published event
# 2. Events are FACTS — something that already happened
# 3. Include enough data for consumers to act without callbacks
# 4. Include correlation_id for distributed tracing
# 5. Version events from day 1
```

### Event Versioning

```python
class EventUpgrader:
    """Handle event schema evolution without breaking consumers."""

    def __init__(self):
        self._upgraders = {}

    def register(self, event_type: str, from_version: int, upgrader):
        self._upgraders[(event_type, from_version)] = upgrader

    def upgrade(self, event: EventEnvelope) -> EventEnvelope:
        """Upgrade event to latest version."""
        current = event.event_version
        while (event.event_type, current) in self._upgraders:
            upgrader = self._upgraders[(event.event_type, current)]
            event = upgrader(event)
            current += 1
            event.event_version = current
        return event


# Register upgraders
upgrader = EventUpgrader()

# v1 → v2: Added customer_email to OrderCreated
upgrader.register("order.created", 1, lambda e: EventEnvelope(
    **{**asdict(e), "event_version": 2, "data": {
        **e.data,
        "customer_email": e.data.get("customer_email", "unknown@example.com"),
    }}
))

# v2 → v3: Renamed "total" to "order_total"
upgrader.register("order.created", 2, lambda e: EventEnvelope(
    **{**asdict(e), "event_version": 3, "data": {
        **{k: v for k, v in e.data.items() if k != "total"},
        "order_total": e.data.get("total", e.data.get("order_total", 0)),
    }}
))


# Versioning strategies:
# 1. ADDITIVE CHANGES (backward compatible):
#    Adding new fields — old consumers ignore them
#    This is always safe and preferred
#
# 2. TRANSFORMATIVE CHANGES (breaking):
#    Renaming fields, changing types, removing fields
#    Use upgraders to transform old events to new schema
#
# 3. NEW EVENT TYPE (for major changes):
#    Instead of OrderCreated v5, create OrderCreatedV2
#    Run both in parallel during migration
```

### Sync vs Async Communication

```python
# SYNCHRONOUS (Request-Response):
# Service A calls Service B and WAITS for response
# Use when: you need the result immediately
# Examples: GET user profile, validate payment, check authorization

async def sync_pattern(user_id: str):
    # Blocks until response received
    user = await user_service.get_user(user_id)
    permissions = await auth_service.check_permissions(user_id)
    return {"user": user, "permissions": permissions}

# Pros: Simple, immediate consistency, easy to reason about
# Cons: Tight coupling, cascading failures, latency accumulates


# ASYNCHRONOUS (Event-Driven):
# Service A publishes event and continues; Service B processes later
# Use when: you don't need immediate result
# Examples: send email, update analytics, sync to search index

async def async_pattern(order_data: dict):
    # Save order and publish event
    order = await db.save(order_data)
    await event_bus.publish(EventEnvelope(
        event_type="order.created",
        data=asdict(order),
    ))
    # Return immediately — don't wait for email, analytics, etc.
    return order

# Pros: Loose coupling, fault tolerance, scalability
# Cons: Eventual consistency, harder to debug, no immediate feedback


# HYBRID: Most real systems use both
async def hybrid_pattern(order_data: dict):
    # Synchronous: validate payment (need immediate result)
    payment_valid = await payment_service.validate(order_data["payment_method"])
    if not payment_valid:
        raise PaymentError("Invalid payment method")

    # Synchronous: create the order (need order_id for response)
    order = await order_service.create(order_data)

    # Asynchronous: notify downstream services (don't need to wait)
    await event_bus.publish(EventEnvelope(
        event_type="order.created",
        data={"order_id": order.id, **order_data},
    ))

    # Return to user immediately
    return {"order_id": order.id, "status": "processing"}
```

**EDA principles**: (1) Use fat events (event-carried state transfer) as the default — thin events cause event chasing, (2) Design event schemas carefully from day 1 — they're your public API, (3) Version all events and support upgrading old versions, (4) Use synchronous calls for queries and validation, async events for notifications and side effects, (5) Always include correlation_id for distributed tracing — debugging async systems without tracing is nearly impossible."""
    ),
]
