"""p15 ddd"""

PAIRS = [
    (
        "architecture/domain-driven-design-fundamentals",
        "Explain Domain-Driven Design fundamentals including bounded contexts, aggregates, entities vs value objects, domain events, repositories, and the ubiquitous language. Show how to implement these patterns in Python with practical examples.",
        '''DDD is an approach to software design that centers the development on the business domain. It's most valuable for complex business logic where the domain is the hardest part of the problem.

### Ubiquitous Language

The foundation of DDD -- developers and domain experts use the SAME terms:

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
            (i for i in self._items if i.product_id == product_id), None'''
    ),
    (
        "architecture/clean-architecture-implementation",
        "Explain Clean Architecture (hexagonal/ports-and-adapters) including layer separation, dependency rule, use cases as application services, port and adapter patterns, and how to structure a Python project following these principles.",
        '''Clean Architecture (also called Hexagonal or Ports & Adapters) organizes code so that business logic is independent of frameworks, databases, and external services. The core insight: **dependencies point inward** -- outer layers depend on inner layers, never the reverse.

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
  Frameworks -> Adapters -> Use Cases -> Domain
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
    """Input DTO -- belongs to application layer."""
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
    """Application service -- orchestrates domain objects."""

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
            shipping_address=address,'''
    ),
    (
        "architecture/cqrs-event-sourcing",
        "Explain CQRS (Command Query Responsibility Segregation) and Event Sourcing patterns including when to use them, implementing commands and queries separately, event stores, projections/read models, and eventual consistency trade-offs.",
        '''CQRS separates the write model (commands) from the read model (queries). Event Sourcing stores state as a sequence of events rather than current state. They're often used together but are independent patterns.

### CQRS Without Event Sourcing

The simpler form -- separate models for reading and writing:

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
    """Flat read model -- optimized for display, no business logic."""
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
            """, order_id'''
    ),
    (
        "price",
        "}) def _on_OrderSubmittedEvent(self, event): self._status = 'submitted",
        '''@classmethod
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
            event.aggregate_id, data["customer_id"], event.occurred_at,'''
    ),
]
