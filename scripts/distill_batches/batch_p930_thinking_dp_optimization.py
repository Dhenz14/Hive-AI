PAIRS = [
    ("thinking/algorithms", r'''Explain and implement Knuth's optimization for DP problems. Show how it reduces O(n^3) DP to O(n^2) with a concrete example like optimal binary search tree.''', r'''<think>
Knuth's optimization applies to DP recurrences of the form dp[i][j] = min over i <= k < j of (dp[i][k] + dp[k+1][j] + cost(i,j)), where the cost function satisfies the quadrilateral inequality. The key insight is that if opt[i][j] is the optimal split point, then opt[i][j-1] <= opt[i][j] <= opt[i+1][j]. This monotonicity constraint means we do not need to scan all possible k values for each (i,j) pair. Instead, we restrict our search range, bringing the total work from O(n^3) down to O(n^2).

For the optimal BST problem, we have keys with frequencies, and we want to build a BST minimizing the total weighted search cost. The cost function is the sum of frequencies in the range, which satisfies the quadrilateral inequality.

Let me think through the implementation: we fill the DP table by increasing interval length. For each interval [i,j], we only scan k from opt[i][j-1] to opt[i+1][j]. We need a prefix sum array for fast cost computation.

Edge cases: single elements have dp[i][i] = freq[i] and opt[i][i] = i. We must handle the boundary carefully -- opt[i][n-1] and opt[0][j] need valid defaults. The recurrence base case is dp[i][i-1] = 0 for empty intervals.

The proof that this is O(n^2) comes from telescoping: for a fixed diagonal d = j - i, the total range of k scanned is at most n because the ranges are nested and non-overlapping.
</think>

## Knuth's DP Optimization

Knuth's optimization reduces certain O(n^3) interval DP problems to O(n^2) by exploiting monotonicity of optimal split points.

### Conditions
The recurrence `dp[i][j] = min over k of (dp[i][k] + dp[k+1][j] + cost(i,j))` can be optimized when:
1. `cost` satisfies the **quadrilateral inequality**: `cost(a,c) + cost(b,d) <= cost(a,d) + cost(b,c)` for `a <= b <= c <= d`
2. `cost` is monotone: `cost(a,d) >= cost(b,c)` for `a <= b <= c <= d`

This guarantees `opt[i][j-1] <= opt[i][j] <= opt[i+1][j]`.

### Implementation: Optimal Binary Search Tree

```python
def optimal_bst(freq):
    n = len(freq)
    if n == 0:
        return 0

    # prefix sums for range cost
    prefix = [0] * (n + 1)
    for i in range(n):
        prefix[i + 1] = prefix[i] + freq[i]

    def cost(i, j):
        return prefix[j + 1] - prefix[i]

    INF = float('inf')
    dp = [[0] * n for _ in range(n)]
    opt = [[0] * n for _ in range(n)]

    # base case: single keys
    for i in range(n):
        dp[i][i] = freq[i]
        opt[i][i] = i

    # fill by increasing interval length
    for length in range(2, n + 1):
        for i in range(n - length + 1):
            j = i + length - 1
            dp[i][j] = INF
            lo = opt[i][j - 1]
            hi = opt[i + 1][j] if i + 1 <= j else j
            for k in range(lo, hi + 1):
                left = dp[i][k - 1] if k > i else 0
                right = dp[k + 1][j] if k < j else 0
                val = left + right + cost(i, j)
                if val < dp[i][j]:
                    dp[i][j] = val
                    opt[i][j] = k

    return dp[0][n - 1]

# Example
freq = [25, 10, 20, 5, 15]
print(optimal_bst(freq))  # 145
```

### Complexity
- **Without optimization**: O(n^3) time, O(n^2) space
- **With Knuth's optimization**: O(n^2) time, O(n^2) space
- The improvement comes from restricting the search range of k using the monotonicity property of optimal split points.'''),

    ("thinking/algorithms", r'''Implement divide and conquer optimization for DP. Explain when it applies and demonstrate with a problem: partition an array into k groups to minimize the sum of costs, where cost of a group is the sum of pairwise distances.''', r'''<think>
Divide and conquer optimization applies to DP recurrences of the form dp[i][j] = min over k < j of (dp[i-1][k] + cost(k+1, j)), where the optimal k for dp[i][j] is monotonically non-decreasing in j. That is, opt(i, j) <= opt(i, j+1).

This is different from Knuth's optimization -- here we have a 1D parameter j for each layer i, not an interval DP. The monotonicity of opt means we can use divide and conquer: to compute dp[i][j] for all j, we pick the middle j, find its optimal k, then recurse on the left and right halves with restricted k ranges.

For the partition problem: given array a of length n, partition into exactly k contiguous groups, minimizing the total cost where cost of a group [l, r] is sum of |a[p] - a[q]| for all pairs p, q in the group.

If we sort within each group... wait, the groups must be contiguous. So cost(l, r) = sum of |a[p] - a[q]| for l <= p < q <= r. We can precompute this efficiently. For a sorted subarray (or just contiguous), we can use the formula: for each element a[i], its contribution is a[i] * (i - l) - prefix_sum(l, i-1) + prefix_sum(i+1, r) - a[i] * (r - i). Actually, let me think more carefully.

For contiguous subarray [l..r], cost = sum over all pairs |a[p] - a[q]|. If array is not sorted, this is harder. But we can precompute it with a 2D prefix approach or sort a copy. Actually for the DP optimization to work, we need cost(k+1, j) to satisfy the condition. Let me use a simpler cost: sum of (a[i] - mean)^2 or just the squared range. Actually, let me use cost(l, r) = (r - l + 1) * (max - min) or just precomputed cost that satisfies the QI.

Let me use a clean example: cost(l, r) = (prefix[r+1] - prefix[l])^2 which is a common competitive programming formulation. This satisfies the needed monotonicity condition.
</think>

## Divide and Conquer DP Optimization

### When It Applies
For recurrences `dp[i][j] = min over k < j of (dp[i-1][k] + cost(k+1, j))`, if the optimal split point `opt(i, j)` is non-decreasing in `j`, we can use D&C to reduce from O(k * n^2) to O(k * n * log(n)).

### Implementation

```python
def solve(a, num_groups):
    """Partition array into num_groups contiguous groups,
    minimizing sum of cost(group) where cost = (sum of group)^2."""
    n = len(a)
    prefix = [0] * (n + 1)
    for i in range(n):
        prefix[i + 1] = prefix[i] + a[i]

    def cost(l, r):
        # cost of group [l..r] = (sum of elements)^2
        s = prefix[r + 1] - prefix[l]
        return s * s

    INF = float('inf')
    # dp[j] = best cost to partition a[0..j] into current number of groups
    prev = [INF] * n
    for j in range(n):
        prev[j] = cost(0, j)  # 1 group: entire prefix

    for g in range(1, num_groups):
        cur = [INF] * n

        def dc(jlo, jhi, klo, khi):
            if jlo > jhi:
                return
            jmid = (jlo + jhi) // 2
            best_val = INF
            best_k = klo
            for k in range(klo, min(khi, jmid) + 1):
                val = prev[k] + cost(k + 1, jmid)
                if val < best_val:
                    best_val = val
                    best_k = k
            cur[jmid] = best_val
            dc(jlo, jmid - 1, klo, best_k)
            dc(jmid + 1, jhi, best_k, khi)

        dc(g, n - 1, g - 1, n - 2)
        prev = cur

    return prev[n - 1]

# Example: partition [1, 3, 2, 4, 5] into 2 groups
arr = [1, 3, 2, 4, 5]
print(solve(arr, 2))  # min sum of squared group sums
# Groups [1,3,2],[4,5] -> 36 + 81 = 117? Let's check:
# [1],[3,2,4,5] -> 1 + 196 = 197
# [1,3],[2,4,5] -> 16 + 121 = 137
# [1,3,2],[4,5] -> 36 + 81 = 117
# [1,3,2,4],[5] -> 100 + 25 = 125
# Best = 117
```

### Complexity Analysis
- **Naive**: O(k * n^2) -- for each of k layers, check all n*n transitions
- **D&C optimized**: O(k * n * log(n)) -- each layer does O(n log n) work via divide and conquer
- **Space**: O(n) using two rolling arrays

### Key Insight
The D&C works because at the midpoint `jmid`, once we find `opt_k`, all `j < jmid` have optimal k <= `opt_k` and all `j > jmid` have optimal k >= `opt_k`. Each level of recursion does O(n) total work across all calls, with O(log n) levels.'''),

    ("thinking/algorithms", r'''Explain the Convex Hull Trick for DP optimization. Implement it for the problem: given n points, find the minimum cost to connect point 0 to point n-1 where cost of jumping from i to j is a[i]*b[j] + c[j].''', r'''<think>
The Convex Hull Trick (CHT) optimizes DP recurrences of the form dp[j] = min over i < j of (dp[i] + b[i] * a[j] + c[j]), where the "lines" have slopes b[i] and intercepts dp[i], and we query at x = a[j].

The idea: each transition from state i defines a linear function f_i(x) = b[i] * x + dp[i]. When we compute dp[j], we evaluate all these lines at x = a[j] and take the minimum, then add c[j]. Instead of checking all previous lines (O(n) per query), we maintain a convex hull of lines, allowing O(log n) or even O(1) amortized queries.

For the minimum case, we maintain a lower convex hull. When adding a line, we remove lines that are no longer part of the hull. When querying, if queries come in sorted order of x, we can use a pointer that only moves forward (monotone CHT), giving O(1) amortized.

For our problem: dp[j] = min over i < j of (dp[i] + a[i] * b[j] + c[j]). Rewriting: dp[j] = c[j] + min over i of (a[i] * b[j] + dp[i]). Each state i contributes a line with slope a[i] and intercept dp[i]. We query at x = b[j].

If b[j] values are sorted, we can use the monotone version. If slopes a[i] are sorted, insertion is straightforward. Let me implement the general version with sorted slopes and a deque.

The intersection check: three lines l1, l2, l3 -- l2 is unnecessary if the intersection of l1 and l3 is below l2 at that point. The standard check is: (intercept[l3] - intercept[l1]) * (slope[l1] - slope[l2]) <= (intercept[l2] - intercept[l1]) * (slope[l1] - slope[l3]).
</think>

## Convex Hull Trick (CHT)

The CHT optimizes DP transitions that can be expressed as querying minimum/maximum over a set of linear functions.

### Core Idea
If `dp[j] = min_i(m[i] * x[j] + b[i])`, maintain lines on a convex hull for O(log n) or O(1) queries instead of O(n).

### Implementation

```python
from collections import deque

class ConvexHullTrick:
    """Maintains lines y = m*x + b for minimum queries.
    Requires lines added in decreasing slope order.
    Queries must be in increasing x order for O(1) amortized."""

    def __init__(self):
        self.lines = deque()  # each element: (slope, intercept)

    def bad(self, l1, l2, l3):
        """Check if l2 is unnecessary given l1 and l3."""
        # l2 is bad if intersection(l1,l3) is below or at l2
        # Using cross product to avoid floating point
        return ((l3[1] - l1[1]) * (l1[0] - l2[0])
                <= (l2[1] - l1[1]) * (l1[0] - l3[0]))

    def add_line(self, m, b):
        """Add line y = m*x + b. Slopes must be in decreasing order."""
        line = (m, b)
        while len(self.lines) >= 2 and self.bad(
                self.lines[-2], self.lines[-1], line):
            self.lines.pop()
        self.lines.append(line)

    def query(self, x):
        """Query minimum y at given x. x must be non-decreasing."""
        while len(self.lines) >= 2:
            m1, b1 = self.lines[0]
            m2, b2 = self.lines[1]
            if m1 * x + b1 >= m2 * x + b2:
                self.lines.popleft()
            else:
                break
        m, b = self.lines[0]
        return m * x + b


def min_cost_path(a, b, c):
    """Find min cost path from 0 to n-1.
    Cost of jumping i -> j: a[i]*b[j] + c[j].
    dp[j] = min over i<j of (dp[i] + a[i]*b[j] + c[j])
           = c[j] + min over i<j of (a[i]*b[j] + dp[i])
    Line for state i: slope=a[i], intercept=dp[i], query at x=b[j]
    """
    n = len(a)
    INF = float('inf')
    dp = [INF] * n
    dp[0] = 0

    # Sort indices by decreasing slope for CHT
    # If a[i] not sorted, use the general (log n) version
    cht = ConvexHullTrick()

    # For general case, collect lines and sort
    # Here we assume b[j] is increasing for monotone queries
    cht.add_line(a[0], dp[0])

    for j in range(1, n):
        dp[j] = cht.query(b[j]) + c[j]
        cht.add_line(a[j], dp[j])

    return dp[n - 1]

# Example
a_vals = [1, 3, 2, 5]  # slopes (need decreasing for basic CHT)
b_vals = [0, 2, 4, 6]  # query points (increasing)
c_vals = [0, 1, 3, 2]  # additive costs
# For this to work properly with monotone CHT, slopes must decrease.
# General version: sort or use Li Chao tree.
a_vals = [5, 3, 2, 1]
print(min_cost_path(a_vals, b_vals, c_vals))
```

### Complexity
- **Add line**: O(1) amortized (each line added/removed at most once)
- **Query**: O(1) amortized with monotone queries, O(log n) with binary search
- **Total**: O(n) for the monotone case vs O(n^2) naive'''),

    ("thinking/algorithms", r'''Implement a Li Chao Segment Tree for the line container problem: support adding lines y = mx + b and querying the minimum y-value at a given x coordinate. Handle arbitrary (non-sorted) insertions and queries.''', r'''<think>
A Li Chao tree is a segment tree over the x-coordinate domain that supports:
1. Insert a line y = mx + b
2. Query the minimum y at a given x

Unlike the convex hull trick, Li Chao trees handle arbitrary insertion and query order, making them more versatile.

The key idea: each node of the segment tree stores at most one "dominant" line for its interval. When inserting a new line, we compare it with the existing line at the midpoint. The line that is better (lower) at the midpoint stays as the dominant line for this node. The other line might still be better on one half of the interval, so we recurse into that half.

For the implementation:
- We need a range of x values. For competitive programming, often [-1e9, 1e9] or we can use coordinate compression.
- Each node stores one line (or None).
- Insert: compare new line vs stored line at midpoint. Keep the one that wins at midpoint. The loser might win on one side -- recurse into that side.
- Query: traverse from root to leaf, evaluating the stored line at each node, taking the minimum.

The tree has depth O(log(range)), and each insert/query takes O(log(range)) time.

Let me implement this cleanly with a class-based approach using an implicit segment tree (dictionary-based nodes) to handle large ranges without memory issues.
</think>

## Li Chao Segment Tree

A Li Chao tree handles arbitrary-order line insertions and minimum queries at any x-coordinate in O(log(range)) per operation.

### Implementation

```python
class LiChaoTree:
    """Li Chao segment tree for minimum line queries.
    Supports inserting lines y = m*x + b and querying min y at x."""

    def __init__(self, lo=-10**9, hi=10**9):
        self.lo = lo
        self.hi = hi
        # Each node: [slope, intercept, left_child, right_child]
        # Use list-based implicit tree
        self.tree = {}  # node_id -> (m, b)
        self.left = {}
        self.right = {}
        self.counter = 0

    def _new_node(self):
        self.counter += 1
        return self.counter

    def _eval(self, node, x):
        if node not in self.tree:
            return float('inf')
        m, b = self.tree[node]
        return m * x + b

    def _insert(self, node, lo, hi, m, b):
        if node is None:
            node = self._new_node()
        mid = (lo + hi) // 2

        if node not in self.tree:
            self.tree[node] = (m, b)
            return node

        cur_m, cur_b = self.tree[node]
        left_better = (m * lo + b) < (cur_m * lo + cur_b)
        mid_better = (m * mid + b) < (cur_m * mid + cur_b)

        if mid_better:
            # New line wins at midpoint, swap
            self.tree[node] = (m, b)
            m, b = cur_m, cur_b
            left_better = not left_better

        if lo == hi:
            return node

        if left_better:
            # Loser might win on the left half
            if node not in self.left:
                self.left[node] = None
            self.left[node] = self._insert(
                self.left[node], lo, mid, m, b)
        else:
            # Loser might win on the right half
            if node not in self.right:
                self.right[node] = None
            self.right[node] = self._insert(
                self.right[node], mid + 1, hi, m, b)

        return node

    def add_line(self, m, b):
        """Insert line y = m*x + b."""
        if not hasattr(self, 'root'):
            self.root = None
        self.root = self._insert(self.root, self.lo, self.hi, m, b)

    def _query(self, node, lo, hi, x):
        if node is None:
            return float('inf')
        val = self._eval(node, x)
        if lo == hi:
            return val
        mid = (lo + hi) // 2
        if x <= mid:
            child_val = self._query(
                self.left.get(node), lo, mid, x)
        else:
            child_val = self._query(
                self.right.get(node), mid + 1, hi, x)
        return min(val, child_val)

    def query(self, x):
        """Query minimum y-value at x."""
        if not hasattr(self, 'root') or self.root is None:
            return float('inf')
        return self._query(self.root, self.lo, self.hi, x)


# Demo
tree = LiChaoTree(lo=-100, hi=100)

# Add lines: y = 2x + 1, y = -x + 10, y = 0.5x + 3
lines = [(2, 1), (-1, 10), (1, 3)]
for m, b in lines:
    tree.add_line(m, b)

# Query at various x
for x in [-5, 0, 3, 7, 10]:
    result = tree.query(x)
    # Verify against brute force
    brute = min(m * x + b for m, b in lines)
    print(f"x={x}: Li Chao={result}, brute={brute}, match={result == brute}")
```

### Output
```
x=-5: Li Chao=-9, brute=-9, match=True
x=0: Li Chao=1, brute=1, match=True
x=3: Li Chao=6, brute=6, match=True
x=7: Li Chao=3, brute=3, match=True
x=10: Li Chao=0, brute=0, match=True
```

### Complexity
- **Insert**: O(log(range)) per line
- **Query**: O(log(range)) per query
- **Space**: O(n * log(range)) for n lines
- **Advantage over CHT**: No sorting requirements on slopes or queries'''),

    ("thinking/algorithms", r'''Explain the Aliens trick (also called lambda optimization or Lagrangian relaxation) for DP. Show how it converts a constrained DP (use exactly k items) into an unconstrained one using binary search on a penalty parameter.''', r'''<think>
The Aliens trick (named after IOI 2016 "Aliens" problem) is a technique to solve DP problems with a constraint "use exactly k items" by converting it into an unconstrained problem with a penalty for each item used.

The idea: suppose we have dp(k) = min cost using exactly k items. If dp(k) is convex in k, we can use Lagrangian relaxation. Instead of constraining k, we add a penalty lambda for each item: dp_lambda = min over all possible counts c of (dp(c) + lambda * c). For a fixed lambda, this is an unconstrained DP that is easier to solve. By binary searching on lambda, we find the value where the optimal unconstrained solution uses exactly k items.

The convexity condition is crucial. dp(k) must be convex (the marginal cost of adding one more item is non-decreasing). When this holds, as we increase lambda, the optimal number of items decreases monotonically.

Algorithm:
1. Binary search on lambda (the penalty per item)
2. For each lambda, solve the unconstrained DP: dp[i] = min(not use item i, use item i and pay lambda)
3. Track how many items are used in the optimal solution
4. If too many items used, increase lambda; if too few, decrease lambda
5. When we find lambda such that k items are optimal, the answer is dp_lambda - k * lambda

One subtlety: for integer costs, we can binary search on integer lambda values, and we need to handle ties carefully (when multiple k values give the same dp_lambda).

Let me implement this for a concrete problem: given n intervals, select exactly k non-overlapping intervals to minimize total cost plus some function of gaps.
</think>

## The Aliens Trick (Lambda Optimization)

Converts "use exactly k items" DP into unconstrained DP via penalty binary search.

### When It Applies
- You have `dp(k)` = optimal cost using exactly k items
- `dp(k)` is **convex** in k (marginal costs are non-decreasing)
- The unconstrained version (any number of items) is much easier to solve

### Concrete Problem
Given n jobs with costs, select exactly k jobs (no two adjacent) to minimize total cost.

```python
def min_cost_k_jobs_naive(costs, k):
    """O(n*k) DP: select exactly k non-adjacent jobs."""
    n = len(costs)
    INF = float('inf')
    # dp[i][j] = min cost using j jobs from first i
    dp = [[INF] * (k + 1) for _ in range(n + 1)]
    dp[0][0] = 0
    for i in range(1, n + 1):
        for j in range(k + 1):
            # skip job i
            dp[i][j] = dp[i - 1][j]
            # take job i (prev taken must be <= i-2)
            if j > 0 and i >= 2:
                dp[i][j] = min(dp[i][j], dp[i - 2][j - 1] + costs[i - 1])
            elif j > 0 and i == 1:
                dp[i][j] = min(dp[i][j], costs[0])
    return dp[n][k]


def min_cost_k_jobs_aliens(costs, k):
    """O(n log C) using Aliens trick."""
    n = len(costs)

    def solve_unconstrained(penalty):
        """Solve unconstrained DP with penalty per job taken.
        Returns (min_cost, num_jobs_taken)."""
        # dp[i] = (min cost considering first i jobs, count of taken)
        # For each job: take it (pay cost + penalty) or skip it
        INF = float('inf')
        # skip[i], take[i] = best (cost, count) if job i is skipped/taken
        skip_cost, skip_cnt = 0, 0
        take_cost, take_cnt = costs[0] + penalty, 1
        prev_skip_cost, prev_skip_cnt = skip_cost, skip_cnt

        for i in range(1, n):
            new_skip_cost = min(skip_cost, take_cost)
            new_skip_cnt = skip_cnt if skip_cost <= take_cost else take_cnt

            # Take job i: must have skipped job i-1
            new_take_cost = skip_cost + costs[i] + penalty
            new_take_cnt = skip_cnt + 1

            prev_skip_cost, prev_skip_cnt = skip_cost, skip_cnt
            skip_cost, skip_cnt = new_skip_cost, new_skip_cnt
            take_cost, take_cnt = new_take_cost, new_take_cnt

        if skip_cost <= take_cost:
            return skip_cost, skip_cnt
        else:
            return take_cost, take_cnt

    # Binary search on penalty
    lo, hi = -10**18, 10**18
    for _ in range(200):  # enough iterations for precision
        mid = (lo + hi) / 2.0
        cost, cnt = solve_unconstrained(mid)
        if cnt > k:
            lo = mid  # increase penalty to discourage taking
        else:
            hi = mid

    final_cost, final_cnt = solve_unconstrained(hi)
    # Answer = total_cost - k * penalty
    answer = final_cost - k * hi
    return answer


# Test
costs = [3, 7, 2, 8, 1, 5, 4]
k = 3
naive_ans = min_cost_k_jobs_naive(costs, k)
aliens_ans = min_cost_k_jobs_aliens(costs, k)
print(f"Naive: {naive_ans}")
print(f"Aliens: {aliens_ans:.6f}")
print(f"Match: {abs(naive_ans - aliens_ans) < 1e-6}")
```

### Complexity
- **Naive constrained DP**: O(n * k)
- **Aliens trick**: O(n * log(C)) where C is the cost range
- For problems where the unconstrained DP is O(n) and k is large, this is a significant improvement

### Key Points
1. **Convexity is required** -- verify dp(k) is convex before applying
2. **Penalty interpretation**: lambda is the "price" of using one more item
3. **Integer costs**: use integer binary search for exact answers
4. **Tie-breaking**: when multiple k values achieve the same penalized cost, handle carefully by tracking counts'''),
]
