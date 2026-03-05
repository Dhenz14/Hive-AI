"""DuckDB — analytical queries, Parquet/CSV ingestion, window functions, embedded OLAP, Python integration, spatial extensions."""

PAIRS = [
    (
        "databases/duckdb-parquet-csv-ingestion",
        "Show how to ingest Parquet and CSV files with DuckDB, including schema inference, glob patterns, partitioned datasets, and Hive-style partitioning.",
        '''DuckDB Parquet/CSV ingestion with advanced file handling:

```python
import duckdb
from pathlib import Path

# === DuckDB connection with configuration ===
conn = duckdb.connect("analytics.duckdb")

# Tune memory and threads for large ingestion
conn.execute("""
    SET memory_limit = '4GB';
    SET threads = 8;
    SET enable_progress_bar = true;
    SET preserve_insertion_order = false;  -- faster bulk insert
""")


# === CSV ingestion with schema control ===
# Auto-detect CSV dialect (delimiter, quoting, headers)
conn.execute("""
    CREATE TABLE sales AS
    SELECT * FROM read_csv_auto(
        'data/sales_*.csv',             -- glob pattern for multiple files
        header = true,
        dateformat = '%Y-%m-%d',
        timestampformat = '%Y-%m-%d %H:%M:%S',
        sample_size = 10000,            -- rows sampled for type inference
        null_padding = true,            -- pad missing columns with NULL
        ignore_errors = true,           -- skip malformed rows
        filename = true                 -- add source filename as column
    );
""")

# CSV with explicit schema (faster — skips inference)
conn.execute("""
    CREATE TABLE transactions (
        txn_id        VARCHAR PRIMARY KEY,
        account_id    INTEGER NOT NULL,
        amount        DECIMAL(12, 2),
        currency      VARCHAR(3),
        txn_date      DATE,
        category      VARCHAR(50),
        merchant      VARCHAR(200)
    );

    COPY transactions FROM 'data/transactions/*.csv' (
        FORMAT CSV,
        HEADER true,
        DELIMITER ',',
        QUOTE '"',
        ESCAPE '"',
        NULL 'NA',
        DATEFORMAT '%m/%d/%Y'
    );
""")


# === Parquet ingestion ===
# Direct query on Parquet files (zero-copy where possible)
result = conn.execute("""
    SELECT
        product_category,
        COUNT(*) AS order_count,
        SUM(total_amount) AS revenue,
        AVG(total_amount) AS avg_order_value
    FROM read_parquet('s3://data-lake/orders/**/*.parquet',
        hive_partitioning = true,   -- reads partition keys from paths
        hive_types_autocast = true
    )
    WHERE order_date >= '2025-01-01'
    GROUP BY product_category
    ORDER BY revenue DESC
    LIMIT 20;
""").fetchdf()  # returns pandas DataFrame


# === Hive-partitioned Parquet export ===
conn.execute("""
    COPY (
        SELECT
            *,
            year(order_date) AS year,
            month(order_date) AS month
        FROM orders
        WHERE order_date >= '2025-01-01'
    )
    TO 'output/orders_partitioned' (
        FORMAT PARQUET,
        PARTITION_BY (year, month),
        COMPRESSION 'zstd',
        ROW_GROUP_SIZE 100000,
        OVERWRITE_OR_IGNORE true
    );
""")


# === Schema inspection and metadata ===
# Check what DuckDB inferred
schema = conn.execute("""
    SELECT column_name, column_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'sales'
    ORDER BY ordinal_position;
""").fetchdf()

# Parquet metadata without reading data
meta = conn.execute("""
    SELECT file_name, row_group_id, row_group_num_rows,
           row_group_bytes, compression
    FROM parquet_metadata('data/large_dataset.parquet');
""").fetchdf()

# Parquet schema inspection
parquet_schema = conn.execute("""
    SELECT name, type, type_length, converted_type
    FROM parquet_schema('data/large_dataset.parquet');
""").fetchdf()


# === Multi-format joins (CSV + Parquet + JSON) ===
conn.execute("""
    CREATE VIEW enriched_orders AS
    SELECT
        o.*,
        c.customer_name,
        c.segment,
        p.product_name,
        p.unit_cost
    FROM read_parquet('data/orders/*.parquet') o
    JOIN read_csv_auto('data/customers.csv') c
        ON o.customer_id = c.customer_id
    JOIN read_json_auto('data/products.json') p
        ON o.product_id = p.product_id;
""")

print(f"Schema:\\n{schema}")
print(f"Parquet metadata:\\n{meta}")
```

Key ingestion patterns:

| Feature | CSV | Parquet | JSON |
|---|---|---|---|
| Schema inference | `read_csv_auto` | automatic | `read_json_auto` |
| Glob patterns | Yes (`*.csv`) | Yes (`**/*.parquet`) | Yes |
| Hive partitioning | No | Yes | No |
| Compression | gzip, zstd | snappy, zstd, gzip | gzip |
| Predicate pushdown | No | Yes (row groups) | No |
| Column pruning | No | Yes | No |

Key patterns:
1. **Use Parquet for analytics** -- column pruning and predicate pushdown skip unneeded data entirely
2. **Glob patterns** -- `*` matches single dir, `**` matches recursively; DuckDB parallelizes file reads
3. **Hive partitioning** -- `year=2025/month=03/` paths become columns automatically with `hive_partitioning=true`
4. **ZSTD compression for export** -- best ratio for analytical workloads; snappy for speed priority
5. **filename column** -- `filename=true` tracks which source file each row came from for data lineage'''
    ),
    (
        "databases/duckdb-window-functions",
        "Demonstrate advanced DuckDB window functions: cumulative distributions, session analysis, funnel queries, and gap-and-island detection.",
        '''DuckDB advanced window function patterns for analytics:

```sql
-- === 1. Cumulative distribution and percentile analysis ===
SELECT
    employee_id,
    department,
    salary,
    -- Percentile rank (0 to 1)
    PERCENT_RANK() OVER (
        PARTITION BY department ORDER BY salary
    ) AS percentile,
    -- Cumulative distribution (fraction of rows <= current)
    CUME_DIST() OVER (
        PARTITION BY department ORDER BY salary
    ) AS cumulative_dist,
    -- Divide into deciles
    NTILE(10) OVER (
        PARTITION BY department ORDER BY salary
    ) AS salary_decile,
    -- Distance from department median
    salary - PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary)
        OVER (PARTITION BY department) AS diff_from_median,
    -- Z-score within department
    (salary - AVG(salary) OVER (PARTITION BY department))
        / STDDEV(salary) OVER (PARTITION BY department) AS z_score
FROM employees
ORDER BY department, salary;


-- === 2. Session detection with configurable gap threshold ===
WITH events_with_gaps AS (
    SELECT
        user_id,
        event_time,
        event_type,
        page_url,
        -- Detect gaps > 30 min between consecutive events
        CASE WHEN event_time - LAG(event_time) OVER (
            PARTITION BY user_id ORDER BY event_time
        ) > INTERVAL '30 minutes'
        OR LAG(event_time) OVER (
            PARTITION BY user_id ORDER BY event_time
        ) IS NULL
        THEN 1 ELSE 0 END AS is_new_session
    FROM user_events
),
sessionized AS (
    SELECT
        *,
        SUM(is_new_session) OVER (
            PARTITION BY user_id
            ORDER BY event_time
            ROWS UNBOUNDED PRECEDING
        ) AS session_id
    FROM events_with_gaps
)
SELECT
    user_id,
    session_id,
    MIN(event_time) AS session_start,
    MAX(event_time) AS session_end,
    AGE(MAX(event_time), MIN(event_time)) AS session_duration,
    COUNT(*) AS event_count,
    COUNT(DISTINCT page_url) AS pages_visited,
    FIRST(page_url ORDER BY event_time) AS landing_page,
    LAST(page_url ORDER BY event_time) AS exit_page,
    LIST(DISTINCT event_type ORDER BY event_type) AS event_types
FROM sessionized
GROUP BY user_id, session_id
HAVING COUNT(*) >= 2
ORDER BY user_id, session_start;


-- === 3. Funnel analysis with ordered step matching ===
WITH step_events AS (
    SELECT
        user_id,
        event_time,
        event_type,
        CASE event_type
            WHEN 'page_view' THEN 1
            WHEN 'add_to_cart' THEN 2
            WHEN 'begin_checkout' THEN 3
            WHEN 'payment_info' THEN 4
            WHEN 'purchase' THEN 5
        END AS step_num
    FROM user_events
    WHERE event_type IN (
        'page_view', 'add_to_cart', 'begin_checkout',
        'payment_info', 'purchase'
    )
    AND event_date BETWEEN '2025-12-01' AND '2025-12-31'
),
user_funnels AS (
    SELECT
        user_id,
        MAX(CASE WHEN step_num >= 1 THEN 1 ELSE 0 END) AS reached_step_1,
        MAX(CASE WHEN step_num >= 2 THEN 1 ELSE 0 END) AS reached_step_2,
        MAX(CASE WHEN step_num >= 3 THEN 1 ELSE 0 END) AS reached_step_3,
        MAX(CASE WHEN step_num >= 4 THEN 1 ELSE 0 END) AS reached_step_4,
        MAX(CASE WHEN step_num >= 5 THEN 1 ELSE 0 END) AS reached_step_5,
        -- Time from first step to purchase
        AGE(
            MIN(CASE WHEN step_num = 5 THEN event_time END),
            MIN(CASE WHEN step_num = 1 THEN event_time END)
        ) AS time_to_convert
    FROM step_events
    GROUP BY user_id
)
SELECT
    'Page View' AS step, SUM(reached_step_1) AS users,
    ROUND(SUM(reached_step_1) * 100.0 / COUNT(*), 1) AS pct
FROM user_funnels
UNION ALL
SELECT 'Add to Cart', SUM(reached_step_2),
    ROUND(SUM(reached_step_2) * 100.0 / SUM(reached_step_1), 1)
FROM user_funnels
UNION ALL
SELECT 'Begin Checkout', SUM(reached_step_3),
    ROUND(SUM(reached_step_3) * 100.0 / SUM(reached_step_2), 1)
FROM user_funnels
UNION ALL
SELECT 'Payment Info', SUM(reached_step_4),
    ROUND(SUM(reached_step_4) * 100.0 / SUM(reached_step_3), 1)
FROM user_funnels
UNION ALL
SELECT 'Purchase', SUM(reached_step_5),
    ROUND(SUM(reached_step_5) * 100.0 / SUM(reached_step_4), 1)
FROM user_funnels;


-- === 4. Gap-and-island detection (consecutive sequences) ===
WITH numbered AS (
    SELECT
        sensor_id,
        reading_time,
        temperature,
        status,
        -- Row number overall vs row number per group
        ROW_NUMBER() OVER (
            PARTITION BY sensor_id ORDER BY reading_time
        ) AS rn_total,
        ROW_NUMBER() OVER (
            PARTITION BY sensor_id, status ORDER BY reading_time
        ) AS rn_status
    FROM sensor_readings
),
islands AS (
    SELECT
        sensor_id,
        status,
        -- The difference is constant within each consecutive island
        rn_total - rn_status AS island_id,
        MIN(reading_time) AS island_start,
        MAX(reading_time) AS island_end,
        COUNT(*) AS consecutive_readings,
        AVG(temperature) AS avg_temp,
        MAX(temperature) AS max_temp
    FROM numbered
    GROUP BY sensor_id, status, rn_total - rn_status
)
SELECT *
FROM islands
WHERE status = 'ALERT' AND consecutive_readings >= 5
ORDER BY sensor_id, island_start;


-- === 5. QUALIFY clause (DuckDB extension for filtering window results) ===
-- Much cleaner than wrapping in subquery
SELECT
    product_id,
    product_name,
    category,
    monthly_sales,
    RANK() OVER (
        PARTITION BY category ORDER BY monthly_sales DESC
    ) AS rank_in_category
FROM product_performance
WHERE month = '2025-12'
QUALIFY rank_in_category <= 5;   -- top 5 per category, no subquery needed
```

Key patterns:
1. **QUALIFY clause** -- DuckDB-specific filter on window results without subqueries; much cleaner SQL
2. **Gap-and-island** -- use difference of two ROW_NUMBER() sequences to identify consecutive groups
3. **Session detection** -- LAG() to find time gaps, then cumulative SUM() to assign session IDs
4. **Funnel analysis** -- assign step numbers, then aggregate MAX(reached_step_N) per user
5. **PERCENTILE_CONT as window** -- DuckDB supports ordered-set aggregate functions in window context'''
    ),
    (
        "databases/duckdb-python-integration",
        "Show DuckDB's deep Python integration: zero-copy with pandas/polars, relation API, user-defined functions, and Arrow interop.",
        '''DuckDB Python integration with zero-copy data exchange:

```python
import duckdb
import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import numpy as np
from datetime import datetime, date


# === Zero-copy DataFrame integration ===
# DuckDB can query pandas and polars DataFrames directly (zero-copy)

# Create sample data
orders_df = pd.DataFrame({
    "order_id": range(1, 100001),
    "customer_id": np.random.randint(1, 5001, 100000),
    "amount": np.random.uniform(10, 500, 100000).round(2),
    "order_date": pd.date_range("2025-01-01", periods=100000, freq="5min"),
    "status": np.random.choice(["completed", "pending", "cancelled"], 100000),
})

customers_pl = pl.DataFrame({
    "customer_id": range(1, 5001),
    "name": [f"Customer {i}" for i in range(1, 5001)],
    "tier": np.random.choice(["bronze", "silver", "gold", "platinum"], 5000),
    "signup_date": pl.date_range(date(2020, 1, 1), date(2024, 12, 31),
                                 eager=True).sample(5000),
})

# Query pandas + polars together — no import/copy needed
result = duckdb.sql("""
    SELECT
        c.tier,
        COUNT(DISTINCT o.customer_id) AS active_customers,
        COUNT(o.order_id) AS total_orders,
        ROUND(SUM(o.amount), 2) AS total_revenue,
        ROUND(AVG(o.amount), 2) AS avg_order_value,
        ROUND(SUM(o.amount) / COUNT(DISTINCT o.customer_id), 2) AS revenue_per_customer
    FROM orders_df o
    JOIN customers_pl c ON o.customer_id = c.customer_id
    WHERE o.status = 'completed'
    GROUP BY c.tier
    ORDER BY total_revenue DESC
""")

# Output to different formats
pandas_result = result.fetchdf()          # -> pandas DataFrame
polars_result = result.pl()               # -> polars DataFrame
arrow_result = result.fetch_arrow_table() # -> PyArrow Table
numpy_result = result.fetchnumpy()        # -> dict of numpy arrays


# === Relation API (lazy, chainable) ===
conn = duckdb.connect()

# Build query programmatically without SQL strings
rel = (
    conn.from_df(orders_df)
    .filter("status = 'completed' AND amount > 100")
    .join(
        conn.from_df(customers_pl.to_pandas()),
        condition="customer_id",
        how="inner"
    )
    .aggregate(
        "tier, "
        "COUNT(*) AS order_count, "
        "SUM(amount) AS total, "
        "AVG(amount) AS avg_amount"
    )
    .order("total DESC")
    .limit(10)
)

# Lazily evaluated — only executes on fetch
print(rel.explain())   # show query plan
df = rel.fetchdf()     # execute and return pandas DataFrame


# === User-Defined Functions (UDFs) ===

# Scalar UDF
@duckdb.create_function(conn, "classify_amount", [duckdb.typing.DOUBLE],
                        duckdb.typing.VARCHAR)
def classify_amount(amount: float) -> str:
    if amount < 50:
        return "small"
    elif amount < 200:
        return "medium"
    elif amount < 500:
        return "large"
    return "enterprise"

# Vectorized UDF (much faster — receives numpy arrays)
def sentiment_score_batch(texts: pd.Series) -> pd.Series:
    """Batch sentiment scoring for text columns."""
    positive_words = {"great", "excellent", "good", "love", "best", "amazing"}
    negative_words = {"bad", "terrible", "worst", "hate", "awful", "poor"}

    def score(text: str) -> float:
        if not text:
            return 0.0
        words = set(text.lower().split())
        pos = len(words & positive_words)
        neg = len(words & negative_words)
        total = pos + neg
        return (pos - neg) / total if total > 0 else 0.0

    return texts.apply(score)

conn.create_function(
    "sentiment_score",
    sentiment_score_batch,
    [duckdb.typing.VARCHAR],
    duckdb.typing.DOUBLE,
    type="arrow",  # vectorized execution
)

# Use UDFs in queries
result = conn.sql("""
    SELECT
        classify_amount(amount) AS size_class,
        COUNT(*) AS count,
        AVG(amount) AS avg_amount
    FROM orders_df
    GROUP BY size_class
    ORDER BY avg_amount
""")


# === Arrow IPC streaming for large datasets ===
# Stream results without materializing full result set
conn_disk = duckdb.connect("large_analytics.duckdb")

# Write query results as streaming Arrow batches
reader = conn_disk.execute("""
    SELECT * FROM large_table WHERE event_date >= '2025-01-01'
""").fetch_arrow_reader(batch_size=100_000)

# Process in chunks (constant memory)
total_rows = 0
for batch in reader:
    # Process each Arrow RecordBatch
    chunk_df = batch.to_pandas()
    total_rows += len(chunk_df)
    # ... process chunk ...

print(f"Processed {total_rows:,} rows in streaming fashion")


# === Persistent database with concurrent reads ===
# WAL mode allows concurrent readers with single writer
db = duckdb.connect("shared.duckdb", config={
    "access_mode": "READ_WRITE",
    "wal_autocheckpoint": "64MB",
})

# Create read-only connections for concurrent queries
reader1 = duckdb.connect("shared.duckdb", read_only=True)
reader2 = duckdb.connect("shared.duckdb", read_only=True)
```

Key patterns:
1. **Zero-copy query** -- DuckDB scans pandas/polars DataFrames in-place via Arrow columnar format; no serialization
2. **Relation API** -- build queries programmatically with `.filter().join().aggregate()`; lazy evaluation until `.fetchdf()`
3. **Vectorized UDFs** -- use `type="arrow"` for batch processing; 10-100x faster than row-at-a-time scalar UDFs
4. **Arrow streaming** -- `fetch_arrow_reader(batch_size=N)` processes billions of rows in constant memory
5. **Multi-format output** -- `.fetchdf()` for pandas, `.pl()` for polars, `.fetch_arrow_table()` for Arrow; choose based on downstream needs'''
    ),
    (
        "databases/duckdb-embedded-olap",
        "Show DuckDB as an embedded OLAP engine: in-process analytics for web apps, replacing reporting databases, and materialized CTEs.",
        '''DuckDB as an embedded OLAP engine replacing traditional reporting databases:

```python
import duckdb
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any
from contextlib import contextmanager


@dataclass
class AnalyticsEngine:
    """Embedded OLAP engine using DuckDB for application analytics.

    Replaces external reporting databases (Redshift, BigQuery) for
    datasets under ~100GB that fit on a single node.
    """

    db_path: str = "analytics.duckdb"
    memory_limit: str = "4GB"
    threads: int = 4
    _conn: Any = field(init=False, default=None)

    def __post_init__(self):
        self._conn = duckdb.connect(self.db_path, config={
            "memory_limit": self.memory_limit,
            "threads": self.threads,
            "default_order": "DESC",
            "enable_object_cache": "true",
        })
        self._init_schema()

    def _init_schema(self):
        """Create analytical tables with optimized types."""
        self._conn.execute("""
            -- Fact table: append-only event log
            CREATE TABLE IF NOT EXISTS events (
                event_id     UBIGINT DEFAULT nextval('event_seq'),
                event_time   TIMESTAMP NOT NULL DEFAULT now(),
                user_id      UINTEGER NOT NULL,
                event_type   VARCHAR NOT NULL,
                properties   JSON,
                session_id   VARCHAR,
                device_type  VARCHAR,
                country      VARCHAR(2),
                revenue      DECIMAL(12, 4) DEFAULT 0
            );

            -- Create sequence if not exists
            CREATE SEQUENCE IF NOT EXISTS event_seq START 1;

            -- Dimension table: slowly changing
            CREATE TABLE IF NOT EXISTS users (
                user_id      UINTEGER PRIMARY KEY,
                email        VARCHAR UNIQUE,
                plan         VARCHAR DEFAULT 'free',
                created_at   TIMESTAMP DEFAULT now(),
                attributes   JSON
            );

            -- Pre-aggregated rollup table
            CREATE TABLE IF NOT EXISTS daily_metrics (
                metric_date  DATE NOT NULL,
                metric_name  VARCHAR NOT NULL,
                dimension    VARCHAR DEFAULT 'all',
                value        DOUBLE NOT NULL,
                sample_count UBIGINT NOT NULL,
                PRIMARY KEY (metric_date, metric_name, dimension)
            );
        """)

    @contextmanager
    def transaction(self):
        """Transaction context manager with auto-rollback."""
        self._conn.execute("BEGIN TRANSACTION")
        try:
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def ingest_events(self, events: list[dict]):
        """Bulk insert events using prepared statement."""
        with self.transaction() as conn:
            conn.executemany("""
                INSERT INTO events (user_id, event_type, properties,
                                    session_id, device_type, country, revenue)
                VALUES (?, ?, ?::JSON, ?, ?, ?, ?)
            """, [
                (e["user_id"], e["event_type"],
                 json.dumps(e.get("properties", {})),
                 e.get("session_id"), e.get("device_type"),
                 e.get("country"), e.get("revenue", 0))
                for e in events
            ])

    def cohort_retention(self, cohort_month: str, periods: int = 12):
        """Calculate monthly cohort retention using window functions."""
        return self._conn.execute("""
            WITH cohort AS (
                SELECT
                    user_id,
                    DATE_TRUNC('month', MIN(event_time)) AS cohort_month
                FROM events
                GROUP BY user_id
                HAVING cohort_month = ?::DATE
            ),
            activity AS (
                SELECT DISTINCT
                    e.user_id,
                    c.cohort_month,
                    DATE_TRUNC('month', e.event_time) AS active_month
                FROM events e
                JOIN cohort c ON e.user_id = c.user_id
            )
            SELECT
                cohort_month,
                DATEDIFF('month', cohort_month, active_month) AS period,
                COUNT(DISTINCT user_id) AS active_users,
                ROUND(
                    COUNT(DISTINCT user_id) * 100.0 /
                    FIRST(COUNT(DISTINCT user_id))
                        OVER (PARTITION BY cohort_month
                              ORDER BY active_month),
                    1
                ) AS retention_pct
            FROM activity
            WHERE DATEDIFF('month', cohort_month, active_month)
                  BETWEEN 0 AND ?
            GROUP BY cohort_month, active_month
            ORDER BY period;
        """, [cohort_month, periods]).fetchdf()

    def revenue_analytics(self, start_date: str, end_date: str):
        """Revenue breakdown with running totals and forecasting."""
        return self._conn.execute("""
            WITH daily AS (
                SELECT
                    DATE_TRUNC('day', event_time)::DATE AS day,
                    SUM(revenue) AS daily_revenue,
                    COUNT(DISTINCT user_id) AS paying_users,
                    COUNT(*) AS transactions
                FROM events
                WHERE revenue > 0
                    AND event_time BETWEEN ?::TIMESTAMP AND ?::TIMESTAMP
                GROUP BY day
            )
            SELECT
                day,
                daily_revenue,
                paying_users,
                transactions,
                ROUND(daily_revenue / paying_users, 2) AS arpu,
                SUM(daily_revenue) OVER (
                    ORDER BY day ROWS UNBOUNDED PRECEDING
                ) AS cumulative_revenue,
                AVG(daily_revenue) OVER (
                    ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS revenue_7d_avg,
                AVG(daily_revenue) OVER (
                    ORDER BY day ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
                ) AS revenue_30d_avg,
                -- Growth rate vs same day last week
                ROUND(
                    (daily_revenue - LAG(daily_revenue, 7) OVER (ORDER BY day))
                    / NULLIF(LAG(daily_revenue, 7) OVER (ORDER BY day), 0)
                    * 100, 1
                ) AS wow_growth_pct
            FROM daily
            ORDER BY day;
        """, [start_date, end_date]).fetchdf()

    def rollup_daily_metrics(self, target_date: str):
        """Compute and store pre-aggregated daily metrics."""
        with self.transaction() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO daily_metrics
                SELECT
                    ?::DATE AS metric_date,
                    metric_name,
                    dimension,
                    value,
                    sample_count
                FROM (
                    -- DAU by country
                    SELECT 'dau' AS metric_name, country AS dimension,
                        COUNT(DISTINCT user_id)::DOUBLE AS value,
                        COUNT(*)::UBIGINT AS sample_count
                    FROM events
                    WHERE event_time::DATE = ?::DATE
                    GROUP BY country

                    UNION ALL

                    -- Revenue by plan
                    SELECT 'revenue', u.plan,
                        SUM(e.revenue)::DOUBLE, COUNT(*)::UBIGINT
                    FROM events e
                    JOIN users u ON e.user_id = u.user_id
                    WHERE e.event_time::DATE = ?::DATE AND e.revenue > 0
                    GROUP BY u.plan

                    UNION ALL

                    -- Event counts by type
                    SELECT 'events', event_type,
                        COUNT(*)::DOUBLE, COUNT(*)::UBIGINT
                    FROM events
                    WHERE event_time::DATE = ?::DATE
                    GROUP BY event_type
                );
            """, [target_date, target_date, target_date, target_date])


# === Usage ===
engine = AnalyticsEngine(db_path="app_analytics.duckdb", memory_limit="2GB")

# Ingest events
engine.ingest_events([
    {"user_id": 1, "event_type": "purchase", "revenue": 29.99,
     "country": "US", "device_type": "mobile",
     "properties": {"plan": "pro", "period": "monthly"}},
    {"user_id": 2, "event_type": "page_view",
     "country": "GB", "device_type": "desktop",
     "properties": {"page": "/pricing"}},
])

# Run analytics
retention = engine.cohort_retention("2025-01-01", periods=6)
revenue = engine.revenue_analytics("2025-01-01", "2025-12-31")
engine.rollup_daily_metrics("2025-12-15")
```

Key patterns:
1. **Embedded OLAP** -- DuckDB runs in-process; no separate server, no network latency, no deployment complexity
2. **Pre-aggregated rollups** -- compute daily_metrics once, query instantly; avoids re-scanning raw event tables
3. **Transaction safety** -- context manager with BEGIN/COMMIT/ROLLBACK for batch ingestion integrity
4. **Cohort analysis in SQL** -- window functions with FIRST() for retention percentage relative to cohort size
5. **Replace reporting DB** -- for datasets under ~100GB, DuckDB on a single machine outperforms distributed systems for most analytical queries'''
    ),
    (
        "databases/duckdb-spatial-extensions",
        "Show DuckDB extensions: spatial (geometry/geography), httpfs for remote files, and the extension ecosystem.",
        '''DuckDB extensions for spatial analytics and remote data access:

```sql
-- === Install and load extensions ===
INSTALL spatial;
INSTALL httpfs;
INSTALL json;
INSTALL excel;

LOAD spatial;
LOAD httpfs;
LOAD json;


-- === Configure remote access (S3 / HTTP) ===
SET s3_region = 'us-east-1';
SET s3_access_key_id = 'AKIAIOSFODNN7EXAMPLE';
SET s3_secret_access_key = '...';
-- Or use credential chain (IAM roles, env vars)
SET s3_use_credential_provider = 'auto';


-- === Spatial extension: geometry operations ===

-- Load geospatial data from GeoJSON
CREATE TABLE regions AS
SELECT
    properties->>'name' AS region_name,
    properties->>'population' AS population,
    ST_GeomFromGeoJSON(geometry) AS geom
FROM read_json_auto('data/regions.geojson',
    records='auto', json_format='array');

-- Create index for spatial queries
CREATE INDEX idx_regions_geom ON regions USING RTREE (geom);

-- Store locations
CREATE TABLE stores (
    store_id INTEGER PRIMARY KEY,
    name VARCHAR,
    lat DOUBLE,
    lon DOUBLE,
    geom GEOMETRY
);

INSERT INTO stores VALUES
    (1, 'Downtown', 40.7128, -74.0060, ST_Point(-74.0060, 40.7128)),
    (2, 'Midtown', 40.7549, -73.9840, ST_Point(-73.9840, 40.7549)),
    (3, 'Brooklyn', 40.6782, -73.9442, ST_Point(-73.9442, 40.6782));


-- Point-in-polygon: which region is each store in?
SELECT
    s.name AS store_name,
    r.region_name,
    r.population
FROM stores s
JOIN regions r ON ST_Within(s.geom, r.geom);


-- Nearest neighbor: find 3 closest stores to a point
SELECT
    name,
    ROUND(ST_Distance_Spheroid(
        geom,
        ST_Point(-73.9857, 40.7484)  -- Empire State Building
    ) / 1000, 2) AS distance_km
FROM stores
ORDER BY ST_Distance(geom, ST_Point(-73.9857, 40.7484))
LIMIT 3;


-- Buffer analysis: find all stores within 2km of a point
SELECT name
FROM stores
WHERE ST_DWithin_Spheroid(
    geom,
    ST_Point(-73.9857, 40.7484),
    2000  -- meters
);


-- Area and perimeter calculations
SELECT
    region_name,
    ROUND(ST_Area_Spheroid(geom) / 1e6, 2) AS area_sq_km,
    ROUND(ST_Perimeter_Spheroid(geom) / 1000, 2) AS perimeter_km
FROM regions
ORDER BY area_sq_km DESC;


-- Spatial aggregation: convex hull of all stores
SELECT ST_AsGeoJSON(
    ST_ConvexHull(ST_Collect(LIST(geom)))
) AS coverage_area
FROM stores;


-- === HTTPFS: query remote files directly ===

-- Query Parquet on S3 without downloading
SELECT
    pickup_zone,
    COUNT(*) AS trips,
    AVG(total_amount) AS avg_fare
FROM read_parquet('s3://nyc-tlc/trip data/yellow_tripdata_2025-*.parquet')
WHERE trip_distance > 0 AND total_amount > 0
GROUP BY pickup_zone
ORDER BY trips DESC
LIMIT 20;

-- Query CSV from HTTP URL
SELECT *
FROM read_csv_auto(
    'https://raw.githubusercontent.com/datasets/covid-19/main/data/time-series-19-covid-combined.csv'
)
WHERE "Country/Region" = 'US'
ORDER BY Date DESC
LIMIT 10;


-- === Combine spatial + remote data ===
-- Analyze geographic patterns from remote Parquet files
CREATE TABLE taxi_zones AS
SELECT * FROM read_parquet('s3://nyc-taxi-data/zones.parquet');

CREATE TABLE trip_analysis AS
WITH trips AS (
    SELECT
        pickup_location_id,
        dropoff_location_id,
        trip_distance,
        total_amount,
        passenger_count
    FROM read_parquet('s3://nyc-tlc/trip data/yellow_tripdata_2025-01.parquet')
    WHERE trip_distance > 0
)
SELECT
    pz.zone AS pickup_zone,
    dz.zone AS dropoff_zone,
    COUNT(*) AS trip_count,
    ROUND(AVG(t.trip_distance), 2) AS avg_distance,
    ROUND(AVG(t.total_amount), 2) AS avg_fare,
    ROUND(AVG(t.total_amount / NULLIF(t.trip_distance, 0)), 2) AS fare_per_mile
FROM trips t
JOIN taxi_zones pz ON t.pickup_location_id = pz.location_id
JOIN taxi_zones dz ON t.dropoff_location_id = dz.location_id
GROUP BY pz.zone, dz.zone
HAVING trip_count >= 100
ORDER BY trip_count DESC;


-- === Excel file reading ===
SELECT * FROM read_xlsx('reports/q4_2025.xlsx',
    sheet_name = 'Revenue',
    range = 'A1:F100'
);
```

```python
# === Python spatial workflow ===
import duckdb
import geopandas as gpd

conn = duckdb.connect()
conn.install_extension("spatial")
conn.load_extension("spatial")

# Load GeoDataFrame directly
neighborhoods = gpd.read_file("data/neighborhoods.geojson")

# DuckDB queries GeoDataFrame with spatial functions
result = conn.execute("""
    SELECT
        name,
        ROUND(ST_Area_Spheroid(geometry) / 1e6, 2) AS area_km2,
        ST_Centroid(geometry) AS centroid,
        ST_NPoints(geometry) AS vertex_count
    FROM neighborhoods
    WHERE ST_Area_Spheroid(geometry) > 1e6  -- > 1 sq km
    ORDER BY area_km2 DESC
""").fetchdf()

# Export spatial results to GeoJSON
conn.execute("""
    COPY (
        SELECT name, ST_AsGeoJSON(geometry) AS geometry
        FROM neighborhoods
    ) TO 'output/filtered.geojson' (FORMAT JSON);
""")
```

Key patterns:
1. **Extension ecosystem** -- `INSTALL x; LOAD x;` adds spatial, httpfs, json, excel, postgres scanner, and more
2. **Spatial R-tree index** -- `CREATE INDEX ... USING RTREE` accelerates ST_Within, ST_DWithin queries
3. **Spheroid functions** -- use `ST_Distance_Spheroid` / `ST_Area_Spheroid` for real-world measurements in meters
4. **Remote query** -- httpfs lets you query S3/HTTP Parquet/CSV without downloading; predicate pushdown still works on Parquet
5. **GeoDataFrame interop** -- DuckDB scans GeoPandas DataFrames directly; geometry columns work with all ST_ functions'''
    ),
]
