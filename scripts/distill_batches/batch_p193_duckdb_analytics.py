"""DuckDB embedded analytics — query patterns, file formats, Python integration, and extensions."""

PAIRS = [
    (
        "databases/duckdb-query-patterns",
        "Show DuckDB advanced query patterns: window functions, CTEs, pivots, and analytical SQL.",
        '''DuckDB advanced analytical query patterns:

```sql
-- === Window functions for analytics ===

-- 1. Running totals and moving averages
SELECT
    order_date,
    product_category,
    daily_revenue,
    -- Running total within each category
    SUM(daily_revenue) OVER (
        PARTITION BY product_category
        ORDER BY order_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue,
    -- 7-day moving average
    AVG(daily_revenue) OVER (
        PARTITION BY product_category
        ORDER BY order_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7d,
    -- Percent of category total
    daily_revenue / SUM(daily_revenue) OVER (
        PARTITION BY product_category
    ) * 100 AS pct_of_total
FROM daily_sales
ORDER BY product_category, order_date;


-- 2. Ranking and top-N per group
SELECT *
FROM (
    SELECT
        department,
        employee_name,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department ORDER BY salary DESC
        ) AS rank_in_dept,
        NTILE(4) OVER (
            ORDER BY salary DESC
        ) AS salary_quartile,
        salary - LAG(salary) OVER (
            PARTITION BY department ORDER BY salary
        ) AS gap_to_prev
    FROM employees
)
WHERE rank_in_dept <= 3;  -- Top 3 per department


-- 3. Session analysis with window functions
WITH session_gaps AS (
    SELECT
        user_id,
        event_time,
        event_type,
        -- Time since last event
        event_time - LAG(event_time) OVER (
            PARTITION BY user_id ORDER BY event_time
        ) AS time_since_last,
        -- New session if gap > 30 minutes
        CASE WHEN event_time - LAG(event_time) OVER (
            PARTITION BY user_id ORDER BY event_time
        ) > INTERVAL '30 minutes' OR LAG(event_time) OVER (
            PARTITION BY user_id ORDER BY event_time
        ) IS NULL
        THEN 1 ELSE 0 END AS new_session
    FROM events
),
sessions AS (
    SELECT
        *,
        SUM(new_session) OVER (
            PARTITION BY user_id ORDER BY event_time
        ) AS session_id
    FROM session_gaps
)
SELECT
    user_id,
    session_id,
    MIN(event_time) AS session_start,
    MAX(event_time) AS session_end,
    COUNT(*) AS events_in_session,
    MAX(event_time) - MIN(event_time) AS session_duration
FROM sessions
GROUP BY user_id, session_id;


-- === Recursive CTEs ===

-- Org chart hierarchy traversal
WITH RECURSIVE org_tree AS (
    -- Base: CEO (no manager)
    SELECT
        employee_id, name, manager_id, title,
        0 AS depth,
        name AS path
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive: add reports
    SELECT
        e.employee_id, e.name, e.manager_id, e.title,
        t.depth + 1,
        t.path || ' > ' || e.name
    FROM employees e
    JOIN org_tree t ON e.manager_id = t.employee_id
)
SELECT * FROM org_tree ORDER BY path;
```

```sql
-- === PIVOT and UNPIVOT ===

-- PIVOT: rows to columns (DuckDB native syntax)
PIVOT monthly_sales
ON month
USING SUM(revenue)
GROUP BY product;
-- Result:
-- | product  | Jan   | Feb   | Mar   | ...
-- | Widget A | 15000 | 18000 | 22000 | ...
-- | Widget B | 8000  | 9500  | 11000 | ...


-- Dynamic PIVOT with all months
PIVOT monthly_sales
ON month IN ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
             'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
USING SUM(revenue) AS rev, COUNT(*) AS orders
GROUP BY product;


-- UNPIVOT: columns to rows
UNPIVOT quarterly_report
ON Q1, Q2, Q3, Q4
INTO NAME quarter VALUE revenue;


-- === QUALIFY clause (filter window functions directly) ===

-- Get latest record per user (no subquery needed!)
SELECT user_id, email, updated_at
FROM users
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY user_id ORDER BY updated_at DESC
) = 1;


-- === SAMPLE and TABLESAMPLE ===

-- Random 10% sample for exploration
SELECT * FROM large_table USING SAMPLE 10%;

-- Reservoir sampling (exact N rows)
SELECT * FROM large_table USING SAMPLE 1000 ROWS;

-- Bernoulli sampling (each row has p% chance)
SELECT * FROM large_table TABLESAMPLE BERNOULLI(5);


-- === List and struct operations (nested data) ===

-- Create and query nested structures
SELECT
    user_id,
    LIST(event_type) AS all_events,
    LIST(event_type ORDER BY event_time) AS ordered_events,
    LIST_DISTINCT(event_type) AS unique_events,
    LEN(LIST_DISTINCT(event_type)) AS distinct_event_count,
    -- Struct creation
    {'name': user_name, 'email': user_email} AS user_info,
    -- Array slicing
    ordered_events[1:3] AS first_3_events,
    -- Array aggregation with filter
    LIST(event_type) FILTER (WHERE revenue > 0) AS revenue_events
FROM events
GROUP BY user_id, user_name, user_email;


-- Unnest arrays
SELECT
    user_id,
    UNNEST(tags) AS tag
FROM user_profiles;
```

```python
# --- DuckDB Python API for analytical queries ---

import duckdb
from typing import Any


def analytical_query_examples(db_path: str = ":memory:") -> None:
    """DuckDB analytical query patterns in Python."""
    con = duckdb.connect(db_path)

    # Create sample data
    con.execute("""
        CREATE TABLE sales AS
        SELECT
            date '2024-01-01' + INTERVAL (i % 365) DAY AS sale_date,
            'Product_' || (i % 20)::VARCHAR AS product,
            ['Electronics', 'Books', 'Clothing', 'Food'][1 + (i % 4)] AS category,
            (random() * 500 + 10)::DECIMAL(10,2) AS amount,
            (random() * 10 + 1)::INT AS quantity
        FROM generate_series(1, 100000) AS t(i)
    """)

    # Cohort analysis with window functions
    result = con.execute("""
        WITH first_purchase AS (
            SELECT
                product,
                MIN(sale_date) AS cohort_month
            FROM sales
            GROUP BY product
        ),
        monthly_revenue AS (
            SELECT
                s.product,
                DATE_TRUNC('month', s.sale_date) AS month,
                SUM(s.amount) AS revenue,
                fp.cohort_month
            FROM sales s
            JOIN first_purchase fp ON s.product = fp.product
            GROUP BY s.product, month, fp.cohort_month
        )
        SELECT
            cohort_month,
            DATE_DIFF('month', cohort_month, month) AS months_since_first,
            COUNT(DISTINCT product) AS products,
            SUM(revenue) AS total_revenue,
            AVG(revenue) AS avg_revenue_per_product
        FROM monthly_revenue
        GROUP BY cohort_month, months_since_first
        ORDER BY cohort_month, months_since_first
    """).fetchall()

    # Percentile analysis
    percentiles = con.execute("""
        SELECT
            category,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY amount) AS p25,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY amount) AS median,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY amount) AS p75,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY amount) AS p95,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY amount) AS p99
        FROM sales
        GROUP BY category
        ORDER BY median DESC
    """).fetchdf()  # Returns pandas DataFrame

    print(percentiles)


def grouping_sets_example(con: duckdb.DuckDBPyConnection) -> None:
    """GROUPING SETS, CUBE, and ROLLUP for multi-level aggregation."""
    result = con.execute("""
        -- GROUPING SETS: multiple aggregation levels in one query
        SELECT
            COALESCE(category, 'ALL') AS category,
            COALESCE(product, 'ALL') AS product,
            SUM(amount) AS total_revenue,
            COUNT(*) AS order_count,
            GROUPING(category, product) AS grouping_level
        FROM sales
        GROUP BY GROUPING SETS (
            (),                     -- Grand total
            (category),             -- Per category
            (category, product)     -- Per category + product
        )
        ORDER BY grouping_level DESC, total_revenue DESC
    """).fetchall()

    return result
```

Key DuckDB query patterns:

| Feature | Syntax | Use Case |
|---|---|---|
| Window functions | OVER (PARTITION BY ... ORDER BY ...) | Running totals, rankings, gaps |
| QUALIFY | QUALIFY ROW_NUMBER() OVER (...) = 1 | Filter window results directly |
| PIVOT/UNPIVOT | PIVOT table ON col USING AGG | Row-to-column transformation |
| SAMPLE | USING SAMPLE 10% | Fast data exploration |
| LIST/STRUCT | LIST(col), {key: val} | Nested data aggregation |
| GROUPING SETS | GROUP BY GROUPING SETS ((), (a), (a,b)) | Multi-level rollups |

1. **QUALIFY replaces subqueries** -- filter window functions inline, cleaner SQL
2. **PIVOT is native** -- no CASE WHEN gymnastics needed for row-to-column
3. **LIST aggregation** -- collect values into arrays with ordering and filtering
4. **SAMPLE for exploration** -- percentage or exact row count sampling built in
5. **GROUPING SETS** -- compute grand totals, subtotals, and details in one pass'''
    ),
    (
        "databases/duckdb-file-formats",
        "Show DuckDB reading Parquet, CSV, and JSON files directly without loading into tables.",
        '''DuckDB querying files directly without ETL:

```python
# --- Reading Parquet files ---

import duckdb
from pathlib import Path
from typing import Any


def query_parquet_files(data_dir: str) -> None:
    """Query Parquet files directly without loading into tables.

    DuckDB reads Parquet with:
      - Predicate pushdown (skip row groups)
      - Column pruning (read only needed columns)
      - Automatic schema detection
      - Glob patterns for multiple files
      - Hive partitioning support
    """
    con = duckdb.connect()

    # Single file query
    result = con.execute("""
        SELECT
            product_category,
            COUNT(*) AS order_count,
            SUM(revenue) AS total_revenue,
            AVG(revenue) AS avg_revenue
        FROM 'data/orders/2024/*.parquet'
        WHERE order_date >= '2024-06-01'
          AND status = 'completed'
        GROUP BY product_category
        ORDER BY total_revenue DESC
    """).fetchdf()
    print(result)

    # Glob pattern: all parquet files in nested directories
    result = con.execute("""
        SELECT *
        FROM 'data/events/**/*.parquet'
        WHERE event_time >= CURRENT_DATE - INTERVAL 7 DAY
        LIMIT 1000
    """).fetchdf()

    # Hive-partitioned Parquet (directories like year=2024/month=01/)
    result = con.execute("""
        SELECT *
        FROM read_parquet(
            'data/partitioned/**/*.parquet',
            hive_partitioning = true
        )
        WHERE year = 2024 AND month = 6
    """).fetchdf()

    # Parquet metadata inspection
    metadata = con.execute("""
        SELECT *
        FROM parquet_metadata('data/orders/2024/jan.parquet')
    """).fetchdf()
    print("Row groups:", metadata)

    schema = con.execute("""
        SELECT *
        FROM parquet_schema('data/orders/2024/jan.parquet')
    """).fetchdf()
    print("Schema:", schema)
```

```python
# --- Reading CSV and JSON ---

def query_csv_files(con: duckdb.DuckDBPyConnection) -> None:
    """Query CSV files with auto-detection and options."""

    # Auto-detect delimiter, header, types
    result = con.execute("""
        SELECT *
        FROM 'data/users.csv'
        LIMIT 10
    """).fetchdf()

    # Explicit CSV options
    result = con.execute("""
        SELECT *
        FROM read_csv(
            'data/legacy_export.csv',
            delim = '|',
            header = true,
            columns = {
                'id': 'INTEGER',
                'name': 'VARCHAR',
                'amount': 'DECIMAL(10,2)',
                'created_at': 'TIMESTAMP'
            },
            dateformat = '%m/%d/%Y',
            null_padding = true,
            ignore_errors = true,    -- Skip malformed rows
            max_line_size = 1048576  -- 1MB max line
        )
        WHERE amount > 100
    """).fetchdf()

    # Multiple CSV files with glob
    result = con.execute("""
        SELECT
            filename AS source_file,
            COUNT(*) AS row_count,
            SUM(amount) AS total
        FROM read_csv('data/reports/*.csv', filename = true)
        GROUP BY source_file
    """).fetchdf()


def query_json_files(con: duckdb.DuckDBPyConnection) -> None:
    """Query JSON and NDJSON (newline-delimited JSON) files."""

    # NDJSON: one JSON object per line
    result = con.execute("""
        SELECT
            json_extract_string(data, '$.user.name') AS user_name,
            json_extract(data, '$.event.type') AS event_type,
            json_extract(data, '$.metrics.duration_ms')::INTEGER AS duration
        FROM read_json(
            'data/events.jsonl',
            format = 'newline_delimited',
            columns = {'data': 'JSON'}
        )
        WHERE duration > 1000
    """).fetchdf()

    # Auto-detect JSON structure
    result = con.execute("""
        SELECT *
        FROM read_json_auto('data/api_response.json')
    """).fetchdf()

    # Nested JSON with struct access
    result = con.execute("""
        SELECT
            id,
            metadata->>'$.name' AS name,
            metadata->>'$.tags[0]' AS first_tag,
            LEN(json_extract(metadata, '$.tags')) AS tag_count
        FROM read_json_auto('data/products.json')
    """).fetchdf()
```

```python
# --- Writing results to files ---

def export_results(con: duckdb.DuckDBPyConnection) -> None:
    """Export query results to various file formats."""

    # Write to Parquet (with compression)
    con.execute("""
        COPY (
            SELECT
                user_id,
                DATE_TRUNC('month', order_date) AS month,
                SUM(revenue) AS monthly_revenue,
                COUNT(*) AS order_count
            FROM 'data/orders/**/*.parquet'
            GROUP BY user_id, month
        )
        TO 'output/monthly_summary.parquet'
        (FORMAT PARQUET, COMPRESSION 'zstd', ROW_GROUP_SIZE 100000)
    """)

    # Write to partitioned Parquet
    con.execute("""
        COPY (
            SELECT * FROM 'data/events/**/*.parquet'
            WHERE event_date >= '2024-01-01'
        )
        TO 'output/events_partitioned'
        (FORMAT PARQUET, PARTITION_BY (year, month), COMPRESSION 'snappy')
    """)

    # Write to CSV
    con.execute("""
        COPY (SELECT * FROM 'data/summary.parquet')
        TO 'output/report.csv'
        (FORMAT CSV, HEADER true, DELIMITER ',')
    """)

    # Write to JSON
    con.execute("""
        COPY (SELECT * FROM 'data/summary.parquet' LIMIT 100)
        TO 'output/sample.json'
        (FORMAT JSON, ARRAY true)
    """)


def file_format_conversion(con: duckdb.DuckDBPyConnection) -> None:
    """Convert between file formats using DuckDB as ETL."""

    # CSV to Parquet (with type coercion)
    con.execute("""
        COPY (
            SELECT
                CAST(id AS INTEGER) AS id,
                name,
                CAST(amount AS DECIMAL(10,2)) AS amount,
                CAST(created_at AS TIMESTAMP) AS created_at
            FROM 'data/legacy.csv'
        )
        TO 'data/converted.parquet'
        (FORMAT PARQUET, COMPRESSION 'zstd')
    """)

    # Multiple CSVs to single Parquet
    con.execute("""
        COPY (
            SELECT * FROM read_csv('data/monthly_reports/*.csv')
        )
        TO 'data/all_reports.parquet'
        (FORMAT PARQUET)
    """)
```

Key DuckDB file access patterns:

| Format | Function | Key Features |
|---|---|---|
| Parquet | read_parquet() / glob | Predicate pushdown, column pruning, Hive partitioning |
| CSV | read_csv() / read_csv_auto() | Auto-detect delimiter/types, multi-file glob |
| JSON | read_json() / read_json_auto() | NDJSON, nested access, struct extraction |
| Export | COPY ... TO | Parquet/CSV/JSON with compression, partitioning |

1. **Query files directly** -- no ETL, no loading step, just point at files
2. **Predicate pushdown** -- Parquet row groups skipped when filters apply
3. **Glob patterns** -- query entire directory trees with **/*.parquet
4. **Hive partitioning** -- automatically parse year=2024/month=01 directories
5. **Format conversion** -- use DuckDB as a zero-config ETL tool between formats'''
    ),
    (
        "databases/duckdb-python-integration",
        "Demonstrate DuckDB Python integration: pandas and polars interop, in-process analytics.",
        '''DuckDB Python integration with pandas and polars:

```python
# --- DuckDB + pandas integration ---

import duckdb
import pandas as pd
import numpy as np
from typing import Any
from datetime import datetime, timedelta


def pandas_interop_examples() -> None:
    """Query pandas DataFrames directly with SQL — zero copy."""

    # Create pandas DataFrame
    df = pd.DataFrame({
        "user_id": np.random.randint(1, 1000, 100000),
        "event_type": np.random.choice(
            ["page_view", "click", "purchase", "signup"], 100000
        ),
        "amount": np.random.exponential(50, 100000).round(2),
        "timestamp": pd.date_range("2024-01-01", periods=100000, freq="min"),
    })

    # Query the DataFrame directly — no loading!
    # DuckDB detects Python variables as virtual tables
    result = duckdb.sql("""
        SELECT
            event_type,
            COUNT(*) AS count,
            ROUND(AVG(amount), 2) AS avg_amount,
            ROUND(SUM(amount), 2) AS total_amount,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP
                  (ORDER BY amount), 2) AS p95_amount
        FROM df
        GROUP BY event_type
        ORDER BY total_amount DESC
    """).df()  # .df() returns pandas DataFrame

    print(result)


def join_dataframes_with_files() -> None:
    """Join pandas DataFrames with Parquet files."""
    # In-memory customer data
    customers = pd.DataFrame({
        "customer_id": range(1, 1001),
        "segment": np.random.choice(["enterprise", "smb", "startup"], 1000),
        "region": np.random.choice(["US", "EU", "APAC"], 1000),
    })

    # Query: join in-memory DF with on-disk Parquet
    result = duckdb.sql("""
        SELECT
            c.segment,
            c.region,
            COUNT(*) AS order_count,
            SUM(o.revenue) AS total_revenue,
            AVG(o.revenue) AS avg_order_value
        FROM customers c
        JOIN 'data/orders/*.parquet' o
            ON c.customer_id = o.customer_id
        WHERE o.order_date >= '2024-01-01'
        GROUP BY c.segment, c.region
        ORDER BY total_revenue DESC
    """).df()

    print(result)


def replace_pandas_operations() -> None:
    """Use DuckDB SQL instead of slow pandas operations."""
    sales = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=365, freq="D").repeat(100),
        "store_id": list(range(1, 101)) * 365,
        "revenue": np.random.exponential(1000, 36500).round(2),
        "units": np.random.poisson(50, 36500),
    })

    # Pandas way (slow for large data):
    # result = sales.groupby(['store_id', pd.Grouper(key='date', freq='M')]).agg(...)

    # DuckDB way (10-100x faster):
    result = duckdb.sql("""
        SELECT
            store_id,
            DATE_TRUNC('month', date) AS month,
            SUM(revenue) AS monthly_revenue,
            SUM(units) AS monthly_units,
            -- Running total per store
            SUM(SUM(revenue)) OVER (
                PARTITION BY store_id
                ORDER BY DATE_TRUNC('month', date)
            ) AS cumulative_revenue,
            -- Month-over-month growth
            SUM(revenue) / LAG(SUM(revenue)) OVER (
                PARTITION BY store_id
                ORDER BY DATE_TRUNC('month', date)
            ) - 1 AS mom_growth
        FROM sales
        GROUP BY store_id, month
        QUALIFY cumulative_revenue > 5000
        ORDER BY store_id, month
    """).df()

    print(result)
```

```python
# --- DuckDB + polars integration ---

import polars as pl


def polars_interop_examples() -> None:
    """DuckDB with polars DataFrames — Apache Arrow zero-copy."""

    # Create polars DataFrame
    lf = pl.LazyFrame({
        "user_id": range(1, 100001),
        "category": ["A", "B", "C", "D"] * 25000,
        "score": [float(i % 100) for i in range(100000)],
        "active": [i % 3 != 0 for i in range(100000)],
    })

    df_polars = lf.collect()

    # Query polars DataFrame with DuckDB SQL
    result = duckdb.sql("""
        SELECT
            category,
            COUNT(*) FILTER (WHERE active) AS active_count,
            COUNT(*) FILTER (WHERE NOT active) AS inactive_count,
            AVG(score) AS avg_score,
            STDDEV(score) AS std_score
        FROM df_polars
        GROUP BY category
        ORDER BY category
    """).pl()  # .pl() returns polars DataFrame

    print(result)


def arrow_interop() -> None:
    """DuckDB with Apache Arrow for zero-copy data exchange."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Read Parquet to Arrow table
    arrow_table = pq.read_table("data/events.parquet")

    # Query Arrow table with DuckDB (zero-copy!)
    result = duckdb.sql("""
        SELECT
            event_type,
            COUNT(*) AS count,
            AVG(duration_ms) AS avg_duration
        FROM arrow_table
        GROUP BY event_type
    """).arrow()  # .arrow() returns Arrow table

    # Write result back to Parquet
    pq.write_table(result, "output/summary.parquet")


def persistent_database_example() -> None:
    """Use DuckDB as a persistent analytical database."""
    # Persistent database (file-backed)
    con = duckdb.connect("analytics.duckdb")

    # Create tables from files
    con.execute("""
        CREATE TABLE IF NOT EXISTS events AS
        SELECT * FROM read_parquet('data/events/**/*.parquet');
    """)

    # Create views for common queries
    con.execute("""
        CREATE OR REPLACE VIEW daily_metrics AS
        SELECT
            DATE_TRUNC('day', event_time) AS day,
            event_type,
            COUNT(*) AS events,
            COUNT(DISTINCT user_id) AS unique_users,
            AVG(duration_ms) AS avg_duration
        FROM events
        GROUP BY day, event_type;
    """)

    # Query the persistent database
    result = con.execute("""
        SELECT * FROM daily_metrics
        WHERE day >= CURRENT_DATE - INTERVAL 30 DAY
        ORDER BY day DESC, events DESC
    """).df()

    con.close()
```

```python
# --- DuckDB as pandas/polars accelerator ---

class DuckDBAccelerator:
    """Use DuckDB to accelerate DataFrame operations.

    DuckDB is 10-100x faster than pandas for:
      - GROUP BY aggregations
      - Window functions
      - JOINs on large DataFrames
      - Filtered aggregations
      - Sorting large datasets
    """

    def __init__(self, db_path: str = ":memory:"):
        self.con = duckdb.connect(db_path)

    def fast_groupby(
        self,
        df: pd.DataFrame,
        group_cols: list[str],
        agg_dict: dict[str, str],
    ) -> pd.DataFrame:
        """Fast GROUP BY using DuckDB instead of pandas."""
        agg_expressions = [
            f"{func}({col}) AS {col}_{func}"
            for col, func in agg_dict.items()
        ]
        group_str = ", ".join(group_cols)
        agg_str = ", ".join(agg_expressions)

        return self.con.execute(f"""
            SELECT {group_str}, {agg_str}
            FROM df
            GROUP BY {group_str}
        """).df()

    def fast_join(
        self,
        left: pd.DataFrame,
        right: pd.DataFrame,
        on: str,
        how: str = "INNER",
    ) -> pd.DataFrame:
        """Fast JOIN using DuckDB instead of pandas merge."""
        return self.con.execute(f"""
            SELECT l.*, r.*
            FROM left l
            {how} JOIN right r ON l.{on} = r.{on}
        """).df()

    def fast_window(
        self,
        df: pd.DataFrame,
        partition_by: str,
        order_by: str,
        window_func: str,
        result_col: str,
    ) -> pd.DataFrame:
        """Fast window function using DuckDB."""
        return self.con.execute(f"""
            SELECT *,
                {window_func} OVER (
                    PARTITION BY {partition_by}
                    ORDER BY {order_by}
                ) AS {result_col}
            FROM df
        """).df()

    def close(self) -> None:
        self.con.close()
```

Key DuckDB Python integration patterns:

| Feature | Method | Returns |
|---|---|---|
| Query pandas DF | duckdb.sql("SELECT * FROM df") | Relation object |
| Return pandas | .df() | pd.DataFrame |
| Return polars | .pl() | pl.DataFrame |
| Return Arrow | .arrow() | pa.Table |
| Query files | FROM 'path/*.parquet' | Zero-ETL file access |
| Persistent DB | duckdb.connect("file.duckdb") | File-backed storage |

1. **Zero-copy from pandas** -- DuckDB reads DataFrames directly, no serialization
2. **10-100x faster than pandas** -- for GROUP BY, JOINs, window functions
3. **Mix DataFrames with files** -- JOIN in-memory DFs with on-disk Parquet
4. **Polars via Arrow** -- zero-copy exchange through Apache Arrow
5. **Persistent databases** -- file-backed DuckDB for repeatable analytics'''
    ),
    (
        "databases/duckdb-extensions",
        "Show DuckDB extensions and remote queries: S3, HTTP, spatial, and community extensions.",
        '''DuckDB extensions for remote data access and specialized queries:

```python
# --- DuckDB extensions and S3 access ---

import duckdb
from typing import Any


def setup_extensions(con: duckdb.DuckDBPyConnection) -> None:
    """Install and load DuckDB extensions.

    Core extensions:
      httpfs     — HTTP/S3/GCS/Azure file access
      json       — JSON processing functions
      parquet    — Parquet reader/writer (built-in)
      spatial    — Geospatial functions (ST_*)
      fts        — Full-text search
      icu        — International Components for Unicode
      tpch       — TPC-H benchmark data generator
      substrait  — Cross-system query plan format
    """
    # Install and load extensions
    extensions = ["httpfs", "json", "spatial", "fts", "icu"]
    for ext in extensions:
        con.execute(f"INSTALL {ext};")
        con.execute(f"LOAD {ext};")
        print(f"Loaded extension: {ext}")


def configure_s3_access(
    con: duckdb.DuckDBPyConnection,
    region: str = "us-east-1",
    access_key: str | None = None,
    secret_key: str | None = None,
    endpoint: str | None = None,
) -> None:
    """Configure S3 access for remote Parquet queries.

    Supports:
      - AWS S3
      - S3-compatible (MinIO, Cloudflare R2, DigitalOcean Spaces)
      - Google Cloud Storage (gs://)
      - Azure Blob Storage (az://)
    """
    con.execute(f"SET s3_region = '{region}';")

    if access_key and secret_key:
        con.execute(f"SET s3_access_key_id = '{access_key}';")
        con.execute(f"SET s3_secret_access_key = '{secret_key}';")
    else:
        # Use IAM role / instance profile
        con.execute("SET s3_use_ssl = true;")

    if endpoint:
        # S3-compatible endpoint (MinIO, R2, etc.)
        con.execute(f"SET s3_endpoint = '{endpoint}';")
        con.execute("SET s3_url_style = 'path';")


def query_s3_data(con: duckdb.DuckDBPyConnection) -> None:
    """Query Parquet files directly from S3."""

    # Query single S3 file
    result = con.execute("""
        SELECT
            product_category,
            COUNT(*) AS orders,
            SUM(revenue) AS total_revenue
        FROM 's3://my-data-lake/orders/2024/*.parquet'
        WHERE order_date >= '2024-06-01'
        GROUP BY product_category
        ORDER BY total_revenue DESC
    """).df()
    print(result)

    # Hive-partitioned data on S3
    result = con.execute("""
        SELECT *
        FROM read_parquet(
            's3://my-data-lake/events/year=*/month=*/*.parquet',
            hive_partitioning = true
        )
        WHERE year = 2024 AND month >= 6
        LIMIT 1000
    """).df()

    # Query public datasets (no auth needed)
    result = con.execute("""
        SELECT *
        FROM 's3://aws-public-datasets/some-dataset/*.parquet'
        LIMIT 100
    """).df()
```

```python
# --- HTTP and remote queries ---

def query_http_sources(con: duckdb.DuckDBPyConnection) -> None:
    """Query files over HTTP/HTTPS directly."""

    # Read CSV from URL
    result = con.execute("""
        SELECT *
        FROM read_csv_auto(
            'https://raw.githubusercontent.com/datasets/co2/master/data/co2-mm-mlo.csv'
        )
        WHERE Year >= 2020
        ORDER BY "Date" DESC
        LIMIT 20
    """).df()
    print(result)

    # Read Parquet from HTTP
    result = con.execute("""
        SELECT *
        FROM read_parquet(
            'https://example.com/data/public_dataset.parquet'
        )
        LIMIT 100
    """).df()

    # Query a REST API JSON response
    result = con.execute("""
        SELECT
            json_extract_string(data, '$.name') AS name,
            json_extract(data, '$.stargazers_count')::INTEGER AS stars
        FROM read_json_auto(
            'https://api.github.com/orgs/duckdb/repos'
        )
        ORDER BY stars DESC
    """).df()


def attach_external_databases(con: duckdb.DuckDBPyConnection) -> None:
    """Attach external databases (PostgreSQL, MySQL, SQLite)."""

    # Attach PostgreSQL
    con.execute("INSTALL postgres;")
    con.execute("LOAD postgres;")
    con.execute("""
        ATTACH 'dbname=mydb user=postgres host=localhost'
        AS pg_db (TYPE POSTGRES, READ_ONLY);
    """)

    # Query PostgreSQL tables with DuckDB SQL
    result = con.execute("""
        SELECT
            p.product_name,
            COUNT(*) AS order_count,
            SUM(o.amount) AS total_revenue
        FROM pg_db.products p
        JOIN pg_db.orders o ON p.id = o.product_id
        GROUP BY p.product_name
        ORDER BY total_revenue DESC
        LIMIT 20
    """).df()

    # Attach SQLite database
    con.execute("INSTALL sqlite;")
    con.execute("LOAD sqlite;")
    con.execute("ATTACH 'legacy.db' AS sqlite_db (TYPE SQLITE);")

    # Cross-database JOIN (DuckDB + PostgreSQL + SQLite!)
    result = con.execute("""
        SELECT
            s.customer_name,
            p.order_count,
            p.total_revenue
        FROM sqlite_db.customers s
        JOIN (
            SELECT customer_id, COUNT(*) AS order_count,
                   SUM(amount) AS total_revenue
            FROM pg_db.orders
            GROUP BY customer_id
        ) p ON s.id = p.customer_id
        ORDER BY p.total_revenue DESC
    """).df()
```

```python
# --- Spatial extension and full-text search ---

def spatial_queries(con: duckdb.DuckDBPyConnection) -> None:
    """Geospatial queries with the spatial extension."""
    con.execute("LOAD spatial;")

    # Read GeoJSON / Shapefile
    result = con.execute("""
        SELECT
            name,
            ST_Area(geom) AS area,
            ST_Centroid(geom) AS centroid
        FROM ST_Read('data/boundaries.geojson')
        ORDER BY area DESC
        LIMIT 10
    """).df()

    # Point-in-polygon queries
    result = con.execute("""
        SELECT
            p.name AS point_name,
            b.region_name
        FROM (
            SELECT name, ST_Point(longitude, latitude) AS geom
            FROM read_csv_auto('data/locations.csv')
        ) p
        JOIN ST_Read('data/regions.geojson') b
            ON ST_Contains(b.geom, p.geom)
    """).df()


def full_text_search(con: duckdb.DuckDBPyConnection) -> None:
    """Full-text search with the FTS extension."""
    con.execute("LOAD fts;")

    # Create FTS index
    con.execute("""
        CREATE TABLE documents (
            id INTEGER,
            title VARCHAR,
            content VARCHAR
        );

        -- Populate with data...

        -- Create FTS index
        PRAGMA create_fts_index(
            'documents', 'id',
            'title', 'content',
            stemmer = 'english',
            stopwords = 'english'
        );
    """)

    # Search with ranking
    result = con.execute("""
        SELECT id, title, content, score
        FROM (
            SELECT *, fts_main_documents.match_bm25(
                id, 'machine learning optimization'
            ) AS score
            FROM documents
        )
        WHERE score IS NOT NULL
        ORDER BY score DESC
        LIMIT 10
    """).fetchall()


# Extension availability summary
EXTENSION_MATRIX = """
| Extension  | Function                    | Install       |
|------------|-----------------------------|---------------|
| httpfs     | S3/HTTP/GCS file access     | INSTALL httpfs |
| json       | JSON processing             | Built-in      |
| parquet    | Parquet reader/writer        | Built-in      |
| spatial    | ST_* geospatial functions   | INSTALL spatial|
| fts        | Full-text search (BM25)     | INSTALL fts   |
| postgres   | Attach PostgreSQL databases | INSTALL postgres|
| sqlite     | Attach SQLite databases     | INSTALL sqlite |
| mysql      | Attach MySQL databases      | INSTALL mysql  |
| icu        | Unicode collation/sorting   | INSTALL icu    |
| tpch       | TPC-H benchmark generator   | INSTALL tpch   |
| excel      | Read/write Excel files      | INSTALL excel  |
"""
```

Key DuckDB extension patterns:

| Extension | Capability | Use Case |
|---|---|---|
| httpfs | S3/GCS/HTTP file access | Query data lake without downloading |
| postgres | Attach PostgreSQL | Cross-database analytics |
| sqlite | Attach SQLite | Migrate or query legacy databases |
| spatial | ST_* geospatial | Point-in-polygon, distance calculations |
| fts | BM25 full-text search | Document search in embedded apps |
| excel | Read/write .xlsx | ETL from spreadsheets |

1. **Query S3 directly** -- no download step, predicate pushdown reduces transfer
2. **Cross-database JOINs** -- attach Postgres + SQLite + Parquet in one query
3. **Spatial extension** -- read GeoJSON/Shapefiles and run ST_* functions
4. **FTS for embedded search** -- BM25 ranking without external search engine
5. **Extensions are lazy-loaded** -- INSTALL once, LOAD per session as needed'''
    ),
]
