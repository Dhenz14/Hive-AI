"""Time-series databases — InfluxDB, TimescaleDB, VictoriaMetrics, and data modeling patterns."""

PAIRS = [
    (
        "databases/timeseries-influxdb",
        "Show InfluxDB patterns: Flux queries, retention policies, continuous queries, and best practices.",
        '''InfluxDB time-series database with Flux query language:

```python
# --- InfluxDB client setup and write operations ---

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS, ASYNCHRONOUS
from datetime import datetime, timedelta, timezone
from typing import Any
import os


def create_influx_client(
    url: str = "http://localhost:8086",
    token: str | None = None,
    org: str = "myorg",
) -> InfluxDBClient:
    """Create InfluxDB v2 client."""
    token = token or os.environ.get("INFLUXDB_TOKEN", "")
    return InfluxDBClient(url=url, token=token, org=org)


def write_metrics(
    client: InfluxDBClient,
    bucket: str,
    org: str,
    measurements: list[dict[str, Any]],
    write_precision: WritePrecision = WritePrecision.S,
    batch_size: int = 5000,
) -> None:
    """Write time-series data points to InfluxDB.

    InfluxDB data model:
      measurement  — like a table name (e.g., "cpu", "temperature")
      tags         — indexed string key-value pairs (low cardinality)
      fields       — non-indexed values (numbers, strings, booleans)
      timestamp    — nanosecond-precision time

    Tag design rules:
      - Tags are indexed, fields are not
      - Use tags for dimensions you filter/group on
      - Keep tag cardinality low (< 100K unique values)
      - Never use high-cardinality values (UUIDs, emails) as tags
    """
    write_api = client.write_api(write_options=SYNCHRONOUS)

    points: list[Point] = []
    for m in measurements:
        point = (
            Point(m["measurement"])
            .time(m.get("time", datetime.now(timezone.utc)), write_precision)
        )

        # Add tags (indexed, low cardinality)
        for tag_key, tag_value in m.get("tags", {}).items():
            point = point.tag(tag_key, str(tag_value))

        # Add fields (non-indexed, any type)
        for field_key, field_value in m.get("fields", {}).items():
            point = point.field(field_key, field_value)

        points.append(point)

    # Batch write for performance
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        write_api.write(bucket=bucket, org=org, record=batch)

    print(f"Wrote {len(points)} points to bucket '{bucket}'")


# Example usage
SAMPLE_METRICS = [
    {
        "measurement": "server_metrics",
        "tags": {"host": "web-01", "region": "us-east", "env": "prod"},
        "fields": {"cpu_percent": 72.5, "memory_mb": 4096, "disk_io_ops": 1523},
        "time": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    },
    {
        "measurement": "server_metrics",
        "tags": {"host": "web-02", "region": "us-east", "env": "prod"},
        "fields": {"cpu_percent": 45.2, "memory_mb": 3200, "disk_io_ops": 892},
        "time": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    },
]
```

```python
# --- Flux query patterns ---

def query_flux(
    client: InfluxDBClient,
    org: str,
    query: str,
) -> list[dict[str, Any]]:
    """Execute Flux query and return results as dicts."""
    query_api = client.query_api()
    tables = query_api.query(query, org=org)

    results: list[dict[str, Any]] = []
    for table in tables:
        for record in table.records:
            results.append({
                "time": record.get_time(),
                "measurement": record.get_measurement(),
                "field": record.get_field(),
                "value": record.get_value(),
                **{k: v for k, v in record.values.items()
                   if k not in ("_time", "_measurement", "_field", "_value",
                                "result", "table")},
            })

    return results


# --- Common Flux query patterns ---

FLUX_QUERIES = {
    # 1. Basic range query with filtering
    "cpu_by_host": '''
        from(bucket: "monitoring")
            |> range(start: -1h)
            |> filter(fn: (r) => r._measurement == "server_metrics")
            |> filter(fn: (r) => r._field == "cpu_percent")
            |> filter(fn: (r) => r.env == "prod")
    ''',

    # 2. Aggregation: average CPU per 5-minute window
    "cpu_avg_5m": '''
        from(bucket: "monitoring")
            |> range(start: -24h)
            |> filter(fn: (r) => r._measurement == "server_metrics")
            |> filter(fn: (r) => r._field == "cpu_percent")
            |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
            |> yield(name: "mean")
    ''',

    # 3. Moving average for trend smoothing
    "cpu_moving_avg": '''
        from(bucket: "monitoring")
            |> range(start: -6h)
            |> filter(fn: (r) => r._measurement == "server_metrics")
            |> filter(fn: (r) => r._field == "cpu_percent")
            |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
            |> movingAverage(n: 10)
    ''',

    # 4. Percentiles for latency analysis
    "latency_percentiles": '''
        from(bucket: "monitoring")
            |> range(start: -1h)
            |> filter(fn: (r) => r._measurement == "http_requests")
            |> filter(fn: (r) => r._field == "duration_ms")
            |> aggregateWindow(every: 5m, fn: (column, tables=<-) =>
                tables |> quantile(q: 0.95, column: column),
                createEmpty: false)
            |> yield(name: "p95")
    ''',

    # 5. Alerting: find hosts exceeding threshold
    "high_cpu_alerts": '''
        from(bucket: "monitoring")
            |> range(start: -15m)
            |> filter(fn: (r) => r._measurement == "server_metrics")
            |> filter(fn: (r) => r._field == "cpu_percent")
            |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
            |> filter(fn: (r) => r._value > 90.0)
            |> group(columns: ["host"])
    ''',

    # 6. Downsampling: reduce resolution for long-term storage
    "downsample_hourly": '''
        from(bucket: "monitoring")
            |> range(start: -30d)
            |> filter(fn: (r) => r._measurement == "server_metrics")
            |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
            |> to(bucket: "monitoring_longterm", org: "myorg")
    ''',
}
```

```python
# --- Bucket management and retention ---

from influxdb_client.client.bucket_api import BucketsApi
from influxdb_client.domain.bucket_retention_rules import BucketRetentionRules


def setup_retention_buckets(
    client: InfluxDBClient,
    org_id: str,
) -> dict[str, str]:
    """Create buckets with different retention policies.

    Retention strategy:
      raw       — full resolution, 7 days
      rollup_1h — hourly aggregates, 90 days
      rollup_1d — daily aggregates, 2 years
      permanent — critical metrics, infinite retention
    """
    buckets_api = client.buckets_api()
    bucket_configs = {
        "monitoring_raw": 7 * 24 * 3600,       # 7 days
        "monitoring_1h": 90 * 24 * 3600,        # 90 days
        "monitoring_1d": 730 * 24 * 3600,       # 2 years
        "monitoring_permanent": 0,              # 0 = infinite
    }

    created: dict[str, str] = {}
    for name, retention_seconds in bucket_configs.items():
        existing = buckets_api.find_bucket_by_name(name)
        if existing:
            created[name] = existing.id
            continue

        retention_rules = BucketRetentionRules(
            type="expire",
            every_seconds=retention_seconds,
        ) if retention_seconds > 0 else None

        bucket = buckets_api.create_bucket(
            bucket_name=name,
            retention_rules=[retention_rules] if retention_rules else None,
            org_id=org_id,
        )
        created[name] = bucket.id
        print(f"Created bucket '{name}' (retention={retention_seconds}s)")

    return created


def create_downsampling_task(
    client: InfluxDBClient,
    org_id: str,
    source_bucket: str = "monitoring_raw",
    dest_bucket: str = "monitoring_1h",
    every: str = "1h",
) -> str:
    """Create InfluxDB task for continuous downsampling.

    Tasks run Flux queries on a schedule to aggregate data
    from high-resolution to low-resolution buckets.
    """
    tasks_api = client.tasks_api()

    flux_script = f'''
        option task = {{name: "downsample_{every}", every: {every}}}

        from(bucket: "{source_bucket}")
            |> range(start: -task.every)
            |> filter(fn: (r) => r._measurement == "server_metrics")
            |> aggregateWindow(every: {every}, fn: mean, createEmpty: false)
            |> to(bucket: "{dest_bucket}")
    '''

    task = tasks_api.create_task_every(
        name=f"downsample_{every}",
        flux=flux_script,
        every=every,
        org_id=org_id,
    )
    return task.id
```

Key InfluxDB patterns:

| Feature | Detail |
|---|---|
| Tags vs fields | Tags indexed + low cardinality; fields for values |
| Flux language | Pipe-forward functional query language |
| Retention policies | Per-bucket TTL for automatic data expiry |
| Tasks | Scheduled Flux scripts for downsampling/alerts |
| aggregateWindow | Window functions: mean, sum, count, quantile |
| Cardinality | Keep tag cardinality < 100K to avoid OOM |

1. **Tag design is critical** -- index what you filter on, avoid high-cardinality tags
2. **Multi-tier retention** -- raw 7d, hourly 90d, daily 2y for cost optimization
3. **Downsampling tasks** -- automatically reduce resolution for long-term storage
4. **Flux pipe-forward** -- chain transformations with |> for readable queries
5. **Batch writes** -- buffer 5000+ points per write for throughput'''
    ),
    (
        "databases/timeseries-timescaledb",
        "Demonstrate TimescaleDB: hypertables, compression, continuous aggregates, and performance tuning.",
        '''TimescaleDB on PostgreSQL for time-series at scale:

```python
# --- TimescaleDB setup and hypertable creation ---

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from datetime import datetime, timedelta
from typing import Any
from contextlib import contextmanager


@contextmanager
def get_connection(dsn: str = "postgresql://localhost:5432/tsdb"):
    """Database connection context manager."""
    conn = psycopg2.connect(dsn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def setup_timescaledb(dsn: str) -> None:
    """Initialize TimescaleDB extension and create hypertables.

    Hypertable = automatically partitioned table by time.
    Each chunk covers a time interval (default: 7 days).
    Chunks enable:
      - Parallel queries across time ranges
      - Per-chunk compression
      - Automatic data retention (drop old chunks)
      - Efficient vacuuming
    """
    with get_connection(dsn) as conn:
        cur = conn.cursor()

        # Enable TimescaleDB
        cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

        # Create metrics table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                time        TIMESTAMPTZ NOT NULL,
                host        TEXT NOT NULL,
                region      TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value       DOUBLE PRECISION NOT NULL,
                tags        JSONB DEFAULT '{}'
            );
        """)

        # Convert to hypertable partitioned by time
        # chunk_time_interval controls chunk size
        cur.execute("""
            SELECT create_hypertable(
                'metrics',
                by_range('time', INTERVAL '1 day'),
                if_not_exists => TRUE
            );
        """)

        # Add composite index for common query patterns
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_host_time
                ON metrics (host, time DESC);
            CREATE INDEX IF NOT EXISTS idx_metrics_name_time
                ON metrics (metric_name, time DESC);
        """)

        # Create events table with space partitioning
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                time        TIMESTAMPTZ NOT NULL,
                device_id   TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                payload     JSONB NOT NULL DEFAULT '{}'
            );

            SELECT create_hypertable(
                'events',
                by_range('time', INTERVAL '7 days'),
                if_not_exists => TRUE
            );

            -- Add space partitioning by device_id for parallel queries
            SELECT add_dimension(
                'events',
                by_hash('device_id', 4),
                if_not_exists => TRUE
            );
        """)

        print("TimescaleDB setup complete")
```

```python
# --- Compression and retention policies ---

def configure_compression(dsn: str) -> None:
    """Enable compression for storage savings.

    TimescaleDB compression achieves 90-95% reduction:
      - Gorilla encoding for floating-point values
      - Delta-of-delta for timestamps
      - Dictionary encoding for repeated strings
      - LZ4/Zstd for remaining data

    Segment-by columns remain queryable without decompression.
    Order-by determines sort within compressed segments.
    """
    with get_connection(dsn) as conn:
        cur = conn.cursor()

        # Enable compression on metrics table
        cur.execute("""
            ALTER TABLE metrics SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'host, metric_name',
                timescaledb.compress_orderby = 'time DESC'
            );
        """)

        # Add compression policy: compress chunks older than 2 days
        cur.execute("""
            SELECT add_compression_policy(
                'metrics',
                INTERVAL '2 days',
                if_not_exists => TRUE
            );
        """)

        print("Compression policy configured")


def configure_retention(dsn: str) -> None:
    """Set up automatic data retention (drop old chunks).

    Unlike DELETE, dropping chunks is O(1) — instant, no vacuum needed.
    """
    with get_connection(dsn) as conn:
        cur = conn.cursor()

        # Drop chunks older than 90 days
        cur.execute("""
            SELECT add_retention_policy(
                'metrics',
                INTERVAL '90 days',
                if_not_exists => TRUE
            );
        """)

        # Manual chunk drop for immediate cleanup
        cur.execute("""
            SELECT drop_chunks('metrics', older_than => INTERVAL '90 days');
        """)

        print("Retention policy configured")


def check_compression_stats(dsn: str) -> list[dict[str, Any]]:
    """Check compression ratios per chunk."""
    with get_connection(dsn) as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                hypertable_name,
                chunk_name,
                before_compression_total_bytes,
                after_compression_total_bytes,
                ROUND(
                    (1 - after_compression_total_bytes::numeric /
                     NULLIF(before_compression_total_bytes, 0)) * 100, 1
                ) AS compression_ratio_pct
            FROM timescaledb_information.compressed_chunk_stats
            WHERE compression_status = 'Compressed'
            ORDER BY before_compression_total_bytes DESC
            LIMIT 20;
        """)
        return [dict(row) for row in cur.fetchall()]
```

```python
# --- Continuous aggregates and queries ---

def create_continuous_aggregates(dsn: str) -> None:
    """Create materialized views that auto-refresh.

    Continuous aggregates:
      - Pre-compute rollups (avg, sum, count, percentile)
      - Incrementally refresh (only process new data)
      - Query like regular tables/views
      - Can be layered (hourly -> daily -> monthly)
    """
    with get_connection(dsn) as conn:
        cur = conn.cursor()

        # Hourly rollup
        cur.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_hourly
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 hour', time) AS bucket,
                host,
                metric_name,
                AVG(value) AS avg_value,
                MIN(value) AS min_value,
                MAX(value) AS max_value,
                COUNT(*) AS sample_count,
                percentile_agg(value) AS pct_agg
            FROM metrics
            GROUP BY bucket, host, metric_name
            WITH NO DATA;
        """)

        # Auto-refresh policy: refresh every hour, covering last 3 hours
        cur.execute("""
            SELECT add_continuous_aggregate_policy(
                'metrics_hourly',
                start_offset => INTERVAL '3 hours',
                end_offset => INTERVAL '1 hour',
                schedule_interval => INTERVAL '1 hour',
                if_not_exists => TRUE
            );
        """)

        # Daily rollup (layered on top of hourly)
        cur.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_daily
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 day', bucket) AS bucket,
                host,
                metric_name,
                AVG(avg_value) AS avg_value,
                MIN(min_value) AS min_value,
                MAX(max_value) AS max_value,
                SUM(sample_count) AS sample_count
            FROM metrics_hourly
            GROUP BY time_bucket('1 day', bucket), host, metric_name
            WITH NO DATA;
        """)

        cur.execute("""
            SELECT add_continuous_aggregate_policy(
                'metrics_daily',
                start_offset => INTERVAL '3 days',
                end_offset => INTERVAL '1 day',
                schedule_interval => INTERVAL '1 day',
                if_not_exists => TRUE
            );
        """)

        print("Continuous aggregates created")


def query_with_time_bucket(
    dsn: str,
    host: str,
    metric: str,
    interval: str = "5 minutes",
    hours_back: int = 24,
) -> list[dict[str, Any]]:
    """Query with time bucketing for dashboards."""
    with get_connection(dsn) as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT
                time_bucket(%(interval)s, time) AS bucket,
                AVG(value) AS avg_value,
                MAX(value) AS max_value,
                MIN(value) AS min_value,
                COUNT(*) AS samples
            FROM metrics
            WHERE host = %(host)s
              AND metric_name = %(metric)s
              AND time > NOW() - make_interval(hours => %(hours)s)
            GROUP BY bucket
            ORDER BY bucket DESC;
        """, {
            "interval": interval,
            "host": host,
            "metric": metric,
            "hours": hours_back,
        })

        return [dict(row) for row in cur.fetchall()]


def query_last_value_per_host(dsn: str, metric: str) -> list[dict[str, Any]]:
    """Get latest value for each host (common dashboard query)."""
    with get_connection(dsn) as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Use DISTINCT ON for efficient last-value queries
        cur.execute("""
            SELECT DISTINCT ON (host)
                host,
                time,
                value AS latest_value
            FROM metrics
            WHERE metric_name = %(metric)s
              AND time > NOW() - INTERVAL '1 hour'
            ORDER BY host, time DESC;
        """, {"metric": metric})

        return [dict(row) for row in cur.fetchall()]
```

Key TimescaleDB patterns:

| Feature | Detail |
|---|---|
| Hypertables | Auto-partitioned by time, transparent to SQL |
| Chunks | Time-range partitions, O(1) drop for retention |
| Compression | 90-95% reduction with Gorilla + delta encoding |
| Continuous aggregates | Incrementally-refreshed materialized views |
| time_bucket() | Group data into time windows for dashboards |
| Space partitioning | Hash-partition by a second dimension (device_id) |

1. **Hypertable chunk interval** -- match to query patterns (1 day for high ingest, 7 days for lower)
2. **Compression segmentby** -- choose columns you filter on most (host, metric_name)
3. **Layered aggregates** -- raw -> hourly -> daily for multi-resolution dashboards
4. **Retention by chunk drop** -- O(1) vs expensive DELETE + VACUUM
5. **Full SQL compatibility** -- JOINs, CTEs, window functions all work on hypertables'''
    ),
    (
        "databases/timeseries-victoriametrics",
        "Explain VictoriaMetrics: PromQL queries, vmagent, cluster mode, and Prometheus compatibility.",
        '''VictoriaMetrics for Prometheus-compatible time-series at scale:

```python
# --- VictoriaMetrics client and write operations ---

import requests
from datetime import datetime, timezone
from typing import Any
from dataclasses import dataclass, field


@dataclass
class VMConfig:
    """VictoriaMetrics connection configuration."""
    url: str = "http://localhost:8428"
    # Cluster mode endpoints:
    # vminsert: http://vminsert:8480/insert/0/prometheus/api/v1/write
    # vmselect: http://vmselect:8481/select/0/prometheus/api/v1/query
    username: str | None = None
    password: str | None = None
    tenant_id: str = "0"     # Multi-tenancy in cluster mode

    @property
    def write_url(self) -> str:
        return f"{self.url}/api/v1/import/prometheus"

    @property
    def query_url(self) -> str:
        return f"{self.url}/api/v1/query"

    @property
    def query_range_url(self) -> str:
        return f"{self.url}/api/v1/query_range"

    @property
    def auth(self) -> tuple[str, str] | None:
        if self.username and self.password:
            return (self.username, self.password)
        return None


def write_prometheus_format(
    config: VMConfig,
    metrics: list[dict[str, Any]],
    timeout: int = 30,
) -> None:
    """Write metrics in Prometheus exposition format.

    VictoriaMetrics accepts:
      - Prometheus remote_write protocol
      - Prometheus exposition format (text)
      - InfluxDB line protocol (/write endpoint)
      - JSON import (/api/v1/import)
      - CSV import
    """
    lines: list[str] = []
    for m in metrics:
        name = m["name"]
        labels = m.get("labels", {})
        value = m["value"]
        timestamp_ms = int(m.get(
            "timestamp",
            datetime.now(timezone.utc).timestamp()
        ) * 1000)

        # Format: metric_name{label1="val1",label2="val2"} value timestamp_ms
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        if label_str:
            lines.append(f"{name}{{{label_str}}} {value} {timestamp_ms}")
        else:
            lines.append(f"{name} {value} {timestamp_ms}")

    payload = "\n".join(lines)
    resp = requests.post(
        config.write_url,
        data=payload,
        headers={"Content-Type": "text/plain"},
        auth=config.auth,
        timeout=timeout,
    )
    resp.raise_for_status()


# --- vmagent configuration (YAML) ---
VMAGENT_CONFIG = """
# vmagent.yml - Scrape and remote_write configuration
# vmagent replaces Prometheus for scraping, supports:
#   - Service discovery (Kubernetes, Consul, EC2, etc.)
#   - Streaming aggregation (reduce cardinality before storage)
#   - Relabeling and filtering
#   - Multi-destination remote_write

global:
  scrape_interval: 15s
  scrape_timeout: 10s

scrape_configs:
  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'kubernetes-pods'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)

remote_write:
  - url: http://victoriametrics:8428/api/v1/write
    queue_config:
      max_samples_per_send: 10000
      batch_send_deadline: 5s
      max_shards: 30
"""
```

```python
# --- PromQL / MetricsQL queries ---

def query_instant(
    config: VMConfig,
    promql: str,
    time: datetime | None = None,
) -> list[dict[str, Any]]:
    """Execute instant PromQL query.

    VictoriaMetrics extends PromQL with MetricsQL:
      - keep_metric_names       — preserve metric name after transforms
      - label_set()             — override label values
      - range_median()          — median over a range
      - histogram_quantiles()   — multiple quantiles at once
      - rollup_rate()           — rate with better accuracy
    """
    params: dict[str, Any] = {"query": promql}
    if time:
        params["time"] = time.timestamp()

    resp = requests.get(
        config.query_url,
        params=params,
        auth=config.auth,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    results: list[dict[str, Any]] = []
    for result in data.get("data", {}).get("result", []):
        results.append({
            "metric": result["metric"],
            "value": float(result["value"][1]),
            "timestamp": datetime.fromtimestamp(
                float(result["value"][0]), tz=timezone.utc
            ),
        })

    return results


def query_range(
    config: VMConfig,
    promql: str,
    start: datetime,
    end: datetime,
    step: str = "1m",
) -> list[dict[str, Any]]:
    """Execute range PromQL query for time-series data."""
    resp = requests.get(
        config.query_range_url,
        params={
            "query": promql,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step,
        },
        auth=config.auth,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    results: list[dict[str, Any]] = []
    for result in data.get("data", {}).get("result", []):
        series = {
            "metric": result["metric"],
            "values": [
                {
                    "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                    "value": float(val),
                }
                for ts, val in result["values"]
            ],
        }
        results.append(series)

    return results


# Common PromQL/MetricsQL patterns
PROMQL_PATTERNS = {
    # CPU usage percentage
    "cpu_usage": (
        '100 - (avg by (instance) '
        '(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
    ),

    # Memory usage percentage
    "memory_usage": (
        '(1 - node_memory_MemAvailable_bytes / '
        'node_memory_MemTotal_bytes) * 100'
    ),

    # HTTP request rate by status code
    "http_rate": (
        'sum by (status_code) '
        '(rate(http_requests_total[5m]))'
    ),

    # P99 latency from histogram
    "latency_p99": (
        'histogram_quantile(0.99, '
        'sum by (le) (rate(http_duration_seconds_bucket[5m])))'
    ),

    # Error rate percentage
    "error_rate": (
        'sum(rate(http_requests_total{status_code=~"5.."}[5m])) / '
        'sum(rate(http_requests_total[5m])) * 100'
    ),

    # Disk space prediction (linear extrapolation)
    "disk_full_prediction": (
        'predict_linear('
        'node_filesystem_avail_bytes{mountpoint="/"}[6h], 24*3600)'
    ),
}
```

```python
# --- Cluster mode architecture ---

VM_CLUSTER_ARCHITECTURE = """
VictoriaMetrics Cluster Mode:

  ┌─────────┐     ┌──────────┐     ┌───────────┐
  │ vmagent  │────▶│ vminsert │────▶│ vmstorage │
  │ (scrape) │     │ (route)  │     │ (store)   │
  └─────────┘     └──────────┘     └───────────┘
                                         │
  ┌─────────┐     ┌──────────┐          │
  │ Grafana  │◀───│ vmselect │◀─────────┘
  │ (viz)    │     │ (query)  │
  └─────────┘     └──────────┘

Components:
  vmagent    — scrapes targets, applies relabeling, remote_writes
  vminsert   — routes writes to correct vmstorage shard
  vmstorage  — stores data on disk with compression
  vmselect   — queries data across all vmstorage nodes
"""


def check_vm_health(config: VMConfig) -> dict[str, Any]:
    """Check VictoriaMetrics health and stats."""
    # Health check
    health = requests.get(f"{config.url}/health", timeout=5)

    # Active time series count
    tsdb_status = requests.get(
        f"{config.url}/api/v1/status/tsdb",
        auth=config.auth,
        timeout=10,
    )

    status_data = tsdb_status.json().get("data", {}) if tsdb_status.ok else {}

    return {
        "healthy": health.status_code == 200,
        "total_series": status_data.get("totalSeries", 0),
        "total_label_value_pairs": status_data.get("totalLabelValuePairs", 0),
        "series_count_by_metric": status_data.get(
            "seriesCountByMetricName", []
        )[:10],
    }


def configure_retention_filters(config: VMConfig) -> dict[str, str]:
    """VictoriaMetrics retention configuration.

    CLI flags for vmstorage:
      -retentionPeriod=90d          — global retention
      -retentionFilter='{db="dev"}:7d'  — per-label retention
      -dedup.minScrapeInterval=15s  — deduplicate HA pairs
    """
    return {
        "global_retention": "-retentionPeriod=90d",
        "dev_retention": '-retentionFilter=\'{job="dev"}:7d\'',
        "staging_retention": '-retentionFilter=\'{env="staging"}:30d\'',
        "dedup": "-dedup.minScrapeInterval=15s",
        "downsampling": (
            "-downsampling.period=30d:5m,90d:1h,365d:6h"
            # Keep 5m resolution for 30d, 1h for 90d, 6h for 365d
        ),
    }
```

Key VictoriaMetrics patterns:

| Feature | Detail |
|---|---|
| Prometheus compatible | Drop-in replacement for Prometheus storage |
| MetricsQL | Extended PromQL with keep_metric_names, rollup_rate |
| vmagent | Lightweight scraper with streaming aggregation |
| Cluster mode | vminsert/vmselect/vmstorage for horizontal scale |
| Multi-tenancy | accountID in URL path for tenant isolation |
| Retention filters | Per-label retention for cost optimization |
| Compression | 10x better than Prometheus TSDB |

1. **vmagent over Prometheus** -- lighter, supports streaming aggregation to reduce cardinality
2. **MetricsQL extensions** -- keep_metric_names, rollup_rate for more accurate calculations
3. **Per-label retention** -- keep production data longer, dev data shorter
4. **Downsampling periods** -- progressive resolution reduction saves storage
5. **Cluster for scale** -- separate insert/select/storage for independent scaling'''
    ),
    (
        "databases/timeseries-modeling",
        "Explain time-series data modeling patterns: schema design, partitioning, and query optimization.",
        '''Time-series data modeling patterns and best practices:

```python
# --- Schema design patterns ---

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


class SchemaPattern(Enum):
    """Time-series schema design patterns."""
    WIDE = "wide"           # One row per timestamp, many columns
    NARROW = "narrow"       # One row per metric per timestamp
    HYBRID = "hybrid"       # Related metrics grouped per row


@dataclass
class WideSchema:
    """Wide table: one row per timestamp with all metrics.

    Best for: correlated metrics always queried together.
    Example: all server metrics collected simultaneously.

    CREATE TABLE server_metrics_wide (
        time        TIMESTAMPTZ NOT NULL,
        host        TEXT NOT NULL,
        cpu_user    DOUBLE PRECISION,
        cpu_system  DOUBLE PRECISION,
        cpu_iowait  DOUBLE PRECISION,
        mem_used_mb BIGINT,
        mem_free_mb BIGINT,
        disk_read_ops  BIGINT,
        disk_write_ops BIGINT,
        net_rx_bytes   BIGINT,
        net_tx_bytes   BIGINT
    );

    Pros: single query gets all metrics, natural row layout
    Cons: schema changes require ALTER TABLE, sparse data wastes space
    """
    time: datetime
    host: str
    cpu_user: float = 0.0
    cpu_system: float = 0.0
    mem_used_mb: int = 0
    mem_free_mb: int = 0
    disk_read_ops: int = 0
    disk_write_ops: int = 0


@dataclass
class NarrowSchema:
    """Narrow table: one row per metric per timestamp.

    Best for: dynamic/variable metrics, IoT with heterogeneous sensors.

    CREATE TABLE metrics_narrow (
        time        TIMESTAMPTZ NOT NULL,
        source      TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        value       DOUBLE PRECISION NOT NULL,
        tags        JSONB DEFAULT '{}'
    );

    Pros: flexible schema, add metrics without ALTER TABLE
    Cons: queries across metrics need self-joins or pivots
    """
    time: datetime
    source: str
    metric_name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class HybridSchema:
    """Hybrid: group related metrics in one row.

    Best for: metrics with natural groupings.

    CREATE TABLE http_metrics (
        time            TIMESTAMPTZ NOT NULL,
        service         TEXT NOT NULL,
        endpoint        TEXT NOT NULL,
        request_count   BIGINT,
        error_count     BIGINT,
        latency_p50_ms  DOUBLE PRECISION,
        latency_p95_ms  DOUBLE PRECISION,
        latency_p99_ms  DOUBLE PRECISION,
        bytes_sent      BIGINT
    );

    Pros: natural grouping, efficient queries, clear schema
    Cons: less flexible than narrow for dynamic metrics
    """
    time: datetime
    service: str
    endpoint: str
    request_count: int = 0
    error_count: int = 0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
```

```python
# --- Partitioning and indexing strategies ---

PARTITIONING_SQL = """
-- 1. Time-based partitioning (most common)
-- PostgreSQL native partitioning:
CREATE TABLE events (
    time        TIMESTAMPTZ NOT NULL,
    device_id   TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB
) PARTITION BY RANGE (time);

-- Create monthly partitions
CREATE TABLE events_2024_01 PARTITION OF events
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE events_2024_02 PARTITION OF events
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

-- 2. Composite partitioning (time + hash)
-- Useful for high-cardinality device_id with time queries
CREATE TABLE sensor_data (
    time        TIMESTAMPTZ NOT NULL,
    sensor_id   TEXT NOT NULL,
    value       DOUBLE PRECISION
) PARTITION BY RANGE (time);

CREATE TABLE sensor_data_2024_01 PARTITION OF sensor_data
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01')
    PARTITION BY HASH (sensor_id);

CREATE TABLE sensor_data_2024_01_p0 PARTITION OF sensor_data_2024_01
    FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE sensor_data_2024_01_p1 PARTITION OF sensor_data_2024_01
    FOR VALUES WITH (MODULUS 4, REMAINDER 1);


-- 3. Indexing strategies for time-series
-- BRIN index: tiny size, great for time-ordered data
CREATE INDEX idx_events_time_brin ON events USING BRIN (time)
    WITH (pages_per_range = 32);

-- B-tree: precise lookups, larger but faster
CREATE INDEX idx_events_device_time ON events (device_id, time DESC);

-- Partial index: only index recent hot data
CREATE INDEX idx_events_recent ON events (time DESC)
    WHERE time > NOW() - INTERVAL '7 days';
"""


def calculate_partition_size(
    rows_per_second: int,
    row_size_bytes: int,
    partition_interval_hours: int = 24,
) -> dict[str, Any]:
    """Calculate optimal partition sizing.

    Guidelines:
      - Each partition/chunk should be 25-100 GB uncompressed
      - Too small: too many partitions, planning overhead
      - Too large: slow maintenance operations
    """
    rows_per_partition = rows_per_second * partition_interval_hours * 3600
    partition_size_gb = (rows_per_partition * row_size_bytes) / (1024 ** 3)

    # Recommend partition interval
    target_gb = 50  # Target 50 GB per partition
    optimal_hours = (target_gb * (1024 ** 3)) / (
        rows_per_second * row_size_bytes * 3600
    )

    return {
        "rows_per_partition": rows_per_partition,
        "partition_size_gb": round(partition_size_gb, 2),
        "recommended_interval_hours": max(1, round(optimal_hours)),
        "partitions_per_year": round(8760 / max(1, optimal_hours)),
    }
```

```python
# --- Query optimization patterns ---

from enum import Enum


class QueryPattern(Enum):
    """Common time-series query patterns with optimization strategies."""

    LATEST_VALUE = "latest_value"
    TIME_RANGE_AGG = "time_range_aggregation"
    TOP_N = "top_n_series"
    ANOMALY = "anomaly_detection"
    DOWNSAMPLED = "downsampled_historical"


OPTIMIZED_QUERIES = {
    # 1. Latest value per entity — avoid full scan
    QueryPattern.LATEST_VALUE: """
        -- BAD: scans all data then sorts
        -- SELECT DISTINCT ON (host) host, time, value
        -- FROM metrics ORDER BY host, time DESC;

        -- GOOD: use a lateral join with index
        SELECT l.host, m.time, m.value
        FROM (SELECT DISTINCT host FROM metrics) l
        CROSS JOIN LATERAL (
            SELECT time, value
            FROM metrics
            WHERE host = l.host
            ORDER BY time DESC
            LIMIT 1
        ) m;
    """,

    # 2. Time-range aggregation — use continuous aggregates
    QueryPattern.TIME_RANGE_AGG: """
        -- For recent data (< 2 days): query raw table
        SELECT time_bucket('5 minutes', time) AS bucket,
               AVG(value), MAX(value), MIN(value), COUNT(*)
        FROM metrics
        WHERE time > NOW() - INTERVAL '2 hours'
          AND metric_name = 'cpu_usage'
        GROUP BY bucket
        ORDER BY bucket;

        -- For historical data: query pre-aggregated table
        SELECT bucket, avg_value, max_value, min_value
        FROM metrics_hourly
        WHERE bucket > NOW() - INTERVAL '30 days'
          AND metric_name = 'cpu_usage'
        ORDER BY bucket;
    """,

    # 3. Top-N series by a metric
    QueryPattern.TOP_N: """
        SELECT host,
               AVG(value) AS avg_cpu
        FROM metrics
        WHERE metric_name = 'cpu_usage'
          AND time > NOW() - INTERVAL '1 hour'
        GROUP BY host
        ORDER BY avg_cpu DESC
        LIMIT 10;
    """,

    # 4. Anomaly detection with z-score
    QueryPattern.ANOMALY: """
        WITH stats AS (
            SELECT host,
                   AVG(value) AS mean_val,
                   STDDEV(value) AS std_val
            FROM metrics
            WHERE metric_name = 'cpu_usage'
              AND time BETWEEN NOW() - INTERVAL '7 days'
                          AND NOW() - INTERVAL '1 hour'
            GROUP BY host
        ),
        recent AS (
            SELECT host, time, value
            FROM metrics
            WHERE metric_name = 'cpu_usage'
              AND time > NOW() - INTERVAL '1 hour'
        )
        SELECT r.host, r.time, r.value,
               (r.value - s.mean_val) / NULLIF(s.std_val, 0) AS z_score
        FROM recent r
        JOIN stats s ON r.host = s.host
        WHERE ABS((r.value - s.mean_val) / NULLIF(s.std_val, 0)) > 3.0
        ORDER BY z_score DESC;
    """,
}


# Schema design decision tree
DESIGN_GUIDE = """
Schema Design Decision Tree:

1. Are all metrics collected at the same time?
   YES -> Wide schema (one row with all metric columns)
   NO  -> Continue to 2

2. Is the set of metrics fixed and known?
   YES -> Hybrid schema (group related metrics)
   NO  -> Narrow schema (metric_name + value columns)

3. Partitioning:
   - Always partition by time (range partitioning)
   - Add hash sub-partitioning if one dimension has high cardinality
   - Target 25-100 GB per partition

4. Indexing:
   - BRIN on time column (tiny, great for sequential scans)
   - B-tree on (entity_id, time DESC) for point lookups
   - Partial indexes on hot data windows

5. Retention:
   - Raw data: 7-30 days
   - Hourly aggregates: 90 days - 1 year
   - Daily aggregates: 2-5 years
   - Drop old partitions (O(1)) instead of DELETE
"""
```

Key time-series modeling patterns:

| Pattern | Use Case | Pros | Cons |
|---|---|---|---|
| Wide schema | Correlated metrics | Single query, natural | Rigid schema |
| Narrow schema | Dynamic/IoT metrics | Flexible, extensible | Self-joins needed |
| Hybrid schema | Grouped metrics | Balance of both | Moderate flexibility |
| BRIN indexes | Time-ordered data | Tiny index, fast scans | Imprecise for random |
| Lateral joins | Latest-value queries | Index-friendly | More complex SQL |
| Continuous aggs | Dashboard queries | Pre-computed, fast | Storage overhead |

1. **Choose schema by access pattern** -- wide for correlated, narrow for dynamic, hybrid for grouped
2. **Partition by time always** -- enables O(1) retention and parallel queries
3. **BRIN indexes for time** -- 100x smaller than B-tree, great for sequential data
4. **Multi-tier retention** -- raw -> hourly -> daily with automatic rollup
5. **Lateral joins for latest value** -- avoid expensive DISTINCT ON with full scan'''
    ),
]
