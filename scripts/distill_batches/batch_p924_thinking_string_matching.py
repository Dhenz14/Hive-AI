PAIRS = [
    ("thinking/algorithms", r'''Implement the KMP (Knuth-Morris-Pratt) string matching algorithm. Explain the failure function (partial match table) and how it enables O(n+m) pattern matching.''', r'''<think>
The KMP algorithm matches a pattern P against a text T in O(n+m) time, where n = len(T) and m = len(P). The key innovation is the failure function (also called the prefix function or partial match table), which tells us how to skip ahead on mismatches without rechecking characters.

Failure function lps[i] = length of the longest proper prefix of P[0..i] that is also a suffix of P[0..i].

Example: P = "ABABC"
- lps[0] = 0 (single char, no proper prefix)
- lps[1] = 0 ("AB" -- no prefix equals suffix)
- lps[2] = 1 ("ABA" -- "A" is both prefix and suffix)
- lps[3] = 2 ("ABAB" -- "AB" is both prefix and suffix)
- lps[4] = 0 ("ABABC" -- no match)

How KMP uses the failure function:
- When matching P[j] against T[i], if mismatch:
  - Instead of resetting j to 0 (like naive), set j = lps[j-1]
  - This skips re-examining characters we already know match
  - The prefix P[0..lps[j-1]-1] is known to match the text at current position

Why it is O(n+m):
- Building the failure function: O(m)
- Searching: i never goes backwards, and j can decrease at most as many times as it increases
- Total pointer movements bounded by O(n+m)

Building the failure function uses the same logic as the search itself -- it is essentially matching the pattern against itself.

Edge cases:
- Pattern longer than text
- Pattern not found
- Multiple occurrences
- Pattern is a single character
- Pattern equals text
- Pattern has all same characters ("AAAA")
</think>

**KMP String Matching Algorithm**

```python
def compute_lps(pattern):
    """
    Compute the Longest Proper Prefix which is also Suffix (LPS) array.

    lps[i] = length of longest proper prefix of pattern[0..i]
             that is also a suffix.

    Args:
        pattern: the pattern string
    Returns:
        lps array
    """
    m = len(pattern)
    lps = [0] * m
    length = 0  # length of previous longest prefix suffix
    i = 1

    while i < m:
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            i += 1
        else:
            if length != 0:
                # Fall back using the lps table
                length = lps[length - 1]
            else:
                lps[i] = 0
                i += 1

    return lps


def kmp_search(text, pattern):
    """
    Find all occurrences of pattern in text using KMP.

    Args:
        text: the text to search in
        pattern: the pattern to search for
    Returns:
        list of starting indices of matches
    """
    n, m = len(text), len(pattern)
    if m == 0:
        return []

    lps = compute_lps(pattern)
    matches = []

    i = 0  # index in text
    j = 0  # index in pattern

    while i < n:
        if text[i] == pattern[j]:
            i += 1
            j += 1

            if j == m:
                matches.append(i - m)
                j = lps[j - 1]
        else:
            if j != 0:
                j = lps[j - 1]
            else:
                i += 1

    return matches


# Example
text = "ABABDABACDABABCABAB"
pattern = "ABABCABAB"

lps = compute_lps(pattern)
matches = kmp_search(text, pattern)

print(f"Text:    {text}")
print(f"Pattern: {pattern}")
print(f"LPS:     {lps}")
print(f"Matches at indices: {matches}")

for idx in matches:
    print(f"  {' ' * idx}{pattern}")

# More examples
examples = [
    ("AAAAAA", "AA"),
    ("abcxabcdabcdabcy", "abcdabcy"),
    ("hello world", "xyz"),
    ("aabaabaaab", "aab"),
]

for t, p in examples:
    result = kmp_search(t, p)
    print(f"\n  text='{t}' pattern='{p}'")
    print(f"  LPS={compute_lps(p)} matches={result}")
```

**LPS Construction Trace for "ABABCABAB":**
```
i=1: B vs A -> lps[1]=0
i=2: A vs A -> lps[2]=1
i=3: B vs B -> lps[3]=2
i=4: C vs A -> fall back, C vs _ -> lps[4]=0
i=5: A vs A -> lps[5]=1
i=6: B vs B -> lps[6]=2
i=7: A vs A -> lps[7]=3
i=8: B vs B -> lps[8]=4
LPS = [0, 0, 1, 2, 0, 1, 2, 3, 4]
```

**Complexity:**
- LPS computation: O(m)
- Search: O(n)
- Total: O(n + m) time, O(m) space'''),

    ("thinking/algorithms", r'''Implement the Rabin-Karp string matching algorithm using rolling hash. Explain the hash function design and how to handle hash collisions.''', r'''<think>
Rabin-Karp uses hashing to speed up string matching. Instead of comparing characters one by one, it compares hash values. If hashes match, verify with actual string comparison to handle collisions.

Rolling hash concept:
- Treat the string as a number in base d (d = alphabet size)
- hash("abc") = a * d^2 + b * d^1 + c * d^0, all mod q (a large prime)
- When sliding the window by one position:
  hash_new = (d * (hash_old - text[i] * d^(m-1)) + text[i+m]) mod q

This allows updating the hash in O(1) when the window slides, instead of O(m) recomputation.

Hash function design:
- Base d: typically 256 (for ASCII) or a prime like 31
- Modulus q: a large prime (e.g., 10^9 + 7) to minimize collisions
- The probability of a spurious hit (collision) is approximately 1/q per position

Algorithm:
1. Compute hash of pattern and hash of first window in text
2. Slide window through text:
   a. If hashes match, verify by comparing actual strings
   b. Update hash using rolling formula
3. Return all verified match positions

Multiple pattern search: Rabin-Karp extends naturally to searching for multiple patterns simultaneously by storing all pattern hashes in a set.

Time complexity:
- Average case: O(n + m)
- Worst case: O(n * m) if all hashes collide (extremely unlikely with good hash)
- Multiple patterns: O(n * k + sum(m_i)) average, where k = number of patterns

Edge cases:
- Pattern longer than text
- Negative hash values (ensure proper modular arithmetic)
- Single character pattern
</think>

**Rabin-Karp String Matching with Rolling Hash**

```python
def rabin_karp(text, pattern, base=256, mod=1000000007):
    """
    Find all occurrences of pattern in text using Rabin-Karp.

    Args:
        text: search text
        pattern: pattern to find
        base: hash base (alphabet size)
        mod: hash modulus (large prime)
    Returns:
        list of starting indices of matches
    """
    n, m = len(text), len(pattern)
    if m > n or m == 0:
        return []

    # Precompute base^(m-1) mod q
    h = pow(base, m - 1, mod)

    # Compute initial hashes
    p_hash = 0  # pattern hash
    t_hash = 0  # text window hash

    for i in range(m):
        p_hash = (base * p_hash + ord(pattern[i])) % mod
        t_hash = (base * t_hash + ord(text[i])) % mod

    matches = []

    for i in range(n - m + 1):
        # Check hash match
        if p_hash == t_hash:
            # Verify actual match (avoid false positive from collision)
            if text[i:i + m] == pattern:
                matches.append(i)

        # Roll hash to next window
        if i < n - m:
            t_hash = (base * (t_hash - ord(text[i]) * h) +
                       ord(text[i + m])) % mod
            # Ensure non-negative
            if t_hash < 0:
                t_hash += mod

    return matches


def rabin_karp_multi(text, patterns, base=256, mod=1000000007):
    """
    Search for multiple patterns simultaneously.

    Args:
        text: search text
        patterns: list of patterns (all same length for simplicity)
    Returns:
        dict mapping pattern -> list of match positions
    """
    if not patterns:
        return {}

    n = len(text)
    results = {p: [] for p in patterns}

    # Group patterns by length
    by_length = {}
    for p in patterns:
        by_length.setdefault(len(p), []).append(p)

    for m, pats in by_length.items():
        if m > n:
            continue

        # Compute pattern hashes
        pat_hashes = {}
        for p in pats:
            h = 0
            for c in p:
                h = (base * h + ord(c)) % mod
            pat_hashes.setdefault(h, []).append(p)

        # Sliding window
        h_pow = pow(base, m - 1, mod)
        t_hash = 0
        for i in range(m):
            t_hash = (base * t_hash + ord(text[i])) % mod

        for i in range(n - m + 1):
            if t_hash in pat_hashes:
                for p in pat_hashes[t_hash]:
                    if text[i:i + m] == p:
                        results[p].append(i)

            if i < n - m:
                t_hash = (base * (t_hash - ord(text[i]) * h_pow) +
                           ord(text[i + m])) % mod
                if t_hash < 0:
                    t_hash += mod

    return results


# Example
text = "AABAACAADAABAABA"
pattern = "AABA"

matches = rabin_karp(text, pattern)
print(f"Text:    {text}")
print(f"Pattern: {pattern}")
print(f"Matches: {matches}")

# Multi-pattern search
patterns = ["AABA", "AACA", "AADA"]
results = rabin_karp_multi(text, patterns)
print(f"\nMulti-pattern search:")
for p, indices in results.items():
    print(f"  '{p}': {indices}")

# Collision analysis
import random
random.seed(42)
text2 = "".join(random.choice("ABCD") for _ in range(10000))
pattern2 = "ABCD" * 3
m2 = rabin_karp(text2, pattern2)
print(f"\nRandom text search: found {len(m2)} matches of '{pattern2}'")
```

**Rolling Hash Formula:**
```
Initial: hash = s[0]*d^(m-1) + s[1]*d^(m-2) + ... + s[m-1]
Roll:    hash = d * (hash - s[i]*d^(m-1)) + s[i+m]
All operations mod q
```

**Complexity:**
- Average: O(n + m) per pattern
- Worst case: O(n * m) due to hash collisions (rare with good prime)
- Multi-pattern: O(n * k + sum of pattern lengths) average
- Space: O(m) for hash computation'''),

    ("thinking/algorithms", r'''Implement the Z-algorithm for string matching: compute the Z-array where Z[i] is the length of the longest substring starting at position i that matches a prefix of the string. Show how to use it for pattern matching.''', r'''<think>
The Z-algorithm computes the Z-array for a string S, where Z[i] is the length of the longest substring starting at i that matches a prefix of S. Z[0] is undefined (or set to 0/n by convention).

The algorithm runs in O(n) using a "Z-box" window [l, r] that tracks the rightmost interval matching a prefix:

1. Initialize l = r = 0, Z[0] = 0 (or n)
2. For each i from 1 to n-1:
   a. If i < r: Z[i] = min(r - i, Z[i - l]) (copy from previously computed)
   b. Extend Z[i] by comparing characters while they match
   c. If i + Z[i] > r: update l = i, r = i + Z[i]

The key insight: if i is inside a previously found Z-box [l, r], then S[i..r-1] matches S[i-l..r-l-1]. So Z[i] >= min(r-i, Z[i-l]). If Z[i-l] < r-i, we know the exact value without extension.

For pattern matching:
1. Concatenate: combined = pattern + "$" + text ($ is a separator not in the alphabet)
2. Compute Z-array of combined
3. Pattern occurs at position i in text whenever Z[m+1+i] == m (where m = len(pattern))

Why this works: Z[m+1+i] gives the longest prefix of combined matching at that position. If it equals m, the entire pattern matches at that position in the text.

Time: O(n+m) -- Z-array computation is O(n) amortized because the right boundary r only moves right.
Space: O(n+m) for the Z-array.
</think>

**Z-Algorithm for String Matching**

```python
def z_array(s):
    """
    Compute the Z-array for string s.

    Z[i] = length of longest substring starting at i
           that matches a prefix of s.

    Args:
        s: input string
    Returns:
        Z-array (Z[0] = 0 by convention)
    """
    n = len(s)
    if n == 0:
        return []

    z = [0] * n
    z[0] = n  # some implementations set this to 0

    l, r = 0, 0  # Z-box window [l, r)

    for i in range(1, n):
        if i < r:
            # Inside Z-box: copy from previously computed value
            z[i] = min(r - i, z[i - l])

        # Try to extend
        while i + z[i] < n and s[z[i]] == s[i + z[i]]:
            z[i] += 1

        # Update Z-box if we extended past r
        if i + z[i] > r:
            l, r = i, i + z[i]

    return z


def z_search(text, pattern):
    """
    Find all occurrences of pattern in text using Z-algorithm.

    Args:
        text: search text
        pattern: pattern to find
    Returns:
        list of starting indices in text where pattern occurs
    """
    m = len(pattern)
    if m == 0:
        return []

    # Use a character not in either string as separator
    combined = pattern + "$" + text
    z = z_array(combined)

    matches = []
    for i in range(m + 1, len(combined)):
        if z[i] == m:
            matches.append(i - m - 1)

    return matches


# Example: Z-array computation
s = "aabxaab"
z = z_array(s)
print(f"String: {s}")
print(f"Z-array: {z}")
print(f"Explanation:")
for i in range(len(s)):
    if z[i] > 0 and i > 0:
        matched = s[i:i+z[i]]
        print(f"  Z[{i}]={z[i]}: '{matched}' matches prefix '{s[:z[i]]}'")

# Pattern matching
text = "AABAACAADAABAABA"
pattern = "AABA"

matches = z_search(text, pattern)
print(f"\nText:    {text}")
print(f"Pattern: {pattern}")
print(f"Matches at: {matches}")

# Visualize
combined = pattern + "$" + text
z_combined = z_array(combined)
print(f"\nCombined: {combined}")
print(f"Z-array:  {z_combined}")
print(f"Pattern length m={len(pattern)}")
print("Positions where Z[i]==m:")
for i in range(len(pattern)+1, len(combined)):
    if z_combined[i] == len(pattern):
        text_pos = i - len(pattern) - 1
        print(f"  Z[{i}]={z_combined[i]} -> text position {text_pos}")

# Another example
s2 = "aaaaa"
print(f"\nZ-array of '{s2}': {z_array(s2)}")

s3 = "abcabcabc"
print(f"Z-array of '{s3}': {z_array(s3)}")
```

**Z-Box Optimization:**
- [l, r) tracks the rightmost interval where s[l..r-1] = s[0..r-l-1]
- When i < r, we can "copy" z[i-l] because the substring at i mirrors the one at i-l
- Extension only happens when we go beyond r, and r only increases
- This gives amortized O(n) -- each character position is extended at most once

**Complexity:**
- Z-array computation: O(n) time, O(n) space
- Pattern matching: O(n + m) time, O(n + m) space
- Comparable to KMP but sometimes easier to understand'''),

    ("thinking/algorithms", r'''Implement the Aho-Corasick algorithm for multi-pattern string matching: given a set of patterns and a text, find all occurrences of any pattern in the text simultaneously.''', r'''<think>
Aho-Corasick is the standard algorithm for searching multiple patterns simultaneously. It combines a Trie with failure links (similar to KMP's failure function) and dictionary suffix links.

Construction:
1. Build a Trie from all patterns
2. Compute failure links using BFS:
   - Root's failure link points to root
   - For each node u with child c on character ch:
     - Follow failure links from u until we find one with a child on ch
     - That child is the failure link target for c
3. Compute dictionary suffix links (output links):
   - For each node, the dict link points to the nearest ancestor (via failure links) that is a pattern end

Search:
1. Start at the root
2. For each character in text:
   a. Follow failure links until we find a node with a transition on this character (or reach root)
   b. Move to that child
   c. Follow dictionary suffix links from the current node to report all matching patterns

Time complexity:
- Construction: O(sum of pattern lengths * alphabet_size) for naive, O(sum of pattern lengths) with careful implementation
- Search: O(text_length + number_of_matches)
- Total: O(n + m + z) where n = text length, m = sum of pattern lengths, z = number of matches

This is the foundation of tools like grep (for multiple patterns) and intrusion detection systems.
</think>

**Aho-Corasick Multi-Pattern Matching**

```python
from collections import deque, defaultdict


class AhoCorasick:
    """Aho-Corasick automaton for multi-pattern matching."""

    def __init__(self):
        # Each node: {char: child_index}
        self.goto = [{}]
        self.fail = [0]
        self.output = [[]]  # list of pattern indices at each node
        self.dict_link = [0]  # dictionary suffix link

    def add_pattern(self, pattern, pattern_id):
        """Add a pattern to the automaton."""
        node = 0
        for ch in pattern:
            if ch not in self.goto[node]:
                self.goto[node][ch] = len(self.goto)
                self.goto.append({})
                self.fail.append(0)
                self.output.append([])
                self.dict_link.append(0)
            node = self.goto[node][ch]
        self.output[node].append(pattern_id)

    def build(self):
        """Build failure links and dictionary suffix links using BFS."""
        queue = deque()

        # Initialize: children of root have fail link to root
        for ch, child in self.goto[0].items():
            self.fail[child] = 0
            queue.append(child)

        # BFS to compute failure links
        while queue:
            u = queue.popleft()

            for ch, v in self.goto[u].items():
                queue.append(v)

                # Compute fail[v]: follow fail links from u
                f = self.fail[u]
                while f != 0 and ch not in self.goto[f]:
                    f = self.fail[f]
                self.fail[v] = self.goto[f].get(ch, 0)
                if self.fail[v] == v:
                    self.fail[v] = 0

                # Dictionary suffix link
                if self.output[self.fail[v]]:
                    self.dict_link[v] = self.fail[v]
                else:
                    self.dict_link[v] = self.dict_link[self.fail[v]]

    def search(self, text):
        """
        Search text for all pattern occurrences.

        Returns:
            list of (position, pattern_id) tuples
        """
        results = []
        node = 0

        for i, ch in enumerate(text):
            # Follow failure links until match or root
            while node != 0 and ch not in self.goto[node]:
                node = self.fail[node]

            node = self.goto[node].get(ch, 0)

            # Report matches at this node and via dict links
            temp = node
            while temp != 0:
                for pid in self.output[temp]:
                    results.append((i, pid))
                temp = self.dict_link[temp]

        return results


# Example
patterns = ["he", "she", "his", "hers"]
text = "ahishers"

ac = AhoCorasick()
for i, p in enumerate(patterns):
    ac.add_pattern(p, i)
ac.build()

matches = ac.search(text)

print(f"Text: '{text}'")
print(f"Patterns: {patterns}")
print(f"\nMatches found:")
for end_pos, pid in sorted(matches):
    p = patterns[pid]
    start = end_pos - len(p) + 1
    print(f"  '{p}' at position {start} (ends at {end_pos})")

# Visualize matches
print(f"\n  {text}")
for end_pos, pid in sorted(matches):
    p = patterns[pid]
    start = end_pos - len(p) + 1
    print(f"  {' '*start}{'^'*len(p)} '{p}'")

# Larger example
patterns2 = ["AB", "BC", "ABC", "BCA"]
text2 = "ABCABCABCA"
ac2 = AhoCorasick()
for i, p in enumerate(patterns2):
    ac2.add_pattern(p, i)
ac2.build()

matches2 = ac2.search(text2)
print(f"\nText: '{text2}'")
for end_pos, pid in sorted(matches2):
    p = patterns2[pid]
    start = end_pos - len(p) + 1
    print(f"  '{p}' at position {start}")
```

**Failure Links = "KMP for Tries":**
- In KMP, the failure function tells where to resume on mismatch
- In Aho-Corasick, failure links serve the same purpose across multiple patterns
- The failure link of node u points to the longest proper suffix of u's string that is also a prefix in the Trie

**Complexity:**
- Build: O(sum of pattern lengths)
- Search: O(text_length + number_of_matches)
- Space: O(sum of pattern lengths * alphabet_size)'''),

    ("thinking/algorithms", r'''Implement suffix array construction for a string. A suffix array is a sorted array of all suffixes of the string, represented by their starting indices. Include an O(n log^2 n) construction and demonstrate LCP array computation.''', r'''<think>
A suffix array SA is an array of integers giving the starting positions of all suffixes of a string, sorted in lexicographic order. It is a space-efficient alternative to a suffix tree.

For string "banana":
Suffixes: banana(0), anana(1), nana(2), ana(3), na(4), a(5)
Sorted: a(5), ana(3), anana(1), banana(0), na(4), nana(2)
SA = [5, 3, 1, 0, 4, 2]

Construction approaches:
1. Naive: Sort all suffixes using string comparison. O(n^2 log n) -- each comparison is O(n).
2. Prefix doubling (O(n log^2 n)): Sort by first 1 character, then 2, then 4, etc. At each step, compare pairs of previously computed ranks.
3. SA-IS or DC3: O(n) algorithms, more complex.

I will implement the prefix doubling approach:
1. Assign initial ranks based on first character
2. At step k, sort suffixes by (rank[i], rank[i + 2^(k-1)]) using the ranks from step k-1
3. Recompute ranks based on the new sorted order
4. Repeat until all ranks are unique or we have covered the string length

Using Python's sort, each step is O(n log n), and we need O(log n) steps, giving O(n log^2 n).

LCP array: lcp[i] = length of longest common prefix between SA[i] and SA[i-1] (consecutive suffixes in sorted order). Computed in O(n) using Kasai's algorithm.

Kasai's algorithm:
1. Build inverse suffix array (rank of each suffix)
2. For each suffix in original order, compute LCP with the previous suffix in sorted order
3. Key observation: if lcp between suffix i and its predecessor is h, then lcp between suffix i+1 and its predecessor is at least h-1
</think>

**Suffix Array Construction with LCP Array**

```python
def build_suffix_array(s):
    """
    Build suffix array using prefix doubling. O(n log^2 n).

    Args:
        s: input string
    Returns:
        suffix array (list of starting indices of sorted suffixes)
    """
    n = len(s)
    if n == 0:
        return []

    # Initial ranks based on character values
    sa = list(range(n))
    rank = [ord(c) for c in s]
    tmp = [0] * n

    k = 1
    while k < n:
        # Sort by (rank[i], rank[i+k])
        def sort_key(i):
            return (rank[i], rank[i + k] if i + k < n else -1)

        sa.sort(key=sort_key)

        # Recompute ranks
        tmp[sa[0]] = 0
        for i in range(1, n):
            tmp[sa[i]] = tmp[sa[i - 1]]
            if sort_key(sa[i]) != sort_key(sa[i - 1]):
                tmp[sa[i]] += 1

        rank = tmp[:]

        # Early termination if all ranks unique
        if rank[sa[-1]] == n - 1:
            break

        k *= 2

    return sa


def build_lcp_array(s, sa):
    """
    Build LCP array using Kasai's algorithm. O(n).

    lcp[i] = length of longest common prefix of sa[i] and sa[i-1].
    lcp[0] = 0 by convention.

    Args:
        s: input string
        sa: suffix array
    Returns:
        LCP array
    """
    n = len(s)
    rank = [0] * n
    for i in range(n):
        rank[sa[i]] = i

    lcp = [0] * n
    h = 0

    for i in range(n):
        if rank[i] > 0:
            j = sa[rank[i] - 1]  # previous suffix in sorted order
            while i + h < n and j + h < n and s[i + h] == s[j + h]:
                h += 1
            lcp[rank[i]] = h
            if h > 0:
                h -= 1
        else:
            h = 0

    return lcp


def search_suffix_array(s, sa, pattern):
    """Binary search on suffix array for pattern occurrences."""
    n = len(s)
    m = len(pattern)

    # Find leftmost match
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        suffix = s[sa[mid]:sa[mid] + m]
        if suffix < pattern:
            lo = mid + 1
        else:
            hi = mid
    left = lo

    # Find rightmost match
    hi = n
    while lo < hi:
        mid = (lo + hi) // 2
        suffix = s[sa[mid]:sa[mid] + m]
        if suffix <= pattern:
            lo = mid + 1
        else:
            hi = mid
    right = lo

    return [sa[i] for i in range(left, right)]


# Example
s = "banana"
sa = build_suffix_array(s)
lcp = build_lcp_array(s, sa)

print(f"String: '{s}'")
print(f"Suffix Array: {sa}")
print(f"LCP Array:    {lcp}")
print(f"\nSorted suffixes:")
for i, idx in enumerate(sa):
    suffix = s[idx:]
    print(f"  SA[{i}] = {idx}: '{suffix}' (LCP={lcp[i]})")

# Pattern search
patterns = ["an", "na", "ban"]
for p in patterns:
    positions = search_suffix_array(s, sa, p)
    print(f"\nSearch '{p}': found at positions {sorted(positions)}")

# Application: count distinct substrings
# Total substrings = n*(n+1)/2, minus LCP overlaps
n = len(s)
total = n * (n + 1) // 2
duplicates = sum(lcp)
distinct = total - duplicates
print(f"\nDistinct substrings of '{s}': {distinct}")
print(f"  Total: {total}, Duplicates (sum of LCP): {duplicates}")
```

**Kasai's Algorithm Key Insight:**
- If suffix i has LCP h with its sorted predecessor, suffix i+1 has LCP >= h-1
- This is because removing the first character shortens the common prefix by at most 1
- Total work: h increases at most n times and decreases at most n times -> O(n)

**Applications of Suffix Arrays:**
- Pattern matching: O(m log n) per query
- Counting distinct substrings: n*(n+1)/2 - sum(LCP)
- Longest repeated substring: max(LCP)
- Longest common substring (of two strings): build SA on concatenation

**Complexity:**
- Construction: O(n log^2 n) prefix doubling, O(n) with SA-IS
- LCP array: O(n) with Kasai's algorithm
- Pattern search: O(m log n)
- Space: O(n)'''),
]
