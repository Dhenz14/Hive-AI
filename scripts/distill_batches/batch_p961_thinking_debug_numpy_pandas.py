PAIRS = [
    ("thinking/debugging", r'''My pandas boolean indexing gives wrong results:

```python
import pandas as pd

df = pd.DataFrame({
    'status': ['active', 'inactive', 'active', 'pending'],
    'score': [85, 92, 78, 95],
})

# Want: active OR score > 90
result = df[df['status'] == 'active' | df['score'] > 90]
print(result)
```

Expected 3 rows (active rows + the 92-score row), but I get:
```
TypeError: Cannot perform 'ror_' with a scalar value
```

What's wrong?''', r'''<think>
The user gets a TypeError with pandas boolean indexing. This could be a type mismatch issue... but wait, the error message mentions 'ror_' which is the reflected bitwise OR operator. That points to operator precedence, not data types.

In Python, the bitwise OR operator `|` has higher precedence than the comparison operators `==` and `>`. So the expression is parsed as:

`df['status'] == ('active' | df['score']) > 90`

which tries to OR the string 'active' with a pandas Series, causing the TypeError.

I considered whether this might be a pandas version issue, but that won't work as an explanation because Python operator precedence is a language-level rule, not a pandas behavior. Because `|` binds tighter than `==` in Python's grammar, therefore parentheses are the only fix. The tradeoff is that parentheses add visual clutter, but `df.query()` offers a cleaner alternative for complex filters since it uses its own parser that handles precedence more intuitively.
</think>

The issue is Python's operator precedence. The bitwise OR `|` operator has **higher precedence** than the comparison operators `==` and `>`. Your expression is parsed as:

```python
df['status'] == ('active' | df['score']) > 90
```

Python tries to evaluate `'active' | df['score']` first, which attempts a bitwise OR between a string and a Series -- hence the TypeError.

**Fix: Wrap each condition in parentheses**

```python
result = df[(df['status'] == 'active') | (df['score'] > 90)]
print(result)
```

Output:
```
     status  score
0    active     85
1  inactive     92
2    active     78
3   pending     95
```

**Why pandas uses `|` instead of `or`:**

Python's `or` operator cannot be overloaded for element-wise operations on Series. It calls `bool()` on the entire Series, which raises "The truth value of a Series is ambiguous." The bitwise operators `&`, `|`, `~` are used instead because they can be overloaded via `__or__`, `__and__`, `__invert__`.

**Common boolean indexing patterns:**

```python
# AND: both conditions must be true
df[(df['status'] == 'active') & (df['score'] > 80)]

# OR: either condition
df[(df['status'] == 'active') | (df['score'] > 90)]

# NOT: negate a condition
df[~(df['status'] == 'inactive')]

# Multiple values: use isin()
df[df['status'].isin(['active', 'pending'])]

# Complex conditions: use query() for readability
df.query("status == 'active' or score > 90")
# No parentheses needed with query()!
```

**The `query()` method is often cleaner for complex filters:**

```python
# Equivalent, but more readable
result = df.query("status == 'active' | score > 90")
result = df.query("status in ['active', 'pending'] and score > 80")
```

**Prevention tips:**
- Always use parentheses around each condition in pandas boolean expressions
- Consider using `df.query()` for complex multi-condition filters
- Use a linter or formatter that warns about operator precedence issues
- Remember: `&` for AND, `|` for OR, `~` for NOT (not `and`, `or`, `not`)
- Test filters on small sample data before applying to large DataFrames'''),

    ("thinking/debugging", r'''I keep getting SettingWithCopyWarning and my data modifications are silently lost:

```python
import pandas as pd

df = pd.DataFrame({
    'department': ['eng', 'sales', 'eng', 'sales', 'eng'],
    'salary': [100000, 80000, 95000, 75000, 110000],
    'bonus': [0, 0, 0, 0, 0],
})

eng_df = df[df['department'] == 'eng']
eng_df['bonus'] = eng_df['salary'] * 0.1

print(df['bonus'].sum())  # Expected: 30500, Got: 0
```

Warning:
```
SettingWithCopyWarning: A value is trying to be set on a copy of a slice from a DataFrame.
Try using .loc[row_indexer,col_indexer] = value instead
```

Why is the bonus column still all zeros in the original DataFrame?''', r'''<think>
The user modifies a filtered DataFrame and the original is unchanged. This could be a pandas bug... but wait, the SettingWithCopyWarning is literally telling them what is wrong.

When you do `eng_df = df[df['department'] == 'eng']`, pandas may return either a view (reference to original data) or a copy (independent data). I initially thought boolean indexing might return a view in some cases, but actually it typically returns a copy. Hmm, actually, the behavior depends on pandas version and internal memory layout -- pandas itself is not always sure whether it created a view or copy, which is precisely why the warning exists.

When you then set `eng_df['bonus'] = ...`, you are modifying the copy, not the original `df`. Hence df['bonus'] remains all zeros. Because the assignment targets a copy rather than the original, therefore the changes are silently lost.

I considered suggesting they just suppress the warning, but that won't work because the underlying problem (modifying a copy) would still cause silent data loss. The fix is to use `.loc` on the original DataFrame to modify in place. Option A (.loc) modifies the original directly while option B (.copy()) creates an intentionally independent DataFrame -- the choice depends on whether they want changes to propagate back.
</think>

When you do `eng_df = df[df['department'] == 'eng']`, pandas creates a **copy** of the filtered rows (boolean indexing always returns a copy). Modifying `eng_df` modifies the copy, not the original `df`. Your bonus assignments are silently discarded.

**The chain of events:**
```
df (original)  --->  eng_df (independent copy)
                     eng_df['bonus'] = ...  <- modifies copy only
df['bonus']  --->  still all zeros
```

**Fix: Use .loc on the original DataFrame**

```python
df.loc[df['department'] == 'eng', 'bonus'] = df.loc[df['department'] == 'eng', 'salary'] * 0.1
print(df['bonus'].sum())  # 30500.0
```

`.loc` modifies `df` directly -- no intermediate copy is created.

**Alternative: Use .copy() explicitly when you want an independent DataFrame**

```python
# If you WANT a separate DataFrame for engineering:
eng_df = df[df['department'] == 'eng'].copy()
eng_df['bonus'] = eng_df['salary'] * 0.1
# eng_df is now independent -- changes don't affect df (intentional)
```

**When does pandas create a view vs a copy?**

```python
# VIEWS (changes propagate to original):
df['salary']           # single column selection
df[2:5]                # slice indexing
df.iloc[2:5]           # iloc slice

# COPIES (changes do NOT propagate):
df[df['x'] > 5]        # boolean indexing
df[['a', 'b']]         # multiple column selection
df.query("x > 5")      # query
```

However, this behavior is inconsistent and depends on pandas version and internal memory layout. That is why the warning exists -- pandas itself is not sure if it is a view or copy.

**Modern pandas approach (pandas 2.0+ with Copy-on-Write):**

```python
pd.options.mode.copy_on_write = True

# Now ALL indexing returns a copy-on-write view
# Modifications always create an independent copy
# No more SettingWithCopyWarning
eng_df = df[df['department'] == 'eng']
eng_df['bonus'] = eng_df['salary'] * 0.1  # creates an independent copy automatically
# df is unchanged (clear, predictable behavior)
```

**Common patterns that trigger the warning:**

```python
# Chained indexing -- ALWAYS problematic
df[df['dept'] == 'eng']['bonus'] = 100   # modifies a temporary!

# Fix: use .loc
df.loc[df['dept'] == 'eng', 'bonus'] = 100

# Multiple steps -- may or may not work
subset = df[condition]
subset['col'] = value   # WARNING: may modify copy

# Fix: either use .loc on original, or explicit .copy()
```

**Prevention tips:**
- Always use `.loc[]` or `.iloc[]` for assignment operations
- When creating subsets, call `.copy()` explicitly to make your intent clear
- Enable Copy-on-Write mode in pandas 2.0+ for consistent behavior
- Treat SettingWithCopyWarning as an error: `pd.options.mode.chained_assignment = 'raise'`
- Never use chained indexing (`df[...][...] = value`) for assignment'''),

    ("thinking/debugging", r'''My numpy operation is giving unexpected results due to axis confusion:

```python
import numpy as np

# Matrix of test scores: 4 students, 3 tests
scores = np.array([
    [85, 90, 78],
    [92, 88, 95],
    [76, 82, 80],
    [88, 91, 87],
])

# Want: average score per student (should be 4 values)
student_avg = np.mean(scores, axis=0)
print(f"Student averages: {student_avg}")
# Output: Student averages: [85.25 87.75 85.  ]  -- only 3 values!

# Want: average score per test (should be 3 values)
test_avg = np.mean(scores, axis=1)
print(f"Test averages: {test_avg}")
# Output: Test averages: [84.33 91.67 79.33 88.67]  -- 4 values!
```

The axes are backwards from what I expected. Why?''', r'''<think>
This is the classic numpy axis confusion. The user expects axis=0 to give "per-row" results... but wait, that is the opposite of how numpy works.

For a 2D array with shape (4, 3):
- axis=0 means "operate along axis 0 (rows)" -- this COLLAPSES rows, leaving columns. Result shape: (3,)
- axis=1 means "operate along axis 1 (columns)" -- this COLLAPSES columns, leaving rows. Result shape: (4,)

I considered explaining it as "axis=0 means row-wise"... hmm, actually, that phrasing is ambiguous and part of the problem. "Row-wise" could mean "for each row" or "across rows." The clearest mental model is: the axis parameter specifies which axis disappears. Because axis=0 has size 4, collapsing it leaves size (3,).

So:
- axis=0: mean across all students for each test -> 3 values (one per test)
- axis=1: mean across all tests for each student -> 4 values (one per student)

The user has them swapped. The tradeoff between numpy's axis convention and a labeled approach like xarray is worth mentioning -- numpy is faster but xarray eliminates this entire class of bugs by using named dimensions instead of numeric axis indices.
</think>

The confusion stems from what "axis" means in numpy. It does NOT mean "compute along each element of this axis." It means "collapse this axis by aggregating."

**How numpy axes work for a (4, 3) array:**

```
axis=0 is the ROW axis (4 students)
axis=1 is the COLUMN axis (3 tests)

np.mean(scores, axis=0)  -> collapse rows, keep columns  -> shape (3,)
                          -> average ACROSS students for each test
                          -> gives 3 values (one per test)

np.mean(scores, axis=1)  -> collapse columns, keep rows   -> shape (4,)
                          -> average ACROSS tests for each student
                          -> gives 4 values (one per student)
```

**Your corrected code:**

```python
# Average score per student (collapse tests axis)
student_avg = np.mean(scores, axis=1)  # axis=1, not axis=0
print(f"Student averages: {student_avg}")
# [84.33 91.67 79.33 88.67]  -- 4 values, one per student

# Average score per test (collapse students axis)
test_avg = np.mean(scores, axis=0)  # axis=0, not axis=1
print(f"Test averages: {test_avg}")
# [85.25 87.75 85.00]  -- 3 values, one per test
```

**The mental model that helps:**

Think of axis as "the axis that disappears." The result shape is the original shape with the specified axis removed.

```python
scores.shape = (4, 3)

np.mean(scores, axis=0).shape = (3,)     # removed axis 0 (size 4)
np.mean(scores, axis=1).shape = (4,)     # removed axis 1 (size 3)
np.mean(scores, axis=None)               # scalar (removed all axes)
```

**For 3D arrays:**

```python
data = np.random.rand(2, 3, 4)  # shape (2, 3, 4)

np.mean(data, axis=0).shape  # (3, 4)  -- collapsed first dim
np.mean(data, axis=1).shape  # (2, 4)  -- collapsed second dim
np.mean(data, axis=2).shape  # (2, 3)  -- collapsed third dim
np.mean(data, axis=(0,2)).shape  # (3,) -- collapsed first and third dims
```

**Using keepdims for broadcasting:**

```python
# Normalize each student's scores by their mean
student_means = np.mean(scores, axis=1, keepdims=True)  # shape (4, 1)
normalized = scores - student_means  # broadcasts correctly!

# Without keepdims:
# np.mean(scores, axis=1) has shape (4,) which doesn't broadcast
# against (4, 3) the way you want
```

**Prevention tips:**
- Always print `.shape` before and after operations to verify
- Use `keepdims=True` when you need the result for broadcasting
- Name your axes: consider using `xarray` for labeled axes (`dim='students'` instead of `axis=0`)
- Write a comment: `# axis=1: average across tests for each student`
- Use pandas DataFrames with named columns/index when axis semantics matter'''),

    ("thinking/debugging", r'''My pandas merge is producing duplicate rows:

```python
import pandas as pd

orders = pd.DataFrame({
    'order_id': [1, 2, 3],
    'customer_id': [101, 102, 101],
    'amount': [50, 75, 100],
})

customers = pd.DataFrame({
    'customer_id': [101, 101, 102],  # customer 101 appears twice!
    'name': ['Alice', 'Alice Smith', 'Bob'],
})

result = orders.merge(customers, on='customer_id')
print(result)
```

Output:
```
   order_id  customer_id  amount         name
0         1          101      50        Alice
1         1          101      50  Alice Smith
2         3          101     100        Alice
3         3          101     100  Alice Smith
4         2          102      75          Bob
```

Expected 3 rows, got 5. Orders for customer 101 are duplicated because of the duplicate in the customers table.''', r'''<think>
The user expects 3 rows but gets 5 after a merge. This could be a join type issue (left vs inner)... but wait, the row count increased, which points to duplicate keys creating a cartesian product, not a join type problem.

Customer 101 appears twice in the customers DataFrame. When merging, each order for customer 101 is matched with each customer record for 101, creating a cartesian product for that key.

Orders with customer_id 101: 2 rows
Customers with customer_id 101: 2 rows
Result for customer_id 101: 2 * 2 = 4 rows

I considered whether a left join vs inner join would fix this, but that won't work because the issue is duplicate keys, not missing keys. Because the merge is many-to-many (unintentionally), therefore the fix depends on the root cause:
1. If the duplicate is a data quality issue, deduplicate the customers table first
2. If it is intentional (historical names), specify which record to use
3. Use the validate parameter to catch this early -- this is the best defensive practice since it fails fast rather than silently producing wrong results
</think>

The merge produces a cartesian product for any key that appears multiple times in both DataFrames. Customer 101 has 2 orders and 2 customer records, producing 2 x 2 = 4 rows for that customer.

**Understanding merge cardinality:**
```
Orders:    customer_id 101 appears 2 times
Customers: customer_id 101 appears 2 times
Result:    2 * 2 = 4 rows for customer_id 101
```

This is a many-to-many merge, which is almost always unintended.

**Fix 1: Deduplicate the customers table first**

```python
# Keep the first (or last) record per customer
customers_dedup = customers.drop_duplicates(subset='customer_id', keep='last')

result = orders.merge(customers_dedup, on='customer_id')
print(result)
#    order_id  customer_id  amount         name
# 0         1          101      50  Alice Smith
# 1         3          101     100  Alice Smith
# 2         2          102      75          Bob
```

**Fix 2: Use validate parameter to catch duplicates early**

```python
try:
    result = orders.merge(customers, on='customer_id', validate='many_to_one')
except pd.errors.MergeError as e:
    print(f"Merge validation failed: {e}")
    # "Merge keys are not unique in right dataset"
```

The `validate` parameter options:
- `'one_to_one'` (1:1) -- both sides must have unique keys
- `'one_to_many'` (1:N) -- left side must have unique keys
- `'many_to_one'` (N:1) -- right side must have unique keys
- `'many_to_many'` (N:N) -- no validation (default, allows duplicates)

**Fix 3: Aggregate duplicates before merging**

```python
# If you want to combine duplicate customer records
customers_agg = customers.groupby('customer_id').agg({
    'name': 'last',  # or 'first', or lambda x: ' / '.join(x)
}).reset_index()

result = orders.merge(customers_agg, on='customer_id')
```

**Fix 4: Check for duplicates before merging**

```python
def safe_merge(left, right, on, expected='many_to_one', **kwargs):
    """Merge with automatic duplicate detection."""
    left_dupes = left[on].duplicated().sum()
    right_dupes = right[on].duplicated().sum() if isinstance(on, str) else right[on].duplicated().sum()

    if right_dupes > 0 and expected in ('many_to_one', 'one_to_one'):
        print(f"WARNING: {right_dupes} duplicate keys in right DataFrame")
        print(right[right[on].duplicated(keep=False)].sort_values(on))

    return left.merge(right, on=on, validate=expected, **kwargs)
```

**Diagnosing merge issues:**

```python
# Before merging, always check for duplicates in join keys
print(f"Left duplicates: {orders['customer_id'].duplicated().sum()}")
print(f"Right duplicates: {customers['customer_id'].duplicated().sum()}")

# Check the expected vs actual row count
print(f"Left rows: {len(orders)}")
print(f"Right unique keys: {customers['customer_id'].nunique()}")
print(f"Expected result rows (for many-to-one): {len(orders)}")
print(f"Actual result rows: {len(result)}")  # if different, you have duplicates
```

**Prevention tips:**
- Always use `validate=` parameter in production merge calls
- Check `df.duplicated(subset=key_columns).sum()` before merging
- Assert row count after merge: `assert len(result) == len(orders), "Unexpected row count after merge"`
- Use `indicator=True` to see which rows matched: `merge(..., indicator=True)`
- Investigate duplicate keys before merging -- they usually indicate a data quality issue upstream'''),

    ("thinking/debugging", r'''My pandas datetime operations are silently giving wrong results because of timezone issues:

```python
import pandas as pd
from datetime import datetime

# Event timestamps from different sources
events = pd.DataFrame({
    'event': ['login', 'purchase', 'logout'],
    'utc_time': pd.to_datetime(['2024-03-15 10:00:00', '2024-03-15 15:30:00', '2024-03-15 18:00:00']),
    'local_time': pd.to_datetime(['2024-03-15 06:00:00-04:00', '2024-03-15 11:30:00-04:00', '2024-03-15 14:00:00-04:00']),
})

# Calculate time between UTC and local
events['diff'] = events['utc_time'] - events['local_time']
print(events['diff'])
```

Output:
```
0   0 days 08:00:00
1   0 days 08:00:00
2   0 days 08:00:00
```

The difference should be 0 (they represent the same moments in time), but it shows 8 hours!''', r'''<think>
The issue is that `utc_time` is timezone-naive (no timezone info) while `local_time` is timezone-aware (has -04:00 offset). This could be a simple formatting issue... but wait, the 8-hour difference is a clue that something deeper is wrong with how pandas handles mixed timezone types.

When you parse '2024-03-15 10:00:00' without timezone info, pandas creates a naive datetime. When you parse '2024-03-15 06:00:00-04:00', pandas creates a timezone-aware datetime.

Hmm, actually, I need to think carefully about the subtraction behavior. In modern pandas, subtracting tz-aware from tz-naive might raise a TypeError, but some versions handle it silently by stripping timezone info or converting inconsistently. The local_time '06:00:00-04:00' when stored internally as UTC is 10:00:00 UTC, but the naive '10:00:00' has no timezone context.

I considered trying to trace the exact conversion path to explain the 8-hour result, but the exact behavior depends on the pandas version and internal representation. Wait, I need to reconsider -- the important point is not the precise arithmetic but the root cause: mixing tz-aware and tz-naive datetimes produces version-dependent, unreliable behavior. Because the fundamental issue is inconsistent timezone handling, therefore the fix is to make both columns consistently timezone-aware rather than trying to predict the coercion rules.

The tradeoff is between using `tz_localize` (which marks a naive timestamp as belonging to a specific timezone without changing the value) vs `tz_convert` (which shifts the time). The user should use `tz_localize('UTC')` on the naive column since those timestamps are already in UTC.
</think>

The problem is mixing timezone-naive and timezone-aware datetimes. `utc_time` has no timezone information (naive), while `local_time` has explicit timezone offset (-04:00). When pandas performs arithmetic between them, it handles the timezone information inconsistently, leading to wrong results.

**What is happening:**

```python
events['utc_time'].dtype    # datetime64[ns]       (no timezone)
events['local_time'].dtype  # datetime64[ns, UTC]   (timezone-aware, converted to UTC)
```

Pandas internally converts timezone-aware timestamps to UTC for storage. So `'06:00:00-04:00'` becomes `'10:00:00+00:00'` internally. But the naive `utc_time` is stored as-is with no timezone context. When subtracting, pandas compares the raw numeric values, producing meaningless results.

**Fix: Make all timestamps consistently timezone-aware**

```python
import pandas as pd

events = pd.DataFrame({
    'event': ['login', 'purchase', 'logout'],
    'utc_time': pd.to_datetime([
        '2024-03-15 10:00:00',
        '2024-03-15 15:30:00',
        '2024-03-15 18:00:00'
    ]).tz_localize('UTC'),  # explicitly mark as UTC
    'local_time': pd.to_datetime([
        '2024-03-15 06:00:00-04:00',
        '2024-03-15 11:30:00-04:00',
        '2024-03-15 14:00:00-04:00',
    ]),
})

events['diff'] = events['utc_time'] - events['local_time']
print(events['diff'])
# 0   0 days 00:00:00
# 1   0 days 00:00:00
# 2   0 days 00:00:00
```

**Key datetime operations:**

```python
# Localize naive timestamps (assign timezone without converting)
naive_ts = pd.to_datetime('2024-03-15 10:00:00')
utc_ts = naive_ts.tz_localize('UTC')
# Result: 2024-03-15 10:00:00+00:00

# Convert between timezones
eastern_ts = utc_ts.tz_convert('US/Eastern')
# Result: 2024-03-15 06:00:00-04:00

# For a Series/column:
events['utc_time'] = events['utc_time'].dt.tz_localize('UTC')
events['eastern_time'] = events['utc_time'].dt.tz_convert('US/Eastern')
```

**Common timezone pitfalls:**

```python
# WRONG: tz_convert on naive datetime (raises error)
naive_series.dt.tz_convert('US/Eastern')  # TypeError!

# WRONG: tz_localize on already-localized datetime (raises error)
aware_series.dt.tz_localize('UTC')  # TypeError!

# RIGHT: check if timezone-aware first
if series.dt.tz is None:
    series = series.dt.tz_localize('UTC')
else:
    series = series.dt.tz_convert('UTC')
```

**DST (Daylight Saving Time) traps:**

```python
# This timestamp is ambiguous during fall-back
ts = pd.Timestamp('2024-11-03 01:30:00', tz='US/Eastern')
# Is it EDT (01:30-04:00) or EST (01:30-05:00)?

# Be explicit:
ts = pd.Timestamp('2024-11-03 01:30:00').tz_localize(
    'US/Eastern', ambiguous=False  # or ambiguous=True
)
```

**Prevention tips:**
- Store ALL timestamps as UTC in your database
- Convert to local timezone only for display purposes
- Always use `tz_localize` when creating timestamps -- never leave them naive
- Use `pd.Timestamp.utcnow()` instead of `pd.Timestamp.now()`
- Add assertions in your data pipeline: `assert df['ts'].dt.tz is not None`
- Use the `pytz` or `zoneinfo` library for timezone definitions'''),
]
