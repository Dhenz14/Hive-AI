"""Phase 4A: Self-Improvement — Training Data Generation (Part 12)

Generate and evaluate training pairs for performance optimization topics.
Each answer creates 3 graded training pairs with quality analysis.
"""

PAIRS = [
    (
        "thinking/auto-datagen-database-optimization",
        r'''Generate 3 high-quality training pairs that teach database query optimization. For each pair, explain why it's effective training data.''',
        r'''<think>
Database optimization is one of the highest-impact skills:
1. Understanding and using EXPLAIN to diagnose slow queries
2. Index design and selection
3. Common query anti-patterns

Progression: reading EXPLAIN output -> adding the right indexes -> rewriting queries for performance
</think>

Here are 3 training pairs for database optimization:

**Pair 1 (Beginner):**
```
Q: My database query is slow but I don't know why. Someone told me to use EXPLAIN but I don't understand the output. Can you help?

A: EXPLAIN shows you the database's plan for executing your query — where it looks for data and how much work it does.

**Start with your slow query:**
```sql
SELECT * FROM orders
WHERE user_id = 42 AND status = 'pending'
ORDER BY created_at DESC;
```

**Add EXPLAIN ANALYZE:**
```sql
EXPLAIN ANALYZE
SELECT * FROM orders
WHERE user_id = 42 AND status = 'pending'
ORDER BY created_at DESC;
```

**Reading the output:**
```
Seq Scan on orders  (cost=0.00..25432.00 rows=150 width=200) (actual time=45.2..312.5 rows=12 loops=1)
  Filter: ((user_id = 42) AND (status = 'pending'))
  Rows Removed by Filter: 500000
Sort  (cost=25435.00..25435.50 rows=150 width=200) (actual time=312.8..312.8 rows=12 loops=1)
  Sort Key: created_at DESC
Planning Time: 0.5 ms
Execution Time: 313.2 ms
```

**What this tells you:**
1. **Seq Scan** = reading EVERY row in the table (bad for large tables)
2. **Rows Removed by Filter: 500000** = it read 500K rows to find 12 (99.99% wasted)
3. **Execution Time: 313ms** = slow because of the full table scan

**The fix — add an index:**
```sql
CREATE INDEX idx_orders_user_status ON orders(user_id, status);
```

**After adding the index:**
```
Index Scan using idx_orders_user_status on orders  (cost=0.42..15.30 rows=12 width=200) (actual time=0.05..0.08 rows=12 loops=1)
Planning Time: 0.3 ms
Execution Time: 0.1 ms
```

**Speed improvement: 313ms -> 0.1ms (3000x faster!)**

**Key things to look for in EXPLAIN:**
| What you see | What it means | Fix |
|-------------|---------------|-----|
| Seq Scan | Full table scan | Add an index |
| Rows Removed by Filter: large number | Index missing or not used | Check index matches WHERE clause |
| Sort with high cost | Sorting without index | Add index on ORDER BY columns |
| Nested Loop with high loops | N+1 join pattern | Use hash join or add index |
```
*Why this is effective:* Makes EXPLAIN output approachable by translating database jargon into plain English with a concrete before/after showing dramatic improvement.

**Pair 2 (Intermediate):**
```
Q: I have indexes on my table but the query is still slow. How do I design better indexes?

A: Having indexes isn't enough — you need the RIGHT indexes for your queries. Here's how to think about index design:

**Rule 1: Index columns match your WHERE + ORDER BY:**
```sql
-- Your query:
SELECT * FROM orders
WHERE user_id = 42 AND status = 'pending'
ORDER BY created_at DESC
LIMIT 20;

-- Perfect index (covers WHERE + ORDER BY):
CREATE INDEX idx_orders_lookup ON orders(user_id, status, created_at DESC);

-- The database can: find user_id=42, filter status='pending', AND read in created_at order
-- without sorting. This is a "covering scan."
```

**Rule 2: Column order in composite indexes matters:**
```sql
-- Index on (user_id, status) helps these queries:
WHERE user_id = 42                        -- YES (uses first column)
WHERE user_id = 42 AND status = 'pending' -- YES (uses both columns)
WHERE status = 'pending'                  -- NO! (can't skip first column)

-- Think of it like a phone book: sorted by last name, then first name.
-- You can look up "Smith" but not "Alice" without scanning everything.
```

**Rule 3: Don't over-index:**
```sql
-- BAD: An index for every possible query
CREATE INDEX idx1 ON orders(user_id);
CREATE INDEX idx2 ON orders(status);
CREATE INDEX idx3 ON orders(user_id, status);
CREATE INDEX idx4 ON orders(user_id, created_at);
CREATE INDEX idx5 ON orders(status, created_at);
-- Each index slows down INSERT/UPDATE/DELETE!

-- GOOD: Fewest indexes that cover your actual queries
CREATE INDEX idx_orders_user_status_date ON orders(user_id, status, created_at DESC);
-- Covers: WHERE user_id=X, WHERE user_id=X AND status=Y, ORDER BY created_at
```

**Rule 4: Use covering indexes to avoid table lookups:**
```sql
-- If you only need specific columns:
SELECT user_id, total, created_at FROM orders WHERE user_id = 42;

-- A covering index includes ALL needed columns:
CREATE INDEX idx_covering ON orders(user_id) INCLUDE (total, created_at);
-- The database reads ONLY the index, never touches the table = much faster
```

**Index design checklist:**
1. Run EXPLAIN on your slow queries
2. Check which columns are in WHERE, ORDER BY, and SELECT
3. Create composite indexes matching the query pattern
4. Put equality conditions first, range conditions last
5. Monitor index usage: `SELECT * FROM pg_stat_user_indexes WHERE idx_scan = 0;`
```
*Why this is effective:* Goes beyond "add an index" to teach index DESIGN — column order, composite indexes, and covering indexes — which is what actually solves performance problems.

**Pair 3 (Advanced):**
```
Q: Our orders table has 50 million rows. Even with indexes, some queries are slow. How do we optimize at scale?

A: At 50M+ rows, you need to think beyond indexes. Here are scale-specific optimization strategies:

**1. Table partitioning — split one big table into many small ones:**
```sql
-- Partition by date range (most common for time-series data):
CREATE TABLE orders (
    id BIGSERIAL,
    user_id INT,
    total DECIMAL,
    created_at TIMESTAMPTZ
) PARTITION BY RANGE (created_at);

CREATE TABLE orders_2024_q1 PARTITION OF orders
    FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');
CREATE TABLE orders_2024_q2 PARTITION OF orders
    FOR VALUES FROM ('2024-04-01') TO ('2024-07-01');

-- Queries with WHERE created_at BETWEEN ... only scan relevant partitions
-- A query for January data scans 1 partition (3M rows) instead of all 50M
```

**2. Materialized views — precompute expensive aggregations:**
```sql
-- This query runs every time someone views the dashboard:
SELECT user_id, COUNT(*) as order_count, SUM(total) as total_spent
FROM orders
GROUP BY user_id;
-- On 50M rows: ~30 seconds

-- Precompute it:
CREATE MATERIALIZED VIEW user_order_stats AS
SELECT user_id, COUNT(*) as order_count, SUM(total) as total_spent
FROM orders
GROUP BY user_id;

CREATE UNIQUE INDEX ON user_order_stats(user_id);

-- Refresh periodically:
REFRESH MATERIALIZED VIEW CONCURRENTLY user_order_stats;
-- Query time: <1ms (reading precomputed results)
```

**3. Query rewriting — avoid common anti-patterns:**
```sql
-- SLOW: Correlated subquery (runs inner query for EACH outer row)
SELECT u.*, (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) as order_count
FROM users u;

-- FAST: JOIN with aggregation
SELECT u.*, COALESCE(o.order_count, 0) as order_count
FROM users u
LEFT JOIN (
    SELECT user_id, COUNT(*) as order_count FROM orders GROUP BY user_id
) o ON u.id = o.user_id;

-- SLOW: Using functions in WHERE (prevents index use)
SELECT * FROM orders WHERE EXTRACT(YEAR FROM created_at) = 2024;

-- FAST: Use range comparison (uses index)
SELECT * FROM orders
WHERE created_at >= '2024-01-01' AND created_at < '2025-01-01';

-- SLOW: SELECT * when you need 3 columns
SELECT * FROM orders WHERE user_id = 42;

-- FAST: Select only what you need
SELECT id, total, created_at FROM orders WHERE user_id = 42;
```

**4. Connection and query management:**
```python
# Use connection pooling (don't open/close per query):
from sqlalchemy import create_engine
engine = create_engine(
    "postgresql://...",
    pool_size=20,        # Keep 20 connections ready
    max_overflow=10,     # Allow 10 more under load
    pool_recycle=3600    # Recycle connections hourly
)

# Use LIMIT for paginated queries:
# NEVER: SELECT * FROM orders WHERE user_id = 42 (returns ALL orders)
# ALWAYS: SELECT * FROM orders WHERE user_id = 42 LIMIT 20 OFFSET 0
```

**Performance monitoring query:**
```sql
-- Find your slowest queries:
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```
```
*Why this is effective:* Covers the specific techniques needed at scale (partitioning, materialized views, query rewriting) that go far beyond basic indexing, with concrete SQL examples.'''
    ),
    (
        "thinking/auto-datagen-python-performance",
        r'''Generate 3 high-quality training pairs that teach Python-specific performance optimization. For each pair, explain why it's effective training data.''',
        r'''<think>
Python performance has specific patterns:
1. Choosing the right data structure (list vs set vs dict)
2. Avoiding common Python performance pitfalls
3. Profiling and optimizing hot paths

Progression: data structure choice -> avoiding anti-patterns -> profiling and optimization
</think>

Here are 3 training pairs for Python performance:

**Pair 1 (Beginner):**
```
Q: My Python script processes a list of 1 million items and takes 10 minutes. The main loop checks if each item exists in another list. How can I make it faster?

A: The most likely cause is using `in` on a list instead of a set. This is the most impactful performance fix in Python.

**The problem:**
```python
# SLOW: O(n) lookup for each check — O(n*m) total
blocklist = [...]  # 100,000 items
for item in items:  # 1,000,000 items
    if item not in blocklist:  # Scans ALL 100,000 items each time!
        process(item)

# Time: 100,000 * 1,000,000 = 100 billion operations!
```

**The fix:**
```python
# FAST: O(1) lookup — O(n) total
blocklist = set(blocklist)  # Convert ONCE — O(m)
for item in items:
    if item not in blocklist:  # Instant hash lookup!
        process(item)

# Time: 1,000,000 operations (100,000x faster)
```

**Data structure lookup times:**
| Operation | list | set | dict |
|-----------|------|-----|------|
| `x in collection` | O(n) slow | O(1) fast | O(1) fast |
| `collection[i]` | O(1) fast | N/A | O(1) fast |
| `collection.append(x)` | O(1) fast | N/A | N/A |
| `collection.add(x)` | N/A | O(1) fast | N/A |

**Rule of thumb:**
- Need to check membership? Use a `set`
- Need key-value lookup? Use a `dict`
- Need ordered sequence with index access? Use a `list`
- Need to add/remove from both ends? Use `collections.deque`

**Real-world impact:**
```python
import time

data = list(range(100_000))
check = list(range(50_000, 150_000))

# List membership: ~45 seconds
start = time.time()
result = [x for x in check if x in data]
print(f"List: {time.time() - start:.2f}s")

# Set membership: ~0.01 seconds
data_set = set(data)
start = time.time()
result = [x for x in check if x in data_set]
print(f"Set: {time.time() - start:.2f}s")
```
```
*Why this is effective:* Addresses the single most common Python performance mistake with a dramatic speedup that developers can apply immediately.

**Pair 2 (Intermediate):**
```
Q: I know about sets and dicts, but my Python code is still slower than I'd expect. What other performance pitfalls should I watch for?

A: Here are the top Python performance anti-patterns beyond data structures:

**1. String concatenation in loops:**
```python
# SLOW: Creates a new string object each iteration — O(n^2)
result = ""
for line in lines:
    result += line + "\n"

# FAST: Join at the end — O(n)
result = "\n".join(lines)

# Benchmark: 100K lines — concat: 5.2s, join: 0.003s
```

**2. Creating objects in tight loops:**
```python
# SLOW: Recompiling regex every iteration
import re
for text in texts:
    match = re.search(r'\d{3}-\d{4}', text)

# FAST: Compile once, reuse
pattern = re.compile(r'\d{3}-\d{4}')
for text in texts:
    match = pattern.search(text)
```

**3. Using global variable lookups:**
```python
# SLOW: Global and attribute lookups in tight loops
import math
def compute(values):
    results = []
    for v in values:
        results.append(math.sqrt(v))  # Looks up 'math' then 'sqrt' each time
    return results

# FAST: Local variable references
def compute(values):
    sqrt = math.sqrt  # Local reference (faster lookup)
    append = results.append
    results = []
    for v in values:
        append(sqrt(v))
    return results

# FASTEST: Use list comprehension (C-optimized loop)
def compute(values):
    return [math.sqrt(v) for v in values]
```

**4. Not using generators for large data:**
```python
# SLOW: Loads ALL data into memory
def get_all_lines(filename):
    return open(filename).readlines()  # 10GB file = 10GB in memory

# FAST: Process one line at a time
def get_all_lines(filename):
    with open(filename) as f:
        for line in f:
            yield line  # One line in memory at a time
```

**5. Using the wrong loop construct:**
```python
# SLOW: Manual loop
squares = []
for x in range(1000000):
    squares.append(x ** 2)

# FAST: List comprehension (2-3x faster)
squares = [x ** 2 for x in range(1000000)]

# FASTEST for numeric: NumPy (100x faster)
import numpy as np
squares = np.arange(1000000) ** 2
```

**Quick performance checklist:**
- [ ] Using `set` for membership tests?
- [ ] Using `str.join()` instead of `+=` for strings?
- [ ] Using list comprehensions instead of append loops?
- [ ] Compiling regex patterns once?
- [ ] Using generators for large datasets?
- [ ] Moved expensive operations outside loops?
```
*Why this is effective:* Catalogs the specific Python anti-patterns that cause slowdowns, with benchmarks showing the magnitude of each improvement.

**Pair 3 (Advanced):**
```
Q: I've optimized my data structures and loops, but my Python application is still too slow. How do I profile it to find the remaining bottlenecks?

A: Use profiling tools to measure where time is actually spent — don't guess.

**Step 1: cProfile for function-level profiling:**
```python
import cProfile
import pstats

# Profile your code:
cProfile.run('main()', 'profile_output')

# Analyze results:
stats = pstats.Stats('profile_output')
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions by cumulative time
```

Output:
```
   ncalls  tottime  cumtime  filename:lineno(function)
   1       0.001    15.234  main.py:1(main)
   50000   8.123    12.456  process.py:45(transform_record)
   50000   3.234    3.234   process.py:67(validate)
   1       0.890    0.890   db.py:12(load_data)
   150000  0.567    0.567   utils.py:89(clean_string)
```

Reading this: `transform_record` is called 50K times and takes 12.5s total — that's your bottleneck.

**Step 2: line_profiler for line-by-line analysis:**
```python
# pip install line_profiler
# Add @profile decorator to the hot function:

@profile
def transform_record(record):
    cleaned = clean_fields(record)       # Line 46
    validated = validate(cleaned)         # Line 47
    enriched = lookup_metadata(cleaned)   # Line 48
    return merge(validated, enriched)     # Line 49
```

```bash
kernprof -l -v script.py
```

Output:
```
Line #  Hits     Time  % Time  Line Contents
    46  50000   1.2s    9.6%   cleaned = clean_fields(record)
    47  50000   3.2s   25.7%   validated = validate(cleaned)
    48  50000   7.8s   62.6%   enriched = lookup_metadata(cleaned)
    49  50000   0.3s    2.4%   return merge(validated, enriched)
```

Now you know: `lookup_metadata` is 62.6% of the time. Focus there.

**Step 3: Optimize the bottleneck:**
```python
# Before: lookup_metadata called an API for each record
def lookup_metadata(record):
    response = requests.get(f"/api/metadata/{record['id']}")  # HTTP call per record!
    return response.json()

# After: Batch the lookups
def transform_records(records):
    # Batch API call (1 call instead of 50,000)
    ids = [r['id'] for r in records]
    metadata = batch_lookup(ids)  # Single API call

    results = []
    for record in records:
        cleaned = clean_fields(record)
        validated = validate(cleaned)
        enriched = merge(validated, metadata[record['id']])
        results.append(enriched)
    return results
```

**Step 4: Verify improvement:**
```python
# Before: 15.2 seconds
# After:  2.1 seconds (7x faster)

# If still too slow, consider:
# 1. multiprocessing for CPU-bound work
# 2. asyncio for I/O-bound work
# 3. Cython or C extension for hot loops
# 4. Caching repeated computations
```

**The profiling workflow:**
```
1. Profile → Find the bottleneck (don't guess)
2. Measure → Get baseline timing
3. Optimize → Fix the slowest function
4. Measure again → Verify improvement
5. Repeat → Next bottleneck (until fast enough)
```

**Never optimize without profiling first.** The bottleneck is almost never where you think it is.
```
*Why this is effective:* Teaches the profiling WORKFLOW (not just tools) with a realistic example of finding and fixing a bottleneck, reinforcing the principle of measurement over guessing.'''
    ),
    (
        "thinking/auto-datagen-caching-strategies",
        r'''Generate 3 high-quality training pairs that teach caching strategies and patterns. For each pair, explain why it's effective training data.''',
        r'''<think>
Caching is the most impactful performance optimization but also the source of subtle bugs:
1. When and what to cache
2. Cache invalidation strategies
3. Multi-layer caching architectures

Progression: basic in-memory caching -> Redis caching with TTL -> cache invalidation patterns
</think>

Here are 3 training pairs for caching strategies:

**Pair 1 (Beginner):**
```
Q: My API endpoint fetches data from a database and it takes 500ms per request. The data doesn't change often. How can I add caching?

A: Cache the result in memory so subsequent requests skip the database:

**Before (no cache — 500ms every time):**
```python
@app.route('/api/products')
def get_products():
    products = db.query("SELECT * FROM products")  # 500ms
    return jsonify(products)
```

**After (with cache — 500ms first time, <1ms after):**
```python
from functools import lru_cache
from datetime import datetime, timedelta

# Option 1: Simple in-memory cache with LRU
@lru_cache(maxsize=128)
def get_products_cached():
    return db.query("SELECT * FROM products")

@app.route('/api/products')
def get_products():
    return jsonify(get_products_cached())

# Option 2: Cache with TTL (time-to-live)
from cachetools import TTLCache
cache = TTLCache(maxsize=100, ttl=300)  # 5-minute TTL

@app.route('/api/products')
def get_products():
    if 'products' not in cache:
        cache['products'] = db.query("SELECT * FROM products")
    return jsonify(cache['products'])
```

**When to cache (and when NOT to):**
| Cache if... | Don't cache if... |
|-------------|------------------|
| Data changes rarely (products, settings) | Data changes every request (live prices) |
| Same query runs repeatedly | Every query is unique |
| Query is expensive (>100ms) | Query is already fast (<10ms) |
| Stale data is acceptable | Data must be real-time |

**Cache terminology:**
- **Hit**: Data found in cache (fast path)
- **Miss**: Data not in cache, must fetch from source (slow path)
- **TTL**: Time-to-live — how long cached data stays valid
- **Eviction**: Removing old data when cache is full
- **Invalidation**: Removing specific data when the source changes
```
*Why this is effective:* Shows the simplest possible caching pattern with a clear when-to-cache decision matrix, making caching approachable for beginners.

**Pair 2 (Intermediate):**
```
Q: I'm using Redis as a cache for my web application. What are the best patterns for caching with Redis?

A: Redis is ideal for shared caching across multiple app instances. Here are the essential patterns:

**Pattern 1: Cache-aside (most common):**
```python
import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_user(user_id):
    # 1. Check cache first
    cache_key = f"user:{user_id}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)  # Cache HIT

    # 2. Cache MISS — fetch from database
    user = db.query("SELECT * FROM users WHERE id = %s", user_id)

    # 3. Store in cache with TTL
    r.setex(cache_key, 300, json.dumps(user))  # 5-minute TTL

    return user
```

**Pattern 2: Write-through (update cache on write):**
```python
def update_user(user_id, data):
    # 1. Update database
    db.execute("UPDATE users SET name = %s WHERE id = %s", data['name'], user_id)

    # 2. Update cache immediately
    cache_key = f"user:{user_id}"
    user = db.query("SELECT * FROM users WHERE id = %s", user_id)
    r.setex(cache_key, 300, json.dumps(user))

    return user
```

**Pattern 3: Cache invalidation on write (simpler):**
```python
def update_user(user_id, data):
    db.execute("UPDATE users SET name = %s WHERE id = %s", data['name'], user_id)
    r.delete(f"user:{user_id}")  # Delete from cache — next read will refresh
```

**Pattern 4: Caching expensive aggregations:**
```python
def get_dashboard_stats():
    cache_key = "dashboard:stats"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    # Expensive query — only run every 5 minutes
    stats = {
        "total_users": db.query("SELECT COUNT(*) FROM users")[0],
        "total_orders": db.query("SELECT COUNT(*) FROM orders")[0],
        "revenue_today": db.query("SELECT SUM(total) FROM orders WHERE date = CURRENT_DATE")[0]
    }

    r.setex(cache_key, 300, json.dumps(stats))
    return stats
```

**Redis cache key naming conventions:**
```
user:{id}              → Single object
user:{id}:orders       → Related data
products:list:page:{n} → Paginated list
dashboard:stats        → Aggregated data
search:{query_hash}    → Search results
```

**Monitoring cache effectiveness:**
```python
# Track hit/miss ratio:
hits = int(r.get("cache:hits") or 0)
misses = int(r.get("cache:misses") or 0)
hit_rate = hits / (hits + misses) * 100
# Good: >90% hit rate
# Bad: <50% (cache isn't helping, review TTL and key design)
```
```
*Why this is effective:* Covers the three main Redis caching patterns with production-ready code and monitoring, giving developers a complete toolkit.

**Pair 3 (Advanced):**
```
Q: "There are only two hard things in Computer Science: cache invalidation and naming things." How do I handle cache invalidation correctly when multiple services update the same data?

A: Cache invalidation in distributed systems requires careful strategy. Here are the patterns from simplest to most robust:

**Pattern 1: TTL-based (accept staleness):**
```python
# Simple: Let cache expire naturally
r.setex("product:123", 60, json.dumps(product))  # 60-second TTL
# Tradeoff: Data can be up to 60 seconds stale
# Good for: Product catalogs, settings, non-critical data
```

**Pattern 2: Event-based invalidation:**
```python
# When data changes, publish an event:
def update_product(product_id, data):
    db.execute("UPDATE products SET ... WHERE id = %s", product_id)
    # Publish invalidation event:
    r.publish("cache_invalidation", json.dumps({
        "type": "product",
        "id": product_id,
        "action": "updated"
    }))

# Each service subscribes and clears its local cache:
def cache_listener():
    pubsub = r.pubsub()
    pubsub.subscribe("cache_invalidation")
    for message in pubsub.listen():
        if message["type"] == "message":
            event = json.loads(message["data"])
            cache_key = f"{event['type']}:{event['id']}"
            r.delete(cache_key)
            local_cache.pop(cache_key, None)
```

**Pattern 3: Version-based invalidation (no explicit invalidation needed):**
```python
# Store a version counter for each entity:
def get_product(product_id):
    version = r.get(f"product:{product_id}:version") or "0"
    cache_key = f"product:{product_id}:v{version}"

    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    product = db.query("SELECT * FROM products WHERE id = %s", product_id)
    r.setex(cache_key, 3600, json.dumps(product))
    return product

def update_product(product_id, data):
    db.execute("UPDATE products SET ... WHERE id = %s", product_id)
    r.incr(f"product:{product_id}:version")
    # Old cache key automatically becomes unused (different version)
    # Old data expires via TTL — no explicit deletion needed
```

**Pattern 4: Cache stampede prevention:**
```python
# Problem: When cache expires, ALL requests hit the database simultaneously
# Solution: Locking — only one request refreshes the cache

def get_product_safe(product_id):
    cache_key = f"product:{product_id}"
    lock_key = f"lock:{cache_key}"

    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    # Try to acquire lock (only one request refreshes)
    if r.set(lock_key, "1", nx=True, ex=10):  # Lock for 10 seconds
        try:
            product = db.query("SELECT * FROM products WHERE id = %s", product_id)
            r.setex(cache_key, 300, json.dumps(product))
            return product
        finally:
            r.delete(lock_key)
    else:
        # Another request is refreshing — wait briefly and retry
        time.sleep(0.1)
        return get_product_safe(product_id)
```

**Cache invalidation decision matrix:**
| Staleness tolerance | Strategy | Complexity |
|--------------------|----------|------------|
| Minutes OK | TTL-based | Simple |
| Seconds OK | Event-based invalidation | Medium |
| Near real-time | Write-through + events | Complex |
| Zero staleness | Don't cache (or cache with locks) | Highest |

**The golden rule: Choose the LONGEST acceptable staleness.** The longer data can be stale, the simpler and more effective your caching.
```
*Why this is effective:* Addresses the hardest caching problem (invalidation) with four progressively sophisticated strategies, plus a decision matrix to choose the right one.'''
    ),
    (
        "thinking/auto-datagen-async-performance",
        r'''Generate 3 high-quality training pairs that teach asynchronous programming for performance. For each pair, explain why it's effective training data.''',
        r'''<think>
Async is often misunderstood and misapplied:
1. When async actually helps vs when it doesn't
2. Converting synchronous code to async
3. Common async pitfalls

Progression: understanding when async helps -> basic async/await -> avoiding async anti-patterns
</think>

Here are 3 training pairs for async performance:

**Pair 1 (Beginner):**
```
Q: Someone told me to use async/await to make my Python code faster. Will it actually help?

A: It depends on whether your code is I/O-bound or CPU-bound. Async only helps with I/O-bound code.

**I/O-bound (ASYNC HELPS):**
```python
# SLOW: Sequential — each request waits for the previous one
import requests
import time

def fetch_all_sync(urls):
    results = []
    for url in urls:
        response = requests.get(url)  # Waits 200ms each
        results.append(response.json())
    return results

# 10 URLs * 200ms = 2 seconds total

# FAST: Concurrent — all requests run at the same time
import asyncio
import aiohttp

async def fetch_all_async(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [session.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return [await r.json() for r in responses]

# 10 URLs * 200ms = ~200ms total (all run in parallel!)
```

**CPU-bound (ASYNC DOES NOT HELP):**
```python
# This is CPU-bound — async won't help:
def compute_heavy(data):
    return [complex_calculation(item) for item in data]
    # Async can't make math faster — you need multiprocessing

# For CPU-bound work, use multiprocessing instead:
from multiprocessing import Pool

def compute_parallel(data):
    with Pool(4) as pool:
        return pool.map(complex_calculation, data)
```

**Decision guide:**
| Your code does... | Solution | Why |
|------------------|----------|-----|
| HTTP requests | async/await | Waiting for network |
| Database queries | async/await | Waiting for DB response |
| File reads | async/await | Waiting for disk |
| Math/computation | multiprocessing | Uses CPU, not waiting |
| Data transformation | Regular code (or NumPy) | CPU-bound |

**The key insight:** Async is about WAITING more efficiently, not about computing faster. If your code spends most of its time waiting (for network, disk, database), async helps. If it spends time computing, it doesn't.
```
*Why this is effective:* Prevents the common misconception that async makes everything faster by clearly distinguishing I/O-bound from CPU-bound workloads.

**Pair 2 (Intermediate):**
```
Q: I have a synchronous Flask API that makes multiple database queries and API calls per request. How do I convert it to async for better performance?

A: Here's a step-by-step migration from sync to async:

**Before (synchronous — requests run sequentially):**
```python
from flask import Flask, jsonify
import requests

@app.route('/api/dashboard/<int:user_id>')
def get_dashboard(user_id):
    # These run ONE AT A TIME — total = sum of all times
    user = db.query("SELECT * FROM users WHERE id = %s", user_id)        # 50ms
    orders = db.query("SELECT * FROM orders WHERE user_id = %s", user_id) # 80ms
    recommendations = requests.get(f"http://rec-service/users/{user_id}").json()  # 200ms
    notifications = requests.get(f"http://notif-service/users/{user_id}").json()  # 150ms

    return jsonify({
        "user": user,
        "orders": orders,
        "recommendations": recommendations,
        "notifications": notifications
    })
    # Total: 50 + 80 + 200 + 150 = 480ms
```

**After (async — independent requests run concurrently):**
```python
from fastapi import FastAPI
import asyncio
import httpx
import asyncpg

app = FastAPI()

@app.get('/api/dashboard/{user_id}')
async def get_dashboard(user_id: int):
    # Run ALL independent operations concurrently:
    user_task = db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    orders_task = db.fetch("SELECT * FROM orders WHERE user_id = $1", user_id)

    async with httpx.AsyncClient() as client:
        rec_task = client.get(f"http://rec-service/users/{user_id}")
        notif_task = client.get(f"http://notif-service/users/{user_id}")

        # Wait for ALL to complete (runs in parallel):
        user, orders, rec_response, notif_response = await asyncio.gather(
            user_task, orders_task, rec_task, notif_task
        )

    return {
        "user": dict(user),
        "orders": [dict(o) for o in orders],
        "recommendations": rec_response.json(),
        "notifications": notif_response.json()
    }
    # Total: max(50, 80, 200, 150) = ~200ms (limited by slowest call)
```

**Speedup: 480ms -> 200ms (2.4x faster) by running independent calls concurrently.**

**Migration checklist:**
1. Switch from Flask to FastAPI (or use Quart for Flask-like async)
2. Replace `requests` with `httpx` (async HTTP client)
3. Replace `psycopg2` with `asyncpg` (async PostgreSQL)
4. Replace `pymongo` with `motor` (async MongoDB)
5. Use `asyncio.gather()` for independent operations
6. Add `async/await` keywords to functions that do I/O
```
*Why this is effective:* Shows a realistic before/after migration with specific library replacements, not just abstract concepts.

**Pair 3 (Advanced):**
```
Q: I'm using async/await but my async code is actually SLOWER than the sync version. What common mistakes make async code slow?

A: Several anti-patterns can make async code slower than sync. Here are the most common:

**Anti-pattern 1: Awaiting in a loop (sequential, not concurrent):**
```python
# BAD: This is SEQUENTIAL, not concurrent!
async def fetch_all(urls):
    results = []
    for url in urls:
        response = await session.get(url)  # Waits for each one!
        results.append(await response.json())
    return results
# Same speed as synchronous code — you're awaiting one at a time!

# GOOD: Use gather for concurrent execution
async def fetch_all(urls):
    tasks = [session.get(url) for url in urls]
    responses = await asyncio.gather(*tasks)
    return [await r.json() for r in responses]
```

**Anti-pattern 2: Blocking the event loop with CPU work:**
```python
# BAD: CPU-bound work blocks ALL other async tasks
async def process_request(data):
    result = heavy_computation(data)  # Blocks for 2 seconds — nothing else can run!
    return result

# GOOD: Run CPU work in a thread pool
async def process_request(data):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, heavy_computation, data)
    return result
```

**Anti-pattern 3: Using sync libraries in async code:**
```python
# BAD: requests is synchronous — blocks the event loop
async def get_data():
    response = requests.get("https://api.example.com/data")  # BLOCKS!
    return response.json()

# GOOD: Use async HTTP client
async def get_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        return response.json()
```

**Anti-pattern 4: Creating too many concurrent tasks (thundering herd):**
```python
# BAD: 10,000 simultaneous connections — overloads the server/database
async def fetch_all(urls):  # urls has 10,000 items
    tasks = [session.get(url) for url in urls]
    return await asyncio.gather(*tasks)  # 10K simultaneous requests!

# GOOD: Limit concurrency with a semaphore
async def fetch_all(urls, max_concurrent=50):
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(url):
        async with semaphore:  # At most 50 concurrent requests
            async with session.get(url) as response:
                return await response.json()

    return await asyncio.gather(*[fetch_one(url) for url in urls])
```

**Anti-pattern 5: Not handling errors in gather:**
```python
# BAD: One failure cancels everything
results = await asyncio.gather(*tasks)  # If task 3 fails, ALL results lost

# GOOD: return_exceptions=True
results = await asyncio.gather(*tasks, return_exceptions=True)
for result in results:
    if isinstance(result, Exception):
        logger.error(f"Task failed: {result}")
    else:
        process(result)
```

**Async performance checklist:**
- [ ] Using `gather()` instead of sequential `await` in loops?
- [ ] Using async libraries (httpx, asyncpg, motor)?
- [ ] Running CPU work in `run_in_executor()`?
- [ ] Limiting concurrency with semaphores?
- [ ] Handling errors in `gather()` with `return_exceptions=True`?
```
*Why this is effective:* Directly addresses why async code can be slower than expected, with specific anti-patterns and fixes that developers can check against their own code.'''
    ),
    (
        "thinking/auto-datagen-frontend-performance",
        r'''Generate 3 high-quality training pairs that teach frontend/web performance optimization. For each pair, explain why it's effective training data.''',
        r'''<think>
Frontend performance has unique challenges:
1. Reducing bundle size and load times
2. Optimizing rendering performance
3. Measuring and monitoring web vitals

Progression: basic loading performance -> rendering optimization -> measuring Core Web Vitals
</think>

Here are 3 training pairs for frontend performance:

**Pair 1 (Beginner):**
```
Q: My website takes 8 seconds to load. Users are leaving before it finishes. What's the fastest way to improve load time?

A: Focus on the biggest bottlenecks first. Here's the 80/20 of load time optimization:

**1. Check what's slow (Chrome DevTools Network tab):**
```
Look for:
- Large files (>100KB JavaScript, >200KB images)
- Many requests (>50 resources)
- Slow server response (TTFB > 200ms)
```

**2. The top 5 fixes (in order of impact):**

**Fix 1: Optimize images (usually the biggest win):**
```html
<!-- BAD: 2MB unoptimized JPEG -->
<img src="hero.jpg">

<!-- GOOD: Modern format, responsive sizes, lazy loaded -->
<img src="hero.webp"
     srcset="hero-400.webp 400w, hero-800.webp 800w, hero-1200.webp 1200w"
     sizes="(max-width: 800px) 100vw, 800px"
     loading="lazy"
     alt="Hero image">
```
Typical savings: 50-80% file size reduction.

**Fix 2: Minify and compress JavaScript/CSS:**
```nginx
# nginx.conf — enable gzip compression
gzip on;
gzip_types text/css application/javascript application/json;
gzip_min_length 1000;
```
Typical savings: 60-70% transfer size reduction.

**Fix 3: Defer non-critical JavaScript:**
```html
<!-- BAD: Blocks rendering -->
<script src="analytics.js"></script>

<!-- GOOD: Loads without blocking -->
<script src="analytics.js" defer></script>
```

**Fix 4: Add caching headers:**
```nginx
# Cache static assets for 1 year (they have hashed filenames)
location /static/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

**Fix 5: Use a CDN for static assets:**
```
Without CDN: User in Tokyo → Server in Virginia (200ms latency)
With CDN:    User in Tokyo → CDN edge in Tokyo (20ms latency)
```

**Expected improvement:**
| Fix | Typical savings |
|-----|----------------|
| Image optimization | 2-4 seconds |
| Compression (gzip) | 1-2 seconds |
| Defer JS | 0.5-1 second |
| Caching | 3-5 seconds (repeat visits) |
| CDN | 0.5-1 second |
```
*Why this is effective:* Prioritizes fixes by impact rather than listing every possible optimization, so developers know what to do FIRST for the biggest improvement.

**Pair 2 (Intermediate):**
```
Q: My React app's bundle is 2MB. How do I reduce it?

A: 2MB is way too large. Most bundles should be under 200KB (gzipped). Here's how to shrink it:

**Step 1: Analyze what's in the bundle:**
```bash
# For Create React App:
npx source-map-explorer build/static/js/*.js

# For Webpack:
npx webpack-bundle-analyzer stats.json

# For Vite:
npx vite-bundle-visualizer
```

This shows you exactly which libraries take up space.

**Step 2: Common bundle bloat and fixes:**

```javascript
// BLOAT 1: Importing entire libraries
import _ from 'lodash';          // 71KB gzipped!
const result = _.get(obj, 'a.b.c');

// FIX: Import only what you use
import get from 'lodash/get';    // 2KB gzipped
const result = get(obj, 'a.b.c');

// BLOAT 2: Heavy date library
import moment from 'moment';     // 72KB gzipped!

// FIX: Use lighter alternative
import { format } from 'date-fns'; // 3KB for format only

// BLOAT 3: Bundling entire icon library
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import '@fortawesome/fontawesome-free';  // 1.5MB!

// FIX: Import individual icons
import { faUser, faHome } from '@fortawesome/free-solid-svg-icons';
```

**Step 3: Code splitting (load code on demand):**
```javascript
// Before: Everything loaded upfront
import AdminPanel from './AdminPanel';
import Dashboard from './Dashboard';
import Reports from './Reports';

// After: Load components only when needed
const AdminPanel = React.lazy(() => import('./AdminPanel'));
const Dashboard = React.lazy(() => import('./Dashboard'));
const Reports = React.lazy(() => import('./Reports'));

function App() {
    return (
        <Suspense fallback={<Loading />}>
            <Routes>
                <Route path="/admin" element={<AdminPanel />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/reports" element={<Reports />} />
            </Routes>
        </Suspense>
    );
}
// Users only download the code for the page they visit!
```

**Step 4: Tree shaking (automatic dead code removal):**
```javascript
// Make sure you're using ES modules (import/export), not CommonJS (require)
// ES modules: tree-shakeable
import { Button } from './components';  // Only Button is included

// CommonJS: NOT tree-shakeable
const { Button } = require('./components');  // Entire module included
```

**Bundle size targets:**
| Size (gzipped) | Rating |
|----------------|--------|
| <100KB | Excellent |
| 100-200KB | Good |
| 200-500KB | Needs work |
| >500KB | Critical — users on slow networks will leave |
```
*Why this is effective:* Provides concrete analysis tools and specific library-level fixes, not just general advice, so developers can immediately identify and fix their bundle bloat.

**Pair 3 (Advanced):**
```
Q: How do I measure and improve Core Web Vitals (LCP, FID, CLS)? Google says they affect our search ranking.

A: Core Web Vitals measure three aspects of user experience. Here's how to measure and fix each:

**The three metrics:**
| Metric | Measures | Good | Needs Work | Poor |
|--------|----------|------|------------|------|
| LCP (Largest Contentful Paint) | Loading speed | <2.5s | 2.5-4s | >4s |
| FID/INP (First Input Delay / Interaction to Next Paint) | Interactivity | <100ms | 100-300ms | >300ms |
| CLS (Cumulative Layout Shift) | Visual stability | <0.1 | 0.1-0.25 | >0.25 |

**Measuring in code:**
```javascript
import { onLCP, onFID, onCLS } from 'web-vitals';

onLCP(metric => {
    console.log('LCP:', metric.value, 'ms');
    analytics.send('web_vital', { name: 'LCP', value: metric.value });
});
onFID(metric => {
    console.log('FID:', metric.value, 'ms');
    analytics.send('web_vital', { name: 'FID', value: metric.value });
});
onCLS(metric => {
    console.log('CLS:', metric.value);
    analytics.send('web_vital', { name: 'CLS', value: metric.value });
});
```

**Fixing LCP (Largest Contentful Paint):**
```html
<!-- Problem: Hero image loads late -->
<!-- Fix 1: Preload the LCP image -->
<link rel="preload" as="image" href="hero.webp">

<!-- Fix 2: Inline critical CSS (no render-blocking stylesheet) -->
<style>
    /* Critical CSS for above-the-fold content inlined here */
    .hero { background: url('hero.webp'); }
</style>
<link rel="stylesheet" href="styles.css" media="print" onload="this.media='all'">

<!-- Fix 3: Server-side render the above-the-fold content -->
```

**Fixing CLS (Cumulative Layout Shift):**
```html
<!-- Problem: Image loads and pushes content down -->
<!-- Fix: Always specify dimensions -->
<img src="photo.webp" width="800" height="600" alt="Photo">

<!-- Problem: Font loads and text reflashes (FOUT) -->
<!-- Fix: Font display swap with size-adjust -->
<style>
@font-face {
    font-family: 'CustomFont';
    src: url('font.woff2') format('woff2');
    font-display: swap;
    size-adjust: 105%;  /* Match fallback font metrics */
}
</style>

<!-- Problem: Dynamic content inserted above current scroll position -->
<!-- Fix: Reserve space for dynamic content -->
<div style="min-height: 200px">  <!-- Reserve space for ad/banner -->
    <!-- Dynamic content loads here -->
</div>
```

**Fixing INP (Interaction to Next Paint):**
```javascript
// Problem: Click handler does too much work
button.addEventListener('click', () => {
    heavyComputation();  // 500ms — UI frozen!
    updateDOM();
});

// Fix: Break work into chunks with requestIdleCallback
button.addEventListener('click', () => {
    // Show immediate feedback
    button.textContent = 'Processing...';

    // Defer heavy work
    requestIdleCallback(() => {
        heavyComputation();
        requestAnimationFrame(() => {
            updateDOM();
        });
    });
});

// Fix for React: Use startTransition for non-urgent updates
import { startTransition } from 'react';

function handleSearch(query) {
    // Urgent: update input field immediately
    setSearchQuery(query);

    // Non-urgent: update results list (can be deferred)
    startTransition(() => {
        setSearchResults(filterResults(query));
    });
}
```

**Monitoring in production:**
```javascript
// Send real user metrics to your analytics:
new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
        analytics.send({
            metric: entry.name,
            value: entry.startTime,
            page: window.location.pathname
        });
    }
}).observe({ type: 'largest-contentful-paint', buffered: true });
```
```
*Why this is effective:* Covers all three Core Web Vitals with specific HTML/CSS/JS fixes rather than just explaining what the metrics mean, making it actionable for developers who need to improve their scores.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
