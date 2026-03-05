PAIRS = [
    (
        "algorithms/advanced-tree-structures-btree-redblack-trie",
        "Explain advanced tree data structures including B-tree insertion and splitting, red-black tree rotations and rebalancing, and trie-based data structures for prefix matching with complete implementations and complexity analysis",
        r"""# Advanced Tree Data Structures: B-Trees, Red-Black Trees, and Tries

## B-Trees: Optimized for Disk Access

B-trees are the backbone of database indexing and file systems **because** they minimize disk I/O by maximizing the branching factor. Unlike binary trees where each node has at most 2 children, a B-tree of order `m` can have up to `m` children per node. This matters **because** disk reads fetch entire blocks (4KB-16KB), and a wider tree means fewer block reads to find any key.

### B-Tree Implementation

```python
from __future__ import annotations
from typing import TypeVar, Generic, Optional, List, Tuple
from dataclasses import dataclass, field

K = TypeVar("K")
V = TypeVar("V")

@dataclass
class BTreeNode(Generic[K, V]):
    # Each node stores keys and optional values
    # Internal nodes also have children pointers
    keys: list[K] = field(default_factory=list)
    values: list[V] = field(default_factory=list)
    children: list[BTreeNode[K, V]] = field(default_factory=list)
    leaf: bool = True

    @property
    def num_keys(self) -> int:
        return len(self.keys)

class BTree(Generic[K, V]):
    # B-tree of order t (minimum degree)
    # Each node has between t-1 and 2t-1 keys (except root)
    # Best practice: choose t based on disk block size
    # t = block_size / (key_size + pointer_size)

    def __init__(self, t: int = 3):
        self.t = t  # Minimum degree
        self.root = BTreeNode[K, V](leaf=True)

    def search(self, key: K) -> Optional[V]:
        return self._search_node(self.root, key)

    def _search_node(self, node: BTreeNode[K, V], key: K) -> Optional[V]:
        # Binary search within node keys — O(log t)
        i = 0
        while i < node.num_keys and key > node.keys[i]:
            i += 1

        if i < node.num_keys and key == node.keys[i]:
            return node.values[i]

        if node.leaf:
            return None

        # Recurse into appropriate child
        return self._search_node(node.children[i], key)

    def insert(self, key: K, value: V) -> None:
        root = self.root
        # If root is full, split it first (tree grows upward)
        # Common mistake: trying to grow the tree downward
        if root.num_keys == 2 * self.t - 1:
            new_root = BTreeNode[K, V](leaf=False)
            new_root.children.append(self.root)
            self._split_child(new_root, 0)
            self.root = new_root

        self._insert_non_full(self.root, key, value)

    def _insert_non_full(self, node: BTreeNode[K, V], key: K, value: V) -> None:
        i = node.num_keys - 1

        if node.leaf:
            # Insert into leaf — shift keys right to make room
            node.keys.append(key)  # Placeholder
            node.values.append(value)
            while i >= 0 and key < node.keys[i]:
                node.keys[i + 1] = node.keys[i]
                node.values[i + 1] = node.values[i]
                i -= 1
            node.keys[i + 1] = key
            node.values[i + 1] = value
        else:
            # Find child to descend into
            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1

            # Split child if full (proactive splitting)
            # Therefore, we never need to backtrack up the tree
            if node.children[i].num_keys == 2 * self.t - 1:
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1

            self._insert_non_full(node.children[i], key, value)

    def _split_child(self, parent: BTreeNode[K, V], i: int) -> None:
        # Split parent.children[i] into two nodes
        # Middle key moves up to parent
        t = self.t
        full_node = parent.children[i]
        new_node = BTreeNode[K, V](leaf=full_node.leaf)

        # Move upper half of keys to new node
        mid = t - 1
        new_node.keys = full_node.keys[mid + 1:]
        new_node.values = full_node.values[mid + 1:]

        if not full_node.leaf:
            new_node.children = full_node.children[mid + 1:]

        # Promote middle key to parent
        parent.keys.insert(i, full_node.keys[mid])
        parent.values.insert(i, full_node.values[mid])
        parent.children.insert(i + 1, new_node)

        # Truncate the original node
        full_node.keys = full_node.keys[:mid]
        full_node.values = full_node.values[:mid]
        if not full_node.leaf:
            full_node.children = full_node.children[:mid + 1]

    def traverse(self) -> list[tuple[K, V]]:
        # In-order traversal returns sorted keys
        result: list[tuple[K, V]] = []
        self._traverse_node(self.root, result)
        return result

    def _traverse_node(self, node: BTreeNode[K, V], result: list[tuple[K, V]]) -> None:
        for i in range(node.num_keys):
            if not node.leaf:
                self._traverse_node(node.children[i], result)
            result.append((node.keys[i], node.values[i]))
        if not node.leaf:
            self._traverse_node(node.children[node.num_keys], result)

# --- Testing B-tree correctness ---
def test_btree():
    tree: BTree[int, str] = BTree(t=2)  # 2-3-4 tree (order 4)

    # Insert keys in random order
    data = [(5, "e"), (3, "c"), (7, "g"), (1, "a"), (4, "d"),
            (6, "f"), (8, "h"), (2, "b"), (9, "i"), (10, "j")]
    for k, v in data:
        tree.insert(k, v)

    # Verify search
    assert tree.search(5) == "e"
    assert tree.search(1) == "a"
    assert tree.search(10) == "j"
    assert tree.search(99) is None

    # Verify sorted traversal
    traversed = tree.traverse()
    keys = [k for k, v in traversed]
    assert keys == sorted(keys), f"Not sorted: {keys}"
    assert len(keys) == 10

    print("B-tree tests passed")

test_btree()
```

### Red-Black Tree with Rotations

**However**, for in-memory use cases where cache performance matters more than disk I/O, red-black trees offer a better **trade-off**. They guarantee O(log n) operations with at most 2 rotations per insertion, making them the choice for `std::map` (C++), `TreeMap` (Java), and Linux's CFS scheduler.

```python
from enum import Enum

class Color(Enum):
    RED = 0
    BLACK = 1

@dataclass
class RBNode:
    key: int
    value: object = None
    color: Color = Color.RED
    left: Optional[RBNode] = None
    right: Optional[RBNode] = None
    parent: Optional[RBNode] = None

class RedBlackTree:
    # Properties that must hold:
    # 1. Every node is red or black
    # 2. Root is black
    # 3. Every leaf (NIL) is black
    # 4. Red node cannot have red children
    # 5. All paths from node to leaves have same black count
    # Pitfall: forgetting to maintain property 5 after rotations

    def __init__(self):
        self.NIL = RBNode(key=0, color=Color.BLACK)
        self.root = self.NIL

    def insert(self, key: int, value: object = None) -> None:
        node = RBNode(key=key, value=value, color=Color.RED,
                       left=self.NIL, right=self.NIL)

        # Standard BST insert
        parent = None
        current = self.root
        while current != self.NIL:
            parent = current
            if key < current.key:
                current = current.left
            elif key > current.key:
                current = current.right
            else:
                current.value = value  # Update existing
                return

        node.parent = parent
        if parent is None:
            self.root = node
        elif key < parent.key:
            parent.left = node
        else:
            parent.right = node

        self._fix_insert(node)

    def _fix_insert(self, node: RBNode) -> None:
        # Fix red-black violations after insertion
        # Therefore, we restore all 5 properties
        while node != self.root and node.parent.color == Color.RED:
            if node.parent == node.parent.parent.left:
                uncle = node.parent.parent.right

                if uncle.color == Color.RED:
                    # Case 1: Uncle is red — recolor
                    node.parent.color = Color.BLACK
                    uncle.color = Color.BLACK
                    node.parent.parent.color = Color.RED
                    node = node.parent.parent
                else:
                    if node == node.parent.right:
                        # Case 2: Node is right child — left rotate parent
                        node = node.parent
                        self._left_rotate(node)
                    # Case 3: Node is left child — right rotate grandparent
                    node.parent.color = Color.BLACK
                    node.parent.parent.color = Color.RED
                    self._right_rotate(node.parent.parent)
            else:
                # Mirror cases for right subtree
                uncle = node.parent.parent.left

                if uncle.color == Color.RED:
                    node.parent.color = Color.BLACK
                    uncle.color = Color.BLACK
                    node.parent.parent.color = Color.RED
                    node = node.parent.parent
                else:
                    if node == node.parent.left:
                        node = node.parent
                        self._right_rotate(node)
                    node.parent.color = Color.BLACK
                    node.parent.parent.color = Color.RED
                    self._left_rotate(node.parent.parent)

        self.root.color = Color.BLACK

    def _left_rotate(self, x: RBNode) -> None:
        y = x.right
        x.right = y.left
        if y.left != self.NIL:
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

    def _right_rotate(self, y: RBNode) -> None:
        x = y.left
        y.left = x.right
        if x.right != self.NIL:
            x.right.parent = y
        x.parent = y.parent
        if y.parent is None:
            self.root = x
        elif y == y.parent.right:
            y.parent.right = x
        else:
            y.parent.left = x
        x.right = y
        y.parent = x

    def search(self, key: int) -> Optional[object]:
        node = self._search_node(self.root, key)
        return node.value if node != self.NIL else None

    def _search_node(self, node: RBNode, key: int) -> RBNode:
        if node == self.NIL or key == node.key:
            return node
        if key < node.key:
            return self._search_node(node.left, key)
        return self._search_node(node.right, key)

    def inorder(self) -> list[int]:
        result: list[int] = []
        self._inorder(self.root, result)
        return result

    def _inorder(self, node: RBNode, result: list[int]) -> None:
        if node != self.NIL:
            self._inorder(node.left, result)
            result.append(node.key)
            self._inorder(node.right, result)

    def black_height(self) -> int:
        # Count black nodes on any root-to-leaf path
        count = 0
        node = self.root
        while node != self.NIL:
            if node.color == Color.BLACK:
                count += 1
            node = node.left
        return count

# --- Testing ---
def test_rbtree():
    tree = RedBlackTree()
    import random
    keys = list(range(1, 101))
    random.shuffle(keys)
    for k in keys:
        tree.insert(k, f"val-{k}")

    # Verify sorted order
    inorder = tree.inorder()
    assert inorder == sorted(inorder)
    assert len(inorder) == 100

    # Verify search
    assert tree.search(42) == "val-42"
    assert tree.search(999) is None

    # Verify root is black
    assert tree.root.color == Color.BLACK

    print(f"RB-tree tests passed, black height: {tree.black_height()}")

test_rbtree()
```

### Trie for Prefix Matching

Tries (prefix trees) provide O(k) lookup where k is the key length — independent of the number of stored keys. This makes them ideal for autocomplete, IP routing tables, and spell checkers. The **best practice** is to use compressed tries (Patricia/radix trees) when memory is a concern.

```python
@dataclass
class TrieNode:
    children: dict[str, TrieNode] = field(default_factory=dict)
    is_end: bool = False
    value: object = None
    # For autocomplete ranking
    frequency: int = 0

class Trie:
    def __init__(self):
        self.root = TrieNode()
        self._size = 0

    def insert(self, key: str, value: object = None, frequency: int = 1) -> None:
        node = self.root
        for char in key:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        if not node.is_end:
            self._size += 1
        node.is_end = True
        node.value = value
        node.frequency = frequency

    def search(self, key: str) -> Optional[object]:
        node = self._find_node(key)
        if node and node.is_end:
            return node.value
        return None

    def starts_with(self, prefix: str) -> list[tuple[str, int]]:
        # Return all words with given prefix, sorted by frequency
        node = self._find_node(prefix)
        if node is None:
            return []
        results: list[tuple[str, int]] = []
        self._collect_words(node, prefix, results)
        results.sort(key=lambda x: -x[1])  # Sort by frequency desc
        return results

    def _find_node(self, prefix: str) -> Optional[TrieNode]:
        node = self.root
        for char in prefix:
            if char not in node.children:
                return None
            node = node.children[char]
        return node

    def _collect_words(
        self, node: TrieNode, prefix: str,
        results: list[tuple[str, int]]
    ) -> None:
        if node.is_end:
            results.append((prefix, node.frequency))
        for char, child in sorted(node.children.items()):
            self._collect_words(child, prefix + char, results)

    def delete(self, key: str) -> bool:
        return self._delete_recursive(self.root, key, 0)

    def _delete_recursive(self, node: TrieNode, key: str, depth: int) -> bool:
        if depth == len(key):
            if not node.is_end:
                return False
            node.is_end = False
            self._size -= 1
            return len(node.children) == 0
        char = key[depth]
        if char not in node.children:
            return False
        should_delete = self._delete_recursive(node.children[char], key, depth + 1)
        if should_delete:
            del node.children[char]
            return not node.is_end and len(node.children) == 0
        return False

    def __len__(self) -> int:
        return self._size

# --- Autocomplete system using trie ---
def test_trie():
    trie = Trie()
    words = [
        ("python", 100), ("pytorch", 80), ("pandas", 90),
        ("pydantic", 70), ("pylint", 40), ("pytest", 85),
        ("java", 60), ("javascript", 95),
    ]
    for word, freq in words:
        trie.insert(word, value=word, frequency=freq)

    # Prefix search
    py_words = trie.starts_with("py")
    assert len(py_words) == 6
    assert py_words[0][0] == "python"  # Highest frequency first

    # Exact search
    assert trie.search("python") == "python"
    assert trie.search("pyth") is None

    # Delete
    assert trie.delete("pylint")
    assert trie.search("pylint") is None
    assert len(trie.starts_with("py")) == 5

    print("Trie tests passed")

test_trie()
```

## Summary and Key Takeaways

- **B-trees** minimize disk I/O by maximizing branching factor — choose order `t` based on disk block size for optimal performance
- **Red-black trees** guarantee O(log n) with at most 2 rotations per insert — preferred for in-memory sorted containers
- A **common mistake** with B-trees is growing the tree downward; it always grows upward by splitting the root
- **Tries** provide O(k) lookup independent of dataset size — ideal for prefix matching and autocomplete
- The **trade-off** between B-trees and red-black trees: B-trees are better for disk, red-black for memory-bound operations
- The **pitfall** of naive trie implementation is memory usage — each node with a full HashMap wastes space for sparse character sets
- **Compressed tries** (radix trees) reduce memory by merging single-child paths into single nodes"""
    ),
    (
        "algorithms/graph-algorithms-shortest-path-mst-topological",
        "Implement and compare graph algorithms including Dijkstra's shortest path with priority queue optimization, A* search with heuristic design, minimum spanning tree with Kruskal's union-find and Prim's approaches, and topological sorting for dependency resolution",
        r"""# Graph Algorithms: Shortest Paths, MST, and Topological Sort

## Graph Representation and Dijkstra's Algorithm

Choosing the right graph representation is the first critical decision. **Adjacency lists** use O(V + E) space and are efficient for sparse graphs (most real-world graphs), while **adjacency matrices** use O(V^2) space but offer O(1) edge lookup. **Because** most practical graphs are sparse (social networks, road maps, dependency graphs), adjacency lists are the default choice.

### Dijkstra and A* Implementation

```python
from __future__ import annotations
import heapq
from typing import TypeVar, Generic, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import math

T = TypeVar("T")

@dataclass
class Edge:
    to: int
    weight: float

class WeightedGraph:
    def __init__(self, num_vertices: int):
        self.V = num_vertices
        self.adj: list[list[Edge]] = [[] for _ in range(num_vertices)]

    def add_edge(self, u: int, v: int, weight: float, directed: bool = False) -> None:
        self.adj[u].append(Edge(to=v, weight=weight))
        if not directed:
            self.adj[v].append(Edge(to=u, weight=weight))

    def dijkstra(self, source: int) -> tuple[list[float], list[int]]:
        # O((V + E) log V) with binary heap
        # Best practice: use a min-heap with lazy deletion
        dist = [math.inf] * self.V
        prev = [-1] * self.V
        dist[source] = 0.0

        # (distance, vertex) — min-heap ordered by distance
        pq: list[tuple[float, int]] = [(0.0, source)]
        visited = set()

        while pq:
            d, u = heapq.heappop(pq)
            if u in visited:
                continue  # Lazy deletion — skip outdated entries
            visited.add(u)

            for edge in self.adj[u]:
                new_dist = d + edge.weight
                if new_dist < dist[edge.to]:
                    dist[edge.to] = new_dist
                    prev[edge.to] = u
                    heapq.heappush(pq, (new_dist, edge.to))

        return dist, prev

    def reconstruct_path(self, prev: list[int], target: int) -> list[int]:
        path = []
        current = target
        while current != -1:
            path.append(current)
            current = prev[current]
        path.reverse()
        return path

    def astar(
        self, source: int, target: int,
        heuristic: Callable[[int], float],
    ) -> tuple[float, list[int]]:
        # A* = Dijkstra + heuristic guidance
        # Trade-off: faster than Dijkstra for single-target queries
        # but requires admissible heuristic (never overestimates)
        # Pitfall: inadmissible heuristic can return suboptimal paths

        g_score = [math.inf] * self.V
        g_score[source] = 0.0
        f_score = [math.inf] * self.V
        f_score[source] = heuristic(source)
        prev = [-1] * self.V

        # (f_score, g_score, vertex) — tie-break on g_score
        open_set: list[tuple[float, float, int]] = [
            (f_score[source], 0.0, source)
        ]
        closed_set: set[int] = set()

        while open_set:
            f, g, u = heapq.heappop(open_set)
            if u == target:
                return g_score[target], self.reconstruct_path(prev, target)

            if u in closed_set:
                continue
            closed_set.add(u)

            for edge in self.adj[u]:
                v = edge.to
                if v in closed_set:
                    continue
                tentative_g = g_score[u] + edge.weight
                if tentative_g < g_score[v]:
                    g_score[v] = tentative_g
                    f_score[v] = tentative_g + heuristic(v)
                    prev[v] = u
                    heapq.heappush(open_set, (f_score[v], tentative_g, v))

        return math.inf, []  # No path found

# --- Grid-based A* example ---
def manhattan_distance(
    positions: dict[int, tuple[int, int]], target: int
) -> Callable[[int], float]:
    tx, ty = positions[target]
    def heuristic(node: int) -> float:
        nx, ny = positions[node]
        return abs(nx - tx) + abs(ny - ty)
    return heuristic

def test_shortest_path():
    # Create a small weighted graph
    g = WeightedGraph(6)
    g.add_edge(0, 1, 4)
    g.add_edge(0, 2, 1)
    g.add_edge(2, 1, 2)
    g.add_edge(1, 3, 1)
    g.add_edge(2, 3, 5)
    g.add_edge(3, 4, 3)
    g.add_edge(4, 5, 1)

    dist, prev = g.dijkstra(0)
    assert dist[3] == 4.0  # 0->2->1->3
    assert dist[5] == 8.0  # 0->2->1->3->4->5

    path = g.reconstruct_path(prev, 5)
    assert path == [0, 2, 1, 3, 4, 5]

    # A* with trivial heuristic (= Dijkstra)
    cost, apath = g.astar(0, 5, lambda n: 0)
    assert cost == 8.0
    assert apath == [0, 2, 1, 3, 4, 5]

    print("Shortest path tests passed")

test_shortest_path()
```

### Minimum Spanning Tree: Kruskal vs Prim

**However**, when you need to connect all vertices with minimum total edge weight, you need MST algorithms. Kruskal's works by sorting edges and using Union-Find, while Prim's grows the tree from a starting vertex. The **trade-off**: Kruskal's is better for sparse graphs (O(E log E)), Prim's with Fibonacci heap is better for dense graphs (O(E + V log V)).

```python
# --- Union-Find (Disjoint Set Union) for Kruskal's ---

class UnionFind:
    # Path compression + union by rank = near-O(1) amortized
    # Common mistake: implementing without path compression
    # which degrades to O(log n)

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n
        self.components = n

    def find(self, x: int) -> int:
        # Path compression — make every node point to root
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        # Union by rank — attach smaller tree under larger
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False  # Already connected
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1
        self.components -= 1
        return True

    def connected(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

def kruskal_mst(num_vertices: int, edges: list[tuple[int, int, float]]) -> tuple[list[tuple[int, int, float]], float]:
    # Sort edges by weight, greedily add if no cycle
    # Therefore, Union-Find detects cycles efficiently
    sorted_edges = sorted(edges, key=lambda e: e[2])
    uf = UnionFind(num_vertices)
    mst: list[tuple[int, int, float]] = []
    total_weight = 0.0

    for u, v, w in sorted_edges:
        if uf.union(u, v):
            mst.append((u, v, w))
            total_weight += w
            if len(mst) == num_vertices - 1:
                break  # MST is complete

    return mst, total_weight

def prim_mst(graph: WeightedGraph) -> tuple[list[tuple[int, int, float]], float]:
    # Grow MST from vertex 0 using min-heap
    # Best practice: use Prim's for dense graphs
    visited = set()
    mst: list[tuple[int, int, float]] = []
    total_weight = 0.0

    # (weight, from, to)
    pq: list[tuple[float, int, int]] = [(0.0, -1, 0)]

    while pq and len(visited) < graph.V:
        w, u, v = heapq.heappop(pq)
        if v in visited:
            continue
        visited.add(v)
        if u != -1:
            mst.append((u, v, w))
            total_weight += w

        for edge in graph.adj[v]:
            if edge.to not in visited:
                heapq.heappush(pq, (edge.weight, v, edge.to))

    return mst, total_weight

# --- Topological Sort for dependency resolution ---

def topological_sort_kahn(num_vertices: int, adj: list[list[int]]) -> list[int]:
    # Kahn's algorithm — BFS-based, detects cycles
    # Therefore, if result length < V, graph has a cycle
    in_degree = [0] * num_vertices
    for u in range(num_vertices):
        for v in adj[u]:
            in_degree[v] += 1

    # Start with all zero in-degree vertices
    queue = [v for v in range(num_vertices) if in_degree[v] == 0]
    result: list[int] = []

    while queue:
        u = queue.pop(0)
        result.append(u)
        for v in adj[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    if len(result) != num_vertices:
        raise ValueError("Graph has a cycle — topological sort impossible")
    return result

def topological_sort_dfs(num_vertices: int, adj: list[list[int]]) -> list[int]:
    # DFS-based — uses finish times
    visited = [False] * num_vertices
    on_stack = [False] * num_vertices  # Cycle detection
    order: list[int] = []

    def dfs(u: int) -> None:
        visited[u] = True
        on_stack[u] = True
        for v in adj[u]:
            if on_stack[v]:
                raise ValueError(f"Cycle detected: edge {u}->{v}")
            if not visited[v]:
                dfs(v)
        on_stack[u] = False
        order.append(u)

    for v in range(num_vertices):
        if not visited[v]:
            dfs(v)

    order.reverse()
    return order

# --- Testing ---
def test_mst_and_topo():
    # MST test
    edges = [
        (0, 1, 4), (0, 2, 1), (1, 2, 2),
        (1, 3, 5), (2, 3, 8), (3, 4, 3),
    ]
    mst, weight = kruskal_mst(5, edges)
    assert len(mst) == 4
    assert weight == 11.0  # 1 + 2 + 5 + 3

    # Prim's should give same weight
    g = WeightedGraph(5)
    for u, v, w in edges:
        g.add_edge(u, v, w)
    _, prim_weight = prim_mst(g)
    assert prim_weight == weight

    # Topological sort test (dependency graph)
    # 0: math, 1: physics (needs math), 2: CS (needs math),
    # 3: ML (needs CS, physics), 4: robotics (needs ML, physics)
    deps: list[list[int]] = [[], [0], [0], [1, 2], [1, 3]]
    order = topological_sort_kahn(5, deps)
    # Verify all dependencies come before dependents
    pos = {v: i for i, v in enumerate(order)}
    assert pos[0] < pos[1]  # math before physics
    assert pos[0] < pos[2]  # math before CS
    assert pos[1] < pos[3]  # physics before ML
    assert pos[2] < pos[3]  # CS before ML

    print(f"MST tests passed (weight={weight}), topo order: {order}")

test_mst_and_topo()
```

## Summary and Key Takeaways

- **Dijkstra's algorithm** with binary heap runs in O((V+E) log V) — use lazy deletion for simplicity
- **A*** adds a heuristic to guide search toward the target — the heuristic must be **admissible** (never overestimate) for optimality
- A **common mistake** with Dijkstra is using it on graphs with negative edges — use Bellman-Ford instead
- **Kruskal's MST** with Union-Find (path compression + rank) is best for sparse graphs at O(E log E)
- **Prim's MST** is better for dense graphs, especially with Fibonacci heap at O(E + V log V)
- **Topological sort** (Kahn's algorithm) naturally detects cycles — if the result has fewer vertices than the graph, there's a cycle
- The **pitfall** of DFS-based topological sort is that it requires explicit cycle detection with an "on-stack" set
- **Union-Find** with both path compression and union by rank achieves near-O(1) amortized operations per query"""
    ),
    (
        "algorithms/dynamic-programming-patterns-optimization",
        "Explain dynamic programming patterns including top-down memoization versus bottom-up tabulation, state design for knapsack and LCS problems, space optimization techniques, bitmask DP for combinatorial problems, and interval DP with practical examples and complexity analysis",
        r"""# Dynamic Programming: Patterns, Optimization, and Advanced Techniques

## The Core Insight of Dynamic Programming

Dynamic programming works when a problem has **optimal substructure** (optimal solution contains optimal sub-solutions) and **overlapping subproblems** (same subproblems are solved repeatedly). The **trade-off** between top-down memoization and bottom-up tabulation is expressiveness vs performance: memoization is easier to write but has function call overhead; tabulation is faster but requires understanding the computation order.

### Classic Patterns: Knapsack and LCS

```python
from typing import Optional
from functools import lru_cache
import time

# --- 0/1 Knapsack: Top-down vs Bottom-up ---

def knapsack_memo(
    weights: list[int], values: list[int], capacity: int
) -> tuple[int, list[int]]:
    # Top-down with memoization
    # Best practice: start with memoization, convert to tabulation if needed
    n = len(weights)
    memo: dict[tuple[int, int], int] = {}

    def dp(i: int, w: int) -> int:
        if i == n or w == 0:
            return 0
        if (i, w) in memo:
            return memo[(i, w)]
        # Skip item i
        result = dp(i + 1, w)
        # Take item i (if it fits)
        if weights[i] <= w:
            result = max(result, values[i] + dp(i + 1, w - weights[i]))
        memo[(i, w)] = result
        return result

    max_value = dp(0, capacity)

    # Backtrack to find which items were selected
    items: list[int] = []
    w = capacity
    for i in range(n):
        if w <= 0:
            break
        # Check if item i was included
        skip_val = memo.get((i + 1, w), 0)
        if memo.get((i, w), 0) != skip_val:
            items.append(i)
            w -= weights[i]

    return max_value, items

def knapsack_tabulation(
    weights: list[int], values: list[int], capacity: int
) -> int:
    # Bottom-up tabulation — O(n * capacity) time and space
    n = len(weights)
    # dp[i][w] = max value using items 0..i-1 with capacity w
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        for w in range(capacity + 1):
            dp[i][w] = dp[i - 1][w]  # Skip item
            if weights[i - 1] <= w:
                dp[i][w] = max(
                    dp[i][w],
                    dp[i - 1][w - weights[i - 1]] + values[i - 1]
                )

    return dp[n][capacity]

def knapsack_space_optimized(
    weights: list[int], values: list[int], capacity: int
) -> int:
    # Space optimization: only need previous row
    # Therefore, reduce from O(n * W) space to O(W)
    # Common mistake: iterating w left-to-right (that's unbounded knapsack)
    # For 0/1 knapsack, iterate RIGHT-TO-LEFT to avoid using an item twice
    dp = [0] * (capacity + 1)

    for i in range(len(weights)):
        # Reverse iteration ensures each item used at most once
        for w in range(capacity, weights[i] - 1, -1):
            dp[w] = max(dp[w], dp[w - weights[i]] + values[i])

    return dp[capacity]

# --- Longest Common Subsequence ---

def lcs(s1: str, s2: str) -> tuple[int, str]:
    # Bottom-up with path reconstruction
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Reconstruct the subsequence
    result: list[str] = []
    i, j = m, n
    while i > 0 and j > 0:
        if s1[i - 1] == s2[j - 1]:
            result.append(s1[i - 1])
            i -= 1
            j -= 1
        elif dp[i - 1][j] > dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    result.reverse()

    return dp[m][n], "".join(result)

# --- Edit Distance (Levenshtein) ---

def edit_distance(s1: str, s2: str) -> tuple[int, list[str]]:
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    # Base cases
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],      # Delete
                    dp[i][j - 1],      # Insert
                    dp[i - 1][j - 1],  # Replace
                )

    # Reconstruct operations
    ops: list[str] = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and s1[i - 1] == s2[j - 1]:
            ops.append(f"keep '{s1[i-1]}'")
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i-1][j-1] + 1:
            ops.append(f"replace '{s1[i-1]}' with '{s2[j-1]}'")
            i -= 1
            j -= 1
        elif j > 0 and dp[i][j] == dp[i][j-1] + 1:
            ops.append(f"insert '{s2[j-1]}'")
            j -= 1
        elif i > 0:
            ops.append(f"delete '{s1[i-1]}'")
            i -= 1
    ops.reverse()

    return dp[m][n], ops

def test_classic_dp():
    # Knapsack
    weights = [2, 3, 4, 5]
    values = [3, 4, 5, 6]
    capacity = 8

    memo_val, items = knapsack_memo(weights, values, capacity)
    tab_val = knapsack_tabulation(weights, values, capacity)
    opt_val = knapsack_space_optimized(weights, values, capacity)
    assert memo_val == tab_val == opt_val
    print(f"Knapsack: max value = {memo_val}, items = {items}")

    # LCS
    length, subseq = lcs("ABCBDAB", "BDCAB")
    assert length == 4
    print(f"LCS: length = {length}, subsequence = '{subseq}'")

    # Edit distance
    dist, ops = edit_distance("kitten", "sitting")
    assert dist == 3
    print(f"Edit distance: {dist}")

test_classic_dp()
```

### Bitmask DP and Interval DP

**However**, some problems require tracking subsets of elements, not just indices. Bitmask DP encodes subsets as integers, enabling O(2^n * n) solutions for problems like TSP and assignment. The **pitfall** is that it only works for small n (typically n <= 20) due to exponential state space.

```python
# --- Bitmask DP: Traveling Salesman Problem ---

def tsp_bitmask(dist: list[list[float]]) -> tuple[float, list[int]]:
    # Find minimum cost Hamiltonian cycle
    # State: dp[mask][i] = min cost to visit all cities in mask, ending at i
    # Therefore, mask is a bitmask where bit j = 1 means city j is visited
    n = len(dist)
    INF = float("inf")
    ALL_VISITED = (1 << n) - 1

    # dp[mask][i] = minimum cost
    dp = [[INF] * n for _ in range(1 << n)]
    parent = [[-1] * n for _ in range(1 << n)]

    # Start at city 0
    dp[1][0] = 0  # mask=0b1 means only city 0 visited

    for mask in range(1, 1 << n):
        for u in range(n):
            if dp[mask][u] == INF:
                continue
            if not (mask & (1 << u)):
                continue  # u not in current set

            for v in range(n):
                if mask & (1 << v):
                    continue  # v already visited
                new_mask = mask | (1 << v)
                new_cost = dp[mask][u] + dist[u][v]
                if new_cost < dp[new_mask][v]:
                    dp[new_mask][v] = new_cost
                    parent[new_mask][v] = u

    # Find best ending city and add return cost
    best_cost = INF
    best_end = -1
    for u in range(n):
        total = dp[ALL_VISITED][u] + dist[u][0]
        if total < best_cost:
            best_cost = total
            best_end = u

    # Reconstruct path
    path: list[int] = []
    mask = ALL_VISITED
    current = best_end
    while current != -1:
        path.append(current)
        prev = parent[mask][current]
        mask ^= (1 << current)
        current = prev
    path.reverse()
    path.append(0)  # Return to start

    return best_cost, path

# --- Interval DP: Matrix Chain Multiplication ---

def matrix_chain_order(dimensions: list[int]) -> tuple[int, str]:
    # Given matrices A1(p0 x p1), A2(p1 x p2), ..., An(p(n-1) x pn)
    # Find optimal parenthesization to minimize scalar multiplications
    # Best practice: think of interval [i, j] as subproblem
    n = len(dimensions) - 1
    # dp[i][j] = min cost to multiply matrices i through j
    dp = [[0] * n for _ in range(n)]
    split = [[0] * n for _ in range(n)]

    # Fill diagonally — length 2, 3, ..., n
    for length in range(2, n + 1):
        for i in range(n - length + 1):
            j = i + length - 1
            dp[i][j] = float("inf")
            for k in range(i, j):
                cost = (dp[i][k] + dp[k + 1][j] +
                        dimensions[i] * dimensions[k + 1] * dimensions[j + 1])
                if cost < dp[i][j]:
                    dp[i][j] = cost
                    split[i][j] = k

    # Reconstruct parenthesization
    def build_parens(i: int, j: int) -> str:
        if i == j:
            return f"A{i + 1}"
        k = split[i][j]
        left = build_parens(i, k)
        right = build_parens(k + 1, j)
        return f"({left} x {right})"

    return dp[0][n - 1], build_parens(0, n - 1)

# --- Longest Increasing Subsequence with binary search ---

def lis_optimized(arr: list[int]) -> tuple[int, list[int]]:
    # O(n log n) using patience sorting
    # Trade-off: harder to implement than O(n^2) but much faster
    if not arr:
        return 0, []

    # tails[i] = smallest tail element for IS of length i+1
    tails: list[int] = []
    # For reconstruction
    predecessors = [-1] * len(arr)
    indices: list[int] = []  # Which index corresponds to each tail

    import bisect

    for i, val in enumerate(arr):
        pos = bisect.bisect_left(tails, val)
        if pos == len(tails):
            tails.append(val)
            indices.append(i)
        else:
            tails[pos] = val
            indices[pos] = i

        if pos > 0:
            predecessors[i] = indices[pos - 1]

    # Reconstruct
    length = len(tails)
    result: list[int] = []
    idx = indices[-1]
    while idx != -1:
        result.append(arr[idx])
        idx = predecessors[idx]
    result.reverse()

    return length, result

def test_advanced_dp():
    # TSP
    dist = [
        [0, 10, 15, 20],
        [10, 0, 35, 25],
        [15, 35, 0, 30],
        [20, 25, 30, 0],
    ]
    cost, path = tsp_bitmask(dist)
    assert cost == 80
    print(f"TSP: min cost = {cost}, path = {path}")

    # Matrix chain
    dims = [30, 35, 15, 5, 10, 20, 25]
    min_ops, parens = matrix_chain_order(dims)
    assert min_ops == 15125
    print(f"Matrix chain: {min_ops} ops, {parens}")

    # LIS
    length, subseq = lis_optimized([10, 9, 2, 5, 3, 7, 101, 18])
    assert length == 4
    print(f"LIS: length = {length}, subsequence = {subseq}")

test_advanced_dp()
```

## Summary and Key Takeaways

- Start with **top-down memoization** for correctness, convert to **bottom-up tabulation** for performance — the **trade-off** is development speed vs runtime speed
- **Space optimization** reduces 2D DP to 1D by only keeping the previous row — iterate in reverse for 0/1 problems, forward for unbounded
- A **common mistake** in 0/1 knapsack is iterating left-to-right in the space-optimized version, which allows items to be used multiple times
- **Bitmask DP** handles subset problems (TSP, assignment) in O(2^n * n) — only feasible for n <= ~20
- **Interval DP** solves problems on contiguous subarrays/substrings — think "what's the optimal split point?"
- The **pitfall** of DP is defining the wrong state — if your state doesn't capture enough information, you'll get wrong answers
- **LIS in O(n log n)** uses patience sorting with binary search — a classic example of replacing a DP dimension with greedy insight"""
    ),
    (
        "algorithms/sorting-internals-comparison-non-comparison",
        "Implement and analyze sorting algorithms including quicksort with three-way partitioning and median-of-three pivot selection, mergesort with in-place optimization, heapsort internals, radix sort for integers and strings, and TimSort hybrid approach with practical benchmarks",
        r"""# Sorting Algorithms: From Quicksort Internals to TimSort

## Why Understanding Sort Internals Matters

Every standard library sort is a carefully engineered hybrid algorithm. Python uses **TimSort**, C++ uses **IntroSort** (quicksort + heapsort + insertion sort), and Go uses **pattern-defeating quicksort**. Understanding the internals is critical **because** the choice of algorithm depends on data characteristics: nearly sorted, many duplicates, random, or adversarial inputs each favor different approaches.

### Quicksort with Three-Way Partitioning

```python
from typing import TypeVar, Callable, MutableSequence
import random
import time

T = TypeVar("T")

def quicksort_3way(arr: list[int], low: int = 0, high: int = -1) -> None:
    # Dijkstra's Dutch National Flag partitioning
    # Best practice: 3-way partition handles duplicates in O(n) per level
    # instead of O(n log n) — critical for real-world data with repeats
    if high == -1:
        high = len(arr) - 1

    if high - low < 16:
        # Insertion sort for small arrays — less overhead
        # Trade-off: insertion sort is O(n^2) but with tiny constant
        _insertion_sort(arr, low, high)
        return

    if low >= high:
        return

    # Median-of-three pivot selection
    # Pitfall: always picking first/last element makes quicksort O(n^2) on sorted input
    pivot = _median_of_three(arr, low, high)

    # 3-way partition: [< pivot | == pivot | > pivot]
    lt, gt = low, high
    i = low
    while i <= gt:
        if arr[i] < pivot:
            arr[lt], arr[i] = arr[i], arr[lt]
            lt += 1
            i += 1
        elif arr[i] > pivot:
            arr[gt], arr[i] = arr[i], arr[gt]
            gt -= 1
            # Don't increment i — swapped element needs checking
        else:
            i += 1

    # Recurse on partitions excluding equal elements
    quicksort_3way(arr, low, lt - 1)
    quicksort_3way(arr, gt + 1, high)

def _median_of_three(arr: list[int], low: int, high: int) -> int:
    mid = (low + high) // 2
    if arr[low] > arr[mid]:
        arr[low], arr[mid] = arr[mid], arr[low]
    if arr[low] > arr[high]:
        arr[low], arr[high] = arr[high], arr[low]
    if arr[mid] > arr[high]:
        arr[mid], arr[high] = arr[high], arr[mid]
    return arr[mid]

def _insertion_sort(arr: list[int], low: int, high: int) -> None:
    for i in range(low + 1, high + 1):
        key = arr[i]
        j = i - 1
        while j >= low and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
        arr[j + 1] = key

# --- Heapsort ---

def heapsort(arr: list[int]) -> None:
    # O(n log n) worst-case, in-place, but not stable
    # However, heapsort has poor cache performance because
    # it accesses memory in a tree pattern (non-sequential)
    n = len(arr)

    # Build max-heap bottom-up — O(n) not O(n log n)
    # Common mistake: thinking build-heap is O(n log n)
    for i in range(n // 2 - 1, -1, -1):
        _sift_down(arr, n, i)

    # Extract max elements one by one
    for i in range(n - 1, 0, -1):
        arr[0], arr[i] = arr[i], arr[0]
        _sift_down(arr, i, 0)

def _sift_down(arr: list[int], size: int, i: int) -> None:
    largest = i
    left = 2 * i + 1
    right = 2 * i + 2

    if left < size and arr[left] > arr[largest]:
        largest = left
    if right < size and arr[right] > arr[largest]:
        largest = right

    if largest != i:
        arr[i], arr[largest] = arr[largest], arr[i]
        _sift_down(arr, size, largest)
```

### Non-Comparison Sorts and TimSort

Comparison-based sorts have an O(n log n) lower bound. **Therefore**, for integer data with known range, non-comparison sorts like radix sort achieve O(nk) where k is the number of digits — faster than O(n log n) when k < log n.

```python
# --- Radix Sort (LSD — Least Significant Digit first) ---

def radix_sort(arr: list[int]) -> list[int]:
    # O(d * (n + b)) where d = digits, b = base
    # Best practice: use base 256 (byte-level) for integers
    # Trade-off: requires O(n) extra space but achieves linear time
    if not arr:
        return arr

    # Handle negative numbers by splitting
    negatives = sorted([-x for x in arr if x < 0], reverse=True)
    positives = [x for x in arr if x >= 0]

    if positives:
        positives = _radix_sort_positive(positives)

    return [-x for x in negatives] + positives

def _radix_sort_positive(arr: list[int]) -> list[int]:
    max_val = max(arr)
    exp = 1
    base = 256  # Process one byte at a time

    while max_val // exp > 0:
        arr = _counting_sort_by_digit(arr, exp, base)
        exp *= base

    return arr

def _counting_sort_by_digit(arr: list[int], exp: int, base: int) -> list[int]:
    n = len(arr)
    output = [0] * n
    count = [0] * base

    for num in arr:
        digit = (num // exp) % base
        count[digit] += 1

    # Prefix sum for stable positioning
    for i in range(1, base):
        count[i] += count[i - 1]

    # Build output in reverse for stability
    for i in range(n - 1, -1, -1):
        digit = (arr[i] // exp) % base
        count[digit] -= 1
        output[count[digit]] = arr[i]

    return output

# --- Simplified TimSort concepts ---

def timsort_simplified(arr: list[int]) -> list[int]:
    # TimSort: merge sort + insertion sort hybrid
    # Key insight: real-world data has "runs" (already-sorted subsequences)
    # Therefore, detect natural runs and merge them
    MIN_RUN = 32
    n = len(arr)
    result = arr.copy()

    # Step 1: Create sorted runs of size MIN_RUN using insertion sort
    for start in range(0, n, MIN_RUN):
        end = min(start + MIN_RUN - 1, n - 1)
        _insertion_sort(result, start, end)

    # Step 2: Merge runs bottom-up
    size = MIN_RUN
    while size < n:
        for left in range(0, n, 2 * size):
            mid = min(left + size - 1, n - 1)
            right = min(left + 2 * size - 1, n - 1)
            if mid < right:
                _merge(result, left, mid, right)
        size *= 2

    return result

def _merge(arr: list[int], left: int, mid: int, right: int) -> None:
    # Merge two sorted subarrays with galloping optimization
    left_arr = arr[left:mid + 1]
    right_arr = arr[mid + 1:right + 1]

    i = j = 0
    k = left

    while i < len(left_arr) and j < len(right_arr):
        if left_arr[i] <= right_arr[j]:
            arr[k] = left_arr[i]
            i += 1
        else:
            arr[k] = right_arr[j]
            j += 1
        k += 1

    while i < len(left_arr):
        arr[k] = left_arr[i]
        i += 1
        k += 1

    while j < len(right_arr):
        arr[k] = right_arr[j]
        j += 1
        k += 1

# --- Benchmarking ---

def benchmark_sorts():
    sizes = [1000, 10000]
    for n in sizes:
        data = list(range(n))
        random.shuffle(data)

        # Quicksort 3-way
        arr = data.copy()
        start = time.perf_counter()
        quicksort_3way(arr)
        qs_time = time.perf_counter() - start
        assert arr == sorted(data)

        # Heapsort
        arr = data.copy()
        start = time.perf_counter()
        heapsort(arr)
        hs_time = time.perf_counter() - start
        assert arr == sorted(data)

        # Radix sort
        start = time.perf_counter()
        result = radix_sort(data)
        rs_time = time.perf_counter() - start
        assert result == sorted(data)

        # TimSort
        start = time.perf_counter()
        result = timsort_simplified(data)
        ts_time = time.perf_counter() - start
        assert result == sorted(data)

        print(f"n={n}: QS3={qs_time:.4f}s, Heap={hs_time:.4f}s, "
              f"Radix={rs_time:.4f}s, Tim={ts_time:.4f}s")

    # Test with many duplicates — 3-way quicksort shines
    dup_data = [random.randint(1, 10) for _ in range(10000)]
    arr = dup_data.copy()
    quicksort_3way(arr)
    assert arr == sorted(dup_data)
    print("Duplicate-heavy sort passed")

benchmark_sorts()
```

## Summary and Key Takeaways

- **Three-way quicksort** handles duplicates in O(n) per partition level — essential for real-world data with repeated values
- **Median-of-three** pivot selection avoids O(n^2) on sorted/reverse-sorted input — a **common mistake** is using fixed pivot positions
- **Heapsort** guarantees O(n log n) worst-case and is in-place, but the **pitfall** is poor cache performance due to tree-pattern memory access
- **Radix sort** breaks the O(n log n) comparison lower bound — use base 256 for byte-level processing of integers
- **TimSort** exploits natural runs in real data — it's O(n) on already-sorted data, making it the **best practice** for general-purpose sorting
- The **trade-off** of stability: mergesort and TimSort are stable (preserve equal-element order), quicksort and heapsort are not
- For small arrays (n < 16), **insertion sort** beats all others due to minimal overhead — that's why hybrid sorts switch to it"""
    ),
    (
        "algorithms/hash-tables-bloom-filters-probabilistic",
        "Implement hash table internals including open addressing with linear and quadratic probing, Robin Hood hashing for reduced variance, cuckoo hashing with guaranteed O(1) lookup, Bloom filters for membership testing, and Count-Min Sketch for frequency estimation",
        r"""# Hash Tables and Probabilistic Data Structures

## Hash Table Internals: Beyond Chaining

Most developers think of hash tables as simple key-value stores, but the implementation details dramatically affect performance. **Because** hash tables are the most-used data structure in software (dictionaries, sets, caches, symbol tables), understanding collision resolution strategies is essential for performance-critical code.

### Open Addressing: Linear, Quadratic, and Robin Hood

```python
from typing import TypeVar, Generic, Optional, Iterator
from dataclasses import dataclass
from math import log, ceil
import hashlib
import struct

K = TypeVar("K")
V = TypeVar("V")

EMPTY = object()
DELETED = object()  # Tombstone for lazy deletion

class LinearProbingHashTable(Generic[K, V]):
    # Open addressing with linear probing
    # Trade-off: excellent cache performance (sequential memory access)
    # but suffers from primary clustering (long probe chains)

    def __init__(self, initial_capacity: int = 16, max_load: float = 0.7):
        self._capacity = initial_capacity
        self._max_load = max_load
        self._size = 0
        self._keys: list = [EMPTY] * initial_capacity
        self._values: list = [EMPTY] * initial_capacity

    def _hash(self, key: K) -> int:
        return hash(key) % self._capacity

    def put(self, key: K, value: V) -> None:
        if (self._size + 1) / self._capacity > self._max_load:
            self._resize(self._capacity * 2)

        idx = self._hash(key)
        while True:
            if self._keys[idx] is EMPTY or self._keys[idx] is DELETED:
                self._keys[idx] = key
                self._values[idx] = value
                self._size += 1
                return
            if self._keys[idx] == key:
                self._values[idx] = value  # Update existing
                return
            idx = (idx + 1) % self._capacity  # Linear probe

    def get(self, key: K) -> Optional[V]:
        idx = self._hash(key)
        while self._keys[idx] is not EMPTY:
            if self._keys[idx] == key:
                return self._values[idx]
            idx = (idx + 1) % self._capacity
        return None

    def delete(self, key: K) -> bool:
        # Common mistake: setting slot to EMPTY breaks probe chains
        # Best practice: use tombstones (DELETED marker)
        idx = self._hash(key)
        while self._keys[idx] is not EMPTY:
            if self._keys[idx] == key:
                self._keys[idx] = DELETED
                self._values[idx] = EMPTY
                self._size -= 1
                return True
            idx = (idx + 1) % self._capacity
        return False

    def _resize(self, new_capacity: int) -> None:
        old_keys = self._keys
        old_values = self._values
        self._capacity = new_capacity
        self._keys = [EMPTY] * new_capacity
        self._values = [EMPTY] * new_capacity
        self._size = 0
        for i, key in enumerate(old_keys):
            if key is not EMPTY and key is not DELETED:
                self.put(key, old_values[i])

    def __len__(self) -> int:
        return self._size

class RobinHoodHashTable(Generic[K, V]):
    # Robin Hood hashing: steal from the rich, give to the poor
    # Elements with longer probe distances "rob" slots from elements
    # with shorter distances — reduces variance dramatically
    # Therefore, worst-case lookups are much shorter than linear probing

    def __init__(self, initial_capacity: int = 16, max_load: float = 0.8):
        self._capacity = initial_capacity
        self._max_load = max_load
        self._size = 0
        self._keys: list = [EMPTY] * initial_capacity
        self._values: list = [EMPTY] * initial_capacity
        self._distances: list[int] = [0] * initial_capacity

    def _hash(self, key: K) -> int:
        return hash(key) % self._capacity

    def _probe_distance(self, key: K, slot: int) -> int:
        ideal = self._hash(key)
        return (slot - ideal + self._capacity) % self._capacity

    def put(self, key: K, value: V) -> None:
        if (self._size + 1) / self._capacity > self._max_load:
            self._resize(self._capacity * 2)

        idx = self._hash(key)
        distance = 0
        current_key = key
        current_value = value

        while True:
            if self._keys[idx] is EMPTY:
                self._keys[idx] = current_key
                self._values[idx] = current_value
                self._distances[idx] = distance
                self._size += 1
                return

            if self._keys[idx] == current_key:
                self._values[idx] = current_value
                return

            # Robin Hood: if current element is "richer" (shorter distance),
            # swap and continue inserting the displaced element
            existing_dist = self._distances[idx]
            if existing_dist < distance:
                # Swap — displace the richer element
                self._keys[idx], current_key = current_key, self._keys[idx]
                self._values[idx], current_value = current_value, self._values[idx]
                self._distances[idx], distance = distance, existing_dist

            idx = (idx + 1) % self._capacity
            distance += 1

    def get(self, key: K) -> Optional[V]:
        idx = self._hash(key)
        distance = 0

        while True:
            if self._keys[idx] is EMPTY:
                return None
            # Early termination: if current slot's distance < our probe distance,
            # the key cannot exist further along
            if self._distances[idx] < distance:
                return None
            if self._keys[idx] == key:
                return self._values[idx]
            idx = (idx + 1) % self._capacity
            distance += 1

    def _resize(self, new_capacity: int) -> None:
        old_keys = self._keys
        old_values = self._values
        self._capacity = new_capacity
        self._keys = [EMPTY] * new_capacity
        self._values = [EMPTY] * new_capacity
        self._distances = [0] * new_capacity
        self._size = 0
        for i, key in enumerate(old_keys):
            if key is not EMPTY:
                self.put(key, old_values[i])

    def __len__(self) -> int:
        return self._size
```

### Bloom Filter and Count-Min Sketch

**However**, sometimes you don't need exact membership testing — a probabilistic answer with tunable false positive rate is sufficient. **Bloom filters** answer "definitely not in set" or "probably in set" using only a few bits per element. The **trade-off** is memory vs accuracy: more bits means fewer false positives.

```python
# --- Bloom Filter ---

class BloomFilter:
    # Space-efficient probabilistic set membership
    # False positives possible, false negatives impossible
    # Pitfall: cannot delete elements (use Counting Bloom Filter for that)

    def __init__(self, expected_items: int, false_positive_rate: float = 0.01):
        # Optimal size: m = -(n * ln(p)) / (ln(2)^2)
        # Optimal hash count: k = (m / n) * ln(2)
        self.size = self._optimal_size(expected_items, false_positive_rate)
        self.hash_count = self._optimal_hashes(self.size, expected_items)
        self.bit_array = bytearray(self.size // 8 + 1)
        self._count = 0

    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        m = -(n * log(p)) / (log(2) ** 2)
        return int(ceil(m))

    @staticmethod
    def _optimal_hashes(m: int, n: int) -> int:
        k = (m / n) * log(2)
        return max(1, int(round(k)))

    def _get_hashes(self, item: str) -> list[int]:
        # Double hashing technique: h(i) = h1 + i * h2
        # Therefore, we only need 2 hash functions for k probes
        h = hashlib.md5(item.encode()).digest()
        h1 = struct.unpack("<Q", h[:8])[0]
        h2 = struct.unpack("<Q", h[8:])[0]
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]

    def add(self, item: str) -> None:
        for pos in self._get_hashes(item):
            byte_idx = pos // 8
            bit_idx = pos % 8
            self.bit_array[byte_idx] |= (1 << bit_idx)
        self._count += 1

    def might_contain(self, item: str) -> bool:
        # Returns True if item MIGHT be in the set
        # Returns False if item is DEFINITELY NOT in the set
        for pos in self._get_hashes(item):
            byte_idx = pos // 8
            bit_idx = pos % 8
            if not (self.bit_array[byte_idx] & (1 << bit_idx)):
                return False
        return True

    @property
    def estimated_false_positive_rate(self) -> float:
        # Actual FPR based on current fill ratio
        bits_set = sum(
            bin(byte).count("1") for byte in self.bit_array
        )
        fill_ratio = bits_set / self.size
        return fill_ratio ** self.hash_count

# --- Count-Min Sketch for frequency estimation ---

class CountMinSketch:
    # Estimates frequency of items in a stream
    # Best practice: use when exact counting is too expensive
    # Overestimates are possible, underestimates are not

    def __init__(self, width: int = 1000, depth: int = 5):
        self.width = width
        self.depth = depth
        self.table = [[0] * width for _ in range(depth)]
        self._total = 0

    def _hash(self, item: str, seed: int) -> int:
        h = hashlib.sha256(f"{seed}:{item}".encode()).digest()
        return struct.unpack("<I", h[:4])[0] % self.width

    def add(self, item: str, count: int = 1) -> None:
        self._total += count
        for i in range(self.depth):
            j = self._hash(item, i)
            self.table[i][j] += count

    def estimate(self, item: str) -> int:
        # Return minimum across all hash functions
        # Therefore, reduces overestimation from hash collisions
        return min(
            self.table[i][self._hash(item, i)]
            for i in range(self.depth)
        )

    @property
    def total_count(self) -> int:
        return self._total

# --- Testing ---

def test_hash_structures():
    # Robin Hood hash table
    rh = RobinHoodHashTable[str, int]()
    for i in range(1000):
        rh.put(f"key-{i}", i)
    assert len(rh) == 1000
    assert rh.get("key-500") == 500
    assert rh.get("nonexistent") is None

    # Bloom filter
    bf = BloomFilter(expected_items=10000, false_positive_rate=0.01)
    for i in range(10000):
        bf.add(f"item-{i}")

    # All added items must be found (no false negatives)
    for i in range(10000):
        assert bf.might_contain(f"item-{i}")

    # Check false positive rate on non-members
    fp = sum(
        1 for i in range(10000, 20000)
        if bf.might_contain(f"item-{i}")
    )
    fp_rate = fp / 10000
    print(f"Bloom filter: FP rate = {fp_rate:.4f} (target: 0.01)")
    assert fp_rate < 0.05  # Allow some margin

    # Count-Min Sketch
    cms = CountMinSketch(width=2000, depth=7)
    # Add items with known frequencies
    for _ in range(100):
        cms.add("frequent")
    for _ in range(10):
        cms.add("moderate")
    cms.add("rare")

    assert cms.estimate("frequent") >= 100
    assert cms.estimate("moderate") >= 10
    assert cms.estimate("rare") >= 1
    assert cms.estimate("absent") >= 0
    print(f"CMS estimates: frequent={cms.estimate('frequent')}, "
          f"moderate={cms.estimate('moderate')}, rare={cms.estimate('rare')}")

    print("All hash structure tests passed")

test_hash_structures()
```

## Summary and Key Takeaways

- **Linear probing** has excellent cache performance but suffers from **primary clustering** — long probe chains that grow quadratically
- **Robin Hood hashing** equalizes probe distances by displacing "richer" elements — reduces worst-case lookups dramatically
- A **common mistake** with open addressing is using EMPTY to mark deleted slots, which breaks probe chain invariants — use tombstones
- **Bloom filters** provide O(1) membership testing with tunable false positive rate using only ~10 bits per element
- **Count-Min Sketch** estimates frequencies in data streams — overestimates are bounded, underestimates are impossible
- The **trade-off** of probabilistic data structures: they sacrifice exactness for massive space savings (Bloom: ~10 bits/element vs hash set: ~50+ bytes/element)
- The **pitfall** of Bloom filters is that standard ones cannot delete elements — use Counting Bloom Filters or Cuckoo Filters for deletion support"""
    ),
]
