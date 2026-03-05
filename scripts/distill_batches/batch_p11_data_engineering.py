"""
Batch P11 — Data Engineering
Covers: Apache Spark optimization, Apache Kafka deep dive, ETL pipeline design,
data lakehouse architecture (Delta Lake/Iceberg), stream processing patterns.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. Apache Spark Optimization ---
    (
        "data-engineering/spark-optimization-partitioning-shuffle",
        r"""Explain Apache Spark optimization strategies in depth including partitioning strategies for DataFrames, shuffle minimization techniques, broadcast join usage and thresholds, Catalyst optimizer internals, memory tuning for executors, and adaptive query execution features with practical PySpark code examples.""",
        r"""# Apache Spark Optimization: Partitioning, Shuffles, Broadcast Joins, and Adaptive Query Execution

## Why Spark Performance Tuning Matters

Apache Spark is the de facto standard for large-scale distributed data processing, but a **common mistake** is treating it as a black box and hoping the defaults work. In practice, the difference between a well-tuned and a poorly-tuned Spark job can be 10x in wall-clock time and 5x in cloud cost. Understanding how Spark distributes data across partitions, when it triggers expensive shuffles, and how the **Catalyst optimizer** rewrites your logical plan into a physical plan is therefore essential for any data engineer working at scale.

The core principle behind every Spark optimization is **minimize data movement**. Every byte that must be serialized, sent over the network, deserialized, and merged on a different executor is a byte that costs CPU, memory, and wall-clock time. Partitioning strategies, broadcast joins, and predicate pushdown all serve this single goal.

## Partitioning Strategies

### Hash Partitioning

The default partitioning strategy in Spark. When you call `repartition(n, col)`, Spark computes `hash(col) % n` to assign each row to a partition. This is the **best practice** when you need uniform distribution for subsequent joins or aggregations on the same key.

```python
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, LongType, DoubleType
from typing import Optional

def create_optimized_session(
    app_name: str,
    shuffle_partitions: int = 200,
    broadcast_threshold: int = 10 * 1024 * 1024,
    aqe_enabled: bool = True,
) -> SparkSession:
    # Build a SparkSession with tuned configuration
    builder = (
        SparkSession.builder
        .appName(app_name)
        .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
        .config("spark.sql.autoBroadcastJoinThreshold", str(broadcast_threshold))
        .config("spark.sql.adaptive.enabled", str(aqe_enabled).lower())
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.adaptive.skewJoin.enabled", "true")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
    )
    return builder.getOrCreate()

spark = create_optimized_session("etl-pipeline", shuffle_partitions=400)
```

### Range Partitioning

When your downstream operation needs sorted data (for example, writing to partitioned Parquet files), **range partitioning** ensures each partition contains a contiguous range of keys. This avoids a subsequent sort stage.

```python
def repartition_for_write(
    df,
    partition_col: str,
    num_partitions: int = 200,
) -> "DataFrame":
    # Range-partition so each output file covers a contiguous key range
    # This eliminates a post-shuffle sort when writing partitioned Parquet
    return df.repartitionByRange(num_partitions, F.col(partition_col))

# Example: partition orders by date range before writing
orders_df = spark.read.parquet("s3a://warehouse/raw/orders/")
partitioned = repartition_for_write(orders_df, "order_date", num_partitions=365)
partitioned.write.partitionBy("order_date").parquet("s3a://warehouse/curated/orders/")
```

### Custom Partitioning with Salt Keys

A **pitfall** in Spark is data skew: when a small number of keys dominate the data, a few partitions become much larger than others, causing stragglers. The classic solution is **salting**: append a random integer to the join key, perform the join on the salted key, then aggregate away the salt.

```python
import random
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from typing import Tuple

def salted_join(
    large_df: DataFrame,
    small_df: DataFrame,
    join_key: str,
    salt_buckets: int = 10,
) -> DataFrame:
    # Add salt to the large side
    large_salted = large_df.withColumn(
        "salt", (F.rand() * salt_buckets).cast("int")
    ).withColumn(
        "salted_key", F.concat(F.col(join_key), F.lit("_"), F.col("salt"))
    )

    # Explode the small side across all salt buckets
    salt_range = list(range(salt_buckets))
    small_exploded = small_df.withColumn(
        "salt", F.explode(F.array([F.lit(s) for s in salt_range]))
    ).withColumn(
        "salted_key", F.concat(F.col(join_key), F.lit("_"), F.col("salt"))
    )

    # Join on salted key -- distributes skewed keys across salt_buckets partitions
    joined = large_salted.join(
        small_exploded,
        on="salted_key",
        how="inner",
    )

    return joined.drop("salt", "salted_key")
```

## Shuffle Minimization

Shuffles are the most expensive operation in Spark because they require writing intermediate data to disk, serializing it, transferring it over the network, and deserializing it on the receiving executor. **Best practice** is to minimize shuffles by:

1. **Co-partitioning**: If two DataFrames are already partitioned on the same key with the same number of partitions, a join between them requires no shuffle.
2. **Predicate pushdown**: Filter early so fewer rows enter the shuffle stage.
3. **Column pruning**: Select only the columns you need before a join or aggregation.
4. **Combining narrow transformations**: `map`, `filter`, and `select` are pipelined within a single stage and never trigger shuffles.

However, some operations inherently require shuffles: `groupByKey`, `reduceByKey`, `join` (when not co-partitioned), `repartition`, and `distinct`. The **trade-off** is between correctness (you need the shuffle to get the right answer) and performance (you want to minimize or defer it).

## Broadcast Joins

When one side of a join is small enough to fit in executor memory, Spark can **broadcast** it to every executor, eliminating the shuffle on the large side entirely. The threshold is controlled by `spark.sql.autoBroadcastJoinThreshold` (default 10 MB).

A **common mistake** is leaving the threshold at the default when you have executors with 8+ GB of memory. Raising it to 100 MB or even 500 MB can eliminate shuffles on many dimension-table joins. However, broadcasting a table that is too large will cause OOM errors on every executor, therefore you must balance the threshold against available executor memory.

## Catalyst Optimizer Internals

The **Catalyst optimizer** is Spark SQL's query optimizer. It operates in four phases:

1. **Analysis**: Resolves column names and types against the catalog.
2. **Logical Optimization**: Applies rule-based rewrites such as predicate pushdown, constant folding, column pruning, and filter/join reordering.
3. **Physical Planning**: Generates candidate physical plans (e.g., sort-merge join vs. broadcast hash join) and selects the cheapest based on cost estimates.
4. **Code Generation (Whole-Stage CodeGen)**: Fuses multiple operators into a single JVM function using Janino compilation, eliminating virtual-method-call overhead.

