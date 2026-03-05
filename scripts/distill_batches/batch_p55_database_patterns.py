"""Database patterns — migrations, time-series, full-text search, and replication."""

PAIRS = [
    (
        "database/migration-patterns",
        "Show database migration patterns: expand-contract, zero-downtime, backfill strategies, and rollback safety.",
        '''Database migration patterns for zero downtime:

```python
# --- Expand-Contract pattern for schema changes ---
# Never make breaking changes in one step. Always:
# 1. Expand: add new column/table (backward compatible)
# 2. Migrate: backfill data to new structure
# 3. Contract: remove old column/table after all code uses new structure


# Migration 1: EXPAND — add new column (nullable)
"""
ALTER TABLE users ADD COLUMN display_name VARCHAR(100);
-- Old code still works: reads/writes `name` column
-- New code can start writing to `display_name`
"""


# Migration 2: BACKFILL — copy data in batches
"""
-- Don't UPDATE all rows at once (locks table)
-- Instead, batch update:
"""

async def backfill_display_name(pool, batch_size: int = 1000):
    """Backfill in batches to avoid long locks."""
    while True:
        async with pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE users
                SET display_name = name
                WHERE display_name IS NULL
                AND id IN (
                    SELECT id FROM users
                    WHERE display_name IS NULL
                    LIMIT $1
                )
            """, batch_size)

            if result == "UPDATE 0":
                break

            # Small delay between batches to reduce load
            await asyncio.sleep(0.1)


# Migration 3: CONTRACT — make NOT NULL, drop old column
"""
-- After all code uses display_name:
ALTER TABLE users ALTER COLUMN display_name SET NOT NULL;
ALTER TABLE users ALTER COLUMN display_name SET DEFAULT '';

-- Later migration (after deploy confirms no issues):
ALTER TABLE users DROP COLUMN name;
"""


# --- Adding an index without locking ---
"""
-- BAD: locks table for writes during index creation
CREATE INDEX idx_users_email ON users (email);

-- GOOD: concurrent index creation (PostgreSQL)
CREATE INDEX CONCURRENTLY idx_users_email ON users (email);
-- Slower but doesn't lock the table
"""


# --- Renaming a column safely ---
# Step 1: Add new column
# Step 2: Write to both columns in application code
# Step 3: Backfill old -> new
# Step 4: Switch reads to new column
# Step 5: Stop writing to old column
# Step 6: Drop old column


# --- Alembic migration with safety checks ---

from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add column (nullable first)
    op.add_column('orders', sa.Column('total_cents', sa.BigInteger(), nullable=True))

    # Create index concurrently
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "idx_orders_total_cents ON orders (total_cents)"
    )

    # Set default for new rows
    op.alter_column('orders', 'total_cents',
                     server_default=sa.text('0'))

def downgrade():
    op.drop_index('idx_orders_total_cents', table_name='orders')
    op.drop_column('orders', 'total_cents')


# --- Safe migration checklist ---
# 1. No ALTER TABLE that locks reads (use CONCURRENTLY for indexes)
# 2. New columns must be nullable or have defaults
# 3. Never rename/drop columns in same deploy as code change
# 4. Backfill in batches, not one giant UPDATE
# 5. Always have a tested downgrade path
# 6. Monitor after each migration step before proceeding
```

Migration safety rules:
1. **Expand-contract** — add first, migrate, then remove (3 separate deploys)
2. **CREATE INDEX CONCURRENTLY** — no table locks during index creation
3. **Batch backfills** — small batches with delays to avoid overwhelming DB
4. **Nullable first** — new columns must be nullable until backfill completes
5. **Always have downgrade** — every migration must be reversible'''
    ),
    (
        "database/postgresql-advanced",
        "Show advanced PostgreSQL patterns: CTEs, window functions, JSONB, partitioning, and advisory locks.",
        '''Advanced PostgreSQL patterns:

```sql
-- --- CTEs (Common Table Expressions) ---

-- Recursive CTE: org chart traversal
WITH RECURSIVE org_tree AS (
    -- Base case: top-level managers
    SELECT id, name, manager_id, 0 AS depth, ARRAY[name] AS path
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive case: reports
    SELECT e.id, e.name, e.manager_id, t.depth + 1, t.path || e.name
    FROM employees e
    JOIN org_tree t ON e.manager_id = t.id
    WHERE t.depth < 10  -- Safety limit
)
SELECT * FROM org_tree ORDER BY path;


-- --- Window functions ---

-- Running total and rank per category
SELECT
    category,
    product_name,
    price,
    SUM(price) OVER (PARTITION BY category ORDER BY price) AS running_total,
    RANK() OVER (PARTITION BY category ORDER BY price DESC) AS price_rank,
    price - LAG(price) OVER (PARTITION BY category ORDER BY price) AS price_diff,
    NTILE(4) OVER (ORDER BY price) AS price_quartile
FROM products;

-- Moving average
SELECT
    date,
    amount,
    AVG(amount) OVER (
        ORDER BY date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7d
FROM daily_sales;


-- --- JSONB operations ---

-- Query nested JSON
SELECT * FROM events
WHERE metadata->>'type' = 'purchase'
AND (metadata->'amount')::numeric > 100
AND metadata @> '{"source": "web"}'::jsonb;

-- Update nested JSON
UPDATE users
SET preferences = jsonb_set(
    preferences,
    '{notifications,email}',
    'true'::jsonb
)
WHERE id = 'user123';

-- Aggregate JSON
SELECT
    user_id,
    jsonb_agg(jsonb_build_object(
        'order_id', id,
        'total', total,
        'date', created_at
    ) ORDER BY created_at DESC) AS recent_orders
FROM orders
GROUP BY user_id;

-- GIN index for JSONB
CREATE INDEX idx_events_metadata ON events USING GIN (metadata jsonb_path_ops);


-- --- Table partitioning ---

-- Range partitioning by date
CREATE TABLE events (
    id BIGSERIAL,
    event_type TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE events_2024_01 PARTITION OF events
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE events_2024_02 PARTITION OF events
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

-- Auto-create partitions with pg_partman
-- SELECT partman.create_parent('public.events', 'created_at', 'native', 'monthly');


-- --- Advisory locks (application-level locking) ---

-- Try to acquire lock (non-blocking)
SELECT pg_try_advisory_lock(hashtext('process_order_123'));

-- Release lock
SELECT pg_advisory_unlock(hashtext('process_order_123'));

-- Session-level lock in Python:
-- async with conn.transaction():
--     acquired = await conn.fetchval(
--         "SELECT pg_try_advisory_xact_lock($1)", lock_id
--     )
--     if not acquired:
--         raise ConflictError("Operation already in progress")
--     # ... do work (lock auto-released at end of transaction)


-- --- Upsert with conflict handling ---

INSERT INTO product_inventory (product_id, warehouse_id, quantity)
VALUES ('prod_1', 'wh_1', 100)
ON CONFLICT (product_id, warehouse_id)
DO UPDATE SET
    quantity = product_inventory.quantity + EXCLUDED.quantity,
    updated_at = NOW()
RETURNING *;
```

PostgreSQL patterns:
1. **Recursive CTEs** — traverse hierarchies (org charts, categories, graphs)
2. **Window functions** — running totals, ranks, moving averages without subqueries
3. **JSONB + GIN index** — flexible schema with indexed queries
4. **Partitioning** — automatic partition pruning for time-series data
5. **Advisory locks** — application-level distributed locking'''
    ),
    (
        "database/full-text-search",
        "Show full-text search patterns: PostgreSQL tsvector, search ranking, faceted search, and autocomplete.",
        '''Full-text search patterns with PostgreSQL:

```sql
-- --- Setup full-text search ---

-- Add tsvector column with GIN index
ALTER TABLE products ADD COLUMN search_vector tsvector;

-- Populate search vector
UPDATE products SET search_vector =
    setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(category, '')), 'C');

-- Create GIN index
CREATE INDEX idx_products_search ON products USING GIN (search_vector);

-- Auto-update trigger
CREATE FUNCTION update_search_vector() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.name, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.description, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.category, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER products_search_update
    BEFORE INSERT OR UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_search_vector();


-- --- Search queries ---

-- Basic search with ranking
SELECT
    id, name, description,
    ts_rank(search_vector, query) AS rank
FROM products,
     to_tsquery('english', 'wireless & bluetooth') AS query
WHERE search_vector @@ query
ORDER BY rank DESC
LIMIT 20;

-- Phrase search
SELECT * FROM products
WHERE search_vector @@ phraseto_tsquery('english', 'noise cancelling headphones');

-- Fuzzy matching with trigram similarity
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_products_name_trgm ON products USING GIN (name gin_trgm_ops);

SELECT name, similarity(name, 'wireles') AS sim
FROM products
WHERE name % 'wireles'  -- Trigram similarity > threshold
ORDER BY sim DESC
LIMIT 10;


-- --- Autocomplete ---

-- Prefix matching for autocomplete
SELECT DISTINCT name
FROM products
WHERE name ILIKE 'wire%'
ORDER BY name
LIMIT 10;

-- Better: trigram + prefix for typo tolerance
SELECT name,
       similarity(name, 'wireles') AS sim,
       ts_rank(search_vector, to_tsquery('english', 'wireles:*')) AS rank
FROM products
WHERE name % 'wireles' OR search_vector @@ to_tsquery('english', 'wireles:*')
ORDER BY sim DESC, rank DESC
LIMIT 10;
```

```python
# --- Python search service ---

class SearchService:
    def __init__(self, pool):
        self.pool = pool

    async def search(self, query: str, category: str = None,
                     page: int = 1, per_page: int = 20) -> dict:
        # Parse and sanitize query
        terms = query.strip().split()
        tsquery = " & ".join(
            f"{term}:*" for term in terms if term
        )

        params = [tsquery, per_page, (page - 1) * per_page]
        where_clauses = ["search_vector @@ to_tsquery('english', $1)"]

        if category:
            where_clauses.append(f"category = ${len(params) + 1}")
            params.append(category)

        where = " AND ".join(where_clauses)

        async with self.pool.acquire() as conn:
            # Search with highlights
            rows = await conn.fetch(f"""
                SELECT
                    id, name, description, category, price,
                    ts_rank(search_vector, to_tsquery('english', $1)) AS rank,
                    ts_headline('english', description,
                        to_tsquery('english', $1),
                        'MaxWords=30, MinWords=15, StartSel=<mark>, StopSel=</mark>'
                    ) AS highlight
                FROM products
                WHERE {where}
                ORDER BY rank DESC
                LIMIT $2 OFFSET $3
            """, *params)

            # Total count
            total = await conn.fetchval(f"""
                SELECT COUNT(*) FROM products WHERE {where}
            """, *params[:1 + (1 if category else 0)])

            # Facets
            facets = await conn.fetch("""
                SELECT category, COUNT(*) as count
                FROM products
                WHERE search_vector @@ to_tsquery('english', $1)
                GROUP BY category
                ORDER BY count DESC
            """, tsquery)

        return {
            "results": [dict(r) for r in rows],
            "total": total,
            "facets": {"categories": [dict(f) for f in facets]},
            "page": page,
            "per_page": per_page,
        }
```

Full-text search patterns:
1. **Weighted vectors** — name (A), description (B), category (C) for relevance ranking
2. **Trigger updates** — auto-update search_vector on INSERT/UPDATE
3. **Prefix matching** — `term:*` for autocomplete ("wire" matches "wireless")
4. **Trigram index** — fuzzy matching and typo tolerance with pg_trgm
5. **Highlights** — `ts_headline` returns search terms marked in context'''
    ),
]
