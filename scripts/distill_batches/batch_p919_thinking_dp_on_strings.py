PAIRS = [
    ("thinking/algorithms", r'''Implement regular expression matching with support for '.' (matches any single character) and '*' (matches zero or more of the preceding element). The matching should cover the entire input string.''', r'''<think>
This is LeetCode 10 -- regex matching with '.' and '*'. This is a classic DP on strings problem.

The key challenge is handling '*'. The character before '*' can appear 0 or more times. So for pattern "a*", it can match "", "a", "aa", "aaa", etc.

DP formulation:
- dp[i][j] = True if s[0..i-1] matches p[0..j-1]
- Base case: dp[0][0] = True (empty string matches empty pattern)
- For empty string with pattern: dp[0][j] is True only if p[j-1] == '*' and dp[0][j-2] is True (the * matches zero occurrences)

Transitions:
1. If p[j-1] is a normal char or '.':
   dp[i][j] = dp[i-1][j-1] AND (s[i-1] == p[j-1] or p[j-1] == '.')

2. If p[j-1] == '*':
   Two sub-cases:
   a. Zero occurrences: dp[i][j] = dp[i][j-2] (skip the "x*" pattern)
   b. One or more occurrences: dp[i][j] = dp[i-1][j] AND (s[i-1] == p[j-2] or p[j-2] == '.')
      (consume one character from s, but keep the "*" pattern for potential further matches)

Edge cases:
- Pattern starts with '*' (invalid in standard regex, but we should handle gracefully)
- Multiple consecutive '*' patterns like "a*b*c*"
- Pattern ".*" matches any string
- Empty string and empty pattern

Time: O(m*n), Space: O(m*n) reducible to O(n).
</think>

**Regular Expression Matching -- Dynamic Programming**

```python
def is_match(s, p):
    """
    Check if string s matches pattern p with '.' and '*' support.

    Args:
        s: input string
        p: pattern with '.' and '*'
    Returns:
        True if s fully matches p
    """
    m, n = len(s), len(p)

    # dp[i][j] = does s[:i] match p[:j]?
    dp = [[False] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = True

    # Base case: empty string with pattern like "a*b*c*"
    for j in range(2, n + 1):
        if p[j - 1] == '*':
            dp[0][j] = dp[0][j - 2]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if p[j - 1] == '*':
                # Zero occurrences of preceding char
                dp[i][j] = dp[i][j - 2]
                # One or more occurrences
                if p[j - 2] == '.' or p[j - 2] == s[i - 1]:
                    dp[i][j] = dp[i][j] or dp[i - 1][j]
            elif p[j - 1] == '.' or p[j - 1] == s[i - 1]:
                dp[i][j] = dp[i - 1][j - 1]

    return dp[m][n]


# Test cases
tests = [
    ("aa", "a", False),
    ("aa", "a*", True),
    ("ab", ".*", True),
    ("aab", "c*a*b", True),
    ("mississippi", "mis*is*ip*.", True),
    ("", "a*b*c*", True),
    ("abc", "abc", True),
    ("abc", "a.c", True),
    ("aaa", "a*a", True),
    ("ab", ".*c", False),
]

for s, p, expected in tests:
    result = is_match(s, p)
    status = "PASS" if result == expected else "FAIL"
    print(f"  [{status}] is_match('{s}', '{p}') = {result}")
```

**DP Transition Summary:**
```
p[j-1] is letter or '.':
    dp[i][j] = dp[i-1][j-1] AND chars match

p[j-1] is '*':
    dp[i][j] = dp[i][j-2]          (zero occurrences)
            OR dp[i-1][j]           (one+ occurrences, if chars match)
```

**Why dp[i-1][j] for "one+ occurrences":**
- We consume s[i-1] but keep the "*" pattern at position j
- This allows the "*" to match additional characters in subsequent rows
- It is equivalent to: match 1 char + recursively match remaining with same pattern

**Complexity:**
- Time: O(m * n) where m = len(s), n = len(p)
- Space: O(m * n), can be optimized to O(n) with rolling array'''),

    ("thinking/algorithms", r'''Implement wildcard pattern matching where '?' matches any single character and '*' matches any sequence of characters (including empty). The matching should cover the entire input string.''', r'''<think>
Wildcard matching (LeetCode 44) differs from regex matching: here '*' matches any sequence independently (not tied to the preceding character).

DP approach:
- dp[i][j] = True if s[0..i-1] matches p[0..j-1]
- Base: dp[0][0] = True. dp[0][j] = True if p[0..j-1] is all '*'s.

Transitions:
1. p[j-1] is a letter: dp[i][j] = dp[i-1][j-1] AND s[i-1] == p[j-1]
2. p[j-1] is '?': dp[i][j] = dp[i-1][j-1] (matches any single char)
3. p[j-1] is '*': dp[i][j] = dp[i][j-1] (match empty) OR dp[i-1][j] (match one more char)

The '*' case: dp[i][j-1] means '*' matches nothing (skip it). dp[i-1][j] means '*' consumes s[i-1] and remains available for more characters.

There is also an O(m+n) greedy/backtracking approach that is faster in practice:
- Track the last '*' position and the string position when we matched it
- On mismatch, backtrack to the last '*' and try matching one more character

Edge cases:
- Multiple consecutive '*'s (equivalent to single '*')
- Pattern is all '*'s (matches anything)
- Empty string with pattern of '*'s only

Time: O(m*n) for DP, O(m+n) for greedy in many cases.
Space: O(m*n) for DP, O(1) for greedy.
</think>

**Wildcard Pattern Matching -- DP and Greedy Solutions**

```python
def is_match_dp(s, p):
    """Wildcard matching using DP. O(m*n) time and space."""
    m, n = len(s), len(p)
    dp = [[False] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = True

    # Empty string matches pattern of only '*'s
    for j in range(1, n + 1):
        if p[j - 1] == '*':
            dp[0][j] = dp[0][j - 1]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if p[j - 1] == '*':
                # Match empty (dp[i][j-1]) or consume one char (dp[i-1][j])
                dp[i][j] = dp[i][j - 1] or dp[i - 1][j]
            elif p[j - 1] == '?' or p[j - 1] == s[i - 1]:
                dp[i][j] = dp[i - 1][j - 1]

    return dp[m][n]


def is_match_greedy(s, p):
    """Wildcard matching using greedy with backtracking. O(m*n) worst, fast in practice."""
    si, pi = 0, 0
    star_pi = -1   # position of last '*' in pattern
    star_si = -1   # position in s when we matched the '*'

    while si < len(s):
        if pi < len(p) and (p[pi] == '?' or p[pi] == s[si]):
            si += 1
            pi += 1
        elif pi < len(p) and p[pi] == '*':
            star_pi = pi
            star_si = si
            pi += 1
            # Initially match zero characters
        elif star_pi != -1:
            # Backtrack: match one more character with last '*'
            star_si += 1
            si = star_si
            pi = star_pi + 1
        else:
            return False

    # Skip trailing '*'s in pattern
    while pi < len(p) and p[pi] == '*':
        pi += 1

    return pi == len(p)


# Test cases
tests = [
    ("aa", "a", False),
    ("aa", "*", True),
    ("cb", "?a", False),
    ("adceb", "*a*b", True),
    ("acdcb", "a*c?b", False),
    ("", "*", True),
    ("", "***", True),
    ("abc", "abc", True),
    ("abc", "?b?", True),
    ("abcdef", "a*d*f", True),
    ("abcdef", "a*d*g", False),
]

print("DP approach:")
for s, p, expected in tests:
    result = is_match_dp(s, p)
    status = "PASS" if result == expected else "FAIL"
    print(f"  [{status}] match('{s}', '{p}') = {result}")

print("\nGreedy approach:")
for s, p, expected in tests:
    result = is_match_greedy(s, p)
    status = "PASS" if result == expected else "FAIL"
    print(f"  [{status}] match('{s}', '{p}') = {result}")
```

**DP vs Greedy Comparison:**
- DP: O(m*n) time, O(m*n) space, clean and easy to prove correct
- Greedy: O(m*n) worst case but often linear, O(1) space
- Greedy works by remembering the last '*' and backtracking when stuck

**Complexity:**
- DP: Time O(m*n), Space O(m*n)
- Greedy: Time O(m*n) worst, O(m+n) best, Space O(1)'''),

    ("thinking/algorithms", r'''Solve the Interleaving String problem: given strings s1, s2, and s3, determine if s3 is formed by interleaving s1 and s2 while maintaining their individual character order.''', r'''<think>
Interleaving String (LeetCode 97): s3 is an interleaving of s1 and s2 if we can form s3 by merging s1 and s2, keeping the relative order of characters from each string.

First check: len(s1) + len(s2) must equal len(s3), otherwise impossible.

DP formulation:
- dp[i][j] = True if s3[0..i+j-1] can be formed by interleaving s1[0..i-1] and s2[0..j-1]
- Base: dp[0][0] = True

Transitions:
- dp[i][j] = True if:
  - dp[i-1][j] is True AND s1[i-1] == s3[i+j-1]  (take from s1)
  - OR dp[i][j-1] is True AND s2[j-1] == s3[i+j-1]  (take from s2)

The idea: at position (i,j) in the DP, we have consumed i characters from s1 and j characters from s2, producing i+j characters of s3. The next character of s3 must come from either s1[i] or s2[j].

This is essentially finding a path in an (m+1) x (n+1) grid from (0,0) to (m,n), where we can move right (take from s2) or down (take from s1), and the character at each step must match the corresponding position in s3.

Space optimization: We only need the previous row, so O(n) space.

Edge cases:
- Either s1 or s2 is empty (s3 must equal the other)
- s1 == s2 and s3 is their interleaving
- Characters match from both strings (need both paths)
- Length mismatch

Time: O(m*n), Space: O(n) optimized.
</think>

**Interleaving String -- Dynamic Programming**

```python
def is_interleave(s1, s2, s3):
    """
    Check if s3 is an interleaving of s1 and s2.

    Args:
        s1, s2: source strings
        s3: target string
    Returns:
        True if s3 is a valid interleaving
    """
    m, n = len(s1), len(s2)
    if m + n != len(s3):
        return False

    # Space-optimized DP: use 1D array
    dp = [False] * (n + 1)
    dp[0] = True

    # First row: only taking from s2
    for j in range(1, n + 1):
        dp[j] = dp[j - 1] and s2[j - 1] == s3[j - 1]

    for i in range(1, m + 1):
        # First column: only taking from s1
        dp[0] = dp[0] and s1[i - 1] == s3[i - 1]

        for j in range(1, n + 1):
            k = i + j - 1  # current position in s3
            dp[j] = (
                (dp[j] and s1[i - 1] == s3[k])      # take from s1
                or (dp[j - 1] and s2[j - 1] == s3[k]) # take from s2
            )

    return dp[n]


def is_interleave_2d(s1, s2, s3):
    """2D DP version for clarity."""
    m, n = len(s1), len(s2)
    if m + n != len(s3):
        return False

    dp = [[False] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = True

    for i in range(m + 1):
        for j in range(n + 1):
            k = i + j
            if i > 0 and s1[i-1] == s3[k-1]:
                dp[i][j] = dp[i][j] or dp[i-1][j]
            if j > 0 and s2[j-1] == s3[k-1]:
                dp[i][j] = dp[i][j] or dp[i][j-1]

    return dp[m][n]


# Test cases
tests = [
    ("aabcc", "dbbca", "aadbbcbcac", True),
    ("aabcc", "dbbca", "aadbbbaccc", False),
    ("", "", "", True),
    ("a", "", "a", True),
    ("a", "b", "ab", True),
    ("a", "b", "ba", True),
    ("a", "b", "c", False),
    ("abc", "def", "adbecf", True),
    ("abc", "def", "abcdef", True),
]

for s1, s2, s3, expected in tests:
    r1 = is_interleave(s1, s2, s3)
    r2 = is_interleave_2d(s1, s2, s3)
    status = "PASS" if r1 == expected else "FAIL"
    print(f"  [{status}] interleave('{s1}', '{s2}', '{s3}') = {r1}")
    assert r1 == r2, "Mismatch between 1D and 2D"
```

**Grid Interpretation:**
- DP table is a grid where going down = take from s1, going right = take from s2
- Each cell (i,j) represents having consumed i chars from s1 and j from s2
- Valid path from (0,0) to (m,n) means s3 is a valid interleaving

**Complexity:**
- Time: O(m * n)
- Space: O(n) with rolling array, O(m * n) for 2D version'''),

    ("thinking/algorithms", r'''Solve the Distinct Subsequences problem: given strings s and t, count the number of distinct subsequences of s that equal t. A subsequence is a sequence derived by deleting some (or no) characters without changing the order.''', r'''<think>
Distinct Subsequences (LeetCode 115): Count how many ways to form t by deleting characters from s.

DP formulation:
- dp[i][j] = number of distinct subsequences of s[0..i-1] that equal t[0..j-1]
- Base cases:
  - dp[i][0] = 1 for all i (empty t can be formed by deleting all chars)
  - dp[0][j] = 0 for j > 0 (cannot form non-empty t from empty s)
  - dp[0][0] = 1

Transitions:
- If s[i-1] == t[j-1]:
  dp[i][j] = dp[i-1][j-1] + dp[i-1][j]
  - dp[i-1][j-1]: use s[i-1] to match t[j-1]
  - dp[i-1][j]: skip s[i-1], look for other ways
- If s[i-1] != t[j-1]:
  dp[i][j] = dp[i-1][j]
  - Must skip s[i-1]

The intuition is: at each character of s, we decide whether to include it in the subsequence (if it matches the current target character) or skip it.

Space optimization: Since dp[i] only depends on dp[i-1], we can use a 1D array. But we must iterate j in reverse to avoid overwriting values we still need.

Edge cases:
- t is longer than s (answer is 0)
- s == t (answer is 1)
- t is empty (answer is 1)
- Many repeated characters (can lead to large counts)

Time: O(m*n), Space: O(n) optimized.
</think>

**Distinct Subsequences -- Dynamic Programming**

```python
def num_distinct(s, t):
    """
    Count distinct subsequences of s that equal t.

    Args:
        s: source string
        t: target string
    Returns:
        number of distinct subsequences
    """
    m, n = len(s), len(t)
    if n > m:
        return 0

    # 1D DP, iterate j in reverse
    dp = [0] * (n + 1)
    dp[0] = 1  # empty subsequence

    for i in range(1, m + 1):
        # Iterate backwards to avoid using updated values
        for j in range(min(i, n), 0, -1):
            if s[i - 1] == t[j - 1]:
                dp[j] += dp[j - 1]
            # If not equal, dp[j] stays the same (skip s[i-1])

    return dp[n]


def num_distinct_2d(s, t):
    """2D version for visualization."""
    m, n = len(s), len(t)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = 1

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = dp[i - 1][j]  # skip s[i-1]
            if s[i - 1] == t[j - 1]:
                dp[i][j] += dp[i - 1][j - 1]  # use s[i-1]

    return dp[m][n]


# Test cases
tests = [
    ("rabbbit", "rabbit", 3),
    ("babgbag", "bag", 5),
    ("abc", "abc", 1),
    ("aaa", "a", 3),
    ("aaa", "aa", 3),
    ("", "a", 0),
    ("a", "", 1),
]

for s, t, expected in tests:
    result = num_distinct(s, t)
    result2 = num_distinct_2d(s, t)
    status = "PASS" if result == expected else "FAIL"
    print(f"  [{status}] distinct('{s}', '{t}') = {result}")
    assert result == result2

# Visualize DP table for "babgbag" -> "bag"
s, t = "babgbag", "bag"
m, n = len(s), len(t)
dp = [[0]*(n+1) for _ in range(m+1)]
for i in range(m+1):
    dp[i][0] = 1
for i in range(1, m+1):
    for j in range(1, n+1):
        dp[i][j] = dp[i-1][j]
        if s[i-1] == t[j-1]:
            dp[i][j] += dp[i-1][j-1]

print(f"\nDP table for '{s}' -> '{t}':")
header = "    " + "  ".join(["''"] + list(t))
print(header)
for i in range(m+1):
    label = "''" if i == 0 else s[i-1]
    row = f" {label}  " + "  ".join(f"{dp[i][j]}" for j in range(n+1))
    print(row)
```

**Output (partial):**
```
  [PASS] distinct('rabbbit', 'rabbit') = 3
  [PASS] distinct('babgbag', 'bag') = 5
```

**Intuition:**
- At each character s[i], we choose: use it (if it matches t[j]) or skip it
- dp[i][j] accumulates both choices
- The "skip" option (dp[i-1][j]) carries forward all ways found so far

**Complexity:**
- Time: O(m * n)
- Space: O(n) with 1D optimization'''),

    ("thinking/algorithms", r'''Solve the Shortest Common Supersequence problem: given two strings str1 and str2, find the shortest string that has both str1 and str2 as subsequences. Return the actual supersequence string, not just its length.''', r'''<think>
Shortest Common Supersequence (LeetCode 1092) builds on LCS (Longest Common Subsequence). The key insight:

Length of SCS = len(s1) + len(s2) - len(LCS(s1, s2))

Because the LCS characters appear in both strings, they need not be duplicated in the supersequence.

To reconstruct the actual string:
1. Compute the LCS DP table
2. Backtrack through the table to build the supersequence:
   - If s1[i-1] == s2[j-1] (part of LCS): include it once, move diagonally
   - If dp[i-1][j] >= dp[i][j-1]: include s1[i-1], move up (it is not part of LCS at this point)
   - Otherwise: include s2[j-1], move left

After backtracking reaches (0,0), append any remaining characters from s1 or s2.

The reconstruction is the tricky part. We are essentially merging s1 and s2, using the LCS as the shared backbone.

Algorithm:
1. Build LCS dp table: dp[i][j] = length of LCS of s1[:i] and s2[:j]
2. Backtrack from dp[m][n]:
   - Both chars match: add to result, go diagonal
   - dp[i-1][j] > dp[i][j-1]: add s1[i-1], go up
   - else: add s2[j-1], go left
3. Add remaining prefixes
4. Reverse the result

Edge cases:
- One string is empty (SCS is the other string)
- Strings are identical (SCS is the string itself)
- No common characters (SCS is concatenation)
- One string is a subsequence of the other

Time: O(m*n) for LCS + O(m+n) for reconstruction. Space: O(m*n).
</think>

**Shortest Common Supersequence -- LCS-based Construction**

```python
def shortest_common_supersequence(s1, s2):
    """
    Find shortest string having both s1 and s2 as subsequences.

    Args:
        s1, s2: input strings
    Returns:
        the shortest common supersequence string
    """
    m, n = len(s1), len(s2)

    # Step 1: Build LCS DP table
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Step 2: Backtrack to build supersequence
    result = []
    i, j = m, n

    while i > 0 and j > 0:
        if s1[i - 1] == s2[j - 1]:
            result.append(s1[i - 1])
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            result.append(s1[i - 1])
            i -= 1
        else:
            result.append(s2[j - 1])
            j -= 1

    # Add remaining characters
    while i > 0:
        result.append(s1[i - 1])
        i -= 1
    while j > 0:
        result.append(s2[j - 1])
        j -= 1

    result.reverse()
    return "".join(result)


def is_subsequence(s, t):
    """Check if s is a subsequence of t."""
    it = iter(t)
    return all(c in it for c in s)


# Test cases
tests = [
    ("abac", "cab"),
    ("abc", "def"),
    ("abc", "abc"),
    ("geek", "eke"),
    ("AGGTAB", "GXTXAYB"),
]

for s1, s2 in tests:
    scs = shortest_common_supersequence(s1, s2)
    valid = is_subsequence(s1, scs) and is_subsequence(s2, scs)
    print(f"  s1='{s1}', s2='{s2}'")
    print(f"  SCS='{scs}' (len={len(scs)}) valid={valid}")
    print(f"  Expected len={len(s1)+len(s2)-dp_lcs(s1,s2)}")
    print()


def dp_lcs(s1, s2):
    m, n = len(s1), len(s2)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(1, m+1):
        for j in range(1, n+1):
            if s1[i-1] == s2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[m][n]
```

**Key Formula:**
```
len(SCS) = len(s1) + len(s2) - len(LCS)
```
The LCS characters are shared, so they appear once instead of twice.

**Reconstruction Strategy:**
- Walk the LCS DP table backward from (m, n) to (0, 0)
- Common characters (diagonal moves) go into the result once
- Non-common characters from s1 (up moves) and s2 (left moves) are added as encountered
- This preserves the order of both original strings

**Complexity:**
- Time: O(m * n) for LCS computation + O(m + n) for backtracking
- Space: O(m * n) for the DP table'''),
]
