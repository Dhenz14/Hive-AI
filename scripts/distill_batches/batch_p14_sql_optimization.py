'''p14 sql optimization'''

PAIRS = [
    (
        "databases/query-optimization-fundamentals",
        "Explain SQL query optimization fundamentals including how query planners work, reading EXPLAIN/EXPLAIN ANALYZE output, index types and when to use each, common anti-patterns that prevent index usage, and join optimization strategies.",
        """### How Query Planners Work

Every SQL query goes through: Parse -> Analyze -> Rewrite -> Plan -> Execute.

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
-- random_page_cost = 4.0    (random disk read -- SSDs: set to 1.1)
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
-- 1. "actual time" vs "cost" -- big discrepancy means stale statistics
-- 2. "rows" estimate vs actual -- wrong estimates cause bad plans
-- 3. Seq Scan on large tables -- usually needs an index
-- 4. "Buffers: read" -- disk I/O, want mostly "hit" (cache)
-- 5. Nested Loop with high "loops" count -- may need hash/merge join
```

### Index Types and When to Use Each

```sql
-- B-Tree (default): equality and range queries
CREATE INDEX idx_users_email ON users (email);
-- Good for: =, <, >, <=, >=, BETWEEN, IN, IS NULL
-- Good for: ORDER BY, GROUP BY
-- Most common choice -- use this unless you have a reason not to

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

**Optimization checklist**: (1) Run `EXPLAIN ANALYZE` -- never guess, always measure, (2) Check if row estimates match actuals -- run `ANALYZE` on tables with stale statistics, (3) Ensure indexes match WHERE, JOIN, ORDER BY columns, (4) Use composite indexes with correct column order (most selective first), (5) Avoid functions on indexed columns -- create expression indexes instead, (6) For large result sets, consider if you really need all columns and all rows."""
    ),
    (
        "databases/postgresql-advanced-features",
        "Explain advanced PostgreSQL features including CTEs and recursive queries, window functions, LATERAL joins, generated columns, partitioning strategies, and advisory locks. Include practical examples for each feature.",
        """### Common Table Expressions (CTEs)

CTEs create named temporary result sets within a query:

```sql
-- Simple CTE for readability
WITH active_users AS (
    SELECT id, name, email
    FROM users
    WHERE last_login > CURRENT_DATE - INTERVAL '30 days'
    AND status = 'active'"""
    ),
    (
        "databases/query-performance-patterns",
        "Explain practical SQL performance patterns including pagination strategies (offset vs cursor), efficient upserts, batch operations, materialized views for expensive aggregations, and query result caching strategies.",
        """### Pagination: Offset vs Cursor

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
    '''Efficient cursor-based pagination.'''
    # Decode cursor
    if cursor:
        last_date, last_id = cursor.split("|")
        rows = await pool.fetch(
            '''
            SELECT id, name, created_at FROM products
            WHERE (created_at, id) < ($1::timestamptz, $2::bigint)
            ORDER BY created_at DESC, id DESC
            LIMIT $3
            ''',
            last_date, int(last_id), limit + 1  # Fetch one extra"""
    ),
    (
        "orders",
        "columns=['user_id', 'product_id', 'total', 'created_at'] records=records ) async def batch_update(pool: asyncpg.Pool, updates: list[dict]):",
        """async with conn.transaction():
            # Create temp table
            await conn.execute('''
                CREATE TEMP TABLE tmp_updates (
                    id BIGINT PRIMARY KEY,
                    new_status TEXT,
                    new_score FLOAT
                ) ON COMMIT DROP
            ''')

            # Bulk load updates
            await conn.copy_records_to_table("""
    ),
    (
        "tmp_updates",
        "records=[(u['id'], u['status'], u['score']) for u in updates] )",
        """count = await conn.execute('''
                UPDATE orders o
                SET status = t.new_status,
                    score = t.new_score
                FROM tmp_updates t
                WHERE o.id = t.id
            ''')
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

-- Refresh (full rebuild -- blocks reads during refresh)
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
    '''Query the materialized view -- instant response.'''
    return await pool.fetch(
        '''
        SELECT day, product_category, order_count, revenue,
               avg_order_value, unique_buyers
        FROM daily_revenue_mv
        WHERE day BETWEEN $1 AND $2
        ORDER BY day DESC, revenue DESC
        ''',
        start_date, end_date"""
    ),
    (
        "databases/connection-pooling-strategies",
        "Explain database connection pooling including why it matters, PgBouncer configuration and pool modes, application-level pooling with asyncpg/SQLAlchemy, pool sizing formulas, and diagnosing connection exhaustion.",
        """### Why Pooling Matters

```
Without pooling:
  Request -> Open Connection -> Execute Query -> Close Connection
  1000 concurrent requests = 1000 connections = 10GB RAM on DB server

With pooling:
  Request -> Get Connection from Pool -> Execute Query -> Return to Pool
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
# asyncpg -- async PostgreSQL driver with built-in pooling
import asyncpg


async def setup_pool():
    pool = await asyncpg.create_pool(
        dsn="postgresql://user:pass@localhost:5432/myapp",
        min_size=5,           # Minimum connections kept open
        max_size=20,          # Maximum connections
        max_inactive_connection_lifetime=300,  # Close idle after 5min
        command_timeout=30,   # Query timeout
        setup=_setup_connection,  # Per-connection initialization"""
    ),
    (
        "jsonb",
        ") async def query_example(pool: asyncpg.Pool):",
        """row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

    # Method 2: Explicit acquire for multiple queries
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, from_id)
            await conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, to_id)
```

```python
# SQLAlchemy 2.0 -- async pooling
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
    poolclass=AsyncAdaptedQueuePool,"""
    ),
    (
        "max",
        "} utilization = stats['used'] / max(stats['size'], 1) if utilization > 0.9: logger.warning( f'Pool near exhaustion: {stats['used']}/{stats['size']} f'({utilization:.0%} utilized) ) if stats['free'] == 0 and stats['size'] >= stats['max']: logger.error( Pool EXHAUSTED -- requests will queue/timeout. f'Max: {stats['max']}, all in use. )",
        """metrics.gauge("db.pool.size", stats["size"])
            metrics.gauge("db.pool.used", stats["used"])
            metrics.gauge("db.pool.free", stats["free"])
            metrics.gauge("db.pool.utilization", utilization)

            await asyncio.sleep(self.check_interval)
```

**Connection pooling rules**: (1) Always use a connection pooler -- never let applications open connections directly, (2) Pool size = `cpu_cores * 2 + 1` for the database, not per-application, (3) Use PgBouncer in transaction mode between applications and PostgreSQL, (4) Monitor `cl_waiting` (PgBouncer) or pool utilization -- if connections wait, your pool is too small OR queries are too slow, (5) Set timeouts at every layer: query timeout, connection timeout, pool acquire timeout."""
    ),
]
