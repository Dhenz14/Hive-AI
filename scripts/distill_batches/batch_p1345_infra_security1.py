"""Infrastructure & security training pairs: database, DevOps, and security patterns."""
PAIRS = [
    # ===================== DATABASE (8 pairs) =====================

    (
        "infra_sec1_01",
        r'''How do I prevent SQL injection in Python? I'm currently using f-strings to build my queries.''',
        r'''<think>
The user is building SQL queries with f-strings, which is a classic SQL injection vulnerability. I need to explain WHY f-strings are dangerous (string interpolation allows arbitrary SQL), show the vulnerable pattern, then demonstrate parameterized queries with both sqlite3 and psycopg2. I should also mention ORMs as a higher-level defense.
</think>

## SQL Injection Prevention with Parameterized Queries

Using f-strings (or any string concatenation) to build SQL queries is **one of the most dangerous security anti-patterns** in software development. The reason is that user-supplied input gets interpolated directly into the SQL statement, allowing an attacker to inject arbitrary SQL commands.

### The Vulnerable Pattern

```python
# NEVER DO THIS — vulnerable to SQL injection
def get_user(username: str):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
```

An attacker can pass `' OR '1'='1' --` as the username, which transforms your query into:

```sql
SELECT * FROM users WHERE username = '' OR '1'='1' --'
```

This returns **every row** in the table because `'1'='1'` is always true.

### The Fix: Parameterized Queries

The **best practice** is to use parameterized queries (also called prepared statements). The database driver handles escaping and quoting, so user input is **never** treated as SQL syntax.

**sqlite3:**

```python
import sqlite3

def get_user(db_path: str, username: str) -> dict | None:
    """Fetch a user safely using parameterized queries."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # The ? placeholder tells sqlite3 to bind the parameter safely
    cursor.execute(
        "SELECT id, username, email FROM users WHERE username = ?",
        (username,)  # tuple of parameters — NEVER f-string
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
```

**psycopg2 (PostgreSQL):**

```python
import psycopg2
from psycopg2.extras import RealDictCursor

def search_products(conn, name_pattern: str, min_price: float):
    """Search products with multiple parameterized conditions."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # %s placeholders are replaced safely by psycopg2
        cur.execute(
            """
            SELECT id, name, price, category
            FROM products
            WHERE name ILIKE %s AND price >= %s
            ORDER BY price ASC
            """,
            (f"%{name_pattern}%", min_price)
        )
        return cur.fetchall()
```

### Why This Works

Parameterized queries separate **code** (the SQL template) from **data** (the parameters). The database engine compiles the SQL structure first, then binds the parameters as literal values. Because the query structure is already finalized before parameters are inserted, there is **no way** for injected SQL to alter the query's logic — the input `' OR '1'='1'` would simply be treated as a literal string to match against.

### ORM Layer (Additional Defense)

ORMs like SQLAlchemy provide an even higher-level abstraction that generates parameterized queries automatically:

```python
from sqlalchemy import select
from models import User

stmt = select(User).where(User.username == username)
result = session.execute(stmt).scalars().first()
```

**Important**: Even with ORMs, avoid `text()` with string interpolation. Always use bound parameters.

### Defense in Depth

- **Parameterized queries**: Primary defense (mandatory)
- **Input validation**: Reject unexpected characters before they reach the query
- **Least privilege**: Database user should only have permissions it needs
- **WAF rules**: Web application firewalls can catch common injection patterns

The trade-off is minimal — parameterized queries add no meaningful performance cost and are actually **faster** for repeated queries because the database can cache the execution plan.'''
    ),

    (
        "infra_sec1_02",
        r'''I have a slow PostgreSQL query on a table with 10 million rows. How should I approach indexing and use EXPLAIN to diagnose it?''',
        r'''<think>
The user needs help with PostgreSQL query performance. I should cover: how to use EXPLAIN ANALYZE to diagnose slow queries, how to read the output (seq scan vs index scan, cost estimates, actual times), common indexing strategies (B-tree, partial indexes, composite indexes), and the trade-offs of over-indexing. Real examples will be important.
</think>

## PostgreSQL Indexing Strategy and EXPLAIN Plans

When a query is slow on a large table, the **first step** is always diagnosis with `EXPLAIN ANALYZE` — never guess which index to create. The reason is that the PostgreSQL query planner may not be doing what you think, and adding the wrong index wastes disk space and slows down writes.

### Step 1: Diagnose with EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT o.id, o.total, c.name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'pending'
  AND o.created_at > NOW() - INTERVAL '30 days'
ORDER BY o.created_at DESC
LIMIT 50;
```

**Important**: `EXPLAIN` alone shows the *plan*; adding `ANALYZE` actually *runs* the query and shows real execution times. `BUFFERS` reveals cache hit/miss ratios.

### Step 2: Read the Output

```
Limit  (cost=45032.14..45032.27 rows=50 width=72) (actual time=1842.331..1842.345 rows=50 loops=1)
  ->  Sort  (cost=45032.14..45187.21 rows=62028 width=72) (actual time=1842.329..1842.338 rows=50 loops=1)
        Sort Key: o.created_at DESC
        ->  Hash Join  (cost=1245.00..43521.85 rows=62028 width=72) (actual time=12.105..1798.442 rows=58234 loops=1)
              ->  Seq Scan on orders o  (cost=0.00..41023.00 rows=62028 width=48) (actual time=0.021..1752.108 rows=58234 loops=1)
                    Filter: (status = 'pending' AND created_at > ...)
                    Rows Removed by Filter: 9941766
Planning Time: 0.285 ms
Execution Time: 1842.502 ms
```

**Red flags here:**
- **Seq Scan on orders**: Scanning all 10M rows — the biggest bottleneck
- **Rows Removed by Filter: 9,941,766**: Filtering out 99.4% of rows means an index would eliminate nearly all I/O
- **actual time=1752ms** on the seq scan: Most of the total 1842ms is spent here

### Step 3: Create the Right Index

Because the query filters on `status` and `created_at`, and only `status = 'pending'` matches a small percentage, a **partial composite index** is ideal:

```sql
-- Composite index covering both filter columns
-- Partial index: only index 'pending' rows (saves disk space)
CREATE INDEX CONCURRENTLY idx_orders_pending_created
ON orders (created_at DESC)
WHERE status = 'pending';
```

**Best practice**: Use `CONCURRENTLY` to avoid locking the table during index creation on production databases.

After creating the index, re-run `EXPLAIN ANALYZE`:

```
Limit  (cost=0.56..52.30 rows=50 width=72) (actual time=0.042..0.398 rows=50 loops=1)
  ->  Index Scan using idx_orders_pending_created on orders o  (cost=0.56..64218.30 rows=62028 width=72) (actual time=0.040..0.385 rows=50 loops=1)
Execution Time: 0.451 ms
```

That is a **4000x improvement** — from 1842ms to 0.45ms — because the index eliminates the sequential scan entirely.

### Index Strategy Guidelines

| Scenario | Index Type | Why |
|----------|-----------|-----|
| Equality + range filter | Composite (eq cols first, range col last) | B-tree traverses equality, then scans range |
| Low-cardinality filter | Partial index | Only index matching rows, saves space |
| Text search (prefix) | `text_pattern_ops` | Enables `LIKE 'prefix%'` to use index |
| JSON field queries | GIN index | Handles `@>`, `?`, `?&` operators |
| Covering queries | `INCLUDE` columns | Avoids heap lookups (index-only scan) |

### Trade-offs of Over-Indexing

Every index you add **slows down INSERT, UPDATE, and DELETE** operations because PostgreSQL must update every relevant index. On a write-heavy table with 10M rows, each unnecessary index can add 5-15% write overhead. The best practice is to index based on actual query patterns shown in `pg_stat_user_indexes` and remove unused indexes periodically.'''
    ),

    (
        "infra_sec1_03",
        r'''What's the best way to implement database connection pooling in a Python web application?''',
        r'''<think>
Connection pooling is important because creating a new database connection per request is expensive (TCP handshake, auth, SSL negotiation). I should cover why pooling matters, show patterns with SQLAlchemy (most common), mention pgBouncer as an external pooler, and discuss pool sizing best practices (the formula from PostgreSQL wiki).
</think>

## Database Connection Pooling Patterns in Python

Connection pooling is a **critical performance pattern** for web applications. The reason is that establishing a new database connection involves a TCP handshake, authentication, SSL negotiation, and memory allocation on the database server — typically 20-50ms per connection. Without pooling, a web app handling 100 requests/second would create and destroy 100 connections/second, overwhelming the database.

### Why Pooling Matters

A connection pool maintains a set of **pre-established, reusable connections**. When your application needs a connection, it borrows one from the pool; when it is done, it returns it. This eliminates the per-request connection overhead and bounds the total number of connections to the database.

### SQLAlchemy Connection Pool (Application-Level)

SQLAlchemy is the most common Python approach. It includes a built-in connection pool with the `create_engine` function:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Engine with connection pool configuration
engine = create_engine(
    "postgresql+psycopg2://user:pass@localhost:5432/mydb",
    pool_size=10,          # Steady-state pool size
    max_overflow=5,        # Extra connections allowed under load
    pool_timeout=30,       # Seconds to wait for available connection
    pool_recycle=1800,     # Recycle connections after 30 min (prevents stale)
    pool_pre_ping=True,    # Test connection health before using it
)

SessionLocal = sessionmaker(bind=engine)

# FastAPI dependency pattern
def get_db():
    """Yield a database session, ensuring cleanup on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # Returns connection to pool (does NOT close it)
```

**Important**: `db.close()` does not destroy the connection — it returns it to the pool. The connection remains open for the next request.

### Pool Sizing Best Practice

A common mistake is setting the pool too large. The **optimal pool size** follows this formula from the PostgreSQL wiki:

```
pool_size = (2 * num_cpu_cores) + num_disks
```

For a typical server with 4 cores and 1 SSD, that is **9 connections**. The reason is that beyond this point, connections compete for CPU time and disk I/O, causing context-switching overhead that actually **reduces** throughput.

```python
import os

def calculate_pool_size() -> int:
    """Calculate optimal pool size based on available CPU cores."""
    cpu_count = os.cpu_count() or 4
    # Formula: 2 * cores + effective_spindles (1 for SSD)
    optimal = (2 * cpu_count) + 1
    return min(optimal, 20)  # Cap at 20 to be a good neighbor
```

### External Pooling with PgBouncer

For larger deployments, **PgBouncer** sits between your app and PostgreSQL as a lightweight proxy. This is the best practice when you have multiple application instances (e.g., Kubernetes pods), because each instance's pool multiplies the total connections:

```ini
# pgbouncer.ini
[databases]
mydb = host=db-primary port=5432 dbname=mydb

[pgbouncer]
listen_port = 6432
pool_mode = transaction    # Release connection after each transaction
default_pool_size = 20
max_client_conn = 200      # Accept many app connections
max_db_connections = 50    # But limit actual DB connections
```

**The trade-off** between pool modes:
- **`session`**: Connection held for entire client session (safest, least efficient)
- **`transaction`**: Connection released after each transaction (best balance)
- **`statement`**: Connection released after each statement (most efficient, but breaks multi-statement transactions)

### Async Connection Pooling

For async frameworks like FastAPI with asyncpg:

```python
import asyncpg

class Database:
    pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            dsn="postgresql://user:pass@localhost/mydb",
            min_size=5,       # Keep at least 5 connections warm
            max_size=20,
            max_inactive_connection_lifetime=300.0,
        )

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def fetch_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1", user_id
            )
```

### Monitoring Pool Health

Always monitor your pool to detect exhaustion before it causes outages:

```python
# SQLAlchemy pool diagnostics
pool = engine.pool
print(f"Pool size: {pool.size()}")
print(f"Checked out: {pool.checkedout()}")
print(f"Overflow: {pool.overflow()}")
print(f"Checked in: {pool.checkedin()}")
```

If `checkedout` consistently equals `pool_size + max_overflow`, you have pool exhaustion — usually caused by leaked connections (forgetting to close sessions) or long-running queries blocking the pool.'''
    ),

    (
        "infra_sec1_04",
        r'''What are best practices for database migrations in a team environment? We use PostgreSQL and keep breaking each other's migrations.''',
        r'''<think>
Database migration issues in teams usually come from: conflicting migration order, non-reversible migrations, destructive operations without safety nets, and lack of CI validation. I should cover Alembic (the Python standard) with concrete patterns for safe migrations, naming conventions, CI checks, and the critical "never modify a deployed migration" rule.
</think>

## Database Migration Best Practices for Teams

Migration conflicts are one of the most common pain points in team development. The reason they happen is that migration tools (Alembic, Django migrations, Flyway) use **linear version chains** — when two developers create migrations from the same parent, you get a fork that must be resolved.

### Core Principles

1. **Never modify a migration that has been deployed** — create a new one instead
2. **Every migration must be reversible** (include `downgrade()`)
3. **Separate schema changes from data migrations**
4. **Run migrations in CI before merge**

### Alembic Setup with Best Practices

```python
# alembic/env.py — configure for team safety
from alembic import context
from sqlalchemy import engine_from_config

def run_migrations_online():
    connectable = engine_from_config(config.get_section("alembic"))
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Important: detect column type changes
            compare_type=True,
            # Important: detect renamed columns vs drop+add
            compare_server_default=True,
            # Lock timeout prevents blocking production
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()
```

### Safe Migration Patterns

**Adding a column (safe):**

```python
"""add user email_verified column

Revision ID: a1b2c3d4e5f6
Revises: previous_rev_id
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Best practice: add nullable column first, backfill, then set NOT NULL
    op.add_column("users", sa.Column(
        "email_verified", sa.Boolean(), nullable=True, server_default="false"
    ))

def downgrade():
    op.drop_column("users", "email_verified")
```

**Renaming a column (dangerous — do it in phases):**

```python
# Phase 1: Add new column, copy data (deploy this first)
def upgrade():
    op.add_column("users", sa.Column("full_name", sa.String(255)))
    op.execute("UPDATE users SET full_name = name")

def downgrade():
    op.drop_column("users", "full_name")

# Phase 2: (separate migration, deployed AFTER app code updated)
def upgrade():
    op.drop_column("users", "name")

def downgrade():
    op.add_column("users", sa.Column("name", sa.String(255)))
    op.execute("UPDATE users SET name = full_name")
```

**The reason** for two phases is that during deployment, old app instances still reference the old column name. If you drop it immediately, those instances crash.

### Preventing Team Conflicts

**Naming convention with timestamps:**

```bash
# Use a timestamp prefix so migrations sort chronologically
alembic revision --autogenerate -m "add_orders_table" \
    --rev-id "$(date +%Y%m%d_%H%M%S)"
```

**CI migration check (GitHub Actions):**

```yaml
# .github/workflows/migrations.yml
name: Migration Safety Check
on: [pull_request]

jobs:
  check-migrations:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - name: Check for migration conflicts
        run: |
          # Detect multiple heads (branching)
          heads=$(alembic heads | wc -l)
          if [ "$heads" -gt 1 ]; then
            echo "ERROR: Multiple migration heads detected!"
            echo "Run: alembic merge heads -m 'merge migrations'"
            exit 1
          fi
      - name: Test upgrade + downgrade
        run: |
          alembic upgrade head
          alembic downgrade -1
          alembic upgrade head
```

### Handling the Merge Conflict

When two developers create migrations from the same parent:

```bash
# Developer sees: "Multiple heads detected"
alembic heads          # Shows two head revisions
alembic merge heads -m "merge_user_and_order_migrations"
alembic upgrade head   # Verify the merged chain works
```

### Safety Checklist for Every Migration

- **Does it have a `downgrade()`?** If not, add one or explicitly mark it as irreversible
- **Does it lock a large table?** Use `CONCURRENTLY` for index creation, add columns as `nullable` first
- **Does it drop anything?** Ensure the app code no longer references it
- **Has it been tested against a production-sized dataset?** A migration that takes 2ms on dev can take 20 minutes on 50M rows

**Important**: Never use `op.execute("DROP TABLE ...")` in a migration without a corresponding `CREATE TABLE` in the downgrade. Lost data is unrecoverable.'''
    ),

    (
        "infra_sec1_05",
        r'''Show me how to use PostgreSQL window functions. I need to rank items, compute running totals, and compare rows with previous values.''',
        r'''<think>
Window functions are one of PostgreSQL's most powerful features but often misunderstood. I should cover the key functions (ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD, SUM OVER), explain the OVER clause with PARTITION BY and ORDER BY, and show practical examples with clear explanations of what each does. The important concept is that window functions operate on a "window" of rows related to the current row without collapsing them like GROUP BY.
</think>

## PostgreSQL Window Functions

Window functions are one of PostgreSQL's most powerful features. The reason they exist is that `GROUP BY` collapses rows into groups, losing individual row detail. Window functions let you **compute aggregates across related rows while keeping every row in the result** — essential for rankings, running totals, and row-to-row comparisons.

### The Core Concept

Every window function uses the `OVER()` clause to define its "window" of rows:

```sql
function_name() OVER (
    PARTITION BY column    -- Groups rows (like GROUP BY, but keeps all rows)
    ORDER BY column        -- Ordering within each partition
    ROWS BETWEEN ...       -- Optional frame specification
)
```

### 1. Ranking Functions

```sql
-- Sample data: employee salaries by department
SELECT
    department,
    name,
    salary,
    -- ROW_NUMBER: unique sequential number (no ties)
    ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) AS row_num,
    -- RANK: same rank for ties, gaps after ties (1,1,3)
    RANK() OVER (PARTITION BY department ORDER BY salary DESC) AS rank,
    -- DENSE_RANK: same rank for ties, no gaps (1,1,2)
    DENSE_RANK() OVER (PARTITION BY department ORDER BY salary DESC) AS dense_rank
FROM employees;
```

| department | name    | salary | row_num | rank | dense_rank |
|-----------|---------|--------|---------|------|------------|
| Engineering | Alice | 150000 | 1 | 1 | 1 |
| Engineering | Bob   | 150000 | 2 | 1 | 1 |
| Engineering | Carol | 130000 | 3 | 3 | 2 |
| Sales       | Dave  | 120000 | 1 | 1 | 1 |

**Best practice**: Use `ROW_NUMBER()` when you need exactly N results per group (e.g., "top 3 per department"). Use `DENSE_RANK()` when ties should share a rank without creating gaps.

### 2. Running Totals and Moving Averages

```sql
SELECT
    order_date,
    amount,
    -- Running total: sum of all rows up to current row
    SUM(amount) OVER (
        ORDER BY order_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total,

    -- 7-day moving average
    AVG(amount) OVER (
        ORDER BY order_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7d,

    -- Percentage of total
    ROUND(
        100.0 * amount / SUM(amount) OVER (),  -- empty OVER() = entire result set
        2
    ) AS pct_of_total
FROM daily_sales
ORDER BY order_date;
```

**The reason** `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` works for running totals is that it tells PostgreSQL to include every row from the start of the partition up to the current row in the aggregate calculation.

### 3. Comparing with Previous/Next Rows (LAG/LEAD)

```sql
SELECT
    month,
    revenue,
    -- Previous month's revenue
    LAG(revenue, 1) OVER (ORDER BY month) AS prev_month,
    -- Month-over-month change
    revenue - LAG(revenue, 1) OVER (ORDER BY month) AS mom_change,
    -- Percentage change
    ROUND(
        100.0 * (revenue - LAG(revenue, 1) OVER (ORDER BY month))
        / NULLIF(LAG(revenue, 1) OVER (ORDER BY month), 0),
        1
    ) AS mom_pct_change,
    -- Next month (for forecasting comparisons)
    LEAD(revenue, 1) OVER (ORDER BY month) AS next_month
FROM monthly_revenue;
```

| month   | revenue | prev_month | mom_change | mom_pct_change | next_month |
|---------|---------|-----------|------------|----------------|------------|
| 2025-01 | 50000   | NULL      | NULL       | NULL           | 62000      |
| 2025-02 | 62000   | 50000     | 12000      | 24.0           | 58000      |
| 2025-03 | 58000   | 62000     | -4000      | -6.5           | NULL       |

### 4. Practical Example: Top N per Group

A common pattern — get the top 3 products by revenue in each category:

```sql
WITH ranked AS (
    SELECT
        category,
        product_name,
        SUM(quantity * price) AS total_revenue,
        ROW_NUMBER() OVER (
            PARTITION BY category
            ORDER BY SUM(quantity * price) DESC
        ) AS rn
    FROM order_items
    JOIN products USING (product_id)
    GROUP BY category, product_name
)
SELECT category, product_name, total_revenue
FROM ranked
WHERE rn <= 3
ORDER BY category, total_revenue DESC;
```

**Important**: You cannot use window functions in `WHERE` clauses directly — that is why the CTE pattern is necessary. The window function runs **after** `WHERE` and `GROUP BY`, so you must wrap it in a subquery or CTE to filter on its result.

### Performance Considerations

Window functions are efficient because PostgreSQL can often compute them in a single pass. However, be mindful that `PARTITION BY` benefits from an index on the partition column, and large windows (like `ROWS BETWEEN UNBOUNDED PRECEDING`) require memory proportional to the partition size.'''
    ),

    (
        "infra_sec1_06",
        r'''How should I implement Redis caching in a Python web application? What patterns should I use and what are the pitfalls?''',
        r'''<think>
Redis caching is essential for performance but has common pitfalls: cache invalidation, thundering herd, stale data, memory limits. I should cover cache-aside (most common), write-through, TTL strategies, the thundering herd problem and how to solve it, and serialization patterns. Practical code with redis-py.
</think>

## Redis Caching Patterns in Python

Redis is the **best practice** choice for application caching because it is an in-memory data store with sub-millisecond latency, rich data structures, and built-in expiration. However, caching introduces complexity around **consistency** and **invalidation** — getting these wrong can be worse than not caching at all.

### Cache-Aside Pattern (Most Common)

The application checks the cache first; on a miss, it queries the database and populates the cache:

```python
import redis
import json
from typing import Any
from functools import wraps

r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

def cached(prefix: str, ttl: int = 300):
    """Decorator implementing cache-aside pattern with JSON serialization."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build a deterministic cache key from function args
            key_parts = [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
            cache_key = f"{prefix}:{':'.join(key_parts)}"

            # Check cache first
            cached_value = r.get(cache_key)
            if cached_value is not None:
                return json.loads(cached_value)

            # Cache miss — call the actual function
            result = await func(*args, **kwargs)

            # Store in cache with TTL
            r.setex(cache_key, ttl, json.dumps(result, default=str))
            return result
        return wrapper
    return decorator

@cached(prefix="user", ttl=600)
async def get_user_profile(user_id: int) -> dict:
    """Fetch user profile from database (expensive query)."""
    return await db.fetch_one(
        "SELECT id, name, email, bio FROM users WHERE id = $1", user_id
    )
```

### Cache Invalidation (The Hard Part)

The reason cache invalidation is called one of the "two hard problems in CS" is that you must ensure the cache never serves stale data after a write. The **best practice** is explicit invalidation on writes:

```python
async def update_user_profile(user_id: int, data: dict):
    """Update profile and invalidate the cache."""
    await db.execute(
        "UPDATE users SET name=$1, bio=$2 WHERE id=$3",
        data["name"], data["bio"], user_id
    )
    # Delete the cached version — next read will repopulate
    r.delete(f"user:{user_id}")

    # Also invalidate any list caches that include this user
    r.delete("user_list:all")
```

### Solving the Thundering Herd Problem

When a popular cache key expires, hundreds of requests simultaneously hit the database. The fix is a **lock-based cache rebuild**:

```python
import time

def get_with_lock(cache_key: str, ttl: int, fetch_func):
    """Cache-aside with lock to prevent thundering herd."""
    value = r.get(cache_key)
    if value is not None:
        return json.loads(value)

    # Try to acquire a rebuild lock (only one process rebuilds)
    lock_key = f"lock:{cache_key}"
    if r.set(lock_key, "1", nx=True, ex=10):  # 10s lock timeout
        try:
            result = fetch_func()
            r.setex(cache_key, ttl, json.dumps(result, default=str))
            return result
        finally:
            r.delete(lock_key)
    else:
        # Another process is rebuilding — wait briefly and retry
        time.sleep(0.1)
        value = r.get(cache_key)
        if value:
            return json.loads(value)
        # Fallback: hit the database directly
        return fetch_func()
```

### TTL Strategy

**Important**: Not all data needs the same TTL. Use a tiered approach:

```python
CACHE_TTLS = {
    "user_profile": 600,       # 10 min — changes infrequently
    "product_listing": 120,    # 2 min — moderate change rate
    "search_results": 30,      # 30 sec — changes often
    "rate_limit": 60,          # 1 min — must be accurate
    "session": 86400,          # 24 hours — long-lived
}
```

### Redis Memory Management

Redis runs in memory, so unbounded caching will eventually crash your server:

```python
# redis.conf — set a memory limit and eviction policy
# maxmemory 512mb
# maxmemory-policy allkeys-lru

# Monitor memory usage in your health check
def check_redis_health() -> dict:
    info = r.info("memory")
    return {
        "used_memory_mb": info["used_memory"] / 1024 / 1024,
        "max_memory_mb": info.get("maxmemory", 0) / 1024 / 1024,
        "evicted_keys": info.get("evicted_keys", 0),
    }
```

The trade-off between eviction policies: `allkeys-lru` is safest for caching (evicts least-recently-used keys), while `volatile-lru` only evicts keys with TTLs set — useful when some keys must persist.'''
    ),

    (
        "infra_sec1_07",
        r'''When should I use NoSQL vs SQL databases? I'm building a new project and trying to decide.''',
        r'''<think>
This is a common architectural decision. I need to present clear trade-offs rather than just advocacy for one side. Cover: data model fit (relational vs document vs key-value vs graph), consistency requirements (ACID vs eventual), scalability patterns (vertical vs horizontal), query patterns (joins vs denormalized reads), and concrete use cases where each excels. I should be opinionated about defaults — SQL is the right default for most applications.
</think>

## NoSQL vs SQL: Trade-offs and Decision Framework

The most **important** thing to understand is that **SQL (relational databases) should be your default choice** for most applications. The reason is that relational databases provide ACID transactions, flexible querying, strong consistency, and decades of battle-tested reliability. NoSQL databases solve *specific* problems that relational databases handle poorly — not general ones.

### Decision Framework

```
Start with SQL (PostgreSQL) UNLESS you have a specific reason not to.

Switch to NoSQL when:
├── Your data is naturally non-relational (documents, graphs, time-series)
├── You need horizontal scaling beyond what a single server handles
├── Your read/write patterns don't need transactions or joins
└── Your schema changes so frequently that migrations are a bottleneck
```

### When SQL Wins

```python
# SQL excels at: complex queries, joins, aggregations, transactions
# Example: E-commerce order system

-- Single query joining 4 tables with aggregation
SELECT
    c.name,
    COUNT(o.id) AS total_orders,
    SUM(oi.quantity * p.price) AS lifetime_value,
    MAX(o.created_at) AS last_order
FROM customers c
JOIN orders o ON o.customer_id = c.id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
WHERE o.created_at > NOW() - INTERVAL '1 year'
GROUP BY c.id, c.name
HAVING SUM(oi.quantity * p.price) > 1000
ORDER BY lifetime_value DESC;
```

**The reason** this is hard in NoSQL: document databases do not support joins. You would need to denormalize the data (store customer info inside every order) or perform multiple queries and join in application code.

### When NoSQL Wins

**MongoDB (Document Store)** — when your data is naturally hierarchical and schema varies:

```python
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client.content_platform

# Each article can have completely different structure
# No schema migration needed when adding fields
db.articles.insert_one({
    "title": "Understanding Redis",
    "author": {"name": "Alice", "bio": "Backend engineer"},
    "tags": ["databases", "caching", "python"],
    "sections": [
        {"heading": "Introduction", "body": "...", "code_samples": [...]},
        {"heading": "Advanced", "body": "...", "diagrams": [...]},
    ],
    "metadata": {
        "word_count": 2500,
        "reading_time_min": 12,
        "custom_fields": {"series": "Database Deep Dives", "part": 3}
    }
})

# Query nested documents naturally
articles = db.articles.find({
    "tags": "python",
    "metadata.word_count": {"$gt": 1000}
}).sort("metadata.reading_time_min", -1)
```

**Redis (Key-Value)** — when you need sub-millisecond access to simple data:

```python
# Session storage, caching, rate limiting, leaderboards
r.setex(f"session:{session_id}", 3600, json.dumps(session_data))
r.zincrby("leaderboard:daily", 10, f"user:{user_id}")
```

### Comparison Table

| Factor | SQL (PostgreSQL) | Document (MongoDB) | Key-Value (Redis) |
|--------|-----------------|-------------------|-------------------|
| **Data model** | Structured, relational | Flexible documents | Simple key-value |
| **Consistency** | Strong (ACID) | Tunable (eventual by default) | Strong (single key) |
| **Joins** | Native, efficient | Manual (application-side) | None |
| **Scaling** | Vertical (read replicas) | Horizontal (sharding) | Horizontal (cluster) |
| **Schema** | Rigid (migrations) | Flexible (schemaless) | None |
| **Query power** | Very high (SQL) | Moderate (MQL) | Minimal (key lookup) |
| **Best for** | Most applications | Content, catalogs, CMS | Caching, sessions |

### Common Mistakes

1. **Choosing MongoDB because "it's easier"** — it is easier to start but harder to maintain. Lack of schema enforcement means your application code must validate everything
2. **Choosing SQL for time-series data** — PostgreSQL can do it with TimescaleDB, but dedicated time-series databases (InfluxDB, QuestDB) are 10-100x faster for this workload
3. **Using Redis as a primary database** — Redis is an in-memory store. Data loss on crash is a real risk unless you configure AOF persistence, and even then it is not designed for primary storage

### The Best Practice: Polyglot Persistence

Most production systems use **multiple databases**, each for what it does best:

```
PostgreSQL  → User accounts, orders, transactions (source of truth)
Redis       → Sessions, caching, rate limiting (ephemeral data)
Elasticsearch → Full-text search, log aggregation (search-optimized)
```

The trade-off is operational complexity — each database is another system to monitor, back up, and maintain. Start with just PostgreSQL and add specialized stores only when you have a measured performance problem.'''
    ),

    (
        "infra_sec1_08",
        r'''Explain database transaction isolation levels with practical examples. When would I choose each one?''',
        r'''<think>
Transaction isolation levels are a core database concept that many developers misunderstand. I need to explain the four SQL standard levels (READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ, SERIALIZABLE), what anomalies each prevents, and practical examples of when to use each. PostgreSQL defaults to READ COMMITTED and doesn't implement READ UNCOMMITTED, which is worth noting.
</think>

## Transaction Isolation Levels Explained

Transaction isolation levels control **how much one transaction can see of another transaction's uncommitted or recently committed changes**. The reason this matters is that without proper isolation, concurrent transactions can produce incorrect results — duplicate charges, lost updates, or phantom data.

### The Four Anomalies

| Anomaly | Description | Example |
|---------|-------------|---------|
| **Dirty Read** | Reading uncommitted data from another transaction | Seeing a price change that gets rolled back |
| **Non-Repeatable Read** | Same query returns different values within one transaction | Balance check shows $100, then $50 a moment later |
| **Phantom Read** | New rows appear between two identical queries | Count shows 10 orders, then 11 on re-query |
| **Serialization Anomaly** | Result differs from any serial execution order | Two transfers both read old balance, both succeed |

### The Four Isolation Levels

```
                    Dirty Read  Non-Repeatable  Phantom  Serialization
READ UNCOMMITTED      Possible     Possible     Possible   Possible
READ COMMITTED        Prevented    Possible     Possible   Possible
REPEATABLE READ       Prevented    Prevented    Possible*  Possible
SERIALIZABLE          Prevented    Prevented    Prevented  Prevented

* PostgreSQL's REPEATABLE READ also prevents phantom reads (stronger than SQL standard)
```

### READ COMMITTED (PostgreSQL Default)

Each statement sees only data committed **before that statement began**. This is the best practice for most applications because it balances consistency and performance:

```python
import psycopg2

conn = psycopg2.connect(dsn)
conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)

with conn.cursor() as cur:
    # Statement 1: sees balance = 1000
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    balance = cur.fetchone()[0]

    # Meanwhile, another transaction commits: balance = 800
    # Statement 2: sees balance = 800 (the NEW committed value)
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    balance2 = cur.fetchone()[0]
    # balance != balance2 — this is a non-repeatable read
```

**Use when**: General CRUD operations, web request handlers, most business logic.

### REPEATABLE READ

The transaction sees a **snapshot** of the database as of the transaction's start. All reads within the transaction see the same data, even if other transactions commit changes:

```python
conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)

with conn.cursor() as cur:
    cur.execute("BEGIN")

    # Snapshot taken at first query
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    balance = cur.fetchone()[0]  # 1000

    # Even if another transaction commits balance = 800...
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    balance2 = cur.fetchone()[0]  # Still 1000 (snapshot)

    # But if we try to UPDATE based on stale data:
    try:
        cur.execute(
            "UPDATE accounts SET balance = balance - 200 WHERE id = 1"
        )
        conn.commit()
    except psycopg2.errors.SerializationFailure:
        # PostgreSQL detects the conflict and raises an error
        # The reason: another transaction modified this row after our snapshot
        conn.rollback()
        # IMPORTANT: retry the entire transaction, not just the statement
```

**Use when**: Financial reports, inventory checks, any multi-statement read that must see consistent data. The trade-off is that write conflicts require retry logic.

### SERIALIZABLE

The strongest level — PostgreSQL guarantees results are equivalent to running transactions **one at a time**. This prevents all anomalies but requires robust retry logic:

```python
import psycopg2
from tenacity import retry, retry_if_exception_type, stop_after_attempt

@retry(
    retry=retry_if_exception_type(psycopg2.errors.SerializationFailure),
    stop=stop_after_attempt(3),
)
def transfer_funds(from_id: int, to_id: int, amount: float):
    """Transfer funds with serializable isolation to prevent double-spending."""
    conn = psycopg2.connect(dsn)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)

    try:
        with conn.cursor() as cur:
            # Both reads and writes are fully serialized
            cur.execute("SELECT balance FROM accounts WHERE id = %s", (from_id,))
            balance = cur.fetchone()[0]

            if balance < amount:
                raise ValueError("Insufficient funds")

            cur.execute(
                "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                (amount, from_id)
            )
            cur.execute(
                "UPDATE accounts SET balance = balance + %s WHERE id = %s",
                (amount, to_id)
            )
            conn.commit()
    except psycopg2.errors.SerializationFailure:
        conn.rollback()
        raise  # Let tenacity retry
    finally:
        conn.close()
```

**Use when**: Financial transactions, booking systems, inventory management — anywhere **correctness is more important than throughput**. The trade-off is higher abort rates under contention (up to 5-10% of transactions may need retries).

### Practical Decision Guide

```python
# Choose isolation level based on your use case:
ISOLATION_GUIDE = {
    "web_api_crud":       "READ COMMITTED",    # Default, fast, sufficient
    "reporting_queries":  "REPEATABLE READ",    # Consistent snapshot for reports
    "financial_transfer": "SERIALIZABLE",       # Correctness critical
    "analytics_etl":      "READ COMMITTED",     # Stale data acceptable
    "inventory_reserve":  "SERIALIZABLE",       # Prevent overselling
    "user_registration":  "READ COMMITTED",     # With UNIQUE constraint
}
```

**Important**: Higher isolation levels do not make your application "safer" by default — they increase the chance of serialization failures that your application must handle with retry logic. If you do not implement retries, SERIALIZABLE is actually **less** reliable than READ COMMITTED because transactions will fail instead of proceeding.'''
    ),

    # ===================== DEVOPS (8 pairs) =====================

    (
        "infra_sec1_09",
        r'''What are best practices for writing Dockerfiles? My images are huge (2GB+) and builds are slow.''',
        r'''<think>
Large Docker images and slow builds are usually caused by: not using multi-stage builds, not leveraging layer caching, installing dev dependencies in production, using a fat base image, not using .dockerignore. I need to show a before/after Dockerfile transformation with concrete size reductions and explain WHY each optimization works.
</think>

## Dockerfile Best Practices: Multi-Stage Builds and Layer Caching

A 2GB+ image means you are likely shipping build tools, dev dependencies, and source artifacts that the production application does not need. The **best practice** is multi-stage builds combined with proper layer ordering. This can typically reduce image size by **80-95%**.

### Before: The Bloated Dockerfile

```dockerfile
# BAD — everything in one stage, no layer optimization
FROM python:3.12
WORKDIR /app
COPY . .
RUN pip install poetry
RUN poetry install
RUN apt-get update && apt-get install -y gcc libpq-dev
CMD ["python", "main.py"]
```

Problems:
- Full Python image (~1GB base)
- `COPY . .` before `pip install` — invalidates dependency cache on every code change
- Build tools (gcc, poetry) shipped to production
- No `.dockerignore` — copies `.git/`, `__pycache__/`, `node_modules/`

### After: Optimized Multi-Stage Build

```dockerfile
# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build-time system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy ONLY dependency files first (layer caching!)
COPY pyproject.toml poetry.lock ./

# Install dependencies into a virtual env (portable)
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.in-project true && \
    poetry install --only=main --no-interaction

# Stage 2: Production image
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install only runtime system libraries (no gcc!)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy the virtual env from builder (contains all dependencies)
COPY --from=builder /app/.venv /app/.venv

# Copy application code last (changes most frequently)
COPY src/ ./src/

# Use non-root user (security best practice)
RUN useradd --create-home appuser
USER appuser

# Set path to use the virtual env
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**The reason** this is dramatically smaller: the `builder` stage contains gcc, poetry, and pip caches (~800MB). The `runtime` stage only copies the `.venv` directory (~150MB) and application code. Final image: **~200MB** vs 2GB+.

### Layer Caching Order

The **most important optimization** is ordering your `COPY` statements from least-frequently-changed to most-frequently-changed:

```dockerfile
# These rarely change — cached most of the time
COPY pyproject.toml poetry.lock ./
RUN poetry install

# This changes on every commit — only this layer rebuilds
COPY src/ ./src/
```

Because Docker caches layers sequentially, changing `src/` only rebuilds the last `COPY` layer. If you `COPY . .` before `pip install`, every code change triggers a full dependency reinstall.

### Essential .dockerignore

```
# .dockerignore
.git
.gitignore
__pycache__
*.pyc
.env
.venv
node_modules
*.md
tests/
docs/
.coverage
.pytest_cache
docker-compose*.yml
```

### Additional Best Practices

**Pin base image digests for reproducibility:**

```dockerfile
# Instead of: FROM python:3.12-slim
FROM python:3.12-slim@sha256:abc123...  # Immutable reference
```

**Use HEALTHCHECK:**

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
```

**Combine RUN commands to reduce layers:**

```dockerfile
# BAD — 3 layers
RUN apt-get update
RUN apt-get install -y gcc
RUN rm -rf /var/lib/apt/lists/*

# GOOD — 1 layer, smaller image
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*
```

### Size Comparison

| Approach | Image Size |
|----------|-----------|
| `python:3.12` (no optimization) | ~1.0 GB |
| `python:3.12-slim` (single stage) | ~350 MB |
| Multi-stage with slim | ~200 MB |
| Multi-stage with `alpine` | ~80 MB |

The trade-off with Alpine is that it uses `musl` instead of `glibc`, which can cause subtle compatibility issues with some Python packages (especially those with C extensions). `slim` is the safest default.'''
    ),

    (
        "infra_sec1_10",
        r'''How do I set up a CI/CD pipeline with GitHub Actions for a Python project? I need linting, testing, and deployment.''',
        r'''<think>
CI/CD with GitHub Actions for Python. I should cover a complete workflow: linting (ruff/black), type checking (mypy), testing (pytest with coverage), and deployment (to a server or container registry). Include matrix testing across Python versions, caching for speed, and secrets management. Show a real, production-ready workflow file.
</think>

## CI/CD Pipeline Design with GitHub Actions

A well-designed CI/CD pipeline catches bugs **before** they reach production and automates deployment so humans cannot make manual deployment errors. The **best practice** is a multi-stage pipeline: lint → test → build → deploy, where each stage gates the next.

### Complete Production Workflow

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

# Important: cancel in-progress runs when a new commit is pushed
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  PYTHON_VERSION: "3.12"
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # Stage 1: Code Quality (fast — runs in ~30 seconds)
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install linting tools
        run: pip install ruff mypy

      - name: Lint with Ruff
        run: ruff check . --output-format=github

      - name: Format check
        run: ruff format --check .

      - name: Type check
        run: mypy src/ --ignore-missing-imports

  # Stage 2: Tests (matrix across Python versions)
  test:
    runs-on: ubuntu-latest
    needs: lint  # Only run if linting passes
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    services:
      # Spin up a real PostgreSQL for integration tests
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: testdb
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpass
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      # Cache pip dependencies — saves ~30s per run
      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ matrix.python-version }}-${{ hashFiles('**/requirements*.txt') }}
          restore-keys: pip-${{ matrix.python-version }}-

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt -r requirements-dev.txt

      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
        run: |
          pytest tests/ \
            --cov=src \
            --cov-report=xml \
            --cov-report=term-missing \
            --junitxml=test-results.xml \
            -v

      - name: Upload coverage
        if: matrix.python-version == '3.12'
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          token: ${{ secrets.CODECOV_TOKEN }}

  # Stage 3: Build container image
  build:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'  # Only build on main
    permissions:
      contents: read
      packages: write

    outputs:
      image-tag: ${{ steps.meta.outputs.tags }}

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # Stage 4: Deploy to production
  deploy:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main'
    environment: production  # Requires manual approval if configured

    steps:
      - name: Deploy to server
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            cd /opt/app
            docker compose pull
            docker compose up -d --remove-orphans
            docker image prune -f
```

### Key Design Decisions

**The reason** for `needs: lint` on the test job is to **fail fast** — linting takes 30 seconds while tests take 2-3 minutes. If there is a syntax error, you find out immediately instead of waiting for tests.

**The reason** for `concurrency.cancel-in-progress` is cost savings — if you push 3 commits rapidly, only the latest commit's pipeline runs. Without this, all 3 run in parallel, wasting CI minutes.

**Important**: The `environment: production` setting on the deploy job enables GitHub's built-in deployment protection rules, including required reviewers and wait timers. This is the best practice for production deployments.

### Secrets Management

Never hardcode secrets in workflow files. Store them in GitHub Settings → Secrets:

```yaml
# Reference secrets like this:
${{ secrets.DEPLOY_SSH_KEY }}    # Repository secret
${{ secrets.GITHUB_TOKEN }}      # Auto-generated, scoped to repo
${{ vars.DEPLOY_REGION }}        # Non-sensitive variables
```'''
    ),

    (
        "infra_sec1_11",
        r'''How do I set up Docker Compose for local development with a Python app, PostgreSQL, and Redis?''',
        r'''<think>
Docker Compose for local dev is about developer experience — fast startup, live reload, persistent data, and parity with production. I should cover a complete docker-compose.yml with a Python app, PostgreSQL, Redis, proper volumes for data persistence, health checks, and the key patterns: bind mounts for live code reload, named volumes for database persistence, depends_on with health checks.
</think>

## Docker Compose for Local Development

Docker Compose is the **best practice** for local development because it gives every developer an identical environment — no more "works on my machine" issues. The reason it excels for local dev specifically is **bind mounts** for live code reloading and **named volumes** for persistent database state across container restarts.

### Complete docker-compose.yml

```yaml
# docker-compose.yml
services:
  # Python application with live reload
  app:
    build:
      context: .
      dockerfile: Dockerfile.dev  # Separate dev Dockerfile (see below)
    ports:
      - "8000:8000"
    volumes:
      # Bind mount: code changes reflected immediately (no rebuild needed)
      - ./src:/app/src:cached
      - ./tests:/app/tests:cached
      # Important: do NOT mount .venv — use container's own venv
    environment:
      - DATABASE_URL=postgresql://devuser:devpass@postgres:5432/devdb
      - REDIS_URL=redis://redis:6379/0
      - DEBUG=true
      - LOG_LEVEL=debug
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    # Auto-restart on crash during development
    restart: unless-stopped

  # PostgreSQL with persistent data
  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"  # Expose for direct access with pgcli/DBeaver
    environment:
      POSTGRES_DB: devdb
      POSTGRES_USER: devuser
      POSTGRES_PASSWORD: devpass
    volumes:
      # Named volume: data survives container recreation
      - pgdata:/var/lib/postgresql/data
      # Init scripts run on first start only
      - ./scripts/init_db.sql:/docker-entrypoint-initdb.d/01_init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U devuser -d devdb"]
      interval: 5s
      timeout: 3s
      retries: 5

  # Redis for caching and sessions
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    command: redis-server --appendonly yes --maxmemory 256mb
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  # pgAdmin for database management (optional)
  pgadmin:
    image: dpage/pgadmin4:latest
    ports:
      - "5050:80"
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@dev.local
      PGADMIN_DEFAULT_PASSWORD: admin
    volumes:
      - pgadmindata:/var/lib/pgadmin
    profiles:
      - tools  # Only starts with: docker compose --profile tools up

# Named volumes persist data across container lifecycle
volumes:
  pgdata:
  redisdata:
  pgadmindata:
```

### Development Dockerfile

The **reason** for a separate `Dockerfile.dev` is that your production Dockerfile uses multi-stage builds optimized for size, while dev needs live reloading and dev dependencies:

```dockerfile
# Dockerfile.dev — optimized for development experience
FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install ALL dependencies (including dev/test)
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && \
    poetry config virtualenvs.in-project true && \
    poetry install --no-interaction

ENV PATH="/app/.venv/bin:$PATH"

# Source code is bind-mounted, so no COPY needed

# uvicorn with --reload watches for file changes
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### Common Developer Workflows

```bash
# Start everything
docker compose up -d

# View logs (follow mode)
docker compose logs -f app

# Run tests inside the container
docker compose exec app pytest tests/ -v

# Run a one-off command (e.g., database migration)
docker compose exec app alembic upgrade head

# Reset the database (delete volume and recreate)
docker compose down -v  # -v removes named volumes
docker compose up -d

# Start with optional tools (pgAdmin)
docker compose --profile tools up -d

# Rebuild after changing dependencies (pyproject.toml)
docker compose build app
docker compose up -d app
```

### Important Patterns

**Health checks with `depends_on`**: The `condition: service_healthy` setting ensures your app does not start until PostgreSQL and Redis are actually ready to accept connections. Without this, your app would crash on startup because the database is not yet accepting connections.

**Bind mount with `:cached`**: On macOS, Docker file system performance is slow. The `:cached` flag relaxes consistency guarantees for better performance. On Linux this flag is ignored (native performance).

**Named volumes vs bind mounts**: The trade-off is that bind mounts reflect host changes immediately (great for code), while named volumes are managed by Docker and survive `docker compose down` (great for data). Never use bind mounts for database data directories.

### Environment Variable Management

```bash
# .env file (gitignored!) for local overrides
DATABASE_URL=postgresql://devuser:devpass@localhost:5432/devdb
REDIS_URL=redis://localhost:6379/0
DEBUG=true
SECRET_KEY=dev-only-not-for-production
```

```yaml
# Reference in docker-compose.yml
services:
  app:
    env_file: .env  # Load all variables from .env
```'''
    ),

    (
        "infra_sec1_12",
        r'''Can you explain the basics of deploying an application to Kubernetes? I need a deployment, service, and ingress.''',
        r'''<think>
Kubernetes deployment basics. I need to cover the three essential resources: Deployment (runs pods with replicas), Service (internal networking/load balancing), and Ingress (external HTTP routing). I should explain what each resource does and WHY it exists, show complete YAML manifests, and cover best practices like resource limits, health checks, and rolling updates.
</think>

## Kubernetes Deployment Basics

Kubernetes has three essential resources for running a web application: **Deployment** (manages your application pods), **Service** (provides stable internal networking), and **Ingress** (routes external HTTP traffic). The reason for this separation is the **single responsibility principle** — each resource handles one concern, making them composable and independently configurable.

### 1. Deployment — Running Your Application

A Deployment declares the **desired state** of your application: which container image to run, how many replicas, and how to update them. Kubernetes continuously reconciles actual state with desired state.

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  labels:
    app: myapp
spec:
  replicas: 3  # Run 3 identical pods for high availability
  selector:
    matchLabels:
      app: myapp
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1   # At most 1 pod down during update
      maxSurge: 1          # At most 1 extra pod during update
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
        - name: myapp
          image: ghcr.io/myorg/myapp:abc123f
          ports:
            - containerPort: 8000

          # Resource limits prevent noisy-neighbor problems
          resources:
            requests:
              cpu: 100m       # 0.1 CPU cores guaranteed
              memory: 256Mi   # 256 MB guaranteed
            limits:
              cpu: 500m       # 0.5 CPU cores max
              memory: 512Mi   # 512 MB max (OOM-killed if exceeded)

          # Liveness: restart pod if app is stuck
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 15
            failureThreshold: 3

          # Readiness: remove from load balancer if not ready
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5

          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: myapp-secrets
                  key: database-url
            - name: LOG_LEVEL
              value: "info"
```

### 2. Service — Internal Networking

A Service provides a **stable DNS name and load balancing** across your pods. The reason you need this is that pods are ephemeral — they get new IP addresses when restarted. The Service abstraction gives other components a fixed endpoint.

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: myapp
spec:
  selector:
    app: myapp  # Routes traffic to pods with this label
  ports:
    - port: 80           # Service listens on port 80
      targetPort: 8000   # Forwards to container port 8000
      protocol: TCP
  type: ClusterIP  # Internal only (default)
```

**Important**: `ClusterIP` (the default) makes the service accessible only within the cluster at `myapp.default.svc.cluster.local`. Use `LoadBalancer` type if you need direct external access without an Ingress (e.g., for TCP services).

### 3. Ingress — External HTTP Routing

An Ingress routes external HTTP/HTTPS traffic to your Services based on hostnames and paths:

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  annotations:
    # These annotations depend on your ingress controller
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - myapp.example.com
      secretName: myapp-tls  # cert-manager auto-provisions this
  rules:
    - host: myapp.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp
                port:
                  number: 80
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: myapp-api  # Different service for API
                port:
                  number: 80
```

### How They Connect

```
Internet → Ingress (myapp.example.com)
              → Service (myapp:80)
                  → Pod 1 (10.1.0.5:8000)
                  → Pod 2 (10.1.0.6:8000)
                  → Pod 3 (10.1.0.7:8000)
```

### Deploying It All

```bash
# Apply all manifests
kubectl apply -f k8s/

# Check deployment status
kubectl rollout status deployment/myapp

# View running pods
kubectl get pods -l app=myapp

# View logs from all replicas
kubectl logs -l app=myapp --tail=50

# Update to new image (triggers rolling update)
kubectl set image deployment/myapp myapp=ghcr.io/myorg/myapp:new-sha
```

### Best Practices

- **Always set resource requests and limits** — without them, a single pod can consume all node resources
- **Always use health probes** — without liveness probes, a hung process stays "running" but serves errors
- **Never use `latest` tag** — the reason is that Kubernetes caches images, so `latest` may not pull the newest version. Use commit SHAs or semantic versions
- **Use namespaces** to isolate environments: `kubectl create namespace staging`

The trade-off with Kubernetes is operational complexity. For a single application, a simple VM with Docker Compose is often sufficient. Kubernetes pays off when you have **5+ services** that need independent scaling, automated rollbacks, and self-healing.'''
    ),

    (
        "infra_sec1_13",
        r'''How do I set up centralized logging and monitoring for a microservices application?''',
        r'''<think>
Log aggregation and monitoring for microservices. I should cover the standard stack: structured logging in the application, a log aggregation pipeline (ELK or Loki), metrics collection (Prometheus + Grafana), and alerting. The key insight is that distributed systems REQUIRE centralized observability because logs are spread across dozens of containers. I'll show practical Python logging config, Prometheus metrics, and the infrastructure setup.
</think>

## Log Aggregation and Monitoring for Microservices

In a microservices architecture, a single user request might traverse 5-10 services. The reason centralized observability is **critical** is that without it, debugging requires SSH-ing into individual containers and correlating timestamps manually — which is impossibly slow during an incident.

### The Three Pillars of Observability

1. **Logs**: Structured event records ("what happened")
2. **Metrics**: Numeric time-series data ("how much / how fast")
3. **Traces**: Request flow across services ("where did time go")

### Pillar 1: Structured Logging

**Best practice**: Log as JSON so log aggregation tools can parse and query fields automatically.

```python
# src/logging_config.py
import logging
import json
import sys
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    """Format log records as JSON for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "user-service",  # Identify the source service
            "module": record.module,
            "line": record.lineno,
        }
        # Include trace context for distributed tracing
        if hasattr(record, "trace_id"):
            log_entry["trace_id"] = record.trace_id
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def setup_logging(level: str = "INFO"):
    """Configure structured JSON logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
```

**FastAPI middleware for request correlation:**

```python
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Use incoming trace ID or generate one
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request_id_var.set(request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

### Pillar 2: Metrics with Prometheus

```python
# src/metrics.py
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response

# Define application metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

DB_QUERY_LATENCY = Histogram(
    "db_query_duration_seconds",
    "Database query latency",
    ["query_name"]
)

async def metrics_endpoint(request):
    """Expose Prometheus metrics at /metrics."""
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

**Instrument your endpoints:**

```python
import time

@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    endpoint = request.url.path
    REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
    REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)
    return response
```

### Infrastructure Stack (Docker Compose)

```yaml
# docker-compose.monitoring.yml
services:
  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    command: --config.file=/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
    volumes:
      - grafana-data:/var/lib/grafana
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin

  loki:
    image: grafana/loki:latest
    ports: ["3100:3100"]

  promtail:
    image: grafana/promtail:latest
    volumes:
      - /var/log:/var/log:ro
      - ./monitoring/promtail.yml:/etc/promtail/config.yml:ro

volumes:
  grafana-data:
```

**Prometheus config:**

```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "user-service"
    static_configs:
      - targets: ["user-service:8000"]
  - job_name: "order-service"
    static_configs:
      - targets: ["order-service:8001"]
```

### Key Metrics to Monitor

The **best practice** "golden signals" for every service:

- **Latency**: p50, p95, p99 response times (use histograms)
- **Traffic**: Requests per second by endpoint
- **Errors**: Error rate (5xx / total requests)
- **Saturation**: CPU, memory, connection pool usage

**Important**: Alert on **symptoms** (high error rate, slow responses), not causes (high CPU). The reason is that high CPU is only a problem if it impacts users — symptom-based alerts reduce noise.'''
    ),

    (
        "infra_sec1_14",
        r'''How do I get started with Terraform for infrastructure as code? Show me a practical example deploying to AWS.''',
        r'''<think>
Terraform basics for IaC. I should cover: why IaC matters, the core Terraform workflow (init/plan/apply), a practical example deploying an EC2 instance or ECS service with VPC, state management (remote backend), and best practices (modules, workspaces, tfvars). Keep it practical and beginner-friendly but complete.
</think>

## Infrastructure as Code with Terraform

Terraform lets you define your infrastructure in **declarative configuration files** that are version-controlled, reviewed, and reproducible. The reason IaC is a best practice is that manual infrastructure changes (clicking in the AWS console) are unreproducible, unauditable, and error-prone. With Terraform, your infrastructure has the same rigor as application code: pull requests, code review, and a clear history of what changed and why.

### Core Workflow

```
terraform init    → Downloads providers, initializes backend
terraform plan    → Shows what will change (dry run)
terraform apply   → Executes the changes
terraform destroy → Tears everything down
```

### Practical Example: Web Server on AWS

```hcl
# main.tf — Deploy a web application with VPC, security groups, and EC2

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Important: store state remotely so the team shares it
  backend "s3" {
    bucket         = "mycompany-terraform-state"
    key            = "prod/web-app/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"  # Prevents concurrent modifications
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

# --- Variables ---
variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

# --- Networking ---
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true

  tags = {
    Name        = "${var.environment}-vpc"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "${var.aws_region}a"

  tags = {
    Name = "${var.environment}-public-subnet"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# --- Security ---
resource "aws_security_group" "web" {
  name_prefix = "${var.environment}-web-"
  vpc_id      = aws_vpc.main.id

  # Allow HTTP from anywhere
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow HTTPS from anywhere
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow SSH from specific IP only (best practice)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["YOUR_IP/32"]  # Replace with your IP
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# --- Compute ---
resource "aws_instance" "web" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]

  user_data = <<-EOF
    #!/bin/bash
    apt-get update -y
    apt-get install -y docker.io
    systemctl enable docker
    docker run -d -p 80:8000 ghcr.io/myorg/myapp:latest
  EOF

  tags = {
    Name        = "${var.environment}-web-server"
    Environment = var.environment
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# --- Outputs ---
output "public_ip" {
  value       = aws_instance.web.public_ip
  description = "Public IP of the web server"
}
```

### Environment-Specific Variables

```hcl
# environments/prod.tfvars
environment   = "prod"
instance_type = "t3.medium"
aws_region    = "us-east-1"

# environments/dev.tfvars
environment   = "dev"
instance_type = "t3.micro"
aws_region    = "us-east-1"
```

```bash
# Deploy to specific environment
terraform plan -var-file="environments/prod.tfvars"
terraform apply -var-file="environments/prod.tfvars"
```

### Best Practices

1. **Remote state with locking**: The S3 + DynamoDB backend prevents two people from running `terraform apply` simultaneously, which would corrupt the state
2. **Tag everything**: Tags like `ManagedBy = "terraform"` make it obvious which resources are IaC-managed
3. **Use modules for reuse**: Extract common patterns (VPC, security groups) into modules
4. **Never modify state manually**: Use `terraform import` to bring existing resources under management
5. **Plan before apply**: Always review `terraform plan` output — the trade-off of a few extra seconds prevents accidental resource destruction

**Important**: Terraform state contains secrets (database passwords, API keys). The reason for `encrypt = true` on the S3 backend is that state files are stored in plaintext by default.'''
    ),

    (
        "infra_sec1_15",
        r'''Explain blue-green and canary deployment strategies. When should I use each one?''',
        r'''<think>
Blue-green and canary are the two most important deployment strategies beyond basic rolling updates. I should explain each clearly, their trade-offs, when to use which, and show implementation examples with both a load balancer approach and Kubernetes. The key distinction: blue-green is all-or-nothing switchover, canary is gradual traffic shifting.
</think>

## Blue-Green and Canary Deployment Strategies

Both strategies aim to **eliminate downtime and reduce the blast radius of bad deployments**. The reason they exist is that traditional deployments (stop old version, start new version) create a window where the application is unavailable, and if the new version has a bug, all users are affected immediately.

### Blue-Green Deployments

Blue-green maintains **two identical production environments**. Only one serves live traffic at any time. You deploy to the idle environment, verify it, then switch traffic.

```
Before deployment:
  [Load Balancer] → [Blue: v1.0 (LIVE)]
                     [Green: v1.0 (idle)]

During deployment:
  [Load Balancer] → [Blue: v1.0 (LIVE)]
                     [Green: v1.1 (deploying + testing)]

After cutover:
  [Load Balancer] → [Blue: v1.0 (idle — instant rollback)]
                     [Green: v1.1 (LIVE)]
```

**Nginx blue-green implementation:**

```nginx
# /etc/nginx/conf.d/app.conf
upstream blue {
    server 10.0.1.10:8000;
    server 10.0.1.11:8000;
}

upstream green {
    server 10.0.2.10:8000;
    server 10.0.2.11:8000;
}

# Switch by changing this single line
upstream active {
    server 10.0.2.10:8000;  # Points to green
    server 10.0.2.11:8000;
}

server {
    listen 80;
    location / {
        proxy_pass http://active;
    }
}
```

**Deployment script:**

```bash
#!/bin/bash
# deploy_blue_green.sh
set -euo pipefail

CURRENT=$(curl -s http://localhost/api/version | jq -r '.environment')
TARGET=$( [ "$CURRENT" = "blue" ] && echo "green" || echo "blue" )

echo "Current: $CURRENT, Deploying to: $TARGET"

# Step 1: Deploy new version to idle environment
ssh "$TARGET-server" "docker pull ghcr.io/myorg/myapp:${NEW_VERSION}"
ssh "$TARGET-server" "docker compose up -d"

# Step 2: Run smoke tests against idle environment
echo "Running smoke tests against $TARGET..."
if ! ./scripts/smoke_test.sh "http://${TARGET}-server:8000"; then
    echo "ERROR: Smoke tests failed. Aborting deployment."
    exit 1
fi

# Step 3: Switch traffic
echo "Switching traffic to $TARGET..."
sed -i "s/upstream active {.*/# Managed by deploy script/" /etc/nginx/conf.d/app.conf
nginx -s reload

# Step 4: Keep old environment running for instant rollback
echo "Deployment complete. Old environment ($CURRENT) available for rollback."
echo "Run './rollback.sh' within 30 minutes if issues are detected."
```

### Canary Deployments

Canary **gradually shifts traffic** from the old version to the new version, monitoring for errors at each step. The reason it is called "canary" is the mining practice of using canaries to detect toxic gases — a small group absorbs risk before the majority.

```
Step 1:  [95% → v1.0] [5% → v1.1]    ← Canary: small traffic slice
Step 2:  [75% → v1.0] [25% → v1.1]   ← Monitoring looks good, increase
Step 3:  [50% → v1.0] [50% → v1.1]   ← Still good, continue
Step 4:  [0%  → v1.0] [100% → v1.1]  ← Full rollout
```

**Kubernetes canary with Ingress-NGINX:**

```yaml
# canary-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp-canary
spec:
  replicas: 1  # Small number of canary pods
  selector:
    matchLabels:
      app: myapp
      track: canary
  template:
    metadata:
      labels:
        app: myapp
        track: canary
    spec:
      containers:
        - name: myapp
          image: ghcr.io/myorg/myapp:v1.1  # New version
---
# Canary ingress: routes percentage of traffic to canary pods
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp-canary
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "10"  # 10% traffic
spec:
  ingressClassName: nginx
  rules:
    - host: myapp.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp-canary
                port:
                  number: 80
```

**Progressive canary script:**

```python
import subprocess
import time
import requests

CANARY_STEPS = [5, 10, 25, 50, 75, 100]
ERROR_THRESHOLD = 0.02  # 2% error rate triggers rollback

def get_error_rate(service: str, window: str = "5m") -> float:
    """Query Prometheus for the canary error rate."""
    query = f'rate(http_requests_total{{service="{service}",status=~"5.."}}[{window}]) / rate(http_requests_total{{service="{service}"}}[{window}])'
    resp = requests.get(f"http://prometheus:9090/api/v1/query", params={"query": query})
    result = resp.json()["data"]["result"]
    return float(result[0]["value"][1]) if result else 0.0

def set_canary_weight(weight: int):
    """Update the canary ingress annotation."""
    subprocess.run([
        "kubectl", "annotate", "ingress", "myapp-canary",
        f"nginx.ingress.kubernetes.io/canary-weight={weight}",
        "--overwrite"
    ], check=True)

for weight in CANARY_STEPS:
    print(f"Setting canary weight to {weight}%...")
    set_canary_weight(weight)

    # Wait for metrics to stabilize
    time.sleep(300)  # 5 minutes per step

    error_rate = get_error_rate("myapp-canary")
    print(f"  Error rate: {error_rate:.3%}")

    if error_rate > ERROR_THRESHOLD:
        print(f"  ERROR: Error rate {error_rate:.3%} exceeds threshold. Rolling back!")
        set_canary_weight(0)
        break
else:
    print("Canary promotion complete — 100% traffic on new version.")
```

### When to Use Each

| Factor | Blue-Green | Canary |
|--------|-----------|--------|
| **Rollback speed** | Instant (switch back) | Fast (set weight to 0) |
| **Resource cost** | 2x infrastructure | ~10-25% extra |
| **Risk exposure** | All-or-nothing switch | Gradual (1% → 100%) |
| **Best for** | Database migrations, breaking changes | Stateless services, UI changes |
| **Complexity** | Lower | Higher (needs metrics pipeline) |

**The trade-off**: Blue-green is simpler to implement but requires double the infrastructure. Canary uses fewer resources but requires a metrics pipeline to detect regressions automatically. For most teams, **start with blue-green** and graduate to canary as your monitoring matures.'''
    ),

    (
        "infra_sec1_16",
        r'''How should I manage secrets in a production application? I'm currently using .env files.''',
        r'''<think>
Secret management is a critical security topic. The user is using .env files which is fine for local dev but dangerous for production. I need to cover: why .env files are risky (checked into git, no access control, no rotation), environment variables (better but limited), and vault-based solutions (HashiCorp Vault, AWS Secrets Manager, etc.). Show practical examples with multiple approaches, from simplest to most secure.
</think>

## Secret Management: From .env Files to Production Vaults

Using `.env` files for secrets is acceptable for **local development only**. The reason they are dangerous in production is: they are often accidentally committed to git (exposing secrets permanently in history), they provide no access control (anyone with server access sees everything), they cannot be rotated without redeployment, and there is no audit trail of who accessed which secret.

### The Secret Management Hierarchy

```
Level 1: .env files        → Local dev only (gitignored)
Level 2: Environment vars  → Simple deployments (CI/CD injects them)
Level 3: Cloud secrets     → AWS Secrets Manager / GCP Secret Manager
Level 4: HashiCorp Vault   → Full secret lifecycle management
```

### Level 1: Local Development (.env with Safety)

```bash
# .env (MUST be in .gitignore)
DATABASE_URL=postgresql://dev:devpass@localhost:5432/devdb
REDIS_URL=redis://localhost:6379
SECRET_KEY=local-dev-only-not-real
```

```python
# settings.py — load with validation
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings with validation and type safety."""
    database_url: str
    redis_url: str
    secret_key: str
    debug: bool = False

    # Important: never log or serialize secrets
    def __repr__(self):
        return "Settings(**redacted**)"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

**Critical .gitignore entries:**

```gitignore
# NEVER commit these
.env
.env.local
.env.production
*.pem
*.key
credentials.json
service-account.json
```

### Level 2: CI/CD Environment Variables

```yaml
# GitHub Actions — secrets injected as env vars
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          SECRET_KEY: ${{ secrets.SECRET_KEY }}
        run: |
          # Secrets available as env vars during this step
          # Important: never echo/log them
          ./deploy.sh
```

**The trade-off**: Environment variables are simple but visible in `/proc/<pid>/environ`, `docker inspect`, and process listings. They are better than files but not truly secure.

### Level 3: Cloud Secret Managers

**AWS Secrets Manager:**

```python
import boto3
import json
from functools import lru_cache

@lru_cache(maxsize=1)
def get_secrets() -> dict:
    """Fetch secrets from AWS Secrets Manager at startup."""
    client = boto3.client("secretsmanager", region_name="us-east-1")
    response = client.get_secret_value(SecretId="prod/myapp/config")
    return json.loads(response["SecretString"])

# Usage
secrets = get_secrets()
db_url = secrets["DATABASE_URL"]
```

**Best practice** — rotate secrets automatically:

```python
import boto3
from datetime import datetime, timedelta

def setup_auto_rotation(secret_id: str, rotation_days: int = 30):
    """Enable automatic secret rotation."""
    client = boto3.client("secretsmanager")
    client.rotate_secret(
        SecretId=secret_id,
        RotationLambdaARN="arn:aws:lambda:us-east-1:123:function:rotate-db-password",
        RotationRules={"AutomaticallyAfterDays": rotation_days},
    )
```

### Level 4: HashiCorp Vault

For full secret lifecycle management (dynamic secrets, leasing, revocation):

```python
import hvac

class VaultClient:
    """HashiCorp Vault client for secret management."""

    def __init__(self, vault_url: str, role_id: str, secret_id: str):
        self.client = hvac.Client(url=vault_url)
        # AppRole auth — no static tokens
        self.client.auth.approle.login(
            role_id=role_id,
            secret_id=secret_id,
        )

    def get_database_credentials(self) -> dict:
        """Get dynamic database credentials (auto-expire after TTL)."""
        # Vault generates a unique username/password with a lease
        response = self.client.secrets.database.generate_credentials(
            name="myapp-readonly"
        )
        return {
            "username": response["data"]["username"],
            "password": response["data"]["password"],
            "lease_id": response["lease_id"],
            "ttl": response["lease_duration"],  # Credentials expire automatically
        }

    def get_static_secret(self, path: str) -> dict:
        """Read a static secret from Vault KV store."""
        response = self.client.secrets.kv.v2.read_secret_version(
            path=path, mount_point="secret"
        )
        return response["data"]["data"]
```

**The reason** Vault is the gold standard is **dynamic secrets**: instead of a shared database password, Vault generates unique, short-lived credentials for each application instance. If credentials are compromised, they expire automatically and can be traced to the specific instance.

### Kubernetes Secrets Integration

```yaml
# Use External Secrets Operator to sync from Vault/AWS to K8s
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: myapp-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: myapp-secrets
  data:
    - secretKey: database-url
      remoteRef:
        key: prod/myapp/config
        property: DATABASE_URL
```

### Secret Management Checklist

- **Never commit secrets to git** — if you did, rotate immediately (the secret is in git history forever)
- **Never log secrets** — use redaction in your logging config
- **Rotate secrets regularly** — 90 days maximum for static secrets
- **Use least-privilege access** — each service gets only the secrets it needs
- **Audit access** — know who/what accessed which secret and when
- **Encrypt at rest and in transit** — TLS for Vault/AWS API calls, encrypted storage backend

**Important**: If a secret has ever been exposed (committed to git, logged, emailed), treat it as compromised and rotate it immediately. Deleting the commit or log entry is not sufficient because copies may exist in caches, backups, or forks.'''
    ),

    # ===================== SECURITY (9 pairs) =====================

    (
        "infra_sec1_17",
        r'''How do I prevent XSS (Cross-Site Scripting) attacks in a web application?''',
        r'''<think>
XSS prevention is a fundamental web security topic. I need to cover the three types (Stored, Reflected, DOM-based), the core defense (output encoding/escaping), Content-Security-Policy headers, and practical examples in both server-side templates and frontend frameworks. The key insight is that XSS is an output encoding problem, not an input validation problem.
</think>

## XSS Prevention in Web Applications

Cross-Site Scripting (XSS) allows attackers to **inject malicious JavaScript** into your web pages, which then executes in other users' browsers. The reason XSS is so dangerous is that the injected script runs with the same privileges as your application — it can steal session cookies, redirect users to phishing pages, or perform actions on behalf of the victim.

### The Three Types

1. **Stored XSS**: Malicious script saved in your database (e.g., a comment containing `<script>`)
2. **Reflected XSS**: Script in a URL parameter reflected back in the page
3. **DOM-based XSS**: Client-side JavaScript inserts untrusted data into the DOM

### Core Defense: Output Encoding

**The most important principle**: XSS is an **output problem**, not an input problem. You must encode data when rendering it, based on the context where it appears.

**Python (Flask/Jinja2) — auto-escaping:**

```python
from markupsafe import escape
from flask import Flask, request, render_template

app = Flask(__name__)

# Jinja2 auto-escapes by default in Flask
# {{ user_input }} is SAFE — auto-escaped
# {{ user_input | safe }} is DANGEROUS — bypasses escaping

@app.route("/profile/<username>")
def profile(username):
    # Jinja2 will auto-escape username in the template
    return render_template("profile.html", username=username)

# If rendering outside templates, use markupsafe
@app.route("/api/search")
def search():
    query = request.args.get("q", "")
    # Manual escaping for non-template contexts
    safe_query = escape(query)
    return f"<p>Results for: {safe_query}</p>"
```

**Template (profile.html):**

```html
<!-- SAFE: Jinja2 auto-escapes {{ username }} -->
<h1>Profile: {{ username }}</h1>

<!-- DANGEROUS: never use | safe with user input -->
<!-- <h1>{{ username | safe }}</h1>  DO NOT DO THIS -->

<!-- DANGEROUS: unquoted attributes -->
<!-- <div class={{ username }}>  ALWAYS quote attributes -->
<div class="{{ username }}">Safe</div>
```

### Context-Specific Encoding

**Important**: Different contexts require different encoding:

```python
from markupsafe import escape
import json

user_input = request.form["name"]

# HTML body context — HTML entity encoding
html_safe = escape(user_input)
# <script>alert(1)</script> → &lt;script&gt;alert(1)&lt;/script&gt;

# JavaScript context — JSON encoding
js_safe = json.dumps(user_input)
# In template: <script>var name = {{ name_json | safe }};</script>

# URL context — URL encoding
from urllib.parse import quote
url_safe = quote(user_input)
# In template: <a href="/search?q={{ query | urlencode }}">
```

### Frontend Framework Defenses

React and Vue **auto-escape by default**, which is the best practice:

```jsx
// React — SAFE by default
function UserProfile({ username }) {
  // React escapes {username} automatically
  return <h1>Welcome, {username}</h1>;
}

// DANGEROUS: dangerouslySetInnerHTML bypasses escaping
// Only use with sanitized HTML from a trusted source
function RichContent({ html }) {
  // If you must render HTML, sanitize first
  const clean = DOMPurify.sanitize(html);
  return <div dangerouslySetInnerHTML={{ __html: clean }} />;
}
```

```javascript
// DOM-based XSS prevention
// DANGEROUS:
element.innerHTML = userInput;  // Executes scripts in input

// SAFE:
element.textContent = userInput;  // Treats input as text only
```

### Content-Security-Policy Header

CSP is a **defense-in-depth** layer that restricts what scripts can execute, even if XSS is present:

```python
@app.after_request
def add_security_headers(response):
    # Block inline scripts and only allow scripts from your domain
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.example.com; "
        "style-src 'self' 'unsafe-inline'; "  # Inline styles often needed
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.example.com; "
        "frame-ancestors 'none'; "  # Prevents clickjacking
        "base-uri 'self'"
    )
    return response
```

**The reason** CSP is so effective: even if an attacker injects `<script>alert(1)</script>`, the browser refuses to execute it because inline scripts are not in the `script-src` policy. This turns a successful XSS injection into a harmless string.

### DOMPurify for User-Generated HTML

When you must accept rich HTML (markdown editors, CMS content):

```javascript
import DOMPurify from "dompurify";

// Sanitize HTML — removes all dangerous tags and attributes
const dirty = '<p>Hello</p><script>alert("xss")</script><img onerror="alert(1)" src="x">';
const clean = DOMPurify.sanitize(dirty);
// Result: '<p>Hello</p><img src="x">'
// Script tag and onerror handler are stripped
```

### XSS Prevention Checklist

- **Use a framework with auto-escaping** (Jinja2, React, Vue)
- **Never use `| safe`, `dangerouslySetInnerHTML`, or `innerHTML`** with user input
- **Set Content-Security-Policy headers** to block inline scripts
- **Use `HttpOnly` and `Secure` flags on cookies** so XSS cannot steal them
- **Validate and sanitize HTML** if you must accept rich text (use DOMPurify)'''
    ),

    (
        "infra_sec1_18",
        r'''How do I implement CSRF protection in a web application? What's the difference between token-based and SameSite cookie approaches?''',
        r'''<think>
CSRF is about forging requests from other sites using the victim's cookies. I need to explain the attack mechanism, then cover two defenses: synchronizer token pattern (traditional) and SameSite cookies (modern). Show implementations in Flask/FastAPI. The key insight is that SameSite cookies are simpler but have browser compatibility considerations, while tokens are the traditional gold standard.
</think>

## CSRF Token Implementation

Cross-Site Request Forgery (CSRF) tricks a user's browser into **making unwanted requests** to your application using their existing session. The reason it works is that browsers automatically attach cookies to every request to a domain, regardless of which site initiated the request.

### How the Attack Works

```
1. User logs into bank.example.com (session cookie set)
2. User visits evil.example.com
3. Evil site has: <form action="https://bank.example.com/transfer" method="POST">
                    <input name="to" value="attacker">
                    <input name="amount" value="10000">
                  </form>
                  <script>document.forms[0].submit();</script>
4. Browser sends the POST with the user's bank session cookie
5. Bank processes the transfer — it looks legitimate
```

### Defense 1: Synchronizer Token Pattern

Generate a unique, unpredictable token per session. Include it in every form and verify it on the server. The reason this works is that the attacker's site cannot read the token (same-origin policy prevents it).

**Flask implementation:**

```python
import secrets
from functools import wraps
from flask import Flask, session, request, abort, render_template

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

def generate_csrf_token() -> str:
    """Generate and store a CSRF token in the session."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

# Make token available in all templates
app.jinja_env.globals["csrf_token"] = generate_csrf_token

def csrf_protect(f):
    """Decorator to verify CSRF token on state-changing requests."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
            if not token or token != session.get("_csrf_token"):
                abort(403, "CSRF token missing or invalid")
        return f(*args, **kwargs)
    return decorated

@app.route("/transfer", methods=["GET", "POST"])
@csrf_protect
def transfer():
    if request.method == "POST":
        # Token was verified by decorator — safe to process
        to_account = request.form["to"]
        amount = request.form["amount"]
        process_transfer(to_account, amount)
        return "Transfer complete"
    return render_template("transfer.html")
```

**Template (transfer.html):**

```html
<form method="POST" action="/transfer">
    <!-- Hidden CSRF token field -->
    <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">

    <label>To Account:</label>
    <input type="text" name="to" required>

    <label>Amount:</label>
    <input type="number" name="amount" required>

    <button type="submit">Transfer</button>
</form>
```

**For AJAX requests:**

```javascript
// Read token from meta tag
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

// Include in all fetch requests
async function apiPost(url, data) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrfToken,  // CSRF token in header
        },
        body: JSON.stringify(data),
        credentials: "same-origin",  // Include cookies
    });
    return response.json();
}
```

### Defense 2: SameSite Cookies

Modern browsers support `SameSite` cookie attribute, which prevents the browser from sending cookies on cross-site requests:

```python
from flask import Flask

app = Flask(__name__)

app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",     # Prevents CSRF on POST requests
    SESSION_COOKIE_SECURE=True,         # HTTPS only
    SESSION_COOKIE_HTTPONLY=True,        # JavaScript cannot read cookie
)
```

**SameSite values explained:**

| Value | Behavior | CSRF Protection |
|-------|----------|----------------|
| `Strict` | Cookie never sent cross-site | Full protection, but breaks legitimate links (e.g., clicking a link from email) |
| `Lax` | Cookie sent on top-level GET navigations, blocked on POST | Protects against POST-based CSRF (most common) |
| `None` | Cookie always sent (requires `Secure` flag) | No protection (used for cross-site APIs) |

### Which Approach to Use?

**Best practice**: Use **both** — defense in depth.

```python
# Belt AND suspenders approach
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"      # Browser-level defense
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True

# Plus token-based CSRF protection for state-changing requests
@app.before_request
def check_csrf():
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if not request.is_json:  # Form submissions need token check
            token = request.form.get("_csrf_token")
            if token != session.get("_csrf_token"):
                abort(403)
```

**The trade-off**: SameSite cookies are simpler (no tokens to manage) but rely on browser support and do not protect against subdomain attacks. Token-based CSRF works everywhere but adds complexity. The reason to use both is that security is about **layers** — if one defense fails, the other catches it.

**Important**: CSRF tokens must be:
- **Unpredictable** (use `secrets.token_hex`, not random numbers)
- **Tied to the user session** (not a global value)
- **Verified on every state-changing request** (POST, PUT, DELETE)'''
    ),

    (
        "infra_sec1_19",
        r'''What are the best practices for implementing JWT authentication? What are the common pitfalls?''',
        r'''<think>
JWT auth is widely used but frequently implemented incorrectly. I need to cover: how JWTs work (header.payload.signature), the critical pitfalls (storing in localStorage = XSS vulnerability, not validating properly, using weak secrets, not setting expiration), and the best practice pattern (short-lived access token + refresh token in httpOnly cookie). Show Python implementation with PyJWT.
</think>

## JWT Authentication: Best Practices and Pitfalls

JSON Web Tokens (JWTs) are the most common authentication mechanism for APIs. However, they are **frequently implemented insecurely**. The reason is that JWTs shift responsibility from the server (session store) to the client (token holder), and this creates several attack surfaces that developers overlook.

### How JWTs Work

```
Header.Payload.Signature

Header:  {"alg": "HS256", "typ": "JWT"}
Payload: {"sub": "user123", "role": "admin", "exp": 1700000000}
Signature: HMAC-SHA256(base64(header) + "." + base64(payload), secret)
```

**Important**: The payload is **base64-encoded, NOT encrypted**. Anyone can decode and read it. The signature only proves it was not tampered with.

### Secure JWT Implementation

```python
import jwt
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.security import HTTPBearer

app = FastAPI()
security = HTTPBearer()

# Best practice: use a strong, random secret (at least 256 bits)
JWT_SECRET = secrets.token_hex(32)  # In production, load from vault
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(minutes=15)   # Short-lived!
REFRESH_TOKEN_TTL = timedelta(days=7)

def create_access_token(user_id: str, role: str) -> str:
    """Create a short-lived access token."""
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + ACCESS_TOKEN_TTL,
        # Best practice: include a unique token ID for revocation
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token."""
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + REFRESH_TOKEN_TTL,
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str, expected_type: str = "access") -> dict:
    """Verify and decode a JWT with full validation."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],  # Always specify! (see pitfall #1)
            options={
                "require": ["exp", "sub", "type", "jti"],
                "verify_exp": True,
            },
        )
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
```

### Login and Token Refresh Flow

```python
@app.post("/auth/login")
async def login(response: Response, credentials: LoginRequest):
    """Authenticate and issue tokens."""
    user = await authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id)

    # Best practice: store refresh token in httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,    # JavaScript cannot access it (XSS protection)
        secure=True,      # HTTPS only
        samesite="lax",   # CSRF protection
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        path="/auth/refresh",  # Only sent to refresh endpoint
    )

    # Access token returned in response body
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    """Issue a new access token using the refresh token."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    payload = verify_token(refresh_token, expected_type="refresh")

    # Check if refresh token has been revoked (blacklist check)
    if await is_token_revoked(payload["jti"]):
        raise HTTPException(status_code=401, detail="Token revoked")

    # Issue new access token
    user = await get_user(payload["sub"])
    new_access = create_access_token(user.id, user.role)
    return {"access_token": new_access, "token_type": "bearer"}
```

### Common Pitfalls

**Pitfall 1: Algorithm confusion attack**

```python
# VULNERABLE: accepts any algorithm
payload = jwt.decode(token, SECRET, algorithms=["HS256", "RS256", "none"])

# SECURE: explicitly specify the expected algorithm
payload = jwt.decode(token, SECRET, algorithms=["HS256"])
```

The reason this matters: an attacker can change the header to `"alg": "none"` and the library will skip signature verification entirely.

**Pitfall 2: Storing tokens in localStorage**

```javascript
// VULNERABLE: localStorage is accessible to any JavaScript on the page
// If you have an XSS vulnerability, attacker steals the token
localStorage.setItem("token", accessToken);

// BETTER: keep access token in memory (JavaScript variable)
// Store refresh token in httpOnly cookie (see login endpoint above)
let accessToken = null;
async function login(username, password) {
    const res = await fetch("/auth/login", { method: "POST", ... });
    const data = await res.json();
    accessToken = data.access_token;  // In-memory only
}
```

**Pitfall 3: No expiration or very long expiration**

```python
# DANGEROUS: token valid forever
payload = {"sub": "user123"}  # No "exp" claim

# DANGEROUS: token valid for 1 year
"exp": datetime.now(timezone.utc) + timedelta(days=365)

# BEST PRACTICE: short access token + refresh token rotation
# Access: 15 minutes, Refresh: 7 days
```

**Pitfall 4: Sensitive data in payload**

```python
# NEVER put secrets in JWT payload (it is NOT encrypted)
payload = {
    "sub": "user123",
    "password": "hunter2",      # NEVER
    "ssn": "123-45-6789",       # NEVER
    "credit_card": "4111...",   # NEVER
}

# Only include what is needed for authorization
payload = {
    "sub": "user123",
    "role": "admin",
    "permissions": ["read", "write"],
}
```

### The Trade-off: JWT vs Session-Based Auth

JWTs are **stateless** (no server-side storage needed), which makes them great for distributed systems. The trade-off is that you cannot instantly revoke a JWT — it remains valid until expiration. This is why access tokens should be short-lived (15 minutes) and why you need a revocation check for refresh tokens.'''
    ),

    (
        "infra_sec1_20",
        r'''What's the correct way to hash passwords? I've seen people use MD5 and SHA-256 but I'm told those aren't good enough.''',
        r'''<think>
Password hashing is a critical security topic where many developers make dangerous mistakes. MD5 and SHA-256 are fast hash functions designed for data integrity, NOT passwords. I need to explain WHY speed is bad for passwords (GPUs can compute billions of SHA-256 hashes/second), then cover the correct options: bcrypt, scrypt, argon2. Show practical Python examples with passlib and argon2-cffi.
</think>

## Password Hashing: bcrypt, scrypt, and Argon2

MD5 and SHA-256 are **completely unsuitable** for password hashing. The reason is that they are designed to be **fast** — a modern GPU can compute **10 billion SHA-256 hashes per second**. This means an attacker with a leaked database can crack most passwords in minutes through brute force.

### Why Speed Is the Enemy

```
Hash Function    | Hashes/second (GPU) | Time to crack 8-char password
MD5              | ~40 billion         | Seconds
SHA-256          | ~10 billion         | Minutes
bcrypt (cost 12) | ~10 thousand        | Centuries
Argon2id         | ~1 thousand         | Millennia
```

Password hashing algorithms are **intentionally slow** — they are designed to cost significant CPU time and memory per hash, making brute force attacks computationally infeasible.

### Option 1: bcrypt (Battle-Tested Standard)

```python
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password with bcrypt (cost factor 12)."""
    # bcrypt automatically generates a unique salt per password
    # The salt is embedded in the output hash string
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)  # 2^12 = 4096 iterations
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored bcrypt hash."""
    return bcrypt.checkpw(
        password.encode("utf-8"),
        stored_hash.encode("utf-8")
    )

# Usage
hashed = hash_password("my_secure_password")
# Output: '$2b$12$LJ3m4ys3Lg2VJEjMYGSGf.N2bKVJy8HnSz...'
#          ^^^^  ^^
#          algo  cost factor

assert verify_password("my_secure_password", hashed) == True
assert verify_password("wrong_password", hashed) == False
```

**The reason** bcrypt is still widely used: it has been scrutinized by cryptographers for 25+ years with no practical attacks found. The `rounds` parameter lets you increase the cost as hardware gets faster.

### Option 2: Argon2id (Modern Best Practice)

Argon2 won the Password Hashing Competition in 2015. It is the **recommended choice** for new applications because it is resistant to both GPU attacks (like bcrypt) **and** specialized hardware attacks (ASICs/FPGAs) due to its memory-hard design.

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Configure the hasher with appropriate parameters
ph = PasswordHasher(
    time_cost=3,        # Number of iterations
    memory_cost=65536,  # 64 MB of memory per hash
    parallelism=4,      # Number of parallel threads
    hash_len=32,        # Output hash length in bytes
    salt_len=16,        # Salt length in bytes
)

def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return ph.hash(password)

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password and check if rehashing is needed."""
    try:
        ph.verify(stored_hash, password)

        # Best practice: rehash if parameters have changed
        if ph.check_needs_rehash(stored_hash):
            # Return the new hash so the caller can update the database
            return True  # Caller should update with hash_password(password)

        return True
    except VerifyMismatchError:
        return False

# Usage
hashed = hash_password("my_secure_password")
# Output: '$argon2id$v=19$m=65536,t=3,p=4$randomsalt$hashvalue'
#          ^^^^^^^^       ^^^^^^^^^^^^^
#          algorithm      parameters embedded in hash
```

### Integrating with a Web Application

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from argon2 import PasswordHasher

app = FastAPI()
ph = PasswordHasher()

class RegisterRequest(BaseModel):
    username: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        if v.lower() == v:
            raise ValueError("Password must contain uppercase letters")
        return v

@app.post("/register")
async def register(req: RegisterRequest):
    # Check if user exists
    existing = await db.fetch_one(
        "SELECT id FROM users WHERE username = $1", req.username
    )
    if existing:
        # Important: don't reveal whether username exists
        # Use the same response time to prevent timing attacks
        ph.hash("dummy_password")  # Constant-time operation
        raise HTTPException(400, "Registration failed")

    hashed = ph.hash(req.password)
    await db.execute(
        "INSERT INTO users (username, password_hash) VALUES ($1, $2)",
        req.username, hashed
    )
    return {"message": "User created"}

@app.post("/login")
async def login(req: RegisterRequest):
    user = await db.fetch_one(
        "SELECT id, password_hash FROM users WHERE username = $1",
        req.username
    )
    if not user:
        # Prevent timing attacks: hash a dummy password
        ph.hash("dummy_password")
        raise HTTPException(401, "Invalid credentials")

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")

    # Issue session/JWT token...
    return {"token": create_token(user["id"])}
```

### Choosing Parameters

| Algorithm | Parameter | Recommended | Trade-off |
|-----------|-----------|-------------|-----------|
| bcrypt | rounds | 12-14 | Higher = slower login (~250ms at 12) |
| Argon2id | time_cost | 3 | More iterations = slower |
| Argon2id | memory_cost | 65536 (64MB) | More memory = resistant to GPU/ASIC |
| Argon2id | parallelism | 4 | Matches typical server core count |

**Best practice**: Tune parameters so that hashing takes **250-500ms** on your production hardware. This is imperceptible to users but makes brute force infeasible. The trade-off is server CPU usage during login spikes — use rate limiting to prevent abuse.'''
    ),

    (
        "infra_sec1_21",
        r'''How do I implement rate limiting for a REST API? I want to prevent abuse without blocking legitimate users.''',
        r'''<think>
Rate limiting is essential for API security and stability. I should cover: the sliding window algorithm (most practical), token bucket (for burst tolerance), implementation options (in-memory, Redis-based, middleware), response headers (X-RateLimit-*), and per-user vs per-IP vs per-endpoint strategies. Show a complete FastAPI implementation with Redis.
</think>

## Rate Limiting Implementation for REST APIs

Rate limiting prevents abuse, brute force attacks, and resource exhaustion. The reason it is **critical** for any public API is that without it, a single client can overwhelm your server, degrade performance for all users, or attempt credential stuffing attacks at thousands of requests per second.

### Choosing a Strategy

| Strategy | Use Case | Example |
|----------|----------|---------|
| Per-IP | Anonymous endpoints | 100 req/min per IP |
| Per-User | Authenticated APIs | 1000 req/min per API key |
| Per-Endpoint | Sensitive operations | 5 login attempts/min |
| Tiered | Freemium APIs | Free: 100/hr, Pro: 10000/hr |

### Sliding Window Rate Limiter with Redis

The **best practice** algorithm is the sliding window counter, which provides accurate rate limiting without the boundary issues of fixed windows:

```python
import time
import redis
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()
redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

class RateLimiter:
    """Sliding window rate limiter using Redis sorted sets."""

    def __init__(self, redis_conn: redis.Redis):
        self.redis = redis_conn

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, dict]:
        """Check if a request is allowed under the rate limit.

        Returns (allowed, rate_limit_info) tuple.
        """
        now = time.time()
        window_start = now - window_seconds
        pipe = self.redis.pipeline()

        # Remove expired entries (outside the window)
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current entries in the window
        pipe.zcard(key)

        # Add current request timestamp
        pipe.zadd(key, {f"{now}:{id(key)}": now})

        # Set expiry on the key itself (cleanup)
        pipe.expire(key, window_seconds + 1)

        results = pipe.execute()
        request_count = results[1]  # zcard result

        remaining = max(0, max_requests - request_count - 1)
        reset_time = int(now + window_seconds)

        info = {
            "limit": max_requests,
            "remaining": remaining,
            "reset": reset_time,
            "retry_after": window_seconds if request_count >= max_requests else None,
        }

        return request_count < max_requests, info

limiter = RateLimiter(redis_client)

# Rate limit configurations per endpoint pattern
RATE_LIMITS = {
    "/auth/login":    {"max_requests": 5,    "window_seconds": 60},    # 5/min (brute force prevention)
    "/auth/register": {"max_requests": 3,    "window_seconds": 3600},  # 3/hour
    "/api/":          {"max_requests": 100,  "window_seconds": 60},    # 100/min (general API)
    "/api/search":    {"max_requests": 30,   "window_seconds": 60},    # 30/min (expensive operation)
}

def get_rate_limit_config(path: str) -> dict:
    """Find the most specific rate limit config for a path."""
    for pattern, config in RATE_LIMITS.items():
        if path.startswith(pattern):
            return config
    return {"max_requests": 60, "window_seconds": 60}  # Default: 60/min

def get_client_identifier(request: Request) -> str:
    """Identify the client for rate limiting purposes."""
    # Prefer authenticated user ID over IP
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"

    # Fall back to IP (handle proxies)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host
    return f"ip:{ip}"
```

### FastAPI Middleware Integration

```python
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all requests."""
    # Skip health check endpoint
    if request.url.path == "/health":
        return await call_next(request)

    client_id = get_client_identifier(request)
    config = get_rate_limit_config(request.url.path)

    rate_key = f"ratelimit:{client_id}:{request.url.path}"
    allowed, info = limiter.is_allowed(
        rate_key,
        config["max_requests"],
        config["window_seconds"],
    )

    if not allowed:
        # Return 429 Too Many Requests
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "retry_after": info["retry_after"],
            },
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(info["reset"]),
                "Retry-After": str(info["retry_after"]),
            },
        )

    # Process the request
    response = await call_next(request)

    # Add rate limit headers to all responses (best practice)
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    response.headers["X-RateLimit-Reset"] = str(info["reset"])

    return response
```

### Token Bucket for Burst Tolerance

The sliding window is strict — the token bucket algorithm allows **short bursts** while maintaining an average rate:

```python
class TokenBucket:
    """Token bucket rate limiter — allows bursts up to bucket size."""

    def __init__(self, redis_conn: redis.Redis):
        self.redis = redis_conn

    def is_allowed(self, key: str, rate: float, capacity: int) -> bool:
        """
        rate: tokens added per second
        capacity: max burst size (bucket size)
        """
        now = time.time()
        bucket_key = f"bucket:{key}"

        # Atomic Lua script for thread safety
        lua_script = """
        local tokens = tonumber(redis.call('hget', KEYS[1], 'tokens') or ARGV[3])
        local last = tonumber(redis.call('hget', KEYS[1], 'last') or ARGV[1])
        local rate = tonumber(ARGV[2])
        local capacity = tonumber(ARGV[3])
        local now = tonumber(ARGV[1])

        -- Add tokens based on elapsed time
        local elapsed = now - last
        tokens = math.min(capacity, tokens + (elapsed * rate))

        -- Try to consume one token
        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('hset', KEYS[1], 'tokens', tokens, 'last', now)
            redis.call('expire', KEYS[1], math.ceil(capacity / rate) + 1)
            return 1
        end
        return 0
        """
        result = self.redis.eval(lua_script, 1, bucket_key, now, rate, capacity)
        return result == 1
```

### Important Considerations

**The trade-off** between strict and lenient rate limiting: too strict blocks legitimate users (especially behind shared IPs like corporate NATs); too lenient fails to prevent abuse. Best practice is to start lenient and tighten based on observed abuse patterns.

- **Always return standard headers** (`X-RateLimit-*`, `Retry-After`) so clients can adapt
- **Use different limits per endpoint** — login gets strict limits (brute force), reads get generous limits
- **Consider IP vs user ID** — authenticated requests should use user ID (IPs can be shared)
- **Use Redis** for distributed rate limiting across multiple app instances — in-memory counters do not work behind a load balancer'''
    ),

    (
        "infra_sec1_22",
        r'''How do I configure CORS properly? My frontend gets CORS errors and I'm tempted to just allow everything.''',
        r'''<think>
CORS is one of the most misunderstood web security mechanisms. The user is tempted to use `*` for everything, which is dangerous. I need to explain WHY CORS exists (it protects users, not servers), how the preflight mechanism works, and show proper configuration. The key insight is that CORS errors are usually a sign that your configuration is wrong, not that you need to open everything up.
</think>

## CORS Configuration Explained

CORS errors are frustrating, but **allowing everything (`*`) is dangerous** and often does not even work (browsers block `*` when credentials are involved). The reason CORS exists is to protect **your users** — without it, any website could make requests to your API using the user's cookies, enabling CSRF-like attacks.

### How CORS Works

```
1. Browser makes request from https://myapp.com to https://api.myapp.com
2. Browser checks: "Is api.myapp.com a different origin?" → Yes
3. For "simple" requests (GET, POST with form data): browser sends request,
   checks Access-Control-Allow-Origin in response
4. For "complex" requests (PUT, DELETE, custom headers, JSON):
   browser sends a PREFLIGHT OPTIONS request first
```

### The Preflight Flow

```
Browser                          API Server
  |                                |
  |-- OPTIONS /api/users --------->|  (Preflight: "Can I make this request?")
  |   Origin: https://myapp.com    |
  |   Access-Control-Request-Method: POST
  |   Access-Control-Request-Headers: Content-Type, Authorization
  |                                |
  |<--- 204 No Content ------------|  (Response: "Yes, here are the rules")
  |   Access-Control-Allow-Origin: https://myapp.com
  |   Access-Control-Allow-Methods: GET, POST, PUT, DELETE
  |   Access-Control-Allow-Headers: Content-Type, Authorization
  |   Access-Control-Max-Age: 86400
  |                                |
  |-- POST /api/users ------------>|  (Actual request)
  |   Origin: https://myapp.com    |
  |   Content-Type: application/json
  |   Authorization: Bearer xxx    |
  |                                |
  |<--- 201 Created ---------------|  (Response with CORS headers)
  |   Access-Control-Allow-Origin: https://myapp.com
```

### Correct FastAPI Configuration

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Define allowed origins explicitly — NEVER use ["*"] in production
ALLOWED_ORIGINS = [
    "https://myapp.com",
    "https://www.myapp.com",
    "https://staging.myapp.com",
]

# For local development, add localhost
import os
if os.getenv("ENVIRONMENT") == "development":
    ALLOWED_ORIGINS.extend([
        "http://localhost:3000",      # React dev server
        "http://localhost:5173",      # Vite dev server
        "http://127.0.0.1:3000",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # Specific origins, not "*"
    allow_credentials=True,           # Allow cookies/auth headers
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Request-ID",
        "X-CSRF-Token",
    ],
    expose_headers=[                  # Headers the browser can read
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-Request-ID",
    ],
    max_age=86400,                    # Cache preflight for 24 hours
)
```

### Flask Configuration

```python
from flask import Flask
from flask_cors import CORS

app = Flask(__name__)

CORS(app, resources={
    r"/api/*": {
        "origins": ["https://myapp.com", "https://staging.myapp.com"],
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
        "max_age": 86400,
    }
})
```

### Why `*` Does Not Work with Credentials

```python
# This WILL NOT WORK — browser rejects it:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Wildcard
    allow_credentials=True,      # With credentials
    # Browser error: "Cannot use wildcard with credentials"
)
```

**The reason**: Allowing any origin with credentials would let **any website** make authenticated requests to your API. The browser enforces this restriction specifically to prevent this attack.

### Common CORS Mistakes and Fixes

**Mistake 1: Dynamic origin reflection without validation**

```python
# DANGEROUS: reflects any origin back (equivalent to *)
@app.middleware("http")
async def bad_cors(request, call_next):
    response = await call_next(request)
    origin = request.headers.get("origin")
    response.headers["Access-Control-Allow-Origin"] = origin  # NEVER do this
    return response

# SAFE: validate against allowlist
ALLOWED = {"https://myapp.com", "https://staging.myapp.com"}

@app.middleware("http")
async def good_cors(request, call_next):
    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin in ALLOWED:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"  # Important for caching
    return response
```

**Mistake 2: Forgetting the `Vary: Origin` header**

When you dynamically set `Access-Control-Allow-Origin` based on the request origin, you **must** include `Vary: Origin`. The reason is that CDNs and browser caches might cache a response with `Origin: https://myapp.com` and serve it to a request from `https://evil.com`.

**Mistake 3: Not handling OPTIONS preflight**

```python
# If your framework does not handle OPTIONS automatically:
@app.options("/{path:path}")
async def preflight(path: str):
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "https://myapp.com",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
        },
    )
```

### Debugging CORS Errors

```javascript
// Check the actual error in the browser console:
// "No 'Access-Control-Allow-Origin' header" → Origin not in your allowlist
// "Method PUT is not allowed" → Add PUT to allow_methods
// "Header 'Authorization' is not allowed" → Add to allow_headers
// "Credentials flag is true, but Allow-Origin is '*'" → Use specific origins

// Quick test with curl (simulates a CORS preflight):
// curl -X OPTIONS https://api.myapp.com/endpoint \
//   -H "Origin: https://myapp.com" \
//   -H "Access-Control-Request-Method: POST" \
//   -H "Access-Control-Request-Headers: Content-Type" -v
```

**Important**: CORS is a **browser-enforced** security mechanism. Server-to-server requests (curl, Postman, backend services) are never affected by CORS. If your API works in Postman but not in the browser, CORS is the issue.'''
    ),

    (
        "infra_sec1_23",
        r'''How should I handle input validation and sanitization in a Python web API?''',
        r'''<think>
Input validation is a fundamental security practice. I should cover: validation vs sanitization (different things), Pydantic for structured validation (the Python standard), common injection vectors to validate against, and the principle of "validate input, encode output." Show practical FastAPI examples with Pydantic models, custom validators, and edge cases.
</think>

## Input Validation and Sanitization in Python APIs

Input validation is your **first line of defense** against injection attacks, data corruption, and application crashes. The reason it is so important is that every piece of user input is potentially malicious — and if invalid data reaches your database or business logic, the consequences range from bugs to full system compromise.

### Validation vs Sanitization

- **Validation**: Reject invalid input entirely ("this is not a valid email")
- **Sanitization**: Transform input to make it safe ("strip HTML tags from bio")

**Best practice**: Prefer **validation** (reject bad input) over sanitization (try to fix bad input). The reason is that sanitization can have unexpected edge cases, while rejection is absolute.

### Pydantic Models for Structured Validation

```python
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import EmailStr
from datetime import date
from typing import Annotated
import re

class CreateUserRequest(BaseModel):
    """User registration request with comprehensive validation."""

    username: Annotated[str, Field(
        min_length=3,
        max_length=30,
        pattern=r"^[a-zA-Z0-9_-]+$",  # Alphanumeric + underscore/hyphen only
        description="Username must be 3-30 chars, alphanumeric with _ and -"
    )]

    email: EmailStr  # Pydantic validates email format automatically

    password: Annotated[str, Field(min_length=12, max_length=128)]

    display_name: Annotated[str, Field(max_length=100)] = ""

    birth_date: date | None = None

    @field_validator("username")
    @classmethod
    def username_not_reserved(cls, v: str) -> str:
        """Prevent registration of system usernames."""
        reserved = {"admin", "root", "system", "api", "null", "undefined"}
        if v.lower() in reserved:
            raise ValueError(f"Username '{v}' is reserved")
        return v.lower()  # Normalize to lowercase

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Enforce password complexity requirements."""
        checks = [
            (r"[A-Z]", "one uppercase letter"),
            (r"[a-z]", "one lowercase letter"),
            (r"\d", "one digit"),
            (r"[!@#$%^&*(),.?\":{}|<>]", "one special character"),
        ]
        missing = [msg for pattern, msg in checks if not re.search(pattern, v)]
        if missing:
            raise ValueError(f"Password must contain at least: {', '.join(missing)}")
        return v

    @field_validator("display_name")
    @classmethod
    def sanitize_display_name(cls, v: str) -> str:
        """Remove potentially dangerous characters from display name."""
        # Strip control characters and null bytes
        v = re.sub(r"[\x00-\x1f\x7f]", "", v)
        # Collapse whitespace
        v = re.sub(r"\s+", " ", v).strip()
        return v

    @field_validator("birth_date")
    @classmethod
    def reasonable_birth_date(cls, v: date | None) -> date | None:
        if v is None:
            return v
        if v > date.today():
            raise ValueError("Birth date cannot be in the future")
        if v.year < 1900:
            raise ValueError("Birth date must be after 1900")
        return v
```

### FastAPI Integration

```python
from fastapi import FastAPI, HTTPException, Query, Path
from typing import Annotated

app = FastAPI()

@app.post("/users", status_code=201)
async def create_user(request: CreateUserRequest):
    """Pydantic validates BEFORE this function runs."""
    # If we reach here, all input is valid and sanitized
    user = await db.create_user(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
        display_name=request.display_name,
    )
    return {"id": user.id, "username": user.username}

# Query parameter validation
@app.get("/users")
async def list_users(
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    sort_by: Annotated[str, Query(pattern=r"^(name|created_at|email)$")] = "created_at",
):
    """All query params are validated by FastAPI + Pydantic."""
    offset = (page - 1) * per_page
    return await db.list_users(
        offset=offset, limit=per_page, search=search, sort_by=sort_by
    )

# Path parameter validation
@app.get("/users/{user_id}")
async def get_user(
    user_id: Annotated[int, Path(ge=1, le=2_147_483_647)]  # Valid int32 range
):
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user
```

### Preventing Common Injection Vectors

```python
import re
import html
from pathlib import Path

class SecurityValidators:
    """Reusable validators for common injection vectors."""

    @staticmethod
    def safe_filename(filename: str) -> str:
        """Prevent path traversal attacks in file uploads."""
        # Remove path components — the reason: "../../../etc/passwd"
        filename = Path(filename).name

        # Remove null bytes (bypass technique)
        filename = filename.replace("\x00", "")

        # Whitelist safe characters
        filename = re.sub(r"[^\w\-.]", "_", filename)

        # Prevent hidden files
        if filename.startswith("."):
            filename = "_" + filename

        if not filename:
            raise ValueError("Invalid filename")
        return filename

    @staticmethod
    def safe_redirect_url(url: str, allowed_hosts: set[str]) -> str:
        """Prevent open redirect attacks."""
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # Only allow relative URLs or URLs to allowed hosts
        if parsed.scheme and parsed.netloc:
            if parsed.netloc not in allowed_hosts:
                raise ValueError(f"Redirect to {parsed.netloc} not allowed")
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Invalid URL scheme")
        elif url.startswith("//"):
            # Protocol-relative URL — also a redirect vector
            raise ValueError("Protocol-relative URLs not allowed")

        return url

    @staticmethod
    def safe_html_text(text: str) -> str:
        """Strip all HTML for plain text fields."""
        # Remove HTML tags entirely
        clean = re.sub(r"<[^>]+>", "", text)
        # Decode entities that might have been double-encoded
        clean = html.unescape(clean)
        # Re-escape for safe output
        return html.escape(clean)
```

### Error Responses (Don't Leak Internals)

```python
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    """Return clean validation errors without internal details."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"][1:]),  # Skip "body"
            "message": error["msg"],
            # Important: do NOT include error["input"] — it may contain passwords
        })
    return JSONResponse(status_code=422, content={"errors": errors})
```

### Validation Checklist

- **Validate type, length, format, and range** for every input field
- **Use allowlists** (valid patterns) over blocklists (known bad patterns) — the reason is that attackers always find new bypass techniques for blocklists
- **Validate on the server** even if you validate on the client — client validation is for UX, server validation is for security
- **Never trust Content-Type headers** — validate the actual content, not what the client claims it is
- **Limit request body size** at the web server level (nginx: `client_max_body_size 10m`)'''
    ),

    (
        "infra_sec1_24",
        r'''Explain the OAuth2 authorization flow. How do I implement "Login with Google/GitHub" in my web app?''',
        r'''<think>
OAuth2 Authorization Code flow is the standard for "Login with Google/GitHub." I need to explain the flow clearly (why each step exists for security), show the implementation with a practical Python example, and cover common pitfalls (state parameter for CSRF, PKCE for mobile apps, token storage). The key concept is that OAuth2 is about AUTHORIZATION (delegating access), and OIDC adds AUTHENTICATION (proving identity).
</think>

## OAuth2 Authorization Code Flow

OAuth2 "Login with Google/GitHub" uses the **Authorization Code flow** — the most secure OAuth2 grant type for server-side web applications. The reason it exists is to let users **authorize your application to access their data** without sharing their password with you.

### The Flow (Step by Step)

```
User          Your App           Auth Provider (Google/GitHub)
  |               |                        |
  |-- Click "Login with Google" -->        |
  |               |                        |
  |               |-- Redirect user ------>|  Step 1: Authorization Request
  |               |   (with state param)   |
  |               |                        |
  |               |   <-- User logs in --> |  Step 2: User authenticates
  |               |   <-- User consents -->|  Step 3: User grants permissions
  |               |                        |
  |<---- Redirect back to your app --------|  Step 4: Auth code callback
  |   /callback?code=abc123&state=xyz      |
  |               |                        |
  |               |-- Exchange code ------>|  Step 5: Token exchange (server-to-server)
  |               |   (code + client_secret)|
  |               |                        |
  |               |<-- access_token -------|  Step 6: Receive tokens
  |               |    id_token (OIDC)     |
  |               |                        |
  |               |-- GET /userinfo ------>|  Step 7: Fetch user profile
  |               |<-- {name, email} ------|
  |               |                        |
  |<-- Session created, user logged in     |
```

### Implementation with FastAPI

```python
import secrets
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

app = FastAPI()

# Register your app at https://github.com/settings/applications/new
GITHUB_CLIENT_ID = "your_client_id"          # From GitHub
GITHUB_CLIENT_SECRET = "your_client_secret"  # From GitHub (keep in vault!)
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"
CALLBACK_URL = "https://myapp.com/auth/github/callback"

# Step 1: Redirect user to GitHub for authorization
@app.get("/auth/github/login")
async def github_login(request: Request):
    """Initiate OAuth2 Authorization Code flow."""
    # Generate a random state parameter to prevent CSRF
    # Important: this is NOT optional — without it, an attacker can
    # forge the callback and link their GitHub account to the victim's session
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "scope": "user:email read:user",  # Request minimal permissions
        "state": state,
    }
    return RedirectResponse(f"{GITHUB_AUTH_URL}?{urlencode(params)}")

# Steps 4-7: Handle the callback
@app.get("/auth/github/callback")
async def github_callback(request: Request, code: str, state: str):
    """Exchange authorization code for tokens and create session."""

    # Verify state parameter (CSRF protection)
    stored_state = request.session.pop("oauth_state", None)
    if not stored_state or state != stored_state:
        raise HTTPException(403, "Invalid state parameter — possible CSRF attack")

    # Step 5: Exchange code for access token (server-to-server)
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": CALLBACK_URL,
            },
            headers={"Accept": "application/json"},
        )

        if token_response.status_code != 200:
            raise HTTPException(400, "Failed to exchange authorization code")

        token_data = token_response.json()
        access_token = token_data["access_token"]

        # Step 7: Fetch user profile
        user_response = await client.get(
            f"{GITHUB_API_URL}/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        github_user = user_response.json()

        # Fetch email (may be private)
        email_response = await client.get(
            f"{GITHUB_API_URL}/user/emails",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        emails = email_response.json()
        primary_email = next(
            (e["email"] for e in emails if e["primary"] and e["verified"]),
            None
        )

    # Create or update local user account
    user = await db.get_or_create_user(
        provider="github",
        provider_id=str(github_user["id"]),
        email=primary_email,
        name=github_user.get("name") or github_user["login"],
        avatar_url=github_user.get("avatar_url"),
    )

    # Create session (do NOT store the access_token in the session
    # unless you need to make further GitHub API calls)
    request.session["user_id"] = user.id

    return RedirectResponse("/dashboard")
```

### Supporting Multiple Providers

```python
from dataclasses import dataclass

@dataclass
class OAuthProvider:
    name: str
    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    userinfo_url: str
    scopes: str

PROVIDERS = {
    "github": OAuthProvider(
        name="GitHub",
        client_id=os.getenv("GITHUB_CLIENT_ID"),
        client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
        auth_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        userinfo_url="https://api.github.com/user",
        scopes="user:email read:user",
    ),
    "google": OAuthProvider(
        name="Google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
        scopes="openid email profile",
    ),
}

@app.get("/auth/{provider}/login")
async def oauth_login(request: Request, provider: str):
    if provider not in PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {provider}")

    config = PROVIDERS[provider]
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    request.session["oauth_provider"] = provider

    params = {
        "client_id": config.client_id,
        "redirect_uri": f"https://myapp.com/auth/{provider}/callback",
        "scope": config.scopes,
        "state": state,
        "response_type": "code",
    }
    return RedirectResponse(f"{config.auth_url}?{urlencode(params)}")
```

### Database Schema for OAuth Users

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    name VARCHAR(255),
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- One user can have multiple OAuth providers (GitHub + Google)
CREATE TABLE oauth_accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,       -- "github", "google"
    provider_user_id VARCHAR(255) NOT NULL,
    access_token TEXT,                    -- Encrypted at rest
    refresh_token TEXT,                   -- Encrypted at rest
    UNIQUE (provider, provider_user_id)   -- One link per provider account
);
```

### Security Best Practices

- **Always validate the `state` parameter** — the reason is CSRF prevention; without it, an attacker can link their OAuth account to a victim's session
- **Use PKCE** for mobile and single-page apps (where the client secret cannot be kept secret)
- **Request minimal scopes** — only ask for what you need
- **Store tokens encrypted** if you need them for ongoing API access
- **Validate the `redirect_uri`** matches exactly on the provider side — open redirect vulnerabilities in the callback URL can leak authorization codes

The trade-off with OAuth2: it adds significant complexity compared to password-based auth, but eliminates the risks of storing and managing passwords entirely. For most consumer-facing applications, the security and UX benefits of social login outweigh the implementation cost.'''
    ),

    (
        "infra_sec1_25",
        r'''How do I implement Content Security Policy (CSP) headers? I keep getting CSP violations and I'm not sure what each directive does.''',
        r'''<think>
CSP is one of the most powerful browser security features but also one of the most confusing. I need to explain each major directive, show how to build a policy incrementally (report-only first, then enforce), and cover common issues like inline scripts, CDNs, and nonces. The key insight is to start with a restrictive policy and open it up as needed, not the other way around.
</think>

## Content Security Policy (CSP) Headers

Content Security Policy is the **single most effective defense** against XSS attacks. The reason it works is that even if an attacker successfully injects a `<script>` tag into your page, the browser refuses to execute it because it violates the policy you defined. CSP also prevents other attacks like clickjacking, data injection, and unauthorized resource loading.

### Building a CSP Step by Step

Start with a **restrictive policy** and open it up as needed:

```python
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
import secrets

app = FastAPI()

class CSPMiddleware(BaseHTTPMiddleware):
    """Add Content-Security-Policy headers to all responses."""

    async def dispatch(self, request, call_next):
        # Generate a unique nonce for this request (for inline scripts)
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)

        csp_directives = [
            # Default: block everything not explicitly allowed
            "default-src 'self'",

            # Scripts: only from our domain + nonce for inline scripts
            f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net",

            # Styles: our domain + inline styles (often needed for frameworks)
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",

            # Images: our domain + data URIs (for inline images) + HTTPS
            "img-src 'self' data: https:",

            # Fonts: our domain + Google Fonts
            "font-src 'self' https://fonts.gstatic.com",

            # API calls: our domain + our API subdomain
            "connect-src 'self' https://api.myapp.com wss://ws.myapp.com",

            # Frames: block all embedding (prevents clickjacking)
            "frame-ancestors 'none'",

            # Forms: only submit to our domain
            "form-action 'self'",

            # Block <base> tag manipulation
            "base-uri 'self'",

            # Block <object>, <embed>, <applet> (legacy plugin vectors)
            "object-src 'none'",

            # Upgrade HTTP to HTTPS automatically
            "upgrade-insecure-requests",
        ]

        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Additional security headers (best practice to set alongside CSP)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        return response

app.add_middleware(CSPMiddleware)
```

### Directive Reference

| Directive | Controls | Example |
|-----------|----------|---------|
| `default-src` | Fallback for all resource types | `'self'` |
| `script-src` | JavaScript execution | `'self' 'nonce-abc123'` |
| `style-src` | CSS loading | `'self' 'unsafe-inline'` |
| `img-src` | Image loading | `'self' data: https:` |
| `font-src` | Font loading | `'self' https://fonts.gstatic.com` |
| `connect-src` | XHR, fetch, WebSocket | `'self' https://api.example.com` |
| `frame-src` | iframe sources | `https://youtube.com` |
| `frame-ancestors` | Who can embed YOUR page | `'none'` (blocks all) |
| `form-action` | Form submission targets | `'self'` |
| `base-uri` | `<base>` tag restrictions | `'self'` |
| `object-src` | Plugins (Flash, Java) | `'none'` |

### Source Values Explained

```
'self'          → Same origin only (protocol + host + port)
'none'          → Block everything
'unsafe-inline' → Allow inline <script>/<style> (AVOID for scripts)
'unsafe-eval'   → Allow eval(), new Function() (AVOID)
'nonce-abc123'  → Allow specific inline elements with matching nonce
'sha256-...'    → Allow inline elements with matching hash
https:          → Any HTTPS URL
https://cdn.example.com → Specific domain
*.example.com   → Any subdomain of example.com
```

### Using Nonces for Inline Scripts

Instead of using `'unsafe-inline'` (which defeats XSS protection), use **nonces** — a unique random value generated per request:

```html
<!-- Template (Jinja2) -->
<html>
<head>
    <!-- This inline script is allowed because it has the correct nonce -->
    <script nonce="{{ request.state.csp_nonce }}">
        // Application initialization code
        const config = {
            apiUrl: "https://api.myapp.com",
            wsUrl: "wss://ws.myapp.com",
        };
    </script>

    <!-- This injected script is BLOCKED — no matching nonce -->
    <!-- <script>alert('xss')</script>  → BLOCKED by CSP -->
</head>
<body>
    <!-- Event handlers are also blocked by CSP without 'unsafe-inline' -->
    <!-- <div onclick="alert('xss')">  → BLOCKED -->

    <!-- Use addEventListener instead (loaded from allowed script) -->
    <button id="submit-btn">Submit</button>
    <script nonce="{{ request.state.csp_nonce }}">
        document.getElementById("submit-btn").addEventListener("click", handleSubmit);
    </script>
</body>
</html>
```

### Report-Only Mode (Deploy Safely)

**Best practice**: Deploy CSP in **report-only mode first** to discover violations without breaking your site:

```python
# Phase 1: Report only (does NOT block anything)
response.headers["Content-Security-Policy-Report-Only"] = "; ".join([
    *csp_directives,
    "report-uri /csp-report",
    "report-to csp-endpoint",
])

# Collect and analyze violation reports
@app.post("/csp-report")
async def csp_report(request: Request):
    """Receive CSP violation reports from browsers."""
    report = await request.json()
    violation = report.get("csp-report", {})
    logger.warning(
        "CSP violation: %s blocked by %s on page %s",
        violation.get("blocked-uri"),
        violation.get("violated-directive"),
        violation.get("document-uri"),
    )
    # Store in database for analysis
    await db.store_csp_violation(violation)
    return {"status": "received"}
```

```
# Phase 2: After fixing all violations, switch to enforcing
Content-Security-Policy: <same directives>  (without -Report-Only)
```

### Common CSP Issues and Fixes

**Issue: Google Analytics / Tag Manager**

```
script-src 'self' https://www.googletagmanager.com https://www.google-analytics.com;
connect-src 'self' https://www.google-analytics.com;
img-src 'self' https://www.google-analytics.com;
```

**Issue: Inline styles from CSS-in-JS (styled-components, Emotion)**

```
# Option 1: Use nonces (best)
style-src 'self' 'nonce-abc123';

# Option 2: Allow unsafe-inline for styles (acceptable trade-off)
# The reason this is less risky than inline scripts: CSS injection
# is much harder to exploit than script injection
style-src 'self' 'unsafe-inline';
```

**Important**: CSP is additive — you cannot remove a permission in a more specific directive that was granted in `default-src`. The reason is that each directive is independent. If you set `default-src 'self' https:`, then `script-src 'self'` restricts scripts to only `'self'` (overrides default for scripts), but `img-src` still inherits `'self' https:` from the default.

The trade-off with CSP is upfront effort — building a correct policy requires understanding every external resource your site loads. But the security benefit is enormous: CSP effectively neutralizes the majority of XSS attacks, which remain the most common web vulnerability.'''
    ),
]
