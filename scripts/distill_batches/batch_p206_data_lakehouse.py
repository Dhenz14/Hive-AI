"""Data lakehouse — Delta Lake/Iceberg table formats, ACID on object storage, time travel, schema evolution, partition pruning, merge operations (upsert)."""

PAIRS = [
    (
        "data-engineering/delta-lake-fundamentals",
        "Show how to build a Delta Lake-based data lakehouse with ACID transactions, schema enforcement, time travel queries, and optimized writes using PySpark.",
        '''Delta Lake data lakehouse with ACID transactions, time travel, and optimization:

```python
"""
Delta Lake data lakehouse: ACID transactions on object storage,
schema enforcement, time travel, and write optimization.
"""

from delta import DeltaTable, configure_spark_with_delta_pip
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, current_timestamp, lit, when, hash as spark_hash,
    year, month, dayofmonth, hour, expr, count, sum as spark_sum,
    avg, max as spark_max, min as spark_min,
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType,
    TimestampType, LongType, IntegerType,
)
from typing import Optional
from datetime import datetime, timedelta


def create_lakehouse_session(
    app_name: str = "DataLakehouse",
    warehouse_path: str = "s3a://lakehouse/warehouse",
) -> SparkSession:
    """Create Spark session with Delta Lake configuration."""
    builder = (
        SparkSession.builder
        .appName(app_name)
        .config("spark.sql.extensions",
                "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.sql.warehouse.dir", warehouse_path)
        .config("spark.databricks.delta.optimizeWrite.enabled", "true")
        .config("spark.databricks.delta.autoCompact.enabled", "true")
        .config("spark.sql.shuffle.partitions", "200")
        .config("spark.hadoop.fs.s3a.impl",
                "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.aws.credentials.provider",
                "com.amazonaws.auth.DefaultAWSCredentialsProviderChain")
    )
    return configure_spark_with_delta_pip(builder).getOrCreate()


EVENTS_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("user_id", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("event_timestamp", TimestampType(), False),
    StructField("properties", StringType(), True),
    StructField("amount", DoubleType(), True),
    StructField("session_id", StringType(), True),
    StructField("device_type", StringType(), True),
    StructField("country", StringType(), True),
    StructField("_ingested_at", TimestampType(), False),
])


class DeltaLakeManager:
    """Manages Delta Lake tables with ACID operations."""

    def __init__(self, spark: SparkSession, base_path: str):
        self.spark = spark
        self.base_path = base_path

    def create_table(
        self, table_name: str, schema: StructType,
        partition_columns: list[str], comment: str = "",
        properties: Optional[dict[str, str]] = None,
    ) -> str:
        """Create a Delta table with schema and partitioning."""
        table_path = f"{self.base_path}/{table_name}"

        builder = (
            DeltaTable.createIfNotExists(self.spark)
            .location(table_path)
            .addColumns(schema)
            .comment(comment)
        )

        if partition_columns:
            builder = builder.partitionedBy(*partition_columns)

        props = {
            "delta.autoOptimize.optimizeWrite": "true",
            "delta.autoOptimize.autoCompact": "true",
            "delta.logRetentionDuration": "interval 30 days",
            "delta.deletedFileRetentionDuration": "interval 7 days",
            "delta.enableChangeDataFeed": "true",
        }
        if properties:
            props.update(properties)

        for key, value in props.items():
            builder = builder.property(key, value)

        builder.execute()
        return table_path

    def append(self, table_path: str, df: DataFrame) -> None:
        """Append data with ACID guarantees."""
        (
            df.withColumn("_ingested_at", current_timestamp())
            .write
            .format("delta")
            .mode("append")
            .save(table_path)
        )

    def upsert(
        self, table_path: str, updates: DataFrame,
        merge_keys: list[str],
        update_columns: Optional[list[str]] = None,
    ) -> None:
        """MERGE (upsert): update existing rows, insert new ones."""
        target = DeltaTable.forPath(self.spark, table_path)

        condition = " AND ".join(
            f"target.{k} = source.{k}" for k in merge_keys
        )

        merge_builder = (
            target.alias("target")
            .merge(updates.alias("source"), condition)
        )

        if update_columns:
            update_set = {c: f"source.{c}" for c in update_columns}
            update_set["_updated_at"] = "current_timestamp()"
            merge_builder = merge_builder.whenMatchedUpdate(
                set=update_set
            )
        else:
            merge_builder = merge_builder.whenMatchedUpdateAll()

        merge_builder = merge_builder.whenNotMatchedInsertAll()
        merge_builder.execute()

    def scd_type2(
        self, table_path: str, updates: DataFrame,
        key_columns: list[str], tracked_columns: list[str],
    ) -> None:
        """
        Slowly Changing Dimension Type 2: maintain full history
        by closing old records and inserting new versions.
        """
        target = DeltaTable.forPath(self.spark, table_path)

        key_condition = " AND ".join(
            f"target.{k} = source.{k}" for k in key_columns
        )
        change_condition = " OR ".join(
            f"target.{c} != source.{c}" for c in tracked_columns
        )

        (
            target.alias("target")
            .merge(updates.alias("source"), key_condition)
            .whenMatchedUpdate(
                condition=(
                    f"target.is_current = true AND ({change_condition})"
                ),
                set={
                    "is_current": "false",
                    "end_date": "source.effective_date",
                    "_updated_at": "current_timestamp()",
                },
            )
            .whenNotMatchedInsertAll()
            .execute()
        )

    # --- Time travel ---

    def read_at_version(
        self, table_path: str, version: int
    ) -> DataFrame:
        return (
            self.spark.read.format("delta")
            .option("versionAsOf", version)
            .load(table_path)
        )

    def read_at_timestamp(
        self, table_path: str, timestamp: str
    ) -> DataFrame:
        return (
            self.spark.read.format("delta")
            .option("timestampAsOf", timestamp)
            .load(table_path)
        )

    def get_history(
        self, table_path: str, limit: int = 20
    ) -> DataFrame:
        dt = DeltaTable.forPath(self.spark, table_path)
        return dt.history(limit)

    def get_changes(
        self, table_path: str, start_version: int,
        end_version: Optional[int] = None,
    ) -> DataFrame:
        """Read Change Data Feed between versions."""
        reader = (
            self.spark.read.format("delta")
            .option("readChangeFeed", "true")
            .option("startingVersion", start_version)
        )
        if end_version:
            reader = reader.option("endingVersion", end_version)
        return reader.load(table_path)

    # --- Table maintenance ---

    def optimize(
        self, table_path: str,
        z_order_columns: Optional[list[str]] = None,
        where: Optional[str] = None,
    ) -> None:
        """Compact small files and optionally Z-ORDER."""
        dt = DeltaTable.forPath(self.spark, table_path)

        if z_order_columns:
            if where:
                dt.optimize().where(where).executeZOrderBy(
                    *z_order_columns
                )
            else:
                dt.optimize().executeZOrderBy(*z_order_columns)
        else:
            if where:
                dt.optimize().where(where).executeCompaction()
            else:
                dt.optimize().executeCompaction()

    def vacuum(
        self, table_path: str, retention_hours: int = 168
    ) -> None:
        """Remove old files no longer referenced."""
        dt = DeltaTable.forPath(self.spark, table_path)
        dt.vacuum(retention_hours)


def demo():
    spark = create_lakehouse_session()
    mgr = DeltaLakeManager(spark, "s3a://lakehouse/bronze")

    mgr.create_table(
        table_name="events", schema=EVENTS_SCHEMA,
        partition_columns=["year(event_timestamp)", "month(event_timestamp)"],
        comment="Raw event data with monthly partitioning",
    )

    # Time travel: compare today vs yesterday
    current = spark.read.format("delta").load(
        "s3a://lakehouse/bronze/events"
    )
    yesterday = mgr.read_at_timestamp(
        "s3a://lakehouse/bronze/events",
        (datetime.now() - timedelta(days=1)).isoformat(),
    )

    # Get changes since version 10
    changes = mgr.get_changes(
        "s3a://lakehouse/bronze/events", start_version=10
    )
    changes.filter(col("_change_type") == "insert").show()
```

**Delta Lake ACID operations:**

| Operation | Guarantee | Use Case |
|---|---|---|
| Append | Atomic file commit | Streaming ingestion |
| MERGE (upsert) | Atomic read-modify-write | CDC, SCD updates |
| OVERWRITE | Atomic partition replacement | Full reload, backfill |
| DELETE | Predicate-based atomic delete | GDPR right-to-erasure |
| Time travel | Read any historical version | Audit, debugging, rollback |

**Key patterns:**
- Enable `autoOptimize` and `autoCompact` to prevent small file accumulation
- Use `enableChangeDataFeed` for downstream CDC consumption
- MERGE with key columns for atomic upserts (insert or update in one transaction)
- SCD Type 2 via MERGE: close old records and insert new versions atomically
- Z-ORDER on query filter columns for multi-dimensional partition pruning
- VACUUM after retention period to reclaim storage (default 7 days for safety)
- Time travel via version number or timestamp for audit and debugging'''
    ),
    (
        "data-engineering/iceberg-table-format",
        "Build a data lakehouse using Apache Iceberg with PySpark showing table creation, schema evolution, hidden partitioning, snapshot management, and incremental reads.",
        '''Apache Iceberg data lakehouse with hidden partitioning, schema evolution, and snapshot management:

```python
"""
Apache Iceberg data lakehouse: hidden partitioning, schema evolution,
snapshot isolation, and incremental processing.
"""

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, current_timestamp, lit, expr, when,
    year, month, dayofmonth, hour,
)
from typing import Optional


def create_iceberg_session(
    warehouse_path: str = "s3://lakehouse/iceberg",
    catalog_name: str = "lakehouse",
) -> SparkSession:
    """Create Spark session configured for Apache Iceberg."""
    return (
        SparkSession.builder
        .appName("IcebergLakehouse")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config(
            f"spark.sql.catalog.{catalog_name}",
            "org.apache.iceberg.spark.SparkCatalog",
        )
        .config(f"spark.sql.catalog.{catalog_name}.type", "hadoop")
        .config(
            f"spark.sql.catalog.{catalog_name}.warehouse",
            warehouse_path,
        )
        .config("spark.sql.defaultCatalog", catalog_name)
        .getOrCreate()
    )


class IcebergTableManager:
    """Manages Iceberg tables with production features."""

    def __init__(self, spark: SparkSession, catalog: str = "lakehouse"):
        self.spark = spark
        self.catalog = catalog

    def create_table(
        self, database: str, table_name: str, schema_ddl: str,
        partition_spec: str = "", sort_order: str = "",
        properties: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Create Iceberg table with hidden partitioning.

        Hidden partitioning transforms:
        - years(ts)      -> partition by year from timestamp
        - months(ts)     -> partition by year-month
        - days(ts)       -> partition by date
        - hours(ts)      -> partition by date-hour
        - bucket(N, col) -> hash partition into N buckets
        - truncate(L, col) -> truncate string to length L
        """
        self.spark.sql(f"CREATE DATABASE IF NOT EXISTS {database}")

        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {database}.{table_name} (
                {schema_ddl}
            ) USING iceberg
        """
        if partition_spec:
            create_sql += f" PARTITIONED BY ({partition_spec})"

        default_props = {
            "write.format.default": "parquet",
            "write.parquet.compression-codec": "zstd",
            "write.metadata.delete-after-commit.enabled": "true",
            "write.metadata.previous-versions-max": "100",
            "read.split.target-size": "134217728",
            "write.target-file-size-bytes": "536870912",
            "history.expire.max-snapshot-age-ms": "432000000",
            "write.distribution-mode": "hash",
        }
        if properties:
            default_props.update(properties)

        props_str = ", ".join(
            f"'{k}' = '{v}'" for k, v in default_props.items()
        )
        create_sql += f" TBLPROPERTIES ({props_str})"
        self.spark.sql(create_sql)

    def evolve_schema(
        self, database: str, table_name: str,
        operations: list[dict[str, str]],
    ) -> None:
        """
        Evolve table schema without rewriting data.
        Supports: add, drop, rename, widen, make_optional
        """
        fqn = f"{database}.{table_name}"

        for op in operations:
            op_type = op["type"]
            if op_type == "add":
                after = f"AFTER {op['after']}" if op.get("after") else ""
                self.spark.sql(
                    f"ALTER TABLE {fqn} ADD COLUMN "
                    f"{op['name']} {op['data_type']} {after}"
                )
            elif op_type == "drop":
                self.spark.sql(
                    f"ALTER TABLE {fqn} DROP COLUMN {op['name']}"
                )
            elif op_type == "rename":
                self.spark.sql(
                    f"ALTER TABLE {fqn} RENAME COLUMN "
                    f"{op['from']} TO {op['to']}"
                )
            elif op_type == "widen":
                self.spark.sql(
                    f"ALTER TABLE {fqn} ALTER COLUMN "
                    f"{op['name']} TYPE {op['new_type']}"
                )

    def evolve_partition(
        self, database: str, table_name: str,
        new_partition_spec: str,
    ) -> None:
        """Evolve partitioning without rewriting existing data."""
        fqn = f"{database}.{table_name}"
        self.spark.sql(
            f"ALTER TABLE {fqn} "
            f"REPLACE PARTITION FIELD {new_partition_spec}"
        )

    def list_snapshots(
        self, database: str, table_name: str
    ) -> DataFrame:
        fqn = f"{database}.{table_name}"
        return self.spark.sql(f"SELECT * FROM {fqn}.snapshots")

    def read_at_snapshot(
        self, database: str, table_name: str, snapshot_id: int
    ) -> DataFrame:
        fqn = f"{database}.{table_name}"
        return self.spark.read.option(
            "snapshot-id", snapshot_id
        ).table(fqn)

    def read_at_timestamp(
        self, database: str, table_name: str, timestamp: str
    ) -> DataFrame:
        fqn = f"{database}.{table_name}"
        return self.spark.read.option(
            "as-of-timestamp", timestamp
        ).table(fqn)

    def rollback_to_snapshot(
        self, database: str, table_name: str, snapshot_id: int
    ) -> None:
        fqn = f"{database}.{table_name}"
        self.spark.sql(
            f"CALL {self.catalog}.system.rollback_to_snapshot("
            f"'{fqn}', {snapshot_id})"
        )

    def read_incremental(
        self, database: str, table_name: str,
        start_snapshot: int,
        end_snapshot: Optional[int] = None,
    ) -> DataFrame:
        """Read only changes between two snapshots."""
        fqn = f"{database}.{table_name}"
        reader = self.spark.read.option(
            "start-snapshot-id", start_snapshot
        )
        if end_snapshot:
            reader = reader.option("end-snapshot-id", end_snapshot)
        return reader.table(fqn)

    def merge_into(
        self, database: str, table_name: str,
        source_df: DataFrame, merge_keys: list[str],
    ) -> None:
        """Atomic MERGE INTO operation for upserts."""
        fqn = f"{database}.{table_name}"
        source_df.createOrReplaceTempView("source_data")

        key_condition = " AND ".join(
            f"t.{k} = s.{k}" for k in merge_keys
        )

        self.spark.sql(f"""
            MERGE INTO {fqn} t
            USING source_data s
            ON {key_condition}
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
        """)

    def expire_snapshots(
        self, database: str, table_name: str,
        older_than: str, retain_last: int = 5,
    ) -> None:
        fqn = f"{database}.{table_name}"
        self.spark.sql(
            f"CALL {self.catalog}.system.expire_snapshots("
            f"table => '{fqn}', "
            f"older_than => {older_than}, "
            f"retain_last => {retain_last})"
        )

    def rewrite_data_files(
        self, database: str, table_name: str,
        target_file_size_mb: int = 512,
    ) -> None:
        fqn = f"{database}.{table_name}"
        size_bytes = target_file_size_mb * 1024 * 1024
        self.spark.sql(
            f"CALL {self.catalog}.system.rewrite_data_files("
            f"table => '{fqn}', "
            f"options => map("
            f"'target-file-size-bytes', '{size_bytes}'))"
        )


def demo():
    spark = create_iceberg_session()
    mgr = IcebergTableManager(spark)

    mgr.create_table(
        database="analytics", table_name="events",
        schema_ddl="""
            event_id STRING NOT NULL,
            user_id STRING NOT NULL,
            event_type STRING NOT NULL,
            event_timestamp TIMESTAMP NOT NULL,
            amount DECIMAL(18, 2),
            properties STRING,
            country STRING
        """,
        partition_spec="days(event_timestamp), bucket(16, user_id)",
        sort_order="event_timestamp, user_id",
    )

    # Schema evolution without rewriting data
    mgr.evolve_schema("analytics", "events", [
        {"type": "add", "name": "device_type", "data_type": "STRING"},
        {"type": "add", "name": "session_id", "data_type": "STRING",
         "after": "user_id"},
    ])
```

**Iceberg vs Delta Lake comparison:**

| Feature | Iceberg | Delta Lake |
|---|---|---|
| Hidden partitioning | Yes (transform-based) | No (column-based) |
| Partition evolution | Without rewrite | Requires rewrite |
| Schema evolution | Full (add, drop, rename, widen) | Add/overwrite only |
| Time travel | Snapshot ID or timestamp | Version or timestamp |
| Multi-engine | Spark, Flink, Trino, Presto | Primarily Spark |
| Catalog | Hive, Glue, REST, Nessie | Unity Catalog, Hive |
| Sort order | Table-level sort spec | Z-ORDER (optimize) |

**Key patterns:**
- Hidden partitioning transforms (days, months, bucket) decouple physical layout from queries
- Partition evolution changes layout for new data without rewriting existing files
- Schema evolution (add, drop, rename, widen) is metadata-only, no data rewrite
- Snapshot isolation provides consistent reads during concurrent writes
- Incremental reads between snapshots enable efficient CDC-style ETL
- `rewrite_data_files` compacts small files with configurable target size
- `expire_snapshots` with `retain_last` prevents storage bloat while preserving rollback'''
    ),
    (
        "data-engineering/lakehouse-acid-mechanics",
        "Explain how Delta Lake and Iceberg achieve ACID transactions on object storage (S3/GCS). Show the transaction log mechanics, conflict resolution, and how concurrent writes are handled.",
        '''ACID transactions on object storage: transaction logs, conflict resolution, and concurrency:

```python
"""
How lakehouse formats achieve ACID on object storage:
transaction log mechanics, optimistic concurrency control,
and conflict resolution strategies.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ActionType(str, Enum):
    """Delta Lake transaction log action types."""
    COMMIT_INFO = "commitInfo"
    ADD = "add"
    REMOVE = "remove"
    METADATA = "metaData"
    PROTOCOL = "protocol"
    TXN = "txn"


@dataclass
class AddAction:
    """Records a new file added to the table."""
    path: str
    partition_values: dict[str, str]
    size: int
    modification_time: int
    data_change: bool = True
    stats: Optional[str] = None  # JSON: min/max/nullCount per column


@dataclass
class RemoveAction:
    """Records a file removed from the table."""
    path: str
    deletion_timestamp: int
    data_change: bool = True
    partition_values: dict[str, str] = field(default_factory=dict)


class TransactionLog:
    """
    Simplified Delta Lake transaction log model.

    The log is the source of truth:
    _delta_log/
      00000000000000000000.json  <- initial commit
      00000000000000000001.json  <- append data
      00000000000000000002.json  <- update (remove+add)
      00000000000000000010.checkpoint.parquet <- snapshot
      _last_checkpoint           <- pointer to latest checkpoint

    State reconstruction:
    1. Find latest checkpoint
    2. Replay log entries after checkpoint
    3. Active files = all Add actions not cancelled by Remove
    """

    def __init__(self, table_path: str):
        self.table_path = table_path
        self.log_path = f"{table_path}/_delta_log"
        self.current_version = -1
        self.active_files: dict[str, AddAction] = {}

    def replay(self, up_to_version: Optional[int] = None) -> None:
        """Reconstruct table state by replaying log entries."""
        version = 0
        while True:
            log_file = f"{self.log_path}/{version:020d}.json"
            try:
                actions = self._read_log_file(log_file)
            except FileNotFoundError:
                break

            for action in actions:
                if "add" in action:
                    a = action["add"]
                    self.active_files[a["path"]] = AddAction(
                        path=a["path"],
                        partition_values=a.get("partitionValues", {}),
                        size=a["size"],
                        modification_time=a["modificationTime"],
                        stats=a.get("stats"),
                    )
                elif "remove" in action:
                    self.active_files.pop(
                        action["remove"]["path"], None
                    )

            self.current_version = version
            if up_to_version and version >= up_to_version:
                break
            version += 1

    def _read_log_file(self, path: str) -> list[dict]:
        with open(path) as f:
            return [json.loads(line) for line in f]


# --- Optimistic Concurrency Control ---

class ConflictType(str, Enum):
    NONE = "none"
    APPEND_APPEND = "append_append"
    DELETE_DELETE = "delete_delete"
    UPDATE_UPDATE = "update_update"
    DELETE_UPDATE = "delete_update"


@dataclass
class TransactionAttempt:
    """A pending transaction attempting to commit."""
    transaction_id: str
    read_version: int
    adds: list[AddAction] = field(default_factory=list)
    removes: list[RemoveAction] = field(default_factory=list)
    operation: str = "WRITE"
    is_blind_append: bool = False


class OptimisticConcurrencyController:
    """
    Optimistic concurrency control for lakehouse writes.

    Protocol:
    1. Transaction reads table at version V
    2. Transaction computes changes locally
    3. Transaction attempts to write version V+1
    4. If V+1 already exists (conflict):
       a. Read intervening commits V+1..V+N
       b. Check for logical conflicts
       c. If no conflict: retry at V+N+1
       d. If conflict: abort and retry from scratch

    Conflict rules:
    - Blind appends never conflict with anything
    - Reads conflict with deletes of read files
    - Writes conflict with writes to same partitions
    """

    def __init__(self, max_retries: int = 10):
        self.max_retries = max_retries

    def check_conflicts(
        self, attempt: TransactionAttempt,
        winning_commits: list[dict[str, Any]],
    ) -> tuple[ConflictType, Optional[str]]:
        """Check if transaction conflicts with intervening commits."""
        if attempt.is_blind_append and not attempt.removes:
            return ConflictType.NONE, None

        winning_adds: set[str] = set()
        winning_removes: set[str] = set()

        for commit in winning_commits:
            for action in commit.get("actions", []):
                if "add" in action:
                    winning_adds.add(action["add"]["path"])
                elif "remove" in action:
                    winning_removes.add(action["remove"]["path"])

        # Check for file-level conflicts
        for remove in attempt.removes:
            if remove.path in winning_removes:
                return (
                    ConflictType.DELETE_DELETE,
                    f"File {remove.path} already removed",
                )
            if remove.path in winning_adds:
                return (
                    ConflictType.DELETE_UPDATE,
                    f"File {remove.path} was modified",
                )

        # Check partition-level conflicts for updates
        attempt_partitions = set()
        for add in attempt.adds:
            partition_key = json.dumps(
                add.partition_values, sort_keys=True
            )
            attempt_partitions.add(partition_key)

        for commit in winning_commits:
            for action in commit.get("actions", []):
                if "add" in action and action["add"].get("dataChange"):
                    win_part = json.dumps(
                        action["add"].get("partitionValues", {}),
                        sort_keys=True,
                    )
                    if (win_part in attempt_partitions
                            and attempt.operation != "WRITE"):
                        return (
                            ConflictType.UPDATE_UPDATE,
                            f"Partition {win_part} modified",
                        )

        return ConflictType.NONE, None

    def commit_with_retry(
        self, attempt: TransactionAttempt, log: TransactionLog,
    ) -> bool:
        """Commit with optimistic concurrency, retrying on conflict."""
        for retry in range(self.max_retries):
            if attempt.read_version < log.current_version:
                winning = self._get_commits_since(
                    log, attempt.read_version
                )
                conflict_type, msg = self.check_conflicts(
                    attempt, winning
                )
                if conflict_type != ConflictType.NONE:
                    if conflict_type in (
                        ConflictType.DELETE_DELETE,
                        ConflictType.DELETE_UPDATE,
                    ):
                        raise ConflictError(
                            f"Unresolvable conflict: {msg}"
                        )
                    attempt.read_version = log.current_version
                    continue

            # Attempt atomic write of new log entry
            try:
                self._atomic_write(
                    log, log.current_version + 1, attempt
                )
                return True
            except FileExistsError:
                log.replay()
                attempt.read_version = log.current_version
                continue

        raise ConflictError(
            f"Failed to commit after {self.max_retries} retries"
        )

    def _atomic_write(
        self, log: TransactionLog, version: int,
        attempt: TransactionAttempt,
    ) -> None:
        """Atomically write log entry (PUT-if-absent on S3)."""
        pass  # S3 conditional write or HDFS atomic rename

    def _get_commits_since(
        self, log: TransactionLog, version: int
    ) -> list[dict]:
        return []


class ConflictError(Exception):
    pass


# --- File statistics for data skipping ---

@dataclass
class ColumnStats:
    """Per-column statistics for data skipping."""
    num_records: int
    null_count: dict[str, int]
    min_values: dict[str, Any]
    max_values: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({
            "numRecords": self.num_records,
            "nullCount": self.null_count,
            "minValues": self.min_values,
            "maxValues": self.max_values,
        })

    @staticmethod
    def can_skip(
        stats: "ColumnStats", column: str,
        pred_min: Any, pred_max: Any,
    ) -> bool:
        """Check if a file can be skipped based on stats."""
        if column not in stats.min_values:
            return False
        file_min = stats.min_values[column]
        file_max = stats.max_values[column]
        if pred_min is not None and file_max < pred_min:
            return True
        if pred_max is not None and file_min > pred_max:
            return True
        return False
```

**Transaction log atomicity by storage system:**

| Storage | Atomicity Mechanism | Consistency |
|---|---|---|
| S3 | PUT-if-absent (conditional write) | Eventually consistent listings |
| GCS | Generation-based conditional write | Strong consistency |
| HDFS | Atomic rename | Strong consistency |
| Azure ADLS | Conditional ETag-based write | Strong consistency |

**Optimistic concurrency conflict matrix:**

| Writer A / Writer B | Blind Append | Update | Delete |
|---|---|---|---|
| Blind Append | No conflict | No conflict | No conflict |
| Update | No conflict | Conflict (same partition) | Conflict |
| Delete | No conflict | Conflict | Conflict |

**Key patterns:**
- Transaction log is append-only sequence of JSON files with version numbers
- State = replay all Add/Remove actions (or from checkpoint + subsequent logs)
- Blind appends never conflict, enabling high write concurrency
- Optimistic concurrency: read at version V, write at V+1, retry on conflict
- Per-file column statistics (min/max/nullCount) enable data skipping at query time
- Periodic checkpoints (every 10 commits in Delta) prevent slow log replay
- S3 conditional writes ensure exactly one writer wins per version number'''
    ),
    (
        "data-engineering/lakehouse-partition-pruning",
        "Show advanced partition pruning and data skipping techniques in Delta Lake and Iceberg including Z-ordering, bloom filters, partition evolution, and query optimization strategies.",
        '''Advanced partition pruning: Z-ordering, bloom filters, and query optimization:

```python
"""
Partition pruning and data skipping: Z-ordering, bloom filters,
file statistics, and partition evolution for query performance.
"""

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, year, month, expr, lit, when, count, sum as spark_sum,
)
from delta import DeltaTable
from typing import Optional


class QueryOptimizer:
    """Data skipping and partition pruning strategies."""

    def __init__(self, spark: SparkSession):
        self.spark = spark

    def create_optimized_table(
        self, path: str, partition_strategy: str = "daily",
    ) -> None:
        """
        Create tables with optimal partitioning.

        Rules of thumb:
        - Each partition should have ~1GB of data
        - Avoid >10,000 partitions (small file problem)
        - Partition by query filter columns

        Data volume per day:
          < 1 GB  -> partition by month
          1-10 GB -> partition by day
          > 10 GB -> partition by day + bucket(id)
        """
        if partition_strategy == "daily":
            self.spark.sql(f"""
                CREATE TABLE IF NOT EXISTS delta.`{path}` (
                    event_id STRING,
                    user_id STRING,
                    event_type STRING,
                    event_date DATE GENERATED ALWAYS AS (
                        CAST(event_timestamp AS DATE)
                    ),
                    event_timestamp TIMESTAMP,
                    amount DECIMAL(18, 2),
                    country STRING
                )
                USING delta
                PARTITIONED BY (event_date)
                TBLPROPERTIES (
                    'delta.autoOptimize.optimizeWrite' = 'true',
                    'delta.autoOptimize.autoCompact' = 'true'
                )
            """)

    def z_order_optimize(
        self, table_path: str, z_order_columns: list[str],
        partition_filter: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Z-ordering: interleave column bits to colocate related
        data for multi-dimensional query acceleration.

        Before Z-ordering:
          File 1: user_id=[A-Z], country=[*]
          File 2: user_id=[A-Z], country=[*]
          Query: user_id='X' AND country='US'
          -> Must scan ALL files

        After Z-ordering on (user_id, country):
          File 1: user_id=[A-F], country=[A-M]
          File 2: user_id=[A-F], country=[N-Z]
          File 3: user_id=[G-P], country=[A-M]
          Query: user_id='X' AND country='US'
          -> Scans only relevant files (data skipping)
        """
        dt = DeltaTable.forPath(self.spark, table_path)

        if partition_filter:
            result = (
                dt.optimize().where(partition_filter)
                .executeZOrderBy(*z_order_columns)
            )
        else:
            result = dt.optimize().executeZOrderBy(
                *z_order_columns
            )

        metrics = result.select(
            "metrics.numFilesAdded",
            "metrics.numFilesRemoved",
            "metrics.numBytesAdded",
            "metrics.numBytesRemoved",
        ).first()

        return {
            "files_added": metrics[0],
            "files_removed": metrics[1],
            "bytes_added": metrics[2],
            "bytes_removed": metrics[3],
        }

    def configure_bloom_filters(
        self, table_path: str, columns: list[str],
        fpp: float = 0.01, num_items: int = 1_000_000,
    ) -> None:
        """
        Configure bloom filter indexes for point lookups.

        Bloom filters quickly determine if a value is NOT in a file.
        FPP (False Positive Probability) = 0.01 means 1% chance
        of incorrectly reading a non-matching file.

        Best for: high-cardinality columns with equality predicates.
        Not for: range queries, low-cardinality columns.
        """
        for column in columns:
            self.spark.sql(f"""
                ALTER TABLE delta.`{table_path}`
                SET TBLPROPERTIES (
                    'delta.bloomFilter.columns.{column}.fpp' = '{fpp}',
                    'delta.bloomFilter.columns.{column}.numItems' = '{num_items}',
                    'delta.bloomFilter.columns.{column}.enabled' = 'true'
                )
            """)

    def analyze_data_skipping(
        self, table_path: str, query_filter: str,
    ) -> dict[str, any]:
        """
        Analyze how effectively data skipping works for a query.
        Compares files scanned vs total files.
        """
        dt = DeltaTable.forPath(self.spark, table_path)
        total_files = dt.toDF().inputFiles()

        filtered_df = (
            self.spark.read.format("delta").load(table_path)
            .filter(query_filter)
        )

        filtered_df.cache()
        scanned_files = filtered_df.inputFiles()
        row_count = filtered_df.count()
        filtered_df.unpersist()

        total_count = len(total_files)
        scanned_count = len(scanned_files)
        skip_rate = (
            (1 - scanned_count / total_count) * 100
            if total_count > 0 else 0
        )

        return {
            "total_files": total_count,
            "files_scanned": scanned_count,
            "files_skipped": total_count - scanned_count,
            "skip_rate_pct": round(skip_rate, 1),
            "rows_returned": row_count,
            "query_filter": query_filter,
        }

    def iceberg_partition_evolution(
        self, table_name: str
    ) -> None:
        """
        Iceberg partition evolution: change partitioning
        without rewriting existing data.

        v1: PARTITIONED BY (days(timestamp))
            -> Daily partitions

        v2: REPLACE PARTITION FIELD days(timestamp) WITH hours(timestamp)
            -> New data uses hourly, old data stays daily
            -> Queries spanning both work transparently
        """
        # Start with daily partitions
        self.spark.sql(f"""
            ALTER TABLE {table_name}
            ADD PARTITION FIELD days(event_timestamp)
        """)

        # Later, switch to hourly for higher volume
        self.spark.sql(f"""
            ALTER TABLE {table_name}
            REPLACE PARTITION FIELD days(event_timestamp)
            WITH hours(event_timestamp)
        """)

        # Add bucket partition for user_id lookups
        self.spark.sql(f"""
            ALTER TABLE {table_name}
            ADD PARTITION FIELD bucket(16, user_id)
        """)

    def compute_statistics(
        self, table_path: str, columns: list[str]
    ) -> None:
        """Configure column statistics collection scope."""
        self.spark.sql(f"""
            ALTER TABLE delta.`{table_path}`
            SET TBLPROPERTIES (
                'delta.dataSkippingNumIndexedCols' = '{len(columns)}'
            )
        """)
```

**Data skipping mechanisms comparison:**

| Mechanism | Best For | How It Works |
|---|---|---|
| Partition pruning | Time ranges, categories | Eliminates entire directories |
| Column stats (min/max) | Range filters on sorted data | Skips files outside filter range |
| Z-ordering | Multi-column filters | Colocates related data in files |
| Bloom filters | Equality on high-cardinality | Probabilistic set membership test |
| Generated columns | Derived partition keys | Auto-compute partition from data |

**Query optimization decision tree:**

| Step | Question | Action |
|---|---|---|
| 1 | Filtering on time? | Use time-based partitioning |
| 2 | Multiple filter columns? | Apply Z-ordering on those columns |
| 3 | Point lookups (= predicates)? | Enable bloom filters |
| 4 | Files too small (<128MB)? | Run OPTIMIZE/compaction |
| 5 | Skip rate < 80%? | Re-evaluate Z-order or partitioning |

**Key patterns:**
- Partition by time at granularity where each partition holds about 1GB
- Z-ORDER on columns frequently used together in WHERE clauses
- Enable bloom filters for high-cardinality columns used in equality predicates
- Use `delta.dataSkippingNumIndexedCols` to index more columns for data skipping
- Analyze skip rate with `inputFiles()` comparison to verify optimization effectiveness
- Iceberg partition evolution changes layout without rewriting existing data
- Run OPTIMIZE on recent partitions (not full table) to manage compaction cost'''
    ),
    (
        "data-engineering/lakehouse-merge-patterns",
        "Show production MERGE (upsert) patterns for data lakehouses including SCD Type 1/2, deduplication merge, conditional updates, and performance optimization.",
        '''Production MERGE patterns: SCD Type 1/2, deduplication, conditional updates:

```python
"""
Production MERGE (upsert) patterns for Delta Lake:
SCD Type 1 & 2, deduplication, conditional updates,
and performance optimization techniques.
"""

from delta import DeltaTable
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, current_timestamp, lit, when, row_number,
    max as spark_max, coalesce, sha2, concat_ws,
)
from pyspark.sql.window import Window
from typing import Optional


class MergePatterns:
    """Production-ready MERGE patterns for data lakehouse."""

    def __init__(self, spark: SparkSession):
        self.spark = spark

    def scd_type1_merge(
        self, target_path: str, source_df: DataFrame,
        key_columns: list[str], update_columns: list[str],
    ) -> None:
        """
        SCD Type 1: Overwrite with the latest values.
        No history preserved; previous values are lost.

        Use when: attributes don't need history
        (e.g., email corrections, address updates).
        """
        target = DeltaTable.forPath(self.spark, target_path)

        merge_condition = " AND ".join(
            f"target.{k} = source.{k}" for k in key_columns
        )

        change_condition = " OR ".join(
            f"target.{c} != source.{c} OR "
            f"(target.{c} IS NULL AND source.{c} IS NOT NULL) OR "
            f"(target.{c} IS NOT NULL AND source.{c} IS NULL)"
            for c in update_columns
        )

        update_set = {c: f"source.{c}" for c in update_columns}
        update_set["_updated_at"] = "current_timestamp()"

        (
            target.alias("target")
            .merge(source_df.alias("source"), merge_condition)
            .whenMatchedUpdate(
                condition=change_condition, set=update_set
            )
            .whenNotMatchedInsertAll()
            .execute()
        )

    def scd_type2_merge(
        self, target_path: str, source_df: DataFrame,
        key_columns: list[str], tracked_columns: list[str],
        effective_date_col: str = "effective_date",
    ) -> None:
        """
        SCD Type 2: Full change history.
        Close existing records, insert new versions.

        Target table requires:
        - is_current: BOOLEAN
        - valid_from: TIMESTAMP
        - valid_to: TIMESTAMP (NULL or '9999-12-31' for current)
        """
        target = DeltaTable.forPath(self.spark, target_path)

        source_prepared = (
            source_df
            .withColumn("is_current", lit(True))
            .withColumn("valid_from", col(effective_date_col))
            .withColumn("valid_to",
                        lit("9999-12-31").cast("timestamp"))
        )

        merge_condition = " AND ".join(
            f"target.{k} = source.{k}" for k in key_columns
        )
        change_condition = " OR ".join(
            f"target.{c} != source.{c}" for c in tracked_columns
        )

        # Step 1: Close existing current records that changed
        (
            target.alias("target")
            .merge(
                source_prepared.alias("source"),
                f"{merge_condition} AND target.is_current = true",
            )
            .whenMatchedUpdate(
                condition=change_condition,
                set={
                    "is_current": "false",
                    "valid_to": f"source.{effective_date_col}",
                    "_updated_at": "current_timestamp()",
                },
            )
            .execute()
        )

        # Step 2: Insert new versions
        current_keys = (
            self.spark.read.format("delta").load(target_path)
            .filter("is_current = true")
            .select(*key_columns)
        )
        new_records = source_prepared.join(
            current_keys, key_columns, "left_anti"
        )
        new_records.write.format("delta").mode("append").save(
            target_path
        )

    def deduplicate_merge(
        self, target_path: str, source_df: DataFrame,
        dedup_columns: list[str],
        order_column: str = "_ingested_at",
    ) -> None:
        """
        Insert only records not already in target.
        Deduplicates within source batch first.

        Use when: at-least-once delivery sources need
        exactly-once semantics in the lakehouse.
        """
        # Deduplicate within source batch
        window = Window.partitionBy(
            *[col(c) for c in dedup_columns]
        ).orderBy(col(order_column).desc())

        deduped_source = (
            source_df
            .withColumn("_row_num", row_number().over(window))
            .filter("_row_num = 1")
            .drop("_row_num")
        )

        # Insert-only merge
        target = DeltaTable.forPath(self.spark, target_path)
        merge_condition = " AND ".join(
            f"target.{c} = source.{c}" for c in dedup_columns
        )

        (
            target.alias("target")
            .merge(deduped_source.alias("source"), merge_condition)
            .whenNotMatchedInsertAll()
            .execute()
        )

    def conditional_update_merge(
        self, target_path: str, source_df: DataFrame,
        key_columns: list[str],
        conditions: list[dict[str, str]],
    ) -> None:
        """
        MERGE with multiple conditional update/delete clauses.

        Example conditions:
        [
            {"when": "source.status = 'deleted'",
             "action": "delete"},
            {"when": "source.amount > target.amount",
             "action": "update",
             "columns": ["amount", "updated_reason"]},
        ]
        """
        target = DeltaTable.forPath(self.spark, target_path)
        merge_condition = " AND ".join(
            f"target.{k} = source.{k}" for k in key_columns
        )

        builder = (
            target.alias("target")
            .merge(source_df.alias("source"), merge_condition)
        )

        for cond in conditions:
            if cond["action"] == "delete":
                builder = builder.whenMatchedDelete(
                    condition=cond["when"]
                )
            elif cond["action"] == "update":
                columns = cond.get("columns", [])
                update_set = {c: f"source.{c}" for c in columns}
                update_set["_updated_at"] = "current_timestamp()"
                builder = builder.whenMatchedUpdate(
                    condition=cond["when"], set=update_set
                )

        builder = builder.whenNotMatchedInsertAll()
        builder.execute()

    def soft_delete_merge(
        self, target_path: str, delete_keys_df: DataFrame,
        key_columns: list[str],
        deletion_reason: str = "user_request",
    ) -> None:
        """
        Soft delete: mark records as deleted with metadata.
        Preserves audit trail for compliance (GDPR, HIPAA).
        """
        target = DeltaTable.forPath(self.spark, target_path)
        merge_condition = " AND ".join(
            f"target.{k} = source.{k}" for k in key_columns
        )

        (
            target.alias("target")
            .merge(delete_keys_df.alias("source"), merge_condition)
            .whenMatchedUpdate(
                condition="target.is_deleted = false",
                set={
                    "is_deleted": "true",
                    "deleted_at": "current_timestamp()",
                    "deletion_reason": f"'{deletion_reason}'",
                    "_updated_at": "current_timestamp()",
                },
            )
            .execute()
        )

    def optimized_merge(
        self, target_path: str, source_df: DataFrame,
        key_columns: list[str],
        partition_filter: Optional[str] = None,
        target_file_count: Optional[int] = None,
    ) -> None:
        """
        Performance-optimized MERGE with partition pruning
        and source data repartitioning.

        Techniques:
        1. Filter target to relevant partitions
        2. Repartition source to match target layout
        3. Broadcast small source for hash join
        4. Z-ordered target for efficient file pruning
        """
        target = DeltaTable.forPath(self.spark, target_path)

        if target_file_count:
            source_prepared = source_df.repartition(
                target_file_count,
                *[col(k) for k in key_columns],
            )
        else:
            source_prepared = source_df

        merge_condition = " AND ".join(
            f"target.{k} = source.{k}" for k in key_columns
        )

        if partition_filter:
            merge_condition = (
                f"({merge_condition}) AND {partition_filter}"
            )

        (
            target.alias("target")
            .merge(source_prepared.alias("source"), merge_condition)
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
```

**MERGE pattern selection guide:**

| Pattern | History | Use Case | Performance |
|---|---|---|---|
| SCD Type 1 | No | Correct/overwrite attributes | Fast (update in place) |
| SCD Type 2 | Full | Track attribute changes over time | Moderate (close + insert) |
| Dedup merge | N/A | Exactly-once from at-least-once sources | Fast (insert-only) |
| Conditional | Varies | Multi-rule business logic | Moderate |
| Soft delete | Audit | GDPR/compliance deletion | Fast (flag update) |

**MERGE performance optimization:**

| Technique | Improvement | When to Use |
|---|---|---|
| Partition pruning | 10-100x | Target has time-based partitions |
| Source repartitioning | 2-5x | Source layout mismatches target |
| Broadcast join | 5-20x | Source batch is small (<200MB) |
| Z-ordered target | 3-10x | Multiple merge key columns |
| Change detection | 2-3x | Skip rows where values unchanged |

**Key patterns:**
- Add change detection condition to skip updates where no values actually changed
- SCD Type 2 requires two-step MERGE: close old records then insert new versions
- Dedup merge uses window function to keep latest record per key in source batch
- Soft delete preserves audit trail; physical purge happens on separate schedule
- Repartition source by merge keys to colocate data with target partitions
- Include partition filter in merge condition to enable partition pruning
- Use Z-ordered target tables for efficient file pruning during MERGE scans'''
    ),
]
