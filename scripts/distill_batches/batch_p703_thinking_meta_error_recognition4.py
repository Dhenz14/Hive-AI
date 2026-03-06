"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 4)
Scenarios: Wrong database queries, incorrect error handling
"""

PAIRS = [
    (
        "thinking/meta-error-wrong-join-lost-rows",
        r'''I wrote this SQL query to get all users with their order totals:

```sql
SELECT
    u.id,
    u.name,
    u.email,
    COUNT(o.id) AS order_count,
    SUM(o.total) AS total_spent
FROM users u
JOIN orders o ON o.user_id = u.id
GROUP BY u.id, u.name, u.email
ORDER BY total_spent DESC;
```

Is this query correct?''',
        r'''<think>
Let me trace through this query with sample data...

Users table:
| id | name   | email          |
|----|--------|----------------|
| 1  | Alice  | alice@test.com |
| 2  | Bob    | bob@test.com   |
| 3  | Charlie| charlie@test.com|

Orders table:
| id | user_id | total |
|----|---------|-------|
| 1  | 1       | 50.00 |
| 2  | 1       | 30.00 |
| 3  | 2       | 75.00 |

Notice: Charlie (id=3) has NO orders.

With `JOIN` (INNER JOIN), the query only returns rows where there's a match in BOTH tables. Charlie has no orders, so Charlie is completely excluded from the results!

The query returns:
| id | name  | order_count | total_spent |
|----|-------|-------------|-------------|
| 1  | Alice | 2           | 80.00       |
| 2  | Bob   | 1           | 75.00       |

Charlie is missing! If the intent is "all users with their order totals," we need a LEFT JOIN to include users who haven't ordered yet.

With LEFT JOIN:
| id | name    | order_count | total_spent |
|----|---------|-------------|-------------|
| 1  | Alice   | 2           | 80.00       |
| 2  | Bob     | 1           | 75.00       |
| 3  | Charlie | 0           | NULL        |

Wait, but with LEFT JOIN, `COUNT(o.id)` correctly returns 0 for Charlie (since o.id is NULL and COUNT ignores NULLs). But `SUM(o.total)` returns NULL, not 0. We'd need `COALESCE(SUM(o.total), 0)`.

Also, `COUNT(o.id)` would return 1 instead of 0 if I accidentally used `COUNT(*)` — because LEFT JOIN still produces one row for Charlie, just with NULLs. `COUNT(*)` counts rows, `COUNT(o.id)` counts non-NULL values.

My error: using INNER JOIN when the requirement says "all users." This silently drops users with no orders — which is often the majority of users in a real system. The query appears to work correctly in development where all test users have orders, but fails in production.
</think>

**The query silently drops users who have no orders because it uses INNER JOIN instead of LEFT JOIN.**

### The bug
```sql
-- INNER JOIN excludes users with zero orders
FROM users u
JOIN orders o ON o.user_id = u.id
```

If you have 10,000 users but only 3,000 have ordered, this query only returns 3,000 rows. The other 7,000 users are silently excluded.

### The fix
```sql
SELECT
    u.id,
    u.name,
    u.email,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total), 0) AS total_spent
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
GROUP BY u.id, u.name, u.email
ORDER BY total_spent DESC;
```

Key changes:
- `LEFT JOIN` — includes users even when no matching orders exist
- `COUNT(o.id)` — correctly returns 0 for users with no orders (NULLs aren't counted). Don't use `COUNT(*)` which would return 1
- `COALESCE(SUM(o.total), 0)` — converts NULL sum to 0 for users with no orders

### Why this bug is insidious
It often passes testing because test databases have orders for every user. The bug only manifests in production where many users haven't ordered yet. The query returns valid-looking data — just incomplete. No error is thrown.

### The meta-lesson
When you see `JOIN` in a query that says "all X with their Y," immediately ask: "What happens to X records with no matching Y?" If they should be included, you need `LEFT JOIN` plus `COALESCE` for aggregate functions.'''
    ),
    (
        "thinking/meta-error-wrong-where-with-null",
        r'''I wrote this query to find users who are NOT in the admin role:

```sql
SELECT id, name, role
FROM users
WHERE role != 'admin';
```

A colleague says some users are missing from the results. What's wrong?''',
        r'''<think>
Let me think about what values `role` could have...

If role can be NULL (user hasn't been assigned a role yet), then:
- `NULL != 'admin'` evaluates to... NULL, not TRUE!

In SQL's three-valued logic:
- `'user' != 'admin'` → TRUE (included in results)
- `'admin' != 'admin'` → FALSE (excluded, correct)
- `NULL != 'admin'` → NULL (excluded! NOT correct!)

So users with `role = NULL` are silently excluded from the results. They're neither admin nor non-admin according to SQL's NULL semantics — they're "unknown."

This is one of the most common SQL mistakes. Any comparison with NULL returns NULL, which is treated as falsy in WHERE clauses.

The fix is:
```sql
WHERE role != 'admin' OR role IS NULL
```

Or using COALESCE:
```sql
WHERE COALESCE(role, '') != 'admin'
```

Or in PostgreSQL, the null-safe comparison:
```sql
WHERE role IS DISTINCT FROM 'admin'
```

My error: forgetting that NULL comparisons in SQL follow three-valued logic, not boolean logic. In most programming languages, `null != 'admin'` would be true. In SQL, it's NULL.
</think>

**Users with `role = NULL` are silently excluded because `NULL != 'admin'` evaluates to NULL (falsy) in SQL.**

### The problem
```sql
-- These users are EXCLUDED:
-- role = 'admin'  → FALSE (correct, excluded)
-- role = NULL     → NULL  (WRONG! also excluded)

WHERE role != 'admin'
```

SQL uses three-valued logic. Any comparison with NULL returns NULL, not TRUE or FALSE. NULL is treated as falsy in WHERE clauses, so NULL-role users are filtered out.

### The fix
```sql
-- Option 1: explicit NULL check
WHERE role != 'admin' OR role IS NULL

-- Option 2: COALESCE
WHERE COALESCE(role, '') != 'admin'

-- Option 3: PostgreSQL null-safe operator
WHERE role IS DISTINCT FROM 'admin'
```

### Why this is treacherous
- The query runs without errors
- It returns valid-looking data
- It's only wrong by omission — you notice missing rows, not wrong rows
- Most programming languages treat `null != "admin"` as `true`, so the SQL behavior violates programmer intuition

### The meta-lesson
Any time you write `WHERE column != value`, ask: "Can this column be NULL?" If yes, you're probably losing NULL rows. This applies to `NOT IN` as well: `WHERE id NOT IN (1, 2, NULL)` returns ZERO rows because any comparison with NULL yields NULL.'''
    ),
    (
        "thinking/meta-error-exception-swallowing-retry",
        r'''I wrote this retry wrapper for API calls:

```python
import time
import requests

def api_call_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None
```

I want robust error handling. Does this look right?''',
        r'''<think>
Let me trace through this retry logic...

The function tries the request up to 3 times, with exponential backoff (1s, 2s, 4s). On each failure, it catches `Exception` and either retries or returns `None`.

Several problems jump out:

1. **Catching `Exception` is too broad.** It catches:
   - `ConnectionError` — yes, retry makes sense
   - `Timeout` — yes, retry makes sense
   - `HTTPError` (from raise_for_status) — maybe, depends on status code
   - `JSONDecodeError` — NO! Retrying won't fix malformed JSON
   - `KeyboardInterrupt`... actually no, that's BaseException
   - But it DOES catch `MemoryError`, `RecursionError`, etc.

2. **Retrying 4xx errors is wrong.** `response.raise_for_status()` raises for BOTH 4xx and 5xx. But 4xx means the REQUEST is wrong (bad auth, bad URL, bad payload). Retrying a 400 Bad Request 3 times won't help — it'll fail the same way every time. Only 5xx errors (server-side) are worth retrying.

3. **Returning `None` on final failure is dangerous.** The caller has no idea WHY it failed. Was it a network error? A 404? A 500? The caller will likely do `result = api_call_with_retry(url)` and then `result["data"]` — TypeError on None! Or worse, they check `if result:` and silently proceed with no data. The exception is swallowed — no stack trace, no error message, nothing in logs.

4. **No logging.** When retries happen, there's no record of what went wrong. Debugging in production becomes impossible.

My error: I prioritized "robustness" (never crash) over "correctness" (report errors properly). Returning None instead of raising is not robust — it just moves the crash to a different, harder-to-debug location.
</think>

**This retry function has several issues: it catches too broadly, retries non-retryable errors, and swallows exceptions by returning None.**

### Issue 1: Catching `Exception` is too broad
```python
except Exception:  # catches JSONDecodeError, ValueError, etc.
```

Only retry on transient errors:
```python
except (requests.ConnectionError, requests.Timeout) as e:
    # These are transient — worth retrying
except requests.HTTPError as e:
    if e.response.status_code < 500:
        raise  # 4xx errors won't fix themselves
```

### Issue 2: Retrying 4xx errors is pointless
`raise_for_status()` raises on both 400 and 500. A 401 Unauthorized won't become authorized after a retry. A 404 won't appear. Only 5xx (server errors) and network errors are worth retrying.

### Issue 3: Returning `None` swallows the error
```python
return None  # caller has NO idea what went wrong
```

This guarantees a `TypeError: 'NoneType' is not subscriptable` somewhere downstream — harder to debug than the original error.

### Fixed version
```python
import logging
import time
import requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {500, 502, 503, 504, 429}

def api_call_with_retry(url, max_retries=3):
    last_exception = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt+1}/{max_retries} failed: {e}")
        except requests.HTTPError as e:
            if e.response.status_code not in RETRYABLE_STATUS:
                raise  # 4xx errors — don't retry
            last_exception = e
            logger.warning(f"Attempt {attempt+1}/{max_retries}: HTTP {e.response.status_code}")

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    raise last_exception  # raise, don't return None
```

### The meta-lesson
"Never crash" is not the same as "robust." Returning `None` instead of raising doesn't prevent errors — it just hides them, making bugs harder to find. Robust code fails loudly at the source, not silently downstream. Catch specific exceptions, retry only transient failures, and always propagate the error if retries are exhausted.'''
    ),
    (
        "thinking/meta-error-error-handling-leaks-info",
        r'''I wrote this error handler for my Flask API:

```python
@app.errorhandler(Exception)
def handle_error(error):
    return jsonify({
        "error": str(error),
        "type": type(error).__name__,
        "traceback": traceback.format_exc()
    }), 500
```

This way users always get helpful error messages. Is this good practice?''',
        r'''<think>
Let me examine what information this error handler exposes...

`str(error)` — could contain:
- Database connection strings: "Can't connect to MySQL server at db.internal.company.com:3306"
- File paths: "FileNotFoundError: /var/www/app/config/secrets.yaml"
- SQL query details: "ProgrammingError: relation 'users' has no column 'ssn'"

`type(error).__name__` — reveals:
- The exception class, which tells attackers what libraries/frameworks you use
- "OperationalError" → you use SQLAlchemy
- "RedisError" → you use Redis

`traceback.format_exc()` — this is the worst one. It reveals:
- Full file paths on the server
- All function names and code snippets
- Line numbers (useful for targeting known vulnerabilities)
- Library versions (from file paths like `/usr/lib/python3.9/...`)
- Internal architecture (which functions call which)
- Variable values in local scope

This is a massive information disclosure vulnerability! An attacker can trigger errors deliberately (send malformed input) to map out the entire backend.

My error: I confused "helpful for developers" with "good for production." In development, detailed errors are great. In production, they're a security vulnerability. The fix is to log the full details server-side and return a generic message to the client.
</think>

**This is a severe information disclosure vulnerability. The error handler leaks internal server details to external users.**

### What gets exposed
```python
# An attacker sends a malformed request and gets back:
{
    "error": "Can't connect to MySQL at db-prod.internal.corp:3306 (password='hunter2')",
    "type": "OperationalError",
    "traceback": "File \"/var/www/app/services/user_service.py\", line 42, in get_user\n    db.execute(\"SELECT * FROM users WHERE id = \" + user_id)\n..."
}
```

The attacker now knows:
- Your internal database hostname and port
- That you use MySQL/SQLAlchemy
- Your file structure and function names
- That you have SQL injection on line 42
- Your Python version (from traceback paths)

### The fix
```python
import logging
import traceback
import uuid

logger = logging.getLogger(__name__)

@app.errorhandler(Exception)
def handle_error(error):
    # Generate a correlation ID for support/debugging
    error_id = uuid.uuid4().hex[:8]

    # Log full details server-side
    logger.error(
        f"Error {error_id}: {type(error).__name__}: {error}",
        exc_info=True  # includes full traceback in logs
    )

    # Return minimal info to client
    return jsonify({
        "error": "An internal error occurred",
        "error_id": error_id  # user can reference this for support
    }), 500
```

For development, use Flask's built-in debug mode which is automatically disabled in production:
```python
app = Flask(__name__)
app.config['DEBUG'] = os.environ.get('FLASK_ENV') == 'development'
```

### The meta-lesson
Error messages serve two audiences: developers (who need full details) and users (who need to know something went wrong). Serving developer-level details to users is an information disclosure vulnerability. Always log full details server-side and return sanitized messages to clients.'''
    ),
    (
        "thinking/meta-error-wrong-aggregate-query",
        r'''I wrote this query to find the most recent order for each customer:

```sql
SELECT
    customer_id,
    MAX(order_date) AS latest_date,
    order_total,
    order_status
FROM orders
GROUP BY customer_id;
```

But the results look wrong — the order_total and order_status don't match the most recent order. Why?''',
        r'''<think>
Let me trace through this with sample data...

Orders table:
| customer_id | order_date  | order_total | order_status |
|------------|-------------|-------------|--------------|
| 1          | 2024-01-15  | 50.00       | completed    |
| 1          | 2024-03-20  | 150.00      | pending      |
| 2          | 2024-02-10  | 75.00       | completed    |

The query groups by customer_id and takes MAX(order_date). For customer 1, MAX(order_date) is 2024-03-20.

But what about `order_total` and `order_status`? They're not in the GROUP BY and not in an aggregate function. In standard SQL, this is actually INVALID — you can't select non-aggregated, non-grouped columns.

MySQL (with only_full_group_by disabled) allows this but returns ARBITRARY values from any row in the group. So for customer 1, you might get:
- `latest_date = 2024-03-20` (from MAX, correct)
- `order_total = 50.00` (from the FIRST row MySQL finds — WRONG!)
- `order_status = 'completed'` (from the FIRST row — WRONG!)

The MAX(order_date) is correct, but the other columns are from a random row, not from the row with the max date. SQL doesn't know you want the other columns from the "max date" row.

PostgreSQL and modern MySQL (with ONLY_FULL_GROUP_BY, the default since 5.7.5) would reject this query with an error.

The correct approaches are:
1. Subquery/JOIN: find max dates, then join back to get full rows
2. Window function: ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date DESC)
3. DISTINCT ON (PostgreSQL specific)
</think>

**The `order_total` and `order_status` come from an ARBITRARY row in each group, not from the row with the max date.**

### Why it's wrong
```sql
SELECT customer_id,
    MAX(order_date),  -- correct: takes max across group
    order_total,      -- WRONG: arbitrary row from group!
    order_status      -- WRONG: arbitrary row from group!
FROM orders
GROUP BY customer_id;
```

`MAX(order_date)` correctly finds the latest date. But `order_total` and `order_status` aren't aggregated or grouped — SQL picks values from an arbitrary row. You get the date from one row and the total/status from a different row.

### Fix 1: Window function (recommended)
```sql
SELECT customer_id, order_date, order_total, order_status
FROM (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY order_date DESC
        ) AS rn
    FROM orders
) ranked
WHERE rn = 1;
```

### Fix 2: Subquery join
```sql
SELECT o.customer_id, o.order_date, o.order_total, o.order_status
FROM orders o
INNER JOIN (
    SELECT customer_id, MAX(order_date) AS max_date
    FROM orders
    GROUP BY customer_id
) latest ON o.customer_id = latest.customer_id
       AND o.order_date = latest.max_date;
```

### Fix 3: PostgreSQL DISTINCT ON
```sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_date, order_total, order_status
FROM orders
ORDER BY customer_id, order_date DESC;
```

### The meta-lesson
`GROUP BY` only guarantees correctness for grouped columns and aggregate functions. Any non-aggregated, non-grouped column in SELECT returns undefined results. Strict SQL modes reject this; permissive modes silently give wrong data. When you need "the row with the max/min of X," use window functions, not GROUP BY with non-aggregated columns.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
