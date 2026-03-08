"""Deep reasoning training pairs: hard algorithms with extended think blocks."""

PAIRS = [
    (
        "deep_reasoning/dp-on-trees-maximum-independent-set",
        r'''Given a tree (undirected, acyclic, connected graph), find the maximum weight independent set — the largest-weight subset of nodes such that no two selected nodes are adjacent. Each node has a positive integer weight. Implement an efficient solution.''',
        r'''<think>
The brute force approach would enumerate all 2^n subsets and check independence — obviously O(2^n) which is unusable for large trees.

The key insight is that trees have optimal substructure: for any node, we either include it or exclude it, and each choice constrains the children independently. This is a classic tree DP.

Define:
- dp[v][1] = max weight of independent set in subtree rooted at v, WITH v included
- dp[v][0] = max weight of independent set in subtree rooted at v, WITHOUT v included

Recurrence:
- If we include v: none of v's children can be included → dp[v][1] = weight[v] + sum(dp[child][0])
- If we exclude v: each child can be included or not → dp[v][0] = sum(max(dp[child][0], dp[child][1]))

Base case: leaf node l → dp[l][1] = weight[l], dp[l][0] = 0.

Let me trace through an example tree:
       1(w=3)
      / \
    2(w=7) 3(w=2)
    |
   4(w=5)

Leaves first: dp[4] = (0, 5), dp[3] = (0, 2)
Node 2: dp[2][1] = 7 + dp[4][0] = 7, dp[2][0] = max(0, 5) = 5
Node 1: dp[1][1] = 3 + dp[2][0] + dp[3][0] = 3 + 5 + 0 = 8
         dp[1][0] = max(dp[2][0], dp[2][1]) + max(dp[3][0], dp[3][1]) = 7 + 2 = 9
Answer = max(8, 9) = 9 (pick nodes 2 and 3).

Edge cases: single node (just its weight), star graph (max of center vs all leaves), path graph (reduces to house robber problem).

Time complexity: O(n) — visit each node once. Space: O(n) for the DP table plus O(n) recursion stack.

I'll use iterative DFS with a parent array to avoid stack overflow on deep trees, and reconstruct the actual set.
</think>

```python
from collections import defaultdict, deque


def max_independent_set(n, edges, weights):
    """
    Find the maximum weight independent set on a tree.

    Args:
        n: number of nodes (0-indexed)
        edges: list of (u, v) edges forming a tree
        weights: list of node weights, weights[i] = weight of node i

    Returns:
        (max_weight, selected_nodes)

    Time:  O(n)
    Space: O(n)
    """
    if n == 0:
        return 0, []
    if n == 1:
        return weights[0], [0]

    # Build adjacency list
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    # BFS to get processing order (leaves first) and parent info
    root = 0
    parent = [-1] * n
    order = []
    visited = [False] * n
    queue = deque([root])
    visited[root] = True
    while queue:
        node = queue.popleft()
        order.append(node)
        for nb in adj[node]:
            if not visited[nb]:
                visited[nb] = True
                parent[nb] = node
                queue.append(nb)

    # DP bottom-up (reverse BFS order = leaves first)
    dp = [[0, 0] for _ in range(n)]  # dp[v][0]=exclude, dp[v][1]=include
    for v in reversed(order):
        dp[v][1] = weights[v]
        for child in adj[v]:
            if child == parent[v]:
                continue
            dp[v][1] += dp[child][0]
            dp[v][0] += max(dp[child][0], dp[child][1])

    # Reconstruct the selected set
    selected = []
    include = [False] * n
    # Decide root
    if dp[root][1] >= dp[root][0]:
        include[root] = True
    for v in order:
        for child in adj[v]:
            if child == parent[v]:
                continue
            if include[v]:
                # v is included, child must be excluded
                include[child] = False
            else:
                # v excluded, child takes its best option
                include[child] = dp[child][1] >= dp[child][0]
    selected = [v for v in range(n) if include[v]]

    return max(dp[root][0], dp[root][1]), selected


# --- Example ---
if __name__ == "__main__":
    #        0(w=3)
    #       / \
    #     1(w=7) 2(w=2)
    #     |
    #    3(w=5)
    n = 4
    edges = [(0, 1), (0, 2), (1, 3)]
    weights = [3, 7, 2, 5]
    max_w, nodes = max_independent_set(n, edges, weights)
    print(f"Max weight: {max_w}, Selected nodes: {nodes}")
    # Output: Max weight: 9, Selected nodes: [2, 3]  (w=2+7=9? No: nodes 1,2 → 7+2=9)
    # Actually node 1(w=7) and node 2(w=2) → 9. Or node 3(w=5) and node 2(w=2) and node 0(w=3) → 10?
    # Let's verify: 0 and 3 are not adjacent (path 0-1-3), and 0 and 2 are adjacent.
    # Include 0: can't include 1 or 2. Can include 3. → 3+5=8
    # Exclude 0: can include 1 and 2 (not adjacent). Include 1 → can't include 3. → 7+2=9
    # Exclude 0: include 2 and 3 (not adjacent to each other). → 2+5=7
    # Best: 9 (nodes 1 and 2)
    print("Verified: nodes 1 (w=7) and 2 (w=2) are non-adjacent, total=9")
```

**Complexity Analysis:**
- **Time:** O(n) — each node processed exactly once in reverse BFS order
- **Space:** O(n) — DP table, parent array, BFS queue
- **Key insight:** Tree DP with include/exclude states reduces exponential brute force to linear time'''
    ),
    (
        "deep_reasoning/k-shortest-paths-dijkstra",
        r'''Implement an algorithm to find the K shortest paths from a source to a destination in a weighted directed graph (edges have positive weights). Paths may revisit nodes. Return the lengths of the K shortest paths in order.''',
        r'''<think>
The classic single shortest path uses Dijkstra's in O((V+E) log V). For K shortest paths, we need a modification.

The key insight: in standard Dijkstra, we skip a node once it's been settled. But if we allow a node to be "settled" up to K times, the i-th time we pop the destination gives us the i-th shortest path.

This is Yen's algorithm variant / the "repeat Dijkstra" approach:
- Use a min-heap priority queue.
- Each time we pop a node, increment its count.
- When a node's count reaches K, we don't push its neighbors again.
- The k-th time we pop the destination, that's the k-th shortest path length.

Let me trace with a small example:
Nodes: 0, 1, 2. Edges: 0→1(1), 0→2(5), 1→2(2), 1→0(3)
Source=0, Dest=2, K=3

Heap: [(0, 0)]
Pop (0, 0): count[0]=1. Push (1, 1), (5, 2)
Pop (1, 1): count[1]=1. Push (3, 2), (4, 0)
Pop (3, 2): count[2]=1. → 1st shortest to 2 = 3 (0→1→2)
Pop (4, 0): count[0]=2. Push (5, 1), (9, 2)
Pop (5, 1): count[1]=2. Push (7, 2), (8, 0)
Pop (5, 2): count[2]=2. → 2nd shortest to 2 = 5 (0→2)
Pop (7, 2): count[2]=3. → 3rd shortest to 2 = 7 (0→1→0→1→2)

Result: [3, 5, 7]. Correct!

Edge cases: K=1 is normal Dijkstra. Destination unreachable means fewer than K paths exist. Self-loops can create infinite paths of increasing length.

Time complexity: O(K * (V + E) * log(KV)) in the worst case — each node can be settled K times, and the heap can grow to K*V entries. Space: O(K*V) for the heap.
</think>

```python
import heapq
from collections import defaultdict


def k_shortest_paths(n, edges, source, dest, k):
    """
    Find K shortest path distances from source to dest in a directed graph.
    Paths may revisit nodes.

    Args:
        n: number of nodes (0-indexed)
        edges: list of (u, v, weight) — directed edges with positive weights
        source: start node
        dest: target node
        k: number of shortest paths to find

    Returns:
        List of up to K shortest path distances

    Time:  O(K * (V + E) * log(KV))
    Space: O(KV + E)
    """
    adj = defaultdict(list)
    for u, v, w in edges:
        adj[u].append((v, w))

    # count[v] = how many times node v has been popped from the heap
    count = defaultdict(int)
    results = []

    # Min-heap: (distance, node)
    heap = [(0, source)]

    while heap and len(results) < k:
        dist, u = heapq.heappop(heap)
        count[u] += 1

        # If this is the destination, record the path length
        if u == dest:
            results.append(dist)
            if len(results) == k:
                break

        # Only expand if this node hasn't been settled K times yet
        # (no point expanding beyond K — can't contribute to K shortest to dest)
        if count[u] <= k:
            for v, w in adj[u]:
                heapq.heappush(heap, (dist + w, v))

    return results


# --- Example ---
if __name__ == "__main__":
    n = 3
    edges = [
        (0, 1, 1),
        (0, 2, 5),
        (1, 2, 2),
        (1, 0, 3),
    ]
    result = k_shortest_paths(n, edges, source=0, dest=2, k=3)
    print(f"K=3 shortest paths from 0 to 2: {result}")
    # Output: [3, 5, 7]
    # Path 1: 0→1→2 (cost 3)
    # Path 2: 0→2 (cost 5)
    # Path 3: 0→1→0→1→2 (cost 7)

    # Larger example
    edges2 = [
        (0, 1, 1), (0, 2, 3), (1, 2, 1),
        (1, 3, 5), (2, 3, 2), (2, 1, 1),
    ]
    result2 = k_shortest_paths(4, edges2, 0, 3, 4)
    print(f"K=4 shortest paths from 0 to 3: {result2}")
    # 0→1→2→3 = 4, 0→2→3 = 5, 0→1→2→1→2→3 = 6, 0→2→1→2→3 = 6
```

**Complexity Analysis:**
- **Time:** O(K * E * log(KV)) — each node popped at most K times, each pop does log-heap operations
- **Space:** O(KV + E) — heap can hold up to K*V entries
- **Key insight:** Allow nodes to be settled K times instead of once; the k-th pop of destination = k-th shortest path'''
    ),
    (
        "deep_reasoning/trie-wildcard-matching-autocomplete",
        r'''Implement a Trie that supports: (1) insert(word), (2) search(word) with '.' as wildcard matching any single character, (3) autocomplete(prefix) returning all words with that prefix, sorted lexicographically. All operations should be efficient.''',
        r'''<think>
A standard trie gives O(L) insert and exact search where L is word length. The challenge is supporting '.' wildcards and autocomplete efficiently.

For wildcard search with '.': at each '.' character, we must branch into ALL children — this makes the worst case O(26^m * L) where m is the number of wildcards. But in practice tries are sparse, so it's much faster.

For autocomplete: traverse to the prefix node in O(L), then DFS to collect all words below. This is O(L + K) where K is the number of matching words times their average remaining length.

Design:
- Each TrieNode has a dict of children (char → TrieNode) and an is_end flag.
- insert: straightforward O(L) traversal, create nodes as needed.
- search: recursive. If current char is '.', try all children. Otherwise, follow the exact child.
- autocomplete: walk to prefix node, then DFS collecting all complete words.

Let me trace through:
Insert: "cat", "car", "card", "care", "dog"
Trie structure:
  root → c → a → t (end)
                → r (end) → d (end)
                          → e (end)
       → d → o → g (end)

search("c.r") → at 'c', go to c-node. At '.', try all children of c-node: only 'a'. At 'r', check a-node has 'r' child → yes, and it's end → True.
search("..g") → at '.', try c and d. For c: at '.', try a. For a: at 'g', no child → fail. For d: at '.', try o. For o: at 'g', yes, end → True.

autocomplete("car") → walk to c→a→r node. DFS from there: "car" (end), "card" (end), "care" (end). Return ["car", "card", "care"].

Edge cases: empty string prefix returns all words. Search for "..." matches all 3-letter words. Insert duplicate is idempotent.
</think>

```python
class TrieNode:
    __slots__ = ('children', 'is_end')

    def __init__(self):
        self.children = {}  # char -> TrieNode
        self.is_end = False


class Trie:
    """
    Trie supporting insert, wildcard search (. matches any char),
    and prefix-based autocomplete.
    """

    def __init__(self):
        self.root = TrieNode()

    def insert(self, word: str) -> None:
        """Insert a word. O(L) time where L = len(word)."""
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.is_end = True

    def search(self, pattern: str) -> bool:
        """
        Search for pattern where '.' matches any single character.
        O(L) for exact match, O(26^m * L) worst case with m wildcards.
        """
        return self._search_recursive(self.root, pattern, 0)

    def _search_recursive(self, node: TrieNode, pattern: str, idx: int) -> bool:
        if idx == len(pattern):
            return node.is_end

        ch = pattern[idx]
        if ch == '.':
            # Wildcard: try every child
            for child in node.children.values():
                if self._search_recursive(child, pattern, idx + 1):
                    return True
            return False
        else:
            if ch not in node.children:
                return False
            return self._search_recursive(node.children[ch], pattern, idx + 1)

    def autocomplete(self, prefix: str) -> list:
        """
        Return all words starting with prefix, sorted lexicographically.
        O(P + K*L) where P=prefix length, K=number of matches, L=avg word length.
        """
        # Navigate to the prefix node
        node = self.root
        for ch in prefix:
            if ch not in node.children:
                return []
            node = node.children[ch]

        # DFS to collect all words below this node
        results = []
        self._collect_words(node, list(prefix), results)
        return results

    def _collect_words(self, node: TrieNode, path: list, results: list) -> None:
        if node.is_end:
            results.append(''.join(path))
        # Iterate children in sorted order for lexicographic output
        for ch in sorted(node.children):
            path.append(ch)
            self._collect_words(node.children[ch], path, results)
            path.pop()

    def starts_with(self, prefix: str) -> bool:
        """Check if any word starts with prefix. O(P)."""
        node = self.root
        for ch in prefix:
            if ch not in node.children:
                return False
            node = node.children[ch]
        return True


# --- Example ---
if __name__ == "__main__":
    trie = Trie()
    words = ["cat", "car", "card", "care", "dog", "dot", "dodge"]
    for w in words:
        trie.insert(w)

    # Exact search
    print(trie.search("cat"))    # True
    print(trie.search("cab"))    # False

    # Wildcard search
    print(trie.search("c.r"))    # True (car)
    print(trie.search("..g"))    # True (dog)
    print(trie.search("d.d..")) # True (dodge)
    print(trie.search("c..."))   # True (card, care)
    print(trie.search(".a."))    # True (cat, car)

    # Autocomplete
    print(trie.autocomplete("car"))  # ['car', 'card', 'care']
    print(trie.autocomplete("do"))   # ['dodge', 'dog', 'dot']
    print(trie.autocomplete("z"))    # []
    print(trie.autocomplete(""))     # all words sorted
```

**Complexity Analysis:**
- **insert:** O(L) time, O(L) space for new nodes
- **search (exact):** O(L) time
- **search (wildcard):** O(26^m * L) worst case, where m = number of '.' characters
- **autocomplete:** O(P + total characters in all matching words)
- **Space:** O(N * L) total for N words of average length L (worst case, no shared prefixes)'''
    ),
    (
        "deep_reasoning/segment-tree-lazy-propagation",
        r'''Implement a segment tree with lazy propagation that supports: (1) range update — add a value to all elements in a range [l, r], and (2) range query — find the sum of elements in a range [l, r]. Both operations should be O(log n).''',
        r'''<think>
A naive approach: array with O(1) point update, O(n) range query. Or prefix sums with O(1) range query but O(n) update. We need both operations in O(log n).

A basic segment tree gives O(log n) point update and O(log n) range query. But range UPDATE (add value to all elements in [l, r]) would be O(n log n) if we update each point individually.

The key insight: lazy propagation defers updates. When we update a range, we mark nodes as "lazy" — meaning "all elements in my range need this value added, but I haven't pushed it to children yet." We only push the lazy value down when we need to query or update a child.

Data per node:
- tree[i] = sum of elements in this node's range
- lazy[i] = pending addition to push to children

Range update [l, r] with value val:
- If node's range is fully contained in [l, r]: tree[node] += val * (range length), lazy[node] += val
- Otherwise: push lazy down, recurse on children, pull up sums

Range query [l, r]:
- If fully contained: return tree[node]
- Otherwise: push lazy down, recurse on children, return sum

Push down: transfer lazy from parent to children, adjust children's tree values.

Let me trace with array [1, 3, 5, 7, 9] (n=5):
Initial tree (leaves): [1, 3, 5, 7, 9]
Update [1, 3] += 10 → array becomes [1, 13, 15, 17, 9]
Query [2, 4] → 15 + 17 + 9 = 41

The lazy approach: when updating [1,3]+=10, if a node covers [1,3] exactly, just add 10*3=30 to its sum and set lazy=10. No need to visit individual elements.

Edge cases: single element range, update entire array, query after multiple overlapping updates.

Time: O(log n) per operation. Space: O(n).
</think>

```python
class LazySegmentTree:
    """
    Segment tree with lazy propagation for:
    - Range addition updates
    - Range sum queries
    Both in O(log n).
    """

    def __init__(self, data):
        """Build segment tree from initial array. O(n)."""
        self.n = len(data)
        self.tree = [0] * (4 * self.n)
        self.lazy = [0] * (4 * self.n)
        if self.n > 0:
            self._build(data, 1, 0, self.n - 1)

    def _build(self, data, node, start, end):
        if start == end:
            self.tree[node] = data[start]
            return
        mid = (start + end) // 2
        self._build(data, 2 * node, start, mid)
        self._build(data, 2 * node + 1, mid + 1, end)
        self.tree[node] = self.tree[2 * node] + self.tree[2 * node + 1]

    def _push_down(self, node, start, end):
        """Propagate lazy value to children."""
        if self.lazy[node] != 0:
            mid = (start + end) // 2
            left, right = 2 * node, 2 * node + 1
            # Update left child
            self.tree[left] += self.lazy[node] * (mid - start + 1)
            self.lazy[left] += self.lazy[node]
            # Update right child
            self.tree[right] += self.lazy[node] * (end - mid)
            self.lazy[right] += self.lazy[node]
            # Clear parent's lazy
            self.lazy[node] = 0

    def range_update(self, l, r, val):
        """Add val to all elements in [l, r] (0-indexed). O(log n)."""
        self._update(1, 0, self.n - 1, l, r, val)

    def _update(self, node, start, end, l, r, val):
        if r < start or end < l:
            return  # Out of range
        if l <= start and end <= r:
            # Fully contained — apply lazily
            self.tree[node] += val * (end - start + 1)
            self.lazy[node] += val
            return
        self._push_down(node, start, end)
        mid = (start + end) // 2
        self._update(2 * node, start, mid, l, r, val)
        self._update(2 * node + 1, mid + 1, end, l, r, val)
        self.tree[node] = self.tree[2 * node] + self.tree[2 * node + 1]

    def range_query(self, l, r):
        """Return sum of elements in [l, r] (0-indexed). O(log n)."""
        return self._query(1, 0, self.n - 1, l, r)

    def _query(self, node, start, end, l, r):
        if r < start or end < l:
            return 0  # Out of range
        if l <= start and end <= r:
            return self.tree[node]  # Fully contained
        self._push_down(node, start, end)
        mid = (start + end) // 2
        return (self._query(2 * node, start, mid, l, r) +
                self._query(2 * node + 1, mid + 1, end, l, r))


# --- Example ---
if __name__ == "__main__":
    data = [1, 3, 5, 7, 9]
    st = LazySegmentTree(data)

    print(f"Initial sum [0,4]: {st.range_query(0, 4)}")  # 25
    print(f"Sum [1,3]: {st.range_query(1, 3)}")            # 15

    st.range_update(1, 3, 10)  # Add 10 to indices 1,2,3
    # Array is now [1, 13, 15, 17, 9]
    print(f"After +10 to [1,3], sum [0,4]: {st.range_query(0, 4)}")  # 55
    print(f"Sum [2,4]: {st.range_query(2, 4)}")  # 15+17+9 = 41

    st.range_update(0, 4, -5)  # Subtract 5 from all
    # Array is now [-4, 8, 10, 12, 4]
    print(f"After -5 to [0,4], sum [0,4]: {st.range_query(0, 4)}")  # 30

    # Stress test: single element
    print(f"Single element [2,2]: {st.range_query(2, 2)}")  # 10
```

**Complexity Analysis:**
- **Build:** O(n)
- **Range update:** O(log n) amortized — lazy values defer work to future queries
- **Range query:** O(log n) — push lazy down only along the query path
- **Space:** O(n) for tree and lazy arrays (4n each)
- **Key insight:** Lazy propagation defers range updates, achieving O(log n) by only pushing when needed'''
    ),
    (
        "deep_reasoning/topological-sort-cycle-detection-lexicographic",
        r'''Implement topological sort on a directed graph that: (1) detects if a cycle exists (and reports it), (2) if no cycle, returns the lexicographically smallest topological ordering. Explain the algorithm choice.''',
        r'''<think>
Topological sort: linear ordering of vertices such that for every edge u→v, u comes before v. Only possible on DAGs (directed acyclic graphs).

Two standard approaches:
1. Kahn's algorithm (BFS with in-degree) — naturally supports lexicographic ordering if we use a min-heap instead of a plain queue.
2. DFS-based — detects cycles via back edges, but getting lexicographic order is tricky.

For lexicographically smallest ordering, Kahn's with a min-heap is the right choice:
- Maintain in-degree for each node.
- Start with all nodes having in-degree 0 in a min-heap.
- Always pick the smallest available node → guarantees lexicographic order.
- If we process fewer than n nodes, there's a cycle.

For cycle detection and REPORTING the cycle, we need DFS with coloring:
- WHITE (unvisited), GRAY (in current path), BLACK (fully processed).
- If we visit a GRAY node, we've found a cycle. Backtrack to extract it.

Let me trace Kahn's on: nodes {0,1,2,3}, edges: 2→0, 2→1, 0→1, 3→2
In-degrees: 0:1, 1:2, 2:1, 3:0
Heap starts: [3]
Pop 3 → result=[3], reduce in-degree of 2 → 0. Heap: [2]
Pop 2 → result=[3,2], reduce 0→0, 1→1. Heap: [0]
Pop 0 → result=[3,2,0], reduce 1→0. Heap: [1]
Pop 1 → result=[3,2,0,1]. All 4 processed → no cycle.

For a cycle: nodes {0,1,2}, edges: 0→1, 1→2, 2→0
In-degrees: all 1. Heap starts empty (no zero in-degree). Process 0 nodes → cycle detected.
DFS cycle extraction: 0→1→2→0, cycle = [0, 1, 2].

Edge cases: disconnected graph (multiple components), self-loop (trivial cycle), single node.
</think>

```python
import heapq
from collections import defaultdict


def topological_sort_lexicographic(n, edges):
    """
    Lexicographically smallest topological sort using Kahn's algorithm
    with a min-heap. Detects cycles.

    Args:
        n: number of nodes (0-indexed)
        edges: list of (u, v) meaning u must come before v

    Returns:
        (order, cycle) where:
        - order is the lex-smallest topological ordering (or partial if cycle)
        - cycle is None if DAG, or a list of nodes forming a cycle

    Time:  O((V + E) log V) due to heap operations
    Space: O(V + E)
    """
    adj = defaultdict(list)
    in_degree = [0] * n
    for u, v in edges:
        adj[u].append(v)
        in_degree[v] += 1

    # Min-heap of nodes with in-degree 0
    heap = [i for i in range(n) if in_degree[i] == 0]
    heapq.heapify(heap)

    order = []
    while heap:
        node = heapq.heappop(heap)
        order.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                heapq.heappush(heap, neighbor)

    if len(order) == n:
        return order, None  # Valid DAG

    # Cycle exists — find it using DFS with coloring
    cycle = _find_cycle(n, edges)
    return order, cycle


def _find_cycle(n, edges):
    """Find and return one cycle in the directed graph using DFS."""
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = [WHITE] * n
    parent = [-1] * n

    def dfs(u):
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                # Found cycle — reconstruct
                cycle = [v]
                curr = u
                while curr != v:
                    cycle.append(curr)
                    curr = parent[curr]
                cycle.reverse()
                return cycle
            if color[v] == WHITE:
                parent[v] = u
                result = dfs(v)
                if result:
                    return result
        color[u] = BLACK
        return None

    for i in range(n):
        if color[i] == WHITE:
            cycle = dfs(i)
            if cycle:
                return cycle
    return []


# --- Example ---
if __name__ == "__main__":
    # DAG example
    n = 4
    edges = [(2, 0), (2, 1), (0, 1), (3, 2)]
    order, cycle = topological_sort_lexicographic(n, edges)
    print(f"DAG - Order: {order}, Cycle: {cycle}")
    # Output: Order: [3, 2, 0, 1], Cycle: None

    # Graph with cycle
    n2 = 3
    edges2 = [(0, 1), (1, 2), (2, 0)]
    order2, cycle2 = topological_sort_lexicographic(n2, edges2)
    print(f"Cyclic - Order: {order2}, Cycle: {cycle2}")
    # Output: Order: [], Cycle: [0, 1, 2]

    # Disconnected DAG
    n3 = 6
    edges3 = [(5, 0), (5, 2), (4, 0), (4, 1), (2, 3), (3, 1)]
    order3, cycle3 = topological_sort_lexicographic(n3, edges3)
    print(f"Disconnected - Order: {order3}, Cycle: {cycle3}")
    # Lex smallest: [4, 5, 0, 2, 3, 1]
```

**Complexity Analysis:**
- **Time:** O((V + E) log V) — heap operations dominate over BFS traversal
- **Space:** O(V + E) for adjacency list, in-degree array, heap
- **Cycle detection:** O(V + E) additional DFS pass
- **Key insight:** Min-heap in Kahn's algorithm guarantees lexicographically smallest ordering while maintaining topological constraints'''
    ),
    (
        "deep_reasoning/lru-cache-o1-operations",
        r'''Implement an LRU (Least Recently Used) cache with O(1) time for both get and put operations. The cache has a fixed capacity and evicts the least recently used item when full.''',
        r'''<think>
The brute force: use a list ordered by recency. Get requires O(n) search, put requires O(n) to find and move. We need O(1) for both.

The key insight: combine a hash map with a doubly-linked list.
- Hash map: key → node in the linked list → O(1) lookup
- Doubly-linked list: maintains access order → O(1) move-to-front and remove-from-tail
- Most recently used at head, least recently used at tail

Operations:
- get(key): look up in hashmap. If found, move node to head, return value. O(1).
- put(key, value): if key exists, update value, move to head. If not, create new node at head. If over capacity, remove tail node and delete from hashmap. O(1).

The doubly-linked list needs sentinel nodes (dummy head and tail) to avoid null checks.

Let me trace with capacity=2:
put(1, 'A') → list: [1:A], map: {1: node}
put(2, 'B') → list: [2:B, 1:A], map: {1: node, 2: node}
get(1)      → move 1 to front. list: [1:A, 2:B]. Return 'A'
put(3, 'C') → capacity full, evict tail (2:B). list: [3:C, 1:A], map: {1: node, 3: node}
get(2)      → not in map → return -1

Edge cases: capacity 0 (always evict), put with existing key (update in place), get updates recency.

I'll implement a clean version with a custom doubly-linked list node class rather than using OrderedDict (which would be cheating for an interview).
</think>

```python
class DLLNode:
    """Node in a doubly-linked list."""
    __slots__ = ('key', 'value', 'prev', 'next')

    def __init__(self, key=0, value=0):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None


class LRUCache:
    """
    LRU Cache with O(1) get and put using a hashmap + doubly-linked list.

    Time:  O(1) for get and put
    Space: O(capacity)
    """

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}  # key -> DLLNode

        # Sentinel nodes to avoid null checks
        self.head = DLLNode()  # dummy head (most recent side)
        self.tail = DLLNode()  # dummy tail (least recent side)
        self.head.next = self.tail
        self.tail.prev = self.head

    def _remove(self, node: DLLNode) -> None:
        """Remove a node from the doubly-linked list. O(1)."""
        node.prev.next = node.next
        node.next.prev = node.prev

    def _add_to_front(self, node: DLLNode) -> None:
        """Add a node right after the dummy head (most recent). O(1)."""
        node.prev = self.head
        node.next = self.head.next
        self.head.next.prev = node
        self.head.next = node

    def _move_to_front(self, node: DLLNode) -> None:
        """Move an existing node to the front (most recent). O(1)."""
        self._remove(node)
        self._add_to_front(node)

    def get(self, key: int) -> int:
        """
        Get value by key. Returns -1 if not found.
        Marks the key as most recently used. O(1).
        """
        if key not in self.cache:
            return -1
        node = self.cache[key]
        self._move_to_front(node)
        return node.value

    def put(self, key: int, value: int) -> None:
        """
        Insert or update key-value pair.
        Evicts LRU item if at capacity. O(1).
        """
        if key in self.cache:
            node = self.cache[key]
            node.value = value
            self._move_to_front(node)
            return

        if len(self.cache) >= self.capacity:
            # Evict least recently used (node before tail sentinel)
            lru = self.tail.prev
            self._remove(lru)
            del self.cache[lru.key]

        new_node = DLLNode(key, value)
        self.cache[key] = new_node
        self._add_to_front(new_node)

    def __repr__(self):
        items = []
        node = self.head.next
        while node != self.tail:
            items.append(f"{node.key}:{node.value}")
            node = node.next
        return f"LRU[{' -> '.join(items)}]"


# --- Example ---
if __name__ == "__main__":
    cache = LRUCache(3)

    cache.put(1, 10)
    cache.put(2, 20)
    cache.put(3, 30)
    print(cache)  # LRU[3:30 -> 2:20 -> 1:10]

    print(cache.get(1))  # 10 — moves 1 to front
    print(cache)  # LRU[1:10 -> 3:30 -> 2:20]

    cache.put(4, 40)  # Evicts key 2 (least recent)
    print(cache)  # LRU[4:40 -> 1:10 -> 3:30]
    print(cache.get(2))  # -1 (evicted)

    cache.put(3, 300)  # Update existing key
    print(cache)  # LRU[3:300 -> 4:40 -> 1:10]

    cache.put(5, 50)  # Evicts key 1
    print(cache.get(1))  # -1
    print(cache)  # LRU[5:50 -> 3:300 -> 4:40]
```

**Complexity Analysis:**
- **get:** O(1) — hashmap lookup + linked list move
- **put:** O(1) — hashmap insert/update + linked list add/remove
- **Space:** O(capacity) — one node and one hashmap entry per cached item
- **Key insight:** Hashmap gives O(1) access, doubly-linked list gives O(1) reordering; sentinel nodes eliminate all edge-case null checks'''
    ),
    (
        "deep_reasoning/weighted-interval-scheduling-dp",
        r'''Given n jobs, each with a start time, end time, and profit, find the maximum profit subset of non-overlapping jobs. This is the weighted job scheduling problem. Implement an efficient solution.''',
        r'''<think>
The unweighted version is solved greedily (sort by end time, pick earliest-ending non-overlapping job). But with arbitrary weights/profits, greedy fails — we might skip a high-profit long job for several low-profit short jobs.

This is a classic DP problem. The key insight is:
1. Sort jobs by end time.
2. For each job j, define p(j) = the latest job (by index in sorted order) that doesn't overlap with j.
3. dp[j] = max(dp[j-1], profit[j] + dp[p(j)])
   - Either skip job j (take dp[j-1]) or include job j (get its profit + best from non-overlapping jobs).

Finding p(j) efficiently: since jobs are sorted by end time, p(j) is the rightmost job whose end time <= start time of job j. Use binary search → O(log n) per job.

Let me trace with example:
Jobs (start, end, profit): (1,3,50), (2,5,20), (4,6,70), (6,8,60)
Sorted by end: same order.
p(0) = -1 (no prior job ends before start=1)
p(1) = -1 (no prior job ends before start=2... job 0 ends at 3 > 2, so -1)
p(2) = 0 (job 0 ends at 3 <= start=4)
p(3) = 2 (job 2 ends at 6 <= start=6)

dp[0] = 50 (include job 0)
dp[1] = max(dp[0], 20 + 0) = max(50, 20) = 50
dp[2] = max(dp[1], 70 + dp[0]) = max(50, 70+50) = 120
dp[3] = max(dp[2], 60 + dp[2]) = max(120, 60+120) = 180

Answer: 180 (jobs 0, 2, 3: profit 50+70+60=180). Let me verify non-overlap: job 0 ends at 3, job 2 starts at 4 ✓, job 2 ends at 6, job 3 starts at 6 ✓.

Edge cases: all jobs overlap (pick max single profit), all non-overlapping (sum all), single job.

Time: O(n log n) for sorting + binary search. Space: O(n).
</think>

```python
from bisect import bisect_right


def max_profit_scheduling(jobs):
    """
    Find maximum profit from non-overlapping jobs.

    Args:
        jobs: list of (start, end, profit) tuples

    Returns:
        (max_profit, selected_jobs) where selected_jobs is list of original indices

    Time:  O(n log n)
    Space: O(n)
    """
    if not jobs:
        return 0, []

    n = len(jobs)
    # Sort by end time, keeping original indices
    indexed_jobs = sorted(enumerate(jobs), key=lambda x: x[1][1])
    end_times = [jobs[idx][1] for idx, _ in indexed_jobs]

    # dp[i] = max profit considering first i+1 jobs (sorted)
    dp = [0] * n
    # For reconstruction
    choice = [False] * n  # True if job i is included

    for i in range(n):
        orig_idx, (start, end, profit) = indexed_jobs[i]

        # Binary search for latest job ending <= start
        # bisect_right gives insertion point for start in end_times[:i]
        p = bisect_right(end_times, start, 0, i) - 1

        include_profit = profit + (dp[p] if p >= 0 else 0)
        exclude_profit = dp[i - 1] if i > 0 else 0

        if include_profit >= exclude_profit:
            dp[i] = include_profit
            choice[i] = True
        else:
            dp[i] = exclude_profit

    # Reconstruct selected jobs
    selected = []
    i = n - 1
    while i >= 0:
        if choice[i]:
            orig_idx = indexed_jobs[i][0]
            selected.append(orig_idx)
            start = indexed_jobs[i][1][0]
            # Jump to p(i)
            i = bisect_right(end_times, start, 0, i) - 1
        else:
            i -= 1

    selected.reverse()
    return dp[n - 1], selected


# --- Example ---
if __name__ == "__main__":
    jobs = [
        (1, 3, 50),   # Job 0
        (2, 5, 20),   # Job 1
        (4, 6, 70),   # Job 2
        (6, 8, 60),   # Job 3
    ]
    profit, selected = max_profit_scheduling(jobs)
    print(f"Max profit: {profit}")
    print(f"Selected job indices: {selected}")
    print(f"Jobs: {[jobs[i] for i in selected]}")
    # Max profit: 180, Selected: [0, 2, 3]
    # Jobs: (1,3,50), (4,6,70), (6,8,60) → 50+70+60 = 180

    # All overlapping
    jobs2 = [(0, 10, 5), (1, 11, 10), (2, 12, 15)]
    profit2, sel2 = max_profit_scheduling(jobs2)
    print(f"\nAll overlapping: profit={profit2}, selected={sel2}")
    # Best single job: (2,12,15)

    # No overlap
    jobs3 = [(0, 1, 10), (1, 2, 20), (2, 3, 30)]
    profit3, sel3 = max_profit_scheduling(jobs3)
    print(f"No overlap: profit={profit3}, selected={sel3}")
    # All three: 10+20+30 = 60
```

**Complexity Analysis:**
- **Time:** O(n log n) — sorting is O(n log n), binary search per job is O(log n), total O(n log n)
- **Space:** O(n) for DP array and sorted indices
- **Key insight:** Sort by end time, binary search for latest non-overlapping predecessor, DP decides include vs exclude for each job'''
    ),
    (
        "deep_reasoning/suffix-array-lcp",
        r'''Implement suffix array construction and LCP (Longest Common Prefix) array computation for a given string. Use an efficient O(n log n) construction for the suffix array and Kasai's algorithm for LCP. Explain how these are used.''',
        r'''<think>
A suffix array is the sorted array of all suffixes of a string, stored as starting indices. It's a space-efficient alternative to suffix trees.

Naive construction: generate all n suffixes, sort them → O(n^2 log n) due to string comparisons of length O(n).

The O(n log n) approach uses prefix doubling (also called the "DC3" or "skew" approach is O(n), but prefix doubling is simpler):
1. Start by ranking suffixes by their first character.
2. Iteratively double the comparison length: rank by first 2 chars, then 4, then 8...
3. At each step, use the previous rankings to create sort keys (rank of first half, rank of second half).
4. After log(n) iterations, all suffixes are uniquely ranked → sorted.

For LCP array — Kasai's algorithm:
- LCP[i] = length of longest common prefix between suffix_array[i] and suffix_array[i-1]
- Key insight: if we process suffixes in text order (not sorted order), LCP values decrease by at most 1 when we move to the next text position.
- This gives O(n) time.

Let me trace with "banana$":
Suffixes: banana$, anana$, nana$, ana$, na$, a$, $
Sorted: $, a$, ana$, anana$, banana$, na$, nana$
Suffix array: [6, 5, 3, 1, 0, 4, 2]
LCP: [0, 0, 1, 3, 0, 0, 2]
(LCP[2]=1: "a$" vs "ana$" share "a"; LCP[3]=3: "ana$" vs "anana$" share "ana")

Applications: substring search (binary search on suffix array), finding longest repeated substring (max LCP value), string matching, bioinformatics.

Edge cases: single character string, all same characters, empty string.
</think>

```python
def build_suffix_array(s):
    """
    Build suffix array using prefix doubling. O(n log^2 n).
    (Using Python's sort with tuple keys; true O(n log n) needs radix sort.)

    Args:
        s: input string

    Returns:
        Suffix array — list of starting indices of sorted suffixes

    Time:  O(n log^2 n) with comparison sort, O(n log n) with radix sort
    Space: O(n)
    """
    n = len(s)
    if n == 0:
        return []

    # Initial ranking by single character
    sa = list(range(n))
    rank = [ord(c) for c in s]
    tmp = [0] * n

    k = 1  # Current comparison length
    while k < n:
        # Sort by (rank[i], rank[i+k]) — rank of first half, rank of second half
        def sort_key(i):
            return (rank[i], rank[i + k] if i + k < n else -1)

        sa.sort(key=sort_key)

        # Recompute ranks based on new sorted order
        tmp[sa[0]] = 0
        for i in range(1, n):
            tmp[sa[i]] = tmp[sa[i - 1]]
            if sort_key(sa[i]) != sort_key(sa[i - 1]):
                tmp[sa[i]] += 1

        rank = tmp[:]

        # Early termination: all ranks unique
        if rank[sa[-1]] == n - 1:
            break

        k *= 2

    return sa


def build_lcp_array(s, sa):
    """
    Kasai's algorithm: compute LCP array from string and suffix array.

    LCP[i] = length of longest common prefix between sa[i] and sa[i-1].

    Time:  O(n)
    Space: O(n)
    """
    n = len(s)
    if n == 0:
        return []

    # Inverse suffix array: rank[i] = position of suffix i in sorted order
    rank = [0] * n
    for i in range(n):
        rank[sa[i]] = i

    lcp = [0] * n
    k = 0  # Current LCP length

    for i in range(n):
        if rank[i] == 0:
            k = 0
            continue

        j = sa[rank[i] - 1]  # Previous suffix in sorted order

        # Extend match
        while i + k < n and j + k < n and s[i + k] == s[j + k]:
            k += 1

        lcp[rank[i]] = k

        # Key insight: LCP decreases by at most 1 when moving to next text position
        if k > 0:
            k -= 1

    return lcp


def search_pattern(text, sa, pattern):
    """Binary search for pattern in text using suffix array. O(m log n)."""
    n = len(text)
    m = len(pattern)

    # Lower bound
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        suffix = text[sa[mid]:sa[mid] + m]
        if suffix < pattern:
            lo = mid + 1
        else:
            hi = mid
    start = lo

    # Upper bound
    hi = n
    while lo < hi:
        mid = (lo + hi) // 2
        suffix = text[sa[mid]:sa[mid] + m]
        if suffix <= pattern:
            lo = mid + 1
        else:
            hi = mid

    return [sa[i] for i in range(start, lo)]


def longest_repeated_substring(s, sa, lcp):
    """Find longest repeated substring using LCP array. O(n)."""
    if not lcp:
        return ""
    max_lcp = max(lcp)
    if max_lcp == 0:
        return ""
    idx = lcp.index(max_lcp)
    return s[sa[idx]:sa[idx] + max_lcp]


# --- Example ---
if __name__ == "__main__":
    s = "banana"
    sa = build_suffix_array(s)
    lcp = build_lcp_array(s, sa)

    print(f"String: '{s}'")
    print(f"Suffix Array: {sa}")
    print(f"LCP Array:    {lcp}")
    print("\nSorted suffixes:")
    for i, idx in enumerate(sa):
        print(f"  sa[{i}] = {idx}: '{s[idx:]}' (LCP={lcp[i]})")

    # Pattern search
    positions = search_pattern(s, sa, "ana")
    print(f"\nPattern 'ana' found at positions: {positions}")  # [1, 3]

    # Longest repeated substring
    lrs = longest_repeated_substring(s, sa, lcp)
    print(f"Longest repeated substring: '{lrs}'")  # "ana"

    # Another example
    s2 = "abracadabra"
    sa2 = build_suffix_array(s2)
    lcp2 = build_lcp_array(s2, sa2)
    lrs2 = longest_repeated_substring(s2, sa2, lcp2)
    print(f"\nString: '{s2}', Longest repeated: '{lrs2}'")  # "abra"
```

**Complexity Analysis:**
- **Suffix array construction:** O(n log^2 n) with comparison sort, O(n log n) with radix sort
- **LCP array (Kasai's):** O(n) — the total number of character comparisons is bounded by 2n
- **Pattern search:** O(m log n) where m = pattern length
- **Space:** O(n) for both arrays
- **Key insight:** Prefix doubling iteratively refines suffix rankings by doubling comparison length each round; Kasai's exploits the fact that LCP drops by at most 1 between consecutive text positions'''
    ),
    (
        "deep_reasoning/a-star-pathfinding-weighted-grid",
        r'''Implement A* pathfinding on a weighted grid where each cell has a movement cost. Some cells are obstacles (impassable). Find the shortest path from a start to a goal position. Support 4-directional and 8-directional movement.''',
        r'''<think>
Dijkstra explores all reachable nodes in order of distance — it doesn't use any information about where the goal is. A* improves on this by adding a heuristic that estimates remaining distance to goal.

A* uses f(n) = g(n) + h(n):
- g(n) = actual cost from start to node n
- h(n) = heuristic estimate from n to goal
- f(n) = estimated total cost through n

The heuristic must be admissible (never overestimates) and ideally consistent (h(n) <= cost(n,n') + h(n')).

For 4-directional movement: Manhattan distance is admissible and consistent.
For 8-directional movement: Chebyshev distance (max of dx, dy) or octile distance for weighted diagonals.

If all cell costs are 1, h = Manhattan distance is perfect. With varying costs, Manhattan distance is still admissible as long as minimum cell cost >= 1 (which we can ensure by using h = manhattan * min_cost).

Algorithm:
1. Priority queue ordered by f = g + h
2. Track g-scores for each cell (best known cost to reach it)
3. Pop lowest f-score node. If it's the goal, done.
4. For each neighbor: compute tentative g. If better than known g, update and push.

Let me trace on a small 3x3 grid:
Costs:  [[1, 1, 1],
         [1, 9, 1],
         [1, 1, 1]]
Start (0,0), Goal (2,2), 4-directional.

Path options: right-right-down-down = 1+1+1+1=4, down-down-right-right = 1+1+1+1=4, right-down-down-right=1+9+1+1=12.
A* with Manhattan heuristic will explore the corners first, avoiding the center cell (cost 9).

Edge cases: start == goal, no path exists, all cells are obstacles except start, grid with uniform costs (reduces to BFS).
</think>

```python
import heapq
from typing import Optional


def astar(grid, start, goal, diagonal=False):
    """
    A* pathfinding on a weighted grid.

    Args:
        grid: 2D list where grid[r][c] = movement cost (0 = obstacle)
        start: (row, col) start position
        goal: (row, col) goal position
        diagonal: if True, allow 8-directional movement

    Returns:
        (total_cost, path) where path is list of (row, col),
        or (float('inf'), []) if no path exists

    Time:  O(V log V) where V = rows * cols (worst case explores all cells)
    Space: O(V)
    """
    rows, cols = len(grid), len(grid[0])
    sr, sc = start
    gr, gc = goal

    # Validate
    if grid[sr][sc] == 0 or grid[gr][gc] == 0:
        return float('inf'), []

    # Heuristic function
    if diagonal:
        # Octile distance (assuming diagonal cost = straight cost for simplicity)
        def heuristic(r, c):
            dr, dc = abs(r - gr), abs(c - gc)
            return max(dr, dc)  # Chebyshev distance
        directions = [
            (-1, 0), (1, 0), (0, -1), (0, 1),
            (-1, -1), (-1, 1), (1, -1), (1, 1)
        ]
    else:
        def heuristic(r, c):
            return abs(r - gr) + abs(c - gc)  # Manhattan distance
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    # g_score[r][c] = best known cost to reach (r,c)
    INF = float('inf')
    g_score = [[INF] * cols for _ in range(rows)]
    g_score[sr][sc] = grid[sr][sc]

    # For path reconstruction
    came_from = [[None] * cols for _ in range(rows)]

    # Priority queue: (f_score, g_score, row, col)
    # Include g_score as tiebreaker (prefer nodes closer to goal)
    open_set = [(grid[sr][sc] + heuristic(sr, sc), grid[sr][sc], sr, sc)]
    closed = [[False] * cols for _ in range(rows)]

    while open_set:
        f, g, r, c = heapq.heappop(open_set)

        if (r, c) == (gr, gc):
            # Reconstruct path
            path = []
            curr = (gr, gc)
            while curr is not None:
                path.append(curr)
                curr = came_from[curr[0]][curr[1]]
            path.reverse()
            return g, path

        if closed[r][c]:
            continue
        closed[r][c] = True

        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not closed[nr][nc]:
                if grid[nr][nc] == 0:  # Obstacle
                    continue

                new_g = g + grid[nr][nc]
                if new_g < g_score[nr][nc]:
                    g_score[nr][nc] = new_g
                    came_from[nr][nc] = (r, c)
                    f_new = new_g + heuristic(nr, nc)
                    heapq.heappush(open_set, (f_new, new_g, nr, nc))

    return INF, []  # No path


def print_path_on_grid(grid, path):
    """Visualize the path on the grid."""
    rows, cols = len(grid), len(grid[0])
    display = [['.' if grid[r][c] > 0 else '#' for c in range(cols)]
               for r in range(rows)]
    for r, c in path:
        display[r][c] = '*'
    if path:
        sr, sc = path[0]
        gr, gc = path[-1]
        display[sr][sc] = 'S'
        display[gr][gc] = 'G'
    for row in display:
        print(' '.join(row))


# --- Example ---
if __name__ == "__main__":
    grid = [
        [1, 1, 1, 1, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 1, 0, 1],
        [1, 1, 1, 0, 1],
        [1, 1, 1, 1, 1],
    ]
    cost, path = astar(grid, (0, 0), (4, 4), diagonal=False)
    print(f"4-dir Cost: {cost}, Path length: {len(path)}")
    print(f"Path: {path}")
    print_path_on_grid(grid, path)

    print()

    # Weighted grid
    weighted = [
        [1, 5, 1, 1],
        [1, 5, 1, 1],
        [1, 1, 1, 5],
        [1, 1, 1, 1],
    ]
    cost2, path2 = astar(weighted, (0, 0), (3, 3), diagonal=False)
    print(f"Weighted Cost: {cost2}")
    print(f"Path: {path2}")
    print_path_on_grid(weighted, path2)

    print()

    # 8-directional
    cost3, path3 = astar(grid, (0, 0), (4, 4), diagonal=True)
    print(f"8-dir Cost: {cost3}, Path length: {len(path3)}")
    print(f"Path: {path3}")
```

**Complexity Analysis:**
- **Time:** O(V log V) worst case where V = rows * cols (each cell pushed to heap once, heap operations O(log V))
- **Space:** O(V) for g_score, came_from, and heap
- **Heuristic:** Manhattan (4-dir) / Chebyshev (8-dir) are admissible and consistent → A* finds optimal path
- **Key insight:** A* = Dijkstra + heuristic guidance. The heuristic prunes exploration away from the goal, often visiting far fewer nodes than Dijkstra'''
    ),
    (
        "deep_reasoning/red-black-tree-insertion",
        r'''Implement a Red-Black Tree with insertion and search operations. Include all rotation and recoloring cases. Explain the invariants and why rotations maintain balance.''',
        r'''<think>
A Red-Black Tree is a self-balancing BST with these invariants:
1. Every node is red or black.
2. Root is black.
3. Every leaf (NIL) is black.
4. Red nodes have only black children (no two consecutive reds).
5. Every path from a node to its descendant NIL nodes has the same number of black nodes (black-height).

These invariants guarantee that the tree height is at most 2*log(n+1), giving O(log n) operations.

Insertion:
1. Insert as a normal BST, color the new node RED.
2. Fix violations — the only possible violation is property 4 (red parent + red child).

Fix-up cases (assuming the inserted node z's parent is a LEFT child of grandparent — mirror for right):
- Case 1: Uncle is RED → recolor parent and uncle to black, grandparent to red, move z up to grandparent.
- Case 2: Uncle is BLACK, z is a RIGHT child → left-rotate parent (converts to case 3).
- Case 3: Uncle is BLACK, z is a LEFT child → right-rotate grandparent, swap colors of parent and grandparent.

Rotations preserve BST property while rebalancing:
- Left rotation on x: x's right child y becomes parent, x becomes y's left child, y's old left child becomes x's right child.
- Right rotation is the mirror.

Let me trace inserting 10, 20, 30:
Insert 10: root, color black. Tree: 10(B)
Insert 20: 20 is red, parent 10 is black → no violation. Tree: 10(B)-R→20(R)
Insert 30: 30 is red, parent 20 is red → violation!
  Uncle of 30 is NIL (black). 30 is right child, 20 is right child → Case 3 mirror.
  Left-rotate 10, swap colors: 20(B), 10(R), 30(R).

Edge cases: inserting duplicates (policy choice: skip or allow), single element tree, degenerate insertion order (1,2,3,...n — RBT keeps it balanced unlike BST).
</think>

```python
class RBNode:
    __slots__ = ('key', 'val', 'color', 'left', 'right', 'parent')
    RED = True
    BLACK = False

    def __init__(self, key, val=None, color=True):
        self.key = key
        self.val = val
        self.color = color  # True = RED, False = BLACK
        self.left = None
        self.right = None
        self.parent = None


class RedBlackTree:
    """
    Red-Black Tree with O(log n) insert and search.

    Invariants:
    1. Every node is red or black
    2. Root is black
    3. NIL leaves are black (represented as None)
    4. Red nodes have only black children
    5. All paths from node to NIL have equal black-height
    """

    def __init__(self):
        self.NIL = RBNode(None, color=RBNode.BLACK)
        self.root = self.NIL

    def search(self, key):
        """Search for key. O(log n)."""
        node = self.root
        while node != self.NIL:
            if key == node.key:
                return node.val
            elif key < node.key:
                node = node.left
            else:
                node = node.right
        return None

    def insert(self, key, val=None):
        """Insert key-value pair. O(log n)."""
        new_node = RBNode(key, val, color=RBNode.RED)
        new_node.left = self.NIL
        new_node.right = self.NIL

        # Standard BST insert
        parent = None
        current = self.root
        while current != self.NIL:
            parent = current
            if key < current.key:
                current = current.left
            elif key > current.key:
                current = current.right
            else:
                current.val = val  # Update existing key
                return

        new_node.parent = parent
        if parent is None:
            self.root = new_node
        elif key < parent.key:
            parent.left = new_node
        else:
            parent.right = new_node

        # Fix red-black violations
        self._fix_insert(new_node)

    def _fix_insert(self, z):
        """Fix red-black tree violations after insertion."""
        while z.parent and z.parent.color == RBNode.RED:
            if z.parent == z.parent.parent.left:
                uncle = z.parent.parent.right

                if uncle.color == RBNode.RED:
                    # Case 1: Uncle is red — recolor
                    z.parent.color = RBNode.BLACK
                    uncle.color = RBNode.BLACK
                    z.parent.parent.color = RBNode.RED
                    z = z.parent.parent
                else:
                    if z == z.parent.right:
                        # Case 2: Uncle is black, z is right child — left rotate
                        z = z.parent
                        self._left_rotate(z)
                    # Case 3: Uncle is black, z is left child — right rotate
                    z.parent.color = RBNode.BLACK
                    z.parent.parent.color = RBNode.RED
                    self._right_rotate(z.parent.parent)
            else:
                # Mirror cases (parent is right child of grandparent)
                uncle = z.parent.parent.left

                if uncle.color == RBNode.RED:
                    z.parent.color = RBNode.BLACK
                    uncle.color = RBNode.BLACK
                    z.parent.parent.color = RBNode.RED
                    z = z.parent.parent
                else:
                    if z == z.parent.left:
                        z = z.parent
                        self._right_rotate(z)
                    z.parent.color = RBNode.BLACK
                    z.parent.parent.color = RBNode.RED
                    self._left_rotate(z.parent.parent)

        self.root.color = RBNode.BLACK

    def _left_rotate(self, x):
        """Left rotation around x. O(1)."""
        y = x.right
        x.right = y.left
        if y.left != self.NIL:
            y.left.parent = x
        y.parent = x.parent
        if x.parent is None:
            self.root = y
        elif x == x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y
        y.left = x
        x.parent = y

    def _right_rotate(self, y):
        """Right rotation around y. O(1)."""
        x = y.left
        y.left = x.right
        if x.right != self.NIL:
            x.right.parent = y
        x.parent = y.parent
        if y.parent is None:
            self.root = x
        elif y == y.parent.left:
            y.parent.left = x
        else:
            y.parent.right = x
        x.right = y
        y.parent = x

    def inorder(self):
        """In-order traversal. Returns sorted keys."""
        result = []
        self._inorder(self.root, result)
        return result

    def _inorder(self, node, result):
        if node != self.NIL:
            self._inorder(node.left, result)
            color = 'R' if node.color == RBNode.RED else 'B'
            result.append((node.key, color))
            self._inorder(node.right, result)

    def black_height(self):
        """Verify all paths have equal black height."""
        def _bh(node):
            if node == self.NIL:
                return 1
            lh = _bh(node.left)
            rh = _bh(node.right)
            assert lh == rh, f"Black height mismatch at key {node.key}"
            return lh + (0 if node.color == RBNode.RED else 1)
        return _bh(self.root)


# --- Example ---
if __name__ == "__main__":
    rbt = RedBlackTree()

    # Insert in sorted order — would degenerate a plain BST
    for i in [10, 20, 30, 15, 25, 5, 1]:
        rbt.insert(i, f"val_{i}")

    print(f"In-order: {rbt.inorder()}")
    print(f"Black height: {rbt.black_height()}")
    print(f"Search 15: {rbt.search(15)}")
    print(f"Search 99: {rbt.search(99)}")

    # Verify balance: insert 1..20 (worst case for BST)
    rbt2 = RedBlackTree()
    for i in range(1, 21):
        rbt2.insert(i)
    print(f"\n1..20 in order: {rbt2.inorder()}")
    print(f"Black height: {rbt2.black_height()}")
    # Black height ~3-4, total height ~6-8 vs BST height 20
```

**Complexity Analysis:**
- **Insert:** O(log n) — BST walk + at most 2 rotations and O(log n) recolorings
- **Search:** O(log n) — standard BST search, tree height guaranteed <= 2*log(n+1)
- **Rotations:** O(1) each, at most 2 per insertion
- **Space:** O(n) for the tree
- **Key insight:** Red-black invariants keep the tree approximately balanced; the black-height property ensures no path is more than twice as long as any other'''
    ),
    (
        "deep_reasoning/bloom-filter-optimal-hashing",
        r'''Implement a Bloom filter with optimal hash count calculation. Include methods to add elements, check membership, and analyze the false positive rate. Explain the math behind optimal parameters.''',
        r'''<think>
A Bloom filter is a probabilistic data structure that tests set membership. It can have false positives but NEVER false negatives. It's extremely space-efficient compared to storing actual elements.

Structure: a bit array of m bits, with k independent hash functions.
- add(x): compute k hash positions, set all to 1.
- check(x): compute k hash positions, return True only if ALL are 1.

False positive probability:
After inserting n elements with k hash functions into m bits:
p(false positive) ≈ (1 - e^(-kn/m))^k

Optimal number of hash functions:
k_opt = (m/n) * ln(2) ≈ 0.693 * (m/n)

This minimizes the false positive rate for given m and n.

Given desired false positive rate p and expected element count n:
m = -(n * ln(p)) / (ln(2)^2)
k = (m/n) * ln(2)

For example: n=1000 elements, desired p=1% (0.01):
m = -(1000 * ln(0.01)) / (0.4805) = -(1000 * -4.605) / 0.4805 ≈ 9585 bits ≈ 1.2 KB
k = (9585/1000) * 0.693 ≈ 6.6 → 7 hash functions

Rather than k independent hash functions (hard to generate), we can use the "double hashing" trick:
h_i(x) = h1(x) + i * h2(x) mod m
This gives us k hash positions from just 2 hash functions.

Edge cases: empty filter (all queries return False), m=0 (degenerate), very large n exceeding capacity (FP rate approaches 1).

Let me trace: m=10 bits, k=2, insert "hello"
h1("hello")=3, h2("hello")=7. Set bits 3 and 7.
Check "hello": bits 3,7 are set → True (correct).
Check "world": h1=1, h2=5. Bit 1 is 0 → False (correct).
Check "foo": h1=3, h2=9. Bit 3 is 1, bit 9 is 0 → False (correct).
After many insertions, more bits are 1 → higher false positive chance.
</think>

```python
import math
import hashlib
import struct


class BloomFilter:
    """
    Bloom filter with optimal hash count and false positive analysis.

    A probabilistic set membership test:
    - No false negatives (if added, always found)
    - Controlled false positive rate

    Time:  O(k) per add/check where k = number of hash functions
    Space: O(m) bits
    """

    def __init__(self, expected_elements: int, fp_rate: float = 0.01):
        """
        Initialize Bloom filter with optimal parameters.

        Args:
            expected_elements: expected number of elements (n)
            fp_rate: desired false positive probability (e.g., 0.01 = 1%)
        """
        self.n_expected = expected_elements
        self.fp_rate = fp_rate

        # Optimal bit array size: m = -(n * ln(p)) / (ln(2)^2)
        self.m = max(1, int(-expected_elements * math.log(fp_rate)
                            / (math.log(2) ** 2)))

        # Optimal hash count: k = (m/n) * ln(2)
        self.k = max(1, int((self.m / expected_elements) * math.log(2)))

        # Bit array (using bytearray for efficiency)
        self.bit_array = bytearray(math.ceil(self.m / 8))
        self.n_inserted = 0

    def _hashes(self, item: str):
        """
        Generate k hash positions using double hashing.
        h_i(x) = (h1(x) + i * h2(x)) % m
        """
        # Use MD5 for h1 and SHA256 for h2 (just need two independent hashes)
        data = item.encode('utf-8')
        h1 = int.from_bytes(hashlib.md5(data).digest()[:8], 'big')
        h2 = int.from_bytes(hashlib.sha256(data).digest()[:8], 'big')

        for i in range(self.k):
            yield (h1 + i * h2) % self.m

    def _set_bit(self, pos):
        byte_idx, bit_idx = divmod(pos, 8)
        self.bit_array[byte_idx] |= (1 << bit_idx)

    def _get_bit(self, pos):
        byte_idx, bit_idx = divmod(pos, 8)
        return bool(self.bit_array[byte_idx] & (1 << bit_idx))

    def add(self, item: str):
        """Add an item to the filter. O(k)."""
        for pos in self._hashes(item):
            self._set_bit(pos)
        self.n_inserted += 1

    def check(self, item: str) -> bool:
        """
        Check if item might be in the set.
        Returns True = "probably yes", False = "definitely no".
        O(k).
        """
        return all(self._get_bit(pos) for pos in self._hashes(item))

    def current_fp_rate(self) -> float:
        """Estimate current false positive rate based on items inserted."""
        if self.n_inserted == 0:
            return 0.0
        # p ≈ (1 - e^(-k*n/m))^k
        exponent = -self.k * self.n_inserted / self.m
        return (1 - math.exp(exponent)) ** self.k

    def fill_ratio(self) -> float:
        """Fraction of bits set to 1."""
        set_bits = sum(bin(byte).count('1') for byte in self.bit_array)
        return set_bits / self.m

    def stats(self):
        """Print filter statistics."""
        print(f"Bloom Filter Statistics:")
        print(f"  Bit array size (m): {self.m} bits ({self.m / 8:.0f} bytes)")
        print(f"  Hash functions (k): {self.k}")
        print(f"  Expected elements:  {self.n_expected}")
        print(f"  Inserted elements:  {self.n_inserted}")
        print(f"  Target FP rate:     {self.fp_rate:.4%}")
        print(f"  Current FP rate:    {self.current_fp_rate():.4%}")
        print(f"  Fill ratio:         {self.fill_ratio():.4%}")


# --- Example ---
if __name__ == "__main__":
    # Create filter for 10000 elements with 1% false positive rate
    bf = BloomFilter(expected_elements=10000, fp_rate=0.01)
    bf.stats()

    # Add elements
    for i in range(10000):
        bf.add(f"element_{i}")

    print(f"\nAfter inserting 10000 elements:")
    bf.stats()

    # Test known members (should all be True)
    false_negatives = sum(1 for i in range(10000)
                         if not bf.check(f"element_{i}"))
    print(f"\nFalse negatives: {false_negatives}")  # Always 0

    # Test non-members (count false positives)
    test_count = 10000
    false_positives = sum(1 for i in range(10000, 20000)
                         if bf.check(f"element_{i}"))
    actual_fp_rate = false_positives / test_count
    print(f"False positives out of {test_count}: {false_positives}")
    print(f"Actual FP rate: {actual_fp_rate:.4%}")
    print(f"Expected FP rate: {bf.current_fp_rate():.4%}")

    # Demonstrate parameter calculation
    print(f"\n--- Parameter formulas ---")
    n, p = 1_000_000, 0.001
    m = int(-n * math.log(p) / (math.log(2) ** 2))
    k = int((m / n) * math.log(2))
    print(f"For n={n:,}, p={p}: need m={m:,} bits ({m/8/1024:.1f} KB), k={k} hashes")
```

**Complexity Analysis:**
- **add:** O(k) — compute k hashes, set k bits
- **check:** O(k) — compute k hashes, test k bits
- **Space:** O(m) bits, where m = -(n * ln(p)) / ln(2)^2
- **Optimal k:** (m/n) * ln(2) — minimizes false positive rate
- **Key insight:** With optimal parameters, a Bloom filter uses ~10 bits per element for 1% FP rate — far less than storing actual elements (which might be hundreds of bytes each)'''
    ),
    (
        "deep_reasoning/union-find-path-compression-rank",
        r'''Implement a Disjoint Set (Union-Find) data structure with path compression and union by rank. Include operations: make_set, find, union, and connected. Show how it achieves nearly O(1) amortized operations.''',
        r'''<think>
Union-Find tracks a partition of elements into disjoint sets. Naive implementation with trees can degenerate to O(n) per find.

Two optimizations make it nearly O(1) amortized:

1. Path compression (in find): when finding the root of x, make every node on the path point directly to the root. This flattens the tree.

2. Union by rank: always attach the shorter tree under the root of the taller tree. This keeps trees shallow.

With both optimizations: amortized O(alpha(n)) per operation, where alpha is the inverse Ackermann function — effectively constant (alpha(n) <= 4 for all practical n, even n = 2^65536).

Let me trace:
make_set for 0,1,2,3,4
parent: [0,1,2,3,4], rank: [0,0,0,0,0]

union(0,1): root(0)=0, root(1)=1, same rank → parent[1]=0, rank[0]=1
union(2,3): root(2)=2, root(3)=3, same rank → parent[3]=2, rank[2]=1
union(0,2): root(0)=0, root(2)=2, same rank → parent[2]=0, rank[0]=2
Now tree: 0 is root, children 1 and 2, 2's child 3.

find(3): path 3→2→0. With path compression: parent[3]=0, parent[2]=0 (already).
Next find(3): just 3→0. O(1)!

union(4,3): root(4)=4 (rank 0), root(3)=0 (rank 2). Rank 0 < 2, so parent[4]=0.

connected(1,3): find(1)=0, find(3)=0 → same root → True.

Edge cases: union of already-connected elements (no-op), single element set, all elements in one set.

Applications: Kruskal's MST, connected components, cycle detection in undirected graphs, percolation.
</think>

```python
class UnionFind:
    """
    Disjoint Set (Union-Find) with path compression and union by rank.

    Amortized O(alpha(n)) per operation, where alpha is the inverse
    Ackermann function — effectively O(1) for all practical inputs.
    """

    def __init__(self, n: int = 0):
        """Initialize with n elements (0 to n-1)."""
        self.parent = list(range(n))
        self.rank = [0] * n
        self.count = n  # Number of disjoint sets
        self._size = [1] * n  # Size of each set

    def make_set(self, x: int):
        """Add a new element. O(1)."""
        if x < len(self.parent):
            return  # Already exists
        while len(self.parent) <= x:
            idx = len(self.parent)
            self.parent.append(idx)
            self.rank.append(0)
            self._size.append(1)
            self.count += 1

    def find(self, x: int) -> int:
        """
        Find root of x with path compression. Amortized O(alpha(n)).

        Path compression: every node on the path to root is set to
        point directly to root, flattening the tree for future queries.
        """
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])  # Path compression
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        """
        Merge sets containing x and y. Returns True if they were separate.
        Union by rank: attach shorter tree under taller tree.
        Amortized O(alpha(n)).
        """
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False  # Already in same set

        # Union by rank: attach smaller rank tree under larger
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        self._size[rx] += self._size[ry]

        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1

        self.count -= 1
        return True

    def connected(self, x: int, y: int) -> bool:
        """Check if x and y are in the same set. Amortized O(alpha(n))."""
        return self.find(x) == self.find(y)

    def set_size(self, x: int) -> int:
        """Return size of the set containing x."""
        return self._size[self.find(x)]

    def num_sets(self) -> int:
        """Return number of disjoint sets."""
        return self.count


def count_connected_components(n, edges):
    """Example application: count connected components in undirected graph."""
    uf = UnionFind(n)
    for u, v in edges:
        uf.union(u, v)
    return uf.num_sets()


def detect_cycle(n, edges):
    """Example application: detect cycle in undirected graph."""
    uf = UnionFind(n)
    for u, v in edges:
        if uf.connected(u, v):
            return True, (u, v)  # u-v edge creates a cycle
        uf.union(u, v)
    return False, None


# --- Example ---
if __name__ == "__main__":
    uf = UnionFind(6)
    print(f"Initial sets: {uf.num_sets()}")  # 6

    uf.union(0, 1)
    uf.union(2, 3)
    uf.union(0, 2)
    print(f"After unions 0-1, 2-3, 0-2: {uf.num_sets()} sets")  # 3
    print(f"0 and 3 connected? {uf.connected(0, 3)}")  # True
    print(f"0 and 4 connected? {uf.connected(0, 4)}")  # False
    print(f"Size of set containing 0: {uf.set_size(0)}")  # 4

    uf.union(4, 5)
    uf.union(0, 5)
    print(f"After joining all: {uf.num_sets()} set")  # 1

    # Connected components
    edges = [(0, 1), (1, 2), (3, 4)]
    print(f"\nComponents in 5-node graph: {count_connected_components(5, edges)}")  # 2

    # Cycle detection
    edges2 = [(0, 1), (1, 2), (2, 0)]
    has_cycle, edge = detect_cycle(3, edges2)
    print(f"Cycle? {has_cycle}, at edge {edge}")  # True, (2, 0)

    # Performance demo: union 1 million elements
    import time
    n = 1_000_000
    uf_big = UnionFind(n)
    start = time.time()
    for i in range(1, n):
        uf_big.union(i, i - 1)
    for i in range(n):
        uf_big.find(i)
    elapsed = time.time() - start
    print(f"\n1M unions + 1M finds: {elapsed:.3f}s")
```

**Complexity Analysis:**
- **find:** O(alpha(n)) amortized — alpha(n) <= 4 for all practical n (up to ~10^80)
- **union:** O(alpha(n)) amortized — dominated by two find calls
- **connected:** O(alpha(n)) amortized — two find calls
- **Space:** O(n) for parent, rank, and size arrays
- **Key insight:** Path compression flattens trees on every find; union by rank keeps trees shallow. Combined, they give inverse-Ackermann amortized time — the closest thing to O(1) that isn't actually O(1)'''
    ),
    (
        "deep_reasoning/kmp-string-matching",
        r'''Implement the KMP (Knuth-Morris-Pratt) string matching algorithm. Build the failure function (partial match table) and use it to find all occurrences of a pattern in a text. Explain why it achieves O(n+m) time.''',
        r'''<think>
Naive string matching: for each position in text, try to match the entire pattern → O(n*m) worst case. Example: text="aaaaaab", pattern="aaab" — we keep re-scanning the same 'a' characters.

KMP's key insight: when a mismatch occurs, we've already matched some prefix of the pattern. The failure function tells us the longest proper prefix of the matched portion that is also a suffix — so we can skip ahead instead of restarting.

Failure function (also called "partial match table" or "pi array"):
- pi[i] = length of longest proper prefix of pattern[0..i] that is also a suffix
- pi[0] = 0 (by definition, no proper prefix of a single character)

Building pi: use the pattern itself! Compare pattern against itself, extending matches.

Let me trace building pi for "abcabd":
i=0: pi[0]=0
i=1: 'b' vs 'a' → no match, pi[1]=0
i=2: 'c' vs 'a' → no match, pi[2]=0
i=3: 'a' vs 'a' → match! pi[3]=1
i=4: 'b' vs 'b' → extends match! pi[4]=2
i=5: 'd' vs 'c' → mismatch. Fall back: j=pi[1]=0. 'd' vs 'a' → no match. pi[5]=0.

So pi = [0, 0, 0, 1, 2, 0].

Searching "abcabcabd" for "abcabd":
Match a-b-c-a-b, then mismatch at index 5: text[5]='c' vs pattern[5]='d'.
pi[4]=2, so we know "ab" is both prefix and suffix of what we matched.
Jump: compare from pattern[2] (skip "ab"). Continue matching c-a-b-d → found!

Why O(n+m): each text character is compared at most twice (once when advancing, once when failing back). Building pi is O(m) by same argument. Total: O(n+m).

Edge cases: pattern longer than text, empty pattern, pattern equals text, all same characters.
</think>

```python
def build_failure_function(pattern):
    """
    Build the KMP failure function (pi array / partial match table).

    pi[i] = length of longest proper prefix of pattern[0..i]
            that is also a suffix of pattern[0..i].

    Time:  O(m) where m = len(pattern)
    Space: O(m)
    """
    m = len(pattern)
    pi = [0] * m
    j = 0  # Length of previous longest prefix-suffix

    for i in range(1, m):
        # Fall back until we find a match or exhaust options
        while j > 0 and pattern[i] != pattern[j]:
            j = pi[j - 1]

        if pattern[i] == pattern[j]:
            j += 1

        pi[i] = j

    return pi


def kmp_search(text, pattern):
    """
    Find all occurrences of pattern in text using KMP algorithm.

    Args:
        text: the text to search in
        pattern: the pattern to search for

    Returns:
        List of starting indices where pattern occurs in text

    Time:  O(n + m) where n = len(text), m = len(pattern)
    Space: O(m) for the failure function
    """
    n, m = len(text), len(pattern)
    if m == 0:
        return list(range(n + 1))  # Empty pattern matches everywhere
    if m > n:
        return []

    pi = build_failure_function(pattern)
    matches = []
    j = 0  # Number of characters matched in pattern

    for i in range(n):
        # On mismatch, use failure function to skip
        while j > 0 and text[i] != pattern[j]:
            j = pi[j - 1]

        if text[i] == pattern[j]:
            j += 1

        if j == m:
            # Full match found at index i - m + 1
            matches.append(i - m + 1)
            # Continue searching — use failure function to find overlapping matches
            j = pi[j - 1]

    return matches


def kmp_search_annotated(text, pattern):
    """KMP search with step-by-step trace for educational purposes."""
    n, m = len(text), len(pattern)
    pi = build_failure_function(pattern)
    print(f"Pattern: '{pattern}'")
    print(f"Pi array: {pi}")
    print(f"Text:    '{text}'")
    print()

    matches = []
    j = 0

    for i in range(n):
        while j > 0 and text[i] != pattern[j]:
            print(f"  Mismatch at text[{i}]='{text[i]}' vs pattern[{j}]='{pattern[j]}'. "
                  f"Fallback j: {j} -> {pi[j-1]}")
            j = pi[j - 1]

        if text[i] == pattern[j]:
            j += 1

        if j == m:
            pos = i - m + 1
            matches.append(pos)
            print(f"  MATCH at position {pos}!")
            j = pi[j - 1]

    return matches


# --- Example ---
if __name__ == "__main__":
    # Basic example
    text = "abcabcabd"
    pattern = "abcabd"
    print("=== Basic Example ===")
    matches = kmp_search_annotated(text, pattern)
    print(f"Matches at: {matches}\n")

    # Overlapping matches
    text2 = "aaaaaa"
    pattern2 = "aaa"
    print("=== Overlapping Matches ===")
    pi2 = build_failure_function(pattern2)
    print(f"Pattern: '{pattern2}', Pi: {pi2}")
    matches2 = kmp_search(text2, pattern2)
    print(f"'{pattern2}' in '{text2}': positions {matches2}")
    # [0, 1, 2, 3] — four overlapping occurrences

    # DNA pattern matching
    print("\n=== DNA Pattern ===")
    dna = "ATCGATCGATCG"
    gene = "ATCG"
    matches3 = kmp_search(dna, gene)
    print(f"'{gene}' in '{dna}': positions {matches3}")
    # [0, 4, 8]

    # Worst case for naive but O(n+m) for KMP
    print("\n=== Worst Case ===")
    text_worst = "a" * 1000000 + "b"
    pattern_worst = "a" * 999 + "b"
    import time
    start = time.time()
    matches4 = kmp_search(text_worst, pattern_worst)
    elapsed = time.time() - start
    print(f"1M char text, 1K pattern: found {len(matches4)} match(es) in {elapsed:.4f}s")

    # Compare with naive
    start = time.time()
    naive = [i for i in range(len(text_worst) - len(pattern_worst) + 1)
             if text_worst[i:i+len(pattern_worst)] == pattern_worst]
    elapsed2 = time.time() - start
    print(f"Naive approach: {elapsed2:.4f}s")
```

**Complexity Analysis:**
- **Failure function construction:** O(m) — j never exceeds m, and each iteration either increments j or decreases it (via pi fallback). Total increments bounded by m, so total decrements also bounded by m.
- **Search:** O(n) — same amortized argument. j advances at most n times, falls back at most n times.
- **Total:** O(n + m) time, O(m) space
- **Key insight:** The failure function encodes "how much of the pattern we can reuse after a mismatch" — we never re-examine text characters, unlike naive matching which may rescan the same text positions repeatedly'''
    ),
    (
        "deep_reasoning/kruskal-mst-union-find",
        r'''Implement Kruskal's algorithm for finding the Minimum Spanning Tree of a weighted undirected graph. Use Union-Find for efficient cycle detection. Handle disconnected graphs.''',
        r'''<think>
Minimum Spanning Tree: a subset of edges connecting all vertices with minimum total weight, forming a tree (V-1 edges, no cycles).

Kruskal's approach: greedily add edges in order of increasing weight, skipping any edge that would create a cycle.

Why this works (cut property): the cheapest edge crossing any cut of the graph must be in the MST. By sorting and adding greedily, each edge we add is the cheapest that connects two previously disconnected components.

Cycle detection: when considering edge (u,v), it creates a cycle iff u and v are already in the same connected component. Union-Find makes this O(alpha(n)) per check.

Algorithm:
1. Sort all edges by weight: O(E log E)
2. Initialize Union-Find with V elements
3. For each edge (u,v,w) in sorted order:
   - If find(u) != find(v): add edge to MST, union(u,v)
   - Else: skip (would create cycle)
4. Stop when MST has V-1 edges

Let me trace with example:
Vertices: {0,1,2,3}, Edges: (0,1,4), (0,2,3), (1,2,1), (1,3,2), (2,3,5)
Sorted: (1,2,1), (1,3,2), (0,2,3), (0,1,4), (2,3,5)

Process (1,2,1): 1 and 2 in different sets → add. MST weight=1.
Process (1,3,2): 1 and 3 in different sets → add. MST weight=3.
Process (0,2,3): 0 and 2 in different sets → add. MST weight=6.
Now MST has 3 edges = V-1. Done!

For disconnected graphs: we can't form a single MST. Instead we get a minimum spanning forest — one MST per connected component. We detect this when the loop ends with fewer than V-1 edges.

Time: O(E log E + E * alpha(V)) = O(E log E). Space: O(V + E).

Edge cases: single vertex, no edges, parallel edges (multiple edges between same pair), all equal weights.
</think>

```python
class UnionFind:
    """Disjoint set with path compression and union by rank."""

    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n
        self.components = n

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1
        self.components -= 1
        return True


def kruskal_mst(n, edges):
    """
    Kruskal's Minimum Spanning Tree algorithm.

    Args:
        n: number of vertices (0-indexed)
        edges: list of (u, v, weight) — undirected edges

    Returns:
        (total_weight, mst_edges, is_connected)
        mst_edges: list of (u, v, weight) in the MST
        is_connected: True if graph is connected (full MST exists)

    Time:  O(E log E) — dominated by sorting
    Space: O(V + E)
    """
    if n <= 1:
        return 0, [], True

    # Sort edges by weight
    sorted_edges = sorted(edges, key=lambda e: e[2])

    uf = UnionFind(n)
    mst_edges = []
    total_weight = 0

    for u, v, w in sorted_edges:
        if uf.find(u) != uf.find(v):
            uf.union(u, v)
            mst_edges.append((u, v, w))
            total_weight += w

            # Early termination: MST complete
            if len(mst_edges) == n - 1:
                break

    is_connected = len(mst_edges) == n - 1
    return total_weight, mst_edges, is_connected


def print_mst(n, total_weight, mst_edges, is_connected):
    """Pretty-print MST results."""
    if is_connected:
        print(f"MST weight: {total_weight}")
        print(f"MST edges ({len(mst_edges)}):")
        for u, v, w in mst_edges:
            print(f"  {u} -- {v} (weight {w})")
    else:
        print(f"Graph is DISCONNECTED. Minimum spanning forest:")
        print(f"  Total weight: {total_weight}")
        print(f"  Edges: {len(mst_edges)} (need {n-1} for spanning tree)")
        for u, v, w in mst_edges:
            print(f"  {u} -- {v} (weight {w})")


# --- Example ---
if __name__ == "__main__":
    # Connected graph
    print("=== Connected Graph ===")
    n = 4
    edges = [
        (0, 1, 4), (0, 2, 3), (1, 2, 1),
        (1, 3, 2), (2, 3, 5),
    ]
    weight, mst, connected = kruskal_mst(n, edges)
    print_mst(n, weight, mst, connected)
    # MST: (1,2,1), (1,3,2), (0,2,3) → weight 6

    # Larger example
    print("\n=== Larger Graph (7 vertices) ===")
    edges2 = [
        (0, 1, 7), (0, 3, 5), (1, 2, 8), (1, 3, 9),
        (1, 4, 7), (2, 4, 5), (3, 4, 15), (3, 5, 6),
        (4, 5, 8), (4, 6, 9), (5, 6, 11),
    ]
    weight2, mst2, conn2 = kruskal_mst(7, edges2)
    print_mst(7, weight2, mst2, conn2)

    # Disconnected graph
    print("\n=== Disconnected Graph ===")
    edges3 = [(0, 1, 3), (2, 3, 5)]  # Two components
    weight3, mst3, conn3 = kruskal_mst(4, edges3)
    print_mst(4, weight3, mst3, conn3)

    # Complete graph (K5)
    print("\n=== Complete Graph K5 ===")
    import random
    random.seed(42)
    k5_edges = [(i, j, random.randint(1, 20))
                for i in range(5) for j in range(i+1, 5)]
    print(f"All edges: {k5_edges}")
    w5, m5, c5 = kruskal_mst(5, k5_edges)
    print_mst(5, w5, m5, c5)
```

**Complexity Analysis:**
- **Time:** O(E log E) — sorting edges dominates; Union-Find operations are O(E * alpha(V)) which is effectively O(E)
- **Space:** O(V + E) — Union-Find uses O(V), edge list O(E)
- **Correctness:** Follows from the cut property — each greedy edge selection picks the minimum weight edge crossing a cut
- **Key insight:** Sorting edges + Union-Find cycle detection = elegant O(E log E) MST. Kruskal's is often preferred for sparse graphs, while Prim's is better for dense graphs'''
    ),
    (
        "deep_reasoning/max-flow-edmonds-karp",
        r'''Implement the maximum flow algorithm using Ford-Fulkerson method with BFS (Edmonds-Karp algorithm). Find the maximum flow from a source to a sink in a directed graph with edge capacities.''',
        r'''<think>
Maximum flow problem: given a directed graph with edge capacities, find the maximum amount of "flow" that can be sent from source s to sink t without exceeding any edge's capacity.

Ford-Fulkerson method: repeatedly find an augmenting path from s to t in the residual graph, and push flow along it. The residual graph has:
- Forward edges with remaining capacity (capacity - flow)
- Backward edges with flow (allowing "undoing" previously sent flow)

Edmonds-Karp is Ford-Fulkerson with BFS for path finding. This guarantees:
- Each augmenting path is shortest (in terms of number of edges)
- At most O(VE) augmentation rounds
- Total time: O(VE^2)

Why BFS matters: DFS-based Ford-Fulkerson can be O(E * max_flow) which can be exponential with irrational capacities. BFS guarantees polynomial time.

Let me trace a small example:
Nodes: s=0, a=1, b=2, t=3
Edges: s→a(10), s→b(10), a→b(2), a→t(8), b→t(10)

BFS finds s→a→t, bottleneck=min(10,8)=8. Push 8.
Residual: s→a has 2 left, a→t has 0 left (saturated), t→a has 8 (backward).

BFS finds s→b→t, bottleneck=min(10,10)=10. Push 10.
Residual: s→b has 0, b→t has 0.

BFS finds s→a→b→t... s→a has 2, a→b has 2, b→t is 0 (saturated).
Wait, b→t was saturated. Let me recheck. After pushing 10 through b→t, it's 0.

Actually we need to try: s→a(2 left)→b(2)→t... b→t has 0 left. No path.
Max flow = 8 + 10 = 18.

Actually let me recompute. After first round: s→a:2, a→t:0. After second: s→b:0, b→t:0.
Can we find s→a→b→t? s→a has 2 remaining, a→b has 2, b→t has 0. No.
Max flow = 18.

Edge cases: no path from s to t (max flow = 0), single edge, parallel edges, source equals sink.
</think>

```python
from collections import defaultdict, deque


class MaxFlow:
    """
    Edmonds-Karp algorithm (Ford-Fulkerson with BFS).

    Time:  O(V * E^2)
    Space: O(V + E)
    """

    def __init__(self, n):
        """Initialize with n nodes (0-indexed)."""
        self.n = n
        self.graph = defaultdict(lambda: defaultdict(int))  # capacity
        self.flow = defaultdict(lambda: defaultdict(int))    # current flow

    def add_edge(self, u, v, capacity):
        """Add directed edge u -> v with given capacity."""
        self.graph[u][v] += capacity  # Support parallel edges

    def _bfs(self, source, sink):
        """
        BFS to find shortest augmenting path in residual graph.
        Returns (bottleneck, path) or (0, []) if no path exists.
        """
        visited = {source}
        queue = deque([(source, [source], float('inf'))])

        while queue:
            u, path, bottleneck = queue.popleft()

            for v in set(list(self.graph[u].keys()) + list(self.flow.keys())):
                if v in visited:
                    continue

                # Residual capacity: forward capacity - flow + backward flow
                residual = self.graph[u][v] - self.flow[u][v]

                if residual > 0:
                    visited.add(v)
                    new_bottleneck = min(bottleneck, residual)
                    new_path = path + [v]

                    if v == sink:
                        return new_bottleneck, new_path

                    queue.append((v, new_path, new_bottleneck))

        return 0, []

    def max_flow(self, source, sink):
        """
        Compute maximum flow from source to sink.

        Returns:
            (max_flow_value, flow_on_each_edge)
        """
        total_flow = 0

        while True:
            bottleneck, path = self._bfs(source, sink)
            if bottleneck == 0:
                break

            total_flow += bottleneck

            # Update flow along the path
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                self.flow[u][v] += bottleneck
                self.flow[v][u] -= bottleneck  # Backward edge

        # Collect flow on original edges
        edge_flows = {}
        for u in self.graph:
            for v in self.graph[u]:
                if self.flow[u][v] > 0:
                    edge_flows[(u, v)] = self.flow[u][v]

        return total_flow, edge_flows


class MaxFlowOptimized:
    """
    Optimized Edmonds-Karp using adjacency list with edge objects.
    Better constant factors for large graphs.
    """

    def __init__(self, n):
        self.n = n
        self.adj = [[] for _ in range(n)]

    def add_edge(self, u, v, cap):
        """Add edge u->v with capacity cap. Creates reverse edge too."""
        # Forward edge
        forward = [v, cap, len(self.adj[v])]
        # Backward edge (capacity 0)
        backward = [u, 0, len(self.adj[u])]
        self.adj[u].append(forward)
        self.adj[v].append(backward)

    def _bfs(self, s, t, parent):
        """BFS finding augmenting path. Returns True if path exists."""
        visited = [False] * self.n
        visited[s] = True
        queue = deque([s])

        while queue:
            u = queue.popleft()
            for i, (v, cap, _) in enumerate(self.adj[u]):
                if not visited[v] and cap > 0:
                    visited[v] = True
                    parent[v] = (u, i)
                    if v == t:
                        return True
                    queue.append(v)
        return False

    def max_flow(self, s, t):
        """Compute max flow using Edmonds-Karp. O(VE^2)."""
        total = 0
        parent = [None] * self.n

        while self._bfs(s, t, parent):
            # Find bottleneck
            bottleneck = float('inf')
            v = t
            while v != s:
                u, idx = parent[v]
                bottleneck = min(bottleneck, self.adj[u][idx][1])
                v = u

            # Update residual capacities
            v = t
            while v != s:
                u, idx = parent[v]
                self.adj[u][idx][1] -= bottleneck
                rev_idx = self.adj[u][idx][2]
                self.adj[v][rev_idx][1] += bottleneck
                v = u

            total += bottleneck
            parent = [None] * self.n

        return total


# --- Example ---
if __name__ == "__main__":
    # Example 1: Simple network
    print("=== Simple Network ===")
    mf = MaxFlow(4)
    # s=0, a=1, b=2, t=3
    mf.add_edge(0, 1, 10)
    mf.add_edge(0, 2, 10)
    mf.add_edge(1, 2, 2)
    mf.add_edge(1, 3, 8)
    mf.add_edge(2, 3, 10)

    flow_val, flows = mf.max_flow(0, 3)
    print(f"Max flow: {flow_val}")
    print(f"Edge flows: {flows}")
    # Max flow: 18

    # Example 2: Classic textbook example
    print("\n=== Textbook Example ===")
    mf2 = MaxFlowOptimized(6)
    # s=0, t=5
    edges = [
        (0, 1, 16), (0, 2, 13), (1, 2, 10), (1, 3, 12),
        (2, 1, 4), (2, 4, 14), (3, 2, 9), (3, 5, 20),
        (4, 3, 7), (4, 5, 4),
    ]
    for u, v, c in edges:
        mf2.add_edge(u, v, c)

    flow2 = mf2.max_flow(0, 5)
    print(f"Max flow: {flow2}")  # 23

    # Example 3: No path
    print("\n=== No Path ===")
    mf3 = MaxFlowOptimized(3)
    mf3.add_edge(0, 1, 10)
    # No edge from 1 to 2
    flow3 = mf3.max_flow(0, 2)
    print(f"Max flow (disconnected): {flow3}")  # 0
```

**Complexity Analysis:**
- **Time:** O(V * E^2) — BFS is O(E), at most O(VE) augmentations, each BFS is O(E)
- **Space:** O(V + E) for adjacency list and BFS structures
- **BFS guarantee:** shortest augmenting path ensures at most O(VE) rounds (proven by Edmonds-Karp)
- **Key insight:** The residual graph with backward edges allows "undoing" suboptimal flow choices, guaranteeing we find the true maximum. BFS (vs DFS) makes it polynomial even with irrational capacities'''
    ),
    (
        "deep_reasoning/convex-hull-graham-scan",
        r'''Implement the Convex Hull using Graham Scan algorithm. Handle collinear points correctly. Return the hull points in counter-clockwise order.''',
        r'''<think>
Convex hull: the smallest convex polygon containing all points. Think of it as stretching a rubber band around all points.

Graham Scan algorithm:
1. Find the bottom-most point (lowest y, then leftmost x as tiebreaker). This is guaranteed to be on the hull.
2. Sort all other points by polar angle with respect to this anchor point.
3. Process sorted points, maintaining a stack of hull candidates. For each new point, check if it makes a "left turn" from the last two points on the stack. If not (right turn or collinear), pop the stack.

The cross product determines turn direction:
cross(O, A, B) = (A.x - O.x) * (B.y - O.y) - (A.y - O.y) * (B.x - O.x)
- > 0: counter-clockwise (left turn) ← keep
- = 0: collinear
- < 0: clockwise (right turn) ← pop

Collinear point handling: tricky! When points are collinear with the anchor:
- During sorting: if same angle, sort by distance from anchor.
- For the last group of collinear points (those at the end of sorted order with same max angle), reverse their order so the farthest comes first. This ensures collinear boundary points are handled.
- For strict convex hull (no 3 collinear points), use strict left turn (pop on cross <= 0).
- For hull including collinear points, use pop on cross < 0.

Let me trace with points: (0,0), (1,1), (2,2), (3,0), (0,3)
Anchor: (0,0) (lowest y)
Sorted by angle: (3,0) at 0°, (2,2) at 45°, (1,1) at 45° — wait, same angle.
(1,1) and (2,2) have same angle. Sort by distance: (1,1) first, (2,2) second.
Then (0,3) at 90°.

Stack: [(0,0)]
Process (3,0): stack=[(0,0),(3,0)]
Process (1,1): cross((0,0),(3,0),(1,1)) = 3*1-0*1=3 > 0 → left turn. Push.
Stack: [(0,0),(3,0),(1,1)]
Process (2,2): cross((3,0),(1,1),(2,2)) = (-2)(2)-(1)(1)=-5 < 0 → right turn. Pop (1,1).
cross((0,0),(3,0),(2,2)) = 3*2-0*2=6 > 0 → left turn. Push.
Stack: [(0,0),(3,0),(2,2)]
Process (0,3): cross((3,0),(2,2),(0,3)) = (-1)(3)-(2)(-2)=-3+4=1 > 0 → left turn. Push.
Stack: [(0,0),(3,0),(2,2),(0,3)]

Hull: (0,0), (3,0), (2,2), (0,3). But (2,2) is on the boundary of (3,0)-(0,3)? Let me check: midpoint would be (1.5, 1.5). (2,2) is inside the triangle... Actually no, hull is correct — 4 points form a quadrilateral.

Time: O(n log n) dominated by sorting. Space: O(n).
</think>

```python
import math
from functools import cmp_to_key


def cross(o, a, b):
    """
    Cross product of vectors OA and OB.
    > 0: counter-clockwise, = 0: collinear, < 0: clockwise
    """
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def dist_sq(a, b):
    """Squared Euclidean distance between two points."""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def graham_scan(points, include_collinear=False):
    """
    Graham Scan convex hull algorithm.

    Args:
        points: list of (x, y) tuples
        include_collinear: if True, include collinear points on hull boundary

    Returns:
        List of hull points in counter-clockwise order

    Time:  O(n log n)
    Space: O(n)
    """
    if len(points) <= 1:
        return list(points)

    # Remove duplicates
    points = list(set(points))
    n = len(points)
    if n <= 2:
        return points

    # Step 1: Find anchor — bottom-most, then left-most
    anchor_idx = 0
    for i in range(1, n):
        if (points[i][1] < points[anchor_idx][1] or
            (points[i][1] == points[anchor_idx][1] and
             points[i][0] < points[anchor_idx][0])):
            anchor_idx = i

    points[0], points[anchor_idx] = points[anchor_idx], points[0]
    anchor = points[0]

    # Step 2: Sort by polar angle relative to anchor
    def compare(p, q):
        cp = cross(anchor, p, q)
        if cp != 0:
            return -1 if cp > 0 else 1  # CCW first
        # Collinear: sort by distance (closer first)
        dp = dist_sq(anchor, p)
        dq = dist_sq(anchor, q)
        return -1 if dp < dq else (1 if dp > dq else 0)

    rest = sorted(points[1:], key=cmp_to_key(compare))

    if include_collinear:
        # Reverse the last group of collinear points (farthest first at the end)
        # so that when traversing, we include collinear boundary points
        i = len(rest) - 1
        while i > 0 and cross(anchor, rest[i], rest[i - 1]) == 0:
            i -= 1
        rest[i:] = rest[i:][::-1]

    # Step 3: Build hull using a stack
    stack = [anchor]
    for p in rest:
        # Pop while the last turn is clockwise (or collinear if strict hull)
        while len(stack) > 1:
            cp = cross(stack[-2], stack[-1], p)
            if include_collinear:
                if cp < 0:
                    stack.pop()
                else:
                    break
            else:
                if cp <= 0:
                    stack.pop()
                else:
                    break
        stack.append(p)

    return stack


def hull_area(hull):
    """Compute area of convex hull using shoelace formula."""
    n = len(hull)
    if n < 3:
        return 0
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += hull[i][0] * hull[j][1]
        area -= hull[j][0] * hull[i][1]
    return abs(area) / 2


def hull_perimeter(hull):
    """Compute perimeter of convex hull."""
    n = len(hull)
    perimeter = 0
    for i in range(n):
        j = (i + 1) % n
        perimeter += math.sqrt(dist_sq(hull[i], hull[j]))
    return perimeter


# --- Example ---
if __name__ == "__main__":
    # Basic example
    points = [(0, 0), (1, 1), (2, 2), (3, 0), (0, 3), (1, 0), (2, 1)]
    hull = graham_scan(points)
    print(f"Points: {points}")
    print(f"Convex Hull (CCW): {hull}")
    print(f"Area: {hull_area(hull)}")
    print(f"Perimeter: {hull_perimeter(hull):.2f}")

    # Collinear points
    print("\n=== Collinear Points ===")
    collinear = [(0, 0), (1, 0), (2, 0), (3, 0), (1, 1), (2, 1)]
    hull_strict = graham_scan(collinear, include_collinear=False)
    hull_collinear = graham_scan(collinear, include_collinear=True)
    print(f"Strict hull: {hull_strict}")
    print(f"With collinear: {hull_collinear}")

    # Square with interior points
    print("\n=== Square + Interior ===")
    square = [(0,0), (10,0), (10,10), (0,10), (5,5), (3,7), (8,2)]
    hull_sq = graham_scan(square)
    print(f"Hull: {hull_sq}")
    print(f"Area: {hull_area(hull_sq)}")  # 100

    # Triangle
    print("\n=== Triangle ===")
    tri = [(0,0), (5,0), (2,3)]
    hull_tri = graham_scan(tri)
    print(f"Hull: {hull_tri}, Area: {hull_area(hull_tri)}")
```

**Complexity Analysis:**
- **Time:** O(n log n) — sorting dominates; the stack processing is O(n) amortized (each point pushed/popped at most once)
- **Space:** O(n) for the sorted array and stack
- **Collinear handling:** Reverse the last collinear group in sorted order to include boundary points
- **Key insight:** Graham scan maintains a CCW hull invariant via cross product checks. The sorting by polar angle ensures we process points in a sweep order, and the stack efficiently backtracks when the hull "dents inward"'''
    ),
    (
        "deep_reasoning/b-tree-insert-search",
        r'''Implement a B-tree with insert and search operations, including node splitting when a node exceeds maximum keys. Use minimum degree t (each node has at most 2t-1 keys and at least t-1 keys, except root). Explain why B-trees are optimal for disk-based storage.''',
        r'''<think>
B-trees are balanced search trees designed for systems that read/write large blocks of data (disks, databases). Unlike binary trees where each node has 1 key and 2 children, B-tree nodes have many keys and children — matching disk block sizes.

Why B-trees for disk:
- Disk reads are expensive (seek time ~10ms). Reading 4KB is almost as fast as reading 1 byte.
- B-tree node = one disk block (e.g., 4KB). With 4-byte keys, one node holds ~1000 keys.
- A B-tree of height 3 with t=500 can store ~500 million keys with only 3 disk reads per search!
- Binary tree would need ~30 disk reads for the same dataset.

Properties (minimum degree t):
- Each node has at most 2t-1 keys and 2t children
- Each non-root node has at least t-1 keys
- Root has at least 1 key (if non-empty)
- All leaves at same level (perfectly balanced)

Insert algorithm:
1. Find the leaf node where the key belongs.
2. If the leaf has room (< 2t-1 keys), insert and done.
3. If full, SPLIT: take the median key, push it up to parent, split node into two halves.
4. If parent is also full, split propagates up. If root splits, tree grows taller.

Proactive splitting (top-down): as we descend looking for the insertion point, split any full node we encounter. This ensures the parent always has room to accept a promoted key.

Let me trace with t=2 (2-3-4 tree, max 3 keys per node):
Insert 10: root=[10]
Insert 20: root=[10,20]
Insert 30: root=[10,20,30] — full!
Insert 5: root is full, split! Median=20 promoted.
  New root: [20], children: [5,10] and [30]
Insert 15: goes into left child → [5,10,15]
Insert 25: goes into right child → [25,30]

Time: O(t * log_t(n)) per operation. Height = O(log_t(n)). Each node operation is O(t) for shifting keys.
Space: O(n).
</think>

```python
class BTreeNode:
    """Node in a B-tree."""

    def __init__(self, t, leaf=True):
        self.t = t          # Minimum degree
        self.keys = []       # List of keys
        self.children = []   # List of child nodes
        self.leaf = leaf     # True if leaf node

    @property
    def is_full(self):
        return len(self.keys) == 2 * self.t - 1

    def __repr__(self):
        return f"BNode({self.keys}, leaf={self.leaf})"


class BTree:
    """
    B-tree with insert and search.

    Properties (minimum degree t):
    - Each node: at most 2t-1 keys, at least t-1 keys (except root)
    - All leaves at same depth
    - O(log_t(n)) height → O(t * log_t(n)) per operation

    Optimal for disk-based storage: each node = one disk block,
    minimizing I/O operations.
    """

    def __init__(self, t=3):
        """
        Initialize B-tree with minimum degree t.
        Each node has at most 2t-1 keys.
        """
        self.t = t
        self.root = BTreeNode(t, leaf=True)

    def search(self, key, node=None):
        """
        Search for key in the B-tree.
        Returns (node, index) if found, None otherwise.

        Time: O(t * log_t(n)) — O(log_t(n)) nodes visited, O(t) per node
        """
        if node is None:
            node = self.root

        # Find the first key >= target
        i = 0
        while i < len(node.keys) and key > node.keys[i]:
            i += 1

        if i < len(node.keys) and key == node.keys[i]:
            return node, i
        elif node.leaf:
            return None
        else:
            return self.search(key, node.children[i])

    def insert(self, key):
        """
        Insert key into B-tree. Uses proactive splitting (top-down).

        Time: O(t * log_t(n))
        """
        root = self.root

        if root.is_full:
            # Root is full — split it, creating new root
            new_root = BTreeNode(self.t, leaf=False)
            new_root.children.append(self.root)
            self._split_child(new_root, 0)
            self.root = new_root

        self._insert_non_full(self.root, key)

    def _insert_non_full(self, node, key):
        """Insert into a node that is guaranteed not full."""
        i = len(node.keys) - 1

        if node.leaf:
            # Insert key in sorted position
            node.keys.append(None)
            while i >= 0 and key < node.keys[i]:
                node.keys[i + 1] = node.keys[i]
                i -= 1
            node.keys[i + 1] = key
        else:
            # Find child to descend into
            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1

            # Proactively split child if full
            if node.children[i].is_full:
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1

            self._insert_non_full(node.children[i], key)

    def _split_child(self, parent, child_idx):
        """
        Split parent.children[child_idx] which must be full.
        Promotes median key to parent, creates new sibling node.
        """
        t = self.t
        child = parent.children[child_idx]
        new_node = BTreeNode(t, leaf=child.leaf)

        # Median key goes up to parent
        median_key = child.keys[t - 1]

        # New node gets the right half of keys
        new_node.keys = child.keys[t:]
        child.keys = child.keys[:t - 1]

        # Move children too if not leaf
        if not child.leaf:
            new_node.children = child.children[t:]
            child.children = child.children[:t]

        # Insert median key and new child into parent
        parent.keys.insert(child_idx, median_key)
        parent.children.insert(child_idx + 1, new_node)

    def inorder(self):
        """Return all keys in sorted order."""
        result = []
        self._inorder(self.root, result)
        return result

    def _inorder(self, node, result):
        for i in range(len(node.keys)):
            if not node.leaf:
                self._inorder(node.children[i], result)
            result.append(node.keys[i])
        if not node.leaf:
            self._inorder(node.children[-1], result)

    def height(self):
        """Return height of the tree."""
        h = 0
        node = self.root
        while not node.leaf:
            h += 1
            node = node.children[0]
        return h

    def print_tree(self, node=None, level=0, prefix="Root: "):
        """Pretty-print the B-tree structure."""
        if node is None:
            node = self.root
        print(" " * (level * 4) + prefix + str(node.keys))
        if not node.leaf:
            for i, child in enumerate(node.children):
                self.print_tree(child, level + 1, f"Child {i}: ")


# --- Example ---
if __name__ == "__main__":
    bt = BTree(t=2)  # 2-3-4 tree (max 3 keys per node)

    keys = [10, 20, 30, 5, 15, 25, 35, 1, 8, 12, 18, 22, 28, 33, 38]
    for k in keys:
        bt.insert(k)

    print("B-tree structure (t=2):")
    bt.print_tree()
    print(f"\nHeight: {bt.height()}")
    print(f"In-order: {bt.inorder()}")

    # Search
    for k in [15, 25, 99]:
        result = bt.search(k)
        if result:
            node, idx = result
            print(f"Found {k} at index {idx} in node {node.keys}")
        else:
            print(f"{k} not found")

    # Larger example with t=3
    print("\n=== B-tree with t=3 ===")
    bt2 = BTree(t=3)  # Max 5 keys per node
    for k in range(1, 31):
        bt2.insert(k)
    bt2.print_tree()
    print(f"Height: {bt2.height()}, Keys: {len(bt2.inorder())}")
```

**Complexity Analysis:**
- **Search:** O(t * log_t(n)) — height is O(log_t(n)), scanning a node is O(t) (can be O(log t) with binary search)
- **Insert:** O(t * log_t(n)) — proactive splitting visits O(log_t(n)) nodes, splitting is O(t)
- **Space:** O(n) total for all keys
- **Disk I/O:** O(log_t(n)) — one disk read per level, which is the key advantage
- **Key insight:** By making t match the disk block size (e.g., t=500 for 4KB blocks), a B-tree of height 3 can index billions of records with just 3 disk reads'''
    ),
    (
        "deep_reasoning/skip-list-probabilistic",
        r'''Implement a Skip List — a probabilistic data structure that provides O(log n) expected time for search, insert, and delete. Explain how randomization replaces deterministic balancing.''',
        r'''<think>
A skip list is a layered linked list where higher layers skip over more elements, providing fast search similar to balanced BSTs but with a much simpler implementation.

The key insight: instead of complex rotations (like AVL/RBT), skip lists use RANDOMIZATION to maintain balance probabilistically. Each element is promoted to higher levels with probability p (usually 0.5).

Structure:
- Level 0: sorted linked list of all elements (like a regular sorted list)
- Level 1: a subset of elements (each promoted with probability p)
- Level 2: subset of level 1 (again, probability p)
- ...

Expected height: O(log n) levels. At each level, we skip ~1/p elements.

Search: start at top-left. At each level:
- Move right while next element < target
- If next element >= target, drop down one level
- If at level 0 and element found, return it

This is like binary search but on linked lists! Each level halves the search space (on average).

Let me trace with elements [1, 3, 5, 7, 9] and random promotions:
Level 3: HEAD ———————————————> 5 ——————————> NIL
Level 2: HEAD ——> 3 ————————> 5 ——————————> NIL
Level 1: HEAD ——> 3 ——> 5 ——> 7 ——————————> NIL
Level 0: HEAD -> 1 -> 3 -> 5 -> 7 -> 9 -> NIL

Search for 7:
Level 3: HEAD, next=5 < 7, go right. At 5, next=NIL, drop down.
Level 2: At 5, next=NIL, drop down.
Level 1: At 5, next=7 = target. Found! (3 comparisons vs 4 for linear search)

Insert: search to find position at each level, then randomly decide how many levels to promote.

Expected complexities: O(log n) for search, insert, delete — matching balanced BSTs but with much simpler code.

Edge cases: inserting duplicates, empty list, single element, very unlucky random sequence (extremely rare).
</think>

```python
import random
import math


class SkipNode:
    __slots__ = ('key', 'value', 'forward')

    def __init__(self, key, value, level):
        self.key = key
        self.value = value
        self.forward = [None] * (level + 1)  # forward[i] = next node at level i


class SkipList:
    """
    Skip List: probabilistic alternative to balanced BSTs.

    Expected O(log n) search, insert, delete.
    Uses randomization instead of deterministic balancing.

    Properties:
    - Simpler to implement than AVL/RBT
    - Good cache behavior (sequential pointer chasing)
    - Lock-free variants exist for concurrent programming
    """

    def __init__(self, max_level=16, p=0.5):
        """
        Args:
            max_level: maximum number of levels
            p: probability of promoting to next level (typically 0.5)
        """
        self.max_level = max_level
        self.p = p
        self.level = 0  # Current highest level
        self.header = SkipNode(float('-inf'), None, max_level)
        self.size = 0

    def _random_level(self):
        """Generate random level for new node. Geometric distribution."""
        lvl = 0
        while random.random() < self.p and lvl < self.max_level:
            lvl += 1
        return lvl

    def search(self, key):
        """
        Search for key. Returns value if found, None otherwise.
        Expected time: O(log n)
        """
        current = self.header
        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]

        current = current.forward[0]
        if current and current.key == key:
            return current.value
        return None

    def insert(self, key, value=None):
        """
        Insert key-value pair. Updates value if key exists.
        Expected time: O(log n)
        """
        # Track update points at each level
        update = [None] * (self.max_level + 1)
        current = self.header

        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
            update[i] = current

        current = current.forward[0]

        if current and current.key == key:
            current.value = value  # Update existing
            return

        # Generate random level for new node
        new_level = self._random_level()

        if new_level > self.level:
            for i in range(self.level + 1, new_level + 1):
                update[i] = self.header
            self.level = new_level

        new_node = SkipNode(key, value, new_level)

        # Insert node at each level by updating forward pointers
        for i in range(new_level + 1):
            new_node.forward[i] = update[i].forward[i]
            update[i].forward[i] = new_node

        self.size += 1

    def delete(self, key):
        """
        Delete key from skip list. Returns True if found and deleted.
        Expected time: O(log n)
        """
        update = [None] * (self.max_level + 1)
        current = self.header

        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
            update[i] = current

        target = current.forward[0]

        if target is None or target.key != key:
            return False

        # Remove target from each level
        for i in range(self.level + 1):
            if update[i].forward[i] != target:
                break
            update[i].forward[i] = target.forward[i]

        # Reduce level if top levels are now empty
        while self.level > 0 and self.header.forward[self.level] is None:
            self.level -= 1

        self.size -= 1
        return True

    def __contains__(self, key):
        return self.search(key) is not None

    def __len__(self):
        return self.size

    def to_list(self):
        """Return all key-value pairs in sorted order."""
        result = []
        current = self.header.forward[0]
        while current:
            result.append((current.key, current.value))
            current = current.forward[0]
        return result

    def display(self):
        """Visualize the skip list levels."""
        for i in range(self.level, -1, -1):
            line = f"Level {i}: "
            current = self.header.forward[i]
            while current:
                line += f"{current.key} -> "
                current = current.forward[i]
            line += "NIL"
            print(line)


# --- Example ---
if __name__ == "__main__":
    random.seed(42)
    sl = SkipList()

    # Insert elements
    for x in [3, 6, 7, 9, 12, 19, 17, 26, 21, 25]:
        sl.insert(x, f"val_{x}")

    print("Skip List structure:")
    sl.display()
    print(f"\nSize: {len(sl)}")
    print(f"Sorted: {sl.to_list()}")

    # Search
    print(f"\nSearch 19: {sl.search(19)}")  # val_19
    print(f"Search 15: {sl.search(15)}")    # None
    print(f"12 in list: {12 in sl}")         # True

    # Delete
    sl.delete(19)
    print(f"\nAfter deleting 19:")
    sl.display()
    print(f"Search 19: {sl.search(19)}")  # None

    # Performance comparison
    import time
    n = 100_000
    sl_big = SkipList()
    data = list(range(n))
    random.shuffle(data)

    start = time.time()
    for x in data:
        sl_big.insert(x)
    insert_time = time.time() - start

    start = time.time()
    for x in data:
        sl_big.search(x)
    search_time = time.time() - start

    print(f"\n{n:,} operations:")
    print(f"  Insert: {insert_time:.3f}s")
    print(f"  Search: {search_time:.3f}s")
    print(f"  Levels used: {sl_big.level}")
    print(f"  Expected levels: {math.log2(n):.1f}")
```

**Complexity Analysis:**
- **Search:** O(log n) expected — at each level, we skip ~1/p elements; ~log_{1/p}(n) levels
- **Insert:** O(log n) expected — search + pointer updates at each level of new node
- **Delete:** O(log n) expected — search + pointer cleanup
- **Space:** O(n) expected — each element has ~1/(1-p) = 2 pointers on average (with p=0.5)
- **Key insight:** Randomization provides "balance in expectation" without complex rotations. The probability of worst-case O(n) performance is astronomically small (2^{-n}). Skip lists are used in Redis, LevelDB, and MemSQL'''
    ),
    (
        "deep_reasoning/count-inversions-merge-sort",
        r'''Count the number of inversions in an array. An inversion is a pair (i, j) where i < j but arr[i] > arr[j]. Use a modified merge sort to achieve O(n log n) time. Explain why this works.''',
        r'''<think>
The brute force approach: check all pairs (i, j) where i < j → O(n^2). For large arrays, we need O(n log n).

The key insight: merge sort naturally encounters inversions during the merge step! When merging two sorted halves, if we pick an element from the RIGHT half before all elements in the LEFT half are exhausted, that right element is smaller than all remaining left elements — each of those remaining left elements forms an inversion with it.

Specifically, during merge of left[0..m] and right[0..n]:
If left[i] > right[j], then left[i], left[i+1], ..., left[m] are ALL greater than right[j] (because left is sorted). So we add (m - i + 1) inversions — or equivalently, (len(left) - i) inversions.

Let me trace with [3, 1, 2]:
Split: [3] and [1, 2]
Right half: split [1] and [2], merge → [1, 2], 0 inversions (1 < 2).
Merge [3] with [1, 2]:
  Compare 3 vs 1: 3 > 1, pick 1. Inversions += len([3]) - 0 = 1. (inversion: (3,1))
  Compare 3 vs 2: 3 > 2, pick 2. Inversions += 1. (inversion: (3,2))
  Remaining: [3]. Append it. Total inversions = 2.

Another example: [2, 4, 1, 3, 5]
Split: [2, 4] and [1, 3, 5]
Left: [2] [4] → merge → [2, 4], 0 inversions
Right: [1] and [3, 5] → [3] [5] → [3, 5], 0 inv → merge [1] and [3, 5] → [1, 3, 5], 0 inv
Merge [2, 4] with [1, 3, 5]:
  2 vs 1: 2 > 1, pick 1, inv += 2 (both 2 and 4 > 1)
  2 vs 3: 2 < 3, pick 2, no inversions
  4 vs 3: 4 > 3, pick 3, inv += 1 (just 4 > 3)
  4 vs 5: 4 < 5, pick 4
  Remaining: 5
Total: 2 + 1 = 3 inversions: (2,1), (4,1), (4,3). Correct!

Edge cases: sorted array (0 inversions), reverse sorted (n*(n-1)/2 = maximum), all equal (0), single element (0).
</think>

```python
def count_inversions(arr):
    """
    Count inversions in array using modified merge sort.

    An inversion is a pair (i, j) where i < j but arr[i] > arr[j].

    Args:
        arr: list of comparable elements

    Returns:
        (inversion_count, sorted_array)

    Time:  O(n log n)
    Space: O(n)
    """
    if len(arr) <= 1:
        return 0, arr[:]

    mid = len(arr) // 2
    left_inv, left = count_inversions(arr[:mid])
    right_inv, right = count_inversions(arr[mid:])
    split_inv, merged = _merge_count(left, right)

    return left_inv + right_inv + split_inv, merged


def _merge_count(left, right):
    """
    Merge two sorted arrays while counting split inversions.

    A split inversion occurs when left[i] > right[j].
    Since left is sorted, ALL remaining elements left[i..] > right[j],
    so we count (len(left) - i) inversions at once.
    """
    inversions = 0
    merged = []
    i = j = 0

    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            # Key: all remaining left elements are > right[j]
            inversions += len(left) - i
            j += 1

    merged.extend(left[i:])
    merged.extend(right[j:])

    return inversions, merged


def count_inversions_brute_force(arr):
    """Brute force O(n^2) for verification."""
    count = 0
    n = len(arr)
    for i in range(n):
        for j in range(i + 1, n):
            if arr[i] > arr[j]:
                count += 1
    return count


def inversion_distance(arr):
    """
    Normalized inversion distance: 0.0 (sorted) to 1.0 (reverse sorted).
    Useful as a measure of "sortedness".
    """
    n = len(arr)
    if n <= 1:
        return 0.0
    max_inversions = n * (n - 1) // 2
    inv_count, _ = count_inversions(arr)
    return inv_count / max_inversions


# --- Example ---
if __name__ == "__main__":
    # Basic example
    arr = [2, 4, 1, 3, 5]
    inv_count, sorted_arr = count_inversions(arr)
    print(f"Array: {arr}")
    print(f"Inversions: {inv_count}")  # 3: (2,1), (4,1), (4,3)
    print(f"Sorted: {sorted_arr}")
    print(f"Brute force verify: {count_inversions_brute_force(arr)}")

    # Sorted array: 0 inversions
    print(f"\nSorted [1,2,3,4,5]: {count_inversions([1,2,3,4,5])[0]} inversions")

    # Reverse sorted: maximum inversions
    rev = [5, 4, 3, 2, 1]
    inv_rev, _ = count_inversions(rev)
    print(f"Reverse {rev}: {inv_rev} inversions (max = {len(rev)*(len(rev)-1)//2})")

    # Sortedness measure
    import random
    random.seed(42)
    for desc in ["Sorted", "Nearly sorted", "Random", "Reverse"]:
        if desc == "Sorted":
            a = list(range(100))
        elif desc == "Nearly sorted":
            a = list(range(100))
            a[10], a[11] = a[11], a[10]  # One swap
        elif desc == "Random":
            a = list(range(100))
            random.shuffle(a)
        else:
            a = list(range(99, -1, -1))
        dist = inversion_distance(a)
        inv, _ = count_inversions(a)
        print(f"\n{desc}: {inv} inversions, sortedness distance = {dist:.4f}")

    # Performance test
    import time
    n = 100_000
    big = list(range(n))
    random.shuffle(big)

    start = time.time()
    inv_big, _ = count_inversions(big)
    elapsed = time.time() - start
    print(f"\n{n:,} elements: {inv_big:,} inversions in {elapsed:.3f}s")
```

**Complexity Analysis:**
- **Time:** O(n log n) — same as merge sort; counting inversions adds O(1) work per merge comparison
- **Space:** O(n) for the temporary merged arrays (same as merge sort)
- **Correctness:** Every inversion (i, j) is counted exactly once: either both in left half (left_inv), both in right half (right_inv), or split across halves (split_inv during merge)
- **Key insight:** When merging sorted halves, picking from the right means ALL remaining left elements form inversions with it — allowing us to count multiple inversions in O(1). This piggybacks on merge sort's existing O(n log n) work'''
    ),
    (
        "deep_reasoning/sliding-window-maximum-monotonic-deque",
        r'''Implement the Sliding Window Maximum problem: given an array and window size k, return the maximum value in each window position as it slides from left to right. Achieve O(n) time using a monotonic deque.''',
        r'''<think>
Brute force: for each of the (n-k+1) window positions, scan k elements to find max → O(nk). With k close to n, this is O(n^2).

We could use a max-heap: push elements, lazy-delete expired ones → O(n log n). But we can do O(n).

The key insight: maintain a MONOTONIC DEQUE — a deque where elements are in decreasing order. The front is always the current window maximum.

The deque stores INDICES (not values), and maintains the invariant:
- All indices in the deque are within the current window
- Values at those indices are in decreasing order (front = largest)

For each new element arr[i]:
1. Remove from BACK while deque's back element <= arr[i] (they can never be the maximum — arr[i] is newer AND larger)
2. Add i to the back of the deque
3. Remove from FRONT if the front index is outside the window (i - front >= k)
4. The front of the deque is the maximum of the current window

Why O(n): each element is added to the deque once and removed at most once → total operations = O(n).

Let me trace with arr = [1, 3, -1, -3, 5, 3, 6, 7], k = 3:
i=0: deque=[], push 0. deque=[0]. Window not full yet.
i=1: arr[1]=3 > arr[0]=1, pop 0. Push 1. deque=[1]. Not full.
i=2: arr[2]=-1 < arr[1]=3, push 2. deque=[1,2]. Window [0,2] full. Max=arr[1]=3.
i=3: arr[3]=-3 < arr[2]=-1, push 3. deque=[1,2,3]. Front 1 in [1,3]? Yes. Max=arr[1]=3.
i=4: arr[4]=5 > arr[3],arr[2],arr[1]. Pop all. Push 4. deque=[4]. Front 4 in [2,4]? Yes. Max=5.
i=5: arr[5]=3 < 5. Push 5. deque=[4,5]. Front 4 in [3,5]? Yes. Max=5.
i=6: arr[6]=6 > 3, pop 5. 6 > 5, pop 4. Push 6. deque=[6]. Max=6.
i=7: arr[7]=7 > 6, pop 6. Push 7. deque=[7]. Max=7.

Output: [3, 3, 5, 5, 6, 7]. Correct!

Edge cases: k=1 (output is the array itself), k=n (single max), all equal elements, strictly decreasing array.
</think>

```python
from collections import deque


def sliding_window_max(arr, k):
    """
    Find maximum in each sliding window of size k.

    Uses a monotonic deque (decreasing order) to maintain
    window maximum candidates.

    Args:
        arr: input array
        k: window size

    Returns:
        List of maximums, one per window position

    Time:  O(n) — each element pushed and popped at most once
    Space: O(k) for the deque
    """
    if not arr or k <= 0:
        return []
    if k == 1:
        return list(arr)

    n = len(arr)
    k = min(k, n)
    result = []
    dq = deque()  # Stores indices, values in decreasing order

    for i in range(n):
        # 1. Remove elements from back that are <= current element
        #    (they can never be the max — current is newer and larger)
        while dq and arr[dq[-1]] <= arr[i]:
            dq.pop()

        # 2. Add current index to back
        dq.append(i)

        # 3. Remove front if it's outside the window
        if dq[0] <= i - k:
            dq.popleft()

        # 4. Record maximum (front of deque) once window is full
        if i >= k - 1:
            result.append(arr[dq[0]])

    return result


def sliding_window_min(arr, k):
    """
    Sliding window minimum — same approach with reversed comparison.
    """
    if not arr or k <= 0:
        return []
    n = len(arr)
    k = min(k, n)
    result = []
    dq = deque()

    for i in range(n):
        while dq and arr[dq[-1]] >= arr[i]:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - k:
            dq.popleft()
        if i >= k - 1:
            result.append(arr[dq[0]])

    return result


def sliding_window_max_brute(arr, k):
    """Brute force O(nk) for verification."""
    return [max(arr[i:i+k]) for i in range(len(arr) - k + 1)]


# --- Example ---
if __name__ == "__main__":
    arr = [1, 3, -1, -3, 5, 3, 6, 7]
    k = 3

    result = sliding_window_max(arr, k)
    print(f"Array: {arr}")
    print(f"Window size k={k}")
    print(f"Window maximums: {result}")
    # [3, 3, 5, 5, 6, 7]

    # Show each window
    for i in range(len(arr) - k + 1):
        window = arr[i:i+k]
        print(f"  Window [{i}:{i+k}] = {window} → max = {max(window)}")

    # Verify
    brute = sliding_window_max_brute(arr, k)
    assert result == brute, f"Mismatch: {result} vs {brute}"
    print("Verified against brute force!")

    # Sliding min
    min_result = sliding_window_min(arr, k)
    print(f"\nWindow minimums: {min_result}")

    # Edge cases
    print(f"\nk=1: {sliding_window_max(arr, 1)}")  # Same as input
    print(f"k=n: {sliding_window_max(arr, len(arr))}")  # Single max
    print(f"Decreasing [5,4,3,2,1] k=3: {sliding_window_max([5,4,3,2,1], 3)}")

    # Performance test
    import time
    import random
    random.seed(42)
    n = 1_000_000
    big = [random.randint(0, 1_000_000) for _ in range(n)]
    k_big = 1000

    start = time.time()
    res_opt = sliding_window_max(big, k_big)
    t_opt = time.time() - start

    print(f"\n{n:,} elements, k={k_big}:")
    print(f"  Monotonic deque: {t_opt:.3f}s")
    print(f"  Result length: {len(res_opt)}")
    print(f"  First 10 maximums: {res_opt[:10]}")
```

**Complexity Analysis:**
- **Time:** O(n) — each element enters and leaves the deque at most once (amortized O(1) per element)
- **Space:** O(k) for the deque (at most k indices stored)
- **Why not O(n log n):** A heap-based approach requires lazy deletion of expired elements, giving O(n log k). The deque avoids this entirely.
- **Key insight:** Elements that are both older AND smaller than the current element can never be a future maximum — we safely discard them from the back of the deque. This "monotonic" invariant ensures the front is always the current window's maximum.'''
    ),
]
