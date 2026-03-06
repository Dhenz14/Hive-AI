"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 4)

Pagination strategies (offset, cursor, keyset) and time-series data modeling
with realistic SQL scenarios and performance tradeoff analysis.
"""

PAIRS = [
    (
        "thinking/datamodel-offset-vs-cursor-pagination",
        r'''Our REST API returns paginated product listings. Currently we use offset pagination:

GET /api/products?page=2&per_page=25

SELECT * FROM products
WHERE category_id = 7 AND active = true
ORDER BY created_at DESC
LIMIT 25 OFFSET 25;

With 2 million products, users report that pages beyond ~1000 are very slow. Our DB monitoring shows the query scans 500K+ rows for page 20000. Why is this happening and what's the best pagination strategy?''',
        r'''<think>
Let me analyze why offset pagination degrades and compare the alternatives.

**Why offset pagination is slow for deep pages:**

`LIMIT 25 OFFSET 500000` means PostgreSQL must:
1. Execute the full query with ORDER BY
2. Scan and sort the first 500,025 rows
3. Skip the first 500,000
4. Return the last 25

The database can't "jump" to row 500,000. It must read all preceding rows. The cost is O(offset + limit), not O(limit). So page 1 reads 25 rows, page 20000 reads 500,025 rows.

Additionally:
- If the ORDER BY column isn't indexed, it requires a full table sort
- Even with an index, PostgreSQL may choose a sequential scan for large offsets because index scans have per-row overhead
- OFFSET doesn't cache — repeating the same offset re-scans everything

**Option 1: Keyset pagination (cursor-based using WHERE)**

Instead of OFFSET, use the last seen value:

```sql
-- First page
SELECT * FROM products
WHERE category_id = 7 AND active = true
ORDER BY created_at DESC, id DESC
LIMIT 25;

-- Next page: use the last row's created_at and id
SELECT * FROM products
WHERE category_id = 7 AND active = true
AND (created_at, id) < ('2024-03-15 10:30:00', 12345)
ORDER BY created_at DESC, id DESC
LIMIT 25;
```

The (created_at, id) tuple is the "cursor." The secondary sort on id breaks ties when multiple products have the same created_at.

Pros:
- Constant time O(limit) regardless of page depth — uses index seek
- Consistent results (no skipped/duplicated rows from concurrent inserts)
- Very efficient with a composite index on (category_id, active, created_at DESC, id DESC)

Cons:
- Can't jump to arbitrary page (no "go to page 500")
- Only forward/backward navigation (no random access)
- Client must track the cursor (last seen values)
- Harder to implement with multi-column sorts

**Option 2: Opaque cursor (encoded keyset)**

Same as keyset but the cursor is an opaque token (base64-encoded):

```
GET /api/products?cursor=eyJjcmVhdGVkX2F0IjoiMjAyNC0wMy0xNSIsImlkIjoxMjM0NX0=
```

The token decodes to `{"created_at": "2024-03-15T10:30:00Z", "id": 12345}`.

Pros over raw keyset:
- Client can't tamper with cursor values
- API contract is cleaner (cursor is a string, not exposed column names)
- Can change sort implementation without breaking clients

**Option 3: Indexed materialized page numbers**

Pre-compute page assignments:

```sql
ALTER TABLE products ADD COLUMN page_number INTEGER;
UPDATE products SET page_number = (ROW_NUMBER() OVER (ORDER BY created_at DESC) - 1) / 25;
CREATE INDEX idx_products_page ON products (page_number);
```

Pros: Random page access is fast
Cons: Must recompute when data changes, stale page numbers, terrible for frequently changing data

**For this case (2M products, category browsing):**

Keyset pagination with an opaque cursor is the clear winner because:
1. Product listings are naturally "scroll forward" — users don't jump to page 500
2. 2M rows makes offset prohibitively slow beyond page ~100
3. The composite index makes keyset queries constant-time
4. Consistent results (no items skipped/duplicated from concurrent product additions)

Keep offset pagination only for admin dashboards where total page count matters and dataset is filtered to < 10K rows.
</think>

### Why offset is slow: The database scans ALL skipped rows

```
OFFSET 0:      Reads 25 rows     → ~0.5ms
OFFSET 1000:   Reads 1,025 rows  → ~5ms
OFFSET 100000: Reads 100,025 rows → ~800ms
OFFSET 500000: Reads 500,025 rows → ~4 seconds
```

The cost grows linearly with the offset value. There is no fix for this within offset pagination.

### Solution: Keyset pagination with opaque cursors

```sql
-- Step 1: Create the composite index that makes keyset pagination fast
CREATE INDEX idx_products_category_cursor
ON products (category_id, active, created_at DESC, id DESC)
WHERE active = true;
```

### API design

```python
import base64, json
from datetime import datetime
from fastapi import FastAPI, Query

app = FastAPI()

def encode_cursor(created_at: datetime, product_id: int) -> str:
    payload = {"c": created_at.isoformat(), "i": product_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, int]:
    payload = json.loads(base64.urlsafe_b64decode(cursor))
    return datetime.fromisoformat(payload["c"]), payload["i"]

@app.get("/api/products")
async def list_products(
    category_id: int,
    cursor: str | None = Query(None),
    limit: int = Query(25, le=100),
):
    if cursor:
        last_created, last_id = decode_cursor(cursor)
        rows = await db.fetch_all("""
            SELECT id, name, price, created_at
            FROM products
            WHERE category_id = $1 AND active = true
              AND (created_at, id) < ($2, $3)
            ORDER BY created_at DESC, id DESC
            LIMIT $4
        """, category_id, last_created, last_id, limit + 1)
    else:
        rows = await db.fetch_all("""
            SELECT id, name, price, created_at
            FROM products
            WHERE category_id = $1 AND active = true
            ORDER BY created_at DESC, id DESC
            LIMIT $2
        """, category_id, limit + 1)

    # Fetch limit+1 to detect if there's a next page
    has_next = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = encode_cursor(last["created_at"], last["id"])

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_next": has_next,
    }
```

### Performance comparison

```sql
-- Offset: page 20,000 (scans 500K rows)
EXPLAIN ANALYZE
SELECT * FROM products
WHERE category_id = 7 AND active = true
ORDER BY created_at DESC
LIMIT 25 OFFSET 500000;
-- Execution Time: 3847.231 ms (Seq Scan)

-- Keyset: same position (index seek, reads 25 rows)
EXPLAIN ANALYZE
SELECT * FROM products
WHERE category_id = 7 AND active = true
AND (created_at, id) < ('2023-01-15 10:30:00', 12345)
ORDER BY created_at DESC, id DESC
LIMIT 25;
-- Execution Time: 0.412 ms (Index Scan)
```

### When to use each strategy

| Strategy | Random access | Deep pages | Consistency | Best for |
|----------|-------------|------------|-------------|----------|
| Offset | Yes (page N) | Very slow | Duplicates possible | Admin panels < 10K rows |
| Keyset/cursor | No (forward only) | Constant speed | Consistent | Public APIs, infinite scroll |
| Keyset + count | No | Constant speed | Consistent | When you need total count |'''
    ),
    (
        "thinking/datamodel-keyset-multi-column-sort",
        r'''We're implementing cursor pagination for a job board with sortable columns. Users can sort by:
- salary DESC (highest first)
- posted_date DESC (newest first)
- company_name ASC (alphabetical)

The problem: keyset pagination with multi-column sorts is tricky. With salary DESC, id DESC:

WHERE (salary, id) < ($last_salary, $last_id)

But what about NULL salaries (some jobs don't list salary)? And what about switching sort order mid-pagination? Our current implementation breaks when salary values are identical across many rows.''',
        r'''<think>
Multi-column keyset pagination with NULLs and ties is one of the harder pagination problems. Let me work through it systematically.

**Problem 1: NULL values in sort columns**

SQL comparison with NULL returns NULL (not true/false), so `(salary, id) < (NULL, 123)` won't work. NULLs break the WHERE clause.

In PostgreSQL, we can use `NULLS LAST` in ORDER BY, but the WHERE clause equivalent is complex:

```sql
ORDER BY salary DESC NULLS LAST, id DESC
```

The keyset WHERE clause for this is:
```sql
WHERE (
    salary < $last_salary
    OR (salary = $last_salary AND id < $last_id)
    OR (salary IS NULL AND $last_salary IS NOT NULL)
    OR (salary IS NULL AND $last_salary IS NULL AND id < $last_id)
)
```

This is getting ugly. For N columns it's even worse.

**Problem 2: Many identical values (ties)**

If 500 jobs have salary = 100000, keyset on salary alone would skip or repeat rows. The secondary sort (id) breaks ties, but only if:
1. The cursor includes BOTH salary AND id
2. The WHERE clause handles the compound comparison correctly

**Problem 3: Switching sort orders**

When user changes sort from salary to posted_date, the cursor is invalid (it contains salary-based position, not date-based). You must:
- Invalidate the cursor and start from page 1
- Or encode the sort key in the cursor itself

**Solution approach:**

1. Always include `id` as the final tiebreaker in every sort
2. Use row value comparison syntax where possible: `(col1, col2) < ($1, $2)`
3. Handle NULLs with COALESCE or explicit NULL handling
4. Encode the sort configuration IN the cursor so stale cursors are detected

For NULLs specifically, the cleanest approach is to COALESCE to a sentinel value:

```sql
ORDER BY COALESCE(salary, -1) DESC, id DESC
-- Cursor: WHERE (COALESCE(salary, -1), id) < (COALESCE($1, -1), $2)
```

But this only works if the sentinel value is outside the real data range. For salary, -1 works. For strings, it's harder.

A more robust approach: use a "sort key" computed column or expression index:

```sql
CREATE INDEX idx_jobs_salary_sort ON jobs (
    (CASE WHEN salary IS NULL THEN 1 ELSE 0 END),
    salary DESC,
    id DESC
);
```

This puts NULLs at the end deterministically.

**My recommendation:**

Build a pagination helper that:
1. Takes the sort configuration and builds the correct ORDER BY + WHERE + index
2. Encodes sort params in the cursor to detect stale cursors
3. Always appends id as tiebreaker
4. Handles NULLs with explicit NULL-last logic
</think>

### The three problems with multi-column keyset pagination

1. NULLs break comparison operators
2. Ties in sort column skip/duplicate rows without a tiebreaker
3. Changing sort order invalidates cursors

### Solution: Robust cursor encoder with NULL handling

```python
import base64, json, hashlib
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any

@dataclass
class SortConfig:
    column: str
    direction: str  # 'asc' or 'desc'
    nulls: str = 'last'  # 'first' or 'last'

ALLOWED_SORTS = {
    'salary': SortConfig('salary', 'desc', nulls='last'),
    'posted_date': SortConfig('posted_date', 'desc', nulls='last'),
    'company_name': SortConfig('company_name', 'asc', nulls='last'),
}

def encode_cursor(sort_key: str, values: dict) -> str:
    """Encode sort config + position into opaque cursor."""
    payload = {
        'sort': sort_key,
        'v': values,  # {"salary": 95000, "id": 4521} or {"salary": None, "id": 4521}
        'h': hashlib.sha256(sort_key.encode()).hexdigest()[:8],
    }
    return base64.urlsafe_b64encode(json.dumps(payload, default=str).encode()).decode()

def decode_cursor(cursor: str, expected_sort: str) -> dict | None:
    """Decode cursor, return None if sort changed (stale cursor)."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor))
        if payload['sort'] != expected_sort:
            return None  # Sort changed — restart from page 1
        return payload['v']
    except Exception:
        return None
