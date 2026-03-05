"""Domain-Driven Design patterns — aggregates, repositories, domain events."""

PAIRS = [
    (
        "architecture/ddd-aggregates",
        "Show DDD aggregate design: aggregate roots, invariant enforcement, entity identity, and value objects.",
        '''DDD aggregate design:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4


# Value Objects (immutable, compared by value)
@dataclass(frozen=True)
class Money:
    amount: float
    currency: str = "USD"

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, factor: float) -> "Money":
        return Money(round(self.amount * factor, 2), self.currency)


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"


# Entity (has identity, mutable)
@dataclass
class OrderItem:
    id: str = field(default_factory=lambda: str(uuid4()))
    product_id: str = ""
    product_name: str = ""
    quantity: int = 0
    unit_price: Money = field(default_factory=lambda: Money(0))

    @property
    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


# Aggregate Root (controls all access to aggregate)
class Order:
    """Order aggregate — enforces all business invariants.

    Rules:
    - Cannot add items to shipped/cancelled orders
    - Maximum 50 items per order
    - Minimum order value $10
    - Cannot ship without payment
    """

    def __init__(self, customer_id: str, shipping_address: Address):
        self.id = str(uuid4())
        self.customer_id = customer_id
        self.shipping_address = shipping_address
        self.items: list[OrderItem] = []
        self.status = "draft"
        self.payment_id: Optional[str] = None
        self.created_at = datetime.utcnow()
        self._events: list[dict] = []

    def add_item(self, product_id: str, name: str, qty: int, price: Money):
        """Add item — enforce invariants."""
        if self.status not in ("draft", "pending"):
            raise DomainError("Cannot modify order in status: " + self.status)
        if len(self.items) >= 50:
            raise DomainError("Maximum 50 items per order")
        if qty <= 0:
            raise DomainError("Quantity must be positive")

        item = OrderItem(product_id=product_id, product_name=name,
                          quantity=qty, unit_price=price)
        self.items.append(item)
        self._events.append({"type": "ItemAdded", "item_id": item.id})

    def remove_item(self, item_id: str):
        if self.status not in ("draft", "pending"):
            raise DomainError("Cannot modify order in status: " + self.status)
        self.items = [i for i in self.items if i.id != item_id]

    @property
    def total(self) -> Money:
        if not self.items:
            return Money(0)
        return Money(sum(i.subtotal.amount for i in self.items))

    def submit(self):
        if self.total.amount < 10:
            raise DomainError("Minimum order value is $10")
        if not self.items:
            raise DomainError("Cannot submit empty order")
        self.status = "pending"
        self._events.append({"type": "OrderSubmitted", "order_id": self.id})

    def confirm_payment(self, payment_id: str):
        if self.status != "pending":
            raise DomainError("Order must be pending to confirm payment")
        self.payment_id = payment_id
        self.status = "paid"
        self._events.append({"type": "PaymentConfirmed"})

    def ship(self, tracking_number: str):
        if self.status != "paid":
            raise DomainError("Order must be paid before shipping")
        self.status = "shipped"
        self._events.append({"type": "OrderShipped",
                              "tracking": tracking_number})

    def collect_events(self) -> list[dict]:
        events = self._events.copy()
        self._events.clear()
        return events


class DomainError(Exception):
    pass
```

Key patterns:
1. **Aggregate root** — single entry point; all modifications go through Order, never directly to items
2. **Invariant enforcement** — business rules checked at mutation; invalid states impossible
3. **Value objects** — Money, Address are immutable; compared by value, not identity
4. **Domain events** — collect events during mutations; publish after save for side effects
5. **Status machine** — draft → pending → paid → shipped; each transition has preconditions'''
    ),
    (
        "architecture/repository-pattern",
        "Show the repository pattern: abstracting persistence, unit of work, and specification queries.",
        '''Repository pattern with unit of work:

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional


T = TypeVar("T")


class Repository(ABC, Generic[T]):
    """Abstract repository — persistence interface."""

    @abstractmethod
    async def get(self, id: str) -> Optional[T]:
        ...

    @abstractmethod
    async def save(self, entity: T) -> None:
        ...

    @abstractmethod
    async def delete(self, id: str) -> None:
        ...


class OrderRepository(Repository):
    """Concrete repository for Order aggregate."""

    def __init__(self, db_session):
        self.session = db_session

    async def get(self, order_id: str) -> Optional["Order"]:
        row = await self.session.fetchrow(
            "SELECT * FROM orders WHERE id = $1", order_id
        )
        if not row:
            return None
        items = await self.session.fetch(
            "SELECT * FROM order_items WHERE order_id = $1", order_id
        )
        return self._to_domain(row, items)

    async def save(self, order: "Order"):
        await self.session.execute(
            """INSERT INTO orders (id, customer_id, status, total, created_at)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (id) DO UPDATE SET status = $3, total = $4""",
            order.id, order.customer_id, order.status,
            order.total.amount, order.created_at,
        )
        for item in order.items:
            await self.session.execute(
                """INSERT INTO order_items (id, order_id, product_id, quantity, price)
                   VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING""",
                item.id, order.id, item.product_id, item.quantity,
                item.unit_price.amount,
            )

    async def delete(self, order_id: str):
        await self.session.execute("DELETE FROM order_items WHERE order_id = $1", order_id)
        await self.session.execute("DELETE FROM orders WHERE id = $1", order_id)

    def _to_domain(self, row, item_rows) -> "Order":
        order = Order.__new__(Order)
        order.id = row["id"]
        order.customer_id = row["customer_id"]
        order.status = row["status"]
        order.items = [
            OrderItem(id=r["id"], product_id=r["product_id"],
                      quantity=r["quantity"],
                      unit_price=Money(r["price"]))
            for r in item_rows
        ]
        order._events = []
        return order


class UnitOfWork:
    """Track changes and commit atomically."""

    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.conn = None
        self._repositories: dict = {}
        self._events: list = []

    async def __aenter__(self):
        self.conn = await self.db_pool.acquire()
        self.tx = self.conn.transaction()
        await self.tx.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.tx.rollback()
        else:
            await self.tx.commit()
            # Publish collected domain events after commit
            for event in self._events:
                await self._publish(event)
        await self.db_pool.release(self.conn)

    @property
    def orders(self) -> OrderRepository:
        if "orders" not in self._repositories:
            self._repositories["orders"] = OrderRepository(self.conn)
        return self._repositories["orders"]

    def collect_events(self, entity):
        self._events.extend(entity.collect_events())

    async def _publish(self, event):
        pass  # Publish to event bus
```

Key patterns:
1. **Repository abstraction** — domain layer doesn't know about SQL/ORM; clean boundaries
2. **Reconstitution** — map DB rows back to domain objects with full behavior
3. **Unit of work** — group related saves in one transaction; all-or-nothing
4. **Event publishing after commit** — collect events during work, publish only after successful commit
5. **Aggregate loading** — load root entity + child entities together; enforce consistency boundary'''
    ),
]
