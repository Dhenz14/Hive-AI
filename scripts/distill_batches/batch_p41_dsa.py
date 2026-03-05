"""Data structures and algorithms — practical implementations and interview patterns."""

PAIRS = [
    (
        "algorithms/common-patterns",
        "Show common algorithm patterns: two pointers, sliding window, binary search, BFS/DFS, and dynamic programming with Python examples.",
        '''Essential algorithm patterns with Python:

```python
from typing import Optional
from collections import deque

# --- Two Pointers ---

def two_sum_sorted(nums: list[int], target: int) -> tuple[int, int]:
    """Find two numbers that sum to target in sorted array. O(n)."""
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
    """Remove duplicates in-place from sorted array. O(n)."""
    if not nums:
        return 0
    write = 1
    for read in range(1, len(nums)):
        if nums[read] != nums[read - 1]:
            nums[write] = nums[read]
            write += 1
    return write

def is_palindrome(s: str) -> bool:
    """Check if string is palindrome (ignoring non-alphanumeric)."""
    left, right = 0, len(s) - 1
    while left < right:
        while left < right and not s[left].isalnum():
            left += 1
        while left < right and not s[right].isalnum():
            right -= 1
        if s[left].lower() != s[right].lower():
            return False
        left += 1
        right -= 1
    return True


# --- Sliding Window ---

def max_subarray_sum(nums: list[int], k: int) -> int:
    """Maximum sum of subarray of size k. O(n)."""
    window_sum = sum(nums[:k])
    max_sum = window_sum
    for i in range(k, len(nums)):
        window_sum += nums[i] - nums[i - k]
        max_sum = max(max_sum, window_sum)
    return max_sum

def longest_unique_substring(s: str) -> int:
    """Length of longest substring without repeating characters. O(n)."""
    seen = {}
    max_len = 0
    start = 0
    for end, char in enumerate(s):
        if char in seen and seen[char] >= start:
            start = seen[char] + 1
        seen[char] = end
        max_len = max(max_len, end - start + 1)
    return max_len

def min_window_substring(s: str, t: str) -> str:
    """Smallest window in s containing all characters of t. O(n)."""
    from collections import Counter
    need = Counter(t)
    have = Counter()
    formed = 0
    required = len(need)
    result = ""
    min_len = float("inf")
    left = 0

    for right, char in enumerate(s):
        have[char] += 1
        if char in need and have[char] == need[char]:
            formed += 1

        while formed == required:
            window_len = right - left + 1
            if window_len < min_len:
                min_len = window_len
                result = s[left:right + 1]
            have[s[left]] -= 1
            if s[left] in need and have[s[left]] < need[s[left]]:
                formed -= 1
            left += 1

    return result


# --- Binary Search ---

def binary_search(nums: list[int], target: int) -> int:
    """Standard binary search. O(log n)."""
    left, right = 0, len(nums) - 1
    while left <= right:
        mid = left + (right - left) // 2
        if nums[mid] == target:
            return mid
        elif nums[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

def find_first_occurrence(nums: list[int], target: int) -> int:
    """Find leftmost occurrence of target. O(log n)."""
    left, right = 0, len(nums) - 1
    result = -1
    while left <= right:
        mid = left + (right - left) // 2
        if nums[mid] == target:
            result = mid
            right = mid - 1  # Keep searching left
        elif nums[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return result


# --- BFS / DFS ---

def bfs_shortest_path(graph: dict[str, list[str]],
                       start: str, end: str) -> list[str]:
    """Find shortest path in unweighted graph. O(V + E)."""
    if start == end:
        return [start]
    queue = deque([(start, [start])])
    visited = {start}
    while queue:
        node, path = queue.popleft()
        for neighbor in graph.get(node, []):
            if neighbor == end:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return []

def dfs_all_paths(graph: dict, start: str, end: str) -> list[list[str]]:
    """Find all paths from start to end."""
    results = []
    def dfs(node: str, path: list[str]):
        if node == end:
            results.append(path[:])
            return
        for neighbor in graph.get(node, []):
            if neighbor not in path:
                path.append(neighbor)
                dfs(neighbor, path)
                path.pop()
    dfs(start, [start])
    return results


# --- Dynamic Programming ---

def longest_common_subsequence(text1: str, text2: str) -> int:
    """LCS length. O(m*n) time and space."""
    m, n = len(text1), len(text2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if text1[i - 1] == text2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]

def coin_change(coins: list[int], amount: int) -> int:
    """Minimum coins to make amount. O(amount * len(coins))."""
    dp = [float("inf")] * (amount + 1)
    dp[0] = 0
    for i in range(1, amount + 1):
        for coin in coins:
            if coin <= i:
                dp[i] = min(dp[i], dp[i - coin] + 1)
    return dp[amount] if dp[amount] != float("inf") else -1

def max_profit(prices: list[int]) -> int:
    """Best time to buy and sell stock (one transaction). O(n)."""
    min_price = float("inf")
    max_profit = 0
    for price in prices:
        min_price = min(min_price, price)
        max_profit = max(max_profit, price - min_price)
    return max_profit
```

Pattern recognition:
- **Two pointers** — sorted arrays, palindromes, partition
- **Sliding window** — subarray/substring optimization
- **Binary search** — sorted data, search space reduction
- **BFS** — shortest path, level-order traversal
- **DFS** — all paths, tree traversal, backtracking
- **DP** — overlapping subproblems, optimal substructure'''
    ),
    (
        "algorithms/data-structures",
        "Show practical data structure implementations: LRU cache, Trie, Union-Find, heap, and interval tree in Python.",
        '''Practical data structure implementations:

```python
from collections import OrderedDict
from typing import Optional, Any
import heapq

# --- LRU Cache ---

class LRUCache:
    """Least Recently Used cache with O(1) operations."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: str, value: Any):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)  # Remove oldest

    def __len__(self):
        return len(self.cache)


# --- Trie (prefix tree) ---

class TrieNode:
    __slots__ = ["children", "is_end", "value"]
    def __init__(self):
        self.children: dict[str, TrieNode] = {}
        self.is_end = False
        self.value = None

class Trie:
    """Prefix tree for efficient string operations."""

    def __init__(self):
        self.root = TrieNode()

    def insert(self, word: str, value: Any = None):
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

    def starts_with(self, prefix: str) -> bool:
        return self._find_node(prefix) is not None

    def autocomplete(self, prefix: str, limit: int = 10) -> list[str]:
        """Find all words with given prefix."""
        node = self._find_node(prefix)
        if not node:
            return []

        results = []
        self._collect(node, prefix, results, limit)
        return results

    def _find_node(self, prefix: str) -> Optional[TrieNode]:
        node = self.root
        for char in prefix:
            if char not in node.children:
                return None
            node = node.children[char]
        return node

    def _collect(self, node: TrieNode, prefix: str,
                 results: list, limit: int):
        if len(results) >= limit:
            return
        if node.is_end:
            results.append(prefix)
        for char, child in sorted(node.children.items()):
            self._collect(child, prefix + char, results, limit)


# --- Union-Find (Disjoint Set) ---

class UnionFind:
    """Efficient connected component tracking. Near O(1) operations."""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n
        self.components = n

    def find(self, x: int) -> int:
        """Find root with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        """Union by rank. Returns True if merged."""
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x == root_y:
            return False
        if self.rank[root_x] < self.rank[root_y]:
            root_x, root_y = root_y, root_x
        self.parent[root_y] = root_x
        if self.rank[root_x] == self.rank[root_y]:
            self.rank[root_x] += 1
        self.components -= 1
        return True

    def connected(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)


# --- Priority Queue wrapper ---

class PriorityQueue:
    """Min-heap priority queue with update support."""

    def __init__(self):
        self._heap = []
        self._counter = 0  # Tiebreaker for equal priorities
        self._entry_finder = {}
        self._REMOVED = object()

    def push(self, item: str, priority: float):
        if item in self._entry_finder:
            self._remove(item)
        entry = [priority, self._counter, item]
        self._counter += 1
        self._entry_finder[item] = entry
        heapq.heappush(self._heap, entry)

    def pop(self) -> tuple[str, float]:
        while self._heap:
            priority, _, item = heapq.heappop(self._heap)
            if item is not self._REMOVED:
                del self._entry_finder[item]
                return item, priority
        raise KeyError("Empty queue")

    def _remove(self, item: str):
        entry = self._entry_finder.pop(item)
        entry[2] = self._REMOVED

    def __len__(self):
        return len(self._entry_finder)

    def __bool__(self):
        return bool(self._entry_finder)


# --- Dijkstra's shortest path using PriorityQueue ---

def dijkstra(graph: dict[str, list[tuple[str, float]]],
             start: str) -> dict[str, float]:
    """Shortest paths from start to all nodes. O((V+E) log V)."""
    distances = {start: 0}
    pq = PriorityQueue()
    pq.push(start, 0)

    while pq:
        node, dist = pq.pop()
        if dist > distances.get(node, float("inf")):
            continue

        for neighbor, weight in graph.get(node, []):
            new_dist = dist + weight
            if new_dist < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_dist
                pq.push(neighbor, new_dist)

    return distances
```

When to use:
- **LRU Cache** — bounded memoization, database query caching
- **Trie** — autocomplete, spell checking, IP routing
- **Union-Find** — network connectivity, clustering, Kruskal's MST
- **Priority Queue** — task scheduling, Dijkstra's, event simulation
- **Heap** — top-K elements, merge sorted lists, median finding'''
    ),
]
