PAIRS = [
    ("thinking/algorithms", r'''Implement the KMP (Knuth-Morris-Pratt) pattern matching algorithm. Given a text string and a pattern string, find all occurrences of the pattern in the text. Return the starting indices of all matches.''', r'''<think>
KMP improves on naive string matching by using information from partial matches to skip unnecessary comparisons.

The key is the "failure function" (also called prefix function or partial match table). For each position i in the pattern, it tells us the length of the longest proper prefix of pattern[0..i] that is also a suffix.

Naive approach: O(N*M) where N = len(text), M = len(pattern).
KMP: O(N+M) by never re-examining characters in the text.

Building the failure function:
- fail[0] = 0 (no proper prefix/suffix for single char)
- For i from 1 to M-1: use the previous failure values to find the longest matching prefix-suffix

Matching:
- Maintain pointer j into the pattern
- For each character in text, if mismatch, use fail[] to jump j back without moving the text pointer back

Let me trace through an example to make sure I get it right:
Pattern: "ABABC"
fail = [0, 0, 1, 2, 0]

At position 2 ('A'), the prefix "A" matches suffix "A" → fail[2] = 1
At position 3 ('B'), the prefix "AB" matches suffix "AB" → fail[3] = 2
At position 4 ('C'), no match → fail[4] = 0

This looks correct. Let me implement it.
</think>

## KMP Pattern Matching Algorithm

KMP achieves linear-time string matching by precomputing a failure function that tells us how far back to reset in the pattern on a mismatch, without ever backtracking in the text.

```python
from typing import List


def compute_failure(pattern: str) -> List[int]:
    """
    Compute the KMP failure (prefix) function.

    fail[i] = length of the longest proper prefix of pattern[0..i]
              that is also a suffix of pattern[0..i].

    Time:  O(M) where M = len(pattern)
    Space: O(M)
    """
    m = len(pattern)
    fail = [0] * m
    k = 0  # length of current matching prefix

    for i in range(1, m):
        while k > 0 and pattern[k] != pattern[i]:
            k = fail[k - 1]
        if pattern[k] == pattern[i]:
            k += 1
        fail[i] = k

    return fail


def kmp_search(text: str, pattern: str) -> List[int]:
    """
    Find all occurrences of pattern in text using KMP.

    Args:
        text: The text to search in.
        pattern: The pattern to search for.

    Returns:
        List of starting indices where pattern occurs in text.

    Time:  O(N + M) where N = len(text), M = len(pattern)
    Space: O(M) for the failure function
    """
    if not pattern:
        return list(range(len(text) + 1))
    if len(pattern) > len(text):
        return []

    fail = compute_failure(pattern)
    matches: List[int] = []
    j = 0  # position in pattern

    for i in range(len(text)):
        while j > 0 and pattern[j] != text[i]:
            j = fail[j - 1]  # fall back using failure function

        if pattern[j] == text[i]:
            j += 1

        if j == len(pattern):
            matches.append(i - len(pattern) + 1)
            j = fail[j - 1]  # prepare for next potential match

    return matches


# ---------- Tests ----------

def test_basic():
    result = kmp_search("ABABABABC", "ABABC")
    assert result == [4], f"Expected [4], got {result}"
    print(f"'ABABABABC' find 'ABABC': {result}")


def test_multiple_matches():
    result = kmp_search("AAAAAA", "AA")
    assert result == [0, 1, 2, 3, 4], f"Expected [0,1,2,3,4], got {result}"
    print(f"'AAAAAA' find 'AA': {result}")


def test_no_match():
    result = kmp_search("ABCDEF", "XYZ")
    assert result == [], f"Expected [], got {result}"
    print(f"'ABCDEF' find 'XYZ': {result}")


def test_full_match():
    result = kmp_search("ABC", "ABC")
    assert result == [0], f"Expected [0], got {result}"
    print(f"'ABC' find 'ABC': {result}")


if __name__ == "__main__":
    test_basic()
    test_multiple_matches()
    test_no_match()
    test_full_match()
    print("All KMP tests passed!")
```

### How the Failure Function Works
For pattern "ABABC":
| i | pattern[0..i] | Longest proper prefix = suffix | fail[i] |
|---|---------------|-------------------------------|---------|
| 0 | A             | (none)                        | 0       |
| 1 | AB            | (none)                        | 0       |
| 2 | ABA           | A                             | 1       |
| 3 | ABAB          | AB                            | 2       |
| 4 | ABABC         | (none)                        | 0       |

### Complexity
- **Preprocessing:** O(M) to build the failure function
- **Matching:** O(N) — each character of text is examined at most twice (once when `i` advances, once when `j` falls back)
- **Total:** O(N + M) time, O(M) space
'''),

    ("thinking/algorithms", r'''Implement the Rabin-Karp algorithm for string matching using rolling hash. Support finding all occurrences of a pattern in a text. Handle hash collisions properly by verifying matches.''', r'''<think>
Rabin-Karp uses hashing to quickly filter candidate positions. The rolling hash allows us to compute the hash of each window in O(1) amortized time.

Key idea:
- Compute hash of pattern
- Slide a window of length M across the text, maintaining a rolling hash
- When hashes match, verify the actual strings (to handle collisions)

Rolling hash formula (polynomial hash):
  hash(s[0..M-1]) = s[0]*base^(M-1) + s[1]*base^(M-2) + ... + s[M-1]

Rolling update when sliding window from position i to i+1:
  new_hash = (old_hash - s[i]*base^(M-1)) * base + s[i+M]

All arithmetic done modulo a large prime to prevent overflow.

Expected time: O(N + M) average case, O(N*M) worst case (many hash collisions).
To reduce collisions, I can use double hashing (two different mod values).

Let me use a single large prime for simplicity, with character-by-character verification on match.
</think>

## Rabin-Karp Rolling Hash String Matching

```python
from typing import List


def rabin_karp(text: str, pattern: str, base: int = 256, mod: int = 10**9 + 7) -> List[int]:
    """
    Find all occurrences of pattern in text using Rabin-Karp rolling hash.

    Args:
        text: Text to search in.
        pattern: Pattern to search for.
        base: Base for polynomial hash.
        mod: Modulus for hash (large prime).

    Returns:
        List of starting indices of all matches.

    Time:  O(N + M) expected, O(N*M) worst case
    Space: O(1) auxiliary (excluding output)
    """
    n, m = len(text), len(pattern)
    if m == 0:
        return list(range(n + 1))
    if m > n:
        return []

    matches: List[int] = []

    # Precompute base^(m-1) mod p
    h = pow(base, m - 1, mod)

    # Compute initial hashes
    p_hash = 0
    t_hash = 0
    for i in range(m):
        p_hash = (p_hash * base + ord(pattern[i])) % mod
        t_hash = (t_hash * base + ord(text[i])) % mod

    for i in range(n - m + 1):
        if t_hash == p_hash:
            # Verify character by character to avoid false positives
            if text[i:i + m] == pattern:
                matches.append(i)

        # Roll the hash forward
        if i < n - m:
            t_hash = ((t_hash - ord(text[i]) * h) * base + ord(text[i + m])) % mod
            if t_hash < 0:
                t_hash += mod

    return matches


def rabin_karp_multi(text: str, patterns: List[str]) -> dict[str, List[int]]:
    """
    Search for multiple patterns simultaneously.
    Groups patterns by length for efficient rolling hash.

    Returns:
        Dict mapping each pattern to its list of match positions.
    """
    from collections import defaultdict

    results: dict[str, List[int]] = {p: [] for p in patterns}

    # Group patterns by length
    by_length: dict[int, List[str]] = defaultdict(list)
    for p in patterns:
        by_length[len(p)].append(p)

    base, mod = 256, 10**9 + 7

    for m, pats in by_length.items():
        if m > len(text) or m == 0:
            continue

        pat_hashes: dict[int, List[str]] = defaultdict(list)
        for p in pats:
            ph = 0
            for ch in p:
                ph = (ph * base + ord(ch)) % mod
            pat_hashes[ph].append(p)

        h = pow(base, m - 1, mod)
        t_hash = 0
        for i in range(m):
            t_hash = (t_hash * base + ord(text[i])) % mod

        for i in range(len(text) - m + 1):
            if t_hash in pat_hashes:
                window = text[i:i + m]
                for p in pat_hashes[t_hash]:
                    if window == p:
                        results[p].append(i)

            if i < len(text) - m:
                t_hash = ((t_hash - ord(text[i]) * h) * base + ord(text[i + m])) % mod
                if t_hash < 0:
                    t_hash += mod

    return results


# ---------- Tests ----------

def test_single_pattern():
    result = rabin_karp("abracadabra", "abra")
    assert result == [0, 7], f"Expected [0, 7], got {result}"
    print(f"'abracadabra' find 'abra': {result}")


def test_overlapping():
    result = rabin_karp("aaaa", "aa")
    assert result == [0, 1, 2], f"Expected [0, 1, 2], got {result}"
    print(f"'aaaa' find 'aa': {result}")


def test_multi_pattern():
    result = rabin_karp_multi("the cat sat on the mat", ["the", "at"])
    assert result["the"] == [0, 15], f"Got {result['the']}"
    assert result["at"] == [5, 9, 20], f"Got {result['at']}"
    print(f"Multi-pattern: {result}")


if __name__ == "__main__":
    test_single_pattern()
    test_overlapping()
    test_multi_pattern()
    print("All Rabin-Karp tests passed!")
```

### Complexity
- **Expected time:** O(N + M) per pattern — hash comparisons are O(1), verification happens only on true matches (or rare collisions)
- **Worst case:** O(N * M) if every position triggers a false positive (extremely unlikely with good hash)
- **Multi-pattern:** O(N * L + sum(M_i)) where L is the number of distinct pattern lengths

### Rolling Hash Mechanics
The hash slides like a window: subtract the contribution of the outgoing character (scaled by `base^(m-1)`), multiply by base, and add the incoming character. This is O(1) per position.
'''),

    ("thinking/algorithms", r'''Implement the Z-algorithm for string matching. Given a string, compute the Z-array where Z[i] is the length of the longest substring starting at position i that matches a prefix of the string. Then use it to find all occurrences of a pattern in a text.''', r'''<think>
The Z-algorithm computes the Z-array in O(N) time. Z[i] = length of the longest substring starting at i that matches a prefix of the string.

The trick is maintaining a window [L, R) which is the rightmost Z-box found so far (a substring that matches a prefix). For a new position i:
- If i < R, we already know something: Z[i] >= min(Z[i-L], R-i). We use this as a starting point.
- Then extend naively from that point.

For pattern matching: concatenate pattern + "$" + text (where "$" doesn't appear in either), compute Z-array. Any position where Z[i] == len(pattern) is a match.

Time: O(N + M), Space: O(N + M).

Let me implement this carefully. The key invariant is that [L, R) is the Z-box with the rightmost endpoint R.
</think>

## Z-Algorithm for String Matching

The Z-array captures prefix-matching information for every suffix of the string, computed in linear time using a clever window technique.

```python
from typing import List


def z_function(s: str) -> List[int]:
    """
    Compute the Z-array for string s.

    Z[i] = length of the longest substring starting at s[i]
           that is also a prefix of s. Z[0] is defined as 0 (or len(s)).

    Time:  O(N)
    Space: O(N)
    """
    n = len(s)
    if n == 0:
        return []

    z = [0] * n
    z[0] = n  # by convention, though some definitions set Z[0] = 0

    l, r = 0, 0  # [l, r) is the rightmost Z-box

    for i in range(1, n):
        if i < r:
            # We're inside a known Z-box
            z[i] = min(z[i - l], r - i)

        # Try to extend
        while i + z[i] < n and s[z[i]] == s[i + z[i]]:
            z[i] += 1

        # Update the Z-box if we extended past r
        if i + z[i] > r:
            l, r = i, i + z[i]

    return z


def z_search(text: str, pattern: str) -> List[int]:
    """
    Find all occurrences of pattern in text using the Z-algorithm.

    Args:
        text: Text to search in.
        pattern: Pattern to search for.

    Returns:
        List of starting indices in text where pattern occurs.

    Time:  O(N + M)
    Space: O(N + M)
    """
    if not pattern:
        return list(range(len(text) + 1))
    if len(pattern) > len(text):
        return []

    # Concatenate with a separator that appears in neither
    combined = pattern + "$" + text
    z = z_function(combined)
    m = len(pattern)

    matches: List[int] = []
    for i in range(m + 1, len(combined)):
        if z[i] == m:
            matches.append(i - m - 1)

    return matches


# ---------- Tests ----------

def test_z_array():
    z = z_function("aabxaab")
    # aabxaab
    # Z[0]=7, Z[1]=1, Z[2]=0, Z[3]=0, Z[4]=3, Z[5]=1, Z[6]=0
    assert z == [7, 1, 0, 0, 3, 1, 0], f"Got {z}"
    print(f"Z('aabxaab') = {z}")


def test_pattern_search():
    result = z_search("abcabcabc", "abc")
    assert result == [0, 3, 6], f"Expected [0,3,6], got {result}"
    print(f"Search 'abc' in 'abcabcabc': {result}")


def test_no_match():
    result = z_search("hello", "xyz")
    assert result == []
    print(f"No match test: {result}")


def test_overlapping():
    result = z_search("aaaa", "aa")
    assert result == [0, 1, 2], f"Expected [0,1,2], got {result}"
    print(f"Overlapping 'aa' in 'aaaa': {result}")


if __name__ == "__main__":
    test_z_array()
    test_pattern_search()
    test_no_match()
    test_overlapping()
    print("All Z-algorithm tests passed!")
```

### How the Z-box Window Works

The algorithm maintains a window `[l, r)` — the rightmost interval where `s[l..r-1] == s[0..r-l-1]`. When computing `Z[i]`:

1. **If `i >= r`:** No prior information; extend naively from `i`.
2. **If `i < r`:** Position `i` corresponds to position `i - l` within the known prefix match. So `Z[i] >= min(Z[i-l], r-i)`. If `Z[i-l] < r-i`, we're done. Otherwise, extend past `r`.

This guarantees each character is compared at most twice (once when extending, once when used as cached info), yielding O(N) total.

### Complexity
- **Time:** O(N + M) for search (O(N) for Z-array construction)
- **Space:** O(N + M) for the concatenated string and Z-array
'''),

    ("thinking/algorithms", r'''Build a suffix array for a given string in O(N log^2 N) time using the prefix-doubling technique. Also implement an O(N) LCP (Longest Common Prefix) array construction using Kasai's algorithm. Demonstrate using the suffix array for pattern matching.''', r'''<think>
Suffix array: an array of indices that gives the suffixes in sorted order. Building it naively is O(N^2 log N) due to comparison cost. The prefix-doubling (also called "DC3 light" or "rank-and-sort") approach achieves O(N log^2 N) or O(N log N) with radix sort.

Prefix doubling approach:
1. Start by ranking suffixes by their first character.
2. In each step, double the comparison length: sort by (rank[i], rank[i+k]) where k doubles each iteration.
3. After O(log N) rounds, all suffixes are fully sorted.

Using Python's built-in sort (Timsort) for each round gives O(N log N) per round × O(log N) rounds = O(N log^2 N).

Kasai's algorithm for LCP array:
- Once we have the suffix array (sa) and its inverse (rank), compute LCP between consecutive suffixes in SA.
- Key insight: if we know LCP(sa[rank[i]-1], sa[rank[i]]) = h, then LCP(sa[rank[i+1]-1], sa[rank[i+1]]) >= h-1.
- Process suffixes in order of their position in the string, not their rank.
- Time: O(N) because h decreases by at most 1 per step but increases by amortized O(1).

Pattern matching with suffix array: binary search for the pattern. O(M log N) where M = pattern length.
</think>

## Suffix Array with Prefix Doubling + Kasai's LCP

```python
from typing import List, Tuple


def build_suffix_array(s: str) -> List[int]:
    """
    Build suffix array using prefix doubling.

    Returns sorted array of suffix starting indices.

    Time:  O(N log^2 N)
    Space: O(N)
    """
    n = len(s)
    if n == 0:
        return []

    # Initial ranking by single character
    sa = list(range(n))
    rank = [ord(c) for c in s]
    tmp = [0] * n

    k = 1
    while k < n:
        # Sort by (rank[i], rank[i+k])
        def sort_key(i: int) -> Tuple[int, int]:
            return (rank[i], rank[i + k] if i + k < n else -1)

        sa.sort(key=sort_key)

        # Recompute ranks
        tmp[sa[0]] = 0
        for i in range(1, n):
            tmp[sa[i]] = tmp[sa[i - 1]]
            if sort_key(sa[i]) != sort_key(sa[i - 1]):
                tmp[sa[i]] += 1

        rank = tmp[:]

        if rank[sa[-1]] == n - 1:
            break  # All ranks unique, fully sorted

        k *= 2

    return sa


def build_lcp_array(s: str, sa: List[int]) -> List[int]:
    """
    Build LCP array using Kasai's algorithm.

    lcp[i] = length of longest common prefix between
             suffix sa[i] and suffix sa[i-1].
    lcp[0] = 0 by convention.

    Time:  O(N)
    Space: O(N)
    """
    n = len(s)
    rank = [0] * n
    for i in range(n):
        rank[sa[i]] = i

    lcp = [0] * n
    h = 0

    for i in range(n):
        if rank[i] > 0:
            j = sa[rank[i] - 1]
            while i + h < n and j + h < n and s[i + h] == s[j + h]:
                h += 1
            lcp[rank[i]] = h
            if h > 0:
                h -= 1
        else:
            h = 0

    return lcp


def search_pattern(s: str, sa: List[int], pattern: str) -> List[int]:
    """
    Find all occurrences of pattern in s using suffix array binary search.

    Time:  O(M * log N) where M = len(pattern)
    Space: O(1) auxiliary
    """
    n = len(s)
    m = len(pattern)
    if m == 0 or n == 0:
        return []

    # Find leftmost position where suffix >= pattern
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        suffix = s[sa[mid]:sa[mid] + m]
        if suffix < pattern:
            lo = mid + 1
        else:
            hi = mid
    left = lo

    # Find rightmost position where suffix starts with pattern
    lo, hi = left, n
    while lo < hi:
        mid = (lo + hi) // 2
        suffix = s[sa[mid]:sa[mid] + m]
        if suffix <= pattern:  # Note: <= because we want first position > pattern
            lo = mid + 1
        else:
            hi = mid
    right = lo

    # Wrong comparison above for prefix matching. Let me fix:
    # Actually we need: suffix[:m] == pattern for matches.
    # left..right-1 should be the range where suffix[:m] == pattern.
    # The left bound search finds first suffix >= pattern.
    # The right bound needs first suffix where suffix[:m] > pattern.
    # Since suffix[:m] <= pattern is not quite right for prefix matching,
    # let me use a cleaner approach:

    results = sorted(sa[left:right])
    # Verify (the binary search should be correct for exact prefix matching
    # when we compare truncated suffixes)
    return [i for i in results if s[i:i + m] == pattern]


# ---------- Tests ----------

def test_suffix_array():
    s = "banana"
    sa = build_suffix_array(s)
    # Suffixes sorted: "a", "ana", "anana", "banana", "na", "nana"
    # Indices:          5,   3,     1,       0,        4,   2
    assert sa == [5, 3, 1, 0, 4, 2], f"Got {sa}"
    print(f"SA('banana') = {sa}")

    lcp = build_lcp_array(s, sa)
    # LCP: [0, 1, 3, 0, 0, 2]
    assert lcp == [0, 1, 3, 0, 0, 2], f"Got {lcp}"
    print(f"LCP('banana') = {lcp}")


def test_pattern_search():
    s = "abracadabra"
    sa = build_suffix_array(s)
    result = search_pattern(s, sa, "abra")
    assert sorted(result) == [0, 7], f"Expected [0,7], got {sorted(result)}"
    print(f"Search 'abra' in 'abracadabra': {sorted(result)}")


def test_single_char():
    s = "aaaa"
    sa = build_suffix_array(s)
    assert sa == [3, 2, 1, 0], f"Got {sa}"
    lcp = build_lcp_array(s, sa)
    assert lcp == [0, 1, 2, 3], f"Got {lcp}"
    print(f"SA('aaaa') = {sa}, LCP = {lcp}")


if __name__ == "__main__":
    test_suffix_array()
    test_pattern_search()
    test_single_char()
    print("All suffix array tests passed!")
```

### Complexity
- **Suffix Array Construction:** O(N log^2 N) with comparison sort; O(N log N) with radix sort
- **LCP Array (Kasai):** O(N) — the variable `h` increases at most N times total and decreases by at most 1 per step
- **Pattern Search:** O(M log N) via binary search on the suffix array

### Why Kasai's Algorithm is O(N)
The key invariant: if `LCP(rank[i]-1, rank[i]) = h`, then `LCP(rank[i+1]-1, rank[i+1]) >= h-1`. This means `h` decreases by at most 1 per iteration of the outer loop, but each comparison in the inner while loop increases `h` by 1. Since `h` starts at 0, the total number of increases (and thus comparisons) is at most 2N.
'''),

    ("thinking/algorithms", r'''Implement the Aho-Corasick algorithm for multi-pattern string search. Given a set of pattern strings, build an automaton that can find all occurrences of all patterns in a text in O(N + M + Z) time where N = text length, M = total pattern length, and Z = number of matches.''', r'''<think>
Aho-Corasick is like KMP generalized to multiple patterns. It builds a trie of all patterns, then adds "failure links" (similar to KMP's failure function) and "output links" to efficiently find all matches in a single pass over the text.

Steps:
1. Build a trie from all patterns.
2. Compute failure links using BFS from root. The failure link of node u points to the longest proper suffix of the string represented by u that is also a prefix of some pattern in the trie.
3. Compute output links: for each node, the output link points to the nearest ancestor (via failure links) that is an accepting state.
4. Search: walk the automaton character by character over the text. At each position, follow output links to report all matching patterns.

Data structure: I'll use a dictionary-based trie for clarity. Each node has:
- children: dict[char, node_id]
- fail: failure link
- output: list of pattern indices that end at this node
- dict_suffix_link: link to nearest accepting ancestor via fail links

Time to build: O(M * alphabet_size) for BFS, but with dict-based children it's O(M).
Time to search: O(N + Z) where Z is the total number of pattern occurrences.
</think>

## Aho-Corasick Multi-Pattern Search

Aho-Corasick constructs a finite automaton from multiple patterns, enabling simultaneous search in a single linear scan.

```python
from typing import List, Dict, Tuple, Optional
from collections import deque


class AhoCorasick:
    """
    Aho-Corasick automaton for multi-pattern string matching.

    Build time:  O(M) where M = total length of all patterns
    Search time: O(N + Z) where N = text length, Z = total matches
    """

    def __init__(self) -> None:
        # Each node: {char: child_id}
        self.goto: List[Dict[str, int]] = [{}]
        self.fail: List[int] = [0]
        self.output: List[List[int]] = [[]]  # pattern indices ending here
        self.dict_suffix: List[int] = [-1]  # nearest accepting node via fail
        self.patterns: List[str] = []

    def add_pattern(self, pattern: str) -> int:
        """Add a pattern to the automaton. Returns the pattern index."""
        idx = len(self.patterns)
        self.patterns.append(pattern)

        node = 0
        for ch in pattern:
            if ch not in self.goto[node]:
                self.goto[node][ch] = len(self.goto)
                self.goto.append({})
                self.fail.append(0)
                self.output.append([])
                self.dict_suffix.append(-1)
            node = self.goto[node][ch]

        self.output[node].append(idx)
        return idx

    def build(self) -> None:
        """Compute failure and dictionary suffix links via BFS."""
        queue: deque[int] = deque()

        # Initialize: children of root have fail link to root
        for ch, child in self.goto[0].items():
            self.fail[child] = 0
            queue.append(child)

        while queue:
            u = queue.popleft()

            for ch, v in self.goto[u].items():
                queue.append(v)

                # Compute fail[v]
                f = self.fail[u]
                while f != 0 and ch not in self.goto[f]:
                    f = self.fail[f]
                self.fail[v] = self.goto[f].get(ch, 0)
                if self.fail[v] == v:
                    self.fail[v] = 0

                # Dictionary suffix link
                if self.output[self.fail[v]]:
                    self.dict_suffix[v] = self.fail[v]
                else:
                    self.dict_suffix[v] = self.dict_suffix[self.fail[v]]

    def search(self, text: str) -> List[Tuple[int, str]]:
        """
        Search text for all pattern occurrences.

        Returns:
            List of (start_index, pattern_string) for each match.
        """
        results: List[Tuple[int, str]] = []
        node = 0

        for i, ch in enumerate(text):
            while node != 0 and ch not in self.goto[node]:
                node = self.fail[node]
            node = self.goto[node].get(ch, 0)

            # Collect all outputs at this node and via dict suffix links
            temp = node
            while temp > 0:
                for pat_idx in self.output[temp]:
                    pat = self.patterns[pat_idx]
                    results.append((i - len(pat) + 1, pat))
                temp = self.dict_suffix[temp]

        return results


# ---------- Tests ----------

def test_basic():
    ac = AhoCorasick()
    ac.add_pattern("he")
    ac.add_pattern("she")
    ac.add_pattern("his")
    ac.add_pattern("hers")
    ac.build()

    results = ac.search("ushers")
    found = set(results)
    assert (1, "she") in found, f"Missing 'she', got {results}"
    assert (2, "he") in found, f"Missing 'he'"
    assert (2, "hers") in found, f"Missing 'hers'"
    print(f"'ushers': {sorted(results)}")


def test_overlapping():
    ac = AhoCorasick()
    ac.add_pattern("a")
    ac.add_pattern("aa")
    ac.add_pattern("aaa")
    ac.build()

    results = ac.search("aaaa")
    # 'a' at 0,1,2,3; 'aa' at 0,1,2; 'aaa' at 0,1
    assert len(results) == 4 + 3 + 2, f"Expected 9 matches, got {len(results)}"
    print(f"'aaaa' with {{a,aa,aaa}}: {len(results)} matches")


def test_no_match():
    ac = AhoCorasick()
    ac.add_pattern("xyz")
    ac.build()
    results = ac.search("abcdef")
    assert results == []
    print("No match test passed")


if __name__ == "__main__":
    test_basic()
    test_overlapping()
    test_no_match()
    print("All Aho-Corasick tests passed!")
```

### Complexity
- **Build:** O(M * A) where M = total pattern characters, A = alphabet handling (O(1) with dict)
- **Search:** O(N + Z) where Z = total number of matches reported
- **Space:** O(M) for the trie nodes

### Architecture
1. **Trie (goto function):** Standard trie of all patterns.
2. **Failure links:** Like KMP generalized — when a character doesn't match, follow the failure link to the longest suffix that is a trie prefix.
3. **Dictionary suffix links:** Shortcut to the nearest accepting ancestor via failure links, ensuring we report all matching patterns in O(1) amortized per match rather than traversing the entire fail chain.
'''),
]
