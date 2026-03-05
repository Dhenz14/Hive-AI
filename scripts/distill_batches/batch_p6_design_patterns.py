"""
Batch P6 -- Design Patterns: repository/UoW, CQRS, dependency injection,
observer/event bus, strategy/chain of responsibility.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Repository and Unit of Work Patterns ---
    (
        "repository_unit_of_work_pattern_python_sqlalchemy",
        "Explain the Repository and Unit of Work design patterns in depth -- abstracting "
        "data access behind clean interfaces, managing transactions with the Unit of Work pattern, "
        "testing business logic with in-memory repository implementations, building a complete "
        "Python and SQLAlchemy implementation, handling aggregate boundaries, and avoiding common "
        "pitfalls that arise in layered enterprise applications.",
        r"""
# Repository and Unit of Work Patterns: Clean Data Access Abstractions

## Why Repository and Unit of Work Matter

Most applications start with data access code scattered directly through business logic --
raw SQL queries in route handlers, ORM calls embedded in domain services. This works
initially, **because** the application is small and the team understands every query. However,
as the codebase grows, this approach creates devastating coupling: business logic cannot be
tested without a database, queries cannot be optimized without touching domain code, and
switching data stores becomes a rewrite.

The **Repository pattern** solves this by providing a **collection-like interface** over your
data store. Domain code works with repositories as if they were in-memory collections --
`add()`, `get()`, `list()` -- completely unaware of SQL, ORM sessions, or connection pools
underneath. The **Unit of Work pattern** complements this by managing **transaction boundaries**:
it tracks which objects were modified during a business operation and commits or rolls back
all changes atomically.

**Common mistake**: Developers often create "generic repositories" with methods like
`get_by_id()`, `get_all()`, `filter_by()` that simply mirror the ORM. This defeats the
purpose. A **best practice** is to design repository interfaces around **domain operations**:
`find_active_users_in_region()`, `get_order_with_line_items()`. The interface should speak
the language of the domain, not the language of SQL.

## Defining the Abstract Interfaces

The foundation is a set of **abstract base classes** (or Protocol classes) that define what
the domain layer needs, without specifying how persistence works.

```python
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Protocol, Optional, List, Set, runtime_checkable
from datetime import datetime, timezone
import uuid

# ---------------------------------------------------------------------------
# Domain entities -- pure data, no ORM dependencies
# ---------------------------------------------------------------------------

@dataclass
class OrderLine:
    # Represents a single item in an order
    sku: str
    quantity: int
    price_cents: int
    line_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def total_cents(self) -> int:
        return self.quantity * self.price_cents


@dataclass
class Order:
    # Aggregate root -- all access goes through this entity
    order_id: str
    customer_id: str
    lines: List[OrderLine] = field(default_factory=list)
    status: str = "pending"
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def total_cents(self) -> int:
        return sum(line.total_cents for line in self.lines)

    def add_line(self, sku: str, quantity: int, price_cents: int) -> OrderLine:
        # Business rule: cannot add to completed orders
        if self.status == "completed":
            raise ValueError("Cannot modify a completed order")
        line = OrderLine(sku=sku, quantity=quantity, price_cents=price_cents)
        self.lines.append(line)
        return line

    def complete(self) -> None:
        if not self.lines:
            raise ValueError("Cannot complete an order with no items")
        self.status = "completed"


# ---------------------------------------------------------------------------
# Repository interface -- domain-oriented, not CRUD-oriented
# ---------------------------------------------------------------------------

class OrderRepository(abc.ABC):
    # Abstract interface for order persistence
    # Notice: methods are domain operations, not generic CRUD

    @abc.abstractmethod
    def add(self, order: Order) -> None:
        # Persist a new order
        ...

    @abc.abstractmethod
    def get(self, order_id: str) -> Optional[Order]:
        # Retrieve an order with all its line items
        ...

    @abc.abstractmethod
    def get_pending_for_customer(self, customer_id: str) -> List[Order]:
        # Domain-specific query: find all pending orders for a customer
        ...

    @abc.abstractmethod
    def list_completed_since(self, since: datetime) -> List[Order]:
        # Domain-specific query: reporting on recent completions
        ...


# ---------------------------------------------------------------------------
# Unit of Work interface -- manages transaction boundaries
# ---------------------------------------------------------------------------

class UnitOfWork(abc.ABC):
    orders: OrderRepository

    @abc.abstractmethod
    def __enter__(self) -> "UnitOfWork":
        ...

    @abc.abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Rolls back on exception, otherwise caller must commit explicitly
        ...

    @abc.abstractmethod
    def commit(self) -> None:
        ...

    @abc.abstractmethod
    def rollback(self) -> None:
        ...
```

The **trade-off** here is explicit: we write more interface code upfront, but gain testability,
separation of concerns, and the ability to swap implementations. This is worth it **because**
business logic is the most valuable and longest-lived code in your system -- it should not
be coupled to infrastructure choices.

## SQLAlchemy Implementation

Now we implement these interfaces using SQLAlchemy. The domain entities remain pure Python
dataclasses -- the repository handles mapping between domain objects and ORM models.

```python
from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import (
    declarative_base, sessionmaker, relationship, Session
)
from typing import Optional, List
from datetime import datetime

Base = declarative_base()

# ---------------------------------------------------------------------------
# ORM models -- separate from domain entities
# ---------------------------------------------------------------------------

class OrderModel(Base):
    __tablename__ = "orders"
    order_id = Column(String, primary_key=True)
    customer_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False)
    lines = relationship("OrderLineModel", back_populates="order", cascade="all, delete-orphan")


class OrderLineModel(Base):
    __tablename__ = "order_lines"
    line_id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.order_id"), nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price_cents = Column(Integer, nullable=False)
    order = relationship("OrderModel", back_populates="lines")


# ---------------------------------------------------------------------------
# Mapper functions: domain <-> ORM
# ---------------------------------------------------------------------------

def _order_to_domain(model: OrderModel) -> Order:
    # Convert ORM model to pure domain entity
    return Order(
        order_id=model.order_id,
        customer_id=model.customer_id,
        status=model.status,
        created_at=model.created_at,
        lines=[
            OrderLine(
                line_id=ln.line_id,
                sku=ln.sku,
                quantity=ln.quantity,
                price_cents=ln.price_cents,
            )
            for ln in model.lines
        ],
    )


def _order_to_model(order: Order) -> OrderModel:
    # Convert domain entity to ORM model
    return OrderModel(
        order_id=order.order_id,
        customer_id=order.customer_id,
        status=order.status,
        created_at=order.created_at,
        lines=[
            OrderLineModel(
                line_id=ln.line_id,
                order_id=order.order_id,
                sku=ln.sku,
                quantity=ln.quantity,
                price_cents=ln.price_cents,
            )
            for ln in order.lines
        ],
    )


# ---------------------------------------------------------------------------
# Concrete repository implementation
# ---------------------------------------------------------------------------

class SqlAlchemyOrderRepository(OrderRepository):
    # SQLAlchemy-backed implementation of the order repository

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, order: Order) -> None:
        self._session.add(_order_to_model(order))

    def get(self, order_id: str) -> Optional[Order]:
        model = self._session.query(OrderModel).filter_by(order_id=order_id).first()
        return _order_to_domain(model) if model else None

    def get_pending_for_customer(self, customer_id: str) -> List[Order]:
        models = (
            self._session.query(OrderModel)
            .filter_by(customer_id=customer_id, status="pending")
            .all()
        )
        return [_order_to_domain(m) for m in models]

    def list_completed_since(self, since: datetime) -> List[Order]:
        models = (
            self._session.query(OrderModel)
            .filter(OrderModel.status == "completed", OrderModel.created_at >= since)
            .order_by(OrderModel.created_at.desc())
            .all()
        )
        return [_order_to_domain(m) for m in models]


# ---------------------------------------------------------------------------
# Concrete Unit of Work
# ---------------------------------------------------------------------------

class SqlAlchemyUnitOfWork(UnitOfWork):
    # Wraps a SQLAlchemy session in the Unit of Work pattern

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self._session: Session = self._session_factory()
        self.orders = SqlAlchemyOrderRepository(self._session)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.rollback()
        self._session.close()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
```

A **pitfall** with this approach is the **identity map problem**: if you retrieve the same
entity twice within a Unit of Work, do you get the same Python object? With this mapper-based
approach, you get two separate instances. For most use cases this is fine, **because** each
business operation typically loads an entity once, mutates it, and commits. However, if you
need identity map behavior, you can add a dictionary cache inside the repository.

## In-Memory Implementation for Testing

The real power of the Repository pattern shines in testing. No database setup, no migrations,
no teardown -- just fast, deterministic tests.

