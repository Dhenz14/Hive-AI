PAIRS = [
    (
        "database/time-series-data-modeling",
        r"""Explain time-series database design for high-volume metric ingestion including data model design with tags and fields, downsampling and retention policies, compression algorithms like delta-of-delta and XOR encoding, and efficient query patterns using TimescaleDB and InfluxDB.""",
        r"""## Time-Series Database Design: Data Models, Compression, and Query Patterns for High-Volume Metrics

**Time-series data** is one of the fastest-growing categories of structured data, driven by IoT sensors, application monitoring, financial markets, and infrastructure observability. Unlike relational workloads where rows are updated in place, time-series workloads are **append-heavy** with data arriving as an ordered stream of timestamped observations. This fundamental difference means that general-purpose databases perform poorly for time-series use cases **because** they are optimized for random access patterns rather than sequential writes and range scans over time intervals.

### Data Model Design: Tags, Fields, and Timestamps

The foundational **trade-off** in time-series data modeling is between **cardinality** (the number of unique series) and **query flexibility**. Every time-series system organizes data around three concepts:

- **Timestamp**: the primary ordering dimension, typically stored in nanosecond or millisecond precision
- **Tags** (or labels/dimensions): indexed metadata that identifies the series (e.g., `host=web01`, `region=us-east`)
- **Fields** (or values/metrics): the measured values that change over time (e.g., `cpu_usage=73.2`, `memory_free=4096`)

A **common mistake** is treating high-cardinality attributes as tags. For example, using a user ID as a tag in a system with millions of users creates millions of unique series, which explodes the index size and degrades query performance. **Best practice**: only use tags for dimensions you will filter or group by in queries, and keep tag cardinality below 100,000 per measurement.

```python
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
import hashlib


@dataclass
class TimeSeriesPoint:
    # A single measurement point in a time-series
    # Tags are indexed for filtering; fields store the actual values
    measurement: str
    tags: dict[str, str]
    fields: dict[str, float]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def series_key(self) -> str:
        # Unique identifier for this series based on measurement + sorted tags
        # Because tags define the series identity, changing tags creates a new series
        sorted_tags = sorted(self.tags.items())
        tag_str = ",".join(f"{k}={v}" for k, v in sorted_tags)
        return f"{self.measurement},{tag_str}"

    @property
    def series_hash(self) -> str:
        return hashlib.sha256(self.series_key.encode()).hexdigest()[:16]

    def to_line_protocol(self) -> str:
        # Convert to InfluxDB line protocol format
        # measurement,tag1=val1,tag2=val2 field1=val1,field2=val2 timestamp_ns
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(self.tags.items()))
        field_str = ",".join(f"{k}={v}" for k, v in self.fields.items())
        ts_ns = int(self.timestamp.timestamp() * 1_000_000_000)
        return f"{self.measurement},{tag_str} {field_str} {ts_ns}"


class TimeSeriesBuffer:
    # Batches points in memory before flushing to the database
    # Best practice: batch writes to amortize network and disk overhead
    # Pitfall: unbounded buffers can cause OOM under burst traffic

    def __init__(self, max_size: int = 5000, max_age_seconds: float = 10.0):
        self.max_size = max_size
        self.max_age_seconds = max_age_seconds
        self.points: list[TimeSeriesPoint] = []
        self.last_flush: datetime = datetime.now(timezone.utc)

    def add(self, point: TimeSeriesPoint) -> Optional[list[TimeSeriesPoint]]:
        self.points.append(point)
        elapsed = (datetime.now(timezone.utc) - self.last_flush).total_seconds()
        if len(self.points) >= self.max_size or elapsed >= self.max_age_seconds:
            return self.flush()
        return None

    def flush(self) -> list[TimeSeriesPoint]:
        batch = self.points
        self.points = []
        self.last_flush = datetime.now(timezone.utc)
        return batch
```

### Compression Algorithms: Delta-of-Delta and XOR Encoding

Time-series databases achieve **10x to 20x compression ratios** compared to general-purpose storage by exploiting the temporal structure of metric data. The two key algorithms, pioneered by Facebook's Gorilla paper, are:

**Delta-of-delta encoding for timestamps**: Timestamps in a regular metric stream are nearly equally spaced (e.g., every 10 seconds). Instead of storing each 64-bit timestamp, store the delta between consecutive timestamps. **However**, deltas themselves are often constant (all 10), so storing the *delta of the delta* yields mostly zeros. These zeros compress to just 1 bit per timestamp using variable-length encoding.

**XOR encoding for floating-point values**: Consecutive metric values are often similar. XOR-ing adjacent float64 values produces results with many leading and trailing zeros. By storing only the meaningful bits (the non-zero middle section), each value typically requires only 12-16 bits instead of 64 bits.

```python
import struct
from typing import Iterator


class DeltaOfDeltaEncoder:
    # Compresses timestamps using delta-of-delta encoding
    # Because metric timestamps are nearly equally spaced,
    # the delta-of-delta is usually 0 or very small

    def __init__(self) -> None:
        self.prev_timestamp: Optional[int] = None
        self.prev_delta: int = 0
        self.encoded_bits: list[int] = []

    def encode(self, timestamp_ns: int) -> list[int]:
        if self.prev_timestamp is None:
            # First value: store the full 64-bit timestamp
            self.prev_timestamp = timestamp_ns
            return self._encode_full(timestamp_ns)

        delta = timestamp_ns - self.prev_timestamp
        delta_of_delta = delta - self.prev_delta
        self.prev_timestamp = timestamp_ns
        self.prev_delta = delta

        # Encode delta-of-delta with variable-length coding
        if delta_of_delta == 0:
            return [0]  # single zero bit
        elif -63 <= delta_of_delta <= 64:
            return [1, 0] + self._to_bits(delta_of_delta, 7)
        elif -255 <= delta_of_delta <= 256:
            return [1, 1, 0] + self._to_bits(delta_of_delta, 9)
        elif -2047 <= delta_of_delta <= 2048:
            return [1, 1, 1, 0] + self._to_bits(delta_of_delta, 12)
        else:
            return [1, 1, 1, 1] + self._to_bits(delta_of_delta, 64)

    def _encode_full(self, value: int) -> list[int]:
        return self._to_bits(value, 64)

    def _to_bits(self, value: int, num_bits: int) -> list[int]:
        # Convert integer to bit list with sign handling
        if value < 0:
            value = (1 << num_bits) + value
        return [(value >> (num_bits - 1 - i)) & 1 for i in range(num_bits)]


class XORFloatEncoder:
    # Compresses float64 values using XOR encoding (Gorilla algorithm)
    # Trade-off: higher compression ratio vs slightly slower random access

    def __init__(self) -> None:
        self.prev_bits: Optional[int] = None

    def encode(self, value: float) -> dict:
        current_bits = struct.unpack(">Q", struct.pack(">d", value))[0]

        if self.prev_bits is None:
            self.prev_bits = current_bits
            return {"type": "full", "bits": current_bits, "size": 64}

        xor_result = self.prev_bits ^ current_bits
        self.prev_bits = current_bits

        if xor_result == 0:
            return {"type": "zero", "size": 1}

        # Count leading and trailing zeros in the XOR result
        leading = self._count_leading_zeros(xor_result)
        trailing = self._count_trailing_zeros(xor_result)
        meaningful_bits = 64 - leading - trailing

        return {
            "type": "xor",
            "leading_zeros": leading,
            "trailing_zeros": trailing,
            "meaningful_bits": meaningful_bits,
            "size": meaningful_bits + 12,  # 5 bits leading + 6 bits length + data
        }

    def _count_leading_zeros(self, value: int) -> int:
        if value == 0:
            return 64
        count = 0
        for i in range(63, -1, -1):
            if (value >> i) & 1:
                break
            count += 1
        return count

    def _count_trailing_zeros(self, value: int) -> int:
        if value == 0:
            return 64
        count = 0
        for i in range(64):
            if (value >> i) & 1:
                break
            count += 1
        return count
```

### Downsampling and Retention Policies

Storing every raw data point indefinitely is cost-prohibitive. **Therefore**, time-series systems implement tiered retention with automatic downsampling. The typical pattern is:

- **Raw data**: retain for 7-30 days at full resolution (e.g., 10-second intervals)
- **1-minute aggregates**: retain for 90 days
- **1-hour aggregates**: retain for 2 years
- **1-day aggregates**: retain indefinitely

**Best practice**: pre-compute aggregates using continuous aggregation rather than computing them at query time. TimescaleDB provides `continuous_aggregates` that materialize rollups incrementally.

```python
from enum import Enum
from typing import Callable


class AggregationType(Enum):
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    SUM = "sum"
    COUNT = "count"
    P95 = "percentile_95"
    P99 = "percentile_99"


@dataclass
class RetentionPolicy:
    # Defines how long data is kept at each resolution
    # Common mistake: not keeping min/max alongside avg in rollups
    # because averaging hides spikes that triggered alerts
    raw_retention_days: int
    rollup_interval_seconds: int
    rollup_retention_days: int
    aggregations: list[AggregationType]

    def should_downsample(self, data_age_days: int) -> bool:
        return data_age_days > self.raw_retention_days


@dataclass
class RetentionTier:
    name: str
    interval_seconds: int
    retention_days: int
    aggregations: list[AggregationType]


class RetentionManager:
    # Manages multi-tier retention policies
    # Best practice: always keep count alongside other aggregations
    # because count enables accurate re-aggregation across tiers

    def __init__(self) -> None:
        self.tiers: list[RetentionTier] = []

    def add_tier(self, tier: RetentionTier) -> None:
        self.tiers.append(tier)
        self.tiers.sort(key=lambda t: t.interval_seconds)

    def get_query_tier(self, time_range_seconds: int) -> RetentionTier:
        # Select the appropriate tier based on query time range
        # Trade-off: coarser tiers are faster but lose detail
        for tier in self.tiers:
            points_estimate = time_range_seconds / tier.interval_seconds
            if points_estimate <= 10_000:
                return tier
        return self.tiers[-1]
```

### Query Patterns and Optimization

Efficient time-series queries follow predictable patterns: they always filter by time range first, then by tags, and finally aggregate fields. **Pitfall**: queries without a time range predicate force a full table scan across all chunks, which is catastrophically slow on large datasets.

In TimescaleDB, queries benefit from **chunk exclusion**: the planner skips chunks whose time range does not overlap the query's `WHERE` clause. In InfluxDB, the **TSI (Time-Structured Index)** maps tag combinations to series IDs, enabling sub-millisecond series lookup even with millions of unique series.

### Summary and Key Takeaways

- **Design your schema around query patterns**: tags for filtering, fields for values, and always include a time range in every query.
- **Cardinality is the enemy**: high-cardinality tags destroy index performance. Monitor series cardinality as a first-class metric.
- **Compression is free performance**: delta-of-delta and XOR encoding deliver 10-20x compression with negligible CPU cost, **therefore** always enable them.
- **Tiered retention is mandatory**: raw data is expensive to store; pre-compute rollups and drop raw data after the retention window.
- **Batch your writes**: amortize write overhead by buffering points and flushing in batches of 1,000-5,000 points.
- The fundamental **trade-off** is between query flexibility and storage efficiency; design your data model to match your most common access patterns.
""",
    ),
    (
        "database/event-sourcing-cqrs",
        r"""Describe event sourcing and CQRS architecture for building scalable applications, including event store design with append-only logs, projection and read model building, snapshotting strategies for aggregate recovery, eventual consistency handling, and read model optimization techniques.""",
        r"""## Event Sourcing and CQRS: Building Scalable Event-Driven Architectures

**Event sourcing** is an architectural pattern where application state is derived from an append-only log of immutable events rather than mutable rows in a relational table. Combined with **CQRS (Command Query Responsibility Segregation)**, which separates the write model from the read model, these patterns enable systems that are auditable, scalable, and naturally suited to distributed architectures. **However**, they introduce significant complexity around eventual consistency, event schema evolution, and projection management that must be carefully managed.

### Why Event Sourcing?

In a traditional CRUD application, you store the *current state* of an entity. When a user changes their email, the old email is overwritten. This is a **common mistake** in domains where history matters -- financial systems, healthcare, compliance, and audit-sensitive applications all need a complete record of every state change. Event sourcing solves this **because** every change is captured as a discrete event: `EmailChanged { old: "a@b.com", new: "c@d.com", timestamp: ... }`. The current state is reconstructed by replaying all events from the beginning.

The **trade-off** is clear: you gain complete auditability, temporal queries, and the ability to rebuild state from scratch, but you pay with increased storage, more complex query patterns, and eventual consistency in read models.

### Event Store Design

An event store is fundamentally an append-only log partitioned by **aggregate streams**. Each stream contains the ordered events for a single aggregate (e.g., all events for Order #12345). The store must guarantee:

1. **Append-only semantics**: events are never updated or deleted
2. **Optimistic concurrency**: writes include an expected version number to prevent conflicts
3. **Ordered delivery**: events within a stream maintain strict ordering

```python
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, TypeVar
from datetime import datetime, timezone
from uuid import UUID, uuid4
import json
import hashlib


@dataclass(frozen=True)
class DomainEvent:
    # Base class for all domain events
    # Frozen because events are immutable once created
    event_id: UUID
    aggregate_id: str
    event_type: str
    data: dict[str, Any]
    metadata: dict[str, Any]
    timestamp: datetime
    version: int  # position within the aggregate stream

    def to_json(self) -> str:
        return json.dumps({
            "event_id": str(self.event_id),
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "data": self.data,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
        })


class EventStore:
    # Append-only event store with optimistic concurrency
    # Best practice: use a relational database with a unique constraint
    # on (aggregate_id, version) for built-in optimistic locking

    def __init__(self) -> None:
        self.streams: dict[str, list[DomainEvent]] = {}
        self.global_position: int = 0
        self.global_log: list[DomainEvent] = []

    def append(
        self,
        aggregate_id: str,
        events: list[DomainEvent],
        expected_version: int,
    ) -> None:
        stream = self.streams.get(aggregate_id, [])
        current_version = len(stream)

        # Optimistic concurrency check
        # Common mistake: not checking version, leading to lost updates
        if current_version != expected_version:
            raise ConcurrencyError(
                f"Expected version {expected_version} for aggregate "
                f"{aggregate_id}, but current version is {current_version}"
            )

        for event in events:
            self.global_position += 1
            stream.append(event)
            self.global_log.append(event)

        self.streams[aggregate_id] = stream

    def load_stream(
        self,
        aggregate_id: str,
        from_version: int = 0,
    ) -> list[DomainEvent]:
        stream = self.streams.get(aggregate_id, [])
        return stream[from_version:]

    def read_all(self, from_position: int = 0) -> list[DomainEvent]:
        # Read the global ordered log for building projections
        return self.global_log[from_position:]


class ConcurrencyError(Exception):
    pass
```

### Aggregates and Event Application

An aggregate in event sourcing is rebuilt by replaying its events. The aggregate's `apply` methods define how each event type modifies the internal state. **Best practice**: keep aggregates focused on business invariant enforcement, not read-side concerns.

```python
from abc import ABC, abstractmethod
from typing import TypeVar, Generic


class Aggregate(ABC):
    # Base aggregate with event replay and uncommitted event tracking

    def __init__(self, aggregate_id: str) -> None:
        self.aggregate_id = aggregate_id
        self.version: int = 0
        self._uncommitted_events: list[DomainEvent] = []

    def load_from_history(self, events: list[DomainEvent]) -> None:
        # Replay events to rebuild current state
        for event in events:
            self._apply_event(event)
            self.version = event.version

    def _raise_event(self, event_type: str, data: dict[str, Any]) -> None:
        # Create and apply a new event
        event = DomainEvent(
            event_id=uuid4(),
            aggregate_id=self.aggregate_id,
            event_type=event_type,
            data=data,
            metadata={"source": "command_handler"},
            timestamp=datetime.now(timezone.utc),
            version=self.version + 1,
        )
        self._apply_event(event)
        self.version = event.version
        self._uncommitted_events.append(event)

    @abstractmethod
    def _apply_event(self, event: DomainEvent) -> None:
        pass

    def get_uncommitted_events(self) -> list[DomainEvent]:
        events = self._uncommitted_events[:]
        self._uncommitted_events.clear()
        return events


class OrderAggregate(Aggregate):
    # Example: order aggregate with business invariants

    def __init__(self, aggregate_id: str) -> None:
        super().__init__(aggregate_id)
        self.status: str = "created"
        self.items: list[dict] = []
        self.total: float = 0.0

    def add_item(self, product_id: str, quantity: int, price: float) -> None:
        # Enforce business invariant: cannot add items to shipped orders
        if self.status == "shipped":
            raise ValueError("Cannot add items to a shipped order")
        self._raise_event("ItemAdded", {
            "product_id": product_id,
            "quantity": quantity,
            "price": price,
        })

    def ship(self) -> None:
        if not self.items:
            raise ValueError("Cannot ship empty order")
        if self.status == "shipped":
            raise ValueError("Order already shipped")
        self._raise_event("OrderShipped", {"shipped_at": datetime.now(timezone.utc).isoformat()})

    def _apply_event(self, event: DomainEvent) -> None:
        if event.event_type == "ItemAdded":
            self.items.append(event.data)
            self.total += event.data["price"] * event.data["quantity"]
        elif event.event_type == "OrderShipped":
            self.status = "shipped"
```

### Snapshots for Performance

Replaying thousands of events to rebuild an aggregate is expensive. **Therefore**, snapshot strategies periodically capture the aggregate state so that replay only needs to process events *after* the snapshot.

**Best practice**: snapshot every N events (e.g., every 100 events) and store snapshots alongside the event stream. When loading, first check for a snapshot, then replay only subsequent events.

A **pitfall** with snapshots is schema evolution: if you change the aggregate's internal representation, old snapshots may become invalid. **Best practice**: version your snapshot schema and fall back to full replay if the snapshot version is outdated.

### Projections and Read Models

CQRS separates commands (writes) from queries (reads). The write side produces events; the read side consumes them to build optimized **projections** (also called read models or materialized views).

```python
from typing import Callable


class Projection:
    # Builds and maintains a read model from event streams
    # Trade-off: read models are eventually consistent with the write side
    # However, they can be optimized for specific query patterns

    def __init__(self, name: str) -> None:
        self.name = name
        self.position: int = 0
        self.handlers: dict[str, Callable[[DomainEvent], None]] = {}

    def register_handler(self, event_type: str, handler: Callable[[DomainEvent], None]) -> None:
        self.handlers[event_type] = handler

    def process_events(self, events: list[DomainEvent]) -> int:
        processed = 0
        for event in events:
            handler = self.handlers.get(event.event_type)
            if handler is not None:
                handler(event)
                processed += 1
            self.position += 1
        return processed


class OrderDashboardProjection:
    # Read model optimized for dashboard queries
    # Because this is separate from the write model, we can denormalize freely

    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.projection = Projection("order_dashboard")
        self.projection.register_handler("ItemAdded", self._on_item_added)
        self.projection.register_handler("OrderShipped", self._on_order_shipped)

    def _on_item_added(self, event: DomainEvent) -> None:
        order_id = event.aggregate_id
        if order_id not in self.orders:
            self.orders[order_id] = {
                "order_id": order_id,
                "item_count": 0,
                "total": 0.0,
                "status": "pending",
            }
        order = self.orders[order_id]
        order["item_count"] += event.data["quantity"]
        order["total"] += event.data["price"] * event.data["quantity"]

    def _on_order_shipped(self, event: DomainEvent) -> None:
        order_id = event.aggregate_id
        if order_id in self.orders:
            self.orders[order_id]["status"] = "shipped"

    def get_pending_orders(self) -> list[dict]:
        return [o for o in self.orders.values() if o["status"] == "pending"]

    def get_high_value_orders(self, threshold: float = 1000.0) -> list[dict]:
        return [o for o in self.orders.values() if o["total"] >= threshold]
```

### Eventual Consistency Handling

Because projections consume events asynchronously, there is an inherent delay between a command being executed and the read model reflecting the change. This **eventual consistency** requires careful UX and API design:

- **Read-your-own-writes**: after a command succeeds, return the expected state directly from the command response rather than querying the read model
- **Causal consistency tokens**: include a version token in command responses that the client passes to subsequent queries; the read side waits until it has processed up to that position
- **Polling with backoff**: for operations where the user expects to see updates, poll the read model with exponential backoff

### Summary and Key Takeaways

- **Event sourcing captures every state change** as an immutable event, providing complete auditability and the ability to rebuild state from scratch.
- **CQRS separates writes from reads**, enabling independently optimized models for each concern. **However**, this adds operational complexity.
- **Optimistic concurrency** in the event store prevents lost updates without pessimistic locking. **Best practice**: use a database unique constraint on (aggregate_id, version).
- **Snapshots are essential** for aggregates with many events. Take them every N events and version the schema.
- **Projections are eventually consistent** by nature. Design your API and UX to handle the propagation delay gracefully.
- The fundamental **trade-off** is between simplicity (CRUD) and capability (audit trails, temporal queries, independent scaling). Choose event sourcing when the domain genuinely benefits from event history.
""",
    ),
    (
        "database/zero-downtime-migration-strategies",
        r"""Explain zero-downtime database migration strategies including the expand-contract pattern, ghost table migrations with tools like gh-ost and pt-online-schema-change, schema versioning approaches, backward-compatible migration techniques, and safe rollback procedures for production databases.""",
        r"""## Zero-Downtime Database Migration Strategies: Expand-Contract, Ghost Tables, and Safe Rollbacks

**Database migrations are the most dangerous routine operation** in production systems. A poorly executed migration can lock tables for hours, corrupt data, or cause cascading application failures. **Because** modern applications demand 99.99% uptime, teams need migration strategies that apply schema changes without any service interruption. This requires understanding the expand-contract pattern, online schema change tools, backward compatibility, and rollback procedures.

### The Fundamental Problem

Traditional `ALTER TABLE` statements on large tables in MySQL or PostgreSQL can acquire **exclusive locks** that block all reads and writes for the duration of the operation. Adding a column to a 500-million-row table can take hours, during which the table is effectively offline. **Therefore**, every migration strategy ultimately solves the same problem: how to apply schema changes without holding long-duration locks.

### The Expand-Contract Pattern

The expand-contract pattern (also called **parallel change**) is the foundational approach for zero-downtime migrations. It splits every breaking schema change into three phases:

1. **Expand**: add the new schema elements alongside the old ones (new column, new table, new index)
2. **Migrate**: update application code to write to both old and new structures, backfill existing data
3. **Contract**: remove the old schema elements once all code has been updated

This pattern works **because** each phase is individually backward-compatible. At no point does the application encounter a schema it cannot handle.

```python
from dataclasses import dataclass, field
from typing import Optional, Protocol
from enum import Enum
from datetime import datetime, timezone


class MigrationPhase(Enum):
    EXPAND = "expand"
    MIGRATE = "migrate"
    CONTRACT = "contract"


@dataclass
class MigrationStep:
    # Represents a single step in an expand-contract migration
    # Each step must be independently reversible
    phase: MigrationPhase
    description: str
    up_sql: str
    down_sql: str
    is_safe_online: bool  # whether this can run without locking
    estimated_duration_seconds: Optional[int] = None
    requires_backfill: bool = False


class MigrationPlan:
    # Orchestrates a multi-phase expand-contract migration
    # Best practice: each phase should be deployed independently
    # with monitoring between phases to catch issues early

    def __init__(self, name: str, target_table: str) -> None:
        self.name = name
        self.target_table = target_table
        self.steps: list[MigrationStep] = []
        self.executed: list[MigrationStep] = []

    def add_step(self, step: MigrationStep) -> None:
        self.steps.append(step)

    def validate_ordering(self) -> bool:
        # Ensure phases are in correct order: expand -> migrate -> contract
        phase_order = [MigrationPhase.EXPAND, MigrationPhase.MIGRATE, MigrationPhase.CONTRACT]
        current_phase_idx = 0
        for step in self.steps:
            step_idx = phase_order.index(step.phase)
            if step_idx < current_phase_idx:
                raise ValueError(
                    f"Step '{step.description}' is {step.phase.value} "
                    f"but comes after {phase_order[current_phase_idx].value}"
                )
            current_phase_idx = step_idx
        return True

    def get_rollback_plan(self) -> list[MigrationStep]:
        # Generate rollback by reversing executed steps
        # Pitfall: contract steps cannot always be rolled back
        # because dropped columns lose data permanently
        rollback = []
        for step in reversed(self.executed):
            if step.down_sql:
                rollback.append(MigrationStep(
                    phase=step.phase,
                    description=f"ROLLBACK: {step.description}",
                    up_sql=step.down_sql,
                    down_sql=step.up_sql,
                    is_safe_online=step.is_safe_online,
                ))
            else:
                raise IrreversibleMigrationError(
                    f"Cannot rollback step: {step.description}"
                )
        return rollback


class IrreversibleMigrationError(Exception):
    pass


def create_rename_column_migration(
    table: str,
    old_column: str,
    new_column: str,
    column_type: str,
) -> MigrationPlan:
    # Example: renaming a column using expand-contract
    # Common mistake: using ALTER TABLE RENAME COLUMN directly
    # because it breaks all application code referencing the old name
    plan = MigrationPlan(f"rename_{old_column}_to_{new_column}", table)

    # Phase 1: Expand - add new column
    plan.add_step(MigrationStep(
        phase=MigrationPhase.EXPAND,
        description=f"Add column {new_column}",
        up_sql=f"ALTER TABLE {table} ADD COLUMN {new_column} {column_type}",
        down_sql=f"ALTER TABLE {table} DROP COLUMN {new_column}",
        is_safe_online=True,
    ))

    # Phase 2: Migrate - dual-write trigger and backfill
    trigger_sql = (
        f"CREATE OR REPLACE FUNCTION sync_{old_column}_to_{new_column}() "
        f"RETURNS TRIGGER AS $$ BEGIN "
        f"NEW.{new_column} = NEW.{old_column}; "
        f"RETURN NEW; END; $$ LANGUAGE plpgsql"
    )
    plan.add_step(MigrationStep(
        phase=MigrationPhase.MIGRATE,
        description="Create dual-write trigger",
        up_sql=trigger_sql,
        down_sql=f"DROP FUNCTION IF EXISTS sync_{old_column}_to_{new_column}() CASCADE",
        is_safe_online=True,
    ))

    backfill_sql = (
        f"UPDATE {table} SET {new_column} = {old_column} "
        f"WHERE {new_column} IS NULL"
    )
    plan.add_step(MigrationStep(
        phase=MigrationPhase.MIGRATE,
        description="Backfill existing data",
        up_sql=backfill_sql,
        down_sql="",  # backfill is naturally idempotent
        is_safe_online=False,
        requires_backfill=True,
        estimated_duration_seconds=3600,
    ))

    # Phase 3: Contract - remove old column (after code migration)
    plan.add_step(MigrationStep(
        phase=MigrationPhase.CONTRACT,
        description=f"Drop old column {old_column}",
        up_sql=f"ALTER TABLE {table} DROP COLUMN {old_column}",
        down_sql="",  # data is lost, cannot rollback
        is_safe_online=True,
    ))

    return plan
```

### Ghost Table Migrations

Tools like **gh-ost** (GitHub's Online Schema Tool) and **pt-online-schema-change** (Percona Toolkit) implement a "ghost table" approach for MySQL:

1. Create a **ghost table** with the desired new schema
2. Copy existing rows from the original table to the ghost table in small batches
3. Capture ongoing DML changes (via binlog parsing in gh-ost, triggers in pt-osc) and apply them to the ghost table
4. Once the ghost table is caught up, perform an **atomic rename** to swap the tables

The **trade-off** with gh-ost vs pt-osc is that gh-ost avoids triggers (which add write overhead) by parsing the MySQL binary log directly, **however** it requires binlog access and `ROW` format binlog configuration.

```python
@dataclass
class GhostMigrationConfig:
    # Configuration for a gh-ost style migration
    # Best practice: always set a throttle to prevent replica lag
    table: str
    alter_statement: str
    chunk_size: int = 1000
    max_lag_seconds: float = 1.5
    max_load_percent: float = 70.0
    critical_load_percent: float = 95.0
    nice_ratio: float = 0.0  # sleep between chunks: 0 = no sleep
    cut_over_type: str = "atomic"  # atomic or two-step
    initially_drop_ghost_table: bool = True

    def to_command(self) -> str:
        # Generate the gh-ost command
        # Pitfall: forgetting --allow-on-master when running without replicas
        parts = [
            "gh-ost",
            f"--table={self.table}",
            f"--alter='{self.alter_statement}'",
            f"--chunk-size={self.chunk_size}",
            f"--max-lag-millis={int(self.max_lag_seconds * 1000)}",
            f"--max-load='Threads_running={int(self.max_load_percent)}'",
            f"--critical-load='Threads_running={int(self.critical_load_percent)}'",
            "--execute",
        ]
        if self.initially_drop_ghost_table:
            parts.append("--initially-drop-ghost-table")
        return " ".join(parts)


class BatchBackfiller:
    # Backfills data in controlled batches to avoid table locks
    # Because large UPDATE statements hold row locks for the entire transaction,
    # we process in small batches with optional sleep between batches

    def __init__(
        self,
        table: str,
        batch_size: int = 1000,
        sleep_between_batches: float = 0.1,
    ) -> None:
        self.table = table
        self.batch_size = batch_size
        self.sleep_between_batches = sleep_between_batches
        self.total_processed: int = 0

    def generate_batch_sql(self, update_clause: str, condition: str) -> list[str]:
        # Generate batched UPDATE statements using primary key ranges
        # Best practice: always use an indexed column for batching
        statements = []
        batch_sql = (
            f"UPDATE {self.table} "
            f"SET {update_clause} "
            f"WHERE {condition} "
            f"AND id > {{last_id}} "
            f"ORDER BY id "
            f"LIMIT {self.batch_size}"
        )
        return [batch_sql]
```

### Schema Versioning

Every migration should be tracked in a **schema version table** that records what has been applied. Tools like Flyway, Alembic, and golang-migrate follow this pattern. **Best practice**: use both a version number and a checksum so you can detect when a previously applied migration has been modified (which indicates a serious process violation).

```python
@dataclass
class SchemaVersion:
    version: int
    description: str
    checksum: str
    applied_at: datetime
    execution_time_ms: int
    success: bool

    @staticmethod
    def compute_checksum(sql: str) -> str:
        return hashlib.sha256(sql.strip().encode()).hexdigest()[:16]


class SchemaVersionTracker:
    # Tracks applied migrations and detects tampering
    # Trade-off: strict checksum validation prevents accidental changes
    # but makes it harder to fix typos in applied migrations

    def __init__(self) -> None:
        self.versions: list[SchemaVersion] = []

    def is_applied(self, version: int) -> bool:
        return any(v.version == version and v.success for v in self.versions)

    def validate_integrity(self, migrations: list[MigrationStep]) -> list[str]:
        # Detect if any previously applied migration was modified
        errors = []
        for i, migration in enumerate(migrations):
            applied = next((v for v in self.versions if v.version == i), None)
            if applied is not None:
                current_checksum = SchemaVersion.compute_checksum(migration.up_sql)
                if current_checksum != applied.checksum:
                    errors.append(
                        f"Migration v{i} checksum mismatch: "
                        f"applied={applied.checksum}, current={current_checksum}"
                    )
        return errors
```

### Backward Compatibility Rules

For truly zero-downtime migrations, every schema change must be **backward-compatible** with the currently deployed application code. This means:

- **Adding a column**: always use a default value or make it nullable. Never add a NOT NULL column without a default.
- **Removing a column**: first deploy code that stops reading the column, then drop it in a subsequent migration.
- **Renaming a column**: use the expand-contract pattern (add new, dual-write, backfill, remove old).
- **Changing a column type**: add a new column with the new type, backfill with conversion, switch reads, drop old.

A **pitfall** many teams encounter is combining multiple breaking changes in a single deployment. **Best practice**: each migration should contain exactly one logical change, and each deployment should be independently rollback-safe.

### Summary and Key Takeaways

- **The expand-contract pattern** is the universal strategy for zero-downtime migrations: add new structure, migrate data, remove old structure. Each phase is independently deployable.
- **Ghost table tools** (gh-ost, pt-online-schema-change) enable online ALTER TABLE operations by copying data to a shadow table and performing an atomic swap. The **trade-off** is additional disk space and replication load during the copy.
- **Schema versioning with checksums** prevents migration tampering and ensures reproducible deployments across environments.
- **Backward compatibility** is non-negotiable: every migration must work with both the old and new application code simultaneously.
- **Batch your backfills**: large data migrations must be chunked to avoid holding locks. **Best practice**: use primary key ranges with configurable batch sizes and throttling.
- **Never combine contract steps with expand steps** in a single deployment. **Therefore**, always deploy expand first, verify stability, then deploy contract separately.
""",
    ),
    (
        "database/multi-tenant-design-patterns",
        r"""Explain multi-tenant database design patterns including schema-per-tenant versus shared-schema approaches, row-level security policies in PostgreSQL, tenant-aware connection pooling strategies, data isolation guarantees, cross-tenant query prevention, and performance considerations for scaling to thousands of tenants.""",
        r"""## Multi-Tenant Database Design: Isolation, Security, and Scalability Patterns

**Multi-tenancy** is the architectural pattern where a single application instance serves multiple customers (tenants) while keeping their data logically or physically isolated. The database layer is where multi-tenancy decisions have the most significant impact on **security, performance, cost, and operational complexity**. Choosing the wrong isolation model can result in data leaks between tenants, unpredictable performance due to noisy neighbors, or unsustainable operational overhead as the tenant count grows.

### Isolation Models: The Spectrum of Trade-offs

There are three primary isolation models, each representing a different point on the **trade-off** spectrum between isolation strength and operational efficiency:

1. **Database-per-tenant**: each tenant gets a completely separate database instance. Maximum isolation, maximum cost.
2. **Schema-per-tenant**: all tenants share a database server but each has a dedicated schema (namespace). Strong isolation with moderate overhead.
3. **Shared schema (shared tables)**: all tenants share the same tables with a `tenant_id` column distinguishing rows. Minimum cost, minimum isolation.

**Because** most SaaS applications need to scale to thousands of tenants, shared schema is the most common choice for the data tier. **However**, regulated industries (healthcare, finance) may require schema-per-tenant or database-per-tenant for compliance reasons.

### Shared Schema with Row-Level Security

PostgreSQL's **Row-Level Security (RLS)** is the gold standard for enforcing tenant isolation in a shared-schema model. RLS policies are evaluated by the database engine itself, meaning that even if application code has a bug that omits a `WHERE tenant_id = ?` clause, the database will still filter rows correctly.

```python
from dataclasses import dataclass
from typing import Optional
import contextlib


@dataclass
class Tenant:
    tenant_id: str
    name: str
    plan: str  # free, pro, enterprise
    schema_name: Optional[str] = None  # only for schema-per-tenant
    max_connections: int = 5
    is_isolated: bool = False  # enterprise tenants get dedicated resources


class RLSPolicyManager:
    # Manages PostgreSQL Row-Level Security policies for multi-tenant tables
    # Best practice: apply RLS on ALL tables that contain tenant data
    # Common mistake: forgetting to enable RLS on junction/association tables

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        self.policies: list[str] = []

    def generate_rls_setup(self, table: str) -> list[str]:
        # Generate SQL statements to set up RLS on a table
        # Because RLS is enforced at the database level, it provides
        # defense-in-depth even if application code is compromised
        statements = [
            # Enable RLS on the table
            f"ALTER TABLE {self.schema}.{table} ENABLE ROW LEVEL SECURITY",

            # Force RLS for table owner too (important for superuser safety)
            f"ALTER TABLE {self.schema}.{table} FORCE ROW LEVEL SECURITY",

            # Policy: tenants can only see their own rows
            (
                f"CREATE POLICY tenant_isolation ON {self.schema}.{table} "
                f"USING (tenant_id = current_setting('app.current_tenant_id'))"
            ),

            # Policy: tenants can only insert rows with their own tenant_id
            (
                f"CREATE POLICY tenant_insert ON {self.schema}.{table} "
                f"FOR INSERT "
                f"WITH CHECK (tenant_id = current_setting('app.current_tenant_id'))"
            ),
        ]
        self.policies.extend(statements)
        return statements

    def generate_admin_bypass(self, admin_role: str = "app_admin") -> str:
        # Admin role bypasses RLS for cross-tenant operations
        # Pitfall: granting this role too broadly defeats the purpose of RLS
        return (
            f"ALTER ROLE {admin_role} SET row_security = off"
        )


class TenantContext:
    # Sets the tenant context for the current database session
    # Best practice: set tenant context at the connection/transaction level
    # NOT at the query level, to prevent accidental context leakage

    def __init__(self, connection) -> None:
        self.connection = connection

    @contextlib.contextmanager
    def tenant_scope(self, tenant_id: str):
        # Set tenant context for the duration of a request
        # Because this uses PostgreSQL session variables, it works
        # transparently with all queries on the connection
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT set_config('app.current_tenant_id', %s, true)",
                (tenant_id,),
            )
            yield cursor
        finally:
            # Reset tenant context to prevent leakage
            # Common mistake: not resetting context when using connection pools
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT set_config('app.current_tenant_id', '', true)"
            )
```

### Schema-Per-Tenant Implementation

For tenants requiring stronger isolation (typically enterprise customers), schema-per-tenant provides physical separation within the same database:

```python
from typing import Callable


class SchemaPerTenantManager:
    # Manages dedicated schemas for isolated tenants
    # Trade-off: stronger isolation but harder to query across tenants
    # and migrations must be applied to every schema individually

    def __init__(self, base_schema_template: str = "tenant_{tenant_id}") -> None:
        self.schema_template = base_schema_template
        self.active_schemas: dict[str, str] = {}

    def schema_name_for(self, tenant_id: str) -> str:
        return self.schema_template.format(tenant_id=tenant_id)

    def generate_create_schema(self, tenant: Tenant) -> list[str]:
        schema = self.schema_name_for(tenant.tenant_id)
        self.active_schemas[tenant.tenant_id] = schema
        return [
            f"CREATE SCHEMA IF NOT EXISTS {schema}",
            f"SET search_path TO {schema}",
            # Copy table definitions from template schema
            # Best practice: maintain a template schema that new tenants clone
            f"CREATE TABLE {schema}.users (LIKE template.users INCLUDING ALL)",
            f"CREATE TABLE {schema}.orders (LIKE template.users INCLUDING ALL)",
            # Grant permissions to tenant-specific role
            f"GRANT USAGE ON SCHEMA {schema} TO tenant_role_{tenant.tenant_id}",
            f"GRANT ALL ON ALL TABLES IN SCHEMA {schema} TO tenant_role_{tenant.tenant_id}",
        ]

    def generate_migration_for_all(self, migration_sql: str) -> list[str]:
        # Apply a migration to all tenant schemas
        # Pitfall: this is O(n) in the number of tenants
        # Therefore, schema-per-tenant becomes expensive at scale
        statements = []
        for tenant_id, schema in self.active_schemas.items():
            statements.append(f"SET search_path TO {schema}")
            statements.append(migration_sql)
        return statements
```

### Tenant-Aware Connection Pooling

Connection pooling in a multi-tenant system requires careful design. Each database connection has session-level state (search path, RLS context, prepared statements), and **mixing tenant contexts on shared connections is a critical security vulnerability**.

```python
from collections import defaultdict
from typing import Any
import threading
import time


class TenantConnectionPool:
    # Connection pool that ensures tenant context isolation
    # Common mistake: using a single pool where connections retain
    # the previous tenant's context after being returned

    def __init__(
        self,
        dsn: str,
        default_pool_size: int = 5,
        max_pool_size: int = 50,
        max_total_connections: int = 500,
    ) -> None:
        self.dsn = dsn
        self.default_pool_size = default_pool_size
        self.max_pool_size = max_pool_size
        self.max_total_connections = max_total_connections
        self.pools: dict[str, list[Any]] = defaultdict(list)
        self.pool_sizes: dict[str, int] = {}
        self.total_connections: int = 0
        self._lock = threading.Lock()

    def get_connection(self, tenant: Tenant) -> Any:
        # Get a connection pre-configured for this tenant
        # Best practice: set tenant context immediately on checkout
        with self._lock:
            pool = self.pools[tenant.tenant_id]
            if pool:
                conn = pool.pop()
                self._set_tenant_context(conn, tenant)
                return conn

            if self.total_connections >= self.max_total_connections:
                # Implement fair queuing per tenant
                # Trade-off: prevents one tenant from starving others
                # but adds latency for burst traffic
                raise ConnectionPoolExhausted(
                    f"Total connection limit ({self.max_total_connections}) reached"
                )

            conn = self._create_connection()
            self.total_connections += 1
            self._set_tenant_context(conn, tenant)
            return conn

    def return_connection(self, tenant: Tenant, conn: Any) -> None:
        # Return connection to pool after clearing tenant context
        # CRITICAL: always clear context before returning
        self._clear_tenant_context(conn)
        max_size = self.pool_sizes.get(tenant.tenant_id, self.default_pool_size)
        with self._lock:
            pool = self.pools[tenant.tenant_id]
            if len(pool) < max_size:
                pool.append(conn)
            else:
                conn.close()
                self.total_connections -= 1

    def _create_connection(self) -> Any:
        # Create a new database connection
        # In production, use psycopg2, asyncpg, or similar
        pass

    def _set_tenant_context(self, conn: Any, tenant: Tenant) -> None:
        # Set session-level tenant context
        # Because RLS policies reference this variable, it must be set
        # before any queries execute
        cursor = conn.cursor()
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, false)",
            (tenant.tenant_id,),
        )
        if tenant.schema_name:
            cursor.execute(f"SET search_path TO {tenant.schema_name}, public")

    def _clear_tenant_context(self, conn: Any) -> None:
        cursor = conn.cursor()
        cursor.execute("SELECT set_config('app.current_tenant_id', '', false)")
        cursor.execute("SET search_path TO public")


class ConnectionPoolExhausted(Exception):
    pass
```

### Cross-Tenant Query Prevention

Beyond RLS, additional safeguards are critical for preventing data leakage:

- **Application-level middleware**: extract tenant ID from the authentication token and inject it into every database call. Never trust client-supplied tenant IDs for data access.
- **Query analysis**: log and audit queries that do not contain a `tenant_id` predicate. Use PostgreSQL's `auto_explain` to capture query plans and verify partition pruning.
- **Separate credentials**: each tenant schema should have a dedicated database role with permissions limited to that schema. **Therefore**, even SQL injection cannot access another tenant's data.

### Performance Considerations at Scale

As tenant count grows into the thousands, several performance challenges emerge:

- **Connection exhaustion**: 5,000 tenants with 5 connections each requires 25,000 connections, far exceeding any database's capacity. **Best practice**: use PgBouncer in transaction-mode pooling with a shared pool, and set tenant context at the transaction level rather than the session level.
- **Noisy neighbor isolation**: one tenant running expensive queries can starve others. Use PostgreSQL's `statement_timeout` and resource groups (in enterprise distributions) to enforce per-tenant limits.
- **Index bloat**: shared tables with a `tenant_id` prefix on every index create wider indexes. **However**, partitioning by `tenant_id` (using PostgreSQL declarative partitioning) enables partition pruning that effectively gives each tenant its own index segments.

### Summary and Key Takeaways

- **Shared schema with RLS** is the most cost-effective approach for most SaaS applications. PostgreSQL RLS provides database-enforced isolation that protects against application bugs.
- **Schema-per-tenant** offers stronger isolation but scales poorly beyond hundreds of tenants **because** migrations must be applied to every schema individually.
- **Connection pooling must be tenant-aware**: always clear session state when returning connections to the pool. A single leaked tenant context is a data breach.
- **Defense in depth**: combine RLS policies, application middleware, query auditing, and per-tenant database roles. No single layer is sufficient.
- The fundamental **trade-off** is isolation strength versus operational cost. Start with shared schema and RLS, and offer schema-per-tenant as a premium feature for enterprise customers.
- **Monitor per-tenant resource usage**: track query counts, connection usage, and storage consumption per tenant to identify noisy neighbors before they impact other customers.
""",
    ),
    (
        "database/distributed-transactions-patterns",
        r"""Explain distributed transaction patterns including two-phase commit protocol, the saga pattern for long-running transactions, the transactional outbox pattern for reliable event publishing, compensating transactions for rollback in distributed systems, and idempotency strategies for exactly-once processing semantics.""",
        r"""## Distributed Transaction Patterns: Sagas, Outbox, and Idempotent Processing

**Distributed transactions** are among the hardest problems in software engineering. When a business operation spans multiple services or databases, maintaining consistency requires coordination mechanisms that go far beyond a single database's ACID guarantees. **Because** microservice architectures decompose monolithic databases into per-service data stores, every cross-service operation is inherently a distributed transaction. Understanding the available patterns -- two-phase commit, sagas, outbox, and compensating transactions -- is essential for building reliable distributed systems.

### The CAP Theorem Context

Before diving into patterns, it is critical to understand why distributed transactions are hard. The **CAP theorem** states that a distributed system can provide at most two of three guarantees: Consistency, Availability, and Partition tolerance. Since network partitions are inevitable, you must choose between consistency and availability. Traditional two-phase commit (2PC) chooses consistency at the expense of availability, while saga-based patterns choose availability with eventual consistency. This **trade-off** is fundamental and cannot be engineered away.

### Two-Phase Commit (2PC)

The two-phase commit protocol is the classic solution for distributed transactions. It uses a **coordinator** that orchestrates the transaction across multiple **participants**:

**Phase 1 (Prepare)**: The coordinator asks each participant to prepare (vote YES or NO). Participants acquire locks and write to their local transaction log but do not commit.

**Phase 2 (Commit/Abort)**: If all participants voted YES, the coordinator sends COMMIT. If any voted NO, the coordinator sends ABORT and all participants roll back.

```python
from dataclasses import dataclass, field
from typing import Optional, Protocol
from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class Vote(Enum):
    YES = "yes"
    NO = "no"
    TIMEOUT = "timeout"


class TransactionState(Enum):
    INITIATED = "initiated"
    PREPARING = "preparing"
    PREPARED = "prepared"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ABORTING = "aborting"
    ABORTED = "aborted"


class Participant(Protocol):
    # Protocol defining what a 2PC participant must implement
    def prepare(self, transaction_id: UUID) -> Vote: ...
    def commit(self, transaction_id: UUID) -> bool: ...
    def abort(self, transaction_id: UUID) -> bool: ...


@dataclass
class TransactionLog:
    # Durable transaction log for crash recovery
    # Best practice: write log entries BEFORE sending messages
    # because the log is the source of truth for recovery
    transaction_id: UUID
    state: TransactionState
    participants: list[str]
    votes: dict[str, Vote] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TwoPhaseCommitCoordinator:
    # Coordinates a distributed transaction using 2PC
    # Pitfall: if the coordinator crashes between Phase 1 and Phase 2,
    # all participants are stuck holding locks (the "blocking" problem)
    # Therefore, 2PC should only be used when all participants are
    # within the same trust boundary and network partition is rare

    def __init__(self, participants: dict[str, Participant]) -> None:
        self.participants = participants
        self.logs: dict[UUID, TransactionLog] = {}

    def execute(self, transaction_id: Optional[UUID] = None) -> bool:
        tx_id = transaction_id or uuid4()
        log = TransactionLog(
            transaction_id=tx_id,
            state=TransactionState.PREPARING,
            participants=list(self.participants.keys()),
        )
        self.logs[tx_id] = log

        # Phase 1: Prepare
        all_yes = True
        for name, participant in self.participants.items():
            try:
                vote = participant.prepare(tx_id)
                log.votes[name] = vote
                if vote != Vote.YES:
                    all_yes = False
                    logger.warning(f"Participant {name} voted {vote.value}")
                    break
            except Exception as e:
                log.votes[name] = Vote.TIMEOUT
                all_yes = False
                logger.error(f"Participant {name} failed during prepare: {e}")
                break

        # Phase 2: Commit or Abort
        if all_yes:
            log.state = TransactionState.COMMITTING
            for name, participant in self.participants.items():
                # Common mistake: not retrying commit on failure
                # because a YES vote is a PROMISE to commit
                success = participant.commit(tx_id)
                if not success:
                    logger.critical(
                        f"Participant {name} failed to commit after YES vote. "
                        f"Manual intervention required for tx {tx_id}"
                    )
            log.state = TransactionState.COMMITTED
            return True
        else:
            log.state = TransactionState.ABORTING
            for name, participant in self.participants.items():
                if name in log.votes and log.votes[name] == Vote.YES:
                    participant.abort(tx_id)
            log.state = TransactionState.ABORTED
            return False
```

**However**, 2PC has critical drawbacks: it is a **blocking protocol** (participants hold locks while waiting for the coordinator's decision), it has a single point of failure (the coordinator), and it reduces availability during network partitions. **Therefore**, modern distributed systems overwhelmingly prefer saga-based patterns.

### The Saga Pattern

A saga is a sequence of local transactions where each step has a corresponding **compensating transaction** that undoes its effect. If any step fails, the previously completed steps are rolled back by executing their compensations in reverse order.

There are two saga orchestration styles:

- **Choreography**: each service publishes events and reacts to events from other services. No central coordinator, but harder to understand and debug.
- **Orchestration**: a central saga orchestrator directs each participant. Easier to understand and monitor, but introduces a single point that must be highly available.

```python
from abc import ABC, abstractmethod
from typing import Callable, Any


@dataclass
class SagaStep:
    # A single step in a saga with its compensating action
    name: str
    action: Callable[..., Any]
    compensation: Callable[..., Any]
    max_retries: int = 3
    timeout_seconds: float = 30.0


class SagaOrchestrator:
    # Executes a saga with automatic compensation on failure
    # Best practice: log every step execution for debugging
    # because distributed failures are notoriously hard to reproduce

    def __init__(self, saga_id: str, steps: list[SagaStep]) -> None:
        self.saga_id = saga_id
        self.steps = steps
        self.completed_steps: list[SagaStep] = []
        self.state: str = "pending"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        self.state = "running"
        logger.info(f"Saga {self.saga_id} starting with {len(self.steps)} steps")

        for step in self.steps:
            try:
                logger.info(f"Saga {self.saga_id}: executing step '{step.name}'")
                result = await self._execute_with_retry(step, context)
                context[f"{step.name}_result"] = result
                self.completed_steps.append(step)
            except Exception as e:
                logger.error(
                    f"Saga {self.saga_id}: step '{step.name}' failed: {e}. "
                    f"Initiating compensation for {len(self.completed_steps)} steps."
                )
                await self._compensate(context)
                self.state = "compensated"
                raise SagaFailedError(
                    f"Saga {self.saga_id} failed at step '{step.name}': {e}"
                ) from e

        self.state = "completed"
        logger.info(f"Saga {self.saga_id} completed successfully")
        return context

    async def _execute_with_retry(
        self, step: SagaStep, context: dict[str, Any]
    ) -> Any:
        last_error = None
        for attempt in range(1, step.max_retries + 1):
            try:
                return await step.action(context)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Step '{step.name}' attempt {attempt}/{step.max_retries} failed: {e}"
                )
        raise last_error

    async def _compensate(self, context: dict[str, Any]) -> None:
        # Execute compensations in reverse order
        # Pitfall: compensations can also fail
        # Therefore, compensations must be idempotent and retryable
        for step in reversed(self.completed_steps):
            try:
                logger.info(f"Saga {self.saga_id}: compensating step '{step.name}'")
                await step.compensation(context)
            except Exception as e:
                logger.critical(
                    f"Saga {self.saga_id}: compensation for '{step.name}' failed: {e}. "
                    f"Manual intervention required."
                )


class SagaFailedError(Exception):
    pass
```

### The Transactional Outbox Pattern

A **common mistake** in event-driven architectures is publishing an event and updating the database in separate operations. If the database write succeeds but the event publish fails (or vice versa), the system enters an inconsistent state. The **transactional outbox pattern** solves this by writing the event to an "outbox" table within the same database transaction as the business data change.

A separate process (the **relay** or **poller**) reads the outbox table and publishes events to the message broker. **Because** both the business data and the outbox entry are in the same transaction, they are atomically committed or rolled back together.

```python
import json
from typing import Any


@dataclass
class OutboxMessage:
    # Message stored in the outbox table
    # Written in the same transaction as the business data
    id: UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    published_at: Optional[datetime] = None
    retry_count: int = 0


class TransactionalOutbox:
    # Implements the outbox pattern for reliable event publishing
    # Best practice: use a dedicated outbox table per aggregate type
    # to avoid contention on a single outbox table

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def save_with_event(
        self,
        business_sql: str,
        business_params: tuple,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        event_payload: dict,
    ) -> UUID:
        # Execute business logic and write outbox entry in ONE transaction
        # This is the key insight: atomic write guarantees consistency
        message_id = uuid4()
        cursor = self.connection.cursor()

        try:
            # Business operation
            cursor.execute(business_sql, business_params)

            # Outbox entry in the SAME transaction
            outbox_sql = (
                "INSERT INTO outbox "
                "(id, aggregate_type, aggregate_id, event_type, payload, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)"
            )
            cursor.execute(outbox_sql, (
                str(message_id),
                aggregate_type,
                aggregate_id,
                event_type,
                json.dumps(event_payload),
                datetime.now(timezone.utc),
            ))

            self.connection.commit()
            return message_id

        except Exception:
            self.connection.rollback()
            raise


class OutboxRelay:
    # Polls the outbox table and publishes messages to the broker
    # Trade-off: polling introduces latency vs CDC-based approaches
    # However, polling is simpler and works with any database

    def __init__(
        self,
        connection: Any,
        publisher: Any,
        batch_size: int = 100,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.connection = connection
        self.publisher = publisher
        self.batch_size = batch_size
        self.poll_interval_seconds = poll_interval_seconds

    def poll_and_publish(self) -> int:
        cursor = self.connection.cursor()
        # Select unpublished messages ordered by creation time
        select_sql = (
            "SELECT id, aggregate_type, aggregate_id, event_type, payload "
            "FROM outbox "
            "WHERE published_at IS NULL "
            "ORDER BY created_at ASC "
            "LIMIT %s "
            "FOR UPDATE SKIP LOCKED"
        )
        cursor.execute(select_sql, (self.batch_size,))
        rows = cursor.fetchall()

        published_count = 0
        for row in rows:
            msg_id, agg_type, agg_id, event_type, payload = row
            try:
                self.publisher.publish(
                    topic=f"{agg_type}.{event_type}",
                    key=agg_id,
                    value=payload,
                )
                update_sql = (
                    "UPDATE outbox SET published_at = %s WHERE id = %s"
                )
                cursor.execute(update_sql, (datetime.now(timezone.utc), msg_id))
                published_count += 1
            except Exception as e:
                logger.error(f"Failed to publish outbox message {msg_id}: {e}")
                update_retry_sql = (
                    "UPDATE outbox SET retry_count = retry_count + 1 WHERE id = %s"
                )
                cursor.execute(update_retry_sql, (msg_id,))

        self.connection.commit()
        return published_count
```

### Idempotency: Achieving Exactly-Once Semantics

In distributed systems, messages can be delivered more than once due to retries, network issues, or consumer restarts. **Therefore**, every operation must be **idempotent** -- producing the same result regardless of how many times it is applied. There are several strategies:

- **Idempotency keys**: the client sends a unique key with each request. The server stores processed keys and returns the cached result for duplicates.
- **Natural idempotency**: design operations so that repeating them is inherently safe (e.g., "set balance to $100" rather than "add $50 to balance").
- **Deduplication tables**: before processing a message, check if its ID exists in a deduplication table. If it does, skip processing.

```python
class IdempotencyStore:
    # Stores idempotency keys to prevent duplicate processing
    # Best practice: include the response in the stored entry
    # so duplicates receive the same response as the original

    def __init__(self, connection: Any, ttl_hours: int = 24) -> None:
        self.connection = connection
        self.ttl_hours = ttl_hours

    def check_and_store(
        self,
        idempotency_key: str,
        handler: Callable[[], dict],
    ) -> dict:
        cursor = self.connection.cursor()

        # Check for existing result
        check_sql = (
            "SELECT response_payload FROM idempotency_keys "
            "WHERE idempotency_key = %s AND created_at > NOW() - INTERVAL '%s hours'"
        )
        cursor.execute(check_sql, (idempotency_key, self.ttl_hours))
        existing = cursor.fetchone()

        if existing is not None:
            logger.info(f"Idempotency key {idempotency_key} already processed")
            return json.loads(existing[0])

        # Process the request
        result = handler()

        # Store the result atomically
        # Pitfall: race condition if two identical requests arrive simultaneously
        # Therefore use INSERT ... ON CONFLICT to handle the race
        store_sql = (
            "INSERT INTO idempotency_keys (idempotency_key, response_payload, created_at) "
            "VALUES (%s, %s, NOW()) "
            "ON CONFLICT (idempotency_key) DO NOTHING"
        )
        cursor.execute(store_sql, (idempotency_key, json.dumps(result)))
        self.connection.commit()

        return result
```

### Compensating Transactions

Unlike database rollbacks, compensations in a saga are **semantic inverses** rather than physical undos. For example, the compensation for "charge credit card $50" is "refund credit card $50", not "undo the charge". This distinction matters **because** the original action may have observable side effects (the customer received a charge notification) that cannot be truly reversed.

**Best practice** for designing compensating transactions:

- Every forward action must have a defined compensation before implementation begins
- Compensations must be idempotent (they may be retried)
- Compensations should be commutative where possible (order should not matter)
- Some actions are **non-compensatable** (sending an email, calling a third-party API). For these, execute them last in the saga to minimize the chance of needing compensation

### Summary and Key Takeaways

- **Two-phase commit** provides strong consistency but is a blocking protocol that reduces availability. Use it only within a single trust boundary (e.g., between databases in the same data center).
- **The saga pattern** breaks distributed transactions into compensatable local transactions. **Best practice**: use orchestration for complex workflows and choreography for simple event chains.
- **The transactional outbox** guarantees atomic data + event publishing by writing both in the same database transaction. A relay process asynchronously publishes events to the message broker.
- **Idempotency is mandatory** in distributed systems. Every service must handle duplicate messages gracefully using idempotency keys or deduplication tables.
- **Compensating transactions** are semantic inverses, not physical undos. **Therefore**, design them carefully and make them idempotent.
- The overarching **trade-off** is between consistency and availability. Choose 2PC when you need strong consistency within a bounded context, and sagas with eventual consistency for cross-service operations.
""",
    ),
]
