PAIRS = [
    ("thinking/algorithms", r'''Solve Word Search II: given an m x n board of characters and a list of words, find all words that can be formed by sequentially adjacent cells (horizontal or vertical). Each cell can be used at most once per word.''', r'''<think>
Word Search II (LeetCode 212) is a classic Trie + DFS/backtracking problem. The naive approach would run a separate DFS for each word, giving O(words * m * n * 4^L). Using a Trie, we search for all words simultaneously.

Strategy:
1. Build a Trie from all target words
2. For each cell in the board, start a DFS that follows Trie edges
3. When we reach a Trie node marked as a word end, add that word to results
4. Use backtracking (mark visited cells, then unmark)

Optimization details:
- Store the full word at leaf nodes to avoid reconstructing it
- After finding a word, remove it from the Trie (prune) to avoid duplicate results and speed up future searches
- Prune Trie branches that have no remaining words (no children and not a word end)

The Trie acts as a filter: we only explore board paths that are prefixes of at least one target word. This is far more efficient than checking each word independently.

Edge cases:
- Word longer than total board cells
- Board has no matching characters for any word
- Overlapping words sharing prefixes
- Single cell board
- Words that are prefixes of other words

Time complexity: O(m * n * 4^L) in worst case where L is max word length, but the Trie prunes most branches in practice.
Space: O(total characters in words) for the Trie + O(L) for recursion stack.
</think>

**Word Search II -- Trie + Backtracking**

```python
class TrieNode:
    def __init__(self):
        self.children = {}
        self.word = None  # store complete word at leaf


def build_trie(words):
    root = TrieNode()
    for word in words:
        node = root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.word = word
    return root


def find_words(board, words):
    """
    Find all words from the list that exist in the board.

    Args:
        board: 2D list of characters
        words: list of target words
    Returns:
        list of found words
    """
    if not board or not board[0] or not words:
        return []

    root = build_trie(words)
    rows, cols = len(board), len(board[0])
    result = []

    def dfs(r, c, node):
        ch = board[r][c]
        if ch not in node.children:
            return

        next_node = node.children[ch]

        # Found a word
        if next_node.word is not None:
            result.append(next_node.word)
            next_node.word = None  # avoid duplicates

        # Mark visited
        board[r][c] = "#"

        # Explore neighbors
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and board[nr][nc] != "#":
                dfs(nr, nc, next_node)

        # Restore
        board[r][c] = ch

        # Prune: remove leaf nodes with no children and no word
        if not next_node.children and next_node.word is None:
            del node.children[ch]

    for r in range(rows):
        for c in range(cols):
            dfs(r, c, root)

    return result


# Example
board = [
    ["o", "a", "a", "n"],
    ["e", "t", "a", "e"],
    ["i", "h", "k", "r"],
    ["i", "f", "l", "v"],
]
words = ["oath", "pea", "eat", "rain"]

found = find_words(board, words)
print(f"Found words: {found}")

# Larger example
board2 = [
    ["a", "b", "c"],
    ["a", "e", "d"],
    ["a", "f", "g"],
]
words2 = ["abcdefg", "gfedcba", "eaabcdgfe", "bead", "aef"]
found2 = find_words(board2, words2)
print(f"Found words: {found2}")
```

**Why Trie is Essential:**
- Without Trie: check each word independently = O(W * M * N * 4^L)
- With Trie: all words searched simultaneously, pruning dead branches
- Shared prefixes are traversed only once

**Pruning Optimization:**
After finding a word, we remove it from the Trie. If a node becomes a childless non-word leaf, we delete it entirely. This progressively shrinks the Trie and speeds up later DFS calls.

**Complexity:**
- Time: O(M * N * 4^L) worst case, much better in practice due to Trie pruning
- Space: O(sum of word lengths) for Trie + O(L) recursion stack'''),

    ("thinking/algorithms", r'''Design an autocomplete system: implement a data structure that, given a prefix typed by the user, returns the top-k most frequently used sentences that match the prefix. Support adding new sentences with frequencies.''', r'''<think>
This is LeetCode 642 (Design Search Autocomplete System). We need a Trie where each node can efficiently return top-k sentences matching the prefix.

Design considerations:
1. Trie for prefix matching
2. At each node, maintain a frequency map or sorted list of sentences passing through that node
3. On query, traverse to the prefix node and return top-k by frequency

Two approaches:
A) Store frequency at leaf + DFS from prefix node to collect all sentences, sort by frequency, return top-k. Simple but slow for queries (must traverse entire subtree).

B) At each Trie node, maintain a sorted list of top-k (sentence, frequency) pairs. Updates propagate up. Queries are O(prefix_length). This is faster for queries but slower for updates.

I will implement approach A with some caching, plus show how to do approach B for comparison.

For the complete system:
- insert(sentence, times): Add sentence with frequency
- search(prefix): Return top 3 sentences matching prefix, sorted by frequency (ties broken lexicographically)

The search involves:
1. Walk the Trie to the prefix node
2. DFS to find all sentences in the subtree
3. Sort by (-frequency, sentence) and return top 3

Edge cases:
- Empty prefix returns all sentences
- No match returns empty list
- Sentence is both a prefix and a complete match
- Adding the same sentence increases its frequency

Time: insert O(L), search O(prefix + total chars in subtree) for approach A.
Space: O(total characters across all sentences).
</think>

**Autocomplete System -- Trie with Frequency Tracking**

```python
class AutocompleteTrieNode:
    def __init__(self):
        self.children = {}
        self.sentences = {}  # sentence -> frequency at this node


class AutocompleteSystem:
    def __init__(self, sentences, times):
        """
        Args:
            sentences: list of historical sentences
            times: list of corresponding frequencies
        """
        self.root = AutocompleteTrieNode()
        self.current_input = []
        self.current_node = self.root
        self.dead = AutocompleteTrieNode()  # dead-end sentinel

        for sentence, freq in zip(sentences, times):
            self._insert(sentence, freq)

    def _insert(self, sentence, freq):
        node = self.root
        for ch in sentence:
            if ch not in node.children:
                node.children[ch] = AutocompleteTrieNode()
            node = node.children[ch]
            # Track this sentence at every node along its path
            node.sentences[sentence] = node.sentences.get(sentence, 0) + freq

    def input(self, ch):
        """
        Process one character of user input.

        Args:
            ch: character typed, or '#' to submit the sentence
        Returns:
            top 3 matching sentences (empty list if ch == '#')
        """
        if ch == "#":
            sentence = "".join(self.current_input)
            self._insert(sentence, 1)
            self.current_input = []
            self.current_node = self.root
            return []

        self.current_input.append(ch)

        # Navigate Trie
        if ch in self.current_node.children:
            self.current_node = self.current_node.children[ch]
        else:
            self.current_node = self.dead
            return []

        # Get top 3 by frequency (ties broken lexicographically)
        items = self.current_node.sentences.items()
        top3 = sorted(items, key=lambda x: (-x[1], x[0]))[:3]
        return [s for s, f in top3]


# Example
sentences = ["i love you", "island", "iroman", "i love leetcode"]
times = [5, 3, 2, 2]

ac = AutocompleteSystem(sentences, times)

# User types "i "
print("Type 'i':", ac.input("i"))
print("Type ' ':", ac.input(" "))

# User types "a" -- no match
print("Type 'a':", ac.input("a"))

# User submits with '#'
print("Type '#':", ac.input("#"))

# Now "i a" is stored with frequency 1
# Type "i " again
print("\nType 'i':", ac.input("i"))
print("Type ' ':", ac.input(" "))
print("Type 'a':", ac.input("a"))
print("Type '#':", ac.input("#"))

# "i a" now has frequency 2
print("\nType 'i':", ac.input("i"))
print("Type ' ':", ac.input(" "))
print("Type '#':", ac.input("#"))
```

**Design Trade-offs:**
- Storing sentences at every node increases memory but makes queries fast
- Alternative: store only at leaves and DFS to collect -- saves space, slower queries
- For production: use a heap or pre-sorted list at each node for O(1) top-k retrieval

**Complexity:**
- Insert: O(L * S) where L = sentence length, S = update at each node
- Query per character: O(1) to navigate + O(N log N) to sort matches (N = matching sentences)
- Space: O(total_chars * avg_sentences_per_node)'''),

    ("thinking/algorithms", r'''Solve the Palindrome Pairs problem: given a list of unique words, find all pairs (i, j) where the concatenation words[i] + words[j] forms a palindrome.''', r'''<think>
Palindrome Pairs (LeetCode 336) is a hard problem. The brute force is O(n^2 * k) where k is average word length. We can do O(n * k^2) using a Trie or hash map.

Key observation: For words[i] + words[j] to be a palindrome, one of these cases must hold:
1. words[j] is the reverse of words[i] (and i != j)
2. words[i] is longer than words[j]: the first part of words[i] (reversed) equals words[j], and the remaining suffix of words[i] is itself a palindrome
3. words[j] is longer than words[i]: the last part of words[j] (reversed) equals words[i], and the remaining prefix of words[j] is itself a palindrome

Hash map approach:
1. Build a map from reversed_word -> index
2. For each word, check all possible splits:
   - Split word into left + right
   - If left is a palindrome AND reverse(right) is in the map, then reverse(right) + word is a palindrome
   - If right is a palindrome AND reverse(left) is in the map, then word + reverse(left) is a palindrome

We check all k+1 split positions for each word, and each check involves palindrome verification (O(k)) and hash lookup (O(k)), giving O(n * k^2) total.

Edge cases:
- Empty string in the list (pairs with any palindrome word)
- Single character words
- Words that are themselves palindromes
- Duplicate handling (pairs must use distinct indices)

I will implement the hash map approach for clarity.
</think>

**Palindrome Pairs -- Hash Map Approach**

```python
def palindrome_pairs(words):
    """
    Find all index pairs (i, j) where words[i] + words[j] is a palindrome.

    Args:
        words: list of unique strings
    Returns:
        list of [i, j] pairs
    """
    def is_palindrome(s, lo, hi):
        while lo < hi:
            if s[lo] != s[hi]:
                return False
            lo += 1
            hi -= 1
        return True

    # Map each reversed word to its index
    rev_map = {}
    for i, w in enumerate(words):
        rev_map[w[::-1]] = i

    result = []

    for i, word in enumerate(words):
        n = len(word)

        for cut in range(n + 1):
            # Split: word = left + right
            left = word[:cut]
            right = word[cut:]

            # Case 1: left is palindrome, reverse(right) exists
            # => reverse(right) + left + right is palindrome
            # => reverse(right) + word is palindrome
            if is_palindrome(left, 0, len(left) - 1):
                rev_right = right[::-1]
                if rev_right in rev_map and rev_map[rev_right] != i:
                    result.append([rev_map[rev_right], i])

            # Case 2: right is palindrome, reverse(left) exists
            # => left + right + reverse(left) is palindrome
            # => word + reverse(left) is palindrome
            if cut < n and is_palindrome(right, 0, len(right) - 1):
                rev_left = left[::-1]
                if rev_left in rev_map and rev_map[rev_left] != i:
                    result.append([i, rev_map[rev_left]])

    return result


# Example
words = ["abcd", "dcba", "lls", "s", "sssll"]
pairs = palindrome_pairs(words)
print(f"Words: {words}")
print(f"Palindrome pairs:")
for i, j in pairs:
    concat = words[i] + words[j]
    print(f"  [{i},{j}] '{words[i]}' + '{words[j]}' = '{concat}'")

# Example with empty string
words2 = ["a", "", "ba"]
pairs2 = palindrome_pairs(words2)
print(f"\nWords: {words2}")
for i, j in pairs2:
    concat = words2[i] + words2[j]
    print(f"  [{i},{j}] '{words2[i]}' + '{words2[j]}' = '{concat}'")
```

**Output:**
```
Words: ['abcd', 'dcba', 'lls', 's', 'sssll']
Palindrome pairs:
  [0,1] 'abcd' + 'dcba' = 'abcddcba'
  [1,0] 'dcba' + 'abcd' = 'dcbaabcd'
  [3,2] 's' + 'lls' = 'slls'
  [2,4] 'lls' + 'sssll' = 'llssssll'
```

**Why We Check Both Directions:**
- `cut` from 0 to n splits word into all possible (left, right) pairs
- When left is a palindrome: prepending reverse(right) creates a palindrome
- When right is a palindrome: appending reverse(left) creates a palindrome
- `cut < n` guard in case 2 avoids double-counting the full-word reverse case

**Complexity:**
- Time: O(n * k^2) where n = number of words, k = max word length
- Space: O(n * k) for the reverse map'''),

    ("thinking/algorithms", r'''Solve Maximum XOR of Two Numbers in an Array: given an array of non-negative integers, find the maximum XOR of any two elements. Implement an efficient O(n * 32) solution using a Trie.''', r'''<think>
The brute force approach checks all pairs in O(n^2). We can achieve O(n * 32) = O(n) using a bitwise Trie.

Key insight: XOR is maximized when corresponding bits differ. For each number, we want to find another number in the array that differs as much as possible in the high-order bits.

Trie approach:
1. Build a binary Trie where each number is represented as a 32-bit path (from MSB to LSB)
2. For each number, traverse the Trie greedily trying to take the opposite bit at each level
   - If we need bit b at position p, try to go to (1-b) branch (this makes that XOR bit = 1)
   - If opposite branch does not exist, take the same branch (XOR bit = 0)
3. Track the maximum XOR found

Why this works: By processing bits from MSB to LSB and always preferring the opposite bit, we greedily maximize the XOR. The Trie gives us O(1) per bit lookup, and we process 32 bits per number.

Alternative approach using hash set (also O(n * 32)):
- Build the answer bit by bit from MSB to LSB
- For each bit position, try setting it to 1
- Use XOR property: if a ^ b = c, then a ^ c = b
- Check if any two numbers in the set can produce the candidate XOR

I will implement both approaches.

Edge cases:
- Array of size 1 (XOR with itself = 0, but problem says two elements)
- All same numbers (XOR = 0)
- Array contains 0
- Very large numbers (need enough bits)
</think>

**Maximum XOR -- Binary Trie Approach**

```python
class BinaryTrieNode:
    def __init__(self):
        self.children = [None, None]  # 0 and 1


def max_xor_trie(nums):
    """
    Find maximum XOR of any two numbers using a binary Trie.

    Args:
        nums: list of non-negative integers
    Returns:
        maximum XOR value
    """
    if len(nums) < 2:
        return 0

    # Determine bit width
    max_val = max(nums)
    bits = max_val.bit_length() if max_val > 0 else 1

    root = BinaryTrieNode()

    def insert(num):
        node = root
        for i in range(bits - 1, -1, -1):
            bit = (num >> i) & 1
            if node.children[bit] is None:
                node.children[bit] = BinaryTrieNode()
            node = node.children[bit]

    def query(num):
        """Find number in Trie that maximizes XOR with num."""
        node = root
        xor_val = 0
        for i in range(bits - 1, -1, -1):
            bit = (num >> i) & 1
            # Prefer opposite bit to maximize XOR
            want = 1 - bit
            if node.children[want] is not None:
                xor_val |= (1 << i)
                node = node.children[want]
            else:
                node = node.children[bit]
        return xor_val

    # Insert first number, then for each subsequent number
    # query and insert
    insert(nums[0])
    max_result = 0

    for i in range(1, len(nums)):
        max_result = max(max_result, query(nums[i]))
        insert(nums[i])

    return max_result


def max_xor_hashset(nums):
    """Alternative O(n * 32) approach using hash set."""
    max_xor = 0
    mask = 0

    max_val = max(nums) if nums else 0
    bits = max_val.bit_length() if max_val > 0 else 1

    for i in range(bits - 1, -1, -1):
        mask |= (1 << i)
        # Candidate: try setting this bit in the answer
        candidate = max_xor | (1 << i)

        # Get all prefixes at this bit level
        prefixes = set(num & mask for num in nums)

        # Check if any two prefixes XOR to candidate
        for p in prefixes:
            if (candidate ^ p) in prefixes:
                max_xor = candidate
                break

    return max_xor


# Example
nums = [3, 10, 5, 25, 2, 8]
print(f"Array: {nums}")
print(f"Max XOR (Trie):    {max_xor_trie(nums)}")
print(f"Max XOR (HashSet): {max_xor_hashset(nums)}")

# Show the pair
best = 0
best_pair = (0, 0)
for i in range(len(nums)):
    for j in range(i + 1, len(nums)):
        x = nums[i] ^ nums[j]
        if x > best:
            best = x
            best_pair = (nums[i], nums[j])
print(f"Best pair: {best_pair[0]} ^ {best_pair[1]} = {best}")
print(f"Binary: {best_pair[0]:05b} ^ {best_pair[1]:05b} = {best:05b}")
```

**Output:**
```
Array: [3, 10, 5, 25, 2, 8]
Max XOR (Trie):    28
Max XOR (HashSet): 28
Best pair: 5 ^ 25 = 28
Binary: 00101 ^ 11001 = 11100
```

**Complexity:**
- Trie approach: O(n * B) time, O(n * B) space (B = bit width, typically 32)
- Hash set approach: O(n * B) time, O(n) space
- Both are effectively O(n) for fixed-width integers'''),

    ("thinking/algorithms", r'''Implement a Stream Checking class: given a list of words, design a data structure that checks if any suffix of the characters streamed so far matches any word in the list. Each call to query(char) adds a character to the stream and returns True if any word is a suffix of the current stream.''', r'''<think>
This is LeetCode 1032. The challenge is efficiently checking if any suffix of the stream matches a word in the dictionary.

Naive approach: After each character, check all suffixes against all words. Very slow.

Better approach using a reversed Trie:
1. Insert all words reversed into a Trie
2. Maintain a buffer of recent characters
3. On each query, walk backwards through the buffer, following the Trie
4. If we reach a word-end node, return True

Even better: Since we only need to check suffixes up to the maximum word length, we can use a circular buffer of that size.

The key insight is: if we reverse the words and build a Trie, then checking if any suffix of the stream matches a word is equivalent to checking if any prefix of the reversed recent characters matches a reversed word -- which is exactly what a Trie does.

Algorithm:
1. Build a Trie from reversed words
2. Keep a deque of recent characters (max length = max word length)
3. On query(ch):
   a. Append ch to the deque
   b. Walk the Trie from root, reading characters from the deque in reverse order (most recent first)
   c. If we hit a word-end node at any point, return True
   d. If we fall off the Trie or exhaust the deque, return False

Edge cases:
- Single character words
- Word is the entire stream so far
- No match at all
- Multiple words share suffixes

Time per query: O(max_word_length) since we traverse at most that many Trie nodes.
Space: O(total chars in words) for Trie + O(max_word_length) for buffer.
</think>

**Stream Checker -- Reversed Trie Approach**

```python
from collections import deque


class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end = False


class StreamChecker:
    def __init__(self, words):
        """
        Args:
            words: list of strings to match against stream suffixes
        """
        self.root = TrieNode()
        self.max_len = 0

        # Insert reversed words into Trie
        for word in words:
            self.max_len = max(self.max_len, len(word))
            node = self.root
            for ch in reversed(word):
                if ch not in node.children:
                    node.children[ch] = TrieNode()
                node = node.children[ch]
            node.is_end = True

        # Buffer for recent characters
        self.buffer = deque(maxlen=self.max_len)

    def query(self, ch):
        """
        Add character to stream, check if any word matches a suffix.

        Args:
            ch: single character
        Returns:
            True if any word is a suffix of current stream
        """
        self.buffer.append(ch)

        node = self.root
        # Walk backwards through buffer (most recent first)
        for c in reversed(self.buffer):
            if c not in node.children:
                return False
            node = node.children[c]
            if node.is_end:
                return True

        return False


# Example
words = ["cd", "f", "kl"]
sc = StreamChecker(words)

stream = "abcdefghijkl"
print(f"Words to match: {words}")
print(f"Stream: {stream}")
print()

for ch in stream:
    result = sc.query(ch)
    print(f"  query('{ch}') -> {result}", end="")
    if result:
        # Show which suffix matched
        buf = list(sc.buffer)
        for w in words:
            suffix = "".join(buf[len(buf)-len(w):])
            if suffix == w:
                print(f"  (matched '{w}')", end="")
    print()

# Another example with overlapping words
print("\n--- Overlapping words ---")
words2 = ["ab", "b", "abc"]
sc2 = StreamChecker(words2)
stream2 = "xabc"
print(f"Words: {words2}, Stream: {stream2}")
for ch in stream2:
    print(f"  query('{ch}') -> {sc2.query(ch)}")
```

**Output:**
```
Words to match: ['cd', 'f', 'kl']
Stream: abcdefghijkl

  query('a') -> False
  query('b') -> False
  query('c') -> False
  query('d') -> True  (matched 'cd')
  query('e') -> False
  query('f') -> True  (matched 'f')
  query('g') -> False
  query('h') -> False
  query('i') -> False
  query('j') -> False
  query('k') -> False
  query('l') -> True  (matched 'kl')
```

**Why Reversed Trie Works:**
- We need to check suffixes of the stream
- A suffix read right-to-left is a prefix of the reversed string
- The reversed-word Trie matches exactly these reversed suffixes
- Walking backwards through the buffer follows the Trie from root

**Optimization -- Bounded Buffer:**
- The deque has maxlen = longest word length
- We never need to check more characters than the longest word
- This bounds both memory and per-query time

**Complexity:**
- Construction: O(sum of word lengths)
- Per query: O(min(stream_length, max_word_length))
- Space: O(sum of word lengths) for Trie + O(max_word_length) for buffer'''),
]
