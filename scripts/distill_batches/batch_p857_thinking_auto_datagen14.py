"""Phase 4A: Self-Improvement -- Training Data Generation (Part 14)

Generate and evaluate training pairs for database optimization topics.
Each answer creates 3 graded training pairs with quality analysis.
"""

PAIRS = [
    (
        "thinking/auto-datagen-query-optimization",
        r'''Generate 3 high-quality training pairs that teach SQL query optimization using EXPLAIN and index strategies. For each pair, explain why it's effective training data.''',
        r'''<think>
Query optimization is one of the highest-impact backend skills:
1. Most performance problems are database problems
2. EXPLAIN is the most important tool but few developers know how to read it
3. Index design is the single biggest performance lever

Progression: reading EXPLAIN output -> designing indexes -> rewriting queries
</think>

Here are 3 training pairs for SQL query optimization:

**Pair 1 (Beginner):**
```
Q: My query takes 8 seconds on a table with 2 million rows. How do I figure out why it is slow?

```sql
SELECT * FROM orders
WHERE customer_email = 'alice@example.com'
AND status = 'shipped'
ORDER BY created_at DESC
LIMIT 10;
```

A: Use EXPLAIN ANALYZE to see the database execution plan:

```sql
EXPLAIN ANALYZE
SELECT * FROM orders
WHERE customer_email = 'alice@example.com'
AND status = 'shipped'
ORDER BY created_at DESC
LIMIT 10;
```

**Reading the output:**
```
Sort  (cost=45231.12..45231.15 rows=12 width=200) (actual time=8234.5..8234.5 rows=10)
  Sort Key: created_at DESC
  -> Seq Scan on orders  (cost=0.00..45231.00 rows=12 width=200) (actual time=0.05..8230.2 rows=12)
       Filter: ((customer_email = 'alice@example.com') AND (status = 'shipped'))
       Rows Removed by Filter: 1999988
```

**What this tells you:**
- `Seq Scan` = scanning ALL 2 million rows (bad!)
- `Rows Removed by Filter: 1999988` = checked 2M rows, kept only 12
- The database is doing a full table scan to find 12 rows

**The fix -- add an index:**
```sql
CREATE INDEX idx_orders_email_status ON orders(customer_email, status);
```

**After adding the index:**
```
Limit  (rows=10)
  -> Index Scan using idx_orders_email_status on orders (actual time=0.05..0.08 rows=10)
       Index Cond: ((customer_email = 'alice@example.com') AND (status = 'shipped'))
```

**Result:** 8 seconds -> 0.1 milliseconds. The index lets the database jump directly to the matching rows instead of scanning everything.
```

**Why this is effective:** Shows the complete diagnostic workflow -- run EXPLAIN, read the output, identify the problem, apply the fix, verify. The before/after comparison makes the impact concrete.

**Pair 2 (Intermediate):**
```
Q: How do I design composite indexes? I have queries that filter on different combinations of columns and I do not know which indexes to create.

A: **Design indexes based on your queries, not your table structure.**

**The key rules for composite indexes:**

**Rule 1: Column order matters**
```sql
-- Index on (a, b, c) can satisfy:
WHERE a = 1                    -- YES (leftmost prefix)
WHERE a = 1 AND b = 2         -- YES
WHERE a = 1 AND b = 2 AND c = 3  -- YES
WHERE b = 2                    -- NO (skips leftmost column)
WHERE b = 2 AND c = 3         -- NO
WHERE a = 1 AND c = 3         -- PARTIAL (uses a, skips to scan for c)
```

**Rule 2: Equality columns first, then range/sort**
```sql
-- Query:
SELECT * FROM orders
WHERE status = 'active'        -- equality
AND region = 'US'              -- equality
AND created_at > '2024-01-01'  -- range
ORDER BY total DESC;           -- sort

-- Best index:
CREATE INDEX idx_orders_status_region_created ON orders(status, region, created_at);
-- Equality columns (status, region) first, then range column (created_at)
```

**Rule 3: Cover the query if possible**
```sql
-- If the query only needs specific columns:
SELECT customer_id, total FROM orders WHERE status = 'pending';

-- A covering index includes all needed columns:
CREATE INDEX idx_orders_pending ON orders(status) INCLUDE (customer_id, total);
-- The database never touches the table -- everything is in the index
```

**Practical example -- 3 queries, minimum indexes:**
```sql
-- Query 1: WHERE user_id = ? AND status = ?
-- Query 2: WHERE user_id = ? ORDER BY created_at DESC
-- Query 3: WHERE status = ? AND created_at > ?

-- Index 1: (user_id, status, created_at) -- covers Query 1 AND Query 2
-- Index 2: (status, created_at) -- covers Query 3

-- Two indexes cover all three queries
```
```

**Why this is effective:** Teaches the principles (prefix rule, equality-first, covering indexes) with concrete examples. The multi-query optimization at the end shows how to minimize the number of indexes.

**Pair 3 (Advanced):**
```
Q: My query uses an index but is still slow. EXPLAIN shows an Index Scan but it takes 3 seconds. What could be wrong?

A: An index scan can still be slow for several reasons:

**Problem 1: Low selectivity -- index matches too many rows**
```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE active = true;
-- Index Scan on idx_users_active  (actual rows=1800000)
-- 90% of users are active -- index returns most of the table!

-- Fix: Don't index boolean columns with skewed distribution.
-- A Seq Scan is faster when you are reading most of the table.
-- Partial index if you only query the minority:
CREATE INDEX idx_users_inactive ON users(id) WHERE active = false;
```

**Problem 2: Wide rows -- fetching too much data**
```sql
-- Table has 50 columns, each row is 2KB
SELECT * FROM orders WHERE user_id = 42;
-- Index finds 500 rows quickly, but loading 500 * 2KB = 1MB of data

-- Fix: Select only needed columns
SELECT id, total, status, created_at FROM orders WHERE user_id = 42;
-- Or use a covering index to avoid table access entirely
```

**Problem 3: Random I/O from uncorrelated index**
```sql
-- Rows matching the index condition are scattered across disk
-- Each row requires a separate disk seek

-- Fix: CLUSTER the table by the index (one-time operation):
CLUSTER orders USING idx_orders_user_id;
-- Now rows for the same user_id are physically adjacent on disk
```

**Problem 4: Index-only scan blocked by visibility map**
```sql
-- PostgreSQL needs to check if rows are visible to the current transaction
-- If the table has many dead tuples (not vacuumed), it must check the table

-- Fix: Run VACUUM
VACUUM ANALYZE orders;
-- Now the visibility map is up to date and index-only scans work
```

**Diagnostic checklist when index scan is slow:**
| Check | Command | Fix |
|-------|---------|-----|
| How many rows matched? | EXPLAIN ANALYZE | Partial index or different query |
| Is it SELECT *? | Read your query | Select specific columns |
| Table bloat? | pg_stat_user_tables | VACUUM FULL |
| Outdated statistics? | pg_stat_user_tables | ANALYZE table |
| Correlated data? | pg_stats | CLUSTER by index |
```

**Why this is effective:** Goes beyond the simple "add an index" advice to cover the situations where indexes are not enough. These are real production problems that intermediate developers struggle with.'''
    ),
    (
        "thinking/auto-datagen-connection-pooling",
        r'''Generate 3 high-quality training pairs that teach database connection pooling and connection management. For each pair, explain why it's effective training data.''',
        r'''<think>
Connection pooling is a critical production concern:
1. Opening a new database connection is expensive (TCP handshake, auth, TLS)
2. Without pooling, each request opens/closes a connection -- huge overhead
3. Pool misconfiguration causes either exhaustion (too few) or overload (too many)

Progression: why pooling matters -> configuring pool size -> diagnosing pool problems
</think>

Here are 3 training pairs for database connection pooling:

**Pair 1 (Beginner):**
```
Q: My web app becomes extremely slow under load. Each request takes 200ms to connect to the database before the query even runs. How do I fix this?

A: You are opening a new database connection for every request. Each connection requires:
- TCP handshake (~1-2ms local, 50-200ms remote)
- TLS negotiation (~50-100ms)
- Authentication (~10-50ms)
- Server process creation (~10-50ms)

**Total: 70-400ms per connection -- before your query even starts.**

**The fix: Connection pooling**

```python
# WITHOUT pooling (slow):
def get_user(user_id):
    conn = psycopg2.connect(host="db", dbname="myapp")  # 200ms overhead!
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()  # Connection discarded
    return user

# WITH pooling (fast):
from psycopg2 import pool

# Create pool once at app startup
db_pool = pool.ThreadedConnectionPool(
    minconn=5,    # Keep 5 connections ready
    maxconn=20,   # Allow up to 20
    host="db", dbname="myapp"
)

def get_user(user_id):
    conn = db_pool.getconn()  # <1ms -- reuses existing connection
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()
    finally:
        db_pool.putconn(conn)  # Return to pool, not closed
```

**Impact:**
| Metric | No pool | With pool |
|--------|---------|-----------|
| Connection time per request | 200ms | <1ms |
| Max concurrent DB connections | Unlimited (dangerous) | 20 (controlled) |
| Connection overhead at 100 req/s | 20 seconds/s wasted | 0 |
```

**Why this is effective:** Starts with the problem (slow connections), explains WHY it is slow with timing breakdown, then shows the exact code change with measurable impact.

**Pair 2 (Intermediate):**
```
Q: How do I choose the right connection pool size? My app has 50 threads but I have the pool set to 50 connections and the database is slow.

A: **More connections does NOT mean more performance.** Too many connections actually make the database SLOWER.

**Why 50 connections is probably too many:**

Your database server has N CPU cores. Each active connection can use one core. If you have 50 active queries on 8 cores, you get:
- 8 queries running + 42 waiting
- Context switching overhead between 50 processes
- Memory overhead: each PostgreSQL connection uses 5-10MB

**The formula:**
```
Optimal pool size = (CPU cores * 2) + number_of_disk_spindles

For a typical cloud database with 4 vCPUs and SSD:
Pool size = (4 * 2) + 1 = 9-10 connections
```

**Practical guidelines:**
```python
# For a web app with 50 threads:
db_pool = pool.ThreadedConnectionPool(
    minconn=5,     # Idle minimum
    maxconn=10,    # Hard maximum (NOT 50!)
)

# When a thread needs a connection and pool is exhausted:
# - Thread WAITS until a connection is returned to the pool
# - This is GOOD -- it prevents database overload
# - Set a timeout so threads do not wait forever:
conn = db_pool.getconn()  # Blocks until available
```

**What happens at different pool sizes (4-core database):**
| Pool size | Throughput (queries/sec) | Latency (p99) |
|-----------|------------------------|---------------|
| 5 | 900 | 15ms |
| 10 | 1000 | 12ms |
| 20 | 950 | 25ms |
| 50 | 700 | 80ms |
| 100 | 400 | 200ms |

**More connections = worse performance after the optimal point.**
```

**Why this is effective:** Demolishes the common misconception that "more connections = more throughput." The table showing performance degradation with too many connections is particularly compelling.

**Pair 3 (Advanced):**
```
Q: How do I diagnose connection pool exhaustion in production? My app intermittently hangs and I suspect it is waiting for database connections.

A: Connection pool exhaustion is one of the most common production issues. Here is how to diagnose and fix it:

**Symptom:** Requests hang for exactly the pool timeout duration, then fail with "could not obtain connection" or similar.

**Diagnosis step 1: Check active connections**
```sql
-- PostgreSQL: see all active connections
SELECT count(*), state, wait_event_type
FROM pg_stat_activity
WHERE datname = 'myapp'
GROUP BY state, wait_event_type;

-- If you see max_connections worth of 'idle in transaction':
-- You have a connection LEAK
```

**Diagnosis step 2: Find the leak**
```python
# Common leak patterns:

# LEAK 1: Exception before connection return
def bad_function():
    conn = pool.getconn()
    cursor = conn.cursor()
    cursor.execute("SELECT ...")  # If this throws, conn is never returned!
    pool.putconn(conn)

# FIX: Always use try/finally or context manager
def good_function():
    conn = pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ...")
    finally:
        pool.putconn(conn)  # Always returns, even on exception

# LEAK 2: Long-running transaction holds connection
def slow_function():
    conn = pool.getconn()
    cursor = conn.cursor()
    cursor.execute("BEGIN")
    cursor.execute("SELECT ...")
    external_api_call()  # 5 seconds! Connection held the whole time!
    cursor.execute("COMMIT")
    pool.putconn(conn)

# FIX: Do external calls OUTSIDE the transaction
def better_function():
    conn = pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ...")
        data = cursor.fetchall()
    finally:
        pool.putconn(conn)  # Return connection immediately

    result = external_api_call(data)  # No connection held
    return result
```

**Monitoring setup:**
```python
import logging
import time

class MonitoredPool:
    def __init__(self, real_pool, max_checkout_seconds=30):
        self._pool = real_pool
        self._max_checkout = max_checkout_seconds
        self._checkouts = {}
        self._lock = threading.Lock()

    def getconn(self):
        conn = self._pool.getconn()
        with self._lock:
            self._checkouts[id(conn)] = {
                "time": time.time(),
                "stack": traceback.format_stack(),
            }
        return conn

    def putconn(self, conn):
        with self._lock:
            checkout = self._checkouts.pop(id(conn), None)
            if checkout:
                duration = time.time() - checkout["time"]
                if duration > self._max_checkout:
                    logging.warning(
                        f"Connection held for {duration:.1f}s!\n"
                        f"Checked out at:\n{''.join(checkout['stack'])}"
                    )
        self._pool.putconn(conn)

    def health_check(self):
        with self._lock:
            now = time.time()
            for conn_id, info in self._checkouts.items():
                age = now - info["time"]
                if age > self._max_checkout:
                    logging.error(f"LEAKED connection held for {age:.0f}s")
```

**Prevention checklist:**
1. Always use try/finally or context managers for connections
2. Keep transactions as short as possible
3. Never do external I/O while holding a connection
4. Monitor checkout duration in production
5. Set pool timeout so exhaustion fails fast instead of hanging forever
```

**Why this is effective:** Covers the full diagnostic lifecycle -- symptoms, diagnosis, root cause patterns, monitoring. The MonitoredPool class is something the learner can drop into their codebase immediately.'''
    ),
    (
        "thinking/auto-datagen-schema-design",
        r'''Generate 3 high-quality training pairs that teach database schema design and normalization for real applications. For each pair, explain why it's effective training data.''',
        r'''<think>
Schema design is foundational but poorly taught:
1. Normalization is taught academically but practical trade-offs are ignored
2. Real schemas require balancing normalization with query performance
3. Common patterns: one-to-many, many-to-many, polymorphic associations, JSON columns

Progression: normalization basics -> practical patterns -> when to denormalize
</think>

Here are 3 training pairs for database schema design:

**Pair 1 (Beginner):**
```
Q: I am building an e-commerce app. How should I design the database schema for products, orders, and customers? I have everything in one big table right now.

A: Split your single table into properly normalized tables:

```sql
-- Customers (who buys)
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Products (what is sold)
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price_cents INTEGER NOT NULL,  -- Store money as cents, never floats!
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Orders (a customer's purchase)
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    total_cents INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Order items (products in an order) -- the many-to-many link
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL  -- Snapshot price at time of purchase!
);
```

**Why `unit_price_cents` in order_items?**
Product prices change. If you only reference the product, a $10 order becomes $15 when the price changes. Always snapshot the price at purchase time.

**Why `price_cents` instead of `DECIMAL` or `FLOAT`?**
- FLOAT: `0.1 + 0.2 = 0.30000000000000004` -- wrong for money!
- INTEGER cents: `10 + 20 = 30` -- always exact
- Display: divide by 100 in the application layer
```

**Why this is effective:** Starts from the real scenario (everything in one table), shows the correct schema with two critical lessons (snapshot pricing, integer money) that most tutorials miss.

**Pair 2 (Intermediate):**
```
Q: I have a users table and users can have multiple addresses, phone numbers, and notification preferences. Should I create separate tables for each, or use a JSON column?

A: **It depends on how you query the data.** Here is the decision framework:

**Use separate tables when you need to:**
- Query/filter BY the related data
- Enforce constraints on the related data
- Join related data with other tables

```sql
-- Addresses: queried by city, used for shipping calculations
CREATE TABLE addresses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type VARCHAR(20) NOT NULL,  -- 'home', 'work', 'shipping'
    street TEXT NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(50),
    country VARCHAR(2) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id, type)  -- One address per type
);

-- You CAN query: "All users in New York"
SELECT u.* FROM users u
JOIN addresses a ON a.user_id = u.id
WHERE a.city = 'New York';
```

**Use JSON when:**
- Data is read/written as a whole blob
- No need to query individual fields
- Schema varies per user
- Data is only accessed through the parent row

```sql
-- Notification preferences: always read/written as a whole, never queried
ALTER TABLE users ADD COLUMN notification_prefs JSONB DEFAULT '{
    "email_marketing": true,
    "email_transactional": true,
    "sms_alerts": false,
    "push_notifications": true
}'::jsonb;

-- Read: just grab the JSON
SELECT notification_prefs FROM users WHERE id = 42;

-- Update one field:
UPDATE users
SET notification_prefs = jsonb_set(notification_prefs, '{sms_alerts}', 'true')
WHERE id = 42;
```

**Decision table:**
| Data type | Separate table | JSON column |
|-----------|---------------|-------------|
| Addresses | YES -- queried by city/country | No |
| Phone numbers | YES -- need to enforce format | No |
| Notification prefs | No | YES -- blob read/write |
| UI settings (theme, layout) | No | YES -- opaque to backend |
| Order history | YES -- complex queries needed | No |
| Feature flags per user | Maybe | YES -- if simple toggles |
```

**Why this is effective:** Instead of dogmatically saying "always normalize" or "always use JSON," it teaches the decision framework based on query patterns. The table gives a quick reference for common cases.

**Pair 3 (Advanced):**
```
Q: When should I intentionally denormalize my database? I have been taught that normalization is always correct, but my queries are getting complex and slow.

A: Denormalization is a deliberate trade-off: faster reads at the cost of harder writes.

**When denormalization is the RIGHT choice:**

**Case 1: Computed aggregates that are queried frequently**
```sql
-- NORMALIZED (correct but slow):
-- "How many orders does each customer have?"
SELECT c.id, c.name, COUNT(o.id) as order_count, SUM(o.total_cents) as total_spent
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name;
-- Scans entire orders table every time

-- DENORMALIZED (fast read, more complex write):
ALTER TABLE customers ADD COLUMN order_count INTEGER DEFAULT 0;
ALTER TABLE customers ADD COLUMN total_spent_cents BIGINT DEFAULT 0;

-- Update on every new order (trigger or application code):
CREATE FUNCTION update_customer_stats() RETURNS TRIGGER AS $$
BEGIN
    UPDATE customers
    SET order_count = order_count + 1,
        total_spent_cents = total_spent_cents + NEW.total_cents
    WHERE id = NEW.customer_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_order_stats
    AFTER INSERT ON orders
    FOR EACH ROW EXECUTE FUNCTION update_customer_stats();

-- Now: SELECT name, order_count, total_spent_cents FROM customers WHERE id = 42;
-- Instant, no join needed.
```

**Case 2: Snapshot data that must not change**
```sql
-- When an order is placed, copy the shipping address INTO the order.
-- Even if the customer later changes their address, the order
-- records WHERE it was shipped.

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    -- Denormalized snapshot:
    shipping_name TEXT NOT NULL,
    shipping_street TEXT NOT NULL,
    shipping_city TEXT NOT NULL,
    shipping_country TEXT NOT NULL,
    shipping_postal TEXT NOT NULL
);
```

**Case 3: Materialized views for complex reports**
```sql
-- Instead of running a 12-table join for the dashboard:
CREATE MATERIALIZED VIEW dashboard_stats AS
SELECT
    date_trunc('day', o.created_at) as day,
    COUNT(DISTINCT o.customer_id) as unique_customers,
    COUNT(o.id) as order_count,
    SUM(o.total_cents) as revenue_cents
FROM orders o
GROUP BY 1;

-- Refresh periodically (not real-time, but fast):
REFRESH MATERIALIZED VIEW CONCURRENTLY dashboard_stats;

-- Dashboard query: instant
SELECT * FROM dashboard_stats WHERE day >= CURRENT_DATE - 30;
```

**Denormalization decision checklist:**
| Question | If YES | If NO |
|----------|--------|-------|
| Is the query too slow with joins? | Consider denormalization | Keep normalized |
| Is the data read 100x more than written? | Denormalize | Keep normalized |
| Can you tolerate slightly stale data? | Use materialized views | Keep normalized |
| Must the data NEVER change (snapshot)? | Copy into the row | Reference with FK |
| Can you maintain consistency via triggers? | Denormalize with triggers | Keep normalized |
```

**Why this is effective:** Shows that denormalization is a deliberate engineering decision, not a mistake. Each case has a clear justification, concrete SQL, and a decision checklist the learner can apply to their own schemas.'''
    ),
    (
        "thinking/auto-datagen-query-antipatterns",
        r'''Generate 3 high-quality training pairs that teach database query anti-patterns and their fixes. For each pair, explain why it's effective training data.''',
        r'''<think>
Query anti-patterns are responsible for most production database issues:
1. N+1 queries -- the most common ORM problem
2. SELECT * when you need 2 columns
3. Missing WHERE clauses, unbounded queries

Progression: identifying N+1 -> fixing ORM patterns -> recognizing subtle anti-patterns
</think>

Here are 3 training pairs for database query anti-patterns:

**Pair 1 (Beginner):**
```
Q: My page loads in 5 seconds and I see 101 database queries in the debug toolbar. I only have 100 blog posts. What is going on?

A: You have the **N+1 query problem** -- the most common ORM performance killer.

```python
# THE PROBLEM (N+1 queries):
posts = Post.objects.all()  # Query 1: SELECT * FROM posts
for post in posts:
    print(post.author.name)  # Query 2-101: SELECT * FROM authors WHERE id = ?
# Total: 1 + 100 = 101 queries!

# Each post.author triggers a SEPARATE database query because the ORM
# loads authors lazily (on access, not upfront).
```

**The fix: Eager loading**

```python
# Django: select_related (foreign key, one query with JOIN)
posts = Post.objects.select_related('author').all()
# Query: SELECT posts.*, authors.* FROM posts JOIN authors ON ...
# Total: 1 query!

# Django: prefetch_related (many-to-many, two queries)
posts = Post.objects.prefetch_related('tags').all()
# Query 1: SELECT * FROM posts
# Query 2: SELECT * FROM tags WHERE post_id IN (1, 2, 3, ...)
# Total: 2 queries regardless of how many posts!
```

```python
# SQLAlchemy equivalent:
from sqlalchemy.orm import joinedload, selectinload

# JOIN loading:
posts = session.query(Post).options(joinedload(Post.author)).all()

# Subquery loading:
posts = session.query(Post).options(selectinload(Post.tags)).all()
```

**Impact:**
| Metric | N+1 (before) | Eager load (after) |
|--------|-------------|-------------------|
| Queries | 101 | 1-2 |
| Load time | 5 seconds | 50ms |
| DB connections used | 101 | 1-2 |
```

**Why this is effective:** Starts from the symptom the developer sees (101 queries in debug toolbar), explains the root cause with exact code, and shows the fix for two major ORMs.

**Pair 2 (Intermediate):**
```
Q: My query is correct but painfully slow. Here it is:

```sql
SELECT * FROM orders
WHERE YEAR(created_at) = 2024
AND MONTH(created_at) = 3;
```

What am I doing wrong?

A: You have **function-on-column**, which prevents index usage. The database cannot use an index on `created_at` when you wrap it in a function.

```sql
-- BAD: Function on column -- full table scan
SELECT * FROM orders WHERE YEAR(created_at) = 2024 AND MONTH(created_at) = 3;
-- The index on created_at is USELESS because YEAR() transforms every value

-- GOOD: Range comparison -- uses index
SELECT * FROM orders
WHERE created_at >= '2024-03-01'
AND created_at < '2024-04-01';
-- The index on created_at works perfectly
```

**Other common function-on-column anti-patterns:**

```sql
-- BAD: LOWER() prevents index
SELECT * FROM users WHERE LOWER(email) = 'alice@example.com';
-- FIX 1: Use a functional index
CREATE INDEX idx_users_email_lower ON users(LOWER(email));
-- FIX 2: Store normalized data
-- Always store emails as lowercase in the first place

-- BAD: COALESCE prevents index
SELECT * FROM products WHERE COALESCE(category, 'none') = 'electronics';
-- FIX: Use IS NOT NULL + equality
SELECT * FROM products WHERE category = 'electronics';

-- BAD: Concatenation prevents index
SELECT * FROM users WHERE first_name || ' ' || last_name = 'John Smith';
-- FIX: Search on individual columns
SELECT * FROM users WHERE first_name = 'John' AND last_name = 'Smith';

-- BAD: Type casting prevents index
SELECT * FROM orders WHERE order_id::text = '12345';
-- FIX: Compare with the correct type
SELECT * FROM orders WHERE order_id = 12345;
```

**The rule:** Never apply a function to an indexed column in a WHERE clause. Transform the VALUE you are comparing against, not the column.
```

**Why this is effective:** Shows multiple variations of the same anti-pattern with fixes. The golden rule at the end is a principle the learner can apply to any query they write.

**Pair 3 (Advanced):**
```
Q: What are the most dangerous query anti-patterns that can take down a production database?

A: These patterns can cause outages:

**Anti-pattern 1: Unbounded queries**
```sql
-- DANGEROUS: No LIMIT, no WHERE on a 50-million row table
SELECT * FROM events;
-- Transfers gigabytes of data, exhausts memory, kills the connection

-- FIX: Always paginate
SELECT * FROM events WHERE id > :last_seen_id ORDER BY id LIMIT 100;
```

**Anti-pattern 2: SELECT FOR UPDATE on too many rows**
```sql
-- DANGEROUS: Locks thousands of rows
BEGIN;
SELECT * FROM orders WHERE status = 'pending' FOR UPDATE;
-- Every other query touching ANY of these rows is now BLOCKED
-- If your transaction is slow, the entire app freezes

-- FIX: Lock minimal rows with SKIP LOCKED
SELECT * FROM orders WHERE status = 'pending'
FOR UPDATE SKIP LOCKED LIMIT 10;
-- Only locks 10 rows, skips already-locked ones
```

**Anti-pattern 3: Implicit full cartesian join**
```sql
-- DANGEROUS: Missing JOIN condition
SELECT * FROM orders, order_items;
-- If orders has 100K rows and order_items has 1M rows:
-- Result = 100K * 1M = 100 BILLION rows. Database dies.

-- FIX: Always use explicit JOIN with ON clause
SELECT * FROM orders o JOIN order_items oi ON oi.order_id = o.id;
```

**Anti-pattern 4: Long-running transactions**
```sql
-- DANGEROUS: Transaction open for minutes
BEGIN;
SELECT * FROM users WHERE id = 1;  -- Holds read lock
-- ... application does 30 seconds of processing ...
UPDATE users SET name = 'Alice' WHERE id = 1;
COMMIT;

-- During those 30 seconds:
-- PostgreSQL: prevents VACUUM, table bloats
-- MySQL: blocks other writes on the row

-- FIX: Keep transactions under 1 second
-- Do processing OUTSIDE the transaction
data = fetch_from_db()  -- Short transaction
result = process(data)  -- No transaction
save_to_db(result)      -- Short transaction
```

**Anti-pattern 5: LIKE with leading wildcard**
```sql
-- DANGEROUS: Full table scan, cannot use any index
SELECT * FROM products WHERE name LIKE '%widget%';

-- FIX: Use full-text search
-- PostgreSQL:
SELECT * FROM products WHERE to_tsvector('english', name) @@ to_tsquery('widget');
CREATE INDEX idx_products_fts ON products USING GIN(to_tsvector('english', name));
```

**Severity ranking:**
| Anti-pattern | Risk level | Detection |
|-------------|------------|-----------|
| Unbounded query | Can crash app | Monitor query result sizes |
| Cartesian join | Can crash database | Review all queries without explicit JOIN |
| Long transactions | Gradual degradation | Monitor transaction duration |
| SELECT FOR UPDATE (wide) | Sudden lock contention | Monitor lock waits |
| Leading wildcard LIKE | Slow queries | EXPLAIN all search queries |
```

**Why this is effective:** These are the anti-patterns that cause real production outages. The severity ranking helps the learner prioritize what to check first in their own codebase.'''
    ),
    (
        "thinking/auto-datagen-migration-strategies",
        r'''Generate 3 high-quality training pairs that teach database migration strategies for production systems. For each pair, explain why it's effective training data.''',
        r'''<think>
Database migrations are high-risk production operations:
1. Schema changes can lock tables for minutes
2. Data migrations can corrupt or lose data
3. Rollback is often impossible after data transformation

Progression: safe schema changes -> zero-downtime migrations -> data migration patterns
</think>

Here are 3 training pairs for database migration strategies:

**Pair 1 (Beginner):**
```
Q: I need to add a new column to a table with 10 million rows in production. How do I do this without downtime?

A: Adding a nullable column without a default is instant in PostgreSQL:

```sql
-- SAFE: Instant, no table lock (PostgreSQL)
ALTER TABLE orders ADD COLUMN tracking_number TEXT;
-- This is a metadata-only change. No rows are rewritten.

-- DANGEROUS: Locks table while rewriting ALL rows
ALTER TABLE orders ADD COLUMN tracking_number TEXT DEFAULT 'none';
-- PostgreSQL 11+ makes this instant too, but older versions rewrite every row!

-- Safe way to add a column with a default on older PostgreSQL:
ALTER TABLE orders ADD COLUMN tracking_number TEXT;  -- Step 1: add nullable
ALTER TABLE orders ALTER COLUMN tracking_number SET DEFAULT 'none';  -- Step 2: set default for new rows
UPDATE orders SET tracking_number = 'none' WHERE tracking_number IS NULL;  -- Step 3: backfill in batches
```

**Backfill in batches to avoid locking:**
```sql
-- Do NOT update all 10M rows at once:
UPDATE orders SET tracking_number = 'none' WHERE tracking_number IS NULL;
-- This locks the table for minutes!

-- DO update in small batches:
DO $$
DECLARE
    batch_size INT := 10000;
    affected INT;
BEGIN
    LOOP
        UPDATE orders SET tracking_number = 'none'
        WHERE id IN (
            SELECT id FROM orders WHERE tracking_number IS NULL LIMIT batch_size
        );
        GET DIAGNOSTICS affected = ROW_COUNT;
        EXIT WHEN affected = 0;
        PERFORM pg_sleep(0.1);  -- Brief pause to reduce lock contention
    END LOOP;
END $$;
```
```

**Why this is effective:** Distinguishes between safe and dangerous operations with a concrete batch migration pattern. The pause between batches is a crucial production technique.

**Pair 2 (Intermediate):**
```
Q: I need to rename a column in production. How do I do this without breaking the application?

A: You cannot rename a column atomically across application and database. Use a multi-step process:

```
Step 1: Add new column
  ALTER TABLE users ADD COLUMN display_name TEXT;

Step 2: Deploy code that writes to BOTH columns
  -- Application writes to both old and new:
  UPDATE users SET name = 'Alice', display_name = 'Alice' WHERE id = 42;

Step 3: Backfill old data
  UPDATE users SET display_name = name WHERE display_name IS NULL;

Step 4: Deploy code that reads from NEW column
  -- Application now reads display_name instead of name

Step 5: Deploy code that writes ONLY to new column
  -- Application stops writing to old column

Step 6: Drop old column (after verifying everything works)
  ALTER TABLE users DROP COLUMN name;
```

**Timeline:**
```
Day 1: Steps 1-2 (add column, dual-write deploy)
Day 2: Step 3 (backfill)
Day 3: Step 4 (read from new column deploy)
Day 7: Step 5 (stop writing old column)
Day 14: Step 6 (drop old column after confidence period)
```

Each step is independently deployable and rollback-safe.
```

**Why this is effective:** Shows the complete multi-step migration process that production systems require. Each step is safe to roll back independently.

**Pair 3 (Advanced):**
```
Q: I need to split one table into two tables in production (decomposing a monolithic table). How do I do this without downtime or data loss?

A: Use the expand-migrate-contract pattern:

```
Phase 1: EXPAND (add new tables, keep old table)
  -- Create new tables
  CREATE TABLE user_profiles (
      user_id INTEGER PRIMARY KEY REFERENCES users(id),
      bio TEXT,
      avatar_url TEXT,
      website TEXT
  );

  -- Deploy: application writes to BOTH old and new tables
  -- Old table: still the source of truth for reads
  -- New table: receives all writes (dual-write)

Phase 2: MIGRATE (copy existing data)
  -- Backfill new table from old table
  INSERT INTO user_profiles (user_id, bio, avatar_url, website)
  SELECT id, bio, avatar_url, website FROM users
  ON CONFLICT (user_id) DO NOTHING;  -- Skip already-migrated rows

  -- Verify data consistency
  SELECT u.id FROM users u
  LEFT JOIN user_profiles p ON p.user_id = u.id
  WHERE p.user_id IS NULL;  -- Should return 0 rows

Phase 3: SWITCH (read from new tables)
  -- Deploy: application reads from new table
  -- Old table columns still exist but are not read

Phase 4: CONTRACT (remove old columns)
  -- After confidence period (1-2 weeks):
  ALTER TABLE users DROP COLUMN bio;
  ALTER TABLE users DROP COLUMN avatar_url;
  ALTER TABLE users DROP COLUMN website;
```

**Safety checks at each phase:**
| Phase | Rollback plan | Verification |
|-------|-------------|-------------|
| Expand | Drop new table | New table receives writes |
| Migrate | Re-run migration | Row counts match |
| Switch | Deploy old read code | Spot-check data equality |
| Contract | Cannot rollback! Backup first | All data in new table |
```

**Why this is effective:** Shows the complete expand-migrate-contract pattern with safety checks and rollback plans. The warning that the final step is irreversible emphasizes the need for verification.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
