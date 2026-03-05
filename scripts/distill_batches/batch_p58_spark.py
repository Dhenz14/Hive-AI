"""Data engineering — PySpark patterns, DataFrame API, and optimizations."""

PAIRS = [
    (
        "data-engineering/pyspark-fundamentals",
        "Show PySpark patterns: DataFrame operations, joins, aggregations, window functions, and UDFs.",
        '''PySpark DataFrame patterns:

```python
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType,
    DoubleType, TimestampType, ArrayType,
)

# --- Session setup ---

spark = (
    SparkSession.builder
    .appName("ETL Pipeline")
    .config("spark.sql.adaptive.enabled", "true")  # AQE
    .config("spark.sql.shuffle.partitions", "200")
    .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
    .getOrCreate()
)


# --- Schema definition (prefer explicit over inference) ---

order_schema = StructType([
    StructField("order_id", StringType(), nullable=False),
    StructField("customer_id", StringType(), nullable=False),
    StructField("product_id", StringType(), nullable=False),
    StructField("quantity", IntegerType(), nullable=False),
    StructField("price", DoubleType(), nullable=False),
    StructField("ordered_at", TimestampType(), nullable=False),
])

orders = (
    spark.read
    .schema(order_schema)
    .option("header", "true")
    .option("mode", "DROPMALFORMED")
    .csv("s3a://data-lake/raw/orders/")
)


# --- Transformations ---

# Filtering and computed columns
cleaned = (
    orders
    .filter(F.col("quantity") > 0)
    .filter(F.col("price") > 0)
    .withColumn("total", F.col("quantity") * F.col("price"))
    .withColumn("order_date", F.to_date("ordered_at"))
    .withColumn("year_month", F.date_format("ordered_at", "yyyy-MM"))
)

# Aggregations
daily_revenue = (
    cleaned
    .groupBy("order_date")
    .agg(
        F.count("order_id").alias("total_orders"),
        F.sum("total").alias("gross_revenue"),
        F.avg("total").alias("avg_order_value"),
        F.countDistinct("customer_id").alias("unique_customers"),
        F.percentile_approx("total", 0.5).alias("median_order_value"),
    )
    .orderBy("order_date")
)


# --- Window functions ---

window_spec = Window.partitionBy("customer_id").orderBy("ordered_at")
cumulative_window = Window.partitionBy("customer_id").orderBy("ordered_at") \
    .rowsBetween(Window.unboundedPreceding, Window.currentRow)

customer_orders = (
    cleaned
    .withColumn("order_num",
                F.row_number().over(window_spec))
    .withColumn("prev_order_date",
                F.lag("ordered_at").over(window_spec))
    .withColumn("days_since_last",
                F.datediff("ordered_at", F.lag("ordered_at").over(window_spec)))
    .withColumn("cumulative_spend",
                F.sum("total").over(cumulative_window))
    .withColumn("running_avg",
                F.avg("total").over(cumulative_window))
)


# --- Joins ---

products = spark.read.parquet("s3a://data-lake/dim/products/")
customers = spark.read.parquet("s3a://data-lake/dim/customers/")

# Broadcast small dimension table (< 10MB)
enriched = (
    cleaned
    .join(F.broadcast(products), "product_id", "left")
    .join(customers, "customer_id", "left")
    .select(
        "order_id", "customer_id",
        customers["name"].alias("customer_name"),
        products["category"].alias("product_category"),
        "total", "ordered_at",
    )
)


# --- UDFs (use sparingly — prefer built-in functions) ---

from pyspark.sql.functions import udf, pandas_udf
import pandas as pd

# Pandas UDF (vectorized — much faster than row UDFs)
@pandas_udf(DoubleType())
def apply_discount(prices: pd.Series, quantities: pd.Series) -> pd.Series:
    """Bulk discount: 10% off for qty >= 10."""
    discount = (quantities >= 10).astype(float) * 0.1
    return prices * (1 - discount)

with_discount = cleaned.withColumn(
    "discounted_price",
    apply_discount(F.col("price"), F.col("quantity"))
)


# --- Writing output ---

# Partitioned parquet (most common data lake format)
(
    enriched
    .repartition("year_month")
    .write
    .mode("overwrite")
    .partitionBy("year_month")
    .parquet("s3a://data-lake/processed/enriched_orders/")
)

# Delta Lake (ACID transactions)
# enriched.write.format("delta").mode("merge").save("s3a://delta/orders/")
```

PySpark patterns:
1. **Explicit schemas** — avoid `inferSchema=true` in production (slow + fragile)
2. **`broadcast()` joins** — broadcast small tables to avoid shuffles
3. **Window functions** — row_number, lag, cumulative sums without self-joins
4. **Pandas UDFs** — 10-100x faster than row-level UDFs (vectorized)
5. **Partition by date** — partition output for efficient downstream queries'''
    ),
    (
        "data-engineering/spark-optimization",
        "Show PySpark optimization patterns: partitioning, caching, skew handling, and explain plans.",
        '''PySpark optimization patterns:

```python
from pyspark.sql import SparkSession, functions as F


# --- Partition management ---

# Check current partitioning
df.rdd.getNumPartitions()  # e.g., 200

# Repartition for parallelism (causes full shuffle)
df_repartitioned = df.repartition(100)  # By count
df_by_key = df.repartition("date", "region")  # By columns

# Coalesce to reduce partitions (no shuffle — merges adjacent)
df_small = df.coalesce(10)  # When writing small output

# Rule of thumb: ~128MB per partition
# target_partitions = total_data_size_mb / 128


# --- Caching strategies ---

# Cache when reusing a DataFrame multiple times
df_cached = (
    spark.read.parquet("s3a://data/orders/")
    .filter(F.col("status") == "completed")
    .cache()  # Stores in memory (deserialized)
)

# Force materialization
df_cached.count()  # Triggers cache

# Use in multiple downstream operations
revenue = df_cached.groupBy("region").sum("total")
counts = df_cached.groupBy("region").count()

# PERSIST for larger datasets (memory + disk)
from pyspark import StorageLevel
df_large = df.persist(StorageLevel.MEMORY_AND_DISK_SER)

# Always unpersist when done
df_cached.unpersist()


# --- Handling data skew ---

# Problem: one key has 100x more records than others
# Symptom: one task takes forever while others finish quickly

# Solution 1: Salted keys (distribute hot key across partitions)
from pyspark.sql import functions as F
import random

num_salts = 10

# Salt the large table
orders_salted = (
    orders
    .withColumn("salt", (F.rand() * num_salts).cast("int"))
    .withColumn("salted_key",
                F.concat("customer_id", F.lit("_"), "salt"))
)

# Explode the small table to match all salts
customers_exploded = (
    customers
    .crossJoin(
        spark.range(num_salts).withColumnRenamed("id", "salt")
    )
    .withColumn("salted_key",
                F.concat("customer_id", F.lit("_"), "salt"))
)

# Join on salted key (distributes hot key across partitions)
result = orders_salted.join(customers_exploded, "salted_key")

# Solution 2: AQE skew join (Spark 3.0+, automatic)
# spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")
# spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes", "256m")


# --- Explain and optimize ---

# Check execution plan
df.explain(mode="formatted")  # Shows parsed, analyzed, optimized, physical plans
# df.explain("cost")  # Shows estimated costs

# Common explain plan red flags:
# - BroadcastNestedLoopJoin → usually means missing join key
# - SortMergeJoin on small table → should be BroadcastHashJoin
# - Exchange (shuffle) → check if necessary

# Check data sizes for broadcast decision
print(f"Products: {products.count()} rows")
# If < 10MB, broadcast: spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "10m")


# --- Column pruning and predicate pushdown ---

# GOOD: Select columns early (column pruning)
orders_slim = (
    spark.read.parquet("s3a://data/orders/")
    .select("order_id", "customer_id", "total", "ordered_at")
    .filter(F.col("ordered_at") >= "2024-01-01")  # Pushes to file scan
)

# BAD: Read everything then filter
# orders_all = spark.read.parquet("s3a://data/orders/")
# orders_filtered = orders_all.filter(...)  # Still works but reads all columns


# --- Avoid common anti-patterns ---

# BAD: collect() on large dataset
# all_rows = df.collect()  # OOM on driver

# GOOD: Use .take(), .show(), or write output
sample = df.take(10)  # Only 10 rows to driver
df.show(20, truncate=False)  # Display in console

# BAD: Python UDF for simple operations
# @udf(StringType())
# def upper(s): return s.upper()

# GOOD: Use built-in function
df.withColumn("name_upper", F.upper("name"))

# BAD: Multiple small writes
# for date in dates:
#     df.filter(F.col("date") == date).write.parquet(f"output/{date}/")

# GOOD: Partitioned write (one job)
df.write.partitionBy("date").parquet("output/")
```

Spark optimization rules:
1. **Column pruning** — `.select()` early to minimize data shuffled
2. **Predicate pushdown** — `.filter()` early, Spark pushes to file scan
3. **Broadcast joins** — broadcast dimension tables under 10MB
4. **Salted keys** — distribute skewed keys across partitions
5. **Cache wisely** — only cache DataFrames reused multiple times, always unpersist'''
    ),
]
