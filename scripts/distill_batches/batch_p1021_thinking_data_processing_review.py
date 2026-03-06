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
Okay, looking at this pandas pipeline... it reads a CSV, cleans it, converts currencies, aggregates by region/month, and writes output. Standard ETL. Let me trace through for problems.

The first thing that concerns me is the cleaning section. `df.dropna()` drops rows where ANY column is null. But wait -- what if a row has a perfectly valid sale amount but a missing optional field like `notes` or `customer_phone`? That entire row gets silently dropped from the report. That's not just a minor issue -- you could be losing a significant portion of your data without any warning. The developer probably meant to only drop rows where critical fields (amount, date, currency, region) are null.

Similarly, `drop_duplicates()` with no subset parameter deduplicates on ALL columns. But sales data frequently has legitimate duplicates -- two purchases of the same item, same price, same day, same region. Without a unique transaction ID in the subset, you're merging real sales.

Now the big performance issue... `df.apply(lambda row: ..., axis=1)`. My first thought was "that's just a convenience wrapper" but actually no -- apply with axis=1 is a Python-level row-by-row loop wearing a pandas costume. It's easily 100-1000x slower than vectorized operations. For 10 million rows, this could take minutes instead of seconds.

But wait, there's something worse I should consider. What does `get_exchange_rate()` actually do? If it makes a network call (API request) for each row, that's 10 million HTTP requests. That would take hours, not minutes. Even if it's a local lookup, the per-row function call overhead in Python is brutal. The fix is to build a currency-to-rate mapping dict once and use `df['currency'].map(rates)` for vectorized multiplication.

Let me also think about memory. Each cleaning step -- dropna(), boolean filter, drop_duplicates() -- creates a full copy of the DataFrame. So at peak we have the original plus 3 intermediate copies. For a 2GB CSV, that's potentially 8GB+ of RAM. We could chain these or use inplace operations to reduce the footprint.

Hmm, the running total loop is also suboptimal. Iterating over `summary['region'].unique()` and applying boolean masks is slow for many regions. The pandas way to do this is `summary['running_total'] = summary.groupby('region')['total'].cumsum()` -- one line, vectorized, much faster.

One more thing I almost missed -- there's no input validation at all. What if the CSV is missing the 'amount' column? You'd get a KeyError deep in the pipeline with no useful error message. And `to_csv` without specifying float_format means amounts might render as 1234.567890123456.

Priority: (1) fix the apply loop -- that's the performance killer, (2) fix dropna to only target critical columns -- that's silent data loss, (3) memory optimization matters at scale.
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
Let me look at this CSV-to-SQLite import function. It reads a CSV, creates a table from the headers, and inserts rows one at a time.

My first thought is to check how the SQL is built. The table_name parameter goes directly into an f-string for the SQL... and then the column names from `reader.fieldnames` are also interpolated directly. Wait -- those column names come from the CSV file itself. That's untrusted input going straight into SQL.

Let me think about what an attacker could do. If someone crafts a CSV with a header like `name, email); DROP TABLE users; --`, the CREATE TABLE statement becomes:
```sql
CREATE TABLE IF NOT EXISTS data (name TEXT, email); DROP TABLE users; -- TEXT)
```
That's SQL injection through CSV column headers. And you can't fix this with `?` parameterization because you cannot parameterize column names or table names in SQL -- those aren't values, they're identifiers. You'd need to validate or sanitize the header names manually, checking for characters like semicolons, parentheses, and SQL keywords.

Now let me think about performance. Each row is a separate `cursor.execute()` call, and without an explicit transaction, SQLite wraps each insert in its own transaction. For a 1-million row CSV, that's 1M individual INSERT statements with 1M disk syncs. SQLite can do around 50K inserts/sec this way, but with `executemany()` inside a single explicit transaction, it can do 500K+/sec. So we're looking at roughly 10x slower than necessary.

Hmm, I should also check the resource management. The `conn.close()` is at the end of the function, but there's no try/finally block. If any exception occurs during CSV processing -- malformed row, encoding error, disk full -- the connection is never closed. Should use a context manager: `with sqlite3.connect(db_path) as conn`.

There's also a subtle issue with data types. Every column is created as TEXT. If the CSV has numeric data, queries like `WHERE amount > 100` will do string comparison, not numeric. "9" would be greater than "100" because "9" > "1" lexicographically. That's a really confusing bug for someone querying the resulting database.

One more thing -- no duplicate handling at all. No UNIQUE constraints, no ON CONFLICT clause. If you import the same CSV twice, you get every row duplicated. For a generic importer that might be acceptable, but it should at least be documented or have an option.

Priority: (1) SQL injection via headers is the security showstopper, (2) row-by-row inserts are the performance bottleneck, (3) missing resource cleanup is a reliability issue.
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
Let me trace through this ETL script step by step. It extracts unprocessed events, transforms JSON payloads, inserts into an analytics table, and marks source records as processed.

The first thing that worries me is the error recovery story. What happens if this script fails halfway through? Say it crashes on event #5000 of 10000. Nothing has been committed, so the next run will re-process all 10000 events. At first glance that seems fine -- just retry the whole batch. But wait, what if event #5000 has malformed JSON or a missing field? The script will fail at that same event every single run, blocking ALL 10000 events behind it permanently. One bad record poisons the entire pipeline.

Hmm, but let me reconsider the transaction semantics. Steps 3 and 4 are in the same transaction, which means the load and the mark-processed happen atomically. That's actually good -- if we crash mid-insert, nothing is marked processed, so we retry everything. But the problem is the lack of idempotency. If we DO succeed but the process crashes right after commit... actually that's fine since the commit happened. The real issue is that there's no way to skip bad records and continue.

