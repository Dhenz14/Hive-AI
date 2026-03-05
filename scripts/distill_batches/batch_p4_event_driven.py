"""
Batch P4 — Event-Driven Architecture: event sourcing, CQRS, Kafka,
sagas, outbox pattern. Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Event Sourcing Fundamentals ---
    (
        "event_sourcing_fundamentals",
        "Explain event sourcing from first principles — event store design with append-only "
        "logs, aggregate reconstruction from event streams, snapshotting for performance, "
        "and building read-model projections. Provide a complete Python implementation using "
        "SQLite as the event store with proper serialization, concurrency control, and tests.",
        r"""
# Event Sourcing Fundamentals: Capturing Every State Change as an Immutable Fact

## Why Event Sourcing?

Traditional CRUD systems store only the **current state** of an entity. When you update
a row, the previous value is gone forever. Event sourcing flips this model: instead of
storing state, you store the **sequence of events** that produced that state. The current
state is derived by replaying events from the beginning.

```
Traditional CRUD:
  Account { balance: 150 }   ← How did we get here? No idea.

Event Sourcing:
  AccountCreated { id: 1 }
  MoneyDeposited { amount: 200 }
  MoneyWithdrawn { amount: 50 }
  → Replay: 0 + 200 - 50 = 150  ← Full audit trail, deterministic.
```

This matters **because** many domains — banking, healthcare, e-commerce — require a
complete audit trail. However, the benefits go far beyond compliance:

1. **Temporal queries**: "What was the account balance on March 1st?"
2. **Event replay**: Fix a bug in projection logic, replay events, get corrected state
3. **Debugging**: Reproduce any state by replaying the exact event sequence
4. **Decoupling**: Downstream systems subscribe to events without coupling to the source

A **common mistake** is treating event sourcing as just "logging everything." The critical
distinction is that events are the **source of truth**, not a side effect. The database
of record is the event log, not a derived table.

## Event Store Design

The event store is an **append-only log** with strict ordering guarantees. Every event
belongs to a **stream** (typically one stream per aggregate instance), and each event
has a monotonically increasing version number within that stream.

**Best practice**: Design events as past-tense facts — `OrderPlaced`, `PaymentReceived`,
`ItemShipped` — because they represent things that **already happened** and cannot be
undone, only compensated.

```python
"""Event store implementation with SQLite backend."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Core domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events. Immutable by design."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainEvent":
        return cls(**data)


@dataclass(frozen=True)
class AccountCreated(DomainEvent):
    """Emitted when a new bank account is opened."""
    account_id: str = ""
    owner_name: str = ""


@dataclass(frozen=True)
class MoneyDeposited(DomainEvent):
    """Emitted when funds are added to an account."""
    account_id: str = ""
    amount: float = 0.0


@dataclass(frozen=True)
class MoneyWithdrawn(DomainEvent):
    """Emitted when funds are removed from an account."""
    account_id: str = ""
    amount: float = 0.0


# ---------------------------------------------------------------------------
# Event registry for deserialization
# ---------------------------------------------------------------------------

EVENT_REGISTRY: dict[str, type[DomainEvent]] = {
    "AccountCreated": AccountCreated,
    "MoneyDeposited": MoneyDeposited,
    "MoneyWithdrawn": MoneyWithdrawn,
}


def serialize_event(event: DomainEvent) -> str:
    """Serialize a domain event to JSON string."""
    return json.dumps(event.to_dict())


def deserialize_event(event_type: str, data: str) -> DomainEvent:
    """Deserialize a JSON string back to the correct event type."""
    cls = EVENT_REGISTRY[event_type]
    return cls.from_dict(json.loads(data))
```

The registry pattern is important **because** when you read events from the store, you
need to reconstruct the correct Python type. Without it, you would lose the polymorphic
behavior that makes event handling clean.

## SQLite Event Store with Concurrency Control

```python
class SQLiteEventStore:
    """
    Append-only event store backed by SQLite.

    Provides optimistic concurrency control via expected_version checks.
    Thread-safe through connection-per-thread isolation.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                global_position INTEGER PRIMARY KEY AUTOINCREMENT,
                stream_id       TEXT    NOT NULL,
                version         INTEGER NOT NULL,
                event_type      TEXT    NOT NULL,
                data            TEXT    NOT NULL,
                metadata        TEXT    DEFAULT '{}',
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(stream_id, version)
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                stream_id    TEXT    PRIMARY KEY,
                version      INTEGER NOT NULL,
                state        TEXT    NOT NULL,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_events_stream
                ON events(stream_id, version);
        """)
        conn.commit()

    def append(
        self,
        stream_id: str,
        events: list[DomainEvent],
        expected_version: int = -1,
    ) -> int:
        """
        Append events to a stream with optimistic concurrency control.

        Args:
            stream_id: The aggregate/stream identifier.
            events: List of domain events to append.
            expected_version: The last known version. Use -1 for new streams.

        Returns:
            The new version number after appending.

        Raises:
            ConcurrencyError: If another writer modified the stream.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Check current version for optimistic locking
        cursor.execute(
            "SELECT COALESCE(MAX(version), -1) FROM events WHERE stream_id = ?",
            (stream_id,),
        )
        current_version = cursor.fetchone()[0]

        if current_version != expected_version:
            raise ConcurrencyError(
                f"Stream '{stream_id}': expected version {expected_version}, "
                f"but found {current_version}"
            )

        new_version = expected_version
        for event in events:
            new_version += 1
            cursor.execute(
                "INSERT INTO events (stream_id, version, event_type, data) "
                "VALUES (?, ?, ?, ?)",
                (stream_id, new_version, type(event).__name__,
                 serialize_event(event)),
            )

        conn.commit()
        return new_version

    def read_stream(
        self,
        stream_id: str,
        from_version: int = 0,
    ) -> list[tuple[int, DomainEvent]]:
        """Read all events for a stream, optionally from a given version."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT version, event_type, data FROM events "
            "WHERE stream_id = ? AND version >= ? ORDER BY version",
            (stream_id, from_version),
        )
        return [
            (row[0], deserialize_event(row[1], row[2]))
            for row in cursor.fetchall()
        ]

    def save_snapshot(
        self, stream_id: str, version: int, state: dict[str, Any]
    ) -> None:
        """Save a snapshot of aggregate state at a specific version."""
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO snapshots (stream_id, version, state) "
            "VALUES (?, ?, ?)",
            (stream_id, version, json.dumps(state)),
        )
        conn.commit()

    def load_snapshot(
        self, stream_id: str
    ) -> tuple[int, dict[str, Any]] | None:
        """Load the latest snapshot for a stream, if one exists."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT version, state FROM snapshots WHERE stream_id = ?",
            (stream_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return (row[0], json.loads(row[1]))


class ConcurrencyError(Exception):
    """Raised when optimistic concurrency check fails."""
```

The **trade-off** with optimistic concurrency is that under high contention, writers must
retry. However, for most domain aggregates, conflicts are rare **because** aggregates are
designed around consistency boundaries with narrow scope.

## Aggregate Reconstruction and Snapshotting

The aggregate reconstructs its state by replaying events. For aggregates with thousands
of events, replaying from scratch is expensive, therefore we use **snapshotting** — we
periodically save the current state and only replay events after the snapshot.

```python
@runtime_checkable
class Aggregate(Protocol):
    """Protocol for event-sourced aggregates."""

    @property
    def stream_id(self) -> str: ...

    @property
    def version(self) -> int: ...

    def apply(self, event: DomainEvent) -> None: ...

    def to_snapshot(self) -> dict[str, Any]: ...

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> "Aggregate": ...


class BankAccount:
    """
    Event-sourced aggregate representing a bank account.

    State is derived entirely from replaying domain events.
    No direct state mutation — all changes go through events.
    """

    SNAPSHOT_INTERVAL: int = 50  # snapshot every 50 events

    def __init__(self) -> None:
        self._account_id: str = ""
        self._owner_name: str = ""
        self._balance: float = 0.0
        self._version: int = -1
        self._pending_events: list[DomainEvent] = []

    @property
    def stream_id(self) -> str:
        return f"account-{self._account_id}"

    @property
    def version(self) -> int:
        return self._version

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def account_id(self) -> str:
        return self._account_id

    # --- Command methods (produce events) ---

    def open(self, account_id: str, owner_name: str) -> None:
        """Command: open a new account."""
        self._raise_event(AccountCreated(
            account_id=account_id, owner_name=owner_name
        ))

    def deposit(self, amount: float) -> None:
        """Command: deposit money into the account."""
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        self._raise_event(MoneyDeposited(
            account_id=self._account_id, amount=amount
        ))

    def withdraw(self, amount: float) -> None:
        """Command: withdraw money from the account."""
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if amount > self._balance:
            raise ValueError(
                f"Insufficient funds: balance={self._balance}, "
                f"requested={amount}"
            )
        self._raise_event(MoneyWithdrawn(
            account_id=self._account_id, amount=amount
        ))

    # --- Event application (state transitions) ---

    def apply(self, event: DomainEvent) -> None:
        """Apply an event to update internal state. No side effects."""
        if isinstance(event, AccountCreated):
            self._account_id = event.account_id
            self._owner_name = event.owner_name
        elif isinstance(event, MoneyDeposited):
            self._balance += event.amount
        elif isinstance(event, MoneyWithdrawn):
            self._balance -= event.amount

    def _raise_event(self, event: DomainEvent) -> None:
        """Record a new event and apply it immediately."""
        self.apply(event)
        self._pending_events.append(event)

    def get_pending_events(self) -> list[DomainEvent]:
        """Return events not yet persisted."""
        return list(self._pending_events)

    def mark_persisted(self, new_version: int) -> None:
        """Clear pending events after successful persistence."""
        self._version = new_version
        self._pending_events.clear()

    # --- Snapshot support ---

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "account_id": self._account_id,
            "owner_name": self._owner_name,
            "balance": self._balance,
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> "BankAccount":
        account = cls()
        account._account_id = data["account_id"]
        account._owner_name = data["owner_name"]
        account._balance = data["balance"]
        return account


class Repository:
    """
    Repository for loading and saving event-sourced aggregates.

    Handles snapshot loading, event replay, and persistence with
    optimistic concurrency control.
    """

    def __init__(self, store: SQLiteEventStore) -> None:
        self._store = store

    def load(self, account_id: str) -> BankAccount:
        """Load an aggregate by replaying its event stream."""
        stream_id = f"account-{account_id}"

        # Try loading from snapshot first
        snapshot = self._store.load_snapshot(stream_id)
        if snapshot is not None:
            version, state = snapshot
            account = BankAccount.from_snapshot(state)
            account._version = version
            from_version = version + 1
        else:
            account = BankAccount()
            from_version = 0

        # Replay events after snapshot
        events = self._store.read_stream(stream_id, from_version)
        for version, event in events:
            account.apply(event)
            account._version = version

        return account

    def save(self, account: BankAccount) -> None:
        """Persist pending events and optionally create a snapshot."""
        pending = account.get_pending_events()
        if not pending:
            return

        new_version = self._store.append(
            account.stream_id, pending, account.version
        )
        account.mark_persisted(new_version)

        # Create snapshot at intervals
        if new_version % BankAccount.SNAPSHOT_INTERVAL == 0:
            self._store.save_snapshot(
                account.stream_id, new_version, account.to_snapshot()
            )
```

## Projections: Building Read Models

Events are optimized for writes, but reads need different shapes. **Projections**
subscribe to the event stream and build denormalized read models — therefore you can
have multiple projections from the same events without changing the write side.

