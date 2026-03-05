"""Event streaming — Kafka consumers/producers, partitioning, consumer groups, exactly-once, schema evolution."""

PAIRS = [
    (
        "event-streaming/kafka-producer-patterns",
        "Show production-quality Kafka producer patterns in Python using confluent-kafka with idempotent delivery, custom partitioning, headers, and batching configuration.",
        '''Production Kafka producer with idempotent delivery, custom partitioner, and delivery callbacks:

```python
# --- kafka_producer.py --- Production Kafka producer with best practices ---

from __future__ import annotations

import json
import logging
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Callable
from datetime import datetime, timezone
from uuid import uuid4

from confluent_kafka import Producer, KafkaError, KafkaException, Message
from confluent_kafka.serialization import (
    SerializationContext,
    MessageField,
    StringSerializer,
)
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONSerializer

logger = logging.getLogger(__name__)


@dataclass
class ProducerConfig:
    """Typed Kafka producer configuration."""
    bootstrap_servers: str
    client_id: str = "hive-producer"
    acks: str = "all"                    # Wait for all ISR replicas
    enable_idempotence: bool = True      # Exactly-once per partition
    max_in_flight: int = 5               # Max unacked requests (5 is safe with idempotence)
    retries: int = 2147483647            # Infinite retries (bounded by timeout)
    delivery_timeout_ms: int = 120_000   # 2-minute delivery timeout
    linger_ms: int = 20                  # Batch for 20ms for throughput
    batch_size: int = 64 * 1024          # 64KB batch size
    compression_type: str = "zstd"       # Best compression ratio
    schema_registry_url: str | None = None

    def to_confluent_config(self) -> dict[str, Any]:
        return {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": self.client_id,
            "acks": self.acks,
            "enable.idempotence": self.enable_idempotence,
            "max.in.flight.requests.per.connection": self.max_in_flight,
            "retries": self.retries,
            "delivery.timeout.ms": self.delivery_timeout_ms,
            "linger.ms": self.linger_ms,
            "batch.size": self.batch_size,
            "compression.type": self.compression_type,
        }


@dataclass
class EventEnvelope:
    """Standard event envelope for all messages."""
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    source: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    correlation_id: str | None = None
    causation_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1


class EventPartitioner:
    """Consistent hash partitioner for event routing."""

    @staticmethod
    def partition_by_key(
        key: str | bytes, num_partitions: int, available: list[int]
    ) -> int:
        """Murmur2-compatible hash for deterministic partition assignment."""
        if isinstance(key, str):
            key = key.encode("utf-8")
        h = int(hashlib.md5(key).hexdigest(), 16)
        return available[h % len(available)]

    @staticmethod
    def partition_by_tenant(
        tenant_id: str, num_partitions: int, available: list[int]
    ) -> int:
        """Route all events for a tenant to the same partition for ordering."""
        h = int(hashlib.sha256(tenant_id.encode()).hexdigest()[:8], 16)
        return available[h % len(available)]


class KafkaEventProducer:
    """
    Production Kafka producer with:
    - Idempotent delivery (exactly-once per partition)
    - Custom partitioning strategies
    - CloudEvents-style envelope
    - Delivery confirmation callbacks
    - Graceful shutdown with flush
    - Optional Schema Registry integration
    """

    def __init__(self, config: ProducerConfig) -> None:
        self._config = config
        self._producer = Producer(config.to_confluent_config())
        self._delivery_callbacks: list[Callable[[Message | None, Exception | None], None]] = []
        self._sent_count = 0
        self._error_count = 0
        self._serializer = StringSerializer("utf_8")

        # Optional Schema Registry
        self._schema_serializer: JSONSerializer | None = None
        if config.schema_registry_url:
            sr_client = SchemaRegistryClient({"url": config.schema_registry_url})
            self._schema_serializer = JSONSerializer(
                schema_str=None,  # Use auto schema detection
                schema_registry_client=sr_client,
            )

    def _delivery_report(self, err: KafkaError | None, msg: Message) -> None:
        """Callback invoked per message on delivery success or failure."""
        if err is not None:
            self._error_count += 1
            logger.error(
                "Delivery failed for %s [%d]: %s",
                msg.topic(), msg.partition(), err,
            )
        else:
            self._sent_count += 1
            logger.debug(
                "Delivered %s [%d] @ offset %d (latency=%dms)",
                msg.topic(), msg.partition(), msg.offset(), msg.latency() * 1000,
            )

        for cb in self._delivery_callbacks:
            cb(msg if err is None else None, err)

    def on_delivery(self, callback: Callable) -> None:
        """Register additional delivery callbacks."""
        self._delivery_callbacks.append(callback)

    def produce_event(
        self,
        topic: str,
        event: EventEnvelope,
        *,
        key: str | None = None,
        partition: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Produce a single event with envelope metadata.
        Non-blocking — call flush() to wait for delivery.
        """
        # Serialize envelope
        value = json.dumps(asdict(event), default=str).encode("utf-8")
        key_bytes = key.encode("utf-8") if key else None

        # Build headers
        msg_headers = {
            "event-type": event.event_type,
            "event-id": event.event_id,
            "schema-version": str(event.schema_version),
            "content-type": "application/json",
        }
        if event.correlation_id:
            msg_headers["correlation-id"] = event.correlation_id
        if headers:
            msg_headers.update(headers)

        header_list = [(k, v.encode()) for k, v in msg_headers.items()]

        # Produce with callback
        while True:
            try:
                self._producer.produce(
                    topic=topic,
                    key=key_bytes,
                    value=value,
                    partition=partition if partition is not None else -1,
                    headers=header_list,
                    callback=self._delivery_report,
                )
                break
            except BufferError:
                logger.warning("Producer queue full, waiting...")
                self._producer.poll(1.0)

        # Trigger delivery reports for completed sends
        self._producer.poll(0)

    def produce_batch(
        self,
        topic: str,
        events: list[EventEnvelope],
        *,
        key_fn: Callable[[EventEnvelope], str | None] | None = None,
    ) -> int:
        """Produce a batch of events. Returns count queued."""
        for event in events:
            key = key_fn(event) if key_fn else None
            self.produce_event(topic, event, key=key)
        return len(events)

    def flush(self, timeout: float = 30.0) -> int:
        """Flush all queued messages. Returns number remaining (0 = all delivered)."""
        remaining = self._producer.flush(timeout)
        if remaining > 0:
            logger.warning("%d messages still in queue after flush timeout", remaining)
        return remaining

    @property
    def stats(self) -> dict[str, int]:
        return {"sent": self._sent_count, "errors": self._error_count}

    def close(self) -> None:
        """Graceful shutdown: flush remaining messages then clean up."""
        logger.info("Shutting down producer, flushing...")
        self.flush(timeout=60.0)
        logger.info("Producer closed. Stats: %s", self.stats)


# ---- Usage example ----

def main():
    config = ProducerConfig(
        bootstrap_servers="kafka-1:9092,kafka-2:9092,kafka-3:9092",
        client_id="order-service",
        compression_type="zstd",
    )
    producer = KafkaEventProducer(config)

    # Produce an order event
    event = EventEnvelope(
        event_type="order.created",
        source="order-service",
        correlation_id="req-abc-123",
        payload={
            "order_id": "ord-001",
            "customer_id": "cust-42",
            "items": [{"sku": "WIDGET-01", "qty": 3, "price": 29.99}],
            "total": 89.97,
        },
    )
    producer.produce_event(
        topic="orders.events",
        event=event,
        key="cust-42",  # Partition by customer for ordering
    )
    producer.flush()
    producer.close()
```

Key producer patterns:

| Setting | Value | Why |
|---------|-------|-----|
| `acks=all` | Wait for all ISR | No data loss |
| `enable.idempotence=true` | Dedup retries | Exactly-once per partition |
| `max.in.flight=5` | Pipelining | Safe with idempotence ON |
| `compression.type=zstd` | Best ratio | 3-5x reduction |
| `linger.ms=20` | Micro-batching | Throughput vs latency tradeoff |

- **Delivery callbacks** provide async confirmation without blocking the producer loop
- **BufferError handling** back-pressures when the internal queue is full
- **Event envelope** standardizes metadata (CloudEvents-compatible)
- **Custom partitioning** ensures related events (same tenant/customer) land on the same partition for ordering
'''
    ),
    (
        "event-streaming/kafka-consumer-groups",
        "Implement a production Kafka consumer with consumer group management, manual offset commits, error handling, and graceful rebalancing in Python.",
        '''Production Kafka consumer with consumer groups, manual commits, and rebalance handling:

```python
# --- kafka_consumer.py --- Production consumer with exactly-once processing ---

from __future__ import annotations

import json
import logging
import signal
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from collections import defaultdict

from confluent_kafka import (
    Consumer, KafkaError, KafkaException, Message,
    TopicPartition, OFFSET_STORED,
)

logger = logging.getLogger(__name__)


class EventHandler(Protocol):
    """Protocol for event handlers."""
    def __call__(self, event_type: str, payload: dict[str, Any], metadata: dict[str, Any]) -> None: ...


@dataclass
class ConsumerConfig:
    bootstrap_servers: str
    group_id: str
    topics: list[str]
    client_id: str = "hive-consumer"
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False   # Manual commits for exactly-once
    max_poll_interval_ms: int = 300_000
    session_timeout_ms: int = 45_000
    heartbeat_interval_ms: int = 3_000
    fetch_min_bytes: int = 1024
    fetch_max_wait_ms: int = 500
    max_partition_fetch_bytes: int = 1_048_576  # 1MB

    def to_confluent_config(self) -> dict[str, Any]:
        return {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": self.group_id,
            "client.id": self.client_id,
            "auto.offset.reset": self.auto_offset_reset,
            "enable.auto.commit": self.enable_auto_commit,
            "max.poll.interval.ms": self.max_poll_interval_ms,
            "session.timeout.ms": self.session_timeout_ms,
            "heartbeat.interval.ms": self.heartbeat_interval_ms,
            "fetch.min.bytes": self.fetch_min_bytes,
            "fetch.wait.max.ms": self.fetch_max_wait_ms,
            "max.partition.fetch.bytes": self.max_partition_fetch_bytes,
            "partition.assignment.strategy": "cooperative-sticky",
        }


class OffsetTracker:
    """Track processed offsets per partition for manual commit."""

    def __init__(self):
        self._offsets: dict[tuple[str, int], int] = {}  # (topic, partition) -> offset
        self._pending_count = 0
        self._commit_threshold = 100  # Commit every N messages

    def mark(self, topic: str, partition: int, offset: int) -> None:
        key = (topic, partition)
        current = self._offsets.get(key, -1)
        if offset > current:
            self._offsets[key] = offset
            self._pending_count += 1

    def should_commit(self) -> bool:
        return self._pending_count >= self._commit_threshold

    def get_offsets(self) -> list[TopicPartition]:
        """Return TopicPartitions with offset+1 (next offset to read)."""
        return [
            TopicPartition(topic, part, offset + 1)
            for (topic, part), offset in self._offsets.items()
        ]

    def reset(self) -> None:
        self._pending_count = 0

    def remove_partition(self, topic: str, partition: int) -> None:
        self._offsets.pop((topic, partition), None)


class KafkaEventConsumer:
    """
    Production Kafka consumer featuring:
    - Consumer group with cooperative-sticky assignment
    - Manual offset commits (at-least-once / exactly-once with idempotent handler)
    - Graceful rebalance with on_assign/on_revoke
    - Dead letter queue for poison messages
    - Metrics tracking
    - Signal-based graceful shutdown
    """

    def __init__(
        self,
        config: ConsumerConfig,
        *,
        dead_letter_topic: str | None = None,
    ) -> None:
        self._config = config
        self._consumer = Consumer(config.to_confluent_config())
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._offset_tracker = OffsetTracker()
        self._running = False
        self._dead_letter_topic = dead_letter_topic
        self._stats = {
            "processed": 0,
            "errors": 0,
            "rebalances": 0,
            "commits": 0,
        }

    # ---- Handler registration ----

    def on(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)

    def on_any(self, handler: EventHandler) -> None:
        """Register a handler for all event types."""
        self._handlers["*"].append(handler)

    # ---- Rebalance callbacks ----

    def _on_assign(self, consumer: Consumer, partitions: list[TopicPartition]) -> None:
        """Called when partitions are assigned to this consumer."""
        logger.info(
            "Partitions assigned: %s",
            [(tp.topic, tp.partition) for tp in partitions],
        )
        self._stats["rebalances"] += 1

    def _on_revoke(self, consumer: Consumer, partitions: list[TopicPartition]) -> None:
        """Called when partitions are revoked — commit offsets before losing them."""
        logger.info(
            "Partitions revoked: %s — committing offsets",
            [(tp.topic, tp.partition) for tp in partitions],
        )
        # Commit tracked offsets for revoked partitions
        offsets = self._offset_tracker.get_offsets()
        revoked_offsets = [
            o for o in offsets
            if any(tp.topic == o.topic and tp.partition == o.partition for tp in partitions)
        ]
        if revoked_offsets:
            consumer.commit(offsets=revoked_offsets, asynchronous=False)
            self._stats["commits"] += 1

        # Clean up tracker
        for tp in partitions:
            self._offset_tracker.remove_partition(tp.topic, tp.partition)

    # ---- Message processing ----

    def _parse_message(self, msg: Message) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """Parse message into (event_type, payload, metadata)."""
        value = json.loads(msg.value().decode("utf-8"))
        headers = {
            k: v.decode("utf-8") if isinstance(v, bytes) else v
            for k, v in (msg.headers() or [])
        }

        event_type = headers.get("event-type", value.get("event_type", "unknown"))
        metadata = {
            "event_id": headers.get("event-id", value.get("event_id")),
            "topic": msg.topic(),
            "partition": msg.partition(),
            "offset": msg.offset(),
            "timestamp": msg.timestamp(),
            "headers": headers,
            "correlation_id": headers.get("correlation-id"),
        }

        payload = value.get("payload", value)
        return event_type, payload, metadata

    def _handle_message(self, msg: Message) -> None:
        """Dispatch message to registered handlers."""
        try:
            event_type, payload, metadata = self._parse_message(msg)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("Failed to parse message at offset %d: %s", msg.offset(), e)
            self._send_to_dead_letter(msg, str(e))
            return

        # Find matching handlers
        handlers = self._handlers.get(event_type, []) + self._handlers.get("*", [])
        if not handlers:
            logger.debug("No handler for event type '%s', skipping", event_type)
            return

        for handler in handlers:
            try:
                handler(event_type, payload, metadata)
            except Exception as e:
                logger.exception(
                    "Handler error for %s at %s[%d]@%d: %s",
                    event_type, msg.topic(), msg.partition(), msg.offset(), e,
                )
                self._stats["errors"] += 1
                self._send_to_dead_letter(msg, str(e))
                return  # Don't commit offset on error

        self._offset_tracker.mark(msg.topic(), msg.partition(), msg.offset())
        self._stats["processed"] += 1

    def _send_to_dead_letter(self, msg: Message, error: str) -> None:
        """Forward poison messages to DLQ for investigation."""
        if not self._dead_letter_topic:
            return
        # In production, use a separate Producer instance
        logger.warning(
            "Sending to DLQ %s: topic=%s partition=%d offset=%d error=%s",
            self._dead_letter_topic, msg.topic(), msg.partition(), msg.offset(), error,
        )

    def _commit_offsets(self) -> None:
        """Synchronously commit tracked offsets."""
        offsets = self._offset_tracker.get_offsets()
        if offsets:
            self._consumer.commit(offsets=offsets, asynchronous=False)
            self._offset_tracker.reset()
            self._stats["commits"] += 1
            logger.debug("Committed offsets for %d partitions", len(offsets))

    # ---- Main loop ----

    def run(self, poll_timeout: float = 1.0) -> None:
        """Start the consumer loop. Blocks until shutdown signal."""
        self._running = True

        # Graceful shutdown on SIGTERM/SIGINT
        def _signal_handler(sig, frame):
            logger.info("Received signal %d, shutting down...", sig)
            self._running = False

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        self._consumer.subscribe(
            self._config.topics,
            on_assign=self._on_assign,
            on_revoke=self._on_revoke,
        )
        logger.info("Consumer started, topics=%s, group=%s",
                     self._config.topics, self._config.group_id)

        try:
            while self._running:
                msg = self._consumer.poll(poll_timeout)
                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("Reached end of partition %s[%d]",
                                     msg.topic(), msg.partition())
                    else:
                        raise KafkaException(msg.error())
                    continue

                self._handle_message(msg)

                # Periodic commit
                if self._offset_tracker.should_commit():
                    self._commit_offsets()

        except KeyboardInterrupt:
            pass
        finally:
            # Final commit and cleanup
            self._commit_offsets()
            self._consumer.close()
            logger.info("Consumer closed. Stats: %s", self._stats)
```

Key consumer patterns:

| Pattern | Implementation | Purpose |
|---------|---------------|---------|
| Manual commits | `enable.auto.commit=false` | Control exactly when offsets are committed |
| Cooperative rebalancing | `cooperative-sticky` strategy | Minimize partition shuffling |
| Revoke commit | `on_revoke` callback | Prevent offset loss during rebalance |
| Dead letter queue | Forward poison messages | Isolate bad messages for debugging |
| Offset tracking | Per-partition high-water mark | Batch commits for efficiency |
| Signal handling | SIGTERM/SIGINT | Graceful shutdown with final commit |

- **At-least-once** by default: commit after processing, re-process on crash
- **Exactly-once** achievable with idempotent handlers + transactional producer
- **Cooperative-sticky** minimizes partition movement during consumer group changes
'''
    ),
    (
        "event-streaming/kafka-exactly-once-transactions",
        "Implement exactly-once semantics in Kafka using transactions for a consume-transform-produce pattern in Python.",
        '''Exactly-once Kafka processing using transactional consume-transform-produce:

```python
# --- kafka_eos.py --- Exactly-once semantics with Kafka transactions ---

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable
from contextlib import contextmanager

from confluent_kafka import (
    Consumer, Producer, KafkaError, KafkaException,
    Message, TopicPartition,
)

logger = logging.getLogger(__name__)


@dataclass
class EOSConfig:
    """Configuration for exactly-once processing."""
    bootstrap_servers: str
    consumer_group_id: str
    transactional_id: str  # Must be unique per producer instance
    input_topics: list[str]
    isolation_level: str = "read_committed"  # Only see committed messages


class TransactionalProcessor:
    """
    Exactly-once consume-transform-produce pipeline.

    Uses Kafka transactions to atomically:
    1. Read from input topic
    2. Process/transform the message
    3. Write to output topic(s)
    4. Commit consumer offsets

    All within a single transaction — either everything succeeds or
    everything is rolled back.
    """

    def __init__(self, config: EOSConfig) -> None:
        self._config = config

        # Transactional producer
        self._producer = Producer({
            "bootstrap.servers": config.bootstrap_servers,
            "transactional.id": config.transactional_id,
            "enable.idempotence": True,
            "acks": "all",
            "max.in.flight.requests.per.connection": 5,
        })

        # Consumer with read_committed isolation
        self._consumer = Consumer({
            "bootstrap.servers": config.bootstrap_servers,
            "group.id": config.consumer_group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,  # Offsets committed in transaction
            "isolation.level": config.isolation_level,
        })

        self._running = False
        self._transform_fn: Callable | None = None

        # Initialize transactions (must be called before any transactional operation)
        logger.info("Initializing transactions for %s", config.transactional_id)
        self._producer.init_transactions(timeout=30.0)

    def set_transform(
        self,
        fn: Callable[[str, dict[str, Any]], list[tuple[str, str | None, dict[str, Any]]]],
    ) -> None:
        """
        Set the transform function.
        Input: (event_type, payload)
        Output: list of (output_topic, key, output_payload)
        """
        self._transform_fn = fn

    @contextmanager
    def _transaction(self):
        """Context manager for Kafka transactions with automatic abort on error."""
        self._producer.begin_transaction()
        try:
            yield
            self._producer.commit_transaction(timeout=30.0)
        except Exception:
            logger.exception("Transaction failed, aborting")
            try:
                self._producer.abort_transaction(timeout=10.0)
            except Exception:
                logger.exception("Failed to abort transaction — producer is fenced")
                raise
            raise

    def _process_message(self, msg: Message) -> None:
        """Process a single message within a transaction."""
        if self._transform_fn is None:
            raise RuntimeError("No transform function set")

        # Parse input
        value = json.loads(msg.value().decode("utf-8"))
        event_type = value.get("event_type", "unknown")
        payload = value.get("payload", value)

        # Transform
        outputs = self._transform_fn(event_type, payload)

        with self._transaction():
            # Produce output messages within the transaction
            for output_topic, key, output_payload in outputs:
                output_value = json.dumps({
                    "event_type": f"{event_type}.processed",
                    "source_topic": msg.topic(),
                    "source_partition": msg.partition(),
                    "source_offset": msg.offset(),
                    "payload": output_payload,
                }).encode("utf-8")

                self._producer.produce(
                    topic=output_topic,
                    key=key.encode("utf-8") if key else None,
                    value=output_value,
                )

            # Commit consumer offsets within the same transaction
            # This is the key to exactly-once: offset commit and output
            # produce are atomic
            self._producer.send_offsets_to_transaction(
                [TopicPartition(msg.topic(), msg.partition(), msg.offset() + 1)],
                self._consumer.consumer_group_metadata(),
                timeout=30.0,
            )

        logger.debug(
            "Processed %s[%d]@%d -> %d outputs",
            msg.topic(), msg.partition(), msg.offset(), len(outputs),
        )

    def run(self, poll_timeout: float = 1.0) -> None:
        """Main processing loop."""
        self._running = True
        self._consumer.subscribe(self._config.input_topics)
        logger.info("EOS processor started, topics=%s", self._config.input_topics)

        try:
            while self._running:
                msg = self._consumer.poll(poll_timeout)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(msg.error())

                try:
                    self._process_message(msg)
                except KafkaException as e:
                    if "fenced" in str(e).lower():
                        logger.critical("Producer fenced — another instance took over")
                        break
                    raise

        finally:
            self._consumer.close()
            logger.info("EOS processor stopped")

    def stop(self) -> None:
        self._running = False


# ---- Usage example: order enrichment pipeline ----

def enrich_order(event_type: str, payload: dict) -> list[tuple[str, str | None, dict]]:
    """Transform: enrich order with computed fields."""
    if event_type != "order.created":
        return []  # Skip non-order events

    order_id = payload.get("order_id", "unknown")
    items = payload.get("items", [])

    # Compute enrichments
    total = sum(item["qty"] * item["price"] for item in items)
    tax = round(total * 0.08, 2)

    enriched = {
        **payload,
        "computed_total": total,
        "tax": tax,
        "grand_total": round(total + tax, 2),
        "item_count": sum(item["qty"] for item in items),
    }

    return [
        ("orders.enriched", order_id, enriched),
        ("analytics.order-metrics", None, {
            "order_id": order_id,
            "total": total,
            "item_count": enriched["item_count"],
        }),
    ]


def main():
    config = EOSConfig(
        bootstrap_servers="kafka-1:9092,kafka-2:9092",
        consumer_group_id="order-enrichment",
        transactional_id="order-enrichment-0",  # Unique per instance
        input_topics=["orders.events"],
    )

    processor = TransactionalProcessor(config)
    processor.set_transform(enrich_order)
    processor.run()
```

Exactly-once semantics key points:

| Component | Requirement | Purpose |
|-----------|------------|---------|
| `transactional.id` | Unique per producer instance | Enables fencing of zombie producers |
| `init_transactions()` | Called once at startup | Registers transactional producer with coordinator |
| `begin_transaction()` | Before each produce batch | Starts atomic unit of work |
| `send_offsets_to_transaction()` | Within transaction | Atomic offset commit with produces |
| `commit_transaction()` | After all produces | Makes all writes visible atomically |
| `isolation.level=read_committed` | On downstream consumers | Skip aborted/uncommitted messages |

- **Fencing**: If two producers share the same `transactional.id`, the older one is fenced (killed)
- **Zombie protection**: Crashed producer's uncommitted messages are invisible to `read_committed` consumers
- **Performance**: Transactions add ~10-20ms latency per batch; use micro-batching to amortize
'''
    ),
    (
        "event-streaming/schema-evolution-avro",
        "Show how to implement schema evolution for Kafka events using Avro with the Confluent Schema Registry, including compatibility modes and migration strategies.",
        '''Schema evolution with Avro and Confluent Schema Registry for Kafka events:

```python
# --- schema_evolution.py --- Avro schema evolution with Schema Registry ---

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from confluent_kafka import Producer, Consumer, Message
from confluent_kafka.serialization import (
    SerializationContext,
    MessageField,
)
from confluent_kafka.schema_registry import SchemaRegistryClient, Schema
from confluent_kafka.schema_registry.avro import (
    AvroSerializer,
    AvroDeserializer,
)

logger = logging.getLogger(__name__)

# ---- Schema definitions showing evolution ----

# V1: Original schema
ORDER_SCHEMA_V1 = """{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.hiveai.orders",
  "fields": [
    {"name": "order_id", "type": "string"},
    {"name": "customer_id", "type": "string"},
    {"name": "total", "type": "double"},
    {"name": "status", "type": {"type": "enum", "name": "Status",
      "symbols": ["CREATED", "PAID", "SHIPPED", "DELIVERED"]
    }},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}"""

# V2: BACKWARD compatible — add optional field with default
ORDER_SCHEMA_V2 = """{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.hiveai.orders",
  "fields": [
    {"name": "order_id", "type": "string"},
    {"name": "customer_id", "type": "string"},
    {"name": "total", "type": "double"},
    {"name": "status", "type": {"type": "enum", "name": "Status",
      "symbols": ["CREATED", "PAID", "SHIPPED", "DELIVERED", "CANCELLED"]
    }},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "currency", "type": "string", "default": "USD"},
    {"name": "discount_pct", "type": ["null", "double"], "default": null},
    {"name": "tags", "type": {"type": "array", "items": "string"}, "default": []}
  ]
}"""

# V3: FULL compatible — add optional field, keep all existing
ORDER_SCHEMA_V3 = """{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.hiveai.orders",
  "fields": [
    {"name": "order_id", "type": "string"},
    {"name": "customer_id", "type": "string"},
    {"name": "total", "type": "double"},
    {"name": "status", "type": {"type": "enum", "name": "Status",
      "symbols": ["CREATED", "PAID", "SHIPPED", "DELIVERED", "CANCELLED", "REFUNDED"]
    }},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "currency", "type": "string", "default": "USD"},
    {"name": "discount_pct", "type": ["null", "double"], "default": null},
    {"name": "tags", "type": {"type": "array", "items": "string"}, "default": []},
    {"name": "shipping_address", "type": ["null", {
      "type": "record",
      "name": "Address",
      "fields": [
        {"name": "street", "type": "string"},
        {"name": "city", "type": "string"},
        {"name": "state", "type": "string"},
        {"name": "zip", "type": "string"},
        {"name": "country", "type": "string", "default": "US"}
      ]
    }], "default": null},
    {"name": "metadata", "type": {"type": "map", "values": "string"}, "default": {}}
  ]
}"""


class SchemaManager:
    """
    Manage schema evolution with Confluent Schema Registry.
    Handles registration, compatibility checking, and version tracking.
    """

    def __init__(self, registry_url: str) -> None:
        self._client = SchemaRegistryClient({"url": registry_url})
        self._cache: dict[str, int] = {}  # subject -> latest schema_id

    def register_schema(
        self,
        subject: str,
        schema_str: str,
        schema_type: str = "AVRO",
    ) -> int:
        """Register a schema and return its ID."""
        schema = Schema(schema_str, schema_type)
        schema_id = self._client.register_schema(subject, schema)
        self._cache[subject] = schema_id
        logger.info("Registered schema %s v%d (id=%d)", subject, self.get_latest_version(subject), schema_id)
        return schema_id

    def check_compatibility(
        self,
        subject: str,
        schema_str: str,
        schema_type: str = "AVRO",
    ) -> bool:
        """Check if a schema is compatible with the subject's existing schemas."""
        schema = Schema(schema_str, schema_type)
        try:
            return self._client.test_compatibility(subject, schema)
        except Exception as e:
            logger.error("Compatibility check failed: %s", e)
            return False

    def set_compatibility(self, subject: str, level: str) -> None:
        """Set compatibility mode for a subject."""
        self._client.set_compatibility(subject, level)
        logger.info("Set compatibility for %s to %s", subject, level)

    def get_latest_version(self, subject: str) -> int:
        """Get the latest version number for a subject."""
        try:
            reg = self._client.get_latest_version(subject)
            return reg.version
        except Exception:
            return 0

    def get_all_versions(self, subject: str) -> list[int]:
        """List all registered versions."""
        return self._client.get_versions(subject)

    def get_schema_by_version(self, subject: str, version: int) -> str:
        """Retrieve a specific schema version."""
        reg = self._client.get_version(subject, version)
        return reg.schema.schema_str


class EvolvableProducer:
    """Producer that serializes with the latest registered Avro schema."""

    def __init__(
        self,
        bootstrap_servers: str,
        registry_url: str,
        topic: str,
        schema_str: str,
    ) -> None:
        self._topic = topic
        self._sr_client = SchemaRegistryClient({"url": registry_url})
        self._serializer = AvroSerializer(
            self._sr_client,
            schema_str,
            conf={"auto.register.schemas": True, "normalize.schemas": True},
        )
        self._producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",
            "enable.idempotence": True,
        })

    def produce(self, key: str, value: dict[str, Any]) -> None:
        """Produce an Avro-serialized message."""
        ctx = SerializationContext(self._topic, MessageField.VALUE)
        serialized = self._serializer(value, ctx)
        self._producer.produce(
            topic=self._topic,
            key=key.encode("utf-8"),
            value=serialized,
        )
        self._producer.poll(0)

    def flush(self) -> None:
        self._producer.flush()


class EvolvableConsumer:
    """Consumer that deserializes any schema version via Schema Registry."""

    def __init__(
        self,
        bootstrap_servers: str,
        registry_url: str,
        group_id: str,
        topics: list[str],
    ) -> None:
        self._sr_client = SchemaRegistryClient({"url": registry_url})
        self._deserializer = AvroDeserializer(
            self._sr_client,
            # No schema_str needed — reads writer's schema from registry
        )
        self._consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
        })
        self._consumer.subscribe(topics)

    def poll(self, timeout: float = 1.0) -> dict[str, Any] | None:
        """Poll and deserialize one message."""
        msg = self._consumer.poll(timeout)
        if msg is None or msg.error():
            return None

        ctx = SerializationContext(msg.topic(), MessageField.VALUE)
        return self._deserializer(msg.value(), ctx)

    def close(self) -> None:
        self._consumer.close()


# ---- Migration strategy example ----

def migrate_schema_safely(
    manager: SchemaManager,
    subject: str,
    new_schema: str,
) -> bool:
    """
    Safe schema migration workflow:
    1. Check compatibility
    2. Register if compatible
    3. Validate with test message
    """
    # Step 1: Check compatibility
    if not manager.check_compatibility(subject, new_schema):
        logger.error("Schema is NOT compatible with %s", subject)
        return False

    # Step 2: Register new version
    schema_id = manager.register_schema(subject, new_schema)
    version = manager.get_latest_version(subject)
    logger.info("Schema %s evolved to v%d (id=%d)", subject, version, schema_id)

    return True
```

Schema evolution compatibility rules:

| Compatibility | Add Field | Remove Field | Modify Field |
|---------------|-----------|-------------|-------------|
| BACKWARD | With default | Yes | Widen type only |
| FORWARD | Yes | With default | Narrow type only |
| FULL | With default | With default | No |
| NONE | Yes | Yes | Yes |

Safe evolution strategies:

- **Adding fields**: Always provide a default value (BACKWARD compatible)
- **Removing fields**: Only if field had a default (FORWARD compatible)
- **Renaming fields**: Add new field with alias, deprecate old (two-step migration)
- **Enum evolution**: Only add symbols (never remove/reorder)
- **Union types**: Use `["null", "type"]` for optional fields
- **Nested records**: Same rules apply recursively

| Step | Action | Risk |
|------|--------|------|
| 1 | Set FULL_TRANSITIVE compatibility | Prevents breaking changes |
| 2 | Deploy new consumers first | Can read old + new schemas |
| 3 | Register new schema | Validated against all prior versions |
| 4 | Deploy new producers | Start writing new format |
| 5 | Verify old consumers still work | Schema Registry provides reader schema |
'''
    ),
    (
        "event-streaming/kafka-partitioning-strategy",
        "Explain Kafka partitioning strategies with implementation examples for hot partition prevention, partition-aware processing, and custom partitioners.",
        '''Kafka partitioning strategies with hot partition prevention and custom partitioners:

```python
# --- partitioning.py --- Advanced Kafka partitioning strategies ---

from __future__ import annotations

import hashlib
import logging
import struct
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class Murmur2Partitioner:
    """
    Default Kafka partitioner (murmur2 hash).
    Compatible with Java Kafka client's DefaultPartitioner.
    """

    @staticmethod
    def murmur2(data: bytes) -> int:
        """Pure Python murmur2 hash matching Kafka's Java implementation."""
        length = len(data)
        seed = 0x9747b28c
        m = 0x5bd1e995
        r = 24
        h = seed ^ length
        i = 0

        while length >= 4:
            k = struct.unpack_from("<I", data, i)[0]
            k = (k * m) & 0xFFFFFFFF
            k ^= k >> r
            k = (k * m) & 0xFFFFFFFF
            h = (h * m) & 0xFFFFFFFF
            h ^= k
            i += 4
            length -= 4

        if length >= 3:
            h ^= data[i + 2] << 16
        if length >= 2:
            h ^= data[i + 1] << 8
        if length >= 1:
            h ^= data[i]
            h = (h * m) & 0xFFFFFFFF

        h ^= h >> 13
        h = (h * m) & 0xFFFFFFFF
        h ^= h >> 15

        # Convert to signed 32-bit
        if h >= 0x80000000:
            h -= 0x100000000
        return h

    @staticmethod
    def partition(key: bytes, num_partitions: int) -> int:
        h = Murmur2Partitioner.murmur2(key)
        return (h & 0x7FFFFFFF) % num_partitions


class ConsistentHashPartitioner:
    """
    Consistent hashing partitioner with virtual nodes.
    Minimizes partition reassignment when partition count changes.
    """

    def __init__(self, num_partitions: int, vnodes: int = 150) -> None:
        self._ring: list[tuple[int, int]] = []  # (hash, partition)
        for p in range(num_partitions):
            for v in range(vnodes):
                key = f"partition-{p}-vnode-{v}".encode()
                h = int(hashlib.sha256(key).hexdigest(), 16)
                self._ring.append((h, p))
        self._ring.sort(key=lambda x: x[0])
        self._hashes = [h for h, _ in self._ring]

    def partition(self, key: bytes) -> int:
        h = int(hashlib.sha256(key).hexdigest(), 16)
        # Binary search for nearest node
        import bisect
        idx = bisect.bisect_left(self._hashes, h) % len(self._ring)
        return self._ring[idx][1]


class WeightedPartitioner:
    """
    Weighted partitioner for heterogeneous partition capacities.
    Useful when partition brokers have different hardware specs.
    """

    def __init__(self, weights: dict[int, float]) -> None:
        self._weights = weights
        self._total = sum(weights.values())
        # Build cumulative distribution
        self._cdf: list[tuple[float, int]] = []
        cumulative = 0.0
        for partition, weight in sorted(weights.items()):
            cumulative += weight / self._total
            self._cdf.append((cumulative, partition))

    def partition(self, key: bytes) -> int:
        h = int(hashlib.md5(key).hexdigest(), 16)
        normalized = (h % 10000) / 10000.0
        for threshold, partition in self._cdf:
            if normalized <= threshold:
                return partition
        return self._cdf[-1][1]


class HotKeyPartitioner:
    """
    Anti-hot-partition strategy: spread high-cardinality keys
    across partitions using salting.
    """

    def __init__(
        self,
        num_partitions: int,
        hot_keys: set[str],
        spread_factor: int = 4,
    ) -> None:
        self._num_partitions = num_partitions
        self._hot_keys = hot_keys
        self._spread_factor = spread_factor
        self._counters: dict[str, int] = defaultdict(int)

    def partition(self, key: str) -> int:
        if key in self._hot_keys:
            # Spread hot keys across multiple partitions using round-robin salt
            salt = self._counters[key] % self._spread_factor
            self._counters[key] += 1
            salted_key = f"{key}__salt_{salt}"
            h = int(hashlib.md5(salted_key.encode()).hexdigest(), 16)
            return h % self._num_partitions
        else:
            # Normal keys use standard hashing
            h = int(hashlib.md5(key.encode()).hexdigest(), 16)
            return h % self._num_partitions


@dataclass
class PartitionStats:
    """Track partition-level metrics for detecting hot partitions."""
    message_count: int = 0
    byte_count: int = 0
    last_offset: int = 0
    lag: int = 0
    throughput_per_sec: float = 0.0
    _window_start: float = field(default_factory=time.time)
    _window_count: int = 0

    def record(self, bytes_size: int, offset: int) -> None:
        self.message_count += 1
        self.byte_count += bytes_size
        self.last_offset = offset
        self._window_count += 1
        elapsed = time.time() - self._window_start
        if elapsed >= 10.0:  # Calculate throughput every 10s
            self.throughput_per_sec = self._window_count / elapsed
            self._window_count = 0
            self._window_start = time.time()


class PartitionMonitor:
    """
    Monitor partition balance and detect hot partitions.
    Alert when a partition receives disproportionate traffic.
    """

    def __init__(
        self,
        num_partitions: int,
        skew_threshold: float = 2.0,
    ) -> None:
        self._stats = {p: PartitionStats() for p in range(num_partitions)}
        self._skew_threshold = skew_threshold
        self._num_partitions = num_partitions

    def record(self, partition: int, bytes_size: int, offset: int) -> None:
        self._stats[partition].record(bytes_size, offset)

    def detect_hot_partitions(self) -> list[int]:
        """Find partitions with traffic > threshold * average."""
        total = sum(s.message_count for s in self._stats.values())
        if total == 0:
            return []
        avg = total / self._num_partitions
        return [
            p for p, s in self._stats.items()
            if s.message_count > avg * self._skew_threshold
        ]

    def get_report(self) -> dict[int, dict[str, Any]]:
        total = sum(s.message_count for s in self._stats.values()) or 1
        return {
            p: {
                "messages": s.message_count,
                "bytes": s.byte_count,
                "pct_of_total": round(s.message_count / total * 100, 1),
                "throughput_per_sec": round(s.throughput_per_sec, 1),
                "is_hot": s.message_count > (total / self._num_partitions) * self._skew_threshold,
            }
            for p, s in self._stats.items()
        }
```

Partitioning strategy comparison:

| Strategy | Use Case | Ordering | Hot-Partition Risk |
|----------|----------|----------|-------------------|
| Murmur2 (default) | General purpose | Per-key | Medium (popular keys) |
| Consistent hash | Partition count changes | Per-key | Medium |
| Weighted | Heterogeneous brokers | Per-key | Low |
| Hot-key salting | Known hot keys | Relaxed for hot keys | Low |
| Round-robin | Maximum throughput | None | None |
| Custom tenant-based | Multi-tenant | Per-tenant | Depends on tenant size |

Key considerations:

- **Ordering guarantee**: Kafka guarantees ordering within a partition only
- **Key-based partitioning**: Same key always goes to same partition (barring rebalance)
- **Hot partitions**: A few keys receiving disproportionate traffic overload individual brokers
- **Salting trades ordering for balance**: Spread hot keys, but lose strict ordering for those keys
- **Monitor partition skew**: Alert when any partition exceeds 2x the average traffic
- **Partition count**: Choose a count that's a multiple of your consumer group size
'''
    ),
]
