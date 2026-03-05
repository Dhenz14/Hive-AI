"""Database performance — query optimization, indexing, connection pooling."""

PAIRS = [
    (
        "database/query-optimization",
        "Show database query optimization: EXPLAIN ANALYZE reading, index strategies, query rewriting, and common anti-patterns.",
        '''Database query optimization:

```sql
-- EXPLAIN ANALYZE: understand query execution
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT u.name, COUNT(o.id) as order_count, SUM(o.total) as total_spent
FROM users u
JOIN orders o ON o.user_id = u.id
WHERE o.created_at >= NOW() - INTERVAL '30 days'
  AND u.status = 'active'
GROUP BY u.id, u.name
HAVING SUM(o.total) > 100
ORDER BY total_spent DESC
LIMIT 20;

-- Reading EXPLAIN output:
-- Seq Scan = full table scan (bad for large tables)
-- Index Scan = using index (good)
-- Bitmap Index Scan = combining multiple indexes
-- Hash Join vs Nested Loop vs Merge Join
-- Rows: estimated vs actual (large diff = stale stats)

-- Composite index for the query above:
CREATE INDEX CONCURRENTLY idx_orders_user_date
ON orders (user_id, created_at DESC)
WHERE created_at >= NOW() - INTERVAL '90 days';  -- Partial index

-- Covering index (includes all needed columns):
CREATE INDEX CONCURRENTLY idx_orders_covering
ON orders (user_id, created_at) INCLUDE (total, id);
-- Index-only scan: no table lookup needed
```

```python
# Common anti-patterns and fixes
class QueryOptimizer:
    """Common query optimization patterns."""

    # Anti-pattern 1: N+1 queries
    # BAD: for user in users: get_orders(user.id)
    # GOOD: Single JOIN or subquery

    async def get_users_with_orders_bad(self, db):
        """N+1: 1 query for users + N queries for orders."""
        users = await db.fetch("SELECT * FROM users LIMIT 100")
        for user in users:  # 100 additional queries!
            user["orders"] = await db.fetch(
                "SELECT * FROM orders WHERE user_id = $1", user["id"]
            )
        return users

    async def get_users_with_orders_good(self, db):
        """Single query with JOIN."""
        return await db.fetch("""
            SELECT u.*, json_agg(o.*) as orders
            FROM users u
            LEFT JOIN orders o ON o.user_id = u.id
            GROUP BY u.id
            LIMIT 100
        """)

    # Anti-pattern 2: SELECT *
    # BAD: SELECT * FROM users (fetches all columns including blobs)
    # GOOD: SELECT id, name, email FROM users

    # Anti-pattern 3: Functions on indexed columns
    # BAD: WHERE LOWER(email) = 'user@example.com'
    # GOOD: CREATE INDEX idx_email_lower ON users (LOWER(email));
    #   OR: WHERE email = 'user@example.com' (case-insensitive collation)

    # Anti-pattern 4: Large OFFSET
    # BAD: SELECT * FROM orders ORDER BY id OFFSET 100000 LIMIT 20
    # GOOD: SELECT * FROM orders WHERE id > $last_id ORDER BY id LIMIT 20

    async def connection_pool_config(self):
        """Connection pool sizing guidelines."""
        import asyncpg
        # Rule of thumb: connections = (2 * CPU cores) + disk spindles
        # For SSD: connections ≈ CPU cores * 2-4
        # Too many connections = context switching overhead
        pool = await asyncpg.create_pool(
            dsn="postgresql://localhost/mydb",
            min_size=5,        # Keep 5 warm connections
            max_size=20,       # Max 20 concurrent connections
            max_inactive_connection_lifetime=300,  # Close idle after 5 min
            command_timeout=30,  # Query timeout
        )
        return pool
```

Key patterns:
1. **EXPLAIN ANALYZE** — real execution plan with actual timings; first debugging step
2. **Composite indexes** — match query WHERE + ORDER BY; column order matters
3. **Covering indexes** — INCLUDE columns avoid table lookup; index-only scan
4. **N+1 elimination** — JOIN or json_agg instead of loop queries; single round-trip
5. **Keyset pagination** — WHERE id > last_id instead of OFFSET; O(log n) vs O(n)'''
    ),
    (
        "database/connection-pooling",
        "Show database connection pooling: PgBouncer, application-level pooling, and pool sizing strategies.",
        '''Database connection pooling:

```python
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Any
from collections import deque


@dataclass
class PoolStats:
    total_connections: int = 0
    idle_connections: int = 0
    active_connections: int = 0
    waiting_requests: int = 0
    total_acquired: int = 0
    total_timeouts: int = 0
    avg_wait_ms: float = 0


class ConnectionPool:
    """Application-level connection pool with monitoring."""

    def __init__(self, dsn: str, min_size: int = 5, max_size: int = 20,
                 acquire_timeout: float = 10.0):
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self.acquire_timeout = acquire_timeout

        self._idle: deque = deque()
        self._active: set = set()
        self._waiters: deque = deque()
        self._total_created = 0
        self._total_acquired = 0
        self._total_wait_time = 0.0

    async def initialize(self):
        """Pre-create minimum connections."""
        for _ in range(self.min_size):
            conn = await self._create_connection()
            self._idle.append(conn)

    async def acquire(self):
        """Get a connection from the pool."""
        start = time.perf_counter()

        # Try to get idle connection
        while self._idle:
            conn = self._idle.popleft()
            if await self._is_healthy(conn):
                self._active.add(conn)
                self._record_acquire(start)
                return conn
            else:
                await self._close_connection(conn)

        # Create new if under max
        if self._total_created < self.max_size:
            conn = await self._create_connection()
            self._active.add(conn)
            self._record_acquire(start)
            return conn

        # Wait for a connection to be released
        waiter = asyncio.get_event_loop().create_future()
        self._waiters.append(waiter)
        try:
            conn = await asyncio.wait_for(waiter, self.acquire_timeout)
            self._active.add(conn)
            self._record_acquire(start)
            return conn
        except asyncio.TimeoutError:
            self._waiters.remove(waiter) if waiter in self._waiters else None
            raise PoolExhaustedError("Connection pool exhausted")

    async def release(self, conn):
        """Return connection to pool."""
        self._active.discard(conn)

        if self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_result(conn)
                return

        if len(self._idle) < self.max_size:
            self._idle.append(conn)
        else:
            await self._close_connection(conn)

    def stats(self) -> PoolStats:
        avg_wait = (self._total_wait_time / self._total_acquired * 1000
                    if self._total_acquired else 0)
        return PoolStats(
            total_connections=self._total_created,
            idle_connections=len(self._idle),
            active_connections=len(self._active),
            waiting_requests=len(self._waiters),
            total_acquired=self._total_acquired,
            avg_wait_ms=round(avg_wait, 2),
        )

    def _record_acquire(self, start: float):
        self._total_acquired += 1
        self._total_wait_time += time.perf_counter() - start

    async def _create_connection(self):
        self._total_created += 1
        return await asyncio.sleep(0)  # Placeholder

    async def _close_connection(self, conn):
        self._total_created -= 1

    async def _is_healthy(self, conn) -> bool:
        return True  # SELECT 1 health check


class PoolExhaustedError(Exception):
    pass
```

Key patterns:
1. **Min/max sizing** — pre-warm minimum connections; cap maximum to prevent DB overload
2. **Waiter queue** — when pool exhausted, queue requests instead of failing immediately
3. **Health checks** — validate idle connections before reuse; discard stale connections
4. **Acquire timeout** — bounded wait time; fail fast if pool is overwhelmed
5. **Stats tracking** — monitor pool utilization; tune min/max based on actual usage'''
    ),
]
"""
