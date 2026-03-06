PAIRS = [
    ("thinking/algorithms", r'''Implement the Activity Selection Problem: given n activities with start and finish times, find the maximum number of non-overlapping activities that can be performed by a single person.''', r'''<think>
The Activity Selection Problem. I need to maximize the number of non-overlapping activities.

My first idea was to sort by start time and greedily pick the earliest starting activity... but wait, that is wrong. An activity that starts early but finishes very late could block many shorter activities. For example, (0, 100) starts earliest but blocks everything from 0 to 100.

What about sorting by duration? Pick the shortest activity first? That also fails -- a short activity in the middle could overlap with two non-overlapping activities that together give a better count.

Actually, the correct greedy choice is to sort by finish time and always pick the earliest-finishing activity. Why? Because finishing early leaves the maximum remaining time for subsequent activities. Let me convince myself with the exchange argument: suppose an optimal solution OPT picks some activity a_k first instead of a1 (the earliest finisher). Since a1 finishes no later than a_k, replacing a_k with a1 cannot invalidate any subsequent selection. So the modified solution has the same count but starts with a1. By induction on the remaining subproblem, greedy matches OPT.

Algorithm:
1. Sort activities by finish time
2. Pick the first activity (earliest finish)
3. For each subsequent activity, if its start time >= last selected finish time, select it

Hmm, I should clarify the boundary condition: is start == finish of previous a conflict? If activities are [start, finish) (half-open), then start >= last_finish allows back-to-back scheduling. If [start, finish] (closed), then start > last_finish is needed. I will use >= since half-open intervals are the standard convention.

Time: O(n log n) for sorting + O(n) for selection.
Space: O(n) for storing results.
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
Huffman coding: assign shorter codes to frequent characters, longer codes to rare ones.

I initially considered a simple approach: sort characters by frequency and assign codes 0, 1, 00, 01, 10, 11, etc. But wait, that does not produce a prefix code -- "0" would be a prefix of "00", making decoding ambiguous. I need a tree-based construction to guarantee the prefix-free property.

The Huffman algorithm builds a binary tree bottom-up:
1. Create a leaf node for each character with its frequency
2. Put all nodes in a min-heap keyed by frequency
3. While heap has more than one node: extract two smallest, merge into a new internal node, reinsert
4. The remaining node is the root

But why always merge the two LEAST frequent? I considered merging the two MOST frequent first (to get them out of the way), but that would actually give them the longest codes -- exactly the opposite of what we want. Since the merge order determines tree depth, and deeper nodes get longer codes, we want rare characters to be merged first (pushed deeper). The two least frequent characters should be siblings at the maximum depth because they contribute the least total bits (frequency * code_length) from being deep.

Hmm, there is an edge case I almost overlooked: what if there is only one unique character (e.g., "aaaa")? Then the heap starts with one node and we never enter the merge loop. The tree is just a single leaf with no edges, so the character has no code. By convention, I should assign it code "0" so it can still be encoded.

Time: O(n log n) where n is distinct characters. Each of the n-1 merges involves two heap operations at O(log n) each.
Space: O(n) for the tree and code table.

The result is a prefix code: since codes correspond to root-to-leaf paths in a binary tree, no code is a prefix of another, which guarantees unambiguous decoding.
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
Fractional Knapsack: we can take fractions of items. My first instinct was to use dynamic programming like the 0/1 knapsack... but wait, fractions make this fundamentally different. In 0/1, we face a discrete choice (take or leave), which requires DP. With fractions, there are no discrete decisions to force suboptimal local choices -- we can always take exactly the right amount.

This means greedy should work. The key insight: prioritize items by value-to-weight ratio (value density). Take as much as possible of the highest-density item first.

But hmm, why is greedy provably optimal here? Suppose we have remaining capacity c. Filling it with the highest-ratio material gives value = c * best_ratio. Any alternative allocation uses some capacity on lower-ratio material, giving less total value for the same weight. Since fractions are allowed, there is no "wasted capacity" from partially taking items. Each unit of weight contributes its item's ratio to the total value, and we maximize by always using the best ratio.

I initially wondered: could it be better to save capacity for a heavy-but-high-value item later? No, because with fractions we can take just a fraction of that item. We are never forced to take all-or-nothing, so there is no benefit to reserving capacity.

Contrast with 0/1 knapsack where greedy fails: items (10,60) and (20,100) with capacity 20. Greedy by ratio picks item 0 (ratio 6.0) for value 60, but item 1 (ratio 5.0, value 100) is better. This only fails because we cannot take a fraction of item 1 in the 0/1 case.

Algorithm:
1. Compute value/weight ratio for each item
2. Sort by ratio descending
3. Greedily take items: whole if they fit, fractional if they do not

Edge case: item with weight 0 but positive value gives infinite ratio. I should handle division carefully, perhaps treating it as float('inf').

Time: O(n log n) for sorting.
Space: O(n) for the indexed array.
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
Job Sequencing with Deadlines: each job has a deadline and profit, one job per time slot, maximize total profit.

My first thought was to sort by deadline and schedule greedily... but wait, that prioritizes urgency over value. A job with deadline 1 and profit 5 would be scheduled before a job with deadline 2 and profit 100. We should prioritize profit instead.

Greedy strategy: Sort jobs by profit in descending order. For each job, try to schedule it.

But at WHICH slot should I schedule it? I initially thought: the earliest available slot before its deadline. But actually, scheduling it as LATE as possible is better. Why? Because earlier slots are more constrained (they might be needed by jobs with earlier deadlines). Placing a job as late as possible preserves earlier slots for future jobs. This maximizes scheduling flexibility.

Let me trace an example: jobs A(deadline=2, profit=100), C(deadline=2, profit=27), E(deadline=3, profit=15).
- Sort by profit: A(100), C(27), E(15)
- A: latest slot before deadline 2 -> slot 2. Assign.
- C: latest slot before deadline 2 -> slot 2 taken, try slot 1. Assign.
- E: latest slot before deadline 3 -> slot 3. Assign.
- Total: 100 + 27 + 15 = 142. All scheduled!

If I had placed A at slot 1 instead (earliest available), then C would need slot 2, and E slot 3 -- same result here. But in other cases, "latest available" prevents conflicts.

Implementation:
1. Simple array-based: O(n^2) -- scan backwards from deadline for each job
2. Union-Find optimization: O(n * alpha(n)) -- find(d) gives the latest available slot <= d, and union merges a slot with its predecessor when used

The Union-Find approach is clever: initially each slot points to itself. When slot t is used, union(t, t-1) so that future find(t) returns t-1, the next available slot. This avoids the linear scan.

Time: O(n^2) for simple, O(n log n) with union-find (sorting dominates).
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
