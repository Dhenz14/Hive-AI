PAIRS = [
    ("thinking/algorithms", r'''Implement Dijkstra's algorithm with modifications: (1) find the shortest path with minimum number of edges among all shortest paths, (2) count the number of shortest paths, (3) find the shortest path avoiding specific nodes.''', r'''<think>
Three Dijkstra modifications. Let me think through each carefully.

1. Shortest path with minimum edges: I could maintain both dist[] and edge_count[]. When we find an equal-distance path with fewer edges, update edge_count. But wait -- should I track edge count separately or embed it in the priority queue tuple? Hmm, actually embedding it in the tuple is cleaner because then the priority queue naturally breaks ties by edge count.

2. Count shortest paths: maintain count[]. This could be tricky -- when we find an equal-distance path, add to count. When we find a strictly shorter path, reset count. I initially thought about incrementing count[v] by 1 for each equal-distance path, but that would be wrong. We need to add count[u] (the number of shortest paths to the predecessor), not just 1. Because each shortest path to u extends to a shortest path to v.

3. Avoiding specific nodes: simply skip forbidden nodes during relaxation. This seems straightforward, but I need to be careful -- should I skip them when popping from the queue or when relaxing neighbors? Skipping during relaxation is better because it prevents them from ever entering the queue.

I considered implementing each modification as a separate function, but that won't work well because the user wants all three combined. All three can be implemented in a single modified Dijkstra by maintaining additional state per node.

Key implementation detail: in standard Dijkstra, once a node is popped from the priority queue, its distance is finalized. Modifications 1 and 2 need to update counts/edges even when a node is re-visited with the same distance. Hmm, actually that is the tricky part -- with the counting modification, we need to process equal-distance arrivals.

Wait, I need to reconsider the lazy deletion approach. With lazy deletion (re-inserting nodes), we might process a node multiple times. A cleaner approach: only process a node when it is first popped, and update neighbors' dist/count during relaxation. But for the min-edges modification, we might need to re-process if we find a same-distance path with fewer edges. So I will skip entries where both dist and edges are outdated.

Let me implement this with a standard priority queue approach using (distance, edge_count, node) tuples.
</think>

## Dijkstra's Algorithm with Modifications

### Implementation

```python
import heapq
from collections import defaultdict


def dijkstra_modified(n, adj, source, forbidden=None):
    """Modified Dijkstra: shortest dist, min edges, path count, avoiding nodes.

    Args:
        n: number of nodes
        adj: adjacency list: adj[u] = [(v, weight), ...]
        source: source node
        forbidden: set of nodes to avoid (optional)

    Returns:
        dist: shortest distances
        count: number of shortest paths
        edges: minimum number of edges among shortest paths
        prev: predecessor for path reconstruction
    """
    INF = float('inf')
    forbidden = forbidden or set()

    dist = [INF] * n
    count = [0] * n
    edges = [INF] * n
    prev = [-1] * n

    dist[source] = 0
    count[source] = 1
    edges[source] = 0

    # (distance, edge_count, node)
    pq = [(0, 0, source)]

    while pq:
        d, e, u = heapq.heappop(pq)

        if d > dist[u]:
            continue
        if d == dist[u] and e > edges[u]:
            continue

        for v, w in adj[u]:
            if v in forbidden:
                continue

            new_dist = d + w
            new_edges = e + 1

            if new_dist < dist[v]:
                dist[v] = new_dist
                count[v] = count[u]
                edges[v] = new_edges
                prev[v] = u
                heapq.heappush(pq, (new_dist, new_edges, v))
            elif new_dist == dist[v]:
                count[v] += count[u]
                if new_edges < edges[v]:
                    edges[v] = new_edges
                    prev[v] = u
                    heapq.heappush(pq, (new_dist, new_edges, v))

    return dist, count, edges, prev


def reconstruct_path(prev, target):
    path = []
    v = target
    while v != -1:
        path.append(v)
        v = prev[v]
    path.reverse()
    return path


# Demo
n = 7
adj = defaultdict(list)
edges_list = [
    (0, 1, 2), (0, 2, 5), (1, 2, 1), (1, 3, 7),
    (2, 3, 3), (2, 4, 8), (3, 4, 1), (3, 5, 2),
    (4, 5, 4), (4, 6, 6), (5, 6, 1),
]
for u, v, w in edges_list:
    adj[u].append((v, w))
    adj[v].append((u, w))

print("=== Dijkstra with Modifications ===")
print(f"Graph: {n} nodes, {len(edges_list)} edges")

# Standard run
dist, count, min_edges, prev = dijkstra_modified(n, adj, 0)
print(f"\nFrom node 0:")
print(f"{'Node':>4} {'Dist':>6} {'Paths':>6} {'MinEdges':>9} {'Path':>15}")
for v in range(n):
    path = reconstruct_path(prev, v)
    print(f"{v:>4} {dist[v]:>6} {count[v]:>6} {min_edges[v]:>9} {str(path):>15}")

# With forbidden nodes
print(f"\n--- Avoiding node 2 ---")
dist2, count2, edges2, prev2 = dijkstra_modified(n, adj, 0, forbidden={2})
for v in range(n):
    path = reconstruct_path(prev2, v)
    d = dist2[v] if dist2[v] < float('inf') else "INF"
    print(f"  Node {v}: dist={d}, path={path}")

# Verify shortest path count with brute force (small graph)
print(f"\n--- Path Count Verification ---")
from itertools import permutations

def all_simple_paths(adj, src, dst, n):
    """Find all simple paths and their distances."""
    paths = []
    def dfs(u, path, dist_so_far, visited):
        if u == dst:
            paths.append((dist_so_far, list(path)))
            return
        for v, w in adj[u]:
            if v not in visited:
                visited.add(v)
                path.append(v)
                dfs(v, path, dist_so_far + w, visited)
                path.pop()
                visited.remove(v)
    dfs(src, [src], 0, {src})
    return paths

for target in [3, 5, 6]:
    all_p = all_simple_paths(adj, 0, target, n)
    if all_p:
        min_dist = min(d for d, p in all_p)
        shortest = [(d, p) for d, p in all_p if d == min_dist]
        print(f"  Node {target}: {len(shortest)} shortest paths of length {min_dist} "
              f"(Dijkstra says {count[target]} paths, dist={dist[target]})")
```

### Complexity
- **Time**: O((V + E) log V) with binary heap
- **Space**: O(V + E)
- **Each modification adds O(1) work per relaxation**'''),

    ("thinking/algorithms", r'''Implement Bellman-Ford algorithm with negative cycle detection. Show how to find and print the actual negative cycle, not just detect it.''', r'''<think>
Bellman-Ford relaxes all edges V-1 times. If any edge can still be relaxed after V-1 iterations, there is a negative cycle.

But finding the actual cycle is harder than just detecting one. My first thought was: just trace back from the node that got updated in iteration V. But wait -- that node might be reachable FROM a negative cycle without being ON the cycle itself. For example, if there is a cycle A->B->C->A with negative total weight, and an edge C->D, then D gets updated but D is not part of the cycle.

So the approach needs to be:
1. Run V iterations of relaxation (one extra beyond the standard V-1)
2. If any distance is updated in the V-th iteration, the updated node is reachable from a negative cycle
3. Trace back through predecessors V times from that node -- this guarantees we land on a node that IS on the cycle, because the predecessor chain eventually loops through the cycle

I considered just checking for a node that appears twice in the predecessor chain, but that would require storing and scanning the path. Tracing back exactly V times is simpler -- because the cycle has at most V nodes, after V steps we must have entered the cycle and gone around at least once.

4. Follow predecessors from that node until we return to it -- this gives the cycle

Hmm, actually there is an edge case: what if we have multiple negative cycles? The algorithm finds one of them -- whichever one the updated node is reachable from. That should be fine for the problem statement.
</think>

## Bellman-Ford with Negative Cycle Finding

### Implementation

```python
def bellman_ford(n, edges, source):
    """Bellman-Ford shortest paths with negative cycle detection and finding.

    Args:
        n: number of nodes
        edges: list of (u, v, weight)
        source: source node

    Returns:
        (dist, prev, negative_cycle)
        negative_cycle: list of nodes forming the cycle, or None
    """
    INF = float('inf')
    dist = [INF] * n
    prev = [-1] * n
    dist[source] = 0

    # Relax all edges V-1 times
    for iteration in range(n - 1):
        updated = False
        for u, v, w in edges:
            if dist[u] < INF and dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                prev[v] = u
                updated = True
        if not updated:
            break  # early termination

    # Check for negative cycles (V-th iteration)
    cycle_node = -1
    for u, v, w in edges:
        if dist[u] < INF and dist[u] + w < dist[v]:
            dist[v] = dist[u] + w
            prev[v] = u
            cycle_node = v

    if cycle_node == -1:
        return dist, prev, None

    # Find a node on the actual cycle
    # Go back n times to ensure we are on the cycle
    v = cycle_node
    for _ in range(n):
        v = prev[v]

    # Now v is on the cycle. Follow prev until we return to v.
    cycle = []
    u = v
    while True:
        cycle.append(u)
        u = prev[u]
        if u == v:
            cycle.append(v)
            break

    cycle.reverse()
    return dist, prev, cycle


def verify_negative_cycle(edges, cycle):
    """Verify that the cycle is indeed negative weight."""
    edge_map = {}
    for u, v, w in edges:
        edge_map[(u, v)] = w

    total = 0
    for i in range(len(cycle) - 1):
        u, v = cycle[i], cycle[i + 1]
        if (u, v) not in edge_map:
            return False, 0
        total += edge_map[(u, v)]

    return total < 0, total


# Demo
print("=== Bellman-Ford with Negative Cycle Detection ===")

# Graph without negative cycle
n1 = 5
edges1 = [
    (0, 1, 4), (0, 2, 1), (2, 1, 2),
    (1, 3, 1), (2, 3, 5), (3, 4, 3),
]
dist1, prev1, cycle1 = bellman_ford(n1, edges1, 0)
print(f"Graph 1 (no negative cycle):")
print(f"  Distances from 0: {dist1}")
print(f"  Negative cycle: {cycle1}")

# Graph with negative cycle
n2 = 5
edges2 = [
    (0, 1, 1), (1, 2, -1), (2, 3, -1),
    (3, 1, -1),  # cycle: 1 -> 2 -> 3 -> 1, weight = -3
    (0, 4, 10),
]
dist2, prev2, cycle2 = bellman_ford(n2, edges2, 0)
print(f"\nGraph 2 (with negative cycle):")
print(f"  Negative cycle found: {cycle2}")
if cycle2:
    is_neg, weight = verify_negative_cycle(edges2, cycle2)
    print(f"  Cycle weight: {weight}")
    print(f"  Is negative: {is_neg}")

# Graph with negative edges but no negative cycle
n3 = 4
edges3 = [
    (0, 1, 3), (0, 2, 8),
    (1, 2, -2), (2, 3, 4), (1, 3, 7),
]
dist3, prev3, cycle3 = bellman_ford(n3, edges3, 0)
print(f"\nGraph 3 (negative edges, no cycle):")
print(f"  Distances: {dist3}")
print(f"  Negative cycle: {cycle3}")

# Detailed path reconstruction
def reconstruct(prev, target):
    if prev[target] == -1 and target != 0:
        return None
    path = []
    v = target
    while v != -1:
        path.append(v)
        v = prev[v]
    path.reverse()
    return path

print(f"\n  Paths from 0:")
for v in range(n3):
    path = reconstruct(prev3, v)
    print(f"    to {v}: dist={dist3[v]}, path={path}")
```

### The Cycle-Finding Algorithm
```
1. Run V iterations (not V-1)
2. If V-th iteration updates node x, a negative cycle is reachable from x
3. Follow prev[x] V times to reach a node guaranteed to be ON the cycle
4. Follow prev from that node until we revisit it -> that's the cycle
```

### Complexity
- **Time**: O(V * E)
- **Space**: O(V + E)
- **Negative cycle detection**: O(E) additional (one more iteration)
- **Cycle extraction**: O(V) additional'''),

    ("thinking/algorithms", r'''Implement Floyd-Warshall with path reconstruction. Compute all-pairs shortest paths and reconstruct the actual shortest path between any two nodes.''', r'''<think>
Floyd-Warshall computes all-pairs shortest paths in O(V^3). The recurrence:
dist[i][j] = min(dist[i][j], dist[i][k] + dist[k][j]) for each intermediate vertex k.

For path reconstruction, I need to track HOW we got the shortest path. My first instinct was to store a prev[i][j] matrix (predecessor), but actually a next[i][j] matrix is more natural for reconstruction. Let me think about why...

With prev[i][j], to reconstruct i->j I would need to trace back from j, which gives the path in reverse. With next[i][j] = "the next node after i on the shortest path to j", I can trace forward from i, which is cleaner. So:
- Initialize next[i][j] = j for each edge (i,j)
- When dist[i][j] is updated through k, set next[i][j] = next[i][k]

Wait, why next[i][k] and not just k? Because the path from i to j through k goes: i -> ... -> k -> ... -> j. The next hop from i is toward k, so it is next[i][k], which was already computed in an earlier iteration.

To reconstruct path from i to j:
- Start at i, follow next[i][j] to get the next vertex, repeat until reaching j

Edge cases I need to handle: no path exists (dist = INF), and negative cycles (dist[i][i] < 0). The path reconstruction could loop infinitely if there is a negative cycle, so I should add a length check as a safety guard.

After running Floyd-Warshall, we can detect negative cycles by checking if dist[i][i] < 0 for any i. If so, any path passing through i can be made arbitrarily short. I considered detecting them during the main loop, but checking afterward is simpler and just as effective.
</think>

## Floyd-Warshall with Path Reconstruction

### Implementation

```python
def floyd_warshall(n, edges):
    """All-pairs shortest paths with path reconstruction.

    Args:
        n: number of nodes (0-indexed)
        edges: list of (u, v, weight) -- directed edges

    Returns:
        dist: n x n distance matrix
        nxt: n x n next-hop matrix for path reconstruction
        has_negative_cycle: boolean
    """
    INF = float('inf')

    # Initialize
    dist = [[INF] * n for _ in range(n)]
    nxt = [[-1] * n for _ in range(n)]

    for i in range(n):
        dist[i][i] = 0

    for u, v, w in edges:
        if w < dist[u][v]:
            dist[u][v] = w
            nxt[u][v] = v

    # Floyd-Warshall
    for k in range(n):
        for i in range(n):
            for j in range(n):
                if dist[i][k] < INF and dist[k][j] < INF:
                    if dist[i][k] + dist[k][j] < dist[i][j]:
                        dist[i][j] = dist[i][k] + dist[k][j]
                        nxt[i][j] = nxt[i][k]

    # Check for negative cycles
    has_negative_cycle = any(dist[i][i] < 0 for i in range(n))

    return dist, nxt, has_negative_cycle


def reconstruct_path(nxt, u, v, dist):
    """Reconstruct shortest path from u to v."""
    if dist[u][v] == float('inf'):
        return None  # no path

    path = [u]
    current = u
    while current != v:
        current = nxt[current][v]
        if current == -1:
            return None
        path.append(current)
        if len(path) > len(dist):  # cycle detection
            return None
    return path


# Demo
n = 5
edges = [
    (0, 1, 3), (0, 2, 8), (0, 4, -4),
    (1, 3, 1), (1, 4, 7),
    (2, 1, 4),
    (3, 0, 2), (3, 2, -5),
    (4, 3, 6),
]

dist, nxt, neg_cycle = floyd_warshall(n, edges)

print("=== Floyd-Warshall with Path Reconstruction ===")
print(f"Negative cycle: {neg_cycle}\n")

# Distance matrix
print("Distance matrix:")
header = "     " + "".join(f"{j:>6}" for j in range(n))
print(header)
for i in range(n):
    row = f"  {i}: "
    for j in range(n):
        d = dist[i][j]
        row += f"{'INF':>6}" if d == float('inf') else f"{d:>6}"
    print(row)

# Path reconstruction examples
print(f"\nPaths:")
pairs = [(0, 2), (0, 3), (1, 0), (3, 1), (4, 2)]
for u, v in pairs:
    path = reconstruct_path(nxt, u, v, dist)
    d = dist[u][v]
    if d == float('inf'):
        print(f"  {u} -> {v}: no path")
    else:
        print(f"  {u} -> {v}: dist={d}, path={path}")

        # Verify path distance
        total = 0
        edge_map = {}
        for a, b, w in edges:
            edge_map[(a, b)] = w
        for i in range(len(path) - 1):
            total += edge_map.get((path[i], path[i+1]), float('inf'))
        assert total == d, f"Path distance mismatch: {total} vs {d}"

print(f"\nAll paths verified correct.")

# Negative cycle example
n2 = 3
edges2 = [(0, 1, 1), (1, 2, -3), (2, 0, 1)]
dist2, nxt2, neg2 = floyd_warshall(n2, edges2)
print(f"\nNegative cycle graph:")
print(f"  Cycle: 0->1->2->0, weight = {1+(-3)+1} = -1")
print(f"  Detected: {neg2}")
print(f"  dist[0][0] = {dist2[0][0]}")
```

### Complexity
- **Time**: O(V^3)
- **Space**: O(V^2)
- **Path reconstruction**: O(V) per path
- **Negative cycle detection**: O(V) after main computation

### When to Use
- All-pairs queries needed (vs Dijkstra for single-source)
- Dense graphs (V^3 is better than V times Dijkstra on dense graphs)
- Negative weights (Dijkstra fails with negative edges)
- Small-medium V (up to ~500-1000 nodes)'''),

    ("thinking/algorithms", r'''Implement A* search algorithm for pathfinding. Show how the heuristic function guides the search, prove admissibility conditions, and compare with Dijkstra on a grid.''', r'''<think>
A* search extends Dijkstra's algorithm with a heuristic. The idea is to expand nodes in order of f(n) = g(n) + h(n), where g(n) is the actual cost from start and h(n) is the estimated cost to goal. This should guide the search toward the goal rather than expanding uniformly in all directions.

But does this always find the optimal path? Only if h(n) is admissible -- meaning it never overestimates the actual cost to goal. I initially thought any heuristic would work, but consider: if h(n) overestimates, we might skip a node that is actually on the optimal path because its f-value looks too high. So admissibility is critical for optimality.

There is a stronger property -- consistency (monotonicity): h(n) <= cost(n, n') + h(n') for all neighbors n'. This is like the triangle inequality. With consistency, each node is expanded at most once (like Dijkstra). Without it, A* is still optimal but might expand nodes multiple times, hurting performance. Hmm, actually I need to be careful here -- admissibility guarantees optimality, consistency guarantees efficiency. Most natural heuristics satisfy both.

For grid pathfinding, which heuristic should I use?
- Manhattan distance: h = |dx| + |dy| -- perfect for 4-directional movement, tight bound
- Euclidean distance: h = sqrt(dx^2 + dy^2) -- always admissible but looser than Manhattan for grid movement, so it expands more nodes
- Chebyshev distance: h = max(|dx|, |dy|) -- right for 8-directional movement

I considered using Euclidean as the default, but for 4-directional grids Manhattan is tighter and will expand fewer nodes. The tradeoff: tighter heuristic = fewer nodes expanded but more computation per node. For simple grids the per-node cost is trivial so Manhattan wins.

I will implement A* on a grid and compare the number of nodes expanded with Dijkstra (which uses h=0, making it expand uniformly).
</think>

## A* Search Algorithm

### Implementation

```python
import heapq
import math


def astar(grid, start, goal, heuristic):
    """A* search on a 2D grid.

    Args:
        grid: 2D grid (0 = passable, 1 = wall)
        start: (row, col) start position
        goal: (row, col) goal position
        heuristic: function(pos, goal) -> estimated cost

    Returns:
        (path, cost, nodes_expanded)
    """
    rows, cols = len(grid), len(grid[0])
    directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

    # f = g + h
    g_score = {start: 0}
    f_score = {start: heuristic(start, goal)}
    came_from = {}
    expanded = 0

    # Priority queue: (f_score, g_score, position)
    open_set = [(f_score[start], 0, start)]
    closed = set()

    while open_set:
        f, g, current = heapq.heappop(open_set)

        if current in closed:
            continue

        expanded += 1
        closed.add(current)

        if current == goal:
            # Reconstruct path
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path, g, expanded

        r, c = current
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 0:
                neighbor = (nr, nc)
                if neighbor in closed:
                    continue

                tentative_g = g + 1  # uniform edge cost

                if tentative_g < g_score.get(neighbor, float('inf')):
                    g_score[neighbor] = tentative_g
                    f = tentative_g + heuristic(neighbor, goal)
                    f_score[neighbor] = f
                    came_from[neighbor] = (r, c)
                    heapq.heappush(open_set, (f, tentative_g, neighbor))

    return None, float('inf'), expanded  # no path


def dijkstra_grid(grid, start, goal):
    """Dijkstra on grid (A* with h=0)."""
    return astar(grid, start, goal, lambda a, b: 0)


# Heuristic functions
def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def euclidean(a, b):
    return math.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

def zero_heuristic(a, b):
    return 0


# Demo: Create a grid with obstacles
grid = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]

start = (0, 0)
goal = (7, 14)

print("=== A* Search Algorithm ===")
print(f"Grid: {len(grid)}x{len(grid[0])}")
print(f"Start: {start}, Goal: {goal}\n")

# Compare heuristics
heuristics = [
    ("Zero (Dijkstra)", zero_heuristic),
    ("Manhattan", manhattan),
    ("Euclidean", euclidean),
]

for name, h in heuristics:
    path, cost, expanded = astar(grid, start, goal, h)
    print(f"{name:>20}: cost={cost}, expanded={expanded} nodes, "
          f"path_len={len(path) if path else 'N/A'}")

# Visualize the best path
path, _, _ = astar(grid, start, goal, manhattan)
print(f"\nPath visualization (Manhattan heuristic):")
vis = [['.' if grid[r][c] == 0 else '#' for c in range(len(grid[0]))]
       for r in range(len(grid))]
if path:
    for r, c in path:
        vis[r][c] = '*'
    vis[start[0]][start[1]] = 'S'
    vis[goal[0]][goal[1]] = 'G'
for row in vis:
    print('  ' + ' '.join(row))

# Admissibility proof
print(f"\n=== Admissibility ===")
print(f"  Manhattan: h(n) = |dx| + |dy|")
print(f"  Each step moves 1 unit in one direction")
print(f"  Actual cost >= Manhattan distance (never overestimates)")
print(f"  Therefore Manhattan is ADMISSIBLE -> A* finds optimal path")
```

### Complexity
- **Time**: O(b^d) worst case, but much better with good heuristic
- **With consistent heuristic**: each node expanded at most once, like Dijkstra
- **Space**: O(V) for open and closed sets

### Admissibility Theorem
If h(n) is admissible (never overestimates), A* is guaranteed to find the optimal path. If h(n) is also consistent, each node is expanded at most once.'''),

    ("thinking/algorithms", r'''Implement bidirectional BFS for finding the shortest path in an unweighted graph. Show how it reduces the search space and compare with standard BFS.''', r'''<think>
Bidirectional BFS runs two simultaneous BFS searches: one from the source and one from the target. When the two search frontiers meet, we have found the shortest path.

Why is this faster? My first thought was "it is roughly 2x faster" but that is way off. Standard BFS explores all nodes within distance d, which is O(b^d) where b is the branching factor. Bidirectional BFS explores O(b^(d/2)) from each side, totaling O(2 * b^(d/2)). For b=10, d=6: standard explores ~1,000,000 nodes while bidirectional explores ~2,000. That is a 500x speedup, not 2x. The key insight is that exponential functions grow so fast that halving the exponent is enormously better than halving the base.

But wait, there is a subtlety with correctness. When the two frontiers meet at a node, is that guaranteed to be on the shortest path? I considered just stopping when any node appears in both visited sets, but that could give a suboptimal path if we are not careful about level-by-level expansion. We need to expand a full level from one side before checking for intersection with the other side. Otherwise we might find a meeting point that uses a longer path through one side.

Implementation:
1. Maintain two queues (front from source, back from target)
2. Alternately expand one full level from each side
3. When a node is found in both visited sets, the path is found
4. The shortest path = path in forward search + path in backward search

For path reconstruction: maintain parent pointers for both forward and backward searches. When they meet at node m, the path is: source -> ... -> m -> ... -> target. Hmm, actually building this path requires tracing parents backward from m to source, then tracing backward parents from m to target. I need to be careful to reverse the first half.

Should I alternate strictly, or expand the smaller frontier? Expanding the smaller frontier first is better because it keeps both frontiers roughly the same size, maximizing the chance of early intersection.

Edge cases: source == target (path length 0), disconnected graph (no meeting point -- both queues empty).
</think>

## Bidirectional BFS

### Implementation

```python
from collections import deque, defaultdict


def bfs_standard(adj, source, target):
    """Standard BFS. Returns (distance, path, nodes_expanded)."""
    if source == target:
        return 0, [source], 1

    visited = {source: None}  # node -> parent
    queue = deque([source])
    expanded = 0

    while queue:
        u = queue.popleft()
        expanded += 1

        for v in adj[u]:
            if v not in visited:
                visited[v] = u
                if v == target:
                    # Reconstruct path
                    path = [v]
                    while path[-1] != source:
                        path.append(visited[path[-1]])
                    path.reverse()
                    return len(path) - 1, path, expanded
                queue.append(v)

    return -1, [], expanded  # no path


def bfs_bidirectional(adj, source, target):
    """Bidirectional BFS. Returns (distance, path, nodes_expanded)."""
    if source == target:
        return 0, [source], 1

    # Forward search from source
    fwd_visited = {source: None}
    fwd_queue = deque([source])

    # Backward search from target
    bwd_visited = {target: None}
    bwd_queue = deque([target])

    expanded = 0

    while fwd_queue and bwd_queue:
        # Expand the smaller frontier
        if len(fwd_queue) <= len(bwd_queue):
            # Expand one level of forward
            level_size = len(fwd_queue)
            for _ in range(level_size):
                u = fwd_queue.popleft()
                expanded += 1
                for v in adj[u]:
                    if v not in fwd_visited:
                        fwd_visited[v] = u
                        fwd_queue.append(v)
                    if v in bwd_visited:
                        # Meeting point found
                        path = _build_path(fwd_visited, bwd_visited, v, source, target)
                        return len(path) - 1, path, expanded
        else:
            # Expand one level of backward
            level_size = len(bwd_queue)
            for _ in range(level_size):
                u = bwd_queue.popleft()
                expanded += 1
                for v in adj[u]:
                    if v not in bwd_visited:
                        bwd_visited[v] = u
                        bwd_queue.append(v)
                    if v in fwd_visited:
                        path = _build_path(fwd_visited, bwd_visited, v, source, target)
                        return len(path) - 1, path, expanded

    return -1, [], expanded


def _build_path(fwd_visited, bwd_visited, meeting, source, target):
    """Build path from forward and backward parent maps."""
    # Forward path: source -> meeting
    fwd_path = [meeting]
    v = meeting
    while v != source:
        v = fwd_visited[v]
        fwd_path.append(v)
    fwd_path.reverse()

    # Backward path: meeting -> target
    v = meeting
    while v != target:
        v = bwd_visited[v]
        fwd_path.append(v)

    return fwd_path


# Demo: Grid graph
def make_grid_graph(rows, cols):
    adj = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            node = r * cols + c
            if c + 1 < cols:
                adj[node].append(node + 1)
                adj[node + 1].append(node)
            if r + 1 < rows:
                adj[node].append(node + cols)
                adj[node + cols].append(node)
    return adj, rows * cols


print("=== Bidirectional BFS ===\n")

# Test on grid graphs of various sizes
for rows, cols in [(10, 10), (20, 20), (30, 30)]:
    adj, n = make_grid_graph(rows, cols)
    source = 0
    target = n - 1

    d1, p1, e1 = bfs_standard(adj, source, target)
    d2, p2, e2 = bfs_bidirectional(adj, source, target)

    print(f"Grid {rows}x{cols} ({n} nodes):")
    print(f"  Standard BFS:      dist={d1}, expanded={e1}")
    print(f"  Bidirectional BFS: dist={d2}, expanded={e2}")
    print(f"  Speedup: {e1/max(e2,1):.1f}x")
    print(f"  Paths match: {d1 == d2}")
    print()

# Tree-like graph (high branching factor)
print("=== High Branching Factor ===")
adj2 = defaultdict(list)
# Build a tree with branching factor 4, depth 5
node_id = [0]
def build_tree(parent, depth, max_depth, branching):
    if depth >= max_depth:
        return
    for _ in range(branching):
        node_id[0] += 1
        child = node_id[0]
        adj2[parent].append(child)
        adj2[child].append(parent)
        build_tree(child, depth + 1, max_depth, branching)

build_tree(0, 0, 5, 4)
n_tree = node_id[0] + 1
target_node = node_id[0]  # deepest node

d1, _, e1 = bfs_standard(adj2, 0, target_node)
d2, _, e2 = bfs_bidirectional(adj2, 0, target_node)
print(f"Tree (branching=4, depth=5, {n_tree} nodes):")
print(f"  Standard: dist={d1}, expanded={e1}")
print(f"  Bidirectional: dist={d2}, expanded={e2}")
print(f"  Speedup: {e1/max(e2,1):.1f}x")
```

### Why Bidirectional BFS is Faster
```
Standard BFS: explores O(b^d) nodes
Bidirectional: explores O(2 * b^(d/2)) nodes

For b=10, d=6:
  Standard: 10^6 = 1,000,000
  Bidirectional: 2 * 10^3 = 2,000
  Speedup: 500x
```

### Complexity
- **Time**: O(b^(d/2)) vs O(b^d) for standard BFS
- **Space**: O(b^(d/2)) for visited sets
- **Optimal**: finds shortest path (same guarantee as BFS)'''),
]
