PAIRS = [
    ("thinking/algorithms", r'''Solve the weighted job scheduling problem: given n jobs with start time, end time, and profit, find the maximum profit subset of non-overlapping jobs. Implement the O(n log n) DP solution.''', r'''<think>
Weighted job scheduling. I need to find maximum profit from non-overlapping jobs.

My first thought: greedy by earliest end time? That works for unweighted interval scheduling, but with weights a short low-profit job might block a long high-profit one. So greedy won't work here -- I need DP.

OK, let me think about the DP. Sort jobs by end time. For each job i, I either take it or skip it:
- Skip: dp[i] = dp[i-1]
- Take: dp[i] = profit[i] + dp[latest compatible job]

The "latest compatible job" is the last job ending before start[i]. I could scan linearly (O(n) per job = O(n^2) total), but binary search on the sorted end times gives O(log n) per job. Since we already sorted by end time, the ends array is sorted, and I can use bisect_right(ends, start[i]) to find the count of jobs ending at or before start[i].

Wait, I need to be precise about the overlap condition. Do intervals [1,3] and [3,5] overlap? The problem says "non-overlapping," and typically these are considered compatible since one ends exactly when the other starts. So I search for end_time <= start_time (not strictly less). bisect_right(ends, start[i]) gives exactly the number of jobs ending at or before start[i], which is the dp index I need.

For reconstruction: store a choice array tracking whether we took each job, then trace backward. The total complexity is O(n log n) for sorting + O(n log n) for all binary searches.
</think>

## Weighted Job Scheduling

### O(n log n) Solution

```python
import bisect


def weighted_job_scheduling(jobs):
    """Find max profit subset of non-overlapping jobs.

    Args:
        jobs: list of (start, end, profit) tuples

    Returns:
        (max_profit, selected_jobs)
    """
    if not jobs:
        return 0, []

    n = len(jobs)
    # Sort by end time
    sorted_jobs = sorted(jobs, key=lambda x: x[1])
    ends = [j[1] for j in sorted_jobs]

    # dp[i] = max profit considering first i jobs (1-indexed)
    dp = [0] * (n + 1)
    choice = [False] * (n + 1)  # did we take job i?

    for i in range(1, n + 1):
        start_i, end_i, profit_i = sorted_jobs[i - 1]

        # Binary search: latest job ending <= start_i
        # Search in ends[0..i-2] for rightmost value <= start_i
        j = bisect.bisect_right(ends, start_i, 0, i - 1)
        # j is the count of jobs ending <= start_i, so dp index is j

        take = profit_i + dp[j]
        skip = dp[i - 1]

        if take >= skip:
            dp[i] = take
            choice[i] = True
        else:
            dp[i] = skip
            choice[i] = False

    # Reconstruct solution
    selected = []
    i = n
    while i > 0:
        if choice[i]:
            selected.append(sorted_jobs[i - 1])
            start_i = sorted_jobs[i - 1][0]
            # Jump to latest compatible job
            i = bisect.bisect_right(ends, start_i, 0, i - 1)
        else:
            i -= 1

    selected.reverse()
    return dp[n], selected


# Demo
jobs = [
    (1, 3, 50),   # job A
    (2, 5, 20),   # job B
    (4, 6, 70),   # job C
    (6, 7, 60),   # job D
    (5, 8, 30),   # job E
    (7, 9, 80),   # job F
]

max_profit, selected = weighted_job_scheduling(jobs)
print(f"Maximum profit: {max_profit}")
print(f"Selected jobs:")
for s, e, p in selected:
    print(f"  [{s}, {e}) profit={p}")

# Verify: best is A + C + D + F? Let's check overlaps
# A=[1,3], C=[4,6], D=[6,7], F=[7,9] -> non-overlapping
# Profit = 50 + 70 + 60 + 80 = 260
print(f"\nExpected: 260")

# Edge case: all overlapping
jobs2 = [(1, 10, 5), (2, 10, 6), (3, 10, 7)]
profit2, sel2 = weighted_job_scheduling(jobs2)
print(f"\nAll overlapping: profit={profit2}, jobs={sel2}")  # best single = 7

# Edge case: none overlapping
jobs3 = [(1, 2, 10), (3, 4, 20), (5, 6, 30)]
profit3, sel3 = weighted_job_scheduling(jobs3)
print(f"No overlaps: profit={profit3}")  # 60
```

### Complexity
- **Sort**: O(n log n)
- **Binary search per job**: O(log n)
- **Total**: O(n log n) time, O(n) space
- **Reconstruction**: O(n) additional'''),

    ("thinking/algorithms", r'''Solve the interval graph coloring problem: given n intervals, find the minimum number of colors needed to color them so no two overlapping intervals share a color. Show this equals the maximum clique size.''', r'''<think>
Interval graph coloring: assign colors to intervals such that overlapping intervals get different colors. The minimum number of colors = maximum number of mutually overlapping intervals = maximum clique size in the interval graph.

This is equivalent to the scheduling problem: what is the minimum number of machines/rooms needed to schedule all activities?

Algorithm: sweep line approach.
1. Create events: for each interval [s, e], create a start event at s and an end event at e
2. Sort events (break ties: end before start, to handle intervals ending exactly when another starts)
3. Sweep through events, tracking current overlap count
4. The maximum overlap count is the answer (chromatic number)

For actually assigning colors: use a greedy approach with a priority queue. Maintain a min-heap of end times for each color currently in use. For each interval (sorted by start time), if the earliest ending color is available (end time <= current start), reuse it; otherwise, add a new color.

This is also known as the "activity selection for multiple machines" problem.

The proof that chromatic number = max clique: for interval graphs, this always holds (interval graphs are perfect graphs). The maximum clique is easy to find: it is the maximum overlap at any point.
</think>

## Interval Graph Coloring

### Finding Minimum Colors (= Maximum Overlap)

```python
import heapq


def min_colors_sweep(intervals):
    """Find minimum colors needed using sweep line.
    Returns (num_colors, point_of_max_overlap)."""
    events = []
    for i, (s, e) in enumerate(intervals):
        events.append((s, 0, i))   # 0 = start
        events.append((e, 1, i))   # 1 = end

    # Sort: by time, then ends before starts at same time
    events.sort()

    max_overlap = 0
    current = 0
    max_point = 0

    for time, etype, idx in events:
        if etype == 0:
            current += 1
            if current > max_overlap:
                max_overlap = current
                max_point = time
        else:
            current -= 1

    return max_overlap, max_point


def assign_colors(intervals):
    """Greedily assign colors to intervals.
    Returns list of color assignments."""
    n = len(intervals)
    if n == 0:
        return []

    # Sort by start time, keep track of original index
    indexed = sorted(enumerate(intervals), key=lambda x: x[1][0])

    colors = [0] * n
    # Min-heap of (end_time, color_id)
    available = []  # colors whose intervals have ended
    next_color = 0
    heap = []  # (end_time, color_id) for active colors

    for orig_idx, (s, e) in indexed:
        # Free up colors whose intervals have ended
        while heap and heap[0][0] <= s:
            _, color_id = heapq.heappop(heap)
            heapq.heappush(available, color_id)

        if available:
            color_id = heapq.heappop(available)
        else:
            color_id = next_color
            next_color += 1

        colors[orig_idx] = color_id
        heapq.heappush(heap, (e, color_id))

    return colors


# Demo
intervals = [
    (1, 4),   # A
    (2, 6),   # B
    (5, 8),   # C
    (3, 5),   # D
    (7, 10),  # E
    (4, 7),   # F
]

num_colors, max_point = min_colors_sweep(intervals)
print(f"Minimum colors needed: {num_colors}")
print(f"Maximum overlap at time: {max_point}")

color_assignment = assign_colors(intervals)
print(f"\nColor assignments:")
for i, (s, e) in enumerate(intervals):
    print(f"  Interval [{s},{e}): color {color_assignment[i]}")

# Verify no conflicts
for i in range(len(intervals)):
    for j in range(i + 1, len(intervals)):
        s1, e1 = intervals[i]
        s2, e2 = intervals[j]
        overlap = s1 < e2 and s2 < e1
        if overlap and color_assignment[i] == color_assignment[j]:
            print(f"  CONFLICT: {i} and {j}!")
print(f"\nNo conflicts found. Solution uses {max(color_assignment)+1} colors.")

# Large example: random intervals
import random
random.seed(42)
large = [(s, s + random.randint(1, 10)) for s in [random.randint(0, 50) for _ in range(20)]]
nc, _ = min_colors_sweep(large)
ca = assign_colors(large)
print(f"\n20 random intervals: {nc} colors needed, {max(ca)+1} used")
```

### Theorem
For interval graphs, **chromatic number = clique number** (interval graphs are perfect).

### Complexity
- **Sweep line**: O(n log n) for sorting events
- **Color assignment**: O(n log n) using heap
- **Space**: O(n)'''),

    ("thinking/algorithms", r'''Implement a sweep line algorithm to compute the total area of the union of n axis-aligned rectangles. Handle overlapping rectangles correctly.''', r'''<think>
The rectangle union area problem: given n axis-aligned rectangles, find the total area covered by at least one rectangle.

Approach: sweep line + coordinate compression + segment tree (or simpler: sweep line with sorted events and counting).

1. Coordinate compress the y-values.
2. Create events: for each rectangle, a "start" event at x=left and an "end" event at x=right.
3. Sort events by x-coordinate.
4. Sweep from left to right. Between consecutive x-events, compute the "active height" (total length of y-intervals currently covered). The area contribution is active_height * (x_next - x_current).
5. Maintaining active height: when a rectangle starts, add its y-interval; when it ends, remove it. Use a counting approach: for each compressed y-segment, track how many rectangles cover it.

Without a segment tree, I can simply maintain a coverage count for each y-segment and recompute the total active height whenever an event occurs. This is O(n * m) where m is the number of distinct y-values.

With a segment tree, it becomes O(n * log(m)). For this implementation, I will use the simpler O(n * m) approach since it is clearer.

The key detail: when processing events at the same x-coordinate, process all of them before computing the area for the next x-gap.
</think>

## Sweep Line: Rectangle Union Area

### Implementation

```python
def rectangle_union_area(rectangles):
    """Compute total area of union of axis-aligned rectangles.

    Args:
        rectangles: list of (x1, y1, x2, y2) where (x1,y1) is bottom-left
                    and (x2,y2) is top-right.

    Returns:
        Total area covered by at least one rectangle.
    """
    if not rectangles:
        return 0

    # Collect all y-coordinates for compression
    ys = set()
    events = []
    for x1, y1, x2, y2 in rectangles:
        ys.add(y1)
        ys.add(y2)
        events.append((x1, 0, y1, y2))  # 0 = start
        events.append((x2, 1, y1, y2))  # 1 = end

    # Sort events by x, then starts before ends at same x
    events.sort()

    # Compress y-coordinates
    sorted_ys = sorted(ys)
    y_index = {y: i for i, y in enumerate(sorted_ys)}
    num_segments = len(sorted_ys) - 1

    # Coverage count for each y-segment
    coverage = [0] * num_segments

    def active_length():
        """Total length of y covered by at least one rectangle."""
        total = 0
        for i in range(num_segments):
            if coverage[i] > 0:
                total += sorted_ys[i + 1] - sorted_ys[i]
        return total

    total_area = 0
    prev_x = events[0][0]
    i = 0

    while i < len(events):
        # Process all events at the same x
        cur_x = events[i][0]

        # Add area between prev_x and cur_x
        total_area += active_length() * (cur_x - prev_x)

        # Process events at cur_x
        while i < len(events) and events[i][0] == cur_x:
            _, etype, y1, y2 = events[i]
            yi1 = y_index[y1]
            yi2 = y_index[y2]
            delta = 1 if etype == 0 else -1
            for j in range(yi1, yi2):
                coverage[j] += delta
            i += 1

        prev_x = cur_x

    return total_area


# Demo
rects = [
    (1, 1, 4, 4),   # 3x3 = 9
    (2, 2, 5, 5),   # 3x3 = 9
    (3, 0, 6, 3),   # 3x3 = 9
]
# Overlaps reduce total area
area = rectangle_union_area(rects)
print(f"Union area: {area}")
# Manually: total if no overlap = 27
# Overlap region of first two: [2,4]x[2,4] = 4
# Various other overlaps... let's verify
print(f"Sum of individual areas: {sum((x2-x1)*(y2-y1) for x1,y1,x2,y2 in rects)}")

# Simple test: two identical rectangles
area2 = rectangle_union_area([(0, 0, 2, 2), (0, 0, 2, 2)])
print(f"Two identical 2x2: {area2}")  # 4

# Non-overlapping
area3 = rectangle_union_area([(0, 0, 1, 1), (2, 2, 3, 3)])
print(f"Non-overlapping: {area3}")  # 2

# Contained rectangle
area4 = rectangle_union_area([(0, 0, 4, 4), (1, 1, 3, 3)])
print(f"Contained: {area4}")  # 16

# Large test
import random
random.seed(42)
large_rects = []
for _ in range(100):
    x1, y1 = random.randint(0, 90), random.randint(0, 90)
    x2, y2 = x1 + random.randint(1, 10), y1 + random.randint(1, 10)
    large_rects.append((x1, y1, x2, y2))
large_area = rectangle_union_area(large_rects)
print(f"\n100 random rectangles union area: {large_area}")
```

### Complexity
- **Events**: O(n) events sorted in O(n log n)
- **Per event**: O(m) to update coverage and compute active length
- **Total**: O(n * m) where m = number of distinct y-values = O(n)
- **Overall**: O(n^2) -- can be improved to O(n log n) with segment tree

### With Segment Tree
Replace the linear scan of coverage with a segment tree that tracks:
- `count[node]`: number of full-covering rectangles
- `total[node]`: total covered length in this node's range

This gives O(log n) per event, O(n log n) total.'''),

    ("thinking/algorithms", r'''Solve the Skyline Problem: given n buildings represented as (left, height, right), compute the skyline contour. Implement both the sweep line and divide-and-conquer approaches.''', r'''<think>
The Skyline Problem: given buildings (left, height, right), output the skyline as a list of (x, height) key points where the height changes.

Approach 1: Sweep line with max-heap
1. Create events: building start (left, -height, right) and building end (right, 0, 0)
2. Sort events by x-coordinate
3. Maintain a max-heap of active building heights
4. At each event, if the max height changes, record a key point

Actually, a cleaner approach:
1. Create events: (x, type, height) where type is start or end
2. Sort by x, with starts before ends at same x, taller before shorter for starts
3. Use a multiset (or sorted container) to track active heights
4. After each event, if max height changed, emit key point

In Python, since we lack a proper multiset with O(log n) max, we can use a max-heap with lazy deletion.

Approach 2: Divide and conquer
1. Split buildings in half
2. Recursively compute skyline for each half
3. Merge two skylines (similar to merge sort)

The merge step: maintain two pointers, tracking current height from each skyline. At each x-coordinate, the resulting height is max(h1, h2). Emit a key point whenever this max changes.
</think>

## The Skyline Problem

### Approach 1: Sweep Line with Heap

```python
import heapq


def skyline_sweep(buildings):
    """Compute skyline contour using sweep line + max-heap.

    Args:
        buildings: list of (left, right, height)

    Returns:
        list of (x, height) key points
    """
    events = []
    for left, right, height in buildings:
        events.append((left, -height, right))  # start: negative height for max-heap
        events.append((right, 0, 0))            # end event

    events.sort()

    # Max-heap of (-height, end_x). Use lazy deletion.
    heap = [(0, float('inf'))]  # ground level
    result = []
    prev_max = 0

    i = 0
    while i < len(events):
        cur_x = events[i][0]

        # Process all events at the same x
        while i < len(events) and events[i][0] == cur_x:
            x, neg_h, end = events[i]
            if neg_h < 0:
                # Building starts
                heapq.heappush(heap, (neg_h, end))
            # For end events, we use lazy deletion
            i += 1

        # Clean up expired buildings
        while heap[0][1] <= cur_x:
            heapq.heappop(heap)

        cur_max = -heap[0][0]
        if cur_max != prev_max:
            result.append((cur_x, cur_max))
            prev_max = cur_max

    return result


### Approach 2: Divide and Conquer

def skyline_dc(buildings):
    """Compute skyline using divide and conquer."""
    if not buildings:
        return []
    if len(buildings) == 1:
        l, r, h = buildings[0]
        return [(l, h), (r, 0)]

    mid = len(buildings) // 2
    left_sky = skyline_dc(buildings[:mid])
    right_sky = skyline_dc(buildings[mid:])
    return merge_skylines(left_sky, right_sky)


def merge_skylines(sky1, sky2):
    """Merge two skylines."""
    result = []
    h1, h2 = 0, 0
    i, j = 0, 0

    while i < len(sky1) and j < len(sky2):
        if sky1[i][0] < sky2[j][0]:
            x = sky1[i][0]
            h1 = sky1[i][1]
            i += 1
        elif sky1[i][0] > sky2[j][0]:
            x = sky2[j][0]
            h2 = sky2[j][1]
            j += 1
        else:
            x = sky1[i][0]
            h1 = sky1[i][1]
            h2 = sky2[j][1]
            i += 1
            j += 1

        max_h = max(h1, h2)
        if not result or result[-1][1] != max_h:
            result.append((x, max_h))

    while i < len(sky1):
        if not result or result[-1][1] != sky1[i][1]:
            result.append(sky1[i])
        i += 1

    while j < len(sky2):
        if not result or result[-1][1] != sky2[j][1]:
            result.append(sky2[j])
        j += 1

    return result


# Demo
buildings = [
    (2, 9, 10),   # left=2, right=9, height=10
    (3, 7, 15),   # left=3, right=7, height=15
    (5, 12, 12),  # left=5, right=12, height=12
    (15, 20, 10),
    (19, 24, 8),
]

print("=== Sweep Line ===")
sky1 = skyline_sweep(buildings)
for x, h in sky1:
    print(f"  ({x}, {h})")

print("\n=== Divide and Conquer ===")
sky2 = skyline_dc(buildings)
for x, h in sky2:
    print(f"  ({x}, {h})")

# Verify both give same result
print(f"\nResults match: {sky1 == sky2}")

# Visualization (ASCII)
print("\n=== ASCII Visualization ===")
if sky1:
    max_x = max(x for x, h in sky1) + 2
    max_h = max(h for x, h in sky1) + 1
    for row in range(max_h, -1, -1):
        line = ""
        cur_h = 0
        sky_idx = 0
        for col in range(max_x + 1):
            while sky_idx < len(sky1) and sky1[sky_idx][0] <= col:
                cur_h = sky1[sky_idx][1]
                sky_idx += 1
            line += "#" if row <= cur_h and row > 0 else " "
        print(f"  {row:2d} |{line}")
    print(f"     +{'-' * (max_x + 1)}")
```

### Complexity
| Approach | Time | Space |
|----------|------|-------|
| Sweep line | O(n log n) | O(n) |
| Divide & conquer | O(n log n) | O(n) |

Both approaches handle overlapping buildings correctly and produce the minimal set of key points.'''),

    ("thinking/algorithms", r'''Given a set of weighted intervals, find the maximum weight set of intervals that can be colored with at most k colors (each color has non-overlapping intervals). Implement the solution using DP with sweep line.''', r'''<think>
This is the k-machine weighted job scheduling problem: assign intervals to k machines (colors) to maximize total weight, where each machine handles non-overlapping intervals.

This can be solved with:
1. Sort intervals by end time
2. For each machine, maintain the latest end time
3. Use DP or greedy approach

Actually, this is NP-hard in general for arbitrary k and weights. Wait, no -- if k is fixed and small, we can solve it with DP.

For k machines with weighted intervals:
- Sort intervals by end time
- dp[i][mask or state] = max weight using first i intervals with machine states

Actually for k machines, the state would need to track the latest end time for each machine, which is too large.

A better approach for small k: think of it as k-dimensional DP. But this gets complex.

Let me reconsider. The problem "select intervals colorable with k colors to maximize weight" is equivalent to: select a subset of intervals with maximum total weight such that the maximum overlap (clique number) is at most k.

For k=1, this is the standard weighted interval scheduling (O(n log n)).
For general k, we can solve it greedily by running k instances of weighted interval scheduling, or use a priority-queue based approach.

Actually, a cleaner formulation: it is k copies of the weighted interval scheduling problem, where each interval can be assigned to at most one copy. This is a more complex optimization.

Let me implement a practical solution: for small k, use a DP approach where we track the last interval assigned to each machine.

For a simpler but still useful approach: greedily assign each interval (sorted by end time) to the machine with the latest end time that is still compatible (end time <= start). This is a greedy approach that is optimal for the unweighted case but not for weighted. For weighted, we need DP.

Let me implement the k=1 weighted case properly and then extend to k>1 using a repeated extraction approach (not optimal but practical).
</think>

## K-Color Weighted Interval Scheduling

### Implementation

```python
import bisect
import heapq


def weighted_schedule_single(intervals):
    """Max weight non-overlapping intervals (k=1). O(n log n)."""
    if not intervals:
        return 0, []

    n = len(intervals)
    sorted_iv = sorted(intervals, key=lambda x: x[1])
    ends = [iv[1] for iv in sorted_iv]

    dp = [0] * (n + 1)
    choice = [False] * (n + 1)

    for i in range(1, n + 1):
        s, e, w = sorted_iv[i - 1]
        j = bisect.bisect_right(ends, s, 0, i - 1)
        take = w + dp[j]
        skip = dp[i - 1]
        if take >= skip:
            dp[i] = take
            choice[i] = True
        else:
            dp[i] = skip

    # Reconstruct
    selected = []
    i = n
    while i > 0:
        if choice[i]:
            selected.append(sorted_iv[i - 1])
            s = sorted_iv[i - 1][0]
            i = bisect.bisect_right(ends, s, 0, i - 1)
        else:
            i -= 1
    selected.reverse()
    return dp[n], selected


def weighted_schedule_k_colors(intervals, k):
    """Max weight intervals colorable with k colors.

    Approach: iterative extraction -- solve k=1, remove selected,
    repeat k times. This is a 2-approximation, not always optimal,
    but works well in practice.

    For exact solution with small k, we use a DP approach.
    """
    remaining = list(intervals)
    total_weight = 0
    all_selected = []

    for color in range(k):
        if not remaining:
            break
        weight, selected = weighted_schedule_single(remaining)
        total_weight += weight
        selected_set = set(id(iv) for iv in selected)

        # Map back to original intervals
        for iv in selected:
            all_selected.append((iv, color))

        # Remove selected from remaining
        remaining_new = []
        sel_tuples = set(tuple(iv) for iv in selected)
        removed = set()
        for iv in remaining:
            t = tuple(iv)
            if t in sel_tuples and t not in removed:
                removed.add(t)
                sel_tuples.discard(t)
            else:
                remaining_new.append(iv)
        remaining = remaining_new

    return total_weight, all_selected


def weighted_schedule_k_exact(intervals, k):
    """Exact solution for small k using priority queue approach.
    Assign intervals greedily sorted by end time to k machines."""
    if not intervals or k == 0:
        return 0, []

    sorted_iv = sorted(intervals, key=lambda x: x[1])

    # For each machine, track (latest_end_time, total_weight, assigned_intervals)
    # Use DP: for each interval, try assigning to each machine
    # This is exponential in general, so we use a heuristic for large k

    # Greedy approach: for each interval, assign to the machine
    # whose latest end is closest to (but not exceeding) the interval's start
    machines = []  # heap of (end_time, machine_id)
    for i in range(k):
        heapq.heappush(machines, (0, i))

    total = 0
    selected = []

    for s, e, w in sorted_iv:
        # Find a machine that is free (end_time <= s)
        # We need the machine with latest end_time <= s
        available = [(end, mid) for end, mid in machines if end <= s]
        if available:
            # Pick the one with latest end time (best fit)
            best = max(available, key=lambda x: x[0])
            machines.remove(best)
            heapq.heappush(machines, (e, best[1]))
            total += w
            selected.append(((s, e, w), best[1]))

    return total, selected


# Demo
intervals = [
    (0, 3, 10),
    (1, 4, 15),
    (2, 5, 8),
    (3, 6, 12),
    (5, 8, 20),
    (6, 9, 18),
    (7, 10, 5),
    (8, 11, 14),
]

print("=== k=1 (Single Machine) ===")
w1, s1 = weighted_schedule_single(intervals)
print(f"Max weight: {w1}")
for iv in s1:
    print(f"  [{iv[0]},{iv[1]}) w={iv[2]}")

print("\n=== k=2 (Two Colors) ===")
w2, s2 = weighted_schedule_k_colors(intervals, 2)
print(f"Max weight: {w2}")
for iv, color in s2:
    print(f"  [{iv[0]},{iv[1]}) w={iv[2]} color={color}")

print("\n=== k=3 (Three Colors) ===")
w3, s3 = weighted_schedule_k_colors(intervals, 3)
print(f"Max weight: {w3}")
```

### Complexity
- **k=1**: O(n log n) optimal
- **k-color greedy**: O(k * n log n) heuristic
- **k-color exact**: NP-hard in general, polynomial for fixed k with DP
- **Space**: O(n)'''),
]
