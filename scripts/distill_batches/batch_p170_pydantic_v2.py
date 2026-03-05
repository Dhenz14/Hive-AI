"""Pydantic v2 advanced patterns — field validators, computed fields, custom types, settings, discriminated unions, generics."""

PAIRS = [
    (
        "python/pydantic-v2-validators-computed",
        "Show Pydantic v2 field validators and computed fields with before/after/wrap validators, model validators, and cached_property-style computed fields.",
        '''Pydantic v2 field validators and computed fields:

```python
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Self

from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
    ValidationInfo,
)


# ── Before / After / Wrap validators ──────────────────────────────

class User(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str
    age: int = Field(ge=0, le=150)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- before validator: runs BEFORE Pydantic's own validation ---
    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    # --- after validator: runs AFTER Pydantic type coercion ---
    @field_validator("email", mode="after")
    @classmethod
    def validate_email(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, v):
            raise ValueError(f"Invalid email: {v}")
        return v.lower()

    # --- wrap validator: controls the entire validation pipeline ---
    @field_validator("tags", mode="wrap")
    @classmethod
    def deduplicate_tags(cls, v: Any, handler: Any) -> list[str]:
        # Call the default handler first
        validated: list[str] = handler(v)
        # Then post-process
        return list(dict.fromkeys(validated))  # preserve order, remove dupes

    # --- model validator: access multiple fields at once ---
    @model_validator(mode="after")
    def check_admin_age(self) -> Self:
        if "admin" in self.tags and self.age < 18:
            raise ValueError("Admin users must be 18 or older")
        return self


# ── Computed fields (like @property but included in serialization) ─

class Order(BaseModel):
    items: list[LineItem]
    discount_pct: float = Field(ge=0, le=100, default=0)
    tax_rate: float = Field(ge=0, default=0.08)

    @computed_field
    @property
    def subtotal(self) -> float:
        return sum(item.total for item in self.items)

    @computed_field
    @property
    def discount_amount(self) -> float:
        return round(self.subtotal * (self.discount_pct / 100), 2)

    @computed_field
    @property
    def tax(self) -> float:
        taxable = self.subtotal - self.discount_amount
        return round(taxable * self.tax_rate, 2)

    @computed_field
    @property
    def grand_total(self) -> float:
        return round(self.subtotal - self.discount_amount + self.tax, 2)


class LineItem(BaseModel):
    name: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)

    @computed_field
    @property
    def total(self) -> float:
        return round(self.quantity * self.unit_price, 2)


# Rebuild Order to resolve forward ref
Order.model_rebuild()
```

```python
# ── Using validators with context ─────────────────────────────────

from pydantic import BaseModel, field_validator, ValidationInfo, Field


class TranslatedContent(BaseModel):
    text: str
    language: str = "en"

    @field_validator("text", mode="after")
    @classmethod
    def check_length_by_language(cls, v: str, info: ValidationInfo) -> str:
        """Different max lengths for different languages."""
        limits = {"en": 5000, "ja": 2000, "zh": 2000, "de": 6000}
        lang = info.data.get("language", "en")
        max_len = limits.get(lang, 5000)
        if len(v) > max_len:
            raise ValueError(
                f"Text too long for {lang}: {len(v)} > {max_len}"
            )
        return v


# ── Reusable validators via Annotated ─────────────────────────────

from typing import Annotated
from pydantic import AfterValidator


def must_be_positive(v: float) -> float:
    if v <= 0:
        raise ValueError("Must be positive")
    return v


def clamp_to_range(min_v: float, max_v: float):
    def _clamp(v: float) -> float:
        return max(min_v, min(max_v, v))
    return _clamp


PositiveFloat = Annotated[float, AfterValidator(must_be_positive)]
Percentage = Annotated[float, AfterValidator(clamp_to_range(0.0, 100.0))]


class Pricing(BaseModel):
    base_price: PositiveFloat
    markup_pct: Percentage
    discount_pct: Percentage = 0.0

    @computed_field
    @property
    def final_price(self) -> float:
        price = self.base_price * (1 + self.markup_pct / 100)
        price *= 1 - self.discount_pct / 100
        return round(price, 2)
```

```python
# ── Model validator: before mode for raw data transformation ──────

from pydantic import model_validator


class APIResponse(BaseModel):
    status: str
    data: dict[str, Any]
    meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def unwrap_envelope(cls, values: Any) -> Any:
        """Handle APIs that wrap responses in an envelope."""
        if isinstance(values, dict) and "result" in values:
            return {
                "status": "ok",
                "data": values["result"],
                "meta": values.get("metadata", {}),
            }
        return values


# ── Testing validators ────────────────────────────────────────────

from pydantic import ValidationError

# Valid user
user = User(
    username="  Alice  ",
    email="ALICE@Example.COM",
    age=30,
    tags=["dev", "admin", "dev"],  # duplicate removed
)
assert user.username == "alice"
assert user.email == "alice@example.com"
assert user.tags == ["dev", "admin"]

# Validation error
try:
    User(username="ab", email="bad", age=-1)
except ValidationError as e:
    for err in e.errors():
        print(f"  {err['loc']}: {err['msg']}")

# Order with computed fields
order = Order(
    items=[
        LineItem(name="Widget", quantity=3, unit_price=9.99),
        LineItem(name="Gadget", quantity=1, unit_price=49.99),
    ],
    discount_pct=10,
)
print(order.model_dump())
# subtotal, discount_amount, tax, grand_total all computed automatically
```

| Validator Type | mode= | Runs When | Use Case |
|---|---|---|---|
| `field_validator` | `"before"` | Before type coercion | Normalization, type conversion |
| `field_validator` | `"after"` | After type coercion | Business rules on typed values |
| `field_validator` | `"wrap"` | Wraps entire pipeline | Custom coercion + post-processing |
| `model_validator` | `"before"` | Before any field parsing | Raw data transformation |
| `model_validator` | `"after"` | After all fields validated | Cross-field validation |
| `computed_field` | N/A | On access / serialization | Derived values in JSON output |

Key patterns:
1. Use `mode="before"` for normalization (strip, lowercase, type coerce).
2. Use `mode="after"` for business-rule validation on already-typed values.
3. Use `mode="wrap"` when you need to control the full pipeline (call `handler`).
4. `@model_validator(mode="after")` returns `Self` for cross-field checks.
5. `@computed_field` + `@property` replaces `@validator` + `always=True` from v1.
6. `Annotated[T, AfterValidator(fn)]` creates reusable composable types.'''
    ),
    (
        "python/pydantic-v2-custom-types-serialization",
        "Demonstrate Pydantic v2 custom types and serialization: custom annotated types, PlainSerializer, model_serializer, and custom JSON encoders.",
        '''Pydantic v2 custom types and serialization:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
    field_serializer,
    model_serializer,
)


# ── Custom Annotated types ────────────────────────────────────────

def parse_money(v: Any) -> Decimal:
    """Accept strings like '$1,234.56' or plain numbers."""
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    if isinstance(v, str):
        cleaned = v.replace("$", "").replace(",", "").strip()
        return Decimal(cleaned)
    raise ValueError(f"Cannot parse money from {type(v)}")


def serialize_money(v: Decimal) -> str:
    """Serialize Decimal to 2-decimal-place string."""
    return f"{v:.2f}"


# Reusable money type with parsing + serialization + JSON schema
Money = Annotated[
    Decimal,
    BeforeValidator(parse_money),
    PlainSerializer(serialize_money, return_type=str),
    WithJsonSchema({"type": "string", "pattern": r"^\d+\.\d{2}$"}),
]


def parse_unix_timestamp(v: Any) -> datetime:
    """Accept Unix timestamps or ISO strings."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    raise ValueError(f"Cannot parse datetime from {type(v)}")


UnixTimestamp = Annotated[
    datetime,
    BeforeValidator(parse_unix_timestamp),
    PlainSerializer(lambda v: int(v.timestamp()), return_type=int),
    WithJsonSchema({"type": "integer", "description": "Unix timestamp"}),
]


# ── Model using custom types ─────────────────────────────────────

class Transaction(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    amount: Money
    fee: Money = Decimal("0.00")
    created_at: UnixTimestamp = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    description: str = ""

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "amount": "99.99",
                    "fee": "2.50",
                    "created_at": 1700000000,
                    "description": "Widget purchase",
                }
            ]
        }


# Accepts varied input formats
tx = Transaction(
    amount="$1,234.56",   # string with symbols
    fee=2.5,              # float
    created_at=1700000000 # unix timestamp
)
print(tx.model_dump())
# {'id': UUID(...), 'amount': '1234.56', 'fee': '2.50',
#  'created_at': 1700000000, 'description': ''}
```

```python
# ── field_serializer for targeted control ─────────────────────────

from enum import Enum
from pydantic import field_serializer


class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class Account(BaseModel):
    id: int
    name: str
    balance: Decimal
    status: Status
    tags: set[str] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("balance")
    def serialize_balance(self, v: Decimal, _info: Any) -> str:
        return f"${v:,.2f}"

    @field_serializer("tags")
    def serialize_tags(self, v: set[str], _info: Any) -> list[str]:
        return sorted(v)  # sets aren't JSON-serializable; sort for stability

    @field_serializer("status")
    def serialize_status(self, v: Status, _info: Any) -> str:
        return v.value.upper()


account = Account(
    id=1,
    name="Acme Corp",
    balance=Decimal("50000.00"),
    status=Status.ACTIVE,
    tags={"premium", "enterprise", "api"},
)
print(json.dumps(account.model_dump(), indent=2))
# balance → "$50,000.00", tags → sorted list, status → "ACTIVE"


# ── model_serializer for full control ─────────────────────────────

class CompactEvent(BaseModel):
    event_type: str
    payload: dict[str, Any]
    timestamp: datetime

    @model_serializer
    def custom_serialize(self) -> dict[str, Any]:
        """Flatten the event for wire format."""
        return {
            "t": self.event_type,
            "ts": int(self.timestamp.timestamp()),
            **{f"d_{k}": v for k, v in self.payload.items()},
        }


event = CompactEvent(
    event_type="user.signup",
    payload={"user_id": 42, "plan": "pro"},
    timestamp=datetime(2025, 1, 15, tzinfo=timezone.utc),
)
print(event.model_dump())
# {'t': 'user.signup', 'ts': 1736899200, 'd_user_id': 42, 'd_plan': 'pro'}
```

```python
# ── Fully custom types with __get_pydantic_core_schema__ ──────────

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema


class Color:
    """Custom color type that accepts hex strings or RGB tuples."""

    __slots__ = ("r", "g", "b")

    def __init__(self, r: int, g: int, b: int) -> None:
        self.r, self.g, self.b = r, g, b

    @classmethod
    def from_hex(cls, hex_str: str) -> Color:
        hex_str = hex_str.lstrip("#")
        if len(hex_str) != 6:
            raise ValueError(f"Invalid hex color: #{hex_str}")
        return cls(
            int(hex_str[0:2], 16),
            int(hex_str[2:4], 16),
            int(hex_str[4:6], 16),
        )

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def __repr__(self) -> str:
        return f"Color({self.r}, {self.g}, {self.b})"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda v: v.to_hex(),
                info_arg=False,
            ),
        )

    @classmethod
    def _validate(cls, v: Any) -> Color:
        if isinstance(v, cls):
            return v
        if isinstance(v, str):
            return cls.from_hex(v)
        if isinstance(v, (list, tuple)) and len(v) == 3:
            return cls(*v)
        raise ValueError(f"Cannot create Color from {v!r}")


class Theme(BaseModel):
    name: str
    primary: Color
    secondary: Color
    background: Color = Color(255, 255, 255)


theme = Theme(
    name="Ocean",
    primary="#1a73e8",
    secondary=[46, 134, 193],
    # background uses default white
)
print(theme.model_dump())
# {'name': 'Ocean', 'primary': '#1a73e8', 'secondary': '#2e86c1',
#  'background': '#ffffff'}
print(theme.model_dump_json())
# JSON string with hex colors
```

| Feature | Mechanism | When to Use |
|---|---|---|
| `BeforeValidator` | Runs before core validation | Input normalization / coercion |
| `PlainValidator` | Replaces core validation entirely | Fully custom type parsing |
| `PlainSerializer` | Custom JSON output for a type | Control wire format |
| `field_serializer` | Per-field serialization on model | Format specific fields |
| `model_serializer` | Replace entire model serialization | Flatten / reshape output |
| `WithJsonSchema` | Override generated JSON Schema | API docs accuracy |
| `__get_pydantic_core_schema__` | Full custom type integration | Reusable non-BaseModel types |

Key patterns:
1. `Annotated[T, BeforeValidator(...), PlainSerializer(...)]` bundles parsing + serialization into one reusable type alias.
2. `WithJsonSchema` ensures OpenAPI / JSON Schema docs match your custom format.
3. `field_serializer` handles one field; `model_serializer` reshapes the whole output.
4. For complex custom types, implement `__get_pydantic_core_schema__` as a classmethod.
5. Always provide `return_type` to `PlainSerializer` so Pydantic knows the JSON type.'''
    ),
    (
        "python/pydantic-v2-settings-management",
        "Show Pydantic v2 settings management with environment variables, .env files, nested settings, secret files, and validation.",
        '''Pydantic v2 settings management with environment variables:

```python
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


# ── Database settings (nested) ────────────────────────────────────

class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "myapp"
    user: str = "postgres"
    password: SecretStr = SecretStr("changeme")
    pool_min: int = Field(default=2, ge=1)
    pool_max: int = Field(default=10, ge=1, le=100)
    ssl_mode: str = "prefer"

    @field_validator("pool_max")
    @classmethod
    def pool_max_gte_min(cls, v: int, info: Any) -> int:
        pool_min = info.data.get("pool_min", 2)
        if v < pool_min:
            raise ValueError(f"pool_max ({v}) must be >= pool_min ({pool_min})")
        return v

    @property
    def dsn(self) -> str:
        pwd = self.password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.user}:{pwd}"
            f"@{self.host}:{self.port}/{self.name}"
            f"?ssl={self.ssl_mode}"
        )


# ── Redis settings (nested) ──────────────────────────────────────

class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: SecretStr | None = None
    max_connections: int = 20

    @property
    def url(self) -> str:
        auth = ""
        if self.password:
            auth = f":{self.password.get_secret_value()}@"
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


# ── Top-level application settings ───────────────────────────────

class AppSettings(BaseSettings):
    """Main application configuration.

    Priority (highest to lowest):
      1. Environment variables
      2. .env file
      3. Secrets directory (/run/secrets)
      4. Default values
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",     # APP__DB__HOST=... for nested
        secrets_dir="/run/secrets",    # Docker secrets
        case_sensitive=False,
        extra="ignore",               # Ignore unknown env vars
    )

    # Core
    environment: Environment = Environment.DEV
    debug: bool = False
    app_name: str = "MyApp"
    version: str = "1.0.0"
    secret_key: SecretStr

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = Field(default=1, ge=1, le=32)

    # Nested
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)

    # Feature flags
    enable_metrics: bool = True
    enable_docs: bool = True
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    @model_validator(mode="after")
    def production_checks(self) -> AppSettings:
        if self.environment == Environment.PRODUCTION:
            if self.debug:
                raise ValueError("debug=True not allowed in production")
            if self.secret_key.get_secret_value() == "changeme":
                raise ValueError("Must set a real secret_key in production")
            if self.workers < 2:
                raise ValueError("Production needs at least 2 workers")
            if self.enable_docs:
                # Auto-disable docs in prod
                object.__setattr__(self, "enable_docs", False)
        return self
```

```python
# ── .env file example ─────────────────────────────────────────────
# .env
# APP_ENVIRONMENT=production
# APP_DEBUG=false
# APP_SECRET_KEY=super-secret-key-here
# APP_WORKERS=4
# APP_CORS_ORIGINS=["https://myapp.com","https://admin.myapp.com"]
#
# DB_HOST=db.internal
# DB_PORT=5432
# DB_NAME=myapp_prod
# DB_USER=myapp
# DB_PASSWORD=hunter2
# DB_POOL_MIN=5
# DB_POOL_MAX=20
# DB_SSL_MODE=require
#
# REDIS_HOST=redis.internal
# REDIS_PASSWORD=redis-secret

# ── Using settings with dependency injection (FastAPI) ────────────

from functools import lru_cache

from fastapi import Depends, FastAPI


@lru_cache
def get_settings() -> AppSettings:
    """Cached settings singleton — reads env once."""
    return AppSettings()


app = FastAPI()


@app.get("/health")
async def health(settings: AppSettings = Depends(get_settings)):
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment.value,
    }


# ── Override settings in tests ────────────────────────────────────

import pytest


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    """Create test settings without touching real env."""
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "testdb")
    get_settings.cache_clear()  # clear lru_cache
    settings = AppSettings()
    return settings


def test_database_dsn(test_settings: AppSettings) -> None:
    assert "testdb" in test_settings.db.dsn
    assert "localhost" in test_settings.db.dsn
```

```python
# ── Custom settings sources ───────────────────────────────────────

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class VaultSettingsSource(PydanticBaseSettingsSource):
    """Load secrets from HashiCorp Vault."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._secrets: dict[str, Any] = {}

    def _load_from_vault(self) -> dict[str, Any]:
        # In production, use hvac client
        import os
        vault_addr = os.getenv("VAULT_ADDR", "")
        if not vault_addr:
            return {}
        # Placeholder for real Vault call:
        # client = hvac.Client(url=vault_addr, token=os.getenv("VAULT_TOKEN"))
        # return client.secrets.kv.v2.read_secret("myapp")["data"]["data"]
        return {}

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        val = self._secrets.get(field_name)
        return val, field_name, val is not None

    def __call__(self) -> dict[str, Any]:
        if not self._secrets:
            self._secrets = self._load_from_vault()
        return self._secrets


class VaultAwareSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")

    secret_key: SecretStr
    db_password: SecretStr

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,             # highest priority
            env_settings,              # env vars
            VaultSettingsSource(settings_cls),  # Vault
            dotenv_settings,           # .env file
            file_secret_settings,      # /run/secrets
        )
```

| Source | Priority | Use Case |
|---|---|---|
| `__init__` kwargs | Highest | Tests, explicit overrides |
| Environment variables | High | Container / CI config |
| Custom source (Vault) | Medium | Secret management |
| `.env` file | Low | Local development |
| `/run/secrets` files | Low | Docker / K8s secrets |
| Field defaults | Lowest | Sensible fallbacks |

Key patterns:
1. Use `SecretStr` for passwords/keys -- prevents accidental logging.
2. `env_nested_delimiter="__"` maps `APP__DB__HOST` to `settings.db.host`.
3. `@lru_cache` on `get_settings()` ensures one read of env per process.
4. Production validators prevent insecure defaults from reaching prod.
5. Custom `PydanticBaseSettingsSource` integrates Vault, AWS SSM, etc.
6. Always clear `lru_cache` in tests with `get_settings.cache_clear()`.'''
    ),
    (
        "python/pydantic-v2-discriminated-unions",
        "Show Pydantic v2 discriminated unions and tagged types for polymorphic deserialization with proper type narrowing.",
        '''Pydantic v2 discriminated unions and tagged types:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, TypeAdapter


# ── Discriminated unions with Literal tag field ───────────────────

class EmailNotification(BaseModel):
    type: Literal["email"] = "email"
    recipient: str
    subject: str
    body: str
    cc: list[str] = Field(default_factory=list)

    def deliver(self) -> str:
        return f"Sending email to {self.recipient}: {self.subject}"


class SMSNotification(BaseModel):
    type: Literal["sms"] = "sms"
    phone_number: str
    message: str

    def deliver(self) -> str:
        return f"Sending SMS to {self.phone_number}"


class PushNotification(BaseModel):
    type: Literal["push"] = "push"
    device_token: str
    title: str
    body: str
    data: dict[str, Any] = Field(default_factory=dict)

    def deliver(self) -> str:
        return f"Pushing to device {self.device_token[:8]}..."


class WebhookNotification(BaseModel):
    type: Literal["webhook"] = "webhook"
    url: str
    payload: dict[str, Any]
    headers: dict[str, str] = Field(default_factory=dict)

    def deliver(self) -> str:
        return f"POST {self.url}"


# The discriminated union — Pydantic checks `type` field first
Notification = Annotated[
    EmailNotification | SMSNotification | PushNotification | WebhookNotification,
    Field(discriminator="type"),
]


class NotificationBatch(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    notifications: list[Notification]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def deliver_all(self) -> list[str]:
        return [n.deliver() for n in self.notifications]


# Pydantic auto-selects the right model based on `type`
batch = NotificationBatch(notifications=[
    {"type": "email", "recipient": "a@b.com", "subject": "Hi", "body": "Hello"},
    {"type": "sms", "phone_number": "+1234567890", "message": "Code: 1234"},
    {"type": "push", "device_token": "abc123def", "title": "Alert", "body": "!"},
])
for n in batch.notifications:
    print(type(n).__name__, "->", n.deliver())
```

```python
# ── Nested discriminated unions (event system) ────────────────────

class UserCreated(BaseModel):
    event: Literal["user.created"] = "user.created"
    user_id: int
    email: str


class UserUpdated(BaseModel):
    event: Literal["user.updated"] = "user.updated"
    user_id: int
    changes: dict[str, Any]


class OrderPlaced(BaseModel):
    event: Literal["order.placed"] = "order.placed"
    order_id: int
    total: float
    items: list[str]


class OrderCancelled(BaseModel):
    event: Literal["order.cancelled"] = "order.cancelled"
    order_id: int
    reason: str


DomainEvent = Annotated[
    UserCreated | UserUpdated | OrderPlaced | OrderCancelled,
    Field(discriminator="event"),
]


class EventEnvelope(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    source: str
    event: DomainEvent  # discriminated union


# ── TypeAdapter for standalone parsing ────────────────────────────

event_adapter = TypeAdapter(DomainEvent)

# Parse a single event without wrapping in a model
raw = {"event": "order.placed", "order_id": 42, "total": 99.99, "items": ["x"]}
parsed = event_adapter.validate_python(raw)
assert isinstance(parsed, OrderPlaced)
assert parsed.order_id == 42

# Parse a list of events
events_adapter = TypeAdapter(list[DomainEvent])
raw_events = [
    {"event": "user.created", "user_id": 1, "email": "a@b.com"},
    {"event": "order.placed", "order_id": 10, "total": 50.0, "items": ["y"]},
]
events = events_adapter.validate_python(raw_events)
assert isinstance(events[0], UserCreated)
assert isinstance(events[1], OrderPlaced)
```

```python
# ── Custom discriminator functions (Pydantic v2.5+) ──────────────

from pydantic import Discriminator, Tag


class Circle(BaseModel):
    radius: float

    def area(self) -> float:
        import math
        return math.pi * self.radius ** 2


class Rectangle(BaseModel):
    width: float
    height: float

    def area(self) -> float:
        return self.width * self.height


class Triangle(BaseModel):
    base: float
    height: float

    def area(self) -> float:
        return 0.5 * self.base * self.height


def shape_discriminator(raw: dict[str, Any]) -> str:
    """Infer shape type from which fields are present."""
    if "radius" in raw:
        return "circle"
    if "width" in raw and "height" in raw:
        return "rectangle"
    if "base" in raw and "height" in raw:
        return "triangle"
    raise ValueError("Cannot determine shape type from fields")


Shape = Annotated[
    Annotated[Circle, Tag("circle")]
    | Annotated[Rectangle, Tag("rectangle")]
    | Annotated[Triangle, Tag("triangle")],
    Discriminator(shape_discriminator),
]


class Canvas(BaseModel):
    shapes: list[Shape]

    def total_area(self) -> float:
        return sum(s.area() for s in self.shapes)


# No explicit `type` field needed — discriminator infers from keys
canvas = Canvas(shapes=[
    {"radius": 5.0},
    {"width": 10, "height": 20},
    {"base": 6, "height": 8},
])
print(f"Total area: {canvas.total_area():.2f}")
# Circle + Rectangle + Triangle


# ── JSON Schema output ───────────────────────────────────────────

import json

schema = NotificationBatch.model_json_schema()
print(json.dumps(schema, indent=2))
# Generates proper oneOf with discriminator mapping in JSON Schema
```

| Approach | Discriminator | Pros | Cons |
|---|---|---|---|
| `Literal` field | `Field(discriminator="type")` | Fast, explicit, standard JSON | Requires tag field in data |
| Custom function | `Discriminator(fn)` | No tag field needed | Slower, fragile heuristics |
| Plain `Union` | None (try each) | No setup needed | Slow, ambiguous, wrong matches |
| `TypeAdapter` | Any of above | No wrapping model needed | Slightly less discoverable |

Key patterns:
1. Always prefer `Literal` discriminators -- they generate correct JSON Schema `oneOf`.
2. `Field(discriminator="type")` makes Pydantic check the tag FIRST, O(1) dispatch.
3. `TypeAdapter` lets you validate unions without a wrapping `BaseModel`.
4. Custom `Discriminator(fn)` handles legacy data without explicit type tags.
5. Each branch model should define `type: Literal["..."] = "..."` as a default for serialization.
6. Nested discriminated unions compose naturally for complex event systems.'''
    ),
    (
        "python/pydantic-v2-generics-inheritance",
        "Show Pydantic v2 model inheritance and generic models for building reusable API response wrappers, paginated results, and type-safe repositories.",
        '''Pydantic v2 model inheritance and generic models:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, Sequence, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


# ── Generic API response wrapper ──────────────────────────────────

DataT = TypeVar("DataT")


class APIResponse(BaseModel, Generic[DataT]):
    """Type-safe API response envelope."""
    success: bool = True
    data: DataT
    message: str = ""
    request_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def ok(cls, data: DataT, message: str = "") -> APIResponse[DataT]:
        return cls(data=data, message=message)

    @classmethod
    def error(cls, message: str) -> APIResponse[None]:
        return APIResponse[None](success=False, data=None, message=message)


class PaginationMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)

    @computed_field
    @property
    def total_pages(self) -> int:
        return max(1, -(-self.total_items // self.page_size))

    @computed_field
    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @computed_field
    @property
    def has_prev(self) -> bool:
        return self.page > 1


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Generic paginated response."""
    items: list[DataT]
    pagination: PaginationMeta

    @classmethod
    def create(
        cls,
        items: Sequence[DataT],
        page: int,
        page_size: int,
        total_items: int,
    ) -> PaginatedResponse[DataT]:
        return cls(
            items=list(items),
            pagination=PaginationMeta(
                page=page,
                page_size=page_size,
                total_items=total_items,
            ),
        )


# ── Domain models ────────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    username: str
    email: str


class ProductOut(BaseModel):
    id: int
    name: str
    price: float


# Concrete typed responses
UserResponse = APIResponse[UserOut]
UserListResponse = APIResponse[PaginatedResponse[UserOut]]
ProductListResponse = APIResponse[PaginatedResponse[ProductOut]]

# Usage
user = UserOut(id=1, username="alice", email="a@b.com")
response: UserResponse = APIResponse.ok(user, message="User found")
print(response.model_dump_json(indent=2))
```

```python
# ── Model inheritance: base audit fields ──────────────────────────

from pydantic import ConfigDict


class AuditMixin(BaseModel):
    """Mixin for audit fields — not used standalone."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

    def touch(self, by: str = "system") -> None:
        object.__setattr__(self, "updated_at", datetime.now(timezone.utc))
        object.__setattr__(self, "created_by", by)


class SoftDeleteMixin(BaseModel):
    """Mixin for soft-delete pattern."""
    is_deleted: bool = False
    deleted_at: datetime | None = None

    def soft_delete(self) -> None:
        object.__setattr__(self, "is_deleted", True)
        object.__setattr__(self, "deleted_at", datetime.now(timezone.utc))


class BaseEntity(AuditMixin, SoftDeleteMixin):
    """Base for all domain entities."""
    model_config = ConfigDict(
        from_attributes=True,  # ORM mode
        populate_by_name=True,
    )

    id: UUID = Field(default_factory=uuid4)


class Customer(BaseEntity):
    name: str
    email: str
    tier: str = "free"


class Invoice(BaseEntity):
    customer_id: UUID
    amount: float
    status: str = "draft"
    line_items: list[InvoiceLineItem] = Field(default_factory=list)

    @computed_field
    @property
    def total(self) -> float:
        return sum(li.amount for li in self.line_items)


class InvoiceLineItem(BaseModel):
    description: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)

    @computed_field
    @property
    def amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)


Invoice.model_rebuild()  # resolve forward ref
```

```python
# ── Generic repository pattern ────────────────────────────────────

from typing import ClassVar

ModelT = TypeVar("ModelT", bound=BaseEntity)


class InMemoryRepository(Generic[ModelT]):
    """Type-safe in-memory repository for testing."""

    def __init__(self) -> None:
        self._store: dict[UUID, ModelT] = {}

    def add(self, entity: ModelT) -> ModelT:
        self._store[entity.id] = entity
        return entity

    def get(self, entity_id: UUID) -> ModelT | None:
        item = self._store.get(entity_id)
        if item and not item.is_deleted:
            return item
        return None

    def list_all(
        self, *, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse[ModelT]:
        active = [e for e in self._store.values() if not e.is_deleted]
        start = (page - 1) * page_size
        end = start + page_size
        return PaginatedResponse.create(
            items=active[start:end],
            page=page,
            page_size=page_size,
            total_items=len(active),
        )

    def update(self, entity_id: UUID, **fields: Any) -> ModelT | None:
        item = self.get(entity_id)
        if not item:
            return None
        updated = item.model_copy(update=fields)
        updated.touch()
        self._store[entity_id] = updated
        return updated

    def delete(self, entity_id: UUID) -> bool:
        item = self.get(entity_id)
        if not item:
            return False
        item.soft_delete()
        return True


# ── Usage ─────────────────────────────────────────────────────────

customer_repo: InMemoryRepository[Customer] = InMemoryRepository()
invoice_repo: InMemoryRepository[Invoice] = InMemoryRepository()

c = customer_repo.add(Customer(name="Acme", email="acme@co.com", tier="pro"))
inv = invoice_repo.add(Invoice(
    customer_id=c.id,
    amount=0,
    line_items=[
        InvoiceLineItem(description="Widget", quantity=5, unit_price=10.0),
        InvoiceLineItem(description="Service", quantity=1, unit_price=200.0),
    ],
))

page = customer_repo.list_all(page=1, page_size=10)
assert page.pagination.total_items == 1

# JSON Schema for concrete generic
import json
schema = APIResponse[PaginatedResponse[UserOut]].model_json_schema()
print(json.dumps(schema, indent=2))
# Generates fully resolved schema with no $ref ambiguity
```

| Pattern | Base Class | Purpose |
|---|---|---|
| `APIResponse[T]` | `BaseModel, Generic[T]` | Type-safe response envelope |
| `PaginatedResponse[T]` | `BaseModel, Generic[T]` | Reusable pagination |
| `AuditMixin` | `BaseModel` | `created_at`, `updated_at` fields |
| `SoftDeleteMixin` | `BaseModel` | Soft-delete with `is_deleted` |
| `BaseEntity` | Multiple mixins | Common entity base |
| `InMemoryRepository[T]` | `Generic[T]` | Type-safe CRUD operations |

Key patterns:
1. `Generic[T]` with `BaseModel` creates reusable typed containers.
2. Concrete aliases like `UserResponse = APIResponse[UserOut]` give explicit schema names.
3. Mixins add shared fields; `BaseEntity` composes them via multiple inheritance.
4. `model_copy(update={...})` creates immutable-style updates.
5. `ConfigDict(from_attributes=True)` enables ORM integration (replaces v1 `orm_mode`).
6. `model_rebuild()` resolves forward references in mutually-dependent models.'''
    ),
]
"""
