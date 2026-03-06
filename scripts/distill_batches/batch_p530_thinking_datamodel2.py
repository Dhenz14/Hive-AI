"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 2/5)
Data integrity, transactions, caching patterns, data pipeline design."""

PAIRS = [
    (
        "thinking/datamodel-transaction-isolation",
        "Two users are buying the last item in stock simultaneously. Even with transactions, we sometimes oversell. What's wrong?\n\n```python\nwith db.transaction():\n    product = db.query('SELECT stock FROM products WHERE id = %s', product_id)\n    if product.stock > 0:\n        db.execute('UPDATE products SET stock = stock - 1 WHERE id = %s', product_id)\n        db.execute('INSERT INTO orders (product_id, user_id) VALUES (%s, %s)',\n                   (product_id, user_id))\n```",
        r"""<think>
The default transaction isolation level in most databases is READ COMMITTED. At this level:

1. Transaction A: SELECT stock → 1
2. Transaction B: SELECT stock → 1 (reads the same committed value)
3. Transaction A: UPDATE stock = 0, INSERT order → COMMIT
4. Transaction B: UPDATE stock = -1, INSERT order → COMMIT (oversold!)

The SELECT doesn't lock the row. Both transactions read stock=1 before either commits.

Fixes:
1. SELECT FOR UPDATE (row lock)
2. Atomic UPDATE with WHERE clause
3. SERIALIZABLE isolation level (PostgreSQL automatically detects conflicts)
</think>

The default `READ COMMITTED` isolation doesn't prevent this — both transactions read `stock=1` before either updates.

```
Tx A: SELECT stock → 1
Tx B: SELECT stock → 1    (same committed value)
Tx A: UPDATE stock=0 ✓ COMMIT
Tx B: UPDATE stock=-1 ✓ COMMIT  ← Oversold!
```

## Fix 1: Atomic UPDATE (Best Performance)

```python
with db.transaction():
    result = db.execute('''
        UPDATE products SET stock = stock - 1
        WHERE id = %s AND stock > 0
        RETURNING stock
    ''', (product_id,))

    if result.rowcount == 0:
        raise OutOfStockError()

    db.execute('INSERT INTO orders (product_id, user_id) VALUES (%s, %s)',
               (product_id, user_id))
```

The UPDATE's WHERE clause is atomic — the database handles concurrency.

## Fix 2: SELECT FOR UPDATE (When You Need Complex Logic)

```python
with db.transaction():
    product = db.query('''
        SELECT stock, price FROM products WHERE id = %s FOR UPDATE
    ''', (product_id,))  # Locks the row

    if product.stock <= 0:
        raise OutOfStockError()

    # Complex business logic here
    if product.price > user.balance:
        raise InsufficientFunds()

    db.execute('UPDATE products SET stock = stock - 1 WHERE id = %s', (product_id,))
    db.execute('INSERT INTO orders ...', ...)
```

## Fix 3: SERIALIZABLE Isolation

```python
with db.transaction(isolation_level='SERIALIZABLE'):
    product = db.query('SELECT stock FROM products WHERE id = %s', product_id)
    if product.stock > 0:
        db.execute('UPDATE products SET stock = stock - 1 WHERE id = %s', product_id)
        db.execute('INSERT INTO orders ...', ...)
# PostgreSQL detects the conflict and rolls back one transaction
# You must retry on serialization failure
```

## Isolation Levels Explained

| Level | Dirty Read | Non-Repeatable Read | Phantom | Use Case |
|-------|-----------|-------------------|---------|----------|
| READ UNCOMMITTED | Yes | Yes | Yes | Never use |
| READ COMMITTED | No | Yes | Yes | Default, most queries |
| REPEATABLE READ | No | No | Yes | Reports, analytics |
| SERIALIZABLE | No | No | No | Financial, inventory |

