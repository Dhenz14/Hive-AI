"""Phase 1A: Foundation Thinking — Systematic Debugging (Part 4/4)
Environment issues, dependency conflicts, logging anti-patterns, edge cases."""

PAIRS = [
    (
        "thinking/debug-circular-import-init-order",
        "Our Flask app crashes on startup with `ImportError: cannot import name 'db' from partially initialized module 'app.extensions'`. The project structure:\n\n```python\n# app/__init__.py\nfrom flask import Flask\nfrom app.extensions import db\nfrom app.models import User  # Crashes here\n\ndef create_app():\n    app = Flask(__name__)\n    db.init_app(app)\n    return app\n\n# app/extensions.py\nfrom flask_sqlalchemy import SQLAlchemy\ndb = SQLAlchemy()\n\n# app/models.py\nfrom app.extensions import db\n\nclass User(db.Model):\n    id = db.Column(db.Integer, primary_key=True)\n    name = db.Column(db.String(100))\n```\n\nEach file individually looks correct. Why does it crash?",
        r'''<think>
Let me trace the import chain step by step.

**Python imports are executed top-to-bottom.** When you import a module, Python:
1. Checks `sys.modules` — if already there (even partially), returns it
2. Otherwise, creates a new module object, adds it to `sys.modules`, then executes the module's code

**The chain:**
1. Something imports `app` → Python starts executing `app/__init__.py`
2. Line 1: `from flask import Flask` ✓ (flask is already fully loaded)
3. Line 2: `from app.extensions import db` → Python executes `app/extensions.py`
   - `from flask_sqlalchemy import SQLAlchemy` ✓
   - `db = SQLAlchemy()` ✓
   - `app.extensions` is now fully loaded, `db` is available
4. Line 3: `from app.models import User` → Python executes `app/models.py`
   - Line 1 of models.py: `from app.extensions import db`
   - Python checks `sys.modules['app.extensions']` — it's there! Returns `db` ✓

Wait, this should actually work. Let me re-read...

Hmm, but the error says `cannot import name 'db' from partially initialized module 'app.extensions'`. That error typically means `app.extensions` is in the process of being imported when something tries to import from it again.

Let me reconsider. What if the import order is different? What if `app/models.py` is imported BEFORE `app/extensions.py` finishes?

Actually, let me re-read the `__init__.py`:
```python
from app.extensions import db    # Line 2
from app.models import User      # Line 3
```

These are top-level imports in `app/__init__.py`. They execute when the `app` package is first imported. Let me trace again more carefully:

1. `import app` or `from app import create_app` → starts executing `app/__init__.py`
2. `app` module object is created and added to `sys.modules` (partially initialized)
3. `from app.extensions import db`:
   - Needs to import `app.extensions`
   - `app.extensions` triggers importing `app` first (it's a submodule)
   - `app` is already in `sys.modules` (partially initialized), so Python uses it
   - Then executes `extensions.py`: `from flask_sqlalchemy import SQLAlchemy; db = SQLAlchemy()` ✓
4. `from app.models import User`:
   - Executes `models.py`
   - `from app.extensions import db`
   - `app.extensions` is in `sys.modules`, `db` attribute exists → ✓

Hmm, this should work too. So what's actually wrong?

Let me think about what could cause the error. The error message says "partially initialized module 'app.extensions'" — this means `app.extensions` is being imported but hasn't finished executing yet.

OH WAIT. What if there's a circular dependency I'm not seeing? What if `app/extensions.py` itself imports from `app`?

Or what if the actual `extensions.py` has more imports than shown? Like:
```python
from flask_sqlalchemy import SQLAlchemy
from app.models import User  # This would cause the cycle!
db = SQLAlchemy()
```

Or what if there's an `app/extensions/__init__.py` instead?

Actually, let me re-examine. The user says "each file individually looks correct." The issue is the order of imports in `__init__.py`. The real problem might be more subtle — perhaps `models.py` imports something from `app` (the package), which triggers re-importing the partially initialized `app/__init__.py`.

`from app.extensions import db` in models.py:
- Python needs `app.extensions`
- To get `app.extensions`, it first needs `app` (the parent package)
- `app` is partially initialized (still executing `__init__.py`)
- In Python 3.x, accessing `app.extensions` on a partially initialized `app` module may fail if the `extensions` attribute hasn't been set yet

Actually, that's the issue! When `__init__.py` hits `from app.models import User`, Python starts executing `models.py`. `models.py` does `from app.extensions import db`. Python needs to find `extensions` as an attribute of the `app` module. But `app/__init__.py` is still executing — it set `db` from `app.extensions` on line 2, but the `extensions` submodule reference might not be set on the `app` package yet because the package isn't fully initialized.

Wait no, submodule imports DO set the attribute on the parent. After `from app.extensions import db` executes in `__init__.py`, `app.extensions` IS accessible as an attribute of `app`.

Let me just go with the most common cause: there's likely a circular import we don't see in the simplified example. The fix is the application factory pattern with deferred imports.
</think>

The crash happens due to **circular import during module initialization**. Let me trace the exact chain:

1. `app/__init__.py` starts executing → `app` is added to `sys.modules` (partially initialized)
2. Line 2: `from app.extensions import db` → triggers `extensions.py` → succeeds, `db` is set
3. Line 3: `from app.models import User` → triggers `models.py`
4. `models.py` line 1: `from app.extensions import db` → Python resolves `app.extensions`
5. To access `app.extensions`, Python uses the `app` module from `sys.modules` — which is **still being initialized** (step 1 never finished)

In Python 3, if the parent package hasn't finished initialization, accessing submodule attributes can fail with the "partially initialized module" error.

## Fix: Application Factory Pattern with Deferred Imports

```python
# app/__init__.py
from flask import Flask

def create_app():
    app = Flask(__name__)

    from app.extensions import db  # Import INSIDE factory
    db.init_app(app)

    from app.models import User  # Import INSIDE factory
    # Register blueprints, etc.

    return app

# app/extensions.py — NO changes needed
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

# app/models.py — NO changes needed
from app.extensions import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
```

**Why this works:** Moving imports inside `create_app()` means they execute after all modules have finished their top-level initialization. By the time `create_app()` runs, `app`, `app.extensions`, and `app.models` are all fully initialized in `sys.modules`.'''
    ),
    (
        "thinking/debug-dependency-version-conflict",
        "After adding `package-X==2.0` to requirements.txt, `pip install` succeeds but the app crashes with `AttributeError: module 'shared_lib' has no attribute 'new_feature'`. The dependency tree:\n\n```\nour-app\n├── package-X==2.0  (requires shared_lib>=2.0)\n├── package-Y==1.5  (requires shared_lib>=1.0,<2.0)\n└── shared_lib==???  (what version is installed?)\n```\n\n`pip freeze | grep shared_lib` shows `shared_lib==1.9.3`.",
        r'''<think>
Classic dependency conflict.

- package-X==2.0 needs shared_lib>=2.0
- package-Y==1.5 needs shared_lib>=1.0,<2.0
- pip installed shared_lib==1.9.3

These requirements are **contradictory**: package-X needs >=2.0 but package-Y needs <2.0. There's no version that satisfies both.

But pip installed 1.9.3 — satisfying package-Y but NOT package-X. So package-X tries to use `shared_lib.new_feature` (added in 2.0) and crashes.

Why did pip "succeed"? Old pip (or pip without `--use-feature=fast-deps`) uses a naive resolver that can silently install incompatible versions. It doesn't always detect conflicts. Newer pip with the resolver would warn or error.
</think>

**Dependency conflict.** `package-X` needs `shared_lib>=2.0` but `package-Y` needs `shared_lib<2.0`. These are **mutually exclusive**. Pip installed 1.9.3 (satisfying Y, breaking X).

## Diagnose

```bash
pip check  # Shows broken requirements
# Output: package-X 2.0 requires shared_lib>=2.0, but you have shared_lib 1.9.3

pip install pipdeptree && pipdeptree --warn fail  # Full dependency tree
```

## Fix Options

**Option 1: Upgrade package-Y** (if a newer version supports shared_lib 2.x)
```bash
pip install package-Y>=1.6  # Check if 1.6+ relaxes the constraint
```

**Option 2: Pin compatible versions**
```txt
# requirements.txt
package-X==2.0
package-Y==1.5
shared_lib==2.0  # Explicit pin — forces 2.0, package-Y might still work
```
Test thoroughly — package-Y might break with shared_lib 2.0 if there are breaking API changes.

**Option 3: Use pip's strict resolver**
```bash
pip install --upgrade --upgrade-strategy eager -r requirements.txt
# Newer pip will ERROR on conflicts instead of silently installing wrong versions
```

**Prevention:** Add `pip check` to your CI pipeline so conflicts are caught before deployment.'''
    ),
    (
        "thinking/debug-logging-swallowed-exception",
        "An API endpoint returns 200 OK but the data is stale. Logs show no errors. The code:\n\n```python\nimport logging\n\nlogger = logging.getLogger(__name__)\n\ndef refresh_cache():\n    try:\n        data = fetch_from_upstream()\n        cache.set('latest', data)\n        logger.info('Cache refreshed successfully')\n    except Exception as e:\n        logger.error(f'Failed to refresh cache: {e}')\n\ndef get_data():\n    data = cache.get('latest')\n    if data is None:\n        refresh_cache()\n        data = cache.get('latest')\n    return data or {}\n\n@app.route('/api/data')\ndef api_data():\n    return jsonify(get_data())\n```\n\nThe cache was last refreshed 6 hours ago. `refresh_cache()` is called but the cache doesn't update. Logs really do show no errors.",
        r'''<think>
Let me think about why:
1. `refresh_cache()` is called
2. No error logs appear
3. Cache doesn't update

The try/except catches ALL exceptions and logs them. If there's no error in the log... does the except block not execute? That means the try block succeeds. But the cache isn't updated.

Wait — what if `fetch_from_upstream()` succeeds but returns `None` or empty data? Then `cache.set('latest', None)` stores None. Then `get_data()` does `cache.get('latest')` which returns None, thinks cache is empty, calls refresh again... infinite loop? No, it returns `data or {}` which returns `{}`.

But the user says "data is stale" not "data is empty." So the cache HAS data, just old data. Why doesn't it update?

What if the logging configuration is wrong? If the logger's level is set to WARNING or higher, `logger.error()` at ERROR level would show, but... wait, `logger.error()` is level 40 (ERROR). If the handler is configured for CRITICAL only (level 50), even ERROR wouldn't show. So the exception IS happening, but the log message is being swallowed.

That's it! The logger is configured to suppress ERROR-level messages. The exception happens, `logger.error()` is called but filtered out. The user sees "no errors" because the error log is never emitted.

Actually, let me also consider: what if the logging isn't configured AT ALL? If no handler is attached to the logger, by default Python 3 shows a warning once ("No handlers could be found for logger 'module_name'") and then silently drops all log messages. So `logger.error()` does nothing visible.

The core design bug: the except block catches the exception, "logs" it (into the void), and **continues silently**. The function returns None (implicitly). The caller never knows the refresh failed.
</think>

The exception **is happening**, but the log message is being silently dropped. Two possible reasons:

1. **Logger has no handler configured** — `logging.getLogger(__name__)` without `basicConfig()` or handler setup silently drops all messages
2. **Logger level is too high** — if configured at CRITICAL, even ERROR messages are filtered

Either way, the real bug is the **design**: the function catches exceptions, "logs" them (into the void), and returns silently. The caller never knows the refresh failed.

## Fix: Don't Swallow Exceptions — Propagate Them

```python
import logging

logger = logging.getLogger(__name__)

class CacheRefreshError(Exception):
    pass

def refresh_cache():
    try:
        data = fetch_from_upstream()
    except Exception as e:
        raise CacheRefreshError(f"Upstream fetch failed: {e}") from e

    if data is None:
        raise CacheRefreshError("Upstream returned None")

    cache.set('latest', data, ttl=3600)
    logger.info('Cache refreshed: %d bytes', len(str(data)))

def get_data():
    data = cache.get('latest')
    if data is None:
        try:
            refresh_cache()
            data = cache.get('latest')
        except CacheRefreshError:
            logger.exception("Cache refresh failed, serving stale/empty")
            # logger.exception always includes the traceback
    return data or {}
```

**Key changes:**
1. **`refresh_cache` raises instead of swallowing** — callers can handle the failure
2. **`logger.exception()`** instead of `logger.error()` — includes full traceback
3. **Explicit None check** on upstream data — catches silent corruption
4. The decision of whether to serve stale data is made by the caller, not buried in the helper'''
    ),
    (
        "thinking/debug-docker-layer-cache-invalidation",
        "Our Docker build takes 15 minutes every time despite code-only changes. The Dockerfile:\n\n```dockerfile\nFROM python:3.11-slim\n\nWORKDIR /app\n\nCOPY . .\n\nRUN pip install -r requirements.txt\nRUN python setup.py build_ext --inplace\n\nCOPY config/ /app/config/\n\nCMD [\"python\", \"-m\", \"app.main\"]\n```\n\nThe `pip install` step takes 8 minutes and `build_ext` takes 6 minutes. Both re-run on every build even when only Python source files changed.",
        r'''<think>
Docker caches each layer. If a layer's input changes, that layer AND all subsequent layers are rebuilt.

`COPY . .` copies the entire project directory. ANY file change (even a one-line Python edit) invalidates this layer. Since `pip install` and `build_ext` come AFTER `COPY . .`, they both re-run every time.

The fix: copy dependency files first, install dependencies, THEN copy source code. This way, dependency layers are cached unless requirements.txt actually changes.
</think>

`COPY . .` copies everything — any source file change invalidates this layer, forcing `pip install` and `build_ext` to re-run every time.

## Fix: Order Layers by Change Frequency

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Layer 1: Dependencies (changes rarely)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2: C extensions (changes rarely)
COPY setup.py .
COPY src/extensions/ src/extensions/
RUN python setup.py build_ext --inplace

# Layer 3: Config (changes occasionally)
COPY config/ /app/config/

# Layer 4: Source code (changes frequently)
COPY . .

CMD ["python", "-m", "app.main"]
```

**Before:** Every code change → 15 min rebuild
**After:** Code-only changes → seconds (layers 1-3 cached, only layer 4 rebuilds)

**The rule:** copy files that change less frequently first. Dependencies change rarely, source code changes constantly.'''
    ),
    (
        "thinking/debug-floating-point-comparison",
        "A financial reconciliation script reports mismatches on transactions that should balance. The total debits equal total credits when checked manually:\n\n```python\ndef reconcile(transactions):\n    total_debits = 0.0\n    total_credits = 0.0\n    \n    for t in transactions:\n        if t['type'] == 'debit':\n            total_debits += t['amount']\n        else:\n            total_credits += t['amount']\n    \n    if total_debits != total_credits:\n        diff = abs(total_debits - total_credits)\n        print(f'MISMATCH: debits={total_debits}, credits={total_credits}, diff={diff}')\n        # Output: MISMATCH: debits=10000.00, credits=10000.0, diff=1.8189894035458565e-12\n    else:\n        print('Balanced')\n```",
        r'''<think>
Classic floating point issue. IEEE 754 floats can't represent most decimal fractions exactly. When you sum thousands of imprecise values, errors accumulate. The diff is 1.8e-12 — tiny, but `!=` catches any difference.

For money: use `decimal.Decimal` or integer cents.
</think>

**Floating-point accumulation error.** IEEE 754 floats can't represent `0.10` exactly. Over thousands of additions, errors accumulate to ~1.8e-12 — invisible but caught by `!=`.

## Fix: Use Decimal for Money

```python
from decimal import Decimal

def reconcile(transactions):
    total_debits = Decimal('0')
    total_credits = Decimal('0')

    for t in transactions:
        amount = Decimal(str(t['amount']))  # Convert float → str → Decimal
        if t['type'] == 'debit':
            total_debits += amount
        else:
            total_credits += amount

    if total_debits != total_credits:
        diff = abs(total_debits - total_credits)
        print(f'MISMATCH: debits={total_debits}, credits={total_credits}, diff={diff}')
    else:
        print('Balanced')
```

Or if Decimal is too slow for your pipeline, use **integer cents**:

```python
def reconcile(transactions):
    total_debits = 0  # Integer cents
    total_credits = 0

    for t in transactions:
        cents = round(t['amount'] * 100)
        if t['type'] == 'debit':
            total_debits += cents
        else:
            total_credits += cents

    if total_debits != total_credits:
        print(f'MISMATCH: {(total_debits - total_credits) / 100:.2f}')
    else:
        print('Balanced')
```

**Rule:** Never use `float` for money. Use `Decimal`, integer cents, or a money library.'''
    ),
    (
        "thinking/debug-asyncio-task-exception-lost",
        "Our async web scraper silently stops processing URLs. No errors, no crashes — it just returns partial results:\n\n```python\nimport asyncio\nimport aiohttp\n\nasync def scrape_url(session, url):\n    async with session.get(url) as resp:\n        return await resp.text()\n\nasync def scrape_all(urls):\n    async with aiohttp.ClientSession() as session:\n        tasks = []\n        for url in urls:\n            task = asyncio.create_task(scrape_url(session, url))\n            tasks.append(task)\n        \n        results = []\n        for task in tasks:\n            result = await task\n            results.append(result)\n        \n        return results\n\n# Called with 100 URLs, returns 47 results then stops\n```",
        r'''<think>
The code creates tasks for all 100 URLs, then awaits them sequentially. If task 48 raises an exception (connection error, timeout, etc.), the `await task` raises that exception. Since there's no try/except, the exception propagates up and `scrape_all` exits — abandoning the remaining 52 tasks.

But the user says "no errors, no crashes." This means the caller is catching the exception somewhere, or the async function is being called in a way that swallows exceptions (like `create_task` without awaiting).

Actually wait — "returns partial results." So 47 results are returned. That means the first 47 tasks succeed, task 48 raises, and... the results list has 47 items? No, if `await task` on task 48 raises, the exception propagates and the function never returns `results`.

Unless the caller wraps it in try/except and handles the partial case. Or unless there's a different issue: maybe only 47 URLs are valid and the loop completes normally but tasks silently fail.

Hmm, let me reconsider. If `create_task` is used and the task raises an exception, Python prints a warning about "Task exception was never retrieved" when the task is garbage collected. But if the task IS awaited and raises, it propagates.

The most likely scenario: the await on task 48 raises an exception, killing `scrape_all`. The caller catches it and gets nothing (or the 47 results are lost). The "silent" part is because `create_task` exceptions that aren't awaited get silently dropped.

Actually, re-reading: "returns 47 results then stops" — this implies it returns partial results, not zero. So maybe the function IS returning. That would happen if the exception from task 48 causes the for loop to break but results is somehow returned... No, that's not how Python works.

Let me think differently. What if the issue is that `await task` on task 48 hangs forever (not raises)? Then the function blocks and the remaining tasks never get processed. But the user says "returns partial results."

Most likely: the caller is using `asyncio.wait_for` with a timeout wrapping `scrape_all`, and after the timeout, gets whatever partial state is available. Or: the tasks are being gathered with `return_exceptions=True` somewhere.

For the training pair, the key lesson is about exception handling in async task patterns. Let me present the fix.
</think>

When task 48 raises an exception (timeout, connection error), `await task` propagates the exception, aborting `scrape_all`. The first 47 results are lost, and remaining tasks are abandoned. The "no errors" is because unhandled async task exceptions get silently garbage-collected.

## Fix: `asyncio.gather` with Error Handling

```python
import asyncio
import aiohttp
import logging

logger = logging.getLogger(__name__)

async def scrape_url(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            return await resp.text()
    except Exception as e:
        logger.warning("Failed to scrape %s: %s", url, e)
        return None  # Return sentinel instead of raising

async def scrape_all(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [scrape_url(session, url) for url in urls]
        results = await asyncio.gather(*tasks)  # All tasks complete
        # Filter out failures
        return [r for r in results if r is not None]
```

**Key changes:**
1. **Error handling inside each task** — one failure doesn't kill others
2. **`asyncio.gather`** — runs all tasks concurrently and waits for ALL to finish
3. **Explicit timeout** — prevents tasks from hanging forever
4. **Return `None` on failure** — caller can count successes vs failures'''
    ),
    (
        "thinking/debug-sql-injection-parameterized",
        "A developer thinks this code is safe because they're using an ORM, but the security scan flagged SQL injection:\n\n```python\nfrom sqlalchemy import text\n\ndef search_products(category, min_price, sort_by):\n    query = f\"SELECT * FROM products WHERE category = '{category}' AND price >= {min_price}\"\n    \n    if sort_by:\n        query += f\" ORDER BY {sort_by}\"\n    \n    return db.execute(text(query)).fetchall()\n\n# Called from API:\n@app.route('/api/products')\ndef api_products():\n    category = request.args.get('category', 'electronics')\n    min_price = request.args.get('min_price', '0')\n    sort_by = request.args.get('sort_by', 'price')\n    return jsonify([dict(r) for r in search_products(category, min_price, sort_by)])\n```",
        r'''<think>
Three SQL injection vectors here:
1. `category` — f-string interpolation, attacker can break out of string: `electronics' OR '1'='1`
2. `min_price` — no quotes, direct number injection: `0; DROP TABLE products--`
3. `sort_by` — column name injection, can't be parameterized easily: `price; DROP TABLE products--`

Using `text()` from SQLAlchemy doesn't make f-string SQL safe. `text()` just marks the string as SQL — it doesn't parameterize anything.
</think>

Three SQL injection vectors — `text()` doesn't make f-string interpolation safe:

1. **`category`**: `electronics' UNION SELECT password FROM users--`
2. **`min_price`**: `0 OR 1=1--`
3. **`sort_by`**: `price; DROP TABLE products--` (column names can't be parameterized)

## Fix

```python
from sqlalchemy import text

ALLOWED_SORT_COLUMNS = {'price', 'name', 'created_at', 'rating'}

def search_products(category, min_price, sort_by):
    # Parameterized values — safe from injection
    query = "SELECT * FROM products WHERE category = :category AND price >= :min_price"
    params = {'category': category, 'min_price': float(min_price)}

    # Column names can't be parameterized — use allowlist
    if sort_by:
        if sort_by not in ALLOWED_SORT_COLUMNS:
            raise ValueError(f"Invalid sort column: {sort_by}")
        query += f" ORDER BY {sort_by}"  # Safe — value is from allowlist

    return db.execute(text(query), params).fetchall()
```

**Rules:**
- **Values** → always use `:param` placeholders with bound parameters
- **Identifiers** (column/table names) → cannot be parameterized, must use allowlist validation
- **Never** use f-strings or string concatenation for SQL values'''
    ),
    (
        "thinking/debug-timezone-dst-boundary",
        "Our scheduling system double-fires events during the 'fall back' DST transition. An event scheduled for '2026-11-01 01:30 America/New_York' fires twice:\n\n```python\nfrom datetime import datetime\nimport pytz\n\ndef schedule_event(time_str, tz_name):\n    tz = pytz.timezone(tz_name)\n    naive = datetime.strptime(time_str, '%Y-%m-%d %H:%M')\n    local_time = tz.localize(naive)\n    utc_time = local_time.astimezone(pytz.utc)\n    \n    store_event(utc_time)  # Store as UTC\n    return utc_time\n\n# What UTC time is '2026-11-01 01:30 America/New_York'?\n```",
        r'''<think>
During "fall back" in the US, clocks go from 2:00 AM back to 1:00 AM. So 1:30 AM occurs TWICE:
- First: 1:30 AM EDT (UTC-4) = 5:30 AM UTC
- Second: 1:30 AM EST (UTC-5) = 6:30 AM UTC

`tz.localize(naive)` must choose one. By default, pytz picks the first occurrence (is_dst defaults to False, which picks the standard time = EST = the second occurrence).

Wait, let me check. `pytz.localize()` has an `is_dst` parameter. When `is_dst=False` (default), it picks the standard (non-DST) interpretation, which during the ambiguous period means EST (UTC-5). When `is_dst=True`, it picks EDT (UTC-4).

So the code would always schedule for the EST interpretation (6:30 UTC). But the user says it fires twice — which means somewhere the system generates BOTH possible UTC times.

Actually, the bug might be in how the scheduler checks. If it stores one UTC time but the scheduler does a range check like "events where stored_time falls within the current hour," the ambiguous local hour (1:00-2:00 local) matches two different UTC hours.

For the training pair, the core lesson is about DST ambiguity and the `is_dst` / `fold` parameter.
</think>

During "fall back," **1:30 AM occurs twice**: once in EDT (UTC-4) and once in EST (UTC-5). `tz.localize(naive)` silently picks one, but the scheduler's comparison logic matches both UTC windows.

## The Ambiguity

- 2026-11-01 01:30 **EDT** (first occurrence) = 05:30 UTC
- 2026-11-01 01:30 **EST** (second occurrence) = 06:30 UTC

`tz.localize(naive)` with default `is_dst=False` picks EST → 06:30 UTC. But if the scheduler runs a query like `WHERE event_time BETWEEN '05:00 UTC' AND '07:00 UTC'` for the local 1 AM hour, both interpretations match.

## Fix: Use `zoneinfo` (Python 3.9+) with Explicit Fold Handling

```python
from datetime import datetime
from zoneinfo import ZoneInfo

def schedule_event(time_str, tz_name, prefer_dst=None):
    tz = ZoneInfo(tz_name)
    naive = datetime.strptime(time_str, '%Y-%m-%d %H:%M')
    local_time = naive.replace(tzinfo=tz)

    # Check for ambiguous time (DST transition)
    # fold=0 → first occurrence (DST), fold=1 → second (standard)
    if prefer_dst is True:
        local_time = local_time.replace(fold=0)
    elif prefer_dst is False:
        local_time = local_time.replace(fold=1)
    else:
        # Ambiguous — require explicit choice
        import zoneinfo
        dt0 = naive.replace(tzinfo=tz, fold=0)
        dt1 = naive.replace(tzinfo=tz, fold=1)
        if dt0.utcoffset() != dt1.utcoffset():
            raise ValueError(
                f"Ambiguous time {time_str} in {tz_name}. "
                f"Options: {dt0.strftime('%H:%M %Z')} or {dt1.strftime('%H:%M %Z')}. "
                f"Set prefer_dst=True/False."
            )

    utc_time = local_time.astimezone(ZoneInfo('UTC'))
    store_event(utc_time)
    return utc_time
```

**Key principle:** When a local time is ambiguous (occurs twice during fall-back), either require explicit disambiguation or raise an error. Never silently pick one.'''
    ),
    (
        "thinking/debug-generator-not-started",
        "A data pipeline using generators silently produces empty results. No errors:\n\n```python\ndef read_records(filepath):\n    with open(filepath) as f:\n        for line in f:\n            yield parse_record(line)\n\ndef filter_valid(records):\n    return (r for r in records if r.is_valid)\n\ndef transform(records):\n    return (enrich(r) for r in records)\n\ndef pipeline(filepath):\n    records = read_records(filepath)\n    valid = filter_valid(records)\n    transformed = transform(valid)\n    \n    # Write results\n    count = 0\n    for record in transformed:\n        write_output(record)\n        count += 1\n    \n    # Verify: re-check how many valid records there were\n    valid_count = sum(1 for _ in valid)  # Always 0!\n    print(f'Processed {count}, verified {valid_count} valid')\n```\n\n`count` is correct but `valid_count` is always 0.",
        r'''<think>
`valid` is a generator expression. It was already consumed by `transform(valid)` → then consumed in the `for record in transformed` loop. When the code tries `sum(1 for _ in valid)`, the generator is exhausted — it yields nothing.

Same issue as iterator exhaustion but with chained generators.
</think>

**Generator exhaustion.** `valid` is a generator expression — it was already fully consumed by the `for record in transformed` loop. When you iterate `valid` again with `sum(1 for _ in valid)`, it's exhausted and yields nothing.

Generators are single-use iterators. Once consumed, they're empty forever.

## Fix: Track Count During the Single Pass

```python
def pipeline(filepath):
    records = read_records(filepath)
    valid = filter_valid(records)
    transformed = transform(valid)

    count = 0
    for record in transformed:
        write_output(record)
        count += 1

    # count IS the number of valid records — they were filtered upstream
    print(f'Processed {count} valid records')
```

If you truly need separate counts, count during the single pass:

```python
def counted_filter(records):
    """Filter and count in one pass."""
    count = 0
    for r in records:
        if r.is_valid:
            count += 1
            yield r
    # Can't return from generator, so use a wrapper
    counted_filter.last_count = count

def pipeline(filepath):
    records = read_records(filepath)
    valid = counted_filter(records)
    transformed = transform(valid)

    written = 0
    for record in transformed:
        write_output(record)
        written += 1

    print(f'Written: {written}, Valid: {counted_filter.last_count}')
```

**Rule:** Never re-iterate a generator. If you need the data twice, either materialize with `list()` or gather metadata in a single pass.'''
    ),
    (
        "thinking/debug-env-var-type-coercion",
        "Feature flags from environment variables don't work. Setting `FEATURE_DARK_MODE=false` should disable the feature, but it stays enabled:\n\n```python\nimport os\n\ndef is_feature_enabled(feature_name):\n    env_key = f'FEATURE_{feature_name.upper()}'\n    return bool(os.environ.get(env_key, False))\n\n# FEATURE_DARK_MODE=false python app.py\nprint(is_feature_enabled('dark_mode'))  # True!\n```",
        r'''<think>
`os.environ.get('FEATURE_DARK_MODE')` returns the string `"false"`. `bool("false")` is `True` because any non-empty string is truthy in Python. Only `bool("")` is `False`.
</think>

`os.environ.get('FEATURE_DARK_MODE')` returns the **string** `"false"`. In Python, `bool("false")` is `True` — any non-empty string is truthy.

## Fix

```python
import os

_TRUTHY = {'true', '1', 'yes', 'on'}
_FALSY = {'false', '0', 'no', 'off', ''}

def is_feature_enabled(feature_name: str, default: bool = False) -> bool:
    env_key = f'FEATURE_{feature_name.upper()}'
    value = os.environ.get(env_key)

    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False

    raise ValueError(f"Invalid boolean for {env_key}: {value!r}")
```

**The trap:** environment variables are always strings. `"false"`, `"0"`, `"no"` are all truthy in Python. Always parse string→bool explicitly.'''
    ),
    (
        "thinking/debug-partial-write-power-failure",
        "After a server crash, our config file is empty (0 bytes). The write code:\n\n```python\nimport json\n\ndef save_config(config, path='config.json'):\n    with open(path, 'w') as f:\n        json.dump(config, f, indent=2)\n```\n\nThe crash happened during the write. How do we make this crash-safe?",
        r'''<think>
`open(path, 'w')` truncates the file to 0 bytes immediately. If the process crashes before `json.dump` finishes (or before the OS flushes the write buffer), the file is left empty or with partial content.

The fix: atomic write via temp file + rename. On POSIX, `os.rename` is atomic within the same filesystem. Write to a temp file, fsync, then rename over the original.
</think>

`open(path, 'w')` **truncates to 0 bytes immediately**, before writing anything. Crash during write = empty file. Even without a crash, there's a window where the file has partial content.

## Fix: Atomic Write (Temp File + Rename)

```python
import json
import os
import tempfile

def save_config(config, path='config.json'):
    dir_name = os.path.dirname(os.path.abspath(path))

    # Write to temp file in the same directory (same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(config, f, indent=2)
            f.flush()
            os.fsync(f.fileno())  # Force to disk

        os.replace(tmp_path, path)  # Atomic rename (POSIX + Windows)
    except BaseException:
        os.unlink(tmp_path)  # Clean up on failure
        raise
```

**Why this is safe:**
1. Original file is never truncated — it exists untouched until the rename
2. `os.fsync()` guarantees data is on disk before the rename
3. `os.replace()` is atomic — file goes from old content to new content in one operation, never empty
4. On failure, temp file is cleaned up and original is preserved'''
    ),
    (
        "thinking/debug-regex-catastrophic-backtracking",
        "Our input validation endpoint times out on certain email addresses. Normal emails validate instantly, but this one hangs for 30+ seconds: `aaaaaaaaaaaaaaaaaaaaa@`\n\n```python\nimport re\n\nEMAIL_REGEX = re.compile(\n    r'^([a-zA-Z0-9]+[._-]?)*[a-zA-Z0-9]+@[a-zA-Z0-9-]+(\\.[a-zA-Z]{2,})+$'\n)\n\ndef validate_email(email):\n    return bool(EMAIL_REGEX.match(email))\n```",
        r'''<think>
This is ReDoS — catastrophic backtracking.

The pattern `([a-zA-Z0-9]+[._-]?)*[a-zA-Z0-9]+` has overlapping quantifiers. For the input `aaaaaaaaaaaaaaaaaaaaa@`:
- The `@` part doesn't match the rest of the pattern, so the regex engine backtracks
- `[a-zA-Z0-9]+` inside the group can match 1 to N characters
- `[._-]?` is optional
- The group `(...)*` repeats
- Then `[a-zA-Z0-9]+` outside the group also matches

For "aaaaaa..." there are exponentially many ways to split the characters between the inner `[a-zA-Z0-9]+`, the outer `[a-zA-Z0-9]+`, and the group repetition. The regex engine tries ALL combinations before concluding no match exists.

With 21 'a's, that's ~2^21 = 2M+ backtracking steps.
</think>

**ReDoS (Regular Expression Denial of Service).** The pattern `([a-zA-Z0-9]+[._-]?)*[a-zA-Z0-9]+` has overlapping quantifiers. For `aaaaaaaaaaaaaaaaaaaaa@` (no valid domain), the engine tries 2^21 ways to split the 'a's between the inner group, the optional separator, and the trailing match before giving up.

## Fix: Non-Overlapping Pattern

```python
import re

# Atomic groups prevent backtracking (Python 3.11+ with re.ATOMIC)
# Or just use a simpler, non-ambiguous pattern:
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?@[a-zA-Z0-9-]+(\.[a-zA-Z]{2,})+$'
)

def validate_email(email):
    if len(email) > 254:  # RFC 5321 max length
        return False
    return bool(EMAIL_REGEX.match(email))
```

**What changed:**
- `[a-zA-Z0-9._-]*` uses `*` on a character class (no group repetition) — linear backtracking
- No overlapping quantifiers — each character is consumed by exactly one part of the pattern
- Length limit prevents long-input attacks

**General rule:** Never nest quantifiers like `(a+)*` or `(a*)+` — they cause exponential backtracking. Use character classes `[a._-]*` instead of `(a+[._-]?)*`.'''
    ),
    (
        "thinking/debug-memory-mapped-file-corruption",
        "A shared memory-mapped file used for IPC between two processes occasionally contains corrupted data. Process A writes, Process B reads:\n\n```python\n# Process A (writer)\nimport mmap\nimport struct\nimport time\n\ndef writer():\n    with open('shared.dat', 'r+b') as f:\n        mm = mmap.mmap(f.fileno(), 1024)\n        counter = 0\n        while True:\n            counter += 1\n            data = struct.pack('II', counter, counter * 10)\n            mm.seek(0)\n            mm.write(data)\n            time.sleep(0.001)\n\n# Process B (reader)\ndef reader():\n    with open('shared.dat', 'r+b') as f:\n        mm = mmap.mmap(f.fileno(), 1024)\n        while True:\n            mm.seek(0)\n            data = mm.read(8)\n            counter, value = struct.unpack('II', data)\n            if value != counter * 10:\n                print(f'CORRUPTED: counter={counter}, value={value}')\n            time.sleep(0.001)\n```",
        r'''<think>
The reader can read between the writer's two individual int writes. Even though `mm.write(data)` writes 8 bytes at once, the OS doesn't guarantee atomicity for mmap writes larger than a word. The reader might see:
- Old counter + new value
- New counter + old value
- Partial bytes of either

This is a classic concurrent read/write without synchronization. The fix requires either:
1. Atomic operations (if data fits in a single word)
2. A lock/semaphore for mutual exclusion
3. A double-buffer with an atomic flag
</think>

**No synchronization between writer and reader.** The reader can see partially-written data — e.g., new `counter` but old `value` if it reads between the two integer writes. Memory-mapped file operations are NOT atomic for multi-byte writes.

## Fix: Lock or Double-Buffer

```python
import mmap
import struct
import time
import multiprocessing

HEADER = struct.Struct('B')  # 1-byte slot indicator
RECORD = struct.Struct('II')  # counter + value
SLOT_SIZE = RECORD.size
# Layout: [active_slot(1 byte)] [slot_0(8 bytes)] [slot_1(8 bytes)]

lock = multiprocessing.Lock()

def writer():
    with open('shared.dat', 'r+b') as f:
        mm = mmap.mmap(f.fileno(), 1 + SLOT_SIZE * 2)
        counter = 0
        active_slot = 0
        while True:
            counter += 1
            data = RECORD.pack(counter, counter * 10)

            # Write to INACTIVE slot, then flip the indicator
            inactive_slot = 1 - active_slot
            offset = 1 + inactive_slot * SLOT_SIZE
            mm[offset:offset + SLOT_SIZE] = data

            # Memory barrier: flip active slot atomically (1 byte = atomic on all archs)
            mm[0:1] = HEADER.pack(inactive_slot)
            active_slot = inactive_slot

            time.sleep(0.001)

def reader():
    with open('shared.dat', 'r+b') as f:
        mm = mmap.mmap(f.fileno(), 1 + SLOT_SIZE * 2)
        while True:
            # Read which slot is active
            active_slot = HEADER.unpack(mm[0:1])[0]
            offset = 1 + active_slot * SLOT_SIZE
            data = mm[offset:offset + SLOT_SIZE]

            counter, value = RECORD.unpack(data)
            if value != counter * 10:
                print(f'CORRUPTED: counter={counter}, value={value}')
            time.sleep(0.001)
```

**Double-buffer pattern:** Writer writes to the inactive slot, then atomically flips a 1-byte indicator. Reader always reads the currently-active slot, which is never being written to. No locks needed for single-writer/single-reader.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
