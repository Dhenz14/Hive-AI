"""Design patterns — dependency injection, observer, strategy, and repository patterns."""

PAIRS = [
    (
        "patterns/dependency-injection",
        "Show dependency injection patterns: constructor injection, DI containers, and testing with DI.",
        '''Dependency injection patterns:

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass, field
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


# --- Define interfaces (protocols) ---

@runtime_checkable
class EmailSender(Protocol):
    async def send(self, to: str, subject: str, body: str) -> bool: ...

@runtime_checkable
class UserRepository(Protocol):
    async def get(self, user_id: str) -> dict | None: ...
    async def save(self, user: dict) -> None: ...
    async def delete(self, user_id: str) -> None: ...

class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, hash: str) -> bool: ...


# --- Service with constructor injection ---

class UserService:
    """Service with all dependencies injected via constructor."""

    def __init__(
        self,
        repo: UserRepository,
        email: EmailSender,
        hasher: PasswordHasher,
    ):
        self.repo = repo
        self.email = email
        self.hasher = hasher

    async def register(self, email_addr: str, password: str) -> dict:
        # All dependencies are injected — easy to test
        password_hash = self.hasher.hash(password)
        user = {"email": email_addr, "password_hash": password_hash}
        await self.repo.save(user)
        await self.email.send(email_addr, "Welcome!", "Thanks for signing up")
        return user

    async def authenticate(self, email_addr: str, password: str) -> dict | None:
        user = await self.repo.get_by_email(email_addr)
        if user and self.hasher.verify(password, user["password_hash"]):
            return user
        return None


# --- Simple DI container ---

class Container:
    """Lightweight dependency injection container."""

    def __init__(self):
        self._factories: dict[type, callable] = {}
        self._singletons: dict[type, object] = {}
        self._singleton_types: set[type] = set()

    def register(self, interface: type, factory: callable,
                 singleton: bool = False):
        self._factories[interface] = factory
        if singleton:
            self._singleton_types.add(interface)

    def resolve(self, interface: type):
        """Resolve a dependency."""
        if interface in self._singletons:
            return self._singletons[interface]

        factory = self._factories.get(interface)
        if not factory:
            raise KeyError(f"No registration for {interface}")

        instance = factory(self)

        if interface in self._singleton_types:
            self._singletons[interface] = instance

        return instance


# --- Wire up dependencies ---

def create_container(config: dict) -> Container:
    container = Container()

    # Register implementations
    container.register(
        UserRepository,
        lambda c: PostgresUserRepo(config["database_url"]),
        singleton=True,
    )
    container.register(
        EmailSender,
        lambda c: SMTPEmailSender(config["smtp_host"]),
        singleton=True,
    )
    container.register(
        PasswordHasher,
        lambda c: BcryptHasher(),
        singleton=True,
    )
    container.register(
        UserService,
        lambda c: UserService(
            repo=c.resolve(UserRepository),
            email=c.resolve(EmailSender),
            hasher=c.resolve(PasswordHasher),
        ),
    )

    return container


# --- FastAPI integration ---

from fastapi import FastAPI, Depends

app = FastAPI()
container = create_container({"database_url": "...", "smtp_host": "..."})


def get_user_service() -> UserService:
    return container.resolve(UserService)


@app.post("/register")
async def register(
    email: str,
    password: str,
    service: UserService = Depends(get_user_service),
):
    return await service.register(email, password)


# --- Testing with mock implementations ---

class FakeUserRepo:
    def __init__(self):
        self.users = {}

    async def get(self, user_id):
        return self.users.get(user_id)

    async def save(self, user):
        self.users[user.get("email")] = user

    async def delete(self, user_id):
        self.users.pop(user_id, None)


class FakeEmailSender:
    def __init__(self):
        self.sent = []

    async def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject})
        return True


# In tests:
# repo = FakeUserRepo()
# email = FakeEmailSender()
# service = UserService(repo=repo, email=email, hasher=BcryptHasher())
# await service.register("test@example.com", "password123")
# assert len(email.sent) == 1
```

DI patterns:
1. **Constructor injection** — pass dependencies via `__init__`, never import directly
2. **Protocol interfaces** — define contracts, swap implementations freely
3. **DI container** — centralized registration, automatic resolution
4. **Singleton scope** — share one instance per dependency type
5. **Fake implementations** — in-memory mocks for fast, isolated tests'''
    ),
    (
        "patterns/observer-strategy",
        "Show observer and strategy patterns: event systems, pluggable algorithms, and composition.",
        '''Observer and strategy patterns:

```python
from typing import Callable, Any, Protocol
from dataclasses import dataclass, field
from collections import defaultdict
import asyncio
import logging

logger = logging.getLogger(__name__)


# --- Observer pattern (event bus) ---

class EventBus:
    """Publish-subscribe event bus."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._async_handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, handler: Callable):
        """Subscribe to an event."""
        if asyncio.iscoroutinefunction(handler):
            self._async_handlers[event].append(handler)
        else:
            self._handlers[event].append(handler)
        return lambda: self.off(event, handler)  # Return unsubscribe function

    def off(self, event: str, handler: Callable):
        """Unsubscribe from an event."""
        self._handlers[event] = [h for h in self._handlers[event] if h != handler]
        self._async_handlers[event] = [
            h for h in self._async_handlers[event] if h != handler
        ]

    async def emit(self, event: str, **data):
        """Emit event to all subscribers."""
        # Sync handlers
        for handler in self._handlers.get(event, []):
            try:
                handler(**data)
            except Exception as e:
                logger.error("Handler error for %s: %s", event, e)

        # Async handlers (concurrent)
        async_handlers = self._async_handlers.get(event, [])
        if async_handlers:
            await asyncio.gather(
                *(h(**data) for h in async_handlers),
                return_exceptions=True,
            )

    def once(self, event: str, handler: Callable):
        """Subscribe to event, auto-unsubscribe after first call."""
        def wrapper(**data):
            self.off(event, wrapper)
            return handler(**data)
        self.on(event, wrapper)


# Usage:
# bus = EventBus()
#
# async def on_user_created(user_id: str, email: str, **_):
#     await send_welcome_email(email)
#
# def on_user_created_log(user_id: str, **_):
#     logger.info("User created: %s", user_id)
#
# bus.on("user.created", on_user_created)
# bus.on("user.created", on_user_created_log)
# await bus.emit("user.created", user_id="123", email="alice@example.com")


# --- Strategy pattern ---

class PricingStrategy(Protocol):
    """Pluggable pricing algorithm."""
    def calculate(self, base_price: float, quantity: int,
                  customer_type: str) -> float: ...


class StandardPricing:
    def calculate(self, base_price: float, quantity: int,
                  customer_type: str) -> float:
        return base_price * quantity


class BulkDiscountPricing:
    """10% off for 10+, 20% off for 100+."""
    def calculate(self, base_price: float, quantity: int,
                  customer_type: str) -> float:
        total = base_price * quantity
        if quantity >= 100:
            return total * 0.80
        elif quantity >= 10:
            return total * 0.90
        return total


class TieredPricing:
    """Different rates per tier."""
    TIERS = [
        (10, 1.0),    # First 10: full price
        (50, 0.9),    # 11-50: 10% off
        (100, 0.8),   # 51-100: 20% off
        (float('inf'), 0.7),  # 100+: 30% off
    ]

    def calculate(self, base_price: float, quantity: int,
                  customer_type: str) -> float:
        total = 0
        remaining = quantity
        prev_limit = 0

        for limit, rate in self.TIERS:
            tier_qty = min(remaining, limit - prev_limit)
            total += base_price * tier_qty * rate
            remaining -= tier_qty
            prev_limit = limit
            if remaining <= 0:
                break

        return total


class LoyaltyPricing:
    """Additional discount based on customer type."""
    DISCOUNTS = {"gold": 0.15, "silver": 0.10, "bronze": 0.05}

    def __init__(self, base_strategy: PricingStrategy):
        self.base_strategy = base_strategy

    def calculate(self, base_price: float, quantity: int,
                  customer_type: str) -> float:
        base_total = self.base_strategy.calculate(
            base_price, quantity, customer_type,
        )
        discount = self.DISCOUNTS.get(customer_type, 0)
        return base_total * (1 - discount)


# --- Order service using strategy ---

class OrderService:
    def __init__(self, pricing: PricingStrategy):
        self.pricing = pricing

    def calculate_total(self, items: list[dict],
                       customer_type: str = "standard") -> float:
        total = 0
        for item in items:
            total += self.pricing.calculate(
                item["price"], item["quantity"], customer_type,
            )
        return round(total, 2)


# Swap strategies at runtime:
# standard = OrderService(StandardPricing())
# bulk = OrderService(BulkDiscountPricing())
# loyalty = OrderService(LoyaltyPricing(BulkDiscountPricing()))
#
# price = loyalty.calculate_total(
#     [{"price": 10.0, "quantity": 50}],
#     customer_type="gold",
# )


# --- Strategy registry ---

PRICING_STRATEGIES: dict[str, type[PricingStrategy]] = {
    "standard": StandardPricing,
    "bulk": BulkDiscountPricing,
    "tiered": TieredPricing,
}

def get_pricing(name: str) -> PricingStrategy:
    cls = PRICING_STRATEGIES.get(name)
    if not cls:
        raise ValueError(f"Unknown pricing strategy: {name}")
    return cls()
```

Design patterns:
1. **Event bus** — decouple emitters from handlers via pub/sub
2. **`once()`** — auto-unsubscribe after first event (one-shot handler)
3. **Strategy protocol** — pluggable algorithms via interface + composition
4. **Decorator strategy** — `LoyaltyPricing` wraps another strategy (composition)
5. **Strategy registry** — map names to strategies for config-driven selection'''
    ),
    (
        "patterns/repository-uow",
        "Show repository and unit of work patterns: data access abstraction and transactional boundaries.",
        '''Repository and Unit of Work patterns:

```python
from typing import Protocol, TypeVar, Generic
from dataclasses import dataclass
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)
T = TypeVar("T")


# --- Generic repository interface ---

class Repository(Protocol[T]):
    async def get(self, id: str) -> T | None: ...
    async def get_all(self, **filters) -> list[T]: ...
    async def add(self, entity: T) -> T: ...
    async def update(self, entity: T) -> T: ...
    async def delete(self, id: str) -> None: ...


# --- Domain models ---

@dataclass
class User:
    id: str
    name: str
    email: str


@dataclass
class Order:
    id: str
    user_id: str
    total: float
    status: str = "pending"


# --- SQLAlchemy repository ---

class SQLUserRepository:
    """Concrete repository using SQLAlchemy session."""

    def __init__(self, session):
        self.session = session

    async def get(self, user_id: str) -> User | None:
        result = await self.session.execute(
            "SELECT * FROM users WHERE id = :id",
            {"id": user_id},
        )
        row = result.fetchone()
        return User(**dict(row)) if row else None

    async def get_all(self, **filters) -> list[User]:
        query = "SELECT * FROM users"
        conditions = []
        params = {}

        for key, value in filters.items():
            conditions.append(f"{key} = :{key}")
            params[key] = value

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        result = await self.session.execute(query, params)
        return [User(**dict(row)) for row in result.fetchall()]

    async def add(self, user: User) -> User:
        await self.session.execute(
            "INSERT INTO users (id, name, email) VALUES (:id, :name, :email)",
            {"id": user.id, "name": user.name, "email": user.email},
        )
        return user

    async def update(self, user: User) -> User:
        await self.session.execute(
            "UPDATE users SET name = :name, email = :email WHERE id = :id",
            {"id": user.id, "name": user.name, "email": user.email},
        )
        return user

    async def delete(self, user_id: str) -> None:
        await self.session.execute(
            "DELETE FROM users WHERE id = :id",
            {"id": user_id},
        )


# --- Unit of Work ---

class UnitOfWork:
    """Manage transactional boundaries across repositories."""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    @asynccontextmanager
    async def __call__(self):
        session = self.session_factory()
        uow = UnitOfWorkContext(session)
        try:
            yield uow
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class UnitOfWorkContext:
    """Provides access to repositories within a transaction."""

    def __init__(self, session):
        self.session = session
        self._users: SQLUserRepository | None = None
        self._orders: SQLOrderRepository | None = None

    @property
    def users(self) -> SQLUserRepository:
        if self._users is None:
            self._users = SQLUserRepository(self.session)
        return self._users

    @property
    def orders(self) -> SQLOrderRepository:
        if self._orders is None:
            self._orders = SQLOrderRepository(self.session)
        return self._orders


# --- Application service using UoW ---

class OrderPlacementService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def place_order(self, user_id: str, items: list[dict]) -> Order:
        """Place order — user lookup and order creation in one transaction."""
        async with self.uow() as ctx:
            # Both operations share the same transaction
            user = await ctx.users.get(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")

            total = sum(item["price"] * item["qty"] for item in items)
            order = Order(
                id=generate_id(),
                user_id=user_id,
                total=total,
            )
            await ctx.orders.add(order)

            return order
        # Auto-commit on success, rollback on error


# --- In-memory repository for testing ---

class InMemoryUserRepository:
    def __init__(self):
        self._store: dict[str, User] = {}

    async def get(self, user_id: str) -> User | None:
        return self._store.get(user_id)

    async def get_all(self, **filters) -> list[User]:
        users = list(self._store.values())
        for key, value in filters.items():
            users = [u for u in users if getattr(u, key, None) == value]
        return users

    async def add(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def update(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def delete(self, user_id: str) -> None:
        self._store.pop(user_id, None)
```

Repository + UoW patterns:
1. **Repository interface** — abstract data access behind Protocol
2. **Unit of Work** — single transaction spans multiple repository operations
3. **Context manager** — auto-commit on success, rollback on exception
4. **Lazy repositories** — created on first access within UoW context
5. **In-memory repo** — swap SQL for dict-based store in tests (no DB needed)'''
    ),
]
"""
