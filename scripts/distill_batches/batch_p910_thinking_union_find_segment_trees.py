PAIRS = [
    ("thinking/algorithms", r'''Implement a Union-Find (Disjoint Set Union) data structure with union by rank and path compression. Support operations: find(x), union(x, y), and connected(x, y). Then use it to solve the problem: given n nodes and a list of edges, determine the number of connected components and whether adding a specific edge would create a cycle.''', r'''<think>
Let me think about Union-Find step by step.

The naive approach to tracking connected components would be to run BFS/DFS from each node — that's O(V + E) per query. But Union-Find gives us nearly O(1) amortized per operation with two key optimizations:

1. **Path compression**: During find(), make every node on the path point directly to the root. This flattens the tree structure.
2. **Union by rank**: Always attach the shorter tree under the taller tree's root, keeping the structure balanced.

Without optimizations, find() can be O(n) in the worst case (a long chain). With both optimizations together, the amortized time per operation is O(α(n)) where α is the inverse Ackermann function — effectively constant for all practical inputs.

Let me think about potential pitfalls:
- Off-by-one: nodes could be 0-indexed or 1-indexed
- Self-loops: union(x, x) should be a no-op
- The rank should only increase when two trees of equal rank are merged

I considered using union by size instead of rank, but rank is slightly cleaner since we don't need to track exact subtree sizes unless the problem requires it.
</think>

## Union-Find with Rank and Path Compression

### Implementation

```python
from typing import List, Tuple


class UnionFind:
    """Disjoint Set Union with union by rank and path compression.

    Time Complexity:
        - find: O(α(n)) amortized (inverse Ackermann, effectively O(1))
        - union: O(α(n)) amortized
        - connected: O(α(n)) amortized
    Space Complexity: O(n)
    """

    def __init__(self, n: int) -> None:
        self.parent: List[int] = list(range(n))
        self.rank: List[int] = [0] * n
        self.components: int = n

    def find(self, x: int) -> int:
        """Find root of x with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        """Union two sets. Returns False if already connected (cycle detected)."""
        root_x, root_y = self.find(x), self.find(y)
        if root_x == root_y:
            return False  # Already in the same set — edge would create a cycle

        # Union by rank: attach smaller tree under larger tree
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1

        self.components -= 1
        return True

    def connected(self, x: int, y: int) -> bool:
        """Check if x and y are in the same component."""
        return self.find(x) == self.find(y)


def solve(n: int, edges: List[Tuple[int, int]], query_edge: Tuple[int, int]) -> Tuple[int, bool]:
    """
    Returns (number_of_components, would_query_edge_create_cycle).
    """
    uf = UnionFind(n)
    for u, v in edges:
        uf.union(u, v)

    num_components = uf.components
    creates_cycle = uf.connected(query_edge[0], query_edge[1])

    return num_components, creates_cycle


# --- Tests ---
def test_basic():
    # 5 nodes: 0-1-2 connected, 3-4 connected
    components, cycle = solve(5, [(0, 1), (1, 2), (3, 4)], (0, 2))
    assert components == 2, f"Expected 2, got {components}"
    assert cycle is True, "0 and 2 are already connected"

def test_no_cycle():
    components, cycle = solve(5, [(0, 1), (1, 2), (3, 4)], (2, 3))
    assert components == 2
    assert cycle is False, "2 and 3 are in different components"

def test_single_nodes():
    components, cycle = solve(3, [], (0, 1))
    assert components == 3
    assert cycle is False

test_basic()
test_no_cycle()
test_single_nodes()
print("All Union-Find tests passed!")
```

### Complexity Analysis

| Operation | Time (amortized) | Space |
|-----------|-----------------|-------|
| `find`    | O(α(n))         | O(n)  |
| `union`   | O(α(n))         | O(n)  |
| `connected` | O(α(n))       | O(n)  |
| `solve` (m edges) | O(m·α(n)) | O(n) |

The inverse Ackermann function α(n) grows so slowly that α(2^{2^{2^{65536}}}) = 4, making it effectively O(1) for any conceivable input size.
'''),

    ("thinking/algorithms", r'''Implement a Segment Tree with lazy propagation that supports two operations on an array of integers:
1. Range update: add a value to all elements in a range [l, r]
2. Range query: find the sum of elements in a range [l, r]

Handle up to 10^5 elements and 10^5 operations efficiently.''', r'''<think>
Let me think through segment tree with lazy propagation carefully.

A basic segment tree supports point updates and range queries in O(log n). But range updates naively would require O(n log n) — updating each point individually. Lazy propagation defers the updates, storing a "pending" value at each node and only pushing it down when needed.

Key design decisions:
1. **Array-based vs pointer-based**: Array-based with 4*n size is simpler and faster (cache-friendly). I'll use 1-indexed where node i has children 2i and 2i+1.
2. **Lazy array**: Same size as tree array, stores pending additions to propagate.
3. **Push-down**: Before accessing children, propagate any pending lazy value from parent to children.

Let me think about the push-down mechanics:
- When we push lazy[node] down to children, each child's tree value increases by lazy[node] * (child's range length)
- Each child's lazy value accumulates the parent's lazy value
- Then clear the parent's lazy

Edge cases to handle:
- Query/update range fully contains the node's range: apply directly, don't recurse
- Query/update range doesn't overlap at all: return 0 / do nothing
- Partial overlap: push down lazy, recurse into both children

I initially thought about using a recursive approach vs iterative. Recursive is cleaner and easier to get right for lazy propagation. The stack depth is O(log n) which is fine for n ≤ 10^5.
</think>

## Segment Tree with Lazy Propagation (Range Add + Range Sum)

```python
from typing import List, Optional


class LazySegmentTree:
    """Segment tree supporting range-add updates and range-sum queries.

    Time Complexity: O(log n) per operation
    Space Complexity: O(n)
    """

    def __init__(self, data: List[int]) -> None:
        self.n = len(data)
        self.tree: List[int] = [0] * (4 * self.n)
        self.lazy: List[int] = [0] * (4 * self.n)
        if self.n > 0:
            self._build(data, 1, 0, self.n - 1)

    def _build(self, data: List[int], node: int, start: int, end: int) -> None:
        if start == end:
            self.tree[node] = data[start]
            return
        mid = (start + end) // 2
        self._build(data, 2 * node, start, mid)
        self._build(data, 2 * node + 1, mid + 1, end)
        self.tree[node] = self.tree[2 * node] + self.tree[2 * node + 1]

    def _push_down(self, node: int, start: int, end: int) -> None:
        """Propagate lazy value to children."""
        if self.lazy[node] != 0:
            mid = (start + end) // 2
            left, right = 2 * node, 2 * node + 1
            # Update children's tree values
            self.tree[left] += self.lazy[node] * (mid - start + 1)
            self.tree[right] += self.lazy[node] * (end - mid)
            # Accumulate lazy to children
            self.lazy[left] += self.lazy[node]
            self.lazy[right] += self.lazy[node]
            self.lazy[node] = 0

    def update_range(self, l: int, r: int, val: int) -> None:
        """Add val to every element in [l, r] (0-indexed)."""
        self._update(1, 0, self.n - 1, l, r, val)

    def _update(self, node: int, start: int, end: int, l: int, r: int, val: int) -> None:
        if r < start or end < l:
            return
        if l <= start and end <= r:
            self.tree[node] += val * (end - start + 1)
            self.lazy[node] += val
            return
        self._push_down(node, start, end)
        mid = (start + end) // 2
        self._update(2 * node, start, mid, l, r, val)
        self._update(2 * node + 1, mid + 1, end, l, r, val)
        self.tree[node] = self.tree[2 * node] + self.tree[2 * node + 1]

    def query_range(self, l: int, r: int) -> int:
        """Return sum of elements in [l, r] (0-indexed)."""
        return self._query(1, 0, self.n - 1, l, r)

    def _query(self, node: int, start: int, end: int, l: int, r: int) -> int:
        if r < start or end < l:
            return 0
        if l <= start and end <= r:
            return self.tree[node]
        self._push_down(node, start, end)
        mid = (start + end) // 2
        return (self._query(2 * node, start, mid, l, r) +
                self._query(2 * node + 1, mid + 1, end, l, r))


# --- Tests ---
def test_basic():
    st = LazySegmentTree([1, 3, 5, 7, 9, 11])
    assert st.query_range(1, 3) == 15  # 3 + 5 + 7
    st.update_range(1, 3, 10)  # Add 10 to indices 1..3
    assert st.query_range(1, 3) == 45  # 13 + 15 + 17
    assert st.query_range(0, 5) == 66  # 1 + 13 + 15 + 17 + 9 + 11

def test_full_range():
    st = LazySegmentTree([0, 0, 0, 0])
    st.update_range(0, 3, 5)
    assert st.query_range(0, 3) == 20
    st.update_range(2, 3, -3)
    assert st.query_range(0, 3) == 14  # 5+5+2+2

def test_single_element():
    st = LazySegmentTree([42])
    assert st.query_range(0, 0) == 42
    st.update_range(0, 0, 8)
    assert st.query_range(0, 0) == 50

test_basic()
test_full_range()
test_single_element()
print("All Lazy Segment Tree tests passed!")
```

### Complexity

| Operation       | Time      | Space |
|----------------|-----------|-------|
| Build          | O(n)      | O(n)  |
| Range update   | O(log n)  | —     |
| Range query    | O(log n)  | —     |

With n = 10^5 and 10^5 operations, total work is O(n + q·log n) ≈ 10^5 + 10^5 · 17 ≈ 1.8 × 10^6, which is very fast.
'''),

    ("thinking/algorithms", r'''Count the number of inversions in an array using a Binary Indexed Tree (Fenwick Tree). An inversion is a pair (i, j) where i < j but arr[i] > arr[j]. The array can contain up to 10^5 elements with values up to 10^6.''', r'''<think>
Let me think about counting inversions.

**Brute force**: Check all pairs — O(n^2). Too slow for n = 10^5.

**Merge sort approach**: Classic O(n log n) solution by counting split inversions during merge. Works well but let me think about the BIT approach since that's what's asked.

**BIT approach**: Process the array from right to left. For each element arr[i], the number of inversions it contributes is the count of elements already processed (to its right) that are smaller than arr[i]. That count is a prefix sum query on the BIT.

Wait, let me reconsider the direction. If I process left to right:
- For each arr[i], I want to know how many elements already inserted are greater than arr[i]
- That's: (total inserted so far) - (count of elements ≤ arr[i])
- Count of elements ≤ arr[i] is a prefix sum query: query(arr[i])

So the algorithm is:
1. For i = 0 to n-1:
   - inversions += i - query(arr[i])  (i elements inserted so far, query gives count ≤ arr[i])
   - update(arr[i], +1)

But values up to 10^6 means BIT size is 10^6. That's fine memory-wise (4MB).

Alternatively, I could coordinate compress to bring values down to range [1, n]. That saves memory and is better practice. Let me do both — implement with coordinate compression.

One tricky part: duplicate values. With coordinate compression, I need to make sure equal elements don't count as inversions. Since I'm using ≤ in the prefix query, equal elements are correctly excluded from the inversion count.
</think>

## Counting Inversions with a Fenwick Tree (BIT)

### Approach

Process elements left to right. For each element at index `i`, the number of elements already placed that are **greater** than `arr[i]` equals `i - prefix_count(arr[i])`. We use coordinate compression to handle large values efficiently.

```python
from typing import List


class FenwickTree:
    """Binary Indexed Tree for prefix sum queries and point updates.

    1-indexed internally. Supports:
        - point update: add a value at position i
        - prefix query: sum of values in [1, i]
    """

    def __init__(self, size: int) -> None:
        self.n = size
        self.tree: List[int] = [0] * (size + 1)

    def update(self, i: int, delta: int = 1) -> None:
        """Add delta at position i (1-indexed)."""
        while i <= self.n:
            self.tree[i] += delta
            i += i & (-i)  # Move to parent

    def query(self, i: int) -> int:
        """Return prefix sum [1, i]."""
        total = 0
        while i > 0:
            total += self.tree[i]
            i -= i & (-i)  # Move to predecessor
        return total


def count_inversions(arr: List[int]) -> int:
    """Count inversions using a Fenwick tree with coordinate compression.

    Time Complexity: O(n log n)
    Space Complexity: O(n)
    """
    if len(arr) <= 1:
        return 0

    # Coordinate compression: map values to [1, m]
    sorted_unique = sorted(set(arr))
    rank = {v: i + 1 for i, v in enumerate(sorted_unique)}

    m = len(sorted_unique)
    bit = FenwickTree(m)
    inversions = 0

    for i, val in enumerate(arr):
        r = rank[val]
        # Elements already inserted that are <= val
        leq_count = bit.query(r)
        # Elements already inserted that are > val
        inversions += i - leq_count
        bit.update(r)

    return inversions


# --- Tests ---
def test_sorted():
    assert count_inversions([1, 2, 3, 4, 5]) == 0

def test_reverse_sorted():
    # Fully reversed: n*(n-1)/2 = 10 inversions
    assert count_inversions([5, 4, 3, 2, 1]) == 10

def test_general():
    # [2, 4, 1, 3, 5]
    # Inversions: (2,1), (4,1), (4,3) = 3
    assert count_inversions([2, 4, 1, 3, 5]) == 3

def test_duplicates():
    # [2, 1, 2, 1] -> inversions: (2,1), (2,1), (2,1) = 3
    # Pairs: (0,1), (0,3), (2,3)
    assert count_inversions([2, 1, 2, 1]) == 3

def test_empty():
    assert count_inversions([]) == 0

test_sorted()
test_reverse_sorted()
test_general()
test_duplicates()
test_empty()
print("All inversion counting tests passed!")
```

### Complexity Analysis

| Step                    | Time       | Space  |
|------------------------|------------|--------|
| Coordinate compression | O(n log n) | O(n)   |
| Fenwick operations     | O(n log n) | O(n)   |
| **Total**              | **O(n log n)** | **O(n)** |

Each of the n elements requires one `query` and one `update`, each O(log m) where m ≤ n. The coordinate compression step sorts unique values in O(n log n). This easily handles n = 10^5 within time limits.
'''),

    ("thinking/algorithms", r'''Implement a Sparse Table for Range Minimum Query (RMQ). Given an array of n integers, preprocess it so that any range minimum query [l, r] can be answered in O(1) time. The array is static (no updates).''', r'''<think>
The Sparse Table is one of my favorite data structures for static RMQ because it achieves O(1) query time after O(n log n) preprocessing.

The key insight is the **overlap-friendly** property of the min function: min(A ∪ B) = min(min(A), min(B)) even if A and B overlap. So we can answer a range query using two precomputed ranges that together cover [l, r], even if they overlap.

**Preprocessing:**
- Build a table `sp[k][i]` = minimum of arr[i..i+2^k-1]
- Base case: sp[0][i] = arr[i]
- Recurrence: sp[k][i] = min(sp[k-1][i], sp[k-1][i + 2^(k-1)])
- We need k up to floor(log2(n))

**Query [l, r]:**
- Compute k = floor(log2(r - l + 1))
- Answer = min(sp[k][l], sp[k][r - 2^k + 1])
- These two ranges of length 2^k cover [l, r] entirely (they may overlap, but that's fine for min)

I need to precompute log values too. I can either use math.log2 or build a lookup table. A lookup table avoids floating-point issues.

Alternative considered: Segment tree gives O(log n) per query. Sparse table wins for static arrays because O(1) query. The tradeoff is that sparse table doesn't support updates (would need to rebuild in O(n log n)).

Space is O(n log n) which for n = 10^5 is about 1.7 × 10^6 entries — very manageable.
</think>

## Sparse Table for O(1) Range Minimum Queries

```python
import math
from typing import List, Tuple


class SparseTable:
    """Sparse Table for static Range Minimum Query.

    Preprocessing: O(n log n) time and space
    Query: O(1) time
    """

    def __init__(self, arr: List[int]) -> None:
        self.n = len(arr)
        if self.n == 0:
            self.table = []
            self.log = []
            return

        # Precompute floor(log2(i)) for i in [0, n]
        self.log: List[int] = [0] * (self.n + 1)
        for i in range(2, self.n + 1):
            self.log[i] = self.log[i // 2] + 1

        self.max_k = self.log[self.n] + 1

        # table[k][i] = min of arr[i .. i + 2^k - 1]
        self.table: List[List[int]] = [[0] * self.n for _ in range(self.max_k)]
        self.table[0] = arr[:]

        for k in range(1, self.max_k):
            half = 1 << (k - 1)
            for i in range(self.n - (1 << k) + 1):
                self.table[k][i] = min(
                    self.table[k - 1][i],
                    self.table[k - 1][i + half]
                )

    def query(self, l: int, r: int) -> int:
        """Return minimum in arr[l..r] (0-indexed, inclusive). O(1)."""
        length = r - l + 1
        k = self.log[length]
        return min(self.table[k][l], self.table[k][r - (1 << k) + 1])


# --- Tests ---
def test_basic():
    arr = [1, 3, 2, 7, 9, 11, 3, 5, 0, 6]
    st = SparseTable(arr)
    assert st.query(0, 9) == 0   # min of entire array
    assert st.query(0, 2) == 1   # min(1, 3, 2)
    assert st.query(3, 5) == 7   # min(7, 9, 11)
    assert st.query(6, 8) == 0   # min(3, 5, 0)
    assert st.query(4, 4) == 9   # single element

def test_all_same():
    st = SparseTable([5, 5, 5, 5])
    assert st.query(0, 3) == 5
    assert st.query(1, 2) == 5

def test_decreasing():
    arr = [10, 8, 6, 4, 2]
    st = SparseTable(arr)
    assert st.query(0, 4) == 2
    assert st.query(0, 1) == 8
    assert st.query(0, 0) == 10

test_basic()
test_all_same()
test_decreasing()
print("All Sparse Table RMQ tests passed!")
```

### How the O(1) Query Works

For query `[l, r]`, let `k = floor(log2(r - l + 1))`. Then:
- Interval 1: `[l, l + 2^k - 1]`
- Interval 2: `[r - 2^k + 1, r]`

Both intervals have length `2^k`, and together they cover `[l, r]`. Since `min` is idempotent over overlapping ranges, the answer is simply `min(table[k][l], table[k][r - 2^k + 1])`.

### Complexity Summary

| Phase         | Time       | Space      |
|--------------|------------|------------|
| Preprocessing | O(n log n) | O(n log n) |
| Query         | O(1)       | —          |

For n = 10^5: preprocessing builds ~1.7M entries, each query is two lookups and a min.
'''),

    ("thinking/algorithms", r'''Implement a Persistent Segment Tree that supports two operations:
1. Point update on a version, creating a new version
2. Range sum query on any historical version

This should allow querying any past state of the array without storing full copies.''', r"""<think>
A persistent segment tree is an elegant application of the path-copying technique. When we update one element, only O(log n) nodes on the path from root to leaf change. Instead of modifying them in place, we create new copies of just those nodes, with the rest of the tree shared.

Let me think about the implementation:

**Node-based approach** (necessary for persistence — array-based won't work since we need to share subtrees):
- Each node has: value, left_child, right_child
- We store an array of root references, one per version

**Point update creating new version:**
- Walk from root to the leaf containing the update position
- Create new copies of each node on this path
- The new copies point to the same children as the originals, except at the level where we diverge
- O(log n) new nodes created per update

**Range sum query on any version:**
- Use the root for that version, then standard segment tree range query
- O(log n) per query

Space analysis:
- Initial build: O(n) nodes (actually 2n - 1 for a full segment tree)
- Each update: O(log n) new nodes
- After q updates: O(n + q log n) total nodes

I need to be careful with Python's recursion limit for large n. For n = 10^5, depth is ~17, so it's fine.

I considered using an implicit/dynamic segment tree style with dictionaries, but explicit node objects are clearer and more efficient.
</think>

## Persistent Segment Tree

A persistent segment tree preserves all historical versions by creating O(log n) new nodes per update, sharing the rest of the tree structure.

```python
from typing import List, Optional


class Node:
    '''Segment tree node with persistent (immutable) structure.'''
    __slots__ = ['val', 'left', 'right']

    def __init__(self, val: int = 0, left: Optional['Node'] = None,
                 right: Optional['Node'] = None) -> None:
        self.val = val
        self.left = left
        self.right = right


class PersistentSegTree:
    '''Persistent Segment Tree supporting versioned point updates and range sum queries.

    Time Complexity:
        - build: O(n)
        - update (new version): O(log n)
        - query (any version): O(log n)
    Space Complexity: O(n + q * log n) for q updates
    '''

    def __init__(self, data: List[int]) -> None:
        self.n = len(data)
        self.roots: List[Node] = []
        if self.n > 0:
            self.roots.append(self._build(data, 0, self.n - 1))
        else:
            self.roots.append(Node())

    def _build(self, data: List[int], start: int, end: int) -> Node:
        if start == end:
            return Node(val=data[start])
        mid = (start + end) // 2
        left = self._build(data, start, mid)
        right = self._build(data, mid + 1, end)
        return Node(val=left.val + right.val, left=left, right=right)

    def update(self, version: int, idx: int, val: int) -> int:
        '''Create a new version by setting arr[idx] = val based on given version.

        Returns the new version number.
        '''
        new_root = self._update(self.roots[version], 0, self.n - 1, idx, val)
        self.roots.append(new_root)
        return len(self.roots) - 1

    def _update(self, node: Node, start: int, end: int, idx: int, val: int) -> Node:
        if start == end:
            return Node(val=val)
        mid = (start + end) // 2
        if idx <= mid:
            new_left = self._update(node.left, start, mid, idx, val)
            return Node(val=new_left.val + node.right.val,
                        left=new_left, right=node.right)
        else:
            new_right = self._update(node.right, mid + 1, end, idx, val)
            return Node(val=node.left.val + new_right.val,
                        left=node.left, right=new_right)

    def query(self, version: int, l: int, r: int) -> int:
        '''Range sum query on a specific version. O(log n).'''
        return self._query(self.roots[version], 0, self.n - 1, l, r)

    def _query(self, node: Optional[Node], start: int, end: int, l: int, r: int) -> int:
        if node is None or r < start or end < l:
            return 0
        if l <= start and end <= r:
            return node.val
        mid = (start + end) // 2
        return (self._query(node.left, start, mid, l, r) +
                self._query(node.right, mid + 1, end, l, r))


# --- Tests ---
def test_persistence():
    data = [1, 2, 3, 4, 5]
    pst = PersistentSegTree(data)

    # Version 0: [1, 2, 3, 4, 5]
    assert pst.query(0, 0, 4) == 15
    assert pst.query(0, 1, 3) == 9  # 2 + 3 + 4

    # Version 1: set index 2 to 10 -> [1, 2, 10, 4, 5]
    v1 = pst.update(0, 2, 10)
    assert pst.query(v1, 0, 4) == 22
    assert pst.query(v1, 1, 3) == 16  # 2 + 10 + 4

    # Version 0 is unchanged
    assert pst.query(0, 0, 4) == 15

    # Version 2: from version 1, set index 0 to 100 -> [100, 2, 10, 4, 5]
    v2 = pst.update(v1, 0, 100)
    assert pst.query(v2, 0, 4) == 121
    assert pst.query(v1, 0, 4) == 22  # v1 unchanged
    assert pst.query(0, 0, 4) == 15   # v0 unchanged

def test_branching_versions():
    pst = PersistentSegTree([0, 0, 0])
    # Branch from v0 in two different ways
    v1 = pst.update(0, 0, 5)   # [5, 0, 0]
    v2 = pst.update(0, 0, 99)  # [99, 0, 0]
    assert pst.query(v1, 0, 2) == 5
    assert pst.query(v2, 0, 2) == 99

test_persistence()
test_branching_versions()
print("All Persistent Segment Tree tests passed!")
```

### Space Complexity Detail

Each update creates exactly `ceil(log2(n))` new nodes, reusing all other subtrees. For n = 10^5 and q = 10^5 updates: total nodes ≈ 2 × 10^5 + 10^5 × 17 ≈ 1.9 × 10^6 — very manageable.
"""),
]
