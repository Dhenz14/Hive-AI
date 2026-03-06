PAIRS = [
    ("thinking/algorithms", r'''Implement Dijkstra's shortest path algorithm that also detects if negative-weight edges are present in the graph (and refuses to run, explaining why). Return the shortest distances and the actual paths from a source to all vertices.

Example:
Graph: {0: [(1, 4), (2, 1)], 1: [(3, 1)], 2: [(1, 2), (3, 5)], 3: []}
Source: 0
Output: distances = {0: 0, 1: 3, 2: 1, 3: 4}, paths = {0: [0], 1: [0,2,1], 2: [0,2], 3: [0,2,1,3]}''', r'''<think>
Dijkstra's algorithm finds shortest paths from a single source in a graph with non-negative edge weights. The critical thing here is that Dijkstra does NOT work correctly with negative edges — it can produce wrong results because once a node is "finalized" (popped from the priority queue), Dijkstra assumes no shorter path exists, which negative edges can violate.

So the approach should be:
1. First scan all edges. If any edge has negative weight, raise an error / return a warning suggesting Bellman-Ford instead.
2. If all edges are non-negative, proceed with Dijkstra.

For the algorithm itself:
- Use a min-heap (priority queue)
- Track distances and predecessors for path reconstruction
- Standard relaxation: if dist[u] + weight < dist[v], update

Let me think about implementation details:
- Graph represented as adjacency list: dict[int, list[tuple[int, int]]] mapping node -> [(neighbor, weight)]
- Priority queue entries: (distance, node)
- Need a visited/finalized set to avoid reprocessing

For path reconstruction, I maintain `prev[v]` = predecessor of v on the shortest path. Then walk back from target to source.

Edge cases:
- Source node not in graph
- Disconnected nodes (distance = infinity, no path)
- Self-loops with weight 0
- Graph with single node

Time: O((V + E) log V) with a binary heap
Space: O(V + E)

Wait, I should also handle the case where the graph has nodes that appear only as targets (not as keys in the adjacency list). I'll collect all nodes first.

Let me code this up carefully.
</think>

## Dijkstra's Shortest Path with Negative Edge Detection and Path Reconstruction

```python
import heapq
from typing import Dict, List, Optional, Tuple


Graph = Dict[int, List[Tuple[int, int]]]  # node -> [(neighbor, weight)]


class NegativeEdgeError(Exception):
    """Raised when Dijkstra encounters a negative edge weight."""
    pass


def dijkstra(
    graph: Graph, source: int
) -> Tuple[Dict[int, float], Dict[int, List[int]]]:
    """
    Run Dijkstra's algorithm from source. Detects negative edges and raises
    NegativeEdgeError if found.

    Args:
        graph: Adjacency list with (neighbor, weight) tuples.
        source: Starting vertex.

    Returns:
        Tuple of (distances_dict, paths_dict).
        Unreachable nodes have distance float('inf') and empty path.

    Raises:
        NegativeEdgeError: If any edge has negative weight.
    """
    # Step 1: Detect negative edges
    all_nodes: set = set()
    for u, neighbors in graph.items():
        all_nodes.add(u)
        for v, w in neighbors:
            all_nodes.add(v)
            if w < 0:
                raise NegativeEdgeError(
                    f"Negative edge ({u} -> {v}, weight={w}) detected. "
                    f"Dijkstra is incorrect with negative weights — "
                    f"use Bellman-Ford instead."
                )

    if source not in all_nodes:
        raise ValueError(f"Source {source} not in graph.")

    # Step 2: Initialize
    dist: Dict[int, float] = {node: float('inf') for node in all_nodes}
    prev: Dict[int, Optional[int]] = {node: None for node in all_nodes}
    dist[source] = 0

    # Min-heap: (distance, node)
    heap: List[Tuple[float, int]] = [(0, source)]
    finalized: set = set()

    # Step 3: Process
    while heap:
        d, u = heapq.heappop(heap)

        if u in finalized:
            continue
        finalized.add(u)

        for v, weight in graph.get(u, []):
            if v not in finalized and d + weight < dist[v]:
                dist[v] = d + weight
                prev[v] = u
                heapq.heappush(heap, (dist[v], v))

    # Step 4: Reconstruct paths
    paths: Dict[int, List[int]] = {}
    for node in all_nodes:
        if dist[node] == float('inf'):
            paths[node] = []
        else:
            path = []
            current: Optional[int] = node
            while current is not None:
                path.append(current)
                current = prev[current]
            path.reverse()
            paths[node] = path

    return dist, paths


# --- Test Cases ---

# Test 1: Standard graph
graph1: Graph = {
    0: [(1, 4), (2, 1)],
    1: [(3, 1)],
    2: [(1, 2), (3, 5)],
    3: [],
}
dist1, paths1 = dijkstra(graph1, 0)
assert dist1[0] == 0
assert dist1[1] == 3
assert dist1[2] == 1
assert dist1[3] == 4
assert paths1[1] == [0, 2, 1]
assert paths1[3] == [0, 2, 1, 3]
print(f"Test 1 distances: {dist1}")
print(f"Test 1 paths: {paths1}")

# Test 2: Negative edge detection
graph2: Graph = {
    0: [(1, 3), (2, -1)],
    1: [],
    2: [(1, 2)],
}
try:
    dijkstra(graph2, 0)
    assert False, "Should have raised NegativeEdgeError"
except NegativeEdgeError as e:
    print(f"\nTest 2: Correctly caught negative edge: {e}")

# Test 3: Disconnected graph
graph3: Graph = {
    0: [(1, 5)],
    1: [],
    2: [(3, 1)],
    3: [],
}
dist3, paths3 = dijkstra(graph3, 0)
assert dist3[2] == float('inf')
assert paths3[2] == []
print(f"\nTest 3 distances: {dist3}")

# Test 4: Single node
graph4: Graph = {0: []}
dist4, paths4 = dijkstra(graph4, 0)
assert dist4[0] == 0
assert paths4[0] == [0]
print(f"\nTest 4 distances: {dist4}")
```

**Time Complexity:** O((V + E) log V) — each vertex is extracted from the heap once (O(V log V)), and each edge causes at most one heap insertion (O(E log V)).

**Space Complexity:** O(V + E) — for the distance table, heap, and graph storage.

The negative-edge detection pass runs in O(V + E) and ensures correctness. Without it, Dijkstra could silently return wrong results — a dangerous bug in production systems.'''),

    ("thinking/algorithms", r'''Implement topological sort for a directed graph with cycle detection. If the graph has a cycle, return the cycle. Otherwise, return a valid topological ordering.

The solution should handle disconnected components.''', r'''<think>
Topological sort: order vertices of a DAG so that for every directed edge (u, v), u comes before v. Only possible if the graph is a DAG (no cycles).

Two main approaches:
1. Kahn's algorithm (BFS with in-degree tracking)
2. DFS-based with finishing times

For cycle detection with the actual cycle returned, the DFS approach is more natural. In DFS, a cycle exists if we find a back edge — an edge from the current node to a node still on the current DFS stack (colored GRAY).

Let me use the three-color approach:
- WHITE: not visited
- GRAY: currently being processed (on the recursion stack)
- BLACK: completely processed

When I find a GRAY node while exploring, I've found a cycle. To extract the cycle, I need to trace back through the recursion stack from the current node to the gray node.

Wait, extracting the exact cycle from recursion is tricky. Let me think...

Approach: maintain an explicit stack/path. When I find a back edge (u, v) where v is GRAY, the cycle is v -> ... -> u -> v. I can extract it from the current path.

For the topological sort itself: add nodes to the result in reverse post-order (add when a node turns BLACK). Then reverse at the end.

For disconnected components: iterate over all nodes and start DFS from any WHITE node.

Let me think about the data structure. I'll keep:
- `color` dict for each node
- `path` list as the current DFS path
- `order` list for topological ordering

Actually, let me use an iterative DFS approach to avoid recursion limits. Hmm, but iterative DFS with cycle detection and path tracking is more complex. Let me use recursive for clarity, with a note about stack limits.

Edge cases:
- Empty graph
- Single node
- Self-loop (cycle of length 1)
- Multiple disconnected DAGs

Time: O(V + E)
Space: O(V + E)
</think>

## Topological Sort with Cycle Detection and Reporting

```python
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union


class Color(Enum):
    WHITE = 0  # Unvisited
    GRAY = 1   # On current DFS stack
    BLACK = 2  # Fully processed


Graph = Dict[int, List[int]]


def topological_sort_with_cycle_detection(
    graph: Graph,
) -> Union[Tuple[str, List[int]], Tuple[str, List[int]]]:
    """
    Perform topological sort or detect and return a cycle.

    Args:
        graph: Adjacency list mapping node -> [neighbors].

    Returns:
        ("sorted", ordering) if DAG, or ("cycle", cycle_nodes) if cycle found.
    """
    # Collect all nodes (including those only appearing as targets)
    all_nodes: Set[int] = set()
    for u, neighbors in graph.items():
        all_nodes.add(u)
        for v in neighbors:
            all_nodes.add(v)

    # Ensure every node has an adjacency list entry
    for node in all_nodes:
        if node not in graph:
            graph[node] = []

    color: Dict[int, Color] = {node: Color.WHITE for node in all_nodes}
    path: List[int] = []          # Current DFS path
    topo_order: List[int] = []    # Reverse post-order
    cycle: Optional[List[int]] = None

    def dfs(u: int) -> bool:
        """Returns True if a cycle is found."""
        nonlocal cycle

        color[u] = Color.GRAY
        path.append(u)

        for v in graph[u]:
            if color[v] == Color.GRAY:
                # Found a cycle: extract from path
                cycle_start = path.index(v)
                cycle = path[cycle_start:] + [v]
                return True
            if color[v] == Color.WHITE:
                if dfs(v):
                    return True

        path.pop()
        color[u] = Color.BLACK
        topo_order.append(u)
        return False

    # Process all components
    for node in sorted(all_nodes):  # sorted for deterministic output
        if color[node] == Color.WHITE:
            if dfs(node):
                return ("cycle", cycle)

    topo_order.reverse()
    return ("sorted", topo_order)


# --- Test Cases ---

# Test 1: Valid DAG
graph1: Graph = {
    0: [1, 2],
    1: [3],
    2: [3],
    3: [4],
    4: [],
}
status1, result1 = topological_sort_with_cycle_detection(graph1)
assert status1 == "sorted"
# Verify topological property: for every edge u->v, u appears before v
idx = {node: i for i, node in enumerate(result1)}
for u, neighbors in graph1.items():
    for v in neighbors:
        assert idx[u] < idx[v], f"{u} should come before {v}"
print(f"Test 1: {status1} -> {result1}")

# Test 2: Graph with a cycle
graph2: Graph = {
    0: [1],
    1: [2],
    2: [0, 3],
    3: [],
}
status2, result2 = topological_sort_with_cycle_detection(graph2)
assert status2 == "cycle"
# Verify it is actually a cycle
assert result2[0] == result2[-1]  # starts and ends at same node
print(f"Test 2: {status2} -> {result2}")

# Test 3: Self-loop
graph3: Graph = {0: [0]}
status3, result3 = topological_sort_with_cycle_detection(graph3)
assert status3 == "cycle"
assert result3 == [0, 0]
print(f"Test 3: {status3} -> {result3}")

# Test 4: Disconnected DAG
graph4: Graph = {
    0: [1],
    1: [],
    2: [3],
    3: [],
}
status4, result4 = topological_sort_with_cycle_detection(graph4)
assert status4 == "sorted"
assert len(result4) == 4
print(f"Test 4: {status4} -> {result4}")

# Test 5: Empty graph
graph5: Graph = {}
status5, result5 = topological_sort_with_cycle_detection(graph5)
assert status5 == "sorted"
assert result5 == []
print(f"Test 5: {status5} -> {result5}")
```

**Time Complexity:** O(V + E) — each vertex and edge is visited exactly once during DFS.

**Space Complexity:** O(V + E) — for the color map, recursion stack, and path tracking.

The three-color DFS approach (WHITE/GRAY/BLACK) is elegant because GRAY nodes form the current recursion path. A back edge to a GRAY node immediately identifies a cycle, and since we maintain the explicit `path` list, we can extract the exact cycle vertices. For production use with very deep graphs, convert to iterative DFS to avoid Python's recursion limit.'''),

    ("thinking/algorithms", r'''Implement an algorithm to find all bridges (edges whose removal disconnects the graph) and all articulation points (vertices whose removal disconnects the graph) in an undirected graph.

Example:
Edges: (0,1), (1,2), (2,0), (1,3), (3,4), (4,5), (5,3)
Bridges: [(1,3)]
Articulation points: [1, 3]''', r'''<think>
Finding bridges and articulation points — this uses Tarjan's algorithm with DFS and the concept of "discovery time" and "low value."

Key definitions:
- disc[u] = discovery time when node u is first visited in DFS
- low[u] = lowest discovery time reachable from the subtree rooted at u

For bridges:
An edge (u, v) where v is a child of u in DFS tree is a bridge if low[v] > disc[u]. This means v's subtree cannot reach u or anything above u without using edge (u, v).

For articulation points:
- Root of DFS tree: articulation point if it has 2+ children in the DFS tree
- Non-root u: articulation point if it has a child v where low[v] >= disc[u]. This means v's subtree cannot reach above u.

Wait, let me be careful about the difference: for bridges it's low[v] > disc[u] (strictly greater), for articulation points it's low[v] >= disc[u] (can equal, because even if v can reach u, removing u still disconnects v's subtree).

Let me trace the example:
Edges: (0,1), (1,2), (2,0), (1,3), (3,4), (4,5), (5,3)

DFS from 0:
- Visit 0: disc[0]=0, low[0]=0
  - Visit 1 (child): disc[1]=1, low[1]=1
    - Visit 2 (child): disc[2]=2, low[2]=2
      - Back edge to 0: low[2] = min(low[2], disc[0]) = 0
    - low[1] = min(low[1], low[2]) = 0
    - Visit 3 (child): disc[3]=3, low[3]=3
      - Visit 4 (child): disc[4]=4, low[4]=4
        - Visit 5 (child): disc[5]=5, low[5]=5
          - Back edge to 3: low[5] = min(low[5], disc[3]) = 3
        - low[4] = min(low[4], low[5]) = 3
      - low[3] = min(low[3], low[4]) = 3
    - Check bridge: low[3]=3 > disc[1]=1 → edge (1,3) IS a bridge
    - Check articulation: low[3]=3 >= disc[1]=1 → 1 is an articulation point (non-root, has child where low >= disc)
  - low[0] = min(low[0], low[1]) = 0
  - 0 is DFS root with only 1 child (1), so NOT an articulation point

For node 3: it has child 4, low[4]=3 >= disc[3]=3 → 3 IS an articulation point

Wait, but 3 has a back edge from 5. Let me re-examine. Node 3 has children {4} in DFS tree (5 is child of 4, not 3). And there's back edge (5,3). The subtree of 4 has low=3 which equals disc[3]=3, so even though 5 can reach 3 via back edge, removing 3 would disconnect 4 (or... wait, 5 connects to 3, 4 connects to 5 and 3).

Actually, let me reconsider. Edges from 3: to 1, to 4, to 5. In DFS from 3, we visit 4 first (since 1 is parent). From 4, visit 5. From 5, back edge to 3. So child of 3 in DFS tree is just 4.

low[4] = min(disc[4], low[5]) = min(4, 3) = 3. And low[3] = min(disc[3], low[4]) = min(3, 3) = 3. Since low[4] >= disc[3] (3 >= 3), node 3 is an articulation point.

But wait — if we remove node 3, the remaining graph has {0,1,2} connected and {4,5} connected (4-5 edge). So yes, 3 IS an articulation point because {4,5} gets disconnected from {0,1,2}.

Bridges: (1,3) — removing it disconnects {0,1,2} from {3,4,5}. Correct.
Articulation points: {1, 3}. Removing 1 disconnects {0,2} from {3,4,5}. Removing 3 disconnects {4,5} from {0,1,2}. Correct.

Now let me also handle disconnected graphs — we run DFS from each unvisited node.

Time: O(V + E) — single DFS pass
Space: O(V) for the arrays
</think>

## Bridges and Articulation Points via Tarjan's Algorithm

```python
from typing import Dict, List, Set, Tuple


def find_bridges_and_articulation_points(
    n: int, edges: List[Tuple[int, int]]
) -> Tuple[List[Tuple[int, int]], List[int]]:
    """
    Find all bridges and articulation points in an undirected graph.

    Args:
        n: Number of vertices (labeled 0 to n-1).
        edges: List of undirected edges (u, v).

    Returns:
        Tuple of (bridges_list, articulation_points_list).
    """
    # Build adjacency list
    adj: Dict[int, List[int]] = {i: [] for i in range(n)}
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    disc: List[int] = [-1] * n
    low: List[int] = [-1] * n
    parent: List[int] = [-1] * n
    timer: List[int] = [0]  # mutable for closure

    bridges: List[Tuple[int, int]] = []
    art_points: Set[int] = set()

    def dfs(u: int) -> None:
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        child_count = 0

        for v in adj[u]:
            if disc[v] == -1:
                # Tree edge
                child_count += 1
                parent[v] = u
                dfs(v)

                low[u] = min(low[u], low[v])

                # Bridge check: subtree of v cannot reach above u
                if low[v] > disc[u]:
                    bridges.append((min(u, v), max(u, v)))

                # Articulation point check (non-root)
                if parent[u] != -1 and low[v] >= disc[u]:
                    art_points.add(u)

            elif v != parent[u]:
                # Back edge — update low
                low[u] = min(low[u], disc[v])

        # Articulation point check (root with 2+ DFS children)
        if parent[u] == -1 and child_count >= 2:
            art_points.add(u)

    # Handle disconnected components
    for i in range(n):
        if disc[i] == -1:
            dfs(i)

    bridges.sort()
    return bridges, sorted(art_points)


# --- Test Cases ---

# Test 1: Example from problem
edges1 = [(0, 1), (1, 2), (2, 0), (1, 3), (3, 4), (4, 5), (5, 3)]
bridges1, arts1 = find_bridges_and_articulation_points(6, edges1)
assert bridges1 == [(1, 3)]
assert arts1 == [1, 3]
print(f"Test 1: bridges={bridges1}, articulation points={arts1}")

# Test 2: Simple chain (all edges are bridges)
edges2 = [(0, 1), (1, 2), (2, 3)]
bridges2, arts2 = find_bridges_and_articulation_points(4, edges2)
assert bridges2 == [(0, 1), (1, 2), (2, 3)]
assert arts2 == [1, 2]
print(f"Test 2: bridges={bridges2}, articulation points={arts2}")

# Test 3: Complete cycle (no bridges, no articulation points)
edges3 = [(0, 1), (1, 2), (2, 3), (3, 0)]
bridges3, arts3 = find_bridges_and_articulation_points(4, edges3)
assert bridges3 == []
assert arts3 == []
print(f"Test 3: bridges={bridges3}, articulation points={arts3}")

# Test 4: Disconnected components
edges4 = [(0, 1), (2, 3)]
bridges4, arts4 = find_bridges_and_articulation_points(4, edges4)
assert bridges4 == [(0, 1), (2, 3)]
assert arts4 == []  # removing any single node doesn't disconnect its component further
print(f"Test 4: bridges={bridges4}, articulation points={arts4}")

# Test 5: Star graph
edges5 = [(0, 1), (0, 2), (0, 3), (0, 4)]
bridges5, arts5 = find_bridges_and_articulation_points(5, edges5)
assert len(bridges5) == 4  # all edges are bridges
assert arts5 == [0]  # center is the only articulation point
print(f"Test 5: bridges={bridges5}, articulation points={arts5}")
```

**Time Complexity:** O(V + E) — single DFS traversal visiting each vertex and edge once.

**Space Complexity:** O(V + E) — adjacency list plus O(V) for disc/low/parent arrays.

The key insight: `low[u]` captures the earliest reachable ancestor from u's subtree via back edges. When `low[v] > disc[u]`, edge (u,v) is a bridge because v's subtree is completely isolated without it. The articulation point condition differs subtly: `low[v] >= disc[u]` (allowing equality) because even if v can reach u, removing u still disconnects v's subtree from u's ancestors.'''),

    ("thinking/algorithms", r'''Implement Kosaraju's algorithm to find all Strongly Connected Components (SCCs) in a directed graph. Return the SCCs and also the condensation DAG (the graph of SCCs).

Example:
Graph: 0->1, 1->2, 2->0, 1->3, 3->4, 4->5, 5->3
SCCs: {0,1,2}, {3,4,5}
Condensation: SCC0 -> SCC1''', r'''<think>
Strongly Connected Components — vertices where every vertex is reachable from every other vertex in the same component.

Kosaraju's algorithm:
1. Do a DFS on the original graph, pushing vertices onto a stack in order of completion (post-order)
2. Transpose the graph (reverse all edges)
3. Pop vertices from the stack and do DFS on the transposed graph — each DFS from an unvisited vertex gives one SCC

Why does this work? The first DFS orders vertices so that if there's a path from SCC_A to SCC_B, vertices in SCC_A finish after SCC_B. In the transposed graph, the edge from A to B is reversed, so starting from A's vertices, we can't reach B, correctly separating them.

For the condensation DAG: after finding SCCs, I map each vertex to its SCC index. Then for each edge (u, v) in the original graph, if scc[u] != scc[v], add an edge from scc[u] to scc[v] in the condensation.

Let me trace the example:
Graph: 0->1, 1->2, 2->0, 1->3, 3->4, 4->5, 5->3

DFS on original (say starting from 0):
0 -> 1 -> 2 -> back to 0 (done). 2 finishes.
1 -> 3 -> 4 -> 5 -> back to 3 (done). 5 finishes, 4 finishes, 3 finishes.
1 finishes. 0 finishes.
Stack: [2, 5, 4, 3, 1, 0] (order of finishing)

Transpose graph: 1->0, 2->1, 0->2, 3->1, 4->3, 5->4, 3->5

Process stack (pop from top):
Pop 0: DFS on transpose from 0 -> 2 -> 1. SCC = {0, 1, 2}. Mark visited.
Pop 3: DFS from 3 -> 5 -> 4. SCC = {3, 4, 5}. Mark visited.

Condensation: edge 1->3 in original, scc[1]=0, scc[3]=1. So SCC0 -> SCC1.

Time: O(V + E) — two DFS passes + transpose
Space: O(V + E)
</think>

## Kosaraju's Algorithm: SCCs and Condensation DAG

```python
from typing import Dict, List, Set, Tuple


Graph = Dict[int, List[int]]


def kosaraju_scc(
    graph: Graph,
) -> Tuple[List[List[int]], Graph]:
    """
    Find all Strongly Connected Components using Kosaraju's algorithm.
    Also build the condensation DAG.

    Args:
        graph: Directed graph as adjacency list.

    Returns:
        Tuple of (list_of_SCCs, condensation_DAG).
        Each SCC is a sorted list of vertices.
        Condensation maps SCC index -> [SCC neighbor indices].
    """
    # Collect all nodes
    all_nodes: Set[int] = set()
    for u in graph:
        all_nodes.add(u)
        for v in graph[u]:
            all_nodes.add(v)

    for node in all_nodes:
        if node not in graph:
            graph[node] = []

    # Step 1: DFS on original graph, record finish order
    visited: Set[int] = set()
    finish_stack: List[int] = []

    def dfs1(u: int) -> None:
        visited.add(u)
        for v in graph[u]:
            if v not in visited:
                dfs1(v)
        finish_stack.append(u)

    for node in sorted(all_nodes):
        if node not in visited:
            dfs1(node)

    # Step 2: Build transposed graph
    transposed: Graph = {node: [] for node in all_nodes}
    for u in graph:
        for v in graph[u]:
            transposed[v].append(u)

    # Step 3: DFS on transposed graph in reverse finish order
    visited.clear()
    sccs: List[List[int]] = []

    def dfs2(u: int, component: List[int]) -> None:
        visited.add(u)
        component.append(u)
        for v in transposed[u]:
            if v not in visited:
                dfs2(v, component)

    while finish_stack:
        node = finish_stack.pop()
        if node not in visited:
            component: List[int] = []
            dfs2(node, component)
            sccs.append(sorted(component))

    # Step 4: Build condensation DAG
    node_to_scc: Dict[int, int] = {}
    for idx, scc in enumerate(sccs):
        for node in scc:
            node_to_scc[node] = idx

    condensation: Graph = {i: [] for i in range(len(sccs))}
    seen_edges: Set[Tuple[int, int]] = set()

    for u in graph:
        for v in graph[u]:
            scc_u, scc_v = node_to_scc[u], node_to_scc[v]
            if scc_u != scc_v and (scc_u, scc_v) not in seen_edges:
                condensation[scc_u].append(scc_v)
                seen_edges.add((scc_u, scc_v))

    return sccs, condensation


# --- Test Cases ---

# Test 1: Two SCCs
graph1: Graph = {
    0: [1],
    1: [2, 3],
    2: [0],
    3: [4],
    4: [5],
    5: [3],
}
sccs1, cond1 = kosaraju_scc(graph1)
assert len(sccs1) == 2
scc_sets1 = [set(scc) for scc in sccs1]
assert {0, 1, 2} in scc_sets1
assert {3, 4, 5} in scc_sets1
print(f"Test 1 SCCs: {sccs1}")
print(f"Test 1 condensation: {cond1}")

# Test 2: Each node is its own SCC (DAG)
graph2: Graph = {0: [1], 1: [2], 2: []}
sccs2, cond2 = kosaraju_scc(graph2)
assert len(sccs2) == 3
print(f"\nTest 2 SCCs: {sccs2}")
print(f"Test 2 condensation: {cond2}")

# Test 3: Single large SCC
graph3: Graph = {0: [1], 1: [2], 2: [3], 3: [0]}
sccs3, cond3 = kosaraju_scc(graph3)
assert len(sccs3) == 1
assert set(sccs3[0]) == {0, 1, 2, 3}
print(f"\nTest 3 SCCs: {sccs3}")

# Test 4: Empty graph
graph4: Graph = {0: [], 1: [], 2: []}
sccs4, cond4 = kosaraju_scc(graph4)
assert len(sccs4) == 3
print(f"\nTest 4 SCCs: {sccs4}")

# Test 5: Self-loop
graph5: Graph = {0: [0, 1], 1: []}
sccs5, cond5 = kosaraju_scc(graph5)
scc_sets5 = [set(s) for s in sccs5]
assert {0} in scc_sets5
assert {1} in scc_sets5
print(f"\nTest 5 SCCs: {sccs5}")
```

**Time Complexity:** O(V + E) — two DFS passes (each O(V + E)), plus O(V + E) for transposing the graph and building the condensation.

**Space Complexity:** O(V + E) — for the transposed graph and auxiliary data structures.

Kosaraju's algorithm leverages a beautiful insight: the first DFS ensures that source SCCs (those with no incoming cross-SCC edges) have the latest finish times. Processing in reverse finish order on the transposed graph isolates each SCC because cross-SCC edges are now reversed, preventing "leakage" between components. The condensation DAG is always a DAG by definition and is useful for problems like 2-SAT and reachability queries.'''),

    ("thinking/algorithms", r'''Implement an algorithm to check if an undirected graph is bipartite. If it is, return the two-coloring (partition). If not, return an odd-length cycle as proof.

Example:
Bipartite: edges (0,1), (1,2), (2,3), (3,0) -> Yes, partition: {0,2} and {1,3}
Not bipartite: edges (0,1), (1,2), (2,0) -> No, odd cycle: [0,1,2,0]''', r'''<think>
A graph is bipartite if and only if it contains no odd-length cycles. Equivalently, it's bipartite if and only if it's 2-colorable.

The standard approach is BFS (or DFS) coloring:
1. Pick an unvisited vertex, color it 0
2. For each neighbor, if uncolored, color it with the opposite color
3. If a neighbor already has the same color, the graph is not bipartite

For finding the odd cycle when it's not bipartite: when we detect a conflict (two adjacent nodes with the same color), we need to find the odd cycle. Using BFS, both nodes u and v have the same color, meaning they're at the same distance parity from the root. The odd cycle is: path from LCA(u,v) to u + edge (u,v) + path from v to LCA(u,v).

Actually, a simpler approach with BFS: maintain parent pointers. When we find the conflict edge (u,v) with same colors, trace back from both u and v to their common ancestor to form the cycle.

Let me think more carefully. With BFS from root:
- parent[u] tracks the parent in BFS tree
- When we find edge (u,v) where color[u] == color[v], we trace both paths back to their common ancestor

To find common ancestor: trace both paths simultaneously, or trace one path and check.

Actually, a simpler method: trace path from u back to root and from v back to root. Find where they diverge. The cycle is the path from the LCA down to u, then edge u-v, then path from v back to LCA.

Wait, let me think about this differently. Since BFS gives levels, and u and v are at the same level (same color means same parity of distance from root), I trace both back until they meet.

Let me implement this step by step:
1. BFS with coloring
2. On conflict edge (u, v): build path_u from u to root, build path_v from v to root
3. Find LCA by popping common suffix
4. Construct cycle: path from LCA to u + edge (u,v) + reverse path from LCA to v

Edge cases:
- Disconnected graph: check each component
- Single node: trivially bipartite
- Self-loop: odd cycle of length 1? Actually a self-loop means node connects to itself, so color[u] == color[u], always a conflict. But a self-loop isn't really an "odd cycle" in the traditional sense. I'll treat it as a special case.

Time: O(V + E) — single BFS
Space: O(V)
</think>

## Bipartite Check with Two-Coloring or Odd Cycle Extraction

```python
from collections import deque
from typing import Dict, List, Optional, Set, Tuple, Union


def check_bipartite(
    n: int, edges: List[Tuple[int, int]]
) -> Union[Tuple[str, List[Set[int]]], Tuple[str, List[int]]]:
    """
    Check if an undirected graph is bipartite.

    Args:
        n: Number of vertices (0 to n-1).
        edges: List of undirected edges.

    Returns:
        ("bipartite", [set_A, set_B]) if bipartite, or
        ("odd_cycle", cycle_vertices) if not.
    """
    adj: Dict[int, List[int]] = {i: [] for i in range(n)}
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    color: List[int] = [-1] * n  # -1 = uncolored, 0 or 1
    parent: List[int] = [-1] * n

    def find_odd_cycle(u: int, v: int) -> List[int]:
        """Given conflict edge (u, v) with same color, extract odd cycle."""
        # Trace paths from u and v back to root
        path_u: List[int] = []
        path_v: List[int] = []

        a, b = u, v
        visited_a: Set[int] = set()

        # Build path from u to root
        curr = u
        while curr != -1:
            path_u.append(curr)
            curr = parent[curr]

        # Build path from v to root
        curr = v
        while curr != -1:
            path_v.append(curr)
            curr = parent[curr]

        # Find LCA: both paths end at root, find where they diverge from the end
        set_u = set(path_u)
        # First node in path_v that is also in path_u is the LCA
        lca = -1
        for node in path_v:
            if node in set_u:
                lca = node
                break

        # Build cycle: u -> ... -> lca -> ... -> v -> u
        cycle: List[int] = []
        for node in path_u:
            cycle.append(node)
            if node == lca:
                break

        tail: List[int] = []
        for node in path_v:
            if node == lca:
                break
            tail.append(node)
        tail.reverse()
        cycle.extend(tail)
        cycle.append(u)  # close the cycle

        return cycle

    for start in range(n):
        if color[start] != -1:
            continue

        color[start] = 0
        parent[start] = -1
        queue: deque = deque([start])

        while queue:
            u = queue.popleft()
            for v in adj[u]:
                if color[v] == -1:
                    color[v] = 1 - color[u]
                    parent[v] = u
                    queue.append(v)
                elif color[v] == color[u]:
                    # Not bipartite — find odd cycle
                    cycle = find_odd_cycle(u, v)
                    return ("odd_cycle", cycle)

    # Bipartite — build partition
    set_a: Set[int] = {i for i in range(n) if color[i] == 0}
    set_b: Set[int] = {i for i in range(n) if color[i] == 1}

    return ("bipartite", [set_a, set_b])


# --- Test Cases ---

# Test 1: Bipartite (even cycle)
status1, result1 = check_bipartite(4, [(0, 1), (1, 2), (2, 3), (3, 0)])
assert status1 == "bipartite"
set_a, set_b = result1
assert len(set_a & set_b) == 0  # no overlap
assert set_a | set_b == {0, 1, 2, 3}
print(f"Test 1: {status1}, A={set_a}, B={set_b}")

# Test 2: Not bipartite (triangle)
status2, result2 = check_bipartite(3, [(0, 1), (1, 2), (2, 0)])
assert status2 == "odd_cycle"
assert result2[0] == result2[-1]  # cycle is closed
assert len(result2) % 2 == 0  # odd cycle has even length when closed
print(f"Test 2: {status2}, cycle={result2}")

# Test 3: Disconnected bipartite
status3, result3 = check_bipartite(4, [(0, 1), (2, 3)])
assert status3 == "bipartite"
print(f"Test 3: {status3}, partitions={result3}")

# Test 4: Single node
status4, result4 = check_bipartite(1, [])
assert status4 == "bipartite"
print(f"Test 4: {status4}")

# Test 5: Complete graph K4 (not bipartite)
edges5 = [(i, j) for i in range(4) for j in range(i + 1, 4)]
status5, result5 = check_bipartite(4, edges5)
assert status5 == "odd_cycle"
print(f"Test 5: {status5}, cycle={result5}")
```

**Time Complexity:** O(V + E) — BFS visits each vertex and edge once. Cycle extraction is O(V) in the worst case.

**Space Complexity:** O(V + E) — for the adjacency list, color array, parent array, and BFS queue.

The algorithm exploits the fundamental theorem: a graph is bipartite if and only if it contains no odd cycles. BFS naturally assigns "levels" to vertices, and vertices at the same level get the same color. When two same-colored vertices are adjacent, we've found an odd cycle, which we reconstruct via parent pointers and LCA finding. This provides a constructive proof of non-bipartiteness.'''),
]
