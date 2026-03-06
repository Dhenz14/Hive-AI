PAIRS = [
    ("thinking/algorithms", r'''Implement an efficient bipartite check for a graph. If bipartite, produce a valid 2-coloring. If not, find an odd cycle as a certificate. Handle disconnected graphs.''', r'''<think>
Bipartite check: a graph is bipartite if and only if it contains no odd-length cycle. We can check this using BFS or DFS to try to 2-color the graph. If we find a neighbor with the same color, the graph is not bipartite.

But the problem asks for more than just a yes/no answer -- it wants a certificate. If bipartite, produce the 2-coloring. If not, find an actual odd cycle. The coloring is easy (we get it from BFS). The odd cycle is trickier.

To find an odd cycle when not bipartite: during BFS, when we discover a conflict (neighbor already colored the same color), we need to reconstruct the cycle. My first thought was to just walk backwards from both endpoints to the root, but wait -- they might not share the same root if we started BFS from an arbitrary node. What I actually need is the LCA (lowest common ancestor) of the two conflicting endpoints in the BFS tree. The odd cycle goes from one endpoint up to the LCA and back down to the other, plus the conflicting edge.

Hmm, should I use BFS or DFS for this? BFS makes the LCA computation simpler because BFS trees have a nice layered structure. With DFS, the back edge gives you the cycle directly, but reconstructing it from the DFS stack is messier. Let me go with BFS.

For disconnected graphs: run BFS from each unvisited node -- a graph is bipartite if and only if every connected component is bipartite.

Implementation:
1. BFS from each uncolored node
2. Assign colors alternately
3. If conflict found, trace back through parent pointers to find odd cycle
4. If no conflict, return the 2-coloring
</think>

## Bipartite Check with Certificate

### Implementation

```python
from collections import deque, defaultdict


def bipartite_check(n, edges):
    """Check if graph is bipartite.

    Returns:
        If bipartite: (True, coloring_dict)
        If not bipartite: (False, odd_cycle_list)
    """
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    color = [-1] * n
    parent = [-1] * n

    for start in range(n):
        if color[start] != -1:
            continue

        color[start] = 0
        queue = deque([start])

        while queue:
            u = queue.popleft()
            for v in adj[u]:
                if color[v] == -1:
                    color[v] = 1 - color[u]
                    parent[v] = u
                    queue.append(v)
                elif color[v] == color[u]:
                    # Found odd cycle -- reconstruct it
                    cycle = find_odd_cycle(u, v, parent)
                    return False, cycle

    # Graph is bipartite
    coloring = {i: color[i] for i in range(n)}
    return True, coloring


def find_odd_cycle(u, v, parent):
    """Find odd cycle given conflicting edge (u, v) and BFS parents."""
    # Trace paths from u and v back to their LCA
    path_u = []
    path_v = []

    # Find depths
    a, b = u, v
    depth_a = 0
    x = a
    while x != -1:
        depth_a += 1
        x = parent[x]

    depth_b = 0
    x = b
    while x != -1:
        depth_b += 1
        x = parent[x]

    # Equalize depths
    a, b = u, v
    da, db = depth_a, depth_b
    while da > db:
        path_u.append(a)
        a = parent[a]
        da -= 1
    while db > da:
        path_v.append(b)
        b = parent[b]
        db -= 1

    # Walk up together until LCA
    while a != b:
        path_u.append(a)
        path_v.append(b)
        a = parent[a]
        b = parent[b]

    path_u.append(a)  # LCA
    path_v.reverse()
    cycle = path_u + path_v
    return cycle


def verify_bipartite(n, edges, coloring):
    """Verify that coloring is a valid 2-coloring."""
    for u, v in edges:
        if coloring.get(u) == coloring.get(v):
            return False
    return True


def verify_odd_cycle(n, edges, cycle):
    """Verify that cycle is an odd cycle in the graph."""
    if len(cycle) % 2 == 0:
        return False  # must be odd length
    edge_set = set()
    for u, v in edges:
        edge_set.add((min(u,v), max(u,v)))
    for i in range(len(cycle)):
        u = cycle[i]
        v = cycle[(i + 1) % len(cycle)]
        if (min(u,v), max(u,v)) not in edge_set:
            return False
    return True


# Demo
print("=== Bipartite Check ===")

# Bipartite graph (tree)
n1 = 6
edges1 = [(0,1), (0,2), (1,3), (2,4), (2,5)]
is_bip, result = bipartite_check(n1, edges1)
print(f"Graph 1 (tree): bipartite={is_bip}")
if is_bip:
    print(f"  Coloring: {result}")
    print(f"  Valid: {verify_bipartite(n1, edges1, result)}")

# Non-bipartite (triangle)
n2 = 3
edges2 = [(0,1), (1,2), (2,0)]
is_bip2, result2 = bipartite_check(n2, edges2)
print(f"\nGraph 2 (triangle): bipartite={is_bip2}")
if not is_bip2:
    print(f"  Odd cycle: {result2}")

# Bipartite (even cycle)
n3 = 4
edges3 = [(0,1), (1,2), (2,3), (3,0)]
is_bip3, result3 = bipartite_check(n3, edges3)
print(f"\nGraph 3 (4-cycle): bipartite={is_bip3}")
if is_bip3:
    print(f"  Coloring: {result3}")
    print(f"  Valid: {verify_bipartite(n3, edges3, result3)}")

# Non-bipartite (5-cycle)
n4 = 5
edges4 = [(0,1), (1,2), (2,3), (3,4), (4,0)]
is_bip4, result4 = bipartite_check(n4, edges4)
print(f"\nGraph 4 (5-cycle): bipartite={is_bip4}")
if not is_bip4:
    print(f"  Odd cycle: {result4}")

# Disconnected graph
n5 = 6
edges5 = [(0,1), (2,3), (4,5)]  # three disconnected edges
is_bip5, result5 = bipartite_check(n5, edges5)
print(f"\nGraph 5 (disconnected): bipartite={is_bip5}")
```

### Complexity
- **Time**: O(V + E) -- single BFS traversal
- **Space**: O(V + E)
- **Certificate**: 2-coloring (if bipartite) or odd cycle (if not)
- **Key theorem**: a graph is bipartite iff it has no odd cycles'''),

    ("thinking/algorithms", r'''Implement a chromatic number approximation for small graphs. Use backtracking with pruning to find the exact chromatic number for graphs up to ~20 nodes.''', r'''<think>
The chromatic number chi(G) is the minimum number of colors needed to properly color a graph (adjacent vertices get different colors). Computing it is NP-hard in general, so there is no polynomial algorithm unless P=NP.

For small graphs (n <= 20-25), we can compute the exact chromatic number. But what approach? My first idea was brute force: try all possible colorings. But that is k^n possibilities, which is astronomically large even for n=20. I need something smarter.

Better approach:
1. DSatur (degree of saturation) heuristic for upper bound -- this gives us a ceiling
2. Clique number for lower bound (chi >= omega) -- this gives us a floor
3. Backtracking with pruning between lower and upper bound

The backtracking approach: try to color the graph with k colors for increasing k. For each k, use backtracking to find a valid coloring. If we start from the lower bound, we often find the answer quickly because the gap between omega and chi is usually small.

Pruning strategies are critical for making this tractable:
- Assign colors in order to break symmetry (first uncolored node gets color 0) -- wait, why does this help? Because without symmetry breaking, coloring node 0 red then node 1 blue is equivalent to coloring node 0 blue then node 1 red. We would explore both, wasting half the search.
- Use forward checking: if an uncolored node has no valid colors left, backtrack immediately
- Choose the most constrained variable first (DSatur heuristic: node with most already-colored neighbors) -- this is a well-known CSP technique that dramatically reduces the search tree

DSatur algorithm: greedily color nodes in order of "saturation degree" (number of distinct colors used by neighbors). This gives a good upper bound, often within 1-2 of optimal.

I initially considered using the inclusion-exclusion formula for chromatic polynomial, but that is O(2^n * n) which is similar to brute force clique finding. For n <= 20, the backtracking approach with good bounds is more practical.
</think>

## Chromatic Number (Exact for Small Graphs)

### Implementation

```python
from collections import defaultdict


def dsatur_coloring(n, adj):
    """DSatur greedy coloring for upper bound on chromatic number.
    Returns (num_colors, coloring)."""
    color = [-1] * n
    sat_degree = [0] * n  # number of distinct colors among neighbors
    adj_colors = [set() for _ in range(n)]  # colors used by neighbors

    for step in range(n):
        # Choose uncolored node with highest saturation degree
        # Break ties by highest degree
        best = -1
        for v in range(n):
            if color[v] != -1:
                continue
            if best == -1 or sat_degree[v] > sat_degree[best]:
                best = v
            elif sat_degree[v] == sat_degree[best]:
                if len(adj[v]) > len(adj[best]):
                    best = v

        # Assign smallest available color
        c = 0
        while c in adj_colors[best]:
            c += 1
        color[best] = c

        # Update neighbors
        for u in adj[best]:
            if c not in adj_colors[u]:
                adj_colors[u].add(c)
                sat_degree[u] = len(adj_colors[u])

    num_colors = max(color) + 1
    return num_colors, color


def is_k_colorable(n, adj, k):
    """Check if graph is k-colorable using backtracking.
    Returns coloring if possible, None otherwise."""
    color = [-1] * n

    def backtrack(node):
        if node == n:
            return True

        used_by_neighbors = set()
        for v in adj[node]:
            if color[v] != -1:
                used_by_neighbors.add(color[v])

        for c in range(k):
            if c not in used_by_neighbors:
                color[node] = c
                if backtrack(node + 1):
                    return True
                color[node] = -1

        return False

    if backtrack(0):
        return list(color)
    return None


def chromatic_number(n, edges):
    """Find exact chromatic number for small graphs.

    Returns:
        (chi, coloring)
    """
    adj = defaultdict(list)
    adj_set = defaultdict(set)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
        adj_set[u].add(v)
        adj_set[v].add(u)

    if not edges:
        return 1 if n > 0 else 0, [0] * n

    # Upper bound: DSatur
    upper, greedy_color = dsatur_coloring(n, adj)

    # Lower bound: clique number (brute force for small n)
    lower = 1
    if n <= 20:
        for mask in range(1 << n):
            nodes = [i for i in range(n) if mask & (1 << i)]
            is_clique = True
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    if nodes[j] not in adj_set[nodes[i]]:
                        is_clique = False
                        break
                if not is_clique:
                    break
            if is_clique:
                lower = max(lower, len(nodes))

    # Search from lower bound to upper bound
    for k in range(lower, upper + 1):
        result = is_k_colorable(n, adj, k)
        if result is not None:
            return k, result

    return upper, greedy_color


# Demo
print("=== Chromatic Number ===")

# Petersen graph (chi = 3)
n = 10
edges_petersen = [
    (0,1),(1,2),(2,3),(3,4),(4,0),  # outer cycle
    (0,5),(1,6),(2,7),(3,8),(4,9),  # spokes
    (5,7),(7,9),(9,6),(6,8),(8,5),  # inner pentagram
]
chi, coloring = chromatic_number(n, edges_petersen)
print(f"Petersen graph: chi = {chi}")
print(f"  Coloring: {coloring}")

# Complete graph K4 (chi = 4)
edges_k4 = [(i,j) for i in range(4) for j in range(i+1, 4)]
chi4, col4 = chromatic_number(4, edges_k4)
print(f"\nK4: chi = {chi4} (expected: 4)")

# Cycle C5 (chi = 3)
edges_c5 = [(i, (i+1)%5) for i in range(5)]
chi5, col5 = chromatic_number(5, edges_c5)
print(f"C5: chi = {chi5} (expected: 3)")

# Bipartite graph (chi = 2)
edges_bip = [(0,3),(0,4),(1,3),(1,5),(2,4),(2,5)]
chi_bip, col_bip = chromatic_number(6, edges_bip)
print(f"K3,3: chi = {chi_bip} (expected: 2)")

# Verify colorings
def verify_coloring(n, edges, coloring):
    for u, v in edges:
        if coloring[u] == coloring[v]:
            return False
    return True

for name, n_v, e, col in [("Petersen", 10, edges_petersen, coloring),
                            ("K4", 4, edges_k4, col4)]:
    print(f"\n  {name} coloring valid: {verify_coloring(n_v, e, col)}")
```

### Complexity
- **DSatur upper bound**: O(n^2)
- **Backtracking**: O(k^n) worst case, much better with pruning
- **Clique lower bound**: O(2^n) for brute force
- **Practical**: works well for n <= 20-25'''),

    ("thinking/algorithms", r'''Implement edge coloring for a bipartite graph. By Konig's theorem, bipartite graphs can be edge-colored with exactly Delta colors (maximum degree). Show the constructive proof via matching decomposition.''', r'''<think>
Edge coloring: assign colors to edges so no two edges sharing a vertex have the same color. By Vizing's theorem, any graph needs Delta or Delta+1 colors. For bipartite graphs, Konig's theorem strengthens this to exactly Delta colors. The question is: how do we construct such a coloring?

My first thought for the constructive proof:
1. Find a maximum matching in the bipartite graph
2. Color those edges with color 1
3. Remove the matching from the graph
4. The remaining graph has maximum degree Delta-1
5. Recurse

But wait -- this requires finding Delta perfect matchings, and each matching computation is O(E * sqrt(V)) with Hopcroft-Karp. For a graph with many edges, that could be slow. Is there a more direct approach?

Since the graph is bipartite, by Hall's theorem a perfect matching exists when both sides have the same degree. If degrees are unequal, we would need to augment the graph first... hmm, that adds complexity.

Actually, I was overcomplicating this. The simplest correct approach uses the augmenting path method from Konig's theorem proof: process edges one at a time. When assigning a color to edge (u,v), find a color a free at u and a color b free at v. If a == b, use it -- done. If a != b, find an alternating path of colors a and b starting from v, swap colors along this path, and then color (u,v) with a.

Why does this work for bipartite graphs but not general graphs? Because in a bipartite graph, the alternating path starting from v cannot return to u (since u and v are on different sides), so the swap never creates a conflict at u. In a general graph, the path could loop back, which is why Vizing's theorem only guarantees Delta+1.

I initially worried about the augmenting path not terminating, but actually it must terminate because the graph is finite and the path visits each vertex at most once (since each vertex has at most one edge of each color).
</think>

## Edge Coloring for Bipartite Graphs

### Implementation

```python
from collections import defaultdict


def edge_color_bipartite(n, edges):
    """Edge-color a bipartite graph with exactly Delta colors.
    Uses augmenting path method from Konig's theorem.

    Returns:
        dict mapping edge (u,v) -> color (0-indexed)
    """
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    # Find max degree
    delta = max(len(adj[v]) for v in adj) if adj else 0

    # edge_colors: dict from (min(u,v), max(u,v)) -> color
    edge_color = {}
    # vertex_colors[v] = set of colors used at v
    vertex_colors = defaultdict(set)

    def free_color(v):
        """Find smallest color not used at vertex v."""
        for c in range(delta):
            if c not in vertex_colors[v]:
                return c
        return delta

    def augmenting_swap(v, c1, c2):
        """Swap colors c1 and c2 along alternating path starting at v."""
        visited = set()
        current = v
        while current is not None and current not in visited:
            visited.add(current)
            # Find edge at current with color c2
            next_node = None
            for u in adj[current]:
                key = (min(current, u), max(current, u))
                if edge_color.get(key) == c2:
                    next_node = u
                    # Swap this edge to c1
                    edge_color[key] = c1
                    vertex_colors[current].discard(c2)
                    vertex_colors[current].add(c1)
                    vertex_colors[u].discard(c2)
                    vertex_colors[u].add(c1)
                    break
            if next_node is None:
                break
            current = next_node
            c1, c2 = c2, c1  # alternate

    for u, v in edges:
        key = (min(u, v), max(u, v))

        c_u = free_color(u)
        c_v = free_color(v)

        if c_u == c_v:
            # Same free color, use it
            edge_color[key] = c_u
            vertex_colors[u].add(c_u)
            vertex_colors[v].add(c_v)
        else:
            # Need augmenting path swap
            # Swap c_u and c_v along path from v
            augmenting_swap(v, c_u, c_v)
            edge_color[key] = c_u
            vertex_colors[u].add(c_u)
            vertex_colors[v].add(c_u)

    return edge_color


def verify_edge_coloring(n, edges, coloring):
    """Verify that edge coloring is valid."""
    adj_colors = defaultdict(set)
    for u, v in edges:
        key = (min(u, v), max(u, v))
        c = coloring.get(key, -1)
        if c in adj_colors[u] or c in adj_colors[v]:
            return False, f"Color conflict at vertex {u} or {v}"
        adj_colors[u].add(c)
        adj_colors[v].add(c)
    return True, "Valid"


# Demo
print("=== Edge Coloring (Bipartite) ===")

# K3,3: bipartite, Delta=3, needs 3 edge colors
n = 6
edges = [(0,3), (0,4), (0,5), (1,3), (1,4), (1,5), (2,3), (2,4), (2,5)]
coloring = edge_color_bipartite(n, edges)

print(f"K3,3 edge coloring:")
for (u, v), c in sorted(coloring.items()):
    print(f"  Edge ({u},{v}): color {c}")

num_colors = len(set(coloring.values()))
valid, msg = verify_edge_coloring(n, edges, coloring)
print(f"Colors used: {num_colors} (Delta = 3)")
print(f"Valid: {msg}")

# Another example: path graph (bipartite)
edges2 = [(0,1), (1,2), (2,3), (3,4)]
coloring2 = edge_color_bipartite(5, edges2)
print(f"\nPath graph edge coloring:")
for (u, v), c in sorted(coloring2.items()):
    print(f"  Edge ({u},{v}): color {c}")
num2 = len(set(coloring2.values()))
print(f"Colors used: {num2} (Delta = 2)")

# Complete bipartite K4,4
edges3 = [(i, j+4) for i in range(4) for j in range(4)]
coloring3 = edge_color_bipartite(8, edges3)
num3 = len(set(coloring3.values()))
valid3, msg3 = verify_edge_coloring(8, edges3, coloring3)
print(f"\nK4,4: {num3} colors used (Delta=4), valid={msg3}")
```

### Theorem (Konig, 1916)
For bipartite graphs: **chromatic index = Delta** (maximum degree).

### Complexity
- **Time**: O(|E| * Delta) for the augmenting path method
- **Space**: O(|V| + |E|)
- **Comparison**: for general graphs, Vizing's theorem gives Delta or Delta+1'''),

    ("thinking/algorithms", r'''Implement interval graph recognition and optimal coloring. Given a set of intervals, verify the graph is an interval graph and find its chromatic number (which equals the clique number for perfect graphs).''', r'''<think>
An interval graph is the intersection graph of a set of intervals on the real line. Two nodes are adjacent if and only if their intervals overlap.

Properties of interval graphs:
1. They are perfect graphs (chromatic number = clique number)
2. They are chordal (every cycle of length 4+ has a chord)
3. Optimal coloring can be found in O(n log n) by greedy coloring in right-endpoint order

Wait, property 1 is very powerful. It means we do not need to solve the NP-hard chromatic number problem -- we can just find the maximum clique instead, which for interval graphs is easy (it equals the maximum overlap).

For optimal coloring, hmm, my first thought was to sort by right endpoint and use a greedy algorithm, but actually sorting by LEFT endpoint works better for the sweep approach:
1. Sort intervals by left endpoint
2. Sweep left to right, maintaining active intervals
3. Assign colors greedily: reuse a color whose interval has ended
4. The number of colors = maximum overlap = clique number

This is the same as the interval scheduling / room assignment problem. I initially did not make that connection, but once you see it, the algorithm is obvious: each "room" is a color, and you are assigning intervals to rooms such that no room has overlapping intervals.

Recognition is trickier: given a graph (as adjacency lists, not intervals), how do we check if it CAN be represented as an interval graph? Being chordal is necessary but not sufficient -- for example, a tree is always chordal but not always an interval graph. Actually wait, every tree IS an interval graph. Hmm, let me reconsider... the correct characterization is: a graph is an interval graph iff it is chordal AND its complement is a comparability graph. That second condition is harder to check.

For practical purposes, I will use the chordality check as a necessary condition. A graph is chordal iff it has a perfect elimination ordering (PEO). We can find a PEO using maximum cardinality search (MCS), then verify that each vertex and its later neighbors form a clique. If that check fails, the graph is not chordal and therefore not an interval graph.
</think>

## Interval Graph Recognition and Optimal Coloring

### Implementation

```python
import heapq
from collections import defaultdict


def interval_graph_coloring(intervals):
    """Optimally color an interval graph (given intervals).
    Chromatic number = clique number = maximum overlap.

    Args:
        intervals: list of (start, end) tuples

    Returns:
        (chromatic_number, color_assignment)
    """
    n = len(intervals)
    if n == 0:
        return 0, []

    # Sort by start time, keep original indices
    indexed = sorted(enumerate(intervals), key=lambda x: x[1][0])

    colors = [0] * n
    # Min-heap of (end_time, color_id) for available colors
    active = []  # currently used: (end_time, color_id)
    freed = []   # available colors
    next_color = 0
    max_overlap = 0

    for orig_idx, (start, end) in indexed:
        # Free colors whose intervals have ended
        while active and active[0][0] <= start:
            _, color_id = heapq.heappop(active)
            heapq.heappush(freed, color_id)

        # Assign a color
        if freed:
            color_id = heapq.heappop(freed)
        else:
            color_id = next_color
            next_color += 1

        colors[orig_idx] = color_id
        heapq.heappush(active, (end, color_id))
        max_overlap = max(max_overlap, len(active))

    return max_overlap, colors


def is_chordal(n, adj):
    """Check if graph is chordal using Maximum Cardinality Search.
    Returns (is_chordal, peo) where peo is perfect elimination ordering."""
    # MCS: repeatedly pick the node with most already-chosen neighbors
    weight = [0] * n
    chosen = [False] * n
    peo = []

    for _ in range(n):
        # Find unchosen node with max weight
        best = -1
        for v in range(n):
            if not chosen[v]:
                if best == -1 or weight[v] > weight[best]:
                    best = v
        chosen[best] = True
        peo.append(best)

        for u in adj[best]:
            if not chosen[u]:
                weight[u] += 1

    # Verify PEO: for each v in order, its later neighbors must form a clique
    position = [0] * n
    for i, v in enumerate(peo):
        position[v] = i

    adj_set = defaultdict(set)
    for u in range(n):
        for v in adj[u]:
            adj_set[u].add(v)

    for idx in range(n):
        v = peo[idx]
        # Later neighbors of v
        later = [u for u in adj[v] if position[u] > idx]
        # Check all pairs in later are adjacent
        for i in range(len(later)):
            for j in range(i + 1, len(later)):
                if later[j] not in adj_set[later[i]]:
                    return False, peo

    return True, peo


# Demo
print("=== Interval Graph Coloring ===")
intervals = [
    (1, 5), (2, 6), (4, 8), (7, 10), (9, 12),
    (3, 7), (6, 9), (11, 15),
]

chi, colors = interval_graph_coloring(intervals)
print(f"Intervals: {intervals}")
print(f"Chromatic number (= max overlap): {chi}")
print(f"Color assignment:")
for i, ((s, e), c) in enumerate(zip(intervals, colors)):
    print(f"  [{s},{e}]: color {c}")

# Verify: no two overlapping intervals share a color
conflicts = 0
for i in range(len(intervals)):
    for j in range(i+1, len(intervals)):
        s1, e1 = intervals[i]
        s2, e2 = intervals[j]
        if s1 < e2 and s2 < e1:  # overlap
            if colors[i] == colors[j]:
                conflicts += 1
print(f"Conflicts: {conflicts}")

# Build adjacency for chordality check
n = len(intervals)
adj = defaultdict(list)
for i in range(n):
    for j in range(i+1, n):
        s1, e1 = intervals[i]
        s2, e2 = intervals[j]
        if s1 < e2 and s2 < e1:
            adj[i].append(j)
            adj[j].append(i)

is_ch, peo = is_chordal(n, adj)
print(f"\nChordal (necessary for interval graph): {is_ch}")
print(f"Perfect elimination ordering: {peo}")

print(f"\n=== Key Theorem ===")
print(f"For interval graphs (which are perfect):")
print(f"  chromatic number = clique number = max overlap")
print(f"  This is {chi} for our example")
```

### Properties of Interval Graphs
| Property | Value |
|----------|-------|
| Perfect | Yes (chi = omega) |
| Chordal | Yes (no induced C4+) |
| Recognition | O(n log n) from intervals |
| Optimal coloring | O(n log n) by greedy |
| Max clique | O(n log n) via sweep line |

### Complexity
- **Coloring**: O(n log n) -- sort + heap operations
- **Chordality check**: O(n + m) for MCS
- **Optimality**: guaranteed by perfection of interval graphs'''),

    ("thinking/algorithms", r'''Explain list coloring and implement a solver. In list coloring, each vertex has a list of permissible colors. Determine if a valid coloring exists where each vertex uses a color from its list.''', r'''<think>
List coloring: each vertex v has a list L(v) of permissible colors. We need to find a proper coloring where color(v) is in L(v) and adjacent vertices have different colors.

This is a generalization of graph coloring: standard coloring is the special case where all lists are {1, 2, ..., k}. But it is strictly harder -- a graph might be 2-colorable in the standard sense but not list-colorable with certain lists of size 2.

Wait, is list coloring NP-hard even for simple graph classes? Actually yes, it is NP-hard even for bipartite graphs when list sizes vary. That surprised me initially, but it makes sense because the constraint is per-vertex, not global. However, it can be solved efficiently in special cases:
- If all lists have size >= Delta+1 (by greedy -- because at each step, there are more available colors than neighbors, so you can always find a valid color)
- On trees (by dynamic programming)
- On chordal graphs (by PEO-based greedy)

For general small graphs, we need backtracking. My first thought was plain backtracking, but that is too slow without pruning. Adding constraint propagation makes it practical:
1. Choose the most constrained vertex (smallest list) -- this is the MRV heuristic from CSP theory, and it dramatically reduces the search tree
2. Try each color in its list
3. Propagate: remove the chosen color from neighbors' lists
4. If any neighbor's list becomes empty, backtrack immediately (forward checking)

This is essentially CSP (Constraint Satisfaction Problem) solving. Hmm, I could also add arc consistency (AC-3), but for graph coloring with small n, forward checking is usually sufficient.

I will implement:
1. Backtracking solver for general graphs (with constraint propagation)
2. Efficient solver for trees using DP (since trees are a common special case)
3. Greedy solver when lists are large enough (the easy case)
</think>

## List Coloring

### Implementation

```python
from collections import defaultdict


def list_coloring_backtrack(n, adj, lists):
    """Solve list coloring using backtracking with constraint propagation.

    Args:
        n: number of vertices
        adj: adjacency list (dict or list of lists)
        lists: lists[v] = set of permissible colors for vertex v

    Returns:
        coloring dict or None if impossible
    """
    # Working copy of lists
    available = [set(lists[v]) for v in range(n)]
    color = [None] * n

    def propagate(v, c):
        """Remove color c from v's neighbors' lists. Return removed set."""
        removed = []
        for u in adj[v]:
            if c in available[u]:
                available[u].discard(c)
                removed.append((u, c))
                if color[u] is None and len(available[u]) == 0:
                    # Undo and fail
                    for node, col in removed:
                        available[node].add(col)
                    return None
        return removed

    def backtrack():
        # Choose most constrained uncolored vertex
        best = -1
        min_choices = float('inf')
        for v in range(n):
            if color[v] is None:
                if len(available[v]) < min_choices:
                    min_choices = len(available[v])
                    best = v

        if best == -1:
            return True  # all colored

        if min_choices == 0:
            return False  # dead end

        for c in list(available[best]):
            color[best] = c
            removed = propagate(best, c)
            if removed is not None:
                if backtrack():
                    return True
                # Undo propagation
                for node, col in removed:
                    available[node].add(col)
            color[best] = None

        return False

    if backtrack():
        return {v: color[v] for v in range(n)}
    return None


def list_coloring_tree(n, edges, lists, root=0):
    """Efficient list coloring on a tree using DP.
    Returns coloring or None."""
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    parent = [-1] * n
    children = [[] for _ in range(n)]
    order = []
    visited = [False] * n
    visited[root] = True
    stack = [root]
    while stack:
        u = stack.pop()
        order.append(u)
        for v in adj[u]:
            if not visited[v]:
                visited[v] = True
                parent[v] = u
                children[u].append(v)
                stack.append(v)

    # Bottom-up: for each node, compute which colors are feasible
    # feasible[v] = set of colors c in lists[v] such that
    # all children can be colored with c removed from their parent's constraint
    feasible = [set(lists[v]) for v in range(n)]

    for v in reversed(order):
        for c in children[v]:
            # Child c must have at least one color != parent's color
            new_feasible = set()
            for parent_color in feasible[v]:
                child_options = feasible[c] - {parent_color}
                if child_options:
                    new_feasible.add(parent_color)
            feasible[v] = new_feasible

    if not feasible[root]:
        return None

    # Top-down: assign colors
    color = [None] * n
    color[root] = next(iter(feasible[root]))

    for v in order:
        for c in children[v]:
            for col in feasible[c]:
                if col != color[v]:
                    color[c] = col
                    break

    return {v: color[v] for v in range(n)}


# Demo
print("=== List Coloring ===")

# Simple example
n = 4
adj = defaultdict(list)
edges = [(0,1), (1,2), (2,3), (0,3)]
for u, v in edges:
    adj[u].append(v)
    adj[v].append(u)

lists = [
    {'red', 'blue'},       # vertex 0
    {'blue', 'green'},     # vertex 1
    {'red', 'green'},      # vertex 2
    {'blue', 'green'},     # vertex 3
]

print(f"Graph: 4-cycle with lists:")
for v in range(n):
    print(f"  Vertex {v}: {lists[v]}")

result = list_coloring_backtrack(n, adj, lists)
if result:
    print(f"\nColoring found:")
    for v, c in result.items():
        print(f"  Vertex {v}: {c}")
    # Verify
    valid = all(result[u] != result[v] for u, v in edges)
    in_list = all(result[v] in lists[v] for v in range(n))
    print(f"Valid: {valid and in_list}")
else:
    print("\nNo valid coloring exists.")

# Impossible case
lists2 = [
    {'red'},          # vertex 0
    {'red'},          # vertex 1 - conflict with 0!
    {'red', 'blue'},  # vertex 2
    {'blue'},         # vertex 3
]
print(f"\nImpossible case:")
result2 = list_coloring_backtrack(n, adj, lists2)
print(f"  Result: {result2}")

# Tree example
print(f"\n=== List Coloring on Tree ===")
tree_edges = [(0,1), (0,2), (1,3), (1,4)]
tree_lists = [
    {'a', 'b'},     # 0
    {'a', 'c'},     # 1
    {'b', 'c'},     # 2
    {'a', 'b'},     # 3
    {'b', 'c'},     # 4
]
tree_result = list_coloring_tree(5, tree_edges, tree_lists)
if tree_result:
    print(f"Tree coloring: {tree_result}")
```

### Complexity
- **Backtracking**: O(k^n) worst case, practical for small n
- **Tree DP**: O(n * max_list_size)
- **Greedy (when lists >= Delta+1)**: O(n + m) -- always succeeds

### Choosability
A graph is k-choosable if it has a valid list coloring for ANY assignment of lists of size k. The **list chromatic number** ch(G) is the minimum k for which G is k-choosable.'''),
]
