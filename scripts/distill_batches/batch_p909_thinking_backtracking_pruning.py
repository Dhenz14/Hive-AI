PAIRS = [
    ("thinking/algorithms", r'''Solve the N-Queens problem using backtracking with bitmasking for efficient constraint checking. Place N queens on an NxN chessboard so that no two queens threaten each other. Return all distinct solutions.''', r'''<think>
N-Queens with bitmasking. My first thought was to use arrays or sets to track attacked columns and diagonals, but wait -- that would require O(N) lookup per constraint check in the worst case. Can I do better?

Yes! Bitmasks allow O(1) constraint checking. I need three bitmasks:
- `cols`: which columns are occupied
- `diag1`: which "\" diagonals are occupied
- `diag2`: which "/" diagonals are occupied

At each row, the available positions are: ~(cols | diag1 | diag2) & ((1 << N) - 1). This single bitwise expression gives me all valid placements at once -- no loops needed.

But hmm, how do I extract individual positions from the available bitmask? I could iterate through bits with a for loop and check each one... actually, there is a much better trick: bit = available & (-available) gives the lowest set bit directly (two's complement trick). Then I remove it with available ^= bit and repeat. This visits only the set bits, skipping zeros entirely.

I initially worried about how the diagonal masks propagate between rows. Let me think carefully: when I place a queen at column bit in row r, the "\" diagonal constraint shifts right as we go to the next row (because row increases but the diagonal index stays relative), and the "/" diagonal shifts left. So the update is: diag1 = (diag1 | bit) >> 1 and diag2 = (diag2 | bit) << 1. Actually wait, I need to double-check this direction. A "\" diagonal has constant (row - col), so going down one row means the column constraint moves right -- yes, shift right is correct. And "/" has constant (row + col), so going down means column constraint moves left -- shift left. Good.

Time: still O(N!) in the worst case since we try all valid placements, but the bitmask pruning makes it orders of magnitude faster in practice. For N=12, the bitmask approach solves in milliseconds versus seconds for array-based checking.
</think>

## N-Queens with Bitmask Backtracking

Using bitmasks for columns and both diagonal directions provides O(1) per-move constraint checking.

```python
from typing import List


def solve_n_queens(n: int) -> List[List[str]]:
    """
    Find all solutions to the N-Queens problem using bitmask backtracking.

    Args:
        n: Board size / number of queens.

    Returns:
        List of solutions, each as a list of strings representing the board.

    Time:  O(N!) worst case, heavily pruned in practice
    Space: O(N) for recursion depth
    """
    solutions: List[List[int]] = []
    queens: List[int] = []  # queens[row] = col

    all_bits = (1 << n) - 1

    def backtrack(row: int, cols: int, diag1: int, diag2: int) -> None:
        if row == n:
            solutions.append(queens[:])
            return

        # Available positions: bits NOT attacked by any constraint
        available = all_bits & ~(cols | diag1 | diag2)

        while available:
            # Extract lowest set bit
            bit = available & (-available)
            available ^= bit  # remove this bit

            col = bit.bit_length() - 1
            queens.append(col)

            # Place queen and recurse
            # diag1 shifts right (going down-right), diag2 shifts left (going down-left)
            backtrack(
                row + 1,
                cols | bit,
                (diag1 | bit) >> 1,
                (diag2 | bit) << 1,
            )

            queens.pop()

    backtrack(0, 0, 0, 0)

    # Convert to board representation
    result: List[List[str]] = []
    for placement in solutions:
        board = []
        for col in placement:
            board.append("." * col + "Q" + "." * (n - col - 1))
        result.append(board)

    return result


def count_n_queens(n: int) -> int:
    """Count the number of N-Queens solutions (faster, no board construction)."""
    all_bits = (1 << n) - 1
    count = 0

    def backtrack(cols: int, diag1: int, diag2: int) -> None:
        nonlocal count
        if cols == all_bits:
            count += 1
            return

        available = all_bits & ~(cols | diag1 | diag2)
        while available:
            bit = available & (-available)
            available ^= bit
            backtrack(
                cols | bit,
                (diag1 | bit) >> 1,
                (diag2 | bit) << 1,
            )

    backtrack(0, 0, 0)
    return count


# ---------- Tests ----------

def test_n4():
    solutions = solve_n_queens(4)
    assert len(solutions) == 2, f"Expected 2 solutions, got {len(solutions)}"
    print(f"4-Queens: {len(solutions)} solutions")
    for s in solutions:
        for row in s:
            print(f"  {row}")
        print()


def test_n8():
    count = count_n_queens(8)
    assert count == 92, f"Expected 92, got {count}"
    print(f"8-Queens: {count} solutions")


def test_n1():
    solutions = solve_n_queens(1)
    assert len(solutions) == 1
    assert solutions[0] == ["Q"]
    print("1-Queen: 1 solution")


if __name__ == "__main__":
    test_n4()
    test_n8()
    test_n1()
    print("All N-Queens tests passed!")
```

### Bitmask Trick Explained
- `available & (-available)` extracts the lowest set bit (two's complement trick)
- Diagonal masks shift after each row: `diag1 >> 1` propagates the "\" diagonal constraint downward, `diag2 << 1` propagates "/"
- This eliminates all loops for constraint checking — pure bitwise operations

### Complexity
- **Time:** O(N!) upper bound, but bitmask pruning explores far fewer branches. N=14 solves in under a second.
- **Space:** O(N) for the recursion stack.
- **Known counts:** N=8→92, N=12→14200, N=14→365596
'''),

    ("thinking/algorithms", r'''Implement a Sudoku solver using backtracking with constraint propagation. Use the "naked singles" and "hidden singles" techniques to reduce the search space before resorting to trial-and-error.''', r'''<think>
Sudoku solver: 9x9 grid, fill 1-9 in each cell such that each row, column, and 3x3 box has all digits 1-9.

My first idea was pure backtracking: try each possibility at each empty cell. But wait, that could be horrendously slow for hard puzzles -- up to 9^81 branches in the worst case. There must be a better way.

Constraint propagation can eliminate most possibilities before we even start guessing:
1. Naked singles: if a cell has only one possible value, it must be that value
2. Hidden singles: if a value can only go in one cell within a row/column/box, place it there

I initially thought naked singles alone would be sufficient, but actually many puzzles require hidden singles too. Consider a row where digit 7 is possible in cells A, B, and C. Naked singles would not help here (each cell has multiple candidates). But if after checking the column and box constraints, only cell B can actually hold 7 in that row, then 7 must go in B. That is a hidden single.

Strategy:
- Maintain a "possible" set for each empty cell
- Apply constraint propagation until no more deductions can be made
- If stuck, pick the cell with fewest possibilities (MRV heuristic) and try each
- Backtrack if contradiction found (a cell has zero possibilities)

Hmm, which cell should I branch on when stuck? I considered random selection, but the MRV (Minimum Remaining Values) heuristic is much better. A cell with 2 possibilities has at most 1 wrong guess before finding the right value, while a cell with 8 possibilities could waste 7 attempts. So MRV minimizes the branching factor and causes contradictions to surface faster.

For data structures, I will use possible[r][c] = set of possible digits. I also need deep copies when branching, since backtracking requires restoring the previous state.
</think>

## Sudoku Solver with Constraint Propagation

```python
from typing import List, Optional, Set, Tuple
import copy


def solve_sudoku(board: List[List[int]]) -> Optional[List[List[int]]]:
    """
    Solve a 9x9 Sudoku puzzle using constraint propagation + backtracking.

    Args:
        board: 9x9 grid where 0 represents empty cells, 1-9 are filled.

    Returns:
        Solved board, or None if unsolvable.

    Uses naked singles, hidden singles, and MRV heuristic.
    """
    # Initialize possible values for each cell
    possible: List[List[Set[int]]] = [[set() for _ in range(9)] for _ in range(9)]

    for r in range(9):
        for c in range(9):
            if board[r][c] == 0:
                possible[r][c] = set(range(1, 10))
            else:
                possible[r][c] = set()

    # Remove initial constraints
    for r in range(9):
        for c in range(9):
            if board[r][c] != 0:
                _eliminate(board, possible, r, c, board[r][c])

    return _solve(board, possible)


def _eliminate(
    board: List[List[int]],
    possible: List[List[Set[int]]],
    row: int,
    col: int,
    val: int,
) -> bool:
    """Remove val from peers of (row, col). Returns False if contradiction."""
    # Remove from same row
    for c in range(9):
        if c != col:
            possible[row][c].discard(val)
            if board[row][c] == 0 and len(possible[row][c]) == 0:
                return False

    # Remove from same column
    for r in range(9):
        if r != row:
            possible[r][col].discard(val)
            if board[r][col] == 0 and len(possible[r][col]) == 0:
                return False

    # Remove from same 3x3 box
    br, bc = 3 * (row // 3), 3 * (col // 3)
    for r in range(br, br + 3):
        for c in range(bc, bc + 3):
            if (r, c) != (row, col):
                possible[r][c].discard(val)
                if board[r][c] == 0 and len(possible[r][c]) == 0:
                    return False

    return True


def _propagate(
    board: List[List[int]],
    possible: List[List[Set[int]]],
) -> bool:
    """Apply constraint propagation. Returns False if contradiction."""
    changed = True
    while changed:
        changed = False

        # Naked singles: cells with only one possibility
        for r in range(9):
            for c in range(9):
                if board[r][c] == 0 and len(possible[r][c]) == 1:
                    val = next(iter(possible[r][c]))
                    board[r][c] = val
                    possible[r][c] = set()
                    if not _eliminate(board, possible, r, c, val):
                        return False
                    changed = True

        # Hidden singles: value possible in only one cell in a unit
        for val in range(1, 10):
            # Check rows
            for r in range(9):
                candidates = [c for c in range(9) if val in possible[r][c]]
                if len(candidates) == 0:
                    if not any(board[r][c] == val for c in range(9)):
                        return False
                elif len(candidates) == 1:
                    c = candidates[0]
                    board[r][c] = val
                    possible[r][c] = set()
                    if not _eliminate(board, possible, r, c, val):
                        return False
                    changed = True

            # Check columns
            for c in range(9):
                candidates = [r for r in range(9) if val in possible[r][c]]
                if len(candidates) == 0:
                    if not any(board[r][c] == val for r in range(9)):
                        return False
                elif len(candidates) == 1:
                    r = candidates[0]
                    board[r][c] = val
                    possible[r][c] = set()
                    if not _eliminate(board, possible, r, c, val):
                        return False
                    changed = True

            # Check 3x3 boxes
            for br in range(0, 9, 3):
                for bc in range(0, 9, 3):
                    candidates = [
                        (r, c)
                        for r in range(br, br + 3)
                        for c in range(bc, bc + 3)
                        if val in possible[r][c]
                    ]
                    if len(candidates) == 0:
                        if not any(
                            board[r][c] == val
                            for r in range(br, br + 3)
                            for c in range(bc, bc + 3)
                        ):
                            return False
                    elif len(candidates) == 1:
                        r, c = candidates[0]
                        board[r][c] = val
                        possible[r][c] = set()
                        if not _eliminate(board, possible, r, c, val):
                            return False
                        changed = True

    return True


def _solve(
    board: List[List[int]],
    possible: List[List[Set[int]]],
) -> Optional[List[List[int]]]:
    """Recursive solve with constraint propagation + MRV branching."""
    if not _propagate(board, possible):
        return None

    # Check if solved
    empty_cells = [
        (len(possible[r][c]), r, c)
        for r in range(9)
        for c in range(9)
        if board[r][c] == 0
    ]

    if not empty_cells:
        return board  # Solved!

    # MRV: choose cell with fewest possibilities
    empty_cells.sort()
    _, row, col = empty_cells[0]

    for val in list(possible[row][col]):
        # Deep copy state
        board_copy = [row[:] for row in board]
        poss_copy = [[cell.copy() for cell in row] for row in possible]

        board_copy[row][col] = val
        poss_copy[row][col] = set()
        if _eliminate(board_copy, poss_copy, row, col, val):
            result = _solve(board_copy, poss_copy)
            if result is not None:
                return result

    return None  # No valid assignment


# ---------- Tests ----------

def test_easy():
    board = [
        [5, 3, 0, 0, 7, 0, 0, 0, 0],
        [6, 0, 0, 1, 9, 5, 0, 0, 0],
        [0, 9, 8, 0, 0, 0, 0, 6, 0],
        [8, 0, 0, 0, 6, 0, 0, 0, 3],
        [4, 0, 0, 8, 0, 3, 0, 0, 1],
        [7, 0, 0, 0, 2, 0, 0, 0, 6],
        [0, 6, 0, 0, 0, 0, 2, 8, 0],
        [0, 0, 0, 4, 1, 9, 0, 0, 5],
        [0, 0, 0, 0, 8, 0, 0, 7, 9],
    ]
    result = solve_sudoku(board)
    assert result is not None
    # Verify all rows, cols, boxes have 1-9
    for r in range(9):
        assert sorted(result[r]) == list(range(1, 10))
    for c in range(9):
        assert sorted(result[r][c] for r in range(9)) == list(range(1, 10))
    print("Easy puzzle solved!")
    for row in result:
        print(row)


def test_hard():
    # "World's hardest Sudoku" (Arto Inkala)
    board = [
        [8, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 3, 6, 0, 0, 0, 0, 0],
        [0, 7, 0, 0, 9, 0, 2, 0, 0],
        [0, 5, 0, 0, 0, 7, 0, 0, 0],
        [0, 0, 0, 0, 4, 5, 7, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 3, 0],
        [0, 0, 1, 0, 0, 0, 0, 6, 8],
        [0, 0, 8, 5, 0, 0, 0, 1, 0],
        [0, 9, 0, 0, 0, 0, 4, 0, 0],
    ]
    result = solve_sudoku(board)
    assert result is not None
    print("Hard puzzle solved!")


if __name__ == "__main__":
    test_easy()
    print()
    test_hard()
    print("All Sudoku tests passed!")
```

### Constraint Propagation Techniques
1. **Naked singles:** If a cell has exactly one candidate, it must be that value.
2. **Hidden singles:** If a value can only go in one cell within a row/column/box, place it there.
3. **MRV heuristic:** When branching, choose the cell with fewest candidates — this fails faster on bad guesses.

### Complexity
- **Worst case:** O(9^(81)) without pruning. With constraint propagation, most easy/medium puzzles solve without any backtracking. Hard puzzles typically require only a few branch points.
- **Space:** O(81) = O(1) for the board state.
'''),

    ("thinking/algorithms", r'''Solve Word Search II (LeetCode 212): given a 2D board of characters and a list of words, find all words that can be formed by sequentially adjacent cells (horizontally or vertically). Each cell may only be used once per word. Use a Trie for efficient pruning.''', r'''<think>
Word Search II: find all words from a dictionary that exist as paths on a 2D grid.

Brute force would be: for each word, run a DFS from each cell. That is O(W * M * N * 4^L) where W = words, L = max word length. With W up to 30,000 and grids up to 12x12, this could be way too slow.

Could I search for all words simultaneously? Yes -- if I build a Trie from all words, then DFS from each cell using the Trie. Shared prefixes are explored only once, which is a huge win. For example, if I have "apple" and "application", the prefix "appl" is searched just once rather than twice.

But wait, I need to be careful about pruning. If I find the word "apple" at some point, I should remove it from the Trie to avoid finding it again from a different starting cell. Actually, I can just set word = None at the leaf to deduplicate, but should I also remove the Trie branch? Hmm, yes -- if a Trie node has no remaining children and no word, it is a dead end. Removing it prevents future DFS from exploring a path that cannot lead to any word. This progressive pruning is critical for performance.

I also considered using a hash set of prefixes instead of a Trie, but that would not support the progressive pruning trick. The Trie structure is essential here because it lets me incrementally remove branches as words are found.

One more thing: I must not revisit cells within a single word path. I will mark cells with '#' during DFS and restore them on backtrack. This is cleaner than maintaining a separate visited set since it avoids hash overhead.

Time: O(M * N * 4^L) worst case, but Trie pruning makes it dramatically faster in practice.
</think>

## Word Search II with Trie Pruning

```python
from typing import List, Set, Dict, Optional


class TrieNode:
    __slots__ = ['children', 'word']

    def __init__(self) -> None:
        self.children: Dict[str, 'TrieNode'] = {}
        self.word: Optional[str] = None  # Complete word ending here


def find_words(board: List[List[str]], words: List[str]) -> List[str]:
    """
    Find all dictionary words that can be traced on the board.

    Args:
        board: M x N grid of characters.
        words: List of words to search for.

    Returns:
        List of found words (no duplicates).

    Time:  O(M * N * 4^L) worst case, heavily pruned by Trie
    Space: O(W * L) for the Trie where W = number of words, L = max length
    """
    if not board or not board[0] or not words:
        return []

    # Build Trie
    root = TrieNode()
    for word in words:
        node = root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.word = word

    rows, cols = len(board), len(board[0])
    found: List[str] = []

    def dfs(r: int, c: int, parent: TrieNode) -> None:
        ch = board[r][c]
        node = parent.children.get(ch)
        if node is None:
            return

        # Check if we found a word
        if node.word is not None:
            found.append(node.word)
            node.word = None  # Avoid duplicates

        # Mark cell as visited
        board[r][c] = '#'

        # Explore 4 directions
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and board[nr][nc] != '#':
                if board[nr][nc] in node.children:
                    dfs(nr, nc, node)

        # Restore cell
        board[r][c] = ch

        # Pruning: if node has no children, remove it from parent
        if not node.children:
            del parent.children[ch]

    # Start DFS from every cell
    for r in range(rows):
        for c in range(cols):
            if board[r][c] in root.children:
                dfs(r, c, root)

    return found


# ---------- Tests ----------

def test_leetcode_example():
    board = [
        ['o', 'a', 'a', 'n'],
        ['e', 't', 'a', 'e'],
        ['i', 'h', 'k', 'r'],
        ['i', 'f', 'l', 'v'],
    ]
    words = ["oath", "pea", "eat", "rain"]
    result = set(find_words(board, words))
    assert result == {"oath", "eat"}, f"Expected {{'oath', 'eat'}}, got {result}"
    print(f"LeetCode example: {sorted(result)}")


def test_single_cell():
    board = [['a']]
    words = ["a", "b"]
    result = find_words(board, words)
    assert result == ["a"], f"Expected ['a'], got {result}"
    print(f"Single cell: {result}")


def test_no_matches():
    board = [['a', 'b'], ['c', 'd']]
    words = ["xyz", "pqr"]
    result = find_words(board, words)
    assert result == []
    print("No matches: correct")


def test_overlapping():
    board = [
        ['a', 'b'],
        ['c', 'd'],
    ]
    words = ["ab", "abc", "abcd", "abdc"]
    result = set(find_words(board, words))
    # ab: a(0,0)->b(0,1) ✓
    # abc: a->b->c? b is at (0,1), neighbors are a(0,0),d(1,1); no c adjacent to b...
    # Actually c is at (1,0). Not adjacent to b(0,1). So abc not found.
    # abdc: a->b->d->c ✓ (a(0,0)->b(0,1)->d(1,1)->c(1,0))
    assert "ab" in result
    assert "abdc" in result
    print(f"Overlapping: {sorted(result)}")


if __name__ == "__main__":
    test_leetcode_example()
    test_single_cell()
    test_no_matches()
    test_overlapping()
    print("All Word Search II tests passed!")
```

### Key Optimizations
1. **Trie-based DFS:** All words searched simultaneously — shared prefixes explored only once.
2. **Progressive pruning:** After finding a word or exhausting a branch, remove Trie nodes. This prevents re-exploring dead branches.
3. **Early termination:** If `board[r][c]` is not in the current Trie node's children, skip immediately.

### Complexity
- **Time:** O(M * N * 4^L) theoretical worst case, but Trie pruning reduces this dramatically. Each Trie node is visited at most once across all DFS calls.
- **Space:** O(W * L) for the Trie, O(L) for recursion depth.
'''),

    ("thinking/algorithms", r'''Implement a function to generate all valid combinations of N pairs of parentheses. Use backtracking with the constraint that at every point, the number of closing parentheses used must not exceed the number of opening ones.''', r'''<think>
Generate all valid parentheses -- a classic backtracking problem.

My first instinct is to generate all 2^(2n) binary strings and filter valid ones... but that is exponentially wasteful. Most strings would be invalid, and for n=10 we would generate over a million strings just to keep about 16,000.

A much better approach: build the string character by character with constraints that guarantee every generated string is valid. The key invariant is:
- At any point in the string, open_count >= close_count
- Total: open_count = close_count = n

So at each position:
- If open_count < n, we can add '('
- If close_count < open_count, we can add ')'
- When len(string) == 2*n, we have a valid combination

Wait, could there be a case where I get stuck -- where neither condition holds? Let me check: if open_count == n and close_count == open_count, then the string has length 2n and we are done. If open_count == n and close_count < open_count, then we can still add ')'. If open_count < n, we can always add '('. So no, we never get stuck. The algorithm naturally produces exactly the valid combinations without any dead ends. That is elegant -- this is a perfectly pruned backtracking where zero work is wasted.

The number of valid combinations is the Nth Catalan number: C(n) = C(2n, n) / (n+1). For n=3: ((())), (()()), (())(), ()(()), ()()() -- 5 combinations (C_3 = 5). Let me verify: C_3 = C(6,3)/4 = 20/4 = 5. Correct.

Time: O(4^n / sqrt(n)) since the Catalan number grows as 4^n / (n^(3/2) * sqrt(pi)), and generating each string takes O(n). This is optimal because we generate every valid string exactly once.
</think>

## Generate Valid Parentheses

The backtracking constraint is elegant: we can always add `(` if we haven't used all N, and we can add `)` only if it wouldn't exceed the count of `(`.

```python
from typing import List


def generate_parentheses(n: int) -> List[str]:
    """
    Generate all valid combinations of n pairs of parentheses.

    Args:
        n: Number of pairs.

    Returns:
        List of all valid parenthesis strings.

    Time:  O(4^n / sqrt(n)) — the nth Catalan number of results, each of length 2n
    Space: O(n) for recursion depth (excluding output)
    """
    result: List[str] = []
    path: List[str] = []

    def backtrack(open_count: int, close_count: int) -> None:
        if len(path) == 2 * n:
            result.append("".join(path))
            return

        if open_count < n:
            path.append('(')
            backtrack(open_count + 1, close_count)
            path.pop()

        if close_count < open_count:
            path.append(')')
            backtrack(open_count, close_count + 1)
            path.pop()

    backtrack(0, 0)
    return result


def generate_parentheses_iterative(n: int) -> List[str]:
    """Iterative BFS-style generation (alternative approach)."""
    if n == 0:
        return [""]

    # (current_string, open_count, close_count)
    stack: List[tuple] = [("", 0, 0)]
    result: List[str] = []

    while stack:
        s, op, cl = stack.pop()
        if len(s) == 2 * n:
            result.append(s)
            continue
        if cl < op:
            stack.append((s + ")", op, cl + 1))
        if op < n:
            stack.append((s + "(", op + 1, cl))

    return result


def is_valid(s: str) -> bool:
    """Verify a parenthesis string is valid."""
    count = 0
    for ch in s:
        if ch == '(':
            count += 1
        else:
            count -= 1
        if count < 0:
            return False
    return count == 0


# ---------- Tests ----------

def test_n3():
    result = generate_parentheses(3)
    expected = {"((()))", "(()())", "(())()", "()(())", "()()()"}
    assert set(result) == expected, f"Got {result}"
    assert len(result) == 5  # C_3 = 5
    print(f"n=3: {result}")


def test_n1():
    result = generate_parentheses(1)
    assert result == ["()"]
    print(f"n=1: {result}")


def test_n4():
    result = generate_parentheses(4)
    assert len(result) == 14  # C_4 = 14
    assert all(is_valid(s) for s in result)
    assert len(set(result)) == len(result)  # no duplicates
    print(f"n=4: {len(result)} combinations, all valid")


def test_catalan_numbers():
    # Catalan numbers: 1, 1, 2, 5, 14, 42, 132
    expected_counts = [1, 1, 2, 5, 14, 42, 132]
    for n, expected in enumerate(expected_counts):
        result = generate_parentheses(n)
        assert len(result) == expected, f"n={n}: expected {expected}, got {len(result)}"
    print("Catalan number verification passed for n=0..6")


if __name__ == "__main__":
    test_n3()
    test_n1()
    test_n4()
    test_catalan_numbers()
    print("All parentheses generation tests passed!")
```

### Why This is Perfectly Pruned
The two conditions (`open_count < n` and `close_count < open_count`) ensure:
1. We never place more than N opening parens
2. At every prefix, we have at least as many `(` as `)` — the defining property of valid prefixes
3. Every generated string is guaranteed valid — no wasted work

### Complexity
- **Time:** O(4^n / sqrt(n)) — this is the nth Catalan number C_n = C(2n,n)/(n+1), and each string has length 2n
- **Space:** O(n) recursion depth; O(C_n * n) for the output
- The Catalan number grows as 4^n / (n^(3/2) * sqrt(pi)), so this is asymptotically optimal
'''),

    ("thinking/algorithms", r'''Implement a Combination Sum solver with deduplication. Given a collection of candidate numbers (which may contain duplicates) and a target number, find all unique combinations that sum to the target. Each number may be used at most once. (LeetCode 40)''', r'''<think>
Combination Sum II: candidates may have duplicates, each used at most once, find all unique combinations summing to target.

The key challenge is avoiding duplicate combinations. For example, if candidates = [1, 1, 2] and target = 3, we should return [[1, 2]] only once, not twice (once for each '1').

My first thought was to use a set to track seen combinations... but that would require hashing lists (converting to tuples), and more importantly it would still generate all the duplicates before filtering them. That is wasteful.

A better strategy: prevent duplicates from being generated at all.
1. Sort the candidates -- this groups duplicates together
2. Backtrack with an index parameter (only consider candidates at index >= current)
3. Dedup: if candidates[i] == candidates[i-1] and i > start, skip candidates[i]

Wait, why does the condition i > start matter? Because at a given recursion level, we are choosing which value to branch on. The first occurrence of a value (at index start) includes all possible combinations using 1, 2, ..., k copies of that value. If we also branched on the second occurrence, we would re-explore a subset of those same combinations. So we skip it. But if i == start, this is the first element we are considering at this level and we must include it.

Hmm, let me trace through an example to make sure. candidates = [1, 1, 2], target = 3.
- Sorted: [1, 1, 2]. Start backtrack at index 0.
- i=0: pick 1, recurse with start=1, remaining=2.
  - i=1: pick 1, recurse with start=2, remaining=1.
    - i=2: pick 2 > remaining 1, break. Dead end.
  - i=2: pick 2, recurse with start=3, remaining=0. Found [1, 2]!
- i=1: candidates[1]==candidates[0] and i > 0, so SKIP. This prevents the duplicate.
- i=2: pick 2, remaining=1, no further options. Dead end.
Result: [[1, 2]]. Correct -- no duplicates.

Additional pruning: if current candidate > remaining target, break immediately since the array is sorted and all subsequent values are even larger.

Time: O(2^N) in the worst case (power set), but pruning makes it much faster in practice.
</think>

## Combination Sum with Deduplication

```python
from typing import List


def combination_sum2(candidates: List[int], target: int) -> List[List[int]]:
    """
    Find all unique combinations in candidates that sum to target.
    Each number used at most once. Input may contain duplicates.

    Args:
        candidates: List of candidate numbers (may have duplicates).
        target: Target sum.

    Returns:
        List of unique combinations (sorted).

    Time:  O(2^N) worst case, pruned significantly in practice
    Space: O(N) for recursion depth
    """
    candidates.sort()
    result: List[List[int]] = []
    path: List[int] = []

    def backtrack(start: int, remaining: int) -> None:
        if remaining == 0:
            result.append(path[:])
            return

        for i in range(start, len(candidates)):
            val = candidates[i]

            # Pruning: if this value exceeds remaining, all subsequent will too
            if val > remaining:
                break

            # Deduplication: skip duplicate values at the same recursion level
            if i > start and candidates[i] == candidates[i - 1]:
                continue

            path.append(val)
            backtrack(i + 1, remaining - val)
            path.pop()

    backtrack(0, target)
    return result


def combination_sum_unlimited(candidates: List[int], target: int) -> List[List[int]]:
    """
    Variant: each candidate can be used unlimited times (LeetCode 39).
    """
    candidates = sorted(set(candidates))  # Dedup input
    result: List[List[int]] = []
    path: List[int] = []

    def backtrack(start: int, remaining: int) -> None:
        if remaining == 0:
            result.append(path[:])
            return

        for i in range(start, len(candidates)):
            if candidates[i] > remaining:
                break
            path.append(candidates[i])
            backtrack(i, remaining - candidates[i])  # i, not i+1
            path.pop()

    backtrack(0, target)
    return result


# ---------- Tests ----------

def test_leetcode_example():
    result = combination_sum2([10, 1, 2, 7, 6, 1, 5], 8)
    expected = [[1, 1, 6], [1, 2, 5], [1, 7], [2, 6]]
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"Example: {result}")


def test_no_solution():
    result = combination_sum2([2, 4, 6], 1)
    assert result == []
    print("No solution: correct")


def test_all_same():
    result = combination_sum2([1, 1, 1, 1, 1], 3)
    # Only one combination: [1, 1, 1]
    assert result == [[1, 1, 1]], f"Got {result}"
    print(f"All same: {result}")


def test_single_element():
    result = combination_sum2([5], 5)
    assert result == [[5]]
    result = combination_sum2([5], 3)
    assert result == []
    print("Single element tests passed")


def test_unlimited_variant():
    result = combination_sum_unlimited([2, 3, 6, 7], 7)
    expected = [[2, 2, 3], [7]]
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"Unlimited variant: {result}")


if __name__ == "__main__":
    test_leetcode_example()
    test_no_solution()
    test_all_same()
    test_single_element()
    test_unlimited_variant()
    print("All combination sum tests passed!")
```

### Deduplication Logic
After sorting, duplicates are adjacent. The condition `i > start and candidates[i] == candidates[i-1]` means: "at this recursion level, we already explored a branch starting with this value — skip it." This is correct because:
- The first occurrence includes all combinations using 1, 2, ..., k copies of this value
- Later occurrences would only produce subsets of those combinations

### Pruning Techniques
1. **Sort + early termination:** Once `candidates[i] > remaining`, break the loop — all subsequent values are even larger.
2. **Duplicate skipping:** Prevents exploring equivalent branches.
3. **Combined effect:** Reduces the search space from O(2^N) to often near-linear for typical inputs.

### Complexity
- **Time:** O(2^N) worst case (every subset is valid), but pruning makes typical cases much faster.
- **Space:** O(N) for the recursion stack and current path. O(C * K) for output where C = number of combinations, K = average combination length.
'''),
]
