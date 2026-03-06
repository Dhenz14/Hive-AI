PAIRS = [
    ("thinking/algorithms", r'''Implement rolling hash (Rabin-Karp) for substring matching. Explain the math behind it, how to handle hash collisions, and demonstrate finding all occurrences of a pattern in a text.''', r'''<think>
Rolling hash is the foundation of Rabin-Karp string matching. The naive approach would recompute the hash from scratch for each window position, but that costs O(m) per window. Could we do better? Yes -- by treating the string as a polynomial in some base, we can update the hash in O(1) as the window slides.

For string s[0..m-1], hash = s[0]*base^(m-1) + s[1]*base^(m-2) + ... + s[m-1], all mod some large prime. When sliding from position i to i+1, we subtract the contribution of s[i] and add s[i+m]:
new_hash = (old_hash - s[i] * base^(m-1)) * base + s[i+m], all mod p.

Now, choosing the right parameters matters more than I initially thought. I considered using a small prime modulus for speed, but actually that leads to frequent collisions. With mod = 10^9 + 7, the collision probability per window is roughly 1/(10^9), which is negligible for practical inputs. The base should be larger than the alphabet size -- I initially considered base=26 for lowercase letters, but wait, that would map 'a'*base + 'b' the same as some other combination. Using 131 or 256 avoids this ambiguity.

One subtle pitfall: the subtraction in the rolling formula can produce negative values. In Python, the % operator handles this correctly (always returns non-negative), but in C/Java you must add the modulus explicitly. I almost forgot about this.

For multiple pattern matching, we can use double hashing -- two independent hash functions with different bases and moduli. The probability of a false positive drops from 1/p to 1/(p1*p2), which is essentially zero. I considered whether we still need string verification with double hashing. Technically yes for correctness guarantees, but in practice the collision probability is so low that many implementations skip it.

Edge cases to handle: empty pattern, pattern longer than text, all characters the same (where poor hash parameters could cause every window to collide).
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
Polynomial hashing with prefix hashes allows O(1) substring hash queries. But how? My first idea was to store hashes for every possible substring, but that would require O(n^2) space. Instead, we precompute prefix hashes and extract any substring hash using subtraction.

The formula: hash(s[l..r]) = (prefix_hash[r+1] - prefix_hash[l] * base^(r-l+1)) mod p, where prefix_hash[i] = hash of s[0..i-1].

Wait, why does this subtraction work? Let me think through the math carefully. prefix_hash[i] = s[0]*b^(i-1) + s[1]*b^(i-2) + ... + s[i-1]. For substring [l..r], we want s[l]*b^(r-l) + ... + s[r]. Now prefix_hash[r+1] contains all terms for positions 0..r, and prefix_hash[l] * b^(r-l+1) contains all terms for positions 0..l-1 but shifted by b^(r-l+1) to align the powers correctly. Subtracting removes the prefix contribution. Hmm, I initially got the power exponent wrong -- it is (r-l+1), not (r-l), because we need to shift by the length of the substring.

I need to precompute the powers array to avoid recalculating base^k each query. One subtle issue: the subtraction can go negative in modular arithmetic. In Python this is fine since % always returns non-negative, but it is a common source of bugs in other languages.

For comparing substrings from different strings, I considered building separate hash structures and comparing across them. Actually, as long as both use the same base and modulus, we can directly compare hash values. This enables O(1) substring equality testing with collision probability roughly 1/p per comparison.

Applications: longest common prefix via binary search (O(log n) per query), lexicographic comparison of substrings, and finding all repeated substrings of a given length. The binary search for LCP works because "the first k characters match" is a monotonic property -- if they match for length k, they match for all shorter lengths too.
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
Building a hash map from scratch with open addressing. My first decision: which collision resolution? I considered chaining (linked lists at each slot), but open addressing with linear probing is more cache-friendly since probes hit adjacent memory locations. The tradeoff is that linear probing suffers from primary clustering -- runs of occupied slots grow and merge, making future collisions more likely.

Hash function: use Python's built-in hash() then reduce modulo table size. I considered using a prime table size to reduce clustering, but powers of 2 are simpler and Python's hash() already has good distribution. Actually, for linear probing specifically, prime sizes might help more than for chaining, but I will keep it simple with powers of 2.

Deletion is trickier than I initially thought. I cannot simply empty a slot because that would break probe chains -- a later search would stop at the empty slot and miss elements that were inserted after the deleted one. Wait, could I re-insert all elements in the broken chain? That would work but is complex. The simpler approach is a sentinel "DELETED" marker: on insert, we can reuse DELETED slots; on search, we skip over them.

Dynamic resizing: when load factor exceeds 0.7, double and rehash. But hmm, what about shrinking? After many deletes, the table could be mostly DELETED markers, which degrades probe length. So I should also shrink when load factor drops below 0.2 (but never below a minimum capacity of 8 to avoid thrashing on small tables).

Expected probe lengths with load factor alpha:
- Successful search: O(1/(1-alpha)) on average
- Unsuccessful search: O(1/(1-alpha)^2) on average
These assume uniform hashing; linear probing is somewhat worse in practice due to clustering, but the cache locality often compensates.
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
Consistent hashing maps both keys and servers onto a circular hash space (ring). Each key goes to the nearest server clockwise. The key advantage over simple modular hashing (key % n): when a server is added or removed, only keys between the affected server and its predecessor need to move -- roughly 1/n of all keys, not (n-1)/n.

But wait, with just a few physical servers, the ring partitions can be very uneven. I initially thought we could just hash each server name to one position, but that gives poor load balancing with small n. For example, with 3 servers, one might end up with 60% of the ring arc. Virtual nodes fix this: each physical server gets V positions on the ring (e.g., V=150). With more points, the law of large numbers kicks in and the standard deviation of load drops from O(1/sqrt(n)) to O(1/sqrt(n*V)).

Implementation decisions:
- I considered using a balanced BST for the ring, but Python's bisect module on a sorted list is simpler and gives O(log(n*V)) lookup via binary search. Good enough.
- For the hash function, I initially thought to use Python's hash(), but actually that is not deterministic across runs (Python randomizes hash seeds for security). Since consistent hashing in distributed systems requires all nodes to agree on the same hash, I should use hashlib (MD5 or SHA) instead. The cryptographic strength is overkill, but determinism across machines is essential.

For key lookup: hash the key, use bisect_right to find the next position on the ring, wrap around if past the end. For add/remove server: insert/remove V virtual node positions.

Hmm, one thing I considered: should removed keys be actively migrated or lazily discovered? In practice (e.g., Redis Cluster), migration happens actively in the background, but for this implementation the ring lookup handles it transparently -- keys simply map to a different server after the topology changes.
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
Cuckoo hashing gives O(1) worst-case lookup -- not amortized, actual worst case. That is remarkable compared to chaining or linear probing where worst case is O(n). The trick: every key has exactly two possible positions (h1(key) in table1, h2(key) in table2), so lookup checks at most two slots.

The insertion algorithm is where it gets interesting. I initially thought we could just try both positions and fail if both are occupied. But actually, cuckoo hashing uses eviction: place the new key in table1[h1(key)], evicting whatever was there. The evicted key then goes to its alternate position in the other table. If that is also occupied, evict again. This chain continues until we find an empty slot.

But wait -- what if we enter a cycle? For example, key A evicts key B, which evicts key C, which evicts key A again. We would loop forever. So we need cycle detection: if we exceed a threshold number of evictions (I considered using the table size, but 6*log(n) or even a small constant like 20 works well in practice), we assume a cycle and trigger a rehash with completely new hash functions.

Rehashing: choose new random salts for both hash functions and reinsert everything. Could this also cycle? Yes, but the probability is low -- with random hash functions and load factor below 0.5 per table, the expected number of rehashes before success is O(1). Hmm, but in the worst case we might need multiple rehash attempts. In practice this almost never happens.

One design tradeoff I considered: using three hash functions and three tables instead of two. This raises the achievable load factor from ~50% to ~91%, at the cost of checking three positions per lookup instead of two. For most applications, two tables with 50% load is acceptable.

For implementation, I will use two arrays and two hash functions parameterized by different random salts. The eviction chain is tracked to detect cycles.
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
