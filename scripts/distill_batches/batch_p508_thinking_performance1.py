"""Phase 1C: Foundation Thinking — Performance Optimization (Part 1/4)
Database query optimization, N+1 problems, indexing strategies."""

PAIRS = [
    (
        "thinking/perf-n-plus-one-orm",
        "A Django view takes 8 seconds to load 50 blog posts with their authors and tags:\n\n```python\ndef blog_list(request):\n    posts = Post.objects.all()[:50]\n    data = []\n    for post in posts:\n        data.append({\n            'title': post.title,\n            'author': post.author.name,  # Separate query per post!\n            'tags': [t.name for t in post.tags.all()],  # Another query per post!\n        })\n    return JsonResponse({'posts': data})\n```\n\nDjango debug toolbar shows 151 queries. Explain and fix.",
        r'''<think>
Classic N+1 problem:
- 1 query for 50 posts
- 50 queries for post.author (one per post, lazy loading)
- 50 queries for post.tags.all() (one per post)
= 1 + 50 + 50 = 101 queries

Wait, 151 = 1 + 50 + 50*2? Maybe tags uses a junction table with two queries each. Or post.tags.all() hits the junction table. Regardless, it's N+1.

Fix: select_related for ForeignKey (author), prefetch_related for M2M (tags).
</think>

**N+1 query problem.** For 50 posts:
- 1 query: fetch all posts
- 50 queries: `post.author` (lazy-loaded ForeignKey)
- 100 queries: `post.tags.all()` (lazy-loaded M2M, 2 queries each)
= 151 total

## Fix: Eager Loading

```python
def blog_list(request):
    posts = (
        Post.objects
        .select_related('author')      # JOIN for ForeignKey (1 query)
        .prefetch_related('tags')       # Separate query for M2M (1 query)
        [:50]
    )
    data = [
        {
            'title': post.title,
            'author': post.author.name,   # No extra query — already loaded
            'tags': [t.name for t in post.tags.all()],  # From prefetch cache
        }
        for post in posts
    ]
    return JsonResponse({'posts': data})
```

**Before:** 151 queries, 8 seconds
**After:** 3 queries (posts + authors JOIN + tags), ~50ms

- **`select_related`** — uses SQL JOIN, best for ForeignKey/OneToOne (single-valued relations)
- **`prefetch_related`** — separate query + Python-side join, best for ManyToMany/reverse FK (multi-valued relations)'''
    ),
    (
        "thinking/perf-missing-index-slow-query",
        "A search query takes 12 seconds on a table with 10M rows:\n\n```sql\nSELECT * FROM orders\nWHERE customer_id = 12345\n  AND status = 'pending'\n  AND created_at > '2025-01-01'\nORDER BY created_at DESC\nLIMIT 20;\n```\n\n`EXPLAIN ANALYZE` shows:\n```\nSort  (cost=485231.00 rows=15234 width=312) (actual time=12456.123..12456.145 rows=20)\n  Sort Key: created_at DESC\n  ->  Seq Scan on orders  (cost=0.00..485012.00 rows=15234 width=312) (actual time=0.023..12234.567 rows=18)\n        Filter: ((customer_id = 12345) AND (status = 'pending') AND (created_at > '2025-01-01'))\n        Rows Removed by Filter: 9999982\n```\n\nDesign the optimal index.",
        r'''<think>
The EXPLAIN shows a sequential scan filtering 10M rows to find 18. No index is being used.

For optimal indexing, consider the query pattern:
- `customer_id = 12345` — equality filter (high selectivity)
- `status = 'pending'` — equality filter (low cardinality)
- `created_at > '2025-01-01'` — range filter
- `ORDER BY created_at DESC` — sorting
- `LIMIT 20` — only need first 20 sorted results

Index design rules:
1. Equality columns first (in any order): customer_id, status
2. Range/sort column last: created_at
3. If the ORDER BY matches the range column direction, the DB can use the index for both filtering and sorting

Optimal index: `(customer_id, status, created_at DESC)`

With this index:
- B-tree navigates to customer_id=12345, status='pending'
- Scans backward (DESC) from the most recent date
- Stops after 20 rows (LIMIT)
- No sort needed — index is already in the right order

Could also use a covering index (INCLUDE) to avoid table lookups.
</think>

**Sequential scan on 10M rows** — no index is being used. The DB examines every row, filters 9,999,982, and sorts the remaining 18.

## Optimal Index Design

```sql
-- Equality columns first, range/sort column last
CREATE INDEX idx_orders_customer_status_date
ON orders (customer_id, status, created_at DESC);
```

**Why this order:**
1. **`customer_id`** (equality) — narrows from 10M to ~10K rows
2. **`status`** (equality) — narrows further to ~100 rows
3. **`created_at DESC`** (range + sort) — index is pre-sorted, so ORDER BY is free and LIMIT 20 stops early

**After index:**
```
Limit  (rows=20)
  ->  Index Scan Backward on idx_orders_customer_status_date
        Index Cond: (customer_id = 12345 AND status = 'pending' AND created_at > '2025-01-01')
```

**Time: 12 seconds → <1ms**

**Covering index** (avoids table lookup entirely):
```sql
CREATE INDEX idx_orders_covering
ON orders (customer_id, status, created_at DESC)
INCLUDE (order_total, item_count);  -- Add columns used in SELECT
```

**Index design rules:**
1. Equality columns before range columns
2. Put the column used in ORDER BY as the last indexed column
3. Match the sort direction (DESC) in the index
4. INCLUDE frequently selected columns for covering scans'''
    ),
    (
        "thinking/perf-count-vs-exists",
        "An API checks if a user has any unread notifications. The query takes 500ms:\n\n```python\ndef has_unread_notifications(user_id):\n    count = Notification.objects.filter(\n        user_id=user_id,\n        read=False\n    ).count()\n    return count > 0\n\n# Called on EVERY page load\n```\n\nThe user has 50,000 unread notifications. Why is this slow?",
        r'''<think>
`count()` counts ALL 50,000 matching rows. But we only need to know if there's at least one. `EXISTS` short-circuits after finding the first match.
</think>

**`count()` scans all 50,000 rows** just to check if there's at least one. That's 49,999 unnecessary row reads.

## Fix: Use `exists()` — Short-Circuits After First Match

```python
def has_unread_notifications(user_id):
    return Notification.objects.filter(
        user_id=user_id,
        read=False
    ).exists()  # Stops at first match
```

**SQL difference:**
```sql
-- count(): scans all 50,000 rows
SELECT COUNT(*) FROM notifications WHERE user_id = 123 AND read = false;

-- exists(): stops at row 1
SELECT 1 FROM notifications WHERE user_id = 123 AND read = false LIMIT 1;
```

**500ms → <1ms.** Same result, orders of magnitude faster for users with many unread notifications. Always use `exists()` for boolean checks, never `count() > 0`.'''
    ),
    (
        "thinking/perf-pagination-offset-vs-cursor",
        "Paginating a large table gets slower on later pages. Page 1 takes 5ms, page 1000 takes 8 seconds:\n\n```python\ndef list_orders(page, page_size=20):\n    offset = (page - 1) * page_size\n    orders = db.execute(\n        'SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?',\n        (page_size, offset)\n    ).fetchall()\n    return orders\n\n# Page 1000: OFFSET 19980, LIMIT 20\n# DB must scan and discard 19,980 rows before returning 20\n```",
        r'''<think>
OFFSET-based pagination requires the database to scan (and discard) all rows before the offset. OFFSET 19980 means reading 20,000 rows to return 20.

Cursor-based pagination (keyset pagination) uses a WHERE clause to skip directly to the right position using the index.
</think>

**OFFSET pagination is O(offset)** — the database scans and discards all rows before the offset. Page 1000 scans 20,000 rows to return 20.

## Fix: Cursor-Based Pagination (Keyset)

```python
def list_orders(cursor=None, page_size=20):
    if cursor:
        # Jump directly to the position using index
        orders = db.execute(
            'SELECT * FROM orders '
            'WHERE created_at < ? '
            'ORDER BY created_at DESC '
            'LIMIT ?',
            (cursor, page_size)
        ).fetchall()
    else:
        orders = db.execute(
            'SELECT * FROM orders ORDER BY created_at DESC LIMIT ?',
            (page_size,)
        ).fetchall()

    next_cursor = orders[-1]['created_at'] if orders else None
    return {'orders': orders, 'next_cursor': next_cursor}
```

**For non-unique sort columns, use a composite cursor:**
```python
# When multiple orders can have the same created_at
'WHERE (created_at, id) < (?, ?) ORDER BY created_at DESC, id DESC LIMIT ?'
```

**Performance comparison:**
| Page | OFFSET | Cursor |
|------|--------|--------|
| 1 | 5ms | 5ms |
| 100 | 800ms | 5ms |
| 1000 | 8000ms | 5ms |

Cursor pagination is **O(1)** regardless of position — it uses the index to jump directly to the right row.'''
    ),
    (
        "thinking/perf-select-star-columns",
        "An endpoint that only needs user names and emails takes 2 seconds. The table has a large JSON `profile_data` column (avg 50KB per row):\n\n```python\ndef get_user_list():\n    users = db.execute('SELECT * FROM users LIMIT 100').fetchall()\n    return [{'name': u['name'], 'email': u['email']} for u in users]\n```",
        r'''<think>
`SELECT *` fetches ALL columns including the 50KB profile_data. 100 rows × 50KB = 5MB transferred from DB to application, only to discard the profile_data immediately.
</think>

**`SELECT *` fetches the 50KB `profile_data` column for all 100 rows** — 5MB of data transferred from DB to app, then immediately discarded.

## Fix: Select Only Needed Columns

```python
def get_user_list():
    users = db.execute('SELECT name, email FROM users LIMIT 100').fetchall()
    return [{'name': u['name'], 'email': u['email']} for u in users]
```

**Before:** ~5MB transferred (100 × 50KB per row), 2 seconds
**After:** ~10KB transferred (100 × 100 bytes), <10ms

**Rule:** Never use `SELECT *` in production code. Always specify the columns you need. This is especially critical when tables have large text/JSON/blob columns.'''
    ),
    (
        "thinking/perf-query-in-loop",
        "A report generator takes 45 seconds. Profiling shows 10,000 individual database queries:\n\n```python\ndef generate_monthly_report(month):\n    orders = Order.objects.filter(created_at__month=month)\n    report = []\n    \n    for order in orders:  # 10,000 orders\n        customer = Customer.objects.get(id=order.customer_id)\n        items = OrderItem.objects.filter(order_id=order.id)\n        \n        total = sum(item.price * item.quantity for item in items)\n        \n        report.append({\n            'order_id': order.id,\n            'customer_name': customer.name,\n            'total': total,\n            'item_count': items.count(),  # ANOTHER query!\n        })\n    return report\n```",
        r'''<think>
For 10,000 orders:
- 1 query: all orders
- 10,000 queries: Customer.objects.get() per order
- 10,000 queries: OrderItem.objects.filter() per order
- 10,000 queries: items.count() per order
= 1 + 30,000 = 30,001 queries

Fix: use select_related, prefetch_related, and annotations to do it in 2-3 queries.
</think>

**30,001 queries** (1 + 10K customers + 10K items + 10K counts). Each query has network round-trip overhead.

## Fix: Eager Loading + Database Aggregation

```python
from django.db.models import Sum, Count, F

def generate_monthly_report(month):
    orders = (
        Order.objects
        .filter(created_at__month=month)
        .select_related('customer')  # JOIN customers (0 extra queries)
        .annotate(
            total=Sum(F('items__price') * F('items__quantity')),
            item_count=Count('items'),
        )
    )

    report = [
        {
            'order_id': order.id,
            'customer_name': order.customer.name,  # From JOIN
            'total': order.total,      # From annotation
            'item_count': order.item_count,  # From annotation
        }
        for order in orders
    ]
    return report
```

**Before:** 30,001 queries, 45 seconds
**After:** 1 query (with JOINs and aggregation), ~200ms

**Rule:** Let the database do the work. JOINs, aggregations, and annotations are orders of magnitude faster than Python loops with individual queries.'''
    ),
    (
        "thinking/perf-missing-db-connection-pooling",
        "Under load, our FastAPI app's response times spike from 50ms to 5 seconds. Each request creates a new database connection:\n\n```python\nimport psycopg2\nfrom fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/api/users/{user_id}')\nasync def get_user(user_id: int):\n    conn = psycopg2.connect(  # New TCP connection + TLS handshake every request!\n        host='db.internal',\n        dbname='myapp',\n        user='app',\n        password='secret',\n    )\n    try:\n        with conn.cursor() as cur:\n            cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))\n            user = cur.fetchone()\n        return {'user': user}\n    finally:\n        conn.close()\n```",
        r'''<think>
Creating a new TCP connection per request involves:
1. TCP 3-way handshake
2. TLS handshake (if SSL)
3. PostgreSQL authentication protocol
4. Connection setup queries

This can be 50-200ms per connection. Under load, the DB also runs out of connection slots (default max_connections=100).

Fix: connection pool. Reuse connections across requests.
</think>

**Each request creates a new TCP + TLS + auth connection** (~50-200ms overhead). Under load, this also exhausts PostgreSQL's `max_connections` (default 100).

## Fix: Connection Pool

```python
from fastapi import FastAPI
from psycopg2 import pool
from contextlib import contextmanager

app = FastAPI()

# Create pool once at startup — connections are reused
db_pool = pool.ThreadedConnectionPool(
    minconn=5,
    maxconn=20,
    host='db.internal',
    dbname='myapp',
    user='app',
    password='secret',
)

@contextmanager
def get_db():
    conn = db_pool.getconn()  # ~0ms — reuses existing connection
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        db_pool.putconn(conn)  # Return to pool, don't close

@app.get('/api/users/{user_id}')
async def get_user(user_id: int):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
            user = cur.fetchone()
    return {'user': user}

@app.on_event('shutdown')
def shutdown():
    db_pool.closeall()
```

**Before:** 50-200ms connection overhead per request, max ~100 concurrent requests
**After:** ~0ms connection overhead (reused), pool manages connections efficiently

For async FastAPI, use `asyncpg` with its built-in pool for even better performance.'''
    ),
    (
        "thinking/perf-slow-aggregation-materialized-view",
        "A dashboard query aggregates sales data across millions of rows. It takes 30 seconds and runs on every page load:\n\n```sql\nSELECT \n    DATE_TRUNC('day', created_at) as day,\n    category,\n    COUNT(*) as order_count,\n    SUM(total) as revenue,\n    AVG(total) as avg_order\nFROM orders\nWHERE created_at > NOW() - INTERVAL '90 days'\nGROUP BY day, category\nORDER BY day DESC, revenue DESC;\n```\n\nThe table has 50M rows. Running this on every dashboard load is killing the database.",
        r'''<think>
Aggregating 50M rows (even with a 90-day filter, that could still be millions) on every page load is wasteful. The data doesn't change that frequently.

Options:
1. Materialized view — precomputed, refreshed periodically
2. Summary table — updated incrementally
3. Caching layer — Redis cache with TTL
</think>

**Aggregating millions of rows on every page load is wasteful.** Sales data from yesterday doesn't change — why recompute it every request?

## Fix: Materialized View + Incremental Refresh

```sql
-- Create materialized view (precomputed)
CREATE MATERIALIZED VIEW daily_sales_summary AS
SELECT
    DATE_TRUNC('day', created_at) as day,
    category,
    COUNT(*) as order_count,
    SUM(total) as revenue,
    AVG(total) as avg_order
FROM orders
WHERE created_at > NOW() - INTERVAL '90 days'
GROUP BY day, category
ORDER BY day DESC, revenue DESC;

-- Index for fast dashboard queries
CREATE INDEX idx_sales_summary_day ON daily_sales_summary (day DESC);

-- Refresh periodically (cron job every 5 minutes)
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_sales_summary;
```

```python
# Dashboard query — reads precomputed data
def get_dashboard_data():
    return db.execute(
        'SELECT * FROM daily_sales_summary ORDER BY day DESC, revenue DESC'
    ).fetchall()
    # Reads ~270 rows (90 days × 3 categories) instead of aggregating millions
```

**Performance:**
- Before: 30 seconds per page load, hammers the database
- After: <5ms per page load, refreshed every 5 minutes

**`CONCURRENTLY`** allows reads during refresh — no downtime for dashboard users.'''
    ),
    (
        "thinking/perf-json-column-indexing",
        "Filtering on a JSONB column is slow despite having a GIN index:\n\n```sql\n-- Table: events (50M rows)\n-- Column: metadata JSONB\n-- Index: CREATE INDEX idx_events_metadata ON events USING GIN (metadata);\n\n-- This query is slow (3 seconds):\nSELECT * FROM events \nWHERE metadata->>'event_type' = 'purchase'\n  AND metadata->>'country' = 'US'\nORDER BY created_at DESC \nLIMIT 50;\n\n-- EXPLAIN shows the GIN index is NOT used\n```",
        r'''<think>
GIN index on the full JSONB column supports containment operators (`@>`, `?`, `?|`, `?&`), NOT the `->>'key' = 'value'` extraction operator. The `->>` operator extracts text, which the GIN index can't efficiently filter.

Fix: either use the containment operator `@>` which the GIN index supports, or create a B-tree expression index on the specific extracted values.
</think>

**GIN indexes support containment operators (`@>`), not text extraction (`->>`).**  The query uses `->>` which bypasses the GIN index entirely.

## Fix Options

**Option 1: Use containment operator (works with existing GIN index)**
```sql
SELECT * FROM events
WHERE metadata @> '{"event_type": "purchase", "country": "US"}'
ORDER BY created_at DESC
LIMIT 50;
```

**Option 2: Expression index on extracted fields (faster for known query patterns)**
```sql
-- B-tree index on specific extracted fields
CREATE INDEX idx_events_type_country
ON events ((metadata->>'event_type'), (metadata->>'country'), created_at DESC);

-- Original query now uses the B-tree index
SELECT * FROM events
WHERE metadata->>'event_type' = 'purchase'
  AND metadata->>'country' = 'US'
ORDER BY created_at DESC
LIMIT 50;
```

**Option 2 is faster** for this specific query pattern because B-tree is more efficient for equality + ordering than GIN. But GIN is more flexible for ad-hoc queries across any JSON key.

**Rule:** GIN indexes work with `@>` (containment), `?` (key exists), `?&` (all keys exist). For `->>` extraction, create B-tree expression indexes on the specific paths you query.'''
    ),
    (
        "thinking/perf-unbatched-inserts",
        "Importing 100,000 records takes 45 minutes. Each record is inserted individually:\n\n```python\ndef import_records(records):\n    for record in records:  # 100,000 records\n        db.execute(\n            'INSERT INTO products (name, sku, price, category) VALUES (?, ?, ?, ?)',\n            (record['name'], record['sku'], record['price'], record['category'])\n        )\n        db.commit()  # Commit per row!\n```",
        r'''<think>
Two problems:
1. Individual INSERT per row — 100K network round trips
2. Commit per row — 100K fsync operations

Fix: batch inserts + single commit. Or use COPY/bulk insert.
</think>

**100,000 individual INSERT + COMMIT operations** — each one requires a network round trip and an fsync to disk. That's ~27ms per record × 100K = 45 minutes.

## Fix: Batch Insert + Single Commit

```python
def import_records(records, batch_size=1000):
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        db.executemany(
            'INSERT INTO products (name, sku, price, category) VALUES (?, ?, ?, ?)',
            [(r['name'], r['sku'], r['price'], r['category']) for r in batch]
        )
    db.commit()  # Single commit at the end
```

**For PostgreSQL, use COPY (fastest possible):**
```python
import io
import csv

def import_records_fast(records, conn):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter='\t')
    for r in records:
        writer.writerow([r['name'], r['sku'], r['price'], r['category']])
    buf.seek(0)

    with conn.cursor() as cur:
        cur.copy_from(buf, 'products', columns=('name', 'sku', 'price', 'category'))
    conn.commit()
```

**Performance:**
| Method | Time | Improvement |
|--------|------|-------------|
| Individual INSERT + COMMIT | 45 min | baseline |
| Batched executemany (1000) | 15 sec | 180x |
| COPY (PostgreSQL) | 3 sec | 900x |'''
    ),
    (
        "thinking/perf-orm-deferred-fields",
        "A Django API endpoint loads user profiles but only uses 3 of 20 fields. The query transfers 10MB of data:\n\n```python\ndef user_search(request):\n    query = request.GET['q']\n    users = User.objects.filter(name__icontains=query)[:100]\n    return JsonResponse({\n        'users': [\n            {'id': u.id, 'name': u.name, 'avatar_url': u.avatar_url}\n            for u in users\n        ]\n    })\n```\n\nThe User model has large fields: `bio` (TextField), `settings` (JSONField), `activity_log` (JSONField), plus 17 other columns.",
        r'''<think>
Django loads all fields by default. With large text/JSON fields, this transfers massive amounts of unnecessary data.

Fix: use `.only()` or `.values()` to select only needed fields.
</think>

Django loads all 20 columns by default. The large `bio`, `settings`, and `activity_log` fields are transferred but never used.

## Fix: Load Only What You Need

```python
def user_search(request):
    query = request.GET['q']
    users = (
        User.objects
        .filter(name__icontains=query)
        .only('id', 'name', 'avatar_url')  # Only these 3 columns
        [:100]
    )
    return JsonResponse({
        'users': [
            {'id': u.id, 'name': u.name, 'avatar_url': u.avatar_url}
            for u in users
        ]
    })
```

**Or use `.values()` for even less overhead (returns dicts, not model instances):**
```python
users = (
    User.objects
    .filter(name__icontains=query)
    .values('id', 'name', 'avatar_url')  # Returns list of dicts
    [:100]
)
return JsonResponse({'users': list(users)})
```

**Before:** ~10MB transferred (100 users × 100KB per row with all fields)
**After:** ~50KB transferred (100 users × 500 bytes for 3 fields)

`.values()` is fastest (no model instantiation), `.only()` is best when you need model methods.'''
    ),
    (
        "thinking/perf-lock-contention-counter",
        "A global counter using a database row causes lock contention under high concurrency:\n\n```python\ndef increment_page_views(page_id):\n    db.execute(\n        'UPDATE pages SET view_count = view_count + 1 WHERE id = ?',\n        (page_id,)\n    )\n    db.commit()\n```\n\nWith 1000 concurrent requests/second hitting the same page, response times spike to 5 seconds due to row-level lock contention.",
        r'''<think>
Every UPDATE acquires a row-level lock. With 1000 concurrent requests/sec on the same row, each request waits for all previous requests to commit. This creates a serialization bottleneck.

Fix: buffer the counter in Redis (atomic INCR, no locking) and flush to DB periodically.
</think>

Each `UPDATE` acquires an exclusive row lock. With 1000 concurrent requests on the same row, they serialize — each waits for the previous to commit.

## Fix: Buffer in Redis, Flush to DB

```python
import redis

r = redis.Redis()

def increment_page_views(page_id):
    # Redis INCR is atomic, no locking, ~0.1ms
    r.incr(f'pageviews:{page_id}')

# Periodic flush (every 10 seconds via background task)
def flush_page_views():
    keys = r.keys('pageviews:*')
    for key in keys:
        page_id = key.decode().split(':')[1]
        count = r.getdel(key)  # Atomic get and delete
        if count:
            db.execute(
                'UPDATE pages SET view_count = view_count + ? WHERE id = ?',
                (int(count), page_id)
            )
    db.commit()
```

**Before:** 1000 serialized DB writes/sec → 5 second response times
**After:** 1000 Redis INCR/sec (~0.1ms each) + 1 DB write every 10 seconds

**Alternative for PostgreSQL: advisory locks or INSERT with batch aggregation.**'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
