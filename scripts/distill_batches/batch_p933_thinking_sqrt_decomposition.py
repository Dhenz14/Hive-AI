PAIRS = [
    ("thinking/algorithms", r'''Implement Mo's algorithm for answering offline range queries. Given an array and queries [l, r], answer each query for the number of distinct elements in the range. Explain the block-based ordering and its complexity.''', r'''<think>
Mo's algorithm for offline range queries. The naive approach answers each query independently in O(n), giving O(nq) total. Can we do better by reordering queries cleverly?

The core insight: if we maintain a "current range" with left and right pointers, and can add/remove elements from the edges in O(1), then the total cost depends on how far we move the pointers across all queries. The question is: what ordering minimizes total pointer movement?

I initially considered sorting queries by l, but then r could jump all over the place. Sorting by r has the same problem with l. What if we do something hybrid?

The trick is block-based sorting: divide indices into blocks of size sqrt(n). Sort queries by (block of l, r). This ensures:
1. Within a block of l, r only moves forward -- so O(n) total r movement per block
2. l moves at most sqrt(n) between consecutive queries in the same block
3. There are sqrt(n) blocks, so total r movement is O(n * sqrt(n))
4. Total l movement: O(q * sqrt(n))

Combined: O((n + q) * sqrt(n)). That is much better than O(nq).

For counting distinct elements, I maintain a frequency array. When adding an element, if freq goes 0->1, increment distinct count. When removing, if freq goes 1->0, decrement. Both O(1).

Hmm, actually there is a nice optimization I should include: for even-numbered blocks, sort r in decreasing order. This way r alternates direction between consecutive blocks instead of resetting to the start, reducing total r movement by roughly 2x in practice.
</think>

## Mo's Algorithm for Offline Range Queries

### Core Idea
Sort queries by (block_of_l, r) to minimize pointer movement. Total complexity: O((n + q) * sqrt(n)).

### Implementation: Count Distinct Elements in Range

```python
import math


def mo_algorithm(arr, queries):
    """Answer range queries [l, r] for count of distinct elements.

    Args:
        arr: input array (0-indexed)
        queries: list of (l, r) pairs (inclusive, 0-indexed)

    Returns:
        list of answers in original query order
    """
    n = len(arr)
    q = len(queries)
    if q == 0:
        return []

    block_size = max(1, int(math.sqrt(n)))

    # Sort queries by (block of l, r with alternating direction)
    indexed_queries = [(l, r, i) for i, (l, r) in enumerate(queries)]
    indexed_queries.sort(
        key=lambda x: (
            x[0] // block_size,
            x[1] if (x[0] // block_size) % 2 == 0 else -x[1]
        )
    )

    # Frequency array and distinct counter
    freq = [0] * (max(arr) + 1) if arr else []
    distinct = 0
    answers = [0] * q

    cur_l, cur_r = 0, -1  # empty range initially

    def add(idx):
        nonlocal distinct
        val = arr[idx]
        if freq[val] == 0:
            distinct += 1
        freq[val] += 1

    def remove(idx):
        nonlocal distinct
        val = arr[idx]
        freq[val] -= 1
        if freq[val] == 0:
            distinct -= 1

    for ql, qr, qi in indexed_queries:
        # Expand/shrink to reach [ql, qr]
        while cur_r < qr:
            cur_r += 1
            add(cur_r)
        while cur_l > ql:
            cur_l -= 1
            add(cur_l)
        while cur_r > qr:
            remove(cur_r)
            cur_r -= 1
        while cur_l < ql:
            remove(cur_l)
            cur_l += 1

        answers[qi] = distinct

    return answers


# Demo
arr = [1, 2, 1, 3, 2, 1, 4, 3, 2, 1]
queries = [
    (0, 3),   # [1,2,1,3] -> 3 distinct
    (2, 5),   # [1,3,2,1] -> 3 distinct
    (0, 9),   # entire array -> 4 distinct
    (5, 7),   # [1,4,3] -> 3 distinct
    (3, 3),   # [3] -> 1 distinct
]

answers = mo_algorithm(arr, queries)
for (l, r), ans in zip(queries, answers):
    print(f"  [{l},{r}] = {arr[l:r+1]} -> {ans} distinct")

# Verify with brute force
for (l, r), ans in zip(queries, answers):
    brute = len(set(arr[l:r+1]))
    assert ans == brute, f"Mismatch at [{l},{r}]: {ans} vs {brute}"
print("\nAll answers verified correct.")
```

### Complexity Analysis
- **Block size**: B = sqrt(n)
- **Left pointer**: moves at most B per query -> O(q * B) total
- **Right pointer**: for each block, moves at most n -> O(n * n/B) = O(n * sqrt(n)) total
- **Overall**: O((n + q) * sqrt(n))
- **Space**: O(n + max_value) for frequency array'''),

    ("thinking/algorithms", r'''Implement block (sqrt) decomposition for range sum queries with point updates. Compare its simplicity and performance trade-offs against segment trees and BITs.''', r'''<think>
Sqrt decomposition for range sum queries. The idea is to divide the array into blocks of size ~sqrt(n), each with a precomputed sum.

For point updates, we just update the element and its block sum -- O(1), which is actually better than segment tree or BIT (those are O(log n) for updates). That is a nice advantage I had not considered initially.

For range sum [l, r]: we could have up to 2 partial blocks at the ends and some complete blocks in the middle. The partial blocks we sum element-by-element (at most 2*sqrt(n) elements), and complete blocks use precomputed sums. Total: O(sqrt(n)) per query.

Now, O(sqrt(n)) is worse than O(log n) from segment trees. Is this approach ever worth it? I think yes, for two reasons. First, the constant factor is tiny -- no pointer overhead, no recursion, great cache behavior. For n up to ~10^5, sqrt decomposition is competitive in wall-clock time. Second, and more importantly, sqrt decomposition is incredibly flexible. Operations like "count elements > x in range" are hard with segment trees but easy with sqrt blocks if you keep each block sorted.

We could also use a segment tree here (O(log n) query) or a BIT (same), but for teaching the concept and for problems where the operation does not compose cleanly for a tree structure, sqrt decomposition wins on simplicity.
</think>

## Sqrt (Block) Decomposition for Range Sum

### Implementation

```python
import math


class SqrtDecomposition:
    """Sqrt decomposition for range sum queries with point updates."""

    def __init__(self, arr):
        self.arr = list(arr)
        self.n = len(self.arr)
        self.block_size = max(1, int(math.sqrt(self.n)))
        self.num_blocks = (self.n + self.block_size - 1) // self.block_size
        self.block_sum = [0] * self.num_blocks

        # Precompute block sums
        for i in range(self.n):
            self.block_sum[i // self.block_size] += self.arr[i]

    def update(self, idx, val):
        """Set arr[idx] = val. O(1)."""
        block = idx // self.block_size
        self.block_sum[block] += val - self.arr[idx]
        self.arr[idx] = val

    def query(self, l, r):
        """Sum of arr[l..r] inclusive. O(sqrt(n))."""
        total = 0
        bl = l // self.block_size
        br = r // self.block_size

        if bl == br:
            # Same block: just iterate
            for i in range(l, r + 1):
                total += self.arr[i]
            return total

        # Left partial block
        for i in range(l, (bl + 1) * self.block_size):
            total += self.arr[i]

        # Full blocks in the middle
        for b in range(bl + 1, br):
            total += self.block_sum[b]

        # Right partial block
        for i in range(br * self.block_size, r + 1):
            total += self.arr[i]

        return total


# Demo
arr = list(range(1, 17))  # [1, 2, 3, ..., 16]
sd = SqrtDecomposition(arr)

print(f"Block size: {sd.block_size}")
print(f"Array: {sd.arr}")
print(f"Block sums: {sd.block_sum}")

# Queries
print(f"\nSum [0, 15] = {sd.query(0, 15)}")   # 136
print(f"Sum [3, 7]  = {sd.query(3, 7)}")      # 4+5+6+7+8 = 30
print(f"Sum [5, 5]  = {sd.query(5, 5)}")      # 6

# Update
sd.update(4, 100)  # change arr[4] from 5 to 100
print(f"\nAfter arr[4] = 100:")
print(f"Sum [3, 7]  = {sd.query(3, 7)}")      # 4+100+6+7+8 = 125

# Verify
assert sd.query(3, 7) == sum(sd.arr[3:8])
print("Verified correct.")
```

### Comparison with Other Structures

```
| Feature          | Sqrt Decomp  | BIT       | Segment Tree |
|-----------------|-------------|-----------|-------------|
| Update          | O(1)        | O(log n)  | O(log n)    |
| Range query     | O(sqrt(n))  | O(log n)  | O(log n)    |
| Implementation  | ~30 lines   | ~20 lines | ~50 lines   |
| Flexibility     | High        | Low       | Medium      |
| Cache behavior  | Good        | Good      | Moderate    |
| Lazy propagation| Easy        | Hard      | Moderate    |
```

### When to Choose Sqrt Decomposition
- **Prototyping**: fastest to implement correctly
- **Complex operations**: e.g., "count elements > x in range" (keep blocks sorted)
- **Tight time limits with small n**: competitive due to low constant factor
- **Add/remove elements**: easier to maintain than tree structures

### Complexity
- **Point update**: O(1)
- **Range query**: O(sqrt(n))
- **Build**: O(n)
- **Space**: O(n)'''),

    ("thinking/algorithms", r'''Implement sqrt decomposition on trees. Given a tree with weighted nodes, support path queries (sum of weights from u to v) and point updates. Use heavy path decomposition with sqrt blocks.''', r'''<think>
Sqrt decomposition on trees -- this is less common than HLD + segment tree, but the question asks for it specifically. Let me think about the approach.

My first thought: flatten the tree with an Euler tour, then apply sqrt decomposition on the flat array. For subtree queries this works directly (contiguous range in the Euler tour), but for path queries (u to v) I need to decompose the path somehow. I would need LCA and then the path splits into u->LCA and v->LCA.

But wait, Euler tour does not give contiguous ranges for arbitrary paths -- only for subtrees and for paths when combined with HLD. So I think the right approach is: use HLD to decompose the tree into chains, flatten with HLD ordering, then use sqrt decomposition on the flat array instead of a segment tree.

I initially considered doing sqrt decomposition on each chain separately, but that complicates the indexing. Since HLD already gives a flat ordering where each chain is contiguous, I can just do one big sqrt decomposition on the entire flat array. Path queries become O(log n) range queries on the flat array (one per chain segment), each costing O(sqrt(n)), giving O(log(n) * sqrt(n)) total.

For point updates: just O(1) to update the flat array element and its block sum. Actually that is a nice advantage over the segment tree version which would be O(log n) for updates.

Let me implement:
1. HLD to decompose paths into O(log n) chains
2. Flatten with HLD position assignment
3. Sqrt decomposition on the flat array
4. Path query = sum of O(log n) range queries
5. Point update = O(1)
</think>

## Sqrt Decomposition on Trees

### Approach
Flatten the tree with HLD, then use sqrt decomposition on the flat array for path queries.

### Implementation

```python
import math
from collections import defaultdict


class TreeSqrt:
    """Tree path queries using HLD + sqrt decomposition."""

    def __init__(self, n):
        self.n = n
        self.adj = defaultdict(list)
        self.weight = [0] * n

    def add_edge(self, u, v):
        self.adj[u].append(v)
        self.adj[v].append(u)

    def build(self, root=0):
        """Build HLD and sqrt decomposition."""
        # BFS-based HLD setup (avoid recursion limit)
        self.parent = [-1] * self.n
        self.depth = [0] * self.n
        self.subtree_size = [1] * self.n
        self.heavy = [-1] * self.n
        self.head = [0] * self.n  # chain head
        self.pos = [0] * self.n   # position in flat array
        self.flat = [0] * self.n  # flat array of weights

        # BFS to compute parent, depth, subtree sizes
        order = []
        visited = [False] * self.n
        stack = [root]
        visited[root] = True
        while stack:
            u = stack.pop()
            order.append(u)
            for v in self.adj[u]:
                if not visited[v]:
                    visited[v] = True
                    self.parent[v] = u
                    self.depth[v] = self.depth[u] + 1
                    stack.append(v)

        # Compute subtree sizes and heavy children (bottom-up)
        for u in reversed(order):
            max_size = 0
            for v in self.adj[u]:
                if v != self.parent[u]:
                    self.subtree_size[u] += self.subtree_size[v]
                    if self.subtree_size[v] > max_size:
                        max_size = self.subtree_size[v]
                        self.heavy[u] = v

        # Assign positions via HLD
        timer = [0]

        def assign(u, h):
            self.head[u] = h
            self.pos[u] = timer[0]
            self.flat[timer[0]] = self.weight[u]
            timer[0] += 1
            if self.heavy[u] != -1:
                assign(self.heavy[u], h)
            for v in self.adj[u]:
                if v != self.parent[u] and v != self.heavy[u]:
                    assign(v, v)

        import sys
        sys.setrecursionlimit(self.n + 100)
        assign(root, root)

        # Build sqrt decomposition on flat array
        self.block_size = max(1, int(math.sqrt(self.n)))
        self.num_blocks = (self.n + self.block_size - 1) // self.block_size
        self.block_sum = [0] * self.num_blocks
        for i in range(self.n):
            self.block_sum[i // self.block_size] += self.flat[i]

    def update(self, node, new_weight):
        """Update weight of a node. O(1)."""
        p = self.pos[node]
        diff = new_weight - self.flat[p]
        self.flat[p] = new_weight
        self.block_sum[p // self.block_size] += diff
        self.weight[node] = new_weight

    def _range_sum(self, l, r):
        """Sum of flat[l..r]. O(sqrt(n))."""
        if l > r:
            return 0
        total = 0
        bl, br = l // self.block_size, r // self.block_size
        if bl == br:
            for i in range(l, r + 1):
                total += self.flat[i]
            return total
        for i in range(l, (bl + 1) * self.block_size):
            total += self.flat[i]
        for b in range(bl + 1, br):
            total += self.block_sum[b]
        for i in range(br * self.block_size, r + 1):
            total += self.flat[i]
        return total

    def path_sum(self, u, v):
        """Sum of weights on path u -> v. O(log(n) * sqrt(n))."""
        total = 0
        while self.head[u] != self.head[v]:
            if self.depth[self.head[u]] < self.depth[self.head[v]]:
                u, v = v, u
            total += self._range_sum(self.pos[self.head[u]], self.pos[u])
            u = self.parent[self.head[u]]
        if self.depth[u] > self.depth[v]:
            u, v = v, u
        total += self._range_sum(self.pos[u], self.pos[v])
        return total


# Demo
tree = TreeSqrt(7)
# Tree:    0
#         / \
#        1   2
#       / \   \
#      3   4   5
#     /
#    6
edges = [(0,1), (0,2), (1,3), (1,4), (2,5), (3,6)]
for u, v in edges:
    tree.add_edge(u, v)

tree.weight = [10, 20, 30, 40, 50, 60, 70]
tree.build(root=0)

print(f"Path 6->5: {tree.path_sum(6, 5)}")  # 70+40+20+10+30+60 = 230
print(f"Path 3->4: {tree.path_sum(3, 4)}")  # 40+20+50 = 110
print(f"Path 0->0: {tree.path_sum(0, 0)}")  # 10

tree.update(1, 100)
print(f"After update node 1 to 100:")
print(f"Path 6->5: {tree.path_sum(6, 5)}")  # 70+40+100+10+30+60 = 310
```

### Complexity
- **Build**: O(n)
- **Point update**: O(1)
- **Path query**: O(log(n) * sqrt(n)) -- O(log n) chain segments, each O(sqrt(n))
- **Space**: O(n)'''),

    ("thinking/algorithms", r'''Implement Mo's algorithm with updates (Mo's algorithm with modifications). Handle queries of the form "after applying first t updates, what is the answer for range [l, r]?" Show the 3D block sorting approach.''', r'''<think>
Mo's algorithm with updates -- the standard Mo's algorithm assumes static data, but what if updates are interleaved with queries? We need to add a time dimension.

My first thought: just re-run standard Mo's after each update, but that is obviously too slow. What if we incorporate updates into the query sorting?

Each query now has three parameters: (l, r, t) where t is the number of updates applied before this query. So we have three "pointers" to maintain: cur_l, cur_r, and cur_t. We move l and r as in standard Mo's, and additionally move t forward/backward by applying/reverting updates.

But what block size should we use? With standard Mo's we use sqrt(n), but now we have a third dimension. Let me think... if the block size is B, then:
- l movement: O(q * B) per block transition
- r movement: O(n * n/B) = O(n^2/B)
- t movement: O(U * n^2/B^2) where U = number of updates

Hmm, actually the standard analysis says block size n^(2/3) gives O(n^(5/3)) total. That makes sense because we are balancing three dimensions instead of two.

For applying/reverting updates, there is a clever trick: store the old value, swap it with the new value when applying, and when reverting just swap again. Since each update stores both old and new values, applying it is its own inverse. This means apply_update and revert_update are the same operation -- just a swap.

Wait, I need to be careful: if the updated position is within the current [cur_l, cur_r] range, I also need to remove the old value from the frequency count and add the new one. If it is outside the range, just update the working array. Let me implement this carefully.
</think>

## Mo's Algorithm with Updates

### Extension to Handle Modifications
Add a time dimension to queries. Each query is (l, r, t) where t updates have been applied. Sort by blocks of size n^(2/3).

### Implementation

```python
def mo_with_updates(n, arr, updates, queries):
    """Mo's algorithm handling interleaved updates and range queries.

    Args:
        n: array size
        arr: initial array (0-indexed)
        updates: list of (pos, new_val) -- point updates
        queries: list of (l, r, t) -- range query after t updates applied
                 t is 0-indexed into updates list

    Returns:
        count of distinct elements for each query
    """
    arr = list(arr)
    q = len(queries)
    if q == 0:
        return []

    block = max(1, int(round(n ** (2.0 / 3))))

    # Sort queries by (block(l), block(r), t)
    indexed = [(l, r, t, i) for i, (l, r, t) in enumerate(queries)]
    indexed.sort(key=lambda x: (
        x[0] // block,
        x[1] // block,
        x[2]
    ))

    # Prepare update history: store old values
    # When applying update[i], we swap arr[pos] with new_val
    update_old = [0] * len(updates)
    for i, (pos, new_val) in enumerate(updates):
        update_old[i] = 0  # will be filled during processing

    # Working copy of array
    work = list(arr)
    max_val = max(arr) + 1
    for pos, val in updates:
        max_val = max(max_val, val + 1)

    freq = [0] * max_val
    distinct = 0
    answers = [0] * q

    cur_l, cur_r, cur_t = 0, -1, 0

    def add(idx):
        nonlocal distinct
        v = work[idx]
        if freq[v] == 0:
            distinct += 1
        freq[v] += 1

    def remove(idx):
        nonlocal distinct
        v = work[idx]
        freq[v] -= 1
        if freq[v] == 0:
            distinct -= 1

    def apply_update(t_idx):
        """Apply update t_idx, saving old value."""
        pos, new_val = updates[t_idx]
        old_val = work[pos]
        # If pos is in current range, remove old and add new
        if cur_l <= pos <= cur_r:
            remove(pos)
            work[pos] = new_val
            add(pos)
        else:
            work[pos] = new_val
        # Store old value so we can revert
        updates[t_idx] = (pos, old_val)

    def revert_update(t_idx):
        """Revert update t_idx (same as apply since it swaps)."""
        apply_update(t_idx)

    for ql, qr, qt, qi in indexed:
        # Move time pointer
        while cur_t < qt:
            apply_update(cur_t)
            cur_t += 1
        while cur_t > qt:
            cur_t -= 1
            revert_update(cur_t)

        # Expand/shrink range
        while cur_r < qr:
            cur_r += 1
            add(cur_r)
        while cur_l > ql:
            cur_l -= 1
            add(cur_l)
        while cur_r > qr:
            remove(cur_r)
            cur_r -= 1
        while cur_l < ql:
            remove(cur_l)
            cur_l += 1

        answers[qi] = distinct

    return answers


# Demo
arr = [1, 2, 3, 1, 2]
updates = [
    (2, 1),  # update 0: arr[2] = 1
    (0, 5),  # update 1: arr[0] = 5
]
queries = [
    (0, 4, 0),  # before any updates: [1,2,3,1,2] -> 3 distinct
    (0, 4, 1),  # after update 0: [1,2,1,1,2] -> 2 distinct
    (0, 4, 2),  # after updates 0,1: [5,2,1,1,2] -> 3 distinct
    (1, 3, 1),  # after update 0: [2,1,1] -> 2 distinct
]

answers = mo_with_updates(5, arr, updates, queries)
for (l, r, t), ans in zip(queries, answers):
    print(f"  [{l},{r}] after {t} updates -> {ans} distinct")
```

### Complexity
- **Block size**: B = n^(2/3)
- **Time**: O((n + q) * n^(2/3))
- **Space**: O(n + max_value)
- **Compared to standard Mo's**: one extra dimension adds n^(1/6) factor'''),

    ("thinking/algorithms", r'''Implement heavy-light decomposition (HLD) combined with sqrt decomposition for answering path maximum queries on a weighted tree. Support path queries and edge weight updates.''', r'''<think>
HLD + sqrt decomposition for path maximum queries on a weighted tree. Let me think through the design.

HLD gives us O(log n) chain segments per path query. For each chain segment, we need a range maximum query. With a segment tree, that would be O(log n) per segment. With sqrt decomposition, it is O(sqrt(n)) per segment. So the total is O(log(n) * sqrt(n)) -- worse asymptotically than HLD + segment tree's O(log^2 n), but simpler to implement.

For edge weights, I need to decide where to store them. I could store edge weights on nodes -- specifically, push each edge's weight to the child node (the one farther from root). Then path queries become node queries. But wait, I need to exclude the LCA node from the query, because the LCA's stored value represents the edge from the LCA to its parent, which is not on the u-to-v path. So when u and v are on the same chain, I query pos[u]+1 to pos[v] (excluding u, the higher node).

For the sqrt blocks: each block stores a precomputed maximum. Range max query checks partial blocks element-by-element, full blocks by precomputed max -- O(sqrt(n)).

Hmm, what about updates? After updating an edge weight, I need to recompute the block maximum. I initially thought this would be O(1), but actually recomputing max for a block requires scanning the entire block -- O(sqrt(n)). That is still acceptable since it matches the query cost. With a segment tree, updates would be O(log n), so we trade faster queries for simpler code.
</think>

## HLD + Sqrt Decomposition for Path Maximum Queries

### Implementation

```python
import math
from collections import defaultdict


class HLDSqrtMax:
    """HLD with sqrt decomposition for path maximum and edge updates."""

    def __init__(self, n):
        self.n = n
        self.adj = defaultdict(list)  # adj[u] = [(v, weight), ...]

    def add_edge(self, u, v, w):
        self.adj[u].append((v, w))
        self.adj[v].append((u, w))

    def build(self, root=0):
        import sys
        sys.setrecursionlimit(self.n + 100)

        self.parent = [-1] * self.n
        self.depth = [0] * self.n
        self.sz = [1] * self.n
        self.heavy = [-1] * self.n
        self.head = [0] * self.n
        self.pos = [0] * self.n
        self.edge_node = {}  # (u,v) -> child node holding edge weight
        self.flat = [0] * self.n  # flat array: edge weight at child node

        # BFS for parent/depth
        order = []
        visited = [False] * self.n
        stack = [root]
        visited[root] = True
        while stack:
            u = stack.pop()
            order.append(u)
            for v, w in self.adj[u]:
                if not visited[v]:
                    visited[v] = True
                    self.parent[v] = u
                    self.depth[v] = self.depth[u] + 1
                    stack.append(v)

        # Bottom-up: subtree sizes and heavy children
        for u in reversed(order):
            best = -1
            for v, w in self.adj[u]:
                if v != self.parent[u]:
                    self.sz[u] += self.sz[v]
                    if best == -1 or self.sz[v] > self.sz[best]:
                        best = v
            self.heavy[u] = best

        # HLD position assignment + assign edge weights to children
        timer = [0]

        def assign(u, h):
            self.head[u] = h
            self.pos[u] = timer[0]
            timer[0] += 1
            # Assign edge weight to this node (edge from parent to u)
            for v, w in self.adj[self.parent[u]] if self.parent[u] >= 0 else []:
                if v == u or (self.parent[u] == -1):
                    break
            if self.heavy[u] != -1:
                assign(self.heavy[u], h)
            for v, w in self.adj[u]:
                if v != self.parent[u] and v != self.heavy[u]:
                    assign(v, v)

        assign(root, root)

        # Map edge weights to child nodes in flat array
        for u in range(self.n):
            for v, w in self.adj[u]:
                if self.parent[v] == u:
                    self.flat[self.pos[v]] = w
                    self.edge_node[(u, v)] = v
                    self.edge_node[(v, u)] = v

        # Build sqrt blocks for max
        self.bs = max(1, int(math.sqrt(self.n)))
        self.nb = (self.n + self.bs - 1) // self.bs
        self.block_max = [0] * self.nb
        for i in range(self.n):
            b = i // self.bs
            self.block_max[b] = max(self.block_max[b], self.flat[i])

    def update_edge(self, u, v, new_w):
        """Update weight of edge (u,v). O(sqrt(n))."""
        child = self.edge_node[(u, v)]
        p = self.pos[child]
        self.flat[p] = new_w
        # Recompute block max
        b = p // self.bs
        start = b * self.bs
        end = min(start + self.bs, self.n)
        self.block_max[b] = max(self.flat[start:end])

    def _range_max(self, l, r):
        if l > r:
            return 0
        result = 0
        bl, br = l // self.bs, r // self.bs
        if bl == br:
            for i in range(l, r + 1):
                result = max(result, self.flat[i])
            return result
        for i in range(l, (bl + 1) * self.bs):
            result = max(result, self.flat[i])
        for b in range(bl + 1, br):
            result = max(result, self.block_max[b])
        for i in range(br * self.bs, r + 1):
            result = max(result, self.flat[i])
        return result

    def path_max(self, u, v):
        """Maximum edge weight on path u->v. O(log(n)*sqrt(n))."""
        result = 0
        while self.head[u] != self.head[v]:
            if self.depth[self.head[u]] < self.depth[self.head[v]]:
                u, v = v, u
            result = max(result, self._range_max(
                self.pos[self.head[u]], self.pos[u]))
            u = self.parent[self.head[u]]
        if self.depth[u] > self.depth[v]:
            u, v = v, u
        # Exclude LCA node (pos[u]), query pos[u]+1 to pos[v]
        if u != v:
            result = max(result, self._range_max(
                self.pos[u] + 1, self.pos[v]))
        return result


# Demo
tree = HLDSqrtMax(6)
edges = [(0,1,10), (0,2,20), (1,3,30), (1,4,15), (2,5,25)]
for u, v, w in edges:
    tree.add_edge(u, v, w)
tree.build(0)

print(f"Path max 3->5: {tree.path_max(3, 5)}")  # max(30,10,20,25) = 30
print(f"Path max 3->4: {tree.path_max(3, 4)}")  # max(30,15) = 30
print(f"Path max 4->5: {tree.path_max(4, 5)}")  # max(15,10,20,25) = 25

tree.update_edge(1, 3, 5)  # reduce edge 1-3 from 30 to 5
print(f"\nAfter edge(1,3)=5:")
print(f"Path max 3->5: {tree.path_max(3, 5)}")  # max(5,10,20,25) = 25
```

### Complexity
- **Build**: O(n)
- **Edge update**: O(sqrt(n)) to recompute block max
- **Path query**: O(log(n) * sqrt(n))
- **Space**: O(n)'''),
]
