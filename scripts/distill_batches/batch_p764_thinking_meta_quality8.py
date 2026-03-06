"""Phase 3F: Metacognition -- Code Quality Judgment (Part 8)

Rate code performance with complexity analysis: Big-O evaluation of common
anti-patterns including sort-based anagram checks, naive recursive Fibonacci,
unindexed LIKE queries, string concatenation in loops, and N+1 API call patterns.
"""

PAIRS = [
    (
        "thinking/meta-quality-performance-anagram-sort",
        r'''Rate the performance of this anagram checker (1-10):

```python
def are_anagrams(s1: str, s2: str) -> bool:
    return sorted(s1.lower().strip()) == sorted(s2.lower().strip())
```''',
        r'''<think>
Let me analyze the time and space complexity of this anagram checker.

The function sorts both strings and compares the results. Let n = len(s1), m = len(s2).

Time complexity:
- `s1.lower()`: O(n)
- `s1.strip()`: O(n)
- `sorted(...)`: O(n log n) -- Timsort
- Same for s2: O(m log m)
- Comparison of two sorted lists: O(min(n, m))
- Total: O(n log n + m log m)

Space complexity:
- `sorted()` creates new lists: O(n) + O(m)
- `lower()` and `strip()` create new strings: O(n) + O(m)
- Total: O(n + m)

The alternative approach using a frequency counter (Counter or a dictionary) would be O(n + m) time with O(k) space where k is the alphabet size (bounded constant for typical character sets).

For short strings (typical anagram use cases like words), O(n log n) vs O(n) makes negligible practical difference. For very long strings (document-level comparison), the sorting approach is measurably slower.

The code is clean, readable, and correct. The early-exit optimization of checking length equality first is missing but would only save work when lengths differ.

Score: 6/10. Correct and readable but not optimal.
</think>

**Performance: 6/10**

| Criterion              | Rating  | Analysis                                       |
|-------------------------|---------|------------------------------------------------|
| Time complexity         | 5/10    | O(n log n) -- suboptimal; O(n) is achievable   |
| Space complexity        | 5/10    | O(n) for sorted copies; could be O(1) with fixed-size counter |
| Practical performance   | 7/10    | For typical word-length inputs, overhead is minimal |
| Algorithmic correctness | 10/10   | Correct for all inputs                         |
| Readability trade-off   | 8/10    | Extremely clear one-liner                      |

**What's good:**
- Extremely readable and concise -- the intent is immediately clear.
- Handles case insensitivity and whitespace trimming.
- Correct for all Unicode inputs (sorted works on any comparable sequence).

**What could be improved:**
1. **Missing length short-circuit:** If `len(s1) != len(s2)`, they cannot be anagrams. This O(1) check avoids unnecessary sorting.
2. **O(n log n) vs O(n):** A frequency counter achieves linear time.

**Optimized version:**

```python
from collections import Counter

def are_anagrams(s1: str, s2: str) -> bool:
    a, b = s1.lower().strip(), s2.lower().strip()
    if len(a) != len(b):
        return False
    return Counter(a) == Counter(b)
```

This runs in O(n) time. For ASCII-only inputs, an even faster approach uses a fixed-size array:

```python
def are_anagrams_fast(s1: str, s2: str) -> bool:
    a, b = s1.lower().strip(), s2.lower().strip()
    if len(a) != len(b):
        return False
    counts = [0] * 26
    for c1, c2 in zip(a, b):
        counts[ord(c1) - ord('a')] += 1
        counts[ord(c2) - ord('a')] -= 1
    return all(c == 0 for c in counts)
```

That said, the original sort-based approach is perfectly acceptable for typical use cases (word-length strings). The difference matters when processing millions of comparisons or very long strings.'''
    ),
    (
        "thinking/meta-quality-performance-recursive-fibonacci",
        r'''Rate the performance of this Fibonacci function (1-10):

```python
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# Usage
for i in range(40):
    print(f"fib({i}) = {fibonacci(i)}")
```''',
        r'''<think>
This is the classic naive recursive Fibonacci -- one of the most well-known examples of catastrophic time complexity.

Time complexity: O(2^n). Each call branches into two recursive calls, forming a binary tree. The exact complexity is O(phi^n) where phi is the golden ratio (~1.618), but for analysis purposes O(2^n) captures the exponential growth.

For n=40, this results in approximately 2^40 = ~1 trillion operations. In practice, `fibonacci(40)` takes several seconds in Python. `fibonacci(50)` can take minutes. `fibonacci(100)` is effectively uncomputable.

Space complexity: O(n) for the call stack depth (the tree is depth-n, and Python uses the call stack).

The massive redundancy: `fibonacci(n-2)` is computed twice, `fibonacci(n-3)` is computed 3 times, `fibonacci(n-4)` is computed 5 times, etc. The number of redundant computations follows the Fibonacci sequence itself.

The usage loop makes it even worse: it calls `fibonacci(i)` independently for each i from 0 to 39, recomputing everything from scratch each time. Total work is sum of 2^i for i in 0..39.

Solutions, in order of improvement:
- Memoization (top-down DP): O(n) time, O(n) space
- Iterative (bottom-up DP): O(n) time, O(1) space
- Matrix exponentiation: O(log n) time
- Closed form (Binet's formula): O(1) but loses precision for large n

Score: 1/10. This is the textbook example of exponential blowup.
</think>

**Performance: 1/10**

| Criterion              | Rating  | Analysis                                       |
|-------------------------|---------|------------------------------------------------|
| Time complexity         | 0/10    | O(2^n) -- exponential; unusable past n~40      |
| Space complexity        | 4/10    | O(n) call stack; risks RecursionError for large n |
| Redundant computation   | 0/10    | Identical subproblems recomputed exponentially  |
| Usage pattern           | 0/10    | Loop recomputes from scratch for each i        |
| Scalability             | 0/10    | n=50 takes minutes; n=100 is uncomputable      |

**What's good:**
- The code is mathematically correct and matches the recursive definition of Fibonacci.
- It is readable and easy to understand.

**What's critically wrong:**
1. **Exponential time (CRITICAL):** O(2^n) means each increment of n roughly doubles execution time. `fib(40)` makes ~1.6 billion calls in Python.
2. **Massive redundancy:** `fib(38)` is computed twice, `fib(37)` three times, `fib(36)` five times -- the redundancy itself grows as the Fibonacci sequence.
3. **Loop compounds the problem:** Calling `fibonacci(i)` independently for each i means zero reuse between iterations.

**Fixed versions (three levels of optimization):**

```python
# 1. Memoized -- O(n) time, O(n) space
from functools import lru_cache

@lru_cache(maxsize=None)
def fib_memo(n):
    if n <= 1:
        return n
    return fib_memo(n - 1) + fib_memo(n - 2)

# 2. Iterative -- O(n) time, O(1) space (best general approach)
def fib_iter(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

# 3. For the loop use case -- generate all values in one pass
def fib_sequence(count):
    a, b = 0, 1
    for _ in range(count):
        yield a
        a, b = b, a + b

for i, val in enumerate(fib_sequence(40)):
    print(f"fib({i}) = {val}")
```

The iterative generator is the best fit for the original use case: it computes all 40 values in a single O(n) pass with O(1) space, compared to the original's O(2^41) total work.'''
    ),
    (
        "thinking/meta-quality-performance-like-wildcard-query",
        r'''Rate the performance of this database query (1-10):

```python
def search_products(search_term):
    query = f"""
        SELECT p.id, p.name, p.description, p.price,
               c.name as category_name
        FROM products p
        JOIN categories c ON p.category_id = c.id
        WHERE p.name LIKE '%{search_term}%'
           OR p.description LIKE '%{search_term}%'
           OR c.name LIKE '%{search_term}%'
        ORDER BY p.name
    """
    return db.execute(query)
```''',
        r'''<think>
Let me analyze the performance and security of this database query.

Performance issues:

1. `LIKE '%term%'` (leading wildcard): This pattern forces a full table scan because the database cannot use a B-tree index when the pattern starts with a wildcard. The database must examine every row and perform string matching on every value. For a products table with millions of rows, this is O(n) per column per table.

2. Three LIKE clauses with OR: The query checks three columns across two tables with leading wildcards. The optimizer cannot use indexes for any of them, so it must scan the full join result and test all three conditions for every row.

3. JOIN before filter: The JOIN between products and categories is computed before the WHERE filter is applied (since the filter is on columns from both tables). This means the full cartesian product of matching rows is materialized before filtering.

4. ORDER BY on unindexed result: After the full scan, the result must be sorted by p.name. Without a usable index, this is an additional O(n log n) filesort.

5. No pagination (LIMIT/OFFSET): The query returns ALL matching rows. For a broad search term, this could be thousands of results.

Security issue:
6. SQL INJECTION: The search_term is interpolated directly into the query string with an f-string. This is a critical SQL injection vulnerability. `search_term = "'; DROP TABLE products; --"` would be catastrophic.

For proper text search, the solution is full-text search indexes (PostgreSQL tsvector, MySQL FULLTEXT, or Elasticsearch/Solr).

Score: 2/10.
</think>

**Performance: 2/10**

| Criterion              | Rating  | Analysis                                          |
|-------------------------|---------|---------------------------------------------------|
| Index utilization        | 0/10    | Leading wildcard `%term%` defeats all B-tree indexes |
| Scan efficiency          | 1/10    | Full table scan on joined result for every query  |
| Result set control       | 2/10    | No LIMIT; potentially returns thousands of rows   |
| Sort cost                | 3/10    | ORDER BY requires filesort on unindexed scan result |
| Scalability              | 1/10    | Linearly degrades with table size; 1M rows = seconds |
| **Also: SQL injection**  | 0/10    | f-string interpolation; trivially exploitable     |

**What's good:**
- The query logic is correct for a naive text search.
- The JOIN structure is straightforward.

**What's critically wrong:**
1. **Leading wildcard kills indexes (CRITICAL):** `LIKE '%term%'` requires a full sequential scan of every row. With 1M products, this means reading and string-matching every single row on every search.
2. **Three-way OR across two tables:** The optimizer cannot short-circuit; it must evaluate all three LIKE conditions across the full join.
3. **No pagination:** Returning all results at once wastes bandwidth and memory.
4. **SQL injection (CRITICAL):** Direct f-string interpolation is exploitable. This is not a performance issue but must be flagged.

**Fixed version using full-text search (PostgreSQL):**

```python
def search_products(search_term, page=1, page_size=20):
    query = """
        SELECT p.id, p.name, p.description, p.price,
               c.name as category_name,
               ts_rank(p.search_vector, plainto_tsquery('english', %s)) AS rank
        FROM products p
        JOIN categories c ON p.category_id = c.id
        WHERE p.search_vector @@ plainto_tsquery('english', %s)
        ORDER BY rank DESC, p.name
        LIMIT %s OFFSET %s
    """
    offset = (page - 1) * page_size
    return db.execute(query, (search_term, search_term, page_size, offset))
```

This requires a GIN index on a `tsvector` column: `CREATE INDEX idx_products_search ON products USING GIN(search_vector);`. Full-text search uses inverted indexes for O(log n) lookups instead of O(n) scans, and parameterized queries eliminate the SQL injection vector.'''
    ),
    (
        "thinking/meta-quality-performance-string-concat-loop",
        r'''Rate the performance of this string builder function (1-10):

```python
def build_report(records):
    report = ""
    report += "=== SALES REPORT ===\n"
    report += f"Generated: {datetime.now()}\n"
    report += f"Total Records: {len(records)}\n"
    report += "=" * 40 + "\n\n"

    for record in records:
        report += f"Date: {record['date']}\n"
        report += f"  Product: {record['product']}\n"
        report += f"  Quantity: {record['quantity']}\n"
        report += f"  Price: ${record['price']:.2f}\n"
        report += f"  Total: ${record['quantity'] * record['price']:.2f}\n"
        report += "-" * 30 + "\n"

    report += "\n=== END OF REPORT ===\n"
    return report
```''',
        r'''<think>
Let me analyze the string concatenation pattern in this function.

In Python, strings are immutable. Every `+=` operation creates a new string object, copies the existing content, and appends the new content. For n records, each with ~5 concatenation operations in the loop body:

Naive analysis: If the report grows to length L after processing all records, the total bytes copied is approximately sum(i for i in range(L)), which is O(L^2). With n records each adding ~100 characters, L grows linearly with n, so total work is O(n^2) in the worst case.

CPython optimization: CPython has an optimization (since ~2.4) that detects when the string being concatenated has a reference count of 1 and resizes it in place. In many cases this turns O(n^2) into amortized O(n). HOWEVER:
- This optimization is CPython-specific, not guaranteed by the language spec
- It can break if another reference to the string exists
- PyPy, Jython, and other implementations may not have it
- It's still considered bad practice to rely on this

The idiomatic and reliable approach in Python is to use a list of strings and `str.join()`, or `io.StringIO`. Both give guaranteed O(n) performance.

For this specific use case (report generation), the practical impact depends on the number of records. For <1000 records, the difference is negligible even without the CPython optimization. For 100K+ records, the quadratic behavior (if triggered) becomes painfully slow.

Score: 4/10. Functionally correct but uses a known anti-pattern.
</think>

**Performance: 4/10**

| Criterion              | Rating  | Analysis                                          |
|-------------------------|---------|---------------------------------------------------|
| Time complexity         | 4/10    | O(n^2) worst case; O(n) with CPython optimization |
| Memory efficiency       | 3/10    | Creates many intermediate string objects           |
| GC pressure             | 3/10    | Each `+=` potentially discards a large string      |
| Idiomatic correctness   | 3/10    | Known anti-pattern in Python style guides          |
| Practical impact        | 6/10    | CPython optimization often masks the issue         |

**What's good:**
- The code is very readable; the intent is clear line-by-line.
- Formatting with f-strings is clean and appropriate.
- For small datasets, performance is perfectly acceptable.

**What's problematic:**
1. **Quadratic worst-case:** Without CPython's refcount-1 optimization, each `report +=` copies the entire accumulated string. With 5 concatenations per record across n records, total bytes copied grows as O(n^2).
2. **Memory churn:** Each concatenation can allocate a new string and discard the old one, pressuring the garbage collector.
3. **Non-portable:** The CPython optimization is an implementation detail, not a language guarantee.

**Fixed version using list join:**

```python
def build_report(records):
    parts = []
    parts.append("=== SALES REPORT ===\n")
    parts.append(f"Generated: {datetime.now()}\n")
    parts.append(f"Total Records: {len(records)}\n")
    parts.append("=" * 40 + "\n\n")

    for record in records:
        parts.append(f"Date: {record['date']}\n")
        parts.append(f"  Product: {record['product']}\n")
        parts.append(f"  Quantity: {record['quantity']}\n")
        parts.append(f"  Price: ${record['price']:.2f}\n")
        parts.append(f"  Total: ${record['quantity'] * record['price']:.2f}\n")
        parts.append("-" * 30 + "\n")

    parts.append("\n=== END OF REPORT ===\n")
    return "".join(parts)
```

`list.append()` is amortized O(1), and `"".join(parts)` makes a single pass to allocate the final string. Total: guaranteed O(n) time regardless of Python implementation. For very large reports, `io.StringIO` is equally efficient and provides a file-like interface.'''
    ),
    (
        "thinking/meta-quality-performance-n-plus-one-api",
        r'''Rate the performance of this API data fetching pattern (1-10):

```javascript
async function getUsersDashboard() {
  const usersResponse = await fetch('/api/users');
  const users = await usersResponse.json();

  const dashboardData = [];

  for (const user of users) {
    const postsResponse = await fetch(`/api/users/${user.id}/posts`);
    const posts = await postsResponse.json();

    const followersResponse = await fetch(`/api/users/${user.id}/followers`);
    const followers = await followersResponse.json();

    const statsResponse = await fetch(`/api/users/${user.id}/stats`);
    const stats = await statsResponse.json();

    dashboardData.push({
      ...user,
      posts,
      followers,
      stats,
    });
  }

  return dashboardData;
}
```''',
        r'''<think>
This is the N+1 problem applied to API calls, but even worse -- it's N*3+1.

For N users, the code makes:
- 1 request to fetch all users
- N requests to fetch posts (one per user)
- N requests to fetch followers (one per user)
- N requests to fetch stats (one per user)
- Total: 3N + 1 HTTP requests

And all of these are sequential due to `await` inside the for loop. Each request must complete before the next one starts. If each HTTP round-trip takes ~100ms:
- 10 users: 31 requests = ~3.1 seconds
- 100 users: 301 requests = ~30 seconds
- 1000 users: 3001 requests = ~5 minutes

Even worse, this hammers the backend API server with thousands of individual requests that could be served as bulk queries.

There are multiple levels of optimization:
1. Parallelize the three per-user requests with Promise.all (still N+1 total groups, but 3x faster)
2. Parallelize all user requests with Promise.all (1 initial + 1 parallel batch = ~200ms regardless of N)
3. Use a batch/bulk API endpoint: `POST /api/users/bulk?include=posts,followers,stats` -- single request
4. Use GraphQL to fetch everything in one query
5. Server-side: aggregate endpoint that returns the dashboard data in one call

Also: no error handling. If any single request fails, the entire function throws. No pagination on the users list. No timeout handling.

Score: 1/10.
</think>

**Performance: 1/10**

| Criterion              | Rating  | Analysis                                          |
|-------------------------|---------|---------------------------------------------------|
| HTTP request count       | 0/10    | 3N+1 sequential requests; 100 users = 301 calls  |
| Latency                  | 0/10    | All requests sequential; total = sum of all round-trips |
| Backend load             | 1/10    | Thousands of individual requests hammer the server |
| Parallelism              | 0/10    | `await` in loop serializes everything             |
| Scalability              | 0/10    | Linear growth in wall-clock time with user count  |
| Error resilience         | 1/10    | One failed request crashes everything             |

**What's good:**
- The code is readable and the data assembly logic is clear.
- Async/await syntax is used correctly (just inefficiently).

**What's critically wrong:**
1. **Sequential N+1 (CRITICAL):** `await` inside a `for` loop means each request waits for the previous one. With 100ms per round-trip and 100 users, this takes 30 seconds for data that could be fetched in 200ms.
2. **Three sub-requests per user:** Posts, followers, and stats are fetched as separate sequential calls, tripling the already-bad N+1 pattern.
3. **No batching:** The API is called with individual user IDs instead of a bulk request.

**Fixed version (progressive improvement):**

```javascript
// Level 1: Parallelize per-user requests
async function getUsersDashboard() {
  const usersResponse = await fetch('/api/users');
  const users = await usersResponse.json();

  const dashboardData = await Promise.all(
    users.map(async (user) => {
      const [posts, followers, stats] = await Promise.all([
        fetch(`/api/users/${user.id}/posts`).then(r => r.json()),
        fetch(`/api/users/${user.id}/followers`).then(r => r.json()),
        fetch(`/api/users/${user.id}/stats`).then(r => r.json()),
      ]);
      return { ...user, posts, followers, stats };
    })
  );

  return dashboardData;
}

// Level 2: Single bulk API call (best -- requires backend support)
async function getUsersDashboardOptimal() {
  const response = await fetch('/api/dashboard/users?include=posts,followers,stats');
  return response.json();
}
```

Level 1 reduces wall-clock time from 3N sequential round-trips to ~1 parallel batch (all 3N requests fire concurrently). Level 2 reduces it to a single HTTP request. For production systems, always prefer a dedicated aggregate endpoint or GraphQL query that resolves everything server-side in one round-trip.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
