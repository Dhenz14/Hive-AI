"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 22)"""

PAIRS = [
    (
        "thinking/firstprinciples-why-authentication-tokens",
        "Why do we use JWT tokens for authentication? Why not just send the username and password with every request?",
        r'''<think>
Why tokens exist instead of sending credentials every request.

**What happens if you send username/password with every request:**
1. Password sent over the network on EVERY request (more exposure = more risk)
2. Server must verify password on EVERY request (hash comparison is intentionally slow: ~100ms for bcrypt)
3. If any request is intercepted, attacker has the actual password (not just a session)
4. Can't revoke access without changing the password
5. Can't have different permission levels per session
6. Third-party apps would need your actual password

**What tokens solve:**
1. Password sent ONCE (at login) → receive a token
2. Token sent on subsequent requests (token verification is fast: ~1ms for JWT)
3. If token is intercepted, attacker has temporary access (token expires)
4. Can revoke tokens without changing password
5. Tokens can encode permissions (scopes)
6. Third-party apps get tokens, never see your password

**JWT specifically:**
- Self-contained: contains user ID, expiry, permissions
- Stateless: server doesn't need to store session state
- Verifiable: cryptographic signature proves it wasn't tampered with
</think>

Sending the password every time is like showing your birth certificate at every door in a building. A token is like a visitor badge — issued once, verified quickly, expires automatically.

## The Problems With Sending Passwords Every Request

```
REQUEST 1: GET /api/profile     Authorization: Basic dXNlcjpwYXNzd29yZA==
REQUEST 2: GET /api/orders      Authorization: Basic dXNlcjpwYXNzd29yZA==
REQUEST 3: POST /api/comment    Authorization: Basic dXNlcjpwYXNzd29yZA==
... 50 more requests per session

PROBLEM 1: PASSWORD EXPOSURE
  Your password crosses the network 50 times instead of once.
  Each transmission is an opportunity for interception.
  If ANY request is captured → attacker has your ACTUAL PASSWORD
  → they can log into your bank, email, everything (password reuse)

PROBLEM 2: PERFORMANCE
  Password verification is intentionally SLOW (bcrypt: ~100ms)
  Why slow? To prevent brute-force attacks.
  50 requests × 100ms = 5 SECONDS of CPU time just for auth.
  Token verification: 50 × 1ms = 50ms. That's 100x faster.

PROBLEM 3: NO REVOCATION
  User's phone is stolen. How do you lock them out?
  With password: change the password (disrupts all devices)
  With tokens: revoke the token (other devices keep working)

PROBLEM 4: THIRD-PARTY ACCESS
  "Log in with Google" on a third-party app.
  With passwords: give your Google password to the app ← TERRIBLE
  With tokens: Google gives the app a limited token ← safe
```

## How Tokens Work

```
STEP 1: LOGIN (password sent ONCE)
  POST /auth/login
  Body: {"email": "dan@example.com", "password": "s3cure!"}
  Server: verify password (slow, ~100ms, but only once)
  Response: {"token": "eyJhbGciOiJIUzI1NiIs..."}

STEP 2: ALL SUBSEQUENT REQUESTS (token sent, fast)
  GET /api/profile
  Header: Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
  Server: verify token signature (fast, ~1ms)
  Response: {"name": "Dan", ...}

THE TOKEN CONTAINS:
  {
    "user_id": 42,
    "email": "dan@example.com",
    "role": "admin",
    "exp": 1709654400,        ← expires in 1 hour
    "iat": 1709650800          ← issued at
  }
  + cryptographic signature (proves server issued it, not tampered)
```

## In Code

```python
import jwt
from datetime import datetime, timedelta

SECRET_KEY = "your-256-bit-secret"

# LOGIN: verify password once, issue token
@app.post("/auth/login")
async def login(email: str, password: str):
    user = await db.get_user_by_email(email)
    if not user or not bcrypt.checkpw(password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")

    # Create token (contains user info + expiry)
    token = jwt.encode({
        "user_id": user.id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }, SECRET_KEY, algorithm="HS256")

    return {"token": token}

# EVERY OTHER REQUEST: verify token (fast, no database hit)
async def get_current_user(authorization: str = Header()):
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload  # {"user_id": 42, "role": "admin"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")

@app.get("/api/profile")
async def get_profile(user=Depends(get_current_user)):
    return await db.get_user(user["user_id"])
```

## The Key Properties

```
PASSWORD:
  - Permanent (doesn't expire)
  - One per user (shared across all sessions)
  - Slow to verify (by design)
  - If stolen → full account compromise
  - Can't scope permissions ("read-only password" doesn't exist)

TOKEN:
  - Temporary (expires in hours/days)
  - Many per user (one per session/device)
  - Fast to verify (cryptographic signature check)
  - If stolen → limited damage (expires soon, can be revoked)
  - Can scope permissions (read-only token, admin token)
```

**Login once, get a badge, show the badge everywhere.** Don't show your birth certificate at every door.'''
    ),
    (
        "thinking/causal-memory-leak-python-django",
        "Our Django app's memory usage grows from 200MB to 1.5GB over a few days, then the OOM killer terminates it. We restart and it happens again. How do I find the leak?",
        r'''<think>
Django/Python memory leak growing over days. Let me reason through the most common causes.

**Python-specific memory leak causes:**

1. **Global/module-level caches growing unbounded**
   - Django's `get_language()` or custom caching dicts
   - QuerySet results stored in module-level variables
   - Memoization decorators without size limits

2. **Django-specific leaks:**
   - DEBUG=True in production: Django stores EVERY SQL query in `django.db.connection.queries`
   - Signals with strong references to objects
   - Middleware storing data on request objects that aren't cleaned up
   - File upload handling not closing file handles

3. **C extension leaks**
   - Libraries like PIL/Pillow, lxml, numpy can leak memory in C code
   - Python's GC doesn't see C-allocated memory

4. **Circular references with __del__**
   - Objects with circular references AND `__del__` methods can't be GC'd

5. **Thread-local storage**
   - Data stored in threading.local() that grows per thread

**Most likely for Django: DEBUG=True in production**
This is the #1 cause. With DEBUG=True, Django logs every SQL query to memory. After millions of queries over days → gigabytes of stored query strings.

**Second most likely: unbounded caches**
</think>

The #1 cause of Django memory leaks is embarrassingly simple: **DEBUG=True in production**.

## Check This First (60% of Django Memory Leaks)

```python
# settings.py — check IMMEDIATELY
DEBUG = True  # ← THIS IS YOUR LEAK

# When DEBUG=True, Django stores EVERY SQL query in memory:
from django.db import connection
len(connection.queries)  # After 1 day: 500,000 queries stored in RAM
# Each query: ~1KB → 500MB of just query logs

# FIX:
DEBUG = False  # In production, ALWAYS
```

```bash
# Verify in production:
python manage.py shell -c "from django.conf import settings; print(settings.DEBUG)"
# If this prints True → that's your leak
```

## If DEBUG Is Already False: Find the Real Leak

```python
# Add memory profiling to find what's growing

# 1. Track memory over time (add to a management command or middleware)
import tracemalloc
import gc

# Start tracing
tracemalloc.start()

# Take snapshots at intervals
@app.middleware
def memory_middleware(get_response):
    def middleware(request):
        response = get_response(request)

        # Log memory every 1000 requests
        if random.random() < 0.001:
            snapshot = tracemalloc.take_snapshot()
            top = snapshot.statistics('lineno')[:10]
            for stat in top:
                logger.info(f"Memory: {stat}")

        return response
    return middleware
```

## Common Django Memory Leaks

```python
# 1. UNBOUNDED CACHES (module-level dicts that grow forever)
# ❌ LEAK:
_cache = {}  # Module-level, never evicted

def get_user_data(user_id):
    if user_id not in _cache:
        _cache[user_id] = expensive_query(user_id)
    return _cache[user_id]
# After 100K unique users → hundreds of MB in _cache

# ✅ FIX: use LRU cache with max size
from functools import lru_cache

@lru_cache(maxsize=1000)  # Bounded! Evicts old entries
def get_user_data(user_id):
    return expensive_query(user_id)

# Or use Django's cache framework (backed by Redis, not RAM)
from django.core.cache import cache
cache.set(f"user:{user_id}", data, timeout=300)


# 2. QUERYSETS EVALUATED IN MODULE SCOPE
# ❌ LEAK: QuerySet evaluated once, result stored forever
ALL_PRODUCTS = list(Product.objects.all())  # Loaded at import time
# Never refreshed, holds references to thousands of model instances

# ✅ FIX: evaluate in function scope
def get_all_products():
    return Product.objects.all()  # Fresh query each time


# 3. SIGNAL HANDLERS WITH STRONG REFERENCES
# ❌ LEAK: lambda/closure captures objects that should be freed
from django.db.models.signals import post_save

def register_handlers(some_large_object):
    # This closure captures some_large_object permanently
    post_save.connect(lambda sender, **kw: some_large_object.process(kw))

# ✅ FIX: use weak references or class-based handlers
from django.dispatch import receiver

@receiver(post_save, sender=MyModel)
def handle_save(sender, instance, **kwargs):
    # No captured variables, no leak
    process(instance)


# 4. FILE HANDLES NOT CLOSED
# ❌ LEAK: file handles accumulate
def process_upload(uploaded_file):
    data = uploaded_file.read()
    # uploaded_file never closed explicitly
    process(data)

# ✅ FIX: use context manager
def process_upload(uploaded_file):
    with uploaded_file.open() as f:
        data = f.read()
    process(data)
```

## Diagnostic Commands

```bash
# Check current memory usage by object type
python manage.py shell -c "
import gc, sys
gc.collect()
types = {}
for obj in gc.get_objects():
    t = type(obj).__name__
    types[t] = types.get(t, 0) + 1
for t, c in sorted(types.items(), key=lambda x: -x[1])[:20]:
    print(f'{t}: {c}')
"

# If you see millions of dict, str, or specific model objects → that's the leak
# Look for: which code path creates these objects without releasing them?
```

Start with `DEBUG=False`. If that doesn't fix it, add `tracemalloc` to find which code path is accumulating objects.'''
    ),
    (
        "thinking/analogy-git-branching-parallel-universes",
        "I don't understand Git branches. Why would I create a branch instead of just editing the code directly?",
        r'''<think>
Git branches — the parallel universe analogy works perfectly here.

Without branches: you're editing the one copy of reality. If you mess up, everyone is affected.

With branches: you create a parallel universe where you can experiment. If it works, merge it back. If not, delete the universe. The original reality was never affected.

Key concepts to explain:
1. main branch = the "real world" / production reality
2. Feature branch = parallel universe for experimenting
3. Merge = bringing changes from parallel universe back to reality
4. Delete branch = discarding a failed experiment, no harm done
</think>

Think of Git branches as **parallel universes**.

## The Analogy

```
WITHOUT BRANCHES (editing directly):
  There's ONE reality. You start changing things.
  You're halfway through a risky change when...
  → Boss: "There's a critical bug in production! Fix it NOW!"
  → Your half-finished feature is mixed with the working code
  → You can't deploy the fix without the broken half-feature
  → Panic. Manually undo changes. Hope you remember what to revert.

WITH BRANCHES (parallel universes):
  MAIN = the "real world" (production, always working)
  YOUR BRANCH = a parallel universe where you experiment

  → You create a parallel universe: git checkout -b new-feature
  → You experiment freely (break things, try ideas)
  → Boss: "Critical bug! Fix it now!"
  → Switch back to the real world: git checkout main
  → The real world is clean, untouched by your experiment
  → Fix the bug in the real world, deploy it
  → Switch back to your experiment: git checkout new-feature
  → Continue where you left off
  → Experiment works? Merge it into reality: git merge new-feature
  → Experiment failed? Delete the universe: git branch -d new-feature
  → The real world was never affected by the failed experiment
```

## In Practice

```bash
# The "real world" — always works, always deployable
# main branch: your-app.com is running this code

# CREATE A PARALLEL UNIVERSE for your feature
git checkout -b add-dark-mode
# You're now in a parallel universe
# Changes here don't affect main AT ALL

# Work on dark mode...
git add .
git commit -m "Add dark mode toggle"
git commit -m "Style all components for dark theme"
git commit -m "Add dark mode preference to user settings"

# MEANWHILE: critical bug reported on production
git checkout main        # ← switch back to the real world
git checkout -b fix-login-bug
# Fix the bug in ANOTHER parallel universe
git add .
git commit -m "Fix login bug for Safari users"
git checkout main
git merge fix-login-bug  # ← bring the fix into reality
# Deploy the fix. Production is fixed. Dark mode work unaffected.

# BACK TO YOUR FEATURE
git checkout add-dark-mode  # ← back to dark mode universe
# Continue working...
# Done? Merge into reality:
git checkout main
git merge add-dark-mode  # ← dark mode now exists in the real world
```

## Visual Map

```
main:        A ── B ── C ──────── F ── G ── H ──── K
                        \        /              \  /
fix-bug:                 D ── E                  |
                          (fix login bug)         |
dark-mode:               D' ── E' ── F' ── G' ── J
                          (dark mode feature)

A-C: existing code (production)
D-E: bug fix (in its own parallel universe)
F: bug fix merged into main (deployed to production)
D'-J: dark mode work (in its own parallel universe)
K: dark mode merged into main (deployed to production)

At no point was main broken.
Bug fix and dark mode were developed independently.
```

## Why This Matters

```
WITHOUT BRANCHES:
  "I'm scared to change this code because if I break it,
   everyone else is affected."
  "I can't work on two things at the same time."
  "I can't experiment because there's no undo."

WITH BRANCHES:
  "I can experiment freely — main is safe."
  "I can switch between features instantly."
  "I can throw away failed experiments with no consequences."
  "Multiple people can work on different features simultaneously."
```

Branches are free and instant in Git. Create one for every feature, bug fix, or experiment. It costs nothing and protects your working code.'''
    ),
    (
        "thinking/abstraction-retry-to-resilience-policy",
        "I have retry logic scattered across my codebase. Every API call has its own try/except with sleep and retry. How do I clean this up?",
        r'''<think>
Scattered retry logic — let me ladder from concrete to abstract.

**Concrete: duplicated try/except retry loops**
Every API call has 10 lines of retry boilerplate. This is the DRY violation.

**Pattern: retry decorator/wrapper**
Extract the retry logic into a reusable decorator. One implementation, applied everywhere.

**Principle: cross-cutting concerns as decorators/middleware**
Retry is a cross-cutting concern. Other cross-cutting concerns:
- Timeout
- Circuit breaker
- Logging
- Metrics
- Rate limiting

All of these should be separated from business logic.

**Policy: resilience as composable policies**
Stack these together: timeout → retry → circuit breaker → fallback
</think>

Extract the repeated pattern into a reusable decorator, then compose it into a resilience policy.

## Level 1: Concrete — Your Current Problem

```python
# ❌ BEFORE: retry logic duplicated in every API call
def get_user(user_id):
    for attempt in range(3):
        try:
            response = requests.get(f"{API_URL}/users/{user_id}", timeout=5)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
            logger.warning(f"Retry {attempt + 1} for get_user: {e}")

def get_orders(user_id):
    for attempt in range(3):
        try:
            response = requests.get(f"{API_URL}/orders?user={user_id}", timeout=5)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
            logger.warning(f"Retry {attempt + 1} for get_orders: {e}")

# ... repeated 20 more times. Same logic. Same bugs if you fix one and miss another.
```

## Level 2: Pattern — Retry Decorator

```python
# ✅ AFTER: extract once, use everywhere
import time
import functools
import logging

logger = logging.getLogger(__name__)

def retry(max_attempts=3, backoff_base=2, retryable_exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    if attempt == max_attempts - 1:
                        raise
                    wait = backoff_base ** attempt
                    logger.warning(
                        f"Retry {attempt + 1}/{max_attempts} for {func.__name__}: {e}. "
                        f"Waiting {wait}s"
                    )
                    time.sleep(wait)
        return wrapper
    return decorator

# Clean API calls — no retry boilerplate
@retry(max_attempts=3, retryable_exceptions=(requests.ConnectionError, requests.Timeout))
def get_user(user_id):
    response = requests.get(f"{API_URL}/users/{user_id}", timeout=5)
    response.raise_for_status()
    return response.json()

@retry(max_attempts=3, retryable_exceptions=(requests.ConnectionError, requests.Timeout))
def get_orders(user_id):
    response = requests.get(f"{API_URL}/orders?user={user_id}", timeout=5)
    response.raise_for_status()
    return response.json()
```

## Level 3: Principle — Use a Battle-Tested Library

```python
# Don't reinvent retry logic — use tenacity
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    before_sleep=lambda state: logger.warning(f"Retry {state.attempt_number}")
)
def get_user(user_id):
    response = requests.get(f"{API_URL}/users/{user_id}", timeout=5)
    response.raise_for_status()
    return response.json()
```

## Level 4: Policy — Composable Resilience

```python
# Stack multiple resilience patterns together
from tenacity import retry, stop_after_attempt, wait_exponential
import pybreaker

# Circuit breaker: stop trying if the service is DOWN
user_service_breaker = pybreaker.CircuitBreaker(
    fail_max=5,           # Open after 5 failures
    reset_timeout=60,     # Try again after 60 seconds
)

# Compose: timeout → retry → circuit breaker
@user_service_breaker
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def get_user(user_id):
    response = requests.get(f"{API_URL}/users/{user_id}", timeout=5)
    response.raise_for_status()
    return response.json()

# With fallback:
def get_user_safe(user_id):
    try:
        return get_user(user_id)
    except (pybreaker.CircuitBreakerError, requests.RequestException):
        return get_cached_user(user_id)  # Degraded but functional

# THE RESILIENCE STACK:
#   Request → TIMEOUT(5s)
#           → RETRY(3 attempts, exponential backoff)
#           → CIRCUIT BREAKER(5 failures → open for 60s)
#           → FALLBACK(return cached data)
```

The ladder: duplicated try/except → retry decorator → battle-tested library → composable resilience policies. Each level removes more boilerplate and adds more reliability.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
