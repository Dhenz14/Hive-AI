"""Pandas — data manipulation, cleaning, aggregation, and performance patterns."""

PAIRS = [
    (
        "python/pandas-fundamentals",
        "Show Pandas patterns: data loading, cleaning, transformation, groupby, merge, and window functions.",
        '''Pandas data manipulation patterns:

```python
import pandas as pd
import numpy as np
from typing import Optional

# --- Data loading ---

# CSV with type hints and parsing
df = pd.read_csv(
    "data.csv",
    dtype={"user_id": str, "category": "category", "amount": float},
    parse_dates=["created_at"],
    usecols=["user_id", "category", "amount", "created_at"],
    na_values=["", "NULL", "N/A"],
)

# Chunked reading for large files
def process_large_csv(filepath: str, chunksize: int = 100_000):
    results = []
    for chunk in pd.read_csv(filepath, chunksize=chunksize):
        processed = chunk.groupby("category")["amount"].sum()
        results.append(processed)
    return pd.concat(results).groupby(level=0).sum()


# --- Data cleaning ---

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Standard cleaning pipeline."""
    df = df.copy()

    # Remove duplicates
    df = df.drop_duplicates(subset=["user_id", "created_at"])

    # Handle missing values
    df["amount"] = df["amount"].fillna(0)
    df["category"] = df["category"].fillna("unknown")
    df = df.dropna(subset=["user_id"])  # Required field

    # Fix data types
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

    # String cleaning
    df["email"] = df["email"].str.lower().str.strip()
    df["name"] = df["name"].str.title().str.strip()

    # Remove outliers (IQR method)
    Q1 = df["amount"].quantile(0.25)
    Q3 = df["amount"].quantile(0.75)
    IQR = Q3 - Q1
    df = df[(df["amount"] >= Q1 - 1.5 * IQR) & (df["amount"] <= Q3 + 1.5 * IQR)]

    return df


# --- Groupby and aggregation ---

# Multiple aggregations
summary = df.groupby("category").agg(
    total_amount=("amount", "sum"),
    avg_amount=("amount", "mean"),
    count=("amount", "count"),
    unique_users=("user_id", "nunique"),
    max_amount=("amount", "max"),
).sort_values("total_amount", ascending=False)

# Custom aggregation
def percentile_95(x):
    return x.quantile(0.95)

stats = df.groupby("category")["amount"].agg(
    ["mean", "median", "std", percentile_95]
)

# Transform: add group-level stats back to each row
df["category_avg"] = df.groupby("category")["amount"].transform("mean")
df["pct_of_category"] = df["amount"] / df["category_avg"]

# Filter groups
big_categories = df.groupby("category").filter(lambda g: len(g) >= 100)


# --- Merge / Join ---

# Inner join
merged = pd.merge(orders, customers, on="customer_id", how="inner")

# Left join with indicator
merged = pd.merge(
    customers, orders,
    on="customer_id", how="left", indicator=True,
)
no_orders = merged[merged["_merge"] == "left_only"]

# Multiple key join
merged = pd.merge(
    sales, products,
    left_on=["product_id", "region"],
    right_on=["id", "market_region"],
    suffixes=("_sale", "_product"),
)


# --- Window functions ---

# Rolling average
df["rolling_7d_avg"] = (
    df.sort_values("date")
    .groupby("category")["amount"]
    .transform(lambda x: x.rolling(7, min_periods=1).mean())
)

# Cumulative sum per group
df["cumulative_amount"] = df.groupby("user_id")["amount"].cumsum()

# Rank within group
df["rank_in_category"] = df.groupby("category")["amount"].rank(
    method="dense", ascending=False
)

# Lag / Lead
df["prev_amount"] = df.groupby("user_id")["amount"].shift(1)
df["amount_change"] = df["amount"] - df["prev_amount"]

# Expanding window (all previous rows)
df["running_max"] = df.groupby("category")["amount"].expanding().max().reset_index(level=0, drop=True)


# --- Pivot and reshape ---

# Pivot table
pivot = df.pivot_table(
    values="amount",
    index="category",
    columns=pd.Grouper(key="created_at", freq="M"),
    aggfunc="sum",
    fill_value=0,
)

# Melt (wide to long)
long = pd.melt(
    wide_df,
    id_vars=["user_id", "date"],
    value_vars=["metric_a", "metric_b", "metric_c"],
    var_name="metric",
    value_name="value",
)

# Cross-tabulation
cross = pd.crosstab(
    df["category"], df["status"],
    margins=True, normalize="index",
)
```

Performance tips:
1. **`category` dtype** — for low-cardinality strings (10x memory reduction)
2. **`usecols`** — only read needed columns
3. **Chunked processing** — for files larger than memory
4. **Vectorized ops** — avoid `apply()` loops; use built-in methods
5. **`transform`** — add group stats without reshaping'''
    ),
    (
        "python/pandas-advanced",
        "Show advanced Pandas patterns: method chaining, pipe, eval/query, MultiIndex, and performance optimization.",
        '''Advanced Pandas patterns for clean, performant code:

```python
import pandas as pd
import numpy as np

# --- Method chaining (fluent API) ---

result = (
    pd.read_csv("sales.csv", parse_dates=["date"])
    .query("amount > 0")
    .assign(
        year=lambda df: df["date"].dt.year,
        month=lambda df: df["date"].dt.month,
        quarter=lambda df: df["date"].dt.quarter,
        amount_log=lambda df: np.log1p(df["amount"]),
    )
    .groupby(["year", "quarter", "category"])
    .agg(
        total=("amount", "sum"),
        count=("amount", "count"),
        avg=("amount", "mean"),
    )
    .reset_index()
    .sort_values(["year", "quarter", "total"], ascending=[True, True, False])
    .pipe(add_growth_rate, "total")
)

def add_growth_rate(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Pipe-compatible function."""
    df = df.copy()
    df[f"{column}_growth"] = df.groupby("category")[column].pct_change()
    return df


# --- query and eval (readable filtering) ---

# query: string-based filtering (faster for large DataFrames)
filtered = df.query(
    "amount > 100 and category == 'electronics' and date >= '2024-01-01'"
)

# With variables
min_amount = 50
category = "electronics"
filtered = df.query("amount > @min_amount and category == @category")

# eval: computed columns (avoids intermediate arrays)
df.eval("profit = revenue - cost", inplace=True)
df.eval("margin = profit / revenue * 100", inplace=True)


# --- MultiIndex ---

# Create MultiIndex
mi_df = df.set_index(["region", "category", "date"]).sort_index()

# Access levels
mi_df.loc["US"]                          # All US data
mi_df.loc[("US", "electronics")]         # US electronics
mi_df.loc[("US", "electronics", "2024-01-01")]  # Specific entry

# Cross-section
mi_df.xs("electronics", level="category")  # All regions, electronics

# Reset specific level
mi_df.reset_index(level="date")

# Aggregate over level
mi_df.groupby(level=["region", "category"]).sum()


# --- Performance optimization ---

# 1. Use appropriate dtypes
def optimize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce memory usage by downcasting types."""
    df = df.copy()

    for col in df.select_dtypes(include=["int64"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="integer")

    for col in df.select_dtypes(include=["float64"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="float")

    for col in df.select_dtypes(include=["object"]).columns:
        if df[col].nunique() / len(df) < 0.5:
            df[col] = df[col].astype("category")

    return df

# 2. Vectorized string operations
df["domain"] = df["email"].str.split("@").str[1]
df["has_gmail"] = df["email"].str.contains("gmail.com", na=False)

# 3. numpy where (faster than apply)
df["tier"] = np.where(df["amount"] > 1000, "premium",
             np.where(df["amount"] > 100, "standard", "basic"))

# 4. Categorical for groupby (much faster)
df["category"] = df["category"].astype("category")

# 5. Memory usage check
print(df.memory_usage(deep=True).sum() / 1e6, "MB")
print(df.dtypes)

# 6. Avoid apply — use vectorized alternatives
# BAD (slow):
df["result"] = df.apply(lambda row: row["a"] + row["b"], axis=1)
# GOOD (fast):
df["result"] = df["a"] + df["b"]

# BAD:
df["category_upper"] = df["category"].apply(str.upper)
# GOOD:
df["category_upper"] = df["category"].str.upper()


# --- Time series resampling ---

ts = df.set_index("date")

# Resample to monthly
monthly = ts.resample("ME").agg({
    "amount": "sum",
    "user_id": "nunique",
    "orders": "count",
})

# Business days
ts.resample("B").ffill()  # Forward fill business days

# Rolling with time-based window
ts["rolling_30d"] = ts["amount"].rolling("30D").mean()
```

Advanced patterns:
1. **Method chaining** — `.assign()` + `.query()` + `.pipe()` for readability
2. **`pipe()`** — pass DataFrame through custom functions in the chain
3. **`query()`** — string-based filtering, faster than boolean indexing for large DFs
4. **Dtype optimization** — downcast numerics, categorize strings (50-90% memory reduction)
5. **Avoid `apply`** — use vectorized operations for 100x speedup'''
    ),
]
"""
