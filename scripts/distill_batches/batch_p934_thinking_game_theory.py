PAIRS = [
    ("thinking/algorithms", r'''Explain the Sprague-Grundy theorem and implement a solver for a general combinatorial game. Show how to compute Grundy numbers and how the XOR of Grundy values determines the winner.''', r'''<think>
The Sprague-Grundy theorem -- I need to implement a general solver for impartial games.

First, some definitions. A position is "losing" (P-position) if the current player loses with optimal play, and "winning" (N-position) if the current player can win. The simplest approach would be to just classify positions as W/L using backward induction, but the Grundy number gives us something more powerful.

The Grundy number G(p) = mex({G(q) : q reachable from p}), where mex is the minimum excludant (smallest non-negative integer not in the set). Terminal positions (no moves) have G = 0.

But why bother with Grundy numbers instead of just W/L? Because of the composition theorem: for a game that is the sum of independent subgames, the combined Grundy number is the XOR of individual Grundy numbers. This is incredibly powerful -- it means I can analyze each subgame independently and combine with XOR. Without this, analyzing combined games would require examining the product of all state spaces.

Wait, let me verify my understanding with Nim. In Nim, each heap of size n has Grundy number n (since from a heap of n you can move to any heap of size 0..n-1, and mex({0,1,...,n-1}) = n). The XOR of heap sizes determines the winner. That matches Bouton's theorem, which is exactly what Sprague-Grundy generalizes.

For implementation, I need:
1. A mex function -- scan from 0 upward for the first gap in the set
2. Recursive Grundy computation with memoization (to avoid recomputing)
3. A demo showing XOR composition for combined subgames

I initially considered iterating through sorted sets for mex, but it is simpler to just check 0, 1, 2, ... until we find one not in the set. For small branching factors this is efficient enough.
</think>

## Sprague-Grundy Theorem

### Core Concepts
- Every impartial game position has a **Grundy number** G(p)
- G(p) = mex({G(q) : q reachable from p})
- For combined games: G(game1 + game2) = G(game1) XOR G(game2)
- First player wins iff G(position) != 0

### Implementation

```python
def mex(s):
    """Minimum excludant: smallest non-negative integer not in set s."""
    i = 0
    while i in s:
        i += 1
    return i


class GameSolver:
    """General Sprague-Grundy solver for impartial games."""

    def __init__(self, move_function):
        """move_function(state) -> list of reachable states."""
        self.moves = move_function
        self.cache = {}

    def grundy(self, state):
        """Compute Grundy number for a state."""
        if state in self.cache:
            return self.cache[state]
        reachable = self.moves(state)
        if not reachable:
            self.cache[state] = 0  # terminal = losing position
            return 0
        g = mex({self.grundy(s) for s in reachable})
        self.cache[state] = g
        return g

    def is_winning(self, state):
        """True if the current player can win."""
        return self.grundy(state) != 0

    def winning_move(self, state):
        """Find a move that leaves opponent in losing position."""
        for s in self.moves(state):
            if self.grundy(s) == 0:
                return s
        return None  # no winning move (losing position)


# Example 1: Subtraction game
# Remove 1, 2, or 3 stones from a pile
def subtraction_moves(n):
    return [n - k for k in [1, 2, 3] if n - k >= 0]

solver = GameSolver(subtraction_moves)
print("Subtraction game (remove 1,2,3):")
for n in range(13):
    g = solver.grundy(n)
    print(f"  G({n}) = {g}  ({'W' if g else 'L'})")
# Pattern: G(n) = n % 4


# Example 2: Combined games (XOR rule)
def combined_grundy(games, solver_func, states):
    """XOR of Grundy numbers for independent subgames."""
    total = 0
    for state in states:
        total ^= solver_func(state)
    return total

# Three piles of subtraction game
piles = [5, 7, 3]
xor_val = 0
for p in piles:
    g = solver.grundy(p)
    xor_val ^= g
    print(f"Pile {p}: G = {g}")
print(f"XOR = {xor_val} -> {'First player wins' if xor_val else 'Second player wins'}")


# Example 3: Nim (verification)
def nim_moves(n):
    return [n - k for k in range(1, n + 1)]  # remove any number

nim_solver = GameSolver(nim_moves)
print("\nNim verification (G(n) should equal n):")
for n in range(8):
    assert nim_solver.grundy(n) == n, f"Failed for n={n}"
print("  All G(n) = n verified for n = 0..7")

# Nim with 3 piles
piles = [3, 5, 6]
result = piles[0] ^ piles[1] ^ piles[2]
print(f"\nNim piles {piles}: XOR = {result}")
print(f"  {'First player wins' if result else 'Second player wins'}")
```

### Complexity
- **Grundy computation**: O(|states| * max_branching) with memoization
- **Combined game**: O(number of subgames) for XOR
- The theorem reduces exponential game trees to polynomial computation when subgames are independent'''),

    ("thinking/algorithms", r'''Implement solutions for Nim game variations: standard Nim, Misere Nim (last move loses), Staircase Nim, and Nim with restrictions (can only take up to half). Prove each strategy.''', r'''<think>
Four Nim variants. Let me think through each one carefully.

1. Standard Nim: XOR of all pile sizes. First player wins iff XOR != 0. This is Bouton's theorem, well-known.

2. Misere Nim (last move loses): This is tricky. My first instinct is "just flip the result of standard Nim," but that is wrong. The correct strategy is almost the same as normal Nim but with a twist at the endgame. Let me think...

If all piles have size <= 1, the game reduces to counting: the player forced to take the last stone loses, so you want an even number of remaining 1-piles. That means you win iff XOR = 0 (even number of 1s). But if any pile has size > 1, the strategy is the same as normal Nim (win iff XOR != 0). The key is that when reducing to the all-small position, you aim for an odd number of 1-piles so the opponent takes the last.

Wait, let me double-check: if all piles are 0 or 1, and there is an even number of 1s, then the current player takes one, leaving odd -- opponent takes next, and so on -- opponent takes the last. So even count = win for current player. That confirms XOR = 0 means even count means current player wins.

3. Staircase Nim: piles on stairs, you move stones from pile i to pile i-1 (pile 0 is the ground). I initially thought all piles matter, but the key insight is that moves to even-indexed piles are "free" -- they do not change the Grundy value. Only odd-indexed piles matter because moves from odd to even are like removing stones from Nim. So XOR of odd-indexed piles determines the winner.

4. Restricted Nim (take 1 to floor(n/2)): I considered whether this relates to Fibonacci numbers or Zeckendorf's representation, but let me just compute the Grundy numbers directly and look for a pattern. When n=1, floor(1/2)=0, so no moves -- losing. For n >= 2 the Grundy numbers should be computable via standard mex.
</think>

## Nim Game Variations

### Implementation

```python
def mex(s):
    i = 0
    while i in s:
        i += 1
    return i


# 1. Standard Nim
def standard_nim(piles):
    """First player wins iff XOR of all piles != 0."""
    xor = 0
    for p in piles:
        xor ^= p
    return xor != 0, xor


# 2. Misere Nim (last move LOSES)
def misere_nim(piles):
    """Like standard Nim but last move loses.
    Strategy: if all piles <= 1, win iff even count of 1s.
    Otherwise, win iff XOR != 0 (same as normal)."""
    xor = 0
    all_small = True
    for p in piles:
        xor ^= p
        if p > 1:
            all_small = False

    if all_small:
        # Even number of 1-piles means current player wins
        # (opponent will be forced to take the last one)
        count_ones = sum(1 for p in piles if p == 1)
        return count_ones % 2 == 0
    else:
        return xor != 0


# 3. Staircase Nim
def staircase_nim(piles):
    """Piles on a staircase; move stones from pile i to pile i-1.
    Only odd-indexed piles matter for the Grundy value."""
    xor = 0
    for i in range(len(piles)):
        if i % 2 == 1:  # odd indices
            xor ^= piles[i]
    return xor != 0, xor


# 4. Nim with restriction: take 1 to floor(n/2) stones
def restricted_nim_grundy(max_n):
    """Compute Grundy numbers for 'take 1 to floor(n/2)' game."""
    grundy = [0] * (max_n + 1)
    for n in range(1, max_n + 1):
        reachable = set()
        max_take = n // 2
        for k in range(1, max_take + 1):
            reachable.add(grundy[n - k])
        # Can also take all (n stones) to win? Only if n > 0
        # Actually, the game ends at 0. Let's say you must take 1..floor(n/2)
        # If floor(n/2) == 0 (n==1), you cannot move -> losing
        if max_take == 0:
            grundy[n] = 0  # no moves available, losing
        else:
            grundy[n] = mex(reachable)
    return grundy


# Demo
print("=== Standard Nim ===")
tests = [[3, 4, 5], [1, 1], [4, 4], [1, 2, 3]]
for piles in tests:
    wins, xor = standard_nim(piles)
    print(f"  Piles {piles}: XOR={xor}, First player {'wins' if wins else 'loses'}")

print("\n=== Misere Nim ===")
tests_m = [[1, 1], [1, 1, 1], [2, 3], [1, 2, 3], [4, 4]]
for piles in tests_m:
    wins = misere_nim(piles)
    print(f"  Piles {piles}: First player {'wins' if wins else 'loses'}")

print("\n=== Staircase Nim ===")
stairs = [2, 5, 3, 1, 4]
wins, xor = staircase_nim(stairs)
print(f"  Stairs {stairs}: XOR(odd)={xor}, First player {'wins' if wins else 'loses'}")
# Odd-indexed: piles[1]=5, piles[3]=1 -> XOR = 5^1 = 4 -> wins

print("\n=== Restricted Nim (take 1 to n//2) ===")
g = restricted_nim_grundy(20)
print("  Grundy numbers:")
for n in range(21):
    print(f"    G({n:2d}) = {g[n]}", end="")
    if n > 0 and n // 2 == 0:
        print("  (no moves)", end="")
    print()

# The pattern: G(n) = 0 for n = 0, 1 (losing)
# For n >= 2: non-trivial pattern related to binary representation
```

### Strategy Proofs

**Standard Nim**: Bouton's theorem (1901). XOR = 0 is invariant under optimal play by second player. If XOR != 0, first player can always move to XOR = 0.

**Misere Nim**: When all piles are <= 1, the game reduces to counting. Otherwise, play normal Nim strategy but aim to leave an odd number of 1-piles when reducing to all-small position.

**Staircase Nim**: Moving stones from odd to even index is "free" (does not change the Grundy value). Moving from even to odd is equivalent to adding to a Nim pile. So only odd-indexed piles matter.

### Complexity
- Standard/Misere/Staircase: O(n) to evaluate
- Restricted: O(n^2) to precompute Grundy numbers up to n'''),

    ("thinking/algorithms", r'''Implement minimax with alpha-beta pruning for a two-player zero-sum game. Use it to solve Tic-Tac-Toe optimally and show the pruning improvement over plain minimax.''', r'''<think>
Minimax with alpha-beta pruning for Tic-Tac-Toe. Let me think about the algorithm.

Plain minimax is simple: the maximizer picks the highest-value move, the minimizer picks the lowest. For Tic-Tac-Toe with X as maximizer (+1 win, -1 loss, 0 draw), we recursively evaluate all possible games. But this explores the entire game tree -- about 549,946 nodes from an empty board.

Can we prune? Yes -- alpha-beta pruning. The idea is to maintain a window [alpha, beta]:
- alpha = best score the maximizer can already guarantee
- beta = best score the minimizer can already guarantee

At a MAX node, if we find a child with value >= beta, we can stop. Why? Because the MIN parent already has a better option (beta), so it would never choose this branch. Similarly at a MIN node, if value <= alpha, prune.

I initially wondered: does the pruning order matter? Actually, yes -- dramatically. If we evaluate the best move first, alpha-beta achieves O(b^(d/2)) instead of O(b^d). For Tic-Tac-Toe we do not bother with move ordering since the game tree is small, but for chess or Go it is critical.

Let me implement both plain minimax and alpha-beta, count nodes evaluated, and compare. Tic-Tac-Toe should show a significant reduction -- I expect alpha-beta to evaluate maybe 5-10x fewer nodes even without move ordering.

One subtlety: for the best_move function, I need to evaluate all top-level moves (cannot prune the root), but the recursive calls below benefit from pruning.
</think>

## Minimax with Alpha-Beta Pruning

### Implementation: Optimal Tic-Tac-Toe

```python
class TicTacToe:
    """Tic-Tac-Toe with minimax and alpha-beta pruning."""

    def __init__(self):
        self.board = [' '] * 9  # 3x3 board as flat array
        self.nodes_evaluated = 0

    def copy(self):
        t = TicTacToe()
        t.board = self.board[:]
        return t

    def winner(self):
        """Return 'X', 'O', or None."""
        lines = [
            (0,1,2), (3,4,5), (6,7,8),  # rows
            (0,3,6), (1,4,7), (2,5,8),  # cols
            (0,4,8), (2,4,6),           # diagonals
        ]
        for a, b, c in lines:
            if self.board[a] == self.board[b] == self.board[c] != ' ':
                return self.board[a]
        return None

    def is_terminal(self):
        return self.winner() is not None or ' ' not in self.board

    def moves(self):
        return [i for i in range(9) if self.board[i] == ' ']

    def minimax(self, is_maximizing):
        """Plain minimax without pruning."""
        self.nodes_evaluated += 1
        w = self.winner()
        if w == 'X':
            return 1
        if w == 'O':
            return -1
        if ' ' not in self.board:
            return 0

        if is_maximizing:
            best = -2
            for m in self.moves():
                self.board[m] = 'X'
                best = max(best, self.minimax(False))
                self.board[m] = ' '
            return best
        else:
            best = 2
            for m in self.moves():
                self.board[m] = 'O'
                best = min(best, self.minimax(True))
                self.board[m] = ' '
            return best

    def alphabeta(self, is_maximizing, alpha=-2, beta=2):
        """Minimax with alpha-beta pruning."""
        self.nodes_evaluated += 1
        w = self.winner()
        if w == 'X':
            return 1
        if w == 'O':
            return -1
        if ' ' not in self.board:
            return 0

        if is_maximizing:
            best = -2
            for m in self.moves():
                self.board[m] = 'X'
                val = self.alphabeta(False, alpha, beta)
                self.board[m] = ' '
                best = max(best, val)
                alpha = max(alpha, val)
                if alpha >= beta:
                    break  # beta cutoff
            return best
        else:
            best = 2
            for m in self.moves():
                self.board[m] = 'O'
                val = self.alphabeta(True, alpha, beta)
                self.board[m] = ' '
                best = min(best, val)
                beta = min(beta, val)
                if alpha >= beta:
                    break  # alpha cutoff
            return best

    def best_move(self, player='X'):
        """Find the best move using alpha-beta."""
        is_max = (player == 'X')
        best_val = -2 if is_max else 2
        best_m = -1
        for m in self.moves():
            self.board[m] = player
            val = self.alphabeta(not is_max)
            self.board[m] = ' '
            if is_max and val > best_val:
                best_val = val
                best_m = m
            elif not is_max and val < best_val:
                best_val = val
                best_m = m
        return best_m, best_val

    def display(self):
        for i in range(3):
            row = ' | '.join(self.board[i*3:(i+1)*3])
            print(f"  {row}")
            if i < 2:
                print("  ---------")


# Compare minimax vs alpha-beta
game1 = TicTacToe()
game1.nodes_evaluated = 0
val1 = game1.minimax(True)
plain_nodes = game1.nodes_evaluated

game2 = TicTacToe()
game2.nodes_evaluated = 0
val2 = game2.alphabeta(True)
ab_nodes = game2.nodes_evaluated

print(f"Empty board value: {val1} (draw with optimal play)")
print(f"Plain minimax nodes: {plain_nodes}")
print(f"Alpha-beta nodes:    {ab_nodes}")
print(f"Pruning saved:       {plain_nodes - ab_nodes} nodes "
      f"({100*(plain_nodes-ab_nodes)/plain_nodes:.1f}%)")

# Play a game: AI vs AI
print("\n--- AI vs AI Game ---")
game = TicTacToe()
turn = 'X'
while not game.is_terminal():
    move, val = game.best_move(turn)
    game.board[move] = turn
    turn = 'O' if turn == 'X' else 'X'
game.display()
print(f"Result: {game.winner() or 'Draw'}")
```

### Complexity
- **Plain minimax**: O(b^d) where b=branching, d=depth
- **Alpha-beta**: O(b^(d/2)) best case (perfect move ordering)
- **Tic-Tac-Toe**: ~549,946 nodes (plain) vs ~18,000-30,000 (alpha-beta)

### Alpha-Beta Pruning Rules
- **At MAX node**: if value >= beta, prune (MIN parent will not choose this)
- **At MIN node**: if value <= alpha, prune (MAX parent will not choose this)
- **Move ordering** dramatically improves pruning -- try best moves first'''),

    ("thinking/algorithms", r'''Model and solve a game played on a directed graph. Each player moves a token along an edge; the player who cannot move loses. Compute which positions are winning/losing using the Sprague-Grundy approach.''', r'''<think>
A game on a directed graph: token on a node, players alternate moving along edges, last player to move wins. I need to compute which positions are winning vs losing.

This is an impartial game, so Sprague-Grundy applies. Terminal nodes (no outgoing edges) are losing -- G = 0. For other nodes, G = mex({G(v) : v is a successor}).

But wait -- what about cycles? If the graph has cycles, a game could potentially last forever, and Grundy numbers might not be well-defined. I need to assume the graph is a DAG (no infinite play). For DAGs, I can compute Grundy numbers using topological sort: process nodes in reverse topological order, so all successors are already computed.

Hmm, actually there is a simpler approach too -- just W/L marking via backward induction:
- Terminal nodes are L (losing)
- A node is W if any successor is L (you can move to a losing position for your opponent)
- A node is L if ALL successors are W (every move leaves your opponent winning)

This is equivalent to checking G > 0 vs G = 0, but does not give us the full Grundy numbers. The Grundy numbers are more useful because they enable the XOR composition for multi-token games. So I should implement both.

For the W/L computation, I initially considered DFS, but reverse BFS is cleaner: start from terminal nodes, propagate backward. When a node marked L is found, all its predecessors become W. When a predecessor has all successors resolved as W, it becomes L. This naturally handles the propagation order.

I will also demonstrate the multi-token game: with two tokens on the graph, the combined Grundy number is XOR of individual values, determining the winner.
</think>

## Game on a Directed Graph

### Computing Winning/Losing Positions

```python
from collections import deque


def compute_win_lose(adj, n):
    """Compute W/L for each node in a game on DAG.

    A node is L (losing) if all successors are W (or no successors).
    A node is W (winning) if any successor is L.

    Uses reverse BFS from terminal nodes.
    """
    out_degree = [0] * n
    rev_adj = [[] for _ in range(n)]
    for u in range(n):
        out_degree[u] = len(adj[u])
        for v in adj[u]:
            rev_adj[v].append(u)

    status = ['?'] * n  # 'W', 'L', or '?'
    remaining = list(out_degree)  # unresolved successor count
    queue = deque()

    # Terminal nodes are losing
    for u in range(n):
        if out_degree[u] == 0:
            status[u] = 'L'
            queue.append(u)

    while queue:
        v = queue.popleft()
        for u in rev_adj[v]:
            if status[u] != '?':
                continue
            if status[v] == 'L':
                # u has a successor that is losing -> u is winning
                status[u] = 'W'
                queue.append(u)
            else:
                # status[v] == 'W', this successor does not help u
                remaining[u] -= 1
                if remaining[u] == 0:
                    # All successors are W -> u is losing
                    status[u] = 'L'
                    queue.append(u)

    return status


def compute_grundy_dag(adj, n):
    """Compute Grundy numbers on a DAG using topological sort."""
    from collections import deque

    in_degree = [0] * n
    for u in range(n):
        for v in adj[u]:
            in_degree[v] += 1

    # Topological sort
    topo = []
    queue = deque(u for u in range(n) if in_degree[u] == 0)
    while queue:
        u = queue.popleft()
        topo.append(u)
        for v in adj[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    # Compute Grundy in reverse topological order
    grundy = [0] * n
    for u in reversed(topo):
        reachable = set()
        for v in adj[u]:
            reachable.add(grundy[v])
        # mex
        g = 0
        while g in reachable:
            g += 1
        grundy[u] = g

    return grundy


# Example: Game on a DAG
# Nodes 0-7, edges form a DAG
n = 8
adj = [[] for _ in range(n)]
edges = [
    (0, 1), (0, 2),
    (1, 3), (1, 4),
    (2, 4), (2, 5),
    (3, 6),
    (4, 6), (4, 7),
    (5, 7),
    # 6 and 7 are terminal (no outgoing edges)
]
for u, v in edges:
    adj[u].append(v)

status = compute_win_lose(adj, n)
grundy = compute_grundy_dag(adj, n)

print("Node | W/L | Grundy")
print("-----|-----|-------")
for i in range(n):
    print(f"  {i}  |  {status[i]}  |   {grundy[i]}")

# Verify consistency
for i in range(n):
    wl = 'W' if grundy[i] > 0 else 'L'
    assert wl == status[i], f"Mismatch at node {i}"
print("\nGrundy and W/L are consistent.")


# Multi-token game: two tokens on the graph
# Combined game: XOR of Grundy values
print("\n--- Two-token game ---")
pos1, pos2 = 0, 2
g_combined = grundy[pos1] ^ grundy[pos2]
print(f"Token 1 at {pos1} (G={grundy[pos1]})")
print(f"Token 2 at {pos2} (G={grundy[pos2]})")
print(f"Combined Grundy: {g_combined}")
print(f"First player {'wins' if g_combined else 'loses'}")
```

### Complexity
- **W/L computation**: O(V + E) using reverse BFS
- **Grundy computation**: O(V + E) on DAG with topological sort
- **Multi-token extension**: O(tokens) for XOR after individual Grundy computation

### Key Insight
The game graph naturally encodes all possible plays. Terminal nodes with no outgoing edges are losing positions. The backward induction (or Grundy number computation) propagates this information through the entire graph.'''),

    ("thinking/algorithms", r'''Explain and implement solutions for classic combinatorial games: Wythoff's game, Green Hackenbush, and the Turning Turtles game. Show how each reduces to known Grundy theory.''', r'''<think>
Three classic combinatorial games. Let me think through each one.

1. Wythoff's Game: Two piles. Remove any number from one pile, OR remove the same number from both piles. I need to find the losing positions (cold positions).

My first thought: compute them by brute force and look for a pattern. The losing positions for small values are (0,0), (1,2), (3,5), (4,7), (6,10)... The differences between the pair elements are 0, 1, 2, 3, 4 -- exactly k for the k-th pair. And the smaller element follows floor(k * phi) where phi = (1+sqrt(5))/2. This connects to Beatty's theorem -- the two Beatty sequences for phi and phi^2 partition the positive integers, which is why each number appears in exactly one cold position.

2. Green Hackenbush: A graph game where you remove an edge, and anything disconnected from the ground vanishes. For trees rooted at the ground, I need the Grundy number.

A path of n edges has Grundy number n (like a Nim pile -- you can remove any edge to leave two shorter paths, but by Sprague-Grundy, mex gives n). For trees, the Colon Principle says we can compute bottom-up. But what exactly is the formula?

Let me work through an example. A star with 3 leaf edges from ground: removing any edge gives a star with 2 edges. G(star_1) = mex({G(star_0)}) = mex({0}) = 1. G(star_2) = mex({G(star_1)}) = mex({1}) = 0. G(star_3) = mex({G(star_2)}) = mex({0}) = 1. So G alternates 0,1 based on parity -- which equals XOR of k ones.

Hmm, for a general tree, I think the formula is: nimber(v) = XOR over children c of (nimber(c) + 1). Let me verify with a path: ground - v1 - v2 - v3. nimber(v3) = 0 (leaf, no children). nimber(v2) = 0 + 1 = 1. nimber(v1) = 1 + 1 = 2. nimber(ground) = 2 + 1 = 3. That matches path length 3. And for the star: nimber(ground) = (0+1) XOR (0+1) XOR (0+1) = 1 XOR 1 XOR 1 = 1. Correct! I will implement this formula computationally and verify.

3. Turning Turtles: flip the rightmost face-up turtle down, optionally flip one to its left. This reduces to Nim where each face-up turtle at position i contributes Grundy number i. So XOR of face-up positions determines the winner. The reasoning: flipping the rightmost face-up turtle down is like removing a Nim pile, and optionally flipping another is like a Mock Turtles game move that does not change the Grundy parity.
</think>

## Classic Combinatorial Games

### 1. Wythoff's Game

```python
import math

def wythoff_cold_positions(n):
    """Generate first n cold (losing) positions of Wythoff's game.
    Cold positions: (floor(k*phi), floor(k*phi^2)) for k=0,1,2,..."""
    phi = (1 + math.sqrt(5)) / 2
    positions = []
    for k in range(n):
        a = int(k * phi)
        b = int(k * phi * phi)
        positions.append((a, b))
    return positions

def wythoff_is_losing(a, b):
    """Check if (a, b) is a losing position in Wythoff's game."""
    if a > b:
        a, b = b, a
    phi = (1 + math.sqrt(5)) / 2
    k = b - a
    expected_a = int(k * phi)
    return a == expected_a

print("=== Wythoff's Game ===")
print("Cold (losing) positions:")
for a, b in wythoff_cold_positions(10):
    print(f"  ({a}, {b})")

# Test some positions
tests = [(0,0), (1,2), (3,5), (2,3), (4,7)]
for a, b in tests:
    result = "LOSE" if wythoff_is_losing(a, b) else "WIN"
    print(f"  ({a},{b}): {result}")
```

### 2. Green Hackenbush on Trees

```python
def hackenbush_grundy(adj, ground=0):
    """Compute Grundy number for Green Hackenbush on a tree.
    The Colon Principle: G(node) = XOR of (1 + G(child)) for each child.
    Wait -- actually for rooted trees:
    G(leaf) = 0 (no children)
    G(node) = XOR of (1 + G(child)) ... no.

    Correct: Nim-value of a bamboo stalk (path) of length n is n.
    For a tree, by the Colon Principle:
    G(subtree rooted at v) = XOR over children c of G(subtree at c)
    But each edge adds 1 to the "height" of the game.

    Standard result: for tree rooted at ground,
    G = XOR over children c of (1 XOR G(subtree_c))... no.

    Let me compute it directly via game analysis.
    """
    # BFS to build rooted tree
    n = len(adj)
    parent = [-1] * n
    children = [[] for _ in range(n)]
    visited = [False] * n
    visited[ground] = True
    queue = [ground]
    order = []
    while queue:
        u = queue.pop(0)
        order.append(u)
        for v in adj[u]:
            if not visited[v]:
                visited[v] = True
                parent[v] = u
                children[u].append(v)
                queue.append(v)

    # Bottom-up Grundy computation
    # For Green Hackenbush on trees:
    # Each subtree hanging from an edge is an independent game
    # A single edge has nimber 1
    # A path of k edges has nimber k
    # By Colon Principle: nimber(subtree at v) is computed,
    # then the edge connecting v to parent has nimber 1,
    # and the combined nimber for the branch is nimber(subtree) XOR ...
    # Actually: the nimber contributed by the subtree rooted at child c
    # (including the edge from parent to c) = G(c_subtree) + 1
    # where + is nim-addition? No -- for paths it should give path length.
    # Path: ground - v1 - v2 - v3. G(v3)=0, edge v2-v3 contributes 1.
    # G(v2) should be 1. Edge v1-v2 contributes... G(v1) = 1+1 = 2?
    # That gives 2 for path of 3, but it should be 3.
    # Hmm, G(v1) = G(child_contribution) where child is v2.
    # child_contribution = G(v2) + 1? But G(v2) = 1, so 2.
    # Then G(ground) considers v1 as child: contribution = 2+1 = 3.
    # Yes! Each edge adds 1. For a node with children c1, c2:
    # G(node) = XOR of contributions, where contribution(ci) = G(ci) + 1.
    # Wait, G(ci) here means the contribution already, and we add the edge.
    # Let me define it properly:
    # nimber(v) = XOR over children c of (nimber(c) + 1)
    # where + is ordinary addition for paths (which equals XOR for these cases?)
    # No, for a star with 3 children: nimber = (0+1) XOR (0+1) XOR (0+1) = 1 XOR 1 XOR 1 = 1
    # But a star with 3 edges should have nimber... actually it's a position
    # where you remove one edge and the game continues.
    # For star with k edges: removing any edge gives star with k-1 edges.
    # G(star_k) = mex({G(star_{k-1})}) ... G(star_1)=mex({G(star_0)})=mex({0})=1
    # G(star_2) = mex({G(star_1), G(star_1)}) = mex({1}) = 0
    # Hmm, but that depends on which edge you remove giving the same result.
    # Actually for star with k edges from ground, removing any edge gives star with k-1.
    # So G(star_k) = mex({G(star_{k-1})}).
    # G(0)=0, G(1)=1, G(2)=mex({1})=0, G(3)=mex({0})=1, ...
    # So star with even edges: 0, odd: 1. This matches XOR of 1s.

    nimber = [0] * n
    for v in reversed(order):
        val = 0
        for c in children[v]:
            val ^= (nimber[c] + 1)
        nimber[v] = val

    return nimber[ground]

print("\n=== Green Hackenbush ===")
# Path of length 3: ground-1-2-3
adj_path = [[] for _ in range(4)]
for u, v in [(0,1),(1,2),(2,3)]:
    adj_path[u].append(v)
    adj_path[v].append(u)
print(f"Path of 3 edges: G = {hackenbush_grundy(adj_path, 0)}")  # 3

# Star with 3 edges
adj_star = [[] for _ in range(4)]
for v in [1,2,3]:
    adj_star[0].append(v)
    adj_star[v].append(0)
print(f"Star with 3 edges: G = {hackenbush_grundy(adj_star, 0)}")  # 1
```

### 3. Turning Turtles

```python
def turning_turtles(turtles):
    """Turtles game: list of booleans (True=face up).
    Turn: flip rightmost face-up turtle down, optionally flip one to its left.
    Equivalent to Nim where face-up turtle at position i has Grundy = i.
    First player wins iff XOR of positions of face-up turtles != 0."""
    xor = 0
    face_up_positions = []
    for i, t in enumerate(turtles):
        if t:
            xor ^= i
            face_up_positions.append(i)
    return xor != 0, xor, face_up_positions

print("\n=== Turning Turtles ===")
# True = face up, False = face down
turtles = [True, False, True, True, False, True]
wins, xor, positions = turning_turtles(turtles)
print(f"Turtles: {['U' if t else 'D' for t in turtles]}")
print(f"Face-up at positions: {positions}")
print(f"XOR = {xor}, First player {'wins' if wins else 'loses'}")
```

### Summary
| Game | Losing Condition | Key Insight |
|------|-----------------|-------------|
| Wythoff | (floor(k*phi), floor(k*phi^2)) | Golden ratio positions |
| Hackenbush | G(tree) = 0 | Colon Principle, XOR of branches |
| Turning Turtles | XOR of face-up positions = 0 | Reduces to Nim |'''),
]
