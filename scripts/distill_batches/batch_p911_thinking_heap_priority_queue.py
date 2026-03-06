PAIRS = [
    ("thinking/algorithms", r'''Merge K sorted linked lists into one sorted linked list. Return the head of the merged list. Each list may have up to 500 nodes, and there can be up to 10^4 lists. Design an efficient solution.''', r'''<think>
Let me think about the different approaches.

**Brute force**: Collect all values, sort them, build a new list. Time: O(N log N) where N is total number of nodes. Space: O(N). This works but doesn't leverage the fact that the lists are already sorted.

**Compare one by one**: At each step, compare the heads of all K lists and pick the minimum. Time: O(N * K) — for each of the N nodes, we scan K heads. Too slow for K = 10^4.

**Priority Queue / Min-Heap**: Maintain a min-heap of size K containing the current head of each list. Pop the minimum, advance that list's pointer, push the next node. Time: O(N log K). Space: O(K). This is optimal.

Why O(N log K)? Each of the N nodes is pushed and popped from the heap exactly once. Each heap operation is O(log K) since the heap has at most K elements.

**Divide and Conquer**: Merge lists in pairs, like merge sort. log(K) rounds, each round processes N total nodes. Time: O(N log K). Same asymptotic complexity but heap approach is simpler to implement.

I'll go with the heap approach. One Python gotcha: heapq compares tuples lexicographically. If two nodes have equal values, Python will try to compare the ListNode objects, which will fail. I need a tiebreaker — I'll use an incrementing counter as the second tuple element.
</think>

## Merge K Sorted Lists with a Min-Heap

```python
import heapq
from typing import List, Optional


class ListNode:
    def __init__(self, val: int = 0, next: Optional['ListNode'] = None) -> None:
        self.val = val
        self.next = next


def merge_k_lists(lists: List[Optional[ListNode]]) -> Optional[ListNode]:
    """Merge K sorted linked lists using a min-heap.

    Time Complexity: O(N log K) where N = total nodes, K = number of lists
    Space Complexity: O(K) for the heap
    """
    heap: List[tuple] = []
    counter = 0  # Tiebreaker to avoid comparing ListNode objects

    # Initialize heap with head of each non-empty list
    for node in lists:
        if node:
            heapq.heappush(heap, (node.val, counter, node))
            counter += 1

    dummy = ListNode(0)
    current = dummy

    while heap:
        val, _, node = heapq.heappop(heap)
        current.next = node
        current = current.next

        if node.next:
            heapq.heappush(heap, (node.next.val, counter, node.next))
            counter += 1

    return dummy.next


# --- Helper functions for testing ---
def build_list(values: List[int]) -> Optional[ListNode]:
    dummy = ListNode(0)
    curr = dummy
    for v in values:
        curr.next = ListNode(v)
        curr = curr.next
    return dummy.next


def list_to_array(head: Optional[ListNode]) -> List[int]:
    result = []
    while head:
        result.append(head.val)
        head = head.next
    return result


# --- Tests ---
def test_basic():
    lists = [build_list([1, 4, 5]), build_list([1, 3, 4]), build_list([2, 6])]
    result = list_to_array(merge_k_lists(lists))
    assert result == [1, 1, 2, 3, 4, 4, 5, 6], f"Got {result}"

def test_empty_lists():
    lists = [None, build_list([1]), None]
    result = list_to_array(merge_k_lists(lists))
    assert result == [1]

def test_all_empty():
    assert merge_k_lists([]) is None
    assert merge_k_lists([None, None]) is None

test_basic()
test_empty_lists()
test_all_empty()
print("All merge K sorted lists tests passed!")
```

### Complexity Breakdown

| Approach          | Time         | Space | Notes                        |
|-------------------|-------------|-------|------------------------------|
| Brute force sort  | O(N log N)  | O(N)  | Ignores sorted property      |
| Compare all heads | O(N·K)      | O(1)  | Too slow for large K         |
| **Min-heap**      | **O(N log K)** | **O(K)** | **Optimal for this problem** |
| Divide & conquer  | O(N log K)  | O(log K) | Same time, different style   |

The heap always contains at most K elements, so each push/pop is O(log K). Every node enters and leaves the heap exactly once, giving O(N log K) total.
'''),

    ("thinking/algorithms", r'''Design a class that finds the K-th largest element in a stream of numbers. Implement the constructor that takes K and an initial array, and an `add(val)` method that adds a new value and returns the K-th largest element.''', r'''<think>
Let me think about this carefully.

The K-th largest element in a collection of n numbers — if we sort descending, it's the element at index K-1. We need this to be efficient for repeated `add()` calls.

**Naive approach**: Keep all elements sorted, return the K-th from end. Each add is O(n) for insertion into sorted position.

**Better: Min-heap of size K**: This is the classic trick.
- Maintain a min-heap of exactly K elements, representing the K largest seen so far.
- The K-th largest is always the root (minimum of these K elements).
- When a new value arrives:
  - If heap size < K: push it
  - Else if val > heap[0]: pop the min and push val
  - Return heap[0]

Why a min-heap and not a max-heap? Because we want quick access to the smallest of the K largest — that's the K-th largest. If a new element is bigger than this smallest, it displaces it.

Time per add: O(log K)
Space: O(K)

This is much better than O(n) per add or O(n log n) re-sorting.

Edge case: what if K equals the total number of elements? Then every element is in the heap and the K-th largest is the minimum of all elements.
</think>

## K-th Largest Element in a Stream

```python
import heapq
from typing import List


class KthLargest:
    """Finds the K-th largest element in a stream using a min-heap of size K.

    Time Complexity:
        - __init__: O(n log K) where n = len(initial array)
        - add: O(log K) per call
    Space Complexity: O(K)
    """

    def __init__(self, k: int, nums: List[int]) -> None:
        self.k = k
        self.heap: List[int] = []

        # Build initial heap — only keep top K elements
        for num in nums:
            self._push(num)

    def _push(self, val: int) -> None:
        if len(self.heap) < self.k:
            heapq.heappush(self.heap, val)
        elif val > self.heap[0]:
            heapq.heapreplace(self.heap, val)  # Pop min + push in one operation

    def add(self, val: int) -> int:
        """Add a value to the stream and return the K-th largest element."""
        self._push(val)
        return self.heap[0]


# --- Tests ---
def test_leetcode_example():
    kl = KthLargest(3, [4, 5, 8, 2])
    # Heap keeps top 3: [4, 5, 8], so 3rd largest = 4
    assert kl.add(3) == 4   # stream: [2,3,4,5,8], 3rd largest = 4
    assert kl.add(5) == 5   # stream: [2,3,4,5,5,8], 3rd largest = 5
    assert kl.add(10) == 5  # stream: [2,3,4,5,5,8,10], 3rd largest = 5
    assert kl.add(9) == 8   # stream: [2,3,4,5,5,8,9,10], 3rd largest = 8
    assert kl.add(4) == 8   # stream: [2,3,4,4,5,5,8,9,10], 3rd largest = 8

def test_k_equals_one():
    kl = KthLargest(1, [])
    assert kl.add(5) == 5   # max so far
    assert kl.add(3) == 5
    assert kl.add(10) == 10

def test_initial_fewer_than_k():
    kl = KthLargest(3, [1])
    # Heap: [1], size < K
    kl.add(2)  # Heap: [1, 2], size < K
    assert kl.add(3) == 1  # Heap: [1, 2, 3], now kth largest = 1

test_leetcode_example()
test_k_equals_one()
test_initial_fewer_than_k()
print("All KthLargest stream tests passed!")
```

### Why Min-Heap of Size K?

The key insight: we only care about the top K elements. The min-heap's root is the **smallest** among those K, which is exactly the K-th largest overall. Elements smaller than the root can never become the K-th largest, so we discard them.

| Operation | Heap size | Time    |
|-----------|-----------|---------|
| `add`     | ≤ K       | O(log K)|
| `__init__`| Build     | O(n log K)|

Using `heapreplace` (combined pop-push) is faster than separate `heappop` + `heappush` since it only sifts once.
'''),

    ("thinking/algorithms", r'''Given a string s, rearrange it so that no two adjacent characters are the same. If not possible, return an empty string. Example: "aab" -> "aba", "aaab" -> "" (impossible).''', r'''<think>
Let me think about when this is possible and how to construct the arrangement.

**When is it impossible?** If any character appears more than ceil(n/2) times, it's impossible. For a string of length n, the most frequent character can fill at most every other position, giving ceil(n/2) slots.

**Greedy approach with max-heap:**
At each step, place the character with the highest remaining frequency. But we can't place the same character twice in a row, so if the most frequent character is the same as the last placed character, we place the second most frequent instead.

Algorithm:
1. Count frequencies
2. Build a max-heap (negate frequencies for Python's min-heap)
3. At each step:
   - Pop the most frequent character
   - If it's the same as the last placed, pop the second most frequent instead (and push the first back)
   - Place the character, decrement its count, push back if count > 0

Wait, there's a simpler way to think about this. I can maintain a "previous" character that's temporarily excluded:

1. Pop top from heap -> (count, char)
2. Append char to result
3. If there's a "previous" waiting to be re-added with count > 0, push it back
4. Set current (count-1, char) as the new "previous"

This ensures we never pick the same character twice in a row because the last-used character is always held out of the heap for one round.

Time: O(n log A) where A is alphabet size (26 for lowercase). Since log 26 is constant, effectively O(n).
Space: O(A) = O(1) for the heap.
</think>

## Reorganize String — No Adjacent Same Characters

```python
import heapq
from collections import Counter
from typing import Optional


def reorganize_string(s: str) -> str:
    """Rearrange string so no two adjacent characters are the same.

    Returns empty string if impossible.

    Time Complexity: O(n log A) where A = alphabet size (26) -> effectively O(n)
    Space Complexity: O(A) = O(1)
    """
    counts = Counter(s)
    n = len(s)

    # Impossibility check
    max_freq = max(counts.values(), default=0)
    if max_freq > (n + 1) // 2:
        return ""

    # Max-heap: store (-count, char) since Python has min-heap
    heap = [(-count, char) for char, count in counts.items()]
    heapq.heapify(heap)

    result: list[str] = []
    prev_count, prev_char = 0, ''

    while heap:
        neg_count, char = heapq.heappop(heap)
        # Re-add previous character if it still has remaining count
        if prev_count < 0:
            heapq.heappush(heap, (prev_count, prev_char))

        result.append(char)
        # Hold current character out for one round
        prev_count = neg_count + 1  # +1 because we used one (and counts are negative)
        prev_char = char

    return ''.join(result)


# --- Tests ---
def test_basic():
    result = reorganize_string("aab")
    assert result in ("aba",), f"Got {result}"

def test_impossible():
    assert reorganize_string("aaab") == ""

def test_longer():
    s = "aaabbbccc"
    result = reorganize_string(s)
    assert len(result) == len(s)
    for i in range(1, len(result)):
        assert result[i] != result[i - 1], f"Adjacent duplicate at {i}: {result}"
    assert Counter(result) == Counter(s)

def test_single():
    assert reorganize_string("a") == "a"

def test_two_chars():
    result = reorganize_string("aabb")
    assert len(result) == 4
    for i in range(1, len(result)):
        assert result[i] != result[i - 1]

test_basic()
test_impossible()
test_longer()
test_single()
test_two_chars()
print("All reorganize string tests passed!")
```

### Algorithm Walkthrough for "aaabbbccc"

```
Heap: [(-3,'a'), (-3,'b'), (-3,'c')]
Step 1: Pop 'a'(3), place 'a'. Hold out a(2).
Step 2: Pop 'b'(3), push back a(2). Place 'b'. Hold out b(2).
Step 3: Pop 'c'(3), push back b(2). Place 'c'. Hold out c(2).
Step 4: Pop 'a'(2), push back c(2). Place 'a'. Hold out a(1).
...continues until all placed.
Result: "abcabcabc" or similar valid arrangement
```

The "hold out one round" trick guarantees no character can appear adjacent to itself, while the greedy max-frequency strategy ensures we don't get stuck (as long as the impossibility condition isn't triggered).
'''),

    ("thinking/algorithms", r'''Implement a Task Scheduler. Given a list of tasks represented by characters and a cooldown period n, find the minimum number of intervals needed to complete all tasks. Each interval is 1 unit. The same task must be separated by at least n intervals. You can insert idle intervals.

Example: tasks = ["A","A","A","B","B","B"], n = 2 -> Output: 8 (A B idle A B idle A B)''', r'''<think>
Let me think through this problem carefully.

First, the key insight: the task with the highest frequency determines the minimum time. Let's call the max frequency `f_max` and the number of tasks that have this max frequency `count_max`.

**Greedy formula approach:**
Consider task A with frequency f_max. We need f_max - 1 gaps of size n+1 between consecutive A's:

```
A _ _ A _ _ A
```

Each gap has n+1 slots (including the A). The last group doesn't need trailing idles.

Framework time = (f_max - 1) * (n + 1) + count_max

But this formula might give a value less than the total number of tasks (when cooldown is small relative to variety of tasks). In that case, the answer is simply len(tasks) because we can interleave without any idle time.

So: answer = max(len(tasks), (f_max - 1) * (n + 1) + count_max)

Let me verify with the example:
- tasks = ["A","A","A","B","B","B"], n = 2
- f_max = 3, count_max = 2 (both A and B appear 3 times)
- Formula: (3-1) * (2+1) + 2 = 6 + 2 = 8
- len(tasks) = 6
- max(6, 8) = 8 ✓

Another test: tasks = ["A","A","A","B","B","B"], n = 0
- Formula: (3-1) * 1 + 2 = 4
- len(tasks) = 6
- max(6, 4) = 6 ✓ (no cooldown, just do all 6)

I could also simulate this with a max-heap + queue approach, which would be more intuitive but O(n * total_tasks). The formula approach is O(n) and more elegant.

Let me implement both — the formula for efficiency and a simulation to verify.
</think>

## Task Scheduler with Cooldown

### Solution 1: O(n) Mathematical Formula

```python
from collections import Counter
from typing import List


def least_interval(tasks: List[str], n: int) -> int:
    """Find minimum intervals to complete all tasks with cooldown n.

    Time Complexity: O(T) where T = len(tasks)
    Space Complexity: O(26) = O(1) (at most 26 distinct tasks)
    """
    counts = Counter(tasks)
    f_max = max(counts.values())
    # How many tasks share the maximum frequency
    count_max = sum(1 for freq in counts.values() if freq == f_max)

    # Framework: (f_max - 1) groups of (n+1) slots + final group of count_max
    framework = (f_max - 1) * (n + 1) + count_max

    # If we have enough variety, no idle time needed
    return max(len(tasks), framework)


# --- Solution 2: Simulation with heap (for verification) ---
import heapq
from collections import deque


def least_interval_simulation(tasks: List[str], n: int) -> int:
    """Simulate task scheduling with max-heap and cooldown queue."""
    counts = Counter(tasks)
    heap = [-c for c in counts.values()]
    heapq.heapify(heap)

    time = 0
    cooldown: deque = deque()  # (available_time, neg_remaining_count)

    while heap or cooldown:
        time += 1
        if heap:
            neg_count = heapq.heappop(heap)
            remaining = neg_count + 1  # Used one (neg_count is negative)
            if remaining < 0:  # Still has tasks left
                cooldown.append((time + n, remaining))
        # Check if any task is ready to be re-added
        if cooldown and cooldown[0][0] == time:
            _, neg_count = cooldown.popleft()
            heapq.heappush(heap, neg_count)

    return time


# --- Tests ---
def test_example():
    tasks = ["A", "A", "A", "B", "B", "B"]
    assert least_interval(tasks, 2) == 8
    assert least_interval_simulation(tasks, 2) == 8

def test_no_cooldown():
    tasks = ["A", "A", "A", "B", "B", "B"]
    assert least_interval(tasks, 0) == 6

def test_high_cooldown():
    tasks = ["A", "A", "A"]
    # A _ _ A _ _ A with n=2 -> 7
    assert least_interval(tasks, 2) == 7
    assert least_interval_simulation(tasks, 2) == 7

def test_many_tasks():
    tasks = ["A", "B", "C", "D", "E", "F"]
    # All unique, no cooldown needed regardless of n
    assert least_interval(tasks, 2) == 6

test_example()
test_no_cooldown()
test_high_cooldown()
test_many_tasks()
print("All task scheduler tests passed!")
```

### Why the Formula Works

Visualize the schedule as a grid with `f_max - 1` full rows plus a final partial row:

```
For tasks=["A","A","A","B","B","B"], n=2:

A B idle
A B idle
A B        <- final row: only count_max tasks

Width = n+1 = 3, Rows = f_max-1 = 2, Final = count_max = 2
Total = 2*3 + 2 = 8
```

When there are many distinct tasks (more than n+1 types), the idle slots get filled and the answer becomes simply `len(tasks)`.
'''),

    ("thinking/algorithms", r'''Meeting Rooms II: Given a list of meeting time intervals [start, end), find the minimum number of conference rooms required so that no two overlapping meetings share a room.

Example: intervals = [[0,30],[5,10],[15,20]] -> 2 rooms needed (meetings 1 and 2 overlap).''', r'''<think>
Classic interval scheduling problem. Let me consider approaches:

**Approach 1: Sort + Min-Heap**
Sort meetings by start time. Use a min-heap tracking the end times of active meetings (one per room). For each meeting:
- If the earliest ending room is free (heap top ≤ current start), reuse it (pop and push new end)
- Otherwise, allocate a new room (just push new end)
The heap size at the end is the answer.

Time: O(n log n) for sorting + O(n log n) for heap operations = O(n log n)

**Approach 2: Event sweep / chronological ordering**
Create events: +1 for each start, -1 for each end. Sort all events by time (break ties: end before start, so a room freed at time t can be reused by a meeting starting at time t). Sweep through and track the running count; the maximum is the answer.

Time: O(n log n)

Both are optimal. The sweep approach is elegant and has lower constant factor since it avoids heap operations.

Wait, for the sweep approach tie-breaking: if a meeting ends at time t and another starts at time t, they don't overlap (intervals are [start, end)). So end events should come before start events at the same time. This means: sort by (time, type) where end=0 and start=1.

Let me implement both approaches.
</think>

## Meeting Rooms II — Minimum Conference Rooms

### Solution 1: Min-Heap Approach

```python
import heapq
from typing import List


def min_meeting_rooms_heap(intervals: List[List[int]]) -> int:
    """Find minimum rooms using a min-heap of end times.

    Time Complexity: O(n log n)
    Space Complexity: O(n)
    """
    if not intervals:
        return 0

    intervals.sort(key=lambda x: x[0])  # Sort by start time

    # Heap stores end times of rooms in use
    rooms: List[int] = []
    heapq.heappush(rooms, intervals[0][1])

    for i in range(1, len(intervals)):
        start, end = intervals[i]
        # If earliest available room is free, reuse it
        if rooms[0] <= start:
            heapq.heappop(rooms)
        heapq.heappush(rooms, end)

    return len(rooms)


### Solution 2: Event Sweep (Chronological Ordering)

def min_meeting_rooms_sweep(intervals: List[List[int]]) -> int:
    """Find minimum rooms using event sweep line.

    Time Complexity: O(n log n)
    Space Complexity: O(n)
    """
    if not intervals:
        return 0

    events: List[tuple[int, int]] = []
    for start, end in intervals:
        events.append((start, 1))   # Meeting starts: need a room
        events.append((end, -1))    # Meeting ends: free a room

    # Sort by time; at same time, process ends (-1) before starts (+1)
    events.sort()

    max_rooms = 0
    current_rooms = 0
    for _, delta in events:
        current_rooms += delta
        max_rooms = max(max_rooms, current_rooms)

    return max_rooms


# --- Tests ---
def test_example():
    intervals = [[0, 30], [5, 10], [15, 20]]
    assert min_meeting_rooms_heap(intervals) == 2
    assert min_meeting_rooms_sweep(intervals) == 2

def test_no_overlap():
    intervals = [[0, 5], [5, 10], [10, 15]]
    assert min_meeting_rooms_heap(intervals) == 1
    assert min_meeting_rooms_sweep(intervals) == 1

def test_all_overlap():
    intervals = [[0, 10], [1, 10], [2, 10]]
    assert min_meeting_rooms_heap(intervals) == 3
    assert min_meeting_rooms_sweep(intervals) == 3

def test_empty():
    assert min_meeting_rooms_heap([]) == 0
    assert min_meeting_rooms_sweep([]) == 0

def test_single():
    assert min_meeting_rooms_heap([[1, 5]]) == 1

test_example()
test_no_overlap()
test_all_overlap()
test_empty()
test_single()
print("All meeting rooms tests passed!")
```

### Comparing the Two Approaches

| Approach   | Time       | Space | Key Idea                              |
|-----------|------------|-------|---------------------------------------|
| Min-Heap  | O(n log n) | O(n)  | Track earliest-ending room for reuse  |
| Sweep Line| O(n log n) | O(n)  | Count overlapping meetings at any point|

The sweep line approach is conceptually simpler: the maximum overlap at any point in time equals the minimum rooms needed. The heap approach more directly simulates room assignment and can be extended to track which room each meeting uses.

Both correctly handle the half-open interval property: `[0, 5)` and `[5, 10)` don't overlap, so they share one room.
'''),
]
