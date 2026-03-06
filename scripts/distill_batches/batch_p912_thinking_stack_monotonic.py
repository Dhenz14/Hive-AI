PAIRS = [
    ("thinking/algorithms", r'''Given an array of integers representing heights of bars in a histogram, find the area of the largest rectangle that can be formed within the histogram. Each bar has width 1.

Example: heights = [2,1,5,6,2,3] -> Output: 10 (the rectangle spans bars with heights 5 and 6, giving 5*2=10).''', r'''<think>
This is the classic "Largest Rectangle in Histogram" problem. Let me think through the approaches.

**Brute force**: For each bar i, expand left and right while heights are >= heights[i]. Area = heights[i] * width. O(n^2) time.

**Monotonic stack approach**: This is the O(n) solution. The key insight is: for each bar, we want to find the nearest shorter bar on the left and right. The rectangle using bar i as the limiting height extends from (left_boundary + 1) to (right_boundary - 1).

The stack maintains indices in increasing order of heights:
1. Iterate through bars. For each bar:
   - While the stack top has height >= current bar's height, pop it
   - The popped bar's rectangle extends from the new stack top + 1 to current index - 1
   - Calculate area for each popped bar
2. After iteration, process remaining bars in the stack

Why does this work? When we pop index `mid` because `heights[i] < heights[mid]`:
- Right boundary: i (first shorter bar to the right)
- Left boundary: new stack top + 1 (first shorter bar to the left is at the new top)
- Width: i - stack_top - 1

If the stack is empty after popping, left boundary is 0, so width = i.

Let me trace through the example: [2, 1, 5, 6, 2, 3]
- i=0: push 0. Stack: [0]
- i=1: h[1]=1 < h[0]=2. Pop 0: width=1, area=2*1=2. Push 1. Stack: [1]
- i=2: h[2]=5 > h[1]=1. Push 2. Stack: [1,2]
- i=3: h[3]=6 > h[2]=5. Push 3. Stack: [1,2,3]
- i=4: h[4]=2 < h[3]=6. Pop 3: width=4-2-1=1, area=6*1=6. Pop 2: width=4-1-1=2, area=5*2=10. Push 4. Stack: [1,4]
- i=5: h[5]=3 > h[4]=2. Push 5. Stack: [1,4,5]
- End: Pop 5: width=6-4-1=1, area=3. Pop 4: width=6-1-1=4, area=2*4=8. Pop 1: width=6, area=1*6=6.

Max = 10. Correct!
</think>

## Largest Rectangle in Histogram — Monotonic Stack

```python
from typing import List


def largest_rectangle_area(heights: List[int]) -> int:
    """Find the largest rectangular area in a histogram.

    Uses a monotonic increasing stack of indices.

    Time Complexity: O(n) — each index pushed and popped at most once
    Space Complexity: O(n) for the stack
    """
    stack: List[int] = []  # Stores indices; heights at these indices are increasing
    max_area = 0
    n = len(heights)

    for i in range(n):
        while stack and heights[stack[-1]] >= heights[i]:
            h = heights[stack.pop()]
            # Width: from (new stack top + 1) to (i - 1)
            width = i if not stack else i - stack[-1] - 1
            max_area = max(max_area, h * width)
        stack.append(i)

    # Process remaining bars in stack
    while stack:
        h = heights[stack.pop()]
        width = n if not stack else n - stack[-1] - 1
        max_area = max(max_area, h * width)

    return max_area


# --- Tests ---
def test_example():
    assert largest_rectangle_area([2, 1, 5, 6, 2, 3]) == 10

def test_ascending():
    # [1,2,3,4,5] -> best is min(3,4,5)*3=9 or similar
    # Actually: 3*3=9 at indices 2-4, or 2*4=8 at 1-4, or 1*5=5
    # Wait: 4*2=8 at [3,4]? No, h[3]=4,h[4]=5 -> min=4, width=2, area=8.
    # Or 3*3=9 at [2,3,4]: min=3, width=3, area=9. That's it.
    assert largest_rectangle_area([1, 2, 3, 4, 5]) == 9

def test_descending():
    assert largest_rectangle_area([5, 4, 3, 2, 1]) == 9

def test_uniform():
    assert largest_rectangle_area([3, 3, 3, 3]) == 12

def test_single():
    assert largest_rectangle_area([5]) == 5

def test_empty():
    assert largest_rectangle_area([]) == 0

test_example()
test_ascending()
test_descending()
test_uniform()
test_single()
test_empty()
print("All largest rectangle in histogram tests passed!")
```

### Complexity

Each index is pushed onto the stack exactly once and popped at most once. Total operations: O(2n) = O(n). This is significantly better than the O(n^2) brute force and is optimal since we must examine each bar at least once.
'''),

    ("thinking/algorithms", r'''Given an array of daily temperatures, return an array where answer[i] is the number of days you have to wait after day i to get a warmer temperature. If there is no future warmer day, answer[i] = 0.

Example: temperatures = [73,74,75,71,69,72,76,73] -> [1,1,4,2,1,1,0,0]''', r'''<think>
This is a classic "next greater element" problem, which screams monotonic stack.

**Brute force**: For each day, scan forward to find the next warmer day. O(n^2).

**Monotonic stack (decreasing)**: We maintain a stack of indices whose temperatures are in decreasing order (from bottom to top). When we encounter a temperature warmer than the stack top, we've found the answer for that stack top.

Algorithm:
1. Iterate i from 0 to n-1
2. While stack is non-empty and temps[i] > temps[stack[-1]]:
   - Pop index j from stack
   - answer[j] = i - j
3. Push i onto stack
4. Any indices remaining in the stack get answer = 0 (already initialized)

Why decreasing stack? Because we're looking for the NEXT GREATER element. A decreasing stack ensures that when a larger element arrives, it resolves all smaller elements waiting on the stack.

Let me trace: [73, 74, 75, 71, 69, 72, 76, 73]
- i=0(73): stack empty, push 0. Stack: [0]
- i=1(74): 74>73, pop 0, ans[0]=1. Push 1. Stack: [1]
- i=2(75): 75>74, pop 1, ans[1]=1. Push 2. Stack: [2]
- i=3(71): 71<75, push 3. Stack: [2,3]
- i=4(69): 69<71, push 4. Stack: [2,3,4]
- i=5(72): 72>69, pop 4, ans[4]=1. 72>71, pop 3, ans[3]=2. 72<75, push 5. Stack: [2,5]
- i=6(76): 76>72, pop 5, ans[5]=1. 76>75, pop 2, ans[2]=4. Push 6. Stack: [6]
- i=7(73): 73<76, push 7. Stack: [6,7]
- Remaining: ans[6]=0, ans[7]=0. ✓
</think>

## Daily Temperatures — Monotonic Decreasing Stack

```python
from typing import List


def daily_temperatures(temperatures: List[int]) -> List[int]:
    """Find days until a warmer temperature using a monotonic stack.

    Time Complexity: O(n) — each index pushed/popped at most once
    Space Complexity: O(n) for stack and result
    """
    n = len(temperatures)
    answer = [0] * n
    stack: List[int] = []  # Indices with decreasing temperatures

    for i in range(n):
        while stack and temperatures[i] > temperatures[stack[-1]]:
            j = stack.pop()
            answer[j] = i - j
        stack.append(i)

    return answer


# --- Tests ---
def test_example():
    temps = [73, 74, 75, 71, 69, 72, 76, 73]
    expected = [1, 1, 4, 2, 1, 1, 0, 0]
    assert daily_temperatures(temps) == expected

def test_decreasing():
    # No warmer days ahead for any day
    assert daily_temperatures([5, 4, 3, 2, 1]) == [0, 0, 0, 0, 0]

def test_increasing():
    assert daily_temperatures([1, 2, 3, 4, 5]) == [1, 1, 1, 1, 0]

def test_uniform():
    # Equal temps are NOT warmer
    assert daily_temperatures([70, 70, 70]) == [0, 0, 0]

test_example()
test_decreasing()
test_increasing()
test_uniform()
print("All daily temperatures tests passed!")
```

### Stack Invariant

The stack always holds indices in decreasing order of temperature. When temperature `T[i]` is processed:
- All stack indices with temperature < T[i] are popped (they found their answer)
- i is pushed (it hasn't found a warmer day yet)

This guarantees each element is pushed and popped at most once, giving O(n) total time regardless of input pattern.
'''),

    ("thinking/algorithms", r'''Given a circular array of integers, find the Next Greater Element for every element. The next greater element of an element x is the first element greater than x encountered when traversing the array in circular fashion. If no greater element exists, output -1.

Example: nums = [1,2,1] -> [2,-1,2] (for nums[2]=1, the next greater wrapping around is nums[0]=... wait, we continue to nums[1]=2, which is greater)''', r'''<think>
This is "Next Greater Element II" — the circular variant.

In a non-circular array, we use a single pass with a monotonic decreasing stack. For the circular version, the trick is to iterate through the array twice (i from 0 to 2n-1, using i % n for indexing). The second pass lets elements "wrap around" to find their next greater element.

But we only push indices during the first pass (i < n), or more precisely, we can push during both passes but only care about results for indices 0..n-1.

Actually, the standard approach: iterate i from 0 to 2n-1. Use i % n to get the actual index. Only push onto the stack during any iteration, but the answer array is only for indices [0, n-1].

Wait let me think more carefully. The approach:
1. Initialize result = [-1] * n
2. Stack holds indices (in [0, n-1])
3. For i in range(2 * n):
   - While stack and nums[i % n] > nums[stack[-1]]:
     - Pop j, result[j] = nums[i % n]
   - Only push if i < n (otherwise we'd be pushing duplicate indices)

This works because the second pass allows elements from the first pass to find greater elements that appear before them in the array.

Time: O(n) — each index pushed at most once, popped at most once.
Space: O(n)
</think>

## Next Greater Element in Circular Array

```python
from typing import List


def next_greater_circular(nums: List[int]) -> List[int]:
    """Find next greater element for each position in a circular array.

    Time Complexity: O(n)
    Space Complexity: O(n)
    """
    n = len(nums)
    result = [-1] * n
    stack: List[int] = []  # Monotonic decreasing stack of indices

    for i in range(2 * n):
        idx = i % n
        while stack and nums[idx] > nums[stack[-1]]:
            j = stack.pop()
            result[j] = nums[idx]
        # Only push during first pass to avoid duplicate indices
        if i < n:
            stack.append(i)

    return result


# --- Tests ---
def test_example():
    assert next_greater_circular([1, 2, 1]) == [2, -1, 2]

def test_all_same():
    assert next_greater_circular([5, 5, 5]) == [-1, -1, -1]

def test_decreasing():
    # [5, 4, 3, 2, 1]
    # 5 -> no greater, -1
    # 4 -> wraps to 5, so 5
    # 3 -> 4? No wait: next elements are 2, 1, 5. First greater = 5.
    # Actually: 3 -> next is 2(no), 1(no), 5(yes) -> 5
    # 2 -> next is 1(no), 5(yes) -> 5
    # 1 -> next is 5(yes) -> 5
    assert next_greater_circular([5, 4, 3, 2, 1]) == [-1, 5, 5, 5, 5]

def test_single():
    assert next_greater_circular([7]) == [-1]

def test_two_elements():
    assert next_greater_circular([1, 2]) == [2, -1]
    assert next_greater_circular([2, 1]) == [-1, 2]

test_example()
test_all_same()
test_decreasing()
test_single()
test_two_elements()
print("All circular next greater element tests passed!")
```

### Why Two Passes?

In a linear array, one right-to-left or left-to-right pass suffices. In a circular array, element at index `n-1` might have its next greater element at index `0`. By iterating `2n` times, we simulate the wrap-around:

```
Array:    [1, 2, 1]
Extended: [1, 2, 1, 1, 2, 1]  (conceptually)
```

The second pass (indices n to 2n-1) resolves stack elements whose next greater element wraps around. We still only push indices 0..n-1 once, ensuring O(n) time.
'''),

    ("thinking/algorithms", r'''Given a binary matrix of 0s and 1s, find the area of the largest rectangle containing only 1s.

Example:
matrix = [
  ["1","0","1","0","0"],
  ["1","0","1","1","1"],
  ["1","1","1","1","1"],
  ["1","0","0","1","0"]
]
Output: 6 (the rectangle spanning rows 1-2, columns 2-4)''', r'''<think>
This is "Maximal Rectangle" — a classic hard problem. The key insight is reducing it to the "Largest Rectangle in Histogram" problem.

**Approach**: For each row, build a histogram where the height at column j is the number of consecutive 1s above (and including) the current row. Then apply the largest rectangle in histogram algorithm.

For the example matrix:
- Row 0: heights = [1, 0, 1, 0, 0]
- Row 1: heights = [2, 0, 2, 1, 1]
- Row 2: heights = [3, 1, 3, 2, 2]
- Row 3: heights = [4, 0, 0, 3, 0]

For row 2 with heights [3, 1, 3, 2, 2]:
- The largest rectangle is 2*3 = 6 (heights 3, 2, 2 with min height 2... wait, that's width 3, min 2 = 6. Or heights 2,2 with width 2, area 4. Or 3,2,2 width 3, min 2, area 6. Yes, 6.)

Actually let me check: the bars are [3, 1, 3, 2, 2].
- Using bar of height 1 (index 1): width is entire array = 5, area = 5
- Using bar of height 2 (indices 2-4): width 3, area = 6
- Using bar of height 3 (index 0): width 1, area = 3
- Using bar of height 3 (index 2): width 1, area = 3
So max is 6. Correct!

Time complexity: O(rows * cols) — building histograms is O(rows * cols), and for each row we run the O(cols) histogram algorithm.

Space: O(cols) for the heights array and stack.
</think>

## Maximal Rectangle in Binary Matrix

This reduces each row to a histogram problem, then applies the O(n) largest rectangle in histogram algorithm.

```python
from typing import List


def largest_rectangle_histogram(heights: List[int]) -> int:
    """O(n) largest rectangle in histogram using monotonic stack."""
    stack: List[int] = []
    max_area = 0
    n = len(heights)

    for i in range(n):
        while stack and heights[stack[-1]] >= heights[i]:
            h = heights[stack.pop()]
            w = i if not stack else i - stack[-1] - 1
            max_area = max(max_area, h * w)
        stack.append(i)

    while stack:
        h = heights[stack.pop()]
        w = n if not stack else n - stack[-1] - 1
        max_area = max(max_area, h * w)

    return max_area


def maximal_rectangle(matrix: List[List[str]]) -> int:
    """Find the largest rectangle of 1s in a binary matrix.

    Time Complexity: O(rows * cols)
    Space Complexity: O(cols)
    """
    if not matrix or not matrix[0]:
        return 0

    rows, cols = len(matrix), len(matrix[0])
    heights = [0] * cols
    max_area = 0

    for i in range(rows):
        # Build histogram heights for current row
        for j in range(cols):
            if matrix[i][j] == "1":
                heights[j] += 1
            else:
                heights[j] = 0  # Reset: no consecutive 1s

        # Apply largest rectangle in histogram
        max_area = max(max_area, largest_rectangle_histogram(heights))

    return max_area


# --- Tests ---
def test_example():
    matrix = [
        ["1", "0", "1", "0", "0"],
        ["1", "0", "1", "1", "1"],
        ["1", "1", "1", "1", "1"],
        ["1", "0", "0", "1", "0"],
    ]
    assert maximal_rectangle(matrix) == 6

def test_single_cell():
    assert maximal_rectangle([["1"]]) == 1
    assert maximal_rectangle([["0"]]) == 0

def test_all_ones():
    matrix = [["1", "1"], ["1", "1"]]
    assert maximal_rectangle(matrix) == 4

def test_empty():
    assert maximal_rectangle([]) == 0

test_example()
test_single_cell()
test_all_ones()
test_empty()
print("All maximal rectangle tests passed!")
```

### Row-by-Row Histogram Construction

```
Matrix:          Histograms:
1 0 1 0 0       [1, 0, 1, 0, 0]  -> max rect = 1
1 0 1 1 1       [2, 0, 2, 1, 1]  -> max rect = 3
1 1 1 1 1       [3, 1, 3, 2, 2]  -> max rect = 6  <-- answer
1 0 0 1 0       [4, 0, 0, 3, 0]  -> max rect = 4
```

Each row takes O(cols) to build the histogram and O(cols) for the stack algorithm, giving O(rows * cols) total — optimal since we must read every cell at least once.
'''),

    ("thinking/algorithms", r'''Simulate an asteroid collision. Given an array of integers representing asteroids in a row, where the absolute value is size and the sign represents direction (positive = right, negative = left), determine the state of the asteroids after all collisions.

Rules: When two asteroids meet, the smaller one explodes. If equal size, both explode. Asteroids moving the same direction never meet.

Example: asteroids = [5,10,-5] -> [5,10] (10 and -5 collide, 10 survives)''', r'''<think>
This is a stack problem. Let me think about when collisions happen:
- A collision only occurs when a positive (right-moving) asteroid meets a negative (left-moving) one
- Specifically: when the stack top is positive and the current asteroid is negative
- Two negatives never collide (both going left)
- Two positives never collide (both going right)
- Negative then positive never collide (moving apart)

Algorithm using a stack:
1. For each asteroid:
   - While the stack top is positive AND current is negative AND |current| > stack top:
     - Pop the stack top (it gets destroyed)
   - If the stack top is positive AND current is negative AND they're equal:
     - Pop the stack top (both destroyed), don't push current
   - If the stack top is positive AND current is negative AND |current| < stack top:
     - Current is destroyed, don't push it
   - Otherwise (no collision): push current

Let me code this carefully. The tricky part is the while loop — a large negative asteroid can destroy multiple positive ones.

Let me trace [5, 10, -5]:
- Push 5. Stack: [5]
- Push 10. Stack: [5, 10]
- Current: -5. Stack top 10 > 0, current < 0: collision. |(-5)| = 5 < 10. Current destroyed.
- Result: [5, 10] ✓

Another trace: [-2, -1, 1, 2]:
- Push -2. Stack: [-2]
- Push -1. Stack: [-2, -1]
- Current: 1. Stack top -1 < 0, so no collision (moving apart). Push. Stack: [-2, -1, 1]
- Current: 2. Stack top 1 > 0, current 2 > 0, same direction. Push. Stack: [-2, -1, 1, 2]
Result: [-2, -1, 1, 2] ✓ (no collisions)
</think>

## Asteroid Collision Simulation

```python
from typing import List


def asteroid_collision(asteroids: List[int]) -> List[int]:
    """Simulate asteroid collisions using a stack.

    Positive = moving right, negative = moving left.
    Collision happens only when stack top is positive and current is negative.

    Time Complexity: O(n) — each asteroid pushed/popped at most once
    Space Complexity: O(n) for the stack
    """
    stack: List[int] = []

    for ast in asteroids:
        alive = True
        # Collision: stack top moving right (+), current moving left (-)
        while alive and stack and stack[-1] > 0 and ast < 0:
            if stack[-1] < abs(ast):
                # Stack top is smaller, it explodes
                stack.pop()
                # Current asteroid survives, continue checking
            elif stack[-1] == abs(ast):
                # Equal size: both explode
                stack.pop()
                alive = False
            else:
                # Stack top is larger: current asteroid explodes
                alive = False

        if alive:
            stack.append(ast)

    return stack


# --- Tests ---
def test_basic():
    assert asteroid_collision([5, 10, -5]) == [5, 10]

def test_equal_destroy():
    assert asteroid_collision([8, -8]) == []

def test_no_collision():
    assert asteroid_collision([-2, -1, 1, 2]) == [-2, -1, 1, 2]

def test_chain_destruction():
    # -10 destroys 2 and 5, collides with 10: equal, both destroyed
    assert asteroid_collision([10, 5, 2, -10]) == []

def test_large_negative():
    # -15 destroys 5 and 10
    assert asteroid_collision([5, 10, -15]) == [-15]

def test_all_negative():
    assert asteroid_collision([-1, -2, -3]) == [-1, -2, -3]

def test_complex():
    assert asteroid_collision([1, -1, -2, -3]) == [-2, -3]

test_basic()
test_equal_destroy()
test_no_collision()
test_chain_destruction()
test_large_negative()
test_all_negative()
test_complex()
print("All asteroid collision tests passed!")
```

### Collision Logic Summary

| Stack Top | Current | Action                                      |
|-----------|---------|---------------------------------------------|
| + (right) | - (left)| **Collision!** Larger survives, equal = both die |
| + (right) | + (right)| No collision — same direction              |
| - (left)  | + (right)| No collision — moving apart                |
| - (left)  | - (left)| No collision — same direction               |

The `while` loop handles chain reactions: a single large negative asteroid can destroy multiple smaller positive ones before either surviving or being destroyed itself. Each asteroid enters and leaves the stack at most once, so total work is O(n).
'''),
]
