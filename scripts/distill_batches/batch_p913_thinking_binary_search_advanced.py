PAIRS = [
    ("thinking/algorithms", r'''Search for a target value in a rotated sorted array. The array was originally sorted in ascending order, then rotated at some pivot. You must achieve O(log n) time. The array contains no duplicates.

Example: nums = [4,5,6,7,0,1,2], target = 0 -> Output: 4 (index of 0)''', r'''<think>
Classic binary search variant. The key observation: even though the array is rotated, at least one half of any binary search window is always sorted.

When we look at mid:
- If nums[left] <= nums[mid]: the left half [left, mid] is sorted
  - If target is in range [nums[left], nums[mid]): search left
  - Otherwise: search right
- Else: the right half [mid, right] is sorted
  - If target is in range (nums[mid], nums[right]]: search right
  - Otherwise: search left

Why does this work? A rotation creates at most one "break point." In any window, the break point is in at most one half, so the other half must be perfectly sorted. We can check if the target falls in the sorted half using simple comparisons.

Edge cases to think about:
- Array not rotated at all (rotation by 0)
- Single element
- Target not found
- Target at the rotation point

Let me be careful with the bounds. I'll use inclusive [lo, hi].

Tracing [4,5,6,7,0,1,2], target=0:
- lo=0, hi=6, mid=3. nums[3]=7. Left half [4,5,6,7] is sorted (4<=7). Target 0 not in [4,7], go right.
- lo=4, hi=6, mid=5. nums[5]=1. Left half nums[4]=0 <= 1, sorted. Target 0 in [0,1]? Yes (0 >= 0 and 0 < 1). Go left.
- lo=4, hi=4, mid=4. nums[4]=0 == target. Return 4. ✓
</think>

## Search in Rotated Sorted Array — O(log n)

```python
from typing import List


def search_rotated(nums: List[int], target: int) -> int:
    """Binary search in a rotated sorted array (no duplicates).

    Time Complexity: O(log n)
    Space Complexity: O(1)
    """
    lo, hi = 0, len(nums) - 1

    while lo <= hi:
        mid = (lo + hi) // 2

        if nums[mid] == target:
            return mid

        # Determine which half is sorted
        if nums[lo] <= nums[mid]:
            # Left half [lo, mid] is sorted
            if nums[lo] <= target < nums[mid]:
                hi = mid - 1  # Target in sorted left half
            else:
                lo = mid + 1  # Target in right half
        else:
            # Right half [mid, hi] is sorted
            if nums[mid] < target <= nums[hi]:
                lo = mid + 1  # Target in sorted right half
            else:
                hi = mid - 1  # Target in left half

    return -1  # Not found


# --- Tests ---
def test_example():
    assert search_rotated([4, 5, 6, 7, 0, 1, 2], 0) == 4

def test_not_found():
    assert search_rotated([4, 5, 6, 7, 0, 1, 2], 3) == -1

def test_not_rotated():
    assert search_rotated([1, 2, 3, 4, 5], 3) == 2

def test_single():
    assert search_rotated([1], 1) == 0
    assert search_rotated([1], 0) == -1

def test_two_elements():
    assert search_rotated([3, 1], 1) == 1
    assert search_rotated([3, 1], 3) == 0

def test_first_last():
    nums = [4, 5, 6, 7, 0, 1, 2]
    assert search_rotated(nums, 4) == 0
    assert search_rotated(nums, 2) == 6

test_example()
test_not_found()
test_not_rotated()
test_single()
test_two_elements()
test_first_last()
print("All rotated array search tests passed!")
```

### Key Insight

In any subarray `[lo, hi]` of a rotated sorted array, the rotation point (if it exists) is in exactly one half. The other half is perfectly sorted. By checking `nums[lo] <= nums[mid]`, we determine which half is sorted, then check if our target falls within that sorted range. This gives us a definitive direction to search in each step, maintaining O(log n).
'''),

    ("thinking/algorithms", r'''Find a peak element in a 2D matrix. A peak is an element strictly greater than all its (up to 4) neighbors. The matrix borders are considered negative infinity. Guarantee: at least one peak exists. Find any peak in better than O(m*n) time.

Example: mat = [[1,4],[3,2]] -> (0,1) since mat[0][1]=4 is greater than all neighbors (1, 2, and borders).''', r'''<think>
Finding a peak in a 2D matrix efficiently is an interesting problem. Let me think about approaches.

**Brute force**: Check every cell. O(m*n).

**Binary search on columns** (O(m log n) or O(n log m)):
1. Pick the middle column `mid`.
2. Find the maximum element in that column: O(m).
3. Compare this max with its left and right neighbors.
   - If it's greater than both, it's a peak — done.
   - If the left neighbor is larger, a peak must exist in the left half.
   - If the right neighbor is larger, a peak must exist in the right half.

Why does this work? When the column max at row `r`, column `mid` has a larger right neighbor at (r, mid+1), we know:
- mat[r][mid+1] > mat[r][mid] >= mat[any other row][mid]
- So the right half has an element larger than everything in column mid
- By the "uphill walk" argument (start at the max element of any column, go to the larger neighbor, you eventually reach a peak since values can't increase forever in a bounded matrix), a peak exists in the right half.

Actually, the formal argument: take the global maximum of the right submatrix. It must be a peak because it's the maximum, so no neighbor is larger. But this doesn't quite work for the submatrix peak guarantee... Let me think again.

The correct argument: the maximum of column `mid` at row `r` satisfies mat[r][mid] >= mat[any row][mid]. If mat[r][mid+1] > mat[r][mid], then mat[r][mid+1] > mat[r][mid] >= all in column mid. Now in the submatrix right of mid, consider the global maximum. It's ≥ mat[r][mid+1], and since it's a global maximum in that submatrix, all its neighbors within the submatrix are ≤ it. Its left neighbor in column mid is ≤ column mid's max ≤ mat[r][mid] < mat[r][mid+1] ≤ global max. So the global max of the right submatrix is a peak of the original matrix.

Time: T(m, n) = T(m, n/2) + O(m) = O(m log n). We can also do O(n log m) by binary searching on rows.
</think>

## Find Peak Element in 2D Matrix — O(m log n)

```python
from typing import List, Tuple


def find_peak_2d(mat: List[List[int]]) -> Tuple[int, int]:
    """Find any peak element in a 2D matrix using binary search on columns.

    A peak is strictly greater than all its (up to 4) adjacent neighbors.
    Matrix borders are treated as -infinity.

    Time Complexity: O(m * log n) where m = rows, n = cols
    Space Complexity: O(1)
    """
    rows, cols = len(mat), len(mat[0])
    lo, hi = 0, cols - 1

    while lo <= hi:
        mid = (lo + hi) // 2

        # Find the maximum element in column `mid`
        max_row = 0
        for r in range(rows):
            if mat[r][mid] > mat[max_row][mid]:
                max_row = r

        val = mat[max_row][mid]
        left = mat[max_row][mid - 1] if mid > 0 else float('-inf')
        right = mat[max_row][mid + 1] if mid < cols - 1 else float('-inf')

        if val > left and val > right:
            return (max_row, mid)
        elif left > val:
            hi = mid - 1
        else:
            lo = mid + 1

    # Should never reach here if input guarantees a peak
    return (-1, -1)


def is_peak(mat: List[List[int]], r: int, c: int) -> bool:
    """Verify a position is a peak."""
    rows, cols = len(mat), len(mat[0])
    val = mat[r][c]
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols and mat[nr][nc] >= val:
            return False
    return True


# --- Tests ---
def test_small():
    mat = [[1, 4], [3, 2]]
    r, c = find_peak_2d(mat)
    assert is_peak(mat, r, c), f"({r},{c})={mat[r][c]} is not a peak"

def test_3x3():
    mat = [
        [1, 2, 3],
        [4, 9, 5],
        [6, 7, 8],
    ]
    r, c = find_peak_2d(mat)
    assert is_peak(mat, r, c), f"({r},{c})={mat[r][c]} is not a peak"

def test_single_row():
    mat = [[1, 5, 3, 4, 2]]
    r, c = find_peak_2d(mat)
    assert is_peak(mat, r, c)

def test_single_element():
    mat = [[42]]
    r, c = find_peak_2d(mat)
    assert (r, c) == (0, 0)

test_small()
test_3x3()
test_single_row()
test_single_element()
print("All 2D peak finding tests passed!")
```

### Correctness Argument

When we find the column max at `(max_row, mid)` and its right neighbor is larger:
1. `mat[max_row][mid+1] > mat[max_row][mid] >= mat[r][mid]` for all `r`
2. The global maximum of the right submatrix `M` satisfies `M >= mat[max_row][mid+1]`
3. `M` is greater than all its neighbors within the right submatrix (it's the max)
4. `M`'s left neighbor in column `mid` is at most the column max, which is < `M`
5. Therefore `M` is a peak of the original matrix

This guarantees we always eliminate half the columns safely.
'''),

    ("thinking/algorithms", r'''Koko loves eating bananas. There are n piles of bananas, where piles[i] is the number of bananas in the i-th pile. Koko can eat at most K bananas per hour from one pile. If a pile has fewer than K bananas, she eats it all and waits the rest of that hour. Given h hours total, find the minimum integer K such that she can eat all bananas within h hours.

Example: piles = [3,6,7,11], h = 8 -> K = 4''', r'''<think>
This is a classic "binary search on the answer" problem. We need to find the minimum eating speed K.

**Observation**: If Koko can finish with speed K, she can also finish with any speed > K. This monotonicity makes binary search applicable.

**For a given K**: The hours needed to eat pile of size p is ceil(p / K). Total hours = sum of ceil(p / K) for all piles. We need total <= h.

**Search space**:
- Minimum K = 1 (eat at least 1 per hour)
- Maximum K = max(piles) (at this speed, each pile takes 1 hour, so n hours total; since h >= n is guaranteed, this always works)

**Binary search**:
- lo = 1, hi = max(piles)
- mid = (lo + hi) // 2
- If can_finish(mid, h): try smaller -> hi = mid
- Else: need faster -> lo = mid + 1

**ceil(p / K)** without floating point: (p + K - 1) // K or equivalently -(-p // K) in Python.

Time: O(n * log(max_pile)) where n = number of piles.
Space: O(1).

Let me verify with the example: piles = [3,6,7,11], h = 8
- K=4: ceil(3/4)=1, ceil(6/4)=2, ceil(7/4)=2, ceil(11/4)=3. Total=8. OK!
- K=3: ceil(3/3)=1, ceil(6/3)=2, ceil(7/3)=3, ceil(11/3)=4. Total=10 > 8. Too slow.
So K=4 is correct.
</think>

## Koko Eating Bananas — Binary Search on Answer

```python
from typing import List
import math


def min_eating_speed(piles: List[int], h: int) -> int:
    """Find minimum eating speed K to finish all piles within h hours.

    Time Complexity: O(n * log(max_pile))
    Space Complexity: O(1)
    """
    def hours_needed(speed: int) -> int:
        """Total hours to eat all piles at given speed."""
        return sum((p + speed - 1) // speed for p in piles)

    lo, hi = 1, max(piles)

    while lo < hi:
        mid = (lo + hi) // 2
        if hours_needed(mid) <= h:
            hi = mid      # Can finish — try slower
        else:
            lo = mid + 1  # Too slow — need faster

    return lo


# --- Tests ---
def test_example():
    assert min_eating_speed([3, 6, 7, 11], 8) == 4

def test_tight():
    # 4 piles, 4 hours -> must eat max pile in 1 hour
    assert min_eating_speed([3, 6, 7, 11], 4) == 11

def test_generous_time():
    # Lots of time -> can eat slowly
    assert min_eating_speed([30, 11, 23, 4, 20], 30) == 4

def test_single_pile():
    # 10 bananas, 5 hours -> need speed 2
    assert min_eating_speed([10], 5) == 2
    # 10 bananas, 10 hours -> speed 1
    assert min_eating_speed([10], 10) == 1

test_example()
test_tight()
test_generous_time()
test_single_pile()
print("All Koko eating bananas tests passed!")
```

### Why Binary Search Works Here

The function `hours_needed(K)` is **monotonically non-increasing** in K:
- Higher speed -> fewer hours needed
- Lower speed -> more hours needed

We want the smallest K such that `hours_needed(K) <= h`. This is exactly the "leftmost true" binary search pattern:

```
K:     1  2  3  4  5  6  ...  11
OK?:   F  F  F  T  T  T  ...  T
                ^--- find this boundary
```

The search range is [1, max(piles)], giving O(log(max_pile)) iterations. Each iteration scans all n piles, yielding O(n log(max_pile)) total.
'''),

    ("thinking/algorithms", r'''Split Array Largest Sum: Given an integer array nums and an integer k, split the array into k non-empty contiguous subarrays such that the largest sum among these subarrays is minimized. Return this minimized largest sum.

Example: nums = [7,2,5,10,8], k = 2 -> Output: 18 (split as [7,2,5] and [10,8], sums are 14 and 18, max is 18. Any other split gives a larger max.)''', r'''<think>
This is another "binary search on the answer" problem, similar to Koko's bananas.

**Key insight**: We're minimizing the maximum subarray sum. If we can achieve a maximum of M, we can certainly achieve any maximum > M. So the feasibility function is monotonic.

**Feasibility check**: Given a maximum allowed sum M, can we split the array into at most k subarrays each with sum <= M?
- Greedy: scan left to right, accumulate sum. When adding the next element would exceed M, start a new subarray. Count subarrays used. If count <= k, feasible.

**Search space**:
- lo = max(nums) — each element must fit in some subarray, so M >= max element
- hi = sum(nums) — entire array in one subarray (k=1 case)

**Binary search** for the minimum M such that feasible(M) is true.

Time: O(n * log(sum - max)) where n = len(nums).

Let me verify: nums = [7,2,5,10,8], k = 2
- lo = 10, hi = 32
- mid = 21: greedy with max 21 -> [7,2,5,10]=24 > 21, so [7,2,5]=14, [10,8]=18. 2 subarrays. Feasible. hi=21.
- mid = 15: [7,2,5]=14, [10]=10... wait, [10,8]=18 > 15. So [10], [8]. That's [7,2,5], [10], [8] = 3 subarrays > 2. Not feasible. lo=16.
- mid = 18: [7,2,5]=14, [10,8]=18. 2 subarrays. Feasible. hi=18.
- mid = 17: [7,2,5]=14, [10]=10, [8]=8. 3 subarrays > 2. Not feasible. lo=18.
- lo == hi == 18. Answer: 18. ✓
</think>

## Split Array Largest Sum — Binary Search on Answer

```python
from typing import List


def split_array(nums: List[int], k: int) -> int:
    """Minimize the largest sum when splitting nums into k contiguous subarrays.

    Time Complexity: O(n * log(sum(nums) - max(nums)))
    Space Complexity: O(1)
    """
    def can_split(max_sum: int) -> bool:
        """Check if we can split into <= k subarrays each with sum <= max_sum."""
        count = 1
        current_sum = 0
        for num in nums:
            if current_sum + num > max_sum:
                count += 1
                current_sum = num
                if count > k:
                    return False
            else:
                current_sum += num
        return True

    lo = max(nums)     # At minimum, must fit the largest single element
    hi = sum(nums)     # At maximum, everything in one subarray

    while lo < hi:
        mid = (lo + hi) // 2
        if can_split(mid):
            hi = mid       # Feasible — try smaller maximum
        else:
            lo = mid + 1   # Not feasible — need larger maximum

    return lo


# --- Tests ---
def test_example():
    assert split_array([7, 2, 5, 10, 8], 2) == 18

def test_single_split():
    # k=1: entire array is one subarray
    assert split_array([7, 2, 5, 10, 8], 1) == 32

def test_max_splits():
    # k=n: each element is its own subarray, answer = max element
    assert split_array([7, 2, 5, 10, 8], 5) == 10

def test_equal_elements():
    assert split_array([1, 1, 1, 1], 2) == 2  # [1,1] and [1,1]

def test_single_element():
    assert split_array([10], 1) == 10

test_example()
test_single_split()
test_max_splits()
test_equal_elements()
test_single_element()
print("All split array largest sum tests passed!")
```

### The Binary Search on Answer Pattern

This problem exemplifies a powerful pattern:
1. **Identify the answer range**: `[max(nums), sum(nums)]`
2. **Define a monotonic feasibility function**: `can_split(M)` — as M increases, it only gets easier
3. **Binary search for the boundary**: smallest M where feasible

```
M:     10  11  12  ...  17  18  19  ...  32
OK?:    F   F   F  ...   F   T   T  ...   T
                         ^--- answer = 18
```

This pattern appears in many optimization problems: Koko's bananas, book allocation, painter's partition, and aggressive cows.
'''),

    ("thinking/algorithms", r'''Aggressive Cows / Magnetic Balls: Given n stalls at positions along a line and c cows, place the cows in stalls such that the minimum distance between any two cows is maximized. Return this maximum possible minimum distance.

Example: positions = [1, 2, 4, 8, 9], c = 3 -> Output: 3 (place cows at 1, 4, 8 or 1, 4, 9, etc.; minimum gap = 3)''', r'''<think>
Another binary search on the answer! This is a classic competitive programming problem.

We want to maximize the minimum distance. If we can place cows with minimum distance D, we can also place them with any minimum distance < D. So feasibility is monotonic (non-increasing).

**Feasibility check**: Given a minimum distance D, can we place c cows such that every pair is at least D apart?
- Greedy: sort positions. Place first cow at the first stall. For each subsequent cow, place it at the first stall that is >= D away from the last placed cow.
- If we place all c cows, return True.

**Search space**:
- lo = 1 (minimum possible distance between distinct stalls, after sorting; actually could be 0 but distances are at least 1 if positions are integers)

Wait, actually lo should be 0 or 1. Let me think... the minimum gap between adjacent sorted positions could be 1 (positions 1, 2). So lo = 1 is safe (we definitely can place with gap 1 if there are enough stalls).

Actually, lo = 1 works since positions are distinct integers. But to be safe:
- lo = 0 (or 1)
- hi = (max_pos - min_pos) // (c - 1)... or simpler, hi = max_pos - min_pos.

**Binary search** for the maximum D such that feasible(D) is true.

Time: O(n log n + n log(max_range)) — sorting + binary search * feasibility check.

Verification: positions = [1, 2, 4, 8, 9], c = 3
- D=3: place at 1, then next >= 4: stall 4. Then next >= 7: stall 8. 3 cows placed. ✓
- D=4: place at 1, then next >= 5: stall 8. Then next >= 12: none. Only 2 cows. ✗
So answer = 3. ✓
</think>

## Aggressive Cows — Maximize Minimum Distance

```python
from typing import List


def aggressive_cows(positions: List[int], c: int) -> int:
    """Place c cows to maximize the minimum distance between any two cows.

    Time Complexity: O(n log n + n log(max_range))
    Space Complexity: O(1) extra (sort is in-place)
    """
    positions.sort()

    def can_place(min_dist: int) -> bool:
        """Check if we can place c cows with at least min_dist between each pair."""
        placed = 1
        last_pos = positions[0]
        for i in range(1, len(positions)):
            if positions[i] - last_pos >= min_dist:
                placed += 1
                last_pos = positions[i]
                if placed == c:
                    return True
        return placed >= c

    lo = 1
    hi = (positions[-1] - positions[0]) // (c - 1)  # Upper bound: evenly spaced

    # Find the largest D such that can_place(D) is True
    while lo < hi:
        mid = (lo + hi + 1) // 2  # Upper mid to avoid infinite loop
        if can_place(mid):
            lo = mid       # Feasible — try larger distance
        else:
            hi = mid - 1   # Not feasible — reduce distance

    return lo


# --- Tests ---
def test_example():
    assert aggressive_cows([1, 2, 4, 8, 9], 3) == 3

def test_two_cows():
    # 2 cows: place at extremes for max distance
    assert aggressive_cows([1, 2, 4, 8, 9], 2) == 8  # Place at 1 and 9

def test_all_stalls():
    # 5 cows, 5 stalls: must use all, min gap is min adjacent diff
    assert aggressive_cows([1, 2, 4, 8, 9], 5) == 1

def test_evenly_spaced():
    assert aggressive_cows([0, 3, 6, 9, 12], 3) == 6  # Place at 0, 6, 12

def test_unsorted_input():
    assert aggressive_cows([9, 1, 4, 8, 2], 3) == 3

test_example()
test_two_cows()
test_all_stalls()
test_evenly_spaced()
test_unsorted_input()
print("All aggressive cows tests passed!")
```

### Important Detail: Upper vs Lower Mid

Note `mid = (lo + hi + 1) // 2` — we use the **upper mid** because we're searching for the **rightmost true** (maximizing D):

```
D:     1  2  3  4  5  6  7  8
OK?:   T  T  T  F  F  F  F  F
             ^--- find this boundary (rightmost True)
```

When `can_place(mid)` is True, we set `lo = mid`. If we used lower mid `(lo+hi)//2`, we'd get stuck in an infinite loop when `lo + 1 == hi` and `mid == lo`. Upper mid avoids this.

Contrast with "leftmost true" problems (split array, Koko's bananas) where we set `hi = mid` and use lower mid.
'''),
]
