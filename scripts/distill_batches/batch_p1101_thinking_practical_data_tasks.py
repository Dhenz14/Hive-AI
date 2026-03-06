"""Thinking-trace pairs: real-world data processing tasks with vague requests."""

PAIRS = [
    (
        "thinking/practical",
        r'''I have a 50GB CSV I need to process but my script keeps running out of memory''',
        r'''<think>
The user is trying to process a 50GB CSV and running out of memory. This is almost certainly because they are doing something like `pd.read_csv("huge.csv")` which loads the entire file into memory, or reading the whole file with `csv.reader` into a list.

The core insight: you almost never need the entire file in memory at once. The solution depends on what kind of processing they need:

1. Row-by-row transforms (filtering, cleaning) -- just stream through line by line
2. Aggregations (sum, mean, group by) -- use chunked reading with accumulator
3. Joins with other data -- use database-like approach or chunked merge
4. Sorting -- external sort (split into sorted chunks, merge)

Since they did not specify what processing they need, I will provide a comprehensive toolkit that handles the most common scenarios:
- Streaming with Python's csv module (lowest memory footprint)
- Pandas chunked reading for when you need DataFrame operations
- Polars for better performance (lazy evaluation)
- DuckDB for SQL on CSV without loading into memory

I should also mention practical tips like: check if you actually need all columns, use appropriate dtypes to reduce memory, consider if the file can be split first.
</think>

The fix depends on what kind of processing you need. Here are solutions from simplest to most powerful, all designed to work within a fixed memory budget regardless of file size.

**Solution 1: Streaming row-by-row (lowest memory, ~10MB RAM)**

Use this when you need to filter, transform, or clean rows independently:

```python
import csv
from pathlib import Path
from typing import Iterator


def stream_csv(
    input_path: str,
    output_path: str,
    transform_fn,
    filter_fn=None,
    chunk_size: int = 8192,
):
    """Process a CSV file row-by-row with constant memory usage.

    Args:
        input_path: Path to the input CSV.
        output_path: Path for the output CSV.
        transform_fn: Function that takes a dict row and returns a dict row.
        filter_fn: Optional function that returns True to keep a row.
        chunk_size: Read buffer size in bytes.
    """
    rows_read = 0
    rows_written = 0

    with open(input_path, "r", newline="", buffering=chunk_size) as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames

        with open(output_path, "w", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                rows_read += 1

                if filter_fn and not filter_fn(row):
                    continue

                transformed = transform_fn(row)
                writer.writerow(transformed)
                rows_written += 1

                if rows_read % 1_000_000 == 0:
                    print(f"  Processed {rows_read:,} rows, wrote {rows_written:,}")

    print(f"Done: {rows_read:,} read, {rows_written:,} written")


# Example usage:
def clean_row(row):
    """Clean up a row -- strip whitespace, normalize emails."""
    return {
        k: v.strip() if isinstance(v, str) else v
        for k, v in row.items()
    }

def is_valid(row):
    """Filter out rows with missing required fields."""
    return bool(row.get("email")) and bool(row.get("name"))


stream_csv(
    "huge_data.csv",
    "cleaned_data.csv",
    transform_fn=clean_row,
    filter_fn=is_valid,
)
```

**Solution 2: Chunked pandas for aggregations (~200MB RAM)**

Use this when you need group-by, statistics, or DataFrame operations:

```python
import pandas as pd
from collections import defaultdict


def chunked_aggregation(
    filepath: str,
    group_col: str,
    agg_col: str,
    chunk_size: int = 100_000,
) -> pd.DataFrame:
    """Compute aggregations on a huge CSV using chunked reading.

    Processes the file in chunks, accumulating partial results,
    then combines them at the end. Memory usage is proportional
    to the number of groups, not the file size.
    """
    # Accumulators for computing mean = sum / count
    sums = defaultdict(float)
    counts = defaultdict(int)
    mins = {}
    maxs = {}

    # Only read the columns we need -- huge memory savings
    usecols = [group_col, agg_col]

    total_rows = 0
    for chunk in pd.read_csv(
        filepath,
        chunksize=chunk_size,
        usecols=usecols,
        # Specify dtypes to prevent pandas from guessing (saves memory)
        dtype={agg_col: "float64"},
        # Low memory mode
        low_memory=True,
    ):
        total_rows += len(chunk)

        # Accumulate per-group stats
        grouped = chunk.groupby(group_col)[agg_col]

        for group_name, group_sum in grouped.sum().items():
            sums[group_name] += group_sum

        for group_name, group_count in grouped.count().items():
            counts[group_name] += group_count

        for group_name, group_min in grouped.min().items():
            if group_name not in mins or group_min < mins[group_name]:
                mins[group_name] = group_min

        for group_name, group_max in grouped.max().items():
            if group_name not in maxs or group_max < maxs[group_name]:
                maxs[group_name] = group_max

        print(f"  Processed {total_rows:,} rows...")

    # Combine accumulators into final result
    results = []
    for group_name in sums:
        results.append({
            group_col: group_name,
            "sum": sums[group_name],
            "count": counts[group_name],
            "mean": sums[group_name] / counts[group_name],
            "min": mins[group_name],
            "max": maxs[group_name],
        })

    return pd.DataFrame(results).sort_values("count", ascending=False)


# Example:
result = chunked_aggregation(
    "sales_50gb.csv",
    group_col="region",
    agg_col="revenue",
)
print(result)
result.to_csv("regional_summary.csv", index=False)
```

**Solution 3: DuckDB -- SQL on CSV without loading into memory (~50MB RAM)**

This is often the best option. DuckDB reads CSV files directly with its own memory-efficient engine:

```python
import duckdb


def sql_on_csv(filepath: str):
    """Use DuckDB to run SQL directly on a CSV file.

    DuckDB uses its own buffer manager and can handle files
    much larger than available RAM. It also auto-detects
    column types and parallelizes reads.
    """
    con = duckdb.connect()

    # Set memory limit to prevent runaway usage
    con.execute("SET memory_limit = '2GB'")
    # Use temporary directory for spilling to disk
    con.execute("SET temp_directory = '/tmp/duckdb_temp'")

    # Basic aggregation -- runs in seconds even on 50GB
    result = con.execute(f"""
        SELECT
            region,
            COUNT(*) as order_count,
            SUM(revenue) as total_revenue,
            AVG(revenue) as avg_revenue,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY revenue) as median_revenue
        FROM read_csv_auto('{filepath}')
        GROUP BY region
        ORDER BY total_revenue DESC
    """).fetchdf()

    print(result)

    # Filter and export a subset
    con.execute(f"""
        COPY (
            SELECT *
            FROM read_csv_auto('{filepath}')
            WHERE revenue > 1000
              AND region = 'US'
        ) TO 'us_high_value.parquet' (FORMAT PARQUET)
    """)

    # Convert the whole file to Parquet for faster future reads
    # (Parquet is columnar, compressed, and much faster to query)
    con.execute(f"""
        COPY (
            SELECT * FROM read_csv_auto('{filepath}')
        ) TO 'data.parquet' (FORMAT PARQUET, ROW_GROUP_SIZE 100000)
    """)
    print("Converted to Parquet -- future queries will be 10-100x faster")

    con.close()


sql_on_csv("sales_50gb.csv")
```

**Solution 4: Polars lazy evaluation (~100MB RAM)**

```python
import polars as pl


def polars_lazy(filepath: str):
    """Use Polars lazy API to process large CSV with minimal memory.

    Polars builds a query plan and only materializes what is needed.
    It also uses all CPU cores automatically.
    """
    # scan_csv does NOT load the file -- it creates a lazy frame
    lf = pl.scan_csv(filepath)

    # Build a query plan (no data read yet)
    result = (
        lf
        .filter(pl.col("revenue") > 0)
        .group_by("region")
        .agg([
            pl.col("revenue").sum().alias("total_revenue"),
            pl.col("revenue").mean().alias("avg_revenue"),
            pl.col("order_id").count().alias("order_count"),
        ])
        .sort("total_revenue", descending=True)
    )

    # .collect() executes the plan with streaming
    df = result.collect(streaming=True)
    print(df)


polars_lazy("sales_50gb.csv")
```

**Quick decision guide:**

| Situation | Best tool | Memory usage |
|---|---|---|
| Row-by-row filtering/cleaning | csv module streaming | ~10MB |
| Group-by aggregations | Pandas chunked or DuckDB | ~200MB |
| Complex SQL queries | DuckDB | ~50MB (with spill to disk) |
| High-performance analytics | Polars lazy | ~100MB |
| Convert to faster format | DuckDB COPY to Parquet | ~2GB |

**Pro tip:** If you will query this data more than once, the first thing to do is convert it from CSV to Parquet using the DuckDB method above. Parquet files are typically 3-5x smaller and 10-100x faster to query because they are columnar and compressed.'''),
    (
        "thinking/practical",
        r'''our ETL pipeline keeps failing silently, data just goes missing''',
        r'''<think>
Silent failures in ETL pipelines are one of the most dangerous problems in data engineering because you do not know data is missing until someone notices wrong numbers downstream. The user has not told me what their pipeline looks like, but I can infer common patterns:

Root causes of silent data loss in ETL:
1. Exceptions being swallowed (bare except: pass, or catch-all with just logging)
2. No row count validation between stages (extracted 1M rows but only loaded 800K)
3. No checksums or hash verification
4. Partial writes -- a batch fails halfway and the partial data looks complete
5. Schema drift -- source adds/removes columns and the pipeline silently drops data
6. Null/empty handling -- rows with NULL keys get silently filtered by JOINs
7. Deduplication removing too much -- overly aggressive dedup losing unique records
8. Timezone/encoding issues causing silent data corruption

My approach: build an ETL framework with observability baked in at every stage:
- Record counts at every step with automatic validation
- Checksums for data integrity
- Dead letter queue for rows that cannot be processed
- Alerting on anomalies (row count drops, schema changes)
- Audit log showing exactly what happened

I will build a practical pipeline wrapper that can be applied to existing ETL code without rewriting everything.
</think>

Silent data loss in ETL is usually caused by exceptions being swallowed, missing row count validation, or partial writes. Here is a framework that makes every failure visible and every row accountable.

```python
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

logger = logging.getLogger(__name__)


# --- Pipeline observability ---

class StepStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"  # some rows failed but pipeline continued
    FAILED = "failed"


@dataclass
class StepMetrics:
    """Tracks metrics for a single pipeline step."""
    step_name: str
    status: StepStatus = StepStatus.RUNNING
    rows_in: int = 0
    rows_out: int = 0
    rows_errored: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    checksum_in: Optional[str] = None
    checksum_out: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return 0.0

    @property
    def loss_rate(self) -> float:
        """Percentage of input rows that were lost (not output or errored)."""
        if self.rows_in == 0:
            return 0.0
        accounted = self.rows_out + self.rows_errored
        lost = self.rows_in - accounted
        return (lost / self.rows_in) * 100

    def validate(self, max_loss_pct: float = 0.0) -> bool:
        """Check if row counts are acceptable."""
        if self.loss_rate > max_loss_pct:
            logger.error(
                "Step '%s' lost %.1f%% of rows (%d in, %d out, %d errored, %d unaccounted)",
                self.step_name,
                self.loss_rate,
                self.rows_in,
                self.rows_out,
                self.rows_errored,
                self.rows_in - self.rows_out - self.rows_errored,
            )
            return False
        return True


@dataclass
class PipelineRun:
    """Tracks an entire pipeline execution."""
    pipeline_name: str
    run_id: str = ""
    steps: list[StepMetrics] = field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: StepStatus = StepStatus.RUNNING

    def __post_init__(self):
        if not self.run_id:
            self.run_id = f"{self.pipeline_name}_{int(time.time())}"

    def summary(self) -> dict:
        return {
            "pipeline": self.pipeline_name,
            "run_id": self.run_id,
            "status": self.status.value,
            "duration": (
                (self.finished_at - self.started_at).total_seconds()
                if self.started_at and self.finished_at
                else None
            ),
            "steps": [
                {
                    "name": s.step_name,
                    "status": s.status.value,
                    "rows_in": s.rows_in,
                    "rows_out": s.rows_out,
                    "rows_errored": s.rows_errored,
                    "loss_rate": f"{s.loss_rate:.2f}%",
                    "duration": f"{s.duration_seconds:.1f}s",
                    "error": s.error_message,
                }
                for s in self.steps
            ],
        }


# --- Dead letter queue ---

class DeadLetterQueue:
    """Captures rows that failed processing so nothing is silently lost.

    Every failed row is written with its error context so you can
    investigate and replay later.
    """

    def __init__(self, output_dir: str = "./dead_letters"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._counts: dict[str, int] = {}

    def send(self, step_name: str, row: dict, error: str, run_id: str = ""):
        """Write a failed row to the dead letter file for this step."""
        filename = f"{run_id}_{step_name}.jsonl" if run_id else f"{step_name}.jsonl"
        filepath = self.output_dir / filename

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "step": step_name,
            "error": error,
            "row": row,
        }

        with open(filepath, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

        self._counts[step_name] = self._counts.get(step_name, 0) + 1

    def get_count(self, step_name: str) -> int:
        return self._counts.get(step_name, 0)


# --- Row checksum for integrity verification ---

def compute_checksum(rows: list[dict]) -> str:
    """Compute a deterministic checksum for a batch of rows.

    Used to verify data integrity between pipeline stages.
    """
    hasher = hashlib.sha256()
    for row in sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, default=str)):
        row_bytes = json.dumps(row, sort_keys=True, default=str).encode("utf-8")
        hasher.update(row_bytes)
    return hasher.hexdigest()[:16]


# --- The pipeline runner ---

class Pipeline:
    """ETL pipeline with built-in observability.

    Every row is tracked through every step. Nothing can disappear
    without being logged as an error in the dead letter queue.
    """

    def __init__(self, name: str, dead_letter_dir: str = "./dead_letters"):
        self.name = name
        self.steps: list[tuple[str, Callable, float]] = []
        self.dlq = DeadLetterQueue(dead_letter_dir)
        self.current_run: Optional[PipelineRun] = None

    def add_step(
        self,
        name: str,
        fn: Callable[[list[dict]], list[dict]],
        max_loss_pct: float = 0.0,
    ):
        """Register a pipeline step.

        Args:
            name: Human-readable step name.
            fn: Function that takes a list of dicts and returns a list of dicts.
            max_loss_pct: Maximum acceptable percentage of row loss (0.0 = no loss allowed).
        """
        self.steps.append((name, fn, max_loss_pct))

    def run(self, data: list[dict]) -> list[dict]:
        """Execute all pipeline steps with full tracking."""
        run = PipelineRun(pipeline_name=self.name)
        run.started_at = datetime.utcnow()
        self.current_run = run

        current_data = data
        logger.info("Pipeline '%s' started with %d rows", self.name, len(data))

        for step_name, step_fn, max_loss_pct in self.steps:
            metrics = StepMetrics(step_name=step_name)
            metrics.started_at = datetime.utcnow()
            metrics.rows_in = len(current_data)
            metrics.checksum_in = compute_checksum(current_data)

            try:
                result = self._run_step_safe(
                    step_name, step_fn, current_data, metrics, run.run_id
                )
                metrics.rows_out = len(result)
                metrics.checksum_out = compute_checksum(result)
                metrics.finished_at = datetime.utcnow()

                # Validate row counts
                if not metrics.validate(max_loss_pct):
                    metrics.status = StepStatus.PARTIAL
                    logger.warning(
                        "Step '%s' has unacceptable data loss: %.1f%% (max %.1f%%)",
                        step_name,
                        metrics.loss_rate,
                        max_loss_pct,
                    )
                elif metrics.rows_errored > 0:
                    metrics.status = StepStatus.PARTIAL
                else:
                    metrics.status = StepStatus.SUCCESS

                current_data = result

            except Exception as exc:
                metrics.status = StepStatus.FAILED
                metrics.error_message = str(exc)
                metrics.finished_at = datetime.utcnow()
                run.steps.append(metrics)
                run.status = StepStatus.FAILED
                run.finished_at = datetime.utcnow()

                logger.error(
                    "Pipeline '%s' FAILED at step '%s': %s",
                    self.name,
                    step_name,
                    exc,
                )
                self._save_run_report(run)
                raise

            run.steps.append(metrics)
            logger.info(
                "Step '%s': %d in -> %d out (%d errors) [%.1fs]",
                step_name,
                metrics.rows_in,
                metrics.rows_out,
                metrics.rows_errored,
                metrics.duration_seconds,
            )

        run.status = StepStatus.SUCCESS
        run.finished_at = datetime.utcnow()
        self._save_run_report(run)

        logger.info(
            "Pipeline '%s' completed: %d rows in -> %d rows out",
            self.name,
            len(data),
            len(current_data),
        )
        return current_data

    def _run_step_safe(
        self,
        step_name: str,
        step_fn: Callable,
        data: list[dict],
        metrics: StepMetrics,
        run_id: str,
    ) -> list[dict]:
        """Run a step function with per-row error handling.

        If the step function raises on the whole batch, we fall back
        to processing row-by-row so individual failures go to the
        dead letter queue instead of killing the pipeline.
        """
        try:
            return step_fn(data)
        except Exception:
            # Batch failed -- try row-by-row to salvage what we can
            logger.warning(
                "Step '%s' failed on batch, falling back to row-by-row",
                step_name,
            )
            results = []
            for row in data:
                try:
                    result = step_fn([row])
                    results.extend(result)
                except Exception as row_exc:
                    metrics.rows_errored += 1
                    self.dlq.send(step_name, row, str(row_exc), run_id)
            return results

    def _save_run_report(self, run: PipelineRun):
        """Save the pipeline run report as JSON for auditing."""
        report_dir = Path("./pipeline_reports")
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / f"{run.run_id}.json"
        with open(report_path, "w") as f:
            json.dump(run.summary(), f, indent=2, default=str)
        logger.info("Run report saved to %s", report_path)


# --- Example usage ---

def extract_from_source(data: list[dict]) -> list[dict]:
    """Simulate extracting data from a source system."""
    # In real code this would query a database, API, or file
    return data


def validate_schema(data: list[dict]) -> list[dict]:
    """Validate that required fields exist and have correct types."""
    required_fields = {"id", "email", "amount"}
    valid = []
    for row in data:
        missing = required_fields - set(row.keys())
        if missing:
            raise ValueError(f"Missing fields: {missing}")
        if not isinstance(row.get("amount"), (int, float)):
            raise ValueError(f"amount must be numeric, got {type(row['amount'])}")
        valid.append(row)
    return valid


def transform_data(data: list[dict]) -> list[dict]:
    """Clean and transform rows."""
    results = []
    for row in data:
        row["email"] = row["email"].strip().lower()
        row["amount"] = round(float(row["amount"]), 2)
        row["processed_at"] = datetime.utcnow().isoformat()
        results.append(row)
    return results


def load_to_warehouse(data: list[dict]) -> list[dict]:
    """Load data to the target system."""
    # In real code: INSERT into database, write to S3, etc.
    print(f"Loading {len(data)} rows to warehouse...")
    return data


# Build and run the pipeline
pipeline = Pipeline("daily_revenue_etl")
pipeline.add_step("extract", extract_from_source, max_loss_pct=0.0)
pipeline.add_step("validate", validate_schema, max_loss_pct=1.0)  # allow 1% validation failures
pipeline.add_step("transform", transform_data, max_loss_pct=0.0)
pipeline.add_step("load", load_to_warehouse, max_loss_pct=0.0)

# Run it
sample_data = [
    {"id": 1, "email": "Alice@Example.COM  ", "amount": 99.99},
    {"id": 2, "email": "bob@test.com", "amount": 150},
    {"id": 3, "email": "charlie@test.com", "amount": "not_a_number"},  # will fail validation
]

result = pipeline.run(sample_data)
print(json.dumps(pipeline.current_run.summary(), indent=2))
```

This framework catches the most common causes of silent data loss: swallowed exceptions go to the dead letter queue, row count mismatches are flagged immediately, checksums verify integrity between stages, and every run produces an audit trail.'''),
    (
        "thinking/practical",
        r'''need to deduplicate our customer database, some records have slightly different names/emails''',
        r'''<think>
This is a fuzzy deduplication problem -- one of the trickiest data quality tasks because "slightly different" could mean many things:
- "John Smith" vs "Jon Smith" (typo in name)
- "john.smith@gmail.com" vs "johnsmith@gmail.com" (dot in gmail)
- "John A. Smith" vs "John Smith" (middle initial)
- "ACME Corp" vs "Acme Corporation" (abbreviation)
- Same person, different email entirely

Approaches:
1. Exact matching on normalized fields -- catches trivial duplicates
2. Phonetic matching (Soundex, Metaphone) -- catches spelling variations
3. Edit distance (Levenshtein) -- catches typos
4. Token-based similarity (Jaccard on word sets) -- catches reordering
5. ML-based record linkage -- most accurate but complex

For a practical solution, I will use a multi-stage approach:
1. First, normalize (lowercase, strip, remove punctuation)
2. Then use blocking to avoid O(n^2) comparisons (group records by a "blocking key" like first 3 chars of last name + zip code)
3. Within blocks, compute similarity scores using multiple signals
4. Merge records above a configurable threshold

I will implement this with configurable thresholds so they can tune false positives vs false negatives. Important: NEVER auto-delete duplicates. Generate a report of suspected duplicates and let a human review, or at minimum merge into a primary record while keeping the original data.

Libraries to use: thefuzz (fuzzy string matching), potentially recordlinkage. But I will keep it self-contained with just thefuzz for simplicity.
</think>

Fuzzy deduplication is tricky because you need to balance catching real duplicates against falsely merging distinct records. Here is a complete solution with configurable thresholds and a safe merge strategy.

```python
import re
import csv
import json
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
from itertools import combinations

# pip install thefuzz python-Levenshtein
from thefuzz import fuzz


# --- Normalization ---

def normalize_name(name: str) -> str:
    """Normalize a name for comparison.

    Strips whitespace, lowercases, removes titles and suffixes,
    collapses multiple spaces.
    """
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common titles and suffixes
    for title in ["mr.", "mrs.", "ms.", "dr.", "jr.", "sr.", "iii", "ii", "iv"]:
        name = name.replace(title, "")
    # Remove punctuation except hyphens (for hyphenated names)
    name = re.sub(r"[^\w\s-]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normalize_email(email: str) -> str:
    """Normalize an email for comparison.

    Handles gmail dot-insensitivity, plus-addressing,
    and common domain aliases.
    """
    if not email:
        return ""
    email = email.lower().strip()

    local, _, domain = email.partition("@")
    if not domain:
        return email

    # Remove plus-addressing (user+tag@gmail.com -> user@gmail.com)
    local = local.split("+")[0]

    # Gmail ignores dots in local part
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        domain = "gmail.com"  # normalize googlemail -> gmail

    return f"{local}@{domain}"


def normalize_phone(phone: str) -> str:
    """Strip a phone number to just digits."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    # Remove leading 1 for US numbers
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


# --- Blocking (avoid O(n^2) comparisons) ---

def generate_blocking_keys(record: dict) -> list[str]:
    """Generate blocking keys to group potential duplicates.

    Instead of comparing every pair (O(n^2)), we only compare
    records that share a blocking key. Multiple keys per record
    increase recall at the cost of more comparisons.
    """
    keys = []
    name = normalize_name(record.get("name", ""))
    email = normalize_email(record.get("email", ""))

    if name:
        # First 3 chars of name
        keys.append(f"name3:{name[:3]}")
        # First + last name initials
        parts = name.split()
        if len(parts) >= 2:
            keys.append(f"initials:{parts[0][0]}{parts[-1][0]}")
            # Soundex-like: first letter + length
            keys.append(f"shape:{parts[-1][0]}{len(parts[-1])}")

    if email:
        # Email domain
        domain = email.split("@")[-1] if "@" in email else ""
        if domain:
            local = email.split("@")[0]
            keys.append(f"email_prefix:{local[:4]}")

    phone = normalize_phone(record.get("phone", ""))
    if phone and len(phone) >= 7:
        # Last 7 digits of phone
        keys.append(f"phone7:{phone[-7:]}")

    return keys


# --- Similarity scoring ---

@dataclass
class SimilarityResult:
    """Result of comparing two records."""
    record_a_id: str
    record_b_id: str
    overall_score: float
    name_score: float
    email_score: float
    phone_score: float
    signals: list[str] = field(default_factory=list)


def compute_similarity(rec_a: dict, rec_b: dict) -> SimilarityResult:
    """Compute a weighted similarity score between two records.

    Uses multiple signals and weights them based on reliability:
    - Exact email match is very strong (weight 0.5)
    - Name similarity matters but is fuzzier (weight 0.3)
    - Phone match is strong when available (weight 0.2)
    """
    signals = []

    # Name similarity (using token_sort_ratio to handle reordering)
    name_a = normalize_name(rec_a.get("name", ""))
    name_b = normalize_name(rec_b.get("name", ""))
    if name_a and name_b:
        name_score = fuzz.token_sort_ratio(name_a, name_b) / 100.0
    else:
        name_score = 0.0

    if name_score > 0.9:
        signals.append(f"name_very_similar ({name_score:.2f})")

    # Email similarity
    email_a = normalize_email(rec_a.get("email", ""))
    email_b = normalize_email(rec_b.get("email", ""))
    if email_a and email_b:
        if email_a == email_b:
            email_score = 1.0
            signals.append("exact_email_match")
        else:
            email_score = fuzz.ratio(email_a, email_b) / 100.0
            if email_score > 0.85:
                signals.append(f"email_similar ({email_score:.2f})")
    else:
        email_score = 0.0

    # Phone similarity
    phone_a = normalize_phone(rec_a.get("phone", ""))
    phone_b = normalize_phone(rec_b.get("phone", ""))
    if phone_a and phone_b:
        if phone_a == phone_b:
            phone_score = 1.0
            signals.append("exact_phone_match")
        else:
            phone_score = fuzz.ratio(phone_a, phone_b) / 100.0
    else:
        phone_score = 0.0

    # Weighted overall score
    weights = {"name": 0.3, "email": 0.5, "phone": 0.2}
    total_weight = 0.0
    weighted_sum = 0.0

    if name_a and name_b:
        weighted_sum += weights["name"] * name_score
        total_weight += weights["name"]
    if email_a and email_b:
        weighted_sum += weights["email"] * email_score
        total_weight += weights["email"]
    if phone_a and phone_b:
        weighted_sum += weights["phone"] * phone_score
        total_weight += weights["phone"]

    overall = weighted_sum / total_weight if total_weight > 0 else 0.0

    return SimilarityResult(
        record_a_id=str(rec_a.get("id", "")),
        record_b_id=str(rec_b.get("id", "")),
        overall_score=overall,
        name_score=name_score,
        email_score=email_score,
        phone_score=phone_score,
        signals=signals,
    )


# --- Deduplication engine ---

class Deduplicator:
    """Find and merge duplicate customer records.

    Uses blocking + fuzzy matching + configurable thresholds.
    NEVER deletes records -- merges into clusters with a primary record.
    """

    def __init__(
        self,
        auto_merge_threshold: float = 0.95,
        review_threshold: float = 0.75,
    ):
        self.auto_merge_threshold = auto_merge_threshold
        self.review_threshold = review_threshold

    def find_duplicates(self, records: list[dict]) -> dict:
        """Find duplicate clusters in the records.

        Returns a dict with:
        - auto_merge: pairs above auto_merge_threshold (safe to merge)
        - needs_review: pairs between review and auto_merge threshold
        - stats: summary statistics
        """
        # Build blocking index
        blocks: dict[str, list[int]] = defaultdict(list)
        for idx, record in enumerate(records):
            for key in generate_blocking_keys(record):
                blocks[key].append(idx)

        # Compare pairs within blocks
        compared = set()  # avoid comparing the same pair twice
        auto_merge = []
        needs_review = []
        total_comparisons = 0

        for block_key, indices in blocks.items():
            if len(indices) > 100:
                # Skip overly large blocks (they produce too many false positives)
                continue
            for i, j in combinations(indices, 2):
                pair_key = (min(i, j), max(i, j))
                if pair_key in compared:
                    continue
                compared.add(pair_key)
                total_comparisons += 1

                sim = compute_similarity(records[i], records[j])

                if sim.overall_score >= self.auto_merge_threshold:
                    auto_merge.append({
                        "record_a": records[i],
                        "record_b": records[j],
                        "score": round(sim.overall_score, 3),
                        "signals": sim.signals,
                    })
                elif sim.overall_score >= self.review_threshold:
                    needs_review.append({
                        "record_a": records[i],
                        "record_b": records[j],
                        "score": round(sim.overall_score, 3),
                        "signals": sim.signals,
                    })

        # Sort by score descending
        auto_merge.sort(key=lambda x: x["score"], reverse=True)
        needs_review.sort(key=lambda x: x["score"], reverse=True)

        n_records = len(records)
        max_possible = n_records * (n_records - 1) // 2

        return {
            "auto_merge": auto_merge,
            "needs_review": needs_review,
            "stats": {
                "total_records": n_records,
                "comparisons_made": total_comparisons,
                "comparisons_skipped": max_possible - total_comparisons,
                "auto_merge_pairs": len(auto_merge),
                "review_pairs": len(needs_review),
            },
        }

    def generate_report(self, results: dict, output_path: str = "dedup_report.json"):
        """Save a human-reviewable deduplication report."""
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Report saved to {output_path}")
        print(f"  {results['stats']['auto_merge_pairs']} pairs safe to auto-merge")
        print(f"  {results['stats']['review_pairs']} pairs need human review")


# --- Example usage ---

customers = [
    {"id": 1, "name": "John Smith", "email": "john.smith@gmail.com", "phone": "555-123-4567"},
    {"id": 2, "name": "Jon Smith", "email": "johnsmith@gmail.com", "phone": "(555) 123-4567"},
    {"id": 3, "name": "John A. Smith", "email": "john.smith+work@gmail.com", "phone": "5551234567"},
    {"id": 4, "name": "Jane Doe", "email": "jane@example.com", "phone": "555-999-8888"},
    {"id": 5, "name": "John Smith", "email": "jsmith@company.com", "phone": "555-000-1111"},
    {"id": 6, "name": "Jayne Doe", "email": "jane.doe@example.com", "phone": "555-999-8888"},
]

dedup = Deduplicator(
    auto_merge_threshold=0.92,  # high confidence -- safe to auto-merge
    review_threshold=0.70,      # medium confidence -- needs human eyes
)

results = dedup.find_duplicates(customers)
dedup.generate_report(results)

# Records 1, 2, 3 should cluster together (same person, different spellings)
# Records 4, 6 should be flagged for review (similar name, same phone)
# Record 5 has same name as 1 but different email/phone -- should be review
```

The key principle: **never auto-delete**. Generate merge candidates with confidence scores, let humans verify the borderline cases, and keep original records for audit. The thresholds (0.92 auto-merge, 0.70 review) are starting points -- tune them by running against a sample and checking false positive/negative rates.'''),
    (
        "thinking/practical",
        r'''migrate our data from MongoDB to PostgreSQL, here's our schema

{
  "_id": ObjectId("..."),
  "name": "Acme Corp",
  "contacts": [
    {"name": "Alice", "email": "alice@acme.com", "role": "CTO"},
    {"name": "Bob", "email": "bob@acme.com", "role": "Engineer"}
  ],
  "address": {
    "street": "123 Main St",
    "city": "Springfield",
    "state": "IL",
    "zip": "62701"
  },
  "tags": ["enterprise", "active"],
  "notes": "Good customer, been with us since 2019.\nPrefers email contact.",
  "created_at": ISODate("2024-01-15"),
  "last_order": {
    "id": "ord_abc123",
    "amount": 5000.00,
    "items": [
      {"sku": "WIDGET-A", "qty": 100, "unit_price": 25.00},
      {"sku": "GADGET-B", "qty": 50, "unit_price": 50.00}
    ]
  },
  "metadata": {"source": "website", "campaign": "q1-2024"}
}''',
        r'''<think>
This is a MongoDB-to-PostgreSQL migration. The MongoDB document has several patterns that need careful mapping to relational tables:

1. Embedded arrays (contacts, tags, order items) -> separate tables with foreign keys
2. Embedded objects (address, last_order, metadata) -> either flatten into the parent table or separate tables
3. Dynamic/flexible fields (metadata) -> JSONB column (PostgreSQL is great for this)
4. ObjectId -> UUID or serial ID
5. ISODate -> TIMESTAMP WITH TIME ZONE

Let me think about the normalization:

companies table:
- id (serial or UUID)
- name
- street, city, state, zip (flatten address -- it is 1:1)
- notes
- created_at
- metadata (JSONB -- good for semi-structured data)

contacts table:
- id
- company_id (FK)
- name
- email
- role

tags table (or company_tags join table):
- Two options: simple array column (PostgreSQL TEXT[]) or proper normalization
- For tags, TEXT[] is pragmatic -- they are just strings, no extra attributes

orders table:
- id
- company_id (FK)
- mongo_order_id (the "ord_abc123")
- amount
- created_at

order_items table:
- id
- order_id (FK)
- sku
- qty
- unit_price

I need to provide:
1. PostgreSQL schema (DDL)
2. Migration script that reads from MongoDB and writes to PostgreSQL
3. Validation to ensure no data loss
4. Handling of edge cases (nulls, missing fields, data type mismatches)
</think>

Here is a complete migration from your MongoDB schema to a normalized PostgreSQL database, including the schema design, migration script, and validation.

**Step 1: PostgreSQL schema (schema.sql)**

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Companies (main table, address flattened since it is 1:1)
CREATE TABLE companies (
    id              SERIAL PRIMARY KEY,
    mongo_id        VARCHAR(24) UNIQUE NOT NULL,  -- preserve original _id for reference
    name            VARCHAR(255) NOT NULL,
    -- Address fields (flattened from embedded document)
    street          VARCHAR(255),
    city            VARCHAR(100),
    state           VARCHAR(50),
    zip             VARCHAR(20),
    -- Semi-structured data stays as JSONB
    metadata        JSONB DEFAULT '{}',
    tags            TEXT[] DEFAULT '{}',  -- PostgreSQL array for simple string tags
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_companies_name ON companies (name);
CREATE INDEX idx_companies_tags ON companies USING GIN (tags);
CREATE INDEX idx_companies_metadata ON companies USING GIN (metadata);

-- Contacts (extracted from embedded array)
CREATE TABLE contacts (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255),
    role            VARCHAR(100),
    UNIQUE(company_id, email)
);

CREATE INDEX idx_contacts_company ON contacts (company_id);
CREATE INDEX idx_contacts_email ON contacts (email);

-- Orders (extracted from embedded last_order, designed for multiple orders)
CREATE TABLE orders (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    external_id     VARCHAR(100),  -- the "ord_abc123" from MongoDB
    amount          NUMERIC(12, 2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_company ON orders (company_id);
CREATE INDEX idx_orders_external ON orders (external_id);

-- Order items (extracted from nested array within orders)
CREATE TABLE order_items (
    id              SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sku             VARCHAR(100) NOT NULL,
    qty             INTEGER NOT NULL CHECK (qty > 0),
    unit_price      NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE INDEX idx_order_items_order ON order_items (order_id);
CREATE INDEX idx_order_items_sku ON order_items (sku);
```

**Step 2: Migration script (migrate.py)**

```python
import logging
from datetime import datetime
from typing import Any, Optional

import psycopg2
import psycopg2.extras
from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class MongoToPostgresMigrator:
    """Migrates data from MongoDB to PostgreSQL with validation.

    Processes documents in batches to manage memory.
    Tracks success/failure counts and saves failed documents
    for manual review.
    """

    def __init__(
        self,
        mongo_uri: str,
        mongo_db: str,
        mongo_collection: str,
        pg_dsn: str,
        batch_size: int = 500,
    ):
        self.mongo_client = MongoClient(mongo_uri)
        self.mongo_col = self.mongo_client[mongo_db][mongo_collection]
        self.pg_dsn = pg_dsn
        self.batch_size = batch_size
        self.stats = {
            "total": 0,
            "migrated": 0,
            "failed": 0,
            "contacts_created": 0,
            "orders_created": 0,
            "order_items_created": 0,
        }
        self.failures: list[dict] = []

    def run(self):
        """Execute the full migration."""
        logger.info("Starting migration...")
        pg_conn = psycopg2.connect(self.pg_dsn)
        pg_conn.autocommit = False

        try:
            total_docs = self.mongo_col.count_documents({})
            logger.info("Found %d documents to migrate", total_docs)

            cursor = self.mongo_col.find({}).batch_size(self.batch_size)

            for doc in cursor:
                self.stats["total"] += 1
                try:
                    self._migrate_document(doc, pg_conn)
                    self.stats["migrated"] += 1
                except Exception as exc:
                    self.stats["failed"] += 1
                    self.failures.append({
                        "mongo_id": str(doc.get("_id")),
                        "error": str(exc),
                        "name": doc.get("name", "unknown"),
                    })
                    logger.warning(
                        "Failed to migrate document %s: %s",
                        doc.get("_id"),
                        exc,
                    )
                    pg_conn.rollback()
                    continue

                # Commit in batches
                if self.stats["migrated"] % self.batch_size == 0:
                    pg_conn.commit()
                    logger.info(
                        "Progress: %d/%d migrated, %d failed",
                        self.stats["migrated"],
                        total_docs,
                        self.stats["failed"],
                    )

            # Final commit
            pg_conn.commit()

        finally:
            pg_conn.close()
            self.mongo_client.close()

        self._print_report()

    def _migrate_document(self, doc: dict, conn):
        """Migrate a single MongoDB document to PostgreSQL tables."""
        cur = conn.cursor()

        # --- Insert company ---
        address = doc.get("address", {})
        tags = doc.get("tags", [])
        metadata = doc.get("metadata", {})

        cur.execute(
            """
            INSERT INTO companies (mongo_id, name, street, city, state, zip, metadata, tags, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (mongo_id) DO UPDATE SET
                name = EXCLUDED.name,
                street = EXCLUDED.street,
                city = EXCLUDED.city,
                state = EXCLUDED.state,
                zip = EXCLUDED.zip,
                metadata = EXCLUDED.metadata,
                tags = EXCLUDED.tags,
                notes = EXCLUDED.notes
            RETURNING id
            """,
            (
                str(doc["_id"]),
                doc.get("name", ""),
                address.get("street"),
                address.get("city"),
                address.get("state"),
                address.get("zip"),
                psycopg2.extras.Json(metadata),
                tags,
                doc.get("notes"),
                doc.get("created_at", datetime.utcnow()),
            ),
        )
        company_id = cur.fetchone()[0]

        # --- Insert contacts ---
        contacts = doc.get("contacts", [])
        for contact in contacts:
            cur.execute(
                """
                INSERT INTO contacts (company_id, name, email, role)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (company_id, email) DO UPDATE SET
                    name = EXCLUDED.name,
                    role = EXCLUDED.role
                """,
                (
                    company_id,
                    contact.get("name", ""),
                    contact.get("email"),
                    contact.get("role"),
                ),
            )
            self.stats["contacts_created"] += 1

        # --- Insert order (if present) ---
        last_order = doc.get("last_order")
        if last_order:
            cur.execute(
                """
                INSERT INTO orders (company_id, external_id, amount)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    company_id,
                    last_order.get("id"),
                    last_order.get("amount", 0),
                ),
            )
            order_row = cur.fetchone()
            if order_row:
                order_id = order_row[0]
                self.stats["orders_created"] += 1

                # Insert order items
                items = last_order.get("items", [])
                for item in items:
                    cur.execute(
                        """
                        INSERT INTO order_items (order_id, sku, qty, unit_price)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            order_id,
                            item.get("sku", "UNKNOWN"),
                            item.get("qty", 0),
                            item.get("unit_price", 0),
                        ),
                    )
                    self.stats["order_items_created"] += 1

    def _print_report(self):
        """Print migration summary."""
        logger.info("=" * 60)
        logger.info("MIGRATION COMPLETE")
        logger.info("=" * 60)
        for key, value in self.stats.items():
            logger.info("  %-25s %d", key, value)

        if self.failures:
            logger.warning("  %d documents failed -- see failures.json", len(self.failures))
            import json
            with open("migration_failures.json", "w") as f:
                json.dump(self.failures, f, indent=2)


# --- Validation ---

def validate_migration(mongo_uri: str, mongo_db: str, mongo_col: str, pg_dsn: str):
    """Verify that all data was migrated correctly."""
    mongo = MongoClient(mongo_uri)
    collection = mongo[mongo_db][mongo_col]
    pg_conn = psycopg2.connect(pg_dsn)
    cur = pg_conn.cursor()

    # Count comparison
    mongo_count = collection.count_documents({})
    cur.execute("SELECT COUNT(*) FROM companies")
    pg_count = cur.fetchone()[0]
    logger.info("Document count: MongoDB=%d, PostgreSQL=%d", mongo_count, pg_count)
    if mongo_count != pg_count:
        logger.error("COUNT MISMATCH -- %d documents missing", mongo_count - pg_count)

    # Spot-check: verify contacts were migrated
    mongo_contacts = sum(
        len(doc.get("contacts", []))
        for doc in collection.find({}, {"contacts": 1})
    )
    cur.execute("SELECT COUNT(*) FROM contacts")
    pg_contacts = cur.fetchone()[0]
    logger.info("Contact count: MongoDB=%d, PostgreSQL=%d", mongo_contacts, pg_contacts)

    # Spot-check: verify monetary amounts match
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$last_order.amount"}}}]
    mongo_total = list(collection.aggregate(pipeline))
    mongo_amount = mongo_total[0]["total"] if mongo_total else 0

    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM orders")
    pg_amount = float(cur.fetchone()[0])
    logger.info("Order totals: MongoDB=%.2f, PostgreSQL=%.2f", mongo_amount, pg_amount)

    pg_conn.close()
    mongo.close()


# --- Run it ---

if __name__ == "__main__":
    migrator = MongoToPostgresMigrator(
        mongo_uri="mongodb://localhost:27017",
        mongo_db="myapp",
        mongo_collection="companies",
        pg_dsn="host=localhost dbname=myapp user=postgres password=secret",
        batch_size=500,
    )
    migrator.run()

    validate_migration(
        mongo_uri="mongodb://localhost:27017",
        mongo_db="myapp",
        mongo_col="companies",
        pg_dsn="host=localhost dbname=myapp user=postgres password=secret",
    )
```

**Design decisions:**

| MongoDB pattern | PostgreSQL mapping | Rationale |
|---|---|---|
| Embedded address object | Flattened columns on companies | 1:1 relationship, no benefit to separate table |
| Embedded contacts array | Separate contacts table with FK | 1:many, needs independent querying |
| tags array | TEXT[] column | Simple strings, no extra attributes |
| metadata object | JSONB column | Semi-structured, schema varies per record |
| Embedded order + items | Separate orders and order_items tables | Proper normalization for querying and reporting |
| ObjectId | mongo_id VARCHAR + serial PK | Keep reference to original, use serial for relational joins |

Run the schema SQL first, then the migration script, then the validation. The ON CONFLICT clauses make the migration idempotent so you can safely re-run it if something goes wrong.'''),
    (
        "thinking/practical",
        r'''the analytics dashboard is showing wrong numbers for monthly revenue''',
        r'''<think>
"Wrong numbers for monthly revenue" is a classic data bug. The most common causes in order of likelihood:

1. Timezone issues -- the most frequent cause of "wrong monthly numbers"
   - Server stores timestamps in UTC, dashboard aggregates by calendar month in local time
   - A sale at 11pm EST on Jan 31 is stored as 4am UTC Feb 1 -> counted in February instead of January
   - Different services use different timezone conventions

2. Aggregation boundary issues
   - Off-by-one on date ranges (using < vs <= on month end dates)
   - Inclusive vs exclusive boundaries (is midnight the end of yesterday or start of today?)
   - BETWEEN in SQL is inclusive on both ends

3. Double-counting
   - Retries or duplicate events from payment processor
   - Same transaction appearing in multiple tables (payments + refunds both positive)

4. Missing data
   - Transactions in "pending" status not included (or incorrectly included)
   - Partial refunds not subtracted
   - Currency conversion issues

5. Data type issues
   - Floating point rounding in aggregations
   - Integer overflow in SUM for large datasets
   - Storing amounts in dollars (float) vs cents (integer)

Since the user did not specify their stack, I will provide a diagnostic approach + corrected query patterns that handle the common pitfalls, focusing on the timezone issue since that is the most likely culprit.
</think>

Wrong monthly revenue numbers are almost always caused by one (or a combination) of these issues: timezone misalignment, aggregation boundary errors, or double-counting. Here is how to diagnose and fix each one.

**Step 1: Diagnose the problem**

Run these diagnostic queries to identify which issue you have:

```sql
-- DIAGNOSTIC 1: Check for timezone-shifted records at month boundaries
-- If these counts differ, you have a timezone problem
SELECT
    DATE_TRUNC('month', created_at AT TIME ZONE 'UTC') AS month_utc,
    DATE_TRUNC('month', created_at AT TIME ZONE 'America/New_York') AS month_local,
    COUNT(*) AS records,
    SUM(amount) AS revenue
FROM payments
WHERE created_at >= '2025-01-28' AND created_at < '2025-02-03'
GROUP BY month_utc, month_local
ORDER BY month_utc;

-- DIAGNOSTIC 2: Check for duplicates
-- If any count > 1, you have double-counting
SELECT
    transaction_id,
    COUNT(*) AS occurrences,
    SUM(amount) AS total_charged
FROM payments
GROUP BY transaction_id
HAVING COUNT(*) > 1
LIMIT 20;

-- DIAGNOSTIC 3: Check for status issues
-- Are you including/excluding the right statuses?
SELECT
    status,
    COUNT(*) AS count,
    SUM(amount) AS total
FROM payments
WHERE created_at >= '2025-01-01' AND created_at < '2025-02-01'
GROUP BY status
ORDER BY total DESC;

-- DIAGNOSTIC 4: Check for floating point drift
-- Compare SUM of float vs SUM of integer cents
SELECT
    SUM(amount) AS float_sum,
    SUM(amount_cents) / 100.0 AS cents_sum,
    SUM(amount) - SUM(amount_cents) / 100.0 AS drift
FROM payments
WHERE created_at >= '2025-01-01' AND created_at < '2025-02-01';
```

**Step 2: The correct monthly revenue query**

```sql
-- CORRECT monthly revenue query that handles all common pitfalls
WITH params AS (
    -- Define the business timezone once
    SELECT 'America/New_York'::TEXT AS biz_tz
),
deduped_payments AS (
    -- Remove duplicate transactions (keep the latest version)
    SELECT DISTINCT ON (transaction_id)
        id,
        transaction_id,
        amount,
        currency,
        status,
        created_at,
        -- Convert to business timezone for aggregation
        (created_at AT TIME ZONE (SELECT biz_tz FROM params))::DATE AS biz_date
    FROM payments
    WHERE
        -- Only count completed payments
        status IN ('completed', 'settled')
        -- Exclude test transactions
        AND NOT is_test
    ORDER BY transaction_id, created_at DESC
),
monthly AS (
    SELECT
        DATE_TRUNC('month', biz_date) AS month,
        -- Use NUMERIC to avoid floating point errors
        SUM(amount::NUMERIC(12,2)) AS gross_revenue,
        COUNT(*) AS transaction_count
    FROM deduped_payments
    GROUP BY DATE_TRUNC('month', biz_date)
),
refunds AS (
    SELECT
        DATE_TRUNC(
            'month',
            (created_at AT TIME ZONE (SELECT biz_tz FROM params))::DATE
        ) AS month,
        SUM(amount::NUMERIC(12,2)) AS refund_total,
        COUNT(*) AS refund_count
    FROM payments
    WHERE status = 'refunded'
      AND NOT is_test
    GROUP BY 1
)
SELECT
    TO_CHAR(m.month, 'YYYY-MM') AS month,
    m.gross_revenue,
    COALESCE(r.refund_total, 0) AS refunds,
    m.gross_revenue - COALESCE(r.refund_total, 0) AS net_revenue,
    m.transaction_count,
    COALESCE(r.refund_count, 0) AS refund_count
FROM monthly m
LEFT JOIN refunds r ON m.month = r.month
ORDER BY m.month DESC;
```

**Step 3: Python helper for correct date ranges**

```python
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional
import calendar


class RevenueReporter:
    """Generates correct revenue reports with timezone-aware boundaries.

    The key insight: 'January revenue' means transactions that occurred
    during January in your BUSINESS timezone, not UTC. A purchase at
    11:30pm EST on Jan 31 is January revenue even though it is
    4:30am UTC on Feb 1.
    """

    def __init__(self, db_connection, business_tz: str = "America/New_York"):
        self.conn = db_connection
        self.tz = ZoneInfo(business_tz)
        self.tz_name = business_tz

    def get_month_boundaries(self, year: int, month: int) -> tuple[datetime, datetime]:
        """Get UTC boundaries for a business-timezone month.

        Returns (start_utc, end_utc) where:
        - start_utc = midnight on the 1st in business timezone, converted to UTC
        - end_utc = midnight on the 1st of NEXT month in business timezone, converted to UTC

        This handles DST transitions correctly.
        """
        # Start of month in business timezone
        start_local = datetime(year, month, 1, tzinfo=self.tz)

        # Start of next month in business timezone
        if month == 12:
            end_local = datetime(year + 1, 1, 1, tzinfo=self.tz)
        else:
            end_local = datetime(year, month + 1, 1, tzinfo=self.tz)

        # Convert to UTC for querying
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc = end_local.astimezone(ZoneInfo("UTC"))

        return start_utc, end_utc

    def monthly_revenue(
        self,
        year: int,
        month: int,
        currency: str = "USD",
    ) -> dict:
        """Calculate correct monthly revenue with all adjustments."""
        start_utc, end_utc = self.get_month_boundaries(year, month)

        cursor = self.conn.cursor()

        # Gross revenue (deduplicated, correct timezone, correct statuses)
        cursor.execute(
            """
            WITH deduped AS (
                SELECT DISTINCT ON (transaction_id)
                    amount, status
                FROM payments
                WHERE created_at >= %s
                  AND created_at < %s
                  AND currency = %s
                  AND NOT is_test
                ORDER BY transaction_id, created_at DESC
            )
            SELECT
                COALESCE(SUM(amount) FILTER (WHERE status IN ('completed', 'settled')), 0) AS gross,
                COALESCE(SUM(amount) FILTER (WHERE status = 'refunded'), 0) AS refunds,
                COUNT(*) FILTER (WHERE status IN ('completed', 'settled')) AS tx_count,
                COUNT(*) FILTER (WHERE status = 'refunded') AS refund_count
            FROM deduped
            """,
            (start_utc, end_utc, currency),
        )

        row = cursor.fetchone()
        gross = float(row[0])
        refunds = float(row[1])
        tx_count = row[2]
        refund_count = row[3]

        return {
            "period": f"{year}-{month:02d}",
            "timezone": self.tz_name,
            "currency": currency,
            "gross_revenue": round(gross, 2),
            "refunds": round(refunds, 2),
            "net_revenue": round(gross - refunds, 2),
            "transaction_count": tx_count,
            "refund_count": refund_count,
            "query_range_utc": {
                "start": start_utc.isoformat(),
                "end": end_utc.isoformat(),
            },
        }

    def validate_against_payment_processor(
        self,
        year: int,
        month: int,
        processor_total: float,
        tolerance_pct: float = 0.01,
    ) -> dict:
        """Compare our numbers against the payment processor's report.

        Always reconcile against an external source of truth.
        A small difference (< 0.01%) is normal due to rounding.
        A large difference means something is wrong.
        """
        our_numbers = self.monthly_revenue(year, month)
        our_total = our_numbers["net_revenue"]
        difference = abs(our_total - processor_total)
        pct_diff = (difference / processor_total * 100) if processor_total else 0

        result = {
            "period": f"{year}-{month:02d}",
            "our_total": our_total,
            "processor_total": processor_total,
            "difference": round(difference, 2),
            "difference_pct": round(pct_diff, 4),
            "within_tolerance": pct_diff <= tolerance_pct,
        }

        if not result["within_tolerance"]:
            result["investigation_needed"] = True
            result["possible_causes"] = []
            if our_total > processor_total:
                result["possible_causes"].append(
                    "We may be double-counting transactions"
                )
            else:
                result["possible_causes"].append(
                    "We may be missing transactions -- check for failed webhook deliveries"
                )

        return result
```

**Step 4: Add automated tests for your revenue calculation**

```python
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock


def test_month_boundaries_handle_dst():
    """Verify that month boundaries account for DST transitions."""
    reporter = RevenueReporter(MagicMock(), business_tz="America/New_York")

    # March 2025: DST starts March 9 (clocks spring forward)
    start, end = reporter.get_month_boundaries(2025, 3)

    # March 1 midnight EST = 5:00 UTC
    assert start.hour == 5  # EST is UTC-5
    # April 1 midnight EDT = 4:00 UTC (DST in effect)
    assert end.hour == 4  # EDT is UTC-4


def test_no_double_count_on_boundary():
    """A transaction at 11:59pm on Jan 31 EST should be in January,
    not February, even though it is Feb 1 in UTC."""
    reporter = RevenueReporter(MagicMock(), business_tz="America/New_York")
    jan_start, jan_end = reporter.get_month_boundaries(2025, 1)
    feb_start, feb_end = reporter.get_month_boundaries(2025, 2)

    # 11:59pm EST Jan 31 = 4:59am UTC Feb 1
    tx_time = datetime(2025, 2, 1, 4, 59, tzinfo=ZoneInfo("UTC"))

    assert jan_start <= tx_time < jan_end  # should be in January
    assert not (feb_start <= tx_time < feb_end)  # should NOT be in February


def test_refunds_subtracted_from_gross():
    """Net revenue should be gross minus refunds."""
    # This is a sanity check -- sounds obvious but is a common bug
    gross = 10000.00
    refunds = 500.00
    net = gross - refunds
    assert net == 9500.00
```

**Summary of fixes to check:**

1. **Timezone**: Always convert to business timezone before truncating to month
2. **Boundaries**: Use `>=` start and `<` end (never `BETWEEN` for timestamps)
3. **Deduplication**: Use `DISTINCT ON (transaction_id)` to eliminate duplicate events
4. **Status filtering**: Only count `completed`/`settled`, subtract `refunded`
5. **Data types**: Use `NUMERIC(12,2)` not `FLOAT` for money
6. **Validation**: Reconcile against your payment processor's numbers monthly'''),
]
