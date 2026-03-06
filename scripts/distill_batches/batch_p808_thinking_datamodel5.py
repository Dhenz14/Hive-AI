"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 5)

JSON columns vs normalized tables and zero-downtime migration strategies
with realistic SQL scenarios and production deployment patterns.
"""

PAIRS = [
    (
        "thinking/datamodel-json-vs-normalized",
        r'''We're building a product catalog where products have variable attributes. A laptop has RAM, CPU, screen_size; a shirt has size, color, material; a book has author, ISBN, page_count. Our team is debating:

Option A: JSONB attributes column
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'
);

Option B: EAV (Entity-Attribute-Value)
CREATE TABLE product_attributes (
    product_id INTEGER REFERENCES products(id),
    attribute_name VARCHAR(100) NOT NULL,
    attribute_value TEXT NOT NULL,
    PRIMARY KEY (product_id, attribute_name)
);

Option C: Category-specific tables (like CTI)

We have 50 product categories, each with 5-15 unique attributes. New categories are added monthly. Which approach is best?''',
        r'''<think>
Let me analyze each option for this specific scenario: 50 categories, 5-15 attrs each, categories added monthly.

**Option A: JSONB column**

```sql
INSERT INTO products (name, category, price, attributes) VALUES
('MacBook Pro', 'laptop', 2499.99, '{"ram_gb": 32, "cpu": "M3 Pro", "screen_inches": 16.2}'),
('Cotton Tee', 'shirt', 29.99, '{"size": "L", "color": "navy", "material": "cotton"}');
```

Pros:
1. No schema changes when adding categories or attributes
2. Single table — simple queries for cross-category operations
3. PostgreSQL JSONB supports indexing (GIN), containment queries (@>), path queries (->)
4. Application code can validate JSON schema (JSON Schema or Pydantic)
5. One INSERT per product (no multi-table coordination)

Cons:
1. No DB-level type enforcement (ram_gb could be a string)
2. No DB-level NOT NULL on attributes (can't enforce that laptops must have ram_gb)
3. GIN indexes are slower than B-tree for range queries (price < 100 is fast, attributes->>'ram_gb' < 32 is slower)
4. JSONB storage is larger than native columns (keys stored per row)
5. Hard to do relational operations (JOIN on an attribute value)

**Option B: EAV**

```sql
INSERT INTO product_attributes VALUES
(1, 'ram_gb', '32'),
(1, 'cpu', 'M3 Pro'),
(1, 'screen_inches', '16.2');
```

Pros:
1. Fully flexible — any attribute on any product
2. Can add metadata to attributes (display_name, data_type, sort_order)
3. Can query "all products with attribute X" efficiently

Cons:
1. ALL values are TEXT — no type safety (is "32" an integer or string?)
2. Querying multiple attributes requires pivoting (multiple JOINs or crosstab)
3. "Get product with all attributes" requires aggregation (array_agg or JSON_OBJECT_AGG)
4. More rows, more index entries, more storage overhead
5. Complex queries for filtering (WHERE ram_gb > 16 AND color = 'red')
6. Historically considered an anti-pattern in SQL

**Option C: Category-specific tables (CTI)**

```sql
CREATE TABLE products (...common fields...);
CREATE TABLE laptop_attributes (product_id PK FK, ram_gb INT NOT NULL, cpu VARCHAR, ...);
CREATE TABLE shirt_attributes (product_id PK FK, size VARCHAR NOT NULL, color VARCHAR, ...);
```

Pros:
1. Full type safety, NOT NULL constraints, check constraints
2. Optimal query performance (native columns, B-tree indexes)
3. Self-documenting schema

Cons:
1. 50 categories = 50 tables (manageable but noisy)
2. New category = new table + new code (DDL change, deploy required)
3. Cross-category queries need UNION or LEFT JOIN across 50 tables
4. Adding monthly means 12 new tables/year, each needs migrations

**For this specific case (50 categories, monthly additions):**

The monthly addition of new categories rules out CTI — you don't want to write a migration, add ORM models, and deploy code just to add a new product category.

EAV is the wrong tool — it was designed for truly unlimited attributes, but the 5-15 attributes per category are structured and known. EAV's type-safety problems are severe for a product catalog (you need numeric filtering for price ranges, RAM sizes, etc.).

JSONB is the sweet spot:
- No DDL changes for new categories
- Structured enough with JSON Schema validation in the application
- PostgreSQL JSONB indexing handles the common query patterns
- Can add computed/generated columns for frequently-filtered attributes

The key is to pair JSONB with application-level schema validation (JSON Schema or Pydantic) and strategic expression indexes for hot query paths.

**Hybrid approach:**
Use JSONB for variable attributes BUT extract the most commonly filtered/sorted attributes into real columns (denormalized). This gives you the flexibility of JSONB with the query performance of native columns for hot paths.
</think>

### Recommendation: JSONB with strategic expression indexes and app-level validation

For 50+ categories with monthly additions, JSONB offers the best flexibility/performance balance.

### Schema: Hybrid approach

```sql
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    -- Variable attributes in JSONB
    attributes JSONB NOT NULL DEFAULT '{}',
    -- Frequently-filtered attributes extracted as real columns
    -- (denormalized from JSONB for query performance)
    brand VARCHAR(100) GENERATED ALWAYS AS (attributes->>'brand') STORED,
    rating DECIMAL(3,2) GENERATED ALWAYS AS ((attributes->>'rating')::decimal) STORED,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    -- Validate that required keys exist per category
    CONSTRAINT valid_laptop_attrs CHECK (
        category != 'laptop' OR (
            attributes ? 'ram_gb' AND
            attributes ? 'cpu' AND
            attributes ? 'screen_inches'
        )
    ),
    CONSTRAINT valid_shirt_attrs CHECK (
        category != 'shirt' OR (
            attributes ? 'size' AND
            attributes ? 'color' AND
            attributes ? 'material'
        )
    )
);

-- GIN index for containment queries (find products with specific attributes)
CREATE INDEX idx_products_attrs ON products USING GIN (attributes);

-- Expression indexes for common filtered attributes
CREATE INDEX idx_products_brand ON products (brand) WHERE brand IS NOT NULL;
CREATE INDEX idx_products_rating ON products (rating DESC) WHERE rating IS NOT NULL;

-- Category-specific expression indexes for hot query paths
CREATE INDEX idx_laptops_ram ON products (((attributes->>'ram_gb')::int))
    WHERE category = 'laptop';
CREATE INDEX idx_laptops_screen ON products (((attributes->>'screen_inches')::decimal))
    WHERE category = 'laptop';
```

### Application-level schema validation

```python
from pydantic import BaseModel, Field
from typing import Optional

# Define attribute schemas per category
class LaptopAttrs(BaseModel):
    ram_gb: int = Field(ge=1, le=512)
    cpu: str
    screen_inches: float = Field(ge=10, le=20)
    gpu: Optional[str] = None
    storage_gb: Optional[int] = None
    brand: Optional[str] = None
    rating: Optional[float] = Field(None, ge=0, le=5)

class ShirtAttrs(BaseModel):
    size: str = Field(pattern=r'^(XS|S|M|L|XL|XXL)$')
    color: str
    material: str
    brand: Optional[str] = None
    rating: Optional[float] = Field(None, ge=0, le=5)

CATEGORY_SCHEMAS = {
    'laptop': LaptopAttrs,
    'shirt': ShirtAttrs,
    # New categories: just add a Pydantic model — no DB migration
}

def validate_product(category: str, attributes: dict) -> dict:
    schema = CATEGORY_SCHEMAS.get(category)
    if not schema:
        return attributes  # Unknown category: accept any attributes
    return schema(**attributes).model_dump(exclude_none=True)

# Usage
attrs = validate_product('laptop', {
    'ram_gb': 32,
    'cpu': 'M3 Pro',
    'screen_inches': 16.2,
    'brand': 'Apple',
})
```

### Query patterns

```sql
-- Filter laptops by RAM (uses expression index)
SELECT id, name, price, attributes
FROM products
WHERE category = 'laptop'
  AND (attributes->>'ram_gb')::int >= 16
ORDER BY price;

-- Find all products with a specific brand (uses generated column index)
SELECT id, name, category, price
FROM products
WHERE brand = 'Apple'
ORDER BY rating DESC NULLS LAST;

-- Containment query: find products with specific attribute values
SELECT * FROM products
WHERE attributes @> '{"color": "navy", "material": "cotton"}';

-- Cross-category search with price and rating filters
SELECT id, name, category, price, rating
FROM products
WHERE price BETWEEN 50 AND 200
  AND rating >= 4.0
ORDER BY rating DESC;

-- Category facets: count products per attribute value
SELECT attributes->>'color' AS color, COUNT(*)
FROM products
WHERE category = 'shirt'
GROUP BY attributes->>'color'
ORDER BY COUNT(*) DESC;
```

### Adding a new category (no migration needed)

```python
# 1. Add the Pydantic schema (application code only)
class BookAttrs(BaseModel):
    author: str
    isbn: str = Field(pattern=r'^\d{13}$')
    page_count: int = Field(ge=1)
    publisher: Optional[str] = None

CATEGORY_SCHEMAS['book'] = BookAttrs

# 2. Optionally add a CHECK constraint (online, non-blocking in PG)
# ALTER TABLE products ADD CONSTRAINT valid_book_attrs CHECK (
#     category != 'book' OR (attributes ? 'author' AND attributes ? 'isbn')
# ) NOT VALID;
# ALTER TABLE products VALIDATE CONSTRAINT valid_book_attrs;

# 3. Optionally add expression index if books need filtered queries
# CREATE INDEX CONCURRENTLY idx_books_author
#     ON products ((attributes->>'author')) WHERE category = 'book';
```

### Comparison table

| Criteria | JSONB (recommended) | EAV | CTI (50 tables) |
|----------|-------------------|-----|-----------------|
| Add new category | No DDL | No DDL | New table + migration |
| Type safety | App-level (Pydantic) | None (all TEXT) | Full DB-level |
| Filter on attribute | Expression index | Complex JOIN | Native column index |
| Cross-category query | Single table | Pivot/aggregate | UNION x50 |
| Storage per product | ~200 bytes overhead | ~80 bytes/attr | Minimal |
| Schema discoverability | JSON Schema / docs | Query distinct names | DB catalog |'''
    ),
    (
        "thinking/datamodel-json-column-indexing",
        r'''We're using JSONB columns in PostgreSQL for our multi-tenant SaaS. Each tenant stores custom fields in a JSONB column:

CREATE TABLE tickets (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    custom_fields JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Example custom_fields:
-- Tenant A: {"priority": "high", "department": "engineering", "severity": 3}
-- Tenant B: {"region": "EMEA", "contract_id": "C-12345", "sla_hours": 24}

We have a GIN index on custom_fields. Tenant A reports that filtering by priority is slow (800ms for 100K tickets). How do we optimize JSONB queries without per-tenant schema changes?''',
        r'''<think>
Let me think about why the GIN index might not be helping and what alternatives exist.

**Why GIN might be slow for this query:**

The query is probably:
```sql
SELECT * FROM tickets
WHERE tenant_id = 5 AND custom_fields->>'priority' = 'high'
ORDER BY created_at DESC
LIMIT 50;
```

A GIN index on `custom_fields` supports containment queries (`@>`), existence (`?`), and path queries. But:

1. GIN indexes are not ordered — they can't help with ORDER BY. So PostgreSQL finds all matching rows via GIN, then sorts them.
2. With 100K tickets for tenant A, if 30% are "high" priority, that's 30K rows to sort.
3. The GIN index on the full JSONB is broad — it indexes ALL keys and values across ALL tenants.
4. GIN indexes have higher per-row overhead than B-tree.

**Better approach 1: Use containment operator with GIN**

Instead of `custom_fields->>'priority' = 'high'`, use `custom_fields @> '{"priority": "high"}'`. The containment operator is what GIN is optimized for.

But this still doesn't help with ORDER BY.

**Better approach 2: Composite B-tree expression index**

```sql
CREATE INDEX idx_tickets_tenant_priority ON tickets (
    tenant_id,
    (custom_fields->>'priority'),
    created_at DESC
);
```

This is a B-tree index on the extracted value. It supports equality + ordering. But it's specific to the 'priority' key — you'd need one per custom field.

For multi-tenant SaaS, you can't create per-tenant indexes (too many). But you CAN create indexes for the most commonly-queried custom fields.

**Better approach 3: Expression index with partial index per tenant**

```sql
CREATE INDEX idx_tickets_t5_priority ON tickets (
    (custom_fields->>'priority'),
    created_at DESC
) WHERE tenant_id = 5;
```

Small, efficient, but you need to create/manage these per tenant. Could automate this.

**Better approach 4: Generalized inverted index with path ops**

The `jsonb_path_ops` GIN operator class is more compact and faster for containment queries:

```sql
CREATE INDEX idx_tickets_custom_path ON tickets
    USING GIN (custom_fields jsonb_path_ops);
```

This is 2-3x smaller and faster than the default GIN for `@>` queries. But still doesn't help with ORDER BY.

**The real solution: Combine approaches**

1. Use `jsonb_path_ops` GIN for ad-hoc containment queries
2. Create B-tree expression indexes for the top N most-queried custom fields
3. Add a system to track which custom fields are queried frequently and auto-create indexes

**Also: consider the query pattern**

If tenants are filtering AND sorting, the ideal index is:
```sql
(tenant_id, extracted_field, created_at DESC)
```

This supports: WHERE tenant_id = X AND field = Y ORDER BY created_at DESC LIMIT 50 with a single index scan.

Let me recommend a practical approach that scales with multi-tenant SaaS.
</think>

### Root cause: GIN indexes don't support ORDER BY or range scans on extracted values

GIN is designed for containment (`@>`), not for `ORDER BY created_at DESC LIMIT 50`.

### Step 1: Fix the query syntax

```sql
-- SLOW: GIN can't optimize this (expression extraction, not containment)
SELECT * FROM tickets
WHERE tenant_id = 5 AND custom_fields->>'priority' = 'high'
ORDER BY created_at DESC LIMIT 50;

-- FASTER: Uses GIN containment operator
SELECT * FROM tickets
WHERE tenant_id = 5 AND custom_fields @> '{"priority": "high"}'
ORDER BY created_at DESC LIMIT 50;

-- But still slow for ORDER BY — GIN returns unordered results
```

### Step 2: B-tree expression indexes for hot fields

```sql
-- Composite B-tree: tenant + extracted field + sort column
-- This handles WHERE + ORDER BY in a single index scan
CREATE INDEX CONCURRENTLY idx_tickets_priority
ON tickets (tenant_id, (custom_fields->>'priority'), created_at DESC);

-- Now the original query uses the B-tree index:
EXPLAIN ANALYZE
SELECT * FROM tickets
WHERE tenant_id = 5 AND custom_fields->>'priority' = 'high'
ORDER BY created_at DESC LIMIT 50;
-- Index Scan using idx_tickets_priority (cost: 0.56..12.34)
-- Execution Time: 0.8 ms (was 800ms)
```

### Step 3: Automated index management for custom fields

```python
from collections import Counter

class CustomFieldIndexManager:
    """Track custom field usage and auto-create B-tree indexes for hot fields."""

    # Threshold: if a custom field is used in >1000 queries/day, index it
    INDEX_THRESHOLD = 1000

    async def track_query(self, tenant_id: int, field_name: str):
        """Call this whenever a custom field filter is used in a query."""
        await redis.hincrby(f"cf_query_count:{tenant_id}", field_name, 1)

    async def evaluate_indexes(self):
        """Run daily: create indexes for hot fields, drop unused ones."""
        # Get all tenants with query counts
        for tenant_key in await redis.scan_iter("cf_query_count:*"):
            tenant_id = int(tenant_key.split(":")[1])
            counts = await redis.hgetall(tenant_key)

            for field_name, count in counts.items():
                if int(count) >= self.INDEX_THRESHOLD:
                    await self.ensure_index(tenant_id, field_name)

            # Reset counters
            await redis.delete(tenant_key)

    async def ensure_index(self, tenant_id: int, field_name: str):
        """Create a partial expression index for a hot custom field."""
        index_name = f"idx_cf_{tenant_id}_{field_name}"
        exists = await db.fetch_val(
            "SELECT 1 FROM pg_indexes WHERE indexname = $1", index_name
        )
        if not exists:
            # CONCURRENTLY: non-blocking index creation
            await db.execute(f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name}
                ON tickets (
                    (custom_fields->>'{field_name}'),
                    created_at DESC
                )
                WHERE tenant_id = {tenant_id}
            """)
            # Partial index: only this tenant's rows — small and fast

    async def cleanup_unused_indexes(self):
        """Drop indexes for fields no longer queried."""
        indexes = await db.fetch_all("""
            SELECT indexname, pg_relation_size(indexname::regclass) AS size_bytes
            FROM pg_indexes
            WHERE indexname LIKE 'idx_cf_%'
        """)
        for idx in indexes:
            # Check if this field was queried recently
            parts = idx['indexname'].split('_')  # idx_cf_{tenant}_{field}
            tenant_id, field = parts[2], '_'.join(parts[3:])
            recent_count = await redis.hget(f"cf_query_count:{tenant_id}", field)
            if not recent_count or int(recent_count) < 100:
                await db.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {idx['indexname']}")