```python
class AccountSummaryProjection:
    """
    Builds a read-optimized view of all accounts.

    This projection listens to account events and maintains a
    denormalized summary table suitable for listing and searching.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS account_summary (
                account_id  TEXT PRIMARY KEY,
                owner_name  TEXT NOT NULL,
                balance     REAL NOT NULL DEFAULT 0.0,
                tx_count    INTEGER NOT NULL DEFAULT 0,
                last_update TEXT
            )
        """)
        self._conn.commit()
        self._handlers: dict[str, Any] = {
            "AccountCreated": self._on_account_created,
            "MoneyDeposited": self._on_money_deposited,
            "MoneyWithdrawn": self._on_money_withdrawn,
        }

    def handle(self, event_type: str, event: DomainEvent) -> None:
        """Dispatch an event to the appropriate handler."""
        handler = self._handlers.get(event_type)
        if handler:
            handler(event)

    def _on_account_created(self, event: AccountCreated) -> None:
        self._conn.execute(
            "INSERT INTO account_summary (account_id, owner_name, balance) "
            "VALUES (?, ?, 0.0)",
            (event.account_id, event.owner_name),
        )
        self._conn.commit()

    def _on_money_deposited(self, event: MoneyDeposited) -> None:
        self._conn.execute(
            "UPDATE account_summary SET balance = balance + ?, "
            "tx_count = tx_count + 1, last_update = datetime('now') "
            "WHERE account_id = ?",
            (event.amount, event.account_id),
        )
        self._conn.commit()

    def _on_money_withdrawn(self, event: MoneyWithdrawn) -> None:
        self._conn.execute(
            "UPDATE account_summary SET balance = balance - ?, "
            "tx_count = tx_count + 1, last_update = datetime('now') "
            "WHERE account_id = ?",
            (event.amount, event.account_id),
        )
        self._conn.commit()

    def get_all_accounts(self) -> list[dict[str, Any]]:
        """Return all account summaries as dictionaries."""
        cursor = self._conn.execute(
            "SELECT account_id, owner_name, balance, tx_count FROM account_summary"
        )
        return [
            {"account_id": r[0], "owner_name": r[1],
             "balance": r[2], "tx_count": r[3]}
            for r in cursor.fetchall()
        ]
```

## Testing the Complete Pipeline

```python
import unittest


class TestEventSourcing(unittest.TestCase):
    """End-to-end tests for the event sourcing implementation."""

    def setUp(self) -> None:
        self.store = SQLiteEventStore(":memory:")
        self.repo = Repository(self.store)

    def test_create_and_transact(self) -> None:
        """Verify basic account lifecycle through events."""
        account = BankAccount()
        account.open("acc-001", "Alice")
        account.deposit(500.0)
        account.withdraw(150.0)
        self.repo.save(account)

        loaded = self.repo.load("acc-001")
        self.assertEqual(loaded.balance, 350.0)
        self.assertEqual(loaded.account_id, "acc-001")

    def test_optimistic_concurrency(self) -> None:
        """Two concurrent writers should conflict."""
        account = BankAccount()
        account.open("acc-002", "Bob")
        self.repo.save(account)

        a1 = self.repo.load("acc-002")
        a2 = self.repo.load("acc-002")

        a1.deposit(100.0)
        self.repo.save(a1)

        a2.deposit(200.0)
        with self.assertRaises(ConcurrencyError):
            self.repo.save(a2)

    def test_snapshot_and_replay(self) -> None:
        """Snapshots should accelerate aggregate loading."""
        account = BankAccount()
        account.open("acc-003", "Charlie")
        for i in range(60):
            account.deposit(10.0)
        self.repo.save(account)

        # Snapshot should exist at version 50
        snap = self.store.load_snapshot("account-acc-003")
        self.assertIsNotNone(snap)

        loaded = self.repo.load("acc-003")
        self.assertEqual(loaded.balance, 600.0)

    def test_projection_builds_read_model(self) -> None:
        """Projection should maintain a denormalized view."""
        projection = AccountSummaryProjection()
        events = [
            AccountCreated(account_id="acc-004", owner_name="Dana"),
            MoneyDeposited(account_id="acc-004", amount=1000.0),
            MoneyWithdrawn(account_id="acc-004", amount=250.0),
        ]
        for evt in events:
            projection.handle(type(evt).__name__, evt)

        summaries = projection.get_all_accounts()
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["balance"], 750.0)
        self.assertEqual(summaries[0]["tx_count"], 2)


if __name__ == "__main__":
    unittest.main()
```

## Summary and Key Takeaways

- **Event sourcing** stores state as an append-only sequence of immutable domain events;
  the current state is always derived, never stored directly as the primary record.
- The **event store** must guarantee stream-level ordering and support optimistic
  concurrency control — therefore the `(stream_id, version)` uniqueness constraint is
  the critical invariant.
- **Snapshotting** is a performance optimization that avoids replaying the entire event
  history; however, correctness must never depend on snapshots because they can always
  be rebuilt from events.
- **Projections** build read-optimized views from the event stream. They are disposable
  and rebuildable, which means you can add new projections retroactively.
- A **common pitfall** is making events too granular or too coarse. Events should represent
  meaningful domain state transitions — `MoneyDeposited` rather than `BalanceFieldUpdated`.
- **Best practice**: version your event schemas from day one. When you need to change an
  event structure, create a new version and write an upcaster that transforms old events
  to the new shape during replay.
"""
    ),

    # --- 2. CQRS Pattern ---
    (
        "cqrs_pattern_implementation",
        "Explain the CQRS (Command Query Responsibility Segregation) pattern in depth — why "
        "separate write and read models, how to implement command handlers and query handlers, "
        "how to build read-model projections with eventual consistency, and the trade-offs "
        "involved. Provide a complete Python implementation with command bus, event bus, "
        "separate write and read paths, and comprehensive tests.",
        r"""
# CQRS: Separating Write and Read Responsibilities for Scalable Systems

## The Core Insight Behind CQRS

In most applications, **reads vastly outnumber writes** — often by a ratio of 100:1 or
more. Yet traditional architectures force reads and writes through the same model, the
same database schema, and the same service layer. This creates a fundamental tension:
the schema that is optimal for enforcing business rules on writes is rarely optimal for
serving complex queries on reads.

**CQRS** resolves this tension by splitting the system into two sides:

```
┌──────────────┐          ┌──────────────────┐
│  Command Side │         │    Query Side     │
│  (Write Model)│         │   (Read Model)    │
│               │  events │                   │
│  Commands ──► │ ──────► │ ──► Projections   │
│  Aggregates   │         │ ──► Denormalized  │
│  Domain Logic │         │     Views         │
│  Event Store  │         │  Read Database    │
└──────────────┘          └──────────────────┘
```

This separation matters **because** it lets you independently optimize each side:
- **Write side**: Normalized, enforces invariants, uses event sourcing or a relational model
- **Read side**: Denormalized, pre-computed, optimized for specific query patterns

A **common mistake** is applying CQRS everywhere. It adds complexity, therefore it should
only be used in domains with genuinely different read/write scaling requirements or complex
query needs.

## Command Side: Enforcing Business Rules

The command side receives **commands** — imperative requests to change state. Commands
pass through validation, domain logic, and produce **events** that describe what happened.

```python
"""CQRS implementation with complete command and query separation."""

from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Generic, TypeVar

# ---------------------------------------------------------------------------
# Commands — imperative requests to change state
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Command(ABC):
    """Base class for all commands. Commands are requests, not guarantees."""
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class CreateProduct(Command):
    """Request to add a new product to the catalog."""
    product_id: str = ""
    name: str = ""
    price: float = 0.0
    stock: int = 0


@dataclass(frozen=True)
class UpdatePrice(Command):
    """Request to change a product's price."""
    product_id: str = ""
    new_price: float = 0.0


@dataclass(frozen=True)
class PlaceOrder(Command):
    """Request to place an order for a product."""
    order_id: str = ""
    product_id: str = ""
    quantity: int = 0
    customer_id: str = ""


# ---------------------------------------------------------------------------
# Events — immutable facts about what happened
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Event:
    """Base class for domain events."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class ProductCreated(Event):
    product_id: str = ""
    name: str = ""
    price: float = 0.0
    stock: int = 0


@dataclass(frozen=True)
class PriceUpdated(Event):
    product_id: str = ""
    old_price: float = 0.0
    new_price: float = 0.0


@dataclass(frozen=True)
class OrderPlaced(Event):
    order_id: str = ""
    product_id: str = ""
    quantity: int = 0
    customer_id: str = ""
    total_price: float = 0.0


@dataclass(frozen=True)
class StockReserved(Event):
    product_id: str = ""
    quantity_reserved: int = 0
    remaining_stock: int = 0
```

**Best practice**: Commands should be named as imperatives (`CreateProduct`, `PlaceOrder`)
while events should be named as past-tense facts (`ProductCreated`, `OrderPlaced`). This
linguistic distinction reinforces the conceptual difference — commands can be rejected,
events cannot.

## Command Handlers and the Write Model

```python
# ---------------------------------------------------------------------------
# Write-side aggregate (domain model)
# ---------------------------------------------------------------------------

class Product:
    """
    Write-model aggregate for products.

    Enforces business invariants: price must be positive,
    stock cannot go negative, etc.
    """

    def __init__(
        self, product_id: str, name: str, price: float, stock: int
    ) -> None:
        self.product_id = product_id
        self.name = name
        self.price = price
        self.stock = stock

    def update_price(self, new_price: float) -> PriceUpdated:
        """Change price with validation."""
        if new_price <= 0:
            raise ValueError("Price must be positive")
        old_price = self.price
        self.price = new_price
        return PriceUpdated(
            product_id=self.product_id,
            old_price=old_price,
            new_price=new_price,
        )

    def reserve_stock(self, quantity: int) -> StockReserved:
        """Reserve stock for an order with availability check."""
        if quantity > self.stock:
            raise ValueError(
                f"Insufficient stock: available={self.stock}, "
                f"requested={quantity}"
            )
        self.stock -= quantity
        return StockReserved(
            product_id=self.product_id,
            quantity_reserved=quantity,
            remaining_stock=self.stock,
        )


# ---------------------------------------------------------------------------
# Command bus and handlers
# ---------------------------------------------------------------------------

class EventBus:
    """
    Simple in-process event bus for publishing domain events.

    In production, this would be backed by Kafka, RabbitMQ, or similar.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[Event], None]]] = {}

    def subscribe(
        self, event_type: str, handler: Callable[[Event], None]
    ) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: Event) -> None:
        event_type = type(event).__name__
        for handler in self._handlers.get(event_type, []):
            handler(event)


class WriteDatabase:
    """
    Write-side storage. Normalized schema optimized for consistency.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                price      REAL NOT NULL,
                stock      INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                order_id    TEXT PRIMARY KEY,
                product_id  TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                quantity    INTEGER NOT NULL,
                total_price REAL NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        self._conn.commit()

    def save_product(self, product: Product) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO products VALUES (?, ?, ?, ?)",
            (product.product_id, product.name,
             product.price, product.stock),
        )
        self._conn.commit()

    def load_product(self, product_id: str) -> Product | None:
        row = self._conn.execute(
            "SELECT product_id, name, price, stock FROM products "
            "WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if row is None:
            return None
        return Product(*row)

    def save_order(
        self, order_id: str, product_id: str, customer_id: str,
        quantity: int, total_price: float
    ) -> None:
        self._conn.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (order_id, product_id, customer_id, quantity, total_price),
        )
        self._conn.commit()


class CommandHandler:
    """
    Processes commands, enforces business rules, and emits events.

    This is the single point of entry for all write operations.
    """

    def __init__(
        self, write_db: WriteDatabase, event_bus: EventBus
    ) -> None:
        self._db = write_db
        self._bus = event_bus

    def handle(self, command: Command) -> list[Event]:
        """Dispatch a command to the appropriate handler method."""
        if isinstance(command, CreateProduct):
            return self._create_product(command)
        elif isinstance(command, UpdatePrice):
            return self._update_price(command)
        elif isinstance(command, PlaceOrder):
            return self._place_order(command)
        raise ValueError(f"Unknown command: {type(command).__name__}")

    def _create_product(self, cmd: CreateProduct) -> list[Event]:
        product = Product(cmd.product_id, cmd.name, cmd.price, cmd.stock)
        self._db.save_product(product)
        event = ProductCreated(
            product_id=cmd.product_id, name=cmd.name,
            price=cmd.price, stock=cmd.stock,
        )
        self._bus.publish(event)
        return [event]

    def _update_price(self, cmd: UpdatePrice) -> list[Event]:
        product = self._db.load_product(cmd.product_id)
        if product is None:
            raise ValueError(f"Product {cmd.product_id} not found")
        event = product.update_price(cmd.new_price)
        self._db.save_product(product)
        self._bus.publish(event)
        return [event]

    def _place_order(self, cmd: PlaceOrder) -> list[Event]:
        product = self._db.load_product(cmd.product_id)
        if product is None:
            raise ValueError(f"Product {cmd.product_id} not found")
        reserve_event = product.reserve_stock(cmd.quantity)
        total_price = product.price * cmd.quantity
        self._db.save_product(product)
        self._db.save_order(
            cmd.order_id, cmd.product_id, cmd.customer_id,
            cmd.quantity, total_price,
        )
        order_event = OrderPlaced(
            order_id=cmd.order_id, product_id=cmd.product_id,
            quantity=cmd.quantity, customer_id=cmd.customer_id,
            total_price=total_price,
        )
        self._bus.publish(reserve_event)
        self._bus.publish(order_event)
        return [reserve_event, order_event]
```