```python
from typing import Optional, List, Dict
from datetime import datetime
import copy

class InMemoryOrderRepository(OrderRepository):
    # In-memory implementation for unit testing

    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}

    def add(self, order: Order) -> None:
        # Deep copy prevents test code from accidentally mutating stored state
        self._orders[order.order_id] = copy.deepcopy(order)

    def get(self, order_id: str) -> Optional[Order]:
        order = self._orders.get(order_id)
        return copy.deepcopy(order) if order else None

    def get_pending_for_customer(self, customer_id: str) -> List[Order]:
        return [
            copy.deepcopy(o)
            for o in self._orders.values()
            if o.customer_id == customer_id and o.status == "pending"
        ]

    def list_completed_since(self, since: datetime) -> List[Order]:
        return sorted(
            [
                copy.deepcopy(o)
                for o in self._orders.values()
                if o.status == "completed" and o.created_at >= since
            ],
            key=lambda o: o.created_at,
            reverse=True,
        )


class InMemoryUnitOfWork(UnitOfWork):
    # In-memory UoW for testing -- tracks committed state

    committed: bool = False

    def __enter__(self) -> "InMemoryUnitOfWork":
        self.orders = InMemoryOrderRepository()
        self.committed = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass  # nothing to clean up

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass  # in-memory state is discarded when UoW goes out of scope


# ---------------------------------------------------------------------------
# Service layer uses only the abstract UnitOfWork
# ---------------------------------------------------------------------------

def place_order(
    uow: UnitOfWork,
    customer_id: str,
    items: List[dict],
) -> str:
    # Application service -- pure business logic, no infrastructure
    with uow:
        order = Order(order_id=str(uuid.uuid4()), customer_id=customer_id)
        for item in items:
            order.add_line(
                sku=item["sku"],
                quantity=item["quantity"],
                price_cents=item["price_cents"],
            )
        uow.orders.add(order)
        uow.commit()
        return order.order_id


# ---------------------------------------------------------------------------
# Tests are fast and deterministic
# ---------------------------------------------------------------------------

def test_place_order_persists_and_commits() -> None:
    uow = InMemoryUnitOfWork()
    order_id = place_order(
        uow,
        customer_id="cust-1",
        items=[
            {"sku": "WIDGET-1", "quantity": 2, "price_cents": 999},
            {"sku": "GADGET-2", "quantity": 1, "price_cents": 1499},
        ],
    )
    # Re-enter the UoW to verify persistence
    with uow:
        order = uow.orders.get(order_id)
        assert order is not None
        assert len(order.lines) == 2
        assert order.total_cents == 2 * 999 + 1499
    assert uow.committed is True


def test_cannot_complete_empty_order() -> None:
    uow = InMemoryUnitOfWork()
    with uow:
        order = Order(order_id="ord-1", customer_id="cust-1")
        try:
            order.complete()
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "no items" in str(e).lower()
```

## Aggregate Boundaries and Best Practices

**Best practice**: Each repository manages exactly one **aggregate root**. An aggregate is a
cluster of domain objects that must be consistent together. The `Order` aggregate includes
its `OrderLine` items -- they are always loaded and saved as a unit. You never have a
standalone `OrderLineRepository`, **because** order lines have no independent lifecycle.

**However**, if you need to query across aggregates (e.g., "total revenue by SKU"), that is
a **read model concern**, not a repository concern. Use a separate read-optimized query
service or CQRS projection for cross-aggregate reporting.

**Common mistake**: Injecting the ORM session directly into services and "kind of" using
the repository pattern. This creates a leaky abstraction where domain code depends on
SQLAlchemy's `Session.query()` API. **Therefore**, the **best practice** is strict
separation: services receive only the `UnitOfWork` interface, never raw sessions.

## Summary and Key Takeaways

- **Repository pattern** provides a collection-like interface over persistence, decoupling
  domain logic from database details
- **Unit of Work** manages transaction boundaries, ensuring atomic commits and rollbacks
  across multiple repository operations
- **Design repository interfaces around domain operations**, not generic CRUD -- methods
  like `get_pending_for_customer()` communicate intent better than `filter_by(status="pending")`
- **In-memory implementations** enable fast, deterministic unit tests with zero infrastructure
  dependencies -- this is the primary reason to use the pattern
- **Pitfall**: generic repositories that mirror the ORM API provide no real abstraction and
  add boilerplate without benefit
- **Best practice**: one repository per aggregate root; cross-aggregate queries belong in
  dedicated read models or query services
- **Trade-off**: the pattern adds indirection and interface code; it pays off in medium-to-large
  applications where testability and flexibility outweigh the initial cost
""",
    ),

    # --- 2. CQRS Implementation Deep Dive ---
    (
        "cqrs_implementation_python_sqlite",
        "Explain CQRS (Command Query Responsibility Segregation) in depth -- why and when to "
        "separate read and write models, designing dedicated command handlers and query handlers, "
        "projecting domain events into optimized read models, strategies for rebuilding read-side "
        "projections from scratch, navigating eventual consistency trade-offs, and building a "
        "complete Python implementation using SQLite for both the event store and materialized "
        "read models with proper typing, error handling, and test examples.",
        r"""
# CQRS Implementation Deep Dive: Separating Reads from Writes

## Why CQRS Exists

In a traditional application, the same model serves both reads and writes. Your `Order` class
handles validation, business rules, and persistence *and* serves as the shape returned by API
queries. This works for simple domains, **because** the read and write requirements are nearly
identical. However, as complexity grows, a fundamental tension emerges:

- **Write models** need rich behavior, validation, invariant enforcement, and domain events
- **Read models** need flat, denormalized, pre-computed shapes optimized for specific UI views

Trying to serve both from one model leads to **bloated entities** loaded with `@property`
methods, lazy-loading traps, and N+1 query problems. CQRS resolves this by **splitting
the architecture**: commands (writes) go through one path with a rich domain model, and
queries (reads) go through a separate path with optimized read models.

**Common mistake**: Adopting CQRS everywhere. CQRS adds complexity -- separate models,
synchronization logic, eventual consistency handling. **Therefore**, apply it selectively
to bounded contexts where read and write requirements genuinely diverge. Simple CRUD
resources do not need CQRS.

## Architecture Overview

```
Commands                          Queries
   │                                 │
   ▼                                 ▼
┌──────────────┐            ┌──────────────────┐
│ Command Bus  │            │   Query Handler   │
│  (validate,  │            │  (read-optimized  │
│   dispatch)  │            │   denormalized)   │
└──────┬───────┘            └────────┬─────────┘
       │                             │
       ▼                             ▼
┌──────────────┐            ┌──────────────────┐
│ Domain Model │            │   Read Database   │
│ (aggregates, │──events──▶│  (projections,    │
│  invariants) │            │   materialized)   │
└──────┬───────┘            └──────────────────┘
       │
       ▼
┌──────────────┐
│ Event Store  │
│ (append-only)│
└──────────────┘
```

The **key insight** is that the read database is a **derived view** of the event store. Events
flow from the write side to projectors that build read-optimized tables. **Because** the read
model is derived, it can be rebuilt from scratch at any time by replaying all events.

## Command Side: Domain Model and Event Emission

The write side focuses entirely on enforcing business rules and emitting events.

```python
from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import (
    Any, Callable, Dict, List, Optional, Protocol, Type,
    runtime_checkable,
)

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Event:
    # Base event with identity and timestamp
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

@dataclass(frozen=True)
class TaskCreated(Event):
    task_id: str = ""
    title: str = ""
    assignee: str = ""
    priority: int = 0

@dataclass(frozen=True)
class TaskCompleted(Event):
    task_id: str = ""
    completed_by: str = ""

@dataclass(frozen=True)
class TaskReassigned(Event):
    task_id: str = ""
    old_assignee: str = ""
    new_assignee: str = ""

@dataclass(frozen=True)
class TaskPriorityChanged(Event):
    task_id: str = ""
    old_priority: int = 0
    new_priority: int = 0

# Event registry for deserialization
EVENT_TYPES: Dict[str, Type[Event]] = {
    "TaskCreated": TaskCreated,
    "TaskCompleted": TaskCompleted,
    "TaskReassigned": TaskReassigned,
    "TaskPriorityChanged": TaskPriorityChanged,
}

# ---------------------------------------------------------------------------
# Write-side aggregate
# ---------------------------------------------------------------------------

class Task:
    # Aggregate root -- enforces invariants, emits events

    def __init__(self, task_id: str, title: str, assignee: str, priority: int) -> None:
        self.task_id = task_id
        self.title = title
        self.assignee = assignee
        self.priority = priority
        self.completed = False
        self._pending_events: List[Event] = []

    def _emit(self, event: Event) -> None:
        self._pending_events.append(event)

    def collect_events(self) -> List[Event]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    @classmethod
    def create(cls, title: str, assignee: str, priority: int = 0) -> "Task":
        # Factory method -- validates inputs and emits creation event
        if not title.strip():
            raise ValueError("Task title cannot be empty")
        if priority < 0 or priority > 5:
            raise ValueError("Priority must be between 0 and 5")
        task_id = str(uuid.uuid4())
        task = cls(task_id, title.strip(), assignee, priority)
        task._emit(TaskCreated(
            task_id=task_id, title=title.strip(),
            assignee=assignee, priority=priority,
        ))
        return task

    def reassign(self, new_assignee: str) -> None:
        if self.completed:
            raise ValueError("Cannot reassign a completed task")
        if new_assignee == self.assignee:
            return  # idempotent -- no event emitted
        old = self.assignee
        self.assignee = new_assignee
        self._emit(TaskReassigned(
            task_id=self.task_id,
            old_assignee=old,
            new_assignee=new_assignee,
        ))

    def change_priority(self, new_priority: int) -> None:
        if new_priority < 0 or new_priority > 5:
            raise ValueError("Priority must be between 0 and 5")
        if new_priority == self.priority:
            return
        old = self.priority
        self.priority = new_priority
        self._emit(TaskPriorityChanged(
            task_id=self.task_id,
            old_priority=old,
            new_priority=new_priority,
        ))

    def complete(self, completed_by: str) -> None:
        if self.completed:
            raise ValueError("Task already completed")
        self.completed = True
        self._emit(TaskCompleted(
            task_id=self.task_id,
            completed_by=completed_by,
        ))
```

