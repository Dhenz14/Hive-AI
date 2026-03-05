"""Algorithms — data structures, graph algorithms, and common interview patterns."""

PAIRS = [
    (
        "algorithms/data-structures",
        "Show practical data structure implementations: LRU cache, trie, min-heap, and union-find.",
        '''Data structure implementations:

```python
from collections import OrderedDict
from typing import TypeVar, Generic, Optional, Iterator

T = TypeVar("T")


# --- LRU Cache ---

class LRUCache(Generic[T]):
    """Least Recently Used cache with O(1) operations."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._cache: OrderedDict[str, T] = OrderedDict()

    def get(self, key: str) -> Optional[T]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: T) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)  # Remove oldest

    def __len__(self) -> int:
        return len(self._cache)


# --- Trie (prefix tree) ---

class TrieNode:
    __slots__ = ("children", "is_end", "value")

    def __init__(self):
        self.children: dict[str, TrieNode] = {}
        self.is_end: bool = False
        self.value = None

class Trie:
    """Prefix tree for autocomplete and prefix matching."""

    def __init__(self):
        self.root = TrieNode()

    def insert(self, word: str, value=None) -> None:
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end = True
        node.value = value

    def search(self, word: str) -> bool:
        node = self._find_node(word)
        return node is not None and node.is_end

    def starts_with(self, prefix: str) -> list[str]:
        """Find all words with given prefix."""
        node = self._find_node(prefix)
        if not node:
            return []
        results = []
        self._collect(node, prefix, results)
        return results

    def _find_node(self, prefix: str) -> Optional[TrieNode]:
        node = self.root
        for char in prefix:
            if char not in node.children:
                return None
            node = node.children[char]
        return node

    def _collect(self, node: TrieNode, prefix: str, results: list):
        if node.is_end:
            results.append(prefix)
        for char, child in node.children.items():
            self._collect(child, prefix + char, results)


# --- Min-Heap (priority queue) ---

class MinHeap(Generic[T]):
    """Binary min-heap for priority queue operations."""

    def __init__(self):
        self._data: list[tuple[float, T]] = []

    def push(self, priority: float, item: T) -> None:
        self._data.append((priority, item))
        self._sift_up(len(self._data) - 1)

    def pop(self) -> tuple[float, T]:
        if not self._data:
            raise IndexError("Heap is empty")
        self._swap(0, len(self._data) - 1)
        item = self._data.pop()
        if self._data:
            self._sift_down(0)
        return item

    def peek(self) -> tuple[float, T]:
        if not self._data:
            raise IndexError("Heap is empty")
        return self._data[0]

    def _sift_up(self, i: int):
        while i > 0:
            parent = (i - 1) // 2
            if self._data[i][0] < self._data[parent][0]:
                self._swap(i, parent)
                i = parent
            else:
                break

    def _sift_down(self, i: int):
        n = len(self._data)
        while True:
            smallest = i
            left = 2 * i + 1
            right = 2 * i + 2
            if left < n and self._data[left][0] < self._data[smallest][0]:
                smallest = left
            if right < n and self._data[right][0] < self._data[smallest][0]:
                smallest = right
            if smallest != i:
                self._swap(i, smallest)
                i = smallest
            else:
                break

    def _swap(self, i: int, j: int):
        self._data[i], self._data[j] = self._data[j], self._data[i]

    def __len__(self) -> int:
        return len(self._data)

    def __bool__(self) -> bool:
        return bool(self._data)


# --- Union-Find (Disjoint Set) ---

class UnionFind:
    """Disjoint set with path compression and union by rank."""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n
        self.count = n  # Number of components

    def find(self, x: int) -> int:
        """Find root with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        """Union by rank. Returns True if merged."""
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1
        self.count -= 1
        return True

    def connected(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)
```

Data structure patterns:
1. **LRU Cache** — `OrderedDict.move_to_end()` for O(1) access + eviction
2. **Trie** — O(L) prefix search for autocomplete (L = word length)
3. **Min-Heap** — O(log n) push/pop for priority queues
4. **Union-Find** — near O(1) amortized with path compression + union by rank
5. **`__slots__`** — reduce memory overhead for nodes with many instances'''
    ),
    (
        "algorithms/graph-algorithms",
        "Show graph algorithm patterns: BFS, DFS, Dijkstra, topological sort, and cycle detection.",
        '''Graph algorithm patterns:

```python
from collections import defaultdict, deque
from typing import TypeVar, Iterator
import heapq

T = TypeVar("T")


class Graph:
    """Adjacency list graph with weighted edges."""

    def __init__(self, directed: bool = True):
        self.directed = directed
        self.adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self._nodes: set[str] = set()

    def add_edge(self, u: str, v: str, weight: float = 1.0):
        self.adj[u].append((v, weight))
        self._nodes.update([u, v])
        if not self.directed:
            self.adj[v].append((u, weight))

    @property
    def nodes(self) -> set[str]:
        return self._nodes


# --- BFS (shortest path in unweighted graph) ---

def bfs(graph: Graph, start: str) -> dict[str, int]:
    """BFS: returns shortest distance from start to all reachable nodes."""
    distances = {start: 0}
    queue = deque([start])

    while queue:
        node = queue.popleft()
        for neighbor, _ in graph.adj[node]:
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)

    return distances


def bfs_path(graph: Graph, start: str, end: str) -> list[str]:
    """Find shortest path using BFS."""
    if start == end:
        return [start]

    visited = {start}
    queue = deque([(start, [start])])

    while queue:
        node, path = queue.popleft()
        for neighbor, _ in graph.adj[node]:
            if neighbor == end:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return []  # No path found


# --- DFS (traversal + cycle detection) ---

def dfs_iterative(graph: Graph, start: str) -> Iterator[str]:
    """Iterative DFS traversal."""
    visited = set()
    stack = [start]

    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        yield node
        for neighbor, _ in graph.adj[node]:
            if neighbor not in visited:
                stack.append(neighbor)


def has_cycle(graph: Graph) -> bool:
    """Detect cycle in directed graph using DFS coloring."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph.nodes}

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbor, _ in graph.adj[node]:
            if color[neighbor] == GRAY:
                return True  # Back edge = cycle
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node] = BLACK
        return False

    return any(
        dfs(node) for node in graph.nodes if color[node] == WHITE
    )


# --- Dijkstra (shortest path in weighted graph) ---

def dijkstra(graph: Graph, start: str) -> tuple[dict, dict]:
    """Dijkstra's algorithm: shortest paths from start.
    Returns (distances, predecessors) for path reconstruction."""
    dist = {node: float("inf") for node in graph.nodes}
    dist[start] = 0
    prev = {node: None for node in graph.nodes}
    heap = [(0, start)]

    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue  # Stale entry

        for v, weight in graph.adj[u]:
            new_dist = dist[u] + weight
            if new_dist < dist[v]:
                dist[v] = new_dist
                prev[v] = u
                heapq.heappush(heap, (new_dist, v))

    return dist, prev


def reconstruct_path(prev: dict, start: str, end: str) -> list[str]:
    """Reconstruct shortest path from Dijkstra's predecessor map."""
    path = []
    node = end
    while node is not None:
        path.append(node)
        node = prev[node]
    path.reverse()
    return path if path[0] == start else []


# --- Topological sort (DAG ordering) ---

def topological_sort(graph: Graph) -> list[str]:
    """Kahn's algorithm: topological ordering of DAG."""
    in_degree = defaultdict(int)
    for node in graph.nodes:
        for neighbor, _ in graph.adj[node]:
            in_degree[neighbor] += 1

    # Start with nodes that have no dependencies
    queue = deque(
        node for node in graph.nodes if in_degree[node] == 0
    )
    result = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor, _ in graph.adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(graph.nodes):
        raise ValueError("Graph has a cycle (not a DAG)")

    return result


# Usage:
# g = Graph(directed=True)
# g.add_edge("A", "B", 4)
# g.add_edge("A", "C", 2)
# g.add_edge("B", "D", 3)
# g.add_edge("C", "B", 1)
# g.add_edge("C", "D", 5)
# dist, prev = dijkstra(g, "A")
# path = reconstruct_path(prev, "A", "D")  # ["A", "C", "B", "D"]
```

Graph algorithm patterns:
1. **BFS** — shortest path in unweighted graphs, level-order traversal
2. **DFS coloring** — WHITE/GRAY/BLACK for cycle detection in directed graphs
3. **Dijkstra** — shortest weighted paths with min-heap priority queue
4. **Topological sort** — dependency ordering using Kahn's algorithm (in-degree)
5. **Path reconstruction** — predecessor map from Dijkstra traces back shortest path'''
    ),
    (
        "algorithms/common-patterns",
        "Show common algorithm patterns: sliding window, two pointers, binary search, and dynamic programming.",
        '''Common algorithm patterns:

```python
from typing import TypeVar, Sequence, Optional
from collections import Counter, defaultdict

T = TypeVar("T")


# --- Sliding window ---

def max_sum_subarray(nums: list[int], k: int) -> int:
    """Maximum sum of subarray of size k."""
    window_sum = sum(nums[:k])
    max_sum = window_sum

    for i in range(k, len(nums)):
        window_sum += nums[i] - nums[i - k]
        max_sum = max(max_sum, window_sum)

    return max_sum


def longest_substring_k_distinct(s: str, k: int) -> int:
    """Longest substring with at most k distinct characters."""
    freq = Counter()
    left = 0
    max_len = 0

    for right in range(len(s)):
        freq[s[right]] += 1

        while len(freq) > k:
            freq[s[left]] -= 1
            if freq[s[left]] == 0:
                del freq[s[left]]
            left += 1

        max_len = max(max_len, right - left + 1)

    return max_len


# --- Two pointers ---

def two_sum_sorted(nums: list[int], target: int) -> tuple[int, int]:
    """Find pair summing to target in sorted array."""
    left, right = 0, len(nums) - 1

    while left < right:
        current = nums[left] + nums[right]
        if current == target:
            return left, right
        elif current < target:
            left += 1
        else:
            right -= 1

    return -1, -1


def remove_duplicates(nums: list[int]) -> int:
    """Remove duplicates in-place from sorted array. Returns new length."""
    if not nums:
        return 0

    write = 1
    for read in range(1, len(nums)):
        if nums[read] != nums[read - 1]:
            nums[write] = nums[read]
            write += 1

    return write


# --- Binary search ---

def binary_search(arr: list[int], target: int) -> int:
    """Standard binary search. Returns index or -1."""
    left, right = 0, len(arr) - 1

    while left <= right:
        mid = left + (right - left) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1

    return -1


def bisect_left_custom(arr: list[int], target: int) -> int:
    """Find leftmost position where target could be inserted."""
    left, right = 0, len(arr)

    while left < right:
        mid = left + (right - left) // 2
        if arr[mid] < target:
            left = mid + 1
        else:
            right = mid

    return left


def search_rotated(nums: list[int], target: int) -> int:
    """Binary search in rotated sorted array."""
    left, right = 0, len(nums) - 1

    while left <= right:
        mid = left + (right - left) // 2
        if nums[mid] == target:
            return mid

        # Left half is sorted
        if nums[left] <= nums[mid]:
            if nums[left] <= target < nums[mid]:
                right = mid - 1
            else:
                left = mid + 1
        # Right half is sorted
        else:
            if nums[mid] < target <= nums[right]:
                left = mid + 1
            else:
                right = mid - 1

    return -1


# --- Dynamic programming ---

def longest_common_subsequence(s1: str, s2: str) -> int:
    """LCS length with O(min(m,n)) space."""
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    prev = [0] * (len(s2) + 1)

    for i in range(1, len(s1) + 1):
        curr = [0] * (len(s2) + 1)
        for j in range(1, len(s2) + 1):
            if s1[i - 1] == s2[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr

    return prev[len(s2)]


def knapsack(weights: list[int], values: list[int],
             capacity: int) -> int:
    """0/1 knapsack with O(capacity) space."""
    dp = [0] * (capacity + 1)

    for w, v in zip(weights, values):
        for c in range(capacity, w - 1, -1):
            dp[c] = max(dp[c], dp[c - w] + v)

    return dp[capacity]


def coin_change(coins: list[int], amount: int) -> int:
    """Minimum coins to make amount. Returns -1 if impossible."""
    dp = [float("inf")] * (amount + 1)
    dp[0] = 0

    for coin in coins:
        for a in range(coin, amount + 1):
            dp[a] = min(dp[a], dp[a - coin] + 1)

    return dp[amount] if dp[amount] != float("inf") else -1
```

Algorithm patterns:
1. **Sliding window** — expand right, shrink left when constraint violated
2. **Two pointers** — converge from both ends for sorted array problems
3. **Binary search** — `left + (right - left) // 2` prevents overflow
4. **DP space optimization** — 2D DP often reducible to 1D with rolling array
5. **Rotated array search** — identify sorted half, then standard binary search'''
    ),
]