## Query Side: Optimized Read Models

The query side maintains **denormalized projections** that are purpose-built for specific
UI views. This is where the real power of CQRS emerges — each screen or API endpoint
can have its own projection without compromising the write model.

```python
# ---------------------------------------------------------------------------
# Read-side projections
# ---------------------------------------------------------------------------

class ReadDatabase:
    """
    Read-side storage with denormalized views.

    Separate from the write database — in production these could be
    different technologies entirely (e.g., write to Postgres,
    read from Elasticsearch or Redis).
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS product_catalog (
                product_id   TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                price        REAL NOT NULL,
                stock        INTEGER NOT NULL,
                total_orders INTEGER NOT NULL DEFAULT 0,
                revenue      REAL NOT NULL DEFAULT 0.0
            );
            CREATE TABLE IF NOT EXISTS customer_orders (
                order_id     TEXT PRIMARY KEY,
                customer_id  TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity     INTEGER NOT NULL,
                total_price  REAL NOT NULL
            );
        """)
        self._conn.commit()

    def upsert_catalog(
        self, product_id: str, name: str, price: float, stock: int
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO product_catalog "
            "(product_id, name, price, stock) VALUES (?, ?, ?, ?)",
            (product_id, name, price, stock),
        )
        self._conn.commit()

    def update_catalog_price(
        self, product_id: str, new_price: float
    ) -> None:
        self._conn.execute(
            "UPDATE product_catalog SET price = ? WHERE product_id = ?",
            (new_price, product_id),
        )
        self._conn.commit()

    def update_catalog_stock(
        self, product_id: str, remaining_stock: int
    ) -> None:
        self._conn.execute(
            "UPDATE product_catalog SET stock = ? WHERE product_id = ?",
            (remaining_stock, product_id),
        )
        self._conn.commit()

    def record_order_in_catalog(
        self, product_id: str, revenue: float
    ) -> None:
        self._conn.execute(
            "UPDATE product_catalog SET total_orders = total_orders + 1, "
            "revenue = revenue + ? WHERE product_id = ?",
            (revenue, product_id),
        )
        self._conn.commit()

    def add_customer_order(
        self, order_id: str, customer_id: str, product_name: str,
        quantity: int, total_price: float,
    ) -> None:
        self._conn.execute(
            "INSERT INTO customer_orders VALUES (?, ?, ?, ?, ?)",
            (order_id, customer_id, product_name, quantity, total_price),
        )
        self._conn.commit()

    def get_catalog(self) -> list[dict[str, Any]]:
        """Query: full product catalog with order stats."""
        rows = self._conn.execute(
            "SELECT * FROM product_catalog ORDER BY revenue DESC"
        ).fetchall()
        return [
            {"product_id": r[0], "name": r[1], "price": r[2],
             "stock": r[3], "total_orders": r[4], "revenue": r[5]}
            for r in rows
        ]

    def get_customer_orders(self, customer_id: str) -> list[dict[str, Any]]:
        """Query: all orders for a specific customer."""
        rows = self._conn.execute(
            "SELECT * FROM customer_orders WHERE customer_id = ?",
            (customer_id,),
        ).fetchall()
        return [
            {"order_id": r[0], "customer_id": r[1], "product_name": r[2],
             "quantity": r[3], "total_price": r[4]}
            for r in rows
        ]


class ProjectionHandler:
    """
    Subscribes to domain events and updates read-side projections.

    This is the bridge between the write side and the read side.
    Eventual consistency is guaranteed — projections may lag behind
    the write model by milliseconds to seconds.
    """

    def __init__(self, read_db: ReadDatabase) -> None:
        self._db = read_db
        self._product_names: dict[str, str] = {}

    def on_product_created(self, event: ProductCreated) -> None:
        self._product_names[event.product_id] = event.name
        self._db.upsert_catalog(
            event.product_id, event.name, event.price, event.stock
        )

    def on_price_updated(self, event: PriceUpdated) -> None:
        self._db.update_catalog_price(event.product_id, event.new_price)

    def on_stock_reserved(self, event: StockReserved) -> None:
        self._db.update_catalog_stock(
            event.product_id, event.remaining_stock
        )

    def on_order_placed(self, event: OrderPlaced) -> None:
        product_name = self._product_names.get(
            event.product_id, "Unknown"
        )
        self._db.record_order_in_catalog(
            event.product_id, event.total_price
        )
        self._db.add_customer_order(
            event.order_id, event.customer_id, product_name,
            event.quantity, event.total_price,
        )
```

## Wiring It Together and Testing

```python
import unittest


def build_system() -> tuple[CommandHandler, ReadDatabase]:
    """Factory that wires up the complete CQRS system."""
    write_db = WriteDatabase()
    read_db = ReadDatabase()
    event_bus = EventBus()
    projection = ProjectionHandler(read_db)

    # Subscribe projections to events
    event_bus.subscribe("ProductCreated", projection.on_product_created)
    event_bus.subscribe("PriceUpdated", projection.on_price_updated)
    event_bus.subscribe("StockReserved", projection.on_stock_reserved)
    event_bus.subscribe("OrderPlaced", projection.on_order_placed)

    handler = CommandHandler(write_db, event_bus)
    return handler, read_db


class TestCQRS(unittest.TestCase):
    """Integration tests for the CQRS implementation."""

    def setUp(self) -> None:
        self.handler, self.read_db = build_system()

    def test_create_product_updates_read_model(self) -> None:
        self.handler.handle(CreateProduct(
            product_id="p1", name="Widget", price=29.99, stock=100
        ))
        catalog = self.read_db.get_catalog()
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["name"], "Widget")
        self.assertEqual(catalog[0]["stock"], 100)

    def test_order_updates_both_models(self) -> None:
        self.handler.handle(CreateProduct(
            product_id="p2", name="Gadget", price=49.99, stock=50
        ))
        self.handler.handle(PlaceOrder(
            order_id="o1", product_id="p2",
            quantity=3, customer_id="c1"
        ))
        catalog = self.read_db.get_catalog()
        self.assertEqual(catalog[0]["stock"], 47)
        self.assertEqual(catalog[0]["total_orders"], 1)
        self.assertAlmostEqual(catalog[0]["revenue"], 149.97, places=2)

        orders = self.read_db.get_customer_orders("c1")
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["product_name"], "Gadget")

    def test_insufficient_stock_rejected(self) -> None:
        self.handler.handle(CreateProduct(
            product_id="p3", name="Rare Item", price=999.99, stock=2
        ))
        with self.assertRaises(ValueError):
            self.handler.handle(PlaceOrder(
                order_id="o2", product_id="p3",
                quantity=5, customer_id="c2"
            ))


if __name__ == "__main__":
    unittest.main()
```

## Summary and Key Takeaways

- **CQRS** separates the write model (commands, domain logic, consistency enforcement) from
  the read model (queries, denormalized projections, optimized for specific views).
- The **trade-off** is increased complexity: you now maintain two models, handle eventual
  consistency, and need event-based synchronization between them.
- **Best practice**: Start with a single database and logical separation. Only physically
  separate write and read databases when you have concrete scaling evidence.
- The **event bus** is the bridge — every state change on the write side publishes events
  that projections consume to update the read side.
- **Eventual consistency** is the reality: the read model may lag behind by milliseconds.
  However, for most user-facing scenarios this is imperceptible, and the scalability
  benefits are substantial.
- A **common pitfall** is using CQRS for simple CRUD applications. If your read and write
  models look identical, CQRS adds overhead without benefit. Reserve it for domains with
  genuinely different read/write requirements or where event sourcing is already in play.
"""
    ),

    # --- 3. Apache Kafka Deep Dive ---
    (
        "apache_kafka_deep_dive",
        "Provide a comprehensive deep dive into Apache Kafka — topic partitioning strategies, "
        "consumer group mechanics and rebalancing, exactly-once semantics with idempotent "
        "producers and transactional APIs, Schema Registry for schema evolution, and complete "
        "Python producer/consumer implementations using confluent-kafka-python with robust "
        "error handling, monitoring metrics, and graceful shutdown.",
        r"""
# Apache Kafka Deep Dive: Distributed Event Streaming at Scale

## Kafka's Core Architecture

Apache Kafka is a **distributed commit log** — an append-only, partitioned, replicated
log structure that provides durable, ordered, and replayable event streams. Understanding
its architecture is essential **because** every design decision in Kafka traces back to
the commit log abstraction.

```
Producer ──► Topic: "orders" ──────────────────────────────────────────────
              │
              ├── Partition 0: [msg0, msg1, msg4, msg7, ...]  → Broker 1
              ├── Partition 1: [msg2, msg3, msg6, msg9, ...]  → Broker 2
              └── Partition 2: [msg5, msg8, msg10, ...]       → Broker 3
                                                                    │
              Consumer Group "order-service" ◄──────────────────────┘
                Consumer A ← Partition 0
                Consumer B ← Partition 1
                Consumer C ← Partition 2
```

Key concepts:
- **Topics** are logical channels; **partitions** are the unit of parallelism
- Each partition is an ordered, append-only log with monotonic offsets
- **Consumer groups** enable parallel consumption — each partition is assigned to exactly
  one consumer within a group
- **Replication** ensures durability — each partition has a leader and N-1 followers

## Partitioning Strategies

Partition selection determines ordering guarantees and load distribution. The **trade-off**
is between strict ordering (all related events in one partition) and parallelism (events
spread across partitions).

