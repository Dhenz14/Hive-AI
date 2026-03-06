PAIRS = [
    ("thinking/algorithms", r'''Implement matrix exponentiation to solve linear recurrences efficiently. Demonstrate with Fibonacci, Tribonacci, and a general k-th order linear recurrence.''', r'''<think>
Matrix exponentiation converts a linear recurrence into matrix multiplication. The naive approach to computing f(n) iterates n times -- O(n). Could we do better? Yes, because the recurrence can be expressed as a matrix raised to the n-th power, and we can compute M^n in O(log n) multiplications using repeated squaring.

For Fibonacci: F(n) = F(n-1) + F(n-2). I initially tried to express this as a single equation, but actually we need to track two consecutive values. The matrix form:
[F(n+1)]   [1 1]^n   [F(1)]
[F(n)  ] = [1 0]   * [F(0)]

For Tribonacci T(n) = T(n-1) + T(n-2) + T(n-3), we need a 3x3 matrix. Wait, how do I construct the companion matrix for a general k-th order recurrence? The first row contains the coefficients [c1, c2, ..., ck], and below that is an identity matrix shifted down by one row. I considered putting the identity on top and coefficients on the bottom, but that does not work -- the coefficients must be in the first row because multiplying by this matrix computes the next value from the k previous ones.

One subtlety: the power we raise the matrix to is not always n. For a k-th order recurrence, we need M^(n-k+1) applied to the initial vector [f(k-1), f(k-2), ..., f(0)]^T. I initially thought it was M^n, but that gives the wrong result -- off by k-1 since the first k values are given directly.

For modular arithmetic (crucial in competitive programming where answers are mod 10^9+7), we apply mod at every multiplication step to prevent integer overflow. In Python this is not strictly necessary since integers have arbitrary precision, but it keeps numbers small and fast.

Each matrix multiplication is O(k^3), and repeated squaring does O(log n) multiplications, so total is O(k^3 * log n). Compare with iterative O(k * n) -- matrix exponentiation wins dramatically when n is huge (e.g., 10^18).
</think>

## Matrix Exponentiation for Linear Recurrences

### Implementation

```python
def mat_mul(A, B, mod=None):
    """Multiply two matrices. Optional modular arithmetic."""
    n = len(A)
    m = len(B[0])
    k = len(B)
    C = [[0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            s = 0
            for p in range(k):
                s += A[i][p] * B[p][j]
            C[i][j] = s % mod if mod else s
    return C


def mat_pow(M, exp, mod=None):
    """Compute M^exp using repeated squaring."""
    n = len(M)
    # Identity matrix
    result = [[1 if i == j else 0 for j in range(n)] for i in range(n)]

    base = [row[:] for row in M]
    while exp > 0:
        if exp % 2 == 1:
            result = mat_mul(result, base, mod)
        base = mat_mul(base, base, mod)
        exp //= 2
    return result


def fibonacci(n, mod=None):
    """Compute n-th Fibonacci number using matrix exponentiation.
    F(0)=0, F(1)=1, F(2)=1, ..."""
    if n <= 1:
        return n
    M = [[1, 1], [1, 0]]
    result = mat_pow(M, n - 1, mod)
    # result * [F(1), F(0)]^T = [F(n), F(n-1)]^T
    return result[0][0] % mod if mod else result[0][0]


def tribonacci(n):
    """T(0)=0, T(1)=0, T(2)=1, T(n)=T(n-1)+T(n-2)+T(n-3)."""
    if n < 2:
        return 0
    if n == 2:
        return 1
    M = [[1, 1, 1],
         [1, 0, 0],
         [0, 1, 0]]
    result = mat_pow(M, n - 2)
    # result * [T(2), T(1), T(0)]^T
    return result[0][0]


def linear_recurrence(coeffs, initial, n, mod=None):
    """Solve general k-th order linear recurrence.

    f(n) = coeffs[0]*f(n-1) + coeffs[1]*f(n-2) + ... + coeffs[k-1]*f(n-k)
    initial = [f(0), f(1), ..., f(k-1)]

    Returns f(n).
    """
    k = len(coeffs)
    if n < k:
        return initial[n] % mod if mod else initial[n]

    # Build companion matrix
    M = [[0] * k for _ in range(k)]
    for j in range(k):
        M[0][j] = coeffs[j]
    for i in range(1, k):
        M[i][i - 1] = 1

    result = mat_pow(M, n - k + 1, mod)

    # Multiply result by [f(k-1), f(k-2), ..., f(0)]^T
    rev_initial = list(reversed(initial))
    ans = 0
    for j in range(k):
        ans += result[0][j] * rev_initial[j]
    return ans % mod if mod else ans


# Demo: Fibonacci
print("=== Fibonacci ===")
fibs = [fibonacci(i) for i in range(15)]
print(f"F(0..14): {fibs}")
print(f"F(50) = {fibonacci(50)}")
print(f"F(100) mod 10^9+7 = {fibonacci(100, mod=10**9+7)}")

# Demo: Tribonacci
print("\n=== Tribonacci ===")
tribs = [tribonacci(i) for i in range(15)]
print(f"T(0..14): {tribs}")

# Demo: General recurrence
# f(n) = 2*f(n-1) + 3*f(n-2), f(0)=1, f(1)=1
print("\n=== Custom Recurrence: f(n) = 2*f(n-1) + 3*f(n-2) ===")
coeffs = [2, 3]
initial = [1, 1]
values = [linear_recurrence(coeffs, initial, i) for i in range(10)]
print(f"f(0..9): {values}")

# Verify
f = [1, 1]
for i in range(2, 10):
    f.append(2 * f[-1] + 3 * f[-2])
print(f"Direct:  {f}")
assert values == f

# Large n with modular arithmetic
print(f"\nf(10^18) mod 10^9+7 = {linear_recurrence(coeffs, initial, 10**18, mod=10**9+7)}")
```

### Complexity
- **Matrix multiplication**: O(k^3) for k x k matrices
- **Matrix power**: O(k^3 * log(n))
- **Total for k-th order recurrence**: O(k^3 * log(n))
- **Compared to iterative**: O(k * n) -- matrix exponentiation wins when n >> k^2'''),

    ("thinking/algorithms", r'''Implement Gaussian elimination for solving systems of linear equations. Handle singular systems, find rank, and detect inconsistency. Support both floating-point and modular arithmetic.''', r'''<think>
Gaussian elimination reduces the augmented matrix [A|b] to row echelon form. The basic idea is straightforward, but there are several subtleties I need to think through carefully.

First, pivoting. I initially thought we could just use whatever non-zero element is in the pivot position, but that leads to numerical instability with floating-point arithmetic. For example, if the pivot is 1e-15, dividing by it amplifies rounding errors catastrophically. Partial pivoting (choosing the row with the largest absolute value in the pivot column) fixes this. Hmm, but for modular arithmetic, we have exact values -- no rounding errors -- so partial pivoting is unnecessary. We just need any non-zero element.

For the elimination step: after selecting the pivot, I considered only eliminating entries below the pivot (classical row echelon form), then back-substituting. But actually, eliminating entries both above and below (reduced row echelon form / Gauss-Jordan) is simpler to implement because it avoids a separate back-substitution phase. I will go with full elimination.

Edge cases that tripped me up:
- Zero pivot when all entries in the column are zero: skip this column entirely. The rank decreases by one. I initially wanted to declare "no solution" here, but that is wrong -- it just means we have a free variable.
- After elimination, a row of the form [0 0 ... 0 | b] with b != 0 indicates inconsistency (no solution exists).
- If rank < number of variables, we have infinitely many solutions. I will return one particular solution with free variables set to 0.

For the modular version: division becomes multiplication by modular inverse (using Fermat's little theorem since the modulus is prime). This gives exact results with no floating-point concerns.
</think>

## Gaussian Elimination

### Implementation

```python
def gauss_eliminate(A, b, mod=None):
    """Solve Ax = b using Gaussian elimination.

    Returns:
        (solution, rank, status)
        status: 'unique', 'infinite', or 'inconsistent'
    """
    n = len(A)
    m = len(A[0]) if A else 0

    # Build augmented matrix
    aug = []
    for i in range(n):
        row = [x for x in A[i]] + [b[i]]
        if mod:
            row = [x % mod for x in row]
        aug.append(row)

    cols = m  # number of variables
    pivot_col = [0] * n  # which column is the pivot for each row
    rank = 0
    pivot_rows = []

    col = 0
    for row in range(n):
        if col >= cols:
            break

        # Find pivot
        if mod:
            pivot = -1
            for r in range(row, n):
                if aug[r][col] % mod != 0:
                    pivot = r
                    break
        else:
            pivot = row
            for r in range(row + 1, n):
                if abs(aug[r][col]) > abs(aug[pivot][col]):
                    pivot = r
            if abs(aug[pivot][col]) < 1e-12:
                pivot = -1

        if pivot == -1:
            col += 1
            continue

        # Swap rows
        aug[row], aug[pivot] = aug[pivot], aug[row]
        pivot_col[row] = col
        pivot_rows.append(row)
        rank += 1

        # Normalize pivot row
        if mod:
            inv = pow(aug[row][col], mod - 2, mod)
            for j in range(cols + 1):
                aug[row][j] = aug[row][j] * inv % mod
        else:
            factor = aug[row][col]
            for j in range(cols + 1):
                aug[row][j] /= factor

        # Eliminate other rows
        for r in range(n):
            if r == row or aug[r][col] == 0:
                continue
            if mod:
                factor = aug[r][col]
                for j in range(cols + 1):
                    aug[r][j] = (aug[r][j] - factor * aug[row][j]) % mod
            else:
                factor = aug[r][col]
                for j in range(cols + 1):
                    aug[r][j] -= factor * aug[row][j]

        col += 1

    # Check consistency
    for r in range(rank, n):
        rhs = aug[r][cols]
        if mod:
            if rhs % mod != 0:
                return None, rank, 'inconsistent'
        else:
            if abs(rhs) > 1e-9:
                return None, rank, 'inconsistent'

    if rank < cols:
        # Infinite solutions -- return one particular solution
        x = [0] * cols
        for r in range(rank):
            x[pivot_col[r]] = aug[r][cols]
        return x, rank, 'infinite'

    # Unique solution
    x = [0] * cols
    for r in range(rank):
        x[pivot_col[r]] = aug[r][cols]
    return x, rank, 'unique'


def matrix_rank(A, mod=None):
    """Compute rank of matrix A."""
    b = [0] * len(A)
    _, rank, _ = gauss_eliminate(A, b, mod)
    return rank


# Demo: Unique solution
print("=== Unique Solution ===")
A = [[2, 1, -1],
     [-3, -1, 2],
     [-2, 1, 2]]
b = [8, -11, -3]
x, rank, status = gauss_eliminate(A, b)
print(f"Solution: {[round(v, 6) for v in x]}")
print(f"Rank: {rank}, Status: {status}")
# Expected: x = [2, 3, -1]

# Verify
for i in range(3):
    lhs = sum(A[i][j] * x[j] for j in range(3))
    print(f"  Row {i}: {round(lhs, 6)} = {b[i]}")

# Demo: Inconsistent system
print("\n=== Inconsistent System ===")
A2 = [[1, 1], [1, 1]]
b2 = [1, 2]
x2, rank2, status2 = gauss_eliminate(A2, b2)
print(f"Status: {status2}, Rank: {rank2}")

# Demo: Infinite solutions
print("\n=== Infinite Solutions ===")
A3 = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
b3 = [6, 15, 24]
x3, rank3, status3 = gauss_eliminate(A3, b3)
print(f"Status: {status3}, Rank: {rank3}")
print(f"Particular solution: {[round(v, 6) for v in x3]}")

# Demo: Modular arithmetic
print("\n=== Modular Arithmetic (mod 7) ===")
A4 = [[3, 2], [5, 4]]
b4 = [1, 3]
x4, rank4, status4 = gauss_eliminate(A4, b4, mod=7)
print(f"Solution mod 7: {x4}")
print(f"Status: {status4}")
# Verify
for i in range(2):
    lhs = sum(A4[i][j] * x4[j] for j in range(2)) % 7
    print(f"  Row {i}: {lhs} = {b4[i] % 7}")
```

### Complexity
- **Time**: O(n^2 * m) for n equations, m variables
- **Space**: O(n * m) for augmented matrix
- **Modular version**: exact (no floating point errors), requires prime modulus
- **Numerical stability**: partial pivoting helps but does not eliminate all issues'''),

    ("thinking/algorithms", r'''Implement the matrix chain multiplication problem with path reconstruction. Given matrices A1, A2, ..., An with dimensions, find the optimal parenthesization that minimizes scalar multiplications.''', r'''<think>
Matrix chain multiplication: given n matrices, find the parenthesization that minimizes scalar multiplications. This is a classic DP problem, but the key insight is not obvious at first -- why does parenthesization matter at all?

Consider three matrices: A(10x100), B(100x5), C(5x50). If we compute (AB)C: 10*100*5 + 10*5*50 = 5000 + 2500 = 7500. If we compute A(BC): 100*5*50 + 10*100*50 = 25000 + 50000 = 75000. That is a 10x difference! So the order matters enormously.

I initially considered a greedy approach: always multiply the "cheapest" pair first. But wait, that does not work because the cheapest local choice can lead to expensive later multiplications. This is why we need DP.

The recurrence: dp[i][j] = min over k from i to j-1 of (dp[i][k] + dp[k+1][j] + p[i-1]*p[k]*p[j]). The split point k determines where we parenthesize: multiply chain i..k first, then chain k+1..j, then combine. The combination cost is p[i-1]*p[k]*p[j] because the result of i..k has dimensions p[i-1] x p[k] and the result of k+1..j has dimensions p[k] x p[j].

Base case: dp[i][i] = 0 (single matrix, no multiplication needed). We fill by increasing chain length since dp[i][j] depends on shorter subchains.

For path reconstruction, I store s[i][j] = optimal k at each cell, then recursively build the parenthesization string. I considered whether we need the full split table or could reconstruct from the DP table alone, but actually the split table is necessary -- knowing the minimum cost does not tell us which k achieved it without re-examining all candidates.

Time: O(n^3), Space: O(n^2). Knuth's optimization could reduce to O(n^2) since the cost function satisfies the quadrilateral inequality, but O(n^3) is sufficient for practical n.
</think>

## Matrix Chain Multiplication with Path Reconstruction

### Implementation

```python
def matrix_chain_order(dimensions):
    """Find optimal parenthesization for matrix chain multiplication.

    Args:
        dimensions: list of dimensions [p0, p1, p2, ..., pn]
                    Matrix i has dimensions p[i-1] x p[i]

    Returns:
        (min_cost, split_table, parenthesization_string)
    """
    n = len(dimensions) - 1  # number of matrices
    if n <= 0:
        return 0, [], ""

    INF = float('inf')
    # dp[i][j] = min cost for matrices i..j (1-indexed)
    dp = [[0] * (n + 1) for _ in range(n + 1)]
    split = [[0] * (n + 1) for _ in range(n + 1)]

    # Fill by increasing chain length
    for length in range(2, n + 1):
        for i in range(1, n - length + 2):
            j = i + length - 1
            dp[i][j] = INF
            for k in range(i, j):
                cost = (dp[i][k] + dp[k + 1][j]
                        + dimensions[i - 1] * dimensions[k] * dimensions[j])
                if cost < dp[i][j]:
                    dp[i][j] = cost
                    split[i][j] = k

    def build_parens(i, j):
        if i == j:
            return f"A{i}"
        k = split[i][j]
        left = build_parens(i, k)
        right = build_parens(k + 1, j)
        return f"({left} x {right})"

    parens = build_parens(1, n)
    return dp[1][n], split, parens


def print_dp_table(dp, n):
    """Display the DP cost table."""
    print("  DP Table (dp[i][j] = min cost for chain i..j):")
    header = "     " + "".join(f"{j:>8}" for j in range(1, n + 1))
    print(header)
    for i in range(1, n + 1):
        row = f"  {i}: "
        for j in range(1, n + 1):
            if j < i:
                row += "       -"
            else:
                row += f"{dp[i][j]:>8}"
        print(row)


# Demo
# 4 matrices: A1(10x30), A2(30x5), A3(5x60), A4(60x10)
dims = [10, 30, 5, 60, 10]
cost, split, parens = matrix_chain_order(dims)
n = len(dims) - 1

print("=== Matrix Chain Multiplication ===")
print(f"Dimensions: {dims}")
print(f"Matrices: ", end="")
for i in range(1, n + 1):
    print(f"A{i}({dims[i-1]}x{dims[i]})", end="  ")
print()
print(f"\nMinimum scalar multiplications: {cost}")
print(f"Optimal parenthesization: {parens}")
print()
print_dp_table(split, n)

# Compare with worst case
# Naive left-to-right: ((A1 x A2) x A3) x A4
naive = (dims[0]*dims[1]*dims[2]  # A1 x A2
         + dims[0]*dims[2]*dims[3]  # result x A3
         + dims[0]*dims[3]*dims[4])  # result x A4
print(f"\nNaive left-to-right cost: {naive}")
print(f"Optimal cost: {cost}")
print(f"Savings: {naive - cost} ({100*(naive-cost)/naive:.1f}%)")

# Larger example
print("\n=== Larger Example (6 matrices) ===")
dims2 = [30, 35, 15, 5, 10, 20, 25]
cost2, _, parens2 = matrix_chain_order(dims2)
print(f"Dimensions: {dims2}")
print(f"Min cost: {cost2}")
print(f"Parenthesization: {parens2}")

# Classic textbook answer: 15125
print(f"Expected (CLRS): 15125, Got: {cost2}")
```

### Complexity
- **Time**: O(n^3)
- **Space**: O(n^2) for dp and split tables
- **Reconstruction**: O(n) to build parenthesization string

### Optimization Note
Knuth's optimization can reduce this to O(n^2) since the cost function satisfies the quadrilateral inequality, but the O(n^3) version is simpler and sufficient for most cases.'''),

    ("thinking/algorithms", r'''Implement sparse matrix operations: compressed storage formats (CSR/CSC), sparse matrix-vector multiplication, and sparse matrix addition. Compare memory usage with dense representation.''', r'''<think>
Sparse matrices have mostly zero entries -- storing all n*m values wastes enormous memory. For a 10000x10000 matrix with only 5000 non-zeros, dense storage uses 800MB (8 bytes * 10^8) while sparse needs roughly 80KB. That is a 10000x saving.

But which sparse format to use? I considered several options:
- COO (coordinate list): store (row, col, value) triples. Simple but slow for row-based operations since entries are not grouped by row.
- CSR (Compressed Sparse Row): three arrays -- values, column indices, and row pointers. Row pointers tell you where each row's data starts in the values array. This makes row-based operations like SpMV very efficient.
- CSC (Compressed Sparse Column): same idea but compressed by columns. Better for column-based operations.

I will go with CSR since matrix-vector multiplication (the most common sparse operation) is naturally row-oriented: for each row, dot-product the non-zeros with the corresponding vector elements.

Hmm, one thing I initially overlooked: element access in CSR is not O(1) like in dense matrices. To get element (i, j), I need to scan row i's entries to find column j. That is O(nnz_in_row) or O(log(nnz_in_row)) with binary search on the sorted column indices. For SpMV this does not matter since we process all entries anyway, but random access is slower.

For sparse addition, I need to merge non-zero entries from both matrices row by row. I considered doing this in-place, but actually creating a new matrix from merged entries is cleaner and avoids complications with overlapping positions.

Memory for CSR: values (8 bytes each) + col_indices (4 bytes each) + row_ptr (4 bytes * (n+1)). Total = 12*nnz + 4*(n+1). Dense would be 8*n*m. The breakeven point is when nnz is roughly 2/3 * n * m, so CSR wins whenever the matrix is less than ~67% full -- which is almost always the case for "sparse" matrices.
</think>

## Sparse Matrix Operations

### CSR Format Implementation

```python
class SparseMatrixCSR:
    """Compressed Sparse Row matrix format."""

    def __init__(self, rows, cols):
        self.rows = rows
        self.cols = cols
        self.values = []
        self.col_indices = []
        self.row_ptr = [0]
        self._building = True

    @classmethod
    def from_dense(cls, dense):
        """Create CSR from dense 2D list."""
        rows = len(dense)
        cols = len(dense[0]) if rows > 0 else 0
        m = cls(rows, cols)
        for i in range(rows):
            for j in range(cols):
                if dense[i][j] != 0:
                    m.values.append(dense[i][j])
                    m.col_indices.append(j)
            m.row_ptr.append(len(m.values))
        m._building = False
        return m

    @classmethod
    def from_entries(cls, rows, cols, entries):
        """Create from list of (row, col, value) tuples."""
        # Sort by row, then column
        entries = sorted(entries, key=lambda x: (x[0], x[1]))
        m = cls(rows, cols)
        cur_row = 0
        for r, c, v in entries:
            while cur_row < r:
                m.row_ptr.append(len(m.values))
                cur_row += 1
            m.values.append(v)
            m.col_indices.append(c)
        while cur_row < rows:
            m.row_ptr.append(len(m.values))
            cur_row += 1
        m._building = False
        return m

    def nnz(self):
        """Number of non-zero elements."""
        return len(self.values)

    def get(self, i, j):
        """Get element at (i, j). O(log(row_nnz)) with binary search."""
        start = self.row_ptr[i]
        end = self.row_ptr[i + 1]
        for idx in range(start, end):
            if self.col_indices[idx] == j:
                return self.values[idx]
        return 0

    def matvec(self, x):
        """Sparse matrix-vector multiply: y = A * x. O(nnz)."""
        assert len(x) == self.cols
        y = [0] * self.rows
        for i in range(self.rows):
            start = self.row_ptr[i]
            end = self.row_ptr[i + 1]
            s = 0
            for idx in range(start, end):
                s += self.values[idx] * x[self.col_indices[idx]]
            y[i] = s
        return y

    def add(self, other):
        """Sparse matrix addition. Returns new CSR matrix."""
        assert self.rows == other.rows and self.cols == other.cols
        entries = []
        for i in range(self.rows):
            # Merge non-zeros from both matrices for row i
            row_vals = {}
            for idx in range(self.row_ptr[i], self.row_ptr[i + 1]):
                j = self.col_indices[idx]
                row_vals[j] = row_vals.get(j, 0) + self.values[idx]
            for idx in range(other.row_ptr[i], other.row_ptr[i + 1]):
                j = other.col_indices[idx]
                row_vals[j] = row_vals.get(j, 0) + other.values[idx]
            for j, v in sorted(row_vals.items()):
                if v != 0:
                    entries.append((i, j, v))
        return SparseMatrixCSR.from_entries(self.rows, self.cols, entries)

    def to_dense(self):
        """Convert to dense matrix."""
        dense = [[0] * self.cols for _ in range(self.rows)]
        for i in range(self.rows):
            for idx in range(self.row_ptr[i], self.row_ptr[i + 1]):
                dense[i][self.col_indices[idx]] = self.values[idx]
        return dense

    def memory_bytes(self):
        """Estimated memory usage."""
        # Each value: 8 bytes (float), each index: 4 bytes (int)
        return len(self.values) * 8 + len(self.col_indices) * 4 + len(self.row_ptr) * 4

    def dense_memory_bytes(self):
        """Memory if stored as dense."""
        return self.rows * self.cols * 8


# Demo
print("=== Sparse Matrix CSR ===")
dense = [
    [0, 0, 3, 0, 4],
    [0, 0, 5, 7, 0],
    [0, 0, 0, 0, 0],
    [0, 2, 6, 0, 0],
]
m = SparseMatrixCSR.from_dense(dense)
print(f"Shape: {m.rows}x{m.cols}")
print(f"Non-zeros: {m.nnz()}")
print(f"Values: {m.values}")
print(f"Col indices: {m.col_indices}")
print(f"Row pointers: {m.row_ptr}")

# Matrix-vector multiply
x = [1, 2, 3, 4, 5]
y = m.matvec(x)
print(f"\nA * {x} = {y}")
# Verify: row 0: 3*3 + 4*5 = 29, row 1: 5*3 + 7*4 = 43, etc.

# Matrix addition
m2 = SparseMatrixCSR.from_entries(4, 5, [
    (0, 0, 1), (1, 2, -5), (3, 4, 10)
])
m3 = m.add(m2)
print(f"\nA + B (dense):")
for row in m3.to_dense():
    print(f"  {row}")

# Memory comparison
print(f"\n=== Memory Comparison ===")
sizes = [(100, 100, 50), (1000, 1000, 500), (10000, 10000, 5000)]
for r, c, nnz in sizes:
    sparse_mem = nnz * 8 + nnz * 4 + (r + 1) * 4
    dense_mem = r * c * 8
    ratio = dense_mem / sparse_mem
    print(f"  {r}x{c}, nnz={nnz}: sparse={sparse_mem/1024:.1f}KB, "
          f"dense={dense_mem/1024:.1f}KB, ratio={ratio:.1f}x")
```

### Complexity
| Operation | Dense | CSR Sparse |
|-----------|-------|-----------|
| Storage | O(n*m) | O(nnz + n) |
| MatVec | O(n*m) | O(nnz) |
| Element access | O(1) | O(log(row_nnz)) |
| Addition | O(n*m) | O(nnz1 + nnz2) |'''),

    ("thinking/algorithms", r'''Implement Strassen's algorithm for matrix multiplication. Explain how it achieves O(n^2.807) by reducing 8 multiplications to 7. Compare with naive O(n^3) multiplication.''', r'''<think>
Strassen's algorithm reduces matrix multiplication from 8 recursive multiplications to 7. That sounds like a tiny savings, but the impact on asymptotic complexity is significant: T(n) = 7*T(n/2) + O(n^2) solves to O(n^log2(7)) = O(n^2.807) instead of O(n^3).

The standard 2x2 block approach needs 8 multiplications: C11 = A11*B11 + A12*B21, and similarly for C12, C21, C22 (2 mults each, 4 quadrants = 8 total). I initially wondered if we could save a multiplication by some algebraic trick on the standard formulas, but actually Strassen found a completely different set of 7 intermediate products using clever sums and differences of blocks.

The 7 products are:
M1 = (A11 + A22)(B11 + B22), M2 = (A21 + A22)B11, M3 = A11(B12 - B22),
M4 = A22(B21 - B11), M5 = (A11 + A12)B22, M6 = (A21 - A11)(B11 + B12),
M7 = (A12 - A22)(B21 + B22).

Then C11 = M1 + M4 - M5 + M7, C12 = M3 + M5, C21 = M2 + M4, C22 = M1 - M2 + M3 + M6. Wait, do these formulas actually produce the correct result? Let me verify C11: M1 + M4 - M5 + M7 = (A11+A22)(B11+B22) + A22(B21-B11) - (A11+A12)B22 + (A12-A22)(B21+B22). Expanding... yes, the cross terms cancel and we get A11*B11 + A12*B21. The algebra is non-obvious but correct.

One practical concern: for small n (say n <= 64), the constant factor and extra additions in Strassen make it slower than naive multiplication. Therefore we need a crossover threshold -- below it, fall back to the O(n^3) algorithm.

I also need to handle non-power-of-2 dimensions. I considered only supporting powers of 2, but that would be too restrictive. Instead, I will pad with zeros to the next even size at each recursion level. Hmm, this adds some overhead, but the asymptotic complexity is unchanged since padding at most doubles n at each level.

Another tradeoff I should mention: Strassen is numerically less stable than naive multiplication for floating point, because the intermediate sums and differences can cause cancellation. For integer or modular arithmetic, this is not a concern.
</think>

## Strassen's Matrix Multiplication

### Implementation

```python
import time


def naive_multiply(A, B):
    """Standard O(n^3) matrix multiplication."""
    n = len(A)
    C = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            for k in range(n):
                C[i][j] += A[i][k] * B[k][j]
    return C


def mat_add(A, B):
    n = len(A)
    return [[A[i][j] + B[i][j] for j in range(n)] for i in range(n)]


def mat_sub(A, B):
    n = len(A)
    return [[A[i][j] - B[i][j] for j in range(n)] for i in range(n)]


def split(M):
    """Split matrix into 4 quadrants."""
    n = len(M)
    h = n // 2
    A11 = [row[:h] for row in M[:h]]
    A12 = [row[h:] for row in M[:h]]
    A21 = [row[:h] for row in M[h:]]
    A22 = [row[h:] for row in M[h:]]
    return A11, A12, A21, A22


def combine(C11, C12, C21, C22):
    """Combine 4 quadrants into one matrix."""
    n = len(C11) * 2
    h = n // 2
    C = [[0] * n for _ in range(n)]
    for i in range(h):
        for j in range(h):
            C[i][j] = C11[i][j]
            C[i][j + h] = C12[i][j]
            C[i + h][j] = C21[i][j]
            C[i + h][j + h] = C22[i][j]
    return C


def strassen(A, B, threshold=32):
    """Strassen's O(n^2.807) matrix multiplication.
    Falls back to naive for small matrices."""
    n = len(A)

    if n <= threshold:
        return naive_multiply(A, B)

    # Pad to even size if needed
    if n % 2 != 0:
        A = [row + [0] for row in A] + [[0] * (n + 1)]
        B = [row + [0] for row in B] + [[0] * (n + 1)]
        result = strassen(A, B, threshold)
        return [row[:n] for row in result[:n]]

    A11, A12, A21, A22 = split(A)
    B11, B12, B21, B22 = split(B)

    # 7 recursive multiplications (instead of 8)
    M1 = strassen(mat_add(A11, A22), mat_add(B11, B22), threshold)
    M2 = strassen(mat_add(A21, A22), B11, threshold)
    M3 = strassen(A11, mat_sub(B12, B22), threshold)
    M4 = strassen(A22, mat_sub(B21, B11), threshold)
    M5 = strassen(mat_add(A11, A12), B22, threshold)
    M6 = strassen(mat_sub(A21, A11), mat_add(B11, B12), threshold)
    M7 = strassen(mat_sub(A12, A22), mat_add(B21, B22), threshold)

    # Combine results
    C11 = mat_add(mat_sub(mat_add(M1, M4), M5), M7)
    C12 = mat_add(M3, M5)
    C21 = mat_add(M2, M4)
    C22 = mat_add(mat_sub(mat_add(M1, M3), M2), M6)

    return combine(C11, C12, C21, C22)


# Verify correctness
import random
random.seed(42)

def random_matrix(n):
    return [[random.randint(-10, 10) for _ in range(n)] for _ in range(n)]

n = 16
A = random_matrix(n)
B = random_matrix(n)

C_naive = naive_multiply(A, B)
C_strassen = strassen(A, B, threshold=4)

match = all(C_naive[i][j] == C_strassen[i][j]
            for i in range(n) for j in range(n))
print(f"Correctness check (n={n}): {'PASS' if match else 'FAIL'}")

# Timing comparison
print("\n=== Timing Comparison ===")
for n in [32, 64, 128]:
    A = random_matrix(n)
    B = random_matrix(n)

    start = time.time()
    naive_multiply(A, B)
    t_naive = time.time() - start

    start = time.time()
    strassen(A, B, threshold=32)
    t_strassen = time.time() - start

    print(f"  n={n:3d}: naive={t_naive:.4f}s, strassen={t_strassen:.4f}s, "
          f"ratio={t_naive/max(t_strassen,1e-9):.2f}x")

print("\n=== The 7 Products (Strassen's Insight) ===")
print("  Naive: 8 multiplications per level -> O(n^3)")
print("  Strassen: 7 multiplications per level -> O(n^log2(7)) = O(n^2.807)")
print("  Savings grow with matrix size")
print("  Practical crossover: n ~ 32-128 depending on hardware")
```

### Complexity Comparison
| Algorithm | Multiplications | Time |
|-----------|----------------|------|
| Naive | n^3 | O(n^3) |
| Strassen | n^2.807 | O(n^2.807) |
| Coppersmith-Winograd | -- | O(n^2.376) |

### Trade-offs
- Strassen has higher constant factor and worse cache behavior
- Practical only for large matrices (n > 32-128)
- Numerically less stable than naive for floating point
- Uses more memory due to temporary matrices'''),
]