```

### SQL builder with NULL-safe keyset conditions

```python
def build_keyset_query(
    sort: SortConfig,
    cursor_values: dict | None,
    limit: int = 25,
) -> tuple[str, list]:
    """Build a keyset-paginated query with NULL handling."""

    col = sort.column
    desc = sort.direction == 'desc'
    nulls_last = sort.nulls == 'last'

    # ORDER BY with explicit NULL handling + id tiebreaker
    null_rank = "1" if nulls_last else "0"
    order_dir = "DESC" if desc else "ASC"
    id_dir = "DESC"  # id always descending for stable ordering

    order_clause = f"""
        ORDER BY
            (CASE WHEN {col} IS NULL THEN {null_rank} ELSE 0 END) {"ASC" if nulls_last else "DESC"},
            {col} {order_dir},
            id {id_dir}
    """

    if cursor_values is None:
        # First page — no WHERE keyset filter
        query = f"""
            SELECT * FROM jobs
            WHERE active = true
            {order_clause}
            LIMIT $1
        """
        return query, [limit + 1]

    last_val = cursor_values.get(col)
    last_id = cursor_values['id']

    # NULL-safe keyset WHERE clause
    if last_val is None:
        # Cursor was on a NULL value — only rows with NULL and lower id remain
        where_keyset = f"""
            AND (
                ({col} IS NULL AND id < $2)
            )
        """ if nulls_last else f"""
            AND (
                ({col} IS NOT NULL)
                OR ({col} IS NULL AND id < $2)
            )
        """
        query = f"""
            SELECT * FROM jobs
            WHERE active = true
            {where_keyset}
            {order_clause}
            LIMIT $1
        """
        return query, [limit + 1, last_id]
    else:
        # Normal case: last value was not NULL
        comp = "<" if desc else ">"
        where_keyset = f"""
            AND (
                ({col} {comp} $2)
                OR ({col} = $2 AND id < $3)
                OR ({col} IS NULL)
            )
        """ if nulls_last else f"""
            AND (
                ({col} {comp} $2)
                OR ({col} = $2 AND id < $3)
            )
        """
        query = f"""
            SELECT * FROM jobs
            WHERE active = true
            {where_keyset}
            {order_clause}
            LIMIT $1
        """
        return query, [limit + 1, last_val, last_id]
