PAIRS = [
    ("thinking/algorithms", r'''Implement sliding window maximum: given an array and window size k, find the maximum element in each window position. Use the O(n) deque-based approach and explain why it works.''', r'''<think>
Sliding window maximum: for each position i, find max(arr[i-k+1..i]). The naive approach checks all k elements per window, giving O(nk). Could we use a max-heap? That would give O(n log k), but we can do better.

The key insight is a monotonic deque. I initially considered a regular deque storing values, but actually we need to store indices (so we can check if an element has left the window). The invariant: elements in the deque are in decreasing order of their values, and all are within the current window.

When adding arr[i]:
1. Remove from the back while arr[deque.back] <= arr[i]. These elements can never be the window max while arr[i] is present, because arr[i] is both larger and newer.
2. Add i to the back.
3. Remove from the front if front index < i - k + 1 (outside window).
4. The front is the current window maximum.

Wait, why is this O(n) and not O(nk)? I initially worried that step 1 could remove up to k elements each iteration. But here is the amortized argument: each element enters the deque exactly once and leaves at most once (either popped from the back in step 1, or from the front in step 3). So total operations across all n elements is at most 2n = O(n).

Hmm, is the correctness obvious? Consider: after step 1, all remaining deque elements are larger than arr[i]. The front element is the oldest and largest. Since we only remove elements that are smaller than newer arrivals, the front is always the true maximum. An element stays in the deque only as long as no later element in the window exceeds it -- this is the monotonic decreasing property.

Edge cases: k = 1 (every element is its own max, deque always has exactly one element), k = n (single window), all elements equal (deque fills up fully since nothing gets popped from the back), strictly decreasing (deque also fills up, front drops off one by one).
</think>

## Sliding Window Maximum

### O(n) Deque-Based Solution

```python
from collections import deque


def sliding_window_max(arr, k):
    """Find maximum in each sliding window of size k.

    Uses monotonic decreasing deque. O(n) time, O(k) space.

    Args:
        arr: input array
        k: window size

    Returns:
        list of maximums, one per window position
    """
    n = len(arr)
    if n == 0 or k == 0:
        return []

    dq = deque()  # stores indices, values are decreasing
    result = []

    for i in range(n):
        # Remove elements outside the window
        while dq and dq[0] < i - k + 1:
            dq.popleft()

        # Remove elements smaller than arr[i] from the back
        # They can never be the max while arr[i] is in the window
        while dq and arr[dq[-1]] <= arr[i]:
            dq.pop()

        dq.append(i)

        # Window is complete starting from index k-1
        if i >= k - 1:
            result.append(arr[dq[0]])

    return result


def sliding_window_max_naive(arr, k):
    """O(nk) naive approach for verification."""
    return [max(arr[i:i + k]) for i in range(len(arr) - k + 1)]


# Demo
arr = [1, 3, -1, -3, 5, 3, 6, 7]
k = 3
result = sliding_window_max(arr, k)
print(f"Array: {arr}")
print(f"k = {k}")
print(f"Window maximums: {result}")
print(f"Expected:        [3, 3, 5, 5, 6, 7]")

# Show each window
print(f"\nDetailed windows:")
for i in range(len(arr) - k + 1):
    window = arr[i:i + k]
    print(f"  [{i}:{i+k}] = {window} -> max = {max(window)}")

# Verify
assert result == sliding_window_max_naive(arr, k)

# Edge cases
print(f"\nEdge cases:")
print(f"  k=1: {sliding_window_max([5,3,4], 1)}")           # [5,3,4]
print(f"  k=n: {sliding_window_max([5,3,4], 3)}")           # [5]
print(f"  decreasing: {sliding_window_max([5,4,3,2,1], 3)}")  # [5,4,3]
print(f"  increasing: {sliding_window_max([1,2,3,4,5], 3)}")  # [3,4,5]

# Performance test
import time
import random
random.seed(42)
large = [random.randint(0, 10**6) for _ in range(100000)]
start = time.time()
r1 = sliding_window_max(large, 1000)
t_deque = time.time() - start
print(f"\n100k elements, k=1000: {t_deque:.4f}s (deque)")
```

### Why It Works
The deque maintains a **monotonic decreasing** sequence of values:
- **Front** = current maximum (largest value in window)
- Elements behind the front are "candidates" for future maximums
- When we add `arr[i]`, we remove all smaller elements because they can never be the max while `arr[i]` exists in the window
- Elements naturally expire from the front when they leave the window

### Complexity
- **Time**: O(n) -- each element enters and leaves the deque at most once
- **Space**: O(k) for the deque
- **Amortized**: O(1) per element'''),

    ("thinking/algorithms", r'''Implement an online median finder that supports adding numbers one at a time and querying the current median efficiently. Use the two-heap approach.''', r'''<think>
The online median problem: maintain a running median as numbers arrive. I initially thought about keeping a sorted list and inserting with bisect.insort -- that gives O(n) per insertion due to shifting elements. Could we use a balanced BST for O(log n)? Yes, but Python does not have one in the standard library.

The elegant solution uses two heaps. But which elements go where? My first instinct was to split at the current median, but tracking that creates a chicken-and-egg problem. Actually, the split is simpler: max_heap stores the smaller half, min_heap stores the larger half. We want quick access to the largest of the small half and the smallest of the large half -- those two values determine the median.

Invariants:
1. All elements in max_heap <= all elements in min_heap
2. |max_heap| == |min_heap| or |max_heap| == |min_heap| + 1

When sizes are equal, median = (max_heap.top + min_heap.top) / 2.0.
When max_heap has one more element, median = max_heap.top.

For the insertion procedure, I considered several approaches. One that tripped me up: what if we just add to whichever heap has fewer elements? That does not maintain the ordering invariant. Instead, the correct approach is:
1. Always add to max_heap first (guarantees it gets first pick).
2. Move max_heap's top to min_heap (this ensures the ordering invariant, since the largest element from the lower half goes to the upper half).
3. If min_heap becomes larger, move its top back to max_heap (rebalance sizes).

This three-step process looks redundant -- why not just compare and add directly? Wait, the three-step approach is actually simpler because it handles all cases uniformly. Each step is O(log n), so the total insertion cost is O(log n). Median query is O(1) since we just peek at heap tops.

Python's heapq is a min-heap only, so I negate values for the max-heap. A common source of bugs is forgetting to negate when peeking or popping.
</think>

## Online Median Finder

### Two-Heap Implementation

```python
import heapq


class MedianFinder:
    """Maintains running median with O(log n) insert and O(1) query."""

    def __init__(self):
        self.lo = []   # max-heap (negated) for lower half
        self.hi = []   # min-heap for upper half

    def add(self, num):
        """Add a number. O(log n)."""
        # Step 1: Add to max-heap (lower half)
        heapq.heappush(self.lo, -num)

        # Step 2: Balance -- move largest from lo to hi
        heapq.heappush(self.hi, -heapq.heappop(self.lo))

        # Step 3: Rebalance sizes (lo should be >= hi in size)
        if len(self.hi) > len(self.lo):
            heapq.heappush(self.lo, -heapq.heappop(self.hi))

    def median(self):
        """Return current median. O(1)."""
        if len(self.lo) > len(self.hi):
            return -self.lo[0]
        return (-self.lo[0] + self.hi[0]) / 2.0

    def size(self):
        return len(self.lo) + len(self.hi)


# Demo
mf = MedianFinder()
stream = [5, 15, 1, 3, 8, 7, 9, 2, 6, 4]

print("=== Online Median ===")
print(f"Stream: {stream}")
print()
running = []
for num in stream:
    mf.add(num)
    running.append(num)
    sorted_so_far = sorted(running)
    n = len(sorted_so_far)
    if n % 2 == 1:
        expected = sorted_so_far[n // 2]
    else:
        expected = (sorted_so_far[n // 2 - 1] + sorted_so_far[n // 2]) / 2
    computed = mf.median()
    status = "OK" if abs(computed - expected) < 1e-9 else "FAIL"
    print(f"  Add {num:2d}: median = {computed:5.1f} "
          f"(sorted: {sorted_so_far}) [{status}]")


# Performance test
import random
import time
random.seed(42)

mf2 = MedianFinder()
n = 100000
data = [random.randint(1, 10**6) for _ in range(n)]

start = time.time()
for x in data:
    mf2.add(x)
    mf2.median()
elapsed = time.time() - start
print(f"\n{n} insertions + queries: {elapsed:.3f}s")
print(f"Final median: {mf2.median()}")

# Verify final median
sorted_data = sorted(data)
expected_median = (sorted_data[n//2 - 1] + sorted_data[n//2]) / 2
print(f"Expected:     {expected_median}")
```

### How It Works
```
Lower half (max-heap)    Upper half (min-heap)
[... 3, 5]              [7, 8, ...]
      ^                  ^
   max of lo          min of hi

Median = (5 + 7) / 2 = 6.0  (even count)
Median = 5                    (odd count, lo has extra)
```

### Complexity
- **Add**: O(log n) -- at most 3 heap operations
- **Median**: O(1) -- just peek at heap tops
- **Space**: O(n) total
- **Alternative**: balanced BST (O(log n) for both ops, supports delete)'''),

    ("thinking/algorithms", r'''Implement an LRU (Least Recently Used) cache from scratch. Support get and put operations in O(1) time. Use a doubly linked list with a hash map.''', r'''<think>
LRU cache needs O(1) for both get and put. My first thought was: could we just use a dictionary and track timestamps? But finding the minimum timestamp for eviction would be O(n). What about a sorted structure? That gives O(log n) at best.

The trick is combining two data structures: a hash map for O(1) key lookup, and a doubly linked list to maintain access order. I initially considered a singly linked list, but wait -- removing a node from the middle of a singly linked list requires traversing from the head to find the predecessor, which is O(n). A doubly linked list allows O(1) removal given a reference to the node, since we can unlink it using prev/next pointers directly.

When we access a key (get or put):
- If it exists, move it to the front (most recently used).
- If it does not exist (put), add to front. If over capacity, remove from the back (least recently used) and delete it from the hash map too.

One implementation detail I almost overlooked: edge cases with empty lists, single-element lists, etc. Sentinel nodes (dummy head and tail) eliminate all these special cases. With sentinels, the "real" list is always between head and tail, so we never have to check for null pointers during insert or remove. This is a classic trick but easy to forget.

Hmm, should the hash map store keys or node references? It must store node references, because when we need to move a node to the front, we need O(1) access to the node itself (not just its value). So cache = {key -> Node}, and each Node stores both key and value. The key is stored in the node so that when we evict the LRU node from the tail, we can look up and delete its entry from the hash map.
</think>

## LRU Cache Implementation

### Doubly Linked List + Hash Map for O(1) Operations

```python
class Node:
    """Doubly linked list node."""
    __slots__ = ('key', 'value', 'prev', 'next')

    def __init__(self, key=0, value=0):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None


class LRUCache:
    """Least Recently Used cache with O(1) get and put."""

    def __init__(self, capacity):
        self.capacity = capacity
        self.cache = {}  # key -> Node

        # Sentinel nodes to avoid edge cases
        self.head = Node()  # dummy head (most recent side)
        self.tail = Node()  # dummy tail (least recent side)
        self.head.next = self.tail
        self.tail.prev = self.head

    def _add_to_front(self, node):
        """Add node right after head (most recently used)."""
        node.prev = self.head
        node.next = self.head.next
        self.head.next.prev = node
        self.head.next = node

    def _remove_node(self, node):
        """Remove node from its current position."""
        node.prev.next = node.next
        node.next.prev = node.prev

    def _move_to_front(self, node):
        """Move existing node to front (mark as most recently used)."""
        self._remove_node(node)
        self._add_to_front(node)

    def _pop_lru(self):
        """Remove and return the least recently used node."""
        lru = self.tail.prev
        self._remove_node(lru)
        return lru

    def get(self, key):
        """Get value by key. Returns -1 if not found. O(1)."""
        if key not in self.cache:
            return -1
        node = self.cache[key]
        self._move_to_front(node)
        return node.value

    def put(self, key, value):
        """Set key-value pair. Evicts LRU if at capacity. O(1)."""
        if key in self.cache:
            node = self.cache[key]
            node.value = value
            self._move_to_front(node)
            return

        # Add new node
        node = Node(key, value)
        self.cache[key] = node
        self._add_to_front(node)

        # Evict if over capacity
        if len(self.cache) > self.capacity:
            lru = self._pop_lru()
            del self.cache[lru.key]

    def __len__(self):
        return len(self.cache)

    def __repr__(self):
        items = []
        node = self.head.next
        while node != self.tail:
            items.append(f"{node.key}:{node.value}")
            node = node.next
        return f"LRU[{' -> '.join(items)}]"


# Demo
cache = LRUCache(3)
print("=== LRU Cache (capacity=3) ===")

ops = [
    ("put", 1, 10),
    ("put", 2, 20),
    ("put", 3, 30),
    ("get", 1, None),
    ("put", 4, 40),     # evicts key 2 (LRU)
    ("get", 2, None),   # returns -1
    ("get", 3, None),
    ("put", 5, 50),     # evicts key 1? No, key 1 was accessed. Evicts key 4
]

for op in ops:
    if op[0] == "put":
        cache.put(op[1], op[2])
        print(f"  put({op[1]}, {op[2]})  -> {cache}")
    else:
        result = cache.get(op[1])
        print(f"  get({op[1]}) = {result:3d} -> {cache}")

# Stress test
import time
import random
random.seed(42)

cache2 = LRUCache(1000)
start = time.time()
for _ in range(500000):
    key = random.randint(0, 2000)
    if random.random() < 0.5:
        cache2.put(key, key * 10)
    else:
        cache2.get(key)
elapsed = time.time() - start
print(f"\n500k operations: {elapsed:.3f}s")
print(f"Cache size: {len(cache2)}")

# Verify correctness with OrderedDict comparison
from collections import OrderedDict

def verify_lru(capacity, operations):
    lru = LRUCache(capacity)
    ref = OrderedDict()

    for op, key, val in operations:
        if op == "put":
            lru.put(key, val)
            if key in ref:
                ref.move_to_end(key)
            ref[key] = val
            while len(ref) > capacity:
                ref.popitem(last=False)
        else:
            r1 = lru.get(key)
            r2 = ref.get(key, -1)
            if r2 != -1:
                ref.move_to_end(key)
            if r1 != r2:
                return False
    return True

test_ops = [(("put", random.randint(0,10), random.randint(0,99))
             if random.random() < 0.5
             else ("get", random.randint(0,10), None))
            for _ in range(10000)]
print(f"Correctness test: {'PASS' if verify_lru(5, test_ops) else 'FAIL'}")
```

### Complexity
- **get**: O(1) amortized -- hash lookup + list move
- **put**: O(1) amortized -- hash insert + list operations
- **Space**: O(capacity) for nodes and hash map'''),

    ("thinking/algorithms", r'''Implement an online algorithm for computing approximate stream quantiles (p50, p90, p99) using the t-digest or P-squared algorithm. Handle arbitrary data streams without storing all values.''', r'''<think>
Streaming quantiles without storing all values -- this is trickier than it first appears. The exact solution (sort everything) requires O(n) memory, which defeats the purpose of streaming.

I considered several approaches:
1. P-squared algorithm: maintains only 5 markers -- O(1) space! But it only tracks a single quantile. Could we run multiple instances? Yes, one per quantile, but they are independent and cannot share work.
2. t-digest: more modern, clusters data points with centroids and counts. Excellent for tail quantiles (p99, p99.9). But complex to implement correctly.
3. GK algorithm (Greenwald-Khanna): deterministic epsilon-approximate quantiles. Theoretically clean but the implementation has subtle invariants.

Hmm, which to implement? I initially leaned toward t-digest, but its merging rules are fiddly. Actually, let me implement P-squared for single quantiles (it is elegant and O(1) space) plus a simple quantile sketch using a sorted buffer with periodic compression for multiple quantiles.

The P-squared algorithm (Jain & Chlamtac) works by maintaining 5 markers at positions that track the min, p/2 quantile, p quantile, (1+p)/2 quantile, and max. As data arrives, marker positions shift, and the algorithm uses parabolic interpolation to adjust marker heights without storing data. Wait, I initially thought the parabolic formula was just for smoothness, but actually it is essential for accuracy -- linear interpolation is the fallback when the parabolic estimate falls outside the neighboring markers.

For the simpler sketch approach: maintain a sorted buffer, and when it exceeds a size limit, compress by keeping every other element. This loses information but bounds memory. I considered more sophisticated compression (keeping elements near quantile boundaries), but the simple approach is surprisingly effective in practice, especially if the buffer is large enough (say 500 elements).
</think>

## Streaming Quantile Estimation

### Implementation

```python
import math
import random
import bisect


class PSquaredQuantile:
    """P-squared algorithm for single quantile estimation.
    Uses exactly 5 markers, no data storage."""

    def __init__(self, p=0.5):
        self.p = p
        self.count = 0
        self.markers = [0.0] * 5       # marker heights (values)
        self.positions = [0] * 5        # actual positions (1-indexed)
        self.desired = [0.0] * 5        # desired positions
        self.initialized = False

    def _init_markers(self, initial):
        """Initialize with first 5 observations."""
        initial.sort()
        self.markers = list(initial)
        self.positions = [1, 2, 3, 4, 5]
        p = self.p
        self.desired_inc = [0, p / 2, p, (1 + p) / 2, 1]
        self.desired = [1, 1 + 2 * p, 1 + 4 * p, 3 + 2 * p, 5]
        self.initialized = True

    def add(self, x):
        self.count += 1
        if self.count <= 5:
            if not hasattr(self, '_init_buffer'):
                self._init_buffer = []
            self._init_buffer.append(x)
            if self.count == 5:
                self._init_markers(self._init_buffer)
            return

        # Find cell k where x falls
        if x < self.markers[0]:
            self.markers[0] = x
            k = 0
        elif x >= self.markers[4]:
            self.markers[4] = x
            k = 3
        else:
            for k in range(3, -1, -1):
                if x >= self.markers[k]:
                    break

        # Increment positions of markers k+1 through 4
        for i in range(k + 1, 5):
            self.positions[i] += 1

        # Update desired positions
        n = self.count
        self.desired = [1,
                        1 + (n - 1) * self.p / 2,
                        1 + (n - 1) * self.p,
                        1 + (n - 1) * (1 + self.p) / 2,
                        n]

        # Adjust markers 1, 2, 3
        for i in range(1, 4):
            d = self.desired[i] - self.positions[i]
            if ((d >= 1 and self.positions[i + 1] - self.positions[i] > 1) or
                    (d <= -1 and self.positions[i - 1] - self.positions[i] < -1)):
                sign = 1 if d > 0 else -1
                # Parabolic formula
                qi = self.markers[i]
                qm1 = self.markers[i - 1]
                qp1 = self.markers[i + 1]
                ni = self.positions[i]
                nm1 = self.positions[i - 1]
                np1 = self.positions[i + 1]

                # P-squared parabolic interpolation
                new_q = qi + (sign / (np1 - nm1)) * (
                    (ni - nm1 + sign) * (qp1 - qi) / (np1 - ni) +
                    (np1 - ni - sign) * (qi - qm1) / (ni - nm1)
                )

                if qm1 < new_q < qp1:
                    self.markers[i] = new_q
                else:
                    # Linear interpolation fallback
                    idx = i + sign if sign > 0 else i - 1
                    self.markers[i] = qi + sign * (
                        self.markers[i + sign] - qi
                    ) / (self.positions[i + sign] - ni)

                self.positions[i] += sign

    def quantile(self):
        if not self.initialized:
            if hasattr(self, '_init_buffer') and self._init_buffer:
                buf = sorted(self._init_buffer)
                idx = int(self.p * (len(buf) - 1))
                return buf[idx]
            return 0
        return self.markers[2]


class QuantileSketch:
    """Simple quantile sketch using sorted buffer with periodic compression."""

    def __init__(self, max_buffer=500):
        self.buffer = []
        self.max_buffer = max_buffer
        self.count = 0

    def add(self, x):
        bisect.insort(self.buffer, x)
        self.count += 1
        if len(self.buffer) > self.max_buffer * 2:
            self._compress()

    def _compress(self):
        """Keep every other element to halve buffer size."""
        self.buffer = self.buffer[::2] + [self.buffer[-1]]

    def quantile(self, p):
        """Approximate p-th quantile (0 <= p <= 1)."""
        if not self.buffer:
            return 0
        idx = int(p * (len(self.buffer) - 1))
        return self.buffer[idx]

    def multi_quantile(self, quantiles):
        """Get multiple quantiles at once."""
        return {p: self.quantile(p) for p in quantiles}


# Demo
random.seed(42)
n = 100000
data = [random.gauss(100, 15) for _ in range(n)]

# P-squared for median
ps = PSquaredQuantile(p=0.5)
for x in data:
    ps.add(x)

# Quantile sketch for multiple quantiles
qs = QuantileSketch()
for x in data:
    qs.add(x)

# Compare with exact (sort all data)
sorted_data = sorted(data)
exact = {
    0.50: sorted_data[int(0.50 * n)],
    0.90: sorted_data[int(0.90 * n)],
    0.95: sorted_data[int(0.95 * n)],
    0.99: sorted_data[int(0.99 * n)],
}

print("=== Stream Quantile Estimation (Normal(100, 15)) ===")
print(f"{'Quantile':>10} {'Exact':>10} {'P-squared':>10} {'Sketch':>10}")
print(f"{'p50':>10} {exact[0.50]:>10.2f} {ps.quantile():>10.2f} {qs.quantile(0.50):>10.2f}")
for p in [0.90, 0.95, 0.99]:
    ps_p = PSquaredQuantile(p=p)
    for x in data:
        ps_p.add(x)
    print(f"{'p'+str(int(p*100)):>10} {exact[p]:>10.2f} {ps_p.quantile():>10.2f} "
          f"{qs.quantile(p):>10.2f}")

print(f"\nMemory: P-squared uses 5 markers, Sketch uses {len(qs.buffer)} elements")
print(f"Data points processed: {n}")
```

### Complexity
| Algorithm | Space | Add | Query |
|-----------|-------|-----|-------|
| P-squared | O(1) | O(1) | O(1) |
| Sketch | O(B) | O(B) amort. | O(1) |
| Exact | O(n) | O(log n) | O(1) |

P-squared is ideal for a single quantile; the sketch handles multiple quantiles with bounded memory.'''),

    ("thinking/algorithms", r'''Implement an exponential moving average (EMA) for streaming data. Show how to compute EMA efficiently, compare with simple moving average, and implement adaptive EMA that adjusts the smoothing factor based on volatility.''', r'''<think>
Exponential Moving Average (EMA) gives more weight to recent values. The formula is simple: EMA_t = alpha * x_t + (1 - alpha) * EMA_{t-1}. But I should think about what alpha means and how to choose it.

The typical formula is alpha = 2 / (N + 1) where N is the equivalent window size. I initially thought larger alpha means smoother, but wait -- that is backwards. Larger alpha means MORE weight on the newest value, so the EMA is MORE responsive (less smooth). Smaller alpha means MORE weight on history, so MORE smooth. This is easy to confuse.

Key advantage over SMA: O(1) memory vs O(N). SMA requires storing the last N values in a buffer to subtract the departing value when the window slides. EMA needs only the previous EMA value. But hmm, EMA never truly "forgets" old values -- they just decay exponentially. Is that a problem? Usually not, because the contribution of a value k steps ago is (1-alpha)^k, which decays rapidly.

For Adaptive EMA, I considered simply varying alpha based on some volatility measure. Kaufman's KAMA is a well-known approach: it uses an efficiency ratio ER = |net change over N periods| / sum of |individual changes|. When ER is near 1 (strong trend, price moves consistently in one direction), alpha is high -- track the trend closely. When ER is near 0 (choppy, noisy), alpha is low -- smooth heavily.

The formula is: smoothing_constant = ER * (fast_alpha - slow_alpha) + slow_alpha, then alpha = sc^2. Wait, why squared? I initially thought this was arbitrary, but actually squaring makes the transition between fast and slow more aggressive -- when ER is low, sc is close to slow_alpha, and squaring makes it even smaller, providing extra smoothing during noisy periods.

I will implement all three (SMA, EMA, KAMA) for comparison.
</think>

## Exponential Moving Average (EMA)

### Implementation

```python
from collections import deque


class SimpleMovingAverage:
    """SMA: average of last N values. O(N) space, O(1) update."""

    def __init__(self, window):
        self.window = window
        self.values = deque()
        self.total = 0

    def add(self, x):
        self.values.append(x)
        self.total += x
        if len(self.values) > self.window:
            self.total -= self.values.popleft()

    def value(self):
        if not self.values:
            return 0
        return self.total / len(self.values)


class ExponentialMovingAverage:
    """EMA: weighted average favoring recent values. O(1) space."""

    def __init__(self, span=None, alpha=None):
        if alpha is not None:
            self.alpha = alpha
        elif span is not None:
            self.alpha = 2.0 / (span + 1)
        else:
            self.alpha = 0.1
        self.ema = None
        self.count = 0

    def add(self, x):
        self.count += 1
        if self.ema is None:
            self.ema = x
        else:
            self.ema = self.alpha * x + (1 - self.alpha) * self.ema

    def value(self):
        return self.ema if self.ema is not None else 0


class AdaptiveEMA:
    """Kaufman's Adaptive Moving Average (KAMA).
    Adjusts smoothing factor based on market efficiency ratio."""

    def __init__(self, er_period=10, fast_period=2, slow_period=30):
        self.er_period = er_period
        self.fast_alpha = 2.0 / (fast_period + 1)
        self.slow_alpha = 2.0 / (slow_period + 1)
        self.history = deque(maxlen=er_period + 1)
        self.kama = None

    def _efficiency_ratio(self):
        """ER = |total change| / sum of |individual changes|.
        ER near 1 = strong trend, near 0 = noise."""
        if len(self.history) < 2:
            return 1.0
        values = list(self.history)
        direction = abs(values[-1] - values[0])
        volatility = sum(abs(values[i] - values[i-1])
                        for i in range(1, len(values)))
        if volatility == 0:
            return 1.0
        return direction / volatility

    def add(self, x):
        self.history.append(x)
        er = self._efficiency_ratio()

        # Smoothing constant: adapts between fast and slow
        sc = er * (self.fast_alpha - self.slow_alpha) + self.slow_alpha
        alpha = sc * sc  # squared for extra smoothing

        if self.kama is None:
            self.kama = x
        else:
            self.kama = self.kama + alpha * (x - self.kama)

    def value(self):
        return self.kama if self.kama is not None else 0


# Demo: Compare on synthetic data
import random
import math
random.seed(42)

# Generate signal: sine wave + noise
n = 200
signal = []
for i in range(n):
    clean = 50 + 20 * math.sin(2 * math.pi * i / 50)
    noise = random.gauss(0, 5)
    signal.append(clean + noise)

sma = SimpleMovingAverage(20)
ema = ExponentialMovingAverage(span=20)
kama = AdaptiveEMA(er_period=10)

sma_vals, ema_vals, kama_vals = [], [], []
for x in signal:
    sma.add(x)
    ema.add(x)
    kama.add(x)
    sma_vals.append(sma.value())
    ema_vals.append(ema.value())
    kama_vals.append(kama.value())

# Print sample points
print("=== Moving Average Comparison ===")
print(f"{'t':>4} {'Signal':>8} {'SMA(20)':>8} {'EMA(20)':>8} {'KAMA':>8}")
for t in [0, 10, 25, 50, 75, 100, 150, 199]:
    print(f"{t:4d} {signal[t]:8.2f} {sma_vals[t]:8.2f} "
          f"{ema_vals[t]:8.2f} {kama_vals[t]:8.2f}")

# Compute tracking error
def rmse(actual, predicted, start=20):
    clean = [50 + 20 * math.sin(2 * math.pi * i / 50) for i in range(n)]
    err = sum((clean[i] - predicted[i])**2 for i in range(start, n))
    return math.sqrt(err / (n - start))

print(f"\n=== RMSE vs Clean Signal (after warmup) ===")
print(f"  Raw signal: {rmse(signal, signal):.3f}")
print(f"  SMA(20):    {rmse(signal, sma_vals):.3f}")
print(f"  EMA(20):    {rmse(signal, ema_vals):.3f}")
print(f"  KAMA:       {rmse(signal, kama_vals):.3f}")

print(f"\n=== Memory Usage ===")
print(f"  SMA:  O(window) = O(20)")
print(f"  EMA:  O(1)")
print(f"  KAMA: O(er_period) = O(10)")
```

### Key Properties
| Property | SMA | EMA | KAMA |
|----------|-----|-----|------|
| Memory | O(N) | O(1) | O(N) |
| Update | O(1) | O(1) | O(1) |
| Lag | High | Medium | Adaptive |
| Noise rejection | Good | Moderate | Best |

### EMA Formula
```
EMA_t = alpha * x_t + (1 - alpha) * EMA_{t-1}
alpha = 2 / (span + 1)
```

The "half-life" (time for weight to decay by 50%) is approximately `ln(2) / alpha` periods.'''),
]
