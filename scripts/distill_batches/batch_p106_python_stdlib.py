"""Python stdlib — collections, enum patterns, itertools, and functools."""

PAIRS = [
    (
        "python/collections-module",
        "Show Python collections module patterns: defaultdict, Counter, deque, OrderedDict, and ChainMap.",
        '''Python collections module patterns:

```python
from collections import (
    defaultdict, Counter, deque, OrderedDict, ChainMap, namedtuple,
)


# --- defaultdict ---

# Group items by key
items = [("fruit", "apple"), ("veggie", "carrot"), ("fruit", "banana"), ("veggie", "pea")]
grouped = defaultdict(list)
for category, item in items:
    grouped[category].append(item)
# {'fruit': ['apple', 'banana'], 'veggie': ['carrot', 'pea']}

# Nested defaultdict (auto-creating nested dicts)
tree = lambda: defaultdict(tree)
config = tree()
config["database"]["primary"]["host"] = "localhost"
config["database"]["primary"]["port"] = 5432

# Count with defaultdict
word_count = defaultdict(int)
for word in "the cat sat on the mat".split():
    word_count[word] += 1


# --- Counter ---

text = "abracadabra"
freq = Counter(text)
# Counter({'a': 5, 'b': 2, 'r': 2, 'c': 1, 'd': 1})

freq.most_common(3)       # [('a', 5), ('b', 2), ('r', 2)]

# Counter arithmetic
c1 = Counter(a=3, b=1)
c2 = Counter(a=1, b=2)
c1 + c2  # Counter({'a': 4, 'b': 3})
c1 - c2  # Counter({'a': 2})  — drops zero/negative

# Count elements from iterable
words = ["error", "warning", "error", "info", "error", "warning"]
log_counts = Counter(words)
log_counts["error"]  # 3


# --- deque (double-ended queue) ---

# Bounded deque (keeps last N items)
recent = deque(maxlen=5)
for i in range(10):
    recent.append(i)
# deque([5, 6, 7, 8, 9], maxlen=5)

# Efficient rotation
d = deque([1, 2, 3, 4, 5])
d.rotate(2)   # [4, 5, 1, 2, 3] — rotate right
d.rotate(-1)  # [5, 1, 2, 3, 4] — rotate left

# O(1) append/pop from both ends
d.appendleft(0)   # [0, 5, 1, 2, 3, 4]
d.popleft()        # 0

# Sliding window pattern
def sliding_window(iterable, size):
    it = iter(iterable)
    window = deque(maxlen=size)
    for _ in range(size):
        window.append(next(it))
    yield tuple(window)
    for item in it:
        window.append(item)
        yield tuple(window)


# --- ChainMap (layered lookups) ---

defaults = {"color": "blue", "size": "medium", "font": "Arial"}
user_prefs = {"color": "red"}
session = {"size": "large"}

# First dict wins on lookup
config = ChainMap(session, user_prefs, defaults)
config["color"]  # "red"   (from user_prefs)
config["size"]   # "large" (from session)
config["font"]   # "Arial" (from defaults)

# New child scope (like variable scoping)
local_config = config.new_child({"color": "green"})
local_config["color"]  # "green"
config["color"]        # "red" (parent unchanged)


# --- namedtuple ---

Point = namedtuple("Point", ["x", "y"])
p = Point(3, 4)
p.x, p.y  # 3, 4
x, y = p  # Unpacking works

# With defaults
Color = namedtuple("Color", ["r", "g", "b", "a"], defaults=[255])
white = Color(255, 255, 255)  # a defaults to 255

# Convert to/from dict
p._asdict()  # {'x': 3, 'y': 4}
Point(**{"x": 1, "y": 2})  # Point(x=1, y=2)

# Replace (returns new instance)
p._replace(x=10)  # Point(x=10, y=4)
```

Collections patterns:
1. **`defaultdict(list)`** — group items by key without checking key existence
2. **`Counter.most_common(n)`** — top-N frequency counting in one line
3. **`deque(maxlen=N)`** — bounded buffer that auto-evicts oldest items
4. **`ChainMap`** — layered config lookup (session > user > defaults)
5. **`namedtuple`** — lightweight immutable records with named field access'''
    ),
    (
        "python/enum-patterns",
        "Show Python enum patterns: IntEnum, StrEnum, Flag, auto(), and practical usage patterns.",
        '''Python enum patterns:

```python
from enum import Enum, IntEnum, StrEnum, Flag, auto, unique


# --- Basic Enum ---

class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"

color = Color.RED
color.name   # "RED"
color.value  # "red"

# Lookup by value
Color("red")      # Color.RED
Color["RED"]      # Color.RED (by name)

# Iteration
list(Color)       # [Color.RED, Color.GREEN, Color.BLUE]


# --- StrEnum (string-compatible) ---

class Status(StrEnum):
    PENDING = auto()     # "pending"
    ACTIVE = auto()      # "active"
    SUSPENDED = auto()   # "suspended"
    DELETED = auto()     # "deleted"

# StrEnum values work as strings directly
status = Status.ACTIVE
f"User is {status}"        # "User is active"
status == "active"         # True
status.upper()             # "ACTIVE"

# Useful for API responses, database values, JSON
import json
json.dumps({"status": status})  # '{"status": "active"}'


# --- IntEnum (integer-compatible) ---

class Priority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

# Comparable and sortable
Priority.HIGH > Priority.LOW  # True
sorted_tasks = sorted(tasks, key=lambda t: t.priority)

# Works in arithmetic (use sparingly)
Priority.HIGH + 1  # 4


# --- Flag (bitwise combinations) ---

class Permission(Flag):
    READ = auto()     # 1
    WRITE = auto()    # 2
    EXECUTE = auto()  # 4
    DELETE = auto()   # 8

    # Composite flags
    READ_WRITE = READ | WRITE
    ADMIN = READ | WRITE | EXECUTE | DELETE

# Combine flags
user_perms = Permission.READ | Permission.WRITE

# Check membership
Permission.READ in user_perms    # True
Permission.DELETE in user_perms  # False

# Remove a flag
user_perms &= ~Permission.WRITE  # Only READ left


# --- Enum with methods ---

class HttpStatus(IntEnum):
    OK = 200
    CREATED = 201
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_ERROR = 500

    @property
    def is_success(self) -> bool:
        return 200 <= self.value < 300

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.value < 500

    @property
    def is_server_error(self) -> bool:
        return self.value >= 500

    def __str__(self) -> str:
        return f"{self.value} {self.name.replace('_', ' ').title()}"


status = HttpStatus.NOT_FOUND
status.is_client_error  # True
str(status)             # "404 Not Found"


# --- Enum as state machine transitions ---

class OrderState(StrEnum):
    DRAFT = auto()
    PLACED = auto()
    PAID = auto()
    SHIPPED = auto()
    DELIVERED = auto()
    CANCELLED = auto()

VALID_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.DRAFT: {OrderState.PLACED, OrderState.CANCELLED},
    OrderState.PLACED: {OrderState.PAID, OrderState.CANCELLED},
    OrderState.PAID: {OrderState.SHIPPED, OrderState.CANCELLED},
    OrderState.SHIPPED: {OrderState.DELIVERED},
    OrderState.DELIVERED: set(),
    OrderState.CANCELLED: set(),
}

def transition(current: OrderState, target: OrderState) -> OrderState:
    if target not in VALID_TRANSITIONS[current]:
        raise ValueError(
            f"Cannot transition from {current} to {target}. "
            f"Valid: {VALID_TRANSITIONS[current]}"
        )
    return target
```

Enum patterns:
1. **`StrEnum` + `auto()`** — auto-generates lowercase string values, JSON-friendly
2. **`Flag`** — bitwise combinable permissions with `|`, `&`, `~` operators
3. **Methods on enums** — add `@property` and `__str__` for rich behavior
4. **State machine** — map valid transitions using enum keys
5. **`IntEnum`** — comparable/sortable enums that work in numeric contexts'''
    ),
    (
        "python/itertools-functools",
        "Show Python itertools and functools patterns: chain, groupby, product, lru_cache, partial, reduce.",
        '''Python itertools and functools patterns:

```python
import itertools
from functools import lru_cache, cache, partial, reduce, wraps
from operator import add, mul


# --- itertools: combining ---

# chain: flatten multiple iterables
all_items = list(itertools.chain([1, 2], [3, 4], [5]))  # [1, 2, 3, 4, 5]

# chain.from_iterable: flatten nested lists
nested = [[1, 2], [3, 4], [5, 6]]
flat = list(itertools.chain.from_iterable(nested))  # [1, 2, 3, 4, 5, 6]

# product: cartesian product (nested loops)
sizes = ["S", "M", "L"]
colors = ["red", "blue"]
combos = list(itertools.product(sizes, colors))
# [('S', 'red'), ('S', 'blue'), ('M', 'red'), ...]

# permutations and combinations
itertools.permutations([1, 2, 3], 2)     # (1,2), (1,3), (2,1), (2,3), ...
itertools.combinations([1, 2, 3, 4], 2)  # (1,2), (1,3), (1,4), (2,3), ...
itertools.combinations_with_replacement([1, 2, 3], 2)  # includes (1,1), (2,2)


# --- itertools: filtering and grouping ---

# groupby (requires sorted input!)
data = [
    {"dept": "eng", "name": "Alice"},
    {"dept": "eng", "name": "Bob"},
    {"dept": "sales", "name": "Carol"},
    {"dept": "sales", "name": "Dave"},
]
for dept, members in itertools.groupby(data, key=lambda x: x["dept"]):
    print(dept, [m["name"] for m in members])

# takewhile / dropwhile
nums = [2, 4, 6, 7, 8, 10]
list(itertools.takewhile(lambda x: x % 2 == 0, nums))  # [2, 4, 6]
list(itertools.dropwhile(lambda x: x % 2 == 0, nums))  # [7, 8, 10]

# islice (lazy slicing for generators)
gen = (x**2 for x in range(1000000))
first_5 = list(itertools.islice(gen, 5))  # [0, 1, 4, 9, 16]

# compress (filter by selector)
data = ["a", "b", "c", "d"]
selectors = [True, False, True, False]
list(itertools.compress(data, selectors))  # ['a', 'c']


# --- itertools: infinite ---

# count: infinite counter
for i in itertools.islice(itertools.count(10, 2), 5):
    print(i)  # 10, 12, 14, 16, 18

# cycle: repeat forever
colors = itertools.cycle(["red", "green", "blue"])
[next(colors) for _ in range(5)]  # ['red', 'green', 'blue', 'red', 'green']

# repeat
list(itertools.repeat("hello", 3))  # ['hello', 'hello', 'hello']

# accumulate (running totals)
list(itertools.accumulate([1, 2, 3, 4, 5]))         # [1, 3, 6, 10, 15]
list(itertools.accumulate([1, 2, 3, 4], mul))        # [1, 2, 6, 24]
list(itertools.accumulate([3, 1, 4, 1, 5], max))     # [3, 3, 4, 4, 5]


# --- functools ---

# lru_cache: memoize function results
@lru_cache(maxsize=128)
def fibonacci(n: int) -> int:
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

fibonacci(100)             # Instant (cached)
fibonacci.cache_info()     # CacheInfo(hits=98, misses=101, ...)
fibonacci.cache_clear()    # Reset cache

# cache (unlimited, Python 3.9+)
@cache
def expensive_lookup(key: str) -> dict:
    return db.fetch(key)


# partial: freeze some arguments
def power(base, exp):
    return base ** exp

square = partial(power, exp=2)
cube = partial(power, exp=3)
square(5)  # 25
cube(3)    # 27

# Useful for callbacks
import logging
debug = partial(logging.log, logging.DEBUG)
debug("Connection established")


# reduce: fold left
total = reduce(add, [1, 2, 3, 4, 5])  # 15
product = reduce(mul, [1, 2, 3, 4, 5])  # 120

# Flatten deeply nested
def deep_flatten(nested):
    return reduce(
        lambda acc, x: acc + (deep_flatten(x) if isinstance(x, list) else [x]),
        nested, [],
    )

# Compose functions
def compose(*fns):
    return reduce(lambda f, g: lambda x: f(g(x)), fns)

process = compose(str.upper, str.strip, str.lower)
process("  Hello World  ")  # "HELLO WORLD"
```

itertools/functools patterns:
1. **`chain.from_iterable()`** — flatten nested iterables lazily
2. **`groupby()`** — group consecutive items (sort first for full grouping)
3. **`islice()`** — slice generators without consuming the whole thing
4. **`@lru_cache`** — memoize pure functions with bounded cache
5. **`partial()`** — create specialized functions by freezing arguments'''
    ),
    (
        "python/string-formatting",
        "Show Python string formatting patterns: f-strings, format spec, template strings, and text processing.",
        '''Python string formatting and text processing:

```python
from string import Template
from textwrap import dedent, indent, fill, shorten
import re


# --- f-string features (Python 3.12+) ---

name = "Alice"
score = 95.678
items = ["a", "b", "c"]

# Basic
f"Hello, {name}!"

# Expressions
f"Sum: {2 + 3}"
f"Items: {len(items)}"
f"Upper: {name.upper()}"

# Format spec (after colon)
f"{score:.2f}"        # "95.68"     — 2 decimal places
f"{score:>10.2f}"     # "     95.68" — right-align, width 10
f"{1234567:,}"        # "1,234,567" — thousands separator
f"{1234567:_}"        # "1_234_567" — underscore separator
f"{0.456:.1%}"        # "45.6%"     — percentage
f"{42:08b}"           # "00101010"  — binary, zero-padded
f"{255:02x}"          # "ff"        — hex
f"{42:+d}"            # "+42"       — always show sign

# Padding and alignment
f"{'left':<20}"       # "left                "
f"{'right':>20}"      # "               right"
f"{'center':^20}"     # "       center       "
f"{'padded':*^20}"    # "*******padded*******"

# Date formatting
from datetime import datetime
now = datetime.now()
f"{now:%Y-%m-%d %H:%M}"    # "2024-06-15 14:30"
f"{now:%B %d, %Y}"          # "June 15, 2024"

# Debug mode (Python 3.8+)
x = 42
f"{x = }"             # "x = 42"
f"{x = :.2f}"         # "x = 42.00"
f"{len(items) = }"    # "len(items) = 3"

# Nested f-strings
width = 10
f"{'hello':>{width}}"  # "     hello"

# Multiline f-strings
message = (
    f"User: {name}\\n"
    f"Score: {score:.1f}\\n"
    f"Items: {', '.join(items)}"
)


# --- textwrap ---

long_text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 3

# Wrap to 40 columns
print(fill(long_text, width=40))

# Shorten with ellipsis
shorten("Hello World, this is a long string", width=20)
# "Hello World, [...]"

# Dedent (remove common leading whitespace)
code = dedent("""\\
    def hello():
        print("world")
""")

# Indent all lines
indented = indent("line1\\nline2\\nline3", prefix="    ")


# --- Template strings (safe substitution) ---

# Safe for user-provided templates (no arbitrary code execution)
tmpl = Template("Hello, $name! You have $count messages.")
result = tmpl.substitute(name="Alice", count=5)

# safe_substitute: doesn't raise on missing keys
tmpl = Template("$greeting, $name!")
tmpl.safe_substitute(greeting="Hi")  # "Hi, $name!"


# --- Practical formatting ---

# Table formatting
def format_table(headers: list[str], rows: list[list]) -> str:
    widths = [
        max(len(str(h)), *(len(str(row[i])) for row in rows))
        for i, h in enumerate(headers)
    ]
    header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, widths))
    separator = "-+-".join("-" * w for w in widths)
    data_lines = [
        " | ".join(f"{str(v):<{w}}" for v, w in zip(row, widths))
        for row in rows
    ]
    return "\\n".join([header_line, separator, *data_lines])

print(format_table(
    ["Name", "Age", "City"],
    [["Alice", 30, "NYC"], ["Bob", 25, "LA"], ["Carol", 35, "Chicago"]],
))
# Name  | Age | City
# ------+-----+--------
# Alice | 30  | NYC
# Bob   | 25  | LA
# Carol | 35  | Chicago


# --- Byte size formatting ---

def human_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"

human_size(1536)        # "1.5 KB"
human_size(1073741824)  # "1.0 GB"
```

String formatting patterns:
1. **`f"{value:.2f}"`** — format spec for numbers, alignment, padding
2. **`f"{x = }"`** — debug mode shows variable name and value
3. **`textwrap.fill()`** — wrap long text to a column width
4. **`Template.safe_substitute()`** — safe user-provided templates (no code exec)
5. **`f"{now:%Y-%m-%d}"`** — datetime formatting inside f-strings'''
    ),
]
"""
