"""Phase 1A: Foundation Thinking — Systematic Debugging (Part 2/4)
Silent data corruption, state mutation, async ordering, import cycles."""

PAIRS = [
    (
        "thinking/debug-timezone-silent-corruption",
        "Users in different timezones see events at wrong times. An event created at '3:00 PM EST' shows as '3:00 PM' for a user in PST (should show 12:00 PM PST). The code:\n\n```python\nfrom datetime import datetime\n\ndef create_event(title, event_time_str, timezone_str):\n    # Parse the user's input\n    event_time = datetime.strptime(event_time_str, '%Y-%m-%d %H:%M')\n    # Store in database\n    db.execute(\n        'INSERT INTO events (title, event_time, timezone) VALUES (?, ?, ?)',\n        (title, event_time, timezone_str)\n    )\n\ndef get_event_for_user(event_id, user_timezone):\n    event = db.get_event(event_id)\n    # Just return the stored time\n    return {\n        'title': event.title,\n        'time': event.event_time.strftime('%Y-%m-%d %H:%M'),\n        'timezone': event.timezone,\n    }\n```",
        r'''<think>
Let me trace through the data flow with the user's example.

**Creating the event:**
- User input: "3:00 PM EST" → `event_time_str='2026-03-05 15:00'`, `timezone_str='EST'`
- `datetime.strptime('2026-03-05 15:00', '%Y-%m-%d %H:%M')` → `datetime(2026, 3, 5, 15, 0)` — a **naive** datetime (no timezone info!)
- Stored in DB: `datetime(2026, 3, 5, 15, 0)` + `'EST'` as separate fields

**Retrieving for a PST user:**
- `event.event_time` = `datetime(2026, 3, 5, 15, 0)` (naive, no tz)
- `event.timezone` = `'EST'`
- Returns `'2026-03-05 15:00'` with timezone `'EST'`

The problem: the function ignores the user's timezone entirely. It returns the stored time as-is. A PST user sees "3:00 PM EST" — the timezone label is there, but no conversion happens. The user report says they see "3:00 PM" without "EST", which means the timezone isn't even displayed.

But actually there are multiple bugs here:

**Bug 1: Naive datetime (no timezone awareness)**
`datetime.strptime` creates a naive datetime — it has no concept of timezone. The timezone is stored as a separate string, disconnected from the actual time value. This means:
- No conversion is possible without manually parsing the timezone string
- The datetime object can't be compared meaningfully with other datetimes in different zones
- Daylight saving time transitions are impossible to handle correctly

**Bug 2: No conversion to user's timezone**
The code returns the raw stored time regardless of who's viewing it. A PST user should see the time converted to PST.

**Bug 3: Storing timezone as a string abbreviation**
`'EST'` is ambiguous — it could mean US Eastern Standard Time (UTC-5) or Eastern Standard Time in Australia (UTC+10). Also, 'EST' doesn't tell you about DST. During summer, US Eastern is EDT (UTC-4), not EST. Using abbreviations makes DST handling incorrect.

**Bug 4: The stored time might not be in UTC**
Best practice is to store all times in UTC and convert to the user's timezone on display. Storing in the creator's local timezone plus a timezone string is fragile.

**The correct approach:**
1. Parse the input with timezone awareness
2. Convert to UTC for storage
3. Store a single `TIMESTAMP WITH TIME ZONE` column (or UTC timestamp)
4. Convert to the viewer's timezone on retrieval
</think>

Four bugs, all related to timezone handling:

1. **Naive datetime** — `datetime.strptime` creates a timezone-unaware object
2. **No conversion** — returns raw stored time regardless of viewer's timezone
3. **Ambiguous timezone string** — `'EST'` is ambiguous, doesn't handle DST
4. **Not stored in UTC** — stored in creator's local time

### Fixed version

```python
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

def create_event(title, event_time_str, timezone_str):
    # Parse with timezone awareness
    tz = ZoneInfo(timezone_str)  # Use IANA names: 'America/New_York', not 'EST'
    local_time = datetime.strptime(event_time_str, '%Y-%m-%d %H:%M')
    aware_time = local_time.replace(tzinfo=tz)

    # Convert to UTC for storage
    utc_time = aware_time.astimezone(ZoneInfo('UTC'))

    db.execute(
        'INSERT INTO events (title, event_time_utc) VALUES (?, ?)',
        (title, utc_time)
    )

def get_event_for_user(event_id, user_timezone):
    event = db.get_event(event_id)

    # Convert from UTC to user's timezone
    utc_time = event.event_time_utc.replace(tzinfo=ZoneInfo('UTC'))
    user_tz = ZoneInfo(user_timezone)  # e.g., 'America/Los_Angeles'
    local_time = utc_time.astimezone(user_tz)

    return {
        'title': event.title,
        'time': local_time.strftime('%Y-%m-%d %H:%M'),
        'timezone': str(user_tz),
    }
```

**Trace with the fix:**
```
Create: "3:00 PM" in America/New_York
  → 2026-03-05 15:00 EST (UTC-5)
  → Stored as: 2026-03-05 20:00 UTC

Retrieve for America/Los_Angeles (PST, UTC-8):
  → 2026-03-05 20:00 UTC → 2026-03-05 12:00 PST
  → User sees: "12:00 PM" ✓
```

### The golden rules of timezone handling

1. **Store in UTC** — always. No exceptions.
2. **Use IANA names** — `'America/New_York'` not `'EST'` (handles DST automatically)
3. **Convert on display** — UTC → user's timezone at the last moment
4. **Never use naive datetimes** — always attach timezone info'''
    ),
    (
        "thinking/debug-state-mutation-aliasing",
        "We have a function that applies default settings to user preferences. But changing one user's preferences changes ALL users' defaults:\n\n```python\nDEFAULT_PREFS = {\n    'theme': 'light',\n    'notifications': {'email': True, 'sms': False, 'push': True},\n    'language': 'en',\n}\n\ndef get_user_prefs(user_id):\n    saved = db.get_prefs(user_id)  # Returns saved overrides or None\n    prefs = DEFAULT_PREFS\n    if saved:\n        prefs.update(saved)\n    return prefs\n\n# Later in the code:\nprefs = get_user_prefs(42)\nprefs['notifications']['push'] = False  # User 42 disables push\n\n# Now ALL future calls return push=False!\nnew_user_prefs = get_user_prefs(99)  # push is False here too!\n```",
        r'''<think>
Classic Python aliasing bug. Let me trace the references.

`DEFAULT_PREFS` is a module-level dict (a mutable global).

In `get_user_prefs`:
```python
prefs = DEFAULT_PREFS  # NOT a copy — prefs IS DEFAULT_PREFS (same object)
```

This is an assignment, not a copy. `prefs` and `DEFAULT_PREFS` are two names for the SAME dictionary object. `id(prefs) == id(DEFAULT_PREFS)` is True.

When `prefs.update(saved)` runs, it mutates DEFAULT_PREFS directly.

Then in the calling code:
```python
prefs = get_user_prefs(42)  # Returns THE DEFAULT_PREFS object itself
prefs['notifications']['push'] = False  # Mutates DEFAULT_PREFS!
```

Now `DEFAULT_PREFS['notifications']['push']` is `False` for the rest of the program's lifetime. Every subsequent call to `get_user_prefs` returns the mutated DEFAULT_PREFS.

Even worse: `prefs.update(saved)` also mutates DEFAULT_PREFS. So if user 42 has `saved = {'theme': 'dark'}`, now DEFAULT_PREFS has `theme: 'dark'` permanently. Every user after 42 gets dark theme as the "default."

**Fix options:**

1. **Shallow copy**: `prefs = DEFAULT_PREFS.copy()` — but this only copies the top-level dict. Nested dicts like `notifications` are still shared references.

2. **Deep copy**: `prefs = copy.deepcopy(DEFAULT_PREFS)` — copies everything recursively. Nested dicts get their own copies.

3. **Immutable defaults**: Use a frozen/immutable structure. But Python dicts aren't easily frozen.

The shallow copy trap:
```python
prefs = DEFAULT_PREFS.copy()  # New top-level dict
prefs['notifications']['push'] = False  # STILL mutates DEFAULT_PREFS!
```
Because `prefs['notifications']` is the SAME dict object as `DEFAULT_PREFS['notifications']`. The copy only creates a new top-level dict; nested objects are still shared.

Deep copy is the correct fix here.
</think>

**Mutable default aliasing.** `prefs = DEFAULT_PREFS` doesn't create a copy — it's a reference to the same object. Mutations through `prefs` directly modify `DEFAULT_PREFS`.

```python
prefs = DEFAULT_PREFS           # Same object!
id(prefs) == id(DEFAULT_PREFS)  # True

prefs['theme'] = 'dark'         # DEFAULT_PREFS is now dark too
```

### Shallow copy is NOT enough

```python
prefs = DEFAULT_PREFS.copy()              # New top-level dict
prefs['notifications']['push'] = False    # STILL mutates DEFAULT_PREFS!
# Because prefs['notifications'] IS DEFAULT_PREFS['notifications']
```

### Fix: deep copy

```python
import copy

DEFAULT_PREFS = {
    'theme': 'light',
    'notifications': {'email': True, 'sms': False, 'push': True},
    'language': 'en',
}

def get_user_prefs(user_id):
    prefs = copy.deepcopy(DEFAULT_PREFS)  # Independent copy, all levels
    saved = db.get_prefs(user_id)
    if saved:
        deep_merge(prefs, saved)  # Merge without mutating DEFAULT_PREFS
    return prefs

def deep_merge(base, override):
    """Recursively merge override into base (mutates base, not the original default)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
```

### The rule

In Python, assignment (`=`) never copies. It creates a new reference to the same object. For mutable objects (dict, list, set), this means mutations through one reference affect all references. Always use `.copy()` for flat structures or `copy.deepcopy()` for nested structures.'''
    ),
    (
        "thinking/debug-state-mutation-default-arg",
        "This function is supposed to collect items into groups. The first call works fine, but subsequent calls have leftover items from previous calls:\n\n```python\ndef group_items(items, groups={}):n    for item in items:\n        key = item['category']\n        if key not in groups:\n            groups[key] = []\n        groups[key].append(item)\n    return groups\n\n# First call\nresult1 = group_items([{'category': 'A', 'name': 'x'}, {'category': 'B', 'name': 'y'}])\n# result1 = {'A': [{'category': 'A', 'name': 'x'}], 'B': [{'category': 'B', 'name': 'y'}]}\n\n# Second call — should be independent!\nresult2 = group_items([{'category': 'C', 'name': 'z'}])\n# result2 = {'A': [...], 'B': [...], 'C': [...]}  ← WHY does it have A and B?!\n```",
        r'''<think>
This is the classic "mutable default argument" bug in Python — one of the most common Python gotchas.

The default argument `groups={}` is evaluated ONCE when the function is defined, not each time the function is called. This means every call that doesn't provide `groups` shares the SAME dict object.

Let me trace:

**Function definition:**
```python
def group_items(items, groups={}):
    # groups is created ONCE here: id(groups) = 0x7f...abc
```

**First call: `group_items([...])`**
- `groups` defaults to the shared dict (currently empty: `{}`)
- Loop adds items: `{'A': [...], 'B': [...]}`
- Returns the shared dict
- The shared dict is now `{'A': [...], 'B': [...]}`

**Second call: `group_items([...])`**
- `groups` defaults to the SAME shared dict (now contains `{'A': [...], 'B': [...]}`)
- Loop adds more items: now `{'A': [...], 'B': [...], 'C': [...]}`
- Returns the shared dict with accumulated data from ALL calls

The function accumulates state across calls through the mutable default argument.

Python created this behavior because:
1. Default arguments are expressions
2. Expressions are evaluated at definition time (when `def` runs)
3. The result is stored as part of the function object
4. On each call, the stored default is used if no argument is provided

You can see the shared default object:
```python
>>> group_items.__defaults__
({},)  # This is the shared dict, modified by every call
```

The fix is to use `None` as the default and create a new dict inside the function:
```python
def group_items(items, groups=None):
    if groups is None:
        groups = {}  # New dict for EACH call
```
</think>

**Mutable default argument.** `groups={}` is evaluated once at function definition. Every call shares the same dict, accumulating items across calls.

```python
# You can see the shared object:
>>> group_items.__defaults__
({},)  # This dict persists and grows with each call
```

### Fix: use None sentinel

```python
def group_items(items, groups=None):
    if groups is None:
        groups = {}  # Fresh dict for each call
    for item in items:
        key = item['category']
        if key not in groups:
            groups[key] = []
        groups[key].append(item)
    return groups
```

### The Python default argument rule

```python
# DANGEROUS: mutable defaults (evaluated once, shared across calls)
def bad(items=[]):     # List is shared
def bad(config={}):    # Dict is shared
def bad(seen=set()):   # Set is shared

# SAFE: immutable defaults or None sentinel
def good(items=None):
    items = items if items is not None else []
def good(config=None):
    config = config or {}
```

This applies to ALL mutable default arguments: lists, dicts, sets, and custom objects.'''
    ),
    (
        "thinking/debug-import-cycle",
        "Our Flask app crashes on startup with `ImportError: cannot import name 'db' from partially initialized module 'app.database'`. The project structure:\n\n```python\n# app/database.py\nfrom app.models import User  # Need User for type hints\n\ndb = SQLAlchemy()\n\ndef get_user(user_id) -> User:\n    return User.query.get(user_id)\n```\n\n```python\n# app/models.py\nfrom app.database import db  # Need db for model base\n\nclass User(db.Model):\n    id = db.Column(db.Integer, primary_key=True)\n    name = db.Column(db.String(100))\n```",
        r'''<think>
Let me trace the import sequence.

Python resolves imports by executing the module file top-to-bottom. When module A imports from module B, Python starts executing B's file. If B also imports from A, and A hasn't finished executing yet, you get a circular import.

**Scenario: Something imports `app.database` first.**

1. Python starts executing `app/database.py`
2. Line 1: `from app.models import User`
3. Python starts executing `app/models.py` (it hasn't been imported yet)
4. Line 1 of models.py: `from app.database import db`
5. Python checks: is `app.database` already being imported? YES — it's partially initialized (only executed line 1)
6. Python tries to find `db` in the partially initialized `app.database` module
7. `db` hasn't been defined yet (it's on line 3, which hasn't executed)
8. `ImportError: cannot import name 'db' from partially initialized module 'app.database'`

The circular dependency:
```
database.py → imports → models.py → imports → database.py (circular!)
```

**Fix options:**

1. **Move the import inside the function (lazy import)**:
   ```python
   # database.py
   db = SQLAlchemy()
   def get_user(user_id):
       from app.models import User  # Import at use time, not module load time
       return User.query.get(user_id)
   ```
   This breaks the cycle because `app.models` isn't imported until `get_user` is called, by which time both modules are fully initialized.

2. **Use TYPE_CHECKING for type hints**:
   ```python
   from __future__ import annotations
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from app.models import User
   ```
   `TYPE_CHECKING` is `False` at runtime, so the import doesn't execute. The type hint still works for static analysis because `from __future__ import annotations` makes all annotations strings (lazy evaluation).

3. **Restructure to break the cycle**:
   Put `db` in a third module that both can import without cycles:
   ```
   app/extensions.py  ← db = SQLAlchemy() (no imports from models)
   app/models.py      ← imports db from extensions
   app/database.py    ← imports db from extensions, imports User from models
   ```

Option 3 is the cleanest long-term solution. It's the standard Flask pattern.
</think>

**Circular import.** `database.py` imports from `models.py` which imports from `database.py`. Python can't resolve this because `db` hasn't been defined yet when `models.py` tries to import it.

```
database.py starts → imports models.py → models.py starts → imports database.py (partial!)
                                                              → db not defined yet → CRASH
```

### Fix: extract shared objects into a third module

```python
# app/extensions.py (no imports from app modules)
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
```

```python
# app/models.py
from app.extensions import db  # No cycle: extensions doesn't import models

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
```

```python
# app/database.py
from app.extensions import db
from app.models import User  # Safe: models imports from extensions, not database

def get_user(user_id) -> User:
    return User.query.get(user_id)
```

**Import graph (no cycles):**
```
extensions.py ← models.py ← database.py
              ↖─────────────────────────┘
```

### Quick fix for type hints only: TYPE_CHECKING

```python
# database.py
from __future__ import annotations  # Makes annotations lazy (strings)
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Only True during mypy/pyright, False at runtime
    from app.models import User

db = SQLAlchemy()

def get_user(user_id) -> User:  # Works for type checking, no runtime import
    return db.session.get(User, user_id)
```'''
    ),
    (
        "thinking/debug-regex-greedy-html",
        "Our HTML sanitizer is supposed to strip tags but it removes too much content:\n\n```python\nimport re\n\ndef strip_tags(html):\n    return re.sub(r'<.*>', '', html)\n\n# Expected: 'Hello World'\n# Actual:   ''\nprint(strip_tags('<b>Hello</b> <i>World</i>'))\n```",
        r'''<think>
The regex `<.*>` uses the `.*` quantifier which is GREEDY by default. Greedy means it matches AS MUCH AS POSSIBLE.

Let me trace the regex against `<b>Hello</b> <i>World</i>`:

1. `<` matches the first `<`
2. `.*` greedily consumes EVERYTHING up to the end of the string: `b>Hello</b> <i>World</i>`
3. Now `>` needs to match. The regex backtracks from the end:
   - `<i>World</i>` — last char is `>` — it ends with `>`!
4. So `.*` matches `b>Hello</b> <i>World</i` and `>` matches the final `>`

The full match: `<b>Hello</b> <i>World</i>` — the ENTIRE string!

After `re.sub`, everything is removed: `''`.

The problem: `.*` matches across HTML tags because `.` matches `>` characters too. The greedy quantifier extends the match to the LAST `>` in the string, not the first.

**Fix options:**

1. **Non-greedy quantifier**: `<.*?>` — matches as LITTLE as possible
   - `<` matches first `<`
   - `.*?` matches as little as possible: nothing initially
   - `>` needs to match: checks next char `b` — no. `.*?` expands to match `b`, then tries `>` again: the next char is `>` — yes!
   - First match: `<b>`. Then continues and matches `</b>`, `<i>`, `</i>`.
   - Result: `'Hello World'` ✓

2. **Negated character class**: `<[^>]*>` — matches any character EXCEPT `>`
   - This is actually more efficient because it doesn't require backtracking
   - `[^>]*` cannot match past a `>`, so each tag is matched individually

3. **Use an HTML parser** (proper fix for real sanitization):
   ```python
   from html.parser import HTMLParser
   ```
   Regex-based HTML parsing is fragile and can have security bypasses.
</think>

**Greedy `.*` matches across tags.** The `.*` greedily consumes everything from the first `<` to the LAST `>` in the entire string.

```
Input:  <b>Hello</b> <i>World</i>
Match:  <b>Hello</b> <i>World</i>   ← one giant match
         ^^^^^^^^^^^^^^^^^^^^^^^^^^
Result: ''  (everything removed)
```

### Fix 1: Non-greedy `.*?`

```python
def strip_tags(html):
    return re.sub(r'<.*?>', '', html)
# <b>Hello</b> <i>World</i>
# Matches: <b>, </b>, <i>, </i> (individually)
# Result: 'Hello World'
```

### Fix 2: Negated character class (faster, no backtracking)

```python
def strip_tags(html):
    return re.sub(r'<[^>]*>', '', html)
# [^>]* matches anything EXCEPT '>', so it can't span across tags
```

### Fix 3: Use an HTML parser (correct for real sanitization)

```python
from html.parser import HTMLParser
from io import StringIO

class TagStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = StringIO()

    def handle_data(self, data):
        self._text.write(data)

    def get_text(self):
        return self._text.getvalue()

def strip_tags(html):
    s = TagStripper()
    s.feed(html)
    return s.get_text()
```

Regex can't handle edge cases like `<script>var x = '<b>';</script>` or malformed HTML. Use a parser for security-critical sanitization.'''
    ),
    (
        "thinking/debug-type-coercion-js-equality",
        "This JavaScript validation function sometimes lets invalid data through:\n\n```javascript\nfunction validateAge(age) {\n    if (age == '') return false;  // Empty string check\n    if (age == null) return false;  // Null check\n    if (age < 0 || age > 150) return false;  // Range check\n    return true;\n}\n\n// Bug: validateAge(0) returns false, but 0 is a valid age!\n// Bug: validateAge('') should return false but... wait, it does. Hmm.\n// Bug: validateAge(null) should return false but... it does too.\n// So what's actually wrong?\n```\n\nActually, the real report is: `validateAge([])` returns `true`, and `validateAge('abc')` returns `true`.",
        r'''<think>
JavaScript's `==` operator does type coercion, which creates all sorts of unexpected behavior. Let me trace through each case.

**Case 1: `validateAge(0)`**
- `0 == ''` → JavaScript coerces: `0 == 0` → `true`! (empty string coerces to 0)
- First check returns `false` — but 0 IS a valid age! Bug!

**Case 2: `validateAge([])`**
- `[] == ''` → JavaScript coerces: `'' == ''` → `true`... wait, let me re-check.
  Actually: `[] == ''` → Array is coerced via `.toString()` → `'' == ''` → `true`
- First check returns `false`. So `[]` should be rejected? Let me re-read the report.

Hmm wait, let me be more careful with JS coercion rules.

`[] == ''`:
1. Array vs string: Array is converted to primitive via `[].toString()` = `''`
2. `'' == ''` → `true`
3. So the first check `age == ''` catches it... and returns `false`. So `[]` IS rejected.

But the report says `validateAge([])` returns `true`. Let me re-examine.

Oh wait — maybe the array isn't empty. Let me check `validateAge([5])`:
- `[5] == ''` → `[5].toString()` = `'5'`, `'5' == ''` → `false`
- `[5] == null` → `false` (only `null == undefined` is true in loose equality)
- `[5] < 0` → `[5]` is coerced to `5`, `5 < 0` → `false`
- `[5] > 150` → `5 > 150` → `false`
- Returns `true`! But `[5]` is not a valid age — it's an array!

**Case 3: `validateAge('abc')`**
- `'abc' == ''` → `false`
- `'abc' == null` → `false`
- `'abc' < 0` → `NaN < 0` → `false` (NaN comparisons are always false!)
- `'abc' > 150` → `NaN > 150` → `false` (NaN again!)
- Returns `true`! But 'abc' is not a valid age!

The NaN issue is critical: any comparison with NaN returns false, so the range check PASSES for non-numeric strings. `'abc'` < 0 is false AND `'abc'` > 150 is false, so it passes both checks.

**Summary of bugs:**
1. `age == ''` uses loose equality: catches `0`, `false`, `[]` — not just empty string
2. `age == null` uses loose equality: catches `undefined` too (intentional?) but not other falsy values
3. Range check doesn't handle NaN: non-numeric strings pass because NaN comparisons are always false
4. No type checking: arrays, objects, functions all make it through

**Fix: use strict equality and explicit type checking**
</think>

JavaScript's `==` (loose equality) and NaN comparison rules create multiple bypasses:

### Bug analysis

| Input | `age == ''` | `age == null` | `age < 0 \|\| age > 150` | Returns | Correct? |
|-------|------------|--------------|--------------------------|---------|----------|
| `0` | `true` (coercion!) | — | — | `false` | Wrong — 0 is valid |
| `'abc'` | `false` | `false` | `NaN < 0` → `false`; `NaN > 150` → `false` | `true` | Wrong |
| `[5]` | `false` | `false` | `5 < 0` → `false`; `5 > 150` → `false` | `true` | Wrong |
| `null` | `false` | `true` | — | `false` | Correct |

**Why `0 == ''` is `true`:** JS coerces empty string to `0`, then compares `0 == 0`.
**Why `'abc'` passes range check:** `Number('abc')` is `NaN`. ALL comparisons with `NaN` return `false`, including `<` and `>`.

### Fixed version

```javascript
function validateAge(age) {
    // Strict type check first
    if (typeof age !== 'number') return false;
    // NaN check (NaN is typeof 'number' but isn't a number)
    if (Number.isNaN(age)) return false;
    // Must be an integer
    if (!Number.isInteger(age)) return false;
    // Range check
    if (age < 0 || age > 150) return false;
    return true;
}
```

### The rule: always use `===` in JavaScript

```javascript
0 == ''     // true  (type coercion)
0 === ''    // false (strict: different types)

null == undefined  // true  (special case)
null === undefined // false (strict)

[] == false // true  ([] → '' → 0 → false)
[] === false // false
```'''
    ),
    (
        "thinking/debug-orm-query-wrong-results",
        "Our report shows wrong revenue numbers. The query joins orders with order_items and applies a discount, but the totals are inflated:\n\n```python\n# SQLAlchemy query\nresults = (\n    db.session.query(\n        Order.customer_id,\n        func.sum(OrderItem.price * OrderItem.quantity).label('total_revenue'),\n        func.count(Order.id).label('order_count'),\n    )\n    .join(OrderItem, Order.id == OrderItem.order_id)\n    .group_by(Order.customer_id)\n    .all()\n)\n```\n\nFor a customer with 2 orders, each with 3 items, the `order_count` shows 6 instead of 2.",
        r'''<think>
This is the Cartesian product / fan-out problem with JOINs and aggregates.

Let me trace with concrete data.

**Orders table:**
| id | customer_id |
|----|------------|
| 1  | 100        |
| 2  | 100        |

**OrderItems table:**
| id | order_id | price | quantity |
|----|----------|-------|----------|
| 1  | 1        | 10.00 | 2        |
| 2  | 1        | 5.00  | 1        |
| 3  | 1        | 15.00 | 1        |
| 4  | 2        | 20.00 | 1        |
| 5  | 2        | 8.00  | 3        |
| 6  | 2        | 12.00 | 1        |

After JOIN (Order × OrderItem):
| order_id | customer_id | item_id | price | quantity |
|----------|------------|---------|-------|----------|
| 1        | 100        | 1       | 10.00 | 2        |
| 1        | 100        | 2       | 5.00  | 1        |
| 1        | 100        | 3       | 15.00 | 1        |
| 2        | 100        | 4       | 20.00 | 1        |
| 2        | 100        | 5       | 8.00  | 3        |
| 2        | 100        | 6       | 12.00 | 1        |

Now GROUP BY customer_id:
- `SUM(price * quantity)` = (10×2) + (5×1) + (15×1) + (20×1) + (8×3) + (12×1) = 20 + 5 + 15 + 20 + 24 + 12 = 96
- `COUNT(order_id)` = 6 (counts each ROW, not each unique order!)

The COUNT is wrong because after the JOIN, order_id appears once per item. Order 1 appears 3 times (once per item), Order 2 appears 3 times. COUNT counts rows, not unique values.

The SUM of revenue is actually CORRECT in this case — each item appears exactly once in the join result. The problem is specifically with COUNT.

But the user also mentioned "totals are inflated." That would happen if there were MULTIPLE joins creating a Cartesian product. Let me re-read...

Actually, the totals would be inflated if there were another join in play (e.g., joining order_discounts too). With just one join (order → items), the item prices appear once each, so SUM is correct. But COUNT(Order.id) is definitely wrong — it should be COUNT(DISTINCT Order.id).

**Fixes:**
1. `COUNT(DISTINCT Order.id)` for accurate order count
2. Or use subqueries to aggregate at different levels
</think>

**JOIN fan-out inflates COUNT.** After joining orders with items, each order appears once per item. `COUNT(Order.id)` counts rows (6), not unique orders (2).

```
After JOIN, customer 100 has:
Order 1 × Item 1    ← Order 1 counted
Order 1 × Item 2    ← Order 1 counted AGAIN
Order 1 × Item 3    ← Order 1 counted AGAIN
Order 2 × Item 4    ← Order 2 counted
Order 2 × Item 5    ← Order 2 counted AGAIN
Order 2 × Item 6    ← Order 2 counted AGAIN

COUNT(Order.id) = 6  (wrong — should be 2)
```

### Fix: COUNT(DISTINCT)

```python
results = (
    db.session.query(
        Order.customer_id,
        func.sum(OrderItem.price * OrderItem.quantity).label('total_revenue'),
        func.count(func.distinct(Order.id)).label('order_count'),  # DISTINCT!
    )
    .join(OrderItem, Order.id == OrderItem.order_id)
    .group_by(Order.customer_id)
    .all()
)
```

### When fan-out DOES inflate SUM

If you join MULTIPLE one-to-many relations, SUM gets inflated too:

```python
# BROKEN: if order has 3 items AND 2 discounts, each item appears 2x
query.join(OrderItem).join(OrderDiscount)
# Item prices are summed 2x because of the Cartesian product

# FIX: use subqueries or aggregate separately
revenue_subq = (
    db.session.query(
        OrderItem.order_id,
        func.sum(OrderItem.price * OrderItem.quantity).label('revenue')
    )
    .group_by(OrderItem.order_id)
    .subquery()
)
```

**The rule:** when you JOIN a one-to-many relation, every aggregate on the "one" side gets inflated by the "many" side's fan-out. Use `DISTINCT` for COUNT, and subqueries for SUM when multiple one-to-many joins are involved.'''
    ),
    (
        "thinking/debug-signal-handling-partial-write",
        "Our data export script sometimes produces truncated CSV files. The file ends mid-line. Users Ctrl+C to cancel long exports:\n\n```python\nimport csv\nimport signal\n\ndef export_data(query_results, output_path):\n    with open(output_path, 'w', newline='') as f:\n        writer = csv.writer(f)\n        writer.writerow(['id', 'name', 'email', 'created_at'])\n        for row in query_results:\n            writer.writerow([row.id, row.name, row.email, row.created_at])\n    print(f'Exported to {output_path}')\n```",
        r'''<think>
When the user presses Ctrl+C, Python raises `KeyboardInterrupt`. This can happen at ANY point during execution — including in the middle of `writer.writerow()` or even during the file system's write buffer flush.

The sequence that causes truncation:

1. The script is writing rows in a loop
2. User presses Ctrl+C
3. Python raises `KeyboardInterrupt` INSIDE the `with` block
4. The `with` block's `__exit__` runs — `f.close()` is called
5. `f.close()` flushes the write buffer to disk
6. But the buffer might contain a partial line (the row that was being written when the interrupt hit)
7. The partial line gets flushed, creating a truncated CSV

Actually, there's a subtlety. `csv.writer.writerow()` writes to the file object, which has an internal buffer. The interrupt could happen:
- During the CSV formatting (before anything is written to the buffer)
- During the write to the file buffer
- During a buffer flush to the OS

In any case, the file ends up with whatever was flushed at the time of interruption.

But the bigger issue: the `with` block catches the interrupt via its context manager, closes the file properly, and then the `KeyboardInterrupt` propagates. So the file is properly closed but contains incomplete data. The user now has a corrupt CSV that looks valid (same filename, header present) but is missing rows or has a truncated last line.

**Fix options:**

1. **Write to a temp file, rename on completion** (atomic):
   ```python
   import tempfile, os
   with tempfile.NamedTemporaryFile(mode='w', dir=os.path.dirname(output_path),
                                     suffix='.tmp', delete=False) as f:
       # write all data
       pass
   os.rename(f.name, output_path)  # Atomic on same filesystem
   ```
   If interrupted, the temp file exists but the output file is either absent (first export) or still has the previous complete version.

2. **Signal handler that sets a flag**:
   ```python
   should_stop = False
   def handle_sigint(sig, frame):
       nonlocal should_stop
       should_stop = True
   ```
   Check the flag between rows. Finish the current row cleanly, then stop.

3. **Catch KeyboardInterrupt and clean up**:
   ```python
   try:
       # write loop
   except KeyboardInterrupt:
       os.remove(output_path)  # Delete incomplete file
   ```

Option 1 (temp file + rename) is the most robust because it's atomic. Even if the process is killed with SIGKILL (which can't be caught), the output file is either complete or doesn't exist.
</think>

When Ctrl+C hits mid-write, the `with` block closes the file (flushing the partial buffer), leaving a truncated CSV that looks valid but has incomplete data.

### Fix: write to temp file, atomic rename on completion

```python
import csv
import os
import tempfile

def export_data(query_results, output_path):
    output_dir = os.path.dirname(output_path) or '.'

    # Write to temp file in same directory (needed for atomic rename)
    fd, tmp_path = tempfile.mkstemp(dir=output_dir, suffix='.csv.tmp')
    try:
        with os.fdopen(fd, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'email', 'created_at'])
            for row in query_results:
                writer.writerow([row.id, row.name, row.email, row.created_at])

        # Atomic rename — only happens if ALL rows were written
        os.replace(tmp_path, output_path)
        print(f'Exported to {output_path}')
    except (KeyboardInterrupt, Exception):
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

**Why this works:** `os.replace()` is atomic on the same filesystem. Either the output file has the old complete data, or the new complete data. Never partial.

### For graceful cancellation with progress

```python
import signal

def export_data(query_results, output_path):
    cancelled = False

    def handle_cancel(sig, frame):
        nonlocal cancelled
        cancelled = True
        print('\nCancelling after current row...')

    old_handler = signal.signal(signal.SIGINT, handle_cancel)
    try:
        # ... write loop ...
        for i, row in enumerate(query_results):
            if cancelled:
                print(f'Cancelled after {i} rows')
                break
            writer.writerow([...])
    finally:
        signal.signal(signal.SIGINT, old_handler)  # Restore original handler
```'''
    ),
    (
        "thinking/debug-serialization-datetime",
        "Our API returns `TypeError: Object of type datetime is not JSON serializable` but only on some endpoints:\n\n```python\n@app.get('/api/orders/{order_id}')\nasync def get_order(order_id: int):\n    order = await db.get_order(order_id)\n    return {\n        'id': order.id,\n        'total': order.total,\n        'status': order.status,\n        'items': [{'name': i.name, 'qty': i.quantity} for i in order.items],\n        'created_at': order.created_at,  # datetime object\n        'shipped_at': order.shipped_at,  # datetime or None\n        'metadata': order.metadata,      # dict from JSONB column\n    }\n```",
        r'''<think>
`json.dumps()` (which FastAPI uses internally via JSONResponse) doesn't know how to serialize `datetime` objects. The standard JSON types are: string, number, object, array, boolean, null. `datetime` isn't one of them.

But the user says "only on some endpoints." That means some other endpoints DO return datetimes without error. Why?

Possible reasons:
1. **FastAPI's JSONResponse uses a custom encoder** that handles datetime. But if you return a plain dict, FastAPI uses `jsonable_encoder` which converts datetimes to ISO strings. Wait — if they're using `return {...}`, FastAPI SHOULD handle datetime via its response serialization.

Let me reconsider. Actually, FastAPI uses `jsonable_encoder` which calls `json.dumps` with a custom encoder that handles datetime, Decimal, etc. So if you return a dict from a FastAPI endpoint, datetimes should be auto-converted.

But what if `order.metadata` contains a datetime? The `metadata` field is from a JSONB column — it should contain only JSON-serializable types. But what if the ORM converts some values to Python objects? For example, if the JSONB contains `{"last_updated": "2026-03-05T10:00:00"}`, the ORM might parse it as a datetime string. But JSONB is stored as JSON — it shouldn't have datetime objects.

Hmm, actually the error "only on some endpoints" might be because:
- Endpoints that use Pydantic models have serialization handled by the model
- Endpoints that return raw dicts rely on `jsonable_encoder`
- `jsonable_encoder` might not deep-convert nested structures

Wait, another possibility: `order.total` is a `Decimal` (from a DECIMAL column). `Decimal` is also not JSON serializable. But `jsonable_encoder` should handle that too...

Let me reconsider. Perhaps the issue is that `order.metadata` contains Python objects that the JSONB column returned. Some ORMs (like SQLAlchemy with specific type decorators) can deserialize JSONB values into Python types. If metadata has `datetime` objects nested inside it, the top-level `jsonable_encoder` might not recursively convert them.

Actually, the simplest explanation: FastAPI's default JSON encoder handles top-level datetime fields, but might not handle datetimes NESTED inside arbitrary dicts (like `order.metadata`). If `metadata` contains something like `{'audit': {'created': datetime(2026, 3, 5)}}`, the serializer might miss it.

But the most likely real cause: the endpoint is NOT using FastAPI's response handling. If they're calling `json.dumps()` manually or using a different Response class, the custom encoder isn't applied.

Let me provide a comprehensive fix.
</think>

`json.dumps()` can't serialize `datetime` objects. FastAPI normally handles this via `jsonable_encoder`, but it can fail with nested structures or manual serialization.

### Fix 1: Use Pydantic response model (FastAPI best practice)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class OrderItem(BaseModel):
    name: str
    qty: int

class OrderResponse(BaseModel):
    id: int
    total: float
    status: str
    items: list[OrderItem]
    created_at: datetime    # Pydantic auto-converts to ISO string
    shipped_at: Optional[datetime]
    metadata: dict

@app.get('/api/orders/{order_id}', response_model=OrderResponse)
async def get_order(order_id: int):
    order = await db.get_order(order_id)
    return order  # Pydantic handles all serialization
```

### Fix 2: Custom JSON encoder for manual serialization

```python
from datetime import datetime, date
from decimal import Decimal
import json

class AppJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)

# Use everywhere:
json.dumps(data, cls=AppJSONEncoder)
```

### Fix 3: Explicit conversion in the endpoint

```python
@app.get('/api/orders/{order_id}')
async def get_order(order_id: int):
    order = await db.get_order(order_id)
    return {
        'id': order.id,
        'total': float(order.total),                           # Decimal → float
        'status': order.status,
        'items': [{'name': i.name, 'qty': i.quantity} for i in order.items],
        'created_at': order.created_at.isoformat(),            # datetime → string
        'shipped_at': order.shipped_at.isoformat() if order.shipped_at else None,
        'metadata': order.metadata,
    }
```

### Common non-serializable Python types

| Type | JSON fix |
|------|----------|
| `datetime` | `.isoformat()` |
| `Decimal` | `str()` or `float()` |
| `bytes` | `base64.b64encode().decode()` |
| `set` | `list()` |
| `UUID` | `str()` |
| `Enum` | `.value` |
| `Path` | `str()` |'''
    ),
]
