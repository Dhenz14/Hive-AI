"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 1/5)
Database schema design, normalization, denormalization, migration strategies."""

PAIRS = [
    (
        "thinking/datamodel-schema-design",
        "I'm designing a database for a SaaS project management tool. It needs users, organizations, projects, tasks, comments, and file attachments. What's the right schema design?",
        r'''<think>
Let me think about the relationships:
- Users belong to Organizations (many-to-many — users can be in multiple orgs)
- Projects belong to Organizations (one-to-many)
- Tasks belong to Projects (one-to-many)
- Tasks can be assigned to Users (many-to-many)
- Comments belong to Tasks (one-to-many), created by Users
- Attachments can be on Tasks or Comments (polymorphic)

Key design decisions:
1. Soft delete (is_deleted) vs hard delete — soft for audit trail
2. Timestamps on everything (created_at, updated_at)
3. UUIDs vs auto-increment — UUIDs for distributed/API-friendly
4. Polymorphic attachments — use a generic foreign key or separate tables?

I'll go with a clean design focusing on the most common queries.
</think>

## Schema Design

```sql
-- Core entities
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    plan VARCHAR(50) DEFAULT 'free',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Many-to-many: users ↔ organizations
CREATE TABLE org_members (
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'member',  -- 'owner', 'admin', 'member'
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (org_id, user_id)
);

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'active',  -- 'active', 'archived'
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_projects_org ON projects(org_id);

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'todo',  -- 'todo', 'in_progress', 'done'
    priority INTEGER DEFAULT 0,         -- 0=low, 1=medium, 2=high, 3=urgent
    due_date DATE,
    created_by UUID REFERENCES users(id),
    position INTEGER DEFAULT 0,         -- For drag-and-drop ordering
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_status ON tasks(project_id, status);
CREATE INDEX idx_tasks_due ON tasks(due_date) WHERE due_date IS NOT NULL;

-- Many-to-many: tasks ↔ users (assignees)
CREATE TABLE task_assignees (
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (task_id, user_id)
);

CREATE TABLE comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE NOT NULL,
    author_id UUID REFERENCES users(id) NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_comments_task ON comments(task_id);

-- Attachments: can belong to tasks or comments
CREATE TABLE attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    comment_id UUID REFERENCES comments(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_url VARCHAR(500) NOT NULL,
    file_size INTEGER,
    mime_type VARCHAR(100),
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT attachment_parent CHECK (
        (task_id IS NOT NULL AND comment_id IS NULL) OR
        (task_id IS NULL AND comment_id IS NOT NULL)
    )
);
```

## Design Decisions Explained

| Decision | Choice | Why |
|----------|--------|-----|
| Primary keys | UUID | API-friendly, no sequential ID guessing, safe for distributed systems |
| Timestamps | TIMESTAMPTZ | Always store with timezone — avoids UTC conversion bugs |
| Soft delete | No | Adds complexity; use separate audit log if needed |
| Attachment parent | CHECK constraint | Ensures exactly one parent (task OR comment) |
| Task ordering | `position` column | Integer for drag-and-drop reordering |
| Status fields | VARCHAR enum | Easy to add new statuses without migration |
| Indexes | On foreign keys + common queries | Task by project, task by status, comments by task |'''
    ),
    (
        "thinking/datamodel-normalization-vs-denormalization",
        "Our product page query joins 6 tables and takes 200ms. My colleague suggests denormalizing by copying category names into the products table. When is denormalization appropriate?",
        r'''<think>
Normalization vs denormalization trade-offs:
- Normalization: no redundancy, easier updates, smaller storage, but more JOINs
- Denormalization: faster reads (fewer JOINs), but redundant data, harder updates, risk of inconsistency

The key question: is the slow query the most important query? And how often does the denormalized data change?

Rules:
- Denormalize when read:write ratio is very high (100:1+)
- Denormalize when the joined data rarely changes
- Don't denormalize when data changes frequently (risk of stale data)
- Consider materialized views as a middle ground
</think>

## When to Denormalize

### Yes: High Read, Low Write, Rarely Changes

```sql
-- BEFORE: 6-table join for product page (200ms)
SELECT p.*, c.name as category_name, b.name as brand_name,
       AVG(r.rating), COUNT(r.id),
       s.quantity as stock
FROM products p
JOIN categories c ON p.category_id = c.id
JOIN brands b ON p.brand_id = b.id
LEFT JOIN reviews r ON r.product_id = p.id
LEFT JOIN stock s ON s.product_id = p.id
GROUP BY p.id, c.name, b.name, s.quantity;

-- AFTER: Denormalized product table (5ms)
-- category_name and brand_name copied into products
-- avg_rating and review_count maintained by triggers
ALTER TABLE products ADD COLUMN category_name VARCHAR(100);
ALTER TABLE products ADD COLUMN brand_name VARCHAR(100);
ALTER TABLE products ADD COLUMN avg_rating DECIMAL(3,2) DEFAULT 0;
ALTER TABLE products ADD COLUMN review_count INTEGER DEFAULT 0;

SELECT * FROM products WHERE id = $1;  -- One table, no joins
```

### No: Frequently Updated Data

```sql
-- DON'T denormalize prices into order_items if prices change hourly
-- The order_item should store the price AT TIME OF PURCHASE
-- This is actually correct normalization (snapshot), not denormalization
```

## Better Alternative: Materialized View

```sql
CREATE MATERIALIZED VIEW product_display AS
SELECT p.id, p.name, p.price, p.description,
       c.name as category_name,
       b.name as brand_name,
       COALESCE(AVG(r.rating), 0) as avg_rating,
       COUNT(r.id) as review_count,
       s.quantity as stock
FROM products p
JOIN categories c ON p.category_id = c.id
JOIN brands b ON p.brand_id = b.id
LEFT JOIN reviews r ON r.product_id = p.id
LEFT JOIN stock s ON s.product_id = p.id
GROUP BY p.id, c.name, b.name, s.quantity;

CREATE UNIQUE INDEX idx_product_display_id ON product_display(id);

-- Refresh periodically (every 5 minutes)
REFRESH MATERIALIZED VIEW CONCURRENTLY product_display;
```

## Decision Framework

| Factor | Normalize | Denormalize |
|--------|-----------|-------------|
| Read:write ratio | <10:1 | >100:1 |
| Data changes | Frequently | Rarely |
| Consistency requirement | Critical | Tolerable lag |
| Query complexity | Acceptable JOINs | 5+ table JOINs |
| Storage cost | Important | Negligible |

**Default**: Start normalized. Denormalize only specific queries that are slow AND critical AND join data that rarely changes. Use materialized views as the first option.'''
    ),
    (
        "thinking/datamodel-migration-strategies",
        "We need to rename a column from `name` to `full_name` in our users table. We have 10 million rows and can't afford downtime. How do we do this safely?",
        r"""<think>
