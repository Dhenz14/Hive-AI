PAIRS = [
    (
        "architecture/domain-driven-design-fundamentals",
        r"""Explain Domain-Driven Design fundamentals including bounded contexts, aggregates, entities vs value objects, domain events, repositories, and the ubiquitous language. Show how to implement these patterns in Python with practical examples.""",
        r"""## Domain-Driven Design: Bounded Contexts, Aggregates, and Strategic Patterns

DDD is an approach to software design that centers the development on the business domain. It's most valuable for complex business logic where the domain is the hardest part of the problem.

### Ubiquitous Language

The foundation of DDD — developers and domain experts use the SAME terms:

```python
# BAD: Developer-centric naming
class UserRecord:
    status: int  # 1=active, 2=suspended, 3=deleted
    type_id: int  # FK to user_types table

# GOOD: Domain language
class Member:
    membership_status: MembershipStatus  # ACTIVE, SUSPENDED, CANCELLED
    subscription_tier: SubscriptionTier  # FREE, PROFESSIONAL, ENTERPRISE
```

### Entities vs Value Objects

```python
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID, uuid4
from decimal import Decimal


# ENTITY: has a unique identity, mutable, lifecycle
# Two Orders with the same items are DIFFERENT orders
class Order:
    def __init__(self, customer_id: UUID):
        self.id: UUID = uuid4()  # Unique identity
        self.customer_id = customer_id
        self._items: list["OrderItem"] = []
        self._status = OrderStatus.DRAFT
        self._events: list = []

    def add_item(self, product_id: UUID, quantity: int, unit_price: Money):
        if self._status != OrderStatus.DRAFT:
            raise DomainError("Cannot modify a submitted order")
        if quantity <= 0:
            raise DomainError("Quantity must be positive")

        existing = next(
            (i for i in self._items if i.product_id == product_id), None
        )
        if existing:
            existing.quantity += quantity
        else:
            self._items.append(OrderItem(product_id, quantity, unit_price))

        self._events.append(OrderItemAdded(self.id, product_id, quantity))

    def submit(self):
        if not self._items:
            raise DomainError("Cannot submit an empty order")
        if self._status != OrderStatus.DRAFT:
            raise DomainError(f"Cannot submit order in {self._status} status")

        self._status = OrderStatus.SUBMITTED
        self._events.append(OrderSubmitted(self.id, self.total))

    @property
    def total(self) -> "Money":
        return Money.sum(item.subtotal for item in self._items)

    def collect_events(self) -> list:
        events = self._events.copy()
        self._events.clear()
        return events


# VALUE OBJECT: no identity, immutable, defined by its attributes
# Two Money(10, "USD") are the SAME thing
@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Money cannot be negative")

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise DomainError(
                f"Cannot add {self.currency} and {other.currency}"
            )
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, quantity: int) -> "Money":
        return Money(self.amount * quantity, self.currency)

    @classmethod
    def sum(cls, moneys) -> "Money":
        total = None
        for m in moneys:
            total = m if total is None else total + m
        return total or Money(Decimal("0"), "USD")


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    state: str
    zip_code: str
    country: str

    def __post_init__(self):
        if not self.zip_code:
            raise ValueError("Zip code is required")
```

### Aggregates

An aggregate is a cluster of domain objects treated as a single unit for data changes. The aggregate root is the only entry point:

```python
from enum import Enum


class OrderStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class OrderItem:
    """Part of the Order aggregate — never accessed directly."""
    product_id: UUID
    quantity: int
    unit_price: Money

    @property
    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


class Order:
    """Aggregate root — all access goes through Order."""

    # Aggregate rules:
    # 1. External objects can only hold references to the root (Order)
    # 2. Only the root can be obtained from the repository
    # 3. Objects inside the aggregate can hold references to each other
    # 4. All invariants are enforced by the root
    # 5. Changes to the aggregate are atomic (single transaction)

    MAX_ITEMS = 50
    MAX_ORDER_TOTAL = Money(Decimal("10000"), "USD")

    def __init__(self, customer_id: UUID, shipping_address: Address):
        self.id = uuid4()
        self.customer_id = customer_id
        self.shipping_address = shipping_address
        self._items: list[OrderItem] = []
        self._status = OrderStatus.DRAFT
        self._events: list = []

    def add_item(self, product_id: UUID, quantity: int, unit_price: Money):
        """Business rule: enforce aggregate invariants."""
        self._require_status(OrderStatus.DRAFT)

        if len(self._items) >= self.MAX_ITEMS:
            raise DomainError(f"Order cannot have more than {self.MAX_ITEMS} items")

        item = OrderItem(product_id, quantity, unit_price)

        # Check total won't exceed limit
        projected_total = self.total + item.subtotal
        if projected_total.amount > self.MAX_ORDER_TOTAL.amount:
            raise DomainError("Order total would exceed maximum")

        self._items.append(item)

    def remove_item(self, product_id: UUID):
        self._require_status(OrderStatus.DRAFT)
        self._items = [i for i in self._items if i.product_id != product_id]

    def submit(self) -> list:
        """Submit the order, return domain events."""
        self._require_status(OrderStatus.DRAFT)
        if not self._items:
            raise DomainError("Cannot submit empty order")

        self._status = OrderStatus.SUBMITTED
        self._events.append(OrderSubmitted(
            order_id=self.id,
            customer_id=self.customer_id,
            total=self.total,
            item_count=len(self._items),
        ))
        return self.collect_events()

    def mark_paid(self, payment_id: UUID):
        self._require_status(OrderStatus.SUBMITTED)
        self._status = OrderStatus.PAID
        self._events.append(OrderPaid(self.id, payment_id))

    def cancel(self, reason: str):
        if self._status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise DomainError("Cannot cancel shipped/delivered order")
        self._status = OrderStatus.CANCELLED
        self._events.append(OrderCancelled(self.id, reason))

    @property
    def total(self) -> Money:
        if not self._items:
            return Money(Decimal("0"), "USD")
        return Money.sum(i.subtotal for i in self._items)

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def item_count(self) -> int:
        return len(self._items)

    def _require_status(self, expected: OrderStatus):
        if self._status != expected:
            raise DomainError(
                f"Operation requires {expected.value} status, "
                f"current is {self._status.value}"
            )

    def collect_events(self) -> list:
        events = self._events.copy()
        self._events.clear()
        return events


class DomainError(Exception):
    """Business rule violation."""
    pass
```

### Domain Events

Events capture something meaningful that happened in the domain:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class DomainEvent:
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class OrderSubmitted(DomainEvent):
    order_id: UUID = None
    customer_id: UUID = None
    total: Money = None
    item_count: int = 0


@dataclass(frozen=True)
class OrderPaid(DomainEvent):
    order_id: UUID = None
    payment_id: UUID = None


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    order_id: UUID = None
    reason: str = ""


class EventDispatcher:
    """Dispatch domain events to handlers."""

    def __init__(self):
        self._handlers: dict[type, list] = {}

    def register(self, event_type: type, handler):
        self._handlers.setdefault(event_type, []).append(handler)

    async def dispatch(self, events: list[DomainEvent]):
        for event in events:
            handlers = self._handlers.get(type(event), [])
            for handler in handlers:
                await handler(event)


# Event handlers (in application layer, not domain)
async def send_order_confirmation(event: OrderSubmitted):
    await email_service.send(
        to=event.customer_id,
        template="order_confirmation",
        data={"order_id": event.order_id, "total": event.total},
    )

async def notify_warehouse(event: OrderPaid):
    await warehouse_api.create_fulfillment(event.order_id)


# Wire up
dispatcher = EventDispatcher()
dispatcher.register(OrderSubmitted, send_order_confirmation)
dispatcher.register(OrderPaid, notify_warehouse)
```

### Repository Pattern

Repositories encapsulate data access, presenting a collection-like interface:

```python
from abc import ABC, abstractmethod


class OrderRepository(ABC):
    """Repository interface — defined in domain layer."""

    @abstractmethod
    async def get(self, order_id: UUID) -> Optional[Order]:
        ...

    @abstractmethod
    async def save(self, order: Order) -> None:
        ...

    @abstractmethod
    async def find_by_customer(
        self, customer_id: UUID, status: Optional[OrderStatus] = None
    ) -> list[Order]:
        ...


class SqlOrderRepository(OrderRepository):
    """Implementation — lives in infrastructure layer."""

    def __init__(self, session):
        self.session = session

    async def get(self, order_id: UUID) -> Optional[Order]:
        row = await self.session.fetchrow(
            "SELECT * FROM orders WHERE id = $1", order_id
        )
        if not row:
            return None
        return self._to_domain(row)

    async def save(self, order: Order) -> None:
        await self.session.execute(
            """
            INSERT INTO orders (id, customer_id, status, shipping_address, total)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (id) DO UPDATE SET
                status = $3, total = $5
            """,
            order.id, order.customer_id, order.status.value,
            str(order.shipping_address), str(order.total.amount),
        )
        # Save items...

    def _to_domain(self, row) -> Order:
        """Reconstitute domain object from database row."""
        order = Order.__new__(Order)
        order.id = row["id"]
        order.customer_id = row["customer_id"]
        order._status = OrderStatus(row["status"])
        # ... reconstruct full aggregate
        return order
```

### Bounded Contexts

Large systems are divided into bounded contexts — each with its own model:

```python
# In the ORDER context, a "Product" is:
@dataclass(frozen=True)
class OrderProduct:
    product_id: UUID
    name: str
    price: Money
    # That's all the Order context needs to know

# In the INVENTORY context, a "Product" is:
@dataclass
class InventoryProduct:
    product_id: UUID
    sku: str
    warehouse_location: str
    quantity_on_hand: int
    reorder_point: int
    # Very different model, same real-world thing!

# In the CATALOG context, a "Product" is:
@dataclass
class CatalogProduct:
    product_id: UUID
    name: str
    description: str
    images: list[str]
    categories: list[str]
    specifications: dict

# Contexts communicate through domain events or an anti-corruption layer
# NOT by sharing database tables
```

**DDD decision guide**: (1) Use DDD when business logic is complex — CRUD apps don't need it, (2) Aggregates enforce business rules and consistency boundaries, (3) Value objects eliminate a class of bugs by being immutable and validated at creation, (4) Domain events decouple bounded contexts — the Order context publishes OrderPaid, the Inventory context reacts, (5) Repositories abstract storage — the domain doesn't know about databases."""
    ),
    (
        "architecture/clean-architecture-implementation",
        r"""Explain Clean Architecture (hexagonal/ports-and-adapters) including layer separation, dependency rule, use cases as application services, port and adapter patterns, and how to structure a Python project following these principles.""",
        r"""## Clean Architecture: Dependency Inversion, Ports & Adapters, and Project Structure

Clean Architecture (also called Hexagonal or Ports & Adapters) organizes code so that business logic is independent of frameworks, databases, and external services. The core insight: **dependencies point inward** — outer layers depend on inner layers, never the reverse.

### The Dependency Rule

```
┌─────────────────────────────────────────────┐
│  Frameworks & Drivers (outermost)           │
│  ┌─────────────────────────────────────┐    │
│  │  Interface Adapters                  │    │
│  │  ┌─────────────────────────────┐    │    │
│  │  │  Application (Use Cases)     │    │    │
│  │  │  ┌─────────────────────┐    │    │    │
│  │  │  │  Domain (Entities)   │    │    │    │
│  │  │  │                      │    │    │    │
│  │  │  └─────────────────────┘    │    │    │
│  │  └─────────────────────────────┘    │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘

Dependencies ALWAYS point inward:
  Frameworks → Adapters → Use Cases → Domain
  Domain knows about: NOTHING external
  Use Cases know about: Domain only
  Adapters know about: Use Cases + Domain
  Frameworks know about: Everything
```

### Project Structure

```
src/
├── domain/                    # Inner layer: pure business logic
│   ├── entities/
│   │   ├── order.py          # Aggregate roots, entities
│   │   └── customer.py
│   ├── value_objects/
│   │   ├── money.py
│   │   └── address.py
│   ├── events/
│   │   └── order_events.py   # Domain events
│   ├── errors.py             # Domain exceptions
│   └── ports/                # Interfaces (abstract base classes)
│       ├── repositories.py   # Repository interfaces
│       ├── payment_gateway.py
│       └── notification.py
│
├── application/              # Use cases / application services
│   ├── commands/
│   │   ├── create_order.py
│   │   └── process_payment.py
│   ├── queries/
│   │   ├── get_order.py
│   │   └── list_orders.py
│   └── services/
│       └── order_service.py
│
├── adapters/                 # Interface adapters
│   ├── inbound/              # Driving adapters (trigger use cases)
│   │   ├── rest_api.py       # FastAPI routes
│   │   ├── graphql.py
│   │   └── cli.py
│   └── outbound/             # Driven adapters (implement ports)
│       ├── postgres_order_repo.py
│       ├── stripe_payment.py
│       ├── sendgrid_email.py
│       └── redis_cache.py
│
└── infrastructure/           # Framework configuration
    ├── container.py          # Dependency injection
    ├── database.py           # DB connection setup
    ├── settings.py           # Environment config
    └── main.py               # Application entry point
```

### Ports (Interfaces in Domain Layer)

```python
# domain/ports/repositories.py
from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID
from domain.entities.order import Order


class OrderRepository(ABC):
    """Port: how the domain expects to persist orders."""

    @abstractmethod
    async def get(self, order_id: UUID) -> Optional[Order]:
        ...

    @abstractmethod
    async def save(self, order: Order) -> None:
        ...

    @abstractmethod
    async def next_id(self) -> UUID:
        ...


# domain/ports/payment_gateway.py
class PaymentGateway(ABC):
    """Port: how the domain expects to process payments."""

    @abstractmethod
    async def charge(
        self, customer_id: str, amount: Money, idempotency_key: str
    ) -> PaymentResult:
        ...

    @abstractmethod
    async def refund(self, payment_id: str, amount: Money) -> RefundResult:
        ...


# domain/ports/notification.py
class NotificationService(ABC):
    @abstractmethod
    async def send_order_confirmation(
        self, customer_email: str, order: Order
    ) -> None:
        ...
```

### Use Cases (Application Layer)

```python
# application/commands/create_order.py
from dataclasses import dataclass
from uuid import UUID
from domain.entities.order import Order
from domain.value_objects.money import Money
from domain.value_objects.address import Address
from domain.ports.repositories import OrderRepository
from domain.ports.notification import NotificationService


@dataclass
class CreateOrderCommand:
    """Input DTO — belongs to application layer."""
    customer_id: UUID
    shipping_address: dict
    items: list[dict]  # [{product_id, quantity, unit_price}]


@dataclass
class CreateOrderResult:
    """Output DTO."""
    order_id: UUID
    total: str
    item_count: int


class CreateOrderUseCase:
    """Application service — orchestrates domain objects."""

    def __init__(
        self,
        order_repo: OrderRepository,
        notifications: NotificationService,
    ):
        # Dependencies are PORTS (abstractions), not implementations
        self.order_repo = order_repo
        self.notifications = notifications

    async def execute(self, command: CreateOrderCommand) -> CreateOrderResult:
        # Create domain object
        address = Address(**command.shipping_address)
        order = Order(
            customer_id=command.customer_id,
            shipping_address=address,
        )

        # Add items (domain validates business rules)
        for item in command.items:
            order.add_item(
                product_id=item["product_id"],
                quantity=item["quantity"],
                unit_price=Money(item["unit_price"], "USD"),
            )

        # Submit order (domain enforces invariants)
        events = order.submit()

        # Persist through port
        await self.order_repo.save(order)

        # Side effects
        for event in events:
            if isinstance(event, OrderSubmitted):
                await self.notifications.send_order_confirmation(
                    customer_email="...",
                    order=order,
                )

        # Return result DTO (not domain entity!)
        return CreateOrderResult(
            order_id=order.id,
            total=str(order.total.amount),
            item_count=order.item_count,
        )
```

### Adapters (Implementation Layer)

```python
# adapters/outbound/postgres_order_repo.py
from domain.ports.repositories import OrderRepository
from domain.entities.order import Order


class PostgresOrderRepository(OrderRepository):
    """Adapter: implements OrderRepository port with PostgreSQL."""

    def __init__(self, pool):
        self.pool = pool

    async def get(self, order_id: UUID) -> Optional[Order]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM orders WHERE id = $1", order_id
            )
            if not row:
                return None
            items = await conn.fetch(
                "SELECT * FROM order_items WHERE order_id = $1", order_id
            )
            return self._to_domain(row, items)

    async def save(self, order: Order) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """INSERT INTO orders (id, customer_id, status, total)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (id) DO UPDATE SET status=$3, total=$4""",
                    order.id, order.customer_id,
                    order.status.value, float(order.total.amount),
                )

    async def next_id(self) -> UUID:
        return uuid4()

    def _to_domain(self, row, items) -> Order:
        # Reconstitute domain object from DB representation
        ...


# adapters/outbound/stripe_payment.py
import stripe
from domain.ports.payment_gateway import PaymentGateway


class StripePaymentGateway(PaymentGateway):
    """Adapter: implements PaymentGateway port with Stripe."""

    def __init__(self, api_key: str):
        stripe.api_key = api_key

    async def charge(self, customer_id, amount, idempotency_key):
        intent = stripe.PaymentIntent.create(
            amount=int(amount.amount * 100),
            currency=amount.currency.lower(),
            customer=customer_id,
            idempotency_key=idempotency_key,
        )
        return PaymentResult(
            payment_id=intent.id,
            status="success" if intent.status == "succeeded" else "pending",
        )


# adapters/inbound/rest_api.py
from fastapi import APIRouter, Depends
from application.commands.create_order import CreateOrderCommand, CreateOrderUseCase

router = APIRouter()

@router.post("/orders")
async def create_order(
    body: CreateOrderRequest,
    use_case: CreateOrderUseCase = Depends(get_create_order_use_case),
):
    command = CreateOrderCommand(
        customer_id=body.customer_id,
        shipping_address=body.shipping_address.dict(),
        items=[item.dict() for item in body.items],
    )
    result = await use_case.execute(command)
    return {"order_id": str(result.order_id), "total": result.total}
```

### Dependency Injection

```python
# infrastructure/container.py
from adapters.outbound.postgres_order_repo import PostgresOrderRepository
from adapters.outbound.stripe_payment import StripePaymentGateway
from adapters.outbound.sendgrid_email import SendGridNotificationService
from application.commands.create_order import CreateOrderUseCase


class Container:
    """Wire everything together — the only place that knows all implementations."""

    def __init__(self, config):
        self.config = config
        self._pool = None

    async def initialize(self):
        import asyncpg
        self._pool = await asyncpg.create_pool(self.config.database_url)

    def order_repository(self):
        return PostgresOrderRepository(self._pool)

    def payment_gateway(self):
        return StripePaymentGateway(self.config.stripe_key)

    def notifications(self):
        return SendGridNotificationService(self.config.sendgrid_key)

    def create_order_use_case(self):
        return CreateOrderUseCase(
            order_repo=self.order_repository(),
            notifications=self.notifications(),
        )
```

### Testing Benefits

```python
# Domain tests: no mocks, no infrastructure
def test_order_cannot_exceed_max_total():
    order = Order(customer_id=uuid4(), shipping_address=test_address)
    order.add_item(uuid4(), 1, Money(Decimal("9999"), "USD"))

    with pytest.raises(DomainError, match="exceed maximum"):
        order.add_item(uuid4(), 1, Money(Decimal("100"), "USD"))


# Use case tests: mock only ports
async def test_create_order():
    mock_repo = AsyncMock(spec=OrderRepository)
    mock_notifications = AsyncMock(spec=NotificationService)

    use_case = CreateOrderUseCase(mock_repo, mock_notifications)
    result = await use_case.execute(CreateOrderCommand(...))

    assert result.order_id is not None
    mock_repo.save.assert_awaited_once()
```

**Clean Architecture benefits**: (1) Domain logic is testable without any infrastructure, (2) Swapping databases/frameworks requires changing only adapters, (3) Use cases document the application's capabilities explicitly, (4) The dependency rule prevents infrastructure concerns from leaking into business logic, (5) Multiple entry points (REST, CLI, GraphQL) share the same use cases."""
    ),
    (
        "architecture/cqrs-event-sourcing",
        r"""Explain CQRS (Command Query Responsibility Segregation) and Event Sourcing patterns including when to use them, implementing commands and queries separately, event stores, projections/read models, and eventual consistency trade-offs.""",
        r"""## CQRS and Event Sourcing: Separating Reads from Writes

CQRS separates the write model (commands) from the read model (queries). Event Sourcing stores state as a sequence of events rather than current state. They're often used together but are independent patterns.

### CQRS Without Event Sourcing

The simpler form — separate models for reading and writing:

```python
from dataclasses import dataclass
from uuid import UUID
from typing import Optional

# ── COMMAND SIDE (writes) ──

@dataclass
class PlaceOrderCommand:
    customer_id: UUID
    items: list[dict]
    shipping_address: dict


class OrderCommandHandler:
    """Handles write operations with full domain logic."""

    def __init__(self, order_repo, event_bus):
        self.order_repo = order_repo
        self.event_bus = event_bus

    async def handle_place_order(self, cmd: PlaceOrderCommand) -> UUID:
        # Full domain model with validation and business rules
        order = Order(customer_id=cmd.customer_id, ...)
        for item in cmd.items:
            order.add_item(...)
        order.submit()

        await self.order_repo.save(order)
        await self.event_bus.publish(order.collect_events())
        return order.id


# ── QUERY SIDE (reads) ──

@dataclass
class OrderSummary:
    """Flat read model — optimized for display, no business logic."""
    order_id: UUID
    customer_name: str
    total: float
    status: str
    item_count: int
    created_at: str


class OrderQueryHandler:
    """Handles read operations against denormalized read store."""

    def __init__(self, read_db):
        self.read_db = read_db

    async def get_order_summary(self, order_id: UUID) -> Optional[OrderSummary]:
        # Direct query against read-optimized table/view
        row = await self.read_db.fetchrow(
            """
            SELECT o.id, c.name as customer_name, o.total,
                   o.status, o.item_count, o.created_at
            FROM order_summaries o
            JOIN customers c ON o.customer_id = c.id
            WHERE o.id = $1
            """, order_id
        )
        return OrderSummary(**row) if row else None

    async def list_recent_orders(
        self, customer_id: UUID, limit: int = 20
    ) -> list[OrderSummary]:
        rows = await self.read_db.fetch(
            """
            SELECT * FROM order_summaries
            WHERE customer_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """, customer_id, limit
        )
        return [OrderSummary(**r) for r in rows]
```

### Event Sourcing: State as Event Stream

Instead of storing current state, store the sequence of events that led to it:

```python
from abc import ABC, abstractmethod
import json
from datetime import datetime, timezone


@dataclass(frozen=True)
class StoredEvent:
    event_id: UUID
    aggregate_id: UUID
    aggregate_type: str
    event_type: str
    event_data: dict
    version: int
    occurred_at: datetime


class EventStore:
    """Append-only event store."""

    def __init__(self, db):
        self.db = db

    async def append(
        self,
        aggregate_id: UUID,
        aggregate_type: str,
        events: list,
        expected_version: int,
    ):
        """Append events with optimistic concurrency control."""
        async with self.db.transaction():
            # Check current version matches expected
            current = await self.db.fetchval(
                """SELECT COALESCE(MAX(version), 0)
                FROM events WHERE aggregate_id = $1""",
                aggregate_id,
            )
            if current != expected_version:
                raise ConcurrencyError(
                    f"Expected version {expected_version}, "
                    f"got {current} for {aggregate_id}"
                )

            # Append new events
            for i, event in enumerate(events):
                version = expected_version + i + 1
                await self.db.execute(
                    """INSERT INTO events
                    (event_id, aggregate_id, aggregate_type,
                     event_type, event_data, version, occurred_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    uuid4(), aggregate_id, aggregate_type,
                    type(event).__name__,
                    json.dumps(event.__dict__, default=str),
                    version,
                    datetime.now(timezone.utc),
                )

    async def get_events(
        self, aggregate_id: UUID, after_version: int = 0
    ) -> list[StoredEvent]:
        rows = await self.db.fetch(
            """SELECT * FROM events
            WHERE aggregate_id = $1 AND version > $2
            ORDER BY version""",
            aggregate_id, after_version,
        )
        return [StoredEvent(**r) for r in rows]


# Event-sourced aggregate
class EventSourcedOrder:
    """Order aggregate rebuilt from events."""

    def __init__(self):
        self.id: Optional[UUID] = None
        self._items: list = []
        self._status = None
        self._version = 0
        self._pending_events: list = []

    # ── Command methods (produce events) ──

    @classmethod
    def create(cls, order_id: UUID, customer_id: UUID) -> "EventSourcedOrder":
        order = cls()
        order._apply(OrderCreated(order_id=order_id, customer_id=customer_id))
        return order

    def add_item(self, product_id: UUID, quantity: int, price: float):
        if self._status != "draft":
            raise DomainError("Cannot modify non-draft order")
        self._apply(ItemAdded(
            order_id=self.id, product_id=product_id,
            quantity=quantity, price=price,
        ))

    def submit(self):
        if not self._items:
            raise DomainError("Cannot submit empty order")
        self._apply(OrderSubmittedEvent(
            order_id=self.id,
            total=sum(i["price"] * i["quantity"] for i in self._items),
        ))

    # ── Event application (state transitions) ──

    def _apply(self, event):
        self._pending_events.append(event)
        self._mutate(event)

    def _mutate(self, event):
        """Apply event to state — called for both new and replayed events."""
        handler = getattr(self, f"_on_{type(event).__name__}", None)
        if handler:
            handler(event)
        self._version += 1

    def _on_OrderCreated(self, event):
        self.id = event.order_id
        self._status = "draft"

    def _on_ItemAdded(self, event):
        self._items.append({
            "product_id": event.product_id,
            "quantity": event.quantity,
            "price": event.price,
        })

    def _on_OrderSubmittedEvent(self, event):
        self._status = "submitted"

    # ── Reconstitution ──

    @classmethod
    def from_events(cls, events: list) -> "EventSourcedOrder":
        """Rebuild aggregate from event history."""
        order = cls()
        for event in events:
            order._mutate(event)
        return order

    def collect_pending(self) -> tuple[list, int]:
        events = self._pending_events.copy()
        version = self._version - len(events)
        self._pending_events.clear()
        return events, version
```

### Projections (Read Models)

Build read-optimized views by processing the event stream:

```python
class OrderSummaryProjection:
    """Builds a denormalized read model from events."""

    def __init__(self, read_db):
        self.read_db = read_db

    async def handle(self, event: StoredEvent):
        """Route events to handlers."""
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            await handler(event)

    async def _on_OrderCreated(self, event: StoredEvent):
        data = event.event_data
        await self.read_db.execute(
            """INSERT INTO order_summaries
            (id, customer_id, status, total, item_count, created_at)
            VALUES ($1, $2, 'draft', 0, 0, $3)""",
            event.aggregate_id, data["customer_id"], event.occurred_at,
        )

    async def _on_ItemAdded(self, event: StoredEvent):
        data = event.event_data
        await self.read_db.execute(
            """UPDATE order_summaries
            SET item_count = item_count + 1,
                total = total + $2
            WHERE id = $1""",
            event.aggregate_id, data["price"] * data["quantity"],
        )

    async def _on_OrderSubmittedEvent(self, event: StoredEvent):
        await self.read_db.execute(
            """UPDATE order_summaries SET status = 'submitted' WHERE id = $1""",
            event.aggregate_id,
        )


class ProjectionRunner:
    """Runs projections by consuming the event stream."""

    def __init__(self, event_store, projections: list):
        self.event_store = event_store
        self.projections = projections

    async def run(self):
        """Process all events through all projections."""
        last_position = await self._get_checkpoint()

        while True:
            events = await self.event_store.get_events_after(last_position)
            if not events:
                await asyncio.sleep(1)
                continue

            for event in events:
                for projection in self.projections:
                    await projection.handle(event)
                last_position = event.version

            await self._save_checkpoint(last_position)

    async def rebuild(self, projection):
        """Rebuild a projection from scratch."""
        await projection.reset()
        all_events = await self.event_store.get_all_events()
        for event in all_events:
            await projection.handle(event)
```

### When to Use CQRS and Event Sourcing

```
Use CQRS (without Event Sourcing) when:
✓ Read and write models have very different shapes
✓ Read-heavy workload (different optimization needs)
✓ Multiple read representations of the same data
✓ You need to scale reads and writes independently

Use Event Sourcing when:
✓ Audit trail is a hard requirement (finance, healthcare)
✓ You need temporal queries ("what was the state at time X?")
✓ The event stream IS the business value (activity feeds, analytics)
✓ You need to replay events to fix bugs or add features

Do NOT use when:
✗ Simple CRUD with no complex business logic
✗ The team is unfamiliar with eventual consistency
✗ You can't accept eventual consistency between reads and writes
✗ The domain doesn't naturally express itself in events
```

**CQRS/ES trade-offs**: (1) CQRS adds complexity — only use when read/write models genuinely differ, (2) Event Sourcing gives perfect audit trails but projections introduce eventual consistency, (3) Projections can be rebuilt from events — this is a superpower for fixing bugs and adding views, (4) Optimistic concurrency (expected version) prevents conflicting updates, (5) Start with CQRS without Event Sourcing — add ES only if the event stream provides clear business value."""
    ),
]
