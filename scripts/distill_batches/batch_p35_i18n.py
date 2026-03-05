"""Internationalization — i18n, date/time handling, localization patterns."""

PAIRS = [
    (
        "python/datetime-handling",
        "Show Python date/time best practices: timezone-aware datetimes, parsing, formatting, duration calculations, and common pitfalls.",
        '''Python datetime best practices:

```python
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo  # Python 3.9+
from typing import Optional

# --- Always use timezone-aware datetimes ---

# GOOD: Always UTC internally
now_utc = datetime.now(timezone.utc)

# GOOD: Specific timezone
now_tokyo = datetime.now(ZoneInfo("Asia/Tokyo"))
now_ny = datetime.now(ZoneInfo("America/New_York"))

# BAD: Naive datetime (no timezone)
# now_bad = datetime.now()  # Don't do this!

# --- Conversion between timezones ---

def to_user_timezone(dt: datetime, tz_name: str) -> datetime:
    """Convert UTC datetime to user's timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz_name))

# UTC -> user timezone for display
utc_time = datetime(2024, 6, 15, 14, 30, tzinfo=timezone.utc)
local_time = to_user_timezone(utc_time, "America/New_York")
# 2024-06-15 10:30:00-04:00 (EDT)

# --- Parsing dates ---

def parse_datetime(value: str) -> datetime:
    """Parse common datetime formats, always return UTC."""
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",      # ISO 8601 with microseconds
        "%Y-%m-%dT%H:%M:%SZ",           # ISO 8601
        "%Y-%m-%dT%H:%M:%S%z",          # ISO 8601 with offset
        "%Y-%m-%d %H:%M:%S",            # Common format
        "%Y-%m-%d",                      # Date only
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {value}")

# ISO 8601 parsing (Python 3.11+)
dt = datetime.fromisoformat("2024-06-15T14:30:00+00:00")


# --- Formatting ---

def format_relative(dt: datetime) -> str:
    """Human-readable relative time (e.g., '2 hours ago')."""
    now = datetime.now(timezone.utc)
    diff = now - dt

    if diff < timedelta(seconds=60):
        return "just now"
    elif diff < timedelta(hours=1):
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff < timedelta(days=30):
        days = diff.days
        return f"{days} day{'s' if days != 1 else ''} ago"
    elif diff < timedelta(days=365):
        months = diff.days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        years = diff.days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"


# --- Duration calculations ---

def business_days_between(start: date, end: date) -> int:
    """Count business days between two dates."""
    if start > end:
        start, end = end, start
    days = 0
    current = start
    while current < end:
        if current.weekday() < 5:  # Mon=0, Fri=4
            days += 1
        current += timedelta(days=1)
    return days

def add_business_days(start: date, days: int) -> date:
    """Add N business days to a date."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


# --- Date ranges ---

def date_range(start: date, end: date, step: timedelta = timedelta(days=1)):
    """Generate dates in range."""
    current = start
    while current <= end:
        yield current
        current += step

def month_boundaries(year: int, month: int) -> tuple[date, date]:
    """Get first and last day of a month."""
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


# --- Common pitfalls ---

# 1. DST transitions: "2 AM" might not exist or might occur twice
def safe_localize(dt_utc: datetime, tz_name: str) -> datetime:
    """Safely convert UTC to local, handling DST."""
    return dt_utc.astimezone(ZoneInfo(tz_name))
    # Always convert FROM UTC, never construct local directly

# 2. Comparing datetimes: always ensure same timezone
def datetimes_equal(a: datetime, b: datetime) -> bool:
    return a.astimezone(timezone.utc) == b.astimezone(timezone.utc)

# 3. Storing in database: always store UTC
#    Convert to local only for display

# 4. API serialization: always ISO 8601 with timezone
def serialize_datetime(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
```

Rules:
1. **Store UTC** — always store datetimes in UTC in databases/APIs
2. **Convert for display** — convert to user's timezone only at presentation layer
3. **Use `zoneinfo`** — Python 3.9+ standard library, replaces `pytz`
4. **ISO 8601** — always use for serialization/API communication
5. **Avoid naive datetimes** — always attach timezone info'''
    ),
    (
        "python/i18n-localization",
        "Show internationalization patterns in Python: message translation, number/currency formatting, pluralization, and locale-aware sorting.",
        '''Internationalization (i18n) patterns in Python:

```python
import locale
from babel import Locale, numbers, dates
from babel.support import Translations
from typing import Optional
from pathlib import Path
from functools import lru_cache
import gettext

# --- Message translation with gettext ---

LOCALE_DIR = Path("locales")

@lru_cache(maxsize=20)
def get_translator(lang: str) -> gettext.GNUTranslations:
    """Load translation catalog for a language."""
    try:
        return gettext.translation(
            "messages", localedir=LOCALE_DIR, languages=[lang]
        )
    except FileNotFoundError:
        return gettext.NullTranslations()

def translate(key: str, lang: str = "en", **kwargs) -> str:
    """Translate a message with interpolation."""
    translator = get_translator(lang)
    translated = translator.gettext(key)
    if kwargs:
        translated = translated.format(**kwargs)
    return translated

def translate_plural(singular: str, plural: str, n: int,
                     lang: str = "en", **kwargs) -> str:
    """Translate with pluralization."""
    translator = get_translator(lang)
    translated = translator.ngettext(singular, plural, n)
    return translated.format(n=n, **kwargs)

# Usage:
# _("Welcome, {name}!") -> translate("Welcome, {name}!", "es", name="Alice")
# ngettext("{n} item", "{n} items", count) -> "1 item" / "5 items"


# --- Number and currency formatting with Babel ---

class Formatter:
    def __init__(self, locale_str: str = "en_US"):
        self.locale = Locale.parse(locale_str)

    def number(self, value: float) -> str:
        return numbers.format_decimal(value, locale=self.locale)

    def currency(self, amount: float, currency: str = "USD") -> str:
        return numbers.format_currency(
            amount, currency, locale=self.locale
        )

    def percent(self, value: float) -> str:
        return numbers.format_percent(value, locale=self.locale)

    def compact_number(self, value: float) -> str:
        return numbers.format_compact_decimal(
            value, locale=self.locale
        )

    def date(self, dt, format: str = "medium") -> str:
        return dates.format_date(dt, format=format, locale=self.locale)

    def datetime(self, dt, format: str = "medium") -> str:
        return dates.format_datetime(dt, format=format, locale=self.locale)

    def relative_time(self, dt) -> str:
        return dates.format_timedelta(
            dt - datetime.now(timezone.utc),
            locale=self.locale, add_direction=True,
        )

# Examples:
fmt_us = Formatter("en_US")
fmt_de = Formatter("de_DE")
fmt_ja = Formatter("ja_JP")

# Numbers:
# fmt_us.number(1234567.89)  -> "1,234,567.89"
# fmt_de.number(1234567.89)  -> "1.234.567,89"
# fmt_ja.number(1234567.89)  -> "1,234,567.89"

# Currency:
# fmt_us.currency(1234.50)         -> "$1,234.50"
# fmt_de.currency(1234.50, "EUR")  -> "1.234,50 €"
# fmt_ja.currency(1234.50, "JPY")  -> "￥1,235"

# Compact:
# fmt_us.compact_number(1500000)  -> "1.5M"
# fmt_de.compact_number(1500000)  -> "1,5 Mio."
# fmt_ja.compact_number(1500000)  -> "150万"


# --- i18n-aware FastAPI middleware ---

from fastapi import FastAPI, Request

SUPPORTED_LANGUAGES = ["en", "es", "de", "fr", "ja"]
DEFAULT_LANGUAGE = "en"

def get_language(request: Request) -> str:
    """Determine user language from header or query."""
    # Check query param first
    lang = request.query_params.get("lang")
    if lang in SUPPORTED_LANGUAGES:
        return lang

    # Parse Accept-Language header
    accept = request.headers.get("Accept-Language", "")
    for part in accept.split(","):
        lang_tag = part.split(";")[0].strip()[:2].lower()
        if lang_tag in SUPPORTED_LANGUAGES:
            return lang_tag

    return DEFAULT_LANGUAGE

# Use in routes:
# @app.get("/products")
# async def list_products(lang: str = Depends(get_language)):
#     fmt = Formatter(f"{lang}_{lang.upper()}")
#     ...
```

Best practices:
1. **Externalize strings** — use gettext `.po`/`.mo` files, not hardcoded
2. **Pluralization** — `ngettext` handles language-specific plural rules
3. **Babel for formatting** — locale-aware numbers, dates, currencies
4. **Accept-Language** — respect browser preference, allow override
5. **Store locale-neutral** — UTC dates, raw numbers; format only for display'''
    ),
]
"""
