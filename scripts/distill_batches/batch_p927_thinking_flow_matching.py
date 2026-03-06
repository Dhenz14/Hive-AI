PAIRS = [
    ("thinking/algorithms", r'''Explain and prove the Max-Flow Min-Cut Theorem. Implement an algorithm that, given a flow network after computing max flow, finds the minimum cut and verifies the theorem.''', r'''<think>
The Max-Flow Min-Cut Theorem states: In any flow network, the maximum flow from source s to sink t equals the minimum capacity of any s-t cut.

An s-t cut (S, T) is a partition of vertices into two sets S and T where s is in S and t is in T. The capacity of the cut is the sum of capacities of edges going from S to T.

Proof sketch:
1. (Flow <= Cut capacity): Any flow must pass through any cut. The net flow across any cut equals the total flow. Since flow on each edge <= capacity, total flow <= cut capacity.

2. (Max flow = Min cut): When Ford-Fulkerson terminates, there is no augmenting path from s to t in the residual graph. Define S = set of vertices reachable from s in the residual graph, T = V - S. Then:
   - t is in T (otherwise there would be an augmenting path)
   - For every edge (u,v) with u in S, v in T: the edge is fully saturated (otherwise v would be reachable, contradicting v in T)
   - For every edge (v,u) with v in T, u in S: flow is 0 (otherwise u could reach v via reverse edge)
   - Therefore: flow across cut = sum of capacities of S->T edges = capacity of this cut
   - Since flow <= any cut capacity, and we found a cut with capacity = flow, both are optimal

To find the min cut after max flow:
1. Build the residual graph
2. BFS/DFS from source to find all reachable vertices (set S)
3. S-T edges with positive capacity in the original graph form the min cut

I will implement this on top of a max-flow implementation.
</think>

**Max-Flow Min-Cut Theorem -- Implementation and Verification**

```python
from collections import defaultdict, deque


class FlowNetwork:
    """Flow network with max-flow and min-cut computation."""

    def __init__(self):
        self.graph = defaultdict(lambda: defaultdict(int))
        self.flow = defaultdict(lambda: defaultdict(int))

    def add_edge(self, u, v, cap):
        self.graph[u][v] += cap

    def bfs(self, source, sink):
        """BFS on residual graph. Returns parent map or None."""
        visited = {source}
        parent = {source: None}
        queue = deque([source])

        while queue:
            u = queue.popleft()
            for v in self.graph[u]:
                res_cap = self.graph[u][v] - self.flow[u][v]
                if v not in visited and res_cap > 0:
                    visited.add(v)
                    parent[v] = u
                    if v == sink:
                        return parent
                    queue.append(v)

            # Also check reverse edges
            for v in self.flow:
                if v not in visited and self.flow[v][u] > 0:
                    visited.add(v)
                    parent[v] = u
                    if v == sink:
                        return parent
                    queue.append(v)

        return None

    def max_flow(self, source, sink):
        """Edmonds-Karp max flow algorithm."""
        total = 0

        while True:
            parent = self.bfs(source, sink)
            if parent is None:
                break

            # Find bottleneck
            bottleneck = float('inf')
            v = sink
            while v != source:
                u = parent[v]
                # Check forward edge
                fwd = self.graph[u][v] - self.flow[u][v]
                # Check reverse edge
                rev = self.flow[v][u]
                bottleneck = min(bottleneck, max(fwd, rev))
                v = u

            # Update flow
            v = sink
            while v != source:
                u = parent[v]
                if self.graph[u][v] - self.flow[u][v] > 0:
                    self.flow[u][v] += bottleneck
                else:
                    self.flow[v][u] -= bottleneck
                v = u

            total += bottleneck

        return total

    def min_cut(self, source):
        """Find minimum cut after max flow has been computed."""
        # BFS on residual graph from source
        reachable = set()
        queue = deque([source])
        reachable.add(source)

        while queue:
            u = queue.popleft()
            for v in self.graph[u]:
                if v not in reachable:
                    res = self.graph[u][v] - self.flow[u][v]
                    if res > 0:
                        reachable.add(v)
                        queue.append(v)
            for v in self.flow:
                if v not in reachable and self.flow[v][u] > 0:
                    reachable.add(v)
                    queue.append(v)

        # Find cut edges: from reachable to non-reachable with capacity > 0
        cut_edges = []
        cut_capacity = 0
        for u in reachable:
            for v in self.graph[u]:
                if v not in reachable and self.graph[u][v] > 0:
                    cut_edges.append((u, v, self.graph[u][v]))
                    cut_capacity += self.graph[u][v]

        return reachable, cut_edges, cut_capacity


# Example
fn = FlowNetwork()
fn.add_edge("s", "a", 10)
fn.add_edge("s", "b", 10)
fn.add_edge("a", "b", 2)
fn.add_edge("a", "c", 8)
fn.add_edge("a", "d", 4)
fn.add_edge("b", "d", 9)
fn.add_edge("c", "t", 10)
fn.add_edge("d", "c", 6)
fn.add_edge("d", "t", 10)

mf = fn.max_flow("s", "t")
s_side, cut_edges, cut_cap = fn.min_cut("s")

print(f"Max Flow: {mf}")
print(f"Min Cut Capacity: {cut_cap}")
print(f"Max Flow = Min Cut: {mf == cut_cap}")
print(f"\nS-side of cut: {sorted(s_side)}")
print(f"T-side of cut: all other vertices")
print(f"Cut edges:")
for u, v, cap in cut_edges:
    print(f"  {u} -> {v} (capacity={cap})")

# Verify: flow on each edge
print(f"\nEdge flows:")
for u in fn.graph:
    for v in fn.graph[u]:
        if fn.flow[u][v] > 0:
            print(f"  {u} -> {v}: {fn.flow[u][v]}/{fn.graph[u][v]}")
```

**Max-Flow Min-Cut Theorem:**
- Maximum flow value = Minimum cut capacity
- After running max flow, S = vertices reachable from source in residual graph
- All S->T edges are saturated, all T->S edges have zero flow
- This cut has capacity exactly equal to the max flow

**Complexity:**
- Edmonds-Karp: O(V * E^2)
- Finding min cut after max flow: O(V + E) single BFS'''),

    ("thinking/algorithms", r'''Implement the Hungarian Algorithm for solving the assignment problem optimally in O(n^3) time. Given an n x n cost matrix, find the minimum-cost perfect matching.''', r'''<think>
The Hungarian Algorithm solves the assignment problem (minimum cost perfect matching in a bipartite graph) in O(n^3) time. It is based on the concept of potentials (dual variables) and augmenting paths.

The algorithm maintains:
- u[i]: potential for each row (worker) i
- v[j]: potential for each column (task) j
- Matching: which task is assigned to which worker

Key properties:
- Reduced cost: c[i][j] - u[i] - v[j] >= 0 always
- An edge is "tight" when c[i][j] - u[i] - v[j] == 0
- The current matching uses only tight edges
- Optimality: when we have a perfect matching on tight edges, it is optimal

Algorithm (row-by-row):
1. For each worker i:
   a. Try to find an augmenting path using only tight edges
   b. If no augmenting path exists, adjust potentials to create new tight edges
   c. Repeat until augmenting path is found

The potential adjustment uses the minimum reduced cost among explored edges to open up new tight edges while maintaining the non-negativity invariant.

I will implement the O(n^3) version that processes one row at a time using a shortest-path approach with potentials.

The implementation uses the "shortest augmenting path" formulation:
- Maintain distances from the current worker to each task
- Use a Dijkstra-like approach to find the shortest augmenting path
- Update potentials to reflect distances found

This is tricky to implement correctly. I will follow the well-known compact implementation.
</think>

**Hungarian Algorithm -- O(n^3) Assignment**

```python
def hungarian(cost_matrix):
    """
    Solve the assignment problem using the Hungarian algorithm.

    Args:
        cost_matrix: n x n cost matrix
    Returns:
        (min_cost, assignment) where assignment[i] = task for worker i
    """
    n = len(cost_matrix)
    INF = float('inf')

    # Add padding: use 1-indexed for convenience
    # u[i], v[j] = potentials
    u = [0] * (n + 1)
    v = [0] * (n + 1)
    # match_task[j] = worker assigned to task j (0 = unassigned)
    match_task = [0] * (n + 1)

    for i in range(1, n + 1):
        # Start augmenting from worker i
        match_task[0] = i
        j0 = 0  # virtual task

        min_v = [INF] * (n + 1)  # min reduced cost to reach task j
        used = [False] * (n + 1)  # task j used in current iteration
        prev = [0] * (n + 1)     # previous task in augmenting path

        while True:
            used[j0] = True
            i0 = match_task[j0]
            delta = INF
            j1 = -1

            for j in range(1, n + 1):
                if used[j]:
                    continue
                # Reduced cost
                reduced = cost_matrix[i0 - 1][j - 1] - u[i0] - v[j]
                if reduced < min_v[j]:
                    min_v[j] = reduced
                    prev[j] = j0
                if min_v[j] < delta:
                    delta = min_v[j]
                    j1 = j

            # Update potentials
            for j in range(n + 1):
                if used[j]:
                    u[match_task[j]] += delta
                    v[j] -= delta
                else:
                    min_v[j] -= delta

            j0 = j1

            if match_task[j0] == 0:
                break

        # Update matching along augmenting path
        while j0 != 0:
            j1 = prev[j0]
            match_task[j0] = match_task[j1]
            j0 = j1

    # Build result
    assignment = [0] * n
    for j in range(1, n + 1):
        if match_task[j] > 0:
            assignment[match_task[j] - 1] = j - 1

    min_cost = sum(cost_matrix[i][assignment[i]] for i in range(n))
    return min_cost, assignment


# Example
cost = [
    [9, 2, 7, 8],
    [6, 4, 3, 7],
    [5, 8, 1, 8],
    [7, 6, 9, 4],
]

min_cost, assignment = hungarian(cost)

print("Cost matrix:")
for row in cost:
    print(f"  {row}")
print(f"\nMinimum cost: {min_cost}")
print("Assignment:")
for i, j in enumerate(assignment):
    print(f"  Worker {i} -> Task {j} (cost={cost[i][j]})")

# Verify with brute force
from itertools import permutations
best = min(sum(cost[i][p[i]] for i in range(len(cost)))
           for p in permutations(range(len(cost))))
print(f"\nBrute force minimum: {best}")
print(f"Match: {min_cost == best}")

# Larger example
import random
random.seed(42)
n = 6
cost2 = [[random.randint(1, 50) for _ in range(n)] for _ in range(n)]
c2, a2 = hungarian(cost2)
print(f"\n{n}x{n} problem: min cost = {c2}")
print(f"Assignment: {a2}")
```

**Algorithm Key Ideas:**
1. Maintain dual potentials u[i] and v[j] such that c[i][j] - u[i] - v[j] >= 0
2. Process workers one at a time
3. Find shortest augmenting path using reduced costs
4. Adjust potentials to maintain feasibility while opening new tight edges

**Complexity:**
- Time: O(n^3) -- n iterations, each doing O(n^2) work
- Space: O(n^2) for the cost matrix, O(n) for potentials and matching
- Much better than bitmask DP O(n * 2^n) for large n'''),

    ("thinking/algorithms", r'''Implement the Gale-Shapley algorithm for the Stable Matching problem: given n men and n women with preference lists, find a stable matching where no two people would prefer each other over their current partners.''', r'''<think>
The Stable Matching Problem (also called the Stable Marriage Problem) was solved by Gale and Shapley in 1962. A matching is stable if there is no "blocking pair" -- a man and woman who both prefer each other over their current partners.

The Gale-Shapley algorithm:
1. All men and women start unmatched
2. While there is a free (unmatched) man:
   a. He proposes to his most preferred woman he has not yet proposed to
   b. If she is free, she accepts (they become matched)
   c. If she is matched, she compares the proposer with her current partner:
      - If she prefers the proposer, she dumps her current partner (he becomes free) and accepts the proposer
      - Otherwise, she rejects the proposer (he remains free and will try the next woman)
3. The algorithm terminates with a perfect stable matching

Key properties:
- Always produces a man-optimal stable matching (each man gets the best partner he could get in any stable matching)
- Simultaneously woman-pessimal (each woman gets the worst partner she could get in any stable matching)
- Running the algorithm with women proposing gives the woman-optimal matching

Proof of stability: Suppose man m and woman w form a blocking pair (both prefer each other over their partners). Then m proposed to w before his current partner (since he proposes in order of preference). When he proposed, w either accepted and later replaced him, or rejected him. In both cases, w was matched with someone she prefers to m -- contradiction.

Time: O(n^2) -- each man proposes to each woman at most once.
Space: O(n^2) for preference lists.
</think>

**Gale-Shapley Stable Matching**

```python
from collections import deque


def gale_shapley(men_prefs, women_prefs):
    """
    Find a stable matching using the Gale-Shapley algorithm.

    Args:
        men_prefs: men_prefs[m] = list of women in order of preference
        women_prefs: women_prefs[w] = list of men in order of preference
    Returns:
        dict mapping man -> woman (the stable matching)
    """
    n = len(men_prefs)

    # Precompute women's ranking of men for O(1) comparison
    # women_rank[w][m] = rank of man m in woman w's preference list
    women_rank = {}
    for w in range(n):
        women_rank[w] = {}
        for rank, m in enumerate(women_prefs[w]):
            women_rank[w][m] = rank

    # Track proposals: next_proposal[m] = index into men_prefs[m]
    next_proposal = [0] * n

    # Current matches
    man_partner = [None] * n   # man -> woman
    woman_partner = [None] * n  # woman -> man

    # Queue of free men
    free_men = deque(range(n))

    while free_men:
        m = free_men.popleft()

        # Man m proposes to next woman on his list
        w = men_prefs[m][next_proposal[m]]
        next_proposal[m] += 1

        if woman_partner[w] is None:
            # Woman is free, accept
            man_partner[m] = w
            woman_partner[w] = m
        elif women_rank[w][m] < women_rank[w][woman_partner[w]]:
            # Woman prefers new proposer
            old_m = woman_partner[w]
            man_partner[old_m] = None
            free_men.append(old_m)

            man_partner[m] = w
            woman_partner[w] = m
        else:
            # Woman rejects proposer
            free_men.append(m)

    return {m: man_partner[m] for m in range(n)}


def is_stable(matching, men_prefs, women_prefs):
    """Check if a matching is stable (no blocking pairs)."""
    n = len(men_prefs)
    women_rank = {}
    men_rank = {}
    for w in range(n):
        women_rank[w] = {m: r for r, m in enumerate(women_prefs[w])}
    for m in range(n):
        men_rank[m] = {w: r for r, w in enumerate(men_prefs[m])}

    for m in range(n):
        w_current = matching[m]
        for w in men_prefs[m]:
            if w == w_current:
                break
            # m prefers w over w_current
            # Check if w prefers m over her current partner
            m_current = None
            for m2, w2 in matching.items():
                if w2 == w:
                    m_current = m2
                    break
            if women_rank[w][m] < women_rank[w][m_current]:
                return False, (m, w)

    return True, None


# Example
men_prefs = [
    [0, 1, 2],  # Man 0 prefers Woman 0 > 1 > 2
    [1, 0, 2],  # Man 1 prefers Woman 1 > 0 > 2
    [0, 2, 1],  # Man 2 prefers Woman 0 > 2 > 1
]
women_prefs = [
    [1, 0, 2],  # Woman 0 prefers Man 1 > 0 > 2
    [0, 1, 2],  # Woman 1 prefers Man 0 > 1 > 2
    [0, 2, 1],  # Woman 2 prefers Man 0 > 2 > 1
]

matching = gale_shapley(men_prefs, women_prefs)
stable, blocking = is_stable(matching, men_prefs, women_prefs)

print("Preferences:")
for m in range(len(men_prefs)):
    print(f"  Man {m}: {men_prefs[m]}")
for w in range(len(women_prefs)):
    print(f"  Woman {w}: {women_prefs[w]}")

print(f"\nStable matching (man-optimal):")
for m, w in sorted(matching.items()):
    print(f"  Man {m} <-> Woman {w}")
print(f"Stable: {stable}")

# Woman-optimal: swap roles
w_matching = gale_shapley(women_prefs, men_prefs)
print(f"\nStable matching (woman-optimal):")
for w, m in sorted(w_matching.items()):
    print(f"  Woman {w} <-> Man {m}")
```

**Properties of Gale-Shapley:**
- Always terminates in at most n^2 proposals
- Produces a man-optimal stable matching (proposing side gets best possible)
- No stable matching can give any man a better partner
- The matching is unique if there is only one stable matching

**Complexity:**
- Time: O(n^2) -- at most n proposals per man, n men total
- Space: O(n^2) for preference lists and rankings'''),

    ("thinking/algorithms", r'''Implement the Minimum Cost Maximum Flow algorithm: given a flow network where each edge has both a capacity and a cost per unit of flow, find a maximum flow that minimizes total cost.''', r'''<think>
Minimum Cost Maximum Flow combines flow maximization with cost minimization. Each edge has capacity c and cost w (cost per unit of flow). We want to push maximum flow from s to t while minimizing total cost = sum of flow * cost over all edges.

Algorithm (Successive Shortest Path):
1. Initialize with zero flow
2. While there exists an augmenting path from s to t in the residual graph:
   a. Find the shortest (minimum cost) augmenting path using Bellman-Ford or SPFA (since costs can include negative edges from reverse arcs)
   b. Push maximum possible flow along this path
   c. Update residual graph

Using shortest path ensures each augmenting iteration adds flow along the cheapest possible path, guaranteeing minimum cost at each flow level.

Residual graph: For edge (u,v) with capacity c, flow f, cost w:
- Forward: residual capacity c-f, cost w
- Backward: residual capacity f, cost -w

Since reverse edges have negative cost, we need Bellman-Ford or SPFA (not Dijkstra) unless we use Johnson's potential transformation.

With potentials (Johnson's trick):
- Maintain potential p[v] from previous shortest path
- Reduced cost: w'(u,v) = w(u,v) + p[u] - p[v] >= 0
- This allows using Dijkstra for shortest paths

Time: O(V * E * max_flow) with SPFA, or O(V^2 * E * log V) with Dijkstra + potentials.
For unit-capacity graphs: O(E * sqrt(V) * log V).
</think>

**Minimum Cost Maximum Flow**

```python
from collections import defaultdict, deque
import heapq


class MinCostFlow:
    """Minimum cost maximum flow using SPFA (Bellman-Ford variant)."""

    def __init__(self, n):
        self.n = n
        self.graph = [[] for _ in range(n)]

    def add_edge(self, u, v, cap, cost):
        """Add directed edge u->v with given capacity and cost."""
        # Forward edge
        self.graph[u].append([v, cap, cost, len(self.graph[v])])
        # Reverse edge
        self.graph[v].append([u, 0, -cost, len(self.graph[u]) - 1])

    def min_cost_max_flow(self, source, sink):
        """
        Compute minimum cost maximum flow.

        Returns: (max_flow, min_cost)
        """
        total_flow = 0
        total_cost = 0

        while True:
            # SPFA to find shortest path (minimum cost augmenting path)
            dist = [float('inf')] * self.n
            in_queue = [False] * self.n
            prev_node = [-1] * self.n
            prev_edge = [-1] * self.n
            dist[source] = 0
            in_queue[source] = True
            queue = deque([source])

            while queue:
                u = queue.popleft()
                in_queue[u] = False

                for idx, (v, cap, cost, _) in enumerate(self.graph[u]):
                    if cap > 0 and dist[u] + cost < dist[v]:
                        dist[v] = dist[u] + cost
                        prev_node[v] = u
                        prev_edge[v] = idx
                        if not in_queue[v]:
                            in_queue[v] = True
                            queue.append(v)

            if dist[sink] == float('inf'):
                break  # No more augmenting paths

            # Find bottleneck flow along shortest path
            flow = float('inf')
            v = sink
            while v != source:
                u = prev_node[v]
                edge_idx = prev_edge[v]
                flow = min(flow, self.graph[u][edge_idx][1])
                v = u

            # Push flow along path
            v = sink
            while v != source:
                u = prev_node[v]
                edge_idx = prev_edge[v]
                self.graph[u][edge_idx][1] -= flow
                rev_idx = self.graph[u][edge_idx][3]
                self.graph[v][rev_idx][1] += flow
                v = u

            total_flow += flow
            total_cost += flow * dist[sink]

        return total_flow, total_cost


# Example: shipping goods through a network
mcf = MinCostFlow(6)
# source=0, sink=5
# Edge: (from, to, capacity, cost_per_unit)
mcf.add_edge(0, 1, 4, 1)
mcf.add_edge(0, 2, 2, 5)
mcf.add_edge(1, 2, 2, 1)
mcf.add_edge(1, 3, 3, 3)
mcf.add_edge(2, 4, 3, 2)
mcf.add_edge(3, 5, 3, 1)
mcf.add_edge(4, 5, 5, 2)
mcf.add_edge(3, 4, 1, 1)

flow, cost = mcf.min_cost_max_flow(0, 5)
print(f"Maximum flow: {flow}")
print(f"Minimum cost: {cost}")

# Application: assignment as min-cost flow
print("\n--- Assignment via Min-Cost Flow ---")
# 3 workers, 3 tasks
costs = [[3, 2, 7], [5, 1, 3], [2, 7, 2]]
n = 3
mcf2 = MinCostFlow(2 * n + 2)
s, t = 0, 2 * n + 1

for i in range(n):
    mcf2.add_edge(s, i + 1, 1, 0)           # source -> worker
    mcf2.add_edge(n + i + 1, t, 1, 0)       # task -> sink
    for j in range(n):
        mcf2.add_edge(i + 1, n + j + 1, 1, costs[i][j])

flow2, cost2 = mcf2.min_cost_max_flow(s, t)
print(f"Assignment cost: {cost2}")
print(f"Flow: {flow2}")
```

**Key Insight -- Successive Shortest Paths:**
- Each iteration finds the cheapest augmenting path
- Pushing flow along cheapest paths first ensures global optimality
- Reverse edges with negative costs allow "undoing" previous flow decisions

**Applications:**
- Transportation problems
- Assignment problems
- Network design with costs
- Minimum cost bipartite matching

**Complexity:**
- SPFA version: O(V * E * F) where F = max flow value
- With Dijkstra + potentials: O(F * E * log V)
- Space: O(V + E)'''),

    ("thinking/algorithms", r'''Implement the Hopcroft-Karp algorithm for maximum bipartite matching. Achieve O(E * sqrt(V)) time complexity by finding maximal sets of shortest augmenting paths simultaneously.''', r'''<think>
Hopcroft-Karp improves on the naive augmenting path algorithm by finding multiple augmenting paths of the same shortest length in each phase.

Algorithm:
1. BFS phase: Find the length of shortest augmenting paths. Build a layered graph from all free left vertices to free right vertices.
2. DFS phase: Find a maximal set of vertex-disjoint shortest augmenting paths. Augment all of them.
3. Repeat until no augmenting path exists.

BFS details:
- Start BFS from all unmatched left vertices simultaneously
- Alternate between unmatched edges (left->right) and matched edges (right->left)
- When we first reach an unmatched right vertex, we know the shortest augmenting path length
- Build the layered graph (distance labels)

DFS details:
- For each unmatched left vertex, try to find an augmenting path within the layered graph
- Use the distance labels to only follow edges that go to the next layer
- Mark vertices as used to ensure vertex-disjoint paths

Why O(E * sqrt(V)):
- After sqrt(V) phases, the shortest augmenting path has length > sqrt(V)
- At most sqrt(V) such long augmenting paths can exist (each uses at least sqrt(V) vertices)
- Each phase does O(E) work
- Total: O(sqrt(V) * E)

I will implement this cleanly with separate BFS and DFS functions.
</think>

**Hopcroft-Karp Maximum Bipartite Matching**

```python
from collections import deque


class HopcroftKarp:
    """Maximum bipartite matching using Hopcroft-Karp algorithm."""

    def __init__(self, n_left, n_right):
        self.n_left = n_left
        self.n_right = n_right
        self.adj = [[] for _ in range(n_left)]
        self.match_left = [-1] * n_left
        self.match_right = [-1] * n_right
        self.dist = [0] * n_left

    def add_edge(self, u, v):
        """Add edge from left vertex u to right vertex v."""
        self.adj[u].append(v)

    def bfs(self):
        """
        BFS from all free left vertices.
        Returns True if augmenting path exists.
        """
        queue = deque()
        INF = float('inf')

        for u in range(self.n_left):
            if self.match_left[u] == -1:
                self.dist[u] = 0
                queue.append(u)
            else:
                self.dist[u] = INF

        found = False

        while queue:
            u = queue.popleft()

            for v in self.adj[u]:
                # v is a right vertex
                next_u = self.match_right[v]

                if next_u == -1:
                    # Found augmenting path (free right vertex)
                    found = True
                elif self.dist[next_u] == INF:
                    # Extend BFS to the matched left vertex
                    self.dist[next_u] = self.dist[u] + 1
                    queue.append(next_u)

        return found

    def dfs(self, u):
        """
        DFS from left vertex u to find augmenting path.
        Uses distance labels from BFS for layered graph.
        """
        INF = float('inf')

        for v in self.adj[u]:
            next_u = self.match_right[v]

            if next_u == -1 or (self.dist[next_u] == self.dist[u] + 1
                                 and self.dfs(next_u)):
                self.match_left[u] = v
                self.match_right[v] = u
                return True

        self.dist[u] = INF  # Mark as visited / dead end
        return False

    def max_matching(self):
        """Find maximum matching. Returns matching size."""
        matching = 0

        while self.bfs():
            for u in range(self.n_left):
                if self.match_left[u] == -1:
                    if self.dfs(u):
                        matching += 1

        return matching

    def get_matching(self):
        """Return list of (left, right) matched pairs."""
        pairs = []
        for u in range(self.n_left):
            if self.match_left[u] != -1:
                pairs.append((u, self.match_left[u]))
        return pairs


# Example: Job assignment
n_workers = 5
n_jobs = 5
hk = HopcroftKarp(n_workers, n_jobs)

# Worker skills (which jobs each worker can do)
skills = {
    0: [0, 1],       # Worker 0 can do jobs 0, 1
    1: [0, 2],       # Worker 1 can do jobs 0, 2
    2: [1, 2, 3],    # Worker 2 can do jobs 1, 2, 3
    3: [2, 4],       # Worker 3 can do jobs 2, 4
    4: [3, 4],       # Worker 4 can do jobs 3, 4
}

for worker, jobs in skills.items():
    for job in jobs:
        hk.add_edge(worker, job)

size = hk.max_matching()
pairs = hk.get_matching()

print(f"Workers: {n_workers}, Jobs: {n_jobs}")
print(f"Maximum matching size: {size}")
print(f"Assignments:")
for w, j in pairs:
    print(f"  Worker {w} -> Job {j}")

# Verify matching is valid
used_workers = set()
used_jobs = set()
for w, j in pairs:
    assert w not in used_workers, f"Worker {w} assigned twice"
    assert j not in used_jobs, f"Job {j} assigned twice"
    assert j in skills[w], f"Worker {w} cannot do job {j}"
    used_workers.add(w)
    used_jobs.add(j)
print(f"Matching verified!")

# Minimum vertex cover via Konig's theorem
print(f"\nBy Konig's theorem:")
print(f"  Min vertex cover size = Max matching = {size}")
```

**Phase Analysis:**
- Each BFS+DFS phase takes O(E) time
- After phase k, shortest augmenting path length >= 2k+1
- After sqrt(V) phases, path length > sqrt(V)
- Remaining unmatched vertices <= sqrt(V)
- Total: O(sqrt(V)) phases * O(E) per phase = O(E * sqrt(V))

**Konig's Theorem:**
In bipartite graphs: Maximum Matching = Minimum Vertex Cover.
This is a fundamental theorem connecting matching and covering.

**Complexity:**
- Time: O(E * sqrt(V))
- Space: O(V + E)'''),
]