```

### Index design for each sort option

```sql
-- Salary sort: NULLs last, then salary DESC, id DESC
CREATE INDEX idx_jobs_salary_keyset ON jobs (
    (CASE WHEN salary IS NULL THEN 1 ELSE 0 END),
    salary DESC,
    id DESC
) WHERE active = true;

-- Posted date sort
CREATE INDEX idx_jobs_posted_keyset ON jobs (
    posted_date DESC,
    id DESC
) WHERE active = true;

-- Company name sort: ASC with NULLs last
CREATE INDEX idx_jobs_company_keyset ON jobs (
    (CASE WHEN company_name IS NULL THEN 1 ELSE 0 END),
    company_name ASC,
    id DESC
) WHERE active = true;
```

### API endpoint tying it all together

```python
from fastapi import FastAPI, Query, HTTPException

@app.get("/api/jobs")
async def list_jobs(
    sort_by: str = Query("posted_date", enum=["salary", "posted_date", "company_name"]),
    cursor: str | None = Query(None),
    limit: int = Query(25, le=100),
):
    sort_config = ALLOWED_SORTS[sort_by]

    cursor_values = None
    if cursor:
        cursor_values = decode_cursor(cursor, sort_by)
        # cursor_values is None if sort changed — means restart from page 1

    query, params = build_keyset_query(sort_config, cursor_values, limit)
    rows = await db.fetch_all(query, *params)

    has_next = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = encode_cursor(sort_by, {
            sort_config.column: last[sort_config.column],
            'id': last['id'],
        })

    return {
        "items": items,
        "sort_by": sort_by,
        "next_cursor": next_cursor,
        "has_next": has_next,
    }
