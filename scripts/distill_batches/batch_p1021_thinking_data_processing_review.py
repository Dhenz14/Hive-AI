"""Thinking-trace code review pairs: data processing (pandas, CSV, ETL, validation, batch)."""

PAIRS = [
    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
import pandas as pd

def prepare_sales_report(input_file: str, output_file: str):
    df = pd.read_csv(input_file)

    # Clean data
    df = df.dropna()
    df = df[df['amount'] > 0]
    df = df.drop_duplicates()

    # Convert dates
    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.to_period('M').astype(str)

    # Calculate metrics per region
    df['amount_usd'] = df.apply(
        lambda row: row['amount'] * get_exchange_rate(row['currency']),
        axis=1
    )

    # Aggregate
    summary = df.groupby(['region', 'month']).agg(
        total=('amount_usd', 'sum'),
        count=('amount_usd', 'count'),
        avg=('amount_usd', 'mean'),
    ).reset_index()

    summary = summary.sort_values(['region', 'month'])

    # Add running totals
    for region in summary['region'].unique():
        mask = summary['region'] == region
        summary.loc[mask, 'running_total'] = summary.loc[mask, 'total'].cumsum()

    summary.to_csv(output_file, index=False)
    return summary
```''',
        r'''<think>
Let me analyze this pandas pipeline for a sales report.

First read: reads a CSV, cleans data, converts currencies, aggregates by region/month, adds running totals, writes output. Straightforward ETL.

**Memory issues — the main performance problem:**

Every operation creates a full copy of the DataFrame:
- `df = df.dropna()` — copy
- `df = df[df['amount'] > 0]` — copy
- `df = df.drop_duplicates()` — copy

For a large file (millions of rows), this means 4x the memory at peak (original + 3 intermediate copies). With a 2GB CSV, you need 8GB+ RAM.

**The `apply` with `axis=1` is the worst bottleneck:**
`df.apply(lambda row: ..., axis=1)` is a Python-speed row-by-row loop disguised as a pandas call. It's 100-1000x slower than vectorized operations. For 10 million rows, this could take minutes instead of seconds.

If `get_exchange_rate` makes a network call per row, this is catastrophically slow — 10 million HTTP requests.

**Silent data loss with `dropna()`:**
`df.dropna()` drops rows where ANY column is null. If a row has a valid amount but a missing optional field like `notes`, it gets dropped. This silently reduces your dataset. You should only drop rows where critical columns are null.

**Other issues:**
- `drop_duplicates()` with no subset specified deduplicates on ALL columns. Two legitimate sales with identical values get merged into one.
- No dtype specification on `read_csv` — pandas guesses types, which is slow and sometimes wrong
- The running total loop with `mask` indexing is slow; `groupby().cumsum()` is faster
- No input validation (what if the file has wrong columns?)
- `to_csv` without float format — amounts might show as 1234.5678901234

Priority: the `apply` loop is the performance killer. Silent data loss from aggressive `dropna` is the correctness issue. Memory copies matter at scale.
</think>

## Code Review

### Critical Issues

**Silent data loss with `dropna()` (Severity: High)**

`df.dropna()` drops any row with ANY null value in ANY column. If your CSV has 20 columns and a row has a valid sale but a missing `notes` or `customer_phone`, that entire sale vanishes from the report. You should only drop rows where business-critical columns are null.

**Overly aggressive `drop_duplicates()` (Severity: Medium)**

With no `subset` parameter, this deduplicates on ALL columns. Two legitimate sales with the same amount, date, region, and currency are merged into one. Sales data frequently has genuine duplicates — you need a unique transaction ID to deduplicate safely.

### Performance

**`apply(axis=1)` is a Python loop (Severity: High)**

```python
df['amount_usd'] = df.apply(
    lambda row: row['amount'] * get_exchange_rate(row['currency']), axis=1
)
```

This iterates row-by-row in Python. For 1M rows, this is ~100x slower than a vectorized approach. If `get_exchange_rate` makes a network call, it's 1M network round trips.

The fix: build a currency-to-rate mapping once, then merge or map it vectorially.

**Excessive memory copies**: Each filter/clean operation creates a full DataFrame copy. Chain operations or use `inplace` strategically.

**Running total loop**: The `for region in unique()` loop with boolean masking is slow. `groupby().cumsum()` does this in one vectorized call.

### Refactored Code

```python
import pandas as pd
from typing import Optional

# Build exchange rate lookup ONCE (cache, don't call per-row)
EXCHANGE_RATES = {
    'USD': 1.0, 'EUR': 1.08, 'GBP': 1.27, 'JPY': 0.0067,
    # ... load from config/API once at startup
}

REQUIRED_COLUMNS = {'date', 'amount', 'currency', 'region'}


def prepare_sales_report(
    input_file: str,
    output_file: str,
    exchange_rates: Optional[dict] = None,
) -> pd.DataFrame:
    rates = exchange_rates or EXCHANGE_RATES

    # Specify dtypes upfront — faster parsing, less memory
    df = pd.read_csv(
        input_file,
        dtype={
            'amount': 'float64',
            'currency': 'category',   # low cardinality → huge memory savings
            'region': 'category',
        },
        parse_dates=['date'],         # parse dates during read, not after
        usecols=lambda c: c.strip(),  # handle whitespace in headers
    )

    # Validate required columns exist
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Drop only rows with null CRITICAL fields (not all nulls)
    df = df.dropna(subset=['date', 'amount', 'currency', 'region'])

    # Filter in one step to minimize copies
    df = df.loc[
        (df['amount'] > 0) &
        (df['currency'].isin(rates.keys()))
    ].copy()  # single explicit copy

    if df.empty:
        raise ValueError("No valid records after filtering")

    # Deduplicate on transaction_id if available, otherwise log a warning
    if 'transaction_id' in df.columns:
        df = df.drop_duplicates(subset=['transaction_id'])

    # Vectorized currency conversion — NO apply(), NO per-row function calls
    rate_series = df['currency'].map(rates)
    df['amount_usd'] = df['amount'] * rate_series

    df['month'] = df['date'].dt.to_period('M').astype(str)

    # Aggregate
    summary = (
        df.groupby(['region', 'month'], observed=True)
        .agg(
            total=('amount_usd', 'sum'),
            count=('amount_usd', 'count'),
            avg=('amount_usd', 'mean'),
        )
        .reset_index()
        .sort_values(['region', 'month'])
    )

    # Running total — vectorized groupby cumsum, no loop
    summary['running_total'] = summary.groupby('region')['total'].cumsum()

    summary.to_csv(output_file, index=False, float_format='%.2f')
    return summary
```

### Key Changes Summary

| Before | After |
|--------|-------|
| `dropna()` on all columns — silent data loss | `dropna(subset=[critical columns])` |
| `drop_duplicates()` on all columns | Deduplicate on `transaction_id` if available |
| `apply(axis=1)` Python loop for currency conversion | Vectorized `map()` + multiplication |
| 3 separate filter steps = 3 copies | Combined filter in one `.loc[]` call |
| No dtype hints — pandas guesses | Explicit dtypes + `category` for low-cardinality |
| Date parsing in separate step | `parse_dates` in `read_csv` |
| Running total loop with mask | `groupby().cumsum()` |
| No input validation | Column existence check + empty result check |
| Unformatted float output | `float_format='%.2f'` |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
import csv
import sqlite3

def import_csv_to_db(csv_file: str, db_path: str, table_name: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        placeholders = ', '.join(['?'] * len(columns))
        col_names = ', '.join(columns)

        cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(c + ' TEXT' for c in columns)})")

        for row in reader:
            values = [row[c] for c in columns]
            cursor.execute(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})", values)

    conn.commit()
    conn.close()
```''',
        r'''<think>
Let me analyze this CSV-to-SQLite import function.

First read: reads a CSV file, creates a table with TEXT columns matching the headers, inserts rows one at a time.

**SQL injection via CSV headers (Severity: Critical):**

The `table_name` parameter is interpolated directly into SQL. But even worse: the CSV column NAMES (from `reader.fieldnames`) are interpolated into both the CREATE TABLE and INSERT statements without any sanitization.

An attacker can craft a CSV with a header like:
```
name, email); DROP TABLE users; --
```

This would produce:
```sql
CREATE TABLE IF NOT EXISTS data (name TEXT, email); DROP TABLE users; -- TEXT)
```

The column names come from untrusted input (the CSV file). You cannot parameterize column names or table names with `?` — they need to be validated/sanitized manually.

**Performance — row-by-row inserts:**

Each row is a separate `cursor.execute` + implicit transaction. For a 1-million row CSV, this is 1M individual INSERT statements. SQLite can do ~50K inserts/sec with individual statements, but ~500K/sec with `executemany` and a single transaction. This is 10x slower than it needs to be.

**Resource management:**

- `conn.close()` is not in a `finally` block. If any exception occurs during processing, the connection leaks.
- No `with` statement for the connection.
- If the CSV is malformed (mismatched columns), the error is cryptic.

**Data type issues:**

All columns are `TEXT`. If the CSV has numeric data, it's stored as text. Queries like `WHERE amount > 100` will do string comparison, not numeric. While this might be intentional for a generic importer, it should at least be documented.

**Other issues:**
- No handling of duplicate rows (no UNIQUE constraint, no ON CONFLICT)
- No progress indication for large files
- The file is read entirely with DictReader — fine for memory since it's an iterator, but DictReader is slower than regular reader

Priority: SQL injection via headers is the security killer. Row-by-row inserts is the performance killer. Missing error handling/cleanup is the reliability issue.
</think>

## Code Review

### Critical Issues

**SQL injection via CSV column headers (Severity: Critical)**

Column names from `reader.fieldnames` are interpolated directly into SQL:

```python
cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(c + ' TEXT' for c in columns)})")
```

A malicious CSV with a header like `id); DROP TABLE users; --` results in arbitrary SQL execution. Column names and table names cannot be parameterized with `?` in SQLite — they must be validated manually.

The `table_name` parameter is similarly injectable.

**No resource cleanup on error (Severity: Medium)**

If an exception occurs during CSV processing, `conn.commit()` and `conn.close()` are never called. The connection leaks, and any partially inserted data is left in an ambiguous state (auto-committed in some SQLite configurations).

### Performance

**Row-by-row inserts**: Each `cursor.execute` inside the loop is an individual statement. For large files, `executemany` with batching is 10x faster. SQLite's journaling overhead per-statement is significant.

### Refactored Code

```python
import csv
import re
import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Only allow alphanumeric + underscore in identifiers
SAFE_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
BATCH_SIZE = 5000


def _validate_identifier(name: str) -> str:
    """Prevent SQL injection in table/column names.
    Identifiers can't be parameterized, so we must validate manually."""
    cleaned = name.strip()
    if not SAFE_IDENTIFIER.match(cleaned):
        raise ValueError(
            f"Unsafe SQL identifier: {cleaned!r}. "
            "Only alphanumeric characters and underscores are allowed."
        )
    return cleaned


def import_csv_to_db(
    csv_file: str,
    db_path: str,
    table_name: str,
    batch_size: int = BATCH_SIZE,
    if_exists: str = "append",  # "append", "replace", or "fail"
) -> int:
    """Import a CSV file into a SQLite table. Returns row count.

    Args:
        csv_file: path to CSV file
        db_path: path to SQLite database
        table_name: target table name (alphanumeric + underscore only)
        batch_size: rows per INSERT batch (default 5000)
        if_exists: behavior if table exists — "append", "replace", or "fail"
    """
    safe_table = _validate_identifier(table_name)
    total_rows = 0

    with sqlite3.connect(db_path) as conn:  # auto-closes, auto-rollback on error
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")  # better concurrent write perf

        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            if not reader.fieldnames:
                raise ValueError(f"CSV file {csv_file} has no headers")

            # Validate EVERY column name against injection
            safe_columns = [_validate_identifier(c) for c in reader.fieldnames]

            # Handle existing table
            if if_exists == "replace":
                cursor.execute(f"DROP TABLE IF EXISTS [{safe_table}]")
            elif if_exists == "fail":
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (safe_table,),
                )
                if cursor.fetchone():
                    raise ValueError(f"Table {safe_table} already exists")

            # Create table with validated column names
            col_defs = ', '.join(f'[{c}] TEXT' for c in safe_columns)
            cursor.execute(f"CREATE TABLE IF NOT EXISTS [{safe_table}] ({col_defs})")

            # Batch insert with executemany — 10x faster than row-by-row
            placeholders = ', '.join(['?'] * len(safe_columns))
            insert_sql = (
                f"INSERT INTO [{safe_table}] "
                f"({', '.join(f'[{c}]' for c in safe_columns)}) "
                f"VALUES ({placeholders})"
            )

            batch = []
            for row_num, row in enumerate(reader, start=2):  # line 2 = first data row
                try:
                    values = [row.get(c, None) for c in reader.fieldnames]
                    batch.append(values)
                except Exception as e:
                    logger.warning("Skipping malformed row %d: %s", row_num, e)
                    continue

                if len(batch) >= batch_size:
                    cursor.executemany(insert_sql, batch)
                    total_rows += len(batch)
                    batch.clear()
                    logger.debug("Imported %d rows so far", total_rows)

            # Insert remaining rows
            if batch:
                cursor.executemany(insert_sql, batch)
                total_rows += len(batch)

        conn.commit()

    logger.info("Imported %d rows into %s", total_rows, safe_table)
    return total_rows
```

### Key Changes Summary

| Before | After |
|--------|-------|
| Column names interpolated unsanitized — SQL injection | Regex validation + bracket quoting for all identifiers |
| Table name injectable | Validated with `_validate_identifier()` |
| Row-by-row `execute` | Batched `executemany` (5000 rows at a time) |
| `conn.close()` not in finally | `with sqlite3.connect()` — auto-close + auto-rollback |
| No error handling for malformed rows | try/except per row with logging |
| No return value | Returns total imported row count |
| No encoding specified | Explicit `utf-8` encoding |
| Silent behavior on existing table | `if_exists` parameter: append/replace/fail |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
import os
import json
import psycopg2
from datetime import datetime

def run_daily_etl():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cursor = conn.cursor()

    # Step 1: Extract raw events from source
    cursor.execute("SELECT * FROM raw_events WHERE processed = false")
    events = cursor.fetchall()

    # Step 2: Transform
    transformed = []
    for event in events:
        data = json.loads(event[3])  # column index 3 is json_payload
        transformed.append({
            'event_type': event[1],
            'user_id': data['user_id'],
            'amount': float(data['amount']),
            'timestamp': datetime.fromisoformat(event[2]),
            'metadata': data.get('metadata', {}),
        })

    # Step 3: Load into analytics table
    for record in transformed:
        cursor.execute(
            "INSERT INTO analytics_events (event_type, user_id, amount, event_time, metadata) "
            "VALUES (%s, %s, %s, %s, %s)",
            (record['event_type'], record['user_id'], record['amount'],
             record['timestamp'], json.dumps(record['metadata']))
        )

    # Step 4: Mark as processed
    for event in events:
        cursor.execute("UPDATE raw_events SET processed = true WHERE id = %s", (event[0],))

    conn.commit()
    conn.close()
    print(f"Processed {len(events)} events")
```''',
        r'''<think>
Let me analyze this ETL script that processes raw events into an analytics table.

First read: extracts unprocessed events, transforms JSON payloads, loads into analytics table, marks source records as processed. Classic ETL pattern.

**No error recovery — the catastrophic problem:**

If this script fails at Step 3 (say, on event #5000 of 10000), nothing is committed. But the next run will re-process all 10000 events because none were marked processed. That seems okay at first — but what if the failure was a data issue in event #5000? The script will fail at the same event forever, blocking ALL subsequent events behind it.

Even worse: `fetchall()` loads ALL unprocessed events into memory. If the system was down for a week and there are 50 million events, this OOMs the process.

**No atomicity between load and mark-processed:**

Steps 3 and 4 are in the same transaction, which is good. But if the process crashes after `conn.commit()` but before the script completes... well, that's fine actually since everything committed. The real issue is the opposite: if the process crashes DURING step 3, none of the marks happen, and we re-process everything.

For idempotency, we need either:
- A unique constraint on analytics_events to prevent duplicate inserts on retry
- Or batch processing with checkpointing

**Accessing columns by index:**
`event[3]`, `event[1]`, `event[2]`, `event[0]` — this is fragile. If someone adds a column to raw_events or changes the column order, all indices break silently (wrong data, not an error).

**Performance issues:**
- `SELECT *` fetches all columns including potentially large ones we don't need
- `fetchall()` loads everything into memory at once
- Row-by-row INSERT in step 3
- Row-by-row UPDATE in step 4
- No batching or chunking

**Other:**
- `print()` instead of logging
- No monitoring/alerting on failure
- `json.loads` can throw on malformed JSON — no handling
- `float(data['amount'])` can throw on non-numeric values
- `data['user_id']` throws KeyError if missing
- No connection cleanup on error (not using context manager)

Priority: lack of error recovery/checkpointing is the operational killer. Memory bomb from fetchall is the scalability issue. Column-by-index access is the maintainability trap.
</think>

## Code Review

### Critical Issues

**No error recovery — one bad event blocks everything (Severity: Critical)**

If event #5000 has malformed JSON or a missing `user_id` field, the entire batch of 10,000+ events fails. On the next run, it tries the same 10,000 events and fails at #5000 again. Forever. The pipeline is permanently stuck.

There is no mechanism to skip bad records, no dead-letter queue, no checkpointing.

**Memory bomb with `fetchall()` (Severity: High)**

`cursor.fetchall()` loads ALL unprocessed events into memory at once. If the pipeline was down for a day and 10 million events accumulated, this consumes gigabytes of RAM and may OOM-kill the process. Use server-side cursors or `LIMIT`-based batching.

**No idempotency on retry (Severity: High)**

If the script crashes after inserting some analytics records but before committing the processed flags, the retry inserts duplicates. There is no `ON CONFLICT` clause or unique constraint to prevent double-counting in analytics.

### Maintainability

**Column access by index**: `event[3]`, `event[0]` — impossible to understand without knowing the table schema. If columns are reordered or added, this breaks silently with wrong data.

### Refactored Code

```python
import os
import json
import logging
from datetime import datetime
from typing import Iterator

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def run_daily_etl():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    total_processed = 0
    total_failed = 0

    try:
        while True:
            batch_count, fail_count = _process_batch(conn, BATCH_SIZE)
            total_processed += batch_count
            total_failed += fail_count

            if batch_count == 0:
                break  # no more unprocessed events

            logger.info(
                "Batch complete: %d processed, %d failed, %d total so far",
                batch_count, fail_count, total_processed,
            )

    except Exception:
        logger.exception("ETL pipeline failed after %d events", total_processed)
        raise
    finally:
        conn.close()

    logger.info(
        "ETL complete: %d processed, %d failed",
        total_processed, total_failed,
    )


def _process_batch(conn, batch_size: int) -> tuple[int, int]:
    """Process one batch. Returns (success_count, failure_count)."""
    processed_count = 0
    failed_count = 0

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        # Explicit columns, LIMIT for bounded memory, FOR UPDATE to prevent
        # concurrent processing, SKIP LOCKED for parallel workers
        cursor.execute(
            "SELECT id, event_type, created_at, json_payload "
            "FROM raw_events "
            "WHERE processed = false "
            "ORDER BY id "
            "LIMIT %s "
            "FOR UPDATE SKIP LOCKED",
            (batch_size,),
        )
        events = cursor.fetchall()

        if not events:
            return 0, 0

        analytics_rows = []
        processed_ids = []
        failed_ids = []

        for event in events:
            try:
                record = _transform_event(event)
                analytics_rows.append(record)
                processed_ids.append(event['id'])
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(
                    "Skipping bad event %s: %s", event['id'], e
                )
                failed_ids.append(event['id'])
                failed_count += 1

        # Bulk insert with ON CONFLICT for idempotency
        if analytics_rows:
            psycopg2.extras.execute_values(
                cursor,
                "INSERT INTO analytics_events "
                "(event_type, user_id, amount, event_time, metadata, source_event_id) "
                "VALUES %s "
                "ON CONFLICT (source_event_id) DO NOTHING",
                [
                    (r['event_type'], r['user_id'], r['amount'],
                     r['timestamp'], json.dumps(r['metadata']), r['source_id'])
                    for r in analytics_rows
                ],
            )

        # Mark successful events as processed
        all_handled = processed_ids + failed_ids
        if all_handled:
            cursor.execute(
                "UPDATE raw_events SET processed = true, processed_at = NOW() "
                "WHERE id = ANY(%s)",
                (all_handled,),
            )
            processed_count = len(processed_ids)

    conn.commit()
    return processed_count, failed_count


def _transform_event(event) -> dict:
    """Transform a raw event. Raises on bad data (caller handles)."""
    data = json.loads(event['json_payload'])
    return {
        'event_type': event['event_type'],
        'user_id': data['user_id'],
        'amount': float(data['amount']),
        'timestamp': datetime.fromisoformat(event['created_at']),
        'metadata': data.get('metadata', {}),
        'source_id': event['id'],
    }
```

### Key Changes Summary

| Before | After |
|--------|-------|
| `fetchall()` on unbounded query — OOM risk | `LIMIT`-based batching with configurable batch size |
| One bad event blocks entire pipeline | Per-event try/except, bad events logged and skipped |
| No idempotency — duplicates on retry | `ON CONFLICT (source_event_id) DO NOTHING` |
| Row-by-row INSERT and UPDATE | `execute_values` bulk insert + `ANY(%s)` bulk update |
| Column access by index `event[3]` | `DictCursor` with named access `event['json_payload']` |
| `print()` statement | Structured logging with counts |
| No connection cleanup on failure | `try/finally` with `conn.close()` |
| No `SELECT ... FOR UPDATE` | `FOR UPDATE SKIP LOCKED` for safe concurrent workers |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
from dataclasses import dataclass
from typing import Any
import re

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]

def validate_user_input(data: dict[str, Any]) -> ValidationResult:
    errors = []

    # Name validation
    if 'name' in data:
        if len(data['name']) < 2:
            errors.append("Name too short")

    # Email validation
    if 'email' in data:
        if not re.match(r'.+@.+\..+', data['email']):
            errors.append("Invalid email")

    # Age validation
    if 'age' in data:
        try:
            age = int(data['age'])
            if age < 0 or age > 150:
                errors.append("Age out of range")
        except ValueError:
            pass

    # Phone validation
    if 'phone' in data:
        phone = re.sub(r'[^0-9]', '', data['phone'])
        if len(phone) < 10:
            errors.append("Phone too short")

    # Address validation
    if 'address' in data:
        addr = data['address']
        if not addr.get('street'):
            pass
        if not addr.get('city'):
            pass

    return ValidationResult(valid=len(errors) == 0, errors=errors)
```''',
        r'''<think>
Let me analyze this validation function carefully.

First read: validates a user input dictionary with optional fields — name, email, age, phone, address. Returns a ValidationResult with errors.

**Silent failures — the fundamental design flaw:**

This validator silently passes on invalid data in multiple places:

1. `except ValueError: pass` — if age is "abc", it catches the error and... does nothing. The invalid age is silently accepted as valid. No error is added to the list.

2. Address validation: `if not addr.get('street'): pass` — literally does nothing. This is dead code. Missing street and city are silently accepted.

3. All fields are optional: if the input dict is `{}`, it returns `valid=True` with no errors. For user creation, you probably need at least name and email.

4. If `data['name']` is `None` (not missing, but None), `len(None)` throws `TypeError`. The validator crashes instead of reporting an error.

**Weak email validation:**
`r'.+@.+\..+'` matches `"@a.b"`, `"x@.."`, `"@@a.b"` — almost anything with an @ and a dot. It also doesn't check for maximum length, which matters for SQL columns.

**Type safety issues:**
- No check that `data['name']` is actually a string. If it's a list or int, `len()` works but means something different.
- `data['phone']` — no check it's a string before calling `re.sub`
- `data['address']` — no check it's a dict before calling `.get()`

**Missing validations:**
- No max length on name (SQL injection or storage issues)
- No email normalization (upper/lowercase)
- No phone format validation beyond "has 10+ digits"
- No sanitization of any input

Priority: silent failures are the worst because they give a false sense of safety. The dead code in address validation suggests this was written hastily. The email regex gives an illusion of validation.
</think>

## Code Review

### Critical Issues

**Silent failure on invalid data (Severity: Critical)**

Multiple validation branches silently accept bad data:

```python
except ValueError:
    pass  # age = "abc" is silently accepted as valid!

if not addr.get('street'):
    pass  # missing street? That's fine apparently
```

The `except ValueError: pass` on age means non-numeric ages pass validation. The address block is literally dead code — the `pass` statements do nothing. A validator that silently accepts invalid data is worse than no validator, because it gives false confidence.

**No required field checking (Severity: High)**

An empty dict `{}` returns `ValidationResult(valid=True, errors=[])`. If this validates user registration data, you can create a user with no name, no email, no nothing.

**Type confusion crashes (Severity: Medium)**

If `data['name']` is `None` instead of a missing key, `len(None)` raises `TypeError`. The `if 'name' in data` check passes (key exists), but the value isn't a string. Same for phone, address, etc.

### Weak Validation

**Email regex `r'.+@.+\..+'`** matches:
- `"@@a.b"` (multiple @)
- `"x@.."` (empty domain parts)
- `"a very long string with spaces@a.b"` (spaces in email)

### Refactored Code

```python
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Reasonably strict email regex (not perfect, but catches obvious problems)
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)
PHONE_PATTERN = re.compile(r'^\+?[0-9\s\-().]{10,20}$')


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def add_error(self, field_name: str, message: str):
        self.errors.append(f"{field_name}: {message}")
        self.valid = False


def validate_user_input(
    data: dict[str, Any],
    required_fields: Optional[set[str]] = None,
) -> ValidationResult:
    """Validate user input data. Reports ALL problems, never silently passes."""
    if required_fields is None:
        required_fields = {'name', 'email'}

    result = ValidationResult(valid=True)

    # Check required fields first
    for field_name in required_fields:
        if field_name not in data or data[field_name] is None:
            result.add_error(field_name, "is required")

    # Name validation
    if 'name' in data and data['name'] is not None:
        if not isinstance(data['name'], str):
            result.add_error('name', "must be a string")
        elif len(data['name'].strip()) < 2:
            result.add_error('name', "must be at least 2 characters")
        elif len(data['name']) > 200:
            result.add_error('name', "must be at most 200 characters")

    # Email validation
    if 'email' in data and data['email'] is not None:
        if not isinstance(data['email'], str):
            result.add_error('email', "must be a string")
        else:
            email = data['email'].strip().lower()
            if len(email) > 254:  # RFC 5321 limit
                result.add_error('email', "exceeds maximum length")
            elif not EMAIL_PATTERN.match(email):
                result.add_error('email', "is not a valid email address")

    # Age validation — NEVER silently accept bad values
    if 'age' in data and data['age'] is not None:
        try:
            age = int(data['age'])
            if age < 0:
                result.add_error('age', "cannot be negative")
            elif age > 150:
                result.add_error('age', "is unrealistically large")
        except (ValueError, TypeError):
            result.add_error('age', "must be a valid integer")

    # Phone validation
    if 'phone' in data and data['phone'] is not None:
        if not isinstance(data['phone'], str):
            result.add_error('phone', "must be a string")
        else:
            digits = re.sub(r'[^0-9]', '', data['phone'])
            if len(digits) < 10:
                result.add_error('phone', "must have at least 10 digits")
            elif len(digits) > 15:  # ITU-T E.164 max
                result.add_error('phone', "has too many digits")

    # Address validation — actually validate, don't just `pass`
    if 'address' in data and data['address'] is not None:
        if not isinstance(data['address'], dict):
            result.add_error('address', "must be an object")
        else:
            addr = data['address']
            if not addr.get('street') or not isinstance(addr['street'], str):
                result.add_error('address.street', "is required")
            if not addr.get('city') or not isinstance(addr['city'], str):
                result.add_error('address.city', "is required")
            if 'zip' in addr and addr['zip'] is not None:
                zip_code = str(addr['zip']).strip()
                if not re.match(r'^[0-9A-Za-z\s\-]{3,10}$', zip_code):
                    result.add_error('address.zip', "is not a valid format")

    return result
```

### Key Changes Summary

| Before | After |
|--------|-------|
| `except ValueError: pass` — silent acceptance | Always adds an error: `"must be a valid integer"` |
| Address validation with `pass` (dead code) | Actually validates street, city, zip |
| No required fields | `required_fields` parameter, defaults to name + email |
| `None` values crash with `TypeError` | Explicit `is not None` checks before processing |
| Email regex matches almost anything | Stricter pattern + length limit (RFC 5321) |
| No type checking on values | `isinstance` checks before string operations |
| No max length on any field | Length limits on name (200), email (254), phone (15 digits) |
| Error messages are generic strings | `"field_name: message"` format for programmatic use |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
import os
import glob
import gzip
import json
from datetime import datetime

def process_log_files(input_dir: str, output_dir: str):
    files = glob.glob(os.path.join(input_dir, '*.log.gz'))
    results = {}

    for filepath in files:
        with gzip.open(filepath, 'rt') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    date = entry['timestamp'][:10]
                    level = entry['level']
                    service = entry['service']

                    key = (date, service)
                    if key not in results:
                        results[key] = {'errors': 0, 'warnings': 0, 'total': 0}

                    results[key]['total'] += 1
                    if level == 'ERROR':
                        results[key]['errors'] += 1
                    elif level == 'WARN':
                        results[key]['warnings'] += 1
                except:
                    continue

    # Write output
    for (date, service), counts in results.items():
        filename = f"{date}_{service}.json"
        output_path = os.path.join(output_dir, filename)
        with open(output_path, 'w') as f:
            json.dump(counts, f)

    print(f"Processed {len(files)} files, {len(results)} groups")
```''',
        r'''<think>
Let me analyze this log file batch processor.

First read: reads compressed JSON log files (one JSON object per line), aggregates counts by date+service, writes per-group output files.

**Bare `except:` — swallowing ALL errors (Severity: Critical):**

```python
except:
    continue
```

This catches EVERYTHING: `KeyboardInterrupt`, `MemoryError`, `SystemExit`, corrupted data, encoding errors. If half the log files are corrupted, you get silently wrong results with no indication. You cannot even Ctrl+C out of the script because `KeyboardInterrupt` is caught.

At minimum this should be `except (json.JSONDecodeError, KeyError, ValueError)`. But even better, it should count and report skipped lines.

**No progress tracking:**

For a directory with hundreds of multi-gigabyte log files, this runs silently for hours. No progress indication, no estimate of completion, no way to know if it's stuck.

**Filename injection:**

`service = entry['service']` is used directly in the output filename: `f"{date}_{service}.json"`. If a service name is `"../../etc/cron.d/evil"`, this writes outside the output directory. Path traversal attack via log data.

**Memory:**

The `results` dict grows unbounded. If there are thousands of unique (date, service) combinations across years of logs, this is fine. But if service names are user-controlled or include unique IDs, memory grows without bound.

**Other issues:**
- No output directory creation (`os.makedirs`)
- Files are processed sequentially — embarrassingly parallel workload
- `glob.glob` sorts arbitrarily; no deterministic processing order
- `print()` instead of logging
- No handling of partially written gzip files (truncated)
- Output files are overwritten without warning if re-run
- No checksums or record counts in output for verification

Priority: bare except is the reliability/debuggability killer. Path traversal is the security issue. No progress tracking is the operational issue.
</think>

## Code Review

### Critical Issues

**Bare `except:` swallows all errors (Severity: Critical)**

```python
except:
    continue
```

This catches everything including `KeyboardInterrupt`, `MemoryError`, and `SystemExit`. You cannot Ctrl+C this script. If log files are corrupted, half-parsed, or the JSON schema changes, every error is silently ignored. You get incomplete results with no indication anything went wrong.

**Path traversal via service name (Severity: High)**

The `service` field from log data is used directly in the output filename:
```python
filename = f"{date}_{service}.json"
```

A log entry with `"service": "../../etc/cron.d/pwned"` writes outside the output directory. Log data is untrusted input — it could come from compromised services or user-controlled fields.

### Operational Issues

**No progress tracking**: Processing hundreds of multi-GB gzip files takes hours. There is no indication of progress, no ETA, no way to distinguish "working" from "stuck." If the process is killed after 3 hours, there is no way to resume — it starts over.

**No output directory creation**: If `output_dir` doesn't exist, every `open()` in the output loop fails.

### Refactored Code

```python
import os
import glob
import gzip
import json
import logging
import re
import time
from collections import defaultdict
from typing import Iterator

logger = logging.getLogger(__name__)

SAFE_NAME = re.compile(r'^[a-zA-Z0-9_\-]+$')


def _sanitize_component(value: str) -> str:
    """Sanitize a string for use in filenames. Prevent path traversal."""
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '_', value)
    return cleaned[:100]  # cap length


