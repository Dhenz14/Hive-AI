"""Input validation: Pydantic validators, Zod schemas, SQL injection prevention, XSS sanitization."""

PAIRS = [
    (
        "validation/pydantic-advanced-validators",
        "How do I build complex input validation with Pydantic v2 validators, custom types, and nested models?",
        '''Pydantic v2 provides powerful validation with significant performance improvements over v1. Here is a comprehensive implementation covering custom validators, computed fields, discriminated unions, and reusable types:

```python
"""Advanced Pydantic v2 validation patterns for production APIs."""

import re
import uuid
from decimal import Decimal
from datetime import datetime, date, timezone
from typing import Annotated, Literal, Optional, Self
from enum import Enum

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    computed_field,
    ConfigDict,
    EmailStr,
    HttpUrl,
    SecretStr,
    constr,
    conint,
    confloat,
)
from pydantic.functional_validators import AfterValidator, BeforeValidator
from pydantic import TypeAdapter


# ─── Custom Annotated Types (Reusable) ──────────────────────────────

def validate_phone(v: str) -> str:
    """Validate and normalize phone numbers to E.164 format."""
    cleaned = re.sub(r"[\\s\\-\\(\\)\\.]", "", v)
    if not re.match(r"^\\+?[1-9]\\d{6,14}$", cleaned):
        raise ValueError("Invalid phone number. Use E.164 format: +1234567890")
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    return cleaned


def validate_slug(v: str) -> str:
    """Validate URL-safe slug."""
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
        raise ValueError("Slug must be lowercase alphanumeric with hyphens only")
    return v


def sanitize_string(v: str) -> str:
    """Strip leading/trailing whitespace and normalize internal whitespace."""
    return " ".join(v.split())


# Reusable annotated types
PhoneNumber = Annotated[str, AfterValidator(validate_phone)]
Slug = Annotated[str, AfterValidator(validate_slug), Field(min_length=1, max_length=100)]
SanitizedStr = Annotated[str, BeforeValidator(lambda v: str(v).strip() if v else v)]
PositiveDecimal = Annotated[Decimal, Field(gt=0, decimal_places=2)]
Percentage = Annotated[float, Field(ge=0, le=100)]


# ─── Enums and Choices ──────────────────────────────────────────────

class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# ─── Nested Models with Validation ──────────────────────────────────

class Address(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    street: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=50)
    postal_code: str = Field(min_length=3, max_length=20)
    country: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2")

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        v = v.upper()
        valid_countries = {"US", "CA", "GB", "DE", "FR", "JP", "AU"}
        if v not in valid_countries:
            raise ValueError(f"Unsupported country: {v}")
        return v

    @field_validator("postal_code")
    @classmethod
    def validate_postal_code(cls, v: str, info) -> str:
        # Access other validated fields via info.data
        country = info.data.get("country", "").upper()
        patterns = {
            "US": r"^\\d{5}(-\\d{4})?$",
            "CA": r"^[A-Z]\\d[A-Z] \\d[A-Z]\\d$",
            "GB": r"^[A-Z]{1,2}\\d[A-Z\\d]? \\d[A-Z]{2}$",
        }
        pattern = patterns.get(country)
        if pattern and not re.match(pattern, v):
            raise ValueError(f"Invalid postal code for {country}")
        return v


class Money(BaseModel):
    """Value object for monetary amounts."""
    amount: Decimal = Field(ge=0, decimal_places=2)
    currency: Currency

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return f"{self.currency.value} {self.amount}"


class OrderItem(BaseModel):
    product_id: uuid.UUID
    name: SanitizedStr = Field(max_length=200)
    quantity: conint(gt=0, le=10000)
    unit_price: Money
    discount_percent: Percentage = 0

    @computed_field
    @property
    def total_price(self) -> Decimal:
        base = self.unit_price.amount * self.quantity
        discount = base * Decimal(str(self.discount_percent)) / 100
        return (base - discount).quantize(Decimal("0.01"))


class CreateOrderRequest(BaseModel):
    """Full order creation request with cross-field validation."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        str_min_length=1,
        validate_default=True,
    )

    customer_email: EmailStr
    customer_phone: Optional[PhoneNumber] = None
    shipping_address: Address
    billing_address: Optional[Address] = None
    items: list[OrderItem] = Field(min_length=1, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=1000)
    coupon_code: Optional[constr(pattern=r"^[A-Z0-9]{4,20}$")] = None
    requested_delivery: Optional[date] = None

    @field_validator("requested_delivery")
    @classmethod
    def delivery_in_future(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v <= date.today():
            raise ValueError("Delivery date must be in the future")
        return v

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Cross-field validation after all fields are parsed."""
        # Ensure all items use the same currency
        currencies = {item.unit_price.currency for item in self.items}
        if len(currencies) > 1:
            raise ValueError(
                f"All items must use the same currency, got: {currencies}"
            )

        # Use shipping as billing if not provided
        if self.billing_address is None:
            self.billing_address = self.shipping_address

        # Validate max order total
        total = sum(item.total_price for item in self.items)
        if total > Decimal("100000"):
            raise ValueError(f"Order total {total} exceeds maximum of 100,000")

        return self

    @computed_field
    @property
    def order_total(self) -> Decimal:
        return sum(item.total_price for item in self.items)

    @computed_field
    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)


# ─── Discriminated Unions ───────────────────────────────────────────

class CreditCardPayment(BaseModel):
    method: Literal["credit_card"]
    card_token: str = Field(min_length=10, max_length=100)
    last_four: constr(pattern=r"^\\d{4}$")
    save_card: bool = False


class BankTransferPayment(BaseModel):
    method: Literal["bank_transfer"]
    bank_name: str = Field(min_length=1, max_length=100)
    account_last_four: constr(pattern=r"^\\d{4}$")
    routing_number: constr(pattern=r"^\\d{9}$")


class WalletPayment(BaseModel):
    method: Literal["wallet"]
    wallet_id: str = Field(min_length=1, max_length=50)
    pin_hash: SecretStr


# Discriminated union - Pydantic picks the right model based on "method"
PaymentMethod = CreditCardPayment | BankTransferPayment | WalletPayment


class PaymentRequest(BaseModel):
    order_id: uuid.UUID
    payment: Annotated[PaymentMethod, Field(discriminator="method")]
    idempotency_key: uuid.UUID = Field(default_factory=uuid.uuid4)


# ─── Standalone Validation (without models) ─────────────────────────

# TypeAdapter for validating raw data without a model
email_validator = TypeAdapter(EmailStr)
phone_validator = TypeAdapter(PhoneNumber)
order_items_validator = TypeAdapter(list[OrderItem])


def validate_email(email: str) -> str:
    """Validate a single email address."""
    return email_validator.validate_python(email)


def validate_batch_items(raw_data: list[dict]) -> list[OrderItem]:
    """Validate a list of order items from raw dicts."""
    return order_items_validator.validate_python(raw_data)


# ─── FastAPI Integration ────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

app = FastAPI()


@app.post("/orders")
async def create_order(order: CreateOrderRequest):
    """Pydantic validates automatically in FastAPI."""
    return {
        "message": "Order created",
        "total": str(order.order_total),
        "items": order.item_count,
    }


@app.post("/validate-batch")
async def validate_batch(items: list[dict]):
    """Manual validation with detailed error responses."""
    try:
        validated = validate_batch_items(items)
        return {"valid": True, "count": len(validated)}
    except ValidationError as e:
        return {
            "valid": False,
            "errors": [
                {
                    "field": ".".join(str(loc) for loc in err["loc"]),
                    "message": err["msg"],
                    "type": err["type"],
                }
                for err in e.errors()
            ],
        }
```

Pydantic v2 validation patterns:

| Pattern | Use Case | Example |
|---------|----------|---------|
| field_validator | Single field rules | Email format, date ranges |
| model_validator | Cross-field rules | Items must share currency |
| Annotated types | Reusable validators | PhoneNumber, Slug, SanitizedStr |
| computed_field | Derived values | order_total, item_count |
| Discriminated unions | Polymorphic input | PaymentMethod by "method" field |
| TypeAdapter | Standalone validation | Validate without a model class |
| ConfigDict | Model-wide settings | str_strip_whitespace, min_length |

Key patterns:

- Use Annotated types with AfterValidator/BeforeValidator for reusable validation
- Use model_validator(mode="after") for cross-field validation
- Use discriminated unions for polymorphic request bodies
- Set str_strip_whitespace=True in ConfigDict to auto-strip strings
- Use computed_field for derived properties included in serialization
- Return structured error responses with field paths and messages
- Use SecretStr for sensitive fields to prevent accidental logging'''
    ),
    (
        "validation/zod-typescript-schemas",
        "How do I build comprehensive input validation with Zod in TypeScript for API request/response validation?",
        '''Zod is the standard schema validation library for TypeScript, providing type-safe validation with excellent inference. Here is a production-grade implementation covering transforms, refinements, discriminated unions, and API integration:

```typescript
/**
 * Comprehensive Zod validation schemas for a TypeScript API.
 */
import { z } from "zod";

// ─── Reusable Schema Primitives ─────────────────────────────────────

const emailSchema = z
  .string()
  .email("Invalid email address")
  .toLowerCase()
  .trim();

const phoneSchema = z
  .string()
  .transform((v) => v.replace(/[\s\-\(\)\.]/g, ""))
  .refine((v) => /^\+?[1-9]\d{6,14}$/.test(v), {
    message: "Invalid phone number. Use E.164 format: +1234567890",
  })
  .transform((v) => (v.startsWith("+") ? v : `+${v}`));

const slugSchema = z
  .string()
  .min(1)
  .max(100)
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Must be a valid URL slug");

const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .max(128, "Password must not exceed 128 characters")
  .regex(/[A-Z]/, "Must contain at least one uppercase letter")
  .regex(/[a-z]/, "Must contain at least one lowercase letter")
  .regex(/[0-9]/, "Must contain at least one digit")
  .regex(/[^A-Za-z0-9]/, "Must contain at least one special character");

const dateInFuture = z.coerce
  .date()
  .refine((d) => d > new Date(), { message: "Date must be in the future" });

const positiveDecimal = z
  .number()
  .positive()
  .multipleOf(0.01)
  .transform((v) => Math.round(v * 100) / 100);

const paginationSchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(20),
  sortBy: z.string().optional(),
  sortOrder: z.enum(["asc", "desc"]).default("asc"),
});

// ─── Enum Schemas ──────────────────────────────────────────────────

const CurrencySchema = z.enum(["USD", "EUR", "GBP", "JPY"]);
type Currency = z.infer<typeof CurrencySchema>;

const OrderStatusSchema = z.enum([
  "pending",
  "confirmed",
  "shipped",
  "delivered",
  "cancelled",
]);

// ─── Nested Object Schemas ─────────────────────────────────────────

const AddressSchema = z
  .object({
    street: z.string().min(1).max(200).trim(),
    city: z.string().min(1).max(100).trim(),
    state: z.string().min(2).max(50).trim(),
    postalCode: z.string().min(3).max(20),
    country: z
      .string()
      .length(2)
      .toUpperCase()
      .refine((v) => ["US", "CA", "GB", "DE", "FR", "JP", "AU"].includes(v), {
        message: "Unsupported country code",
      }),
  })
  .refine(
    (addr) => {
      if (addr.country === "US") {
        return /^\d{5}(-\d{4})?$/.test(addr.postalCode);
      }
      return true;
    },
    { message: "Invalid US postal code", path: ["postalCode"] }
  );

const MoneySchema = z.object({
  amount: positiveDecimal,
  currency: CurrencySchema,
});

const OrderItemSchema = z.object({
  productId: z.string().uuid(),
  name: z.string().min(1).max(200).trim(),
  quantity: z.number().int().positive().max(10000),
  unitPrice: MoneySchema,
  discountPercent: z.number().min(0).max(100).default(0),
});

// Add computed field via transform
const OrderItemWithTotal = OrderItemSchema.transform((item) => ({
  ...item,
  totalPrice:
    Math.round(
      item.unitPrice.amount *
        item.quantity *
        (1 - item.discountPercent / 100) *
        100
    ) / 100,
}));

// ─── Complex Request Schema with Cross-Field Validation ────────────

const CreateOrderSchema = z
  .object({
    customerEmail: emailSchema,
    customerPhone: phoneSchema.optional(),
    shippingAddress: AddressSchema,
    billingAddress: AddressSchema.optional(),
    items: z.array(OrderItemWithTotal).min(1).max(100),
    notes: z.string().max(1000).optional(),
    couponCode: z
      .string()
      .regex(/^[A-Z0-9]{4,20}$/)
      .optional(),
    requestedDelivery: dateInFuture.optional(),
  })
  .refine(
    (order) => {
      // All items must use the same currency
      const currencies = new Set(order.items.map((i) => i.unitPrice.currency));
      return currencies.size <= 1;
    },
    { message: "All items must use the same currency", path: ["items"] }
  )
  .refine(
    (order) => {
      // Max order total
      const total = order.items.reduce((sum, i) => sum + i.totalPrice, 0);
      return total <= 100000;
    },
    { message: "Order total exceeds maximum of $100,000", path: ["items"] }
  )
  .transform((order) => ({
    ...order,
    billingAddress: order.billingAddress ?? order.shippingAddress,
    orderTotal: order.items.reduce((sum, i) => sum + i.totalPrice, 0),
    itemCount: order.items.reduce((sum, i) => sum + i.quantity, 0),
  }));

type CreateOrderInput = z.input<typeof CreateOrderSchema>;
type CreateOrderOutput = z.output<typeof CreateOrderSchema>;

// ─── Discriminated Unions ──────────────────────────────────────────

const CreditCardPaymentSchema = z.object({
  method: z.literal("credit_card"),
  cardToken: z.string().min(10).max(100),
  lastFour: z.string().regex(/^\d{4}$/),
  saveCard: z.boolean().default(false),
});

const BankTransferPaymentSchema = z.object({
  method: z.literal("bank_transfer"),
  bankName: z.string().min(1).max(100),
  accountLastFour: z.string().regex(/^\d{4}$/),
  routingNumber: z.string().regex(/^\d{9}$/),
});

const WalletPaymentSchema = z.object({
  method: z.literal("wallet"),
  walletId: z.string().min(1).max(50),
  pin: z.string().min(4).max(8),
});

const PaymentMethodSchema = z.discriminatedUnion("method", [
  CreditCardPaymentSchema,
  BankTransferPaymentSchema,
  WalletPaymentSchema,
]);

const PaymentRequestSchema = z.object({
  orderId: z.string().uuid(),
  payment: PaymentMethodSchema,
  idempotencyKey: z.string().uuid().default(() => crypto.randomUUID()),
});

// ─── Express/Hono Middleware Integration ───────────────────────────

type ValidationTarget = "body" | "query" | "params";

function validate<T extends z.ZodType>(
  schema: T,
  target: ValidationTarget = "body"
) {
  return (req: any, res: any, next: any) => {
    const data = req[target];
    const result = schema.safeParse(data);

    if (!result.success) {
      const errors = result.error.issues.map((issue) => ({
        field: issue.path.join("."),
        message: issue.message,
        code: issue.code,
      }));

      return res.status(400).json({
        error: "Validation failed",
        details: errors,
      });
    }

    // Replace raw data with validated + transformed data
    req[`validated${target.charAt(0).toUpperCase()}${target.slice(1)}`] =
      result.data;
    next();
  };
}

// Usage in Express routes:
// app.post("/orders", validate(CreateOrderSchema), createOrderHandler);
// app.get("/orders", validate(paginationSchema, "query"), listOrdersHandler);

// ─── API Response Schemas ──────────────────────────────────────────

const OrderResponseSchema = z.object({
  id: z.string().uuid(),
  status: OrderStatusSchema,
  customerEmail: emailSchema,
  items: z.array(OrderItemWithTotal),
  orderTotal: z.number(),
  createdAt: z.coerce.date(),
  updatedAt: z.coerce.date(),
});

// Partial schema for PATCH updates
const UpdateOrderSchema = CreateOrderSchema.innerType()
  .partial()
  .omit({ customerEmail: true });

// ─── Schema Composition and Extension ──────────────────────────────

// Extend a base schema
const AdminOrderSchema = CreateOrderSchema.innerType().extend({
  assignedTo: z.string().uuid(),
  priority: z.enum(["low", "medium", "high", "critical"]),
  internalNotes: z.string().max(5000).optional(),
});

// Merge two schemas
const AuditFieldsSchema = z.object({
  createdBy: z.string().uuid(),
  createdAt: z.coerce.date(),
  updatedBy: z.string().uuid().optional(),
  updatedAt: z.coerce.date().optional(),
});

// Pick specific fields
const OrderSummarySchema = OrderResponseSchema.pick({
  id: true,
  status: true,
  orderTotal: true,
});

export {
  CreateOrderSchema,
  PaymentRequestSchema,
  paginationSchema,
  validate,
  type CreateOrderInput,
  type CreateOrderOutput,
};
```

Zod vs Pydantic comparison:

| Feature | Zod (TypeScript) | Pydantic v2 (Python) |
|---------|-----------------|---------------------|
| Type inference | z.infer<typeof schema> | Automatic from model |
| Transforms | .transform() | BeforeValidator / computed_field |
| Refinements | .refine() / .superRefine() | field_validator / model_validator |
| Discriminated unions | z.discriminatedUnion() | Literal + Field(discriminator=) |
| Default values | .default() | Field(default=) |
| Partial schemas | .partial() | No direct equivalent |
| Coercion | z.coerce.number() | Automatic type coercion |

Key patterns:

- Use z.infer to derive TypeScript types from schemas (single source of truth)
- Use .transform() for normalization (trim, lowercase, computed fields)
- Use .refine() for cross-field validation with custom error paths
- Use discriminatedUnion for polymorphic inputs with a discriminator field
- Create middleware functions that validate and replace req.body with typed data
- Use .safeParse() (not .parse()) in middleware to return structured errors
- Compose schemas with .extend(), .merge(), .pick(), .omit(), .partial()'''
    ),
    (
        "validation/sql-injection-prevention",
        "How do I prevent SQL injection in Python applications using parameterized queries and ORMs?",
        '''SQL injection remains one of the most critical web vulnerabilities. Prevention requires parameterized queries at every database interaction point. Here is a comprehensive guide covering raw SQL, ORMs, and common pitfalls:

```python
"""SQL injection prevention: parameterized queries, ORM safety, and common pitfalls."""

import re
import logging
from typing import Any, Optional
from datetime import datetime

from sqlalchemy import text, select, and_, or_, func, column
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Boolean
from fastapi import FastAPI, Query, HTTPException, Depends

logger = logging.getLogger(__name__)

app = FastAPI()

engine = create_async_engine("postgresql+asyncpg://localhost/myapp")
async_session = async_sessionmaker(engine, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer)  # cents
    stock: Mapped[int] = mapped_column(Integer, default=0)


# ─── SAFE: Parameterized Queries ────────────────────────────────────

async def get_user_safe(session: AsyncSession, username: str) -> Optional[User]:
    """SAFE: Uses SQLAlchemy ORM with parameterized query."""
    result = await session.execute(
        select(User).where(User.username == username)
    )
    return result.scalar_one_or_none()


async def get_user_raw_safe(session: AsyncSession, username: str) -> Optional[dict]:
    """SAFE: Raw SQL with bound parameters using text()."""
    result = await session.execute(
        text("SELECT * FROM users WHERE username = :username"),
        {"username": username},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def search_products_safe(
    session: AsyncSession,
    search_term: str,
    category: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
) -> list[Product]:
    """SAFE: Dynamic query building with parameterized filters."""
    query = select(Product)
    filters = []

    if search_term:
        # SAFE: LIKE with parameterized value
        # Escape special LIKE characters in the search term
        escaped = search_term.replace("%", "\\%").replace("_", "\\_")
        filters.append(Product.name.ilike(f"%{escaped}%"))

    if category:
        filters.append(Product.category == category)

    if min_price is not None:
        filters.append(Product.price >= min_price)

    if max_price is not None:
        filters.append(Product.price <= max_price)

    if filters:
        query = query.where(and_(*filters))

    # SAFE: Whitelist allowed sort columns instead of interpolating
    allowed_sort_columns = {
        "name": Product.name,
        "price": Product.price,
        "category": Product.category,
        "stock": Product.stock,
    }

    sort_column = allowed_sort_columns.get(sort_by, Product.name)
    if sort_order == "desc":
        sort_column = sort_column.desc()

    query = query.order_by(sort_column)

    result = await session.execute(query)
    return list(result.scalars().all())


async def bulk_lookup_safe(session: AsyncSession, user_ids: list[int]) -> list[User]:
    """SAFE: IN clause with parameterized list."""
    if not user_ids:
        return []
    # Validate that all IDs are integers
    validated_ids = [int(uid) for uid in user_ids]
    result = await session.execute(
        select(User).where(User.id.in_(validated_ids))
    )
    return list(result.scalars().all())


async def update_user_safe(
    session: AsyncSession,
    user_id: int,
    updates: dict[str, Any],
) -> bool:
    """SAFE: Dynamic UPDATE with whitelisted columns."""
    allowed_fields = {"email", "role", "is_active"}
    safe_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not safe_updates:
        return False

    # Build parameterized update
    set_clauses = ", ".join(f"{k} = :{k}" for k in safe_updates)
    safe_updates["user_id"] = user_id

    await session.execute(
        text(f"UPDATE users SET {set_clauses} WHERE id = :user_id"),
        safe_updates,
    )
    await session.commit()
    return True


# ─── VULNERABLE: Anti-patterns to AVOID ─────────────────────────────

async def get_user_VULNERABLE(session: AsyncSession, username: str):
    """VULNERABLE: String formatting in SQL query.

    Attack: username = "admin' OR '1'='1"
    Result: SELECT * FROM users WHERE username = 'admin' OR '1'='1'
    """
    # NEVER DO THIS:
    # result = await session.execute(
    #     text(f"SELECT * FROM users WHERE username = '{username}'")
    # )
    raise NotImplementedError("This is an intentional anti-pattern example")


async def search_VULNERABLE(session: AsyncSession, sort_by: str):
    """VULNERABLE: Unvalidated column name in ORDER BY.

    Attack: sort_by = "name; DROP TABLE users; --"
    """
    # NEVER DO THIS:
    # query = f"SELECT * FROM products ORDER BY {sort_by}"
    raise NotImplementedError("This is an intentional anti-pattern example")


# ─── Input Sanitization Layer ───────────────────────────────────────

class QuerySanitizer:
    """Input sanitization for search and filter parameters."""

    # Characters that should never appear in search queries
    DANGEROUS_PATTERNS = [
        r"('|--|;|/\\*|\\*/|xp_|sp_|exec|execute|drop|alter|create|insert|"
        r"update|delete|truncate|union|select|from|where|having|group by|order by)"
    ]

    @staticmethod
    def sanitize_search(term: str, max_length: int = 200) -> str:
        """Sanitize a search term for safe use in LIKE queries."""
        if not term:
            return ""
        # Truncate
        term = term[:max_length]
        # Remove null bytes
        term = term.replace("\\x00", "")
        # Strip excessive whitespace
        term = " ".join(term.split())
        return term

    @staticmethod
    def validate_identifier(name: str, allowed: set[str]) -> str:
        """Validate that an identifier is in the allowed whitelist."""
        if name not in allowed:
            raise ValueError(f"Invalid identifier: {name}. Allowed: {allowed}")
        return name

    @staticmethod
    def validate_int_list(values: list[Any]) -> list[int]:
        """Ensure all values in a list are valid integers."""
        try:
            return [int(v) for v in values]
        except (ValueError, TypeError) as e:
            raise ValueError(f"All values must be integers: {e}")


# ─── FastAPI Endpoints with Safe Query Building ─────────────────────

async def get_session():
    async with async_session() as session:
        yield session


@app.get("/users/{username}")
async def get_user_endpoint(
    username: str,
    session: AsyncSession = Depends(get_session),
):
    """Safe user lookup with parameterized query."""
    user = await get_user_safe(session, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "username": user.username, "email": user.email}


@app.get("/products/search")
async def search_products_endpoint(
    q: str = Query(default="", max_length=200),
    category: Optional[str] = Query(default=None, max_length=100),
    min_price: Optional[int] = Query(default=None, ge=0),
    max_price: Optional[int] = Query(default=None, ge=0),
    sort_by: str = Query(default="name", pattern="^(name|price|category|stock)$"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_session),
):
    """Safe product search with validated and parameterized filters."""
    sanitized_q = QuerySanitizer.sanitize_search(q)

    products = await search_products_safe(
        session,
        search_term=sanitized_q,
        category=category,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return {"results": [{"id": p.id, "name": p.name, "price": p.price} for p in products]}
```

SQL injection prevention checklist:

| Technique | Protection Level | Notes |
|-----------|-----------------|-------|
| Parameterized queries (bind params) | Essential | Always use :param or ? placeholders |
| ORM queries (SQLAlchemy, Prisma) | Strong | Parameterizes automatically for standard operations |
| Column name whitelisting | Essential for ORDER BY | Never interpolate column names from user input |
| Input type validation | Defense in depth | Validate types before they reach the query layer |
| LIKE escaping | Important | Escape %, _ in user-provided LIKE patterns |
| Least privilege DB user | Essential | App DB user should never have DROP/ALTER/GRANT |
| Prepared statements | Strong | Server-side preparation (connection pool dependent) |

Key patterns:

- ALWAYS use parameterized queries with bind parameters (:param or ?)
- NEVER concatenate or f-string user input into SQL strings
- Whitelist allowed column names for ORDER BY and dynamic queries
- Escape LIKE wildcards (%, _) in user-provided search terms
- Use ORM query builders for standard CRUD operations
- Validate and cast input types (int, uuid) before query construction
- Use the principle of least privilege for database users
- Log suspicious query patterns but never log the full query with user data'''
    ),
    (
        "validation/xss-sanitization",
        "How do I prevent XSS (Cross-Site Scripting) attacks with proper input sanitization and output encoding?",
        '''XSS prevention requires a defense-in-depth approach: sanitize on input, encode on output, and use Content Security Policy headers. Here is a comprehensive implementation for both server-side and client-side:

```python
"""XSS prevention: input sanitization, output encoding, and CSP integration."""

import re
import html
import logging
from typing import Optional
from enum import Enum

import bleach
from markupsafe import Markup, escape
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

app = FastAPI()


# ─── HTML Sanitization ──────────────────────────────────────────────

class SanitizationLevel(str, Enum):
    """Predefined sanitization profiles."""
    STRICT = "strict"       # Plain text only, no HTML
    BASIC = "basic"         # Bold, italic, links
    RICH = "rich"           # Full rich text (blog posts)
    ADMIN = "admin"         # Most HTML allowed (admin-only content)


class HTMLSanitizer:
    """Context-aware HTML sanitization using bleach."""

    PROFILES = {
        SanitizationLevel.STRICT: {
            "tags": [],
            "attributes": {},
            "protocols": [],
            "strip": True,
        },
        SanitizationLevel.BASIC: {
            "tags": ["b", "i", "em", "strong", "a", "br", "p"],
            "attributes": {
                "a": ["href", "title", "rel"],
            },
            "protocols": ["https", "mailto"],
            "strip": True,
        },
        SanitizationLevel.RICH: {
            "tags": [
                "h1", "h2", "h3", "h4", "h5", "h6",
                "p", "br", "hr",
                "b", "i", "em", "strong", "u", "s", "mark",
                "a", "img",
                "ul", "ol", "li",
                "blockquote", "pre", "code",
                "table", "thead", "tbody", "tr", "th", "td",
                "div", "span",
            ],
            "attributes": {
                "a": ["href", "title", "rel", "target"],
                "img": ["src", "alt", "width", "height", "loading"],
                "td": ["colspan", "rowspan"],
                "th": ["colspan", "rowspan"],
                "div": ["class"],
                "span": ["class"],
                "code": ["class"],
                "pre": ["class"],
            },
            "protocols": ["https", "mailto"],
            "strip": True,
        },
    }

    @classmethod
    def sanitize(
        cls,
        html_input: str,
        level: SanitizationLevel = SanitizationLevel.BASIC,
    ) -> str:
        """Sanitize HTML input according to the specified level."""
        if not html_input:
            return ""

        profile = cls.PROFILES[level]

        cleaned = bleach.clean(
            html_input,
            tags=profile["tags"],
            attributes=profile["attributes"],
            protocols=profile["protocols"],
            strip=profile["strip"],
        )

        # Additional protections
        cleaned = cls._remove_dangerous_patterns(cleaned)

        # Linkify URLs in text (converts plain URLs to safe links)
        if level != SanitizationLevel.STRICT:
            cleaned = bleach.linkify(
                cleaned,
                callbacks=[cls._linkify_callback],
                parse_email=False,
            )

        return cleaned

    @staticmethod
    def _remove_dangerous_patterns(text: str) -> str:
        """Remove patterns that could bypass sanitization."""
        # Remove javascript: protocol variants
        text = re.sub(
            r"(?i)(?:j\s*a\s*v\s*a\s*s\s*c\s*r\s*i\s*p\s*t)\s*:",
            "",
            text,
        )
        # Remove data: URLs (except images in rich mode, handled by bleach)
        text = re.sub(r"(?i)data\s*:", "", text)
        # Remove event handlers that might have slipped through
        text = re.sub(r"(?i)\bon\w+\s*=", "", text)
        # Remove expression() CSS
        text = re.sub(r"(?i)expression\s*\(", "", text)
        return text

    @staticmethod
    def _linkify_callback(attrs, new=False):
        """Ensure all links are safe (add rel=noopener, target=_blank)."""
        attrs[(None, "rel")] = "noopener noreferrer nofollow"
        attrs[(None, "target")] = "_blank"
        # Only allow https links
        href = attrs.get((None, "href"), "")
        if href and not href.startswith(("https://", "mailto:")):
            return None  # Remove non-https links
        return attrs

    @classmethod
    def plain_text(cls, html_input: str) -> str:
        """Strip all HTML and return plain text."""
        return bleach.clean(html_input, tags=[], strip=True).strip()


# ─── Output Encoding ────────────────────────────────────────────────

class OutputEncoder:
    """Context-aware output encoding for different insertion points."""

    @staticmethod
    def html_encode(text: str) -> str:
        """Encode for HTML body content. Escapes <, >, &, ', \""""
        return html.escape(text, quote=True)

    @staticmethod
    def html_attribute_encode(text: str) -> str:
        """Encode for HTML attribute values. Extra escaping for attributes."""
        encoded = html.escape(text, quote=True)
        # Additional attribute-specific escaping
        encoded = encoded.replace("`", "&#x60;")
        return encoded

    @staticmethod
    def js_encode(text: str) -> str:
        """Encode for JavaScript string literals."""
        replacements = {
            "\\": "\\\\",
            "'": "\\'",
            '"': '\\"',
            "\n": "\\n",
            "\r": "\\r",
            "\t": "\\t",
            "<": "\\x3c",  # Prevent </script> injection
            ">": "\\x3e",
            "&": "\\x26",
            "/": "\\/",
        }
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        return text

    @staticmethod
    def url_encode(text: str) -> str:
        """Encode for URL parameter values."""
        from urllib.parse import quote
        return quote(text, safe="")

    @staticmethod
    def css_encode(text: str) -> str:
        """Encode for CSS values."""
        return re.sub(r"[^a-zA-Z0-9\s]", lambda m: f"\\{ord(m.group()):06x}", text)


# ─── Pydantic Models with Built-in Sanitization ────────────────────

class CommentCreate(BaseModel):
    """User comment with automatic XSS sanitization."""
    author: str
    content: str
    allow_html: bool = False

    @field_validator("author")
    @classmethod
    def sanitize_author(cls, v: str) -> str:
        # Names are plain text only
        return HTMLSanitizer.plain_text(v)[:100]

    @field_validator("content")
    @classmethod
    def sanitize_content(cls, v: str, info) -> str:
        allow_html = info.data.get("allow_html", False)
        if allow_html:
            return HTMLSanitizer.sanitize(v, SanitizationLevel.BASIC)
        return HTMLSanitizer.plain_text(v)[:5000]


class BlogPostCreate(BaseModel):
    """Blog post with rich HTML support."""
    title: str
    slug: str
    body: str
    excerpt: str = ""

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        return HTMLSanitizer.plain_text(v)[:200]

    @field_validator("body")
    @classmethod
    def sanitize_body(cls, v: str) -> str:
        return HTMLSanitizer.sanitize(v, SanitizationLevel.RICH)

    @field_validator("excerpt")
    @classmethod
    def sanitize_excerpt(cls, v: str) -> str:
        return HTMLSanitizer.plain_text(v)[:500]

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        cleaned = re.sub(r"[^a-z0-9-]", "", v.lower())
        return cleaned[:100]


# ─── CSP Middleware ─────────────────────────────────────────────────

class SecurityHeadersMiddleware:
    """Add security headers to all responses."""

    def __init__(self, app, csp_policy: Optional[str] = None):
        self.app = app
        self.csp = csp_policy or self._default_csp()

    @staticmethod
    def _default_csp() -> str:
        return "; ".join([
            "default-src 'self'",
            "script-src 'self' 'strict-dynamic'",
            "style-src 'self' 'unsafe-inline'",  # Required for many CSS frameworks
            "img-src 'self' https: data:",
            "font-src 'self' https://fonts.gstatic.com",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",
        ])

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            async def send_with_headers(message):
                if message["type"] == "http.response.start":
                    headers = dict(message.get("headers", []))
                    security_headers = [
                        (b"content-security-policy", self.csp.encode()),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"x-xss-protection", b"0"),  # Disable legacy XSS auditor
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    ]
                    existing = list(message.get("headers", []))
                    existing.extend(security_headers)
                    message["headers"] = existing
                await send(message)
            await self.app(scope, receive, send_with_headers)
        else:
            await self.app(scope, receive, send)


app.add_middleware(SecurityHeadersMiddleware)


# ─── API Endpoints ──────────────────────────────────────────────────

@app.post("/comments")
async def create_comment(comment: CommentCreate):
    """Comments are automatically sanitized by Pydantic validators."""
    return {
        "author": comment.author,
        "content": comment.content,
        "safe": True,
    }


@app.post("/blog")
async def create_blog_post(post: BlogPostCreate):
    """Blog posts allow rich HTML, sanitized to safe subset."""
    return {
        "title": post.title,
        "slug": post.slug,
        "body_preview": post.body[:200],
    }


@app.get("/render/{user_id}")
async def render_user_profile(user_id: str):
    """Example of safe HTML rendering with output encoding."""
    # Simulate fetching user data (could contain XSS payloads)
    user_name = "<script>alert('xss')</script>John"
    user_bio = '<img src=x onerror="steal(document.cookie)">'

    # Output encoding based on context
    encoder = OutputEncoder()

    safe_html = f"""
    <div class="profile">
        <h1>{encoder.html_encode(user_name)}</h1>
        <p>{encoder.html_encode(user_bio)}</p>
        <a href="/users/{encoder.url_encode(user_id)}">Profile Link</a>
    </div>
    """
    return HTMLResponse(content=safe_html)
```

XSS prevention strategy by context:

| Insertion Context | Encoding Required | Example |
|------------------|-------------------|---------|
| HTML body | HTML entity encoding | &lt;script&gt; |
| HTML attribute | Attribute encoding + quotes | value="encoded" |
| JavaScript string | JS string escaping | \\x3cscript\\x3e |
| URL parameter | Percent encoding | %3Cscript%3E |
| CSS value | CSS hex encoding | \\00003c |
| JSON in HTML | JSON.stringify + HTML encode | Both layers |

Key patterns:

- Sanitize on input (remove dangerous HTML) AND encode on output (context-aware escaping)
- Use bleach for HTML sanitization with whitelisted tags and attributes
- Define sanitization levels per content type (comments vs blog posts vs admin)
- Use Content Security Policy (CSP) headers as defense in depth
- Set X-Content-Type-Options: nosniff to prevent MIME sniffing
- Disable the legacy X-XSS-Protection header (set to 0) and rely on CSP instead
- Use output encoding appropriate to the insertion context (HTML, JS, URL, CSS)
- In SPAs, use framework-provided escaping (React auto-escapes, Vue v-text)
- Never use dangerouslySetInnerHTML or v-html with unsanitized user data'''
    ),
]