Because Catalyst operates on the logical plan, writing your transformations as DataFrame/SQL operations (not RDD lambdas) is a **best practice** -- it gives Catalyst the most information to optimize.

## Adaptive Query Execution (AQE)

Spark 3.0 introduced **Adaptive Query Execution**, which re-optimizes the query plan at runtime based on actual shuffle statistics. AQE provides three major features:

1. **Coalescing post-shuffle partitions**: If a shuffle produces many small partitions, AQE merges them to reduce task overhead.
2. **Converting sort-merge joins to broadcast joins**: If a shuffle stage reveals that one side is much smaller than estimated, AQE switches to a broadcast join mid-execution.
3. **Skew join optimization**: If AQE detects that certain partitions are much larger than others, it splits the skewed partition and replicates the corresponding partition from the other side.

```python
def demonstrate_aqe_config(spark: SparkSession) -> None:
    # Enable AQE with all sub-features
    spark.conf.set("spark.sql.adaptive.enabled", "true")
    spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
    spark.conf.set("spark.sql.adaptive.coalescePartitions.minPartitionSize", "1m")
    spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")
    spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionFactor", "5")
    spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes", "256m")
    spark.conf.set("spark.sql.adaptive.localShuffleReader.enabled", "true")

    # Verify plan uses AQE
    df = spark.sql(
        "SELECT customer_id, SUM(amount) AS total "
        "FROM transactions GROUP BY customer_id"
    )
    # The explain output will show AdaptiveSparkPlan when AQE is active
    df.explain(mode="formatted")
```

## Memory Tuning

Spark executor memory is divided into three regions:

- **Execution memory** (default 60% of usable heap): Used for shuffles, joins, sorts, and aggregations.
- **Storage memory** (default 40% of usable heap): Used for cached DataFrames and broadcast variables.
- **User memory**: The remainder, used for user data structures and UDF overhead.

Since Spark 1.6, execution and storage memory share a **unified pool** -- execution can borrow from storage and vice versa, however execution always has eviction priority. Therefore, caching too aggressively can starve execution memory and cause spills to disk, which is a **pitfall** that degrades performance significantly.

## Summary and Key Takeaways

- **Partitioning is the foundation** of Spark performance: hash partitioning for uniform joins, range partitioning for sorted writes, and salting for skew mitigation
- **Shuffle minimization** is the single most impactful optimization: co-partition DataFrames, push down predicates early, prune columns, and use broadcast joins for small tables
- **Catalyst optimizer** requires DataFrame/SQL APIs to work effectively; RDD lambdas bypass optimization because Spark cannot inspect opaque closures
- **Adaptive Query Execution** in Spark 3.x is a game-changer that dynamically adjusts partition counts, join strategies, and skew handling at runtime based on actual data statistics
- **Memory tuning** must balance execution and storage needs; over-caching is a common mistake that causes shuffle spills and GC pressure
- Always use `explain(mode="formatted")` to verify your physical plan matches expectations before running at scale
"""
    ),

    # --- 2. Apache Kafka Deep Dive ---
    (
        "data-engineering/kafka-consumer-groups-exactly-once-schema-registry",
        r"""Provide a comprehensive deep dive into Apache Kafka covering consumer group mechanics and rebalancing protocols, exactly-once semantics with idempotent producers and transactional APIs, partition strategies for ordering guarantees, log compaction for stateful topics, Schema Registry with Avro evolution, Kafka Connect for source and sink connectors, and Kafka Streams topology design with practical Python and Java code examples.""",
        r"""# Apache Kafka Deep Dive: Consumer Groups, Exactly-Once Semantics, Schema Registry, and Streams

## Why Kafka Dominates Event Streaming

Apache Kafka has become the backbone of modern event-driven architectures because it solves a fundamental distributed systems problem: **decoupling producers and consumers** while providing durability, ordering guarantees, and horizontal scalability. However, achieving production-grade reliability with Kafka requires understanding its internals deeply. A **common mistake** is treating Kafka as a simple message queue when it is actually a distributed commit log with nuanced semantics around partitioning, consumer coordination, and delivery guarantees.

The **trade-off** at the heart of Kafka's design is between throughput and ordering. Kafka provides ordering guarantees only within a single partition, therefore the choice of partition key directly impacts both data locality and processing semantics.

## Consumer Groups and Rebalancing

### Consumer Group Mechanics

A **consumer group** is a set of consumers that cooperatively consume from a set of topic partitions. Each partition is assigned to exactly one consumer within the group, which guarantees that messages within a partition are processed in order by a single consumer.

The **group coordinator** (a Kafka broker elected for each group) manages partition assignment. When a consumer joins or leaves the group, the coordinator triggers a **rebalance** -- a protocol that redistributes partitions among the remaining consumers.

```python
from confluent_kafka import Consumer, KafkaError, KafkaException
from typing import Callable, Optional, Dict, List
import json
import logging

logger = logging.getLogger(__name__)

class ReliableConsumer:
    # Wraps confluent_kafka.Consumer with explicit offset management
    # and graceful rebalance handling

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: List[str],
        auto_commit: bool = False,
    ) -> None:
        self.config: Dict[str, object] = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "enable.auto.commit": str(auto_commit).lower(),
            "auto.offset.reset": "earliest",
            "session.timeout.ms": 30000,
            "heartbeat.interval.ms": 10000,
            "max.poll.interval.ms": 300000,
            "partition.assignment.strategy": "cooperative-sticky",
        }
        self.consumer = Consumer(self.config)
        self.consumer.subscribe(topics, on_assign=self._on_assign, on_revoke=self._on_revoke)
        self._running = True

    def _on_assign(self, consumer, partitions) -> None:
        # Called when partitions are assigned after a rebalance
        logger.info(f"Partitions assigned: {[p.partition for p in partitions]}")

    def _on_revoke(self, consumer, partitions) -> None:
        # Commit offsets for revoked partitions before they move to another consumer
        # This prevents duplicate processing during rebalance
        logger.info(f"Partitions revoked: {[p.partition for p in partitions]}")
        consumer.commit(offsets=partitions, asynchronous=False)

    def consume_loop(
        self,
        handler: Callable[[str, bytes], None],
        batch_size: int = 100,
    ) -> None:
        try:
            while self._running:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(msg.error())

                handler(msg.key(), msg.value())
                # Manual commit after successful processing
                self.consumer.commit(message=msg, asynchronous=False)
        finally:
            self.consumer.close()

    def shutdown(self) -> None:
        self._running = False
```

### Cooperative Sticky Rebalancing

