"""
Batch P5 -- Streaming & Real-Time Data Processing
Covers: Apache Flink, CDC with Debezium, ClickHouse real-time analytics,
message queue comparison (Kafka/RabbitMQ/NATS/Pulsar), stream processing patterns.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. Apache Flink Stream Processing ---
    (
        "streaming/flink-event-time-windowing",
        "Explain Apache Flink stream processing in depth including event time versus processing time semantics, watermark generation strategies and their trade-offs, windowing approaches such as tumbling sliding and session windows, exactly-once processing guarantees with checkpointing and barriers, and provide complete Python and Java code examples demonstrating real-world Flink pipelines.",
        '''# Apache Flink Stream Processing: Event Time, Watermarks, and Exactly-Once Semantics

## Why Flink Stands Apart in Stream Processing

Apache Flink was designed from the ground up as a **stream-first** processing engine. Unlike frameworks that bolt streaming onto a batch core (early Spark Streaming with micro-batches), Flink treats every dataset as a potentially unbounded stream. This architectural decision has profound consequences: Flink provides native support for event-time processing, sophisticated watermark handling, and true exactly-once semantics without the latency penalties that micro-batch architectures impose.

Understanding the distinction between **event time** and **processing time** is fundamental because it determines whether your analytics reflect reality or reflect the order in which your infrastructure happened to receive messages. A **common mistake** is defaulting to processing time because it is simpler, only to discover that your hourly aggregations are wrong every time there is a consumer lag spike or a producer backlog flush.

## Event Time vs Processing Time

### Processing Time

Processing time is the wall-clock time on the machine executing the operator. It is the simplest model: events are processed in the order they arrive, and windows close based on system time.

**Pros**: Zero latency overhead, no watermark complexity, deterministic only in ideal conditions.
**Cons**: Results depend on arrival order, which varies with network delays, partition rebalancing, and consumer restarts. Therefore, results are **non-reproducible** -- replaying the same events will produce different window assignments.

### Event Time

Event time is the timestamp embedded in the event itself -- the moment the event actually occurred. Flink uses watermarks to track the progress of event time.

**Pros**: Results are **deterministic and reproducible**. Late events are handled correctly. Window boundaries reflect real-world time.
**Cons**: Requires watermark management. Late events introduce latency (you must wait before closing a window). Watermark generation strategy directly impacts both correctness and latency.

### Ingestion Time

A middle ground: the timestamp is assigned when the event enters the Flink pipeline. This gives partial ordering guarantees without requiring producer-side timestamps, however it still suffers from network jitter between source and Flink ingress.

## Watermark Strategies

Watermarks are the mechanism by which Flink tracks the **progress of event time**. A watermark with timestamp `t` declares: "No events with timestamp less than `t` will arrive after this point." This is a **best practice** assertion, not a guarantee, which is why late data handling exists.

### Bounded Out-of-Orderness

The most common strategy. You declare the maximum expected delay, and Flink generates watermarks at `max_event_time_seen - max_delay`. The trade-off is clear: a larger delay tolerates more out-of-order events but increases end-to-end latency because windows stay open longer.

### Punctuated Watermarks

Watermarks are emitted based on specific events in the stream (for example, a "batch complete" sentinel). This works well when the data source provides natural completion signals, however it fails if those signals are delayed or missing.

### Custom Watermark Strategies

For multi-source pipelines where different partitions have vastly different lag characteristics, you may need per-partition watermark tracking. Flink's `WatermarkStrategy` API supports this through `WatermarkGenerator` implementations.

## Windowing Strategies

### Tumbling Windows

Fixed-size, non-overlapping windows. Every event belongs to exactly one window.

```python
# PyFlink tumbling window aggregation
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.datastream.functions import AggregateFunction
from pyflink.common import Time, WatermarkStrategy, Duration
from pyflink.common.typeinfo import Types
from dataclasses import dataclass
from typing import Tuple


@dataclass
class SensorReading:
    # Represents a single sensor measurement
    sensor_id: str
    temperature: float
    timestamp: int  # epoch millis


class AvgTemperatureAggregate(AggregateFunction):
    # Computes running average temperature per sensor window.
    # The accumulator is a tuple of (sum, count) that merges
    # associatively across parallel subtasks.

    def create_accumulator(self) -> Tuple[float, int]:
        return (0.0, 0)

    def add(self, value: SensorReading, accumulator: Tuple[float, int]) -> Tuple[float, int]:
        return (accumulator[0] + value.temperature, accumulator[1] + 1)

    def get_result(self, accumulator: Tuple[float, int]) -> float:
        total, count = accumulator
        return total / count if count > 0 else 0.0

    def merge(self, a: Tuple[float, int], b: Tuple[float, int]) -> Tuple[float, int]:
        return (a[0] + b[0], a[1] + b[1])


def build_tumbling_pipeline() -> None:
    # Build and execute a tumbling window pipeline that computes
    # 1-minute average temperatures per sensor using event time.
    env = StreamExecutionEnvironment.get_execution_environment()

    # Configure checkpointing for exactly-once guarantees
    env.enable_checkpointing(60000)  # checkpoint every 60 seconds
    env.get_checkpoint_config().set_min_pause_between_checkpoints(30000)

    watermark_strategy = (
        WatermarkStrategy
        .for_bounded_out_of_orderness(Duration.of_seconds(5))
        .with_timestamp_assigner(
            lambda event, _: event.timestamp
        )
    )

    # Source would be Kafka, Kinesis, etc. in production
    sensor_stream = env.from_collection(
        collection=[
            SensorReading("sensor-1", 22.5, 1700000000000),
            SensorReading("sensor-1", 23.1, 1700000030000),
            SensorReading("sensor-2", 18.7, 1700000010000),
        ],
        type_info=Types.PICKLED_BYTE_ARRAY(),
    ).assign_timestamps_and_watermarks(watermark_strategy)

    # Key by sensor, 1-minute tumbling windows, aggregate
    result = (
        sensor_stream
        .key_by(lambda r: r.sensor_id)
        .window(TumblingEventTimeWindows.of(Time.minutes(1)))
        .aggregate(AvgTemperatureAggregate())
    )

    result.print()
    env.execute("Tumbling Window Temperature Averages")
```

### Sliding Windows

Windows of fixed size that advance by a fixed slide interval. Events belong to multiple windows, which is useful for computing rolling averages.

**Pitfall**: If the slide is much smaller than the window size, each event is duplicated across many windows, increasing memory and computation proportionally. A 1-hour window with a 1-second slide means each event is in 3,600 windows.

### Session Windows

Windows defined by a **gap of inactivity**. A new event arriving after the gap timeout starts a new window. This is ideal for user session analytics because session length varies naturally.

**Trade-off**: Session windows cannot be pre-allocated because their boundaries are data-dependent. Flink must maintain state for all active sessions, and merging sessions when late events bridge a gap requires careful state management.

## Exactly-Once with Checkpointing

Flink achieves exactly-once processing through a combination of **distributed snapshots** (Chandy-Lamport algorithm variant) and **checkpoint barriers**.

### How Checkpoint Barriers Work

1. The `JobManager` injects a **barrier** into the source streams
2. Each operator receives the barrier, snapshots its state to durable storage, and forwards the barrier downstream
3. Operators that receive input from multiple streams perform **barrier alignment**: they buffer records from faster streams until the barrier arrives on all inputs
4. Once all operators have acknowledged the checkpoint, it is committed

```java
// Java Flink pipeline with exactly-once Kafka sink
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.windowing.time.Time;
import org.apache.flink.streaming.api.windowing.assigners.TumblingEventTimeWindows;
import org.apache.flink.streaming.api.CheckpointingMode;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.connector.kafka.sink.KafkaSink;
import org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.serialization.SimpleStringSchema;

import java.time.Duration;

public class ExactlyOnceFlinkPipeline {

    // Demonstrates end-to-end exactly-once semantics using
    // Kafka as both source and sink with Flink checkpointing.

    public static void main(String[] args) throws Exception {
        StreamExecutionEnvironment env =
            StreamExecutionEnvironment.getExecutionEnvironment();

        // Enable exactly-once checkpointing
        env.enableCheckpointing(30000L, CheckpointingMode.EXACTLY_ONCE);
        env.getCheckpointConfig().setCheckpointTimeout(60000L);
        env.getCheckpointConfig().setMaxConcurrentCheckpoints(1);

        // Kafka source with bounded out-of-orderness watermarks
        KafkaSource<String> source = KafkaSource.<String>builder()
            .setBootstrapServers("kafka:9092")
            .setTopics("sensor-events")
            .setGroupId("flink-processor")
            .setStartingOffsets(OffsetsInitializer.latest())
            .setValueOnlyDeserializer(new SimpleStringSchema())
            .build();

        WatermarkStrategy<String> watermarks = WatermarkStrategy
            .<String>forBoundedOutOfOrderness(Duration.ofSeconds(10))
            .withIdleness(Duration.ofMinutes(1));

        DataStream<String> events = env
            .fromSource(source, watermarks, "Kafka Source");

        // Process events with tumbling windows
        DataStream<String> aggregated = events
            .keyBy(event -> extractSensorId(event))
            .window(TumblingEventTimeWindows.of(Time.minutes(5)))
            .reduce((a, b) -> mergeReadings(a, b));

        // Exactly-once Kafka sink using two-phase commit
        KafkaSink<String> sink = KafkaSink.<String>builder()
            .setBootstrapServers("kafka:9092")
            .setRecordSerializer(
                KafkaRecordSerializationSchema.builder()
                    .setTopic("aggregated-readings")
                    .setValueSerializationSchema(new SimpleStringSchema())
                    .build()
            )
            .setDeliveryGuarantee(
                org.apache.flink.connector.base.DeliveryGuarantee.EXACTLY_ONCE
            )
            .setTransactionalIdPrefix("flink-agg-")
            .build();

        aggregated.sinkTo(sink);
        env.execute("Exactly-Once Sensor Pipeline");
    }

    private static String extractSensorId(String json) {
        // Parse sensor_id from JSON event
        return json.split("\"sensor_id\":\"")[1].split("\"")[0];
    }

    private static String mergeReadings(String a, String b) {
        // Merge two sensor readings by averaging values
        return a;  // simplified for illustration
    }
}
```

### The Two-Phase Commit Protocol for Sinks

For end-to-end exactly-once semantics (not just within Flink but including external systems), Flink uses a **two-phase commit** protocol for sinks that support transactions (Kafka, some databases):

1. **Pre-commit**: On checkpoint barrier, the sink opens a new transaction and flushes buffered records into the pending transaction
2. **Commit**: When the checkpoint is confirmed complete across all operators, the `JobManager` notifies sinks to commit their transactions

**Pitfall**: The Kafka `transaction.timeout.ms` on the broker must be greater than the Flink checkpoint interval plus any potential delay, otherwise the broker will abort the transaction before Flink commits it.

## Late Data Handling

```python
# Handling late data with allowed lateness and side outputs
from pyflink.datastream import StreamExecutionEnvironment, OutputTag
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.common import Time, WatermarkStrategy, Duration, Types

# Define a side output tag for late events
LATE_DATA_TAG = OutputTag("late-sensor-data", Types.PICKLED_BYTE_ARRAY())


def build_late_data_pipeline() -> None:
    # Pipeline that routes late data to a side output for
    # separate processing instead of silently dropping it.
    # This is a best practice because late data often indicates
    # upstream issues that need monitoring.
    env = StreamExecutionEnvironment.get_execution_environment()
    env.enable_checkpointing(60000)

    watermark_strategy = (
        WatermarkStrategy
        .for_bounded_out_of_orderness(Duration.of_seconds(10))
    )

    # In a production pipeline, configure allowed lateness on the window:
    # - Events within the watermark delay are processed normally
    # - Events within allowed_lateness trigger window re-computation
    # - Events beyond allowed_lateness are routed to side output
    #
    # The trade-off: longer allowed lateness means more state
    # retention and potential duplicate outputs for updated windows.

    sensor_stream = env.from_collection(
        collection=[],  # would be Kafka source in production
        type_info=Types.PICKLED_BYTE_ARRAY(),
    ).assign_timestamps_and_watermarks(watermark_strategy)

    windowed = (
        sensor_stream
        .key_by(lambda r: r.sensor_id)
        .window(TumblingEventTimeWindows.of(Time.minutes(5)))
        .allowed_lateness(Time.minutes(10))
        .side_output_late_data(LATE_DATA_TAG)
        .reduce(lambda a, b: merge_readings(a, b))
    )

    # Main output: on-time and re-fired window results
    windowed.print()

    # Side output: events that arrived too late even for allowed lateness
    late_stream = windowed.get_side_output(LATE_DATA_TAG)
    late_stream.map(lambda e: f"LATE: {e}").print()

    env.execute("Late Data Handling Pipeline")


def merge_readings(a, b):
    # Merge two sensor readings keeping the maximum temperature
    return a if a.temperature > b.temperature else b
```

## State Management and Savepoints

Flink operators maintain **keyed state** (per-key values, lists, maps) and **operator state** (per-parallel-instance). State backends determine where this data lives:

| Backend | Latency | State Size | Checkpointing |
|---------|---------|-----------|---------------|
| **HashMapStateBackend** | Lowest (heap) | Limited by JVM memory | Full snapshot |
| **EmbeddedRocksDBStateBackend** | Higher (disk) | Terabytes | Incremental |

**Best practice**: Use RocksDB for production workloads because it supports incremental checkpointing (only changed state is persisted) and is not limited by heap size. However, it adds serialization overhead for every state access, therefore hot-path state should be minimized.

**Savepoints** are manually triggered, portable snapshots that allow you to stop a job, upgrade code, change parallelism, or migrate between clusters -- something that is impossible with simpler streaming frameworks.

## Summary and Key Takeaways

- **Event time** gives deterministic results regardless of processing delays; processing time is simpler but produces non-reproducible output -- therefore always prefer event time for analytics
- **Watermarks** balance latency against completeness: tighter bounds mean faster results but more late data; the bounded out-of-orderness strategy covers most use cases
- **Tumbling windows** are best for periodic aggregation, **sliding windows** for rolling metrics, and **session windows** for activity-based grouping -- each has distinct memory and computation trade-offs
- **Exactly-once semantics** require both Flink checkpointing (Chandy-Lamport barriers) and sink-side two-phase commit for end-to-end guarantees
- **Late data handling** via allowed lateness and side outputs is a best practice that prevents silent data loss and enables monitoring of upstream ordering issues
- **RocksDB state backend** with incremental checkpointing is the production default because it decouples state size from heap memory and reduces checkpoint I/O
'''
    ),

    # --- 2. Change Data Capture (CDC) with Debezium ---
    (
        "streaming/cdc-debezium-patterns",
        "Explain Change Data Capture architecture with Debezium including log-based CDC versus trigger-based approaches, the Debezium connector architecture with Kafka Connect, the transactional outbox pattern for reliable event publishing, handling schema evolution in CDC pipelines, and provide a complete Python consumer implementation that processes CDC events with idempotent writes.",
        '''# Change Data Capture with Debezium: Reliable Event Streams from Database Changes

## Why CDC Matters for Event-Driven Systems

In a microservices architecture, services own their data and communicate through events. The fundamental challenge is **dual write reliability**: when a service updates its database AND publishes an event, one of those operations can fail, leaving the system in an inconsistent state. Change Data Capture solves this by treating the **database transaction log** as the source of events, because the log is already written atomically as part of the database commit.

This is a **best practice** that eliminates an entire class of distributed consistency bugs. However, implementing CDC correctly requires understanding the trade-offs between different approaches, handling schema changes gracefully, and building idempotent consumers that can tolerate duplicates.

## Log-Based CDC vs Trigger-Based CDC

### Log-Based CDC (Debezium's Approach)

Log-based CDC reads the database's **write-ahead log** (WAL in PostgreSQL, binlog in MySQL, oplog in MongoDB). Every committed transaction is captured as a stream of change events without modifying the database schema or adding query overhead.

**Advantages**:
- **Zero application impact**: No triggers, no additional queries, no schema changes
- **Captures all changes**: Including those made by direct SQL, migrations, and other services
- **Preserves transaction order**: Events appear in commit order with transaction metadata
- **Low latency**: Typically sub-second from commit to event publication

**Disadvantages**:
- Requires database configuration (replication slots in PostgreSQL, binlog format in MySQL)
- Log retention limits the catch-up window (if the connector falls behind past retention, a snapshot is needed)
- Different databases have different log formats, requiring connector-specific logic

### Trigger-Based CDC

Trigger-based CDC creates database triggers on monitored tables that write change records to a shadow table. A poller then reads the shadow table and publishes events.

**Advantages**:
- Works with any database that supports triggers
- No special database configuration or permissions needed
- Can capture computed values that are not in the WAL

**Disadvantages**:
- **Performance impact**: Every write now executes additional trigger logic inside the transaction
- **Schema pollution**: Shadow tables and triggers must be maintained alongside application schema
- **Incomplete capture**: Bulk operations may bypass triggers; DDL changes are not captured
- **Ordering challenges**: Without careful sequence management, events can be reordered

**Therefore**, log-based CDC is strongly preferred for production systems. Trigger-based approaches are acceptable only when log access is not available (some managed database services) or when you need to capture derived values.

## Debezium Architecture

Debezium runs as a set of **Kafka Connect source connectors**. The architecture has these components:

```
+------------+     +------------------+     +-----------+     +------------+
|  Database   | --> | Debezium         | --> |  Kafka    | --> | Consumers  |
|  (WAL/      |    | Connector        |    |  Topics   |    | (services) |
|   binlog)   |    | (Kafka Connect)  |    |           |    |            |
+------------+     +------------------+     +-----------+     +------------+
                         |
                   +------------------+
                   | Schema Registry  |
                   | (Avro/JSON)      |
                   +------------------+
```

### Connector Lifecycle

1. **Snapshot phase**: On first start, the connector takes a consistent snapshot of existing data
2. **Streaming phase**: After the snapshot, the connector switches to streaming changes from the WAL
3. **Offset tracking**: Kafka Connect stores the current WAL position as an offset, enabling restarts without data loss

```python
# Debezium connector configuration for PostgreSQL
# Deployed via Kafka Connect REST API
import json
import requests
from typing import Any, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class DebeziumConnectorConfig:
    # Configuration builder for Debezium PostgreSQL connector.
    # Encapsulates the dozens of configuration options into a
    # type-safe builder that validates settings before deployment.

    name: str = "inventory-connector"
    database_hostname: str = "postgres"
    database_port: int = 5432
    database_user: str = "debezium"
    database_password: str = ""
    database_dbname: str = "inventory"
    database_server_name: str = "dbserver1"
    schema_include_list: str = "public"
    table_include_list: str = "public.orders,public.customers"
    slot_name: str = "debezium_slot"
    publication_name: str = "dbz_publication"
    # Snapshot mode: initial (snapshot + stream), never (stream only),
    # when_needed (snapshot if no offset or offset invalid)
    snapshot_mode: str = "initial"
    # Heartbeat keeps the replication slot alive during low-activity periods
    heartbeat_interval_ms: int = 30000
    # Transforms for topic routing
    transforms: Dict[str, str] = field(default_factory=dict)

    def to_connect_config(self) -> Dict[str, Any]:
        # Convert to Kafka Connect JSON configuration format
        config = {
            "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
            "database.hostname": self.database_hostname,
            "database.port": str(self.database_port),
            "database.user": self.database_user,
            "database.password": self.database_password,
            "database.dbname": self.database_dbname,
            "topic.prefix": self.database_server_name,
            "schema.include.list": self.schema_include_list,
            "table.include.list": self.table_include_list,
            "slot.name": self.slot_name,
            "publication.name": self.publication_name,
            "snapshot.mode": self.snapshot_mode,
            "heartbeat.interval.ms": str(self.heartbeat_interval_ms),
            "plugin.name": "pgoutput",
            "key.converter": "org.apache.kafka.connect.json.JsonConverter",
            "value.converter": "org.apache.kafka.connect.json.JsonConverter",
            "key.converter.schemas.enable": "false",
            "value.converter.schemas.enable": "true",
        }
        for k, v in self.transforms.items():
            config[k] = v
        return config


def deploy_connector(
    connect_url: str,
    config: DebeziumConnectorConfig,
    timeout: int = 30,
) -> Dict[str, Any]:
    # Deploy or update a Debezium connector via Kafka Connect REST API.
    # Returns the connector status after deployment.
    payload = {
        "name": config.name,
        "config": config.to_connect_config(),
    }
    response = requests.put(
        f"{connect_url}/connectors/{config.name}/config",
        json=config.to_connect_config(),
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
```

## The Transactional Outbox Pattern

The outbox pattern solves the dual-write problem by writing events to an **outbox table** within the same database transaction as the business data change. Debezium then captures changes to the outbox table and publishes them to Kafka.

**Why this works**: Because both the business write and the event write are in the same ACID transaction, they either both succeed or both fail. There is no window where one succeeds and the other fails.

```python
# Transactional outbox pattern implementation
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol
import sqlalchemy as sa
from sqlalchemy.orm import Session, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB


class Base(DeclarativeBase):
    pass


class OutboxEvent(Base):
    # The outbox table stores events that need to be published.
    # Debezium watches this table and forwards events to Kafka.
    # After Debezium captures the event, the row can be deleted
    # (or archived) to prevent unbounded table growth.
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    aggregate_type: Mapped[str] = mapped_column(sa.String(255))
    aggregate_id: Mapped[str] = mapped_column(sa.String(255))
    event_type: Mapped[str] = mapped_column(sa.String(255))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    customer_id: Mapped[str] = mapped_column(sa.String(255))
    total_amount: Mapped[float] = mapped_column(sa.Numeric(10, 2))
    status: Mapped[str] = mapped_column(sa.String(50), default="pending")


class OrderService:
    # Service that creates orders and publishes events atomically
    # using the transactional outbox pattern.

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def place_order(
        self, customer_id: str, total_amount: float
    ) -> Order:
        # Create an order and write the event in a single transaction.
        # Because both writes are in the same transaction, there is
        # no possibility of publishing an event for an order that
        # was not actually created (or vice versa).
        with self._session_factory() as session:
            order = Order(
                customer_id=customer_id,
                total_amount=total_amount,
                status="placed",
            )
            session.add(order)

            # Write event to outbox in the SAME transaction
            outbox_event = OutboxEvent(
                aggregate_type="Order",
                aggregate_id=order.id,
                event_type="OrderPlaced",
                payload={
                    "order_id": order.id,
                    "customer_id": customer_id,
                    "total_amount": float(total_amount),
                    "status": "placed",
                },
            )
            session.add(outbox_event)
            session.commit()
            return order
```

## Schema Evolution in CDC Pipelines

Schema evolution is one of the most challenging aspects of CDC, because the database schema changes over time while consumers expect a stable event format. A **common mistake** is deploying a database migration without considering its impact on the CDC pipeline, which can cause deserialization failures in all downstream consumers.

### Strategies for Safe Schema Evolution

1. **Additive-only changes**: Add new nullable columns. Existing consumers ignore unknown fields.
2. **Schema Registry with compatibility checks**: Use Confluent Schema Registry in BACKWARD or FORWARD compatibility mode to enforce that schema changes do not break consumers.
3. **Envelope versioning**: Include a schema version in the event payload so consumers can branch on version.
4. **Transform SMTs**: Use Debezium's Single Message Transforms to reshape events before they reach Kafka, shielding consumers from raw schema changes.

## Idempotent CDC Consumer

```python
# Idempotent CDC event consumer with exactly-once processing
from __future__ import annotations

import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Protocol
from dataclasses import dataclass
from confluent_kafka import Consumer, KafkaError, KafkaException, Message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CDCEvent:
    # Parsed Debezium CDC event with before/after snapshots.
    # The operation field indicates: c=create, u=update, d=delete, r=read(snapshot)
    operation: str       # c, u, d, r
    before: Optional[Dict[str, Any]]
    after: Optional[Dict[str, Any]]
    source_table: str
    source_ts_ms: int
    transaction_id: Optional[str]

    @classmethod
    def from_debezium(cls, raw: Dict[str, Any]) -> CDCEvent:
        # Parse a raw Debezium JSON envelope into a CDCEvent
        payload = raw.get("payload", raw)
        source = payload.get("source", {})
        return cls(
            operation=payload["op"],
            before=payload.get("before"),
            after=payload.get("after"),
            source_table=source.get("table", "unknown"),
            source_ts_ms=payload.get("ts_ms", 0),
            transaction_id=source.get("txId"),
        )

    @property
    def idempotency_key(self) -> str:
        # Generate a deterministic key for deduplication.
        # Using source table + primary key + transaction ID ensures
        # that replayed events produce the same key.
        record = self.after or self.before or {}
        pk = record.get("id", "")
        raw = f"{self.source_table}:{pk}:{self.transaction_id}:{self.source_ts_ms}"
        return hashlib.sha256(raw.encode()).hexdigest()


class IdempotencyStore(Protocol):
    # Protocol for checking and recording processed event IDs.
    # Implementations can use Redis, PostgreSQL, or any durable store.

    def has_been_processed(self, key: str) -> bool: ...
    def mark_processed(self, key: str) -> None: ...


class PostgresIdempotencyStore:
    # PostgreSQL-backed idempotency store using an INSERT ON CONFLICT
    # pattern that is itself idempotent.

    def __init__(self, engine) -> None:
        self._engine = engine
        self._ensure_table()

    def _ensure_table(self) -> None:
        import sqlalchemy as sa
        with self._engine.connect() as conn:
            conn.execute(sa.text("""
                CREATE TABLE IF NOT EXISTS processed_events (
                    idempotency_key VARCHAR(64) PRIMARY KEY,
                    processed_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.commit()

    def has_been_processed(self, key: str) -> bool:
        import sqlalchemy as sa
        with self._engine.connect() as conn:
            result = conn.execute(
                sa.text("SELECT 1 FROM processed_events WHERE idempotency_key = :key"),
                {"key": key},
            )
            return result.fetchone() is not None

    def mark_processed(self, key: str) -> None:
        import sqlalchemy as sa
        with self._engine.connect() as conn:
            conn.execute(
                sa.text("""
                    INSERT INTO processed_events (idempotency_key)
                    VALUES (:key)
                    ON CONFLICT (idempotency_key) DO NOTHING
                """),
                {"key": key},
            )
            conn.commit()


class CDCConsumer:
    # Consumes Debezium CDC events from Kafka with idempotent processing.
    # Handles deserialization, deduplication, and error routing.

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        idempotency_store: IdempotencyStore,
        handlers: Dict[str, Callable[[CDCEvent], None]],
    ) -> None:
        self._consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            # Reduce rebalance disruption
            "max.poll.interval.ms": 300000,
            "session.timeout.ms": 30000,
        })
        self._consumer.subscribe(topics)
        self._store = idempotency_store
        self._handlers = handlers
        self._running = True

    def run(self) -> None:
        # Main consume loop with manual offset commits for at-least-once,
        # combined with idempotency checks for effectively-exactly-once.
        try:
            while self._running:
                msg: Optional[Message] = self._consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(msg.error())

                self._process_message(msg)
                # Commit after successful processing
                self._consumer.commit(message=msg)
        finally:
            self._consumer.close()

    def _process_message(self, msg: Message) -> None:
        try:
            raw = json.loads(msg.value().decode("utf-8"))
            event = CDCEvent.from_debezium(raw)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse CDC event: {e}")
            return

        # Idempotency check: skip if already processed
        if self._store.has_been_processed(event.idempotency_key):
            logger.debug(f"Skipping duplicate event: {event.idempotency_key}")
            return

        handler = self._handlers.get(event.source_table)
        if handler is None:
            logger.warning(f"No handler for table: {event.source_table}")
            return

        handler(event)
        self._store.mark_processed(event.idempotency_key)

    def stop(self) -> None:
        self._running = False
