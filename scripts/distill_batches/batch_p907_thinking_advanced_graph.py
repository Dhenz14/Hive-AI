PAIRS = [
    ("thinking/algorithms", r'''Implement the Ford-Fulkerson algorithm for computing maximum flow in a flow network using BFS (Edmonds-Karp variant). Given a directed graph with capacities, find the maximum flow from source to sink.''', r'''<think>
Maximum flow problem: find the maximum amount of flow from source s to sink t in a directed graph with capacity constraints.

My first instinct is to use DFS to find augmenting paths... but wait, basic Ford-Fulkerson with DFS can loop forever on irrational capacities, and even on integer capacities it could be O(E * max_flow) which is pseudo-polynomial. That is a trap. I considered using DFS because it is simpler to implement, but the Edmonds-Karp variant with BFS is strictly better here since it guarantees O(V * E^2) time complexity regardless of capacity values.

Hmm, actually let me reconsider the complexity. Each BFS finds the shortest augmenting path, and after at most O(V * E) augmentations the flow is maximal. So the total work is O(V * E) augmentations times O(E) per BFS, giving O(V * E^2). That makes sense because each augmentation increases the shortest-path distance by at least 1, and the shortest path length is bounded by V.

Key data structure: residual graph. For each edge (u, v) with capacity c and flow f:
- Forward edge: residual capacity = c - f
- Backward edge: residual capacity = f (allows "undoing" flow)

I need to store edges and their reverses. I could use an adjacency matrix... but that would be O(V^2) space and slow for sparse graphs. Actually, the standard approach is to store edges in a flat list where edge i and edge i^1 are reverse pairs (using XOR to find the reverse). This is more memory-efficient and the XOR trick is elegant because if edge 0 pairs with edge 1, edge 2 with edge 3, etc. -- flipping the last bit always gives you the reverse edge.

Wait, one subtlety: backward edges start with capacity 0, not with the original capacity. The backward edge capacity grows as we push flow, since it represents the ability to "undo" previously sent flow. I initially thought both edges should have the original capacity but that is wrong -- only the forward edge does.

Algorithm:
1. Build residual graph
2. While BFS finds a path from s to t:
   a. Find bottleneck (min residual capacity on path)
   b. Update residual capacities along path
3. Return total flow

Let me implement this cleanly.
</think>

## Edmonds-Karp Maximum Flow (BFS-based Ford-Fulkerson)

```python
from typing import List, Tuple, Optional
from collections import deque


class MaxFlow:
    """
    Edmonds-Karp maximum flow algorithm (Ford-Fulkerson with BFS).

    Time:  O(V * E^2)
    Space: O(V + E)
    """

    def __init__(self, n: int) -> None:
        self.n = n
        self.graph: List[List[int]] = [[] for _ in range(n)]
        # Each edge: [to, capacity, flow]
        self.edges: List[List[int]] = []

    def add_edge(self, u: int, v: int, cap: int) -> None:
        """Add directed edge u -> v with capacity cap."""
        # Forward edge
        self.graph[u].append(len(self.edges))
        self.edges.append([v, cap, 0])
        # Reverse edge (capacity 0)
        self.graph[v].append(len(self.edges))
        self.edges.append([u, 0, 0])

    def _bfs(self, s: int, t: int) -> Optional[List[int]]:
        """BFS to find shortest augmenting path. Returns parent edge array."""
        parent_edge = [-1] * self.n
        visited = [False] * self.n
        visited[s] = True
        queue: deque[int] = deque([s])

        while queue:
            u = queue.popleft()
            for eid in self.graph[u]:
                e = self.edges[eid]
                v, cap, flow = e
                if not visited[v] and cap - flow > 0:
                    visited[v] = True
                    parent_edge[v] = eid
                    if v == t:
                        return parent_edge
                    queue.append(v)

        return None

    def max_flow(self, s: int, t: int) -> int:
        """
        Compute maximum flow from source s to sink t.

        Returns:
            Maximum flow value.
        """
        total_flow = 0

        while True:
            parent_edge = self._bfs(s, t)
            if parent_edge is None:
                break

            # Find bottleneck
            bottleneck = float('inf')
            v = t
            while v != s:
                eid = parent_edge[v]
                e = self.edges[eid]
                bottleneck = min(bottleneck, e[1] - e[2])
                v = self.edges[eid ^ 1][0]  # go to the other endpoint

            # Update flow along path
            v = t
            while v != s:
                eid = parent_edge[v]
                self.edges[eid][2] += bottleneck      # forward flow
                self.edges[eid ^ 1][2] -= bottleneck   # reverse flow
                v = self.edges[eid ^ 1][0]

            total_flow += bottleneck

        return total_flow

    def get_min_cut(self, s: int) -> Tuple[List[int], List[int]]:
        """
        After computing max flow, find the min cut.
        Returns (S_side, T_side) partition.
        """
        visited = [False] * self.n
        queue: deque[int] = deque([s])
        visited[s] = True
        while queue:
            u = queue.popleft()
            for eid in self.graph[u]:
                e = self.edges[eid]
                v, cap, flow = e
                if not visited[v] and cap - flow > 0:
                    visited[v] = True
                    queue.append(v)

        s_side = [i for i in range(self.n) if visited[i]]
        t_side = [i for i in range(self.n) if not visited[i]]
        return s_side, t_side


# ---------- Tests ----------

def test_simple():
    # 0 -> 1 (cap 3), 0 -> 2 (cap 2), 1 -> 3 (cap 2), 2 -> 3 (cap 3)
    mf = MaxFlow(4)
    mf.add_edge(0, 1, 3)
    mf.add_edge(0, 2, 2)
    mf.add_edge(1, 3, 2)
    mf.add_edge(2, 3, 3)
    result = mf.max_flow(0, 3)
    assert result == 4, f"Expected 4, got {result}"
    print(f"Simple graph max flow: {result}")


def test_classic():
    # Classic Ford-Fulkerson example
    #    10    10
    # 0 ---> 1 ---> 3
    # |      |^     ^
    # |10   1| |10  |10
    # v      v |    |
    # 2 ---> 4 ---> 5 (sink=5, source=0... let me simplify)
    mf = MaxFlow(4)
    mf.add_edge(0, 1, 1000)
    mf.add_edge(0, 2, 1000)
    mf.add_edge(1, 2, 1)
    mf.add_edge(1, 3, 1000)
    mf.add_edge(2, 3, 1000)
    result = mf.max_flow(0, 3)
    assert result == 2000, f"Expected 2000, got {result}"
    print(f"Classic example max flow: {result}")


def test_min_cut():
    mf = MaxFlow(4)
    mf.add_edge(0, 1, 3)
    mf.add_edge(0, 2, 2)
    mf.add_edge(1, 3, 2)
    mf.add_edge(2, 3, 3)
    flow = mf.max_flow(0, 3)
    s_side, t_side = mf.get_min_cut(0)
    print(f"Min cut: S={s_side}, T={t_side}, flow={flow}")
    assert flow == 4


if __name__ == "__main__":
    test_simple()
    test_classic()
    test_min_cut()
    print("All max flow tests passed!")
```

### Complexity
- **Time:** O(V * E^2). BFS finds shortest augmenting paths, and each path increases the shortest-path distance by at least 1, bounding iterations to O(V * E).
- **Space:** O(V + E) for the residual graph.
- **Max-Flow Min-Cut Theorem:** The maximum flow equals the minimum cut capacity, and the min cut is recoverable by finding nodes reachable from source in the final residual graph.
'''),

    ("thinking/algorithms", r'''Implement Kruskal's algorithm for Minimum Spanning Tree using a Union-Find (Disjoint Set Union) data structure with path compression and union by rank. Return the MST edges and total weight.''', r'''<think>
Kruskal's algorithm for MST. My first thought is to sort all edges by weight and greedily add them... but wait, I need to avoid creating cycles. How do I check for cycles efficiently?

I considered using DFS/BFS to check connectivity each time we add an edge, but that would be O(V) per edge check, giving O(V * E) total. That is way too slow for large graphs. Actually, Union-Find (Disjoint Set Union) is perfect here because it reduces cycle detection to near-constant time.

Union-Find has two key optimizations:
- Path compression: make every node on the find path point directly to root
- Union by rank: attach smaller tree under root of larger tree

Hmm, do I need both? Path compression alone gives O(log N) amortized, and union by rank alone also gives O(log N) worst case. But together they achieve O(alpha(N)) amortized, where alpha is the inverse Ackermann function. Since alpha(N) <= 4 for all practical N (even up to 10^80), this is effectively O(1). So yes, both optimizations are worth including.

Therefore the total time is O(E log E) dominated by sorting. The Union-Find operations contribute O(E * alpha(V)) which is negligible compared to sorting.

One thing I almost forgot: I need to handle disconnected graphs. If after processing all edges we have fewer than V-1 MST edges, the graph is disconnected and no spanning tree exists. I should return None in that case rather than returning an incomplete tree.

I can also early-terminate once we have exactly V-1 edges, since that completes the tree.
</think>

## Kruskal's MST with Union-Find

```python
from typing import List, Tuple, Optional


class UnionFind:
    """
    Disjoint Set Union with path compression and union by rank.

    Operations are nearly O(1) amortized — O(alpha(N)).
    """

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n
        self.components = n

    def find(self, x: int) -> int:
        """Find root with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        """
        Merge sets containing x and y.
        Returns True if they were in different sets (merge happened).
        """
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


def kruskal_mst(
    n: int,
    edges: List[Tuple[int, int, float]],
) -> Optional[Tuple[float, List[Tuple[int, int, float]]]]:
    """
    Compute MST using Kruskal's algorithm.

    Args:
        n: Number of vertices (0-indexed).
        edges: List of (u, v, weight) undirected edges.

    Returns:
        (total_weight, mst_edges) or None if graph is disconnected.

    Time:  O(E log E)
    Space: O(V + E)
    """
    sorted_edges = sorted(edges, key=lambda e: e[2])
    uf = UnionFind(n)
    mst_edges: List[Tuple[int, int, float]] = []
    total_weight = 0.0

    for u, v, w in sorted_edges:
        if uf.union(u, v):
            mst_edges.append((u, v, w))
            total_weight += w
            if len(mst_edges) == n - 1:
                break

    if len(mst_edges) != n - 1:
        return None  # Graph is disconnected

    return (total_weight, mst_edges)


# ---------- Tests ----------

def test_simple():
    # Triangle: 0-1 (1), 1-2 (2), 0-2 (3)
    # MST: edges (0,1,1) and (1,2,2) with total 3
    edges = [(0, 1, 1), (1, 2, 2), (0, 2, 3)]
    result = kruskal_mst(3, edges)
    assert result is not None
    total, mst = result
    assert total == 3, f"Expected 3, got {total}"
    print(f"Triangle MST: weight={total}, edges={mst}")


def test_classic():
    # 4 nodes, 5 edges
    edges = [
        (0, 1, 10), (0, 2, 6), (0, 3, 5),
        (1, 3, 15), (2, 3, 4),
    ]
    result = kruskal_mst(4, edges)
    assert result is not None
    total, mst = result
    # MST: (2,3,4), (0,3,5), (0,1,10) = 19
    assert total == 19, f"Expected 19, got {total}"
    print(f"Classic MST: weight={total}, edges={mst}")


def test_disconnected():
    edges = [(0, 1, 1)]  # 3 nodes but only 1 edge
    result = kruskal_mst(3, edges)
    assert result is None
    print("Disconnected graph: correctly returned None")


if __name__ == "__main__":
    test_simple()
    test_classic()
    test_disconnected()
    print("All Kruskal MST tests passed!")
```

### Complexity
- **Time:** O(E log E) for sorting edges. Union-Find operations are O(alpha(N)) ≈ O(1).
- **Space:** O(V + E)
- Kruskal's is particularly efficient for sparse graphs. For dense graphs, Prim's with a priority queue may be preferable.

### Why Union by Rank + Path Compression
- **Path compression** alone gives O(log N) amortized per operation.
- **Union by rank** alone gives O(log N) worst case.
- **Together** they achieve O(alpha(N)) amortized, which is effectively constant for all practical inputs (alpha(N) <= 4 for N up to 10^80).
'''),

    ("thinking/algorithms", r'''Implement the Bellman-Ford algorithm for single-source shortest paths that also detects negative-weight cycles. If a negative cycle is reachable from the source, report it and reconstruct the cycle.''', r'''<think>
Bellman-Ford: relax all edges V-1 times. But why exactly V-1? Because the shortest path from source to any node has at most V-1 edges (otherwise it would revisit a node, implying a cycle, which would only help if it were a negative cycle). So after V-1 rounds of relaxation, all shortest distances are finalized -- unless there is a negative cycle.

If after V-1 iterations we can still relax an edge, there must be a negative cycle. That is the key detection step.

Now, reconstructing the actual cycle is trickier. I initially thought I could just follow parent pointers from the relaxed node... but wait, the node where we detect further relaxation might not be on the cycle itself -- it could just be reachable from the cycle. So I need to walk back through parent pointers N times from that node to guarantee I land inside the cycle (since the cycle has at most N nodes, walking back N steps must enter it). Then I trace parents until I revisit a node to extract the cycle. Actually, let me double-check: could the parent chain lead through a non-cyclic path? No, because if further relaxation is possible, the parent chain must eventually loop through a negative cycle. Walking N steps guarantees we are inside it.

Time: O(V * E), Space: O(V).

Edge case I was worried about: what about negative cycles not reachable from the source? Initially I thought we might detect those too, but actually no -- since we initialize dist[source] = 0 and everything else to infinity, edges from unreachable nodes never trigger relaxation (because dist[u] = infinity means dist[u] + w is still infinity, never less than dist[v]). So we correctly only find negative cycles reachable from the source. That is the right behavior.

Another optimization: I can add early termination. If no edge gets relaxed in a full pass, the algorithm is done -- no need to continue the remaining iterations. This helps significantly in practice for graphs without negative cycles.
</think>

## Bellman-Ford with Negative Cycle Detection and Reconstruction

```python
from typing import List, Tuple, Optional


def bellman_ford(
    n: int,
    edges: List[Tuple[int, int, float]],
    source: int,
) -> Tuple[List[float], List[int], Optional[List[int]]]:
    """
    Single-source shortest paths with negative cycle detection.

    Args:
        n: Number of vertices (0-indexed).
        edges: List of (u, v, weight) directed edges.
        source: Source vertex.

    Returns:
        (dist, parent, negative_cycle) where:
        - dist[v] = shortest distance from source to v (inf if unreachable)
        - parent[v] = predecessor on shortest path
        - negative_cycle = list of vertices forming a negative cycle, or None

    Time:  O(V * E)
    Space: O(V + E)
    """
    INF = float('inf')
    dist = [INF] * n
    parent = [-1] * n
    dist[source] = 0

    # Relax all edges V-1 times
    for _ in range(n - 1):
        updated = False
        for u, v, w in edges:
            if dist[u] < INF and dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                parent[v] = u
                updated = True
        if not updated:
            break  # Early termination

    # Check for negative cycles (Vth iteration)
    cycle_node = -1
    for u, v, w in edges:
        if dist[u] < INF and dist[u] + w < dist[v]:
            dist[v] = dist[u] + w
            parent[v] = u
            cycle_node = v
            break

    if cycle_node == -1:
        return (dist, parent, None)

    # Reconstruct negative cycle
    # Walk back N steps to ensure we're inside the cycle
    v = cycle_node
    for _ in range(n):
        v = parent[v]

    # Now v is on the cycle. Walk until we return to v.
    cycle: List[int] = []
    u = v
    while True:
        cycle.append(u)
        u = parent[u]
        if u == v:
            cycle.append(v)
            break

    cycle.reverse()
    return (dist, parent, cycle)


# ---------- Tests ----------

def test_no_negative_cycle():
    # Simple graph with negative edge but no negative cycle
    edges = [
        (0, 1, 4), (0, 2, 5), (1, 2, -3), (2, 3, 4),
    ]
    dist, parent, cycle = bellman_ford(4, edges, 0)
    assert cycle is None
    assert dist[0] == 0
    assert dist[1] == 4
    assert dist[2] == 1  # 0->1->2 = 4 + (-3) = 1
    assert dist[3] == 5  # 0->1->2->3 = 1 + 4 = 5
    print(f"No negative cycle: dist={dist}")


def test_negative_cycle():
    # 0 -> 1 (1), 1 -> 2 (-1), 2 -> 0 (-1)
    # Cycle: 0 -> 1 -> 2 -> 0 with total weight -1 (negative!)
    edges = [
        (0, 1, 1), (1, 2, -1), (2, 0, -1),
    ]
    dist, parent, cycle = bellman_ford(3, edges, 0)
    assert cycle is not None, "Expected negative cycle"
    # Verify cycle has negative total weight
    total = 0
    for i in range(len(cycle) - 1):
        u, v = cycle[i], cycle[i + 1]
        for eu, ev, ew in edges:
            if eu == u and ev == v:
                total += ew
                break
    assert total < 0, f"Cycle weight {total} should be negative"
    print(f"Negative cycle found: {cycle}, weight={total}")


def test_unreachable():
    edges = [(0, 1, 5)]
    dist, parent, cycle = bellman_ford(3, edges, 0)
    assert dist[2] == float('inf')
    assert cycle is None
    print(f"Unreachable node: dist={dist}")


if __name__ == "__main__":
    test_no_negative_cycle()
    test_negative_cycle()
    test_unreachable()
    print("All Bellman-Ford tests passed!")
```

### Complexity
- **Time:** O(V * E) — V-1 relaxation passes over all E edges
- **Space:** O(V + E)
- Early termination if no updates in a pass can help in practice

### Negative Cycle Reconstruction
After finding a node `v` that can still be relaxed in the Vth pass, we walk back through parent pointers N times. This guarantees we land inside the cycle (since the cycle has at most N nodes). Then we trace the cycle by walking parents until we revisit the same node.

### Comparison with Dijkstra
Dijkstra is faster (O(E log V)) but fails with negative edges. Bellman-Ford handles negative edges and detects negative cycles, at the cost of higher time complexity.
'''),

    ("thinking/algorithms", r'''Implement A* pathfinding algorithm on a 2D grid. Given a grid where some cells are blocked, find the shortest path from start to goal. Use Manhattan distance as the heuristic. Return the path and its cost.''', r'''<think>
A* pathfinding. My first thought is to use Dijkstra's algorithm, since it finds shortest paths... but wait, Dijkstra explores in all directions uniformly, which wastes time when we have a specific target. A* improves on this by adding a heuristic that guides the search toward the goal.

f(n) = g(n) + h(n) where:
- g(n) = actual cost from start to n
- h(n) = heuristic estimate of cost from n to goal

The heuristic must be admissible (never overestimates) and consistent (h(n) <= cost(n,n') + h(n')). If it is not admissible, A* might return a suboptimal path. If it is admissible but not consistent, we might need to re-expand nodes, losing the guarantee that each node is expanded at most once.

For 4-directional grid movement with uniform cost, Manhattan distance |dx| + |dy| is the tightest admissible heuristic. I considered using Euclidean distance, but actually that would be looser -- sqrt(dx^2 + dy^2) <= |dx| + |dy|, so Euclidean underestimates more, causing A* to explore more nodes than necessary. Manhattan is exact for the movement model, so it prunes maximally.

Hmm, what about 8-directional movement? Then I would need Chebyshev distance max(|dx|, |dy|) instead. But the problem specifies a grid with standard movement, so Manhattan is correct here.

Algorithm:
1. Priority queue (min-heap) ordered by f = g + h
2. Keep track of g-values (best known cost to reach each node)
3. When we pop the goal, we are done -- this works because consistency guarantees f-values are non-decreasing along any path, so the first time we pop the goal it must be via the shortest path

I also need a came_from dictionary to reconstruct the path. And a closed set to avoid re-expanding nodes, which is valid because the heuristic is consistent.
</think>

## A* Pathfinding on a 2D Grid

```python
from typing import List, Tuple, Optional
import heapq


def astar_grid(
    grid: List[List[int]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
) -> Optional[Tuple[int, List[Tuple[int, int]]]]:
    """
    A* pathfinding on a 2D grid with 4-directional movement.

    Args:
        grid: 2D grid where 0 = passable, 1 = blocked.
        start: (row, col) start position.
        goal: (row, col) goal position.

    Returns:
        (cost, path) where path is list of (row, col) from start to goal,
        or None if no path exists.

    Time:  O(V log V) where V = rows * cols (worst case explores all cells)
    Space: O(V)
    """
    rows, cols = len(grid), len(grid[0])
    sr, sc = start
    gr, gc = goal

    if grid[sr][sc] == 1 or grid[gr][gc] == 1:
        return None

    def heuristic(r: int, c: int) -> int:
        """Manhattan distance — admissible and consistent for 4-dir movement."""
        return abs(r - gr) + abs(c - gc)

    # Priority queue: (f, g, row, col)
    open_set: List[Tuple[int, int, int, int]] = [(heuristic(sr, sc), 0, sr, sc)]
    g_score: dict[Tuple[int, int], int] = {start: 0}
    came_from: dict[Tuple[int, int], Tuple[int, int]] = {}
    closed: set[Tuple[int, int]] = set()

    directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

    while open_set:
        f, g, r, c = heapq.heappop(open_set)

        if (r, c) == goal:
            # Reconstruct path
            path: List[Tuple[int, int]] = [(r, c)]
            while (r, c) in came_from:
                r, c = came_from[(r, c)]
                path.append((r, c))
            path.reverse()
            return (g, path)

        if (r, c) in closed:
            continue
        closed.add((r, c))

        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 0:
                new_g = g + 1
                if new_g < g_score.get((nr, nc), float('inf')):
                    g_score[(nr, nc)] = new_g
                    came_from[(nr, nc)] = (r, c)
                    new_f = new_g + heuristic(nr, nc)
                    heapq.heappush(open_set, (new_f, new_g, nr, nc))

    return None  # No path found


# ---------- Tests ----------

def test_simple():
    grid = [
        [0, 0, 0],
        [0, 1, 0],
        [0, 0, 0],
    ]
    result = astar_grid(grid, (0, 0), (2, 2))
    assert result is not None
    cost, path = result
    assert cost == 4, f"Expected cost 4, got {cost}"
    assert path[0] == (0, 0) and path[-1] == (2, 2)
    print(f"Simple: cost={cost}, path={path}")


def test_no_path():
    grid = [
        [0, 1, 0],
        [0, 1, 0],
        [0, 1, 0],
    ]
    result = astar_grid(grid, (0, 0), (0, 2))
    assert result is None
    print("No path: correctly returned None")


def test_straight_line():
    grid = [[0] * 5 for _ in range(1)]
    result = astar_grid(grid, (0, 0), (0, 4))
    assert result is not None
    cost, path = result
    assert cost == 4
    assert len(path) == 5
    print(f"Straight line: cost={cost}, path={path}")


if __name__ == "__main__":
    test_simple()
    test_no_path()
    test_straight_line()
    print("All A* tests passed!")
```

### Why A* is Optimal
With an admissible heuristic (never overestimates), A* is guaranteed to find the shortest path. With a consistent heuristic (triangle inequality), each node is expanded at most once, making the closed set optimization valid.

### Complexity
- **Time:** O(V log V) worst case where V = grid cells, due to the priority queue. In practice, A* explores far fewer cells than Dijkstra when the heuristic is informative.
- **Space:** O(V) for the open/closed sets and g-scores.

### Manhattan vs Euclidean Heuristic
- **Manhattan** (`|dx| + |dy|`): admissible for 4-directional movement. Tighter heuristic means fewer explored nodes.
- **Euclidean** (`sqrt(dx^2 + dy^2)`): admissible for any movement, but looser — more exploration.
- **Chebyshev** (`max(|dx|, |dy|)`): admissible for 8-directional movement.
'''),

    ("thinking/algorithms", r'''Implement an algorithm to find an Euler path or Euler circuit in a graph. Given an undirected graph, determine if an Euler path/circuit exists, and if so, find one using Hierholzer's algorithm.''', r'''<think>
Euler path: visits every edge exactly once.
Euler circuit: Euler path that starts and ends at the same vertex.

First, when does an Euler path/circuit even exist? For an undirected graph:
- Euler circuit exists iff all vertices have even degree (and the graph is connected among vertices with edges)
- Euler path exists iff exactly 0 or 2 vertices have odd degree

I initially thought any connected graph would have an Euler path, but that is wrong -- consider a star graph with 4 leaves: the center has degree 4 (even) but each leaf has degree 1 (odd), giving 4 odd-degree vertices. Since 4 is not 0 or 2, no Euler path exists.

Now for the algorithm. I considered naive DFS: follow edges, backtrack when stuck. But wait, naive DFS can get stuck in a dead end if it does not explore sub-tours properly, and backtracking to fix this could be O(E^2) in the worst case.

Hierholzer's algorithm solves this efficiently with a stack-based approach:
- Start at vertex, push onto stack
- While stack is non-empty:
  - If current vertex has remaining edges, follow one (remove it) and push the new vertex
  - Else, pop and add to result (building the path in reverse)

The key insight is that when we get stuck at a vertex (no remaining edges), we know we have completed a sub-tour through that vertex. By popping to the result, we effectively splice sub-tours together. Actually, I realize this works because at any stuck point, all edges incident to that vertex have been used (since we entered and left an equal number of times for even-degree vertices).

For undirected graphs, there is a subtlety: when I traverse edge (u,v), I must also mark the same edge as used from v's perspective. I will use edge indices and a visited array, so marking edge i as used prevents traversal from both directions.

Time: O(V + E), Space: O(V + E). Each edge is visited exactly once, making this optimal.
</think>

## Hierholzer's Algorithm for Euler Path/Circuit

```python
from typing import List, Tuple, Optional
from collections import defaultdict


def find_euler_path(
    n: int,
    edges: List[Tuple[int, int]],
) -> Optional[List[int]]:
    """
    Find an Euler path or circuit in an undirected graph using Hierholzer's algorithm.

    Args:
        n: Number of vertices (0-indexed).
        edges: List of (u, v) undirected edges.

    Returns:
        List of vertices forming the Euler path/circuit, or None if impossible.
        For a circuit, first == last vertex.

    Time:  O(E)
    Space: O(V + E)
    """
    if not edges:
        return [0] if n > 0 else []

    # Build adjacency list with edge indices
    adj: List[List[List[int]]] = [[] for _ in range(n)]
    for i, (u, v) in enumerate(edges):
        adj[u].append([v, i])
        adj[v].append([u, i])

    # Check degree conditions
    degree = [len(adj[v]) for v in range(n)]
    odd_vertices = [v for v in range(n) if degree[v] % 2 == 1]

    if len(odd_vertices) not in (0, 2):
        return None  # No Euler path/circuit possible

    # Check connectivity (among vertices with edges)
    vertices_with_edges = {v for v in range(n) if degree[v] > 0}
    if not vertices_with_edges:
        return [0] if n > 0 else []

    start_v = min(vertices_with_edges)
    visited_nodes = set()
    stack = [start_v]
    while stack:
        v = stack.pop()
        if v in visited_nodes:
            continue
        visited_nodes.add(v)
        for neighbor, _ in adj[v]:
            if neighbor not in visited_nodes:
                stack.append(neighbor)

    if visited_nodes != vertices_with_edges:
        return None  # Graph not connected

    # Choose starting vertex
    if len(odd_vertices) == 2:
        start = odd_vertices[0]
    else:
        start = min(vertices_with_edges)

    # Hierholzer's algorithm
    used_edge = [False] * len(edges)
    # Track current position in adjacency list for each vertex
    adj_idx = [0] * n
    path_stack: List[int] = [start]
    result: List[int] = []

    while path_stack:
        v = path_stack[-1]
        found = False
        while adj_idx[v] < len(adj[v]):
            neighbor, edge_id = adj[v][adj_idx[v]]
            adj_idx[v] += 1
            if not used_edge[edge_id]:
                used_edge[edge_id] = True
                path_stack.append(neighbor)
                found = True
                break
        if not found:
            result.append(path_stack.pop())

    result.reverse()

    # Verify all edges used
    if len(result) != len(edges) + 1:
        return None

    return result


# ---------- Tests ----------

def test_circuit():
    # Triangle: 0-1, 1-2, 2-0 → Euler circuit
    edges = [(0, 1), (1, 2), (2, 0)]
    path = find_euler_path(3, edges)
    assert path is not None
    assert len(path) == 4  # 3 edges + 1
    assert path[0] == path[-1]  # circuit
    print(f"Triangle circuit: {path}")


def test_path():
    # 0-1, 1-2, 2-3, 3-1 → vertices 0 and 3 have odd degree → Euler path
    edges = [(0, 1), (1, 2), (2, 3), (3, 1)]
    path = find_euler_path(4, edges)
    assert path is not None
    assert len(path) == 5
    ends = {path[0], path[-1]}
    assert ends == {0, 3} or ends <= {0, 3}
    print(f"Euler path: {path}")


def test_impossible():
    # 4 vertices, all odd degree
    edges = [(0, 1), (2, 3)]
    path = find_euler_path(4, edges)
    # Disconnected with both components having Euler paths...
    # but the graph is disconnected so no single Euler path
    assert path is None
    print("Impossible case: correctly returned None")


if __name__ == "__main__":
    test_circuit()
    test_path()
    test_impossible()
    print("All Euler path tests passed!")
```

### Complexity
- **Time:** O(V + E) — each edge is visited exactly once, each vertex is processed proportional to its degree.
- **Space:** O(V + E) for adjacency lists and the stack.

### Hierholzer's Key Insight
Instead of DFS with backtracking (which can be O(E^2) in naive implementations), Hierholzer's algorithm uses a stack to efficiently interleave sub-tour construction. When stuck at a vertex with no remaining edges, it pops to the result. When it later encounters a vertex with remaining edges, it extends from there. This single-pass approach achieves linear time.

### Euler Conditions Summary
| Graph Type | Euler Circuit | Euler Path |
|-----------|---------------|------------|
| Undirected | All even degree | 0 or 2 odd-degree vertices |
| Directed | in-degree = out-degree for all | At most 1 vertex with out-in=1, at most 1 with in-out=1 |
'''),
]
