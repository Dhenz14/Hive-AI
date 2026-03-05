PAIRS = [
    (
        "databases/query-optimization-fundamentals",
        r"""Explain SQL query optimization fundamentals including how query planners work, reading EXPLAIN/EXPLAIN ANALYZE output, index types and when to use each, common anti-patterns that prevent index usage, and join optimization strategies.""",
        r"""## SQL Query Optimization: Query Planners, EXPLAIN, and Index Strategy

Query optimization is the difference between a 50ms response and a 50-second timeout. Understanding how databases execute queries lets you write SQL that cooperates with the optimizer rather than fighting it.

### How Query Planners Work

Every SQL query goes through: Parse → Analyze → Rewrite → Plan → Execute.

The planner considers multiple execution strategies and picks the cheapest one based on **cost estimation**:

```sql
-- The planner considers:
-- 1. Which indexes to use (or full table scan)
-- 2. Join order (for multi-table queries)
-- 3. Join algorithm (nested loop, hash join, merge join)
-- 4. Sort strategy (index scan vs. explicit sort)
-- 5. Aggregation method (hash agg vs. sort agg)

-- PostgreSQL cost model parameters:
-- seq_page_cost = 1.0       (sequential disk read)
-- random_page_cost = 4.0    (random disk read — SSDs: set to 1.1)
-- cpu_tuple_cost = 0.01     (processing one row)
-- cpu_index_tuple_cost = 0.005
-- cpu_operator_cost = 0.0025
```

### Reading EXPLAIN ANALYZE

```sql
-- Always use ANALYZE for real execution statistics
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT u.name, COUNT(o.id) as order_count
FROM users u
JOIN orders o ON o.user_id = u.id
WHERE u.created_at > '2024-01-01'
GROUP BY u.name
ORDER BY order_count DESC
LIMIT 10;

-- Output (annotated):
/*
Limit  (cost=1234.56..1234.59 rows=10 width=48)
       (actual time=45.2..45.3 rows=10 loops=1)
  -> Sort  (cost=1234.56..1245.67 rows=4444 width=48)
           (actual time=45.2..45.2 rows=10 loops=1)
        Sort Key: (count(o.id)) DESC
        Sort Method: top-N heapsort  Memory: 25kB
        -> HashAggregate  (cost=1100.00..1144.44 rows=4444 width=48)
                          (actual time=42.1..43.8 rows=4444 loops=1)
              Group Key: u.name
              Batches: 1  Memory Usage: 625kB
              -> Hash Join  (cost=150.00..1050.00 rows=10000 width=40)
                            (actual time=5.2..35.6 rows=10000 loops=1)
                    Hash Cond: (o.user_id = u.id)
                    -> Seq Scan on orders o
                       (cost=0.00..800.00 rows=50000 width=12)
                       (actual time=0.01..12.3 rows=50000 loops=1)
                    -> Hash  (cost=125.00..125.00 rows=2000 width=36)
                             (actual time=4.8..4.8 rows=2000 loops=1)
                          Buckets: 2048  Memory: 150kB
                          -> Index Scan using idx_users_created
                             on users u
                             (cost=0.29..125.00 rows=2000 width=36)
                             (actual time=0.05..3.2 rows=2000 loops=1)
                                Index Cond: (created_at > '2024-01-01')
Planning Time: 0.5 ms
Execution Time: 45.8 ms
Buffers: shared hit=850 read=45
*/

-- Key things to look for:
-- 1. "actual time" vs "cost" — big discrepancy means stale statistics
-- 2. "rows" estimate vs actual — wrong estimates cause bad plans
-- 3. Seq Scan on large tables — usually needs an index
-- 4. "Buffers: read" — disk I/O, want mostly "hit" (cache)
-- 5. Nested Loop with high "loops" count — may need hash/merge join
```

### Index Types and When to Use Each

```sql
-- B-Tree (default): equality and range queries
CREATE INDEX idx_users_email ON users (email);
-- Good for: =, <, >, <=, >=, BETWEEN, IN, IS NULL
-- Good for: ORDER BY, GROUP BY
-- Most common choice — use this unless you have a reason not to

-- Composite index: multi-column queries
CREATE INDEX idx_orders_user_date ON orders (user_id, created_at DESC);
-- Follows the "leftmost prefix" rule:
-- Uses index: WHERE user_id = 1
-- Uses index: WHERE user_id = 1 AND created_at > '2024-01-01'
-- Does NOT use index: WHERE created_at > '2024-01-01' (missing left column)

-- Covering index (INCLUDE): avoids table lookups
CREATE INDEX idx_orders_covering ON orders (user_id)
  INCLUDE (total, status);
-- Index-only scan: SELECT total, status FROM orders WHERE user_id = 1
-- The included columns are in the index leaf pages but NOT used for searching

-- Partial index: index a subset of rows
CREATE INDEX idx_orders_pending ON orders (created_at)
  WHERE status = 'pending';
-- Much smaller than full index, faster for common queries
-- Only used when WHERE clause matches the predicate

-- GIN (Generalized Inverted Index): arrays, JSONB, full-text
CREATE INDEX idx_tags ON articles USING GIN (tags);
-- Good for: @>, ?, ?|, ?& operators on JSONB
-- Good for: array containment, full-text search

-- GiST (Generalized Search Tree): geometric, range, nearest-neighbor
CREATE INDEX idx_location ON stores USING GiST (location);
-- Good for: spatial queries, range types, nearest-neighbor search

-- BRIN (Block Range Index): large naturally-ordered tables
CREATE INDEX idx_events_time ON events USING BRIN (created_at);
-- Tiny index (128KB vs 2GB B-tree for 1B rows)
-- Only useful when data is physically sorted by the column
-- Perfect for append-only time-series tables

-- Hash index: equality-only, very fast
CREATE INDEX idx_session ON sessions USING HASH (session_id);
-- Only good for = comparisons, not ranges
-- Slightly faster than B-tree for exact matches
```

### Common Anti-Patterns That Prevent Index Usage

```sql
-- Anti-pattern 1: Function on indexed column
-- BAD: index on email is NOT used
SELECT * FROM users WHERE LOWER(email) = 'alice@example.com';
-- FIX: expression index
CREATE INDEX idx_users_email_lower ON users (LOWER(email));
-- OR: store normalized data

-- Anti-pattern 2: Implicit type casting
-- BAD: user_id is INTEGER but compared to TEXT
SELECT * FROM orders WHERE user_id = '123';
-- The cast prevents index usage on some databases
-- FIX: use correct types
SELECT * FROM orders WHERE user_id = 123;

-- Anti-pattern 3: Leading wildcard in LIKE
-- BAD: cannot use B-tree index
SELECT * FROM users WHERE name LIKE '%smith%';
-- FIX: use full-text search or trigram index
CREATE INDEX idx_name_trgm ON users USING GIN (name gin_trgm_ops);
SELECT * FROM users WHERE name ILIKE '%smith%';

-- Anti-pattern 4: OR conditions on different columns
-- BAD: typically results in sequential scan
SELECT * FROM users WHERE email = 'x' OR phone = '555-1234';
-- FIX: UNION approach
SELECT * FROM users WHERE email = 'x'
UNION
SELECT * FROM users WHERE phone = '555-1234';

-- Anti-pattern 5: NOT IN with subquery
-- BAD: often prevents index usage and is slow with NULLs
SELECT * FROM users WHERE id NOT IN (SELECT user_id FROM banned);
-- FIX: use NOT EXISTS or LEFT JOIN
SELECT u.* FROM users u
LEFT JOIN banned b ON u.id = b.user_id
WHERE b.user_id IS NULL;

-- Anti-pattern 6: Selecting too many columns
-- BAD: forces table lookup even with covering index
SELECT * FROM orders WHERE user_id = 1;
-- FIX: select only needed columns
SELECT id, total, status FROM orders WHERE user_id = 1;
```

### Join Optimization

```sql
-- The planner chooses between three join algorithms:

-- 1. Nested Loop: best for small result sets with indexed lookup
-- For each row in outer table, look up matching rows in inner table
-- Cost: O(N * M) without index, O(N * log M) with index
-- Used when: one side is small and inner side has an index

-- 2. Hash Join: best for equi-joins on large tables
-- Build hash table from smaller table, probe with larger table
-- Cost: O(N + M) but needs memory for hash table
-- Used when: both tables are large, no useful index

-- 3. Merge Join: best for pre-sorted data
-- Both inputs must be sorted on join key
-- Cost: O(N log N + M log M) for sort + O(N + M) for merge
-- Used when: data is already sorted (from index) or needs ORDER BY

-- Force join order hints (use sparingly):
-- PostgreSQL:
SET join_collapse_limit = 1;  -- Respect FROM clause order

-- Example: ensure small table is the driver
SELECT /*+ Leading(small_table big_table) */
  s.*, b.value
FROM small_table s
JOIN big_table b ON s.id = b.small_id;
```

**Optimization checklist**: (1) Run `EXPLAIN ANALYZE` — never guess, always measure, (2) Check if row estimates match actuals — run `ANALYZE` on tables with stale statistics, (3) Ensure indexes match WHERE, JOIN, ORDER BY columns, (4) Use composite indexes with correct column order (most selective first), (5) Avoid functions on indexed columns — create expression indexes instead, (6) For large result sets, consider if you really need all columns and all rows."""
    ),
    (
        "databases/postgresql-advanced-features",
        r"""Explain advanced PostgreSQL features including CTEs and recursive queries, window functions, LATERAL joins, generated columns, partitioning strategies, and advisory locks. Include practical examples for each feature.""",
        r"""## Advanced PostgreSQL Features: CTEs, Window Functions, Partitioning, and Beyond

PostgreSQL offers powerful features beyond standard SQL that can simplify complex queries and improve performance dramatically.

### Common Table Expressions (CTEs)

CTEs create named temporary result sets within a query:

```sql
-- Simple CTE for readability
WITH active_users AS (
    SELECT id, name, email
    FROM users
    WHERE last_login > CURRENT_DATE - INTERVAL '30 days'
    AND status = 'active'
),
user_orders AS (
    SELECT user_id, COUNT(*) as order_count, SUM(total) as total_spent
    FROM orders
    WHERE created_at > CURRENT_DATE - INTERVAL '30 days'
    GROUP BY user_id
)
SELECT
    au.name,
    au.email,
    COALESCE(uo.order_count, 0) as orders,
    COALESCE(uo.total_spent, 0) as spent
FROM active_users au
LEFT JOIN user_orders uo ON au.id = uo.user_id
ORDER BY spent DESC;

-- IMPORTANT: In PostgreSQL 12+, CTEs can be inlined (optimized)
-- Add MATERIALIZED to force separate evaluation:
WITH MATERIALIZED expensive_calc AS (
    SELECT user_id, complex_function(data) as result
    FROM big_table
)
SELECT * FROM expensive_calc WHERE result > threshold;
```

### Recursive CTEs

Traverse hierarchies, generate series, and solve graph problems:

```sql
-- Organizational hierarchy
WITH RECURSIVE org_tree AS (
    -- Base case: top-level managers
    SELECT id, name, manager_id, 1 as depth,
           ARRAY[name] as path
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive case: employees under current level
    SELECT e.id, e.name, e.manager_id, ot.depth + 1,
           ot.path || e.name
    FROM employees e
    JOIN org_tree ot ON e.manager_id = ot.id
    WHERE ot.depth < 10  -- Safety limit!
)
SELECT
    repeat('  ', depth - 1) || name as org_chart,
    depth,
    array_to_string(path, ' > ') as chain
FROM org_tree
ORDER BY path;

-- Bill of materials (parts explosion)
WITH RECURSIVE bom AS (
    SELECT part_id, component_id, quantity, 1 as level
    FROM assemblies
    WHERE part_id = 'WIDGET-100'

    UNION ALL

    SELECT a.part_id, a.component_id, a.quantity * bom.quantity, bom.level + 1
    FROM assemblies a
    JOIN bom ON a.part_id = bom.component_id
    WHERE bom.level < 20
)
SELECT component_id, SUM(quantity) as total_needed
FROM bom
GROUP BY component_id
ORDER BY total_needed DESC;

-- Graph traversal: shortest path
WITH RECURSIVE paths AS (
    SELECT
        destination as current_node,
        ARRAY[origin, destination] as path,
        distance as total_distance
    FROM routes
    WHERE origin = 'NYC'

    UNION ALL

    SELECT
        r.destination,
        p.path || r.destination,
        p.total_distance + r.distance
    FROM paths p
    JOIN routes r ON r.origin = p.current_node
    WHERE r.destination != ALL(p.path)  -- Prevent cycles
    AND p.total_distance + r.distance < 10000  -- Prune
)
SELECT path, total_distance
FROM paths
WHERE current_node = 'LAX'
ORDER BY total_distance
LIMIT 1;
```

### Window Functions

Compute values across related rows without collapsing them:

```sql
-- Running totals and moving averages
SELECT
    date,
    revenue,
    SUM(revenue) OVER (ORDER BY date) as cumulative_revenue,
    AVG(revenue) OVER (
        ORDER BY date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) as moving_avg_7d,
    revenue - LAG(revenue) OVER (ORDER BY date) as daily_change,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (ORDER BY date))
        / NULLIF(LAG(revenue) OVER (ORDER BY date), 0), 1
    ) as pct_change
FROM daily_revenue;

-- Ranking within groups
SELECT
    department,
    name,
    salary,
    RANK() OVER (PARTITION BY department ORDER BY salary DESC) as dept_rank,
    DENSE_RANK() OVER (ORDER BY salary DESC) as company_rank,
    NTILE(4) OVER (ORDER BY salary DESC) as salary_quartile,
    PERCENT_RANK() OVER (ORDER BY salary) as percentile
FROM employees;

-- First/last value in group
SELECT DISTINCT
    department,
    FIRST_VALUE(name) OVER w as highest_paid,
    LAST_VALUE(name) OVER w as lowest_paid,
    AVG(salary) OVER (PARTITION BY department) as avg_salary
FROM employees
WINDOW w AS (
    PARTITION BY department
    ORDER BY salary DESC
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
);

-- Gap detection (find missing sequence numbers)
SELECT
    id,
    LEAD(id) OVER (ORDER BY id) as next_id,
    LEAD(id) OVER (ORDER BY id) - id as gap_size
FROM invoices
HAVING LEAD(id) OVER (ORDER BY id) - id > 1;
```

### LATERAL Joins

Correlated subqueries in the FROM clause — use the current row in a subquery:

```sql
-- Top N per group (get latest 3 orders per user)
SELECT u.name, recent_orders.*
FROM users u
CROSS JOIN LATERAL (
    SELECT id, total, created_at
    FROM orders o
    WHERE o.user_id = u.id
    ORDER BY created_at DESC
    LIMIT 3
) recent_orders
WHERE u.status = 'active';

-- Unnest with ordinality (expand arrays with position)
SELECT
    p.name,
    t.tag,
    t.position
FROM products p
CROSS JOIN LATERAL unnest(p.tags) WITH ORDINALITY AS t(tag, position);

-- Dependent function call
SELECT
    city.name,
    weather.*
FROM cities city
CROSS JOIN LATERAL get_weather(city.latitude, city.longitude) AS weather;
```

### Table Partitioning

Split large tables for query performance and maintenance:

```sql
-- Range partitioning by date (most common)
CREATE TABLE events (
    id          BIGSERIAL,
    event_type  TEXT NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- Create partitions
CREATE TABLE events_2024_q1 PARTITION OF events
    FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');
CREATE TABLE events_2024_q2 PARTITION OF events
    FOR VALUES FROM ('2024-04-01') TO ('2024-07-01');
CREATE TABLE events_2024_q3 PARTITION OF events
    FOR VALUES FROM ('2024-07-01') TO ('2024-10-01');

-- Default partition for anything that doesn't match
CREATE TABLE events_default PARTITION OF events DEFAULT;

-- Indexes are inherited by partitions
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_events_created ON events (created_at);

-- Queries automatically prune partitions
EXPLAIN SELECT * FROM events
WHERE created_at BETWEEN '2024-04-01' AND '2024-06-30';
-- Only scans events_2024_q2, skips all others

-- Automatic partition creation (pg_partman extension)
-- Or create a function to auto-create monthly partitions
CREATE OR REPLACE FUNCTION create_monthly_partition()
RETURNS TRIGGER AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    start_date := DATE_TRUNC('month', NEW.created_at);
    end_date := start_date + INTERVAL '1 month';
    partition_name := 'events_' || TO_CHAR(start_date, 'YYYY_MM');

    IF NOT EXISTS (
        SELECT 1 FROM pg_class WHERE relname = partition_name
    ) THEN
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF events FOR VALUES FROM (%L) TO (%L)',
            partition_name, start_date, end_date
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### Advisory Locks

Application-level distributed locking without table locks:

```sql
-- Session-level advisory lock (held until released or session ends)
SELECT pg_advisory_lock(hashtext('process-payments'));
-- ... do exclusive work ...
SELECT pg_advisory_unlock(hashtext('process-payments'));

-- Transaction-level advisory lock (auto-released at COMMIT/ROLLBACK)
SELECT pg_advisory_xact_lock(hashtext('user-123-balance'));
UPDATE accounts SET balance = balance - 100 WHERE user_id = 123;
COMMIT;  -- Lock automatically released

-- Try-lock (non-blocking)
SELECT pg_try_advisory_lock(hashtext('singleton-job'));
-- Returns TRUE if acquired, FALSE if already held
```

```python
import asyncpg
from contextlib import asynccontextmanager


@asynccontextmanager
async def advisory_lock(pool: asyncpg.Pool, lock_key: str):
    """Distributed lock using PostgreSQL advisory locks."""
    lock_id = hash(lock_key) % (2**63)  # Must be bigint

    async with pool.acquire() as conn:
        acquired = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)", lock_id
        )
        if not acquired:
            raise LockNotAcquired(f"Could not acquire lock: {lock_key}")
        try:
            yield conn
        finally:
            await conn.fetchval(
                "SELECT pg_advisory_unlock($1)", lock_id
            )


# Usage:
async def process_payment(pool, user_id: int, amount: float):
    async with advisory_lock(pool, f"payment-{user_id}"):
        balance = await pool.fetchval(
            "SELECT balance FROM accounts WHERE user_id = $1",
            user_id
        )
        if balance < amount:
            raise InsufficientFunds()
        await pool.execute(
            "UPDATE accounts SET balance = balance - $1 WHERE user_id = $2",
            amount, user_id
        )
```

**Feature selection guide**: (1) CTEs for readability and breaking complex queries into steps, (2) Recursive CTEs for tree/graph traversal — always include a depth limit, (3) Window functions when you need per-row calculations relative to a group, (4) LATERAL joins for top-N-per-group and correlated subqueries, (5) Partitioning for tables > 100M rows queried by the partition key, (6) Advisory locks for application-level distributed coordination."""
    ),
    (
        "databases/query-performance-patterns",
        r"""Explain practical SQL performance patterns including pagination strategies (offset vs cursor), efficient upserts, batch operations, materialized views for expensive aggregations, and query result caching strategies.""",
        r"""## SQL Performance Patterns: Pagination, Upserts, Batching, and Caching

These patterns solve common performance problems that appear at scale — when naive approaches that work fine with 10K rows collapse at 10M.

### Pagination: Offset vs Cursor

```sql
-- OFFSET pagination: simple but SLOW at deep pages
-- Page 1000 of 20 items: database must read AND DISCARD 19,980 rows
SELECT * FROM products ORDER BY id LIMIT 20 OFFSET 19980;
-- Gets slower linearly with page number

-- Cursor (keyset) pagination: constant performance at any depth
-- Instead of "page 1000", say "items after the last one I saw"
SELECT * FROM products
WHERE id > 99980           -- Last ID from previous page
ORDER BY id
LIMIT 20;
-- Always fast: just an index seek + 20 rows

-- Cursor pagination with composite sort
SELECT * FROM products
WHERE (created_at, id) < ('2024-06-15 10:30:00', 55432)
ORDER BY created_at DESC, id DESC
LIMIT 20;
-- Requires index: CREATE INDEX idx_products_cursor ON products (created_at DESC, id DESC);

-- For search results with relevance ranking:
-- Use a score + tiebreaker cursor
SELECT id, title, ts_rank(search_vector, query) as score
FROM products,
     to_tsquery('english', 'wireless & headphones') query
WHERE search_vector @@ query
  AND (ts_rank(search_vector, query), id) < (0.85, 12345)
ORDER BY score DESC, id DESC
LIMIT 20;
```

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class CursorPage:
    items: list
    next_cursor: Optional[str]
    has_more: bool


async def paginate_cursor(
    pool,
    cursor: Optional[str] = None,
    limit: int = 20,
) -> CursorPage:
    """Efficient cursor-based pagination."""
    # Decode cursor
    if cursor:
        last_date, last_id = cursor.split("|")
        rows = await pool.fetch(
            """
            SELECT id, name, created_at FROM products
            WHERE (created_at, id) < ($1::timestamptz, $2::bigint)
            ORDER BY created_at DESC, id DESC
            LIMIT $3
            """,
            last_date, int(last_id), limit + 1  # Fetch one extra
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, name, created_at FROM products
            ORDER BY created_at DESC, id DESC
            LIMIT $1
            """,
            limit + 1
        )

    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = f"{last['created_at'].isoformat()}|{last['id']}"

    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)
