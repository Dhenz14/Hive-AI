PAIRS = [
    ("thinking/algorithms", r'''Implement Dijkstra's shortest path algorithm that also detects if negative-weight edges are present in the graph (and refuses to run, explaining why). Return the shortest distances and the actual paths from a source to all vertices.

Example:
Graph: {0: [(1, 4), (2, 1)], 1: [(3, 1)], 2: [(1, 2), (3, 5)], 3: []}
Source: 0
Output: distances = {0: 0, 1: 3, 2: 1, 3: 4}, paths = {0: [0], 1: [0,2,1], 2: [0,2], 3: [0,2,1,3]}''', r'''<think>
Dijkstra's with negative edge detection and path reconstruction. Let me think through this.

First thought: just run Dijkstra normally. But the problem specifically asks to detect negative edges. Why? Because Dijkstra assumes that once you pop a node from the priority queue, you've found its shortest distance. With negative edges, a later path through a negative edge could actually be shorter, but Dijkstra would have already "finalized" the node. So the results would be silently wrong -- which is worse than crashing.

So step 1: scan all edges, reject if any are negative. Then proceed with standard Dijkstra.

For the algorithm itself, I need a min-heap. Each entry is (distance, node). I also need a "finalized" set -- once I pop a node, I don't process it again. For each neighbor of the popped node, if the new distance is better, update and push.

Hmm, one design question: should I use a decrease-key operation on the heap? Python's heapq doesn't support decrease-key. The standard workaround is lazy deletion -- just push a new entry and skip stale ones when popping. That's what the "finalized" set handles. A node might appear multiple times in the heap with different distances, but only the first pop (smallest distance) matters.

For path reconstruction, I'll keep prev[v] = the node we came from when we last improved dist[v]. Then walk backwards from any target to source.

What about nodes that only appear as edge targets but not as keys in the adjacency list? I should collect all nodes from both keys and values. Otherwise I'd miss nodes that have no outgoing edges.

Also, what if the source isn't in the graph at all? Should raise an error.

For disconnected nodes, their distance stays at infinity and their path is empty. That's a natural fallout of the algorithm.

Time: O((V + E) log V) with binary heap. Space: O(V + E).
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
Topological sort with cycle detection -- and if there IS a cycle, return it.

Two classic approaches: Kahn's algorithm (BFS, track in-degrees) or DFS-based. For finding the actual cycle, DFS is more natural because I can track the recursion path and extract the cycle when I find a back edge.

I'll use the three-color scheme: WHITE (unvisited), GRAY (in progress, on the current recursion stack), BLACK (done). A back edge to a GRAY node means a cycle.

But here's the tricky part: when I detect the back edge (u -> v) where v is GRAY, how do I extract the actual cycle? I can't just look at the recursion call stack in Python easily. I think I need to maintain an explicit `path` list. Every time I enter a node, append it to path. When I finish a node (turn it BLACK), pop it. Then when I find a back edge to v, the cycle is path[path.index(v):] + [v].

Wait, is path.index(v) correct? The path list contains the current DFS path from the root to the current node. If v is GRAY, it must be somewhere on this path. So yes, slicing from v's position to the end gives the cycle, and appending v closes it.

For the topological ordering (when there's no cycle): I append nodes in post-order (when they turn BLACK), then reverse at the end. That gives a valid topological order because a node finishes only after all its descendants finish.

For disconnected components, I iterate over all nodes and start DFS from any WHITE one.

Should I use iterative DFS to avoid Python's recursion limit? For correctness it doesn't matter, but for large graphs the recursive approach could hit the stack limit. I'll go with recursive for clarity since the problem doesn't mention size constraints. Could always convert later with an explicit stack if needed, though managing the three colors and path tracking iteratively is messier.

Self-loops are a fun edge case -- a node with an edge to itself. When I process the edge, the node is GRAY, so it's immediately detected as a cycle: [v, v].

Time: O(V + E). Space: O(V + E).
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
Bridges and articulation points -- Tarjan's algorithm with discovery times and low values.

The idea: during DFS, track disc[u] (when u was first visited) and low[u] (the minimum discovery time reachable from u's subtree, including back edges). A back edge lets a subtree "reach" an ancestor, so if low[v] is high, it means v's subtree is isolated.

For bridges: edge (u,v) is a bridge if low[v] > disc[u]. Meaning v's subtree has no back edge to u or above -- removing (u,v) disconnects it.

For articulation points: non-root u is an articulation point if some child v has low[v] >= disc[u]. Root is an articulation point if it has 2+ DFS children.

Hmm, I keep getting confused about the > vs >= distinction. Let me think about why they differ. For bridges, if low[v] == disc[u], it means v's subtree can reach u (via some back edge), so removing edge (u,v) doesn't disconnect anything -- there's still a path through the back edge. So we need strict >. For articulation points, even if v's subtree can reach u (low[v] == disc[u]), removing u itself still disconnects v's subtree from everything above u. So >= suffices.

Let me trace the example to make sure I have this right.
Edges: (0,1), (1,2), (2,0), (1,3), (3,4), (4,5), (5,3)

DFS from 0:
- 0: disc=0, low=0
  - 1: disc=1, low=1
    - 2: disc=2. Has edge to 0 (back edge since 0 is already visited and isn't parent). low[2] = min(2, disc[0]) = 0.
    - Back at 1: low[1] = min(1, low[2]) = 0
    - 3: disc=3, low=3
      - 4: disc=4, low=4
        - 5: disc=5. Has edge to 3 (back edge). low[5] = min(5, disc[3]) = 3
        - Back at 4: low[4] = min(4, low[5]) = 3
      - Back at 3: low[3] = min(3, low[4]) = 3
    - Bridge check for edge (1,3): low[3]=3 > disc[1]=1? Yes -- bridge!
    - Articulation check for 1: low[3]=3 >= disc[1]=1? Yes -- 1 is an articulation point.
  - Back at 0: low[0] = min(0, low[1]) = 0. Root with 1 DFS child, so not an articulation point.

For node 3: child 4 has low[4]=3 >= disc[3]=3. So 3 is an articulation point. Let me verify intuitively: removing 3 leaves {0,1,2} and {4,5} disconnected. Yes, correct. And the cycle 3-4-5-3 means 4 and 5 can reach each other, but they can't reach {0,1,2} without going through 3.

What about node 4? Its child 5 has low[5]=3 < disc[4]=4, so low[5] < disc[4], which means 4 is NOT an articulation point. That's right -- removing 4 still leaves 5 connected to 3 via the back edge.

Need to handle disconnected graphs by running DFS from each unvisited node.

One implementation detail: when checking back edges, I need to avoid treating the parent edge as a back edge. For undirected graphs, the edge to parent is in the adjacency list, but it's a tree edge, not a back edge. I track parent[v] and skip it.

Time: O(V + E). Space: O(V).
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
Strongly connected components. I know Tarjan's and Kosaraju's algorithms for this. The problem asks for Kosaraju's specifically, plus the condensation DAG.

Kosaraju's has three steps:
1. DFS on original graph, record nodes in finishing order (push to stack when done)
2. Transpose the graph (reverse all edges)
3. Process nodes from the stack (most recently finished first), running DFS on the transposed graph -- each DFS gives one SCC

Why does this work? I always have to re-derive this in my head. The key insight is about finishing times. If SCC A has an edge to SCC B in the condensation, then in the first DFS, some node in A finishes after all nodes in B. So when we process in reverse finish order, we start with A. In the transposed graph, the edge from A to B is reversed (B -> A), so starting from A we can't accidentally reach B. We only reach other nodes in A (because within an SCC, all edges are bidirectionally reachable, so transposing doesn't break intra-SCC connectivity).

Wait, actually, do I have that direction right? Let me think again with the example.

Graph: 0->1, 1->2, 2->0, 1->3, 3->4, 4->5, 5->3

First DFS from 0: 0->1->2->back to 0. Finish 2. Back to 1: 1->3->4->5->back to 3. Finish 5, finish 4, finish 3. Finish 1. Finish 0.
Stack (bottom to top): [2, 5, 4, 3, 1, 0]

Transpose: 1->0, 2->1, 0->2, 3->1, 4->3, 5->4, 3->5

Process from top of stack: pop 0. DFS on transpose from 0: 0->2 (because 0->2 in transpose), 2->1 (because 2->1 in transpose), 1 has edge to 0 (already visited). SCC = {0, 1, 2}.
Next unvisited on stack: pop 3 (1 already visited). DFS from 3: 3->5->4->3 (already visited). SCC = {3, 4, 5}.

That's correct. The condensation DAG: look at original edges crossing SCCs. Edge 1->3, where 1 is in SCC0 and 3 is in SCC1. So SCC0 -> SCC1.

For building the condensation, I map each node to its SCC index, then scan all original edges and add cross-SCC edges (deduplicating).

One thing to be careful about: nodes that appear only as targets in the graph (no outgoing edges listed). I need to make sure they're included. I'll collect all nodes from both keys and values of the adjacency list.

Time: O(V + E) for two DFS passes plus transpose. Space: O(V + E).
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
Bipartite check -- 2-color the graph via BFS, and if that fails, return an odd cycle as proof.

The basic BFS coloring is straightforward: start at any unvisited node, color it 0, color all neighbors 1, their neighbors 0, etc. If I ever find an edge where both endpoints have the same color, the graph isn't bipartite.

The harder part is extracting the actual odd cycle when it fails. When I find the conflict edge (u, v) where both have the same color, I know there's an odd cycle going through u and v. But what cycle exactly?

My first idea: since BFS assigns levels, u and v are at the same level (same color = same parity of distance from root). So the odd cycle is: path from their lowest common ancestor (LCA) down to u, then edge u-v, then path from v back to LCA. That's an odd number of edges because the two paths from LCA have equal length (same level) plus the one conflict edge.

But how do I find the LCA? I have parent pointers from BFS. I can trace path_u from u to root and path_v from v to root, then find the first node they share. That's O(V) worst case, which is fine.

Actually wait, I don't even need a proper LCA algorithm. I can just trace both paths to root, put path_u's nodes in a set, then walk path_v until I hit something in that set. That gives me the LCA. Then the cycle is: u -> ... -> LCA -> ... -> v -> u.

Hmm, let me be more precise about constructing the cycle. path_u = [u, parent[u], parent[parent[u]], ..., LCA, ..., root]. I only want the portion from u to LCA. Similarly for v. So:
- cycle = path_u[:path_u.index(LCA)+1] (u to LCA)
- tail = path_v[:path_v.index(LCA)] reversed (LCA to v, but without LCA itself since it's already in cycle)
- Then close with u

Let me make sure this handles disconnected graphs. I just run BFS from each unvisited component. If any component isn't bipartite, I return the odd cycle. If all pass, it's bipartite.

Self-loops: a node with edge to itself would show color[u] == color[u], which is always a conflict. The "cycle" would be [u, u], which is length 1. Technically odd. A bit degenerate but correct.

Time: O(V + E). Space: O(V).
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