**Best practice**: The aggregate never directly modifies the read model. It emits events as
**facts about what happened**, and projectors consume those events to build read models.
This decoupling is the essence of CQRS.

## Event Store: Append-Only Persistence

The event store is the **single source of truth** on the write side. It is append-only --
events are never updated or deleted.

```python
class EventStore:
    # SQLite-backed append-only event store

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "  sequence_num INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  stream_id    TEXT NOT NULL,"
            "  event_type   TEXT NOT NULL,"
            "  event_data   TEXT NOT NULL,"
            "  occurred_at  TEXT NOT NULL"
            ")"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stream ON events(stream_id)"
        )
        self._conn.commit()

    def append(self, stream_id: str, events: List[Event]) -> None:
        # Atomically append events to a stream
        for event in events:
            self._conn.execute(
                "INSERT INTO events (stream_id, event_type, event_data, occurred_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    stream_id,
                    type(event).__name__,
                    json.dumps(asdict(event)),
                    event.occurred_at,
                ),
            )
        self._conn.commit()

    def get_stream(self, stream_id: str) -> List[Event]:
        # Load all events for a stream in order
        cursor = self._conn.execute(
            "SELECT event_type, event_data FROM events "
            "WHERE stream_id = ? ORDER BY sequence_num",
            (stream_id,),
        )
        result: List[Event] = []
        for event_type, event_data in cursor:
            cls = EVENT_TYPES[event_type]
            result.append(cls(**json.loads(event_data)))
        return result

    def get_all_events_since(self, sequence_num: int = 0) -> List[tuple]:
        # For projection rebuilding -- returns (seq, event) pairs
        cursor = self._conn.execute(
            "SELECT sequence_num, event_type, event_data FROM events "
            "WHERE sequence_num > ? ORDER BY sequence_num",
            (sequence_num,),
        )
        results: List[tuple] = []
        for seq, event_type, event_data in cursor:
            cls = EVENT_TYPES[event_type]
            results.append((seq, cls(**json.loads(event_data))))
        return results


# ---------------------------------------------------------------------------
# Read-side projections
# ---------------------------------------------------------------------------

class TaskReadModel:
    # Materialized read model optimized for queries

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks_view ("
            "  task_id   TEXT PRIMARY KEY,"
            "  title     TEXT NOT NULL,"
            "  assignee  TEXT NOT NULL,"
            "  priority  INTEGER NOT NULL,"
            "  status    TEXT NOT NULL DEFAULT 'open',"
            "  completed_by TEXT"
            ")"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS assignee_stats ("
            "  assignee       TEXT PRIMARY KEY,"
            "  open_count     INTEGER NOT NULL DEFAULT 0,"
            "  completed_count INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS projection_checkpoint ("
            "  projection_name TEXT PRIMARY KEY,"
            "  last_sequence   INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        self._conn.commit()

    def project_event(self, event: Event) -> None:
        # Dispatch event to the appropriate handler
        handler = getattr(self, f"_handle_{type(event).__name__}", None)
        if handler:
            handler(event)

    def _handle_TaskCreated(self, e: TaskCreated) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO tasks_view (task_id, title, assignee, priority, status) "
            "VALUES (?, ?, ?, ?, 'open')",
            (e.task_id, e.title, e.assignee, e.priority),
        )
        self._conn.execute(
            "INSERT INTO assignee_stats (assignee, open_count, completed_count) "
            "VALUES (?, 1, 0) ON CONFLICT(assignee) DO UPDATE SET open_count = open_count + 1",
            (e.assignee,),
        )
        self._conn.commit()

    def _handle_TaskCompleted(self, e: TaskCompleted) -> None:
        row = self._conn.execute(
            "SELECT assignee FROM tasks_view WHERE task_id = ?", (e.task_id,)
        ).fetchone()
        if row:
            self._conn.execute(
                "UPDATE tasks_view SET status = 'done', completed_by = ? WHERE task_id = ?",
                (e.completed_by, e.task_id),
            )
            self._conn.execute(
                "UPDATE assignee_stats SET open_count = open_count - 1, "
                "completed_count = completed_count + 1 WHERE assignee = ?",
                (row[0],),
            )
            self._conn.commit()

    def _handle_TaskReassigned(self, e: TaskReassigned) -> None:
        self._conn.execute(
            "UPDATE tasks_view SET assignee = ? WHERE task_id = ?",
            (e.new_assignee, e.task_id),
        )
        self._conn.execute(
            "UPDATE assignee_stats SET open_count = open_count - 1 WHERE assignee = ?",
            (e.old_assignee,),
        )
        self._conn.execute(
            "INSERT INTO assignee_stats (assignee, open_count, completed_count) "
            "VALUES (?, 1, 0) ON CONFLICT(assignee) DO UPDATE SET open_count = open_count + 1",
            (e.new_assignee,),
        )
        self._conn.commit()

    def _handle_TaskPriorityChanged(self, e: TaskPriorityChanged) -> None:
        self._conn.execute(
            "UPDATE tasks_view SET priority = ? WHERE task_id = ?",
            (e.new_priority, e.task_id),
        )
        self._conn.commit()

    # ---- Query methods (the whole point of the read model) ----

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT task_id, title, assignee, priority, status, completed_by "
            "FROM tasks_view WHERE task_id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        return dict(zip(
            ["task_id", "title", "assignee", "priority", "status", "completed_by"], row
        ))

    def get_open_tasks_by_assignee(self, assignee: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT task_id, title, priority FROM tasks_view "
            "WHERE assignee = ? AND status = 'open' ORDER BY priority DESC",
            (assignee,),
        ).fetchall()
        return [dict(zip(["task_id", "title", "priority"], r)) for r in rows]

    def get_assignee_stats(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT assignee, open_count, completed_count FROM assignee_stats "
            "ORDER BY open_count DESC"
        ).fetchall()
        return [dict(zip(["assignee", "open_count", "completed_count"], r)) for r in rows]


# ---------------------------------------------------------------------------
# Read model rebuilding
# ---------------------------------------------------------------------------

class ProjectionRebuilder:
    # Rebuilds the read model from scratch by replaying all events

    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store

    def rebuild(self, read_model: TaskReadModel) -> int:
        # Drop and recreate all read model tables, then replay
        read_model._conn.execute("DELETE FROM tasks_view")
        read_model._conn.execute("DELETE FROM assignee_stats")
        read_model._conn.commit()

        events = self._store.get_all_events_since(0)
        for seq, event in events:
            read_model.project_event(event)
        return len(events)
```

## Handling Eventual Consistency

The **trade-off** at the heart of CQRS is **eventual consistency**. After a command succeeds,
the read model may not reflect the change immediately. This matters **because** users expect
to see their own writes. Several strategies mitigate this:

1. **Read-your-writes consistency**: After a command, redirect the user to a page that reads
   from the write model (or waits for the projection to catch up)
2. **Optimistic UI**: The client optimistically shows the expected state, then reconciles
   when the read model catches up
3. **Synchronous projection**: For simple systems, project events synchronously in the same
   transaction as the command -- this sacrifices scalability for simplicity

**However**, a **pitfall** is trying to make the read model **strongly consistent** by
projecting synchronously everywhere. This defeats one of CQRS's key benefits: independent
scaling of reads and writes. **Therefore**, accept eventual consistency as the default and
use read-your-writes only where the UX demands it.

## Summary and Key Takeaways

- **CQRS separates the write model (commands) from the read model (queries)**, allowing each
  to be optimized independently for its specific workload
- **Events bridge the two sides**: the write model emits events, projectors consume them to
  build denormalized read views
- **Read model rebuilding** is a superpower -- fix a projection bug, replay all events, and
  the read model self-corrects. This is possible **because** events are the source of truth
