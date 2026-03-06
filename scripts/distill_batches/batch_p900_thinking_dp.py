PAIRS = [
    ("thinking/algorithms", r'''Given an array of integers, find the length of the longest strictly increasing subsequence (LIS). Also return one such subsequence. Implement an O(n log n) solution.

Example:
Input: [10, 9, 2, 5, 3, 7, 101, 18]
Output: length = 4, one possible LIS = [2, 3, 7, 18]''', r'''<think>
Longest Increasing Subsequence. Need both the length and the actual subsequence, in O(n log n).

My first instinct is the O(n^2) DP: dp[i] = longest increasing subsequence ending at index i, where dp[i] = max(dp[j] + 1) for all j < i with nums[j] < nums[i]. That would work, but the problem asks for O(n log n). Can I do better?

Right, the patience sorting idea. I maintain an array of "tails" -- tails[k] holds the smallest ending element among all increasing subsequences of length k+1 found so far. Because if two subsequences have the same length, the one with the smaller tail is more useful (more room to extend). This tails array stays sorted, so I can binary search to find where each new element goes.

For each element:
- If it's bigger than everything in tails, append (we found a longer subsequence)
- Otherwise, find the first tail >= element and replace it (we found a subsequence of that length with a smaller ending)

Hmm, but wait. This only gives me the length. The tails array at the end isn't the actual subsequence -- it's a mix of elements from different subsequences. For example, if I process [3, 1, 4], tails would be [1, 4], but the actual LIS is [3, 4] or [1, 4], not necessarily the tails array itself. Well, in this case tails happens to be valid, but that's coincidence.

So how do I reconstruct? I was thinking I could keep a separate "pile" for each position and pick from each pile... but that sounds complicated. Let me think differently.

What if I track parent pointers? When I place nums[i] at position pos in the tails array, the element before it in the subsequence is whatever was at position pos-1 in tails at that moment. So I store parent[i] = tails_indices[pos - 1]. And I keep tails_indices[pos] = i to track which original index is currently the tail at each position.

Actually, does this work correctly? If I later replace an element at some position, the parent of the replacement points to whatever was at pos-1 at that time, which could be different from the original. Let me trace through the example to make sure.

[10, 9, 2, 5, 3, 7, 101, 18]:
- 10: tails = [10], tails_idx = [0], parent[0] = -1
- 9: 9 < 10, replace pos 0. tails = [9], tails_idx = [1], parent[1] = -1
- 2: 2 < 9, replace pos 0. tails = [2], tails_idx = [2], parent[2] = -1
- 5: 5 > 2, append at pos 1. tails = [2, 5], tails_idx = [2, 3], parent[3] = tails_idx[0] = 2
- 3: bisect_left finds pos 1 (3 > 2 but < 5), replace. tails = [2, 3], tails_idx = [2, 4], parent[4] = tails_idx[0] = 2
- 7: 7 > 3, append at pos 2. tails = [2, 3, 7], tails_idx = [2, 4, 5], parent[5] = tails_idx[1] = 4
- 101: append at pos 3. tails = [2, 3, 7, 101], tails_idx = [2, 4, 5, 6], parent[6] = tails_idx[2] = 5
- 18: bisect_left finds pos 3 (18 < 101), replace. tails = [2, 3, 7, 18], tails_idx = [2, 4, 5, 7], parent[7] = tails_idx[2] = 5

Length = 4. Reconstruct from tails_idx[-1] = 7 (value 18), parent 5 (value 7), parent 4 (value 3), parent 2 (value 2). That gives [2, 3, 7, 18]. Correct!

But wait, I was worried: when I replaced 5 with 3 at position 1, did that mess up anything? No -- the parent of index 4 (value 3) correctly points to index 2 (value 2), and later when 7 goes to position 2, its parent points to index 4 (value 3, the current occupant of position 1). The key insight is that even though we're overwriting tails_idx entries, the parent pointers were already set when the element was placed. Old parent pointers remain valid because they reference original array indices, not tails positions.

Edge cases: empty array (return 0), all equal (LIS = 1 since strictly increasing), already sorted (LIS = whole array).

One thing I need to be careful about: bisect_left vs bisect_right. Since we want strictly increasing, we need bisect_left -- if the element equals a tail, we replace it rather than appending after it.

Time: O(n log n) -- binary search per element.
Space: O(n) for the auxiliary arrays.
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
Coin change with path reconstruction. My first thought: just be greedy. Pick the largest coin that fits, repeat. For [1, 5, 10, 25] with amount 36: take 25, then 10, then 1 = 3 coins. That works here.

But hold on -- greedy fails for some coin sets. Take coins = [1, 3, 4], amount = 6. Greedy picks 4, then 1, then 1 = 3 coins. But 3 + 3 = 2 coins is better. So I can't use greedy in general. I need DP.

OK so the DP is straightforward: dp[i] = min coins to make amount i. For each amount i, try subtracting each coin denomination and take the minimum. dp[0] = 0, and if dp[i] stays at infinity, that amount is impossible.

For reconstruction, I need to remember which coin I actually picked at each amount. I'll keep a used_coin[i] array. Then to recover the path, start at `amount`, look up used_coin[amount], subtract it, repeat until I hit 0.

Wait, should I iterate coins in the outer loop or amounts? If I do amounts in the outer loop and coins in the inner loop, each dp[i] sees the best from all coins. That's correct for unbounded supply. If I did coins outer and amounts inner, that would also work but is more like the unbounded knapsack framing. Either way same result for this problem. I'll go with amounts outer since the reconstruction logic is cleaner -- at each amount I just pick the best coin.

Let me sanity-check with coins = [1, 3, 4], amount = 6:
dp[0] = 0
dp[1] = dp[0]+1 = 1 (coin 1)
dp[2] = dp[1]+1 = 2 (coin 1)
dp[3] = min(dp[2]+1, dp[0]+1) = 1 (coin 3)
dp[4] = min(dp[3]+1, dp[1]+1, dp[0]+1) = 1 (coin 4)
dp[5] = min(dp[4]+1, dp[2]+1) = 2 (coin 1 off dp[4], or coin 3 off dp[2] -- both give 2)
dp[6] = min(dp[5]+1, dp[3]+1, dp[2]+1) = min(3, 2, 3) = 2 (coin 3, from dp[3]=1)

So dp[6] = 2, used_coin[6] = 3. Trace back: 6 - 3 = 3, used_coin[3] = 3. 3 - 3 = 0. Path: [3, 3]. That's the optimal answer.

Now the original example: coins = [1, 5, 10, 25], amount = 36. dp[25] = 1, dp[35] = min over (dp[34]+1, dp[30]+1, dp[25]+1, dp[10]+1). dp[25]+1 = 2 and dp[10]+1 = 2, so dp[35] = 2. dp[36] = min(dp[35]+1, dp[31]+1, dp[26]+1, dp[11]+1) = 3. The exact coin chosen depends on iteration order, but 25+10+1 is one valid path.

Edge cases: amount = 0 returns immediately. If no coins can make the amount (like coins=[2], amount=3), dp stays at infinity and we return -1.

Time: O(amount * len(coins)), Space: O(amount).
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
Edit distance between two strings, with full backtracking to show operations. Classic DP.

Let me set up the recurrence. dp[i][j] = min operations to transform s1[0..i-1] into s2[0..j-1]. Base cases: dp[0][j] = j (all inserts), dp[i][0] = i (all deletes). Transition: if characters match, dp[i][j] = dp[i-1][j-1], otherwise take min of replace (dp[i-1][j-1]+1), delete (dp[i-1][j]+1), insert (dp[i][j-1]+1).

The tricky part is backtracking. I need to walk from dp[m][n] back to dp[0][0] and figure out which operation was chosen at each cell. My first thought was to store the operation in a separate table, but actually I can just re-derive it during backtracking by checking which predecessor gives the right value. That saves memory on the extra table, though I still need the full dp table.

Hmm, actually can I use a rolling array and reconstruct? No -- with only two rows, I lose the information needed to backtrack through the whole table. I need the complete m x n grid. That's fine, space is O(mn) either way for the backtracking case.

One thing I need to be careful about: the order of checking during backtracking matters for which operations get priority. If multiple predecessors tie, I should pick consistently. I'll check match first (if chars equal), then replace, then delete, then insert. That tends to produce more intuitive operation sequences.

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
- dp[6][7]=3, 'n' vs 'g', not equal. Check: dp[5][6]+1=3 (replace), dp[5][7]+1=5 (delete -- wait, what's dp[5][7]? Row for 'e' col for 'g'... that's 4, so +1=5). dp[6][6]+1=3 (insert). Both replace and insert give 3. I'll prefer... hmm, replace comes from diagonal, insert from left. With my priority (replace before insert), I'd pick replace. But actually, looking at the expected output, the answer uses insert 'g'. Let me re-examine.

Oh wait, I mixed up. dp[5][6] is row 'e', column 'n', which is 3. So replace would be dp[5][6]+1 = 4, not 3. Let me recount. dp[i-1][j-1] for (6,7) is dp[5][6] = 3, so replace cost = 3+1 = 4. dp[i-1][j] = dp[5][7] = 4, delete cost = 5. dp[i][j-1] = dp[6][6] = 2, insert cost = 3. So insert wins at cost 3. Insert 'g', go to (6,6).

- dp[6][6]=2, 'n'=='n', match. Go to (5,5).
- dp[5][5]=2, 'e' vs 'i', not equal. dp[4][4]+1=2 (replace), dp[4][5]+1=3, dp[5][4]+1=3. Replace 'e'->'i'. Go to (4,4).
- dp[4][4]=1, 't'=='t'. Go to (3,3).
- dp[3][3]=1, 't'=='t'. Go to (2,2).
- dp[2][2]=1, 'i'=='i'. Go to (1,1).
- dp[1][1]=1, 'k' vs 's'. dp[0][0]+1=1 (replace), dp[0][1]+1=2, dp[1][0]+1=2. Replace 'k'->'s'. Go to (0,0).

Operations: replace k->s, replace e->i, insert g. Matches expected output. Good -- I almost got the backtracking wrong by miscounting the dp indices. The lesson is that dp[i-1][j-1] means "row i-1, column j-1", not "one step back in both strings from the current characters."

Time: O(m*n). Space: O(m*n) since we need the full table for backtracking.
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
Matrix chain multiplication -- I need to find the optimal way to parenthesize a chain of matrix multiplications to minimize scalar operations.

My initial thought is: does the order even matter? Yes, definitely. Multiplying a 40x20 by a 20x30 matrix costs 40*20*30 = 24000 operations, and the result is 40x30. If I then multiply by a 30x10, that's 40*30*10 = 12000. Total = 36000. But if I multiply the 20x30 by 30x10 first (cost 6000, result 20x10), then 40x20 by 20x10 (cost 8000), total = 14000. Huge difference!

Could I just try all orderings? The number of parenthesizations is the Catalan number, which is exponential. So brute force is out for large n.

This has optimal substructure though. Any optimal parenthesization must split the chain somewhere: (A1..Ak)(Ak+1..An). Once I choose k, both subproblems are independent. That screams interval DP.

Let dp[i][j] = min cost to multiply Ai through Aj. Base case: dp[i][i] = 0. Transition: dp[i][j] = min over k in [i, j-1] of dp[i][k] + dp[k+1][j] + dims[i-1]*dims[k]*dims[j]. The last term is the cost of multiplying the two resulting matrices together.

I need to fill this bottom-up by increasing chain length. And for reconstruction, I store split[i][j] = the k that achieved the minimum.

Let me trace dims = [40, 20, 30, 10, 30] (4 matrices):

Chain length 2:
dp[1][2] = 40*20*30 = 24000
dp[2][3] = 20*30*10 = 6000
dp[3][4] = 30*10*30 = 9000

Chain length 3:
dp[1][3]: k=1 gives 0 + 6000 + 40*20*10 = 14000. k=2 gives 24000 + 0 + 40*30*10 = 36000. So 14000, split at k=1.
dp[2][4]: k=2 gives 0 + 9000 + 20*30*30 = 27000. k=3 gives 6000 + 0 + 20*10*30 = 12000. So 12000, split at k=3.

Chain length 4:
dp[1][4]: k=1 gives 0 + 12000 + 40*20*30 = 36000. k=2 gives 24000 + 9000 + 40*30*30 = 69000. Ouch, that's terrible. k=3 gives 14000 + 0 + 40*10*30 = 26000. Best is k=3 at 26000.

Hmm, interesting that k=3 wins. That means the optimal is (A1..A3)(A4), and within A1..A3 we split at k=1: (A1)(A2 A3). So the full grouping is ((A1(A2 A3))A4).

For reconstruction, I just need a recursive function that reads split[i][j] and builds a parenthesized string. If i==j, return "Ai".

One thing I briefly wondered: is there a faster algorithm than O(n^3)? There's the Hu-Shing algorithm that does O(n log n) for the special case, but the general MCM is O(n^3) with this DP approach, and that's standard.

Time: O(n^3). Space: O(n^2).
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
Minimum cuts to partition a string into palindromes, plus return the actual partition.

Brute force: try every possible set of cut positions (2^(n-1) subsets). Way too slow.

I could try a recursive approach with memoization -- for each prefix, try all possible first palindromes and recurse on the rest. That might work but the key optimization is precomputing which substrings are palindromes so I don't keep re-checking.

Actually, this is naturally two separate problems:
1. Which substrings s[i..j] are palindromes?
2. Given that info, what's the minimum cuts?

For (1), I can use the expand-from-center approach... no wait, the DP table approach is easier since I need O(1) lookup for any (i,j) pair later. is_pal[i][j] = True if s[i]==s[j] and is_pal[i+1][j-1]. Fill by increasing length.

For (2), dp[i] = min cuts for s[0..i]. If s[0..i] is already a palindrome, dp[i] = 0 (no cuts needed). Otherwise, try every split point j: if s[j..i] is a palindrome, then dp[i] = min(dp[j-1] + 1).

Hmm, I initially thought about using dp[i] = min cuts for s[0..i-1], which would shift all indices by one. That's confusing. Let me stick with dp[i] = min cuts for s[0..i], 0-indexed. Initialize dp[i] = i (worst case: every character is its own palindrome, needs i cuts).

For reconstruction I need to remember where the last palindrome starts. Store cut_at[i] = j meaning the last palindrome in the optimal partition of s[0..i] is s[j..i].

Let me trace "abcbdd":
is_pal table -- the interesting entries: is_pal[1][3] = True ("bcb"), is_pal[4][5] = True ("dd"). Everything length 4+ is False.

dp[0] = 0 (single char "a")
dp[1]: is "ab" a palindrome? No. j=1: s[1..1]="b" palindrome, dp[0]+1=1. dp[1] = 1, cut_at[1] = 1.
dp[2]: "abc" not palindrome. j=2: dp[1]+1=2. j=1: "bc" not palindrome. dp[2] = 2, cut_at[2] = 2.
dp[3]: "abcb" not palindrome. Try j=3: dp[2]+1=3. j=2: "cb" not palindrome. j=1: "bcb" IS palindrome! dp[0]+1=1. j=0: "abcb" not palindrome. Best = 1, cut_at[3] = 1.
dp[4]: "abcbd" not palindrome. j=4: dp[3]+1=2. j=3: "bd" no. j=2: "cbd" no. j=1: "bcbd" no. j=0: "abcbd" no. dp[4] = 2.
dp[5]: j=5: dp[4]+1=3. j=4: "dd" palindrome! dp[3]+1=2. j=3: "bdd" no. j=2: "cbdd" no. j=1: "bcbdd" no. dp[5] = 2, cut_at[5] = 4.

Reconstruction: end=5, cut_at[5]=4 -> "dd", end=3, cut_at[3]=1 -> "bcb", end=0, cut_at[0]=0 -> "a". Reverse: ["a", "bcb", "dd"]. 2 cuts.

Wait, I need to double-check the reconstruction logic. When end=0, cut_at[0] should be 0 (the palindrome "a" starts at index 0), then end = 0-1 = -1, loop ends. That works.

One subtle issue: I initialize dp[i] = i, but what if I forget to check the "whole prefix is a palindrome" case and just rely on the inner loop? If s[0..i] is a palindrome, then j=0 gives dp[-1]+1... which doesn't exist. So I need to handle that separately: check if is_pal[0][i], and if so set dp[i]=0 and skip the inner loop. That's cleaner.

Time: O(n^2) for both phases. Space: O(n^2) for the palindrome table.
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
