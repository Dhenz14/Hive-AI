PAIRS = [
    ("thinking/debugging", r'''My SQL query returns wrong results because of implicit type coercion:

```sql
SELECT * FROM users WHERE phone_number = 5551234567;
```

The phone_number column is VARCHAR(20). The query returns users with phone "5551234567" but also returns a user with phone "5551234567-ext100". In another case:

```sql
SELECT * FROM orders WHERE order_id = '12345abc';
```

order_id is INT. Instead of an error, MySQL returns the row with order_id = 12345. What's going on?''', r'''<think>
This is about MySQL's implicit type coercion behavior.

1. When comparing a VARCHAR column to an integer, MySQL converts the VARCHAR to a number. "5551234567-ext100" becomes 5551234567 (parsing stops at the first non-numeric character). So the comparison becomes 5551234567 = 5551234567, which is true.

2. When comparing an INT column to a string, MySQL converts the string to a number. '12345abc' becomes 12345. So order_id = 12345 matches.

This is a well-known MySQL gotcha that causes silent data correctness issues and can also prevent index usage.
</think>

MySQL performs implicit type coercion when comparing values of different types, leading to silent data correctness issues.

**Case 1: VARCHAR compared to INT**

```sql
-- phone_number is VARCHAR(20)
SELECT * FROM users WHERE phone_number = 5551234567;
```

MySQL converts the VARCHAR to a number for comparison. The string `'5551234567-ext100'` is converted to `5551234567` because MySQL parses from left to right and stops at the first non-numeric character. So `5551234567 = 5551234567` is true, and the wrong row is returned.

**Case 2: INT compared to STRING**

```sql
-- order_id is INT
SELECT * FROM orders WHERE order_id = '12345abc';
```

MySQL converts `'12345abc'` to `12345` (stops at first non-numeric character). No error is raised, and order 12345 is returned silently.

**Fix: Always use matching types**

```sql
-- For VARCHAR columns, compare with strings:
SELECT * FROM users WHERE phone_number = '5551234567';

-- For INT columns, compare with integers:
SELECT * FROM orders WHERE order_id = 12345;
```

**Additional dangers of implicit coercion:**

```sql
-- Index bypass: comparing VARCHAR to INT prevents index usage
SELECT * FROM users WHERE phone_number = 5551234567;
-- MySQL converts EVERY row's phone_number to INT for comparison
-- This causes a full table scan even if phone_number is indexed!

-- Fix:
SELECT * FROM users WHERE phone_number = '5551234567';
-- This uses the index on phone_number
```

**Even worse examples:**

```sql
-- All these match because '0abc' converts to 0:
SELECT * FROM users WHERE username = 0;
-- Returns ALL rows where username starts with a non-numeric character!
-- 'alice' -> 0, 'bob' -> 0, 'charlie' -> 0
-- They ALL equal 0!
```

**PostgreSQL is stricter (for comparison):**

```sql
-- PostgreSQL:
SELECT * FROM orders WHERE order_id = '12345abc';
-- ERROR: invalid input syntax for type integer: "12345abc"
```

**Prevention tips:**
- Always use the correct data type in WHERE clauses -- string columns need quoted values
- Use parameterized queries (prepared statements) which handle type casting correctly
- Enable `STRICT_TRANS_TABLES` SQL mode in MySQL for stricter behavior
- Use PostgreSQL if data type safety is critical
- Add CHECK constraints to validate data formats
- Review EXPLAIN output to check for full table scans caused by type mismatches
- Use a linter like `sqlfluff` that can detect type mismatch in comparisons'''),

    ("thinking/debugging", r'''My SQL aggregation is producing wrong results because of NULL handling:

```sql
SELECT
    department,
    COUNT(*) as total_employees,
    AVG(bonus) as avg_bonus,
    SUM(bonus) as total_bonus
FROM employees
GROUP BY department;
```

Results:
```
department  | total_employees | avg_bonus | total_bonus
engineering |              10 |      5000 |       25000
marketing   |               8 |      4000 |       20000
```

But engineering has 10 employees and only 5 received bonuses. The AVG should include the 5 employees with NULL bonus (treating NULL as 0), giving avg_bonus = 2500, not 5000. And total_bonus should account for all 10 employees somehow.''', r'''<think>
SQL aggregate functions (AVG, SUM, COUNT, etc.) ignore NULL values by default. This is the SQL standard behavior.

- AVG(bonus) computes the average of non-NULL values only. 5 employees have bonuses totaling 25000. AVG = 25000/5 = 5000.
- SUM(bonus) sums non-NULL values. 25000 is correct.
- COUNT(*) counts all rows. COUNT(bonus) would count only non-NULL values.

The user wants NULL bonuses treated as 0. The fix is to use COALESCE(bonus, 0).
</think>

SQL aggregate functions ignore NULL values by default. This is standard SQL behavior, not a bug, but it often produces surprising results.

**How NULLs affect each aggregate:**

```sql
-- Given: 10 employees, 5 have bonus, 5 have NULL bonus
-- Bonuses: 5000, 5000, 5000, 5000, 5000, NULL, NULL, NULL, NULL, NULL

COUNT(*)      = 10    -- counts all rows
COUNT(bonus)  = 5     -- counts only non-NULL values
SUM(bonus)    = 25000 -- sums non-NULL values
AVG(bonus)    = 5000  -- SUM(non-NULL) / COUNT(non-NULL) = 25000/5
```

`AVG(bonus)` divides by 5 (non-NULL count), not 10 (total rows). If you want NULL treated as 0, you must explicitly convert.

**Fix: Use COALESCE to treat NULL as 0**

```sql
SELECT
    department,
    COUNT(*) as total_employees,
    COUNT(bonus) as employees_with_bonus,
    AVG(COALESCE(bonus, 0)) as avg_bonus_all,
    AVG(bonus) as avg_bonus_recipients,
    SUM(COALESCE(bonus, 0)) as total_bonus
FROM employees
GROUP BY department;
```

Results:
```
department  | total | with_bonus | avg_all | avg_recipients | total_bonus
engineering |    10 |          5 |    2500 |           5000 |       25000
marketing   |     8 |          5 |    2500 |           4000 |       20000
```

Now `avg_bonus_all` divides by 10 (all employees) because COALESCE converts NULLs to 0 before AVG processes them.

**Other NULL surprises in SQL:**

```sql
-- NULL in comparisons: neither true nor false
SELECT * FROM employees WHERE bonus != 5000;
-- Does NOT return rows where bonus IS NULL!
-- NULL != 5000 evaluates to NULL (unknown), not TRUE

-- Fix: explicitly handle NULL
SELECT * FROM employees WHERE bonus != 5000 OR bonus IS NULL;

-- NULL in DISTINCT
SELECT DISTINCT bonus FROM employees;
-- NULL is grouped as a single value in DISTINCT

-- NULL in GROUP BY
SELECT bonus, COUNT(*) FROM employees GROUP BY bonus;
-- All NULLs are grouped together as one group

-- NULL in ORDER BY
SELECT * FROM employees ORDER BY bonus;
-- NULLs appear first (PostgreSQL default) or last (MySQL default)
-- Use: ORDER BY bonus NULLS LAST (PostgreSQL)
```

**NULL in boolean logic:**

```sql
-- AND with NULL
TRUE AND NULL  = NULL
FALSE AND NULL = FALSE

-- OR with NULL
TRUE OR NULL   = TRUE
FALSE OR NULL  = NULL

-- NOT NULL = NULL
```

**Common aggregate NULL pitfalls:**

```sql
-- WRONG: percentage calculation ignoring NULLs
SELECT department,
    SUM(CASE WHEN bonus > 3000 THEN 1 ELSE 0 END) * 100.0 / COUNT(bonus)
    -- Divides by count of non-NULL, not total employees

-- RIGHT:
SELECT department,
    SUM(CASE WHEN bonus > 3000 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
    -- Divides by total employees
```

**Prevention tips:**
- Always consider whether NULL values should be included in your aggregation
- Use COALESCE(column, default) when NULLs should be treated as a specific value
- Use COUNT(*) for total rows, COUNT(column) for non-NULL rows
- Use IS NULL / IS NOT NULL, never = NULL or != NULL
- Document whether columns allow NULLs and what NULL means in your business context
- Consider using NOT NULL constraints with default values to avoid NULL complexity'''),

    ("thinking/debugging", r'''My SQL window function gives wrong results because of ordering:

```sql
SELECT
    employee_id,
    department,
    salary,
    ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) as rank,
    SUM(salary) OVER (PARTITION BY department) as dept_total,
    SUM(salary) OVER (PARTITION BY department ORDER BY salary DESC) as running_total
FROM employees;
```

Results for engineering department:
```
employee_id | department  | salary | rank | dept_total | running_total
101         | engineering | 150000 |    1 |     460000 |        150000
102         | engineering | 120000 |    2 |     460000 |        270000
103         | engineering | 100000 |    3 |     460000 |        370000
104         | engineering |  90000 |    4 |     460000 |        460000
```

dept_total is 460000 (correct for all rows). But running_total accumulates. Why does adding ORDER BY to the window function change SUM from total to running sum?''', r'''<think>
This is a very common source of confusion with SQL window functions. When you use an aggregate window function (SUM, AVG, etc.) with ORDER BY in the OVER clause, the default frame changes.

Without ORDER BY:
- Default frame: ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
- This means the aggregate considers ALL rows in the partition

With ORDER BY:
- Default frame: RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
- This means the aggregate considers only rows from the start of the partition up to the current row

So `SUM(salary) OVER (PARTITION BY department ORDER BY salary DESC)` computes a running sum because the default frame is "from the beginning to the current row."
</think>

Adding ORDER BY to a window function's OVER clause changes the default window frame, which changes the behavior of aggregate functions like SUM.

**The key rule:**

```sql
-- Without ORDER BY: frame is ALL rows in partition
SUM(salary) OVER (PARTITION BY department)
-- Default frame: ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
-- Result: total of entire partition (same value for every row)

-- With ORDER BY: frame is START to CURRENT ROW
SUM(salary) OVER (PARTITION BY department ORDER BY salary DESC)
-- Default frame: RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
-- Result: running total (accumulates as you go down)
```

This is defined by the SQL standard. When ORDER BY is present, the database assumes you want a running/cumulative calculation.

**To get dept_total with ORDER BY (for ranking purposes):**

```sql
SELECT
    employee_id,
    department,
    salary,
    ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) as rank,
    -- Explicitly specify full partition frame:
    SUM(salary) OVER (
        PARTITION BY department
        ORDER BY salary DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) as dept_total,
    -- Running total (uses default frame with ORDER BY):
    SUM(salary) OVER (
        PARTITION BY department
        ORDER BY salary DESC
    ) as running_total
FROM employees;
```

By explicitly specifying `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`, you get the total even with ORDER BY present.

**Common window frame specifications:**

```sql
-- All rows in partition (total):
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING

-- Start to current row (running total):
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW

-- Moving average of 3 rows (1 before, current, 1 after):
ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING

-- Last 7 rows (trailing window):
ROWS BETWEEN 6 PRECEDING AND CURRENT ROW

-- Current row to end (reverse running total):
ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
```

**ROWS vs RANGE:**

```sql
-- ROWS: counts individual rows
ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
-- Includes exactly 2 rows: previous row and current row

-- RANGE: includes all rows with the same ORDER BY value
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
-- If multiple rows have the same salary, they all get the same running total!

-- Example with ties:
-- salary 100000 (row 1): running_total with RANGE = 200000 (includes both 100k rows)
-- salary 100000 (row 2): running_total with RANGE = 200000 (same!)
-- salary 100000 (row 1): running_total with ROWS = 100000 (only this row)
-- salary 100000 (row 2): running_total with ROWS = 200000 (this + previous)
```

**Named windows for readability:**

```sql
SELECT
    employee_id,
    salary,
    ROW_NUMBER() OVER w as rank,
    SUM(salary) OVER (w ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as dept_total,
    SUM(salary) OVER w as running_total
FROM employees
WINDOW w AS (PARTITION BY department ORDER BY salary DESC);
```

**Prevention tips:**
- Always specify the frame explicitly when using ORDER BY with aggregate window functions
- Use ROWS (not RANGE) to avoid surprises with tied values
- Use named windows (WINDOW clause) to avoid repeating complex specifications
- Test window functions with small datasets where you can verify results manually
- Remember: ROW_NUMBER, RANK, DENSE_RANK always require ORDER BY
- Remember: without ORDER BY, aggregate window functions use the full partition'''),

    ("thinking/debugging", r'''Two transactions are deadlocking in our PostgreSQL database:

```
ERROR:  deadlock detected
DETAIL:  Process 1234 waits for ShareLock on transaction 5678;
         blocked by process 5679.
         Process 5679 waits for ShareLock on transaction 1234;
         blocked by process 1234.
HINT:  See server log for query details.

-- Transaction 1 (process 1234):
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;  -- locks row id=1
UPDATE accounts SET balance = balance + 100 WHERE id = 2;  -- waits for row id=2

-- Transaction 2 (process 5679):
BEGIN;
UPDATE accounts SET balance = balance - 50 WHERE id = 2;   -- locks row id=2
UPDATE accounts SET balance = balance + 50 WHERE id = 1;   -- waits for row id=1
```

Classic deadlock from updating rows in different order. How do I prevent this?''', r'''<think>
Same pattern as the threading deadlock earlier but at the database level. Transaction 1 locks row 1 then needs row 2. Transaction 2 locks row 2 then needs row 1. Deadlock.

Fix: consistent ordering of row locks, or use SELECT FOR UPDATE to acquire all locks upfront, or use a single UPDATE statement.
</think>

This is the database equivalent of a threading deadlock. Transaction 1 holds a lock on row 1 and waits for row 2. Transaction 2 holds a lock on row 2 and waits for row 1. PostgreSQL detects this after `deadlock_timeout` (default 1 second) and kills one transaction.

**Fix 1: Consistent lock ordering**

Always update rows in the same order (e.g., by ascending ID):

```sql
-- Transaction 1: transfer from account 1 to account 2
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;  -- lower ID first
UPDATE accounts SET balance = balance + 100 WHERE id = 2;  -- higher ID second
COMMIT;

-- Transaction 2: transfer from account 2 to account 1
BEGIN;
UPDATE accounts SET balance = balance - 50 WHERE id = 1;   -- lower ID first (not 2!)
UPDATE accounts SET balance = balance + 50 WHERE id = 2;   -- higher ID second
COMMIT;
```

In application code:

```python
def transfer(from_id, to_id, amount):
    # Always lock in ascending ID order
    first_id, second_id = sorted([from_id, to_id])

    with db.begin():
        if first_id == from_id:
            db.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, first_id))
            db.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, second_id))
        else:
            db.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, first_id))
            db.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, second_id))
```

**Fix 2: Acquire all locks upfront with SELECT FOR UPDATE**

```sql
BEGIN;
-- Lock both rows at once, in consistent order
SELECT * FROM accounts WHERE id IN (1, 2) ORDER BY id FOR UPDATE;

-- Now safely update both
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
```

`SELECT FOR UPDATE` acquires row-level exclusive locks. By locking both rows in one statement with `ORDER BY`, you ensure consistent ordering.

**Fix 3: Single UPDATE statement**

```sql
BEGIN;
UPDATE accounts SET balance = CASE
    WHEN id = 1 THEN balance - 100
    WHEN id = 2 THEN balance + 100
END
WHERE id IN (1, 2);
COMMIT;
```

A single UPDATE acquires all necessary locks in one operation, eliminating the window for deadlock.

**Fix 4: Advisory locks for application-level ordering**

```sql
BEGIN;
-- Acquire advisory lock based on lower account ID
SELECT pg_advisory_xact_lock(LEAST(1, 2));

UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
-- Advisory lock auto-releases at end of transaction
```

**Detecting and monitoring deadlocks:**

```sql
-- Check for deadlocks in PostgreSQL logs
-- Enable logging:
ALTER SYSTEM SET log_lock_waits = on;
ALTER SYSTEM SET deadlock_timeout = '1s';
SELECT pg_reload_conf();

-- Monitor current locks:
SELECT blocked_locks.pid AS blocked_pid,
       blocking_locks.pid AS blocking_pid,
       blocked_activity.query AS blocked_query,
       blocking_activity.query AS blocking_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_locks blocking_locks
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.relation = blocked_locks.relation
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

**Prevention tips:**
- Establish a consistent lock ordering convention (by primary key, by table name)
- Use `SELECT FOR UPDATE` with ORDER BY to lock multiple rows predictably
- Keep transactions short to minimize the window for conflicts
- Set `lock_timeout` to fail fast: `SET lock_timeout = '5s'`
- Monitor `pg_stat_activity` for long-running transactions holding locks
- Use `NOWAIT` in `SELECT FOR UPDATE NOWAIT` to fail immediately instead of waiting'''),

    ("thinking/debugging", r'''My PostgreSQL query suddenly got 100x slower after a data load. EXPLAIN ANALYZE shows a seq scan instead of index scan:

```sql
EXPLAIN ANALYZE SELECT * FROM orders WHERE status = 'pending' AND created_at > '2024-01-01';

-- Before data load (1M rows):
-- Index Scan using idx_orders_status_created on orders (cost=0.42..8.45 rows=10 width=120)
--   actual time=0.035..0.089 rows=12 loops=1

-- After data load (10M rows):
-- Seq Scan on orders (cost=0.00..385124.00 rows=4500000 width=120)
--   Filter: ((status = 'pending') AND (created_at > '2024-01-01'))
--   actual time=0.031..2145.892 rows=4500123 loops=1
```

The index exists and is valid. Why did the planner switch to a sequential scan?''', r'''<think>
After the data load, the number of matching rows went from 12 to 4,500,123. The planner correctly determined that when you need 45% of the table (4.5M out of 10M), a sequential scan is faster than an index scan.

Index scans are efficient when you need a small fraction of the table (typically < 5-15%). For each row found via the index, PostgreSQL must do a random I/O to fetch the actual row from the heap. Random I/O is much slower than sequential I/O. When you need millions of rows, the accumulated random I/O cost exceeds the cost of just reading the entire table sequentially.

The "fix" is not to force the index -- it is to recognize that the query is correct and either:
1. Accept the seq scan for this data distribution
2. Change the query to be more selective
3. Use a partial index
4. Analyze the table to update statistics
</think>

The PostgreSQL query planner is actually making the **correct decision**. After the data load, 4.5 million out of 10 million rows match the query (45% of the table). For such a large fraction, a sequential scan IS faster than an index scan.

**Why index scan is slower for large result sets:**

```
Index scan: for each of 4.5M rows:
  1. Read index page (sequential within index)
  2. Read data page (RANDOM I/O -- expensive!)
Total: 4.5M random page reads from the heap

Sequential scan:
  1. Read entire table sequentially (much faster I/O pattern)
  2. Filter out non-matching rows
Total: sequential read of ~385K pages
```

Random I/O is 10-100x slower than sequential I/O on spinning disks and 3-5x slower even on SSDs. The crossover point is typically around 5-15% of the table.

**Fix 1: Make the query more selective**

```sql
-- Add more conditions to reduce the result set
SELECT * FROM orders
WHERE status = 'pending'
  AND created_at > '2024-01-01'
  AND created_at < '2024-02-01'  -- narrow the date range
LIMIT 100;
```

**Fix 2: Update statistics after bulk load**

```sql
-- The planner uses statistics to estimate row counts
-- After a large data load, statistics may be stale
ANALYZE orders;

-- Check the statistics:
SELECT tablename, last_analyze, n_live_tup
FROM pg_stat_user_tables WHERE tablename = 'orders';
```

If `last_analyze` is before your data load, the planner might have wrong estimates. Running ANALYZE updates the statistics.

**Fix 3: Use a partial index for common queries**

```sql
-- Index only the rows you commonly query
CREATE INDEX idx_orders_pending ON orders (created_at)
WHERE status = 'pending';

-- This index is much smaller than a full index and will be used
-- even for large result sets of pending orders
```

**Fix 4: Use a covering index to avoid heap access**

```sql
-- Include all needed columns in the index (index-only scan)
CREATE INDEX idx_orders_covering ON orders (status, created_at)
INCLUDE (order_id, customer_id, total);

-- Now PostgreSQL can satisfy the query entirely from the index
-- without reading the heap table
```

**Fix 5: Adjust planner parameters (last resort)**

```sql
-- Lower the random page cost estimate (for SSDs)
SET random_page_cost = 1.1;  -- default is 4.0

-- This makes the planner more willing to use index scans
-- Only do this if your storage is actually SSD
```

**Verify the actual plan is optimal:**

```sql
-- Force index scan and compare actual times
SET enable_seqscan = off;
EXPLAIN ANALYZE SELECT * FROM orders WHERE status = 'pending' AND created_at > '2024-01-01';
-- If this is slower than the seq scan, the planner was right!
SET enable_seqscan = on;
```

**Prevention tips:**
- Run `ANALYZE` after large data loads or before critical queries
- Configure `autovacuum` to run ANALYZE frequently: `autovacuum_analyze_scale_factor = 0.02`
- Use `pg_stat_user_tables` to monitor table statistics freshness
- Set `random_page_cost = 1.1` for SSD storage
- Do not blindly force index scans -- trust the planner unless you have measured evidence
- Use partial indexes for queries that filter on a specific subset of data'''),
]