```

## Monitoring and Operational Concerns

### Replication Slot Monitoring

A critical **pitfall** with PostgreSQL CDC is replication slot growth. If the Debezium connector stops consuming, the replication slot retains WAL segments indefinitely, which can fill the disk and crash the database. **Best practice**: Set `max_slot_wal_keep_size` in PostgreSQL 13+ and alert on `pg_replication_slots.active = false`.

### Lag Monitoring

Monitor the difference between `source.ts_ms` (when the change happened in the database) and the current wall-clock time when the consumer processes it. A growing lag indicates either consumer throughput issues or connector problems.

## Summary and Key Takeaways

- **Log-based CDC** (Debezium) is superior to trigger-based because it has zero impact on database write performance, captures all changes including direct SQL, and preserves transaction ordering
- The **transactional outbox pattern** eliminates dual-write inconsistency by writing both business data and events in a single ACID transaction -- Debezium then relays outbox events to Kafka
- **Idempotent consumers** are essential because CDC guarantees at-least-once delivery; use a persistent idempotency store with INSERT ON CONFLICT to deduplicate without race conditions
- **Schema evolution** requires planning: prefer additive-only changes, use Schema Registry compatibility checks, and consider SMTs to decouple database schema from event schema
- **Monitor replication slots** aggressively -- an inactive slot can fill your database disk within hours during high write load; set `max_slot_wal_keep_size` and alert on inactive slots
- The combination of CDC + outbox + idempotent consumers provides **effectively-exactly-once** end-to-end semantics without requiring distributed transactions
'''
    ),

    # --- 3. Real-Time Analytics with ClickHouse ---
    (
        "streaming/clickhouse-realtime-analytics",
        "Explain how to build a real-time analytics system with ClickHouse including materialized views for continuous aggregation, AggregatingMergeTree and ReplacingMergeTree engine selection, table design for time-series and event data, query optimization techniques, and provide a complete Python ingestion pipeline with batch inserts and error handling.",
        '''# Real-Time Analytics with ClickHouse: Materialized Views and Specialized Table Engines

## Why ClickHouse for Real-Time Analytics

ClickHouse is a **columnar OLAP database** that processes billions of rows per second on commodity hardware. Unlike traditional OLAP systems that require pre-aggregation in ETL pipelines, ClickHouse is fast enough to query raw event data in real time while **also** supporting materialized views for pre-aggregated dashboards. This combination means you can serve both exploratory ad-hoc queries and low-latency dashboard panels from the same system.

The critical insight is that ClickHouse achieves this speed through a fundamentally different storage model. Where PostgreSQL stores rows contiguously (great for transactional access), ClickHouse stores each column separately and compresses it with type-specific codecs. A column of timestamps compresses 10-50x because adjacent values are similar, and analytical queries that scan a single column skip all other columns entirely. **Therefore**, ClickHouse reads orders of magnitude less data from disk for typical analytical queries.

However, this design means ClickHouse is **not** a replacement for OLTP databases. It has no row-level UPDATE or DELETE in the traditional sense (mutations are asynchronous background operations), and single-row lookups are slow. Understanding this trade-off is essential before committing to a ClickHouse-based architecture.

## Table Engine Selection

### MergeTree (The Foundation)

All ClickHouse table engines in the MergeTree family share a core mechanism: data is written in sorted **parts**, and background merges combine parts into larger, optimized chunks. The `ORDER BY` clause determines the sort order within parts, which directly controls query performance.

**Best practice**: Choose `ORDER BY` columns that match your most frequent `WHERE` and `GROUP BY` patterns. ClickHouse can skip entire granules (blocks of 8,192 rows by default) when the filter matches the sort key prefix.

### AggregatingMergeTree

AggregatingMergeTree stores **partially aggregated states** instead of raw data. When parts are merged, aggregation states are combined. This is the engine behind efficient materialized views for real-time dashboards.

```sql
-- Raw events table: receives inserts from the ingestion pipeline
CREATE TABLE events_raw (
    event_id UUID DEFAULT generateUUIDv4(),
    event_type LowCardinality(String),
    user_id UInt64,
    page_url String,
    country LowCardinality(String),
    device_type LowCardinality(String),
    revenue Decimal(10, 2),
    event_time DateTime64(3),
    inserted_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_type, user_id, event_time)
