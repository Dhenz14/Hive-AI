"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 6)

Autonomously fixing code suggestion patterns — detecting and correcting
systematic errors in code recommendations.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-fix-outdated-patterns",
        r'''I sometimes suggest outdated coding patterns because they were common when I learned them. How do I autonomously detect and update my code suggestion patterns?''',
        r'''<think>
Outdated patterns are one of the most insidious problems in code suggestions. They technically work but aren't best practice anymore. The user implements them, and everything functions — but they've written legacy code on day one.

**Common outdated pattern categories:**
1. Language features superseded by newer ones (var → let/const)
2. Library patterns replaced by built-in features (lodash → native JS)
3. Architecture patterns that fell out of favor (God objects, deep inheritance)
4. Security practices that are now insufficient (MD5 hashing)
5. Framework-specific patterns from old versions

**Detection strategy:** Maintain awareness of when patterns were introduced and whether they've been superseded.
</think>

**Detecting and Fixing Outdated Code Suggestions**

**Pattern age audit — check before suggesting:**

| Category | Outdated pattern | Modern replacement | How to detect |
|----------|-----------------|-------------------|---------------|
| JS variables | `var x = 5` | `const x = 5` or `let x = 5` | `var` is pre-ES6 (2015) |
| JS async | Callback pyramids | `async/await` | Nested callbacks = outdated |
| Python strings | `"Hello %s" % name` | `f"Hello {name}"` | `%` formatting is pre-3.6 |
| Python typing | No type hints | Type hints everywhere | Untyped code = pre-3.5 |
| React | Class components | Functional + hooks | `class extends Component` = pre-16.8 |
| Error handling | Generic `catch (e)` | Specific error types | Catching everything = bad practice |

**The self-check protocol:**
```
Before suggesting code, ask:
1. "When was this pattern introduced?" (is it current?)
2. "Has a better alternative emerged since?" (is it best practice?)
3. "What version of the language/framework does this require?"
4. "Would a senior engineer at a modern company use this?"

If any answer raises doubt → research the current best practice.
```

**Example — catching an outdated suggestion:**
```python
# My first instinct (outdated):
import requests
try:
    response = requests.get(url)
    data = response.json()
except Exception as e:
    print(f"Error: {e}")

# Self-check:
# - "except Exception" catches too broadly → outdated practice
# - No timeout specified → silent hang risk
# - No status code check → silent failure

# Corrected (modern):
import httpx

async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
```

**Building an update trigger system:**
```
When I suggest a pattern, flag it if:
□ I learned it more than 3 years ago
□ It uses a library that has a major new version
□ The language has released 2+ major versions since I learned it
□ I can't cite WHY this pattern is preferred over alternatives
□ It doesn't use type hints, async, or other modern features

Any flag → pause and verify it's still current.
```

**The versioned recommendation pattern:**
```
Instead of: "Use useEffect for side effects"
Say: "In React 18+, use useEffect for side effects.
     Note: In the upcoming React compiler, some patterns
     will change — check the migration guide if you're
     on React 19+."

Versioning your advice prevents it from becoming outdated
silently.
```

**The meta-principle:** Every code pattern has a shelf life. The more confident you are in a pattern, the more likely you learned it long ago and haven't re-evaluated it. Treat high confidence in old knowledge as a signal to verify, not a reason to skip verification.'''
    ),
    (
        "thinking/auto-autonomous-fix-copy-paste-code",
        r'''I sometimes suggest code that works in isolation but causes problems when integrated into a real project — missing imports, namespace conflicts, incompatible versions. How do I improve this?''',
        r'''<think>
This is the "example code vs. production code" gap. Code snippets in explanations often work in a vacuum but fail in reality because:

1. Missing dependencies/imports
2. Implicit assumptions about environment (OS, Python version, etc.)
3. Naming conflicts with common libraries
4. Missing error handling that matters in production
5. Hardcoded values that should be configurable
6. No consideration of the existing codebase

**The fix:** Mentally simulate integrating the code into a real project before suggesting it.
</think>

**Fixing the Integration Gap in Code Suggestions**

**The integration checklist (run before suggesting any code):**

```
□ IMPORTS: Are all imports listed? Including standard library?
□ DEPENDENCIES: Are third-party packages specified with versions?
□ COMPATIBILITY: Does this work on the user's likely Python/Node/etc. version?
□ NAMING: Could any variable/function names conflict with common libraries?
□ ERROR HANDLING: What happens when this code fails in production?
□ CONFIGURATION: Are hardcoded values (URLs, paths, keys) parameterized?
□ SIDE EFFECTS: Does this code modify global state, files, or environment?
```

**Bad suggestion (works in isolation, fails in reality):**
```python
# Fetch user data
data = requests.get("https://api.example.com/users").json()
users = [User(d['name'], d['email']) for d in data]
```

**Problems:**
```
1. No "import requests" — will fail
2. No "from models import User" — undefined
3. No error handling — crashes on network failure
4. No timeout — hangs forever on slow network
5. No authentication — will get 401 in production
6. Hardcoded URL — different per environment
```

**Good suggestion (integration-ready):**
```python
import httpx
from typing import List
from app.models import User
from app.config import settings

async def fetch_users() -> List[User]:
    """Fetch user data from the external API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.API_BASE_URL}/users",
            headers={"Authorization": f"Bearer {settings.API_KEY}"},
        )
        response.raise_for_status()
        data = response.json()
        return [User(name=d["name"], email=d["email"]) for d in data]
```

**The mental simulation test:**
```
Before suggesting code, imagine:
1. The user creates a new file and pastes this code
2. They run it immediately
3. What error do they get?

If the answer isn't "it works" → add the missing pieces.
```

**Context-aware suggestions:**
```
When you don't know the user's setup, be explicit:

"This uses httpx (install with: pip install httpx).
 Requires Python 3.8+.
 Assumes you have a User model with name and email fields.
 Replace settings.API_BASE_URL with your actual API URL."
```

**The "copy-paste test":**
```
Could someone copy this code into a fresh file,
install the stated dependencies, and run it successfully?

If yes → good suggestion
If no  → what's missing?
```

**The meta-principle:** Example code should be as close to production code as possible without sacrificing clarity. The gap between "example" and "production-ready" is where bugs live. Close that gap proactively.'''
    ),
    (
        "thinking/auto-autonomous-fix-error-handling-suggestions",
        r'''I notice I often suggest try/except blocks that are too broad or too narrow. How do I calibrate my error handling suggestions to be appropriate for the context?''',
        r'''<think>
Error handling calibration is one of the hardest things to get right in code suggestions. Too broad catches everything and hides bugs. Too narrow misses real failures. The right level depends on context.

**Common mistakes:**
1. `except Exception` — catches everything, including bugs you want to see
2. `except SpecificError` only — misses related errors
3. Catch and ignore (bare `except: pass`) — silent failures
4. Catch and log but don't handle — user still gets an error
5. Too many try/except blocks — obscures the happy path

**The right approach depends on:**
- Is this a library or an application?
- Is this a critical path or a best-effort operation?
- What should happen when it fails?
- Who sees the error — developer or end user?
</think>

**Calibrating Error Handling Suggestions**

**The error handling decision matrix:**

| Context | Approach | Example |
|---------|----------|---------|
| Library code | Let exceptions propagate (caller decides) | `raise ValueError("invalid input")` |
| Application entry point | Catch broadly, show user-friendly message | `except Exception: show_error_page()` |
| Critical operation | Catch specifically, retry or fail loudly | `except ConnectionError: retry()` |
| Best-effort operation | Catch specifically, log and continue | `except TimeoutError: log.warning(...)` |
| Data processing | Catch per-item, continue batch | `except ValueError: skip_and_log(item)` |

**The calibration checklist:**
```
Before writing try/except, answer:
1. WHAT can fail? (specific exceptions)
2. WHY would it fail? (network, input, state)
3. WHO needs to know? (user, developer, ops)
4. WHAT should happen? (retry, skip, abort, degrade)
5. Is silence acceptable? (almost never)
```

**Bad patterns and their fixes:**

**Too broad:**
```python
# BAD: Catches bugs you want to see
try:
    result = process_data(input)
except Exception:
    return None  # silently hides TypeError, AttributeError, etc.

# GOOD: Catch only what you expect
try:
    result = process_data(input)
except (ValueError, KeyError) as e:
    logger.warning(f"Invalid input: {e}")
    return default_value
```

**Too narrow:**
```python
# BAD: Only catches one specific error
try:
    response = httpx.get(url)
except httpx.ConnectTimeout:
    retry()
# Misses: ConnectError, ReadTimeout, HTTPStatusError

# GOOD: Catch the family of related errors
try:
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
except httpx.TimeoutException:
    retry()  # any timeout
except httpx.HTTPStatusError as e:
    handle_http_error(e)  # 4xx/5xx
except httpx.RequestError as e:
    handle_network_error(e)  # connection failures
```

**Catch and ignore (worst pattern):**
```python
# NEVER DO THIS:
try:
    something()
except:
    pass

# If you must continue despite errors, at minimum:
try:
    something()
except SpecificError as e:
    logger.error(f"something() failed: {e}", exc_info=True)
    # Explicit decision to continue despite failure
```

**The context-sensitive template:**
```python
# For CRITICAL operations (payments, data writes):
try:
    result = critical_operation()
except ExpectedError as e:
    logger.error(f"Critical operation failed: {e}")
    alert_ops_team(e)  # someone needs to know NOW
    raise  # don't swallow critical failures

# For BEST-EFFORT operations (analytics, caching):
try:
    cache.set(key, value)
except CacheError as e:
    logger.warning(f"Cache write failed: {e}")
    # Continue without cache — degraded but functional
```

**The meta-principle:** Error handling should match the severity and recoverability of the failure. Critical failures should be loud. Expected failures should be handled gracefully. The worst error handling is the kind that makes problems invisible.'''
    ),
    (
        "thinking/auto-autonomous-fix-security-suggestions",
        r'''How do I autonomously detect when my code suggestions have security implications that I might be overlooking?''',
        r'''<think>
Security is the area where code suggestion mistakes have the highest consequences. A working-but-insecure code suggestion can lead to data breaches, unauthorized access, or data loss.

**Common security blind spots in code suggestions:**
1. SQL injection (string concatenation in queries)
2. Hardcoded credentials
3. Missing input validation
4. Insecure defaults (HTTP instead of HTTPS, no CORS, etc.)
5. Overly permissive file operations
6. Missing authentication/authorization checks
7. Insecure random number generation for security contexts
8. Logging sensitive data

**The challenge:** Security issues are invisible in the happy path. The code works correctly — until an attacker exploits it.
</think>

**Autonomous Security Review for Code Suggestions**

**The security scan checklist (run on EVERY code suggestion):**

```
□ INPUT: Is user input ever used directly in queries, commands, or paths?
□ SECRETS: Are any credentials, keys, or tokens in the code?
□ AUTH: Does this endpoint/function check who's calling it?
□ CRYPTO: Are security-sensitive operations using secure algorithms?
□ TRANSPORT: Is data transmitted over HTTPS, not HTTP?
□ LOGGING: Is sensitive data (passwords, tokens, PII) excluded from logs?
□ PERMISSIONS: Are file/database operations scoped to minimum required?
□ VALIDATION: Is input validated for type, range, and format?
```

**Critical patterns to catch:**

**SQL Injection:**
```python
# INSECURE (catch this every time):
query = f"SELECT * FROM users WHERE email = '{email}'"
cursor.execute(query)

# SECURE:
cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
```

**Hardcoded secrets:**
```python
# INSECURE (catch this every time):
API_KEY = "sk-abc123def456"
db_password = "supersecret"

# SECURE:
import os
API_KEY = os.environ["API_KEY"]
db_password = os.environ["DB_PASSWORD"]
```

**Missing auth checks:**
```python
# INSECURE:
@app.route("/admin/users")
def list_users():
    return User.query.all()  # anyone can access!

# SECURE:
@app.route("/admin/users")
@require_role("admin")
def list_users():
    return User.query.all()
```

**Insecure randomness:**
```python
# INSECURE (for security contexts):
import random
token = ''.join(random.choices(string.ascii_letters, k=32))

# SECURE:
import secrets
token = secrets.token_urlsafe(32)
```

**The security impact assessment:**
```
For every code suggestion, ask:
1. "What if the input is malicious?" (injection)
2. "What if this code is called by an unauthorized user?" (auth)
3. "What if this runs in production with real data?" (secrets/PII)
4. "What if an attacker reads the source code?" (hardcoded secrets)
5. "What if this data is intercepted in transit?" (encryption)
```

**Severity-based response:**
```
CRITICAL (must fix before suggesting):
  - SQL injection, command injection
  - Hardcoded production credentials
  - Missing authentication on sensitive endpoints

HIGH (flag prominently):
  - Missing input validation
  - Insecure hash algorithms (MD5/SHA1 for passwords)
  - Overly permissive CORS

MEDIUM (note in explanation):
  - Missing rate limiting
  - Verbose error messages in production
  - Missing HTTPS enforcement
```

**The meta-principle:** Assume every code suggestion will be copy-pasted into production by someone who trusts you. If that thought makes you uncomfortable about a piece of code, fix it before suggesting it. Security isn't a feature — it's a baseline.'''
    ),
    (
        "thinking/auto-autonomous-fix-performance-suggestions",
        r'''How do I autonomously detect when my code suggestions have hidden performance problems — things that work fine in development but fail at scale?''',
        r'''<think>
Performance issues in code suggestions are sneaky because the code works perfectly during development with small datasets. The problems only appear at scale.

**Common hidden performance problems:**
1. N+1 queries (loads related data one at a time)
2. Loading entire datasets into memory
3. Synchronous I/O where async is needed
4. Missing pagination
5. Quadratic algorithms hidden in innocent-looking code
6. String concatenation in loops
7. Missing database indexes for common queries
8. Unnecessary serialization/deserialization

**Detection requires thinking about scale: "What happens when there are 1 million records?"**
</think>

**Detecting Hidden Performance Problems in Code Suggestions**

**The scale simulation test:**
```
For every code suggestion, mentally substitute:
  - 10 items → 1,000,000 items
  - 1 user → 10,000 concurrent users
  - 1 MB data → 10 GB data
  - Local network → 200ms latency

Does the code still work? How long does it take?
```

**Hidden performance killers to detect:**

**N+1 queries (the most common):**
```python
# Looks innocent, kills at scale:
users = User.query.all()
for user in users:
    orders = Order.query.filter_by(user_id=user.id).all()
    # 1 query for users + N queries for orders = N+1

# Fix: Eager load
users = User.query.options(joinedload(User.orders)).all()
# 1 query with JOIN = fast at any scale
```

**Loading everything into memory:**
```python
# Works with 100 rows, crashes with 10 million:
all_data = list(db.query("SELECT * FROM logs"))
filtered = [row for row in all_data if row.level == "ERROR"]

# Fix: Filter in the database, paginate results
error_logs = db.query(
    "SELECT * FROM logs WHERE level = 'ERROR' LIMIT 100 OFFSET 0"
)
```

**Quadratic algorithms hiding in plain sight:**
```python
# O(n^2) — looks simple, explodes at scale:
def find_duplicates(items):
    duplicates = []
    for i, item in enumerate(items):
        if item in items[i+1:]:  # 'in' scans the list = O(n)
            duplicates.append(item)
    return duplicates
# 1,000 items: 0.01s | 1,000,000 items: 3+ hours

# O(n) fix:
def find_duplicates(items):
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:  # set lookup = O(1)
            duplicates.add(item)
        seen.add(item)
    return list(duplicates)
# 1,000,000 items: <1 second
```

**Missing pagination:**
```python
# BAD: Returns unbounded results
@app.get("/users")
def list_users():
    return User.query.all()  # what if there are 5 million users?

# GOOD: Always paginate
@app.get("/users")
def list_users(page: int = 1, per_page: int = 50):
    return User.query.paginate(page=page, per_page=per_page)
```

**The performance checklist:**
```
□ QUERIES: No N+1 patterns? Eager loading where needed?
□ MEMORY: No unbounded data loading? Streaming/pagination used?
□ ALGORITHMS: No hidden O(n^2)? Using sets/dicts for lookups?
□ I/O: Async where network calls are made? Connection pooling?
□ PAGINATION: All list endpoints paginated?
□ INDEXES: Columns used in WHERE/JOIN have database indexes?
□ CACHING: Repeated expensive computations cached?
```

**The meta-principle:** Code that works is not the same as code that scales. Every code suggestion should be mentally tested at 1000x the expected load. If it breaks at scale, flag it and show the scalable alternative.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
