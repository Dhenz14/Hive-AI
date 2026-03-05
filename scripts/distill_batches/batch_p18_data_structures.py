PAIRS = [
    (
        "algorithms/graph-algorithms-practical",
        r"""Explain practical graph algorithms including BFS/DFS traversal, Dijkstra's shortest path, topological sort for dependency resolution, cycle detection, connected components, and A* pathfinding. Include Python implementations with real-world applications.""",
        r"""## Practical Graph Algorithms: Traversal, Shortest Path, and Dependency Resolution

Graph algorithms solve problems in networking, dependency management, social networks, and pathfinding. Understanding when to apply each algorithm is as important as implementing them.

### Graph Representation

```python
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional
import heapq


class Graph:
    """Adjacency list graph supporting directed/undirected, weighted/unweighted."""

    def __init__(self, directed: bool = True):
        self.adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self.directed = directed

    def add_edge(self, u: str, v: str, weight: float = 1.0):
        self.adj[u].append((v, weight))
        if not self.directed:
            self.adj[v].append((u, weight))
        # Ensure both nodes exist in adj
        if v not in self.adj:
            self.adj[v] = []

    def neighbors(self, node: str) -> list[tuple[str, float]]:
        return self.adj[node]

    @property
    def nodes(self) -> set[str]:
        return set(self.adj.keys())
```

### BFS: Level-Order Traversal and Shortest Unweighted Path

```python
def bfs(graph: Graph, start: str) -> dict[str, int]:
    """BFS: shortest path (hop count) from start to all reachable nodes."""
    distances = {start: 0}
    queue = deque([start])

    while queue:
        node = queue.popleft()
        for neighbor, _ in graph.neighbors(node):
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)

    return distances


def bfs_path(graph: Graph, start: str, end: str) -> Optional[list[str]]:
    """Find shortest path (by hops) between two nodes."""
    if start == end:
        return [start]

    visited = {start}
    queue = deque([(start, [start])])

    while queue:
        node, path = queue.popleft()
        for neighbor, _ in graph.neighbors(node):
            if neighbor == end:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return None  # No path exists


# Application: social network — find degrees of separation
# Application: web crawler — discover pages level by level
# Application: shortest path in unweighted graph (maze solving)
```

### DFS: Cycle Detection and Connected Components

```python
def has_cycle(graph: Graph) -> bool:
    """Detect cycles in a directed graph using DFS coloring."""
    # WHITE=0 (unvisited), GRAY=1 (in current path), BLACK=2 (fully processed)
    color = {node: 0 for node in graph.nodes}

    def dfs(node: str) -> bool:
        color[node] = 1  # Mark as being processed

        for neighbor, _ in graph.neighbors(node):
            if color[neighbor] == 1:
                return True  # Back edge → cycle!
            if color[neighbor] == 0 and dfs(neighbor):
                return True

        color[node] = 2  # Mark as fully processed
        return False

    return any(dfs(node) for node in graph.nodes if color[node] == 0)


def connected_components(graph: Graph) -> list[set[str]]:
    """Find connected components in an undirected graph."""
    visited = set()
    components = []

    def dfs(node: str, component: set):
        visited.add(node)
        component.add(node)
        for neighbor, _ in graph.neighbors(node):
            if neighbor not in visited:
                dfs(neighbor, component)

    for node in graph.nodes:
        if node not in visited:
            component = set()
            dfs(node, component)
            components.append(component)

    return components


# Application: cycle detection in dependency graphs (circular imports)
# Application: finding isolated clusters in social networks
# Application: determining if a graph is bipartite
```

### Dijkstra's Algorithm: Weighted Shortest Path

```python
def dijkstra(
    graph: Graph, start: str
) -> tuple[dict[str, float], dict[str, Optional[str]]]:
    """Shortest path in weighted graph (non-negative weights)."""
    distances = {node: float("inf") for node in graph.nodes}
    predecessors = {node: None for node in graph.nodes}
    distances[start] = 0

    # Min-heap: (distance, node)
    heap = [(0, start)]

    while heap:
        dist, node = heapq.heappop(heap)

        if dist > distances[node]:
            continue  # Stale entry

        for neighbor, weight in graph.neighbors(node):
            new_dist = dist + weight
            if new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                predecessors[neighbor] = node
                heapq.heappush(heap, (new_dist, neighbor))

    return distances, predecessors


def reconstruct_path(predecessors: dict, start: str, end: str) -> list[str]:
    """Reconstruct shortest path from Dijkstra's predecessors."""
    path = []
    current = end
    while current is not None:
        path.append(current)
        current = predecessors[current]
    path.reverse()
    return path if path[0] == start else []


# Application: routing (GPS navigation)
# Application: network routing protocols (OSPF)
# Application: finding cheapest flight connections
```

### Topological Sort: Dependency Resolution

```python
def topological_sort(graph: Graph) -> Optional[list[str]]:
    """
    Kahn's algorithm: topological ordering of a DAG.
    Returns None if the graph has cycles.
    """
    # Count incoming edges for each node
    in_degree = {node: 0 for node in graph.nodes}
    for node in graph.nodes:
        for neighbor, _ in graph.neighbors(node):
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

    # Start with nodes that have no dependencies
    queue = deque([node for node, deg in in_degree.items() if deg == 0])
    result = []

    while queue:
        node = queue.popleft()
        result.append(node)

        for neighbor, _ in graph.neighbors(node):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(graph.nodes):
        return None  # Cycle detected

    return result


# Real-world dependency resolver
class DependencyResolver:
    """Resolve build/install order for packages with dependencies."""

    def __init__(self):
        self.graph = Graph(directed=True)

    def add_dependency(self, package: str, depends_on: str):
        self.graph.add_edge(depends_on, package)

    def resolve(self) -> list[str]:
        order = topological_sort(self.graph)
        if order is None:
            cycle = self._find_cycle()
            raise CircularDependencyError(
                f"Circular dependency detected: {' -> '.join(cycle)}"
            )
        return order

    def _find_cycle(self) -> list[str]:
        """Find and return a cycle for error reporting."""
        visited = set()
        path = []
        path_set = set()

        def dfs(node):
            visited.add(node)
            path.append(node)
            path_set.add(node)

            for neighbor, _ in self.graph.neighbors(node):
                if neighbor in path_set:
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]
                if neighbor not in visited:
                    result = dfs(neighbor)
                    if result:
                        return result

            path.pop()
            path_set.remove(node)
            return None

        for node in self.graph.nodes:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    return cycle
        return []


# Usage:
resolver = DependencyResolver()
resolver.add_dependency("web-app", "auth-lib")
resolver.add_dependency("web-app", "db-lib")
resolver.add_dependency("auth-lib", "crypto-lib")
resolver.add_dependency("db-lib", "crypto-lib")
build_order = resolver.resolve()
# ['crypto-lib', 'auth-lib', 'db-lib', 'web-app']
```

### A* Pathfinding

```python
def astar(
    graph: Graph,
    start: str,
    goal: str,
    heuristic: callable,  # h(node) -> estimated cost to goal
) -> tuple[list[str], float]:
    """A* search: optimal pathfinding with heuristic guidance."""
    open_set = [(0, start)]
    came_from = {}
    g_score = {start: 0}
    f_score = {start: heuristic(start)}

    while open_set:
        _, current = heapq.heappop(open_set)

        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path, g_score[goal]

        for neighbor, weight in graph.neighbors(current):
            tentative_g = g_score[current] + weight

            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + heuristic(neighbor)
                f_score[neighbor] = f
                heapq.heappush(open_set, (f, neighbor))

    return [], float("inf")  # No path found


# Application: game pathfinding, robot navigation, map routing
# A* = Dijkstra + heuristic guidance → explores fewer nodes
# Heuristic must be admissible (never overestimate) for optimality
```

**Algorithm selection guide**: (1) **BFS** for shortest path in unweighted graphs, (2) **Dijkstra** for shortest path in weighted graphs (no negative weights), (3) **Topological sort** for dependency resolution and build ordering, (4) **DFS** for cycle detection and connected components, (5) **A*** when you have a good distance heuristic (grid maps, road networks)."""
    ),
    (
        "algorithms/btree-lsm-tree-internals",
        r"""Explain B-Tree and LSM-Tree data structures including how they work, read/write performance characteristics, when databases use each, compaction strategies for LSM-Trees, and write amplification trade-offs.""",
        r"""## B-Tree vs LSM-Tree: The Two Pillars of Database Storage Engines

Every database uses one of two fundamental data structures for on-disk storage. Understanding their trade-offs explains why PostgreSQL and RocksDB behave so differently.

### B-Tree: Read-Optimized

B-Trees are balanced search trees where each node can have many children. They're the default storage structure for PostgreSQL, MySQL InnoDB, and SQLite.

```python
from dataclasses import dataclass, field
from typing import Optional, Any
from bisect import bisect_left, insort


@dataclass
class BTreeNode:
    """B-Tree node with order M (max M children, M-1 keys)."""
    keys: list = field(default_factory=list)
    values: list = field(default_factory=list)  # Only in leaf nodes
    children: list = field(default_factory=list)  # Only in internal nodes
    is_leaf: bool = True

    def is_full(self, order: int) -> bool:
        return len(self.keys) >= order - 1


class BTree:
    """Simplified B-Tree demonstrating core operations."""

    def __init__(self, order: int = 4):
        self.order = order  # Max children per node
        self.root = BTreeNode()

    def search(self, key) -> Optional[Any]:
        """Search is O(log_M(N)) — very few disk reads."""
        node = self.root
        while True:
            i = bisect_left(node.keys, key)
            if i < len(node.keys) and node.keys[i] == key:
                if node.is_leaf:
                    return node.values[i]
                # In internal nodes, go to the right child
            if node.is_leaf:
                return None  # Not found
            node = node.children[i]

    def insert(self, key, value):
        """Insert requires finding the leaf, possibly splitting nodes up."""
        if self.root.is_full(self.order):
            # Root is full — create new root and split
            new_root = BTreeNode(is_leaf=False)
            new_root.children = [self.root]
            self._split_child(new_root, 0)
            self.root = new_root

        self._insert_non_full(self.root, key, value)

    def _insert_non_full(self, node: BTreeNode, key, value):
        i = bisect_left(node.keys, key)

        if node.is_leaf:
            node.keys.insert(i, key)
            node.values.insert(i, value)
        else:
            if node.children[i].is_full(self.order):
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1
            self._insert_non_full(node.children[i], key, value)

    def _split_child(self, parent: BTreeNode, child_index: int):
        """Split a full child into two half-full nodes."""
        child = parent.children[child_index]
        mid = len(child.keys) // 2

        # Create new right sibling
        new_node = BTreeNode(is_leaf=child.is_leaf)
        new_node.keys = child.keys[mid + 1:]
        if child.is_leaf:
            new_node.values = child.values[mid + 1:]
        else:
            new_node.children = child.children[mid + 1:]

        # Push median key up to parent
        median_key = child.keys[mid]
        parent.keys.insert(child_index, median_key)
        parent.children.insert(child_index + 1, new_node)

        # Truncate the original child
        child.keys = child.keys[:mid]
        if child.is_leaf:
            child.values = child.values[:mid]
        else:
            child.children = child.children[:mid + 1]


# B-Tree characteristics:
# READ:  O(log_M N) — typically 3-4 disk reads for billions of rows
#        (because M is large, e.g., 100-500 keys per 8KB page)
# WRITE: O(log_M N) — find leaf + update in place
#        BUT: random I/O (need to read-modify-write the page)
# SPACE: ~50-70% page utilization after splits
#
# B-Tree is optimal when:
# - Read-heavy workloads (OLTP, most web apps)
# - Point lookups and range scans
# - Need for strong consistency (update in place)
```

### LSM-Tree: Write-Optimized

LSM-Trees buffer writes in memory, then flush sorted runs to disk. Used in RocksDB, LevelDB, Cassandra, ScyllaDB.

```python
from sortedcontainers import SortedDict
import os
import json
from typing import Optional


class MemTable:
    """In-memory sorted buffer (typically a red-black tree or skip list)."""

    def __init__(self, max_size: int = 4 * 1024 * 1024):  # 4MB
        self.data = SortedDict()
        self.size = 0
        self.max_size = max_size

    def put(self, key: str, value: str):
        self.data[key] = value
        self.size += len(key) + len(value)

    def get(self, key: str) -> Optional[str]:
        return self.data.get(key)

    def delete(self, key: str):
        self.data[key] = None  # Tombstone marker

    def is_full(self) -> bool:
        return self.size >= self.max_size

    def flush_to_sstable(self, path: str) -> "SSTable":
        """Write sorted data to disk as an SSTable."""
        sstable = SSTable(path)
        sstable.write(list(self.data.items()))
        return sstable


class SSTable:
    """Sorted String Table — immutable on-disk sorted file."""

    def __init__(self, path: str):
        self.path = path
        self.index: dict[str, int] = {}  # Sparse index

    def write(self, sorted_pairs: list[tuple[str, str]]):
        """Write sorted key-value pairs to disk."""
        with open(self.path, "w") as f:
            for i, (key, value) in enumerate(sorted_pairs):
                offset = f.tell()
                f.write(json.dumps({"k": key, "v": value}) + "\n")
                # Sparse index: every Nth entry
                if i % 100 == 0:
                    self.index[key] = offset

    def get(self, key: str) -> Optional[str]:
        """Binary search using sparse index + scan."""
        # Find the closest index entry <= key
        candidates = [k for k in self.index if k <= key]
        if not candidates:
            start = 0
        else:
            start = self.index[max(candidates)]

        with open(self.path) as f:
            f.seek(start)
            for line in f:
                entry = json.loads(line)
                if entry["k"] == key:
                    return entry["v"]
                if entry["k"] > key:
                    break
        return None


class LSMTree:
    """Simplified LSM-Tree with leveled compaction."""

    def __init__(self, data_dir: str = "/tmp/lsm"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        self.memtable = MemTable()
        self.immutable_memtable: Optional[MemTable] = None
        self.levels: list[list[SSTable]] = [[] for _ in range(7)]
        self._sstable_counter = 0

    def put(self, key: str, value: str):
        """Write: always goes to memtable first (fast!)."""
        self.memtable.put(key, value)

        if self.memtable.is_full():
            self._flush()

    def get(self, key: str) -> Optional[str]:
        """Read: check memtable → immutable → SSTables (newest first)."""
        # 1. Check active memtable
        result = self.memtable.get(key)
        if result is not None:
            return result if result != "TOMBSTONE" else None

        # 2. Check immutable memtable (being flushed)
        if self.immutable_memtable:
            result = self.immutable_memtable.get(key)
            if result is not None:
                return result if result != "TOMBSTONE" else None

        # 3. Check SSTables from newest to oldest
        for level in self.levels:
            for sstable in reversed(level):
                result = sstable.get(key)
                if result is not None:
                    return result if result != "TOMBSTONE" else None

        return None

    def delete(self, key: str):
        """Delete: write a tombstone marker."""
        self.memtable.put(key, "TOMBSTONE")

    def _flush(self):
        """Flush memtable to L0 SSTable."""
        self.immutable_memtable = self.memtable
        self.memtable = MemTable()

        self._sstable_counter += 1
        path = os.path.join(self.data_dir, f"l0_{self._sstable_counter}.sst")
        sstable = self.immutable_memtable.flush_to_sstable(path)
        self.levels[0].append(sstable)
        self.immutable_memtable = None

        # Trigger compaction if L0 has too many files
        if len(self.levels[0]) > 4:
            self._compact(0)

    def _compact(self, level: int):
        """Merge SSTables from level N into level N+1."""
        # Simplified: merge all files in this level
        # Real LSM: pick overlapping ranges, merge-sort
        pass


# LSM-Tree characteristics:
# WRITE: O(1) amortized — just append to memtable
#        Sequential I/O when flushing (very fast on SSDs and HDDs)
# READ:  O(N * log M) worst case — check each level
#        Bloom filters reduce this to ~1 disk read for negative lookups
# SPACE: Write amplification from compaction (data written multiple times)
#
# LSM-Tree is optimal when:
# - Write-heavy workloads (logging, time-series, ingestion)
# - Sequential write patterns
# - Can tolerate slightly higher read latency
```

### Comparison

```
| Property          | B-Tree              | LSM-Tree                |
|-------------------|---------------------|-------------------------|
| Write pattern     | Random I/O          | Sequential I/O          |
| Write throughput  | Moderate             | Very high               |
| Read latency      | Low (1-3 disk reads) | Higher (check levels)   |
| Space efficiency  | ~60-70% pages full   | Higher after compaction |
| Write amplification| 1x (update in place)| 10-30x (compaction)    |
| Read amplification | 1x                  | 1-5x (bloom filters)   |
| Concurrency       | Page-level locks     | Lock-free writes        |
| Use case          | OLTP (PostgreSQL)    | Write-heavy (RocksDB)   |
```

**Storage engine selection**: (1) **B-Tree** (PostgreSQL, MySQL) for read-heavy OLTP workloads, (2) **LSM-Tree** (RocksDB, Cassandra) for write-heavy ingestion workloads, (3) LSM-Trees trade read latency for write throughput, (4) Bloom filters are essential for LSM read performance — they skip levels that don't contain the key, (5) Compaction strategy (leveled vs size-tiered) is the main tuning knob for LSM-Trees."""
    ),
    (
        "algorithms/bloom-filters-probabilistic",
        r"""Explain Bloom filters and other probabilistic data structures including how Bloom filters work, false positive rate calculation, counting Bloom filters, Count-Min Sketch for frequency estimation, and HyperLogLog for cardinality. Include Python implementations.""",
        r"""## Probabilistic Data Structures: Bloom Filters, Count-Min Sketch, and HyperLogLog

Probabilistic data structures trade perfect accuracy for dramatic space savings. They answer questions like "have I seen this before?", "how many times?", and "how many unique items?" using a fraction of the memory that exact data structures would require.

### Bloom Filter: Membership Testing

A Bloom filter answers "is this element in the set?" with either "definitely not" or "probably yes":

```python
import math
import mmh3  # MurmurHash3
from bitarray import bitarray


class BloomFilter:
    """Space-efficient probabilistic set membership test."""

    def __init__(self, expected_items: int, false_positive_rate: float = 0.01):
        # Calculate optimal bit array size and number of hash functions
        self.size = self._optimal_size(expected_items, false_positive_rate)
        self.num_hashes = self._optimal_hashes(self.size, expected_items)
        self.bits = bitarray(self.size)
        self.bits.setall(0)
        self.count = 0

    def add(self, item: str):
        """Add an item to the filter."""
        for i in range(self.num_hashes):
            idx = mmh3.hash(item, i) % self.size
            self.bits[idx] = 1
        self.count += 1

    def __contains__(self, item: str) -> bool:
        """Check if item might be in the filter."""
        return all(
            self.bits[mmh3.hash(item, i) % self.size]
            for i in range(self.num_hashes)
        )

    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        """Optimal bit array size: m = -(n * ln(p)) / (ln(2)^2)"""
        return int(-n * math.log(p) / (math.log(2) ** 2))

    @staticmethod
    def _optimal_hashes(m: int, n: int) -> int:
        """Optimal number of hashes: k = (m/n) * ln(2)"""
        return max(1, int(m / n * math.log(2)))

    @property
    def estimated_false_positive_rate(self) -> float:
        """Current estimated false positive rate."""
        # (1 - e^(-k*n/m))^k
        k, n, m = self.num_hashes, self.count, self.size
        return (1 - math.exp(-k * n / m)) ** k

    def memory_usage_bytes(self) -> int:
        return self.size // 8


# Usage example: URL deduplication in web crawler
bloom = BloomFilter(expected_items=10_000_000, false_positive_rate=0.001)

# Memory: ~18MB for 10M items at 0.1% false positive rate
# vs ~800MB for a HashSet of 10M URLs

urls_to_crawl = ["https://example.com/page1", "https://example.com/page2"]
for url in urls_to_crawl:
    if url not in bloom:
        bloom.add(url)
        crawl(url)
    else:
        pass  # Probably already crawled (0.1% chance of false positive)


# Real-world uses:
# - Web crawlers: skip already-visited URLs
# - Databases: skip disk reads for non-existent keys (LSM-Tree)
# - CDNs: check if content is cached without querying cache
# - Email: check if address is in blocklist
```

### Counting Bloom Filter

Supports deletions by using counters instead of bits:

```python
class CountingBloomFilter:
    """Bloom filter that supports deletion using counters."""

    def __init__(self, expected_items: int, fp_rate: float = 0.01):
        self.size = BloomFilter._optimal_size(expected_items, fp_rate)
        self.num_hashes = BloomFilter._optimal_hashes(self.size, expected_items)
        self.counters = [0] * self.size  # 4-bit counters typically

    def add(self, item: str):
        for i in range(self.num_hashes):
            idx = mmh3.hash(item, i) % self.size
            self.counters[idx] = min(15, self.counters[idx] + 1)  # 4-bit max

    def remove(self, item: str):
        """Remove an item (only if previously added!)."""
        if item not in self:
            return
        for i in range(self.num_hashes):
            idx = mmh3.hash(item, i) % self.size
            self.counters[idx] = max(0, self.counters[idx] - 1)

    def __contains__(self, item: str) -> bool:
        return all(
            self.counters[mmh3.hash(item, i) % self.size] > 0
            for i in range(self.num_hashes)
        )


# Use when you need to remove items (e.g., user session tracking)
# 4x more memory than standard Bloom filter (4 bits vs 1 bit per slot)
```

### Count-Min Sketch: Frequency Estimation

Estimate how many times each element has appeared:

```python
class CountMinSketch:
    """Estimate frequency of elements with bounded error."""

    def __init__(self, width: int = 10000, depth: int = 7):
        """
        width: number of counters per row (larger = more accurate)
        depth: number of hash functions (more = lower error probability)

        Error guarantee: estimate <= true_count + epsilon * total_count
        where epsilon = e / width, probability of exceeding: (1/e)^depth
        """
        self.width = width
        self.depth = depth
        self.table = [[0] * width for _ in range(depth)]
        self.total = 0

    def add(self, item: str, count: int = 1):
        """Record 'count' occurrences of item."""
        self.total += count
        for i in range(self.depth):
            idx = mmh3.hash(item, i) % self.width
            self.table[i][idx] += count

    def estimate(self, item: str) -> int:
        """Estimate frequency. Always >= true count (may overestimate)."""
        return min(
            self.table[i][mmh3.hash(item, i) % self.width]
            for i in range(self.depth)
        )


# Usage: finding heavy hitters (most frequent items) in a stream
sketch = CountMinSketch(width=100000, depth=7)
# Memory: ~2.8MB (100K * 7 * 4 bytes)
# vs potentially gigabytes for exact counting of millions of items

for event in event_stream:
    sketch.add(event.item_id)

# Find top items
top_items = []
for item_id in candidate_items:
    freq = sketch.estimate(item_id)
    if freq > threshold:
        top_items.append((item_id, freq))

# Real-world uses:
# - Network traffic monitoring (find top talkers)
# - Database query frequency tracking
# - Trending topic detection
# - Cache eviction (LFU approximation)
```

### HyperLogLog: Cardinality Estimation

Count unique elements with O(1) memory:

```python
class HyperLogLog:
    """Estimate number of distinct elements using ~12KB of memory."""

    def __init__(self, precision: int = 14):
        """
        precision: number of bits for register addressing (4-18)
        Higher = more accurate but more memory
        p=14: 16384 registers, ~0.81% error, ~12KB memory
        """
        self.precision = precision
        self.num_registers = 1 << precision
        self.registers = [0] * self.num_registers
        self._alpha = self._compute_alpha(self.num_registers)

    def add(self, item: str):
        """Add an item to the counter."""
        h = mmh3.hash(item, signed=False)

        # First p bits determine the register
        register_idx = h & (self.num_registers - 1)

        # Remaining bits: count leading zeros + 1
        remaining = h >> self.precision
        run_length = self._count_leading_zeros(remaining) + 1

        # Keep the maximum run length seen for this register
        self.registers[register_idx] = max(
            self.registers[register_idx], run_length
        )

    def count(self) -> int:
        """Estimate the number of distinct elements."""
        # Harmonic mean of 2^(-register[i])
        raw_estimate = self._alpha * self.num_registers ** 2 / sum(
            2.0 ** (-r) for r in self.registers
        )

        # Small range correction
        if raw_estimate <= 2.5 * self.num_registers:
            zeros = self.registers.count(0)
            if zeros > 0:
                return int(self.num_registers * math.log(self.num_registers / zeros))

        return int(raw_estimate)

    def merge(self, other: "HyperLogLog"):
        """Merge two HLLs (union of counted elements)."""
        assert self.num_registers == other.num_registers
        for i in range(self.num_registers):
            self.registers[i] = max(self.registers[i], other.registers[i])

    @staticmethod
    def _count_leading_zeros(value: int, max_bits: int = 32) -> int:
        if value == 0:
            return max_bits
        count = 0
        for i in range(max_bits - 1, -1, -1):
            if value & (1 << i):
                break
            count += 1
        return count

    @staticmethod
    def _compute_alpha(m: int) -> float:
        if m == 16:
            return 0.673
        elif m == 32:
            return 0.697
        elif m == 64:
            return 0.709
        return 0.7213 / (1 + 1.079 / m)


# Usage: count unique visitors
hll = HyperLogLog(precision=14)

for visitor_id in visitor_stream:  # Millions of events
    hll.add(visitor_id)

print(f"Estimated unique visitors: {hll.count()}")
# Memory: ~12KB regardless of cardinality
# Error: ±0.81%

# Merge HLLs from different servers
hll_server1 = HyperLogLog()
hll_server2 = HyperLogLog()
# ... add events to each ...
hll_server1.merge(hll_server2)  # Combined unique count
```

**Probabilistic DS selection guide**: (1) **Bloom filter** for "have I seen this?" — web crawlers, cache lookups, database key existence, (2) **Count-Min Sketch** for "how often?" — frequency estimation, heavy hitter detection, (3) **HyperLogLog** for "how many unique?" — unique visitor counts, cardinality estimation, (4) All three trade accuracy for extreme space efficiency — 12KB HLL vs gigabytes for exact sets, (5) Bloom filters have NO false negatives — "definitely not in set" is always correct."""
    ),
    (
        "algorithms/hash-table-design",
        r"""Explain hash table design including hash function properties, collision resolution strategies (chaining, open addressing, Robin Hood hashing), load factor management, consistent hashing for distributed systems, and implementing a production-quality hash map.""",
        r"""## Hash Table Design: Collision Resolution, Consistent Hashing, and Performance

Hash tables provide O(1) average-case lookups — the most used data structure in software. Understanding their internals explains performance characteristics and helps design distributed systems.

### Hash Function Properties

```python
# A good hash function has:
# 1. Deterministic: same input always gives same output
# 2. Uniform distribution: outputs are evenly spread
# 3. Avalanche effect: small input change → big output change
# 4. Fast to compute

# Python's built-in hash() changes per process (security)
# For persistent hashing, use a stable hash:

import hashlib
import struct


def stable_hash(key: str) -> int:
    """Deterministic hash that's stable across processes/restarts."""
    return int(hashlib.md5(key.encode()).hexdigest(), 16)


def fnv1a_hash(data: bytes) -> int:
    """FNV-1a: fast non-cryptographic hash."""
    h = 0xcbf29ce484222325  # FNV offset basis
    for byte in data:
        h ^= byte
        h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF  # FNV prime
    return h
```

### Collision Resolution: Chaining vs Open Addressing

```python
class ChainingHashMap:
    """Hash map with separate chaining (linked list per bucket)."""

    def __init__(self, initial_capacity: int = 16, max_load_factor: float = 0.75):
        self.capacity = initial_capacity
        self.max_load_factor = max_load_factor
        self.size = 0
        self.buckets: list[list] = [[] for _ in range(self.capacity)]

    def put(self, key, value):
        idx = hash(key) % self.capacity

        # Check if key exists in chain
        for i, (k, v) in enumerate(self.buckets[idx]):
            if k == key:
                self.buckets[idx][i] = (key, value)
                return

        self.buckets[idx].append((key, value))
        self.size += 1

        if self.size / self.capacity > self.max_load_factor:
            self._resize()

    def get(self, key, default=None):
        idx = hash(key) % self.capacity
        for k, v in self.buckets[idx]:
            if k == key:
                return v
        return default

    def delete(self, key) -> bool:
        idx = hash(key) % self.capacity
        for i, (k, v) in enumerate(self.buckets[idx]):
            if k == key:
                self.buckets[idx].pop(i)
                self.size -= 1
                return True
        return False

    def _resize(self):
        old_buckets = self.buckets
        self.capacity *= 2
        self.buckets = [[] for _ in range(self.capacity)]
        self.size = 0
        for chain in old_buckets:
            for key, value in chain:
                self.put(key, value)


class OpenAddressingHashMap:
    """Hash map with open addressing (Robin Hood hashing)."""

    EMPTY = object()
    DELETED = object()

    def __init__(self, initial_capacity: int = 16):
        self.capacity = initial_capacity
        self.size = 0
        self.keys = [self.EMPTY] * self.capacity
        self.values = [None] * self.capacity
        self.distances = [0] * self.capacity  # Probe distance from home

    def put(self, key, value):
        if self.size * 10 > self.capacity * 7:  # Load factor > 0.7
            self._resize()

        idx = hash(key) % self.capacity
        distance = 0

        while True:
            if self.keys[idx] is self.EMPTY or self.keys[idx] is self.DELETED:
                self.keys[idx] = key
                self.values[idx] = value
                self.distances[idx] = distance
                self.size += 1
                return

            if self.keys[idx] == key:
                self.values[idx] = value  # Update existing
                return

            # Robin Hood: if current element is closer to home than us,
            # steal its spot and continue with the displaced element
            if distance > self.distances[idx]:
                # Swap
                key, self.keys[idx] = self.keys[idx], key
                value, self.values[idx] = self.values[idx], value
                distance, self.distances[idx] = self.distances[idx], distance

            idx = (idx + 1) % self.capacity
            distance += 1

    def get(self, key, default=None):
        idx = hash(key) % self.capacity
        distance = 0

        while True:
            if self.keys[idx] is self.EMPTY:
                return default

            if self.keys[idx] == key:
                return self.values[idx]

            # Robin Hood optimization: if distance exceeds what we'd have,
            # the key doesn't exist (would have been placed here)
            if distance > self.distances[idx]:
                return default

            idx = (idx + 1) % self.capacity
            distance += 1

    def _resize(self):
        old_keys = self.keys
        old_values = self.values
        self.capacity *= 2
        self.keys = [self.EMPTY] * self.capacity
        self.values = [None] * self.capacity
        self.distances = [0] * self.capacity
        self.size = 0
        for k, v in zip(old_keys, old_values):
            if k is not self.EMPTY and k is not self.DELETED:
                self.put(k, v)
```

### Consistent Hashing for Distributed Systems

Distribute data across nodes so that adding/removing a node only remaps ~1/N of keys:

```python
import hashlib
from bisect import bisect_right


class ConsistentHashRing:
    """Consistent hash ring for distributed data placement."""

    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring: list[tuple[int, str]] = []  # Sorted (hash, node_id)
        self.nodes: set[str] = set()

    def add_node(self, node_id: str):
        """Add a node with virtual nodes for better distribution."""
        self.nodes.add(node_id)
        for i in range(self.virtual_nodes):
            key = f"{node_id}:vnode:{i}"
            h = self._hash(key)
            self.ring.append((h, node_id))
        self.ring.sort()

    def remove_node(self, node_id: str):
        """Remove a node — only its keys are redistributed."""
        self.nodes.discard(node_id)
        self.ring = [(h, n) for h, n in self.ring if n != node_id]

    def get_node(self, key: str) -> str:
        """Find which node owns this key."""
        if not self.ring:
            raise RuntimeError("No nodes in ring")

        h = self._hash(key)
        idx = bisect_right(self.ring, (h,))
        if idx >= len(self.ring):
            idx = 0  # Wrap around

        return self.ring[idx][1]

    def get_nodes(self, key: str, count: int = 3) -> list[str]:
        """Get N distinct nodes for replication."""
        if len(self.nodes) < count:
            return list(self.nodes)

        h = self._hash(key)
        idx = bisect_right(self.ring, (h,))

        result = []
        seen = set()
        for i in range(len(self.ring)):
            pos = (idx + i) % len(self.ring)
            node = self.ring[pos][1]
            if node not in seen:
                seen.add(node)
                result.append(node)
                if len(result) >= count:
                    break

        return result

    @staticmethod
    def _hash(key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)


# Usage: distributed cache
ring = ConsistentHashRing(virtual_nodes=150)
ring.add_node("cache-1")
ring.add_node("cache-2")
ring.add_node("cache-3")

# Route request to correct cache node
node = ring.get_node("user:42:profile")  # Deterministic routing

# Adding cache-4 only remaps ~25% of keys (1/4)
ring.add_node("cache-4")

# Get replicas for redundancy
replicas = ring.get_nodes("user:42:profile", count=2)
```

**Hash table design principles**: (1) **Chaining** is simpler and degrades gracefully — chains just get longer, (2) **Open addressing** is more cache-friendly and uses less memory per entry, (3) **Robin Hood hashing** reduces variance in probe lengths — worst case approaches average case, (4) Keep load factor below 0.75 for open addressing, below 1.0 for chaining, (5) **Consistent hashing** with virtual nodes ensures uniform distribution and minimal disruption when nodes join/leave."""
    ),
    (
        "algorithms/skip-list-implementation",
        r"""Explain skip lists including how they work as a probabilistic alternative to balanced trees, insertion with random level generation, search and delete operations, comparison with red-black trees, and why Redis uses skip lists for sorted sets.""",
        r"""## Skip Lists: Probabilistic Alternative to Balanced Trees

A skip list is a layered linked list where higher layers act as "express lanes" for faster traversal. It provides O(log n) expected search, insert, and delete — same as balanced BSTs — but with much simpler implementation.

### How Skip Lists Work

```
Level 3:  HEAD ──────────────────────────────────→ 50 ──────────────→ NIL
Level 2:  HEAD ──────────→ 20 ──────────────────→ 50 ──→ 70 ──────→ NIL
Level 1:  HEAD ──→ 10 ──→ 20 ──→ 30 ──────────→ 50 ──→ 70 ──→ 80 → NIL
Level 0:  HEAD → 5 → 10 → 20 → 25 → 30 → 40 → 50 → 60 → 70 → 80 → NIL
```

Search for 40:
1. Start at HEAD, Level 3: 50 > 40, go down
2. Level 2: 20 < 40, go right. 50 > 40, go down
3. Level 1: 30 < 40, go right. 50 > 40, go down
4. Level 0: 40 = 40, found!

### Implementation

```python
import random
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class SkipListNode:
    key: Any
    value: Any
    forward: list = field(default_factory=list)  # Forward pointers per level

    def __repr__(self):
        return f"Node({self.key}, levels={len(self.forward)})"


class SkipList:
    """Skip list with probabilistic balancing."""

    MAX_LEVEL = 32  # Supports up to 2^32 elements efficiently
    P = 0.25  # Probability of promoting to next level

    def __init__(self):
        self.header = SkipListNode(key=None, value=None)
        self.header.forward = [None] * self.MAX_LEVEL
        self.level = 0  # Current max level in use
        self.size = 0

    def _random_level(self) -> int:
        """Generate random level with geometric distribution.
        Each level has P probability of being promoted higher.
        Expected height: 1 / (1 - P)
        """
        level = 0
        while random.random() < self.P and level < self.MAX_LEVEL - 1:
            level += 1
        return level

    def search(self, key) -> Optional[Any]:
        """Search for a key. O(log n) expected time."""
        current = self.header

        # Traverse from top level down
        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]

        # Check the next node at level 0
        current = current.forward[0]
        if current and current.key == key:
            return current.value
        return None

    def insert(self, key, value):
        """Insert a key-value pair. O(log n) expected time."""
        # Track the rightmost node at each level that precedes the insertion point
        update = [None] * self.MAX_LEVEL
        current = self.header

        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
            update[i] = current

        # Check if key already exists
        current = current.forward[0]
        if current and current.key == key:
            current.value = value  # Update existing
            return

        # Generate random level for new node
        new_level = self._random_level()

        # If new level exceeds current max, update headers
        if new_level > self.level:
            for i in range(self.level + 1, new_level + 1):
                update[i] = self.header
            self.level = new_level

        # Create and insert new node
        new_node = SkipListNode(key=key, value=value)
        new_node.forward = [None] * (new_level + 1)

        for i in range(new_level + 1):
            new_node.forward[i] = update[i].forward[i]
            update[i].forward[i] = new_node

        self.size += 1

    def delete(self, key) -> bool:
        """Delete a key. O(log n) expected time."""
        update = [None] * self.MAX_LEVEL
        current = self.header

        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
            update[i] = current

        target = current.forward[0]
        if not target or target.key != key:
            return False  # Key not found

        # Remove target from each level
        for i in range(self.level + 1):
            if update[i].forward[i] != target:
                break
            update[i].forward[i] = target.forward[i]

        # Reduce level if necessary
        while self.level > 0 and self.header.forward[self.level] is None:
            self.level -= 1

        self.size -= 1
        return True

    def range_query(self, min_key, max_key) -> list[tuple]:
        """Efficient range query. O(log n + k) where k = results."""
        results = []
        current = self.header

        # Find start position
        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < min_key:
                current = current.forward[i]

        # Scan forward at level 0
        current = current.forward[0]
        while current and current.key <= max_key:
            results.append((current.key, current.value))
            current = current.forward[0]

        return results

    def __len__(self):
        return self.size

    def __contains__(self, key):
        return self.search(key) is not None


# Usage:
sl = SkipList()
for i in range(10000):
    sl.insert(i, f"value-{i}")

# Search
assert sl.search(5000) == "value-5000"  # O(log n) ~ 14 comparisons

# Range query
results = sl.range_query(100, 110)  # All items between 100 and 110
```

### Why Redis Uses Skip Lists for Sorted Sets

```python
# Redis sorted sets (ZSET) need:
# 1. O(log n) insert/delete/search by score
# 2. O(log n + k) range queries by score
# 3. O(1) rank queries (position in sorted order)
# 4. Easy iteration in sorted order
#
# Skip list vs Red-Black tree comparison:
#
# | Operation      | Skip List    | Red-Black Tree |
# |----------------|-------------|----------------|
# | Insert         | O(log n)    | O(log n)       |
# | Delete         | O(log n)    | O(log n)       |
# | Search         | O(log n)    | O(log n)       |
# | Range query    | O(log n + k)| O(log n + k)   |
# | Implementation | ~100 lines  | ~500 lines     |
# | Concurrency    | Easy (fine-grained locks) | Hard |
# | Memory overhead| ~1.33 ptrs/node | 3 ptrs + color |
# | Cache locality | Moderate    | Poor           |
#
# Redis chose skip lists because:
# 1. SIMPLER to implement and debug (Antirez's main reason)
# 2. Easy to extend: Redis adds a span field for O(log n) rank queries
# 3. Range operations are natural: just walk level 0
# 4. Concurrent modifications are simpler (lock fewer nodes)
# 5. Memory is comparable to balanced trees

# Redis skip list enhancement: span tracking for rank queries
@dataclass
class RedisSkipListLevel:
    forward: Optional["RedisSkipListNode"] = None
    span: int = 0  # Number of nodes between this and forward


# With spans, ZRANK (get rank by score) is O(log n):
# Sum the spans while searching down the skip list
```

### Comparison with Balanced Trees

```python
# When to use skip lists:
# ✓ You need range queries (natural in skip lists)
# ✓ You want simple implementation
# ✓ Concurrent access is needed (easier to lock)
# ✓ You need rank queries (with span tracking)
#
# When to use balanced trees (Red-Black, AVL):
# ✓ You need guaranteed O(log n) worst case (not just expected)
# ✓ Memory efficiency is critical (no wasted pointers)
# ✓ You're using a standard library implementation
#
# When to use hash tables instead:
# ✓ You only need exact-match lookups (no ranges, no ordering)
# ✓ O(1) average is important
```

**Skip list insights**: (1) Probabilistic balancing is simpler than rotation-based balancing — no complex tree rotations, (2) Expected O(log n) with high probability — degenerate O(n) case is astronomically unlikely, (3) Range queries are natural — just walk level 0 from start to end, (4) P=0.25 (Redis's choice) uses less memory than P=0.5 with only slightly taller structures, (5) Skip lists shine in concurrent settings — you only need to lock a few nodes during updates."""
    ),
]