Zero-downtime column rename is tricky because:
1. Old code references `name`, new code references `full_name`
2. Can't rename atomically while both old and new code might be running
3. 10M rows — ALTER TABLE RENAME might lock the table

The expand-contract pattern:
1. EXPAND: Add new column, backfill data, write to both
2. MIGRATE: Deploy new code that reads from new column
3. CONTRACT: Remove old column

This is safer than `ALTER TABLE RENAME COLUMN` because it allows both old and new code to run simultaneously during deployment.
</think>

Use the **expand-contract pattern** for zero-downtime migrations:

## Phase 1: Expand (Add New Column)

```sql
-- Migration 1: Add the new column (instant, no lock on Postgres 11+)
ALTER TABLE users ADD COLUMN full_name VARCHAR(255);

-- Backfill existing data (do in batches to avoid long locks)
UPDATE users SET full_name = name WHERE id BETWEEN 1 AND 100000;
UPDATE users SET full_name = name WHERE id BETWEEN 100001 AND 200000;
-- ... or use a script:
```

```python
# Batch backfill script
BATCH_SIZE = 10_000

while True:
    updated = db.execute('''
        UPDATE users SET full_name = name
        WHERE full_name IS NULL
        LIMIT %s
    ''', BATCH_SIZE)
    if updated.rowcount == 0:
        break
    time.sleep(0.1)  # Don't overwhelm the DB
```