```

### Key rules for multi-column keyset pagination

1. Always include a unique column (id) as the last sort key
2. Encode the sort configuration in the cursor to detect stale cursors
3. Handle NULLs explicitly in both ORDER BY and WHERE
4. Create expression indexes matching your ORDER BY exactly
5. Invalidate cursor when sort changes rather than producing wrong results'''
    ),
    (
        "thinking/datamodel-timeseries-schema",
        r'''We're building an IoT platform that ingests sensor readings from 50,000 devices. Each device reports temperature, humidity, and battery level every 30 seconds. That's ~144 million rows per day. We're using PostgreSQL and queries are:

1. Latest reading per device (dashboard)
2. Time-series chart for one device (last 24h, 7d, 30d)
3. Aggregate stats per device per hour (reports)
4. Alert: any device where temperature > threshold in last 5 minutes

Our current schema is a simple append-only table:

CREATE TABLE sensor_readings (
    id BIGSERIAL PRIMARY KEY,
    device_id INTEGER NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    temperature DECIMAL(5,2),
    humidity DECIMAL(5,2),
    battery_pct DECIMAL(5,2)
);

At 144M rows/day, this won't scale. What time-series data modeling strategy should we use?''',
        r'''<think>
144M rows/day = ~1.67K inserts/sec. Over 30 days = 4.3 billion rows. Over a year = 52.6 billion rows. A single unpartitioned PostgreSQL table will die long before that.

Let me think about what's needed:

**Query patterns:**
1. Latest reading per device → needs fast "most recent per group" query
2. Time-series chart → range scan on (device_id, ts) for one device
3. Hourly aggregates → GROUP BY device_id, date_trunc('hour', ts)
4. Recent alert check → scan last 5 minutes for threshold violations

**Problem 1: Table size**
A single table with 4.3B rows:
- Indexes are massive (B-tree on device_id, ts)
- VACUUM takes hours (every UPDATE/DELETE generates dead tuples)
- Query plans become unreliable with stale statistics

Solution: Time-based partitioning. Partition by day or week so each partition is manageable (~144M or 1B rows).

**Problem 2: Partition pruning**
With partitioning by ts range, queries that filter on ts automatically skip irrelevant partitions. "Last 24h" only reads 1-2 partitions instead of scanning billions of rows.

**Problem 3: Latest reading per device**
This is the hardest query to make fast. With 50K devices:

```sql
SELECT DISTINCT ON (device_id) *
FROM sensor_readings
ORDER BY device_id, ts DESC;
```

This scans the entire table (or at least 50K index lookups). Even with partitioning, it must check the most recent partition for each device.

Solution: Maintain a materialized "latest readings" table:

```sql
CREATE TABLE device_latest_readings (
    device_id INTEGER PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    temperature DECIMAL(5,2),
    humidity DECIMAL(5,2),
    battery_pct DECIMAL(5,2)
);
```

Updated on every insert via trigger or UPSERT. Dashboard query becomes a simple scan of 50K rows.

**Problem 4: Retention and rollup**
You don't need per-second granularity forever. Strategy:
- Raw data: keep for 7-30 days
- Hourly rollup: keep for 1 year
- Daily rollup: keep forever

Drop old raw partitions; keep rollup tables.

**Problem 5: INSERT throughput**
1.67K inserts/sec is manageable for PostgreSQL with:
- Batched inserts (COPY or multi-row INSERT)
- No unnecessary indexes on the raw table
- Partitioned so each partition has smaller indexes

**Should they use TimescaleDB?**
TimescaleDB (PostgreSQL extension) is purpose-built for this:
- Automatic partitioning (hypertables)
- Built-in compression (10-20x for time-series data)
- Continuous aggregates (materialized rollups that auto-update)
- Retention policies (auto-drop old data)

If they can install extensions, TimescaleDB is the answer. If not, manual partitioning + rollup tables.

**My recommendation:**
1. TimescaleDB hypertable with compression
2. Continuous aggregate for hourly stats
3. Materialized latest-readings table
4. Retention policy: 30 days raw, 1 year hourly, forever daily
</think>

### The challenge: 144M rows/day requires time-series-specific design

A single table will fail within weeks. You need partitioning, rollup aggregates, and retention policies.

### Option A: TimescaleDB (recommended if you can install extensions)

```sql
-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create the hypertable (auto-partitions by time)
CREATE TABLE sensor_readings (
    ts TIMESTAMPTZ NOT NULL,
    device_id INTEGER NOT NULL,
    temperature DECIMAL(5,2),
    humidity DECIMAL(5,2),
    battery_pct DECIMAL(5,2)
);

-- Convert to hypertable: auto-partitions by 1-day chunks
SELECT create_hypertable('sensor_readings', 'ts',
    chunk_time_interval => INTERVAL '1 day');

-- Composite index for per-device time range queries
CREATE INDEX idx_readings_device_ts
    ON sensor_readings (device_id, ts DESC);

-- Enable compression on chunks older than 2 days (10-20x space savings)
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id',
    timescaledb.compress_orderby = 'ts DESC'
);
SELECT add_compression_policy('sensor_readings', INTERVAL '2 days');

-- Retention: drop raw data older than 30 days
SELECT add_retention_policy('sensor_readings', INTERVAL '30 days');
```

### Continuous aggregates for hourly rollups

```sql
-- Materialized hourly stats (auto-refreshed)
CREATE MATERIALIZED VIEW sensor_hourly
WITH (timescaledb.continuous) AS
SELECT
    device_id,
    time_bucket('1 hour', ts) AS hour,
    AVG(temperature) AS avg_temp,
    MIN(temperature) AS min_temp,
    MAX(temperature) AS max_temp,
    AVG(humidity) AS avg_humidity,
    AVG(battery_pct) AS avg_battery,
    COUNT(*) AS reading_count
FROM sensor_readings
GROUP BY device_id, time_bucket('1 hour', ts);

