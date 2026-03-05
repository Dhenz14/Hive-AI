"""Change Data Capture (CDC) — Debezium, event processing, outbox pattern, cache/search sync."""

PAIRS = [
    (
        "data-engineering/debezium-cdc-postgresql",
        "Show Debezium CDC connector setup for PostgreSQL including configuration, event format, schema registry, and deployment with Kafka Connect.",
        '''Debezium CDC connector for PostgreSQL with Kafka Connect:

```json
// --- Debezium PostgreSQL connector configuration ---
// POST to Kafka Connect REST API: POST /connectors

{
  "name": "postgres-cdc-orders",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres-primary",
    "database.port": "5432",
    "database.user": "debezium_repl",
    "database.password": "${file:/opt/kafka/secrets/pg-password.txt:password}",
    "database.dbname": "ecommerce",

    "topic.prefix": "cdc.ecommerce",
    "schema.include.list": "public",
    "table.include.list": "public.orders,public.customers,public.payments",

    "plugin.name": "pgoutput",
    "slot.name": "debezium_orders",
    "publication.name": "dbz_publication",

    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": "http://schema-registry:8081",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": "http://schema-registry:8081",

    "transforms": "route,unwrap",
    "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.route.regex": "cdc\\.ecommerce\\.public\\.(.*)",
    "transforms.route.replacement": "cdc.$1",
    "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
    "transforms.unwrap.drop.tombstones": "false",
    "transforms.unwrap.delete.handling.mode": "rewrite",
    "transforms.unwrap.add.fields": "op,source.ts_ms,source.lsn",

    "snapshot.mode": "initial",
    "snapshot.locking.mode": "none",

    "heartbeat.interval.ms": "10000",
    "tombstones.on.delete": "true",

    "signal.data.collection": "public.debezium_signals",
    "signal.enabled.channels": "source",

    "errors.tolerance": "all",
    "errors.deadletterqueue.topic.name": "cdc.dlq",
    "errors.deadletterqueue.context.headers.enable": "true",

    "topic.creation.enable": "true",
    "topic.creation.default.replication.factor": 3,
    "topic.creation.default.partitions": 6,
    "topic.creation.default.cleanup.policy": "compact"
  }
}
```

```sql
-- PostgreSQL setup for Debezium CDC

-- 1. Set WAL level to logical (requires restart)
ALTER SYSTEM SET wal_level = 'logical';

-- 2. Create replication user
CREATE ROLE debezium_repl WITH REPLICATION LOGIN PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE ecommerce TO debezium_repl;
GRANT USAGE ON SCHEMA public TO debezium_repl;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO debezium_repl;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO debezium_repl;

-- 3. Create publication for specific tables
CREATE PUBLICATION dbz_publication FOR TABLE
    public.orders,
    public.customers,
    public.payments;

-- 4. Create signal table (for Debezium signal commands)
CREATE TABLE public.debezium_signals (
    id VARCHAR(42) PRIMARY KEY,
    type VARCHAR(32) NOT NULL,
    data VARCHAR(2048) NULL
);
GRANT INSERT ON public.debezium_signals TO debezium_repl;

-- 5. Monitor replication lag
SELECT
    slot_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)
        AS lag_bytes,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)
    ) AS lag_pretty
FROM pg_replication_slots
WHERE slot_name = 'debezium_orders';
```

```python
# --- Debezium CDC event consumer (Python) ---

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
import json
import logging

from confluent_kafka import Consumer, KafkaError, KafkaException

logger = logging.getLogger("cdc.consumer")


@dataclass
class CDCEvent:
    """Parsed CDC change event."""
    operation: str          # "c" (create), "u" (update), "d" (delete), "r" (read/snapshot)
    table: str
    key: dict
    before: dict | None
    after: dict | None
    source_ts_ms: int
    lsn: int | None
    transaction_id: str | None

    @property
    def is_create(self) -> bool:
        return self.operation in ("c", "r")

    @property
    def is_update(self) -> bool:
        return self.operation == "u"

    @property
    def is_delete(self) -> bool:
        return self.operation == "d"

    @property
    def source_timestamp(self) -> datetime:
        return datetime.fromtimestamp(
            self.source_ts_ms / 1000, tz=timezone.utc
        )


class CDCConsumer:
    """Consume Debezium CDC events from Kafka."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
    ) -> None:
        config = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "isolation.level": "read_committed",
        }
        self.consumer = Consumer(config)
        self.consumer.subscribe(topics)
        self._handlers: dict[str, list] = {}

    def register_handler(self, table: str, handler: callable) -> None:
        """Register a handler for CDC events on a specific table."""
        self._handlers.setdefault(table, []).append(handler)

    def parse_event(self, raw_value: bytes | str) -> CDCEvent | None:
        """Parse a Debezium CDC event."""
        try:
            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode("utf-8")
            data = json.loads(raw_value)

            # Handle unwrapped (ExtractNewRecordState) format
            if "__op" in data:
                return CDCEvent(
                    operation=data["__op"],
                    table=data.get("__table", ""),
                    key={},
                    before=None,
                    after=data if data["__op"] != "d" else None,
                    source_ts_ms=data.get("__source_ts_ms", 0),
                    lsn=data.get("__source_lsn"),
                    transaction_id=None,
                )

            # Handle full envelope format
            payload = data.get("payload", data)
            source = payload.get("source", {})
            return CDCEvent(
                operation=payload.get("op", "r"),
                table=source.get("table", ""),
                key=data.get("key", {}),
                before=payload.get("before"),
                after=payload.get("after"),
                source_ts_ms=payload.get("ts_ms", 0),
                lsn=source.get("lsn"),
                transaction_id=source.get("txId"),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse CDC event: {e}")
            return None

    def run(self) -> None:
        """Main consumer loop."""
        try:
            while True:
                msg = self.consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(msg.error())

                event = self.parse_event(msg.value())
                if event is None:
                    continue

                for handler in self._handlers.get(event.table, []):
                    try:
                        handler(event)
                    except Exception as e:
                        logger.error(f"Handler error: {e}", exc_info=True)

                self.consumer.commit(asynchronous=False)
        except KeyboardInterrupt:
            pass
        finally:
            self.consumer.close()
```

```yaml
# --- Docker Compose: Debezium + Kafka Connect stack ---

version: "3.8"
services:
  kafka:
    image: confluentinc/cp-kafka:7.6.0
    ports: ["9092:9092"]
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      CLUSTER_ID: "MkU3OEVBNTcwNTJENDM2Qk"

  schema-registry:
    image: confluentinc/cp-schema-registry:7.6.0
    depends_on: [kafka]
    environment:
      SCHEMA_REGISTRY_HOST_NAME: schema-registry
      SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: kafka:9092

  kafka-connect:
    image: debezium/connect:2.5
    depends_on: [kafka, schema-registry]
    ports: ["8083:8083"]
    environment:
      BOOTSTRAP_SERVERS: kafka:9092
      GROUP_ID: connect-cluster
      CONFIG_STORAGE_TOPIC: connect-configs
      OFFSET_STORAGE_TOPIC: connect-offsets
      STATUS_STORAGE_TOPIC: connect-status
```

| Debezium Setting | Purpose | Recommended Value |
|---|---|---|
| plugin.name | WAL decoder | `pgoutput` (built-in PG 10+) |
| snapshot.mode | Initial data load | `initial` then switch to `no_data` |
| slot.name | Replication slot name | Unique per connector |
| heartbeat.interval.ms | Keep slot alive | 10000 (10 seconds) |
| tombstones.on.delete | Emit null for deletes | `true` (for compacted topics) |
| errors.tolerance | Error handling | `all` + DLQ for production |
| transforms.unwrap | Flatten envelope | `ExtractNewRecordState` |

Key patterns:

1. **pgoutput plugin** -- use PostgreSQL built-in logical decoding, no extensions needed
2. **Publication per connector** -- create explicit publications for table-level control
3. **ExtractNewRecordState** -- flatten Debezium envelope for simpler downstream consumers
4. **Schema Registry** -- use Avro + Schema Registry for schema evolution across CDC events
5. **Heartbeat interval** -- prevent replication slot from being dropped during low traffic
6. **Dead letter queue** -- route unparseable events to DLQ instead of blocking the connector
7. **Monitor replication lag** -- track `pg_wal_lsn_diff` to detect pipeline falling behind'''
    ),
    (
        "data-engineering/cdc-event-processing-pipeline",
        "Show a CDC event processing pipeline that handles ordering, deduplication, schema evolution, and transforms CDC events into domain events.",
        '''CDC event processing: ordering, deduplication, and domain event generation:

```python
# --- CDC event processor with deduplication and change extraction ---

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from collections import defaultdict
import hashlib
import json
import logging

logger = logging.getLogger("cdc.processor")


@dataclass
class ProcessedEvent:
    """A CDC event ready for downstream consumption."""
    event_id: str
    event_type: str         # "order.created", "order.updated", "order.deleted"
    entity_type: str
    entity_id: str
    timestamp: datetime
    data: dict
    previous_data: dict | None
    changes: dict | None
    metadata: dict = field(default_factory=dict)


class CDCEventProcessor:
    """Process raw CDC events into clean domain events."""

    def __init__(self) -> None:
        self._seen_lsns: dict[str, set[int]] = defaultdict(set)
        self._entity_versions: dict[str, int] = {}
        self._transformers: dict[str, Callable] = {}

    def register_transformer(
        self,
        table: str,
        transformer: Callable[[dict, dict | None], dict],
    ) -> None:
        self._transformers[table] = transformer

    def process(self, event: CDCEvent) -> ProcessedEvent | None:
        """Process a CDC event: deduplicate, extract changes, transform."""
        # Step 1: Deduplicate by LSN
        if event.lsn is not None:
            seen = self._seen_lsns[event.table]
            if event.lsn in seen:
                return None
            seen.add(event.lsn)
            # Prune old LSNs
            if len(seen) > 10000:
                sorted_lsns = sorted(seen)
                seen.difference_update(sorted_lsns[:len(sorted_lsns) // 2])

        # Step 2: Extract changes (for updates)
        changes = None
        if event.is_update and event.before and event.after:
            changes = {}
            for key in set(event.before.keys()) | set(event.after.keys()):
                old = event.before.get(key)
                new = event.after.get(key)
                if old != new:
                    changes[key] = {"old": old, "new": new}
            if not changes:
                return None  # No real changes

        # Step 3: Classify event type
        op_map = {"c": "created", "r": "created", "u": "updated", "d": "deleted"}
        event_type = f"{event.table}.{op_map.get(event.operation, 'unknown')}"

        # Step 4: Transform data
        data = event.after or event.before or {}
        transformer = self._transformers.get(event.table)
        if transformer:
            data = transformer(data, event.before)

        # Step 5: Generate deterministic event ID
        content = f"{event.table}:{event.lsn}:{event.operation}:{event.source_ts_ms}"
        event_id = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Step 6: Extract entity ID
        entity_id = str(list(event.key.values())[0]) if event.key else str(data.get("id", "unknown"))

        return ProcessedEvent(
            event_id=event_id,
            event_type=event_type,
            entity_type=event.table,
            entity_id=entity_id,
            timestamp=event.source_timestamp,
            data=data,
            previous_data=event.before,
            changes=changes,
            metadata={
                "source_lsn": event.lsn,
                "source_ts_ms": event.source_ts_ms,
                "operation": event.operation,
            },
        )
```

```python
# --- Domain event transformers and publisher ---

def transform_order(after: dict, before: dict | None) -> dict:
    """Transform raw order CDC data into a clean domain event."""
    return {
        "order_id": after.get("id"),
        "customer_id": after.get("customer_id"),
        "status": after.get("status"),
        "total_amount": after.get("total_amount_cents", 0) / 100.0,
        "currency": after.get("currency", "USD"),
        "items_count": after.get("items_count", 0),
        "shipping_country": after.get("shipping_country"),
        "ordered_at": after.get("created_at"),
        "updated_at": after.get("updated_at"),
    }


def transform_customer(after: dict, before: dict | None) -> dict:
    """Transform raw customer CDC data."""
    return {
        "customer_id": after.get("id"),
        "email": after.get("email"),
        "name": f"{after.get('first_name', '')} {after.get('last_name', '')}".strip(),
        "country": after.get("country_code"),
        "status": after.get("status"),
    }


# --- Event publisher with schema validation ---

from pydantic import BaseModel, Field
from confluent_kafka import Producer


class DomainEventPublisher:
    """Publish processed CDC events as domain events to Kafka."""

    def __init__(
        self,
        producer: Producer,
        topic_prefix: str = "domain",
    ) -> None:
        self.producer = producer
        self.topic_prefix = topic_prefix

    def publish(self, event: ProcessedEvent) -> bool:
        """Publish a domain event with entity_id as key."""
        topic = f"{self.topic_prefix}.{event.entity_type}"

        payload = json.dumps({
            "event_id": event.event_id,
            "event_type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "timestamp": event.timestamp.isoformat(),
            "data": event.data,
            "changes": event.changes,
            "metadata": event.metadata,
        }).encode("utf-8")

        try:
            self.producer.produce(
                topic=topic,
                key=event.entity_id.encode("utf-8"),
                value=payload,
                headers={
                    "event-type": event.event_type.encode(),
                    "entity-id": event.entity_id.encode(),
                },
            )
            self.producer.flush()
            return True
        except Exception as e:
            logger.error(f"Failed to publish: {e}")
            return False


# Wire up
processor = CDCEventProcessor()
processor.register_transformer("orders", transform_order)
processor.register_transformer("customers", transform_customer)
```

```python
# --- Full pipeline: consume, process, publish ---

async def run_cdc_pipeline(
    bootstrap_servers: str = "kafka:9092",
    source_topics: list[str] = None,
    group_id: str = "cdc-processor",
) -> None:
    """Run the full CDC processing pipeline."""
    if source_topics is None:
        source_topics = ["cdc.orders", "cdc.customers", "cdc.payments"]

    consumer = CDCConsumer(
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        topics=source_topics,
    )

    producer = Producer({
        "bootstrap.servers": bootstrap_servers,
        "enable.idempotence": True,
        "acks": "all",
    })

    processor = CDCEventProcessor()
    processor.register_transformer("orders", transform_order)
    processor.register_transformer("customers", transform_customer)

    publisher = DomainEventPublisher(producer, topic_prefix="domain")

    metrics = {"processed": 0, "published": 0, "skipped": 0, "errors": 0}

    def handle_event(event: CDCEvent) -> None:
        processed = processor.process(event)
        metrics["processed"] += 1

        if processed is None:
            metrics["skipped"] += 1
            return

        if publisher.publish(processed):
            metrics["published"] += 1
        else:
            metrics["errors"] += 1

        if metrics["processed"] % 1000 == 0:
            logger.info(f"CDC metrics: {metrics}")

    for table in ["orders", "customers", "payments"]:
        consumer.register_handler(table, handle_event)

    logger.info("Starting CDC pipeline...")
    consumer.run()
```

| Processing Step | Purpose | Implementation |
|---|---|---|
| Deduplication | Skip duplicate CDC events | LSN-based set with bounded cleanup |
| Change extraction | Identify what fields changed | Diff before/after dictionaries |
| No-op detection | Skip updates with no real changes | Return None if changes is empty |
| Domain mapping | Convert CDC ops to business events | `table.created/updated/deleted` naming |
| Data transformation | Clean DB columns to domain fields | Per-table transformer functions |
| Idempotent publishing | Enable safe replay | Deterministic event ID from LSN+table+op |
| Key-based ordering | Per-entity ordering in Kafka | entity_id as Kafka message key |

Key patterns:

1. **LSN-based dedup** -- use Log Sequence Number to detect and skip duplicate events
2. **Change extraction** -- diff before/after to skip no-op updates
3. **Domain transformers** -- per-table functions that clean column names and transform values
4. **Deterministic event IDs** -- derive from LSN + table + op for idempotent downstream processing
5. **Entity key partitioning** -- use entity_id as Kafka key for per-entity ordering
6. **Idempotent producer** -- enable Kafka idempotent producer for exactly-once writes
7. **Metrics logging** -- track processed, published, skipped, and error counts'''
    ),
    (
        "data-engineering/outbox-pattern",
        "Show the transactional outbox pattern for reliable event publishing including database implementation, polling publisher, and Debezium-based relay.",
        '''Transactional outbox pattern for reliable event publishing:

```
Transactional Outbox Pattern:

Application writes business data AND outbox event
in a SINGLE database transaction. A relay process
reads the outbox and publishes to Kafka.

  Application ──▶ Database (single TX)
                   ├── orders table    (business data)
                   └── outbox table    (event to publish)
                          │
                    Relay (poll or CDC)
                          │
                          ▼
                       Kafka topic
```

```python
# --- Outbox table and service implementation ---

from __future__ import annotations
import uuid
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Column, String, DateTime, Text, Boolean,
    BigInteger, Index,
)
from sqlalchemy.orm import DeclarativeBase, Session, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB


class Base(DeclarativeBase):
    pass


class OutboxEvent(Base):
    """Outbox table: events to be published to Kafka."""
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_unpublished", "published", "created_at",
              postgresql_where="published = false"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OrderService:
    """Service using the outbox pattern for reliable events."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_order(
        self,
        customer_id: str,
        items: list[dict],
        total_amount: float,
    ) -> dict:
        """Create order AND outbox event in a single transaction."""
        from sqlalchemy import text

        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # 1. Insert business data
        self.session.execute(
            text("""
                INSERT INTO orders (id, customer_id, total_amount, status, created_at)
                VALUES (:id, :cid, :amount, :status, :created)
            """),
            {"id": order_id, "cid": customer_id, "amount": total_amount,
             "status": "pending", "created": now},
        )

        # 2. Insert outbox event (SAME transaction)
        outbox_event = OutboxEvent(
            aggregate_type="order",
            aggregate_id=order_id,
            event_type="OrderCreated",
            payload={
                "order_id": order_id,
                "customer_id": customer_id,
                "items": items,
                "total_amount": total_amount,
                "status": "pending",
                "created_at": now.isoformat(),
            },
            metadata={"correlation_id": str(uuid.uuid4()), "source": "order-service"},
        )
        self.session.add(outbox_event)

        # 3. Single commit: both succeed or both fail
        self.session.commit()

        return {"id": order_id, "status": "pending"}

    def update_order_status(self, order_id: str, new_status: str) -> None:
        """Update status and publish event atomically."""
        from sqlalchemy import text

        self.session.execute(
            text("UPDATE orders SET status = :s WHERE id = :id"),
            {"s": new_status, "id": order_id},
        )

        outbox_event = OutboxEvent(
            aggregate_type="order",
            aggregate_id=order_id,
            event_type="OrderStatusChanged",
            payload={"order_id": order_id, "new_status": new_status,
                     "changed_at": datetime.now(timezone.utc).isoformat()},
        )
        self.session.add(outbox_event)
        self.session.commit()
```

```python
# --- Polling publisher ---

from confluent_kafka import Producer
import time
import logging

logger = logging.getLogger("outbox.publisher")


class OutboxPollingPublisher:
    """Poll the outbox table and publish events to Kafka."""

    def __init__(
        self,
        session: Session,
        producer: Producer,
        topic_prefix: str = "domain",
        batch_size: int = 100,
        poll_interval: float = 1.0,
    ) -> None:
        self.session = session
        self.producer = producer
        self.topic_prefix = topic_prefix
        self.batch_size = batch_size
        self.poll_interval = poll_interval

    def run(self) -> None:
        """Main polling loop."""
        while True:
            count = self._poll_and_publish()
            if count == 0:
                time.sleep(self.poll_interval)

    def _poll_and_publish(self) -> int:
        """Fetch unpublished events and publish to Kafka."""
        events = (
            self.session.query(OutboxEvent)
            .filter(OutboxEvent.published == False)
            .order_by(OutboxEvent.created_at)
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
            .all()
        )

        if not events:
            return 0

        published = 0
        for event in events:
            topic = f"{self.topic_prefix}.{event.aggregate_type}"

            try:
                self.producer.produce(
                    topic=topic,
                    key=event.aggregate_id.encode("utf-8"),
                    value=json.dumps({
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "aggregate_type": event.aggregate_type,
                        "aggregate_id": event.aggregate_id,
                        "payload": event.payload,
                        "metadata": event.metadata,
                        "created_at": event.created_at.isoformat(),
                    }).encode("utf-8"),
                    headers={"event-type": event.event_type.encode()},
                )
                event.published = True
                event.published_at = datetime.now(timezone.utc)
                published += 1
            except Exception as e:
                logger.error(f"Failed to publish {event.id}: {e}")

        self.producer.flush()
        self.session.commit()
        logger.info(f"Published {published}/{len(events)} events")
        return published
```

```json
// --- Debezium outbox connector (recommended for production) ---

{
  "name": "outbox-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium_repl",
    "database.password": "${file:/secrets/pg-password.txt:password}",
    "database.dbname": "ecommerce",

    "topic.prefix": "outbox",
    "table.include.list": "public.outbox_events",

    "plugin.name": "pgoutput",
    "slot.name": "debezium_outbox",

    "transforms": "outbox",
    "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter",
    "transforms.outbox.table.field.event.id": "id",
    "transforms.outbox.table.field.event.key": "aggregate_id",
    "transforms.outbox.table.field.event.type": "event_type",
    "transforms.outbox.table.field.event.payload": "payload",
    "transforms.outbox.table.fields.additional.placement": "aggregate_type:header,metadata:header",
    "transforms.outbox.route.topic.replacement": "domain.${routedByValue}",
    "transforms.outbox.table.field.event.timestamp": "created_at",

    "tombstones.on.delete": "false",
    "heartbeat.interval.ms": "10000"
  }
}
```

| Outbox Relay Method | Latency | Complexity | At-Least-Once | Ordering |
|---|---|---|---|---|
| Polling publisher | 1-5 seconds | Low | Yes (skip_locked) | By created_at |
| Debezium CDC relay | < 1 second | Medium | Yes (WAL-based) | By WAL order |
| pg_notify + listener | < 100ms | Medium | No (unreliable) | By trigger |
| Background task | Variable | Low | No (task may fail) | No guarantee |

Key patterns:

1. **Single transaction** -- always write business data and outbox event in the same DB transaction
2. **Debezium EventRouter** -- use Debezium built-in outbox routing for lowest latency
3. **skip_locked** -- polling publisher uses `FOR UPDATE SKIP LOCKED` for concurrent publishers
4. **Aggregate key** -- use aggregate_id as Kafka key for per-entity ordering
5. **Idempotent consumers** -- deterministic event_id enables downstream deduplication
6. **Cleanup old events** -- periodically delete published=true events older than N days
7. **Metadata headers** -- pass aggregate_type and correlation_id as Kafka headers'''
    ),
    (
        "data-engineering/cdc-cache-search-sync",
        "Show CDC-based patterns for cache invalidation and search index synchronization using Debezium events to keep Redis and Elasticsearch in sync with PostgreSQL.",
        '''CDC for cache invalidation and search index synchronization:

```python
# --- CDC-based cache invalidation with Redis ---

from __future__ import annotations
import json
import logging
from typing import Callable
from collections import defaultdict

import redis.asyncio as redis

logger = logging.getLogger("cdc.sync")


class CDCCacheInvalidator:
    """Invalidate Redis cache when source data changes via CDC."""

    def __init__(
        self,
        redis_client: redis.Redis,
        cache_prefix: str = "cache",
        ttl_seconds: int = 3600,
    ) -> None:
        self.redis = redis_client
        self.prefix = cache_prefix
        self.ttl = ttl_seconds
        self._strategies: dict[str, str] = {}
        self._related_rules: dict[str, list[tuple[str, Callable]]] = {}

    def register_table(
        self,
        table: str,
        strategy: str = "invalidate",
    ) -> None:
        """
        Register cache strategy for a table.
        Strategies: "invalidate" (delete), "update" (write-through)
        """
        self._strategies[table] = strategy

    def register_related(
        self,
        table: str,
        related_type: str,
        id_extractor: Callable[[dict], str | None],
    ) -> None:
        """Register related caches to invalidate on table change."""
        self._related_rules.setdefault(table, []).append(
            (related_type, id_extractor)
        )

    async def handle_event(self, event: dict) -> None:
        """Process a CDC event and update/invalidate cache."""
        table = event.get("entity_type", "")
        entity_id = event.get("entity_id", "")
        operation = event.get("metadata", {}).get("operation", "")
        data = event.get("data", {})

        strategy = self._strategies.get(table, "invalidate")
        cache_key = f"{self.prefix}:{table}:{entity_id}"

        if strategy == "invalidate" or operation == "d":
            await self.redis.delete(cache_key)
            logger.info(f"Cache invalidated: {cache_key}")
        elif strategy == "update":
            await self.redis.setex(
                cache_key, self.ttl,
                json.dumps(data, default=str),
            )
            logger.info(f"Cache updated: {cache_key}")

        # Invalidate related caches
        for related_type, extractor in self._related_rules.get(table, []):
            related_id = extractor(data)
            if related_id:
                related_key = f"{self.prefix}:{related_type}:{related_id}"
                await self.redis.delete(related_key)
                logger.debug(f"Related cache invalidated: {related_key}")
```

```python
# --- CDC-based Elasticsearch synchronization ---

from elasticsearch import AsyncElasticsearch


class CDCSearchIndexer:
    """Synchronize database changes to Elasticsearch via CDC."""

    def __init__(
        self,
        es_client: AsyncElasticsearch,
        index_prefix: str = "search",
    ) -> None:
        self.es = es_client
        self.index_prefix = index_prefix
        self._configs: dict[str, dict] = {}
        self._transformers: dict[str, Callable] = {}

    def register_index(
        self,
        table: str,
        index_name: str,
        transformer: Callable[[dict], dict],
    ) -> None:
        self._configs[table] = {
            "index": f"{self.index_prefix}-{index_name}",
        }
        self._transformers[table] = transformer

    async def handle_event(self, event: dict) -> None:
        """Process CDC event and update Elasticsearch."""
        table = event.get("entity_type", "")
        entity_id = event.get("entity_id", "")
        operation = event.get("metadata", {}).get("operation", "")
        data = event.get("data", {})

        config = self._configs.get(table)
        if not config:
            return

        index = config["index"]

        if operation == "d":
            try:
                await self.es.delete(index=index, id=entity_id)
                logger.info(f"ES delete: {index}/{entity_id}")
            except Exception:
                pass  # Already deleted
        else:
            transformer = self._transformers.get(table)
            doc = transformer(data) if transformer else data

            await self.es.index(
                index=index,
                id=entity_id,
                document=doc,
                refresh=False,
            )
            logger.info(f"ES index: {index}/{entity_id}")

    async def handle_batch(self, events: list[dict]) -> dict:
        """Bulk process CDC events for Elasticsearch."""
        actions = []

        for event in events:
            table = event.get("entity_type", "")
            entity_id = event.get("entity_id", "")
            operation = event.get("metadata", {}).get("operation", "")
            data = event.get("data", {})

            config = self._configs.get(table)
            if not config:
                continue

            index = config["index"]
            transformer = self._transformers.get(table)

            if operation == "d":
                actions.append({"delete": {"_index": index, "_id": entity_id}})
            else:
                doc = transformer(data) if transformer else data
                actions.append({"index": {"_index": index, "_id": entity_id}})
                actions.append(doc)

        if not actions:
            return {"indexed": 0, "deleted": 0, "errors": 0}

        result = await self.es.bulk(body=actions, refresh=False)

        stats = {"indexed": 0, "deleted": 0, "errors": 0}
        for item in result.get("items", []):
            for op_type, op_result in item.items():
                if op_result.get("error"):
                    stats["errors"] += 1
                elif op_type == "delete":
                    stats["deleted"] += 1
                else:
                    stats["indexed"] += 1
        return stats


# --- Transformer functions ---

def order_search_doc(data: dict) -> dict:
    return {
        "order_id": data.get("order_id"),
        "customer_id": data.get("customer_id"),
        "status": data.get("status"),
        "total_amount": data.get("total_amount"),
        "country": data.get("shipping_country"),
        "ordered_at": data.get("ordered_at"),
    }


def customer_search_doc(data: dict) -> dict:
    return {
        "customer_id": data.get("customer_id"),
        "name": data.get("name"),
        "email": data.get("email"),
        "country": data.get("country"),
    }
```

```python
# --- Combined orchestrator for cache + search sync ---

import asyncio


class CDCSyncOrchestrator:
    """Orchestrate CDC processing for cache and search targets."""

    def __init__(
        self,
        cache: CDCCacheInvalidator,
        search: CDCSearchIndexer,
    ) -> None:
        self.cache = cache
        self.search = search
        self._metrics = defaultdict(int)

    async def process_event(self, event: dict) -> None:
        """Process event through all sync targets in parallel."""
        self._metrics["events_processed"] += 1

        results = await asyncio.gather(
            self.cache.handle_event(event),
            self.search.handle_event(event),
            return_exceptions=True,
        )

        for r in results:
            if isinstance(r, Exception):
                self._metrics["errors"] += 1
                logger.error(f"Sync error: {r}")

    def get_metrics(self) -> dict:
        return dict(self._metrics)


# --- Setup ---

async def setup_sync():
    redis_client = redis.from_url("redis://localhost:6379/0")
    es_client = AsyncElasticsearch(["http://localhost:9200"])

    cache = CDCCacheInvalidator(redis_client, ttl_seconds=3600)
    cache.register_table("orders", strategy="invalidate")
    cache.register_table("customers", strategy="update")
    cache.register_related(
        "orders", "customer_orders",
        lambda d: d.get("customer_id"),
    )

    search = CDCSearchIndexer(es_client)
    search.register_index("orders", "orders", order_search_doc)
    search.register_index("customers", "customers", customer_search_doc)

    return CDCSyncOrchestrator(cache, search)
```

| Sync Target | Strategy | Latency | Consistency |
|---|---|---|---|
| Redis (invalidate) | Delete key on change | < 1s | Eventual (cache miss -> DB) |
| Redis (write-through) | Update key on change | < 1s | Eventual (brief stale) |
| Elasticsearch | Index/delete doc | 1-5s (refresh) | Eventual (refresh interval) |
| Materialized view | Refresh on change | Seconds-min | Eventual |

Key patterns:

1. **Invalidate over update** -- cache invalidation is simpler and safer than write-through
2. **Related cache busting** -- order change invalidates customer's order list cache too
3. **Bulk ES operations** -- batch CDC events for Elasticsearch bulk API throughput
4. **Entity-keyed ordering** -- Kafka key = entity_id ensures per-entity ordering
5. **Async parallel sync** -- process cache and search updates concurrently
6. **Transformer functions** -- decouple DB schema from search document schema
7. **Metrics tracking** -- count events, errors, and lag per sync target'''
    ),
]
