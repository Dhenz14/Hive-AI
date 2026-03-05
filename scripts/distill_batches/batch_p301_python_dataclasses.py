"""Python dataclasses/attrs: frozen, validators, slots, post_init, converters, inheritance patterns."""

PAIRS = [
    (
        "python/dataclasses/frozen-slots-patterns",
        "How do I build immutable, memory-efficient data models with Python dataclasses? Show frozen, slots, field validators, and post_init patterns.",
        '''Python 3.10+ dataclasses with `frozen=True` and `slots=True` give you immutable, memory-efficient value objects that are hashable by default and play well with type checkers.

```python
"""Immutable data models with dataclasses — frozen, slots,
post_init validation, custom fields, and derived attributes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum, auto
from typing import Self
from uuid import UUID, uuid4


# ---------------------------------------------------------------------------
# 1. Basic frozen + slots value object
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Money:
    """Immutable monetary value with currency."""
    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        # Validation in frozen dataclasses requires object.__setattr__
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        if self.amount < 0:
            raise ValueError(f"Amount must be non-negative, got {self.amount}")
        if len(self.currency) != 3:
            raise ValueError(f"Currency must be 3-letter ISO code, got {self.currency!r}")

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, factor: int | float | Decimal) -> Money:
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def format(self, locale: str = "en_US") -> str:
        sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(self.currency, self.currency)
        return f"{sym}{self.amount:,.2f}"


# ---------------------------------------------------------------------------
# 2. Complex model with derived fields and factory methods
# ---------------------------------------------------------------------------
class OrderStatus(StrEnum):
    PENDING = auto()
    CONFIRMED = auto()
    SHIPPED = auto()
    DELIVERED = auto()
    CANCELLED = auto()


@dataclass(frozen=True, slots=True)
class Address:
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"

    def __post_init__(self) -> None:
        if self.country == "US" and not re.match(r"^\d{5}(-\d{4})?$", self.zip_code):
            raise ValueError(f"Invalid US zip code: {self.zip_code!r}")


@dataclass(frozen=True, slots=True)
class LineItem:
    product_id: str
    name: str
    quantity: int
    unit_price: Money

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError(f"Quantity must be >= 1, got {self.quantity}")

    @property
    def total(self) -> Money:
        return self.unit_price * self.quantity


@dataclass(frozen=True, slots=True)
class Order:
    """Immutable order with derived computed fields.

    Uses __post_init__ for validation and field defaults that depend
    on other fields.
    """
    customer_id: str
    items: tuple[LineItem, ...]  # tuple for hashability with frozen
    shipping_address: Address
    order_id: UUID = field(default_factory=uuid4)
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("Order must have at least one item")
        # Ensure items is a tuple (for hashability)
        if isinstance(self.items, list):
            object.__setattr__(self, "items", tuple(self.items))

    @property
    def subtotal(self) -> Money:
        total = Money(Decimal("0"))
        for item in self.items:
            total = total + item.total
        return total

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)

    def with_status(self, new_status: OrderStatus) -> Self:
        """Return a new Order with updated status (immutable update)."""
        return replace(self, status=new_status)

    def add_item(self, item: LineItem) -> Self:
        """Return a new Order with an additional item."""
        return replace(self, items=self.items + (item,))

    def cancel(self) -> Self:
        if self.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise ValueError(f"Cannot cancel order in {self.status} status")
        return self.with_status(OrderStatus.CANCELLED)


# ---------------------------------------------------------------------------
# 3. Generic container with field metadata
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Paginated[T]:
    """Generic paginated response container."""
    items: tuple[T, ...]
    total: int
    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.page_size < 1 or self.page_size > 100:
            raise ValueError("page_size must be between 1 and 100")

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    def map[U](self, fn: callable) -> Paginated[U]:
        return replace(self, items=tuple(fn(item) for item in self.items))


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
def main() -> None:
    # Money
    price = Money(Decimal("29.99"))
    tax = Money(Decimal("2.40"))
    total = price + tax
    print(f"Total: {total.format()}")  # $32.39

    # Order
    addr = Address("123 Main St", "Springfield", "IL", "62704")
    items = (
        LineItem("SKU-001", "Widget", 2, Money(Decimal("9.99"))),
        LineItem("SKU-002", "Gadget", 1, Money(Decimal("24.99"))),
    )
    order = Order(customer_id="CUST-42", items=items, shipping_address=addr)
    print(f"Order {order.order_id}: {order.item_count} items, {order.subtotal.format()}")

    # Immutable update
    confirmed = order.with_status(OrderStatus.CONFIRMED)
    print(f"Status: {confirmed.status}")
    print(f"Original unchanged: {order.status}")

    # Paginated
    page = Paginated(items=items, total=100, page=1, page_size=20)
    print(f"Page 1/{page.total_pages}, has_next={page.has_next}")


if __name__ == "__main__":
    main()
```

**Key patterns:**

- **`frozen=True`** makes instances immutable and hashable (can be dict keys / set members)
- **`slots=True`** reduces memory by 30-40% and prevents accidental attribute creation
- **`__post_init__`** for validation — use `object.__setattr__` to coerce values on frozen instances
- **`replace()`** for immutable updates — returns a copy with specified fields changed
- **Tuples over lists** — use `tuple[T, ...]` instead of `list[T]` in frozen dataclasses for hashability
- **`@property`** for derived values — computed attributes that do not need storage
- **Generic dataclasses** — Python 3.12+ syntax `class Paginated[T]` for type-safe containers'''
    ),
    (
        "python/attrs/validators-converters",
        "Show me how to use attrs (the library) with validators, converters, and advanced patterns like evolve, factory defaults, and pipeline validators.",
        '''attrs is more feature-rich than stdlib dataclasses and offers built-in validators, converters, and a pipeline system. It is the preferred choice for complex domain models.

```python
"""attrs patterns — validators, converters, evolve, factory fields,
pipeline validation, and serialization hooks."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum, auto
from typing import Any
from uuid import UUID, uuid4

import attrs
from attrs import define, field, validators, Factory


# ---------------------------------------------------------------------------
# Custom validators
# ---------------------------------------------------------------------------
def validate_email(instance: Any, attribute: attrs.Attribute, value: str) -> None:
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, value):
        raise ValueError(f"Invalid email: {value!r}")


def validate_range(min_val: float, max_val: float):
    """Factory for range validators."""
    def _validator(instance: Any, attribute: attrs.Attribute, value: float) -> None:
        if not (min_val <= value <= max_val):
            raise ValueError(
                f"{attribute.name} must be between {min_val} and {max_val}, "
                f"got {value}"
            )
    return _validator


# ---------------------------------------------------------------------------
# Custom converters
# ---------------------------------------------------------------------------
def to_decimal(value: Any) -> Decimal:
    """Convert various types to Decimal."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"Cannot convert {value!r} to Decimal") from e


def normalize_phone(value: str) -> str:
    """Strip non-digit characters from phone numbers."""
    digits = re.sub(r"[^\d+]", "", value)
    if len(digits) == 10:
        return f"+1{digits}"
    return digits


# ---------------------------------------------------------------------------
# Domain models with attrs
# ---------------------------------------------------------------------------
class MembershipTier(StrEnum):
    FREE = auto()
    BASIC = auto()
    PREMIUM = auto()
    ENTERPRISE = auto()


@define
class PhoneNumber:
    """Phone number with automatic normalization."""
    number: str = field(converter=normalize_phone)
    country_code: str = field(default="US")
    verified: bool = field(default=False)

    @number.validator
    def _validate_number(self, attribute: attrs.Attribute, value: str) -> None:
        if len(re.sub(r"[^\d]", "", value)) < 10:
            raise ValueError(f"Phone number too short: {value!r}")


@define
class UserProfile:
    """User profile demonstrating attrs validators and converters."""
    # Required fields with validators
    username: str = field(validator=[
        validators.instance_of(str),
        validators.min_len(3),
        validators.max_len(32),
        validators.matches_re(r"^[a-zA-Z0-9_-]+$"),
    ])
    email: str = field(validator=validate_email)

    # Optional fields with converters and defaults
    display_name: str = field(default="")
    phone: PhoneNumber | None = field(default=None)
    tier: MembershipTier = field(
        default=MembershipTier.FREE,
        converter=MembershipTier,
    )

    # Auto-generated fields
    user_id: UUID = field(factory=uuid4)
    created_at: datetime = field(
        factory=lambda: datetime.now(timezone.utc),
    )

    # Computed defaults using Factory with `takes_self`
    slug: str = field(default=Factory(
        lambda self: self.username.lower().replace(" ", "-"),
        takes_self=True,
    ))

    def __attrs_post_init__(self) -> None:
        if not self.display_name:
            object.__setattr__(self, "display_name", self.username)


# ---------------------------------------------------------------------------
# Frozen (immutable) attrs class with evolve
# ---------------------------------------------------------------------------
@define(frozen=True)
class PricingRule:
    """Immutable pricing rule with evolve for updates."""
    name: str
    base_price: Decimal = field(converter=to_decimal)
    discount_pct: float = field(
        default=0.0,
        validator=validate_range(0.0, 100.0),
    )
    min_quantity: int = field(default=1, validator=validators.ge(1))
    max_quantity: int | None = field(default=None)
    active: bool = field(default=True)

    @property
    def effective_price(self) -> Decimal:
        multiplier = Decimal(1) - Decimal(str(self.discount_pct)) / Decimal(100)
        return (self.base_price * multiplier).quantize(Decimal("0.01"))

    def with_discount(self, pct: float) -> PricingRule:
        return attrs.evolve(self, discount_pct=pct)

    def deactivate(self) -> PricingRule:
        return attrs.evolve(self, active=False)


# ---------------------------------------------------------------------------
# Inheritance with attrs
# ---------------------------------------------------------------------------
@define
class BaseEvent:
    """Base event with common fields."""
    event_id: UUID = field(factory=uuid4)
    timestamp: datetime = field(factory=lambda: datetime.now(timezone.utc))
    source: str = field(default="system")


@define
class UserCreatedEvent(BaseEvent):
    """Event emitted when a user is created."""
    user_id: UUID = field(factory=uuid4)
    username: str = field(default="")
    tier: MembershipTier = field(default=MembershipTier.FREE)


@define
class OrderPlacedEvent(BaseEvent):
    """Event emitted when an order is placed."""
    order_id: UUID = field(factory=uuid4)
    total: Decimal = field(converter=to_decimal, default=Decimal("0"))
    item_count: int = field(default=0, validator=validators.ge(0))


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def to_dict(instance: Any) -> dict[str, Any]:
    """Serialize an attrs instance to a JSON-compatible dict."""
    result = {}
    for a in attrs.fields(type(instance)):
        value = getattr(instance, a.name)
        if isinstance(value, (UUID, Decimal)):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, StrEnum):
            value = value.value
        elif attrs.has(type(value)):
            value = to_dict(value)
        result[a.name] = value
    return result


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
def main() -> None:
    # Create user
    user = UserProfile(
        username="alice_dev",
        email="alice@example.com",
        phone=PhoneNumber("(555) 123-4567"),
        tier="premium",  # converter handles string -> enum
    )
    print(f"User: {user.display_name} ({user.tier})")
    print(f"Phone: {user.phone.number}")
    print(f"Slug: {user.slug}")

    # Pricing with evolve
    rule = PricingRule("Standard", base_price=99.99, discount_pct=10)
    print(f"Price: ${rule.effective_price}")

    holiday_rule = rule.with_discount(25.0)
    print(f"Holiday price: ${holiday_rule.effective_price}")

    # Serialization
    event = UserCreatedEvent(
        username=user.username,
        user_id=user.user_id,
        tier=user.tier,
        source="api",
    )
    print(f"Event dict: {to_dict(event)}")


if __name__ == "__main__":
    main()
```

**Comparison: dataclasses vs attrs**

| Feature | dataclasses | attrs |
|---|---|---|
| Built-in validators | No (manual in `__post_init__`) | Yes (`validators` module) |
| Converters | No | Yes (per-field) |
| `evolve()` | `replace()` | `attrs.evolve()` |
| `Factory(takes_self=True)` | No | Yes |
| Slots | `slots=True` (3.10+) | Default since `@define` |
| Frozen | `frozen=True` | `frozen=True` on `@define` |
| Third-party | stdlib | pip install attrs |

**Key patterns:**

- **Validator chaining** — pass a list of validators to apply multiple checks in order
- **Converter functions** — automatically transform input values (e.g., string to Decimal, normalize phone)
- **`Factory(takes_self=True)`** — compute defaults that depend on other fields
- **`attrs.evolve()`** — immutable update, like `dataclasses.replace()` but with validator re-runs
- **Inheritance** — child classes inherit parent fields naturally; validators and converters are preserved'''
    ),
    (
        "python/dataclasses/pydantic-comparison",
        "When should I use dataclasses vs Pydantic v2 vs attrs? Show equivalent models in each and compare performance, features, and use cases.",
        '''Choosing between dataclasses, attrs, and Pydantic depends on your use case. Here is an equivalent model implemented three ways with benchmarks and feature comparison.

```python
"""Side-by-side comparison: dataclasses vs attrs vs Pydantic v2
for the same domain model — a user registration form."""

from __future__ import annotations

import re
import timeit
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID, uuid4

# --- stdlib dataclasses ---
@dataclass(frozen=True, slots=True)
class UserDC:
    """User model with stdlib dataclasses."""
    username: str
    email: str
    age: int
    balance: Decimal = Decimal("0.00")
    user_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (3 <= len(self.username) <= 32):
            raise ValueError("username must be 3-32 chars")
        if not re.match(r"^[\w.+-]+@[\w.-]+\.[\w]{2,}$", self.email):
            raise ValueError(f"Invalid email: {self.email}")
        if not (0 <= self.age <= 150):
            raise ValueError(f"Invalid age: {self.age}")


# --- attrs ---
import attrs
from attrs import define, field as afield, validators

def _validate_email_attrs(inst: Any, attr: attrs.Attribute, val: str) -> None:
    if not re.match(r"^[\w.+-]+@[\w.-]+\.[\w]{2,}$", val):
        raise ValueError(f"Invalid email: {val}")

@define(frozen=True)
class UserAttrs:
    """User model with attrs."""
    username: str = afield(validator=[
        validators.instance_of(str),
        validators.min_len(3),
        validators.max_len(32),
    ])
    email: str = afield(validator=_validate_email_attrs)
    age: int = afield(validator=[validators.ge(0), validators.le(150)])
    balance: Decimal = afield(
        default=Decimal("0.00"),
        converter=lambda v: Decimal(str(v)) if not isinstance(v, Decimal) else v,
    )
    user_id: UUID = afield(factory=uuid4)
    created_at: datetime = afield(
        factory=lambda: datetime.now(timezone.utc),
    )
    tags: tuple[str, ...] = ()


# --- Pydantic v2 ---
from pydantic import BaseModel, Field, field_validator, ConfigDict

class UserPydantic(BaseModel):
    """User model with Pydantic v2."""
    model_config = ConfigDict(frozen=True)

    username: Annotated[str, Field(min_length=3, max_length=32)]
    email: str
    age: Annotated[int, Field(ge=0, le=150)]
    balance: Decimal = Decimal("0.00")
    user_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    tags: tuple[str, ...] = ()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[\w.+-]+@[\w.-]+\.[\w]{2,}$", v):
            raise ValueError(f"Invalid email: {v}")
        return v


# ---------------------------------------------------------------------------
# Serialization comparison
# ---------------------------------------------------------------------------
def serialize_dataclass(user: UserDC) -> dict:
    """Manual serialization for dataclasses."""
    from dataclasses import asdict
    d = asdict(user)
    d["user_id"] = str(d["user_id"])
    d["created_at"] = d["created_at"].isoformat()
    d["balance"] = str(d["balance"])
    return d


def serialize_attrs(user: UserAttrs) -> dict:
    """Manual serialization for attrs."""
    d = attrs.asdict(user)
    d["user_id"] = str(d["user_id"])
    d["created_at"] = d["created_at"].isoformat()
    d["balance"] = str(d["balance"])
    return d


def serialize_pydantic(user: UserPydantic) -> dict:
    """Pydantic has built-in serialization."""
    return user.model_dump(mode="json")


# ---------------------------------------------------------------------------
# JSON parsing comparison (Pydantic excels here)
# ---------------------------------------------------------------------------
def from_json_dataclass(data: dict) -> UserDC:
    """Parse JSON dict into dataclass — manual type coercion."""
    return UserDC(
        username=data["username"],
        email=data["email"],
        age=int(data["age"]),
        balance=Decimal(data["balance"]),
        user_id=UUID(data["user_id"]),
        created_at=datetime.fromisoformat(data["created_at"]),
        tags=tuple(data.get("tags", ())),
    )


def from_json_pydantic(data: dict) -> UserPydantic:
    """Pydantic handles type coercion automatically."""
    return UserPydantic.model_validate(data)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------
def benchmark() -> None:
    test_data = {
        "username": "alice",
        "email": "alice@example.com",
        "age": 30,
        "balance": "100.50",
    }

    n = 10_000

    dc_time = timeit.timeit(
        lambda: UserDC(**test_data), number=n
    )
    attrs_time = timeit.timeit(
        lambda: UserAttrs(**test_data), number=n
    )
    pydantic_time = timeit.timeit(
        lambda: UserPydantic(**test_data), number=n
    )

    print(f"Creation ({n} iterations):")
    print(f"  dataclasses: {dc_time:.3f}s")
    print(f"  attrs:       {attrs_time:.3f}s")
    print(f"  Pydantic v2: {pydantic_time:.3f}s")

    # Serialization
    dc_user = UserDC(**test_data)
    attrs_user = UserAttrs(**test_data)
    pydantic_user = UserPydantic(**test_data)

    dc_ser = timeit.timeit(lambda: serialize_dataclass(dc_user), number=n)
    attrs_ser = timeit.timeit(lambda: serialize_attrs(attrs_user), number=n)
    pydantic_ser = timeit.timeit(lambda: serialize_pydantic(pydantic_user), number=n)

    print(f"\\nSerialization ({n} iterations):")
    print(f"  dataclasses: {dc_ser:.3f}s")
    print(f"  attrs:       {attrs_ser:.3f}s")
    print(f"  Pydantic v2: {pydantic_ser:.3f}s")


if __name__ == "__main__":
    benchmark()
```

**Feature comparison:**

| Feature | dataclasses | attrs | Pydantic v2 |
|---|---|---|---|
| Validation | Manual `__post_init__` | Built-in validators | Built-in + JSON Schema |
| Type coercion | No | Converters | Automatic |
| JSON serialization | Manual | Manual | `model_dump(mode="json")` |
| JSON deserialization | Manual | Manual | `model_validate()` |
| OpenAPI / JSON Schema | No | No | `model_json_schema()` |
| Performance (creation) | Fastest | Fast | Moderate (Rust core) |
| Performance (serialize) | Manual = varies | Manual = varies | Fast (Rust core) |
| Memory (slots) | `slots=True` | Default with `@define` | No slots |
| Frozen/immutable | `frozen=True` | `frozen=True` | `ConfigDict(frozen=True)` |
| Stdlib | Yes | No (pip) | No (pip) |
| Best for | Internal DTOs | Domain models | API boundaries |

**When to use each:**

- **dataclasses** — simple internal DTOs, configuration objects, when you want zero dependencies
- **attrs** — complex domain models with rich validation, converters, and `Factory(takes_self=True)`
- **Pydantic v2** — API request/response models, settings management, anything that needs JSON Schema or automatic type coercion from external input'''
    ),
    (
        "python/dataclasses/inheritance-mixins",
        "What are the best patterns for dataclass inheritance and mixins? Show how to handle field ordering, MRO issues, and composition vs inheritance.",
        '''Dataclass inheritance has specific rules around field ordering (fields with defaults must come after those without) and MRO (Method Resolution Order). Here are the patterns that work cleanly.

```python
"""Dataclass inheritance and composition patterns — solving field
ordering, MRO issues, and when to prefer composition."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, ClassVar, Self
from uuid import UUID, uuid4


# ---------------------------------------------------------------------------
# Problem: naive inheritance breaks field ordering
# ---------------------------------------------------------------------------
# This FAILS because parent has default fields before child's required fields:
#
# @dataclass
# class Base:
#     id: UUID = field(default_factory=uuid4)
#
# @dataclass
# class Child(Base):
#     name: str  # ERROR: non-default after default
#
# Solution 1: All parent fields have defaults, or use kw_only


# ---------------------------------------------------------------------------
# Pattern 1: kw_only=True (Python 3.10+) — cleanest solution
# ---------------------------------------------------------------------------
@dataclass(kw_only=True, slots=True)
class TimestampMixin:
    """Mixin that adds timestamp fields. kw_only avoids ordering issues."""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(kw_only=True, slots=True)
class IdentityMixin:
    """Mixin that adds an ID field."""
    id: UUID = field(default_factory=uuid4)


@dataclass(kw_only=True, slots=True)
class AuditMixin:
    """Mixin that adds audit fields."""
    created_by: str = ""
    updated_by: str = ""
    version: int = 1


@dataclass(kw_only=True, slots=True)
class User(IdentityMixin, TimestampMixin, AuditMixin):
    """Full user model combining multiple mixins.

    kw_only=True on all classes means field order does not matter.
    """
    username: str
    email: str
    is_active: bool = True

    def touch(self, by: str) -> None:
        object.__setattr__(self, "updated_at", datetime.now(timezone.utc))
        object.__setattr__(self, "updated_by", by)
        object.__setattr__(self, "version", self.version + 1)


# ---------------------------------------------------------------------------
# Pattern 2: Abstract base with __init_subclass__
# ---------------------------------------------------------------------------
@dataclass(kw_only=True)
class BaseEntity(ABC):
    """Abstract base entity with registry and lifecycle hooks."""
    _registry: ClassVar[dict[str, type]] = {}

    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "__abstractmethods__", set()):
            BaseEntity._registry[cls.__name__] = cls

    @abstractmethod
    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        ...

    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    @classmethod
    def get_registered(cls) -> dict[str, type]:
        return dict(cls._registry)


@dataclass(kw_only=True)
class Product(BaseEntity):
    name: str
    price_cents: int
    sku: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if len(self.name) < 1:
            errors.append("name is required")
        if self.price_cents < 0:
            errors.append("price must be non-negative")
        if not self.sku:
            errors.append("sku is required")
        return errors


@dataclass(kw_only=True)
class Category(BaseEntity):
    name: str
    parent_id: UUID | None = None

    def validate(self) -> list[str]:
        return ["name is required"] if not self.name else []


# ---------------------------------------------------------------------------
# Pattern 3: Composition over inheritance (preferred for complex models)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Metadata:
    """Reusable metadata component."""
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    tags: tuple[str, ...] = ()

    def bump_version(self) -> Metadata:
        from dataclasses import replace
        return replace(
            self,
            version=self.version + 1,
            updated_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True, slots=True)
class Permissions:
    """Reusable permissions component."""
    owner_id: str
    read_roles: frozenset[str] = frozenset({"admin"})
    write_roles: frozenset[str] = frozenset({"admin"})

    def can_read(self, user_roles: set[str]) -> bool:
        return bool(user_roles & self.read_roles)

    def can_write(self, user_roles: set[str]) -> bool:
        return bool(user_roles & self.write_roles)


@dataclass(frozen=True, slots=True)
class Document:
    """Document using composition instead of inheritance.

    Each concern (metadata, permissions, content) is a separate component.
    """
    title: str
    body: str
    meta: Metadata = field(default_factory=Metadata)
    perms: Permissions = field(default_factory=lambda: Permissions(owner_id="system"))

    def update_body(self, new_body: str, by: str) -> Document:
        from dataclasses import replace
        return replace(
            self,
            body=new_body,
            meta=self.meta.bump_version(),
        )


# ---------------------------------------------------------------------------
# Pattern 4: Serialization mixin using __init_subclass__
# ---------------------------------------------------------------------------
@dataclass
class SerializableMixin:
    """Mixin that adds to_dict/from_dict using field introspection."""

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, (UUID, datetime)):
                value = str(value)
            elif hasattr(value, "to_dict"):
                value = value.to_dict()
            result[f.name] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Construct from a dict, handling basic type conversions."""
        field_names = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


@dataclass(kw_only=True)
class APIResponse(SerializableMixin):
    status: str = "ok"
    data: dict[str, Any] = field(default_factory=dict)
    request_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    # Mixins with kw_only
    user = User(username="alice", email="alice@example.com", created_by="admin")
    print(f"User: {user.username}, version={user.version}")
    user.touch(by="system")
    print(f"After touch: version={user.version}")

    # Abstract base with registry
    p = Product(name="Widget", price_cents=999, sku="WDG-001")
    print(f"Product valid: {p.is_valid()}")
    print(f"Registered entities: {list(BaseEntity.get_registered().keys())}")

    # Composition
    doc = Document(title="Hello", body="World")
    updated = doc.update_body("New content", by="alice")
    print(f"Doc v{doc.meta.version} -> v{updated.meta.version}")

    # Serialization mixin
    resp = APIResponse(data={"items": [1, 2, 3]})
    print(resp.to_json())


if __name__ == "__main__":
    main()
```

**Key patterns:**

- **`kw_only=True`** — solves the field-ordering problem in inheritance by making all fields keyword-only
- **Mixins** — small, focused dataclasses that add specific concerns (timestamps, identity, audit)
- **`__init_subclass__`** — register subclasses automatically for factory patterns or plugin systems
- **Composition over inheritance** — embed components (`Metadata`, `Permissions`) as fields instead of inheriting from multiple bases
- **`SerializableMixin`** — use `fields()` introspection for generic serialization across all dataclass subclasses
- **Abstract base classes** — combine `ABC` with `@dataclass` for validated entity hierarchies'''
    ),
    (
        "python/dataclasses/field-descriptors",
        "How do I create custom field descriptors and validated fields for dataclasses? Show patterns for lazy fields, computed properties, and change tracking.",
        '''Custom descriptors let you add behavior to dataclass fields — lazy initialization, validation on set, and change tracking — while keeping the clean dataclass API.

```python
"""Custom descriptors for dataclasses — lazy fields, validated
properties, change tracking, and computed columns."""

from __future__ import annotations

import functools
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Generic, TypeVar, overload

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Descriptor 1: Validated field (validates on every set)
# ---------------------------------------------------------------------------
class ValidatedField(Generic[T]):
    """Descriptor that runs a validator on every assignment.

    Works with non-frozen dataclasses.

    Usage:
        class User:
            age = ValidatedField(validator=lambda v: 0 <= v <= 150)
    """

    def __init__(
        self,
        *,
        validator: Callable[[T], bool] | None = None,
        converter: Callable[[Any], T] | None = None,
        error_msg: str = "Validation failed",
    ) -> None:
        self.validator = validator
        self.converter = converter
        self.error_msg = error_msg
        self.attr_name: str = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = f"_{name}"

    @overload
    def __get__(self, obj: None, objtype: type) -> ValidatedField[T]: ...
    @overload
    def __get__(self, obj: object, objtype: type) -> T: ...

    def __get__(self, obj: object | None, objtype: type) -> Any:
        if obj is None:
            return self
        return getattr(obj, self.attr_name, None)

    def __set__(self, obj: object, value: Any) -> None:
        if self.converter is not None:
            value = self.converter(value)
        if self.validator is not None and not self.validator(value):
            raise ValueError(f"{self.attr_name[1:]}: {self.error_msg} (got {value!r})")
        setattr(obj, self.attr_name, value)


# ---------------------------------------------------------------------------
# Descriptor 2: Lazy computed field (computed once, cached)
# ---------------------------------------------------------------------------
class LazyField(Generic[T]):
    """Descriptor that computes its value on first access and caches it.

    Uses weakref to avoid preventing garbage collection.
    """

    def __init__(self, factory: Callable[[Any], T]) -> None:
        self.factory = factory
        self.attr_name: str = ""
        self._cache: weakref.WeakKeyDictionary[Any, T] = weakref.WeakKeyDictionary()

    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = name

    def __get__(self, obj: object | None, objtype: type) -> Any:
        if obj is None:
            return self
        try:
            return self._cache[obj]
        except (KeyError, TypeError):
            value = self.factory(obj)
            try:
                self._cache[obj] = value
            except TypeError:
                pass  # unhashable, skip cache
            return value

    def invalidate(self, obj: object) -> None:
        self._cache.pop(obj, None)


# ---------------------------------------------------------------------------
# Descriptor 3: Change-tracked field
# ---------------------------------------------------------------------------
class TrackedField(Generic[T]):
    """Field that records all changes for audit logging.

    Access the change history via `obj.__field_history__[field_name]`.
    """

    def __init__(self, default: T | None = None) -> None:
        self.default = default
        self.attr_name: str = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = name
        # Ensure the owner class has a history dict
        if not hasattr(owner, "__field_history__"):
            owner.__field_history__ = {}

    def _get_history(self, obj: object) -> list[tuple[datetime, Any, Any]]:
        if not hasattr(obj, "__field_history__"):
            object.__setattr__(obj, "__field_history__", {})
        history = obj.__field_history__  # type: ignore
        if self.attr_name not in history:
            history[self.attr_name] = []
        return history[self.attr_name]

    def __get__(self, obj: object | None, objtype: type) -> Any:
        if obj is None:
            return self
        return getattr(obj, f"_{self.attr_name}", self.default)

    def __set__(self, obj: object, value: Any) -> None:
        storage_name = f"_{self.attr_name}"
        old = getattr(obj, storage_name, self.default)
        if old != value:
            self._get_history(obj).append(
                (datetime.now(timezone.utc), old, value)
            )
        setattr(obj, storage_name, value)


# ---------------------------------------------------------------------------
# Using descriptors with dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Employee:
    """Employee model with validated, lazy, and tracked fields."""
    name: str
    _email: str = ""
    _salary: int = 0

    # Validated field — runs check on every assignment
    email = ValidatedField[str](
        validator=lambda v: "@" in v and "." in v.split("@")[1],
        error_msg="Must be a valid email address",
    )

    # Validated + converted field
    salary = ValidatedField[int](
        validator=lambda v: 10_000 <= v <= 10_000_000,
        converter=int,
        error_msg="Must be between 10,000 and 10,000,000",
    )

    # Lazy computed field — expensive computation done once
    department_info = LazyField(
        lambda self: _fetch_department(self.name)
    )

    def __post_init__(self) -> None:
        if self._email:
            self.email = self._email
        if self._salary:
            self.salary = self._salary


def _fetch_department(name: str) -> dict:
    """Simulate expensive lookup."""
    return {"name": name, "department": "Engineering", "level": "Senior"}


# ---------------------------------------------------------------------------
# Change-tracked model
# ---------------------------------------------------------------------------
@dataclass
class Contract:
    """Contract with change tracking on sensitive fields."""
    contract_id: str
    _status: str = "draft"
    _amount: int = 0

    status = TrackedField[str](default="draft")
    amount = TrackedField[int](default=0)

    def __post_init__(self) -> None:
        if self._status != "draft":
            self.status = self._status
        if self._amount != 0:
            self.amount = self._amount

    def get_audit_log(self) -> list[dict]:
        """Return formatted audit log of all field changes."""
        log = []
        for field_name, changes in self.__field_history__.items():
            for ts, old_val, new_val in changes:
                log.append({
                    "field": field_name,
                    "timestamp": ts.isoformat(),
                    "old_value": old_val,
                    "new_value": new_val,
                })
        return sorted(log, key=lambda x: x["timestamp"])


# ---------------------------------------------------------------------------
# Decorator: cached_property alternative for dataclasses
# ---------------------------------------------------------------------------
def computed_field(func: Callable) -> property:
    """Decorator for computed fields on dataclasses.

    Unlike @property, this caches the result and invalidates when
    dependent fields change.
    """
    cache_attr = f"_cached_{func.__name__}"

    @functools.wraps(func)
    def wrapper(self: Any) -> Any:
        try:
            return getattr(self, cache_attr)
        except AttributeError:
            value = func(self)
            object.__setattr__(self, cache_attr, value)
            return value

    return property(wrapper)


@dataclass
class Invoice:
    items: list[tuple[str, int, float]] = field(default_factory=list)
    tax_rate: float = 0.08

    @computed_field
    def subtotal(self) -> float:
        return sum(qty * price for _, qty, price in self.items)

    @computed_field
    def tax(self) -> float:
        return self.subtotal * self.tax_rate

    @computed_field
    def total(self) -> float:
        return self.subtotal + self.tax


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    # Validated fields
    emp = Employee(name="Alice")
    emp.email = "alice@example.com"
    emp.salary = 120_000
    print(f"Employee: {emp.name}, {emp.email}, ${emp.salary:,}")

    # Lazy field
    print(f"Department: {emp.department_info}")

    # Change tracking
    contract = Contract(contract_id="C-001")
    contract.status = "review"
    contract.amount = 50_000
    contract.status = "approved"
    contract.amount = 55_000

    for entry in contract.get_audit_log():
        print(f"  {entry['field']}: {entry['old_value']} -> {entry['new_value']}")

    # Computed fields
    inv = Invoice(
        items=[("Widget", 10, 9.99), ("Gadget", 5, 24.99)],
        tax_rate=0.085,
    )
    print(f"Invoice: ${inv.subtotal:.2f} + ${inv.tax:.2f} = ${inv.total:.2f}")


if __name__ == "__main__":
    main()
```

**Key patterns:**

- **`__set_name__`** — automatically captures the field name when the descriptor is assigned as a class attribute
- **`ValidatedField`** — runs validator/converter on every `__set__`, providing continuous validation (not just at init)
- **`LazyField`** — computes expensive values on first access, uses `WeakKeyDictionary` to avoid memory leaks
- **`TrackedField`** — records `(timestamp, old, new)` tuples for every change, enabling audit logging
- **`computed_field`** — cached property that computes once and stores the result on the instance
- **Descriptor + dataclass integration** — descriptors work alongside `__post_init__` for initial value assignment'''
    ),
]