-- Auto-refresh: update hourly stats every 5 minutes
SELECT add_continuous_aggregate_policy('sensor_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '5 minutes');

-- Keep hourly data for 1 year
SELECT add_retention_policy('sensor_hourly', INTERVAL '1 year');
```

### Latest reading per device (materialized for O(1) dashboard)

```sql
-- Materialized latest readings for the dashboard
CREATE TABLE device_latest (
    device_id INTEGER PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    temperature DECIMAL(5,2),
    humidity DECIMAL(5,2),
    battery_pct DECIMAL(5,2),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- UPSERT on every batch of readings
INSERT INTO device_latest (device_id, ts, temperature, humidity, battery_pct)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (device_id) DO UPDATE SET
    ts = EXCLUDED.ts,
    temperature = EXCLUDED.temperature,
    humidity = EXCLUDED.humidity,
    battery_pct = EXCLUDED.battery_pct,
    updated_at = NOW()
WHERE EXCLUDED.ts > device_latest.ts;  -- Only update if newer

-- Dashboard query: 50K rows, instant
SELECT d.name, dl.* FROM device_latest dl
JOIN devices d ON d.id = dl.device_id;
```

### Option B: Pure PostgreSQL (no extensions)

```sql
-- Manual partitioning by day
CREATE TABLE sensor_readings (
    ts TIMESTAMPTZ NOT NULL,
    device_id INTEGER NOT NULL,
    temperature DECIMAL(5,2),
    humidity DECIMAL(5,2),
    battery_pct DECIMAL(5,2)
) PARTITION BY RANGE (ts);

-- Create daily partitions (automate with pg_cron or app code)
CREATE TABLE sensor_readings_20260305
    PARTITION OF sensor_readings
    FOR VALUES FROM ('2026-03-05') TO ('2026-03-06');

CREATE INDEX ON sensor_readings_20260305 (device_id, ts DESC);

-- Hourly rollup table (populated by cron job)
CREATE TABLE sensor_hourly (
    device_id INTEGER NOT NULL,
    hour TIMESTAMPTZ NOT NULL,
    avg_temp DECIMAL(5,2),
    min_temp DECIMAL(5,2),
    max_temp DECIMAL(5,2),
    avg_humidity DECIMAL(5,2),
    avg_battery DECIMAL(5,2),
    reading_count INTEGER,
    PRIMARY KEY (device_id, hour)
);

-- Rollup job (run every hour)
INSERT INTO sensor_hourly
SELECT
    device_id,
    date_trunc('hour', ts) AS hour,
    AVG(temperature), MIN(temperature), MAX(temperature),
    AVG(humidity), AVG(battery_pct), COUNT(*)
FROM sensor_readings
WHERE ts >= date_trunc('hour', NOW() - INTERVAL '1 hour')
  AND ts < date_trunc('hour', NOW())
GROUP BY device_id, date_trunc('hour', ts)
ON CONFLICT (device_id, hour) DO UPDATE SET
    avg_temp = EXCLUDED.avg_temp,
    reading_count = EXCLUDED.reading_count;
```

### Alert query (optimized)

```sql
-- Partial index for alert-worthy temperatures
CREATE INDEX idx_readings_temp_alert
    ON sensor_readings (device_id, ts DESC)
    WHERE temperature > 80.0;

-- Alert check: only scans the partial index
SELECT DISTINCT device_id
FROM sensor_readings
WHERE ts > NOW() - INTERVAL '5 minutes'
  AND temperature > 80.0;
```

### Data volume projections

| Retention tier | Duration | Rows | Storage (uncompressed) | Storage (compressed) |
|---------------|----------|------|----------------------|---------------------|
| Raw readings | 30 days | 4.3B | ~200 GB | ~15 GB (TimescaleDB) |
| Hourly rollup | 1 year | 438M | ~20 GB | ~2 GB |
| Daily rollup | Forever | 18M/year | ~1 GB | ~100 MB |'''
    ),
    (
        "thinking/datamodel-timeseries-downsampling",
        r'''Our monitoring system stores metrics at 1-second granularity. When users view a 30-day chart, we return 2.6 million data points per metric — way too many for the frontend to render. We need to downsample: return ~1000 points regardless of the time range.

Currently we do this in the application:

def get_metric_chart(metric_id, start, end):
    rows = db.query(
        "SELECT ts, value FROM metrics WHERE metric_id = %s AND ts BETWEEN %s AND %s ORDER BY ts",
        metric_id, start, end
    )
    # Downsample in Python: every Nth point
    step = max(1, len(rows) // 1000)
    return rows[::step]

This fetches millions of rows from the DB just to throw most away. How do we push downsampling to the database?''',
        r'''<think>
The problem is clear: fetching 2.6M rows to return 1K is wasteful. We need to downsample in the database.

**Approach 1: time_bucket aggregation (best)**

Divide the time range into N equal buckets and aggregate each:

```sql
SELECT
    time_bucket($interval, ts) AS bucket,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value
FROM metrics
WHERE metric_id = $1 AND ts BETWEEN $2 AND $3
GROUP BY bucket
ORDER BY bucket;
```

Where $interval = (end - start) / 1000.

For 30 days / 1000 points = 43.2 minute buckets.
For 1 hour / 1000 points = 3.6 second buckets.

Pros:
- Returns exactly ~1000 rows
- Preserves min/max (important for alerting/anomaly visibility)
- DB does the work — minimal data transfer
- Works with any time range

**Approach 2: LTTB (Largest Triangle Three Buckets)**

A visual downsampling algorithm that preserves the shape of the chart better than simple averaging. Used by Grafana and many charting libraries.

Can be implemented as a PostgreSQL function or done application-side on pre-aggregated data.

**Approach 3: Pre-computed rollup tables**

Store multiple resolutions:
- 1-second raw (7 days retention)
- 1-minute avg/min/max (90 days)
- 5-minute avg/min/max (1 year)
- 1-hour avg/min/max (forever)

Query the appropriate resolution based on the time range:
- Last 1 hour → raw 1-second data (3600 points)
- Last 24 hours → 1-minute rollup (1440 points)
- Last 7 days → 5-minute rollup (2016 points)
- Last 30 days → 1-hour rollup (720 points)

This is the most common production approach because:
1. No computation at query time
2. Predictable performance
3. Older data uses less storage
4. Each resolution table is small and fast

**Approach 4: Dynamic interval calculation**

Calculate the bucket interval dynamically:

```python
target_points = 1000
total_seconds = (end - start).total_seconds()
bucket_seconds = max(1, int(total_seconds / target_points))
```

Then use this in the GROUP BY. This works but:
- The DB must scan all raw rows and aggregate
- For 30 days of 1-second data, that's 2.6M rows aggregated per query
- Still slow at scale

**Best solution: Pre-computed rollups + dynamic resolution selection**

Combine rollup tables with automatic tier selection. The application picks the right table based on the time range, then does a simple range scan.

If the rollup resolution gives < 1000 points, no further downsampling needed.
If it gives > 1000 points (e.g., 1-minute rollup for 7 days = 10K points), apply time_bucket on top.
</think>

### Root cause: You're fetching millions of rows to discard 99.9% of them

Push the downsampling to the database using pre-computed rollup tables and dynamic resolution selection.

### Multi-resolution rollup schema

```sql
-- Raw data: 1-second granularity (short retention)
CREATE TABLE metrics_raw (
    ts TIMESTAMPTZ NOT NULL,
    metric_id INTEGER NOT NULL,
    value DOUBLE PRECISION NOT NULL
) PARTITION BY RANGE (ts);
-- Retention: 7 days

-- 1-minute rollups
CREATE TABLE metrics_1m (
    ts TIMESTAMPTZ NOT NULL,
    metric_id INTEGER NOT NULL,
    avg_value DOUBLE PRECISION NOT NULL,
    min_value DOUBLE PRECISION NOT NULL,
    max_value DOUBLE PRECISION NOT NULL,
    sample_count INTEGER NOT NULL,
    PRIMARY KEY (metric_id, ts)
);
-- Retention: 90 days

-- 1-hour rollups
CREATE TABLE metrics_1h (
    ts TIMESTAMPTZ NOT NULL,
    metric_id INTEGER NOT NULL,
    avg_value DOUBLE PRECISION NOT NULL,
    min_value DOUBLE PRECISION NOT NULL,
    max_value DOUBLE PRECISION NOT NULL,
    sample_count INTEGER NOT NULL,
    PRIMARY KEY (metric_id, ts)
);
-- Retention: forever
```

### Rollup jobs

```sql
-- 1-minute rollup (runs every minute via pg_cron)
INSERT INTO metrics_1m (ts, metric_id, avg_value, min_value, max_value, sample_count)
SELECT
    date_trunc('minute', ts) AS ts,
    metric_id,
    AVG(value),
    MIN(value),
    MAX(value),
    COUNT(*)
FROM metrics_raw
WHERE ts >= date_trunc('minute', NOW() - INTERVAL '2 minutes')
  AND ts < date_trunc('minute', NOW())
GROUP BY metric_id, date_trunc('minute', ts)
ON CONFLICT (metric_id, ts) DO UPDATE SET
    avg_value = EXCLUDED.avg_value,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value,
    sample_count = EXCLUDED.sample_count;

-- 1-hour rollup (runs every hour, aggregates from 1m table)
INSERT INTO metrics_1h (ts, metric_id, avg_value, min_value, max_value, sample_count)
SELECT
    date_trunc('hour', ts) AS ts,
    metric_id,
    SUM(avg_value * sample_count) / SUM(sample_count),  -- weighted avg
    MIN(min_value),
    MAX(max_value),
    SUM(sample_count)
FROM metrics_1m
WHERE ts >= date_trunc('hour', NOW() - INTERVAL '2 hours')
  AND ts < date_trunc('hour', NOW())
GROUP BY metric_id, date_trunc('hour', ts)
ON CONFLICT (metric_id, ts) DO UPDATE SET
    avg_value = EXCLUDED.avg_value,
    min_value = EXCLUDED.min_value,
    max_value = EXCLUDED.max_value,
    sample_count = EXCLUDED.sample_count;
```

### Automatic resolution selection

```python
from datetime import timedelta

TARGET_POINTS = 1000

def get_metric_chart(metric_id: int, start: datetime, end: datetime):
    """Select optimal resolution table and fetch ~1000 points."""
    duration = end - start

    # Pick the right resolution table
    if duration <= timedelta(hours=1):
        # 1 hour at 1s = 3600 points — use raw
        table = "metrics_raw"
        value_col = "value AS avg_value, value AS min_value, value AS max_value"
    elif duration <= timedelta(days=7):
        # 7 days at 1m = 10080 points — use 1m rollup
        table = "metrics_1m"
        value_col = "avg_value, min_value, max_value"
    else:
        # 30+ days at 1h = 720 points — use 1h rollup
        table = "metrics_1h"
        value_col = "avg_value, min_value, max_value"

    # If still too many points, apply time_bucket
    estimated_points = estimate_points(table, duration)

    if estimated_points <= TARGET_POINTS * 1.5:
        # Direct query — few enough points
        return db.fetch_all(f"""
            SELECT ts, {value_col}
            FROM {table}
            WHERE metric_id = %s AND ts BETWEEN %s AND %s
            ORDER BY ts
        """, metric_id, start, end)
    else:
        # Downsample with time_bucket
        bucket_seconds = int(duration.total_seconds() / TARGET_POINTS)
        return db.fetch_all(f"""
            SELECT
                date_bin('{bucket_seconds} seconds', ts, %s) AS ts,
                AVG(avg_value) AS avg_value,
                MIN(min_value) AS min_value,
                MAX(max_value) AS max_value
            FROM {table}
            WHERE metric_id = %s AND ts BETWEEN %s AND %s
            GROUP BY 1
            ORDER BY 1
        """, start, metric_id, start, end)

def estimate_points(table: str, duration: timedelta) -> int:
    resolution = {
        "metrics_raw": 1,
        "metrics_1m": 60,
        "metrics_1h": 3600,
    }
    return int(duration.total_seconds() / resolution[table])
```

### Performance comparison

```
Query: 30 days of data for 1 metric

Before (fetch all raw):
  Rows scanned: 2,592,000
  Data transfer: ~50 MB
  Response time: 3.2 seconds

After (1h rollup, direct):
  Rows scanned: 720
  Data transfer: ~28 KB
  Response time: 2 ms
```

### Frontend receives min/max envelope for accurate charts

```json
{
  "metric_id": 42,
  "resolution": "1h",
  "points": [
    {"ts": "2026-02-03T00:00:00Z", "avg": 72.3, "min": 68.1, "max": 78.9},
    {"ts": "2026-02-03T01:00:00Z", "avg": 71.8, "min": 67.5, "max": 76.2}
  ]
}
```

The min/max values let the chart render a shaded "envelope" showing the full range within each bucket, so users see peaks and valleys that averaging alone would hide.'''
    ),
    (
        "thinking/datamodel-timeseries-wide-vs-narrow",
        r'''We're designing a schema for application performance monitoring (APM). Each request generates metrics:

- response_time_ms, cpu_time_ms, db_query_count, db_time_ms, memory_mb, error_count, cache_hits, cache_misses

We're debating two approaches:

-- Narrow (EAV-style): one row per metric per timestamp
CREATE TABLE metrics_narrow (
    ts TIMESTAMPTZ NOT NULL,
    service VARCHAR(100) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    value DOUBLE PRECISION NOT NULL
);

-- Wide: one row per timestamp with all metrics as columns
CREATE TABLE metrics_wide (
    ts TIMESTAMPTZ NOT NULL,
    service VARCHAR(100) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    response_time_ms DOUBLE PRECISION,
    cpu_time_ms DOUBLE PRECISION,
    db_query_count DOUBLE PRECISION,
    db_time_ms DOUBLE PRECISION,
    memory_mb DOUBLE PRECISION,
    error_count DOUBLE PRECISION,
    cache_hits DOUBLE PRECISION,
    cache_misses DOUBLE PRECISION
);

We have 200 endpoints averaging 100 requests/sec. Which schema is better?''',
        r'''<think>
Let me calculate the data volume and compare the schemas.

**Data volume:**
200 endpoints * 100 req/sec = 20K events/sec

If we store per-request:
- Narrow: 20K * 8 metrics = 160K rows/sec = 13.8 BILLION rows/day. Way too many.
- Wide: 20K rows/sec = 1.7 billion rows/day. Still too many.

We clearly need to pre-aggregate, not store per-request. Let's say we aggregate to 10-second buckets:
- 200 endpoints * 6 buckets/min * 60 min/hr * 24 hr = 1.73M rows/day for wide
- 200 endpoints * 6 * 60 * 24 * 8 metrics = 13.8M rows/day for narrow

So narrow creates 8x more rows than wide for the same data.

**Comparison:**

**Narrow (EAV) pros:**
1. Adding new metrics requires no schema change
2. Sparse data is storage-efficient (only store metrics that have values)
3. Queries like "SELECT * FROM metrics WHERE metric_name = 'response_time_ms'" are simple

**Narrow cons:**
1. 8x more rows means 8x more storage, indexes, vacuum work
2. Correlating metrics requires self-JOINs or pivoting: "response_time WHERE db_time > 100ms" needs a JOIN
3. Aggregation across metrics (avg response_time, sum error_count) needs FILTER or CASE
4. Row overhead (tuple header ~23 bytes in PG) per row adds up: 8 rows * 23 bytes = 184 bytes overhead vs 23 bytes for 1 wide row

**Wide pros:**
1. 8x fewer rows = less storage, smaller indexes, faster vacuum
2. Correlated queries are trivial: `WHERE response_time_ms > 500 AND error_count > 0`
3. Columnar compression works much better (all response_time values together)
4. Single row per observation = simpler GROUP BY, no pivoting
5. Type safety: each column has its own type

**Wide cons:**
1. Adding new metrics requires ALTER TABLE
2. Sparse metrics waste space (NULL columns)
3. Table gets wide with many metrics

**For APM specifically:**

APM metrics are strongly correlated — you almost always want to see response_time alongside db_time, cpu_time, etc. The narrow schema forces you to pivot/JOIN every time, which is expensive and complex.

The 8 metrics in question are all "always present" for every request — no sparsity. So NULLs aren't a concern.

Adding new metrics happens maybe once a quarter (when you instrument a new subsystem). An ALTER TABLE ADD COLUMN is cheap and infrequent.

**Verdict: Wide schema for APM metrics, pre-aggregated to 10-second or 1-minute buckets.**

The narrow/EAV schema is better for high-cardinality, sparse, heterogeneous metrics (like custom user-defined metrics where each user tracks different things). APM has a fixed, correlated set of metrics — wide wins.
</think>

### Short answer: Wide schema, pre-aggregated to 10-second buckets

Narrow (EAV) creates 8x more rows, requires self-JOINs for correlated queries, and wastes storage on row overhead. For a fixed set of correlated APM metrics, wide is superior.

### Schema design

```sql
-- Pre-aggregated wide metrics (10-second buckets)
CREATE TABLE apm_metrics (
    ts TIMESTAMPTZ NOT NULL,
    service VARCHAR(100) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    -- Aggregates per bucket
    request_count INTEGER NOT NULL,
    -- Response time
    resp_time_avg DOUBLE PRECISION NOT NULL,
    resp_time_p50 DOUBLE PRECISION,
    resp_time_p95 DOUBLE PRECISION,
    resp_time_p99 DOUBLE PRECISION,
    resp_time_max DOUBLE PRECISION,
    -- CPU
    cpu_time_avg DOUBLE PRECISION,
    -- Database
    db_query_avg DOUBLE PRECISION,
    db_time_avg DOUBLE PRECISION,
    -- Memory
    memory_avg DOUBLE PRECISION,
    -- Errors
    error_count INTEGER NOT NULL DEFAULT 0,
    error_rate DOUBLE PRECISION GENERATED ALWAYS AS (
        CASE WHEN request_count > 0
            THEN error_count::double precision / request_count
            ELSE 0 END
    ) STORED,
    -- Cache
    cache_hit_rate DOUBLE PRECISION
) PARTITION BY RANGE (ts);

-- Composite index for the most common query pattern
CREATE INDEX idx_apm_service_endpoint_ts
    ON apm_metrics (service, endpoint, ts DESC);
```

### In-memory aggregation before DB insert

```python
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import numpy as np

@dataclass
class MetricBucket:
    request_count: int = 0
    response_times: list = field(default_factory=list)
    cpu_times: list = field(default_factory=list)
    db_queries: list = field(default_factory=list)
    db_times: list = field(default_factory=list)
    memory_values: list = field(default_factory=list)
    error_count: int = 0
    cache_hits: int = 0
    cache_total: int = 0

class MetricAggregator:
    """Aggregate raw metrics in memory, flush to DB every 10 seconds."""

    def __init__(self, flush_interval: int = 10):
        self.flush_interval = flush_interval
        self.buckets: dict[tuple, MetricBucket] = defaultdict(MetricBucket)

    def record(self, service: str, endpoint: str, metrics: dict):
        bucket_ts = self._bucket_time(datetime.utcnow())
        key = (bucket_ts, service, endpoint)
        b = self.buckets[key]
        b.request_count += 1
        b.response_times.append(metrics['response_time_ms'])
        b.cpu_times.append(metrics['cpu_time_ms'])
        b.db_queries.append(metrics['db_query_count'])
        b.db_times.append(metrics['db_time_ms'])
        b.memory_values.append(metrics['memory_mb'])
        b.error_count += metrics.get('error_count', 0)
        b.cache_hits += metrics.get('cache_hits', 0)
        b.cache_total += metrics.get('cache_hits', 0) + metrics.get('cache_misses', 0)

    async def flush(self):
        """Flush completed buckets to the database."""
        current_bucket = self._bucket_time(datetime.utcnow())
        rows = []
        keys_to_remove = []

        for key, b in self.buckets.items():
            if key[0] >= current_bucket:
                continue  # Still accumulating
            ts, service, endpoint = key
            rt = np.array(b.response_times)
            rows.append((
                ts, service, endpoint, b.request_count,
                float(np.mean(rt)),
                float(np.percentile(rt, 50)),
                float(np.percentile(rt, 95)),
                float(np.percentile(rt, 99)),
                float(np.max(rt)),
                float(np.mean(b.cpu_times)),
                float(np.mean(b.db_queries)),
                float(np.mean(b.db_times)),
                float(np.mean(b.memory_values)),
                b.error_count,
                b.cache_hits / b.cache_total if b.cache_total > 0 else None,
            ))
            keys_to_remove.append(key)

        if rows:
            await db.executemany("""
                INSERT INTO apm_metrics (
                    ts, service, endpoint, request_count,
                    resp_time_avg, resp_time_p50, resp_time_p95,
                    resp_time_p99, resp_time_max,
                    cpu_time_avg, db_query_avg, db_time_avg,
                    memory_avg, error_count, cache_hit_rate
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
            """, rows)

        for key in keys_to_remove:
            del self.buckets[key]

    def _bucket_time(self, dt: datetime) -> datetime:
        seconds = (dt.second // self.flush_interval) * self.flush_interval
        return dt.replace(second=seconds, microsecond=0)
```

### Query comparison: Wide vs Narrow

```sql
-- "Slow requests with high DB time" — common APM investigation

-- Wide (simple):
SELECT ts, endpoint, resp_time_avg, db_time_avg, db_query_avg
FROM apm_metrics
WHERE service = 'api' AND resp_time_avg > 500 AND db_time_avg > 200
ORDER BY ts DESC LIMIT 50;

-- Narrow (requires self-join or pivot — complex and slow):
SELECT r.ts, r.endpoint, r.value AS resp_time, d.value AS db_time
FROM metrics_narrow r
JOIN metrics_narrow d ON d.ts = r.ts AND d.endpoint = r.endpoint
    AND d.metric_name = 'db_time_ms'
WHERE r.metric_name = 'response_time_ms'
    AND r.service = 'api'
    AND r.value > 500 AND d.value > 200
ORDER BY r.ts DESC LIMIT 50;
```

### Storage comparison (per day, 200 endpoints, 10-sec buckets)

| Schema | Rows/day | Row size | Storage/day |
|--------|----------|----------|-------------|
| Narrow (per metric) | 13.8M | ~80 bytes | ~1.1 GB |
| Wide (all metrics) | 1.73M | ~150 bytes | ~260 MB |
| Wide + compression | 1.73M | ~15 bytes | ~26 MB |

### When to use narrow (EAV) instead

Use narrow when metrics are user-defined, highly sparse, or unpredictable:
- Custom business metrics (each customer tracks different KPIs)
- IoT with heterogeneous sensor types
- Feature flags / A/B test metrics that change weekly'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