TTL event_time + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- Materialized view: automatically aggregates on insert
-- This view intercepts inserts to events_raw and maintains
-- running aggregates in the target AggregatingMergeTree table
CREATE MATERIALIZED VIEW events_hourly_mv
TO events_hourly_agg
AS SELECT
    toStartOfHour(event_time) AS hour,
    event_type,
    country,
    device_type,
    countState() AS event_count,
    uniqState(user_id) AS unique_users,
    sumState(revenue) AS total_revenue,
    avgState(revenue) AS avg_revenue
FROM events_raw
GROUP BY hour, event_type, country, device_type;

-- Target table for the materialized view
CREATE TABLE events_hourly_agg (
    hour DateTime,
    event_type LowCardinality(String),
    country LowCardinality(String),
    device_type LowCardinality(String),
    event_count AggregateFunction(count, UInt64),
    unique_users AggregateFunction(uniq, UInt64),
    total_revenue AggregateFunction(sum, Decimal(10, 2)),
    avg_revenue AggregateFunction(avg, Decimal(10, 2))
) ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, event_type, country, device_type);

-- Querying aggregated data: use the -Merge combinators
SELECT
    hour,
    event_type,
    countMerge(event_count) AS events,
    uniqMerge(unique_users) AS users,
    sumMerge(total_revenue) AS revenue,
    avgMerge(avg_revenue) AS avg_rev