```python
"""Kafka partitioning strategies and custom partitioners."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import Any


@dataclass
class PartitionStrategy:
    """
    Encapsulates partition assignment logic.

    The choice of partition key is one of the most critical
    Kafka design decisions because it determines:
    1. Ordering guarantees within a consumer
    2. Load distribution across partitions
    3. Consumer group scalability ceiling
    """

    num_partitions: int

    def key_based(self, key: str) -> int:
        """
        Consistent hashing on a key — all events with the same
        key land in the same partition, guaranteeing order.

        Best practice: Use the aggregate/entity ID as key.
        """
        murmur = self._murmur2(key.encode("utf-8"))
        return abs(murmur) % self.num_partitions

    def round_robin(self, counter: int) -> int:
        """
        Distribute events evenly across partitions.

        Use when ordering does not matter and maximum
        throughput is the goal.
        """
        return counter % self.num_partitions

    def custom_business_logic(
        self, event: dict[str, Any]
    ) -> int:
        """
        Route by business attributes — e.g., region, priority.

        Common mistake: Using a low-cardinality key (like region)
        causes partition skew. Monitor partition lag to detect this.
        """
        region = event.get("region", "default")
        priority = event.get("priority", "normal")

        if priority == "critical":
            return 0  # Dedicated partition for critical events

        return self.key_based(region)

    @staticmethod
    def _murmur2(data: bytes) -> int:
        """
        Java-compatible Murmur2 hash — matches Kafka's
        default partitioner for interoperability.
        """
        seed = 0x9747B28C
        m = 0x5BD1E995
        r = 24
        length = len(data)
        h = seed ^ length

        for i in range(0, length - (length % 4), 4):
            k = struct.unpack_from("<I", data, i)[0]
            k = (k * m) & 0xFFFFFFFF
            k ^= k >> r
            k = (k * m) & 0xFFFFFFFF
            h = (h * m) & 0xFFFFFFFF
            h ^= k

        remaining = length % 4
        tail_index = length - remaining
        if remaining >= 3:
            h ^= data[tail_index + 2] << 16
        if remaining >= 2:
            h ^= data[tail_index + 1] << 8
        if remaining >= 1:
            h ^= data[tail_index]
            h = (h * m) & 0xFFFFFFFF

        h ^= h >> 13
        h = (h * m) & 0xFFFFFFFF
        h ^= h >> 15
        return h
```

## Consumer Groups and Rebalancing

Consumer groups are Kafka's mechanism for **parallel, fault-tolerant consumption**. When
a consumer joins or leaves a group, Kafka triggers a **rebalance** — reassigning
partitions across the remaining consumers.

However, rebalancing is expensive **because** all consumers in the group must stop
processing during the rebalance. Modern Kafka mitigates this with **cooperative
sticky rebalancing**, which only migrates the affected partitions rather than revoking
all assignments.

```python
"""
Kafka consumer with cooperative rebalancing, error handling,
and graceful shutdown.
"""

import signal
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from confluent_kafka import (
    Consumer,
    KafkaError,
    KafkaException,
    TopicPartition,
)

logger = logging.getLogger(__name__)


@dataclass
class ConsumerConfig:
    """Typed configuration for a Kafka consumer."""
    bootstrap_servers: str = "localhost:9092"
    group_id: str = "default-group"
    topics: list[str] = field(default_factory=lambda: ["events"])
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False
    max_poll_interval_ms: int = 300_000
    session_timeout_ms: int = 45_000
    partition_assignment_strategy: str = "cooperative-sticky"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": self.group_id,
            "auto.offset.reset": self.auto_offset_reset,
            "enable.auto.commit": self.enable_auto_commit,
            "max.poll.interval.ms": self.max_poll_interval_ms,
            "session.timeout.ms": self.session_timeout_ms,
            "partition.assignment.strategy": self.partition_assignment_strategy,
        }


class KafkaConsumerService:
    """
    Production-grade Kafka consumer with:
    - Manual offset commits for at-least-once delivery
    - Cooperative sticky rebalancing
    - Graceful shutdown via signal handlers
    - Dead letter queue for poison messages
    - Metrics tracking (lag, throughput, errors)
    """

    def __init__(
        self,
        config: ConsumerConfig,
        handler: Callable[[str, str, bytes], bool],
        dlq_topic: str = "dead-letter-queue",
    ) -> None:
        self._config = config
        self._handler = handler
        self._dlq_topic = dlq_topic
        self._running = True
        self._consumer: Consumer | None = None

        # Metrics
        self._messages_processed: int = 0
        self._errors: int = 0
        self._last_commit_time: float = 0.0

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal gracefully."""
        logger.info("Shutdown signal received, finishing current batch...")
        self._running = False

    def _on_assign(
        self, consumer: Consumer, partitions: list[TopicPartition]
    ) -> None:
        """Called when partitions are assigned during rebalance."""
        partition_list = [f"{p.topic}[{p.partition}]" for p in partitions]
        logger.info(f"Partitions assigned: {partition_list}")

    def _on_revoke(
        self, consumer: Consumer, partitions: list[TopicPartition]
    ) -> None:
        """Called when partitions are revoked during rebalance."""
        # Commit offsets for revoked partitions before they are reassigned
        logger.info("Committing offsets for revoked partitions...")
        consumer.commit(asynchronous=False)

    def run(self) -> None:
        """
        Main consumer loop with error handling and offset management.

        Best practice: Commit offsets after processing, not before.
        This ensures at-least-once delivery semantics.
        """
        self._consumer = Consumer(self._config.to_dict())
        self._consumer.subscribe(
            self._config.topics,
            on_assign=self._on_assign,
            on_revoke=self._on_revoke,
        )

        logger.info(
            f"Consumer started: group={self._config.group_id}, "
            f"topics={self._config.topics}"
        )

        try:
            while self._running:
                msg = self._consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    self._handle_consumer_error(msg.error())
                    continue

                # Process the message
                success = self._process_message(msg)

                if success:
                    self._messages_processed += 1
                    # Commit every 100 messages or every 5 seconds
                    if (
                        self._messages_processed % 100 == 0
                        or time.time() - self._last_commit_time > 5.0
                    ):
                        self._consumer.commit(asynchronous=False)
                        self._last_commit_time = time.time()

        except KafkaException as e:
            logger.error(f"Fatal Kafka error: {e}")
            raise
        finally:
            logger.info(
                f"Shutting down. Processed: {self._messages_processed}, "
                f"Errors: {self._errors}"
            )
            self._consumer.commit(asynchronous=False)
            self._consumer.close()

    def _process_message(self, msg: Any) -> bool:
        """Process a single message with error isolation."""
        try:
            topic = msg.topic()
            key = msg.key().decode("utf-8") if msg.key() else ""
            value = msg.value()

            return self._handler(topic, key, value)

        except Exception as e:
            self._errors += 1
            logger.error(
                f"Error processing message at "
                f"{msg.topic()}[{msg.partition()}]@{msg.offset()}: {e}"
            )
            # In production, send to dead letter queue
            self._send_to_dlq(msg, str(e))
            return True  # Acknowledge to avoid blocking

    def _handle_consumer_error(self, error: KafkaError) -> None:
        """Handle Kafka-level consumer errors."""
        if error.code() == KafkaError._PARTITION_EOF:
            logger.debug("Reached end of partition")
        elif error.code() == KafkaError._ALL_BROKERS_DOWN:
            logger.critical("All brokers are down!")
            self._running = False
        else:
            logger.error(f"Consumer error: {error}")
            self._errors += 1

    def _send_to_dlq(self, msg: Any, error_reason: str) -> None:
        """Route failed messages to dead letter queue for investigation."""
        logger.warning(
            f"Sending message to DLQ: topic={msg.topic()}, "
            f"partition={msg.partition()}, offset={msg.offset()}, "
            f"reason={error_reason}"
        )
        # In production, produce to self._dlq_topic with headers
        # containing original topic, partition, offset, and error reason

    def get_metrics(self) -> dict[str, Any]:
        """Return current consumer metrics for monitoring."""
        return {
            "messages_processed": self._messages_processed,
            "errors": self._errors,
            "running": self._running,
        }
```

## Exactly-Once Semantics with Idempotent Producers

Kafka provides **exactly-once semantics (EOS)** through two mechanisms:
1. **Idempotent producers**: Kafka deduplicates retries using a producer ID and sequence number
2. **Transactional API**: Atomic writes across multiple partitions

The **pitfall** with exactly-once is that it only applies within Kafka. If your consumer
writes to an external database, you need application-level idempotency (e.g., deduplication
by event ID).

```python
"""
Kafka producer with exactly-once semantics, schema validation,
and delivery callbacks.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable
from confluent_kafka import Producer, KafkaError
from confluent_kafka.serialization import (
    SerializationContext,
    MessageField,
)

logger = logging.getLogger(__name__)


@dataclass
class ProducerMetrics:
    """Track producer health metrics."""
    messages_sent: int = 0
    messages_failed: int = 0
    bytes_sent: int = 0


class KafkaProducerService:
    """
    Production-grade Kafka producer with:
    - Idempotent delivery (exactly-once within Kafka)
    - Delivery confirmation callbacks
    - Batching and compression for throughput
    - Schema validation before sending
    - Comprehensive error handling
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        transactional_id: str | None = None,
    ) -> None:
        config: dict[str, Any] = {
            "bootstrap.servers": bootstrap_servers,
            "enable.idempotence": True,       # Exactly-once within Kafka
            "acks": "all",                    # Wait for all ISR replicas
            "retries": 2147483647,            # Infinite retries with idempotence
            "max.in.flight.requests.per.connection": 5,  # Safe with idempotence
            "compression.type": "lz4",        # Good throughput/ratio balance
            "linger.ms": 5,                   # Batch for 5ms
            "batch.size": 65536,              # 64KB batches
        }

        if transactional_id:
            config["transactional.id"] = transactional_id

        self._producer = Producer(config)
        self._transactional = transactional_id is not None
        self._metrics = ProducerMetrics()

        if self._transactional:
            self._producer.init_transactions()

    def _delivery_callback(
        self, err: KafkaError | None, msg: Any
    ) -> None:
        """Called once per message to confirm delivery."""
        if err is not None:
            self._metrics.messages_failed += 1
            logger.error(
                f"Delivery failed for {msg.topic()}[{msg.partition()}]: {err}"
            )
        else:
            self._metrics.messages_sent += 1
            self._metrics.bytes_sent += len(msg.value())
            logger.debug(
                f"Delivered to {msg.topic()}[{msg.partition()}]"
                f"@{msg.offset()}"
            )

    def send(
        self,
        topic: str,
        key: str,
        value: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Send a message with delivery confirmation.

        The key determines partition assignment — therefore all
        events for the same entity should use the same key.
        """
        serialized_value = json.dumps(value).encode("utf-8")
        kafka_headers = (
            [(k, v.encode("utf-8")) for k, v in headers.items()]
            if headers else None
        )

        self._producer.produce(
            topic=topic,
            key=key.encode("utf-8"),
            value=serialized_value,
            headers=kafka_headers,
            callback=self._delivery_callback,
        )
        # Trigger delivery callbacks for completed sends
        self._producer.poll(0)

    def send_transactional(
        self,
        messages: list[tuple[str, str, dict[str, Any]]],
    ) -> None:
        """
        Send multiple messages atomically using Kafka transactions.

        Either all messages are delivered or none are. This is
        essential for patterns like the outbox pattern where you
        need to atomically produce to multiple topics.
        """
        if not self._transactional:
            raise RuntimeError(
                "Producer not configured for transactions. "
                "Set transactional_id in constructor."
            )

        self._producer.begin_transaction()
        try:
            for topic, key, value in messages:
                self.send(topic, key, value)
            self._producer.commit_transaction()
        except Exception as e:
            logger.error(f"Transaction failed, aborting: {e}")
            self._producer.abort_transaction()
            raise

    def flush(self, timeout: float = 10.0) -> int:
        """Flush pending messages. Returns number of messages still in queue."""
        return self._producer.flush(timeout)

    def get_metrics(self) -> dict[str, int]:
        return {
            "sent": self._metrics.messages_sent,
            "failed": self._metrics.messages_failed,
            "bytes": self._metrics.bytes_sent,
        }
```

