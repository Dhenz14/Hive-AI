PAIRS = [
    ("thinking/algorithms", r'''Implement serialization and deserialization of a binary tree. The serialized format should be a string, and deserialization should reconstruct the exact same tree. Handle None/null nodes properly.

Example:
Tree:     1
         / \
        2   3
           / \
          4   5
Serialized: "1,2,#,#,3,4,#,#,5,#,#"''', r'''<think>
Serializing and deserializing a binary tree — I need a format that uniquely represents the tree structure, including null children.

Approach options:
1. Level-order (BFS) serialization — like LeetCode uses. Somewhat complex because trailing nulls can be omitted.
2. Pre-order with null markers — cleaner and easier to deserialize. Each null child is explicitly marked, so the structure is unambiguous.

I'll go with pre-order traversal using "#" for null nodes. This is the simplest approach with a clean recursive deserialization.

Serialization (pre-order DFS):
- Visit root, append value
- Recurse left, recurse right
- For null nodes, append "#"

Deserialization:
- Split the string by commas
- Use an iterator/index to consume tokens one by one
- Read a token: if "#", return None; otherwise create a node, recurse for left child, then right child

Why pre-order works uniquely: because we explicitly mark every null child, the pre-order sequence is unambiguous. The first token is always the root, the next tokens describe the left subtree completely (including all its nulls), then the right subtree.

Wait, could I use level-order (BFS)? It works but deserialization is trickier — need a queue. Pre-order with recursion is cleaner.

Edge cases:
- Empty tree (None root) → serialize to "#"
- Single node → "1,#,#"
- Skewed tree (all left or all right children)
- Negative values
- Large values

Time: O(n) for both serialize and deserialize
Space: O(n) for the serialized string, O(h) for recursion stack where h is tree height

Let me implement this with a Python class.
</think>

## Serialize and Deserialize Binary Tree

```python
from typing import Iterator, List, Optional


class TreeNode:
    """Binary tree node."""

    def __init__(
        self, val: int = 0, left: "Optional[TreeNode]" = None,
        right: "Optional[TreeNode]" = None
    ):
        self.val = val
        self.left = left
        self.right = right

    def __repr__(self) -> str:
        return f"TreeNode({self.val})"


NULL_MARKER = "#"
SEPARATOR = ","


def serialize(root: Optional[TreeNode]) -> str:
    """
    Serialize a binary tree to a comma-separated string using pre-order
    traversal with '#' as null markers.

    Args:
        root: Root of the binary tree (can be None).

    Returns:
        Serialized string representation.
    """
    tokens: List[str] = []

    def _preorder(node: Optional[TreeNode]) -> None:
        if node is None:
            tokens.append(NULL_MARKER)
            return
        tokens.append(str(node.val))
        _preorder(node.left)
        _preorder(node.right)

    _preorder(root)
    return SEPARATOR.join(tokens)


def deserialize(data: str) -> Optional[TreeNode]:
    """
    Deserialize a string back into a binary tree.

    Args:
        data: Serialized string from serialize().

    Returns:
        Root of the reconstructed tree.
    """
    tokens: Iterator[str] = iter(data.split(SEPARATOR))

    def _build() -> Optional[TreeNode]:
        token = next(tokens)
        if token == NULL_MARKER:
            return None
        node = TreeNode(int(token))
        node.left = _build()
        node.right = _build()
        return node

    return _build()


def trees_equal(a: Optional[TreeNode], b: Optional[TreeNode]) -> bool:
    """Check structural and value equality of two trees."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return (
        a.val == b.val
        and trees_equal(a.left, b.left)
        and trees_equal(a.right, b.right)
    )


# --- Test Cases ---

# Test 1: Standard tree
#       1
#      / \
#     2   3
#        / \
#       4   5
root1 = TreeNode(1, TreeNode(2), TreeNode(3, TreeNode(4), TreeNode(5)))
s1 = serialize(root1)
assert s1 == "1,2,#,#,3,4,#,#,5,#,#"
d1 = deserialize(s1)
assert trees_equal(root1, d1)
print(f"Test 1: serialized = '{s1}'")

# Test 2: Empty tree
s2 = serialize(None)
assert s2 == "#"
d2 = deserialize(s2)
assert d2 is None
print(f"Test 2: serialized = '{s2}'")

# Test 3: Single node
root3 = TreeNode(42)
s3 = serialize(root3)
assert s3 == "42,#,#"
d3 = deserialize(s3)
assert trees_equal(root3, d3)
print(f"Test 3: serialized = '{s3}'")

# Test 4: Left-skewed tree
root4 = TreeNode(1, TreeNode(2, TreeNode(3)))
s4 = serialize(root4)
d4 = deserialize(s4)
assert trees_equal(root4, d4)
print(f"Test 4: serialized = '{s4}'")

# Test 5: Negative values
root5 = TreeNode(-1, TreeNode(-2), TreeNode(-3))
s5 = serialize(root5)
d5 = deserialize(s5)
assert trees_equal(root5, d5)
print(f"Test 5: serialized = '{s5}'")

# Test 6: Round-trip fidelity
import random
def build_random_tree(depth: int) -> Optional[TreeNode]:
    if depth <= 0 or random.random() < 0.3:
        return None
    return TreeNode(
        random.randint(-100, 100),
        build_random_tree(depth - 1),
        build_random_tree(depth - 1),
    )

random.seed(42)
root6 = build_random_tree(5)
assert trees_equal(root6, deserialize(serialize(root6)))
print("Test 6: Random tree round-trip passed")
```

**Time Complexity:** O(n) for both serialization and deserialization, where n is the number of nodes (each node and null marker is visited exactly once).

**Space Complexity:** O(n) for the serialized string. Recursion stack is O(h) where h is the tree height (O(n) worst case for skewed trees, O(log n) for balanced).

The pre-order approach with explicit null markers is the cleanest solution. Each node produces exactly one token, and each null produces a "#" marker, making the format unambiguous without needing delimiters for subtree boundaries. The iterator-based deserialization elegantly consumes tokens left-to-right, naturally reconstructing the tree structure.'''),

    ("thinking/algorithms", r'''Implement Lowest Common Ancestor (LCA) queries on a tree using Binary Lifting (also known as the sparse table / Euler tour method). Support O(log n) per query after O(n log n) preprocessing.

Example:
Tree (rooted at 0):
0 - 1 - 3
0 - 1 - 4
0 - 2 - 5
0 - 2 - 6 - 7

LCA(3, 4) = 1
LCA(3, 5) = 0
LCA(5, 7) = 2''', r'''<think>
LCA with Binary Lifting — this is the classic O(n log n) preprocessing, O(log n) per query approach.

The idea:
1. Root the tree at some node (say 0)
2. Compute depth[v] for all vertices
3. Build a sparse table: up[v][k] = the 2^k-th ancestor of v
   - up[v][0] = parent[v]
   - up[v][k] = up[up[v][k-1]][k-1] (the 2^(k-1)-th ancestor of the 2^(k-1)-th ancestor)
4. For LCA(u, v):
   a. Bring the deeper node up to the same depth as the shallower one
   b. If they're the same node, that's the LCA
   c. Otherwise, jump both up by decreasing powers of 2 as long as they don't meet
   d. When they can't jump without meeting, the LCA is one step above: up[u][0]

Let me work through the preprocessing.

Tree structure:
0 -- 1 -- 3
       \-- 4
  \-- 2 -- 5
       \-- 6 -- 7

Depths: 0:0, 1:1, 2:1, 3:2, 4:2, 5:2, 6:2, 7:3
Parents: 0:-1, 1:0, 2:0, 3:1, 4:1, 5:2, 6:2, 7:6

up table (LOG = 3 since n=8, log2(8)=3):
up[v][0] = parent[v]
up[v][1] = up[up[v][0]][0] = grandparent
up[v][2] = up[up[v][1]][1] = 4th ancestor

For LCA(3, 5):
depth[3] = 2, depth[5] = 2 — same depth
Jump k=2: up[3][2] and up[5][2] — both would go beyond root, so they're -1 (same). Skip.
Jump k=1: up[3][1] = up[up[3][0]][0] = up[1][0] = 0. up[5][1] = up[up[5][0]][0] = up[2][0] = 0. Same! Skip.
Jump k=0: up[3][0] = 1, up[5][0] = 2. Different! So jump: u=1, v=2.
Now up[u][0] = up[1][0] = 0. LCA = 0. Correct!

For LCA(5, 7):
depth[5] = 2, depth[7] = 3. Bring 7 up by 1: 3-2=1 = 2^0. u=7, jump 2^0: up[7][0] = 6. Now depth = 2.
Now u=6, v=5, same depth.
Jump k=1: up[6][1] = up[up[6][0]][0] = up[2][0] = 0. up[5][1] = 0. Same! Skip.
Jump k=0: up[6][0] = 2, up[5][0] = 2. Same! Skip.
Both are same after no jumps... wait, they're not the same node. u=6, v=5. Let me re-check.

Actually after equalizing depths: u=6, v=5. They're different nodes at the same depth. Now:
k=1: up[6][1] = 0, up[5][1] = 0. Same → skip.
k=0: up[6][0] = 2, up[5][0] = 2. Same → skip.
Since we skipped all, and u != v... hmm, that means LCA is up[u][0] = 2. But the loop condition should be: we do NOT jump when ancestors are the SAME, we only jump when they're DIFFERENT. After the loop, LCA = up[u][0].

Wait, I need to reconsider. The algorithm is:
After equalizing depths, if u == v, return u.
Otherwise, for k from LOG-1 down to 0:
  if up[u][k] != up[v][k]: jump both
After loop, LCA = up[u][0].

For u=6, v=5: up[6][0]=2, up[5][0]=2. They're equal, so we don't jump. After loop, LCA = up[u][0] = 2. Correct!

Time: O(n log n) preprocessing, O(log n) per query
Space: O(n log n) for the sparse table
</think>

## LCA with Binary Lifting

```python
from collections import deque
from math import log2
from typing import Dict, List, Optional, Tuple


class LCABinaryLifting:
    """
    Lowest Common Ancestor using Binary Lifting.
    O(n log n) preprocessing, O(log n) per query.
    """

    def __init__(self, n: int, edges: List[Tuple[int, int]], root: int = 0):
        """
        Args:
            n: Number of nodes (labeled 0 to n-1).
            edges: Undirected edges of the tree.
            root: Root node.
        """
        self.n = n
        self.root = root
        self.LOG = max(1, int(log2(n)) + 1)

        # Build adjacency list
        self.adj: Dict[int, List[int]] = {i: [] for i in range(n)}
        for u, v in edges:
            self.adj[u].append(v)
            self.adj[v].append(u)

        # Arrays
        self.depth: List[int] = [0] * n
        # up[v][k] = 2^k-th ancestor of v (-1 if doesn't exist)
        self.up: List[List[int]] = [[-1] * self.LOG for _ in range(n)]

        self._preprocess()

    def _preprocess(self) -> None:
        """BFS to compute depths and parent, then fill sparse table."""
        visited = [False] * self.n
        visited[self.root] = True
        queue: deque = deque([self.root])
        self.up[self.root][0] = self.root  # root's parent is itself

        while queue:
            u = queue.popleft()
            for v in self.adj[u]:
                if not visited[v]:
                    visited[v] = True
                    self.depth[v] = self.depth[u] + 1
                    self.up[v][0] = u  # parent
                    queue.append(v)

        # Fill binary lifting table
        for k in range(1, self.LOG):
            for v in range(self.n):
                ancestor = self.up[v][k - 1]
                if ancestor != -1:
                    self.up[v][k] = self.up[ancestor][k - 1]

    def query(self, u: int, v: int) -> int:
        """
        Find the LCA of nodes u and v.

        Args:
            u, v: Node indices.

        Returns:
            LCA node index.
        """
        # Ensure u is the deeper node
        if self.depth[u] < self.depth[v]:
            u, v = v, u

        # Bring u up to the same depth as v
        diff = self.depth[u] - self.depth[v]
        for k in range(self.LOG):
            if (diff >> k) & 1:
                u = self.up[u][k]

        if u == v:
            return u

        # Binary lift both until they diverge
        for k in range(self.LOG - 1, -1, -1):
            if self.up[u][k] != self.up[v][k]:
                u = self.up[u][k]
                v = self.up[v][k]

        return self.up[u][0]


# --- Test Cases ---

# Test 1: Tree from the problem description
#     0
#    / \
#   1   2
#  / \ / \
# 3  4 5  6
#          |
#          7
edges1 = [(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6), (6, 7)]
lca1 = LCABinaryLifting(8, edges1, root=0)

assert lca1.query(3, 4) == 1
assert lca1.query(3, 5) == 0
assert lca1.query(5, 7) == 2
assert lca1.query(3, 7) == 0
assert lca1.query(7, 7) == 7  # same node
assert lca1.query(0, 7) == 0  # root is LCA
print("Test 1: All LCA queries passed")
print(f"  LCA(3,4) = {lca1.query(3,4)}")
print(f"  LCA(3,5) = {lca1.query(3,5)}")
print(f"  LCA(5,7) = {lca1.query(5,7)}")

# Test 2: Chain tree (worst case for depth)
# 0 - 1 - 2 - 3 - 4
edges2 = [(0, 1), (1, 2), (2, 3), (3, 4)]
lca2 = LCABinaryLifting(5, edges2, root=0)
assert lca2.query(0, 4) == 0
assert lca2.query(2, 4) == 2
assert lca2.query(1, 3) == 1
print("\nTest 2: Chain tree queries passed")

# Test 3: Star tree
edges3 = [(0, i) for i in range(1, 6)]
lca3 = LCABinaryLifting(6, edges3, root=0)
for i in range(1, 6):
    for j in range(i + 1, 6):
        assert lca3.query(i, j) == 0
print("Test 3: Star tree - all leaf LCAs are root")
```

**Time Complexity:** O(n log n) preprocessing (BFS + filling the sparse table), O(log n) per LCA query.

**Space Complexity:** O(n log n) for the binary lifting table.

Binary lifting is preferred over naive LCA (O(n) per query) when many queries are needed. The key idea: any upward path of length d can be decomposed into at most O(log d) jumps of power-of-two lengths. The root's parent is set to itself to simplify boundary conditions during lifting.'''),

    ("thinking/algorithms", r'''Implement a Trie (prefix tree) that supports:
1. insert(word) — add a word
2. search(word) — exact match (returns bool)
3. search_with_wildcards(pattern) — where '.' matches any single character
4. starts_with(prefix) — returns all words with that prefix
5. delete(word) — remove a word

Example:
trie.insert("apple")
trie.insert("app")
trie.insert("ape")
trie.search_with_wildcards("ap.") -> ["app", "ape"]
trie.starts_with("app") -> ["app", "apple"]''', r'''<think>
Implementing a full-featured Trie. Let me think through each operation.

The Trie node structure: each node has a dictionary of children (char -> TrieNode) and a flag indicating if this node marks the end of a word. I might also store the count of words passing through each node (useful for delete).

Operations:

1. insert(word): Walk down the trie, creating nodes as needed. Mark the last node as end-of-word.

2. search(word): Walk down the trie following characters. Return True only if we reach the end and the node is marked as end-of-word.

3. search_with_wildcards(pattern): This is the tricky one. '.' can match any character, so at each '.' I need to try ALL children. This requires backtracking / DFS.

   Time complexity for wildcard: O(26^d * m) in the worst case where d is the number of dots and m is pattern length. But in practice, with a sparse trie, it's much faster.

4. starts_with(prefix): Walk down to the prefix node, then collect all words in the subtree (DFS).

5. delete(word): This is the most complex. Options:
   a. Simple: just unmark the end-of-word flag. Doesn't free memory but is safe.
   b. Full cleanup: after unmarking, walk back up and delete nodes that are no longer needed (no other children, not end-of-word).

   I'll implement the full cleanup version. I'll use a counter for how many words pass through each node, which makes deletion cleaner.

Actually, for deletion with cleanup, I can recursively delete: go to the end of the word, unmark it, and on the way back, remove children that have no remaining words and are not end-of-word.

Let me think about the word count approach:
- Each node has a `count` field: how many words pass through this node
- On insert: increment count for each node along the path
- On delete: decrement count; if count reaches 0, remove the child link

Hmm, but that's a bit tricky. Let me just use the recursive approach:
- delete(word): returns True if the child node should be removed
- At leaf (end of word): unmark. If no children, return True (remove me)
- At internal node: recurse into child. If child says remove, delete it. Then if current node has no children and is not end-of-word, return True.

Edge cases for delete:
- Word doesn't exist: do nothing
- Word is prefix of another: only unmark, don't delete nodes
- Another word is prefix of this one: delete only the tail nodes

Let me code this carefully.
</think>

## Full-Featured Trie with Wildcards, Prefix Search, and Deletion

```python
from typing import Dict, List, Optional


class TrieNode:
    """A node in the Trie."""

    __slots__ = ("children", "is_end")

    def __init__(self) -> None:
        self.children: Dict[str, "TrieNode"] = {}
        self.is_end: bool = False


class Trie:
    """
    Trie supporting insert, search, wildcard search, prefix listing,
    and full deletion with node cleanup.
    """

    def __init__(self) -> None:
        self.root = TrieNode()

    def insert(self, word: str) -> None:
        """Insert a word into the trie. O(m) where m = len(word)."""
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.is_end = True

    def search(self, word: str) -> bool:
        """Exact match search. O(m)."""
        node = self._find_node(word)
        return node is not None and node.is_end

    def _find_node(self, prefix: str) -> Optional[TrieNode]:
        """Walk the trie following the prefix. Returns the node or None."""
        node = self.root
        for ch in prefix:
            if ch not in node.children:
                return None
            node = node.children[ch]
        return node

    def search_with_wildcards(self, pattern: str) -> List[str]:
        """
        Search with '.' matching any single character.
        Returns all matching words sorted alphabetically.
        """
        results: List[str] = []

        def _dfs(node: TrieNode, idx: int, path: List[str]) -> None:
            if idx == len(pattern):
                if node.is_end:
                    results.append("".join(path))
                return

            ch = pattern[idx]
            if ch == ".":
                # Try all children
                for c in sorted(node.children):
                    path.append(c)
                    _dfs(node.children[c], idx + 1, path)
                    path.pop()
            else:
                if ch in node.children:
                    path.append(ch)
                    _dfs(node.children[ch], idx + 1, path)
                    path.pop()

        _dfs(self.root, 0, [])
        return results

    def starts_with(self, prefix: str) -> List[str]:
        """Return all words with the given prefix, sorted."""
        node = self._find_node(prefix)
        if node is None:
            return []

        results: List[str] = []

        def _collect(n: TrieNode, path: List[str]) -> None:
            if n.is_end:
                results.append("".join(path))
            for c in sorted(n.children):
                path.append(c)
                _collect(n.children[c], path)
                path.pop()

        _collect(node, list(prefix))
        return results

    def delete(self, word: str) -> bool:
        """
        Delete a word from the trie. Returns True if the word existed.
        Cleans up nodes that are no longer needed.
        """

        def _delete(node: TrieNode, idx: int) -> bool:
            """Returns True if the current node should be removed."""
            if idx == len(word):
                if not node.is_end:
                    return False  # word not found
                node.is_end = False
                return len(node.children) == 0

            ch = word[idx]
            if ch not in node.children:
                return False  # word not found

            should_remove_child = _delete(node.children[ch], idx + 1)

            if should_remove_child:
                del node.children[ch]
                # Remove current node too if it has no children and isn't end
                return not node.is_end and len(node.children) == 0

            return False

        return _delete(self.root, 0) or not self.search(word)


# --- Test Cases ---

trie = Trie()

# Insert words
for word in ["apple", "app", "ape", "bat", "bad", "badge"]:
    trie.insert(word)

# Test 1: Exact search
assert trie.search("apple") is True
assert trie.search("app") is True
assert trie.search("ap") is False  # prefix only, not a word
assert trie.search("batman") is False
print("Test 1: Exact search passed")

# Test 2: Wildcard search
result2a = trie.search_with_wildcards("ap.")
assert set(result2a) == {"app", "ape"}
print(f"Test 2a: 'ap.' matches {result2a}")

result2b = trie.search_with_wildcards("ba.")
assert set(result2b) == {"bat", "bad"}
print(f"Test 2b: 'ba.' matches {result2b}")

result2c = trie.search_with_wildcards(".....")
assert "apple" in result2c and "badge" in result2c
print(f"Test 2c: '.....' matches {result2c}")

# Test 3: Prefix search
result3 = trie.starts_with("app")
assert set(result3) == {"app", "apple"}
print(f"Test 3: starts_with('app') = {result3}")

result3b = trie.starts_with("ba")
assert set(result3b) == {"bat", "bad", "badge"}
print(f"Test 3b: starts_with('ba') = {result3b}")

# Test 4: Delete
trie.delete("app")
assert trie.search("app") is False
assert trie.search("apple") is True  # should still exist
print("Test 4: Deleted 'app', 'apple' still exists")

# Test 5: Delete word that is prefix of nothing — full cleanup
trie.insert("xyz")
assert trie.search("xyz") is True
trie.delete("xyz")
assert trie.search("xyz") is False
print("Test 5: Deleted 'xyz' with full node cleanup")
```

**Time Complexity:**
- insert: O(m) where m is word length
- search: O(m)
- search_with_wildcards: O(26^d * m) worst case where d = number of dots; typically much faster
- starts_with: O(p + k) where p = prefix length, k = total characters in matching words
- delete: O(m) with O(m) recursive cleanup

**Space Complexity:** O(total characters across all words) for trie storage.

The wildcard search uses DFS with backtracking — at each '.' position, it branches into all available children. The delete operation is carefully implemented to clean up orphaned nodes while preserving shared prefixes used by other words.'''),

    ("thinking/algorithms", r'''Given a sorted array, construct a balanced Binary Search Tree (BST). The resulting tree should have minimal height. Return the root and verify it is a valid BST and is balanced.

Example:
Input: [1, 2, 3, 4, 5, 6, 7]
Output: A balanced BST with root 4:
         4
        / \
       2   6
      / \ / \
     1  3 5  7''', r'''<think>
This is a classic divide-and-conquer problem. Since the array is sorted, the middle element should be the root to ensure balance.

Algorithm:
1. Pick the middle element as root
2. Recursively build the left subtree from the left half
3. Recursively build the right subtree from the right half

For even-length arrays, I can pick either the left-middle or right-middle. I'll pick the left-middle (using (low + high) // 2) for consistency.

This is straightforward, but I should also implement verification:
1. BST property: left subtree values < root < right subtree values
2. Balance property: for every node, |height(left) - height(right)| <= 1

Let me trace [1, 2, 3, 4, 5, 6, 7]:
- mid = 3, root = arr[3] = 4
- Left: [1, 2, 3], mid = 1, root = 2
  - Left: [1], root = 1
  - Right: [3], root = 3
- Right: [5, 6, 7], mid = 1 (relative), root = 6
  - Left: [5], root = 5
  - Right: [7], root = 7

Result:
    4
   / \
  2   6
 / \ / \
1  3 5  7

Height = 3, which is minimal for 7 nodes (ceil(log2(8)) = 3).

Edge cases:
- Empty array: return None
- Single element: return single node
- Two elements: one root, one child
- Already a valid BST ordering (which it is, since array is sorted)

Time: O(n) — visit each element once
Space: O(n) for the tree + O(log n) recursion stack
</think>

## Balanced BST from Sorted Array with Verification

```python
from typing import List, Optional, Tuple


class TreeNode:
    """BST node."""

    def __init__(
        self, val: int,
        left: "Optional[TreeNode]" = None,
        right: "Optional[TreeNode]" = None,
    ):
        self.val = val
        self.left = left
        self.right = right


def sorted_array_to_bst(nums: List[int]) -> Optional[TreeNode]:
    """
    Convert a sorted array into a height-balanced BST.

    Args:
        nums: Sorted list of integers (ascending, no duplicates).

    Returns:
        Root of the balanced BST.
    """
    if not nums:
        return None

    def _build(low: int, high: int) -> Optional[TreeNode]:
        if low > high:
            return None
        mid = (low + high) // 2
        node = TreeNode(nums[mid])
        node.left = _build(low, mid - 1)
        node.right = _build(mid + 1, high)
        return node

    return _build(0, len(nums) - 1)


def is_valid_bst(
    root: Optional[TreeNode],
    min_val: float = float("-inf"),
    max_val: float = float("inf"),
) -> bool:
    """Verify BST property: all values in valid range."""
    if root is None:
        return True
    if root.val <= min_val or root.val >= max_val:
        return False
    return (
        is_valid_bst(root.left, min_val, root.val)
        and is_valid_bst(root.right, root.val, max_val)
    )


def is_balanced(root: Optional[TreeNode]) -> Tuple[bool, int]:
    """
    Check if tree is height-balanced. Returns (is_balanced, height).
    """
    if root is None:
        return True, 0

    left_bal, left_h = is_balanced(root.left)
    right_bal, right_h = is_balanced(root.right)

    balanced = left_bal and right_bal and abs(left_h - right_h) <= 1
    return balanced, 1 + max(left_h, right_h)


def inorder(root: Optional[TreeNode]) -> List[int]:
    """In-order traversal to verify sorted order."""
    if root is None:
        return []
    return inorder(root.left) + [root.val] + inorder(root.right)


def tree_height(root: Optional[TreeNode]) -> int:
    if root is None:
        return 0
    return 1 + max(tree_height(root.left), tree_height(root.right))


# --- Test Cases ---

# Test 1: Odd-length array
nums1 = [1, 2, 3, 4, 5, 6, 7]
root1 = sorted_array_to_bst(nums1)
assert root1 is not None
assert root1.val == 4
assert is_valid_bst(root1)
assert is_balanced(root1)[0]
assert inorder(root1) == nums1
print(f"Test 1: root={root1.val}, height={tree_height(root1)}")
print(f"  Valid BST: {is_valid_bst(root1)}, Balanced: {is_balanced(root1)[0]}")

# Test 2: Even-length array
nums2 = [1, 2, 3, 4, 5, 6]
root2 = sorted_array_to_bst(nums2)
assert is_valid_bst(root2)
assert is_balanced(root2)[0]
assert inorder(root2) == nums2
print(f"\nTest 2: root={root2.val}, height={tree_height(root2)}")

# Test 3: Single element
root3 = sorted_array_to_bst([42])
assert root3.val == 42
assert root3.left is None and root3.right is None
print(f"\nTest 3: single node = {root3.val}")

# Test 4: Empty array
root4 = sorted_array_to_bst([])
assert root4 is None
print(f"\nTest 4: empty array -> None")

# Test 5: Two elements
root5 = sorted_array_to_bst([1, 2])
assert is_valid_bst(root5)
assert is_balanced(root5)[0]
assert inorder(root5) == [1, 2]
print(f"\nTest 5: root={root5.val}, inorder={inorder(root5)}")

# Test 6: Large array — verify minimal height
import math
nums6 = list(range(1, 1001))
root6 = sorted_array_to_bst(nums6)
h6 = tree_height(root6)
min_h = math.ceil(math.log2(1001))
assert is_valid_bst(root6)
assert is_balanced(root6)[0]
assert h6 <= min_h + 1
print(f"\nTest 6: 1000 elements, height={h6}, theoretical min~={min_h}")
```

**Time Complexity:** O(n) — each element is visited exactly once during construction.

**Space Complexity:** O(n) for the tree nodes, plus O(log n) recursion stack depth.

The algorithm exploits the sorted order: the middle element is the ideal root since it splits the remaining elements equally between left and right subtrees, guaranteeing O(log n) height. The verification functions (BST validity + balance check) confirm correctness independently, making this suitable for testing and debugging.'''),

    ("thinking/algorithms", r'''Find the diameter of an N-ary tree (the longest path between any two nodes). The tree is given as an adjacency list. Return the diameter length and the actual path.

Example:
Tree:
      0
    / | \
   1  2  3
  /|     |
 4  5    6
    |
    7

Diameter: 5 (path: 4 -> 1 -> 0 -> 3 -> 6, or 7 -> 5 -> 1 -> 0 -> 3 -> 6)''', r'''<think>
The diameter of a tree is the longest path between any two nodes. For an N-ary tree (general tree), I need to find this path.

Classic approach — two BFS:
1. Start BFS from any node, find the farthest node u
2. Start BFS from u, find the farthest node v
3. The path from u to v is the diameter

This works because in a tree, one endpoint of the diameter is always the farthest node from any starting point. Well, actually that's a well-known theorem: the farthest node from any node is always an endpoint of some diameter.

But wait, I also need to return the actual path, not just the length. So I need to track parents during BFS to reconstruct the path.

Alternative approach — single DFS from root:
For each node, compute the two longest paths going down through different children. The diameter passing through that node is the sum of these two. The overall diameter is the max over all nodes.

But this approach is harder to reconstruct the actual path from. Let me stick with the two-BFS approach since it naturally gives the path.

Algorithm:
1. BFS from node 0 (or any node). Record distances and parents. Find farthest node u.
2. BFS from u. Record distances and parents. Find farthest node v. Distance to v is the diameter.
3. Trace parents from v back to u to get the path.

Let me trace the example:
Tree:
      0
    / | \
   1  2  3
  /|     |
 4  5    6
    |
    7

BFS from 0: distances = {0:0, 1:1, 2:1, 3:1, 4:2, 5:2, 6:2, 7:3}
Farthest = 7 (distance 3), or 4 or 6 (distance 2 or 3... wait, 7 is at distance 3)
Actually 4: distance 2, 6: distance 2, 7: distance 3. So farthest is 7.

BFS from 7: 7->5(1)->1(2)->4(3),0(3)->2(4),3(4)->6(5)
Distances: {7:0, 5:1, 1:2, 4:3, 0:3, 2:4, 3:4, 6:5}
Farthest = 6 (distance 5)

Diameter = 5. Path: 6 -> 3 -> 0 -> 1 -> 5 -> 7.

Wait, diameter is typically the number of edges, not nodes. So 5 edges means 6 nodes in the path. Let me check: 7-5-1-0-3-6 is 5 edges. That's the diameter = 5. But the problem says diameter is 5 with path 4->1->0->3->6 which is 4 edges. Let me re-read...

Actually, the problem says "Diameter: 5 (path: 4 -> 1 -> 0 -> 3 -> 6, or 7 -> 5 -> 1 -> 0 -> 3 -> 6)". The path 7->5->1->0->3->6 has 5 edges, and 4->1->0->3->6 has 4 edges. So the diameter should be 5 (the longer path).

So my two-BFS approach gives diameter = 5 (path 7->5->1->0->3->6). Correct.

Edge cases:
- Single node: diameter = 0
- Chain: diameter = n-1
- Star: diameter = 2

Time: O(V + E) = O(n) for a tree (E = n-1)
Space: O(n)
</think>

## Diameter of N-ary Tree with Path Reconstruction

```python
from collections import deque
from typing import Dict, List, Tuple


def tree_diameter(
    n: int, edges: List[Tuple[int, int]]
) -> Tuple[int, List[int]]:
    """
    Find the diameter (longest path) of an N-ary tree.

    Uses the two-BFS approach:
    1. BFS from any node to find a farthest endpoint u
    2. BFS from u to find the other endpoint v
    3. The path u -> v is the diameter

    Args:
        n: Number of nodes (labeled 0 to n-1).
        edges: Undirected edges of the tree.

    Returns:
        Tuple of (diameter_length_in_edges, path_as_node_list).
    """
    if n == 0:
        return 0, []
    if n == 1:
        return 0, [0]

    # Build adjacency list
    adj: Dict[int, List[int]] = {i: [] for i in range(n)}
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    def bfs(start: int) -> Tuple[int, Dict[int, int], Dict[int, int]]:
        """
        BFS from start. Returns (farthest_node, dist_dict, parent_dict).
        """
        dist: Dict[int, int] = {start: 0}
        parent: Dict[int, int] = {start: -1}
        queue: deque = deque([start])
        farthest = start

        while queue:
            u = queue.popleft()
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    parent[v] = u
                    queue.append(v)
                    if dist[v] > dist[farthest]:
                        farthest = v

        return farthest, dist, parent

    # Step 1: Find one endpoint of the diameter
    endpoint1, _, _ = bfs(0)

    # Step 2: Find the other endpoint and the path
    endpoint2, dist2, parent2 = bfs(endpoint1)

    diameter = dist2[endpoint2]

    # Reconstruct path
    path: List[int] = []
    current = endpoint2
    while current != -1:
        path.append(current)
        current = parent2[current]
    path.reverse()

    return diameter, path


# --- Test Cases ---

# Test 1: Tree from problem description
#       0
#     / | \
#    1  2  3
#   /|     |
#  4  5    6
#     |
#     7
edges1 = [(0, 1), (0, 2), (0, 3), (1, 4), (1, 5), (3, 6), (5, 7)]
diam1, path1 = tree_diameter(8, edges1)
assert diam1 == 5
assert len(path1) == 6
assert path1[0] in (6, 7) and path1[-1] in (6, 7)  # endpoints
print(f"Test 1: diameter={diam1}, path={path1}")

# Test 2: Chain
edges2 = [(0, 1), (1, 2), (2, 3), (3, 4)]
diam2, path2 = tree_diameter(5, edges2)
assert diam2 == 4
assert len(path2) == 5
print(f"Test 2: diameter={diam2}, path={path2}")

# Test 3: Star graph
edges3 = [(0, 1), (0, 2), (0, 3), (0, 4)]
diam3, path3 = tree_diameter(5, edges3)
assert diam3 == 2  # any leaf to leaf through center
assert len(path3) == 3
print(f"Test 3: diameter={diam3}, path={path3}")

# Test 4: Single node
diam4, path4 = tree_diameter(1, [])
assert diam4 == 0
assert path4 == [0]
print(f"Test 4: diameter={diam4}, path={path4}")

# Test 5: Two nodes
diam5, path5 = tree_diameter(2, [(0, 1)])
assert diam5 == 1
print(f"Test 5: diameter={diam5}, path={path5}")
```

**Time Complexity:** O(n) — two BFS traversals, each O(V + E) = O(n) since E = n - 1 in a tree.

**Space Complexity:** O(n) — for the distance, parent dictionaries, and BFS queue.

The two-BFS approach is elegant: the first BFS finds a node guaranteed to be an endpoint of some longest path (provable by contradiction — if the farthest node from any arbitrary start weren't a diameter endpoint, we could construct a longer path). The second BFS then finds the actual diameter and path. This is simpler and more efficient than the DFS approach of tracking the two longest child depths at each node.'''),
]
