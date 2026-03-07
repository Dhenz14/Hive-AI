"""
Code explanation training pairs - Complex SQL (CTEs, window functions, subqueries)
"""

pairs = [
    {
        "instruction": r'''Walk me through this SQL query:

```sql
WITH monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', order_date) AS month,
        SUM(amount) AS revenue
    FROM orders
    WHERE order_date >= '2024-01-01'
    GROUP BY DATE_TRUNC('month', order_date)
),
revenue_with_growth AS (
    SELECT
        month,
        revenue,
        LAG(revenue) OVER (ORDER BY month) AS prev_revenue,
        revenue - LAG(revenue) OVER (ORDER BY month) AS growth,
        ROUND(
            (revenue - LAG(revenue) OVER (ORDER BY month))::numeric
            / NULLIF(LAG(revenue) OVER (ORDER BY month), 0) * 100, 2
        ) AS growth_pct
    FROM monthly_revenue
)
SELECT * FROM revenue_with_growth ORDER BY month;
```''',
        "output": r'''This query calculates month-over-month revenue growth, both in absolute dollars and as a percentage.

**CTE 1 -- `monthly_revenue`:**

Aggregates all orders from 2024 onward into monthly buckets. `DATE_TRUNC('month', order_date)` collapses each date to the first of its month (e.g., 2024-03-15 becomes 2024-03-01). The `SUM(amount)` gives total revenue per month.

**CTE 2 -- `revenue_with_growth`:**

Uses the `LAG` window function to compare each month to the previous one.

- `LAG(revenue) OVER (ORDER BY month)` fetches the revenue from the previous row when ordered by month. For January (the first month), this returns NULL since there is no prior row.

- `growth` is the simple difference: this month minus last month.

- `growth_pct` computes the percentage change. The `::numeric` cast ensures decimal division (not integer division). `NULLIF(..., 0)` prevents division by zero -- if the previous month had zero revenue, the expression returns NULL instead of crashing.

**Key details:**

- The LAG function is called four separate times with the same window. Most databases optimize this into a single pass, but you could also use a named window clause (`WINDOW w AS (ORDER BY month)`) for clarity.

- If a month has zero orders, it will be missing entirely from the results (no row, not a row with revenue=0). To include empty months, you would need to generate a date series and LEFT JOIN against it.

- The final `ORDER BY month` is technically redundant here since the window function already implies ordering, but it makes the intent explicit.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a SQL query with a self-join and window functions for finding gaps in sequences.
</think>

Explain this query -- what problem does it solve?

```sql
SELECT
    island_start,
    MIN(seq_num) AS range_start,
    MAX(seq_num) AS range_end,
    COUNT(*) AS consecutive_count
FROM (
    SELECT
        seq_num,
        seq_num - ROW_NUMBER() OVER (ORDER BY seq_num) AS island_start
    FROM active_sessions
) t
GROUP BY island_start
ORDER BY range_start;
```''',
        "output": r'''<think>
This is the classic "gaps and islands" problem in SQL. The technique uses the difference between the value and row_number to identify consecutive groups.
</think>

This solves the "islands" problem -- finding groups of consecutive numbers in a sequence that may have gaps.

**The trick explained:**

The subquery computes `seq_num - ROW_NUMBER()` for each row. Here is why this works:

Imagine you have seq_nums: 1, 2, 3, 7, 8, 12.

| seq_num | ROW_NUMBER | difference |
|---------|------------|------------|
| 1       | 1          | 0          |
| 2       | 2          | 0          |
| 3       | 3          | 0          |
| 7       | 4          | 3          |
| 8       | 5          | 3          |
| 12      | 6          | 6          |

Within a group of consecutive numbers, ROW_NUMBER increases at the same rate as seq_num, so the difference stays constant. When there is a gap, seq_num jumps but ROW_NUMBER does not, producing a new difference value.

**The outer query** groups by this difference (called `island_start`) and reports each island's range and size. For the example above:
- Island 0: range 1-3, count 3
- Island 3: range 7-8, count 2
- Island 6: range 12-12, count 1

**Important assumption:** This only works correctly if `seq_num` values are unique. Duplicate values would break the pattern because ROW_NUMBER would still increment but seq_num would not.

**The name `island_start` is misleading** -- it is not actually the start of the island, just an identifier that is constant within each consecutive group. The real start is `MIN(seq_num)`.'''
    },
    {
        "instruction": r'''What does this query do?

```sql
SELECT
    d.department_name,
    e.employee_name,
    e.salary,
    RANK() OVER (PARTITION BY d.department_id ORDER BY e.salary DESC) AS salary_rank,
    e.salary - AVG(e.salary) OVER (PARTITION BY d.department_id) AS diff_from_avg,
    SUM(e.salary) OVER (
        PARTITION BY d.department_id
        ORDER BY e.salary DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM employees e
JOIN departments d ON e.department_id = d.department_id
WHERE e.active = true
QUALIFY salary_rank <= 5;
```''',
        "output": r'''This query finds the top 5 highest-paid active employees in each department, along with several analytical metrics.

**The window functions:**

1. **RANK()**: Assigns rank 1 to the highest salary in each department, 2 to the next, etc. `PARTITION BY department_id` restarts ranking for each department. If two employees have the same salary, they get the same rank, and the next rank is skipped (1, 1, 3 -- not 1, 1, 2). Use `DENSE_RANK` if you want no gaps.

2. **diff_from_avg**: Calculates how far each employee's salary is from their department's average. The `AVG` window has no ORDER BY, so it computes the average over the entire partition (all employees in the department), not a running average.

3. **running_total**: A cumulative sum of salaries within each department, ordered from highest to lowest. `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` means "sum from the first row in the partition up to and including the current row."

**The QUALIFY clause:**

`QUALIFY` is a Snowflake/BigQuery/DuckDB extension (not standard SQL everywhere). It filters on window function results the same way `HAVING` filters on aggregates. Here it keeps only employees ranked 5 or better per department.

In databases without QUALIFY, you would wrap the query in a subquery and filter with `WHERE salary_rank <= 5` in the outer query.

**Note:** Since RANK is used (not ROW_NUMBER), ties could result in more than 5 employees per department. If exactly 5 rows are needed, use ROW_NUMBER instead.'''
    },
    {
        "instruction": r'''Explain this recursive CTE:

```sql
WITH RECURSIVE org_tree AS (
    SELECT
        id,
        name,
        manager_id,
        1 AS depth,
        ARRAY[name] AS path
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    SELECT
        e.id,
        e.name,
        e.manager_id,
        ot.depth + 1,
        ot.path || e.name
    FROM employees e
    JOIN org_tree ot ON e.manager_id = ot.id
)
SELECT
    REPEAT('  ', depth - 1) || name AS org_chart,
    depth,
    path
FROM org_tree
ORDER BY path;
```''',
        "output": r'''This builds a complete organizational hierarchy tree using a recursive Common Table Expression (CTE).

**The anchor member (first SELECT):**

Finds the root node(s) -- employees with no manager (`manager_id IS NULL`). These are typically the CEO or top-level executives. Each starts at depth 1 with a path array containing just their name.

**The recursive member (second SELECT):**

Joins the `employees` table against the results accumulated so far in `org_tree`. For each employee whose `manager_id` matches an already-found node's `id`, it adds them to the result set with:
- `depth + 1` -- one level deeper than their manager
- `path || e.name` -- appends their name to the manager's path array

This repeats until no new employees are found (no more manager_id matches).

**The final SELECT:**

- `REPEAT('  ', depth - 1) || name` creates an indented display. The CEO gets zero spaces, their reports get two spaces, their reports' reports get four, etc.
- `ORDER BY path` sorts the output so the tree reads naturally. Since the path array is sorted lexicographically, each subtree is grouped together.

**Example output might look like:**
```
Alice
  Bob
    Dave
    Eve
  Carol
    Frank
```

**Cycle risk:** If the data has a cycle (A manages B manages A), this query will recurse infinitely. PostgreSQL lets you add `CYCLE id SET is_cycle USING path` to detect and stop cycles. Without it, you would hit the recursion limit.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a query that uses multiple subqueries and conditional aggregation. Let me trace through it carefully.
</think>

What does this query compute?

```sql
SELECT
    p.product_name,
    COUNT(DISTINCT o.customer_id) AS unique_buyers,
    SUM(CASE WHEN o.order_date >= CURRENT_DATE - INTERVAL '30 days'
        THEN oi.quantity ELSE 0 END) AS units_last_30d,
    SUM(CASE WHEN o.order_date >= CURRENT_DATE - INTERVAL '90 days'
        THEN oi.quantity ELSE 0 END) AS units_last_90d,
    COALESCE(
        SUM(oi.quantity * oi.unit_price)
        FILTER (WHERE o.status != 'cancelled'),
        0
    ) AS net_revenue
FROM products p
LEFT JOIN order_items oi ON p.id = oi.product_id
LEFT JOIN orders o ON oi.order_id = o.id
GROUP BY p.product_name
HAVING COUNT(DISTINCT o.customer_id) >= 10
ORDER BY net_revenue DESC;
```''',
        "output": r'''<think>
This is a product performance report combining conditional aggregation with FILTER clause. Let me explain each metric.
</think>

This is a product performance report showing sales metrics for products that have at least 10 unique buyers.

**The joins:**

LEFT JOINs ensure products with zero sales still appear in the results (though the HAVING clause will filter them out). The join path is products -> order_items -> orders.

**Each metric explained:**

1. **unique_buyers**: `COUNT(DISTINCT o.customer_id)` counts how many different customers bought this product across all time.

2. **units_last_30d**: Uses conditional aggregation (CASE inside SUM) to count only quantities from orders in the last 30 days. Orders outside that window contribute 0 to the sum.

3. **units_last_90d**: Same pattern but for 90 days. Note this INCLUDES the last 30 days -- it is not "30-90 days ago."

4. **net_revenue**: `SUM(quantity * unit_price)` but only for non-cancelled orders. The `FILTER (WHERE ...)` clause is PostgreSQL-specific syntax that is cleaner than the CASE approach. `COALESCE(..., 0)` converts NULL (from products with no qualifying orders) to 0.

**The HAVING clause** filters out products with fewer than 10 unique buyers, keeping only well-established products in the report.

**Potential issues:**

- The LEFT JOIN becomes effectively an INNER JOIN due to `HAVING COUNT >= 10` -- products with no orders have 0 unique buyers and get filtered.
- The CASE-based date filters do not exclude cancelled orders, but `net_revenue` does. This inconsistency means `units_last_30d` includes cancelled order quantities while revenue does not.
- If `unit_price` varies over time (price changes), the revenue reflects the actual price paid per order, not the current price.'''
    },
]
