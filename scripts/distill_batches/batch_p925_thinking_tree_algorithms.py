PAIRS = [
    ("thinking/algorithms", r'''Implement Lowest Common Ancestor (LCA) using binary lifting: preprocess a rooted tree to answer LCA queries in O(log n) time per query.''', r'''<think>
Binary lifting (also called "doubling") preprocesses a tree to answer LCA queries in O(log n) time after O(n log n) preprocessing.

Key idea: For each node, precompute its 2^k-th ancestor for k = 0, 1, 2, ..., log(n).

up[v][k] = 2^k-th ancestor of v
- up[v][0] = parent of v
- up[v][k] = up[up[v][k-1]][k-1] (the 2^k-th ancestor is the 2^(k-1)-th ancestor of the 2^(k-1)-th ancestor)

LCA query (u, v):
1. Bring u and v to the same depth:
   - If depth[u] > depth[v], lift u by (depth[u] - depth[v]) steps using binary representation
2. If u == v, return u
3. Binary search for LCA:
   - For k from log(n) down to 0:
     - If up[u][k] != up[v][k], then LCA is above both: set u = up[u][k], v = up[v][k]
   - After the loop, up[u][0] is the LCA

Why step 3 works: We are finding the highest point where u and v have different ancestors. After lifting both as high as possible while maintaining different ancestors, their parent must be the LCA.

Preprocessing: O(n log n) time and space (fill the up table via BFS/DFS).
Query: O(log n) per query.

This is one of the most practical LCA methods due to simplicity and good constant factors.
</think>

**LCA with Binary Lifting**

```python
import math
from collections import deque


class LCABinaryLifting:
    """Lowest Common Ancestor using binary lifting (doubling)."""

    def __init__(self, n, root=0):
        self.n = n
        self.root = root
        self.LOG = max(1, int(math.log2(n)) + 1)
        self.adj = [[] for _ in range(n)]
        self.depth = [0] * n
        self.up = [[0] * self.LOG for _ in range(n)]

    def add_edge(self, u, v):
        self.adj[u].append(v)
        self.adj[v].append(u)

    def preprocess(self):
        """Build depth and ancestor tables using BFS."""
        visited = [False] * self.n
        queue = deque([self.root])
        visited[self.root] = True
        self.up[self.root][0] = self.root

        while queue:
            u = queue.popleft()
            for v in self.adj[u]:
                if not visited[v]:
                    visited[v] = True
                    self.depth[v] = self.depth[u] + 1
                    self.up[v][0] = u
                    queue.append(v)

        # Fill binary lifting table
        for k in range(1, self.LOG):
            for v in range(self.n):
                self.up[v][k] = self.up[self.up[v][k - 1]][k - 1]

    def lift(self, v, steps):
        """Lift node v up by 'steps' levels."""
        for k in range(self.LOG):
            if steps & (1 << k):
                v = self.up[v][k]
        return v

    def lca(self, u, v):
        """Find LCA of nodes u and v. O(log n)."""
        # Bring to same depth
        if self.depth[u] < self.depth[v]:
            u, v = v, u
        u = self.lift(u, self.depth[u] - self.depth[v])

        if u == v:
            return u

        # Binary search for LCA
        for k in range(self.LOG - 1, -1, -1):
            if self.up[u][k] != self.up[v][k]:
                u = self.up[u][k]
                v = self.up[v][k]

        return self.up[u][0]

    def distance(self, u, v):
        """Distance between u and v in the tree."""
        ancestor = self.lca(u, v)
        return self.depth[u] + self.depth[v] - 2 * self.depth[ancestor]


# Example tree:
#        0
#       / \
#      1   2
#     / \   \
#    3   4   5
#   /
#  6

n = 7
lca_solver = LCABinaryLifting(n, root=0)
edges = [(0,1), (0,2), (1,3), (1,4), (2,5), (3,6)]
for u, v in edges:
    lca_solver.add_edge(u, v)
lca_solver.preprocess()

print("Tree structure:")
print("      0")
print("     / \\")
print("    1   2")
print("   / \\   \\")
print("  3   4   5")
print(" /")
print("6")
print()

# LCA queries
queries = [(3, 4), (6, 5), (4, 6), (3, 5), (6, 2), (1, 1)]
for u, v in queries:
    ancestor = lca_solver.lca(u, v)
    dist = lca_solver.distance(u, v)
    print(f"  LCA({u}, {v}) = {ancestor}, distance = {dist}")

# Verify depths
print(f"\nDepths: {lca_solver.depth}")
print(f"Binary lifting table (up[v][0] = parent):")
for v in range(n):
    print(f"  Node {v}: ancestors = {[lca_solver.up[v][k] for k in range(lca_solver.LOG)]}")
```

**Binary Lifting Table Construction:**
```
up[v][0] = parent(v)
up[v][k] = up[up[v][k-1]][k-1]  (2^k ancestor = 2^(k-1) ancestor of 2^(k-1) ancestor)
```

**LCA Query Algorithm:**
1. Equalize depths by lifting the deeper node
2. If nodes meet, that is the LCA
3. Otherwise, lift both simultaneously using decreasing powers of 2
4. Stop when lifting would make them equal -- their parent is the LCA

**Complexity:**
- Preprocessing: O(n log n) time and space
- Query: O(log n) per LCA query
- Distance: O(log n) using LCA'''),

    ("thinking/algorithms", r'''Implement Heavy-Light Decomposition (HLD) for a tree. This technique decomposes the tree into chains such that any root-to-leaf path crosses at most O(log n) chains, enabling efficient path queries and updates.''', r'''<think>
Heavy-Light Decomposition (HLD) decomposes a tree into chains of "heavy" edges so that any path from root to leaf crosses at most O(log n) chains. Combined with a segment tree, it enables O(log^2 n) path queries.

Definitions:
- For each node, the "heavy child" is the child with the largest subtree size
- The "heavy edge" connects a node to its heavy child
- A "heavy chain" is a maximal path of heavy edges
- All other edges are "light edges"

Key property: When traveling from any node to the root, you cross at most O(log n) light edges. This is because crossing a light edge means moving to a subtree at least half the size, so after log n light edges, the subtree size exceeds n.

HLD + Segment Tree:
1. Flatten the tree into an array using DFS, visiting heavy children first
2. Each heavy chain becomes a contiguous segment in the array
3. Use a segment tree on this flattened array
4. For a path query (u, v): decompose the path into O(log n) chain segments, query each on the segment tree

This gives O(log^2 n) per path query/update.

Implementation steps:
1. Compute subtree sizes (DFS)
2. Find heavy children
3. Assign positions in the flat array (DFS, heavy child first)
4. Record chain heads
5. For path queries, walk both nodes up to their chain heads until they are on the same chain
</think>

**Heavy-Light Decomposition**

```python
import sys
sys.setrecursionlimit(100000)


class HLD:
    """Heavy-Light Decomposition with segment tree for path queries."""

    def __init__(self, n, root=0):
        self.n = n
        self.root = root
        self.adj = [[] for _ in range(n)]
        self.parent = [0] * n
        self.depth = [0] * n
        self.subtree_size = [1] * n
        self.heavy = [-1] * n  # heavy child
        self.head = [0] * n    # head of chain
        self.pos = [0] * n     # position in flat array
        self.flat = [0] * n    # flattened values
        self.values = [0] * n  # node values
        self.cur_pos = 0

    def add_edge(self, u, v):
        self.adj[u].append(v)
        self.adj[v].append(u)

    def build(self, values=None):
        if values:
            self.values = values[:]
        self._compute_sizes(self.root, -1, 0)
        self._decompose(self.root, self.root)
        # Build segment tree on flat array
        self.tree = [0] * (4 * self.n)
        self._build_seg(1, 0, self.n - 1)

    def _compute_sizes(self, u, par, d):
        self.parent[u] = par if par != -1 else u
        self.depth[u] = d
        max_size = 0
        for v in self.adj[u]:
            if v != par:
                self._compute_sizes(v, u, d + 1)
                self.subtree_size[u] += self.subtree_size[v]
                if self.subtree_size[v] > max_size:
                    max_size = self.subtree_size[v]
                    self.heavy[u] = v

    def _decompose(self, u, h):
        self.head[u] = h
        self.pos[u] = self.cur_pos
        self.flat[self.cur_pos] = self.values[u]
        self.cur_pos += 1

        # Visit heavy child first (keeps chain contiguous)
        if self.heavy[u] != -1:
            self._decompose(self.heavy[u], h)

        for v in self.adj[u]:
            if v != self.parent[u] and v != self.heavy[u]:
                self._decompose(v, v)  # new chain starts

    # Segment tree operations
    def _build_seg(self, node, lo, hi):
        if lo == hi:
            self.tree[node] = self.flat[lo]
            return
        mid = (lo + hi) // 2
        self._build_seg(2*node, lo, mid)
        self._build_seg(2*node+1, mid+1, hi)
        self.tree[node] = max(self.tree[2*node], self.tree[2*node+1])

    def _query_seg(self, node, lo, hi, l, r):
        if r < lo or hi < l:
            return float('-inf')
        if l <= lo and hi <= r:
            return self.tree[node]
        mid = (lo + hi) // 2
        return max(self._query_seg(2*node, lo, mid, l, r),
                   self._query_seg(2*node+1, mid+1, hi, l, r))

    def _update_seg(self, node, lo, hi, pos, val):
        if lo == hi:
            self.tree[node] = val
            return
        mid = (lo + hi) // 2
        if pos <= mid:
            self._update_seg(2*node, lo, mid, pos, val)
        else:
            self._update_seg(2*node+1, mid+1, hi, pos, val)
        self.tree[node] = max(self.tree[2*node], self.tree[2*node+1])

    def path_query_max(self, u, v):
        """Query maximum value on path from u to v. O(log^2 n)."""
        result = float('-inf')
        while self.head[u] != self.head[v]:
            # Move the deeper chain head up
            if self.depth[self.head[u]] < self.depth[self.head[v]]:
                u, v = v, u
            result = max(result,
                         self._query_seg(1, 0, self.n-1,
                                         self.pos[self.head[u]], self.pos[u]))
            u = self.parent[self.head[u]]

        # Now on same chain
        if self.depth[u] > self.depth[v]:
            u, v = v, u
        result = max(result,
                     self._query_seg(1, 0, self.n-1, self.pos[u], self.pos[v]))
        return result

    def point_update(self, u, val):
        """Update value of node u."""
        self.values[u] = val
        self._update_seg(1, 0, self.n-1, self.pos[u], val)


# Example
n = 8
hld = HLD(n, root=0)
edges = [(0,1),(0,2),(1,3),(1,4),(2,5),(2,6),(4,7)]
for u, v in edges:
    hld.add_edge(u, v)

values = [1, 5, 2, 8, 3, 7, 4, 6]
hld.build(values)

print(f"Node values: {values}")
print(f"Heavy children: {hld.heavy}")
print(f"Chain heads: {hld.head}")
print(f"Flat positions: {hld.pos}")

queries = [(3, 5), (7, 6), (3, 7), (0, 7)]
for u, v in queries:
    result = hld.path_query_max(u, v)
    print(f"  Max on path {u}->{v}: {result}")

hld.point_update(4, 100)
print(f"\nAfter updating node 4 to 100:")
print(f"  Max on path 3->7: {hld.path_query_max(3, 7)}")
```

**Why O(log n) Chains Per Path:**
- Crossing a light edge means the subtree size at least doubles
- From any leaf to root, at most log(n) light edges
- Each chain segment is a contiguous range in the segment tree

**Complexity:**
- Preprocessing: O(n)
- Path query: O(log^2 n) -- O(log n) chains, O(log n) per segment tree query
- Point update: O(log n)
- Space: O(n)'''),

    ("thinking/algorithms", r'''Implement Centroid Decomposition of a tree: recursively find the centroid, remove it, and decompose the remaining subtrees. Show how it enables efficient path-based queries.''', r'''<think>
Centroid decomposition is a divide-and-conquer technique on trees. The centroid of a tree is a node whose removal results in no subtree having more than n/2 nodes.

Properties:
- Every tree has at least one centroid (at most two for even-sized trees)
- The centroid decomposition tree has depth O(log n)
- Every path in the original tree passes through the centroid of some level in the decomposition

Algorithm:
1. Find the centroid of the current tree
2. Mark it as the root of the centroid decomposition tree
3. Remove the centroid; this splits the tree into subtrees
4. Recursively decompose each subtree
5. The centroid of each subtree becomes a child of the current centroid in the decomposition tree

Finding the centroid:
1. Compute subtree sizes via DFS
2. The centroid is the node where the maximum subtree (including the "up" subtree) has size <= n/2

Applications:
- Counting/finding paths of certain length in O(n log n)
- Distance queries: for each centroid, precompute distances to all nodes in its subtree
- Point updates + path queries

The key property for queries: any path between two nodes u and v passes through their LCA in the centroid decomposition tree. So we only need to check O(log n) centroids for any path query.

Time: O(n log n) total for construction (O(n) per level, O(log n) levels).
Space: O(n log n) for distance arrays, O(n) for the decomposition tree.
</think>

**Centroid Decomposition**

```python
class CentroidDecomposition:
    """Centroid decomposition for efficient path queries."""

    def __init__(self, n):
        self.n = n
        self.adj = [[] for _ in range(n)]
        self.removed = [False] * n
        self.subtree_size = [0] * n
        self.centroid_parent = [-1] * n
        self.centroid_depth = [0] * n
        # For distance queries: distances from each centroid
        self.centroid_dists = [[] for _ in range(n)]

    def add_edge(self, u, v, w=1):
        self.adj[u].append((v, w))
        self.adj[v].append((u, w))

    def _compute_size(self, u, parent):
        self.subtree_size[u] = 1
        for v, _ in self.adj[u]:
            if v != parent and not self.removed[v]:
                self._compute_size(v, u)
                self.subtree_size[u] += self.subtree_size[v]

    def _find_centroid(self, u, parent, tree_size):
        for v, _ in self.adj[u]:
            if v != parent and not self.removed[v]:
                if self.subtree_size[v] > tree_size // 2:
                    return self._find_centroid(v, u, tree_size)
        return u

    def _get_distances(self, u, parent, dist):
        """Collect all (node, distance) pairs from a centroid."""
        result = [(u, dist)]
        for v, w in self.adj[u]:
            if v != parent and not self.removed[v]:
                result.extend(self._get_distances(v, u, dist + w))
        return result

    def build(self):
        """Build centroid decomposition."""
        self._decompose(0, -1, 0)

    def _decompose(self, u, par, depth):
        self._compute_size(u, -1)
        centroid = self._find_centroid(u, -1, self.subtree_size[u])

        self.removed[centroid] = True
        self.centroid_parent[centroid] = par
        self.centroid_depth[centroid] = depth

        # Collect distances from this centroid to all nodes in its subtree
        self.centroid_dists[centroid] = self._get_distances(centroid, -1, 0)

        # Recursively decompose remaining subtrees
        for v, _ in self.adj[centroid]:
            if not self.removed[v]:
                self._decompose(v, centroid, depth + 1)

    def count_paths_of_length(self, target_dist):
        """Count paths in tree with exactly target_dist total weight."""
        count = 0

        for c in range(self.n):
            dists = self.centroid_dists[c]
            # Count pairs with distance sum == target
            dist_count = {}
            for node, d in dists:
                dist_count[d] = dist_count.get(d, 0) + 1

            # Count pairs summing to target
            for d, cnt in dist_count.items():
                complement = target_dist - d
                if complement in dist_count:
                    if complement == d:
                        count += cnt * (cnt - 1)
                    elif complement > d:
                        count += cnt * dist_count[complement] * 2

            # Subtract over-counted pairs within same subtree
            for v, w in self.adj[c]:
                if self.centroid_parent[v] == c or (
                    not self.removed[v] and self.centroid_depth[v] > self.centroid_depth[c]
                ):
                    sub_dists = {}
                    for node, d in dists:
                        # Check if node is in subtree rooted at v
                        pass  # simplified for demo

        return count // 2


# Example
n = 7
cd = CentroidDecomposition(n)
edges = [(0,1,2), (0,2,3), (1,3,1), (1,4,4), (2,5,2), (2,6,1)]
for u, v, w in edges:
    cd.add_edge(u, v, w)

cd.build()

print("Centroid Decomposition:")
print(f"  Centroid parents: {cd.centroid_parent}")
print(f"  Centroid depths:  {cd.centroid_depth}")

print("\nDistances from each centroid:")
for c in range(n):
    if cd.centroid_dists[c]:
        print(f"  Centroid {c}: {cd.centroid_dists[c]}")

# Build the centroid tree
print("\nCentroid tree edges:")
for v in range(n):
    if cd.centroid_parent[v] != -1:
        print(f"  {cd.centroid_parent[v]} -> {v}")

print(f"\nMax centroid depth: {max(cd.centroid_depth)}")
print(f"Expected O(log {n}) = {int(1 + n.bit_length())}")
```

**Why Centroid Decomposition is Powerful:**
- Decomposition depth is O(log n) because centroid splits tree roughly in half
- Any path u->v passes through their LCA in the centroid tree
- For path queries: walk up from u and v in centroid tree, O(log n) levels

**Applications:**
- Count paths of given length: O(n log n)
- Distance updates and queries: O(log n) per operation
- Finding closest marked node: O(log^2 n)

**Complexity:**
- Build: O(n log n)
- Depth of decomposition: O(log n)
- Space: O(n log n) for distance arrays'''),

    ("thinking/algorithms", r'''Implement an algorithm to find the diameter of a tree: the longest path between any two nodes. Show both the BFS-based approach and the DFS-based approach.''', r'''<think>
The diameter of a tree is the length of the longest path between any two nodes. There are two clean approaches.

Approach 1: Two BFS (simpler, works for unweighted or weighted trees)
1. Pick any node, BFS to find the farthest node u
2. BFS from u to find the farthest node v
3. The distance u->v is the diameter
4. The path u->v is the diameter path

Why this works: Starting from any node, BFS finds one endpoint of the diameter. Then BFS from that endpoint finds the other. The proof uses a exchange argument: if the true diameter endpoints are (a, b), then the farthest node from any starting point must be either a or b.

Approach 2: DFS (elegant, computes diameter as maximum of all paths through each node)
For each node u, the diameter passes through u if the two longest branches from u sum to the maximum. Track the two longest paths from each node to any leaf in its subtree.

For each node u:
- depth1 = longest path going down from u
- depth2 = second longest path going down from u (through different child)
- path through u = depth1 + depth2
- diameter = max over all nodes of (path through u)

Edge cases:
- Single node (diameter = 0)
- Linear tree (diameter = n-1)
- Star tree (diameter = 2)
- Weighted edges (adjust accordingly)

Both approaches are O(n) time and space.
</think>

**Tree Diameter -- BFS and DFS Approaches**

```python
from collections import deque, defaultdict


def tree_diameter_bfs(adj, n, start=0):
    """
    Find tree diameter using two BFS passes.

    Args:
        adj: adjacency list {node: [(neighbor, weight), ...]}
        n: number of nodes
    Returns:
        (diameter, endpoint1, endpoint2, path)
    """
    def bfs(source):
        dist = [-1] * n
        dist[source] = 0
        parent = [-1] * n
        queue = deque([source])
        farthest = source
        max_dist = 0

        while queue:
            u = queue.popleft()
            for v, w in adj[u]:
                if dist[v] == -1:
                    dist[v] = dist[u] + w
                    parent[v] = u
                    queue.append(v)
                    if dist[v] > max_dist:
                        max_dist = dist[v]
                        farthest = v

        return farthest, max_dist, dist, parent

    # First BFS: find one endpoint
    u, _, _, _ = bfs(start)
    # Second BFS: find diameter and other endpoint
    v, diameter, dist, parent = bfs(u)

    # Reconstruct path
    path = []
    node = v
    while node != -1:
        path.append(node)
        node = parent[node]
    path.reverse()

    return diameter, u, v, path


def tree_diameter_dfs(adj, n, root=0):
    """
    Find tree diameter using single DFS pass.

    Returns (diameter, node_through_which_diameter_passes).
    """
    diameter = 0
    best_node = root

    def dfs(u, parent):
        nonlocal diameter, best_node
        # Track two longest depths from this node
        max1 = max2 = 0

        for v, w in adj[u]:
            if v != parent:
                child_depth = dfs(v, u) + w
                if child_depth >= max1:
                    max2 = max1
                    max1 = child_depth
                elif child_depth > max2:
                    max2 = child_depth

        # Path through u = max1 + max2
        if max1 + max2 > diameter:
            diameter = max1 + max2
            best_node = u

        return max1  # longest single path going down from u

    dfs(root, -1)
    return diameter, best_node


# Example: weighted tree
n = 8
adj = defaultdict(list)
edges = [(0,1,3), (0,2,2), (1,3,4), (1,4,1), (2,5,6),
         (3,6,2), (5,7,3)]

for u, v, w in edges:
    adj[u].append((v, w))
    adj[v].append((u, w))

# BFS approach
diam_bfs, u, v, path = tree_diameter_bfs(adj, n)
print(f"BFS approach:")
print(f"  Diameter: {diam_bfs}")
print(f"  Endpoints: {u} and {v}")
print(f"  Path: {' -> '.join(map(str, path))}")

# DFS approach
diam_dfs, center = tree_diameter_dfs(adj, n)
print(f"\nDFS approach:")
print(f"  Diameter: {diam_dfs}")
print(f"  Center node: {center}")

assert diam_bfs == diam_dfs, "Diameter mismatch!"

# Unweighted tree diameter
adj2 = defaultdict(list)
for u, v, _ in edges:
    adj2[u].append((v, 1))
    adj2[v].append((u, 1))

diam2, _, _, path2 = tree_diameter_bfs(adj2, n)
print(f"\nUnweighted diameter: {diam2}")
print(f"Path: {' -> '.join(map(str, path2))}")

# Show all pairwise distances for small tree
print("\nAll-pairs distances:")
for start in range(n):
    _, _, dist, _ = tree_diameter_bfs(adj, n, start)
    dists = [dist[j] for j in range(n)]
```

**BFS Correctness Proof Sketch:**
- Let (a, b) be the true diameter endpoints
- BFS from any node s finds the farthest node u
- Claim: u is an endpoint of some diameter
- Proof by contradiction: if u is not a diameter endpoint, then a longer path exists, contradicting that (a, b) is the diameter

**DFS Approach:**
- For each node, compute the two longest descending paths
- The diameter is the maximum sum of top-two paths at any node
- Single DFS traversal suffices

**Complexity:**
- BFS: O(n) -- two passes
- DFS: O(n) -- single pass
- Space: O(n)'''),

    ("thinking/algorithms", r'''Implement Euler Tour of a tree and show how it enables range queries: specifically, how to answer subtree sum queries and path sum queries using the Euler tour flattening combined with a segment tree or BIT.''', r'''<think>
An Euler Tour linearizes a tree into an array, enabling tree queries to be transformed into range queries on arrays.

There are different types of Euler Tours:

1. Euler Tour for subtree queries (entry/exit times):
   - DFS, recording entry time (tin) and exit time (tout) for each node
   - The subtree of node u corresponds to the range [tin[u], tout[u]] in the flattened array
   - Subtree queries become range queries on this interval

2. Euler Tour for path queries:
   - Record each node when entering and leaving (each node appears twice)
   - Path queries can use LCA + range operations

For subtree sum queries with point updates:
1. Compute Euler Tour (tin, tout)
2. Place node values at position tin[u] in a flat array
3. Build a BIT/segment tree on this array
4. Subtree sum of u = query [tin[u], tout[u]]
5. Update node u = update position tin[u]

For path sum queries:
- Use HLD or the Euler tour with LCA
- path_sum(u, v) = prefix_sum(u) + prefix_sum(v) - 2 * prefix_sum(lca(u,v)) + value(lca)

I will implement the subtree query approach with a BIT (Fenwick tree) since it is the most practical.

Time: O(n) for Euler tour, O(log n) per query/update with BIT.
</think>

**Euler Tour + Range Queries**

```python
class BIT:
    """Binary Indexed Tree (Fenwick Tree) for prefix sums."""
    def __init__(self, n):
        self.n = n
        self.tree = [0] * (n + 1)

    def update(self, i, delta):
        i += 1  # 1-indexed
        while i <= self.n:
            self.tree[i] += delta
            i += i & (-i)

    def prefix_sum(self, i):
        i += 1  # 1-indexed
        s = 0
        while i > 0:
            s += self.tree[i]
            i -= i & (-i)
        return s

    def range_sum(self, l, r):
        if l > r:
            return 0
        return self.prefix_sum(r) - (self.prefix_sum(l - 1) if l > 0 else 0)


class EulerTourTree:
    """Tree with Euler Tour for subtree queries."""

    def __init__(self, n, root=0):
        self.n = n
        self.root = root
        self.adj = [[] for _ in range(n)]
        self.tin = [0] * n   # entry time
        self.tout = [0] * n  # exit time
        self.order = []      # DFS order
        self.timer = 0
        self.values = [0] * n
        self.bit = None

    def add_edge(self, u, v):
        self.adj[u].append(v)
        self.adj[v].append(u)

    def build(self, values):
        self.values = values[:]
        self._euler_tour(self.root, -1)
        self.bit = BIT(self.n)
        # Place values in Euler tour order
        for u in range(self.n):
            self.bit.update(self.tin[u], self.values[u])

    def _euler_tour(self, u, parent):
        self.tin[u] = self.timer
        self.order.append(u)
        self.timer += 1

        for v in self.adj[u]:
            if v != parent:
                self._euler_tour(v, u)

        self.tout[u] = self.timer - 1

    def subtree_sum(self, u):
        """Sum of all values in subtree rooted at u. O(log n)."""
        return self.bit.range_sum(self.tin[u], self.tout[u])

    def update_node(self, u, new_val):
        """Update value of node u. O(log n)."""
        delta = new_val - self.values[u]
        self.values[u] = new_val
        self.bit.update(self.tin[u], delta)

    def is_ancestor(self, u, v):
        """Check if u is ancestor of v using Euler tour times."""
        return self.tin[u] <= self.tin[v] <= self.tout[v] <= self.tout[u]


# Example tree:
#        0 (val=1)
#       / \
#      1   2 (val=5, val=3)
#     / \   \
#    3   4   5 (val=2, val=7, val=4)
#   /
#  6 (val=6)

n = 7
et = EulerTourTree(n, root=0)
edges = [(0,1), (0,2), (1,3), (1,4), (2,5), (3,6)]
for u, v in edges:
    et.add_edge(u, v)

values = [1, 5, 3, 2, 7, 4, 6]
et.build(values)

print(f"Node values: {values}")
print(f"Entry times (tin):  {et.tin}")
print(f"Exit times (tout):  {et.tout}")
print(f"DFS order: {et.order}")

# Subtree queries
print("\nSubtree sum queries:")
for u in range(n):
    s = et.subtree_sum(u)
    # Manual verification
    expected = values[u]
    stack = [u]
    visited = set()
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        expected_sum = sum(values[v] for v in visited)
        for v in et.adj[node]:
            if et.is_ancestor(u, v) and v not in visited:
                stack.append(v)
    print(f"  Subtree({u}): sum={s}")

# Update and re-query
print(f"\nUpdate node 3: value 2 -> 20")
et.update_node(3, 20)
print(f"  Subtree(1): {et.subtree_sum(1)}")
print(f"  Subtree(0): {et.subtree_sum(0)}")

# Ancestor check
print(f"\nAncestor checks:")
pairs = [(0, 6), (1, 5), (3, 6), (2, 4)]
for u, v in pairs:
    print(f"  is_ancestor({u}, {v}): {et.is_ancestor(u, v)}")
```

**Euler Tour Key Property:**
- Subtree of u = contiguous range [tin[u], tout[u]] in the flattened array
- This enables O(log n) subtree queries with a BIT/segment tree
- Ancestor check: u is ancestor of v iff tin[u] <= tin[v] <= tout[u]

**Applications:**
- Subtree sum/min/max queries
- Subtree updates (range update on [tin[u], tout[u]])
- LCA queries (with range minimum query on depths)
- Path queries (combined with LCA)

**Complexity:**
- Euler tour construction: O(n)
- Subtree query: O(log n)
- Point update: O(log n)
- Space: O(n)'''),
]
