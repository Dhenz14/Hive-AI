"""Python stdlib — collections, itertools, functools, pathlib, and useful standard library patterns."""

PAIRS = [
    (
        "python/collections-module",
        "Show Python collections module patterns: defaultdict, Counter, deque, OrderedDict, and ChainMap with practical examples.",
        '''Python collections for efficient data handling:

```python
from collections import (
    defaultdict, Counter, deque, OrderedDict, ChainMap, namedtuple
)

# --- defaultdict: auto-initialize missing keys ---

# Group items by category
products = [
    {"name": "Laptop", "category": "electronics"},
    {"name": "Shirt", "category": "clothing"},
    {"name": "Phone", "category": "electronics"},
    {"name": "Pants", "category": "clothing"},
]

by_category = defaultdict(list)
for product in products:
    by_category[product["category"]].append(product["name"])
# {"electronics": ["Laptop", "Phone"], "clothing": ["Shirt", "Pants"]}

# Nested defaultdict (adjacency list)
graph = defaultdict(lambda: defaultdict(int))
graph["A"]["B"] = 5
graph["A"]["C"] = 3
graph["B"]["C"] = 1

# --- Counter: count and rank ---

text = "the quick brown fox jumps over the lazy brown dog"
word_counts = Counter(text.split())
# Counter({"brown": 2, "the": 2, "quick": 1, ...})

word_counts.most_common(3)   # [("brown", 2), ("the", 2), ("quick", 1)]
word_counts["brown"]          # 2
word_counts["missing"]        # 0 (no KeyError)

# Combine counters
sales_jan = Counter({"widget": 100, "gadget": 50})
sales_feb = Counter({"widget": 80, "gadget": 70, "gizmo": 30})
total = sales_jan + sales_feb  # Counter({"widget": 180, "gadget": 120, "gizmo": 30})

# Most common elements from iterable
from itertools import chain
log_levels = ["ERROR", "INFO", "INFO", "WARN", "ERROR", "INFO", "DEBUG"]
Counter(log_levels)  # Counter({"INFO": 3, "ERROR": 2, "WARN": 1, "DEBUG": 1})


# --- deque: fast appends/pops from both ends ---

# Bounded buffer (keeps last N items)
recent_logs = deque(maxlen=1000)
recent_logs.append("2024-01-01 INFO: Request processed")
# Oldest items automatically discarded when maxlen exceeded

# Sliding window
def sliding_window_max(nums: list[int], k: int) -> list[int]:
    result = []
    window = deque()  # Stores indices
    for i, num in enumerate(nums):
        # Remove elements outside window
        while window and window[0] <= i - k:
            window.popleft()
        # Remove smaller elements
        while window and nums[window[-1]] < num:
            window.pop()
        window.append(i)
        if i >= k - 1:
            result.append(nums[window[0]])
    return result

# BFS (breadth-first search)
def bfs(graph: dict, start: str) -> list[str]:
    visited = set()
    queue = deque([start])
    order = []
    while queue:
        node = queue.popleft()  # O(1) vs list.pop(0) which is O(n)
        if node not in visited:
            visited.add(node)
            order.append(node)
            queue.extend(graph.get(node, []))
    return order

# Rotate
d = deque([1, 2, 3, 4, 5])
d.rotate(2)   # deque([4, 5, 1, 2, 3]) — rotate right
d.rotate(-2)  # deque([1, 2, 3, 4, 5]) — rotate left


# --- ChainMap: layered configuration ---

defaults = {"theme": "light", "language": "en", "page_size": 20}
user_prefs = {"theme": "dark"}
cli_args = {"page_size": 50}

config = ChainMap(cli_args, user_prefs, defaults)
config["theme"]      # "dark" (from user_prefs)
config["page_size"]  # 50 (from cli_args)
config["language"]   # "en" (from defaults)


# --- namedtuple: lightweight data objects ---

Point = namedtuple("Point", ["x", "y"])
p = Point(3, 4)
p.x, p.y  # 3, 4
# Immutable, hashable, memory-efficient

# With defaults
Config = namedtuple("Config", ["host", "port", "debug"], defaults=["localhost", 8000, False])
Config()  # Config(host='localhost', port=8000, debug=False)
```

When to use:
- **defaultdict** — grouping, counting, adjacency lists (auto-init)
- **Counter** — frequency counting, top-N, set-like operations on counts
- **deque** — queues, bounded buffers, sliding windows (O(1) ends)
- **ChainMap** — layered lookups (config precedence, scope chains)
- **namedtuple** — simple immutable records (prefer `dataclass` for mutable)'''
    ),
    (
        "python/itertools-patterns",
        "Show Python itertools patterns: chaining, grouping, windowing, combinatorics, and memory-efficient data processing.",
        '''Python itertools for efficient iteration:

```python
import itertools
from typing import Iterator, TypeVar, Callable
from collections.abc import Iterable

T = TypeVar("T")

# --- Chaining and flattening ---

# Chain multiple iterables
lists = [[1, 2], [3, 4], [5, 6]]
flat = list(itertools.chain.from_iterable(lists))  # [1, 2, 3, 4, 5, 6]

# Chain with different types
files = itertools.chain(
    Path("logs/").glob("*.log"),
    Path("archives/").glob("*.log.gz"),
)

# --- Grouping ---

# groupby (requires sorted input!)
data = [
    {"dept": "eng", "name": "Alice"},
    {"dept": "eng", "name": "Bob"},
    {"dept": "sales", "name": "Carol"},
    {"dept": "sales", "name": "Dave"},
]

from operator import itemgetter
sorted_data = sorted(data, key=itemgetter("dept"))
for dept, members in itertools.groupby(sorted_data, key=itemgetter("dept")):
    print(f"{dept}: {[m['name'] for m in members]}")
# eng: ['Alice', 'Bob']
# sales: ['Carol', 'Dave']

# --- Sliding window (Python 3.12+) ---

# itertools.batched (Python 3.12)
# list(itertools.batched([1, 2, 3, 4, 5], 2))  # [(1, 2), (3, 4), (5,)]

# Manual sliding window
def sliding_window(iterable: Iterable[T], n: int) -> Iterator[tuple[T, ...]]:
    iterator = iter(iterable)
    window = tuple(itertools.islice(iterator, n))
    if len(window) == n:
        yield window
    for item in iterator:
        window = window[1:] + (item,)
        yield window

list(sliding_window([1, 2, 3, 4, 5], 3))
# [(1, 2, 3), (2, 3, 4), (3, 4, 5)]

# Pairwise (Python 3.10+)
from itertools import pairwise
list(pairwise([1, 2, 3, 4]))  # [(1, 2), (2, 3), (3, 4)]


# --- Accumulate (running totals) ---

import operator

# Running sum
list(itertools.accumulate([1, 2, 3, 4, 5]))  # [1, 3, 6, 10, 15]

# Running max
list(itertools.accumulate([3, 1, 4, 1, 5, 9], max))  # [3, 3, 4, 4, 5, 9]

# Running product
list(itertools.accumulate([1, 2, 3, 4], operator.mul))  # [1, 2, 6, 24]


# --- Filtering ---

# takewhile / dropwhile
logs = ["DEBUG: ...", "DEBUG: ...", "ERROR: crash", "INFO: recovered"]
errors_and_after = list(itertools.dropwhile(
    lambda x: not x.startswith("ERROR"), logs
))
# ["ERROR: crash", "INFO: recovered"]

# filterfalse (complement of filter)
evens = list(itertools.filterfalse(lambda x: x % 2, range(10)))
# [0, 2, 4, 6, 8]

# compress (filter by selector)
data = ["a", "b", "c", "d", "e"]
selectors = [1, 0, 1, 0, 1]
list(itertools.compress(data, selectors))  # ["a", "c", "e"]


# --- Combinatorics ---

# Permutations
list(itertools.permutations("ABC", 2))
# [('A', 'B'), ('A', 'C'), ('B', 'A'), ('B', 'C'), ('C', 'A'), ('C', 'B')]

# Combinations
list(itertools.combinations("ABCD", 2))
# [('A', 'B'), ('A', 'C'), ('A', 'D'), ('B', 'C'), ('B', 'D'), ('C', 'D')]

# Product (cartesian product)
list(itertools.product([0, 1], repeat=3))
# [(0,0,0), (0,0,1), (0,1,0), (0,1,1), (1,0,0), (1,0,1), (1,1,0), (1,1,1)]

# All RGB combinations
colors = itertools.product(["red", "green", "blue"], ["light", "dark"])


# --- Infinite iterators ---

# count: infinite counter
for i in itertools.islice(itertools.count(10, 2), 5):
    print(i)  # 10, 12, 14, 16, 18

# cycle: repeat forever
statuses = itertools.cycle([".", "..", "..."])
# next(statuses) -> ".", next(statuses) -> "..", next(statuses) -> "..."

# repeat: same value N times
list(itertools.repeat("default", 5))  # ["default"] * 5


# --- Practical: batch processing ---

def chunked(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    """Split iterable into chunks of given size."""
    iterator = iter(iterable)
    while True:
        chunk = list(itertools.islice(iterator, size))
        if not chunk:
            break
        yield chunk

# Process 1M rows in chunks of 1000
for batch in chunked(range(1_000_000), 1000):
    process_batch(batch)
```

Key principles:
1. **Lazy evaluation** — itertools returns iterators, not lists (memory efficient)
2. **Composition** — chain operations without materializing intermediate results
3. **`islice` for limiting** — take first N from any iterator
4. **`groupby` needs sorted input** — always sort by the grouping key first
5. **`chain.from_iterable`** — flatten without loading everything into memory'''
    ),
    (
        "python/functools-patterns",
        "Show Python functools patterns: lru_cache, partial, reduce, singledispatch, and wraps for decorators.",
        '''Python functools for higher-order programming:

```python
from functools import (
    lru_cache, cache, cached_property, partial,
    reduce, singledispatch, wraps, total_ordering,
)
from typing import Callable, TypeVar, ParamSpec
import time

P = ParamSpec("P")
R = TypeVar("R")

# --- Caching ---

@lru_cache(maxsize=128)
def fibonacci(n: int) -> int:
    """Memoized recursive fibonacci."""
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

fibonacci(100)  # Instant, despite recursive implementation
fibonacci.cache_info()  # CacheInfo(hits=98, misses=101, maxsize=128, currsize=101)
fibonacci.cache_clear()  # Clear cache

# Unbounded cache (Python 3.9+)
@cache
def expensive_computation(x: int, y: int) -> float:
    time.sleep(1)  # Simulated expensive work
    return x ** y

# cached_property (computed once per instance)
class DataAnalyzer:
    def __init__(self, data: list[float]):
        self.data = data

    @cached_property
    def statistics(self) -> dict:
        """Computed once, cached on instance."""
        return {
            "mean": sum(self.data) / len(self.data),
            "min": min(self.data),
            "max": max(self.data),
            "count": len(self.data),
        }


# --- partial: pre-fill arguments ---

def power(base: int, exponent: int) -> int:
    return base ** exponent

square = partial(power, exponent=2)
cube = partial(power, exponent=3)
square(5)  # 25
cube(3)    # 27

# Practical: configure loggers
import logging
log_error = partial(logging.log, logging.ERROR)
log_debug = partial(logging.log, logging.DEBUG)

# Practical: pre-configure API client
from httpx import AsyncClient
get_json = partial(AsyncClient().get, headers={"Accept": "application/json"})


# --- reduce: fold values ---

numbers = [1, 2, 3, 4, 5]
product = reduce(lambda a, b: a * b, numbers)  # 120

# Build nested dict from keys
def set_nested(d: dict, keys: list[str], value):
    """Set value at nested key path."""
    reduce(lambda d, k: d.setdefault(k, {}), keys[:-1], d)[keys[-1]] = value

config = {}
set_nested(config, ["database", "primary", "host"], "localhost")
# {"database": {"primary": {"host": "localhost"}}}

# Compose functions
def compose(*funcs):
    """Compose functions: compose(f, g, h)(x) == f(g(h(x)))."""
    return reduce(lambda f, g: lambda *a, **kw: f(g(*a, **kw)), funcs)

process = compose(str.upper, str.strip, str)
process("  hello  ")  # "HELLO"


# --- singledispatch: function overloading ---

@singledispatch
def serialize(obj) -> str:
    """Default: convert to string."""
    return str(obj)

@serialize.register(dict)
def _(obj: dict) -> str:
    import json
    return json.dumps(obj)

@serialize.register(list)
def _(obj: list) -> str:
    return ", ".join(serialize(item) for item in obj)

@serialize.register(int)
@serialize.register(float)
def _(obj) -> str:
    return f"{obj:,.2f}"

serialize({"key": "value"})  # '{"key": "value"}'
serialize([1, 2, 3])          # "1.00, 2.00, 3.00"
serialize(42)                  # "42.00"


# --- wraps: proper decorator implementation ---

def retry(max_attempts: int = 3, delay: float = 1.0):
    """Decorator factory with retry logic."""
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)  # Preserves __name__, __doc__, __module__
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        await asyncio.sleep(delay * attempt)
            raise last_exception
        return wrapper
    return decorator

@retry(max_attempts=3, delay=2.0)
async def fetch_data(url: str) -> dict:
    """Fetch data from API with automatic retry."""
    ...

# fetch_data.__name__ == "fetch_data" (preserved by @wraps)
# fetch_data.__doc__ == "Fetch data from API..." (preserved by @wraps)


# --- total_ordering: comparison operators ---

@total_ordering
class Version:
    """Only define __eq__ and __lt__, get all 6 comparisons."""
    def __init__(self, major: int, minor: int, patch: int):
        self.major = major
        self.minor = minor
        self.patch = patch

    def __eq__(self, other):
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other):
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

# Now works: <=, >, >=, !=
Version(1, 2, 0) < Version(1, 3, 0)   # True
Version(2, 0, 0) >= Version(1, 9, 9)  # True
```

Key functions:
1. **`lru_cache`/`cache`** — memoize expensive pure functions
2. **`partial`** — create specialized versions of functions
3. **`reduce`** — fold/accumulate sequence into single value
4. **`singledispatch`** — function overloading by argument type
5. **`wraps`** — preserve function metadata in decorators
6. **`total_ordering`** — generate comparison methods from `__eq__` + `__lt__`'''
    ),
    (
        "python/pathlib-patterns",
        "Show Python pathlib patterns: file operations, path manipulation, glob, and cross-platform path handling.",
        '''Python pathlib for file system operations:

```python
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import json

# --- Path construction (cross-platform) ---

# Always use Path, not os.path.join
project = Path.home() / "projects" / "myapp"
config = project / "config" / "settings.json"

# From string
p = Path("/var/log/app.log")
p = Path("relative/path/file.txt")

# Current working directory
cwd = Path.cwd()
script_dir = Path(__file__).parent.resolve()

# --- Path components ---

p = Path("/var/log/app/server.log.gz")
p.name          # "server.log.gz"
p.stem          # "server.log"
p.suffix        # ".gz"
p.suffixes      # [".log", ".gz"]
p.parent        # Path("/var/log/app")
p.parents[1]    # Path("/var/log")
p.parts         # ("/", "var", "log", "app", "server.log.gz")

# Change components
p.with_name("client.log")      # /var/log/app/client.log
p.with_stem("error")           # /var/log/app/error.log.gz (Python 3.9+)
p.with_suffix(".txt")          # /var/log/app/server.log.txt

# --- File operations ---

# Read/write (no open() needed)
text = config.read_text(encoding="utf-8")
config.write_text(json.dumps(data), encoding="utf-8")
binary = Path("image.png").read_bytes()
Path("output.bin").write_bytes(binary)

# Create directories
output = Path("output/reports/2024")
output.mkdir(parents=True, exist_ok=True)

# Check existence and type
config.exists()      # True/False
config.is_file()     # True
config.is_dir()      # False
config.is_symlink()  # False

# File info
config.stat().st_size      # Size in bytes
config.stat().st_mtime     # Modification time
config.stat().st_mode      # Permissions

# --- Glob patterns ---

# Find all Python files
project = Path("src")
py_files = list(project.glob("**/*.py"))         # Recursive
test_files = list(project.glob("**/test_*.py"))  # Test files only
configs = list(project.glob("*.{json,yaml,toml}"))  # Multiple extensions

# rglob = recursive glob (shorthand for **/pattern)
all_logs = list(Path("/var/log").rglob("*.log"))

# Iterate directory
for item in Path("src").iterdir():
    if item.is_file():
        print(f"File: {item.name} ({item.stat().st_size} bytes)")
    elif item.is_dir():
        print(f"Dir: {item.name}/")

# --- Common operations ---

# Copy file
shutil.copy2(Path("src.txt"), Path("dst.txt"))

# Copy directory tree
shutil.copytree(Path("src_dir"), Path("dst_dir"), dirs_exist_ok=True)

# Move/rename
Path("old_name.txt").rename("new_name.txt")
shutil.move("file.txt", "archive/file.txt")

# Delete
Path("temp.txt").unlink(missing_ok=True)    # Delete file
shutil.rmtree(Path("temp_dir"))              # Delete directory tree

# Temporary directory
import tempfile
with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    (tmp / "data.json").write_text("{}")
    # Auto-deleted when context exits


# --- Practical patterns ---

def find_project_root(start: Path = None, marker: str = "pyproject.toml") -> Path:
    """Walk up to find project root by marker file."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / marker).exists():
            return parent
    raise FileNotFoundError(f"No {marker} found in ancestors of {current}")

def ensure_clean_dir(path: Path) -> Path:
    """Create or clean a directory."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path

def safe_filename(name: str) -> str:
    """Sanitize string for use as filename."""
    import re
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:255]  # Max filename length

def relative_to_safe(path: Path, base: Path) -> Path:
    """Get relative path, or return absolute if not relative."""
    try:
        return path.relative_to(base)
    except ValueError:
        return path
```

Best practices:
1. **Use `Path` everywhere** — replace `os.path.join`, `os.path.exists`, etc.
2. **`/` operator** — `Path("a") / "b" / "c"` for path joining
3. **`read_text`/`write_text`** — no need for `open()` for simple I/O
4. **`mkdir(parents=True, exist_ok=True)`** — create nested dirs safely
5. **`rglob`** — recursive search without manual `os.walk`'''
    ),
]
"""
