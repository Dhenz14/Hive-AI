"""p21 patterns"""

PAIRS = [
    (
        "architecture/saga-pattern",
        "Explain the Saga pattern for distributed transactions including choreography vs orchestration, compensating transactions, failure handling, idempotency requirements, and implementing sagas with an event-driven approach. Include Python examples.",
        '''In microservice architectures, a single business operation often spans multiple services. Traditional ACID transactions don't work across service boundaries. Sagas break a transaction into a sequence of local transactions, each with a compensating action for rollback.

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
# 2. PaymentService: Reserve payment -> OrderPaymentReserved
# 3. InventoryService: Reserve stock -> OrderStockReserved
# 4. OrderService: Confirm order -> OrderConfirmed
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
                customer_id=event.data["customer_id"],'''
    ),
    (
        "architecture/outbox-pattern",
        "Explain the Transactional Outbox pattern for reliable event publishing including the problem it solves (dual writes), implementation with polling and CDC, Debezium integration, and guaranteeing at-least-once delivery.",
        '''The outbox pattern solves a fundamental problem in event-driven architectures: how to atomically update a database AND publish an event, when the database and message broker are separate systems.

### The Dual Write Problem

```python
# THE PROBLEM: This code has a race condition
async def create_order(order_data: dict):
    # Step 1: Save to database
    order = await db.save(order_data)

    # Step 2: Publish event
    await message_broker.publish("order.created", order)

    # What if the app crashes between Step 1 and Step 2?
    # -> Order exists in DB but event never published
    # -> Downstream services never know about the order

    # What if we reverse the order?
    # -> Event published but DB save fails
    # -> Downstream services process a phantom order

    # What if we use a transaction?
    # -> Database transaction can't span the message broker
    # -> They're different systems!
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
                uuid4(), order_data["customer_id"], order_data["total"],'''
    ),
    (
        "total",
        "}) datetime.now(timezone.utc) ) return order",
        '''# Outbox table schema:
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
            FOR UPDATE SKIP LOCKED""",'''
    ),
    (
        "aggregate_type",
        "} )",
        '''await self.db.execute(
                    "UPDATE outbox SET published_at = NOW() WHERE id = $1",
                    event["id"],'''
    ),
    (
        "transforms",
        "transforms.outbox.type': 'io.debezium.transforms.outbox.EventRouter' transforms.outbox.table.field.event.id': 'id' transforms.outbox.table.field.event.key': 'aggregate_id' transforms.outbox.table.field.event.type': 'event_type' transforms.outbox.table.field.event.payload': 'payload' transforms.outbox.route.topic.replacement': '${routedByValue}' transforms.outbox.table.expand.json.payload': 'true } }",
        '''```
CDC approach:

Database WAL (Write-Ahead Log)
    │
    └──-> Debezium reads WAL changes
            │
            └──-> Publishes to Kafka topics

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

**Outbox pattern rules**: (1) Always write to the outbox in the SAME transaction as the business data, (2) Consumers must be idempotent -- at-least-once delivery means duplicates, (3) Use CDC (Debezium) for production if you need real-time and can manage the infrastructure, (4) Use polling for simpler setups -- it's reliable and easy to debug, (5) Clean up published events periodically -- the outbox table shouldn't grow unboundedly.'''
    ),
    (
        "architecture/event-driven-architecture",
        "Explain event-driven architecture patterns including event notification, event-carried state transfer, event sourcing, CQRS integration, designing event schemas, event versioning, and choosing between sync and async communication.",
        '''Event-driven architecture (EDA) decouples services by having them communicate through events rather than direct API calls. The choice of event pattern dramatically affects system coupling, complexity, and data consistency.

### Three Event Patterns

```python
# 1. EVENT NOTIFICATION
# "Something happened" -- minimal data, consumer fetches details if needed
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
    # Consumer has everything it needs -- no API calls back

# 3. EVENT SOURCING
# "Here's the state change itself" -- events ARE the data
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
    """Standard event envelope -- consistent across all events."""
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    event_version: int = 1
    source: str = ""  # Which service produced this
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()'''
    ),
    (
        "customer_email",
        "}} ))",
        '''upgrader.register("order.created", 2, lambda e: EventEnvelope(
    **{**asdict(e), "event_version": 3, "data": {
        **{k: v for k, v in e.data.items() if k != "total"},'''
    ),
    (
        "order_total",
        "}} ))",
        '''# 1. ADDITIVE CHANGES (backward compatible):
#    Adding new fields -- old consumers ignore them
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
    # Return immediately -- don't wait for email, analytics, etc.
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

**EDA principles**: (1) Use fat events (event-carried state transfer) as the default -- thin events cause event chasing, (2) Design event schemas carefully from day 1 -- they're your public API, (3) Version all events and support upgrading old versions, (4) Use synchronous calls for queries and validation, async events for notifications and side effects, (5) Always include correlation_id for distributed tracing -- debugging async systems without tracing is nearly impossible.'''
    ),
]
