"""Polars and Apache Arrow — modern dataframe processing for 2026."""

PAIRS = [
    (
        "databases/polars-dataframe",
        "Show Polars dataframe patterns: lazy evaluation, expressions, group-by, joins, and comparison with pandas.",
        '''Polars dataframe patterns:

```python
import polars as pl
from datetime import datetime, date


# --- Lazy vs Eager ---

# Eager (like pandas — immediate execution)
df = pl.DataFrame({
    "user_id": [1, 2, 3, 1, 2],
    "amount": [100.0, 200.0, 150.0, 300.0, 50.0],
    "category": ["food", "tech", "food", "tech", "food"],
    "date": ["2024-01-15", "2024-01-16", "2024-01-17", "2024-02-01", "2024-02-05"],
})

# Lazy (query plan — optimized before execution)
lf = df.lazy()
result = (
    lf
    .filter(pl.col("amount") > 100)
    .group_by("category")
    .agg([
        pl.col("amount").sum().alias("total"),
        pl.col("amount").mean().alias("avg"),
        pl.len().alias("count"),
    ])
    .sort("total", descending=True)
    .collect()  # Execute the optimized plan
)


# --- Scan files (lazy, never loads full file) ---

# CSV scan
lf = pl.scan_csv("sales_*.csv")

# Parquet scan (columnar, predicate pushdown)
lf = pl.scan_parquet("data/events/*.parquet")
result = (
    lf
    .filter(pl.col("event_type") == "purchase")
    .select("user_id", "amount", "timestamp")
    .collect()
)


# --- Expressions (Polars superpower) ---

df = pl.DataFrame({
    "name": ["Alice", "Bob", "Charlie", "Diana"],
    "score": [85, 92, 78, 96],
    "department": ["eng", "eng", "sales", "sales"],
})

# Column expressions
result = df.select(
    pl.col("name"),
    pl.col("score"),
    (pl.col("score") - pl.col("score").mean()).alias("score_deviation"),
    pl.col("score").rank().alias("rank"),
    pl.when(pl.col("score") >= 90)
        .then(pl.lit("A"))
        .when(pl.col("score") >= 80)
        .then(pl.lit("B"))
        .otherwise(pl.lit("C"))
        .alias("grade"),
)

# Window functions (over)
result = df.with_columns(
    pl.col("score").mean().over("department").alias("dept_avg"),
    pl.col("score").rank().over("department").alias("dept_rank"),
    (pl.col("score") / pl.col("score").sum().over("department") * 100)
        .round(1)
        .alias("dept_pct"),
)


# --- String and date operations ---

df = pl.DataFrame({
    "email": ["alice@company.com", "bob@gmail.com", "charlie@company.com"],
    "joined": ["2023-06-15", "2024-01-20", "2024-03-10"],
    "bio": ["Senior Engineer at ACME", "Junior Dev", "Staff Engineer at ACME Corp"],
})

result = df.with_columns(
    pl.col("email").str.split("@").list.last().alias("domain"),
    pl.col("joined").str.to_date("%Y-%m-%d").alias("join_date"),
    pl.col("bio").str.contains("(?i)engineer").alias("is_engineer"),
    pl.col("bio").str.extract(r"(Senior|Junior|Staff)", 1).alias("level"),
)


# --- Group-by with complex aggregations ---

sales = pl.DataFrame({
    "store": ["A", "A", "B", "B", "A", "B"],
    "product": ["X", "Y", "X", "Y", "X", "X"],
    "revenue": [100, 200, 150, 300, 120, 180],
    "units": [10, 5, 8, 12, 6, 9],
})

summary = sales.group_by("store").agg(
    pl.col("revenue").sum().alias("total_revenue"),
    pl.col("revenue").mean().alias("avg_revenue"),
    (pl.col("revenue") / pl.col("units")).mean().alias("avg_price"),
    pl.col("product").n_unique().alias("unique_products"),
    pl.col("revenue").filter(pl.col("product") == "X").sum().alias("product_x_revenue"),
)


# --- Joins ---

users = pl.DataFrame({
    "id": [1, 2, 3],
    "name": ["Alice", "Bob", "Charlie"],
})

orders = pl.DataFrame({
    "user_id": [1, 1, 2, 4],
    "amount": [50, 75, 100, 200],
})

# Inner join
joined = users.join(orders, left_on="id", right_on="user_id", how="inner")

# Left join with coalesce
joined = users.join(orders, left_on="id", right_on="user_id", how="left")

# Anti join (users with no orders)
no_orders = users.join(orders, left_on="id", right_on="user_id", how="anti")


# --- Pivoting ---

pivoted = sales.pivot(
    on="product",
    index="store",
    values="revenue",
    aggregate_function="sum",
)
# shape: (2, 3)
# ┌───────┬──────┬──────┐
# │ store │ X    │ Y    │
# ├───────┼──────┼──────┤
# │ A     │ 220  │ 200  │
# │ B     │ 330  │ 300  │
# └───────┴──────┴──────┘


# --- Polars vs Pandas cheat sheet ---

# Pandas                          Polars
# df["col"]                       pl.col("col")
# df[df["x"] > 5]                 df.filter(pl.col("x") > 5)
# df.groupby("g").agg({"x":"sum"})  df.group_by("g").agg(pl.col("x").sum())
# df.apply(fn, axis=1)            df.with_columns(pl.struct("a","b").map_elements(fn))
# df.merge(other, on="key")       df.join(other, on="key")
# pd.read_csv("f.csv")            pl.read_csv("f.csv")  or  pl.scan_csv("f.csv")
```

Polars patterns:
1. **Lazy evaluation** — `scan_csv/parquet` + `.collect()` enables query optimization and predicate pushdown
2. **Expressions** — `pl.col()`, `pl.when().then()`, `.over()` replace pandas apply/transform
3. **Window functions** — `.over("group")` for partition-level aggregates without group_by
4. **Predicate pushdown** — Polars skips reading columns/rows that aren't needed
5. **Multithreaded** — automatic parallelism across cores, 10-100x faster than pandas'''
    ),
    (
        "data-engineering/apache-arrow-columnar",
        "Show Apache Arrow and PyArrow patterns: zero-copy data sharing, IPC, Parquet I/O, and compute kernels.",
        '''Apache Arrow and PyArrow patterns:

```python
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as pafs
from pathlib import Path


# --- Arrow tables (columnar, zero-copy) ---

# Create table from Python data
table = pa.table({
    "user_id": pa.array([1, 2, 3, 4, 5], type=pa.int64()),
    "name": pa.array(["Alice", "Bob", "Charlie", "Diana", "Eve"]),
    "score": pa.array([85.5, 92.0, 78.3, 96.1, 88.7], type=pa.float64()),
    "active": pa.array([True, True, False, True, False]),
})

# Schema inspection
print(table.schema)
# user_id: int64
# name: string
# score: float64
# active: bool

# Zero-copy column access
scores = table.column("score")  # pa.ChunkedArray, no data copied
print(scores.to_pylist())  # [85.5, 92.0, 78.3, 96.1, 88.7]


# --- Compute kernels (vectorized C++ operations) ---

# Filter
mask = pc.greater(table.column("score"), 85.0)
filtered = table.filter(mask)

# Sort
sorted_table = pc.sort_indices(table, sort_keys=[("score", "descending")])
sorted_table = table.take(sorted_table)

# Aggregation
mean_score = pc.mean(table.column("score"))  # Scalar: 88.12
sum_score = pc.sum(table.column("score"))

# String operations
names = table.column("name")
upper = pc.utf8_upper(names)
lengths = pc.utf8_length(names)
starts_with = pc.starts_with(names, "A")


# --- Parquet I/O (columnar storage) ---

# Write
pq.write_table(table, "users.parquet", compression="zstd")

# Read (column pruning — only reads requested columns)
subset = pq.read_table("users.parquet", columns=["user_id", "score"])

# Read with predicate pushdown
subset = pq.read_table(
    "users.parquet",
    filters=[("score", ">", 85.0), ("active", "==", True)],
)

# Write partitioned dataset
pq.write_to_dataset(
    table,
    root_path="data/users",
    partition_cols=["active"],
)
# Creates: data/users/active=true/part-0.parquet
#          data/users/active=false/part-0.parquet


# --- Dataset API (scan large partitioned datasets) ---

dataset = ds.dataset(
    "data/events/",
    format="parquet",
    partitioning=ds.partitioning(
        pa.schema([("year", pa.int32()), ("month", pa.int32())]),
        flavor="hive",
    ),
)

# Scan with filter (only reads matching partitions)
scanner = dataset.scanner(
    columns=["user_id", "event_type", "amount"],
    filter=(ds.field("year") == 2024) & (ds.field("event_type") == "purchase"),
)
result = scanner.to_table()


# --- IPC (Inter-Process Communication) ---

# Write Arrow IPC (for zero-copy sharing between processes)
with pa.ipc.new_file("data.arrow", table.schema) as writer:
    writer.write_table(table)

# Read Arrow IPC
with pa.ipc.open_file("data.arrow") as reader:
    loaded = reader.read_all()

# Streaming IPC (for large datasets)
sink = pa.BufferOutputStream()
with pa.ipc.new_stream(sink, table.schema) as writer:
    for batch in table.to_batches(max_chunksize=1000):
        writer.write_batch(batch)


# --- Zero-copy conversion to other libraries ---

# Arrow → Pandas (zero-copy where possible)
df = table.to_pandas(self_destruct=True)  # Frees Arrow memory after conversion

# Arrow → Polars (zero-copy)
import polars as pl
polars_df = pl.from_arrow(table)

# Pandas → Arrow
table_back = pa.Table.from_pandas(df)


# --- Custom schema and nested types ---

schema = pa.schema([
    ("id", pa.int64()),
    ("tags", pa.list_(pa.string())),
    ("metadata", pa.struct([
        ("source", pa.string()),
        ("confidence", pa.float32()),
    ])),
    ("embedding", pa.list_(pa.float32(), 384)),  # Fixed-size list
])
```

Apache Arrow patterns:
1. **Zero-copy** — share data between Polars, pandas, and processes without serialization
2. **Compute kernels** — `pc.sum()`, `pc.filter()`, `pc.sort_indices()` run vectorized C++
3. **Parquet** — columnar storage with column pruning and predicate pushdown
4. **Dataset API** — scan partitioned datasets across files with lazy filtering
5. **IPC format** — inter-process data sharing without serialization overhead'''
    ),
]
"""