- **Eventual consistency** is the fundamental trade-off; mitigate it with read-your-writes
  patterns or optimistic UI, not by making everything synchronous
- **Common mistake**: applying CQRS to every bounded context. Only use it where read/write
  requirements genuinely diverge -- simple CRUD should stay simple
- **Best practice**: keep the command side focused on business invariants and event emission;
  keep the query side focused on fast, denormalized reads with no business logic
- **Pitfall**: putting business logic in projectors. Projectors should be pure data
  transformations -- if a projection needs to enforce rules, that logic belongs on the
  command side
""",
    ),

    # --- 3. Dependency Injection ---
    (
        "dependency_injection_ioc_container_python",
        "Explain dependency injection and Inversion of Control in depth -- comparing constructor "
        "injection versus setter injection, implementing lifetime management with singleton, "
        "transient, and scoped scopes, building a fully-featured Python DI container from scratch "
        "with auto-wiring via type hints, integrating with web frameworks for request-scoped "
        "dependencies, testing with overrides and fakes, and advanced patterns like decorator "
        "injection and factory providers. Provide a complete implementation with type safety.",
        r"""
# Dependency Injection: Inversion of Control for Maintainable Python

## Why Dependency Injection Matters

Consider a service that sends order confirmations. Without DI, it directly instantiates its
dependencies:

```python
class OrderService:
    def __init__(self):
        self.db = PostgresDatabase("host=prod.db port=5432")
        self.mailer = SmtpMailer("smtp.company.com")
        self.logger = FileLogger("/var/log/orders.log")
```

This code has three devastating problems. **First**, it is untestable -- running any test
requires a live Postgres database, an SMTP server, and write access to `/var/log`. **Second**,
it violates the Open/Closed Principle -- changing from SMTP to SendGrid requires editing
`OrderService`, even though the service does not care *how* emails are sent. **Third**, it
creates hidden dependencies -- you cannot tell from the constructor signature what this
class needs.

**Dependency injection** solves all three by **inverting control**: instead of a class
creating its dependencies, they are **provided from outside** (injected). The class declares
*what* it needs via constructor parameters, and something else decides *how* to fulfill those
needs.

**Common mistake**: Confusing DI with service locators. A service locator is a global registry
that classes reach into to grab dependencies -- `container.get(Database)`. This is an
**anti-pattern** because it hides dependencies and makes them implicit. True DI pushes
dependencies inward through constructors, making the dependency graph explicit and visible.

## Injection Styles and Trade-offs

There are three main styles, each with distinct **trade-offs**:

- **Constructor injection** (preferred): Dependencies are required parameters in `__init__`.
  The object is fully initialized and usable after construction. This is the **best practice**
  because it makes dependencies explicit and immutable.
- **Setter injection**: Dependencies are assigned via properties after construction. Use this
  only for truly optional dependencies.
- **Method injection**: Dependencies are passed as parameters to individual methods. Use this
  when a dependency varies per call (e.g., a request-scoped context).

## Building a DI Container from Scratch

Let us build a full-featured DI container that supports lifetime management, auto-wiring,
and type-safe resolution.

```python
from __future__ import annotations

import inspect
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, Generic, Iterator, List, Optional,
    Protocol, Type, TypeVar, get_type_hints, runtime_checkable,
)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Lifetime scopes
# ---------------------------------------------------------------------------

class Lifetime(Enum):
    # TRANSIENT: new instance every time
    TRANSIENT = auto()
    # SINGLETON: one instance for the entire container lifetime
    SINGLETON = auto()
    # SCOPED: one instance per scope (e.g., per HTTP request)
    SCOPED = auto()


# ---------------------------------------------------------------------------
# Registration descriptors
# ---------------------------------------------------------------------------

@dataclass
class Registration:
    # Describes how to create an instance of a service
    service_type: type
    factory: Callable[..., Any]
    lifetime: Lifetime
    # For decorator chains
    decorators: List[Type] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The Container
# ---------------------------------------------------------------------------

class Container:
    # IoC container with lifetime management and auto-wiring

    def __init__(self) -> None:
        self._registrations: Dict[type, Registration] = {}
        self._singletons: Dict[type, Any] = {}
        self._singleton_lock = threading.Lock()

    # ---- Registration API ----

    def register_transient(self, service_type: Type[T], impl_type: Type[T]) -> None:
        # Every resolve() call creates a new instance
        self._registrations[service_type] = Registration(
            service_type=service_type,
            factory=impl_type,
            lifetime=Lifetime.TRANSIENT,
        )

    def register_singleton(self, service_type: Type[T], impl_type: Type[T]) -> None:
        # First resolve() creates the instance; subsequent calls return the same one
        self._registrations[service_type] = Registration(
            service_type=service_type,
            factory=impl_type,
            lifetime=Lifetime.SINGLETON,
        )

    def register_factory(
        self,
        service_type: Type[T],
        factory: Callable[..., T],
        lifetime: Lifetime = Lifetime.TRANSIENT,
    ) -> None:
        # Register a custom factory function
        self._registrations[service_type] = Registration(
            service_type=service_type,
            factory=factory,
            lifetime=lifetime,
        )

    def register_instance(self, service_type: Type[T], instance: T) -> None:
        # Register a pre-created instance (always singleton)
        self._registrations[service_type] = Registration(
            service_type=service_type,
            factory=lambda: instance,
            lifetime=Lifetime.SINGLETON,
        )
        self._singletons[service_type] = instance

    def register_decorator(self, service_type: Type[T], decorator_type: Type[T]) -> None:
        # Wraps the existing registration with a decorator
        reg = self._registrations.get(service_type)
        if not reg:
            raise KeyError(f"No registration found for {service_type}")
        reg.decorators.append(decorator_type)

    # ---- Resolution API ----

    def resolve(self, service_type: Type[T]) -> T:
        # Resolve a service, respecting lifetime and auto-wiring
        reg = self._registrations.get(service_type)
        if not reg:
            raise KeyError(
                f"No registration for {service_type.__name__}. "
                f"Registered: {[t.__name__ for t in self._registrations]}"
            )

        if reg.lifetime == Lifetime.SINGLETON:
            return self._resolve_singleton(reg)
        else:
            return self._create_instance(reg)

    def _resolve_singleton(self, reg: Registration) -> Any:
        if reg.service_type not in self._singletons:
            with self._singleton_lock:
                # Double-checked locking
                if reg.service_type not in self._singletons:
                    self._singletons[reg.service_type] = self._create_instance(reg)
        return self._singletons[reg.service_type]

    def _create_instance(self, reg: Registration) -> Any:
        # Auto-wire: inspect constructor, resolve dependencies recursively
        instance = self._auto_wire(reg.factory)
        # Apply decorators in registration order
        for decorator_type in reg.decorators:
            instance = self._auto_wire(decorator_type, override={reg.service_type: instance})
        return instance

    def _auto_wire(
        self,
        factory: Callable[..., Any],
        override: Optional[Dict[type, Any]] = None,
    ) -> Any:
        # Inspect type hints to auto-resolve constructor parameters
        try:
            hints = get_type_hints(factory.__init__ if isinstance(factory, type) else factory)
        except Exception:
            hints = {}
        hints.pop("return", None)

        sig = inspect.signature(factory)
        kwargs: Dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            hint = hints.get(param_name)
            if hint is None:
                continue
            if override and hint in override:
                kwargs[param_name] = override[hint]
            elif hint in self._registrations:
                kwargs[param_name] = self.resolve(hint)
            elif param.default is not inspect.Parameter.empty:
                continue  # has a default, skip
            else:
                raise TypeError(
                    f"Cannot resolve parameter '{param_name}: {hint.__name__}' "
                    f"for {factory}"
                )
        return factory(**kwargs)

    # ---- Scoped resolution ----

    @contextmanager
    def create_scope(self) -> Iterator["ScopedContainer"]:
        # Creates a child container for scoped lifetimes
        scope = ScopedContainer(parent=self)
        try:
            yield scope
        finally:
            scope.dispose()


class ScopedContainer:
    # Child container that manages scoped-lifetime instances

    def __init__(self, parent: Container) -> None:
        self._parent = parent
        self._scoped_instances: Dict[type, Any] = {}
        self._disposables: List[Any] = []

    def resolve(self, service_type: Type[T]) -> T:
        reg = self._parent._registrations.get(service_type)
        if not reg:
            raise KeyError(f"No registration for {service_type.__name__}")

        if reg.lifetime == Lifetime.SINGLETON:
            return self._parent.resolve(service_type)
        elif reg.lifetime == Lifetime.SCOPED:
            if service_type not in self._scoped_instances:
                instance = self._parent._create_instance(reg)
                self._scoped_instances[service_type] = instance
                if hasattr(instance, "dispose"):
                    self._disposables.append(instance)
            return self._scoped_instances[service_type]
        else:
            return self._parent._create_instance(reg)

    def dispose(self) -> None:
        for obj in reversed(self._disposables):
            obj.dispose()
        self._scoped_instances.clear()
        self._disposables.clear()
```

