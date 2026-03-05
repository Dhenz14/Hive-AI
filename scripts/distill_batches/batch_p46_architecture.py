"""Architecture patterns — hexagonal, clean architecture, DDD, and CQRS."""

PAIRS = [
    (
        "architecture/hexagonal",
        "Show hexagonal architecture (ports and adapters) in Python: domain core, ports, adapters, and dependency injection.",
        '''Hexagonal architecture (ports and adapters) in Python:

```python
# --- Domain core (no external dependencies) ---

# domain/models.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

@dataclass
class OrderItem:
    product_id: str
    name: str
    price: float
    quantity: int

    @property
    def total(self) -> float:
        return self.price * self.quantity

@dataclass
class Order:
    id: str
    customer_id: str
    items: list[OrderItem] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total(self) -> float:
        return sum(item.total for item in self.items)

    def confirm(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"Cannot confirm order in {self.status} state")
        if not self.items:
            raise ValueError("Cannot confirm empty order")
        self.status = OrderStatus.CONFIRMED

    def cancel(self) -> None:
        if self.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise ValueError("Cannot cancel shipped/delivered order")
        self.status = OrderStatus.CANCELLED


# --- Ports (interfaces the domain needs) ---

# domain/ports.py
from abc import ABC, abstractmethod

class OrderRepository(ABC):
    @abstractmethod
    async def save(self, order: Order) -> None: ...

    @abstractmethod
    async def find_by_id(self, order_id: str) -> Optional[Order]: ...

    @abstractmethod
    async def find_by_customer(self, customer_id: str) -> list[Order]: ...

class PaymentGateway(ABC):
    @abstractmethod
    async def charge(self, customer_id: str, amount: float,
                     order_id: str) -> str: ...

    @abstractmethod
    async def refund(self, payment_id: str) -> None: ...

class NotificationService(ABC):
    @abstractmethod
    async def send(self, customer_id: str, subject: str,
                   body: str) -> None: ...

class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event_type: str, data: dict) -> None: ...


# --- Application services (use cases / orchestration) ---

# application/order_service.py
class OrderService:
    def __init__(
        self,
        orders: OrderRepository,
        payments: PaymentGateway,
        notifications: NotificationService,
        events: EventPublisher,
    ):
        self.orders = orders
        self.payments = payments
        self.notifications = notifications
        self.events = events

    async def create_order(self, customer_id: str,
                           items: list[dict]) -> Order:
        order = Order(
            id=generate_id(),
            customer_id=customer_id,
            items=[OrderItem(**item) for item in items],
        )
        await self.orders.save(order)
        await self.events.publish("order.created", {"order_id": order.id})
        return order

    async def confirm_order(self, order_id: str) -> Order:
        order = await self.orders.find_by_id(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        order.confirm()
        payment_id = await self.payments.charge(
            order.customer_id, order.total, order.id
        )
        await self.orders.save(order)
        await self.notifications.send(
            order.customer_id,
            "Order Confirmed",
            f"Order {order.id} confirmed. Total: ${order.total:.2f}",
        )
        await self.events.publish("order.confirmed", {
            "order_id": order.id, "payment_id": payment_id,
        })
        return order


# --- Adapters (implementations of ports) ---

# adapters/postgres_order_repo.py
class PostgresOrderRepository(OrderRepository):
    def __init__(self, pool):
        self.pool = pool

    async def save(self, order: Order) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO orders (id, customer_id, status, total, created_at) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (id) DO UPDATE SET status = $3",
                order.id, order.customer_id, order.status.value,
                order.total, order.created_at,
            )

    async def find_by_id(self, order_id: str) -> Optional[Order]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM orders WHERE id = $1", order_id
            )
            return self._to_domain(row) if row else None


# adapters/stripe_payment.py
class StripePaymentGateway(PaymentGateway):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def charge(self, customer_id, amount, order_id) -> str:
        # Call Stripe API
        ...

# adapters/email_notification.py
class EmailNotificationService(NotificationService):
    async def send(self, customer_id, subject, body) -> None:
        # Send via SMTP/SES
        ...


# --- Composition root (wire everything together) ---

# main.py
async def create_app():
    pool = await create_db_pool()
    order_service = OrderService(
        orders=PostgresOrderRepository(pool),
        payments=StripePaymentGateway(os.environ["STRIPE_KEY"]),
        notifications=EmailNotificationService(),
        events=RabbitMQEventPublisher(),
    )
    # Register routes using order_service
    ...
```

Hexagonal rules:
1. **Domain core has zero imports** from frameworks or infrastructure
2. **Ports** are abstract interfaces the domain defines
3. **Adapters** implement ports with specific technologies
4. **Dependency flows inward** — adapters depend on ports, never the reverse
5. **Easy to test** — inject mock adapters for unit tests'''
    ),
    (
        "architecture/domain-driven-design",
        "Show DDD tactical patterns in Python: aggregates, value objects, domain events, and bounded contexts.",
        '''Domain-Driven Design tactical patterns:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from abc import ABC, abstractmethod
from uuid import uuid4
import re


# --- Value Objects (immutable, compared by value) ---

@dataclass(frozen=True)
class Money:
    amount: int        # Store in cents to avoid float issues
    currency: str = "USD"

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")
        if self.currency not in ("USD", "EUR", "GBP"):
            raise ValueError(f"Unsupported currency: {self.currency}")

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, factor: int) -> "Money":
        return Money(self.amount * factor, self.currency)

    @property
    def dollars(self) -> float:
        return self.amount / 100

    @classmethod
    def from_dollars(cls, dollars: float, currency: str = "USD") -> "Money":
        return cls(round(dollars * 100), currency)


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self):
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", self.value):
            raise ValueError(f"Invalid email: {self.value}")
        object.__setattr__(self, 'value', self.value.lower())


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"


# --- Domain Events ---

@dataclass(frozen=True)
class DomainEvent:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    order_id: str = ""
    customer_id: str = ""
    total: Money = field(default_factory=lambda: Money(0))

@dataclass(frozen=True)
class OrderShipped(DomainEvent):
    order_id: str = ""
    tracking_number: str = ""

@dataclass(frozen=True)
class PaymentReceived(DomainEvent):
    order_id: str = ""
    payment_id: str = ""
    amount: Money = field(default_factory=lambda: Money(0))


# --- Aggregate Root ---

class AggregateRoot:
    """Base class for aggregates that collect domain events."""

    def __init__(self):
        self._events: list[DomainEvent] = []

    def _record(self, event: DomainEvent):
        self._events.append(event)

    def collect_events(self) -> list[DomainEvent]:
        events = self._events.copy()
        self._events.clear()
        return events


@dataclass
class OrderLine:
    product_id: str
    product_name: str
    unit_price: Money
    quantity: int

    @property
    def total(self) -> Money:
        return self.unit_price * self.quantity


class Order(AggregateRoot):
    """Order aggregate — enforces all business rules."""

    def __init__(self, id: str, customer_id: str):
        super().__init__()
        self.id = id
        self.customer_id = customer_id
        self.lines: list[OrderLine] = []
        self.status = "draft"
        self.shipping_address: Optional[Address] = None
        self.version = 0  # Optimistic concurrency

    @property
    def total(self) -> Money:
        if not self.lines:
            return Money(0)
        result = self.lines[0].total
        for line in self.lines[1:]:
            result = result + line.total
        return result

    def add_line(self, product_id: str, name: str,
                 price: Money, quantity: int) -> None:
        if self.status != "draft":
            raise ValueError("Can only add items to draft orders")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        # Business rule: max 20 unique items per order
        if len(self.lines) >= 20:
            raise ValueError("Maximum 20 items per order")

        existing = next((l for l in self.lines if l.product_id == product_id), None)
        if existing:
            existing.quantity += quantity
        else:
            self.lines.append(OrderLine(product_id, name, price, quantity))

    def place(self, shipping_address: Address) -> None:
        if self.status != "draft":
            raise ValueError("Order already placed")
        if not self.lines:
            raise ValueError("Cannot place empty order")
        if self.total.amount < 100:  # Min $1.00
            raise ValueError("Minimum order is $1.00")

        self.shipping_address = shipping_address
        self.status = "placed"
        self._record(OrderPlaced(
            order_id=self.id,
            customer_id=self.customer_id,
            total=self.total,
        ))

    def mark_shipped(self, tracking_number: str) -> None:
        if self.status != "paid":
            raise ValueError("Can only ship paid orders")
        self.status = "shipped"
        self._record(OrderShipped(
            order_id=self.id,
            tracking_number=tracking_number,
        ))


# --- Repository (persistence boundary) ---

class OrderRepository(ABC):
    @abstractmethod
    async def save(self, order: Order) -> None: ...

    @abstractmethod
    async def find_by_id(self, id: str) -> Optional[Order]: ...


# --- Domain Service (logic spanning aggregates) ---

class PricingService:
    """Calculate discounts across order + customer context."""

    async def calculate_discount(self, order: Order,
                                 customer_tier: str) -> Money:
        discount_pct = {"bronze": 0, "silver": 5, "gold": 10, "platinum": 15}
        pct = discount_pct.get(customer_tier, 0)
        return Money(round(order.total.amount * pct / 100))
```

DDD tactical patterns:
1. **Value Objects** — immutable, validated at creation, compared by value (Money, Email)
2. **Aggregates** — consistency boundaries with business rule enforcement
3. **Domain Events** — record what happened for other parts of the system
4. **Repository** — abstract persistence, deal only in domain objects
5. **Domain Services** — logic that spans multiple aggregates'''
    ),
    (
        "architecture/clean-architecture",
        "Show clean architecture in Python: entities, use cases, interface adapters, and frameworks layer.",
        '''Clean architecture layers in Python:

```python
# Layer 1: ENTITIES (innermost — business rules)
# entities/user.py

from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass
class User:
    id: str
    email: str
    name: str
    hashed_password: str
    is_active: bool = True
    created_at: datetime = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc)

    def deactivate(self):
        self.is_active = False

    def can_login(self) -> bool:
        return self.is_active


# Layer 2: USE CASES (application business rules)
# use_cases/register_user.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

# Input/Output DTOs
@dataclass
class RegisterUserInput:
    email: str
    name: str
    password: str

@dataclass
class RegisterUserOutput:
    user_id: str
    email: str
    name: str

# Port interfaces (defined in use case layer)
class UserRepository(ABC):
    @abstractmethod
    async def find_by_email(self, email: str) -> Optional[User]: ...
    @abstractmethod
    async def save(self, user: User) -> None: ...

class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str: ...
    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool: ...

class IdGenerator(ABC):
    @abstractmethod
    def generate(self) -> str: ...

# Use case
class RegisterUser:
    def __init__(self, users: UserRepository,
                 hasher: PasswordHasher, id_gen: IdGenerator):
        self.users = users
        self.hasher = hasher
        self.id_gen = id_gen

    async def execute(self, input: RegisterUserInput) -> RegisterUserOutput:
        # Business rule: unique email
        existing = await self.users.find_by_email(input.email)
        if existing:
            raise ValueError(f"Email already registered: {input.email}")

        # Business rule: password strength
        if len(input.password) < 8:
            raise ValueError("Password must be at least 8 characters")

        user = User(
            id=self.id_gen.generate(),
            email=input.email.lower(),
            name=input.name,
            hashed_password=self.hasher.hash(input.password),
        )
        await self.users.save(user)

        return RegisterUserOutput(
            user_id=user.id, email=user.email, name=user.name,
        )


# Layer 3: INTERFACE ADAPTERS (controllers, presenters, gateways)
# adapters/api/user_controller.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

router = APIRouter()

class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str

class RegisterResponse(BaseModel):
    user_id: str
    email: str
    name: str

@router.post("/users", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    use_case = get_register_user_use_case()  # From DI container
    try:
        result = await use_case.execute(RegisterUserInput(
            email=req.email, name=req.name, password=req.password,
        ))
        return RegisterResponse(
            user_id=result.user_id, email=result.email, name=result.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# adapters/persistence/sqlalchemy_user_repo.py

class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session):
        self.session = session

    async def find_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def save(self, user: User) -> None:
        model = self._to_model(user)
        self.session.add(model)
        await self.session.commit()

    def _to_entity(self, model) -> User:
        return User(
            id=model.id, email=model.email, name=model.name,
            hashed_password=model.hashed_password,
            is_active=model.is_active, created_at=model.created_at,
        )


# Layer 4: FRAMEWORKS (outermost — composition root)
# main.py

from fastapi import FastAPI

def create_app() -> FastAPI:
    app = FastAPI()

    # Wire dependencies
    pool = create_db_pool()
    container = DependencyContainer(
        user_repo=SQLAlchemyUserRepository(pool),
        password_hasher=Argon2Hasher(),
        id_generator=UUIDGenerator(),
    )
    set_container(container)

    app.include_router(user_controller.router, prefix="/api")
    return app
```

Clean architecture rules:
1. **Dependency Rule** — dependencies point inward only (frameworks → adapters → use cases → entities)
2. **Entities** — pure business objects, no framework imports
3. **Use cases** — orchestrate entities, define port interfaces
4. **Adapters** — translate between use cases and external systems
5. **Testability** — test use cases with mock ports, no database needed'''
    ),
]
