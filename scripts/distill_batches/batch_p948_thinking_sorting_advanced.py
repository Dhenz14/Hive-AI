PAIRS = [
    ("thinking/algorithms", r'''Implement counting sort and show its applications: sorting strings by length, sort stability for radix sort, and computing frequency-based rankings. Prove it is O(n + k) where k is the range.''', r'''<think>
Counting sort. This is not comparison-based, so it can break the O(n log n) lower bound. But how?

The idea: count occurrences of each value, then compute positions from cumulative counts. It is O(n + k) where k is the range of values. When k = O(n), this is linear -- something no comparison sort can achieve.

Steps:
1. Count occurrences of each value
2. Compute prefix sums (cumulative counts) -- this tells us where each value's block starts in the output
3. Place elements in output array using the counts

Wait, there is a subtlety in step 3. Should I iterate forwards or backwards? If I iterate forwards, elements with equal keys get placed in the order they appear -- that would be stable, right? Hmm, actually no. The prefix sum gives the END position of each group. If I iterate forwards and decrement, earlier elements get placed at the end of their group. To maintain the original relative order (stability), I need to iterate BACKWARDS. Let me think again...

Actually, the standard approach: prefix sums give the starting position of each group's NEXT slot. Iterating backwards through the input, each element goes to count[key]-1, then we decrement count[key]. This ensures the last occurrence gets the last position within the group, preserving relative order. Yes, iterating backwards is correct for stability.

Why does stability matter? Because radix sort depends on it. Radix sort applies counting sort digit-by-digit from least significant to most significant. If counting sort were not stable, sorting by a higher digit would scramble the ordering established by lower digits.

Applications I should demonstrate:
1. Sort strings by length -- the key is string length, bounded by max length
2. Stability for radix sort -- show that it preserves relative order
3. Frequency-based rankings -- the count array directly gives frequencies, which I can use for ranking

The tradeoff: counting sort is fast when k is small relative to n, but if k >> n (e.g., sorting 100 elements in range [0, 10^9]), it wastes massive memory on a sparse count array. In that case, comparison sort wins.
</think>

## Counting Sort and Applications

### Implementation

```python
def counting_sort(arr, key_func=None, max_val=None):
    """Stable counting sort.

    Args:
        arr: input array
        key_func: function to extract sort key (default: identity)
        max_val: maximum key value (computed if None)

    Returns:
        sorted array (stable)
    """
    if not arr:
        return []

    if key_func is None:
        key_func = lambda x: x

    keys = [key_func(x) for x in arr]
    if max_val is None:
        max_val = max(keys)

    n = len(arr)
    k = max_val + 1

    # Step 1: Count occurrences
    count = [0] * k
    for key in keys:
        count[key] += 1

    # Step 2: Prefix sums (cumulative count)
    for i in range(1, k):
        count[i] += count[i - 1]

    # Step 3: Build output (iterate backwards for stability)
    output = [None] * n
    for i in range(n - 1, -1, -1):
        key = keys[i]
        count[key] -= 1
        output[count[key]] = arr[i]

    return output


# Application 1: Sort strings by length
def sort_strings_by_length(strings):
    """Sort strings by length using counting sort. O(n + max_len)."""
    if not strings:
        return []
    return counting_sort(strings, key_func=len, max_val=max(len(s) for s in strings))


# Application 2: Radix sort using counting sort as subroutine
def radix_sort(arr, max_digits=None):
    """Radix sort for non-negative integers. O(d * (n + b)) where d=digits, b=base."""
    if not arr:
        return []

    base = 10
    if max_digits is None:
        max_val = max(arr)
        max_digits = 1
        while max_val >= base:
            max_val //= base
            max_digits += 1

    result = list(arr)
    for digit in range(max_digits):
        # Extract digit and sort by it using counting sort
        def get_digit(x, d=digit):
            return (x // (base ** d)) % base

        result = counting_sort(result, key_func=get_digit, max_val=base - 1)

    return result


# Application 3: Frequency ranking
def frequency_ranking(arr):
    """Rank elements by frequency (most frequent first).
    Uses counting sort to find frequencies."""
    if not arr:
        return [], {}

    # Count frequencies
    freq = {}
    for x in arr:
        freq[x] = freq.get(x, 0) + 1

    # Sort by frequency (descending) using counting sort
    max_freq = max(freq.values())
    ranked = counting_sort(
        list(freq.keys()),
        key_func=lambda x: max_freq - freq[x],  # negate for descending
        max_val=max_freq
    )

    return ranked, freq


# Demo
print("=== Counting Sort ===")
arr = [4, 2, 2, 8, 3, 3, 1, 7, 5, 4]
sorted_arr = counting_sort(arr)
print(f"Input:  {arr}")
print(f"Sorted: {sorted_arr}")

# Stability demonstration
print(f"\n=== Stability Demo ===")
items = [('A', 2), ('B', 1), ('C', 2), ('D', 1), ('E', 3)]
sorted_items = counting_sort(items, key_func=lambda x: x[1], max_val=3)
print(f"Input:  {items}")
print(f"Sorted: {sorted_items}")
print(f"Stability: A before C in key=2? {sorted_items.index(('A', 2)) < sorted_items.index(('C', 2))}")

# Application 1: Sort strings by length
print(f"\n=== Sort Strings by Length ===")
strings = ["cat", "a", "to", "hello", "be", "ant", "world", "I"]
sorted_strings = sort_strings_by_length(strings)
print(f"Input:  {strings}")
print(f"Sorted: {sorted_strings}")

# Application 2: Radix sort
print(f"\n=== Radix Sort ===")
arr2 = [170, 45, 75, 90, 802, 24, 2, 66]
sorted_arr2 = radix_sort(arr2)
print(f"Input:  {arr2}")
print(f"Sorted: {sorted_arr2}")
assert sorted_arr2 == sorted(arr2)

# Application 3: Frequency ranking
print(f"\n=== Frequency Ranking ===")
data = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9, 3, 2, 3]
ranked, freq = frequency_ranking(data)
print(f"Data: {data}")
print(f"Frequency ranking (most common first):")
for val in ranked:
    print(f"  {val}: {freq[val]} occurrences")

print(f"\n=== Complexity ===")
print(f"  Counting sort: O(n + k) time, O(n + k) space")
print(f"  Radix sort: O(d * (n + b)) time")
print(f"  Both are stable and non-comparison-based")
```

### Complexity Proof
```
Step 1 (Count):        O(n) to scan input
Step 2 (Prefix sums):  O(k) to compute cumulative counts
Step 3 (Place output):  O(n) to build result
Total: O(n + k) time, O(n + k) space
```

Counting sort beats O(n log n) when k = O(n).'''),

    ("thinking/algorithms", r'''Implement radix sort for strings. Show how to sort variable-length strings in O(total_chars) time using MSD (Most Significant Digit) radix sort with recursion.''', r'''<think>
MSD (Most Significant Digit) radix sort for strings. The idea: sort by the first character, then recursively sort each group by the next character.

I initially considered LSD (Least Significant Digit) radix sort, which works right-to-left. But LSD has a problem with variable-length strings -- shorter strings need padding, and it always processes max_length * n characters even if most strings are short. MSD is more natural for variable-length strings because it works left-to-right and stops early for short strings.

For variable-length strings, there is a key design decision: what happens when a string ends before the current position? For example, sorting ["app", "apple"]. At position 3, "app" has ended but "apple" has 'l'. The ended string must come FIRST -- because "app" < "apple" lexicographically. So I need to treat end-of-string as a sentinel character smaller than all others. In the counting sort bucket scheme, this means bucket -1 (or bucket 0 with everything else shifted by 1).

Algorithm:
1. Group strings by character at position d (end-of-string gets the lowest bucket)
2. Recursively sort each non-trivial group by position d+1
3. Concatenate results: ended strings first, then each character bucket in order

Wait, should I use an in-place approach or a simpler bucket-based approach? The in-place version (like 3-way string quicksort) is more memory efficient but harder to implement. The bucket approach using counting sort at each level is cleaner and has predictable O(total characters) time. The tradeoff: the bucket approach uses O(n + R) extra space per recursion level where R = alphabet size (256 for ASCII). For deep recursion on long strings, this could add up, but in practice it is fine.

One optimization: for small subarrays (say < 15 elements), switch to insertion sort. This avoids the overhead of counting sort when the bucket approach is overkill for tiny groups.

Time complexity: O(total characters across all strings) = O(sum of lengths). Each character is examined at most once across all recursion levels, because once strings are separated into different buckets, they never interact again.
</think>

## MSD Radix Sort for Strings

### Implementation

```python
def msd_radix_sort(strings):
    """MSD Radix Sort for variable-length strings.
    O(total_characters) time."""
    if len(strings) <= 1:
        return list(strings)

    result = list(strings)
    _msd_sort(result, 0, len(result) - 1, 0)
    return result


def _msd_sort(arr, lo, hi, d):
    """Sort arr[lo..hi] by character at position d."""
    if lo >= hi:
        return

    # Use insertion sort for small subarrays
    if hi - lo < 15:
        _insertion_sort(arr, lo, hi, d)
        return

    R = 256  # ASCII alphabet size
    count = [0] * (R + 2)  # +1 for end-of-string, +1 for prefix sums

    # Count frequencies
    for i in range(lo, hi + 1):
        c = _char_at(arr[i], d)
        count[c + 2] += 1

    # Prefix sums
    for r in range(R + 1):
        count[r + 1] += count[r]

    # Distribute
    aux = [None] * (hi - lo + 1)
    for i in range(lo, hi + 1):
        c = _char_at(arr[i], d)
        aux[count[c + 1]] = arr[i]
        count[c + 1] += 1

    # Copy back
    for i in range(lo, hi + 1):
        arr[i] = aux[i - lo]

    # Recursively sort each character group
    for r in range(R):
        _msd_sort(arr, lo + count[r], lo + count[r + 1] - 1, d + 1)


def _char_at(s, d):
    """Return character at position d, or -1 if past end."""
    if d < len(s):
        return ord(s[d])
    return -1


def _insertion_sort(arr, lo, hi, d):
    """Insertion sort for small subarrays, comparing from position d."""
    for i in range(lo + 1, hi + 1):
        key = arr[i]
        j = i - 1
        while j >= lo and arr[j][d:] > key[d:]:
            arr[j + 1] = arr[j]
            j -= 1
        arr[j + 1] = key


# Simple version without in-place optimization
def msd_radix_simple(strings, depth=0):
    """Simpler recursive MSD radix sort."""
    if len(strings) <= 1:
        return strings

    # Group by character at depth
    buckets = {}
    ended = []  # strings that end at this depth

    for s in strings:
        if depth >= len(s):
            ended.append(s)
        else:
            c = s[depth]
            if c not in buckets:
                buckets[c] = []
            buckets[c].append(s)

    # Ended strings come first (shorter = smaller)
    result = ended

    # Sort each bucket recursively, in character order
    for c in sorted(buckets.keys()):
        result.extend(msd_radix_simple(buckets[c], depth + 1))

    return result


# Demo
print("=== MSD Radix Sort for Strings ===\n")

strings = [
    "banana", "apple", "cherry", "apricot", "blueberry",
    "avocado", "app", "bat", "ball", "ban",
    "a", "ab", "abc", "b", "ba",
]

sorted_strings = msd_radix_simple(strings)
expected = sorted(strings)

print(f"Input:    {strings}")
print(f"Sorted:   {sorted_strings}")
print(f"Expected: {expected}")
print(f"Match: {'OK' if sorted_strings == expected else 'FAIL'}")

# Total characters
total_chars = sum(len(s) for s in strings)
print(f"\nTotal characters: {total_chars}")
print(f"Number of strings: {len(strings)}")

# Larger test
import random
random.seed(42)
chars = 'abcdefghij'
large_strings = [''.join(random.choices(chars, k=random.randint(1, 20)))
                 for _ in range(10000)]

import time
start = time.time()
sorted_large = msd_radix_simple(large_strings)
t_msd = time.time() - start

start = time.time()
sorted_builtin = sorted(large_strings)
t_builtin = time.time() - start

print(f"\n10k strings:")
print(f"  MSD radix: {t_msd:.4f}s")
print(f"  Built-in:  {t_builtin:.4f}s")
print(f"  Correct: {sorted_large == sorted_builtin}")

print(f"\n=== MSD vs LSD Radix Sort ===")
print(f"  MSD: left-to-right, good for variable-length strings")
print(f"  LSD: right-to-left, good for fixed-length (needs padding)")
print(f"  MSD complexity: O(total characters)")
print(f"  LSD complexity: O(max_length * n)")
```

### Complexity
- **Time**: O(total characters) = O(sum of string lengths)
- **Space**: O(n + R) per recursion level, O(n * max_length) total
- **Alphabet size R**: typically 256 for ASCII
- **Optimization**: switch to insertion sort for small groups'''),

    ("thinking/algorithms", r'''Implement external merge sort for sorting data that does not fit in memory. Show the multi-way merge using a min-heap and analyze I/O complexity.''', r'''<think>
External merge sort for data larger than available memory. This is fundamentally different from in-memory sorting because the bottleneck is I/O, not comparisons.

Phase 1 (Run creation): read chunks of data that fit in memory, sort each chunk in memory, write sorted chunks (runs) to disk. This is straightforward -- just use any O(n log n) in-memory sort.

Phase 2 (Multi-way merge): this is the interesting part. I need to merge k sorted runs into one. My first thought was a simple 2-way merge (like merge sort), but that would require O(log k) passes over all the data. With a min-heap, I can do a k-way merge in a single pass: maintain a heap of size k with the smallest unprocessed element from each run. Extract the minimum, output it, and insert the next element from that run.

Hmm, but what about I/O efficiency? Reading one element at a time from each run would be terrible -- each read is a disk seek. In practice, we buffer reads and writes in blocks. Read a block (say 4KB) from each run into memory, process elements from the buffer, and refill when a buffer empties. This is crucial for real-world performance but I will simplify for the implementation.

For k-way merge with n total elements:
- Phase 1: O(n/M * M log M) = O(n log M) internal sort, O(n/B) I/Os
- Phase 2: O(n log k) for the heap-based merge, O(n/B) I/Os per pass

Wait, do we always finish in one merge pass? Only if we can hold one buffer per run in memory: k * B <= M. If k is too large (more runs than we have memory for), we need multiple merge passes. The total I/O becomes O(n/B * ceil(log_{M/B}(n/M))). For typical parameters (M = 1GB, B = 4KB, n = 100GB), this is just 2-3 passes.

I considered using replacement selection for Phase 1 (which creates runs of average length 2M instead of M), but that adds complexity. I will keep it simple with fixed-size chunking.

For this implementation, I will simulate the disk I/O using in-memory lists acting as runs.
</think>

## External Merge Sort

### Implementation

```python
import heapq
import tempfile
import os


class ExternalMergeSort:
    """Sort data larger than memory using external merge sort."""

    def __init__(self, memory_limit=1000):
        """memory_limit: max elements to hold in memory at once."""
        self.memory_limit = memory_limit
        self.temp_files = []
        self.stats = {'reads': 0, 'writes': 0, 'comparisons': 0}

    def sort(self, input_data):
        """Sort input_data (iterator/list) using external merge sort.

        Returns sorted list.
        """
        # Phase 1: Create sorted runs
        runs = self._create_runs(input_data)

        if not runs:
            return []

        # Phase 2: Multi-way merge
        result = self._multiway_merge(runs)

        # Cleanup temp files
        self._cleanup()

        return result

    def _create_runs(self, data):
        """Create sorted runs from input data."""
        runs = []
        chunk = []

        for item in data:
            chunk.append(item)
            if len(chunk) >= self.memory_limit:
                chunk.sort()
                self.stats['writes'] += len(chunk)
                runs.append(list(chunk))
                chunk = []

        if chunk:
            chunk.sort()
            self.stats['writes'] += len(chunk)
            runs.append(chunk)

        return runs

    def _multiway_merge(self, runs):
        """Merge k sorted runs using a min-heap."""
        k = len(runs)
        if k == 0:
            return []
        if k == 1:
            return runs[0]

        # Initialize heap with first element from each run
        heap = []
        iterators = [iter(run) for run in runs]

        for i, it in enumerate(iterators):
            val = next(it, None)
            if val is not None:
                heapq.heappush(heap, (val, i))
                self.stats['reads'] += 1

        result = []
        while heap:
            val, run_idx = heapq.heappop(heap)
            self.stats['comparisons'] += 1
            result.append(val)

            next_val = next(iterators[run_idx], None)
            if next_val is not None:
                heapq.heappush(heap, (next_val, run_idx))
                self.stats['reads'] += 1

        return result

    def _cleanup(self):
        for f in self.temp_files:
            try:
                os.remove(f)
            except OSError:
                pass


def simulate_external_sort(data, memory_limit):
    """Simulate external merge sort and show statistics."""
    ems = ExternalMergeSort(memory_limit=memory_limit)
    sorted_data = ems.sort(data)

    n = len(data)
    k = (n + memory_limit - 1) // memory_limit  # number of runs

    return sorted_data, ems.stats, k


# Demo
import random
random.seed(42)

print("=== External Merge Sort ===\n")

# Small example
data = [38, 27, 43, 3, 9, 82, 10, 55, 24, 67, 15, 44, 31, 72, 8, 61]
memory = 4

sorted_data, stats, num_runs = simulate_external_sort(data, memory)
print(f"Input ({len(data)} elements, memory={memory}):")
print(f"  Data: {data}")
print(f"  Sorted: {sorted_data}")
print(f"  Correct: {sorted_data == sorted(data)}")
print(f"  Runs created: {num_runs}")
print(f"  Stats: {stats}")

# Larger simulation
print(f"\n=== Performance Analysis ===")
sizes = [1000, 10000, 100000]
memory_limits = [100, 500, 1000]

print(f"{'N':>8} {'Memory':>8} {'Runs':>6} {'Reads':>8} {'Writes':>8} {'Compares':>10}")
print("-" * 55)

for n in sizes:
    for mem in memory_limits:
        if mem <= n:
            data = [random.randint(0, 10**6) for _ in range(n)]
            result, stats, k = simulate_external_sort(data, mem)
            assert result == sorted(data)
            print(f"{n:>8} {mem:>8} {k:>6} {stats['reads']:>8} "
                  f"{stats['writes']:>8} {stats['comparisons']:>10}")

print(f"\n=== I/O Complexity ===")
print(f"  Phase 1 (run creation):")
print(f"    Read all data: O(n/B) I/Os")
print(f"    Sort in memory: O(M log M) per chunk")
print(f"    Write runs: O(n/B) I/Os")
print(f"  Phase 2 (k-way merge):")
print(f"    Read all runs: O(n/B) I/Os")
print(f"    Heap operations: O(n log k)")
print(f"    Write output: O(n/B) I/Os")
print(f"  Total I/O: O(n/B * log(n/M) / log(M/B))")
```

### I/O Complexity
```
n = total elements
M = memory size (elements)
B = block size (elements per I/O)
k = n/M runs

Phase 1: O(n/B) I/Os to read + write
Phase 2: O(n/B) I/Os per merge pass
Passes: O(log_{M/B}(n/M))
Total: O(n/B * ceil(log_{M/B}(n/M)))
```

### Practical Considerations
- **Buffer size**: read/write in blocks (4KB-64KB) for I/O efficiency
- **Run creation**: use replacement selection for longer initial runs
- **Multi-pass**: if k > M/B, need multiple merge passes
- **Parallel I/O**: overlap reading from different runs'''),

    ("thinking/algorithms", r'''Implement partial sorting algorithms: find the k smallest elements (selection), partial quicksort, and introselect. Compare with full sorting for various k/n ratios.''', r'''<think>
Partial sorting: find or sort only the k smallest (or largest) elements. When k << n, we should be able to do much better than a full O(n log n) sort.

Three main approaches to consider:

1. Selection (quickselect): partition-based, like quicksort but only recurse into one side. O(n) average. But wait, worst case is O(n^2) if we consistently pick bad pivots. Can be improved to O(n) worst case with median-of-medians, though the constant factor is large (~5n comparisons).

2. Partial quicksort: like quicksort but only recurse into the partition containing positions 0..k-1. If the pivot lands at position p >= k, we skip the right partition entirely. Average O(n + k log k). I initially thought this was just O(n), but no -- we still need to sort the left portion to get the k smallest in order, which costs k log k.

3. Introselect: hybrid approach. Start with quickselect (fast average case), but count bad partitions. If we get too many, switch to median-of-medians for guaranteed O(n). This is what C++ std::nth_element uses.

Hmm, what about a heap approach? Use a max-heap of size k. Scan through all n elements; if the current element is smaller than the heap top, replace it. O(n log k). The tradeoff: this is simpler to implement and has good worst-case behavior, but for k close to n, it degrades to O(n log n) which is no better than full sort. Quickselect is better for large k but has worse worst case.

Actually, which approach is best depends on the use case:
- Just need the k-th element? Quickselect (O(n) average).
- Need the k smallest in sorted order? Partial quicksort (O(n + k log k)) or heap (O(n log k)).
- Need guaranteed O(n)? Introselect.

When k is very small (like top-10 from a million elements), the heap approach shines because log(10) is tiny. When k is a constant fraction of n (like the median), quickselect is clearly better.
</think>

## Partial Sorting Algorithms

### Implementation

```python
import heapq
import random


def quickselect(arr, k):
    """Find k-th smallest element (0-indexed). O(n) average."""
    if k < 0 or k >= len(arr):
        raise IndexError("k out of range")

    arr = list(arr)  # copy

    def select(lo, hi, k):
        if lo == hi:
            return arr[lo]

        # Random pivot
        pivot_idx = random.randint(lo, hi)
        arr[pivot_idx], arr[hi] = arr[hi], arr[pivot_idx]
        pivot = arr[hi]

        # Partition
        store = lo
        for i in range(lo, hi):
            if arr[i] < pivot:
                arr[store], arr[i] = arr[i], arr[store]
                store += 1
        arr[store], arr[hi] = arr[hi], arr[store]

        if k == store:
            return arr[store]
        elif k < store:
            return select(lo, store - 1, k)
        else:
            return select(store + 1, hi, k)

    return select(0, len(arr) - 1, k)


def k_smallest_heap(arr, k):
    """Find k smallest elements using a max-heap. O(n log k)."""
    if k >= len(arr):
        return sorted(arr)
    if k <= 0:
        return []

    # Use a max-heap of size k (negate values for max behavior)
    heap = [-x for x in arr[:k]]
    heapq.heapify(heap)

    for x in arr[k:]:
        if x < -heap[0]:
            heapq.heapreplace(heap, -x)

    result = sorted([-x for x in heap])
    return result


def partial_quicksort(arr, k):
    """Sort only the k smallest elements. O(n + k log k) average."""
    arr = list(arr)

    def sort_partial(lo, hi, k_remaining):
        if lo >= hi or k_remaining <= 0:
            return

        # Partition
        pivot_idx = random.randint(lo, hi)
        arr[pivot_idx], arr[hi] = arr[hi], arr[pivot_idx]
        pivot = arr[hi]

        store = lo
        for i in range(lo, hi):
            if arr[i] < pivot:
                arr[store], arr[i] = arr[i], arr[store]
                store += 1
        arr[store], arr[hi] = arr[hi], arr[store]

        left_size = store - lo

        # Always recurse into left partition
        sort_partial(lo, store - 1, k_remaining)

        # Only recurse into right if we need more elements
        if left_size + 1 < k_remaining:
            sort_partial(store + 1, hi, k_remaining - left_size - 1)

    sort_partial(0, len(arr) - 1, k)
    return arr[:k]


def introselect(arr, k):
    """Find k-th smallest with O(n) worst-case guarantee.
    Uses median-of-medians as fallback."""
    arr = list(arr)

    def median_of_medians(lst):
        if len(lst) <= 5:
            return sorted(lst)[len(lst) // 2]
        groups = [lst[i:i+5] for i in range(0, len(lst), 5)]
        medians = [sorted(g)[len(g) // 2] for g in groups]
        return median_of_medians(medians)

    def select(data, k):
        if len(data) <= 5:
            return sorted(data)[k]

        pivot = median_of_medians(data)
        low = [x for x in data if x < pivot]
        equal = [x for x in data if x == pivot]
        high = [x for x in data if x > pivot]

        if k < len(low):
            return select(low, k)
        elif k < len(low) + len(equal):
            return pivot
        else:
            return select(high, k - len(low) - len(equal))

    return select(arr, k)


# Demo
random.seed(42)
print("=== Partial Sorting Algorithms ===\n")

arr = [64, 34, 25, 12, 22, 11, 90, 78, 55, 43, 67, 31]
k = 5

print(f"Array: {arr}")
print(f"k = {k}\n")

# Quickselect
kth = quickselect(arr, k - 1)  # 0-indexed
print(f"Quickselect (k-th smallest): {kth}")
print(f"  Verify: {sorted(arr)[k-1]}")

# K smallest via heap
k_sm = k_smallest_heap(arr, k)
print(f"\nK smallest (heap): {k_sm}")
print(f"  Verify: {sorted(arr)[:k]}")

# Partial quicksort
p_sorted = partial_quicksort(arr, k)
print(f"\nPartial quicksort: {p_sorted}")
print(f"  Sorted correctly: {sorted(p_sorted) == sorted(arr)[:k]}")

# Introselect
intro_kth = introselect(arr, k - 1)
print(f"\nIntroselect (k-th): {intro_kth}")
print(f"  Verify: {sorted(arr)[k-1]}")

# Performance comparison
import time

n = 100000
data = [random.randint(0, 10**6) for _ in range(n)]

print(f"\n=== Performance (n={n}) ===")
for k in [10, 100, 1000, 10000, 50000]:
    # Full sort
    start = time.time()
    full = sorted(data)[:k]
    t_full = time.time() - start

    # Heap
    start = time.time()
    heap_result = k_smallest_heap(data, k)
    t_heap = time.time() - start

    # Quickselect (just find k-th)
    start = time.time()
    qs_result = quickselect(data, k - 1)
    t_qs = time.time() - start

    print(f"  k={k:>5}: full_sort={t_full:.4f}s, "
          f"heap={t_heap:.4f}s, quickselect={t_qs:.4f}s")
```

### Complexity Comparison
| Algorithm | Average | Worst | Output Sorted? |
|-----------|---------|-------|---------------|
| Full sort | O(n log n) | O(n log n) | Yes |
| Heap (k smallest) | O(n log k) | O(n log k) | Yes |
| Quickselect | O(n) | O(n^2) | No |
| Introselect | O(n) | O(n) | No |
| Partial quicksort | O(n + k log k) | O(n^2) | Yes |

Choose based on whether you need the elements sorted and the k/n ratio.'''),

    ("thinking/algorithms", r'''Implement tournament sort and explain how it works. Show the tree structure, how it achieves O(n log n) with a practical advantage for finding the top-k elements. Compare with heapsort.''', r'''<think>
Tournament sort works like a sports tournament bracket. Let me think through the mechanism carefully.

Elements are paired up, winners (smaller values) advance, until we find the overall minimum at the root. But then what? My first thought was to rebuild the entire tree to find the second minimum, but that would be O(n) per extraction, giving O(n^2) total. We can do better.

Key insight: after extracting the minimum, we only need to replay the path from that leaf to the root. The rest of the tree is unchanged. This is only O(log n) comparisons per extraction.

How it works:
1. Build a tournament tree (complete binary tree) with elements at the leaves
2. Each internal node stores the winner (smaller element) of its two children
3. The root has the overall minimum
4. Extract the root (minimum), replace its leaf with infinity
5. Replay the tournament from that leaf upward (O(log n) comparisons)
6. Repeat n times to get all elements sorted

Wait, there is an interesting consequence: finding the second smallest requires only O(log n) comparisons. Why? Because the second smallest must have lost directly to the first smallest at some point in the tournament. There are only log(n) such "losers" along the winner's path. This is actually an information-theoretic result -- n + ceil(log n) - 2 comparisons are sufficient for finding both the minimum and second minimum.

I considered whether tournament sort is just a heapsort variant, but it is structurally different. A heap modifies elements in-place with sift-up/sift-down; a tournament tree is a separate structure with the original elements only at the leaves. The tradeoff: tournament sort uses O(n) extra space (the 2n-node tree) whereas heapsort is in-place. But tournament sort has better cache behavior for top-k extraction and is naturally suited for external sorting (replacement selection).

The number of comparisons: n - 1 for building the tree (each internal node requires one comparison), plus O(log n) per extraction for the remaining n-1 elements. Total: O(n log n).
</think>

## Tournament Sort

### Implementation

```python
class TournamentSort:
    """Tournament sort using a winner tree."""

    def __init__(self, arr):
        self.n = len(arr)
        # Pad to next power of 2
        self.size = 1
        while self.size < self.n:
            self.size *= 2

        self.INF = float('inf')
        # Tree: 2*size nodes. Leaves at indices [size, 2*size)
        self.tree = [self.INF] * (2 * self.size)
        self.leaf_idx = [0] * (2 * self.size)  # which original index won

        # Place elements at leaves
        for i in range(self.n):
            self.tree[self.size + i] = arr[i]
            self.leaf_idx[self.size + i] = i

        # Build tournament (bottom-up)
        for i in range(self.size - 1, 0, -1):
            left = 2 * i
            right = 2 * i + 1
            if self.tree[left] <= self.tree[right]:
                self.tree[i] = self.tree[left]
                self.leaf_idx[i] = self.leaf_idx[left]
            else:
                self.tree[i] = self.tree[right]
                self.leaf_idx[i] = self.leaf_idx[right]

        self.comparisons = self.size - 1  # initial build

    def extract_min(self):
        """Extract minimum and update tree. O(log n)."""
        if self.tree[1] == self.INF:
            return None

        min_val = self.tree[1]
        winner_leaf = self.leaf_idx[1]

        # Replace winner with infinity
        leaf_pos = self.size + winner_leaf
        self.tree[leaf_pos] = self.INF

        # Replay tournament from leaf to root
        pos = leaf_pos // 2
        while pos >= 1:
            left = 2 * pos
            right = 2 * pos + 1
            self.comparisons += 1
            if self.tree[left] <= self.tree[right]:
                self.tree[pos] = self.tree[left]
                self.leaf_idx[pos] = self.leaf_idx[left]
            else:
                self.tree[pos] = self.tree[right]
                self.leaf_idx[pos] = self.leaf_idx[right]
            pos //= 2

        return min_val

    def sort(self):
        """Extract all elements in sorted order."""
        result = []
        for _ in range(self.n):
            val = self.extract_min()
            if val is not None and val != self.INF:
                result.append(val)
        return result

    def top_k(self, k):
        """Extract k smallest elements. O(n + k log n)."""
        result = []
        for _ in range(min(k, self.n)):
            val = self.extract_min()
            if val is not None and val != self.INF:
                result.append(val)
        return result


def heapsort(arr):
    """Standard heapsort for comparison."""
    import heapq
    h = list(arr)
    heapq.heapify(h)
    comparisons = len(h)  # approximate
    result = []
    while h:
        result.append(heapq.heappop(h))
        comparisons += 2  # approximate
    return result, comparisons


# Demo
print("=== Tournament Sort ===\n")

arr = [38, 27, 43, 3, 9, 82, 10, 55]
ts = TournamentSort(arr)

print(f"Input: {arr}")
print(f"Tournament tree built ({ts.comparisons} comparisons)")

sorted_arr = ts.sort()
print(f"Sorted: {sorted_arr}")
print(f"Correct: {sorted_arr == sorted(arr)}")
print(f"Total comparisons: {ts.comparisons}")

# Top-k extraction
print(f"\n=== Top-K Extraction ===")
arr2 = [64, 34, 25, 12, 22, 11, 90, 78, 55, 43, 67, 31, 88, 15, 72, 49]
for k in [3, 5, 8]:
    ts2 = TournamentSort(arr2)
    top = ts2.top_k(k)
    expected = sorted(arr2)[:k]
    print(f"  Top {k}: {top} (expected: {expected}) "
          f"[{'OK' if top == expected else 'FAIL'}]")
    print(f"    Comparisons: {ts2.comparisons} (vs full sort: ~{len(arr2) * 4})")

# Comparison with heapsort
import time
import random
random.seed(42)

print(f"\n=== Tournament Sort vs Heapsort ===")
for n in [1000, 5000, 10000]:
    data = [random.randint(0, 10**6) for _ in range(n)]

    start = time.time()
    ts_result = TournamentSort(data).sort()
    t_tournament = time.time() - start

    start = time.time()
    hs_result, hs_comp = heapsort(data)
    t_heapsort = time.time() - start

    print(f"  n={n}: tournament={t_tournament:.4f}s, heapsort={t_heapsort:.4f}s")
    assert ts_result == hs_result

print(f"\n=== Key Properties ===")
print(f"  Build tree: O(n) comparisons")
print(f"  Each extraction: O(log n) comparisons")
print(f"  Full sort: O(n log n)")
print(f"  Top-k: O(n + k log n)")
print(f"  Space: O(n) for tournament tree")
print(f"  Advantage: finding 2nd smallest needs only log(n) comparisons")
```

### Tournament Sort vs Heapsort
| Property | Tournament Sort | Heapsort |
|----------|----------------|----------|
| Build | O(n) | O(n) |
| Extract min | O(log n) | O(log n) |
| Total | O(n log n) | O(n log n) |
| Space | O(n) extra | O(1) in-place |
| Top-k | O(n + k log n) | O(n + k log n) |
| Cache | Better (local) | Worse (jumps) |

Tournament sort excels in external sorting (replacement selection) and when comparisons are expensive.'''),
]
