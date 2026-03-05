"""Regular expressions — patterns, parsing, and text extraction."""

PAIRS = [
    (
        "python/regex-patterns",
        "Show Python regex patterns: common patterns, named groups, lookahead/lookbehind, and text extraction.",
        '''Python regex patterns:

```python
import re
from typing import Iterator


# --- Common patterns ---

PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "url": r"https?://[^\s<>\"']+",
    "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "phone_us": r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    "date_iso": r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])",
    "time_24h": r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?",
    "hex_color": r"#(?:[0-9a-fA-F]{3}){1,2}\b",
    "uuid": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    "semver": r"\bv?\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?(?:\+[a-zA-Z0-9.]+)?",
    "slug": r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
}


# --- Named groups ---

# Parse log lines
LOG_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
    r"\s+\[(?P<level>\w+)\]"
    r"\s+(?P<logger>[\w.]+):"
    r"\s+(?P<message>.*)"
)

def parse_log_line(line: str) -> dict | None:
    match = LOG_PATTERN.match(line)
    if match:
        return match.groupdict()
    return None

# parse_log_line("2024-06-15 14:30:00 [ERROR] myapp.auth: Login failed for user@test.com")
# {'timestamp': '2024-06-15 14:30:00', 'level': 'ERROR', 'logger': 'myapp.auth', 'message': '...'}


# Parse URL components
URL_PATTERN = re.compile(
    r"(?P<scheme>https?)://"
    r"(?P<host>[^/:]+)"
    r"(?::(?P<port>\d+))?"
    r"(?P<path>/[^?#]*)?"
    r"(?:\?(?P<query>[^#]*))?"
    r"(?:#(?P<fragment>.*))?"
)


# --- Lookahead and lookbehind ---

# Password validation (all conditions must be true)
def validate_password(password: str) -> list[str]:
    errors = []
    if not re.search(r"(?=.*[A-Z])", password):
        errors.append("Must contain uppercase letter")
    if not re.search(r"(?=.*[a-z])", password):
        errors.append("Must contain lowercase letter")
    if not re.search(r"(?=.*\d)", password):
        errors.append("Must contain digit")
    if not re.search(r"(?=.*[!@#$%^&*])", password):
        errors.append("Must contain special character")
    if len(password) < 12:
        errors.append("Must be at least 12 characters")
    return errors


# Lookbehind: extract values after specific prefixes
text = "Price: $42.99, Discount: $5.00, Tax: $3.50"
prices = re.findall(r"(?<=\$)\d+\.\d{2}", text)
# ['42.99', '5.00', '3.50']

# Negative lookbehind: match 'test' not preceded by 'unit'
re.findall(r"(?<!unit)test", "unittest mytest pytest")
# ['test', 'test']  — from mytest and pytest

# Lookahead: match word followed by specific word
re.findall(r"\w+(?=\s+error)", "connection error timeout error success")
# ['connection', 'timeout']


# --- Substitution with functions ---

def redact_emails(text: str) -> str:
    """Replace emails with redacted version."""
    def replace(match):
        email = match.group()
        local, domain = email.split("@")
        return f"{local[0]}***@{domain}"

    return re.sub(PATTERNS["email"], replace, text)

# redact_emails("Contact alice@example.com or bob@test.com")
# "Contact a***@example.com or b***@test.com"


# Camel case to snake case
def camel_to_snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()

# camel_to_snake("getUserHTTPResponse")  # "get_user_http_response"


# --- Text extraction ---

def extract_markdown_links(text: str) -> list[tuple[str, str]]:
    """Extract [text](url) links from markdown."""
    return re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)


def extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Extract ```lang\\ncode``` blocks from markdown."""
    return re.findall(r"```(\w*)\n(.*?)```", text, re.DOTALL)


def extract_between(text: str, start: str, end: str) -> list[str]:
    """Extract text between delimiters."""
    pattern = re.escape(start) + r"(.*?)" + re.escape(end)
    return re.findall(pattern, text, re.DOTALL)


# --- Compiled patterns with verbose mode ---

# Verbose mode: readable regex with comments
CREDIT_CARD = re.compile(r"""
    \b
    (?:
        4[0-9]{12}(?:[0-9]{3})?       # Visa
        | 5[1-5][0-9]{14}             # Mastercard
        | 3[47][0-9]{13}              # Amex
        | 6(?:011|5[0-9]{2})[0-9]{12} # Discover
    )
    \b
""", re.VERBOSE)


# --- Tokenizer using regex ---

def tokenize(expression: str) -> Iterator[tuple[str, str]]:
    """Tokenize a math expression."""
    token_spec = [
        ("NUMBER",  r"\d+(?:\.\d+)?"),
        ("PLUS",    r"\+"),
        ("MINUS",   r"-"),
        ("TIMES",   r"\*"),
        ("DIVIDE",  r"/"),
        ("LPAREN",  r"\("),
        ("RPAREN",  r"\)"),
        ("SKIP",    r"\s+"),
    ]
    pattern = "|".join(f"(?P<{name}>{regex})" for name, regex in token_spec)

    for match in re.finditer(pattern, expression):
        kind = match.lastgroup
        value = match.group()
        if kind != "SKIP":
            yield kind, value

# list(tokenize("3.14 * (2 + 5)"))
# [('NUMBER', '3.14'), ('TIMES', '*'), ('LPAREN', '('),
#  ('NUMBER', '2'), ('PLUS', '+'), ('NUMBER', '5'), ('RPAREN', ')')]
```

Regex patterns:
1. **Named groups `(?P<name>...)`** — readable extraction with `.groupdict()`
2. **Lookahead `(?=...)` / lookbehind `(?<=...)`** — assert context without consuming
3. **`re.sub()` with function** — dynamic replacement based on match content
4. **`re.VERBOSE`** — multi-line regex with comments for readability
5. **`re.finditer()`** — memory-efficient tokenizer for streaming text processing'''
    ),
    (
        "python/text-processing",
        "Show Python text processing patterns: parsing structured text, template engines, and diffing.",
        '''Python text processing patterns:

```python
import difflib
import textwrap
from string import Formatter
from typing import Any


# --- Structured text parsing ---

def parse_ini_like(text: str) -> dict[str, dict[str, str]]:
    """Parse INI-style config text."""
    result = {}
    current_section = "default"
    result[current_section] = {}

    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            result[current_section] = {}
        elif "=" in line:
            key, _, value = line.partition("=")
            result[current_section][key.strip()] = value.strip()

    return result


def parse_key_value_block(text: str) -> dict[str, str]:
    """Parse 'Key: Value' format (like HTTP headers)."""
    result = {}
    current_key = None

    for line in text.splitlines():
        if ":" in line and not line[0].isspace():
            key, _, value = line.partition(":")
            current_key = key.strip()
            result[current_key] = value.strip()
        elif current_key and line.startswith((" ", "\\t")):
            # Continuation line
            result[current_key] += " " + line.strip()

    return result


# --- Diffing ---

def unified_diff(old: str, new: str, filename: str = "file") -> str:
    """Generate unified diff between two strings."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    return "".join(diff)


def html_diff(old: str, new: str) -> str:
    """Generate HTML side-by-side diff."""
    differ = difflib.HtmlDiff(tabsize=4, wrapcolumn=80)
    return differ.make_file(
        old.splitlines(),
        new.splitlines(),
        fromdesc="Original",
        todesc="Modified",
    )


def similarity_ratio(a: str, b: str) -> float:
    """Get similarity ratio between two strings (0.0 to 1.0)."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def find_closest_match(word: str, candidates: list[str], cutoff: float = 0.6) -> str | None:
    """Find closest match (useful for 'did you mean?' suggestions)."""
    matches = difflib.get_close_matches(word, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None

# find_closest_match("collor", ["color", "colour", "collar"])  # "color"


# --- Safe string templating ---

class SafeFormatter(Formatter):
    """Format strings without raising on missing keys."""

    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            return kwargs.get(key, f"{{{key}}}")
        return super().get_value(key, args, kwargs)

    def format_field(self, value, format_spec):
        if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
            return value  # Return placeholder as-is
        return super().format_field(value, format_spec)

fmt = SafeFormatter()
fmt.format("Hello {name}, your {missing} is ready", name="Alice")
# "Hello Alice, your {missing} is ready"


# --- Text wrapping and formatting ---

def format_as_table(
    rows: list[dict],
    columns: list[str] | None = None,
    max_width: int = 40,
) -> str:
    """Format list of dicts as aligned text table."""
    if not rows:
        return ""

    columns = columns or list(rows[0].keys())

    # Calculate column widths
    widths = {}
    for col in columns:
        values = [str(row.get(col, "")) for row in rows]
        widths[col] = min(
            max(len(col), max((len(v) for v in values), default=0)),
            max_width,
        )

    # Build format string
    header = " | ".join(f"{col:<{widths[col]}}" for col in columns)
    separator = "-+-".join("-" * widths[col] for col in columns)

    lines = [header, separator]
    for row in rows:
        line = " | ".join(
            f"{str(row.get(col, '')):<{widths[col]}}"[:widths[col]]
            for col in columns
        )
        lines.append(line)

    return "\\n".join(lines)


# --- Slug generation ---

import re
import unicodedata

def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    # Normalize unicode (é -> e)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    # Lowercase and replace non-alphanumeric with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())
    # Remove leading/trailing hyphens
    return text.strip("-")

# slugify("Hello World! Café & Bar")  # "hello-world-cafe-bar"


# --- Truncate with word boundary ---

def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text at word boundary."""
    if len(text) <= max_length:
        return text
    truncated = text[:max_length - len(suffix)]
    # Find last space
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + suffix
```

Text processing patterns:
1. **`difflib.unified_diff()`** — generate git-style diffs between strings
2. **`get_close_matches()`** — fuzzy matching for "did you mean?" suggestions
3. **`SafeFormatter`** — template strings that don't crash on missing keys
4. **`unicodedata.normalize("NFKD")`** — strip accents for slugification
5. **Word-boundary truncation** — truncate at spaces, not mid-word'''
    ),
]
