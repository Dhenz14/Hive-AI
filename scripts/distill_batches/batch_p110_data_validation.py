"""Data validation — schema validation, data pipelines, and ETL patterns."""

PAIRS = [
    (
        "patterns/data-validation",
        "Show data validation patterns: multi-layer validation, schema evolution, and data quality checks.",
        '''Data validation patterns:

```python
from dataclasses import dataclass, field
from typing import Any, Callable
from datetime import datetime, date
from enum import StrEnum, auto
import re


# --- Validation result type ---

@dataclass
class ValidationError:
    field: str
    message: str
    code: str
    value: Any = None

@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, field: str, message: str, code: str, value: Any = None):
        self.errors.append(ValidationError(field, message, code, value))

    def merge(self, other: "ValidationResult"):
        self.errors.extend(other.errors)

    def to_dict(self) -> dict:
        return {
            "valid": self.is_valid,
            "errors": [
                {"field": e.field, "message": e.message, "code": e.code}
                for e in self.errors
            ],
        }


# --- Composable validators ---

Validator = Callable[[Any, str, ValidationResult], None]

def required(value: Any, field: str, result: ValidationResult):
    if value is None or (isinstance(value, str) and not value.strip()):
        result.add_error(field, f"{field} is required", "required")

def min_length(n: int) -> Validator:
    def validate(value: Any, field: str, result: ValidationResult):
        if isinstance(value, str) and len(value) < n:
            result.add_error(field, f"Must be at least {n} characters", "min_length", value)
    return validate

def max_length(n: int) -> Validator:
    def validate(value: Any, field: str, result: ValidationResult):
        if isinstance(value, str) and len(value) > n:
            result.add_error(field, f"Must be at most {n} characters", "max_length", value)
    return validate

def matches_pattern(pattern: str, message: str = "Invalid format") -> Validator:
    compiled = re.compile(pattern)
    def validate(value: Any, field: str, result: ValidationResult):
        if isinstance(value, str) and not compiled.match(value):
            result.add_error(field, message, "pattern", value)
    return validate

def in_range(min_val: float, max_val: float) -> Validator:
    def validate(value: Any, field: str, result: ValidationResult):
        if isinstance(value, (int, float)) and not (min_val <= value <= max_val):
            result.add_error(field, f"Must be between {min_val} and {max_val}", "range", value)
    return validate

def one_of(choices: set) -> Validator:
    def validate(value: Any, field: str, result: ValidationResult):
        if value not in choices:
            result.add_error(field, f"Must be one of: {sorted(choices)}", "one_of", value)
    return validate


# --- Schema-based validation ---

class Schema:
    def __init__(self):
        self._fields: dict[str, list[Validator]] = {}

    def field(self, name: str, *validators: Validator) -> "Schema":
        self._fields[name] = list(validators)
        return self

    def validate(self, data: dict) -> ValidationResult:
        result = ValidationResult()
        for field_name, validators in self._fields.items():
            value = data.get(field_name)
            for validator in validators:
                validator(value, field_name, result)
        return result


# --- Usage ---

user_schema = (
    Schema()
    .field("username", required, min_length(3), max_length(30),
           matches_pattern(r"^[a-zA-Z0-9_]+$", "Only alphanumeric and underscore"))
    .field("email", required, matches_pattern(
        r"^[^@]+@[^@]+\.[^@]+$", "Invalid email format"))
    .field("age", in_range(13, 120))
    .field("role", required, one_of({"admin", "user", "viewer"}))
)

result = user_schema.validate({
    "username": "ab",
    "email": "invalid",
    "age": 5,
    "role": "superadmin",
})
# result.is_valid == False
# result.errors: username min_length, email pattern, age range, role one_of


# --- Cross-field validation ---

def validate_date_range(data: dict, result: ValidationResult):
    start = data.get("start_date")
    end = data.get("end_date")
    if start and end and start > end:
        result.add_error("end_date", "End date must be after start date", "date_range")

def validate_password_match(data: dict, result: ValidationResult):
    if data.get("password") != data.get("password_confirm"):
        result.add_error("password_confirm", "Passwords do not match", "match")


# --- Data quality checks (for ETL/pipelines) ---

class DataQualityChecker:
    """Validate data quality for pipeline stages."""

    def __init__(self, name: str):
        self.name = name
        self._checks: list[tuple[str, Callable]] = []

    def check(self, description: str, fn: Callable[[list[dict]], bool]):
        self._checks.append((description, fn))
        return self

    def run(self, records: list[dict]) -> dict:
        results = []
        for description, fn in self._checks:
            try:
                passed = fn(records)
            except Exception as e:
                passed = False
                description += f" (error: {e})"
            results.append({"check": description, "passed": passed})

        return {
            "stage": self.name,
            "total_records": len(records),
            "checks": results,
            "all_passed": all(r["passed"] for r in results),
        }

# Usage:
quality = (
    DataQualityChecker("user_import")
    .check("No empty emails", lambda rows: all(r.get("email") for r in rows))
    .check("All ages positive", lambda rows: all(r.get("age", 0) > 0 for r in rows))
    .check("No duplicates", lambda rows: len(rows) == len({r["id"] for r in rows}))
    .check("At least 100 records", lambda rows: len(rows) >= 100)
)

report = quality.run(records)
```

Data validation patterns:
1. **`ValidationResult`** — accumulate all errors instead of failing on first
2. **Composable validators** — `required`, `min_length(n)`, `one_of(set)` combine freely
3. **`Schema.field()`** — fluent builder for field-level validation rules
4. **Cross-field validation** — date ranges, password confirmation, conditional requirements
5. **`DataQualityChecker`** — pipeline data quality gates with pass/fail reporting'''
    ),
    (
        "patterns/etl-pipeline",
        "Show ETL pipeline patterns: extract, transform, load stages with error handling and idempotency.",
        '''ETL pipeline patterns:

```python
from dataclasses import dataclass, field
from typing import Iterator, Callable, Any, TypeVar
from datetime import datetime, timezone
from pathlib import Path
import json
import csv
import logging
import hashlib

logger = logging.getLogger(__name__)
T = TypeVar("T")


# --- Pipeline stage abstraction ---

@dataclass
class PipelineContext:
    """Shared context across pipeline stages."""
    run_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stats: dict[str, int] = field(default_factory=lambda: {
        "extracted": 0, "transformed": 0, "loaded": 0,
        "errors": 0, "skipped": 0,
    })
    errors: list[dict] = field(default_factory=list)


# --- Extract stage ---

def extract_csv(path: Path) -> Iterator[dict]:
    """Extract records from CSV file."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield dict(row)

def extract_jsonl(path: Path) -> Iterator[dict]:
    """Extract records from JSONL file."""
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Bad JSON at line %d: %s", line_num, e)

def extract_api(url: str, page_size: int = 100) -> Iterator[dict]:
    """Extract records from paginated API."""
    import httpx
    page = 1
    while True:
        response = httpx.get(url, params={"page": page, "per_page": page_size})
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        if not items:
            break
        yield from items
        page += 1


# --- Transform stage ---

def transform_pipeline(*transforms: Callable[[dict], dict | None]) -> Callable:
    """Chain transforms; returning None skips the record."""
    def apply(record: dict) -> dict | None:
        for fn in transforms:
            record = fn(record)
            if record is None:
                return None
        return record
    return apply

# Individual transforms
def normalize_email(record: dict) -> dict:
    if "email" in record:
        record["email"] = record["email"].strip().lower()
    return record

def parse_dates(record: dict) -> dict:
    for key in ("created_at", "updated_at"):
        if key in record and isinstance(record[key], str):
            record[key] = datetime.fromisoformat(record[key])
    return record

def add_record_hash(record: dict) -> dict:
    """Deterministic hash for deduplication."""
    content = json.dumps(record, sort_keys=True, default=str)
    record["_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
    return record

def filter_valid(record: dict) -> dict | None:
    """Skip records missing required fields."""
    if not record.get("email") or not record.get("name"):
        return None
    return record


# --- Load stage ---

class BatchLoader:
    """Load records in batches with error handling."""

    def __init__(self, db, batch_size: int = 500):
        self.db = db
        self.batch_size = batch_size

    def load(self, records: Iterator[dict], ctx: PipelineContext) -> int:
        batch = []
        loaded = 0

        for record in records:
            batch.append(record)
            if len(batch) >= self.batch_size:
                loaded += self._flush_batch(batch, ctx)
                batch = []

        if batch:
            loaded += self._flush_batch(batch, ctx)

        return loaded

    def _flush_batch(self, batch: list[dict], ctx: PipelineContext) -> int:
        try:
            # Upsert for idempotency
            self.db.upsert_many(batch, conflict_key="email")
            ctx.stats["loaded"] += len(batch)
            return len(batch)
        except Exception as e:
            logger.error("Batch load failed: %s", e)
            ctx.stats["errors"] += len(batch)
            ctx.errors.append({
                "stage": "load",
                "error": str(e),
                "batch_size": len(batch),
            })
            return 0


# --- Pipeline orchestrator ---

def run_pipeline(
    source: Iterator[dict],
    transform: Callable[[dict], dict | None],
    loader: BatchLoader,
    ctx: PipelineContext,
) -> dict:
    """Run full ETL pipeline with stats tracking."""
    logger.info("Pipeline %s started", ctx.run_id)

    def transformed_stream():
        for record in source:
            ctx.stats["extracted"] += 1
            try:
                result = transform(record)
                if result is None:
                    ctx.stats["skipped"] += 1
                    continue
                ctx.stats["transformed"] += 1
                yield result
            except Exception as e:
                ctx.stats["errors"] += 1
                ctx.errors.append({
                    "stage": "transform",
                    "error": str(e),
                    "record_id": record.get("id"),
                })

    loader.load(transformed_stream(), ctx)

    logger.info("Pipeline %s complete: %s", ctx.run_id, ctx.stats)
    return {
        "run_id": ctx.run_id,
        "duration_seconds": (datetime.now(timezone.utc) - ctx.started_at).total_seconds(),
        "stats": ctx.stats,
        "errors": ctx.errors[:10],  # First 10 errors
    }


# --- Usage ---

# transform = transform_pipeline(
#     normalize_email,
#     parse_dates,
#     filter_valid,
#     add_record_hash,
# )
#
# ctx = PipelineContext(run_id="import-2024-06-15")
# result = run_pipeline(
#     source=extract_csv(Path("data/users.csv")),
#     transform=transform,
#     loader=BatchLoader(db, batch_size=1000),
#     ctx=ctx,
# )
```

ETL pipeline patterns:
1. **Generator-based extraction** — `yield` records lazily, handles any source size
2. **Transform pipeline** — chain small transforms, `None` return skips records
3. **Batch loading** — upsert in batches with error isolation per batch
4. **Record hashing** — deterministic SHA256 for deduplication and change detection
5. **`PipelineContext`** — track stats and errors across all stages'''
    ),
]
"""
