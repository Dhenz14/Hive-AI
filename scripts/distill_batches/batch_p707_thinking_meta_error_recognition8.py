"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 8)
Scenarios: Incorrect concurrency, wrong error handling patterns, under-engineering
"""

PAIRS = [
    (
        "thinking/meta-error-deadlock-lock-ordering",
        r'''I wrote this transfer function with locks to prevent race conditions:

```python
import threading

account_locks = {}

def get_lock(account_id):
    if account_id not in account_locks:
        account_locks[account_id] = threading.Lock()
    return account_locks[account_id]

def transfer(from_id, to_id, amount):
    from_lock = get_lock(from_id)
    to_lock = get_lock(to_id)

    with from_lock:
        with to_lock:
            from_balance = get_balance(from_id)
            if from_balance >= amount:
                set_balance(from_id, from_balance - amount)
                set_balance(to_id, get_balance(to_id) + amount)
                return True
            return False
```

I used locks on both accounts to prevent race conditions. Is this correct?''',
        r'''<think>
Let me analyze this concurrent code...

The function acquires locks on both accounts: first the sender, then the receiver. This prevents two transfers from modifying the same account simultaneously. Good.

BUT — what if two transfers happen simultaneously in opposite directions?

Thread A: transfer(1, 2, 50)
- Acquires lock for account 1
- Tries to acquire lock for account 2

Thread B: transfer(2, 1, 30)
- Acquires lock for account 2
- Tries to acquire lock for account 1

Thread A holds lock 1, wants lock 2.
Thread B holds lock 2, wants lock 1.
DEADLOCK! Both threads wait forever.

This is the classic dining philosophers problem. The fix is to always acquire locks in a consistent global order (e.g., by account ID):

```python
def transfer(from_id, to_id, amount):
    first_id = min(from_id, to_id)
    second_id = max(from_id, to_id)
    with get_lock(first_id):
        with get_lock(second_id):
            ...
```

By always locking the lower-numbered account first, we prevent circular wait.

There's also a race condition in `get_lock()` itself — two threads could simultaneously see `account_id not in account_locks` and create two different locks for the same account. This needs a lock protecting the lock dictionary (or use `defaultdict` with a lock).

My error: I thought about preventing data races on account balances but didn't think about lock ordering deadlocks. Locking prevents races but INTRODUCES deadlocks if not done carefully.
</think>

**This code will DEADLOCK when two transfers happen in opposite directions simultaneously.**

### The deadlock scenario
```
Thread A: transfer(1, 2, $50)     Thread B: transfer(2, 1, $30)
├── acquires lock(1) ✓             ├── acquires lock(2) ✓
├── tries lock(2) ← BLOCKED       ├── tries lock(1) ← BLOCKED
└── waiting for Thread B...        └── waiting for Thread A...
                    ↑ DEADLOCK — both wait forever ↑
```

### Fix: always acquire locks in consistent order
```python
def transfer(from_id, to_id, amount):
    # Always lock lower ID first — prevents circular wait
    first_id, second_id = sorted([from_id, to_id])

    with get_lock(first_id):
        with get_lock(second_id):
            from_balance = get_balance(from_id)
            if from_balance >= amount:
                set_balance(from_id, from_balance - amount)
                set_balance(to_id, get_balance(to_id) + amount)
                return True
            return False
```

### Second bug: race in get_lock()
```python
# Thread A: account_id not in account_locks → True
# Thread B: account_id not in account_locks → True (concurrent!)
# Thread A: creates Lock() and stores it
# Thread B: creates DIFFERENT Lock() and overwrites!
```

Fix:
```python
from collections import defaultdict

_lock_creation_lock = threading.Lock()
account_locks = {}

def get_lock(account_id):
    with _lock_creation_lock:
        if account_id not in account_locks:
            account_locks[account_id] = threading.Lock()
        return account_locks[account_id]
```

### The meta-lesson
Locks prevent data races but can introduce deadlocks — a different concurrency bug. The four conditions for deadlock: mutual exclusion, hold-and-wait, no preemption, circular wait. Breaking ANY one prevents deadlock. The easiest to break is circular wait: always acquire locks in a global consistent order.'''
    ),
    (
        "thinking/meta-error-error-handling-wrong-scope",
        r'''I wrote this data processing pipeline with error handling:

```python
def process_batch(records):
    results = []
    try:
        for record in records:
            validated = validate(record)
            transformed = transform(validated)
            enriched = enrich(transformed)
            results.append(enriched)
        return results
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        return []
```

This ensures errors are handled gracefully. Good pattern?''',
        r'''<think>
Let me analyze this error handling strategy...

The try/except wraps the ENTIRE loop. If ANY single record fails (on record 50 of 1000), the exception handler fires, logs the error, and returns an EMPTY list — discarding the 49 successfully processed records.

This is wrong on multiple levels:

1. **All-or-nothing failure**: One bad record kills the entire batch. The 999 good records are lost.

2. **Lost progress**: The 49 records already processed and added to `results` are discarded when we return `[]`.

3. **Silent data loss**: The caller gets an empty list and has no way to know that 999 records were valid. It might treat this as "no data" rather than "processing failed."

4. **No indication of which record failed**: The error message says "batch processing failed" but doesn't identify which record caused the failure, making debugging nearly impossible.

5. **Returns empty list instead of raising**: The caller can't distinguish between "no records to process" and "processing failed for all records."

The fix depends on the requirement:
- If any failure should fail the batch → let the exception propagate (remove try/except)
- If individual failures should be skipped → move try/except INSIDE the loop
- If partial results are acceptable → move try/except inside and collect errors

My error: I put the error handling boundary at the wrong scope. The try/except should be around each RECORD, not around the entire BATCH.
</think>

**The try/except is at the wrong scope — one bad record discards ALL results, even successfully processed ones.**

### The problem
```python
# Record 1-49: processed successfully, added to results
# Record 50: fails with ValueError
# Result: return [] — all 49 good records DISCARDED!
```

### Fix: error handling per record
```python
def process_batch(records):
    results = []
    errors = []
    for i, record in enumerate(records):
        try:
            validated = validate(record)
            transformed = transform(validated)
            enriched = enrich(transformed)
            results.append(enriched)
        except Exception as e:
            logger.warning(f"Record {i} failed: {e}", exc_info=True)
            errors.append({"index": i, "record": record, "error": str(e)})

    if errors:
        logger.error(f"Batch completed with {len(errors)}/{len(records)} failures")

    return {"results": results, "errors": errors}
```

### When to use each scope

| Scope | Use when |
|-------|----------|
| Per-record try/except | Partial results are acceptable (most batch processing) |
| Per-batch try/except | All-or-nothing required (financial transactions) |
| No try/except | Caller should handle errors (library code) |

### The meta-lesson
Error handling scope determines failure granularity. A try/except around a loop means "if anything fails, everything fails." A try/except inside a loop means "failures are isolated per iteration." Always match the error handling scope to the business requirement. For batch processing, per-item error handling is almost always correct.'''
    ),
    (
        "thinking/meta-error-under-engineered-config",
        r'''I wrote this configuration loader:

```python
import os

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "myapp")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
API_KEY = os.environ.get("API_KEY", "dev-key-12345")
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
MAX_CONNECTIONS = int(os.environ.get("MAX_CONNECTIONS", "10"))
```

Simple and clean config. Any issues?''',
        r'''<think>
Let me examine this configuration approach...

Several issues:

1. **Default values for secrets**: `DB_PASSWORD = "password"` and `API_KEY = "dev-key-12345"`. If the environment variable is not set in production, the app silently uses the default password. This is a security disaster — the app starts and appears to work, but uses a known default password.

2. **No validation at startup**: `DB_PORT = int(os.environ.get("DB_PORT", "5432"))` — if someone sets `DB_PORT=abc`, this crashes with a ValueError. But NOT at startup — it crashes when this module is imported, which might be during a request, making the error confusing.

3. **`int()` can crash**: If `MAX_CONNECTIONS=ten`, the `int()` call raises ValueError with an unhelpful traceback pointing to the config line.

4. **DEBUG defaults to True**: In production, if `DEBUG` env var is unset, debug mode is ON. This should default to `False` — safe by default.

5. **No required vs optional distinction**: Which env vars MUST be set in production? All have defaults, so the app starts even if none are configured. There's no way to know if you forgot to set `DB_HOST`.

6. **Module-level execution**: Config is evaluated at import time. You can't test with different configs without mocking `os.environ` before import.

7. **Secrets in defaults**: The default API key and password could end up in source control, logs, or error messages.

My error: I made configuration "simple" by giving everything a default, but this means the app will happily start in production with development defaults, including known passwords and debug mode enabled.
</think>

**This config is dangerous because it silently falls back to insecure defaults in production.**

### Critical issues

**1. Secrets have default values:**
```python
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")  # known password in prod!
API_KEY = os.environ.get("API_KEY", "dev-key-12345")     # known key in prod!
```
If the env var isn't set in production, the app starts with known credentials.

**2. DEBUG defaults to True:**
```python
DEBUG = os.environ.get("DEBUG", "true")  # debug mode in production!
```
Secure default should be `False`.

**3. No validation — crashes at random times:**
```python
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
# If DB_PORT="abc", crashes at import time with unclear error
```

### Fixed version
```python
import os
import sys

class ConfigError(Exception):
    pass

def require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ConfigError(f"Required environment variable {key} is not set")
    return value

def env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, str(default))
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{key}={raw!r} is not a valid integer")

# Required in all environments — no defaults
DB_HOST = require_env("DB_HOST")
DB_PASSWORD = require_env("DB_PASSWORD")
API_KEY = require_env("API_KEY")

# Optional with safe defaults
DB_PORT = env_int("DB_PORT", 5432)
DB_NAME = os.environ.get("DB_NAME", "myapp")
DB_USER = os.environ.get("DB_USER", "postgres")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
MAX_CONNECTIONS = env_int("MAX_CONNECTIONS", 10)
```

### The principle
| Config type | Should have default? |
|-------------|---------------------|
| Secrets (passwords, API keys) | NEVER — require explicitly |
| Safety flags (DEBUG) | Default to SAFE (False) |
| Connection params (host, port) | Depend on environment |
| Tuning params (pool size) | Safe defaults OK |

### The meta-lesson
Configuration should fail loudly at startup when required values are missing, not silently use insecure defaults that appear to work. "Simple" config that always starts is actually dangerous config that hides misconfiguration until it causes a security incident.'''
    ),
    (
        "thinking/meta-error-concurrent-dict-not-threadsafe",
        r'''I'm using a Python dictionary as an in-memory cache shared between threads:

```python
import threading

cache = {}

def get_user(user_id):
    if user_id in cache:
        return cache[user_id]

    user = db.query(User).get(user_id)
    cache[user_id] = user
    return user

# Multiple threads call get_user() concurrently
```

Python dicts are thread-safe because of the GIL, right? So this should be fine?''',
        r'''<think>
Let me think about this carefully...

Python's GIL ensures that only one thread executes Python bytecode at a time. Individual dict operations like `d[key] = value` or `key in d` are atomic in CPython because they execute in a single bytecode instruction.

So `cache[user_id] = user` is atomic. And `user_id in cache` is atomic. Each individual operation is safe.

BUT — the combination of `if user_id in cache` followed by `cache[user_id]` is NOT atomic as a unit! Between the `in` check and the access, another thread could modify the dict.

Wait actually, in this specific code, the race condition doesn't cause a crash or incorrect result. Let me think more carefully:

Thread A: `if user_id in cache` → True (user was cached)
Thread B: `del cache[user_id]` (cache invalidation from another part of code)
Thread A: `return cache[user_id]` → KeyError! (it was just deleted)

OK that's a problem if cache invalidation exists. But even without deletion, there's a redundant work issue:

Thread A: `if 42 in cache` → False
Thread B: `if 42 in cache` → False (concurrent)
Thread A: `user = db.query(...)` → queries DB
Thread B: `user = db.query(...)` → ALSO queries DB (redundant!)
Thread A: `cache[42] = user`
Thread B: `cache[42] = user` (overwrites with same value — no harm, but wasted DB call)

So it's not catastrophically broken, but it IS a race condition that causes:
1. Redundant database queries (thundering herd)
2. KeyError if cache entries are ever deleted
3. No size limit — cache grows forever (memory leak)

The bigger issue is that "GIL makes dicts thread-safe" is a dangerous oversimplification. The GIL makes individual operations atomic, not sequences of operations.

Also, this only applies to CPython. PyPy, Jython, and IronPython don't have the GIL, so even individual dict operations might not be safe.
</think>

**Individual dict operations are atomic under CPython's GIL, but the check-then-act pattern (`if key in dict` then `dict[key]`) is NOT atomic as a unit.**

### The race conditions

**1. Thundering herd (redundant queries):**
```
Thread A: 42 in cache → False
Thread B: 42 in cache → False (concurrent)
Thread A: db.query(42) → starts DB query
Thread B: db.query(42) → ALSO starts DB query (redundant!)
Thread A: cache[42] = user_a
Thread B: cache[42] = user_b  (overwrites, wasted work)
```

**2. KeyError if cache invalidation exists:**
```
Thread A: 42 in cache → True
Thread C: del cache[42]  (invalidation!)
Thread A: cache[42] → KeyError!
```

**3. Unbounded growth:**
No `maxsize` — cache grows forever as new users are queried. Eventual OOM.

### Fix: use proper caching
```python
from functools import lru_cache
from threading import Lock

# Option 1: lru_cache (thread-safe, bounded)
@lru_cache(maxsize=1000)
def get_user(user_id):
    return db.query(User).get(user_id)

# Option 2: Manual with lock (prevents thundering herd)
_cache = {}
_cache_lock = Lock()

def get_user(user_id):
    with _cache_lock:
        if user_id in _cache:
            return _cache[user_id]

    # Query outside lock to avoid holding lock during I/O
    user = db.query(User).get(user_id)

    with _cache_lock:
        _cache[user_id] = user
    return user
```

### What the GIL actually guarantees
| Operation | GIL-safe? |
|-----------|-----------|
| `d[key] = value` | Yes (single bytecode) |
| `key in d` | Yes (single bytecode) |
| `if key in d: return d[key]` | NO (two operations) |
| `d[key] += 1` | NO (read + modify + write) |

### The meta-lesson
"Thread-safe" means different things at different granularities. The GIL makes individual dict operations atomic, but compound operations (check-then-act, read-modify-write) still need explicit synchronization. And relying on CPython's GIL makes your code non-portable to other Python implementations.'''
    ),
    (
        "thinking/meta-error-under-eng-missing-unicode",
        r'''I wrote this username validation:

```python
def validate_username(username: str) -> bool:
    if len(username) < 3 or len(username) > 20:
        return False
    if not username[0].isalpha():
        return False
    return all(c.isalnum() or c == '_' for c in username)
```

Simple and clean. Does it handle all cases?''',
        r'''<think>
Let me think about what this validation allows...

Rules enforced:
- Length 3-20 characters
- Must start with a letter
- Only alphanumeric and underscore

What it misses:

1. **Unicode characters**: `isalpha()` and `isalnum()` accept Unicode! So `José`, `Müller`, `有名`, `Кирилл` all pass validation. Is that intentional?
   - `"有名人".isalpha()` → True
   - `"Müller".isalnum()` → True

   If usernames are used in URLs (`/users/José`), this could cause encoding issues. If they're used in file paths, certain Unicode characters could be problematic.

2. **Homoglyph attacks**: Unicode allows characters that look identical to ASCII:
   - `аdmin` (first 'a' is Cyrillic а, U+0430) looks like `admin` but is a different username
   - An attacker registers `аdmin` and impersonates the admin

3. **`len()` counts code points, not display width**: Some Unicode characters are zero-width or combining characters:
   - `len("a\u0300")` → 2 (letter + combining accent, displays as one character "à")
   - `len("a\u200b")` → 2 (letter + zero-width space, displays as "a")

4. **Reserved names**: `admin`, `root`, `system`, `api`, `null`, `undefined` — should probably be blocked.

5. **Case sensitivity**: Is `Admin` different from `admin`? If not, you need case-insensitive uniqueness checking (and beware of Unicode case folding: `ß` uppercases to `SS`).

If the intent is ASCII-only usernames (safest), the fix is to use `string.ascii_letters` and `string.digits` instead of `isalpha()`/`isalnum()`.
</think>

**`isalpha()` and `isalnum()` accept ALL Unicode, including characters that enable homoglyph attacks and encoding issues.**

### The problem
```python
# These all pass validation:
validate_username("有名人")       # Chinese characters
validate_username("Кирилл")      # Cyrillic
validate_username("аdmin")       # Cyrillic 'а' — looks like "admin"!
validate_username("a\u200bbc")   # Zero-width space hidden inside
```

### Homoglyph attack
```python
# Attacker registers this username:
"аdmin"  # Cyrillic 'а' (U+0430), not Latin 'a' (U+0061)
# Looks IDENTICAL to "admin" in most fonts
# Now attacker has a profile at /users/аdmin that looks like /users/admin
```

### Fixed version (ASCII-only, safe)
```python
import re

RESERVED = {'admin', 'root', 'system', 'api', 'null', 'undefined', 'me', 'settings'}

def validate_username(username: str) -> bool:
    if len(username) < 3 or len(username) > 20:
        return False
    # ASCII-only: letters, digits, underscore
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
        return False
    if username.lower() in RESERVED:
        return False
    return True
```

### If you WANT to support Unicode usernames
```python
import unicodedata

def validate_username(username: str) -> bool:
    # Normalize Unicode (NFC) to prevent duplicate representations
    username = unicodedata.normalize('NFC', username)
    if len(username) < 3 or len(username) > 20:
        return False
    # Block mixed scripts (anti-homoglyph)
    scripts = {unicodedata.script(c) for c in username if c != '_'}
    scripts.discard('Common')
    if len(scripts) > 1:
        return False  # mixed scripts like Latin + Cyrillic
    return all(c.isalnum() or c == '_' for c in username)
```

### The meta-lesson
Python's `isalpha()` and `isalnum()` operate on Unicode by default, not ASCII. This is a common assumption error — developers think "letters" means a-z, but Python means ALL Unicode letters. For security-sensitive string validation (usernames, identifiers, URLs), explicitly constrain to the character set you actually want.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
