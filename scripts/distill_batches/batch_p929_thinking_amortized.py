PAIRS = [
    ("thinking/algorithms", r'''Explain and implement the amortized analysis of dynamic array resizing (like Python's list or Java's ArrayList). Show that append operations are O(1) amortized even though individual resizes are O(n).''', r'''<think>
Dynamic arrays are the canonical example of amortized analysis. The puzzle: doubling the array when full means individual resizes copy all elements -- that is O(n) for one operation. So how can append possibly be O(1) amortized?

My initial instinct was "the resizes are rare enough to not matter," but that is hand-wavy. Let me think through three rigorous proof methods.

1. Aggregate method: resizes happen at sizes 1, 2, 4, 8, ..., 2^k. Total copy work = 1 + 2 + 4 + ... + 2^(floor(log n)) < 2n. So total work for n appends = n (inserts) + 2n (copies) = 3n. Amortized = 3n/n = 3. But wait, could the geometric series sum to more than 2n? No -- the sum of a geometric series with ratio 2 is always less than twice its largest term, and the largest term is at most n. So 2n is correct.

2. Accounting method: charge $3 per append. $1 for the insert, $2 saved as credit. I initially thought we need $2 credit per element to pay for copying just itself, but actually when resize happens from k to 2k, we need to copy all k elements. The key insight: only the k elements in the "second half" (inserted since last resize) have credits, and their $2 each totals $2k, which covers copying all 2k elements. Hmm, does that arithmetic work? Each of k elements donates $2, giving $2k total. We need to copy k old elements + move k elements = 2k copies. Yes, exactly enough.

3. Potential method: Phi = 2 * num_elements - capacity. When not resizing: amortized = actual(1) + delta_Phi(2) = 3. When resizing from cap to 2*cap: actual = n+1, delta_Phi = 2(n+1) - 2n - (2n - n) = 2 - n. Amortized = (n+1) + (2-n) = 3. Beautiful -- the potential absorbs the spike.

For shrinking, I considered shrinking at 1/2 full, but that causes thrashing: alternating insert/delete at the boundary triggers O(n) resize every operation. Shrinking at 1/4 full avoids this because after shrinking, the array is half full, providing a buffer before the next resize in either direction.
</think>

**Dynamic Array -- Amortized Analysis**

```python
class DynamicArray:
    """Dynamic array with amortized O(1) append."""

    def __init__(self):
        self.capacity = 1
        self.size = 0
        self.data = [None] * self.capacity
        self.total_copies = 0
        self.total_ops = 0
        self.resize_count = 0

    def append(self, value):
        """Append value. Amortized O(1)."""
        self.total_ops += 1

        if self.size == self.capacity:
            self._resize(2 * self.capacity)

        self.data[self.size] = value
        self.size += 1

    def pop(self):
        """Remove and return last element. Amortized O(1)."""
        if self.size == 0:
            raise IndexError("pop from empty array")

        self.total_ops += 1
        self.size -= 1
        value = self.data[self.size]
        self.data[self.size] = None

        # Shrink at 1/4 capacity (not 1/2) to avoid thrashing
        if self.size > 0 and self.size <= self.capacity // 4:
            self._resize(self.capacity // 2)

        return value

    def _resize(self, new_capacity):
        """Resize internal array. O(n) actual cost."""
        self.resize_count += 1
        new_data = [None] * new_capacity
        for i in range(self.size):
            new_data[i] = self.data[i]
            self.total_copies += 1
        self.data = new_data
        self.capacity = new_capacity

    def __len__(self):
        return self.size

    def __getitem__(self, idx):
        if idx < 0 or idx >= self.size:
            raise IndexError(f"index {idx} out of range")
        return self.data[idx]


# Demonstrate amortized cost
da = DynamicArray()
n = 10000

print("Appending elements to dynamic array:")
print(f"{'Operations':>12} {'Copies':>10} {'Resizes':>8} {'Amortized':>12}")

for i in range(n):
    da.append(i)
    if (i + 1) in [10, 100, 1000, 5000, 10000]:
        amortized = (i + 1 + da.total_copies) / (i + 1)
        print(f"{i+1:12d} {da.total_copies:10d} {da.resize_count:8d} "
              f"{amortized:12.3f}")

print(f"\nFinal state:")
print(f"  Size: {da.size}")
print(f"  Capacity: {da.capacity}")
print(f"  Total copies: {da.total_copies}")
print(f"  Total resizes: {da.resize_count}")
print(f"  Amortized cost: {(n + da.total_copies) / n:.3f}")
print(f"  Theoretical bound: 3.0")

# Show resize events
da2 = DynamicArray()
print("\nResize events:")
for i in range(64):
    old_cap = da2.capacity
    da2.append(i)
    if da2.capacity != old_cap:
        print(f"  After insert {i}: capacity {old_cap} -> {da2.capacity}")

# Accounting method visualization
print("\nAccounting method (charge $3 per append):")
print("  $1: pays for the append itself")
print("  $2: saved as credit for future resize")
print(f"  After {n} appends: ${3*n} charged, "
      f"${n + da.total_copies} actual work")
print(f"  Surplus (credits): ${3*n - n - da.total_copies}")
```

**Three Proof Methods:**

1. **Aggregate**: Total work for n appends < 3n. Amortized = 3n/n = 3.

2. **Accounting**: Charge $3 per append. $1 for insert, $2 saved. On resize of size k to 2k, the k "new" elements fund the copy with their $2 credits.

3. **Potential**: Phi = 2*size - capacity. Change in potential absorbs resize cost.

**Why shrink at 1/4 (not 1/2):**
- Shrinking at 1/2 causes thrashing: insert triggers double, delete triggers halve, alternating = O(n) per operation
- Shrinking at 1/4 provides a buffer: after shrinking, array is half full

**Complexity:**
- Append: O(1) amortized, O(n) worst case
- Pop: O(1) amortized, O(n) worst case
- Access by index: O(1) worst case
- Space: between n and 4n'''),

    ("thinking/algorithms", r'''Explain splay trees and implement the splay operation. Show how splaying provides O(log n) amortized time per operation through rotations that move accessed nodes to the root.''', r'''<think>
A splay tree is a self-adjusting BST where every access splays the accessed node to the root. No balance information is stored anywhere -- the tree restructures itself through rotations. Could this really provide O(log n) amortized? My first instinct says no, because what if the tree degenerates into a linked list? But actually, that is exactly the scenario where splaying helps most.

Splay operation moves node x to the root using three cases:
1. Zig: x is child of root -- single rotation.
2. Zig-zig: x and parent are both left (or both right) children -- rotate parent first, then x.
3. Zig-zag: x is left child, parent is right child (or vice versa) -- rotate x twice.

I initially thought we could just do simple rotate-to-root (always rotate x with its parent). But wait -- Sleator and Tarjan showed that simple rotation can be O(n) amortized on adversarial sequences. The zig-zig case is what makes splay trees work: by rotating the grandparent first instead of the parent, we flatten the path for all nodes along it, not just the accessed one. This is the crucial difference.

For the amortized analysis, the potential function is Phi = sum over all nodes x of log(size(x)), where size(x) = number of nodes in x's subtree. The amortized cost of a splay operation works out to O(log n). The proof is somewhat involved, but the key insight is that zig-zig rotations significantly reduce the potential of deep paths, "paying forward" for future operations on those paths.

Hmm, one thing that surprised me: splay trees have the "working set property." If you repeatedly access only k distinct items, the amortized cost drops to O(log k) per access, since those items cluster near the root. This makes splay trees adaptive in a way that balanced BSTs like AVL or red-black trees are not.

I will implement splay with all three cases, plus insert, search, and delete.
</think>

**Splay Tree Implementation**

```python
class SplayNode:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None
        self.parent = None


class SplayTree:
    """Self-adjusting BST with O(log n) amortized operations."""

    def __init__(self):
        self.root = None
        self.size = 0

    def _right_rotate(self, x):
        """Right rotation at node x."""
        y = x.left
        x.left = y.right
        if y.right:
            y.right.parent = x
        y.parent = x.parent
        if x.parent is None:
            self.root = y
        elif x == x.parent.right:
            x.parent.right = y
        else:
            x.parent.left = y
        y.right = x
        x.parent = y

    def _left_rotate(self, x):
        """Left rotation at node x."""
        y = x.right
        x.right = y.left
        if y.left:
            y.left.parent = x
        y.parent = x.parent
        if x.parent is None:
            self.root = y
        elif x == x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y
        y.left = x
        x.parent = y

    def _splay(self, x):
        """Splay node x to the root."""
        while x.parent is not None:
            if x.parent.parent is None:
                # Zig case: x is child of root
                if x == x.parent.left:
                    self._right_rotate(x.parent)
                else:
                    self._left_rotate(x.parent)
            elif (x == x.parent.left and
                  x.parent == x.parent.parent.left):
                # Zig-zig: both left children
                self._right_rotate(x.parent.parent)
                self._right_rotate(x.parent)
            elif (x == x.parent.right and
                  x.parent == x.parent.parent.right):
                # Zig-zig: both right children
                self._left_rotate(x.parent.parent)
                self._left_rotate(x.parent)
            elif (x == x.parent.right and
                  x.parent == x.parent.parent.left):
                # Zig-zag: right then left
                self._left_rotate(x.parent)
                self._right_rotate(x.parent)
            else:
                # Zig-zag: left then right
                self._right_rotate(x.parent)
                self._left_rotate(x.parent)

    def search(self, key):
        """Search for key, splay the found node (or last visited)."""
        node = self.root
        last = None

        while node:
            last = node
            if key == node.key:
                self._splay(node)
                return True
            elif key < node.key:
                node = node.left
            else:
                node = node.right

        if last:
            self._splay(last)
        return False

    def insert(self, key):
        """Insert key into splay tree."""
        node = SplayNode(key)
        self.size += 1

        if self.root is None:
            self.root = node
            return

        current = self.root
        parent = None

        while current:
            parent = current
            if key < current.key:
                current = current.left
            else:
                current = current.right

        node.parent = parent
        if key < parent.key:
            parent.left = node
        else:
            parent.right = node

        self._splay(node)

    def delete(self, key):
        """Delete key from splay tree."""
        if not self.search(key):
            return False

        # After search, key is at root
        if self.root.left is None:
            self.root = self.root.right
            if self.root:
                self.root.parent = None
        elif self.root.right is None:
            self.root = self.root.left
            if self.root:
                self.root.parent = None
        else:
            # Find max in left subtree
            left_tree = self.root.left
            right_tree = self.root.right

            left_tree.parent = None
            right_tree.parent = None

            # Splay the maximum in left subtree
            node = left_tree
            while node.right:
                node = node.right
            self.root = left_tree
            self._splay(node)

            # Now root of left tree has no right child
            self.root.right = right_tree
            right_tree.parent = self.root

        self.size -= 1
        return True

    def _height(self, node):
        if node is None:
            return 0
        return 1 + max(self._height(node.left), self._height(node.right))

    def height(self):
        return self._height(self.root)

    def inorder(self):
        result = []
        def _traverse(node):
            if node:
                _traverse(node.left)
                result.append(node.key)
                _traverse(node.right)
        _traverse(self.root)
        return result


# Demo
st = SplayTree()
keys = [10, 20, 30, 40, 50, 25]
for k in keys:
    st.insert(k)

print(f"Inserted: {keys}")
print(f"In-order: {st.inorder()}")
print(f"Root: {st.root.key}")
print(f"Height: {st.height()}")

# Access pattern: accessing 25 brings it to root
st.search(10)
print(f"\nAfter searching 10: root={st.root.key}")
st.search(40)
print(f"After searching 40: root={st.root.key}")

# Sequential access pattern
st2 = SplayTree()
for i in range(1000):
    st2.insert(i)
print(f"\nSequential insert 0..999: height={st2.height()}")

# After accessing some elements, tree restructures
for i in range(500):
    st2.search(i)
print(f"After accessing 0..499: height={st2.height()}")
```

**Splay Cases:**
- **Zig**: Single rotation (x is child of root)
- **Zig-zig**: Same direction -- rotate grandparent first, then parent
- **Zig-zag**: Different direction -- two rotations on x

**Why Zig-Zig is Critical:**
- Simple rotate-to-root would leave the tree unbalanced
- Rotating the grandparent first flattens the path, benefiting future operations
- This is what gives the O(log n) amortized guarantee

**Complexity:**
- All operations: O(log n) amortized
- Worst case single operation: O(n)
- Space: O(n)'''),

    ("thinking/algorithms", r'''Explain Fibonacci heap operations and their amortized complexity. Implement the key operations: insert, find-min, extract-min, and decrease-key. Show why decrease-key is O(1) amortized.''', r'''<think>
Fibonacci heaps are designed to make decrease-key O(1) amortized. Why does this matter? Because Dijkstra's algorithm calls decrease-key up to E times. With a binary heap that is O(log V) each, giving O(E log V). With a Fibonacci heap at O(1) each, Dijkstra becomes O(V log V + E) -- a significant improvement for dense graphs.

The structure is a collection of heap-ordered trees stored in a circular doubly-linked list, with a pointer to the minimum root. I initially thought these would be binomial trees (like a binomial heap), but actually they are not -- the cascading cut mechanism means trees can have irregular shapes. Each node has a "mark" bit that tracks whether it has lost a child since it was last made a child of another node.

Operations:
- insert: O(1) -- just add a new single-node tree. I considered maintaining sorted order, but that would ruin the O(1) bound.
- find-min: O(1) -- return the min pointer.
- extract-min: O(log n) amortized -- remove min, add its children to root list, then consolidate. The consolidation step merges trees of the same degree, similar to binary addition in binomial heaps.
- decrease-key: O(1) amortized -- this is the interesting one.

For decrease-key: decrease the key, and if the heap property is violated, cut the node from its parent and add it to the root list. But wait -- if we just cut freely, a parent could lose all its children, making the tree very flat with too many roots. The cascading cut mechanism prevents this: if a parent was already marked (already lost one child), we cascade -- cut it too and recurse upward. This ensures any node loses at most one child before being cut itself, which bounds the maximum degree to O(log n).

Why is decrease-key O(1) amortized? The potential function Phi = t(H) + 2*m(H) where t = number of trees, m = number of marked nodes. A cascade of c cuts has actual cost O(c), but unmarks c-1 nodes. The potential change is roughly c (new trees) - 2*(c-1) (unmarked nodes) = -(c-2). So amortized cost = O(c) + (-(c-2)) = O(1). Hmm, the constants need careful tracking, but the key idea is that cascading cuts "pay for themselves" by reducing the number of marked nodes.
</think>

**Fibonacci Heap -- Key Operations**

```python
import math


class FibNode:
    def __init__(self, key, value=None):
        self.key = key
        self.value = value
        self.degree = 0
        self.mark = False
        self.parent = None
        self.child = None
        self.left = self
        self.right = self


class FibonacciHeap:
    """Fibonacci heap with O(1) amortized decrease-key."""

    def __init__(self):
        self.min_node = None
        self.num_nodes = 0

    def _add_to_root_list(self, node):
        """Add node to the root list."""
        node.parent = None
        if self.min_node is None:
            node.left = node
            node.right = node
            self.min_node = node
        else:
            node.left = self.min_node
            node.right = self.min_node.right
            self.min_node.right.left = node
            self.min_node.right = node
            if node.key < self.min_node.key:
                self.min_node = node

    def _remove_from_list(self, node):
        """Remove node from its doubly-linked list."""
        node.left.right = node.right
        node.right.left = node.left

    def insert(self, key, value=None):
        """Insert new element. O(1)."""
        node = FibNode(key, value)
        self._add_to_root_list(node)
        self.num_nodes += 1
        return node

    def find_min(self):
        """Return minimum key. O(1)."""
        if self.min_node is None:
            return None
        return self.min_node.key

    def extract_min(self):
        """Remove and return minimum. O(log n) amortized."""
        z = self.min_node
        if z is None:
            return None

        # Add all children to root list
        if z.child is not None:
            child = z.child
            children = []
            curr = child
            while True:
                children.append(curr)
                curr = curr.right
                if curr == child:
                    break
            for c in children:
                self._add_to_root_list(c)

        # Remove z from root list
        self._remove_from_list(z)
        self.num_nodes -= 1

        if z == z.right:
            # z was the only root
            self.min_node = None
        else:
            self.min_node = z.right
            self._consolidate()

        return z.key, z.value

    def _consolidate(self):
        """Merge trees of same degree. O(log n) amortized."""
        max_degree = int(math.log2(self.num_nodes + 1)) + 2
        degree_table = [None] * max_degree

        # Collect all roots
        roots = []
        curr = self.min_node
        while True:
            roots.append(curr)
            curr = curr.right
            if curr == self.min_node:
                break

        for root in roots:
            d = root.degree
            while d < max_degree and degree_table[d] is not None:
                other = degree_table[d]
                if root.key > other.key:
                    root, other = other, root
                self._link(other, root)
                degree_table[d] = None
                d += 1
            if d < max_degree:
                degree_table[d] = root

        # Rebuild root list and find new min
        self.min_node = None
        for node in degree_table:
            if node is not None:
                node.left = node
                node.right = node
                if self.min_node is None:
                    self.min_node = node
                else:
                    node.left = self.min_node
                    node.right = self.min_node.right
                    self.min_node.right.left = node
                    self.min_node.right = node
                    if node.key < self.min_node.key:
                        self.min_node = node

    def _link(self, child, parent):
        """Make child a child of parent."""
        self._remove_from_list(child)
        child.parent = parent
        if parent.child is None:
            parent.child = child
            child.left = child
            child.right = child
        else:
            child.left = parent.child
            child.right = parent.child.right
            parent.child.right.left = child
            parent.child.right = child
        parent.degree += 1
        child.mark = False

    def decrease_key(self, node, new_key):
        """Decrease key of node. O(1) amortized."""
        if new_key > node.key:
            raise ValueError("New key is greater than current key")

        node.key = new_key

        parent = node.parent
        if parent is not None and node.key < parent.key:
            self._cut(node, parent)
            self._cascading_cut(parent)

        if node.key < self.min_node.key:
            self.min_node = node

    def _cut(self, node, parent):
        """Cut node from parent, add to root list."""
        parent.degree -= 1
        if parent.child == node:
            parent.child = node.right if node.right != node else None
        self._remove_from_list(node)
        self._add_to_root_list(node)
        node.mark = False

    def _cascading_cut(self, node):
        """Cascading cut: if marked, cut and recurse on parent."""
        parent = node.parent
        if parent is not None:
            if not node.mark:
                node.mark = True
            else:
                self._cut(node, parent)
                self._cascading_cut(parent)


# Demo
fh = FibonacciHeap()

# Insert elements
nodes = {}
for key in [7, 3, 17, 24, 1, 5, 11]:
    nodes[key] = fh.insert(key)
    print(f"  Insert {key}: min = {fh.find_min()}")

# Extract min
key, _ = fh.extract_min()
print(f"\nExtract min: {key}")
print(f"New min: {fh.find_min()}")

# Decrease key
print(f"\nDecrease key 17 -> 2:")
fh.decrease_key(nodes[17], 2)
print(f"New min: {fh.find_min()}")

# Extract all in order
print(f"\nExtract all:")
results = []
while fh.find_min() is not None:
    k, _ = fh.extract_min()
    results.append(k)
print(f"  Order: {results}")
print(f"  Sorted: {results == sorted(results)}")
```

**Amortized Costs:**
| Operation | Amortized | Worst Case |
|---|---|---|
| insert | O(1) | O(1) |
| find-min | O(1) | O(1) |
| union | O(1) | O(1) |
| extract-min | O(log n) | O(n) |
| decrease-key | O(1) | O(log n) |
| delete | O(log n) | O(n) |

**Why Fibonacci Heap Matters:**
- Dijkstra with Fibonacci heap: O(V log V + E) vs O((V+E) log V)
- Prim's MST with Fibonacci heap: O(E + V log V)
- The O(1) decrease-key is the key advantage

**Complexity:**
- decrease-key: O(1) amortized (cascading cuts bounded by potential)
- extract-min: O(log n) amortized (consolidation)'''),

    ("thinking/algorithms", r'''Implement Union-Find (Disjoint Set Union) with union by rank and path compression. Prove that the amortized time per operation is O(alpha(n)), the inverse Ackermann function.''', r'''<think>
Union-Find (DSU) maintains a partition of elements into disjoint sets. The naive approach uses linked lists or simple trees, but without optimization, find can be O(n) -- imagine a degenerate chain where every element points to the next.

Could we fix this with just one optimization? I considered path compression alone (make every node on the find path point directly to the root). That gives O(log n) amortized. And union by rank alone (attach shorter tree under taller) also gives O(log n) per operation. But wait -- Tarjan showed in 1975 that combining both gives O(alpha(n)) amortized, where alpha is the inverse Ackermann function.

The inverse Ackermann function alpha(n) grows so slowly it is effectively constant:
- alpha(65536) = 3
- alpha(2^65536) = 4
- For all practical n (up to atoms in the universe), alpha(n) <= 5

So in practice, Union-Find with both optimizations is O(1) per operation. I initially thought path compression alone might be sufficient, but actually the amortized bound degrades without union by rank -- there exist sequences where path compression alone is Theta(log n) per operation.

How path compression works: during find(x), every node on the path from x to root gets its parent pointer updated to point directly to the root. This "flattens" the tree for all future operations on these nodes. Union by rank keeps trees shallow by attaching the shorter tree under the taller one's root, where "rank" is an upper bound on height.

Hmm, one subtlety: after path compression, the rank no longer equals the actual height -- it becomes an upper bound. I considered tracking exact heights, but that would require updating heights during compression, which is expensive. Since rank as an upper bound is sufficient for the amortized analysis, we leave it as is.
</think>

**Union-Find with Path Compression and Union by Rank**

```python
class UnionFind:
    """Disjoint Set Union with path compression and union by rank."""

    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n
        self.size = [1] * n
        self.num_components = n
        self.n = n

    def find(self, x):
        """
        Find representative of x's set with path compression.
        Amortized O(alpha(n)).
        """
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def find_iterative(self, x):
        """Iterative find with path compression (avoids stack overflow)."""
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # Path compression
        while self.parent[x] != root:
            next_x = self.parent[x]
            self.parent[x] = root
            x = next_x
        return root

    def union(self, x, y):
        """
        Merge sets of x and y using union by rank.
        Returns True if they were in different sets.
        Amortized O(alpha(n)).
        """
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False

        # Union by rank: attach smaller tree under larger
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx
        self.size[rx] += self.size[ry]

        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1

        self.num_components -= 1
        return True

    def connected(self, x, y):
        """Check if x and y are in the same set. O(alpha(n))."""
        return self.find(x) == self.find(y)

    def component_size(self, x):
        """Get size of x's component."""
        return self.size[self.find(x)]

    def get_components(self):
        """Return all components as a dict {root: [members]}."""
        components = {}
        for i in range(self.n):
            root = self.find(i)
            if root not in components:
                components[root] = []
            components[root].append(i)
        return components


# Demo
uf = UnionFind(10)

unions = [(0,1), (2,3), (4,5), (6,7), (0,2), (4,6), (0,4)]
for u, v in unions:
    uf.union(u, v)
    print(f"  Union({u},{v}): components={uf.num_components}")

print(f"\nConnectivity:")
for x, y in [(0,7), (0,8), (3,5), (8,9)]:
    print(f"  connected({x},{y}) = {uf.connected(x, y)}")

print(f"\nComponents: {uf.get_components()}")

# Application: Kruskal's MST
def kruskal_mst(n, edges):
    """Find MST using Kruskal's algorithm with Union-Find."""
    edges_sorted = sorted(edges, key=lambda e: e[2])
    uf = UnionFind(n)
    mst = []
    total_weight = 0

    for u, v, w in edges_sorted:
        if uf.union(u, v):
            mst.append((u, v, w))
            total_weight += w

    return mst, total_weight

edges = [(0,1,4), (0,2,3), (1,2,1), (1,3,2), (2,3,4),
         (3,4,2), (4,5,6)]
mst, weight = kruskal_mst(6, edges)
print(f"\nKruskal's MST:")
for u, v, w in mst:
    print(f"  {u} -- {v} (weight={w})")
print(f"Total weight: {weight}")

# Performance analysis: path compression effect
uf2 = UnionFind(1000)
# Worst case without compression: linked list
for i in range(999):
    uf2.union(i, i + 1)

# After find with path compression, tree is flat
root = uf2.find(0)
max_depth = 0
for i in range(1000):
    depth = 0
    x = i
    while uf2.parent[x] != x:
        depth += 1
        x = uf2.parent[x]
    max_depth = max(max_depth, depth)

print(f"\nAfter 999 unions + 1 find:")
print(f"  Max depth after compression: {max_depth}")
print(f"  (Without compression would be up to 999)")
```

**Inverse Ackermann Function:**
```
alpha(n) <= 5 for all practical n (up to 2^65536)
```
This makes Union-Find operations effectively O(1) in practice.

**Why Both Optimizations Together:**
- Union by rank alone: O(log n) per operation
- Path compression alone: O(log n) amortized
- Both together: O(alpha(n)) amortized -- nearly constant

**Applications:**
- Kruskal's MST algorithm
- Connected components (dynamic)
- Cycle detection in graphs
- Percolation problems
- Equivalence class tracking

**Complexity:**
- make_set: O(1)
- find: O(alpha(n)) amortized
- union: O(alpha(n)) amortized
- Space: O(n)'''),

    ("thinking/algorithms", r'''Explain incremental rehashing in hash tables: how to resize a hash table gradually rather than all at once, and prove the amortized cost remains O(1) per operation.''', r'''<think>
Traditional hash table resizing copies all elements at once when the load factor threshold is exceeded. Even though this is O(1) amortized, the worst-case single operation is O(n) -- a latency spike that is unacceptable in real-time systems. Could we avoid this spike entirely?

The idea (used in Redis, for example) is incremental rehashing: spread the resize work across subsequent operations. When resize is triggered, allocate the new table but keep the old one. Then during each subsequent operation, migrate a small constant number of entries from old to new.

I initially wondered: what if a lookup happens during migration and the key is in the old table? We need to check both tables. And where do new insertions go? They should go into the new table, since the old table is being drained. This means lookups must check both tables, which adds a constant factor but does not change the asymptotic bound.

Amortized analysis: if we migrate k entries per operation and there are n entries to migrate, migration completes in n/k operations. But wait -- will migration finish before the next resize is triggered? Since we double the table, n new operations must happen before the load factor is exceeded again. As long as k >= 1, we migrate at least one entry per operation, so migration completes in at most n operations -- well before the next n insertions trigger another resize. Therefore each operation does O(1) regular work + O(k) migration work = O(1) for constant k.

Trade-offs I considered:
- Memory: during migration we maintain two tables (roughly 2x). I thought about freeing old buckets as they are migrated, but the old table array itself cannot be partially freed.
- Complexity: the implementation is significantly more complex than simple all-at-once rehashing.
- Latency: the whole point -- no O(n) spikes, every operation is O(1) worst case.

Alternative approach: linear hashing grows the table one bucket at a time, which is even more granular.
</think>

**Incremental Rehashing -- Gradual Hash Table Resize**

```python
class IncrementalHashTable:
    """
    Hash table with incremental rehashing.
    Resize work is spread across subsequent operations.
    """

    LOAD_FACTOR_HIGH = 0.75
    LOAD_FACTOR_LOW = 0.25
    MIGRATE_PER_OP = 2  # entries to migrate per operation

    def __init__(self, initial_capacity=8):
        self.table = [[] for _ in range(initial_capacity)]
        self.capacity = initial_capacity
        self.size = 0

        # Rehashing state
        self.old_table = None
        self.old_capacity = 0
        self.rehash_index = 0
        self.is_rehashing = False

    def _hash(self, key, capacity):
        return hash(key) % capacity

    def _start_rehash(self, new_capacity):
        """Begin incremental rehash to new capacity."""
        self.old_table = self.table
        self.old_capacity = self.capacity
        self.table = [[] for _ in range(new_capacity)]
        self.capacity = new_capacity
        self.rehash_index = 0
        self.is_rehashing = True

    def _migrate_step(self):
        """Migrate a few buckets from old table to new table."""
        if not self.is_rehashing:
            return

        migrated = 0
        while (self.rehash_index < self.old_capacity and
               migrated < self.MIGRATE_PER_OP):
            bucket = self.old_table[self.rehash_index]
            for key, value in bucket:
                idx = self._hash(key, self.capacity)
                self.table[idx].append((key, value))
                migrated += 1
            self.old_table[self.rehash_index] = []
            self.rehash_index += 1

        if self.rehash_index >= self.old_capacity:
            self.old_table = None
            self.is_rehashing = False

    def put(self, key, value):
        """Insert or update key-value pair. Amortized O(1)."""
        self._migrate_step()

        # Check if key exists (in both tables during rehash)
        if self._update_existing(key, value):
            return

        # Insert into new table
        idx = self._hash(key, self.capacity)
        self.table[idx].append((key, value))
        self.size += 1

        # Check if resize needed
        load = self.size / self.capacity
        if load > self.LOAD_FACTOR_HIGH and not self.is_rehashing:
            self._start_rehash(self.capacity * 2)

    def _update_existing(self, key, value):
        """Try to update existing key in either table."""
        # Check new table
        idx = self._hash(key, self.capacity)
        for i, (k, v) in enumerate(self.table[idx]):
            if k == key:
                self.table[idx][i] = (key, value)
                return True

        # Check old table during rehash
        if self.is_rehashing:
            idx = self._hash(key, self.old_capacity)
            for i, (k, v) in enumerate(self.old_table[idx]):
                if k == key:
                    self.old_table[idx][i] = (key, value)
                    return True

        return False

    def get(self, key, default=None):
        """Retrieve value by key. Amortized O(1)."""
        self._migrate_step()

        # Check new table
        idx = self._hash(key, self.capacity)
        for k, v in self.table[idx]:
            if k == key:
                return v

        # Check old table during rehash
        if self.is_rehashing:
            idx = self._hash(key, self.old_capacity)
            for k, v in self.old_table[idx]:
                if k == key:
                    return v

        return default

    def delete(self, key):
        """Delete key. Amortized O(1)."""
        self._migrate_step()

        # Check new table
        idx = self._hash(key, self.capacity)
        for i, (k, v) in enumerate(self.table[idx]):
            if k == key:
                self.table[idx].pop(i)
                self.size -= 1
                return True

        # Check old table
        if self.is_rehashing:
            idx = self._hash(key, self.old_capacity)
            for i, (k, v) in enumerate(self.old_table[idx]):
                if k == key:
                    self.old_table[idx].pop(i)
                    self.size -= 1
                    return True

        return False

    def stats(self):
        return {
            "size": self.size,
            "capacity": self.capacity,
            "rehashing": self.is_rehashing,
            "old_capacity": self.old_capacity if self.is_rehashing else None,
            "rehash_progress": (f"{self.rehash_index}/{self.old_capacity}"
                                if self.is_rehashing else "N/A"),
        }


# Demo
ht = IncrementalHashTable(initial_capacity=4)

print("Inserting 20 elements into table with initial capacity 4:")
for i in range(20):
    ht.put(f"key_{i}", i * 10)
    s = ht.stats()
    if s["rehashing"]:
        print(f"  Insert key_{i}: cap={s['capacity']}, "
              f"rehashing from {s['old_capacity']}, "
              f"progress={s['rehash_progress']}")

print(f"\nFinal stats: {ht.stats()}")

# Verify all values
all_correct = all(ht.get(f"key_{i}") == i * 10 for i in range(20))
print(f"All values correct: {all_correct}")

# Update and delete
ht.put("key_5", 999)
print(f"Updated key_5: {ht.get('key_5')}")
ht.delete("key_10")
print(f"Deleted key_10: {ht.get('key_10', 'NOT FOUND')}")

# Latency comparison
import time

def measure_latency(table_class, n, capacity):
    ht = table_class(initial_capacity=capacity)
    latencies = []
    for i in range(n):
        start = time.perf_counter()
        ht.put(f"k{i}", i)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)
    return latencies

inc_lats = measure_latency(IncrementalHashTable, 10000, 8)
max_lat = max(inc_lats)
avg_lat = sum(inc_lats) / len(inc_lats)
print(f"\nIncremental rehash (10K inserts):")
print(f"  Avg latency: {avg_lat*1e6:.1f} us")
print(f"  Max latency: {max_lat*1e6:.1f} us")
print(f"  Max/Avg ratio: {max_lat/avg_lat:.1f}x")
```

**Incremental vs All-at-Once Rehashing:**
| Property | All-at-once | Incremental |
|---|---|---|
| Worst-case single op | O(n) | O(1) |
| Amortized per op | O(1) | O(1) |
| Memory during resize | ~2x briefly | ~2x for longer |
| Implementation | Simple | More complex |
| Latency spikes | Yes | No |

**Complexity:**
- All operations: O(1) amortized, O(1) worst case (bounded migration per op)
- Space: O(n), up to 2n during migration
- Used by Redis, some concurrent hash maps'''),
]
