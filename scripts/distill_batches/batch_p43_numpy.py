"""NumPy — array operations, broadcasting, linear algebra, and performance patterns."""

PAIRS = [
    (
        "python/numpy-patterns",
        "Show NumPy patterns: array creation, broadcasting, vectorization, linear algebra, and performance optimization.",
        '''NumPy patterns for efficient numerical computing:

```python
import numpy as np

# --- Array creation ---

# From data
a = np.array([1, 2, 3, 4, 5])
matrix = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])

# Generation functions
zeros = np.zeros((3, 4))             # 3x4 zeros
ones = np.ones((2, 3), dtype=np.float32)
identity = np.eye(4)                  # 4x4 identity matrix
range_arr = np.arange(0, 10, 0.5)    # [0, 0.5, 1.0, ..., 9.5]
linspace = np.linspace(0, 1, 100)    # 100 points from 0 to 1
random = np.random.randn(3, 4)       # Standard normal distribution
random_int = np.random.randint(0, 100, size=(5, 5))


# --- Indexing and slicing ---

a = np.arange(20).reshape(4, 5)
# [[0,1,2,3,4], [5,6,7,8,9], [10,11,12,13,14], [15,16,17,18,19]]

a[1, 3]         # 8 (row 1, col 3)
a[:, 2]          # [2, 7, 12, 17] (all rows, col 2)
a[1:3, 1:4]      # [[6,7,8], [11,12,13]] (submatrix)

# Boolean indexing (masking)
mask = a > 10
a[mask]          # [11, 12, 13, 14, 15, 16, 17, 18, 19]
a[a % 2 == 0]    # All even numbers

# Fancy indexing
rows = [0, 2, 3]
cols = [1, 3, 4]
a[rows, cols]    # [1, 13, 19] (specific elements)


# --- Broadcasting ---

# Scalar + array
a = np.array([1, 2, 3])
result = a * 2  # [2, 4, 6]

# 1D + 2D (broadcasts rows)
matrix = np.ones((3, 4))
row_weights = np.array([1, 2, 3, 4])
weighted = matrix * row_weights  # Each row multiplied by weights

# Column-wise operation
col_vector = np.array([[10], [20], [30]])  # Shape (3, 1)
result = matrix + col_vector  # Each column gets different offset

# Outer product via broadcasting
a = np.array([1, 2, 3])[:, np.newaxis]  # (3, 1)
b = np.array([4, 5, 6])[np.newaxis, :]  # (1, 3)
outer = a * b  # (3, 3) outer product


# --- Vectorized operations (replace loops) ---

# BAD: Python loop
def distance_loop(points, center):
    distances = []
    for p in points:
        d = np.sqrt(sum((p[i] - center[i])**2 for i in range(len(p))))
        distances.append(d)
    return distances

# GOOD: Vectorized
def distance_vectorized(points, center):
    return np.sqrt(np.sum((points - center)**2, axis=1))

# 100x+ faster for large arrays
points = np.random.randn(100000, 3)
center = np.array([0, 0, 0])


# --- Linear algebra ---

A = np.array([[1, 2], [3, 4]])
B = np.array([[5, 6], [7, 8]])

# Matrix multiplication
C = A @ B              # Or np.matmul(A, B)
C = np.dot(A, B)       # Same for 2D arrays

# Solve Ax = b
b = np.array([5, 11])
x = np.linalg.solve(A, b)  # Much faster than inv(A) @ b

# Eigenvalues
eigenvalues, eigenvectors = np.linalg.eig(A)

# SVD (used in dimensionality reduction)
U, S, Vt = np.linalg.svd(A)

# Norm
norm = np.linalg.norm(A)           # Frobenius norm
row_norms = np.linalg.norm(A, axis=1)  # Per-row L2 norm

# Determinant and inverse
det = np.linalg.det(A)
inv = np.linalg.inv(A)


# --- Common patterns ---

# Softmax
def softmax(x: np.ndarray) -> np.ndarray:
    exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return exp_x / np.sum(exp_x, axis=-1, keepdims=True)

# Cosine similarity (batch)
def cosine_similarity(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    A_norm = A / np.linalg.norm(A, axis=1, keepdims=True)
    B_norm = B / np.linalg.norm(B, axis=1, keepdims=True)
    return A_norm @ B_norm.T

# One-hot encoding
def one_hot(labels: np.ndarray, n_classes: int) -> np.ndarray:
    result = np.zeros((len(labels), n_classes))
    result[np.arange(len(labels)), labels] = 1
    return result

# Top-k indices
def top_k(arr: np.ndarray, k: int) -> np.ndarray:
    """Get indices of k largest values."""
    return np.argpartition(arr, -k)[-k:]

# Moving average
def moving_average(arr: np.ndarray, window: int) -> np.ndarray:
    return np.convolve(arr, np.ones(window)/window, mode="valid")
```

Performance tips:
1. **Vectorize** — replace Python loops with NumPy operations
2. **Avoid copies** — use views (slicing) when possible
3. **Contiguous memory** — use `np.ascontiguousarray` for C-order
4. **dtype matters** — float32 is 2x faster than float64 for many ops
5. **Broadcasting** — avoid explicit `tile`/`repeat` for shape matching'''
    ),
]