```

### Efficient Upserts

```sql
-- PostgreSQL INSERT ... ON CONFLICT (upsert)
INSERT INTO user_stats (user_id, login_count, last_login)
VALUES (123, 1, NOW())
ON CONFLICT (user_id) DO UPDATE SET
    login_count = user_stats.login_count + EXCLUDED.login_count,
    last_login = EXCLUDED.last_login;

-- Bulk upsert with UNNEST (much faster than individual INSERTs)
INSERT INTO product_prices (product_id, price, updated_at)
SELECT * FROM UNNEST(
    $1::bigint[],       -- product_ids array
    $2::numeric[],      -- prices array
    $3::timestamptz[]   -- timestamps array
)
ON CONFLICT (product_id) DO UPDATE SET
    price = EXCLUDED.price,
    updated_at = EXCLUDED.updated_at
WHERE product_prices.price != EXCLUDED.price;  -- Only update if changed

-- Upsert with RETURNING to know what happened
WITH upserted AS (
    INSERT INTO features (key, value, version)
    VALUES ('dark_mode', 'true', 1)
    ON CONFLICT (key) DO UPDATE SET
        value = EXCLUDED.value,
        version = features.version + 1
    RETURNING *, (xmax = 0) as was_inserted
)
SELECT * FROM upserted;
-- was_inserted: true = new row, false = updated existing
```

### Batch Operations

```sql
-- BAD: N individual INSERTs
-- for item in items:
--     INSERT INTO orders (user_id, total) VALUES ($1, $2)
-- 1000 items = 1000 round trips to database

