"""Data engineering — stream processing with Kafka, Flink, and event sourcing."""

PAIRS = [
    (
        "data-engineering/kafka-patterns",
        "Show Kafka patterns: producers, consumers, consumer groups, exactly-once semantics, and schema registry.",
        '''Kafka producer and consumer patterns:

```python
from confluent_kafka import (
    Producer, Consumer, KafkaError, KafkaException,
    TopicPartition,
)
from confluent_kafka.serialization import (
    SerializationContext, MessageField,
)
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
import json
import logging
import signal
import sys

logger = logging.getLogger(__name__)


# --- Producer with delivery callbacks ---

class OrderProducer:
    def __init__(self, bootstrap_servers: str):
        self.producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",             # Wait for all replicas
            "enable.idempotence": True, # Exactly-once per partition
            "max.in.flight.requests.per.connection": 5,
            "retries": 2147483647,     # Infinite retries
            "linger.ms": 10,           # Batch messages for throughput
            "batch.size": 32768,       # 32KB batches
            "compression.type": "lz4", # Compress for network savings
        })

    def _delivery_callback(self, err, msg):
        if err:
            logger.error("Delivery failed for %s: %s", msg.key(), err)
        else:
            logger.debug("Delivered to %s [%d] @ %d",
                        msg.topic(), msg.partition(), msg.offset())

    def send_order(self, order: dict):
        """Send order event with key-based partitioning."""
        key = order["customer_id"]  # Same customer -> same partition -> ordering
        value = json.dumps(order).encode("utf-8")

        self.producer.produce(
            topic="orders",
            key=key.encode("utf-8"),
            value=value,
            on_delivery=self._delivery_callback,
            headers={"event_type": "order.created"},
        )
        self.producer.poll(0)  # Trigger callbacks

    def flush(self):
        """Wait for all messages to be delivered."""
        remaining = self.producer.flush(timeout=30)
        if remaining > 0:
            logger.warning("%d messages still in queue", remaining)


# --- Consumer with graceful shutdown ---

class OrderConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str):
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,  # Manual commit for at-least-once
            "max.poll.interval.ms": 300000,
            "session.timeout.ms": 45000,
            "fetch.min.bytes": 1024,
            "fetch.wait.max.ms": 500,
        })
        self._running = True

    def start(self, topics: list[str], handler):
        """Consume messages with manual commit."""
        self.consumer.subscribe(topics)

        # Graceful shutdown
        signal.signal(signal.SIGTERM, lambda *_: self.stop())

        try:
            while self._running:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(msg.error())

                try:
                    value = json.loads(msg.value().decode("utf-8"))
                    handler(value, msg.headers())

                    # Commit after successful processing
                    self.consumer.commit(asynchronous=False)

                except Exception as e:
                    logger.error("Failed to process message at offset %d: %s",
                               msg.offset(), e)
                    # Dead letter queue or retry logic here

        finally:
            self.consumer.close()

    def stop(self):
        self._running = False


# --- Batch consumer (high throughput) ---

class BatchConsumer:
    """Process messages in batches for better throughput."""

    def __init__(self, consumer: Consumer, batch_size: int = 100,
                 batch_timeout: float = 5.0):
        self.consumer = consumer
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout

    def consume_batch(self) -> list[dict]:
        """Collect batch of messages."""
        batch = []
        import time
        deadline = time.time() + self.batch_timeout

        while len(batch) < self.batch_size and time.time() < deadline:
            msg = self.consumer.poll(timeout=0.5)
            if msg and not msg.error():
                batch.append(json.loads(msg.value()))

        return batch


# --- Schema Registry (Avro) ---

# schema_registry = SchemaRegistryClient({"url": "http://schema-registry:8081"})
# avro_serializer = AvroSerializer(
#     schema_registry,
#     schema_str='{"type":"record","name":"Order","fields":[...]}',
# )
# producer.produce(topic="orders", value=avro_serializer(order, ctx))
```

Kafka patterns:
1. **`acks=all` + idempotence** — exactly-once delivery per partition
2. **Key-based partitioning** — same key always goes to same partition (ordering)
3. **Manual commit** — commit after processing for at-least-once semantics
4. **Batch consuming** — collect N messages then process together for throughput
5. **Graceful shutdown** — handle SIGTERM, close consumer to trigger rebalance'''
    ),
    (
        "data-engineering/event-sourcing",
        "Show event sourcing patterns: event store, projections, snapshots, and CQRS.",
        '''Event sourcing and CQRS patterns:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4
import json
import logging

logger = logging.getLogger(__name__)


# --- Events ---

@dataclass(frozen=True)
class Event:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    aggregate_id: str = ""
    aggregate_type: str = ""
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    version: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# --- Event Store ---

class EventStore:
    """Append-only event store with optimistic concurrency."""

    def __init__(self, pool):
        self.pool = pool

    async def append(self, events: list[Event],
                     expected_version: int) -> None:
        """Append events with optimistic concurrency check."""
        if not events:
            return

        aggregate_id = events[0].aggregate_id

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Check current version (optimistic lock)
                current = await conn.fetchval(
                    "SELECT COALESCE(MAX(version), 0) "
                    "FROM events WHERE aggregate_id = $1",
                    aggregate_id,
                )
                if current != expected_version:
                    raise ConcurrencyError(
                        f"Expected version {expected_version}, "
                        f"got {current}"
                    )

                # Append events
                for i, event in enumerate(events):
                    version = expected_version + i + 1
                    await conn.execute("""
                        INSERT INTO events
                            (event_id, event_type, aggregate_id,
                             aggregate_type, data, metadata, version)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                        event.event_id, event.event_type,
                        event.aggregate_id, event.aggregate_type,
                        json.dumps(event.data),
                        json.dumps(event.metadata),
                        version,
                    )

    async def load(self, aggregate_id: str,
                   after_version: int = 0) -> list[Event]:
        """Load events for an aggregate."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM events
                WHERE aggregate_id = $1 AND version > $2
                ORDER BY version
            """, aggregate_id, after_version)

            return [
                Event(
                    event_id=r["event_id"],
                    event_type=r["event_type"],
                    aggregate_id=r["aggregate_id"],
                    aggregate_type=r["aggregate_type"],
                    data=json.loads(r["data"]),
                    version=r["version"],
                    timestamp=r["timestamp"].isoformat(),
                )
                for r in rows
            ]


# --- Aggregate (reconstructed from events) ---

class BankAccount:
    """Event-sourced aggregate."""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.balance = 0
        self.status = "active"
        self.version = 0
        self._pending_events: list[Event] = []

    # --- Commands (produce events) ---

    def deposit(self, amount: float, description: str = ""):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        self._apply(Event(
            event_type="money_deposited",
            aggregate_id=self.account_id,
            aggregate_type="BankAccount",
            data={"amount": amount, "description": description},
        ))

    def withdraw(self, amount: float, description: str = ""):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if self.balance < amount:
            raise ValueError("Insufficient funds")
        self._apply(Event(
            event_type="money_withdrawn",
            aggregate_id=self.account_id,
            aggregate_type="BankAccount",
            data={"amount": amount, "description": description},
        ))

    def close(self):
        if self.balance != 0:
            raise ValueError("Cannot close account with balance")
        self._apply(Event(
            event_type="account_closed",
            aggregate_id=self.account_id,
            aggregate_type="BankAccount",
            data={},
        ))

    # --- Event handlers (update state) ---

    def _apply(self, event: Event):
        self._handle(event)
        self._pending_events.append(event)

    def _handle(self, event: Event):
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event.data)
        self.version += 1

    def _on_money_deposited(self, data: dict):
        self.balance += data["amount"]

    def _on_money_withdrawn(self, data: dict):
        self.balance -= data["amount"]

    def _on_account_closed(self, data: dict):
        self.status = "closed"

    # --- Reconstruct from events ---

    @classmethod
    def from_events(cls, account_id: str, events: list[Event]):
        account = cls(account_id)
        for event in events:
            account._handle(event)
        return account


# --- Projections (read models) ---

class AccountBalanceProjection:
    """Maintain a read-optimized view of account balances."""

    def __init__(self, pool):
        self.pool = pool

    async def handle(self, event: Event):
        handlers = {
            "money_deposited": self._on_deposit,
            "money_withdrawn": self._on_withdrawal,
            "account_closed": self._on_closed,
        }
        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)

    async def _on_deposit(self, event: Event):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO account_balances (account_id, balance, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (account_id) DO UPDATE
                SET balance = account_balances.balance + $2,
                    updated_at = NOW()
            """, event.aggregate_id, event.data["amount"])

    async def _on_withdrawal(self, event: Event):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE account_balances
                SET balance = balance - $2, updated_at = NOW()
                WHERE account_id = $1
            """, event.aggregate_id, event.data["amount"])

    async def _on_closed(self, event: Event):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE account_balances
                SET status = 'closed', updated_at = NOW()
                WHERE account_id = $1
            """, event.aggregate_id)


# --- Snapshot for performance ---

class SnapshotStore:
    async def save(self, aggregate_id: str, state: dict, version: int):
        # Save serialized aggregate state at version N
        # Load snapshot + replay events after version N
        pass

    async def load(self, aggregate_id: str) -> tuple[dict, int] | None:
        pass
```

Event sourcing patterns:
1. **Append-only store** — events are immutable facts, never deleted or modified
2. **Optimistic concurrency** — check version before appending to prevent conflicts
3. **Aggregate reconstruction** — replay events to rebuild current state
4. **Projections** — read-optimized views updated asynchronously from events
5. **Snapshots** — periodically save aggregate state to avoid replaying all events'''
    ),
]
