"""Patterns — regex, parsing, and text processing."""

PAIRS = [
    (
        "python/regex-patterns",
        "Show Python regex patterns: common patterns, named groups, lookahead/lookbehind, and compilation.",
        '''Python regex patterns:

```python
import re
from typing import Optional


# --- Compiled patterns (reuse for performance) ---

PATTERNS = {
    "email": re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    ),
    "url": re.compile(
        r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}"
        r"\.[a-zA-Z0-9()]{1,6}\b[-a-zA-Z0-9()@:%_+.~#?&/=]*"
    ),
    "ipv4": re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
    ),
    "semver": re.compile(
        r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
        r"(?:-(?P<pre>[a-zA-Z0-9.]+))?"
        r"(?:\+(?P<build>[a-zA-Z0-9.]+))?$"
    ),
    "iso_date": re.compile(
        r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])"
        r"-(?P<day>0[1-9]|[12]\d|3[01])"
        r"(?:T(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)"
        r"(?::(?P<second>[0-5]\d))?(?:Z|[+-]\d{2}:?\d{2})?)?$"
    ),
    "phone_us": re.compile(
        r"^(?:\+1[-.\s]?)?\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})$"
    ),
    "slug": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    "hex_color": re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$"),
}


def validate(pattern_name: str, value: str) -> bool:
    pattern = PATTERNS.get(pattern_name)
    if not pattern:
        raise ValueError(f"Unknown pattern: {pattern_name}")
    return bool(pattern.match(value))


# --- Named groups for structured extraction ---

LOG_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2}T[\d:.]+Z?)\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"\[(?P<module>[^\]]+)\]\s+"
    r"(?P<message>.*)"
)

def parse_log_line(line: str) -> Optional[dict]:
    match = LOG_PATTERN.match(line)
    if match:
        return match.groupdict()
    return None


# --- Lookahead and lookbehind ---

# Password validation with lookaheads
PASSWORD_PATTERN = re.compile(
    r"^"
    r"(?=.*[a-z])"         # At least one lowercase
    r"(?=.*[A-Z])"         # At least one uppercase
    r"(?=.*\d)"            # At least one digit
    r"(?=.*[!@#$%^&*])"   # At least one special char
    r".{8,}$"              # At least 8 characters
)

def is_strong_password(password: str) -> bool:
    return bool(PASSWORD_PATTERN.match(password))


# Lookbehind: extract values after specific labels
METRIC_PATTERN = re.compile(r"(?<=accuracy:\s)\d+\.\d+")
# "Model accuracy: 0.9542" -> "0.9542"


# Negative lookahead: match word NOT followed by something
NOT_TEST = re.compile(r"\bimport\s+(?!test)\w+")
# Matches "import utils" but not "import test_utils"


# --- Substitution with callbacks ---

def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

# camel_to_snake("getUserById")  # "get_user_by_id"

def snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


# Replace with function
def redact_sensitive(text: str) -> str:
    """Redact credit card numbers and SSNs."""
    text = re.sub(
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "****-****-****-****",
        text,
    )
    text = re.sub(
        r"\b\d{3}-\d{2}-\d{4}\b",
        "***-**-****",
        text,
    )
    return text


# --- Splitting with pattern ---

def tokenize(text: str) -> list[str]:
    """Split text into tokens, handling punctuation."""
    return re.findall(r"\b\w+(?:'\w+)?\b", text.lower())

# tokenize("I can't believe it's not butter!")
# ["i", "can't", "believe", "it's", "not", "butter"]


# --- Non-greedy matching ---

# Greedy: <.*>  on "<a>text</a>" matches "<a>text</a>"
# Non-greedy: <.*?> on "<a>text</a>" matches "<a>" then "</a>"

def extract_between_tags(html: str) -> list[tuple[str, str]]:
    """Extract tag name and content."""
    return re.findall(r"<(\w+)[^>]*>(.*?)</\1>", html, re.DOTALL)


# --- Verbose patterns for readability ---

COMPLEX_PATTERN = re.compile(r"""
    ^                       # Start of string
    (?P<protocol>https?)    # Protocol (http or https)
    ://                     # Separator
    (?P<domain>             # Domain group
        (?:[a-z0-9]         # Domain label start
        (?:[a-z0-9-]{0,61}  # Domain label body
        [a-z0-9])?          # Domain label end
        \.)+                # Dot separator
        [a-z]{2,}           # TLD
    )
    (?::(?P<port>\d+))?     # Optional port
    (?P<path>/[^\s?]*)?     # Optional path
    (?:\?(?P<query>[^\s]*))?  # Optional query string
    $                       # End of string
""", re.VERBOSE | re.IGNORECASE)
```

Regex patterns:
1. **Compile patterns** — `re.compile()` once, reuse for performance
2. **Named groups** — `(?P<name>...)` for readable extraction
3. **Lookaheads** — `(?=...)` for zero-width assertions (password validation)
4. **Non-greedy** — `.*?` for minimal matching in nested structures
5. **`re.VERBOSE`** — multi-line patterns with comments for readability'''
    ),
    (
        "python/text-processing",
        "Show text processing patterns: string manipulation, template engines, diff generation, and Unicode handling.",
        '''Text processing patterns:

```python
import re
import textwrap
import difflib
import unicodedata
from string import Template
from typing import Iterator


# --- String formatting and manipulation ---

def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    # Normalize unicode (é -> e)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    # Replace non-alphanumeric with hyphens
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text

# slugify("Hello World! Café & Résumé")  # "hello-world-cafe-resume"


def truncate(text: str, max_length: int = 100,
             suffix: str = "...") -> str:
    """Truncate text at word boundary."""
    if len(text) <= max_length:
        return text
    truncated = text[:max_length - len(suffix)].rsplit(" ", 1)[0]
    return truncated + suffix


def dedent_strip(text: str) -> str:
    """Remove common indentation and strip."""
    return textwrap.dedent(text).strip()


def wrap_text(text: str, width: int = 72) -> str:
    """Wrap text preserving paragraphs."""
    paragraphs = text.split("\\n\\n")
    wrapped = [textwrap.fill(p, width=width) for p in paragraphs]
    return "\\n\\n".join(wrapped)


# --- Diff generation ---

def generate_diff(old: str, new: str,
                  context_lines: int = 3) -> str:
    """Generate unified diff between two strings."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile="old", tofile="new",
        n=context_lines,
    )
    return "".join(diff)


def find_close_matches(word: str, possibilities: list[str],
                       n: int = 3, cutoff: float = 0.6) -> list[str]:
    """Find similar strings (for 'did you mean?' suggestions)."""
    return difflib.get_close_matches(word, possibilities, n=n, cutoff=cutoff)

# find_close_matches("conifg", ["config", "connect", "confirm"])
# ["config", "confirm"]


def similarity_ratio(a: str, b: str) -> float:
    """Calculate string similarity (0.0 to 1.0)."""
    return difflib.SequenceMatcher(None, a, b).ratio()


# --- Unicode handling ---

def normalize_unicode(text: str) -> str:
    """Normalize unicode to NFC form."""
    return unicodedata.normalize("NFC", text)

def strip_accents(text: str) -> str:
    """Remove accents/diacritics from text."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def is_emoji(char: str) -> bool:
    """Check if character is an emoji."""
    return unicodedata.category(char).startswith("So")

def remove_control_chars(text: str) -> str:
    """Remove control characters except newline/tab."""
    return "".join(
        c for c in text
        if unicodedata.category(c) != "Cc" or c in "\\n\\t"
    )

def count_graphemes(text: str) -> int:
    """Count user-perceived characters (handles emoji, combining chars)."""
    import regex  # pip install regex (supports grapheme clusters)
    return len(regex.findall(r"\\X", text))


# --- Template processing ---

def render_template(template: str, context: dict,
                    default: str = "") -> str:
    """Simple template rendering with defaults."""

    class SafeTemplate(Template):
        def safe_substitute(self, mapping=None, **kws):
            if mapping is None:
                mapping = kws
            return super().safe_substitute(
                {**{k: default for k in self.get_identifiers()}, **mapping}
            )

        def get_identifiers(self):
            return [m.group("named") or m.group("braced")
                    for m in self.pattern.finditer(self.template)
                    if m.group("named") or m.group("braced")]

    return SafeTemplate(template).safe_substitute(context)


# --- Line-by-line processing ---

def process_lines(text: str,
                  transform: callable = None,
                  filter_fn: callable = None) -> str:
    """Process text line by line with optional transform and filter."""
    lines = text.splitlines()

    if filter_fn:
        lines = [l for l in lines if filter_fn(l)]

    if transform:
        lines = [transform(l) for l in lines]

    return "\\n".join(lines)

# Remove blank lines and strip whitespace:
# process_lines(text,
#     transform=str.strip,
#     filter_fn=lambda l: l.strip())

# Number lines:
# process_lines(text,
#     transform=lambda l: f"{i}: {l}" for i, l in enumerate(lines, 1))
```

Text processing patterns:
1. **`slugify`** — normalize unicode + strip non-alphanumeric for URL-safe strings
2. **`difflib`** — unified diffs, close matches, and similarity ratios
3. **Unicode normalization** — NFC/NFKD for consistent string comparison
4. **`textwrap`** — `dedent`, `fill`, and `wrap` for text formatting
5. **Grapheme counting** — `regex` library handles emoji and combining characters correctly'''
    ),
]