**However**, a **pitfall** with auto-wiring is **circular dependencies**. If `A` depends on
`B` and `B` depends on `A`, the container enters infinite recursion. The **best practice** is
to treat circular dependencies as a design smell and break them by introducing an interface
or using lazy resolution (a factory that resolves on first use).

## Practical Usage: Services and Testing

Now let us use the container with realistic service classes and demonstrate how DI
transforms testability.

```python
# ---------------------------------------------------------------------------
# Service interfaces (protocols)
# ---------------------------------------------------------------------------

@runtime_checkable
class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> bool: ...

@runtime_checkable
class UserRepository(Protocol):
    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]: ...
    def save(self, user: Dict[str, Any]) -> None: ...

# ---------------------------------------------------------------------------
# Production implementations
# ---------------------------------------------------------------------------

class SmtpEmailSender:
    # Sends real emails via SMTP
    def __init__(self, host: str = "smtp.example.com", port: int = 587) -> None:
        self.host = host
        self.port = port

    def send(self, to: str, subject: str, body: str) -> bool:
        # Production SMTP logic would go here
        print(f"Sending email to {to}: {subject}")
        return True

class PostgresUserRepository:
    # Real database implementation
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}  # simplified

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(user_id)

    def save(self, user: Dict[str, Any]) -> None:
        self._store[user["id"]] = user

# ---------------------------------------------------------------------------
# Application service -- depends on abstractions only
# ---------------------------------------------------------------------------

class NotificationService:
    # Orchestrates sending notifications to users
    def __init__(self, users: UserRepository, emailer: EmailSender) -> None:
        self._users = users
        self._emailer = emailer

    def notify_user(self, user_id: str, message: str) -> bool:
        user = self._users.get_by_id(user_id)
        if not user or "email" not in user:
            return False
        return self._emailer.send(
            to=user["email"],
            subject="Notification",
            body=message,
        )

# ---------------------------------------------------------------------------
# Container setup for production
# ---------------------------------------------------------------------------

def configure_production() -> Container:
    container = Container()
    container.register_singleton(UserRepository, PostgresUserRepository)
    container.register_singleton(EmailSender, SmtpEmailSender)
    container.register_transient(NotificationService, NotificationService)
    return container

# ---------------------------------------------------------------------------
# Test doubles and override for testing
# ---------------------------------------------------------------------------

class FakeEmailSender:
    # Test double that records calls
    def __init__(self) -> None:
        self.sent: List[tuple] = []

    def send(self, to: str, subject: str, body: str) -> bool:
        self.sent.append((to, subject, body))
        return True

class InMemoryUserRepository:
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(user_id)

    def save(self, user: Dict[str, Any]) -> None:
        self._store[user["id"]] = user


def test_notification_sends_email() -> None:
    # DI makes testing trivial -- inject fakes
    container = Container()
    fake_emailer = FakeEmailSender()
    fake_repo = InMemoryUserRepository()
    fake_repo.save({"id": "u1", "name": "Alice", "email": "alice@example.com"})

    container.register_instance(EmailSender, fake_emailer)
    container.register_instance(UserRepository, fake_repo)
    container.register_transient(NotificationService, NotificationService)

    svc = container.resolve(NotificationService)
    result = svc.notify_user("u1", "Hello!")

    assert result is True
    assert len(fake_emailer.sent) == 1
    assert fake_emailer.sent[0][0] == "alice@example.com"


def test_notification_handles_missing_user() -> None:
    container = Container()
    container.register_instance(EmailSender, FakeEmailSender())
    container.register_instance(UserRepository, InMemoryUserRepository())
    container.register_transient(NotificationService, NotificationService)

    svc = container.resolve(NotificationService)
    result = svc.notify_user("nonexistent", "Hello!")
    assert result is False
```

## Decorator Injection and Advanced Patterns

A powerful pattern is **decorator injection** -- automatically wrapping services with
cross-cutting concerns like logging, caching, or retries.

**Because** the decorator implements the same interface as the service it wraps, consumers
are unaware of the decoration. This follows the Open/Closed Principle: behavior is extended
without modifying existing code.

**Best practice**: Register decorators in order from outermost to innermost. For example,
`Retry(Cache(RealService()))` means retry wraps cache wraps the real service. **Therefore**,
register `CachingEmailSender` first, then `RetryEmailSender`.

## Summary and Key Takeaways

- **Dependency injection** decouples classes from their dependencies by pushing creation
  responsibility outward, making code testable and flexible
- **Constructor injection** is the **best practice** -- dependencies are explicit, required,
  and immutable after construction
- **Lifetime management** (singleton/transient/scoped) prevents resource leaks and ensures
  correct sharing; **common mistake** is making everything a singleton, which creates hidden
  shared state
- **Auto-wiring** resolves dependencies automatically from type hints, reducing boilerplate
  while keeping the dependency graph explicit
- **Pitfall**: circular dependencies indicate a design problem -- break them by introducing
  an interface or using lazy factories, not by switching to setter injection
- **Scoped lifetimes** are essential for web applications -- one database session per HTTP
  request, automatically disposed at request end
- **Trade-off**: DI adds indirection and a learning curve; for small scripts, direct
  instantiation is simpler and perfectly fine. Use DI when testability and flexibility
  justify the overhead
""",
    ),

    # --- 4. Observer / Event Bus Pattern ---
    (
        "observer_event_bus_pattern_python_async",
        "Explain the Observer and Event Bus patterns in depth -- decoupled event handling with "
        "strong typing, building an async event bus in Python, priority-based subscriber "
        "ordering, weak references to prevent memory leaks, error isolation between subscribers, "
        "event filtering and middleware, and comprehensive implementation with typing.Protocol "
        "and asyncio. Include production-ready code with full type annotations.",
        r"""
# Observer and Event Bus Patterns: Decoupled Event-Driven Communication

## Why the Observer Pattern Matters

The Observer pattern solves a fundamental problem in software design: **how do you notify
multiple components about state changes without coupling them together?** Consider an
e-commerce system where placing an order must trigger inventory updates, email confirmations,
analytics tracking, and loyalty point calculations. Without the Observer pattern, the order
service must know about and call every downstream system directly:

```python
# Tightly coupled -- the order service knows about everything
class OrderService:
    def place_order(self, order):
        self.inventory.reserve(order)     # coupling to inventory
        self.emailer.send_confirm(order)  # coupling to email
        self.analytics.track(order)       # coupling to analytics
        self.loyalty.award_points(order)  # coupling to loyalty
```

Every new downstream concern requires modifying `OrderService`. This violates the
**Open/Closed Principle** and creates a maintenance nightmare. The Observer pattern
inverts this: the order service **publishes an event**, and interested components
**subscribe** to receive it. The publisher has zero knowledge of its subscribers.

**Common mistake**: Using direct callbacks everywhere instead of a structured event bus.
Individual callbacks work for two-component relationships, but they create a tangled web
when dozens of components need to communicate. An **event bus** provides a centralized
dispatch mechanism with consistent error handling, ordering, and lifecycle management.

## Core Concepts: Events, Subscribers, and the Bus

The three key abstractions are:

1. **Events**: Immutable data objects describing what happened (past tense: `OrderPlaced`,
   `UserRegistered`)
2. **Subscribers/Handlers**: Callables that react to specific event types
3. **Event Bus**: The mediator that routes events to appropriate subscribers

**Best practice**: Define events as frozen dataclasses with all context a subscriber might
need. **Because** events are dispatched asynchronously (in the general case), subscribers
cannot call back to the publisher for more context.

## Full Implementation: Typed Async Event Bus