The legacy **eager rebalance** protocol revokes all partitions from all consumers and reassigns from scratch. This causes a full stop-the-world pause. The **cooperative-sticky** protocol (introduced in Kafka 2.4) only migrates the partitions that need to move, which is a **best practice** for production deployments because it minimizes processing downtime during scaling events.

## Exactly-Once Semantics

Achieving exactly-once delivery in Kafka requires three mechanisms working together:

1. **Idempotent producers**: Each producer is assigned a unique Producer ID, and each message gets a monotonically increasing sequence number. The broker deduplicates messages with the same (PID, sequence) pair.
2. **Transactional API**: Wraps a set of produces and consumer offset commits in an atomic transaction.
3. **Transactional consumers**: Read only committed messages by setting `isolation.level=read_committed`.

```python
from confluent_kafka import Producer, Consumer
from typing import Dict, Any

def create_transactional_producer(
    bootstrap_servers: str,
    transactional_id: str,
) -> Producer:
    # Create a producer configured for exactly-once semantics
    config: Dict[str, Any] = {
        "bootstrap.servers": bootstrap_servers,
        "transactional.id": transactional_id,
        "enable.idempotence": True,
        "acks": "all",
        "retries": 2147483647,
        "max.in.flight.requests.per.connection": 5,
    }
    producer = Producer(config)
    producer.init_transactions()
    return producer

def transactional_consume_transform_produce(
    consumer: Consumer,
    producer: Producer,
    transform_fn,
    input_topic: str,
    output_topic: str,
) -> None:
    # Atomic read-process-write loop
    # Consumes from input, transforms, produces to output,
    # and commits consumer offsets -- all in one transaction
    while True:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue

        transformed = transform_fn(msg.value())

        producer.begin_transaction()
        try:
            producer.produce(output_topic, value=transformed, key=msg.key())
            producer.send_offsets_to_transaction(
                consumer.position(consumer.assignment()),
                consumer.consumer_group_metadata(),
            )
            producer.commit_transaction()
        except Exception:
            producer.abort_transaction()
            raise
```

The **trade-off** with transactions is throughput: transactional commits add latency (typically 50-100ms per commit). Therefore, batching multiple messages per transaction is essential for high-throughput pipelines.

## Partition Strategies and Ordering

Kafka guarantees ordering only within a single partition. Choosing the right partition key is critical:

- **Entity-based keys** (e.g., `user_id`, `order_id`): All events for an entity go to the same partition, preserving causal ordering.
- **Time-based keys**: Useful for time-series data, but can cause hot partitions if traffic is bursty.
- **Custom partitioners**: When the default `murmur2(key) % num_partitions` creates skew, implement a custom partitioner to distribute more evenly.

A **pitfall** is changing the number of partitions on a live topic: because the partition assignment formula changes, messages for the same key will land on different partitions, breaking ordering guarantees for in-flight consumers.

## Log Compaction

For topics that represent **current state** (e.g., user profiles, configuration), log compaction retains only the latest value for each key. The compaction thread runs periodically, scanning closed log segments and removing superseded records. This is fundamentally different from time-based retention: compacted topics can retain data indefinitely while keeping storage bounded because only the latest value per key survives.

Key configuration parameters:
- `cleanup.policy=compact`: Enables compaction. You can also use `compact,delete` for hybrid behavior.
- `min.cleanable.dirty.ratio`: The minimum ratio of dirty (uncompacted) to total log size before compaction triggers. Lower values trigger compaction more aggressively.
- `delete.retention.ms`: How long tombstone records (null values) are retained after compaction.
- `segment.ms` and `segment.bytes`: Control when log segments are closed and become eligible for compaction.

A **common mistake** with compacted topics is forgetting to produce tombstone records (messages with a null value) when entities are deleted. Without tombstones, compaction retains the last non-null value forever, creating ghost records that mislead downstream consumers.

## Kafka Connect

**Kafka Connect** is Kafka's integration framework for streaming data between Kafka and external systems. It provides a standardized API for **source connectors** (ingest data into Kafka) and **sink connectors** (export data from Kafka). Connect handles offset tracking, serialization, fault tolerance, and horizontal scaling automatically, which eliminates the need to write custom producer/consumer code for common integrations.

The **best practice** is to run Connect in **distributed mode** for production workloads, where connector tasks are distributed across a cluster of Connect workers. Single-mode (standalone) is suitable only for development and testing.

## Schema Registry and Avro Evolution

The **Schema Registry** provides a centralized store for Avro, Protobuf, or JSON schemas. Every message includes a schema ID in its header, allowing consumers to deserialize without prior schema knowledge.

Schema evolution rules:
- **Backward compatible**: New schema can read data written by old schema (adding optional fields).
- **Forward compatible**: Old schema can read data written by new schema (removing optional fields).
- **Full compatible**: Both backward and forward.

A **best practice** is setting compatibility mode to `BACKWARD` or `FULL` to prevent breaking changes from being registered.

## Kafka Streams Topology

```java
// Java Kafka Streams topology for real-time order enrichment
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;

public class OrderEnrichmentTopology {
    // Joins an order stream with a customer table for real-time enrichment
    public static void main(String[] args) {
        StreamsBuilder builder = new StreamsBuilder();

        KStream<String, Order> orders = builder.stream("orders");
        KTable<String, Customer> customers = builder.table(
            "customers",
            Materialized.as("customer-store")
        );

        KStream<String, EnrichedOrder> enriched = orders
            .selectKey((key, order) -> order.getCustomerId())
            .join(
                customers,
                (order, customer) -> new EnrichedOrder(order, customer)
            );

        enriched.to("enriched-orders", Produced.with(stringSerde, enrichedSerde));

        KafkaStreams streams = new KafkaStreams(builder.build(), config);
        streams.start();
    }
}
```

## Summary and Key Takeaways

- **Consumer groups** with cooperative-sticky rebalancing minimize processing downtime during scaling events; always disable auto-commit and manage offsets explicitly for at-least-once guarantees
- **Exactly-once semantics** require idempotent producers, transactional APIs, and read_committed consumers working together; the throughput trade-off is managed by batching messages per transaction
- **Partition key selection** determines ordering guarantees and data distribution; never change partition counts on a live topic without a migration plan
- **Log compaction** is essential for state topics where only the latest value per key matters; combine with tombstones for deletions
- **Schema Registry** with backward or full compatibility mode prevents breaking schema changes from reaching production consumers
- **Kafka Streams** provides a lightweight, embedded stream processing library that leverages Kafka's partitioning for parallel, fault-tolerant stateful processing
"""
    ),

    # --- 3. ETL Pipeline Design ---
    (
        "data-engineering/etl-pipeline-idempotent-data-quality-cdc",
        r"""Explain comprehensive ETL pipeline design including idempotent pipeline patterns for safe retries, data quality validation using Great Expectations with custom expectations and checkpoints, incremental load strategies with high watermarks, change data capture patterns with Debezium, and backfill strategies for historical data reprocessing with practical Python code examples and production best practices.""",
        r"""# ETL Pipeline Design: Idempotent Pipelines, Data Quality, Incremental Loads, CDC, and Backfills

