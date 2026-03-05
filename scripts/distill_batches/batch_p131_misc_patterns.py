"""Miscellaneous patterns — date/time handling, money, and configuration."""

PAIRS = [
    (
        "python/datetime-patterns",
        "Show Python datetime patterns: timezone handling, date arithmetic, parsing, and recurring schedules.",
        '''Python datetime patterns:

```python
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Iterator
import calendar


# --- Always use timezone-aware datetimes ---

# UTC now (always use this for storage/APIs)
now_utc = datetime.now(timezone.utc)

# Specific timezone
eastern = ZoneInfo("America/New_York")
tokyo = ZoneInfo("Asia/Tokyo")
now_eastern = datetime.now(eastern)
now_tokyo = datetime.now(tokyo)

# Convert between timezones
utc_time = datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc)
eastern_time = utc_time.astimezone(eastern)  # 2024-06-15 10:00 EDT
tokyo_time = utc_time.astimezone(tokyo)      # 2024-06-15 23:00 JST


# --- Parsing and formatting ---

# ISO 8601 (standard format)
dt = datetime.fromisoformat("2024-06-15T14:30:00+00:00")
dt.isoformat()  # "2024-06-15T14:30:00+00:00"

# Custom format
dt.strftime("%B %d, %Y at %I:%M %p")  # "June 15, 2024 at 02:30 PM"
dt.strftime("%Y-%m-%d")               # "2024-06-15"

# Parse custom format
parsed = datetime.strptime("15/06/2024 14:30", "%d/%m/%Y %H:%M")
parsed = parsed.replace(tzinfo=timezone.utc)  # Always add timezone!


# --- Date arithmetic ---

# Add/subtract time
tomorrow = now_utc + timedelta(days=1)
last_week = now_utc - timedelta(weeks=1)
in_2_hours = now_utc + timedelta(hours=2)

# Difference between dates
delta = datetime(2024, 12, 31, tzinfo=timezone.utc) - now_utc
print(f"{delta.days} days remaining")

# First/last day of month
first_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
_, last_day = calendar.monthrange(now_utc.year, now_utc.month)
last_of_month = now_utc.replace(day=last_day, hour=23, minute=59, second=59)

# Start/end of day
start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
end_of_day = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999)

# Next Monday
def next_weekday(d: date, weekday: int) -> date:
    """Get next occurrence of weekday (0=Monday, 6=Sunday)."""
    days_ahead = weekday - d.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)


# --- Date ranges ---

def date_range(start: date, end: date, step: timedelta = timedelta(days=1)) -> Iterator[date]:
    """Generate dates in range [start, end)."""
    current = start
    while current < end:
        yield current
        current += step

# for d in date_range(date(2024, 1, 1), date(2024, 1, 31)):
#     print(d)

# Weekly range
# for d in date_range(date(2024, 1, 1), date(2024, 12, 31), timedelta(weeks=1)):
#     print(d)


# --- Business days ---

def add_business_days(start: date, days: int) -> date:
    """Add N business days (skip weekends)."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Monday=0 to Friday=4
            added += 1
    return current


def business_days_between(start: date, end: date) -> int:
    """Count business days between two dates."""
    count = 0
    current = start
    while current < end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


# --- Relative time (human-readable) ---

def time_ago(dt: datetime) -> str:
    """Convert datetime to relative string."""
    now = datetime.now(timezone.utc)
    delta = now - dt

    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if seconds < 604800:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''} ago"

    return dt.strftime("%b %d, %Y")

# time_ago(now_utc - timedelta(minutes=5))   # "5 minutes ago"
# time_ago(now_utc - timedelta(hours=3))     # "3 hours ago"
# time_ago(now_utc - timedelta(days=45))     # "May 01, 2024"


# --- Timezone-safe comparison ---

def is_same_day(dt1: datetime, dt2: datetime, tz: ZoneInfo | None = None) -> bool:
    """Check if two datetimes are on the same calendar day in given timezone."""
    if tz:
        dt1 = dt1.astimezone(tz)
        dt2 = dt2.astimezone(tz)
    return dt1.date() == dt2.date()
```

Datetime patterns:
1. **Always use `timezone.utc`** — store/compare in UTC, convert to local for display
2. **`ZoneInfo`** — stdlib timezone support (replaces pytz), handles DST automatically
3. **`fromisoformat()`** — parse ISO 8601 strings (the universal datetime format)
4. **Business days** — skip weekends for delivery/SLA calculations
5. **`time_ago()`** — human-readable relative time ("3 hours ago")'''
    ),
    (
        "patterns/money-handling",
        "Show money and currency handling patterns: Decimal precision, currency conversion, and rounding.",
        '''Money handling patterns:

```python
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, getcontext
from dataclasses import dataclass
from typing import Self


# NEVER use float for money!
# float: 0.1 + 0.2 = 0.30000000000000004
# Decimal: Decimal("0.1") + Decimal("0.2") = Decimal("0.3")


# --- Money value object ---

@dataclass(frozen=True)
class Money:
    """Immutable money type with currency and precise arithmetic."""
    amount: Decimal
    currency: str

    def __post_init__(self):
        # Ensure amount is Decimal
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))

    @classmethod
    def from_cents(cls, cents: int, currency: str = "USD") -> Self:
        return cls(Decimal(cents) / 100, currency)

    @classmethod
    def zero(cls, currency: str = "USD") -> Self:
        return cls(Decimal("0"), currency)

    @property
    def cents(self) -> int:
        return int(self.amount * 100)

    def _check_currency(self, other: "Money"):
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot operate on {self.currency} and {other.currency}"
            )

    def __add__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | float | Decimal) -> "Money":
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __truediv__(self, divisor: int | float | Decimal) -> "Money":
        return Money(self.amount / Decimal(str(divisor)), self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self.amount > other.amount

    def round(self, places: int = 2) -> "Money":
        rounded = self.amount.quantize(
            Decimal(10) ** -places, rounding=ROUND_HALF_UP,
        )
        return Money(rounded, self.currency)

    def allocate(self, ratios: list[int]) -> list["Money"]:
        """Split money by ratios without losing cents.

        allocate([1, 1, 1]) splits $10.00 into [$3.34, $3.33, $3.33]
        """
        total_ratio = sum(ratios)
        total_cents = self.cents
        results = []
        allocated = 0

        for i, ratio in enumerate(ratios):
            if i == len(ratios) - 1:
                # Last one gets remainder (no rounding loss)
                share_cents = total_cents - allocated
            else:
                share_cents = int(total_cents * ratio / total_ratio)
            allocated += share_cents
            results.append(Money.from_cents(share_cents, self.currency))

        return results

    def format(self, locale: str = "en_US") -> str:
        """Format as localized currency string."""
        from babel.numbers import format_currency
        return format_currency(self.amount, self.currency, locale=locale)

    def __str__(self) -> str:
        symbols = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
        symbol = symbols.get(self.currency, self.currency + " ")
        if self.currency == "JPY":
            return f"{symbol}{self.amount:.0f}"
        return f"{symbol}{self.amount:.2f}"

    def __repr__(self) -> str:
        return f"Money({self.amount}, '{self.currency}')"


# --- Usage ---

price = Money(Decimal("29.99"), "USD")
tax = price * Decimal("0.08875")
total = (price + tax).round()
print(total)  # $32.65

# Split bill three ways
shares = total.allocate([1, 1, 1])
# [$10.89, $10.88, $10.88] — no lost cents!

# Discount
discount = price * Decimal("0.15")
final = (price - discount).round()


# --- Percentage calculations ---

def apply_tax(amount: Money, rate: Decimal) -> Money:
    """Apply tax rate (e.g., 0.08875 for 8.875%)."""
    tax = (amount * rate).round()
    return amount + tax

def calculate_discount(amount: Money, percent: Decimal) -> Money:
    """Apply percentage discount."""
    discount = (amount * (percent / 100)).round()
    return amount - discount

def calculate_tip(amount: Money, percent: int) -> dict:
    """Calculate tip and total."""
    tip = (amount * Decimal(percent) / 100).round()
    return {"subtotal": amount, "tip": tip, "total": amount + tip}
```

Money handling patterns:
1. **`Decimal` not `float`** — exact arithmetic prevents rounding errors
2. **`Money` value object** — currency-safe operations, can\'t add USD to EUR
3. **`allocate(ratios)`** — split money without losing cents (remainder to last)
4. **`ROUND_HALF_UP`** — banker\'s rounding for financial calculations
5. **`from_cents()`** — store as integers in database, construct as needed'''
    ),
    (
        "python/context-managers",
        "Show Python context manager patterns: resource management, timing, database transactions, and nested contexts.",
        '''Python context manager patterns:

```python
from contextlib import contextmanager, asynccontextmanager, suppress, ExitStack
from typing import Generator, AsyncGenerator
import time
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


# --- Basic context manager (class-based) ---

class Timer:
    """Measure execution time of a code block."""

    def __init__(self, name: str = ""):
        self.name = name
        self.elapsed = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc_info) -> None:
        self.elapsed = time.monotonic() - self._start
        if self.name:
            logger.info("%s took %.3fs", self.name, self.elapsed)

# with Timer("database query") as t:
#     results = db.query(...)
# print(f"Query took {t.elapsed:.3f}s")


# --- Generator-based context manager ---

@contextmanager
def temporary_directory(prefix: str = "app_") -> Generator[Path, None, None]:
    """Create temp directory, clean up on exit."""
    tmpdir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield tmpdir
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


@contextmanager
def override_env(**env_vars) -> Generator[None, None, None]:
    """Temporarily override environment variables (useful in tests)."""
    import os
    old_values = {}
    for key, value in env_vars.items():
        old_values[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

# with override_env(DATABASE_URL="sqlite:///:memory:", DEBUG="true"):
#     run_tests()


# --- Async context manager ---

@asynccontextmanager
async def db_transaction(conn) -> AsyncGenerator:
    """Database transaction with automatic commit/rollback."""
    tx = await conn.begin()
    try:
        yield conn
        await tx.commit()
    except Exception:
        await tx.rollback()
        raise


@asynccontextmanager
async def http_client(**kwargs) -> AsyncGenerator:
    """Managed HTTP client with connection pooling."""
    import httpx
    client = httpx.AsyncClient(**kwargs)
    try:
        yield client
    finally:
        await client.aclose()


# --- Reentrant lock context manager ---

@contextmanager
def acquire_file_lock(path: Path, timeout: float = 10.0):
    """File-based lock for cross-process synchronization."""
    lock_path = path.with_suffix(".lock")
    start = time.monotonic()

    while True:
        try:
            lock_path.touch(exist_ok=False)
            break
        except FileExistsError:
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"Could not acquire lock: {lock_path}")
            time.sleep(0.1)

    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


# --- ExitStack for dynamic context managers ---

def process_files(file_paths: list[Path]):
    """Open multiple files dynamically."""
    with ExitStack() as stack:
        files = [
            stack.enter_context(open(path))
            for path in file_paths
        ]
        # All files are open here
        for f in files:
            process(f.read())
    # All files automatically closed


# --- suppress (ignore specific exceptions) ---

# Instead of:
# try:
#     os.remove("temp.txt")
# except FileNotFoundError:
#     pass

# Use:
with suppress(FileNotFoundError):
    Path("temp.txt").unlink()


# --- Combining context managers ---

# Python 3.10+ parenthesized context managers
# with (
#     Timer("full pipeline"),
#     temporary_directory() as tmpdir,
#     open("output.txt", "w") as outfile,
# ):
#     ...


# --- Context manager as decorator ---

@contextmanager
def log_exceptions(operation: str):
    """Log exceptions without suppressing them."""
    try:
        yield
    except Exception as e:
        logger.error("Error in %s: %s", operation, e)
        raise

# with log_exceptions("data import"):
#     import_data()
```

Context manager patterns:
1. **`@contextmanager`** — generator-based: code before `yield` = setup, after = cleanup
2. **`@asynccontextmanager`** — async version for database transactions, HTTP clients
3. **`ExitStack`** — dynamically manage variable number of context managers
4. **`suppress(ExcType)`** — clean way to ignore specific expected exceptions
5. **`__enter__`/`__exit__`** — class-based for stateful managers (Timer, Lock)'''
    ),
]
"""
