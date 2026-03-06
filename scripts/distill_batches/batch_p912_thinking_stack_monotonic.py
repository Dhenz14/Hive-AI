PAIRS = [
    ("thinking/algorithms", r'''Given an array of integers representing heights of bars in a histogram, find the area of the largest rectangle that can be formed within the histogram. Each bar has width 1.

Example: heights = [2,1,5,6,2,3] -> Output: 10 (the rectangle spans bars with heights 5 and 6, giving 5*2=10).''', r'''<think>
This is the classic "Largest Rectangle in Histogram" problem. Let me think through the approaches.

**Brute force**: For each bar i, expand left and right while heights are >= heights[i]. Area = heights[i] * width. That is O(n^2) time. Could be acceptable for small n, but I need O(n).

My first instinct for an O(n) solution was to precompute the nearest shorter bar on the left and right for each bar using two separate passes... but wait, that requires two monotonic stack passes. Can I do it in one pass?

Actually yes -- the **single-pass monotonic stack** approach handles both boundaries simultaneously. The stack maintains indices in increasing order of heights. When we pop index `mid` because heights[i] < heights[mid]:
- Right boundary is i (the first shorter bar to the right)
- Left boundary is the new stack top + 1 (the first shorter bar to the left is at the new top)
- Width = i - stack_top - 1

Hmm, but what if the stack is empty after popping? That means there is no shorter bar to the left, so the rectangle extends all the way to the beginning. The width becomes i (from index 0 to i-1).

Let me trace through the example to make sure: [2, 1, 5, 6, 2, 3]
- i=0: push 0. Stack: [0]
- i=1: h[1]=1 < h[0]=2. Pop 0: stack empty, width=1, area=2*1=2. Push 1. Stack: [1]
- i=2: h[2]=5 > h[1]=1. Push 2. Stack: [1,2]
- i=3: h[3]=6 > h[2]=5. Push 3. Stack: [1,2,3]
- i=4: h[4]=2 < h[3]=6. Pop 3: width=4-2-1=1, area=6*1=6. Pop 2: width=4-1-1=2, area=5*2=10. Now h[4]=2 >= h[1]=1, stop. Push 4. Stack: [1,4]
- i=5: h[5]=3 > h[4]=2. Push 5. Stack: [1,4,5]
- End: Pop 5: width=6-4-1=1, area=3. Pop 4: width=6-1-1=4, area=2*4=8. Pop 1: stack empty, width=6, area=1*6=6.

Max = 10. Correct! The key insight I almost missed: after the main loop ends, there may still be bars on the stack. These bars have no shorter bar to their right, so their right boundary is n (the end of the array). I need to process the remaining stack elements with this understanding.

Each index is pushed once and popped once, so total work is O(2n) = O(n). That is optimal since we must examine each bar at least once.
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
This is a "next greater element" problem. My first thought was to scan forward from each day to find the next warmer one, but that would be O(n^2) -- too slow for large inputs.

Could I use binary search somehow? Hmm, the temperatures are not sorted, so binary search does not directly apply. What about precomputing some structure?

Actually, this is a classic monotonic stack problem. The key insight: I maintain a stack of indices whose temperatures are in decreasing order. When I encounter a temperature warmer than the stack top, I have found the answer for that stack top.

But wait, why does a decreasing stack work here? Let me think about this carefully. If I push index j with temperature 71 onto the stack, and later encounter index i with temperature 72, then i is the first day after j with a warmer temperature -- because everything between j and i (if anything) was also on the stack, meaning it was <= 71 and was already popped by something, or it is still there with a value between 71 and 72 and will be popped now too. Actually, the stack invariant guarantees that all indices between j and the current stack state have already been resolved. So when 72 pops 71, it is indeed the nearest warmer day.

Algorithm:
1. Iterate i from 0 to n-1
2. While stack is non-empty and temps[i] > temps[stack[-1]]:
   - Pop index j from stack
   - answer[j] = i - j
3. Push i onto stack
4. Any indices remaining in the stack get answer = 0 (already initialized)

Let me trace to verify: [73, 74, 75, 71, 69, 72, 76, 73]
- i=0(73): push 0. Stack: [0]
- i=1(74): 74>73, pop 0, ans[0]=1. Push 1. Stack: [1]
- i=2(75): 75>74, pop 1, ans[1]=1. Push 2. Stack: [2]
- i=3(71): 71<75, push 3. Stack: [2,3]
- i=4(69): 69<71, push 4. Stack: [2,3,4]
- i=5(72): 72>69, pop 4, ans[4]=1. 72>71, pop 3, ans[3]=2. 72<75, stop. Push 5. Stack: [2,5]
- i=6(76): 76>72, pop 5, ans[5]=1. 76>75, pop 2, ans[2]=4. Push 6. Stack: [6]
- i=7(73): 73<76, push 7. Stack: [6,7]
- Remaining: ans[6]=0, ans[7]=0.

Result: [1,1,4,2,1,1,0,0]. Correct! Each index is pushed and popped at most once, giving O(n) total.
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
This is "Next Greater Element II" -- the circular variant. In a non-circular array, a single pass with a monotonic stack suffices. But in a circular array, element at index n-1 might have its next greater element at index 0 or 1. How do I handle the wrap-around?

My first idea was to concatenate the array with itself [nums + nums] and run the standard algorithm... but that doubles the space and creates duplicate indices that I would need to deduplicate. That feels messy.

A cleaner approach: iterate i from 0 to 2n-1, using i % n for indexing. This simulates the wrap-around without actually duplicating the array. The second pass lets elements find greater values that appear earlier in the original array.

But wait, I need to be careful about what I push onto the stack. If I push during both passes, I would push the same index twice, leading to incorrect results. So I should only push indices during the first pass (i < n). During the second pass, I only pop -- resolving any remaining elements whose next greater element wraps around.

Let me verify: result = [-1] * n, stack holds indices [0, n-1].
For i in range(2 * n):
   - While stack and nums[i % n] > nums[stack[-1]]:
     - Pop j, result[j] = nums[i % n]
   - Only push if i < n

Hmm, could any element remain unresolved after two passes? Only if there is no greater element in the entire array -- i.e., the element is the global maximum (or tied for it). In that case, result stays -1, which is correct since no greater element exists even with wrap-around.

Time: O(n) -- each index is pushed at most once (first pass only) and popped at most once (during either pass). The second pass does at most n pops total.
Space: O(n) for the stack and result.
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
This is "Maximal Rectangle" -- a classic hard problem. My first thought is to check all possible rectangles defined by top-left and bottom-right corners, but that would be O(rows^2 * cols^2) -- way too slow.

Could I use dynamic programming? I considered DP where dp[r][c] represents the largest rectangle ending at (r,c), but the state space gets complicated because rectangles can have different aspect ratios.

Wait, there is a brilliant reduction. I can convert each row into a histogram problem! For each row, the "height" at column j is the number of consecutive 1s above (and including) the current row. Then I apply the O(n) Largest Rectangle in Histogram algorithm to each row's histogram.

For the example matrix:
- Row 0: heights = [1, 0, 1, 0, 0]
- Row 1: heights = [2, 0, 2, 1, 1]
- Row 2: heights = [3, 1, 3, 2, 2]
- Row 3: heights = [4, 0, 0, 3, 0]

Hmm, let me verify row 3. Column 0 has been all 1s from row 0 through row 3, so height = 4. Column 2 was 1 in rows 0-2 but is 0 in row 3, so height resets to 0. That is correct -- a 0 in the matrix breaks the consecutive run and resets the height.

For row 2 with heights [3, 1, 3, 2, 2]:
- Using bar of height 1 (index 1) with full width: area = 1*5 = 5
- Using bar of height 2 spanning indices 2-4: width 3, area = 2*3 = 6
- Using bar of height 3 (index 0 or 2): width 1, area = 3

So max for row 2 is 6. Actually, could there be a larger rectangle I am missing? Let me check: index 3 and 4 have heights 2 and 2, so a rectangle of height 2, width 2 = 4. Indices 2,3,4 have min height 2, so 2*3=6. That matches. The overall answer is max across all rows = 6. Correct!

Time: O(rows * cols) since building each histogram row is O(cols) and the histogram algorithm is O(cols). Space: O(cols) for the heights array and stack.
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
This is an asteroid collision problem. Let me think about when collisions actually happen.

My first instinct was that any two asteroids next to each other with different signs collide, but actually that is wrong. A negative asteroid moving left and a positive asteroid to its right moving right are moving APART -- they never meet. Collisions only happen when a positive (right-moving) asteroid is followed by a negative (left-moving) one. Specifically: when the stack top is positive and the current asteroid is negative.

So the collision conditions are:
- (+) followed by (-): COLLISION
- (+) followed by (+): same direction, no collision
- (-) followed by (-): same direction, no collision
- (-) followed by (+): moving apart, no collision

This naturally suggests a stack approach. But wait, there is a tricky part I need to handle carefully: a large negative asteroid can destroy multiple positive ones in sequence. For example, [5, 3, -10] -- the -10 first destroys 3, then destroys 5. So I need a while loop, not just an if statement.

Algorithm using a stack:
1. For each asteroid, while the stack top is positive AND current is negative:
   - If |current| > stack top: pop (stack top destroyed), continue checking
   - If |current| == stack top: pop (both destroyed), stop
   - If |current| < stack top: current destroyed, stop
2. If current survived all collisions, push it

Hmm, I need to track whether the current asteroid is still "alive" through the while loop. Let me use a boolean flag.

Let me trace [5, 10, -5]:
- Push 5. Stack: [5]
- Push 10. Stack: [5, 10]
- Current: -5. Stack top 10 > 0, current < 0: collision. |-5| = 5 < 10. Current destroyed, alive=False.
- Result: [5, 10]. Correct!

Another trace: [10, 5, 2, -10]:
- Stack builds to [10, 5, 2]. Current: -10.
- |-10|=10 > 2: pop 2. |-10|=10 > 5: pop 5. |-10|=10 == 10: pop 10, both destroyed.
- Result: []. Both the big asteroid and everything it hit are gone. Correct!
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
