"""Advanced database patterns — indexing, query optimization, replication, sharding, migrations."""

PAIRS = [
    (
        "databases/indexing-deep-dive",
        "Explain database indexing in depth: B-tree vs hash vs GIN vs GiST indexes, covering indexes, partial indexes, and index-only scans in PostgreSQL.",
        '''Database indexing strategies for query optimization:

```sql
-- === B-tree Index (default, most common) ===
-- Good for: equality, range, sorting, prefix LIKE
CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_orders_date ON orders (created_at DESC);

-- Composite index (column order matters!)
-- Supports: WHERE status = X AND created_at > Y
-- Supports: WHERE status = X (leftmost prefix)
-- Does NOT support: WHERE created_at > Y alone
CREATE INDEX idx_orders_status_date ON orders (status, created_at DESC);

-- === Covering Index (index-only scans) ===
-- Include columns in index to avoid table lookup
CREATE INDEX idx_orders_covering ON orders (user_id)
    INCLUDE (total, status, created_at);
-- Query can be answered entirely from index:
-- SELECT total, status FROM orders WHERE user_id = 123;

-- === Partial Index (filter subset) ===
-- Only index rows matching a condition
CREATE INDEX idx_orders_active ON orders (created_at)
    WHERE status = 'pending';
-- Smaller index, faster for filtered queries
-- SELECT * FROM orders WHERE status = 'pending' AND created_at > '2024-01-01';

-- === Expression Index ===
CREATE INDEX idx_users_lower_email ON users (LOWER(email));
-- Supports: WHERE LOWER(email) = 'alice@example.com'

CREATE INDEX idx_orders_year ON orders ((EXTRACT(YEAR FROM created_at)));

-- === GIN Index (Generalized Inverted Index) ===
-- Good for: arrays, JSONB, full-text search, tsvector
CREATE INDEX idx_products_tags ON products USING GIN (tags);
-- Supports: WHERE tags @> ARRAY['electronics', 'sale']

CREATE INDEX idx_events_data ON events USING GIN (metadata jsonb_path_ops);
-- Supports: WHERE metadata @> '{"type": "click"}'

-- Full-text search
CREATE INDEX idx_articles_search ON articles USING GIN (
    to_tsvector('english', title || ' ' || body)
);

-- === GiST Index (Generalized Search Tree) ===
-- Good for: geometric, range types, nearest-neighbor
CREATE INDEX idx_locations_point ON locations USING GIST (coordinates);
-- Supports: WHERE coordinates <-> point(40.7, -74.0) < 0.1
-- ORDER BY coordinates <-> point(40.7, -74.0) LIMIT 10

CREATE INDEX idx_events_during ON events USING GIST (
    tstzrange(start_time, end_time)
);
-- Supports: WHERE tstzrange(start_time, end_time) && tstzrange('2024-03-01', '2024-03-31')

-- === BRIN Index (Block Range Index) ===
-- Good for: naturally ordered data (time series, sequential IDs)
-- Very small index, great for append-only tables
CREATE INDEX idx_logs_timestamp ON logs USING BRIN (created_at)
    WITH (pages_per_range = 128);

-- === Index maintenance ===
-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;  -- Low scan count = potentially unused

-- Check index size
SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass))
FROM pg_indexes WHERE tablename = 'orders';

-- Reindex (fix bloat after heavy updates)
REINDEX INDEX CONCURRENTLY idx_orders_status_date;

-- Create index without locking writes
CREATE INDEX CONCURRENTLY idx_new ON orders (column);
```

Index selection guide:
| Query Pattern | Index Type | Example |
|---------------|-----------|---------|
| Equality/range | B-tree | `WHERE id = 1`, `WHERE date > X` |
| Array containment | GIN | `WHERE tags @> ARRAY['x']` |
| JSONB queries | GIN | `WHERE data @> '{"k": "v"}'` |
| Full-text search | GIN | `WHERE tsv @@ to_tsquery('word')` |
| Geometric/spatial | GiST | `WHERE point <-> ref < distance` |
| Time series (ordered) | BRIN | `WHERE timestamp > X` |
| Exact match only | Hash | `WHERE status = 'active'` |'''
    ),
    (
        "databases/query-optimization",
        "Show how to analyze and optimize slow PostgreSQL queries using EXPLAIN ANALYZE, common query anti-patterns, and optimization techniques.",
        '''PostgreSQL query optimization with EXPLAIN ANALYZE:

```sql
-- === Reading EXPLAIN ANALYZE output ===

EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT o.id, o.total, u.name, u.email
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE o.status = 'pending'
  AND o.created_at > '2024-01-01'
ORDER BY o.created_at DESC
LIMIT 20;

/*
Output:
Limit (cost=1234.56..1234.78 rows=20 width=64) (actual time=45.2..45.3 rows=20 loops=1)
  -> Sort (cost=1234.56..1245.67 rows=5000 width=64) (actual time=45.1..45.2 rows=20 loops=1)
        Sort Key: o.created_at DESC
        Sort Method: top-N heapsort  Memory: 28kB
        -> Hash Join (cost=100.00..1100.00 rows=5000 width=64) (actual time=5.1..40.2 rows=4800 loops=1)
              Hash Cond: (o.user_id = u.id)
              -> Seq Scan on orders o (cost=0.00..900.00 rows=5000 width=32) (actual time=0.1..30.5 rows=4800 loops=1)
                    Filter: (status = 'pending' AND created_at > '2024-01-01')
                    Rows Removed by Filter: 95200
              -> Hash (cost=80.00..80.00 rows=2000 width=32) (actual time=4.8..4.8 rows=2000 loops=1)
                    Buckets: 2048  Batches: 1  Memory Usage: 120kB
                    -> Seq Scan on users u (cost=0.00..80.00 rows=2000 width=32) (actual time=0.01..2.1 rows=2000 loops=1)
Planning Time: 0.3ms
Execution Time: 45.5ms
Buffers: shared hit=800 read=200
*/

-- RED FLAGS in EXPLAIN:
-- 1. Seq Scan on large table with low selectivity filter
-- 2. "Rows Removed by Filter" >> actual rows (bad filtering)
-- 3. Nested Loop with high loop count (missing index on join)
-- 4. Sort on disk ("Sort Method: external merge")
-- 5. Large "shared read" count (data not in cache)

-- === Optimization: Add index ===
CREATE INDEX CONCURRENTLY idx_orders_status_date
    ON orders (status, created_at DESC)
    INCLUDE (total, user_id);

-- After index:
-- Index Scan using idx_orders_status_date → 0.5ms (was 30ms Seq Scan)

-- === Common anti-patterns ===

-- BAD: Function on indexed column prevents index use
SELECT * FROM users WHERE LOWER(email) = 'alice@test.com';
-- FIX: Expression index or store normalized
CREATE INDEX idx_users_email_lower ON users (LOWER(email));

-- BAD: Implicit type cast prevents index use
SELECT * FROM orders WHERE id = '123';  -- id is integer, '123' is text
-- FIX: Use correct type
SELECT * FROM orders WHERE id = 123;

-- BAD: OR conditions on different columns
SELECT * FROM orders WHERE user_id = 1 OR status = 'pending';
-- FIX: Use UNION
SELECT * FROM orders WHERE user_id = 1
UNION ALL
SELECT * FROM orders WHERE status = 'pending' AND user_id != 1;

-- BAD: SELECT * (fetches unnecessary columns)
SELECT * FROM orders WHERE id = 1;
-- FIX: Select only needed columns (enables index-only scan)
SELECT id, total, status FROM orders WHERE id = 1;

-- BAD: N+1 queries in application code
-- for user in users:
--     orders = db.query("SELECT * FROM orders WHERE user_id = %s", user.id)
-- FIX: Single query with JOIN or IN
SELECT u.*, o.* FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.id IN (1, 2, 3, 4, 5);

-- === Pagination optimization ===

-- BAD: OFFSET for deep pages (scans and discards rows)
SELECT * FROM orders ORDER BY id LIMIT 20 OFFSET 100000;
-- Scans 100,020 rows, returns 20

-- GOOD: Keyset/cursor pagination
SELECT * FROM orders
WHERE id > 100000  -- Last seen ID
ORDER BY id
LIMIT 20;
-- Scans only 20 rows using index

-- === Batch operations ===

-- BAD: Individual inserts
INSERT INTO events (type, data) VALUES ('click', '{}');
INSERT INTO events (type, data) VALUES ('view', '{}');
-- 1000 inserts = 1000 round trips

-- GOOD: Batch insert
INSERT INTO events (type, data) VALUES
    ('click', '{}'),
    ('view', '{}'),
    ... ;
-- Or use COPY for bulk loading (fastest)
COPY events (type, data) FROM STDIN WITH (FORMAT csv);
```

Optimization checklist:
1. **EXPLAIN ANALYZE** every slow query
2. **Index** columns in WHERE, JOIN, ORDER BY
3. **Covering indexes** for frequently accessed column sets
4. **Keyset pagination** instead of OFFSET
5. **Batch operations** instead of individual queries
6. **Connection pooling** (PgBouncer) for many short-lived connections'''
    ),
    (
        "databases/replication-patterns",
        "Explain database replication patterns: primary-replica, multi-primary, conflict resolution, and read/write splitting.",
        '''Database replication for high availability and read scaling:

```python
from dataclasses import dataclass
from typing import Optional
import random

# --- Read/Write Splitting ---

@dataclass
class DatabaseConfig:
    primary_url: str
    replica_urls: list[str]
    max_replica_lag_seconds: float = 5.0

class ReadWriteSplitter:
    """Route reads to replicas, writes to primary."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.primary_pool = create_pool(config.primary_url)
        self.replica_pools = [create_pool(url) for url in config.replica_urls]
        self.round_robin_index = 0

    def get_write_connection(self):
        """Always use primary for writes."""
        return self.primary_pool.acquire()

    def get_read_connection(self, allow_stale: bool = True):
        """Route reads to a healthy replica."""
        if not allow_stale or not self.replica_pools:
            return self.primary_pool.acquire()

        # Round-robin across replicas
        pool = self.replica_pools[self.round_robin_index % len(self.replica_pools)]
        self.round_robin_index += 1
        return pool.acquire()

    async def get_read_connection_with_lag_check(self, max_lag: float = None):
        """Only use replicas within acceptable lag."""
        max_lag = max_lag or self.config.max_replica_lag_seconds

        for pool in self.replica_pools:
            async with pool.acquire() as conn:
                # Check replication lag
                lag = await conn.fetchval("""
                    SELECT EXTRACT(EPOCH FROM (NOW() - pg_last_xact_replay_timestamp()))
                """)
                if lag is not None and lag <= max_lag:
                    return pool.acquire()

        # All replicas too laggy, fall back to primary
        return self.primary_pool.acquire()

# --- Read-your-writes consistency ---

class SessionConsistency:
    """Ensure user sees their own writes."""

    def __init__(self, splitter: ReadWriteSplitter, cache):
        self.splitter = splitter
        self.cache = cache

    async def write(self, session_id: str, query: str, params=None):
        """Write to primary and record timestamp."""
        async with self.splitter.get_write_connection() as conn:
            result = await conn.execute(query, *params)
        # Record write timestamp for this session
        await self.cache.setex(
            f"last_write:{session_id}",
            30,  # TTL: 30 seconds
            str(time.time()),
        )
        return result

    async def read(self, session_id: str, query: str, params=None):
        """Read from replica unless recent write by this session."""
        last_write = await self.cache.get(f"last_write:{session_id}")
        if last_write:
            # Recent write — read from primary for consistency
            conn_ctx = self.splitter.get_write_connection()
        else:
            conn_ctx = self.splitter.get_read_connection()

        async with conn_ctx as conn:
            return await conn.fetch(query, *params)

# --- Conflict resolution for multi-primary ---

class ConflictResolver:
    """Resolve conflicts in multi-primary replication."""

    @staticmethod
    def last_writer_wins(local_row: dict, remote_row: dict) -> dict:
        """Simple: most recent update wins."""
        if local_row["updated_at"] >= remote_row["updated_at"]:
            return local_row
        return remote_row

    @staticmethod
    def merge_fields(local_row: dict, remote_row: dict,
                     base_row: dict) -> dict:
        """Three-way merge: merge non-conflicting field changes."""
        merged = dict(base_row)
        conflicts = []

        for field in base_row:
            local_changed = local_row.get(field) != base_row.get(field)
            remote_changed = remote_row.get(field) != base_row.get(field)

            if local_changed and remote_changed:
                if local_row[field] == remote_row[field]:
                    merged[field] = local_row[field]  # Same change, no conflict
                else:
                    conflicts.append(field)
                    merged[field] = local_row[field]  # Default to local
            elif local_changed:
                merged[field] = local_row[field]
            elif remote_changed:
                merged[field] = remote_row[field]

        if conflicts:
            merged["_conflicts"] = conflicts
        return merged

    @staticmethod
    def crdt_counter(local_value: dict, remote_value: dict) -> dict:
        """CRDT G-Counter: merge by taking max per node."""
        # Each node maintains its own counter
        # {node_id: count}
        merged = dict(local_value)
        for node, count in remote_value.items():
            merged[node] = max(merged.get(node, 0), count)
        return merged
```

Replication patterns:
| Pattern | Consistency | Write Perf | Read Scale | Failover |
|---------|------------|-----------|------------|----------|
| Primary-Replica (async) | Eventual | High | Linear | Promote replica |
| Primary-Replica (sync) | Strong | Lower | Linear | Automatic |
| Multi-Primary | Eventual | Highest | N/A | Built-in |
| Quorum (Cassandra) | Tunable | Medium | Linear | N/A |

Key concepts:
- **Replication lag** — delay between primary write and replica update
- **Split brain** — two nodes think they're primary (use fencing)
- **Failover** — promote replica to primary on failure
- **Read-your-writes** — route reads to primary after writes'''
    ),
    (
        "databases/sharding-strategies",
        "Explain database sharding: hash vs range partitioning, shard key selection, cross-shard queries, and resharding strategies.",
        '''Database sharding for horizontal scaling:

```python
import hashlib
from dataclasses import dataclass
from typing import Optional

# --- Shard Router ---

@dataclass
class ShardConfig:
    shard_id: int
    host: str
    port: int
    database: str

class ShardRouter:
    """Route queries to the correct shard."""

    def __init__(self, shards: list[ShardConfig]):
        self.shards = {s.shard_id: s for s in shards}
        self.num_shards = len(shards)
        self.pools = {}

    # --- Hash-based sharding ---

    def get_shard_hash(self, shard_key: str) -> ShardConfig:
        """Consistent hash-based routing."""
        hash_val = int(hashlib.md5(str(shard_key).encode()).hexdigest(), 16)
        shard_id = hash_val % self.num_shards
        return self.shards[shard_id]

    # --- Range-based sharding ---

    def get_shard_range(self, value: int, ranges: list[tuple[int, int, int]]) -> ShardConfig:
        """Range-based routing (e.g., by date or ID range).
        ranges: [(min_val, max_val, shard_id), ...]
        """
        for min_val, max_val, shard_id in ranges:
            if min_val <= value <= max_val:
                return self.shards[shard_id]
        raise ValueError(f"No shard for value {value}")

    # --- Shard-aware queries ---

    async def query_single_shard(self, shard_key: str, query: str, params=None):
        """Query a single shard (most efficient)."""
        shard = self.get_shard_hash(shard_key)
        pool = self._get_pool(shard)
        async with pool.acquire() as conn:
            return await conn.fetch(query, *(params or []))

    async def query_all_shards(self, query: str, params=None):
        """Fan-out query to all shards (expensive but sometimes needed)."""
        import asyncio
        tasks = []
        for shard in self.shards.values():
            pool = self._get_pool(shard)
            tasks.append(self._query_shard(pool, query, params))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge results
        merged = []
        for result in results:
            if isinstance(result, Exception):
                raise result
            merged.extend(result)
        return merged

    async def scatter_gather(self, query: str, params=None,
                              order_by: str = None, limit: int = None):
        """Scatter query to all shards, gather and merge results."""
        all_results = await self.query_all_shards(query, params)

        if order_by:
            reverse = order_by.endswith(" DESC")
            key = order_by.replace(" DESC", "").replace(" ASC", "").strip()
            all_results.sort(key=lambda r: r[key], reverse=reverse)

        if limit:
            all_results = all_results[:limit]

        return all_results

# --- Shard key selection ---

SHARD_KEY_GUIDE = """
Good shard keys:
- user_id: Even distribution, queries naturally scoped to user
- tenant_id: Multi-tenant SaaS, all tenant data on one shard
- order_id: If queries primarily by order

Bad shard keys:
- created_at: Range-based creates hot shards (newest shard gets all writes)
- country: Uneven distribution (US shard much larger)
- status: Only a few values, very uneven

Properties of a good shard key:
1. High cardinality (many distinct values)
2. Even distribution (no hot shards)
3. Query affinity (most queries include the key)
4. Immutable (changing shard key = moving data)
"""

# --- Resharding (adding shards) ---

class ReshardManager:
    """Manage adding new shards with minimal downtime."""

    async def add_shard(self, new_shard: ShardConfig, router: ShardRouter):
        """Double-write strategy for adding shards."""

        # Phase 1: Start double-writing to old and new shard
        # New writes go to both old location AND new location
        router.enable_double_write(new_shard)

        # Phase 2: Backfill — copy existing data that should be on new shard
        for old_shard in router.shards.values():
            await self._migrate_data(old_shard, new_shard, router)

        # Phase 3: Verify — compare data between old and new locations
        await self._verify_migration(router)

        # Phase 4: Switch reads to new shard mapping
        router.update_shard_map(new_shard)

        # Phase 5: Stop double-writing, clean up old data
        router.disable_double_write()
        await self._cleanup_old_data(router)

    async def _migrate_data(self, source, target, router):
        """Incrementally migrate data with checkpointing."""
        last_id = 0
        batch_size = 1000

        while True:
            rows = await source.fetch(
                "SELECT * FROM data WHERE id > $1 ORDER BY id LIMIT $2",
                last_id, batch_size,
            )
            if not rows:
                break

            for row in rows:
                new_shard = router.get_shard_hash(str(row["shard_key"]))
                if new_shard.shard_id == target.shard_id:
                    await target.execute("INSERT INTO data ... ON CONFLICT DO NOTHING", row)

            last_id = rows[-1]["id"]
```

Sharding tradeoffs:
| Aspect | Single DB | Sharded |
|--------|-----------|---------|
| Joins | Easy | Cross-shard = expensive |
| Transactions | ACID | Distributed = complex |
| Aggregations | Easy | Scatter-gather required |
| Operations | Simple | Complex (backups, migrations) |
| Scale | Vertical | Horizontal (theoretically infinite) |

Rule of thumb: don't shard until you absolutely must. Optimize queries,
add read replicas, and partition within a single DB first.'''
    ),
]
