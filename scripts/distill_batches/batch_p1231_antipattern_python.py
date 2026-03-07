"""
Anti-pattern training pairs - Python anti-patterns
Topics: mutable defaults, bare except, global state, isinstance abuse, god classes
"""

pairs = [
    {
        "instruction": r'''Why does this function remember items from previous calls? I only want it to return the new item in a list.

```python
def add_item(item, items=[]):
    items.append(item)
    return items

print(add_item("a"))  # ['a']
print(add_item("b"))  # ['a', 'b']  -- why is 'a' here?!
```''',
        "output": r'''<think>
Classic mutable default argument bug. The default list is created once when the function is defined, not on each call. Every call that uses the default shares the same list object. The user is confused by the behavior, so I should explain the mechanism clearly.
</think>

This is Python's most infamous gotcha: **mutable default arguments**. The default `[]` is created once when the function is defined, not on each call. Every call that uses the default shares the same list object.

**What happens internally:**

```python
# Python does this at function definition time:
_default_list = []  # created ONCE

def add_item(item, items=_default_list):
    items.append(item)  # mutates the shared object
    return items
```

So `add_item("a")` appends to the shared list, and `add_item("b")` appends to the SAME list.

**The fix -- use None as a sentinel:**

```python
def add_item(item, items=None):
    if items is None:
        items = []  # fresh list on each call
    items.append(item)
    return items
```

Now each call without an explicit `items` argument gets its own new list.

**This applies to all mutable defaults**, not just lists:

```python
# BAD -- shared dict
def track(key, value, cache={}):
    cache[key] = value
    return cache

# BAD -- shared set
def register(name, registry=set()):
    registry.add(name)
    return registry

# GOOD -- None sentinel for all of them
def track(key, value, cache=None):
    if cache is None:
        cache = {}
    cache[key] = value
    return cache
```

**Why Python works this way:** Function defaults are part of the function object itself (stored in `func.__defaults__`). They are evaluated once at definition time for performance -- re-evaluating on every call would be slow. Immutable defaults like `int`, `str`, and `tuple` are fine because you cannot mutate them in place.'''
    },
    {
        "instruction": r'''I want my script to be resilient so I catch all exceptions:

```python
def process_data(filepath):
    try:
        data = load_file(filepath)
        result = transform(data)
        save_output(result)
    except:
        print("Something went wrong")
        return None
```''',
        "output": r'''<think>
Bare except clause -- catches everything including SystemExit, KeyboardInterrupt, and GeneratorExit. This makes bugs invisible, prevents Ctrl+C from working, and hides the actual error. The user thinks they are being "resilient" but they are actually making debugging impossible. I should show what specific exceptions to catch instead.
</think>

This bare `except:` is one of the worst anti-patterns in Python. It does not make your code resilient -- it makes bugs invisible.

**What bare except catches that it shouldn't:**
- `KeyboardInterrupt` -- Ctrl+C stops working. Your script becomes unkillable.
- `SystemExit` -- `sys.exit()` calls are swallowed silently.
- `MemoryError` -- your program is out of RAM but keeps limping along.
- The actual bug (maybe a `TypeError` in `transform()`) -- you will never find it because "Something went wrong" tells you nothing.

**The fix -- catch specific exceptions and log them:**

```python
import logging

logger = logging.getLogger(__name__)

def process_data(filepath):
    try:
        data = load_file(filepath)
    except FileNotFoundError:
        logger.error("File not found: %s", filepath)
        return None
    except PermissionError:
        logger.error("Cannot read file: %s", filepath)
        return None

    try:
        result = transform(data)
    except ValueError as e:
        logger.error("Invalid data in %s: %s", filepath, e)
        return None

    try:
        save_output(result)
    except IOError as e:
        logger.error("Failed to save output: %s", e)
        return None

    return result
```

**If you truly need a broad catch**, use `Exception` (not bare except) and always log the traceback:

```python
try:
    result = risky_operation()
except Exception:
    logger.exception("Unexpected error in risky_operation")
    return None
```

`except Exception` still lets `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit` propagate correctly. And `logger.exception()` records the full traceback so you can actually debug the problem.'''
    },
    {
        "instruction": r'''I use a global variable to share configuration across my modules:

```python
# config.py
current_user = None
db_connection = None
request_count = 0

# auth.py
import config
def login(user):
    config.current_user = user

# handler.py
import config
def handle_request():
    config.request_count += 1
    if config.current_user:
        return process(config.current_user)
```

This is simple and works. Any issues?''',
        "output": r'''<think>
Global mutable state anti-pattern. Multiple modules read and write shared globals. This creates hidden coupling, makes testing painful, is not thread-safe, and makes the code impossible to reason about because any module can change the state at any time. The user thinks simplicity is a feature but this becomes a nightmare at scale.
</think>

This pattern creates problems that are invisible now but will hurt badly as the project grows.

**Problem 1: Thread safety.** If you ever run this with multiple threads (or async), `request_count += 1` is a race condition and `current_user` will be wrong for concurrent requests. One user will see another user's data.

**Problem 2: Testing is painful.** Every test must reset global state, and tests cannot run in parallel:

```python
# Every test needs this boilerplate
def tearDown(self):
    config.current_user = None
    config.db_connection = None
    config.request_count = 0
# Forget one? Tests bleed into each other.
```

**Problem 3: Hidden dependencies.** Reading `handler.py` alone, you cannot tell what sets `current_user`. You must search the entire codebase. This gets worse with every module that touches the globals.

**The fix -- use explicit dependency injection:**

```python
from dataclasses import dataclass

@dataclass
class AppContext:
    current_user: str = None
    db_connection: object = None
    request_count: int = 0

# auth.py
def login(ctx, user):
    ctx.current_user = user

# handler.py
def handle_request(ctx):
    ctx.request_count += 1
    if ctx.current_user:
        return process(ctx.current_user)

# main.py -- one context per request
def main():
    ctx = AppContext(db_connection=create_db())
    login(ctx, "alice")
    handle_request(ctx)
```

Now each request can have its own context (thread-safe), testing is trivial (just create a fresh `AppContext()`), and every function's dependencies are visible in its signature.'''
    },
    {
        "instruction": r'''I'm validating input types throughout my codebase like this:

```python
def calculate_area(shape):
    if isinstance(shape, Circle):
        return 3.14159 * shape.radius ** 2
    elif isinstance(shape, Rectangle):
        return shape.width * shape.height
    elif isinstance(shape, Triangle):
        return 0.5 * shape.base * shape.height
    else:
        raise ValueError(f"Unknown shape: {type(shape)}")
```

I add a new elif every time we add a shape. Is there a cleaner way?''',
        "output": r'''<think>
isinstance chain anti-pattern -- the user is manually dispatching based on type instead of using polymorphism. Every new shape requires modifying this function (violates Open/Closed Principle). The user recognizes the smell ("I add a new elif every time") but doesn't know the fix. Classic case for polymorphism.
</think>

This is the isinstance chain anti-pattern. Every new shape forces you to modify `calculate_area`, and if you have other functions like `calculate_perimeter` or `draw`, each one needs the same growing chain. This violates the Open/Closed Principle -- the code should be open for extension but closed for modification.

**The fix -- use polymorphism:**

```python
from abc import ABC, abstractmethod
import math

class Shape(ABC):
    @abstractmethod
    def area(self) -> float:
        pass

class Circle(Shape):
    def __init__(self, radius: float):
        self.radius = radius

    def area(self) -> float:
        return math.pi * self.radius ** 2

class Rectangle(Shape):
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height

    def area(self) -> float:
        return self.width * self.height

class Triangle(Shape):
    def __init__(self, base: float, height: float):
        self.base = base
        self.height = height

    def area(self) -> float:
        return 0.5 * self.base * self.height
```

Now adding a new shape is just adding a new class -- you never touch existing code:

```python
class Trapezoid(Shape):
    def __init__(self, a, b, height):
        self.a, self.b, self.height = a, b, height

    def area(self):
        return 0.5 * (self.a + self.b) * self.height
```

And the calling code becomes shape-agnostic:

```python
def total_area(shapes):
    return sum(s.area() for s in shapes)
```

**When isinstance is acceptable:** Type checking at API boundaries (validating user input) or when you truly cannot modify the classes (third-party code). But for your own class hierarchies, use polymorphism.'''
    },
    {
        "instruction": r'''Here's my main application class. It handles everything:

```python
class Application:
    def __init__(self):
        self.db = sqlite3.connect("app.db")
        self.users = {}
        self.email_queue = []
        self.cache = {}
        self.logger = logging.getLogger()

    def create_user(self, name, email): ...
    def delete_user(self, user_id): ...
    def send_email(self, to, subject, body): ...
    def process_email_queue(self): ...
    def cache_get(self, key): ...
    def cache_set(self, key, value, ttl): ...
    def cache_invalidate(self, pattern): ...
    def generate_report(self, start_date, end_date): ...
    def export_csv(self, report_data): ...
    def handle_webhook(self, payload): ...
    def validate_api_key(self, key): ...
    def migrate_database(self): ...
    def backup_database(self): ...
    def healthcheck(self): ...
```

It's getting big but at least everything is in one place. Thoughts?''',
        "output": r'''<think>
God class anti-pattern. This single class handles user management, email, caching, reporting, CSV export, webhooks, auth, database ops, and health checks. It violates Single Responsibility Principle massively. Changes to email logic risk breaking caching. Testing requires instantiating the whole thing. The user sees the size growing but thinks "everything in one place" is a benefit.
</think>

This is called a "God Class" -- one class that knows and does everything. It feels convenient now, but it creates serious problems.

**Why it hurts:**
- **Changing email logic risks breaking caching** -- everything shares the same `self` state
- **Testing is impossible in isolation** -- to test `cache_get` you must set up a database, email queue, and logger
- **Multiple developers cannot work in parallel** -- everyone edits the same file and conflicts constantly
- **The class only grows** -- there is never a reason to remove methods, so it becomes 5000 lines

**The fix -- split by responsibility:**

```python
class UserRepository:
    def __init__(self, db):
        self.db = db

    def create(self, name, email): ...
    def delete(self, user_id): ...

class EmailService:
    def __init__(self):
        self.queue = []

    def send(self, to, subject, body): ...
    def process_queue(self): ...

class CacheService:
    def __init__(self):
        self.store = {}

    def get(self, key): ...
    def set(self, key, value, ttl): ...
    def invalidate(self, pattern): ...

class ReportGenerator:
    def __init__(self, db):
        self.db = db

    def generate(self, start_date, end_date): ...
    def export_csv(self, report_data): ...

class Application:
    """Thin coordinator -- delegates to focused services."""
    def __init__(self):
        db = sqlite3.connect("app.db")
        self.users = UserRepository(db)
        self.email = EmailService()
        self.cache = CacheService()
        self.reports = ReportGenerator(db)
```

Now each class has one reason to change, can be tested independently, and can be worked on by different developers without conflicts. The `Application` class becomes a thin shell that wires services together.'''
    },
]
