"""Advanced Python — generators, metaclasses, descriptors, and context managers."""

PAIRS = [
    (
        "python/generators-advanced",
        "Show advanced generator patterns: pipelines, coroutines, send/throw, and generator-based state machines.",
        '''Advanced generator patterns:

```python
from typing import Generator, Iterator, Any
import os


# --- Generator pipeline (Unix pipes style) ---

def read_lines(filepath: str) -> Iterator[str]:
    """Source: read file line by line (lazy)."""
    with open(filepath) as f:
        for line in f:
            yield line.rstrip('\n')

def grep(pattern: str, lines: Iterator[str]) -> Iterator[str]:
    """Filter lines matching pattern."""
    import re
    compiled = re.compile(pattern)
    for line in lines:
        if compiled.search(line):
            yield line

def field(index: int, lines: Iterator[str],
          sep: str = ',') -> Iterator[str]:
    """Extract field by index."""
    for line in lines:
        parts = line.split(sep)
        if index < len(parts):
            yield parts[index]

def unique(items: Iterator[str]) -> Iterator[str]:
    """Deduplicate while preserving order."""
    seen = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            yield item

# Pipeline: unique emails from CSV error logs
# emails = unique(field(2, grep("ERROR", read_lines("app.log"))))
# for email in emails:
#     print(email)


# --- Generator with send() for coroutine ---

def running_average() -> Generator[float, float, None]:
    """Compute running average, accepting values via send()."""
    total = 0.0
    count = 0
    average = 0.0
    while True:
        value = yield average
        total += value
        count += 1
        average = total / count

# Usage:
# avg = running_average()
# next(avg)          # Prime the generator
# avg.send(10)       # 10.0
# avg.send(20)       # 15.0
# avg.send(30)       # 20.0


# --- Generator-based state machine ---

def tcp_connection() -> Generator[str, str, None]:
    """Simple TCP state machine using generators."""
    while True:
        # CLOSED state
        event = yield "CLOSED"
        if event == "connect":
            # SYN_SENT state
            event = yield "SYN_SENT"
            if event == "syn_ack":
                # ESTABLISHED state
                while True:
                    event = yield "ESTABLISHED"
                    if event == "close":
                        # FIN_WAIT state
                        event = yield "FIN_WAIT"
                        if event == "ack":
                            break
                        continue
                    elif event == "reset":
                        break

# Usage:
# conn = tcp_connection()
# next(conn)                  # "CLOSED"
# conn.send("connect")       # "SYN_SENT"
# conn.send("syn_ack")       # "ESTABLISHED"
# conn.send("close")         # "FIN_WAIT"
# conn.send("ack")           # "CLOSED"


# --- Delegating generators (yield from) ---

def flatten(nested) -> Iterator:
    """Recursively flatten nested iterables."""
    for item in nested:
        if hasattr(item, '__iter__') and not isinstance(item, (str, bytes)):
            yield from flatten(item)
        else:
            yield item

# list(flatten([1, [2, 3], [4, [5, 6]], 7]))  # [1, 2, 3, 4, 5, 6, 7]


def chain_files(*filepaths: str) -> Iterator[str]:
    """Chain multiple files as one stream."""
    for filepath in filepaths:
        yield from read_lines(filepath)


# --- Context manager as generator ---

from contextlib import contextmanager
import time

@contextmanager
def timer(name: str = ""):
    """Time a block of code."""
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"{name}: {elapsed:.4f}s")

@contextmanager
def temp_env(**kwargs):
    """Temporarily set environment variables."""
    old_values = {}
    for key, value in kwargs.items():
        old_values[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

@contextmanager
def transaction(connection):
    """Database transaction with auto-rollback."""
    cursor = connection.cursor()
    try:
        yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


# --- Infinite generators ---

def fibonacci() -> Iterator[int]:
    a, b = 0, 1
    while True:
        yield a
        a, b = b, a + b

def cycle(items: list) -> Iterator:
    while True:
        yield from items

def exponential_backoff(base: float = 1.0, factor: float = 2.0,
                        max_delay: float = 60.0) -> Iterator[float]:
    delay = base
    while True:
        yield min(delay, max_delay)
        delay *= factor

# Usage with itertools:
# from itertools import islice
# first_10_fibs = list(islice(fibonacci(), 10))
# delays = list(islice(exponential_backoff(), 5))  # [1.0, 2.0, 4.0, 8.0, 16.0]
```

Generator patterns:
1. **Pipelines** — compose generators for lazy data processing (no intermediate lists)
2. **`send()`** — two-way communication for stateful processing
3. **State machines** — `yield` at each state, `send()` events
4. **`yield from`** — delegate to sub-generators transparently
5. **`@contextmanager`** — write context managers as generators'''
    ),
    (
        "python/metaclasses-descriptors",
        "Show Python metaclasses and descriptors: custom class creation, attribute control, and validation.",
        '''Metaclasses and descriptors for advanced class customization:

```python
from typing import Any, Callable, Optional


# --- Descriptors (control attribute access) ---

class Validated:
    """Descriptor that validates on set."""

    def __init__(self, validator: Callable, error_msg: str = ""):
        self.validator = validator
        self.error_msg = error_msg

    def __set_name__(self, owner, name):
        self.name = name
        self.storage_name = f"_validated_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return getattr(obj, self.storage_name, None)

    def __set__(self, obj, value):
        if not self.validator(value):
            raise ValueError(
                self.error_msg or f"Invalid value for {self.name}: {value}"
            )
        setattr(obj, self.storage_name, value)


class TypeChecked:
    """Descriptor that enforces type at runtime."""

    def __init__(self, expected_type: type):
        self.expected_type = expected_type

    def __set_name__(self, owner, name):
        self.name = name
        self.storage_name = f"_typed_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return getattr(obj, self.storage_name, None)

    def __set__(self, obj, value):
        if not isinstance(value, self.expected_type):
            raise TypeError(
                f"{self.name} must be {self.expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        setattr(obj, self.storage_name, value)


class Bounded:
    """Numeric value within bounds."""

    def __init__(self, min_val: float = float('-inf'),
                 max_val: float = float('inf')):
        self.min_val = min_val
        self.max_val = max_val

    def __set_name__(self, owner, name):
        self.name = name
        self.storage_name = f"_bounded_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return getattr(obj, self.storage_name, None)

    def __set__(self, obj, value):
        if not self.min_val <= value <= self.max_val:
            raise ValueError(
                f"{self.name} must be between {self.min_val} and {self.max_val}"
            )
        setattr(obj, self.storage_name, value)


# Usage with descriptors:
class Product:
    name = TypeChecked(str)
    price = Bounded(min_val=0, max_val=99999.99)
    quantity = Bounded(min_val=0, max_val=1000000)
    sku = Validated(
        lambda x: len(x) >= 3 and x.isalnum(),
        "SKU must be at least 3 alphanumeric characters",
    )

    def __init__(self, name: str, price: float, quantity: int, sku: str):
        self.name = name
        self.price = price
        self.quantity = quantity
        self.sku = sku


# --- Metaclass: auto-register subclasses ---

class PluginRegistry(type):
    """Metaclass that auto-registers all subclasses."""

    _registry: dict[str, type] = {}

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        if bases:  # Don't register the base class itself
            mcs._registry[name] = cls
        return cls

    @classmethod
    def get_plugin(mcs, name: str) -> Optional[type]:
        return mcs._registry.get(name)

    @classmethod
    def all_plugins(mcs) -> dict[str, type]:
        return dict(mcs._registry)


class Plugin(metaclass=PluginRegistry):
    """Base class for plugins."""
    def execute(self, data: Any) -> Any:
        raise NotImplementedError

class JSONPlugin(Plugin):
    def execute(self, data):
        import json
        return json.dumps(data)

class CSVPlugin(Plugin):
    def execute(self, data):
        return ",".join(str(x) for x in data)

# PluginRegistry.all_plugins()  # {'JSONPlugin': <class>, 'CSVPlugin': <class>}
# PluginRegistry.get_plugin("JSONPlugin")()  # Instantiate by name


# --- Metaclass: enforce interface ---

class InterfaceMeta(type):
    """Ensure subclasses implement required methods."""

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)

        if bases:  # Not the base class
            required = getattr(cls, '_required_methods', [])
            for method_name in required:
                if method_name not in namespace:
                    raise TypeError(
                        f"{name} must implement {method_name}()"
                    )
        return cls


class Serializer(metaclass=InterfaceMeta):
    _required_methods = ['serialize', 'deserialize']

    def serialize(self, data: Any) -> bytes: ...
    def deserialize(self, data: bytes) -> Any: ...


# class BadSerializer(Serializer):
#     def serialize(self, data): return b""
#     # TypeError: BadSerializer must implement deserialize()


# --- __init_subclass__ (simpler than metaclass) ---

class EventHandler:
    _handlers: dict[str, type] = {}

    def __init_subclass__(cls, event_type: str = "", **kwargs):
        super().__init_subclass__(**kwargs)
        if event_type:
            EventHandler._handlers[event_type] = cls

    @classmethod
    def for_event(cls, event_type: str) -> Optional[type]:
        return cls._handlers.get(event_type)

class OrderCreatedHandler(EventHandler, event_type="order.created"):
    def handle(self, event):
        print(f"Order created: {event}")

class UserSignupHandler(EventHandler, event_type="user.signup"):
    def handle(self, event):
        print(f"User signed up: {event}")

# EventHandler.for_event("order.created")  # OrderCreatedHandler
```

Advanced class patterns:
1. **Descriptors** — reusable attribute validation and type checking
2. **`__set_name__`** — descriptor learns its attribute name automatically
3. **Metaclass registry** — auto-register subclasses for plugin systems
4. **`__init_subclass__`** — simpler alternative to metaclasses for many use cases
5. **Interface enforcement** — metaclass ensures subclasses implement required methods'''
    ),
    (
        "python/dataclasses-advanced",
        "Show advanced dataclass patterns: post_init, field factories, ordering, slots, frozen, and attrs comparison.",
        '''Advanced dataclass patterns:

```python
from dataclasses import dataclass, field, asdict, astuple, replace, fields
from typing import Optional, ClassVar
from datetime import datetime, timezone
from functools import total_ordering
import json


# --- Post-init processing ---

@dataclass
class User:
    first_name: str
    last_name: str
    email: str
    age: int
    # Computed fields
    full_name: str = field(init=False)
    email_domain: str = field(init=False)

    def __post_init__(self):
        self.full_name = f"{self.first_name} {self.last_name}"
        self.email_domain = self.email.split("@")[1] if "@" in self.email else ""
        # Validation
        if self.age < 0 or self.age > 150:
            raise ValueError(f"Invalid age: {self.age}")
        self.email = self.email.lower().strip()


# --- Factory fields and defaults ---

@dataclass
class Config:
    name: str
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    # Excluded from repr and comparison
    _cache: dict = field(default_factory=dict, repr=False, compare=False)
    # Class variable (not a field)
    MAX_TAGS: ClassVar[int] = 10


# --- Frozen (immutable) ---

@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return ((self.x - other.x)**2 + (self.y - other.y)**2) ** 0.5

    def translate(self, dx: float, dy: float) -> "Point":
        # Can't modify frozen — return new instance
        return replace(self, x=self.x + dx, y=self.y + dy)

# Hashable (can use as dict key or in set)
# points = {Point(0, 0): "origin", Point(1, 1): "diagonal"}


# --- Slots (memory efficient, faster attribute access) ---

@dataclass(slots=True)
class SensorReading:
    sensor_id: str
    timestamp: float
    value: float
    unit: str = "celsius"

# Uses ~40% less memory than regular dataclass for many instances


# --- Ordering ---

@dataclass(order=True)
class Priority:
    # sort_index is used for comparison (first field)
    sort_index: int = field(init=False, repr=False)
    level: str = "medium"
    task: str = ""

    LEVELS = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def __post_init__(self):
        self.sort_index = self.LEVELS.get(self.level, 99)

# sorted([Priority("low", "A"), Priority("critical", "B"), Priority("high", "C")])
# [Priority(level='critical', task='B'), Priority(level='high', task='C'), ...]


# --- Serialization ---

@dataclass
class APIResponse:
    status: str
    data: dict
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        # Custom serialization for datetime
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "APIResponse":
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


# --- Inheritance ---

@dataclass
class BaseModel:
    id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

@dataclass
class Product(BaseModel):
    name: str = ""
    price: float = 0.0
    category: str = ""

    def __post_init__(self):
        if self.price < 0:
            raise ValueError("Price cannot be negative")


# --- Utility: copy with changes ---

original = Product(name="Widget", price=9.99, category="tools")
discounted = replace(original, price=7.99)  # New instance with changed price


# --- Inspect fields ---

def get_field_names(cls) -> list[str]:
    return [f.name for f in fields(cls)]

def get_required_fields(cls) -> list[str]:
    return [
        f.name for f in fields(cls)
        if f.default is f.default_factory  # No default
    ]
```

Dataclass patterns:
1. **`frozen=True`** — immutable instances, hashable (can use in sets/dict keys)
2. **`slots=True`** — 40% less memory, faster attribute access (Python 3.10+)
3. **`field(init=False)`** — computed in `__post_init__`, not passed to constructor
4. **`replace()`** — create modified copy of frozen instance
5. **`order=True`** — auto-generate comparison methods based on field order'''
    ),
]
"""
