"""Python — abc patterns, dataclasses advanced, descriptors, and metaclasses."""

PAIRS = [
    (
        "python/abc-protocols",
        "Show Python ABC and Protocol patterns: abstract classes, interface definitions, and structural typing.",
        '''Python ABC and Protocol patterns:

```python
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable, Any
from dataclasses import dataclass


# --- Abstract Base Class ---

class Repository(ABC):
    """Abstract repository — subclasses must implement all abstract methods."""

    @abstractmethod
    def get(self, id: str) -> dict:
        """Retrieve item by ID."""
        ...

    @abstractmethod
    def save(self, item: dict) -> None:
        """Persist item."""
        ...

    @abstractmethod
    def delete(self, id: str) -> None:
        """Remove item by ID."""
        ...

    # Concrete method (shared by all subclasses)
    def exists(self, id: str) -> bool:
        try:
            self.get(id)
            return True
        except KeyError:
            return False


class InMemoryRepo(Repository):
    def __init__(self):
        self._store: dict[str, dict] = {}

    def get(self, id: str) -> dict:
        if id not in self._store:
            raise KeyError(f"Not found: {id}")
        return self._store[id]

    def save(self, item: dict) -> None:
        self._store[item["id"]] = item

    def delete(self, id: str) -> None:
        del self._store[id]


# Can't instantiate ABC directly:
# repo = Repository()  # TypeError: Can't instantiate abstract class


# --- Protocol (structural typing — no inheritance needed) ---

@runtime_checkable
class Drawable(Protocol):
    """Anything with a draw() method satisfies this protocol."""
    def draw(self, canvas: Any) -> None: ...


@runtime_checkable
class Serializable(Protocol):
    """Anything with to_dict() and from_dict()."""
    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> "Serializable": ...


# This class satisfies Drawable WITHOUT inheriting from it
class Circle:
    def __init__(self, radius: float):
        self.radius = radius

    def draw(self, canvas: Any) -> None:
        canvas.draw_circle(0, 0, self.radius)


# Type checker knows Circle satisfies Drawable
def render(shapes: list[Drawable], canvas: Any) -> None:
    for shape in shapes:
        shape.draw(canvas)

# Runtime check works with @runtime_checkable:
assert isinstance(Circle(5), Drawable)  # True


# --- Protocol with properties ---

class HasName(Protocol):
    @property
    def name(self) -> str: ...


class HasSize(Protocol):
    @property
    def size(self) -> int: ...


# Intersection of protocols via inheritance
class NamedSized(HasName, HasSize, Protocol):
    pass


def describe(item: NamedSized) -> str:
    return f"{item.name} ({item.size} bytes)"


# --- Abstract property ---

class Shape(ABC):
    @property
    @abstractmethod
    def area(self) -> float: ...

    @property
    @abstractmethod
    def perimeter(self) -> float: ...

    def describe(self) -> str:
        return f"{self.__class__.__name__}: area={self.area:.2f}"


@dataclass
class Rectangle(Shape):
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def perimeter(self) -> float:
        return 2 * (self.width + self.height)


# --- Register virtual subclass ---

class JSONSerializable(ABC):
    @abstractmethod
    def to_json(self) -> str: ...

# Register dict as virtual subclass (duck typing bridge)
JSONSerializable.register(dict)
assert isinstance({}, JSONSerializable)  # True (but doesn't check to_json!)
```

ABC vs Protocol:
1. **ABC** — explicit inheritance required, enforced at instantiation time
2. **Protocol** — structural typing, no inheritance needed (duck typing + type safety)
3. **`@runtime_checkable`** — enables `isinstance()` checks on Protocols
4. **`@abstractmethod`** — subclass must implement or can't be instantiated
5. **`register()`** — declare existing classes as virtual ABC subclasses'''
    ),
    (
        "python/dataclasses-advanced",
        "Show advanced dataclass patterns: post_init, field factories, slots, ordering, and frozen instances.",
        '''Advanced dataclass patterns:

```python
from dataclasses import dataclass, field, asdict, astuple, replace, fields
from typing import ClassVar, Self
from functools import cached_property
import json


# --- Basic with validation ---

@dataclass
class User:
    name: str
    email: str
    age: int = 0
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate after __init__."""
        if not self.email or "@" not in self.email:
            raise ValueError(f"Invalid email: {self.email}")
        self.email = self.email.lower()
        if self.age < 0:
            raise ValueError("Age cannot be negative")


# --- Frozen (immutable) ---

@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5

    def translate(self, dx: float, dy: float) -> "Point":
        """Return new point (can't mutate frozen)."""
        return replace(self, x=self.x + dx, y=self.y + dy)

# p = Point(1, 2)
# p.x = 5  # FrozenInstanceError!
# p2 = p.translate(3, 4)  # Point(x=4, y=6)


# --- Slots (memory efficient, faster attribute access) ---

@dataclass(slots=True)
class SensorReading:
    sensor_id: str
    value: float
    timestamp: float
    unit: str = "celsius"

# Uses __slots__ — ~40% less memory per instance
# Cannot add arbitrary attributes: reading.extra = 1  # AttributeError


# --- Ordering ---

@dataclass(order=True)
class Version:
    """Comparable versions — generates __lt__, __le__, __gt__, __ge__."""
    sort_index: tuple = field(init=False, repr=False)
    major: int
    minor: int
    patch: int

    def __post_init__(self):
        self.sort_index = (self.major, self.minor, self.patch)

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}"

# sorted([Version(2,0,0), Version(1,9,1), Version(1,9,2)])
# → [Version(1,9,1), Version(1,9,2), Version(2,0,0)]


# --- ClassVar and InitVar ---

from dataclasses import InitVar

@dataclass
class Config:
    # ClassVar: shared across instances, not in __init__
    _registry: ClassVar[dict[str, "Config"]] = {}

    name: str
    value: str
    # InitVar: passed to __init__ but not stored as field
    register: InitVar[bool] = True

    def __post_init__(self, register: bool):
        if register:
            Config._registry[self.name] = self

    @classmethod
    def get(cls, name: str) -> "Config":
        return cls._registry[name]


# --- Field metadata ---

@dataclass
class Product:
    id: str
    name: str = field(metadata={"max_length": 100, "searchable": True})
    price: float = field(metadata={"min": 0, "currency": "USD"})
    internal_code: str = field(default="", repr=False)  # Hidden from repr

    def validate(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if "max_length" in f.metadata and len(str(value)) > f.metadata["max_length"]:
                raise ValueError(f"{f.name} exceeds max length")
            if "min" in f.metadata and value < f.metadata["min"]:
                raise ValueError(f"{f.name} below minimum")


# --- Serialization helpers ---

@dataclass
class Order:
    id: str
    items: list[str]
    total: float

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(**data)

    def to_tuple(self) -> tuple:
        return astuple(self)


# --- Inheritance ---

@dataclass
class Animal:
    name: str
    sound: str

    def speak(self) -> str:
        return f"{self.name} says {self.sound}"


@dataclass
class Dog(Animal):
    breed: str = "mixed"
    sound: str = "woof"  # Override default

# Dog(name="Rex", breed="Lab")  → Dog(name='Rex', sound='woof', breed='Lab')


# --- Cached property with dataclass ---

@dataclass
class DataSet:
    values: list[float] = field(default_factory=list)

    # Can't use @cached_property with slots=True
    @cached_property
    def stats(self) -> dict:
        """Computed once, cached."""
        n = len(self.values)
        mean = sum(self.values) / n if n else 0
        return {
            "count": n,
            "mean": mean,
            "min": min(self.values) if n else 0,
            "max": max(self.values) if n else 0,
        }
```

Advanced dataclass patterns:
1. **`__post_init__`** — validate/transform fields after initialization
2. **`frozen=True`** — immutable instances, use `replace()` for copies
3. **`slots=True`** — 40% less memory, faster attribute access
4. **`order=True`** — auto-generate comparison methods from `sort_index`
5. **`field(metadata={})`** — attach validation rules and metadata to fields'''
    ),
    (
        "python/descriptors-metaclasses",
        "Show Python descriptor protocol and metaclass patterns: property implementation, validation descriptors, and class creation.",
        '''Python descriptors and metaclasses:

```python
from typing import Any, Callable
import weakref


# --- Descriptor protocol ---

class Validated:
    """Descriptor that validates on set."""

    def __init__(self, validator: Callable[[Any], Any], default=None):
        self.validator = validator
        self.default = default
        self.data = weakref.WeakKeyDictionary()

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self  # Accessed on class, not instance
        return self.data.get(obj, self.default)

    def __set__(self, obj, value):
        self.data[obj] = self.validator(value)


# Validator functions
def positive(value):
    if value <= 0:
        raise ValueError(f"Must be positive, got {value}")
    return value

def non_empty_string(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Must be non-empty string, got {value!r}")
    return value.strip()

def in_range(low, high):
    def validator(value):
        if not low <= value <= high:
            raise ValueError(f"Must be between {low} and {high}, got {value}")
        return value
    return validator


class Product:
    name = Validated(non_empty_string)
    price = Validated(positive)
    quantity = Validated(in_range(0, 10000), default=0)

    def __init__(self, name: str, price: float, quantity: int = 0):
        self.name = name      # Triggers Validated.__set__
        self.price = price
        self.quantity = quantity

# p = Product("Widget", 9.99)
# p.price = -5  # ValueError: Must be positive


# --- Type-checked descriptor ---

class TypeChecked:
    """Descriptor that enforces type."""

    def __init__(self, expected_type: type):
        self.expected_type = expected_type
        self.data = weakref.WeakKeyDictionary()

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.data.get(obj)

    def __set__(self, obj, value):
        if not isinstance(value, self.expected_type):
            raise TypeError(
                f"{self.name} must be {self.expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        self.data[obj] = value


class Config:
    host = TypeChecked(str)
    port = TypeChecked(int)
    debug = TypeChecked(bool)

    def __init__(self, host: str, port: int, debug: bool = False):
        self.host = host
        self.port = port
        self.debug = debug


# --- Lazy property descriptor ---

class LazyProperty:
    """Compute once on first access, cache on instance."""

    def __init__(self, func):
        self.func = func
        self.attr_name = None

    def __set_name__(self, owner, name):
        self.attr_name = f"_lazy_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if not hasattr(obj, self.attr_name):
            setattr(obj, self.attr_name, self.func(obj))
        return getattr(obj, self.attr_name)


class DataProcessor:
    def __init__(self, path: str):
        self.path = path

    @LazyProperty
    def data(self):
        """Loaded only when first accessed."""
        print(f"Loading {self.path}...")
        with open(self.path) as f:
            return f.read()


# --- Simple metaclass ---

class SingletonMeta(type):
    """Metaclass that ensures only one instance per class."""

    _instances: dict[type, Any] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class Database(metaclass=SingletonMeta):
    def __init__(self, url: str):
        self.url = url
        self.connected = False

# db1 = Database("postgresql://localhost/mydb")
# db2 = Database("different-url")
# assert db1 is db2  # Same instance!


# --- Registry metaclass ---

class PluginMeta(type):
    """Auto-register subclasses."""

    registry: dict[str, type] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "name"):
            PluginMeta.registry[cls.name] = cls


class Plugin(metaclass=PluginMeta):
    name: str

class CSVPlugin(Plugin):
    name = "csv"
    def process(self, data): ...

class JSONPlugin(Plugin):
    name = "json"
    def process(self, data): ...

# PluginMeta.registry → {"csv": CSVPlugin, "json": JSONPlugin}


# --- __init_subclass__ (modern alternative to metaclass) ---

class Validator:
    """Base class that auto-collects validation rules."""

    _validators: dict[str, list[Callable]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._validators = {}
        for name, method in vars(cls).items():
            if hasattr(method, "_validates"):
                field = method._validates
                cls._validators.setdefault(field, []).append(method)


def validates(field: str):
    """Decorator to mark validation methods."""
    def decorator(func):
        func._validates = field
        return func
    return decorator
```

Descriptor and metaclass patterns:
1. **`__set_name__`** — descriptor learns its attribute name automatically
2. **`WeakKeyDictionary`** — per-instance storage without preventing GC
3. **`LazyProperty`** — compute expensive value once on first access
4. **`SingletonMeta`** — metaclass ensures one instance per class
5. **`__init_subclass__`** — modern hook for subclass registration (no metaclass needed)'''
    ),
]
