"""
Proactive alternatives training pairs - Python idioms and patterns
"""

pairs = [
    {
        "instruction": r'''I'm building a plugin system for my app. I have a base class `Plugin` and I want each plugin to inherit from it, overriding methods like `on_load`, `on_event`, etc. I have about 20 plugins planned. Can you help me set up the inheritance hierarchy?''',
        "output": r'''<think>
Inheritance can work for plugins, but with 20 plugins it will get rigid fast. If plugins need to mix capabilities (e.g., one plugin handles both events and logging), deep inheritance leads to diamond problems or awkward multiple inheritance. Composition with a protocol/interface pattern is more flexible -- plugins register handlers rather than overriding methods. I should acknowledge inheritance works, then show the composition alternative.
</think>

Inheritance will work for this, especially if your plugins are simple. But with 20 plugins planned, you might find composition gives you more flexibility -- plugins can mix and match capabilities without running into multiple inheritance headaches.

Here is the inheritance approach you described:

```python
class Plugin:
    def on_load(self):
        pass

    def on_event(self, event):
        pass

class MyPlugin(Plugin):
    def on_load(self):
        print("Loaded")

    def on_event(self, event):
        print(f"Got {event}")
```

And here is a composition-based alternative that scales better:

```python
from typing import Protocol, Callable

class EventHandler(Protocol):
    def __call__(self, event: dict) -> None: ...

class PluginManager:
    def __init__(self):
        self._loaders: list[Callable] = []
        self._handlers: dict[str, list[EventHandler]] = {}

    def on_load(self, func: Callable) -> Callable:
        self._loaders.append(func)
        return func

    def on_event(self, event_type: str):
        def decorator(func: EventHandler) -> EventHandler:
            self._handlers.setdefault(event_type, []).append(func)
            return func
        return decorator

    def load_all(self):
        for loader in self._loaders:
            loader()

    def emit(self, event_type: str, event: dict):
        for handler in self._handlers.get(event_type, []):
            handler(event)

# Usage -- plugins are just decorated functions
pm = PluginManager()

@pm.on_load
def setup_logging():
    print("Logging ready")

@pm.on_event("user_action")
def track_action(event: dict):
    print(f"Tracked: {event}")
```

The composition approach means each plugin file can register multiple handlers without needing a class at all. Adding new hook types is just adding a new decorator method, and plugins can handle multiple event types without awkward multi-inheritance.

Your inheritance approach is totally valid for a smaller set of simple plugins though -- pick whichever fits your complexity level.'''
    },
    {
        "instruction": r'''I need to build a log line from several variables. I'm using string concatenation like this:

```python
log = "User " + username + " performed " + action + " on " + resource + " at " + timestamp
```

It works but it's getting unwieldy with more fields. Any tips for keeping it clean?''',
        "output": r'''<think>
String concatenation works but is hard to read and error-prone with spacing. Since they already feel it is unwieldy, they are ready to hear about f-strings. f-strings are faster than concatenation and much more readable. I should show the direct improvement and mention .format() as another option for cases where the template is stored separately.
</think>

Since you are already finding it unwieldy, f-strings are the natural upgrade here. They are actually faster than concatenation in CPython and much easier to read:

```python
log = f"User {username} performed {action} on {resource} at {timestamp}"
```

That is it -- same result, one clean line. A few more tricks with f-strings that help with log formatting:

```python
# Padding and alignment
log = f"User {username:<20} Action {action:<15} Resource {resource}"

# Expressions inside the braces
log = f"User {username.upper()} performed {action} at {datetime.now():%Y-%m-%d %H:%M}"

# Multiline with parentheses for really long lines
log = (
    f"User {username} "
    f"performed {action} "
    f"on {resource} "
    f"at {timestamp}"
)
```

One case where you would NOT want f-strings: if the template string is loaded from a config file or passed around as data. In that case, use `.format()`:

```python
# Template stored in config
template = "User {username} performed {action} on {resource}"
log = template.format(username=username, action=action, resource=resource)
```

But for inline string building like your example, f-strings are the way to go. They were added in Python 3.6 and are now the standard approach.'''
    },
    {
        "instruction": r'''I need to find all pairs of items from two lists where the sum is greater than 10. Here's my code:

```python
results = []
for x in list_a:
    for y in list_b:
        if x + y > 10:
            results.append((x, y))
```

Works fine but I have a feeling there's a more Pythonic way?''',
        "output": r'''<think>
The nested loop works perfectly. There are two alternatives: a list comprehension (more Pythonic, same performance) and itertools.product (cleaner when you have more than two iterables). Since they asked about being more Pythonic, I should show both and let them pick. The list comprehension is the most common Python idiom here.
</think>

Your instinct is right -- there is a more compact way. A list comprehension handles this nicely:

```python
results = [(x, y) for x in list_a for y in list_b if x + y > 10]
```

Same logic, same performance, just more concise. For two lists this is the standard Pythonic approach.

If you ever need to combine more than two lists, or want to make the "Cartesian product" intent more explicit, `itertools.product` is handy:

```python
from itertools import product

results = [(x, y) for x, y in product(list_a, list_b) if x + y > 10]
```

With three lists, the difference is clearer:

```python
# Nested loops get deep fast
results = []
for x in list_a:
    for y in list_b:
        for z in list_c:
            if x + y + z > 10:
                results.append((x, y, z))

# vs product
results = [
    (x, y, z)
    for x, y, z in product(list_a, list_b, list_c)
    if x + y + z > 10
]
```

For your two-list case, the simple list comprehension is the sweet spot. Your original loop is perfectly fine too -- readability is subjective and some teams prefer explicit loops over dense comprehensions.'''
    },
    {
        "instruction": r'''I need to parse a CSV file and also work with some file paths. I'm doing it manually:

```python
with open('data/report.csv', 'r') as f:
    lines = f.readlines()
    headers = lines[0].strip().split(',')
    for line in lines[1:]:
        fields = line.strip().split(',')
        # process fields...

import os
full_path = os.path.join(base_dir, 'data', 'report.csv')
parent = os.path.dirname(full_path)
```

This works but is there a cleaner way?''',
        "output": r'''<think>
Two things to improve: manual CSV parsing breaks on quoted fields with commas (e.g., "Smith, John"), and os.path is functional but pathlib is more ergonomic. The csv module handles edge cases properly, and pathlib gives object-oriented path manipulation. I should show both improvements and explain why manual CSV splitting is actually a bug waiting to happen.
</think>

Your approach works for simple CSVs, but the manual split on commas will break if any field contains a comma (like `"Smith, John"` or `"$1,200"`). The `csv` module handles quoting, escaping, and edge cases automatically:

```python
import csv
from pathlib import Path

# pathlib for path handling
base = Path(base_dir)
csv_path = base / 'data' / 'report.csv'
parent = csv_path.parent

# csv module for parsing
with csv_path.open() as f:
    reader = csv.DictReader(f)
    for row in reader:
        # row is a dict: {'name': 'Alice', 'score': '95', ...}
        print(row['name'], row['score'])
```

The `csv.DictReader` maps each row to a dictionary using the header line, so you get named access instead of index-based access. No more remembering that `fields[3]` is the email column.

For pathlib, here are some handy operations compared to `os.path`:

```python
from pathlib import Path

p = Path('data/report.csv')

# Common operations
p.exists()              # os.path.exists()
p.parent                # os.path.dirname()
p.name                  # os.path.basename()
p.suffix                # '.csv'
p.stem                  # 'report'
p.read_text()           # open + read + close in one call
p.with_suffix('.json')  # Path('data/report.json')

# Glob for finding files
for csv_file in Path('data').glob('*.csv'):
    print(csv_file)
```

Your `os.path` code is not wrong -- it is stable and works everywhere. But pathlib (available since Python 3.4) reads more naturally and the `/` operator for joining paths is quite nice once you get used to it.'''
    },
    {
        "instruction": r'''I have a few modules in my app that need access to a database connection and a config object. I'm using global variables:

```python
# globals.py
db_connection = None
config = None

def init(db, cfg):
    global db_connection, config
    db_connection = db
    config = cfg
```

Then I import from globals.py wherever I need them. Is this fine for a medium-sized app?''',
        "output": r'''<think>
Global state works for small scripts but causes problems as apps grow: hard to test (must mock globals), implicit dependencies (not clear what a function needs), thread safety issues, and difficult to run multiple configurations. Dependency injection is the cleaner pattern -- pass dependencies explicitly. I should acknowledge it works and explain what breaks as the app scales.
</think>

It will work, and for a small script nobody would argue with it. But for a medium-sized app, you will likely hit a few pain points:

1. **Testing is hard** -- every test that touches db_connection needs to patch the global
2. **Hidden dependencies** -- you cannot tell what a function needs without reading its body
3. **Thread safety** -- if you ever go async or multi-threaded, shared mutable globals are risky

A simple dependency injection approach fixes all three:

```python
from dataclasses import dataclass

@dataclass
class AppContext:
    db_connection: object
    config: dict

# Functions declare what they need
def get_user(ctx: AppContext, user_id: int):
    return ctx.db_connection.execute(
        "SELECT * FROM users WHERE id = %s", (user_id,)
    )

def create_app() -> AppContext:
    db = connect_to_database(...)
    cfg = load_config("config.yaml")
    return AppContext(db=db, config=cfg)

# Entry point
ctx = create_app()
user = get_user(ctx, 42)
```

For a web app, most frameworks have built-in DI. For example, Flask has `g` and `current_app`, FastAPI has `Depends`:

```python
# FastAPI example
from fastapi import Depends

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users/{user_id}")
def read_user(user_id: int, db: Session = Depends(get_db)):
    return db.query(User).filter(User.id == user_id).first()
```

The key benefit: every function's dependencies are visible in its signature. Tests become straightforward because you just pass in a mock context instead of patching globals.

Your global approach is fine for prototyping or small tools -- just be aware of where it starts to hurt if the app grows.'''
    },
]
