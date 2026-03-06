PAIRS = [
    ("thinking/algorithms", r'''Design and implement an LFU (Least Frequently Used) cache. Support get and put operations in O(1) time. Handle frequency ties by evicting the least recently used among least frequent entries.''', r'''<think>
LFU cache evicts the entry with the smallest access frequency. If there are ties, evict the least recently used among those.

For O(1) operations, we need:
1. A hash map from key to (value, frequency, node_reference)
2. A hash map from frequency to a doubly-linked list of keys at that frequency (ordered by recency)
3. A variable tracking the minimum frequency

Operations:
- get(key): increment frequency of key, move it to the next frequency bucket
- put(key, value): if exists, update value and increment frequency. If new and at capacity, evict the LRU entry from the min-frequency bucket.

The frequency buckets use doubly-linked lists (like LRU cache) so that:
- Adding to front (most recent): O(1)
- Removing LRU (from tail): O(1)
- Moving between buckets: O(1) remove + O(1) add

When a bucket becomes empty and its frequency equals min_freq, increment min_freq.
When inserting a new key, min_freq = 1.

This is a classic LeetCode hard problem and a good interview question.
</think>

## LFU Cache Implementation

### O(1) Get and Put Operations

```python
class Node:
    __slots__ = ('key', 'value', 'freq', 'prev', 'next')
    def __init__(self, key=0, value=0):
        self.key = key
        self.value = value
        self.freq = 1
        self.prev = None
        self.next = None


class FreqList:
    """Doubly linked list for a frequency bucket.
    Most recent at head, LRU at tail."""
    def __init__(self):
        self.head = Node()
        self.tail = Node()
        self.head.next = self.tail
        self.tail.prev = self.head
        self.size = 0

    def add_to_front(self, node):
        node.prev = self.head
        node.next = self.head.next
        self.head.next.prev = node
        self.head.next = node
        self.size += 1

    def remove_node(self, node):
        node.prev.next = node.next
        node.next.prev = node.prev
        self.size -= 1

    def remove_lru(self):
        """Remove and return the least recently used node."""
        if self.size == 0:
            return None
        lru = self.tail.prev
        self.remove_node(lru)
        return lru

    def is_empty(self):
        return self.size == 0


class LFUCache:
    """Least Frequently Used cache with O(1) get and put."""

    def __init__(self, capacity):
        self.capacity = capacity
        self.min_freq = 0
        self.key_to_node = {}      # key -> Node
        self.freq_to_list = {}     # freq -> FreqList

    def _get_freq_list(self, freq):
        if freq not in self.freq_to_list:
            self.freq_to_list[freq] = FreqList()
        return self.freq_to_list[freq]

    def _increment_freq(self, node):
        """Move node from freq bucket to freq+1 bucket."""
        old_freq = node.freq
        old_list = self.freq_to_list[old_freq]
        old_list.remove_node(node)

        # If old bucket is empty and was the min_freq, increment min_freq
        if old_list.is_empty() and old_freq == self.min_freq:
            self.min_freq += 1

        node.freq += 1
        new_list = self._get_freq_list(node.freq)
        new_list.add_to_front(node)

    def get(self, key):
        """Get value by key. Returns -1 if not found. O(1)."""
        if key not in self.key_to_node:
            return -1
        node = self.key_to_node[key]
        self._increment_freq(node)
        return node.value

    def put(self, key, value):
        """Set key-value pair. Evicts LFU if at capacity. O(1)."""
        if self.capacity <= 0:
            return

        if key in self.key_to_node:
            node = self.key_to_node[key]
            node.value = value
            self._increment_freq(node)
            return

        # Evict if at capacity
        if len(self.key_to_node) >= self.capacity:
            min_list = self.freq_to_list.get(self.min_freq)
            if min_list:
                evicted = min_list.remove_lru()
                if evicted:
                    del self.key_to_node[evicted.key]

        # Insert new node
        node = Node(key, value)
        self.key_to_node[key] = node
        self.min_freq = 1
        freq_list = self._get_freq_list(1)
        freq_list.add_to_front(node)

    def __len__(self):
        return len(self.key_to_node)


# Demo
print("=== LFU Cache (capacity=3) ===")
cache = LFUCache(3)

ops = [
    ("put", 1, 10),
    ("put", 2, 20),
    ("put", 3, 30),
    ("get", 1, None),    # freq of 1 becomes 2
    ("get", 1, None),    # freq of 1 becomes 3
    ("get", 2, None),    # freq of 2 becomes 2
    ("put", 4, 40),      # evicts key 3 (freq=1, LFU)
    ("get", 3, None),    # returns -1
    ("get", 4, None),    # freq of 4 becomes 2
    ("put", 5, 50),      # evicts key 2 or 4 (both freq=2, LRU among them)
]

for op in ops:
    if op[0] == "put":
        cache.put(op[1], op[2])
        print(f"  put({op[1]}, {op[2]})")
    else:
        result = cache.get(op[1])
        print(f"  get({op[1]}) = {result}")

# Stress test
import random
import time
random.seed(42)

cache2 = LFUCache(1000)
start = time.time()
for _ in range(500000):
    key = random.randint(0, 2000)
    if random.random() < 0.5:
        cache2.put(key, key * 10)
    else:
        cache2.get(key)
elapsed = time.time() - start
print(f"\n500k operations: {elapsed:.3f}s")
```

### Complexity
- **get**: O(1) -- hash lookup + frequency list operations
- **put**: O(1) -- hash + list operations + possible eviction
- **Space**: O(capacity)

### Key Design Decisions
1. **Frequency buckets**: each bucket is a doubly-linked list (LRU within same frequency)
2. **min_freq tracking**: updated on eviction and insertion
3. **No cleanup**: empty frequency lists are left (lazy cleanup)'''),

    ("thinking/algorithms", r'''Design and implement a time-based key-value store. Support set(key, value, timestamp) and get(key, timestamp) that returns the value with the largest timestamp <= the given timestamp.''', r'''<think>
A time-based key-value store needs to:
1. Store multiple (value, timestamp) pairs per key
2. For get(key, t), find the value with the largest timestamp <= t

Since timestamps are added in non-decreasing order (a natural assumption for time-based systems), we can use binary search for get queries.

Data structure:
- Hash map from key to a list of (timestamp, value) pairs
- Each list is sorted by timestamp (maintained naturally if inserts are in order)
- get uses binary search to find the latest timestamp <= query timestamp

If timestamps are not in order, we need to maintain sorted order (use bisect.insort).

Edge cases:
- get with no matching timestamp (return empty/default)
- Multiple sets at the same timestamp (keep the latest)
- Empty key
</think>

## Time-Based Key-Value Store

### Implementation

```python
import bisect


class TimeMap:
    """Time-based key-value store with O(1) set and O(log n) get."""

    def __init__(self):
        self.store = {}  # key -> list of (timestamp, value)

    def set(self, key, value, timestamp):
        """Store value with timestamp. O(1) if timestamps are increasing."""
        if key not in self.store:
            self.store[key] = []
        self.store[key].append((timestamp, value))

    def get(self, key, timestamp):
        """Get value at key with largest timestamp <= given timestamp.
        Returns empty string if no such value exists. O(log n)."""
        if key not in self.store:
            return ""

        entries = self.store[key]
        # Binary search for largest timestamp <= given timestamp
        idx = bisect.bisect_right(entries, (timestamp, chr(127))) - 1

        if idx < 0:
            return ""
        return entries[idx][1]

    def get_all_versions(self, key):
        """Get all stored versions for a key."""
        return self.store.get(key, [])

    def get_range(self, key, t_start, t_end):
        """Get all values in timestamp range [t_start, t_end]."""
        if key not in self.store:
            return []
        entries = self.store[key]
        lo = bisect.bisect_left(entries, (t_start,))
        hi = bisect.bisect_right(entries, (t_end, chr(127)))
        return entries[lo:hi]


# Demo
print("=== Time-Based Key-Value Store ===")
tm = TimeMap()

# Set values at different timestamps
tm.set("price", "100", 1)
tm.set("price", "110", 5)
tm.set("price", "105", 10)
tm.set("price", "120", 15)

tm.set("name", "Alice", 1)
tm.set("name", "Bob", 8)

# Queries
print("Stored data:")
for key in ["price", "name"]:
    print(f"  {key}: {tm.get_all_versions(key)}")

print("\nPoint queries:")
queries = [
    ("price", 0),   # before any data -> ""
    ("price", 1),   # exact match -> "100"
    ("price", 3),   # between 1 and 5 -> "100"
    ("price", 5),   # exact -> "110"
    ("price", 7),   # between 5 and 10 -> "110"
    ("price", 12),  # between 10 and 15 -> "105"
    ("price", 20),  # after all -> "120"
    ("name", 5),    # between 1 and 8 -> "Alice"
    ("name", 10),   # after 8 -> "Bob"
    ("missing", 5), # non-existent key -> ""
]

for key, ts in queries:
    result = tm.get(key, ts)
    print(f"  get('{key}', {ts}) = '{result}'")

# Range query
print(f"\nRange query: price timestamps [3, 12]:")
range_results = tm.get_range("price", 3, 12)
print(f"  {range_results}")

# Performance test
import time
import random
random.seed(42)

tm2 = TimeMap()
start = time.time()
for i in range(100000):
    tm2.set("key" + str(i % 100), str(i), i)
for _ in range(100000):
    key = "key" + str(random.randint(0, 99))
    ts = random.randint(0, 100000)
    tm2.get(key, ts)
elapsed = time.time() - start
print(f"\n100k sets + 100k gets: {elapsed:.3f}s")
```

### Complexity
- **set**: O(1) amortized (append to list)
- **get**: O(log n) where n = number of entries for that key
- **Space**: O(total entries across all keys)

### Design Variants
- **With TTL**: add expiration, skip expired entries during get
- **With snapshots**: maintain a version number for bulk operations
- **Persistent**: use persistent balanced BST for historical queries'''),

    ("thinking/algorithms", r'''Design and implement a Range Module that tracks ranges of numbers. Support addRange, removeRange, and queryRange operations efficiently.''', r'''<think>
A Range Module manages a set of disjoint intervals. Operations:
1. addRange(left, right): add all numbers in [left, right) to the set
2. removeRange(left, right): remove all numbers in [left, right) from the set
3. queryRange(left, right): return True if all numbers in [left, right) are in the set

The key challenge is maintaining disjoint, sorted intervals efficiently.

Approach: use a sorted list of intervals. For each operation:
- addRange: find overlapping intervals, merge them with the new range
- removeRange: find overlapping intervals, split/trim them
- queryRange: check if the range is entirely contained in a single interval

Using bisect for binary search on interval endpoints gives O(log n + k) per operation where k is the number of affected intervals. Since intervals are merged/split, the total number stays manageable.

For better worst-case performance, we could use a balanced BST or segment tree, but sorted list with bisect is practical and clean.
</think>

## Range Module

### Implementation

```python
import bisect


class RangeModule:
    """Tracks ranges of numbers. Supports add, remove, and query."""

    def __init__(self):
        # Store as flat list: [s1, e1, s2, e2, ...]
        # Intervals are disjoint and sorted: s1 < e1 <= s2 < e2 ...
        self.intervals = []

    def addRange(self, left, right):
        """Add [left, right) to the tracked set."""
        # Find where left and right fall
        i = bisect.bisect_left(self.intervals, left)
        j = bisect.bisect_right(self.intervals, right)

        # Merge: new interval absorbs all overlapping ones
        if i % 2 == 0:
            # left is outside an interval, keep it
            new_left = left
        else:
            # left is inside an interval, extend to its start
            new_left = self.intervals[i - 1]
            i -= 1

        if j % 2 == 0:
            new_right = right
        else:
            new_right = self.intervals[j]
            j += 1

        self.intervals[i:j] = [new_left, new_right]

    def removeRange(self, left, right):
        """Remove [left, right) from the tracked set."""
        i = bisect.bisect_left(self.intervals, left)
        j = bisect.bisect_right(self.intervals, right)

        new_segments = []
        if i % 2 == 1:
            # left is inside an interval, keep the part before left
            new_segments.append(self.intervals[i - 1])
            new_segments.append(left)
            i -= 1

        if j % 2 == 1:
            # right is inside an interval, keep the part after right
            new_segments.append(right)
            new_segments.append(self.intervals[j])
            j += 1

        self.intervals[i:j] = new_segments

    def queryRange(self, left, right):
        """Check if all numbers in [left, right) are tracked."""
        i = bisect.bisect_right(self.intervals, left)
        j = bisect.bisect_left(self.intervals, right)
        # Both left and right must be inside the same interval
        # i must be odd (left is inside an interval)
        # j must equal i (right is in or at the boundary of the same interval)
        return i == j and i % 2 == 1

    def get_intervals(self):
        """Return list of tracked intervals as [(s1,e1), (s2,e2), ...]."""
        result = []
        for i in range(0, len(self.intervals), 2):
            result.append((self.intervals[i], self.intervals[i + 1]))
        return result


# Demo
print("=== Range Module ===")
rm = RangeModule()

print("Operations:")
rm.addRange(10, 20)
print(f"  addRange(10, 20) -> {rm.get_intervals()}")

rm.addRange(25, 30)
print(f"  addRange(25, 30) -> {rm.get_intervals()}")

rm.addRange(18, 27)
print(f"  addRange(18, 27) -> {rm.get_intervals()}")  # merges to [10,30)

print(f"\n  queryRange(12, 15) = {rm.queryRange(12, 15)}")  # True
print(f"  queryRange(10, 30) = {rm.queryRange(10, 30)}")   # True
print(f"  queryRange(5, 15)  = {rm.queryRange(5, 15)}")    # False

rm.removeRange(14, 16)
print(f"\n  removeRange(14, 16) -> {rm.get_intervals()}")  # [10,14), [16,30)

print(f"  queryRange(10, 14) = {rm.queryRange(10, 14)}")   # True
print(f"  queryRange(13, 17) = {rm.queryRange(13, 17)}")   # False
print(f"  queryRange(16, 25) = {rm.queryRange(16, 25)}")   # True

rm.addRange(5, 8)
print(f"\n  addRange(5, 8) -> {rm.get_intervals()}")

rm.removeRange(0, 100)
print(f"  removeRange(0, 100) -> {rm.get_intervals()}")    # empty

# Stress test
import random
import time
random.seed(42)

rm2 = RangeModule()
start = time.time()
for _ in range(50000):
    op = random.choice(['add', 'remove', 'query'])
    left = random.randint(0, 10000)
    right = left + random.randint(1, 100)
    if op == 'add':
        rm2.addRange(left, right)
    elif op == 'remove':
        rm2.removeRange(left, right)
    else:
        rm2.queryRange(left, right)
elapsed = time.time() - start
print(f"\n50k random operations: {elapsed:.3f}s")
print(f"Final intervals: {len(rm2.get_intervals())}")
```

### Complexity
- **addRange**: O(log n + k) where k = number of overlapping intervals
- **removeRange**: O(log n + k)
- **queryRange**: O(log n)
- **Space**: O(n) where n = number of disjoint intervals
- **Amortized**: O(log n) per operation since intervals merge/split'''),

    ("thinking/algorithms", r'''Design and implement a Snapshot Array. Support set(index, val), snap(), and get(index, snap_id) operations. snap() saves the current state and returns the snap_id.''', r'''<think>
A snapshot array needs to support:
1. set(index, val): set value at index
2. snap(): take a snapshot, return snap_id (incrementing)
3. get(index, snap_id): get value at index at the time of snap_id

Naive approach: copy the entire array at each snap() -- O(n) per snap, O(1) per get. Too slow if array is large.

Better approach: for each index, store a list of (snap_id, value) pairs. Only store when the value changes (or when set is called).

For get(index, snap_id): binary search in the list for index to find the latest entry with snap_id <= given snap_id.

For set(index, val): append (current_snap_id, val) to the list for index. If the last entry has the same snap_id, just update it.

For snap(): increment snap_id counter and return it.

This gives O(1) for set and snap, O(log n) for get where n is the number of sets at that index.

Space: O(number of set operations) total, much better than copying the whole array.
</think>

## Snapshot Array

### Implementation

```python
import bisect


class SnapshotArray:
    """Array with snapshot capability.
    O(1) set, O(1) snap, O(log s) get where s = snaps for that index."""

    def __init__(self, length):
        self.length = length
        # For each index, store list of (snap_id, value)
        self.history = [[(0, 0)] for _ in range(length)]
        self.snap_id = 0

    def set(self, index, val):
        """Set value at index. O(1)."""
        if self.history[index][-1][0] == self.snap_id:
            # Update existing entry for current snap
            self.history[index][-1] = (self.snap_id, val)
        else:
            self.history[index].append((self.snap_id, val))

    def snap(self):
        """Take a snapshot. Returns snap_id. O(1)."""
        result = self.snap_id
        self.snap_id += 1
        return result

    def get(self, index, snap_id):
        """Get value at index at given snap_id. O(log s)."""
        entries = self.history[index]
        # Binary search for latest entry with snap <= snap_id
        # entries are sorted by snap_id
        idx = bisect.bisect_right(entries, (snap_id, float('inf'))) - 1
        if idx < 0:
            return 0
        return entries[idx][1]

    def current(self, index):
        """Get current value at index."""
        return self.history[index][-1][1]

    def memory_usage(self):
        """Total entries stored."""
        return sum(len(h) for h in self.history)


# Demo
print("=== Snapshot Array ===")
sa = SnapshotArray(5)

# Set some values
sa.set(0, 10)
sa.set(1, 20)
sa.set(2, 30)
snap0 = sa.snap()  # snap 0: [10, 20, 30, 0, 0]
print(f"snap() = {snap0}")

sa.set(0, 15)
sa.set(1, 25)
snap1 = sa.snap()  # snap 1: [15, 25, 30, 0, 0]
print(f"snap() = {snap1}")

sa.set(0, 100)
sa.set(3, 50)
snap2 = sa.snap()  # snap 2: [100, 25, 30, 50, 0]
print(f"snap() = {snap2}")

# Queries
print(f"\nQueries:")
for idx in range(5):
    for sid in range(3):
        val = sa.get(idx, sid)
        print(f"  get({idx}, snap={sid}) = {val}")

# Verify
expected = [
    # snap 0    snap 1     snap 2
    [10, 15, 100],  # index 0
    [20, 25, 25],   # index 1
    [30, 30, 30],   # index 2
    [0, 0, 50],     # index 3
    [0, 0, 0],      # index 4
]
print(f"\nVerification:")
all_correct = True
for idx in range(5):
    for sid in range(3):
        actual = sa.get(idx, sid)
        exp = expected[idx][sid]
        if actual != exp:
            print(f"  MISMATCH: get({idx}, {sid}) = {actual}, expected {exp}")
            all_correct = False
print(f"  All correct: {all_correct}")

print(f"\nMemory: {sa.memory_usage()} entries (vs {5 * 3} = 15 for full copies)")

# Stress test
import random
import time
random.seed(42)

sa2 = SnapshotArray(1000)
start = time.time()
for _ in range(100000):
    op = random.choice(['set', 'snap', 'get'])
    if op == 'set':
        sa2.set(random.randint(0, 999), random.randint(0, 10000))
    elif op == 'snap':
        sa2.snap()
    else:
        sa2.get(random.randint(0, 999), random.randint(0, max(sa2.snap_id - 1, 0)))
elapsed = time.time() - start
print(f"\n100k mixed operations: {elapsed:.3f}s")
print(f"Snaps taken: {sa2.snap_id}")
print(f"Memory entries: {sa2.memory_usage()}")
```

### Complexity
- **set**: O(1)
- **snap**: O(1)
- **get**: O(log s) where s = number of sets at that index
- **Space**: O(total sets) instead of O(length * snaps)

### Trade-off
Full copy: O(length) snap, O(1) get
This approach: O(1) snap, O(log s) get -- much better when array is large and sets are sparse'''),

    ("thinking/algorithms", r'''Design and implement a Max Stack that supports push, pop, top, peekMax, and popMax operations, all in O(log n) time. Handle the challenge of removing the maximum element from the middle.''', r'''<think>
A Max Stack needs these operations:
1. push(x): push x onto the stack
2. pop(): remove and return top element
3. top(): return top element
4. peekMax(): return the maximum element
5. popMax(): remove and return the maximum element (the topmost one if ties)

The challenge is popMax: we need to remove an element from the middle of the stack efficiently.

Approach using a doubly-linked list + sorted container:
1. Doubly-linked list: represents the stack (head = bottom, tail = top)
2. A sorted structure (e.g., sorted list or balanced BST) mapping values to their nodes in the linked list

For push: add node to tail of linked list, add to sorted structure. O(log n).
For pop: remove tail node, remove from sorted structure. O(log n).
For top: return tail value. O(1).
For peekMax: return the max value from sorted structure. O(log n) or O(1).
For popMax: find the max from sorted structure, get the corresponding node (the last one added if ties), remove it from the linked list and sorted structure. O(log n).

In Python, we can use a SortedList from sortedcontainers, or implement using a heap with lazy deletion.

Let me implement using a heap with lazy deletion for peekMax/popMax, combined with a doubly-linked list for order.

Actually, for a cleaner approach: use a doubly linked list for the stack, and a TreeMap (sorted dict) mapping values to a list of nodes with that value. This gives O(log n) for all operations.

Since Python lacks a built-in sorted dict, I will use a simple sorted list approach with bisect.
</think>

## Max Stack Implementation

### O(log n) All Operations

```python
import bisect


class MaxStack:
    """Stack supporting push, pop, top, peekMax, popMax in O(log n)."""

    class Node:
        __slots__ = ('val', 'prev', 'next', 'removed')
        def __init__(self, val):
            self.val = val
            self.prev = None
            self.next = None
            self.removed = False

    def __init__(self):
        # Doubly linked list with sentinel nodes
        self.head = self.Node(0)
        self.tail = self.Node(0)
        self.head.next = self.tail
        self.tail.prev = self.head

        # Sorted list of (value, unique_id) for max queries
        # unique_id ensures LIFO order for ties
        self.sorted_vals = []  # sorted list of (-val, -uid, node)
        self.uid = 0
        self.size = 0

    def push(self, x):
        """Push x onto the stack. O(log n)."""
        node = self.Node(x)

        # Add to tail of linked list (top of stack)
        node.prev = self.tail.prev
        node.next = self.tail
        self.tail.prev.next = node
        self.tail.prev = node

        # Add to sorted list (negate for max behavior with bisect)
        self.uid += 1
        entry = (-x, -self.uid, node)
        bisect.insort(self.sorted_vals, entry)
        self.size += 1

    def pop(self):
        """Remove and return top element. O(log n)."""
        if self.size == 0:
            raise IndexError("pop from empty stack")

        node = self.tail.prev
        val = node.val
        self._remove_node(node)
        return val

    def top(self):
        """Return top element. O(1)."""
        if self.size == 0:
            raise IndexError("top from empty stack")
        return self.tail.prev.val

    def peekMax(self):
        """Return maximum element. O(log n) amortized with lazy deletion."""
        self._clean_sorted()
        if not self.sorted_vals:
            raise IndexError("peekMax from empty stack")
        return -self.sorted_vals[0][0]

    def popMax(self):
        """Remove and return maximum element. O(log n)."""
        self._clean_sorted()
        if not self.sorted_vals:
            raise IndexError("popMax from empty stack")

        neg_val, neg_uid, node = self.sorted_vals.pop(0)
        val = -neg_val
        # Remove from linked list
        node.prev.next = node.next
        node.next.prev = node.prev
        node.removed = True
        self.size -= 1
        return val

    def _remove_node(self, node):
        """Remove node from linked list and mark as removed."""
        node.prev.next = node.next
        node.next.prev = node.prev
        node.removed = True
        self.size -= 1
        # Lazy: do not remove from sorted_vals immediately

    def _clean_sorted(self):
        """Remove invalidated entries from sorted list."""
        while self.sorted_vals and self.sorted_vals[0][2].removed:
            self.sorted_vals.pop(0)

    def __len__(self):
        return self.size


# Demo
print("=== Max Stack ===")
ms = MaxStack()

ops = [
    ("push", 5), ("push", 1), ("push", 5),
    ("top", None), ("popMax", None), ("top", None),
    ("peekMax", None), ("pop", None), ("top", None),
]

for op, val in ops:
    if op == "push":
        ms.push(val)
        print(f"  push({val})")
    elif op == "pop":
        result = ms.pop()
        print(f"  pop() = {result}")
    elif op == "top":
        result = ms.top()
        print(f"  top() = {result}")
    elif op == "peekMax":
        result = ms.peekMax()
        print(f"  peekMax() = {result}")
    elif op == "popMax":
        result = ms.popMax()
        print(f"  popMax() = {result}")

# More complex example
print(f"\n=== Complex Example ===")
ms2 = MaxStack()
for v in [3, 1, 4, 1, 5, 9, 2, 6]:
    ms2.push(v)
print(f"Pushed: [3, 1, 4, 1, 5, 9, 2, 6]")

print(f"peekMax() = {ms2.peekMax()}")  # 9
print(f"popMax() = {ms2.popMax()}")     # 9
print(f"peekMax() = {ms2.peekMax()}")  # 6
print(f"top() = {ms2.top()}")           # 6
print(f"pop() = {ms2.pop()}")           # 6
print(f"peekMax() = {ms2.peekMax()}")  # 5

# Performance
import time
import random
random.seed(42)

ms3 = MaxStack()
start = time.time()
for _ in range(50000):
    op = random.choice(['push', 'push', 'push', 'pop', 'peekMax', 'popMax'])
    if op == 'push':
        ms3.push(random.randint(0, 10000))
    elif len(ms3) > 0:
        if op == 'pop':
            ms3.pop()
        elif op == 'peekMax':
            ms3.peekMax()
        elif op == 'popMax':
            ms3.popMax()
elapsed = time.time() - start
print(f"\n50k operations: {elapsed:.3f}s")
```

### Complexity
- **push**: O(log n) -- sorted list insertion
- **pop**: O(1) amortized (lazy cleanup)
- **top**: O(1)
- **peekMax**: O(1) amortized (with lazy cleanup)
- **popMax**: O(log n) -- sorted list removal
- **Space**: O(n)'''),
]
