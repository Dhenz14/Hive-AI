PAIRS = [
    ("thinking/algorithms", r'''Single Number III: Given an integer array where exactly two elements appear once and all others appear exactly twice, find the two unique elements. You must use O(1) extra space and O(n) time.

Example: nums = [1,2,1,3,2,5] -> [3,5] (order doesn't matter)''', r'''<think>
This is a bit manipulation problem. Let me build up from simpler cases.

**Single Number I recap**: If only ONE element is unique, XOR all elements. Duplicates cancel out (a ^ a = 0), leaving the unique element. Beautiful and simple.

**Two unique elements**: XOR of all elements gives xor_all = a ^ b. Since a != b, xor_all != 0. But how do I separate a from b? I only have their XOR, not the individual values.

My first thought was to somehow iterate through possible values... but that would not be O(1) space. I need a way to split the numbers into two groups such that a and b end up in different groups, while every duplicate pair stays together in the same group.

Hmm, since xor_all != 0, at least one bit position differs between a and b. If I partition all numbers by whether that bit is set, then a and b must land in different groups (they differ at that bit), while every duplicate pair lands in the same group (both copies have identical bits). XOR within each group then isolates one unique number each. That is the key insight!

But which differing bit should I pick? Actually, ANY set bit in xor_all works, since each one represents a position where a and b differ. The easiest to extract is the lowest set bit: diff_bit = xor_all & (-xor_all). This uses the two's complement trick where -x = ~x + 1, so AND-ing with -x isolates the rightmost 1-bit.

Wait, could I also use the highest set bit? Yes, but extracting it is more work (need bit_length). The lowest set bit is cleaner.

Algorithm:
1. XOR all numbers -> xor_all = a ^ b
2. diff_bit = xor_all & (-xor_all)
3. XOR all numbers where (num & diff_bit) != 0 -> gives one unique number, call it a
4. The other number: b = xor_all ^ a

I initially thought I needed two separate XOR groups, but actually I only need one group's XOR and then derive the other from xor_all. That saves a pass.

Verification: [1,2,1,3,2,5]
- xor_all = 1^2^1^3^2^5 = (1^1)^(2^2)^(3^5) = 0^0^6 = 6 (binary: 110)
- diff_bit = 6 & (-6) = 2 (binary: 010)
- Group with bit 1 set: 2, 3, 2 -> XOR = 2^3^2 = 3
- Other number: 6 ^ 3 = 5
- Result: [3, 5]. Correct!
</think>

## Single Number III — Two Unique Elements via Bit Manipulation

```python
from typing import List


def single_number_iii(nums: List[int]) -> List[int]:
    """Find the two elements that appear exactly once (all others appear twice).

    Time Complexity: O(n)
    Space Complexity: O(1)
    """
    # Step 1: XOR all — gives a ^ b
    xor_all = 0
    for num in nums:
        xor_all ^= num

    # Step 2: Find any bit where a and b differ
    # The lowest set bit trick: x & (-x) isolates the rightmost 1-bit
    diff_bit = xor_all & (-xor_all)

    # Step 3: Partition into two groups and XOR within each
    a = 0
    for num in nums:
        if num & diff_bit:
            a ^= num
    b = xor_all ^ a

    return [a, b]


# --- Tests ---
def test_example():
    result = set(single_number_iii([1, 2, 1, 3, 2, 5]))
    assert result == {3, 5}

def test_negative():
    result = set(single_number_iii([1, -1, 2, -2, 3, 4]))
    # All appear once? No — need exactly two unique.
    # Let me fix: [1, -1, 1, 2, -1, 2] -> unique: none. Bad test.
    # Better: [-1, 0, -1, 3, 0, 5]
    result = set(single_number_iii([-1, 0, -1, 3, 0, 5]))
    assert result == {3, 5}

def test_two_elements():
    result = set(single_number_iii([7, 13]))
    assert result == {7, 13}

def test_adjacent_values():
    result = set(single_number_iii([1, 1, 2, 3]))
    assert result == {2, 3}

test_example()
test_negative()
test_two_elements()
test_adjacent_values()
print("All Single Number III tests passed!")
```

### The `x & (-x)` Trick

In two's complement, `-x = ~x + 1`. The lowest set bit of `x` is isolated by `x & (-x)`:

```
x    = 01101100
-x   = 10010100
x&-x = 00000100  <- only the lowest set bit remains
```

This single-bit mask perfectly separates the two unique numbers: one has this bit set, the other doesn't. Duplicates always land in the same group since both copies have identical bits.
'''),

    ("thinking/algorithms", r'''Counting Bits: Given a non-negative integer n, return an array ans of length n+1 where ans[i] is the number of 1-bits (popcount) in the binary representation of i. Solve in O(n) time without using any built-in popcount function for each number.

Example: n = 5 -> [0,1,1,2,1,2] (binary: 0,1,10,11,100,101)''', r'''<think>
I need O(n) total time, meaning O(1) per number. The naive approach of counting bits for each number individually (looping through bits or using Brian Kernighan's trick) would be O(n log n) since each number has up to log(n) bits. I need something faster.

Could I use DP? If I can express bits[i] in terms of some smaller already-computed value, I get O(1) per number.

**Approach 1: Right shift**
bits[i] = bits[i >> 1] + (i & 1). The idea: i >> 1 removes the last bit, and i & 1 tells us whether that removed bit was 1. Since i >> 1 < i for i > 0, it is already computed. This is clean and intuitive.

**Approach 2: Last set bit**
bits[i] = bits[i & (i-1)] + 1. Here i & (i-1) clears the lowest set bit. So the popcount of i is 1 more than the popcount of i with its lowest bit removed. And i & (i-1) < i, so it is already computed.

Hmm, which is better? Both are O(1) per number, O(n) total. Approach 1 is simpler -- just a shift and an AND. Approach 2 requires understanding the i & (i-1) trick. I will implement Approach 1 as primary and Approach 2 as an alternative for educational value.

Wait, I should double-check that i >> 1 is actually smaller. For i = 0, we have bits[0] = 0 (base case). For i = 1, bits[1] = bits[0] + 1 = 1. For i = 2, bits[2] = bits[1] + 0 = 1. All valid.

Let me verify the full sequence for n=5:
- bits[0] = 0
- bits[1] = bits[0] + 1 = 1
- bits[2] = bits[1] + 0 = 1
- bits[3] = bits[1] + 1 = 2
- bits[4] = bits[2] + 0 = 1
- bits[5] = bits[2] + 1 = 2
Result: [0, 1, 1, 2, 1, 2]. Matches the expected output!

Actually, I also considered Approach 3 (offset-based: track the MSB and use bits[i] = bits[i - offset] + 1), but it requires extra bookkeeping to update the offset at each power of 2. Not worth the complexity when Approach 1 is so simple.
</think>

## Counting Bits — O(n) DP Solution

```python
from typing import List


def count_bits(n: int) -> List[int]:
    """Return popcount for every integer from 0 to n using DP.

    Recurrence: bits[i] = bits[i >> 1] + (i & 1)
    - i >> 1: remove last bit (already computed since i >> 1 < i)
    - i & 1:  add 1 if last bit is set

    Time Complexity: O(n)
    Space Complexity: O(n) (output array)
    """
    bits = [0] * (n + 1)
    for i in range(1, n + 1):
        bits[i] = bits[i >> 1] + (i & 1)
    return bits


def count_bits_last_set_bit(n: int) -> List[int]:
    """Alternative: use i & (i-1) which clears the lowest set bit.

    bits[i] = bits[i & (i-1)] + 1
    """
    bits = [0] * (n + 1)
    for i in range(1, n + 1):
        bits[i] = bits[i & (i - 1)] + 1
    return bits


# --- Tests ---
def test_example():
    expected = [0, 1, 1, 2, 1, 2]
    assert count_bits(5) == expected
    assert count_bits_last_set_bit(5) == expected

def test_zero():
    assert count_bits(0) == [0]

def test_powers_of_two():
    result = count_bits(16)
    # Powers of 2 always have exactly 1 bit set
    for p in [1, 2, 4, 8, 16]:
        assert result[p] == 1, f"bits[{p}] = {result[p]}, expected 1"

def test_all_ones():
    result = count_bits(15)
    # 15 = 1111 in binary -> 4 bits
    assert result[15] == 4
    # 7 = 111 -> 3 bits
    assert result[7] == 3

def test_consistency():
    """Verify both methods agree up to 1000."""
    a = count_bits(1000)
    b = count_bits_last_set_bit(1000)
    assert a == b

test_example()
test_zero()
test_powers_of_two()
test_all_ones()
test_consistency()
print("All counting bits tests passed!")
```

### Why Three DP Recurrences All Work

| Recurrence | Intuition | Base Case |
|-----------|-----------|-----------|
| `bits[i>>1] + (i&1)` | Remove last bit, check if it was 1 | `bits[0] = 0` |
| `bits[i&(i-1)] + 1` | Clear lowest set bit, add 1 | `bits[0] = 0` |
| `bits[i-offset] + 1` | Subtract highest power of 2 | `bits[0] = 0` |

All run in O(1) per number with no division or modulo — just bit operations and array lookups. The right-shift approach is arguably cleanest: it decomposes the problem as "how many bits does i have, excluding the last position, plus is the last position a 1?"
'''),

    ("thinking/algorithms", r'''Find the maximum XOR of two numbers in an array. Given an array of non-negative integers, find the pair (a, b) whose XOR a ^ b is maximized. Solve in O(n * L) time where L is the bit length (typically 32).

Example: nums = [3, 10, 5, 25, 2, 8] -> 28 (XOR of 5 and 25: 00101 ^ 11001 = 11100 = 28)''', r'''<think>
The brute force checks all O(n^2) pairs. I need O(n * L) where L is the bit length. What data structure supports per-bit decisions?

My first thought was sorting -- maybe the maximum XOR pair has some nice property in sorted order. But actually no, XOR does not respect numerical ordering at all. For example, 5 (101) and 25 (11001) give XOR 28, which is not related to their relative position in sorted order.

A binary trie is the right approach. I insert each number bit by bit from MSB to LSB. Then for each number, I greedily traverse the trie trying to take the opposite bit at each level.

Why does the greedy work? XOR is 1 when bits differ. Setting bit position k contributes 2^k to the result. Since 2^k > 2^0 + 2^1 + ... + 2^(k-1), maximizing higher bits is always more valuable than any combination of lower bits. Therefore, at each bit from MSB down, we should take the opposite bit if available. The trie lets us make this greedy choice in O(1) per bit.

Hmm, but what if taking the opposite bit at level k forces us into a subtree where all subsequent bits match (giving 0 XOR for the remaining bits)? Could taking the same bit at level k lead to a better overall result? Actually no, because the contribution of bit k (2^k) is strictly larger than the maximum possible contribution of all remaining bits combined (2^(k-1) + 2^(k-2) + ... + 1 = 2^k - 1 < 2^k). So the greedy choice at each level is provably optimal.

One implementation detail: I need a fixed bit width for all numbers so the trie paths are aligned. I will use the bit length of the maximum number in the array.

Time: O(n * L) for building + O(n * L) for queries = O(n * L). For L = 32, this is effectively O(n).
Space: O(n * L) for the trie nodes.
</think>

## Maximum XOR of Two Numbers — Binary Trie

```python
from typing import List, Optional


class TrieNode:
    __slots__ = ['children']

    def __init__(self) -> None:
        self.children: List[Optional['TrieNode']] = [None, None]


class BinaryTrie:
    """Trie storing binary representations of integers (MSB first)."""

    def __init__(self, bit_length: int = 32) -> None:
        self.root = TrieNode()
        self.bit_length = bit_length

    def insert(self, num: int) -> None:
        node = self.root
        for i in range(self.bit_length - 1, -1, -1):
            bit = (num >> i) & 1
            if node.children[bit] is None:
                node.children[bit] = TrieNode()
            node = node.children[bit]

    def max_xor_with(self, num: int) -> int:
        """Find the maximum XOR of num with any number in the trie."""
        node = self.root
        xor_val = 0
        for i in range(self.bit_length - 1, -1, -1):
            bit = (num >> i) & 1
            opposite = 1 - bit

            # Greedily choose the opposite bit to maximize XOR
            if node.children[opposite] is not None:
                xor_val |= (1 << i)
                node = node.children[opposite]
            else:
                node = node.children[bit]

        return xor_val


def find_maximum_xor(nums: List[int]) -> int:
    """Find maximum XOR of any two numbers in the array.

    Time Complexity: O(n * L) where L = bit length (32)
    Space Complexity: O(n * L) for the trie
    """
    if len(nums) < 2:
        return 0

    # Determine bit length needed
    max_num = max(nums)
    bit_length = max_num.bit_length() if max_num > 0 else 1

    trie = BinaryTrie(bit_length)
    for num in nums:
        trie.insert(num)

    max_xor = 0
    for num in nums:
        max_xor = max(max_xor, trie.max_xor_with(num))

    return max_xor


# --- Tests ---
def test_example():
    nums = [3, 10, 5, 25, 2, 8]
    assert find_maximum_xor(nums) == 28  # 5 ^ 25 = 28

def test_small():
    assert find_maximum_xor([1, 2]) == 3  # 1 ^ 2 = 3

def test_all_same():
    assert find_maximum_xor([7, 7, 7]) == 0

def test_powers_of_two():
    nums = [1, 2, 4, 8, 16]
    assert find_maximum_xor(nums) == 24  # 16 ^ 8 = 24

def test_with_zero():
    assert find_maximum_xor([0, 15]) == 15

test_example()
test_small()
test_all_same()
test_powers_of_two()
test_with_zero()
print("All maximum XOR tests passed!")
```

### Greedy Choice Correctness

At each bit position from MSB to LSB, we maximize the XOR by choosing the opposite bit when available. This greedy works because:
- Setting a higher bit contributes more than all lower bits combined (2^k > 2^0 + 2^1 + ... + 2^(k-1))
- So maximizing higher bits first is always optimal
- The trie structure lets us make this choice in O(1) per bit

Total: O(n) insertions * O(L) per insertion + O(n) queries * O(L) per query = O(n * L).
'''),

    ("thinking/algorithms", r'''Implement efficient power-of-two checks and related bit tricks:
1. Check if a number is a power of two
2. Find the next power of two >= n
3. Round down to the nearest power of two
4. Count trailing zeros
5. Check if exactly two bits are set

All operations should be O(1) using bit manipulation, with no loops.''', r'''<think>
These are fundamental bit manipulation tricks. Let me work through each one carefully.

1. **Is power of two**: My first thought is to check if log2(n) is an integer, but that involves floating point and could have precision issues. A better approach: n > 0 and (n & (n-1)) == 0. Why does this work? A power of two has exactly one bit set (e.g., 8 = 1000). n-1 flips that bit and sets all lower bits (7 = 0111). AND gives 0. For non-powers (e.g., 6 = 110, 5 = 101, AND = 100 != 0), it does not. I also need n > 0 because 0 & (-1) = 0 but 0 is not a power of two.

2. **Next power of two >= n**: I considered bit smearing (propagate highest bit down, then add 1), but actually Python's bit_length makes this simpler: 1 << n.bit_length(). Wait, does that work when n is already a power of 2? For n=4 (100), bit_length=3, so 1 << 3 = 8. That is wrong -- I want 4, not 8. So I need to check if n is already a power of two first and return n directly in that case. Hmm, alternatively I could use 1 << (n-1).bit_length(), but for n=1 that gives 1 << 0 = 1, which is correct. For n=4, (4-1)=3, bit_length=2, 1 << 2 = 4. Correct! Actually wait, for n=5, (5-1)=4, bit_length=3, 1 << 3 = 8. Correct. So 1 << (n-1).bit_length() handles all cases cleanly without a special check. But I should still handle n <= 0 separately.

3. **Round down to nearest power of two**: 1 << (n.bit_length() - 1). For n=7 (111), bit_length=3, result = 4. Correct.

4. **Count trailing zeros**: (n & -n) gives the lowest set bit as a value. Then (n & -n).bit_length() - 1 gives its position. I considered using de Bruijn sequences (common in C), but Python's bit_length is cleaner and avoids lookup tables.

5. **Exactly two bits set**: Apply n & (n-1) to clear the lowest set bit. If the result m is itself a power of two (and nonzero), there were exactly 2 bits. So: m = n & (n-1), check m > 0 and (m & (m-1)) == 0. I initially thought I could just check n & (n-1) != 0, but that would be true for any n with 2 or more bits set -- I need to verify exactly 2, not "at least 2."
</think>

## Power of Two Checks and Bit Manipulation Tricks

```python
def is_power_of_two(n: int) -> bool:
    """Check if n is a power of two. O(1).

    Trick: a power of two has exactly one bit set.
    n & (n-1) clears the lowest set bit. If result is 0, there was only one bit.
    """
    return n > 0 and (n & (n - 1)) == 0


def next_power_of_two(n: int) -> int:
    """Find the smallest power of two >= n. O(1).

    Uses bit_length: if n is 2^k, bit_length is k+1 but we want 2^k.
    If n is not a power of 2, we want 2^(bit_length).
    """
    if n <= 0:
        return 1
    if is_power_of_two(n):
        return n
    return 1 << n.bit_length()


def prev_power_of_two(n: int) -> int:
    """Find the largest power of two <= n. O(1).

    The highest set bit position is bit_length - 1.
    """
    if n <= 0:
        return 0
    return 1 << (n.bit_length() - 1)


def count_trailing_zeros(n: int) -> int:
    """Count trailing zeros in binary representation. O(1).

    Trick: n & (-n) isolates the lowest set bit.
    Its bit_length - 1 gives the position (= number of trailing zeros).
    Returns -1 for n = 0 (undefined).
    """
    if n == 0:
        return -1  # Undefined: all zeros
    return (n & -n).bit_length() - 1


def has_exactly_two_bits(n: int) -> bool:
    """Check if exactly two bits are set in n. O(1).

    Clear the lowest bit: m = n & (n-1). If m is a power of two, n had exactly 2 bits.
    """
    if n <= 0:
        return False
    m = n & (n - 1)        # Clear lowest set bit
    return m > 0 and (m & (m - 1)) == 0  # Check remaining is power of two


# --- Tests ---
def test_is_power_of_two():
    assert is_power_of_two(1) is True    # 2^0
    assert is_power_of_two(2) is True    # 2^1
    assert is_power_of_two(1024) is True # 2^10
    assert is_power_of_two(0) is False
    assert is_power_of_two(3) is False
    assert is_power_of_two(6) is False
    assert is_power_of_two(-4) is False

def test_next_power_of_two():
    assert next_power_of_two(1) == 1
    assert next_power_of_two(3) == 4
    assert next_power_of_two(4) == 4
    assert next_power_of_two(5) == 8
    assert next_power_of_two(17) == 32
    assert next_power_of_two(0) == 1

def test_prev_power_of_two():
    assert prev_power_of_two(1) == 1
    assert prev_power_of_two(3) == 2
    assert prev_power_of_two(4) == 4
    assert prev_power_of_two(7) == 4
    assert prev_power_of_two(16) == 16
    assert prev_power_of_two(17) == 16

def test_trailing_zeros():
    assert count_trailing_zeros(1) == 0     # ...0001
    assert count_trailing_zeros(2) == 1     # ...0010
    assert count_trailing_zeros(8) == 3     # ...1000
    assert count_trailing_zeros(12) == 2    # ...1100
    assert count_trailing_zeros(0) == -1

def test_exactly_two_bits():
    assert has_exactly_two_bits(3) is True    # 11
    assert has_exactly_two_bits(5) is True    # 101
    assert has_exactly_two_bits(6) is True    # 110
    assert has_exactly_two_bits(7) is False   # 111 (three bits)
    assert has_exactly_two_bits(4) is False   # 100 (one bit)
    assert has_exactly_two_bits(0) is False

test_is_power_of_two()
test_next_power_of_two()
test_prev_power_of_two()
test_trailing_zeros()
test_exactly_two_bits()
print("All power-of-two and bit trick tests passed!")
```

### Bit Trick Reference Table

| Operation | Expression | Why It Works |
|-----------|-----------|--------------|
| Is power of 2 | `n & (n-1) == 0` | Clears the single set bit |
| Lowest set bit | `n & (-n)` | Two's complement: `-n = ~n + 1` |
| Clear lowest bit | `n & (n-1)` | `n-1` flips lowest bit and below |
| Next power of 2 | `1 << n.bit_length()` | Jump to next bit position |
| Prev power of 2 | `1 << (bit_length - 1)` | Highest set bit position |
| Trailing zeros | `(n & -n).bit_length() - 1` | Position of lowest set bit |

All operations are O(1) with no loops, branches, or lookup tables — pure arithmetic on fixed-width integers.
'''),

    ("thinking/algorithms", r'''Generate the n-bit Gray code sequence. A Gray code is a binary numeral system where two successive values differ in only one bit. The sequence should start with 0.

Example: n = 2 -> [0, 1, 3, 2] (binary: 00, 01, 11, 10 — each adjacent pair differs by one bit, including wrapping)''', r'''<think>
Gray codes: successive values differ by exactly one bit. There are several generation methods. Let me think through them.

**Method 1: Direct formula**
The i-th Gray code is i ^ (i >> 1). Let me verify:
- 0: 0 ^ 0 = 0 (00)
- 1: 1 ^ 0 = 1 (01)
- 2: 2 ^ 1 = 3 (11)
- 3: 3 ^ 1 = 2 (10)

Each consecutive pair differs by one bit. But why does this formula work in general? My initial intuition was unclear, so let me think more carefully. In standard binary, incrementing i to i+1 can flip multiple bits (e.g., 0111 -> 1000 flips 4 bits). The XOR with i >> 1 "smooths" this: it converts the multi-bit increment into a single-bit change. Formally, G(i) ^ G(i+1) always has exactly one bit set -- this can be proven by case analysis on the number of trailing 1-bits in i.

**Method 2: Reflect-and-prefix**
- Start with [0, 1] for n=1
- For each additional bit: take current sequence, reverse it, OR the new bit onto the reversed copy, concatenate
- n=2: [00, 01] + [11, 10] = [0, 1, 3, 2]

Wait, does this guarantee the single-bit difference at the seam (where original meets reflected)? The last element of the original [01] and the first element of the reflected [11] differ only in the new high bit. Yes, because the reflected copy is a mirror, so the elements at the junction are the same except for the new prefix bit. That is the key insight of the "reflected" construction.

I initially considered a **backtracking** method (generate all permutations of bits and check the Gray code property), but that would be O(2^n * n) and completely unnecessary when we have O(2^n) methods available.

I will implement both Method 1 (elegant one-liner) and Method 2 (illustrative of the recursive structure).

Time: O(2^n) for both -- optimal since the output has 2^n values.
</think>

## Gray Code Generation

### Method 1: Direct Formula — `i ^ (i >> 1)`

```python
from typing import List


def gray_code_formula(n: int) -> List[int]:
    """Generate n-bit Gray code using the XOR formula.

    The i-th Gray code value is i ^ (i >> 1).

    Time Complexity: O(2^n)
    Space Complexity: O(2^n)
    """
    return [i ^ (i >> 1) for i in range(1 << n)]


### Method 2: Reflect-and-Prefix (classic construction)

def gray_code_reflect(n: int) -> List[int]:
    """Generate n-bit Gray code using the reflection method.

    Start with [0]. For each bit k:
        - Take current sequence
        - Reflect (reverse) it
        - Prepend 2^k to each reflected value
        - Concatenate

    Time Complexity: O(2^n)
    Space Complexity: O(2^n)
    """
    result = [0]
    for k in range(n):
        # Reflect current sequence and add the k-th bit
        high_bit = 1 << k
        reflected = [high_bit | val for val in reversed(result)]
        result.extend(reflected)
    return result


def verify_gray_code(sequence: List[int], n: int) -> bool:
    """Verify a sequence is a valid n-bit Gray code."""
    expected_len = 1 << n
    if len(sequence) != expected_len:
        return False
    if len(set(sequence)) != expected_len:
        return False  # Duplicates
    if sequence[0] != 0:
        return False

    for i in range(len(sequence)):
        diff = sequence[i] ^ sequence[(i + 1) % len(sequence)]
        # Must differ by exactly one bit (diff is a power of 2)
        if diff == 0 or (diff & (diff - 1)) != 0:
            return False
    return True


# --- Tests ---
def test_n2():
    result = gray_code_formula(2)
    assert result == [0, 1, 3, 2]
    assert verify_gray_code(result, 2)

def test_n3():
    result = gray_code_formula(3)
    assert result == [0, 1, 3, 2, 6, 7, 5, 4]
    assert verify_gray_code(result, 3)

def test_methods_agree():
    for n in range(5):
        assert gray_code_formula(n) == gray_code_reflect(n)

def test_n0():
    assert gray_code_formula(0) == [0]
    assert verify_gray_code([0], 0)

def test_n1():
    assert gray_code_formula(1) == [0, 1]

def test_large():
    result = gray_code_formula(10)
    assert len(result) == 1024
    assert verify_gray_code(result, 10)

test_n2()
test_n3()
test_methods_agree()
test_n0()
test_n1()
test_large()
print("All Gray code tests passed!")
```

### How `i ^ (i >> 1)` Produces Gray Code

Consider consecutive integers in binary:

```
i     binary    i>>1    gray = i^(i>>1)   binary
0     000       000     000                000
1     001       000     001                001
2     010       001     011                011
3     011       001     010                010
4     100       010     110                110
```

The XOR with the shifted version "smooths" the binary counting so that only one bit changes per step. The proof: when incrementing i, the lowest set bit and the bit below it change. After XOR with i>>1, exactly one bit in the Gray code changes.

### Complexity

Both methods generate exactly 2^n values in O(1) per value, giving O(2^n) time — optimal since the output itself has 2^n elements.
'''),
]
