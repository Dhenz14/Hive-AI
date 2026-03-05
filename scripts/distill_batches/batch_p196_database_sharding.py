"""Database sharding strategies — hash vs range, consistent hashing, cross-shard queries, resharding."""

PAIRS = [
    (
        "databases/sharding-hash-vs-range",
        "Compare hash-based vs range-based database sharding with implementation patterns.",
        '''Hash-based vs range-based sharding strategies:

```python
# --- Hash-based sharding ---

import hashlib
from typing import Any, TypeVar, Generic
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

T = TypeVar("T")


class ShardRouter(ABC):
    """Abstract shard router interface."""

    @abstractmethod
    def get_shard(self, key: str) -> int:
        """Return shard number for a given key."""
        ...

    @abstractmethod
    def get_all_shards(self) -> list[int]:
        """Return all shard numbers."""
        ...


class HashShardRouter(ShardRouter):
    """Hash-based sharding: uniform distribution across shards.

    How it works:
      shard = hash(key) % num_shards

    Pros:
      - Even data distribution (balanced load)
      - Simple implementation
      - Any key can be routed in O(1)
      - Good for point lookups by shard key

    Cons:
      - Range queries span ALL shards (expensive)
      - Adding/removing shards requires full data migration
      - No data locality (nearby keys on different shards)
    """

    def __init__(self, num_shards: int) -> None:
        self.num_shards = num_shards

    def get_shard(self, key: str) -> int:
        """Hash key to shard number."""
        # Use SHA256 for uniform distribution
        hash_val = int(hashlib.sha256(key.encode()).hexdigest(), 16)
        return hash_val % self.num_shards

    def get_all_shards(self) -> list[int]:
        return list(range(self.num_shards))

    def get_shard_for_user(self, user_id: int) -> int:
        """Shard by user_id for user-centric workloads."""
        return user_id % self.num_shards

    def get_shard_distribution(
        self, keys: list[str]
    ) -> dict[int, int]:
        """Analyze distribution of keys across shards."""
        distribution: dict[int, int] = {i: 0 for i in range(self.num_shards)}
        for key in keys:
            shard = self.get_shard(key)
            distribution[shard] += 1
        return distribution


class RangeShardRouter(ShardRouter):
    """Range-based sharding: contiguous ranges per shard.

    How it works:
      shard = range that contains the key value

    Pros:
      - Range queries can target specific shard(s)
      - Data locality (nearby keys on same shard)
      - Easy to understand and debug
      - Can shard by time (hot/cold data)

    Cons:
      - Potential hotspots (one range may be much hotter)
      - Uneven data distribution without careful planning
      - Requires maintaining range-to-shard mapping
      - Rebalancing requires moving contiguous data blocks
    """

    def __init__(self, ranges: list[tuple[str, str, int]]) -> None:
        """Initialize with (start, end, shard_id) tuples.

        Example: [('A', 'H', 0), ('I', 'P', 1), ('Q', 'Z', 2)]
        """
        self.ranges = sorted(ranges, key=lambda x: x[0])
        self._shard_ids = list(set(r[2] for r in ranges))

    def get_shard(self, key: str) -> int:
        """Find shard containing the key's range."""
        for start, end, shard_id in self.ranges:
            if start <= key <= end:
                return shard_id
        raise ValueError(f"Key '{key}' not in any range")

    def get_all_shards(self) -> list[int]:
        return self._shard_ids

    def get_shards_for_range(
        self, start_key: str, end_key: str
    ) -> list[int]:
        """Find all shards that overlap with a query range.

        This is the key advantage of range sharding:
        range queries only hit relevant shards.
        """
        shards: set[int] = set()
        for range_start, range_end, shard_id in self.ranges:
            # Check if ranges overlap
            if range_start <= end_key and range_end >= start_key:
                shards.add(shard_id)
        return sorted(shards)
```

```python
# --- Shard-aware database connection manager ---

from contextlib import contextmanager
from typing import Generator
import psycopg2


@dataclass
class ShardConfig:
    """Configuration for a database shard."""
    shard_id: int
    host: str
    port: int = 5432
    database: str = "app"
    username: str = "postgres"
    password: str = ""
    max_connections: int = 20


class ShardManager:
    """Manage connections to multiple database shards."""

    def __init__(
        self,
        shard_configs: list[ShardConfig],
        router: ShardRouter,
    ) -> None:
        self.router = router
        self.shards: dict[int, ShardConfig] = {
            config.shard_id: config for config in shard_configs
        }
        self._pools: dict[int, Any] = {}

    def _get_dsn(self, shard_id: int) -> str:
        config = self.shards[shard_id]
        return (
            f"postgresql://{config.username}:{config.password}"
            f"@{config.host}:{config.port}/{config.database}"
        )

    @contextmanager
    def connection(
        self, shard_key: str
    ) -> Generator[Any, None, None]:
        """Get connection to the shard for a given key."""
        shard_id = self.router.get_shard(shard_key)
        conn = psycopg2.connect(self._get_dsn(shard_id))
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def connection_by_id(
        self, shard_id: int
    ) -> Generator[Any, None, None]:
        """Get connection to a specific shard by ID."""
        conn = psycopg2.connect(self._get_dsn(shard_id))
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute_on_all_shards(
        self, query: str, params: tuple | None = None
    ) -> dict[int, list[Any]]:
        """Execute query on every shard (scatter-gather)."""
        results: dict[int, list[Any]] = {}
        for shard_id in self.router.get_all_shards():
            with self.connection_by_id(shard_id) as conn:
                cur = conn.cursor()
                cur.execute(query, params)
                results[shard_id] = cur.fetchall()
        return results

    def insert(
        self, shard_key: str, table: str, data: dict[str, Any]
    ) -> None:
        """Insert into the correct shard based on key."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))

        with self.connection(shard_key) as conn:
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                tuple(data.values()),
            )
```

```python
# --- Shard key selection and compound sharding ---

SHARD_KEY_GUIDE = """
Shard Key Selection Criteria:

| Criterion               | Hash Sharding | Range Sharding |
|--------------------------|---------------|----------------|
| Even distribution        | Excellent     | Needs tuning   |
| Range query efficiency   | Poor (all)    | Excellent      |
| Point lookup             | O(1)          | O(log N)       |
| Adding shards            | Full reshard  | Split ranges   |
| Hotspot risk             | Low           | High           |
| Data locality            | None          | Strong         |
| Time-based queries       | Poor          | Excellent      |

Choose Hash when:
  - Workload is primarily point lookups (by user_id, order_id)
  - Need even load distribution
  - No range queries on shard key
  - Example: user data, session stores

Choose Range when:
  - Workload includes range scans (date ranges, alphabetical)
  - Data has natural ordering (timestamps, sequences)
  - Need data locality for related items
  - Example: time-series, log data, geographic data
"""


@dataclass
class CompoundShardKey:
    """Compound shard key combining hash and range.

    Strategy: hash on tenant, range on time within tenant.
    This gives:
      - Tenant isolation (hash: each tenant on specific shard)
      - Time-range queries within tenant (range: date partitioning)
    """
    tenant_id: str
    timestamp: str

    def primary_shard(self, num_shards: int) -> int:
        """Hash on tenant_id for shard selection."""
        hash_val = int(
            hashlib.sha256(self.tenant_id.encode()).hexdigest(), 16
        )
        return hash_val % num_shards

    def partition_key(self) -> str:
        """Range partition within shard by month."""
        return self.timestamp[:7]  # YYYY-MM


# Common shard key choices:
#
# E-commerce:
#   Hash by user_id     — user data co-located
#   Hash by merchant_id — multi-tenant marketplace
#   Range by order_date — time-based analytics
#
# SaaS:
#   Hash by tenant_id   — tenant isolation
#   Compound: tenant + time — isolation + time queries
#
# Social media:
#   Hash by user_id     — user's posts, followers together
#   Range by post_date  — timeline queries (risk: celebrity hotspot)
#
# IoT:
#   Hash by device_id   — device data co-located
#   Range by timestamp  — time-range analysis
#   Compound: region + time — geographic + temporal
```

Key sharding patterns:

| Strategy | Distribution | Range Queries | Resharding Cost |
|---|---|---|---|
| Hash (modulo) | Uniform | All shards | Full migration |
| Range | Potentially uneven | Targeted shards | Split/merge ranges |
| Compound | Uniform per dimension | Partial shard set | Moderate |
| Directory-based | Flexible | Lookup required | Update directory |
| Geographic | By region | Regional queries | Move regions |

1. **Hash for even distribution** -- best for point lookups, poor for range queries
2. **Range for data locality** -- great for time-series and sequential access
3. **Compound keys** -- hash on tenant + range on time for multi-tenant SaaS
4. **Choose key by query pattern** -- shard on the column you filter/join on most
5. **Avoid hotspot keys** -- never shard on a column with skewed distribution'''
    ),
    (
        "databases/sharding-consistent-hashing",
        "Implement consistent hashing with virtual nodes for shard routing.",
        '''Consistent hashing with virtual nodes for scalable sharding:

```python
# --- Consistent hash ring implementation ---

import hashlib
import bisect
from typing import Any, TypeVar, Generic
from dataclasses import dataclass, field


T = TypeVar("T")


class ConsistentHashRing:
    """Consistent hash ring with virtual nodes.

    Standard hash sharding (key % N) breaks when N changes:
      - Adding a shard: ~100% of keys need remapping
      - Removing a shard: ~100% of keys need remapping

    Consistent hashing limits redistribution:
      - Adding a shard: only ~1/N keys move to new shard
      - Removing a shard: only removed shard's keys redistribute
      - Virtual nodes ensure even distribution

    Hash ring visualization:
        0 ─── vnode_A1 ─── vnode_B1 ─── vnode_C1 ──
        │                                          │
        vnode_C3                              vnode_A2
        │                                          │
        ── vnode_B3 ─── vnode_A3 ─── vnode_B2 ────
    """

    def __init__(self, virtual_nodes: int = 150) -> None:
        self.virtual_nodes = virtual_nodes
        self._ring: list[int] = []             # Sorted hash positions
        self._ring_to_node: dict[int, str] = {}  # Hash -> node name
        self._nodes: set[str] = set()

    def _hash(self, key: str) -> int:
        """Generate consistent hash for a key."""
        return int(hashlib.sha256(key.encode()).hexdigest(), 16)

    def add_node(self, node: str, weight: int = 1) -> None:
        """Add a node to the ring with virtual nodes.

        Weight multiplier allows bigger servers to handle more keys.
        """
        if node in self._nodes:
            return

        self._nodes.add(node)
        vnodes = self.virtual_nodes * weight

        for i in range(vnodes):
            vnode_key = f"{node}:vnode:{i}"
            hash_val = self._hash(vnode_key)
            self._ring_to_node[hash_val] = node
            bisect.insort(self._ring, hash_val)

    def remove_node(self, node: str) -> None:
        """Remove a node and its virtual nodes from the ring."""
        if node not in self._nodes:
            return

        self._nodes.discard(node)

        # Remove all virtual nodes for this node
        positions_to_remove = [
            pos for pos, n in self._ring_to_node.items()
            if n == node
        ]
        for pos in positions_to_remove:
            del self._ring_to_node[pos]
            self._ring.remove(pos)

    def get_node(self, key: str) -> str:
        """Find the node responsible for a key.

        Walk clockwise on the ring from the key's hash
        to find the next node position.
        """
        if not self._ring:
            raise RuntimeError("No nodes in the ring")

        hash_val = self._hash(key)

        # Find the first node position >= hash_val
        idx = bisect.bisect_right(self._ring, hash_val)

        # Wrap around if past the last node
        if idx >= len(self._ring):
            idx = 0

        position = self._ring[idx]
        return self._ring_to_node[position]

    def get_nodes_for_replication(
        self, key: str, replicas: int = 3
    ) -> list[str]:
        """Get N distinct nodes for replication.

        Walk clockwise, skipping virtual nodes of the same
        physical node, until we find N distinct physical nodes.
        """
        if len(self._nodes) < replicas:
            return list(self._nodes)

        hash_val = self._hash(key)
        idx = bisect.bisect_right(self._ring, hash_val)
        if idx >= len(self._ring):
            idx = 0

        result: list[str] = []
        seen: set[str] = set()

        while len(result) < replicas:
            position = self._ring[idx % len(self._ring)]
            node = self._ring_to_node[position]

            if node not in seen:
                result.append(node)
                seen.add(node)

            idx += 1

        return result
```

```python
# --- Analyzing ring balance and migration ---

from collections import Counter


class RingAnalyzer:
    """Analyze consistent hash ring for balance and migration cost."""

    def __init__(self, ring: ConsistentHashRing) -> None:
        self.ring = ring

    def measure_balance(
        self, sample_keys: list[str]
    ) -> dict[str, Any]:
        """Measure key distribution across nodes.

        Ideal: each node gets ~1/N of keys.
        Acceptable: within 10% of ideal.
        """
        distribution = Counter(
            self.ring.get_node(key) for key in sample_keys
        )

        total = len(sample_keys)
        num_nodes = len(self.ring._nodes)
        ideal_pct = 100.0 / num_nodes if num_nodes > 0 else 0

        balance: dict[str, dict[str, Any]] = {}
        for node in self.ring._nodes:
            count = distribution.get(node, 0)
            pct = (count / total) * 100 if total > 0 else 0
            balance[node] = {
                "count": count,
                "percentage": round(pct, 2),
                "deviation_from_ideal": round(pct - ideal_pct, 2),
            }

        # Calculate standard deviation of percentages
        pcts = [b["percentage"] for b in balance.values()]
        mean_pct = sum(pcts) / len(pcts) if pcts else 0
        std_dev = (
            sum((p - mean_pct) ** 2 for p in pcts) / len(pcts)
        ) ** 0.5 if pcts else 0

        return {
            "node_balance": balance,
            "std_deviation": round(std_dev, 2),
            "is_balanced": std_dev < 5.0,  # < 5% deviation
            "total_keys": total,
            "total_nodes": num_nodes,
        }

    def simulate_migration(
        self,
        sample_keys: list[str],
        add_node: str | None = None,
        remove_node: str | None = None,
    ) -> dict[str, Any]:
        """Simulate adding/removing a node and calculate migration cost."""
        # Record current assignments
        before: dict[str, str] = {}
        for key in sample_keys:
            before[key] = self.ring.get_node(key)

        # Modify ring
        if add_node:
            self.ring.add_node(add_node)
        if remove_node:
            self.ring.remove_node(remove_node)

        # Record new assignments
        after: dict[str, str] = {}
        for key in sample_keys:
            after[key] = self.ring.get_node(key)

        # Calculate migration
        moved = sum(1 for k in sample_keys if before[k] != after[k])
        migration_pct = (moved / len(sample_keys)) * 100 if sample_keys else 0

        # Undo modification
        if add_node:
            self.ring.remove_node(add_node)
        if remove_node:
            self.ring.add_node(remove_node)

        return {
            "keys_moved": moved,
            "total_keys": len(sample_keys),
            "migration_percentage": round(migration_pct, 2),
            "operation": f"add={add_node}" if add_node else f"remove={remove_node}",
            # Ideal: ~1/N for add, ~1/N for remove
            "ideal_migration_pct": round(
                100.0 / (len(self.ring._nodes) + (1 if add_node else 0)),
                2,
            ),
        }
```

```python
# --- Jump consistent hashing (alternative) ---

def jump_consistent_hash(key: int, num_buckets: int) -> int:
    """Jump Consistent Hash — Google's O(ln N) algorithm.

    Pros over ring-based:
      - No memory overhead (no ring structure)
      - Perfectly balanced (exactly uniform)
      - O(ln N) computation
      - Deterministic (same key always maps to same bucket)

    Cons:
      - Only supports adding/removing the LAST bucket
      - Cannot remove an arbitrary node
      - Returns bucket number, not named node

    Best for: numbered shards where you only scale up.
    """
    b: int = -1
    j: int = 0

    while j < num_buckets:
        b = j
        key = ((key * 2862933555777941757) + 1) & 0xFFFFFFFFFFFFFFFF
        j = int((b + 1) * (float(1 << 31) / float((key >> 33) + 1)))

    return b


def rendezvous_hash(key: str, nodes: list[str]) -> str:
    """Rendezvous (highest random weight) hashing.

    Each node gets a score for each key. Highest score wins.

    Pros:
      - Add/remove any node: only ~1/N keys move
      - No ring structure needed
      - Simple implementation
      - Supports weighted nodes

    Cons:
      - O(N) per lookup (must compute score for all nodes)
      - Slower than consistent hash ring for many nodes
    """
    best_node = ""
    best_score = -1

    for node in nodes:
        # Combine key and node for unique hash
        combined = f"{key}:{node}"
        score = int(hashlib.sha256(combined.encode()).hexdigest(), 16)

        if score > best_score:
            best_score = score
            best_node = node

    return best_node


# Algorithm comparison:
# | Algorithm          | Lookup | Memory   | Balance  | Remove Any |
# |--------------------|--------|----------|----------|------------|
# | Modulo hash        | O(1)   | O(1)     | Perfect  | Full reshard|
# | Consistent ring    | O(log N)| O(N*V)  | Good     | Yes (~1/N) |
# | Jump hash          | O(ln N)| O(1)     | Perfect  | No (last)  |
# | Rendezvous hash    | O(N)   | O(1)     | Perfect  | Yes (~1/N) |
# | Maglev hash        | O(1)   | O(N*M)  | Near-perfect| Yes     |
```

Key consistent hashing patterns:

| Feature | Consistent Ring | Jump Hash | Rendezvous Hash |
|---|---|---|---|
| Add/remove any node | Yes (~1/N move) | Last only | Yes (~1/N move) |
| Lookup complexity | O(log N) | O(ln N) | O(N) |
| Memory overhead | O(N * vnodes) | O(1) | O(1) |
| Balance quality | Good (with vnodes) | Perfect | Perfect |
| Weighted nodes | Yes (more vnodes) | No | Yes (weighted score) |
| Best for | General use | Numbered shards | Few nodes |

1. **Virtual nodes for balance** -- 100-200 vnodes per physical node ensures even distribution
2. **Ring for general sharding** -- most flexible, supports add/remove any node
3. **Jump hash for simplicity** -- zero memory, perfect balance, but only append
4. **Rendezvous for few nodes** -- O(N) is fine when N < 100 nodes
5. **Test migration before deploying** -- simulate add/remove to predict data movement'''
    ),
    (
        "databases/sharding-cross-shard",
        "Show cross-shard query patterns: scatter-gather, distributed joins, and global aggregation.",
        '''Cross-shard query patterns and distributed operations:

```python
# --- Scatter-gather query execution ---

import asyncio
from typing import Any, Callable, TypeVar
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import heapq

T = TypeVar("T")


@dataclass
class ShardResult:
    """Result from a single shard query."""
    shard_id: int
    rows: list[dict[str, Any]]
    row_count: int
    execution_ms: float
    error: str | None = None


class ScatterGatherExecutor:
    """Execute queries across multiple shards in parallel.

    Scatter-gather pattern:
      1. Scatter: send query to all (or targeted) shards
      2. Execute: each shard processes independently
      3. Gather: collect and merge results
      4. Reduce: apply final aggregation/sorting
    """

    def __init__(
        self,
        shard_manager: Any,   # ShardManager from previous example
        max_workers: int = 10,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.shard_manager = shard_manager
        self.max_workers = max_workers
        self.timeout = timeout_seconds

    def scatter_gather(
        self,
        query: str,
        params: tuple | None = None,
        shard_ids: list[int] | None = None,
    ) -> list[ShardResult]:
        """Execute query on all or specific shards in parallel."""
        target_shards = shard_ids or self.shard_manager.router.get_all_shards()
        results: list[ShardResult] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self._query_shard, shard_id, query, params
                ): shard_id
                for shard_id in target_shards
            }

            for future in as_completed(futures, timeout=self.timeout):
                shard_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append(ShardResult(
                        shard_id=shard_id,
                        rows=[],
                        row_count=0,
                        execution_ms=0,
                        error=str(e),
                    ))

        return sorted(results, key=lambda r: r.shard_id)

    def _query_shard(
        self,
        shard_id: int,
        query: str,
        params: tuple | None,
    ) -> ShardResult:
        """Execute query on a single shard."""
        import time
        start = time.monotonic()

        with self.shard_manager.connection_by_id(shard_id) as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        elapsed = (time.monotonic() - start) * 1000

        return ShardResult(
            shard_id=shard_id,
            rows=rows,
            row_count=len(rows),
            execution_ms=elapsed,
        )

    def aggregate_results(
        self,
        shard_results: list[ShardResult],
        order_by: str | None = None,
        order_desc: bool = True,
        limit: int | None = None,
        group_by: str | None = None,
        sum_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Merge and aggregate results from multiple shards.

        This is the "reduce" step of scatter-gather.
        """
        # Flatten all rows
        all_rows: list[dict[str, Any]] = []
        for result in shard_results:
            if result.error is None:
                all_rows.extend(result.rows)

        # Group by + aggregate
        if group_by and sum_columns:
            groups: dict[Any, dict[str, Any]] = {}
            for row in all_rows:
                key = row.get(group_by)
                if key not in groups:
                    groups[key] = {group_by: key}
                    for col in sum_columns:
                        groups[key][col] = 0

                for col in sum_columns:
                    groups[key][col] += row.get(col, 0)

            all_rows = list(groups.values())

        # Sort
        if order_by:
            all_rows.sort(
                key=lambda r: r.get(order_by, 0),
                reverse=order_desc,
            )

        # Limit
        if limit:
            all_rows = all_rows[:limit]

        return all_rows
```

```python
# --- Distributed join strategies ---

class DistributedJoinExecutor:
    """Execute joins across shards using different strategies.

    Cross-shard join strategies:
      1. Broadcast join: send small table to all shards
      2. Lookup join: fetch from remote shard per row
      3. Repartition join: reshuffle data to co-locate keys
      4. Global table: replicate reference data to all shards
    """

    def __init__(self, shard_manager: Any) -> None:
        self.shard_manager = shard_manager

    def broadcast_join(
        self,
        query_template: str,
        small_table_data: list[dict[str, Any]],
        small_table_name: str = "lookup_data",
    ) -> list[dict[str, Any]]:
        """Broadcast small table to all shards for local join.

        Best when:
          - One side of join is small (< 10K rows)
          - Small table changes infrequently
          - Example: joining orders (sharded) with categories (small)
        """
        all_results: list[dict[str, Any]] = []

        for shard_id in self.shard_manager.router.get_all_shards():
            with self.shard_manager.connection_by_id(shard_id) as conn:
                cur = conn.cursor()

                # Create temporary table with broadcast data
                cur.execute(f"""
                    CREATE TEMP TABLE {small_table_name} (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        metadata JSONB
                    ) ON COMMIT DROP
                """)

                # Insert broadcast data
                for row in small_table_data:
                    cur.execute(
                        f"INSERT INTO {small_table_name} (id, name, metadata) "
                        "VALUES (%s, %s, %s)",
                        (row["id"], row["name"],
                         json.dumps(row.get("metadata", {}))),
                    )

                # Execute join query
                cur.execute(query_template)
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, r)) for r in cur.fetchall()]
                all_results.extend(rows)

        return all_results

    def lookup_join(
        self,
        local_shard_id: int,
        local_query: str,
        remote_key_column: str,
        remote_shard_resolver: Callable[[Any], int],
        remote_query_template: str,
    ) -> list[dict[str, Any]]:
        """Lookup join: fetch remote data per key.

        Best when:
          - Few rows need remote lookup
          - Can batch remote lookups
          - Example: order details with user profile from user shard
        """
        # Step 1: Get local data with foreign keys
        with self.shard_manager.connection_by_id(local_shard_id) as conn:
            cur = conn.cursor()
            cur.execute(local_query)
            columns = [desc[0] for desc in cur.description]
            local_rows = [dict(zip(columns, r)) for r in cur.fetchall()]

        # Step 2: Group foreign keys by remote shard
        remote_lookups: dict[int, list[Any]] = {}
        for row in local_rows:
            remote_key = row[remote_key_column]
            remote_shard = remote_shard_resolver(remote_key)
            remote_lookups.setdefault(remote_shard, []).append(remote_key)

        # Step 3: Batch-fetch from each remote shard
        remote_data: dict[Any, dict[str, Any]] = {}
        for shard_id, keys in remote_lookups.items():
            with self.shard_manager.connection_by_id(shard_id) as conn:
                cur = conn.cursor()
                cur.execute(
                    remote_query_template,
                    (tuple(keys),),
                )
                columns = [desc[0] for desc in cur.description]
                for r in cur.fetchall():
                    row_dict = dict(zip(columns, r))
                    remote_data[row_dict["id"]] = row_dict

        # Step 4: Merge results
        for row in local_rows:
            remote_key = row[remote_key_column]
            if remote_key in remote_data:
                row.update(remote_data[remote_key])

        return local_rows
```

```python
# --- Global aggregation patterns ---

import json


class GlobalAggregator:
    """Aggregate data across all shards with push-down optimization."""

    def __init__(self, executor: ScatterGatherExecutor) -> None:
        self.executor = executor

    def count_total(self, table: str, where: str = "1=1") -> int:
        """Global COUNT with push-down: sum of per-shard counts."""
        results = self.executor.scatter_gather(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {where}"
        )
        return sum(r.rows[0]["cnt"] for r in results if r.rows)

    def global_top_n(
        self,
        query: str,
        order_by: str,
        n: int = 10,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        """Global Top-N with over-fetch optimization.

        Strategy: fetch top N from each shard, merge, take global top N.
        This works because: global top N is a subset of union of per-shard top N.
        """
        # Add LIMIT to per-shard query (over-fetch to ensure correctness)
        shard_query = f"{query} ORDER BY {order_by} {'DESC' if descending else 'ASC'} LIMIT {n}"
        results = self.executor.scatter_gather(shard_query)

        # Merge: combine all per-shard top-N, re-sort, take global top-N
        return self.executor.aggregate_results(
            results,
            order_by=order_by,
            order_desc=descending,
            limit=n,
        )

    def global_percentile(
        self,
        table: str,
        column: str,
        percentile: float = 0.95,
        sample_size: int = 10000,
    ) -> float:
        """Approximate global percentile using sampling.

        Exact percentiles across shards require all data.
        Approximation: sample from each shard, compute on merged sample.
        """
        per_shard_sample = sample_size // len(
            self.executor.shard_manager.router.get_all_shards()
        )

        query = f"""
            SELECT {column} AS value
            FROM {table}
            ORDER BY RANDOM()
            LIMIT {per_shard_sample}
        """

        results = self.executor.scatter_gather(query)
        all_values = sorted(
            row["value"]
            for result in results
            for row in result.rows
            if result.error is None
        )

        if not all_values:
            return 0.0

        idx = int(len(all_values) * percentile)
        return all_values[min(idx, len(all_values) - 1)]
```

Key cross-shard query patterns:

| Pattern | When to Use | Cost |
|---|---|---|
| Scatter-gather | Aggregations, search across all data | O(shards) queries |
| Broadcast join | Small table + large sharded table | O(shards) copies |
| Lookup join | Few rows need remote enrichment | O(distinct keys) lookups |
| Global table | Reference data (countries, categories) | Replicated to all shards |
| Push-down | COUNT, SUM, MIN, MAX | Minimal network transfer |
| Top-N merge | Global ranking | N * shards rows transferred |

1. **Push down aggregations** -- compute per-shard, merge results (not raw data)
2. **Broadcast small tables** -- replicate reference data for local joins
3. **Batch remote lookups** -- group foreign keys by shard, fetch in batches
4. **Top-N over-fetch** -- fetch N from each shard, merge for global top N
5. **Sample for percentiles** -- exact cross-shard percentiles require all data'''
    ),
    (
        "databases/sharding-resharding",
        "Demonstrate resharding with minimal downtime: online migration, dual-write, and cutover strategies.",
        '''Resharding with minimal downtime strategies:

```python
# --- Online resharding orchestrator ---

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class ReshardPhase(Enum):
    """Phases of an online resharding operation."""
    PREPARE = "prepare"
    DUAL_WRITE = "dual_write"
    BACKFILL = "backfill"
    VERIFY = "verify"
    CUTOVER = "cutover"
    CLEANUP = "cleanup"


@dataclass
class ReshardPlan:
    """Plan for moving data between shards."""
    source_shard: int
    target_shard: int
    key_range_start: str | None = None
    key_range_end: str | None = None
    estimated_rows: int = 0
    batch_size: int = 1000
    verify_sample_rate: float = 0.01   # Verify 1% of rows


class OnlineResharder:
    """Reshard with minimal downtime using dual-write pattern.

    Strategy (4-phase approach):
      1. PREPARE: Create target schema, set up dual-write
      2. BACKFILL: Copy historical data in batches
      3. VERIFY: Compare source and target data
      4. CUTOVER: Switch reads to new shard, stop dual-write

    Total downtime: seconds (during cutover only).
    """

    def __init__(self, shard_manager: Any) -> None:
        self.shard_manager = shard_manager
        self.current_phase = ReshardPhase.PREPARE

    def execute_reshard(self, plan: ReshardPlan) -> dict[str, Any]:
        """Execute full resharding operation."""
        metrics: dict[str, Any] = {"start_time": datetime.utcnow().isoformat()}

        try:
            # Phase 1: Prepare target shard
            self.current_phase = ReshardPhase.PREPARE
            self._prepare_target(plan)
            logger.info("Phase 1: Target prepared")

            # Phase 2: Enable dual-write
            self.current_phase = ReshardPhase.DUAL_WRITE
            self._enable_dual_write(plan)
            logger.info("Phase 2: Dual-write enabled")

            # Phase 3: Backfill historical data
            self.current_phase = ReshardPhase.BACKFILL
            backfill_stats = self._backfill_data(plan)
            metrics["backfill"] = backfill_stats
            logger.info(f"Phase 3: Backfilled {backfill_stats['rows_copied']} rows")

            # Phase 4: Verify data consistency
            self.current_phase = ReshardPhase.VERIFY
            verify_result = self._verify_data(plan)
            metrics["verification"] = verify_result
            if not verify_result["passed"]:
                raise RuntimeError(
                    f"Verification failed: {verify_result['mismatches']} mismatches"
                )
            logger.info("Phase 4: Verification passed")

            # Phase 5: Cutover (brief pause)
            self.current_phase = ReshardPhase.CUTOVER
            cutover_result = self._cutover(plan)
            metrics["cutover"] = cutover_result
            logger.info(f"Phase 5: Cutover complete ({cutover_result['downtime_ms']}ms)")

            # Phase 6: Cleanup
            self.current_phase = ReshardPhase.CLEANUP
            self._cleanup(plan)
            logger.info("Phase 6: Cleanup complete")

            metrics["status"] = "success"

        except Exception as e:
            metrics["status"] = "failed"
            metrics["error"] = str(e)
            metrics["failed_phase"] = self.current_phase.value
            self._rollback(plan)
            raise

        metrics["end_time"] = datetime.utcnow().isoformat()
        return metrics

    def _prepare_target(self, plan: ReshardPlan) -> None:
        """Create schema on target shard."""
        with self.shard_manager.connection_by_id(plan.source_shard) as src:
            cur = src.cursor()
            # Get table definitions from source
            cur.execute("""
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
            """)
            schema_info = cur.fetchall()

        # Apply schema to target (simplified)
        logger.info(f"Target shard {plan.target_shard} schema prepared")

    def _enable_dual_write(self, plan: ReshardPlan) -> None:
        """Enable writing to both source and target shards.

        Implementation options:
          1. Application-level: write to both in business logic
          2. CDC (Change Data Capture): stream changes from source
          3. Database triggers: trigger on source writes to target
          4. Proxy: middleware intercepts and fans out writes
        """
        # In practice, this would configure the application
        # or CDC pipeline to write to both shards
        logger.info(
            f"Dual-write enabled: shard {plan.source_shard} -> "
            f"shard {plan.target_shard}"
        )

    def _backfill_data(self, plan: ReshardPlan) -> dict[str, Any]:
        """Copy historical data in batches with progress tracking."""
        rows_copied = 0
        last_id = 0
        start_time = time.monotonic()

        while True:
            # Read batch from source
            with self.shard_manager.connection_by_id(plan.source_shard) as src:
                cur = src.cursor()
                cur.execute("""
                    SELECT * FROM data_table
                    WHERE id > %s
                    ORDER BY id
                    LIMIT %s
                """, (last_id, plan.batch_size))

                columns = [desc[0] for desc in cur.description]
                batch = [dict(zip(columns, row)) for row in cur.fetchall()]

            if not batch:
                break

            # Write batch to target
            with self.shard_manager.connection_by_id(plan.target_shard) as tgt:
                cur = tgt.cursor()
                for row in batch:
                    cols = ", ".join(row.keys())
                    placeholders = ", ".join(["%s"] * len(row))
                    cur.execute(
                        f"INSERT INTO data_table ({cols}) VALUES ({placeholders}) "
                        "ON CONFLICT (id) DO NOTHING",   # Skip if dual-write already inserted
                        tuple(row.values()),
                    )

            rows_copied += len(batch)
            last_id = batch[-1]["id"]

            if rows_copied % 10000 == 0:
                logger.info(f"Backfill progress: {rows_copied} rows")

        elapsed = time.monotonic() - start_time
        return {
            "rows_copied": rows_copied,
            "elapsed_seconds": round(elapsed, 2),
            "rows_per_second": round(rows_copied / max(elapsed, 0.01)),
        }

    def _verify_data(self, plan: ReshardPlan) -> dict[str, Any]:
        """Verify data consistency between source and target."""
        mismatches = 0
        checked = 0

        # Count comparison
        with self.shard_manager.connection_by_id(plan.source_shard) as src:
            cur = src.cursor()
            cur.execute("SELECT COUNT(*) FROM data_table")
            source_count = cur.fetchone()[0]

        with self.shard_manager.connection_by_id(plan.target_shard) as tgt:
            cur = tgt.cursor()
            cur.execute("SELECT COUNT(*) FROM data_table")
            target_count = cur.fetchone()[0]

        if source_count != target_count:
            mismatches += abs(source_count - target_count)

        return {
            "passed": mismatches == 0,
            "source_count": source_count,
            "target_count": target_count,
            "mismatches": mismatches,
            "checked": checked,
        }

    def _cutover(self, plan: ReshardPlan) -> dict[str, Any]:
        """Switch traffic to new shard (brief downtime window)."""
        start = time.monotonic()

        # 1. Pause writes (brief)
        # 2. Drain remaining dual-write queue
        # 3. Final consistency check
        # 4. Update shard routing table
        # 5. Resume writes to new shard only

        downtime_ms = (time.monotonic() - start) * 1000
        return {"downtime_ms": round(downtime_ms, 1)}

    def _cleanup(self, plan: ReshardPlan) -> None:
        """Remove data from old shard and disable dual-write."""
        logger.info("Disabling dual-write, scheduling source data cleanup")

    def _rollback(self, plan: ReshardPlan) -> None:
        """Rollback on failure: disable dual-write, drop target data."""
        logger.error(f"Rolling back reshard at phase {self.current_phase.value}")
```

```python
# --- CDC-based resharding with Debezium ---

DEBEZIUM_CONFIG = """
{
  "name": "reshard-cdc-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "source-shard-host",
    "database.port": "5432",
    "database.user": "replicator",
    "database.password": "${CDC_PASSWORD}",
    "database.dbname": "app",
    "database.server.name": "shard_0",
    "table.include.list": "public.orders,public.users",
    "plugin.name": "pgoutput",
    "slot.name": "reshard_slot",

    "transforms": "route",
    "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.route.regex": "(.*)",
    "transforms.route.replacement": "reshard.$1",

    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter"
  }
}
"""

RESHARDING_STRATEGIES = """
| Strategy       | Downtime  | Complexity | Data Safety | Best For          |
|----------------|-----------|------------|-------------|-------------------|
| Dual-write     | Seconds   | Medium     | High        | Application-level |
| CDC (Debezium) | Zero      | High       | High        | Database-level    |
| Ghost tables   | Seconds   | Medium     | High        | Schema + reshard  |
| Stop-and-copy  | Minutes   | Low        | Highest     | Small datasets    |
| Read replica   | Seconds   | Medium     | High        | Read-heavy loads  |

Resharding decision tree:

1. Can you tolerate minutes of downtime?
   YES -> Stop-and-copy (simplest, safest)
   NO  -> Continue

2. Is the change at application level?
   YES -> Dual-write pattern
   NO  -> Continue

3. Do you need zero-downtime?
   YES -> CDC with Debezium/DMS
   NO  -> Ghost table (like gh-ost)

4. Rollback plan?
   - Dual-write: switch routing back
   - CDC: stop consumer, replay
   - Ghost table: swap tables back
   - Stop-and-copy: restore backup
"""
```

Key resharding patterns:

| Phase | Action | Duration |
|---|---|---|
| Prepare | Create target schema | Minutes |
| Dual-write | Write to both shards | Duration of backfill |
| Backfill | Copy historical data in batches | Hours (data-dependent) |
| Verify | Compare counts and sample rows | Minutes |
| Cutover | Switch routing, drain queue | Seconds |
| Cleanup | Remove old data, disable dual-write | Minutes |

1. **Dual-write for zero-downtime** -- write to both shards during migration
2. **Batch backfill with checkpoints** -- resume from last position on failure
3. **ON CONFLICT DO NOTHING** -- handle overlap between dual-write and backfill
4. **Verify before cutover** -- count comparison + sample verification
5. **CDC for complex migrations** -- Debezium captures changes at database level'''
    ),
]