## Why ETL Design Patterns Matter

Building an ETL pipeline that works once on clean data is straightforward. Building one that works reliably in production -- where sources fail, schemas drift, data arrives late, and business logic changes retroactively -- requires disciplined engineering patterns. The most important principle in production ETL is **idempotency**: the ability to run the same pipeline multiple times on the same input and produce the same output without side effects. Every other pattern (incremental loads, CDC, backfills) builds on this foundation.

A **common mistake** is designing ETL pipelines that append to target tables without deduplication. When the pipeline fails midway and is retried, you get duplicate records that silently corrupt downstream analytics. Therefore, idempotency is not optional -- it is the baseline requirement for any production data pipeline.

## Idempotent Pipeline Patterns

### Overwrite Partition Strategy

The simplest idempotent pattern: write output to a date-partitioned location and overwrite the entire partition on each run. If the pipeline runs twice for the same date, the second run replaces the first.

```python
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class IdempotentPipelineBase:
    # Base class enforcing idempotent write semantics
    # Subclasses implement extract() and transform()

    def __init__(
        self,
        target_path: str,
        partition_col: str = "processing_date",
    ) -> None:
        self.target_path = target_path
        self.partition_col = partition_col

    def write_partition(
        self,
        df,
        partition_value: str,
        mode: str = "overwrite",
    ) -> None:
        # Overwrite a single partition atomically
        # Because we overwrite the entire partition, reruns are safe
        partition_path = f"{self.target_path}/{self.partition_col}={partition_value}"
        (
            df.write
            .mode(mode)
            .parquet(partition_path)
        )
        logger.info(f"Wrote partition {partition_value} to {partition_path}")

    def run(self, execution_date: date) -> None:
        partition_value = execution_date.isoformat()
        raw_data = self.extract(execution_date)
        transformed = self.transform(raw_data)
        self.write_partition(transformed, partition_value)

    def extract(self, execution_date: date):
        raise NotImplementedError

    def transform(self, df):
        raise NotImplementedError
```

### MERGE / UPSERT Strategy

When overwriting entire partitions is too expensive (large tables, small updates), use a **MERGE** (also called UPSERT) pattern. This requires a unique key to match source and target rows.

```python
from delta.tables import DeltaTable
from pyspark.sql import SparkSession, DataFrame
from typing import List

def idempotent_merge(
    spark: SparkSession,
    source_df: DataFrame,
    target_path: str,
    merge_keys: List[str],
    update_columns: List[str],
) -> None:
    # Upsert source into target Delta table
    # Matching rows are updated; new rows are inserted
    # Running this twice with the same source produces identical results
    if DeltaTable.isDeltaTable(spark, target_path):
        target = DeltaTable.forPath(spark, target_path)
        merge_condition = " AND ".join(
            [f"target.{k} = source.{k}" for k in merge_keys]
        )
        update_set = {col: f"source.{col}" for col in update_columns}
        insert_values = {
            col: f"source.{col}"
            for col in merge_keys + update_columns
        }

        (
            target.alias("target")
            .merge(source_df.alias("source"), merge_condition)
            .whenMatchedUpdate(set=update_set)
            .whenNotMatchedInsert(values=insert_values)
            .execute()
        )
    else:
        # First run -- no target exists yet
        source_df.write.format("delta").save(target_path)
```

## Data Quality with Great Expectations

**Great Expectations** (GE) is the leading open-source framework for data quality validation. It provides a declarative way to define expectations about your data and generate validation reports.

### Setting Up Expectations

```python
import great_expectations as gx
from great_expectations.core import ExpectationSuite, ExpectationConfiguration
from great_expectations.checkpoint import Checkpoint
from typing import Dict, Any

def build_order_expectations() -> ExpectationSuite:
    # Define expectations for the orders table
    # Each expectation is a declarative assertion about data quality
    suite = ExpectationSuite(name="orders_suite")

    # Primary key must never be null
    suite.add_expectation(
        ExpectationConfiguration(
            expectation_type="expect_column_values_to_not_be_null",
            kwargs={"column": "order_id"},
        )
    )

    # Order amounts must be positive
    suite.add_expectation(
        ExpectationConfiguration(
            expectation_type="expect_column_values_to_be_between",
            kwargs={"column": "amount", "min_value": 0.01, "max_value": 1000000},
        )
    )

    # Status must be one of known values
    suite.add_expectation(
        ExpectationConfiguration(
            expectation_type="expect_column_values_to_be_in_set",
            kwargs={
                "column": "status",
                "value_set": ["pending", "confirmed", "shipped", "delivered", "cancelled"],
            },
        )
    )

    # Row count should be within expected range (catch empty loads or explosions)
    suite.add_expectation(
        ExpectationConfiguration(
            expectation_type="expect_table_row_count_to_be_between",
            kwargs={"min_value": 1000, "max_value": 10000000},
        )
    )

    return suite

def run_quality_checkpoint(
    context: gx.DataContext,
    datasource_name: str,
    asset_name: str,
    suite_name: str,
) -> Dict[str, Any]:
    # Run a validation checkpoint and return results
    # If validation fails, the pipeline should halt before writing to the target
    checkpoint = Checkpoint(
        name="etl_quality_gate",
        data_context=context,
        validations=[
            {
                "batch_request": {
                    "datasource_name": datasource_name,
                    "data_asset_name": asset_name,
                },
                "expectation_suite_name": suite_name,
            }
        ],
    )
    result = checkpoint.run()
    if not result.success:
        failing = [
            r for r in result.run_results.values()
            if not r["validation_result"].success
        ]
        logger.error(f"Data quality check failed: {len(failing)} validations failed")
        raise ValueError("Data quality gate failed -- aborting pipeline")
    return result.to_json_dict()
```

The **best practice** is to run quality checks between the transform and load stages. This creates a **quality gate** that prevents bad data from reaching your target tables. However, the **trade-off** is that overly strict expectations can block legitimate data; therefore, tune thresholds based on historical distributions rather than hard-coded values.

## Incremental Load with High Watermark

Instead of reprocessing all historical data on each run, an incremental load tracks the **high watermark** -- the maximum timestamp or sequence number processed in the last run -- and only fetches new records.