```python
from __future__ import annotations

import asyncio
import logging
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import (
    Any, Awaitable, Callable, Dict, Generic, List, Optional,
    Protocol, Set, Type, TypeVar, Union, runtime_checkable,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event base types
# ---------------------------------------------------------------------------

E = TypeVar("E", bound="DomainEvent")

@dataclass(frozen=True)
class DomainEvent:
    # Base class for all domain events -- immutable by design
    event_id: str = field(default_factory=lambda: __import__("uuid").uuid4().hex)
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    order_id: str = ""
    customer_id: str = ""
    total_cents: int = 0

@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    order_id: str = ""
    reason: str = ""

@dataclass(frozen=True)
class UserRegistered(DomainEvent):
    user_id: str = ""
    email: str = ""
    plan: str = "free"


# ---------------------------------------------------------------------------
# Subscriber protocol and priority
# ---------------------------------------------------------------------------

class Priority(IntEnum):
    # Lower value = higher priority (runs first)
    CRITICAL = 0
    HIGH = 10
    NORMAL = 50
    LOW = 100
    AUDIT = 200  # audit/logging always runs last


# Sync handler type
SyncHandler = Callable[[Any], None]
# Async handler type
AsyncHandler = Callable[[Any], Awaitable[None]]
# Union of both
Handler = Union[SyncHandler, AsyncHandler]


@dataclass
class Subscription:
    # Metadata for a registered handler
    handler: Handler
    priority: Priority = Priority.NORMAL
    event_filter: Optional[Callable[[Any], bool]] = None
    # Weak reference support -- if the subscriber object is GC'd, auto-unsubscribe
    _weak_ref: Optional[weakref.ref] = field(default=None, repr=False)

    @property
    def is_alive(self) -> bool:
        if self._weak_ref is None:
            return True
        return self._weak_ref() is not None


# ---------------------------------------------------------------------------
# Event Bus: the central dispatch mechanism
# ---------------------------------------------------------------------------

class EventBus:
    # Async event bus with priority ordering, error isolation, and weak refs

    def __init__(self) -> None:
        # Maps event type -> list of subscriptions
        self._subscribers: Dict[Type[DomainEvent], List[Subscription]] = {}
        self._middleware: List[Callable] = []
        self._dead_letter: List[tuple] = []  # events that no handler processed

    def subscribe(
        self,
        event_type: Type[E],
        handler: Handler,
        priority: Priority = Priority.NORMAL,
        event_filter: Optional[Callable[[E], bool]] = None,
        weak: bool = False,
    ) -> Callable[[], None]:
        # Register a handler for an event type; returns an unsubscribe function
        weak_ref = None
        if weak and hasattr(handler, "__self__"):
            # Create a weak reference to the bound method's instance
            obj = handler.__self__
            method_name = handler.__func__.__name__
            weak_ref = weakref.ref(obj)
            # Replace handler with a weak-ref-aware wrapper
            original_handler = handler
            def weak_handler(event: Any) -> Any:
                target = weak_ref()
                if target is not None:
                    method = getattr(target, method_name)
                    return method(event)
            handler = weak_handler

        sub = Subscription(
            handler=handler,
            priority=priority,
            event_filter=event_filter,
            _weak_ref=weak_ref,
        )

        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(sub)
        # Keep sorted by priority
        self._subscribers[event_type].sort(key=lambda s: s.priority)

        # Return unsubscribe function for cleanup
        def unsubscribe() -> None:
            subs = self._subscribers.get(event_type, [])
            if sub in subs:
                subs.remove(sub)

        return unsubscribe

    def add_middleware(self, middleware: Callable) -> None:
        # Middleware runs before every handler dispatch
        self._middleware.append(middleware)

    async def publish(self, event: DomainEvent) -> List[Exception]:
        # Dispatch event to all matching subscribers; returns list of errors
        # Error isolation: one handler failure does not prevent others from running
        event_type = type(event)
        subs = self._subscribers.get(event_type, [])

        # Clean up dead weak references
        subs = [s for s in subs if s.is_alive]
        self._subscribers[event_type] = subs

        if not subs:
            self._dead_letter.append((event, "no subscribers"))
            return []

        errors: List[Exception] = []
        for sub in subs:
            # Apply event filter
            if sub.event_filter and not sub.event_filter(event):
                continue

            # Run middleware
            skip = False
            for mw in self._middleware:
                try:
                    result = mw(event, sub)
                    if result is False:
                        skip = True
                        break
                except Exception as e:
                    logger.error(f"Middleware error: {e}")
            if skip:
                continue

            # Dispatch to handler with error isolation
            try:
                result = sub.handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    f"Handler {sub.handler} failed for "
                    f"{event_type.__name__}: {e}"
                )
                errors.append(e)

        return errors

    def publish_sync(self, event: DomainEvent) -> List[Exception]:
        # Synchronous dispatch for non-async contexts
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.publish(event))
        finally:
            loop.close()

    @property
    def dead_letters(self) -> List[tuple]:
        return list(self._dead_letter)
```

**However**, error isolation is a critical design decision. The bus catches exceptions from
individual handlers and continues dispatching to remaining subscribers. **Because** subscribers
are independent, one failure should not prevent others from processing the event. The
accumulated errors are returned to the publisher for logging or retry decisions.

## Practical Usage: Wiring Subscribers

```python
# ---------------------------------------------------------------------------
# Subscriber implementations
# ---------------------------------------------------------------------------

class InventoryService:
    # Reacts to order events by managing stock levels

    def __init__(self) -> None:
        self.reservations: Dict[str, int] = {}

    async def on_order_placed(self, event: OrderPlaced) -> None:
        self.reservations[event.order_id] = event.total_cents
        logger.info(f"Inventory reserved for order {event.order_id}")

    async def on_order_cancelled(self, event: OrderCancelled) -> None:
        self.reservations.pop(event.order_id, None)
        logger.info(f"Inventory released for order {event.order_id}")


class EmailService:
    # Sends email notifications for domain events

    def __init__(self) -> None:
        self.sent_emails: List[Dict[str, str]] = []

    async def on_order_placed(self, event: OrderPlaced) -> None:
        self.sent_emails.append({
            "to": event.customer_id,
            "subject": f"Order {event.order_id} confirmed",
            "type": "order_confirmation",
        })

    async def on_user_registered(self, event: UserRegistered) -> None:
        self.sent_emails.append({
            "to": event.email,
            "subject": "Welcome!",
            "type": "welcome_email",
        })


class AuditLogger:
    # Logs all events for audit trail -- lowest priority, runs last

    def __init__(self) -> None:
        self.log: List[str] = []

    async def on_any_event(self, event: DomainEvent) -> None:
        self.log.append(
            f"[AUDIT] {type(event).__name__} at {event.occurred_at}: "
            f"{event.event_id}"
        )


# ---------------------------------------------------------------------------
# Wiring it all together
# ---------------------------------------------------------------------------

async def demo_event_bus() -> None:
    bus = EventBus()

    # Create services
    inventory = InventoryService()
    emailer = EmailService()
    auditor = AuditLogger()

    # Subscribe with priorities
    bus.subscribe(OrderPlaced, inventory.on_order_placed, Priority.HIGH)
    bus.subscribe(OrderPlaced, emailer.on_order_placed, Priority.NORMAL)
    bus.subscribe(OrderCancelled, inventory.on_order_cancelled, Priority.HIGH)
    bus.subscribe(UserRegistered, emailer.on_user_registered, Priority.NORMAL)

    # Audit logger subscribes to all event types at lowest priority
    for event_type in [OrderPlaced, OrderCancelled, UserRegistered]:
        bus.subscribe(event_type, auditor.on_any_event, Priority.AUDIT)

    # Subscribe with a filter: only high-value orders
    def high_value_filter(event: OrderPlaced) -> bool:
        return event.total_cents > 10000

    bus.subscribe(
        OrderPlaced,
        lambda e: logger.warning(f"HIGH VALUE ORDER: {e.order_id}"),
        Priority.CRITICAL,
        event_filter=high_value_filter,
    )

    # Publish events
    errors = await bus.publish(OrderPlaced(
        order_id="ord-1", customer_id="cust-1", total_cents=25000,
    ))
    assert len(errors) == 0

    # Verify side effects
    assert "ord-1" in inventory.reservations
    assert len(emailer.sent_emails) == 1
    assert len(auditor.log) == 1
```

## Weak References and Memory Management

A **pitfall** with the Observer pattern is **memory leaks**. When a subscriber object is
registered with the bus, the bus holds a strong reference to it. Even if all other references
to the subscriber are dropped, it cannot be garbage collected **because** the bus still
references it. This is especially problematic in long-running applications with dynamic
subscriber lifecycles.

The solution is **weak references**: the bus holds a `weakref.ref` to the subscriber. When
the subscriber is garbage collected, the weak reference becomes `None`, and the bus
automatically cleans it up on the next publish cycle. **Therefore**, subscribers with short
lifecycles (e.g., request handlers, UI components) should be registered with `weak=True`.

**Best practice**: Use `weak=True` for subscribers that have a shorter lifecycle than the
bus itself. Use strong references (the default) for singletons and application-scoped
services that live for the entire process lifetime.

## Summary and Key Takeaways

- **The Observer pattern** decouples event publishers from subscribers, enabling extensibility
  without modifying existing code
- **Event buses** centralize dispatch with consistent error handling, priority ordering, and
  lifecycle management -- better than ad-hoc callback registration
- **Priority-based ordering** ensures critical handlers (inventory, payments) run before
  lower-priority ones (analytics, logging). **Because** handlers are sorted by priority,
  the system behavior is predictable and debuggable
- **Error isolation** is essential -- one handler failure must not prevent other subscribers
  from processing the event. **Therefore**, the bus catches per-handler exceptions and
  reports them without aborting
- **Weak references** prevent memory leaks for short-lived subscribers; **common mistake**
  is using strong references everywhere, causing objects to live forever
- **Event filtering** and **middleware** provide fine-grained control over which events
  reach which handlers, enabling patterns like rate limiting, deduplication, and conditional
  routing
- **Trade-off**: the event bus adds indirection that makes control flow harder to follow.
  Use direct method calls for simple two-component interactions; use the bus when you have
  3+ independent subscribers or need extensibility
