PAIRS = [
    ("thinking/algorithms", r'''Implement Tarjan's algorithm for finding Strongly Connected Components (SCCs) in a directed graph. Explain how it works and demonstrate on an example graph.''', r'''<think>
I need to find all strongly connected components in a directed graph. An SCC is a maximal set of vertices where every vertex is reachable from every other.

My first thought is to do something like BFS/DFS from each node and check reachability in both directions... but wait, that would be O(V * (V + E)) which is way too slow for large graphs.

I initially considered Kosaraju's algorithm (two DFS passes -- one on original graph, one on transposed), but Tarjan's does it in a single DFS pass, which is cleaner. Let me think through how Tarjan's works.

The algorithm tracks three things per node:
1. Discovery time (disc): when the node is first visited
2. Low-link value (low): the smallest discovery time reachable from this node's subtree
3. A stack of nodes in the current exploration path

On visiting node u: set disc[u] = low[u] = timer++, push u onto stack.
For each neighbor v of u:
  - If v not visited: recurse, then low[u] = min(low[u], low[v])
  - If v is on the stack: low[u] = min(low[u], disc[v])

Hmm, but why do we only update low from nodes on the stack? I need to think about this carefully. If v was already visited and already popped from the stack, that means v belongs to an already-completed SCC. Since SCCs are maximal, there is no path from v back to u, so v should NOT influence u's low-link. If we mistakenly used disc[v] from a popped node, we could incorrectly merge separate SCCs.

After processing all neighbors, if low[u] == disc[u], u is the "root" of its SCC. This could mean u is alone, or it could mean u is the earliest-discovered node in a cycle. We pop everything from the stack down to and including u -- that forms one complete SCC.

Wait, why does low[u] == disc[u] guarantee this? Because it means no node in u's subtree can reach anything discovered before u. So u and everything above it on the stack are trapped in a cycle with each other, with no escape to earlier nodes. That is exactly the definition of a maximal SCC.

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
I need to find articulation points -- vertices whose removal disconnects the graph. The brute force approach would be to remove each vertex one at a time and check connectivity, but that is O(V * (V + E)). There should be a DFS-based approach similar to Tarjan's SCC...

Actually, yes -- this uses a modified DFS with discovery times and low-link values, but adapted for undirected graphs instead of directed ones.

So when is vertex u an articulation point? Let me think through the cases:

Case 1: u is the root of the DFS tree. If u has only one DFS child, removing u just detaches that single subtree which is still connected internally. But wait, if u has 2+ DFS tree children, those children only connect to each other through u (since there are no cross edges in undirected DFS). So u is an articulation point.

Case 2: u is not root. I initially thought any node with multiple children would be an AP, but that is wrong -- if a child's subtree has a back edge to an ancestor of u, removing u does not disconnect it. The real condition is: u is an AP if some child v has low[v] >= disc[u]. Because low[v] >= disc[u] means v's entire subtree cannot "escape" above u through back edges. Removing u would strand that subtree.

Hmm, I need to be careful about one thing: in an undirected graph, every tree edge (u, v) also appears as (v, u) in the adjacency list. I must not treat the edge back to the parent as a back edge. So I need to track parent[u] and skip it when computing low values.

We could also find bridges (cut edges) with an almost identical algorithm. The difference: for bridges, the condition is low[v] > disc[u] (strict inequality), because if low[v] == disc[u], the subtree can still reach u itself through a back edge, so u-v is not a bridge even though u might be an AP.

Edge cases to consider:
- Already disconnected graph (run DFS from each component)
- Single node (not an AP -- nothing to disconnect)
- Tree (every internal node is an AP)
- Complete graph (no APs -- too many redundant paths)

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
I need to determine if an Euler path or circuit exists, and find one if it does. Let me start with the existence conditions.

For undirected graphs, I recall the degree conditions:
- Euler circuit: every vertex has even degree (and graph is connected among edges)
- Euler path: exactly 0 or 2 vertices have odd degree

Why does this work? Each time the path enters a vertex, it must also leave. So for internal vertices we need even degree. For the endpoints of a non-circuit path, they have one extra enter or exit, giving odd degree.

For directed graphs, similar logic applies but with in-degree and out-degree:
- Euler circuit: in_degree == out_degree for every vertex, and strongly connected
- Euler path: at most one vertex with out - in = 1 (start), one with in - out = 1 (end), rest balanced

Now, how to actually find the path? I initially considered just doing a DFS and hoping for the best, but that fails -- you can get stuck at a dead end with unused edges still remaining. For example, if you greedily follow edges and enter a small cycle early, you might exhaust it and get stuck at a vertex that still has other edges.

Hierholzer's algorithm solves this elegantly. The key idea: when you get stuck, you are guaranteed to be back at a vertex that has remaining edges (since degree conditions ensure you can only get stuck at the start). So you backtrack and splice in sub-circuits.

The clean implementation uses a stack:
1. Push the start vertex
2. At each vertex, if it has unused edges, follow one and push the next vertex
3. If no unused edges remain, pop the vertex into the result
4. The result (reversed) is the Euler path

Wait, for undirected graphs there is a subtlety -- when we "use" edge (u, v), we need to mark it used from both directions. I will track edge indices so that both directions of the same edge share an index.

For directed graphs it is simpler: just pop from the adjacency deque.

Edge cases: graph with no edges (trivial circuit), isolated vertices (ignore them), multigraph with parallel edges.

Time: O(E) -- each edge visited once.
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
I need maximum bipartite matching -- the largest set of edges with no shared endpoints. The naive approach is to repeatedly find augmenting paths one at a time using DFS, which gives O(V * E). Can we do better?

Hopcroft-Karp improves this to O(E * sqrt(V)) by finding multiple shortest augmenting paths simultaneously in each phase. Let me think about why that helps.

An augmenting path starts at a free left vertex, alternates between unmatched and matched edges, and ends at a free right vertex. Flipping the edges along this path grows the matching by 1.

The algorithm has two phases per round:
1. BFS phase: start from ALL free left vertices at once, building layers of an alternating BFS. This finds the shortest augmenting path length.
2. DFS phase: for each free left vertex, try to find an augmenting path using only edges that follow the BFS layers. Augment along each one found.

Hmm, but what if two augmenting paths share a vertex? We need them to be vertex-disjoint. The DFS handles this naturally -- once a vertex is used in one augmenting path, it gets assigned to a new layer distance (set to INF), so subsequent DFS calls will not try to go through it.

I initially wondered why we cannot just find ALL augmenting paths (not just shortest). The answer is that restricting to shortest paths in each phase is what gives the sqrt(V) bound on the number of phases. After k phases, the shortest remaining augmenting path has length >= 2k+1. Since augmenting paths have length at most V, after sqrt(V) phases the remaining unmatched vertices number at most sqrt(V), giving at most sqrt(V) more augmentations.

Wait, let me recheck that reasoning... After sqrt(V) phases, shortest path length > 2*sqrt(V). The remaining augmenting paths are long, and since they are vertex-disjoint from each other (by maximality of each phase), there can be at most V / (2*sqrt(V)) = sqrt(V)/2 of them. So total phases is O(sqrt(V)), each doing O(E) work. Total: O(E * sqrt(V)).

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
I need to compute maximum flow in a network. The basic Ford-Fulkerson idea is simple: keep finding paths from source to sink with available capacity, push flow along them, repeat. But the original method with arbitrary path selection can be very slow (or even non-terminating with irrational capacities).

The Edmonds-Karp variant fixes this by always choosing the shortest augmenting path via BFS. This guarantees termination and gives O(V * E^2) time.

Let me think through the key data structure -- the residual graph. For each original edge (u, v) with capacity c:
- Forward edge: residual capacity = c - f (room for more flow)
- Backward edge (v to u): residual capacity = f (allows "undoing" flow)

I initially thought we could just track flow on forward edges and compute residuals on the fly, but we actually need explicit backward edges in the adjacency list so BFS can find them. The trick is to pair each forward edge with its backward edge so we can update both in O(1).

The algorithm:
1. BFS from source to sink in residual graph
2. If no path exists, we are done -- current flow is maximum
3. Otherwise, find the bottleneck (minimum residual capacity on path)
4. Push flow: increase flow on forward edges, decrease on backward edges
5. Repeat

Wait, why does this always find the true maximum? Because of the Max-Flow Min-Cut theorem. When no augmenting path exists, the BFS-reachable vertices from source form one side of a cut, and that cut's capacity equals the total flow. Since flow <= any cut capacity, and we found a cut matching our flow, both must be optimal.

Why O(V * E^2)? Each BFS is O(E). The key insight is that the shortest path distance from source to sink never decreases between iterations. And after at most O(V * E) augmentations total (since each augmentation saturates at least one edge, and edge distances only increase), we terminate. Actually, more precisely: O(V*E) augmentations, each taking O(E) for BFS, giving O(V * E^2).

For the implementation, I will store edges as [to, capacity, flow, reverse_edge_index] so forward and backward edges can find each other efficiently.
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
