PAIRS = [
    ("thinking/algorithms", r'''Implement Tarjan's algorithm for finding Strongly Connected Components (SCCs) in a directed graph. Explain how it works and demonstrate on an example graph.''', r'''<think>
Tarjan's algorithm finds all strongly connected components in a directed graph in a single DFS pass. An SCC is a maximal set of vertices where every vertex is reachable from every other vertex.

The algorithm uses three key concepts:
1. Discovery time (disc): when each node is first visited during DFS
2. Low-link value (low): the smallest discovery time reachable from the subtree rooted at this node
3. A stack to track the current path/component

How it works:
- DFS from each unvisited node
- On visiting node u, set disc[u] = low[u] = timer++, push u onto stack
- For each neighbor v of u:
  - If v not visited: recurse, then low[u] = min(low[u], low[v])
  - If v is on the stack: low[u] = min(low[u], disc[v])
- After processing all neighbors, if low[u] == disc[u], then u is the root of an SCC. Pop everything from the stack down to and including u -- that is one SCC.

The key insight: low[u] == disc[u] means no node in u's subtree can reach a node discovered before u. So u and all nodes above it on the stack form a complete SCC.

Why we only consider nodes on the stack for the low-link update: nodes already popped belong to a different (already identified) SCC. They should not affect the current component.

Time: O(V + E) -- single DFS traversal.
Space: O(V) for the stack, disc, low arrays.
</think>

**Tarjan's Algorithm for Strongly Connected Components**

```python
def tarjan_scc(graph):
    """
    Find all strongly connected components using Tarjan's algorithm.

    Args:
        graph: adjacency list {node: [neighbors]}
    Returns:
        list of SCCs, each SCC is a list of nodes
    """
    disc = {}
    low = {}
    on_stack = set()
    stack = []
    sccs = []
    timer = [0]

    def dfs(u):
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        stack.append(u)
        on_stack.add(u)

        for v in graph.get(u, []):
            if v not in disc:
                dfs(v)
                low[u] = min(low[u], low[v])
            elif v in on_stack:
                low[u] = min(low[u], disc[v])

        # u is root of an SCC
        if low[u] == disc[u]:
            scc = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == u:
                    break
            sccs.append(scc)

    for node in graph:
        if node not in disc:
            dfs(node)

    return sccs


# Example graph
graph = {
    0: [1],
    1: [2],
    2: [0, 3],
    3: [4],
    4: [5, 7],
    5: [6],
    6: [4],
    7: [7],
}

sccs = tarjan_scc(graph)
print("Strongly Connected Components:")
for i, scc in enumerate(sccs):
    print(f"  SCC {i}: {sorted(scc)}")

# Build condensation graph (DAG of SCCs)
node_to_scc = {}
for i, scc in enumerate(sccs):
    for node in scc:
        node_to_scc[node] = i

condensation = {i: set() for i in range(len(sccs))}
for u in graph:
    for v in graph[u]:
        su, sv = node_to_scc[u], node_to_scc[v]
        if su != sv:
            condensation[su].add(sv)

print("\nCondensation DAG (SCC index -> SCC index):")
for src, dsts in condensation.items():
    if dsts:
        print(f"  SCC {src} -> {dsts}")
```

**Key Properties:**
- Each node belongs to exactly one SCC
- The condensation graph (DAG of SCCs) has no cycles
- Tarjan's finds SCCs in reverse topological order

**Difference from Kosaraju's:**
- Tarjan's: single DFS pass, uses stack + low-link values
- Kosaraju's: two DFS passes (one on original, one on transposed graph)
- Both are O(V + E), but Tarjan's is often preferred for single-pass elegance

**Complexity:**
- Time: O(V + E) -- each vertex and edge visited once
- Space: O(V) for auxiliary arrays and stack'''),

    ("thinking/algorithms", r'''Implement an algorithm to find all articulation points (cut vertices) in an undirected graph. An articulation point is a vertex whose removal disconnects the graph.''', r'''<think>
Finding articulation points uses a modified DFS similar to Tarjan's SCC algorithm, but for undirected graphs.

A vertex u is an articulation point if:
1. u is the root of DFS tree AND has two or more children in the DFS tree, OR
2. u is not root AND has a child v such that no vertex in the subtree rooted at v has a back edge to an ancestor of u (i.e., low[v] >= disc[u])

The algorithm:
1. Run DFS, tracking discovery time disc[u] and low-link value low[u]
2. low[u] = min of:
   - disc[u] itself
   - disc[w] for any back edge (u, w)
   - low[v] for any DFS tree child v
3. For non-root u: if any child v has low[v] >= disc[u], then u is an articulation point (removing u disconnects v's subtree)
4. For root: if it has >= 2 DFS tree children, it is an articulation point

Why low[v] >= disc[u] matters: It means the subtree rooted at v cannot reach any ancestor of u through back edges. So removing u disconnects v's subtree from the rest of the graph.

We must be careful with the parent tracking in undirected graphs to avoid treating the tree edge back to the parent as a back edge. We track the parent of each node in the DFS tree.

Edge cases:
- Graph is already disconnected
- Single node
- Tree (every internal node is an articulation point)
- Complete graph (no articulation points)

Time: O(V + E), Space: O(V).
</think>

**Articulation Points (Cut Vertices) -- DFS Approach**

```python
def find_articulation_points(graph, n):
    """
    Find all articulation points in an undirected graph.

    Args:
        graph: adjacency list {node: [neighbors]}
        n: number of vertices (0 to n-1)
    Returns:
        set of articulation point vertices
    """
    disc = [-1] * n
    low = [0] * n
    parent = [-1] * n
    ap = set()
    timer = [0]

    def dfs(u):
        children = 0
        disc[u] = low[u] = timer[0]
        timer[0] += 1

        for v in graph.get(u, []):
            if disc[v] == -1:
                # Tree edge
                children += 1
                parent[v] = u
                dfs(v)
                low[u] = min(low[u], low[v])

                # Case 1: u is root with 2+ children
                if parent[u] == -1 and children > 1:
                    ap.add(u)

                # Case 2: u is not root and subtree of v
                # cannot reach above u
                if parent[u] != -1 and low[v] >= disc[u]:
                    ap.add(u)

            elif v != parent[u]:
                # Back edge (not to parent)
                low[u] = min(low[u], disc[v])

    for i in range(n):
        if disc[i] == -1:
            dfs(i)

    return ap


def find_bridges(graph, n):
    """Also find bridges (cut edges) -- similar algorithm."""
    disc = [-1] * n
    low = [0] * n
    parent = [-1] * n
    bridges = []
    timer = [0]

    def dfs(u):
        disc[u] = low[u] = timer[0]
        timer[0] += 1

        for v in graph.get(u, []):
            if disc[v] == -1:
                parent[v] = u
                dfs(v)
                low[u] = min(low[u], low[v])
                # Bridge condition: low[v] > disc[u]
                # (strict inequality, unlike AP)
                if low[v] > disc[u]:
                    bridges.append((u, v))
            elif v != parent[u]:
                low[u] = min(low[u], disc[v])

    for i in range(n):
        if disc[i] == -1:
            dfs(i)

    return bridges


# Example
n = 7
edges = [(0,1), (1,2), (2,0), (1,3), (3,4), (4,5), (5,3), (4,6)]
graph = {i: [] for i in range(n)}
for u, v in edges:
    graph[u].append(v)
    graph[v].append(u)

aps = find_articulation_points(graph, n)
brs = find_bridges(graph, n)

print(f"Graph edges: {edges}")
print(f"Articulation points: {sorted(aps)}")
print(f"Bridges: {brs}")

# Verify by removing each AP and checking connectivity
from collections import deque

def is_connected(g, n, removed):
    visited = set()
    start = -1
    for i in range(n):
        if i != removed:
            start = i
            break
    if start == -1:
        return True
    q = deque([start])
    visited.add(start)
    while q:
        u = q.popleft()
        for v in g.get(u, []):
            if v != removed and v not in visited:
                visited.add(v)
                q.append(v)
    return len(visited) == n - 1

print("\nVerification:")
for v in range(n):
    conn = is_connected(graph, n, v)
    is_ap = v in aps
    print(f"  Remove {v}: connected={conn}, is_AP={is_ap}")
```

**Bridge vs Articulation Point:**
- Bridge: edge whose removal disconnects graph (low[v] > disc[u], strict)
- Articulation Point: vertex whose removal disconnects graph (low[v] >= disc[u])

**Complexity:**
- Time: O(V + E) -- single DFS
- Space: O(V) for arrays'''),

    ("thinking/algorithms", r'''Determine if an Euler path or Euler circuit exists in a graph, and if so, find one. An Euler path visits every edge exactly once. An Euler circuit is an Euler path that starts and ends at the same vertex.''', r'''<think>
Euler path/circuit problems have elegant necessary and sufficient conditions:

For undirected graphs:
- Euler circuit exists iff every vertex has even degree and the graph is connected (considering only vertices with degree > 0)
- Euler path exists iff exactly 0 or 2 vertices have odd degree and the graph is connected

For directed graphs:
- Euler circuit: every vertex has in_degree == out_degree, and the graph is strongly connected
- Euler path: at most one vertex has out_degree - in_degree = 1 (start), at most one has in_degree - out_degree = 1 (end), all others balanced, and underlying graph is connected

Algorithm to find the path: Hierholzer's algorithm
1. Start from a valid starting vertex
2. Follow edges, removing them as you go, until you get stuck
3. When stuck, backtrack along the path to find a vertex with remaining edges
4. Continue from there, inserting the new sub-circuit into the main path
5. Repeat until all edges are used

The elegant recursive version:
- DFS from start, removing edges as you traverse them
- After all neighbors are exhausted, push the current vertex to the front of the result
- This naturally handles the backtracking

For directed graphs, we remove edges from the adjacency list as we use them. For undirected, we need to remove the edge from both directions.

Edge cases:
- Graph with no edges (trivial Euler circuit at any vertex)
- Multigraph (multiple edges between same vertices)
- Self-loops
- Disconnected graph with isolated vertices

Time: O(E) for Hierholzer's algorithm.
Space: O(E) for the path + O(V) for the stack.
</think>

**Euler Path and Circuit -- Hierholzer's Algorithm**

```python
from collections import defaultdict, deque


def find_euler_path_undirected(edges, n):
    """
    Find Euler path/circuit in an undirected graph.

    Args:
        edges: list of (u, v) edges
        n: number of vertices
    Returns:
        (path, is_circuit) or (None, False) if no Euler path exists
    """
    graph = defaultdict(list)
    degree = [0] * n

    # Build adjacency with edge indices for removal tracking
    edge_used = [False] * len(edges)
    for idx, (u, v) in enumerate(edges):
        graph[u].append((v, idx))
        graph[v].append((u, idx))
        degree[u] += 1
        degree[v] += 1

    # Check existence
    odd_vertices = [v for v in range(n) if degree[v] % 2 == 1]

    if len(odd_vertices) not in (0, 2):
        return None, False

    # Choose starting vertex
    if len(odd_vertices) == 2:
        start = odd_vertices[0]
        is_circuit = False
    else:
        # Find any vertex with edges
        start = 0
        for v in range(n):
            if degree[v] > 0:
                start = v
                break
        is_circuit = True

    # Hierholzer's algorithm
    stack = [start]
    path = []
    # Track current position in adjacency list for each vertex
    ptr = defaultdict(int)

    while stack:
        v = stack[-1]
        found = False
        while ptr[v] < len(graph[v]):
            neighbor, edge_idx = graph[v][ptr[v]]
            ptr[v] += 1
            if not edge_used[edge_idx]:
                edge_used[edge_idx] = True
                stack.append(neighbor)
                found = True
                break
        if not found:
            path.append(stack.pop())

    path.reverse()

    # Verify all edges used
    if len(path) != len(edges) + 1:
        return None, False

    return path, is_circuit


def find_euler_path_directed(graph_dict, n):
    """
    Find Euler path/circuit in a directed graph.

    Args:
        graph_dict: {u: [v1, v2, ...]} adjacency list
        n: number of vertices
    Returns:
        path as list of vertices, or None
    """
    graph = defaultdict(deque)
    in_deg = [0] * n
    out_deg = [0] * n

    for u, neighbors in graph_dict.items():
        for v in neighbors:
            graph[u].append(v)
            out_deg[u] += 1
            in_deg[v] += 1

    # Check conditions
    start_nodes = []
    end_nodes = []
    for v in range(n):
        diff = out_deg[v] - in_deg[v]
        if diff == 1:
            start_nodes.append(v)
        elif diff == -1:
            end_nodes.append(v)
        elif diff != 0:
            return None

    if len(start_nodes) == 0 and len(end_nodes) == 0:
        start = 0
        for v in range(n):
            if out_deg[v] > 0:
                start = v
                break
    elif len(start_nodes) == 1 and len(end_nodes) == 1:
        start = start_nodes[0]
    else:
        return None

    # Hierholzer's
    stack = [start]
    path = []

    while stack:
        v = stack[-1]
        if graph[v]:
            stack.append(graph[v].popleft())
        else:
            path.append(stack.pop())

    path.reverse()
    total_edges = sum(out_deg)
    if len(path) != total_edges + 1:
        return None
    return path


# Example: Undirected
edges = [(0,1), (1,2), (2,3), (3,0), (0,2)]
path, is_circuit = find_euler_path_undirected(edges, 4)
print(f"Undirected edges: {edges}")
print(f"Euler path: {path}")
print(f"Is circuit: {is_circuit}")

# Example: Directed
dgraph = {0: [1], 1: [2], 2: [0, 3], 3: [1]}
dpath = find_euler_path_directed(dgraph, 4)
print(f"\nDirected graph: {dgraph}")
print(f"Euler path: {dpath}")
```

**Existence Conditions Summary:**
| Graph Type | Circuit | Path |
|---|---|---|
| Undirected | All even degree | 0 or 2 odd degree |
| Directed | in=out for all | 1 start (out=in+1), 1 end (in=out+1) |

**Complexity:**
- Time: O(E) -- each edge traversed exactly once
- Space: O(V + E) for graph and path storage'''),

    ("thinking/algorithms", r'''Implement the Hopcroft-Karp algorithm for maximum bipartite matching. Given a bipartite graph, find the largest set of edges such that no two edges share an endpoint.''', r'''<think>
Maximum bipartite matching finds the largest set of edges where no two share a vertex. Hopcroft-Karp achieves O(E * sqrt(V)) time, better than the naive augmenting path approach of O(V * E).

Key idea of Hopcroft-Karp:
1. Find a maximal set of shortest augmenting paths simultaneously (using BFS)
2. Augment along all of them at once (using DFS)
3. Repeat until no augmenting path exists

An augmenting path starts from an unmatched left vertex, alternates between unmatched and matched edges, and ends at an unmatched right vertex. Flipping all edges along this path increases the matching by 1.

Algorithm:
1. BFS phase: Starting from all free (unmatched) left vertices simultaneously, find the shortest augmenting path length. Build layers of the BFS.
2. DFS phase: For each free left vertex, try to find an augmenting path of the shortest length found in BFS. Use the layers from BFS to guide the DFS.
3. Repeat phases 1 and 2 until BFS finds no augmenting path.

The BFS uses a level/distance array. It explores alternating paths: from unmatched left nodes, through unmatched edges to right nodes, then through matched edges back to left nodes, and so on. When we reach a free right node, we know the shortest augmenting path length.

The DFS then augments along vertex-disjoint augmenting paths of this minimum length.

The algorithm terminates in at most O(sqrt(V)) phases because after sqrt(V) phases, the shortest augmenting path has length > sqrt(V), and there can be at most sqrt(V) such paths remaining.

Time: O(E * sqrt(V)). Space: O(V + E).
</think>

**Hopcroft-Karp Maximum Bipartite Matching**

```python
from collections import deque

INF = float('inf')


def hopcroft_karp(left_nodes, right_nodes, adj):
    """
    Find maximum matching in a bipartite graph.

    Args:
        left_nodes: list of left partition vertices
        right_nodes: list of right partition vertices
        adj: {left_node: [right_node, ...]} adjacency list
    Returns:
        (matching_size, match_left, match_right)
    """
    match_l = {u: None for u in left_nodes}
    match_r = {v: None for v in right_nodes}
    dist = {}

    def bfs():
        queue = deque()
        for u in left_nodes:
            if match_l[u] is None:
                dist[u] = 0
                queue.append(u)
            else:
                dist[u] = INF

        found = False
        while queue:
            u = queue.popleft()
            for v in adj.get(u, []):
                next_u = match_r[v]
                if next_u is None:
                    found = True
                elif dist.get(next_u, INF) == INF:
                    dist[next_u] = dist[u] + 1
                    queue.append(next_u)
        return found

    def dfs(u):
        for v in adj.get(u, []):
            next_u = match_r[v]
            if next_u is None or (dist.get(next_u, INF) == dist[u] + 1
                                   and dfs(next_u)):
                match_l[u] = v
                match_r[v] = u
                return True
        dist[u] = INF
        return False

    matching = 0
    while bfs():
        for u in left_nodes:
            if match_l[u] is None:
                if dfs(u):
                    matching += 1

    return matching, match_l, match_r


# Example: Job assignment
left = ["Alice", "Bob", "Charlie", "Diana"]
right = ["Frontend", "Backend", "DevOps", "QA"]
adj = {
    "Alice":   ["Frontend", "Backend"],
    "Bob":     ["Backend", "DevOps"],
    "Charlie": ["Frontend", "QA"],
    "Diana":   ["DevOps", "QA"],
}

size, ml, mr = hopcroft_karp(left, right, adj)
print(f"Maximum matching size: {size}")
print("Assignments:")
for person in left:
    job = ml[person]
    print(f"  {person} -> {job}")

# Verify matching is maximum using Konig's theorem
# (minimum vertex cover = maximum matching in bipartite graphs)
print(f"\nBy Konig's theorem, min vertex cover = {size}")

# Larger example
left2 = list(range(5))
right2 = list(range(5, 10))
adj2 = {
    0: [5, 6],
    1: [5, 7],
    2: [6, 8],
    3: [7, 8, 9],
    4: [9],
}
size2, ml2, mr2 = hopcroft_karp(left2, right2, adj2)
print(f"\nNumeric example - Max matching: {size2}")
for u in left2:
    print(f"  {u} -> {ml2[u]}")
```

**Algorithm Phases:**
1. BFS: Find shortest augmenting paths from all free left vertices simultaneously
2. DFS: Augment along vertex-disjoint shortest paths
3. Repeat until no augmenting path exists

**Why O(E * sqrt(V)):**
- At most O(sqrt(V)) BFS+DFS phases (proven by path length argument)
- Each phase does O(E) work (BFS + DFS combined)
- Total: O(E * sqrt(V))

**Complexity:**
- Time: O(E * sqrt(V))
- Space: O(V + E)'''),

    ("thinking/algorithms", r'''Implement the Ford-Fulkerson method for computing maximum network flow using BFS (Edmonds-Karp variant). Given a flow network with source and sink, find the maximum flow from source to sink.''', r'''<think>
The Ford-Fulkerson method repeatedly finds augmenting paths from source to sink in the residual graph and pushes flow along them. The Edmonds-Karp variant uses BFS to find shortest augmenting paths, guaranteeing O(V * E^2) time.

Key concepts:
1. Residual graph: For each edge (u,v) with capacity c and flow f:
   - Forward edge: residual capacity = c - f
   - Backward edge: residual capacity = f (allows "undoing" flow)
2. Augmenting path: a path from source to sink in the residual graph with positive capacity on every edge
3. Bottleneck: minimum residual capacity along the augmenting path

Algorithm:
1. Initialize flow to 0 on all edges
2. While there exists an augmenting path (found via BFS):
   a. Find bottleneck capacity along the path
   b. Update flow: add bottleneck to forward edges, subtract from backward edges
   c. Add bottleneck to total flow
3. When no augmenting path exists, current flow is maximum

Max-Flow Min-Cut Theorem: The maximum flow equals the minimum cut capacity. When the algorithm terminates, the BFS-reachable vertices from source form one side of the min cut.

The Edmonds-Karp BFS guarantees:
- Each augmenting path has minimum number of edges
- Total number of augmentations is O(V * E)
- Each BFS is O(E)
- Total: O(V * E^2)

I will implement using an adjacency list with forward/backward edge pairing for efficient residual updates.
</think>

**Ford-Fulkerson (Edmonds-Karp) Maximum Flow**

```python
from collections import deque, defaultdict


class MaxFlow:
    def __init__(self, n):
        self.n = n
        self.graph = defaultdict(list)
        # Each edge: [to, capacity, flow, reverse_edge_index]

    def add_edge(self, u, v, cap):
        """Add directed edge u->v with capacity cap."""
        # Forward edge
        forward = [v, cap, 0, len(self.graph[v])]
        # Backward edge (residual)
        backward = [u, 0, 0, len(self.graph[u])]
        self.graph[u].append(forward)
        self.graph[v].append(backward)

    def bfs(self, source, sink):
        """Find augmenting path using BFS. Return parent map."""
        visited = {source: None}  # node -> (prev_node, edge_index)
        queue = deque([source])

        while queue:
            u = queue.popleft()
            for i, (v, cap, flow, _) in enumerate(self.graph[u]):
                if v not in visited and cap - flow > 0:
                    visited[v] = (u, i)
                    if v == sink:
                        return visited
                    queue.append(v)

        return None

    def max_flow(self, source, sink):
        """Compute maximum flow from source to sink."""
        total_flow = 0

        while True:
            parent = self.bfs(source, sink)
            if parent is None:
                break

            # Find bottleneck
            bottleneck = float('inf')
            v = sink
            while v != source:
                u, edge_idx = parent[v]
                edge = self.graph[u][edge_idx]
                bottleneck = min(bottleneck, edge[1] - edge[2])
                v = u

            # Update flow along path
            v = sink
            while v != source:
                u, edge_idx = parent[v]
                self.graph[u][edge_idx][2] += bottleneck
                rev_idx = self.graph[u][edge_idx][3]
                self.graph[v][rev_idx][2] -= bottleneck
                v = u

            total_flow += bottleneck

        return total_flow

    def min_cut(self, source):
        """Find min cut after max_flow has been computed."""
        # BFS on residual graph from source
        visited = set()
        queue = deque([source])
        visited.add(source)

        while queue:
            u = queue.popleft()
            for v, cap, flow, _ in self.graph[u]:
                if v not in visited and cap - flow > 0:
                    visited.add(v)
                    queue.append(v)

        # Min cut edges: from visited to not visited with positive capacity
        cut_edges = []
        for u in visited:
            for v, cap, flow, _ in self.graph[u]:
                if v not in visited and cap > 0:
                    cut_edges.append((u, v, cap))

        return visited, cut_edges


# Example network
mf = MaxFlow(6)
# source=0, sink=5
mf.add_edge(0, 1, 16)
mf.add_edge(0, 2, 13)
mf.add_edge(1, 2, 10)
mf.add_edge(1, 3, 12)
mf.add_edge(2, 1, 4)
mf.add_edge(2, 4, 14)
mf.add_edge(3, 2, 9)
mf.add_edge(3, 5, 20)
mf.add_edge(4, 3, 7)
mf.add_edge(4, 5, 4)

flow = mf.max_flow(0, 5)
print(f"Maximum flow: {flow}")

s_side, cut = mf.min_cut(0)
print(f"Min cut S-side: {sorted(s_side)}")
print(f"Cut edges: {cut}")
cut_capacity = sum(c for _, _, c in cut)
print(f"Min cut capacity: {cut_capacity}")
print(f"Max flow = Min cut: {flow == cut_capacity}")
```

**Max-Flow Min-Cut Theorem:**
The maximum flow from s to t equals the minimum capacity of any s-t cut. When Edmonds-Karp terminates, the BFS-reachable vertices from s in the residual graph form the S-side of the minimum cut.

**Complexity:**
- Edmonds-Karp: O(V * E^2)
- Dinic's algorithm (improvement): O(V^2 * E)
- For unit-capacity graphs: O(E * sqrt(V))'''),
]
