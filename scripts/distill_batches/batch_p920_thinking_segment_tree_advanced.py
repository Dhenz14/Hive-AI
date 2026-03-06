PAIRS = [
    ("thinking/algorithms", r'''Implement a segment tree with lazy propagation for range updates and range queries. Support both range addition (add a value to all elements in a range) and range sum queries.''', r'''<think>
I need a segment tree that supports range addition and range sum queries. A basic segment tree handles point updates in O(log n), but if I want to add a value to an entire range, that would require updating every leaf individually -- O(n) in the worst case. That defeats the purpose.

The solution is lazy propagation. The idea: when I need to update a range and the current node's range falls entirely within the update range, I just update this node's sum and store a "pending" tag. I do NOT recurse into children. This is the key -- we defer work until it is actually needed.

But wait, what happens when a later query or update needs to access the children of a node with a pending tag? That is where "push down" comes in. Before recursing into children, I check if the current node has a pending lazy value. If so, I push it down: apply it to both children's sums (adjusting by the number of elements each child covers) and transfer the lazy tag to them. Then clear the current node's lazy tag.

I initially worried about correctness -- what if multiple range updates overlap? But since lazy values for addition are additive, we just accumulate them: node.lazy += val. Each push-down correctly transfers the accumulated pending value to children.

For the sum update formula: if adding val to a node covering [nl, nr], the sum increases by val * (nr - nl + 1). This is correct because every element in that range increases by val.

Hmm, one subtlety: the order of operations in the update function matters. If the node is fully covered, we update and return (no push down needed). If partially covered, we must push down FIRST, then recurse into children, then recalculate the current node's sum from its children.

Time: O(log n) per update and query.
Space: O(n) for the tree and lazy arrays.
</think>

**Segment Tree with Lazy Propagation**

```python
class LazySegTree:
    """Segment tree with lazy propagation for range add + range sum."""

    def __init__(self, data):
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
        if self.lazy[node] != 0:
            mid = (start + end) // 2
            left, right = 2 * node, 2 * node + 1
            val = self.lazy[node]

            self.tree[left] += val * (mid - start + 1)
            self.lazy[left] += val

            self.tree[right] += val * (end - mid)
            self.lazy[right] += val

            self.lazy[node] = 0

    def range_add(self, l, r, val):
        """Add val to all elements in [l, r]."""
        self._update(1, 0, self.n - 1, l, r, val)

    def _update(self, node, start, end, l, r, val):
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

    def range_sum(self, l, r):
        """Query sum of elements in [l, r]."""
        return self._query(1, 0, self.n - 1, l, r)

    def _query(self, node, start, end, l, r):
        if r < start or end < l:
            return 0
        if l <= start and end <= r:
            return self.tree[node]
        self._push_down(node, start, end)
        mid = (start + end) // 2
        return (self._query(2 * node, start, mid, l, r) +
                self._query(2 * node + 1, mid + 1, end, l, r))


# Example
data = [1, 3, 5, 7, 9, 11]
st = LazySegTree(data)

print(f"Initial array: {data}")
print(f"Sum [0,5]: {st.range_sum(0, 5)}")
print(f"Sum [1,3]: {st.range_sum(1, 3)}")

# Range add: add 10 to indices [1, 4]
st.range_add(1, 4, 10)
print(f"\nAfter adding 10 to [1,4]:")
print(f"Sum [0,5]: {st.range_sum(0, 5)}")
print(f"Sum [1,3]: {st.range_sum(1, 3)}")

# Verify with brute force
arr = data[:]
for i in range(1, 5):
    arr[i] += 10
print(f"Expected array: {arr}")
print(f"Expected sum [0,5]: {sum(arr)}")
print(f"Expected sum [1,3]: {sum(arr[1:4])}")
```

**Lazy Propagation Key Principle:**
- Delay work until it is absolutely needed
- A node with lazy != 0 means: "my value is correct, but my children have not been updated yet"
- push_down transfers the pending update to children

**Complexity:**
- Range update: O(log n)
- Range query: O(log n)
- Space: O(n)'''),

    ("thinking/algorithms", r'''Explain and implement a persistent segment tree that supports point updates while preserving all previous versions. Given an array, allow querying the sum of any range on any historical version.''', r'''<think>
I need a segment tree that preserves all historical versions after updates. The naive approach would be to copy the entire tree before each update, but that is O(n) per update -- way too expensive.

The key insight: when I update a single position, only O(log n) nodes on the root-to-leaf path actually change. Everything else stays the same. So instead of copying the whole tree, I only create new copies of the changed nodes and reuse (share) all the unchanged subtrees from the previous version.

This is sometimes called "path copying" -- each update creates a new path from root to leaf, with the new root becoming the entry point for the new version. The old root still points to the old structure, completely unchanged.

I initially considered using Python objects with pointers for the tree nodes, but that has too much overhead. An array-based node pool is much better: each node is stored as [left_child_index, right_child_index, value] in a flat list, and we just append new nodes as needed.

The roots[] array stores the root node index for each version. To query version v, I start from roots[v] and traverse exactly like a normal segment tree.

Wait, what about memory? Each update creates O(log n) new nodes. After Q updates, total nodes = O(n + Q * log n). For n = 10^5 and Q = 10^5, that is roughly 10^5 + 10^5 * 17 = ~1.8 million nodes. That is very manageable.

Hmm, one thing to be careful about: when creating a new node during update, I need to correctly link it to the unchanged child from the old tree AND the newly created child. The recursive structure handles this naturally -- at each level, one child is new (recursive call) and the other is reused from the old version.
</think>

**Persistent Segment Tree**

```python
class PersistentSegTree:
    """Persistent segment tree with point update and range sum query."""

    def __init__(self, data):
        self.n = len(data)
        # Node pool: [left_child, right_child, value]
        self.nodes = []
        self.roots = []

        # Build initial tree
        root = self._build(data, 0, self.n - 1)
        self.roots.append(root)

    def _new_node(self, val=0, left=-1, right=-1):
        idx = len(self.nodes)
        self.nodes.append([left, right, val])
        return idx

    def _build(self, data, lo, hi):
        if lo == hi:
            return self._new_node(val=data[lo])
        mid = (lo + hi) // 2
        left = self._build(data, lo, mid)
        right = self._build(data, mid + 1, hi)
        return self._new_node(
            val=self.nodes[left][2] + self.nodes[right][2],
            left=left, right=right
        )

    def update(self, version, pos, new_val):
        """
        Create new version with data[pos] = new_val.

        Args:
            version: base version index
            pos: position to update
            new_val: new value
        Returns:
            new version index
        """
        new_root = self._update(self.roots[version], 0, self.n - 1,
                                pos, new_val)
        self.roots.append(new_root)
        return len(self.roots) - 1

    def _update(self, node, lo, hi, pos, val):
        if lo == hi:
            return self._new_node(val=val)
        left, right, _ = self.nodes[node]
        mid = (lo + hi) // 2
        if pos <= mid:
            new_left = self._update(left, lo, mid, pos, val)
            new_right = right
        else:
            new_left = left
            new_right = self._update(right, mid + 1, hi, pos, val)
        total = self.nodes[new_left][2] + self.nodes[new_right][2]
        return self._new_node(val=total, left=new_left, right=new_right)

    def query(self, version, l, r):
        """Range sum query on a specific version."""
        return self._query(self.roots[version], 0, self.n - 1, l, r)

    def _query(self, node, lo, hi, l, r):
        if r < lo or hi < l:
            return 0
        if l <= lo and hi <= r:
            return self.nodes[node][2]
        left, right, _ = self.nodes[node]
        mid = (lo + hi) // 2
        return (self._query(left, lo, mid, l, r) +
                self._query(right, mid + 1, hi, l, r))


# Example
data = [1, 2, 3, 4, 5]
pst = PersistentSegTree(data)

print(f"Version 0 (original): {data}")
print(f"  Sum [0,4]: {pst.query(0, 0, 4)}")
print(f"  Sum [1,3]: {pst.query(0, 1, 3)}")

# Version 1: set index 2 to 10
v1 = pst.update(0, 2, 10)
print(f"\nVersion 1 (index 2 = 10):")
print(f"  Sum [0,4]: {pst.query(v1, 0, 4)}")
print(f"  Sum [1,3]: {pst.query(v1, 1, 3)}")

# Version 2: set index 0 to 100 (based on version 1)
v2 = pst.update(v1, 0, 100)
print(f"\nVersion 2 (index 0 = 100):")
print(f"  Sum [0,4]: {pst.query(v2, 0, 4)}")

# Original version still intact
print(f"\nVersion 0 still intact:")
print(f"  Sum [0,4]: {pst.query(0, 0, 4)}")

print(f"\nTotal nodes allocated: {len(pst.nodes)}")
print(f"Nodes for plain tree: {2 * len(data) - 1}")
```

**Path Copying Principle:**
- Update at position p only changes O(log n) nodes on the root-to-leaf path
- Create new copies of changed nodes, reuse all other subtrees
- Each version has its own root, but shares most structure with other versions

**Complexity:**
- Build: O(n) time and space
- Update: O(log n) time and space (new nodes per update)
- Query: O(log n) time
- Total space after Q updates: O(n + Q * log n)'''),

    ("thinking/algorithms", r'''Implement a 2D segment tree (segment tree of segment trees) that supports point updates and rectangle sum queries on a 2D grid.''', r'''<think>
I need a 2D segment tree for point updates and rectangle sum queries. My first thought is: could I just flatten the 2D grid into 1D? No, because a rectangle query in 2D does not correspond to a contiguous range in any simple 1D ordering.

The standard approach is a "segment tree of segment trees" -- the outer tree segments rows, and each outer node contains an inner segment tree that segments columns. So a node covering rows [r1, r2] with inner node covering columns [c1, c2] stores the sum of the rectangle [r1..r2] x [c1..c2].

For a point update at (r, c): I walk down the outer tree to row r, and at every outer node on the path, I update column c in that node's inner tree. That is O(log n) outer nodes, each doing an O(log m) inner update, giving O(log n * log m) total.

For a rectangle query: decompose rows [r1, r2] into O(log n) outer nodes, and at each one query columns [c1, c2] in O(log m). Total: O(log n * log m).

Wait, there is a subtlety with updates at internal (non-leaf) outer nodes. When I update a leaf outer node's inner tree directly with the new value, what do I put in the parent outer node's inner tree? I cannot just set it to the new value -- the parent covers multiple rows. I need to sum the corresponding values from both children. So for internal outer nodes, the inner tree value at column c equals the sum of the left child's and right child's values at column c.

This means the inner tree update at an internal outer node looks different from a leaf: at a leaf, I set the value directly; at an internal node, I recompute from children. I will pass an is_leaf_row flag to handle this.

Space: each of the 4*n outer nodes has a 4*m inner tree, so total is O(16 * n * m). That is a large constant factor but acceptable for moderate grid sizes.

Time: O(log n * log m) for both update and query.
</think>

**2D Segment Tree -- Point Update + Rectangle Sum Query**

```python
class SegTree2D:
    """2D segment tree for point update and rectangle sum queries."""

    def __init__(self, grid):
        if not grid or not grid[0]:
            self.rows = self.cols = 0
            return
        self.rows = len(grid)
        self.cols = len(grid[0])
        # tree[outer_node] = inner segment tree (array of size 4*cols)
        self.tree = [[0] * (4 * self.cols) for _ in range(4 * self.rows)]
        self._build_y(grid, 1, 0, self.rows - 1)

    def _build_x(self, oy, ox, lx, rx, grid_row_or_none, row_lo, row_hi):
        """Build inner tree for outer node oy."""
        if lx == rx:
            if row_lo == row_hi:
                self.tree[oy][ox] = grid_row_or_none[lx]
            else:
                self.tree[oy][ox] = (self.tree[2 * oy][ox] +
                                      self.tree[2 * oy + 1][ox])
            return
        mid = (lx + rx) // 2
        self._build_x(oy, 2*ox, lx, mid, grid_row_or_none, row_lo, row_hi)
        self._build_x(oy, 2*ox+1, mid+1, rx, grid_row_or_none, row_lo, row_hi)
        self.tree[oy][ox] = self.tree[oy][2*ox] + self.tree[oy][2*ox+1]

    def _build_y(self, grid, oy, lo, hi):
        if lo == hi:
            self._build_x(oy, 1, 0, self.cols - 1, grid[lo], lo, hi)
            return
        mid = (lo + hi) // 2
        self._build_y(grid, 2 * oy, lo, mid)
        self._build_y(grid, 2 * oy + 1, mid + 1, hi)
        self._build_x(oy, 1, 0, self.cols - 1, None, lo, hi)

    def _update_x(self, oy, ox, lx, rx, col, val, is_leaf_row):
        if lx == rx:
            if is_leaf_row:
                self.tree[oy][ox] = val
            else:
                self.tree[oy][ox] = (self.tree[2*oy][ox] +
                                      self.tree[2*oy+1][ox])
            return
        mid = (lx + rx) // 2
        if col <= mid:
            self._update_x(oy, 2*ox, lx, mid, col, val, is_leaf_row)
        else:
            self._update_x(oy, 2*ox+1, mid+1, rx, col, val, is_leaf_row)
        self.tree[oy][ox] = self.tree[oy][2*ox] + self.tree[oy][2*ox+1]

    def update(self, row, col, val):
        """Set grid[row][col] = val."""
        self._update_y(1, 0, self.rows - 1, row, col, val)

    def _update_y(self, oy, lo, hi, row, col, val):
        if lo == hi:
            self._update_x(oy, 1, 0, self.cols - 1, col, val, True)
            return
        mid = (lo + hi) // 2
        if row <= mid:
            self._update_y(2 * oy, lo, mid, row, col, val)
        else:
            self._update_y(2 * oy + 1, mid + 1, hi, row, col, val)
        self._update_x(oy, 1, 0, self.cols - 1, col, val, False)

    def query(self, r1, c1, r2, c2):
        """Sum of elements in rectangle [r1..r2] x [c1..c2]."""
        return self._query_y(1, 0, self.rows - 1, r1, r2, c1, c2)

    def _query_y(self, oy, lo, hi, r1, r2, c1, c2):
        if r2 < lo or hi < r1:
            return 0
        if r1 <= lo and hi <= r2:
            return self._query_x(oy, 1, 0, self.cols - 1, c1, c2)
        mid = (lo + hi) // 2
        return (self._query_y(2*oy, lo, mid, r1, r2, c1, c2) +
                self._query_y(2*oy+1, mid+1, hi, r1, r2, c1, c2))

    def _query_x(self, oy, ox, lx, rx, c1, c2):
        if c2 < lx or rx < c1:
            return 0
        if c1 <= lx and rx <= c2:
            return self.tree[oy][ox]
        mid = (lx + rx) // 2
        return (self._query_x(oy, 2*ox, lx, mid, c1, c2) +
                self._query_x(oy, 2*ox+1, mid+1, rx, c1, c2))


# Example
grid = [
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9],
]
st = SegTree2D(grid)
print(f"Sum [0,0]->[2,2]: {st.query(0, 0, 2, 2)}")  # 45
print(f"Sum [0,0]->[1,1]: {st.query(0, 0, 1, 1)}")  # 12
print(f"Sum [1,1]->[2,2]: {st.query(1, 1, 2, 2)}")  # 28

st.update(1, 1, 50)  # set grid[1][1] = 50
print(f"\nAfter grid[1][1] = 50:")
print(f"Sum [0,0]->[2,2]: {st.query(0, 0, 2, 2)}")  # 90
print(f"Sum [1,1]->[1,1]: {st.query(1, 1, 1, 1)}")  # 50
```

**Complexity:**
- Point update: O(log n * log m)
- Rectangle query: O(log n * log m)
- Space: O(n * m) with constant factor overhead'''),

    ("thinking/algorithms", r'''Implement a merge sort tree: a segment tree where each node stores the sorted array of elements in its range. Support queries like "count of elements <= k in range [l, r]" efficiently.''', r'''<think>
I need to answer queries like "how many elements <= k in range [l, r]?" efficiently. A regular segment tree stores aggregates like sum or max, but not order statistics.

I initially considered using a persistent segment tree over value ranges (the "online" approach for kth smallest), but that is complex. A simpler alternative: store the sorted array of elements at each segment tree node. This is called a merge sort tree because building it is exactly like merge sort -- each internal node merges its children's sorted arrays.

Storage analysis: each element appears in O(log n) nodes (one per level of the tree), so total storage is O(n log n). Building takes O(n log n) time, same as merge sort.

For "count elements <= k in [l, r]": decompose [l, r] into O(log n) segment tree nodes. At each node, binary search for k in its sorted array -- that is O(log n) per node. Total: O(log^2 n).

For "kth smallest in [l, r]": I could binary search on the answer value! If I pick a candidate value mid, I can use count_leq(l, r, mid) to check how many elements are <= mid. If count >= k, the answer is <= mid; otherwise it is > mid. This binary search adds another O(log n) factor, giving O(log^3 n).

Hmm, could I do better? With fractional cascading, the binary search at each node can be reduced to O(1), bringing count_leq down to O(log n) and kth_smallest to O(log^2 n). But fractional cascading is tricky to implement correctly, so I will stick with the simpler version for now.

Wait, for the kth smallest binary search, I need to be careful about what values I search over. I should search over the actual distinct values in the range, not arbitrary integers. I will extract and sort the unique values from data[l:r+1] and binary search over those.
</think>

**Merge Sort Tree -- Count and Kth Smallest in Range**

```python
from bisect import bisect_right, bisect_left


class MergeSortTree:
    """Segment tree with sorted arrays for range order statistics."""

    def __init__(self, data):
        self.n = len(data)
        self.data = data[:]
        self.tree = [[] for _ in range(4 * self.n)]
        if self.n > 0:
            self._build(1, 0, self.n - 1)

    def _build(self, node, lo, hi):
        if lo == hi:
            self.tree[node] = [self.data[lo]]
            return
        mid = (lo + hi) // 2
        self._build(2 * node, lo, mid)
        self._build(2 * node + 1, mid + 1, hi)
        # Merge two sorted arrays
        self.tree[node] = self._merge(
            self.tree[2 * node], self.tree[2 * node + 1]
        )

    def _merge(self, a, b):
        result = []
        i = j = 0
        while i < len(a) and j < len(b):
            if a[i] <= b[j]:
                result.append(a[i])
                i += 1
            else:
                result.append(b[j])
                j += 1
        result.extend(a[i:])
        result.extend(b[j:])
        return result

    def count_leq(self, l, r, k):
        """Count elements <= k in range [l, r]."""
        return self._count(1, 0, self.n - 1, l, r, k)

    def _count(self, node, lo, hi, l, r, k):
        if r < lo or hi < l:
            return 0
        if l <= lo and hi <= r:
            return bisect_right(self.tree[node], k)
        mid = (lo + hi) // 2
        return (self._count(2 * node, lo, mid, l, r, k) +
                self._count(2 * node + 1, mid + 1, hi, l, r, k))

    def count_range(self, l, r, lo_val, hi_val):
        """Count elements in [lo_val, hi_val] within range [l, r]."""
        return self.count_leq(l, r, hi_val) - self.count_leq(l, r, lo_val - 1)

    def kth_smallest(self, l, r, k):
        """Find kth smallest element in range [l, r] (1-indexed k)."""
        # Binary search on the answer
        sorted_all = sorted(set(self.data[l:r + 1]))
        lo_idx, hi_idx = 0, len(sorted_all) - 1

        while lo_idx < hi_idx:
            mid_idx = (lo_idx + hi_idx) // 2
            count = self.count_leq(l, r, sorted_all[mid_idx])
            if count < k:
                lo_idx = mid_idx + 1
            else:
                hi_idx = mid_idx

        return sorted_all[lo_idx]


# Example
data = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3]
mst = MergeSortTree(data)

print(f"Array: {data}")
print(f"Count <= 3 in [0,9]: {mst.count_leq(0, 9, 3)}")
print(f"Count <= 5 in [2,7]: {mst.count_leq(2, 7, 5)}")
print(f"Count in [2,5] in [0,9]: {mst.count_range(0, 9, 2, 5)}")

# Kth smallest
for k in range(1, 6):
    val = mst.kth_smallest(0, 9, k)
    print(f"  {k}th smallest in [0,9]: {val}")

# Verify
print(f"\n  Sorted [0,9]: {sorted(data)}")

# Subrange query
print(f"\n  Count <= 4 in [3,7]: {mst.count_leq(3, 7, 4)}")
sub = data[3:8]
expected = sum(1 for x in sub if x <= 4)
print(f"  Expected: {expected}, subarray: {sub}")
```

**Complexity:**
- Build: O(n log n) time and space
- count_leq: O(log^2 n) -- O(log n) nodes, O(log n) binary search each
- kth_smallest: O(log^3 n) with binary search on answer, or O(log^2 n) with fractional cascading
- Space: O(n log n) -- each element in O(log n) nodes'''),

    ("thinking/algorithms", r'''Implement a segment tree that supports "range color update" operations: paint an entire range with a single color, and query what color a specific position has. Also support counting the number of distinct colors in a range.''', r'''<think>
I need a segment tree that supports "painting" an entire range with a single color and querying colors. Let me think through the operations:

1. paint(l, r, color): assign one color to all positions in [l, r]
2. query_point(pos): what color is at position pos?
3. count_colors(l, r): how many distinct colors in [l, r]?

For paint and query_point, this is a standard lazy propagation problem, but with assignment instead of addition. The lazy tag stores the color that the entire range has been painted. When pushing down, we just copy the parent's color to both children -- we do NOT add, we overwrite. This is different from range-add lazy propagation.

Now, count_colors is trickier. I initially thought about storing a set of colors at each node and taking the union during queries. But that could be O(n) in the worst case if the range has many alternating colors, and set operations in Python are slow.

Hmm, but what if the number of distinct colors is small? If there are at most 30 colors, I can represent the set of colors as a bitmask! Each node stores a bitmask where bit c is set if color c is present in that range. Then:
- paint(l, r, color): set the bitmask to (1 << color) and the lazy tag to color
- Internal nodes: bitmask = left_child.mask | right_child.mask
- count_colors: OR together the bitmasks from relevant nodes and count bits

This gives O(log n) per query since bitwise OR is O(1). Much better than the set approach.

Wait, I need to think about the push_down carefully. When I push down a color assignment, both children get mask = (1 << color) and lazy = color. This completely overwrites whatever they had before, which is correct because the paint operation overwrites everything.

One subtle point: the lazy value -1 means "no pending update." I must distinguish this from a valid color. Since colors are non-negative integers, -1 works as a sentinel.

I will use the bitmask approach, supporting up to 30 colors (fits in a 32-bit integer).
</think>

**Range Color Updates with Segment Tree**

```python
class ColorSegTree:
    """
    Segment tree for range color painting.
    Supports: paint range, query point color, count distinct colors.
    Colors are integers 0..MAX_COLORS-1 (bitmask approach).
    """
    NONE = -1  # no pending update

    def __init__(self, n, max_colors=30):
        self.n = n
        # color_mask[node] = bitmask of colors in this range
        self.mask = [0] * (4 * n)
        self.lazy = [self.NONE] * (4 * n)
        # Initialize all positions to color 0
        self._build(1, 0, n - 1)

    def _build(self, node, lo, hi):
        if lo == hi:
            self.mask[node] = 1  # color 0
            return
        mid = (lo + hi) // 2
        self._build(2 * node, lo, mid)
        self._build(2 * node + 1, mid + 1, hi)
        self.mask[node] = self.mask[2 * node] | self.mask[2 * node + 1]

    def _push_down(self, node):
        if self.lazy[node] != self.NONE:
            color = self.lazy[node]
            for child in [2 * node, 2 * node + 1]:
                self.lazy[child] = color
                self.mask[child] = 1 << color
            self.lazy[node] = self.NONE

    def paint(self, l, r, color):
        """Paint range [l, r] with given color."""
        self._paint(1, 0, self.n - 1, l, r, color)

    def _paint(self, node, lo, hi, l, r, color):
        if r < lo or hi < l:
            return
        if l <= lo and hi <= r:
            self.mask[node] = 1 << color
            self.lazy[node] = color
            return
        self._push_down(node)
        mid = (lo + hi) // 2
        self._paint(2 * node, lo, mid, l, r, color)
        self._paint(2 * node + 1, mid + 1, hi, l, r, color)
        self.mask[node] = self.mask[2 * node] | self.mask[2 * node + 1]

    def query_point(self, pos):
        """Get color at position pos."""
        return self._query_point(1, 0, self.n - 1, pos)

    def _query_point(self, node, lo, hi, pos):
        if lo == hi:
            # mask has exactly one bit set
            return self.mask[node].bit_length() - 1
        self._push_down(node)
        mid = (lo + hi) // 2
        if pos <= mid:
            return self._query_point(2 * node, lo, mid, pos)
        return self._query_point(2 * node + 1, mid + 1, hi, pos)

    def count_colors(self, l, r):
        """Count distinct colors in range [l, r]."""
        combined = self._query_mask(1, 0, self.n - 1, l, r)
        return bin(combined).count('1')

    def _query_mask(self, node, lo, hi, l, r):
        if r < lo or hi < l:
            return 0
        if l <= lo and hi <= r:
            return self.mask[node]
        self._push_down(node)
        mid = (lo + hi) // 2
        return (self._query_mask(2 * node, lo, mid, l, r) |
                self._query_mask(2 * node + 1, mid + 1, hi, l, r))


# Example
n = 10
cst = ColorSegTree(n)

print(f"Initial: all color 0")
print(f"  Distinct colors [0,9]: {cst.count_colors(0, 9)}")

cst.paint(2, 5, 1)  # paint positions 2-5 with color 1
cst.paint(4, 7, 2)  # paint positions 4-7 with color 2

print(f"\nAfter paint(2,5,1) and paint(4,7,2):")
colors = [cst.query_point(i) for i in range(n)]
print(f"  Colors: {colors}")
print(f"  Distinct in [0,9]: {cst.count_colors(0, 9)}")
print(f"  Distinct in [2,5]: {cst.count_colors(2, 5)}")
print(f"  Distinct in [0,3]: {cst.count_colors(0, 3)}")

cst.paint(0, 9, 3)  # paint everything color 3
print(f"\nAfter paint(0,9,3):")
print(f"  Distinct in [0,9]: {cst.count_colors(0, 9)}")
```

**Bitmask Trick:**
- Store colors as bitmask: color c represented as bit (1 << c)
- Union of color sets = bitwise OR of masks
- Count distinct = popcount of combined mask
- Supports up to 30 colors with 32-bit integers (60 with 64-bit)

**Complexity:**
- paint: O(log n) with lazy propagation
- query_point: O(log n)
- count_colors: O(log n) with bitmask approach
- Space: O(n)'''),
]
