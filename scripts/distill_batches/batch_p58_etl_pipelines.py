"""Data engineering — ETL pipelines, data validation, and batch processing."""

PAIRS = [
    (
        "data-engineering/etl-pipeline",
        "Show ETL pipeline patterns: extract from multiple sources, transform with validation, load with idempotency.",
        '''ETL pipeline patterns:

```python
from dataclasses import dataclass, field
from typing import Iterator, Any, Callable
from datetime import datetime, timezone
import logging
import json
import csv
import hashlib

logger = logging.getLogger(__name__)


# --- Pipeline abstraction ---

@dataclass
class Record:
    """Immutable record flowing through pipeline."""
    data: dict
    metadata: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def with_error(self, error: str) -> 'Record':
        return Record(
            data=self.data,
            metadata=self.metadata,
            errors=[*self.errors, error],
        )

    def with_data(self, **updates) -> 'Record':
        return Record(
            data={**self.data, **updates},
            metadata=self.metadata,
            errors=self.errors,
        )


class Pipeline:
    """Composable ETL pipeline."""

    def __init__(self, name: str):
        self.name = name
        self._steps: list[Callable] = []
        self._error_handlers: list[Callable] = []
        self.stats = {"extracted": 0, "transformed": 0, "loaded": 0,
                      "errors": 0, "skipped": 0}

    def extract(self, extractor: Callable) -> 'Pipeline':
        self._extractor = extractor
        return self

    def transform(self, fn: Callable[[Record], Record]) -> 'Pipeline':
        self._steps.append(fn)
        return self

    def on_error(self, handler: Callable) -> 'Pipeline':
        self._error_handlers.append(handler)
        return self

    def run(self, loader: Callable[[list[Record]], int],
            batch_size: int = 1000) -> dict:
        """Execute pipeline with batched loading."""
        batch: list[Record] = []
        start = datetime.now(timezone.utc)

        for record in self._extractor():
            self.stats["extracted"] += 1

            # Apply transforms
            for step in self._steps:
                try:
                    record = step(record)
                except Exception as e:
                    record = record.with_error(f"{step.__name__}: {e}")
                    break

            if not record.is_valid:
                self.stats["errors"] += 1
                for handler in self._error_handlers:
                    handler(record)
                continue

            self.stats["transformed"] += 1
            batch.append(record)

            if len(batch) >= batch_size:
                loaded = loader(batch)
                self.stats["loaded"] += loaded
                batch = []

        # Flush remaining
        if batch:
            loaded = loader(batch)
            self.stats["loaded"] += loaded

        self.stats["duration"] = (
            datetime.now(timezone.utc) - start
        ).total_seconds()
        return self.stats


# --- Extractors ---

def extract_csv(path: str, encoding: str = "utf-8") -> Callable:
    def _extract() -> Iterator[Record]:
        with open(path, encoding=encoding) as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                yield Record(
                    data=dict(row),
                    metadata={"source": path, "line": i + 2},
                )
    return _extract

def extract_jsonl(path: str) -> Callable:
    def _extract() -> Iterator[Record]:
        with open(path) as f:
            for i, line in enumerate(f):
                yield Record(
                    data=json.loads(line),
                    metadata={"source": path, "line": i + 1},
                )
    return _extract

def extract_api(url: str, params: dict = None) -> Callable:
    import httpx
    def _extract() -> Iterator[Record]:
        page = 1
        while True:
            response = httpx.get(url, params={**(params or {}), "page": page})
            response.raise_for_status()
            data = response.json()
            for item in data["results"]:
                yield Record(data=item, metadata={"source": url, "page": page})
            if not data.get("has_next"):
                break
            page += 1
    return _extract


# --- Transforms ---

def validate_required(*fields: str):
    def _validate(record: Record) -> Record:
        for field in fields:
            if not record.data.get(field):
                return record.with_error(f"Missing required field: {field}")
        return record
    _validate.__name__ = f"validate_required({', '.join(fields)})"
    return _validate

def normalize_email(record: Record) -> Record:
    email = record.data.get("email", "")
    return record.with_data(email=email.strip().lower())

def add_hash_id(record: Record) -> Record:
    key = json.dumps(record.data, sort_keys=True)
    hash_id = hashlib.sha256(key.encode()).hexdigest()[:16]
    return record.with_data(_hash_id=hash_id)

def coerce_types(**type_map: type):
    def _coerce(record: Record) -> Record:
        updates = {}
        for field, target_type in type_map.items():
            if field in record.data:
                try:
                    updates[field] = target_type(record.data[field])
                except (ValueError, TypeError) as e:
                    return record.with_error(
                        f"Cannot coerce {field} to {target_type.__name__}: {e}"
                    )
        return record.with_data(**updates)
    _coerce.__name__ = "coerce_types"
    return _coerce


# --- Loaders ---

def load_postgres(pool, table: str, upsert_key: str = None):
    async def _load(records: list[Record]) -> int:
        if not records:
            return 0
        columns = list(records[0].data.keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
        col_names = ", ".join(columns)

        query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
        if upsert_key:
            updates = ", ".join(
                f"{c} = EXCLUDED.{c}" for c in columns if c != upsert_key
            )
            query += f" ON CONFLICT ({upsert_key}) DO UPDATE SET {updates}"

        async with pool.acquire() as conn:
            await conn.executemany(
                query,
                [tuple(r.data[c] for c in columns) for r in records],
            )
        return len(records)
    return _load


# --- Usage ---

# pipeline = (
#     Pipeline("user_import")
#     .extract(extract_csv("users.csv"))
#     .transform(validate_required("email", "name"))
#     .transform(normalize_email)
#     .transform(coerce_types(age=int, score=float))
#     .transform(add_hash_id)
#     .on_error(lambda r: logger.warning("Bad record: %s", r.errors))
# )
# stats = pipeline.run(load_jsonl("output.jsonl"), batch_size=500)
# print(stats)
```

ETL pipeline patterns:
1. **Immutable records** — `Record` carries data + metadata + errors through pipeline
2. **Composable transforms** — chain small functions with `.transform()`
3. **Batch loading** — accumulate records and flush in configurable batches
4. **Error isolation** — bad records logged and skipped, don't break pipeline
5. **Idempotent loading** — upsert with `ON CONFLICT` for safe re-runs'''
    ),
    (
        "data-engineering/apache-airflow",
        "Show Apache Airflow patterns: DAG design, task dependencies, XCom, sensors, and error handling.",
        '''Apache Airflow DAG patterns:

```python
from airflow import DAG
from airflow.decorators import dag, task
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.http.sensors.http import HttpSensor
from airflow.sensors.filesystem import FileSensor
from airflow.utils.task_group import TaskGroup
from airflow.models import Variable
from datetime import datetime, timedelta
import json


# --- Modern TaskFlow API (recommended) ---

@dag(
    dag_id="etl_daily_sales",
    schedule="0 6 * * *",  # 6 AM daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "data-team",
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "execution_timeout": timedelta(hours=2),
        "on_failure_callback": lambda ctx: notify_slack(ctx),
    },
    tags=["etl", "sales"],
)
def etl_daily_sales():

    @task()
    def extract_orders(ds: str = None) -> list[dict]:
        """Extract orders for the execution date."""
        import httpx
        response = httpx.get(
            f"https://api.example.com/orders",
            params={"date": ds},
            headers={"Authorization": f"Bearer {Variable.get('api_token')}"},
        )
        response.raise_for_status()
        orders = response.json()["data"]
        print(f"Extracted {len(orders)} orders for {ds}")
        return orders

    @task()
    def extract_products() -> dict:
        """Extract product catalog (cached daily)."""
        import httpx
        response = httpx.get("https://api.example.com/products")
        return {p["id"]: p for p in response.json()["data"]}

    @task()
    def transform(orders: list[dict], products: dict) -> list[dict]:
        """Enrich orders with product data."""
        enriched = []
        for order in orders:
            product = products.get(order["product_id"], {})
            enriched.append({
                "order_id": order["id"],
                "product_name": product.get("name", "Unknown"),
                "category": product.get("category", "Other"),
                "amount": order["total"],
                "currency": order["currency"],
                "created_at": order["created_at"],
            })
        return enriched

    @task()
    def validate(records: list[dict]) -> list[dict]:
        """Validate and filter bad records."""
        valid = []
        for r in records:
            if r["amount"] <= 0:
                print(f"Skipping invalid amount: {r}")
                continue
            if not r["order_id"]:
                print(f"Skipping missing order_id: {r}")
                continue
            valid.append(r)
        print(f"Validated: {len(valid)}/{len(records)} records")
        return valid

    @task()
    def load(records: list[dict], ds: str = None):
        """Load to warehouse."""
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id="warehouse")
        hook.run("DELETE FROM daily_sales WHERE date = %s", parameters=[ds])
        hook.insert_rows(
            table="daily_sales",
            rows=[list(r.values()) for r in records],
            target_fields=list(records[0].keys()) if records else [],
        )
        print(f"Loaded {len(records)} records for {ds}")

    @task()
    def notify(records: list[dict], ds: str = None):
        """Send completion notification."""
        total = sum(r["amount"] for r in records)
        print(f"Daily sales for {ds}: {len(records)} orders, ${total:.2f}")

    # Define dependencies (TaskFlow auto-wires via return values)
    orders = extract_orders()
    products = extract_products()
    transformed = transform(orders, products)
    validated = validate(transformed)
    load(validated)
    notify(validated)

etl_daily_sales()


# --- Task groups for organization ---

@dag(dag_id="multi_source_etl", schedule="@daily",
     start_date=datetime(2024, 1, 1), catchup=False)
def multi_source_etl():

    @task()
    def start():
        print("Starting multi-source ETL")

    with TaskGroup("source_a") as source_a:
        @task(task_id="extract_a")
        def extract_a():
            return [{"source": "a", "value": 1}]

        @task(task_id="transform_a")
        def transform_a(data):
            return [{"source": "a", "processed": True, **d} for d in data]

        transform_a(extract_a())

    with TaskGroup("source_b") as source_b:
        @task(task_id="extract_b")
        def extract_b():
            return [{"source": "b", "value": 2}]

        @task(task_id="transform_b")
        def transform_b(data):
            return [{"source": "b", "processed": True, **d} for d in data]

        transform_b(extract_b())

    @task()
    def merge_and_load(**context):
        """Merge results from parallel sources."""
        ti = context["ti"]
        data_a = ti.xcom_pull(task_ids="source_a.transform_a")
        data_b = ti.xcom_pull(task_ids="source_b.transform_b")
        merged = (data_a or []) + (data_b or [])
        print(f"Merged {len(merged)} records from all sources")

    s = start()
    s >> [source_a, source_b] >> merge_and_load()

multi_source_etl()


# --- Sensors and branching ---

# Wait for file, then process
# file_sensor = FileSensor(
#     task_id="wait_for_file",
#     filepath="/data/incoming/{{ ds }}.csv",
#     poke_interval=300,  # Check every 5 min
#     timeout=3600,       # Give up after 1 hour
#     mode="reschedule",  # Free worker while waiting
# )
```

Airflow patterns:
1. **TaskFlow API** — `@task` decorator auto-handles XCom serialization
2. **Task groups** — organize related tasks, run source extracts in parallel
3. **`catchup=False`** — don't backfill on first deploy
4. **`mode="reschedule"`** — sensors release worker slot between pokes
5. **Idempotent loads** — DELETE + INSERT for safe re-runs on same date'''
    ),
    (
        "data-engineering/dbt-patterns",
        "Show dbt patterns: model organization, incremental models, testing, and macros.",
        '''dbt (data build tool) patterns:

```sql
-- --- Model organization ---
-- models/
--   staging/       -- 1:1 with source tables, rename + cast
--   intermediate/  -- business logic joins
--   marts/         -- final tables for BI/analytics


-- models/staging/stg_orders.sql
-- Staging: clean raw source data

{{ config(materialized='view') }}

WITH source AS (
    SELECT * FROM {{ source('raw', 'orders') }}
),

renamed AS (
    SELECT
        id AS order_id,
        user_id AS customer_id,
        CAST(total_amount AS DECIMAL(10,2)) AS order_total,
        CAST(created_at AS TIMESTAMP) AS ordered_at,
        UPPER(status) AS order_status,
        -- Remove test orders
        CASE WHEN email LIKE '%@test.%' THEN TRUE ELSE FALSE END AS is_test
    FROM source
)

SELECT * FROM renamed
WHERE NOT is_test


-- models/intermediate/int_order_items_enriched.sql
-- Intermediate: join staging models

{{ config(materialized='table') }}

WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),

items AS (
    SELECT * FROM {{ ref('stg_order_items') }}
),

products AS (
    SELECT * FROM {{ ref('stg_products') }}
)

SELECT
    orders.order_id,
    orders.customer_id,
    orders.ordered_at,
    items.item_id,
    items.quantity,
    items.unit_price,
    items.quantity * items.unit_price AS line_total,
    products.product_name,
    products.category
FROM orders
JOIN items ON orders.order_id = items.order_id
JOIN products ON items.product_id = products.product_id


-- models/marts/fct_daily_revenue.sql
-- Mart: final analytics table

{{ config(
    materialized='incremental',
    unique_key='date_day',
    on_schema_change='sync_all_columns',
) }}

WITH order_items AS (
    SELECT * FROM {{ ref('int_order_items_enriched') }}
)

SELECT
    DATE_TRUNC('day', ordered_at) AS date_day,
    category,
    COUNT(DISTINCT order_id) AS total_orders,
    COUNT(item_id) AS total_items,
    SUM(line_total) AS gross_revenue,
    AVG(line_total) AS avg_item_value
FROM order_items

{% if is_incremental() %}
    WHERE ordered_at > (SELECT MAX(date_day) FROM {{ this }})
{% endif %}

GROUP BY 1, 2


-- --- Testing ---
-- models/staging/stg_orders.yml

-- version: 2
-- models:
--   - name: stg_orders
--     description: "Cleaned orders from raw source"
--     columns:
--       - name: order_id
--         tests:
--           - unique
--           - not_null
--       - name: customer_id
--         tests:
--           - not_null
--           - relationships:
--               to: ref('stg_customers')
--               field: customer_id
--       - name: order_total
--         tests:
--           - not_null
--           - dbt_utils.accepted_range:
--               min_value: 0
--               max_value: 100000
--       - name: order_status
--         tests:
--           - accepted_values:
--               values: ['PENDING', 'PAID', 'SHIPPED', 'DELIVERED', 'CANCELLED']


-- --- Custom generic test ---
-- tests/generic/test_positive_value.sql

{% test positive_value(model, column_name) %}
    SELECT {{ column_name }}
    FROM {{ model }}
    WHERE {{ column_name }} < 0
{% endtest %}


-- --- Macros ---
-- macros/cents_to_dollars.sql

{% macro cents_to_dollars(column_name) %}
    ROUND(CAST({{ column_name }} AS DECIMAL(10,2)) / 100, 2)
{% endmacro %}

-- Usage: SELECT {{ cents_to_dollars('amount_cents') }} AS amount_dollars


-- macros/generate_surrogate_key.sql

{% macro surrogate_key(fields) %}
    {{ dbt_utils.generate_surrogate_key(fields) }}
{% endmacro %}


-- --- Incremental model with merge strategy ---
-- models/marts/fct_events.sql

{{ config(
    materialized='incremental',
    unique_key='event_id',
    incremental_strategy='merge',
    merge_exclude_columns=['created_at'],
) }}

SELECT
    event_id,
    user_id,
    event_type,
    properties,
    occurred_at,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('stg_events') }}

{% if is_incremental() %}
    WHERE occurred_at >= (
        SELECT DATEADD(hour, -3, MAX(occurred_at))
        FROM {{ this }}
    )
{% endif %}
```

```yaml
# dbt_project.yml key settings
# models:
#   my_project:
#     staging:
#       +materialized: view
#       +schema: staging
#     intermediate:
#       +materialized: table
#       +schema: analytics
#     marts:
#       +materialized: table
#       +schema: analytics
```

dbt patterns:
1. **Staging/intermediate/marts** — layered model organization (raw -> clean -> business logic -> analytics)
2. **Incremental models** — only process new/changed data with `is_incremental()` guard
3. **`ref()` and `source()`** — dependency management and lineage tracking
4. **Schema tests** — unique, not_null, relationships, accepted_values built-in
5. **Macros** — reusable SQL snippets (DRY transformations)'''
    ),
]
