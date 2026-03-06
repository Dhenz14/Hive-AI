PAIRS = [
    ("thinking/algorithms", r'''Explain and prove the Max-Flow Min-Cut Theorem. Implement an algorithm that, given a flow network after computing max flow, finds the minimum cut and verifies the theorem.''', r'''<think>
The Max-Flow Min-Cut Theorem -- one of the fundamental duality results in combinatorics. Let me think through why it is true.

First, the easy direction: max flow <= min cut. Any flow must "cross" every cut, and the flow across a cut cannot exceed its capacity. Since this holds for EVERY cut, the max flow is at most the minimum cut capacity. This is almost trivial.

The hard direction: there exists a cut whose capacity equals the max flow. How do we find it?

Hmm, let me think about what happens when Ford-Fulkerson terminates. At that point, there is no augmenting path from s to t in the residual graph. So let S = vertices reachable from s in the residual graph, and T = V - S.

Now here is the key insight: t must be in T (otherwise there would be an augmenting path and the algorithm would not have stopped). For any edge (u,v) with u in S and v in T, it must be fully saturated -- because if it had residual capacity, v would be reachable from u in the residual graph, contradicting v being in T.

Wait, what about reverse edges? For any edge (v,u) with v in T and u in S, the flow must be 0. Because if flow(v,u) > 0, then u could reach v via the reverse edge in the residual graph, making v reachable -- contradiction.

So the net flow across this cut = sum of saturated forward edges - 0 reverse flow = capacity of the cut. And since we already showed flow <= any cut capacity, this cut must be minimum. Beautiful.

To actually find the min cut: run max flow, then BFS from source in the residual graph to find S. The cut edges are the S->T edges with positive capacity in the original graph.

I need to implement both the max flow (Edmonds-Karp with BFS for shortest augmenting paths) and the min cut extraction.
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
The Hungarian algorithm for optimal assignment. This is one of those algorithms that is conceptually elegant but notoriously tricky to implement correctly.

The core idea is LP duality: maintain dual variables (potentials) u[i] for workers and v[j] for tasks such that c[i][j] - u[i] - v[j] >= 0 always. Edges where this is tight (equals 0) form the "equality subgraph." If we can find a perfect matching using only tight edges, it is optimal by complementary slackness.

I initially considered the simple version: find augmenting paths on tight edges, and when stuck, adjust potentials to create new tight edges. But this can be O(n^4) if we are not careful about which potentials to adjust.

The O(n^3) version processes workers one at a time using a shortest-path approach. For each worker i, we find the shortest augmenting path (in terms of reduced costs) from i to a free task. This is like Dijkstra but on the assignment graph.

Hmm, but reduced costs can be negative because of reverse edges in the matching... wait, no. The potentials guarantee that reduced costs c[i][j] - u[i] - v[j] are always non-negative. So Dijkstra works here. After finding the shortest path, we update potentials to maintain the invariant.

The tricky part is the implementation. The standard compact version uses a "virtual task 0" as a starting point and iteratively expands the shortest path tree. For each worker, we maintain min_v[j] = minimum reduced cost to reach task j, and update it as we explore.

After finding the augmenting path, we flip the matching along it and adjust potentials by the distances found. The potential update ensures future reduced costs remain non-negative.

Why O(n^3)? Each of n workers requires finding a shortest augmenting path. The path-finding does O(n) relaxation steps (each scanning n tasks), giving O(n^2) per worker and O(n^3) total. Much better than bitmask DP O(n * 2^n) for large n.
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
Stable Matching -- the classic Gale-Shapley algorithm. A matching is "stable" if there is no blocking pair: a man and woman who would both prefer each other over their current partners.

The algorithm is deceptively simple: men propose in order of preference, women accept the best offer they have seen so far. But does this always terminate, and is the result always stable?

Termination: each man proposes to at most n women (he never proposes to the same woman twice because he goes down his list). So at most n^2 proposals total. Since each proposal either creates a match or does not, and there are n pairs to form, we must terminate.

Now, why is the result stable? Suppose for contradiction that m and w form a blocking pair -- both prefer each other over their assigned partners. Since m proposes in preference order, he must have proposed to w before proposing to his current partner. When he proposed to w, she either accepted and later dumped him for someone she likes more, or rejected him outright because she already had someone better. Either way, w ended up with someone she prefers to m. But that contradicts w preferring m -- so no blocking pair can exist.

Hmm, an interesting asymmetry: this produces the man-optimal stable matching. Each man gets the best partner he could possibly get in ANY stable matching. I initially found this surprising -- why can not some other stable matching give man 0 a better partner? The proof is by contradiction: if some man is rejected by a "stable-feasible" partner, then a chain of contradictions arises.

The flip side: this is simultaneously woman-pessimal. Each woman gets her WORST stable partner. To get the woman-optimal matching, just swap roles and have women propose.

For implementation, precomputing women's rankings as a lookup table (women_rank[w][m] = rank) makes the comparison O(1) instead of scanning the preference list each time.

Time: O(n^2) total proposals. Space: O(n^2) for preference lists and rankings.
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
Min cost max flow -- we want maximum flow but among all max flows, choose the one with minimum cost. Each edge has both capacity and cost per unit of flow.

The algorithm idea is "successive shortest paths": repeatedly find the CHEAPEST augmenting path and push flow along it. This greedy approach works because at every step we are pushing flow along the path that adds the least additional cost.

But wait, why can we not just use Dijkstra for shortest paths? The problem is that reverse edges in the residual graph have NEGATIVE costs (if we "un-send" flow on an edge with cost w, that saves w, represented as cost -w on the reverse edge). Dijkstra does not handle negative weights.

I initially thought about using Bellman-Ford, which handles negative weights but is O(V*E) per iteration -- slower than Dijkstra. An alternative is SPFA (Shortest Path Faster Algorithm), which is Bellman-Ford with a queue optimization. SPFA works well in practice despite having the same worst case.

Hmm, actually there is a clever trick: Johnson's potentials. After each shortest path computation, use the distances as potentials to re-weight edges so all reduced costs are non-negative. Then Dijkstra works for subsequent iterations. But that makes the implementation more complex. For simplicity, let me go with SPFA.

For the residual graph representation: each edge (u,v,cap,cost) gets a reverse edge (v,u,0,-cost). When we push flow f along an edge, we reduce its capacity by f and increase the reverse edge's capacity by f. The reverse edge lets us "undo" flow decisions later.

One important detail: the total cost is accumulated as flow * dist[sink] per iteration, where dist[sink] is the shortest path cost. Since we always use the cheapest path, the cost increases monotonically per unit of flow.

Time with SPFA: O(V * E * F) where F is max flow. For assignment problems with unit capacities, this is very efficient.
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
Hopcroft-Karp for maximum bipartite matching. The naive approach (find augmenting paths one at a time) gives O(V * E). Hopcroft-Karp improves this by finding MULTIPLE augmenting paths in each phase.

The algorithm has two phases per iteration:
1. BFS: start from ALL unmatched left vertices simultaneously. Build a layered graph by alternating unmatched and matched edges. Stop when we first reach unmatched right vertices -- this gives us the shortest augmenting path length.
2. DFS: greedily find a maximal set of vertex-disjoint augmenting paths within this layered graph. Use distance labels to stay on shortest paths only.

I initially thought the DFS would be complicated, but it is actually elegant. For each unmatched left vertex, try to find a path to an unmatched right vertex, only following edges that go to the next layer. If we succeed, augment. If we fail, mark this vertex as a dead end (set distance to infinity) so other DFS calls skip it.

The key question: why is the total complexity O(E * sqrt(V))?

After sqrt(V) phases, the shortest remaining augmenting path has length > sqrt(V). But the total number of vertices is V, so at most V / sqrt(V) = sqrt(V) such long paths can exist (since they are vertex-disjoint). Each remaining path contributes at most one more phase, so at most sqrt(V) additional phases.

Wait, that is not quite right. After sqrt(V) phases, there are at most sqrt(V) more augmenting paths TOTAL (not phases). So the total number of phases is at most 2 * sqrt(V). Each phase does O(E) work (BFS + DFS both traverse edges). Total: O(sqrt(V) * E).

This is a big improvement over the naive O(V * E) for dense bipartite graphs. Combined with Konig's theorem (max matching = min vertex cover in bipartite graphs), this also gives us the min vertex cover.
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
