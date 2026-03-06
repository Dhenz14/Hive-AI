PAIRS = [
    ("thinking/algorithms", r'''Solve the Traveling Salesman Problem (TSP) using bitmask DP: given n cities and distances between them, find the shortest route that visits every city exactly once and returns to the starting city.''', r'''<think>
TSP -- the classic NP-hard problem. Brute force tries all n! permutations which is awful. But for small n we can do better with DP.

The key observation: if I have visited a subset S of cities and I am currently at city i, it does not matter in what ORDER I visited the cities in S. Only which cities I visited and where I am now. This is the optimal substructure that makes bitmask DP work.

So the state is dp[mask][i] = min cost to visit exactly the cities indicated by mask, ending at city i. The bitmask encodes which cities are in the visited set. With n cities we have 2^n subsets, and for each we track which of the n cities we are at, so n * 2^n states total.

Base case: dp[1 << 0][0] = 0 -- start at city 0, only city 0 visited.

Transition: from state (mask, i), try going to any unvisited city j. New state is (mask | (1 << j), j) with cost dp[mask][i] + dist[i][j].

Hmm, for the final answer, I need to return to the start. So the answer is min over all i of dp[full_mask][i] + dist[i][0].

Wait, could we fix the starting city? Yes -- since the tour is a cycle, fixing city 0 as the start loses no generality. This avoids an extra factor of n.

For path reconstruction, I need to track which city we came from for each state. That means storing parent[mask][i] = previous city.

One thing to watch: the space. n * 2^n entries. For n=20, that is 20 * 1M = 20M entries. Each stores a float and an int -- that is feasible but tight. For n=25, 25 * 33M = 800M entries -- probably too much for Python but doable in C++.

Practical limit is around n=20 in Python, maybe n=23-24 in C++ with careful optimization.
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
The assignment problem: n workers, n tasks, minimize total cost. The Hungarian algorithm does this in O(n^3), but for small n, bitmask DP gives a simpler O(n * 2^n) solution.

The state design is the interesting part. We could try dp[mask][i] like TSP, but actually we can do better. Since workers are processed in order 0, 1, 2, ..., the worker index is implicit -- it is just popcount(mask).

So dp[mask] = minimum cost to assign the tasks indicated by mask to workers 0 through popcount(mask)-1.

Base case: dp[0] = 0.

For the transition, I initially thought about it backwards: dp[mask] = min over j in mask of (dp[mask ^ (1 << j)] + cost[popcount(mask)-1][j]). This means we look at each task j in the current set, consider it as the assignment for the last worker, and take the best.

Hmm wait, it is actually cleaner to think forwards. Worker i = popcount(mask) is the next worker to assign. For each unassigned task j, try dp[mask | (1 << j)] = min(dp[mask | (1 << j)], dp[mask] + cost[i][j]).

Both formulations work. The forward approach avoids the popcount-1 indexing issue. Let me use that.

This is O(n * 2^n) because for each of 2^n masks, we try at most n tasks. Compared to the O(n!) brute force (trying all permutations), this is dramatically better for n >= 15. But for large n, the Hungarian O(n^3) wins. The crossover is around n = 15-18 depending on constants.

Space is just O(2^n) since we only need the dp array and parent tracking. Much cleaner than the n * 2^n space needed for TSP.
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
Hamiltonian Path: does a path exist that visits every vertex exactly once? NP-complete in general, but for small n we can use bitmask DP.

This is basically TSP but simpler -- we only need existence (boolean), not minimum cost, and there is no return to start.

State: dp[mask][v] = can we visit exactly the vertices in mask and end at v?

Base case: dp[1 << v][v] = True for every vertex v. We can start anywhere.

Transition: dp[mask][v] is True if there exists some u where dp[mask ^ (1 << v)][u] is True AND edge (u, v) exists. In other words, we had a valid path through mask-minus-v ending at u, and we can extend it to v.

Hmm, actually I need to be careful about direction here. For the forward formulation: from state (mask, u), try extending to unvisited neighbor v. Set dp[mask | (1 << v)][v] = True. This avoids the XOR and is cleaner.

Answer: any dp[full_mask][v] being True.

For Hamiltonian Cycle, I initially thought we need to try all starting vertices. But wait -- since it is a cycle, we can fix the start at vertex 0 without loss of generality. Then we just need dp[full_mask][v] = True AND edge(v, 0) exists for some v.

One subtlety for undirected graphs: starting from any vertex works for paths. For directed graphs, we genuinely need to try all starting vertices since the graph may not be strongly connected.

For path reconstruction, track parent[mask][v] = the predecessor u. Then walk backwards from the full mask.

Time: O(n^2 * 2^n), Space: O(n * 2^n). Practical for n <= 20, same as TSP.
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
Set Cover: given a universe of n elements and m subsets, find the minimum number (or minimum cost) of subsets that cover everything. NP-hard in general, but for small universe (n <= 20), we can use bitmask DP on the universe.

The state is dp[mask] = minimum cost to cover exactly the elements in mask. Each element is a bit in the mask.

Base case: dp[0] = 0.

Transition: for each mask, try adding each subset S_i. The new mask is mask | S_i (union of currently covered elements and the new subset). dp[new_mask] = min(dp[new_mask], dp[mask] + cost[i]).

Hmm, I initially wondered if the order of adding subsets matters here. It does not -- we are taking the minimum over all possible orderings, and since we try all masks from 0 to full, every possible combination is considered.

One concern: could we accidentally pick the same subset twice? Actually yes, nothing prevents that. But wait -- if costs are positive, using the same subset twice is never optimal (adding it the second time covers no new elements but costs extra). So this is fine for minimum cost. For unweighted case, same reasoning: adding a redundant subset increases the count, so the minimum will not choose it.

For reconstruction, track last_subset[mask] = which subset was last added to reach this mask. Then walk backwards: from full mask, look up the last subset, remove its bits, repeat.

Wait, the reconstruction is slightly tricky. When we remove the bits of the last subset, some of those bits might have been covered by earlier subsets too. But since we are walking the DP path backwards, mask & ~subset_mask gives us the state we came from. Let me verify: if we reached mask by adding subset i to some earlier state, then the earlier state had at least the bits in mask & ~subset_mask[i]. Actually, the earlier state is mask with subset i's NEW contributions removed... hmm, that is not simply mask ^ subset. It is dp[mask] was derived from dp[prev_mask] + cost[i] where prev_mask | subset[i] = mask. So prev_mask = mask & ~subset_mask[i]. Yes, that works because any bits in subset[i] that were already in prev_mask do not matter.

Time: O(m * 2^n). Space: O(2^n). We also get the weighted version for free by using costs instead of counting.
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
Counting valid subsets with constraints -- essentially counting independent sets of a given size in a conflict graph. For small n, bitmask enumeration is the way to go.

My first thought was to use a DP like dp[i][k] = number of valid subsets of size k considering items 0..i. But the issue is that we need to know WHICH items are selected to check compatibility, not just the count. So this DP does not capture enough state... unless the conflict graph has special structure (like only adjacent items conflict).

Hmm, actually for a general conflict graph, we really do need the full bitmask. So the approach is: enumerate all 2^n subsets, check each for validity, and group by popcount.

The validity check can be fast though. Precompute conflict_mask[i] = bitmask of all items incompatible with item i. Then a subset (mask) is invalid if any selected item i has (mask & conflict_mask[i]) != 0 -- meaning some conflict partner is also selected.

Wait, there is a subtle issue: when checking item i against conflict_mask[i], we would also find item i itself if we are not careful. But conflict_mask[i] should not include i itself (an item is not in conflict with itself), so this is fine.

We could also add items incrementally: process items 0 to n-1 and build valid subsets. When considering adding item i to an existing valid subset mask, just check (mask & conflict_mask[i]) == 0. But this does not really save work over just enumerating all 2^n masks.

For the weighted version (max weight independent set), same enumeration but track the best weight instead of counting. Still O(2^n * n) in the worst case.

For n up to 20-25, this is feasible. For larger n, we would need branch-and-bound or meet-in-the-middle (splitting into two halves of n/2 and combining).
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
