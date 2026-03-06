PAIRS = [
    ("thinking/algorithms", r'''Implement a segment tree with lazy propagation for range updates and range queries. Support both range addition (add a value to all elements in a range) and range sum queries.''', r'''<think>
Lazy propagation is an optimization for segment trees that allows range updates in O(log n) instead of O(n). Without lazy propagation, a range update must visit every leaf in the range. With lazy propagation, we defer updates to child nodes until they are actually needed.

The idea:
1. Each node stores the aggregate value (sum) for its range
2. Each node also stores a "lazy" value -- a pending update that has not been pushed to children
3. On a range update, if the current node's range is fully within the update range, update the node's value and set the lazy tag (do NOT recurse into children)
4. On a query or update that needs to go deeper, first "push down" the lazy tag to children before recursing

Push-down process:
- Apply the lazy value to both children's sum values
- Set children's lazy tags
- Clear the current node's lazy tag

For range addition:
- When adding val to range [l, r] and node covers [nl, nr] fully within [l, r]:
  - node.sum += val * (nr - nl + 1)
  - node.lazy += val
- When querying, push down before recursing into children

The key insight: lazy propagation ensures that updates are applied "just in time" -- only when a node's children are accessed. This amortizes the work across subsequent operations.

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
A persistent segment tree preserves all previous versions after updates. Instead of modifying nodes in-place, each update creates new nodes along the path from root to the updated leaf, while sharing unchanged subtrees with the previous version.

Key idea: When we update position p, only O(log n) nodes on the root-to-leaf path change. We create new copies of these nodes, linking unchanged children from the old tree. Each version is identified by its root pointer.

Structure:
- Each node stores: value, left_child_index, right_child_index
- We use an array-based node pool (more memory-efficient than object allocation)
- roots[] stores the root index for each version
- update(version, pos, val) creates a new version

For a range sum query on version v: traverse from roots[v] exactly like a normal segment tree query.

Memory: Each update creates O(log n) new nodes. After Q updates, total nodes = O(n + Q * log n).

This is used in problems like:
- Kth smallest in a range (with merge sort tree or wavelet tree)
- Persistent data structures for functional programming
- Range queries across different time points

The implementation uses an implicit node pool to avoid Python object overhead.
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
A 2D segment tree extends the concept to two dimensions. The outer tree segments rows, and each node of the outer tree contains an inner segment tree that segments columns.

Structure:
- Outer tree: segments over rows [0, n-1]
- Each node in outer tree has an inner tree: segments over columns [0, m-1]
- A node at outer position covering rows [r1, r2] and inner position covering columns [c1, c2] stores the sum of all elements in the rectangle [r1..r2] x [c1..c2]

Point update (r, c, val):
1. Update the outer tree at row r
2. At each outer tree node on the path, update the inner tree at column c

Query (r1, c1, r2, c2):
1. Query the outer tree for rows [r1, r2]
2. At each relevant outer node, query the inner tree for columns [c1, c2]

The tricky part is that internal (non-leaf) outer nodes must aggregate from their children. When updating an internal outer node's inner tree, we combine the values from its two outer children.

For simplicity, I will use a flat array representation for both dimensions. The outer tree has 4*n nodes, each containing a 4*m inner tree.

Time: O(log n * log m) for both update and query.
Space: O(n * m) for the tree (up to 16 * n * m with 4x overhead per dimension).
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
A merge sort tree is a segment tree where each node stores the sorted list of all elements in its range. It is built bottom-up like merge sort, hence the name.

Structure:
- Leaf node for position i stores [arr[i]]
- Internal node stores the sorted merge of its children's arrays
- Total storage: O(n log n) because each element appears in O(log n) nodes

Queries supported:
1. Count elements <= k in range [l, r]: At each relevant segment tree node, binary search for k in its sorted array. Sum up counts. Time: O(log^2 n).
2. Kth smallest in range [l, r]: Binary search on the answer, using query #1 to count. Time: O(log^3 n), or O(log^2 n) with fractional cascading.

Building: O(n log n) time and space (same as merge sort).

This is simpler to implement than a persistent segment tree for range order statistics, though slightly less efficient.

The key operation is: for a query range [l, r], decompose it into O(log n) segment tree nodes, then binary search in each node's sorted array.

I will also implement kth smallest using binary search on the answer.

Edge cases:
- Query covers entire array
- Single element range
- All elements equal
- k smaller than all elements or larger than all
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
This is a practical segment tree problem often seen in competitive programming (sometimes called "range assignment" or "interval painting").

Operations:
1. paint(l, r, color): Set all positions in [l, r] to the given color
2. query_point(pos): Get the color at a specific position
3. count_colors(l, r): Count distinct colors in range [l, r]

For operations 1 and 2, lazy propagation with assignment works perfectly:
- Each node has a lazy "color" tag
- If a node's entire range has the same color, store it
- On paint, if the node's range is fully covered, just set the lazy tag
- On query, push down the lazy tag before recursing

For operation 3 (count distinct colors), this is trickier. A simple approach:
- If a node's entire range has one color (lazy is set), return a set of {color}
- Otherwise, recurse into children and union their color sets
- Return the size of the union

This is O(n) in the worst case for count_colors because the range might have many alternating colors. For better performance, we can use bitmask if the number of colors is small (up to 30-60), storing the set of colors as a bitmask in each node.

With bitmask approach:
- Each node stores a bitmask of colors present in its range
- paint(l, r, color): set the node's bitmask to (1 << color), lazy tag = color
- count_colors: return popcount of the OR of relevant nodes' bitmasks
- This gives O(log n) per query if colors fit in an integer

I will implement both the lazy assignment version and the bitmask version.
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
