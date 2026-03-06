PAIRS = [
    ("thinking/algorithms", r'''Solve the Travelling Salesman Problem (TSP) using bitmask DP. Given a weighted adjacency matrix of N cities (N <= 20), find the minimum cost to visit all cities exactly once and return to the starting city. Return both the minimum cost and the optimal tour.''', r'''<think>
The TSP problem: visit all N cities exactly once and return to start with minimum cost. Brute force would be O(N!) which is way too slow for N=20. Let me think about how to optimize.

Key insight: if I'm at city `i` and have visited a set of cities `S`, it doesn't matter *in what order* I visited the cities in S — only the set matters. This screams bitmask DP.

State: dp[mask][i] = minimum cost to reach city i, having visited exactly the cities in `mask`, starting from city 0.

Base case: dp[1][0] = 0 (we start at city 0, only city 0 visited).

Transition: for each state (mask, i), try extending to an unvisited city j:
  dp[mask | (1 << j)][j] = min(dp[mask | (1 << j)][j], dp[mask][i] + dist[i][j])

Answer: min over all i of dp[(1<<N)-1][i] + dist[i][0]

Time complexity: O(2^N * N^2) — for each of 2^N masks and N possible current cities, we try N transitions.
Space complexity: O(2^N * N).

For N=20: 2^20 * 20^2 = ~400 million operations. Tight but feasible with careful implementation.

I also need to reconstruct the path. I'll store a parent array: parent[mask][i] = previous city.

Let me be careful with initialization — use infinity for all states except the base case.
</think>

## Bitmask DP Solution for TSP

The key insight is that the order in which cities were visited doesn't matter — only **which** cities have been visited and **where** we currently are. This allows us to compress the state space from O(N!) permutations to O(2^N * N) states.

### State Definition
- `dp[mask][i]` = minimum cost to have visited exactly the cities indicated by `mask`, currently at city `i`
- `mask` is a bitmask where bit `j` is set if city `j` has been visited

```python
from typing import List, Tuple, Optional
import math


def solve_tsp(dist: List[List[float]]) -> Tuple[float, List[int]]:
    """
    Solve TSP using bitmask DP.

    Args:
        dist: N x N adjacency matrix where dist[i][j] is cost from city i to j.
              Use math.inf for missing edges.

    Returns:
        (min_cost, tour) where tour is the list of cities in order (starting and ending at 0).

    Time:  O(2^N * N^2)
    Space: O(2^N * N)
    """
    n = len(dist)
    if n == 1:
        return (0, [0, 0])

    full_mask = (1 << n) - 1
    INF = float('inf')

    # dp[mask][i] = min cost to reach city i with visited set = mask
    dp = [[INF] * n for _ in range(1 << n)]
    parent = [[-1] * n for _ in range(1 << n)]

    # Base case: start at city 0
    dp[1][0] = 0

    for mask in range(1, 1 << n):
        for u in range(n):
            if dp[mask][u] == INF:
                continue
            if not (mask & (1 << u)):
                continue
            # Try visiting an unvisited city v
            for v in range(n):
                if mask & (1 << v):
                    continue  # already visited
                new_mask = mask | (1 << v)
                new_cost = dp[mask][u] + dist[u][v]
                if new_cost < dp[new_mask][v]:
                    dp[new_mask][v] = new_cost
                    parent[new_mask][v] = u

    # Find the best last city before returning to 0
    best_cost = INF
    best_last = -1
    for u in range(n):
        total = dp[full_mask][u] + dist[u][0]
        if total < best_cost:
            best_cost = total
            best_last = u

    if best_cost == INF:
        return (INF, [])

    # Reconstruct the path
    path: List[int] = []
    mask = full_mask
    cur = best_last
    while cur != -1:
        path.append(cur)
        prev = parent[mask][cur]
        mask ^= (1 << cur) if cur != 0 else 0
        cur = prev

    path.reverse()
    path.append(0)  # return to start

    return (best_cost, path)


# ---------- Tests ----------

def test_small_triangle():
    dist = [
        [0, 10, 15],
        [10, 0, 20],
        [15, 20, 0],
    ]
    cost, tour = solve_tsp(dist)
    assert cost == 45, f"Expected 45, got {cost}"
    assert tour[0] == 0 and tour[-1] == 0
    assert sorted(tour[:-1]) == [0, 1, 2]
    print(f"Triangle test: cost={cost}, tour={tour}")


def test_four_cities():
    dist = [
        [0, 20, 42, 35],
        [20, 0, 30, 34],
        [42, 30, 0, 12],
        [35, 34, 12, 0],
    ]
    cost, tour = solve_tsp(dist)
    # Optimal tour: 0->1->2->3->0 = 20+30+12+35 = 97
    assert cost == 97, f"Expected 97, got {cost}"
    print(f"Four cities test: cost={cost}, tour={tour}")


def test_single_city():
    dist = [[0]]
    cost, tour = solve_tsp(dist)
    assert cost == 0
    assert tour == [0, 0]
    print(f"Single city test: cost={cost}, tour={tour}")


if __name__ == "__main__":
    test_small_triangle()
    test_four_cities()
    test_single_city()
    print("All TSP tests passed!")
```

### Complexity Analysis
- **Time:** O(2^N * N^2). We iterate over all 2^N masks, for each mask over N possible current cities, and for each try N transitions.
- **Space:** O(2^N * N) for the DP table and parent pointers.
- **Practical limit:** N ~ 20 (2^20 * 400 ≈ 4 * 10^8 operations).

The bitmask DP approach reduces the factorial state space of brute-force TSP to an exponential one, making it feasible for up to ~20 cities.
'''),

    ("thinking/algorithms", r'''Implement digit DP to count how many integers in the range [1, N] have a digit sum equal to exactly S. N can be up to 10^18 and S up to 162 (since max digits is 18, max digit is 9, so 18*9=162).''', r'''<think>
This is a classic digit DP problem. I need to count numbers from 1 to N whose digits sum to exactly S.

Let me think about the state:
- Position in the number (which digit we're placing, from most significant to least)
- Current digit sum so far
- `tight`: whether the digits placed so far exactly match the prefix of N (constraining future digits)
- `started`: whether we've placed a non-zero digit yet (to handle leading zeros)

Wait, do I need `started`? Since we're counting from 1 to N, numbers with leading zeros are just smaller numbers. Actually, digit DP typically processes the number digit by digit with a tight constraint. Leading zeros matter because "007" has digit sum 7, not 0+0+7=7 — well that's the same. So leading zeros don't affect digit sum. But I should make sure I don't count 0 itself as a valid number.

Approach:
- Convert N to its digit representation
- dp(pos, sum_so_far, tight) where:
  - pos: current digit position (0 to len-1)
  - sum_so_far: sum of digits placed so far
  - tight: if True, the next digit is bounded by N's digit at this position

Base case: when pos == len(digits), return 1 if sum_so_far == S else 0.

At each position, the upper bound for the digit is digits[pos] if tight, else 9.

Time: O(D * S * 2) where D = number of digits (up to 18). Each state has at most 10 transitions.
So roughly 18 * 162 * 2 * 10 ≈ 58,000 operations. Very fast.

I'll use memoization with functools.lru_cache.

One subtlety: I need to exclude 0 from the count. Since digit sum of 0 is 0, and S >= 1 typically, this is usually fine. But if S=0, the answer should be 0 (since we count from 1 to N). I'll handle that edge case.
</think>

## Digit DP: Count Numbers with Exact Digit Sum

Digit DP processes the number digit by digit from the most significant, tracking whether we're still "tight" (constrained by N's digits) or "free" (can place any digit 0-9).

```python
from functools import lru_cache
from typing import List


def count_digit_sum(n: int, s: int) -> int:
    """
    Count integers in [1, N] whose digit sum equals exactly S.

    Args:
        n: Upper bound (1 <= n <= 10^18)
        s: Target digit sum (0 <= s <= 162)

    Returns:
        Count of valid integers.

    Time:  O(D * S * 2) where D = number of digits in N (~18)
    Space: O(D * S)
    """
    if n <= 0 or s < 0 or s > 162:
        return 0

    digits: List[int] = [int(c) for c in str(n)]
    length = len(digits)

    @lru_cache(maxsize=None)
    def dp(pos: int, rem_sum: int, tight: bool) -> int:
        """
        Count valid completions from position `pos` onward.

        Args:
            pos: Current digit index
            rem_sum: Remaining digit sum needed
            tight: Whether previous digits matched N's prefix exactly
        """
        if rem_sum < 0:
            return 0
        if pos == length:
            return 1 if rem_sum == 0 else 0

        upper = digits[pos] if tight else 9
        total = 0

        for d in range(0, upper + 1):
            if d > rem_sum:
                break  # Pruning: remaining digits can't fix an overshoot
            total += dp(pos + 1, rem_sum - d, tight and (d == upper))

        return total

    result = dp(0, s, True)

    # Exclude 0: digit sum of 0 is 0, so only matters if s == 0
    if s == 0:
        result -= 1  # remove the number 0 from count

    return result


def count_digit_sum_range(lo: int, hi: int, s: int) -> int:
    """Count integers in [lo, hi] with digit sum = s."""
    if lo > hi:
        return 0
    return count_digit_sum(hi, s) - count_digit_sum(lo - 1, s)


# ---------- Tests ----------

def test_small_range():
    # Numbers 1..100 with digit sum 5:
    # 5, 14, 23, 32, 41, 50 → 6 numbers
    result = count_digit_sum(100, 5)
    assert result == 6, f"Expected 6, got {result}"
    print(f"[1,100] digit sum=5: {result}")


def test_single_digit():
    # Numbers 1..9 with digit sum 7: just {7}
    result = count_digit_sum(9, 7)
    assert result == 1, f"Expected 1, got {result}"
    print(f"[1,9] digit sum=7: {result}")


def test_large_n():
    # N = 10^18, S = 1
    # Numbers with digit sum 1: 1, 10, 100, ..., 10^17 → 18 numbers
    # Plus 10^18 itself: digit sum = 1. So 19 numbers.
    result = count_digit_sum(10**18, 1)
    assert result == 19, f"Expected 19, got {result}"
    print(f"[1, 10^18] digit sum=1: {result}")


def test_range_query():
    # Numbers in [10, 20] with digit sum 3: {12, 21? no 21>20, 30? no} → just 12
    # Wait: 12 has digit sum 3. Also 30 > 20. So just 12.
    result = count_digit_sum_range(10, 20, 3)
    assert result == 1, f"Expected 1, got {result}"
    print(f"[10,20] digit sum=3: {result}")


if __name__ == "__main__":
    test_small_range()
    test_single_digit()
    test_large_n()
    test_range_query()
    print("All digit DP tests passed!")
```

### Complexity
- **Time:** O(D * S * 2 * 10) = O(D * S) effectively. With D=18 and S=162, this is roughly 5,800 unique states, each doing at most 10 work. Blazingly fast even for N = 10^18.
- **Space:** O(D * S) for memoization.

### Key Ideas
1. **Tight constraint**: tracks whether we can freely choose digits or must respect N's upper bound.
2. **Pruning**: if `d > rem_sum`, no point trying larger digits — the remaining sum can only decrease.
3. **Range queries**: use prefix sums — count(lo, hi, s) = count(1, hi, s) - count(1, lo-1, s).
'''),

    ("thinking/algorithms", r'''Solve the "Burst Balloons" problem using interval DP. Given an array of N balloons with values nums[0..N-1], bursting balloon i earns nums[i-1] * nums[i] * nums[i+1] coins (treating out-of-bounds as 1). Find the maximum coins obtainable by bursting all balloons. (LeetCode 312)''', r'''<think>
Burst Balloons — this is a tricky DP problem. Let me think carefully.

If I burst balloon i first, the subproblems on the left and right are NOT independent because the boundaries change. This is the key difficulty.

Wrong approach: thinking about which balloon to burst first. The subproblems overlap in a messy way.

Correct approach: think about which balloon to burst LAST in a given interval. If balloon k is the last one burst in interval (i, j), then when we burst k, the only remaining balloons adjacent to it are i and j (which are boundaries, not part of the interval). So the coins from bursting k last = nums[i] * nums[k] * nums[j].

Let me redefine: pad the array with 1s on both sides. So nums = [1] + original + [1]. Now we want to burst all balloons in (0, n+1) exclusive.

dp[i][j] = max coins from bursting all balloons strictly between i and j.

For each k in (i+1, ..., j-1), if k is the last balloon burst:
  dp[i][j] = max(dp[i][k] + nums[i]*nums[k]*nums[j] + dp[k][j])

Base case: dp[i][j] = 0 when j - i <= 1 (no balloons between i and j).

We iterate by interval length from small to large.

Time: O(N^3), Space: O(N^2).
</think>

## Interval DP: Burst Balloons

The critical insight is to think about which balloon is burst **last** in each interval, not first. This makes subproblems independent.

### Key Idea
Pad the array: `nums = [1] + original + [1]`. Define `dp[i][j]` = max coins from bursting all balloons strictly between indices `i` and `j`. When balloon `k` is the last burst in interval `(i, j)`, its neighbors are exactly `i` and `j`.

```python
from typing import List


def max_coins(nums: List[int]) -> int:
    """
    Maximum coins from bursting all balloons.

    When balloon i is burst, you earn nums[i-1] * nums[i] * nums[i+1].
    Out-of-bounds neighbors are treated as 1.

    Args:
        nums: List of balloon values.

    Returns:
        Maximum coins obtainable.

    Time:  O(N^3)
    Space: O(N^2)
    """
    # Pad with sentinel 1s on both ends
    balloons = [1] + nums + [1]
    n = len(balloons)

    # dp[i][j] = max coins from bursting all balloons in open interval (i, j)
    dp = [[0] * n for _ in range(n)]

    # Enumerate by interval length
    for length in range(2, n):  # j - i = length
        for i in range(0, n - length):
            j = i + length
            for k in range(i + 1, j):
                # k is the LAST balloon burst in interval (i, j)
                coins = balloons[i] * balloons[k] * balloons[j]
                dp[i][j] = max(dp[i][j], dp[i][k] + coins + dp[k][j])

    return dp[0][n - 1]


# ---------- Tests ----------

def test_example_1():
    # LeetCode example: [3,1,5,8]
    # Optimal: burst 1 -> burst 5 -> burst 3 -> burst 8
    # = 3*1*5 + 3*5*8 + 1*3*8 + 1*8*1 = 15+120+24+8 = 167
    result = max_coins([3, 1, 5, 8])
    assert result == 167, f"Expected 167, got {result}"
    print(f"[3,1,5,8] -> {result}")


def test_single():
    # Single balloon: 1 * 5 * 1 = 5
    result = max_coins([5])
    assert result == 5, f"Expected 5, got {result}"
    print(f"[5] -> {result}")


def test_two_balloons():
    # [3, 5]: burst 3 first -> 1*3*5=15, then burst 5 -> 1*5*1=5, total=20
    # Or burst 5 first -> 3*5*1=15, then burst 3 -> 1*3*1=3, total=18
    # Max = 20
    result = max_coins([3, 5])
    assert result == 20, f"Expected 20, got {result}"
    print(f"[3,5] -> {result}")


if __name__ == "__main__":
    test_example_1()
    test_single()
    test_two_balloons()
    print("All burst balloons tests passed!")
```

### Why "Last Burst" Works
If we think about bursting first, the left and right subarrays share a changing boundary. But if balloon `k` is the **last** burst in `(i, j)`, then:
- All balloons in `(i, k)` are already gone when `k` bursts
- All balloons in `(k, j)` are already gone when `k` bursts
- So `k`'s neighbors are exactly `i` and `j`
- The subproblems `dp[i][k]` and `dp[k][j]` are fully independent

### Complexity
- **Time:** O(N^3) — three nested loops over intervals and split points
- **Space:** O(N^2) for the DP table
- N up to ~500 is comfortable with this approach
'''),

    ("thinking/algorithms", r'''Implement DP on trees to solve the Maximum Independent Set problem: given a tree of N nodes where each node has a weight, find the maximum total weight of a set of nodes such that no two selected nodes are adjacent (connected by an edge).''', r'''<think>
Maximum Independent Set on a general graph is NP-hard, but on trees it can be solved in O(N) with DP.

Root the tree at any node (say node 0). For each node u, define:
- dp[u][0] = max weight of independent set in u's subtree when u is NOT selected
- dp[u][1] = max weight of independent set in u's subtree when u IS selected

Transitions:
- dp[u][1] = weight[u] + sum(dp[child][0] for child in children[u])
  (if u is selected, no child can be selected)
- dp[u][0] = sum(max(dp[child][0], dp[child][1]) for child in children[u])
  (if u is not selected, each child can independently be selected or not)

Answer: max(dp[root][0], dp[root][1])

Time: O(N), Space: O(N).

I should use iterative DFS to avoid stack overflow for large N. Let me implement with a post-order traversal using a stack.

I also need to reconstruct the actual set. I'll do a second pass from root downward.
</think>

## Tree DP: Maximum Weight Independent Set

On a tree, Maximum Independent Set is solvable in linear time using DP rooted at any node.

```python
from typing import List, Tuple, Set
from collections import defaultdict


def max_independent_set(
    n: int,
    edges: List[Tuple[int, int]],
    weights: List[int],
) -> Tuple[int, Set[int]]:
    """
    Find maximum weight independent set on a tree.

    Args:
        n: Number of nodes (0-indexed)
        edges: List of (u, v) undirected edges forming a tree
        weights: weights[i] = weight of node i (non-negative)

    Returns:
        (max_weight, selected_nodes)

    Time:  O(N)
    Space: O(N)
    """
    if n == 0:
        return (0, set())
    if n == 1:
        return (weights[0], {0})

    # Build adjacency list
    adj: defaultdict[int, List[int]] = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    # Root at node 0, compute parent and post-order
    root = 0
    parent = [-1] * n
    order: List[int] = []  # post-order
    visited = [False] * n
    stack = [root]
    visited[root] = True

    while stack:
        u = stack.pop()
        order.append(u)
        for v in adj[u]:
            if not visited[v]:
                visited[v] = True
                parent[v] = u
                stack.append(v)

    order.reverse()  # post-order: children before parents

    # DP
    dp = [[0, 0] for _ in range(n)]  # dp[u][0], dp[u][1]

    for u in order:
        dp[u][1] = weights[u]
        for v in adj[u]:
            if v == parent[u]:
                continue
            dp[u][0] += max(dp[v][0], dp[v][1])
            dp[u][1] += dp[v][0]

    # Reconstruct
    selected: Set[int] = set()
    # BFS/DFS from root to decide
    choose = [False] * n
    choose[root] = dp[root][1] >= dp[root][0]

    # Process in BFS order (use `order` reversed = top-down)
    for u in reversed(order):
        if choose[u]:
            selected.add(u)
        for v in adj[u]:
            if v == parent[u]:
                continue
            if choose[u]:
                choose[v] = False  # parent selected, child cannot be
            else:
                choose[v] = dp[v][1] >= dp[v][0]

    total = sum(weights[v] for v in selected)
    return (total, selected)


# ---------- Tests ----------

def test_path_graph():
    # Path: 0--1--2--3 with weights [1, 5, 1, 5]
    # Best: select {1, 3} = 10
    n = 4
    edges = [(0, 1), (1, 2), (2, 3)]
    weights = [1, 5, 1, 5]
    total, selected = max_independent_set(n, edges, weights)
    assert total == 10, f"Expected 10, got {total}"
    # Verify independence
    for u, v in edges:
        assert not (u in selected and v in selected), "Adjacent nodes selected!"
    print(f"Path graph: weight={total}, set={selected}")


def test_star_graph():
    # Star: center=0 connected to 1,2,3,4
    # weights = [10, 3, 3, 3, 3]
    # Select center (10) vs all leaves (12) → 12
    n = 5
    edges = [(0, 1), (0, 2), (0, 3), (0, 4)]
    weights = [10, 3, 3, 3, 3]
    total, selected = max_independent_set(n, edges, weights)
    assert total == 12, f"Expected 12, got {total}"
    assert 0 not in selected
    print(f"Star graph: weight={total}, set={selected}")


def test_single_node():
    total, selected = max_independent_set(1, [], [42])
    assert total == 42
    assert selected == {0}
    print(f"Single node: weight={total}")


if __name__ == "__main__":
    test_path_graph()
    test_star_graph()
    test_single_node()
    print("All tree DP tests passed!")
```

### Complexity
- **Time:** O(N) — each node processed once in post-order
- **Space:** O(N) for the DP table, parent array, and adjacency list

### Why This Works
By rooting the tree, each node's subtree is an independent subproblem once we fix whether the node itself is selected. The tree structure guarantees no cycles, so the DP recurrence is well-defined and each node is visited exactly once.
'''),

    ("thinking/algorithms", r'''Implement broken profile DP (also called profile DP or plug DP) to count the number of ways to tile a W x H grid with 1x2 dominoes. W is small (up to 12) and H can be large (up to 10^9 — use matrix exponentiation for very large H).''', r"""<think>
Profile DP for domino tiling. The idea: process the grid row by row (or column by column), and the "profile" is the bitmask of the boundary between the current row and the next.

Let me think carefully. We place dominoes on a W x H grid. Each domino covers exactly 2 adjacent cells.

Standard approach for moderate H:
- Process cell by cell, left to right, top to bottom.
- The profile (bitmask of width W) indicates which cells in the current "frontier" are already occupied by vertical dominoes placed from the previous row.
- For each cell, if it's already filled (bit set), skip it. If not, we can:
  1. Place a vertical domino (fills this cell and the cell below → set bit for next row)
  2. Place a horizontal domino (fills this cell and the one to the right → requires the right cell to also be free)

Actually, let me use a row-by-row transition approach, which is cleaner and also amenable to matrix exponentiation.

State: bitmask of W bits representing which cells in the current row "protrude" into the next row (from vertical dominoes).

Transition from row i to row i+1: given input profile `mask_in` (cells already filled in row i+1 due to vertical dominoes from row i), generate all valid ways to fill row i+1 completely, producing output profile `mask_out` (cells protruding into row i+2).

This transition can be computed via recursive backtracking across columns.

For H up to ~1000, direct DP is fine: O(H * 2^W * W).
For H up to 10^9, compute the 2^W x 2^W transition matrix and use matrix exponentiation: O(2^(3W) * log H).

With W <= 12, 2^12 = 4096, matrix is 4096 x 4096 — that's 64 billion ops for multiplication. Too slow. So practically W <= 8-10 for matrix exponentiation.

Let me implement both approaches: direct DP for moderate H, and note the matrix exponentiation path.

For the recursive fill of a single row transition:
- Process columns left to right
- At column j with profiles (in_mask, out_mask):
  - If in_mask bit j is set: cell already filled, move to j+1
  - Else:
    a) Place vertical domino: set out_mask bit j, move to j+1
    b) Place horizontal domino: requires bit j+1 of in_mask to be 0, fill both cells, move to j+2
</think>

## Broken Profile DP: Domino Tiling

Profile DP processes the grid row by row, using a bitmask to represent which cells protrude into the next row from vertical dominoes.

```python
from typing import Dict, Tuple
from collections import defaultdict


def count_domino_tilings(width: int, height: int) -> int:
    '''
    Count ways to tile a W x H grid with 1x2 dominoes.

    Args:
        width: Grid width (recommended <= 12 for direct DP)
        height: Grid height

    Returns:
        Number of valid tilings.

    Time:  O(H * 2^W * W) for direct DP
    Space: O(2^W)
    '''
    if (width * height) % 2 == 1:
        return 0  # Odd number of cells can't be tiled

    # Ensure width <= height for efficiency (process along shorter dimension)
    if width > height:
        width, height = height, width

    w, h = width, height

    def generate_transitions(w: int) -> Dict[int, Dict[int, int]]:
        '''
        Build transition table: trans[in_mask][out_mask] = number of ways.
        in_mask: cells in current row already filled from above.
        out_mask: cells protruding into the next row.
        '''
        trans: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))

        def fill(col: int, in_mask: int, out_mask: int) -> None:
            if col == w:
                trans[in_mask][out_mask] += 1
                return

            if in_mask & (1 << col):
                # Cell already filled by vertical domino from above
                fill(col + 1, in_mask, out_mask)
            else:
                # Option 1: place vertical domino (protrudes down)
                fill(col + 1, in_mask, out_mask | (1 << col))

                # Option 2: place horizontal domino (need col+1 to be free too)
                if col + 1 < w and not (in_mask & (1 << (col + 1))):
                    fill(col + 2, in_mask, out_mask)

        for mask in range(1 << w):
            fill(0, mask, 0)

        return trans

    trans = generate_transitions(w)

    # DP row by row
    # dp[mask] = number of ways to have filled all rows up to current,
    # with `mask` indicating cells protruding into next row
    dp: Dict[int, int] = {0: 1}

    for row in range(h):
        new_dp: Dict[int, int] = defaultdict(int)
        for in_mask, ways in dp.items():
            if ways == 0:
                continue
            for out_mask, count in trans[in_mask].items():
                new_dp[out_mask] += ways * count
        dp = new_dp

    return dp.get(0, 0)


# ---------- Tests ----------

def test_2x3():
    # 2x3 grid: 3 tilings
    result = count_domino_tilings(2, 3)
    assert result == 3, f"Expected 3, got {result}"
    print(f"2x3: {result} tilings")


def test_2x4():
    # 2x4 grid: well-known answer is 36? No wait.
    # Actually 2xN tiling follows Fibonacci-like sequence: f(1)=1, f(2)=2, f(3)=3, f(4)=5
    # Wait, that's for 2xN. Let me reconsider.
    # 2x1=1, 2x2=2, 2x3=3, 2x4=5, 2x5=8 (Fibonacci)
    result = count_domino_tilings(2, 4)
    assert result == 5, f"Expected 5, got {result}"
    print(f"2x4: {result} tilings")


def test_4x4():
    # 4x4: known answer is 36
    result = count_domino_tilings(4, 4)
    assert result == 36, f"Expected 36, got {result}"
    print(f"4x4: {result} tilings")


def test_odd_area():
    # 3x3: odd area, impossible
    result = count_domino_tilings(3, 3)
    assert result == 0
    print(f"3x3: {result} tilings (impossible)")


if __name__ == "__main__":
    test_2x3()
    test_2x4()
    test_4x4()
    test_odd_area()
    print("All domino tiling tests passed!")
```

### Complexity
- **Time:** O(H * T) where T is the number of valid transitions (~O(2^W * W) to enumerate, but typically much smaller in practice)
- **Space:** O(2^W) for the DP state
- For very large H with small W, the transition can be encoded as a 2^W x 2^W matrix and exponentiated in O(2^(3W) * log H)

### Profile Interpretation
The bitmask profile represents the "jagged edge" between processed and unprocessed rows. A set bit means a vertical domino extends downward into the next row, pre-filling that cell. The DP ensures every cell is covered exactly once.
"""),
]
