"""Design patterns — creational, structural, behavioral patterns in Python with practical examples."""

PAIRS = [
    (
        "patterns/creational-patterns",
        "Show creational design patterns in Python: Factory, Builder, Singleton, and Prototype with practical use cases.",
        '''Creational patterns for flexible object construction:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from copy import deepcopy

# --- Factory Method ---

class Notification(ABC):
    @abstractmethod
    def send(self, message: str, recipient: str): ...

class EmailNotification(Notification):
    def send(self, message: str, recipient: str):
        print(f"Email to {recipient}: {message}")

class SMSNotification(Notification):
    def send(self, message: str, recipient: str):
        print(f"SMS to {recipient}: {message}")

class SlackNotification(Notification):
    def send(self, message: str, recipient: str):
        print(f"Slack to #{recipient}: {message}")

class NotificationFactory:
    _creators = {
        "email": EmailNotification,
        "sms": SMSNotification,
        "slack": SlackNotification,
    }

    @classmethod
    def create(cls, channel: str) -> Notification:
        creator = cls._creators.get(channel)
        if not creator:
            raise ValueError(f"Unknown channel: {channel}")
        return creator()

    @classmethod
    def register(cls, channel: str, creator: type):
        cls._creators[channel] = creator

# Usage:
notifier = NotificationFactory.create("email")
notifier.send("Hello!", "user@example.com")

# --- Builder Pattern ---

@dataclass
class HTTPRequest:
    method: str = "GET"
    url: str = ""
    headers: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    body: Optional[Any] = None
    timeout: float = 30.0
    retries: int = 0
    auth: Optional[tuple] = None

class RequestBuilder:
    def __init__(self):
        self._request = HTTPRequest()

    def method(self, method: str) -> "RequestBuilder":
        self._request.method = method
        return self

    def url(self, url: str) -> "RequestBuilder":
        self._request.url = url
        return self

    def header(self, key: str, value: str) -> "RequestBuilder":
        self._request.headers[key] = value
        return self

    def param(self, key: str, value: str) -> "RequestBuilder":
        self._request.params[key] = value
        return self

    def json_body(self, data: dict) -> "RequestBuilder":
        self._request.body = data
        self._request.headers["Content-Type"] = "application/json"
        return self

    def timeout(self, seconds: float) -> "RequestBuilder":
        self._request.timeout = seconds
        return self

    def with_retries(self, count: int) -> "RequestBuilder":
        self._request.retries = count
        return self

    def bearer_auth(self, token: str) -> "RequestBuilder":
        self._request.headers["Authorization"] = f"Bearer {token}"
        return self

    def build(self) -> HTTPRequest:
        if not self._request.url:
            raise ValueError("URL is required")
        return self._request

# Usage:
request = (RequestBuilder()
    .method("POST")
    .url("https://api.example.com/users")
    .bearer_auth("token123")
    .json_body({"name": "Alice"})
    .timeout(10)
    .with_retries(3)
    .build())

# --- Registry / Prototype ---

class ConfigPrototype:
    """Clone pre-configured objects instead of building from scratch."""
    _registry: dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, prototype: Any):
        cls._registry[name] = prototype

    @classmethod
    def create(cls, name: str, **overrides) -> Any:
        prototype = cls._registry.get(name)
        if not prototype:
            raise KeyError(f"No prototype: {name}")
        instance = deepcopy(prototype)
        for key, value in overrides.items():
            setattr(instance, key, value)
        return instance

# Register prototypes
ConfigPrototype.register("dev_db", DatabaseConfig(
    host="localhost", port=5432, database="app_dev",
    pool_size=5, ssl=False,
))
ConfigPrototype.register("prod_db", DatabaseConfig(
    host="db.prod.internal", port=5432, database="app_prod",
    pool_size=50, ssl=True,
))

# Clone and customize
my_db = ConfigPrototype.create("prod_db", pool_size=20)
```

When to use:
- **Factory** — create objects without specifying exact class (plugins, strategies)
- **Builder** — construct complex objects step-by-step (configs, queries, requests)
- **Prototype** — clone pre-configured templates (database configs, test fixtures)
- **Singleton** — use module-level instances in Python instead (simpler)'''
    ),
    (
        "patterns/behavioral-patterns",
        "Show behavioral design patterns in Python: Strategy, Observer, Command, Chain of Responsibility, and State Machine.",
        '''Behavioral patterns for flexible runtime behavior:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from enum import Enum, auto

# --- Strategy Pattern ---

class PricingStrategy(ABC):
    @abstractmethod
    def calculate(self, base_price: float, quantity: int) -> float: ...

class RegularPricing(PricingStrategy):
    def calculate(self, base_price: float, quantity: int) -> float:
        return base_price * quantity

class BulkPricing(PricingStrategy):
    def calculate(self, base_price: float, quantity: int) -> float:
        if quantity >= 100:
            return base_price * quantity * 0.7  # 30% discount
        elif quantity >= 10:
            return base_price * quantity * 0.9  # 10% discount
        return base_price * quantity

class SubscriptionPricing(PricingStrategy):
    def __init__(self, monthly_rate: float):
        self.monthly_rate = monthly_rate

    def calculate(self, base_price: float, quantity: int) -> float:
        return self.monthly_rate  # Flat rate regardless of quantity

class OrderCalculator:
    def __init__(self, strategy: PricingStrategy):
        self.strategy = strategy

    def total(self, base_price: float, quantity: int) -> float:
        return self.strategy.calculate(base_price, quantity)

# Python-ic alternative: just pass a function
def calculate_order(base_price: float, quantity: int,
                    pricing_fn: Callable[[float, int], float]) -> float:
    return pricing_fn(base_price, quantity)

# --- Observer Pattern ---

class EventEmitter:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}

    def on(self, event: str, listener: Callable):
        self._listeners.setdefault(event, []).append(listener)
        return self

    def off(self, event: str, listener: Callable):
        if event in self._listeners:
            self._listeners[event] = [l for l in self._listeners[event] if l != listener]

    def emit(self, event: str, *args, **kwargs):
        for listener in self._listeners.get(event, []):
            listener(*args, **kwargs)

class OrderService:
    def __init__(self):
        self.events = EventEmitter()

    def create_order(self, order_data: dict):
        order = save_to_db(order_data)
        self.events.emit("order.created", order)
        return order

# Register handlers (decoupled)
order_service = OrderService()
order_service.events.on("order.created", send_confirmation_email)
order_service.events.on("order.created", update_inventory)
order_service.events.on("order.created", notify_warehouse)

# --- Chain of Responsibility ---

class Handler(ABC):
    def __init__(self):
        self._next: Optional[Handler] = None

    def set_next(self, handler: "Handler") -> "Handler":
        self._next = handler
        return handler

    def handle(self, request: dict) -> Optional[dict]:
        if self._next:
            return self._next.handle(request)
        return None

class AuthenticationHandler(Handler):
    def handle(self, request: dict) -> Optional[dict]:
        token = request.get("token")
        if not token:
            return {"error": "Authentication required", "status": 401}
        request["user"] = validate_token(token)
        return super().handle(request)

class AuthorizationHandler(Handler):
    def __init__(self, required_role: str):
        super().__init__()
        self.required_role = required_role

    def handle(self, request: dict) -> Optional[dict]:
        user = request.get("user")
        if user and user.role != self.required_role:
            return {"error": "Forbidden", "status": 403}
        return super().handle(request)

class RateLimitHandler(Handler):
    def handle(self, request: dict) -> Optional[dict]:
        user = request.get("user")
        if user and is_rate_limited(user.id):
            return {"error": "Too many requests", "status": 429}
        return super().handle(request)

class BusinessLogicHandler(Handler):
    def handle(self, request: dict) -> Optional[dict]:
        return process_request(request)

# Build chain:
chain = AuthenticationHandler()
chain.set_next(RateLimitHandler()).set_next(
    AuthorizationHandler("admin")).set_next(
    BusinessLogicHandler())

result = chain.handle({"token": "abc", "action": "delete_user"})

# --- State Machine ---

class OrderState(Enum):
    PENDING = auto()
    CONFIRMED = auto()
    PROCESSING = auto()
    SHIPPED = auto()
    DELIVERED = auto()
    CANCELLED = auto()

@dataclass
class StateMachine:
    state: OrderState
    transitions: dict[tuple[OrderState, str], OrderState] = field(default_factory=dict)
    callbacks: dict[str, list[Callable]] = field(default_factory=dict)

    def add_transition(self, from_state: OrderState, event: str,
                       to_state: OrderState):
        self.transitions[(from_state, event)] = to_state

    def on_transition(self, event: str, callback: Callable):
        self.callbacks.setdefault(event, []).append(callback)

    def trigger(self, event: str, **context) -> OrderState:
        key = (self.state, event)
        if key not in self.transitions:
            raise ValueError(
                f"Invalid transition: {self.state.name} + {event}"
            )
        old_state = self.state
        self.state = self.transitions[key]

        for cb in self.callbacks.get(event, []):
            cb(old_state=old_state, new_state=self.state, **context)

        return self.state

# Define order state machine
def create_order_state_machine() -> StateMachine:
    sm = StateMachine(state=OrderState.PENDING)
    sm.add_transition(OrderState.PENDING, "confirm", OrderState.CONFIRMED)
    sm.add_transition(OrderState.CONFIRMED, "process", OrderState.PROCESSING)
    sm.add_transition(OrderState.PROCESSING, "ship", OrderState.SHIPPED)
    sm.add_transition(OrderState.SHIPPED, "deliver", OrderState.DELIVERED)
    sm.add_transition(OrderState.PENDING, "cancel", OrderState.CANCELLED)
    sm.add_transition(OrderState.CONFIRMED, "cancel", OrderState.CANCELLED)
    return sm

sm = create_order_state_machine()
sm.trigger("confirm")   # PENDING → CONFIRMED
sm.trigger("process")   # CONFIRMED → PROCESSING
# sm.trigger("confirm") # ValueError: Invalid transition
```

Pattern selection:
- **Strategy** — swap algorithms at runtime (pricing, sorting, compression)
- **Observer** — decouple event producers from consumers
- **Chain of Responsibility** — sequential middleware/pipeline processing
- **Command** — encapsulate operations for undo/redo/queue
- **State Machine** — enforce valid state transitions'''
    ),
    (
        "patterns/repository-pattern",
        "Show the Repository pattern in Python: abstracting data access, unit of work, and testing with in-memory implementations.",
        '''Repository pattern for clean data access:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, TypeVar, Generic
from datetime import datetime, timezone

T = TypeVar("T")

# --- Domain entities ---

@dataclass
class User:
    id: str
    name: str
    email: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class Order:
    id: str
    user_id: str
    items: list[dict]
    total: float
    status: str = "pending"

# --- Repository interface ---

class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[User]: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]: ...

    @abstractmethod
    async def save(self, user: User) -> User: ...

    @abstractmethod
    async def delete(self, user_id: str) -> bool: ...

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> list[User]: ...

# --- PostgreSQL implementation ---

class PostgresUserRepository(UserRepository):
    def __init__(self, pool):
        self.pool = pool

    async def get_by_id(self, user_id: str) -> Optional[User]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1", user_id
            )
            return self._to_entity(row) if row else None

    async def get_by_email(self, email: str) -> Optional[User]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1", email
            )
            return self._to_entity(row) if row else None

    async def save(self, user: User) -> User:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (id, name, email, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (id)
                DO UPDATE SET name = $2, email = $3
            """, user.id, user.name, user.email, user.created_at)
        return user

    async def delete(self, user_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM users WHERE id = $1", user_id
            )
            return result == "DELETE 1"

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[User]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
            return [self._to_entity(row) for row in rows]

    def _to_entity(self, row) -> User:
        return User(id=row["id"], name=row["name"],
                    email=row["email"], created_at=row["created_at"])

# --- In-memory implementation (for testing) ---

class InMemoryUserRepository(UserRepository):
    def __init__(self):
        self.users: dict[str, User] = {}

    async def get_by_id(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    async def get_by_email(self, email: str) -> Optional[User]:
        return next((u for u in self.users.values() if u.email == email), None)

    async def save(self, user: User) -> User:
        self.users[user.id] = user
        return user

    async def delete(self, user_id: str) -> bool:
        return self.users.pop(user_id, None) is not None

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[User]:
        all_users = sorted(self.users.values(),
                           key=lambda u: u.created_at, reverse=True)
        return all_users[offset:offset + limit]

# --- Unit of Work ---

class UnitOfWork(ABC):
    users: UserRepository
    orders: "OrderRepository"

    @abstractmethod
    async def __aenter__(self): ...

    @abstractmethod
    async def __aexit__(self, *args): ...

    @abstractmethod
    async def commit(self): ...

    @abstractmethod
    async def rollback(self): ...

class PostgresUnitOfWork(UnitOfWork):
    def __init__(self, pool):
        self.pool = pool

    async def __aenter__(self):
        self.conn = await self.pool.acquire()
        self.tx = self.conn.transaction()
        await self.tx.start()
        self.users = PostgresUserRepository(self.pool)
        self.orders = PostgresOrderRepository(self.pool)
        return self

    async def __aexit__(self, exc_type, *args):
        if exc_type:
            await self.rollback()
        await self.pool.release(self.conn)

    async def commit(self):
        await self.tx.commit()

    async def rollback(self):
        await self.tx.rollback()

# --- Service layer uses repository interface ---

class UserService:
    def __init__(self, uow_factory):
        self.uow_factory = uow_factory

    async def create_user(self, name: str, email: str) -> User:
        async with self.uow_factory() as uow:
            existing = await uow.users.get_by_email(email)
            if existing:
                raise ValueError(f"Email {email} already registered")

            user = User(id=generate_id(), name=name, email=email)
            await uow.users.save(user)
            await uow.commit()
            return user

# --- Testing with in-memory repo ---

async def test_create_user():
    repo = InMemoryUserRepository()
    service = UserService(lambda: InMemoryUnitOfWork(repo))

    user = await service.create_user("Alice", "alice@test.com")
    assert user.name == "Alice"

    saved = await repo.get_by_email("alice@test.com")
    assert saved is not None
    assert saved.id == user.id
```

Benefits:
1. **Testability** — swap PostgreSQL for in-memory in tests
2. **Decoupling** — service layer doesn't know about SQL
3. **Single source of truth** — all data access through repository
4. **Unit of Work** — transactional consistency across repositories'''
    ),
]
