"""CQRS and Event Sourcing — command/query separation, event stores."""

PAIRS = [
    (
        "architecture/cqrs",
        "Show CQRS (Command Query Responsibility Segregation): separate read/write models, command handlers, and query projections.",
        '''CQRS — separate read and write paths:

```python
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime
import json


# Commands (write side)
@dataclass
class Command:
    command_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CreateOrder(Command):
    customer_id: str = ""
    items: list[dict] = field(default_factory=list)
    total: float = 0.0


@dataclass
class CancelOrder(Command):
    order_id: str = ""
    reason: str = ""


# Events (what happened)
@dataclass
class DomainEvent:
    event_id: str
    aggregate_id: str
    event_type: str
    data: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)
    version: int = 0


# Command handler (write side)
class OrderCommandHandler:
    def __init__(self, event_store, event_bus):
        self.event_store = event_store
        self.event_bus = event_bus

    async def handle_create_order(self, cmd: CreateOrder) -> str:
        order_id = f"order-{cmd.command_id}"
        events = [
            DomainEvent(
                event_id=f"evt-{cmd.command_id}",
                aggregate_id=order_id,
                event_type="OrderCreated",
                data={"customer_id": cmd.customer_id,
                      "items": cmd.items, "total": cmd.total},
            ),
        ]
        await self.event_store.append(order_id, events)
        for event in events:
            await self.event_bus.publish(event)
        return order_id

    async def handle_cancel_order(self, cmd: CancelOrder):
        # Load current state from events
        events = await self.event_store.load(cmd.order_id)
        state = OrderAggregate.from_events(events)

        if state.status == "cancelled":
            raise ValueError("Order already cancelled")

        cancel_event = DomainEvent(
            event_id=f"evt-{cmd.command_id}",
            aggregate_id=cmd.order_id,
            event_type="OrderCancelled",
            data={"reason": cmd.reason},
            version=state.version + 1,
        )
        await self.event_store.append(cmd.order_id, [cancel_event])
        await self.event_bus.publish(cancel_event)


# Read model (query side)
class OrderReadModel:
    """Denormalized read model optimized for queries."""

    def __init__(self, db):
        self.db = db

    async def handle_event(self, event: DomainEvent):
        """Project events into read model."""
        if event.event_type == "OrderCreated":
            await self.db.execute(
                """INSERT INTO order_view (id, customer_id, total, status, created_at)
                   VALUES ($1, $2, $3, $4, $5)""",
                event.aggregate_id, event.data["customer_id"],
                event.data["total"], "active", event.timestamp,
            )
        elif event.event_type == "OrderCancelled":
            await self.db.execute(
                "UPDATE order_view SET status = $1 WHERE id = $2",
                "cancelled", event.aggregate_id,
            )

    async def get_order(self, order_id: str) -> dict:
        return await self.db.fetchrow(
            "SELECT * FROM order_view WHERE id = $1", order_id
        )

    async def get_customer_orders(self, customer_id: str) -> list:
        return await self.db.fetch(
            "SELECT * FROM order_view WHERE customer_id = $1 ORDER BY created_at DESC",
            customer_id,
        )


class OrderAggregate:
    """Rebuild aggregate state from events."""

    def __init__(self):
        self.status = "new"
        self.items = []
        self.total = 0.0
        self.version = 0

    @classmethod
    def from_events(cls, events: list[DomainEvent]) -> "OrderAggregate":
        agg = cls()
        for event in events:
            agg._apply(event)
        return agg

    def _apply(self, event: DomainEvent):
        self.version = event.version
        if event.event_type == "OrderCreated":
            self.status = "active"
            self.items = event.data["items"]
            self.total = event.data["total"]
        elif event.event_type == "OrderCancelled":
            self.status = "cancelled"
```

Key patterns:
1. **Separate models** — write model optimized for consistency; read model optimized for queries
2. **Command handlers** — validate business rules, emit events, no direct DB writes
3. **Event projection** — events project into denormalized read tables for fast queries
4. **Aggregate from events** — rebuild current state by replaying events; source of truth
5. **Eventual consistency** — read model updates asynchronously; slightly delayed but scalable'''
    ),
    (
        "architecture/event-sourcing",
        "Show event sourcing: event store implementation, snapshots for performance, and event replay for rebuilding state.",
        '''Event sourcing — events as source of truth:

```python
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StoredEvent:
    event_id: str
    stream_id: str
    event_type: str
    data: dict
    metadata: dict = field(default_factory=dict)
    version: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Snapshot:
    stream_id: str
    state: dict
    version: int
    timestamp: datetime


class EventStore:
    """Append-only event store with optimistic concurrency."""

    def __init__(self, db):
        self.db = db

    async def append(self, stream_id: str, events: list[StoredEvent],
                      expected_version: Optional[int] = None):
        """Append events with optimistic concurrency check."""
        async with self.db.acquire() as conn:
            async with conn.transaction():
                if expected_version is not None:
                    current = await conn.fetchval(
                        "SELECT MAX(version) FROM events WHERE stream_id = $1",
                        stream_id,
                    )
                    if current != expected_version:
                        raise ConcurrencyError(
                            f"Expected version {expected_version}, got {current}"
                        )

                for event in events:
                    await conn.execute(
                        """INSERT INTO events (event_id, stream_id, event_type,
                           data, metadata, version, timestamp)
                           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                        event.event_id, stream_id, event.event_type,
                        json.dumps(event.data), json.dumps(event.metadata),
                        event.version, event.timestamp,
                    )

    async def load(self, stream_id: str,
                    from_version: int = 0) -> list[StoredEvent]:
        """Load events for a stream, optionally from a version."""
        rows = await self.db.fetch(
            """SELECT * FROM events WHERE stream_id = $1
               AND version >= $2 ORDER BY version""",
            stream_id, from_version,
        )
        return [StoredEvent(
            event_id=r["event_id"], stream_id=r["stream_id"],
            event_type=r["event_type"], data=json.loads(r["data"]),
            version=r["version"], timestamp=r["timestamp"],
        ) for r in rows]

    async def save_snapshot(self, snapshot: Snapshot):
        await self.db.execute(
            """INSERT INTO snapshots (stream_id, state, version, timestamp)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (stream_id) DO UPDATE
               SET state = $2, version = $3, timestamp = $4""",
            snapshot.stream_id, json.dumps(snapshot.state),
            snapshot.version, snapshot.timestamp,
        )

    async def load_with_snapshot(self, stream_id: str) -> tuple:
        """Load snapshot + events since snapshot for fast rebuild."""
        snapshot = await self.db.fetchrow(
            "SELECT * FROM snapshots WHERE stream_id = $1", stream_id,
        )

        from_version = 0
        state = None
        if snapshot:
            state = json.loads(snapshot["state"])
            from_version = snapshot["version"] + 1

        events = await self.load(stream_id, from_version)
        return state, events

    async def replay_all(self, event_handler, from_position: int = 0):
        """Replay all events for rebuilding read models."""
        rows = await self.db.fetch(
            """SELECT * FROM events WHERE version >= $1
               ORDER BY timestamp, version""",
            from_position,
        )
        for row in rows:
            event = StoredEvent(
                event_id=row["event_id"], stream_id=row["stream_id"],
                event_type=row["event_type"], data=json.loads(row["data"]),
                version=row["version"], timestamp=row["timestamp"],
            )
            await event_handler(event)


class ConcurrencyError(Exception):
    pass
```

Key patterns:
1. **Append-only** — events never modified or deleted; complete audit trail
2. **Optimistic concurrency** — check expected version before append; prevent conflicts
3. **Snapshots** — periodically snapshot state; load snapshot + recent events for speed
4. **Replay** — rebuild any read model by replaying events from the beginning
5. **Event versioning** — monotonic version per stream; detect concurrent modifications'''
    ),
]