```python
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

class HighWatermarkTracker:
    # Persists the last processed watermark to enable incremental loads
    # The watermark file is a simple JSON document stored alongside the pipeline

    def __init__(self, state_path: str) -> None:
        self.state_path = Path(state_path)

    def get_watermark(self) -> Optional[str]:
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            return state.get("high_watermark")
        return None

    def set_watermark(self, value: str) -> None:
        # Only update watermark after successful load
        state = {"high_watermark": value, "updated_at": datetime.utcnow().isoformat()}
        self.state_path.write_text(json.dumps(state, indent=2))

def incremental_extract(
    spark,
    source_table: str,
    watermark_col: str,
    tracker: HighWatermarkTracker,
):
    # Extract only records newer than the last watermark
    last_wm = tracker.get_watermark()
    if last_wm:
        query = (
            "SELECT * FROM {table} "
            "WHERE {col} > '{wm}' "
            "ORDER BY {col}"
        ).format(table=source_table, col=watermark_col, wm=last_wm)
    else:
        query = f"SELECT * FROM {source_table} ORDER BY {watermark_col}"

    df = spark.read.format("jdbc").option("query", query).load()
    return df
```

## Change Data Capture with Debezium

**CDC** captures row-level changes (INSERT, UPDATE, DELETE) from a source database's transaction log and streams them to Kafka. Debezium is the leading open-source CDC connector.

The key **trade-off** with CDC is complexity versus freshness. Batch ETL runs hourly or daily; CDC delivers changes in near-real-time (seconds). However, CDC introduces operational complexity: you must manage connector configuration, handle schema changes, monitor replication lag, and deal with snapshot bootstrapping for new tables.

A **pitfall** with CDC is ignoring **delete events**. Debezium emits a delete event followed by a tombstone (null value). Your consumer must handle both to maintain accurate state in the target system.

## Backfill Strategies

When business logic changes or a new derived table is introduced, you need to **backfill** historical data. The key requirements are:

1. **Idempotency**: The backfill must be safe to restart at any point.
2. **Bounded resource usage**: Processing years of data at once will overwhelm your cluster.
3. **Coexistence**: The backfill should not interfere with ongoing incremental loads.

```python
from datetime import date, timedelta
from typing import Callable, Optional

def chunked_backfill(
    pipeline_fn: Callable[[date], None],
    start_date: date,
    end_date: date,
    chunk_days: int = 7,
    on_chunk_complete: Optional[Callable[[date, date], None]] = None,
) -> None:
    # Run the pipeline for each date chunk in the range
    # Because the pipeline is idempotent, failed chunks can be retried safely
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
        logger.info(f"Backfilling chunk: {current} to {chunk_end}")

        for single_date in date_range(current, chunk_end):
            pipeline_fn(single_date)

        if on_chunk_complete:
            on_chunk_complete(current, chunk_end)

        current = chunk_end + timedelta(days=1)

def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
```

## Summary and Key Takeaways

- **Idempotency** is the non-negotiable foundation of production ETL: use partition-overwrite for full partitions and MERGE/UPSERT for incremental updates to ensure safe retries
- **Data quality gates** with Great Expectations should run between transform and load stages; tune thresholds from historical distributions rather than guessing, because overly strict checks block legitimate data
- **Incremental loads** with high watermark tracking reduce processing time from hours to minutes, however they require careful state management and must fall back to full loads when watermarks are corrupted
- **CDC with Debezium** provides near-real-time change streaming from source databases; the trade-off is operational complexity versus data freshness
- **Backfill strategies** must be chunked, idempotent, and isolated from ongoing incremental pipelines to prevent resource contention and data corruption
- Every pipeline should be designed to answer: "What happens if this runs twice?" and "What happens if this fails halfway through?"
"""
    ),

    # --- 4. Data Lakehouse Architecture ---
    (
        "data-engineering/lakehouse-delta-lake-iceberg-acid-time-travel",
        r"""Explain data lakehouse architecture in depth covering Delta Lake and Apache Iceberg table formats, how ACID transactions work on object storage like S3 or ADLS, time travel and snapshot isolation for auditing and rollback, schema evolution strategies with backward and forward compatibility, Z-ordering and data skipping for query performance, and compaction strategies for small file problems with production PySpark and SQL code examples.""",
        r"""# Data Lakehouse Architecture: Delta Lake, Iceberg, ACID Transactions, and Advanced Optimization

## Why the Lakehouse Pattern Emerged

The data lakehouse combines the best aspects of data warehouses (ACID transactions, schema enforcement, governance) with the best aspects of data lakes (open formats, low-cost object storage, decoupled compute). Before lakehouses, organizations maintained both a data lake (cheap, flexible, unreliable) and a data warehouse (expensive, rigid, reliable), with brittle ETL pipelines copying data between them. The lakehouse eliminates this **two-tier architecture** by adding a transactional metadata layer on top of open file formats stored in object storage.

The two dominant lakehouse table formats are **Delta Lake** (created by Databricks) and **Apache Iceberg** (created by Netflix). Both solve the same fundamental problem -- providing ACID guarantees on top of eventually-consistent object stores like S3 -- but with different architectural approaches. Understanding these differences is essential because the choice of table format impacts query performance, ecosystem compatibility, and operational complexity.

## ACID Transactions on Object Storage

### The Challenge

Object stores like S3 provide **eventual consistency** for list operations and no native support for atomic multi-file commits. A **common mistake** is assuming that writing multiple Parquet files to S3 is atomic -- it is not. If a writer crashes after writing 3 of 5 files, readers see a partial, corrupted dataset.

### Delta Lake's Approach

Delta Lake uses a **transaction log** (`_delta_log/`) stored alongside the data files. Each commit is a JSON file containing the list of files added and removed. The transaction log is the single source of truth; data files without a corresponding log entry are invisible to readers.

```python
from delta import configure_spark_with_delta_pip
from delta.tables import DeltaTable
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType
from typing import List, Optional

def create_lakehouse_session() -> SparkSession:
    # Configure Spark with Delta Lake extensions
    builder = (
        SparkSession.builder
        .appName("lakehouse-pipeline")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.databricks.delta.retentionDurationCheck.enabled", "false")
        .config("spark.sql.shuffle.partitions", "200")
    )
    return configure_spark_with_delta_pip(builder).getOrCreate()

def create_delta_table(
    spark: SparkSession,
    path: str,
    schema: StructType,
    partition_cols: Optional[List[str]] = None,
) -> DeltaTable:
    # Create a new Delta table with explicit schema
    # The transaction log is initialized atomically on first write
    writer = (
        spark.createDataFrame([], schema)
        .write
        .format("delta")
    )
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    writer.save(path)
    return DeltaTable.forPath(spark, path)
```

