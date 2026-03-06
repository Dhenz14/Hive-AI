PAIRS = [
    ("thinking/algorithms", r'''Implement the Next Permutation algorithm: given an array of integers, rearrange it to the next lexicographically greater permutation. If the array is the last permutation, rearrange to the first (sorted ascending).''', r'''<think>
Next Permutation (LeetCode 31) requires finding the next permutation in lexicographic order, in-place with O(1) extra space.

The algorithm:
1. Find the largest index i such that nums[i] < nums[i+1]. If no such index exists, the array is in descending order (last permutation) -- reverse the whole array.
2. Find the largest index j > i such that nums[i] < nums[j].
3. Swap nums[i] and nums[j].
4. Reverse the suffix starting at nums[i+1].

Why this works:
- Step 1 finds the rightmost "ascent" -- the position where we can make the number larger by rearranging the suffix.
- The suffix after position i is in descending order (otherwise i would not be the rightmost ascent).
- Step 2 finds the smallest element in the suffix that is larger than nums[i] -- this is the next candidate to place at position i.
- After swapping, the suffix is still in descending order.
- Step 4 reverses the suffix to ascending order, making it the smallest possible suffix -- giving us the very next permutation.

Example: [1, 2, 3] -> [1, 3, 2]
- i = 1 (nums[1]=2 < nums[2]=3)
- j = 2 (nums[2]=3 > nums[1]=2)
- Swap: [1, 3, 2]
- Suffix after i+1 = [2], already sorted

Example: [1, 3, 2] -> [2, 1, 3]
- i = 0 (nums[0]=1 < nums[1]=3)
- j = 2 (nums[2]=2 > nums[0]=1)
- Swap: [2, 3, 1]
- Reverse suffix [3, 1] -> [1, 3]: result [2, 1, 3]

Time: O(n), Space: O(1).
</think>

**Next Permutation -- In-Place Algorithm**

```python
def next_permutation(nums):
    """
    Rearrange nums to the next lexicographically greater permutation.
    Modifies nums in-place.

    Args:
        nums: list of integers
    """
    n = len(nums)
    if n <= 1:
        return

    # Step 1: Find rightmost ascent
    i = n - 2
    while i >= 0 and nums[i] >= nums[i + 1]:
        i -= 1

    if i >= 0:
        # Step 2: Find rightmost element > nums[i]
        j = n - 1
        while nums[j] <= nums[i]:
            j -= 1
        # Step 3: Swap
        nums[i], nums[j] = nums[j], nums[i]

    # Step 4: Reverse suffix
    left, right = i + 1, n - 1
    while left < right:
        nums[left], nums[right] = nums[right], nums[left]
        left += 1
        right -= 1


def generate_all_permutations(arr):
    """Generate all permutations in lexicographic order using next_permutation."""
    arr = sorted(arr)
    perms = [arr[:]]
    while True:
        next_permutation(arr)
        if arr == perms[0]:
            break
        perms.append(arr[:])
    return perms


# Demo
nums = [1, 2, 3]
print(f"All permutations of {nums}:")
perms = generate_all_permutations(nums[:])
for p in perms:
    print(f"  {p}")

# Single step examples
tests = [
    [1, 2, 3],
    [3, 2, 1],
    [1, 1, 5],
    [1, 3, 2],
    [2, 3, 1],
]
print("\nNext permutation steps:")
for t in tests:
    before = t[:]
    next_permutation(t)
    print(f"  {before} -> {t}")
```

**Algorithm Walkthrough ([2, 3, 1]):**
```
Step 1: i=0 (nums[0]=2 < nums[1]=3)
Step 2: j=2 (nums[2]=1? No, 1<2. j=1, nums[1]=3>2) -> j=1
Step 3: Swap nums[0] and nums[1]: [3, 2, 1]
Step 4: Reverse suffix [2,1] -> [1,2]: result [3, 1, 2]
```

**Complexity:**
- Time: O(n) -- at most two linear scans
- Space: O(1) -- in-place modification'''),

    ("thinking/algorithms", r'''Implement an efficient algorithm to count the number of inversions in an array. An inversion is a pair (i, j) where i < j but arr[i] > arr[j]. Use a modified merge sort approach.''', r'''<think>
Counting inversions measures how far an array is from being sorted. Brute force checks all pairs in O(n^2). We can use modified merge sort to count in O(n log n).

Key insight: During the merge step of merge sort, when we pick an element from the right half before all elements from the left half are placed, it means this right element is smaller than all remaining left elements -- each of those is an inversion.

Algorithm (merge sort based):
1. Divide array into two halves
2. Recursively count inversions in each half
3. Count "split inversions" (one element in left, one in right) during merge
4. Total = left inversions + right inversions + split inversions

During merge:
- If left[i] <= right[j]: no inversions for left[i], advance i
- If left[i] > right[j]: right[j] is smaller than all remaining left elements (left[i..end]), so add (len(left) - i) inversions, advance j

Why this works: After each half is sorted by recursion, the merge step correctly counts all inversions where one element was originally in the left half and the other in the right half. Inversions within each half are counted by recursion.

Alternative approaches:
- BIT/Fenwick tree: O(n log n), useful for online counting
- Modified BST: O(n log n) average

Edge cases:
- Already sorted (0 inversions)
- Reverse sorted (n*(n-1)/2 inversions, maximum)
- All equal elements (0 inversions)
- Single element

Time: O(n log n), Space: O(n) for the merge buffer.
</think>

**Count Inversions -- Modified Merge Sort**

```python
def count_inversions(arr):
    """
    Count inversions using modified merge sort.

    Args:
        arr: list of comparable elements
    Returns:
        (sorted_array, inversion_count)
    """
    if len(arr) <= 1:
        return arr[:], 0

    mid = len(arr) // 2
    left, left_inv = count_inversions(arr[:mid])
    right, right_inv = count_inversions(arr[mid:])

    merged = []
    split_inv = 0
    i = j = 0

    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            # All remaining elements in left are > right[j]
            split_inv += len(left) - i
            j += 1

    merged.extend(left[i:])
    merged.extend(right[j:])

    return merged, left_inv + right_inv + split_inv


def count_inversions_brute(arr):
    """O(n^2) brute force for verification."""
    count = 0
    for i in range(len(arr)):
        for j in range(i + 1, len(arr)):
            if arr[i] > arr[j]:
                count += 1
    return count


# Examples
tests = [
    [2, 4, 1, 3, 5],
    [5, 4, 3, 2, 1],
    [1, 2, 3, 4, 5],
    [1, 3, 5, 2, 4, 6],
    [8, 4, 2, 1],
]

for arr in tests:
    _, inv_count = count_inversions(arr)
    brute = count_inversions_brute(arr)
    status = "PASS" if inv_count == brute else "FAIL"
    print(f"  [{status}] {arr}: inversions={inv_count}")

# Maximum inversions
n = 10
reverse_arr = list(range(n, 0, -1))
_, max_inv = count_inversions(reverse_arr)
expected_max = n * (n - 1) // 2
print(f"\n  Reverse [10..1]: inversions={max_inv}, expected={expected_max}")

# Inversion count as distance from sorted
arr = [3, 1, 2]
_, inv = count_inversions(arr)
print(f"\n  {arr}: {inv} inversions = {inv} adjacent swaps needed to sort")
```

**Merge Step Illustration:**
```
Left:  [1, 4]    Right: [2, 3]
Compare 1 vs 2: 1 <= 2, take 1, no inversions
Compare 4 vs 2: 4 > 2, take 2, inversions += 1 (4 > 2)
Compare 4 vs 3: 4 > 3, take 3, inversions += 1 (4 > 3)
Take 4, done. Split inversions = 2
```

**Applications:**
- Measuring similarity between rankings (Kendall tau distance)
- Sorting complexity analysis
- Collaborative filtering

**Complexity:**
- Time: O(n log n) -- same as merge sort
- Space: O(n) for merge buffer'''),

    ("thinking/algorithms", r'''Given a permutation of numbers 1 to n, compute its rank (1-indexed position) in the lexicographically sorted list of all permutations. Do this efficiently without generating all permutations.''', r'''<think>
The rank of a permutation is its position (1-indexed) among all permutations of the same elements in lexicographic order.

For a permutation [a1, a2, ..., an]:
- Count how many permutations come before it
- For each position i from left to right:
  - Count how many of the remaining unused numbers are smaller than a_i. Call this count_smaller.
  - These count_smaller numbers, if placed at position i, would all come before the current permutation.
  - Each such choice leads to (n-i)! permutations for the remaining positions.
  - Add count_smaller * (n-i)! to the rank.
- Final rank = sum + 1 (for 1-indexing)

Example: Permutation [3, 1, 2]
- Position 0: element 3. Unused = {1, 2, 3}. Numbers < 3: {1, 2} -> count = 2. Add 2 * 2! = 4.
- Position 1: element 1. Unused = {1, 2}. Numbers < 1: {} -> count = 0. Add 0.
- Position 2: element 2. Unused = {2}. Numbers < 2: {} -> count = 0. Add 0.
- Rank = 4 + 0 + 0 + 1 = 5.

Verification: All permutations of [1,2,3] in order:
[1,2,3], [1,3,2], [2,1,3], [2,3,1], [3,1,2], [3,2,1]
-> [3,1,2] is at position 5. Correct.

For the "count_smaller" step, we can use a BIT (Fenwick tree) to efficiently count how many unused numbers are smaller than a given value. This gives O(n log n) total.

For the simple approach, maintaining a sorted list and using binary search gives O(n^2) or O(n log n).

Factorials can be precomputed.

For the inverse problem (unrank): given rank, find the permutation.
</think>

**Rank of Permutation -- Factoradic Number System**

```python
from bisect import bisect_left, insort


def factorial(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def permutation_rank(perm):
    """
    Compute 1-indexed rank of a permutation in lexicographic order.

    Args:
        perm: list representing a permutation of 1..n
    Returns:
        rank (1-indexed)
    """
    n = len(perm)
    # Precompute factorials
    fact = [1] * (n + 1)
    for i in range(1, n + 1):
        fact[i] = fact[i - 1] * i

    # Maintain sorted list of available numbers
    available = sorted(perm)
    rank = 0

    for i in range(n):
        # Count how many available numbers are smaller than perm[i]
        idx = bisect_left(available, perm[i])
        rank += idx * fact[n - 1 - i]
        available.pop(idx)

    return rank + 1


def unrank_permutation(rank, n):
    """
    Given a 1-indexed rank, reconstruct the permutation of 1..n.

    Args:
        rank: 1-indexed rank
        n: size of permutation
    Returns:
        list representing the permutation
    """
    rank -= 1  # convert to 0-indexed
    fact = [1] * (n + 1)
    for i in range(1, n + 1):
        fact[i] = fact[i - 1] * i

    available = list(range(1, n + 1))
    perm = []

    for i in range(n):
        f = fact[n - 1 - i]
        idx = rank // f
        rank %= f
        perm.append(available.pop(idx))

    return perm


# Test
n = 4
print(f"All permutations of 1..{n} with ranks:")
from itertools import permutations as iter_perms
for i, p in enumerate(iter_perms(range(1, n + 1)), 1):
    computed_rank = permutation_rank(list(p))
    match = computed_rank == i
    if not match:
        print(f"  FAIL: {list(p)} rank={computed_rank} expected={i}")
print(f"  All {factorial(n)} permutations verified!")

# Demonstrate rank and unrank
test_perms = [[3, 1, 2], [1, 2, 3, 4], [4, 3, 2, 1], [2, 3, 1, 4]]
for p in test_perms:
    r = permutation_rank(p)
    reconstructed = unrank_permutation(r, len(p))
    print(f"\n  perm={p} -> rank={r} -> unrank={reconstructed}")
    assert reconstructed == p
```

**Factoradic (Factorial Number System):**
The rank computation is essentially converting the permutation to its factoradic representation:
- Position i contributes: (count_smaller) * (n-1-i)!
- This is analogous to converting a number between bases

**Complexity:**
- Rank: O(n^2) with list operations, O(n log n) with Fenwick tree
- Unrank: O(n^2) with list, O(n log n) with Fenwick tree
- Space: O(n)'''),

    ("thinking/algorithms", r'''Explain Catalan numbers and their applications. Implement efficient computation and show how Catalan numbers solve at least 3 different combinatorial problems.''', r'''<think>
Catalan numbers are one of the most important sequences in combinatorics. The nth Catalan number is:

C(n) = (2n)! / ((n+1)! * n!) = C(2n, n) / (n+1)

First few: 1, 1, 2, 5, 14, 42, 132, 429, 1430, 4862, ...

Recurrence: C(0) = 1, C(n+1) = sum(C(i) * C(n-i) for i in 0..n)
Or: C(n+1) = C(n) * 2(2n+1) / (n+2)

Applications (all counted by C(n)):
1. Number of valid parenthesizations with n pairs of parentheses
2. Number of distinct binary search trees with n nodes
3. Number of ways to triangulate a convex polygon with n+2 sides
4. Number of paths from (0,0) to (n,n) on a grid that do not cross above the diagonal (Dyck paths)
5. Number of full binary trees with n+1 leaves
6. Number of ways to multiply n+1 matrices (associativity choices)

I will implement:
- Direct formula computation
- DP computation
- Application 1: Generate all valid parenthesizations
- Application 2: Count BSTs
- Application 3: Ballot problem / Dyck paths

For large n, use the direct formula with modular arithmetic to avoid overflow. For small n, DP or the recurrence works fine.
</think>

**Catalan Numbers -- Theory and Applications**

```python
from math import comb


def catalan_formula(n):
    """Compute nth Catalan number using direct formula."""
    return comb(2 * n, n) // (n + 1)


def catalan_dp(n):
    """Compute Catalan numbers 0..n using DP recurrence."""
    cat = [0] * (n + 1)
    cat[0] = 1
    for i in range(1, n + 1):
        for j in range(i):
            cat[i] += cat[j] * cat[i - 1 - j]
    return cat


def catalan_iterative(n):
    """Compute nth Catalan using iterative formula."""
    if n <= 1:
        return 1
    c = 1
    for i in range(n):
        c = c * 2 * (2 * i + 1) // (i + 2)
    return c


# Application 1: Generate all valid parenthesizations
def generate_parens(n):
    """Generate all valid strings of n pairs of parentheses."""
    result = []

    def backtrack(s, open_count, close_count):
        if len(s) == 2 * n:
            result.append(s)
            return
        if open_count < n:
            backtrack(s + "(", open_count + 1, close_count)
        if close_count < open_count:
            backtrack(s + ")", open_count, close_count + 1)

    backtrack("", 0, 0)
    return result


# Application 2: Count distinct BSTs with n nodes
def count_bsts(n):
    """Count structurally unique BSTs with nodes 1..n."""
    dp = [0] * (n + 1)
    dp[0] = dp[1] = 1

    for nodes in range(2, n + 1):
        for root in range(1, nodes + 1):
            left = root - 1
            right = nodes - root
            dp[nodes] += dp[left] * dp[right]

    return dp[n]


# Application 3: Count Dyck paths (paths that stay below diagonal)
def count_dyck_paths(n):
    """
    Count lattice paths from (0,0) to (n,n) using right/up steps
    that never go above the diagonal (y <= x at all points).
    """
    # This equals the nth Catalan number
    return catalan_formula(n)


# Print Catalan numbers
cat = catalan_dp(15)
print("Catalan numbers C(0) through C(15):")
print(f"  {cat}")

# Verify all methods agree
print("\nVerification:")
for i in range(12):
    c1 = catalan_formula(i)
    c2 = cat[i]
    c3 = catalan_iterative(i)
    match = c1 == c2 == c3
    print(f"  C({i}) = {c1} (match={match})")

# Application demos
print(f"\nValid parenthesizations for n=3 (expect C(3)=5):")
parens = generate_parens(3)
for p in parens:
    print(f"  {p}")
print(f"  Count: {len(parens)}")

print(f"\nDistinct BSTs with n=4 nodes: {count_bsts(4)} (C(4)={cat[4]})")
print(f"Dyck paths (0,0)->(5,5): {count_dyck_paths(5)} (C(5)={cat[5]})")
```

**Common Catalan Interpretations:**
| n | C(n) | Parenthesizations | BSTs | Triangulations |
|---|------|-------------------|------|----------------|
| 0 | 1 | (empty) | (empty) | (triangle) |
| 1 | 1 | () | o | 1 way |
| 2 | 2 | ()(), (()) | 2 trees | 2 ways |
| 3 | 5 | 5 strings | 5 trees | 5 ways |
| 4 | 14 | 14 strings | 14 trees | 14 ways |

**Complexity:**
- Formula: O(n) for binomial coefficient
- DP: O(n^2) time, O(n) space
- Generating all valid parenthesizations: O(C(n) * n)'''),

    ("thinking/algorithms", r'''Explain Stirling numbers of the second kind S(n, k): the number of ways to partition a set of n elements into exactly k non-empty subsets. Implement computation and show applications.''', r'''<think>
Stirling numbers of the second kind, denoted S(n, k) or {n brace k}, count the number of ways to partition a set of n elements into exactly k non-empty subsets (where the subsets are unordered).

Recurrence:
S(n, k) = k * S(n-1, k) + S(n-1, k-1)

Interpretation of recurrence:
- Consider element n. Either:
  1. Element n goes into one of the k existing subsets: k * S(n-1, k) ways (partition n-1 elements into k subsets, then place element n in any of the k subsets)
  2. Element n forms its own singleton subset: S(n-1, k-1) ways (partition remaining n-1 elements into k-1 subsets)

Base cases:
- S(0, 0) = 1 (empty partition of empty set)
- S(n, 0) = 0 for n > 0 (cannot partition non-empty set into 0 subsets)
- S(0, k) = 0 for k > 0
- S(n, 1) = 1 (one subset containing everything)
- S(n, n) = 1 (each element in its own subset)

Explicit formula:
S(n, k) = (1/k!) * sum_{j=0}^{k} (-1)^(k-j) * C(k,j) * j^n

This uses inclusion-exclusion: count surjections from n elements to k elements, then divide by k! since subsets are unordered.

Related: Bell numbers B(n) = sum of S(n, k) for k = 0..n, counting total partitions of n elements.

Applications:
- Set partitions in combinatorics
- Distribution of distinct objects into identical boxes
- Polynomial conversion between bases (x^n = sum of S(n,k) * x_falling_k)
</think>

**Stirling Numbers of the Second Kind**

```python
from math import comb, factorial


def stirling2_dp(n_max):
    """
    Compute Stirling numbers S(n, k) for 0 <= k <= n <= n_max.

    Returns 2D table where table[n][k] = S(n, k).
    """
    S = [[0] * (n_max + 1) for _ in range(n_max + 1)]
    S[0][0] = 1

    for n in range(1, n_max + 1):
        for k in range(1, n + 1):
            S[n][k] = k * S[n - 1][k] + S[n - 1][k - 1]

    return S


def stirling2_formula(n, k):
    """Compute S(n, k) using inclusion-exclusion formula."""
    if k == 0:
        return 1 if n == 0 else 0
    result = 0
    for j in range(k + 1):
        sign = (-1) ** (k - j)
        result += sign * comb(k, j) * (j ** n)
    return result // factorial(k)


def bell_number(n, stirling_table):
    """Compute Bell number B(n) = sum of S(n, k) for k=0..n."""
    return sum(stirling_table[n][k] for k in range(n + 1))


def generate_partitions(elements, k):
    """Generate all partitions of elements into exactly k non-empty subsets."""
    n = len(elements)
    if k == 0:
        if n == 0:
            yield []
        return
    if k > n or n == 0:
        return

    elem = elements[0]
    rest = elements[1:]

    # Case 1: elem joins an existing partition
    for partition in generate_partitions(rest, k):
        for i in range(k):
            new_partition = [s[:] for s in partition]
            new_partition[i].append(elem)
            yield new_partition

    # Case 2: elem starts a new singleton partition
    for partition in generate_partitions(rest, k - 1):
        yield partition + [[elem]]


# Compute table
N = 8
S = stirling2_dp(N)

print("Stirling numbers S(n, k):")
print("n\\k", end="")
for k in range(N + 1):
    print(f"  {k:5d}", end="")
print()
for n in range(N + 1):
    print(f" {n} ", end="")
    for k in range(N + 1):
        print(f"  {S[n][k]:5d}", end="")
    print()

# Verify formula matches DP
print("\nVerification (formula vs DP):")
all_match = True
for n in range(7):
    for k in range(n + 1):
        formula = stirling2_formula(n, k)
        if formula != S[n][k]:
            print(f"  MISMATCH: S({n},{k}) dp={S[n][k]} formula={formula}")
            all_match = False
print(f"  All match: {all_match}")

# Bell numbers
print("\nBell numbers B(n):")
for n in range(N + 1):
    b = bell_number(n, S)
    print(f"  B({n}) = {b}")

# Show actual partitions for small example
print(f"\nPartitions of {{1,2,3,4}} into 2 subsets (S(4,2)={S[4][2]}):")
count = 0
for p in generate_partitions([1, 2, 3, 4], 2):
    # Normalize: sort each subset and sort by first element
    p_sorted = sorted([sorted(s) for s in p])
    print(f"  {p_sorted}")
    count += 1
print(f"  Total: {count}")
```

**Key Properties:**
- S(n, 1) = 1 (everything in one set)
- S(n, 2) = 2^(n-1) - 1
- S(n, n) = 1 (all singletons)
- S(n, n-1) = C(n, 2) (one pair, rest singletons)

**Recurrence Intuition:**
- S(n, k) = k * S(n-1, k) + S(n-1, k-1)
- Add element n to one of k existing groups: k choices
- OR make element n its own group: need k-1 groups for rest

**Complexity:**
- DP table: O(n^2) time and space
- Formula: O(k) per value
- Generating partitions: O(S(n,k) * n) total'''),
]
