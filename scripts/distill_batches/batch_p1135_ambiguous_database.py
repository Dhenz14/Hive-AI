"""
Ambiguous request handling pairs - vague database requests
"""

pairs = [
    {
        "instruction": r'''Fix the database. It's not working right.''',
        "output": r'''<think>
"Fix the database" -- not working how? Connection failures? Corrupt data? Slow queries? Wrong results? Schema issues? Full disk? Replication lag? I don't even know which database engine they're using. "Not working right" could mean literally anything. I need error messages and symptoms before I can do anything useful.
</think>

I need a bit more detail to help:

1. **What's the symptom?** Connection errors, slow queries, wrong data returned, disk full, or something else?
2. **Which database?** PostgreSQL, MySQL, SQLite, MongoDB?
3. **What changed recently?** New deployment, data migration, traffic spike?

Here's a quick diagnostic you can run right now to identify the most common database issues:

```sql
-- PostgreSQL diagnostics (adapt for your DB)

-- 1. Is the database accepting connections?
SELECT 1;  -- if this fails, it's a connection/auth issue

-- 2. Check active connections (pool exhaustion?)
SELECT count(*), state
FROM pg_stat_activity
GROUP BY state;
-- If "active" is near max_connections, you have pool exhaustion

-- 3. Check for long-running queries (blocking others?)
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC
LIMIT 10;

-- 4. Check for lock contention
SELECT blocked.pid AS blocked_pid,
       blocked.query AS blocked_query,
       blocking.pid AS blocking_pid,
       blocking.query AS blocking_query
FROM pg_stat_activity AS blocked
JOIN pg_locks AS bl ON bl.pid = blocked.pid
JOIN pg_locks AS kl ON kl.locktype = bl.locktype
    AND kl.database IS NOT DISTINCT FROM bl.database
    AND kl.relation IS NOT DISTINCT FROM bl.relation
    AND kl.pid != bl.pid
JOIN pg_stat_activity AS blocking ON blocking.pid = kl.pid
WHERE NOT bl.granted;

-- 5. Check disk usage
SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;

-- 6. Check for missing indexes (tables with lots of sequential scans)
SELECT relname, seq_scan, idx_scan,
       seq_scan - idx_scan AS too_many_seqs
FROM pg_stat_user_tables
WHERE seq_scan > 1000
ORDER BY too_many_seqs DESC
LIMIT 10;
```

```bash
# System-level checks
# Is the DB process running?
systemctl status postgresql
# or: docker ps | grep postgres

# Check disk space
df -h /var/lib/postgresql/

# Check DB logs for errors
tail -50 /var/log/postgresql/postgresql-*.log
```

Share the error messages or symptoms and I'll give you the specific fix.'''
    },
    {
        "instruction": r'''We need better queries. The current ones are too slow.''',
        "output": r'''<think>
"Better queries" -- which queries? All of them? A specific set? What makes them slow -- missing indexes, complex joins, full table scans, suboptimal query plans? How big are the tables? What's the acceptable response time? Without seeing the actual queries and their EXPLAIN output, I'm guessing. I should ask for the specific slow queries.
</think>

To optimize effectively, I need to know:

1. **Which queries are slow?** Can you share the SQL or ORM code for the 2-3 worst offenders?
2. **What are the table sizes?** Thousands or millions of rows?
3. **What's "too slow"?** 500ms when you need 50ms, or 30 seconds when you need 3?

In the meantime, here's a process for finding and fixing slow queries systematically:

```sql
-- Step 1: Find your slowest queries automatically
-- PostgreSQL: enable pg_stat_statements extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

SELECT query,
       calls,
       round(mean_exec_time::numeric, 2) AS avg_ms,
       round(total_exec_time::numeric, 2) AS total_ms
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Step 2: Analyze a slow query
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.*, c.name AS customer_name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'pending'
  AND o.created_at > NOW() - INTERVAL '30 days'
ORDER BY o.created_at DESC
LIMIT 50;

-- What to look for in EXPLAIN output:
-- "Seq Scan" on large tables --> needs an index
-- "Sort" with high cost --> consider an index that matches the ORDER BY
-- "Nested Loop" with many rows --> might need a different join strategy
-- "Rows Removed by Filter: 999000" --> index would avoid scanning those rows

-- Step 3: Common fixes

-- A. Add indexes for WHERE + ORDER BY columns
CREATE INDEX idx_orders_status_created
    ON orders(status, created_at DESC);

-- B. Use covering indexes to avoid table lookups
CREATE INDEX idx_orders_pending_cover
    ON orders(status, created_at DESC)
    INCLUDE (customer_id, total)
    WHERE status = 'pending';  -- partial index: only indexes pending orders

-- C. Replace SELECT * with specific columns
-- BAD:  SELECT * FROM orders WHERE ...
-- GOOD: SELECT id, status, total, created_at FROM orders WHERE ...
```

```python
# D. Fix N+1 queries in your ORM (the #1 cause of slow apps)

# BAD: N+1 -- runs 1 query for orders + N queries for customers
orders = session.query(Order).filter(Order.status == "pending").all()
for order in orders:
    print(order.customer.name)  # each access triggers a query

# GOOD: eager load in a single query
from sqlalchemy.orm import joinedload
orders = session.query(Order).options(
    joinedload(Order.customer)
).filter(Order.status == "pending").all()
for order in orders:
    print(order.customer.name)  # no additional queries
```

Share your slowest query and its EXPLAIN output, and I'll write the optimized version.'''
    },
    {
        "instruction": r'''The data is wrong in our system. Can you investigate?''',
        "output": r'''<think>
"The data is wrong" -- which data? Wrong how? Incorrect values, missing records, duplicates, stale cached data, wrong calculations, data from the wrong environment? I need a specific example of what's wrong -- expected value vs actual value, which table/field, when it started. Without a concrete example, I'm just listing possibilities.
</think>

Data correctness issues need specifics to investigate. Can you tell me:

1. **What data is wrong?** Specific field, specific record. Example: "User #123's balance shows $50 but should be $75."
2. **Is it a display issue or storage issue?** Have you checked the database directly, or only seeing it through the UI/API?
3. **Scope?** One record, a batch of records, or everything?
4. **When was it last correct?** Did it change after a specific event (migration, import, code deploy)?

Here's a systematic investigation approach once I have a concrete example:

```sql
-- Investigation template: trace the data lifecycle

-- 1. Check the current stored value
SELECT * FROM accounts WHERE id = 123;

-- 2. Check the audit trail (if you have one)
SELECT * FROM account_changes
WHERE account_id = 123
ORDER BY changed_at DESC
LIMIT 20;

-- 3. Look for the write that corrupted the data
-- Check application logs around the time the data changed
-- Correlate updated_at timestamp with deploy/migration times

-- 4. Check for common data corruption patterns:

-- Duplicate records (missing unique constraint?)
SELECT email, COUNT(*) as dupes
FROM users
GROUP BY email
HAVING COUNT(*) > 1;

-- NULL values where there shouldn't be any
SELECT COUNT(*) FROM orders WHERE total IS NULL;

-- Orphaned records (foreign key not enforced?)
SELECT o.id FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE c.id IS NULL;

-- Stale data (not updated when source changed?)
SELECT a.id, a.cached_balance,
       (SELECT SUM(amount) FROM transactions t WHERE t.account_id = a.id) AS actual_balance
FROM accounts a
WHERE a.cached_balance != (SELECT SUM(amount) FROM transactions t WHERE t.account_id = a.id);
```

```python
# Quick script to compare API output vs database for a set of records
import requests
import psycopg2

def compare_data(record_ids):
    conn = psycopg2.connect("your_connection_string")
    cur = conn.cursor()

    mismatches = []
    for rid in record_ids:
        # Get from API
        api_data = requests.get(f"http://localhost:8000/api/accounts/{rid}").json()

        # Get from DB directly
        cur.execute("SELECT id, balance FROM accounts WHERE id = %s", (rid,))
        db_row = cur.fetchone()

        if api_data["balance"] != db_row[1]:
            mismatches.append({
                "id": rid,
                "api_value": api_data["balance"],
                "db_value": db_row[1],
            })

    return mismatches
```

Give me a specific wrong value and I'll trace exactly where it went wrong.'''
    },
    {
        "instruction": r'''Scale the database. We're growing fast.''',
        "output": r'''<think>
"Scale the database" -- scale for what? More reads? More writes? More storage? More concurrent connections? What are the current bottlenecks? What database are they using? How big is it now? What's the growth rate? Scaling strategies differ wildly: read replicas for read-heavy, sharding for write-heavy, vertical scaling if they're on a small instance, connection pooling if they're exhausting connections. Need to understand the current state and bottleneck.
</think>

Database scaling depends heavily on your situation. A few questions:

1. **What's the bottleneck now?** Slow reads, slow writes, too many connections, running out of disk, or just planning ahead?
2. **What database and current specs?** (PostgreSQL on a 2-core VM is very different from MySQL on RDS)
3. **What's the traffic pattern?** Read-heavy (e.g., content site) or write-heavy (e.g., IoT data ingestion)?
4. **How big is the data?** Current size and growth rate?

Here's a scaling roadmap, ordered from easiest to hardest. Most teams should work through these in order:

```text
== Level 1: Optimize what you have (free, hours of work) ==
- Add missing indexes (check pg_stat_user_tables for seq scans)
- Fix N+1 queries in application code
- Add connection pooling (PgBouncer for PostgreSQL)
- Tune database config (shared_buffers, work_mem, effective_cache_size)
- VACUUM and ANALYZE tables

== Level 2: Vertical scaling ($$, minutes of work) ==
- Upgrade to a bigger instance (more CPU, RAM, faster disk)
- Move to SSD/NVMe storage if not already
- This is often the right answer and people skip it for complex solutions

== Level 3: Read replicas ($$$, days of work) ==
- Add 1-2 read replicas for read-heavy workloads
- Route writes to primary, reads to replicas
- Works great when reads >> writes (which is most apps)

== Level 4: Caching layer ($$, days of work) ==
- Add Redis for frequently-accessed, rarely-changing data
- Cache at the application level, not the query level
- Invalidate on writes

== Level 5: Partitioning / Sharding ($$$$, weeks of work) ==
- Only needed for very large datasets or very high write throughput
- Table partitioning by date (for time-series data)
- Application-level sharding by tenant/customer
```

```python
# Level 3 example: read replica routing in SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

primary = create_engine("postgresql://user:pass@primary-host/db")
replica = create_engine("postgresql://user:pass@replica-host/db")

class RoutingSession(Session):
    def get_bind(self, mapper=None, clause=None):
        if self._flushing or self.is_modified():
            return primary  # writes go to primary
        return replica  # reads go to replica

# Level 1 example: add PgBouncer connection pooling
# pgbouncer.ini
# [databases]
# mydb = host=localhost port=5432 dbname=mydb
# [pgbouncer]
# pool_mode = transaction
# max_client_conn = 1000
# default_pool_size = 25
```

Tell me your current bottleneck and database specs, and I'll recommend the specific next step.'''
    },
    {
        "instruction": r'''Add caching to the application.''',
        "output": r'''<think>
"Add caching" -- cache what? Database query results? API responses? Rendered pages? Static assets? What's the caching layer -- in-memory (lru_cache), Redis, Memcached, CDN? What's the invalidation strategy? How stale can data be? Caching without a clear strategy causes more bugs than it solves. I need to know what's slow and what the consistency requirements are.
</think>

Caching is powerful but can introduce subtle bugs if not done carefully. Some questions:

1. **What's slow that you want to cache?** Database queries, external API calls, computed results, rendered pages?
2. **How stale is acceptable?** Real-time data (seconds) or can users see data from minutes/hours ago?
3. **What infrastructure do you have?** Already running Redis? Or starting from scratch?

Here's a layered caching approach, from simplest to most sophisticated:

```python
# === Layer 1: In-memory cache (zero infrastructure, good for single-server) ===
from functools import lru_cache
from datetime import datetime, timedelta

# Good for: config values, reference data, things that rarely change
@lru_cache(maxsize=256)
def get_product_categories():
    return db.query("SELECT * FROM categories WHERE active = true")

# Time-based expiration version
class TTLCache:
    def __init__(self, ttl_seconds=300):
        self.ttl = ttl_seconds
        self.cache = {}

    def get(self, key):
        if key in self.cache:
            value, expires = self.cache[key]
            if datetime.now() < expires:
                return value
            del self.cache[key]
        return None

    def set(self, key, value):
        self.cache[key] = (value, datetime.now() + timedelta(seconds=self.ttl))

cache = TTLCache(ttl_seconds=60)


# === Layer 2: Redis cache (multi-server, survives restarts) ===
import redis
import json

r = redis.Redis(host="localhost", port=6379, db=0)

class RedisCache:
    def __init__(self, client, default_ttl=300):
        self.client = client
        self.default_ttl = default_ttl

    def get_or_set(self, key, fetch_fn, ttl=None):
        """Return cached value, or call fetch_fn and cache the result."""
        cached = self.client.get(key)
        if cached is not None:
            return json.loads(cached)

        value = fetch_fn()
        self.client.setex(key, ttl or self.default_ttl, json.dumps(value))
        return value

    def invalidate(self, key):
        self.client.delete(key)

    def invalidate_pattern(self, pattern):
        """Invalidate all keys matching a pattern, e.g., 'user:123:*'."""
        for key in self.client.scan_iter(match=pattern):
            self.client.delete(key)

rc = RedisCache(r)

# Usage in your API:
@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    cache_key = f"product:{product_id}"
    return rc.get_or_set(
        cache_key,
        lambda: db.query(Product).get(product_id).to_dict(),
        ttl=600,  # cache for 10 minutes
    )

@app.put("/api/products/{product_id}")
def update_product(product_id: int, data: dict):
    product = db.query(Product).get(product_id)
    product.update(data)
    db.commit()
    rc.invalidate(f"product:{product_id}")  # bust the cache on write
    return product.to_dict()
```

The critical rule: always define your invalidation strategy before adding caching. A cache without clear invalidation is a source of stale-data bugs. Tell me what you want to cache and I'll design the right strategy.'''
    },
]