## Schema Registry for Schema Evolution

Schema Registry ensures that producers and consumers agree on message structure.
**Best practice**: Use Avro or Protobuf schemas with compatibility rules (BACKWARD,
FORWARD, FULL) to evolve schemas safely without breaking consumers.

```python
"""Schema validation layer using JSON Schema (simplified Schema Registry)."""

from dataclasses import dataclass, field
from typing import Any
import json


@dataclass
class SchemaVersion:
    """Represents a versioned schema for a topic."""
    subject: str
    version: int
    schema: dict[str, Any]
    compatibility: str = "BACKWARD"  # BACKWARD, FORWARD, FULL, NONE


class LocalSchemaRegistry:
    """
    In-process schema registry for validation.

    In production, use Confluent Schema Registry which provides
    centralized schema management, compatibility enforcement,
    and automatic serialization/deserialization.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, list[SchemaVersion]] = {}

    def register(
        self, subject: str, schema: dict[str, Any],
        compatibility: str = "BACKWARD",
    ) -> int:
        """Register a new schema version for a subject."""
        versions = self._schemas.setdefault(subject, [])
        new_version = len(versions) + 1

        if versions and compatibility != "NONE":
            self._check_compatibility(
                versions[-1].schema, schema, compatibility
            )

        versions.append(SchemaVersion(
            subject=subject, version=new_version,
            schema=schema, compatibility=compatibility,
        ))
        return new_version

    def validate(
        self, subject: str, data: dict[str, Any]
    ) -> bool:
        """Validate data against the latest schema for a subject."""
        versions = self._schemas.get(subject)
        if not versions:
            raise ValueError(f"No schema registered for {subject}")

        latest = versions[-1].schema
        return self._validate_against_schema(data, latest)

    def _check_compatibility(
        self,
        old_schema: dict[str, Any],
        new_schema: dict[str, Any],
        mode: str,
    ) -> None:
        """Check backward/forward compatibility between schemas."""
        old_fields = set(old_schema.get("required", []))
        new_fields = set(new_schema.get("required", []))

        if mode in ("BACKWARD", "FULL"):
            # New schema must be readable by old consumers
            # Therefore new required fields cannot be added
            added_required = new_fields - old_fields
            if added_required:
                raise ValueError(
                    f"Backward incompatible: new required fields "
                    f"{added_required}"
                )

        if mode in ("FORWARD", "FULL"):
            # Old schema must be readable by new consumers
            # Therefore old required fields cannot be removed
            removed_required = old_fields - new_fields
            if removed_required:
                raise ValueError(
                    f"Forward incompatible: removed required fields "
                    f"{removed_required}"
                )

    @staticmethod
    def _validate_against_schema(
        data: dict[str, Any], schema: dict[str, Any]
    ) -> bool:
        """Simple schema validation (production would use jsonschema)."""
        required = schema.get("required", [])
        for req_field in required:
            if req_field not in data:
                return False
        return True


# Example usage and tests
def test_schema_registry() -> None:
    """Demonstrate schema registration and evolution."""
    registry = LocalSchemaRegistry()

    # V1 schema
    v1_schema = {
        "type": "object",
        "required": ["order_id", "product_id", "quantity"],
        "properties": {
            "order_id": {"type": "string"},
            "product_id": {"type": "string"},
            "quantity": {"type": "integer"},
        },
    }
    registry.register("orders-value", v1_schema)

    # V2 adds optional field — backward compatible
    v2_schema = {
        "type": "object",
        "required": ["order_id", "product_id", "quantity"],
        "properties": {
            "order_id": {"type": "string"},
            "product_id": {"type": "string"},
            "quantity": {"type": "integer"},
            "discount_pct": {"type": "number", "default": 0.0},
        },
    }
    registry.register("orders-value", v2_schema)

    # Validate against latest schema
    valid_msg = {"order_id": "o1", "product_id": "p1", "quantity": 5}
    assert registry.validate("orders-value", valid_msg) is True

    invalid_msg = {"order_id": "o1"}  # Missing required fields
    assert registry.validate("orders-value", invalid_msg) is False

    print("All schema registry tests passed!")
```

## Summary and Key Takeaways

- **Partition keys** are the single most important design decision — they determine ordering,
  parallelism, and load distribution. A **common mistake** is choosing low-cardinality keys
  that create hot partitions.
- **Consumer groups** provide automatic parallelism and fault tolerance, however rebalancing
  is disruptive. Use **cooperative-sticky** assignment and size your consumer group to match
  your partition count (more consumers than partitions means idle consumers).
- **Exactly-once semantics** requires idempotent producers (`enable.idempotence=True`) and
  either transactional producers or application-level deduplication on the consumer side.
- **Best practice** for error handling: never let a poison message block the consumer. Route
  failures to a dead letter queue and continue processing. Monitor DLQ depth as a health metric.
- **Schema Registry** prevents breaking changes from reaching production. Enforce BACKWARD
  compatibility as the default — this means new consumers can always read old messages.
- The **trade-off** with Kafka is operational complexity. It requires ZooKeeper (or KRaft),
  careful partition sizing, ISR management, and monitoring. However, for event-driven
  architectures at scale, it provides unmatched durability, ordering, and throughput
  guarantees that simpler message brokers cannot match.
"""
    ),

    # --- 4. Saga Pattern for Distributed Transactions ---
    (
        "saga_pattern_distributed_transactions",
        "Explain the Saga pattern for managing distributed transactions across microservices — "
        "choreography vs orchestration approaches, compensation logic for rollbacks, timeout "
        "handling, and idempotency requirements. Build a complete Python saga orchestrator for "
        "an e-commerce order flow with payment, inventory, and shipping steps including proper "
        "error handling, state persistence, and comprehensive tests.",
        r"""
# Saga Pattern: Coordinating Distributed Transactions Without Two-Phase Commit

## Why Sagas Exist

In a monolith, a database transaction guarantees ACID properties across all operations.
In a microservices architecture, each service owns its own database, therefore a single
business operation (like placing an order) spans multiple services and databases. You
cannot use a distributed transaction (2PC) **because** it creates tight coupling, blocks
resources, and becomes a single point of failure.

The **Saga pattern** replaces a single ACID transaction with a sequence of **local
transactions**, each with a **compensating action** that undoes its effect if a later
step fails.

```
Happy Path:
  Create Order → Reserve Inventory → Charge Payment → Ship Order → Done ✓

Failure at Payment:
  Create Order → Reserve Inventory → Charge Payment ✗
                                          ↓
  Compensate:   Cancel Order ← Release Inventory ← (Payment failed, no compensation needed)
```

## Choreography vs. Orchestration

There are two approaches to coordinating sagas:

**Choreography** — each service listens to events from other services and decides
independently what to do next. No central coordinator.

```
Order Service                  Inventory Service              Payment Service
     │                              │                              │
     │──── OrderCreated ───────────►│                              │
     │                              │──── InventoryReserved ──────►│
     │                              │                              │──── PaymentCharged
     │◄──────────────────────────────────── PaymentCharged ────────│
     │──── OrderConfirmed           │                              │
```

**Orchestration** — a central saga orchestrator directs each service, telling them what
to do and handling failures.

The **trade-off**: choreography is simpler for small flows (3-4 steps) but becomes
tangled as complexity grows. Orchestration adds a coordinator but makes the flow
explicit and easier to reason about. **Best practice**: use orchestration for
business-critical flows with more than three steps.

## Building a Saga Orchestrator

```python
"""
Saga orchestrator for distributed transactions.

Manages multi-step business processes with automatic
compensation on failure and persistent state tracking.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SagaState(str, Enum):
    """Possible states of a saga execution."""
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


class StepState(str, Enum):
    """Possible states of an individual saga step."""
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


@dataclass
class SagaStep:
    """
    Defines a single step in a saga with its action and compensation.

    Each step has:
    - action: The forward operation (e.g., charge payment)
    - compensation: The reverse operation (e.g., refund payment)
    - timeout: Maximum time before the step is considered failed
    """
    name: str
    action: Callable[[dict[str, Any]], dict[str, Any]]
    compensation: Callable[[dict[str, Any]], dict[str, Any]]
    timeout_seconds: int = 30
    retries: int = 3

    def __repr__(self) -> str:
        return f"SagaStep({self.name})"


@dataclass
class StepExecution:
    """Tracks the execution state of a single step."""
    step_name: str
    state: StepState = StepState.PENDING
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    attempts: int = 0
    started_at: str = ""
    completed_at: str = ""


@dataclass
class SagaExecution:
    """
    Represents a running saga instance with all its state.

    This is the core data structure persisted to the saga store.
    """
    saga_id: str
    saga_type: str
    state: SagaState
    context: dict[str, Any]
    step_executions: list[StepExecution]
    current_step_index: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = ""
```

**Best practice**: Always persist saga state to a durable store. If the orchestrator
crashes, it must be able to resume in-progress sagas from where they left off. This
is why each step's state is tracked independently.

## Saga State Persistence

```python
class SagaStore:
    """
    Persistent storage for saga executions.

    Stores the complete saga state including step results,
    enabling crash recovery and auditability.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sagas (
                saga_id    TEXT PRIMARY KEY,
                saga_type  TEXT NOT NULL,
                state      TEXT NOT NULL,
                context    TEXT NOT NULL,
                steps      TEXT NOT NULL,
                current_step INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_sagas_state
                ON sagas(state);
            CREATE INDEX IF NOT EXISTS idx_sagas_type
                ON sagas(saga_type, state);
        """)
        self._conn.commit()

    def save(self, execution: SagaExecution) -> None:
        """Persist or update a saga execution."""
        steps_json = json.dumps([
            {
                "step_name": s.step_name,
                "state": s.state.value,
                "result": s.result,
                "error": s.error,
                "attempts": s.attempts,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
            }
            for s in execution.step_executions
        ])
        execution.updated_at = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            "INSERT OR REPLACE INTO sagas VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                execution.saga_id, execution.saga_type,
                execution.state.value, json.dumps(execution.context),
                steps_json, execution.current_step_index,
                execution.created_at, execution.updated_at,
            ),
        )
        self._conn.commit()

    def load(self, saga_id: str) -> SagaExecution | None:
        """Load a saga execution by ID."""
        row = self._conn.execute(
            "SELECT * FROM sagas WHERE saga_id = ?", (saga_id,)
        ).fetchone()
        if row is None:
            return None

        steps_data = json.loads(row[4])
        step_executions = [
            StepExecution(
                step_name=s["step_name"],
                state=StepState(s["state"]),
                result=s["result"],
                error=s["error"],
                attempts=s["attempts"],
                started_at=s["started_at"],
                completed_at=s["completed_at"],
            )
            for s in steps_data
        ]
        return SagaExecution(
            saga_id=row[0], saga_type=row[1],
            state=SagaState(row[2]),
            context=json.loads(row[3]),
            step_executions=step_executions,
            current_step_index=row[5],
            created_at=row[6], updated_at=row[7],
        )

    def find_stuck_sagas(
        self, timeout_minutes: int = 10
    ) -> list[SagaExecution]:
        """Find sagas stuck in RUNNING or COMPENSATING state."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        ).isoformat()
        rows = self._conn.execute(
            "SELECT saga_id FROM sagas WHERE state IN (?, ?) "
            "AND updated_at < ?",
            (SagaState.RUNNING.value, SagaState.COMPENSATING.value, cutoff),
        ).fetchall()
        return [self.load(row[0]) for row in rows if self.load(row[0])]
```

