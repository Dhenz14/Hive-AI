PAIRS = [
    ("thinking/algorithms", r'''Implement the Minimum Window Substring problem: given strings s and t, find the smallest substring of s that contains all characters of t (including duplicates).

Example:
s = "ADOBECODEBANC", t = "ABC"
Output: "BANC"''', r'''<think>
Minimum Window Substring — a classic sliding window problem.

Brute force: check all O(n^2) substrings of s, for each one check if it contains all characters of t. That's O(n^2 * m) or O(n^3). Way too slow.

Optimal approach: sliding window with two pointers (left and right).
1. Use a frequency map for t (what we need)
2. Expand right pointer to include characters
3. When the window contains all required characters, try shrinking from the left
4. Track the minimum valid window

Key data structures:
- need: Counter of characters in t
- have: Counter of characters in current window
- A counter tracking how many distinct characters have been satisfied (count >= need)

When the number of satisfied characters equals the number of distinct characters in t, the window is valid.

Let me think about the exact tracking:
- required = number of distinct characters in t
- formed = number of distinct characters where window count >= need count
- When formed == required, window is valid

Expand right:
- Add s[right] to window_counts
- If s[right] is in need and window_counts[s[right]] == need[s[right]], increment formed

Shrink left:
- While formed == required:
  - Update answer if current window is smaller
  - Remove s[left] from window_counts
  - If s[left] is in need and window_counts[s[left]] < need[s[left]], decrement formed
  - Increment left

Let me trace s = "ADOBECODEBANC", t = "ABC":
need = {A:1, B:1, C:1}, required = 3

Right=0 (A): have A:1, formed=1
Right=1 (D): skip
Right=2 (O): skip
Right=3 (B): have B:1, formed=2
Right=4 (E): skip
Right=5 (C): have C:1, formed=3. Valid window! "ADOBEC" len=6
  Shrink: remove A, have A:0, formed=2. Window "DOBEC". Left=1.

Right=6 (O): skip
Right=7 (D): skip
Right=8 (E): skip
Right=9 (B): already have B:1 (wait, we had B:1 before, still have it). Nothing changes for formed.
Actually let me re-trace more carefully...

After shrinking at right=5: left=1, window="DOBEC", formed=2
Right=6-8: no formed change
Right=9 (B): window_counts B increases. formed still 2 (need A).
Right=10 (A): window_counts A:1 == need A:1. formed=3. Window = "DOBECODEBA" wait...

Hmm, let me just trust the algorithm and implement it cleanly. The tracing is getting complex but the logic is sound.

Time: O(n + m) where n = len(s), m = len(t). Each character is visited at most twice (once by right, once by left).
Space: O(m + unique chars) for the frequency maps.

Edge cases:
- t is empty: return ""
- t longer than s: return ""
- No valid window: return ""
- s == t: return s
</think>

## Minimum Window Substring

```python
from collections import Counter, defaultdict
from typing import Optional


def min_window_substring(s: str, t: str) -> str:
    """
    Find the smallest substring of s containing all characters of t.

    Args:
        s: Source string.
        t: Target characters (with duplicates).

    Returns:
        The minimum window substring, or "" if no valid window exists.
    """
    if not t or not s or len(t) > len(s):
        return ""

    need: Counter = Counter(t)
    required: int = len(need)  # distinct chars needed

    window_counts: defaultdict = defaultdict(int)
    formed: int = 0  # distinct chars with satisfied count

    best_len: float = float("inf")
    best_left: int = 0

    left: int = 0

    for right in range(len(s)):
        ch = s[right]
        window_counts[ch] += 1

        # Check if this character's requirement is now met
        if ch in need and window_counts[ch] == need[ch]:
            formed += 1

        # Try to shrink from the left
        while formed == required:
            window_size = right - left + 1
            if window_size < best_len:
                best_len = window_size
                best_left = left

            # Remove leftmost character
            left_ch = s[left]
            window_counts[left_ch] -= 1
            if left_ch in need and window_counts[left_ch] < need[left_ch]:
                formed -= 1
            left += 1

    if best_len == float("inf"):
        return ""

    return s[best_left : best_left + int(best_len)]


# --- Test Cases ---

# Test 1: Classic example
result1 = min_window_substring("ADOBECODEBANC", "ABC")
assert result1 == "BANC", f"Got {result1}"
print(f"Test 1: '{result1}'")

# Test 2: Exact match
result2 = min_window_substring("abc", "abc")
assert result2 == "abc"
print(f"Test 2: '{result2}'")

# Test 3: No valid window
result3 = min_window_substring("abc", "xyz")
assert result3 == ""
print(f"Test 3: '{result3}'")

# Test 4: Duplicate characters in t
result4 = min_window_substring("AAABBBCCC", "ABC")
# Smallest window containing A, B, C
assert "A" in result4 and "B" in result4 and "C" in result4
print(f"Test 4: '{result4}'")

# Test 5: Single character
result5 = min_window_substring("abcdef", "e")
assert result5 == "e"
print(f"Test 5: '{result5}'")

# Test 6: t has duplicates
result6 = min_window_substring("aabdcaabbc", "aabc")
# Need 2 a's, 1 b, 1 c
assert Counter(result6) >= Counter("aabc")
print(f"Test 6: '{result6}'")
```

**Time Complexity:** O(|s| + |t|) — each character of s is visited at most twice (once by the right pointer, once by the left). Building the Counter for t is O(|t|).

**Space Complexity:** O(|s| + |t|) — for the window and need frequency maps. In practice, O(|alphabet|) if the alphabet is fixed.

The sliding window technique works because of the monotonicity property: if a window starting at `left` is valid, we don't need to check any window starting before `left` with the same right endpoint, since they'd be larger. The `formed` counter avoids repeatedly scanning the frequency maps, keeping each expansion/contraction step at O(1).'''),

    ("thinking/algorithms", r'''Find the longest substring with at most K distinct characters.

Example:
s = "eceba", k = 2
Output: "ece" (length 3)

s = "aabacbebebe", k = 3
Output: "cbebebe" (length 7)''', r'''<think>
Another sliding window problem. I need to find the longest substring where the number of distinct characters is at most K.

Approach: expand right pointer, adding characters. When the number of distinct characters exceeds K, shrink from the left until we're back to K or fewer.

Data structure: a dictionary mapping character -> count in the current window. The number of distinct characters is just len(char_count) where we remove entries when count reaches 0.

Algorithm:
1. Initialize left = 0, char_count = {}
2. For each right in range(len(s)):
   - Add s[right] to char_count
   - While len(char_count) > k:
     - Remove s[left] from char_count (decrement, delete if 0)
     - left += 1
   - Update best if (right - left + 1) is larger

Let me trace s = "eceba", k = 2:
right=0 (e): counts={e:1}, distinct=1. Window="e", len=1.
right=1 (c): counts={e:1,c:1}, distinct=2. Window="ec", len=2. Best=2.
right=2 (e): counts={e:2,c:1}, distinct=2. Window="ece", len=3. Best=3.
right=3 (b): counts={e:2,c:1,b:1}, distinct=3 > 2.
  Shrink: remove e, counts={e:1,c:1,b:1}. left=1. Still 3.
  Shrink: remove c, counts={e:1,b:1}. left=2. Now distinct=2. Window="eb", len=2.
right=4 (a): counts={e:1,b:1,a:1}, distinct=3 > 2.
  Shrink: remove e, counts={b:1,a:1}. left=3. Distinct=2. Window="ba", len=2.

Best = 3, substring = "ece". Correct!

For the second example s = "aabacbebebe", k = 3:
I'll trust the algorithm — it should find "cbebebe" of length 7.

Edge cases:
- k = 0: return ""
- k >= number of distinct chars in s: return s
- Empty string: return ""

Time: O(n) — each character is added and removed at most once
Space: O(k) for the character count map
</think>

## Longest Substring with At Most K Distinct Characters

```python
from collections import defaultdict
from typing import Tuple


def longest_k_distinct(s: str, k: int) -> Tuple[int, str]:
    """
    Find the longest substring with at most k distinct characters.

    Args:
        s: Input string.
        k: Maximum number of distinct characters allowed.

    Returns:
        Tuple of (length, substring).
    """
    if k == 0 or not s:
        return 0, ""

    char_count: defaultdict = defaultdict(int)
    left: int = 0
    best_len: int = 0
    best_left: int = 0

    for right in range(len(s)):
        char_count[s[right]] += 1

        # Shrink window if too many distinct characters
        while len(char_count) > k:
            left_ch = s[left]
            char_count[left_ch] -= 1
            if char_count[left_ch] == 0:
                del char_count[left_ch]
            left += 1

        # Update best
        window_len = right - left + 1
        if window_len > best_len:
            best_len = window_len
            best_left = left

    return best_len, s[best_left : best_left + best_len]


# --- Test Cases ---

# Test 1: Basic example
length1, sub1 = longest_k_distinct("eceba", 2)
assert length1 == 3
assert sub1 == "ece"
print(f"Test 1: length={length1}, substring='{sub1}'")

# Test 2: Longer example
length2, sub2 = longest_k_distinct("aabacbebebe", 3)
assert length2 == 7
assert sub2 == "cbebebe"
print(f"Test 2: length={length2}, substring='{sub2}'")

# Test 3: k = 1 (longest run of same character)
length3, sub3 = longest_k_distinct("aaabbbccc", 1)
assert length3 == 3
print(f"Test 3: length={length3}, substring='{sub3}'")

# Test 4: k >= distinct chars (entire string)
length4, sub4 = longest_k_distinct("abc", 5)
assert length4 == 3
assert sub4 == "abc"
print(f"Test 4: length={length4}, substring='{sub4}'")

# Test 5: k = 0
length5, sub5 = longest_k_distinct("abc", 0)
assert length5 == 0
assert sub5 == ""
print(f"Test 5: length={length5}, substring='{sub5}'")

# Test 6: All same characters
length6, sub6 = longest_k_distinct("aaaaaa", 2)
assert length6 == 6
assert sub6 == "aaaaaa"
print(f"Test 6: length={length6}, substring='{sub6}'")

# Test 7: Single character string
length7, sub7 = longest_k_distinct("a", 1)
assert length7 == 1
print(f"Test 7: length={length7}, substring='{sub7}'")
```

**Time Complexity:** O(n) — each character is processed at most twice (once when the right pointer includes it, once when the left pointer excludes it).

**Space Complexity:** O(k) — the character count dictionary holds at most k + 1 entries before shrinking.

This is a textbook sliding window problem. The invariant maintained is: the window `[left, right]` always has at most k distinct characters. When adding a new character violates this, we shrink from the left. The amortized cost is O(1) per character because the left pointer only moves forward and each character is removed from the window at most once.'''),

    ("thinking/algorithms", r'''Design a data structure that supports:
1. addNum(num) — add an integer from the data stream
2. findMedian() — return the median of all numbers added so far

Handle both odd and even counts. Optimize for O(log n) insertion and O(1) median retrieval.

Example:
addNum(1), addNum(2) -> median = 1.5
addNum(3) -> median = 2''', r'''<think>
Median from a data stream — a classic design problem.

Brute force approaches:
1. Keep a sorted list, insert in position (O(n) insertion due to shifting, O(1) median). Not great.
2. Keep unsorted list, sort on each findMedian call (O(1) insert, O(n log n) median). Even worse.

Optimal approach: Two heaps!
- max_heap: stores the smaller half of numbers (we want the max of this half)
- min_heap: stores the larger half (we want the min of this half)

The median is either the top of one heap or the average of both tops.

Invariants:
1. All elements in max_heap <= all elements in min_heap
2. len(max_heap) == len(min_heap) or len(max_heap) == len(min_heap) + 1

Python's heapq is a min-heap, so for max_heap I'll negate values.

addNum(num):
1. Push to max_heap (negate for max behavior)
2. Move the top of max_heap to min_heap (to maintain ordering)
3. If min_heap is larger than max_heap, move top back

Wait, let me think more carefully about the balancing:

Option A (cleaner):
- Always add to max_heap first, then balance
- After adding to max_heap, pop its max and push to min_heap
- If min_heap has more elements, pop its min and push to max_heap

This ensures the ordering invariant because:
- New element goes through max_heap first, so the largest of the smaller half moves to min_heap
- If sizes are unbalanced, we move from min_heap back

Let me trace: addNum(1), addNum(2), addNum(3):

addNum(1):
- Push -1 to max_heap: [-1]
- Pop max_heap -> 1, push to min_heap: [1]
- max_heap is empty (size 0), min_heap has 1 element. Rebalance: pop 1 from min_heap, push -1 to max_heap.
- State: max_heap=[-1], min_heap=[]. Median = 1.

addNum(2):
- Push -2 to max_heap: [-2, -1]
- Pop max_heap (gives -(-2)=2), push to min_heap: [2]
- max_heap=[-1], min_heap=[2]. Sizes equal. No rebalance.
- Median = (1 + 2) / 2 = 1.5.

addNum(3):
- Push -3 to max_heap: [-3, -1]
- Pop max_heap (gives 3), push to min_heap: [2, 3]
- max_heap=[-1], min_heap=[2,3]. min_heap larger (2 > 1). Rebalance: pop 2 from min_heap, push -2 to max_heap.
- State: max_heap=[-2, -1], min_heap=[3]. Median = 2. Correct!

Time: O(log n) per addNum (heap operations), O(1) for findMedian.
Space: O(n) for storing all elements.

Edge cases:
- Single element: median is that element
- Two elements: average
- Negative numbers
- Duplicates
</think>

## Median of Data Stream with Two Heaps

```python
import heapq
from typing import List


class MedianFinder:
    """
    Data structure for finding the median of a growing data stream.

    Uses two heaps:
    - max_heap (negated): stores the smaller half
    - min_heap: stores the larger half

    Invariant: len(max_heap) == len(min_heap) or len(max_heap) == len(min_heap) + 1
    """

    def __init__(self) -> None:
        self.max_heap: List[int] = []  # negated values for max behavior
        self.min_heap: List[int] = []  # standard min heap

    def add_num(self, num: int) -> None:
        """
        Add a number to the data structure. O(log n).
        """
        # Step 1: Add to max_heap
        heapq.heappush(self.max_heap, -num)

        # Step 2: Ensure ordering — move max of smaller half to larger half
        val = -heapq.heappop(self.max_heap)
        heapq.heappush(self.min_heap, val)

        # Step 3: Balance sizes — max_heap should have >= min_heap elements
        if len(self.min_heap) > len(self.max_heap):
            val = heapq.heappop(self.min_heap)
            heapq.heappush(self.max_heap, -val)

    def find_median(self) -> float:
        """
        Return the median of all numbers added so far. O(1).

        Raises:
            ValueError: If no numbers have been added.
        """
        if not self.max_heap:
            raise ValueError("No numbers added yet.")

        if len(self.max_heap) > len(self.min_heap):
            # Odd count: median is the top of max_heap
            return float(-self.max_heap[0])
        else:
            # Even count: average of both tops
            return (-self.max_heap[0] + self.min_heap[0]) / 2.0

    def __len__(self) -> int:
        return len(self.max_heap) + len(self.min_heap)


# --- Test Cases ---

# Test 1: Basic sequence
mf = MedianFinder()
mf.add_num(1)
assert mf.find_median() == 1.0
mf.add_num(2)
assert mf.find_median() == 1.5
mf.add_num(3)
assert mf.find_median() == 2.0
print(f"Test 1: After [1,2,3], median = {mf.find_median()}")

# Test 2: Reverse order
mf2 = MedianFinder()
for num in [5, 4, 3, 2, 1]:
    mf2.add_num(num)
assert mf2.find_median() == 3.0
print(f"Test 2: After [5,4,3,2,1], median = {mf2.find_median()}")

# Test 3: Single element
mf3 = MedianFinder()
mf3.add_num(42)
assert mf3.find_median() == 42.0
print(f"Test 3: Single element, median = {mf3.find_median()}")

# Test 4: Negative numbers
mf4 = MedianFinder()
for num in [-5, -3, -1, 0, 2]:
    mf4.add_num(num)
assert mf4.find_median() == -1.0
print(f"Test 4: Negative numbers, median = {mf4.find_median()}")

# Test 5: Duplicates
mf5 = MedianFinder()
for num in [1, 1, 1, 1]:
    mf5.add_num(num)
assert mf5.find_median() == 1.0
print(f"Test 5: All duplicates, median = {mf5.find_median()}")

# Test 6: Large stream — verify correctness against sorted list
import random
random.seed(123)
mf6 = MedianFinder()
all_nums: List[int] = []
for _ in range(1000):
    num = random.randint(-1000, 1000)
    mf6.add_num(num)
    all_nums.append(num)
    all_nums_sorted = sorted(all_nums)
    n = len(all_nums_sorted)
    if n % 2 == 1:
        expected = float(all_nums_sorted[n // 2])
    else:
        expected = (all_nums_sorted[n // 2 - 1] + all_nums_sorted[n // 2]) / 2.0
    assert mf6.find_median() == expected
print("Test 6: 1000-element stream verified against brute force")
```

**Time Complexity:** O(log n) for `add_num` (three heap operations of O(log n) each), O(1) for `find_median` (just peek at heap tops).

**Space Complexity:** O(n) for storing all n elements across the two heaps.

The two-heap approach is the standard optimal solution. The max-heap holds the smaller half and the min-heap holds the larger half. The three-step insertion process (add to max, transfer to min, rebalance) ensures both ordering and size invariants are maintained without complex conditional logic. Python's lack of a native max-heap is handled by negating values.'''),

    ("thinking/algorithms", r'''Solve the Trapping Rain Water problem: given an array of non-negative integers representing an elevation map where the width of each bar is 1, compute how much water it can trap after raining.

Example:
height = [0,1,0,2,1,0,1,3,2,1,2,1]
Output: 6''', r'''<think>
Trapping Rain Water — a classic problem with multiple solution approaches.

Let me think about what determines how much water sits above each bar. For position i, the water level is min(max_left, max_right) - height[i], where max_left is the tallest bar to the left (including i) and max_right is the tallest bar to the right (including i). If this is negative, no water sits there.

Approach 1: Brute force
For each position, scan left and right to find max heights. O(n^2) time.

Approach 2: Precompute prefix max and suffix max
- left_max[i] = max(height[0..i])
- right_max[i] = max(height[i..n-1])
- water at i = min(left_max[i], right_max[i]) - height[i]
O(n) time, O(n) space.

Approach 3: Two pointers — O(n) time, O(1) space
This is the optimal approach. Use left and right pointers:
- Maintain left_max and right_max
- If left_max < right_max, the water at left position is determined by left_max (because right side has something taller), so process left and move right
- Otherwise, process right and move left

Wait, let me think about this more carefully:
- left pointer starts at 0, right pointer starts at n-1
- left_max = max height seen from the left so far
- right_max = max height seen from the right so far
- If height[left] < height[right]:
  - If height[left] >= left_max: update left_max
  - Else: water += left_max - height[left]
  - Move left++
- Else:
  - If height[right] >= right_max: update right_max
  - Else: water += right_max - height[right]
  - Move right--

The key insight: when height[left] < height[right], we know that the right boundary is at least height[right], which is >= height[left]. So the water at position left is constrained by left_max (since the right side can hold at least that much). We don't need to know the exact right_max.

Let me trace height = [0,1,0,2,1,0,1,3,2,1,2,1]:
This would be tedious to trace fully, but the algorithm is well-known and correct. Expected answer: 6.

I'll implement all three approaches but highlight the two-pointer one as optimal.

Edge cases:
- Empty array or length < 3: no water
- Flat array: no water
- Strictly increasing or decreasing: no water
- Single peak: water on both sides
</think>

## Trapping Rain Water — Three Approaches

```python
from typing import List


def trap_brute_force(height: List[int]) -> int:
    """O(n^2) brute force — for each bar find max left and right."""
    n = len(height)
    water = 0
    for i in range(n):
        left_max = max(height[: i + 1]) if i >= 0 else 0
        right_max = max(height[i:]) if i < n else 0
        water += min(left_max, right_max) - height[i]
    return water


def trap_dp(height: List[int]) -> int:
    """O(n) time, O(n) space with prefix/suffix max arrays."""
    if len(height) < 3:
        return 0

    n = len(height)
    left_max: List[int] = [0] * n
    right_max: List[int] = [0] * n

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


def trap_two_pointers(height: List[int]) -> int:
    """
    O(n) time, O(1) space — optimal two-pointer approach.

    The key insight: water at any position is determined by the
    minimum of (max height to its left, max height to its right)
    minus the bar height. We can determine this without precomputing
    all maxima by processing from the side with the smaller known max.

    Args:
        height: Non-negative integers representing bar heights.

    Returns:
        Total trapped water units.
    """
    if len(height) < 3:
        return 0

    left: int = 0
    right: int = len(height) - 1
    left_max: int = 0
    right_max: int = 0
    water: int = 0

    while left < right:
        if height[left] < height[right]:
            if height[left] >= left_max:
                left_max = height[left]
            else:
                water += left_max - height[left]
            left += 1
        else:
            if height[right] >= right_max:
                right_max = height[right]
            else:
                water += right_max - height[right]
            right -= 1

    return water


# --- Test Cases ---

# Test 1: Classic example
h1 = [0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1]
assert trap_two_pointers(h1) == 6
assert trap_dp(h1) == 6
assert trap_brute_force(h1) == 6
print(f"Test 1: water = {trap_two_pointers(h1)}")

# Test 2: No water (ascending)
h2 = [1, 2, 3, 4, 5]
assert trap_two_pointers(h2) == 0
print(f"Test 2: water = {trap_two_pointers(h2)}")

# Test 3: No water (descending)
h3 = [5, 4, 3, 2, 1]
assert trap_two_pointers(h3) == 0
print(f"Test 3: water = {trap_two_pointers(h3)}")

# Test 4: V-shape
h4 = [3, 0, 3]
assert trap_two_pointers(h4) == 3
print(f"Test 4: water = {trap_two_pointers(h4)}")

# Test 5: Empty / too short
assert trap_two_pointers([]) == 0
assert trap_two_pointers([1]) == 0
assert trap_two_pointers([1, 2]) == 0
print(f"Test 5: edge cases passed")

# Test 6: Flat
h6 = [2, 2, 2, 2]
assert trap_two_pointers(h6) == 0
print(f"Test 6: flat = {trap_two_pointers(h6)}")

# Test 7: Large example
h7 = [4, 2, 0, 3, 2, 5]
assert trap_two_pointers(h7) == 9
assert trap_dp(h7) == 9
print(f"Test 7: water = {trap_two_pointers(h7)}")
```

**Time Complexity:**
- Brute force: O(n^2)
- DP (prefix/suffix max): O(n) time, O(n) space
- Two pointers: O(n) time, O(1) space (optimal)

**Space Complexity:** O(1) for the two-pointer approach.

The two-pointer approach works because when `height[left] < height[right]`, we know there exists a boundary on the right at least as tall as `height[right]`. So the water at position `left` is constrained only by `left_max`. We don't need to know the exact maximum on the right — just that it's tall enough. This eliminates the need for precomputed arrays.'''),

    ("thinking/algorithms", r'''Solve the Container With Most Water problem: given n non-negative integers a[0], a[1], ..., a[n-1] where each represents a vertical line at position i with height a[i], find two lines that together with the x-axis form a container that holds the most water.

Example:
height = [1,8,6,2,5,4,8,3,7]
Output: 49 (between positions 1 and 8, min(8,7) * (8-1) = 49)''', r'''<think>
Container With Most Water — the key insight is that the area is determined by the shorter line and the distance between the two lines.

Brute force: try all O(n^2) pairs, compute area for each. Too slow for large n.

Optimal: Two pointer approach, O(n).

The idea: start with the widest container (left=0, right=n-1). The area = min(height[left], height[right]) * (right - left).

Now, which pointer should we move? If we move the pointer with the taller line, the height can't increase (it's still limited by the shorter line) and the width decreases, so the area can only decrease or stay the same. So we should always move the pointer with the shorter line — this gives us a chance of finding a taller line that could increase the area despite reduced width.

Proof of correctness: Consider the pair (left, right). If height[left] < height[right], then no pair (left, j) for j < right can have a larger area than (left, right), because:
- The width is smaller: j - left < right - left
- The height is still limited by height[left] (since min(height[left], height[j]) <= height[left])
So we can safely discard position left and move to left+1.

Let me trace height = [1,8,6,2,5,4,8,3,7]:
left=0, right=8: area = min(1,7)*8 = 8. Move left (1 < 7).
left=1, right=8: area = min(8,7)*7 = 49. Move right (7 < 8).
left=1, right=7: area = min(8,3)*6 = 18. Move right (3 < 8).
left=1, right=6: area = min(8,8)*5 = 40. Either; move right.
left=1, right=5: area = min(8,4)*4 = 16. Move right.
left=1, right=4: area = min(8,5)*3 = 15. Move right.
left=1, right=3: area = min(8,2)*2 = 4. Move right.
left=1, right=2: area = min(8,6)*1 = 6. Move right.
left=1, right=1: done. But wait, left should be < right. So we stop before this.

Actually, left=1, right=2: left < right still true. After this iteration: move right (6 < 8), right becomes 1. Now left >= right, so loop ends.

Max area = 49. Correct!

Hmm wait, I also want to return which indices form the best container. Let me track that.

Time: O(n)
Space: O(1)
</think>

## Container With Most Water

```python
from typing import List, Tuple


def max_water_container(height: List[int]) -> Tuple[int, int, int]:
    """
    Find two lines forming the container that holds the most water.

    Uses the two-pointer approach. We always move the pointer pointing
    to the shorter line because:
    - Moving the taller line can only decrease or maintain the area
      (width shrinks, height is still bounded by the shorter line)
    - Moving the shorter line might find a taller line, potentially
      increasing the area

    Args:
        height: List of non-negative line heights.

    Returns:
        Tuple of (max_area, left_index, right_index).
    """
    if len(height) < 2:
        return 0, 0, 0

    left: int = 0
    right: int = len(height) - 1
    max_area: int = 0
    best_left: int = 0
    best_right: int = 0

    while left < right:
        # Calculate area with current boundaries
        w = right - left
        h = min(height[left], height[right])
        area = w * h

        if area > max_area:
            max_area = area
            best_left = left
            best_right = right

        # Move the pointer with the shorter line
        if height[left] < height[right]:
            left += 1
        else:
            right -= 1

    return max_area, best_left, best_right


# --- Test Cases ---

# Test 1: Classic example
h1 = [1, 8, 6, 2, 5, 4, 8, 3, 7]
area1, l1, r1 = max_water_container(h1)
assert area1 == 49
assert l1 == 1 and r1 == 8
print(f"Test 1: area={area1}, between positions {l1} and {r1}")
print(f"  min({h1[l1]}, {h1[r1]}) * ({r1}-{l1}) = {min(h1[l1],h1[r1])} * {r1-l1} = {area1}")

# Test 2: Two elements
h2 = [5, 10]
area2, l2, r2 = max_water_container(h2)
assert area2 == 5
print(f"Test 2: area={area2}")

# Test 3: Ascending heights
h3 = [1, 2, 3, 4, 5]
area3, _, _ = max_water_container(h3)
# Best: min(1,5)*4=4 or min(2,5)*3=6 or min(3,5)*2=6 or min(4,5)*1=4
assert area3 == 6
print(f"Test 3: area={area3}")

# Test 4: All same height
h4 = [5, 5, 5, 5, 5]
area4, l4, r4 = max_water_container(h4)
assert area4 == 20  # 5 * 4
print(f"Test 4: area={area4}")

# Test 5: One zero
h5 = [0, 100]
area5, _, _ = max_water_container(h5)
assert area5 == 0  # limited by the 0-height line
print(f"Test 5: area={area5}")

# Test 6: Verify against brute force
import random
random.seed(42)
h6 = [random.randint(0, 100) for _ in range(100)]
area6, _, _ = max_water_container(h6)

# Brute force check
bf_max = 0
for i in range(len(h6)):
    for j in range(i + 1, len(h6)):
        bf_max = max(bf_max, min(h6[i], h6[j]) * (j - i))
assert area6 == bf_max
print(f"Test 6: Brute force verification passed (area={area6})")
```

**Time Complexity:** O(n) — each pointer moves at most n times total.

**Space Complexity:** O(1) — only a few variables.

The proof of correctness relies on the observation that when `height[left] < height[right]`, every container using `left` with any index `j < right` has area at most `height[left] * (j - left) < height[left] * (right - left)`, which is already the area we computed. So we lose nothing by discarding `left`. This greedy elimination makes the two-pointer approach exhaustive despite only checking O(n) pairs out of O(n^2).'''),
]
