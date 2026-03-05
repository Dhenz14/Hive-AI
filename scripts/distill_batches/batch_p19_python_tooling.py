"""p19 python tooling"""

PAIRS = [
    (
        "python/packaging-modern",
        "Explain modern Python packaging with pyproject.toml including project metadata, dependency specification, build backends (setuptools, hatch, flit), optional dependencies, entry points, and publishing to PyPI. Include a complete pyproject.toml example.",
        '''Python packaging has converged on `pyproject.toml` as the single configuration file replacing `setup.py`, `setup.cfg`, `MANIFEST.in`, and more. Understanding the modern approach eliminates packaging confusion.

### Complete pyproject.toml

```toml
[build-system]
# The build backend that creates the package
requires = ["hatchling"]
build-backend = "hatchling.build"
# Other options: "setuptools.build_meta", "flit_core.buildapi", "pdm.backend"

[project]
name = "my-library"
version = "1.2.0"
description = "A well-packaged Python library"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
    {name = "Alice Developer", email = "alice@example.com"},
]
keywords = ["utilities", "data-processing"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "License :: OSI Approved :: MIT License",
    "Typing :: Typed",
]

# Dependencies with version constraints
dependencies = [
    "httpx>=0.25.0",
    "pydantic>=2.0,<3.0",
    "structlog>=23.1.0",
]

[project.optional-dependencies]
# pip install my-library[dev]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "ruff>=0.1.0",
    "mypy>=1.5",
    "coverage>=7.0",
]
# pip install my-library[postgres]
postgres = ["asyncpg>=0.28"]
redis = ["redis>=5.0"]
all = ["my-library[postgres,redis]"]

[project.urls]
Homepage = "https://github.com/alice/my-library"
Documentation = "https://my-library.readthedocs.io"
Repository = "https://github.com/alice/my-library"
Changelog = "https://github.com/alice/my-library/blob/main/CHANGELOG.md"

[project.scripts]
# CLI entry points: creates executable commands
my-tool = "my_library.cli:main"
my-server = "my_library.server:run"

[project.entry-points."my_library.plugins"]
# Plugin system entry points
csv-loader = "my_library.plugins.csv:CSVLoader"
json-loader = "my_library.plugins.json:JSONLoader"

# ── Tool Configuration ──

[tool.ruff]
target-version = "py310"
line-length = 100
select = ["E", "W", "F", "I", "N", "UP", "B", "A", "SIM"]

[tool.ruff.isort]
known-first-party = ["my_library"]

[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short"

[tool.coverage.run]
source = ["my_library"]
omit = ["tests/*"]

[tool.coverage.report]
exclude_lines = ["if TYPE_CHECKING:", "pragma: no cover"]
```

### Project Structure

```
my-library/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── my_library/          # Source in src layout (recommended)
│       ├── __init__.py
│       ├── py.typed          # Marker for PEP 561 typed package
│       ├── core.py
│       ├── cli.py
│       └── plugins/
│           ├── __init__.py
│           ├── csv.py
│           └── json.py
├── tests/
│   ├── conftest.py
│   ├── test_core.py
│   └── test_cli.py
└── .github/
    └── workflows/
        └── publish.yml
```

### Build and Publish

```bash
# Install build tools
pip install build twine

# Build distribution packages
python -m build
# Creates:
# dist/my_library-1.2.0.tar.gz     (source distribution)
# dist/my_library-1.2.0-py3-none-any.whl  (wheel)

# Check package metadata
twine check dist/*

# Upload to PyPI
twine upload dist/*

# Upload to Test PyPI first
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ my-library
```

### Dynamic Versioning

```toml
# Option 1: Single source of truth in __init__.py
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "src/my_library/__init__.py"
# Reads: __version__ = "1.2.0" from the file

# Option 2: Git tag-based versioning
[tool.hatch.version]
source = "vcs"  # Uses git tags

[tool.hatch.build.hooks.vcs]
version-file = "src/my_library/_version.py"
```

### Entry Points for CLI Tools

```python
# src/my_library/cli.py
import argparse
import sys


def main():
    """Entry point for 'my-tool' command."""
    parser = argparse.ArgumentParser(description="My Library CLI")
    parser.add_argument("input", help="Input file path")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    try:
        result = process(args.input, args.output)
        if args.verbose:
            print(f"Processed: {result}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


# After: pip install my-library
# Run: my-tool input.csv -o output.json
```

### Publishing with GitHub Actions

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # For trusted publishing
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
        # Uses trusted publishing (no API token needed)
```

**Packaging best practices**: (1) Use `pyproject.toml` for everything -- no `setup.py`, `setup.cfg`, or `requirements.txt` for library metadata, (2) Use `src/` layout to prevent importing uninstalled code during tests, (3) Pin exact versions in `requirements.txt` for apps, use ranges in `pyproject.toml` for libraries, (4) Include `py.typed` marker for typed packages, (5) Use trusted publishing on PyPI (OIDC) instead of API tokens.'''
    ),
    (
        "python/cli-tools-development",
        "Explain Python CLI tool development including argument parsing with argparse and click/typer, rich terminal output, configuration file handling, progress bars, interactive prompts, and packaging CLI tools for distribution.",
        '''Well-crafted CLI tools are a pleasure to use. The difference between a script and a tool is error handling, help text, and user experience.

### Modern CLI with Typer

```python
# cli.py -- using Typer (built on Click, with type hints)
import typer
from pathlib import Path
from typing import Optional
from enum import Enum
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="datactl",
    help="Data processing command-line tool",
    add_completion=True,'''
    ),
    (
        "--format",
        "help='Output format' ) limit: int = typer.Option( 0, '--limit', '-l' help='Limit number of rows (0 = no limit)' ) verbose: bool = typer.Option( False, '--verbose', '-v' help='Show detailed processing info' ) ):",
        '''console.print(f"[blue]Processing:[/blue] {input_file}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading data...", total=None)
        data = load_data(input_file)
        progress.update(task, description="Processing...")
        results = transform(data, limit)
        progress.update(task, description="Done!")

    if format == OutputFormat.table:
        _print_table(results)
    elif format == OutputFormat.json:
        _print_json(results, output)
    elif format == OutputFormat.csv:
        _print_csv(results, output)

    if verbose:
        console.print(f"[green]Processed {len(results)} records[/green]")


@app.command()
def validate(
    input_file: Path = typer.Argument(..., exists=True),
    strict: bool = typer.Option(False, "--strict", help="Strict validation"),
):
    """Validate a data file for correctness."""
    errors = run_validation(input_file, strict)

    if errors:
        console.print(f"[red]Found {len(errors)} errors:[/red]")
        for error in errors:
            console.print(f"  Line {error.line}: {error.message}")
        raise typer.Exit(code=1)
    else:
        console.print("[green]Validation passed![/green]")


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current config"),
    set_key: Optional[str] = typer.Option(None, "--set", help="Set a config key=value"),
):
    """Manage configuration."""
    cfg = load_config()

    if show:
        table = Table(title="Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        for key, value in cfg.items():
            table.add_row(key, str(value))
        console.print(table)
    elif set_key:
        key, _, value = set_key.partition("=")
        cfg[key.strip()] = value.strip()
        save_config(cfg)
        console.print(f"Set [cyan]{key}[/cyan] = [green]{value}[/green]")


def _print_table(data: list[dict]):
    table = Table()
    if data:
        for col in data[0].keys():
            table.add_column(col, style="cyan")
        for row in data:
            table.add_row(*[str(v) for v in row.values()])
    console.print(table)


if __name__ == "__main__":
    app()
```

### Configuration File Handling

```python
from pathlib import Path
import tomllib  # Python 3.11+
import json
from dataclasses import dataclass, field, asdict


CONFIG_LOCATIONS = [
    Path("datactl.toml"),                    # Current directory
    Path.home() / ".config/datactl/config.toml",  # XDG config
    Path.home() / ".datactl.toml",           # Home directory
]


@dataclass
class Config:
    """Application configuration with defaults."""
    database_url: str = "sqlite:///data.db"
    output_format: str = "table"
    max_workers: int = 4
    verbose: bool = False
    api_key: str = ""

    @classmethod
    def load(cls) -> "Config":
        """Load config from first found config file."""
        for path in CONFIG_LOCATIONS:
            if path.exists():
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                return cls(**{
                    k: v for k, v in data.items()
                    if k in cls.__dataclass_fields__
                })
        return cls()

    def save(self, path: Path = None):
        """Save config to file."""
        path = path or CONFIG_LOCATIONS[1]  # Default to XDG
        path.parent.mkdir(parents=True, exist_ok=True)
        # tomllib is read-only; use tomli-w for writing
        import tomli_w
        with open(path, "wb") as f:
            tomli_w.dump(asdict(self), f)
```

### Interactive Prompts

```python
import typer
from rich.prompt import Prompt, Confirm, IntPrompt


@app.command()
def init():
    """Interactive project initialization."""
    name = Prompt.ask("Project name", default="my-project")
    db_type = Prompt.ask('''
    ),
    (
        "Database",
        "choices=['postgres', 'sqlite', 'mysql'] default='postgres' ) port = IntPrompt.ask('Server port', default=8000) use_docker = Confirm.ask('Generate Docker files?', default=True) console.print(f'\n[bold]Creating project:[/bold] {name}') console.print(f'  Database: {db_type}') console.print(f'  Port: {port}') console.print(f'  Docker: {'Yes' if use_docker else 'No'}') if Confirm.ask('\nProceed?'): create_project(name, db_type, port, use_docker) console.print('[green]Project created successfully![/green]') else: console.print('[yellow]Cancelled[/yellow]') raise typer.Abort()",
        '''### Error Handling and Exit Codes

```python
import sys
from contextlib import contextmanager


@contextmanager
def error_handler():
    """Consistent error handling for CLI commands."""
    try:
        yield
    except FileNotFoundError as e:
        console.print(f"[red]File not found:[/red] {e.filename}")
        raise typer.Exit(code=2)
    except PermissionError as e:
        console.print(f"[red]Permission denied:[/red] {e.filename}")
        raise typer.Exit(code=3)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        raise typer.Exit(code=130)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if "--debug" in sys.argv:
            console.print_exception()
        raise typer.Exit(code=1)


# Standard exit codes:
# 0: Success
# 1: General error
# 2: Misuse of command (bad arguments)
# 126: Permission problem
# 127: Command not found
# 130: Interrupted (Ctrl+C)
```

**CLI tool best practices**: (1) Use Typer for new projects -- type hints provide argument validation and help text automatically, (2) Rich console output for tables, progress bars, and colored messages, (3) Follow XDG base directory spec for config files (~/.config/appname/), (4) Always return meaningful exit codes -- scripts need to check success/failure, (5) Support `--verbose` and `--quiet` flags -- default to useful but not noisy output.'''
    ),
    (
        "python/regex-patterns",
        "Explain practical regex patterns in Python including the re module, common patterns for validation (email, URL, IP), named groups, lookahead/lookbehind assertions, non-greedy matching, re.VERBOSE for readable patterns, and performance pitfalls.",
        '''Regular expressions are powerful but often misused. Understanding when to use them (and when not to) prevents both bugs and unmaintainable code.

### Common Validation Patterns

```python
import re
from typing import Optional


# Email validation (simplified but practical)
EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"'''
    ),
    (
        "build",
        "}",
        '''# {'major': 1, 'minor': 2, 'patch': 3, 'prerelease': 'beta.1', 'build': 'build.456'}
```

### Named Groups and re.VERBOSE

```python
# Complex patterns become readable with VERBOSE and named groups
LOG_PATTERN = re.compile("""
    ^
    (?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})  # ISO timestamp
    \s+
    (?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)           # Log level
    \s+
    \[(?P<module>[^\]]+)\]                                 # Module in brackets
    \s+
    (?P<message>.+)                                        # Rest is message
    $
""", re.VERBOSE)

def parse_log_line(line: str) -> Optional[dict]:
    match = LOG_PATTERN.match(line)
    if match:
        return match.groupdict()
    return None

# parse_log_line("2024-03-01T14:30:00 ERROR [auth.handler] Login failed for user 42")
# {'timestamp': '2024-03-01T14:30:00', 'level': 'ERROR',
#  'module': 'auth.handler', 'message': 'Login failed for user 42'}


# SQL-like query parser
QUERY_PATTERN = re.compile("""
    ^SELECT\s+
    (?P<columns>[*\w,\s]+)                          # Columns
    \s+FROM\s+
    (?P<table>\w+)                                   # Table name
    (?:\s+WHERE\s+(?P<where>.+?))?                   # Optional WHERE
    (?:\s+ORDER\s+BY\s+(?P<order>\w+(?:\s+(?:ASC|DESC))?))?  # Optional ORDER BY
    (?:\s+LIMIT\s+(?P<limit>\d+))?                   # Optional LIMIT
    \s*;?\s*$
""", re.VERBOSE | re.IGNORECASE)
```

### Lookahead and Lookbehind

```python
# Lookahead (?=...) -- matches if followed by pattern, but doesn't consume
# Lookbehind (?<=...) -- matches if preceded by pattern

# Password strength: at least 8 chars, one upper, one lower, one digit
STRONG_PASSWORD = re.compile(
    r"^(?=.*[a-z])"    # Lookahead: has lowercase
    r"(?=.*[A-Z])"     # Lookahead: has uppercase
    r"(?=.*\d)"        # Lookahead: has digit
    r"(?=.*[!@#$%])"   # Lookahead: has special char
    r".{8,}$"          # At least 8 characters'''
    ),
    (
        "python/unicode-text-processing",
        "Explain Unicode handling in Python including string encoding/decoding, Unicode normalization forms (NFC, NFD), handling emoji and combining characters, locale-aware sorting, text sanitization, and common pitfalls with string length and comparison.",
        '''Python 3 strings are Unicode by default, but "it just works" hides complexity. Understanding Unicode is essential for internationalized applications, text processing, and preventing subtle bugs.

### Encoding and Decoding

```python
# Python str = sequence of Unicode code points
# bytes = sequence of raw bytes
# Encoding: str -> bytes (text -> wire format)
# Decoding: bytes -> str (wire format -> text)

text = "Hello, 世界! 🌍"

# Encode to bytes
utf8_bytes = text.encode("utf-8")    # b'Hello, \xe4\xb8\x96\xe7\x95\x8c! \xf0\x9f\x8c\x8d'
utf16_bytes = text.encode("utf-16")  # Different byte sequence

# Decode back to str
assert utf8_bytes.decode("utf-8") == text

# Common encoding errors
try:
    text.encode("ascii")  # Fails: 世界 and 🌍 aren't ASCII
except UnicodeEncodeError as e:
    print(f"Can't encode: {e}")

# Handle errors gracefully
safe = text.encode("ascii", errors="replace")    # b'Hello, ???! ?'
safe = text.encode("ascii", errors="ignore")     # b'Hello, ! '
safe = text.encode("ascii", errors="xmlcharrefreplace")  # b'Hello, &#19990;&#30028;! &#127757;'

# ALWAYS specify encoding when opening files
with open("data.txt", "r", encoding="utf-8") as f:
    content = f.read()

# Never use the default encoding (it varies by platform!)
```

### Unicode Normalization

The same visual text can have different byte representations:

```python
import unicodedata

# These look identical but are different strings!
a1 = "café"           # 'é' as single code point (U+00E9)
a2 = "cafe\u0301"     # 'e' + combining acute accent (U+0301)

print(a1 == a2)       # False!
print(len(a1))        # 4
print(len(a2))        # 5

# Normalization makes them comparable
nfc1 = unicodedata.normalize("NFC", a1)   # Composed form
nfc2 = unicodedata.normalize("NFC", a2)   # Also composed form
print(nfc1 == nfc2)   # True!

# NFC: Canonical Composition (most compact, recommended for storage)
# NFD: Canonical Decomposition (separate base + combining chars)
# NFKC: Compatibility Composition (ligatures -> normal chars)
# NFKD: Compatibility Decomposition

# NFKC example: fullwidth characters and ligatures
text = "ﬁle"  # Contains 'ﬁ' ligature (U+FB01)
print(unicodedata.normalize("NFKC", text))  # "file"

# ALWAYS normalize before:
# - Storing in database
# - Comparing strings
# - Using as dictionary keys or set elements

def normalize_text(text: str) -> str:
    """Standard normalization for text processing."""
    return unicodedata.normalize("NFC", text)
```

### String Length vs Visual Width

```python
# len() counts code points, not visual characters

text = "👨‍👩‍👧‍👦"  # Family emoji (ZWJ sequence)
print(len(text))       # 7 (4 emojis + 3 zero-width joiners)
# But visually it's ONE character!

# Combining characters affect this too
text = "e\u0301\u0327"  # e + acute + cedilla
print(len(text))          # 3 code points, 1 visual character

# For visual width (terminal columns), use wcwidth
import wcwidth

def visual_width(text: str) -> int:
    """Get the visual width in terminal columns."""
    return sum(max(0, wcwidth.wcwidth(c)) for c in text)

# CJK characters are double-width
print(visual_width("Hello"))  # 5
print(visual_width("世界"))    # 4 (each char is 2 columns wide)


# For grapheme clusters (user-perceived characters), use regex
import regex  # pip install regex (supports \X for grapheme clusters)

def grapheme_length(text: str) -> int:
    """Count user-perceived characters (grapheme clusters)."""
    return len(regex.findall(r'\X', text))

print(grapheme_length("👨‍👩‍👧‍👦"))  # 1
print(grapheme_length("café"))       # 4
print(grapheme_length("cafe\u0301")) # 4
```

### Text Sanitization

```python
import re
import unicodedata


def sanitize_text(text: str) -> str:
    """Clean text for safe storage and processing."""
    # Step 1: Normalize Unicode
    text = unicodedata.normalize("NFC", text)

    # Step 2: Remove control characters (except newlines and tabs)
    text = "".join(
        c for c in text
        if c in ("\n", "\t") or not unicodedata.category(c).startswith("C")'''
    ),
]
