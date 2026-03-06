"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 7)
Scenarios: Logic errors, wrong abstractions, incorrect library assumptions
"""

PAIRS = [
    (
        "thinking/meta-error-logic-pagination-off-by-one",
        r'''I wrote this pagination logic:

```python
def paginate(items, page, per_page=20):
    start = page * per_page
    end = start + per_page
    total_pages = len(items) // per_page
    return {
        "data": items[start:end],
        "page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages
    }
```

Testing with 50 items:
- paginate(items, 0) → items 0-19 ✓
- paginate(items, 1) → items 20-39 ✓
- paginate(items, 2) → items 40-49 ✓

Looks correct. Is it?''',
        r'''<think>
Let me trace through this more carefully...

50 items, per_page=20.
`total_pages = 50 // 20 = 2`

Page 0: start=0, end=20 → items[0:20] → 20 items ✓
Page 1: start=20, end=40 → items[20:40] → 20 items ✓
Page 2: start=40, end=60 → items[40:50] → 10 items ✓ (Python slicing handles out of bounds)

But `total_pages = 2` and `has_next = page < total_pages`:
- Page 0: has_next = 0 < 2 = True ✓
- Page 1: has_next = 1 < 2 = True ✓
- Page 2: has_next = 2 < 2 = False ✓

Seems fine with 50 items. But let me try 40 items:

`total_pages = 40 // 20 = 2`

Page 0: start=0, end=20 → 20 items ✓
Page 1: start=20, end=40 → 20 items ✓
Page 2: start=40, end=60 → items[40:60] → [] (empty!)

But `total_pages = 2` and `has_next` on page 1 = `1 < 2 = True`. So the UI shows a "Next" button on page 1, but page 2 is empty!

The bug: `total_pages = len(items) // per_page` uses integer division. For 40 items with 20 per page, that's 2, which means pages 0 and 1. But `has_next = page < total_pages` says page 1 has a next page (page 2), which is empty.

Wait, actually the issue is more subtle. There are exactly 2 pages of data (pages 0 and 1). `total_pages = 2` is correct. But `has_next = page < total_pages` means page 1 has `1 < 2 = True`, which is WRONG — page 1 is the last page.

The condition should be `has_next = page < total_pages - 1`.

But wait, there's ANOTHER bug with non-even division. 50 items / 20 per page:
`total_pages = 50 // 20 = 2` — but there are actually 3 pages! Pages 0, 1, and 2. The 10 remaining items on page 2 are lost from the page count.

The fix: `total_pages = math.ceil(len(items) / per_page)` or equivalently `(len(items) + per_page - 1) // per_page`.

With the fix: 50 items → total_pages = 3, 40 items → total_pages = 2.
And has_next: `page < total_pages - 1` (0-indexed) or `page < total_pages` if pages are 1-indexed.

There are actually TWO bugs compounding:
1. Integer division truncates total_pages
2. has_next boundary is off by one
</think>

**There are two compounding bugs: integer division truncates total_pages, and has_next is off by one.**

### Bug 1: Wrong total_pages
```python
# 50 items, 20 per page:
total_pages = 50 // 20  # = 2, but there are 3 pages (0,1,2)!

# 41 items, 20 per page:
total_pages = 41 // 20  # = 2, but there are 3 pages!
```

Integer division drops the remainder page. 10 items on the last page are "invisible" in the page count.

### Bug 2: has_next is off by one
```python
# 40 items, 20 per page:
total_pages = 40 // 20  # = 2 (happens to be correct here)
# Page 1: has_next = 1 < 2 = True — but page 2 would be EMPTY!
```

With 0-indexed pages, the last valid page is `total_pages - 1`, so `has_next` should check `page < total_pages - 1`.

### These bugs compound
With 50 items: total_pages=2 (wrong, should be 3) + has_next on page 1 says True (correct by accident). But page 2 has no "Next" even though... wait, the user never discovers page 2 exists because total_pages says 2.

### Fixed version
```python
import math

def paginate(items, page, per_page=20):
    total_pages = math.ceil(len(items) / per_page) if items else 0
    start = page * per_page
    end = start + per_page
    return {
        "data": items[start:end],
        "page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages - 1,
        "has_prev": page > 0,
    }
```

### Edge cases to test
```python
paginate([], 0)        # total_pages=0, data=[], has_next=False
paginate([1], 0)       # total_pages=1, data=[1], has_next=False
paginate(range(20), 0) # total_pages=1, data=[0..19], has_next=False
paginate(range(21), 0) # total_pages=2, data=[0..19], has_next=True
```

### The meta-lesson
Pagination bugs are almost always off-by-one errors at boundaries: exactly-divisible counts, empty collections, and last-page detection. Always test with: 0 items, exactly per_page items, per_page+1 items, and 2*per_page items.'''
    ),
    (
        "thinking/meta-error-wrong-abstraction-god-class",
        r'''I designed this utility class to handle common operations:

```python
class Utils:
    @staticmethod
    def format_date(date, fmt="%Y-%m-%d"):
        return date.strftime(fmt)

    @staticmethod
    def hash_password(password):
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

    @staticmethod
    def send_email(to, subject, body):
        import smtplib
        # ... send email logic ...

    @staticmethod
    def validate_email(email):
        return "@" in email and "." in email

    @staticmethod
    def generate_thumbnail(image_path, size=(128, 128)):
        from PIL import Image
        img = Image.open(image_path)
        img.thumbnail(size)
        return img

    @staticmethod
    def calculate_tax(amount, rate=0.08):
        return round(amount * rate, 2)

    @staticmethod
    def sanitize_html(text):
        import bleach
        return bleach.clean(text)

    @staticmethod
    def parse_csv(filepath):
        import csv
        with open(filepath) as f:
            return list(csv.DictReader(f))
```

This keeps all utility functions organized in one place. Good pattern?''',
        r'''<think>
Let me evaluate this design...

This `Utils` class contains: date formatting, password hashing, email sending, email validation, image processing, tax calculation, HTML sanitization, and CSV parsing.

These have NOTHING in common. The class is just a namespace for unrelated functions. This is a "God class" or "junk drawer" antipattern.

Problems:

1. **No cohesion**: What do password hashing and image thumbnails have in common? Nothing. The class violates the Single Responsibility Principle — it has 8 completely unrelated responsibilities.

2. **Import bloat**: If I need `format_date`, I also import PIL, bcrypt, bleach, smtplib, and csv. In some environments, `PIL` or `bcrypt` might not be installed, so even importing `Utils` for a date format would fail.

3. **Testing difficulty**: To test `format_date`, I need to have bcrypt, PIL, and bleach installed (they're imported in the same class, even if lazily).

4. **Discovery problem**: When a new developer needs to hash a password, will they look in `Utils`? Will they look in `auth`? Will they grep the codebase? A class named `Utils` gives no hint about its contents.

5. **Growth**: Everyone adds their random functions here. It becomes 500+ lines of unrelated code. No one refactors it because everything depends on it.

6. **All static methods**: A class with only static methods is just a module cosplaying as a class. Python modules already provide namespacing — that's literally what they're for.

The right abstraction: separate modules by domain.
- `auth.py` → password hashing, token generation
- `email.py` → sending/validating emails
- `dates.py` → date formatting
- `media.py` → image processing
- `finance.py` → tax calculations

Or just use plain functions in appropriately named modules.

My error: I confused "organized" with "grouped." Putting unrelated things in one class isn't organization — it's a junk drawer. Organization means grouping by COHESION (things that change together, serve the same purpose).
</think>

**This is a "God class" / "junk drawer" antipattern. A class with only static methods containing unrelated functionality is just a module pretending to be a class.**

### The problems

**1. No cohesion — what changes together?**
If you update the tax rate, you're editing the same file as image thumbnails. If bcrypt updates its API, you're touching the same class as CSV parsing.

**2. Import side effects:**
```python
from utils import Utils  # Need format_date
# But now PIL, bcrypt, bleach must all be installed!
# (Even with lazy imports, the class couples everything)
```

**3. Discovery is impossible:**
```python
Utils.hash_password(...)       # Why would I look in "Utils"?
Utils.generate_thumbnail(...)  # This belongs in an image module
Utils.calculate_tax(...)       # This belongs in a finance module
```

**4. It only grows, never shrinks:**
Month 1: 8 methods. Month 6: 40 methods. Month 12: 150 methods. Everyone adds here because it's the "misc" drawer.

### The fix: domain-specific modules
```
project/
├── auth.py          → hash_password, verify_password
├── email.py         → send_email, validate_email
├── formatting.py    → format_date, format_currency
├── media.py         → generate_thumbnail, resize_image
├── finance.py       → calculate_tax, calculate_discount
├── sanitization.py  → sanitize_html, escape_sql
└── data_import.py   → parse_csv, parse_json
```

Each module has:
- **Cohesion**: related functions that change for the same reasons
- **Independent imports**: `from auth import hash_password` doesn't require PIL
- **Discoverability**: need password hashing? Check `auth.py`

### Why "all static methods" is a code smell
```python
# This class IS a module. Python already has modules.
class Utils:
    @staticmethod
    def foo(): ...

# Just use a module:
# utils/auth.py
def hash_password(password): ...
```

### The meta-lesson
A class should represent a cohesive concept — something where all methods relate to the same data or responsibility. If your class is just a bag of unrelated functions, it's not a class — it's a module. And if it's a module, make it an actual Python module with a descriptive name, not `utils.py`.'''
    ),
    (
        "thinking/meta-error-assuming-json-parse-safe",
        r'''I wrote this API endpoint that accepts JSON configuration:

```python
import json

@app.post("/api/config")
def update_config(request):
    config = json.loads(request.body)
    # Apply configuration
    app.settings.update(config)
    return {"status": "updated"}
```

I'm using json.loads so it's safe from injection, right? JSON doesn't have code execution like eval().''',
        r'''<think>
Let me think about whether json.loads is truly safe here...

`json.loads` itself is safe — it parses JSON and doesn't execute code. Unlike `eval()` or `yaml.load()` (without SafeLoader), it can't run arbitrary Python. So the parsing step is fine.

BUT the parsed result is then passed directly to `app.settings.update(config)`. This is the real vulnerability. The parsed JSON could contain:

1. **Arbitrary key overwriting**: A malicious user sends:
```json
{"debug": true, "secret_key": "attacker-controlled", "database_url": "postgres://attacker.com/steal"}
```
Now they've overwritten the app's secret key and database connection.

2. **Prototype pollution equivalent**: If `app.settings` has special keys that control behavior (like `ALLOWED_HOSTS`, `CORS_ORIGINS`, `ADMIN_EMAIL`), an attacker can set them to anything.

3. **Type confusion**: JSON can contain nested objects, arrays, numbers, booleans. If the app expects `config["max_retries"]` to be an int but the attacker sends a deeply nested object, downstream code might crash or behave unexpectedly.

4. **DoS via large payload**: `json.loads` will happily parse a 100MB JSON string, consuming all server memory. No size limit is checked.

5. **JSON bomb**: Deeply nested structure `[[[[[[...]]]]]]` can cause stack overflow or excessive memory use during parsing.

The error: I assumed "safe from injection" means "safe from all attacks." JSON parsing is safe (no code execution), but blindly trusting parsed data and merging it into application settings is a completely different vulnerability class — authorization/validation, not injection.

The fix: whitelist allowed configuration keys, validate types and ranges, require authentication and authorization.
</think>

**`json.loads` is safe from code execution, but blindly applying parsed JSON to application settings is a different vulnerability entirely.**

### The real vulnerability
```python
# Attacker sends:
{
    "SECRET_KEY": "attacker-controlled-key",
    "DEBUG": true,
    "DATABASE_URL": "postgres://evil.com/exfiltrate",
    "ALLOWED_HOSTS": ["*"],
    "ADMIN_EMAIL": "attacker@evil.com"
}

# Your code does:
app.settings.update(config)  # Overwrites ALL settings!
```

The attacker can overwrite any application setting without restriction.

### What json.loads DOES protect against
```python
json.loads('__import__("os").system("rm -rf /")')  # JSONDecodeError
# Unlike eval(), json.loads cannot execute code. This IS safe.
```

### What json.loads does NOT protect against
- **Arbitrary data injection**: parsed values can be anything the attacker wants
- **Type confusion**: expected int, got nested object
- **Memory exhaustion**: 100MB JSON string, billion-element array
- **Key overwriting**: any key name the attacker chooses

### The fix: whitelist, validate, authorize
```python
from pydantic import BaseModel, validator

class ConfigUpdate(BaseModel):
    max_retries: int = None
    log_level: str = None
    feature_flags: dict = None

    @validator('max_retries')
    def validate_retries(cls, v):
        if v is not None and not (1 <= v <= 10):
            raise ValueError('max_retries must be 1-10')
        return v

    @validator('log_level')
    def validate_log_level(cls, v):
        if v is not None and v not in ('DEBUG', 'INFO', 'WARNING', 'ERROR'):
            raise ValueError('invalid log level')
        return v

@app.post("/api/config")
@require_admin  # Authorization!
def update_config(request):
    config = ConfigUpdate.parse_raw(request.body)
    # Only whitelisted keys with validated values are applied
    app.settings.update(config.dict(exclude_none=True))
    return {"status": "updated"}
```

### The meta-lesson
"Safe from injection" and "safe" are different things. `json.loads` prevents code execution (injection safety), but the PARSED DATA still needs validation, authorization, and whitelisting. Security is layered: safe parsing + safe handling + safe authorization. One safe layer doesn't make the others unnecessary.'''
    ),
    (
        "thinking/meta-error-logic-binary-search-bounds",
        r'''I implemented binary search to find a target in a sorted array:

```python
def binary_search(arr, target):
    left = 0
    right = len(arr)
    while left < right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
```

I tested with [1,3,5,7,9] and searching for 5 returned index 2. Correct?''',
        r'''<think>
Let me trace through this carefully with different inputs...

Array: [1, 3, 5, 7, 9], target = 5.
left=0, right=5 (len(arr)).

Iteration 1: mid = (0+5)//2 = 2. arr[2] = 5 == 5 → return 2. ✓

That test passes, but let me try target = 9:

left=0, right=5.
Iteration 1: mid=2. arr[2]=5 < 9 → left=3.
Iteration 2: left=3, right=5. mid=4. arr[4]=9 == 9 → return 4. ✓

Target = 1:
left=0, right=5.
Iteration 1: mid=2. arr[2]=5 > 1 → right = 2-1 = 1.
Iteration 2: left=0, right=1. mid=0. arr[0]=1 == 1 → return 0. ✓

Target = 7:
left=0, right=5.
Iteration 1: mid=2. arr[2]=5 < 7 → left=3.
Iteration 2: left=3, right=5. mid=4. arr[4]=9 > 7 → right = 4-1 = 3.
Iteration 3: left=3, right=3. 3 < 3 is False → exit loop. return -1.

WRONG! 7 is at index 3 but the search returns -1!

What happened? The issue is mixing TWO different binary search conventions:
- `right = len(arr)` → exclusive upper bound (half-open interval [left, right))
- `right = mid - 1` → inclusive upper bound update

With exclusive upper bound (right = len(arr)):
- Loop condition: `while left < right` ✓
- Right update should be: `right = mid` (not `mid - 1`)

With inclusive upper bound (right = len(arr) - 1):
- Loop condition: `while left <= right`
- Right update: `right = mid - 1` ✓

The code mixes conventions: it initializes with exclusive right but updates with inclusive logic. This causes elements to be skipped.

Let me verify: with the fix `right = mid` instead of `right = mid - 1`:
Target = 7: left=0, right=5. mid=2. 5<7 → left=3. mid=4. 9>7 → right=4. mid=3. arr[3]=7. ✓
</think>

**The binary search mixes two incompatible conventions, causing it to miss some elements.**

### The bug
```python
right = len(arr)     # exclusive upper bound (half-open [left, right))
right = mid - 1      # inclusive upper bound update
```

These are from two different binary search styles mixed together.

### Proof it fails
```python
binary_search([1, 3, 5, 7, 9], 7)  # Returns -1, should return 3!
```

Trace: left=0, right=5 → mid=2 (5<7) → left=3 → mid=4 (9>7) → right=3 → left=3, right=3, loop exits (3<3 is False). **Missed index 3!**

### Fix option 1: Exclusive upper bound (half-open interval)
```python
def binary_search(arr, target):
    left = 0
    right = len(arr)          # exclusive
    while left < right:       # half-open interval [left, right)
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid       # NOT mid - 1 (exclusive convention)
    return -1
```

### Fix option 2: Inclusive upper bound (closed interval)
```python
def binary_search(arr, target):
    left = 0
    right = len(arr) - 1      # inclusive
    while left <= right:       # closed interval [left, right]
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1   # inclusive convention
    return -1
```

### The meta-lesson
Binary search has exactly two correct patterns (half-open or closed interval), and mixing elements from both creates subtle bugs that pass most tests but fail on specific inputs. The initialization, loop condition, and update rule must all be consistent:

| Convention | Init right | Loop condition | Right update |
|-----------|-----------|----------------|--------------|
| Half-open [l, r) | `len(arr)` | `l < r` | `r = mid` |
| Closed [l, r] | `len(arr)-1` | `l <= r` | `r = mid-1` |

Pick one and be consistent. This is why `bisect` module exists — use it instead of writing binary search from scratch.'''
    ),
    (
        "thinking/meta-error-incorrect-async-assumption",
        r'''I converted my synchronous Flask endpoint to async because I heard async is faster:

```python
from flask import Flask
import asyncio
import aiohttp

app = Flask(__name__)

@app.route('/api/data')
async def get_data():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.example.com/data') as resp:
            data = await resp.json()
    return {"data": data}
```

I converted to async but it's actually SLOWER now. What went wrong?''',
        r'''<think>
Let me think about this...

Flask is a WSGI framework. WSGI is synchronous — it processes one request per thread. Flask added some async support in version 2.0, but it's limited.

When Flask encounters an async view function, it runs it using `asyncio.run()` in a new event loop for EACH request. This means:
1. A new event loop is created per request (overhead)
2. The event loop is destroyed after the request completes
3. There's no persistent event loop shared across requests
4. Each request still blocks a thread — the async doesn't give you concurrency across requests

So `async with aiohttp.ClientSession()` creates a new session AND a new event loop per request. The overhead of creating/destroying the event loop + session is MORE than just using `requests.get()` synchronously.

The performance benefit of async comes from handling MANY concurrent I/O operations on a SINGLE event loop. But Flask creates a new event loop per request, so you get zero concurrency benefit.

For async to actually help, you need:
1. An ASGI framework (FastAPI, Starlette, Quart)
2. An async server (uvicorn, hypercorn)
3. A persistent event loop that handles ALL requests

My error: I assumed "async keyword = async performance." But async is a concurrency model, not a speed boost. It only helps when you can multiplex many I/O operations on one event loop. Flask's WSGI model doesn't support that.

The fix is either:
- Use `requests` (synchronous) with Flask — simpler and faster for this case
- Switch to FastAPI + uvicorn for true async
</think>

**Flask runs each async view in a NEW event loop per request, negating all async benefits and adding overhead.**

### Why it's slower
```python
# What Flask does internally for async views:
def handle_request():
    loop = asyncio.new_event_loop()    # overhead: create event loop
    result = loop.run_until_complete(  # blocks the thread anyway!
        get_data()
    )
    loop.close()                       # overhead: destroy event loop
    return result
```

Each request creates and destroys an event loop. The thread is still blocked waiting for the response. You get the overhead of async with none of the benefits.

### The fix: either stay sync or go fully async

**Option 1: Stay synchronous (simplest, faster for Flask)**
```python
import requests

@app.route('/api/data')
def get_data():
    resp = requests.get('https://api.example.com/data')
    return {"data": resp.json()}
```

**Option 2: Use a real async framework**
```python
from fastapi import FastAPI
import aiohttp

app = FastAPI()

@app.get('/api/data')
async def get_data():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.example.com/data') as resp:
            data = await resp.json()
    return {"data": data}

# Run with: uvicorn app:app (ASGI server with persistent event loop)
```

### When async actually helps
| Scenario | Sync Flask | Async FastAPI |
|----------|-----------|---------------|
| 1 API call per request | Same speed | Same speed |
| 5 parallel API calls per request | Sequential (slow) | Concurrent (fast) |
| 1000 concurrent connections | 1000 threads (heavy) | 1 event loop (light) |
| CPU-heavy computation | Fine | No benefit |

### The meta-lesson
`async` is not a performance optimization — it's a concurrency model. It only helps when you have many concurrent I/O operations that can be multiplexed. Adding `async` to a synchronous framework doesn't make it async — you need the entire stack (framework, server, event loop) to be async. Always understand what your framework actually does with async views before converting.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
