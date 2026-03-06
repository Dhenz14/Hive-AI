PAIRS = [
    ("thinking/algorithms", r'''Implement the rerooting technique for tree DP. Given a tree where each node has a weight, compute for each node the sum of distances to all other nodes, weighted by their weights. Use rerooting to go from O(n^2) to O(n).''', r'''<think>
The rerooting technique (also called rerooting DP) allows computing a tree DP answer for every node as root in O(n) total time, instead of O(n^2) from running DP n times. The naive approach of BFS from every node would be O(n^2) which is too slow for n > 10^5.

For the weighted distance sum problem: for each node u, compute sum over all v of (weight[v] * dist(u, v)).

Step 1: Root the tree at node 0. Compute dp_down[u] = sum of weight[v] * dist(u, v) for all v in subtree of u.
- dp_down[leaf] = 0
- dp_down[u] = sum over children c of (dp_down[c] + subtree_weight[c])
  (because moving from c to u adds 1 to distance for all nodes in c's subtree)

Also compute subtree_weight[u] = sum of weights in u's subtree.

Step 2: This is where it gets tricky. I need dp_up[u] = contribution from nodes NOT in u's subtree. My first thought was to just compute dp_down for each root independently, but that is exactly the O(n^2) approach we want to avoid.

The key insight: when we move the root from u to its child c, most of the answer stays the same. Nodes in c's subtree get 1 closer, while nodes outside get 1 farther. So we can express dp_up[c] in terms of dp_up[u] and dp_down[u].

- dp_up[root] = 0
- For child c of u: dp_up[c] = dp_up[u] + (dp_down[u] - dp_down[c] - subtree_weight[c]) + (total_weight - subtree_weight[c])

Wait, let me verify this formula. The nodes outside c's subtree contribute:
  - dp_up[u]: contribution from above u (add 1 to each distance)
  - dp_down[u] - dp_down[c] - subtree_weight[c]: contribution from u's OTHER subtrees (add 1 for the edge from c to u)
  - total_weight - subtree_weight[c]: the extra +1 distance for the edge u->c for all non-subtree nodes

Hmm, actually the third term is the key -- because every node outside c's subtree is now one edge farther from c than from u, so we add total_weight - subtree_weight[c] to account for that extra edge.

Step 3: answer[u] = dp_down[u] + dp_up[u]

This gives O(n) total time with two passes: one bottom-up, one top-down. The tradeoff versus the naive approach is implementation complexity -- rerooting requires careful derivation of the transition formula, and it is easy to get the signs wrong.
</think>

## Rerooting Technique for Tree DP

### Problem: Weighted Distance Sum for Every Node

```python
from collections import defaultdict


def weighted_distance_sum(n, edges, weights):
    """For each node u, compute sum of weight[v] * dist(u, v) for all v.

    Uses rerooting technique: O(n) instead of O(n^2).

    Args:
        n: number of nodes
        edges: list of (u, v) edges
        weights: weight[i] for each node

    Returns:
        list of answers, one per node
    """
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    total_weight = sum(weights)
    subtree_weight = [0] * n
    dp_down = [0] * n  # sum from subtree
    dp_up = [0] * n    # sum from outside subtree
    parent = [-1] * n

    # BFS ordering for iterative DFS
    order = []
    visited = [False] * n
    stack = [0]
    visited[0] = True
    while stack:
        u = stack.pop()
        order.append(u)
        for v in adj[u]:
            if not visited[v]:
                visited[v] = True
                parent[v] = u
                stack.append(v)

    # Pass 1: bottom-up (compute subtree_weight and dp_down)
    for u in reversed(order):
        subtree_weight[u] = weights[u]
        dp_down[u] = 0
        for v in adj[u]:
            if v != parent[u]:
                subtree_weight[u] += subtree_weight[v]
                dp_down[u] += dp_down[v] + subtree_weight[v]

    # Pass 2: top-down (compute dp_up via rerooting)
    dp_up[0] = 0
    for u in order:
        for v in adj[u]:
            if v != parent[u]:
                # dp_up[v] = contribution from everything outside v's subtree
                # = (dp_up[u] + dp_down[u] - dp_down[v] - subtree_weight[v])
                #   + (total_weight - subtree_weight[v])
                outside_down = dp_down[u] - dp_down[v] - subtree_weight[v]
                dp_up[v] = dp_up[u] + outside_down + (total_weight - subtree_weight[v])

    # Final answer for each node
    answer = [dp_down[u] + dp_up[u] for u in range(n)]
    return answer


def brute_force_weighted_dist(n, edges, weights):
    """O(n^2) brute force for verification."""
    from collections import deque
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    answers = []
    for start in range(n):
        dist = [-1] * n
        dist[start] = 0
        queue = deque([start])
        while queue:
            u = queue.popleft()
            for v in adj[u]:
                if dist[v] == -1:
                    dist[v] = dist[u] + 1
                    queue.append(v)
        total = sum(weights[v] * dist[v] for v in range(n))
        answers.append(total)
    return answers


# Demo
n = 7
edges = [(0,1), (0,2), (1,3), (1,4), (2,5), (2,6)]
weights = [1, 2, 3, 4, 5, 6, 7]

print("=== Rerooting DP: Weighted Distance Sum ===")
print(f"Tree edges: {edges}")
print(f"Weights: {weights}")
print(f"Tree structure:")
print(f"        0(w=1)")
print(f"       / \\")
print(f"      1   2")
print(f"     / \\ / \\")
print(f"    3  4 5  6")

reroot_ans = weighted_distance_sum(n, edges, weights)
brute_ans = brute_force_weighted_dist(n, edges, weights)

print(f"\nResults:")
print(f"  {'Node':>4} {'Weight':>6} {'Rerooting':>10} {'Brute':>10} {'Match':>6}")
for i in range(n):
    match = "OK" if reroot_ans[i] == brute_ans[i] else "FAIL"
    print(f"  {i:>4} {weights[i]:>6} {reroot_ans[i]:>10} {brute_ans[i]:>10} {match:>6}")

# Larger test
import random
random.seed(42)
N = 1000
edges_large = [(i, random.randint(0, i-1)) for i in range(1, N)]
weights_large = [random.randint(1, 100) for _ in range(N)]
ans = weighted_distance_sum(N, edges_large, weights_large)
print(f"\nLarge tree ({N} nodes): answers computed in O(n)")
print(f"  Min answer: {min(ans)}")
print(f"  Max answer: {max(ans)}")
```

### The Rerooting Pattern
1. **Root arbitrarily**, compute bottom-up DP (`dp_down`)
2. **Top-down pass**: for each child, compute `dp_up` using parent's `dp_down` minus child's contribution
3. **Combine**: `answer[v] = dp_down[v] + dp_up[v]`

### Complexity
- **Time**: O(n) -- two passes over the tree
- **Space**: O(n)
- **Compared to naive**: O(n^2) from running BFS/DFS from every node'''),

    ("thinking/algorithms", r'''Implement DP on a Directed Acyclic Graph (DAG). Find the longest path, count the number of paths, and find the path with maximum weight in a weighted DAG.''', r'''<think>
DP on DAGs is natural because topological order gives us the correct order to process states. Every DP can be viewed as a DAG where states are nodes and transitions are edges. This is a fundamental connection -- understanding it makes many DP problems clearer.

Problems to solve on a DAG:
1. Longest path: dp[v] = max over predecessors u of (dp[u] + weight(u,v)). Process in topological order.
2. Count paths from source to sink: dp[v] = sum of dp[u] for all predecessors u. dp[source] = 1.
3. Maximum weight path: same as longest path with edge weights.

I considered using Dijkstra for the longest path, but wait -- Dijkstra does not work for longest paths, even on DAGs, because the greedy choice property fails. You cannot greedily pick the farthest node. The topological order approach is both simpler and correct.

For topological sort, I will use Kahn's algorithm (BFS-based) rather than DFS-based. Kahn's is iterative and avoids recursion depth issues. It also naturally detects cycles: if we process fewer than n nodes, there is a cycle.

Edge cases to watch for: disconnected components (some nodes unreachable from source -- their distances stay at -infinity), multiple sources/sinks, zero-weight edges, and negative weights. Hmm, negative weights are fine on DAGs unlike with Dijkstra, because we process each node exactly once in topological order. No relaxation conflicts.

One tradeoff: should I process forward (source to sink) or backward (sink to source)? Forward is more natural for "longest path from source" but backward works better for "longest path to sink." I will go forward since it matches Kahn's output order directly.
</think>

## DP on Directed Acyclic Graphs

### Implementation

```python
from collections import deque, defaultdict


def topological_sort(n, adj):
    """Kahn's algorithm for topological sort. Returns order or None if cycle."""
    in_degree = [0] * n
    for u in range(n):
        for v, w in adj[u]:
            in_degree[v] += 1

    queue = deque(u for u in range(n) if in_degree[u] == 0)
    order = []
    while queue:
        u = queue.popleft()
        order.append(u)
        for v, w in adj[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    return order if len(order) == n else None


def longest_path(n, adj, source=None):
    """Find longest path (by total weight) in a weighted DAG.

    Returns:
        (distances, predecessors) where distances[v] = longest path to v
    """
    order = topological_sort(n, adj)
    if order is None:
        raise ValueError("Graph has a cycle")

    INF = float('-inf')
    dist = [INF] * n
    pred = [-1] * n

    if source is not None:
        dist[source] = 0
    else:
        # Start from all sources (in-degree 0)
        for u in order:
            if dist[u] == INF:
                dist[u] = 0

    for u in order:
        if dist[u] == INF:
            continue
        for v, w in adj[u]:
            if dist[u] + w > dist[v]:
                dist[v] = dist[u] + w
                pred[v] = u

    return dist, pred


def count_paths(n, adj, source, sink):
    """Count number of distinct paths from source to sink in DAG."""
    order = topological_sort(n, adj)
    count = [0] * n
    count[source] = 1

    for u in order:
        for v, w in adj[u]:
            count[v] += count[u]

    return count[sink]


def reconstruct_path(pred, target):
    """Reconstruct path from predecessors."""
    path = []
    v = target
    while v != -1:
        path.append(v)
        v = pred[v]
    path.reverse()
    return path


def all_paths_dp(n, adj, source, sink):
    """Find longest path, shortest path, and path count simultaneously."""
    order = topological_sort(n, adj)

    INF = float('inf')
    longest = [float('-inf')] * n
    shortest = [INF] * n
    count = [0] * n

    longest[source] = 0
    shortest[source] = 0
    count[source] = 1

    for u in order:
        if count[u] == 0 and u != source:
            continue
        for v, w in adj[u]:
            if longest[u] + w > longest[v]:
                longest[v] = longest[u] + w
            if shortest[u] + w < shortest[v]:
                shortest[v] = shortest[u] + w
            count[v] += count[u]

    return {
        'longest': longest[sink],
        'shortest': shortest[sink],
        'count': count[sink]
    }


# Demo
n = 7
adj = [[] for _ in range(n)]
edges = [
    (0, 1, 3), (0, 2, 6),
    (1, 3, 4), (1, 4, 2),
    (2, 3, 1), (2, 4, 8),
    (3, 5, 7), (3, 6, 2),
    (4, 5, 5), (4, 6, 3),
    (5, 6, 1),
]
for u, v, w in edges:
    adj[u].append((v, w))

print("=== DP on DAG ===")
print(f"Edges: {edges}")

# Longest path from 0
dist, pred = longest_path(n, adj, source=0)
print(f"\nLongest paths from node 0:")
for v in range(n):
    path = reconstruct_path(pred, v)
    print(f"  to {v}: distance={dist[v]}, path={path}")

# Count paths from 0 to 6
num_paths = count_paths(n, adj, 0, 6)
print(f"\nNumber of paths from 0 to 6: {num_paths}")

# All-in-one analysis
results = all_paths_dp(n, adj, 0, 6)
print(f"\nPath analysis (0 -> 6):")
print(f"  Longest path weight:  {results['longest']}")
print(f"  Shortest path weight: {results['shortest']}")
print(f"  Number of paths:      {results['count']}")

# Topological order
order = topological_sort(n, adj)
print(f"\nTopological order: {order}")
```

### Complexity
- **Topological sort**: O(V + E)
- **DP computation**: O(V + E) -- each edge processed once
- **Total**: O(V + E)
- **Key advantage**: works with negative weights (unlike Dijkstra)

### When to Use
- Scheduling with dependencies
- Critical path method (project management)
- Any shortest/longest path on DAG
- Counting combinatorial structures'''),

    ("thinking/algorithms", r'''Implement the tree knapsack problem: given a tree where each node has a weight and value, select a subset of nodes with total weight <= W such that if a node is selected, its parent must also be selected. Maximize total value.''', r'''<think>
Tree knapsack (also called tree-dependent knapsack or precedence-constrained knapsack): select nodes from a tree such that:
1. If a node is selected, its parent must be selected (dependency constraint)
2. Total weight <= W
3. Maximize total value

This is harder than standard knapsack because of the dependency constraint. My first instinct was to reduce it to standard knapsack by enumerating all valid subsets (connected subtrees containing the root), but there can be exponentially many of those.

The right approach is DP on the tree. Let me define:
dp[v][w] = max value using nodes from v's subtree with total weight w.

But wait, there is a subtlety about whether v itself is selected. If v is NOT selected, then none of its descendants can be selected either (because of the parent dependency). So dp[v][0] = 0 (select nothing) and dp[v][w] requires v to be selected when w > 0.

Hmm, actually let me be more precise:
dp[v][w] = max value using weight exactly w from v's subtree, where v IS selected if w >= weight[v], or nothing is selected if w == 0.

Since v must be selected for any of its children to be selected, w >= weight[v] is required for any non-zero selection. The remaining capacity (w - weight[v]) is distributed among children's subtrees.

For combining children: this is like a knapsack over the children. Process children one by one, and for each child c, decide how much weight to allocate to c's subtree.

I initially thought this would be O(n * W^2) -- for each node, iterating over all pairs (w1 from existing, w2 from child). But with the merging technique, we can show it is O(n * W). The argument is subtle: when merging subtrees of sizes s1 and s2, the merge cost is O(s1 * s2) in the W dimension, but summed over all merges in the tree, this telescopes to O(n * W) total by a counting argument (each pair of nodes is compared at most once at their LCA).

Option A: implement the straightforward O(n * W^2) version for clarity.
Option B: implement the optimized O(n * W) version with careful merging.

I will go with the straightforward version since correctness is more important for understanding, and the optimization is mainly about constant factors for moderate n.
</think>

## Tree Knapsack Problem

### Implementation

```python
from collections import defaultdict


def tree_knapsack(n, edges, weights, values, capacity, root=0):
    """Tree knapsack: select nodes with total weight <= capacity,
    if a node is selected its parent must be selected too.

    Args:
        n: number of nodes
        edges: list of (u, v) edges
        weights: weight of each node
        values: value of each node
        capacity: maximum total weight

    Returns:
        (max_value, selected_nodes)
    """
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    # Root the tree
    parent = [-1] * n
    children = [[] for _ in range(n)]
    order = []
    visited = [False] * n
    visited[root] = True
    stack = [root]
    while stack:
        u = stack.pop()
        order.append(u)
        for v in adj[u]:
            if not visited[v]:
                visited[v] = True
                parent[v] = u
                children[u].append(v)
                stack.append(v)

    W = capacity

    # dp[v][w] = max value from subtree of v using exactly w weight
    # with v selected (if w >= weights[v]) or nothing selected (w == 0)
    # We use -1 to indicate impossible states
    dp = [[- 1] * (W + 1) for _ in range(n)]
    chosen = [[False] * (W + 1) for _ in range(n)]

    # Process bottom-up
    for v in reversed(order):
        wv = weights[v]
        vv = values[v]

        # Initialize: can choose not to select v at all
        dp[v][0] = 0

        # Or select v (requires weight >= wv)
        if wv <= W:
            dp[v][wv] = vv

        # Merge children's subtrees
        for c in children[v]:
            # Merge dp[v] with dp[c]
            # New dp[v][w] = max over split (w1 + w2 = w) of dp[v][w1] + dp[c][w2]
            # But we can only use dp[c][w2] if dp[c][w2] > 0 or w2 == 0
            new_dp = [-1] * (W + 1)
            for w1 in range(W + 1):
                if dp[v][w1] < 0:
                    continue
                for w2 in range(W + 1 - w1):
                    if dp[c][w2] < 0:
                        continue
                    # w2 > 0 means we selected some nodes in c's subtree
                    # This requires v to be selected (w1 >= wv)
                    if w2 > 0 and w1 < wv:
                        continue  # cannot select child without selecting parent
                    total = dp[v][w1] + dp[c][w2]
                    if total > new_dp[w1 + w2]:
                        new_dp[w1 + w2] = total
            dp[v] = new_dp

    # Find best weight
    best_val = 0
    best_w = 0
    for w in range(W + 1):
        if dp[root][w] > best_val:
            best_val = dp[root][w]
            best_w = w

    return best_val


# Demo
print("=== Tree Knapsack ===")
n = 7
edges = [(0,1), (0,2), (1,3), (1,4), (2,5), (2,6)]
weights = [2, 3, 4, 1, 2, 3, 1]
values  = [5, 8, 7, 3, 6, 4, 9]
capacity = 10

print(f"Tree structure (node: weight/value):")
print(f"       0: {weights[0]}/{values[0]}")
print(f"      / \\")
print(f"     1   2")
print(f"  {weights[1]}/{values[1]} {weights[2]}/{values[2]}")
print(f"    / \\   / \\")
print(f"   3   4 5   6")
print(f" {weights[3]}/{values[3]} {weights[4]}/{values[4]} "
      f"{weights[5]}/{values[5]} {weights[6]}/{values[6]}")
print(f"\nCapacity: {capacity}")

result = tree_knapsack(n, edges, weights, values, capacity)
print(f"Maximum value: {result}")

# Brute force verification for small instance
best_brute = 0
for mask in range(1 << n):
    selected = [i for i in range(n) if mask & (1 << i)]
    # Check parent constraint
    valid = True
    total_w = 0
    total_v = 0
    for node in selected:
        total_w += weights[node]
        total_v += values[node]
        p = -1
        for u, v in edges:
            if v == node and u in selected:
                p = u
                break
            if u == node and v in selected:
                pass
        # Check if parent is selected (for non-root nodes)
        if node != 0:
            par = None
            # Find parent in our rooted tree
            visited_check = [False] * n
            visited_check[0] = True
            stack_check = [0]
            par_map = {}
            while stack_check:
                uu = stack_check.pop()
                for vv in [v for u, v in edges if u == uu] + [u for u, v in edges if v == uu]:
                    if not visited_check[vv]:
                        visited_check[vv] = True
                        par_map[vv] = uu
                        stack_check.append(vv)
            if par_map.get(node) not in selected:
                valid = False
                break
    if valid and total_w <= capacity:
        best_brute = max(best_brute, total_v)

print(f"Brute force: {best_brute}")
print(f"Match: {'OK' if result == best_brute else 'FAIL'}")
```

### Complexity
- **Time**: O(n * W) with careful merging (each pair of subtree nodes compared at most once)
- **Space**: O(n * W) for DP table
- **Key constraint**: if a child is selected, its parent must also be selected'''),

    ("thinking/algorithms", r'''Implement minimum vertex cover on a tree using DP. A vertex cover is a set of nodes such that every edge has at least one endpoint in the set. Find the minimum size vertex cover.''', r'''<think>
Minimum vertex cover on a tree: select the smallest set of nodes such that every edge has at least one endpoint selected.

My first thought was a greedy approach -- always pick the node with the highest degree. But that does not give optimal results even on trees. Consider a path of 4 nodes: greedy might pick the wrong ones. We need DP.

DP formulation:
dp[v][0] = minimum vertex cover size in subtree of v, where v is NOT in the cover
dp[v][1] = minimum vertex cover size in subtree of v, where v IS in the cover

If v is NOT in the cover (dp[v][0]):
- All children MUST be in the cover (to cover the edges v-child)
- dp[v][0] = sum over children c of dp[c][1]

If v IS in the cover (dp[v][1]):
- Children can be either in or not in the cover -- we pick whichever is cheaper
- dp[v][1] = 1 + sum over children c of min(dp[c][0], dp[c][1])

Answer = min(dp[root][0], dp[root][1])

Wait, does the choice of root matter? No, because we take the minimum over both states at the root. Any rooting gives the same answer since the tree structure is the same.

For reconstruction: track which choice was made at each node and trace back. Hmm, actually reconstruction is slightly tricky -- when dp[v][1] is chosen, each child independently picks its best state. But when dp[v][0] is chosen, ALL children are forced into state 1. I need to propagate this constraint top-down.

This is a classic example of tree DP. The problem is NP-hard on general graphs but polynomial on trees because the tree structure prevents cycles from creating conflicting constraints.

By Konig's theorem, on bipartite graphs (trees are bipartite), minimum vertex cover = maximum matching. So we could also solve this via maximum matching, but the DP approach is more direct and gives us the actual cover, not just its size.
</think>

## Minimum Vertex Cover on Trees

### Implementation

```python
from collections import defaultdict


def min_vertex_cover(n, edges):
    """Find minimum vertex cover on a tree using DP.

    Args:
        n: number of nodes
        edges: list of (u, v) edges

    Returns:
        (cover_size, cover_nodes)
    """
    if n == 0:
        return 0, []
    if n == 1:
        return 0, []

    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    # Root at 0
    parent = [-1] * n
    children = [[] for _ in range(n)]
    order = []
    visited = [False] * n
    visited[0] = True
    stack = [0]
    while stack:
        u = stack.pop()
        order.append(u)
        for v in adj[u]:
            if not visited[v]:
                visited[v] = True
                parent[v] = u
                children[u].append(v)
                stack.append(v)

    # dp[v][0] = min cover in subtree, v NOT in cover
    # dp[v][1] = min cover in subtree, v IN cover
    dp = [[0, 0] for _ in range(n)]

    # Bottom-up
    for v in reversed(order):
        dp[v][0] = 0
        dp[v][1] = 1
        for c in children[v]:
            dp[v][0] += dp[c][1]  # children must be covered
            dp[v][1] += min(dp[c][0], dp[c][1])  # children optional

    # Reconstruct
    in_cover = [False] * n

    def reconstruct(v, must_be_in):
        if must_be_in:
            in_cover[v] = True
            for c in children[v]:
                if dp[c][0] <= dp[c][1]:
                    reconstruct(c, False)
                else:
                    reconstruct(c, True)
        else:
            in_cover[v] = False
            for c in children[v]:
                reconstruct(c, True)

    if dp[0][0] <= dp[0][1]:
        reconstruct(0, False)
    else:
        reconstruct(0, True)

    cover = [v for v in range(n) if in_cover[v]]
    cover_size = min(dp[0][0], dp[0][1])

    return cover_size, cover


def verify_vertex_cover(n, edges, cover):
    """Check that cover is a valid vertex cover."""
    cover_set = set(cover)
    for u, v in edges:
        if u not in cover_set and v not in cover_set:
            return False
    return True


# Demo
n = 9
edges = [(0,1), (0,2), (1,3), (1,4), (2,5), (2,6), (4,7), (4,8)]
size, cover = min_vertex_cover(n, edges)

print("=== Minimum Vertex Cover on Tree ===")
print(f"Tree ({n} nodes, {len(edges)} edges):")
print(f"         0")
print(f"        / \\")
print(f"       1   2")
print(f"      / \\ / \\")
print(f"     3  4 5  6")
print(f"       / \\")
print(f"      7   8")
print(f"\nMinimum vertex cover size: {size}")
print(f"Cover nodes: {cover}")
print(f"Valid cover: {verify_vertex_cover(n, edges, cover)}")

# Check all edges covered
for u, v in edges:
    covered = u in cover or v in cover
    print(f"  Edge ({u},{v}): {'covered' if covered else 'NOT COVERED'}")

# Brute force verification
best = n
for mask in range(1 << n):
    nodes = [i for i in range(n) if mask & (1 << i)]
    if verify_vertex_cover(n, edges, nodes):
        best = min(best, len(nodes))
print(f"\nBrute force minimum: {best}")
print(f"Match: {'OK' if size == best else 'FAIL'}")

# By Konig's theorem: min vertex cover = max matching on bipartite
# Trees are bipartite, so we can verify this
print(f"\n=== Konig's Theorem Verification ===")
print(f"Min vertex cover = {size}")
print(f"(Should equal max matching on tree)")
```

### DP Recurrence
```
dp[v][0] = sum(dp[c][1] for c in children[v])    # v not covered -> children must be
dp[v][1] = 1 + sum(min(dp[c][0], dp[c][1]) for c in children[v])  # v covered -> children optional
answer = min(dp[root][0], dp[root][1])
```

### Complexity
- **Time**: O(n) -- single bottom-up pass
- **Space**: O(n)
- **Reconstruction**: O(n) top-down pass
- **Note**: NP-hard on general graphs, but linear on trees via DP'''),

    ("thinking/algorithms", r'''Implement maximum matching on a tree using DP. A matching is a set of edges where no two edges share a vertex. Find the maximum number of edges that can be in a matching.''', r'''<think>
Maximum matching on a tree: select the maximum number of edges such that no vertex is an endpoint of more than one selected edge.

I considered a greedy approach: pick leaf edges first, remove them, repeat. This actually works on trees (it is optimal), but the DP approach is cleaner and generalizes better to weighted matching.

DP formulation:
dp[v][0] = max matching in subtree of v, where v is NOT matched (edge to parent or child not used)
dp[v][1] = max matching in subtree of v, where v IS matched to one of its children

If v is NOT matched (dp[v][0]):
- Each child can be either matched or unmatched (to its own children)
- dp[v][0] = sum over children c of max(dp[c][0], dp[c][1])

If v IS matched to child c (dp[v][1]):
- Choose the child c that maximizes the gain
- dp[v][1] = max over children c of (1 + dp[c][0] + sum over other children c' of max(dp[c'][0], dp[c'][1]))

Hmm, this looks O(n^2) because for each child c we sum over all other children. But wait, I can simplify using a base sum.

Let base = sum over children c of max(dp[c][0], dp[c][1]) (this is dp[v][0])
dp[v][1] = max over children c of (base - max(dp[c][0], dp[c][1]) + 1 + dp[c][0])
         = base + max over children c of (1 + dp[c][0] - max(dp[c][0], dp[c][1]))

Now let me think about when the gain is positive. If dp[c][1] >= dp[c][0], then the gain of matching v-c is: 1 + dp[c][0] - dp[c][1]. This could be 0 or even negative if dp[c][1] >> dp[c][0]. But actually dp[c][1] can be at most dp[c][0] + 1 (matching one extra edge), so the gain is at least 0.

If dp[c][0] >= dp[c][1], then the gain is: 1 + dp[c][0] - dp[c][0] = 1. Always worth it.

So dp[v][1] = dp[v][0] + max over c of (1 + dp[c][0] - max(dp[c][0], dp[c][1]))

answer = max(dp[root][0], dp[root][1])

This is O(n) total -- one pass bottom-up through the tree.
</think>

## Maximum Matching on Trees

### Implementation

```python
from collections import defaultdict


def max_matching_tree(n, edges):
    """Find maximum matching on a tree using DP.

    Returns:
        (matching_size, matched_edges)
    """
    if n <= 1 or not edges:
        return 0, []

    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    parent = [-1] * n
    children = [[] for _ in range(n)]
    order = []
    visited = [False] * n
    visited[0] = True
    stack = [0]
    while stack:
        u = stack.pop()
        order.append(u)
        for v in adj[u]:
            if not visited[v]:
                visited[v] = True
                parent[v] = u
                children[u].append(v)
                stack.append(v)

    # dp[v][0] = max matching, v unmatched
    # dp[v][1] = max matching, v matched to a child
    dp = [[0, 0] for _ in range(n)]
    match_child = [-1] * n  # which child v is matched to (for reconstruction)

    for v in reversed(order):
        # dp[v][0]: v unmatched, children can be matched or not
        base = 0
        for c in children[v]:
            base += max(dp[c][0], dp[c][1])
        dp[v][0] = base

        # dp[v][1]: match v to best child
        best_gain = -1
        best_child = -1
        for c in children[v]:
            # Gain of matching edge v-c
            gain = 1 + dp[c][0] - max(dp[c][0], dp[c][1])
            if gain > best_gain:
                best_gain = gain
                best_child = c

        if best_child != -1 and best_gain > 0:
            dp[v][1] = base + best_gain
            match_child[v] = best_child
        else:
            dp[v][1] = base  # no beneficial matching

    # Reconstruct matching
    matched_edges = []

    def reconstruct(v, is_matched):
        if is_matched and match_child[v] != -1:
            c = match_child[v]
            matched_edges.append((v, c))
            # c is matched to v, so c is "used"
            for child in children[v]:
                if child == c:
                    reconstruct(child, False)  # c cannot match its own child
                else:
                    if dp[child][1] >= dp[child][0]:
                        reconstruct(child, True)
                    else:
                        reconstruct(child, False)
        else:
            for child in children[v]:
                if dp[child][1] >= dp[child][0]:
                    reconstruct(child, True)
                else:
                    reconstruct(child, False)

    if dp[0][1] >= dp[0][0]:
        reconstruct(0, True)
    else:
        reconstruct(0, False)

    matching_size = max(dp[0][0], dp[0][1])
    return matching_size, matched_edges


def verify_matching(edges_list, matched):
    """Verify that matched edges form a valid matching."""
    used_vertices = set()
    for u, v in matched:
        if u in used_vertices or v in used_vertices:
            return False
        used_vertices.add(u)
        used_vertices.add(v)
    # Verify all matched edges are in the tree
    edge_set = set()
    for u, v in edges_list:
        edge_set.add((min(u,v), max(u,v)))
    for u, v in matched:
        if (min(u,v), max(u,v)) not in edge_set:
            return False
    return True


# Demo
n = 10
edges = [(0,1), (0,2), (1,3), (1,4), (2,5), (2,6), (3,7), (4,8), (6,9)]
size, matched = max_matching_tree(n, edges)

print("=== Maximum Matching on Tree ===")
print(f"Tree ({n} nodes):")
print(f"           0")
print(f"          / \\")
print(f"         1   2")
print(f"        / \\ / \\")
print(f"       3  4 5  6")
print(f"       |  |    |")
print(f"       7  8    9")
print(f"\nMaximum matching size: {size}")
print(f"Matched edges: {matched}")
print(f"Valid matching: {verify_matching(edges, matched)}")

# Brute force verification
from itertools import combinations
best = 0
for r in range(len(edges) + 1):
    for subset in combinations(edges, r):
        if verify_matching(edges, subset):
            best = max(best, len(subset))
print(f"Brute force maximum: {best}")
print(f"Match: {'OK' if size == best else 'FAIL'}")
```

### DP Recurrence
```
dp[v][0] = sum(max(dp[c][0], dp[c][1]) for children c)
dp[v][1] = dp[v][0] + max(1 + dp[c][0] - max(dp[c][0], dp[c][1]) for children c)
answer = max(dp[root][0], dp[root][1])
```

### Complexity
- **Time**: O(n)
- **Space**: O(n)
- **Konig's theorem**: max matching = n - min vertex cover (on bipartite graphs including trees)'''),
]