Now let me think about memory. `fetchall()` loads ALL unprocessed events into memory at once. If the system was down for a week and there are 50 million events queued up, this will consume gigabytes of RAM and likely OOM the process. Should use `fetchmany()` with a batch size, or better yet, use a server-side cursor.

I almost missed something subtle -- the code accesses columns by index: `event[3]`, `event[1]`, `event[0]`. If someone adds a column to the raw_events table, or if the column order changes, all these indices silently point to the wrong data. Not an error -- just wrong results. Should use named columns or a row factory.

The performance is also bad in multiple ways. `SELECT *` fetches all columns including potentially large payload blobs we might not need. The INSERT in step 3 is row-by-row, and the UPDATE in step 4 is also row-by-row. For 10000 events, that's 20000 individual SQL statements. Using `executemany()` would batch these and be dramatically faster.

Let me also check for crash-safety in the JSON handling. `json.loads()` on malformed JSON will raise, `float(data['amount'])` on non-numeric values will raise, `data['user_id']` on missing keys will raise. None of these have error handling, so any one bad event crashes the whole pipeline.

Priority order: (1) batch processing with checkpointing so bad records don't block everything, (2) memory-bounded fetching so large backlogs don't OOM, (3) named column access instead of fragile indices, (4) batched inserts/updates for performance.
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
Let me walk through this validation function field by field and check what actually happens with bad input.

Starting with the age validation... there's an `except ValueError: pass`. So if someone passes age="abc", the int() conversion fails, the exception is caught, and... nothing happens. No error is added to the list. The invalid age is silently accepted as valid. That completely defeats the purpose of validation.

Wait, let me check the address validation too. `if not addr.get('street'): pass` -- that's literally a no-op. The pass statement does nothing. Missing street and city are silently accepted. This looks like someone started writing validation, got interrupted, and left placeholder code. But now it's giving callers a false sense of security -- they think addresses are being validated when they're not.

Hmm, there's an even more fundamental problem. All fields are optional -- if the input dict is `{}`, the function returns `valid=True` with no errors. For user creation, you almost certainly need at least name and email. An empty form submission would pass validation.

Let me think about what happens with edge cases. If `data['name']` is present but is `None` (not missing, but explicitly None), then `len(None)` throws a `TypeError`. The validator crashes with an unhandled exception instead of reporting a friendly error. The same issue exists if name is an integer or a list -- `len()` would work but give a meaningless result.

Now the email regex: `r'.+@.+\..+'`. My first thought was "that's basic but okay" but actually let me think about what it matches... it would match `"@a.b"` because `.+` matches any character. It would match `"x@..y"` because the dots are not escaped. It would match `"@@@a.b"`. This is barely checking anything. And it doesn't check for maximum length, which matters for database columns.

I should also consider the phone validation. `re.sub(r'\D', '', phone)` strips non-digits and checks if there are 10+ digits. But there's no check that phone is actually a string before calling re.sub. If someone passes a number, it crashes. And "10+ digits" is very loose -- a 20-digit string passes fine.

So the priority here is clear: the silent failures are the most dangerous issue because they create a false sense of safety. Code elsewhere is probably relying on this validator to reject bad data, but it's letting almost everything through. The dead code in address validation needs to either be implemented or removed. And the email regex needs significant tightening.
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
Let me trace through this log processor. It reads gzipped JSON log files, aggregates counts by date and service, and writes per-group output files. Sounds straightforward, but let me check the error handling...

The inner loop has `except: continue`. That's a bare except -- it catches literally everything. Not just json.JSONDecodeError, but also KeyboardInterrupt, MemoryError, SystemExit. So if you try to Ctrl+C out of a long-running job, the exception is caught and the loop continues. You can't stop it. And if half the log lines are corrupted or malformed, the script silently skips them and produces results based on only the good half, with no indication that anything was wrong.

My first instinct was "just change it to except json.JSONDecodeError", but actually there are multiple things that could fail: json.loads could fail, entry['service'] could raise KeyError, the date parsing could fail. The right approach is to catch specific exceptions AND count how many lines were skipped. If 40% of lines are being skipped, something is seriously wrong and the operator needs to know.

Hmm, now let me think about security. The service name from `entry['service']` goes directly into the output filename: `f"{date}_{service}.json"`. What if a service name contains path separators? If service is `"../../etc/cron.d/evil"`, this writes files outside the output directory. That's path traversal via log data. Should sanitize the service name -- strip slashes, limit to alphanumeric characters.

Actually, I should also think about what happens at scale. The `results` dict accumulates all (date, service) combinations in memory. For normal log data with maybe 50 services and 365 days, that's fine. But if service names include unique request IDs or user IDs, the dict grows without bound and eventually exhausts memory. Need to validate that the cardinality is reasonable.

What about operational concerns? This script processes files sequentially, but log file processing is embarrassingly parallel -- each file is independent. On a machine with 8 cores, this is using 1/8 of the available compute. Using multiprocessing.Pool or concurrent.futures would give a near-linear speedup.

Also, there's no progress tracking at all. With hundreds of multi-gigabyte log files, this runs silently for hours. No progress bar, no ETA, no way to know if it's stuck or making progress. That's painful for operators who need to monitor batch jobs.

Priority: (1) fix the bare except -- that's a reliability and debuggability killer, (2) sanitize service names for the output path to prevent path traversal, (3) add progress tracking and error counting for operational visibility.
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
