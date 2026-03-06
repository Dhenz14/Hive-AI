PAIRS = [
    ("thinking/algorithms", r'''Implement a 2D Binary Indexed Tree (Fenwick Tree) that supports point updates and rectangle sum queries. Explain the extension from 1D to 2D.''', r'''<think>
So the task is a 2D BIT. Let me think about how to extend from 1D. In 1D, BIT gives us point update and prefix sum in O(log n). The question is how to go to 2D.

I initially considered maintaining a separate 1D BIT for each row and querying across rows, but that won't work because a row-by-row approach would give O(n log m) per query -- no better than brute force in one dimension.

Hmm, actually... what if we nest BITs? For each index in the outer BIT (rows), we maintain an inner BIT (columns). That way, a point update at (r, c) traverses the outer BIT dimension using r += r & (-r), and for each stop, traverses the inner BIT with c += c & (-c). That should give O(log n * log m) per update.

For prefix sum queries over rectangle (1,1) to (r,c), we do the reverse: traverse downward in both dimensions. But wait, we need arbitrary rectangle sums (r1,c1) to (r2,c2), not just from the origin. Since we only have prefix sums, we need inclusion-exclusion:
sum(r2,c2) - sum(r1-1,c2) - sum(r2,c1-1) + sum(r1-1,c1-1)

That works because each cell is counted exactly once in the final result. Good.

One thing I need to be careful about: BIT is 1-indexed. If I accidentally pass 0 to the update loop, the i += i & (-i) operation on 0 gives 0, causing an infinite loop. So I must validate inputs or at least document the 1-indexed requirement clearly.

Time complexity: O(log(n) * log(m)) per operation. Space: O(n * m). Let me implement this with clear separation of update and query logic.
</think>

## 2D Binary Indexed Tree (Fenwick Tree)

### Extension from 1D to 2D
In 1D, BIT[i] stores partial sums using the lowest-set-bit trick. In 2D, we nest this: for each row index in the outer BIT, we maintain a complete inner BIT over columns.

### Implementation

```python
class BIT2D:
    """2D Binary Indexed Tree for point update and rectangle sum query."""

    def __init__(self, rows, cols):
        self.rows = rows
        self.cols = cols
        # 1-indexed, so allocate rows+1 x cols+1
        self.tree = [[0] * (cols + 1) for _ in range(rows + 1)]

    def update(self, r, c, delta):
        """Add delta to position (r, c). 1-indexed."""
        i = r
        while i <= self.rows:
            j = c
            while j <= self.cols:
                self.tree[i][j] += delta
                j += j & (-j)
            i += i & (-i)

    def _prefix_sum(self, r, c):
        """Sum of rectangle (1,1) to (r,c)."""
        total = 0
        i = r
        while i > 0:
            j = c
            while j > 0:
                total += self.tree[i][j]
                j -= j & (-j)
            i -= i & (-i)
        return total

    def range_sum(self, r1, c1, r2, c2):
        """Sum of rectangle (r1,c1) to (r2,c2). 1-indexed."""
        return (self._prefix_sum(r2, c2)
                - self._prefix_sum(r1 - 1, c2)
                - self._prefix_sum(r2, c1 - 1)
                + self._prefix_sum(r1 - 1, c1 - 1))

    def set_val(self, r, c, val):
        """Set position (r,c) to val (need current value)."""
        current = self.range_sum(r, c, r, c)
        self.update(r, c, val - current)


# Demo
bit = BIT2D(4, 5)

# Build a grid:
# 1 2 3 4 5
# 6 7 8 9 10
# 11 12 13 14 15
# 16 17 18 19 20
for r in range(1, 5):
    for c in range(1, 6):
        val = (r - 1) * 5 + c
        bit.update(r, c, val)

# Query: sum of subgrid (2,2) to (3,4) = 7+8+9+12+13+14 = 63
print(f"Sum (2,2)-(3,4): {bit.range_sum(2, 2, 3, 4)}")  # 63

# Query: sum of entire grid
print(f"Sum (1,1)-(4,5): {bit.range_sum(1, 1, 4, 5)}")  # 210

# Update: add 10 to position (2,3)
bit.update(2, 3, 10)
print(f"After update: {bit.range_sum(2, 2, 3, 4)}")  # 73

# Verify with brute force
grid = [[0]*6 for _ in range(5)]
for r in range(1, 5):
    for c in range(1, 6):
        grid[r][c] = (r - 1) * 5 + c
grid[2][3] += 10
brute = sum(grid[r][c] for r in range(2, 4) for c in range(2, 5))
print(f"Brute force: {brute}")  # 73
```

### Complexity
- **Update**: O(log(n) * log(m))
- **Query**: O(log(n) * log(m))
- **Space**: O(n * m)
- **Build from matrix**: O(n * m * log(n) * log(m)), or O(n*m) with careful initialization'''),

    ("thinking/algorithms", r'''Implement a BIT that supports range updates and point queries. Show the difference trick and explain how it relates to the standard point-update/prefix-sum BIT.''', r'''<think>
OK so the standard BIT supports point updates and prefix sum queries. Now I need range updates and point queries -- that is the opposite pattern. How do I flip things around?

I initially considered building a segment tree with lazy propagation, but that feels like overkill for this specific operation pair. There should be a way to reuse the BIT machinery.

Wait -- what about a difference array? If I maintain D[i] = A[i] - A[i-1], then A[i] = D[1] + D[2] + ... + D[i] = prefix_sum(D, i). And a range update A[l..r] += val only changes two elements of D: D[l] += val, D[r+1] -= val. That is exactly two point updates!

So the operations swap roles:
- "Point query of A[i]" becomes "prefix sum query on D" (which BIT handles natively)
- "Range update on A" becomes "two point updates on D" (which BIT also handles natively)

Hmm, actually this is a nice duality. The underlying BIT is identical -- we just reinterpret what the stored values mean. The implementation is the same BIT class, with a wrapper that translates range_update into two point updates and point_query into a prefix_sum call.

One thing to watch: when updating D[r+1], if r+1 > n we just skip it because D values beyond the array do not affect any prefix sum within bounds. Let me implement this and show both interpretations side by side.
</think>

## BIT for Range Updates and Point Queries

### The Duality
| Standard BIT | Difference BIT |
|-------------|---------------|
| Point update A[i] += val | Range update A[l..r] += val |
| Prefix sum A[1..i] | Point query A[i] |

The trick: maintain BIT over the **difference array** D[i] = A[i] - A[i-1].

### Implementation

```python
class BIT:
    """Standard BIT: point update, prefix sum query."""
    def __init__(self, n):
        self.n = n
        self.tree = [0] * (n + 1)  # 1-indexed

    def update(self, i, delta):
        """Add delta at position i."""
        while i <= self.n:
            self.tree[i] += delta
            i += i & (-i)

    def prefix_sum(self, i):
        """Sum of elements 1..i."""
        s = 0
        while i > 0:
            s += self.tree[i]
            i -= i & (-i)
        return s


class RangeUpdatePointQuery:
    """BIT-based structure for range update and point query.
    Internally uses a BIT over the difference array."""

    def __init__(self, n):
        self.n = n
        self.bit = BIT(n)

    def range_update(self, l, r, val):
        """Add val to all elements in [l, r]. 1-indexed."""
        self.bit.update(l, val)
        if r + 1 <= self.n:
            self.bit.update(r + 1, -val)

    def point_query(self, i):
        """Get the value at position i. 1-indexed.
        This is prefix_sum of the difference array = actual value."""
        return self.bit.prefix_sum(i)

    def build_from_array(self, arr):
        """Initialize from 0-indexed array. arr[0] -> position 1."""
        for i in range(len(arr)):
            # Difference: D[i+1] = arr[i] - arr[i-1]
            diff = arr[i] - (arr[i - 1] if i > 0 else 0)
            self.bit.update(i + 1, diff)


# Demo
n = 8
rupq = RangeUpdatePointQuery(n)

# Initialize: [0, 0, 0, 0, 0, 0, 0, 0]
# Range update [2, 5] += 10 -> [0, 10, 10, 10, 10, 0, 0, 0]
rupq.range_update(2, 5, 10)
print("After +10 on [2,5]:", [rupq.point_query(i) for i in range(1, 9)])

# Range update [3, 7] += 5 -> [0, 10, 15, 15, 15, 5, 5, 0]
rupq.range_update(3, 7, 5)
print("After +5 on [3,7]: ", [rupq.point_query(i) for i in range(1, 9)])

# Range update [1, 4] -= 3 -> [-3, 7, 12, 12, 15, 5, 5, 0]
rupq.range_update(1, 4, -3)
print("After -3 on [1,4]: ", [rupq.point_query(i) for i in range(1, 9)])

# Build from existing array
rupq2 = RangeUpdatePointQuery(5)
rupq2.build_from_array([3, 1, 4, 1, 5])
print("\nBuilt from [3,1,4,1,5]:", [rupq2.point_query(i) for i in range(1, 6)])
rupq2.range_update(2, 4, 10)
print("After +10 on [2,4]:   ", [rupq2.point_query(i) for i in range(1, 6)])
```

### Why It Works
```
D[1] = A[1]
D[i] = A[i] - A[i-1]  for i > 1

A[i] = D[1] + D[2] + ... + D[i] = prefix_sum(D, i)

Range add val to A[l..r]:
  D[l] += val    (A[l] increases, gap from A[l-1] grows)
  D[r+1] -= val  (A[r+1] stays same, gap from A[r] shrinks)
```

### Complexity
- **Range update**: O(log n) -- two BIT point updates
- **Point query**: O(log n) -- one BIT prefix sum
- **Space**: O(n)'''),

    ("thinking/algorithms", r'''Implement a BIT that supports both range updates AND range sum queries. Show the mathematical derivation using two BITs.''', r'''<think>
This is the hardest BIT variant -- both range updates AND range sum queries. With a single BIT on a difference array, I can do range update + point query (as shown before). But now I need range sums too.

My first thought: could I just maintain a running total alongside the difference BIT? But that does not work because a range update affects a contiguous block, so the prefix sum changes non-uniformly.

Let me derive this from scratch. Let D[i] = A[i] - A[i-1], so A[i] = sum(D[j] for j=1..i).

prefix_sum(k) = sum(A[j] for j=1..k) = sum(sum(D[j] for j=1..i) for i=1..k)

Hmm, expanding the double sum: each D[j] appears in sums for i = j, j+1, ..., k. So D[j] appears (k - j + 1) times.

prefix_sum(k) = sum(D[j] * (k - j + 1) for j=1..k)
              = (k+1) * sum(D[j]) - sum(j * D[j])

Wait, that is actually clean! I can split this into two independent prefix sums:
- B1 tracks D[i] --> gives sum(D[j] for j=1..k)
- B2 tracks i * D[i] --> gives sum(j * D[j] for j=1..k)

Then prefix_sum(k) = (k+1) * B1.prefix(k) - B2.prefix(k). Nice.

For range update A[l..r] += val, I update the difference array at two points:
- B1: update(l, val), update(r+1, -val)
- B2: update(l, l*val), update(r+1, -(r+1)*val)

Because D[l] changes by val and D[r+1] changes by -val, the corresponding j*D[j] terms change by l*val and -(r+1)*val.

For range query, just use prefix_sum(r) - prefix_sum(l-1). This gives O(log n) for both operations using only two BITs. The math works out cleanly once you see the double-sum expansion trick.
</think>

## BIT with Range Update + Range Query

### Mathematical Derivation

Starting from difference array D[i] = A[i] - A[i-1]:

```
prefix_sum(k) = sum_{i=1}^{k} A[i]
              = sum_{i=1}^{k} sum_{j=1}^{i} D[j]
              = sum_{j=1}^{k} D[j] * (k - j + 1)
              = (k+1) * sum_{j=1}^{k} D[j]  -  sum_{j=1}^{k} j*D[j]
```

So we need two BITs: one for D[j] and one for j*D[j].

### Implementation

```python
class BIT:
    def __init__(self, n):
        self.n = n
        self.tree = [0] * (n + 2)

    def update(self, i, delta):
        while i <= self.n:
            self.tree[i] += delta
            i += i & (-i)

    def query(self, i):
        s = 0
        while i > 0:
            s += self.tree[i]
            i -= i & (-i)
        return s


class RangeUpdateRangeQuery:
    """Supports range update and range sum query in O(log n)."""

    def __init__(self, n):
        self.n = n
        self.b1 = BIT(n)  # stores D[i]
        self.b2 = BIT(n)  # stores i * D[i]

    def range_update(self, l, r, val):
        """Add val to all elements in [l, r]. 1-indexed."""
        # Update D[l] += val, D[r+1] -= val
        self.b1.update(l, val)
        self.b1.update(r + 1, -val)
        self.b2.update(l, l * val)
        self.b2.update(r + 1, -(r + 1) * val)

    def _prefix_sum(self, k):
        """Sum of A[1..k]."""
        if k <= 0:
            return 0
        return (k + 1) * self.b1.query(k) - self.b2.query(k)

    def range_query(self, l, r):
        """Sum of A[l..r]. 1-indexed."""
        return self._prefix_sum(r) - self._prefix_sum(l - 1)

    def point_query(self, i):
        """Get A[i]."""
        return self.range_query(i, i)

    def build_from_array(self, arr):
        """Initialize from 0-indexed array."""
        for i in range(len(arr)):
            self.range_update(i + 1, i + 1, arr[i])


# Demo
rurq = RangeUpdateRangeQuery(10)

# Build array [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
rurq.build_from_array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

print("Initial array:", [rurq.point_query(i) for i in range(1, 11)])
print("Sum [3..7]:", rurq.range_query(3, 7))  # 3+4+5+6+7 = 25

# Range update: add 10 to [2, 6]
rurq.range_update(2, 6, 10)
print("\nAfter +10 on [2,6]:", [rurq.point_query(i) for i in range(1, 11)])
print("Sum [3..7]:", rurq.range_query(3, 7))  # 13+14+15+16+7 = 65

# Another update: add -5 to [4, 8]
rurq.range_update(4, 8, -5)
print("\nAfter -5 on [4,8]:", [rurq.point_query(i) for i in range(1, 11)])
print("Sum [1..10]:", rurq.range_query(1, 10))

# Verify against brute force
arr = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
for i in range(1, 6):  # [2,6] += 10
    arr[i] += 10
for i in range(3, 8):  # [4,8] -= 5
    arr[i] -= 5
print("Brute force:", arr)
print("Brute sum [1..10]:", sum(arr))
```

### Complexity
- **Range update**: O(log n) -- 4 BIT point updates
- **Range query**: O(log n) -- 4 BIT prefix queries
- **Space**: O(n) for two BITs
- **Advantage over segment tree**: ~3-5x less memory, simpler code, same asymptotics'''),

    ("thinking/algorithms", r'''Implement order statistics using a BIT. Support: insert a number, delete a number, find k-th smallest element, and count elements less than a given value. All in O(log n) time.''', r'''<think>
Order statistics with a BIT. The idea is to use the BIT as a frequency array over the value domain -- BIT[v] stores the count of value v. Insert is update(v, +1), delete is update(v, -1), and count-less-than is prefix_sum(x-1). So far so good.

But the k-th smallest is trickier. My first thought is binary search: find the smallest x where prefix_sum(x) >= k. That works but takes O(log^2 n) -- a binary search with O(log n) per prefix_sum call.

Wait, I recall there is a way to walk the BIT structure directly in O(log n). The idea is to go from the most significant bit to the least significant. At each step, we check if the left subtree (the BIT node at pos + bit) has enough elements. If tree[pos + bit] < remaining, the k-th element is to the right, so we subtract that count and advance pos. Otherwise we stay left.

Hmm, actually I need to be careful here. The tree[pos + bit] value in a BIT stores exactly the sum of a specific range of elements -- the "left subtree" at that level. So checking tree[next_pos] < remaining tells us whether the answer is in the right half. This is essentially a binary search baked into the BIT structure, avoiding redundant prefix sum recomputation. Each level processes one bit, so it is O(log n) total.

One constraint: the value domain needs to be bounded. If values can be up to 10^9, we would need coordinate compression first to map values to [1, n]. For this implementation I will assume a known max_val.
</think>

## Order Statistics with Binary Indexed Tree

### Implementation

```python
class OrderStatisticsBIT:
    """BIT-based order statistics supporting insert, delete,
    k-th smallest, and rank queries in O(log n)."""

    def __init__(self, max_val):
        """max_val: maximum value that can be inserted (1-indexed)."""
        self.n = max_val
        self.tree = [0] * (self.n + 1)
        self.total = 0
        # Precompute largest power of 2 <= n
        self.log = 0
        while (1 << (self.log + 1)) <= self.n:
            self.log += 1

    def _update(self, i, delta):
        while i <= self.n:
            self.tree[i] += delta
            i += i & (-i)

    def _prefix(self, i):
        s = 0
        while i > 0:
            s += self.tree[i]
            i -= i & (-i)
        return s

    def insert(self, val):
        """Insert a value (1-indexed)."""
        self._update(val, 1)
        self.total += 1

    def delete(self, val):
        """Delete one occurrence of value (1-indexed)."""
        if self._prefix(val) - self._prefix(val - 1) > 0:
            self._update(val, -1)
            self.total -= 1
            return True
        return False

    def count_less(self, val):
        """Count elements strictly less than val."""
        if val <= 1:
            return 0
        return self._prefix(val - 1)

    def count_range(self, lo, hi):
        """Count elements in [lo, hi]."""
        return self._prefix(hi) - self._prefix(lo - 1)

    def kth_smallest(self, k):
        """Find k-th smallest element in O(log n).
        Uses BIT tree walking instead of binary search."""
        if k < 1 or k > self.total:
            return -1

        pos = 0
        remaining = k
        # Walk from highest bit to lowest
        bit_mask = 1 << self.log
        while bit_mask > 0:
            next_pos = pos + bit_mask
            if next_pos <= self.n and self.tree[next_pos] < remaining:
                remaining -= self.tree[next_pos]
                pos = next_pos
            bit_mask >>= 1
        return pos + 1

    def rank(self, val):
        """Return rank of val (1-based position if sorted)."""
        return self._prefix(val - 1) + 1


# Demo
os_bit = OrderStatisticsBIT(100)  # values in range [1, 100]

# Insert elements
for v in [15, 3, 7, 22, 7, 42, 3, 10]:
    os_bit.insert(v)

print("Elements: [15, 3, 7, 22, 7, 42, 3, 10]")
print(f"Sorted:   [3, 3, 7, 7, 10, 15, 22, 42]")
print(f"Total: {os_bit.total}")

# K-th smallest
for k in range(1, 9):
    print(f"  {k}-th smallest: {os_bit.kth_smallest(k)}")

# Count operations
print(f"\nCount less than 10: {os_bit.count_less(10)}")  # 4 (3,3,7,7)
print(f"Count in [5,20]: {os_bit.count_range(5, 20)}")   # 4 (7,7,10,15)

# Rank of 10
print(f"Rank of 10: {os_bit.rank(10)}")  # 5

# Delete
os_bit.delete(7)
print(f"\nAfter deleting one 7:")
print(f"  3rd smallest: {os_bit.kth_smallest(3)}")  # 7 (remaining one)
print(f"  4th smallest: {os_bit.kth_smallest(4)}")  # 10
```

### The O(log n) K-th Smallest Trick
Instead of binary searching over prefix sums (O(log^2 n)), we walk the BIT directly:
1. Start at position 0, remaining = k
2. For each bit from high to low, check if adding that bit keeps us within bounds
3. If `tree[pos + bit] < remaining`, go right (subtract and advance)
4. Otherwise, go left (do not advance)

This works because `tree[pos + bit]` stores exactly the sum of the left subtree at that level.

### Complexity
- **Insert/Delete**: O(log n)
- **K-th smallest**: O(log n) with tree walking
- **Count/Rank**: O(log n)
- **Space**: O(max_val) -- requires coordinate compression for large ranges'''),

    ("thinking/algorithms", r'''Use a BIT to count inversions in an array efficiently. An inversion is a pair (i, j) where i < j but a[i] > a[j]. Show the O(n log n) approach and prove correctness.''', r'''<think>
Counting inversions with BIT. An inversion is (i, j) where i < j but a[i] > a[j]. I need to count all such pairs efficiently.

My first idea: for each element a[i], count how many inversions it participates in as the smaller element (the right side of the inversion). Wait, let me think about this more carefully. If I process left to right, for position i I want to know how many elements before i are greater than a[i]. That would be the inversions where i is the right index.

OK so using a frequency BIT: for each a[i] processed left to right:
1. Query: how many already-inserted elements are > a[i]? That is (elements so far) - prefix_sum(a[i])
2. Update: insert a[i] by doing update(a[i], +1)

The total over all positions gives the inversion count.

But wait -- what if values are large (up to 10^9)? The BIT size would be huge. I need coordinate compression: replace each value with its rank in sorted order. This maps to [1, n] without changing relative order, so inversions are preserved. I could also use value-1 but ranks are cleaner.

For correctness: when processing position i, the BIT contains all elements from positions 0..i-1. prefix_sum(a[i]) counts elements <= a[i], so i - prefix_sum(a[i]) counts elements > a[i]. Each such element forms an inversion pair with position i. Summing over all i counts every inversion exactly once because each pair (i,j) with i<j is counted when processing j.

I initially considered the alternative of processing right-to-left and counting prefix_sum(a[i]-1) for each element (elements to the right that are smaller), but the left-to-right approach feels more natural. Both are O(n log n).
</think>

## Inversion Count Using Binary Indexed Tree

### Approach
Process elements left to right. For each element, count how many already-inserted elements are larger (these form inversions with the current position).

### Implementation

```python
class BIT:
    def __init__(self, n):
        self.n = n
        self.tree = [0] * (n + 1)

    def update(self, i, delta=1):
        while i <= self.n:
            self.tree[i] += delta
            i += i & (-i)

    def query(self, i):
        s = 0
        while i > 0:
            s += self.tree[i]
            i -= i & (-i)
        return s


def count_inversions(arr):
    """Count inversions in O(n log n) using BIT.

    An inversion is a pair (i, j) with i < j and arr[i] > arr[j].
    """
    if not arr:
        return 0

    n = len(arr)

    # Coordinate compression: map values to ranks 1..n
    sorted_unique = sorted(set(arr))
    rank_map = {v: i + 1 for i, v in enumerate(sorted_unique)}
    max_rank = len(sorted_unique)

    bit = BIT(max_rank)
    inversions = 0

    for i in range(n):
        r = rank_map[arr[i]]
        # Count elements already in BIT with rank > r
        # = (elements inserted so far) - (elements with rank <= r)
        elements_so_far = i  # we've inserted i elements before this one
        elements_leq = bit.query(r)
        inversions += elements_so_far - elements_leq

        # Insert current element
        bit.update(r)

    return inversions


def count_inversions_brute(arr):
    """O(n^2) brute force for verification."""
    n = len(arr)
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            if arr[i] > arr[j]:
                count += 1
    return count


# Test cases
test_cases = [
    [2, 4, 1, 3, 5],     # inversions: (2,1), (4,1), (4,3) = 3
    [5, 4, 3, 2, 1],     # reverse sorted: 10 inversions
    [1, 2, 3, 4, 5],     # sorted: 0 inversions
    [1, 1, 1, 1],        # all equal: 0 inversions
    [3, 1, 2],           # (3,1), (3,2) = 2
    [7, 2, 5, 3, 1, 8],  # multiple inversions
]

for arr in test_cases:
    bit_result = count_inversions(arr)
    brute_result = count_inversions_brute(arr)
    status = "OK" if bit_result == brute_result else "MISMATCH"
    print(f"{arr} -> {bit_result} [{status}]")


# Large-scale test
import random
random.seed(42)
large = [random.randint(1, 10000) for _ in range(10000)]
result = count_inversions(large)
print(f"\nRandom array of 10000 elements: {result} inversions")
```

### Output
```
[2, 4, 1, 3, 5] -> 3 [OK]
[5, 4, 3, 2, 1] -> 10 [OK]
[1, 2, 3, 4, 5] -> 0 [OK]
[1, 1, 1, 1] -> 0 [OK]
[3, 1, 2] -> 2 [OK]
[7, 2, 5, 3, 1, 8] -> 8 [OK]
```

### Proof of Correctness
When processing index `i`, the BIT contains elements from indices `0, 1, ..., i-1`.
- `bit.query(r)` = count of elements at indices < i with value <= arr[i]
- `i - bit.query(r)` = count of elements at indices < i with value > arr[i]
- Each such element forms an inversion pair with index i
- Summing over all i counts every inversion exactly once

### Complexity
- **Time**: O(n log n) -- n elements, each O(log n) for BIT ops
- **Space**: O(n) for BIT and rank mapping
- **Comparison**: merge sort inversion count is also O(n log n) but modifies the array; BIT approach is non-destructive'''),
]
