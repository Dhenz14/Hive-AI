"""Regular expressions — patterns, optimization, and practical recipes."""

PAIRS = [
    (
        "python/regex-patterns",
        "Show practical regular expression patterns: parsing, validation, extraction, and substitution with performance tips.",
        '''Practical regex patterns and techniques:

```python
import re
from typing import Optional

# --- Validation patterns ---

PATTERNS = {
    # Email (simplified RFC 5322)
    "email": re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    ),
    # Strong password (8+, upper, lower, digit, special)
    "strong_password": re.compile(
        r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
    ),
    # URL
    "url": re.compile(
        r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE
    ),
    # IPv4
    "ipv4": re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
    ),
    # Semantic version
    "semver": re.compile(
        r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
        r"(?:-(?P<pre>[a-zA-Z0-9.]+))?"
        r"(?:\+(?P<build>[a-zA-Z0-9.]+))?$"
    ),
    # ISO 8601 date
    "iso_date": re.compile(
        r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
        r"(?:T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?$"
    ),
    # UUID
    "uuid": re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    ),
    # Slug (URL-safe string)
    "slug": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
}

def validate(pattern_name: str, value: str) -> bool:
    pattern = PATTERNS.get(pattern_name)
    return bool(pattern and pattern.match(value))


# --- Extraction patterns ---

def extract_urls(text: str) -> list[str]:
    """Extract all URLs from text."""
    pattern = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE
    )
    return pattern.findall(text)

def extract_mentions(text: str) -> list[str]:
    """Extract @mentions from text."""
    return re.findall(r"@(\w{1,30})", text)

def extract_hashtags(text: str) -> list[str]:
    """Extract #hashtags from text."""
    return re.findall(r"#(\w{1,50})", text)

def extract_code_blocks(markdown: str) -> list[dict]:
    """Extract fenced code blocks from markdown."""
    pattern = re.compile(
        r"```(\w*)\n(.*?)```", re.DOTALL
    )
    return [
        {"language": m.group(1) or "text", "code": m.group(2).strip()}
        for m in pattern.finditer(markdown)
    ]


# --- Substitution patterns ---

def clean_html(html: str) -> str:
    """Strip HTML tags."""
    return re.sub(r"<[^>]+>", "", html)

def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)   # Remove non-word chars
    text = re.sub(r"[\s_]+", "-", text)     # Spaces/underscores to hyphens
    text = re.sub(r"-+", "-", text)         # Collapse multiple hyphens
    return text.strip("-")

def mask_sensitive(text: str) -> str:
    """Mask credit card numbers and SSNs."""
    # Credit card: keep last 4
    text = re.sub(
        r"\b(\d{4})[- ]?\d{4}[- ]?\d{4}[- ]?(\d{4})\b",
        r"****-****-****-\2", text
    )
    # SSN: mask completely
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "***-**-****", text)
    return text

def camel_to_snake(name: str) -> str:
    """Convert camelCase/PascalCase to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()

def snake_to_camel(name: str, pascal: bool = False) -> str:
    """Convert snake_case to camelCase or PascalCase."""
    components = name.split("_")
    if pascal:
        return "".join(c.title() for c in components)
    return components[0] + "".join(c.title() for c in components[1:])


# --- Log parsing ---

LOG_PATTERN = re.compile(
    r"^(?P<ip>[\d.]+)\s+"
    r"- - \[(?P<date>[^\]]+)\]\s+"
    r'"(?P<method>\w+)\s+(?P<path>\S+)\s+HTTP/[\d.]+" '
    r"(?P<status>\d+)\s+(?P<size>\d+)\s+"
    r'"(?P<referrer>[^"]*)"\s+'
    r'"(?P<user_agent>[^"]*)"$'
)

def parse_access_log(line: str) -> Optional[dict]:
    m = LOG_PATTERN.match(line)
    if not m:
        return None
    return {
        "ip": m.group("ip"),
        "date": m.group("date"),
        "method": m.group("method"),
        "path": m.group("path"),
        "status": int(m.group("status")),
        "size": int(m.group("size")),
        "user_agent": m.group("user_agent"),
    }


# --- Performance tips ---

# 1. Compile patterns used multiple times
COMPILED = re.compile(r"\d+")  # Do this once, not in a loop

# 2. Use raw strings to avoid double-escaping
good = re.compile(r"\d+\.\d+")    # Raw string
bad  = re.compile("\\d+\\.\\d+")  # Needs double escape

# 3. Use non-capturing groups when you don't need the match
fast = re.compile(r"(?:abc|def)\d+")   # Non-capturing (?:...)
slow = re.compile(r"(abc|def)\d+")     # Capturing (creates group)

# 4. Anchor patterns for validation (^ and $)
# Without anchors, "abc" would match "xyzabcxyz"

# 5. Be specific — [0-9] is clearer than \d in some contexts
# \d matches any Unicode digit; [0-9] is ASCII-only

# 6. Avoid catastrophic backtracking
# BAD: (a+)+ — exponential backtracking
# GOOD: a+ — same match, no backtracking
```

Common mistakes to avoid:
1. **No anchors in validation** — always use `^...$` for full-string match
2. **Greedy by default** — `.*` matches as much as possible; use `.*?` for lazy
3. **Forgetting `re.DOTALL`** — `.` doesn't match `\\n` by default
4. **Catastrophic backtracking** — nested quantifiers like `(a+)+` can hang
5. **Not compiling** — `re.compile()` once vs re-parsing in every call'''
    ),
]
"""
