"""Data engineering — ETL/ELT patterns, data pipelines, data quality, lakehouse architecture."""

PAIRS = [
    (
        "data-engineering/etl-patterns",
        "Show ETL vs ELT patterns with Python. Include incremental loading, change data capture, idempotent transformations, and error handling.",
        '''ETL/ELT pipeline patterns for data engineering:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Generator
from enum import Enum
import hashlib
import json
import logging

log = logging.getLogger(__name__)

class LoadStrategy(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    CDC = "cdc"  # Change data capture

@dataclass
class PipelineState:
    """Track pipeline execution state for incremental loading."""
    pipeline_name: str
    last_run: Optional[datetime] = None
    last_watermark: Optional[str] = None  # Last processed ID/timestamp
    rows_processed: int = 0
    status: str = "pending"

class DataPipeline:
    """Idempotent ETL pipeline with incremental loading."""

    def __init__(self, source_db, target_db, state_store):
        self.source = source_db
        self.target = target_db
        self.state = state_store

    def run(self, pipeline_name: str, strategy: LoadStrategy = LoadStrategy.INCREMENTAL):
        state = self.state.get(pipeline_name) or PipelineState(pipeline_name)
        state.status = "running"
        self.state.save(state)

        try:
            if strategy == LoadStrategy.FULL:
                rows = self._extract_full(pipeline_name)
            elif strategy == LoadStrategy.INCREMENTAL:
                rows = self._extract_incremental(pipeline_name, state.last_watermark)
            elif strategy == LoadStrategy.CDC:
                rows = self._extract_cdc(pipeline_name, state.last_watermark)

            transformed = self._transform(rows, pipeline_name)
            count, new_watermark = self._load(transformed, pipeline_name, strategy)

            state.last_run = datetime.now(timezone.utc)
            state.last_watermark = new_watermark
            state.rows_processed = count
            state.status = "completed"

        except Exception as e:
            state.status = f"failed: {str(e)[:200]}"
            log.error(f"Pipeline {pipeline_name} failed", exc_info=True)
            raise
        finally:
            self.state.save(state)

    def _extract_incremental(self, pipeline: str, watermark: Optional[str]) -> Generator:
        """Extract only new/changed rows since last watermark."""
        if watermark:
            query = f"""
                SELECT * FROM {pipeline}_source
                WHERE updated_at > %(watermark)s
                ORDER BY updated_at ASC
            """
            params = {"watermark": watermark}
        else:
            query = f"SELECT * FROM {pipeline}_source ORDER BY updated_at ASC"
            params = {}

        # Stream results to avoid memory issues
        cursor = self.source.cursor(name=f"extract_{pipeline}")
        cursor.execute(query, params)

        while True:
            batch = cursor.fetchmany(1000)
            if not batch:
                break
            yield from batch

        cursor.close()

    def _transform(self, rows: Generator, pipeline: str) -> Generator:
        """Apply transformations with data quality checks."""
        for row in rows:
            try:
                transformed = self._apply_rules(row, pipeline)
                if self._validate(transformed, pipeline):
                    yield transformed
                else:
                    self._send_to_dead_letter(row, "validation_failed", pipeline)
            except Exception as e:
                self._send_to_dead_letter(row, str(e), pipeline)

    def _load(self, rows: Generator, pipeline: str, strategy: LoadStrategy) -> tuple[int, str]:
        """Idempotent load with upsert."""
        count = 0
        last_watermark = None

        batch = []
        for row in rows:
            batch.append(row)
            last_watermark = str(row.get("updated_at", ""))

            if len(batch) >= 1000:
                self._upsert_batch(batch, pipeline)
                count += len(batch)
                batch = []

        if batch:
            self._upsert_batch(batch, pipeline)
            count += len(batch)

        return count, last_watermark

    def _upsert_batch(self, batch: list[dict], pipeline: str):
        """Idempotent upsert — safe to re-run."""
        # PostgreSQL UPSERT
        columns = list(batch[0].keys())
        values_template = ", ".join([f"%({c})s" for c in columns])
        update_set = ", ".join([f"{c} = EXCLUDED.{c}" for c in columns if c != "id"])

        query = f"""
            INSERT INTO {pipeline}_target ({", ".join(columns)})
            VALUES ({values_template})
            ON CONFLICT (id)
            DO UPDATE SET {update_set}, _loaded_at = NOW()
        """
        self.target.executemany(query, batch)
        self.target.commit()

# --- Data Quality Framework ---

@dataclass
class DataQualityCheck:
    name: str
    query: str
    expected: str  # "empty" (no rows = pass), "non_empty", or a count
    severity: str = "warning"  # "warning" or "error"

class DataQualityRunner:
    def __init__(self, db):
        self.db = db

    def run_checks(self, checks: list[DataQualityCheck]) -> list[dict]:
        results = []
        for check in checks:
            count = self.db.execute(check.query).scalar()
            passed = (
                (count == 0 and check.expected == "empty") or
                (count > 0 and check.expected == "non_empty") or
                (str(count) == check.expected)
            )
            results.append({
                "check": check.name,
                "passed": passed,
                "actual_count": count,
                "severity": check.severity,
            })
            if not passed and check.severity == "error":
                log.error(f"DQ check FAILED: {check.name} (count={count})")
        return results

# Standard data quality checks
QUALITY_CHECKS = [
    DataQualityCheck(
        "no_null_emails",
        "SELECT COUNT(*) FROM users WHERE email IS NULL",
        "empty",
        severity="error",
    ),
    DataQualityCheck(
        "no_duplicate_orders",
        "SELECT COUNT(*) FROM (SELECT order_id, COUNT(*) c FROM orders GROUP BY order_id HAVING c > 1) t",
        "empty",
        severity="error",
    ),
    DataQualityCheck(
        "reasonable_order_amounts",
        "SELECT COUNT(*) FROM orders WHERE amount < 0 OR amount > 100000",
        "empty",
        severity="warning",
    ),
    DataQualityCheck(
        "data_freshness",
        "SELECT COUNT(*) FROM orders WHERE created_at > NOW() - INTERVAL '1 hour'",
        "non_empty",
        severity="warning",
    ),
]

# --- SCD Type 2 (Slowly Changing Dimensions) ---

def scd_type2_merge(source_rows: list[dict], target_table: str, db,
                    natural_key: str, tracked_columns: list[str]):
    """Maintain history of dimension changes."""
    for row in source_rows:
        row_hash = hashlib.md5(
            json.dumps({k: str(row[k]) for k in tracked_columns}, sort_keys=True).encode()
        ).hexdigest()

        # Check if current record matches
        current = db.execute(f"""
            SELECT *, md5_hash FROM {target_table}
            WHERE {natural_key} = %(key)s AND is_current = TRUE
        """, {"key": row[natural_key]}).fetchone()

        if current is None:
            # New record
            db.execute(f"""
                INSERT INTO {target_table} ({", ".join(row.keys())}, effective_from, is_current, md5_hash)
                VALUES ({", ".join([f"%({k})s" for k in row.keys()])}, NOW(), TRUE, %(hash)s)
            """, {**row, "hash": row_hash})
        elif current["md5_hash"] != row_hash:
            # Changed — close old, insert new
            db.execute(f"""
                UPDATE {target_table}
                SET is_current = FALSE, effective_to = NOW()
                WHERE {natural_key} = %(key)s AND is_current = TRUE
            """, {"key": row[natural_key]})
            db.execute(f"""
                INSERT INTO {target_table} ({", ".join(row.keys())}, effective_from, is_current, md5_hash)
                VALUES ({", ".join([f"%({k})s" for k in row.keys()])}, NOW(), TRUE, %(hash)s)
            """, {**row, "hash": row_hash})
    db.commit()
```

Pipeline architecture patterns:
- **Batch ETL** — scheduled, processes all data since last run
- **Micro-batch** — frequent small batches (every 5-15 min)
- **Streaming** — real-time event processing (Kafka → Flink)
- **ELT** — load raw to warehouse, transform with SQL (dbt)
- **CDC** — capture database changes via WAL/binlog'''
    ),
    (
        "data-engineering/streaming-architectures",
        "Explain stream processing architectures with Kafka. Cover producers, consumers, exactly-once semantics, stream joins, and windowing.",
        '''Stream processing with Kafka and Python:

```python
from confluent_kafka import Producer, Consumer, KafkaError
from confluent_kafka.admin import AdminClient, NewTopic
from dataclasses import dataclass
from datetime import datetime, timezone
from collections import defaultdict
import json
import time

# --- Producer with delivery guarantees ---

class ReliableProducer:
    def __init__(self, bootstrap_servers: str):
        self.producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",              # Wait for all replicas
            "retries": 3,
            "retry.backoff.ms": 1000,
            "enable.idempotence": True, # Exactly-once producer
            "max.in.flight.requests.per.connection": 5,
            "compression.type": "lz4",
        })

    def send(self, topic: str, key: str, value: dict,
             headers: dict = None):
        """Send with delivery confirmation."""
        payload = json.dumps(value).encode()
        kafka_headers = [(k, v.encode()) for k, v in (headers or {}).items()]

        self.producer.produce(
            topic=topic,
            key=key.encode(),
            value=payload,
            headers=kafka_headers,
            callback=self._delivery_callback,
        )
        self.producer.poll(0)  # Trigger callbacks

    def _delivery_callback(self, err, msg):
        if err:
            print(f"Delivery failed: {err}")
        else:
            print(f"Delivered to {msg.topic()}[{msg.partition()}] @ {msg.offset()}")

    def flush(self, timeout=30):
        self.producer.flush(timeout)

# --- Consumer with exactly-once processing ---

class ExactlyOnceConsumer:
    """Consumer with manual offset management for exactly-once."""

    def __init__(self, bootstrap_servers: str, group_id: str,
                 topics: list[str]):
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,  # Manual commits
            "max.poll.interval.ms": 300000,
        })
        self.consumer.subscribe(topics)
        self.processed_offsets = {}

    def process_messages(self, handler, batch_size: int = 100):
        """Process with transactional offset commits."""
        while True:
            messages = []
            for _ in range(batch_size):
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    break
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise Exception(msg.error())
                messages.append(msg)

            if not messages:
                continue

            try:
                # Process batch
                for msg in messages:
                    value = json.loads(msg.value().decode())
                    handler(msg.key().decode(), value, msg.headers())

                # Commit offsets after successful processing
                self.consumer.commit(asynchronous=False)

            except Exception as e:
                print(f"Processing failed: {e}")
                # Don't commit — messages will be reprocessed
                # Handler must be idempotent!

    def close(self):
        self.consumer.close()

# --- Stream Processing (windowed aggregations) ---

class StreamProcessor:
    """Tumbling window aggregation over event streams."""

    def __init__(self, window_seconds: int = 60):
        self.window_size = window_seconds
        self.windows: dict[str, dict] = defaultdict(lambda: {
            "count": 0, "sum": 0.0, "min": float("inf"), "max": float("-inf"),
        })

    def _window_key(self, timestamp: float, group_key: str) -> str:
        window_start = int(timestamp) // self.window_size * self.window_size
        return f"{group_key}:{window_start}"

    def process_event(self, event: dict) -> list[dict]:
        """Process event and emit completed windows."""
        ts = event["timestamp"]
        key = event["key"]
        value = event["value"]

        wkey = self._window_key(ts, key)
        window = self.windows[wkey]
        window["count"] += 1
        window["sum"] += value
        window["min"] = min(window["min"], value)
        window["max"] = max(window["max"], value)

        # Emit and clean expired windows
        current_window = int(ts) // self.window_size * self.window_size
        results = []
        expired = []

        for wk, w in self.windows.items():
            parts = wk.rsplit(":", 1)
            window_time = int(parts[1])
            if window_time < current_window - self.window_size:
                results.append({
                    "key": parts[0],
                    "window_start": window_time,
                    "window_end": window_time + self.window_size,
                    **w,
                    "avg": w["sum"] / w["count"],
                })
                expired.append(wk)

        for wk in expired:
            del self.windows[wk]

        return results

# --- Stream-Table Join ---

class StreamTableJoin:
    """Join streaming events with a lookup table (enrichment)."""

    def __init__(self):
        self.table: dict[str, dict] = {}  # Materialized table

    def update_table(self, key: str, value: dict):
        """Update lookup table from changelog topic."""
        if value is None:
            self.table.pop(key, None)  # Tombstone = delete
        else:
            self.table[key] = value

    def join(self, event: dict, join_key: str) -> dict:
        """Enrich event with table data."""
        lookup_key = event.get(join_key)
        table_data = self.table.get(lookup_key, {})
        return {**event, **table_data}

# Usage: enrich order events with user details
enricher = StreamTableJoin()

# Consume user updates (compact topic)
# enricher.update_table(user_id, user_data)

# Join order events
# enriched_order = enricher.join(order_event, "user_id")

# --- Topic Design ---

TOPIC_DESIGN = """
Topic naming: {domain}.{entity}.{event_type}
Examples:
  orders.order.created
  orders.order.fulfilled
  payments.payment.processed
  users.user.updated

Partitioning:
  - Partition by entity ID for ordering guarantees
  - Same user's events always in same partition
  - Consumer group parallelism = partition count

Retention:
  - Event topics: 7-30 days
  - Changelog topics: compact (keep latest per key forever)
  - Archival: sink to S3/data lake for long-term
"""
```

Kafka guarantees:
- **At-most-once**: auto-commit before processing (may lose messages)
- **At-least-once**: commit after processing, idempotent consumer
- **Exactly-once**: transactional producer + consumer (enable.idempotence + read_committed)'''
    ),
    (
        "data-engineering/dbt-patterns",
        "Show dbt (data build tool) patterns: model organization, incremental models, testing, documentation, and macros.",
        '''dbt patterns for analytics engineering:

```sql
-- --- Model Organization ---
-- models/
--   staging/          -- 1:1 with source tables, light cleaning
--     stg_orders.sql
--     stg_users.sql
--   intermediate/     -- Business logic building blocks
--     int_order_items.sql
--   marts/             -- Final business-facing models
--     fct_orders.sql   -- Facts (events/transactions)
--     dim_users.sql    -- Dimensions (entities)

-- --- Staging Model (CTE-based) ---
-- models/staging/stg_orders.sql

WITH source AS (
    SELECT * FROM {{ source('ecommerce', 'raw_orders') }}
),

renamed AS (
    SELECT
        id AS order_id,
        user_id,
        CAST(order_date AS DATE) AS order_date,
        CAST(amount AS DECIMAL(10, 2)) AS order_amount,
        LOWER(status) AS order_status,
        CAST(created_at AS TIMESTAMP) AS created_at,
        CAST(updated_at AS TIMESTAMP) AS updated_at
    FROM source
    WHERE id IS NOT NULL  -- Filter corrupt rows
)

SELECT * FROM renamed

-- --- Incremental Model ---
-- models/marts/fct_orders.sql

{{
    config(
        materialized='incremental',
        unique_key='order_id',
        incremental_strategy='merge',
        on_schema_change='append_new_columns',
    )
}}

WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
    {% if is_incremental() %}
        WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})
    {% endif %}
),

order_items AS (
    SELECT * FROM {{ ref('int_order_items') }}
),

final AS (
    SELECT
        o.order_id,
        o.user_id,
        o.order_date,
        o.order_status,
        COUNT(oi.item_id) AS item_count,
        SUM(oi.quantity) AS total_quantity,
        SUM(oi.line_total) AS order_total,
        o.created_at,
        o.updated_at
    FROM orders o
    LEFT JOIN order_items oi ON o.order_id = oi.order_id
    GROUP BY 1, 2, 3, 4, 7, 8
)

SELECT * FROM final

-- --- Dimension with SCD Type 2 ---
-- models/marts/dim_users.sql

{{
    config(
        materialized='table',
    )
}}

WITH users AS (
    SELECT * FROM {{ ref('stg_users') }}
),

with_surrogate_key AS (
    SELECT
        {{ dbt_utils.generate_surrogate_key(['user_id', 'updated_at']) }} AS user_key,
        user_id,
        email,
        full_name,
        account_tier,
        region,
        created_at,
        updated_at,
        LEAD(updated_at) OVER (
            PARTITION BY user_id ORDER BY updated_at
        ) AS valid_to,
        ROW_NUMBER() OVER (
            PARTITION BY user_id ORDER BY updated_at DESC
        ) = 1 AS is_current
    FROM users
)

SELECT * FROM with_surrogate_key
```

```yaml
# --- Schema tests ---
# models/marts/schema.yml

version: 2

models:
  - name: fct_orders
    description: "Order fact table with aggregated metrics"
    columns:
      - name: order_id
        description: "Primary key"
        tests:
          - unique
          - not_null
      - name: order_total
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 100000
      - name: order_status
        tests:
          - accepted_values:
              values: ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
      - name: user_id
        tests:
          - not_null
          - relationships:
              to: ref('dim_users')
              field: user_id

  - name: dim_users
    description: "User dimension with SCD Type 2 history"
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - user_id
            - updated_at
```

```sql
-- --- Custom macro ---
-- macros/cents_to_dollars.sql

{% macro cents_to_dollars(column_name) %}
    ROUND(CAST({{ column_name }} AS DECIMAL(10, 2)) / 100, 2)
{% endmacro %}

-- Usage: SELECT {{ cents_to_dollars('amount_cents') }} AS amount_dollars

-- --- Custom test ---
-- tests/assert_positive_revenue.sql

SELECT order_id, order_total
FROM {{ ref('fct_orders') }}
WHERE order_total < 0
  AND order_status != 'cancelled'
-- Test passes if this returns 0 rows
```

dbt best practices:
1. **Staging models** — rename, cast, filter; 1:1 with sources
2. **Intermediate models** — reusable business logic (ephemeral or view)
3. **Mart models** — final tables for BI tools (table or incremental)
4. **Test everything** — unique, not_null, accepted_values, relationships
5. **Document** — descriptions on every model and column
6. **Incremental** — use for large fact tables, always handle late-arriving data'''
    ),
    (
        "data-engineering/data-lake-patterns",
        "Explain data lakehouse architecture: Delta Lake, Iceberg table formats, partitioning strategies, and query optimization.",
        '''Data lakehouse with modern table formats:

```python
# --- Delta Lake with PySpark ---

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, lit
from delta.tables import DeltaTable

spark = SparkSession.builder \\
    .appName("lakehouse") \\
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \\
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \\
    .getOrCreate()

# --- Write with partitioning ---

def write_events(df, path: str, partition_cols: list[str]):
    """Write events to Delta Lake with optimized partitioning."""
    (df
     .withColumn("_ingested_at", current_timestamp())
     .write
     .format("delta")
     .mode("append")
     .partitionBy(partition_cols)
     .option("mergeSchema", "true")  # Handle schema evolution
     .save(path))

# --- MERGE (upsert) ---

def upsert_users(new_data_df, delta_path: str):
    """SCD Type 1 merge — update existing, insert new."""
    delta_table = DeltaTable.forPath(spark, delta_path)

    (delta_table.alias("target")
     .merge(
         new_data_df.alias("source"),
         "target.user_id = source.user_id"
     )
     .whenMatchedUpdate(set={
         "email": "source.email",
         "name": "source.name",
         "updated_at": "source.updated_at",
     })
     .whenNotMatchedInsertAll()
     .execute())

# --- Time Travel ---

# Read specific version
df_v5 = spark.read.format("delta").option("versionAsOf", 5).load(path)

# Read at specific timestamp
df_yesterday = (spark.read.format("delta")
                .option("timestampAsOf", "2024-03-14")
                .load(path))

# Compare versions (audit/debugging)
changes = (spark.read.format("delta").option("versionAsOf", 10).load(path)
           .exceptAll(
               spark.read.format("delta").option("versionAsOf", 9).load(path)
           ))

# --- Table Maintenance ---

def optimize_table(delta_path: str):
    """Compact small files and run Z-ORDER for query performance."""
    delta_table = DeltaTable.forPath(spark, delta_path)

    # Compact small files into larger ones
    delta_table.optimize().executeCompaction()

    # Z-ORDER for query optimization (co-locate related data)
    delta_table.optimize().executeZOrderBy("user_id", "order_date")

    # Clean up old versions (retain 30 days)
    delta_table.vacuum(retentionHours=720)

# --- Partitioning Strategy ---

PARTITIONING_GUIDE = """
Choose partition columns based on query patterns:

| Data Type          | Partition By          | Why                              |
|-------------------|-----------------------|----------------------------------|
| Events/logs       | date (daily)          | Time-range queries, lifecycle    |
| User activity     | date + region         | Regional queries + time filter   |
| IoT sensor data   | date + device_type    | Device-specific analysis         |
| Financial txns    | date + currency       | Currency-specific reporting      |

Rules:
- Each partition should have 100MB-1GB of data
- Too many partitions = slow metadata operations
- Too few = poor pruning, full scans
- Use date for time-series, avoid high-cardinality columns

Anti-patterns:
- Partitioning by user_id (millions of tiny partitions)
- Partitioning by hour when daily is sufficient
- Not partitioning at all (full scans on every query)
"""

# --- Apache Iceberg alternative ---

ICEBERG_EXAMPLE = """
-- Iceberg with hidden partitioning (no directory structure)
CREATE TABLE events (
    event_id STRING,
    user_id STRING,
    event_type STRING,
    event_time TIMESTAMP,
    payload STRING
)
USING iceberg
PARTITIONED BY (days(event_time), bucket(16, user_id));

-- Iceberg handles partition evolution without rewriting
ALTER TABLE events
ADD PARTITION FIELD hours(event_time);  -- No data movement!

-- Schema evolution
ALTER TABLE events ADD COLUMN new_field STRING;
ALTER TABLE events ALTER COLUMN payload TYPE MAP<STRING, STRING>;

-- Time travel
SELECT * FROM events VERSION AS OF 12345;
SELECT * FROM events TIMESTAMP AS OF '2024-03-14 10:00:00';

-- Maintenance
CALL catalog.system.rewrite_data_files('events');
CALL catalog.system.expire_snapshots('events', TIMESTAMP '2024-02-01');
"""
```

Lakehouse vs traditional:
- **Data lake** — cheap storage, no ACID, schema-on-read
- **Data warehouse** — ACID, schema-on-write, expensive storage
- **Lakehouse** — ACID on object storage, time travel, schema evolution
  - Delta Lake (Databricks), Iceberg (Netflix), Hudi (Uber)'''
    ),
]
