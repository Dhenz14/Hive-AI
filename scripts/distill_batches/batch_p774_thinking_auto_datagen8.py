r'''Phase 4A: Self-Improvement — Training Data Generation (Part 8)

Generate and evaluate training pairs for data handling topics.
Each answer creates 3 graded training pairs with quality analysis.
'''

PAIRS = [
    (
        "thinking/auto-datagen-data-serialization",
        r'''Generate 3 high-quality training pairs that teach data serialization (JSON, Protocol Buffers, MessagePack). For each pair, explain why it's effective training data.''',
        r'''<think>
To create effective training data for data serialization, I need to consider:
1. Common misconceptions: JSON is always the best choice, binary formats are premature optimization, serialization format does not matter for small payloads
2. Real scenarios: choosing between formats, migrating from JSON to a binary format, handling schema evolution
3. Difficulty progression: understanding JSON tradeoffs -> comparing formats -> handling schema evolution in production

The key insight is that serialization choices affect performance, correctness, and maintainability — they are architecture decisions, not just encoding details.
</think>

Here are 3 training pairs for data serialization:

**Pair 1 (Beginner):**
```
Q: I use JSON for everything in my application — API responses, configuration files, message queues, caching. Are there cases where JSON is not the best choice?

A: JSON is excellent for human-readable data exchange, but it has real limitations:

**Where JSON works well:**
- REST API responses (human-readable, universal client support)
- Configuration files (easy to edit by hand)
- Small payloads between services (<10KB)
- Data that needs to be inspected during debugging

**Where JSON falls short:**

1. **Size and speed for large payloads:**
   A list of 1 million records:
   - JSON: ~150MB, parse time ~3 seconds
   - MessagePack: ~80MB, parse time ~0.8 seconds
   - Protocol Buffers: ~60MB, parse time ~0.3 seconds

   For high-throughput message queues or caching, this difference compounds.

2. **No schema enforcement:**
   JSON is schemaless. A producer can send {"user_id": "123"} one day and {"userId": 123} the next. The consumer crashes.
   Protocol Buffers and Avro enforce schemas at compile/read time.

3. **No native binary data:**
   JSON cannot represent binary data (images, audio, compressed blobs) without Base64 encoding, which increases size by 33%.

4. **Numeric precision:**
   JSON numbers are IEEE 754 floats. Large integers lose precision:
   >>> json.loads('{"id": 9007199254740993}')
   {'id': 9007199254740993}  # Python handles this, but JavaScript rounds to 9007199254740992

**Practical alternatives:**

import msgpack
import json

data = {"users": [{"id": i, "name": f"user_{i}", "active": True} for i in range(10000)]}

# JSON
json_bytes = json.dumps(data).encode()  # 488KB, ~15ms to encode

# MessagePack — drop-in replacement for JSON, binary, no schema needed
msgpack_bytes = msgpack.packb(data)  # 278KB, ~4ms to encode
data_back = msgpack.unpackb(msgpack_bytes)  # Same data, same API

**Decision guide:**
- Public APIs: JSON (universal compatibility)
- Internal service communication with high throughput: MessagePack or Protocol Buffers
- Data stored long-term that needs schema evolution: Protocol Buffers or Avro
- Configuration: JSON, YAML, or TOML (human-readable)
```
**Why this works:** It starts from the common default (JSON everywhere) and shows specific cases where it fails with concrete numbers. The MessagePack example shows how easy it is to switch. The decision guide prevents both premature optimization and stubborn adherence to JSON.

**Pair 2 (Intermediate):**
```
Q: We are considering Protocol Buffers for communication between our microservices. How do we set it up, and what does the development workflow look like?

A: Protocol Buffers (protobuf) uses schema files (.proto) to define message structures, then generates code for your language. Here is the complete workflow:

**Step 1: Define the schema**
// proto/orders.proto
syntax = "proto3";
package orders;

message Order {
  string order_id = 1;
  string customer_id = 2;
  repeated OrderItem items = 3;
  OrderStatus status = 4;
  double total_amount = 5;
  google.protobuf.Timestamp created_at = 6;
}

message OrderItem {
  string product_id = 1;
  int32 quantity = 2;
  double unit_price = 3;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_CONFIRMED = 2;
  ORDER_STATUS_SHIPPED = 3;
  ORDER_STATUS_DELIVERED = 4;
}

**Step 2: Generate code**
pip install grpcio-tools
python -m grpc_tools.protoc -I proto --python_out=generated --pyi_out=generated proto/orders.proto

This generates orders_pb2.py with Python classes for each message.

**Step 3: Use in your service**
from generated import orders_pb2

# Serialize
order = orders_pb2.Order(
    order_id="ord-123",
    customer_id="cust-456",
    status=orders_pb2.ORDER_STATUS_CONFIRMED,
    total_amount=59.99,
)
order.items.append(orders_pb2.OrderItem(
    product_id="prod-789", quantity=2, unit_price=29.99
))
binary_data = order.SerializeToString()  # bytes, very compact

# Deserialize
order2 = orders_pb2.Order()
order2.ParseFromString(binary_data)
print(order2.order_id)  # "ord-123"

**Step 4: Use for inter-service communication**
# Producer service
import pika  # RabbitMQ
channel.basic_publish(exchange='', routing_key='orders',
                      body=order.SerializeToString(),
                      properties=pika.BasicProperties(content_type='application/protobuf'))

# Consumer service
def callback(ch, method, properties, body):
    order = orders_pb2.Order()
    order.ParseFromString(body)
    process_order(order)

**Key benefits over JSON:**
- Type safety: you cannot assign a string to an int32 field
- Compact: typically 3-10x smaller than JSON
- Fast: 10-100x faster serialization/deserialization
- Schema as documentation: the .proto file is the contract between services
- Forward/backward compatibility: built-in rules for adding/removing fields

**Development workflow consideration:**
Store .proto files in a shared repository. Both producer and consumer teams generate code from the same schema. Changes to the schema are reviewed like API changes.
```
**Why this works:** It covers the complete workflow from schema definition to code generation to actual usage, which tutorials often fragment. The RabbitMQ example grounds it in a real inter-service communication pattern. The comparison with JSON at the end reinforces when the switch is worthwhile.

**Pair 3 (Advanced):**
```
Q: We have been using Protocol Buffers for 2 years. Now we need to add and remove fields from our messages without breaking existing services that have not been updated yet. How do we handle schema evolution safely?

A: Schema evolution in protobuf is safe IF you follow the compatibility rules. Breaking these rules causes data corruption or crashes in services using the old schema.

**Safe changes (backward and forward compatible):**

1. **Adding a new field:**
   // v1
   message User {
     string id = 1;
     string name = 2;
   }

   // v2 — added email
   message User {
     string id = 1;
     string name = 2;
     string email = 3;  // New field
   }

   Safe because: old consumers ignore unknown field 3. New consumers see email as empty string if reading old data (proto3 default).

2. **Removing a field (with reservation):**
   // v3 — removed name, added display_name
   message User {
     string id = 1;
     reserved 2;  // Prevents reuse of field number 2
     reserved "name";  // Prevents reuse of field name
     string email = 3;
     string display_name = 4;
   }

   The reserved keyword is critical. Without it, someone might later add a new field with number 2, and old data with name would be misinterpreted.

**UNSAFE changes (will cause bugs):**

1. **Changing a field's type:**
   // v1: string customer_id = 1;
   // v2: int64 customer_id = 1;  // BREAKING: binary encoding is different
   Old services reading new data will get garbage.

2. **Reusing a field number:**
   // v1: string name = 2;
   // v2: (name removed)  int32 age = 2;  // BREAKING: old "name" bytes decoded as "age"
   This is why reserved exists.

3. **Renaming a field:**
   Renaming is safe in proto3 (field numbers matter, not names) UNLESS you also use JSON serialization, where names are used as keys.

**Schema evolution strategy for production:**

1. **Version your .proto files in Git.** Every change gets a PR with compatibility review.

2. **Use a schema registry** (like Buf or Confluent Schema Registry):
   # buf.yaml — Buf enforces compatibility rules automatically
   version: v1
   breaking:
     use:
       - FILE  # Prevent breaking changes across versions

   # CI check:
   buf breaking --against .git#branch=main
   # Fails the build if any breaking change is detected

3. **Deploy consumers before producers:**
   When adding a new field, deploy the consuming services first (they will handle the field when it appears). Then deploy the producer. This prevents a window where consumers receive unknown fields.

4. **Use wrapper types for optional fields with meaningful defaults:**
   // Proto3 cannot distinguish "field not set" from "field set to default value"
   // Use wrappers when the distinction matters:
   import "google/protobuf/wrappers.proto";
   message Product {
     string id = 1;
     google.protobuf.DoubleValue discount_percent = 2;
     // null = no discount set, 0.0 = explicitly 0% discount
   }

5. **Deprecate before removing:**
   message User {
     string id = 1;
     string name = 2 [deprecated = true];  // Warn but do not break
     string display_name = 3;
   }
   Give teams 2-3 release cycles to migrate before reserving the field.

**Comparison with other formats:**
- JSON: No schema evolution rules. Anything goes, which means anything can break.
- Avro: Schema evolution with a central schema registry. Better for data pipelines (Kafka).
- Protobuf: Schema evolution via field numbers. Better for RPC and service communication.
- Thrift: Similar to protobuf but less commonly used now.
```
**Why this works:** Schema evolution is where serialization gets hard and where real production incidents occur. The safe vs unsafe changes list prevents the most common mistakes. The Buf integration shows modern tooling for enforcing compatibility in CI. The deployment order advice (consumers first) is operational wisdom that comes from experience, not documentation.

**Quality assessment:**
- Concept coverage: JSON limitations, protobuf setup and workflow, schema evolution rules, compatibility enforcement
- Realism: Progresses from "should I use something other than JSON" to "set up protobuf" to "evolve schemas safely in production" — the actual adoption journey
- Difficulty curve: Format selection -> implementation workflow -> safe evolution in distributed systems'''
    ),
    (
        "thinking/auto-datagen-data-validation",
        r'''Generate 3 high-quality training pairs that teach data validation (Pydantic, marshmallow, JSON Schema). For each pair, explain why it's effective training data.''',
        r'''<think>
For data validation, I need to consider:
1. Common misconceptions: validation is just type checking, client-side validation is sufficient, one validation layer is enough
2. Real scenarios: validating API inputs, validating configuration, validating data between services
3. Difficulty progression: basic Pydantic models -> advanced validation patterns -> choosing and combining validation approaches

Pydantic v2 is the most popular choice in the Python ecosystem, so I should focus on it while covering alternatives.
</think>

Here are 3 training pairs for data validation:

**Pair 1 (Beginner):**
```
Q: I have a FastAPI endpoint that accepts user registration data. How do I validate the input properly using Pydantic?

A: Pydantic models define expected structure, types, and constraints. FastAPI uses them automatically for request validation.

from pydantic import BaseModel, Field, field_validator, EmailStr
from datetime import date

class UserRegistration(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=50)
    birth_date: date | None = None  # Optional
    referral_code: str | None = Field(default=None, pattern=r'^[A-Z0-9]{6}$')

    @field_validator('password')
    @classmethod
    def password_complexity(cls, v):
        if v.lower() == v or v.upper() == v:
            raise ValueError('Password must contain both upper and lowercase letters')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

    @field_validator('display_name')
    @classmethod
    def clean_display_name(cls, v):
        cleaned = v.strip()
        if not cleaned:
            raise ValueError('Display name cannot be only whitespace')
        return cleaned

    @field_validator('birth_date')
    @classmethod
    def validate_age(cls, v):
        if v is not None:
            age = (date.today() - v).days // 365
            if age < 13:
                raise ValueError('Must be at least 13 years old')
            if age > 150:
                raise ValueError('Invalid birth date')
        return v

**Usage in FastAPI:**
@app.post("/register")
async def register(user: UserRegistration):
    # By this point, all validation has passed:
    # - email is a valid email format
    # - password meets complexity requirements
    # - display_name is trimmed and non-empty
    # - birth_date (if provided) indicates age >= 13
    # - referral_code (if provided) matches the pattern
    create_user(user)

**What happens on invalid input:**
POST /register {"email": "bad", "password": "short", "display_name": "  "}

Response (422):
{
  "detail": [
    {"loc": ["body", "email"], "msg": "value is not a valid email address"},
    {"loc": ["body", "password"], "msg": "String should have at least 10 characters"},
    {"loc": ["body", "display_name"], "msg": "Display name cannot be only whitespace"}
  ]
}

**Key benefits:**
- Validation errors list ALL problems, not just the first one
- Error messages include the field path (loc) for precise client-side error display
- Type coercion happens automatically (string "2024-01-15" becomes a date object)
- The model IS the documentation — OpenAPI/Swagger docs are generated from it
```
**Why this works:** It shows a realistic registration model with multiple validation types (built-in constraints, custom validators, regex patterns, optional fields). The error response example demonstrates how Pydantic communicates validation failures, which is critical for frontend integration. The cleaning behavior (stripping whitespace) shows that validators can transform data, not just reject it.

**Pair 2 (Intermediate):**
```
Q: I need to validate complex nested data structures with conditional validation — for example, a shipping form where the required fields depend on the selected shipping method. How do I handle this with Pydantic?

A: Use Pydantic's model_validator for cross-field validation and discriminated unions for type-dependent structures.

**Approach 1: model_validator for cross-field rules**
from pydantic import BaseModel, model_validator
from typing import Literal

class ShippingInfo(BaseModel):
    method: Literal["standard", "express", "pickup"]
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    pickup_location_id: str | None = None

    @model_validator(mode='after')
    def validate_shipping_fields(self):
        if self.method in ("standard", "express"):
            required = ["address_line1", "city", "state", "zip_code"]
            missing = [f for f in required if not getattr(self, f)]
            if missing:
                raise ValueError(f"Shipping method '{self.method}' requires: {', '.join(missing)}")
        elif self.method == "pickup":
            if not self.pickup_location_id:
                raise ValueError("Pickup method requires pickup_location_id")
        return self

**Approach 2: Discriminated unions (cleaner for complex differences)**
from pydantic import BaseModel, Field
from typing import Annotated, Union

class StandardShipping(BaseModel):
    method: Literal["standard"] = "standard"
    address_line1: str
    city: str
    state: str = Field(pattern=r'^[A-Z]{2}$')
    zip_code: str = Field(pattern=r'^\d{5}(-\d{4})?$')

class ExpressShipping(BaseModel):
    method: Literal["express"] = "express"
    address_line1: str
    city: str
    state: str = Field(pattern=r'^[A-Z]{2}$')
    zip_code: str = Field(pattern=r'^\d{5}(-\d{4})?$')
    phone: str  # Required for express — courier needs to call

class PickupShipping(BaseModel):
    method: Literal["pickup"] = "pickup"
    pickup_location_id: str
    preferred_time: str | None = None

ShippingMethod = Annotated[
    Union[StandardShipping, ExpressShipping, PickupShipping],
    Field(discriminator='method')
]

class Order(BaseModel):
    items: list[OrderItem]
    shipping: ShippingMethod  # Pydantic picks the right model based on 'method'

# Input: {"items": [...], "shipping": {"method": "express", ...}}
# Pydantic selects ExpressShipping and validates phone is present

**When to use each approach:**
- model_validator: when the variations are small (a few conditional required fields)
- Discriminated unions: when each variant has substantially different fields and validation rules
- Avoid deeply nesting validators — if validation logic exceeds 20 lines, extract it to a separate function

**Advanced pattern: Reusable validators**
from pydantic import AfterValidator

def must_be_positive(v: float) -> float:
    if v <= 0:
        raise ValueError("Must be positive")
    return v

PositiveFloat = Annotated[float, AfterValidator(must_be_positive)]

class OrderItem(BaseModel):
    product_id: str
    quantity: PositiveFloat
    unit_price: PositiveFloat  # Reused validator
```
**Why this works:** Conditional validation is one of the hardest real-world validation problems. Showing both the model_validator approach and discriminated unions with clear guidance on when to use each teaches design judgment. The Annotated type pattern for reusable validators is a Pydantic v2 best practice.

**Pair 3 (Advanced):**
```
Q: We have a data pipeline where data flows through multiple systems: API input (Python/FastAPI), message queue (JSON), analytics database (SQL), and a reporting frontend (TypeScript). How do we ensure data validity across all these boundaries?

A: This is the "schema consistency across boundaries" problem. No single validation library works everywhere, so you need a strategy that keeps schemas synchronized.

**Approach: Single source of truth with code generation**

Option A: JSON Schema as the source of truth
JSON Schema is language-agnostic and supported everywhere:

{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "title": "Order",
  "properties": {
    "order_id": {"type": "string", "format": "uuid"},
    "customer_id": {"type": "string", "format": "uuid"},
    "items": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "properties": {
          "product_id": {"type": "string"},
          "quantity": {"type": "integer", "minimum": 1},
          "unit_price": {"type": "number", "exclusiveMinimum": 0}
        },
        "required": ["product_id", "quantity", "unit_price"]
      }
    },
    "total": {"type": "number", "exclusiveMinimum": 0},
    "status": {"type": "string", "enum": ["pending", "confirmed", "shipped"]}
  },
  "required": ["order_id", "customer_id", "items", "total", "status"]
}

Generate language-specific code from this:
- Python: datamodel-code-generator --input order.json --output models.py (generates Pydantic models)
- TypeScript: json-schema-to-typescript order.json > Order.ts (generates TypeScript interfaces)
- SQL: derive column types and CHECK constraints from the schema

Option B: Pydantic as the source of truth (Python-first teams)
Use Pydantic models and export JSON Schema for other systems:

class Order(BaseModel):
    order_id: UUID
    customer_id: UUID
    items: list[OrderItem] = Field(min_length=1)
    total: float = Field(gt=0)
    status: Literal["pending", "confirmed", "shipped"]

# Export for other systems
schema = Order.model_json_schema()
Path("schemas/order.json").write_text(json.dumps(schema, indent=2))

**Validation at each boundary:**

1. **API input (Python):** Pydantic model validates structure and types
2. **Message queue:** Validate JSON against the schema before publishing AND after consuming:
   # Producer
   order = Order(**data)  # Validate
   queue.publish(order.model_dump_json())

   # Consumer (different service, possibly different language)
   from jsonschema import validate
   validate(instance=json.loads(message), schema=order_schema)

3. **Database:** Use CHECK constraints and NOT NULL as a last line of defense:
   CREATE TABLE orders (
     order_id UUID PRIMARY KEY,
     total NUMERIC CHECK (total > 0),
     status TEXT CHECK (status IN ('pending', 'confirmed', 'shipped'))
   );

4. **Frontend:** TypeScript interfaces from the same schema:
   interface Order {
     order_id: string;
     items: OrderItem[];
     total: number;
     status: 'pending' | 'confirmed' | 'shipped';
   }

**CI pipeline for schema consistency:**
- Store schemas in a shared repository
- On PR: run compatibility check (ensure new schemas are backward-compatible)
- On merge: auto-generate code for all languages and push to respective repos
- On deploy: run integration tests that send data through the full pipeline

**The key principle:** Validate at every boundary, not just at the entry point. Data can be corrupted by bugs at any stage (serialization errors, queue message truncation, database trigger side effects). Each boundary should independently verify the data it receives.
```
**Why this works:** It addresses the real-world problem of maintaining validation consistency across polyglot systems. The dual approach (JSON Schema first vs Pydantic first) gives teams flexibility. The CI pipeline for schema consistency is the production-grade solution that prevents schema drift. The "validate at every boundary" principle is the core architectural insight.

**Quality assessment:**
- Concept coverage: Pydantic basics, conditional/discriminated validation, cross-system schema consistency, code generation from schemas
- Realism: Progresses from "validate API input" to "handle complex conditional validation" to "maintain schemas across a distributed system" — real data validation challenges at increasing scale
- Difficulty curve: Single-model validation -> complex nested validation patterns -> cross-system schema architecture'''
    ),
    (
        "thinking/auto-datagen-data-migration",
        r'''Generate 3 high-quality training pairs that teach data migration strategies. For each pair, explain why it's effective training data.''',
        r'''<think>
For data migration strategies, I need to consider:
1. Common misconceptions: migrations are just ALTER TABLE, downtime is always required, you can roll back any migration, data migration = schema migration
2. Real scenarios: adding columns safely, migrating large tables without downtime, handling data transformation
3. Difficulty progression: basic schema migrations -> zero-downtime migrations -> large-scale data migration strategies

Migrations are one of the highest-risk operations in production systems, so the training data should emphasize safety and reversibility.
</think>

Here are 3 training pairs for data migration strategies:

**Pair 1 (Beginner):**
```
Q: What is the difference between a schema migration and a data migration? How do I manage migrations in a Python project?

A: They serve different purposes and have different risk profiles:

**Schema migration** = Changing the structure of the database
- Adding/removing columns, tables, indexes
- Changing column types or constraints
- Example: ALTER TABLE users ADD COLUMN phone VARCHAR(20);

**Data migration** = Changing the values stored in the database
- Backfilling a new column with computed values
- Transforming data format (e.g., splitting full_name into first_name + last_name)
- Moving data between tables during a restructure
- Example: UPDATE users SET phone_normalized = regexp_replace(phone, '[^0-9]', '');

**Managing migrations with Alembic (SQLAlchemy):**

# Install and initialize
pip install alembic
alembic init migrations

# Create a migration
alembic revision --autogenerate -m "add phone column to users"

# Generated migration file:
def upgrade():
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))

def downgrade():
    op.drop_column('users', 'phone')

# Apply migration
alembic upgrade head

# Rollback one step
alembic downgrade -1

**Best practices:**
1. **Always write both upgrade and downgrade.** You will need to rollback someday.
2. **One logical change per migration.** Do not combine "add phone column" with "rename email table" — if one fails, you cannot partially rollback.
3. **Never edit a migration that has been applied in production.** Create a new migration to fix issues.
4. **Test migrations on a copy of production data,** not just an empty test database. Schema changes may fail on real data (e.g., adding NOT NULL to a column that has NULLs).
5. **Separate schema and data migrations** into distinct migration files. Schema changes are fast; data migrations can be slow and should be monitored separately.

**Migration file naming convention:**
001_create_users_table.py
002_add_phone_to_users.py
003_backfill_phone_from_profiles.py  # Data migration, clearly labeled
004_add_not_null_to_phone.py         # Only safe after backfill is complete
```
**Why this works:** It distinguishes schema and data migrations clearly — a distinction many developers miss. The Alembic example is practical and complete. The best practices (especially "test on production data copy" and "separate schema from data migrations") prevent real incidents. The naming convention shows how to sequence dependent migrations.

**Pair 2 (Intermediate):**
```
Q: We need to add a NOT NULL column to a table with 50 million rows in PostgreSQL. Our application cannot tolerate downtime. How do we do this safely?

A: Adding a NOT NULL column with a default to a large table can lock the table for minutes or hours, depending on the database version. Here is the safe zero-downtime approach:

**The naive approach (causes downtime):**
ALTER TABLE orders ADD COLUMN region VARCHAR(50) NOT NULL DEFAULT 'unknown';
-- In PostgreSQL < 11, this rewrites the entire table while holding an ACCESS EXCLUSIVE lock
-- Even in PostgreSQL 11+, this is safer but adding a constraint still locks

**Safe multi-step approach:**

**Step 1: Add the column as nullable (instant, no lock)**
ALTER TABLE orders ADD COLUMN region VARCHAR(50);
-- This is metadata-only in modern PostgreSQL. No table rewrite. Milliseconds.

**Step 2: Deploy application code that writes to the new column**
Update your application to populate region for all new rows:
# New code path — all new inserts include region
db.execute("INSERT INTO orders (..., region) VALUES (..., %s)", (..., region))

**Step 3: Backfill existing rows in batches**
Do NOT run a single UPDATE on 50M rows — it generates enormous WAL, bloats the table, and can exhaust disk space.

-- Backfill in batches of 10,000
DO $$
DECLARE
    batch_size INT := 10000;
    updated INT;
BEGIN
    LOOP
        UPDATE orders
        SET region = compute_region(shipping_address)
        WHERE region IS NULL
        AND id IN (
            SELECT id FROM orders WHERE region IS NULL LIMIT batch_size
            FOR UPDATE SKIP LOCKED  -- Avoid blocking concurrent transactions
        );
        GET DIAGNOSTICS updated = ROW_COUNT;
        RAISE NOTICE 'Updated % rows', updated;
        IF updated = 0 THEN EXIT; END IF;
        PERFORM pg_sleep(0.1);  -- Brief pause to reduce load
        COMMIT;
    END LOOP;
END $$;

Monitor progress: SELECT COUNT(*) FROM orders WHERE region IS NULL;

**Step 4: Add the NOT NULL constraint with validation**
-- In PostgreSQL 12+:
ALTER TABLE orders ADD CONSTRAINT orders_region_not_null
    CHECK (region IS NOT NULL) NOT VALID;  -- Instant, does not scan existing rows

-- Then validate asynchronously (holds a weaker SHARE UPDATE EXCLUSIVE lock):
ALTER TABLE orders VALIDATE CONSTRAINT orders_region_not_null;

-- Optionally, convert to a proper NOT NULL:
ALTER TABLE orders ALTER COLUMN region SET NOT NULL;
ALTER TABLE orders DROP CONSTRAINT orders_region_not_null;

**Step 5: Add a default for future rows**
ALTER TABLE orders ALTER COLUMN region SET DEFAULT 'unknown';

**Total migration time:** hours to days for the backfill, but zero downtime. Each step is independently deployable and reversible.

**Rollback plan at each step:**
- Step 1: DROP COLUMN (instant for unused column)
- Step 2: Deploy old application code
- Step 3: No rollback needed (data is better with region)
- Step 4: DROP CONSTRAINT
```
**Why this works:** It addresses the exact scenario that causes real production outages — a developer runs a naive ALTER TABLE and locks a table for 30 minutes. The batched backfill with SKIP LOCKED and pg_sleep is production-tested technique. The NOT VALID + VALIDATE pattern for constraints is PostgreSQL-specific knowledge that avoids long-held locks.

**Pair 3 (Advanced):**
```
Q: We are splitting our monolithic database into two databases — the orders service will have its own database separate from the users database. How do we migrate the data and update the application without downtime?

A: This is a database decomposition migration, one of the hardest operations in software engineering. Use the "expand-contract" pattern over multiple releases.

**Current state:**
- Single database with orders table referencing users table via foreign key
- Application JOINs orders and users in queries

**Target state:**
- Orders database (orders service owns it)
- Users database (users service owns it)
- No cross-database JOINs, services communicate via API

**Phase 1: Dual-write (Release N)**
Continue reading from the old database, but start writing to both:

class OrderService:
    def create_order(self, order_data):
        # Write to old database (source of truth)
        old_db.orders.insert(order_data)
        # Also write to new orders database
        try:
            new_orders_db.orders.insert(order_data)
        except Exception as e:
            log.error("Dual-write to new DB failed", error=e)
            # Do NOT fail the request — old DB is still source of truth
            metrics.increment("dual_write_failure")

Monitor dual-write failures. If they exceed a threshold, investigate before proceeding.

**Phase 2: Backfill historical data**
Migrate existing orders from old DB to new DB:

def backfill_orders():
    last_id = 0
    while True:
        batch = old_db.execute(
            "SELECT * FROM orders WHERE id > %s ORDER BY id LIMIT 1000", (last_id,))
        if not batch:
            break
        for order in batch:
            new_orders_db.upsert(order)  # UPSERT to handle dual-write overlap
            last_id = order["id"]
        time.sleep(0.1)

After backfill, verify:
SELECT COUNT(*) FROM old_db.orders;  -- Should equal
SELECT COUNT(*) FROM new_orders_db.orders;

Run a checksumming job to verify data integrity.

**Phase 3: Replace JOINs with API calls (Release N+1)**
Before:
SELECT o.*, u.name, u.email
FROM orders o JOIN users u ON o.user_id = u.id
WHERE o.id = ?

After:
order = orders_db.get_order(order_id)
user = user_service.get_user(order.user_id)  # API call
response = {**order, "customer_name": user["name"]}

Cache user data aggressively (users change rarely) to avoid latency impact.

**Phase 4: Switch reads to new database (Release N+2)**
class OrderService:
    def get_order(self, order_id):
        # PRIMARY: read from new database
        order = new_orders_db.get_order(order_id)
        if order is None:
            # FALLBACK: check old database (should never happen after backfill)
            order = old_db.get_order(order_id)
            if order:
                log.warning("Order found in old DB but not new", order_id=order_id)
                new_orders_db.upsert(order)  # Self-healing
        return order

Monitor the fallback path. Once it hits zero for 2+ weeks, remove it.

**Phase 5: Stop writing to old database (Release N+3)**
Remove the dual-write code. The new orders database is now the sole source of truth.

**Phase 6: Remove old orders table (Release N+4)**
After verifying no services read from the old table (check query logs):
-- Archive first
CREATE TABLE old_orders_archive AS SELECT * FROM orders;
-- Then drop
DROP TABLE orders;

**Timeline:** This entire process takes 2-4 months for a critical table. Do not rush it.

**What can go wrong:**
- Dual-write divergence: new DB misses writes due to transient failures -> checksumming job catches this
- JOIN replacement performance: API calls are slower than JOINs -> cache aggressively, batch requests
- Referential integrity: cannot use foreign keys across databases -> enforce at application level
- Transaction boundaries: cannot do cross-database transactions -> use eventual consistency or saga pattern
```
**Why this works:** It teaches the hardest migration scenario with a concrete, phased approach. Each phase is a separate release with clear rollback options. The self-healing fallback pattern and checksumming verification reflect real production experience. The timeline callout (2-4 months) sets realistic expectations and prevents management pressure to rush.

**Quality assessment:**
- Concept coverage: Schema vs data migrations, zero-downtime column additions, database decomposition with dual-write
- Realism: Progresses from "manage migrations properly" to "add a column without downtime" to "split a database between services" — actual challenges at increasing organizational scale
- Difficulty curve: Migration fundamentals -> production-safe schema changes -> multi-phase database decomposition'''
    ),
    (
        "thinking/auto-datagen-etl-pipeline",
        r'''Generate 3 high-quality training pairs that teach ETL pipeline design. For each pair, explain why it's effective training data.''',
        r'''<think>
For ETL pipeline design, I need to consider:
1. Common misconceptions: ETL is just moving data, batch is always simpler, schema-on-read means no validation, ETL and ELT are the same
2. Real scenarios: building a data ingestion pipeline, handling failures and retries, designing for scalability
3. Difficulty progression: basic ETL concepts and implementation -> error handling and monitoring -> scalable pipeline architecture

I should focus on practical implementation rather than just theory, and use realistic tools and patterns.
</think>

Here are 3 training pairs for ETL pipeline design:

**Pair 1 (Beginner):**
```
Q: What is ETL, how does it differ from ELT, and when should I use each? Show me a simple Python ETL pipeline.

A: ETL (Extract, Transform, Load) and ELT (Extract, Load, Transform) differ in where transformation happens:

**ETL:** Extract data from source -> Transform in a processing layer (Python, Spark) -> Load into destination
- Use when: target system has limited compute (traditional data warehouses), transformations are complex, data needs cleaning before storage

**ELT:** Extract data from source -> Load raw into destination -> Transform using the destination's compute engine (SQL in BigQuery/Snowflake)
- Use when: target has powerful compute (modern cloud warehouses), you want to keep raw data, analysts write their own transforms

**Simple ETL pipeline in Python:**

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path

def extract(source_path: str) -> list[dict]:
    """Extract: Read raw data from CSV files."""
    records = []
    with open(source_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    print(f"Extracted {len(records)} records from {source_path}")
    return records

def transform(records: list[dict]) -> list[dict]:
    """Transform: Clean, validate, and reshape data."""
    transformed = []
    errors = []
    for i, record in enumerate(records):
        try:
            clean = {
                "customer_name": record["name"].strip().title(),
                "email": record["email"].strip().lower(),
                "total_spent": round(float(record["amount"]), 2),
                "signup_date": datetime.strptime(
                    record["date"], "%m/%d/%Y").strftime("%Y-%m-%d"),
                "is_active": record.get("status", "").lower() == "active",
            }
            if clean["total_spent"] < 0:
                errors.append((i, "Negative amount"))
                continue
            if "@" not in clean["email"]:
                errors.append((i, "Invalid email"))
                continue
            transformed.append(clean)
        except (ValueError, KeyError) as e:
            errors.append((i, str(e)))

    print(f"Transformed: {len(transformed)} valid, {len(errors)} errors")
    if errors:
        for row_num, error in errors[:5]:
            print(f"  Row {row_num}: {error}")
    return transformed

def load(records: list[dict], db_path: str):
    """Load: Insert cleaned data into the destination database."""
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS customers
        (customer_name TEXT, email TEXT UNIQUE, total_spent REAL,
         signup_date TEXT, is_active BOOLEAN, loaded_at TEXT)""")

    loaded = 0
    for record in records:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO customers VALUES (?, ?, ?, ?, ?, ?)",
                (*record.values(), datetime.utcnow().isoformat()))
            loaded += 1
        except sqlite3.Error as e:
            print(f"Load error: {e}")
    conn.commit()
    print(f"Loaded {loaded} records into {db_path}")

# Run the pipeline
if __name__ == "__main__":
    raw_data = extract("sales_data.csv")
    clean_data = transform(raw_data)
    load(clean_data, "analytics.db")

**Key principles:**
- Each phase (E, T, L) is a separate function — testable and replaceable independently
- Transform phase handles errors without stopping the whole pipeline
- Load uses UPSERT (INSERT OR REPLACE) so the pipeline is idempotent — running it twice does not create duplicates
- Error records are logged, not silently dropped
```
**Why this works:** It shows a complete, runnable ETL pipeline that demonstrates all three phases clearly. The error handling in the transform phase is realistic — real data is messy. The idempotency point is the most important ETL principle and is called out explicitly.

**Pair 2 (Intermediate):**
```
Q: Our ETL pipeline processes data from 5 different APIs daily. Sometimes APIs are down, data is malformed, or the pipeline crashes mid-run. How do I make it resilient?

A: Build resilience at every layer: retries, checkpointing, dead letter queues, and monitoring.

**1. Retry with exponential backoff for extraction:**
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    before_sleep=lambda state: print(f"Retry {state.attempt_number} in {state.next_action.sleep}s")
)
def extract_from_api(endpoint: str, params: dict) -> dict:
    response = httpx.get(endpoint, params=params, timeout=30)
    response.raise_for_status()
    return response.json()

**2. Checkpointing for resumable pipelines:**
If the pipeline crashes after processing 3 of 5 data sources, do not restart from scratch:

import json
from pathlib import Path

class PipelineCheckpoint:
    def __init__(self, pipeline_id: str):
        self.path = Path(f"/var/etl/checkpoints/{pipeline_id}.json")
        self.state = self._load()

    def _load(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"completed_sources": [], "last_run": None}

    def mark_complete(self, source: str):
        self.state["completed_sources"].append(source)
        self.path.write_text(json.dumps(self.state))

    def is_complete(self, source: str) -> bool:
        return source in self.state["completed_sources"]

    def reset(self):
        self.state = {"completed_sources": [], "last_run": None}
        self.path.write_text(json.dumps(self.state))

# Usage:
checkpoint = PipelineCheckpoint("daily-ingest-2025-01-15")
for source in ["api_a", "api_b", "api_c", "api_d", "api_e"]:
    if checkpoint.is_complete(source):
        print(f"Skipping {source} (already complete)")
        continue
    data = extract_from_api(ENDPOINTS[source], params)
    transformed = transform(data)
    load(transformed, destination)
    checkpoint.mark_complete(source)

**3. Dead letter queue for bad records:**
Instead of failing or silently dropping, route bad records to a separate table:

def transform_with_dlq(records, pipeline_run_id):
    good, bad = [], []
    for record in records:
        try:
            good.append(transform_record(record))
        except Exception as e:
            bad.append({
                "original": record,
                "error": str(e),
                "pipeline_run": pipeline_run_id,
                "timestamp": datetime.utcnow().isoformat()
            })
    if bad:
        db.insert_many("etl_dead_letters", bad)
        alert(f"{len(bad)} records sent to dead letter queue")
    return good

**4. Pipeline monitoring and alerting:**
Track these metrics for every run:
- Records extracted, transformed, loaded (completeness)
- Records rejected (quality)
- Duration per phase (performance)
- Source API response times (dependency health)

pipeline_metrics = {
    "run_id": run_id,
    "source": source_name,
    "extracted": len(raw_data),
    "transformed": len(clean_data),
    "rejected": len(raw_data) - len(clean_data),
    "loaded": loaded_count,
    "duration_seconds": elapsed,
    "status": "success"  # or "partial_failure" or "failure"
}
db.insert("etl_run_metrics", pipeline_metrics)

# Alert if rejection rate exceeds threshold
if pipeline_metrics["rejected"] / pipeline_metrics["extracted"] > 0.05:
    alert(f"High rejection rate: {rejection_rate:.1%} for {source_name}")
```
**Why this works:** It covers the four pillars of resilient ETL: retries, checkpointing, dead letter queues, and monitoring. Each is shown with concrete, usable code. The checkpointing pattern for resumable pipelines is especially valuable because most ETL tutorials skip it, yet it is essential when pipelines take hours.

**Pair 3 (Advanced):**
```
Q: We are processing 50GB of data daily from multiple sources. Our Python ETL scripts are too slow and memory-hungry. How do we scale this up without rewriting everything?

A: Scale incrementally: first optimize the Python code, then add parallelism, then consider distributed processing if still needed.

**Level 1: Streaming instead of loading everything into memory**

# BAD: loads entire dataset into memory
data = json.load(open("huge_file.json"))  # 50GB file -> 50GB+ RAM

# GOOD: stream with ijson (incremental JSON parser)
import ijson

def stream_records(filepath):
    with open(filepath, 'rb') as f:
        for record in ijson.items(f, 'item'):
            yield record  # One record at a time, constant memory

# GOOD: stream CSV
def stream_csv(filepath):
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row  # Memory: ~1 row at a time

# Process in batches for efficient DB writes
def process_in_batches(stream, batch_size=5000):
    batch = []
    for record in stream:
        batch.append(transform(record))
        if len(batch) >= batch_size:
            load_batch(batch)
            batch = []
    if batch:
        load_batch(batch)

**Level 2: Parallel extraction from multiple sources**

import asyncio
import httpx

async def extract_all_sources(sources: list[dict]) -> dict:
    async with httpx.AsyncClient() as client:
        tasks = [extract_source(client, s) for s in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    return {s["name"]: r for s, r in zip(sources, results)}

async def extract_source(client, source):
    pages = []
    url = source["url"]
    while url:
        response = await client.get(url, timeout=60)
        data = response.json()
        pages.extend(data["results"])
        url = data.get("next")  # Pagination
    return pages

# For CPU-bound transformation, use multiprocessing:
from concurrent.futures import ProcessPoolExecutor

def parallel_transform(records, num_workers=4):
    chunks = [records[i::num_workers] for i in range(num_workers)]
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = executor.map(transform_chunk, chunks)
    return [r for chunk_result in results for r in chunk_result]

**Level 3: Incremental processing (process only new/changed data)**

Instead of processing 50GB daily, process only what changed:

def extract_incremental(source, last_run_timestamp):
    """Only fetch records modified since last run."""
    return api.get_records(
        modified_after=last_run_timestamp,
        order_by="modified_at"
    )

# For database sources, use change data capture (CDC):
# - PostgreSQL: logical replication slots
# - MySQL: binlog
# - Tools: Debezium, Airbyte

**Level 4: Distributed processing (when Python alone is not enough)**

If after streaming, parallelism, and incremental processing you still need more:

# Apache Spark with PySpark — your transform functions translate naturally
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lower, trim

spark = SparkSession.builder.appName("etl").getOrCreate()

# Extract
raw_df = spark.read.json("s3://data-lake/raw/2025-01-15/")

# Transform (same logic, distributed execution)
clean_df = (raw_df
    .filter(col("amount") > 0)
    .withColumn("email", lower(trim(col("email"))))
    .withColumn("signup_date", col("date").cast("date"))
)

# Load
clean_df.write.mode("append").parquet("s3://data-lake/processed/customers/")

**Decision framework:**
- <1GB/day: Plain Python with streaming is fine
- 1-10GB/day: Add async extraction + multiprocessing transforms
- 10-100GB/day: Incremental processing + consider Spark or DuckDB
- 100GB+/day: Spark, Flink, or a managed service (Databricks, AWS Glue)

Do NOT jump to Spark for small data. The overhead of cluster management exceeds the processing time saved until you hit 10GB+ daily.
```
**Why this works:** It provides a scaling ladder instead of jumping to distributed systems. The streaming pattern is the most impactful optimization and is shown first. The decision framework with concrete thresholds prevents both premature optimization and under-engineering. The progression from Python to PySpark shows how existing logic translates, making the eventual migration less scary.

**Quality assessment:**
- Concept coverage: ETL vs ELT, basic pipeline implementation, resilience patterns (retry/checkpoint/DLQ/monitoring), scaling strategies
- Realism: Progresses from "build your first pipeline" to "make it resilient" to "make it scale" — the actual growth path of data engineering projects
- Difficulty curve: Simple three-function pipeline -> production resilience patterns -> distributed processing architecture'''
    ),
    (
        "thinking/auto-datagen-data-consistency",
        r'''Generate 3 high-quality training pairs that teach data consistency in distributed systems. For each pair, explain why it's effective training data.''',
        r'''<think>
For data consistency in distributed systems, I need to consider:
1. Common misconceptions: distributed transactions solve everything, eventual consistency means data loss, CAP theorem means you must choose between consistency and availability always
2. Real scenarios: handling failures in multi-service operations, implementing eventual consistency correctly, choosing consistency levels
3. Difficulty progression: understanding consistency models -> implementing the saga pattern -> designing systems that handle inconsistency gracefully

This is one of the hardest topics in software engineering, so concrete examples are essential.
</think>

Here are 3 training pairs for data consistency in distributed systems:

**Pair 1 (Beginner):**
```
Q: In a monolithic application, I use database transactions to keep data consistent. Now we are moving to microservices where data is spread across multiple databases. How do I maintain consistency?

A: In a monolith, a single transaction guarantees atomicity: either all changes commit or none do. In microservices, you cannot do this across databases. You have three options, listed from simplest to most complex:

**Option 1: Keep the data together (best when possible)**
If two pieces of data must always be consistent, they belong in the same service. Do not split them across microservices just because the code is organized that way.

Example: If creating an order always requires reserving inventory, maybe orders and inventory belong in the same service. The simplest distributed systems problem is the one you do not create.

**Option 2: Eventual consistency with events**
Accept that data may be temporarily inconsistent. The system converges to consistency eventually:

# Order service creates the order
order = create_order(items)  # Committed to orders DB
event_bus.publish("order.created", {"order_id": order.id, "items": items})

# Inventory service handles the event (async)
@event_handler("order.created")
def reserve_inventory(event):
    for item in event["items"]:
        inventory_db.reserve(item["product_id"], item["quantity"])

If the inventory service is down, the event stays in the queue and is processed when the service recovers. The data is inconsistent during the delay but eventually consistent.

**Option 3: Saga pattern (when you need coordinated rollback)**
A saga is a sequence of local transactions, each with a compensating action:

1. Order Service: Create order (status=pending)
   Compensation: Cancel order
2. Payment Service: Charge credit card
   Compensation: Refund credit card
3. Inventory Service: Reserve items
   Compensation: Release reservation
4. Order Service: Update status to confirmed

If step 3 fails, execute compensations in reverse: refund the credit card, cancel the order.

**Key insight:** There is no distributed transaction that "just works." You must design your system to handle temporary inconsistency or implement explicit compensation logic. The choice depends on how much inconsistency your business can tolerate.

- Displaying a user's order history? Eventual consistency is fine (show it 2 seconds late).
- Charging a credit card? You need a saga with compensation (no double charges).
```
**Why this works:** It starts by explaining what was lost in the move to microservices (single-transaction atomicity), then presents three solutions in order of complexity. The "keep data together" option is the most important because it prevents unnecessary complexity. The business tolerance framing at the end teaches the right way to evaluate tradeoffs.

**Pair 2 (Intermediate):**
```
Q: We are implementing the saga pattern for our order processing flow. Show me a concrete implementation with proper error handling and compensation.

A: Here is an orchestration-based saga implementation:

**Saga orchestrator:**
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable
import logging

log = logging.getLogger(__name__)

class SagaStepStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"

@dataclass
class SagaStep:
    name: str
    action: Callable
    compensation: Callable
    status: SagaStepStatus = SagaStepStatus.PENDING

class SagaOrchestrator:
    def __init__(self, saga_id: str, steps: list[SagaStep]):
        self.saga_id = saga_id
        self.steps = steps
        self.completed_steps: list[SagaStep] = []

    def execute(self, context: dict) -> dict:
        log.info(f"Starting saga {self.saga_id}")

        for step in self.steps:
            try:
                log.info(f"Executing step: {step.name}")
                result = step.action(context)
                context.update(result or {})
                step.status = SagaStepStatus.COMPLETED
                self.completed_steps.append(step)
                # Persist state for crash recovery
                self._save_state()
            except Exception as e:
                log.error(f"Step {step.name} failed: {e}")
                step.status = SagaStepStatus.FAILED
                self._compensate(context)
                raise SagaFailedError(
                    f"Saga {self.saga_id} failed at {step.name}: {e}",
                    completed_steps=[s.name for s in self.completed_steps],
                    failed_step=step.name
                )

        log.info(f"Saga {self.saga_id} completed successfully")
        return context

    def _compensate(self, context: dict):
        """Execute compensations in reverse order."""
        log.warning(f"Compensating saga {self.saga_id}")
        for step in reversed(self.completed_steps):
            try:
                log.info(f"Compensating: {step.name}")
                step.compensation(context)
                step.status = SagaStepStatus.COMPENSATED
            except Exception as e:
                # Compensation failure is critical — needs manual intervention
                log.critical(
                    f"COMPENSATION FAILED for {step.name}: {e}. "
                    f"Manual intervention required for saga {self.saga_id}")
                # Alert on-call engineer immediately
                alert_oncall(self.saga_id, step.name, str(e))

    def _save_state(self):
        """Persist saga state so it can resume after a crash."""
        db.upsert("saga_state", {
            "saga_id": self.saga_id,
            "steps": [(s.name, s.status.value) for s in self.steps]
        })

**Usage for order processing:**

def create_order_saga(order_data: dict) -> dict:
    steps = [
        SagaStep(
            name="create_order",
            action=lambda ctx: order_service.create(ctx["order_data"]),
            compensation=lambda ctx: order_service.cancel(ctx["order_id"])
        ),
        SagaStep(
            name="charge_payment",
            action=lambda ctx: payment_service.charge(
                ctx["customer_id"], ctx["total"]),
            compensation=lambda ctx: payment_service.refund(
                ctx["payment_id"])
        ),
        SagaStep(
            name="reserve_inventory",
            action=lambda ctx: inventory_service.reserve(ctx["items"]),
            compensation=lambda ctx: inventory_service.release(
                ctx["reservation_id"])
        ),
        SagaStep(
            name="confirm_order",
            action=lambda ctx: order_service.confirm(ctx["order_id"]),
            compensation=lambda ctx: order_service.revert_to_pending(
                ctx["order_id"])
        ),
    ]

    saga = SagaOrchestrator(f"order-{uuid4()}", steps)
    return saga.execute({"order_data": order_data})

**Critical design decisions:**
1. **Compensations must be idempotent** — if compensation is retried (e.g., after a crash), calling refund twice should not refund twice. Use idempotency keys.
2. **Compensation failure requires alerts** — this is the most dangerous case. A failed compensation means the system is in an inconsistent state that requires human intervention.
3. **State persistence** — the saga state is saved after each step so it can resume after a process crash. Without this, a crash mid-saga leaves the system inconsistent with no record of what happened.
4. **Timeout handling** — each step should have a timeout. A hanging API call should not block the saga indefinitely.
```
**Why this works:** It provides a complete, runnable saga implementation rather than just describing the concept. The compensation failure handling (alerting on-call) is crucial — most saga tutorials ignore what happens when compensation itself fails. The state persistence for crash recovery makes this production-grade.

**Pair 3 (Advanced):**
```
Q: We keep running into consistency issues in our distributed system despite using sagas. Events arrive out of order, services process the same event twice, and sometimes we end up with orphaned data. What is our fundamental problem, and how do we fix it?

A: These symptoms point to three missing foundational guarantees: idempotency, ordering, and exactly-once processing. Let us address each:

**Problem 1: Duplicate processing**
Every message consumer must be idempotent — processing the same message twice must produce the same result.

# WITHOUT idempotency (broken):
@event_handler("payment.completed")
def handle_payment(event):
    db.execute("UPDATE orders SET status = 'paid' WHERE id = ?", event["order_id"])
    email_service.send_receipt(event["order_id"])  # Sends duplicate receipt!

# WITH idempotency:
@event_handler("payment.completed")
def handle_payment(event):
    # Check if we already processed this specific event
    if db.exists("processed_events", event_id=event["event_id"]):
        log.info(f"Skipping duplicate event {event['event_id']}")
        return

    # Process and record in a single transaction
    with db.transaction():
        db.execute("UPDATE orders SET status = 'paid' WHERE id = ?", event["order_id"])
        db.insert("processed_events", {
            "event_id": event["event_id"],
            "processed_at": datetime.utcnow()
        })

    # Side effects (email) outside the transaction — use a separate outbox
    outbox.enqueue("send_receipt", {"order_id": event["order_id"]})

**Problem 2: Out-of-order events**
Events from the same entity may arrive out of order (order.shipped before order.confirmed):

# Use version numbers / timestamps to detect stale events
@event_handler("order.status_changed")
def handle_status(event):
    current = db.get_order(event["order_id"])
    if current["version"] >= event["version"]:
        log.info("Ignoring stale event (version %d <= %d)",
                 event["version"], current["version"])
        return
    db.update_order(event["order_id"],
                    status=event["new_status"],
                    version=event["version"])

For systems where ordering matters at the entity level, use partitioned message queues (Kafka partitioned by order_id) so all events for one order go to the same partition and are consumed in order.

**Problem 3: Orphaned data (missing related records)**
This happens when one service processes an event but another service missed it:

Solution: Transactional outbox pattern
Instead of publishing events directly, write them to an outbox table within the same database transaction:

# Service A — order creation
with db.transaction():
    order = db.insert("orders", order_data)
    db.insert("outbox", {
        "event_type": "order.created",
        "payload": json.dumps({"order_id": order["id"], "items": items}),
        "published": False
    })

# Separate process polls the outbox and publishes:
def publish_outbox_events():
    events = db.query("SELECT * FROM outbox WHERE published = FALSE ORDER BY id LIMIT 100")
    for event in events:
        message_bus.publish(event["event_type"], event["payload"])
        db.update("outbox", event["id"], published=True)

This guarantees that the event is published if and only if the database transaction committed. No orphaned data from events that were published but the transaction rolled back, and no lost events from transactions that committed but publishing failed.

**Alternative: Change Data Capture (CDC)**
Instead of an outbox table, use CDC (Debezium) to capture database changes and stream them as events. This requires no code changes but adds infrastructure complexity.

**The fundamental principle:**
Distributed consistency is not about preventing inconsistency — it is about detecting and recovering from it. Design every component to be:
1. **Idempotent** — safe to retry
2. **Order-tolerant** — handles stale/reordered events
3. **Self-healing** — reconciliation jobs that detect and fix drift

Run a reconciliation job nightly:
def reconcile_orders():
    """Find and fix inconsistencies between order and inventory services."""
    for order in db.get_confirmed_orders():
        inventory_status = inventory_service.check_reservation(order["id"])
        if inventory_status is None:
            log.error(f"Order {order['id']} has no inventory reservation — fixing")
            inventory_service.reserve(order["items"])
```
**Why this works:** It identifies the root causes (not just symptoms) of consistency issues and provides concrete solutions for each. The transactional outbox pattern solves the most common cause of orphaned data. The reconciliation job as a safety net reflects the reality that no distributed system achieves perfect consistency — you need both preventive and detective controls. The final principle ("design for recovery, not prevention") is the key mindset shift for distributed systems engineers.

**Quality assessment:**
- Concept coverage: Consistency models, saga pattern with compensation, idempotency, ordering, transactional outbox, reconciliation
- Realism: Progresses from "what replaces transactions in microservices" to "implement a saga" to "fix fundamental consistency guarantees" — the actual debugging journey in distributed systems
- Difficulty curve: Understanding the problem -> implementing a solution (saga) -> fixing the underlying guarantees that make any solution work'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