""",
    ),

    # --- 5. Strategy and Chain of Responsibility ---
    (
        "strategy_chain_of_responsibility_python_protocol",
        "Explain the Strategy and Chain of Responsibility design patterns in depth -- composable "
        "behavior selection at runtime using polymorphism, building middleware chains and "
        "validation pipelines with generic handler types, implementing both patterns with "
        "Python Protocol classes and generics for structural subtyping, combining Strategy and "
        "Chain of Responsibility for extensible processing architectures, real-world examples "
        "with payment processing and request validation, and comprehensive production code with "
        "full type annotations and tests.",
        r"""
# Strategy and Chain of Responsibility: Composable Behavior and Processing Pipelines

## Why These Patterns Work Together

The **Strategy pattern** lets you swap algorithms at runtime -- different pricing rules,
different compression algorithms, different authentication methods -- without changing the
code that uses them. The **Chain of Responsibility** pattern lets you build a pipeline of
handlers where each handler decides whether to process a request or pass it along. Together,
they enable **composable, extensible processing** that follows the Open/Closed Principle:
new behaviors are added by writing new classes, not by modifying existing ones.

**Common mistake**: Implementing conditional behavior with long `if/elif/else` chains:

```python
# Anti-pattern: every new payment method means editing this function
def process_payment(method: str, amount: float) -> bool:
    if method == "credit_card":
        # 50 lines of credit card logic
        ...
    elif method == "paypal":
        # 40 lines of PayPal logic
        ...
    elif method == "crypto":
        # 60 lines of crypto logic
        ...
    # Grows forever, violates Open/Closed Principle
```

This is fragile **because** every new payment method requires modifying a function that
already handles multiple concerns. The Strategy pattern replaces this with polymorphism:
each payment method is a separate class that implements a common interface.

## The Strategy Pattern with Protocol Classes

Python's `typing.Protocol` provides structural subtyping -- a class satisfies a Protocol
if it has the right methods, without explicit inheritance. This is ideal for Strategy
**because** it avoids coupling strategies to a base class.

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import (
    Any, Callable, Dict, Generic, List, Optional,
    Protocol, Sequence, Type, TypeVar, runtime_checkable,
)

# ---------------------------------------------------------------------------
# Strategy interfaces via Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class PaymentStrategy(Protocol):
    # Structural interface -- any class with this method signature qualifies
    def process_payment(self, amount: Decimal, currency: str) -> "PaymentResult": ...

@runtime_checkable
class PricingStrategy(Protocol):
    def calculate_price(self, base_price: Decimal, context: "PricingContext") -> Decimal: ...


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PaymentResult:
    success: bool
    transaction_id: str = ""
    error_message: str = ""
    gateway: str = ""

@dataclass(frozen=True)
class PricingContext:
    customer_tier: str = "standard"  # standard, premium, enterprise
    quantity: int = 1
    coupon_code: Optional[str] = None
    is_annual: bool = False


# ---------------------------------------------------------------------------
# Concrete strategies -- each is independent, testable, and swappable
# ---------------------------------------------------------------------------

class CreditCardProcessor:
    # Processes credit card payments via Stripe-like gateway
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def process_payment(self, amount: Decimal, currency: str) -> PaymentResult:
        # Production code would call Stripe API here
        if amount <= 0:
            return PaymentResult(success=False, error_message="Amount must be positive")
        tx_id = f"cc_{id(self)}_{amount}"
        return PaymentResult(success=True, transaction_id=tx_id, gateway="stripe")


class PayPalProcessor:
    # Processes payments via PayPal
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._secret = client_secret

    def process_payment(self, amount: Decimal, currency: str) -> PaymentResult:
        if currency not in ("USD", "EUR", "GBP"):
            return PaymentResult(
                success=False,
                error_message=f"PayPal does not support {currency}",
            )
        tx_id = f"pp_{id(self)}_{amount}"
        return PaymentResult(success=True, transaction_id=tx_id, gateway="paypal")


class CryptoProcessor:
    # Processes cryptocurrency payments
    def __init__(self, wallet_address: str) -> None:
        self._wallet = wallet_address

    def process_payment(self, amount: Decimal, currency: str) -> PaymentResult:
        if currency not in ("BTC", "ETH", "USDC"):
            return PaymentResult(
                success=False,
                error_message=f"Unsupported crypto: {currency}",
            )
        tx_id = f"crypto_{id(self)}_{amount}"
        return PaymentResult(success=True, transaction_id=tx_id, gateway="crypto")


# ---------------------------------------------------------------------------
# Pricing strategies
# ---------------------------------------------------------------------------

class StandardPricing:
    def calculate_price(self, base_price: Decimal, context: PricingContext) -> Decimal:
        return base_price * context.quantity

class TieredPricing:
    # Discount tiers: premium gets 10% off, enterprise gets 20% off
    _discounts: Dict[str, Decimal] = {
        "standard": Decimal("1.00"),
        "premium": Decimal("0.90"),
        "enterprise": Decimal("0.80"),
    }

    def calculate_price(self, base_price: Decimal, context: PricingContext) -> Decimal:
        multiplier = self._discounts.get(context.customer_tier, Decimal("1.00"))
        subtotal = base_price * context.quantity * multiplier
        if context.is_annual:
            subtotal *= Decimal("0.85")  # 15% annual discount
        return subtotal.quantize(Decimal("0.01"))

class VolumePricing:
    # Price per unit decreases with quantity
    def calculate_price(self, base_price: Decimal, context: PricingContext) -> Decimal:
        qty = context.quantity
        if qty >= 100:
            unit_price = base_price * Decimal("0.60")
        elif qty >= 50:
            unit_price = base_price * Decimal("0.75")
        elif qty >= 10:
            unit_price = base_price * Decimal("0.90")
        else:
            unit_price = base_price
        return (unit_price * qty).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Strategy context: uses strategies without knowing concrete types
# ---------------------------------------------------------------------------

class PaymentService:
    # Selects payment strategy at runtime based on method
    def __init__(self) -> None:
        self._strategies: Dict[str, PaymentStrategy] = {}

    def register_strategy(self, method_name: str, strategy: PaymentStrategy) -> None:
        self._strategies[method_name] = strategy

    def process(self, method: str, amount: Decimal, currency: str) -> PaymentResult:
        strategy = self._strategies.get(method)
        if not strategy:
            return PaymentResult(
                success=False,
                error_message=f"Unknown payment method: {method}",
            )
        return strategy.process_payment(amount, currency)
```

**Best practice**: Register strategies in a configuration function or DI container, not
scattered throughout business logic. This centralizes the decision of *which* strategy to
use, making it easy to change for different environments (production vs. testing vs. staging).

## The Chain of Responsibility: Middleware Pipelines

The Chain of Responsibility builds a **pipeline** where each handler either processes the
request and stops, or passes it to the next handler. This is the pattern behind HTTP
middleware stacks, validation pipelines, and logging chains.

```python
# ---------------------------------------------------------------------------
# Generic Chain of Responsibility with typing
# ---------------------------------------------------------------------------

T_Request = TypeVar("T_Request")
T_Response = TypeVar("T_Response")

class Handler(ABC, Generic[T_Request, T_Response]):
    # Abstract handler in the chain
    _next_handler: Optional["Handler[T_Request, T_Response]"] = None

    def set_next(self, handler: "Handler[T_Request, T_Response]") -> "Handler[T_Request, T_Response]":
        self._next_handler = handler
        return handler  # enables chaining: a.set_next(b).set_next(c)

    @abstractmethod
    def handle(self, request: T_Request) -> Optional[T_Response]:
        ...

    def pass_to_next(self, request: T_Request) -> Optional[T_Response]:
        if self._next_handler:
            return self._next_handler.handle(request)
        return None


# ---------------------------------------------------------------------------
# Validation pipeline using Chain of Responsibility
# ---------------------------------------------------------------------------

@dataclass
class ValidationRequest:
    # The data being validated
    data: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    is_valid: bool = True

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.is_valid = False


class ValidationHandler(Handler[ValidationRequest, ValidationRequest]):
    # Base for validation chain -- each validator checks one concern
    pass


class RequiredFieldsValidator(ValidationHandler):
    # Validates that required fields are present and non-empty
    def __init__(self, required_fields: List[str]) -> None:
        super().__init__()
        self._fields = required_fields

    def handle(self, request: ValidationRequest) -> Optional[ValidationRequest]:
        for f in self._fields:
            if f not in request.data or not request.data[f]:
                request.add_error(f"Missing required field: {f}")
        # Always pass to next -- accumulate all errors
        return self.pass_to_next(request) or request