```

### Step 4: Upgrade GIN to jsonb_path_ops for ad-hoc queries

```sql
-- Default GIN: indexes keys AND values separately (larger, slower)
DROP INDEX idx_tickets_custom_fields;

-- jsonb_path_ops: 2-3x smaller, faster for @> queries
CREATE INDEX idx_tickets_custom_pathops
ON tickets USING GIN (custom_fields jsonb_path_ops);

-- Supports:
SELECT * FROM tickets
WHERE custom_fields @> '{"department": "engineering", "severity": 3}';

-- Does NOT support (use B-tree expression index instead):
-- custom_fields ? 'priority'  (key existence)
-- custom_fields->>'severity' > '2'  (range queries)
```

### Performance comparison

```
Query: WHERE tenant_id=5 AND priority='high' ORDER BY created_at DESC LIMIT 50
100K tickets for tenant 5, 30K with priority='high'

GIN only:                     ~800ms (finds 30K rows, sorts in memory)
GIN + containment (@>):       ~400ms (faster match, still sorts)
B-tree expression index:      ~0.8ms (index scan, pre-sorted)
Partial B-tree (per-tenant):  ~0.3ms (smaller index, only tenant's rows)
```

### Indexing strategy summary

| Query type | Best index | Example |
|-----------|-----------|---------|
| Exact match + sort | B-tree expression | `WHERE field = 'x' ORDER BY ts` |
| Multiple key match | GIN jsonb_path_ops | `WHERE attrs @> '{"a":1,"b":2}'` |
| Key existence | GIN default | `WHERE attrs ? 'key'` |
| Range on JSON value | B-tree expression | `WHERE (attrs->>'num')::int > 5` |
| Full-text in JSON | GIN tsvector | Custom tsvector expression |'''
    ),
    (
        "thinking/datamodel-zero-downtime-migration-add-column",
        r'''We need to add a NOT NULL column to a table with 50 million rows in PostgreSQL. Our current plan:

ALTER TABLE orders ADD COLUMN shipping_method VARCHAR(50) NOT NULL DEFAULT 'standard';

In testing, this locked the table for 45 seconds, which would cause a production outage. How do we add this column with zero downtime?''',
        r'''<think>
This is a critical production concern. Let me analyze why the lock happens and the solutions.

**Why the lock happens:**

In PostgreSQL < 11, `ADD COLUMN ... DEFAULT ...` rewrites the entire table to fill in default values. This takes an ACCESS EXCLUSIVE lock for the duration — no reads or writes.

In PostgreSQL 11+, `ADD COLUMN ... DEFAULT ...` with a non-volatile default is instant! The default is stored in the catalog, not written to every row. Rows get the default lazily when read.

BUT — there's a catch. `NOT NULL` combined with `DEFAULT` is only instant in PostgreSQL 11+ if the default is not volatile (no `NOW()`, no `random()`, etc). `'standard'` is a constant, so it should be instant.

Wait, so why is their test taking 45 seconds? Possible reasons:

1. They're on PostgreSQL < 11
2. The DEFAULT is a function call (volatile)
3. They're running additional operations (backfill, index creation) in the same transaction
4. Their test isn't representative (different PG version)

Let me provide both the modern (PG 11+) approach and the safe approach for any version.

**Safe approach for any PostgreSQL version (3-step migration):**

Step 1: Add column as NULLABLE with DEFAULT (instant, no rewrite)
```sql
ALTER TABLE orders ADD COLUMN shipping_method VARCHAR(50) DEFAULT 'standard';
```

Step 2: Backfill existing rows in batches (no lock)
```sql
UPDATE orders SET shipping_method = 'standard' WHERE shipping_method IS NULL AND id BETWEEN 1 AND 10000;
-- Repeat in batches
```

Step 3: Add NOT NULL constraint
```sql
ALTER TABLE orders ALTER COLUMN shipping_method SET NOT NULL;
```

But Step 3 requires a full table scan to verify no NULLs exist. In PG 12+, you can use NOT VALID + VALIDATE to make this faster.

Actually, in PG 12+:
```sql
ALTER TABLE orders ADD CONSTRAINT orders_shipping_not_null
    CHECK (shipping_method IS NOT NULL) NOT VALID;
-- Instant, non-blocking

ALTER TABLE orders VALIDATE CONSTRAINT orders_shipping_not_null;
-- Scans table but takes only SHARE UPDATE EXCLUSIVE lock (allows reads AND writes)
```

Then in PG 12+, once the CHECK constraint is validated, you can safely do:
```sql
ALTER TABLE orders ALTER COLUMN shipping_method SET NOT NULL;
```
And PostgreSQL will see the validated CHECK and skip the scan!

**Additional considerations:**
- Lock timeout: always set a short lock timeout so if you can't get the lock quickly, you abort rather than queue up
- Application compatibility: the app must handle both states (column exists/doesn't exist) during migration
- Foreign key considerations: if the new column references another table, that's additional locking
</think>

### Why it locks: PostgreSQL version matters

| PG Version | `ADD COLUMN ... DEFAULT ... NOT NULL` | Lock duration |
|-----------|--------------------------------------|--------------|
| < 11 | Rewrites entire table | Minutes (50M rows) |
| 11+ | Stores default in catalog (instant) | Milliseconds |
| 11+ with volatile default | Rewrites entire table | Minutes |

### If you're on PostgreSQL 11+: It should be instant

```sql
-- Check your version first
SELECT version();

-- On PG 11+, this is instant (non-volatile constant default)
ALTER TABLE orders ADD COLUMN shipping_method VARCHAR(50) NOT NULL DEFAULT 'standard';
-- Takes ~10ms regardless of table size
```

If it's still slow, check for long-running transactions that hold locks:

```sql
-- Find blocking queries
SELECT pid, age(clock_timestamp(), xact_start), query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY xact_start;
```

### Safe approach for any PostgreSQL version (zero-downtime 4-step)

```sql
-- Step 0: Set lock timeout to avoid blocking if we can't get lock quickly
SET lock_timeout = '5s';

-- Step 1: Add column as NULLABLE (instant on all PG versions)
ALTER TABLE orders ADD COLUMN shipping_method VARCHAR(50);
-- Lock: ACCESS EXCLUSIVE but instant (no rewrite, no default to fill)
```

```python
# Step 2: Backfill in small batches (no lock, production-safe)
BATCH_SIZE = 5000
SLEEP_BETWEEN = 0.1  # seconds, to avoid overwhelming the DB

async def backfill_shipping_method():
    """Backfill in batches to avoid long locks and replication lag."""
    while True:
        result = await db.execute("""
            UPDATE orders
            SET shipping_method = 'standard'
            WHERE id IN (
                SELECT id FROM orders
                WHERE shipping_method IS NULL
                ORDER BY id
                LIMIT $1
                FOR UPDATE SKIP LOCKED
            )
        """, BATCH_SIZE)

        rows_updated = result.split()[-1]  # "UPDATE 5000"
        if int(rows_updated) == 0:
            break

        # Pause to let replication catch up and avoid I/O spikes
        await asyncio.sleep(SLEEP_BETWEEN)

    print("Backfill complete")
```

```sql
-- Step 3: Add NOT NULL via CHECK constraint (non-blocking on PG 12+)

-- 3a: Add constraint NOT VALID (instant, no scan)
ALTER TABLE orders ADD CONSTRAINT orders_shipping_nn
    CHECK (shipping_method IS NOT NULL) NOT VALID;

-- 3b: Validate constraint (scans table but allows concurrent reads AND writes)
ALTER TABLE orders VALIDATE CONSTRAINT orders_shipping_nn;
-- Lock: SHARE UPDATE EXCLUSIVE (allows SELECT, INSERT, UPDATE, DELETE)

-- 3c: Convert to real NOT NULL (instant because PG sees the validated CHECK)
ALTER TABLE orders ALTER COLUMN shipping_method SET NOT NULL;

-- 3d: Drop the now-redundant CHECK constraint
ALTER TABLE orders DROP CONSTRAINT orders_shipping_nn;

-- Step 4: Set default for future rows
ALTER TABLE orders ALTER COLUMN shipping_method SET DEFAULT 'standard';
```

### Application-side safety during migration

```python
# During the migration window, handle both states:
class Order(BaseModel):
    id: int
    # shipping_method might be NULL during migration
    shipping_method: str = 'standard'

    @model_validator(mode='before')
    @classmethod
    def default_shipping(cls, values):
        if values.get('shipping_method') is None:
            values['shipping_method'] = 'standard'
        return values
```

### Common zero-downtime migration patterns

```sql
-- SAFE: Add nullable column (instant)
ALTER TABLE t ADD COLUMN c TYPE;

-- SAFE: Add column with non-volatile default (PG 11+, instant)
ALTER TABLE t ADD COLUMN c TYPE NOT NULL DEFAULT 'value';

-- SAFE: Create index concurrently (no lock)
CREATE INDEX CONCURRENTLY idx ON t (col);

-- SAFE: Add FK with NOT VALID (instant, no scan)
ALTER TABLE t ADD CONSTRAINT fk FOREIGN KEY (c) REFERENCES other(id) NOT VALID;
ALTER TABLE t VALIDATE CONSTRAINT fk;  -- scans but allows concurrent writes

-- DANGEROUS: Add NOT NULL to existing column (full scan with ACCESS EXCLUSIVE)
ALTER TABLE t ALTER COLUMN c SET NOT NULL;
-- Use the CHECK NOT VALID + VALIDATE pattern instead

-- DANGEROUS: Change column type (full rewrite)
ALTER TABLE t ALTER COLUMN c TYPE new_type;
-- Use the dual-column migration pattern instead

-- DANGEROUS: Add column with volatile default (full rewrite)
ALTER TABLE t ADD COLUMN c TIMESTAMP DEFAULT NOW();
-- Add nullable first, then backfill in batches
```

### The dual-column pattern (for type changes)

```sql
-- Changing orders.amount from INTEGER to DECIMAL:

-- 1. Add new column
ALTER TABLE orders ADD COLUMN amount_new DECIMAL(12,2);

-- 2. Backfill in batches
UPDATE orders SET amount_new = amount::decimal WHERE amount_new IS NULL AND id BETWEEN ...;

-- 3. Deploy app code that writes to BOTH columns
-- INSERT INTO orders (..., amount, amount_new) VALUES (..., $1, $1);

-- 4. Once backfill complete, switch reads to new column
-- SELECT amount_new AS amount FROM orders;

-- 5. Drop old column
ALTER TABLE orders DROP COLUMN amount;
ALTER TABLE orders RENAME COLUMN amount_new TO amount;
```

### Migration safety checklist

| Check | Why |
|-------|-----|
| `SET lock_timeout = '5s'` | Abort if lock takes too long |
| `SET statement_timeout = '30s'` | Abort if migration takes too long |
| Backfill in batches of 5K-10K | Avoid long transactions and replication lag |
| Use `NOT VALID` + `VALIDATE` | Avoid ACCESS EXCLUSIVE for constraint scans |
| Use `CONCURRENTLY` for indexes | Avoid blocking reads/writes |
| Test on production-size dataset | Dev databases hide performance issues |'''
    ),
    (
        "thinking/datamodel-migration-rename-column",
        r'''We need to rename a column in a high-traffic table:

ALTER TABLE users RENAME COLUMN email_address TO email;

This table handles 5000 queries/sec. The rename itself is fast, but our application will break because the old column name is used in hundreds of queries. We can't deploy the application code change and the migration at the exact same instant. How do we handle this safely?''',
        r'''<think>
This is the classic "schema change vs application code change" timing problem. You can't change both atomically.

**The timing gap:**
- If you rename the column FIRST: application queries fail because they reference `email_address` which no longer exists
- If you deploy app code FIRST: application queries fail because they reference `email` which doesn't exist yet

Either way, there's a window where queries fail.

**Solution: Expand-and-contract migration pattern**

Phase 1 (Expand): Add the new name alongside the old, supporting both
Phase 2 (Migrate): Update application code to use new name
Phase 3 (Contract): Remove the old name

For a column rename, this means:

1. Create a view or alias that exposes both names
2. Deploy app code using the new name
3. Drop the old name

In PostgreSQL specifically, there are a few options:

**Option A: Computed column (generated column)**

```sql
ALTER TABLE users ADD COLUMN email VARCHAR(255)
    GENERATED ALWAYS AS (email_address) STORED;
```

Wait — generated columns can't reference other columns of the same table in PostgreSQL? Actually they can, that's exactly what generated columns do. But: you can't have a generated column with the same NOT NULL / UNIQUE constraints as the original. And you can't write to a generated column.

This won't work because the app needs to INSERT into `email`.

**Option B: View-based approach**

Create a view with the new column name and point the app at the view:

```sql
CREATE VIEW users_v AS
SELECT *, email_address AS email FROM users;
```

But views complicate writes (need INSTEAD OF triggers) and changing the app to use a view is almost as much work as changing the column name.

**Option C: The expand-contract with trigger-based sync**

1. Add a new column `email`
2. Create triggers to sync `email_address` <-> `email`
3. Backfill `email` from `email_address`
4. Deploy app code using `email`
5. Verify all queries use `email`
6. Drop triggers and old column

This is the safest approach but most complex.

**Option D: The practical approach (most common)**

1. Deploy app code that handles BOTH column names (try `email`, fall back to `email_address`)
2. Run the rename
3. Deploy app code that only uses `email`

With an ORM, step 1 is: add a column alias that reads from either name.

**Actually, the simplest approach in PostgreSQL:**

Just don't rename at all. Create a view or use a database alias. Or better: the rename in PostgreSQL is instant (catalog-only change) and takes ACCESS EXCLUSIVE lock for ~1ms. The issue isn't the rename speed — it's the code deployment timing.

**The real solution: Expand-contract with both columns temporarily existing.**

Let me detail this approach.
</think>

### The problem: You can't atomically change schema AND application code

The rename is instant, but the application code deployment takes minutes. During that window, queries break.

### Solution: Expand-and-contract migration (3 phases)

### Phase 1: Expand (add new column, keep old)

```sql
-- Add new column (nullable initially)
ALTER TABLE users ADD COLUMN email VARCHAR(255);

-- Create trigger: sync writes in both directions
CREATE OR REPLACE FUNCTION sync_email_columns() RETURNS TRIGGER AS $$
BEGIN
    -- If app writes to old column, copy to new
    IF NEW.email IS NULL AND NEW.email_address IS NOT NULL THEN
        NEW.email := NEW.email_address;
    END IF;
    -- If app writes to new column, copy to old
    IF NEW.email_address IS NULL AND NEW.email IS NOT NULL THEN
        NEW.email_address := NEW.email;
    END IF;
    -- If both set, new column wins
    IF NEW.email IS NOT NULL AND NEW.email_address IS NOT NULL
       AND NEW.email != NEW.email_address THEN
        NEW.email_address := NEW.email;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_email
    BEFORE INSERT OR UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION sync_email_columns();

-- Backfill new column from old (batched)
UPDATE users SET email = email_address
WHERE email IS NULL AND id BETWEEN 1 AND 10000;
-- Repeat in batches...

-- Add matching constraints once backfill is complete
CREATE UNIQUE INDEX CONCURRENTLY idx_users_email_new ON users (email);
ALTER TABLE users ALTER COLUMN email SET NOT NULL;
```

At this point: both columns exist, both have the same data, both stay in sync.

### Phase 2: Migrate application code

```python
# OLD code:
class UserModel:
    email_address: str

# NEW code (deploy this):
class UserModel:
    email: str  # Uses the new column name

# ORM mapping (SQLAlchemy example for transitional period):
class User(Base):
    __tablename__ = 'users'
    email = Column('email', String(255))  # New column
    # email_address still exists in DB but isn't mapped
```

```
Deploy sequence:
1. Run Phase 1 migration (both columns exist, synced by trigger)
2. Deploy new application code (reads/writes "email")
3. Monitor for errors — if issues, rollback app code (old code still works with "email_address")
4. Once stable, proceed to Phase 3
```

### Phase 3: Contract (remove old column)

```sql
-- Drop the sync trigger (no longer needed)
DROP TRIGGER trg_sync_email ON users;
DROP FUNCTION sync_email_columns();

-- Drop the old column
ALTER TABLE users DROP COLUMN email_address;

-- Drop old index (if it existed)
DROP INDEX IF EXISTS idx_users_email_address;
```

### Timeline

```
Day 1: Phase 1 — Add column + trigger + backfill    (5 min migration)
Day 1: Phase 2 — Deploy application code             (rolling deploy)
Day 3: Phase 3 — Drop old column                     (after monitoring)
```

### Alternative: PostgreSQL-specific shortcut

If your downtime tolerance is ~100ms (not zero, but nearly zero):

```sql
-- Step 1: Deploy app code with column alias handling
-- Use SQLAlchemy column_property or Django's db_column to accept either name

-- Step 2: The rename is catalog-only (instant lock + release)
SET lock_timeout = '1s';
ALTER TABLE users RENAME COLUMN email_address TO email;
-- Lock duration: <10ms on PostgreSQL (no data rewrite)
-- But all in-flight queries using "email_address" will fail for ~100ms

-- Step 3: Deploy final app code (cleanup aliases)
```

This is acceptable if you have:
- Retry logic in the application
- Connection pooler (PgBouncer) that retries transparently
- Tolerance for ~100ms of errors

### Decision matrix

| Approach | Downtime | Complexity | Risk | Best for |
|----------|----------|-----------|------|----------|
| Expand-contract (3-phase) | Zero | High | Very low | Mission-critical systems |
| Rename + retry | ~100ms | Low | Low | Apps with retry logic |
| Blue-green deploy | Zero | Medium | Medium | Kubernetes/container deploys |
| Maintenance window | Minutes | Low | Low | Non-critical systems |'''
    ),
    (
        "thinking/datamodel-migration-large-backfill",
        r'''We need to backfill a computed column on a 200 million row table:

ALTER TABLE events ADD COLUMN event_date DATE;
-- Then: UPDATE events SET event_date = event_timestamp::date;

Running this as a single UPDATE would lock the table and generate massive WAL. Our replication lag is already tight. What's the safest backfill strategy?''',
        r'''<think>
A single UPDATE on 200M rows would:
1. Lock rows for the duration (blocking concurrent updates)
2. Generate ~200M dead tuples (autovacuum will struggle)
3. Write ~200M WAL records (replication lag will spike)
4. Potentially run out of disk space for WAL
5. Take hours

The solution is batched updates with throttling. Let me think about the details.

**Key considerations:**

1. **Batch size:** Too small (100) = too many transactions, overhead. Too large (1M) = long locks, WAL spikes. Sweet spot: 5K-50K rows per batch.

2. **Throttling:** Pause between batches to let replication catch up and autovacuum run. Monitor replication lag and pause if it exceeds threshold.

3. **Finding batches:** `WHERE event_date IS NULL LIMIT 5000` works but gets slower as fewer NULLs remain (index can help). Better: use ID ranges (`WHERE id BETWEEN X AND X+5000`).

4. **Dead tuples:** Each UPDATE creates a dead tuple. 200M dead tuples = massive table bloat. Autovacuum will run but may not keep up. Consider running VACUUM manually between batches.

5. **WAL volume:** Each UPDATE writes to WAL. With 200M rows at ~100 bytes per WAL record = ~20GB of WAL. This affects replication lag and disk space. Batching spreads this over time.

6. **Concurrent writes:** If the table is being written to concurrently, your backfill UPDATE might conflict. Use `FOR UPDATE SKIP LOCKED` to avoid blocking.

7. **Monitoring:** Track progress, replication lag, disk usage, autovacuum status.

8. **Alternative: Use a generated column**

In PG 12+:
```sql
ALTER TABLE events ADD COLUMN event_date DATE
    GENERATED ALWAYS AS (event_timestamp::date) STORED;
```

Wait — this rewrites the entire table (because STORED generated columns require computing and storing the value). So this has the same problem as the manual approach, but worse because it's a single DDL statement with a table lock.

Actually, for a GENERATED ALWAYS AS ... STORED column, PostgreSQL needs to compute and store the value for all existing rows. This means a full table rewrite with ACCESS EXCLUSIVE lock. So this is NOT a solution for large tables.

**Alternative: Just use a virtual/computed expression in queries**

Do you even need the column? If queries can use `event_timestamp::date` directly with an expression index:

```sql
CREATE INDEX CONCURRENTLY idx_events_date ON events ((event_timestamp::date));
```

This index creation scans the table but uses SHARE locks (allows writes). And you don't need the backfill at all.

But if the computed column is needed for other reasons (partitioning, exports, simplifying queries), then batched backfill is the way.

Let me provide the batched backfill approach with all the safety measures.
</think>

### The dangerous approach (never do this in production)

```sql
-- Single UPDATE on 200M rows: ~2 hours, massive WAL, replication lag spike
UPDATE events SET event_date = event_timestamp::date;
-- DON'T DO THIS
```

### First: Do you even need the column?

```sql
-- Alternative: Expression index eliminates the need for a stored column
CREATE INDEX CONCURRENTLY idx_events_date
    ON events ((event_timestamp::date));

-- Queries use the expression directly (index is used automatically)
SELECT * FROM events WHERE event_timestamp::date = '2026-03-05';
```

If this is sufficient, you avoid the backfill entirely. `CREATE INDEX CONCURRENTLY` takes time but doesn't block writes.

### If you need the column: Batched backfill with throttling

```python
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

class SafeBackfill:
    """Zero-downtime batched backfill with replication lag monitoring."""

    def __init__(
        self,
        batch_size: int = 10_000,
        sleep_seconds: float = 0.2,
        max_replication_lag_mb: int = 100,
        vacuum_every_n_batches: int = 50,
    ):
        self.batch_size = batch_size
        self.sleep_seconds = sleep_seconds
        self.max_replication_lag_mb = max_replication_lag_mb
        self.vacuum_every_n_batches = vacuum_every_n_batches

    async def run(self):
        """Backfill event_date in safe batches."""
        # Get the ID range
        min_id, max_id = await db.fetch_one(
            "SELECT MIN(id), MAX(id) FROM events WHERE event_date IS NULL"
        )
        if min_id is None:
            logger.info("Nothing to backfill")
            return

        total = max_id - min_id + 1
        processed = 0
        batch_num = 0
        start_time = time.time()
        current_id = min_id

        logger.info(f"Backfilling {total} rows (id {min_id} to {max_id})")

        while current_id <= max_id:
            # Check replication lag before proceeding
            await self.wait_for_replication()

            # Update one batch using ID range (predictable, index-friendly)
            result = await db.execute("""
                UPDATE events
                SET event_date = event_timestamp::date
                WHERE id >= $1 AND id < $2
                  AND event_date IS NULL
            """, current_id, current_id + self.batch_size)

            rows_affected = int(result.split()[-1])
            processed += rows_affected
            current_id += self.batch_size
            batch_num += 1

            # Progress logging
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            pct = (current_id - min_id) / total * 100
            eta = (max_id - current_id) / rate if rate > 0 else 0
            logger.info(
                f"Batch {batch_num}: {processed:,} rows ({pct:.1f}%), "
                f"{rate:.0f} rows/sec, ETA: {eta/60:.1f} min"
            )

            # Periodic VACUUM to prevent bloat
            if batch_num % self.vacuum_every_n_batches == 0:
                logger.info("Running VACUUM on events...")
                await db.execute("VACUUM events")

            # Throttle to avoid overwhelming the DB
            await asyncio.sleep(self.sleep_seconds)

        logger.info(f"Backfill complete: {processed:,} rows in {time.time()-start_time:.0f}s")

    async def wait_for_replication(self):
        """Pause if replication lag exceeds threshold."""
        while True:
            lag = await db.fetch_val("""
                SELECT COALESCE(
                    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) / 1024 / 1024,
                    0
                )
                FROM pg_stat_replication
                LIMIT 1
            """)
            if lag is None or lag < self.max_replication_lag_mb:
                return
            logger.warning(f"Replication lag: {lag:.0f}MB, pausing...")
            await asyncio.sleep(5)

# Run it
backfill = SafeBackfill(batch_size=10_000, sleep_seconds=0.2)
await backfill.run()
```

### After backfill: Add NOT NULL safely

```sql
-- Step 1: Add CHECK constraint (non-blocking validation)
ALTER TABLE events ADD CONSTRAINT events_date_nn
    CHECK (event_date IS NOT NULL) NOT VALID;

-- Step 2: Validate (allows concurrent writes)
ALTER TABLE events VALIDATE CONSTRAINT events_date_nn;

-- Step 3: Promote to real NOT NULL (instant with validated CHECK)
ALTER TABLE events ALTER COLUMN event_date SET NOT NULL;

-- Step 4: Drop redundant CHECK
ALTER TABLE events DROP CONSTRAINT events_date_nn;

-- Step 5: Create index on the new column
CREATE INDEX CONCURRENTLY idx_events_date ON events (event_date);
```

### Backfill performance tuning

| Parameter | Conservative | Moderate | Aggressive |
|-----------|-------------|----------|-----------|
| batch_size | 5,000 | 10,000 | 50,000 |
| sleep_seconds | 0.5 | 0.2 | 0.05 |
| max_replication_lag_mb | 50 | 100 | 500 |
| vacuum_every_n_batches | 20 | 50 | 100 |
| Estimated time (200M rows) | ~12 hours | ~5 hours | ~2 hours |
| WAL impact | Low | Medium | High |

### Monitoring during backfill

```sql
-- Check table bloat (dead tuples)
SELECT relname, n_live_tup, n_dead_tup,
       round(n_dead_tup::numeric / greatest(n_live_tup, 1) * 100, 1) AS dead_pct
FROM pg_stat_user_tables
WHERE relname = 'events';

-- Check replication lag
SELECT client_addr,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) / 1024 / 1024 AS lag_mb
FROM pg_stat_replication;

-- Check autovacuum progress
SELECT relname, phase, heap_blks_scanned, heap_blks_total
FROM pg_stat_progress_vacuum;

-- Check WAL generation rate
SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0') / 1024 / 1024 / 1024 AS total_wal_gb;
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
