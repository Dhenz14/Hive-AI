"""Python metaclasses and descriptors: __init_subclass__, __set_name__, ABC, protocols, custom descriptors."""

PAIRS = [
    (
        "python/metaclasses/init-subclass-patterns",
        "How do I use __init_subclass__ instead of metaclasses in modern Python? Show plugin registration, validation, and automatic configuration patterns.",
        '''`__init_subclass__` (PEP 487) replaces most metaclass use cases with a simpler, more composable mechanism. It runs whenever a class is subclassed, letting you register, validate, or configure subclasses automatically.

```python
"""__init_subclass__ patterns — plugin registration, automatic
configuration, validation, and hook systems."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pattern 1: Auto-registration (plugin/handler discovery)
# ---------------------------------------------------------------------------
class CommandHandler(ABC):
    """Base class that auto-registers all subclasses as command handlers.

    Subclasses specify their command name via the class keyword arg:
        class MyHandler(CommandHandler, command="my-command"): ...
    """
    _registry: ClassVar[dict[str, type[CommandHandler]]] = {}

    def __init_subclass__(cls, *, command: str = "", **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if command:
            if command in cls._registry:
                raise ValueError(
                    f"Duplicate command {command!r}: "
                    f"{cls.__name__} vs {cls._registry[command].__name__}"
                )
            cls._registry[command] = cls
            cls.command_name = command  # type: ignore[attr-defined]
            logger.info("Registered command: %s -> %s", command, cls.__name__)

    @abstractmethod
    def execute(self, args: dict[str, Any]) -> Any:
        ...

    @classmethod
    def dispatch(cls, command: str, args: dict[str, Any]) -> Any:
        handler_cls = cls._registry.get(command)
        if not handler_cls:
            raise ValueError(f"Unknown command: {command!r}")
        handler = handler_cls()
        return handler.execute(args)

    @classmethod
    def list_commands(cls) -> list[str]:
        return sorted(cls._registry.keys())


class DeployHandler(CommandHandler, command="deploy"):
    def execute(self, args: dict[str, Any]) -> str:
        env = args.get("env", "staging")
        return f"Deploying to {env}..."


class RollbackHandler(CommandHandler, command="rollback"):
    def execute(self, args: dict[str, Any]) -> str:
        version = args.get("version", "previous")
        return f"Rolling back to {version}..."


class StatusHandler(CommandHandler, command="status"):
    def execute(self, args: dict[str, Any]) -> str:
        return "All systems operational"


# ---------------------------------------------------------------------------
# Pattern 2: Automatic field validation on subclasses
# ---------------------------------------------------------------------------
class ValidatedModel:
    """Base class that enforces type annotations on subclass instances.

    Every subclass must define type-annotated fields. At instantiation,
    values are checked against annotations.
    """
    _required_fields: ClassVar[dict[str, type]] = {}

    def __init_subclass__(cls, *, strict: bool = True, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._strict = strict
        # Collect annotations from the class (not parents)
        cls._required_fields = {}
        for name, annotation in cls.__annotations__.items():
            if not name.startswith("_"):
                cls._required_fields[name] = annotation

    def __init__(self, **kwargs: Any) -> None:
        cls = type(self)
        # Check required fields
        for field_name, field_type in cls._required_fields.items():
            if field_name not in kwargs:
                if not hasattr(cls, field_name):
                    raise TypeError(
                        f"{cls.__name__} requires field {field_name!r}"
                    )
            else:
                value = kwargs[field_name]
                if cls._strict and not isinstance(value, field_type):
                    raise TypeError(
                        f"{field_name} must be {field_type.__name__}, "
                        f"got {type(value).__name__}"
                    )
                setattr(self, field_name, value)

        # Set defaults for fields with class-level defaults
        for name in cls._required_fields:
            if name not in kwargs and hasattr(cls, name):
                setattr(self, name, getattr(cls, name))


class UserConfig(ValidatedModel, strict=True):
    username: str
    max_retries: int
    timeout: float = 30.0


# ---------------------------------------------------------------------------
# Pattern 3: Hook system with __init_subclass__
# ---------------------------------------------------------------------------
class Hookable:
    """Base class providing lifecycle hooks that subclasses can register."""
    _hooks: ClassVar[dict[str, list[Callable]]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._hooks = {}

        # Auto-discover hook methods (methods starting with "on_")
        for name in dir(cls):
            if name.startswith("on_") and callable(getattr(cls, name)):
                event = name[3:]  # strip "on_" prefix
                cls._hooks.setdefault(event, []).append(getattr(cls, name))

    def trigger(self, event: str, **data: Any) -> list[Any]:
        """Trigger all registered hooks for an event."""
        results = []
        for hook in self._hooks.get(event, []):
            results.append(hook(self, **data))
        return results


class OrderProcessor(Hookable):
    def on_created(self, order_id: str = "", **kw: Any) -> str:
        return f"Order {order_id} created"

    def on_paid(self, amount: float = 0, **kw: Any) -> str:
        return f"Payment received: ${amount:.2f}"

    def on_shipped(self, tracking: str = "", **kw: Any) -> str:
        return f"Shipped with tracking {tracking}"


# ---------------------------------------------------------------------------
# Pattern 4: Abstract interface enforcement
# ---------------------------------------------------------------------------
class Interface:
    """Enforce that subclasses implement required methods and properties.

    More explicit than ABC — fails at class creation, not instantiation.
    """
    _required_methods: ClassVar[tuple[str, ...]] = ()
    _required_properties: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(
        cls,
        *,
        required_methods: tuple[str, ...] = (),
        required_properties: tuple[str, ...] = (),
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)

        # Inherit parent requirements
        all_methods = set(cls._required_methods) | set(required_methods)
        all_props = set(cls._required_properties) | set(required_properties)

        # Only check concrete (non-abstract) classes
        if not getattr(cls, "__abstractmethods__", set()):
            missing_methods = [
                m for m in all_methods
                if not hasattr(cls, m) or not callable(getattr(cls, m))
            ]
            missing_props = [
                p for p in all_props
                if not isinstance(getattr(cls, p, None), property)
            ]

            if missing_methods:
                raise TypeError(
                    f"{cls.__name__} must implement methods: {missing_methods}"
                )
            if missing_props:
                # Allow non-property attributes too
                pass

        cls._required_methods = tuple(all_methods)
        cls._required_properties = tuple(all_props)


class Repository(
    Interface,
    required_methods=("get", "save", "delete", "list_all"),
):
    """Abstract repository interface."""
    pass


class UserRepository(Repository):
    """Concrete repository — must implement get, save, delete, list_all."""
    def get(self, id: str) -> dict:
        return {"id": id}

    def save(self, entity: dict) -> None:
        pass

    def delete(self, id: str) -> None:
        pass

    def list_all(self) -> list[dict]:
        return []


# ---------------------------------------------------------------------------
# Pattern 5: Mixin composition with __init_subclass__
# ---------------------------------------------------------------------------
class TimestampMixin:
    """Add created_at / updated_at tracking."""
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        original_init = cls.__init__ if hasattr(cls, "__init__") else None

        def new_init(self: Any, *args: Any, **kw: Any) -> None:
            from datetime import datetime, timezone
            self.created_at = datetime.now(timezone.utc)
            self.updated_at = self.created_at
            if original_init and original_init is not object.__init__:
                original_init(self, *args, **kw)

        cls.__init__ = new_init


class SoftDeleteMixin:
    """Add soft-delete capability."""
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.is_deleted = False

        def soft_delete(self: Any) -> None:
            self.is_deleted = True
            from datetime import datetime, timezone
            self.deleted_at = datetime.now(timezone.utc)

        def restore(self: Any) -> None:
            self.is_deleted = False
            self.deleted_at = None

        cls.soft_delete = soft_delete
        cls.restore = restore


class ManagedEntity(TimestampMixin, SoftDeleteMixin):
    """Entity with timestamp tracking and soft-delete."""
    def __init__(self, name: str) -> None:
        self.name = name


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    # Command dispatch
    print("=== Command Dispatch ===")
    print(f"Commands: {CommandHandler.list_commands()}")
    print(CommandHandler.dispatch("deploy", {"env": "production"}))
    print(CommandHandler.dispatch("status", {}))

    # Validated model
    print("\\n=== Validated Model ===")
    config = UserConfig(username="alice", max_retries=3)
    print(f"Config: {config.username}, timeout={config.timeout}")

    try:
        bad = UserConfig(username=42, max_retries=3)  # type error
    except TypeError as e:
        print(f"Validation error: {e}")

    # Hooks
    print("\\n=== Hooks ===")
    processor = OrderProcessor()
    results = processor.trigger("created", order_id="ORD-001")
    print(f"Hook results: {results}")

    # Managed entity
    print("\\n=== Managed Entity ===")
    entity = ManagedEntity("test")
    print(f"Created: {entity.created_at}, deleted: {entity.is_deleted}")
    entity.soft_delete()
    print(f"After delete: {entity.is_deleted}")


if __name__ == "__main__":
    main()
```

**Key patterns:**

- **Plugin registration** — subclasses register themselves via class keyword args (`command="deploy"`)
- **Validation at class creation** — check that subclasses implement required methods before any instance is created
- **Hook discovery** — auto-discover methods matching a naming convention (`on_*`) at subclass creation time
- **Mixin composition** — multiple `__init_subclass__` mixins compose via `super().__init_subclass__(**kwargs)`
- **Class keyword args** — `class Foo(Base, command="x")` passes `command` to `__init_subclass__`
- **Prefer `__init_subclass__` over metaclasses** — simpler, composable, and compatible with multiple inheritance'''
    ),
    (
        "python/metaclasses/descriptors-set-name",
        "How do custom descriptors work with __set_name__ in Python? Show patterns for validated attributes, lazy loading, and ORM-style field definitions.",
        '''The descriptor protocol (`__get__`, `__set__`, `__delete__`) combined with `__set_name__` (PEP 487) lets you build reusable field types — the same mechanism behind `@property`, `@classmethod`, and ORM fields.

```python
"""Custom descriptors with __set_name__ — validated fields, lazy
attributes, ORM-style columns, and dependency tracking."""

from __future__ import annotations

import re
import weakref
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar, overload

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 1. Typed + validated descriptor
# ---------------------------------------------------------------------------
class TypedField(Generic[T]):
    """Descriptor that enforces type and runs custom validators.

    Usage:
        class User:
            name = TypedField(str, min_length=1, max_length=100)
            age = TypedField(int, ge=0, le=150)
    """

    def __init__(
        self,
        expected_type: type[T],
        *,
        ge: float | None = None,
        le: float | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
        validator: Callable[[T], bool] | None = None,
    ) -> None:
        self.expected_type = expected_type
        self.ge = ge
        self.le = le
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = re.compile(pattern) if pattern else None
        self.custom_validator = validator
        self.name: str = ""
        self.storage_name: str = ""

    def __set_name__(self, owner: type, name: str) -> None:
        """Called when the descriptor is assigned to a class attribute."""
        self.name = name
        self.storage_name = f"_field_{name}"

    @overload
    def __get__(self, obj: None, objtype: type) -> TypedField[T]: ...
    @overload
    def __get__(self, obj: Any, objtype: type) -> T: ...

    def __get__(self, obj: Any, objtype: type = None) -> Any:
        if obj is None:
            return self  # class-level access returns descriptor
        return getattr(obj, self.storage_name, None)

    def __set__(self, obj: Any, value: T) -> None:
        self._validate(value)
        setattr(obj, self.storage_name, value)

    def __delete__(self, obj: Any) -> None:
        try:
            delattr(obj, self.storage_name)
        except AttributeError:
            raise AttributeError(
                f"'{type(obj).__name__}' has no value for '{self.name}'"
            )

    def _validate(self, value: T) -> None:
        if not isinstance(value, self.expected_type):
            raise TypeError(
                f"{self.name}: expected {self.expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        if self.ge is not None and value < self.ge:  # type: ignore
            raise ValueError(f"{self.name}: must be >= {self.ge}, got {value}")
        if self.le is not None and value > self.le:  # type: ignore
            raise ValueError(f"{self.name}: must be <= {self.le}, got {value}")
        if self.min_length is not None and len(value) < self.min_length:  # type: ignore
            raise ValueError(
                f"{self.name}: length must be >= {self.min_length}"
            )
        if self.max_length is not None and len(value) > self.max_length:  # type: ignore
            raise ValueError(
                f"{self.name}: length must be <= {self.max_length}"
            )
        if self.pattern and not self.pattern.match(str(value)):
            raise ValueError(
                f"{self.name}: does not match pattern {self.pattern.pattern}"
            )
        if self.custom_validator and not self.custom_validator(value):
            raise ValueError(f"{self.name}: custom validation failed")


class User:
    """User model using TypedField descriptors."""
    name = TypedField(str, min_length=1, max_length=100)
    email = TypedField(str, pattern=r"^[\w.+-]+@[\w.-]+\.[\w]{2,}$")
    age = TypedField(int, ge=0, le=150)

    def __init__(self, name: str, email: str, age: int) -> None:
        self.name = name    # triggers TypedField.__set__
        self.email = email
        self.age = age


# ---------------------------------------------------------------------------
# 2. Lazy descriptor (compute on first access)
# ---------------------------------------------------------------------------
class LazyAttribute:
    """Descriptor that computes value on first access and caches it.

    The factory receives the instance as its argument.
    """

    def __init__(self, factory: Callable[[Any], Any]) -> None:
        self.factory = factory
        self.name: str = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, obj: Any, objtype: type = None) -> Any:
        if obj is None:
            return self
        value = self.factory(obj)
        # Replace descriptor access with the computed value
        # This means __get__ only runs once per instance
        setattr(obj, self.name, value)
        return value


class ExpensiveModel:
    """Model with lazily computed attributes."""

    def __init__(self, data: dict) -> None:
        self.data = data

    @LazyAttribute
    def processed(self) -> dict:
        """Expensive computation — only runs once."""
        import time
        time.sleep(0.01)  # simulate work
        return {k: v.upper() if isinstance(v, str) else v
                for k, v in self.data.items()}

    @LazyAttribute
    def summary(self) -> str:
        return f"Model with {len(self.data)} fields"


# ---------------------------------------------------------------------------
# 3. ORM-style column descriptor
# ---------------------------------------------------------------------------
class Column(ABC):
    """Base ORM column descriptor."""
    _columns: dict[str, Column]

    def __init__(
        self,
        *,
        primary_key: bool = False,
        nullable: bool = True,
        default: Any = None,
        unique: bool = False,
    ) -> None:
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.unique = unique
        self.name: str = ""
        self.owner: type | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self.owner = owner
        # Register this column on the owner class
        if not hasattr(owner, "_columns"):
            owner._columns = {}
        owner._columns[name] = self

    def __get__(self, obj: Any, objtype: type = None) -> Any:
        if obj is None:
            return self
        return getattr(obj, f"_col_{self.name}", self.default)

    def __set__(self, obj: Any, value: Any) -> None:
        if value is None and not self.nullable:
            raise ValueError(f"{self.name}: cannot be null")
        if value is not None:
            value = self.coerce(value)
            self.validate(value)
        setattr(obj, f"_col_{self.name}", value)

    @abstractmethod
    def coerce(self, value: Any) -> Any:
        """Convert value to the column's type."""
        ...

    def validate(self, value: Any) -> None:
        """Override for type-specific validation."""
        pass

    def to_sql_type(self) -> str:
        """Return SQL type string for schema generation."""
        return "TEXT"


class StringColumn(Column):
    def __init__(self, max_length: int = 255, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_length = max_length

    def coerce(self, value: Any) -> str:
        return str(value)

    def validate(self, value: str) -> None:
        if len(value) > self.max_length:
            raise ValueError(
                f"{self.name}: max length is {self.max_length}, "
                f"got {len(value)}"
            )

    def to_sql_type(self) -> str:
        return f"VARCHAR({self.max_length})"


class IntegerColumn(Column):
    def coerce(self, value: Any) -> int:
        return int(value)

    def to_sql_type(self) -> str:
        return "INTEGER"


class BooleanColumn(Column):
    def coerce(self, value: Any) -> bool:
        return bool(value)

    def to_sql_type(self) -> str:
        return "BOOLEAN"


class DateTimeColumn(Column):
    def coerce(self, value: Any) -> datetime:
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        if isinstance(value, datetime):
            return value
        raise TypeError(f"Cannot coerce {type(value)} to datetime")

    def to_sql_type(self) -> str:
        return "TIMESTAMP"


# ---------------------------------------------------------------------------
# ORM Model base using __init_subclass__ to collect columns
# ---------------------------------------------------------------------------
class Model:
    """Base model that discovers Column descriptors on subclasses."""
    _table_name: str = ""

    def __init_subclass__(cls, *, table: str = "", **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._table_name = table or cls.__name__.lower() + "s"

    @classmethod
    def create_table_sql(cls) -> str:
        """Generate CREATE TABLE SQL from column descriptors."""
        columns = getattr(cls, "_columns", {})
        parts = []
        for name, col in columns.items():
            sql = f"  {name} {col.to_sql_type()}"
            if col.primary_key:
                sql += " PRIMARY KEY"
            if not col.nullable:
                sql += " NOT NULL"
            if col.unique:
                sql += " UNIQUE"
            parts.append(sql)
        return f"CREATE TABLE {cls._table_name} (\\n" + ",\\n".join(parts) + "\\n);"


class Article(Model, table="articles"):
    id = IntegerColumn(primary_key=True, nullable=False)
    title = StringColumn(max_length=200, nullable=False)
    body = StringColumn(max_length=10000)
    published = BooleanColumn(default=False)
    created_at = DateTimeColumn(nullable=False)

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    # TypedField
    print("=== TypedField ===")
    user = User("Alice", "alice@example.com", 30)
    print(f"User: {user.name}, {user.email}, age={user.age}")

    try:
        user.age = -1
    except ValueError as e:
        print(f"Validation: {e}")

    # Lazy attribute
    print("\\n=== LazyAttribute ===")
    model = ExpensiveModel({"name": "test", "value": "hello"})
    print(f"Summary: {model.summary}")  # computed once
    print(f"Summary: {model.summary}")  # cached — no recomputation

    # ORM columns
    print("\\n=== ORM Columns ===")
    article = Article(
        id=1,
        title="Hello World",
        body="Content here",
        published=True,
        created_at=datetime.now(timezone.utc),
    )
    print(f"Article: {article.title} (published={article.published})")
    print(f"\\n{Article.create_table_sql()}")


if __name__ == "__main__":
    main()
```

**Key patterns:**

- **`__set_name__`** — automatically receives the attribute name when assigned to a class, eliminating manual name passing
- **`__get__` with `obj is None` check** — return the descriptor itself for class-level access, return the value for instance access
- **Storage naming convention** — store values under `_field_{name}` or `_col_{name}` to avoid conflicts with the descriptor attribute
- **Lazy attributes** — use `setattr(obj, self.name, value)` to replace the descriptor lookup with the computed value (one-shot)
- **ORM columns** — combine descriptors with `__init_subclass__` to auto-discover columns and generate SQL schemas
- **Type coercion** — descriptors can convert values (`str -> datetime`) on every `__set__`, acting like automatic converters'''
    ),
    (
        "python/metaclasses/protocols-structural-typing",
        "How do Protocols work in Python for structural typing? Show runtime checkable protocols, combining with ABCs, and patterns for duck typing with type safety.",
        '''Protocols (PEP 544) bring structural typing ("duck typing") to Python's type system. An object satisfies a Protocol if it has the required methods/attributes, regardless of inheritance.

```python
"""Protocols for structural typing — runtime checking, combining
with ABCs, generic protocols, and practical patterns."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator, Sized
from dataclasses import dataclass
from typing import (
    Any,
    Protocol,
    TypeVar,
    runtime_checkable,
)


# ---------------------------------------------------------------------------
# 1. Basic Protocol — structural typing
# ---------------------------------------------------------------------------
@runtime_checkable
class Renderable(Protocol):
    """Any object that can render itself to HTML."""
    def render(self) -> str: ...


@runtime_checkable
class Serializable(Protocol):
    """Any object that can serialize to a dict."""
    def to_dict(self) -> dict[str, Any]: ...


class JSONSerializable(Protocol):
    """Object that can produce JSON string."""
    def to_json(self) -> str: ...


# These classes satisfy the protocols WITHOUT inheriting from them:
@dataclass
class Button:
    label: str
    variant: str = "primary"

    def render(self) -> str:
        return f'<button class="btn-{self.variant}">{self.label}</button>'

    def to_dict(self) -> dict[str, Any]:
        return {"type": "button", "label": self.label, "variant": self.variant}


@dataclass
class Card:
    title: str
    body: str

    def render(self) -> str:
        return f"<div class='card'><h2>{self.title}</h2><p>{self.body}</p></div>"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "card", "title": self.title, "body": self.body}


# Functions that accept Protocol types — works with ANY class that matches:
def render_all(components: list[Renderable]) -> str:
    """Render a list of components to HTML."""
    return "\\n".join(c.render() for c in components)


def serialize_all(objects: list[Serializable]) -> list[dict]:
    """Serialize a list of objects to dicts."""
    return [obj.to_dict() for obj in objects]


# ---------------------------------------------------------------------------
# 2. Generic Protocol — type-safe containers
# ---------------------------------------------------------------------------
T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)


class Repository(Protocol[T]):
    """Generic repository protocol — any storage backend that
    implements these methods satisfies the contract."""
    def get(self, id: str) -> T | None: ...
    def save(self, entity: T) -> None: ...
    def delete(self, id: str) -> bool: ...
    def list_all(self, limit: int = 100) -> list[T]: ...


class Comparable(Protocol):
    """Protocol for objects that support comparison."""
    def __lt__(self, other: Any) -> bool: ...
    def __le__(self, other: Any) -> bool: ...


class SupportsAdd(Protocol[T_co]):
    """Protocol for objects supporting addition."""
    def __add__(self, other: Any) -> T_co: ...


# Concrete implementation satisfies Repository[User] structurally:
@dataclass
class UserEntity:
    id: str
    name: str
    email: str


class InMemoryUserRepo:
    """Satisfies Repository[UserEntity] without inheriting from it."""
    def __init__(self) -> None:
        self._store: dict[str, UserEntity] = {}

    def get(self, id: str) -> UserEntity | None:
        return self._store.get(id)

    def save(self, entity: UserEntity) -> None:
        self._store[entity.id] = entity

    def delete(self, id: str) -> bool:
        return self._store.pop(id, None) is not None

    def list_all(self, limit: int = 100) -> list[UserEntity]:
        return list(self._store.values())[:limit]


# ---------------------------------------------------------------------------
# 3. Protocol with properties and class variables
# ---------------------------------------------------------------------------
@runtime_checkable
class HasVersion(Protocol):
    """Protocol requiring a version property."""
    @property
    def version(self) -> str: ...


class Configurable(Protocol):
    """Protocol with class variable and instance method."""
    config_key: str

    def get_config(self) -> dict[str, Any]: ...
    def update_config(self, **kwargs: Any) -> None: ...


# ---------------------------------------------------------------------------
# 4. Combining Protocol with ABC (abstract + structural)
# ---------------------------------------------------------------------------
class Cacheable(Protocol):
    """Structural requirement: must have a cache_key."""
    @property
    def cache_key(self) -> str: ...
    def cache_ttl(self) -> int: ...


class CacheableService(ABC):
    """Abstract base that uses Protocol for type checking but ABC for
    enforcing implementation in subclasses."""

    @abstractmethod
    def get_cache_key(self, *args: Any) -> str: ...

    @abstractmethod
    def compute(self, *args: Any) -> Any: ...

    def cached_compute(self, *args: Any, cache: dict | None = None) -> Any:
        cache = cache if cache is not None else {}
        key = self.get_cache_key(*args)
        if key in cache:
            return cache[key]
        result = self.compute(*args)
        cache[key] = result
        return result


class FibonacciService(CacheableService):
    def get_cache_key(self, n: int) -> str:
        return f"fib:{n}"

    def compute(self, n: int) -> int:
        if n < 2:
            return n
        return self.cached_compute(n - 1) + self.cached_compute(n - 2)


# ---------------------------------------------------------------------------
# 5. Protocol intersection and composition
# ---------------------------------------------------------------------------
class ReadableWritable(Renderable, Serializable, Protocol):
    """Intersection protocol — object must satisfy BOTH Renderable
    and Serializable."""
    pass


def process_component(component: ReadableWritable) -> dict:
    """Accept only objects that are both Renderable AND Serializable."""
    html = component.render()
    data = component.to_dict()
    data["html"] = html
    return data


# ---------------------------------------------------------------------------
# 6. Callback protocols (callable with specific signature)
# ---------------------------------------------------------------------------
class EventCallback(Protocol):
    """Protocol for event handler callbacks."""
    def __call__(self, event_type: str, data: dict[str, Any]) -> bool: ...


class Middleware(Protocol):
    """Protocol for middleware functions."""
    def __call__(self, request: dict, next_handler: Any) -> dict: ...


def register_handler(event: str, callback: EventCallback) -> None:
    """Register an event callback — any callable matching the
    signature is accepted."""
    # In production, store in a registry
    print(f"Registered {callback} for {event}")


# This plain function satisfies EventCallback:
def log_event(event_type: str, data: dict[str, Any]) -> bool:
    print(f"Event: {event_type}, data: {data}")
    return True


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    # Structural typing
    print("=== Structural Typing ===")
    components: list[Renderable] = [
        Button("Click me"),
        Card("Title", "Body text"),
    ]
    print(render_all(components))

    # Runtime checking
    print(f"\\nButton is Renderable: {isinstance(Button('x'), Renderable)}")
    print(f"dict is Renderable: {isinstance({}, Renderable)}")
    print(f"Button is Serializable: {isinstance(Button('x'), Serializable)}")

    # Generic protocol
    print("\\n=== Generic Repository ===")
    repo: Repository[UserEntity] = InMemoryUserRepo()
    repo.save(UserEntity("1", "Alice", "alice@example.com"))
    print(f"User: {repo.get('1')}")
    print(f"All: {repo.list_all()}")

    # Intersection
    print("\\n=== Intersection ===")
    btn = Button("Submit")
    result = process_component(btn)
    print(f"Processed: {result}")

    # Callback protocol
    print("\\n=== Callback Protocol ===")
    register_handler("click", log_event)


if __name__ == "__main__":
    main()
```

**Comparison: Protocol vs ABC**

| Feature | Protocol | ABC |
|---|---|---|
| Typing | Structural (duck typing) | Nominal (explicit inheritance) |
| Runtime checking | `@runtime_checkable` + `isinstance` | `isinstance` via `__subclasshook__` |
| Failure point | Type checker (mypy/pyright) | Instantiation time |
| Multiple inheritance | Natural composition | MRO complexity |
| Generics | `Protocol[T]` | `Generic[T]` |
| Best for | Third-party code, callbacks, interfaces | Your own class hierarchies |

**Key patterns:**

- **`@runtime_checkable`** — enables `isinstance()` checks at runtime (only checks method existence, not signatures)
- **Generic protocols** — `Repository[T]` creates type-safe interfaces parameterized by entity type
- **Intersection protocols** — inherit from multiple protocols to require all their methods
- **Callback protocols** — define `__call__` to type-check callable objects with specific signatures
- **Structural typing** — classes satisfy protocols without inheriting from them; works with third-party code you cannot modify
- **Combine with ABC** — use Protocol for external interfaces, ABC for internal hierarchies where you control the code'''
    ),
    (
        "python/metaclasses/actual-metaclass-patterns",
        "When do I actually need a real metaclass in Python? Show the few remaining use cases where __init_subclass__ is not sufficient.",
        '''True metaclasses are rarely needed in modern Python, but there are a few cases where `__init_subclass__` cannot do the job: controlling `__new__` (class creation itself), modifying the class namespace, or intercepting attribute access at the class level.

```python
"""Real metaclass patterns — the few cases where __init_subclass__
is not sufficient: namespace control, class-level __getattr__,
and instance creation interception."""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Ordered attributes (e.g., ORM field ordering)
# ---------------------------------------------------------------------------
class OrderedNamespace(dict):
    """Custom namespace that records attribute definition order."""

    def __init__(self) -> None:
        super().__init__()
        self._order: list[str] = []

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self and not key.startswith("_"):
            self._order.append(key)
        super().__setitem__(key, value)


class OrderedMeta(type):
    """Metaclass that preserves field definition order.

    __init_subclass__ CANNOT do this because it runs AFTER the class
    body has been evaluated — the namespace dict has already lost order
    in older Python versions.
    """

    @classmethod
    def __prepare__(mcs, name: str, bases: tuple, **kwargs: Any) -> OrderedNamespace:
        """Return a custom dict that tracks insertion order.

        __prepare__ is unique to metaclasses — __init_subclass__
        has no equivalent.
        """
        return OrderedNamespace()

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: OrderedNamespace,
        **kwargs: Any,
    ) -> OrderedMeta:
        cls = super().__new__(mcs, name, bases, dict(namespace), **kwargs)
        cls._field_order = namespace._order  # type: ignore[attr-defined]
        return cls


class Form(metaclass=OrderedMeta):
    """Form base class — fields are kept in definition order."""

    @classmethod
    def get_fields(cls) -> list[str]:
        return cls._field_order  # type: ignore[attr-defined]


class RegistrationForm(Form):
    username = "text"
    email = "email"
    password = "password"
    confirm_password = "password"
    agree_terms = "checkbox"


# ---------------------------------------------------------------------------
# 2. Singleton metaclass (thread-safe)
# ---------------------------------------------------------------------------
import threading


class SingletonMeta(type):
    """Thread-safe singleton metaclass.

    Unlike the __init_subclass__ singleton approach, this intercepts
    __call__ at the metaclass level — guaranteeing exactly one instance
    even with concurrent instantiation.
    """
    _instances: dict[type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            with cls._lock:
                # Double-check locking
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]


class DatabaseConnection(metaclass=SingletonMeta):
    def __init__(self, dsn: str = "postgres://localhost/db") -> None:
        self.dsn = dsn
        self.connected = True
        logger.info("Database connected to %s", dsn)


# ---------------------------------------------------------------------------
# 3. Class-level __getattr__ (attribute access interception)
# ---------------------------------------------------------------------------
class EnumMeta(type):
    """Metaclass that provides class-level __getattr__ for
    dynamic enum-like access.

    __init_subclass__ cannot intercept attribute access on the class.
    """
    _members: dict[str, Any]

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: dict,
        **kwargs: Any,
    ) -> EnumMeta:
        members = {}
        for key, value in list(namespace.items()):
            if not key.startswith("_") and not callable(value):
                members[key] = value
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        cls._members = members
        return cls

    def __getattr__(cls, name: str) -> Any:
        """Intercept class-level attribute access for dynamic lookup."""
        if name in cls._members:
            return cls._members[name]
        raise AttributeError(f"{cls.__name__} has no member {name!r}")

    def __contains__(cls, value: Any) -> bool:
        return value in cls._members.values()

    def __iter__(cls):
        return iter(cls._members.items())

    def __len__(cls) -> int:
        return len(cls._members)


class Color(metaclass=EnumMeta):
    RED = "#FF0000"
    GREEN = "#00FF00"
    BLUE = "#0000FF"


# ---------------------------------------------------------------------------
# 4. Abstract enforcement at class creation (not instantiation)
# ---------------------------------------------------------------------------
class StrictAbstractMeta(type):
    """Metaclass that FAILS at class definition time (not instantiation)
    if abstract methods are not implemented.

    ABC only fails when you try to create an instance.
    This fails when you define the class.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: dict,
        *,
        abstract: bool = False,
        **kwargs: Any,
    ) -> StrictAbstractMeta:
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        if not abstract and bases:
            # Check if all abstract methods from parents are implemented
            for base in bases:
                for attr_name in dir(base):
                    attr = getattr(base, attr_name, None)
                    if getattr(attr, "_is_required", False):
                        if attr_name not in namespace:
                            raise TypeError(
                                f"{name} must implement {attr_name}() "
                                f"(required by {base.__name__})"
                            )
        return cls


def required(func):
    """Mark a method as required (must be overridden)."""
    func._is_required = True
    return func


class BaseService(metaclass=StrictAbstractMeta, abstract=True):
    @required
    def start(self) -> None: ...

    @required
    def stop(self) -> None: ...

    @required
    def health_check(self) -> bool: ...


class WorkingService(BaseService):
    """This works because all required methods are implemented."""
    def start(self) -> None:
        print("Started")

    def stop(self) -> None:
        print("Stopped")

    def health_check(self) -> bool:
        return True


# This would FAIL at class definition time:
# class BrokenService(BaseService):
#     def start(self) -> None: ...
#     # Missing stop() and health_check()
#     # TypeError: BrokenService must implement stop()


# ---------------------------------------------------------------------------
# 5. Automatic method wrapping (AOP-style)
# ---------------------------------------------------------------------------
class LoggedMeta(type):
    """Metaclass that automatically wraps all public methods with logging.

    This is true AOP (Aspect-Oriented Programming) — cross-cutting
    concerns applied transparently at class creation.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: dict,
        *,
        log_level: int = logging.DEBUG,
        **kwargs: Any,
    ) -> LoggedMeta:
        import functools

        for attr_name, attr_value in list(namespace.items()):
            if (
                callable(attr_value)
                and not attr_name.startswith("_")
                and not isinstance(attr_value, (staticmethod, classmethod))
            ):
                original = attr_value

                @functools.wraps(original)
                def wrapper(self, *args, _fn=original, _name=attr_name, **kw):
                    logger.log(
                        log_level,
                        "%s.%s called with args=%s kwargs=%s",
                        type(self).__name__, _name, args, kw,
                    )
                    result = _fn(self, *args, **kw)
                    logger.log(
                        log_level,
                        "%s.%s returned %r",
                        type(self).__name__, _name, result,
                    )
                    return result

                namespace[attr_name] = wrapper

        return super().__new__(mcs, name, bases, namespace, **kwargs)


class PaymentService(metaclass=LoggedMeta, log_level=logging.INFO):
    def charge(self, amount: float, currency: str = "USD") -> dict:
        return {"status": "charged", "amount": amount}

    def refund(self, transaction_id: str) -> dict:
        return {"status": "refunded", "id": transaction_id}


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    # Ordered fields
    print("=== Ordered Fields ===")
    print(f"Field order: {RegistrationForm.get_fields()}")

    # Singleton
    print("\\n=== Singleton ===")
    db1 = DatabaseConnection("postgres://prod/db")
    db2 = DatabaseConnection("postgres://other/db")
    print(f"Same instance: {db1 is db2}")  # True
    print(f"DSN: {db1.dsn}")  # First DSN wins

    # Enum-like
    print("\\n=== Enum-like ===")
    print(f"Color.RED = {Color.RED}")
    print(f"'#FF0000' in Color: {'#FF0000' in Color}")
    print(f"Members: {list(Color)}")

    # Strict abstract
    print("\\n=== Strict Abstract ===")
    svc = WorkingService()
    svc.start()
    print(f"Health: {svc.health_check()}")

    # Auto-logged
    print("\\n=== Auto-logged ===")
    pay = PaymentService()
    pay.charge(99.99, currency="EUR")
    pay.refund("TXN-123")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
```

**When you need a real metaclass vs `__init_subclass__`:**

| Need | `__init_subclass__` | Metaclass |
|---|---|---|
| Register subclasses | Yes | Overkill |
| Add class methods | Yes | Overkill |
| Control namespace (`__prepare__`) | No | Yes |
| Class-level `__getattr__` | No | Yes |
| Thread-safe singleton (`__call__`) | Hacky | Clean |
| Fail at class definition (not instantiation) | Partially | Yes |
| AOP method wrapping | Partially | Clean |
| Modify the class dict before creation | No | Yes (`__new__`) |

**Key patterns:**

- **`__prepare__`** — return a custom dict that tracks insertion order, counts accesses, or restricts keys (metaclass-only)
- **`__call__` on metaclass** — intercept instance creation for singletons, pooling, or proxying
- **Class-level `__getattr__`** — handle missing attributes on the class itself (not instances)
- **AOP wrapping** — automatically wrap all methods with logging, tracing, or error handling at class creation
- **Rule of thumb**: prefer `__init_subclass__` for 90% of cases; use metaclasses only for `__prepare__`, `__call__`, or class-level dunder methods'''
    ),
]