class TypeValidator(ValidationHandler):
    # Validates field types match expected types
    def __init__(self, type_specs: Dict[str, type]) -> None:
        super().__init__()
        self._specs = type_specs

    def handle(self, request: ValidationRequest) -> Optional[ValidationRequest]:
        for field_name, expected_type in self._specs.items():
            value = request.data.get(field_name)
            if value is not None and not isinstance(value, expected_type):
                request.add_error(
                    f"Field '{field_name}' expected {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )
        return self.pass_to_next(request) or request


class RangeValidator(ValidationHandler):
    # Validates numeric fields are within acceptable ranges
    def __init__(self, ranges: Dict[str, tuple]) -> None:
        super().__init__()
        self._ranges = ranges  # field -> (min, max)

    def handle(self, request: ValidationRequest) -> Optional[ValidationRequest]:
        for field_name, (min_val, max_val) in self._ranges.items():
            value = request.data.get(field_name)
            if value is not None and isinstance(value, (int, float)):
                if value < min_val or value > max_val:
                    request.add_error(
                        f"Field '{field_name}' value {value} outside "
                        f"range [{min_val}, {max_val}]"
                    )
        return self.pass_to_next(request) or request


class BusinessRuleValidator(ValidationHandler):
    # Validates custom business rules via callables
    def __init__(self, rules: List[Callable[[Dict[str, Any]], Optional[str]]]) -> None:
        super().__init__()
        self._rules = rules

    def handle(self, request: ValidationRequest) -> Optional[ValidationRequest]:
        for rule in self._rules:
            error = rule(request.data)
            if error:
                request.add_error(error)
        return self.pass_to_next(request) or request
```

**However**, the classic linked-list Chain of Responsibility has a **pitfall**: building the
chain is verbose and error-prone. A **best practice** is to provide a builder that composes
the chain from a list, which is both cleaner and less bug-prone.

## Combining Strategy and Chain: The Pipeline Builder

```python
# ---------------------------------------------------------------------------
# Pipeline builder: composes chains from lists of handlers
# ---------------------------------------------------------------------------

class ValidationPipeline:
    # Builds and executes validation chains from a list of handlers
    def __init__(self) -> None:
        self._handlers: List[ValidationHandler] = []

    def add_handler(self, handler: ValidationHandler) -> "ValidationPipeline":
        self._handlers.append(handler)
        return self  # fluent interface

    def build(self) -> Optional[ValidationHandler]:
        if not self._handlers:
            return None
        # Chain handlers together
        for i in range(len(self._handlers) - 1):
            self._handlers[i].set_next(self._handlers[i + 1])
        return self._handlers[0]

    def validate(self, data: Dict[str, Any]) -> ValidationRequest:
        request = ValidationRequest(data=data)
        head = self.build()
        if head:
            head.handle(request)
        return request


# ---------------------------------------------------------------------------
# Middleware-style chain (functional approach)
# ---------------------------------------------------------------------------

# Middleware type: takes a request and a next function
Middleware = Callable[[Dict[str, Any], Callable], Any]

class MiddlewareChain:
    # Functional middleware chain -- each middleware calls next() to continue
    def __init__(self) -> None:
        self._middlewares: List[Middleware] = []

    def use(self, middleware: Middleware) -> "MiddlewareChain":
        self._middlewares.append(middleware)
        return self

    def execute(self, request: Dict[str, Any]) -> Any:
        # Build the chain from inside out
        def terminal(req: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "ok", "data": req}

        chain = terminal
        for mw in reversed(self._middlewares):
            # Capture current chain in closure
            next_fn = chain
            def make_handler(middleware: Middleware, nxt: Callable) -> Callable:
                def handler(req: Dict[str, Any]) -> Any:
                    return middleware(req, nxt)
                return handler
            chain = make_handler(mw, next_fn)

        return chain(request)


# ---------------------------------------------------------------------------
# Putting it all together: complete example with tests
# ---------------------------------------------------------------------------

def test_validation_pipeline() -> None:
    # Build the validation chain
    pipeline = ValidationPipeline()
    pipeline.add_handler(RequiredFieldsValidator(["name", "email", "age"]))
    pipeline.add_handler(TypeValidator({"name": str, "email": str, "age": int}))
    pipeline.add_handler(RangeValidator({"age": (0, 150)}))
    pipeline.add_handler(BusinessRuleValidator([
        lambda d: "Email must contain @" if "@" not in d.get("email", "") else None,
        lambda d: "Name too short" if len(d.get("name", "")) < 2 else None,
    ]))

    # Valid input
    result = pipeline.validate({
        "name": "Alice", "email": "alice@example.com", "age": 30,
    })
    assert result.is_valid
    assert len(result.errors) == 0

    # Multiple validation failures
    result = pipeline.validate({"name": "A", "age": 200})
    assert not result.is_valid
    assert any("email" in e.lower() for e in result.errors)  # missing email
    assert any("range" in e.lower() for e in result.errors)  # age out of range
    assert any("too short" in e.lower() for e in result.errors)  # name too short


def test_strategy_payment_selection() -> None:
    service = PaymentService()
    service.register_strategy("credit_card", CreditCardProcessor("sk_test_123"))
    service.register_strategy("paypal", PayPalProcessor("client_1", "secret_1"))
    service.register_strategy("crypto", CryptoProcessor("0xABC"))

    # Strategy selection at runtime
    result = service.process("credit_card", Decimal("99.99"), "USD")
    assert result.success
    assert result.gateway == "stripe"

    result = service.process("paypal", Decimal("50.00"), "JPY")
    assert not result.success  # PayPal doesn't support JPY

    result = service.process("bitcoin", Decimal("100.00"), "BTC")
    assert not result.success  # unknown method


def test_pricing_strategies() -> None:
    # Same base price, different strategies yield different results
    base = Decimal("100.00")

    standard = StandardPricing()
    tiered = TieredPricing()
    volume = VolumePricing()

    ctx = PricingContext(customer_tier="enterprise", quantity=50, is_annual=True)

    standard_price = standard.calculate_price(base, ctx)
    tiered_price = tiered.calculate_price(base, ctx)
    volume_price = volume.calculate_price(base, ctx)

    # Standard: 100 * 50 = 5000
    assert standard_price == Decimal("5000")

    # Tiered: 100 * 50 * 0.80 (enterprise) * 0.85 (annual) = 3400.00
    assert tiered_price == Decimal("3400.00")

    # Volume: 100 * 0.75 (50+ tier) * 50 = 3750.00
    assert volume_price == Decimal("3750.00")


def test_middleware_chain() -> None:
    chain = MiddlewareChain()

    # Logging middleware
    log: List[str] = []
    def logging_mw(req: Dict[str, Any], nxt: Callable) -> Any:
        log.append(f"Request: {req.get('path', '/')}")
        result = nxt(req)
        log.append(f"Response: {result.get('status', 'unknown')}")
        return result

    # Auth middleware
    def auth_mw(req: Dict[str, Any], nxt: Callable) -> Any:
        if not req.get("token"):
            return {"status": "unauthorized", "data": None}
        return nxt(req)

    chain.use(logging_mw).use(auth_mw)

    # Authenticated request passes through
    result = chain.execute({"path": "/api/data", "token": "valid"})
    assert result["status"] == "ok"
    assert len(log) == 2

    # Unauthenticated request is blocked by auth middleware
    log.clear()
    result = chain.execute({"path": "/api/data"})
    assert result["status"] == "unauthorized"
```

## When to Use Each Pattern

**Strategy** is the right choice when you have **multiple interchangeable algorithms** for
the same task, and the selection happens at runtime based on configuration, user input, or
context. **Because** each strategy is a separate class, adding new algorithms requires zero
changes to existing code.

**Chain of Responsibility** is the right choice when a request must pass through **multiple
processing stages** -- validation, authentication, authorization, transformation, logging.
**Therefore**, it is the natural pattern for middleware stacks, request pipelines, and
multi-step validation.

The **trade-off** between them: Strategy selects **one** algorithm; Chain of Responsibility
composes **many** processors in sequence. Combine them when you need both -- for example,
a validation pipeline (Chain) where each validator uses a different checking strategy
(Strategy).

## Summary and Key Takeaways

- **Strategy pattern** eliminates `if/elif/else` cascades by encapsulating each algorithm
  in a separate class behind a common Protocol interface
- **Chain of Responsibility** builds processing pipelines where each handler addresses one
  concern and passes the request onward -- ideal for validation, middleware, and multi-step
  workflows
- **Protocol classes** in Python provide structural subtyping, enabling strategies without
  inheritance hierarchies. **Best practice**: use `@runtime_checkable` for debugging but
  rely on static type checking with mypy for production safety
- **Pipeline builders** simplify chain construction -- the `ValidationPipeline` class
  provides a fluent API that is less error-prone than manual `set_next()` calls
- **Functional middleware chains** offer an alternative to class-based chains. **Because**
  Python supports first-class functions, middleware can be simple closures
- **Pitfall**: over-engineering simple problems with patterns. A function with two branches
  does not need the Strategy pattern. Apply these patterns when the number of variants is
  growing and extensibility matters
- **Trade-off**: Strategy picks one algorithm; Chain of Responsibility composes many processors.
  Combine both for maximum flexibility in extensible processing architectures
""",
    ),
]
