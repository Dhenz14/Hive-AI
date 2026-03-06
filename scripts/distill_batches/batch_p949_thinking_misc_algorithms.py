PAIRS = [
    ("thinking/algorithms", r'''Prove that reservoir sampling produces a uniform random sample and implement it. Given a stream of unknown length, maintain a sample of exactly k elements where each element has equal probability of being selected.''', r'''<think>
Reservoir sampling: maintain a sample of size k from a stream of unknown length n. The challenge is that we do not know n in advance, yet each element must have equal probability k/n of being in the final sample.

Algorithm (Vitter's Algorithm R):
1. Fill the reservoir with the first k elements
2. For the i-th element (i > k, 0-indexed as i >= k):
   - Generate random j in [0, i]
   - If j < k, replace reservoir[j] with the i-th element

Proof of uniformity by induction. I need to show each element has probability k/i after seeing i elements.

Base case: after seeing k elements, each is in reservoir with probability 1 = k/k. Correct.

Inductive step: assume after i-1 elements, each has probability k/(i-1) of being in the reservoir.

For the i-th element: P(selected) = k/i. That is direct from the algorithm. Correct.

For any previous element j that was in the reservoir: P(j survives step i) = P(j in reservoir after i-1) * P(j not replaced at step i).

Hmm, what is P(j not replaced at step i)? The i-th element gets selected with probability k/i. If selected, it replaces a uniformly random slot, so P(j's slot is chosen) = 1/k. Let me compute P(j not replaced):

P(j not replaced) = P(i-th not selected) + P(i-th selected but replaces a different slot)
= (1 - k/i) + (k/i) * (k-1)/k
= (i-k)/i + (k-1)/i = (i-1)/i

Wait, let me double-check that algebra. (i-k)/i + (k-1)/i = (i-k+k-1)/i = (i-1)/i. Yes.

So P(j in reservoir after i) = k/(i-1) * (i-1)/i = k/i. QED.

Each element has probability k/i after seeing i elements, which is k/n after all n elements. The beauty is that this works without knowing n in advance -- the probabilities automatically adjust as more elements arrive.

I should also implement weighted reservoir sampling as an extension. The Efraimidis-Spirakis algorithm assigns each element a key = random()^(1/weight), and the reservoir keeps the k elements with the highest keys. This is elegant but I initially thought it was random()/weight -- that would be wrong because it does not give the right distribution.
</think>

## Reservoir Sampling

### Proof and Implementation

```python
import random


def reservoir_sample(stream, k):
    """Reservoir sampling: maintain k uniform random elements from a stream.

    Proof of uniformity:
    After seeing i elements, each has probability k/i of being in reservoir.
    Base: first k elements all in reservoir, prob = k/k = 1.
    Step: element i (>k) enters with prob k/i.
          Previous element j survives with prob (i-1)/i.
          P(j in reservoir after i) = k/(i-1) * (i-1)/i = k/i. QED.
    """
    reservoir = []
    for i, item in enumerate(stream):
        if i < k:
            reservoir.append(item)
        else:
            j = random.randint(0, i)
            if j < k:
                reservoir[j] = item

    return reservoir


def verify_uniformity(n, k, trials=100000):
    """Verify that reservoir sampling is uniform via simulation."""
    counts = [0] * n

    for _ in range(trials):
        sample = reservoir_sample(range(n), k)
        for item in sample:
            counts[item] += 1

    expected = k * trials / n
    max_deviation = max(abs(c - expected) / expected for c in counts)
    return counts, expected, max_deviation


# Demo
random.seed(42)

print("=== Reservoir Sampling ===\n")

# Basic usage
stream = range(100)
sample = reservoir_sample(stream, 5)
print(f"Stream: 0..99")
print(f"Sample of 5: {sample}")

# Uniformity verification
print(f"\n=== Uniformity Verification ===")
n, k = 20, 5
counts, expected, max_dev = verify_uniformity(n, k, trials=200000)

print(f"n={n}, k={k}, 200k trials")
print(f"Expected count per element: {expected:.0f}")
print(f"Actual counts: {counts}")
print(f"Max relative deviation: {max_dev:.4f}")
print(f"Uniform (deviation < 5%): {max_dev < 0.05}")

# Streaming demonstration
print(f"\n=== Streaming Demo ===")

def data_stream():
    """Simulate an infinite-looking stream."""
    for i in range(1000000):
        yield i

sample = reservoir_sample(data_stream(), 10)
print(f"10 random samples from stream of 1M elements:")
print(f"  {sample}")

# Weighted reservoir sampling
def weighted_reservoir_sample(stream, k):
    """Reservoir sampling with weights.
    Each item is (value, weight)."""
    import math
    reservoir = []
    keys = []

    for value, weight in stream:
        key = random.random() ** (1.0 / weight)
        if len(reservoir) < k:
            reservoir.append(value)
            keys.append(key)
        elif key > min(keys):
            min_idx = keys.index(min(keys))
            reservoir[min_idx] = value
            keys[min_idx] = key

    return reservoir

print(f"\n=== Weighted Reservoir Sampling ===")
weighted_stream = [(f"item_{i}", i + 1) for i in range(20)]
# Higher weight = more likely to be sampled
sample_counts = {}
for _ in range(10000):
    sample = weighted_reservoir_sample(weighted_stream, 3)
    for item in sample:
        sample_counts[item] = sample_counts.get(item, 0) + 1

print("Top 5 most sampled (higher weight = more likely):")
for item, count in sorted(sample_counts.items(), key=lambda x: -x[1])[:5]:
    print(f"  {item}: {count} times")
```

### Proof of Uniformity
```
After processing i elements, P(element j is in reservoir) = k/i.

Base case (i = k): P = k/k = 1. All first k elements are in reservoir.

Inductive step (i -> i+1):
  P(j in reservoir after i+1)
  = P(j in reservoir after i) * P(j not replaced at step i+1)
  = (k/i) * (1 - k/(i+1) * 1/k)
  = (k/i) * (1 - 1/(i+1))
  = (k/i) * (i/(i+1))
  = k/(i+1)
```

### Complexity
- **Time**: O(n) single pass
- **Space**: O(k) for the reservoir
- **No need to know n in advance** -- works on arbitrary streams'''),

    ("thinking/algorithms", r'''Implement and prove the Fisher-Yates shuffle produces a uniformly random permutation. Show both the modern (Knuth) version and the inside-out version for streaming.''', r'''<think>
Fisher-Yates shuffle (modern version, Knuth):
1. Start with array of n elements
2. For i from n-1 down to 1:
   - Pick random j in [0, i]
   - Swap arr[i] and arr[j]

Proof of uniformity: Each of the n! permutations is equally likely.

My first attempt at a proof: count the number of possible outcomes. At step i, we choose from i+1 positions. Total outcomes = n * (n-1) * ... * 1 = n!. Since there are exactly n! permutations, each one must correspond to exactly one sequence of choices. Therefore each permutation has probability 1/n!.

But wait, I should verify that different sequences of choices actually produce different permutations. Could two different choice sequences give the same result? Let me think... At step n-1, we choose which element goes to position n-1. Given that, at step n-2, we choose from the remaining. Each choice sequence uniquely determines which element ends up at each position, working from the end. So yes, the mapping from choice sequences to permutations is a bijection.

A common mistake is to swap with a random position from [0, n-1] at EVERY step (instead of [0, i]). This seems equivalent but it is not -- it produces n^n possible outcomes, and n^n is not divisible by n! for n > 2. So some permutations must be more likely than others. For n=3: 3^3 = 27 outcomes, 3! = 6 permutations, 27/6 = 4.5 -- not an integer. This proves the naive approach is biased.

The inside-out version (for streaming) is clever:
1. Start with empty array
2. For each new element x (index i):
   - Pick random j in [0, i]
   - If j != i, set result[i] = result[j]
   - Set result[j] = x

I initially worried this might introduce bias because we are building the array incrementally, but the proof is analogous to the standard version. After inserting element i, we have (i+1)! equally likely configurations. Each new element is placed at a uniformly random position, displacing the current occupant. This works without knowing n in advance, making it suitable for streaming.
</think>

## Fisher-Yates Shuffle

### Implementation and Proof

```python
import random
from collections import Counter


def fisher_yates_shuffle(arr):
    """Modern Fisher-Yates (Knuth) shuffle. O(n), in-place.

    Proof: each permutation has probability exactly 1/n!
    Step i chooses uniformly from [0, i], giving n * (n-1) * ... * 1 = n!
    equally likely outcomes, each producing a unique permutation.
    """
    arr = list(arr)
    n = len(arr)
    for i in range(n - 1, 0, -1):
        j = random.randint(0, i)
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def inside_out_shuffle(stream):
    """Inside-out Fisher-Yates for streaming data.
    Builds shuffled array without knowing n in advance."""
    result = []
    for i, x in enumerate(stream):
        j = random.randint(0, i)
        if j == len(result):
            result.append(x)
        else:
            result.append(result[j])
            result[j] = x
    return result


def biased_shuffle_WRONG(arr):
    """INCORRECT shuffle -- common mistake.
    Swapping with random position from [0, n-1] at each step
    does NOT produce uniform permutations."""
    arr = list(arr)
    n = len(arr)
    for i in range(n):
        j = random.randint(0, n - 1)  # BUG: should be [0, i]
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def verify_uniformity(shuffle_func, n, trials=500000):
    """Count frequency of each permutation."""
    perm_counts = Counter()
    arr = list(range(n))
    for _ in range(trials):
        result = shuffle_func(arr)
        perm_counts[tuple(result)] += 1
    return perm_counts


# Demo
random.seed(42)
print("=== Fisher-Yates Shuffle ===\n")

arr = [1, 2, 3, 4, 5]
print(f"Original: {arr}")
for i in range(5):
    shuffled = fisher_yates_shuffle(arr)
    print(f"  Shuffle {i+1}: {shuffled}")

# Inside-out version
print(f"\nInside-out (streaming):")
stream = iter(range(1, 6))
result = inside_out_shuffle(stream)
print(f"  Stream 1..5 -> {result}")

# Uniformity test with n=3 (6 permutations)
print(f"\n=== Uniformity Test (n=3, 6 permutations) ===")
trials = 600000

# Correct shuffle
correct_counts = verify_uniformity(fisher_yates_shuffle, 3, trials)
expected = trials / 6

print(f"\nCorrect Fisher-Yates:")
for perm in sorted(correct_counts.keys()):
    count = correct_counts[perm]
    ratio = count / expected
    print(f"  {perm}: {count:>6} (ratio: {ratio:.3f})")

# Wrong shuffle (biased)
wrong_counts = verify_uniformity(biased_shuffle_WRONG, 3, trials)
print(f"\nBiased shuffle (WRONG):")
for perm in sorted(wrong_counts.keys()):
    count = wrong_counts[perm]
    ratio = count / expected
    print(f"  {perm}: {count:>6} (ratio: {ratio:.3f})")

# Chi-squared test
def chi_squared(counts, expected):
    return sum((c - expected)**2 / expected for c in counts.values())

chi_correct = chi_squared(correct_counts, expected)
chi_wrong = chi_squared(wrong_counts, expected)
print(f"\nChi-squared (lower = more uniform):")
print(f"  Correct: {chi_correct:.2f}")
print(f"  Wrong:   {chi_wrong:.2f}")

print(f"\n=== Proof of Correctness ===")
print(f"  Step n-1: choose from n elements   -> n choices")
print(f"  Step n-2: choose from n-1 elements -> n-1 choices")
print(f"  ...")
print(f"  Step 0:   1 element remains         -> 1 choice")
print(f"  Total outcomes: n! (each equally likely)")
print(f"  Each permutation: probability 1/n!")
```

### Common Mistake
The naive approach (swap with random `[0, n-1]` at each step) produces n^n outcomes, which is NOT divisible by n! for n > 2. This makes some permutations more likely than others.

### Complexity
- **Time**: O(n)
- **Space**: O(1) in-place (or O(n) for inside-out)
- **Randomness**: n-1 random numbers needed
- **Correctness**: each of n! permutations has probability exactly 1/n!'''),

    ("thinking/algorithms", r'''Implement and prove Boyer-Moore majority voting algorithm. Given an array, find the element that appears more than n/2 times (if it exists) using O(1) space and O(n) time.''', r'''<think>
Boyer-Moore majority vote algorithm. The goal: find the element appearing > n/2 times, using O(1) space and O(n) time. The naive approach (hash map counting) uses O(n) space, so we need something cleverer.

Algorithm:
1. Initialize candidate = None, count = 0
2. For each element x:
   - If count == 0, set candidate = x, count = 1
   - Else if x == candidate, count++
   - Else count--
3. Verify that candidate actually appears > n/2 times (second pass)

But why does this work? My first intuition was wrong -- I thought the count tracks how many times we have seen the majority element. It does not. The count tracks the "net advantage" of the current candidate over all other elements combined.

Let me think about it differently: imagine "pairing off" different elements. Each decrement pairs one instance of the candidate with one non-candidate element, eliminating both from consideration. Since the majority element m appears > n/2 times and all other elements combined appear < n/2 times, m cannot be fully paired off. Some copies of m must remain unpaired, and those will be the final candidate.

But wait -- could a non-majority element survive as the candidate? Consider [1, 2, 3, 4, 5]. After processing: 1(count=1), 2(count=0), 3(count=1), 4(count=0), 5(count=1). The candidate is 5, but 5 is not a majority. This is why the verification step is necessary -- without it, the algorithm can return a false positive when no majority exists.

Hmm, can I extend this to find elements appearing > n/3 times? Yes -- maintain up to k-1 = 2 candidates with counts. When a new element matches neither candidate and both have positive counts, decrement both. This generalizes naturally: for > n/k, maintain k-1 candidates.

The verification step is essential. Phase 1 only identifies candidates; Phase 2 confirms. For the extended version, each candidate needs separate verification.
</think>

## Boyer-Moore Majority Vote Algorithm

### Implementation and Proof

```python
def boyer_moore_majority(arr):
    """Find majority element (> n/2 occurrences) in O(n) time, O(1) space.

    Returns:
        (candidate, is_majority) -- is_majority is True only if verified
    """
    # Phase 1: Find candidate
    candidate = None
    count = 0

    for x in arr:
        if count == 0:
            candidate = x
            count = 1
        elif x == candidate:
            count += 1
        else:
            count -= 1

    # Phase 2: Verify
    if candidate is None:
        return None, False

    actual_count = sum(1 for x in arr if x == candidate)
    is_majority = actual_count > len(arr) // 2

    return candidate, is_majority


def boyer_moore_extended(arr, k=3):
    """Find all elements appearing > n/k times.
    Extension of Boyer-Moore to at most k-1 candidates."""
    # Phase 1: Find up to k-1 candidates
    candidates = {}  # value -> count

    for x in arr:
        if x in candidates:
            candidates[x] += 1
        elif len(candidates) < k - 1:
            candidates[x] = 1
        else:
            # Decrement all counts, remove zeros
            to_remove = []
            for key in candidates:
                candidates[key] -= 1
                if candidates[key] == 0:
                    to_remove.append(key)
            for key in to_remove:
                del candidates[key]

    # Phase 2: Verify each candidate
    result = []
    threshold = len(arr) // k
    for cand in candidates:
        count = sum(1 for x in arr if x == cand)
        if count > threshold:
            result.append((cand, count))

    return result


# Demo
print("=== Boyer-Moore Majority Vote ===\n")

# Test cases
tests = [
    [3, 3, 4, 2, 4, 4, 2, 4, 4],    # 4 is majority (5/9 > 4.5)
    [1, 1, 1, 2, 2],                  # 1 is majority (3/5 > 2.5)
    [1, 2, 3, 4, 5],                  # no majority
    [7, 7, 7, 7, 1, 2, 7],            # 7 is majority (5/7 > 3.5)
    [1],                               # 1 is majority
]

for arr in tests:
    candidate, is_maj = boyer_moore_majority(arr)
    print(f"  {str(arr):35s} -> candidate={candidate}, majority={is_maj}")

# Proof visualization
print(f"\n=== Proof Visualization ===")
arr = [3, 3, 4, 2, 4, 4, 2, 4, 4]
candidate = None
count = 0
print(f"Array: {arr}")
print(f"{'Step':>4} {'Element':>8} {'Candidate':>10} {'Count':>6} {'Action':>15}")
for i, x in enumerate(arr):
    if count == 0:
        candidate = x
        count = 1
        action = "new candidate"
    elif x == candidate:
        count += 1
        action = "increment"
    else:
        count -= 1
        action = "decrement"
    print(f"{i:>4} {x:>8} {candidate:>10} {count:>6} {action:>15}")

# Extended version: elements appearing > n/3 times
print(f"\n=== Extended Boyer-Moore (> n/3) ===")
arr2 = [1, 2, 3, 1, 2, 1, 2, 1, 2]
results = boyer_moore_extended(arr2, k=3)
print(f"Array: {arr2}")
print(f"Elements appearing > {len(arr2)//3} times:")
for val, cnt in results:
    print(f"  {val}: {cnt} times")

# Uniformity test: does it work on random data?
import random
random.seed(42)
print(f"\n=== Stress Test ===")
for trial in range(5):
    n = 1000
    majority_val = random.randint(0, 9)
    arr = [majority_val] * (n // 2 + 1) + [random.randint(0, 9) for _ in range(n - n // 2 - 1)]
    random.shuffle(arr)
    cand, is_maj = boyer_moore_majority(arr)
    actual_count = sum(1 for x in arr if x == cand)
    print(f"  Trial {trial}: candidate={cand}, count={actual_count}/{n}, "
          f"correct={cand == majority_val}")
```

### Proof of Correctness
```
Let m = majority element, count(m) > n/2.

Claim: after Phase 1, candidate = m.

Proof by contradiction: if candidate != m, then m was "canceled out"
by non-m elements. But there are > n/2 copies of m and < n/2 non-m
elements, so m cannot be fully canceled. Therefore m survives as
the candidate.

Formally: each decrement pairs one m with one non-m. Since
count(m) > count(non-m), some m's remain unpaired.
```

### Complexity
- **Time**: O(n) -- two passes
- **Space**: O(1) -- only candidate and count
- **Phase 2 is essential**: without verification, algorithm may report non-majority element when no majority exists'''),

    ("thinking/algorithms", r'''Implement the Dutch National Flag algorithm (3-way partition). Given an array with three types of elements, sort it in O(n) time with O(1) extra space. Show applications to quicksort and color sorting.''', r'''<think>
The Dutch National Flag problem (Dijkstra): given an array containing three types of elements (e.g., 0, 1, 2), sort it in-place in a single pass.

My first thought was to count occurrences of each value and then overwrite the array, but that requires two passes and does not generalize to complex objects. The single-pass approach with three pointers is more elegant.

Algorithm: maintain three pointers:
- lo: boundary between 0s and 1s (everything < lo is 0)
- mid: current element being examined
- hi: boundary between 1s and 2s (everything > hi is 2)

Process:
- If arr[mid] == 0: swap arr[lo] and arr[mid], advance both lo and mid
- If arr[mid] == 1: just advance mid
- If arr[mid] == 2: swap arr[mid] and arr[hi], decrement hi

Wait, why don't we advance mid in the third case? Because we swapped an unknown element from position hi into position mid. We need to examine it before moving on. In the first case (swap with lo), we CAN advance mid because everything below lo is already a 0 or 1 (specifically, it is a 1 that was in the [lo..mid-1] region). Hmm, actually is it always a 1? Yes -- because the invariant says arr[lo..mid-1] contains 1s, and lo < mid when we do the swap, so arr[lo] was a 1. After swapping, arr[lo] = 0 and arr[mid] = 1, both correct positions.

Invariant:
- arr[0..lo-1] contains 0s
- arr[lo..mid-1] contains 1s
- arr[mid..hi] is unprocessed
- arr[hi+1..n-1] contains 2s

This is powerful for quicksort with many duplicates. Standard quicksort degrades to O(n^2) when all elements are equal because every partition is maximally unbalanced. The 3-way partition puts all elements equal to the pivot in the middle, eliminating them from further recursion. This makes quicksort O(n) for arrays with O(1) distinct values.

Applications beyond sorting: any time you need to classify elements into exactly 3 categories in a single pass with O(1) extra space.
</think>

## Dutch National Flag Algorithm

### Implementation

```python
def dutch_national_flag(arr, low_val=0, mid_val=1, high_val=2):
    """Sort array of three values in O(n) time, O(1) space.

    Uses three pointers: lo, mid, hi.
    Invariant:
      [0, lo)    = low_val
      [lo, mid)  = mid_val
      [mid, hi]  = unprocessed
      (hi, n)    = high_val
    """
    arr = list(arr)
    n = len(arr)
    lo, mid, hi = 0, 0, n - 1

    while mid <= hi:
        if arr[mid] == low_val:
            arr[lo], arr[mid] = arr[mid], arr[lo]
            lo += 1
            mid += 1
        elif arr[mid] == mid_val:
            mid += 1
        else:  # arr[mid] == high_val
            arr[mid], arr[hi] = arr[hi], arr[mid]
            hi -= 1
            # Do NOT advance mid -- swapped element needs checking

    return arr


def three_way_partition(arr, pivot):
    """3-way partition for quicksort: elements < pivot, == pivot, > pivot.
    Returns (less, equal, greater) lists."""
    arr = list(arr)
    lo, mid, hi = 0, 0, len(arr) - 1

    while mid <= hi:
        if arr[mid] < pivot:
            arr[lo], arr[mid] = arr[mid], arr[lo]
            lo += 1
            mid += 1
        elif arr[mid] == pivot:
            mid += 1
        else:
            arr[mid], arr[hi] = arr[hi], arr[mid]
            hi -= 1

    return arr[:lo], arr[lo:mid], arr[mid:]


def quicksort_3way(arr):
    """Quicksort using 3-way partitioning. Handles duplicates efficiently."""
    if len(arr) <= 1:
        return arr

    import random
    pivot = arr[random.randint(0, len(arr) - 1)]
    less, equal, greater = three_way_partition(arr, pivot)
    return quicksort_3way(less) + equal + quicksort_3way(greater)


# Demo
print("=== Dutch National Flag ===\n")

# Basic usage
arr = [2, 0, 1, 2, 1, 0, 0, 2, 1, 0, 1, 2]
sorted_arr = dutch_national_flag(arr)
print(f"Input:  {arr}")
print(f"Sorted: {sorted_arr}")
assert sorted_arr == sorted(arr)

# Step-by-step visualization
print(f"\n=== Step-by-Step ===")
arr = [1, 2, 0, 1, 0, 2]
arr_copy = list(arr)
n = len(arr_copy)
lo, mid, hi = 0, 0, n - 1
step = 0

print(f"{'Step':>4} {'Array':>20} {'lo':>3} {'mid':>4} {'hi':>3} {'Action':>20}")
print(f"{'':>4} {str(arr_copy):>20} {lo:>3} {mid:>4} {hi:>3} {'initial':>20}")

while mid <= hi:
    step += 1
    if arr_copy[mid] == 0:
        arr_copy[lo], arr_copy[mid] = arr_copy[mid], arr_copy[lo]
        action = f"swap [{lo}]<->[{mid}], lo++,mid++"
        lo += 1
        mid += 1
    elif arr_copy[mid] == 1:
        action = "mid++"
        mid += 1
    else:
        arr_copy[mid], arr_copy[hi] = arr_copy[hi], arr_copy[mid]
        action = f"swap [{mid}]<->[{hi}], hi--"
        hi -= 1
    print(f"{step:>4} {str(arr_copy):>20} {lo:>3} {mid:>4} {hi:>3} {action:>20}")

# 3-way partition for quicksort
print(f"\n=== 3-Way Partition (Quicksort) ===")
arr2 = [4, 2, 7, 4, 1, 4, 8, 4, 3]
pivot = 4
less, equal, greater = three_way_partition(arr2, pivot)
print(f"Array: {arr2}, pivot={pivot}")
print(f"Less:    {less}")
print(f"Equal:   {equal}")
print(f"Greater: {greater}")

# Full quicksort with 3-way partition
import random
random.seed(42)
arr3 = [random.randint(1, 5) for _ in range(20)]
sorted3 = quicksort_3way(arr3)
print(f"\nQuicksort 3-way:")
print(f"  Input:  {arr3}")
print(f"  Sorted: {sorted3}")
print(f"  Correct: {sorted3 == sorted(arr3)}")

# Color sorting application
print(f"\n=== Color Sorting ===")
colors = ['blue', 'red', 'white', 'blue', 'red', 'white', 'red', 'blue']
color_map = {'red': 0, 'white': 1, 'blue': 2}
rev_map = {0: 'red', 1: 'white', 2: 'blue'}
numeric = [color_map[c] for c in colors]
sorted_numeric = dutch_national_flag(numeric)
sorted_colors = [rev_map[n] for n in sorted_numeric]
print(f"Input:  {colors}")
print(f"Sorted: {sorted_colors}")
```

### Invariant
```
[0, lo)     -> all low_val  (sorted section: 0s)
[lo, mid)   -> all mid_val  (sorted section: 1s)
[mid, hi]   -> unprocessed
(hi, n-1]   -> all high_val (sorted section: 2s)
```

### Complexity
- **Time**: O(n) -- single pass, each element examined at most twice
- **Space**: O(1) -- three pointers only
- **Comparisons**: at most 2n
- **Key property**: handles elements equal to pivot in O(1) for quicksort'''),

    ("thinking/algorithms", r'''Implement Morris traversal for binary trees. Perform inorder traversal using O(1) extra space (no stack, no recursion). Explain the threading technique and prove it does not damage the tree.''', r'''<think>
Morris traversal: inorder traversal of a binary tree using O(1) extra space. Standard approaches use either recursion (O(h) stack space) or an explicit stack (O(h) space). Can we do better?

The key idea: temporarily modify the tree itself to remember where to return after processing a left subtree. Specifically, for each node, find its inorder predecessor (rightmost node in left subtree) and create a temporary link from the predecessor's right pointer back to the current node.

But wait, does this not damage the tree? My initial concern was that modifying pointers could break the tree structure permanently. The trick is that threads are removed when we revisit a node. Each node is encountered twice: once when we create the thread (going left), and once when we follow the thread back (visiting the node and going right). On the second encounter, we remove the thread, restoring the original structure.

Algorithm:
1. current = root
2. While current is not None:
   a. If current has no left child: visit current, move to right
   b. If current has left child:
      - Find inorder predecessor (rightmost in left subtree)
      - If predecessor's right is None: set predecessor.right = current (create thread), move left
      - If predecessor's right == current: we came back via the thread. Remove it, visit current, move right

How do we distinguish case b.1 from b.2? By checking whether the predecessor's right pointer is None or points to current. If it is None, we have not visited yet. If it points to current, we are returning via the thread. This is elegant -- the thread itself is the "visited" flag.

Hmm, what about the time complexity? Finding the inorder predecessor requires traversing down the left subtree's right spine, which could be O(n) in the worst case for a single node. But across all nodes, each edge is traversed at most 3 times: once going left, once finding the predecessor, and once following the thread back. So the amortized total is O(n).

I considered whether this could be adapted for preorder traversal. Yes -- just move the "visit" step. For inorder, we visit when removing the thread (on the way back). For preorder, we visit when creating the thread (on the way down). The tree modification logic stays the same.

Proof that the tree is not damaged:
- Each thread is created exactly once and removed exactly once
- After traversal completes, all temporary threads are gone
- The tree is identical to its original structure
</think>

## Morris Traversal (O(1) Space Tree Traversal)

### Implementation

```python
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


def morris_inorder(root):
    """Inorder traversal using O(1) extra space.

    Uses temporary threading: predecessor's right points to current node.
    All threads are removed after traversal -- tree is unchanged.
    """
    result = []
    current = root

    while current is not None:
        if current.left is None:
            # No left child: visit and go right
            result.append(current.val)
            current = current.right
        else:
            # Find inorder predecessor (rightmost in left subtree)
            predecessor = current.left
            while predecessor.right is not None and predecessor.right is not current:
                predecessor = predecessor.right

            if predecessor.right is None:
                # Create thread: predecessor -> current
                predecessor.right = current
                current = current.left
            else:
                # Thread exists: we've returned. Remove thread, visit, go right
                predecessor.right = None  # restore tree
                result.append(current.val)
                current = current.right

    return result


def morris_preorder(root):
    """Preorder traversal using O(1) space."""
    result = []
    current = root

    while current is not None:
        if current.left is None:
            result.append(current.val)
            current = current.right
        else:
            predecessor = current.left
            while predecessor.right is not None and predecessor.right is not current:
                predecessor = predecessor.right

            if predecessor.right is None:
                result.append(current.val)  # visit BEFORE going left
                predecessor.right = current
                current = current.left
            else:
                predecessor.right = None
                current = current.right

    return result


def recursive_inorder(root):
    """Standard recursive inorder for verification."""
    if root is None:
        return []
    return recursive_inorder(root.left) + [root.val] + recursive_inorder(root.right)


def verify_tree_unchanged(root, original_edges):
    """Verify tree structure is unchanged after Morris traversal."""
    edges = []
    def collect(node):
        if node is None:
            return
        if node.left:
            edges.append((node.val, node.left.val, 'L'))
        if node.right:
            edges.append((node.val, node.right.val, 'R'))
        collect(node.left)
        collect(node.right)
    collect(root)
    return sorted(edges) == sorted(original_edges)


# Build test tree
#         4
#        / \
#       2   6
#      / \ / \
#     1  3 5  7
root = TreeNode(4,
    TreeNode(2, TreeNode(1), TreeNode(3)),
    TreeNode(6, TreeNode(5), TreeNode(7))
)

# Record original structure
original_edges = []
def collect_edges(node):
    if node is None:
        return
    if node.left:
        original_edges.append((node.val, node.left.val, 'L'))
    if node.right:
        original_edges.append((node.val, node.right.val, 'R'))
    collect_edges(node.left)
    collect_edges(node.right)
collect_edges(root)

print("=== Morris Traversal ===\n")

# Inorder
morris_result = morris_inorder(root)
recursive_result = recursive_inorder(root)
print(f"Tree:      4")
print(f"          / \\")
print(f"         2   6")
print(f"        / \\ / \\")
print(f"       1  3 5  7")
print(f"\nMorris inorder:    {morris_result}")
print(f"Recursive inorder: {recursive_result}")
print(f"Match: {morris_result == recursive_result}")

# Verify tree unchanged
unchanged = verify_tree_unchanged(root, original_edges)
print(f"Tree unchanged: {unchanged}")

# Preorder
morris_pre = morris_preorder(root)
print(f"\nMorris preorder: {morris_pre}")

# Larger tree test
def build_bst(values):
    if not values:
        return None
    mid = len(values) // 2
    return TreeNode(values[mid],
                    build_bst(values[:mid]),
                    build_bst(values[mid+1:]))

large_tree = build_bst(list(range(1, 16)))  # BST with 15 nodes
morris_large = morris_inorder(large_tree)
print(f"\nBST 1-15 Morris inorder: {morris_large}")
print(f"Correct: {morris_large == list(range(1, 16))}")

# Step-by-step visualization
print(f"\n=== Step-by-Step Threading ===")
small_root = TreeNode(2, TreeNode(1), TreeNode(3))
current = small_root
steps = 0
while current is not None:
    steps += 1
    if current.left is None:
        print(f"  Step {steps}: visit {current.val}, go right")
        current = current.right
    else:
        pred = current.left
        while pred.right is not None and pred.right is not current:
            pred = pred.right
        if pred.right is None:
            print(f"  Step {steps}: thread {pred.val} -> {current.val}, go left")
            pred.right = current
            current = current.left
        else:
            print(f"  Step {steps}: remove thread {pred.val} -> {current.val}, "
                  f"visit {current.val}, go right")
            pred.right = None
            current = current.right

print(f"\n=== Complexity ===")
print(f"  Time: O(n) -- each edge traversed at most 3 times")
print(f"  Space: O(1) -- only a few pointers, no stack/recursion")
print(f"  Tree is fully restored after traversal completes")
```

### How Threading Works
```
Before:  1 <- 2 -> 3        After threading 1->2:
             |                    1 -> 2 -> 3
             v                    ^    |
            (left subtree)        |____|  (temporary thread)

Thread is removed when we return to node 2 via the thread.
```

### Complexity
- **Time**: O(n) -- each of the n-1 edges traversed at most 3 times
- **Space**: O(1) -- no recursion stack, no explicit stack
- **Trade-off**: modifies tree temporarily (thread creation/removal)'''),
]
