PAIRS = [
    ("thinking/algorithms", r'''Given an array of integers, find the length of the longest strictly increasing subsequence (LIS). Also return one such subsequence. Implement an O(n log n) solution.

Example:
Input: [10, 9, 2, 5, 3, 7, 101, 18]
Output: length = 4, one possible LIS = [2, 3, 7, 18]''', r'''<think>
Let me think through the Longest Increasing Subsequence problem carefully.

First, the brute force approach: I could generate all 2^n subsequences and check which ones are strictly increasing, keeping the longest. That's O(2^n) — completely impractical for large inputs.

A better approach: classic DP. Let dp[i] = length of the longest increasing subsequence ending at index i. For each i, I look at all j < i where nums[j] < nums[i], and set dp[i] = max(dp[j] + 1). This is O(n^2) time, O(n) space. That's reasonable but we can do better.

The O(n log n) approach uses a "tails" array. The key insight: maintain an array `tails` where tails[k] is the smallest tail element of all increasing subsequences of length k+1 found so far. This array is always sorted, so we can binary search.

For each element:
- If it's larger than all tails, append it (extends longest subsequence)
- Otherwise, find the leftmost tail that is >= current element and replace it

Wait — this gives us the LENGTH, but how do we reconstruct the actual subsequence? The tails array doesn't preserve the original subsequence. I need to also track which elements were placed where.

I'll maintain a `parent` array and a `positions` array. For each element, I record which position in tails it was placed at, and what element came before it (the element at position-1 in the most recent state). Actually, let me think again...

A cleaner reconstruction: alongside `tails`, keep `tails_indices` (indices into the original array) and `parent[i]` = index of the previous element in the LIS ending at i. When I place nums[i] at position `pos` in tails, the parent of i is tails_indices[pos - 1] (if pos > 0). Then I update tails_indices[pos] = i.

Let me trace through [10, 9, 2, 5, 3, 7, 101, 18]:
- 10: tails = [10], tails_idx = [0]
- 9: 9 < 10, replace. tails = [9], tails_idx = [1], parent[1] = -1
- 2: 2 < 9, replace. tails = [2], tails_idx = [2], parent[2] = -1
- 5: 5 > 2, append. tails = [2, 5], tails_idx = [2, 3], parent[3] = 2
- 3: 3 > 2 but < 5, replace at pos 1. tails = [2, 3], tails_idx = [2, 4], parent[4] = 2
- 7: 7 > 3, append. tails = [2, 3, 7], tails_idx = [2, 4, 5], parent[5] = 4
- 101: append. tails = [2, 3, 7, 101], tails_idx = [2, 4, 5, 6], parent[6] = 5
- 18: 18 > 7 but < 101, replace at pos 3. tails = [2, 3, 7, 18], tails_idx = [2, 4, 5, 7], parent[7] = 5

Length = 4. Reconstruct from tails_idx[-1] = 7 (value 18), parent = 5 (value 7), parent = 4 (value 3), parent = 2 (value 2). So [2, 3, 7, 18]. Correct!

Edge cases:
- Empty array: return 0, []
- All equal elements: LIS length 1
- Already sorted: LIS is the whole array
- Reverse sorted: LIS length 1

Time: O(n log n) due to binary search at each step
Space: O(n) for the auxiliary arrays
</think>

## Longest Increasing Subsequence — O(n log n) with Path Reconstruction

```python
from bisect import bisect_left
from typing import List, Tuple


def longest_increasing_subsequence(nums: List[int]) -> Tuple[int, List[int]]:
    """
    Find the length and one actual longest strictly increasing subsequence.

    Uses the patience sorting / tails approach for O(n log n) time.

    Args:
        nums: List of integers.

    Returns:
        Tuple of (length, one valid LIS).
    """
    if not nums:
        return 0, []

    n = len(nums)
    tails: List[int] = []          # smallest tail for each LIS length
    tails_indices: List[int] = []  # index in nums of each tail
    parent: List[int] = [-1] * n   # parent pointer for reconstruction

    for i, val in enumerate(nums):
        pos = bisect_left(tails, val)

        if pos == len(tails):
            tails.append(val)
            tails_indices.append(i)
        else:
            tails[pos] = val
            tails_indices[pos] = i

        # Set parent: the element at the previous position in tails
        parent[i] = tails_indices[pos - 1] if pos > 0 else -1

    # Reconstruct the subsequence
    lis_length = len(tails)
    result: List[int] = []
    idx = tails_indices[-1]
    while idx != -1:
        result.append(nums[idx])
        idx = parent[idx]

    result.reverse()
    return lis_length, result


# --- Test Cases ---

# Test 1: Standard example
nums1 = [10, 9, 2, 5, 3, 7, 101, 18]
length1, lis1 = longest_increasing_subsequence(nums1)
assert length1 == 4
assert len(lis1) == 4
assert all(lis1[i] < lis1[i + 1] for i in range(len(lis1) - 1))
print(f"Test 1: length={length1}, LIS={lis1}")  # [2, 3, 7, 18]

# Test 2: Already sorted
nums2 = [1, 2, 3, 4, 5]
length2, lis2 = longest_increasing_subsequence(nums2)
assert length2 == 5
assert lis2 == [1, 2, 3, 4, 5]
print(f"Test 2: length={length2}, LIS={lis2}")

# Test 3: Reverse sorted
nums3 = [5, 4, 3, 2, 1]
length3, lis3 = longest_increasing_subsequence(nums3)
assert length3 == 1
print(f"Test 3: length={length3}, LIS={lis3}")

# Test 4: Empty
length4, lis4 = longest_increasing_subsequence([])
assert length4 == 0
assert lis4 == []
print(f"Test 4: length={length4}, LIS={lis4}")

# Test 5: Duplicates
nums5 = [3, 3, 3, 3]
length5, lis5 = longest_increasing_subsequence(nums5)
assert length5 == 1
print(f"Test 5: length={length5}, LIS={lis5}")
```

**Time Complexity:** O(n log n) — for each of the n elements, we perform a binary search (O(log n)) on the tails array.

**Space Complexity:** O(n) — for `tails`, `tails_indices`, `parent`, and the output list.

The key insight is that the `tails` array is always sorted, which enables binary search. While it doesn't directly represent the LIS, tracking parent pointers lets us reconstruct the actual subsequence by walking backward from the last element placed.'''),

    ("thinking/algorithms", r'''Implement the Coin Change problem with full path reconstruction. Given coins of certain denominations and a target amount, find the minimum number of coins needed AND return which coins were used. If the amount cannot be made, return -1.

Example:
coins = [1, 5, 10, 25], amount = 36
Output: 3 coins → [25, 10, 1]''', r'''<think>
The Coin Change problem — a classic DP problem. Let me think through it.

Greedy approach first: always pick the largest coin that fits. For [1, 5, 10, 25] and 36: pick 25, then 10, then 1. That gives 3 coins, which is optimal here. But greedy doesn't always work! Consider coins = [1, 3, 4] and amount = 6. Greedy gives 4 + 1 + 1 = 3 coins, but optimal is 3 + 3 = 2 coins. So DP is necessary.

DP formulation:
- dp[i] = minimum number of coins to make amount i
- dp[0] = 0 (base case)
- dp[i] = min(dp[i - coin] + 1) for all coins where coin <= i
- If dp[i] remains infinity, amount i is unreachable

For reconstruction, I need to track which coin was used at each step. I'll maintain a `used_coin[i]` array where used_coin[i] = the coin denomination chosen when computing dp[i]. Then I trace back: from amount, subtract used_coin[amount], go to the remainder, repeat.

Time: O(amount * len(coins))
Space: O(amount) for dp and used_coin arrays

Edge cases:
- amount = 0: return 0 coins, empty list
- No valid combination: return -1
- Single coin denomination: amount must be divisible by it
- Very large amounts: still O(amount * coins) which could be large but is polynomial

Let me trace through coins = [1, 5, 10, 25], amount = 36:
dp[0] = 0
dp[1] = dp[0] + 1 = 1 (used coin 1)
...
dp[5] = min(dp[4]+1, dp[0]+1) = 1 (used coin 5)
dp[10] = min(dp[9]+1, dp[5]+1, dp[0]+1) = 1 (used coin 10)
dp[25] = 1 (used coin 25)
dp[26] = dp[25] + 1 = 2 (used coin 1)
...
dp[35] = dp[25] + 1 = 2? No, dp[35] = min(dp[34]+1, dp[30]+1, dp[25]+1, dp[10]+1). dp[25]+1 = 2 using coin 10. dp[10]+1 = 2 using coin 25. Either way, 2.
dp[36] = min(dp[35]+1, dp[31]+1, dp[26]+1, dp[11]+1). dp[35]+1 = 3. Let me check dp[26] = dp[25]+1 = 2 using coin 1, so dp[26]+1 = 3 using coin 10. dp[11] = 2 (10+1), so dp[11]+1 = 3 using coin 25. All give 3. With used_coin tracking, the specific path depends on which coin we check first that achieves the minimum.

This should work correctly.
</think>

## Coin Change with Path Reconstruction

```python
from typing import List, Tuple


def coin_change_with_path(coins: List[int], amount: int) -> Tuple[int, List[int]]:
    """
    Find minimum coins to make the given amount and return the coins used.

    Args:
        coins: Available denominations (positive integers).
        amount: Target amount (non-negative integer).

    Returns:
        Tuple of (min_coins, list_of_coins_used).
        Returns (-1, []) if the amount cannot be made.
    """
    if amount == 0:
        return 0, []

    if not coins:
        return -1, []

    INF = float('inf')
    dp: List[float] = [INF] * (amount + 1)
    dp[0] = 0
    used_coin: List[int] = [-1] * (amount + 1)

    for i in range(1, amount + 1):
        for coin in coins:
            if coin <= i and dp[i - coin] + 1 < dp[i]:
                dp[i] = dp[i - coin] + 1
                used_coin[i] = coin

    if dp[amount] == INF:
        return -1, []

    # Reconstruct the path
    result: List[int] = []
    remaining = amount
    while remaining > 0:
        chosen = used_coin[remaining]
        result.append(chosen)
        remaining -= chosen

    # Sort descending for nice presentation
    result.sort(reverse=True)
    return int(dp[amount]), result


# --- Test Cases ---

# Test 1: Standard case
coins1 = [1, 5, 10, 25]
count1, path1 = coin_change_with_path(coins1, 36)
assert count1 == 3
assert sum(path1) == 36
assert all(c in coins1 for c in path1)
print(f"Test 1: {count1} coins -> {path1}")  # e.g., [25, 10, 1]

# Test 2: Greedy fails — DP required
coins2 = [1, 3, 4]
count2, path2 = coin_change_with_path(coins2, 6)
assert count2 == 2
assert sum(path2) == 6
print(f"Test 2: {count2} coins -> {path2}")  # [3, 3]

# Test 3: Impossible
coins3 = [2]
count3, path3 = coin_change_with_path(coins3, 3)
assert count3 == -1
assert path3 == []
print(f"Test 3: {count3} coins -> {path3}")

# Test 4: Zero amount
count4, path4 = coin_change_with_path([1, 2, 5], 0)
assert count4 == 0
assert path4 == []
print(f"Test 4: {count4} coins -> {path4}")

# Test 5: Large amount
coins5 = [1, 5, 10, 25]
count5, path5 = coin_change_with_path(coins5, 99)
assert sum(path5) == 99
assert len(path5) == count5
print(f"Test 5: {count5} coins -> {path5}")  # [25, 25, 25, 10, 10, 1, 1, 1, 1]
```

**Time Complexity:** O(amount * len(coins)) — we fill a DP table of size `amount`, and for each cell consider all coin denominations.

**Space Complexity:** O(amount) — for the `dp` and `used_coin` arrays.

The critical insight is that greedy coin selection can fail (e.g., coins [1, 3, 4] with amount 6), so dynamic programming is necessary for correctness. The `used_coin` array adds negligible overhead but enables full path reconstruction by tracing back from the target amount.'''),

    ("thinking/algorithms", r'''Implement the Edit Distance (Levenshtein Distance) algorithm between two strings with full backtracking to show the sequence of operations (insert, delete, replace) that transforms one string into the other.

Example:
s1 = "kitten", s2 = "sitting"
Output: distance = 3, operations: replace k->s, replace e->i, insert g''', r'''<think>
Edit distance is a classic DP problem. Let me think through the approach.

We have two strings s1 and s2. We want the minimum number of operations (insert, delete, replace) to transform s1 into s2.

DP formulation:
- dp[i][j] = edit distance between s1[0..i-1] and s2[0..j-1]
- Base cases: dp[0][j] = j (insert j characters), dp[i][0] = i (delete i characters)
- Transition: if s1[i-1] == s2[j-1], dp[i][j] = dp[i-1][j-1] (no operation needed)
- Otherwise: dp[i][j] = 1 + min(dp[i-1][j-1] (replace), dp[i][j-1] (insert), dp[i-1][j] (delete))

For backtracking, I trace from dp[m][n] back to dp[0][0], at each step determining which operation was used.

Wait, I should be careful about the backtracking logic. At dp[i][j]:
- If s1[i-1] == s2[j-1]: came from dp[i-1][j-1], no op
- Else, look at which of the three predecessors gave the min:
  - dp[i-1][j-1] + 1: replace s1[i-1] with s2[j-1]
  - dp[i-1][j] + 1: delete s1[i-1]
  - dp[i][j-1] + 1: insert s2[j-1]

Let me trace "kitten" -> "sitting":
    ""  s  i  t  t  i  n  g
""   0  1  2  3  4  5  6  7
k    1  1  2  3  4  5  6  7
i    2  2  1  2  3  4  5  6
t    3  3  2  1  2  3  4  5
t    4  4  3  2  1  2  3  4
e    5  5  4  3  2  2  3  4
n    6  6  5  4  3  3  2  3

Distance = 3. Now backtrack from (6,7):
- dp[6][7]=3, s1[5]='n', s2[6]='g'. Not equal. Min predecessor: dp[5][6]=3 (replace), dp[5][7]=4 (delete), dp[6][6]=2 (insert). Insert 'g'. Go to (6,6).
- dp[6][6]=2, s1[5]='n', s2[5]='n'. Equal. Go to (5,5).
- dp[5][5]=2, s1[4]='e', s2[4]='i'. Not equal. dp[4][4]=1 (replace), dp[4][5]=2 (delete), dp[5][4]=2 (insert). Replace 'e'->'i'. Go to (4,4).
- dp[4][4]=1, s1[3]='t', s2[3]='t'. Equal. Go to (3,3).
- dp[3][3]=1, s1[2]='t', s2[2]='t'. Equal. Go to (2,2).
- dp[2][2]=1, s1[1]='i', s2[1]='i'. Equal. Go to (1,1).
- dp[1][1]=1, s1[0]='k', s2[0]='s'. Not equal. dp[0][0]=0 (replace), dp[0][1]=1 (delete), dp[1][0]=1 (insert). Replace 'k'->'s'. Go to (0,0).

Operations: replace k->s, replace e->i, insert g. That matches the expected output!

Time: O(m*n) for both building dp and backtracking
Space: O(m*n) for the full dp table (needed for backtracking — can't use rolling array)
</think>

## Edit Distance with Operation Backtracking

```python
from typing import List, Tuple


def edit_distance_with_ops(
    s1: str, s2: str
) -> Tuple[int, List[str]]:
    """
    Compute the Levenshtein edit distance between s1 and s2, and return
    the sequence of operations to transform s1 into s2.

    Operations: 'replace X->Y', 'insert Y', 'delete X', or 'match X'.

    Args:
        s1: Source string.
        s2: Target string.

    Returns:
        Tuple of (edit_distance, list_of_operations).
    """
    m, n = len(s1), len(s2)

    # Build DP table
    dp: List[List[int]] = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j - 1],  # replace
                    dp[i - 1][j],       # delete from s1
                    dp[i][j - 1],       # insert into s1
                )

    # Backtrack to find operations
    ops: List[str] = []
    i, j = m, n

    while i > 0 or j > 0:
        if i > 0 and j > 0 and s1[i - 1] == s2[j - 1]:
            ops.append(f"match '{s1[i - 1]}'")
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            ops.append(f"replace '{s1[i - 1]}' -> '{s2[j - 1]}'")
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(f"delete '{s1[i - 1]}'")
            i -= 1
        elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            ops.append(f"insert '{s2[j - 1]}'")
            j -= 1
        else:
            # Fallback — should not reach here with correct logic
            break

    ops.reverse()
    return dp[m][n], ops


# --- Test Cases ---

# Test 1: Classic example
dist1, ops1 = edit_distance_with_ops("kitten", "sitting")
assert dist1 == 3
edit_ops1 = [op for op in ops1 if not op.startswith("match")]
print(f"Test 1: distance={dist1}")
for op in ops1:
    print(f"  {op}")
# Expected edits: replace k->s, replace e->i, insert g

# Test 2: One empty string
dist2, ops2 = edit_distance_with_ops("", "abc")
assert dist2 == 3
assert all("insert" in op for op in ops2)
print(f"\nTest 2: distance={dist2}, ops={ops2}")

# Test 3: Identical strings
dist3, ops3 = edit_distance_with_ops("same", "same")
assert dist3 == 0
assert all(op.startswith("match") for op in ops3)
print(f"\nTest 3: distance={dist3}")

# Test 4: Complete replacement
dist4, ops4 = edit_distance_with_ops("abc", "xyz")
assert dist4 == 3
print(f"\nTest 4: distance={dist4}, ops={ops4}")

# Test 5: Deletion only
dist5, ops5 = edit_distance_with_ops("abcde", "ace")
assert dist5 == 2
print(f"\nTest 5: distance={dist5}")
for op in ops5:
    print(f"  {op}")
```

**Time Complexity:** O(m * n) where m = len(s1) and n = len(s2), for both DP construction and backtracking.

**Space Complexity:** O(m * n) for the full DP table. Note: we cannot use the common rolling-array optimization here because backtracking requires the complete table. If only the distance is needed (no operations), space can be reduced to O(min(m, n)).

The backtracking phase walks from dp[m][n] to dp[0][0], choosing at each cell which predecessor led to the current value. This reconstructs the exact sequence of edits. Priority is given to match > replace > delete > insert to produce intuitive operation sequences.'''),

    ("thinking/algorithms", r'''Implement Matrix Chain Multiplication. Given dimensions of n matrices, find the minimum number of scalar multiplications needed and the optimal parenthesization.

Example:
dimensions = [40, 20, 30, 10, 30] (representing 4 matrices: 40x20, 20x30, 30x10, 10x30)
Output: minimum cost and the optimal grouping like ((A1(A2 A3))A4)''', r'''<think>
Matrix Chain Multiplication — one of the classic interval DP problems.

Given matrices A1 (p0 x p1), A2 (p1 x p2), ..., An (p_{n-1} x p_n), find the order of multiplication that minimizes the total number of scalar multiplications.

The key insight: the cost of multiplying a (a x b) matrix by a (b x c) matrix is a * b * c scalar multiplications. The total cost depends on parenthesization.

Brute force: try all possible parenthesizations. The number of ways is the Catalan number C(n-1), which grows exponentially. Not feasible for large n.

DP approach:
- Let dp[i][j] = minimum cost to multiply matrices Ai through Aj (1-indexed)
- Base case: dp[i][i] = 0 (single matrix, no multiplication needed)
- Transition: dp[i][j] = min over all k in [i, j-1] of (dp[i][k] + dp[k+1][j] + p[i-1]*p[k]*p[j])
- We split the chain at position k: multiply Ai..Ak, then Ak+1..Aj, then combine

For reconstruction, I'll keep a split[i][j] array recording the optimal k.

Let me trace dimensions = [40, 20, 30, 10, 30], so 4 matrices:
- A1: 40x20, A2: 20x30, A3: 30x10, A4: 10x30

Chain length 2:
dp[1][2] = 40*20*30 = 24000, split[1][2] = 1
dp[2][3] = 20*30*10 = 6000, split[2][3] = 2
dp[3][4] = 30*10*30 = 9000, split[3][4] = 3

Chain length 3:
dp[1][3] = min(
  dp[1][1] + dp[2][3] + 40*20*10 = 0 + 6000 + 8000 = 14000 (k=1),
  dp[1][2] + dp[3][3] + 40*30*10 = 24000 + 0 + 12000 = 36000 (k=2)
) = 14000, split[1][3] = 1

dp[2][4] = min(
  dp[2][2] + dp[3][4] + 20*30*30 = 0 + 9000 + 18000 = 27000 (k=2),
  dp[2][3] + dp[4][4] + 20*10*30 = 6000 + 0 + 6000 = 12000 (k=3)
) = 12000, split[2][4] = 3

Chain length 4:
dp[1][4] = min(
  dp[1][1] + dp[2][4] + 40*20*30 = 0 + 12000 + 24000 = 36000 (k=1),
  dp[1][2] + dp[3][4] + 40*30*30 = 24000 + 9000 + 36000 = 69000 (k=2),
  dp[1][3] + dp[4][4] + 40*10*30 = 14000 + 0 + 12000 = 26000 (k=3)
) = 26000, split[1][4] = 3

Minimum cost = 26000. Now reconstruct:
split[1][4] = 3: (A1..A3)(A4)
split[1][3] = 1: (A1)(A2..A3)
split[2][3] = 2: (A2)(A3)
Result: ((A1(A2 A3))A4)

Time: O(n^3) — three nested loops (i, j, k)
Space: O(n^2) for dp and split tables
</think>

## Matrix Chain Multiplication with Optimal Parenthesization

```python
from typing import List, Tuple


def matrix_chain_multiply(
    dims: List[int],
) -> Tuple[int, str]:
    """
    Find minimum scalar multiplications for a chain of matrices
    and return the optimal parenthesization.

    Args:
        dims: List of dimensions [p0, p1, ..., pn] representing n matrices
              where matrix i has dimensions p[i-1] x p[i].

    Returns:
        Tuple of (minimum_cost, parenthesization_string).
    """
    n = len(dims) - 1  # number of matrices

    if n <= 0:
        return 0, ""
    if n == 1:
        return 0, "A1"

    INF = float('inf')
    # dp[i][j] = min cost to multiply matrices i through j (1-indexed)
    dp: List[List[float]] = [[0.0] * (n + 1) for _ in range(n + 1)]
    split: List[List[int]] = [[0] * (n + 1) for _ in range(n + 1)]

    # Fill by increasing chain length
    for chain_len in range(2, n + 1):
        for i in range(1, n - chain_len + 2):
            j = i + chain_len - 1
            dp[i][j] = INF

            for k in range(i, j):
                cost = dp[i][k] + dp[k + 1][j] + dims[i - 1] * dims[k] * dims[j]
                if cost < dp[i][j]:
                    dp[i][j] = cost
                    split[i][j] = k

    def build_parens(i: int, j: int) -> str:
        """Recursively build the parenthesization string."""
        if i == j:
            return f"A{i}"
        k = split[i][j]
        left = build_parens(i, k)
        right = build_parens(k + 1, j)
        return f"({left} {right})"

    parens = build_parens(1, n)
    return int(dp[1][n]), parens


# --- Test Cases ---

# Test 1: Classic example
dims1 = [40, 20, 30, 10, 30]
cost1, parens1 = matrix_chain_multiply(dims1)
assert cost1 == 26000
print(f"Test 1: cost={cost1}, grouping={parens1}")
# Expected: ((A1 (A2 A3)) A4)

# Test 2: Two matrices (no choice)
dims2 = [10, 20, 30]
cost2, parens2 = matrix_chain_multiply(dims2)
assert cost2 == 10 * 20 * 30  # 6000
print(f"Test 2: cost={cost2}, grouping={parens2}")

# Test 3: Three matrices
dims3 = [10, 30, 5, 60]
cost3, parens3 = matrix_chain_multiply(dims3)
assert cost3 == 4500  # (A1 A2) then result * A3
print(f"Test 3: cost={cost3}, grouping={parens3}")

# Test 4: Single matrix
dims4 = [5, 10]
cost4, parens4 = matrix_chain_multiply(dims4)
assert cost4 == 0
print(f"Test 4: cost={cost4}, grouping={parens4}")

# Test 5: Larger chain
dims5 = [30, 35, 15, 5, 10, 20, 25]
cost5, parens5 = matrix_chain_multiply(dims5)
assert cost5 == 15125
print(f"Test 5: cost={cost5}, grouping={parens5}")
```

**Time Complexity:** O(n^3) — three nested loops over chain length, start index, and split point.

**Space Complexity:** O(n^2) — for the `dp` and `split` tables.

This is a textbook interval DP problem. The key idea is that any optimal solution must split the chain somewhere, and we try all possible splits. The `split` table records which split point was chosen, enabling recursive reconstruction of the parenthesization. There is no known algorithm faster than O(n^3) for the general case, though Hu-Shing achieves O(n log n) for the special case of finding the split order.'''),

    ("thinking/algorithms", r'''Given a string, find the minimum number of cuts needed to partition it such that every substring in the partition is a palindrome. Return the minimum cuts and the actual partition.

Example:
Input: "aab"
Output: 1 cut -> ["aa", "b"]

Input: "abcbdd"
Output: 2 cuts -> ["a", "bcb", "dd"]''', r'''<think>
Palindrome Partitioning with minimum cuts. Let me think about approaches.

Brute force: try all possible partitions (2^(n-1) possible cut positions), check if all parts are palindromes, find the one with minimum cuts. Exponential time — too slow.

DP approach. There are actually two parts:
1. Precompute which substrings are palindromes
2. Find the minimum cuts

For part 1, I'll build a table `is_pal[i][j]` = True if s[i..j] is a palindrome.
- is_pal[i][i] = True (single char)
- is_pal[i][i+1] = (s[i] == s[i+1])
- is_pal[i][j] = (s[i] == s[j]) and is_pal[i+1][j-1]

For part 2:
- dp[i] = minimum cuts for s[0..i]
- If s[0..i] is itself a palindrome, dp[i] = 0
- Otherwise, dp[i] = min(dp[j-1] + 1) for all j in [1, i] where s[j..i] is a palindrome
- Base: dp[0] = 0 (single character is always a palindrome)

Wait, I need to be careful with indexing. Let me use dp[i] = minimum cuts for s[0..i-1] (the first i characters). Actually, let me just use dp[i] = min cuts for s[0..i].

For reconstruction, I track cut_pos[i] = the index j where the last cut was made for dp[i].

Let me trace "abcbdd":
First, build is_pal:
- Single chars: all True
- Length 2: is_pal[4][5] for "dd" = True, others False
- Length 3: is_pal[1][3] for "bcb" = True
- Length 4+: check... is_pal[0][3] "abcb" = (a==b)? No. is_pal[1][4] "bcbd" = (b==d)? No. is_pal[2][5] "cbdd" = (c==d)? No.

dp[0] = 0 ("a" is palindrome)
dp[1] = dp[0] + 1 = 1 ("b" is palindrome, cut after "a")
dp[2] = dp[1] + 1 = 2 ("c" is palindrome, cut after "ab")
dp[3]: s[0..3]="abcb" not palindrome. Check j=1: s[1..3]="bcb" IS palindrome, so dp[0]+1 = 1. j=2: s[2..3]="cb" not palindrome. j=3: s[3..3]="b" palindrome, dp[2]+1=3. Min = 1. dp[3] = 1.
dp[4]: s[0..4]="abcbd" not palindrome. j=4: s[4..4]="d" palindrome, dp[3]+1=2. j=3: s[3..4]="bd" not. j=2: s[2..4]="cbd" not. j=1: s[1..4]="bcbd" not. So dp[4] = 2.
dp[5]: s[0..5]="abcbdd" not palindrome. j=5: s[5..5]="d", dp[4]+1=3. j=4: s[4..5]="dd" palindrome, dp[3]+1=2. j=3: s[3..5]="bdd" not. j=1: s[1..5]="bcbdd" not. Min = 2. dp[5] = 2.

Minimum cuts = 2. Reconstruction from dp[5]: last palindrome starts at j=4 ("dd"), dp[3]: last palindrome starts at j=1 ("bcb"), dp[0]: "a" is palindrome. So partition = ["a", "bcb", "dd"]. Correct!

Time: O(n^2) for both palindrome precomputation and cut DP
Space: O(n^2) for is_pal table
</think>

## Palindrome Partitioning — Minimum Cuts with Reconstruction

```python
from typing import List, Tuple


def min_palindrome_partition(s: str) -> Tuple[int, List[str]]:
    """
    Find the minimum number of cuts to partition s into palindromic substrings,
    and return the actual partition.

    Args:
        s: Input string.

    Returns:
        Tuple of (min_cuts, list_of_palindromic_substrings).
    """
    if not s:
        return 0, []

    n = len(s)

    # Step 1: Precompute palindrome table
    is_pal: List[List[bool]] = [[False] * n for _ in range(n)]

    for i in range(n):
        is_pal[i][i] = True

    for i in range(n - 1):
        is_pal[i][i + 1] = (s[i] == s[i + 1])

    for length in range(3, n + 1):
        for i in range(n - length + 1):
            j = i + length - 1
            is_pal[i][j] = (s[i] == s[j]) and is_pal[i + 1][j - 1]

    # Step 2: DP for minimum cuts
    # dp[i] = min cuts for s[0..i]
    dp: List[int] = list(range(n))  # worst case: cut after every char
    cut_at: List[int] = list(range(n))  # where the last partition starts

    for i in range(n):
        if is_pal[0][i]:
            dp[i] = 0
            cut_at[i] = 0
            continue

        for j in range(1, i + 1):
            if is_pal[j][i] and dp[j - 1] + 1 < dp[i]:
                dp[i] = dp[j - 1] + 1
                cut_at[i] = j  # last palindrome starts at index j

    # Step 3: Reconstruct the partition
    parts: List[str] = []
    end = n - 1
    while end >= 0:
        start = cut_at[end]
        parts.append(s[start:end + 1])
        end = start - 1

    parts.reverse()
    return dp[n - 1], parts


# --- Test Cases ---

# Test 1: Simple split
cuts1, parts1 = min_palindrome_partition("aab")
assert cuts1 == 1
assert parts1 == ["aa", "b"]
assert all(p == p[::-1] for p in parts1)
print(f"Test 1: {cuts1} cut(s) -> {parts1}")

# Test 2: Multiple palindromic segments
cuts2, parts2 = min_palindrome_partition("abcbdd")
assert cuts2 == 2
assert "".join(parts2) == "abcbdd"
assert all(p == p[::-1] for p in parts2)
print(f"Test 2: {cuts2} cut(s) -> {parts2}")

# Test 3: Already a palindrome — no cuts needed
cuts3, parts3 = min_palindrome_partition("racecar")
assert cuts3 == 0
assert parts3 == ["racecar"]
print(f"Test 3: {cuts3} cut(s) -> {parts3}")

# Test 4: All distinct characters — maximum cuts
cuts4, parts4 = min_palindrome_partition("abcd")
assert cuts4 == 3
assert parts4 == ["a", "b", "c", "d"]
print(f"Test 4: {cuts4} cut(s) -> {parts4}")

# Test 5: Single character
cuts5, parts5 = min_palindrome_partition("x")
assert cuts5 == 0
assert parts5 == ["x"]
print(f"Test 5: {cuts5} cut(s) -> {parts5}")

# Test 6: Complex case
cuts6, parts6 = min_palindrome_partition("aabba")
assert cuts6 == 0  # "aabba" is a palindrome
print(f"Test 6: {cuts6} cut(s) -> {parts6}")
```

**Time Complexity:** O(n^2) — palindrome precomputation is O(n^2), and the cut DP is also O(n^2).

**Space Complexity:** O(n^2) — for the `is_pal` table. The DP and reconstruction arrays are O(n).

The two-phase approach is important: first precompute all palindromic substrings in O(n^2), then use that lookup table in the cut DP to avoid redundant palindrome checking. The `cut_at` array records where each last palindromic segment begins, enabling O(n) reconstruction by walking backward from the end of the string.'''),
]
