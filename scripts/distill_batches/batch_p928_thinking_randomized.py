PAIRS = [
    ("thinking/algorithms", r'''Implement the Quickselect algorithm: find the kth smallest element in an unsorted array in expected O(n) time. Discuss the randomized pivot selection and worst-case analysis.''', r'''<think>
Quickselect (also called Hoare's selection algorithm) is a randomized algorithm to find the kth smallest element. It is related to quicksort but only recurses into one partition, giving expected O(n) time instead of O(n log n).

Algorithm:
1. Pick a random pivot
2. Partition the array around the pivot
3. If the pivot is at position k, return it
4. If k < pivot position, recurse on the left partition
5. If k > pivot position, recurse on the right partition

Why expected O(n):
- With a random pivot, the expected partition splits the array roughly in half
- T(n) = T(n/2) + O(n) = O(n) on average
- Each level of recursion does O(n) work but on a shrinking subproblem

Worst case: O(n^2) if we always pick the worst pivot (like always picking min or max). This happens with probability that decreases exponentially, so it is extremely unlikely with random pivots.

Median-of-medians gives guaranteed O(n) worst case but has a large constant factor and is rarely used in practice.

For the partition scheme, I will use Lomuto's partition (simpler) and also show the Hoare partition.

Edge cases:
- k = 0 (minimum element)
- k = n-1 (maximum element)
- All elements equal
- Array of size 1
- Duplicates

I will implement both the randomized version and the iterative version.
</think>

**Quickselect -- Randomized Selection**

```python
import random


def quickselect(arr, k):
    """
    Find the kth smallest element (0-indexed).

    Args:
        arr: list of comparable elements
        k: index of desired order statistic (0-indexed)
    Returns:
        kth smallest element
    """
    if len(arr) == 1:
        return arr[0]

    arr = arr[:]  # avoid modifying original
    return _quickselect(arr, 0, len(arr) - 1, k)


def _quickselect(arr, lo, hi, k):
    while lo < hi:
        pivot_idx = _partition(arr, lo, hi)

        if pivot_idx == k:
            return arr[k]
        elif k < pivot_idx:
            hi = pivot_idx - 1
        else:
            lo = pivot_idx + 1

    return arr[lo]


def _partition(arr, lo, hi):
    """Lomuto partition with random pivot."""
    # Random pivot selection
    pivot_idx = random.randint(lo, hi)
    arr[pivot_idx], arr[hi] = arr[hi], arr[pivot_idx]
    pivot = arr[hi]

    i = lo
    for j in range(lo, hi):
        if arr[j] <= pivot:
            arr[i], arr[j] = arr[j], arr[i]
            i += 1

    arr[i], arr[hi] = arr[hi], arr[i]
    return i


def quickselect_3way(arr, k):
    """Three-way partition variant (handles duplicates better)."""
    arr = arr[:]
    lo, hi = 0, len(arr) - 1

    while lo < hi:
        pivot = arr[random.randint(lo, hi)]
        # Three-way partition: [< pivot | == pivot | > pivot]
        lt, gt = lo, hi
        i = lo

        while i <= gt:
            if arr[i] < pivot:
                arr[lt], arr[i] = arr[i], arr[lt]
                lt += 1
                i += 1
            elif arr[i] > pivot:
                arr[gt], arr[i] = arr[i], arr[gt]
                gt -= 1
            else:
                i += 1

        # Elements equal to pivot are in arr[lt..gt]
        if k < lt:
            hi = lt - 1
        elif k > gt:
            lo = gt + 1
        else:
            return arr[k]

    return arr[lo]


# Test
random.seed(42)
arr = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5]
sorted_arr = sorted(arr)

print(f"Array: {arr}")
print(f"Sorted: {sorted_arr}")

for k in range(len(arr)):
    result = quickselect(arr, k)
    result2 = quickselect_3way(arr, k)
    expected = sorted_arr[k]
    status = "PASS" if result == expected == result2 else "FAIL"
    print(f"  [{status}] k={k}: qs={result}, 3way={result2}, expected={expected}")

# Median finding
n = len(arr)
median = quickselect(arr, n // 2)
print(f"\nMedian: {median}")

# Performance test
large = [random.randint(0, 1000000) for _ in range(100000)]
k = len(large) // 2
result = quickselect(large, k)
expected = sorted(large)[k]
print(f"Large array median: {result == expected}")
```

**Expected Time Analysis:**
- Good pivot (rank in middle half): probability 1/2
- Expected levels until good pivot: 2
- After good pivot, subproblem shrinks by at least 1/4
- T(n) <= T(3n/4) + O(n) = O(n)

**Complexity:**
- Expected time: O(n)
- Worst case: O(n^2) -- vanishingly unlikely with random pivots
- Guaranteed O(n): use median-of-medians (Blum et al., 1973)
- Space: O(1) iterative, O(log n) expected recursive'''),

    ("thinking/algorithms", r'''Implement a Treap (tree + heap): a randomized binary search tree where each node has a key (BST property) and a random priority (heap property). Show that it maintains expected O(log n) height.''', r'''<think>
A Treap is a randomized BST that combines:
- BST property on keys: left < root < right
- Max-heap property on priorities: parent priority >= child priority

Each node is assigned a random priority on insertion. The heap property on random priorities ensures the tree is equivalent to a random BST, which has expected O(log n) height.

Why it works: A treap built by inserting keys with random priorities is distributionally equivalent to a BST built by inserting the same keys in a random order. Random BSTs have expected height O(log n).

Operations:
1. Split(T, key): Split tree T into two trees L and R where all keys in L <= key and all keys in R > key. O(log n) expected.
2. Merge(L, R): Merge two trees where all keys in L < all keys in R. Compare priorities to decide which root to keep. O(log n) expected.

Using split and merge:
- Insert(key): Split at key, create new node, merge(L, new_node, R)
- Delete(key): Split at key-1 and key, discard the middle, merge(L, R)
- Search: Standard BST search

Alternatively, insert/delete can use rotations to maintain heap property, similar to AVL rotations but triggered by priority violations.

I will implement the split/merge approach as it is cleaner and more composable.
</think>

**Treap -- Randomized BST with Split/Merge**

```python
import random


class TreapNode:
    def __init__(self, key, priority=None):
        self.key = key
        self.priority = priority if priority is not None else random.random()
        self.left = None
        self.right = None
        self.size = 1  # subtree size for order statistics

    def update(self):
        self.size = 1
        if self.left:
            self.size += self.left.size
        if self.right:
            self.size += self.right.size


class Treap:
    """Treap (randomized BST) with split/merge operations."""

    def __init__(self):
        self.root = None

    def _split(self, node, key):
        """Split tree into (left <= key, right > key)."""
        if node is None:
            return None, None

        if node.key <= key:
            left, right = self._split(node.right, key)
            node.right = left
            node.update()
            return node, right
        else:
            left, right = self._split(node.left, key)
            node.left = right
            node.update()
            return left, node

    def _merge(self, left, right):
        """Merge two treaps. All keys in left < all keys in right."""
        if left is None:
            return right
        if right is None:
            return left

        if left.priority > right.priority:
            left.right = self._merge(left.right, right)
            left.update()
            return left
        else:
            right.left = self._merge(left, right.left)
            right.update()
            return right

    def insert(self, key):
        """Insert key into treap."""
        new_node = TreapNode(key)
        left, right = self._split(self.root, key - 0.5)
        self.root = self._merge(self._merge(left, new_node), right)

    def delete(self, key):
        """Delete one occurrence of key from treap."""
        left, mid_right = self._split(self.root, key - 0.5)
        mid, right = self._split(mid_right, key)
        # mid contains all nodes with this key; remove one
        if mid is not None:
            mid = self._merge(mid.left, mid.right)
        self.root = self._merge(self._merge(left, mid), right)

    def search(self, key):
        """Check if key exists in treap."""
        node = self.root
        while node:
            if key == node.key:
                return True
            elif key < node.key:
                node = node.left
            else:
                node = node.right
        return False

    def kth(self, k):
        """Find kth smallest element (1-indexed)."""
        node = self.root
        while node:
            left_size = node.left.size if node.left else 0
            if k <= left_size:
                node = node.left
            elif k == left_size + 1:
                return node.key
            else:
                k -= left_size + 1
                node = node.right
        return None

    def height(self):
        """Compute tree height."""
        def _height(node):
            if node is None:
                return 0
            return 1 + max(_height(node.left), _height(node.right))
        return _height(self.root)

    def inorder(self):
        """Return sorted list of keys."""
        result = []
        def _inorder(node):
            if node:
                _inorder(node.left)
                result.append(node.key)
                _inorder(node.right)
        _inorder(self.root)
        return result


# Demo
random.seed(42)
treap = Treap()

keys = [5, 3, 7, 1, 4, 6, 8, 2, 9, 0]
for k in keys:
    treap.insert(k)

print(f"Inserted: {keys}")
print(f"In-order: {treap.inorder()}")
print(f"Height: {treap.height()}")
print(f"Size: {treap.root.size if treap.root else 0}")

# Search
for k in [3, 10, 7]:
    print(f"  Search {k}: {treap.search(k)}")

# Kth smallest
for k in range(1, 11):
    print(f"  {k}th smallest: {treap.kth(k)}")

# Delete
treap.delete(5)
treap.delete(0)
print(f"\nAfter deleting 5 and 0:")
print(f"In-order: {treap.inorder()}")

# Height analysis
heights = []
for _ in range(100):
    t = Treap()
    for i in range(1000):
        t.insert(i)
    heights.append(t.height())
avg_h = sum(heights) / len(heights)
print(f"\nHeight of 1000-node treaps (100 trials):")
print(f"  Average: {avg_h:.1f}, Expected O(log 1000) ~ {10:.1f}")
```

**Key Properties:**
- Expected height: O(log n)
- Split/Merge: O(log n) expected
- Insert/Delete/Search: O(log n) expected
- Order statistics (kth): O(log n)

**Complexity:**
- All operations: O(log n) expected
- Space: O(n)'''),

    ("thinking/algorithms", r'''Implement a Skip List: a randomized data structure that provides expected O(log n) search, insertion, and deletion. Explain the probabilistic balancing mechanism.''', r'''<think>
A skip list is a layered linked list where higher levels skip over elements, allowing binary-search-like behavior on a linked list.

Structure:
- Level 0: a sorted linked list of all elements
- Level 1: a subset of level 0 elements (each element promoted with probability 1/2)
- Level 2: a subset of level 1 elements
- ...
- Each node exists at consecutive levels from 0 up to its randomly determined height

Insertion:
1. Find the position (using search from top level down)
2. Determine the height of the new node (flip coins: keep going while heads)
3. Insert at all levels up to its height, linking to neighbors

Search:
1. Start at the top-left (highest level, head sentinel)
2. At each level, move right while the next key is less than target
3. Drop down one level and repeat
4. At level 0, we are either at the target or know it is not present

Expected search time: O(log n) -- we skip roughly half the remaining elements at each level.

Why O(log n): The expected number of levels is O(log n). At each level, we make O(1) expected comparisons before dropping down. Total: O(log n) expected comparisons.

The skip list is an elegant alternative to balanced BSTs. It is easier to implement, especially for concurrent access (lock-free skip lists are simpler than lock-free trees).

Memory: Each element has an expected 2 pointers (geometric sum: 1 + 1/2 + 1/4 + ... = 2).
</think>

**Skip List Implementation**

```python
import random


class SkipNode:
    def __init__(self, key, level):
        self.key = key
        self.forward = [None] * (level + 1)


class SkipList:
    """Skip list with expected O(log n) operations."""

    MAX_LEVEL = 20
    P = 0.5  # probability of promotion

    def __init__(self):
        self.header = SkipNode(float('-inf'), self.MAX_LEVEL)
        self.level = 0  # current max level in use
        self.size = 0

    def _random_level(self):
        """Generate random level for new node."""
        lvl = 0
        while random.random() < self.P and lvl < self.MAX_LEVEL:
            lvl += 1
        return lvl

    def search(self, key):
        """Search for key. Returns True if found."""
        current = self.header
        for i in range(self.level, -1, -1):
            while (current.forward[i] is not None and
                   current.forward[i].key < key):
                current = current.forward[i]
        current = current.forward[0]
        return current is not None and current.key == key

    def insert(self, key):
        """Insert key into skip list."""
        update = [None] * (self.MAX_LEVEL + 1)
        current = self.header

        for i in range(self.level, -1, -1):
            while (current.forward[i] is not None and
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current

        current = current.forward[0]

        # Allow duplicates or update existing
        new_level = self._random_level()

        if new_level > self.level:
            for i in range(self.level + 1, new_level + 1):
                update[i] = self.header
            self.level = new_level

        new_node = SkipNode(key, new_level)
        for i in range(new_level + 1):
            new_node.forward[i] = update[i].forward[i]
            update[i].forward[i] = new_node

        self.size += 1

    def delete(self, key):
        """Delete key from skip list. Returns True if found and deleted."""
        update = [None] * (self.MAX_LEVEL + 1)
        current = self.header

        for i in range(self.level, -1, -1):
            while (current.forward[i] is not None and
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current

        current = current.forward[0]

        if current is not None and current.key == key:
            for i in range(self.level + 1):
                if update[i].forward[i] != current:
                    break
                update[i].forward[i] = current.forward[i]

            while self.level > 0 and self.header.forward[self.level] is None:
                self.level -= 1

            self.size -= 1
            return True

        return False

    def display(self):
        """Visualize the skip list."""
        for i in range(self.level, -1, -1):
            node = self.header.forward[i]
            keys = []
            while node:
                keys.append(str(node.key))
                node = node.forward[i]
            print(f"  Level {i}: {' -> '.join(keys)}")


# Demo
random.seed(42)
sl = SkipList()

keys = [3, 6, 7, 9, 12, 19, 17, 26, 21, 25]
for k in keys:
    sl.insert(k)

print(f"Inserted: {keys}")
print(f"Skip list structure:")
sl.display()
print(f"Size: {sl.size}")

# Search
for k in [7, 15, 21]:
    print(f"  Search {k}: {sl.search(k)}")

# Delete
sl.delete(19)
sl.delete(7)
print(f"\nAfter deleting 19 and 7:")
sl.display()

# Performance test
sl2 = SkipList()
n = 10000
for i in range(n):
    sl2.insert(random.randint(0, 100000))
print(f"\n{n} elements inserted")
print(f"Max level: {sl2.level}")
print(f"Expected max level: ~{int(14)}")  # log2(10000) ~ 13.3
```

**Why O(log n) Expected:**
- Expected number of levels: O(log n) (geometric distribution)
- At each level, expected O(1) comparisons before dropping down
- Total comparisons: O(log n)

**Comparison with Balanced BSTs:**
- Simpler implementation (no rotations)
- Natural support for concurrent access
- Slightly higher constant factors
- Same O(log n) expected complexity

**Complexity:**
- Search, Insert, Delete: O(log n) expected
- Space: O(n) expected (each node has ~2 pointers on average)'''),

    ("thinking/algorithms", r'''Implement Reservoir Sampling: given a stream of elements of unknown length, select k items uniformly at random from the stream using O(k) memory. Prove the correctness of the sampling probabilities.''', r'''<think>
Reservoir Sampling (Algorithm R by Vitter, 1985) solves the problem of selecting k items uniformly at random from a stream of unknown length, using only O(k) space.

Algorithm:
1. Fill the reservoir with the first k items
2. For each subsequent item i (index k, k+1, ...):
   a. Generate random number j in [0, i]
   b. If j < k, replace reservoir[j] with the new item
3. When the stream ends, the reservoir contains k items sampled uniformly

Why this is correct (proof by induction):
- After seeing n items, each item should be in the reservoir with probability k/n.
- Base case: After k items, all are in the reservoir. P = k/k = 1. Correct.
- Inductive step: Assume after n items, each is in reservoir with P = k/n.
  - Item n+1: selected with probability k/(n+1). Correct.
  - Previous item: Was in reservoir with P = k/n. Survives if item n+1 does NOT replace it.
    - P(not replaced) = P(n+1 not selected) + P(n+1 selected but replaces a different slot)
    - = (n+1-k)/(n+1) + (k/(n+1)) * ((k-1)/k)
    - = (n+1-k)/(n+1) + (k-1)/(n+1)
    - = (n+1-k+k-1)/(n+1) = n/(n+1)
  - P(previous item in reservoir) = (k/n) * (n/(n+1)) = k/(n+1). Correct.

By induction, all items have equal probability k/n of being in the reservoir.

For k=1: simplifies to keeping the ith item with probability 1/i.
</think>

**Reservoir Sampling**

```python
import random
from collections import Counter


def reservoir_sample(stream, k):
    """
    Select k items uniformly at random from a stream.

    Args:
        stream: iterable of items
        k: number of items to sample
    Returns:
        list of k sampled items
    """
    reservoir = []
    iterator = iter(stream)

    # Fill reservoir with first k items
    for i in range(k):
        try:
            reservoir.append(next(iterator))
        except StopIteration:
            return reservoir  # Stream shorter than k

    # Process remaining items
    i = k
    for item in iterator:
        j = random.randint(0, i)
        if j < k:
            reservoir[j] = item
        i += 1

    return reservoir


def weighted_reservoir_sample(stream, k):
    """
    Reservoir sampling with weights.
    Each item is (element, weight). Higher weight = more likely to be sampled.
    Uses Efraimidis-Spirakis algorithm.
    """
    import heapq

    reservoir = []  # min-heap of (key, element)

    for item, weight in stream:
        if weight <= 0:
            continue
        # Generate key = random^(1/weight)
        key = random.random() ** (1.0 / weight)

        if len(reservoir) < k:
            heapq.heappush(reservoir, (key, item))
        elif key > reservoir[0][0]:
            heapq.heapreplace(reservoir, (key, item))

    return [item for _, item in reservoir]


# Demo: sample from a large stream
random.seed(42)
stream = range(1000)
sample = reservoir_sample(stream, 10)
print(f"Reservoir sample (k=10) from 0..999:")
print(f"  {sample}")

# Verify uniformity with many trials
n = 100
k = 5
trials = 100000
counts = Counter()

for _ in range(trials):
    s = reservoir_sample(range(n), k)
    for item in s:
        counts[item] += 1

# Each item should appear with frequency k/n * trials = 5000
expected = k * trials / n
print(f"\nUniformity test: n={n}, k={k}, trials={trials}")
print(f"Expected frequency per item: {expected:.0f}")

min_freq = min(counts.values())
max_freq = max(counts.values())
print(f"Actual: min={min_freq}, max={max_freq}")

# Chi-squared test approximation
chi_sq = sum((counts[i] - expected)**2 / expected for i in range(n))
print(f"Chi-squared statistic: {chi_sq:.1f} (expected ~{n-1})")
uniform = abs(chi_sq - (n-1)) < 3 * (2*(n-1))**0.5
print(f"Approximately uniform: {uniform}")

# Single-item reservoir sampling (k=1)
print(f"\nSingle item sampling from stream of 1M items:")
single_counts = Counter()
for _ in range(10000):
    result = reservoir_sample(range(10), 1)
    single_counts[result[0]] += 1
print(f"Frequencies: {dict(sorted(single_counts.items()))}")
```

**Correctness Proof (Induction):**
```
After n items, P(item i in reservoir) = k/n for all i.

For item n+1:
  P(selected) = k/(n+1)  -- correct

For previous item (already in reservoir):
  P(survives) = P(n+1 not selected) + P(n+1 selected, different slot)
              = (n+1-k)/(n+1) + (k/(n+1))*(k-1)/k
              = n/(n+1)
  P(in reservoir) = (k/n) * (n/(n+1)) = k/(n+1)  -- correct
```

**Complexity:**
- Time: O(n) single pass through stream
- Space: O(k) for the reservoir
- No need to know stream length in advance'''),

    ("thinking/algorithms", r'''Implement a Bloom Filter: a space-efficient probabilistic data structure that supports membership testing with no false negatives and a controllable false positive rate. Show how to choose optimal parameters.''', r'''<think>
A Bloom filter is a probabilistic set data structure that can tell you:
- "Definitely not in the set" (no false negatives)
- "Probably in the set" (possible false positives)

Structure:
- Bit array of m bits, initialized to all 0
- k independent hash functions, each mapping elements to positions [0, m-1]

Insert(x):
- Compute k hash positions: h1(x), h2(x), ..., hk(x)
- Set all these bits to 1

Query(x):
- Compute k hash positions
- If ALL corresponding bits are 1, return "possibly in set"
- If ANY bit is 0, return "definitely not in set"

False positive probability:
- After inserting n elements with m bits and k hash functions:
  p_fp = (1 - e^(-kn/m))^k

Optimal k: k = (m/n) * ln(2) ~ 0.693 * (m/n)

For a desired false positive rate p:
- m = -n * ln(p) / (ln(2))^2
- k = -ln(p) / ln(2) = log2(1/p)

In practice, we use double hashing to simulate k hash functions:
hi(x) = h1(x) + i * h2(x)

This avoids needing k independent hash functions while preserving theoretical guarantees.

I should implement:
1. The Bloom filter with configurable parameters
2. Automatic parameter selection given n and desired false positive rate
3. Demonstration with real data
</think>

**Bloom Filter Implementation**

```python
import math
import hashlib


class BloomFilter:
    """
    Bloom filter for probabilistic membership testing.

    No false negatives. False positive rate controlled by parameters.
    """

    def __init__(self, expected_items, fp_rate=0.01):
        """
        Args:
            expected_items: expected number of items to insert
            fp_rate: desired false positive rate
        """
        self.n = expected_items
        self.fp_rate = fp_rate

        # Calculate optimal parameters
        self.m = self._optimal_size(expected_items, fp_rate)
        self.k = self._optimal_hash_count(self.m, expected_items)

        self.bits = [False] * self.m
        self.count = 0

    @staticmethod
    def _optimal_size(n, p):
        """Calculate optimal bit array size."""
        m = -n * math.log(p) / (math.log(2) ** 2)
        return int(math.ceil(m))

    @staticmethod
    def _optimal_hash_count(m, n):
        """Calculate optimal number of hash functions."""
        k = (m / n) * math.log(2)
        return max(1, int(round(k)))

    def _hashes(self, item):
        """Generate k hash positions using double hashing."""
        item_bytes = str(item).encode('utf-8')
        h1 = int(hashlib.md5(item_bytes).hexdigest(), 16)
        h2 = int(hashlib.sha256(item_bytes).hexdigest(), 16)

        for i in range(self.k):
            yield (h1 + i * h2) % self.m

    def add(self, item):
        """Add item to the Bloom filter."""
        for pos in self._hashes(item):
            self.bits[pos] = True
        self.count += 1

    def contains(self, item):
        """
        Check if item might be in the set.

        Returns:
            True: item is PROBABLY in the set (may be false positive)
            False: item is DEFINITELY NOT in the set
        """
        return all(self.bits[pos] for pos in self._hashes(item))

    def estimated_fp_rate(self):
        """Estimate current false positive rate."""
        bits_set = sum(self.bits)
        if bits_set == 0:
            return 0.0
        return (bits_set / self.m) ** self.k

    def fill_ratio(self):
        """Fraction of bits set to 1."""
        return sum(self.bits) / self.m


# Demo
bf = BloomFilter(expected_items=1000, fp_rate=0.01)
print(f"Bloom Filter Parameters:")
print(f"  Expected items: {bf.n}")
print(f"  Desired FP rate: {bf.fp_rate}")
print(f"  Bit array size: {bf.m} bits ({bf.m/8:.0f} bytes)")
print(f"  Hash functions: {bf.k}")

# Insert items
for i in range(1000):
    bf.add(f"item_{i}")

print(f"\nAfter inserting 1000 items:")
print(f"  Fill ratio: {bf.fill_ratio():.3f}")
print(f"  Estimated FP rate: {bf.estimated_fp_rate():.4f}")

# Test: no false negatives
false_negatives = 0
for i in range(1000):
    if not bf.contains(f"item_{i}"):
        false_negatives += 1
print(f"  False negatives: {false_negatives}")

# Test: measure false positive rate
false_positives = 0
test_count = 10000
for i in range(1000, 1000 + test_count):
    if bf.contains(f"item_{i}"):
        false_positives += 1
actual_fp = false_positives / test_count
print(f"  False positives: {false_positives}/{test_count} = {actual_fp:.4f}")

# Space comparison
set_size = 1000 * 50  # rough estimate: 50 bytes per string in a set
bf_size = bf.m / 8
print(f"\nSpace comparison:")
print(f"  Python set (approx): {set_size:,.0f} bytes")
print(f"  Bloom filter: {bf_size:,.0f} bytes")
print(f"  Savings: {(1 - bf_size/set_size)*100:.0f}%")
```

**Parameter Formulas:**
```
Optimal bit array size:  m = -n * ln(p) / (ln 2)^2
Optimal hash count:      k = (m/n) * ln 2
False positive rate:     p = (1 - e^(-kn/m))^k
```

**Applications:**
- Web browsers: check if a URL is in a malicious site list
- Databases: avoid disk lookups for non-existent keys
- Network routers: packet deduplication
- Distributed systems: set reconciliation

**Complexity:**
- Insert: O(k) hash computations
- Query: O(k) hash computations
- Space: O(m) bits, much less than storing actual elements'''),
]
