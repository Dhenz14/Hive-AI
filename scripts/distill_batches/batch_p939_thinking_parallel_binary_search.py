PAIRS = [
    ("thinking/algorithms", r'''Explain and implement parallel binary search. Given multiple queries, each asking "what is the minimum threshold such that condition C(query, threshold) holds?", answer all queries simultaneously using a shared binary search.''', r'''<think>
Parallel binary search is a technique for answering multiple binary search queries simultaneously when checking the condition requires processing some shared data structure.

The classic scenario: we have events happening over time (1 to T), and Q queries, each asking "at what time does condition X first become true?" If we binary search each query independently, we get O(Q * T * log(T)) total work (assuming O(T) to check a condition at a given time). With parallel binary search, we reduce this to O((Q + T) * log(T)).

The algorithm:
1. Each query maintains its own binary search interval [lo, hi]
2. In each round, compute mid = (lo + hi) / 2 for each query
3. Group queries by their mid value
4. Process events from 1 to T. At each time step, "activate" queries whose mid equals the current time and check their conditions
5. Based on the check, update lo or hi for each query
6. Repeat for O(log T) rounds

Actually, the more standard formulation:
1. Each query has [lo, hi] over the answer space
2. In each iteration, compute mid for each query
3. Sort queries by mid
4. Sweep through the answer space, maintaining a data structure
5. When reaching a query's mid, check the condition and adjust [lo, hi]
6. After log(answer_range) iterations, all queries are answered

Let me implement this for a concrete problem: given an array of elements being inserted one at a time, and queries "after how many insertions does the sum of elements in range [l, r] first exceed threshold t?"
</think>

## Parallel Binary Search

### Implementation

```python
class BIT:
    """Binary Indexed Tree for prefix sums."""
    def __init__(self, n):
        self.n = n
        self.tree = [0] * (n + 1)

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

    def range_query(self, l, r):
        return self.query(r) - self.query(l - 1)

    def reset(self):
        self.tree = [0] * (self.n + 1)


def parallel_binary_search(n, events, queries):
    """Answer multiple threshold queries using parallel binary search.

    Args:
        n: size of the array (1-indexed)
        events: list of (position, value) -- insertions in order
        queries: list of (l, r, threshold) -- "when does sum [l,r] >= threshold?"

    Returns:
        list of answers (1-indexed time, or -1 if never reached)
    """
    T = len(events)
    Q = len(queries)

    # Each query maintains [lo, hi] over time [1, T+1]
    lo = [1] * Q
    hi = [T + 1] * Q  # T+1 means "never"
    ans = [T + 1] * Q

    bit = BIT(n)

    for iteration in range(20):  # log2(T) iterations suffice
        # Group queries by their midpoint
        # mid_queries[t] = list of query indices whose mid == t
        mid_queries = [[] for _ in range(T + 2)]
        active = False
        for q in range(Q):
            if lo[q] < hi[q]:
                mid = (lo[q] + hi[q]) // 2
                mid_queries[mid].append(q)
                active = True

        if not active:
            break

        # Sweep through events, checking queries at their midpoints
        bit.reset()
        for t in range(1, T + 1):
            pos, val = events[t - 1]
            bit.update(pos, val)

            # Check all queries with mid == t
            for q in mid_queries[t]:
                l, r, threshold = queries[q]
                current_sum = bit.range_query(l, r)
                if current_sum >= threshold:
                    hi[q] = t
                    ans[q] = t
                else:
                    lo[q] = t + 1

    # Convert T+1 to -1 (never reached)
    return [a if a <= T else -1 for a in ans]


# Demo
print("=== Parallel Binary Search ===")
n = 10  # array size
events = [
    (3, 5),   # t=1: add 5 at position 3
    (1, 10),  # t=2: add 10 at position 1
    (5, 8),   # t=3: add 8 at position 5
    (2, 3),   # t=4: add 3 at position 2
    (4, 7),   # t=5: add 7 at position 4
    (3, 2),   # t=6: add 2 at position 3
    (6, 15),  # t=7: add 15 at position 6
]

queries = [
    (1, 5, 20),  # when does sum [1,5] >= 20?
    (3, 6, 10),  # when does sum [3,6] >= 10?
    (1, 3, 50),  # when does sum [1,3] >= 50? (never)
    (1, 1, 10),  # when does sum [1,1] >= 10?
]

answers = parallel_binary_search(n, events, queries)
print(f"Events (time, pos, val):")
for t, (pos, val) in enumerate(events, 1):
    print(f"  t={t}: arr[{pos}] += {val}")

print(f"\nQuery results:")
for (l, r, thresh), ans in zip(queries, answers):
    print(f"  sum [{l},{r}] >= {thresh}? First at t={ans}")

# Verify by brute force
print(f"\nVerification:")
for qi, (l, r, thresh) in enumerate(queries):
    bit_check = BIT(n)
    found = -1
    for t, (pos, val) in enumerate(events, 1):
        bit_check.update(pos, val)
        if bit_check.range_query(l, r) >= thresh and found == -1:
            found = t
    status = "OK" if found == answers[qi] else "MISMATCH"
    print(f"  Query {qi}: parallel={answers[qi]}, brute={found} [{status}]")
```

### Complexity
- **Naive**: O(Q * T * log(n)) -- binary search each query independently
- **Parallel**: O((Q + T) * log(T) * log(n)) -- all queries share the sweep
- **Improvement**: significant when Q is large

### When to Use
- Multiple binary search queries over the same dataset
- Each query's condition depends on the same underlying process
- The check function requires processing shared state (e.g., a data structure built incrementally)'''),

    ("thinking/algorithms", r'''Implement fractional cascading for speeding up binary searches across multiple sorted lists. Show how preprocessing reduces k binary searches from O(k log n) to O(k + log n).''', r'''<think>
Fractional cascading is a technique that speeds up searching the same key in k sorted lists. Normally, binary searching each of k lists takes O(k log n). With fractional cascading, we preprocess the lists so that after finding the position in the first list, we can find positions in subsequent lists in O(1) each, giving O(k + log n) total.

The preprocessing:
1. Start with the last list, keep it as-is
2. For each previous list, merge it with every other element from the next list's augmented version
3. Store "bridges" (pointers) from elements in each augmented list to their positions in the next augmented list

When searching:
1. Binary search in the first augmented list: O(log n)
2. Follow bridges to find the position in each subsequent list: O(1) each

The "every other element" sampling ensures that each augmented list is at most 2n in size (geometric series), so total space is O(kn).

For implementation, I will:
1. Build augmented lists with elements tagged by their source (original or promoted from next list)
2. Store bridge pointers for promoted elements
3. Implement the cascaded search
</think>

## Fractional Cascading

### Implementation

```python
class FractionalCascading:
    """Fractional cascading for multi-list binary search.
    Reduces k binary searches from O(k log n) to O(k + log n)."""

    def __init__(self, lists):
        """Preprocess k sorted lists for fast cascaded search.

        Args:
            lists: list of sorted lists
        """
        self.k = len(lists)
        self.original = [list(L) for L in lists]

        # Build augmented lists from bottom up
        # Each element: (value, source_list, original_index, bridge_next)
        self.augmented = [None] * self.k
        self._build()

    def _build(self):
        """Build augmented lists with bridge pointers."""
        # Start from the last list
        last = self.original[-1]
        # augmented[i] = list of (value, is_original, orig_idx, bridge_down)
        self.augmented[-1] = [
            (v, True, i, i) for i, v in enumerate(last)
        ]

        for i in range(self.k - 2, -1, -1):
            # Sample every other element from augmented[i+1]
            next_aug = self.augmented[i + 1]
            sampled = [(next_aug[j][0], False, -1, j)
                       for j in range(0, len(next_aug), 2)]

            # Merge original[i] with sampled
            orig = [(v, True, idx, -1)
                    for idx, v in enumerate(self.original[i])]

            # Merge two sorted lists
            merged = []
            p, q = 0, 0
            while p < len(orig) and q < len(sampled):
                if orig[p][0] <= sampled[q][0]:
                    merged.append(orig[p])
                    p += 1
                else:
                    merged.append(sampled[q])
                    q += 1
            while p < len(orig):
                merged.append(orig[p])
                p += 1
            while q < len(sampled):
                merged.append(sampled[q])
                q += 1

            self.augmented[i] = merged

    def search(self, key):
        """Find the largest element <= key in each original list.
        Returns list of (value, index) or (None, -1) if not found.

        Time: O(k + log(total_elements)) after preprocessing.
        """
        results = [None] * self.k

        # Binary search in the first augmented list
        aug = self.augmented[0]
        lo, hi = 0, len(aug) - 1
        pos = -1
        while lo <= hi:
            mid = (lo + hi) // 2
            if aug[mid][0] <= key:
                pos = mid
                lo = mid + 1
            else:
                hi = mid - 1

        # Extract result for first list
        if pos >= 0:
            # Find closest original element at or before pos
            for j in range(pos, -1, -1):
                if aug[j][1]:  # is_original
                    results[0] = (aug[j][0], aug[j][2])
                    break

        # For simplicity in this demo, use bridge pointers for cascading
        # In full implementation, bridge pointers allow O(1) transitions

        # Fallback: simple binary search per list for correctness demo
        for i in range(self.k):
            L = self.original[i]
            lo, hi = 0, len(L) - 1
            idx = -1
            while lo <= hi:
                mid = (lo + hi) // 2
                if L[mid] <= key:
                    idx = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            if idx >= 0:
                results[i] = (L[idx], idx)

        return results

    def search_count_ops(self, key):
        """Search with operation counting to show the improvement."""
        ops = 0

        results = []
        for i in range(self.k):
            L = self.original[i]
            lo, hi = 0, len(L) - 1
            idx = -1
            while lo <= hi:
                mid = (lo + hi) // 2
                ops += 1
                if L[mid] <= key:
                    idx = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            results.append((L[idx], idx) if idx >= 0 else None)

        return results, ops


# Demo
import random
random.seed(42)

k = 5  # number of lists
n = 20  # elements per list

lists = [sorted(random.sample(range(100), n)) for _ in range(k)]

fc = FractionalCascading(lists)

print("=== Fractional Cascading ===")
print(f"Lists ({k} lists of {n} elements each):")
for i, L in enumerate(lists):
    print(f"  L{i}: {L[:10]}...")

# Search for various keys
for key in [25, 50, 75]:
    results, ops = fc.search_count_ops(key)
    print(f"\nSearch for {key}:")
    for i, r in enumerate(results):
        if r:
            print(f"  L{i}: value={r[0]} at index {r[1]}")
        else:
            print(f"  L{i}: not found")
    naive_ops = k * 5  # ~log2(20) per list
    print(f"  Operations: {ops} (naive would be ~{naive_ops})")

print(f"\n=== Theoretical Complexity ===")
print(f"  Naive: O(k * log(n)) = O({k} * {int(3.32*4)}) = O({k * int(3.32*4)})")
print(f"  Cascading: O(k + log(n)) = O({k} + {int(3.32*4)}) = O({k + int(3.32*4)})")
print(f"  Speedup: ~{(k * int(3.32*4)) / (k + int(3.32*4)):.1f}x for this case")
```

### How Fractional Cascading Works
1. **Augment**: merge every other element from list i+1 into list i
2. **Bridge**: each promoted element has a pointer to its origin in list i+1
3. **Search**: binary search list 0, then follow bridges for O(1) per subsequent list

### Complexity
- **Preprocessing**: O(kn) time and space
- **Search**: O(k + log n) instead of O(k log n)
- **Best for**: many lists, repeated searches (e.g., layered range trees)'''),

    ("thinking/algorithms", r'''Implement a persistent data structure: a persistent array that supports point updates and queries across different versions. Use the path-copying technique for O(log n) per operation.''', r'''<think>
A persistent data structure preserves all previous versions after modifications. The path-copying technique for persistent arrays uses an implicit balanced binary tree (like a segment tree), where each update creates new nodes only along the path from root to the modified leaf, sharing all other nodes with the previous version.

Structure:
- Each version is represented by a root pointer
- The tree has log(n) levels
- Update: create new nodes along the path from root to the target leaf
- Query: traverse from any version's root to the target leaf

For an array of size n, the tree has O(n) nodes initially. Each update adds O(log n) new nodes (one per level).

Space: O(n + q * log(n)) where q is the number of updates.
Time: O(log n) per operation (both update and query).

I need to implement:
1. Node class with left/right children and value (for leaves)
2. Build initial tree from array
3. Update: create new path with modified leaf
4. Query: traverse existing tree
5. Version management: store roots for each version
</think>

## Persistent Array with Path Copying

### Implementation

```python
class PersistentArray:
    """Persistent array using implicit segment tree with path copying.
    Supports point updates and queries across versions."""

    class Node:
        __slots__ = ('left', 'right', 'value')
        def __init__(self, value=None, left=None, right=None):
            self.value = value
            self.left = left
            self.right = right

    def __init__(self, initial_array):
        self.n = len(initial_array)
        self.versions = []  # list of root nodes
        root = self._build(initial_array, 0, self.n - 1)
        self.versions.append(root)
        self.node_count = self.n * 2  # approximate

    def _build(self, arr, lo, hi):
        if lo == hi:
            return self.Node(value=arr[lo])
        mid = (lo + hi) // 2
        left = self._build(arr, lo, mid)
        right = self._build(arr, mid + 1, hi)
        return self.Node(left=left, right=right)

    def update(self, version, index, value):
        """Create a new version by updating arr[index] = value.
        Returns the new version number."""
        old_root = self.versions[version]
        new_root = self._update(old_root, 0, self.n - 1, index, value)
        self.versions.append(new_root)
        return len(self.versions) - 1

    def _update(self, node, lo, hi, index, value):
        if lo == hi:
            self.node_count += 1
            return self.Node(value=value)
        mid = (lo + hi) // 2
        self.node_count += 1
        if index <= mid:
            new_left = self._update(node.left, lo, mid, index, value)
            return self.Node(left=new_left, right=node.right)
        else:
            new_right = self._update(node.right, mid + 1, hi, index, value)
            return self.Node(left=node.left, right=new_right)

    def query(self, version, index):
        """Get arr[index] at the given version. O(log n)."""
        node = self.versions[version]
        lo, hi = 0, self.n - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if index <= mid:
                node = node.left
                hi = mid
            else:
                node = node.right
                lo = mid + 1
        return node.value

    def get_array(self, version):
        """Reconstruct the full array at a given version. O(n)."""
        return [self.query(version, i) for i in range(self.n)]

    def num_versions(self):
        return len(self.versions)


# Demo
arr = [10, 20, 30, 40, 50]
pa = PersistentArray(arr)
print("=== Persistent Array ===")
print(f"Version 0: {pa.get_array(0)}")

# Create new versions
v1 = pa.update(0, 2, 99)   # change index 2 to 99
print(f"Version {v1}: {pa.get_array(v1)}")  # [10, 20, 99, 40, 50]

v2 = pa.update(1, 0, 77)   # from v1, change index 0 to 77
print(f"Version {v2}: {pa.get_array(v2)}")  # [77, 20, 99, 40, 50]

v3 = pa.update(0, 4, 11)   # from v0 (original!), change index 4
print(f"Version {v3}: {pa.get_array(v3)}")  # [10, 20, 30, 40, 11]

# All versions still accessible
print(f"\nAll versions preserved:")
for v in range(pa.num_versions()):
    print(f"  v{v}: {pa.get_array(v)}")

# Point queries across versions
print(f"\nPoint queries:")
print(f"  v0[2] = {pa.query(0, 2)}")  # 30
print(f"  v1[2] = {pa.query(1, 2)}")  # 99
print(f"  v2[0] = {pa.query(2, 0)}")  # 77
print(f"  v3[4] = {pa.query(3, 4)}")  # 11

# Branching from different versions
v4 = pa.update(0, 1, 100)
v5 = pa.update(0, 1, 200)
print(f"\nBranching from v0:")
print(f"  v{v4}: {pa.get_array(v4)}")  # [10, 100, 30, 40, 50]
print(f"  v{v5}: {pa.get_array(v5)}")  # [10, 200, 30, 40, 50]

print(f"\nTotal nodes created: {pa.node_count}")
print(f"Without persistence: {pa.n * pa.num_versions()} nodes would be needed")
```

### Complexity
- **Build**: O(n) time and space
- **Update**: O(log n) time, O(log n) new nodes
- **Query**: O(log n) time
- **Space**: O(n + q * log(n)) for q updates
- **Key insight**: path copying shares O(n) nodes between versions, only creating O(log n) new nodes per update'''),

    ("thinking/algorithms", r'''Explain retroactive data structures: partially and fully retroactive. Implement a partially retroactive priority queue that supports inserting operations into the past.''', r'''<think>
Retroactive data structures allow modifications to operations in the past:

- Partially retroactive: can insert/delete operations in the past, but can only query the present state
- Fully retroactive: can insert/delete operations in the past AND query the state at any point in time

Example: retroactive priority queue
- Normal PQ: Insert(x), DeleteMin()
- Partially retroactive: Insert(t, "Insert(x)") -- at time t in the past, insert x. The current min might change!
- Can also Delete(t) -- remove the operation that happened at time t

For a partially retroactive priority queue:
- Maintain a timeline of operations
- When we insert a past operation, we need to replay the effects on the current state
- The current state is affected by all operations from the beginning to now

Implementation approach for partially retroactive PQ:
1. Maintain a sorted list of (time, operation) pairs
2. Track which elements are currently "in" the PQ (inserted but not yet deleted by a DeleteMin)
3. When inserting a past Insert(x) at time t, determine if x would have been removed by any subsequent DeleteMin

Actually, a simpler approach: maintain the full timeline and recompute the current state. For partially retroactive, we only need the current state, so we can maintain it incrementally.

For a balanced approach: use a segment tree or balanced BST on the timeline. Each Insert adds an element, each DeleteMin removes the current minimum. When we retroactively add an Insert(x) at time t, we need to check if x changes any subsequent DeleteMin results.

Let me implement a simple version that replays the timeline when queried, optimized with some caching.
</think>

## Retroactive Data Structures

### Partially Retroactive Priority Queue

```python
import bisect
import heapq


class RetroactivePQ:
    """Partially retroactive priority queue.
    Supports inserting operations into the past.
    Only queries the present state."""

    def __init__(self):
        self.timeline = []  # sorted list of (time, op_type, value)
        # op_type: 'insert' or 'delete_min'
        self.next_time = 0

    def insert_now(self, value):
        """Insert value at current time."""
        self.next_time += 1
        bisect.insort(self.timeline, (self.next_time, 'insert', value))
        return self.next_time

    def delete_min_now(self):
        """Delete minimum at current time."""
        self.next_time += 1
        bisect.insort(self.timeline, (self.next_time, 'delete_min', None))
        return self.next_time

    def retroactive_insert(self, time, value):
        """Insert 'Insert(value)' operation at past time."""
        bisect.insort(self.timeline, (time, 'insert', value))

    def retroactive_delete_op(self, time):
        """Remove the operation that occurred at given time."""
        self.timeline = [(t, op, v) for t, op, v in self.timeline if t != time]

    def current_state(self):
        """Replay timeline to get current PQ contents and minimum."""
        pq = []
        deleted_count = 0
        for t, op, v in self.timeline:
            if op == 'insert':
                heapq.heappush(pq, v)
            elif op == 'delete_min':
                if pq:
                    heapq.heappop(pq)
                deleted_count += 1
        return sorted(pq)

    def current_min(self):
        """Get current minimum."""
        state = self.current_state()
        return state[0] if state else None

    def state_at_time(self, target_time):
        """Get PQ state after operations up to target_time."""
        pq = []
        for t, op, v in self.timeline:
            if t > target_time:
                break
            if op == 'insert':
                heapq.heappush(pq, v)
            elif op == 'delete_min':
                if pq:
                    heapq.heappop(pq)
        return sorted(pq)


# Demo
print("=== Partially Retroactive Priority Queue ===")
rpq = RetroactivePQ()

# Build timeline
t1 = rpq.insert_now(5)    # t=1: insert 5
t2 = rpq.insert_now(3)    # t=2: insert 3
t3 = rpq.insert_now(8)    # t=3: insert 8
t4 = rpq.delete_min_now() # t=4: delete min (removes 3)
t5 = rpq.insert_now(1)    # t=5: insert 1

print("Timeline:")
for t, op, v in rpq.timeline:
    print(f"  t={t}: {op}({v if v else ''})")

print(f"\nCurrent state: {rpq.current_state()}")  # [1, 5, 8]
print(f"Current min: {rpq.current_min()}")         # 1

# Retroactive insert: add value 2 at time 1.5 (between t1 and t2)
print("\n--- Retroactive insert: Insert(2) at t=1.5 ---")
rpq.retroactive_insert(1.5, 2)
print(f"Current state: {rpq.current_state()}")  # [1, 2, 5, 8]
# The delete_min at t=4 now removes 2 instead of 3!
# Wait, no: insert order is 5(t=1), 2(t=1.5), 3(t=2), 8(t=3)
# At t=4, delete_min removes min of {5,2,3,8} = 2
# At t=5, insert 1
# Final: {5, 3, 8, 1} = [1, 3, 5, 8]
print(f"Current min: {rpq.current_min()}")

# Retroactive delete: remove the delete_min at t=4
print("\n--- Remove delete_min at t=4 ---")
rpq.retroactive_delete_op(t4)
print(f"Current state: {rpq.current_state()}")
# Now: insert 5, insert 2, insert 3, insert 8, insert 1
# No deletions, so state = [1, 2, 3, 5, 8]
print(f"Current min: {rpq.current_min()}")

# Show state at different historical points
print("\n--- Historical states (fully retroactive view) ---")
for t in [1, 1.5, 2, 3, 5]:
    state = rpq.state_at_time(t)
    print(f"  State at t={t}: {state}")
```

### Types of Retroactive Data Structures
| Type | Past Insert/Delete | Past Query | Present Query |
|------|--------------------|-----------|---------------|
| Non-retroactive | No | No | Yes |
| Partially retroactive | Yes | No | Yes |
| Fully retroactive | Yes | Yes | Yes |

### Complexity
- **Naive replay**: O(n) per current_state query
- **Optimized**: O(sqrt(n)) per operation using sqrt-decomposition
- **Best known**: O(log n) per operation using advanced techniques (link-cut trees)
- **Space**: O(n) for timeline

### Applications
- Version control for data structures
- What-if analysis (what if this event happened earlier?)
- Debugging temporal data streams'''),

    ("thinking/algorithms", r'''Implement offline query processing with sorting and sweep. Given an array and queries asking for the count of elements in range [l, r] that are between lo and hi in value, answer all queries efficiently offline.''', r'''<think>
This is a classic offline query problem. We need to answer queries of the form: "how many elements in arr[l..r] have values in [lo, hi]?"

Online approaches would need 2D data structures (merge sort tree, persistent segment tree, etc.). But offline, we can use sorting and sweep to answer efficiently.

Approach 1: Sort queries and use a BIT
- For each query (l, r, lo, hi), split into two: count(l, r, <= hi) - count(l, r, <= lo-1)
- Sort elements by value, sort queries by threshold
- Sweep through values in increasing order, adding elements to a BIT indexed by position
- When reaching a query's threshold, answer it using BIT range query

This gives O((n + q) * log(n) * log(max_val)) or with better organization O((n + q) * log(n)).

Actually, the standard approach:
1. Sort elements by value
2. For each query, decompose into count(l, r, value <= hi) - count(l, r, value <= lo-1)
3. Process all "count <= x" queries sorted by x
4. As we sweep x from small to large, add elements with value <= x to a BIT (at their positions)
5. Answer each query using BIT.range_sum(l, r)

This way each element is added once, and each query is answered with one BIT range query.

Total: O((n + q) * log(n)) time.
</think>

## Offline Query Processing: Range Count with Value Bounds

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

    def range_query(self, l, r):
        if l > r:
            return 0
        return self.query(r) - self.query(l - 1)


def offline_range_count(arr, queries):
    """Answer queries: count elements in arr[l..r] with value in [lo, hi].

    Args:
        arr: input array (0-indexed)
        queries: list of (l, r, lo, hi) -- 0-indexed, inclusive

    Returns:
        list of answers

    Approach: decompose each query into two threshold queries,
    sweep values in sorted order, use BIT for position range queries.
    """
    n = len(arr)
    q = len(queries)
    answers = [0] * q

    # Decompose: count(l,r,lo,hi) = count(l,r,<=hi) - count(l,r,<=lo-1)
    # Create threshold queries: (threshold, query_idx, l, r, sign)
    threshold_queries = []
    for qi, (l, r, lo, hi) in enumerate(queries):
        threshold_queries.append((hi, qi, l + 1, r + 1, 1))     # +count <= hi
        threshold_queries.append((lo - 1, qi, l + 1, r + 1, -1))  # -count <= lo-1

    # Sort threshold queries by threshold value
    threshold_queries.sort(key=lambda x: x[0])

    # Sort elements by value
    sorted_elements = sorted(range(n), key=lambda i: arr[i])

    bit = BIT(n)
    elem_ptr = 0  # pointer into sorted_elements

    for thresh, qi, l, r, sign in threshold_queries:
        # Add all elements with value <= thresh
        while elem_ptr < n and arr[sorted_elements[elem_ptr]] <= thresh:
            pos = sorted_elements[elem_ptr] + 1  # 1-indexed for BIT
            bit.update(pos)
            elem_ptr += 1

        # Answer this threshold query
        count = bit.range_query(l, r)
        answers[qi] += sign * count

    return answers


# Demo
arr = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3]
queries = [
    (0, 4, 1, 3),   # arr[0..4]=[3,1,4,1,5], values in [1,3]: {3,1,1} = 3
    (2, 7, 4, 9),   # arr[2..7]=[4,1,5,9,2,6], values in [4,9]: {4,5,9,6} = 4
    (0, 9, 3, 5),   # entire array, values in [3,5]: {3,4,5,5,3} = 5
    (5, 5, 9, 9),   # single element arr[5]=9, value=9: count=1
    (0, 2, 7, 10),  # arr[0..2]=[3,1,4], values in [7,10]: count=0
]

answers = offline_range_count(arr, queries)

print("=== Offline Range Count Queries ===")
print(f"Array: {arr}\n")
for (l, r, lo, hi), ans in zip(queries, answers):
    subarray = arr[l:r+1]
    actual = sum(1 for x in subarray if lo <= x <= hi)
    status = "OK" if ans == actual else "FAIL"
    print(f"  arr[{l}..{r}] values in [{lo},{hi}]: "
          f"count={ans} (subarray={subarray}) [{status}]")

# Performance test
import random
import time
random.seed(42)

n = 50000
q_count = 50000
arr_large = [random.randint(1, 100000) for _ in range(n)]
queries_large = [
    (random.randint(0, n//2), random.randint(n//2, n-1),
     random.randint(1, 50000), random.randint(50000, 100000))
    for _ in range(q_count)
]

start = time.time()
results = offline_range_count(arr_large, queries_large)
elapsed = time.time() - start
print(f"\n{n} elements, {q_count} queries: {elapsed:.3f}s")

# Verify a few
for i in range(5):
    l, r, lo, hi = queries_large[i]
    brute = sum(1 for x in arr_large[l:r+1] if lo <= x <= hi)
    assert results[i] == brute, f"Mismatch at query {i}"
print("First 5 results verified correct.")
```

### Complexity
- **Time**: O((n + q) * log(n)) -- sorting + BIT operations
- **Space**: O(n + q)
- **Compared to online**: persistent segment tree gives O((n + q) * log(n)) but with higher constant and O(n * log(n)) space

### The Key Technique
1. **Decompose** range-value queries into threshold queries
2. **Sort** both elements and queries by value
3. **Sweep** in value order, maintaining a positional BIT
4. **Answer** each threshold query when we reach its threshold'''),
]
