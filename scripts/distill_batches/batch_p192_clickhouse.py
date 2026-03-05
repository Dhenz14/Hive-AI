"""ClickHouse OLAP analytics — table engines, materialized views, distributed queries, and Kafka ingestion."""

PAIRS = [
    (
        "databases/clickhouse-engines",
        "Explain ClickHouse table engines: MergeTree family, ReplacingMergeTree, AggregatingMergeTree, and engine selection.",
        '''ClickHouse MergeTree family table engines:

```sql
-- === MergeTree: the foundation of ClickHouse storage ===

-- Basic MergeTree table
CREATE TABLE events (
    event_id     UUID DEFAULT generateUUIDv4(),
    event_time   DateTime64(3) DEFAULT now64(3),
    event_date   Date DEFAULT toDate(event_time),
    user_id      UInt64,
    event_type   LowCardinality(String),
    page_url     String,
    referrer     String,
    device_type  LowCardinality(String),
    country      LowCardinality(String),
    duration_ms  UInt32,
    revenue      Decimal64(2) DEFAULT 0,
    properties   Map(String, String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)       -- Monthly partitions
ORDER BY (user_id, event_time)          -- Primary key / sort order
TTL event_date + INTERVAL 90 DAY       -- Auto-delete after 90 days
SETTINGS
    index_granularity = 8192,           -- Rows per index mark
    min_bytes_for_wide_part = 10485760, -- 10MB threshold for wide parts
    storage_policy = 'tiered';          -- Hot/cold storage


-- === ReplacingMergeTree: upsert / last-write-wins ===
-- Keeps latest version by (ver) column; deduplicates during merges

CREATE TABLE user_profiles (
    user_id      UInt64,
    username     String,
    email        String,
    plan         LowCardinality(String),
    updated_at   DateTime DEFAULT now(),
    is_deleted   UInt8 DEFAULT 0          -- Soft delete flag
)
ENGINE = ReplacingMergeTree(updated_at)   -- Keep row with max updated_at
ORDER BY user_id
SETTINGS index_granularity = 8192;

-- Query with FINAL to get deduplicated results (slower)
-- SELECT * FROM user_profiles FINAL WHERE is_deleted = 0;

-- Or use subquery for better performance:
-- SELECT argMax(username, updated_at), argMax(email, updated_at)
-- FROM user_profiles WHERE is_deleted = 0 GROUP BY user_id;


-- === AggregatingMergeTree: pre-aggregated rollups ===

CREATE TABLE page_views_hourly (
    hour         DateTime,
    page_url     String,
    country      LowCardinality(String),
    views        AggregateFunction(count, UInt64),
    unique_users AggregateFunction(uniq, UInt64),
    total_duration AggregateFunction(sum, UInt64),
    avg_duration AggregateFunction(avg, UInt32)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (page_url, country, hour);


-- === SummingMergeTree: automatic sum on merge ===

CREATE TABLE daily_stats (
    stat_date    Date,
    channel      LowCardinality(String),
    impressions  UInt64,
    clicks       UInt64,
    conversions  UInt64,
    revenue      Decimal64(2)
)
ENGINE = SummingMergeTree((impressions, clicks, conversions, revenue))
ORDER BY (stat_date, channel);
-- Rows with same ORDER BY key get summed during background merges


-- === CollapsingMergeTree: state changes via +1/-1 ===

CREATE TABLE user_sessions (
    user_id      UInt64,
    session_start DateTime,
    page_views   UInt32,
    duration_s   UInt32,
    sign         Int8  -- 1 = insert, -1 = cancel previous
)
ENGINE = CollapsingMergeTree(sign)
ORDER BY (user_id, session_start);
-- Insert sign=1 for new state, sign=-1 to cancel old + sign=1 for new
```

```python
# --- Python client for ClickHouse ---

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from typing import Any
from datetime import datetime


def create_client(
    host: str = "localhost",
    port: int = 8123,
    username: str = "default",
    password: str = "",
    database: str = "default",
) -> Client:
    """Create ClickHouse client connection."""
    return clickhouse_connect.get_client(
        host=host,
        port=port,
        username=username,
        password=password,
        database=database,
    )


def insert_events(
    client: Client,
    events: list[dict[str, Any]],
) -> int:
    """Batch insert events using columnar format.

    ClickHouse is columnar — insert by column, not by row.
    """
    columns = [
        "user_id", "event_type", "page_url",
        "device_type", "country", "duration_ms", "revenue",
    ]

    # Convert row-oriented to columnar
    data = [
        [event[col] for event in events]
        for col in columns
    ]

    client.insert(
        table="events",
        data=list(zip(*data)),    # Transpose back to rows for the driver
        column_names=columns,
    )

    return len(events)


def query_analytics(
    client: Client,
    start_date: str,
    end_date: str,
    group_by: str = "event_type",
) -> list[dict[str, Any]]:
    """Run analytical queries with ClickHouse optimizations."""
    result = client.query(
        """
        SELECT
            {group_by:Identifier} AS dimension,
            count() AS event_count,
            uniq(user_id) AS unique_users,
            avg(duration_ms) AS avg_duration,
            quantile(0.95)(duration_ms) AS p95_duration,
            sum(revenue) AS total_revenue,
            round(sum(revenue) / uniq(user_id), 2) AS revenue_per_user
        FROM events
        WHERE event_date BETWEEN {start:String} AND {end:String}
        GROUP BY dimension
        ORDER BY event_count DESC
        LIMIT 50
        """,
        parameters={
            "group_by": group_by,
            "start": start_date,
            "end": end_date,
        },
    )

    return [dict(zip(result.column_names, row)) for row in result.result_rows]
```

```python
# --- Engine selection guide ---

ENGINE_SELECTION = {
    "MergeTree": {
        "use_case": "General analytics, event logs, time-series",
        "dedup": "None (append-only)",
        "merge_behavior": "Compact parts, apply TTL",
        "query_pattern": "Range scans, aggregations",
        "example": "Clickstream events, application logs",
    },
    "ReplacingMergeTree": {
        "use_case": "Mutable entities, user profiles, configs",
        "dedup": "Keep latest by version column",
        "merge_behavior": "Deduplicate during merge (eventual)",
        "query_pattern": "Point lookups with FINAL or argMax",
        "example": "User profiles, product catalog, CDC sync",
    },
    "AggregatingMergeTree": {
        "use_case": "Pre-aggregated rollups, materialized views",
        "dedup": "Merge aggregate states",
        "merge_behavior": "Combine AggregateFunction columns",
        "query_pattern": "Dashboard queries on pre-aggregated data",
        "example": "Hourly/daily metric rollups",
    },
    "SummingMergeTree": {
        "use_case": "Counter/sum metrics, simple rollups",
        "dedup": "Sum numeric columns with same key",
        "merge_behavior": "Add values for duplicate keys",
        "query_pattern": "Sum queries on grouped data",
        "example": "Daily ad impressions, revenue totals",
    },
    "CollapsingMergeTree": {
        "use_case": "State changes, CDC with cancel/insert",
        "dedup": "Cancel pairs (sign +1/-1)",
        "merge_behavior": "Remove cancelled rows",
        "query_pattern": "Sum(sign * column) for correct totals",
        "example": "Session tracking, inventory changes",
    },
    "VersionedCollapsingMergeTree": {
        "use_case": "Same as Collapsing but order-independent",
        "dedup": "Cancel pairs with version ordering",
        "merge_behavior": "Remove cancelled, keep latest version",
        "query_pattern": "Same as Collapsing but safer for async inserts",
        "example": "Distributed CDC pipelines",
    },
}


# Performance tips for MergeTree family:
# 1. ORDER BY = primary key = sparse index — choose columns by query filter order
# 2. LowCardinality(String) for columns with < 10K unique values (2-10x faster)
# 3. PARTITION BY month or week — enables partition pruning and fast drops
# 4. TTL for automatic data lifecycle management
# 5. index_granularity = 8192 (default) — rarely needs changing
```

Key ClickHouse engine patterns:

| Engine | Dedup | Merge Behavior | Best For |
|---|---|---|---|
| MergeTree | None | Compact parts | Append-only events/logs |
| ReplacingMergeTree | Latest version | Deduplicate | Mutable entities |
| AggregatingMergeTree | Merge states | Combine aggregates | Pre-aggregated rollups |
| SummingMergeTree | Sum columns | Add values | Counter metrics |
| CollapsingMergeTree | Cancel pairs | Remove cancelled | State change tracking |

1. **ORDER BY is the primary key** -- choose columns matching your most common WHERE/GROUP BY
2. **LowCardinality for strings** -- 2-10x speedup for columns with < 10K unique values
3. **PARTITION BY month** -- enables fast partition drops and query pruning
4. **ReplacingMergeTree for upserts** -- use argMax() or FINAL for deduplication
5. **AggregatingMergeTree + materialized views** -- pre-compute dashboards at insert time'''
    ),
    (
        "databases/clickhouse-materialized-views",
        "Show ClickHouse materialized views and projections for real-time pre-aggregation.",
        '''ClickHouse materialized views and projections for real-time analytics:

```sql
-- === Materialized Views: transform data at insert time ===

-- Source table: raw events
CREATE TABLE raw_events (
    event_time   DateTime64(3),
    user_id      UInt64,
    event_type   LowCardinality(String),
    page_url     String,
    country      LowCardinality(String),
    device       LowCardinality(String),
    duration_ms  UInt32,
    revenue      Decimal64(2)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_type, event_time);


-- Target table for hourly aggregates
CREATE TABLE hourly_stats (
    hour         DateTime,
    event_type   LowCardinality(String),
    country      LowCardinality(String),
    event_count  AggregateFunction(count, UInt64),
    unique_users AggregateFunction(uniq, UInt64),
    total_revenue AggregateFunction(sum, Decimal64(2)),
    p95_duration AggregateFunction(quantile(0.95), UInt32)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (event_type, country, hour);


-- Materialized view: triggers on INSERT to raw_events
CREATE MATERIALIZED VIEW hourly_stats_mv
TO hourly_stats AS
SELECT
    toStartOfHour(event_time) AS hour,
    event_type,
    country,
    countState() AS event_count,
    uniqState(user_id) AS unique_users,
    sumState(revenue) AS total_revenue,
    quantileState(0.95)(duration_ms) AS p95_duration
FROM raw_events
GROUP BY hour, event_type, country;


-- Query the pre-aggregated data (fast!)
SELECT
    hour,
    event_type,
    country,
    countMerge(event_count) AS events,
    uniqMerge(unique_users) AS users,
    sumMerge(total_revenue) AS revenue,
    quantileMerge(0.95)(p95_duration) AS p95_ms
FROM hourly_stats
WHERE hour >= now() - INTERVAL 7 DAY
GROUP BY hour, event_type, country
ORDER BY hour DESC, events DESC;


-- === Multiple materialized views on one source ===
-- You can attach many MVs to one source table

-- MV 2: Per-user session summary
CREATE TABLE user_daily_summary (
    day          Date,
    user_id      UInt64,
    session_count SimpleAggregateFunction(sum, UInt64),
    total_duration SimpleAggregateFunction(sum, UInt64),
    page_views   SimpleAggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree()
ORDER BY (day, user_id);

CREATE MATERIALIZED VIEW user_daily_mv
TO user_daily_summary AS
SELECT
    toDate(event_time) AS day,
    user_id,
    1 AS session_count,
    duration_ms AS total_duration,
    if(event_type = 'page_view', 1, 0) AS page_views
FROM raw_events;


-- MV 3: Real-time funnel tracking
CREATE TABLE funnel_steps (
    day          Date,
    step_name    LowCardinality(String),
    unique_users AggregateFunction(uniq, UInt64)
)
ENGINE = AggregatingMergeTree()
ORDER BY (day, step_name);

CREATE MATERIALIZED VIEW funnel_mv
TO funnel_steps AS
SELECT
    toDate(event_time) AS day,
    event_type AS step_name,
    uniqState(user_id) AS unique_users
FROM raw_events
WHERE event_type IN ('landing', 'signup', 'purchase')
GROUP BY day, step_name;
```

```sql
-- === Projections: alternative sort orders within one table ===

-- Projections are like built-in materialized views stored
-- inside the same table — ClickHouse auto-selects the best one

CREATE TABLE web_analytics (
    event_time   DateTime,
    user_id      UInt64,
    page_url     String,
    country      LowCardinality(String),
    device       LowCardinality(String),
    duration_ms  UInt32
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (page_url, event_time);  -- Primary sort: by page

-- Projection 1: sorted by country for country-based queries
ALTER TABLE web_analytics ADD PROJECTION country_proj (
    SELECT
        country,
        event_time,
        count() AS cnt,
        avg(duration_ms) AS avg_duration
    GROUP BY country, event_time
    ORDER BY country, event_time
);

-- Projection 2: sorted by device for device analytics
ALTER TABLE web_analytics ADD PROJECTION device_proj (
    SELECT
        device,
        toStartOfHour(event_time) AS hour,
        count() AS cnt,
        uniq(user_id) AS users
    GROUP BY device, hour
    ORDER BY device, hour
);

-- Materialize projections for existing data
ALTER TABLE web_analytics MATERIALIZE PROJECTION country_proj;
ALTER TABLE web_analytics MATERIALIZE PROJECTION device_proj;

-- ClickHouse automatically picks the best projection:
-- Uses country_proj:
SELECT country, count() FROM web_analytics
WHERE event_time > now() - INTERVAL 1 DAY
GROUP BY country;

-- Uses device_proj:
SELECT device, uniq(user_id) FROM web_analytics
WHERE event_time > now() - INTERVAL 1 DAY
GROUP BY device;

-- Uses base table (page_url is in primary ORDER BY):
SELECT page_url, count() FROM web_analytics
WHERE page_url = '/checkout'
GROUP BY page_url;
```

```python
# --- Managing materialized views in Python ---

from clickhouse_connect.driver.client import Client
from typing import Any
from dataclasses import dataclass


@dataclass
class MVDefinition:
    """Materialized view definition."""
    name: str
    source_table: str
    target_table: str
    target_engine: str
    select_query: str
    order_by: str
    partition_by: str | None = None


def create_mv_pipeline(
    client: Client,
    mv_def: MVDefinition,
) -> None:
    """Create target table and materialized view."""
    # Create target table
    client.command(f"""
        CREATE TABLE IF NOT EXISTS {mv_def.target_table}
        ENGINE = {mv_def.target_engine}
        {f"PARTITION BY {mv_def.partition_by}" if mv_def.partition_by else ""}
        ORDER BY ({mv_def.order_by})
        AS {mv_def.select_query}
        LIMIT 0
    """)

    # Create materialized view
    client.command(f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {mv_def.name}
        TO {mv_def.target_table}
        AS {mv_def.select_query}
    """)


def check_mv_lag(
    client: Client,
    source_table: str,
    target_table: str,
    time_column: str = "event_time",
) -> dict[str, Any]:
    """Check if materialized view is keeping up with inserts."""
    source_max = client.query(
        f"SELECT max({time_column}) FROM {source_table}"
    ).first_row[0]

    target_max = client.query(
        f"SELECT max({time_column}) FROM {target_table}"
    ).first_row[0]

    lag_seconds = (source_max - target_max).total_seconds() if (
        source_max and target_max
    ) else None

    source_count = client.query(
        f"SELECT count() FROM {source_table}"
    ).first_row[0]

    target_count = client.query(
        f"SELECT count() FROM {target_table}"
    ).first_row[0]

    return {
        "source_latest": source_max,
        "target_latest": target_max,
        "lag_seconds": lag_seconds,
        "source_rows": source_count,
        "target_rows": target_count,
    }


def list_materialized_views(client: Client, database: str = "default") -> list[dict[str, Any]]:
    """List all materialized views and their targets."""
    result = client.query(f"""
        SELECT
            name,
            as_select,
            engine,
            metadata_modification_time
        FROM system.tables
        WHERE database = '{database}'
          AND engine = 'MaterializedView'
        ORDER BY name
    """)

    return [dict(zip(result.column_names, row)) for row in result.result_rows]
```

Key materialized view patterns:

| Pattern | Mechanism | Best For |
|---|---|---|
| MV to AggregatingMergeTree | -State() / -Merge() functions | Complex aggregates (uniq, quantile) |
| MV to SummingMergeTree | Auto-sum on merge | Simple counters and sums |
| Multiple MVs on one source | Fan-out at insert time | Different dashboards from one stream |
| Projections | Built-in alternative indexes | Multiple query patterns on one table |
| Chained MVs | MV -> MV -> MV | Multi-level rollups (5m -> 1h -> 1d) |

1. **-State() and -Merge()** -- use aggregate function combinators for correct pre-aggregation
2. **Multiple MVs per source** -- each insert triggers all attached MVs, pay once at write time
3. **Projections over MVs** -- when you need different sort orders without separate tables
4. **SimpleAggregateFunction** -- use for sum/min/max/any (lighter than full AggregateFunction)
5. **Check MV lag** -- monitor target vs source freshness to catch processing delays'''
    ),
    (
        "databases/clickhouse-distributed",
        "Show ClickHouse distributed queries and sharding: cluster setup, shard keys, and cross-shard operations.",
        '''ClickHouse distributed queries and sharding for horizontal scale:

```xml
<!-- === ClickHouse cluster configuration (config.xml) === -->

<!-- Define a 3-shard, 2-replica cluster -->
<clickhouse>
  <remote_servers>
    <analytics_cluster>
      <!-- Shard 1: primary + replica -->
      <shard>
        <weight>1</weight>
        <internal_replication>true</internal_replication>
        <replica>
          <host>ch-shard1-r1</host>
          <port>9000</port>
        </replica>
        <replica>
          <host>ch-shard1-r2</host>
          <port>9000</port>
        </replica>
      </shard>

      <!-- Shard 2 -->
      <shard>
        <weight>1</weight>
        <internal_replication>true</internal_replication>
        <replica>
          <host>ch-shard2-r1</host>
          <port>9000</port>
        </replica>
        <replica>
          <host>ch-shard2-r2</host>
          <port>9000</port>
        </replica>
      </shard>

      <!-- Shard 3 -->
      <shard>
        <weight>1</weight>
        <internal_replication>true</internal_replication>
        <replica>
          <host>ch-shard3-r1</host>
          <port>9000</port>
        </replica>
        <replica>
          <host>ch-shard3-r2</host>
          <port>9000</port>
        </replica>
      </shard>
    </analytics_cluster>
  </remote_servers>
</clickhouse>
```

```sql
-- === Local and Distributed table setup ===

-- Step 1: Create local table on each shard (ReplicatedMergeTree)
CREATE TABLE events_local ON CLUSTER analytics_cluster (
    event_time   DateTime64(3),
    event_date   Date DEFAULT toDate(event_time),
    user_id      UInt64,
    event_type   LowCardinality(String),
    page_url     String,
    country      LowCardinality(String),
    duration_ms  UInt32,
    revenue      Decimal64(2)
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/events_local',   -- ZooKeeper path
    '{replica}'                                   -- Replica ID
)
PARTITION BY toYYYYMM(event_date)
ORDER BY (user_id, event_time)
TTL event_date + INTERVAL 180 DAY;


-- Step 2: Create Distributed table (virtual layer over all shards)
CREATE TABLE events_distributed ON CLUSTER analytics_cluster (
    event_time   DateTime64(3),
    event_date   Date DEFAULT toDate(event_time),
    user_id      UInt64,
    event_type   LowCardinality(String),
    page_url     String,
    country      LowCardinality(String),
    duration_ms  UInt32,
    revenue      Decimal64(2)
)
ENGINE = Distributed(
    'analytics_cluster',       -- Cluster name
    'default',                 -- Database
    'events_local',            -- Local table
    sipHash64(user_id)         -- Sharding key (determines which shard)
);

-- Inserts go to Distributed table -> routed to correct shard
INSERT INTO events_distributed VALUES (...);

-- Queries go to Distributed table -> scatter-gather across shards
SELECT event_type, count(), uniq(user_id)
FROM events_distributed
WHERE event_date = today()
GROUP BY event_type
ORDER BY count() DESC;


-- === Sharding key selection ===

-- Good: user_id — even distribution, user queries hit 1 shard
-- ENGINE = Distributed('cluster', 'db', 'local', sipHash64(user_id))

-- Good: tenant_id — tenant isolation, single-shard queries
-- ENGINE = Distributed('cluster', 'db', 'local', sipHash64(tenant_id))

-- Bad: event_time — skewed to recent data, hotspot on latest shard
-- Bad: country — uneven distribution (US >> LI)

-- Composite sharding key for balanced distribution:
-- ENGINE = Distributed('cluster', 'db', 'local',
--          sipHash64(concat(toString(user_id), event_type)))
```

```python
# --- Distributed query patterns and monitoring ---

from clickhouse_connect.driver.client import Client
from typing import Any


def query_cluster_health(client: Client) -> list[dict[str, Any]]:
    """Check cluster shard and replica status."""
    result = client.query("""
        SELECT
            cluster,
            shard_num,
            replica_num,
            host_name,
            port,
            is_local,
            errors_count,
            estimated_recovery_time
        FROM system.clusters
        WHERE cluster = 'analytics_cluster'
        ORDER BY shard_num, replica_num
    """)
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def query_shard_sizes(client: Client) -> list[dict[str, Any]]:
    """Check data distribution across shards."""
    result = client.query("""
        SELECT
            hostName() AS host,
            formatReadableSize(sum(bytes_on_disk)) AS disk_size,
            sum(rows) AS total_rows,
            count() AS part_count,
            min(min_date) AS oldest_data,
            max(max_date) AS newest_data
        FROM clusterAllReplicas('analytics_cluster', system.parts)
        WHERE table = 'events_local'
          AND active = 1
        GROUP BY host
        ORDER BY total_rows DESC
    """)
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def distributed_query_with_settings(
    client: Client,
    query: str,
    max_execution_time: int = 30,
    max_threads: int = 8,
) -> list[dict[str, Any]]:
    """Execute distributed query with performance settings."""
    settings = {
        # Distributed query settings
        "max_execution_time": max_execution_time,
        "max_threads": max_threads,
        "distributed_aggregation_memory_efficient": 1,
        "prefer_localhost_replica": 1,

        # Push aggregation down to shards (reduce network transfer)
        "distributed_group_by_no_merge": 0,
        "optimize_distributed_group_by_sharding_key": 1,

        # Two-stage aggregation for better memory efficiency
        "group_by_two_level_threshold": 100000,
    }

    result = client.query(query, settings=settings)
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def cross_shard_join_pattern(client: Client) -> list[dict[str, Any]]:
    """Cross-shard JOIN using GLOBAL keyword.

    Regular JOINs on Distributed tables can be expensive:
      - Right table is sent to every shard for local join
      - Use GLOBAL IN / GLOBAL JOIN for small right-side tables

    Alternatives to cross-shard joins:
      1. Denormalize: store joined data in the same table
      2. Dictionaries: use external dictionaries for lookups
      3. GLOBAL JOIN: broadcast small table to all shards
      4. Pre-join in materialized views at insert time
    """
    result = client.query("""
        -- Pattern 1: GLOBAL IN for subquery broadcast
        SELECT user_id, count() AS events
        FROM events_distributed
        WHERE user_id GLOBAL IN (
            SELECT user_id
            FROM user_segments_distributed
            WHERE segment = 'high_value'
        )
        GROUP BY user_id
        ORDER BY events DESC
        LIMIT 100
    """)
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


# External dictionaries for efficient lookups
DICTIONARY_DDL = """
CREATE DICTIONARY IF NOT EXISTS country_dict (
    country_code String,
    country_name String,
    continent    String,
    population   UInt64
)
PRIMARY KEY country_code
SOURCE(CLICKHOUSE(
    HOST 'localhost'
    PORT 9000
    TABLE 'country_reference'
    DB 'default'
))
LIFETIME(MIN 3600 MAX 7200)
LAYOUT(HASHED());

-- Usage in queries (no JOIN needed):
-- SELECT
--     country,
--     dictGet('country_dict', 'country_name', country) AS name,
--     dictGet('country_dict', 'continent', country) AS continent,
--     count() AS events
-- FROM events_distributed
-- GROUP BY country;
"""
```

Key ClickHouse distributed patterns:

| Feature | Detail |
|---|---|
| ReplicatedMergeTree | Per-shard replication via ZooKeeper/ClickHouse Keeper |
| Distributed engine | Virtual table routing queries across shards |
| Shard key selection | Hash on high-cardinality column (user_id, tenant_id) |
| GLOBAL IN/JOIN | Broadcast small tables to all shards for cross-shard joins |
| Dictionaries | External lookup tables cached in memory, avoid JOINs |
| ON CLUSTER DDL | Execute DDL on all nodes in one command |

1. **Shard by query pattern** -- choose key that makes most queries single-shard
2. **ReplicatedMergeTree for HA** -- automatic cross-replica synchronization
3. **Avoid cross-shard JOINs** -- denormalize, use dictionaries, or GLOBAL IN
4. **Push aggregation to shards** -- distributed_group_by settings reduce network
5. **Monitor shard balance** -- uneven data distribution creates hotspots'''
    ),
    (
        "databases/clickhouse-kafka-pipeline",
        "Build a real-time analytics pipeline: Kafka ingestion into ClickHouse with materialized views.",
        '''Real-time analytics pipeline: Kafka to ClickHouse:

```sql
-- === Kafka Engine table: consumes from Kafka topic ===

-- Step 1: Kafka consumer table
-- This table represents the Kafka consumer — reads messages continuously
CREATE TABLE kafka_events (
    raw_message String
)
ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka1:9092,kafka2:9092,kafka3:9092',
    kafka_topic_list = 'analytics.events',
    kafka_group_name = 'clickhouse_consumer_group',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 4,           -- Parallelism
    kafka_max_block_size = 65536,      -- Batch size
    kafka_skip_broken_messages = 10,   -- Skip N bad messages
    kafka_poll_timeout_ms = 5000;


-- Step 2: Target MergeTree table for permanent storage
CREATE TABLE events (
    event_id     UUID,
    event_time   DateTime64(3),
    event_date   Date DEFAULT toDate(event_time),
    user_id      UInt64,
    event_type   LowCardinality(String),
    page_url     String,
    country      LowCardinality(String),
    device       LowCardinality(String),
    duration_ms  UInt32,
    revenue      Decimal64(2) DEFAULT 0,
    properties   Map(String, String),
    -- Kafka metadata
    _kafka_topic     LowCardinality(String) DEFAULT '',
    _kafka_partition UInt32 DEFAULT 0,
    _kafka_offset    UInt64 DEFAULT 0
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_type, user_id, event_time)
TTL event_date + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;


-- Step 3: Materialized view to pipe Kafka -> MergeTree
-- This MV triggers on every batch consumed from Kafka
CREATE MATERIALIZED VIEW kafka_to_events_mv
TO events AS
SELECT
    JSONExtract(raw_message, 'event_id', 'UUID') AS event_id,
    parseDateTimeBestEffort(
        JSONExtractString(raw_message, 'timestamp')
    ) AS event_time,
    JSONExtract(raw_message, 'user_id', 'UInt64') AS user_id,
    JSONExtractString(raw_message, 'event_type') AS event_type,
    JSONExtractString(raw_message, 'page_url') AS page_url,
    JSONExtractString(raw_message, 'country') AS country,
    JSONExtractString(raw_message, 'device') AS device,
    JSONExtract(raw_message, 'duration_ms', 'UInt32') AS duration_ms,
    JSONExtract(raw_message, 'revenue', 'Float64') AS revenue,
    JSONExtractKeysAndValues(raw_message, 'properties', 'String')
        AS properties,
    _topic AS _kafka_topic,
    _partition AS _kafka_partition,
    _offset AS _kafka_offset
FROM kafka_events;


-- === Alternative: direct JSON parsing without raw_message ===

CREATE TABLE kafka_events_typed (
    event_id     UUID,
    timestamp    String,
    user_id      UInt64,
    event_type   String,
    page_url     String,
    country      String,
    device       String,
    duration_ms  UInt32,
    revenue      Float64
)
ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka1:9092,kafka2:9092,kafka3:9092',
    kafka_topic_list = 'analytics.events',
    kafka_group_name = 'clickhouse_typed_consumer',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 4;
```

```python
# --- Pipeline monitoring and management ---

from clickhouse_connect.driver.client import Client
from typing import Any
from datetime import datetime, timedelta


def check_kafka_lag(client: Client) -> list[dict[str, Any]]:
    """Monitor Kafka consumer lag in ClickHouse."""
    result = client.query("""
        SELECT
            database,
            table AS kafka_table,
            -- Check latest Kafka offsets vs consumed
            metadata_modification_time AS last_activity,
            total_rows,
            bytes_on_disk
        FROM system.tables
        WHERE engine = 'Kafka'
        ORDER BY database, table
    """)
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def check_ingestion_rate(
    client: Client,
    table: str = "events",
    interval_minutes: int = 5,
) -> dict[str, Any]:
    """Measure real-time ingestion rate."""
    result = client.query(f"""
        SELECT
            count() AS events_last_interval,
            round(count() / {interval_minutes} / 60, 0) AS events_per_second,
            uniq(user_id) AS unique_users,
            min(event_time) AS oldest_event,
            max(event_time) AS newest_event,
            dateDiff('second', min(event_time), max(event_time)) AS span_seconds
        FROM {table}
        WHERE event_time >= now() - INTERVAL {interval_minutes} MINUTE
    """)

    if result.result_rows:
        return dict(zip(result.column_names, result.result_rows[0]))
    return {}


def check_pipeline_health(client: Client) -> dict[str, Any]:
    """Comprehensive pipeline health check."""
    health: dict[str, Any] = {}

    # 1. Check for stale data (ingestion lag)
    lag_result = client.query("""
        SELECT
            dateDiff('second', max(event_time), now()) AS lag_seconds
        FROM events
    """)
    health["ingestion_lag_seconds"] = lag_result.first_row[0]

    # 2. Check part merges (healthy system merges in background)
    merge_result = client.query("""
        SELECT
            table,
            count() AS active_parts,
            sum(rows) AS total_rows,
            formatReadableSize(sum(bytes_on_disk)) AS disk_size,
            max(modification_time) AS latest_part
        FROM system.parts
        WHERE table = 'events' AND active = 1
        GROUP BY table
    """)
    if merge_result.result_rows:
        health["parts"] = dict(
            zip(merge_result.column_names, merge_result.result_rows[0])
        )

    # 3. Check for broken materialized views
    mv_errors = client.query("""
        SELECT
            database, table, engine,
            metadata_modification_time,
            create_table_query
        FROM system.tables
        WHERE engine = 'MaterializedView'
          AND database = 'default'
    """)
    health["materialized_views"] = [
        dict(zip(mv_errors.column_names, row))
        for row in mv_errors.result_rows
    ]

    # 4. Check mutations (async ALTER operations)
    mutations = client.query("""
        SELECT
            table, mutation_id, command,
            is_done, parts_to_do,
            create_time, latest_fail_reason
        FROM system.mutations
        WHERE NOT is_done
        ORDER BY create_time DESC
    """)
    health["pending_mutations"] = [
        dict(zip(mutations.column_names, row))
        for row in mutations.result_rows
    ]

    return health
```

```python
# --- Complete pipeline architecture ---

PIPELINE_ARCHITECTURE = """
Real-Time Analytics Pipeline:

  ┌─────────┐    ┌───────┐    ┌─────────────┐    ┌───────────────┐
  │ App/API │───▶│ Kafka │───▶│ Kafka Engine │───▶│ MergeTree     │
  │ Events  │    │ Topic │    │ (consumer)   │    │ (raw storage) │
  └─────────┘    └───────┘    └─────────────┘    └───────┬───────┘
                                                         │
                              ┌──────────────────────────┤
                              │                          │
                    ┌─────────▼──────────┐    ┌─────────▼──────────┐
                    │ MV: hourly_stats   │    │ MV: user_funnel    │
                    │ (AggregatingMT)    │    │ (AggregatingMT)    │
                    └─────────┬──────────┘    └────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │ MV: daily_stats    │    ┌──────────┐
                    │ (chained rollup)   │───▶│ Grafana  │
                    └────────────────────┘    └──────────┘

Data flow:
  1. Applications produce JSON events to Kafka topic
  2. Kafka Engine table continuously consumes messages
  3. MV parses JSON and inserts into MergeTree storage
  4. Additional MVs compute real-time aggregates
  5. Grafana queries pre-aggregated tables for dashboards
"""


def create_error_handling_pipeline(client: Client) -> None:
    """Create pipeline with dead-letter queue for bad messages.

    Error handling strategies:
      1. kafka_skip_broken_messages — skip N bad messages per batch
      2. Dead-letter table — store unparseable messages for review
      3. Null() engine — discard data (for testing)
    """
    # Dead letter queue for unparseable messages
    client.command("""
        CREATE TABLE IF NOT EXISTS kafka_dead_letters (
            received_at DateTime DEFAULT now(),
            raw_message String,
            error_reason String,
            kafka_topic  String,
            kafka_offset UInt64
        )
        ENGINE = MergeTree()
        ORDER BY received_at
        TTL received_at + INTERVAL 30 DAY;
    """)

    # Materialized view with error routing
    # Use try/catch-style with ifNull and coalesce
    client.command("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS kafka_error_handler_mv
        TO kafka_dead_letters AS
        SELECT
            now() AS received_at,
            raw_message,
            'parse_error' AS error_reason,
            _topic AS kafka_topic,
            _offset AS kafka_offset
        FROM kafka_events
        WHERE JSONHas(raw_message, 'event_id') = 0
           OR JSONHas(raw_message, 'user_id') = 0;
    """)
```

Key Kafka-ClickHouse pipeline patterns:

| Component | Role | Key Settings |
|---|---|---|
| Kafka Engine table | Consumer | kafka_num_consumers, kafka_max_block_size |
| MV (Kafka -> MergeTree) | Transform + route | JSON parsing, type coercion |
| MergeTree target | Persistent storage | ORDER BY, PARTITION BY, TTL |
| Additional MVs | Pre-aggregation | AggregatingMergeTree, -State() functions |
| Dead letter table | Error handling | Capture unparseable messages |
| Monitoring queries | Observability | system.parts, system.mutations |

1. **Kafka Engine = consumer** -- ClickHouse manages offsets, no external consumer needed
2. **MV pipes data** -- materialized view triggers on each consumed batch
3. **Multiple MVs per source** -- fan-out to raw storage + aggregates simultaneously
4. **Dead letter queues** -- capture bad messages instead of losing data
5. **Monitor ingestion lag** -- compare max(event_time) to now() for freshness alerts'''
    ),
]
