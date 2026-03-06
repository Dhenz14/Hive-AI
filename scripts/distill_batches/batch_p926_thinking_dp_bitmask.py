PAIRS = [
    ("thinking/algorithms", r'''Solve the Traveling Salesman Problem (TSP) using bitmask DP: given n cities and distances between them, find the shortest route that visits every city exactly once and returns to the starting city.''', r'''<think>
The TSP is NP-hard, but for small n (up to ~20), bitmask DP gives an O(n^2 * 2^n) solution, which is much better than the O(n!) brute force.

State: dp[mask][i] = minimum cost to visit exactly the cities in mask, ending at city i.

Base case: dp[1 << start][start] = 0 (start at city 0, only city 0 visited).

Transition: For each state (mask, i), try extending to an unvisited city j:
dp[mask | (1 << j)][j] = min(dp[mask | (1 << j)][j], dp[mask][i] + dist[i][j])
where bit j is not set in mask.

Final answer: min over all i of dp[(1 << n) - 1][i] + dist[i][start]
(visit all cities and return to start).

The bitmask encodes which cities have been visited. With n cities, there are 2^n possible subsets, and for each subset we track which city we are currently at.

To reconstruct the path, track the predecessor for each state.

Edge cases:
- n = 1: cost is 0 (trivially at start)
- n = 2: go and return
- Asymmetric distances (dist[i][j] != dist[j][i])
- Some edges missing (set dist to infinity)

Time: O(n^2 * 2^n)
Space: O(n * 2^n)
Practical limit: n ~ 20 (2^20 * 20^2 ~ 400M operations).
</think>

**TSP with Bitmask DP**

```python
def tsp_bitmask(dist):
    """
    Solve TSP using bitmask DP.

    Args:
        dist: n x n distance matrix
    Returns:
        (min_cost, path) where path is list of city indices
    """
    n = len(dist)
    INF = float('inf')
    full_mask = (1 << n) - 1

    # dp[mask][i] = min cost to visit cities in mask, ending at i
    dp = [[INF] * n for _ in range(1 << n)]
    parent = [[-1] * n for _ in range(1 << n)]

    # Start at city 0
    dp[1][0] = 0

    for mask in range(1, 1 << n):
        for u in range(n):
            if dp[mask][u] == INF:
                continue
            if not (mask & (1 << u)):
                continue

            # Try visiting unvisited city v
            for v in range(n):
                if mask & (1 << v):
                    continue  # already visited
                new_mask = mask | (1 << v)
                new_cost = dp[mask][u] + dist[u][v]
                if new_cost < dp[new_mask][v]:
                    dp[new_mask][v] = new_cost
                    parent[new_mask][v] = u

    # Find minimum cost tour (return to start)
    min_cost = INF
    last_city = -1
    for u in range(n):
        total = dp[full_mask][u] + dist[u][0]
        if total < min_cost:
            min_cost = total
            last_city = u

    # Reconstruct path
    path = []
    mask = full_mask
    city = last_city
    while city != -1:
        path.append(city)
        prev = parent[mask][city]
        mask ^= (1 << city)
        city = prev
    path.reverse()
    path.append(0)  # return to start

    return min_cost, path


# Example
dist = [
    [0, 10, 15, 20],
    [10, 0, 35, 25],
    [15, 35, 0, 30],
    [20, 25, 30, 0],
]

cost, path = tsp_bitmask(dist)
print(f"Distance matrix:")
for row in dist:
    print(f"  {row}")
print(f"\nMinimum TSP cost: {cost}")
print(f"Optimal tour: {' -> '.join(map(str, path))}")

# Verify cost
total = 0
for i in range(len(path) - 1):
    seg = dist[path[i]][path[i+1]]
    total += seg
    print(f"  {path[i]} -> {path[i+1]}: {seg}")
print(f"  Total: {total}")

# Larger example
import random
random.seed(42)
n = 8
dist2 = [[0]*n for _ in range(n)]
for i in range(n):
    for j in range(i+1, n):
        d = random.randint(1, 100)
        dist2[i][j] = dist2[j][i] = d

cost2, path2 = tsp_bitmask(dist2)
print(f"\n{n}-city TSP: cost={cost2}, tour={path2}")
```

**State Space Analysis:**
- Bitmask has 2^n states, each with n possible current cities
- Total states: n * 2^n
- Each state considers n transitions
- Total work: O(n^2 * 2^n)

**Complexity:**
- Time: O(n^2 * 2^n)
- Space: O(n * 2^n)
- Feasible for n <= 20 (about 20M states)'''),

    ("thinking/algorithms", r'''Solve the Assignment Problem using bitmask DP: given n workers and n tasks with a cost matrix, assign each worker exactly one task and each task exactly one worker to minimize total cost.''', r'''<think>
The assignment problem is a special case of bipartite matching with costs. While the Hungarian algorithm solves it in O(n^3), bitmask DP provides a clean O(n * 2^n) solution.

State: dp[mask] = minimum cost to assign tasks in mask to the first popcount(mask) workers.

The key insight: if mask has k bits set, it means we have assigned tasks (the set bits) to workers 0 through k-1.

Base case: dp[0] = 0 (no tasks assigned to zero workers).

Transition: For mask with k bits set, we are assigning to worker k.
For each bit j set in mask:
dp[mask] = min over j in mask of (dp[mask ^ (1 << j)] + cost[k][j])

where k = popcount(mask) - 1 (the current worker is the number of assigned workers minus 1, since we are completing the assignment of worker k).

Wait, let me reconsider. dp[mask] represents having assigned the tasks indicated by mask to workers 0, 1, ..., popcount(mask)-1.

For worker k (where k = popcount(mask) - 1), we assigned task j (some bit in mask).

Actually it is easier to think of it iteratively: process workers 0 to n-1. When processing worker i, we pick a task j from the remaining unassigned tasks.

dp[mask] = min cost when the set of assigned tasks is mask, having processed workers 0..popcount(mask)-1.

Transition: worker i = popcount(mask), for each unassigned task j (bit j not in mask):
dp[mask | (1 << j)] = min(dp[mask | (1 << j)], dp[mask] + cost[i][j])

Final answer: dp[(1 << n) - 1].

Time: O(n * 2^n) -- for each mask, we iterate over at most n unset bits.
Space: O(2^n).
</think>

**Assignment Problem -- Bitmask DP**

```python
def assignment_bitmask(cost):
    """
    Solve assignment problem using bitmask DP.

    Args:
        cost: n x n cost matrix where cost[i][j] = cost of worker i doing task j
    Returns:
        (min_cost, assignment) where assignment[i] = task assigned to worker i
    """
    n = len(cost)
    INF = float('inf')
    full = (1 << n) - 1

    dp = [INF] * (1 << n)
    parent = [-1] * (1 << n)
    dp[0] = 0

    for mask in range(full):
        if dp[mask] == INF:
            continue

        worker = bin(mask).count('1')  # which worker to assign next

        for task in range(n):
            if mask & (1 << task):
                continue  # task already assigned

            new_mask = mask | (1 << task)
            new_cost = dp[mask] + cost[worker][task]

            if new_cost < dp[new_mask]:
                dp[new_mask] = new_cost
                parent[new_mask] = task

    # Reconstruct assignment
    assignment = [0] * n
    mask = full
    for worker in range(n - 1, -1, -1):
        task = parent[mask]
        assignment[worker] = task
        mask ^= (1 << task)

    return dp[full], assignment


# Example
cost = [
    [9, 2, 7, 8],
    [6, 4, 3, 7],
    [5, 8, 1, 8],
    [7, 6, 9, 4],
]

min_cost, assignment = assignment_bitmask(cost)

print("Cost matrix:")
for i, row in enumerate(cost):
    print(f"  Worker {i}: {row}")

print(f"\nMinimum total cost: {min_cost}")
print("Assignment:")
total = 0
for worker, task in enumerate(assignment):
    c = cost[worker][task]
    total += c
    print(f"  Worker {worker} -> Task {task} (cost={c})")
print(f"  Total: {total}")

# Compare with brute force
from itertools import permutations

best_cost = INF
best_perm = None
for perm in permutations(range(len(cost))):
    c = sum(cost[i][perm[i]] for i in range(len(cost)))
    if c < best_cost:
        best_cost = c
        best_perm = perm

print(f"\nBrute force verification: cost={best_cost}, assignment={best_perm}")
print(f"Match: {min_cost == best_cost}")
```

**Why Bitmask DP Works Here:**
- Workers are processed in order 0, 1, 2, ..., n-1
- The bitmask tracks which tasks have been assigned so far
- popcount(mask) tells us which worker to assign next
- This avoids explicitly tracking which worker gets which task

**Complexity:**
- Time: O(n * 2^n) -- iterate over all masks, try all tasks
- Space: O(2^n)
- Better than brute force O(n!) for n >= 15
- Hungarian algorithm O(n^3) is better for large n'''),

    ("thinking/algorithms", r'''Solve the Hamiltonian Path problem using bitmask DP: determine if a Hamiltonian path exists in a given graph (a path that visits every vertex exactly once), and find the path if it exists.''', r'''<think>
The Hamiltonian Path problem asks whether there exists a path visiting every vertex exactly once. It is NP-complete, but bitmask DP solves it in O(n^2 * 2^n).

This is very similar to TSP but without the return edge and without optimizing cost -- we just need existence.

State: dp[mask][v] = True if there exists a path visiting exactly the vertices in mask, ending at vertex v.

Base case: dp[1 << v][v] = True for all v (path of length 0 starting at v).

Transition: dp[mask][v] = True if there exists some u such that:
1. dp[mask ^ (1 << v)][u] is True (path visiting mask minus v, ending at u)
2. There is an edge from u to v in the graph

Answer: True if any dp[(1 << n) - 1][v] is True for some v.

For Hamiltonian Cycle, additionally check that there is an edge from v back to the starting vertex.

To find the actual path, track predecessors.

Optimization: We can start from any vertex for undirected graphs. For directed graphs, we must try all possible starting vertices.

Time: O(n^2 * 2^n)
Space: O(n * 2^n)
Practical for n <= 20.
</think>

**Hamiltonian Path -- Bitmask DP**

```python
def hamiltonian_path(adj_matrix):
    """
    Find a Hamiltonian path using bitmask DP.

    Args:
        adj_matrix: n x n adjacency matrix (1 = edge exists)
    Returns:
        path as list of vertices, or None if no Hamiltonian path exists
    """
    n = len(adj_matrix)
    full = (1 << n) - 1

    # dp[mask][v] = True if path visiting vertices in mask can end at v
    dp = [[False] * n for _ in range(1 << n)]
    parent = [[-1] * n for _ in range(1 << n)]

    # Base case: single vertex paths
    for v in range(n):
        dp[1 << v][v] = True

    for mask in range(1, 1 << n):
        for v in range(n):
            if not dp[mask][v]:
                continue
            if not (mask & (1 << v)):
                continue

            # Extend path to unvisited neighbor u
            for u in range(n):
                if mask & (1 << u):
                    continue
                if not adj_matrix[v][u]:
                    continue

                new_mask = mask | (1 << u)
                if not dp[new_mask][u]:
                    dp[new_mask][u] = True
                    parent[new_mask][u] = v

    # Check if Hamiltonian path exists
    for v in range(n):
        if dp[full][v]:
            # Reconstruct path
            path = []
            mask = full
            node = v
            while node != -1:
                path.append(node)
                prev = parent[mask][node]
                mask ^= (1 << node)
                node = prev
            path.reverse()
            return path

    return None


def hamiltonian_cycle(adj_matrix):
    """Find Hamiltonian cycle (if exists)."""
    n = len(adj_matrix)
    full = (1 << n) - 1

    # Fix starting vertex as 0
    dp = [[False] * n for _ in range(1 << n)]
    parent = [[-1] * n for _ in range(1 << n)]
    dp[1][0] = True

    for mask in range(1, 1 << n):
        for v in range(n):
            if not dp[mask][v]:
                continue
            for u in range(n):
                if mask & (1 << u):
                    continue
                if adj_matrix[v][u]:
                    new_mask = mask | (1 << u)
                    if not dp[new_mask][u]:
                        dp[new_mask][u] = True
                        parent[new_mask][u] = v

    # Check for cycle back to 0
    for v in range(1, n):
        if dp[full][v] and adj_matrix[v][0]:
            path = []
            mask = full
            node = v
            while node != -1:
                path.append(node)
                prev = parent[mask][node]
                mask ^= (1 << node)
                node = prev
            path.reverse()
            path.append(0)
            return path

    return None


# Example 1: Graph with Hamiltonian path
adj1 = [
    [0, 1, 0, 1, 0],
    [1, 0, 1, 1, 1],
    [0, 1, 0, 0, 1],
    [1, 1, 0, 0, 1],
    [0, 1, 1, 1, 0],
]

path = hamiltonian_path(adj1)
print(f"Graph 1 - Hamiltonian path: {path}")
if path:
    for i in range(len(path) - 1):
        assert adj1[path[i]][path[i+1]], f"Invalid edge {path[i]}-{path[i+1]}"
    print("  Path verified!")

cycle = hamiltonian_cycle(adj1)
print(f"Hamiltonian cycle: {cycle}")

# Example 2: Graph without Hamiltonian path
adj2 = [
    [0, 1, 0, 0],
    [1, 0, 0, 0],
    [0, 0, 0, 1],
    [0, 0, 1, 0],
]
path2 = hamiltonian_path(adj2)
print(f"\nGraph 2 (disconnected) - Hamiltonian path: {path2}")

# Example 3: Complete graph
n = 6
adj3 = [[1 if i != j else 0 for j in range(n)] for i in range(n)]
path3 = hamiltonian_path(adj3)
print(f"\nComplete K{n} - Hamiltonian path: {path3}")
```

**Complexity:**
- Time: O(n^2 * 2^n)
- Space: O(n * 2^n)
- Practical for n <= 20

**Hamiltonian Path vs Cycle:**
- Path: dp allows starting from any vertex
- Cycle: fix start vertex (say 0), check if end vertex has edge back to 0'''),

    ("thinking/algorithms", r'''Solve the Set Cover problem using bitmask DP: given a universe of n elements and a collection of subsets, find the minimum number of subsets whose union equals the universe.''', r'''<think>
The Set Cover problem is NP-hard, but for small universe size (up to ~20), bitmask DP gives an exact solution.

State: dp[mask] = minimum number of subsets needed to cover exactly the elements in mask.

Base case: dp[0] = 0 (empty set, no subsets needed).

Transition: For each mask and each subset S_i:
dp[mask | S_i] = min(dp[mask | S_i], dp[mask] + 1)

where S_i is represented as a bitmask of which elements it contains.

But this is O(2^n * m) where m is the number of subsets. We can optimize by only considering subsets that add at least one new element.

Final answer: dp[(1 << n) - 1].

To reconstruct which subsets were chosen, track the last subset used for each state.

Alternative formulation: dp[mask] = min subsets to cover mask.
For each mask, try adding each subset:
  new_mask = mask | subset_mask
  dp[new_mask] = min(dp[new_mask], dp[mask] + 1)

This is straightforward. The key is that we iterate over all 2^n masks and for each, try all m subsets.

We can also include costs (weighted set cover) by changing dp[mask] to track minimum cost instead of minimum count.

Time: O(m * 2^n), Space: O(2^n).
</think>

**Set Cover -- Bitmask DP**

```python
def set_cover_bitmask(universe_size, subsets, costs=None):
    """
    Find minimum-cost set cover using bitmask DP.

    Args:
        universe_size: number of elements (0 to n-1)
        subsets: list of sets, each a set/list of element indices
        costs: list of costs per subset (default: all 1 for min-count)
    Returns:
        (min_cost, chosen_subset_indices)
    """
    n = universe_size
    m = len(subsets)
    full = (1 << n) - 1
    INF = float('inf')

    if costs is None:
        costs = [1] * m

    # Convert subsets to bitmasks
    sub_masks = []
    for s in subsets:
        mask = 0
        for elem in s:
            mask |= (1 << elem)
        sub_masks.append(mask)

    dp = [INF] * (1 << n)
    last_subset = [-1] * (1 << n)
    dp[0] = 0

    for mask in range(full + 1):
        if dp[mask] == INF:
            continue

        for i in range(m):
            new_mask = mask | sub_masks[i]
            new_cost = dp[mask] + costs[i]

            if new_cost < dp[new_mask]:
                dp[new_mask] = new_cost
                last_subset[new_mask] = i

    if dp[full] == INF:
        return None, []

    # Reconstruct solution
    chosen = []
    mask = full
    while mask != 0:
        i = last_subset[mask]
        chosen.append(i)
        # Remove elements covered by subset i
        mask = mask & ~sub_masks[i]
        # Find the mask we came from
        # We need to find the exact predecessor
        # Actually, just remove the bits this subset contributed
        # mask now has those bits cleared

    chosen.reverse()
    return dp[full], chosen


def set_cover_greedy(universe_size, subsets, costs=None):
    """Greedy approximation for comparison."""
    n = universe_size
    m = len(subsets)
    if costs is None:
        costs = [1] * m

    uncovered = (1 << n) - 1
    chosen = []
    total_cost = 0

    sub_masks = []
    for s in subsets:
        mask = 0
        for elem in s:
            mask |= (1 << elem)
        sub_masks.append(mask)

    while uncovered:
        # Pick subset with best cost-effectiveness
        best_ratio = float('inf')
        best_idx = -1
        for i in range(m):
            new_covered = bin(uncovered & sub_masks[i]).count('1')
            if new_covered > 0:
                ratio = costs[i] / new_covered
                if ratio < best_ratio:
                    best_ratio = ratio
                    best_idx = i

        if best_idx == -1:
            return None, []

        chosen.append(best_idx)
        total_cost += costs[best_idx]
        uncovered &= ~sub_masks[best_idx]

    return total_cost, chosen


# Example
universe = 6  # elements 0-5
subsets = [
    {0, 1, 2},     # S0
    {2, 3, 4},     # S1
    {4, 5},         # S2
    {0, 3, 5},     # S3
    {1, 2, 4, 5},  # S4
]
costs = [3, 2, 1, 4, 5]

opt_cost, opt_chosen = set_cover_bitmask(universe, subsets, costs)
greedy_cost, greedy_chosen = set_cover_greedy(universe, subsets, costs)

print(f"Universe: {{0..{universe-1}}}")
print(f"Subsets: {[list(s) for s in subsets]}")
print(f"Costs: {costs}")

print(f"\nOptimal (bitmask DP):")
print(f"  Cost: {opt_cost}")
print(f"  Subsets chosen: {opt_chosen}")
covered = set()
for i in opt_chosen:
    covered |= subsets[i]
    print(f"    S{i}={list(subsets[i])} cost={costs[i]}")
print(f"  Covered: {sorted(covered)}")

print(f"\nGreedy approximation:")
print(f"  Cost: {greedy_cost}")
print(f"  Subsets: {greedy_chosen}")
```

**Greedy vs Exact:**
- Greedy: O(m * n) time, gives H(n)-approximation (harmonic number)
- Bitmask DP: O(m * 2^n) time, gives exact optimal solution
- Use bitmask DP when n <= 20, greedy when n is large

**Complexity:**
- Time: O(m * 2^n) where m = number of subsets, n = universe size
- Space: O(2^n)'''),

    ("thinking/algorithms", r'''Implement counting subsets with constraints using bitmask DP: given a set of n items with compatibility constraints (some items cannot be in the same subset), count the number of valid subsets of exactly k items.''', r'''<think>
This is a bitmask DP problem where we count subsets satisfying constraints. A common formulation: given a conflict graph (edges indicate incompatible pairs), count independent sets of size k.

Approach 1: Iterate over all 2^n subsets, check validity and size. O(2^n * n).

Approach 2: Profile DP -- process items one by one, maintaining which items are selected. But with constraints, we need the full bitmask.

Approach 3: DP with bitmask + popcount filtering.

For the general problem, I will implement:
1. Count valid subsets of each size (subsets where no two conflicting items coexist)
2. Use dp[mask] = True/False for validity, then group by popcount

For better efficiency with the "exactly k" constraint:
dp[i][k] where i is the current item being considered and k is items chosen so far, but we also need to track which items are chosen (for constraint checking). This brings us back to bitmasks.

Alternative formulation: dp[mask] = 1 if mask is a valid (independent) subset, 0 otherwise.
Answer for size k = sum of dp[mask] for all mask with popcount(mask) == k.

We can compute this incrementally:
- Process items 0 to n-1
- dp[mask] = 1 if mask forms an independent set
- When adding item i to mask, check that i has no conflicts with existing items in mask

Optimization: precompute for each item i, a conflict mask (bitmask of items conflicting with i). Item i can be added to mask if (mask & conflict[i]) == 0.

Time: O(2^n), Space: O(2^n).
</think>

**Counting Valid Subsets with Constraints -- Bitmask DP**

```python
def count_valid_subsets(n, conflicts, target_size=None):
    """
    Count subsets where no two conflicting items coexist.

    Args:
        n: number of items
        conflicts: list of (i, j) pairs indicating incompatible items
        target_size: if specified, only count subsets of this exact size
    Returns:
        count (or dict of size -> count if target_size is None)
    """
    # Build conflict masks
    conflict_mask = [0] * n
    for i, j in conflicts:
        conflict_mask[i] |= (1 << j)
        conflict_mask[j] |= (1 << i)

    # Enumerate valid subsets
    count_by_size = [0] * (n + 1)

    for mask in range(1 << n):
        valid = True
        for i in range(n):
            if mask & (1 << i):
                # Check if any conflict partner is also in mask
                if mask & conflict_mask[i]:
                    valid = False
                    break
        if valid:
            size = bin(mask).count('1')
            count_by_size[size] += 1

    if target_size is not None:
        return count_by_size[target_size]
    return count_by_size


def count_valid_subsets_fast(n, conflicts, target_size):
    """
    Optimized version: DP processing items one by one.
    dp[mask] = 1 if mask is valid independent set.
    """
    conflict_mask = [0] * n
    for i, j in conflicts:
        conflict_mask[i] |= (1 << j)
        conflict_mask[j] |= (1 << i)

    # dp[k] = set of valid masks with exactly k items
    # Use rolling approach
    # Actually, for counting, just check validity per mask
    count = 0
    for mask in range(1 << n):
        if bin(mask).count('1') != target_size:
            continue
        valid = True
        for i in range(n):
            if (mask & (1 << i)) and (mask & conflict_mask[i]):
                valid = False
                break
        if valid:
            count += 1
    return count


def max_weight_independent_set(n, conflicts, weights):
    """
    Find maximum weight subset with no conflicts (bitmask DP).
    """
    conflict_mask = [0] * n
    for i, j in conflicts:
        conflict_mask[i] |= (1 << j)
        conflict_mask[j] |= (1 << i)

    best_weight = 0
    best_mask = 0

    for mask in range(1 << n):
        valid = True
        weight = 0
        for i in range(n):
            if mask & (1 << i):
                if mask & conflict_mask[i]:
                    valid = False
                    break
                weight += weights[i]
        if valid and weight > best_weight:
            best_weight = weight
            best_mask = mask

    items = [i for i in range(n) if best_mask & (1 << i)]
    return best_weight, items


# Example: Team selection with conflicts
n = 6
conflicts = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]  # path graph
# This is like coloring a path -- independent sets on a path

counts = count_valid_subsets(n, conflicts)
print(f"Items: 0..{n-1}")
print(f"Conflicts: {conflicts}")
print(f"\nValid subsets by size:")
for k, c in enumerate(counts):
    print(f"  Size {k}: {c} subsets")
print(f"  Total valid subsets: {sum(counts)}")

# Weighted version
weights = [10, 30, 20, 40, 15, 25]
best_w, best_items = max_weight_independent_set(n, conflicts, weights)
print(f"\nWeights: {weights}")
print(f"Max weight independent set: {best_items} (weight={best_w})")

# Verify: check no conflicts in solution
for i in best_items:
    for j in best_items:
        assert (i, j) not in conflicts and (j, i) not in conflicts

# Example: Graph coloring constraint
print("\nAll valid subsets of size 3:")
size3 = count_valid_subsets(n, conflicts, target_size=3)
print(f"  Count: {size3}")

# List them
for mask in range(1 << n):
    if bin(mask).count('1') != 3:
        continue
    items = [i for i in range(n) if mask & (1 << i)]
    valid = all((a, b) not in conflicts and (b, a) not in conflicts
                for a in items for b in items if a < b)
    if valid:
        print(f"  {items}")
```

**Applications:**
- Team formation with incompatibility constraints
- Independent set problems on small graphs
- Graph coloring (assign colors = choose independent sets)
- Scheduling with exclusion constraints

**Complexity:**
- Brute force enumeration: O(2^n * n) to check all subsets
- Practical for n <= 20-25
- For larger n, use branch-and-bound or approximation algorithms'''),
]
