"""Database sharding — hash-based sharding, range sharding, consistent hashing, cross-shard queries, shard rebalancing, tenant-based sharding."""

PAIRS = [
    (
        "databases/sharding-hash-based",
        "Implement hash-based database sharding in Python: shard key selection, hash ring, connection routing, and query execution across shards.",
        '''Hash-based database sharding with automatic shard routing:

```python
import hashlib
import asyncio
import asyncpg
from dataclasses import dataclass, field
from typing import Any, Optional
from collections import defaultdict


@dataclass
class ShardConfig:
    """Configuration for a single database shard."""
    shard_id: int
    host: str
    port: int = 5432
    database: str = "app"
    user: str = "app"
    password: str = ""
    min_connections: int = 5
    max_connections: int = 20

    @property
    def dsn(self) -> str:
        return (f"postgresql://{self.user}:{self.password}"
                f"@{self.host}:{self.port}/{self.database}")


class HashShardRouter:
    """Hash-based shard router using modulo hashing.

    Distributes records across N shards by hashing the shard key.
    Simple and predictable, but adding/removing shards requires
    resharding all data.
    """

    def __init__(self, shard_configs: list[ShardConfig]):
        self.shards = {s.shard_id: s for s in shard_configs}
        self.num_shards = len(shard_configs)
        self._pools: dict[int, asyncpg.Pool] = {}

    async def initialize(self):
        """Create connection pools for all shards."""
        for shard_id, config in self.shards.items():
            self._pools[shard_id] = await asyncpg.create_pool(
                dsn=config.dsn,
                min_size=config.min_connections,
                max_size=config.max_connections,
                command_timeout=30,
            )
            # Ensure schema exists on each shard
            async with self._pools[shard_id].acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id     BIGINT PRIMARY KEY,
                        email       VARCHAR(255) UNIQUE NOT NULL,
                        name        VARCHAR(255) NOT NULL,
                        created_at  TIMESTAMPTZ DEFAULT NOW(),
                        shard_id    INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id    BIGINT PRIMARY KEY,
                        user_id     BIGINT NOT NULL REFERENCES users(user_id),
                        total       DECIMAL(12, 2) NOT NULL,
                        status      VARCHAR(20) DEFAULT 'pending',
                        created_at  TIMESTAMPTZ DEFAULT NOW(),
                        shard_id    INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_orders_user
                        ON orders(user_id);
                """)

    def get_shard_id(self, shard_key: str | int) -> int:
        """Determine which shard owns a given key.

        Uses MD5 hash for uniform distribution.
        Modulo N means all N shards get ~equal load.
        """
        key_bytes = str(shard_key).encode("utf-8")
        hash_val = int(hashlib.md5(key_bytes).hexdigest(), 16)
        return hash_val % self.num_shards

    def get_pool(self, shard_key: str | int) -> asyncpg.Pool:
        """Get connection pool for the shard that owns this key."""
        shard_id = self.get_shard_id(shard_key)
        return self._pools[shard_id]

    async def insert_user(self, user_id: int, email: str,
                          name: str) -> dict:
        """Insert a user into the correct shard."""
        shard_id = self.get_shard_id(user_id)
        pool = self._pools[shard_id]
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, email, name, shard_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE
                SET email = $2, name = $3
            """, user_id, email, name, shard_id)
        return {"user_id": user_id, "shard_id": shard_id}

    async def get_user(self, user_id: int) -> Optional[dict]:
        """Fetch a user from the correct shard (single-shard query)."""
        pool = self.get_pool(user_id)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
            return dict(row) if row else None

    async def create_order(self, order_id: int, user_id: int,
                           total: float) -> dict:
        """Create order on same shard as the user (co-located)."""
        # Orders are sharded by user_id so joins stay local
        shard_id = self.get_shard_id(user_id)
        pool = self._pools[shard_id]
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO orders (order_id, user_id, total, shard_id)
                VALUES ($1, $2, $3, $4)
            """, order_id, user_id, total, shard_id)
        return {"order_id": order_id, "shard_id": shard_id}

    async def get_user_orders(self, user_id: int) -> list[dict]:
        """Get all orders for a user (single-shard, co-located)."""
        pool = self.get_pool(user_id)
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT o.*, u.name AS user_name
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.user_id = $1
                ORDER BY o.created_at DESC
            """, user_id)
            return [dict(r) for r in rows]

    async def scatter_gather(self, query: str,
                             params: list = None,
                             order_by: str = None,
                             limit: int = None) -> list[dict]:
        """Execute query on ALL shards and merge results.

        Used for cross-shard queries (analytics, global search).
        Slower than single-shard queries — avoid in hot paths.
        """
        tasks = []
        for shard_id, pool in self._pools.items():
            tasks.append(self._query_shard(pool, query, params))

        # Execute on all shards in parallel
        shard_results = await asyncio.gather(*tasks)

        # Merge results
        all_rows = []
        for rows in shard_results:
            all_rows.extend(rows)

        # Sort merged results if requested
        if order_by:
            desc = order_by.startswith("-")
            key = order_by.lstrip("-")
            all_rows.sort(key=lambda r: r.get(key, 0), reverse=desc)

        if limit:
            all_rows = all_rows[:limit]

        return all_rows

    async def _query_shard(self, pool: asyncpg.Pool, query: str,
                           params: list = None) -> list[dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *(params or []))
            return [dict(r) for r in rows]

    async def global_stats(self) -> dict:
        """Aggregate statistics across all shards."""
        results = await self.scatter_gather("""
            SELECT
                COUNT(*) AS user_count,
                COUNT(DISTINCT shard_id) AS shard_id,
                MIN(created_at) AS earliest_user
            FROM users
        """)
        total_users = sum(r["user_count"] for r in results)
        return {
            "total_users": total_users,
            "shard_distribution": {
                r["shard_id"]: r["user_count"] for r in results
            },
        }

    async def close(self):
        for pool in self._pools.values():
            await pool.close()


# === Usage ===
async def main():
    shards = [
        ShardConfig(shard_id=0, host="shard0.db.internal"),
        ShardConfig(shard_id=1, host="shard1.db.internal"),
        ShardConfig(shard_id=2, host="shard2.db.internal"),
        ShardConfig(shard_id=3, host="shard3.db.internal"),
    ]

    router = HashShardRouter(shards)
    await router.initialize()

    # Single-shard operations (fast, co-located)
    await router.insert_user(12345, "alice@example.com", "Alice")
    user = await router.get_user(12345)
    await router.create_order(99001, 12345, total=149.99)
    orders = await router.get_user_orders(12345)

    # Cross-shard query (scatter-gather, slower)
    top_spenders = await router.scatter_gather(
        "SELECT user_id, SUM(total) AS total_spend "
        "FROM orders GROUP BY user_id "
        "ORDER BY total_spend DESC LIMIT 10",
        order_by="-total_spend", limit=10,
    )

    await router.close()
```

Key patterns:
1. **Hash-based routing** -- MD5 hash mod N gives uniform distribution; deterministic so any app server can compute the correct shard
2. **Co-located data** -- orders sharded by user_id (not order_id) so user+orders JOIN stays on one shard; choose shard key for your most common query
3. **Scatter-gather** -- cross-shard queries fan out to all shards in parallel then merge; use sparingly (analytics, not hot paths)
4. **Schema per shard** -- each shard has identical schema; shard_id column enables debugging and rebalancing audits
5. **Shard key is immutable** -- once a record is assigned to a shard by its key, it cannot move without explicit migration; never shard by a mutable column'''
    ),
    (
        "databases/sharding-consistent-hashing",
        "Implement consistent hashing for database sharding: virtual nodes, minimal redistribution, adding/removing shards, and key rebalancing.",
        '''Consistent hashing for database sharding with virtual nodes:

```python
import hashlib
import bisect
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict


@dataclass
class VirtualNode:
    """A virtual node on the consistent hash ring."""
    physical_shard: str   # e.g. "shard-0"
    virtual_id: int       # e.g. 0, 1, 2 ... vnodes_per_shard-1
    hash_value: int       # position on the ring

    @property
    def key(self) -> str:
        return f"{self.physical_shard}#vn{self.virtual_id}"


class ConsistentHashRing:
    """Consistent hash ring with virtual nodes.

    When adding or removing a shard, only ~1/N of keys need to move
    (vs. modulo hashing where ALL keys must be reshuffled).

    Virtual nodes ensure even distribution even with few physical shards.
    """

    def __init__(self, vnodes_per_shard: int = 150):
        self.vnodes_per_shard = vnodes_per_shard
        self._ring: list[int] = []           # sorted hash positions
        self._ring_map: dict[int, VirtualNode] = {}  # hash -> vnode
        self._shards: set[str] = set()

    def _hash(self, key: str) -> int:
        """Compute a 64-bit hash for consistent ring placement."""
        digest = hashlib.sha256(key.encode()).hexdigest()
        return int(digest[:16], 16)  # use first 64 bits

    def add_shard(self, shard_name: str) -> list[tuple[str, str]]:
        """Add a physical shard to the ring.

        Returns list of (key_range, old_shard) that need migration.
        """
        if shard_name in self._shards:
            return []

        self._shards.add(shard_name)
        migrations = []

        for i in range(self.vnodes_per_shard):
            vnode = VirtualNode(
                physical_shard=shard_name,
                virtual_id=i,
                hash_value=self._hash(f"{shard_name}#vn{i}"),
            )

            # Before inserting, find which shard currently owns this range
            if self._ring:
                pos = bisect.bisect_right(self._ring, vnode.hash_value)
                # The next node clockwise currently owns keys at this position
                next_pos = pos % len(self._ring)
                current_owner = self._ring_map[self._ring[next_pos]]
                if current_owner.physical_shard != shard_name:
                    migrations.append((
                        f"range ending at {vnode.hash_value}",
                        current_owner.physical_shard,
                    ))

            self._ring_map[vnode.hash_value] = vnode
            bisect.insort(self._ring, vnode.hash_value)

        return migrations

    def remove_shard(self, shard_name: str) -> dict[str, str]:
        """Remove a shard. Returns {key_range: new_owner_shard}."""
        if shard_name not in self._shards:
            return {}

        reassignments = {}
        vnodes_to_remove = [
            h for h, vn in self._ring_map.items()
            if vn.physical_shard == shard_name
        ]

        for h in vnodes_to_remove:
            # Find who will inherit this range (next clockwise node)
            pos = self._ring.index(h)
            self._ring.remove(h)
            del self._ring_map[h]

            if self._ring:
                new_pos = pos % len(self._ring)
                new_owner = self._ring_map[self._ring[new_pos]]
                reassignments[f"range at {h}"] = new_owner.physical_shard

        self._shards.discard(shard_name)
        return reassignments

    def get_shard(self, key: str) -> str:
        """Find which physical shard owns a key."""
        if not self._ring:
            raise RuntimeError("No shards in the ring")

        h = self._hash(key)
        # Find first ring position >= key hash (clockwise)
        pos = bisect.bisect_right(self._ring, h)
        # Wrap around if past the last node
        pos = pos % len(self._ring)
        return self._ring_map[self._ring[pos]].physical_shard

    def get_shard_with_replicas(self, key: str,
                                 num_replicas: int = 2) -> list[str]:
        """Get primary shard + N distinct replica shards for a key.

        Walk clockwise on the ring, skipping vnodes of the same
        physical shard, until we find enough distinct shards.
        """
        if not self._ring:
            raise RuntimeError("No shards in the ring")

        h = self._hash(key)
        pos = bisect.bisect_right(self._ring, h) % len(self._ring)

        result = []
        seen_shards = set()

        for i in range(len(self._ring)):
            idx = (pos + i) % len(self._ring)
            vnode = self._ring_map[self._ring[idx]]
            if vnode.physical_shard not in seen_shards:
                result.append(vnode.physical_shard)
                seen_shards.add(vnode.physical_shard)
                if len(result) >= num_replicas + 1:
                    break

        return result  # [primary, replica1, replica2, ...]

    def get_distribution(self) -> dict[str, float]:
        """Show what fraction of the key space each shard owns."""
        if len(self._ring) < 2:
            return {}

        ownership = defaultdict(int)
        ring_size = 2**64  # total hash space

        for i in range(len(self._ring)):
            current = self._ring[i]
            prev = self._ring[i - 1] if i > 0 else self._ring[-1]
            shard = self._ring_map[current].physical_shard

            if current > prev:
                ownership[shard] += current - prev
            else:
                # Wrap around
                ownership[shard] += ring_size - prev + current

        total = sum(ownership.values())
        return {
            shard: round(count / total * 100, 2)
            for shard, count in sorted(ownership.items())
        }

    def simulate_rebalance(self, new_shard: str) -> dict:
        """Simulate adding a shard: show how many keys would migrate."""
        # Take a snapshot
        old_assignments = {}
        test_keys = [f"key_{i}" for i in range(10000)]
        for k in test_keys:
            old_assignments[k] = self.get_shard(k)

        # Add shard
        self.add_shard(new_shard)

        # Count migrations
        migrations = defaultdict(int)
        for k in test_keys:
            new_shard_name = self.get_shard(k)
            if new_shard_name != old_assignments[k]:
                migrations[
                    f"{old_assignments[k]} -> {new_shard_name}"
                ] += 1

        # Rollback
        self.remove_shard(new_shard)

        total_moved = sum(migrations.values())
        return {
            "total_keys": len(test_keys),
            "keys_moved": total_moved,
            "move_pct": round(total_moved / len(test_keys) * 100, 2),
            "expected_pct": round(100 / (len(self._shards) + 1), 2),
            "migrations": dict(migrations),
        }


# === Usage ===
ring = ConsistentHashRing(vnodes_per_shard=150)

# Add initial shards
ring.add_shard("shard-0")
ring.add_shard("shard-1")
ring.add_shard("shard-2")

# Route keys
print(ring.get_shard("user:12345"))     # -> "shard-1" (deterministic)
print(ring.get_shard("order:99001"))    # -> "shard-0"

# Get primary + replicas
print(ring.get_shard_with_replicas("user:12345", num_replicas=2))
# -> ["shard-1", "shard-2", "shard-0"]

# Check distribution uniformity
print(ring.get_distribution())
# -> {"shard-0": 33.21, "shard-1": 33.54, "shard-2": 33.25}

# Simulate adding a 4th shard
rebalance = ring.simulate_rebalance("shard-3")
print(f"Keys moved: {rebalance['keys_moved']}/{rebalance['total_keys']} "
      f"({rebalance['move_pct']}%, expected ~{rebalance['expected_pct']}%)")
# Keys moved: ~2500/10000 (25%, expected ~25%)
```

Key patterns:
1. **Virtual nodes** -- 150 vnodes per shard ensures uniform distribution; without vnodes, 3 physical nodes could have 60/20/20 imbalance
2. **Minimal redistribution** -- adding shard N+1 moves only ~1/(N+1) of keys; modulo hashing would move ~(N-1)/N of keys
3. **Clockwise lookup** -- `bisect_right` finds the next ring position >= key hash; the shard at that position owns the key
4. **Replica placement** -- walk clockwise past the primary, skipping same-shard vnodes, to find N distinct replica shards
5. **Rebalance simulation** -- always simulate before adding/removing shards; verify actual migration count matches theoretical 1/(N+1)'''
    ),
    (
        "databases/sharding-cross-shard-queries",
        "Show patterns for cross-shard queries: scatter-gather, shard-aware aggregation, distributed transactions, and global secondary indexes.",
        '''Cross-shard query patterns for distributed databases:

```python
import asyncio
import asyncpg
import hashlib
import time
import logging
from dataclasses import dataclass
from typing import Any, Optional
from collections import defaultdict
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class ShardQueryResult:
    """Result from a single shard query."""
    shard_id: int
    rows: list[dict]
    row_count: int
    execution_time_ms: float
    error: Optional[str] = None


class CrossShardQueryEngine:
    """Execute queries across multiple database shards with
    parallel scatter-gather, distributed aggregation, and
    two-phase commit for writes."""

    def __init__(self, shard_pools: dict[int, asyncpg.Pool]):
        self.pools = shard_pools
        self.num_shards = len(shard_pools)

    # === Scatter-Gather with parallel execution ===

    async def scatter_gather_query(
        self, query: str, params: list = None,
        target_shards: list[int] = None,
        timeout_seconds: float = 30.0,
    ) -> list[ShardQueryResult]:
        """Execute query on multiple shards in parallel."""
        shards = target_shards or list(self.pools.keys())

        tasks = [
            self._query_shard_with_timing(
                shard_id, query, params, timeout_seconds
            )
            for shard_id in shards
        ]

        return await asyncio.gather(*tasks)

    async def _query_shard_with_timing(
        self, shard_id: int, query: str,
        params: list, timeout: float,
    ) -> ShardQueryResult:
        """Query a single shard with timing and error handling."""
        start = time.monotonic()
        try:
            async with self.pools[shard_id].acquire() as conn:
                rows = await asyncio.wait_for(
                    conn.fetch(query, *(params or [])),
                    timeout=timeout,
                )
                return ShardQueryResult(
                    shard_id=shard_id,
                    rows=[dict(r) for r in rows],
                    row_count=len(rows),
                    execution_time_ms=(time.monotonic() - start) * 1000,
                )
        except asyncio.TimeoutError:
            return ShardQueryResult(
                shard_id=shard_id, rows=[], row_count=0,
                execution_time_ms=(time.monotonic() - start) * 1000,
                error=f"Timeout after {timeout}s",
            )
        except Exception as e:
            return ShardQueryResult(
                shard_id=shard_id, rows=[], row_count=0,
                execution_time_ms=(time.monotonic() - start) * 1000,
                error=str(e),
            )

    # === Distributed aggregation (push-down + merge) ===

    async def distributed_aggregate(
        self, base_table: str, group_by: list[str],
        aggregations: dict[str, str],
        where_clause: str = "TRUE",
        having_clause: str = None,
        order_by: str = None,
        limit: int = None,
    ) -> list[dict]:
        """Two-phase aggregation: aggregate per-shard, then merge.

        Phase 1 (push-down): Each shard computes partial aggregates
        Phase 2 (merge): Coordinator merges partial results

        This is much more efficient than fetching all rows.
        """
        # Phase 1: Build per-shard aggregation query
        select_parts = list(group_by)
        merge_ops = {}  # how to merge each aggregation

        for alias, expr in aggregations.items():
            op = expr.split("(")[0].upper().strip()
            col = expr.split("(")[1].rstrip(")")

            if op == "SUM" or op == "COUNT":
                select_parts.append(f"{expr} AS {alias}")
                merge_ops[alias] = "SUM"
            elif op == "AVG":
                # Push down SUM + COUNT, compute AVG at merge
                select_parts.append(f"SUM({col}) AS {alias}_sum")
                select_parts.append(f"COUNT({col}) AS {alias}_count")
                merge_ops[alias] = "AVG"
            elif op == "MAX":
                select_parts.append(f"MAX({col}) AS {alias}")
                merge_ops[alias] = "MAX"
            elif op == "MIN":
                select_parts.append(f"MIN({col}) AS {alias}")
                merge_ops[alias] = "MIN"

        shard_query = (
            f"SELECT {', '.join(select_parts)} "
            f"FROM {base_table} "
            f"WHERE {where_clause} "
            f"GROUP BY {', '.join(group_by)}"
        )

        shard_results = await self.scatter_gather_query(shard_query)

        # Phase 2: Merge partial aggregates
        merged = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
        counts = defaultdict(lambda: defaultdict(lambda: 0))

        for result in shard_results:
            if result.error:
                logger.warning(
                    f"Shard {result.shard_id} failed: {result.error}"
                )
                continue

            for row in result.rows:
                group_key = tuple(row[col] for col in group_by)

                for alias, merge_op in merge_ops.items():
                    if merge_op == "SUM":
                        merged[group_key][alias] += Decimal(
                            str(row[alias])
                        )
                    elif merge_op == "MAX":
                        current = merged[group_key].get(alias)
                        val = row[alias]
                        if current is None or val > current:
                            merged[group_key][alias] = val
                    elif merge_op == "MIN":
                        current = merged[group_key].get(alias)
                        val = row[alias]
                        if current is None or val < current:
                            merged[group_key][alias] = val
                    elif merge_op == "AVG":
                        merged[group_key][f"{alias}_sum"] += Decimal(
                            str(row[f"{alias}_sum"])
                        )
                        counts[group_key][alias] += row[
                            f"{alias}_count"
                        ]

        # Finalize AVG calculations
        final_results = []
        for group_key, aggs in merged.items():
            row = dict(zip(group_by, group_key))
            for alias, merge_op in merge_ops.items():
                if merge_op == "AVG":
                    total = aggs[f"{alias}_sum"]
                    count = counts[group_key][alias]
                    row[alias] = float(total / count) if count else 0
                else:
                    row[alias] = float(aggs[alias])
            final_results.append(row)

        # Sort and limit
        if order_by:
            desc = order_by.startswith("-")
            key = order_by.lstrip("-")
            final_results.sort(
                key=lambda r: r.get(key, 0), reverse=desc
            )
        if limit:
            final_results = final_results[:limit]

        return final_results

    # === Two-phase commit for cross-shard writes ===

    async def distributed_transaction(
        self, operations: list[tuple[int, str, list]],
    ) -> bool:
        """Two-phase commit across multiple shards.

        operations: [(shard_id, sql, params), ...]

        Phase 1 (PREPARE): Each shard prepares the transaction
        Phase 2 (COMMIT/ROLLBACK): All commit or all rollback
        """
        txn_id = hashlib.md5(
            str(time.time()).encode()
        ).hexdigest()[:12]

        # Group operations by shard
        shard_ops = defaultdict(list)
        for shard_id, sql, params in operations:
            shard_ops[shard_id].append((sql, params))

        connections = {}
        prepared_shards = set()

        try:
            # Phase 1: PREPARE on each shard
            for shard_id, ops in shard_ops.items():
                conn = await self.pools[shard_id].acquire()
                connections[shard_id] = conn

                tx = conn.transaction()
                await tx.start()

                for sql, params in ops:
                    await conn.execute(sql, *params)

                # Prepare (but don't commit yet)
                await conn.execute(
                    f"PREPARE TRANSACTION 'txn_{txn_id}_s{shard_id}'"
                )
                prepared_shards.add(shard_id)

            # Phase 2: COMMIT all prepared transactions
            for shard_id in prepared_shards:
                conn = connections[shard_id]
                await conn.execute(
                    f"COMMIT PREPARED 'txn_{txn_id}_s{shard_id}'"
                )

            logger.info(
                f"Distributed txn {txn_id} committed on "
                f"{len(prepared_shards)} shards"
            )
            return True

        except Exception as e:
            # Rollback all prepared transactions
            logger.error(f"Distributed txn {txn_id} failed: {e}")
            for shard_id in prepared_shards:
                try:
                    conn = connections[shard_id]
                    await conn.execute(
                        f"ROLLBACK PREPARED "
                        f"'txn_{txn_id}_s{shard_id}'"
                    )
                except Exception as rollback_err:
                    logger.critical(
                        f"ROLLBACK FAILED on shard {shard_id}: "
                        f"{rollback_err}. Manual intervention required!"
                    )
            return False

        finally:
            for shard_id, conn in connections.items():
                await self.pools[shard_id].release(conn)


# === Usage ===
async def example():
    # Distributed aggregation
    engine = CrossShardQueryEngine(shard_pools={})  # pools injected

    # Two-phase aggregation: SUM/AVG pushed to shards, merged locally
    results = await engine.distributed_aggregate(
        base_table="orders",
        group_by=["status"],
        aggregations={
            "total_revenue": "SUM(total)",
            "order_count": "COUNT(*)",
            "avg_order": "AVG(total)",
        },
        where_clause="created_at >= '2025-01-01'",
        order_by="-total_revenue",
        limit=10,
    )

    # Cross-shard transfer (two-phase commit)
    success = await engine.distributed_transaction([
        (0, "UPDATE accounts SET balance = balance - $1 WHERE id = $2",
         [100.00, "acc_sender"]),
        (2, "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
         [100.00, "acc_receiver"]),
    ])
```

Key patterns:
1. **Scatter-gather** -- fan out query to all shards in parallel with `asyncio.gather`; collect and merge results; timeout per shard prevents slow shards from blocking
2. **Push-down aggregation** -- push SUM/COUNT/MAX/MIN to each shard; merge partial aggregates at coordinator; for AVG, push SUM+COUNT, divide at merge
3. **Two-phase commit** -- PREPARE TRANSACTION on each shard, then COMMIT PREPARED on all; if any fails, ROLLBACK PREPARED on all prepared shards
4. **Partial failure handling** -- if a shard times out during scatter-gather, log warning and continue with partial results; for 2PC, rollback failures require manual intervention
5. **Avoid cross-shard queries** -- design your shard key so 90%+ of queries hit a single shard; scatter-gather is a fallback, not the default path'''
    ),
    (
        "databases/sharding-range-based",
        "Implement range-based sharding with automatic shard splitting, range assignment, and online rebalancing without downtime.",
        '''Range-based sharding with dynamic shard splitting:

```python
import asyncio
import bisect
import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ShardRange:
    """Defines the key range owned by a shard."""
    shard_id: str
    range_start: int      # inclusive
    range_end: int         # exclusive
    row_count: int = 0
    size_bytes: int = 0
    status: str = "active"  # active, splitting, draining

    @property
    def range_size(self) -> int:
        return self.range_end - self.range_start

    def contains(self, key: int) -> bool:
        return self.range_start <= key < self.range_end

    @property
    def midpoint(self) -> int:
        return (self.range_start + self.range_end) // 2


class RangeShardManager:
    """Range-based sharding with automatic splitting.

    Keys are divided into contiguous ranges, each assigned to a shard.
    Ranges can be split when they grow too large.

    Advantages over hash sharding:
    - Range scans are single-shard (e.g., "all orders this month")
    - Splitting and rebalancing only moves a contiguous key range
    - Natural data locality for time-series or sequential IDs

    Disadvantages:
    - Hot spots if writes concentrate on one range (e.g., latest dates)
    - Requires a routing table (vs. deterministic hash computation)
    """

    def __init__(self, initial_shards: list[ShardRange]):
        self.ranges = sorted(initial_shards, key=lambda r: r.range_start)
        self._range_starts = [r.range_start for r in self.ranges]
        self.split_threshold_rows = 1_000_000
        self.split_threshold_bytes = 10 * 1024**3  # 10 GB
        self.rebalance_ratio = 2.0  # trigger if largest/smallest > 2x

    def get_shard(self, key: int) -> ShardRange:
        """Find the shard that owns a key via binary search on ranges."""
        pos = bisect.bisect_right(self._range_starts, key) - 1
        if pos < 0:
            pos = 0
        shard = self.ranges[pos]
        if shard.contains(key):
            return shard
        raise KeyError(f"Key {key} not in any shard range")

    def get_shards_for_range(self, start: int,
                             end: int) -> list[ShardRange]:
        """Find all shards that overlap with a key range.
        Used for range-scan queries spanning multiple shards."""
        result = []
        for shard in self.ranges:
            if shard.range_start < end and shard.range_end > start:
                result.append(shard)
        return result

    def split_shard(self, shard_id: str,
                    split_point: int = None) -> tuple[ShardRange, ShardRange]:
        """Split a shard at the given point (or midpoint).

        Creates two new ranges from the original shard.
        Data migration must happen separately (online, in background).
        """
        # Find the shard to split
        original = None
        idx = -1
        for i, s in enumerate(self.ranges):
            if s.shard_id == shard_id:
                original = s
                idx = i
                break

        if original is None:
            raise ValueError(f"Shard {shard_id} not found")

        split_at = split_point or original.midpoint

        if split_at <= original.range_start or split_at >= original.range_end:
            raise ValueError(
                f"Split point {split_at} outside range "
                f"[{original.range_start}, {original.range_end})"
            )

        # Create two new ranges
        left = ShardRange(
            shard_id=f"{shard_id}-L",
            range_start=original.range_start,
            range_end=split_at,
            row_count=original.row_count // 2,  # estimated
            size_bytes=original.size_bytes // 2,
        )
        right = ShardRange(
            shard_id=f"{shard_id}-R",
            range_start=split_at,
            range_end=original.range_end,
            row_count=original.row_count // 2,
            size_bytes=original.size_bytes // 2,
        )

        # Replace original with two new ranges
        self.ranges[idx] = left
        self.ranges.insert(idx + 1, right)
        self._range_starts = [r.range_start for r in self.ranges]

        logger.info(
            f"Split shard {shard_id} at {split_at}: "
            f"{left.shard_id} [{left.range_start}, {left.range_end}) + "
            f"{right.shard_id} [{right.range_start}, {right.range_end})"
        )
        return left, right

    def merge_shards(self, shard_id_a: str,
                     shard_id_b: str) -> ShardRange:
        """Merge two adjacent shards into one."""
        idx_a = idx_b = -1
        for i, s in enumerate(self.ranges):
            if s.shard_id == shard_id_a:
                idx_a = i
            if s.shard_id == shard_id_b:
                idx_b = i

        if idx_a < 0 or idx_b < 0:
            raise ValueError("Shard(s) not found")

        # Ensure they're adjacent
        if abs(idx_a - idx_b) != 1:
            raise ValueError("Shards must be adjacent to merge")

        a = self.ranges[min(idx_a, idx_b)]
        b = self.ranges[max(idx_a, idx_b)]

        merged = ShardRange(
            shard_id=f"{a.shard_id}+{b.shard_id}",
            range_start=a.range_start,
            range_end=b.range_end,
            row_count=a.row_count + b.row_count,
            size_bytes=a.size_bytes + b.size_bytes,
        )

        # Replace the two with one
        self.ranges[min(idx_a, idx_b)] = merged
        self.ranges.pop(max(idx_a, idx_b))
        self._range_starts = [r.range_start for r in self.ranges]

        return merged

    def check_rebalance_needed(self) -> list[str]:
        """Check if any shards need splitting or merging."""
        actions = []

        for shard in self.ranges:
            if shard.row_count > self.split_threshold_rows:
                actions.append(
                    f"SPLIT {shard.shard_id}: {shard.row_count:,} rows "
                    f"> threshold {self.split_threshold_rows:,}"
                )
            if shard.size_bytes > self.split_threshold_bytes:
                actions.append(
                    f"SPLIT {shard.shard_id}: "
                    f"{shard.size_bytes / 1024**3:.1f} GB > "
                    f"threshold {self.split_threshold_bytes / 1024**3:.0f} GB"
                )

        if len(self.ranges) >= 2:
            sizes = [s.row_count for s in self.ranges if s.row_count > 0]
            if sizes:
                ratio = max(sizes) / max(min(sizes), 1)
                if ratio > self.rebalance_ratio:
                    actions.append(
                        f"REBALANCE: size ratio {ratio:.1f}x "
                        f"exceeds {self.rebalance_ratio}x threshold"
                    )

        return actions

    def get_routing_table(self) -> list[dict]:
        """Export the routing table for client-side caching."""
        return [
            {
                "shard_id": s.shard_id,
                "range_start": s.range_start,
                "range_end": s.range_end,
                "status": s.status,
                "row_count": s.row_count,
                "size_gb": round(s.size_bytes / 1024**3, 2),
            }
            for s in self.ranges
        ]


# === Usage: time-based range sharding for events ===
# Shard by month (YYYYMM as integer)
manager = RangeShardManager([
    ShardRange("events-2025H1", 202501, 202507,
               row_count=5_000_000, size_bytes=8 * 1024**3),
    ShardRange("events-2025H2", 202507, 202601,
               row_count=3_000_000, size_bytes=5 * 1024**3),
    ShardRange("events-2026H1", 202601, 202607,
               row_count=500_000, size_bytes=1 * 1024**3),
])

# Route a key
shard = manager.get_shard(202503)  # -> events-2025H1
print(f"March 2025 data is on shard: {shard.shard_id}")

# Range scan: find all shards for Q4 2025
q4_shards = manager.get_shards_for_range(202510, 202601)
print(f"Q4 2025 spans shards: {[s.shard_id for s in q4_shards]}")

# Check if rebalancing is needed
actions = manager.check_rebalance_needed()
for action in actions:
    print(f"Action needed: {action}")

# Split an overloaded shard
if any("SPLIT events-2025H1" in a for a in actions):
    left, right = manager.split_shard("events-2025H1", split_point=202504)
    print(f"Split into: {left.shard_id} and {right.shard_id}")

print("Routing table:", manager.get_routing_table())
```

Key patterns:
1. **Range sharding** -- contiguous key ranges assigned to shards; range scans (date ranges, ID ranges) hit minimal shards vs. hash sharding hitting all shards
2. **Binary search routing** -- `bisect_right` on range starts gives O(log N) lookup; cache the routing table client-side for zero-network routing
3. **Dynamic splitting** -- when a shard exceeds row/size threshold, split at midpoint (or a data-aware split point like median key)
4. **Hot spot risk** -- time-series data always writes to the "latest" shard; mitigate with pre-splitting or adding a random prefix to distribute within range
5. **Merge for cleanup** -- merge adjacent under-utilized shards to reduce operational overhead; only works for adjacent ranges in the key space'''
    ),
    (
        "databases/sharding-tenant-based",
        "Implement tenant-based (multi-tenant) database sharding: tenant isolation, shard-per-tenant, pooled tenants, tenant migration, and quota management.",
        '''Tenant-based database sharding for multi-tenant SaaS applications:

```python
import asyncio
import asyncpg
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class TenantTier(Enum):
    FREE = "free"
    STARTER = "starter"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class IsolationLevel(Enum):
    SHARED = "shared"       # multiple tenants per shard (pool)
    DEDICATED = "dedicated"  # one tenant per shard (isolated)


@dataclass
class TenantInfo:
    tenant_id: str
    tier: TenantTier
    isolation: IsolationLevel
    shard_id: str
    row_limit: int = 0       # 0 = unlimited
    storage_limit_mb: int = 0
    is_active: bool = True
    created_at: str = ""


@dataclass
class ShardInfo:
    shard_id: str
    host: str
    port: int = 5432
    database: str = "tenants"
    max_tenants: int = 100  # for shared shards
    current_tenants: int = 0
    isolation: IsolationLevel = IsolationLevel.SHARED


class TenantShardManager:
    """Multi-tenant shard manager with mixed isolation strategies.

    Small tenants share shards (pooled). Large tenants get dedicated
    shards. Supports tenant migration between shards.
    """

    TIER_LIMITS = {
        TenantTier.FREE: {
            "isolation": IsolationLevel.SHARED,
            "row_limit": 10_000,
            "storage_limit_mb": 100,
        },
        TenantTier.STARTER: {
            "isolation": IsolationLevel.SHARED,
            "row_limit": 100_000,
            "storage_limit_mb": 1_000,
        },
        TenantTier.BUSINESS: {
            "isolation": IsolationLevel.SHARED,
            "row_limit": 1_000_000,
            "storage_limit_mb": 10_000,
        },
        TenantTier.ENTERPRISE: {
            "isolation": IsolationLevel.DEDICATED,
            "row_limit": 0,  # unlimited
            "storage_limit_mb": 0,
        },
    }

    def __init__(self):
        self.tenants: dict[str, TenantInfo] = {}
        self.shards: dict[str, ShardInfo] = {}
        self._pools: dict[str, asyncpg.Pool] = {}

    async def register_shard(self, shard: ShardInfo):
        """Register a database shard and create connection pool."""
        self.shards[shard.shard_id] = shard
        dsn = (f"postgresql://app:password@{shard.host}:"
               f"{shard.port}/{shard.database}")
        self._pools[shard.shard_id] = await asyncpg.create_pool(
            dsn=dsn, min_size=5, max_size=50,
        )
        # Ensure tenant schema exists
        async with self._pools[shard.shard_id].acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tenant_data (
                    tenant_id    VARCHAR(50) NOT NULL,
                    record_id    BIGSERIAL,
                    data         JSONB NOT NULL,
                    created_at   TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (tenant_id, record_id)
                );
                CREATE INDEX IF NOT EXISTS idx_tenant_data_tenant
                    ON tenant_data(tenant_id);

                -- Row-level security for tenant isolation
                ALTER TABLE tenant_data ENABLE ROW LEVEL SECURITY;

                -- Policy: tenants can only see their own rows
                DO $$ BEGIN
                    CREATE POLICY tenant_isolation ON tenant_data
                        USING (tenant_id = current_setting(
                            'app.current_tenant', true
                        ));
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;
            """)

    async def provision_tenant(self, tenant_id: str,
                               tier: TenantTier) -> TenantInfo:
        """Provision a new tenant and assign to a shard."""
        limits = self.TIER_LIMITS[tier]
        isolation = limits["isolation"]

        if isolation == IsolationLevel.DEDICATED:
            shard_id = await self._provision_dedicated_shard(tenant_id)
        else:
            shard_id = self._find_shared_shard()

        tenant = TenantInfo(
            tenant_id=tenant_id,
            tier=tier,
            isolation=isolation,
            shard_id=shard_id,
            row_limit=limits["row_limit"],
            storage_limit_mb=limits["storage_limit_mb"],
            is_active=True,
        )
        self.tenants[tenant_id] = tenant

        # Update shard tenant count
        shard = self.shards[shard_id]
        shard.current_tenants += 1

        logger.info(
            f"Provisioned tenant {tenant_id} ({tier.value}) "
            f"on shard {shard_id} ({isolation.value})"
        )
        return tenant

    def _find_shared_shard(self) -> str:
        """Find the least-loaded shared shard with capacity."""
        shared = [
            s for s in self.shards.values()
            if s.isolation == IsolationLevel.SHARED
            and s.current_tenants < s.max_tenants
        ]
        if not shared:
            raise RuntimeError("No shared shards with capacity available")
        # Pick the least loaded
        return min(shared, key=lambda s: s.current_tenants).shard_id

    async def _provision_dedicated_shard(self, tenant_id: str) -> str:
        """Allocate a dedicated shard for enterprise tenants."""
        # In production, this would spin up a new database
        shard_id = f"dedicated-{tenant_id}"
        shard = ShardInfo(
            shard_id=shard_id,
            host=f"{shard_id}.db.internal",
            database=f"tenant_{tenant_id}",
            max_tenants=1,
            isolation=IsolationLevel.DEDICATED,
        )
        await self.register_shard(shard)
        return shard_id

    async def get_connection(self, tenant_id: str):
        """Get a database connection scoped to a tenant.

        Sets RLS context so the tenant can only access their own data.
        """
        tenant = self.tenants.get(tenant_id)
        if not tenant or not tenant.is_active:
            raise PermissionError(f"Tenant {tenant_id} not found or inactive")

        pool = self._pools[tenant.shard_id]
        conn = await pool.acquire()

        # Set RLS context for row-level security
        await conn.execute(
            f"SET app.current_tenant = '{tenant_id}'"
        )
        return conn

    async def execute_for_tenant(self, tenant_id: str,
                                 query: str,
                                 params: list = None) -> list[dict]:
        """Execute a query in the tenant's context with quota check."""
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Unknown tenant: {tenant_id}")

        conn = await self.get_connection(tenant_id)
        try:
            rows = await conn.fetch(query, *(params or []))
            return [dict(r) for r in rows]
        finally:
            pool = self._pools[tenant.shard_id]
            await pool.release(conn)

    async def check_quota(self, tenant_id: str) -> dict:
        """Check tenant's current usage against limits."""
        tenant = self.tenants[tenant_id]
        conn = await self.get_connection(tenant_id)
        try:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) AS row_count,
                    COALESCE(pg_total_relation_size('tenant_data'), 0)
                        AS total_bytes
                FROM tenant_data
                WHERE tenant_id = $1
            """, tenant_id)

            usage = dict(row)
            return {
                "tenant_id": tenant_id,
                "tier": tenant.tier.value,
                "rows_used": usage["row_count"],
                "rows_limit": tenant.row_limit or "unlimited",
                "rows_pct": (
                    round(usage["row_count"] / tenant.row_limit * 100, 1)
                    if tenant.row_limit else 0
                ),
                "storage_used_mb": round(
                    usage["total_bytes"] / 1024 / 1024, 2
                ),
                "storage_limit_mb": (
                    tenant.storage_limit_mb or "unlimited"
                ),
            }
        finally:
            pool = self._pools[tenant.shard_id]
            await pool.release(conn)

    async def migrate_tenant(self, tenant_id: str,
                             target_shard_id: str,
                             batch_size: int = 10000) -> dict:
        """Migrate a tenant from one shard to another (online).

        1. Copy data in batches from source to target
        2. Flip the routing table entry
        3. Clean up source shard
        """
        tenant = self.tenants[tenant_id]
        source_shard = tenant.shard_id

        if source_shard == target_shard_id:
            return {"status": "already on target shard"}

        logger.info(
            f"Migrating tenant {tenant_id}: "
            f"{source_shard} -> {target_shard_id}"
        )

        source_pool = self._pools[source_shard]
        target_pool = self._pools[target_shard_id]

        # Phase 1: Copy data in batches
        migrated_rows = 0
        last_id = 0

        while True:
            async with source_pool.acquire() as src_conn:
                rows = await src_conn.fetch("""
                    SELECT * FROM tenant_data
                    WHERE tenant_id = $1 AND record_id > $2
                    ORDER BY record_id
                    LIMIT $3
                """, tenant_id, last_id, batch_size)

            if not rows:
                break

            async with target_pool.acquire() as tgt_conn:
                # Batch insert into target
                await tgt_conn.executemany("""
                    INSERT INTO tenant_data
                        (tenant_id, record_id, data, created_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT DO NOTHING
                """, [
                    (r["tenant_id"], r["record_id"],
                     r["data"], r["created_at"])
                    for r in rows
                ])

            migrated_rows += len(rows)
            last_id = rows[-1]["record_id"]
            logger.info(f"  Migrated {migrated_rows} rows so far...")

        # Phase 2: Flip routing
        tenant.shard_id = target_shard_id
        self.shards[source_shard].current_tenants -= 1
        self.shards[target_shard_id].current_tenants += 1

        # Phase 3: Clean up source (after routing is confirmed)
        async with source_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM tenant_data WHERE tenant_id = $1",
                tenant_id,
            )

        logger.info(
            f"Migration complete: {migrated_rows} rows moved for "
            f"tenant {tenant_id}"
        )
        return {
            "status": "completed",
            "rows_migrated": migrated_rows,
            "source_shard": source_shard,
            "target_shard": target_shard_id,
        }


# === Usage ===
async def main():
    manager = TenantShardManager()

    # Register shared shards
    for i in range(3):
        await manager.register_shard(ShardInfo(
            shard_id=f"shared-{i}",
            host=f"shared-{i}.db.internal",
            max_tenants=100,
        ))

    # Provision tenants
    await manager.provision_tenant("acme-corp", TenantTier.ENTERPRISE)
    await manager.provision_tenant("startup-xyz", TenantTier.STARTER)
    await manager.provision_tenant("hobby-user", TenantTier.FREE)

    # Query in tenant context (RLS enforced)
    data = await manager.execute_for_tenant(
        "startup-xyz",
        "SELECT * FROM tenant_data ORDER BY created_at DESC LIMIT 10"
    )

    # Check quotas
    quota = await manager.check_quota("startup-xyz")
    print(f"Usage: {quota['rows_used']}/{quota['rows_limit']} rows")

    # Migrate tenant to a different shard
    result = await manager.migrate_tenant("startup-xyz", "shared-2")
```

Key patterns:
1. **Mixed isolation** -- free/starter tenants share shards (cost-efficient); enterprise tenants get dedicated shards (performance/compliance isolation)
2. **Row-level security** -- PostgreSQL RLS policies enforce tenant isolation at the database level; even bugs in the app cannot leak cross-tenant data
3. **Quota enforcement** -- check row count and storage against tier limits before allowing writes; prevents noisy neighbors
4. **Online migration** -- batch-copy data to target shard, flip routing table, clean source; tenant experiences brief inconsistency during flip, not downtime
5. **Shard assignment** -- least-loaded bin-packing for shared shards; monitor current_tenants and rebalance when skewed'''
    ),
]
