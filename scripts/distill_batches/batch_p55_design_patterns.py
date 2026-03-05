"""Design patterns — GoF patterns in modern Python, refactoring, and anti-patterns."""

PAIRS = [
    (
        "patterns/behavioral",
        "Show behavioral design patterns in Python: strategy, observer, command, chain of responsibility, and state.",
        '''Behavioral design patterns in modern Python:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Any, Protocol
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


# --- Strategy (using callables) ---

# Instead of class hierarchy, use functions:
PricingStrategy = Callable[[float, dict], float]

def regular_pricing(base_price: float, context: dict) -> float:
    return base_price

def member_pricing(base_price: float, context: dict) -> float:
    return base_price * 0.9  # 10% discount

def bulk_pricing(base_price: float, context: dict) -> float:
    qty = context.get("quantity", 1)
    if qty >= 100:
        return base_price * 0.7
    elif qty >= 10:
        return base_price * 0.85
    return base_price

class PriceCalculator:
    def __init__(self, strategy: PricingStrategy = regular_pricing):
        self.strategy = strategy

    def calculate(self, base_price: float, **context) -> float:
        return self.strategy(base_price, context)

# calc = PriceCalculator(bulk_pricing)
# calc.calculate(100, quantity=50)  # 85.0


# --- Observer (event system) ---

class EventBus:
    """Type-safe event bus."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, handler: Callable) -> Callable:
        """Register handler. Returns unsubscribe function."""
        self._handlers[event].append(handler)
        return lambda: self._handlers[event].remove(handler)

    def emit(self, event: str, **data):
        for handler in self._handlers.get(event, []):
            try:
                handler(**data)
            except Exception as e:
                logger.error("Handler error for %s: %s", event, e)

    def once(self, event: str, handler: Callable):
        def wrapper(**data):
            handler(**data)
            self._handlers[event].remove(wrapper)
        self._handlers[event].append(wrapper)

bus = EventBus()
bus.on("order.created", lambda order_id, **_: print(f"Order {order_id}"))
bus.on("order.created", lambda order_id, **_: send_email(order_id))
bus.emit("order.created", order_id="123", total=99.99)


# --- Command (undo/redo) ---

class Command(Protocol):
    def execute(self) -> None: ...
    def undo(self) -> None: ...

@dataclass
class AddItemCommand:
    cart: list
    item: Any

    def execute(self):
        self.cart.append(self.item)

    def undo(self):
        self.cart.remove(self.item)

@dataclass
class RemoveItemCommand:
    cart: list
    item: Any
    _index: int = -1

    def execute(self):
        self._index = self.cart.index(self.item)
        self.cart.remove(self.item)

    def undo(self):
        self.cart.insert(self._index, self.item)

class CommandHistory:
    def __init__(self):
        self._history: list[Command] = []
        self._redo_stack: list[Command] = []

    def execute(self, command: Command):
        command.execute()
        self._history.append(command)
        self._redo_stack.clear()

    def undo(self):
        if self._history:
            cmd = self._history.pop()
            cmd.undo()
            self._redo_stack.append(cmd)

    def redo(self):
        if self._redo_stack:
            cmd = self._redo_stack.pop()
            cmd.execute()
            self._history.append(cmd)


# --- Chain of Responsibility ---

class Handler(Protocol):
    def handle(self, request: dict) -> dict | None: ...

def auth_handler(request: dict) -> dict | None:
    if not request.get("token"):
        return {"status": 401, "error": "Unauthorized"}
    return None  # Pass to next handler

def rate_limit_handler(request: dict) -> dict | None:
    if is_rate_limited(request.get("ip")):
        return {"status": 429, "error": "Rate limited"}
    return None

def validation_handler(request: dict) -> dict | None:
    if not request.get("body"):
        return {"status": 400, "error": "Empty body"}
    return None

def process_handler(request: dict) -> dict | None:
    return {"status": 200, "data": process(request["body"])}

def chain(*handlers: Callable) -> Callable:
    """Chain handlers: first non-None response wins."""
    def handle(request: dict) -> dict:
        for handler in handlers:
            result = handler(request)
            if result is not None:
                return result
        return {"status": 500, "error": "No handler"}
    return handle

pipeline = chain(auth_handler, rate_limit_handler,
                 validation_handler, process_handler)


# --- State machine ---

from enum import Enum, auto

class OrderState(Enum):
    DRAFT = auto()
    PENDING = auto()
    PAID = auto()
    SHIPPED = auto()
    DELIVERED = auto()
    CANCELLED = auto()

class OrderStateMachine:
    TRANSITIONS = {
        OrderState.DRAFT: [OrderState.PENDING, OrderState.CANCELLED],
        OrderState.PENDING: [OrderState.PAID, OrderState.CANCELLED],
        OrderState.PAID: [OrderState.SHIPPED, OrderState.CANCELLED],
        OrderState.SHIPPED: [OrderState.DELIVERED],
        OrderState.DELIVERED: [],
        OrderState.CANCELLED: [],
    }

    def __init__(self, initial: OrderState = OrderState.DRAFT):
        self.state = initial
        self._on_enter: dict[OrderState, list[Callable]] = defaultdict(list)

    def can_transition(self, target: OrderState) -> bool:
        return target in self.TRANSITIONS.get(self.state, [])

    def transition(self, target: OrderState):
        if not self.can_transition(target):
            raise ValueError(
                f"Cannot transition from {self.state} to {target}"
            )
        self.state = target
        for callback in self._on_enter.get(target, []):
            callback()

    def on_enter(self, state: OrderState, callback: Callable):
        self._on_enter[state].append(callback)
```

Behavioral patterns:
1. **Strategy** — use callables instead of class hierarchies (Pythonic)
2. **Observer/EventBus** — decouple producers from consumers
3. **Command** — encapsulate actions for undo/redo support
4. **Chain of Responsibility** — compose handler pipeline (middleware)
5. **State machine** — enforce valid transitions with explicit allowed states'''
    ),
    (
        "patterns/structural",
        "Show structural patterns in Python: adapter, facade, proxy, decorator, and repository.",
        '''Structural design patterns:

```python
from typing import Protocol, Any
from functools import wraps
import time
import logging

logger = logging.getLogger(__name__)


# --- Adapter (make incompatible interfaces work together) ---

class OldPaymentGateway:
    """Legacy API we can't change."""
    def make_payment(self, card_number: str, amount_cents: int,
                     currency_code: str) -> dict:
        return {"transaction_id": "txn_123", "success": True}

class PaymentProvider(Protocol):
    """Our standardized interface."""
    async def charge(self, amount: float, currency: str,
                     payment_method: dict) -> str: ...

class LegacyPaymentAdapter:
    """Adapt old API to our interface."""

    def __init__(self, gateway: OldPaymentGateway):
        self._gateway = gateway

    async def charge(self, amount: float, currency: str,
                     payment_method: dict) -> str:
        result = self._gateway.make_payment(
            card_number=payment_method["card_number"],
            amount_cents=int(amount * 100),
            currency_code=currency.upper(),
        )
        if not result["success"]:
            raise PaymentError("Payment failed")
        return result["transaction_id"]


# --- Facade (simplify complex subsystem) ---

class OrderFacade:
    """Simple interface for complex order processing."""

    def __init__(self, inventory, payment, shipping, notification):
        self._inventory = inventory
        self._payment = payment
        self._shipping = shipping
        self._notification = notification

    async def place_order(self, user_id: str,
                          items: list[dict], address: dict) -> str:
        """One method hides 4 subsystem interactions."""
        # 1. Check inventory
        for item in items:
            if not await self._inventory.check(item["product_id"], item["qty"]):
                raise OutOfStockError(item["product_id"])

        # 2. Calculate and charge
        total = await self._inventory.calculate_total(items)
        payment_id = await self._payment.charge(user_id, total)

        # 3. Reserve inventory and create shipment
        await self._inventory.reserve(items)
        tracking = await self._shipping.create(address, items)

        # 4. Notify user
        await self._notification.send(user_id, "order_placed", {
            "payment_id": payment_id,
            "tracking": tracking,
        })

        return payment_id


# --- Proxy (add behavior around an object) ---

class CachingProxy:
    """Cache results of expensive operations."""

    def __init__(self, service, cache, ttl: int = 300):
        self._service = service
        self._cache = cache
        self._ttl = ttl

    async def get(self, key: str) -> Any:
        cached = await self._cache.get(key)
        if cached is not None:
            return cached
        result = await self._service.get(key)
        await self._cache.set(key, result, ttl=self._ttl)
        return result

class LoggingProxy:
    """Log all method calls."""

    def __init__(self, target):
        self._target = target

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if callable(attr):
            @wraps(attr)
            async def logged(*args, **kwargs):
                logger.info("Calling %s.%s", type(self._target).__name__, name)
                start = time.perf_counter()
                result = await attr(*args, **kwargs)
                elapsed = time.perf_counter() - start
                logger.info("%s.%s took %.3fs", type(self._target).__name__,
                           name, elapsed)
                return result
            return logged
        return attr

class CircuitBreakerProxy:
    """Stop calling failing service temporarily."""

    def __init__(self, service, failure_threshold: int = 5,
                 reset_timeout: float = 60):
        self._service = service
        self._failures = 0
        self._threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._last_failure = 0
        self._state = "closed"  # closed, open, half-open

    async def call(self, method: str, *args, **kwargs):
        if self._state == "open":
            if time.time() - self._last_failure > self._reset_timeout:
                self._state = "half-open"
            else:
                raise ServiceUnavailable("Circuit breaker is open")

        try:
            result = await getattr(self._service, method)(*args, **kwargs)
            if self._state == "half-open":
                self._state = "closed"
                self._failures = 0
            return result
        except Exception as e:
            self._failures += 1
            self._last_failure = time.time()
            if self._failures >= self._threshold:
                self._state = "open"
                logger.error("Circuit breaker opened for %s",
                           type(self._service).__name__)
            raise


# --- Repository (abstract data access) ---

class UserRepository(Protocol):
    async def find_by_id(self, id: str) -> User | None: ...
    async def find_by_email(self, email: str) -> User | None: ...
    async def save(self, user: User) -> None: ...
    async def delete(self, id: str) -> None: ...

class PostgresUserRepository:
    def __init__(self, pool):
        self.pool = pool

    async def find_by_id(self, id: str) -> User | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1", id
            )
            return User(**row) if row else None

    async def save(self, user: User) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (id, email, name) VALUES ($1, $2, $3) "
                "ON CONFLICT (id) DO UPDATE SET email=$2, name=$3",
                user.id, user.email, user.name,
            )

class InMemoryUserRepository:
    """For testing."""
    def __init__(self):
        self._users: dict[str, User] = {}

    async def find_by_id(self, id: str) -> User | None:
        return self._users.get(id)

    async def save(self, user: User) -> None:
        self._users[user.id] = user
```

Structural patterns:
1. **Adapter** — wrap incompatible interfaces to match your protocol
2. **Facade** — single entry point for complex multi-service operations
3. **Proxy** — add caching, logging, circuit breaking transparently
4. **Repository** — abstract data access behind Protocol interface
5. **Circuit breaker** — stop calling failing services to prevent cascading failures'''
    ),
]
"""