FROM events_hourly_agg
WHERE hour >= now() - INTERVAL 24 HOUR
GROUP BY hour, event_type
ORDER BY hour DESC;
```

A **common mistake** is forgetting to use `-State` functions in the materialized view SELECT and `-Merge` functions when querying. Without `-Merge`, you get the raw binary aggregate state instead of the final value.

### ReplacingMergeTree

ReplacingMergeTree deduplicates rows with the same sort key during background merges. It optionally uses a version column to keep the latest version. This is essential for CDC ingestion where you receive multiple updates for the same entity.

```sql
-- ReplacingMergeTree for maintaining latest state from CDC events
-- The ver column ensures that during merges, only the row with
-- the highest version (latest update) is retained
CREATE TABLE customer_current_state (
    customer_id UInt64,
    email String,
    name String,
    subscription_tier LowCardinality(String),
    lifetime_value Decimal(12, 2),
    updated_at DateTime64(3),
    ver UInt64
) ENGINE = ReplacingMergeTree(ver)
ORDER BY customer_id;

-- IMPORTANT: ReplacingMergeTree only deduplicates during merges,
-- which happen asynchronously. To get deduplicated reads, use FINAL:
SELECT * FROM customer_current_state FINAL
WHERE subscription_tier = 'premium';

-- However, FINAL forces a merge at query time, which is slower.
-- A best practice alternative: use argMax in your queries
SELECT
    customer_id,
    argMax(email, ver) AS email,
    argMax(name, ver) AS name,
    argMax(subscription_tier, ver) AS tier,
    argMax(lifetime_value, ver) AS ltv
FROM customer_current_state
GROUP BY customer_id;
```

**Pitfall**: The `FINAL` keyword forces synchronous deduplication at query time, which can be significantly slower than normal reads. For high-throughput dashboards, prefer the `argMax` pattern or accept eventual consistency between merges.

## Python Ingestion Pipeline

```python
# Production ClickHouse ingestion pipeline with batching and error handling
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from datetime import datetime, timezone

import clickhouse_connect
from clickhouse_connect.driver import Client

logger = logging.getLogger(__name__)


@dataclass
class IngestionConfig:
    # Configuration for the ClickHouse ingestion pipeline
    host: str = "localhost"
    port: int = 8123
    database: str = "analytics"
    username: str = "default"
    password: str = ""
    # Batching parameters: trade-off between latency and throughput.
    # Larger batches = higher throughput but more latency and memory.
    batch_size: int = 10000
    flush_interval_seconds: float = 5.0
    max_retries: int = 3
    retry_backoff_base: float = 1.0
    # Buffer limit prevents OOM if ClickHouse is down
    max_buffer_size: int = 1000000


class ClickHouseIngestionError(Exception):
    # Raised when ingestion fails after all retries
    pass


class BatchIngestionPipeline:
    # Asynchronous batch ingestion pipeline for ClickHouse.
    #
    # Events are buffered in-memory and flushed in batches either
    # when the batch size is reached or the flush interval expires.
    # This batching is critical for ClickHouse performance because
    # ClickHouse creates a new data part per INSERT, and too many
    # small inserts cause "too many parts" errors and degraded
    # merge performance.

    def __init__(self, config: IngestionConfig) -> None:
        self._config = config
        self._client: Optional[Client] = None
        self._buffer: queue.Queue = queue.Queue(
            maxsize=config.max_buffer_size
        )
        self._flush_thread: Optional[threading.Thread] = None
        self._running = False
        self._metrics = IngestionMetrics()

    def start(self) -> None:
        # Initialize the ClickHouse connection and start the flush thread
        self._client = clickhouse_connect.get_client(
            host=self._config.host,
            port=self._config.port,
            database=self._config.database,
            username=self._config.username,
            password=self._config.password,
            # Compress data in transit to reduce network usage
            compress=True,
        )
        self._running = True
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            daemon=True,
            name="clickhouse-flush",
        )
        self._flush_thread.start()
        logger.info("ClickHouse ingestion pipeline started")

    def ingest(self, event: Dict[str, Any]) -> None:
        # Add an event to the buffer. Non-blocking; raises if buffer full.
        try:
            self._buffer.put_nowait(event)
            self._metrics.events_received += 1
        except queue.Full:
            self._metrics.events_dropped += 1
            logger.error("Buffer full -- dropping event. Consider increasing max_buffer_size")

    def _flush_loop(self) -> None:
        # Background thread that periodically flushes the buffer
        while self._running:
            batch = self._drain_batch()
            if batch:
                self._flush_with_retry(batch)
            else:
                time.sleep(0.1)

    def _drain_batch(self) -> List[Dict[str, Any]]:
        # Drain up to batch_size events or wait until flush interval
        batch: List[Dict[str, Any]] = []
        deadline = time.monotonic() + self._config.flush_interval_seconds

        while len(batch) < self._config.batch_size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                event = self._buffer.get(timeout=min(remaining, 0.5))
                batch.append(event)
            except queue.Empty:
                if batch:
                    break
        return batch

    def _flush_with_retry(self, batch: List[Dict[str, Any]]) -> None:
        # Flush a batch to ClickHouse with exponential backoff retry
        for attempt in range(self._config.max_retries):
            try:
                self._do_insert(batch)
                self._metrics.batches_flushed += 1
                self._metrics.events_flushed += len(batch)
                return
            except Exception as e:
                wait = self._config.retry_backoff_base * (2 ** attempt)
                logger.warning(
                    f"Flush attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {wait:.1f}s"
                )
                time.sleep(wait)

        # All retries exhausted
        self._metrics.batches_failed += 1
        self._metrics.events_dropped += len(batch)
        logger.error(f"Failed to flush batch of {len(batch)} events after "
                     f"{self._config.max_retries} attempts")

    def _do_insert(self, batch: List[Dict[str, Any]]) -> None:
        # Perform the actual INSERT using clickhouse-connect's columnar format
        if not batch or not self._client:
            return

        columns = list(batch[0].keys())
        # Transpose row-oriented dicts into columnar format
        # for optimal ClickHouse insertion performance
        col_data = [
            [row.get(col) for row in batch]
            for col in columns
        ]
        self._client.insert(
            table="events_raw",
            data=list(zip(*col_data)),
            column_names=columns,
        )

    def stop(self) -> None:
        # Gracefully stop: flush remaining buffer, then shut down
        self._running = False
        if self._flush_thread:
            self._flush_thread.join(timeout=30)
        # Final flush
        remaining = self._drain_batch()
        if remaining:
            self._flush_with_retry(remaining)
        if self._client:
            self._client.close()
        logger.info(f"Pipeline stopped. Metrics: {self._metrics}")

    @property
    def metrics(self) -> IngestionMetrics:
        return self._metrics


@dataclass
class IngestionMetrics:
    # Tracks pipeline health metrics
    events_received: int = 0
    events_flushed: int = 0
    events_dropped: int = 0
    batches_flushed: int = 0
    batches_failed: int = 0

    @property
    def drop_rate(self) -> float:
        total = self.events_received
        return self.events_dropped / total if total > 0 else 0.0
```

## Query Optimization Techniques

### Column Selection and Projection Pushdown

Because ClickHouse stores columns independently, selecting fewer columns dramatically reduces I/O. A query selecting 3 columns from a 50-column table reads 94% less data. **Therefore**, always avoid `SELECT *` in production queries.

### Partition Pruning

Partitioning by time (monthly or daily) allows ClickHouse to skip entire partitions when the query has a time filter. Combined with the `ORDER BY` key for granule skipping, this provides two levels of data pruning.

### Prewhere Optimization

ClickHouse supports `PREWHERE` clauses that filter rows before reading all columns. For queries that filter on a small column (like `event_type`) and then read large columns (like `page_url`), `PREWHERE` can reduce I/O by reading the filter column first and only fetching other columns for matching rows.

| Optimization | Effect | When to Use |
|-------------|--------|-------------|
| **ORDER BY alignment** | Granule skipping | Always match sort key to common filters |
| **Partition pruning** | Skip entire partitions | Time-range filters on partitioned tables |
| **PREWHERE** | Read filter columns first | Small filter columns + large payload columns |
| **Projection** | Pre-sorted alternative ordering | Queries with different sort key patterns |
| **LowCardinality** | Dictionary encoding | Columns with < 10,000 distinct values |

## Summary and Key Takeaways

- ClickHouse excels at real-time analytics because its **columnar storage** with type-specific compression reads 10-100x less data than row-oriented databases for analytical queries
- **Materialized views** with `AggregatingMergeTree` maintain running aggregates incrementally on insert, enabling sub-second dashboard queries over billions of events without pre-computation ETL
- Use `-State` aggregate functions in materialized view SELECTs and `-Merge` when querying the aggregated table -- this is the most common pitfall for ClickHouse beginners
- **ReplacingMergeTree** handles CDC-style upserts but only deduplicates during asynchronous merges; use `FINAL` or `argMax` patterns for consistent reads, understanding the performance trade-off
- **Batch inserts are mandatory**: ClickHouse creates one data part per INSERT, and too many small inserts trigger "too many parts" errors; buffer events and flush in batches of 10,000+
- Align `ORDER BY` keys with query filter patterns for granule skipping, use `LowCardinality` for low-cardinality string columns, and partition by time for efficient range scans
'''
    ),

    # --- 4. Message Queue Comparison ---
    (
        "streaming/message-queue-comparison",
        "Compare Kafka, RabbitMQ, NATS, and Apache Pulsar as message queue and streaming platforms, covering their architecture differences, partitioning versus routing models, delivery guarantees, throughput and latency characteristics, when to choose each tool, and provide Python producer and consumer code examples for all four systems.",
        '''# Message Queue Comparison: Kafka vs RabbitMQ vs NATS vs Pulsar

## Why Choosing the Right Messaging System Matters

Selecting a messaging system is one of the most consequential infrastructure decisions you will make, because it is extremely difficult to migrate once producers and consumers are deeply integrated. Each system embodies fundamentally different architectural philosophies: Kafka is a **distributed log**, RabbitMQ is a **message broker**, NATS is a **connectivity mesh**, and Pulsar is a **unified messaging and streaming platform**. Understanding these philosophies -- not just feature comparisons -- is essential for making the right choice.

A **common mistake** is choosing a system based on a single benchmark or a "what's trending" article. The right choice depends on your specific requirements: Do you need message replay? Fan-out to many consumers? Sub-millisecond latency? Exactly-once semantics? Each system excels in different areas and has distinct operational costs.

## Architecture Overview

### Apache Kafka: The Distributed Commit Log

Kafka's core abstraction is a **partitioned, replicated, append-only log**. Producers append messages to topic partitions, and consumers track their position (offset) in each partition. Messages are retained for a configurable duration regardless of consumption. This means consumers can replay history, multiple consumer groups can read independently, and the broker does not track per-message acknowledgment state.

**Key properties**: High throughput (millions of messages/second), strong ordering within partitions, consumer-managed offsets, durable retention.

### RabbitMQ: The Smart Broker

RabbitMQ implements the AMQP protocol with a **smart broker, dumb consumer** model. The broker manages message routing through exchanges and bindings, tracks per-message acknowledgments, and supports complex routing topologies (direct, topic, fanout, headers exchanges). Messages are typically consumed once and deleted.

**Key properties**: Flexible routing, per-message acknowledgment, priority queues, dead letter exchanges, built-in management UI.

### NATS: The Connectivity Fabric

NATS is a lightweight, high-performance messaging system designed for **cloud-native connectivity**. Core NATS provides at-most-once pub/sub with no persistence. NATS JetStream adds persistence, exactly-once semantics, and stream processing capabilities while maintaining NATS's simplicity.

**Key properties**: Ultra-low latency, simple subject-based routing, built-in clustering and auto-discovery, tiny operational footprint.

### Apache Pulsar: Unified Messaging and Streaming

Pulsar separates the **serving layer** (brokers) from the **storage layer** (Apache BookKeeper). This separation allows independent scaling of compute and storage, and supports both queue (exclusive/shared subscriptions) and streaming (failover subscriptions) patterns in a single system.

**Key properties**: Multi-tenancy, geo-replication, tiered storage, unified queue+streaming, topic compaction.

## Detailed Comparison

| Feature | **Kafka** | **RabbitMQ** | **NATS JetStream** | **Pulsar** |
|---------|-----------|-------------|-------------------|-----------|
| **Model** | Distributed log | Message broker | Subject-based messaging | Segmented log |
| **Ordering** | Per-partition | Per-queue (with caveats) | Per-subject | Per-partition |
| **Delivery** | At-least-once, exactly-once | At-least-once, at-most-once | At-least-once, exactly-once | At-least-once, exactly-once |
| **Retention** | Time/size-based | Until consumed | Time/size/count-based | Tiered (hot/warm/cold) |
| **Replay** | Yes (offset-based) | No (messages deleted after ack) | Yes (stream-based) | Yes (cursor-based) |
| **Routing** | Topic + partition key | Exchanges + bindings | Subject hierarchy + wildcards | Topic + subscription type |
| **Latency (p99)** | 5-15ms | 1-5ms | <1ms (core), 2-5ms (JetStream) | 5-10ms |
| **Throughput** | Millions/sec | Tens of thousands/sec | Millions/sec | Millions/sec |
| **Ops complexity** | High (ZK/KRaft, brokers) | Medium | Low | High (brokers + BookKeeper) |

## Partitioning vs Routing

This is a fundamental architectural distinction. Kafka and Pulsar use **partitioning**: messages are distributed across numbered partitions, and consumers within a group are assigned partitions. Ordering is guaranteed only within a partition. RabbitMQ and NATS use **routing**: messages are directed to consumers based on content (routing keys, subject hierarchies), with ordering guarantees per-queue or per-subject.

**Trade-off**: Partitioning excels at parallelism and throughput (add partitions to scale), however rebalancing partitions across consumers is disruptive and partition count is hard to change. Routing is more flexible for complex delivery patterns, however scaling beyond a single queue's throughput requires application-level sharding.

## Python Examples for Each System

### Kafka with confluent-kafka

```python
# Kafka producer and consumer with exactly-once semantics
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional
from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
from confluent_kafka.serialization import SerializationContext, MessageField
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class KafkaConfig:
    # Kafka connection and behavior configuration
    bootstrap_servers: str = "localhost:9092"
    topic: str = "events"
    group_id: str = "my-service"
    enable_exactly_once: bool = True