**Default choice**: Atomic UPDATE with WHERE clause. Simplest, fastest, handles 95% of concurrency cases."""
    ),
    (
        "thinking/datamodel-caching-patterns",
        "We added Redis caching but now have stale data issues. Sometimes users see outdated information. What's the right caching pattern?",
        r'''<think>
Common caching patterns:
1. Cache-Aside (Lazy Loading): App checks cache, misses go to DB, app populates cache
2. Write-Through: App writes to cache and DB simultaneously
3. Write-Behind (Write-Back): App writes to cache, cache writes to DB asynchronously
4. Read-Through: Cache itself fetches from DB on miss

The stale data problem comes from not invalidating the cache when data changes. Solutions:
1. TTL (time-based expiration)
2. Event-driven invalidation (invalidate on write)
3. Write-through (cache always has latest)

For most apps, cache-aside with event-driven invalidation is the right balance.
</think>

## Pattern 1: Cache-Aside with Invalidation (Most Common)

```python
class CachedUserService:
    def __init__(self, db, cache, ttl=300):
        self.db = db
        self.cache = cache
        self.ttl = ttl

    def get_user(self, user_id: int) -> dict:
        # 1. Check cache
        cache_key = f"user:{user_id}"
        cached = self.cache.get(cache_key)
        if cached:
            return json.loads(cached)

        # 2. Cache miss → fetch from DB
        user = self.db.query("SELECT * FROM users WHERE id = %s", user_id)
        if user:
            self.cache.setex(cache_key, self.ttl, json.dumps(user))
        return user

    def update_user(self, user_id: int, data: dict):
        # 1. Update DB (source of truth)
        self.db.execute("UPDATE users SET name = %s WHERE id = %s",
                        (data['name'], user_id))

        # 2. Invalidate cache (NOT update — avoids race conditions)
        self.cache.delete(f"user:{user_id}")

        # Next read will fetch fresh data from DB
```

## Why Invalidate, Not Update?

```python
# BAD: Race condition with cache update
def update_user(user_id, data):
    self.db.update(user_id, data)    # Thread A writes DB
    self.cache.set(key, new_data)    # Thread A updates cache

    # But Thread B also updated the DB between these two lines!
    # Cache now has Thread A's data, DB has Thread B's data → stale!

# GOOD: Just delete the cache entry
def update_user(user_id, data):
    self.db.update(user_id, data)
    self.cache.delete(key)
    # Next read fetches from DB (always fresh)
```

## Pattern 2: Write-Through (Always Fresh)

```python
class WriteThroughCache:
    def set(self, key, value):
        # Write to BOTH cache and DB atomically
        with db.transaction():
            db.execute("UPDATE ... SET data = %s WHERE key = %s", (value, key))
            self.cache.set(key, value)

    def get(self, key):
        cached = self.cache.get(key)
        if cached:
            return cached
        value = db.query("SELECT data FROM ... WHERE key = %s", key)
        self.cache.set(key, value)
        return value
```

## Cache Stampede Prevention

```python
def get_with_lock(self, key: str, compute_fn, ttl=300):
    """Prevent 100 concurrent requests from all computing the same value."""
    cached = self.cache.get(key)
    if cached:
        return json.loads(cached)

    # Acquire lock — only one request computes
    lock_key = f"lock:{key}"
    if self.cache.set(lock_key, "1", nx=True, ex=30):
        try:
            value = compute_fn()
            self.cache.setex(key, ttl, json.dumps(value))
            return value
        finally:
            self.cache.delete(lock_key)
    else:
        # Another request is computing — wait and retry
        time.sleep(0.1)
        return self.get_with_lock(key, compute_fn, ttl)
```

## Caching Decision Guide

| Data Type | Pattern | TTL | Why |
|-----------|---------|-----|-----|
| User profile | Cache-aside + invalidate | 5 min | Changes rarely, read often |
| Product catalog | Cache-aside | 1 min | Moderate change rate |
| Shopping cart | No cache | N/A | Changes every click |
| Session data | Write-through (Redis) | 30 min | Must be fresh |
| Analytics/reports | Cache-aside | 1 hour | Stale is OK |
| Search results | Cache-aside | 10 min | Expensive to compute |'''
    ),
    (
        "thinking/datamodel-json-in-rdbms",
        "Should we store flexible/dynamic data as JSONB in PostgreSQL or create proper relational tables? We have product attributes that vary by category — electronics have 'screen_size', clothing has 'fabric_type', etc.",
        r'''<think>
This is the EAV (Entity-Attribute-Value) vs JSONB vs dedicated tables debate.

Options:
1. Separate tables per category (electronics_attributes, clothing_attributes)
2. EAV table (attribute_name, attribute_value — rows)
3. JSONB column on the products table
4. Hybrid: common fields as columns, variable fields as JSONB

JSONB is usually the best for this use case because:
- PostgreSQL has excellent JSONB indexing (GIN indexes)
- No schema migration needed for new attribute types
- Can query and filter on JSONB fields efficiently
- Avoids the EAV anti-pattern's performance issues

The hybrid approach is ideal: structured columns for common/searchable fields, JSONB for the rest.
</think>

Use the **hybrid approach**: relational columns for common fields, JSONB for variable attributes.

## The Hybrid Design

```sql
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    description TEXT,
    -- Common fields everyone queries → proper columns
    brand VARCHAR(100),
    weight DECIMAL(8,2),
    -- Variable attributes → JSONB
    attributes JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- GIN index for JSONB queries
CREATE INDEX idx_products_attributes ON products USING GIN (attributes);

-- Partial index for category-specific queries
CREATE INDEX idx_electronics_screen ON products ((attributes->>'screen_size'))
    WHERE category = 'electronics';
```

## Inserting Data

```sql
-- Electronics product
INSERT INTO products (name, category, price, brand, attributes)
VALUES ('MacBook Pro', 'electronics', 2499.00, 'Apple', '{
    "screen_size": 16,
    "ram_gb": 32,
    "storage_gb": 1000,
    "processor": "M3 Pro",
    "ports": ["USB-C", "HDMI", "MagSafe"]
}');

-- Clothing product
INSERT INTO products (name, category, price, brand, attributes)
VALUES ('Classic T-Shirt', 'clothing', 29.99, 'Uniqlo', '{
    "fabric_type": "cotton",
    "sizes_available": ["S", "M", "L", "XL"],
    "colors": ["black", "white", "navy"],
    "care_instructions": "Machine wash cold"
}');
```

## Querying JSONB

```sql
-- Find electronics with screen_size > 14
SELECT name, price, attributes->>'screen_size' as screen
FROM products
WHERE category = 'electronics'
  AND (attributes->>'screen_size')::int > 14;

-- Find products with specific attribute value
SELECT name, price
FROM products
WHERE attributes @> '{"processor": "M3 Pro"}';

-- Search within JSONB arrays
SELECT name FROM products
WHERE attributes->'colors' ? 'navy';

-- Aggregate JSONB values
SELECT attributes->>'fabric_type' as fabric, COUNT(*)
FROM products
WHERE category = 'clothing'
GROUP BY fabric;
```

## When to Use Columns vs JSONB

| Use Columns | Use JSONB |
|-------------|-----------|
| Queried/filtered in most requests | Rarely queried, mostly displayed |
| Used in JOINs | Category-specific attributes |
| Needs strict type enforcement | Flexible/evolving schema |
| Needs unique constraints | Optional metadata |
| High-performance filtering | Nested/array data |

## Validation with CHECK Constraints

```sql
-- Ensure required attributes exist for electronics
ALTER TABLE products ADD CONSTRAINT electronics_attrs CHECK (
    category != 'electronics' OR (
        attributes ? 'screen_size' AND
        attributes ? 'processor'
    )
);
```

**JSONB is NOT a replacement for relational design** — it's for the genuinely variable parts. Use proper columns for anything you filter, sort, or join on frequently.'''
    ),
    (
        "thinking/datamodel-audit-trail",
        "We need a complete audit trail of all data changes for compliance (who changed what, when, and what the old value was). What's the best approach?",
        r'''<think>
Audit trail approaches:
1. Trigger-based audit table (PostgreSQL triggers capture all changes)
2. Application-level audit logging
3. Event sourcing (store events, derive current state)
4. Temporal tables (system-versioned tables in SQL:2011)
5. CDC (Change Data Capture) with Debezium

For compliance, trigger-based is the most reliable because it catches ALL changes regardless of whether they go through the application.
</think>

## PostgreSQL Trigger-Based Audit (Most Reliable)

```sql
-- Generic audit log table
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_id UUID NOT NULL,
    action VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE
    old_data JSONB,
    new_data JSONB,
    changed_fields TEXT[],
    changed_by UUID,              -- User who made the change
    changed_at TIMESTAMPTZ DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX idx_audit_table_record ON audit_log(table_name, record_id);
CREATE INDEX idx_audit_changed_at ON audit_log(changed_at);
CREATE INDEX idx_audit_changed_by ON audit_log(changed_by);

-- Generic audit trigger function
CREATE OR REPLACE FUNCTION audit_trigger() RETURNS TRIGGER AS $$
DECLARE
    old_data JSONB;
    new_data JSONB;
    changed TEXT[];
    user_id UUID;
BEGIN
    -- Get current user from session variable (set by app)
    user_id := current_setting('app.current_user_id', true)::UUID;

    IF TG_OP = 'INSERT' THEN
        new_data := to_jsonb(NEW);
        INSERT INTO audit_log (table_name, record_id, action, new_data, changed_by)
        VALUES (TG_TABLE_NAME, NEW.id, 'INSERT', new_data, user_id);
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        old_data := to_jsonb(OLD);
        new_data := to_jsonb(NEW);

        -- Find which fields actually changed
        SELECT array_agg(key) INTO changed
        FROM jsonb_each(new_data) n
        FULL OUTER JOIN jsonb_each(old_data) o USING (key)
        WHERE n.value IS DISTINCT FROM o.value;

        IF changed IS NOT NULL THEN
            INSERT INTO audit_log (table_name, record_id, action,
                                   old_data, new_data, changed_fields, changed_by)
            VALUES (TG_TABLE_NAME, NEW.id, 'UPDATE',
                    old_data, new_data, changed, user_id);
        END IF;
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        old_data := to_jsonb(OLD);
        INSERT INTO audit_log (table_name, record_id, action, old_data, changed_by)
        VALUES (TG_TABLE_NAME, OLD.id, 'DELETE', old_data, user_id);
        RETURN OLD;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables that need auditing
CREATE TRIGGER audit_users
    AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();

CREATE TRIGGER audit_orders
    AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();
```

## Setting the Current User (From Application)

```python
# In your middleware/request handler
def before_request(request):
    with db.connection() as conn:
        conn.execute(
            "SET LOCAL app.current_user_id = %s",
            (str(request.user.id),)
        )
```

## Querying the Audit Trail

```sql
-- What changed on this order?
SELECT action, changed_fields, old_data, new_data, changed_by, changed_at
FROM audit_log
WHERE table_name = 'orders' AND record_id = 'abc-123'
ORDER BY changed_at;

-- Who changed the price of this product?
SELECT changed_by, old_data->>'price' as old_price,
       new_data->>'price' as new_price, changed_at
FROM audit_log
WHERE table_name = 'products'
  AND record_id = 'prod-456'
  AND 'price' = ANY(changed_fields);

-- All changes by a specific user today
SELECT table_name, record_id, action, changed_at
FROM audit_log
WHERE changed_by = 'user-789'
  AND changed_at > CURRENT_DATE;
```

**Why triggers, not application code**: Triggers catch ALL changes — direct SQL, admin queries, migration scripts, bulk updates. Application-level audit only catches changes made through the application.'''
    ),
    (
        "thinking/datamodel-multitenancy",
        "We're building a SaaS app and need to support multiple tenants (companies). Should we use separate databases per tenant, separate schemas, or a shared table with a tenant_id column?",
        r'''<think>
Multi-tenancy approaches:
1. Shared tables with tenant_id (simplest, most common)
2. Schema per tenant (isolation without separate DBs)
3. Database per tenant (strongest isolation, most complex)

For most SaaS apps:
- <100 tenants: shared tables
- 100-1000 tenants: schema per tenant or shared tables with RLS
- Enterprise with strict data isolation needs: database per tenant

Let me compare the approaches.
</think>

## Comparison

| Approach | Isolation | Complexity | Cost | Tenants |
|----------|-----------|-----------|------|---------|
| Shared tables + tenant_id | Low | Low | Low | 1-10K+ |
| Schema per tenant | Medium | Medium | Medium | 1-1000 |
| Database per tenant | High | High | High | 1-100 |

## Option 1: Shared Tables with Row-Level Security (Best Default)

```sql
-- Every table has a tenant_id
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_projects_tenant ON projects(tenant_id);

-- Row-Level Security: automatic tenant isolation
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON projects
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- Set tenant context per request
SET LOCAL app.current_tenant_id = 'tenant-abc-123';

-- Now ALL queries are automatically filtered:
SELECT * FROM projects;
-- Actually executes: SELECT * FROM projects WHERE tenant_id = 'tenant-abc-123'
```

```python
# FastAPI middleware
@app.middleware("http")
async def set_tenant(request, call_next):
    tenant_id = get_tenant_from_request(request)
    async with db.acquire() as conn:
        await conn.execute(
            f"SET LOCAL app.current_tenant_id = '{tenant_id}'"
        )
    return await call_next(request)
```

## Option 2: Schema Per Tenant

```python
# Each tenant gets their own schema
def create_tenant(tenant_name):
    schema = f"tenant_{tenant_name}"
    db.execute(f"CREATE SCHEMA {schema}")
    db.execute(f"SET search_path TO {schema}")
    # Run migrations in the new schema
    run_migrations()

# Route queries to the right schema
@app.middleware("http")
async def set_schema(request, call_next):
    tenant = get_tenant(request)
    db.execute(f"SET search_path TO tenant_{tenant.slug}, public")
    return await call_next(request)
```

## Decision Guide

```
Choose SHARED TABLES when:
  ✓ Standard SaaS app
  ✓ Tenants don't need strict data isolation
  ✓ You want simplest operations (one migration, one backup)
  ✓ Cross-tenant analytics/reporting needed

Choose SCHEMA PER TENANT when:
  ✓ Tenants need custom schema modifications
  ✓ Moderate isolation requirements
  ✓ <1000 tenants (too many schemas = slow migrations)

Choose DATABASE PER TENANT when:
  ✓ Enterprise contracts require physical data isolation
  ✓ Tenants in different geographic regions
  ✓ Individual tenant backups/restores needed
  ✓ <100 tenants (operational overhead)
```

**Default choice**: Shared tables with PostgreSQL Row-Level Security. Simplest to operate, scales to thousands of tenants, and RLS prevents data leaks at the database level.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
