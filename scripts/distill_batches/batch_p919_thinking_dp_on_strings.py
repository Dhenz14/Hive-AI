PAIRS = [
    ("thinking/algorithms", r'''Implement regular expression matching with support for '.' (matches any single character) and '*' (matches zero or more of the preceding element). The matching should cover the entire input string.''', r'''<think>
Regex matching with '.' and '*'. This could be done recursively, but that would have exponential time due to the branching from '*'. Let me think about a DP approach instead.

The tricky part is '*' -- it means "zero or more of the preceding element." So "a*" can match "", "a", "aa", etc. This is different from wildcard matching where '*' is standalone.

Let me define dp[i][j] = True if s[0..i-1] matches p[0..j-1].

Base case: dp[0][0] = True. What about dp[0][j] for j > 0? An empty string can match a pattern like "a*b*" because each x* can match zero times. So dp[0][j] = True when p[j-1] == '*' and dp[0][j-2] is True.

For the transitions, I need to consider what p[j-1] is:

If p[j-1] is a letter or '.': straightforward -- dp[i][j] = dp[i-1][j-1] AND the characters match. No branching.

If p[j-1] == '*': this is where it gets interesting. I initially thought I would need to try matching 0, 1, 2, ... characters, but actually there is a cleaner recurrence:
  a. Zero occurrences: dp[i][j] = dp[i][j-2] (skip the "x*" entirely)
  b. One or more: dp[i][j] = dp[i-1][j] AND (s[i-1] matches p[j-2])

Wait, why does dp[i-1][j] handle "one or more" without looping? Because dp[i-1][j] itself will check the same '*' pattern against s[0..i-2]. So if the '*' matches 3 characters, it happens through a chain: dp[i][j] -> dp[i-1][j] -> dp[i-2][j] -> dp[i-3][j] -> dp[i-3][j-2] (zero occurrences). Each step "consumes" one character from s while keeping the '*' pattern active. That is elegant.

Hmm, one thing to be careful about: pattern ".*" matches literally any string, because '.' matches any char and '*' repeats it. So dp transitions must use p[j-2] (the char before '*') and check if it is '.' as a special case.

Time: O(m*n), Space: O(m*n) reducible to O(n) with a rolling array.
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
This looks similar to the regex matching problem, but actually it is quite different. Here '*' matches any sequence of characters by itself -- it is not tied to the preceding character. So '*' is more like a "glob" wildcard.

I could try the same DP formulation: dp[i][j] = True if s[0..i-1] matches p[0..j-1].

For the transitions:
- p[j-1] is a letter: dp[i][j] = dp[i-1][j-1] AND s[i-1] == p[j-1]. Simple.
- p[j-1] is '?': dp[i][j] = dp[i-1][j-1]. Matches any single char.
- p[j-1] is '*': this is the interesting case.

For '*', I initially thought I would need to enumerate all possible lengths it could match, but wait -- there is the same trick as before. dp[i][j] = dp[i][j-1] (star matches empty sequence) OR dp[i-1][j] (star consumes s[i-1] and stays active for more). The chain of dp[i-1][j] -> dp[i-2][j] -> ... handles matching any number of characters.

Base cases: dp[0][0] = True. For dp[0][j], an empty string can match a pattern only if every character so far is '*'. So dp[0][j] = dp[0][j-1] when p[j-1] == '*'.

Hmm, actually there is a much faster approach for this specific problem. We could use a greedy algorithm with backtracking: scan through s and p simultaneously, and whenever we see a '*', remember its position. If we later hit a mismatch, backtrack to the last '*' and have it consume one more character. This runs in O(m*n) worst case but is often O(m+n) in practice, and uses O(1) space.

We could do DP (simpler to prove correct) or greedy (faster in practice)... I will implement both so the reader can compare. The DP is cleaner for understanding correctness, while the greedy is better for competitive programming.

Time: O(m*n) for DP, O(m+n) average for greedy.
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
Interleaving String: determine if s3 can be formed by interleaving s1 and s2 while keeping their internal order.

First sanity check: len(s1) + len(s2) must equal len(s3). If not, immediately return False.

I initially considered a recursive approach -- at each position in s3, try taking from s1 or s2. But that has exponential branching in the worst case (e.g., when both s1 and s2 start with the same character). So this needs DP.

Let me define dp[i][j] = True if s3[0..i+j-1] can be formed from s1[0..i-1] and s2[0..j-1]. The state is how many characters we have consumed from each string.

Transitions: the next character of s3 is at position i+j-1. It could come from s1 or s2:
  - From s1: dp[i][j] = dp[i-1][j] AND s1[i-1] == s3[i+j-1]
  - From s2: dp[i][j] = dp[i][j-1] AND s2[j-1] == s3[i+j-1]
  - Either path being True is sufficient.

Hmm, actually this has a nice geometric interpretation. Think of it as a grid where going down means "take from s1" and going right means "take from s2". We need a path from (0,0) to (m,n) where each step matches the corresponding character in s3. This is basically a reachability problem in a grid with obstacles.

Since dp[i][j] only depends on dp[i-1][j] and dp[i][j-1], I can optimize space to O(n) by using a single row and updating it in-place. The key insight: dp[j] (from the previous row) gives us dp[i-1][j], and dp[j-1] (already updated in this row) gives us dp[i][j-1]. So we just overwrite the array left to right.

Wait, I need to be careful with dp[0] in each row -- it represents taking only from s1, so dp[0] = dp[0] AND s1[i-1] == s3[i-1].

Time: O(m*n), Space: O(n) with the rolling array.
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
Count distinct subsequences of s that equal t. So for s = "rabbbit" and t = "rabbit", we need to count how many ways to select characters from s (in order) to spell t.

This feels like a counting DP problem. Let me define dp[i][j] = number of ways to form t[0..j-1] using characters from s[0..i-1].

Base cases: dp[i][0] = 1 for all i, because there is exactly one way to form the empty string (delete everything). And dp[0][j] = 0 for j > 0 since we cannot form a non-empty target from an empty source.

For the transitions, at each character s[i-1], I have a choice:
- If s[i-1] == t[j-1]: I can either USE this character (consuming both s[i-1] and t[j-1], giving dp[i-1][j-1]) or SKIP it (giving dp[i-1][j]). Total: dp[i-1][j-1] + dp[i-1][j].
- If s[i-1] != t[j-1]: I must skip it. dp[i][j] = dp[i-1][j].

I initially thought this was similar to edit distance, but actually it is simpler -- we never insert or replace, only decide to include or exclude each character of s.

For space optimization, since row i only depends on row i-1, I can use a 1D array. But wait -- if I iterate j left to right, updating dp[j] would overwrite dp[j] (the old value from row i-1) before I use it for dp[j+1]. Since the transition uses dp[j-1] (from the previous row) AND dp[j] (from the previous row), I need to iterate j in reverse to preserve the old values. This is the standard trick for 0/1 knapsack-style space optimization.

Edge cases: if len(t) > len(s), answer is 0 immediately. If s == t, answer is 1. Repeated characters (like "aaa" matching "a") give combinatorial counts -- C(3,1) = 3.

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
I need the shortest string that contains both s1 and s2 as subsequences. My first instinct is that this relates to LCS somehow...

Actually yes -- the LCS characters are shared between s1 and s2, so in the supersequence they only need to appear once. Everything else from both strings must appear too. So:

Length of SCS = len(s1) + len(s2) - len(LCS(s1, s2))

But the problem asks for the actual string, not just the length. So I need to reconstruct it.

I initially considered just finding the LCS and then merging the remaining characters around it, but that gets complicated with the ordering constraints. A cleaner approach: backtrack through the LCS DP table.

The reconstruction works like this -- start at dp[m][n] and walk to dp[0][0]:
- If s1[i-1] == s2[j-1]: this character is part of the LCS, include it once and move diagonally.
- If dp[i-1][j] >= dp[i][j-1]: s1[i-1] is not part of the LCS here, include it and move up.
- Otherwise: include s2[j-1] and move left.

Wait, I need to think about why this produces a valid supersequence. At each step, we are including a character and advancing the pointer for whichever string it came from. Since we include every character from both strings (LCS chars once, others once each), both s1 and s2 are subsequences of the result. And because we follow the DP table, we use the optimal LCS alignment, giving the shortest possible result.

After reaching (0, 0), any remaining prefix of s1 or s2 gets appended. Then we reverse since we built the string backwards.

Edge cases: if the strings are identical, LCS = the string itself, so SCS = the string (length unchanged). If they share no characters, SCS is just the concatenation.

Time: O(m*n) for LCS + O(m+n) for reconstruction. Space: O(m*n) for the DP table.
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
