"""Message queue patterns — pub/sub, dead letter queues, exactly-once."""

PAIRS = [
    (
        "architecture/message-patterns",
        "Show message queue patterns: pub/sub, work queues, request-reply, and dead letter queue handling.",
        '''Message queue patterns:

```python
import json
import time
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from enum import Enum


class DeliveryMode(Enum):
    AT_MOST_ONCE = "at_most_once"
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"


@dataclass
class Message:
    id: str
    topic: str
    payload: dict
    headers: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    attempt: int = 0
    max_retries: int = 3


@dataclass
class DeadLetterEntry:
    original_message: Message
    error: str
    failed_at: float
    consumer: str


class MessageBroker:
    """In-memory message broker with DLQ support."""

    def __init__(self):
        self.queues: dict[str, asyncio.Queue] = {}
        self.subscribers: dict[str, list[Callable]] = {}
        self.dlq: list[DeadLetterEntry] = []
        self.processed_ids: set = set()  # For deduplication

    def create_queue(self, name: str, max_size: int = 10000):
        self.queues[name] = asyncio.Queue(maxsize=max_size)

    async def publish(self, topic: str, payload: dict,
                       headers: dict = None) -> str:
        """Publish message to topic (fan-out to all subscribers)."""
        import uuid
        msg = Message(id=str(uuid.uuid4()), topic=topic,
                      payload=payload, headers=headers or {})

        # Fan-out to all subscriber queues
        for handler in self.subscribers.get(topic, []):
            await handler(msg)

        # Also put in named queue if exists
        if topic in self.queues:
            await self.queues[topic].put(msg)

        return msg.id

    def subscribe(self, topic: str, handler: Callable):
        """Subscribe to topic (pub/sub pattern)."""
        self.subscribers.setdefault(topic, []).append(handler)

    async def consume(self, queue_name: str, handler: Callable,
                       delivery: DeliveryMode = DeliveryMode.AT_LEAST_ONCE):
        """Consume from work queue with retry and DLQ."""
        queue = self.queues[queue_name]

        while True:
            msg = await queue.get()

            # Deduplication for exactly-once
            if delivery == DeliveryMode.EXACTLY_ONCE:
                if msg.id in self.processed_ids:
                    continue
                self.processed_ids.add(msg.id)

            try:
                await handler(msg)
            except Exception as e:
                msg.attempt += 1
                if msg.attempt < msg.max_retries:
                    # Retry with backoff
                    await asyncio.sleep(2 ** msg.attempt)
                    await queue.put(msg)
                else:
                    # Send to dead letter queue
                    self.dlq.append(DeadLetterEntry(
                        original_message=msg, error=str(e),
                        failed_at=time.time(), consumer=queue_name,
                    ))


class IdempotentConsumer:
    """Ensure message processing is idempotent."""

    def __init__(self, db):
        self.db = db

    async def process(self, message: Message, handler: Callable):
        """Process message exactly once using idempotency key."""
        async with self.db.transaction():
            # Check if already processed
            exists = await self.db.fetchval(
                "SELECT 1 FROM processed_messages WHERE message_id = $1",
                message.id,
            )
            if exists:
                return  # Already processed, skip

            # Process and record atomically
            result = await handler(message)
            await self.db.execute(
                "INSERT INTO processed_messages (message_id, processed_at) VALUES ($1, $2)",
                message.id, time.time(),
            )
            return result
```

Key patterns:
1. **Work queue** — competing consumers; each message processed by one worker
2. **Pub/sub** — fan-out; message delivered to all subscribers
3. **Dead letter queue** — failed messages after max retries; enables manual investigation
4. **Idempotent consumer** — track processed message IDs; safe to replay messages
5. **Delivery guarantees** — at-most-once (fire-and-forget), at-least-once (retry), exactly-once (dedup)'''
    ),
    (
        "architecture/event-driven-arch",
        "Show event-driven architecture: event bus, event handlers, eventual consistency, and compensating actions.",
        '''Event-driven architecture:

```python
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Type
from datetime import datetime


@dataclass
class DomainEvent:
    event_type: str
    aggregate_id: str
    data: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: str = ""


class EventBus:
    """Central event bus for decoupled communication."""

    def __init__(self):
        self.handlers: dict[str, list[Callable]] = {}
        self.middleware: list[Callable] = []
        self.failed_events: list[tuple] = []

    def register(self, event_type: str, handler: Callable):
        self.handlers.setdefault(event_type, []).append(handler)

    def add_middleware(self, middleware: Callable):
        self.middleware.append(middleware)

    async def publish(self, event: DomainEvent):
        """Publish event to all registered handlers."""
        # Run middleware (logging, metrics, etc.)
        for mw in self.middleware:
            event = await mw(event)

        handlers = self.handlers.get(event.event_type, [])
        # Run handlers concurrently
        results = await asyncio.gather(
            *[self._safe_handle(h, event) for h in handlers],
            return_exceptions=True,
        )

        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                self.failed_events.append((event, handler, result))

    async def _safe_handle(self, handler: Callable, event: DomainEvent):
        try:
            return await handler(event)
        except Exception as e:
            return e


# Example: Order events drive multiple side effects
class OrderEventHandlers:
    def __init__(self, bus: EventBus):
        bus.register("OrderCreated", self.send_confirmation)
        bus.register("OrderCreated", self.reserve_inventory)
        bus.register("OrderCreated", self.notify_warehouse)
        bus.register("OrderCancelled", self.release_inventory)
        bus.register("OrderCancelled", self.refund_payment)

    async def send_confirmation(self, event: DomainEvent):
        email = event.data["customer_email"]
        # Send email...

    async def reserve_inventory(self, event: DomainEvent):
        for item in event.data["items"]:
            await inventory_service.reserve(item["product_id"], item["quantity"])

    async def notify_warehouse(self, event: DomainEvent):
        await warehouse_service.prepare(event.aggregate_id)

    async def release_inventory(self, event: DomainEvent):
        for item in event.data["items"]:
            await inventory_service.release(item["product_id"], item["quantity"])

    async def refund_payment(self, event: DomainEvent):
        await payment_service.refund(event.data["payment_id"])
```

Key patterns:
1. **Loose coupling** — publishers don't know about subscribers; add handlers without changing publisher
2. **Concurrent handlers** — multiple side effects run in parallel via asyncio.gather
3. **Error isolation** — one handler failure doesn't block others; failed events tracked
4. **Compensating events** — OrderCancelled triggers release_inventory and refund_payment
5. **Middleware** — cross-cutting concerns (logging, metrics) applied to all events'''
    ),
]
