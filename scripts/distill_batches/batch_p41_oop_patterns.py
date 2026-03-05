"""OOP patterns — SOLID principles, composition, inheritance, and Python-specific OOP."""

PAIRS = [
    (
        "python/solid-principles",
        "Show SOLID principles in Python: single responsibility, open-closed, Liskov substitution, interface segregation, and dependency inversion.",
        '''SOLID principles with practical Python examples:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

# --- S: Single Responsibility ---

# BAD: One class does everything
class UserManager:
    def create_user(self, data): ...
    def send_welcome_email(self, user): ...
    def generate_report(self, users): ...
    def validate_password(self, password): ...

# GOOD: Each class has one responsibility
class UserService:
    def __init__(self, repo, validator, notifier):
        self.repo = repo
        self.validator = validator
        self.notifier = notifier

    def create_user(self, data):
        self.validator.validate(data)
        user = self.repo.save(User(**data))
        self.notifier.welcome(user)
        return user

class PasswordValidator:
    def validate(self, password: str) -> bool: ...

class EmailNotifier:
    def welcome(self, user) -> None: ...


# --- O: Open/Closed (open for extension, closed for modification) ---

# BAD: Modify existing code for each new format
class ReportGenerator:
    def generate(self, data, format):
        if format == "pdf":
            return self._generate_pdf(data)
        elif format == "csv":
            return self._generate_csv(data)
        # Must add elif for every new format...

# GOOD: Extend via new classes
class ReportFormatter(Protocol):
    def format(self, data: list[dict]) -> bytes: ...

class PDFFormatter:
    def format(self, data: list[dict]) -> bytes: ...

class CSVFormatter:
    def format(self, data: list[dict]) -> bytes: ...

class ExcelFormatter:  # New format = new class, no existing code changes
    def format(self, data: list[dict]) -> bytes: ...

class ReportGenerator:
    def generate(self, data: list[dict], formatter: ReportFormatter) -> bytes:
        return formatter.format(data)


# --- L: Liskov Substitution ---

# BAD: Subclass violates parent's contract
class Rectangle:
    def __init__(self, width, height):
        self.width = width
        self.height = height

    def area(self):
        return self.width * self.height

class Square(Rectangle):
    def __init__(self, side):
        super().__init__(side, side)

    @property
    def width(self):
        return self._side

    @width.setter
    def width(self, value):
        self._side = value
        # This breaks Rectangle's contract!
        # Setting width also changes height

# GOOD: Use composition or separate abstractions
class Shape(Protocol):
    def area(self) -> float: ...

@dataclass
class Rectangle:
    width: float
    height: float
    def area(self) -> float:
        return self.width * self.height

@dataclass
class Square:
    side: float
    def area(self) -> float:
        return self.side * self.side

def total_area(shapes: list[Shape]) -> float:
    return sum(s.area() for s in shapes)


# --- I: Interface Segregation ---

# BAD: Fat interface forces implementing unused methods
class Worker(ABC):
    @abstractmethod
    def work(self): ...
    @abstractmethod
    def eat(self): ...
    @abstractmethod
    def sleep(self): ...

class Robot(Worker):
    def work(self): ...
    def eat(self): raise NotImplementedError  # Robot doesn't eat!
    def sleep(self): raise NotImplementedError

# GOOD: Small, focused interfaces
class Workable(Protocol):
    def work(self) -> None: ...

class Feedable(Protocol):
    def eat(self) -> None: ...

class HumanWorker:
    def work(self): ...
    def eat(self): ...
    def sleep(self): ...

class RobotWorker:
    def work(self): ...
    # No eat or sleep needed


# --- D: Dependency Inversion ---

# BAD: High-level depends on low-level implementation
class OrderService:
    def __init__(self):
        self.db = PostgresDatabase()  # Concrete dependency
        self.emailer = SMTPEmailer()  # Concrete dependency

# GOOD: Depend on abstractions
class OrderRepository(Protocol):
    async def save(self, order) -> None: ...
    async def get_by_id(self, order_id: str) -> dict: ...

class NotificationService(Protocol):
    async def notify(self, user_id: str, message: str) -> None: ...

class OrderService:
    def __init__(self, repo: OrderRepository, notifier: NotificationService):
        self.repo = repo
        self.notifier = notifier

    async def create_order(self, data: dict):
        order = Order(**data)
        await self.repo.save(order)
        await self.notifier.notify(order.user_id, "Order created")
        return order

# Inject dependencies:
# service = OrderService(
#     repo=PostgresOrderRepo(db_pool),
#     notifier=EmailNotifier(smtp_client),
# )
# For tests:
# service = OrderService(
#     repo=InMemoryOrderRepo(),
#     notifier=MockNotifier(),
# )
```

Python-specific notes:
1. **Protocol** over ABC — structural subtyping, no inheritance required
2. **Composition over inheritance** — inject dependencies, don't inherit behavior
3. **Duck typing** — Python naturally supports interface segregation
4. **`dataclass` for value objects** — immutable data containers
5. **Simple DI** — constructor injection, no framework needed for most cases'''
    ),
    (
        "python/composition-patterns",
        "Show composition over inheritance patterns: mixins, delegation, strategy injection, and plugin systems in Python.",
        '''Composition patterns replacing deep inheritance:

```python
from typing import Protocol, Callable, Any
from dataclasses import dataclass, field
from functools import wraps

# --- Delegation pattern ---

class Logger:
    def log(self, message: str, level: str = "INFO"):
        print(f"[{level}] {message}")

class Metrics:
    def __init__(self):
        self._counters = {}

    def increment(self, name: str, value: int = 1):
        self._counters[name] = self._counters.get(name, 0) + value

class Cache:
    def __init__(self):
        self._store = {}

    def get(self, key: str) -> Any:
        return self._store.get(key)

    def set(self, key: str, value: Any, ttl: int = 300):
        self._store[key] = value

# Compose via delegation (not inheritance)
class UserService:
    def __init__(self, repo, logger: Logger, metrics: Metrics, cache: Cache):
        self.repo = repo
        self.logger = logger
        self.metrics = metrics
        self.cache = cache

    async def get_user(self, user_id: str):
        # Check cache
        cached = self.cache.get(f"user:{user_id}")
        if cached:
            self.metrics.increment("cache_hit")
            return cached

        self.metrics.increment("cache_miss")
        user = await self.repo.get_by_id(user_id)
        if user:
            self.cache.set(f"user:{user_id}", user)

        self.logger.log(f"Fetched user {user_id}")
        return user


# --- Strategy pattern with callables ---

# Instead of class hierarchy for strategies, use functions
def price_regular(base: float, qty: int) -> float:
    return base * qty

def price_bulk(base: float, qty: int) -> float:
    if qty >= 100: return base * qty * 0.7
    if qty >= 10: return base * qty * 0.9
    return base * qty

def price_subscription(monthly_rate: float):
    def calculate(base: float, qty: int) -> float:
        return monthly_rate
    return calculate

@dataclass
class Order:
    items: list
    pricing: Callable[[float, int], float] = price_regular

    @property
    def total(self) -> float:
        return sum(
            self.pricing(item["price"], item["qty"])
            for item in self.items
        )

# Usage:
order = Order(items=[{"price": 10, "qty": 50}], pricing=price_bulk)


# --- Plugin system ---

class PluginRegistry:
    """Register and discover plugins by type."""

    def __init__(self):
        self._plugins: dict[str, list] = {}

    def register(self, plugin_type: str):
        """Decorator to register a plugin."""
        def decorator(cls):
            self._plugins.setdefault(plugin_type, []).append(cls)
            return cls
        return decorator

    def get_plugins(self, plugin_type: str) -> list:
        return self._plugins.get(plugin_type, [])

    def create_all(self, plugin_type: str, **kwargs) -> list:
        return [cls(**kwargs) for cls in self.get_plugins(plugin_type)]

plugins = PluginRegistry()

# Register exporters
@plugins.register("exporter")
class JSONExporter:
    def export(self, data): return json.dumps(data)

@plugins.register("exporter")
class CSVExporter:
    def export(self, data): ...

@plugins.register("exporter")
class XMLExporter:
    def export(self, data): ...

# Use all registered exporters
for exporter in plugins.create_all("exporter"):
    output = exporter.export(data)


# --- Decorator pattern (wrapping behavior) ---

class Middleware(Protocol):
    async def __call__(self, request: dict, next_fn: Callable) -> dict: ...

class Pipeline:
    """Composable middleware pipeline."""

    def __init__(self, handler: Callable):
        self.handler = handler
        self.middlewares: list[Middleware] = []

    def use(self, middleware: Middleware) -> "Pipeline":
        self.middlewares.append(middleware)
        return self

    async def execute(self, request: dict) -> dict:
        async def dispatch(index: int, req: dict) -> dict:
            if index >= len(self.middlewares):
                return await self.handler(req)
            middleware = self.middlewares[index]
            return await middleware(req, lambda r: dispatch(index + 1, r))
        return await dispatch(0, request)

# Middlewares
async def logging_middleware(request, next_fn):
    print(f"Request: {request}")
    response = await next_fn(request)
    print(f"Response: {response}")
    return response

async def auth_middleware(request, next_fn):
    if "token" not in request:
        return {"error": "Unauthorized", "status": 401}
    return await next_fn(request)

# Build pipeline
pipeline = (Pipeline(handler=process_request)
    .use(logging_middleware)
    .use(auth_middleware))

result = await pipeline.execute({"token": "abc", "action": "list"})
```

Composition advantages:
1. **Flexible** — swap components at runtime (strategies, plugins)
2. **Testable** — inject mocks for any component
3. **Avoids diamond problem** — no multiple inheritance issues
4. **Single responsibility** — each component does one thing
5. **Plugin systems** — extend without modifying core code'''
    ),
]
