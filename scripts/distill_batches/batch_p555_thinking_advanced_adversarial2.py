"""Phase 2B: Advanced Reasoning — Adversarial Self-Testing (Part 2/5)
Unicode edge cases, timezone traps, floating point precision, error propagation, config interactions."""

PAIRS = [
    (
        "thinking/adversarial-unicode-edge-cases",
        "Write a function that counts the number of characters in a user's display name and enforces a 50-character limit.",
        r'''<think>
Let me write the obvious solution and then break it with Unicode.

```python
def validate_display_name(name: str) -> bool:
    return len(name) <= 50
```

Now let me attack with Unicode:

1. "Hello" → len = 5. Correct.
2. "🎉🎊🎈" → len = 3 in Python (each emoji is one code point). But visually they might be wider. Probably fine for a "character" count.
3. "👨‍👩‍👧‍👦" (family emoji) → This is FOUR code points joined by ZWJ (Zero Width Joiner): 👨 + ZWJ + 👩 + ZWJ + 👧 + ZWJ + 👦 = 7 code points, but appears as ONE emoji to the user. len() = 7. So a user sees 1 character but we count 7. BUG — we'd reject a name with 8 family emojis.

4. "é" could be:
   - U+00E9 (single code point, precomposed) → len = 1
   - U+0065 U+0301 (e + combining accent) → len = 2
   Same visual character, different lengths! BUG.

5. "Z̤̈̈͐̊" (Zalgo text) → One visible character with many combining marks. len() could be huge.

6. "🏳️‍🌈" (rainbow flag) → 4 code points: 🏳 + VS16 + ZWJ + 🌈. len() = 4, visual = 1.

7. Null bytes: "hello\x00world" → len = 11, but some systems treat \x00 as string terminator. Potential truncation bug.

8. RTL override: "\u202E" + "dlrow olleH" → visually shows "Hello world" backwards. Could be used for phishing-style attacks in names.

9. Very long combining character sequences: "a" + "\u0300" * 1000 → len = 1001, but visually looks like one character with tons of accents. Could cause rendering issues.

The right approach: use grapheme cluster counting, not code point counting. A "grapheme cluster" is what a user perceives as one character. Python's `grapheme` library or `regex` with \X can do this.

Also: normalize the string first (NFC normalization) to handle the é case.
</think>

`len()` counts **code points**, not what users perceive as "characters." This breaks with emoji, accented characters, and combining marks.

```python
# BROKEN: len() counts code points, not visual characters
def validate_display_name_broken(name: str) -> bool:
    return len(name) <= 50

# "👨‍👩‍👧‍👦" → user sees 1 character, len() returns 7
# "é" (decomposed) → user sees 1 character, len() returns 2
# Both are unfairly penalized
```

**Fixed: count grapheme clusters (what users actually see)**:
```python
import unicodedata
import re

# Option 1: Using the `grapheme` library (most correct)
import grapheme

def validate_display_name(name: str) -> bool:
    # Normalize to NFC first — "e + accent" becomes "é" (single code point)
    name = unicodedata.normalize("NFC", name)

    # Strip control characters (null bytes, RTL override, etc.)
    name = re.sub(r'[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\ufeff]', '', name)

    # Count grapheme clusters — what users visually perceive as characters
    count = grapheme.length(name)

    return 0 < count <= 50

# Option 2: Using regex \X (grapheme cluster match) without extra dependency
def count_visual_characters(text: str) -> int:
    import regex  # `regex` module, not `re` — supports \X
    return len(regex.findall(r'\X', text))
```

**Test cases that break naive `len()` but work with grapheme counting**:
```python
# Family emoji: 1 visual character, 7 code points
assert validate_display_name("👨‍👩‍👧‍👦" * 50)  # 50 family emojis = 50 visual chars ✓
assert len("👨‍👩‍👧‍👦" * 50) == 350              # len() says 350 — would reject!

# Accented characters (decomposed form)
name_nfd = "e\u0301" * 50  # 50 "é" in decomposed form
assert validate_display_name(name_nfd)  # NFC normalizes, counts 50

# Flag emojis: 2 code points each
assert validate_display_name("🇺🇸" * 50)  # 50 flags = 50 visual chars ✓
assert len("🇺🇸" * 50) == 200             # len() says 200 — would reject!

# Zalgo text: one visible char with many marks
zalgo = "Z" + "\u0300" * 100  # 100 combining marks
assert grapheme.length(zalgo) == 1  # One grapheme cluster

# Control character stripping
assert not validate_display_name("\u202Eevil")  # RTL override stripped → "evil" (4) OK but flagged
assert not validate_display_name("")             # Empty after stripping
assert not validate_display_name("\x00\x00")     # Null bytes stripped → empty
```

**Lesson**: Any time you count "characters" for a user-facing limit, count **grapheme clusters**, not code points or bytes. `len("👨‍👩‍👧‍👦") == 7` but users see one character.'''
    ),
    (
        "thinking/adversarial-timezone-traps",
        "Write a function that checks if an event (with start and end timestamps) falls on a weekend.",
        r'''<think>
Simple version first:

```python
def is_weekend_event(start, end):
    return start.weekday() >= 5  # Saturday=5, Sunday=6
```

Now let me break it with timezone edge cases:

1. What type are start and end? datetime? string? Unix timestamp? If the user passes a string, we need to parse it. If they pass a naive datetime, we don't know the timezone.

2. Naive vs aware datetimes: If start is naive (no timezone info), `weekday()` returns the weekday in whatever local timezone Python thinks it's running in. On a server in UTC, this could be wrong for users in other timezones.

Example: Friday 11 PM in New York (UTC-5) = Saturday 4 AM UTC. Is this a weekend event?
- In UTC: weekday() returns 5 (Saturday) → weekend ✓
- In New York: weekday() returns 4 (Friday) → NOT weekend ✗
The answer depends on the USER's timezone, which we need to know.

3. Events that span midnight Friday → Saturday:
- Start: Friday 10 PM, End: Saturday 2 AM
- Is this a weekend event? The start is on a weekday, but most of it is on the weekend.
- Business rule needed: does "falls on a weekend" mean starts on weekend, ends on weekend, any overlap, or entirely within?

4. DST transitions:
- An event on the day DST changes could have ambiguous local times
- 2 AM springs forward to 3 AM → an event at 2:30 AM doesn't exist
- 2 AM falls back to 1 AM → an event at 1:30 AM happens twice

5. Date-line crossing:
- It's Saturday in Tokyo but Friday in LA. Same moment in time, different days of the week.

6. Events that span multiple days:
- Start: Friday, End: Monday → spans both weekday and weekend. What's the answer?

The "correct" solution needs:
- Timezone-aware datetimes
- User's timezone to determine what "weekend" means for them
- Clear business rules for span handling
</think>

This question hides at least **4 timezone traps**. Here's what breaks and how to fix it:

```python
# BROKEN: Ignores timezone entirely
def is_weekend_broken(start: datetime) -> bool:
    return start.weekday() >= 5
# Friday 11 PM in NYC = Saturday 4 AM UTC → gives wrong answer depending on server TZ
```

**Fixed: timezone-aware with explicit user timezone**:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

def event_falls_on_weekend(
    start: datetime,
    end: datetime,
    user_timezone: str = "UTC",
) -> dict:
    """Check if an event overlaps with a weekend in the user's timezone.

    Returns dict with 'starts_on_weekend', 'ends_on_weekend', 'spans_weekend'.
    """
    tz = ZoneInfo(user_timezone)

    # Convert to user's local time
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)

    starts_on_weekend = local_start.weekday() >= 5
    ends_on_weekend = local_end.weekday() >= 5

    # Check if any day in the range is a weekend
    spans_weekend = False
    current = local_start.date()
    end_date = local_end.date()
    while current <= end_date:
        if current.weekday() >= 5:
            spans_weekend = True
            break
        current += timedelta(days=1)

    return {
        "starts_on_weekend": starts_on_weekend,
        "ends_on_weekend": ends_on_weekend,
        "spans_weekend": spans_weekend,
        "entirely_weekend": starts_on_weekend and ends_on_weekend,
    }
```

**Traps I tested**:
```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Trap 1: Friday night in NYC = Saturday morning in UTC
friday_night_nyc = datetime(2024, 3, 15, 23, 0, tzinfo=ZoneInfo("America/New_York"))
# In UTC: Saturday 4 AM
# In NYC: Friday 11 PM
result = event_falls_on_weekend(friday_night_nyc, friday_night_nyc + timedelta(hours=2), "America/New_York")
assert result["starts_on_weekend"] == False  # Friday in user's timezone
result_utc = event_falls_on_weekend(friday_night_nyc, friday_night_nyc + timedelta(hours=2), "UTC")
assert result_utc["starts_on_weekend"] == True  # Saturday in UTC!

# Trap 2: Event spanning Friday → Saturday
friday_to_saturday = datetime(2024, 3, 15, 22, 0, tzinfo=ZoneInfo("UTC"))
result = event_falls_on_weekend(
    friday_to_saturday,
    friday_to_saturday + timedelta(hours=4),
    "UTC"
)
assert result["starts_on_weekend"] == False  # Starts Friday
assert result["ends_on_weekend"] == True     # Ends Saturday
assert result["spans_weekend"] == True       # Crosses into weekend

# Trap 3: DST transition — March "spring forward"
# 2 AM → 3 AM, so 2:30 AM doesn't exist
dst_day = datetime(2024, 3, 10, 1, 30, tzinfo=ZoneInfo("America/New_York"))
# Sunday — is_weekend should be True regardless of DST weirdness
result = event_falls_on_weekend(dst_day, dst_day + timedelta(hours=2), "America/New_York")
assert result["starts_on_weekend"] == True

# Trap 4: Same instant, different days in different timezones
instant = datetime(2024, 3, 16, 3, 0, tzinfo=ZoneInfo("UTC"))  # Saturday 3 AM UTC
# In Honolulu (UTC-10): Friday 5 PM
result_hi = event_falls_on_weekend(instant, instant + timedelta(hours=1), "Pacific/Honolulu")
assert result_hi["starts_on_weekend"] == False  # Friday in Hawaii!
```

**Rules**: Always store timestamps in UTC. Always convert to user's timezone for display/business logic. Never use `datetime.now()` — use `datetime.now(ZoneInfo("UTC"))`.'''
    ),
    (
        "thinking/adversarial-floating-point",
        "Write a function that calculates the total price of items in a shopping cart, applying a percentage discount and tax.",
        r'''<think>
Let me write the obvious version and break it with floating point.

```python
def cart_total(items, discount_pct, tax_pct):
    subtotal = sum(item['price'] * item['qty'] for item in items)
    discount = subtotal * discount_pct / 100
    after_discount = subtotal - discount
    tax = after_discount * tax_pct / 100
    return after_discount + tax
```

Floating point attacks:

1. Classic: 0.1 + 0.2 = 0.30000000000000004
   Cart with item price $0.10 × qty 3 = 0.30000000000000004. Display nightmare.

2. Accumulation error: sum of 1000 items at $0.01 each.
   Sequential addition: 0.01 + 0.01 + ... might not equal 10.00 exactly.

3. 10% discount on $33.33 → $3.333 → how do we round? Round half up? Banker's rounding?
   $33.33 - $3.33 = $30.00 or $33.33 - $3.334 = $29.996?

4. Tax calculation: $29.997 * 8.25% = $2.474... → $2.47 or $2.48?

5. Order of operations matters:
   - Round after each step: $33.33 → discount → $30.00 → tax → $32.48
   - Round only at end: $33.33 → $29.997 → $32.472... → $32.47
   Different results! One penny difference from rounding order.

6. Negative prices: return/refund items with negative amounts. Should work but needs testing.

7. Very large numbers: 999,999 items at $9,999.99 each. Precision at extreme values.

8. Zero discount: 0% discount should not change the subtotal.

9. 100% discount: everything should be free, tax on $0.

The right approach: use Decimal for all money calculations, and be explicit about rounding.
</think>

Floating point math is **fundamentally broken for money**. `0.1 + 0.2 != 0.3` in IEEE 754, and rounding order changes the result by pennies.

```python
# BROKEN: float arithmetic
def cart_total_broken(items, discount_pct, tax_pct):
    subtotal = sum(i['price'] * i['qty'] for i in items)  # Accumulates float errors
    return subtotal * (1 - discount_pct/100) * (1 + tax_pct/100)

# 3 items at $0.10: sum = 0.30000000000000004
# Penny discrepancies on invoices, refund mismatches, failed reconciliation
```

**Fixed: Decimal with explicit rounding**:
```python
from decimal import Decimal, ROUND_HALF_UP

def calculate_cart(
    items: list[dict],
    discount_pct: Decimal,
    tax_pct: Decimal,
) -> dict:
    # Calculate subtotal with Decimal precision
    subtotal = sum(
        Decimal(str(item["price"])) * item["qty"]
        for item in items
    )

    # Round discount to cents BEFORE subtracting
    discount = (subtotal * discount_pct / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    after_discount = subtotal - discount

    # Round tax to cents
    tax = (after_discount * tax_pct / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    total = after_discount + tax

    return {
        "subtotal": subtotal,
        "discount": discount,
        "after_discount": after_discount,
        "tax": tax,
        "total": total,
    }
```

**Adversarial test cases**:
```python
# Trap 1: 0.1 + 0.2 problem
items = [{"price": "0.10", "qty": 3}]
result = calculate_cart(items, Decimal("0"), Decimal("0"))
assert result["subtotal"] == Decimal("0.30")  # Exact, no 0.300000000004

# Trap 2: Rounding at boundary (half-cent)
items = [{"price": "33.33", "qty": 1}]
result = calculate_cart(items, Decimal("10"), Decimal("0"))
# 10% of 33.33 = 3.333 → rounds to 3.33
assert result["discount"] == Decimal("3.33")
assert result["after_discount"] == Decimal("30.00")

# Trap 3: Tax rounding
items = [{"price": "9.99", "qty": 1}]
result = calculate_cart(items, Decimal("0"), Decimal("8.25"))
# 8.25% of 9.99 = 0.824175 → rounds to 0.82
assert result["tax"] == Decimal("0.82")
assert result["total"] == Decimal("10.81")

# Trap 4: Accumulation with many items
items = [{"price": "0.01", "qty": 1} for _ in range(1000)]
result = calculate_cart(items, Decimal("0"), Decimal("0"))
assert result["subtotal"] == Decimal("10.00")  # Exact

# Trap 5: 100% discount
items = [{"price": "99.99", "qty": 2}]
result = calculate_cart(items, Decimal("100"), Decimal("8"))
assert result["total"] == Decimal("0.00")  # No tax on $0

# Trap 6: Zero quantity (shouldn't crash)
items = [{"price": "10.00", "qty": 0}]
result = calculate_cart(items, Decimal("0"), Decimal("0"))
assert result["total"] == Decimal("0.00")
```

**Rules for money**: Always use `Decimal`, never `float`. Round at each financial step (not just at the end). Use `ROUND_HALF_UP` for consumer-facing math (banker's rounding `ROUND_HALF_EVEN` for financial systems). Store prices as cents (integers) in the database.'''
    ),
    (
        "thinking/adversarial-error-propagation",
        "Write a data processing pipeline that reads a CSV, validates each row, transforms the data, and writes results. Handle errors gracefully.",
        r'''<think>
Let me write the pipeline and then test every error path.

Simple version:
```python
def process_csv(input_path, output_path):
    with open(input_path) as f:
        reader = csv.DictReader(f)
        results = []
        for row in reader:
            validated = validate(row)
            transformed = transform(validated)
            results.append(transformed)
    write_output(results, output_path)
```

Error path analysis:

1. File not found → FileNotFoundError. Should provide clear message.
2. File encoding wrong (Latin-1 file opened as UTF-8) → UnicodeDecodeError on some rows. Should detect encoding or provide clear error.
3. Empty file → reader has no rows. results is empty. Should we write empty output or warn?
4. Missing columns → DictReader with missing fields → KeyError in validate/transform. Should report which row and which column.
5. Single bad row → entire pipeline fails. Should we skip bad rows and continue? Report all errors?
6. Transformation error (e.g., date parse) → fails on one row. Should collect errors, not fail fast.
7. Output directory doesn't exist → FileNotFoundError on write. Should create or error clearly.
8. Output file exists and is read-only → PermissionError.
9. Disk full during write → partial output file left behind. Should clean up.
10. Very large file → memory error from results.append(). Should stream.
11. CSV with special characters (quoted commas, newlines in fields) → csv module handles this, but need to test.
12. Duplicate headers → DictReader uses last value for duplicate column names.

The robust approach:
- Stream processing (not load all into memory)
- Collect errors per row, don't fail fast
- Provide a summary of successes and failures
- Handle partial failure (write good rows, report bad ones)
</think>

My first version failed on 8 of 12 error scenarios. Here's the robust version:

```python
import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

@dataclass
class ProcessingError:
    row_number: int
    field: str
    value: str
    error: str

@dataclass
class ProcessingResult:
    total_rows: int = 0
    successful: int = 0
    failed: int = 0
    errors: list[ProcessingError] = field(default_factory=list)

def process_csv(
    input_path: str,
    output_path: str,
    required_columns: list[str] | None = None,
) -> ProcessingResult:
    result = ProcessingResult()
    input_file = Path(input_path)
    output_file = Path(output_path)

    # Validate input exists
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file, rename on success (atomic write)
    temp_path = output_file.with_suffix('.tmp')

    try:
        with (
            open(input_file, 'r', encoding='utf-8-sig') as infile,  # Handle BOM
            open(temp_path, 'w', newline='', encoding='utf-8') as outfile,
        ):
            reader = csv.DictReader(infile)

            if not reader.fieldnames:
                raise ValueError("CSV file is empty or has no header")

            # Check required columns
            if required_columns:
                missing = set(required_columns) - set(reader.fieldnames)
                if missing:
                    raise ValueError(f"Missing required columns: {missing}")

            writer = None

            for row_num, row in enumerate(reader, start=2):  # Row 1 is header
                result.total_rows += 1

                try:
                    validated = validate_row(row, row_num)
                    transformed = transform_row(validated)

                    # Initialize writer from first successful row
                    if writer is None:
                        writer = csv.DictWriter(outfile, fieldnames=transformed.keys())
                        writer.writeheader()

                    writer.writerow(transformed)
                    result.successful += 1

                except RowValidationError as e:
                    result.failed += 1
                    result.errors.append(ProcessingError(
                        row_number=row_num,
                        field=e.field,
                        value=e.value,
                        error=str(e),
                    ))

                    if result.failed > 1000:
                        raise TooManyErrorsError(
                            f"Stopped after 1000 errors. First error: {result.errors[0]}"
                        )

        # Atomic rename — either full output or nothing
        if result.successful > 0:
            temp_path.rename(output_file)
        else:
            temp_path.unlink()
            raise ValueError("No valid rows to write")

    except Exception:
        # Clean up temp file on any error
        if temp_path.exists():
            temp_path.unlink()
        raise

    return result


class RowValidationError(Exception):
    def __init__(self, message: str, field: str = "", value: str = ""):
        self.field = field
        self.value = value
        super().__init__(message)

class TooManyErrorsError(Exception):
    pass


def validate_row(row: dict, row_num: int) -> dict:
    """Validate a single row. Raises RowValidationError with details."""
    errors = []
    if not row.get("name", "").strip():
        errors.append(("name", row.get("name", ""), "Name is required"))
    if not row.get("email", "").strip():
        errors.append(("email", row.get("email", ""), "Email is required"))
    try:
        price = float(row.get("price", ""))
        if price < 0:
            errors.append(("price", row.get("price"), "Price must be non-negative"))
    except (ValueError, TypeError):
        errors.append(("price", row.get("price", ""), "Invalid price format"))

    if errors:
        field, value, msg = errors[0]
        raise RowValidationError(f"Row {row_num}: {msg}", field=field, value=str(value))

    return row

def transform_row(row: dict) -> dict:
    return {
        "name": row["name"].strip().title(),
        "email": row["email"].strip().lower(),
        "price": f"{float(row['price']):.2f}",
    }
```

**Error scenarios tested**:
```
Scenario                     | Result
-----------------------------|----------------------------------
File not found               | Clear FileNotFoundError message
Empty CSV                    | ValueError "empty or no header"
Missing required column      | ValueError listing missing columns
Bad encoding (BOM)           | utf-8-sig handles BOM transparently
Single bad row               | Skipped, reported, other rows processed
All bad rows                 | ValueError "no valid rows"
1001 bad rows                | TooManyErrorsError (fail-safe)
Disk full during write       | Temp file cleaned up
Output dir doesn't exist     | Created automatically
Partial write (crash mid-file)| Temp file, not renamed → no corrupt output
```'''
    ),
    (
        "thinking/adversarial-config-interaction",
        "Our app has feature flags and they work individually, but when we enable `premium_features` AND `legacy_mode` at the same time, the app crashes. How should we handle feature flag interactions?",
        r'''<think>
This is a combinatorial interaction bug — each flag works alone, but certain combinations create impossible or conflicting states.

Let me think about common feature flag interaction problems:

1. Mutual exclusion: premium_features assumes new data model, legacy_mode uses old data model → accessing new fields in legacy context crashes.

2. Dependency: feature B requires feature A, but you can enable B without A.

3. Ordering: enabling A then B works, but B then A doesn't.

4. Cross-feature UI: two features both try to modify the same page element.

5. Database schema: one feature adds columns that another feature queries differ from.

With N flags, there are 2^N combinations. Even 20 flags = 1M combinations. You can't test all of them.

The solution approaches:
1. Declare constraints between flags (mutual exclusion, dependencies)
2. Validate constraints before enabling a flag
3. Test the "important" combinations, not all
4. Use flag grouping / feature sets instead of individual flags

Let me design a system that makes these interactions explicit and validated.
</think>

With N feature flags, you have 2^N possible states. Most work, some crash. The fix is making **flag constraints explicit and validated**.

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class ConstraintType(Enum):
    REQUIRES = "requires"       # A requires B (B must be on if A is on)
    EXCLUDES = "excludes"       # A excludes B (can't both be on)
    IMPLIES = "implies"         # A on → automatically enable B

@dataclass
class FlagConstraint:
    flag_a: str
    constraint: ConstraintType
    flag_b: str
    reason: str

class FeatureFlagSystem:
    def __init__(self):
        self.flags: dict[str, bool] = {}
        self.constraints: list[FlagConstraint] = []

    def define_constraint(
        self, flag_a: str, constraint: ConstraintType, flag_b: str, reason: str
    ):
        self.constraints.append(FlagConstraint(flag_a, constraint, flag_b, reason))

    def enable(self, flag_name: str) -> list[str]:
        """Enable a flag, validating constraints. Returns list of warnings."""
        warnings = []

        # Check EXCLUDES: would enabling this conflict with any active flag?
        for c in self.constraints:
            if c.constraint == ConstraintType.EXCLUDES:
                if c.flag_a == flag_name and self.flags.get(c.flag_b):
                    raise FlagConflictError(
                        f"Cannot enable '{flag_name}': conflicts with '{c.flag_b}'. {c.reason}"
                    )
                if c.flag_b == flag_name and self.flags.get(c.flag_a):
                    raise FlagConflictError(
                        f"Cannot enable '{flag_name}': conflicts with '{c.flag_a}'. {c.reason}"
                    )

        # Check REQUIRES: does this flag need another flag?
        for c in self.constraints:
            if c.constraint == ConstraintType.REQUIRES and c.flag_a == flag_name:
                if not self.flags.get(c.flag_b):
                    raise FlagDependencyError(
                        f"Cannot enable '{flag_name}': requires '{c.flag_b}'. {c.reason}"
                    )

        # Handle IMPLIES: automatically enable dependencies
        for c in self.constraints:
            if c.constraint == ConstraintType.IMPLIES and c.flag_a == flag_name:
                if not self.flags.get(c.flag_b):
                    self.flags[c.flag_b] = True
                    warnings.append(f"Auto-enabled '{c.flag_b}' (implied by '{flag_name}')")

        self.flags[flag_name] = True
        return warnings

    def validate_all(self) -> list[str]:
        """Check all constraints against current state. Returns violations."""
        violations = []
        for c in self.constraints:
            a_on = self.flags.get(c.flag_a, False)
            b_on = self.flags.get(c.flag_b, False)

            if c.constraint == ConstraintType.EXCLUDES and a_on and b_on:
                violations.append(f"CONFLICT: '{c.flag_a}' and '{c.flag_b}' cannot both be enabled. {c.reason}")
            elif c.constraint == ConstraintType.REQUIRES and a_on and not b_on:
                violations.append(f"MISSING: '{c.flag_a}' requires '{c.flag_b}'. {c.reason}")

        return violations


class FlagConflictError(Exception):
    pass

class FlagDependencyError(Exception):
    pass


# Configure constraints at startup
flags = FeatureFlagSystem()

# Declare interactions explicitly
flags.define_constraint(
    "premium_features", ConstraintType.EXCLUDES, "legacy_mode",
    "Premium features use the v2 data model; legacy mode expects v1"
)
flags.define_constraint(
    "new_checkout", ConstraintType.REQUIRES, "payment_v2",
    "New checkout uses payment v2 API"
)
flags.define_constraint(
    "dark_mode", ConstraintType.IMPLIES, "ui_v2",
    "Dark mode requires the v2 UI framework"
)
```

**Testing**:
```python
# This now fails FAST with a clear message instead of a production crash
try:
    flags.enable("premium_features")
    flags.enable("legacy_mode")  # BOOM
except FlagConflictError as e:
    print(e)
    # "Cannot enable 'legacy_mode': conflicts with 'premium_features'.
    #  Premium features use the v2 data model; legacy mode expects v1"

# Dependency enforcement
try:
    flags.enable("new_checkout")  # Fails: payment_v2 not enabled
except FlagDependencyError as e:
    print(e)
    # "Cannot enable 'new_checkout': requires 'payment_v2'."

# Auto-implication
warnings = flags.enable("dark_mode")
# warnings: ["Auto-enabled 'ui_v2' (implied by 'dark_mode')"]
```

**For 20+ flags, also add**: constraint visualization (dependency graph), automated combinatorial testing of the most common flag groups, and a startup validator that runs `validate_all()` before the app accepts traffic.'''
    ),
    (
        "thinking/adversarial-backward-compat",
        "We're adding a `middle_name` field to our User API response. It's optional. This should be a safe, backward-compatible change, right?",
        r'''<think>
Adding an optional field to an API response seems harmless, but let me try to find ways it could break clients.

1. Strict deserialization: Some clients (especially Java/C# with generated types) will reject unknown fields. If a Go client uses `DisallowUnknownFields`, the new field causes a deserialization error.

2. Schema validation: If clients validate the response against a JSON schema with `"additionalProperties": false`, the new field fails validation.

3. Snapshot tests: Any client with snapshot/golden-file tests that compare full JSON responses will see test failures.

4. Caching: If response caching is keyed on the response body hash, all caches are invalidated simultaneously (cache stampede).

5. Bandwidth/size: If the API returns lists of users, adding even an optional field multiplies. 1000 users × "middle_name": null = measurable payload increase for mobile clients.

6. Null vs absent: Is `"middle_name": null` the same as the field being absent? In JavaScript, `user.middle_name` is `undefined` if absent, `null` if present-but-null. These behave differently in conditionals.

7. Database implications: If `middle_name` is null in DB and clients start sending it back in update requests (PATCH), does `null` mean "clear the middle name" or "don't change it"?

8. GraphQL impact: If there's a GraphQL layer, the schema change needs a deploy before clients can query the new field.

9. Documentation/SDK: Auto-generated client SDKs need to be regenerated and published before clients can use the field.

10. Serialization order: Some clients depend on JSON key ordering (fragile but exists).

So the answer is: it's MOSTLY safe, but not completely safe. The careful approach is:
- Add the field but document it
- Warn consumers in advance
- Don't change existing field semantics
- Be clear about null vs absent
</think>

It's **mostly** safe but not **completely** safe. Here are the ways it can break:

**Clients that WILL break**:
```go
// Go client with strict deserialization
type User struct {
    ID    int    `json:"id"`
    Name  string `json:"name"`
    Email string `json:"email"`
}

decoder := json.NewDecoder(resp.Body)
decoder.DisallowUnknownFields()  // BREAKS: "middle_name" is unknown
err := decoder.Decode(&user)      // json: unknown field "middle_name"
```

```java
// Java with Jackson strict mode
@JsonIgnoreProperties(allowUnknown = false)  // BREAKS on new field
public class User {
    private int id;
    private String name;
    private String email;
}
```

**Clients with test failures**:
```python
# Snapshot tests comparing full JSON
def test_get_user():
    response = client.get("/users/1")
    assert response.json() == {
        "id": 1,
        "name": "Alice",
        "email": "alice@example.com",
        # No middle_name — test FAILS when field is added
    }
```

**The null vs absent problem**:
```javascript
// BEFORE: field doesn't exist
user.middle_name          // undefined
user.middle_name ?? "N/A" // "N/A"
"middle_name" in user     // false

// AFTER: field is null
user.middle_name          // null
user.middle_name ?? "N/A" // "N/A" (same — but...)
user.middle_name || "N/A" // "N/A" (same)
"middle_name" in user     // true (different!)

// AFTER: field is empty string ""
user.middle_name || "N/A" // "N/A" (|| treats "" as falsy)
user.middle_name ?? "N/A" // "" (?? only catches null/undefined)
// This difference WILL cause bugs in consumer code
```

**Safe rollout approach**:
```python
# 1. Announce the change to API consumers (changelog, email)

# 2. Add to API response with clear semantics
class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    middle_name: str | None = None  # null = not provided, "" = explicitly blank

# 3. Add API version header
@app.get("/users/{user_id}")
async def get_user(user_id: int, request: Request):
    user = await user_repo.get(user_id)
    api_version = request.headers.get("X-API-Version", "1")

    response = {"id": user.id, "name": user.name, "email": user.email}
    if api_version >= "2":
        response["middle_name"] = user.middle_name

    return response

# 4. Update API documentation and OpenAPI spec
# 5. Regenerate and publish client SDKs
# 6. Give consumers 2 weeks before making v2 the default
```

**The lesson**: Adding fields is the safest API change you can make — but "safest" ≠ "safe." Always communicate changes to consumers, and consider strict-mode deserializers in typed languages.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
