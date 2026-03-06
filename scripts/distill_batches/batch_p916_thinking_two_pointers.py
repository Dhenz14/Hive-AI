PAIRS = [
    ("thinking/algorithms", r'''Solve the 3Sum problem: given an array of integers, find all unique triplets that sum to zero. Return them without duplicates.''', r'''<think>
The brute force approach checks all O(n^3) triplets. Could I use a hash set to reduce this? I could fix two elements and look up the third in O(1), giving O(n^2). But wait -- handling duplicates with a hash set is messy. I would need to track which triplets I have already seen, possibly using a set of tuples, which adds complexity and hidden constant factors.

A cleaner approach: sort the array first, then fix the first element and use two pointers for the remaining pair. After sorting, the two-pointer technique works because if the current sum is too small, moving lo right increases it, and if too large, moving hi left decreases it. This monotonicity is precisely why two pointers converge on all valid pairs in O(n) per fixed element.

Duplicate handling is the tricky part. I initially thought I could just use a result set to filter duplicates at the end. Actually, that would work but is wasteful -- since the array is sorted, I can skip duplicates inline. For the outer loop, if nums[i] == nums[i-1], I skip because all triplets starting with that value were already found. After finding a valid triplet, I advance both lo and hi past any duplicates. Hmm, but I need to be careful: the duplicate-skipping while loops must check lo < hi to avoid going out of bounds.

One more optimization: if nums[i] > 0 after sorting, then nums[lo] and nums[hi] are also positive (since lo > i and hi > lo), so the sum must be positive. Therefore we can break early. Similarly, I considered whether nums[i] + nums[n-1] + nums[n-2] < 0 means we should skip this i entirely, but that is an optimization that is not strictly necessary for correctness.

Time: O(n^2) -- sorting is O(n log n) which is dominated by the nested loop. Space: O(1) extra ignoring the output.
</think>

**3Sum -- Two Pointer Approach**

```python
def three_sum(nums):
    """
    Find all unique triplets summing to zero.

    Args:
        nums: list of integers
    Returns:
        list of triplets [a, b, c] where a + b + c = 0
    """
    nums.sort()
    n = len(nums)
    result = []

    for i in range(n - 2):
        # Skip duplicates for first element
        if i > 0 and nums[i] == nums[i - 1]:
            continue

        # Early termination: if smallest is positive, no solution
        if nums[i] > 0:
            break

        lo, hi = i + 1, n - 1

        while lo < hi:
            total = nums[i] + nums[lo] + nums[hi]

            if total < 0:
                lo += 1
            elif total > 0:
                hi -= 1
            else:
                result.append([nums[i], nums[lo], nums[hi]])
                # Skip duplicates
                while lo < hi and nums[lo] == nums[lo + 1]:
                    lo += 1
                while lo < hi and nums[hi] == nums[hi - 1]:
                    hi -= 1
                lo += 1
                hi -= 1

    return result


# Example
nums = [-1, 0, 1, 2, -1, -4]
print(f"Input: {nums}")
triplets = three_sum(nums)
print(f"Triplets summing to 0:")
for t in triplets:
    print(f"  {t}")

# Edge cases
print(f"\nAll zeros: {three_sum([0, 0, 0, 0])}")
print(f"No solution: {three_sum([1, 2, 3])}")
print(f"Duplicates: {three_sum([-2, 0, 0, 2, 2])}")
```

**Output:**
```
Input: [-1, 0, 1, 2, -1, -4]
Triplets summing to 0:
  [-1, -1, 2]
  [-1, 0, 1]
```

**Complexity:**
- Time: O(n^2) -- sorting O(n log n) + nested loop O(n^2)
- Space: O(1) extra (excluding output)

**Common Pitfalls:**
- Forgetting to skip duplicates at all three positions
- Off-by-one errors when skipping duplicates (check lo < hi)
- Not sorting the array first'''),

    ("thinking/algorithms", r'''Solve the Container With Most Water problem: given an array of heights, find two lines that together with the x-axis form a container holding the most water. Return the maximum area.''', r'''<think>
We need to maximize min(heights[i], heights[j]) * (j - i). The brute force checks all O(n^2) pairs. Could I use dynamic programming here? Hmm, it is hard to define useful subproblems because the area depends on both the distance and the minimum height, and there is no obvious overlapping structure.

Two pointers starting from the widest container (lo=0, hi=n-1) and working inward seems promising. But the key question is: which pointer do we move? My first instinct was to move whichever pointer points to the smaller absolute height. But wait, I need to think about why this is correct -- it feels greedy and greedy approaches require proof.

Suppose heights[lo] < heights[hi]. Consider all containers that include lo: (lo, hi), (lo, hi-1), (lo, hi-2), etc. Every one of them has height bounded by heights[lo] since it is the shorter side. And every one with j < hi has strictly smaller width. Therefore the area for any (lo, j < hi) is strictly less than the area for (lo, hi). So we have already found the best container involving lo, and we can safely discard it by moving lo right.

Actually, I initially worried about the case when heights[lo] == heights[hi]. In that case, moving either pointer is safe by the same argument -- both pointers have been maximized for their respective pairings. Some implementations move the left pointer; others move either. It does not matter for correctness.

One more edge case I considered: what if there is one extremely tall line in the middle and two short ones at the edges? The algorithm still works because it will eventually reach the tall line from both sides before the pointers converge, since it only eliminates the shorter side at each step.

Time: O(n) because each pointer moves at most n times total. Space: O(1).
</think>

**Container With Most Water -- Two Pointers**

```python
def max_area(heights):
    """
    Find maximum water container area.

    Args:
        heights: list of non-negative integers
    Returns:
        maximum area
    """
    lo, hi = 0, len(heights) - 1
    best = 0

    while lo < hi:
        width = hi - lo
        h = min(heights[lo], heights[hi])
        area = width * h
        best = max(best, area)

        # Move the shorter line inward
        if heights[lo] < heights[hi]:
            lo += 1
        else:
            hi -= 1

    return best


# Example
heights = [1, 8, 6, 2, 5, 4, 8, 3, 7]
result = max_area(heights)
print(f"Heights: {heights}")
print(f"Max area: {result}")

# Trace the algorithm
lo, hi = 0, len(heights) - 1
print("\nStep-by-step:")
while lo < hi:
    area = min(heights[lo], heights[hi]) * (hi - lo)
    shorter = "left" if heights[lo] < heights[hi] else "right"
    print(f"  lo={lo}(h={heights[lo]}) hi={hi}(h={heights[hi]}) "
          f"area={area} -> move {shorter}")
    if heights[lo] < heights[hi]:
        lo += 1
    else:
        hi -= 1
```

**Output:**
```
Heights: [1, 8, 6, 2, 5, 4, 8, 3, 7]
Max area: 49
```

The optimal container uses lines at index 1 (height 8) and index 8 (height 7): min(8,7) * (8-1) = 49.

**Correctness Proof Sketch:**
- We never skip a pair that could be optimal
- When heights[lo] <= heights[hi], any pair (lo, j) with j < hi has smaller width AND height bounded by heights[lo], so area is strictly smaller
- Thus discarding lo is safe. Symmetric argument for hi.

**Complexity:**
- Time: O(n) -- each pointer moves at most n times
- Space: O(1)'''),

    ("thinking/algorithms", r'''Solve the Trapping Rain Water problem: given an elevation map represented by an array of non-negative integers, compute how much water can be trapped after raining.''', r'''<think>
The water above each position i is min(max_left, max_right) - height[i]. My first approach would be to precompute left_max[i] and right_max[i] arrays, then sum up the water. That gives O(n) time but O(n) space. Could I do better on space?

I considered using a stack-based approach where I process bars and compute water when I find a taller bar to the right. But wait -- that computes water "horizontally" (layer by layer) rather than "vertically" (column by column), and while it works, it is harder to reason about correctness.

The two-pointer approach is more elegant. The key insight took me a moment: if left_max <= right_max, then the water at the left pointer is determined solely by left_max, regardless of what lies beyond the right pointer. Why? Because the actual maximum to the right of lo is >= right_max (since right_max tracks the max we have seen so far from the right side, and there could be taller bars further left that we have not reached yet). Hmm, actually I need to think about this more carefully. The right_max variable is the maximum of height[hi], height[hi+1], ..., height[n-1] -- everything to the right of hi has already been scanned. So the true right maximum for position lo is at least right_max. Therefore min(left_max, true_right_max) = left_max when left_max <= right_max. That confirms the water calculation is correct.

One subtlety: when I advance lo, I update left_max first, then compute water as left_max - height[lo]. Since left_max = max(left_max, height[lo]), this means water = left_max - height[lo] which is always >= 0. I initially had the update and water computation in the wrong order, but actually it does not matter because if height[lo] > left_max, then the new left_max equals height[lo] and the water contribution is zero.

Edge cases: arrays shorter than 3 cannot trap any water, and monotonically increasing or decreasing arrays also trap nothing because one side always has no barrier.

Time: O(n), Space: O(1).
</think>

**Trapping Rain Water -- Two Pointer Solution**

```python
def trap_water(height):
    """
    Compute trapped rainwater.

    Args:
        height: list of non-negative integers (elevation map)
    Returns:
        total units of trapped water
    """
    if len(height) < 3:
        return 0

    lo, hi = 0, len(height) - 1
    left_max, right_max = height[lo], height[hi]
    water = 0

    while lo < hi:
        if left_max <= right_max:
            lo += 1
            left_max = max(left_max, height[lo])
            water += left_max - height[lo]
        else:
            hi -= 1
            right_max = max(right_max, height[hi])
            water += right_max - height[hi]

    return water


def trap_water_dp(height):
    """O(n) time, O(n) space DP approach for comparison."""
    n = len(height)
    if n < 3:
        return 0

    left_max = [0] * n
    right_max = [0] * n

    left_max[0] = height[0]
    for i in range(1, n):
        left_max[i] = max(left_max[i - 1], height[i])

    right_max[n - 1] = height[n - 1]
    for i in range(n - 2, -1, -1):
        right_max[i] = max(right_max[i + 1], height[i])

    water = 0
    for i in range(n):
        water += min(left_max[i], right_max[i]) - height[i]

    return water


# Example
height = [0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1]
print(f"Height map: {height}")
print(f"Trapped water (two-pointer): {trap_water(height)}")
print(f"Trapped water (DP):          {trap_water_dp(height)}")

# Visualize
max_h = max(height)
print("\nVisualization (# = wall, ~ = water):")
for level in range(max_h, 0, -1):
    row = ""
    for h in height:
        if h >= level:
            row += "#"
        else:
            row += " "
    # Fill water: between walls
    filled = list(row)
    first_wall = row.find("#")
    last_wall = row.rfind("#")
    for i in range(first_wall, last_wall + 1):
        if filled[i] == " ":
            filled[i] = "~"
    print(f"  {''.join(filled)}")
```

**Output:**
```
Height map: [0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1]
Trapped water (two-pointer): 6
Trapped water (DP):          6
```

**Why Two Pointers Work:**
- At each step, we process the side with the smaller known maximum
- If left_max <= right_max, the water at lo depends only on left_max (the actual right max is >= right_max >= left_max)
- This invariant guarantees correctness without needing the full arrays

**Complexity:**
- Two-pointer: O(n) time, O(1) space
- DP approach: O(n) time, O(n) space'''),

    ("thinking/algorithms", r'''Solve Remove Duplicates from Sorted Array in-place: given a sorted array, remove duplicates such that each element appears only once. Return the new length. Modify the array in-place with O(1) extra memory.''', r'''<think>
The array is sorted, so duplicates are adjacent. My first thought was to use a set to track seen elements, but wait -- that would use O(n) extra space and the problem requires O(1). Since the array is sorted, I do not need a set at all; I just need to compare adjacent elements.

I considered using Python's built-in list operations like `del` to remove duplicates in place. But that would be O(n^2) because each deletion shifts all subsequent elements. The read/write pointer technique avoids this entirely: the write pointer marks where the next unique element should go, and the read pointer scans forward.

The comparison should be nums[read] != nums[write-1] rather than nums[read] != nums[read-1]. Hmm, does it matter? Actually for the basic version they produce the same result because write always trails or equals read, and we only write unique values. But the nums[write-1] comparison is more general -- it naturally extends to "allow at most k duplicates" by comparing nums[read] with nums[write-k]. I initially did not see this generalization, but it is elegant: the invariant is that nums[0..write-1] contains the processed result, and we check whether the new element would create more than k consecutive copies by looking back k positions in the output.

One edge case worth noting: if the array is empty, we should return 0 immediately. And if write equals n at the end, there were no duplicates at all. The algorithm handles both cases naturally without special-casing, since the loop simply does not execute for length-0 or length-1 arrays.

Time: O(n) single pass. Space: O(1) in-place.
</think>

**Remove Duplicates from Sorted Array -- Two Pointer (Read/Write)**

```python
def remove_duplicates(nums):
    """
    Remove duplicates in-place from sorted array.

    Args:
        nums: sorted list of integers (modified in-place)
    Returns:
        length of array after deduplication
    """
    if not nums:
        return 0

    write = 1

    for read in range(1, len(nums)):
        if nums[read] != nums[write - 1]:
            nums[write] = nums[read]
            write += 1

    return write


def remove_duplicates_allow_k(nums, k=2):
    """
    Generalized: allow each element at most k times.

    Works for any k >= 1.
    """
    if len(nums) <= k:
        return len(nums)

    write = k

    for read in range(k, len(nums)):
        if nums[read] != nums[write - k]:
            nums[write] = nums[read]
            write += 1

    return write


# Example 1: Remove all duplicates
nums = [0, 0, 1, 1, 1, 2, 2, 3, 3, 4]
print(f"Original: {nums}")
new_len = remove_duplicates(nums)
print(f"After dedup: {nums[:new_len]} (length={new_len})")

# Example 2: Allow at most 2 duplicates
nums2 = [1, 1, 1, 2, 2, 3]
print(f"\nOriginal: {nums2}")
new_len2 = remove_duplicates_allow_k(nums2, k=2)
print(f"Allow 2 dupes: {nums2[:new_len2]} (length={new_len2})")

# Edge cases
for test in [[], [1], [1, 1], [1, 2, 3]]:
    arr = test[:]
    length = remove_duplicates(arr)
    print(f"  {test} -> {arr[:length]}")
```

**Output:**
```
Original: [0, 0, 1, 1, 1, 2, 2, 3, 3, 4]
After dedup: [0, 1, 2, 3, 4] (length=5)

Original: [1, 1, 1, 2, 2, 3]
Allow 2 dupes: [1, 1, 2, 2, 3] (length=5)
```

**Pattern -- Read/Write Pointers:**
This is a fundamental pattern for in-place array transformations:
- `read` scans every element
- `write` only advances when we keep an element
- Everything before `write` is the processed result

The generalization to "allow k duplicates" is elegant: just compare nums[read] with nums[write - k] instead of nums[write - 1].

**Complexity:**
- Time: O(n) -- single pass
- Space: O(1) -- in-place modification'''),

    ("thinking/algorithms", r'''Solve the Partition Labels problem: given a string s, partition it into as many parts as possible so that each letter appears in at most one part. Return a list of the sizes of these parts.''', r'''<think>
We need to partition the string so no character spans multiple partitions, while maximizing the number of partitions. I first considered an interval-merging approach: treat each character's range [first_occurrence, last_occurrence] as an interval, merge overlapping intervals, and each merged interval becomes a partition. That would work, but could be overkill since we would need to sort the intervals.

Actually, a simpler greedy approach works. First pass: record the last occurrence of each character. Second pass: scan left to right, maintaining the farthest "last occurrence" of any character seen so far in the current partition. When the scan position i reaches this farthest point (i == end), we know every character in the current partition has its final appearance within [start, end], so we can safely cut here.

But wait -- is this actually optimal? Could cutting later sometimes yield more partitions? Hmm, no. Cutting later would merge the current partition with the next one, reducing the total count. Since we cut at the earliest safe position, we leave the maximum remaining string for subsequent partitions. This greedy choice is locally optimal and does not constrain future choices, so it produces the global optimum.

I briefly considered whether we need to handle overlapping character ranges explicitly. For example, if character 'a' spans [0, 5] and 'b' spans [2, 8], the partition must extend to at least 8 once we encounter 'b'. The algorithm handles this naturally because when we scan position 2 and see 'b', we update end = max(end, last['b']) = max(5, 8) = 8. Therefore the merging happens implicitly without needing a separate interval-merging step.

Time: O(n) for two passes. Space: O(1) since the last-occurrence map has at most 26 entries for lowercase letters.
</think>

**Partition Labels -- Greedy with Last Occurrence**

```python
def partition_labels(s):
    """
    Partition string so each letter appears in at most one part.

    Args:
        s: string of lowercase letters
    Returns:
        list of partition sizes
    """
    # Step 1: Record last occurrence of each character
    last = {}
    for i, ch in enumerate(s):
        last[ch] = i

    # Step 2: Greedily partition
    partitions = []
    start = 0
    end = 0

    for i, ch in enumerate(s):
        end = max(end, last[ch])

        if i == end:
            partitions.append(end - start + 1)
            start = end + 1

    return partitions


# Example
s = "ababcbacadefegdehijhklij"
result = partition_labels(s)
print(f"String: {s}")
print(f"Partition sizes: {result}")

# Show the actual partitions
idx = 0
parts = []
for size in result:
    parts.append(s[idx:idx + size])
    idx += size
print(f"Partitions: {parts}")

# Verify: no character spans multiple partitions
print("\nVerification:")
for i, part in enumerate(parts):
    chars = set(part)
    other_chars = set()
    for j, other in enumerate(parts):
        if j != i:
            other_chars |= set(other)
    overlap = chars & other_chars
    status = "PASS" if not overlap else f"FAIL (overlap: {overlap})"
    print(f"  Part {i} '{part}': chars={chars} -> {status}")

# More examples
for test in ["eccbbbbdec", "abcabc", "abcdef"]:
    r = partition_labels(test)
    idx = 0
    ps = []
    for sz in r:
        ps.append(test[idx:idx+sz])
        idx += sz
    print(f"\n'{test}' -> sizes={r} parts={ps}")
```

**Output:**
```
String: ababcbacadefegdehijhklij
Partition sizes: [9, 7, 8]
Partitions: ['ababcbaca', 'defegde', 'hijhklij']
```

**Algorithm Walkthrough (first example):**
1. Build last occurrence map: a->8, b->5, c->7, d->14, e->15, f->11, g->13, h->19, i->22, j->23, k->20, l->21
2. Scan: at i=0 (a), end=8. At i=5 (b), end stays 8. At i=7 (c), end stays 8. At i=8, i==end, cut partition [0..8] size 9.
3. Continue similarly for remaining characters.

**Greedy Correctness:**
- We extend each partition to the minimum possible: the farthest last-occurrence of any character seen so far
- Cutting at i==end is the earliest safe cut point
- This maximizes the number of partitions

**Complexity:**
- Time: O(n) -- two passes
- Space: O(1) -- at most 26 character entries'''),
]
