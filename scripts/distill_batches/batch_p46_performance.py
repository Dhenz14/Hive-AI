"""Performance optimization — profiling, caching, database tuning, and frontend performance."""

PAIRS = [
    (
        "performance/python-profiling",
        "Show Python profiling and optimization: cProfile, line_profiler, memory_profiler, and common speedups.",
        '''Python profiling and optimization patterns:

```python
import cProfile
import pstats
import io
import time
import functools
from typing import Callable, TypeVar

T = TypeVar("T")


# --- Profiling decorator ---

def profile(func: Callable) -> Callable:
    """Profile a function with cProfile."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        result = func(*args, **kwargs)
        pr.disable()

        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
        ps.print_stats(20)
        print(s.getvalue())
        return result
    return wrapper


# --- Timing context manager ---

class Timer:
    def __init__(self, name: str = ""):
        self.name = name

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self.start
        print(f"{self.name}: {self.elapsed:.4f}s")

# Usage: with Timer("query"): db.execute(...)


# --- Common optimizations ---

# 1. Use __slots__ for data classes with many instances
class Point:
    __slots__ = ('x', 'y', 'z')
    def __init__(self, x: float, y: float, z: float):
        self.x, self.y, self.z = x, y, z
# 40-50% less memory than regular class

# 2. Local variable access is faster than global/attribute
def process_fast(items: list) -> list:
    # Cache method lookup outside loop
    result_append = [].append  # Avoid repeated attribute lookup
    for item in items:
        result_append(item * 2)

# 3. Generator for large sequences (lazy evaluation)
def read_large_file(path: str):
    with open(path) as f:
        for line in f:
            yield line.strip()

# vs loading everything into memory:
# lines = open(path).readlines()  # BAD for large files

# 4. Use set for membership testing
allowed = set(range(10000))       # O(1) lookup
# vs list: allowed = list(range(10000))  # O(n) lookup

# 5. String concatenation
# BAD:
result = ""
for s in strings:
    result += s  # O(n^2) — creates new string each time

# GOOD:
result = "".join(strings)  # O(n) — single allocation

# 6. Dict comprehension vs loop
# GOOD:
mapping = {k: v for k, v in pairs}

# 7. collections.defaultdict avoids key checks
from collections import defaultdict
groups = defaultdict(list)
for item in items:
    groups[item.category].append(item)

# 8. Use bisect for sorted list operations
import bisect
sorted_list = []
for item in items:
    bisect.insort(sorted_list, item)  # O(log n) insert

# 9. Avoid repeated computation
# BAD:
for i in range(len(data)):
    if len(data) > threshold:  # len() called every iteration
        ...

# GOOD:
data_len = len(data)
for i in range(data_len):
    if data_len > threshold:
        ...

# 10. Use array/numpy for numeric data
import array
# array.array('d', ...) uses ~8 bytes per float
# list of floats uses ~28 bytes per float (3.5x more)


# --- Memory profiling ---
# pip install memory_profiler
# @profile  # from memory_profiler import profile
# def memory_heavy():
#     big_list = [i ** 2 for i in range(1_000_000)]
#     ...
# Run: python -m memory_profiler script.py

# --- line_profiler ---
# pip install line_profiler
# @profile  # kernprof decorator
# def compute():
#     ...
# Run: kernprof -l -v script.py
```

Optimization rules:
1. **Profile first** — measure before optimizing, don't guess
2. **Algorithmic wins** — O(n) vs O(n^2) matters more than micro-optimization
3. **Batch I/O** — combine database queries, batch API calls
4. **Lazy evaluation** — generators for large sequences
5. **Cache expensive results** — `lru_cache`, Redis, or precomputation'''
    ),
    (
        "performance/caching-strategies",
        "Show caching strategies: cache-aside, write-through, TTL management, cache invalidation, and multi-layer caching.",
        '''Caching strategy patterns:

```python
import hashlib
import json
import time
from functools import wraps
from typing import Any, Callable, Optional
import redis


# --- Cache-aside pattern ---

class CacheAside:
    """Application manages cache reads/writes."""

    def __init__(self, redis_client: redis.Redis, default_ttl: int = 300):
        self.redis = redis_client
        self.default_ttl = default_ttl

    async def get_or_set(self, key: str, fetch_fn: Callable,
                         ttl: int = None) -> Any:
        # Try cache first
        cached = self.redis.get(key)
        if cached:
            return json.loads(cached)

        # Cache miss — fetch from source
        value = await fetch_fn()

        # Store in cache
        self.redis.setex(
            key, ttl or self.default_ttl, json.dumps(value, default=str)
        )
        return value

    def invalidate(self, key: str):
        self.redis.delete(key)

    def invalidate_pattern(self, pattern: str):
        """Delete all keys matching pattern."""
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
            if keys:
                self.redis.delete(*keys)
            if cursor == 0:
                break


# --- Write-through cache ---

class WriteThrough:
    """Write to cache and database simultaneously."""

    def __init__(self, redis_client, db, ttl: int = 3600):
        self.redis = redis_client
        self.db = db
        self.ttl = ttl

    async def get(self, key: str) -> Optional[dict]:
        cached = self.redis.get(f"wt:{key}")
        if cached:
            return json.loads(cached)

        value = await self.db.find_one(key)
        if value:
            self.redis.setex(f"wt:{key}", self.ttl, json.dumps(value, default=str))
        return value

    async def set(self, key: str, value: dict) -> None:
        # Write to both atomically
        await self.db.upsert(key, value)
        self.redis.setex(f"wt:{key}", self.ttl, json.dumps(value, default=str))

    async def delete(self, key: str) -> None:
        await self.db.delete(key)
        self.redis.delete(f"wt:{key}")


# --- Cache stampede prevention ---

class StampedeProtectedCache:
    """Prevent thundering herd on cache expiry."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def get_or_set(self, key: str, fetch_fn: Callable,
                         ttl: int = 300, lock_timeout: int = 10) -> Any:
        cached = self.redis.get(key)
        if cached:
            return json.loads(cached)

        # Try to acquire lock
        lock_key = f"lock:{key}"
        acquired = self.redis.set(lock_key, "1", nx=True, ex=lock_timeout)

        if acquired:
            try:
                # Winner fetches and caches
                value = await fetch_fn()
                self.redis.setex(key, ttl, json.dumps(value, default=str))
                return value
            finally:
                self.redis.delete(lock_key)
        else:
            # Losers wait and retry
            for _ in range(lock_timeout * 10):
                time.sleep(0.1)
                cached = self.redis.get(key)
                if cached:
                    return json.loads(cached)
            # Fallback: fetch directly
            return await fetch_fn()


# --- Decorator-based caching ---

def cached(ttl: int = 300, prefix: str = ""):
    """Cache function results with TTL."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function name + arguments
            key_data = f"{prefix or func.__name__}:{args}:{sorted(kwargs.items())}"
            cache_key = hashlib.md5(key_data.encode()).hexdigest()

            cached_value = redis_client.get(cache_key)
            if cached_value:
                return json.loads(cached_value)

            result = await func(*args, **kwargs)
            redis_client.setex(cache_key, ttl, json.dumps(result, default=str))
            return result
        return wrapper
    return decorator

@cached(ttl=600, prefix="user")
async def get_user_profile(user_id: str) -> dict:
    return await db.users.find_one(user_id)


# --- Multi-layer cache (L1: in-memory, L2: Redis) ---

from cachetools import TTLCache

class MultiLayerCache:
    def __init__(self, redis_client):
        self.l1 = TTLCache(maxsize=1000, ttl=60)  # In-process, 60s
        self.l2 = redis_client                      # Shared, 300s

    async def get(self, key: str, fetch_fn: Callable = None) -> Any:
        # L1: in-memory (fastest)
        if key in self.l1:
            return self.l1[key]

        # L2: Redis
        cached = self.l2.get(f"ml:{key}")
        if cached:
            value = json.loads(cached)
            self.l1[key] = value
            return value

        # Miss: fetch from source
        if fetch_fn:
            value = await fetch_fn()
            self.l1[key] = value
            self.l2.setex(f"ml:{key}", 300, json.dumps(value, default=str))
            return value
        return None

    def invalidate(self, key: str):
        self.l1.pop(key, None)
        self.l2.delete(f"ml:{key}")
```

Caching strategies:
1. **Cache-aside** — app checks cache, fetches on miss (most common)
2. **Write-through** — write to cache + DB together (strong consistency)
3. **Stampede prevention** — lock on miss, others wait (prevents thundering herd)
4. **Multi-layer** — L1 in-process + L2 distributed (lowest latency)
5. **Invalidation** — pattern-based, event-driven, or TTL-based expiry'''
    ),
    (
        "performance/database-optimization",
        "Show database optimization patterns: query analysis, indexing strategies, N+1 prevention, and connection pooling.",
        '''Database performance optimization patterns:

```python
import asyncpg
from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload, joinedload, subqueryload
from contextlib import asynccontextmanager


# --- Connection pooling ---

async def create_pool():
    """Properly configured connection pool."""
    return await asyncpg.create_pool(
        dsn="postgresql://user:pass@localhost/db",
        min_size=5,           # Keep 5 connections warm
        max_size=20,          # Max 20 connections
        max_inactive_connection_lifetime=300,  # Close idle after 5min
        command_timeout=30,   # Query timeout
        statement_cache_size=100,  # Prepared statement cache
    )


# --- N+1 query prevention ---

# BAD: N+1 problem
async def get_orders_bad(session):
    orders = await session.scalars(select(Order))
    for order in orders:
        # Each access triggers a separate query!
        print(order.customer.name)
        for item in order.items:
            print(item.product.name)

# GOOD: Eager loading
async def get_orders_good(session):
    stmt = (
        select(Order)
        .options(
            joinedload(Order.customer),          # JOIN (1:1 or M:1)
            selectinload(Order.items)            # SELECT IN (1:N)
                .joinedload(OrderItem.product),  # Nested eager load
        )
        .order_by(Order.created_at.desc())
        .limit(20)
    )
    orders = await session.scalars(stmt)
    # All data loaded in 2-3 queries instead of N+1


# --- Query optimization ---

# 1. Select only needed columns
stmt = select(User.id, User.name, User.email).where(User.is_active == True)

# 2. Use EXISTS instead of COUNT for existence checks
exists_stmt = select(
    select(Order).where(Order.user_id == user_id).exists()
)

# 3. Bulk operations instead of row-by-row
async def bulk_update_status(session, order_ids: list[str], status: str):
    await session.execute(
        Order.__table__.update()
        .where(Order.id.in_(order_ids))
        .values(status=status)
    )
    # Single query instead of N updates

# 4. Use database-side aggregation
async def get_category_stats(session):
    stmt = (
        select(
            Product.category,
            func.count(Product.id).label("count"),
            func.avg(Product.price).label("avg_price"),
            func.sum(Product.price).label("total"),
        )
        .group_by(Product.category)
        .having(func.count(Product.id) > 5)
        .order_by(func.sum(Product.price).desc())
    )
    return (await session.execute(stmt)).all()


# --- Index strategies ---

# PostgreSQL index examples via raw SQL
INDEX_STATEMENTS = [
    # B-tree (default) — equality and range queries
    "CREATE INDEX idx_orders_user_id ON orders (user_id)",

    # Composite — covers multi-column WHERE and ORDER BY
    "CREATE INDEX idx_orders_user_date ON orders (user_id, created_at DESC)",

    # Partial — index only relevant rows (smaller, faster)
    "CREATE INDEX idx_active_users ON users (email) WHERE is_active = true",

    # Covering — includes extra columns to avoid table lookup
    "CREATE INDEX idx_products_category ON products (category) INCLUDE (name, price)",

    # GIN — for array/JSONB containment queries
    "CREATE INDEX idx_products_tags ON products USING GIN (tags)",

    # Expression — index computed values
    "CREATE INDEX idx_users_email_lower ON users (LOWER(email))",
]


# --- Query analysis ---

async def explain_query(pool, query: str):
    """Run EXPLAIN ANALYZE and return execution plan."""
    async with pool.acquire() as conn:
        plan = await conn.fetch(
            f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
        )
        return plan[0][0]


# --- Batch processing ---

async def process_in_batches(pool, query: str, batch_size: int = 1000):
    """Process large result sets without loading all into memory."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Server-side cursor
            async for record in conn.cursor(query, prefetch=batch_size):
                await process_record(record)


# --- Read replica routing ---

class DatabaseRouter:
    def __init__(self, write_pool, read_pool):
        self.write_pool = write_pool
        self.read_pool = read_pool

    @asynccontextmanager
    async def read(self):
        async with self.read_pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def write(self):
        async with self.write_pool.acquire() as conn:
            yield conn
```

Database optimization rules:
1. **EXPLAIN ANALYZE** — always check query plans before optimizing
2. **Index the WHERE + ORDER BY** — compound indexes cover common queries
3. **Eager load** — prevent N+1 with `joinedload`/`selectinload`
4. **Select columns** — don't `SELECT *` when you only need 3 fields
5. **Connection pooling** — reuse connections, set appropriate pool sizes'''
    ),
]
"""