def _process_single_file(filepath: str) -> tuple[dict, int, int]:
    """Process one gzip log file. Returns (counts_dict, line_count, error_count)."""
    counts = defaultdict(lambda: {'errors': 0, 'warnings': 0, 'total': 0})
    lines_processed = 0
    lines_skipped = 0

    try:
        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    entry = json.loads(line)
                    date = entry['timestamp'][:10]
                    level = entry['level']
                    service = entry['service']

                    key = (_sanitize_component(date), _sanitize_component(service))
                    counts[key]['total'] += 1
                    if level == 'ERROR':
                        counts[key]['errors'] += 1
                    elif level in ('WARN', 'WARNING'):
                        counts[key]['warnings'] += 1
                    lines_processed += 1

                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    lines_skipped += 1
                    if lines_skipped <= 10:  # log first 10, then stop spamming
                        logger.warning(
                            "%s line %d: %s", os.path.basename(filepath), line_num, e
                        )
    except (gzip.BadGzipFile, EOFError) as e:
        logger.error("Corrupted gzip file %s: %s", filepath, e)

    return dict(counts), lines_processed, lines_skipped


def process_log_files(input_dir: str, output_dir: str) -> dict:
    """Process compressed JSON log files and write per-date-service summaries.

    Returns summary stats dict.
    """
    os.makedirs(output_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(input_dir, '*.log.gz')))
    if not files:
        logger.warning("No .log.gz files found in %s", input_dir)
        return {'files': 0, 'groups': 0}

    logger.info("Found %d log files to process", len(files))

    # Aggregate across all files
    totals = defaultdict(lambda: {'errors': 0, 'warnings': 0, 'total': 0})
    total_lines = 0
    total_skipped = 0
    start_time = time.monotonic()

    for i, filepath in enumerate(files, 1):
        file_counts, lines, skipped = _process_single_file(filepath)

        # Merge into totals
        for key, counts in file_counts.items():
            for metric in ('errors', 'warnings', 'total'):
                totals[key][metric] += counts[metric]

        total_lines += lines
        total_skipped += skipped

        # Progress reporting
        elapsed = time.monotonic() - start_time
        rate = total_lines / elapsed if elapsed > 0 else 0
        logger.info(
            "Progress: %d/%d files (%.1f%%), %d lines, %.0f lines/sec",
            i, len(files), 100 * i / len(files), total_lines, rate,
        )

    # Write output files
    for (date, service), counts in sorted(totals.items()):
        filename = f"{date}_{service}.json"
        output_path = os.path.join(output_dir, filename)
        output_data = {
            **counts,
            'date': date,
            'service': service,
            'error_rate': counts['errors'] / counts['total'] if counts['total'] else 0,
        }
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

    summary = {
        'files_processed': len(files),
        'groups': len(totals),
        'total_lines': total_lines,
        'lines_skipped': total_skipped,
        'skip_rate': total_skipped / (total_lines + total_skipped) if (total_lines + total_skipped) else 0,
        'elapsed_seconds': round(time.monotonic() - start_time, 1),
    }
    logger.info("ETL complete: %s", json.dumps(summary))

    if summary['skip_rate'] > 0.05:
        logger.warning(
            "High skip rate: %.1f%% of lines failed to parse",
            summary['skip_rate'] * 100,
        )

    return summary
```

### Key Changes Summary

| Before | After |
|--------|-------|
| Bare `except:` — catches KeyboardInterrupt, MemoryError | Specific exceptions: `json.JSONDecodeError`, `KeyError`, `TypeError` |
| Service name used raw in filename — path traversal | `_sanitize_component()` strips unsafe characters |
| No progress indication | Per-file progress logging with lines/sec rate |
| Silently skips all bad lines | Counts skipped lines, warns if skip rate > 5% |
| No handling of corrupt gzip files | `except (gzip.BadGzipFile, EOFError)` per file |
| `print()` | Structured logging |
| No output dir creation | `os.makedirs(output_dir, exist_ok=True)` |
| No return value / summary stats | Returns comprehensive summary dict |
| No error rate in output | Includes `error_rate` per group in output JSON |
'''),
]
