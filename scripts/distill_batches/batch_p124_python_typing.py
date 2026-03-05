"""Python typing — advanced type hints, generics, protocols, and type narrowing."""

PAIRS = [
    (
        "python/typing-advanced",
        "Show advanced Python typing patterns: generics, overloads, TypeVar bounds, ParamSpec, and type narrowing.",
        '''Advanced Python typing patterns:

```python
from typing import (
    TypeVar, Generic, Protocol, runtime_checkable,
    overload, TypeAlias, TypeGuard, Never, Self,
    ParamSpec, Concatenate, Callable, Awaitable,
    Literal, Annotated, get_type_hints,
)
from dataclasses import dataclass


# --- Bounded TypeVar ---

from collections.abc import Sequence

T = TypeVar("T")
Numeric = TypeVar("Numeric", int, float)  # Constrained to int or float
Comparable = TypeVar("Comparable", bound="SupportsLessThan")

def clamp(value: Numeric, low: Numeric, high: Numeric) -> Numeric:
    return max(low, min(high, value))

clamp(5, 1, 10)      # int
clamp(3.14, 0.0, 1.0)  # float


# --- Generic classes ---

class Stack(Generic[T]):
    def __init__(self) -> None:
        self._items: list[T] = []

    def push(self, item: T) -> None:
        self._items.append(item)

    def pop(self) -> T:
        if not self._items:
            raise IndexError("Stack is empty")
        return self._items.pop()

    def peek(self) -> T:
        if not self._items:
            raise IndexError("Stack is empty")
        return self._items[-1]

    def __len__(self) -> int:
        return len(self._items)

# Type-safe usage:
int_stack: Stack[int] = Stack()
int_stack.push(42)
value: int = int_stack.pop()


# --- Self type (Python 3.11+) ---

class Builder:
    def __init__(self) -> None:
        self._name = ""
        self._value = 0

    def name(self, name: str) -> Self:
        self._name = name
        return self

    def value(self, value: int) -> Self:
        self._value = value
        return self


# --- @overload for different return types ---

@overload
def parse(data: str, as_list: Literal[True]) -> list[str]: ...
@overload
def parse(data: str, as_list: Literal[False] = ...) -> str: ...

def parse(data: str, as_list: bool = False) -> str | list[str]:
    if as_list:
        return data.split(",")
    return data.strip()

# Type checker knows:
result1: str = parse("hello")              # str
result2: list[str] = parse("a,b,c", True)  # list[str]


# --- TypeGuard (type narrowing) ---

def is_string_list(val: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(item, str) for item in val)

def process(items: list[object]) -> None:
    if is_string_list(items):
        # Type checker now knows items is list[str]
        joined: str = ",".join(items)
        print(joined)


# --- ParamSpec (preserving function signatures) ---

P = ParamSpec("P")
R = TypeVar("R")

def with_logging(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator that preserves the wrapped function's type signature."""
    import functools
    import logging

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logging.info("Calling %s", func.__name__)
        result = func(*args, **kwargs)
        logging.info("Result: %s", result)
        return result

    return wrapper

@with_logging
def add(a: int, b: int) -> int:
    return a + b

# Type checker preserves signature: add(a: int, b: int) -> int


# --- Callable types ---

# Simple callback
Handler = Callable[[str, int], bool]

# Async callback
AsyncHandler = Callable[[str], Awaitable[dict]]

# With specific parameter names (use Protocol)
class RequestHandler(Protocol):
    async def __call__(self, path: str, *, method: str = "GET") -> dict: ...


# --- Type aliases ---

UserId = TypeAlias = str
JsonDict: TypeAlias = dict[str, "JsonValue"]
JsonValue: TypeAlias = str | int | float | bool | None | JsonDict | list["JsonValue"]

# Annotated (metadata for validation frameworks)
from typing import Annotated

PositiveInt = Annotated[int, "must be > 0"]
Email = Annotated[str, "valid email address"]
Password = Annotated[str, "min_length=12"]


# --- Never (functions that never return) ---

def assert_never(value: Never) -> Never:
    """Exhaustiveness check for match/if-else chains."""
    raise AssertionError(f"Unexpected value: {value}")

class Shape:
    pass
class Circle(Shape):
    radius: float
class Square(Shape):
    side: float

def area(shape: Circle | Square) -> float:
    if isinstance(shape, Circle):
        return 3.14159 * shape.radius ** 2
    elif isinstance(shape, Square):
        return shape.side ** 2
    else:
        assert_never(shape)  # Type error if new Shape subclass added
```

Python typing patterns:
1. **Bounded `TypeVar`** — constrain generic types to specific types or protocols
2. **`@overload`** — different return types based on argument values
3. **`TypeGuard`** — custom type narrowing functions for `isinstance`-like checks
4. **`ParamSpec`** — preserve decorated function signatures in type checker
5. **`Never` + `assert_never()`** — exhaustiveness checking for union types'''
    ),
    (
        "python/pydantic-patterns",
        "Show advanced Pydantic patterns: custom validators, computed fields, serialization, and model inheritance.",
        '''Advanced Pydantic patterns:

```python
from pydantic import (
    BaseModel, Field, field_validator, model_validator,
    computed_field, ConfigDict, SecretStr,
    field_serializer, model_serializer,
)
from datetime import datetime, timezone
from typing import Annotated, Literal
from enum import StrEnum


# --- Model with validation ---

class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,  # Auto-strip strings
        strict=True,                # No type coercion
    )

    username: Annotated[str, Field(
        min_length=3, max_length=30,
        pattern=r"^[a-zA-Z0-9_]+$",
        examples=["alice_smith"],
    )]
    email: str
    password: SecretStr = Field(min_length=12)
    role: UserRole = UserRole.USER
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.lower()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return [tag.lower().strip() for tag in v if tag.strip()]

    @model_validator(mode="after")
    def check_admin_constraints(self) -> "CreateUserRequest":
        if self.role == UserRole.ADMIN and len(self.password.get_secret_value()) < 16:
            raise ValueError("Admin password must be at least 16 characters")
        return self


# --- Computed fields and serialization ---

class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # ORM mode

    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    role: UserRole
    created_at: datetime
    is_active: bool = True

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @computed_field
    @property
    def is_new(self) -> bool:
        delta = datetime.now(timezone.utc) - self.created_at
        return delta.days < 30

    @field_serializer("created_at")
    def serialize_datetime(self, v: datetime) -> str:
        return v.isoformat()


# --- Discriminated unions ---

class EmailNotification(BaseModel):
    type: Literal["email"] = "email"
    to: str
    subject: str
    body: str

class SMSNotification(BaseModel):
    type: Literal["sms"] = "sms"
    phone: str
    message: str

class PushNotification(BaseModel):
    type: Literal["push"] = "push"
    device_token: str
    title: str
    body: str

# Discriminated by "type" field
Notification = EmailNotification | SMSNotification | PushNotification


class NotificationBatch(BaseModel):
    notifications: list[Notification] = Field(discriminator="type")

# Automatically deserializes to correct type:
batch = NotificationBatch.model_validate({
    "notifications": [
        {"type": "email", "to": "a@b.com", "subject": "Hi", "body": "Hello"},
        {"type": "sms", "phone": "+1234567890", "message": "Hello"},
    ]
})
# batch.notifications[0] is EmailNotification
# batch.notifications[1] is SMSNotification


# --- Model inheritance ---

class TimestampMixin(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SoftDeleteMixin(BaseModel):
    is_deleted: bool = False
    deleted_at: datetime | None = None

class BaseEntity(TimestampMixin, SoftDeleteMixin):
    id: int

class Product(BaseEntity):
    name: str
    price: float = Field(gt=0)
    category: str


# --- Nested models with custom serialization ---

class Address(BaseModel):
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"

class Company(BaseModel):
    name: str
    address: Address
    employees: list[User] = []

    @model_serializer
    def serialize(self) -> dict:
        """Custom serialization (e.g., for API response)."""
        return {
            "name": self.name,
            "location": f"{self.address.city}, {self.address.state}",
            "employee_count": len(self.employees),
            "employees": [
                {"id": e.id, "name": e.full_name, "role": e.role}
                for e in self.employees
            ],
        }
```

Pydantic patterns:
1. **`field_validator`** — per-field validation with `@classmethod` decorator
2. **`model_validator(mode="after")`** — cross-field validation after all fields parsed
3. **`computed_field`** — derived properties included in serialization
4. **Discriminated unions** — `Field(discriminator="type")` for polymorphic deserialization
5. **`model_config = ConfigDict(from_attributes=True)`** — create from ORM objects'''
    ),
]
"""