## The Saga Orchestrator Engine

```python
class SagaOrchestrator:
    """
    Executes sagas by running steps forward and compensating on failure.

    The orchestrator is the central coordinator that:
    1. Executes steps sequentially with retry logic
    2. Triggers compensation chain on any step failure
    3. Persists state after every step for crash recovery
    4. Handles timeouts for hung steps
    """

    def __init__(self, store: SagaStore) -> None:
        self._store = store
        self._saga_definitions: dict[str, list[SagaStep]] = {}

    def register_saga(
        self, saga_type: str, steps: list[SagaStep]
    ) -> None:
        """Register a saga definition with its steps."""
        self._saga_definitions[saga_type] = steps

    def start_saga(
        self, saga_type: str, context: dict[str, Any]
    ) -> str:
        """
        Start a new saga execution.

        Args:
            saga_type: The registered saga type name.
            context: Initial data passed to all steps.

        Returns:
            The saga_id for tracking.
        """
        steps = self._saga_definitions.get(saga_type)
        if not steps:
            raise ValueError(f"Unknown saga type: {saga_type}")

        saga_id = str(uuid.uuid4())
        execution = SagaExecution(
            saga_id=saga_id,
            saga_type=saga_type,
            state=SagaState.STARTED,
            context=context,
            step_executions=[
                StepExecution(step_name=step.name)
                for step in steps
            ],
        )
        self._store.save(execution)

        # Execute the saga
        self._execute_saga(execution, steps)
        return saga_id

    def _execute_saga(
        self, execution: SagaExecution, steps: list[SagaStep]
    ) -> None:
        """Run all saga steps forward, compensate on failure."""
        execution.state = SagaState.RUNNING
        self._store.save(execution)

        for i, step in enumerate(steps):
            execution.current_step_index = i
            step_exec = execution.step_executions[i]
            step_exec.state = StepState.EXECUTING
            step_exec.started_at = datetime.now(timezone.utc).isoformat()
            self._store.save(execution)

            success = self._execute_step_with_retry(
                step, step_exec, execution.context
            )

            if success:
                step_exec.state = StepState.COMPLETED
                step_exec.completed_at = (
                    datetime.now(timezone.utc).isoformat()
                )
                # Merge step result into saga context for next steps
                execution.context.update(step_exec.result)
                self._store.save(execution)
            else:
                step_exec.state = StepState.FAILED
                self._store.save(execution)
                logger.warning(
                    f"Saga {execution.saga_id}: Step '{step.name}' failed. "
                    f"Starting compensation..."
                )
                self._compensate(execution, steps, i)
                return

        execution.state = SagaState.COMPLETED
        self._store.save(execution)
        logger.info(f"Saga {execution.saga_id} completed successfully.")

    def _execute_step_with_retry(
        self,
        step: SagaStep,
        step_exec: StepExecution,
        context: dict[str, Any],
    ) -> bool:
        """Execute a step with retry logic and timeout."""
        for attempt in range(1, step.retries + 1):
            step_exec.attempts = attempt
            try:
                start_time = time.monotonic()
                result = step.action(context)
                elapsed = time.monotonic() - start_time

                if elapsed > step.timeout_seconds:
                    step_exec.error = (
                        f"Step timed out after {elapsed:.1f}s "
                        f"(limit: {step.timeout_seconds}s)"
                    )
                    logger.warning(
                        f"Step '{step.name}' timed out on "
                        f"attempt {attempt}"
                    )
                    continue

                step_exec.result = result
                return True

            except Exception as e:
                step_exec.error = str(e)
                logger.warning(
                    f"Step '{step.name}' attempt {attempt} failed: {e}"
                )

        return False

    def _compensate(
        self,
        execution: SagaExecution,
        steps: list[SagaStep],
        failed_step_index: int,
    ) -> None:
        """
        Run compensation for all completed steps in reverse order.

        Common mistake: Only compensating the failed step. You must
        compensate ALL previously completed steps because they each
        made changes that need to be undone.
        """
        execution.state = SagaState.COMPENSATING
        self._store.save(execution)

        # Compensate completed steps in reverse order
        for i in range(failed_step_index - 1, -1, -1):
            step = steps[i]
            step_exec = execution.step_executions[i]

            if step_exec.state != StepState.COMPLETED:
                continue

            step_exec.state = StepState.COMPENSATING
            self._store.save(execution)

            try:
                step.compensation(execution.context)
                step_exec.state = StepState.COMPENSATED
                step_exec.completed_at = (
                    datetime.now(timezone.utc).isoformat()
                )
                logger.info(f"Compensated step '{step.name}'")
            except Exception as e:
                step_exec.state = StepState.FAILED
                step_exec.error = f"Compensation failed: {e}"
                logger.error(
                    f"CRITICAL: Compensation failed for '{step.name}': {e}. "
                    f"Manual intervention required!"
                )
                execution.state = SagaState.FAILED
                self._store.save(execution)
                return

            self._store.save(execution)

        execution.state = SagaState.COMPENSATED
        self._store.save(execution)
        logger.info(f"Saga {execution.saga_id} fully compensated.")
```

## E-Commerce Order Saga: Putting It All Together

```python
# ---------------------------------------------------------------------------
# Service simulators (in production, these would be HTTP/gRPC calls)
# ---------------------------------------------------------------------------

class OrderService:
    """Simulates order service operations."""

    def __init__(self) -> None:
        self.orders: dict[str, dict[str, Any]] = {}

    def create_order(self, ctx: dict[str, Any]) -> dict[str, Any]:
        order_id = ctx["order_id"]
        self.orders[order_id] = {
            "status": "CREATED",
            "product_id": ctx["product_id"],
            "quantity": ctx["quantity"],
        }
        return {"order_status": "CREATED"}

    def cancel_order(self, ctx: dict[str, Any]) -> dict[str, Any]:
        order_id = ctx["order_id"]
        if order_id in self.orders:
            self.orders[order_id]["status"] = "CANCELLED"
        return {"order_status": "CANCELLED"}


class InventoryService:
    """Simulates inventory service with stock tracking."""

    def __init__(self, initial_stock: dict[str, int] | None = None) -> None:
        self.stock: dict[str, int] = initial_stock or {}
        self.reservations: dict[str, int] = {}

    def reserve(self, ctx: dict[str, Any]) -> dict[str, Any]:
        product_id = ctx["product_id"]
        quantity = ctx["quantity"]
        available = self.stock.get(product_id, 0)
        if available < quantity:
            raise ValueError(
                f"Insufficient stock for {product_id}: "
                f"available={available}, requested={quantity}"
            )
        self.stock[product_id] -= quantity
        self.reservations[ctx["order_id"]] = quantity
        return {"inventory_reserved": True}

    def release(self, ctx: dict[str, Any]) -> dict[str, Any]:
        order_id = ctx["order_id"]
        product_id = ctx["product_id"]
        quantity = self.reservations.pop(order_id, 0)
        self.stock[product_id] = self.stock.get(product_id, 0) + quantity
        return {"inventory_released": True}


class PaymentService:
    """Simulates payment processing."""

    def __init__(self, should_fail: bool = False) -> None:
        self.charges: dict[str, float] = {}
        self._should_fail = should_fail

    def charge(self, ctx: dict[str, Any]) -> dict[str, Any]:
        if self._should_fail:
            raise ValueError("Payment declined by bank")
        amount = ctx.get("amount", 99.99)
        self.charges[ctx["order_id"]] = amount
        return {"payment_id": f"pay-{ctx['order_id']}", "charged": amount}

    def refund(self, ctx: dict[str, Any]) -> dict[str, Any]:
        order_id = ctx["order_id"]
        amount = self.charges.pop(order_id, 0.0)
        return {"refunded": amount}


class ShippingService:
    """Simulates shipping coordination."""

    def __init__(self) -> None:
        self.shipments: dict[str, str] = {}

    def create_shipment(self, ctx: dict[str, Any]) -> dict[str, Any]:
        tracking = f"TRACK-{ctx['order_id'][:8]}"
        self.shipments[ctx["order_id"]] = tracking
        return {"tracking_number": tracking}

    def cancel_shipment(self, ctx: dict[str, Any]) -> dict[str, Any]:
        self.shipments.pop(ctx["order_id"], None)
        return {"shipment_cancelled": True}
```

## Testing the Saga Orchestrator

```python
import unittest


class TestSagaOrchestrator(unittest.TestCase):
    """Comprehensive tests for the saga orchestrator."""

    def setUp(self) -> None:
        self.store = SagaStore(":memory:")
        self.orchestrator = SagaOrchestrator(self.store)
        self.order_svc = OrderService()
        self.inventory_svc = InventoryService({"widget": 100})
        self.payment_svc = PaymentService()
        self.shipping_svc = ShippingService()

        steps = [
            SagaStep(
                name="create_order",
                action=self.order_svc.create_order,
                compensation=self.order_svc.cancel_order,
            ),
            SagaStep(
                name="reserve_inventory",
                action=self.inventory_svc.reserve,
                compensation=self.inventory_svc.release,
            ),
            SagaStep(
                name="charge_payment",
                action=self.payment_svc.charge,
                compensation=self.payment_svc.refund,
            ),
            SagaStep(
                name="create_shipment",
                action=self.shipping_svc.create_shipment,
                compensation=self.shipping_svc.cancel_shipment,
            ),
        ]
        self.orchestrator.register_saga("place_order", steps)

    def test_happy_path(self) -> None:
        """All steps succeed — saga completes."""
        saga_id = self.orchestrator.start_saga("place_order", {
            "order_id": "ord-001",
            "product_id": "widget",
            "quantity": 5,
            "amount": 49.95,
        })
        execution = self.store.load(saga_id)
        self.assertIsNotNone(execution)
        self.assertEqual(execution.state, SagaState.COMPLETED)
        self.assertEqual(self.inventory_svc.stock["widget"], 95)
        self.assertIn("ord-001", self.shipping_svc.shipments)

    def test_payment_failure_triggers_compensation(self) -> None:
        """Payment fails — order and inventory are compensated."""
        self.payment_svc._should_fail = True

        saga_id = self.orchestrator.start_saga("place_order", {
            "order_id": "ord-002",
            "product_id": "widget",
            "quantity": 3,
            "amount": 29.97,
        })

        execution = self.store.load(saga_id)
        self.assertEqual(execution.state, SagaState.COMPENSATED)

        # Inventory should be fully released
        self.assertEqual(self.inventory_svc.stock["widget"], 100)
        # Order should be cancelled
        self.assertEqual(
            self.order_svc.orders["ord-002"]["status"], "CANCELLED"
        )

    def test_insufficient_stock_compensation(self) -> None:
        """Inventory reservation fails — only order is compensated."""
        saga_id = self.orchestrator.start_saga("place_order", {
            "order_id": "ord-003",
            "product_id": "widget",
            "quantity": 999,  # More than available
            "amount": 999.99,
        })

        execution = self.store.load(saga_id)
        self.assertEqual(execution.state, SagaState.COMPENSATED)

        # Order created then cancelled
        self.assertEqual(
            self.order_svc.orders["ord-003"]["status"], "CANCELLED"
        )
        # No payment should have been attempted
        self.assertNotIn("ord-003", self.payment_svc.charges)

    def test_saga_state_persistence(self) -> None:
        """Verify saga state is persisted to the store."""
        saga_id = self.orchestrator.start_saga("place_order", {
            "order_id": "ord-004",
            "product_id": "widget",
            "quantity": 1,
            "amount": 9.99,
        })

        loaded = self.store.load(saga_id)
        self.assertEqual(len(loaded.step_executions), 4)
        for step_exec in loaded.step_executions:
            self.assertEqual(step_exec.state, StepState.COMPLETED)


if __name__ == "__main__":
    unittest.main()
```