## Phase 2: Dual Write (Both Columns Kept in Sync)

```python
# Deploy code that writes to BOTH columns
class User(Model):
    def save(self):
        self.full_name = self.full_name or self.name  # Sync
        self.name = self.full_name  # Keep old column updated
        super().save()
```

```sql
-- Add trigger to keep columns in sync during transition
CREATE OR REPLACE FUNCTION sync_user_name() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.full_name IS NULL THEN
        NEW.full_name := NEW.name;
    END IF;
    IF NEW.name != NEW.full_name THEN
        NEW.name := NEW.full_name;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sync_name BEFORE INSERT OR UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION sync_user_name();
```

## Phase 3: Migrate Reads (Switch to New Column)

```python
# Deploy code that reads from full_name
class User(Model):
    @property
    def display_name(self):
        return self.full_name  # Read from new column
```

## Phase 4: Contract (Remove Old Column)

```sql
-- After ALL servers are running new code:
-- 1. Remove trigger
DROP TRIGGER sync_name ON users;

-- 2. Remove old column
ALTER TABLE users DROP COLUMN name;
```

## Timeline

```
Week 1: Add full_name column + backfill (Phase 1)
Week 2: Deploy dual-write code (Phase 2)
Week 3: Deploy read-from-new code (Phase 3)
Week 4: Drop old column (Phase 4)
```

