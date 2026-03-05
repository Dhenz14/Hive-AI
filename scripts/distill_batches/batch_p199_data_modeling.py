"""Advanced data modeling — event sourcing schema, CQRS read models, temporal tables, polymorphic associations, EAV pattern, graph-relational hybrid models."""

PAIRS = [
    (
        "databases/event-sourcing-schema",
        "Design an event sourcing schema: event store, aggregate snapshots, event replay, projections, and idempotent event processing.",
        '''Event sourcing schema design with PostgreSQL:

```sql
-- === Core event store schema ===

-- Event store: append-only log of all domain events
CREATE TABLE event_store (
    -- Global ordering (monotonically increasing)
    global_position  BIGSERIAL PRIMARY KEY,
    -- Aggregate identity
    stream_name      VARCHAR(255) NOT NULL,    -- e.g. 'Order-ord_123'
    stream_position  INTEGER NOT NULL,          -- per-stream version
    -- Event metadata
    event_id         UUID NOT NULL DEFAULT gen_random_uuid(),
    event_type       VARCHAR(200) NOT NULL,     -- e.g. 'OrderPlaced'
    -- Event payload (immutable once written)
    data             JSONB NOT NULL,
    metadata         JSONB NOT NULL DEFAULT '{}',
    -- Timestamps
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Enforce ordering within a stream (optimistic concurrency)
    CONSTRAINT uq_stream_position
        UNIQUE (stream_name, stream_position),
    CONSTRAINT uq_event_id
        UNIQUE (event_id)
);

-- Indexes for common access patterns
CREATE INDEX idx_event_store_stream ON event_store (stream_name, stream_position);
CREATE INDEX idx_event_store_type ON event_store (event_type, global_position);
CREATE INDEX idx_event_store_created ON event_store (created_at);


-- === Aggregate snapshots (optimization for long streams) ===
CREATE TABLE aggregate_snapshots (
    stream_name       VARCHAR(255) PRIMARY KEY,
    stream_position   INTEGER NOT NULL,  -- snapshot taken at this version
    snapshot_data     JSONB NOT NULL,
    snapshot_type     VARCHAR(200) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- === Projection tracking (consumer offsets) ===
CREATE TABLE projection_checkpoints (
    projection_name   VARCHAR(200) PRIMARY KEY,
    last_position     BIGINT NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- === Idempotency tracking ===
CREATE TABLE processed_events (
    consumer_name     VARCHAR(200) NOT NULL,
    event_id          UUID NOT NULL,
    processed_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
```

```python
import asyncpg
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Callable


# === Domain Events ===

@dataclass
class DomainEvent:
    """Base class for all domain events."""
    event_type: str
    aggregate_id: str
    data: dict
    metadata: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# Order domain events
class OrderPlaced(DomainEvent):
    def __init__(self, order_id: str, customer_id: str,
                 items: list[dict], total: float, **kwargs):
        super().__init__(
            event_type="OrderPlaced",
            aggregate_id=order_id,
            data={"customer_id": customer_id, "items": items,
                  "total": total},
            **kwargs,
        )

class OrderPaid(DomainEvent):
    def __init__(self, order_id: str, payment_id: str,
                 amount: float, method: str, **kwargs):
        super().__init__(
            event_type="OrderPaid",
            aggregate_id=order_id,
            data={"payment_id": payment_id, "amount": amount,
                  "method": method},
            **kwargs,
        )

class OrderShipped(DomainEvent):
    def __init__(self, order_id: str, tracking_number: str,
                 carrier: str, **kwargs):
        super().__init__(
            event_type="OrderShipped",
            aggregate_id=order_id,
            data={"tracking_number": tracking_number, "carrier": carrier},
            **kwargs,
        )


# === Event Store ===

class EventStore:
    """Append-only event store with optimistic concurrency control."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def append(self, stream_name: str, events: list[DomainEvent],
                     expected_version: int = -1) -> int:
        """Append events to a stream with optimistic concurrency.

        expected_version: the version the caller expects the stream to be at.
        -1 means any version (no concurrency check).
        0 means stream must not exist yet.
        N means stream must be at exactly version N.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Check current version
                current = await conn.fetchval("""
                    SELECT COALESCE(MAX(stream_position), 0)
                    FROM event_store WHERE stream_name = $1
                """, stream_name)

                if expected_version >= 0 and current != expected_version:
                    raise ConcurrencyError(
                        f"Stream '{stream_name}' at version {current}, "
                        f"expected {expected_version}"
                    )

                # Append events
                position = current
                for event in events:
                    position += 1
                    await conn.execute("""
                        INSERT INTO event_store
                            (stream_name, stream_position, event_id,
                             event_type, data, metadata, created_at)
                        VALUES ($1, $2, $3, $4, $5::JSONB,
                                $6::JSONB, NOW())
                    """, stream_name, position,
                        uuid.UUID(event.event_id),
                        event.event_type,
                        json.dumps(event.data),
                        json.dumps(event.metadata))

                return position  # new stream version

    async def read_stream(self, stream_name: str,
                          from_position: int = 0) -> list[dict]:
        """Read all events for a stream from a given position."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT event_id, event_type, stream_position,
                       data, metadata, created_at
                FROM event_store
                WHERE stream_name = $1
                  AND stream_position > $2
                ORDER BY stream_position
            """, stream_name, from_position)
            return [dict(r) for r in rows]

    async def read_all(self, from_position: int = 0,
                       batch_size: int = 1000,
                       event_types: list[str] = None) -> list[dict]:
        """Read events across all streams (for projections)."""
        async with self.pool.acquire() as conn:
            if event_types:
                rows = await conn.fetch("""
                    SELECT global_position, stream_name, event_id,
                           event_type, stream_position, data,
                           metadata, created_at
                    FROM event_store
                    WHERE global_position > $1
                      AND event_type = ANY($3)
                    ORDER BY global_position
                    LIMIT $2
                """, from_position, batch_size, event_types)
            else:
                rows = await conn.fetch("""
                    SELECT global_position, stream_name, event_id,
                           event_type, stream_position, data,
                           metadata, created_at
                    FROM event_store
                    WHERE global_position > $1
                    ORDER BY global_position
                    LIMIT $2
                """, from_position, batch_size)
            return [dict(r) for r in rows]

    async def save_snapshot(self, stream_name: str,
                            position: int, state: dict,
                            snapshot_type: str):
        """Save aggregate snapshot for fast reconstitution."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO aggregate_snapshots
                    (stream_name, stream_position, snapshot_data, snapshot_type)
                VALUES ($1, $2, $3::JSONB, $4)
                ON CONFLICT (stream_name) DO UPDATE SET
                    stream_position = $2,
                    snapshot_data = $3::JSONB,
                    snapshot_type = $4,
                    created_at = NOW()
            """, stream_name, position, json.dumps(state), snapshot_type)

    async def load_aggregate(self, stream_name: str,
                             apply_fn: Callable) -> tuple[dict, int]:
        """Load aggregate from snapshot + subsequent events."""
        async with self.pool.acquire() as conn:
            # Try snapshot first
            snapshot = await conn.fetchrow("""
                SELECT stream_position, snapshot_data
                FROM aggregate_snapshots
                WHERE stream_name = $1
            """, stream_name)

            if snapshot:
                state = json.loads(snapshot["snapshot_data"])
                from_pos = snapshot["stream_position"]
            else:
                state = {}
                from_pos = 0

            # Apply events after snapshot
            events = await self.read_stream(stream_name, from_pos)
            for event in events:
                state = apply_fn(state, event)

            version = events[-1]["stream_position"] if events else from_pos
            return state, version


class ConcurrencyError(Exception):
    pass


# === Usage ===
async def main():
    pool = await asyncpg.create_pool("postgresql://localhost/eventstore")
    store = EventStore(pool)

    # Append events with optimistic concurrency
    order_id = "ord_12345"
    stream = f"Order-{order_id}"

    version = await store.append(stream, [
        OrderPlaced(order_id, "cust_42",
                    items=[{"sku": "W001", "qty": 2, "price": 29.99}],
                    total=59.98),
    ], expected_version=0)  # stream must be new

    version = await store.append(stream, [
        OrderPaid(order_id, "pay_789", amount=59.98, method="stripe"),
    ], expected_version=version)

    # Rebuild aggregate state from events
    def apply_order_event(state: dict, event: dict) -> dict:
        if event["event_type"] == "OrderPlaced":
            return {**event["data"], "status": "placed"}
        elif event["event_type"] == "OrderPaid":
            return {**state, "status": "paid", **event["data"]}
        elif event["event_type"] == "OrderShipped":
            return {**state, "status": "shipped", **event["data"]}
        return state

    order_state, current_version = await store.load_aggregate(
        stream, apply_order_event
    )
```

Key patterns:
1. **Append-only store** -- events are never modified or deleted; the complete history is the source of truth; current state is derived by replaying events
2. **Optimistic concurrency** -- `expected_version` check prevents conflicting writes to the same aggregate; the UNIQUE constraint on (stream_name, stream_position) is the safety net
3. **Snapshots** -- for aggregates with thousands of events, snapshot the state periodically; rebuild = snapshot + events since snapshot
4. **Global position** -- `BIGSERIAL` provides a total ordering across all streams; projections use this as a cursor to process events in order
5. **Idempotent consumers** -- track processed event_ids per consumer in `processed_events` table; skip duplicates on reprocessing'''
    ),
    (
        "databases/cqrs-read-models",
        "Implement CQRS read models: projection builders, materialized views from events, eventual consistency patterns, and query-optimized read stores.",
        '''CQRS read model projections built from event streams:

```python
import asyncpg
import json
import logging
from abc import ABC, abstractmethod
from typing import Callable

logger = logging.getLogger(__name__)


class Projection(ABC):
    """Base class for CQRS read model projections.

    A projection subscribes to events and builds a query-optimized
    read model. Each projection maintains its own checkpoint.
    """

    def __init__(self, pool: asyncpg.Pool, name: str):
        self.pool = pool
        self.name = name

    @abstractmethod
    async def handle_event(self, conn: asyncpg.Connection,
                           event: dict):
        """Process a single event and update the read model."""
        pass

    async def get_checkpoint(self) -> int:
        """Get the last processed global position."""
        async with self.pool.acquire() as conn:
            pos = await conn.fetchval("""
                SELECT last_position FROM projection_checkpoints
                WHERE projection_name = $1
            """, self.name)
            return pos or 0

    async def advance_checkpoint(self, conn: asyncpg.Connection,
                                 position: int):
        """Update checkpoint within the same transaction as the projection."""
        await conn.execute("""
            INSERT INTO projection_checkpoints
                (projection_name, last_position, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (projection_name) DO UPDATE SET
                last_position = $2, updated_at = NOW()
        """, self.name, position)

    async def process_events(self, events: list[dict]):
        """Process a batch of events with transactional checkpoint."""
        for event in events:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Check idempotency
                    exists = await conn.fetchval("""
                        SELECT 1 FROM processed_events
                        WHERE consumer_name = $1 AND event_id = $2
                    """, self.name, event["event_id"])

                    if exists:
                        continue  # already processed

                    await self.handle_event(conn, event)

                    await conn.execute("""
                        INSERT INTO processed_events
                            (consumer_name, event_id)
                        VALUES ($1, $2)
                    """, self.name, event["event_id"])

                    await self.advance_checkpoint(
                        conn, event["global_position"]
                    )


class OrderSummaryProjection(Projection):
    """Read model: order summaries for customer dashboard."""

    def __init__(self, pool: asyncpg.Pool):
        super().__init__(pool, "order-summary")

    async def setup(self):
        """Create the read model table."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS read_order_summaries (
                    order_id        VARCHAR(100) PRIMARY KEY,
                    customer_id     VARCHAR(100) NOT NULL,
                    status          VARCHAR(50) NOT NULL,
                    total           DECIMAL(12, 2),
                    item_count      INTEGER,
                    payment_method  VARCHAR(50),
                    tracking_number VARCHAR(100),
                    carrier         VARCHAR(50),
                    placed_at       TIMESTAMPTZ,
                    paid_at         TIMESTAMPTZ,
                    shipped_at      TIMESTAMPTZ,
                    last_updated    TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_order_summary_customer
                    ON read_order_summaries(customer_id, placed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_order_summary_status
                    ON read_order_summaries(status);
            """)

    async def handle_event(self, conn: asyncpg.Connection,
                           event: dict):
        data = event["data"]
        order_id = event["stream_name"].replace("Order-", "")

        if event["event_type"] == "OrderPlaced":
            await conn.execute("""
                INSERT INTO read_order_summaries
                    (order_id, customer_id, status, total,
                     item_count, placed_at, last_updated)
                VALUES ($1, $2, 'placed', $3, $4, $5, NOW())
                ON CONFLICT (order_id) DO UPDATE SET
                    status = 'placed', total = $3,
                    item_count = $4, placed_at = $5, last_updated = NOW()
            """, order_id, data["customer_id"],
                data["total"],
                len(data.get("items", [])),
                event["created_at"])

        elif event["event_type"] == "OrderPaid":
            await conn.execute("""
                UPDATE read_order_summaries SET
                    status = 'paid',
                    payment_method = $2,
                    paid_at = $3,
                    last_updated = NOW()
                WHERE order_id = $1
            """, order_id, data.get("method"),
                event["created_at"])

        elif event["event_type"] == "OrderShipped":
            await conn.execute("""
                UPDATE read_order_summaries SET
                    status = 'shipped',
                    tracking_number = $2,
                    carrier = $3,
                    shipped_at = $4,
                    last_updated = NOW()
                WHERE order_id = $1
            """, order_id, data.get("tracking_number"),
                data.get("carrier"), event["created_at"])

        elif event["event_type"] == "OrderCancelled":
            await conn.execute("""
                UPDATE read_order_summaries SET
                    status = 'cancelled',
                    last_updated = NOW()
                WHERE order_id = $1
            """, order_id)


class CustomerStatsProjection(Projection):
    """Read model: aggregated customer statistics."""

    def __init__(self, pool: asyncpg.Pool):
        super().__init__(pool, "customer-stats")

    async def setup(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS read_customer_stats (
                    customer_id     VARCHAR(100) PRIMARY KEY,
                    total_orders    INTEGER DEFAULT 0,
                    total_spent     DECIMAL(12, 2) DEFAULT 0,
                    avg_order_value DECIMAL(12, 2) DEFAULT 0,
                    first_order_at  TIMESTAMPTZ,
                    last_order_at   TIMESTAMPTZ,
                    last_updated    TIMESTAMPTZ DEFAULT NOW()
                );
            """)

    async def handle_event(self, conn: asyncpg.Connection,
                           event: dict):
        data = event["data"]

        if event["event_type"] == "OrderPlaced":
            await conn.execute("""
                INSERT INTO read_customer_stats
                    (customer_id, total_orders, total_spent,
                     avg_order_value, first_order_at, last_order_at)
                VALUES ($1, 1, $2, $2, $3, $3)
                ON CONFLICT (customer_id) DO UPDATE SET
                    total_orders = read_customer_stats.total_orders + 1,
                    total_spent = read_customer_stats.total_spent + $2,
                    avg_order_value = (read_customer_stats.total_spent + $2)
                        / (read_customer_stats.total_orders + 1),
                    last_order_at = $3,
                    last_updated = NOW()
            """, data["customer_id"], data["total"],
                event["created_at"])


class ProjectionRunner:
    """Runs all projections, catching up from their checkpoints."""

    def __init__(self, pool: asyncpg.Pool, event_store):
        self.pool = pool
        self.store = event_store
        self.projections: list[Projection] = []

    def register(self, projection: Projection):
        self.projections.append(projection)

    async def run_catch_up(self, batch_size: int = 500):
        """Catch up all projections to the latest events."""
        for projection in self.projections:
            checkpoint = await projection.get_checkpoint()
            logger.info(
                f"Catching up '{projection.name}' from position {checkpoint}"
            )

            while True:
                events = await self.store.read_all(
                    from_position=checkpoint,
                    batch_size=batch_size,
                )
                if not events:
                    break

                await projection.process_events(events)
                checkpoint = events[-1]["global_position"]

    async def rebuild_projection(self, projection: Projection):
        """Rebuild a projection from scratch (reset + replay all events)."""
        logger.warning(f"Rebuilding projection '{projection.name}'")

        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM projection_checkpoints
                WHERE projection_name = $1
            """, projection.name)
            await conn.execute("""
                DELETE FROM processed_events
                WHERE consumer_name = $1
            """, projection.name)

        await projection.setup()

        checkpoint = 0
        total = 0
        while True:
            events = await self.store.read_all(
                from_position=checkpoint, batch_size=1000
            )
            if not events:
                break
            await projection.process_events(events)
            checkpoint = events[-1]["global_position"]
            total += len(events)

        logger.info(f"Rebuild complete: {total} events replayed")


# === Usage ===
async def main():
    pool = await asyncpg.create_pool("postgresql://localhost/eventstore")

    orders = OrderSummaryProjection(pool)
    stats = CustomerStatsProjection(pool)
    await orders.setup()
    await stats.setup()

    runner = ProjectionRunner(pool, event_store=None)  # inject store
    runner.register(orders)
    runner.register(stats)
    await runner.run_catch_up()

    # Query read models (fast, denormalized)
    async with pool.acquire() as conn:
        recent = await conn.fetch("""
            SELECT * FROM read_order_summaries
            WHERE customer_id = $1 ORDER BY placed_at DESC LIMIT 10
        """, "cust_42")
```

Key patterns:
1. **Separate read/write models** -- write side appends events; read side builds denormalized tables optimized for specific queries; different schemas for different needs
2. **Idempotent processing** -- track processed event_ids per projection; safe to replay events after crashes without double-counting
3. **Transactional checkpoint** -- read model update + checkpoint advance happen in one transaction; no gap between "processed" and "recorded as processed"
4. **Projection rebuild** -- reset checkpoint to 0, truncate read model, replay all events; enables schema changes without data migration
5. **Multiple projections** -- same event stream feeds OrderSummary (customer dashboard), CustomerStats (analytics), search index, etc.; each independently paced'''
    ),
    (
        "databases/temporal-tables",
        "Implement temporal tables in PostgreSQL: system-versioned tables, bitemporal data, time-travel queries, and history tracking.",
        '''Temporal tables for time-travel queries and audit history:

```sql
-- === System-versioned temporal table (automatic history tracking) ===

-- Main table: current state
CREATE TABLE employees (
    employee_id     SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    department      VARCHAR(100),
    salary          DECIMAL(12, 2),
    title           VARCHAR(200),
    manager_id      INTEGER REFERENCES employees(employee_id),
    -- System time columns (managed automatically)
    sys_period      TSTZRANGE NOT NULL DEFAULT tstzrange(NOW(), NULL)
);

-- History table: automatic copies of old rows
CREATE TABLE employees_history (
    LIKE employees INCLUDING ALL
);

-- Remove unique constraints from history (allow duplicates)
ALTER TABLE employees_history DROP CONSTRAINT IF EXISTS employees_history_email_key;
ALTER TABLE employees_history DROP CONSTRAINT IF EXISTS employees_history_pkey;
ALTER TABLE employees_history ADD PRIMARY KEY (employee_id, sys_period);

-- Versioning trigger: copies old row to history on UPDATE/DELETE
CREATE OR REPLACE FUNCTION versioning_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
        -- Close the old row's time range
        OLD.sys_period = tstzrange(
            lower(OLD.sys_period), NOW(), '[)'
        );
        INSERT INTO employees_history VALUES (OLD.*);
    END IF;

    IF TG_OP = 'UPDATE' THEN
        NEW.sys_period = tstzrange(NOW(), NULL);
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER employees_versioning
    BEFORE UPDATE OR DELETE ON employees
    FOR EACH ROW EXECUTE FUNCTION versioning_trigger();


-- === Time-travel queries ===

-- Current state
SELECT * FROM employees WHERE department = 'Engineering';

-- State at a specific point in time
CREATE OR REPLACE FUNCTION employees_at(query_time TIMESTAMPTZ)
RETURNS SETOF employees AS $$
    SELECT * FROM employees
    WHERE sys_period @> query_time
    UNION ALL
    SELECT * FROM employees_history
    WHERE sys_period @> query_time;
$$ LANGUAGE SQL STABLE;

-- Usage: what was the Engineering team on June 15?
SELECT * FROM employees_at('2025-06-15 12:00:00+00')
WHERE department = 'Engineering'
ORDER BY name;


-- === Complete change history for an entity ===
SELECT
    employee_id,
    name,
    department,
    salary,
    title,
    lower(sys_period) AS valid_from,
    upper(sys_period) AS valid_until,
    CASE WHEN upper(sys_period) IS NULL
         THEN 'current' ELSE 'historical' END AS status
FROM (
    SELECT * FROM employees WHERE employee_id = 42
    UNION ALL
    SELECT * FROM employees_history WHERE employee_id = 42
) all_versions
ORDER BY lower(sys_period) DESC;


-- === Bitemporal: system time + application (valid) time ===

CREATE TABLE contracts (
    contract_id     SERIAL,
    employee_id     INTEGER NOT NULL,
    position_title  VARCHAR(200) NOT NULL,
    annual_salary   DECIMAL(12, 2) NOT NULL,
    department      VARCHAR(100),

    -- Application time: when the contract is valid in the real world
    valid_from      DATE NOT NULL,
    valid_to        DATE NOT NULL DEFAULT '9999-12-31',

    -- System time: when we recorded this in the database
    sys_period      TSTZRANGE NOT NULL DEFAULT tstzrange(NOW(), NULL),

    PRIMARY KEY (contract_id, sys_period),
    CHECK (valid_from < valid_to)
);

CREATE TABLE contracts_history (LIKE contracts INCLUDING ALL);

CREATE TRIGGER contracts_versioning
    BEFORE UPDATE OR DELETE ON contracts
    FOR EACH ROW EXECUTE FUNCTION versioning_trigger();


-- Bitemporal query: "What did we KNOW about the contract
-- that was VALID on June 1, as of our records on July 15?"
SELECT *
FROM (
    SELECT * FROM contracts
    WHERE sys_period @> '2025-07-15'::TIMESTAMPTZ
    UNION ALL
    SELECT * FROM contracts_history
    WHERE sys_period @> '2025-07-15'::TIMESTAMPTZ
) AS known_at_july15
WHERE valid_from <= '2025-06-01'
  AND valid_to > '2025-06-01'
  AND employee_id = 42;


-- === Salary change audit with computed diffs ===
WITH salary_timeline AS (
    SELECT
        employee_id, name, salary,
        lower(sys_period) AS changed_at,
        LAG(salary) OVER (
            PARTITION BY employee_id ORDER BY lower(sys_period)
        ) AS previous_salary
    FROM (
        SELECT * FROM employees WHERE employee_id = 42
        UNION ALL
        SELECT * FROM employees_history WHERE employee_id = 42
    ) all_versions
)
SELECT
    changed_at, name, previous_salary,
    salary AS new_salary,
    salary - previous_salary AS change_amount,
    ROUND(
        (salary - previous_salary) / NULLIF(previous_salary, 0) * 100, 1
    ) AS change_pct
FROM salary_timeline
WHERE previous_salary IS NOT NULL
ORDER BY changed_at DESC;


-- === Indexes for temporal queries ===
CREATE INDEX idx_employees_history_period
    ON employees_history USING GIST (sys_period);
CREATE INDEX idx_employees_history_id
    ON employees_history (employee_id, sys_period);
CREATE INDEX idx_contracts_valid
    ON contracts (employee_id, valid_from, valid_to);
```

Key patterns:
1. **System-versioned tables** -- trigger automatically copies old row to history on UPDATE/DELETE; `sys_period` tstzrange tracks when each version was active in the database
2. **Time-travel queries** -- `sys_period @> timestamp` finds the version valid at that time; UNION current + history tables for complete view
3. **Bitemporal** -- two time dimensions: `valid_from/valid_to` (real-world validity) and `sys_period` (database recording time); answers "what did we know, when?"
4. **GiST index on tstzrange** -- `USING GIST (sys_period)` enables efficient range containment queries (`@>` operator)
5. **Immutable history** -- history table is append-only; current table trigger handles all versioning; no application code changes needed for basic time-travel'''
    ),
    (
        "databases/polymorphic-associations",
        "Implement polymorphic associations in SQL: single-table inheritance, class-table inheritance, exclusive belongs-to, and the discriminator pattern.",
        '''Polymorphic association patterns for relational databases:

```sql
-- === Pattern 1: Single Table Inheritance (STI) ===
-- All types share one table. Simple queries, wasted NULLs.

CREATE TABLE notifications (
    notification_id  SERIAL PRIMARY KEY,
    notification_type VARCHAR(50) NOT NULL,  -- discriminator

    -- Common fields
    recipient_id     INTEGER NOT NULL,
    title            VARCHAR(200) NOT NULL,
    body             TEXT,
    is_read          BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMPTZ DEFAULT NOW(),

    -- Email-specific (NULL for non-email)
    email_to         VARCHAR(255),
    email_subject    VARCHAR(500),
    email_sent_at    TIMESTAMPTZ,

    -- SMS-specific
    phone_number     VARCHAR(20),
    sms_provider     VARCHAR(50),

    -- Push-specific
    device_token     VARCHAR(500),
    push_badge_count INTEGER,

    -- Slack-specific
    slack_channel    VARCHAR(100),
    slack_thread_ts  VARCHAR(50),

    CONSTRAINT valid_notification_type
        CHECK (notification_type IN ('email', 'sms', 'push', 'slack'))
);

-- Partial indexes: only index rows of each type
CREATE INDEX idx_notif_email ON notifications (email_to, created_at)
    WHERE notification_type = 'email';
CREATE INDEX idx_notif_sms ON notifications (phone_number, created_at)
    WHERE notification_type = 'sms';
CREATE INDEX idx_notif_recipient ON notifications
    (recipient_id, created_at DESC);


-- === Pattern 2: Class Table Inheritance (CTI) ===
-- Base table + per-type extension tables. Normalized, needs JOINs.

CREATE TABLE content_items (
    content_id       SERIAL PRIMARY KEY,
    content_type     VARCHAR(50) NOT NULL,
    author_id        INTEGER NOT NULL,
    title            VARCHAR(500) NOT NULL,
    status           VARCHAR(20) DEFAULT 'draft',
    published_at     TIMESTAMPTZ,
    view_count       INTEGER DEFAULT 0,
    created_at       TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT valid_content_type
        CHECK (content_type IN ('article', 'video', 'podcast', 'gallery'))
);

CREATE TABLE articles (
    content_id       INTEGER PRIMARY KEY REFERENCES content_items(content_id)
                     ON DELETE CASCADE,
    body             TEXT NOT NULL,
    word_count       INTEGER,
    reading_time_min INTEGER,
    featured_image   VARCHAR(500)
);

CREATE TABLE videos (
    content_id       INTEGER PRIMARY KEY REFERENCES content_items(content_id)
                     ON DELETE CASCADE,
    video_url        VARCHAR(500) NOT NULL,
    duration_seconds INTEGER NOT NULL,
    resolution       VARCHAR(20),
    thumbnail_url    VARCHAR(500),
    transcript       TEXT
);

CREATE TABLE podcasts (
    content_id       INTEGER PRIMARY KEY REFERENCES content_items(content_id)
                     ON DELETE CASCADE,
    audio_url        VARCHAR(500) NOT NULL,
    duration_seconds INTEGER NOT NULL,
    episode_number   INTEGER,
    show_notes       TEXT
);

-- Unified view with LEFT JOINs
CREATE VIEW content_full AS
SELECT
    ci.*,
    a.body AS article_body, a.word_count, a.reading_time_min,
    v.video_url, v.duration_seconds AS video_duration, v.resolution,
    p.audio_url, p.duration_seconds AS podcast_duration, p.episode_number
FROM content_items ci
LEFT JOIN articles a ON ci.content_id = a.content_id
    AND ci.content_type = 'article'
LEFT JOIN videos v ON ci.content_id = v.content_id
    AND ci.content_type = 'video'
LEFT JOIN podcasts p ON ci.content_id = p.content_id
    AND ci.content_type = 'podcast';


-- === Pattern 3: Exclusive Belongs-To ===
-- A comment can belong to exactly one parent type.

-- Option A: Multiple nullable FKs with exclusive constraint
CREATE TABLE comments (
    comment_id       SERIAL PRIMARY KEY,
    author_id        INTEGER NOT NULL,
    body             TEXT NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW(),

    article_id       INTEGER REFERENCES articles(content_id),
    video_id         INTEGER REFERENCES videos(content_id),
    podcast_id       INTEGER REFERENCES podcasts(content_id),

    -- Exactly one FK must be set
    CONSTRAINT one_parent CHECK (
        (article_id IS NOT NULL)::INTEGER +
        (video_id IS NOT NULL)::INTEGER +
        (podcast_id IS NOT NULL)::INTEGER = 1
    )
);

-- Option B: Type + ID pair (no FK enforcement, more flexible)
CREATE TABLE reactions (
    reaction_id      SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL,
    reaction_type    VARCHAR(20) NOT NULL,
    target_type      VARCHAR(50) NOT NULL,  -- 'article', 'video', 'comment'
    target_id        INTEGER NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (user_id, target_type, target_id, reaction_type)
);

CREATE INDEX idx_reactions_target ON reactions (target_type, target_id);


-- === Pattern 4: JSONB for dynamic polymorphism ===

CREATE TABLE audit_log (
    log_id           BIGSERIAL PRIMARY KEY,
    actor_id         INTEGER NOT NULL,
    action           VARCHAR(100) NOT NULL,
    resource_type    VARCHAR(100) NOT NULL,
    resource_id      VARCHAR(100) NOT NULL,
    changes          JSONB NOT NULL DEFAULT '{}',
    context          JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_changes ON audit_log
    USING GIN (changes jsonb_path_ops);
CREATE INDEX idx_audit_resource ON audit_log
    (resource_type, resource_id, created_at DESC);

-- Find all salary changes
SELECT * FROM audit_log
WHERE resource_type = 'employee'
  AND changes ? 'salary'
ORDER BY created_at DESC;
```

| Pattern | Pros | Cons | Best For |
|---|---|---|---|
| STI (single table) | Simple queries, no JOINs | NULL bloat, wide table | Few types, similar fields |
| CTI (class table) | Clean, normalized | Requires JOINs | Many distinct fields per type |
| Exclusive FK | Referential integrity | Fixed set of types | Known, stable type set |
| Type + ID pair | Flexible, extensible | No FK enforcement | Open-ended types |
| JSONB | Maximum flexibility | No schema validation | Audit logs, dynamic data |

Key patterns:
1. **Discriminator column** -- `content_type` tells you which table/fields to use; always index it; add a CHECK constraint for valid values
2. **Partial indexes** -- `WHERE notification_type = 'email'` indexes only email rows; much smaller and faster than full-table indexes
3. **Exclusive constraint** -- `CHECK ((a IS NOT NULL)::INT + (b IS NOT NULL)::INT = 1)` enforces exactly one FK is set; database-level safety
4. **CTI view** -- create a view with LEFT JOINs to all type tables; application queries the view and gets all fields; NULL for inapplicable fields
5. **JSONB for flexibility** -- when you cannot predict the shape of type-specific data, use JSONB with GIN indexes; trade schema enforcement for extensibility'''
    ),
    (
        "databases/eav-and-hybrid-models",
        "Implement the EAV (Entity-Attribute-Value) pattern and graph-relational hybrid models: flexible schemas, attribute indexing, and combining relational + graph in one database.",
        '''EAV pattern and graph-relational hybrid data models:

```sql
-- === Entity-Attribute-Value (EAV) pattern ===
-- For entities with highly variable attributes

-- Core EAV tables
CREATE TABLE entities (
    entity_id       SERIAL PRIMARY KEY,
    entity_type     VARCHAR(100) NOT NULL,
    name            VARCHAR(500),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Attribute definitions (schema registry)
CREATE TABLE attribute_definitions (
    attribute_id    SERIAL PRIMARY KEY,
    entity_type     VARCHAR(100) NOT NULL,
    attribute_name  VARCHAR(200) NOT NULL,
    data_type       VARCHAR(20) NOT NULL,  -- 'string', 'integer', 'decimal', 'boolean', 'date', 'json'
    is_required     BOOLEAN DEFAULT FALSE,
    is_searchable   BOOLEAN DEFAULT TRUE,
    display_order   INTEGER DEFAULT 0,
    validation_rule JSONB,
    UNIQUE (entity_type, attribute_name)
);

-- Attribute values with typed columns for proper indexing
CREATE TABLE attribute_values (
    value_id        BIGSERIAL PRIMARY KEY,
    entity_id       INTEGER NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    attribute_id    INTEGER NOT NULL REFERENCES attribute_definitions(attribute_id),
    value_text      TEXT,
    value_integer   BIGINT,
    value_decimal   DECIMAL(18, 6),
    value_boolean   BOOLEAN,
    value_date      DATE,
    value_json      JSONB,
    UNIQUE (entity_id, attribute_id)
);

-- Typed column indexes for efficient filtering
CREATE INDEX idx_attr_values_entity ON attribute_values (entity_id);
CREATE INDEX idx_attr_values_text ON attribute_values (attribute_id, value_text)
    WHERE value_text IS NOT NULL;
CREATE INDEX idx_attr_values_int ON attribute_values (attribute_id, value_integer)
    WHERE value_integer IS NOT NULL;
CREATE INDEX idx_attr_values_decimal ON attribute_values (attribute_id, value_decimal)
    WHERE value_decimal IS NOT NULL;


-- === EAV query: pivot to columnar format ===
SELECT
    e.entity_id,
    e.name AS product_name,
    MAX(CASE WHEN ad.attribute_name = 'brand' THEN av.value_text END) AS brand,
    MAX(CASE WHEN ad.attribute_name = 'price' THEN av.value_decimal END) AS price,
    MAX(CASE WHEN ad.attribute_name = 'screen_size' THEN av.value_decimal END) AS screen_size,
    MAX(CASE WHEN ad.attribute_name = 'ram_gb' THEN av.value_integer END) AS ram_gb,
    MAX(CASE WHEN ad.attribute_name = 'storage_gb' THEN av.value_integer END) AS storage_gb
FROM entities e
JOIN attribute_values av ON e.entity_id = av.entity_id
JOIN attribute_definitions ad ON av.attribute_id = ad.attribute_id
WHERE e.entity_type = 'product'
GROUP BY e.entity_id, e.name
HAVING MAX(CASE WHEN ad.attribute_name = 'category'
           THEN av.value_text END) = 'laptop'
ORDER BY MAX(CASE WHEN ad.attribute_name = 'price'
             THEN av.value_decimal END);


-- === EAV filter: "laptops with 16GB+ RAM under $1500" ===
SELECT e.entity_id, e.name
FROM entities e
WHERE e.entity_type = 'product'
  AND EXISTS (
      SELECT 1 FROM attribute_values av
      JOIN attribute_definitions ad ON av.attribute_id = ad.attribute_id
      WHERE av.entity_id = e.entity_id
        AND ad.attribute_name = 'ram_gb' AND av.value_integer >= 16
  )
  AND EXISTS (
      SELECT 1 FROM attribute_values av
      JOIN attribute_definitions ad ON av.attribute_id = ad.attribute_id
      WHERE av.entity_id = e.entity_id
        AND ad.attribute_name = 'price' AND av.value_decimal < 1500
  );


-- === JSONB alternative to EAV (simpler for PostgreSQL) ===

CREATE TABLE products_flex (
    product_id      SERIAL PRIMARY KEY,
    product_type    VARCHAR(100) NOT NULL,
    name            VARCHAR(500) NOT NULL,
    price           DECIMAL(12, 2),
    brand           VARCHAR(200),
    -- Variable attributes as JSONB
    attributes      JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- GIN index for attribute queries
CREATE INDEX idx_products_flex_attrs ON products_flex
    USING GIN (attributes jsonb_path_ops);

-- Generated columns for hot attributes (materialized from JSONB)
ALTER TABLE products_flex ADD COLUMN
    ram_gb INTEGER GENERATED ALWAYS AS (
        (attributes->>'ram_gb')::INTEGER
    ) STORED;

CREATE INDEX idx_products_flex_ram ON products_flex (ram_gb)
    WHERE ram_gb IS NOT NULL;

-- Same query, much simpler with JSONB
SELECT product_id, name, price, brand, attributes
FROM products_flex
WHERE product_type = 'laptop'
  AND (attributes->>'ram_gb')::INTEGER >= 16
  AND price < 1500
ORDER BY price;


-- === Graph-relational hybrid (PostgreSQL as both) ===

-- Nodes table
CREATE TABLE graph_nodes (
    node_id         SERIAL PRIMARY KEY,
    node_type       VARCHAR(100) NOT NULL,
    properties      JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Edges table
CREATE TABLE graph_edges (
    edge_id         SERIAL PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES graph_nodes(node_id),
    target_id       INTEGER NOT NULL REFERENCES graph_nodes(node_id),
    edge_type       VARCHAR(100) NOT NULL,
    properties      JSONB NOT NULL DEFAULT '{}',
    weight          DOUBLE PRECISION DEFAULT 1.0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source_id, target_id, edge_type)
);

CREATE INDEX idx_graph_edges_source ON graph_edges (source_id, edge_type);
CREATE INDEX idx_graph_edges_target ON graph_edges (target_id, edge_type);


-- Graph traversal: find all descendants (recursive CTE)
WITH RECURSIVE descendants AS (
    -- Base case: direct children
    SELECT
        target_id AS node_id,
        1 AS depth,
        ARRAY[source_id, target_id] AS path
    FROM graph_edges
    WHERE source_id = 1 AND edge_type = 'MANAGES'

    UNION ALL

    -- Recursive case
    SELECT
        e.target_id,
        d.depth + 1,
        d.path || e.target_id
    FROM graph_edges e
    JOIN descendants d ON e.source_id = d.node_id
    WHERE e.edge_type = 'MANAGES'
      AND d.depth < 10                     -- max depth
      AND NOT e.target_id = ANY(d.path)    -- cycle detection
)
SELECT
    d.node_id, d.depth,
    n.properties->>'name' AS name,
    n.properties->>'title' AS title,
    d.path
FROM descendants d
JOIN graph_nodes n ON d.node_id = n.node_id
ORDER BY d.depth, n.properties->>'name';


-- Shortest path (BFS)
WITH RECURSIVE bfs AS (
    SELECT
        target_id AS node_id,
        1 AS distance,
        ARRAY[source_id, target_id] AS path
    FROM graph_edges
    WHERE source_id = 1

    UNION ALL

    SELECT
        e.target_id,
        b.distance + 1,
        b.path || e.target_id
    FROM graph_edges e
    JOIN bfs b ON e.source_id = b.node_id
    WHERE NOT e.target_id = ANY(b.path)
      AND b.distance < 6
)
SELECT path, distance
FROM bfs
WHERE node_id = 42
ORDER BY distance
LIMIT 1;


-- Combine relational + graph: find people who manage teams
-- in the Engineering department with > 5 direct reports
WITH team_sizes AS (
    SELECT
        source_id AS manager_id,
        COUNT(*) AS direct_reports
    FROM graph_edges
    WHERE edge_type = 'MANAGES'
    GROUP BY source_id
    HAVING COUNT(*) > 5
)
SELECT
    n.properties->>'name' AS manager_name,
    n.properties->>'title' AS title,
    ts.direct_reports,
    n.properties->>'department' AS department
FROM team_sizes ts
JOIN graph_nodes n ON ts.manager_id = n.node_id
WHERE n.properties->>'department' = 'Engineering'
ORDER BY ts.direct_reports DESC;
```

| Pattern | When to Use | Avoid When |
|---|---|---|
| EAV | Truly unknown schema, 100s of optional attributes | Most attributes are common; need complex queries |
| JSONB | Variable attributes, moderate querying needs | Need strict schema enforcement |
| Graph-relational | Need both structured data + relationship traversal | Pure graph or pure relational workloads |
| Generated columns | Frequently filtered JSONB attributes | Attribute set changes constantly |

Key patterns:
1. **Typed value columns** -- EAV with separate `value_text`, `value_integer`, `value_decimal` enables proper indexing and sorting; never store everything as text
2. **JSONB over EAV** -- for PostgreSQL, JSONB with GIN indexes handles most EAV use cases with simpler queries; use generated columns for hot attributes
3. **Attribute definitions** -- a schema registry validates what attributes are allowed per entity type; EAV without it becomes unmanageable chaos
4. **Graph in SQL** -- recursive CTEs handle tree/graph traversal; `ARRAY path + ANY()` detects cycles; works for moderate graphs (millions of edges)
5. **Hybrid approach** -- use relational columns for common fields, JSONB for variable fields, graph edges for relationships; one database, three patterns'''
    ),
]