class KafkaEventProducer:
    # Produces events to Kafka with optional exactly-once semantics
    # using idempotent producer and transactional writes.

    def __init__(self, config: KafkaConfig) -> None:
        producer_config: Dict[str, Any] = {
            "bootstrap.servers": config.bootstrap_servers,
            "enable.idempotence": True,
            "acks": "all",
            "retries": 5,
            "max.in.flight.requests.per.connection": 5,
        }
        if config.enable_exactly_once:
            producer_config["transactional.id"] = f"{config.group_id}-producer"
        self._producer = Producer(producer_config)
        if config.enable_exactly_once:
            self._producer.init_transactions()
        self._topic = config.topic

    def send(self, key: str, value: Dict[str, Any]) -> None:
        # Send a single event. The partition is determined by
        # hashing the key, ensuring all events for the same
        # entity go to the same partition (preserving order).
        self._producer.produce(
            topic=self._topic,
            key=key.encode("utf-8"),
            value=json.dumps(value).encode("utf-8"),
            callback=self._delivery_callback,
        )
        self._producer.poll(0)

    def flush(self) -> None:
        self._producer.flush(timeout=10)

    @staticmethod
    def _delivery_callback(err: Optional[KafkaError], msg) -> None:
        if err:
            logger.error(f"Delivery failed: {err}")
        else:
            logger.debug(f"Delivered to {msg.topic()}[{msg.partition()}]")


