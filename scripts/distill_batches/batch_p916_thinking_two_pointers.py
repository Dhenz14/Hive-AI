PAIRS = [
    ("thinking/algorithms", r'''Solve the 3Sum problem: given an array of integers, find all unique triplets that sum to zero. Return them without duplicates.''', r'''<think>
The 3Sum problem is a classic two-pointer application. The brute force O(n^3) approach checks all triplets, but we can do O(n^2) by sorting and using two pointers.

Strategy:
1. Sort the array
2. Fix the first element (index i), then use two pointers (lo, hi) to find pairs that sum to -nums[i]
3. Skip duplicates at each level to avoid repeated triplets

Why sorting helps: After sorting, we can use the two-pointer technique on the remaining subarray. If the current sum is too small, move the left pointer right. If too large, move the right pointer left.

Duplicate handling is the tricky part:
- Skip duplicate values for i: if nums[i] == nums[i-1], skip (we already found all triplets starting with that value)
- After finding a valid triplet, skip duplicates for both lo and hi pointers

Edge cases:
- Array with fewer than 3 elements: return []
- All zeros: [0, 0, 0] is the only triplet
- No valid triplets exist
- Array with many duplicates

Early termination: if nums[i] > 0, no triplet starting from i can sum to 0 (since lo, hi are larger), so break.

Time: O(n^2) -- outer loop O(n), inner two-pointer scan O(n).
Space: O(1) extra (ignoring output and sort space).

This is a foundational pattern. Many problems (4Sum, closest sum) build on this template.
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
This is LeetCode 11. We have vertical lines at positions 0..n-1 with heights[i]. We need to find i, j that maximize min(heights[i], heights[j]) * (j - i).

Brute force: O(n^2) -- check all pairs. But we can do O(n) with two pointers.

Two-pointer approach:
- Start with lo=0, hi=n-1 (widest container)
- Compute area = min(heights[lo], heights[hi]) * (hi - lo)
- Move the pointer that points to the shorter line inward

Why move the shorter line? The area is limited by the shorter line. If we move the taller line inward, the width decreases and the height cannot increase beyond the shorter line -- so the area can only decrease or stay the same. Moving the shorter line gives us a chance to find a taller line that might increase the area.

More formally: suppose heights[lo] < heights[hi]. Any container using lo with a different right boundary j < hi will have:
- Smaller width (j - lo < hi - lo)
- Height still bounded by heights[lo]
- Therefore strictly smaller area

So we can safely eliminate lo from further consideration. This is the key insight that makes the greedy approach correct.

Edge cases:
- Two elements: only one possible container
- All same height: first and last give max area (widest)
- Decreasing heights: optimal might not be the widest
- One very tall line in the middle

Time: O(n), Space: O(1).
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
Trapping Rain Water (LeetCode 42) is a classic problem with multiple approaches. I will show the two-pointer O(n) time O(1) space solution.

Key insight: The water above position i is determined by min(max_left, max_right) - height[i], where max_left and max_right are the tallest bars to the left and right of i respectively.

Approach 1 -- Precompute arrays:
- left_max[i] = max of heights[0..i]
- right_max[i] = max of heights[i..n-1]
- water[i] = max(0, min(left_max[i], right_max[i]) - height[i])
- O(n) time, O(n) space

Approach 2 -- Two pointers (optimal):
- Maintain lo, hi pointers and left_max, right_max
- If left_max <= right_max, the water at lo is determined by left_max (regardless of what is beyond hi, right_max is already >= left_max, so the true right max is also >= left_max)
- Process the side with the smaller max

Why does this work? At each step:
- If left_max <= right_max, we know the bottleneck at lo is left_max (true right max >= right_max >= left_max)
- Water at lo = left_max - height[lo] (if positive)
- Move lo right. Symmetrically for the other side.

Edge cases:
- Array of length < 3: no water can be trapped
- Flat array: no water
- V-shaped: water in the middle
- Monotonically increasing or decreasing: no water

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
This is LeetCode 26. The array is sorted, so duplicates are adjacent. We use a two-pointer (read/write) approach.

The idea is simple:
- Pointer `write` tracks where to place the next unique element
- Pointer `read` scans through the array
- When nums[read] != nums[write-1], we found a new unique element; write it at position `write` and advance `write`

Since the array is sorted, we only need to compare with the last written element. This is a classic in-place deduplication pattern.

Algorithm:
1. If array is empty, return 0
2. Set write = 1 (first element is always unique)
3. For read from 1 to n-1:
   - If nums[read] != nums[write-1], set nums[write] = nums[read], increment write
4. Return write

This naturally extends to "allow at most k duplicates" by comparing nums[read] with nums[write-k].

Edge cases:
- Empty array
- Single element
- All identical elements
- Already unique (no duplicates)
- Two elements, same or different

Time: O(n), Space: O(1). Single pass through the array.
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
This is LeetCode 763. We need to partition the string so that no character appears in more than one partition, and we want the maximum number of partitions.

Key insight: For each character, we must include all its occurrences in the same partition. So the partition containing the first occurrence of a character must extend at least to its last occurrence.

Greedy approach:
1. First pass: record the last occurrence index of each character
2. Second pass: use two pointers/variables to track the current partition
   - start = beginning of current partition
   - end = the farthest last-occurrence we have seen so far in this partition
   - When i == end, we have reached the end of the current partition (all characters in [start, end] have their last occurrence within this range)
   - Record the partition size (end - start + 1) and start a new partition

Why this works: As we scan, we expand `end` to include the last occurrence of every character we encounter. Once we reach index i == end, we know no character in the current partition appears later -- so we can safely cut here.

This is optimal because we cut as early as possible, maximizing the number of partitions.

Edge cases:
- Single character string: one partition of size 1
- All same characters: one partition of the full length
- All unique characters: each character is its own partition
- String of length 1

Time: O(n), Space: O(1) -- the last-occurrence map has at most 26 entries.
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
