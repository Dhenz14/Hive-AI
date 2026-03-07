"""
Code explanation training pairs - Python algorithm implementations
"""

pairs = [
    {
        "instruction": r'''Walk me through this Python function:

```python
def kadane(arr):
    max_ending_here = max_so_far = arr[0]
    start = end = s = 0
    for i in range(1, len(arr)):
        if arr[i] > max_ending_here + arr[i]:
            max_ending_here = arr[i]
            s = i
        else:
            max_ending_here += arr[i]
        if max_ending_here > max_so_far:
            max_so_far = max_ending_here
            start = s
            end = i
    return max_so_far, arr[start:end+1]
```''',
        "output": r'''This is Kadane's algorithm for finding the maximum subarray -- the contiguous slice of an array whose elements sum to the largest possible value.

**How it works step by step:**

1. It initializes two trackers: `max_ending_here` (the best sum ending at the current position) and `max_so_far` (the global best). Both start at `arr[0]`.

2. For each element from index 1 onward, it makes a decision: is it better to extend the current subarray by adding `arr[i]`, or start a brand new subarray beginning at `arr[i]`? That is the `if arr[i] > max_ending_here + arr[i]` check -- which simplifies to "is `max_ending_here` negative?"

3. If starting fresh is better, it resets the tentative start index `s` to `i`.

4. Whenever `max_ending_here` beats `max_so_far`, it updates the global best and locks in the `start` and `end` indices.

**Key insight:** The algorithm runs in O(n) time with O(1) space. The naive approach of checking all subarrays would be O(n^2) or O(n^3).

**Edge case to note:** If the input array is all negative numbers, this correctly returns the single least-negative element -- it does not return 0 or an empty subarray. However, it will crash on an empty array since `arr[0]` would raise an IndexError.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain this binary search implementation.
I should identify the variant -- this looks like it finds the leftmost insertion point.
I need to explain the loop invariant and why it uses lo < hi instead of lo <= hi.
</think>

What does this code do?

```python
def bisect_left(a, x, lo=0, hi=None):
    if hi is None:
        hi = len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo
```''',
        "output": r'''<think>
This is the standard library bisect_left implementation. I should explain the loop invariant, what "leftmost" means, and how the boundary updates maintain correctness.
</think>

This is a left-biased binary search -- it finds the leftmost position where `x` could be inserted into sorted array `a` while maintaining sort order.

**Step by step:**

1. `lo` and `hi` define a half-open range `[lo, hi)` -- the search space.

2. Each iteration computes the midpoint. If `a[mid] < x`, everything at or before `mid` is too small, so `lo` moves to `mid + 1`. Otherwise, `mid` might be the answer, so `hi` moves to `mid` (not `mid - 1` -- this is crucial for finding the leftmost match).

3. The loop ends when `lo == hi`, and that position is returned.

**Why `lo < hi` instead of `lo <= hi`?** This variant maintains the invariant that the answer is always in `[lo, hi)`. When the range collapses to a single point, that point is the answer. There is no risk of infinite loops because either `lo` increases or `hi` decreases each iteration.

**Key behavior:** If `x` already exists in the array, this returns the index of the first occurrence, not just any occurrence. If `x` is not in the array, it returns where `x` would go. This makes it useful for both searching and maintaining sorted insertion order.

The `hi=None` defaulting to `len(a)` lets callers search the full array without knowing its length upfront.'''
    },
    {
        "instruction": r'''Explain this function to me:

```python
def lcs(s1, s2):
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i-1] == s2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    result = []
    i, j = m, n
    while i > 0 and j > 0:
        if s1[i-1] == s2[j-1]:
            result.append(s1[i-1])
            i -= 1
            j -= 1
        elif dp[i-1][j] > dp[i][j-1]:
            i -= 1
        else:
            j -= 1
    return ''.join(reversed(result))
```''',
        "output": r'''This computes the Longest Common Subsequence (LCS) of two strings -- the longest sequence of characters that appears in both strings in the same order, but not necessarily contiguously.

**Phase 1 -- Building the DP table:**

The 2D table `dp[i][j]` stores the LCS length for `s1[:i]` and `s2[:j]`. The extra row/column of zeros handles the base case (empty string has LCS length 0 with anything).

For each pair (i, j):
- If the characters match (`s1[i-1] == s2[j-1]`), extend the LCS by 1 from the diagonal `dp[i-1][j-1]`.
- If they do not match, take the better result from either dropping a character from s1 (`dp[i-1][j]`) or from s2 (`dp[i][j-1]`).

**Phase 2 -- Backtracking to reconstruct the actual subsequence:**

Starting from `dp[m][n]`, it traces back through the table. When characters match, that character is part of the LCS. Otherwise, it moves toward the larger neighbor. The result is built in reverse, so it gets reversed at the end.

**Complexity:** O(m * n) time and space. The space could be optimized to O(min(m, n)) if you only need the length, but reconstruction requires the full table.

**Note:** When `dp[i-1][j] == dp[i][j-1]`, the `else` branch arbitrarily goes right (decrements j). This means the function returns one valid LCS, but there may be others of the same length.'''
    },
    {
        "instruction": r'''<think>
The user is asking about a topological sort implementation. Let me trace through the algorithm and identify the approach used.
</think>

Can you walk me through how this topological sort works?

```python
from collections import deque, defaultdict

def topo_sort(num_nodes, edges):
    graph = defaultdict(list)
    in_degree = [0] * num_nodes
    for u, v in edges:
        graph[u].append(v)
        in_degree[v] += 1
    queue = deque(i for i in range(num_nodes) if in_degree[i] == 0)
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    if len(order) != num_nodes:
        raise ValueError("Graph has a cycle")
    return order
```''',
        "output": r'''<think>
This is Kahn's algorithm for topological sorting. I should explain the in-degree approach, contrast it with DFS-based topo sort, and highlight the cycle detection.
</think>

This is Kahn's algorithm for topological sorting -- it orders nodes in a directed acyclic graph (DAG) so that for every edge u -> v, u comes before v.

**Setup phase:**
- Builds an adjacency list (`graph`) and counts incoming edges for each node (`in_degree`).
- Seeds the queue with all nodes that have zero incoming edges -- these have no dependencies and can go first.

**Processing phase:**
- Pops a node from the queue and adds it to the result.
- For each neighbor of that node, decrements its in-degree (conceptually "removing" the edge). If a neighbor's in-degree drops to zero, it has no remaining dependencies and enters the queue.
- Repeats until the queue is empty.

**Cycle detection:**
The clever part is the final check: `len(order) != num_nodes`. If there is a cycle, some nodes will always have in-degree > 0 (they depend on each other circularly), so they never enter the queue and never appear in `order`. This makes cycle detection essentially free.

**Time complexity:** O(V + E) -- each node and edge is processed exactly once.

**Behavior note:** Using `deque` with `popleft()` gives a BFS-like ordering. If you used a min-heap instead of a deque, you would get the lexicographically smallest topological order, which some problems require.'''
    },
    {
        "instruction": r'''What does this function do? I found it in a utils module.

```python
def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return _merge(left, right)

def _merge(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result
```''',
        "output": r'''This is a classic merge sort implementation -- a divide-and-conquer sorting algorithm.

**`merge_sort` function:**
1. Base case: arrays of length 0 or 1 are already sorted, so return them as-is.
2. Splits the array in half at the midpoint.
3. Recursively sorts each half.
4. Merges the two sorted halves back together via `_merge`.

**`_merge` function:**
Uses two pointers (`i` and `j`) to walk through the sorted left and right arrays simultaneously. At each step, it picks the smaller of the two current elements and appends it to the result. When one array is exhausted, `extend` appends whatever remains from the other.

**Key detail:** The `<=` comparison (not `<`) makes this a stable sort -- equal elements maintain their original relative order. This matters when sorting objects by one key while preserving a previous sort on another key.

**Performance:** O(n log n) time in all cases (best, average, worst). This is better than quicksort's worst case of O(n^2). The tradeoff is O(n) extra space for the temporary arrays, whereas quicksort sorts in-place.

**Practical note:** This implementation creates many intermediate lists via slicing (`arr[:mid]`, `arr[mid:]`), which adds overhead. An in-place variant using indices would be more memory-efficient but harder to read. Python's built-in `sorted()` uses Timsort, which is a hybrid of merge sort and insertion sort.'''
    },
]
