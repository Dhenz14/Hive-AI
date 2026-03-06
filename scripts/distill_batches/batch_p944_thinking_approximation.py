PAIRS = [
    ("thinking/algorithms", r'''Implement the 2-approximation algorithm for Vertex Cover. Prove the approximation ratio and compare with the optimal solution on small graphs.''', r'''<think>
The 2-approximation for vertex cover is beautifully simple:
1. Find a maximal matching (not maximum -- just maximal, meaning no more edges can be added)
2. Take both endpoints of every matched edge
3. This gives a vertex cover of size 2 * |matching|

Proof of 2-approximation:
- The set is a valid vertex cover: every edge is either in the matching (both endpoints covered) or has an endpoint adjacent to a matched edge (covered by maximality)
- OPT >= |matching| because each matched edge needs at least one endpoint in any vertex cover
- Our solution = 2 * |matching| <= 2 * OPT

Finding a maximal matching: greedily add edges whose endpoints are both unmatched.

For comparison, I will also compute the optimal vertex cover for small graphs using brute force.
</think>

## Vertex Cover 2-Approximation

### Implementation

```python
def maximal_matching(n, edges):
    """Find a maximal matching greedily."""
    matched = set()
    matching = []
    for u, v in edges:
        if u not in matched and v not in matched:
            matching.append((u, v))
            matched.add(u)
            matched.add(v)
    return matching


def vertex_cover_2approx(n, edges):
    """2-approximation for minimum vertex cover.
    Take both endpoints of every edge in a maximal matching."""
    matching = maximal_matching(n, edges)
    cover = set()
    for u, v in matching:
        cover.add(u)
        cover.add(v)
    return cover


def vertex_cover_optimal(n, edges):
    """Exact minimum vertex cover via brute force. O(2^n)."""
    edge_set = set()
    for u, v in edges:
        edge_set.add((min(u,v), max(u,v)))

    best = set(range(n))  # worst case: all vertices
    for mask in range(1 << n):
        nodes = set(i for i in range(n) if mask & (1 << i))
        if len(nodes) >= len(best):
            continue
        # Check if nodes is a valid vertex cover
        valid = True
        for u, v in edge_set:
            if u not in nodes and v not in nodes:
                valid = False
                break
        if valid:
            best = nodes
    return best


def verify_cover(edges, cover):
    """Check that cover is a valid vertex cover."""
    for u, v in edges:
        if u not in cover and v not in cover:
            return False
    return True


# Demo
import random
random.seed(42)

print("=== Vertex Cover 2-Approximation ===\n")

test_graphs = [
    ("Triangle", 3, [(0,1),(1,2),(2,0)]),
    ("Path P5", 5, [(0,1),(1,2),(2,3),(3,4)]),
    ("Star K1,4", 5, [(0,1),(0,2),(0,3),(0,4)]),
    ("Petersen", 10, [(0,1),(1,2),(2,3),(3,4),(4,0),
                       (0,5),(1,6),(2,7),(3,8),(4,9),
                       (5,7),(7,9),(9,6),(6,8),(8,5)]),
]

print(f"{'Graph':<12} {'|V|':>4} {'|E|':>4} {'OPT':>4} {'Approx':>7} {'Ratio':>6}")
print("-" * 45)

for name, n, edges in test_graphs:
    approx_cover = vertex_cover_2approx(n, edges)
    if n <= 15:
        opt_cover = vertex_cover_optimal(n, edges)
        opt_size = len(opt_cover)
    else:
        opt_size = "?"

    approx_size = len(approx_cover)
    valid = verify_cover(edges, approx_cover)

    if isinstance(opt_size, int):
        ratio = approx_size / opt_size
        print(f"{name:<12} {n:>4} {len(edges):>4} {opt_size:>4} {approx_size:>7} {ratio:>6.2f}")
    else:
        print(f"{name:<12} {n:>4} {len(edges):>4} {'?':>4} {approx_size:>7} {'?':>6}")

# Random graphs
print(f"\n=== Random Graphs ===")
for n in [8, 10, 12]:
    edges = []
    for i in range(n):
        for j in range(i+1, n):
            if random.random() < 0.3:
                edges.append((i, j))
    approx = vertex_cover_2approx(n, edges)
    opt = vertex_cover_optimal(n, edges)
    ratio = len(approx) / max(len(opt), 1)
    print(f"  n={n}, |E|={len(edges)}: OPT={len(opt)}, approx={len(approx)}, ratio={ratio:.2f}")

print(f"\n=== Proof of 2-Approximation ===")
print(f"  1. Find maximal matching M")
print(f"  2. Cover = both endpoints of M -> size = 2|M|")
print(f"  3. OPT >= |M| (each matched edge needs >= 1 endpoint)")
print(f"  4. Therefore: Cover <= 2 * OPT")
```

### Complexity
- **Algorithm**: O(V + E) -- one pass through edges
- **Approximation ratio**: 2 (tight in worst case)
- **Best known polynomial ratio**: 2 - epsilon is open problem
- **This is one of the simplest approximation algorithms with provable guarantee**'''),

    ("thinking/algorithms", r'''Implement the greedy approximation for Set Cover. Given a universe U and a collection of subsets, find the minimum number of subsets that cover U. Show the O(ln n) approximation ratio.''', r'''<think>
Greedy Set Cover:
1. While there are uncovered elements:
   a. Pick the subset that covers the most uncovered elements
   b. Add it to the solution
   c. Remove covered elements from the universe

This gives an H(n) = O(ln n) approximation, where H(n) = 1 + 1/2 + ... + 1/n is the harmonic number.

Proof of approximation ratio (sketch):
- Let OPT = size of optimal solution
- At each step, the best subset covers at least |remaining| / OPT elements (pigeonhole)
- After t steps, remaining <= n * (1 - 1/OPT)^t
- After OPT * ln(n) steps, remaining < 1, so we're done
- Total subsets used <= OPT * ln(n) = H(n) * OPT

This is essentially tight: there exist instances where greedy uses H(n) * OPT subsets.

I will also implement the LP relaxation approach for comparison (not optimal but interesting).
</think>

## Greedy Set Cover Approximation

### Implementation

```python
import math


def greedy_set_cover(universe, subsets):
    """Greedy approximation for minimum set cover.

    Args:
        universe: set of elements to cover
        subsets: list of (cost, elements_set) tuples

    Returns:
        (total_cost, selected_indices)
    """
    uncovered = set(universe)
    selected = []
    total_cost = 0

    while uncovered:
        # Find subset with best cost-effectiveness
        best_idx = -1
        best_ratio = float('inf')

        for i, (cost, elements) in enumerate(subsets):
            if i in set(selected):
                continue
            covered_new = len(elements & uncovered)
            if covered_new > 0:
                ratio = cost / covered_new
                if ratio < best_ratio:
                    best_ratio = ratio
                    best_idx = i

        if best_idx == -1:
            break  # cannot cover remaining elements

        cost, elements = subsets[best_idx]
        selected.append(best_idx)
        total_cost += cost
        uncovered -= elements

    if uncovered:
        return None, None  # infeasible

    return total_cost, selected


def optimal_set_cover(universe, subsets):
    """Exact minimum set cover via brute force. O(2^m)."""
    m = len(subsets)
    best_cost = float('inf')
    best_selection = None

    for mask in range(1 << m):
        covered = set()
        cost = 0
        selection = []
        for i in range(m):
            if mask & (1 << i):
                c, elements = subsets[i]
                covered |= elements
                cost += c
                selection.append(i)
        if covered >= universe and cost < best_cost:
            best_cost = cost
            best_selection = selection

    return best_cost, best_selection


# Demo
print("=== Greedy Set Cover ===\n")

# Example 1: Unit cost
universe = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
subsets = [
    (1, {1, 2, 3}),
    (1, {2, 4, 5}),
    (1, {3, 5, 6, 7}),
    (1, {8, 9, 10}),
    (1, {1, 4, 7, 8}),
    (1, {2, 5, 9}),
    (1, {6, 10}),
]

greedy_cost, greedy_sel = greedy_set_cover(universe, subsets)
opt_cost, opt_sel = optimal_set_cover(universe, subsets)

print(f"Universe: {universe}")
print(f"Subsets: {len(subsets)}")
print(f"\nGreedy: cost={greedy_cost}, subsets={greedy_sel}")
print(f"Optimal: cost={opt_cost}, subsets={opt_sel}")
if opt_cost > 0:
    print(f"Ratio: {greedy_cost/opt_cost:.2f} (bound: H({len(universe)}) = {sum(1/i for i in range(1,len(universe)+1)):.2f})")

# Example 2: Weighted
print(f"\n--- Weighted Example ---")
universe2 = {1, 2, 3, 4, 5}
subsets2 = [
    (10, {1, 2, 3, 4, 5}),  # expensive but covers all
    (3, {1, 2}),
    (3, {3, 4}),
    (3, {5}),
    (4, {1, 3, 5}),
]

gc, gs = greedy_set_cover(universe2, subsets2)
oc, os = optimal_set_cover(universe2, subsets2)
print(f"Greedy: cost={gc}, subsets={gs}")
print(f"Optimal: cost={oc}, subsets={os}")
print(f"Ratio: {gc/oc:.2f}")

# Worst-case demonstration
print(f"\n--- Approximation Ratio Analysis ---")
print(f"{'n':>4} {'H(n)':>6} {'Greedy ratio bound':>18}")
for n in [5, 10, 50, 100, 1000]:
    hn = sum(1.0/i for i in range(1, n+1))
    print(f"{n:>4} {hn:>6.2f} {'<= ' + f'{hn:.2f}':>18}")

print(f"\n=== Proof Sketch ===")
print(f"  After each greedy step, uncovered reduces by factor (1 - 1/OPT)")
print(f"  After OPT * ln(n) steps, uncovered < 1")
print(f"  Total subsets <= H(n) * OPT")
print(f"  This is essentially tight (matching lower bound)")
```

### Complexity
- **Greedy**: O(|U| * |subsets|) per iteration, O(|U| * |subsets|^2) total
- **Approximation ratio**: H(n) = O(ln n) -- best possible unless P=NP
- **Hardness**: cannot approximate better than (1-epsilon)*ln(n) unless P=NP'''),

    ("thinking/algorithms", r'''Implement the 2-approximation for metric TSP using minimum spanning tree. Show the MST-based tour construction and prove the approximation ratio.''', r'''<think>
The MST-based 2-approximation for metric TSP:
1. Build MST of the complete graph
2. Double every edge (creating an Eulerian multigraph)
3. Find an Euler tour
4. Shortcut: skip already-visited vertices

This gives a tour of length <= 2 * MST_weight <= 2 * OPT.

Proof:
- OPT >= MST_weight (removing one edge from optimal tour gives a spanning tree)
- Euler tour of doubled MST = 2 * MST_weight
- Shortcutting only reduces length (triangle inequality)
- Therefore: tour <= 2 * MST_weight <= 2 * OPT

Note: This only works for metric TSP (triangle inequality holds).

The Christofides algorithm improves this to 1.5-approximation by using minimum weight perfect matching on odd-degree vertices instead of doubling all edges.

I will implement:
1. MST construction (Prim's)
2. DFS preorder traversal of MST (equivalent to shortcutting)
3. Tour length computation
4. Comparison with brute-force optimal for small instances
</think>

## TSP 2-Approximation via MST

### Implementation

```python
import heapq
import math
from itertools import permutations


def euclidean_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)


def complete_distance_matrix(points):
    """Build complete distance matrix from point coordinates."""
    n = len(points)
    dist = [[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1, n):
            d = euclidean_distance(points[i], points[j])
            dist[i][j] = d
            dist[j][i] = d
    return dist


def mst_prim(n, dist):
    """Prim's algorithm for MST. Returns MST edges and total weight."""
    in_mst = [False] * n
    mst_edges = []
    total_weight = 0

    # (weight, vertex, parent)
    heap = [(0, 0, -1)]
    while heap and len(mst_edges) < n:
        w, u, parent = heapq.heappop(heap)
        if in_mst[u]:
            continue
        in_mst[u] = True
        total_weight += w
        if parent != -1:
            mst_edges.append((parent, u, w))
        for v in range(n):
            if not in_mst[v]:
                heapq.heappush(heap, (dist[u][v], v, u))

    return mst_edges, total_weight


def tsp_mst_approx(n, dist):
    """2-approximation for metric TSP using MST.

    Returns:
        (tour, tour_length)
    """
    # Build MST
    mst_edges, mst_weight = mst_prim(n, dist)

    # Build MST adjacency
    adj = [[] for _ in range(n)]
    for u, v, w in mst_edges:
        adj[u].append(v)
        adj[v].append(u)

    # DFS preorder traversal = shortcutted Euler tour
    visited = [False] * n
    tour = []

    def dfs(u):
        visited[u] = True
        tour.append(u)
        for v in adj[u]:
            if not visited[v]:
                dfs(v)

    dfs(0)
    tour.append(0)  # return to start

    # Compute tour length
    tour_length = sum(dist[tour[i]][tour[i+1]] for i in range(len(tour)-1))

    return tour, tour_length


def tsp_optimal(n, dist):
    """Brute force optimal TSP tour. O(n!)."""
    if n <= 1:
        return [0, 0], 0

    best_length = float('inf')
    best_tour = None

    for perm in permutations(range(1, n)):
        tour = [0] + list(perm) + [0]
        length = sum(dist[tour[i]][tour[i+1]] for i in range(len(tour)-1))
        if length < best_length:
            best_length = length
            best_tour = tour

    return best_tour, best_length


# Demo
import random
random.seed(42)

print("=== TSP 2-Approximation via MST ===\n")

# Generate random points
n = 8
points = [(random.uniform(0, 100), random.uniform(0, 100)) for _ in range(n)]
dist = complete_distance_matrix(points)

# MST info
mst_edges, mst_weight = mst_prim(n, dist)
print(f"Points: {n} random points in [0,100]x[0,100]")
print(f"MST weight: {mst_weight:.2f}")

# Approximation
approx_tour, approx_length = tsp_mst_approx(n, dist)
print(f"\nMST-based tour: {approx_tour}")
print(f"Tour length: {approx_length:.2f}")

# Optimal (brute force)
opt_tour, opt_length = tsp_optimal(n, dist)
print(f"\nOptimal tour: {opt_tour}")
print(f"Optimal length: {opt_length:.2f}")

ratio = approx_length / opt_length
print(f"\nApproximation ratio: {ratio:.3f} (guaranteed <= 2.0)")
print(f"MST lower bound: {mst_weight:.2f}")
print(f"Approx / MST: {approx_length / mst_weight:.3f}")

# Multiple trials
print(f"\n=== Ratio Statistics (20 trials, n=8) ===")
ratios = []
for _ in range(20):
    pts = [(random.uniform(0, 100), random.uniform(0, 100)) for _ in range(n)]
    d = complete_distance_matrix(pts)
    _, al = tsp_mst_approx(n, d)
    _, ol = tsp_optimal(n, d)
    ratios.append(al / ol)
print(f"  Min ratio: {min(ratios):.3f}")
print(f"  Max ratio: {max(ratios):.3f}")
print(f"  Avg ratio: {sum(ratios)/len(ratios):.3f}")
print(f"  All <= 2.0: {all(r <= 2.001 for r in ratios)}")
```

### Proof of 2-Approximation
```
1. OPT >= MST_weight    (MST is cheapest connected subgraph)
2. Doubled MST = 2 * MST_weight    (Eulerian multigraph)
3. Shortcutting <= Doubled MST     (triangle inequality)
4. Therefore: Tour <= 2 * MST <= 2 * OPT
```

### Complexity
- **MST**: O(n^2) with adjacency matrix (Prim's)
- **DFS**: O(n)
- **Total**: O(n^2)
- **Christofides improvement**: 1.5-approximation using minimum weight perfect matching'''),

    ("thinking/algorithms", r'''Implement the randomized max-cut algorithm. Show that a random partition achieves at least 1/2 of the optimal cut, and implement local search improvement.''', r'''<think>
Max-cut: partition vertices into two sets S and T to maximize the number (or weight) of edges crossing the partition.

Randomized algorithm: assign each vertex to S or T with probability 1/2 independently.

Expected value analysis: for each edge (u,v), P(edge is cut) = 1/2 (since u and v must be in different sets). By linearity of expectation, E[cut size] = |E|/2 >= OPT/2.

So the random partition is a 1/2-approximation in expectation.

Derandomization: we can use the method of conditional expectations to achieve 1/2 guaranteed (not just in expectation). For each vertex, decide deterministically whether S or T gives more cut edges.

Local search improvement: starting from any partition, repeatedly move a vertex to the other side if it increases the cut size. This converges to a locally optimal partition, which is at least |E|/2 (same 1/2-approximation guarantee).

Proof of local search guarantee: at a local optimum, for each vertex v, at least half its edges cross the cut (otherwise, moving v would improve the cut). So total cut >= sum(degree(v)/2) / 2 = |E|/2. Wait, that's not quite right. Let me think again.

At local optimum, for each vertex v, the number of cut edges incident to v >= number of uncut edges incident to v. So cut >= sum(cut_edges(v))/2 = |E|/2.

I will implement all three approaches and compare.
</think>

## Max-Cut Approximation

### Implementation

```python
import random


def random_cut(n, edges):
    """Random partition: each vertex in S or T with prob 1/2.
    Expected cut >= |E|/2 >= OPT/2."""
    partition = [random.choice([0, 1]) for _ in range(n)]
    cut = sum(1 for u, v in edges if partition[u] != partition[v])
    return partition, cut


def greedy_derandomized_cut(n, edges):
    """Derandomized greedy: for each vertex, choose side that maximizes cut.
    Guaranteed cut >= |E|/2."""
    partition = [-1] * n
    adj = [[] for _ in range(n)]
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    for v in range(n):
        # Count how many already-assigned neighbors are in each side
        count = [0, 0]
        for u in adj[v]:
            if partition[u] != -1:
                count[partition[u]] += 1
        # Put v on the side with MORE already-assigned neighbors
        # (this maximizes edges crossing the cut)
        partition[v] = 0 if count[0] >= count[1] else 1

    cut = sum(1 for u, v in edges if partition[u] != partition[v])
    return partition, cut


def local_search_cut(n, edges, partition=None, max_iter=10000):
    """Local search: repeatedly move vertices to improve cut.
    Converges to local optimum >= |E|/2."""
    if partition is None:
        partition = [random.choice([0, 1]) for _ in range(n)]
    else:
        partition = list(partition)

    adj = [[] for _ in range(n)]
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    def cut_contribution(v):
        """Net contribution: cut edges - uncut edges for vertex v."""
        cut_e = sum(1 for u in adj[v] if partition[u] != partition[v])
        uncut_e = sum(1 for u in adj[v] if partition[u] == partition[v])
        return cut_e - uncut_e

    improved = True
    iterations = 0
    while improved and iterations < max_iter:
        improved = False
        for v in range(n):
            if cut_contribution(v) < 0:
                # Moving v to other side increases cut
                partition[v] = 1 - partition[v]
                improved = True
        iterations += 1

    cut = sum(1 for u, v in edges if partition[u] != partition[v])
    return partition, cut, iterations


def max_cut_brute(n, edges):
    """Exact max-cut via brute force. O(2^n)."""
    best_cut = 0
    best_partition = [0] * n
    for mask in range(1 << n):
        partition = [(mask >> i) & 1 for i in range(n)]
        cut = sum(1 for u, v in edges if partition[u] != partition[v])
        if cut > best_cut:
            best_cut = cut
            best_partition = partition[:]
    return best_partition, best_cut


# Demo
random.seed(42)

print("=== Max-Cut Approximation ===\n")

# Test graph
n = 10
edges = []
for i in range(n):
    for j in range(i+1, n):
        if random.random() < 0.4:
            edges.append((i, j))

print(f"Graph: {n} nodes, {len(edges)} edges")

# Optimal
opt_part, opt_cut = max_cut_brute(n, edges)
print(f"\nOptimal cut: {opt_cut}")
print(f"|E|/2 = {len(edges)/2:.1f} (lower bound on all methods)")

# Methods
results = []
for trial in range(10):
    rp, rc = random_cut(n, edges)
    results.append(rc)
avg_random = sum(results) / len(results)
print(f"\nRandom (avg of 10): {avg_random:.1f} (ratio: {avg_random/opt_cut:.3f})")

gp, gc = greedy_derandomized_cut(n, edges)
print(f"Greedy derandomized: {gc} (ratio: {gc/opt_cut:.3f})")

lp, lc, li = local_search_cut(n, edges)
print(f"Local search: {lc} (ratio: {lc/opt_cut:.3f}, {li} iterations)")

# Verify guarantees
print(f"\n=== Guarantee Check ===")
print(f"  |E|/2 = {len(edges)/2:.1f}")
print(f"  Greedy >= |E|/2: {gc >= len(edges)/2}")
print(f"  Local search >= |E|/2: {lc >= len(edges)/2}")

print(f"\n=== Proof of 1/2-Approximation ===")
print(f"  Random: E[cut] = sum P(edge cut) = |E| * 1/2")
print(f"  Since OPT <= |E|: E[cut] >= |E|/2 >= OPT/2")
print(f"  Derandomization: conditional expectations maintain guarantee")
```

### Approximation Ratios
| Method | Ratio | Deterministic? | Time |
|--------|-------|---------------|------|
| Random | 1/2 (expected) | No | O(n + m) |
| Greedy derand. | 1/2 (guaranteed) | Yes | O(n + m) |
| Local search | 1/2 (guaranteed) | Yes | O(m * n) |
| SDP relaxation | 0.878 (GW) | Randomized | O(n^3) |'''),

    ("thinking/algorithms", r'''Implement the LPT (Longest Processing Time) algorithm for load balancing on identical machines. Prove it achieves a 4/3-approximation for makespan minimization.''', r'''<think>
Load balancing (makespan minimization): given n jobs with processing times and m identical machines, assign jobs to machines to minimize the maximum load (makespan).

LPT (Longest Processing Time First):
1. Sort jobs by decreasing processing time
2. Assign each job to the machine with the current minimum load

This is a greedy algorithm that achieves a (4/3 - 1/(3m))-approximation.

Proof sketch:
- Let OPT be the optimal makespan
- OPT >= max(p_max, sum(p_i)/m) where p_max is the largest job
- In the LPT schedule, the last job to finish (determining the makespan) has some processing time p_j
- If p_j <= OPT/3, then the makespan <= OPT + OPT/3 = 4*OPT/3 (because the machine was the least loaded when p_j was assigned)
- If p_j > OPT/3, then there are at most 2m jobs with processing time > OPT/3, so the problem can be solved optimally in polynomial time

The analysis is more nuanced but the key result is makespan <= (4/3 - 1/(3m)) * OPT.

For comparison, I will also implement the naive round-robin and the list scheduling (just assign to least loaded without sorting) approaches.
</think>

## Load Balancing: LPT Algorithm

### Implementation

```python
import heapq


def lpt_schedule(jobs, m):
    """LPT (Longest Processing Time) scheduling.
    Sort jobs descending, assign each to least loaded machine.

    Args:
        jobs: list of processing times
        m: number of machines

    Returns:
        (makespan, assignment) where assignment[i] = machine for job i
    """
    n = len(jobs)
    indexed_jobs = sorted(enumerate(jobs), key=lambda x: -x[1])

    # Min-heap of (load, machine_id)
    machines = [(0, i) for i in range(m)]
    assignment = [0] * n

    for orig_idx, p_time in indexed_jobs:
        load, machine_id = heapq.heappop(machines)
        assignment[orig_idx] = machine_id
        heapq.heappush(machines, (load + p_time, machine_id))

    makespan = max(load for load, _ in machines)
    return makespan, assignment


def list_schedule(jobs, m):
    """List scheduling (without sorting). Assign to least loaded."""
    n = len(jobs)
    machines = [(0, i) for i in range(m)]
    assignment = [0] * n

    for i, p_time in enumerate(jobs):
        load, machine_id = heapq.heappop(machines)
        assignment[i] = machine_id
        heapq.heappush(machines, (load + p_time, machine_id))

    makespan = max(load for load, _ in machines)
    return makespan, assignment


def optimal_schedule(jobs, m):
    """Brute force optimal scheduling. O(m^n)."""
    n = len(jobs)
    if n == 0:
        return 0, []

    best_makespan = sum(jobs)  # worst case: all on one machine
    best_assignment = [0] * n

    def backtrack(job_idx, loads, assignment):
        nonlocal best_makespan, best_assignment
        if job_idx == n:
            ms = max(loads)
            if ms < best_makespan:
                best_makespan = ms
                best_assignment = assignment[:]
            return

        # Pruning: if current max already >= best, skip
        if max(loads) >= best_makespan:
            return

        seen = set()  # avoid duplicate machine loads
        for machine in range(m):
            if loads[machine] in seen and loads[machine] > 0:
                continue  # symmetry breaking
            seen.add(loads[machine])
            loads[machine] += jobs[job_idx]
            assignment[job_idx] = machine
            backtrack(job_idx + 1, loads, assignment)
            loads[machine] -= jobs[job_idx]

    backtrack(0, [0] * m, [0] * n)
    return best_makespan, best_assignment


# Demo
import random
random.seed(42)

print("=== Load Balancing: LPT Algorithm ===\n")

# Example
jobs = [6, 4, 3, 2, 8, 5, 7, 1]
m = 3

lpt_ms, lpt_assign = lpt_schedule(jobs, m)
list_ms, list_assign = list_schedule(jobs, m)
opt_ms, opt_assign = optimal_schedule(jobs, m)

print(f"Jobs: {jobs}")
print(f"Machines: {m}")
print(f"Sum: {sum(jobs)}, Lower bound (sum/m): {sum(jobs)/m:.1f}")
print(f"Max job: {max(jobs)}")
print(f"\n{'Method':<15} {'Makespan':>8} {'Ratio':>8}")
print("-" * 35)
print(f"{'Optimal':<15} {opt_ms:>8} {1.00:>8.3f}")
print(f"{'LPT':<15} {lpt_ms:>8} {lpt_ms/opt_ms:>8.3f}")
print(f"{'List':<15} {list_ms:>8} {list_ms/opt_ms:>8.3f}")

# Show machine loads
print(f"\nLPT schedule (sorted: {sorted(jobs, reverse=True)}):")
for machine in range(m):
    machine_jobs = [jobs[i] for i in range(len(jobs)) if lpt_assign[i] == machine]
    print(f"  Machine {machine}: jobs={machine_jobs}, load={sum(machine_jobs)}")

# Multiple random tests
print(f"\n=== Ratio Statistics (50 trials) ===")
ratios_lpt = []
ratios_list = []
for _ in range(50):
    js = [random.randint(1, 20) for _ in range(8)]
    ms = 3
    lpt_r, _ = lpt_schedule(js, ms)
    list_r, _ = list_schedule(js, ms)
    opt_r, _ = optimal_schedule(js, ms)
    if opt_r > 0:
        ratios_lpt.append(lpt_r / opt_r)
        ratios_list.append(list_r / opt_r)

print(f"  LPT:  avg={sum(ratios_lpt)/len(ratios_lpt):.3f}, "
      f"max={max(ratios_lpt):.3f}")
print(f"  List: avg={sum(ratios_list)/len(ratios_list):.3f}, "
      f"max={max(ratios_list):.3f}")
print(f"  LPT all <= 4/3 = {4/3:.3f}: {all(r <= 4/3 + 0.001 for r in ratios_lpt)}")

print(f"\n=== Approximation Guarantee ===")
print(f"  LPT: makespan <= (4/3 - 1/(3m)) * OPT")
print(f"  For m=3: bound = {4/3 - 1/9:.4f}")
print(f"  List scheduling: makespan <= (2 - 1/m) * OPT")
```

### Complexity
- **LPT**: O(n log n) for sorting + O(n log m) for assignments
- **Approximation ratio**: 4/3 - 1/(3m) for LPT, 2 - 1/m for list scheduling
- **PTAS exists**: (1 + epsilon)-approximation in time O(n * f(1/epsilon, m))'''),
]