### Apache Iceberg's Approach

Iceberg uses a **tree of metadata files**: a metadata file points to a manifest list, which points to manifest files, which point to data files. Atomic commits are achieved by atomically swapping the metadata file pointer (using the catalog's atomic compare-and-swap operation).

The **trade-off** between Delta and Iceberg is ecosystem lock-in versus flexibility. Delta Lake has tighter integration with Spark and Databricks, however Iceberg's catalog-based design supports a wider range of query engines (Trino, Flink, Dremio, Snowflake) natively.

## Time Travel and Snapshot Isolation

Both Delta Lake and Iceberg maintain a history of table snapshots, enabling **time travel** -- querying the table as it existed at a specific point in time or version number.

```python
def demonstrate_time_travel(
    spark: SparkSession,
    table_path: str,
) -> None:
    # Query historical versions of a Delta table
    # Useful for auditing, debugging, and rollback

    # Read the current version
    current = spark.read.format("delta").load(table_path)
    current.show()

    # Read a specific version by number
    version_5 = (
        spark.read
        .format("delta")
        .option("versionAsOf", 5)
        .load(table_path)
    )

    # Read as of a specific timestamp
    historical = (
        spark.read
        .format("delta")
        .option("timestampAsOf", "2025-12-01T00:00:00Z")
        .load(table_path)
    )

    # Compare current vs historical for data drift detection
    drift = (
        current.select(
            F.count("*").alias("current_count"),
            F.mean("amount").alias("current_avg"),
        )
        .crossJoin(
            historical.select(
                F.count("*").alias("historical_count"),
                F.mean("amount").alias("historical_avg"),
            )
        )
    )
    drift.show()

def rollback_table(
    spark: SparkSession,
    table_path: str,
    target_version: int,
) -> None:
    # Restore a Delta table to a previous version
    # This creates a new commit that makes the table match the old version
    delta_table = DeltaTable.forPath(spark, table_path)
    delta_table.restoreToVersion(target_version)
```

Time travel is invaluable for **auditing** (what did the table look like when that report was generated?), **debugging** (what changed between yesterday and today?), and **rollback** (an ETL bug corrupted the table; restore to the last good version). However, the **trade-off** is storage cost: every snapshot retains references to old data files, so you must configure retention policies to vacuum old files periodically.

## Schema Evolution

### Adding Columns

Both Delta Lake and Iceberg support adding new columns without rewriting data. Existing files simply return `null` for the new column. This is **backward compatible** because readers with the new schema can read old files.

### Renaming and Reordering Columns

Iceberg excels here because it uses **column IDs** rather than column names for physical-to-logical mapping. Renaming a column in Iceberg is a metadata-only operation. Delta Lake requires `mergeSchema` and historically had weaker rename support (improved in recent versions).

```python
def evolve_schema_safely(
    spark: SparkSession,
    table_path: str,
    new_data: DataFrame,
) -> None:
    # Write with automatic schema evolution enabled
    # New columns in the source are added to the target schema
    # Best practice: always validate new columns before enabling auto-merge
    (
        new_data.write
        .format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .save(table_path)
    )

def validate_schema_compatibility(
    current_schema: StructType,
    incoming_schema: StructType,
) -> List[str]:
    # Check for breaking changes before allowing schema evolution
    issues: List[str] = []
    current_fields = {f.name: f.dataType for f in current_schema.fields}
    incoming_fields = {f.name: f.dataType for f in incoming_schema.fields}

    # Detect removed columns (breaking change)
    for name in current_fields:
        if name not in incoming_fields:
            issues.append(f"Column '{name}' removed -- this is a breaking change")

    # Detect type changes (breaking change)
    for name, dtype in incoming_fields.items():
        if name in current_fields and current_fields[name] != dtype:
            issues.append(
                f"Column '{name}' type changed from "
                f"{current_fields[name]} to {dtype}"
            )

    return issues
```

## Z-Ordering and Data Skipping

**Z-ordering** (also called multi-dimensional clustering) reorganizes data within partitions so that rows with similar values for the Z-order columns are stored in the same files. This enables **data skipping**: when a query filters on a Z-ordered column, the engine can skip entire files whose min/max statistics do not overlap with the filter predicate.

```sql
-- Z-order a Delta table by customer_id and order_date
-- This co-locates related rows for faster point lookups and range scans
OPTIMIZE delta.`s3://warehouse/orders/`
ZORDER BY (customer_id, order_date);

-- After Z-ordering, this query skips 95%+ of files:
SELECT * FROM delta.`s3://warehouse/orders/`
WHERE customer_id = 'C12345'
  AND order_date BETWEEN '2025-01-01' AND '2025-06-30';
```

The **best practice** is to Z-order on columns that appear most frequently in WHERE clauses. However, Z-ordering more than 3-4 columns provides diminishing returns because the space-filling curve becomes increasingly fragmented in high dimensions.

## Compaction: Solving the Small File Problem

Streaming ingestion and frequent batch writes create many small files, which degrade query performance because each file incurs metadata overhead and prevents efficient I/O coalescing. **Compaction** merges small files into larger ones.

```python
def compact_delta_table(
    spark: SparkSession,
    table_path: str,
    target_file_size_mb: int = 128,
    z_order_cols: Optional[List[str]] = None,
) -> None:
    # Run OPTIMIZE to compact small files
    # Combines with Z-ordering if columns are specified
    if z_order_cols:
        z_order_clause = ", ".join(z_order_cols)
        spark.sql(
            f"OPTIMIZE delta.`{table_path}` ZORDER BY ({z_order_clause})"
        )
    else:
        spark.sql(f"OPTIMIZE delta.`{table_path}`")

def vacuum_old_files(
    spark: SparkSession,
    table_path: str,
    retention_hours: int = 168,
) -> None:
    # Remove data files no longer referenced by any snapshot
    # Default retention is 7 days (168 hours) to allow for long-running queries
    delta_table = DeltaTable.forPath(spark, table_path)
    delta_table.vacuum(retention_hours)
```

## Summary and Key Takeaways

- The **lakehouse pattern** unifies data lake flexibility with warehouse reliability by adding a transactional metadata layer (Delta Lake or Iceberg) on top of open file formats in object storage
- **ACID transactions** on object storage are achieved through atomic metadata commits (transaction logs in Delta, catalog-level CAS in Iceberg), which is essential because object stores provide no native atomicity
- **Time travel** enables auditing, debugging, and rollback, however it requires careful retention management to control storage costs; vacuum old snapshots after the retention window expires
- **Schema evolution** should always be validated before auto-merge; Iceberg's column-ID approach provides stronger rename and reorder support than name-based mapping
- **Z-ordering** dramatically improves query performance by co-locating related rows, enabling data skipping that can eliminate 95%+ of file reads; limit Z-order columns to 3-4 for best results
- **Compaction** is mandatory for streaming-ingested tables; schedule OPTIMIZE regularly and vacuum old files to prevent unbounded storage growth and query performance degradation
"""
    ),

    # --- 5. Stream Processing Patterns ---
    (
        "data-engineering/stream-processing-windowing-watermarks-flink-state",
        r"""Explain stream processing patterns in depth including tumbling sliding and session window semantics with real-world use cases, watermark generation strategies and their impact on correctness versus latency, late data handling with allowed lateness and side outputs, exactly-once processing guarantees with Apache Flink checkpointing and barriers, and state management patterns including keyed state and operator state with practical Python and Java code examples.""",
        r"""# Stream Processing Patterns: Windowing, Watermarks, Late Data, Exactly-Once, and State Management

## Why Stream Processing Patterns Are Universal

Stream processing patterns -- windowing, watermarks, late data handling, and state management -- are **framework-agnostic concepts** that apply whether you use Apache Flink, Kafka Streams, Apache Beam, or a custom implementation. Understanding these patterns at the conceptual level is more valuable than memorizing any single framework's API, because the frameworks change and evolve but the fundamental patterns remain stable.

The core challenge in stream processing is that **time is ambiguous**. When an event says "this click happened at 14:32:05," your processing system might receive it at 14:32:07, 14:35:00, or even the next day (if the mobile device was offline). Windowing and watermarks exist to reconcile the gap between **when events happen** and **when they arrive**. A **common mistake** is ignoring this gap entirely, which produces analytics that are silently wrong whenever there is network latency, consumer lag, or producer buffering.

## Windowing Semantics

### Tumbling Windows

A tumbling window is a **fixed-size, non-overlapping** time interval. Every event belongs to exactly one window. Tumbling windows are the simplest and most common pattern, ideal for periodic aggregations.

**Real-world use case**: Compute the total revenue per merchant per hour. Each hour is a distinct, non-overlapping window, and every transaction falls into exactly one hourly bucket.

```python
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.datastream.functions import ProcessWindowFunction
from pyflink.common import Time, WatermarkStrategy, Duration
from pyflink.common.typeinfo import Types
from typing import Iterable, Tuple
from dataclasses import dataclass

@dataclass
class Transaction:
    merchant_id: str
    amount: float
    event_time: int  # epoch milliseconds

class HourlyRevenueAggregator(ProcessWindowFunction):
    # Aggregates transactions within each tumbling window
    # Emits (merchant_id, window_start, window_end, total_revenue)

    def process(
        self,
        key: str,
        context: ProcessWindowFunction.Context,
        elements: Iterable[Transaction],
    ) -> Iterable[Tuple[str, int, int, float]]:
        total = sum(txn.amount for txn in elements)
        window = context.window()
        yield (key, window.start, window.end, total)

def build_tumbling_window_pipeline(env: StreamExecutionEnvironment):
    # Configure a 1-hour tumbling window with 10-second watermark tolerance
    watermark_strategy = (
        WatermarkStrategy
        .for_bounded_out_of_orderness(Duration.of_seconds(10))
        .with_timestamp_assigner(lambda txn, _: txn.event_time)
    )

    transactions = env.from_collection([], type_info=Types.PICKLED_BYTE_ARRAY())
    (
        transactions
        .assign_timestamps_and_watermarks(watermark_strategy)
        .key_by(lambda txn: txn.merchant_id)
        .window(TumblingEventTimeWindows.of(Time.hours(1)))
        .process(HourlyRevenueAggregator())
        .print()
    )
    env.execute("Hourly Revenue Pipeline")
```

### Sliding Windows

A sliding window has a **fixed size and a slide interval**. Windows overlap, so each event can belong to multiple windows. Sliding windows are ideal for **rolling metrics** where you need continuous, overlapping aggregations.

**Real-world use case**: Compute a 5-minute rolling average of CPU utilization, updated every 30 seconds. Each data point participates in 10 overlapping windows (5 minutes / 30 seconds).

The **trade-off** with sliding windows is memory: each element is stored in `window_size / slide_interval` windows. A 1-hour window sliding every 1 second means each event exists in 3,600 windows simultaneously, which can overwhelm memory. Therefore, choose slide intervals that are a reasonable fraction of the window size.

### Session Windows

A session window groups events by **activity gaps**. A new window starts when no event has arrived for a configurable gap duration. Session windows are unique because their size is **data-driven** rather than fixed.

**Real-world use case**: Group user clicks into browsing sessions. If a user is idle for more than 30 minutes, the current session closes and a new one begins. This pattern is essential for web analytics, mobile app engagement tracking, and customer journey analysis.

```java
// Java Flink: Session window for user activity tracking
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.windowing.assigners.EventTimeSessionWindows;
import org.apache.flink.streaming.api.windowing.time.Time;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

public class SessionWindowExample {
    // Groups user events into sessions with a 30-minute inactivity gap
    // Emits session summaries including duration and event count

    public static void buildSessionPipeline(DataStream<UserEvent> events) {
        events
            .keyBy(UserEvent::getUserId)
            .window(EventTimeSessionWindows.withGap(Time.minutes(30)))
            .process(new ProcessWindowFunction<UserEvent, SessionSummary, String, TimeWindow>() {
                @Override
                public void process(
                    String userId,
                    Context context,
                    Iterable<UserEvent> elements,
                    Collector<SessionSummary> out
                ) {
                    int count = 0;
                    for (UserEvent e : elements) {
                        count++;
                    }
                    TimeWindow window = context.window();
                    long durationMs = window.getEnd() - window.getStart();
                    out.collect(new SessionSummary(userId, window.getStart(), durationMs, count));
                }
            })
            .print();
    }
}
```

A **pitfall** with session windows is that they can grow unboundedly if events arrive continuously without a gap. This can cause memory exhaustion on the operator, therefore set a maximum session duration as a safety limit.

## Watermark Generation Strategies

Watermarks are **progress indicators** that tell the stream processor: "All events with timestamps up to this point have been observed." This allows the processor to know when it is safe to close a window and emit results.

### Bounded Out-of-Orderness

The most common strategy. You configure a maximum expected delay (e.g., 10 seconds), and the watermark is set to `max_event_time_seen - max_delay`. The **trade-off** is clear:

- **Tight watermark** (small delay): Low latency, but late events are missed.
- **Loose watermark** (large delay): High completeness, but increased end-to-end latency because windows stay open longer.

### Per-Partition Watermarks

When consuming from multiple Kafka partitions with different lag characteristics, Flink tracks watermarks per input partition and advances the overall watermark to the **minimum** across all partitions. A **common mistake** is having one idle partition that never advances its watermark, which stalls the entire pipeline. Flink addresses this with `withIdleness()`:

```python
from pyflink.common import WatermarkStrategy, Duration

def create_robust_watermark_strategy(
    max_out_of_orderness_seconds: int = 10,
    idle_timeout_seconds: int = 60,
) -> WatermarkStrategy:
    # Bounded out-of-orderness with idle partition handling
    # If a partition produces no events for idle_timeout, it is excluded
    # from the watermark calculation to prevent pipeline stalls
    return (
        WatermarkStrategy
        .for_bounded_out_of_orderness(
            Duration.of_seconds(max_out_of_orderness_seconds)
        )
        .with_idleness(Duration.of_seconds(idle_timeout_seconds))
    )
```

## Late Data Handling

Despite watermarks, some events will inevitably arrive after the watermark has passed their window. Flink provides three mechanisms for handling late data:

1. **Allowed lateness**: Keep the window open for an additional period after the watermark passes the window end. Late events within this period trigger window re-computation and emit updated results.
2. **Side outputs**: Route excessively late events (beyond allowed lateness) to a separate stream for manual inspection or offline reprocessing.
3. **Retractions**: When a window result is updated due to a late event, emit a retraction of the previous result followed by the corrected result.

```python
from pyflink.datastream import OutputTag
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.common import Time

# Define a side output tag for late events
LATE_EVENTS_TAG = OutputTag("late-events")

def build_late_data_pipeline(env, stream):
    # Window with 5-minute allowed lateness and side output for very late events
    windowed = (
        stream
        .key_by(lambda event: event.key)
        .window(TumblingEventTimeWindows.of(Time.minutes(5)))
        .allowed_lateness(Time.minutes(5))
        .side_output_late_data(LATE_EVENTS_TAG)
        .reduce(lambda a, b: merge_events(a, b))
    )

    # Main output: windowed aggregations (may include updates from late events)
    windowed.print()

    # Side output: events that arrived more than 5 minutes late
    late_events = windowed.get_side_output(LATE_EVENTS_TAG)
    late_events.add_sink(dead_letter_sink())
```

The **best practice** is to configure allowed lateness based on your observed data characteristics. Analyze the distribution of event-time-to-processing-time skew in your data and set allowed lateness to cover the 99th percentile. Events beyond that go to the side output for investigation.

## Exactly-Once with Flink Checkpointing

Flink achieves exactly-once processing through **distributed snapshots** using the Chandy-Lamport algorithm. The process works as follows:

1. The **checkpoint coordinator** (JobManager) inserts barrier markers into the input streams.
2. When an operator receives a barrier from all its input channels, it snapshots its state to durable storage (HDFS, S3) and forwards the barrier downstream.
3. When all operators have completed the snapshot, the checkpoint is considered complete.
4. On failure, Flink restores operator state from the latest checkpoint and replays input from the corresponding offsets.

This provides exactly-once **state semantics**. For exactly-once **end-to-end** semantics (including sinks), the sink must support either idempotent writes or two-phase commit.

## State Management Patterns

### Keyed State

State that is partitioned by key. Each key has its own independent state, and Flink handles redistribution when parallelism changes. Common keyed state types:

- **ValueState**: A single value per key.
- **ListState**: A list of values per key.
- **MapState**: A key-value map per key.

```java
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.api.common.typeinfo.TypeInformation;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.util.Collector;
import org.apache.flink.configuration.Configuration;

public class FraudDetector extends KeyedProcessFunction<String, Transaction, Alert> {
    // Detects suspicious patterns using keyed state
    // Maintains per-user state tracking the last transaction amount

    private ValueState<Double> lastAmountState;
    private ValueState<Long> lastTimestampState;

    @Override
    public void open(Configuration parameters) {
        lastAmountState = getRuntimeContext().getState(
            new ValueStateDescriptor<>("last-amount", TypeInformation.of(Double.class))
        );
        lastTimestampState = getRuntimeContext().getState(
            new ValueStateDescriptor<>("last-timestamp", TypeInformation.of(Long.class))
        );
    }

    @Override
    public void processElement(
        Transaction txn,
        Context ctx,
        Collector<Alert> out
    ) throws Exception {
        Double lastAmount = lastAmountState.value();
        Long lastTimestamp = lastTimestampState.value();

        if (lastAmount != null && lastTimestamp != null) {
            long timeDelta = txn.getTimestamp() - lastTimestamp;
            // Flag if amount increases 10x within 60 seconds
            if (txn.getAmount() > lastAmount * 10 && timeDelta < 60000) {
                out.collect(new Alert(txn.getUserId(), "rapid-escalation", txn.getAmount()));
            }
        }

        lastAmountState.update(txn.getAmount());
        lastTimestampState.update(txn.getTimestamp());
    }
}
```

### State Backends

Flink supports two main state backends:

- **HashMapStateBackend**: Stores state in JVM heap memory. Fast but limited by heap size. Best for small state.
- **EmbeddedRocksDBStateBackend**: Stores state in RocksDB on local disk with asynchronous snapshots to durable storage. Supports state larger than memory. The **trade-off** is higher per-access latency (disk I/O vs. memory access), however it enables processing with terabytes of state.

A **best practice** is to start with RocksDB in production because it scales predictably. Only switch to HashMapStateBackend when you have profiled and confirmed that state fits comfortably in memory and the access latency difference matters for your SLA.

## Summary and Key Takeaways

- **Tumbling windows** provide non-overlapping periodic aggregation, **sliding windows** provide rolling metrics with overlapping buckets, and **session windows** group events by activity gaps -- each with distinct memory and latency trade-offs
- **Watermarks** are the mechanism for tracking event-time progress; the bounded-out-of-orderness strategy is the standard choice, with the lateness tolerance directly trading off completeness against latency
- **Late data handling** must be a first-class design concern: use allowed lateness for bounded corrections, side outputs for excessively late events, and configure thresholds based on observed skew distributions
- **Exactly-once processing** in Flink is achieved through distributed snapshot barriers (Chandy-Lamport), but end-to-end exactly-once additionally requires idempotent or transactional sinks
- **Keyed state** is partitioned by key and automatically redistributed on rescaling; use ValueState for simple per-key tracking and MapState for richer per-key data structures
- **RocksDB state backend** is the best practice for production because it supports state larger than memory and provides predictable scaling, while HashMapStateBackend offers lower latency for small-state workloads
"""
    ),
]
