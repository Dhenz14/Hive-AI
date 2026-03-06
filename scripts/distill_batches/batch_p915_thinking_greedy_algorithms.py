PAIRS = [
    ("thinking/algorithms", r'''Implement the Activity Selection Problem: given n activities with start and finish times, find the maximum number of non-overlapping activities that can be performed by a single person.''', r'''<think>
The Activity Selection Problem is a classic greedy algorithm problem. The key insight is that we should always pick the activity that finishes earliest, because that leaves the most room for subsequent activities.

Let me reason through why greedy works here. If we sort by finish time, picking the earliest-finishing activity is optimal because:
1. It never blocks more activities than any alternative choice would
2. Any solution that picks a later-finishing activity can be transformed to pick the earlier one without losing count

Algorithm steps:
1. Sort activities by finish time
2. Pick the first activity (earliest finish)
3. For each subsequent activity, if its start time >= last selected finish time, select it
4. Return the selected activities

Edge cases to consider:
- Empty input
- All activities overlap (only pick one)
- No overlaps at all (pick all)
- Activities with same finish time but different start times
- Activities with zero duration (start == finish)

Time complexity: O(n log n) for sorting, O(n) for selection = O(n log n) total.
Space complexity: O(n) for storing the result, O(1) extra if we sort in place.

This greedy approach is provably optimal. A formal proof uses exchange argument: suppose an optimal solution OPT does not include the earliest-finishing activity a1. Replace the first activity in OPT with a1. Since a1 finishes no later, the replacement is valid and the count stays the same. By induction, greedy matches OPT.
</think>

**Activity Selection Problem -- Greedy Approach**

```python
def activity_selection(activities):
    """
    Select maximum non-overlapping activities.

    Args:
        activities: list of (start, finish) tuples
    Returns:
        list of selected activities (as indices)
    """
    if not activities:
        return []

    # Create indexed list and sort by finish time
    indexed = sorted(enumerate(activities), key=lambda x: x[1][1])

    selected = [indexed[0][0]]
    last_finish = indexed[0][1][1]

    for i in range(1, len(indexed)):
        idx, (start, finish) = indexed[i]
        if start >= last_finish:
            selected.append(idx)
            last_finish = finish

    return selected


# Example usage
activities = [(1, 4), (3, 5), (0, 6), (5, 7), (3, 9), (5, 9),
              (6, 10), (8, 11), (8, 12), (2, 14), (12, 16)]

result = activity_selection(activities)
print(f"Selected activity indices: {result}")
print(f"Maximum activities: {len(result)}")
for i in result:
    print(f"  Activity {i}: start={activities[i][0]}, finish={activities[i][1]}")
```

**Output:**
```
Selected activity indices: [0, 3, 7, 10]
Maximum activities: 4
```

**Why Greedy Works (Exchange Argument):**
- Sort by finish time. The earliest-finishing activity a1 is always safe to pick.
- Proof: If OPT skips a1 and picks some other first activity a_k, we can swap a_k for a1. Since a1 finishes no later than a_k, all subsequent selections remain valid. The count does not decrease.
- By induction on the remaining subproblem, greedy matches any optimal solution.

**Complexity:**
- Time: O(n log n) -- dominated by sorting
- Space: O(n) for the result list'''),

    ("thinking/algorithms", r'''Implement Huffman Coding: given a string or frequency table, build the Huffman tree and generate variable-length prefix codes. Include both encoding and decoding functions.''', r'''<think>
Huffman coding is a greedy algorithm for lossless data compression. The idea is to assign shorter bit codes to more frequent characters and longer codes to less frequent ones.

Algorithm:
1. Count frequency of each character
2. Create a leaf node for each character, put them all in a min-heap (priority queue) keyed by frequency
3. While the heap has more than one node:
   a. Extract the two nodes with lowest frequency
   b. Create a new internal node with these two as children, frequency = sum of their frequencies
   c. Insert the new node back into the heap
4. The remaining node is the root of the Huffman tree
5. Traverse the tree: left edge = 0, right edge = 1, leaf paths give the codes

Why greedy works: By always merging the two least frequent symbols, we ensure the least frequent symbols end up deepest in the tree (longest codes). This minimizes the weighted path length, which equals the total encoded length.

Edge cases:
- Single character string (code is "0" by convention)
- Empty string
- All characters have equal frequency (balanced tree)
- Two characters only

Time complexity: O(n log n) where n is number of distinct characters -- each heap operation is O(log n) and we do O(n) of them.
Space complexity: O(n) for the tree and code table.

The resulting code is a prefix code -- no codeword is a prefix of another -- which allows unambiguous decoding.
</think>

**Huffman Coding -- Complete Implementation**

```python
import heapq
from collections import Counter


class HuffmanNode:
    def __init__(self, char=None, freq=0, left=None, right=None):
        self.char = char
        self.freq = freq
        self.left = left
        self.right = right

    def __lt__(self, other):
        return self.freq < other.freq


def build_huffman_tree(freq_map):
    """Build Huffman tree from character frequencies."""
    if not freq_map:
        return None

    heap = [HuffmanNode(char=c, freq=f) for c, f in freq_map.items()]
    heapq.heapify(heap)

    # Special case: single unique character
    if len(heap) == 1:
        node = heapq.heappop(heap)
        root = HuffmanNode(freq=node.freq, left=node)
        return root

    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        merged = HuffmanNode(freq=left.freq + right.freq,
                             left=left, right=right)
        heapq.heappush(heap, merged)

    return heap[0]


def generate_codes(root):
    """Traverse tree to build code table."""
    codes = {}

    def dfs(node, code):
        if node is None:
            return
        if node.char is not None:
            codes[node.char] = code if code else "0"
            return
        dfs(node.left, code + "0")
        dfs(node.right, code + "1")

    dfs(root, "")
    return codes


def huffman_encode(text):
    """Encode text using Huffman coding."""
    if not text:
        return "", None, {}
    freq = Counter(text)
    tree = build_huffman_tree(freq)
    codes = generate_codes(tree)
    encoded = "".join(codes[ch] for ch in text)
    return encoded, tree, codes


def huffman_decode(encoded, tree):
    """Decode Huffman-encoded bit string using the tree."""
    if not encoded or tree is None:
        return ""
    result = []
    node = tree
    for bit in encoded:
        node = node.left if bit == "0" else node.right
        if node.char is not None:
            result.append(node.char)
            node = tree
    return "".join(result)


# Demo
text = "huffman coding is a greedy algorithm"
encoded, tree, codes = huffman_encode(text)

print("Character codes:")
for ch, code in sorted(codes.items()):
    print(f"  '{ch}': {code}")

print(f"\nOriginal size:  {len(text) * 8} bits")
print(f"Encoded size:   {len(encoded)} bits")
print(f"Compression:    {100 - len(encoded)*100//(len(text)*8)}%")

decoded = huffman_decode(encoded, tree)
print(f"Decoded matches: {decoded == text}")
```

**Complexity:**
- Tree construction: O(n log n) where n = distinct characters
- Encoding: O(m) where m = text length
- Decoding: O(m) traversing bits
- Space: O(n) for tree + O(m) for encoded output'''),

    ("thinking/algorithms", r'''Solve the Fractional Knapsack Problem: given items with weights and values and a knapsack capacity W, maximize the total value. You can take fractions of items.''', r'''<think>
The Fractional Knapsack problem differs from 0/1 knapsack in that we can take fractions of items. This makes it solvable by a greedy approach, whereas 0/1 knapsack requires DP.

Key insight: We should prioritize items by their value-to-weight ratio (value density). Take as much as possible of the highest-density item first, then the next, and so on until the knapsack is full.

Why greedy is optimal here: If we have remaining capacity c, filling it with the highest value-per-unit-weight material gives the maximum possible value for that capacity. No rearrangement can improve it because every unit of weight we add comes from the best available source.

Algorithm:
1. Compute value/weight ratio for each item
2. Sort items by ratio in descending order
3. For each item in sorted order:
   a. If item fits entirely, take it all
   b. Otherwise, take the fraction that fills remaining capacity
   c. Stop when capacity is exhausted

Edge cases:
- Capacity is 0 -- return 0
- All items fit -- take everything
- Item with weight 0 but positive value -- infinite ratio, take it (handle division carefully)
- Single item heavier than capacity -- take fraction

Time: O(n log n) for sorting.
Space: O(n) for the ratio array (or O(1) extra if we sort in place).

This is one of the simplest greedy proofs: at each step we are extracting maximum value per unit weight, and since fractions are allowed, there is no "waste" from partial items.
</think>

**Fractional Knapsack -- Greedy Solution**

```python
def fractional_knapsack(items, capacity):
    """
    Solve fractional knapsack problem.

    Args:
        items: list of (weight, value) tuples
        capacity: maximum weight capacity
    Returns:
        (max_value, selections) where selections is list of
        (index, fraction_taken) tuples
    """
    if capacity <= 0 or not items:
        return 0.0, []

    # Compute value/weight ratio, sort descending
    indexed = []
    for i, (w, v) in enumerate(items):
        ratio = v / w if w > 0 else float('inf')
        indexed.append((ratio, i, w, v))
    indexed.sort(reverse=True)

    total_value = 0.0
    remaining = capacity
    selections = []

    for ratio, idx, weight, value in indexed:
        if remaining <= 0:
            break

        if weight <= remaining:
            # Take entire item
            total_value += value
            remaining -= weight
            selections.append((idx, 1.0))
        else:
            # Take fraction
            fraction = remaining / weight
            total_value += value * fraction
            remaining = 0
            selections.append((idx, fraction))

    return total_value, selections


# Example
items = [
    (10, 60),   # weight=10, value=60, ratio=6.0
    (20, 100),  # weight=20, value=100, ratio=5.0
    (30, 120),  # weight=30, value=120, ratio=4.0
]
capacity = 50

max_val, selections = fractional_knapsack(items, capacity)

print(f"Knapsack capacity: {capacity}")
print(f"Maximum value: {max_val}")
print("\nItem selections:")
for idx, frac in selections:
    w, v = items[idx]
    print(f"  Item {idx} (w={w}, v={v}): "
          f"take {frac*100:.0f}% -> value {v*frac:.1f}")
```

**Output:**
```
Knapsack capacity: 50
Maximum value: 240.0

Item selections:
  Item 0 (w=10, v=60): take 100% -> value 60.0
  Item 1 (w=20, v=100): take 100% -> value 100.0
  Item 2 (w=30, v=120): take 67% -> value 80.0
```

**Why Greedy is Optimal:**
- Each unit of capacity should hold the most valuable material available
- Since we can split items, there is no "wasted" capacity or forced suboptimal choices
- Sorting by value/weight ratio guarantees each unit filled maximizes marginal value

**Contrast with 0/1 Knapsack:**
- 0/1 knapsack does NOT allow fractions, so greedy fails (need DP)
- Example: items (10,60), (20,100) with capacity 20. Greedy picks item 0 (ratio 6) for value 60, but item 1 gives value 100

**Complexity:**
- Time: O(n log n) for sorting
- Space: O(n) for indexed array'''),

    ("thinking/algorithms", r'''Solve the Job Scheduling with Deadlines problem: given n jobs each with a deadline and profit, schedule jobs on a single machine (one job per time slot) to maximize total profit. Each job takes exactly one unit of time.''', r'''<think>
This is the classic Job Sequencing with Deadlines problem. Each job has a deadline d_i and profit p_i. We can do at most one job per time slot. We want to maximize total profit.

Greedy strategy: Sort jobs by profit in descending order. For each job, try to schedule it as late as possible (at or before its deadline). This is greedy because we prioritize high-profit jobs and place them as late as possible to leave earlier slots open for other jobs.

Why "as late as possible"? If we place a job in the latest available slot before its deadline, we preserve earlier slots for jobs with earlier deadlines. This maximizes flexibility.

Implementation approaches:
1. Simple array-based: O(n^2) -- for each job, scan backwards from min(deadline, n) to find an empty slot
2. Disjoint Set (Union-Find): O(n * alpha(n)) -- nearly linear

I will implement both for educational value but focus on the array approach for clarity.

Algorithm (array-based):
1. Sort jobs by profit descending
2. Create a slot array of size max_deadline, initialized to -1 (empty)
3. For each job in sorted order:
   a. Start from min(deadline-1, max_slot-1) and go backwards
   b. Find the first empty slot
   c. If found, assign the job there and add its profit
4. Return total profit and schedule

Edge cases:
- All jobs have same deadline (only one can be scheduled at that slot, but earlier slots might be available)
- Deadline is 0 (impossible to schedule)
- All deadlines exceed n (all jobs can potentially be scheduled)

Time: O(n^2) for the simple version, O(n log n) with union-find optimization.
Space: O(n) for the slot array.
</think>

**Job Scheduling with Deadlines -- Greedy Approach**

```python
def job_scheduling(jobs):
    """
    Schedule jobs to maximize profit.

    Args:
        jobs: list of (job_id, deadline, profit)
    Returns:
        (max_profit, scheduled_jobs)
    """
    if not jobs:
        return 0, []

    # Sort by profit descending
    sorted_jobs = sorted(jobs, key=lambda x: x[2], reverse=True)

    # Find maximum deadline to determine slot count
    max_deadline = max(j[1] for j in sorted_jobs)
    n = min(len(jobs), max_deadline)

    # Slot array: slot[i] = job_id or None
    slots = [None] * n
    total_profit = 0
    scheduled = []

    for job_id, deadline, profit in sorted_jobs:
        # Try to place job as late as possible, up to its deadline
        # Slots are 0-indexed: slot i represents time unit i+1
        for t in range(min(deadline, n) - 1, -1, -1):
            if slots[t] is None:
                slots[t] = job_id
                total_profit += profit
                scheduled.append((job_id, t + 1, profit))
                break

    scheduled.sort(key=lambda x: x[1])  # sort by time slot
    return total_profit, scheduled


# Union-Find optimized version
class DSU:
    def __init__(self, n):
        self.parent = list(range(n + 1))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x, y):
        self.parent[self.find(x)] = self.find(y)


def job_scheduling_fast(jobs):
    """O(n log n) version using Union-Find."""
    if not jobs:
        return 0, []

    sorted_jobs = sorted(jobs, key=lambda x: x[2], reverse=True)
    max_deadline = max(j[1] for j in sorted_jobs)
    dsu = DSU(max_deadline)

    total_profit = 0
    scheduled = []

    for job_id, deadline, profit in sorted_jobs:
        available = dsu.find(min(deadline, max_deadline))
        if available > 0:
            dsu.union(available, available - 1)
            total_profit += profit
            scheduled.append((job_id, available, profit))

    scheduled.sort(key=lambda x: x[1])
    return total_profit, scheduled


# Example
jobs = [
    ("A", 2, 100),
    ("B", 1, 19),
    ("C", 2, 27),
    ("D", 1, 25),
    ("E", 3, 15),
]

profit, schedule = job_scheduling(jobs)
print(f"Max profit: {profit}")
for jid, slot, p in schedule:
    print(f"  Slot {slot}: Job {jid} (profit={p})")

print()
profit2, schedule2 = job_scheduling_fast(jobs)
print(f"Max profit (fast): {profit2}")
for jid, slot, p in schedule2:
    print(f"  Slot {slot}: Job {jid} (profit={p})")
```

**Output:**
```
Max profit: 142
  Slot 1: Job C (profit=27)
  Slot 2: Job A (profit=100)
  Slot 3: Job E (profit=15)
```

**Complexity:**
- Naive: O(n^2) time, O(n) space
- Union-Find: O(n log n) time (sorting dominates), O(n) space'''),

    ("thinking/algorithms", r'''Solve the Minimum Number of Platforms problem: given arrival and departure times of trains at a station, find the minimum number of platforms required so that no train has to wait.''', r'''<think>
This is a classic greedy/sweep-line problem. We need to find the maximum number of trains present at the station at any point in time -- that gives us the minimum platforms needed.

Approach 1 -- Sort and sweep:
1. Put all arrivals and departures into a single event list
2. Sort events by time
3. Sweep through: increment counter on arrival, decrement on departure
4. Track the maximum counter value

But there is a subtlety: if an arrival and departure happen at the same time, which comes first? If a train departs at time t and another arrives at t, they can share a platform. So departures should be processed before arrivals at the same time.

Approach 2 -- Sort separately:
1. Sort arrivals and departures arrays separately
2. Use two pointers to merge them
3. If next event is an arrival, increment platforms needed
4. If next event is a departure, decrement
5. Track maximum

The two-pointer approach is cleaner and avoids the tie-breaking issue if we handle it correctly: when arrival[i] <= departure[j], it is an arrival event (use <= because if equal, the arriving train needs a platform even though another is departing -- actually this depends on interpretation).

Wait, let me reconsider. If arrival == departure at same time, can the departing train free the platform for the arriving one? Usually yes. So we process departure first at ties: if arrival[i] > departure[j], process departure. But with <=, arrival[i] <= departure[j] means we process arrival. If arr[i] == dep[j], processing arrival first means we need an extra platform. The correct interpretation: if a train departs at time t, the platform is available at time t for another train. So we should process departure first at ties: use arr[i] > dep[j] to trigger arrival processing, meaning at ties we process departure.

Time: O(n log n), Space: O(1) extra beyond the sorted arrays.
</think>

**Minimum Platforms -- Sweep Line / Two Pointers**

```python
def min_platforms(arrivals, departures):
    """
    Find minimum platforms needed at a train station.

    Args:
        arrivals: list of arrival times
        departures: list of departure times
    Returns:
        minimum number of platforms required
    """
    n = len(arrivals)
    if n == 0:
        return 0

    arr = sorted(arrivals)
    dep = sorted(departures)

    platforms_needed = 0
    max_platforms = 0
    i, j = 0, 0

    while i < n:
        if arr[i] <= dep[j]:
            # A train arrives before (or when) one departs
            # It needs a new platform
            platforms_needed += 1
            max_platforms = max(max_platforms, platforms_needed)
            i += 1
        else:
            # A train departs, freeing a platform
            platforms_needed -= 1
            j += 1

    return max_platforms


def min_platforms_event_sweep(arrivals, departures):
    """Alternative: explicit event-based sweep line."""
    events = []
    for t in arrivals:
        events.append((t, 1))    # +1 for arrival
    for t in departures:
        events.append((t, -1))   # -1 for departure

    # Sort by time; at same time, departures (-1) before arrivals (+1)
    events.sort(key=lambda x: (x[0], x[1]))

    current = 0
    max_platforms = 0
    for time, delta in events:
        current += delta
        max_platforms = max(max_platforms, current)

    return max_platforms


# Example
arrivals   = [900, 940, 950, 1100, 1500, 1800]
departures = [910, 1200, 1120, 1130, 1900, 2000]

result1 = min_platforms(arrivals, departures)
result2 = min_platforms_event_sweep(arrivals, departures)

print(f"Minimum platforms (two-pointer): {result1}")
print(f"Minimum platforms (event sweep): {result2}")

# Detailed timeline
print("\nEvent timeline:")
events = [(t, "ARR") for t in arrivals] + [(t, "DEP") for t in departures]
events.sort()
count = 0
for t, typ in events:
    count += 1 if typ == "ARR" else -1
    print(f"  {t:4d} {typ} -> {count} trains at station")
```

**Output:**
```
Minimum platforms (two-pointer): 3
Minimum platforms (event sweep): 3
```

**Key Insight:** The minimum platforms equals the maximum overlap of train intervals. This is equivalent to finding the maximum number of overlapping intervals at any time point.

**Tie-breaking matters:**
- If arrival time == departure time, we process the departure first
- This allows the departing train to free its platform for the arriving one
- In the event sweep, sorting by (time, delta) with delta=-1 before +1 handles this

**Complexity:**
- Time: O(n log n) for sorting
- Space: O(1) extra for two-pointer; O(n) for event sweep variant'''),
]
