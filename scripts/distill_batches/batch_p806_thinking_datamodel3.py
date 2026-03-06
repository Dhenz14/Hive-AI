"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 3)

Schema polymorphism strategies (STI, CTI, concrete table) and soft delete vs hard delete
with realistic SQL scenarios and tradeoff analysis.
"""

PAIRS = [
    (
        "thinking/datamodel-sti-vs-cti-ecommerce",
        r'''We're building an e-commerce platform with three product types: PhysicalProduct (weight, dimensions, shipping_class), DigitalProduct (download_url, file_size, license_type), and SubscriptionProduct (billing_interval, trial_days, renewal_price). We currently use Single Table Inheritance:

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    type VARCHAR(30) NOT NULL,
    name VARCHAR(255) NOT NULL,
    base_price DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    -- Physical
    weight_kg DECIMAL(5,2),
    length_cm DECIMAL(5,1),
    width_cm DECIMAL(5,1),
    height_cm DECIMAL(5,1),
    shipping_class VARCHAR(20),
    -- Digital
    download_url TEXT,
    file_size_mb INTEGER,
    license_type VARCHAR(30),
    -- Subscription
    billing_interval VARCHAR(20),
    trial_days INTEGER,
    renewal_price DECIMAL(10,2)
);

We have 500K products (70% physical, 20% digital, 10% subscription). Queries are getting slow and the NULLable columns make validation hard. Should we switch to Class Table Inheritance or Concrete Table Inheritance?''',
        r'''<think>
Let me analyze the current situation and compare the three inheritance strategies for this specific case.

**Current state (STI):**
- 500K rows, single wide table with ~16 columns
- 70% physical = 350K rows where digital+subscription columns are NULL (5 wasted columns)
- 20% digital = 100K rows where physical+subscription columns are NULL (8 wasted columns)
- 10% subscription = 50K rows where physical+digital columns are NULL (8 wasted columns)
- Cannot enforce NOT NULL on type-specific fields at DB level
- Index bloat: every index covers all 500K rows even for type-specific queries

**Option A: Class Table Inheritance (CTI)**

Base `products` table with shared columns + one child table per type joined by FK.

Pros:
1. Proper NOT NULL constraints on type-specific fields
2. Base table is narrow (id, type, name, base_price, created_at) - fast full scans
3. Cross-type queries (search all products by name) work on base table without JOINs
4. Adding a new product type = adding a new child table, no ALTER TABLE
5. Each child table is compact and well-indexed

Cons:
1. Fetching full product details requires a JOIN (base + child)
2. INSERT requires two statements in a transaction
3. Slightly more complex application code (ORM must handle the join)

**Option B: Concrete Table Inheritance**

Three separate tables, each with ALL columns (shared + specific).

Pros:
1. No JOINs ever for single-type queries
2. Perfect per-type indexing
3. NOT NULL constraints work

Cons:
1. Cross-type queries ("search all products") require UNION ALL across 3 tables - painful with 500K rows
2. Shared columns (name, base_price) duplicated in schema - changing a shared column means ALTER TABLE x3
3. Foreign keys from order_items can't reference "a product" generically - need a polymorphic FK pattern or a product_id + product_type pair
4. Global product ID uniqueness requires coordination (sequences or UUIDs)

**Analysis for this specific case:**

The 70/20/10 split matters. Physical products dominate. With STI, every query on physical products drags along 5 unused columns per row. That's not terrible but adds up at 350K rows.

The bigger issue is validation. "Cannot enforce NOT NULL on type-specific fields" is a real data integrity risk. Imagine a PhysicalProduct with NULL weight_kg - that breaks shipping calculation.

Cross-type queries matter in e-commerce: product search, catalog browsing, admin product listing all query across types. This strongly favors CTI over Concrete Table, because CTI can search the base table without UNION ALL.

For foreign keys from order_items, CTI wins because order_items.product_id references products(id) - one FK, works for all types.

JOINs in CTI: the child table JOIN is on PRIMARY KEY = FOREIGN KEY, which is essentially free (both indexed, single row lookup). The JOIN cost is negligible for single-product fetches. For bulk queries (listing 50 products), it's one extra JOIN which is fine.

**My recommendation: Class Table Inheritance (CTI)**

It gives us:
- Clean validation (NOT NULL on type-specific fields)
- Fast cross-type queries on the narrow base table
- Simple foreign keys from other tables
- Easy extensibility (new types = new tables)
- The JOIN cost is minimal for PK-to-PK joins
</think>

### Recommendation: Switch to Class Table Inheritance (CTI)

CTI gives you the best balance of data integrity, query performance, and extensibility for this e-commerce scenario.

### Migration schema

```sql
-- Step 1: Create the new normalized tables

-- Base table: shared fields only (narrow, fast to scan)
CREATE TABLE products_new (
    id SERIAL PRIMARY KEY,
    type VARCHAR(30) NOT NULL CHECK (type IN ('physical', 'digital', 'subscription')),
    name VARCHAR(255) NOT NULL,
    base_price DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_products_type ON products_new (type);
CREATE INDEX idx_products_name ON products_new USING gin (to_tsvector('english', name));

-- Physical products: NOT NULL on weight/dimensions
CREATE TABLE physical_products (
    product_id INTEGER PRIMARY KEY REFERENCES products_new(id) ON DELETE CASCADE,
    weight_kg DECIMAL(5,2) NOT NULL,
    length_cm DECIMAL(5,1) NOT NULL,
    width_cm DECIMAL(5,1) NOT NULL,
    height_cm DECIMAL(5,1) NOT NULL,
    shipping_class VARCHAR(20) NOT NULL DEFAULT 'standard'
);

-- Digital products: NOT NULL on download_url
CREATE TABLE digital_products (
    product_id INTEGER PRIMARY KEY REFERENCES products_new(id) ON DELETE CASCADE,
    download_url TEXT NOT NULL,
    file_size_mb INTEGER NOT NULL,
    license_type VARCHAR(30) NOT NULL DEFAULT 'single-use'
);

-- Subscription products: NOT NULL on billing fields
CREATE TABLE subscription_products (
    product_id INTEGER PRIMARY KEY REFERENCES products_new(id) ON DELETE CASCADE,
    billing_interval VARCHAR(20) NOT NULL CHECK (billing_interval IN ('monthly', 'quarterly', 'yearly')),
    trial_days INTEGER NOT NULL DEFAULT 0,
    renewal_price DECIMAL(10,2) NOT NULL
);
```

### Data migration (zero-downtime safe)

```sql
-- Step 2: Migrate data in batches
BEGIN;

-- Insert base records
INSERT INTO products_new (id, type, name, base_price, created_at)
SELECT id, type, name, base_price, created_at FROM products;

-- Insert type-specific records
INSERT INTO physical_products (product_id, weight_kg, length_cm, width_cm, height_cm, shipping_class)
SELECT id, weight_kg, length_cm, width_cm, height_cm, COALESCE(shipping_class, 'standard')
FROM products WHERE type = 'physical';

INSERT INTO digital_products (product_id, download_url, file_size_mb, license_type)
SELECT id, download_url, file_size_mb, COALESCE(license_type, 'single-use')
FROM products WHERE type = 'digital';

INSERT INTO subscription_products (product_id, billing_interval, trial_days, renewal_price)
SELECT id, billing_interval, COALESCE(trial_days, 0), renewal_price
FROM products WHERE type = 'subscription';

-- Reset sequence
SELECT setval('products_new_id_seq', (SELECT MAX(id) FROM products_new));

COMMIT;
```

### Query patterns

```sql
-- Cross-type product search (no JOINs on narrow base table)
SELECT id, type, name, base_price
FROM products_new
WHERE to_tsvector('english', name) @@ plainto_tsquery('wireless headphones')
ORDER BY base_price;

-- Full physical product details (PK-to-PK JOIN is near-free)
SELECT p.*, pp.*
FROM products_new p
JOIN physical_products pp ON pp.product_id = p.id
WHERE p.id = 42;

-- Catalog page with mixed types
SELECT p.id, p.type, p.name, p.base_price,
       pp.weight_kg, pp.shipping_class,
       dp.file_size_mb,
       sp.billing_interval
FROM products_new p
LEFT JOIN physical_products pp ON pp.product_id = p.id AND p.type = 'physical'
LEFT JOIN digital_products dp ON dp.product_id = p.id AND p.type = 'digital'
LEFT JOIN subscription_products sp ON sp.product_id = p.id AND p.type = 'subscription'
WHERE p.id IN (1, 2, 3, 4, 5);
```

### Decision matrix

| Criteria | STI (current) | CTI (recommended) | Concrete Table |
|----------|--------------|-------------------|----------------|
| NOT NULL constraints | No | Yes | Yes |
| Cross-type search | Fast (1 table) | Fast (base table) | Slow (UNION x3) |
| Type-specific query | Scan all rows | JOIN on PK | Fast (1 table) |
| Foreign keys | Simple | Simple | Complex |
| Add new type | ALTER TABLE | New table | New table |
| Storage efficiency | Wasteful (NULLs) | Optimal | Duplicated cols |'''
    ),
    (
        "thinking/datamodel-soft-delete-cascading",
        r'''We have a multi-tenant SaaS with soft deletes using deleted_at timestamps. Our schema:

CREATE TABLE organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    deleted_at TIMESTAMP
);

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    deleted_at TIMESTAMP
);

CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    title VARCHAR(255) NOT NULL,
    assignee_id INTEGER REFERENCES users(id),
    deleted_at TIMESTAMP
);

Problem: When we soft-delete an organization, its projects and tasks remain "active" (deleted_at IS NULL). Users can still see tasks from deleted orgs. We manually cascade soft-deletes but keep finding edge cases. What's the right approach?''',
        r'''<think>
This is a classic soft-delete cascading problem. Let me analyze what's going wrong and what the options are.

**The core problem:**
SQL's ON DELETE CASCADE only works with hard deletes. Soft delete (UPDATE deleted_at) doesn't trigger any cascade. So you need to manually propagate the "deleted" state down the hierarchy: org -> projects -> tasks.

**Current edge cases they're likely hitting:**
1. Soft-delete org, but new projects/tasks get created for that org before the cascade runs
2. Restore an org (set deleted_at = NULL) but forget to restore projects/tasks
3. Soft-delete a project independently, then soft-delete the org, then restore the org - should the project stay deleted?
4. Queries joining tasks to projects to orgs need to check deleted_at at EVERY level
5. Unique constraints: two orgs with the same name, one deleted - broken UNIQUE(name)

**Option 1: Fix soft delete cascading with triggers**

```sql
CREATE TRIGGER cascade_org_soft_delete
AFTER UPDATE OF deleted_at ON organizations
FOR EACH ROW
WHEN (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL)
EXECUTE FUNCTION cascade_soft_delete_org();
```

This works but:
- Need triggers for every parent-child relationship
- Triggers are hard to debug and test
- Restore cascading is even harder (do you restore children that were independently deleted?)

**Option 2: Query-time filtering with effective deletion**

Instead of cascading, check parent deletion status at query time:

```sql
SELECT t.* FROM tasks t
JOIN projects p ON p.id = t.project_id AND p.deleted_at IS NULL
JOIN organizations o ON o.id = p.org_id AND o.deleted_at IS NULL
WHERE t.deleted_at IS NULL;
```

This eliminates the cascade problem but:
- Every query needs to JOIN up the entire hierarchy
- Performance degrades with deep hierarchies
- Easy to forget a JOIN

**Option 3: Materialized "effective_deleted_at" column**

Add a computed column that reflects whether the record OR any ancestor is deleted:

```sql
ALTER TABLE tasks ADD COLUMN effective_deleted_at TIMESTAMP;
```

Update this when any ancestor changes. This is essentially pre-computing the cascade.

**Option 4: Switch to hard delete + archive (my recommendation)**

Move to hard deletes with:
- Archive tables for compliance/undo
- SQL CASCADE for automatic propagation
- No more cascade bugs, no more forgotten WHERE clauses

**For multi-tenant SaaS specifically:**

Soft deleting an entire organization is a big operation. In practice, you want:
1. Deactivate the org (set status = 'deactivated', not deleted)
2. Hide all org data via a single org-level filter (not per-table soft delete)
3. After a grace period (30 days), hard-delete everything with CASCADE

This way you only need ONE filter (org.status = 'active') instead of checking deleted_at on every table.

**My recommendation:**

For the multi-tenant case, use a two-phase approach:
1. Organization-level deactivation (single column) handles the "hide everything" case
2. Individual record deletion uses hard delete + archive for within-org operations
3. SQL CASCADE handles the hierarchy automatically for hard deletes

The key insight: soft-deleting an entire org is really "deactivation," not deletion. Treat it differently.
</think>

### Root cause: Soft delete doesn't cascade, and never will

SQL CASCADE only fires on DELETE, not UPDATE. You're fighting the database instead of working with it.

### Recommended approach: Two-phase deletion model

```sql
-- Phase 1: Organization-level deactivation (not deletion)
ALTER TABLE organizations ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'deactivated', 'pending_deletion'));
ALTER TABLE organizations DROP COLUMN deleted_at;

-- Phase 2: Individual records use hard delete + CASCADE
ALTER TABLE projects DROP COLUMN deleted_at;
ALTER TABLE tasks DROP COLUMN deleted_at;

-- Re-create FKs with CASCADE
ALTER TABLE projects DROP CONSTRAINT projects_org_id_fkey;
ALTER TABLE projects ADD CONSTRAINT projects_org_id_fkey
    FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE tasks DROP CONSTRAINT tasks_project_id_fkey;
ALTER TABLE tasks ADD CONSTRAINT tasks_project_id_fkey
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
```

### Row-Level Security for org deactivation

```sql
-- PostgreSQL RLS: deactivated orgs are invisible to normal users
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

CREATE POLICY org_active_only ON organizations
    FOR ALL
    USING (status = 'active' OR current_setting('app.role') = 'admin');

-- Projects/tasks are filtered through their org relationship
CREATE POLICY project_active_org ON projects
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM organizations o
            WHERE o.id = org_id AND o.status = 'active'
        )
        OR current_setting('app.role') = 'admin'
    );
```

### Archive tables for undo capability

```sql
CREATE TABLE deleted_records (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_id INTEGER NOT NULL,
    record_data JSONB NOT NULL,
    deleted_by INTEGER REFERENCES users(id),
    deleted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL DEFAULT NOW() + INTERVAL '90 days'
);

CREATE INDEX idx_deleted_records_lookup
    ON deleted_records (table_name, record_id, deleted_at DESC);

-- Automatic cleanup
CREATE OR REPLACE FUNCTION cleanup_expired_archives() RETURNS void AS $$
BEGIN
    DELETE FROM deleted_records WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;
```

### Organization lifecycle

```python
async def deactivate_organization(org_id: int, deactivated_by: int):
    """Phase 1: Deactivate (reversible, instant)."""
    await db.execute(
        "UPDATE organizations SET status = 'deactivated' WHERE id = $1",
        org_id
    )
    # Everything becomes invisible via RLS — no cascade needed

async def reactivate_organization(org_id: int):
    """Undo deactivation — all data is still there."""
    await db.execute(
        "UPDATE organizations SET status = 'active' WHERE id = $1",
        org_id
    )

async def permanently_delete_organization(org_id: int):
    """Phase 2: After grace period, hard delete with CASCADE."""
    async with db.transaction():
        # Archive first
        org = await db.fetch_one("SELECT * FROM organizations WHERE id = $1", org_id)
        await archive_record('organizations', org_id, dict(org))

        # CASCADE handles projects -> tasks automatically
        await db.execute("DELETE FROM organizations WHERE id = $1", org_id)
```

### Why this beats soft-delete cascading

| Problem | Soft delete | Two-phase model |
|---------|------------|-----------------|
| Cascade to children | Manual triggers | SQL CASCADE (automatic) |
| Org deactivation | Update N tables | Update 1 column |
| Undo deactivation | Restore N tables | Update 1 column |
| Forgotten WHERE | Bug at every query | RLS enforces at DB level |
| Unique constraints | Broken | Work normally |
| Query performance | Check deleted_at everywhere | Clean tables, no NULLs |'''
    ),
    (
        "thinking/datamodel-concrete-table-inheritance",
        r'''We're designing an analytics pipeline that ingests events from multiple sources. Each source has completely different schemas:

- PageViewEvent: url, referrer, viewport_width, viewport_height, load_time_ms
- PurchaseEvent: order_id, items (array), total_amount, currency, payment_method
- APICallEvent: endpoint, method, status_code, latency_ms, request_size, response_size

Events are write-heavy (10K/sec), rarely updated, and queried almost exclusively by type. Cross-type queries are rare (only for "count all events in time range" dashboards). Should we use one events table with a JSONB payload column, or separate tables per event type?''',
        r'''<think>
Let me analyze this based on the specific access patterns described.

**Key constraints:**
1. Write-heavy: 10K/sec inserts
2. Rarely updated (append-only essentially)
3. Queried almost exclusively by type
4. Cross-type queries are rare
5. Each type has completely different fields (no overlap beyond timestamp/user)

**Option A: Single table with JSONB payload**

```sql
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL,
    user_id INTEGER,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
```

Pros:
- Single table for cross-type queries
- Flexible schema (add new event types without DDL)
- Simple application code

Cons:
- At 10K/sec, this table grows fast: ~864M rows/day
- JSONB indexing is slower and larger than native column indexes
- Querying JSONB fields (payload->>'status_code') is slower than native columns
- Can't use columnar compression effectively on JSONB
- Partitioning helps but partitions still contain mixed types
- Vacuuming one massive table is expensive

**Option B: Separate tables per event type (Concrete Table Inheritance)**

```sql
CREATE TABLE page_view_events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER,
    timestamp TIMESTAMPTZ NOT NULL,
    url TEXT NOT NULL,
    referrer TEXT,
    viewport_width INTEGER,
    viewport_height INTEGER,
    load_time_ms INTEGER NOT NULL
);

CREATE TABLE purchase_events (...);
CREATE TABLE api_call_events (...);
```

Pros:
- Native column types with proper constraints
- Optimal indexing per type (e.g., index on status_code for API calls)
- Better compression (columnar storage works well with uniform types)
- Independent partitioning strategies per type (page views by day, purchases by month)
- Vacuum/maintenance per table - no blocking between types
- Write throughput is distributed: 7K page views/sec to one table, 2K API calls to another, etc.

Cons:
- Cross-type queries need UNION ALL
- New event type requires new table (DDL change)
- Application code needs type-to-table routing

**For this specific case:**

The access pattern strongly favors Concrete Table Inheritance:

1. "Queried almost exclusively by type" - this means 95%+ of queries hit a single type. Separate tables are perfect.

2. "10K/sec write-heavy" - distributing writes across tables reduces contention. Single table at 10K/sec means autovacuum is constantly fighting.

3. "Completely different schemas" - there's almost no shared field overlap. JSONB wastes the opportunity for proper column types and constraints.

4. "Cross-type queries are rare" - the main advantage of a single table barely matters. A UNION ALL view handles the rare cases.

5. For time-series analytics, partitioning by time is critical. Separate tables let you partition each type independently (page views might need daily partitions, purchases monthly).

**What about the cross-type dashboard query?**

Create a materialized view or a UNION ALL view:

```sql
CREATE VIEW all_events AS
SELECT 'page_view' AS type, id, user_id, timestamp FROM page_view_events
UNION ALL
SELECT 'purchase', id, user_id, timestamp FROM purchase_events
UNION ALL
SELECT 'api_call', id, user_id, timestamp FROM api_call_events;
```

Or better: maintain a lightweight `event_counts` rollup table for dashboards.

**Recommendation: Concrete Table Inheritance with time partitioning.**
</think>

### Recommendation: Separate tables per event type (Concrete Table Inheritance)

Your access pattern (query by type, 10K/sec writes, different schemas) is the textbook case for concrete table inheritance.

### Schema with time-range partitioning

```sql
-- Page view events: partitioned by week
CREATE TABLE page_view_events (
    id BIGSERIAL,
    user_id INTEGER,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    url TEXT NOT NULL,
    referrer TEXT,
    viewport_width SMALLINT,
    viewport_height SMALLINT,
    load_time_ms INTEGER NOT NULL,
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);

-- Auto-create weekly partitions
CREATE TABLE page_view_events_2026_w10
    PARTITION OF page_view_events
    FOR VALUES FROM ('2026-03-02') TO ('2026-03-09');

-- Purchase events: partitioned by month (lower volume)
CREATE TABLE purchase_events (
    id BIGSERIAL,
    user_id INTEGER NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    order_id VARCHAR(50) NOT NULL,
    items JSONB NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    payment_method VARCHAR(30) NOT NULL,
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);

-- API call events: partitioned by day (highest volume)
CREATE TABLE api_call_events (
    id BIGSERIAL,
    user_id INTEGER,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    endpoint VARCHAR(500) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code SMALLINT NOT NULL,
    latency_ms INTEGER NOT NULL,
    request_size INTEGER,
    response_size INTEGER,
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);

-- Type-specific indexes
CREATE INDEX idx_pageview_url ON page_view_events (url, ts DESC);
CREATE INDEX idx_pageview_slow ON page_view_events (load_time_ms DESC, ts)
    WHERE load_time_ms > 3000;

CREATE INDEX idx_purchase_order ON purchase_events (order_id);
CREATE INDEX idx_purchase_amount ON purchase_events (total_amount DESC, ts);

CREATE INDEX idx_apicall_endpoint ON api_call_events (endpoint, method, ts DESC);
CREATE INDEX idx_apicall_errors ON api_call_events (ts DESC)
    WHERE status_code >= 500;
```

### Cross-type view for rare dashboard queries

```sql
-- Lightweight view for "count all events" dashboards
CREATE VIEW all_events_summary AS
SELECT 'page_view' AS event_type, id, user_id, ts FROM page_view_events
UNION ALL
SELECT 'purchase', id, user_id, ts FROM purchase_events
UNION ALL
SELECT 'api_call', id, user_id, ts FROM api_call_events;

-- Better: pre-aggregated rollup table updated by cron
CREATE TABLE event_counts_hourly (
    event_type VARCHAR(30) NOT NULL,
    hour TIMESTAMPTZ NOT NULL,
    count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (event_type, hour)
);

-- Updated every minute via pg_cron or application job
INSERT INTO event_counts_hourly (event_type, hour, count)
SELECT 'page_view', date_trunc('hour', ts), COUNT(*)
FROM page_view_events
WHERE ts >= date_trunc('hour', NOW())
GROUP BY date_trunc('hour', ts)
ON CONFLICT (event_type, hour) DO UPDATE SET count = EXCLUDED.count;
```

### Partition management automation

```python
import asyncio
from datetime import datetime, timedelta

async def create_future_partitions(weeks_ahead: int = 4):
    """Create partitions ahead of time so inserts never fail."""
    tables = {
        'page_view_events': 'week',
        'purchase_events': 'month',
        'api_call_events': 'day',
    }
    for table, interval in tables.items():
        for i in range(weeks_ahead * 7 if interval == 'day' else weeks_ahead):
            start = datetime.now().date() + timedelta(days=i)
            end = start + timedelta(days=1 if interval == 'day' else 7)
            partition_name = f"{table}_{start.strftime('%Y_%m_%d')}"
            await db.execute(f"""
                CREATE TABLE IF NOT EXISTS {partition_name}
                PARTITION OF {table}
                FOR VALUES FROM ('{start}') TO ('{end}')
            """)

async def drop_old_partitions(retention_days: int = 90):
    """Drop partitions older than retention period."""
    cutoff = (datetime.now() - timedelta(days=retention_days)).date()
    # Query pg_catalog for partition names, drop those before cutoff
    partitions = await db.fetch_all("""
        SELECT inhrelid::regclass AS partition_name
        FROM pg_inherits
        WHERE inhparent = 'page_view_events'::regclass
    """)
    for p in partitions:
        # Parse date from partition name, drop if old
        await db.execute(f"DROP TABLE IF EXISTS {p['partition_name']}")
```

### When to use JSONB payload instead

| Criteria | Separate tables | Single + JSONB |
|----------|----------------|----------------|
| Query mostly by type | Best | Wasteful |
| 50+ event types | Too many tables | Better |
| Schema changes weekly | DDL per type | No DDL needed |
| Need SQL aggregation on fields | Native columns | Slower JSONB extraction |
| Compliance/retention per type | Independent partitions | Complex |'''
    ),
    (
        "thinking/datamodel-soft-delete-unique-constraints",
        r'''We use soft deletes in our user management system. The problem is unique constraints:

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    username VARCHAR(100) NOT NULL,
    deleted_at TIMESTAMP,
    UNIQUE(email),
    UNIQUE(username)
);

Scenario: User "alice@co.com" with username "alice" is soft-deleted. A new user tries to register with the same email and username. It fails because the UNIQUE constraint sees the soft-deleted row.

We tried removing the UNIQUE constraint and checking in application code, but we got race conditions (two users registered with the same email simultaneously). What's the proper solution?''',
        r'''<think>
This is one of the most painful soft-delete problems. Let me think through all the solutions.

**The fundamental tension:**
- UNIQUE constraint prevents duplicates at the DB level (good for data integrity)
- Soft-deleted rows still occupy the uniqueness space (bad for re-registration)

**Solution 1: Partial unique index (PostgreSQL)**

PostgreSQL supports unique indexes with a WHERE clause:

```sql
CREATE UNIQUE INDEX idx_users_email_active ON users (email) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX idx_users_username_active ON users (username) WHERE deleted_at IS NULL;
```

This only enforces uniqueness among non-deleted rows. Two deleted rows can have the same email, and a new active row can reuse a deleted email.

Pros: Clean, database-enforced, no application logic needed
Cons: PostgreSQL-only. MySQL, SQL Server, Oracle don't support this directly.

**Solution 2: Coalesce trick for other databases**

MySQL/SQL Server approach: include deleted_at (or a sentinel) in the unique constraint.

```sql
-- MySQL: unique on (email, deleted_at) won't work because NULL != NULL in unique constraints
-- Actually, in MySQL, multiple NULLs ARE allowed in a unique index... so:
ALTER TABLE users ADD UNIQUE (email, deleted_at);
```

Wait, this has a problem. If deleted_at is NULL for active users, MySQL allows multiple NULL,email pairs? Actually no - MySQL treats NULL as distinct in unique indexes (unlike PostgreSQL where NULLs are distinct too). So UNIQUE(email, deleted_at) allows:
- ('alice@co.com', NULL) - active
- ('alice@co.com', '2024-01-01 00:00:00') - soft deleted

But two active users with the same email would both have (email, NULL) which would conflict. So this works for MySQL!

But it allows multiple soft-deleted records with DIFFERENT deleted_at timestamps to have the same email. That's actually fine - you might delete alice, she re-registers, then deletes again.

However, two soft-deleted records with the EXACT same deleted_at and email would conflict. That's extremely unlikely but possible in theory.

**Solution 3: Mangle the unique field on delete**

When soft-deleting, modify the unique field to include a suffix:

```sql
UPDATE users SET
    deleted_at = NOW(),
    email = email || '_deleted_' || id::text,
    username = username || '_deleted_' || id::text
WHERE id = 5;
```

Pros: Works on any database, unique constraint stays simple
Cons: Ugly, pollutes data, harder to restore (need to strip suffix), loses original value

**Solution 4: Add an "active" boolean column**

```sql
ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
CREATE UNIQUE INDEX idx_email_active ON users (email) WHERE is_active = true;
```

Same as partial index but more explicit.

**Solution 5: Hard delete + archive (best for this case)**

If soft delete is causing this much pain, move to hard delete:

```sql
DELETE FROM users WHERE id = 5;
-- Trigger archives to users_archive table
```

The archived row doesn't interfere with unique constraints.

**My recommendation for this specific case:**

For PostgreSQL: Use partial unique indexes. It's the cleanest solution and purpose-built for this.

For MySQL: Use the UNIQUE(email, deleted_at) approach with a caveat.

For any database: Consider whether soft delete is worth the complexity. If the main reason is undo/audit, archive tables are simpler.

The fact that they're already hitting race conditions when they tried application-level checking confirms that database-level constraints are essential. They need a DB-enforced solution.
</think>

### The core issue: Soft deletes break unique constraints

This is the #1 reason teams regret choosing soft deletes. Here are the solutions ranked by database.

### PostgreSQL: Partial unique index (best solution)

```sql
-- Drop the old full-table unique constraints
ALTER TABLE users DROP CONSTRAINT users_email_key;
ALTER TABLE users DROP CONSTRAINT users_username_key;

-- Create partial unique indexes: only enforce among active rows
CREATE UNIQUE INDEX idx_users_email_active
    ON users (email)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX idx_users_username_active
    ON users (username)
    WHERE deleted_at IS NULL;
```

Now:
```sql
-- Active user alice@co.com exists
INSERT INTO users (email, username) VALUES ('alice@co.com', 'alice');  -- OK

-- Soft-delete alice
UPDATE users SET deleted_at = NOW() WHERE email = 'alice@co.com';

-- New user registers with same email — works!
INSERT INTO users (email, username) VALUES ('alice@co.com', 'alice_new');  -- OK

-- Race condition: two simultaneous inserts with same email — one fails!
-- The partial unique index prevents this at the DB level. No application check needed.
```

### MySQL: Compound unique with a sentinel column

```sql
-- MySQL doesn't support partial indexes. Use a virtual column instead.
ALTER TABLE users ADD COLUMN active_email VARCHAR(255) AS (
    CASE WHEN deleted_at IS NULL THEN email ELSE NULL END
) STORED;

ALTER TABLE users ADD COLUMN active_username VARCHAR(100) AS (
    CASE WHEN deleted_at IS NULL THEN username ELSE NULL END
) STORED;

-- MySQL allows multiple NULLs in unique indexes
CREATE UNIQUE INDEX idx_users_active_email ON users (active_email);
CREATE UNIQUE INDEX idx_users_active_username ON users (active_username);
```

### SQL Server: Filtered unique index

```sql
-- SQL Server supports filtered indexes (similar to PostgreSQL partial indexes)
CREATE UNIQUE INDEX idx_users_email_active
    ON users (email)
    WHERE deleted_at IS NULL;
```

### If you need cross-database compatibility: Mangle on delete

```python
async def soft_delete_user(user_id: int):
    """Soft delete with unique field mangling for cross-DB compatibility."""
    await db.execute("""
        UPDATE users SET
            deleted_at = NOW(),
            email = CONCAT(email, '::deleted::', id),
            username = CONCAT(username, '::deleted::', id)
        WHERE id = $1 AND deleted_at IS NULL
    """, user_id)

async def restore_user(user_id: int):
    """Restore soft-deleted user, stripping the mangle suffix."""
    await db.execute("""
        UPDATE users SET
            deleted_at = NULL,
            email = SPLIT_PART(email, '::deleted::', 1),
            username = SPLIT_PART(username, '::deleted::', 1)
        WHERE id = $1 AND deleted_at IS NOT NULL
    """, user_id)
```

### The real recommendation: Hard delete + archive

```sql
-- Archive table captures deleted users with full context
CREATE TABLE users_archive (
    archive_id SERIAL PRIMARY KEY,
    original_id INTEGER NOT NULL,
    email VARCHAR(255) NOT NULL,
    username VARCHAR(100) NOT NULL,
    original_data JSONB NOT NULL,
    deleted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_by INTEGER,
    retention_until TIMESTAMP NOT NULL DEFAULT NOW() + INTERVAL '7 years'
);

-- On DELETE trigger auto-archives
CREATE OR REPLACE FUNCTION archive_user() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO users_archive (original_id, email, username, original_data)
    VALUES (OLD.id, OLD.email, OLD.username, row_to_json(OLD)::jsonb);
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_archive_user
    BEFORE DELETE ON users FOR EACH ROW
    EXECUTE FUNCTION archive_user();

-- Now the unique constraint just works:
-- DELETE FROM users WHERE id = 5;
-- INSERT INTO users (email, username) VALUES ('alice@co.com', 'alice2');  -- no conflict!
```

### Summary

| Approach | DB support | Complexity | Data integrity | Recommended? |
|----------|-----------|------------|----------------|-------------|
| Partial unique index | PostgreSQL, SQL Server | Low | Strong | Yes (PG/SS) |
| Virtual column + NULL | MySQL 5.7+ | Medium | Strong | Yes (MySQL) |
| Mangle on delete | Any | Medium | Fragile | Fallback only |
| Application-level check | Any | High | Race conditions | Never |
| Hard delete + archive | Any | Low | Perfect | Best overall |'''
    ),
    (
        "thinking/datamodel-polymorphic-fk-patterns",
        r'''We have a comments system where users can comment on different entity types: BlogPost, Video, and Product. Currently we use a polymorphic foreign key pattern:

CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    commentable_type VARCHAR(50) NOT NULL,  -- 'BlogPost', 'Video', 'Product'
    commentable_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- No actual FK constraint because commentable_id could reference any table

The problem: we have orphaned comments where the parent entity was deleted but comments remain. We can't add a real FK constraint. Our ORM (Rails/Django) handles the polymorphic association in application code but the DB has no integrity guarantee. Is there a better schema design?''',
        r'''<think>
Polymorphic foreign keys are one of the most debated patterns in database design. Let me analyze the options.

**Current problem:**
- `commentable_id` + `commentable_type` is a polymorphic FK (anti-pattern per SQL standards)
- No database-level referential integrity
- Orphaned rows when parents are deleted
- Can't use ON DELETE CASCADE

**Option 1: Exclusive belongs-to (multiple nullable FK columns)**

```sql
CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    blog_post_id INTEGER REFERENCES blog_posts(id) ON DELETE CASCADE,
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    CHECK (
        (blog_post_id IS NOT NULL)::int +
        (video_id IS NOT NULL)::int +
        (product_id IS NOT NULL)::int = 1
    )
);
```

Pros:
- Real FK constraints with ON DELETE CASCADE
- Database-enforced integrity
- CHECK constraint ensures exactly one parent

Cons:
- Adding a new commentable type requires ALTER TABLE (add column + FK + update CHECK)
- Many NULL columns if many commentable types
- Queries need COALESCE or CASE to find the parent

Works well when: few commentable types (3-5), types change rarely.

**Option 2: Intermediate join tables**

```sql
CREATE TABLE blog_post_comments (
    comment_id INTEGER PRIMARY KEY REFERENCES comments(id) ON DELETE CASCADE,
    blog_post_id INTEGER NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE
);

CREATE TABLE video_comments (
    comment_id INTEGER PRIMARY KEY REFERENCES comments(id) ON DELETE CASCADE,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE
);
```

Similar to CTI but for the relationship. Comments table has no parent reference - the join table connects them.

Pros:
- Real FK constraints on both sides
- Comments table stays clean
- Adding new types = new join table

Cons:
- Extra JOIN to find a comment's parent
- Need to ensure a comment exists in exactly one join table (no DB constraint for this across tables)

**Option 3: Shared parent table (the best pattern)**

Create a common "commentable" parent entity:

```sql
CREATE TABLE commentable_entities (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL
);

CREATE TABLE blog_posts (
    id INTEGER PRIMARY KEY REFERENCES commentable_entities(id),
    title TEXT NOT NULL,
    ...
);

CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    commentable_entity_id INTEGER NOT NULL REFERENCES commentable_entities(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    ...
);
```

This gives a real FK from comments to commentable_entities, and each entity type's PK is also a FK to commentable_entities. Deletion of any entity cascades to comments.

Pros:
- Real FK constraints everywhere
- Single JOIN to get comments for any entity
- Adding new types just requires new type table referencing commentable_entities

Cons:
- Creating an entity requires inserting into commentable_entities first (like CTI)
- Extra table and extra JOIN
- commentable_entities table grows to include all blog posts + videos + products

**For this case (3 entity types, Rails/Django ORM):**

Option 1 (exclusive belongs-to) is simplest if they have only 3 types and it's unlikely to grow much. The CHECK constraint is elegant and the NULL columns aren't bad with only 3 types.

Option 3 (shared parent) is best if they expect to add more commentable types over time. It's the most normalized and scalable.

The polymorphic FK they have now is actually fine IF they add triggers or use the ORM's callbacks properly. But since they're already having orphan issues, they need DB-level enforcement.

I'll recommend Option 1 for simplicity given only 3 types, with Option 3 as the scalable alternative.
</think>

### The problem: Polymorphic FKs have no database-level integrity

The `(commentable_type, commentable_id)` pattern is an ORM convenience that the database cannot enforce. You need a design where real FK constraints prevent orphans.

### Solution 1: Exclusive belongs-to (best for 3-5 types)

```sql
CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Exactly one of these must be set
    blog_post_id INTEGER REFERENCES blog_posts(id) ON DELETE CASCADE,
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,

    -- Enforce exactly one parent
    CONSTRAINT exactly_one_parent CHECK (
        (blog_post_id IS NOT NULL)::int +
        (video_id IS NOT NULL)::int +
        (product_id IS NOT NULL)::int = 1
    )
);

-- Indexes for each parent type
CREATE INDEX idx_comments_blog_post ON comments (blog_post_id) WHERE blog_post_id IS NOT NULL;
CREATE INDEX idx_comments_video ON comments (video_id) WHERE video_id IS NOT NULL;
CREATE INDEX idx_comments_product ON comments (product_id) WHERE product_id IS NOT NULL;
```

```python
# Query helper
def get_comments_for(entity_type: str, entity_id: int):
    column = {
        'BlogPost': 'blog_post_id',
        'Video': 'video_id',
        'Product': 'product_id',
    }[entity_type]
    return db.fetch_all(
        f"SELECT * FROM comments WHERE {column} = $1 ORDER BY created_at DESC",
        entity_id
    )
```

### Solution 2: Shared parent table (best for 5+ types or growing)

```sql
-- Abstract "commentable" entity
CREATE TABLE commentable_entities (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL
);

-- Each commentable type uses the shared ID
CREATE TABLE blog_posts (
    id INTEGER PRIMARY KEY REFERENCES commentable_entities(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    published_at TIMESTAMP
);

CREATE TABLE videos (
    id INTEGER PRIMARY KEY REFERENCES commentable_entities(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    duration_seconds INTEGER
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY REFERENCES commentable_entities(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    price DECIMAL(10,2) NOT NULL
);

-- Comments reference the shared parent — real FK, real CASCADE
CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    commentable_id INTEGER NOT NULL REFERENCES commentable_entities(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_comments_parent ON comments (commentable_id, created_at DESC);
```

```python
# Creating a blog post with the shared entity pattern
async def create_blog_post(title: str, content: str) -> int:
    async with db.transaction():
        entity_id = await db.fetch_val(
            "INSERT INTO commentable_entities (entity_type) VALUES ('BlogPost') RETURNING id"
        )
        await db.execute(
            "INSERT INTO blog_posts (id, title, content) VALUES ($1, $2, $3)",
            entity_id, title, content
        )
        return entity_id

# Getting comments works for any entity type — single query
async def get_comments(entity_id: int):
    return await db.fetch_all(
        "SELECT c.*, u.username FROM comments c "
        "JOIN users u ON u.id = c.user_id "
        "WHERE c.commentable_id = $1 ORDER BY c.created_at DESC",
        entity_id
    )
```

### Migration from polymorphic FK to exclusive belongs-to

```sql
-- Step 1: Add nullable FK columns
ALTER TABLE comments ADD COLUMN blog_post_id INTEGER REFERENCES blog_posts(id) ON DELETE CASCADE;
ALTER TABLE comments ADD COLUMN video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE;
ALTER TABLE comments ADD COLUMN product_id INTEGER REFERENCES products(id) ON DELETE CASCADE;

-- Step 2: Backfill from polymorphic columns
UPDATE comments SET blog_post_id = commentable_id WHERE commentable_type = 'BlogPost';
UPDATE comments SET video_id = commentable_id WHERE commentable_type = 'Video';
UPDATE comments SET product_id = commentable_id WHERE commentable_type = 'Product';

-- Step 3: Clean up orphans (where the parent no longer exists)
DELETE FROM comments WHERE blog_post_id IS NOT NULL
    AND blog_post_id NOT IN (SELECT id FROM blog_posts);
DELETE FROM comments WHERE video_id IS NOT NULL
    AND video_id NOT IN (SELECT id FROM videos);
DELETE FROM comments WHERE product_id IS NOT NULL
    AND product_id NOT IN (SELECT id FROM products);

-- Step 4: Add the CHECK constraint
ALTER TABLE comments ADD CONSTRAINT exactly_one_parent CHECK (
    (blog_post_id IS NOT NULL)::int +
    (video_id IS NOT NULL)::int +
    (product_id IS NOT NULL)::int = 1
);

-- Step 5: Drop old polymorphic columns
ALTER TABLE comments DROP COLUMN commentable_type;
ALTER TABLE comments DROP COLUMN commentable_id;
```

### Comparison

| Criteria | Polymorphic FK | Exclusive belongs-to | Shared parent |
|----------|---------------|---------------------|---------------|
| FK integrity | None | Full CASCADE | Full CASCADE |
| Orphan prevention | Application only | DB enforced | DB enforced |
| Add new type | No DDL | ALTER TABLE | New table only |
| Query complexity | Filter by type | COALESCE/CASE | Single JOIN |
| Best for | Rapid prototyping | 3-5 stable types | Many/growing types |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