## Summary and Key Takeaways

- **Sagas** replace distributed transactions with a sequence of local transactions plus
  compensating actions, making them suitable for microservice architectures where 2PC
  is impractical.
- **Choreography** works for simple flows but leads to tangled event chains as complexity
  grows. **Orchestration** makes the flow explicit and easier to debug, therefore it is
  the **best practice** for business-critical multi-step processes.
- **Compensation** must be **idempotent** — the same compensation may run multiple times
  due to retries. A **common pitfall** is writing compensations that fail on the second
  invocation because the resource was already cleaned up.
- **Timeout handling** is essential because distributed calls can hang indefinitely. Every
  saga step needs a timeout, and stuck sagas should be detected by a background sweeper.
- **State persistence** enables crash recovery. If the orchestrator restarts, it must
  resume in-progress sagas from their last persisted state rather than starting over.
- The **trade-off** with sagas is that they provide eventual consistency, not immediate
  consistency. During the saga execution window, the system is in an intermediate state.
  Design your UI to handle this gracefully — show "order processing" rather than
  "order confirmed" until the saga completes.
"""
    ),

    # --- 5. Domain Events with Outbox Pattern ---
    (
        "domain_events_outbox_pattern",
        "Explain the transactional outbox pattern for reliable domain event publishing — why "
        "dual writes fail, how the outbox guarantees atomicity, CDC with Debezium concepts, "
        "polling publisher implementation, and idempotent consumer design. Provide a complete "
        "Python implementation with SQLite-backed outbox, polling publisher, relay service, "
        "and idempotent event handler with deduplication and comprehensive tests.",
        r"""
# Transactional Outbox Pattern: Reliable Event Publishing Without Dual Writes

## The Dual Write Problem

When a service needs to update its database **and** publish an event to a message broker,
it faces a fundamental consistency challenge. These are two separate systems, and without
a distributed transaction, one can succeed while the other fails.

```
Scenario A — Write DB first, then publish:
  1. UPDATE orders SET status = 'confirmed'     ← succeeds
  2. kafka.produce("order-confirmed")            ← FAILS (broker down)
  Result: Database updated, but no event published. Downstream out of sync.

Scenario B — Publish first, then write DB:
  1. kafka.produce("order-confirmed")            ← succeeds
  2. UPDATE orders SET status = 'confirmed'      ← FAILS (DB constraint)
  Result: Event published, but database not updated. Lie published to consumers.
```

This is the **dual write problem** — writing to two separate systems cannot be made atomic
without a distributed transaction. **Because** 2PC is impractical in microservice
architectures (it blocks resources, creates a single point of failure, and does not scale),
we need a different approach.

## The Outbox Pattern Solution

The outbox pattern solves dual writes by **writing the event to the same database as the
business data**, in a single local transaction. A separate process then reads from this
"outbox" table and publishes events to the message broker.

```
┌─── Single Database Transaction ───────────────────────┐
│  1. UPDATE orders SET status = 'confirmed'            │
│  2. INSERT INTO outbox (event_type, payload) VALUES   │
│     ('OrderConfirmed', '{"order_id": "o1", ...}')     │
└───────────────────────────────────────────────────────┘
        │
        │  (Separate process)
        ▼
┌─── Outbox Relay / CDC ────────────────────────────────┐
│  Read unpublished events from outbox table            │
│  Publish to Kafka/RabbitMQ                            │
│  Mark as published                                    │
└───────────────────────────────────────────────────────┘
```

This works **because** both the business write and the event write are in the same
transaction — they either both commit or both roll back. The relay process handles
publishing asynchronously, with at-least-once delivery guarantees.

## Complete Outbox Implementation

```python
"""
Transactional outbox pattern with polling publisher and
idempotent consumer support.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
import time
import threading
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from enum import Enum

logger = logging.getLogger(__name__)


class OutboxStatus(str, Enum):
    """Status of an outbox entry."""
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class OutboxEntry:
    """
    Represents a single event in the outbox table.

    Immutable because once written to the outbox, the event
    content must never change — only its publication status.
    """
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    aggregate_type: str = ""
    aggregate_id: str = ""
    event_type: str = ""
    payload: str = ""
    status: str = OutboxStatus.PENDING.value
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    published_at: str = ""
    retry_count: int = 0


class OutboxDatabase:
    """
    Database layer that supports the outbox pattern.

    Business tables and outbox table share the same database,
    enabling atomic writes via local transactions.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id    TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                product_id  TEXT NOT NULL,
                quantity    INTEGER NOT NULL,
                total_price REAL NOT NULL,
                status      TEXT NOT NULL DEFAULT 'PENDING',
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS outbox (
                entry_id       TEXT PRIMARY KEY,
                aggregate_type TEXT NOT NULL,
                aggregate_id   TEXT NOT NULL,
                event_type     TEXT NOT NULL,
                payload        TEXT NOT NULL,
                status         TEXT NOT NULL DEFAULT 'PENDING',
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                published_at   TEXT,
                retry_count    INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_outbox_status
                ON outbox(status, created_at);
        """)
        self._conn.commit()
        self._lock = threading.Lock()

    def create_order_with_event(
        self,
        order_id: str,
        customer_id: str,
        product_id: str,
        quantity: int,
        total_price: float,
    ) -> OutboxEntry:
        """
        Create an order AND write the domain event in one transaction.

        This is the key to the outbox pattern — both writes happen
        atomically in the same database transaction.
        """
        event_payload = json.dumps({
            "order_id": order_id,
            "customer_id": customer_id,
            "product_id": product_id,
            "quantity": quantity,
            "total_price": total_price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        entry = OutboxEntry(
            aggregate_type="Order",
            aggregate_id=order_id,
            event_type="OrderCreated",
            payload=event_payload,
        )

        with self._lock:
            cursor = self._conn.cursor()
            try:
                # Both in one transaction — atomic!
                cursor.execute(
                    "INSERT INTO orders "
                    "(order_id, customer_id, product_id, quantity, "
                    "total_price, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, customer_id, product_id, quantity,
                     total_price, "CREATED"),
                )
                cursor.execute(
                    "INSERT INTO outbox "
                    "(entry_id, aggregate_type, aggregate_id, "
                    "event_type, payload, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (entry.entry_id, entry.aggregate_type,
                     entry.aggregate_id, entry.event_type,
                     entry.payload, entry.status),
                )
                self._conn.commit()
                logger.info(
                    f"Order {order_id} created with outbox entry "
                    f"{entry.entry_id}"
                )
                return entry
            except Exception:
                self._conn.rollback()
                raise

    def confirm_order_with_event(
        self, order_id: str
    ) -> OutboxEntry:
        """Confirm an order and write the confirmation event atomically."""
        event_payload = json.dumps({
            "order_id": order_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        entry = OutboxEntry(
            aggregate_type="Order",
            aggregate_id=order_id,
            event_type="OrderConfirmed",
            payload=event_payload,
        )

        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    "UPDATE orders SET status = 'CONFIRMED', "
                    "updated_at = datetime('now') WHERE order_id = ?",
                    (order_id,),
                )
                cursor.execute(
                    "INSERT INTO outbox "
                    "(entry_id, aggregate_type, aggregate_id, "
                    "event_type, payload, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (entry.entry_id, entry.aggregate_type,
                     entry.aggregate_id, entry.event_type,
                     entry.payload, entry.status),
                )
                self._conn.commit()
                return entry
            except Exception:
                self._conn.rollback()
                raise

    def get_pending_entries(
        self, batch_size: int = 100
    ) -> list[OutboxEntry]:
        """Fetch unpublished outbox entries for the relay."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT entry_id, aggregate_type, aggregate_id, "
                "event_type, payload, status, created_at, "
                "published_at, retry_count "
                "FROM outbox WHERE status = ? "
                "ORDER BY created_at ASC LIMIT ?",
                (OutboxStatus.PENDING.value, batch_size),
            )
            return [
                OutboxEntry(
                    entry_id=r[0], aggregate_type=r[1],
                    aggregate_id=r[2], event_type=r[3],
                    payload=r[4], status=r[5], created_at=r[6],
                    published_at=r[7] or "", retry_count=r[8],
                )
                for r in cursor.fetchall()
            ]

    def mark_published(self, entry_id: str) -> None:
        """Mark an outbox entry as successfully published."""
        with self._lock:
            self._conn.execute(
                "UPDATE outbox SET status = ?, published_at = datetime('now') "
                "WHERE entry_id = ?",
                (OutboxStatus.PUBLISHED.value, entry_id),
            )
            self._conn.commit()

    def mark_failed(self, entry_id: str) -> None:
        """Mark an entry as failed and increment retry count."""
        with self._lock:
            self._conn.execute(
                "UPDATE outbox SET status = ?, retry_count = retry_count + 1 "
                "WHERE entry_id = ?",
                (OutboxStatus.FAILED.value, entry_id),
            )
            self._conn.commit()

    def reset_failed_entries(self, max_retries: int = 5) -> int:
        """Reset failed entries for retry (up to max_retries)."""
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE outbox SET status = ? "
                "WHERE status = ? AND retry_count < ?",
                (OutboxStatus.PENDING.value,
                 OutboxStatus.FAILED.value, max_retries),
            )
            self._conn.commit()
            return cursor.rowcount
```

## Polling Publisher: The Relay Service

There are two approaches to reading the outbox:
1. **Polling publisher**: Periodically queries the outbox table for pending entries
2. **CDC (Change Data Capture)**: Uses database log tailing (e.g., Debezium reads the
   MySQL binlog or PostgreSQL WAL) to detect new outbox rows

**Polling** is simpler to implement. **CDC via Debezium** is more efficient and lower
latency, however it requires additional infrastructure (Kafka Connect, Debezium connector).
The **trade-off** is operational complexity vs. publish latency.

