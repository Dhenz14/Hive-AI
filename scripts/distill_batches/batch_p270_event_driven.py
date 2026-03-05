"""Event-driven architecture: event sourcing, CQRS, event stores, projections, sagas."""

PAIRS = [
    (
        "architecture/event-sourcing",
        "How do I implement event sourcing in Python with a proper event store, snapshotting, and event replay capabilities?",
        '''Event sourcing stores every state change as an immutable event rather than overwriting current state. This provides a complete audit trail, enables temporal queries, and allows rebuilding state from scratch.

Here is a production-grade event sourcing implementation:

```python
"""Event sourcing framework with snapshotting and replay."""

import json
import uuid
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any, Protocol, TypeVar, Generic, ClassVar
from abc import ABC, abstractmethod
from collections import defaultdict
import asyncio
import asyncpg


# ── Domain Events ──────────────────────────────────────────────

@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    version: int = 0
    aggregate_id: str = ""
    correlation_id: str = ""
    causation_id: str = ""

    @property
    def event_type(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AccountOpened(DomainEvent):
    owner_name: str = ""
    initial_balance: float = 0.0
    account_type: str = "checking"


@dataclass(frozen=True)
class MoneyDeposited(DomainEvent):
    amount: float = 0.0
    description: str = ""


@dataclass(frozen=True)
class MoneyWithdrawn(DomainEvent):
    amount: float = 0.0
    description: str = ""


@dataclass(frozen=True)
class AccountClosed(DomainEvent):
    reason: str = ""
    final_balance: float = 0.0


# ── Event Store ────────────────────────────────────────────────

class EventStore:
    """PostgreSQL-backed event store with optimistic concurrency."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._event_registry: dict[str, type[DomainEvent]] = {}

    def register_event(self, event_cls: type[DomainEvent]) -> None:
        self._event_registry[event_cls.__name__] = event_cls

    async def initialize(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS event_store (
                    global_position  BIGSERIAL PRIMARY KEY,
                    stream_id        TEXT NOT NULL,
                    stream_position  INTEGER NOT NULL,
                    event_type       TEXT NOT NULL,
                    event_data       JSONB NOT NULL,
                    metadata         JSONB DEFAULT '{}',
                    event_id         UUID NOT NULL UNIQUE,
                    timestamp        TIMESTAMPTZ DEFAULT NOW(),
                    checksum         TEXT NOT NULL,
                    UNIQUE (stream_id, stream_position)
                );

                CREATE INDEX IF NOT EXISTS idx_stream_id
                    ON event_store (stream_id, stream_position);
                CREATE INDEX IF NOT EXISTS idx_event_type
                    ON event_store (event_type);
                CREATE INDEX IF NOT EXISTS idx_timestamp
                    ON event_store (timestamp);

                CREATE TABLE IF NOT EXISTS snapshots (
                    stream_id       TEXT PRIMARY KEY,
                    version         INTEGER NOT NULL,
                    state           JSONB NOT NULL,
                    timestamp       TIMESTAMPTZ DEFAULT NOW()
                );
            """)

    def _compute_checksum(self, event_data: dict) -> str:
        raw = json.dumps(event_data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def append(
        self,
        stream_id: str,
        events: list[DomainEvent],
        expected_version: int = -1,
    ) -> int:
        """Append events with optimistic concurrency control."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Check current version
                row = await conn.fetchrow(
                    "SELECT MAX(stream_position) as version "
                    "FROM event_store WHERE stream_id = $1",
                    stream_id,
                )
                current = row["version"] if row["version"] is not None else -1

                if expected_version != -1 and current != expected_version:
                    raise ConcurrencyError(
                        f"Expected version {expected_version}, "
                        f"but stream is at {current}"
                    )

                new_version = current
                for event in events:
                    new_version += 1
                    data = event.to_dict()
                    checksum = self._compute_checksum(data)

                    await conn.execute(
                        """INSERT INTO event_store
                        (stream_id, stream_position, event_type,
                         event_data, event_id, checksum)
                        VALUES ($1, $2, $3, $4, $5, $6)""",
                        stream_id, new_version, event.event_type,
                        json.dumps(data), uuid.UUID(event.event_id),
                        checksum,
                    )

                return new_version

    async def load_stream(
        self,
        stream_id: str,
        from_version: int = 0,
    ) -> list[DomainEvent]:
        """Load all events for a stream from a given version."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT event_type, event_data FROM event_store "
                "WHERE stream_id = $1 AND stream_position >= $2 "
                "ORDER BY stream_position",
                stream_id, from_version,
            )

        events = []
        for row in rows:
            cls = self._event_registry.get(row["event_type"])
            if cls:
                data = json.loads(row["event_data"])
                events.append(cls(**data))
        return events

    async def save_snapshot(
        self, stream_id: str, version: int, state: dict
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO snapshots (stream_id, version, state)
                VALUES ($1, $2, $3)
                ON CONFLICT (stream_id)
                DO UPDATE SET version = $2, state = $3,
                              timestamp = NOW()""",
                stream_id, version, json.dumps(state),
            )

    async def load_snapshot(
        self, stream_id: str
    ) -> tuple[int, dict] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT version, state FROM snapshots "
                "WHERE stream_id = $1", stream_id,
            )
        if row:
            return row["version"], json.loads(row["state"])
        return None


class ConcurrencyError(Exception):
    pass


# ── Aggregate Root ─────────────────────────────────────────────

class AggregateRoot(ABC):
    """Base aggregate root with event sourcing support."""

    SNAPSHOT_INTERVAL: ClassVar[int] = 50

    def __init__(self, aggregate_id: str):
        self.aggregate_id = aggregate_id
        self.version = -1
        self._pending_events: list[DomainEvent] = []

    def apply_event(self, event: DomainEvent) -> None:
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event)
        self.version += 1

    def raise_event(self, event: DomainEvent) -> None:
        self.apply_event(event)
        self._pending_events.append(event)

    def collect_events(self) -> list[DomainEvent]:
        events = self._pending_events.copy()
        self._pending_events.clear()
        return events

    @abstractmethod
    def to_snapshot(self) -> dict: ...

    @abstractmethod
    def from_snapshot(self, state: dict) -> None: ...


# ── Bank Account Aggregate ─────────────────────────────────────

class BankAccount(AggregateRoot):
    def __init__(self, aggregate_id: str):
        super().__init__(aggregate_id)
        self.owner_name = ""
        self.balance = 0.0
        self.is_open = False
        self.account_type = "checking"

    def open(self, owner: str, initial: float, acct_type: str) -> None:
        if self.is_open:
            raise ValueError("Account already open")
        self.raise_event(AccountOpened(
            aggregate_id=self.aggregate_id,
            owner_name=owner,
            initial_balance=initial,
            account_type=acct_type,
        ))

    def deposit(self, amount: float, desc: str = "") -> None:
        if not self.is_open:
            raise ValueError("Account is closed")
        if amount <= 0:
            raise ValueError("Deposit must be positive")
        self.raise_event(MoneyDeposited(
            aggregate_id=self.aggregate_id,
            amount=amount, description=desc,
        ))

    def withdraw(self, amount: float, desc: str = "") -> None:
        if not self.is_open:
            raise ValueError("Account is closed")
        if amount > self.balance:
            raise ValueError("Insufficient funds")
        self.raise_event(MoneyWithdrawn(
            aggregate_id=self.aggregate_id,
            amount=amount, description=desc,
        ))

    # Event handlers
    def _on_AccountOpened(self, e: AccountOpened) -> None:
        self.owner_name = e.owner_name
        self.balance = e.initial_balance
        self.is_open = True
        self.account_type = e.account_type

    def _on_MoneyDeposited(self, e: MoneyDeposited) -> None:
        self.balance += e.amount

    def _on_MoneyWithdrawn(self, e: MoneyWithdrawn) -> None:
        self.balance -= e.amount

    def _on_AccountClosed(self, e: AccountClosed) -> None:
        self.is_open = False

    def to_snapshot(self) -> dict:
        return {
            "owner_name": self.owner_name,
            "balance": self.balance,
            "is_open": self.is_open,
            "account_type": self.account_type,
        }

    def from_snapshot(self, state: dict) -> None:
        self.owner_name = state["owner_name"]
        self.balance = state["balance"]
        self.is_open = state["is_open"]
        self.account_type = state["account_type"]
```

Key design principles:

| Principle | Implementation |
|-----------|---------------|
| Immutable events | Frozen dataclasses with unique IDs |
| Optimistic concurrency | Expected version check on append |
| Data integrity | SHA-256 checksums on every event |
| Efficient rebuild | Snapshotting after N events |
| Temporal queries | Events ordered by global position |
| Audit trail | Complete history with timestamps |

Key patterns to remember:
- Events are facts that happened -- never delete or modify them
- Use optimistic concurrency to prevent write conflicts
- Snapshot periodically (every 50-100 events) to speed up replay
- Register all event types for deserialization
- Separate event application (apply_event) from raising (raise_event)
- Pending events are collected after a command succeeds for persistence
'''
    ),
    (
        "architecture/cqrs",
        "How do I implement CQRS (Command Query Responsibility Segregation) with separate read and write models in Python?",
        '''CQRS separates the write side (commands that change state) from the read side (queries that return data). This enables independent scaling, optimized read models, and eventual consistency.

Here is a comprehensive CQRS implementation:

```python
"""CQRS framework with command bus, query bus, and read model projections."""

import uuid
import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar, Generic, Callable, Awaitable
from abc import ABC, abstractmethod
from collections import defaultdict
import asyncpg
import json


# ── Commands ───────────────────────────────────────────────────

@dataclass(frozen=True)
class Command:
    """Base command -- represents an intent to change state."""
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    correlation_id: str = ""
    user_id: str = ""


@dataclass(frozen=True)
class CreateOrder(Command):
    customer_id: str = ""
    items: tuple = ()  # ((product_id, qty, price), ...)
    shipping_address: str = ""


@dataclass(frozen=True)
class CancelOrder(Command):
    order_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class UpdateOrderStatus(Command):
    order_id: str = ""
    new_status: str = ""


# ── Queries ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Query:
    """Base query -- represents a read request."""
    pass


@dataclass(frozen=True)
class GetOrderById(Query):
    order_id: str = ""


@dataclass(frozen=True)
class GetOrdersByCustomer(Query):
    customer_id: str = ""
    status_filter: str | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class GetOrderStats(Query):
    customer_id: str = ""
    period_days: int = 30


# ── Command Handlers ──────────────────────────────────────────

C = TypeVar("C", bound=Command)
Q = TypeVar("Q", bound=Query)


class CommandHandler(ABC, Generic[C]):
    @abstractmethod
    async def handle(self, command: C) -> dict[str, Any]: ...


class CreateOrderHandler(CommandHandler[CreateOrder]):
    def __init__(self, event_store, event_bus):
        self.event_store = event_store
        self.event_bus = event_bus

    async def handle(self, cmd: CreateOrder) -> dict[str, Any]:
        order_id = str(uuid.uuid4())
        total = sum(qty * price for _, qty, price in cmd.items)

        events = [
            {
                "type": "OrderCreated",
                "data": {
                    "order_id": order_id,
                    "customer_id": cmd.customer_id,
                    "items": [
                        {"product_id": p, "quantity": q, "price": pr}
                        for p, q, pr in cmd.items
                    ],
                    "total": total,
                    "shipping_address": cmd.shipping_address,
                    "status": "pending",
                    "correlation_id": cmd.correlation_id,
                },
            }
        ]

        # Write to event store (write model)
        await self.event_store.append(f"order-{order_id}", events)

        # Publish for read model projection
        for event in events:
            await self.event_bus.publish(event)

        return {"order_id": order_id, "status": "created"}


class CancelOrderHandler(CommandHandler[CancelOrder]):
    def __init__(self, event_store, event_bus):
        self.event_store = event_store
        self.event_bus = event_bus

    async def handle(self, cmd: CancelOrder) -> dict[str, Any]:
        stream = await self.event_store.load_stream(
            f"order-{cmd.order_id}"
        )
        if not stream:
            raise OrderNotFoundError(cmd.order_id)

        current_status = self._derive_status(stream)
        if current_status in ("shipped", "delivered", "cancelled"):
            raise InvalidOperationError(
                f"Cannot cancel order in '{current_status}' status"
            )

        event = {
            "type": "OrderCancelled",
            "data": {
                "order_id": cmd.order_id,
                "reason": cmd.reason,
                "cancelled_by": cmd.user_id,
                "previous_status": current_status,
            },
        }

        await self.event_store.append(
            f"order-{cmd.order_id}", [event],
            expected_version=len(stream) - 1,
        )
        await self.event_bus.publish(event)
        return {"order_id": cmd.order_id, "status": "cancelled"}

    def _derive_status(self, events: list[dict]) -> str:
        status = "unknown"
        for e in events:
            match e["type"]:
                case "OrderCreated":
                    status = "pending"
                case "OrderCancelled":
                    status = "cancelled"
                case "OrderStatusUpdated":
                    status = e["data"]["new_status"]
        return status


# ── Query Handlers (Read Side) ────────────────────────────────

class QueryHandler(ABC, Generic[Q]):
    @abstractmethod
    async def handle(self, query: Q) -> Any: ...


class GetOrderByIdHandler(QueryHandler[GetOrderById]):
    def __init__(self, read_db: asyncpg.Pool):
        self.read_db = read_db

    async def handle(self, query: GetOrderById) -> dict | None:
        async with self.read_db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM orders_read_model WHERE order_id = $1",
                query.order_id,
            )
        if row:
            return dict(row)
        return None


class GetOrdersByCustomerHandler(QueryHandler[GetOrdersByCustomer]):
    def __init__(self, read_db: asyncpg.Pool):
        self.read_db = read_db

    async def handle(self, query: GetOrdersByCustomer) -> dict:
        offset = (query.page - 1) * query.page_size
        async with self.read_db.acquire() as conn:
            where = "WHERE customer_id = $1"
            params: list[Any] = [query.customer_id]
            idx = 2

            if query.status_filter:
                where += f" AND status = ${idx}"
                params.append(query.status_filter)
                idx += 1

            count = await conn.fetchval(
                f"SELECT COUNT(*) FROM orders_read_model {where}",
                *params,
            )

            rows = await conn.fetch(
                f"SELECT * FROM orders_read_model {where} "
                f"ORDER BY created_at DESC "
                f"LIMIT ${idx} OFFSET ${idx + 1}",
                *params, query.page_size, offset,
            )

        return {
            "orders": [dict(r) for r in rows],
            "total": count,
            "page": query.page,
            "page_size": query.page_size,
        }


class GetOrderStatsHandler(QueryHandler[GetOrderStats]):
    def __init__(self, read_db: asyncpg.Pool):
        self.read_db = read_db

    async def handle(self, query: GetOrderStats) -> dict:
        async with self.read_db.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT
                    COUNT(*) as total_orders,
                    SUM(total) as total_spent,
                    AVG(total) as avg_order_value,
                    COUNT(*) FILTER (WHERE status = 'cancelled')
                        as cancelled_orders
                FROM orders_read_model
                WHERE customer_id = $1
                  AND created_at >= NOW() - INTERVAL '$2 days'
                """,
                query.customer_id, query.period_days,
            )
        return dict(row) if row else {}


# ── Buses ──────────────────────────────────────────────────────

class CommandBus:
    """Routes commands to their handlers."""

    def __init__(self):
        self._handlers: dict[type, CommandHandler] = {}

    def register(self, cmd_type: type[Command], handler: CommandHandler):
        self._handlers[cmd_type] = handler

    async def dispatch(self, command: Command) -> Any:
        handler = self._handlers.get(type(command))
        if not handler:
            raise ValueError(f"No handler for {type(command).__name__}")
        return await handler.handle(command)


class QueryBus:
    """Routes queries to their handlers."""

    def __init__(self):
        self._handlers: dict[type, QueryHandler] = {}

    def register(self, query_type: type[Query], handler: QueryHandler):
        self._handlers[query_type] = handler

    async def dispatch(self, query: Query) -> Any:
        handler = self._handlers.get(type(query))
        if not handler:
            raise ValueError(f"No handler for {type(query).__name__}")
        return await handler.handle(query)


class EventBus:
    """Publishes domain events to subscribers."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(
        self, event_type: str, handler: Callable[[dict], Awaitable[None]]
    ):
        self._subscribers[event_type].append(handler)

    async def publish(self, event: dict) -> None:
        for handler in self._subscribers.get(event["type"], []):
            await handler(event)
        for handler in self._subscribers.get("*", []):
            await handler(event)


class OrderNotFoundError(Exception):
    pass

class InvalidOperationError(Exception):
    pass
```

CQRS architecture comparison:

| Aspect | Traditional CRUD | CQRS |
|--------|-----------------|------|
| Data model | Single model for reads/writes | Separate read/write models |
| Scaling | Scale everything together | Scale reads and writes independently |
| Query optimization | Compromise between read/write | Read model optimized for queries |
| Complexity | Simple | Higher (eventual consistency) |
| Consistency | Strong | Eventual (read model lags) |
| Audit trail | Must add separately | Built-in with event sourcing |

Key patterns:
- Commands represent intent (imperative: "CreateOrder") while events represent facts (past tense: "OrderCreated")
- Command bus dispatches to exactly one handler; event bus fans out to many subscribers
- Read models are disposable projections -- you can rebuild them from events
- Use correlation IDs to trace a request across command and event handling
- Validate business rules in command handlers before emitting events
- Keep command handlers focused on one aggregate at a time
'''
    ),
    (
        "architecture/event-projections",
        "How do I build read model projections that consume events and maintain denormalized query-optimized views?",
        '''Projections consume domain events and build denormalized read models optimized for specific query patterns. They are the bridge between the write side (event store) and the read side (query handlers).

Here is a robust projection system:

```python
"""Event projection framework for building and rebuilding read models."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from abc import ABC, abstractmethod
from enum import Enum
import asyncpg

logger = logging.getLogger(__name__)


class ProjectionStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    REBUILDING = "rebuilding"
    ERROR = "error"


@dataclass
class ProjectionCheckpoint:
    projection_name: str
    last_position: int
    updated_at: str = ""
    events_processed: int = 0
    status: ProjectionStatus = ProjectionStatus.STOPPED


class ProjectionStore:
    """Manages projection checkpoints and metadata."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def initialize(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS projection_checkpoints (
                    projection_name  TEXT PRIMARY KEY,
                    last_position    BIGINT NOT NULL DEFAULT 0,
                    events_processed BIGINT NOT NULL DEFAULT 0,
                    status           TEXT NOT NULL DEFAULT 'stopped',
                    updated_at       TIMESTAMPTZ DEFAULT NOW(),
                    error_message    TEXT
                );
            """)

    async def load_checkpoint(self, name: str) -> ProjectionCheckpoint:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM projection_checkpoints "
                "WHERE projection_name = $1", name,
            )
        if row:
            return ProjectionCheckpoint(
                projection_name=row["projection_name"],
                last_position=row["last_position"],
                events_processed=row["events_processed"],
                status=ProjectionStatus(row["status"]),
            )
        return ProjectionCheckpoint(
            projection_name=name, last_position=0
        )

    async def save_checkpoint(self, cp: ProjectionCheckpoint) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO projection_checkpoints
                (projection_name, last_position, events_processed,
                 status, updated_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (projection_name)
                DO UPDATE SET
                    last_position = $2, events_processed = $3,
                    status = $4, updated_at = NOW()
                """,
                cp.projection_name, cp.last_position,
                cp.events_processed, cp.status.value,
            )


class Projection(ABC):
    """Base class for event projections."""

    def __init__(self, pool: asyncpg.Pool, store: ProjectionStore):
        self.pool = pool
        self.store = store
        self._handlers: dict[str, Callable] = {}
        self._status = ProjectionStatus.STOPPED
        self._register_handlers()

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def _register_handlers(self) -> None: ...

    @abstractmethod
    async def create_schema(self) -> None: ...

    @abstractmethod
    async def drop_schema(self) -> None: ...

    def on(self, event_type: str):
        """Decorator to register an event handler."""
        def decorator(fn: Callable):
            self._handlers[event_type] = fn
            return fn
        return decorator

    async def handle_event(
        self, event: dict, position: int, conn: asyncpg.Connection
    ) -> None:
        handler = self._handlers.get(event["type"])
        if handler:
            await handler(event["data"], conn)

    async def rebuild(self, event_store) -> None:
        """Drop and rebuild the entire projection from events."""
        logger.info("Rebuilding projection: %s", self.name)
        self._status = ProjectionStatus.REBUILDING
        checkpoint = ProjectionCheckpoint(
            projection_name=self.name,
            last_position=0,
            status=ProjectionStatus.REBUILDING,
        )
        await self.store.save_checkpoint(checkpoint)

        await self.drop_schema()
        await self.create_schema()

        batch_size = 500
        position = 0
        total = 0

        while True:
            events = await event_store.load_global(
                from_position=position, limit=batch_size
            )
            if not events:
                break

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for event_row in events:
                        await self.handle_event(
                            event_row["event"],
                            event_row["position"],
                            conn,
                        )
                        position = event_row["position"] + 1
                        total += 1

            checkpoint.last_position = position
            checkpoint.events_processed = total
            await self.store.save_checkpoint(checkpoint)
            logger.info("Rebuilt %d events so far...", total)

        checkpoint.status = ProjectionStatus.RUNNING
        await self.store.save_checkpoint(checkpoint)
        logger.info("Rebuild complete: %d events processed", total)


class OrderReadModelProjection(Projection):
    """Projects order events into a denormalized read model."""

    @property
    def name(self) -> str:
        return "order_read_model"

    def _register_handlers(self) -> None:
        self._handlers = {
            "OrderCreated": self._on_order_created,
            "OrderCancelled": self._on_order_cancelled,
            "OrderStatusUpdated": self._on_status_updated,
            "OrderItemAdded": self._on_item_added,
            "PaymentReceived": self._on_payment_received,
        }

    async def create_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders_read_model (
                    order_id        TEXT PRIMARY KEY,
                    customer_id     TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    total           NUMERIC(12,2) NOT NULL DEFAULT 0,
                    item_count      INTEGER NOT NULL DEFAULT 0,
                    items           JSONB NOT NULL DEFAULT '[]',
                    shipping_address TEXT,
                    payment_status  TEXT DEFAULT 'unpaid',
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ DEFAULT NOW(),
                    cancelled_at    TIMESTAMPTZ,
                    cancel_reason   TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_orders_customer
                    ON orders_read_model (customer_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_orders_status
                    ON orders_read_model (status);
            """)

    async def drop_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS orders_read_model")

    async def _on_order_created(
        self, data: dict, conn: asyncpg.Connection
    ) -> None:
        items_json = json.dumps(data.get("items", []))
        await conn.execute(
            """INSERT INTO orders_read_model
            (order_id, customer_id, status, total, item_count,
             items, shipping_address)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (order_id) DO NOTHING""",
            data["order_id"], data["customer_id"], "pending",
            data["total"], len(data.get("items", [])),
            items_json, data.get("shipping_address", ""),
        )

    async def _on_order_cancelled(
        self, data: dict, conn: asyncpg.Connection
    ) -> None:
        await conn.execute(
            """UPDATE orders_read_model
            SET status = 'cancelled',
                cancel_reason = $2,
                cancelled_at = NOW(),
                updated_at = NOW()
            WHERE order_id = $1""",
            data["order_id"], data.get("reason", ""),
        )

    async def _on_status_updated(
        self, data: dict, conn: asyncpg.Connection
    ) -> None:
        await conn.execute(
            """UPDATE orders_read_model
            SET status = $2, updated_at = NOW()
            WHERE order_id = $1""",
            data["order_id"], data["new_status"],
        )

    async def _on_item_added(
        self, data: dict, conn: asyncpg.Connection
    ) -> None:
        await conn.execute(
            """UPDATE orders_read_model
            SET items = items || $2::jsonb,
                item_count = item_count + 1,
                total = total + $3,
                updated_at = NOW()
            WHERE order_id = $1""",
            data["order_id"],
            json.dumps([data["item"]]),
            data["item"]["price"] * data["item"]["quantity"],
        )

    async def _on_payment_received(
        self, data: dict, conn: asyncpg.Connection
    ) -> None:
        await conn.execute(
            """UPDATE orders_read_model
            SET payment_status = 'paid', updated_at = NOW()
            WHERE order_id = $1""",
            data["order_id"],
        )


class ProjectionEngine:
    """Manages multiple projections, running them as async tasks."""

    def __init__(
        self,
        event_store,
        projections: list[Projection],
        poll_interval: float = 0.5,
    ):
        self.event_store = event_store
        self.projections = {p.name: p for p in projections}
        self.poll_interval = poll_interval
        self._tasks: dict[str, asyncio.Task] = {}

    async def start_all(self) -> None:
        for name, projection in self.projections.items():
            await projection.create_schema()
            task = asyncio.create_task(
                self._run_projection(projection)
            )
            self._tasks[name] = task
            logger.info("Started projection: %s", name)

    async def _run_projection(self, projection: Projection) -> None:
        checkpoint = await projection.store.load_checkpoint(
            projection.name
        )
        position = checkpoint.last_position

        while True:
            try:
                events = await self.event_store.load_global(
                    from_position=position, limit=100
                )
                if events:
                    async with projection.pool.acquire() as conn:
                        async with conn.transaction():
                            for row in events:
                                await projection.handle_event(
                                    row["event"], row["position"], conn
                                )
                                position = row["position"] + 1
                                checkpoint.events_processed += 1

                    checkpoint.last_position = position
                    checkpoint.status = ProjectionStatus.RUNNING
                    await projection.store.save_checkpoint(checkpoint)
                else:
                    await asyncio.sleep(self.poll_interval)
            except Exception:
                logger.exception("Projection %s error", projection.name)
                checkpoint.status = ProjectionStatus.ERROR
                await projection.store.save_checkpoint(checkpoint)
                await asyncio.sleep(5.0)

    async def stop_all(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(
            *self._tasks.values(), return_exceptions=True
        )
```

Projection design patterns comparison:

| Pattern | Latency | Consistency | Rebuild | Use Case |
|---------|---------|-------------|---------|----------|
| Synchronous | Low | Strong | Slow | Critical reads |
| Async polling | Medium | Eventual | Fast | General queries |
| Async push | Low | Eventual | Fast | Real-time dashboards |
| Batch | High | Eventual | Fastest | Analytics/reports |

Key patterns:
- Projections are disposable -- you can always rebuild from the event store
- Use checkpoints to track processed position and resume after restarts
- Run each projection as an independent async task for isolation
- Batch event processing in transactions for consistency and performance
- Monitor projection lag (difference between latest event and checkpoint) as an SLI
- Create separate projections for different query patterns rather than one giant read model
'''
    ),
    (
        "architecture/sagas",
        "How do I implement the saga pattern for distributed transactions across multiple services in Python?",
        '''The saga pattern manages distributed transactions by breaking them into a sequence of local transactions with compensating actions. If any step fails, previous steps are rolled back using their compensations.

Here is a production saga orchestrator implementation:

```python
"""Saga orchestrator for managing distributed transactions."""

import uuid
import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from enum import Enum
from abc import ABC, abstractmethod
import json
import asyncpg

logger = logging.getLogger(__name__)


class SagaStepStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


class SagaStatus(str, Enum):
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass
class SagaStep:
    """A single step in a saga with its compensation."""
    name: str
    action: Callable[[dict], Awaitable[dict]]
    compensation: Callable[[dict], Awaitable[None]]
    timeout_seconds: float = 30.0
    max_retries: int = 3
    status: SagaStepStatus = SagaStepStatus.PENDING
    result: dict = field(default_factory=dict)
    error: str = ""
    attempts: int = 0


@dataclass
class SagaContext:
    """Shared context passed through saga steps."""
    saga_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    data: dict = field(default_factory=dict)
    step_results: dict = field(default_factory=dict)
    status: SagaStatus = SagaStatus.STARTED
    started_at: str = ""
    completed_at: str = ""
    error: str = ""


class SagaDefinition:
    """Defines a saga as a sequence of steps."""

    def __init__(self, name: str):
        self.name = name
        self.steps: list[SagaStep] = []

    def step(
        self,
        name: str,
        action: Callable[[dict], Awaitable[dict]],
        compensation: Callable[[dict], Awaitable[None]],
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> "SagaDefinition":
        self.steps.append(SagaStep(
            name=name,
            action=action,
            compensation=compensation,
            timeout_seconds=timeout,
            max_retries=max_retries,
        ))
        return self


class SagaLog:
    """Persistent saga execution log for recovery."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def initialize(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS saga_log (
                    saga_id     TEXT NOT NULL,
                    step_name   TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    status      TEXT NOT NULL,
                    data        JSONB DEFAULT '{}',
                    error       TEXT,
                    timestamp   TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (saga_id, step_name, action_type)
                );

                CREATE TABLE IF NOT EXISTS saga_state (
                    saga_id      TEXT PRIMARY KEY,
                    saga_name    TEXT NOT NULL,
                    status       TEXT NOT NULL,
                    context_data JSONB DEFAULT '{}',
                    started_at   TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    error        TEXT
                );
            """)

    async def record_step(
        self,
        saga_id: str,
        step_name: str,
        action_type: str,
        status: str,
        data: dict | None = None,
        error: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO saga_log
                (saga_id, step_name, action_type, status, data, error)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (saga_id, step_name, action_type)
                DO UPDATE SET status = $4, data = $5,
                              error = $6, timestamp = NOW()
                """,
                saga_id, step_name, action_type, status,
                json.dumps(data or {}), error,
            )

    async def save_state(self, ctx: SagaContext, saga_name: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO saga_state
                (saga_id, saga_name, status, context_data)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (saga_id)
                DO UPDATE SET status = $3, context_data = $4,
                    completed_at = CASE WHEN $3 IN
                        ('completed','compensated','failed')
                        THEN NOW() ELSE NULL END
                """,
                ctx.saga_id, saga_name, ctx.status.value,
                json.dumps(ctx.step_results),
            )


class SagaOrchestrator:
    """Executes sagas with compensation on failure."""

    def __init__(self, saga_log: SagaLog):
        self.saga_log = saga_log
        self._definitions: dict[str, SagaDefinition] = {}

    def register(self, definition: SagaDefinition) -> None:
        self._definitions[definition.name] = definition

    async def execute(
        self, saga_name: str, initial_data: dict
    ) -> SagaContext:
        definition = self._definitions.get(saga_name)
        if not definition:
            raise ValueError(f"Unknown saga: {saga_name}")

        ctx = SagaContext(
            data=initial_data,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        ctx.status = SagaStatus.RUNNING
        await self.saga_log.save_state(ctx, saga_name)

        completed_steps: list[SagaStep] = []

        for step in definition.steps:
            success = await self._execute_step(step, ctx)

            if success:
                completed_steps.append(step)
                ctx.step_results[step.name] = step.result
            else:
                ctx.error = step.error
                logger.warning(
                    "Saga %s step '%s' failed: %s. Compensating...",
                    ctx.saga_id, step.name, step.error,
                )
                ctx.status = SagaStatus.COMPENSATING
                await self.saga_log.save_state(ctx, saga_name)

                await self._compensate(completed_steps, ctx)

                ctx.status = SagaStatus.COMPENSATED
                await self.saga_log.save_state(ctx, saga_name)
                return ctx

        ctx.status = SagaStatus.COMPLETED
        ctx.completed_at = datetime.now(timezone.utc).isoformat()
        await self.saga_log.save_state(ctx, saga_name)
        logger.info("Saga %s completed successfully", ctx.saga_id)
        return ctx

    async def _execute_step(
        self, step: SagaStep, ctx: SagaContext
    ) -> bool:
        step.status = SagaStepStatus.EXECUTING

        for attempt in range(step.max_retries):
            step.attempts = attempt + 1
            try:
                await self.saga_log.record_step(
                    ctx.saga_id, step.name, "execute",
                    "attempting",
                    data={"attempt": attempt + 1},
                )

                result = await asyncio.wait_for(
                    step.action(ctx.data | ctx.step_results),
                    timeout=step.timeout_seconds,
                )

                step.result = result or {}
                step.status = SagaStepStatus.COMPLETED

                await self.saga_log.record_step(
                    ctx.saga_id, step.name, "execute",
                    "completed", data=step.result,
                )
                return True

            except asyncio.TimeoutError:
                step.error = f"Timeout after {step.timeout_seconds}s"
                logger.warning(
                    "Step %s attempt %d timed out",
                    step.name, attempt + 1,
                )
            except Exception as exc:
                step.error = str(exc)
                logger.warning(
                    "Step %s attempt %d failed: %s",
                    step.name, attempt + 1, exc,
                )

            if attempt < step.max_retries - 1:
                backoff = min(2 ** attempt, 10)
                await asyncio.sleep(backoff)

        step.status = SagaStepStatus.FAILED
        await self.saga_log.record_step(
            ctx.saga_id, step.name, "execute", "failed",
            error=step.error,
        )
        return False

    async def _compensate(
        self, steps: list[SagaStep], ctx: SagaContext
    ) -> None:
        """Run compensations in reverse order."""
        for step in reversed(steps):
            step.status = SagaStepStatus.COMPENSATING
            try:
                await self.saga_log.record_step(
                    ctx.saga_id, step.name, "compensate",
                    "attempting",
                )
                await asyncio.wait_for(
                    step.compensation(ctx.data | ctx.step_results),
                    timeout=step.timeout_seconds,
                )
                step.status = SagaStepStatus.COMPENSATED
                await self.saga_log.record_step(
                    ctx.saga_id, step.name, "compensate",
                    "completed",
                )
            except Exception as exc:
                logger.error(
                    "CRITICAL: Compensation for step '%s' failed: %s. "
                    "Manual intervention required.",
                    step.name, exc,
                )
                await self.saga_log.record_step(
                    ctx.saga_id, step.name, "compensate",
                    "failed", error=str(exc),
                )


# ── Example: Order Processing Saga ────────────────────────────

async def create_order_saga(
    orchestrator: SagaOrchestrator,
) -> None:
    """Define and register the order processing saga."""

    async def reserve_inventory(data: dict) -> dict:
        # Call inventory service
        items = data["items"]
        reservation_id = str(uuid.uuid4())
        logger.info("Reserved inventory: %s", reservation_id)
        return {"reservation_id": reservation_id}

    async def undo_reserve_inventory(data: dict) -> None:
        reservation_id = data.get("reservation_id")
        logger.info("Released inventory reservation: %s", reservation_id)

    async def process_payment(data: dict) -> dict:
        payment_id = str(uuid.uuid4())
        logger.info("Payment processed: %s", payment_id)
        return {"payment_id": payment_id}

    async def refund_payment(data: dict) -> None:
        payment_id = data.get("payment_id")
        logger.info("Refunded payment: %s", payment_id)

    async def create_shipment(data: dict) -> dict:
        tracking = f"TRACK-{uuid.uuid4().hex[:8].upper()}"
        logger.info("Shipment created: %s", tracking)
        return {"tracking_number": tracking}

    async def cancel_shipment(data: dict) -> None:
        tracking = data.get("tracking_number")
        logger.info("Cancelled shipment: %s", tracking)

    async def send_confirmation(data: dict) -> dict:
        logger.info("Confirmation sent to customer")
        return {"notification_sent": True}

    async def no_op_compensate(data: dict) -> None:
        pass  # Notification doesn't need compensation

    saga = (
        SagaDefinition("process_order")
        .step("reserve_inventory", reserve_inventory,
              undo_reserve_inventory, timeout=10.0)
        .step("process_payment", process_payment,
              refund_payment, timeout=30.0, max_retries=3)
        .step("create_shipment", create_shipment,
              cancel_shipment, timeout=15.0)
        .step("send_confirmation", send_confirmation,
              no_op_compensate, timeout=5.0)
    )

    orchestrator.register(saga)
```

Saga pattern comparison:

| Approach | Coordination | Coupling | Complexity | Best For |
|----------|-------------|----------|------------|----------|
| Orchestration | Central orchestrator | Higher | Lower | Clear workflows |
| Choreography | Event-driven | Lower | Higher | Loosely coupled |
| Hybrid | Mix of both | Medium | Medium | Complex domains |

Key patterns:
- Every action must have a corresponding compensation (undo)
- Compensations run in reverse order to unwind partial state
- Persist saga state so you can recover from orchestrator crashes
- Use timeouts and retries on individual steps with exponential backoff
- Log every step attempt, completion, and compensation for debugging
- Compensations must be idempotent -- they may run more than once
- Notifications typically do not need real compensation
'''
    ),
]