Each phase is independently deployable and rollback-safe. At no point does old code or new code break."""
    ),
    (
        "thinking/datamodel-polymorphic-associations",
        "We have comments that can belong to tasks, projects, or documents. How should I model this? I've seen three approaches and don't know which is best.\n\nOption A: Three nullable foreign keys\nOption B: A 'commentable_type' + 'commentable_id' pattern\nOption C: Separate tables (task_comments, project_comments, document_comments)",
        r'''<think>
Three approaches to polymorphic associations:

Option A (Nullable FKs): Simple, enforced by DB, but wastes space and gets ugly with many types
Option B (STI/generic FK): Flexible, used by Rails/Django, but NO database-level FK enforcement
Option C (Separate tables): Strongest integrity, but duplicated schema

For most cases:
- If ≤3 types: Option A is simplest
- If many types and you need flexibility: Option B with application-level integrity
- If data integrity is critical: Option C

Let me also consider a 4th option: shared parent table with FK.
</think>

## Comparison

### Option A: Nullable Foreign Keys (Best for ≤3 Types)

```sql
CREATE TABLE comments (
    id UUID PRIMARY KEY,
    body TEXT NOT NULL,
    author_id UUID REFERENCES users(id),
    task_id UUID REFERENCES tasks(id),
    project_id UUID REFERENCES projects(id),
    document_id UUID REFERENCES documents(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT exactly_one_parent CHECK (
        (task_id IS NOT NULL)::int +
        (project_id IS NOT NULL)::int +
        (document_id IS NOT NULL)::int = 1
    )
);
CREATE INDEX idx_comments_task ON comments(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX idx_comments_project ON comments(project_id) WHERE project_id IS NOT NULL;
CREATE INDEX idx_comments_document ON comments(document_id) WHERE document_id IS NOT NULL;
```

**Pros**: Real foreign keys, database enforces integrity, simple queries
**Cons**: New commentable type = schema migration, sparse columns

### Option B: Generic Foreign Key (Most Flexible)

```sql
CREATE TABLE comments (
    id UUID PRIMARY KEY,
    body TEXT NOT NULL,
    author_id UUID REFERENCES users(id),
    commentable_type VARCHAR(50) NOT NULL,  -- 'task', 'project', 'document'
    commentable_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_comments_parent ON comments(commentable_type, commentable_id);
```

**Pros**: No schema change for new types, clean table
**Cons**: No FK enforcement — the `commentable_id` might reference a non-existent row. Must enforce in application code.

### Option C: Separate Tables (Strongest Integrity)

```sql
CREATE TABLE task_comments (
    id UUID PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE NOT NULL,
    body TEXT NOT NULL,
    author_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE project_comments (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
    body TEXT NOT NULL,
    author_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Pros**: Full FK integrity, targeted indexes, clear schema
**Cons**: Duplicated schema, harder to query "all comments by user"

### Option D: Shared Parent Table (Best of Both Worlds)

```sql
CREATE TABLE commentable (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

-- Each entity gets a commentable_id
ALTER TABLE tasks ADD COLUMN commentable_id UUID REFERENCES commentable(id);
ALTER TABLE projects ADD COLUMN commentable_id UUID REFERENCES commentable(id);
ALTER TABLE documents ADD COLUMN commentable_id UUID REFERENCES commentable(id);

CREATE TABLE comments (
    id UUID PRIMARY KEY,
    commentable_id UUID REFERENCES commentable(id) ON DELETE CASCADE NOT NULL,
    body TEXT NOT NULL,
    author_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Pros**: Real FK enforcement, no nullable columns, extensible
**Cons**: Extra indirection table, slightly more complex queries

## My Recommendation

| Types Count | Best Option | Why |
|-------------|-------------|-----|
| 2-3 types | A (Nullable FKs) | Simple, enforced, efficient |
| 4+ types | D (Shared parent) | Extensible with real FKs |
| Rapid prototyping | B (Generic FK) | Fastest to add new types |
| Financial/regulated | C (Separate tables) | Maximum integrity |'''
    ),
    (
        "thinking/datamodel-indexing-strategy",
        "Our queries are slow but we're afraid of adding too many indexes. How do I decide which indexes to create?",
        r'''<think>
Index strategy:
1. Every foreign key gets an index (for JOINs and CASCADE deletes)
2. Every WHERE clause in common queries gets considered
3. Cover multi-column queries with composite indexes
4. Partial indexes for filtered queries
5. Don't index columns that are rarely queried
6. Don't index low-cardinality columns (boolean, status with 3 values) alone

Use EXPLAIN ANALYZE to find which queries need indexes.
</think>

## The Indexing Decision Framework

### Always Index

```sql
-- 1. Primary keys (automatic)
-- 2. Foreign keys (NOT automatic in PostgreSQL!)
CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_comments_task_id ON comments(task_id);

-- 3. Unique constraints (automatic)
-- 4. Columns in WHERE clauses of frequent queries
```

### Find Slow Queries First

```sql
-- Enable slow query logging
ALTER SYSTEM SET log_min_duration_statement = 100;  -- Log queries >100ms

-- Or check pg_stat_statements for most time-consuming queries
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

### Use EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT * FROM orders
WHERE user_id = 123 AND status = 'pending'
ORDER BY created_at DESC
LIMIT 20;

-- Look for:
-- "Seq Scan" → needs an index
-- "Index Scan" → already indexed
-- "Sort" with high cost → needs index on ORDER BY column
```

### Composite Indexes (Column Order Matters)

```sql
-- Query: WHERE user_id = ? AND status = ? ORDER BY created_at DESC
-- Index covers all three: filter + sort
CREATE INDEX idx_orders_user_status_date
    ON orders(user_id, status, created_at DESC);

-- This ONE index covers:
-- WHERE user_id = 123                          ✓ (leftmost prefix)
-- WHERE user_id = 123 AND status = 'pending'   ✓ (two-column prefix)
-- WHERE user_id = 123 ORDER BY created_at DESC ✓ (skip scan)
-- WHERE status = 'pending'                     ✗ (can't use, wrong prefix)
```

### Partial Indexes (Index Only What You Query)

```sql
-- Only 5% of orders are 'pending', but you query them constantly
CREATE INDEX idx_orders_pending
    ON orders(user_id, created_at)
    WHERE status = 'pending';
-- Much smaller index, faster lookups for the common query

-- Only active users need login index
CREATE INDEX idx_users_email_active
    ON users(email)
    WHERE is_active = true;
```

### What NOT to Index

```sql
-- DON'T: Low-cardinality columns alone
CREATE INDEX idx_orders_status ON orders(status);
-- Only 3-5 distinct values → not selective, rarely useful alone

-- DON'T: Columns only used in rarely-run reports
-- The occasional 500ms report query doesn't justify the write overhead

-- DON'T: Small tables (<1000 rows)
-- Seq scan is faster than index lookup for small tables
```

### Index Overhead

```
Each index:
  + Faster SELECT/WHERE queries
  - Slower INSERT (must update index)
  - Slower UPDATE on indexed columns
  - Uses disk space
  - Uses memory (cached index pages)

Rule of thumb: 3-5 indexes per table is normal
              10+ indexes → review if all are needed
```'''
    ),
    (
        "thinking/datamodel-time-series-design",
        "We're building an IoT platform that ingests sensor readings — temperature, humidity, pressure — from 10,000 devices every 10 seconds. That's 86 million rows per day. How should we design the database?",
        r'''<think>
86M rows/day is a time-series problem. Regular PostgreSQL tables would struggle with this volume. Options:

1. TimescaleDB (PostgreSQL extension for time-series)
2. InfluxDB (purpose-built time-series DB)
3. QuestDB (fast time-series DB)
4. Partitioned PostgreSQL tables

TimescaleDB is the best choice if they want to stay in PostgreSQL ecosystem — it auto-partitions by time (hypertables) and compresses old data.

Key design decisions:
- Partition by time (daily/weekly)
- Compress old data
- Retention policies (delete old data automatically)
- Downsampling (aggregate old data to hourly/daily)
</think>

## TimescaleDB Design (PostgreSQL Extension)

```sql
-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Wide table design (recommended for IoT)
CREATE TABLE sensor_readings (
    time        TIMESTAMPTZ NOT NULL,
    device_id   INTEGER NOT NULL,
    temperature DOUBLE PRECISION,
    humidity    DOUBLE PRECISION,
    pressure    DOUBLE PRECISION,
    battery     DOUBLE PRECISION
);

-- Convert to hypertable (auto-partitions by time)
SELECT create_hypertable('sensor_readings', 'time',
    chunk_time_interval => INTERVAL '1 day'
);

-- Indexes for common queries
CREATE INDEX idx_readings_device_time
    ON sensor_readings(device_id, time DESC);
```

## Ingestion (Batch Insert for Performance)

```python
# Batch insert — 10x faster than individual INSERTs
async def ingest_readings(readings: list[dict]):
    async with db.acquire() as conn:
        await conn.copy_records_to_table(
            'sensor_readings',
            records=[
                (r['time'], r['device_id'], r['temperature'],
                 r['humidity'], r['pressure'], r['battery'])
                for r in readings
            ],
        )
```

## Common Queries

```sql
-- Latest reading per device
SELECT DISTINCT ON (device_id)
    device_id, time, temperature, humidity
FROM sensor_readings
WHERE time > NOW() - INTERVAL '1 hour'
ORDER BY device_id, time DESC;

-- Hourly averages for a device
SELECT time_bucket('1 hour', time) AS hour,
       AVG(temperature) as avg_temp,
       MIN(temperature) as min_temp,
       MAX(temperature) as max_temp
FROM sensor_readings
WHERE device_id = 42
  AND time > NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour;
```

## Continuous Aggregates (Pre-Computed Rollups)

```sql
-- Auto-maintained hourly summary (materialized view on steroids)
CREATE MATERIALIZED VIEW hourly_readings
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', time) AS hour,
       device_id,
       AVG(temperature) as avg_temp,
       AVG(humidity) as avg_humidity,
       AVG(pressure) as avg_pressure,
       COUNT(*) as reading_count
FROM sensor_readings
GROUP BY hour, device_id;

-- Refresh policy
SELECT add_continuous_aggregate_policy('hourly_readings',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);
```

## Compression & Retention

```sql
-- Compress data older than 7 days (10x storage reduction)
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('sensor_readings', INTERVAL '7 days');

-- Delete data older than 90 days
SELECT add_retention_policy('sensor_readings', INTERVAL '90 days');
```

## Storage Estimates

```
Raw: 86M rows/day × 48 bytes/row = ~4 GB/day
Compressed: ~400 MB/day (10x compression)
90-day retention: ~36 GB total
With hourly aggregates: queries on old data hit small summary table
```'''
    ),
    (
        "thinking/datamodel-soft-delete-patterns",
        "We need to keep deleted records for compliance but also want `SELECT * FROM users` to only return active users. What are the options for soft delete?",
        r'''<think>
Soft delete approaches:
1. Boolean flag: `is_deleted`
2. Timestamp: `deleted_at`
3. Status enum: `status = 'deleted'`
4. Separate archive table
5. History/audit table

Each has trade-offs. The main problems with soft delete:
- Every query needs `WHERE NOT deleted`
- Foreign key constraints get complicated
- Unique constraints need special handling
- Data grows forever

Let me cover the practical approaches.
</think>

## Option 1: `deleted_at` Timestamp (Most Common)

```sql
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMPTZ;

-- Create a view for "active" users (most queries use this)
CREATE VIEW active_users AS
SELECT * FROM users WHERE deleted_at IS NULL;

-- Partial unique index — email unique only among non-deleted
CREATE UNIQUE INDEX idx_users_email_active
    ON users(email)
    WHERE deleted_at IS NULL;
-- Allows: same email to be "deleted" and then re-registered

-- Soft delete
UPDATE users SET deleted_at = NOW() WHERE id = $1;

-- Hard delete (for GDPR "right to erasure")
DELETE FROM users WHERE id = $1;
```

## Option 2: Row-Level Security (PostgreSQL)

```sql
-- Force all queries to filter deleted records automatically
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY active_users_only ON users
    FOR SELECT
    USING (deleted_at IS NULL);

-- Admin role can see deleted records
CREATE POLICY admin_see_all ON users
    FOR SELECT
    TO admin_role
    USING (true);

-- Now SELECT * FROM users automatically excludes deleted rows
-- No need to remember WHERE deleted_at IS NULL everywhere
```

## Option 3: Archive Table (Best for Compliance)

```sql
-- Move deleted records to a separate table
CREATE TABLE users_archive (LIKE users INCLUDING ALL);
ALTER TABLE users_archive ADD COLUMN archived_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE users_archive ADD COLUMN archived_by UUID;

-- Delete function moves to archive first
CREATE OR REPLACE FUNCTION soft_delete_user(user_id UUID, deleted_by UUID)
RETURNS VOID AS $$
BEGIN
    INSERT INTO users_archive
    SELECT *, NOW(), deleted_by
    FROM users WHERE id = user_id;

    DELETE FROM users WHERE id = user_id;
END;
$$ LANGUAGE plpgsql;
```

**Pros**: `users` table stays clean, no filter needed, FK constraints work normally
**Cons**: Joins across active + archived data are harder

## Comparison

| Approach | Query Simplicity | FK Safety | Storage | Best For |
|----------|-----------------|-----------|---------|----------|
| `deleted_at` column | Need filter everywhere | Complex | Grows | Simple apps |
| Row-Level Security | Transparent | Complex | Grows | PostgreSQL apps |
| Archive table | Clean queries | Clean | Separated | Compliance-heavy |

## Handling Cascades

```sql
-- Problem: User is soft-deleted but their tasks still reference them
-- Option 1: Cascade soft delete (complex)
-- Option 2: Keep FK valid (deleted user still exists in table)
-- Option 3: SET NULL on soft delete

-- Best practice: keep the reference, add display logic
-- "Task assigned to [Deleted User]" is better than broken references
```

**My recommendation**: Archive table for compliance-heavy apps. `deleted_at` + Row-Level Security for everything else. Always add a view or RLS policy so developers don't accidentally query deleted records.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
