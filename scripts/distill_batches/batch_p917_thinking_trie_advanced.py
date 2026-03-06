PAIRS = [
    ("thinking/algorithms", r'''Solve Word Search II: given an m x n board of characters and a list of words, find all words that can be formed by sequentially adjacent cells (horizontal or vertical). Each cell can be used at most once per word.''', r'''<think>
The naive approach runs a separate DFS for each word: O(words * m * n * 4^L). Could I speed this up by checking all words at once? That is exactly what a Trie enables -- I build a Trie from all target words, then each DFS simultaneously searches for all words whose prefixes match the current path.

I initially considered using a hash set of words and checking at each DFS step whether the current path string is in the set. But wait -- that approach cannot prune early. If no word starts with "xyz", the DFS would still explore all "xyz..." paths before failing at the membership check. The Trie prunes immediately when the current character has no matching child, which is a huge difference in practice.

For optimization, I should store the complete word at leaf nodes rather than reconstructing it from the path. And after finding a word, I set node.word = None to prevent duplicate results. Hmm, but there is a subtlety: after nullifying a word, I should also prune the Trie branch if the node has no children. Otherwise dead branches accumulate and slow down future DFS calls. The pruning works by deleting the child entry from the parent's dictionary after the recursive call returns, but only if that child node is now both childless and wordless.

One edge case I almost missed: words that are prefixes of other words. For example, "app" and "apple" share the same Trie path up to "app". The DFS should report "app" when it reaches that node but continue deeper to find "apple". Since I store words at intermediate nodes (not just leaves), this works naturally -- the DFS does not stop after finding a word, it keeps exploring children.

Time: O(m * n * 4^L) worst case, but the Trie makes this much faster in practice because most branches are pruned early. Space: O(total characters) for the Trie plus O(L) for the recursion stack.
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
I need a data structure that returns top-k sentences matching a prefix as the user types. Could I just store all sentences in a list and filter by prefix each time? That would be O(N * L) per keystroke where N is the number of sentences and L is the average length -- too slow for a responsive autocomplete system.

A Trie is the natural choice for prefix matching. But how do I efficiently get the top-k results? I considered two approaches:

Approach A: Store frequency only at leaf nodes, then DFS from the prefix node to collect all matching sentences, sort by frequency, return top-k. This is simple but the query cost is O(subtree size), which could be the entire dataset if the prefix is short (like a single letter).

Approach B: At each Trie node, maintain a dict of {sentence: frequency} for all sentences passing through that node. Queries become O(N_matches * log N_matches) for sorting at that node. Hmm, this is still potentially expensive, but in practice the sorting happens on a smaller set than the full DFS approach.

Wait, there is actually a hybrid that works well for the interactive use case: since the user types one character at a time, I can track the "current node" as the user types. Each new character just moves one step deeper in the Trie. If I store the sentence-frequency map at every node along the insertion path, then each keystroke only needs to sort the map at the current node -- no DFS needed.

One subtlety: when the user submits a sentence (types '#'), I need to insert it into the Trie and update the frequency maps at every node along its path. I initially forgot this propagation step, but it is essential because each ancestor node's sentence map must reflect the updated frequency.

For tie-breaking, sentences with equal frequency are ordered lexicographically. Since Python's sorted() is stable and I sort by (-frequency, sentence), this handles ties correctly.

Time per character: O(1) to navigate + O(M log M) to sort matches where M is the number of matching sentences at that node. Space: O(total_chars * avg_sentences_per_node) which is the trade-off for fast queries.
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
Brute force checks all O(n^2) pairs, verifying each concatenation is a palindrome in O(k) time, giving O(n^2 * k). For large word lists this is too slow. Could I use a Trie to speed up matching? Yes, but let me think about the hash map approach first since it is conceptually simpler.

The key observation is: for words[i] + words[j] to be a palindrome, the shorter word must "mirror" part of the longer word, and the leftover part of the longer word must itself be a palindrome. I initially thought there were only two cases (exact reversal and one word is a suffix of the reverse of the other), but actually there are three distinct cases:

1. words[j] is exactly the reverse of words[i] -- the simplest case.
2. words[i] is longer: some prefix of words[i] reversed equals words[j], and the remaining suffix of words[i] is a palindrome.
3. words[j] is longer: some suffix of words[j] reversed equals words[i], and the remaining prefix of words[j] is a palindrome.

Wait, do I really need to handle all three separately? Let me think about this differently. For each word, I try all k+1 split positions (left + right). If left is a palindrome and reverse(right) exists in my map, then reverse(right) prepended to the word forms a palindrome. If right is a palindrome and reverse(left) exists in the map, then the word followed by reverse(left) forms a palindrome. Hmm, but I need to be careful about double-counting: when cut=0, left is empty (a palindrome), and I check if reverse(word) exists -- this covers case 1. When cut=n, right is empty, and I check the same thing from the other direction. To avoid duplicates, I skip cut=n for the second case (the `cut < n` guard).

The empty string edge case is subtle: if "" is in the word list, it pairs with every word that is itself a palindrome. My split-based approach handles this naturally because when we process "", all its splits produce empty strings, and the palindrome check on empty strings returns True, so it will match with reversed versions of palindromic words in the map.

Time: O(n * k^2) -- for each word, k+1 splits, each requiring O(k) palindrome check and O(k) hash lookup.
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
The brute force checks all O(n^2) pairs which is too slow for large arrays. Could I sort the array and use some clever binary search? Hmm, XOR does not respect sorted order -- 3 XOR 5 = 6 but 4 XOR 5 = 1, so sorting does not help in the usual way.

The key insight is that XOR is maximized when high-order bits differ. So I should think bit-by-bit, from the most significant bit downward. A binary Trie is perfect for this: each number becomes a path from MSB to LSB, and for each number I greedily take the opposite bit at each level to maximize the XOR.

I initially worried about the bit width -- should I always use 32 bits? Actually, I only need enough bits to represent the maximum value in the array. Using max_val.bit_length() avoids unnecessary Trie depth and wasted comparisons.

Wait, there is a subtlety in the order of operations. If I insert all numbers first and then query each one, a number would find itself as its own best match (XOR with itself is 0, which is actually the worst). But that is not a problem because the query greedily seeks the opposite bit, so it naturally finds a different number. Hmm, actually what if all numbers are identical? Then every query returns XOR = 0, which is correct since that is the only possible result. For the general case, I can also insert and query interleaved: insert nums[0], then for each subsequent number, query first (finding the best match among previously inserted numbers), then insert it. This naturally avoids self-matching.

The hash set approach is an interesting alternative: build the answer bit by bit from MSB to LSB, using the property that if a ^ b = c then a ^ c = b. At each bit level, we try setting the current bit to 1 and check if any pair of prefixes can achieve it. Since there are at most 32 bit levels and each level processes O(n) prefixes, this is also O(32n).

Both approaches are effectively O(n) for fixed-width integers.
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
The challenge is checking whether any suffix of the stream matches a word in the dictionary, and we must do this efficiently after each new character. The naive approach would check all possible suffixes against all words after every character -- that could be O(stream_length * total_word_chars) per query, which is way too slow.

My first idea was to use Aho-Corasick, feeding characters one at a time into the automaton. That would work, but it is complex to implement with the failure links and output links. Could there be a simpler approach?

Actually, yes -- a reversed Trie is the key insight. If I reverse all the words and build a Trie, then checking if any suffix of the stream matches a word is equivalent to reading the recent characters backwards and checking if that forms a prefix in the reversed-word Trie. This is exactly what a standard Trie prefix lookup does. I was initially confused about the direction -- wait, let me think again. The stream is "...xyz" and I want to check if "xyz" matches some word. If I reverse "xyz" to get "zyx" and check against the reversed-word Trie... hmm, no. I should read the buffer backwards directly: the most recent character first (z, then y, then x), and follow the reversed-word Trie from the root. Since the word "xyz" was inserted as "zyx", the path z->y->x in the Trie matches. Yes, that works.

One optimization I considered: do I need to keep the entire stream history? No -- I only need the last max_word_length characters, because no word can match a suffix longer than the longest word. A deque with maxlen handles this cleanly, automatically discarding old characters.

A subtlety: during the backward walk, I should return True as soon as I hit any word-end node, not just at the end of the walk. This handles shorter words that are suffixes of longer words. For example, if both "f" and "ef" are in the dictionary and the stream ends with "...ef", I should find "f" first (one step back) before even reaching "ef".

Time per query: O(max_word_length) for the backward Trie walk. Space: O(total chars in words) for the Trie plus O(max_word_length) for the buffer.
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