-- GOOD: Single multi-row INSERT
INSERT INTO orders (user_id, total)
VALUES
    (1, 99.99),
    (2, 149.50),
    (3, 79.00);
-- 1 round trip regardless of row count

-- GOOD: COPY for bulk loading (fastest)
COPY orders (user_id, total, created_at)
FROM STDIN WITH (FORMAT csv);
-- 10x-100x faster than INSERT for large batches
```

```python
import asyncpg


async def batch_insert(pool: asyncpg.Pool, records: list[tuple]):
    """Efficient batch insert using COPY protocol."""
    async with pool.acquire() as conn:
        # copy_records_to_table: uses binary COPY protocol
        await conn.copy_records_to_table(
            "orders",
            columns=["user_id", "product_id", "total", "created_at"],
            records=records,
        )


async def batch_update(pool: asyncpg.Pool, updates: list[dict]):
    """Batch update using temporary table pattern."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Create temp table
            await conn.execute("""
                CREATE TEMP TABLE tmp_updates (
                    id BIGINT PRIMARY KEY,
                    new_status TEXT,
                    new_score FLOAT
                ) ON COMMIT DROP
            """)

            # Bulk load updates
            await conn.copy_records_to_table(
                "tmp_updates",
                records=[(u["id"], u["status"], u["score"]) for u in updates],
            )

            # Single UPDATE from temp table
            count = await conn.execute("""
                UPDATE orders o
                SET status = t.new_status,
                    score = t.new_score
                FROM tmp_updates t
                WHERE o.id = t.id
            """)
            return count
```

### Materialized Views

Pre-compute expensive aggregations:

```sql
-- Create materialized view for dashboard metrics
CREATE MATERIALIZED VIEW daily_revenue_mv AS
SELECT
    DATE_TRUNC('day', created_at) as day,
    product_category,
    COUNT(*) as order_count,
    SUM(total) as revenue,
    AVG(total) as avg_order_value,
    COUNT(DISTINCT user_id) as unique_buyers
FROM orders o
JOIN products p ON o.product_id = p.id
WHERE o.status = 'completed'
GROUP BY DATE_TRUNC('day', created_at), product_category
WITH DATA;

-- Index the materialized view
CREATE UNIQUE INDEX idx_daily_revenue_mv
ON daily_revenue_mv (day, product_category);

-- Refresh (full rebuild — blocks reads during refresh)
REFRESH MATERIALIZED VIEW daily_revenue_mv;

-- Concurrent refresh (no read blocking, requires unique index)
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_revenue_mv;

-- Automate refresh with pg_cron
SELECT cron.schedule(
    'refresh-daily-revenue',
    '*/15 * * * *',  -- Every 15 minutes
    'REFRESH MATERIALIZED VIEW CONCURRENTLY daily_revenue_mv'
);
```

```python
async def get_dashboard_metrics(
    pool: asyncpg.Pool,
    start_date: str,
    end_date: str,
) -> list:
    """Query the materialized view — instant response."""
    return await pool.fetch(
        """
        SELECT day, product_category, order_count, revenue,
               avg_order_value, unique_buyers
        FROM daily_revenue_mv
        WHERE day BETWEEN $1 AND $2
        ORDER BY day DESC, revenue DESC
        """,
        start_date, end_date
    )
    # Sub-millisecond response vs 30+ seconds on raw tables
```

### Query Result Caching

```python
import hashlib
import json
import asyncio
from typing import Optional


class QueryCache:
    """Application-level query result cache with Redis."""

    def __init__(self, redis_client, default_ttl: int = 300):
        self.redis = redis_client
        self.default_ttl = default_ttl

    def _cache_key(self, query: str, params: tuple) -> str:
        content = json.dumps({"q": query, "p": list(params)}, sort_keys=True)
        return f"qcache:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    async def execute_cached(
        self,
        pool,
        query: str,
        *params,
        ttl: Optional[int] = None,
    ) -> list:
        cache_key = self._cache_key(query, params)
        ttl = ttl or self.default_ttl

        # Try cache first
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # Execute query
        rows = await pool.fetch(query, *params)
        result = [dict(row) for row in rows]

        # Cache result (fire-and-forget)
        asyncio.create_task(
            self.redis.set(cache_key, json.dumps(result, default=str), ex=ttl)
        )

        return result

    async def invalidate_pattern(self, pattern: str):
        """Invalidate all cached queries matching a pattern."""
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match=f"qcache:{pattern}*", count=100
            )
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break
```

**Performance patterns priority**: (1) Cursor pagination for any user-facing list — never use OFFSET past page 10, (2) Batch operations for writes — individual INSERTs are 100x slower, (3) Materialized views for dashboards and reports — pre-compute expensive aggregations, (4) Upserts with ON CONFLICT for idempotent write operations, (5) Application-level caching for read-heavy queries with TTL-based invalidation."""
    ),
    (
        "databases/connection-pooling-strategies",
        r"""Explain database connection pooling including why it matters, PgBouncer configuration and pool modes, application-level pooling with asyncpg/SQLAlchemy, pool sizing formulas, and diagnosing connection exhaustion.""",
        r"""## Database Connection Pooling: PgBouncer, Application Pools, and Sizing

Every database connection costs memory (typically 5-10MB per connection in PostgreSQL), a process or thread, and file descriptors. Without pooling, a burst of 1000 requests creates 1000 connections, exhausting database resources.

### Why Pooling Matters

```
Without pooling:
  Request → Open Connection → Execute Query → Close Connection
  1000 concurrent requests = 1000 connections = 10GB RAM on DB server

With pooling:
  Request → Get Connection from Pool → Execute Query → Return to Pool
  1000 concurrent requests = 20 pool connections = 200MB RAM on DB server
```

### PgBouncer: External Connection Pooler

PgBouncer sits between your application and PostgreSQL, multiplexing many client connections onto few server connections:

```ini
; /etc/pgbouncer/pgbouncer.ini

[databases]
myapp = host=localhost port=5432 dbname=myapp

[pgbouncer]
; Pool mode determines when connections are returned to pool:
;   session     - returned when client disconnects (least aggressive)
;   transaction - returned when transaction completes (recommended)
;   statement   - returned after each statement (most aggressive, limited)
pool_mode = transaction

; Pool sizing
default_pool_size = 20        ; Connections per user/database pair
min_pool_size = 5             ; Keep this many connections warm
max_client_conn = 1000        ; Max client connections to PgBouncer
max_db_connections = 50       ; Max connections to actual PostgreSQL

; Timeouts
server_idle_timeout = 300     ; Close idle server connections after 5min
client_idle_timeout = 0       ; Never close idle clients (app manages this)
query_timeout = 30            ; Kill queries running > 30s
server_connect_timeout = 3    ; Timeout for new server connections

; Connection validation
server_reset_query = DISCARD ALL  ; Clean state between transactions
server_check_query = SELECT 1     ; Health check query
server_check_delay = 30           ; Health check interval

; Auth
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
```

```bash
# Monitor PgBouncer
psql -p 6432 -U pgbouncer pgbouncer -c "SHOW POOLS;"
# database | user | cl_active | cl_waiting | sv_active | sv_idle | sv_used
# myapp    | app  | 45        | 0          | 12        | 8       | 0

# cl_waiting > 0 means clients are waiting for connections = pool exhaustion!

# Show active server connections
psql -p 6432 pgbouncer -c "SHOW SERVERS;"

# Show statistics
psql -p 6432 pgbouncer -c "SHOW STATS;"
```

### Application-Level Pooling

```python
# asyncpg — async PostgreSQL driver with built-in pooling
import asyncpg


async def setup_pool():
    pool = await asyncpg.create_pool(
        dsn="postgresql://user:pass@localhost:5432/myapp",
        min_size=5,           # Minimum connections kept open
        max_size=20,          # Maximum connections
        max_inactive_connection_lifetime=300,  # Close idle after 5min
        command_timeout=30,   # Query timeout
        setup=_setup_connection,  # Per-connection initialization
    )
    return pool


async def _setup_connection(conn):
    """Called when a new connection is created."""
    # Set session-level parameters
    await conn.execute("SET timezone = 'UTC'")
    await conn.execute("SET statement_timeout = '30s'")
    # Register custom type codecs
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def query_example(pool: asyncpg.Pool):
    # Method 1: Implicit acquire/release
    row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

    # Method 2: Explicit acquire for multiple queries
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, from_id)
            await conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, to_id)
```

```python
# SQLAlchemy 2.0 — async pooling
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool


engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/myapp",
    pool_size=20,            # Number of persistent connections
    max_overflow=10,         # Extra connections under load (total max: 30)
    pool_timeout=5,          # Wait max 5s for a connection
    pool_recycle=1800,       # Recycle connections after 30min
    pool_pre_ping=True,      # Test connection health before using
    echo_pool="debug",       # Log pool events
    poolclass=AsyncAdaptedQueuePool,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Pool Sizing Formula

The optimal pool size depends on your workload, not your connection count:

```python
def calculate_pool_size(
    cpu_cores: int,
    disk_type: str = "ssd",
    concurrent_io: int = 1,
) -> int:
    """
    PostgreSQL pool size formula from the PostgreSQL wiki:

    pool_size = cpu_cores * 2 + effective_spindle_count

    For SSDs, effective_spindle_count ≈ 1 (parallel I/O is handled internally)
    For HDDs, effective_spindle_count = number of disks

    Key insight: adding more connections HURTS performance past the
    optimal point because of context switching and lock contention.
    """
    if disk_type == "ssd":
        spindles = 1
    else:
        spindles = concurrent_io

    optimal = cpu_cores * 2 + spindles

    # Real-world adjustments:
    # - If queries are mostly CPU-bound: pool_size ≈ cpu_cores
    # - If queries are mostly I/O-bound: pool_size can be 2-3x optimal
    # - Never exceed: cpu_cores * 4

    return optimal


# Example: 8-core server with SSD
# Optimal pool size = 8 * 2 + 1 = 17 connections
# NOT 100, NOT 200 — just 17!

# For microservices with many instances:
# If you have 10 pods each with pool_size=20 → 200 connections
# Database can handle maybe 100 → use PgBouncer between
```

### Diagnosing Connection Exhaustion

```sql
-- Check current connections
SELECT
    datname,
    usename,
    application_name,
    client_addr,
    state,
    COUNT(*) as count
FROM pg_stat_activity
GROUP BY datname, usename, application_name, client_addr, state
ORDER BY count DESC;

-- Find idle connections that should be closed
SELECT
    pid,
    usename,
    application_name,
    state,
    state_change,
    NOW() - state_change as idle_duration,
    query
FROM pg_stat_activity
WHERE state = 'idle'
AND NOW() - state_change > INTERVAL '5 minutes'
ORDER BY idle_duration DESC;

-- Find long-running queries blocking connections
SELECT
    pid,
    NOW() - query_start as duration,
    state,
    LEFT(query, 100) as query_preview
FROM pg_stat_activity
WHERE state != 'idle'
AND NOW() - query_start > INTERVAL '30 seconds'
ORDER BY duration DESC;

-- Check max connections and current usage
SELECT
    setting::int as max_connections,
    (SELECT COUNT(*) FROM pg_stat_activity) as current,
    setting::int - (SELECT COUNT(*) FROM pg_stat_activity) as available
FROM pg_settings
WHERE name = 'max_connections';
```

```python
# Connection pool health monitoring
import asyncio


class PoolMonitor:
    """Monitor connection pool health and alert on issues."""

    def __init__(self, pool: asyncpg.Pool, check_interval: float = 10.0):
        self.pool = pool
        self.check_interval = check_interval

    async def start(self):
        while True:
            stats = {
                "size": self.pool.get_size(),
                "free": self.pool.get_idle_size(),
                "used": self.pool.get_size() - self.pool.get_idle_size(),
                "min": self.pool.get_min_size(),
                "max": self.pool.get_max_size(),
            }

            utilization = stats["used"] / max(stats["size"], 1)

            if utilization > 0.9:
                logger.warning(
                    f"Pool near exhaustion: {stats['used']}/{stats['size']} "
                    f"({utilization:.0%} utilized)"
                )

            if stats["free"] == 0 and stats["size"] >= stats["max"]:
                logger.error(
                    "Pool EXHAUSTED — requests will queue/timeout. "
                    f"Max: {stats['max']}, all in use."
                )

            # Emit metrics
            metrics.gauge("db.pool.size", stats["size"])
            metrics.gauge("db.pool.used", stats["used"])
            metrics.gauge("db.pool.free", stats["free"])
            metrics.gauge("db.pool.utilization", utilization)

            await asyncio.sleep(self.check_interval)
```

**Connection pooling rules**: (1) Always use a connection pooler — never let applications open connections directly, (2) Pool size = `cpu_cores * 2 + 1` for the database, not per-application, (3) Use PgBouncer in transaction mode between applications and PostgreSQL, (4) Monitor `cl_waiting` (PgBouncer) or pool utilization — if connections wait, your pool is too small OR queries are too slow, (5) Set timeouts at every layer: query timeout, connection timeout, pool acquire timeout."""
    ),
]