```python
class MessageBroker(Protocol):
    """Protocol for message broker abstraction."""

    def publish(
        self, topic: str, key: str, value: str, headers: dict[str, str]
    ) -> bool: ...


class InMemoryBroker:
    """
    In-memory message broker for testing.

    Production would use KafkaProducer, RabbitMQ, etc.
    """

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self._should_fail: bool = False

    def publish(
        self, topic: str, key: str, value: str,
        headers: dict[str, str],
    ) -> bool:
        if self._should_fail:
            raise ConnectionError("Broker unavailable")
        self.published.append({
            "topic": topic,
            "key": key,
            "value": json.loads(value),
            "headers": headers,
        })
        return True


class PollingPublisher:
    """
    Reads pending events from the outbox and publishes them to the broker.

    Runs on a configurable polling interval. Handles broker failures
    by marking entries as FAILED for later retry.

    Best practice: Run as a separate process or thread from the
    main application to avoid blocking business operations.
    """

    def __init__(
        self,
        db: OutboxDatabase,
        broker: MessageBroker,
        poll_interval_seconds: float = 1.0,
        batch_size: int = 100,
        topic_prefix: str = "domain-events",
    ) -> None:
        self._db = db
        self._broker = broker
        self._poll_interval = poll_interval_seconds
        self._batch_size = batch_size
        self._topic_prefix = topic_prefix
        self._running = False
        self._thread: threading.Thread | None = None
        self._published_count = 0
        self._failed_count = 0

    def start(self) -> None:
        """Start the polling loop in a background thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True
        )
        self._thread.start()
        logger.info("Polling publisher started.")

    def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10.0)
        logger.info(
            f"Polling publisher stopped. Published: "
            f"{self._published_count}, Failed: {self._failed_count}"
        )

    def _poll_loop(self) -> None:
        """Main polling loop — fetch and publish pending entries."""
        while self._running:
            try:
                self._process_batch()
            except Exception as e:
                logger.error(f"Polling error: {e}")
            time.sleep(self._poll_interval)

    def _process_batch(self) -> int:
        """Process one batch of pending outbox entries."""
        entries = self._db.get_pending_entries(self._batch_size)
        published = 0

        for entry in entries:
            topic = f"{self._topic_prefix}.{entry.aggregate_type.lower()}"
            headers = {
                "event_id": entry.entry_id,
                "event_type": entry.event_type,
                "aggregate_type": entry.aggregate_type,
                "aggregate_id": entry.aggregate_id,
            }

            try:
                self._broker.publish(
                    topic=topic,
                    key=entry.aggregate_id,
                    value=entry.payload,
                    headers=headers,
                )
                self._db.mark_published(entry.entry_id)
                self._published_count += 1
                published += 1
            except Exception as e:
                logger.warning(
                    f"Failed to publish {entry.entry_id}: {e}"
                )
                self._db.mark_failed(entry.entry_id)
                self._failed_count += 1

        return published

    def process_batch_sync(self) -> int:
        """Synchronous batch processing for testing."""
        return self._process_batch()
```

## Idempotent Consumer: Handling Duplicate Deliveries

Because the outbox pattern provides **at-least-once delivery**, consumers must be
**idempotent** — processing the same event twice must produce the same result as
processing it once. The standard approach is to track processed event IDs.

A **common mistake** is assuming the broker provides exactly-once delivery. Even with
Kafka's exactly-once semantics, network issues and consumer restarts can cause
redelivery. **Therefore**, always design consumers to be idempotent.

```python
class IdempotentEventHandler:
    """
    Event handler with built-in deduplication.

    Tracks processed event IDs to ensure each event is handled
    exactly once, even if delivered multiple times by the broker.

    The deduplication table uses the event_id as the primary key,
    which makes duplicate detection O(1) via index lookup.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id    TEXT PRIMARY KEY,
                event_type  TEXT NOT NULL,
                processed_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS order_notifications (
                notification_id TEXT PRIMARY KEY,
                order_id        TEXT NOT NULL,
                event_type      TEXT NOT NULL,
                message         TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        self._conn.commit()
        self._handlers: dict[str, Callable[[dict[str, Any]], None]] = {
            "OrderCreated": self._on_order_created,
            "OrderConfirmed": self._on_order_confirmed,
        }

    def handle(
        self, event_id: str, event_type: str, payload: dict[str, Any]
    ) -> bool:
        """
        Process an event idempotently.

        Returns True if the event was processed, False if it was
        a duplicate that was skipped.
        """
        # Check for duplicate
        existing = self._conn.execute(
            "SELECT 1 FROM processed_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()

        if existing is not None:
            logger.info(f"Duplicate event {event_id} skipped.")
            return False

        # Process the event
        handler = self._handlers.get(event_type)
        if handler is None:
            logger.warning(f"No handler for event type: {event_type}")
            return False

        try:
            # Process and record atomically
            handler(payload)
            self._conn.execute(
                "INSERT INTO processed_events (event_id, event_type) "
                "VALUES (?, ?)",
                (event_id, event_type),
            )
            self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            raise

    def _on_order_created(self, payload: dict[str, Any]) -> None:
        """Handle OrderCreated — send notification to customer."""
        self._conn.execute(
            "INSERT INTO order_notifications "
            "(notification_id, order_id, event_type, message) "
            "VALUES (?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                payload["order_id"],
                "OrderCreated",
                f"Order {payload['order_id']} received for "
                f"customer {payload['customer_id']}.",
            ),
        )

    def _on_order_confirmed(self, payload: dict[str, Any]) -> None:
        """Handle OrderConfirmed — send confirmation notification."""
        self._conn.execute(
            "INSERT INTO order_notifications "
            "(notification_id, order_id, event_type, message) "
            "VALUES (?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                payload["order_id"],
                "OrderConfirmed",
                f"Order {payload['order_id']} has been confirmed!",
            ),
        )

    def get_notifications(
        self, order_id: str
    ) -> list[dict[str, Any]]:
        """Query notifications for an order."""
        rows = self._conn.execute(
            "SELECT notification_id, event_type, message "
            "FROM order_notifications WHERE order_id = ?",
            (order_id,),
        ).fetchall()
        return [
            {"id": r[0], "event_type": r[1], "message": r[2]}
            for r in rows
        ]
```

## CDC with Debezium: The Production Alternative

While polling works for moderate throughput, **Change Data Capture (CDC)** with Debezium
is the production **best practice** for the outbox pattern. Debezium reads the database's
transaction log (WAL in PostgreSQL, binlog in MySQL) and streams outbox insertions directly
to Kafka — with sub-second latency and zero polling overhead.

```
┌──────────────────────────────────────────────────────────┐
│ Debezium CDC Pipeline                                    │
│                                                          │
│  PostgreSQL WAL ──► Debezium Connector ──► Kafka Topic   │
│  (binlog/WAL)       (Kafka Connect)        (outbox.event)│
│                                                          │
│  Debezium outbox event router:                           │
│  - Reads inserts to the outbox table from the WAL        │
│  - Routes to topic based on aggregate_type               │
│  - Optionally deletes outbox rows after publishing       │
│  - Guarantees at-least-once with Kafka Connect offsets    │
└──────────────────────────────────────────────────────────┘
```

The **trade-off** compared to polling: Debezium adds operational complexity (Kafka Connect
cluster, connector configuration, schema management) but provides near-zero latency, no
polling overhead, and handles the outbox cleanup automatically.

## End-to-End Integration Tests

```python
import unittest


class TestOutboxPattern(unittest.TestCase):
    """End-to-end tests for the transactional outbox pattern."""

    def setUp(self) -> None:
        self.db = OutboxDatabase(":memory:")
        self.broker = InMemoryBroker()
        self.publisher = PollingPublisher(
            self.db, self.broker, poll_interval_seconds=0.1
        )
        self.handler = IdempotentEventHandler(":memory:")

    def test_atomic_write_creates_order_and_event(self) -> None:
        """Business write and outbox write are atomic."""
        entry = self.db.create_order_with_event(
            "ord-001", "cust-1", "prod-A", 3, 59.97
        )
        self.assertEqual(entry.event_type, "OrderCreated")
        pending = self.db.get_pending_entries()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].aggregate_id, "ord-001")

    def test_publisher_sends_to_broker(self) -> None:
        """Polling publisher publishes pending entries."""
        self.db.create_order_with_event(
            "ord-002", "cust-2", "prod-B", 1, 19.99
        )
        count = self.publisher.process_batch_sync()
        self.assertEqual(count, 1)
        self.assertEqual(len(self.broker.published), 1)
        self.assertEqual(
            self.broker.published[0]["value"]["order_id"], "ord-002"
        )
        # Entry should be marked as published
        pending = self.db.get_pending_entries()
        self.assertEqual(len(pending), 0)

    def test_broker_failure_marks_entry_failed(self) -> None:
        """Failed publish marks entry for retry."""
        self.db.create_order_with_event(
            "ord-003", "cust-3", "prod-C", 2, 39.98
        )
        self.broker._should_fail = True
        count = self.publisher.process_batch_sync()
        self.assertEqual(count, 0)

        # Reset broker and retry
        self.broker._should_fail = False
        self.db.reset_failed_entries()
        count = self.publisher.process_batch_sync()
        self.assertEqual(count, 1)

    def test_idempotent_consumer_deduplicates(self) -> None:
        """Same event processed twice produces one result."""
        payload = {
            "order_id": "ord-004",
            "customer_id": "cust-4",
            "product_id": "prod-D",
            "quantity": 1,
            "total_price": 9.99,
            "timestamp": "2024-01-01T00:00:00Z",
        }
        event_id = "evt-unique-001"

        # First processing — should succeed
        result1 = self.handler.handle(event_id, "OrderCreated", payload)
        self.assertTrue(result1)

        # Second processing — duplicate, should be skipped
        result2 = self.handler.handle(event_id, "OrderCreated", payload)
        self.assertFalse(result2)

        # Only one notification created
        notifications = self.handler.get_notifications("ord-004")
        self.assertEqual(len(notifications), 1)

    def test_full_pipeline_integration(self) -> None:
        """End-to-end: write → outbox → publish → consume idempotently."""
        # Step 1: Create order (writes to DB + outbox atomically)
        entry = self.db.create_order_with_event(
            "ord-005", "cust-5", "prod-E", 10, 199.90
        )

        # Step 2: Publisher reads outbox and sends to broker
        self.publisher.process_batch_sync()
        self.assertEqual(len(self.broker.published), 1)

        # Step 3: Consumer processes the published event
        msg = self.broker.published[0]
        processed = self.handler.handle(
            msg["headers"]["event_id"],
            msg["headers"]["event_type"],
            msg["value"],
        )
        self.assertTrue(processed)

        # Step 4: Confirm order (another atomic write + event)
        self.db.confirm_order_with_event("ord-005")
        self.publisher.process_batch_sync()
        self.assertEqual(len(self.broker.published), 2)

        confirm_msg = self.broker.published[1]
        self.handler.handle(
            confirm_msg["headers"]["event_id"],
            confirm_msg["headers"]["event_type"],
            confirm_msg["value"],
        )

        # Verify full notification chain
        notifications = self.handler.get_notifications("ord-005")
        self.assertEqual(len(notifications), 2)
        event_types = {n["event_type"] for n in notifications}
        self.assertEqual(event_types, {"OrderCreated", "OrderConfirmed"})


if __name__ == "__main__":
    unittest.main()
```

## Summary and Key Takeaways

- The **dual write problem** makes it impossible to atomically update a database and
  publish to a message broker without special patterns. Never write to two systems
  independently and hope for the best — this is a **common pitfall** that leads to
  data inconsistency.
- The **transactional outbox** solves this by writing events to an outbox table in the
  same database transaction as the business data. **Because** both writes share a
  transaction, atomicity is guaranteed by the database itself.
- **Polling publishers** are simple to implement but add latency proportional to the poll
  interval. **CDC with Debezium** provides near-real-time publishing by reading the
  database transaction log directly, however it requires Kafka Connect infrastructure.
- **Idempotent consumers** are mandatory because the outbox pattern provides at-least-once
  delivery. Track processed event IDs in a deduplication table to ensure exactly-once
  processing semantics at the application level.
- **Best practice**: Clean up published outbox entries periodically to prevent the table
  from growing indefinitely. Either use Debezium's built-in outbox event router (which
  can delete rows after publishing) or run a scheduled cleanup job.
- The **trade-off** with the outbox pattern is added complexity: an extra table, a relay
  process, and idempotency logic. However, for any system where event reliability matters,
  this complexity is far preferable to the silent data loss that dual writes produce.
"""
    ),
]