class KafkaEventConsumer:
    # Consumes events from Kafka with manual commit for at-least-once

    def __init__(
        self, config: KafkaConfig, handler: Callable[[str, Dict], None]
    ) -> None:
        self._consumer = Consumer({
            "bootstrap.servers": config.bootstrap_servers,
            "group.id": config.group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        self._consumer.subscribe([config.topic])
        self._handler = handler

    def run(self) -> None:
        try:
            while True:
                msg = self._consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        raise KafkaException(msg.error())
                    continue
                key = msg.key().decode("utf-8") if msg.key() else ""
                value = json.loads(msg.value().decode("utf-8"))
                self._handler(key, value)
                self._consumer.commit(message=msg)
        finally:
            self._consumer.close()
```

### RabbitMQ with pika

```python
# RabbitMQ producer and consumer with topic exchange routing
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict
from dataclasses import dataclass

import pika
from pika import BlockingConnection, ConnectionParameters
from pika.adapters.blocking_connection import BlockingChannel

logger = logging.getLogger(__name__)


@dataclass
class RabbitConfig:
    # RabbitMQ connection configuration
    host: str = "localhost"
    port: int = 5672
    exchange: str = "events"
    exchange_type: str = "topic"  # topic exchange for flexible routing
    queue: str = "my-service-events"
    routing_key: str = "order.#"  # matches order.created, order.updated, etc.
    prefetch_count: int = 10


class RabbitProducer:
    # Publishes events to a RabbitMQ topic exchange.
    # The routing_key determines which queues receive the message
    # based on their binding patterns.

    def __init__(self, config: RabbitConfig) -> None:
        self._connection = BlockingConnection(
            ConnectionParameters(host=config.host, port=config.port)
        )
        self._channel: BlockingChannel = self._connection.channel()
        self._channel.exchange_declare(
            exchange=config.exchange,
            exchange_type=config.exchange_type,
            durable=True,
        )
        self._exchange = config.exchange

    def publish(self, routing_key: str, message: Dict[str, Any]) -> None:
        self._channel.basic_publish(
            exchange=self._exchange,
            routing_key=routing_key,
            body=json.dumps(message).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent message
                content_type="application/json",
            ),
        )

    def close(self) -> None:
        self._connection.close()


class RabbitConsumer:
    # Consumes events from RabbitMQ with manual acknowledgment.
    # Messages are redelivered if not acked, providing at-least-once.

    def __init__(
        self, config: RabbitConfig, handler: Callable[[str, Dict], None]
    ) -> None:
        self._connection = BlockingConnection(
            ConnectionParameters(host=config.host, port=config.port)
        )
        self._channel: BlockingChannel = self._connection.channel()
        self._channel.exchange_declare(
            exchange=config.exchange,
            exchange_type=config.exchange_type,
            durable=True,
        )
        self._channel.queue_declare(queue=config.queue, durable=True)
        self._channel.queue_bind(
            queue=config.queue,
            exchange=config.exchange,
            routing_key=config.routing_key,
        )
        self._channel.basic_qos(prefetch_count=config.prefetch_count)
        self._handler = handler
        self._queue = config.queue

    def run(self) -> None:
        def on_message(ch, method, properties, body):
            try:
                message = json.loads(body.decode("utf-8"))
                self._handler(method.routing_key, message)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                logger.error(f"Handler failed: {e}")
                # Nack and requeue for retry (or send to DLX after threshold)
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        self._channel.basic_consume(
            queue=self._queue, on_message_callback=on_message
        )
        self._channel.start_consuming()
```

### NATS with nats-py

```python
# NATS JetStream producer and consumer with exactly-once
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict
from dataclasses import dataclass

import nats
from nats.aio.client import Client as NATSClient
from nats.js.api import StreamConfig, ConsumerConfig, AckPolicy, DeliverPolicy

logger = logging.getLogger(__name__)


@dataclass
class NATSConfig:
    # NATS connection and stream configuration
    servers: str = "nats://localhost:4222"
    stream_name: str = "EVENTS"
    subjects: list = None  # e.g., ["events.>"]
    consumer_name: str = "my-service"

    def __post_init__(self):
        if self.subjects is None:
            self.subjects = ["events.>"]


class NATSEventPipeline:
    # NATS JetStream producer and consumer.
    # JetStream adds persistence and exactly-once to NATS's
    # ultra-low-latency core, making it suitable for both
    # fire-and-forget and durable messaging use cases.

    def __init__(self, config: NATSConfig) -> None:
        self._config = config
        self._nc: NATSClient = None
        self._js = None

    async def connect(self) -> None:
        self._nc = await nats.connect(self._config.servers)
        self._js = self._nc.jetstream()
        # Create or update the stream
        await self._js.add_stream(
            StreamConfig(
                name=self._config.stream_name,
                subjects=self._config.subjects,
                retention="limits",
                max_bytes=1_073_741_824,  # 1GB
                max_age=86400_000_000_000,  # 24 hours in nanoseconds
                storage="file",
                num_replicas=3,
                # Enable deduplication window for exactly-once publishing
                duplicate_window=120_000_000_000,  # 2 minutes
            )
        )

    async def publish(self, subject: str, data: Dict[str, Any]) -> None:
        # Publish with a message ID for deduplication.
        # NATS JetStream uses the Nats-Msg-Id header to
        # deduplicate within the duplicate_window.
        msg_id = data.get("event_id", "")
        await self._js.publish(
            subject,
            json.dumps(data).encode("utf-8"),
            headers={"Nats-Msg-Id": msg_id},
        )

    async def subscribe(
        self, handler: Callable[[str, Dict], None]
    ) -> None:
        # Pull-based subscription with manual ack
        sub = await self._js.pull_subscribe(
            subject=self._config.subjects[0],
            durable=self._config.consumer_name,
            config=ConsumerConfig(
                ack_policy=AckPolicy.EXPLICIT,
                deliver_policy=DeliverPolicy.ALL,
                max_deliver=3,
            ),
        )
        while True:
            try:
                msgs = await sub.fetch(batch=100, timeout=5)
                for msg in msgs:
                    try:
                        data = json.loads(msg.data.decode("utf-8"))
                        handler(msg.subject, data)
                        await msg.ack()
                    except Exception as e:
                        logger.error(f"Handler error: {e}")
                        await msg.nak()
            except nats.errors.TimeoutError:
                continue

    async def close(self) -> None:
        if self._nc:
            await self._nc.drain()
```

### Apache Pulsar with pulsar-client

```python
# Apache Pulsar producer and consumer with schema and subscriptions
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict
from dataclasses import dataclass

import pulsar
from pulsar import Client, Producer as PulsarProducer
from pulsar import Consumer as PulsarConsumer, ConsumerType

logger = logging.getLogger(__name__)


@dataclass
class PulsarConfig:
    # Pulsar connection configuration
    service_url: str = "pulsar://localhost:6650"
    topic: str = "persistent://public/default/events"
    subscription: str = "my-service-sub"
    # Subscription type determines consumption model:
    # Exclusive: only one consumer (streaming)
    # Shared: round-robin across consumers (queue)
    # Key_Shared: partition by key (ordered per key)
    # Failover: active-standby (HA streaming)
    subscription_type: ConsumerType = ConsumerType.KeyShared


class PulsarEventProducer:
    # Pulsar producer with batching and key-based ordering.
    # Pulsar's Key_Shared subscription type provides the same
    # per-key ordering as Kafka partitions without requiring
    # a fixed partition count.

    def __init__(self, config: PulsarConfig) -> None:
        self._client = Client(config.service_url)
        self._producer: PulsarProducer = self._client.create_producer(
            topic=config.topic,
            batching_enabled=True,
            batching_max_publish_delay_ms=10,
            batching_max_messages=1000,
        )

    def send(self, key: str, value: Dict[str, Any]) -> None:
        # Send with a partition key for ordering guarantees.
        # Pulsar hashes the key to determine the consumer
        # in Key_Shared subscriptions.
        self._producer.send(
            content=json.dumps(value).encode("utf-8"),
            partition_key=key,
        )

    def close(self) -> None:
        self._producer.close()
        self._client.close()


class PulsarEventConsumer:
    # Pulsar consumer with configurable subscription type

    def __init__(
        self,
        config: PulsarConfig,
        handler: Callable[[str, Dict], None],
    ) -> None:
        self._client = Client(config.service_url)
        self._consumer: PulsarConsumer = self._client.subscribe(
            topic=config.topic,
            subscription_name=config.subscription,
            consumer_type=config.subscription_type,
            negative_ack_redelivery_delay_ms=1000,
        )
        self._handler = handler

    def run(self) -> None:
        while True:
            msg = self._consumer.receive(timeout_millis=5000)
            if msg is None:
                continue
            try:
                key = msg.partition_key() or ""
                value = json.loads(msg.data().decode("utf-8"))
                self._handler(key, value)
                self._consumer.acknowledge(msg)
            except Exception as e:
                logger.error(f"Handler failed: {e}")
                self._consumer.negative_acknowledge(msg)
```

## Decision Framework: When to Choose Each

### Choose **Kafka** when:
- You need **event replay** and long-term retention (event sourcing, audit logs)
- Throughput is the primary concern (millions of messages/second)
- You need the mature ecosystem (Kafka Connect, Kafka Streams, Schema Registry)
- Your team can handle the operational complexity (ZooKeeper/KRaft, broker tuning)

### Choose **RabbitMQ** when:
- You need **complex routing** (topic patterns, headers-based routing, priority queues)
- Request-reply (RPC) patterns are common
- You want a mature, well-understood broker with excellent management tooling
- Message replay is not required (consume-and-delete model)

### Choose **NATS** when:
- **Operational simplicity** is paramount (single binary, zero external dependencies)
- You need ultra-low latency (<1ms for core NATS)
- The system is primarily request-reply or pub-sub with moderate durability needs
- You are building a cloud-native microservices mesh

### Choose **Pulsar** when:
- You need **both queue and streaming** semantics in one system
- **Multi-tenancy** and **geo-replication** are requirements
- You need **tiered storage** (automatically offload old data to S3/GCS)
- You want to avoid Kafka's tight coupling of serving and storage

## Summary and Key Takeaways

- **Kafka** is a distributed log optimized for high-throughput ordered streaming with replay; it excels at event sourcing and data pipelines but has high operational complexity
- **RabbitMQ** is a smart broker with flexible routing (exchanges, bindings, priority queues); it is the best choice for task distribution and complex routing patterns where replay is unnecessary
- **NATS** provides the lowest latency and simplest operations; JetStream adds durability and exactly-once semantics while maintaining the lightweight footprint that makes it ideal for edge and IoT scenarios
- **Pulsar** uniquely separates compute and storage, enabling independent scaling and tiered storage; choose it when you need both queue and streaming patterns with multi-tenancy
- The **partitioning vs routing** distinction is fundamental: Kafka/Pulsar partition for throughput, RabbitMQ/NATS route for flexibility -- this trade-off shapes every aspect of your consumer architecture
- **No system is universally best**: evaluate against your specific requirements for replay, latency, routing complexity, operational capacity, and scaling patterns before committing
'''
    ),

    # --- 5. Stream Processing Patterns ---
    (
        "streaming/stream-processing-patterns",
        "Explain essential stream processing patterns including windowed aggregation with tumbling and sliding windows, complex event processing for pattern detection, exactly-once semantics implementation strategies, late data and out-of-order event handling, and provide complete Python implementations with a lightweight stream processing framework demonstrating each pattern.",
        '''# Stream Processing Patterns: Windowed Aggregation, CEP, Exactly-Once, and Late Data Handling

## Why Patterns Matter More Than Frameworks

Stream processing frameworks come and go -- Storm, Samza, early Spark Streaming have all faded in relevance -- but the **patterns** they implement are timeless. Understanding windowed aggregation, complex event processing, exactly-once semantics, and late data handling at the pattern level means you can implement them in any framework (Flink, Kafka Streams, custom Python) and evaluate new tools based on how well they support these fundamental abstractions.

A **common mistake** is learning a specific API (like Flink's `WindowedStream`) without understanding the underlying pattern. When the framework changes or you need a custom solution, that API knowledge becomes useless. The patterns in this guide apply regardless of your technology stack.

## Pattern 1: Windowed Aggregation

Windowed aggregation groups unbounded stream events into finite buckets (windows) and computes aggregate functions over each bucket. This is the most fundamental stream processing pattern because raw event streams are too granular for most analytics and alerting use cases.

### Tumbling Windows

Non-overlapping, fixed-duration windows. Every event belongs to exactly one window. Best for periodic reporting (hourly counts, daily summaries).

### Sliding Windows

Fixed-duration windows that advance by a configurable slide interval. Events belong to multiple windows. Best for rolling metrics (5-minute moving average updated every 30 seconds).

### Session Windows

Variable-duration windows bounded by a **gap of inactivity**. Best for user session analytics where session length varies.

```python
# Lightweight windowed aggregation framework
from __future__ import annotations

import time
import threading
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, Generic, Iterator, List,
    Optional, Protocol, Tuple, TypeVar,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")
K = TypeVar("K")
R = TypeVar("R")


@dataclass(frozen=True)
class StreamEvent(Generic[T]):
    # A timestamped event in the stream.
    # event_time is the actual time the event occurred (not processing time).
    key: str
    value: T
    event_time: float  # epoch seconds


@dataclass
class WindowBounds:
    # Defines the time range of a window [start, end)
    start: float
    end: float

    def contains(self, timestamp: float) -> bool:
        return self.start <= timestamp < self.end

    def __hash__(self) -> int:
        return hash((self.start, self.end))


class WindowAssigner(ABC):
    # Determines which windows an event belongs to.
    # Different assigners implement different windowing strategies.

    @abstractmethod
    def assign_windows(self, timestamp: float) -> List[WindowBounds]:
        ...


class TumblingWindowAssigner(WindowAssigner):
    # Assigns each event to exactly one non-overlapping window.
    # Window boundaries align to epoch (e.g., minute boundaries).

    def __init__(self, size_seconds: float) -> None:
        self._size = size_seconds

    def assign_windows(self, timestamp: float) -> List[WindowBounds]:
        start = (timestamp // self._size) * self._size
        return [WindowBounds(start=start, end=start + self._size)]


class SlidingWindowAssigner(WindowAssigner):
    # Assigns events to multiple overlapping windows.
    # Each event belongs to (size / slide) windows.

    def __init__(self, size_seconds: float, slide_seconds: float) -> None:
        self._size = size_seconds
        self._slide = slide_seconds

    def assign_windows(self, timestamp: float) -> List[WindowBounds]:
        # Find all windows that contain this timestamp
        windows = []
        # The earliest window that could contain this timestamp
        first_start = (timestamp // self._slide) * self._slide - self._size + self._slide
        start = first_start
        while start <= timestamp:
            end = start + self._size
            if start <= timestamp < end:
                windows.append(WindowBounds(start=start, end=end))
            start += self._slide
        return windows


class SessionWindowAssigner(WindowAssigner):
    # Session windows are special: they cannot be pre-assigned because
    # their boundaries depend on the full sequence of events per key.
    # This assigner creates initial single-event windows that are
    # later merged by the SessionWindowMerger.

    def __init__(self, gap_seconds: float) -> None:
        self._gap = gap_seconds

    def assign_windows(self, timestamp: float) -> List[WindowBounds]:
        return [WindowBounds(start=timestamp, end=timestamp + self._gap)]


class AggregateFunction(ABC, Generic[T, R]):
    # Defines how to accumulate stream events into an aggregate result.
    # Must be associative and commutative for correct parallel execution.

    @abstractmethod
    def create_accumulator(self) -> Any:
        ...

    @abstractmethod
    def add(self, value: T, accumulator: Any) -> Any:
        ...

    @abstractmethod
    def get_result(self, accumulator: Any) -> R:
        ...

    @abstractmethod
    def merge(self, acc_a: Any, acc_b: Any) -> Any:
        ...


class CountAggregate(AggregateFunction[Any, int]):
    # Counts events in a window

    def create_accumulator(self) -> int:
        return 0

    def add(self, value: Any, accumulator: int) -> int:
        return accumulator + 1

    def get_result(self, accumulator: int) -> int:
        return accumulator

    def merge(self, acc_a: int, acc_b: int) -> int:
        return acc_a + acc_b


class SumAggregate(AggregateFunction[float, float]):
    # Sums numeric values in a window

    def create_accumulator(self) -> float:
        return 0.0

    def add(self, value: float, accumulator: float) -> float:
        return accumulator + value

    def get_result(self, accumulator: float) -> float:
        return accumulator

    def merge(self, acc_a: float, acc_b: float) -> float:
        return acc_a + acc_b


class WindowedAggregator(Generic[T, R]):
    # Core windowed aggregation engine.
    # Maintains per-key, per-window accumulators and fires results
    # when watermarks advance past window boundaries.
    #
    # The trade-off in watermark delay directly impacts this:
    # - Tight watermarks: fast results but more late events
    # - Loose watermarks: complete results but higher latency

    def __init__(
        self,
        assigner: WindowAssigner,
        aggregate_fn: AggregateFunction[T, R],
        allowed_lateness: float = 0.0,
        on_result: Optional[Callable[[str, WindowBounds, R], None]] = None,
    ) -> None:
        self._assigner = assigner
        self._aggregate_fn = aggregate_fn
        self._allowed_lateness = allowed_lateness
        self._on_result = on_result or (lambda k, w, r: None)
        # state: key -> window -> accumulator
        self._state: Dict[str, Dict[WindowBounds, Any]] = defaultdict(dict)
        self._watermark: float = 0.0
        self._fired_windows: set = set()

    def process(self, event: StreamEvent[T]) -> None:
        # Process a single event: assign to windows and update accumulators
        windows = self._assigner.assign_windows(event.event_time)
        for window in windows:
            state_key = (event.key, window)
            # Check if this is late data beyond allowed lateness
            if window.end + self._allowed_lateness < self._watermark:
                logger.debug(f"Dropping late event for window {window}")
                continue

            key_state = self._state[event.key]
            if window not in key_state:
                key_state[window] = self._aggregate_fn.create_accumulator()
            key_state[window] = self._aggregate_fn.add(
                event.value, key_state[window]
            )

    def advance_watermark(self, new_watermark: float) -> List[Tuple[str, WindowBounds, R]]:
        # Advance the watermark and fire all windows whose end time
        # is at or before the new watermark.
        results = []
        self._watermark = new_watermark

        for key in list(self._state.keys()):
            key_state = self._state[key]
            for window in list(key_state.keys()):
                if window.end <= new_watermark:
                    state_id = (key, window)
                    if state_id not in self._fired_windows:
                        result = self._aggregate_fn.get_result(key_state[window])
                        results.append((key, window, result))
                        self._on_result(key, window, result)
                        self._fired_windows.add(state_id)

                    # Clean up windows past allowed lateness
                    if window.end + self._allowed_lateness < new_watermark:
                        del key_state[window]

            if not key_state:
                del self._state[key]

        return results
```

## Pattern 2: Complex Event Processing (CEP)

Complex Event Processing detects **patterns across sequences of events**. Unlike simple windowed aggregation that applies a function to all events in a window, CEP matches specific ordered sequences: "event A followed by event B within 5 minutes, but only if event C did not occur in between."

CEP is essential for fraud detection, intrusion detection, SLA monitoring, and business process automation. The challenge is expressing patterns declaratively while maintaining performance over high-throughput streams.

```python
# Complex Event Processing engine with pattern matching
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Sequence


class PatternQuantifier(Enum):
    # How many times a pattern element must match
    ONCE = auto()           # exactly once
    ONE_OR_MORE = auto()    # one or more (greedy)
    OPTIONAL = auto()       # zero or one


@dataclass
class PatternElement:
    # A single element in a CEP pattern.
    # The condition is a predicate that determines whether
    # an event matches this element.
    name: str
    condition: Callable[[Dict[str, Any]], bool]
    quantifier: PatternQuantifier = PatternQuantifier.ONCE
    # Within constraint: max time between this and previous element
    within_seconds: Optional[float] = None


@dataclass
class PatternMatch:
    # A complete pattern match with all matched events
    pattern_name: str
    events: Dict[str, List[Dict[str, Any]]]
    match_time: float = field(default_factory=time.time)


class Pattern:
    # Fluent builder for CEP patterns.
    # Patterns are sequences of elements with conditions,
    # quantifiers, and time constraints.

    def __init__(self, name: str) -> None:
        self._name = name
        self._elements: List[PatternElement] = []

    def begin(
        self, name: str, condition: Callable[[Dict], bool]
    ) -> Pattern:
        # Start the pattern with a required first element
        self._elements.append(PatternElement(
            name=name, condition=condition
        ))
        return self

    def followed_by(
        self,
        name: str,
        condition: Callable[[Dict], bool],
        within_seconds: Optional[float] = None,
    ) -> Pattern:
        # Add a strict sequence element (must be next matching event)
        self._elements.append(PatternElement(
            name=name,
            condition=condition,
            within_seconds=within_seconds,
        ))
        return self

    def followed_by_any(
        self,
        name: str,
        condition: Callable[[Dict], bool],
        within_seconds: Optional[float] = None,
    ) -> Pattern:
        # Add a relaxed sequence element (non-matching events allowed between)
        self._elements.append(PatternElement(
            name=name,
            condition=condition,
            quantifier=PatternQuantifier.ONE_OR_MORE,
            within_seconds=within_seconds,
        ))
        return self

    def optional(
        self, name: str, condition: Callable[[Dict], bool]
    ) -> Pattern:
        # Add an optional element
        self._elements.append(PatternElement(
            name=name,
            condition=condition,
            quantifier=PatternQuantifier.OPTIONAL,
        ))
        return self

    @property
    def elements(self) -> List[PatternElement]:
        return self._elements

    @property
    def name(self) -> str:
        return self._name


class NFAState:
    # NFA (Non-deterministic Finite Automaton) state for pattern matching.
    # Each partial match is tracked as an NFA state with its current
    # position in the pattern and the events matched so far.

    def __init__(
        self,
        pattern: Pattern,
        position: int = 0,
        matched_events: Optional[Dict[str, List[Dict]]] = None,
        start_time: Optional[float] = None,
    ) -> None:
        self.pattern = pattern
        self.position = position
        self.matched_events = matched_events or {}
        self.start_time = start_time

    def is_complete(self) -> bool:
        # Check if all required elements have been matched
        required = sum(
            1 for e in self.pattern.elements
            if e.quantifier != PatternQuantifier.OPTIONAL
        )
        matched_required = sum(
            1 for e in self.pattern.elements[:self.position]
            if e.quantifier != PatternQuantifier.OPTIONAL
        )
        return self.position >= len(self.pattern.elements)

    def clone(self) -> NFAState:
        return NFAState(
            pattern=self.pattern,
            position=self.position,
            matched_events={k: list(v) for k, v in self.matched_events.items()},
            start_time=self.start_time,
        )


class CEPEngine:
    # Complex Event Processing engine using NFA-based pattern matching.
    #
    # For each registered pattern, the engine maintains a set of
    # partial matches (NFA states). When a new event arrives, each
    # partial match is advanced if the event satisfies the next
    # element's condition. Completed matches are emitted.
    #
    # This approach handles multiple concurrent partial matches
    # and supports time constraints between pattern elements.

    def __init__(self) -> None:
        self._patterns: List[Pattern] = []
        self._active_states: List[NFAState] = []
        self._match_callbacks: Dict[str, Callable[[PatternMatch], None]] = {}

    def register_pattern(
        self,
        pattern: Pattern,
        callback: Callable[[PatternMatch], None],
    ) -> None:
        self._patterns.append(pattern)
        self._match_callbacks[pattern.name] = callback

    def process_event(self, event: Dict[str, Any]) -> List[PatternMatch]:
        # Process a single event against all registered patterns.
        # Returns any completed pattern matches.
        event_time = event.get("timestamp", time.time())
        matches: List[PatternMatch] = []
        next_states: List[NFAState] = []

        # Try to start new pattern matches
        for pattern in self._patterns:
            if pattern.elements and pattern.elements[0].condition(event):
                state = NFAState(
                    pattern=pattern,
                    position=1,
                    matched_events={pattern.elements[0].name: [event]},
                    start_time=event_time,
                )
                if state.is_complete():
                    match = PatternMatch(
                        pattern_name=pattern.name,
                        events=state.matched_events,
                    )
                    matches.append(match)
                    self._match_callbacks[pattern.name](match)
                else:
                    next_states.append(state)

        # Try to advance existing partial matches
        for state in self._active_states:
            if state.position >= len(state.pattern.elements):
                continue

            current_element = state.pattern.elements[state.position]

            # Check time constraint
            if current_element.within_seconds is not None:
                elapsed = event_time - state.start_time
                if elapsed > current_element.within_seconds:
                    continue  # timed out, discard this partial match

            if current_element.condition(event):
                # Event matches: advance the NFA
                advanced = state.clone()
                elem_name = current_element.name
                if elem_name not in advanced.matched_events:
                    advanced.matched_events[elem_name] = []
                advanced.matched_events[elem_name].append(event)
                advanced.position += 1

                if advanced.is_complete():
                    match = PatternMatch(
                        pattern_name=advanced.pattern.name,
                        events=advanced.matched_events,
                    )
                    matches.append(match)
                    self._match_callbacks[advanced.pattern.name](match)
                else:
                    next_states.append(advanced)

                # For ONE_OR_MORE, keep the current state alive too
                if current_element.quantifier == PatternQuantifier.ONE_OR_MORE:
                    next_states.append(state)
            else:
                # Event does not match: keep state alive for relaxed sequences
                next_states.append(state)

        self._active_states = next_states
        return matches


# Example: Fraud detection pattern
def build_fraud_detection_pattern() -> Pattern:
    # Detect: large withdrawal followed by multiple small transfers
    # within 10 minutes -- a common money laundering pattern.
    return (
        Pattern("potential_fraud")
        .begin(
            "large_withdrawal",
            lambda e: e.get("type") == "withdrawal" and e.get("amount", 0) > 10000,
        )
        .followed_by(
            "rapid_transfers",
            lambda e: e.get("type") == "transfer" and e.get("amount", 0) < 1000,
            within_seconds=600,  # 10 minutes
        )
        .followed_by(
            "international_transfer",
            lambda e: e.get("type") == "transfer" and e.get("country") != "US",
            within_seconds=600,
        )
    )
```

## Pattern 3: Exactly-Once Semantics

Exactly-once is the most misunderstood guarantee in stream processing. It does not mean each event is processed exactly once by the CPU -- it means the **effect** of processing each event is reflected exactly once in the output. The implementation strategy depends on the scope of the guarantee.

### Three Levels of Exactly-Once

1. **Within the processor**: Checkpointing + replay ensures internal state reflects each event once (Flink's approach)
2. **End-to-end with transactional sinks**: Two-phase commit ensures both state and output are consistent (Kafka transactions)
3. **Effective exactly-once with idempotency**: At-least-once delivery + idempotent writes = same final result (most practical approach)

**Best practice**: Level 3 (idempotent writes) is the most widely applicable because it works with any sink, not just transactional ones. However, it requires careful design of the idempotency key to cover all edge cases.

```python
# Exactly-once processing with checkpointing and idempotent writes
from __future__ import annotations

import json
import hashlib
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, Optional, TypeVar

S = TypeVar("S")  # State type


@dataclass
class Checkpoint(Generic[S]):
    # A snapshot of processor state at a specific point in the input stream.
    # Includes both the application state and the input offset so that
    # recovery replays from the exact right position.
    checkpoint_id: int
    state: S
    input_offset: int
    timestamp: float


class CheckpointStore(ABC):
    # Durable storage for checkpoints. Must survive process crashes.

    @abstractmethod
    def save(self, checkpoint: Checkpoint) -> None:
        ...

    @abstractmethod
    def load_latest(self) -> Optional[Checkpoint]:
        ...


class FileCheckpointStore(CheckpointStore):
    # File-based checkpoint store for single-process deployments.
    # In production, use a distributed store (S3, HDFS, etc.).

    def __init__(self, path: str) -> None:
        self._path = path

    def save(self, checkpoint: Checkpoint) -> None:
        import time
        data = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "state": checkpoint.state,
            "input_offset": checkpoint.input_offset,
            "timestamp": checkpoint.timestamp,
        }
        with open(self._path, "w") as f:
            json.dump(data, f)

    def load_latest(self) -> Optional[Checkpoint]:
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
                return Checkpoint(**data)
        except FileNotFoundError:
            return None


class ExactlyOnceProcessor(Generic[S]):
    # Stream processor with exactly-once semantics via checkpointing.
    #
    # The algorithm:
    # 1. On startup, load the latest checkpoint (state + offset)
    # 2. Resume reading input from the checkpointed offset
    # 3. Process events, updating internal state
    # 4. Periodically snapshot state + current offset as a checkpoint
    # 5. On crash recovery, reload checkpoint and replay from offset
    #
    # Because we replay from the checkpointed offset, some events
    # may be processed twice. Therefore, the output sink MUST be
    # idempotent to achieve end-to-end exactly-once.

    def __init__(
        self,
        checkpoint_store: CheckpointStore,
        initial_state: S,
        checkpoint_interval: int = 1000,  # checkpoint every N events
    ) -> None:
        self._store = checkpoint_store
        self._state = initial_state
        self._checkpoint_interval = checkpoint_interval
        self._current_offset = 0
        self._events_since_checkpoint = 0
        self._checkpoint_id = 0
        self._lock = threading.Lock()

        # Attempt recovery from existing checkpoint
        self._recover()

    def _recover(self) -> None:
        checkpoint = self._store.load_latest()
        if checkpoint:
            self._state = checkpoint.state
            self._current_offset = checkpoint.input_offset
            self._checkpoint_id = checkpoint.checkpoint_id
            logger.info(
                f"Recovered from checkpoint {checkpoint.checkpoint_id} "
                f"at offset {checkpoint.input_offset}"
            )

    def process(
        self,
        event: Dict[str, Any],
        offset: int,
        state_updater: Callable[[S, Dict[str, Any]], S],
    ) -> S:
        # Process a single event and update state.
        # The state_updater must be a pure function for deterministic replay.
        with self._lock:
            # Skip events before our checkpoint offset (replay dedup)
            if offset <= self._current_offset:
                return self._state

            self._state = state_updater(self._state, event)
            self._current_offset = offset
            self._events_since_checkpoint += 1

            if self._events_since_checkpoint >= self._checkpoint_interval:
                self._create_checkpoint()

            return self._state

    def _create_checkpoint(self) -> None:
        import time as _time
        self._checkpoint_id += 1
        checkpoint = Checkpoint(
            checkpoint_id=self._checkpoint_id,
            state=self._state,
            input_offset=self._current_offset,
            timestamp=_time.time(),
        )
        self._store.save(checkpoint)
        self._events_since_checkpoint = 0
        logger.debug(f"Checkpoint {self._checkpoint_id} at offset {self._current_offset}")

    @property
    def state(self) -> S:
        return self._state
```

## Pattern 4: Late Data Handling

Late data is inevitable in distributed systems. Network partitions, producer batching, and clock skew all cause events to arrive after the watermark has advanced past their event time. The question is not whether late data will occur, but **how your system handles it**.

### Strategies for Late Data

| Strategy | Behavior | Trade-off |
|----------|----------|-----------|
| **Drop** | Silently discard late events | Simplest; data loss |
| **Allowed lateness** | Keep windows open longer | More memory; delayed cleanup |
| **Side output** | Route late data to separate stream | No data loss; requires separate processing |
| **Retraction/Update** | Re-emit corrected window result | Most correct; consumers must handle updates |

**Best practice**: Use **side outputs** combined with **allowed lateness**. Events within the lateness window update the existing result (with retraction). Events beyond the lateness window go to a side output for batch reconciliation. This provides the best balance of correctness, resource usage, and operational simplicity.

```python
# Late data handling with watermark tracking and side outputs
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, TypeVar
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

V = TypeVar("V")


@dataclass
class LateDataPolicy:
    # Configuration for late data handling
    allowed_lateness_seconds: float = 300.0  # 5 minutes
    emit_retractions: bool = True
    side_output_enabled: bool = True


@dataclass
class WindowResult(Generic[V]):
    # A window result that may be updated by late data.
    # is_retraction=True means this result replaces a previous emission.
    key: str
    window_start: float
    window_end: float
    value: V
    is_retraction: bool = False
    version: int = 1


class WatermarkTracker:
    # Tracks watermark across multiple input partitions.
    # The global watermark is the minimum across all partition watermarks,
    # because events from any partition could arrive with timestamps
    # up to that partition's watermark.

    def __init__(self, num_partitions: int) -> None:
        self._partition_watermarks: Dict[int, float] = {
            i: 0.0 for i in range(num_partitions)
        }
        self._global_watermark: float = 0.0

    def update_partition(self, partition: int, watermark: float) -> float:
        # Update a partition's watermark and recalculate global
        old = self._partition_watermarks.get(partition, 0.0)
        if watermark > old:
            self._partition_watermarks[partition] = watermark

        # Global watermark = min of all partition watermarks
        new_global = min(self._partition_watermarks.values())
        advanced = new_global > self._global_watermark
        self._global_watermark = new_global
        return self._global_watermark

    @property
    def current(self) -> float:
        return self._global_watermark


class LateDataAwareAggregator(Generic[V]):
    # Windowed aggregator with comprehensive late data handling.
    #
    # When a late event arrives for an already-fired window:
    # 1. If within allowed_lateness: re-aggregate and emit retraction + update
    # 2. If beyond allowed_lateness: route to side output
    #
    # This approach provides eventual correctness while bounding
    # the state that must be retained.

    def __init__(
        self,
        window_size_seconds: float,
        aggregate_fn: Callable[[List[V]], V],
        policy: Optional[LateDataPolicy] = None,
    ) -> None:
        self._window_size = window_size_seconds
        self._aggregate_fn = aggregate_fn
        self._policy = policy or LateDataPolicy()
        self._watermark_tracker = WatermarkTracker(num_partitions=1)

        # State: key -> window_start -> list of values
        self._window_state: Dict[str, Dict[float, List[V]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # Track which windows have been fired and their last result
        self._fired_results: Dict[Tuple[str, float], WindowResult] = {}
        # Side output buffer for excessively late data
        self._side_output: List[Tuple[str, float, V]] = []
        # Main output buffer
        self._output: List[WindowResult[V]] = []

    def _get_window_start(self, event_time: float) -> float:
        return (event_time // self._window_size) * self._window_size

    def process(
        self,
        key: str,
        value: V,
        event_time: float,
        partition: int = 0,
    ) -> None:
        # Process a single event, handling on-time and late data
        window_start = self._get_window_start(event_time)
        window_end = window_start + self._window_size
        window_key = (key, window_start)
        current_wm = self._watermark_tracker.current

        if event_time < current_wm:
            # This is late data
            if window_key in self._fired_results:
                # Window already fired
                lateness = current_wm - window_end
                if lateness <= self._policy.allowed_lateness_seconds:
                    # Within allowed lateness: update the window
                    self._window_state[key][window_start].append(value)
                    new_result = self._aggregate_fn(
                        self._window_state[key][window_start]
                    )
                    prev = self._fired_results[window_key]

                    if self._policy.emit_retractions:
                        # Emit retraction of old result
                        retraction = WindowResult(
                            key=key,
                            window_start=window_start,
                            window_end=window_end,
                            value=prev.value,
                            is_retraction=True,
                            version=prev.version,
                        )
                        self._output.append(retraction)

                    # Emit updated result
                    updated = WindowResult(
                        key=key,
                        window_start=window_start,
                        window_end=window_end,
                        value=new_result,
                        is_retraction=False,
                        version=prev.version + 1,
                    )
                    self._fired_results[window_key] = updated
                    self._output.append(updated)
                    logger.info(
                        f"Late data updated window [{window_start}, {window_end}) "
                        f"for key={key}, version={updated.version}"
                    )
                else:
                    # Beyond allowed lateness: side output
                    if self._policy.side_output_enabled:
                        self._side_output.append((key, event_time, value))
                        logger.warning(
                            f"Event too late ({lateness:.1f}s > "
                            f"{self._policy.allowed_lateness_seconds}s), "
                            f"routed to side output"
                        )
            else:
                # Window not yet fired (late but still in progress)
                self._window_state[key][window_start].append(value)
        else:
            # On-time event
            self._window_state[key][window_start].append(value)

    def advance_watermark(
        self, watermark: float, partition: int = 0
    ) -> Tuple[List[WindowResult[V]], List[Tuple[str, float, V]]]:
        # Advance watermark and fire ready windows.
        # Returns (main_output, side_output).
        self._watermark_tracker.update_partition(partition, watermark)
        current_wm = self._watermark_tracker.current

        # Fire all windows whose end time <= current watermark
        for key in list(self._window_state.keys()):
            for window_start in list(self._window_state[key].keys()):
                window_end = window_start + self._window_size
                window_key = (key, window_start)

                if window_end <= current_wm and window_key not in self._fired_results:
                    values = self._window_state[key][window_start]
                    result = self._aggregate_fn(values)
                    window_result = WindowResult(
                        key=key,
                        window_start=window_start,
                        window_end=window_end,
                        value=result,
                    )
                    self._fired_results[window_key] = window_result
                    self._output.append(window_result)

                # Clean up state for windows past allowed lateness
                cleanup_threshold = current_wm - self._policy.allowed_lateness_seconds
                if window_end < cleanup_threshold:
                    del self._window_state[key][window_start]
                    # Optionally clean fired_results too for memory

            if not self._window_state[key]:
                del self._window_state[key]

        # Drain output buffers
        main_output = list(self._output)
        side_output = list(self._side_output)
        self._output.clear()
        self._side_output.clear()
        return main_output, side_output
```

## Putting It All Together

The patterns above compose naturally. A real stream processing pipeline typically combines all four:

1. **Windowed aggregation** computes metrics over time intervals
2. **CEP** detects anomalous patterns that trigger alerts
3. **Exactly-once checkpointing** ensures state consistency across restarts
4. **Late data handling** provides correctness without sacrificing timeliness

The key insight is that these patterns are **orthogonal**: you can mix and match them based on requirements. A fraud detection system might use CEP with exactly-once checkpointing but no windowed aggregation. A metrics pipeline might use windowed aggregation with late data handling but no CEP. Understanding each pattern independently gives you the flexibility to compose the right solution.

## Summary and Key Takeaways

- **Windowed aggregation** is the foundation of stream analytics: tumbling windows for periodic reports, sliding windows for rolling metrics, session windows for user activity -- each with distinct memory and latency trade-offs
- **Complex Event Processing** uses NFA-based pattern matching to detect ordered sequences of events across time; this is essential for fraud detection, SLA monitoring, and business rule automation where simple aggregation is insufficient
- **Exactly-once semantics** are best achieved through at-least-once delivery combined with idempotent writes (effective exactly-once), because this approach works with any sink regardless of transactional support
- **Late data handling** must be a first-class concern: use allowed lateness for bounded updates, side outputs for excessively late events, and retractions to notify downstream consumers of corrected results
- **Watermark management** is the single most impactful tuning parameter: too tight and you lose late data, too loose and you increase end-to-end latency; monitor watermark lag as a key operational metric
- These patterns are **composable and framework-agnostic**: understanding them at the pattern level means you can implement in Flink, Kafka Streams, or custom Python depending on scale requirements
'''
    ),
]
