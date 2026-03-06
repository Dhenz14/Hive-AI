PAIRS = [
    ("thinking/algorithms", r'''Implement rolling hash (Rabin-Karp) for substring matching. Explain the math behind it, how to handle hash collisions, and demonstrate finding all occurrences of a pattern in a text.''', r'''<think>
Rolling hash is the foundation of Rabin-Karp string matching. The idea is to compute a hash for each substring of length m in the text using O(1) updates as we slide the window.

The hash function: treat the string as a polynomial in some base. For string s[0..m-1], hash = s[0]*base^(m-1) + s[1]*base^(m-2) + ... + s[m-1], all mod some large prime.

When we slide the window from position i to i+1, we remove the contribution of s[i] and add s[i+m]:
new_hash = (old_hash - s[i] * base^(m-1)) * base + s[i+m], all mod p.

Key considerations:
1. Choose a large prime modulus (e.g., 10^9 + 7 or 10^9 + 9)
2. Choose a base larger than the alphabet size (e.g., 31 or 131)
3. Handle collisions by verifying matches with actual string comparison
4. Precompute base^(m-1) mod p to avoid recomputation
5. Be careful with negative values in modular arithmetic

For multiple pattern matching, we can use multiple hash functions (double hashing) to reduce collision probability. The probability of a false positive with one hash is roughly 1/p, so with two independent hashes it becomes 1/p^2.

Edge cases: empty pattern, pattern longer than text, all characters the same (worst case for collisions with bad hash parameters).
</think>

## Rolling Hash (Rabin-Karp Algorithm)

### Mathematical Foundation
Treat each string as a number in base `b` modulo prime `p`:
- `hash(s[0..m-1]) = sum(s[i] * b^(m-1-i)) mod p`
- Sliding: `hash(s[1..m]) = (hash(s[0..m-1]) - s[0]*b^(m-1)) * b + s[m]`

### Implementation

```python
class RollingHash:
    def __init__(self, base=131, mod=10**9 + 7):
        self.base = base
        self.mod = mod

    def match(self, text, pattern):
        """Find all start indices where pattern occurs in text."""
        n, m = len(text), len(pattern)
        if m == 0 or m > n:
            return []

        b, p = self.base, self.mod
        results = []

        # Precompute base^(m-1) mod p
        power = pow(b, m - 1, p)

        # Compute hash of pattern
        pat_hash = 0
        for ch in pattern:
            pat_hash = (pat_hash * b + ord(ch)) % p

        # Compute hash of first window
        win_hash = 0
        for i in range(m):
            win_hash = (win_hash * b + ord(text[i])) % p

        # Check first window
        if win_hash == pat_hash and text[:m] == pattern:
            results.append(0)

        # Slide the window
        for i in range(1, n - m + 1):
            # Remove leftmost character, add new rightmost
            win_hash = (win_hash - ord(text[i - 1]) * power) % p
            win_hash = (win_hash * b + ord(text[i + m - 1])) % p

            # On hash match, verify to avoid false positives
            if win_hash == pat_hash and text[i:i + m] == pattern:
                results.append(i)

        return results


class DoubleHash:
    """Double hashing for lower collision probability."""
    def __init__(self):
        self.h1 = RollingHash(base=131, mod=10**9 + 7)
        self.h2 = RollingHash(base=137, mod=10**9 + 9)

    def match(self, text, pattern):
        s1 = set(self.h1.match(text, pattern))
        s2 = set(self.h2.match(text, pattern))
        return sorted(s1 & s2)


# Demo
rh = RollingHash()
text = "abcabcabcabc"
pattern = "abcabc"
positions = rh.match(text, pattern)
print(f"Pattern found at: {positions}")  # [0, 3, 6]

# Stress test with repeated characters
text2 = "aaaaaa"
pattern2 = "aaa"
print(f"Repeated: {rh.match(text2, pattern2)}")  # [0, 1, 2, 3]

# Double hash
dh = DoubleHash()
print(f"Double hash: {dh.match(text, pattern)}")  # [0, 3, 6]
```

### Complexity
- **Time**: O(n + m) expected, O(n * m) worst case (many collisions)
- **Space**: O(1) extra (excluding output)
- **Collision probability**: ~1/p per window, ~n/p total for single hash
- With double hashing: ~n/p^2, essentially zero for practical inputs

### When to Use
- Multiple pattern search (hash each pattern, store in set)
- 2D pattern matching (hash rows then columns)
- Longest common substring via binary search + hash set'''),

    ("thinking/algorithms", r'''Implement polynomial hashing with the ability to compute hash of any substring in O(1) after O(n) preprocessing. Show how to compare arbitrary substrings efficiently.''', r'''<think>
Polynomial hashing with prefix hashes allows O(1) substring hash queries. The idea: precompute prefix hashes and powers of the base, then extract any substring hash using the formula:

hash(s[l..r]) = (prefix_hash[r+1] - prefix_hash[l] * base^(r-l+1)) mod p

Where prefix_hash[i] = hash of s[0..i-1].

The math: prefix_hash[i] = s[0]*b^(i-1) + s[1]*b^(i-2) + ... + s[i-1]

For substring [l..r]:
hash(s[l..r]) = s[l]*b^(r-l) + s[l+1]*b^(r-l-1) + ... + s[r]
             = prefix_hash[r+1] - prefix_hash[l] * b^(r-l+1)

This is because prefix_hash[r+1] contains terms for positions 0..r, and subtracting prefix_hash[l] * b^(r-l+1) removes the contribution of positions 0..l-1 (shifted appropriately).

I need to precompute the powers array. For comparing substrings from different strings, I can use the same base and modulus. This enables O(1) substring comparison with high probability.

Applications: longest common prefix via binary search, lexicographic comparison, finding repeated substrings.
</think>

## Polynomial Hashing with O(1) Substring Queries

### Implementation

```python
class SubstringHash:
    """Preprocess string for O(1) hash queries on any substring."""

    def __init__(self, s, base=131, mod=10**9 + 7):
        self.s = s
        self.n = len(s)
        self.base = base
        self.mod = mod

        # prefix_hash[i] = hash of s[0..i-1]
        self.prefix = [0] * (self.n + 1)
        for i in range(self.n):
            self.prefix[i + 1] = (
                self.prefix[i] * base + ord(s[i])
            ) % mod

        # Precompute powers: pw[i] = base^i mod p
        self.pw = [1] * (self.n + 1)
        for i in range(1, self.n + 1):
            self.pw[i] = self.pw[i - 1] * base % mod

    def get_hash(self, l, r):
        """Return hash of s[l..r] (inclusive) in O(1)."""
        # hash = prefix[r+1] - prefix[l] * base^(r-l+1)
        length = r - l + 1
        h = (self.prefix[r + 1]
             - self.prefix[l] * self.pw[length]) % self.mod
        return h

    def compare(self, l1, r1, l2, r2):
        """Check if s[l1..r1] == s[l2..r2] via hash."""
        if r1 - l1 != r2 - l2:
            return False
        return self.get_hash(l1, r1) == self.get_hash(l2, r2)

    def lcp(self, i, j):
        """Longest common prefix of suffixes starting at i and j."""
        max_len = min(self.n - i, self.n - j)
        lo, hi = 0, max_len
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.get_hash(i, i + mid - 1) == self.get_hash(j, j + mid - 1):
                lo = mid
            else:
                hi = mid - 1
        return lo


class DoubleSubstringHash:
    """Double hashing for higher reliability."""
    def __init__(self, s):
        self.h1 = SubstringHash(s, base=131, mod=10**9 + 7)
        self.h2 = SubstringHash(s, base=137, mod=10**9 + 9)

    def get_hash(self, l, r):
        return (self.h1.get_hash(l, r), self.h2.get_hash(l, r))

    def compare(self, l1, r1, l2, r2):
        return (self.h1.compare(l1, r1, l2, r2)
                and self.h2.compare(l1, r1, l2, r2))


# Demo
s = "abcabcxyzabc"
sh = SubstringHash(s)

# Compare substrings
print(sh.compare(0, 2, 3, 5))   # "abc" vs "abc" -> True
print(sh.compare(0, 2, 6, 8))   # "abc" vs "xyz" -> False
print(sh.compare(0, 2, 9, 11))  # "abc" vs "abc" -> True

# Longest common prefix
print(sh.lcp(0, 3))  # suffixes "abcabcxyzabc" and "abcxyzabc" -> lcp=3
print(sh.lcp(0, 9))  # suffixes "abcabcxyzabc" and "abc" -> lcp=3

# Find all repeated substrings of length 3
seen = {}
for i in range(len(s) - 2):
    h = sh.get_hash(i, i + 2)
    if h in seen:
        print(f"Repeat: '{s[i:i+3]}' at {seen[h]} and {i}")
    else:
        seen[h] = i
```

### Complexity
- **Preprocessing**: O(n) time and space
- **Query**: O(1) per hash, O(log n) for LCP via binary search
- **Collision probability**: ~1/p per comparison (~10^-9 with good prime)'''),

    ("thinking/algorithms", r'''Build a hash map from scratch in Python (without using dict). Implement open addressing with linear probing, including insert, search, delete, and dynamic resizing. Analyze the expected time complexity.''', r'''<think>
Building a hash map from scratch with open addressing and linear probing. Key design decisions:

1. Hash function: use Python's built-in hash() then reduce modulo table size. Table size should be a prime or power of 2.

2. Linear probing: on collision, check the next slot, then the next, etc. This has the issue of clustering but is cache-friendly.

3. Deletion: cannot simply empty a slot (would break probe chains). Use a sentinel "DELETED" marker. On insert, we can reuse DELETED slots. On search, we skip over them.

4. Dynamic resizing: when load factor exceeds a threshold (say 0.7), double the table size and rehash everything. When load factor drops below 0.2 (after many deletes), shrink.

5. The expected time for operations with load factor alpha:
   - Successful search: O(1/(1-alpha)) on average
   - Unsuccessful search: O(1/(1-alpha)^2) on average
   - This assumes uniform hashing, which linear probing approximates poorly due to clustering

Edge cases: duplicate keys on insert (update value), searching for non-existent keys, resize during iteration, hash of None or unhashable types.

Let me implement this cleanly with proper resize logic.
</think>

## Hash Map from Scratch with Open Addressing

### Implementation

```python
class HashMap:
    """Hash map using open addressing with linear probing."""

    _EMPTY = object()
    _DELETED = object()

    def __init__(self, initial_capacity=8):
        self._capacity = initial_capacity
        self._size = 0
        self._keys = [self._EMPTY] * self._capacity
        self._values = [None] * self._capacity
        self._max_load = 0.7
        self._min_load = 0.2

    def _hash(self, key):
        return hash(key) % self._capacity

    def _probe(self, key):
        """Generate probe sequence starting from hash(key)."""
        idx = self._hash(key)
        for _ in range(self._capacity):
            yield idx
            idx = (idx + 1) % self._capacity

    def put(self, key, value):
        """Insert or update key-value pair."""
        if self._size / self._capacity >= self._max_load:
            self._resize(self._capacity * 2)

        first_deleted = -1
        for idx in self._probe(key):
            if self._keys[idx] is self._EMPTY:
                # Key not found, insert at first available slot
                target = first_deleted if first_deleted >= 0 else idx
                self._keys[target] = key
                self._values[target] = value
                self._size += 1
                return
            elif self._keys[idx] is self._DELETED:
                if first_deleted < 0:
                    first_deleted = idx
            elif self._keys[idx] == key:
                # Key exists, update value
                self._values[idx] = value
                return

        # Should not reach here if load factor < 1
        raise RuntimeError("Hash table is full")

    def get(self, key, default=None):
        """Retrieve value for key, or default if not found."""
        for idx in self._probe(key):
            if self._keys[idx] is self._EMPTY:
                return default
            if self._keys[idx] is not self._DELETED and self._keys[idx] == key:
                return self._values[idx]
        return default

    def remove(self, key):
        """Remove key-value pair. Returns True if found."""
        for idx in self._probe(key):
            if self._keys[idx] is self._EMPTY:
                return False
            if self._keys[idx] is not self._DELETED and self._keys[idx] == key:
                self._keys[idx] = self._DELETED
                self._values[idx] = None
                self._size -= 1
                # Shrink if too sparse
                if (self._capacity > 8
                        and self._size / self._capacity < self._min_load):
                    self._resize(self._capacity // 2)
                return True
        return False

    def _resize(self, new_capacity):
        """Rehash all entries into new table."""
        old_keys = self._keys
        old_values = self._values
        self._capacity = new_capacity
        self._size = 0
        self._keys = [self._EMPTY] * self._capacity
        self._values = [None] * self._capacity
        for k, v in zip(old_keys, old_values):
            if k is not self._EMPTY and k is not self._DELETED:
                self.put(k, v)

    def __contains__(self, key):
        return self.get(key, self._EMPTY) is not self._EMPTY

    def __len__(self):
        return self._size

    def items(self):
        for i in range(self._capacity):
            if (self._keys[i] is not self._EMPTY
                    and self._keys[i] is not self._DELETED):
                yield self._keys[i], self._values[i]


# Test
hm = HashMap()
for i in range(20):
    hm.put(f"key{i}", i * 10)

print(f"Size: {len(hm)}")          # 20
print(f"Get key5: {hm.get('key5')}")  # 50
print(f"Has key10: {'key10' in hm}")   # True

hm.remove("key5")
print(f"After remove: {hm.get('key5')}")  # None
print(f"Size: {len(hm)}")                  # 19

# Update existing key
hm.put("key0", 999)
print(f"Updated key0: {hm.get('key0')}")  # 999
```

### Complexity (with load factor alpha < 0.7)
| Operation | Average | Worst |
|-----------|---------|-------|
| Insert    | O(1)    | O(n)  |
| Search    | O(1)    | O(n)  |
| Delete    | O(1)    | O(n)  |
| Resize    | O(n) amortized over n insertions |

Linear probing suffers from **primary clustering** but has excellent cache locality, often making it faster in practice than chaining despite theoretical disadvantages.'''),

    ("thinking/algorithms", r'''Implement consistent hashing for distributed systems. Show the ring-based approach with virtual nodes, supporting add/remove servers and key lookup. Explain why it minimizes key redistribution.''', r'''<think>
Consistent hashing maps both keys and servers onto a circular hash space (ring). Each key is assigned to the nearest server clockwise on the ring. When a server is added or removed, only keys between the affected server and its predecessor need to move.

Virtual nodes: each physical server gets multiple positions on the ring (virtual nodes). This improves load balancing because with few physical servers, the ring partitions can be very uneven. With V virtual nodes per server, the standard deviation of load drops from O(1/sqrt(n)) to O(1/sqrt(n*V)).

Implementation:
1. Use a sorted list (or balanced BST) of hash positions on the ring
2. Each position maps to a physical server
3. For key lookup: hash the key, find the next position on the ring (binary search)
4. For add server: insert V virtual nodes, keys in affected ranges migrate
5. For remove server: remove V virtual nodes, keys go to next server

I will use Python's bisect module for efficient sorted list operations. The hash function should be uniform -- I will use hashlib for consistent hashing across machines (Python's hash() is not deterministic across runs).

For the redistribution analysis: with n servers, adding one new server only moves ~1/n of the keys. Compare with simple modular hashing where adding a server moves ~(n-1)/n keys.
</think>

## Consistent Hashing with Virtual Nodes

### Implementation

```python
import hashlib
import bisect


class ConsistentHash:
    """Consistent hashing ring with virtual nodes."""

    def __init__(self, num_virtual=150):
        self.num_virtual = num_virtual
        self.ring = []          # sorted list of hash positions
        self.ring_map = {}      # hash position -> server name
        self.servers = set()

    def _hash(self, key):
        """Deterministic hash using MD5 (consistent across runs)."""
        digest = hashlib.md5(key.encode()).hexdigest()
        return int(digest, 16)

    def add_server(self, server):
        """Add a server with virtual nodes to the ring."""
        if server in self.servers:
            return
        self.servers.add(server)
        for i in range(self.num_virtual):
            vnode_key = f"{server}#vnode{i}"
            h = self._hash(vnode_key)
            bisect.insort(self.ring, h)
            self.ring_map[h] = server

    def remove_server(self, server):
        """Remove a server and all its virtual nodes."""
        if server not in self.servers:
            return
        self.servers.discard(server)
        new_ring = []
        for h in self.ring:
            if self.ring_map[h] == server:
                del self.ring_map[h]
            else:
                new_ring.append(h)
        self.ring = new_ring

    def get_server(self, key):
        """Find which server a key maps to."""
        if not self.ring:
            return None
        h = self._hash(key)
        idx = bisect.bisect_right(self.ring, h)
        if idx == len(self.ring):
            idx = 0  # wrap around the ring
        return self.ring_map[self.ring[idx]]

    def get_distribution(self, keys):
        """Show how keys distribute across servers."""
        dist = {}
        for k in keys:
            server = self.get_server(k)
            dist[server] = dist.get(server, 0) + 1
        return dist


# Demo
ch = ConsistentHash(num_virtual=150)
ch.add_server("server-A")
ch.add_server("server-B")
ch.add_server("server-C")

# Distribute 1000 keys
keys = [f"user:{i}" for i in range(1000)]
dist = ch.get_distribution(keys)
print("Distribution with 3 servers:")
for s, count in sorted(dist.items()):
    print(f"  {s}: {count} keys ({count/10:.1f}%)")

# Record assignments before adding server
before = {k: ch.get_server(k) for k in keys}

# Add a new server
ch.add_server("server-D")
after = {k: ch.get_server(k) for k in keys}

moved = sum(1 for k in keys if before[k] != after[k])
print(f"\nAfter adding server-D:")
print(f"  Keys moved: {moved}/1000 ({moved/10:.1f}%)")
print(f"  Expected: ~{1000//4} (1/4 of keys)")

dist2 = ch.get_distribution(keys)
for s, count in sorted(dist2.items()):
    print(f"  {s}: {count} keys ({count/10:.1f}%)")
```

### Why Minimal Redistribution?
- With modular hashing (`server = hash(key) % n`), changing n moves **~(n-1)/n** keys
- With consistent hashing, adding 1 server to n servers moves only **~1/(n+1)** keys
- Each new server only "steals" keys from its immediate neighbors on the ring

### Complexity
- **Add/Remove server**: O(V * log(n*V)) where V = virtual nodes per server
- **Key lookup**: O(log(n*V)) via binary search
- **Space**: O(n*V) for the ring

### Virtual Nodes Trade-off
| Virtual Nodes | Load Balance | Memory | Lookup Speed |
|--------------|-------------|--------|-------------|
| 1            | Poor        | Low    | Fast        |
| 50-200       | Good        | Medium | Fast        |
| 1000+        | Excellent   | High   | Slightly slower |'''),

    ("thinking/algorithms", r'''Implement cuckoo hashing with two hash functions and two tables. Explain the insertion algorithm with eviction chains, detect cycles, and handle rehashing. Compare with other collision resolution strategies.''', r'''<think>
Cuckoo hashing uses two (or more) hash tables, each with its own hash function. Every key has exactly two possible positions: h1(key) in table1, h2(key) in table2. Lookup is O(1) worst case because we check exactly two positions.

Insertion algorithm:
1. Try to place key in table1[h1(key)]
2. If occupied, evict the existing key and place new key there
3. The evicted key goes to its alternate position (in the other table)
4. If that position is also occupied, evict again
5. Continue until we find an empty slot or detect a cycle

Cycle detection: if we evict more than some threshold (typically 6*log(n) or just a constant like the table size), we assume a cycle and trigger a rehash with new hash functions.

Rehashing: choose new hash functions and reinsert all keys. With random hash functions, the probability of needing a rehash is low when load factor < 0.5 (per table), giving an overall load factor < 1.0.

The amortized insertion cost is O(1) assuming good hash functions. The worst case for a single insertion before rehash is O(n), but rehashing itself is O(n), and it happens rarely.

For implementation, I will use two separate arrays and two hash functions (parameterized by different salts). I will track the eviction chain to detect cycles.
</think>

## Cuckoo Hashing

Guarantees O(1) worst-case lookup by maintaining two tables with two hash functions.

### Implementation

```python
import random


class CuckooHashMap:
    """Cuckoo hashing with two tables and automatic rehashing."""

    def __init__(self, capacity=16):
        self._cap = capacity
        self._size = 0
        self._table1 = [None] * self._cap  # entries: (key, value) or None
        self._table2 = [None] * self._cap
        self._salt1 = random.randint(1, 10**9)
        self._salt2 = random.randint(1, 10**9)
        self._max_evictions = 20

    def _h1(self, key):
        return hash((key, self._salt1)) % self._cap

    def _h2(self, key):
        return hash((key, self._salt2)) % self._cap

    def get(self, key, default=None):
        """O(1) worst-case lookup."""
        idx1 = self._h1(key)
        if self._table1[idx1] is not None and self._table1[idx1][0] == key:
            return self._table1[idx1][1]
        idx2 = self._h2(key)
        if self._table2[idx2] is not None and self._table2[idx2][0] == key:
            return self._table2[idx2][1]
        return default

    def __contains__(self, key):
        sentinel = object()
        return self.get(key, sentinel) is not sentinel

    def remove(self, key):
        """O(1) worst-case deletion."""
        idx1 = self._h1(key)
        if self._table1[idx1] is not None and self._table1[idx1][0] == key:
            self._table1[idx1] = None
            self._size -= 1
            return True
        idx2 = self._h2(key)
        if self._table2[idx2] is not None and self._table2[idx2][0] == key:
            self._table2[idx2] = None
            self._size -= 1
            return True
        return False

    def put(self, key, value):
        """Insert with eviction chain."""
        # Check if key already exists
        idx1 = self._h1(key)
        if self._table1[idx1] is not None and self._table1[idx1][0] == key:
            self._table1[idx1] = (key, value)
            return
        idx2 = self._h2(key)
        if self._table2[idx2] is not None and self._table2[idx2][0] == key:
            self._table2[idx2] = (key, value)
            return

        # Resize if load factor too high
        if self._size >= self._cap:
            self._rehash(self._cap * 2)

        entry = (key, value)
        for _ in range(self._max_evictions):
            # Try table 1
            idx1 = self._h1(entry[0])
            if self._table1[idx1] is None:
                self._table1[idx1] = entry
                self._size += 1
                return
            # Evict from table 1
            entry, self._table1[idx1] = self._table1[idx1], entry

            # Try table 2
            idx2 = self._h2(entry[0])
            if self._table2[idx2] is None:
                self._table2[idx2] = entry
                self._size += 1
                return
            # Evict from table 2
            entry, self._table2[idx2] = self._table2[idx2], entry

        # Cycle detected, rehash with new functions
        self._rehash(self._cap * 2)
        self.put(entry[0], entry[1])

    def _rehash(self, new_cap):
        """Rehash all entries with new hash functions."""
        old1, old2 = self._table1, self._table2
        self._cap = new_cap
        self._size = 0
        self._table1 = [None] * self._cap
        self._table2 = [None] * self._cap
        self._salt1 = random.randint(1, 10**9)
        self._salt2 = random.randint(1, 10**9)
        for table in (old1, old2):
            for entry in table:
                if entry is not None:
                    self.put(entry[0], entry[1])

    def __len__(self):
        return self._size


# Test
ck = CuckooHashMap()
for i in range(50):
    ck.put(f"k{i}", i)

print(f"Size: {len(ck)}")           # 50
print(f"Get k25: {ck.get('k25')}")  # 25
print(f"Has k10: {'k10' in ck}")    # True

ck.remove("k10")
print(f"After remove: {'k10' in ck}")  # False
```

### Comparison of Collision Resolution Strategies
| Method          | Lookup  | Insert (amort.) | Cache  | Load Factor |
|----------------|---------|----------------|--------|------------|
| Chaining       | O(1+a)  | O(1)           | Poor   | Can exceed 1 |
| Linear Probing | O(1/(1-a)) | O(1/(1-a))  | Great  | < 1        |
| Cuckoo         | O(1)    | O(1) amortized | Good   | < 0.5/table |

Cuckoo hashing is ideal when **worst-case lookup time matters** (hardware, real-time systems).'''),
]
