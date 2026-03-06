"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 3)
Scenarios: Security holes in own security code, Performance antipatterns
"""

PAIRS = [
    (
        "thinking/meta-error-broken-csrf-protection",
        r'''I wrote this CSRF protection middleware for my Express app:

```javascript
const csrf = require('csurf');

app.use(csrf({ cookie: true }));

app.post('/api/transfer', (req, res) => {
  const { to, amount } = req.body;
  // CSRF token checked by middleware
  transferFunds(req.user.id, to, amount);
  res.json({ success: true });
});

// For the SPA frontend
app.get('/api/csrf-token', (req, res) => {
  res.json({ csrfToken: req.csrfToken() });
});
```

Is this CSRF protection correctly implemented?''',
        r'''<think>
Let me critically examine this CSRF protection...

First, the middleware setup: `csrf({ cookie: true })` — this uses cookie-based CSRF tokens. That means the CSRF secret is stored in a cookie rather than in the server session. Is that a problem?

Actually, yes. With `cookie: true`, the CSRF secret is stored in a cookie. The CSRF token is derived from this secret. But if an attacker can read the cookie (via XSS, subdomain attack, etc.), they can forge valid CSRF tokens. Cookie-based CSRF is weaker than session-based.

But there's a bigger issue. Look at the `/api/csrf-token` endpoint — it returns the CSRF token via a GET JSON endpoint. Any origin can make GET requests and if CORS is misconfigured (or if the API uses `Access-Control-Allow-Origin: *`), any page can fetch the CSRF token.

Wait, actually even without CORS issues, there's still the fundamental question: is the CSRF token being validated on the POST? The middleware should handle that... but only if the token is being SENT by the client. How does the SPA send it? The code doesn't show the client-side implementation. If the SPA stores the token in a JavaScript variable and sends it as a header, that's fine. But if there's an XSS vulnerability, the attacker can just fetch `/api/csrf-token` and get a valid token.

Let me re-examine: the real security hole is that `/api/csrf-token` has no authentication check. An unauthenticated request can get a CSRF token. Combined with `cookie: true`, an attacker on a sibling subdomain can:
1. Visit `/api/csrf-token` to get a valid token
2. Set the CSRF cookie on the victim's browser (cookie tossing from subdomain)
3. Submit a POST with the known token

My error was presenting this as "secured" when the cookie-based approach plus an open token endpoint creates an exploitable chain. The proper approach is session-based CSRF tokens.
</think>

**This CSRF protection has several security weaknesses that could be exploited.**

### Issue 1: Cookie-based CSRF is vulnerable to subdomain attacks
```javascript
// WEAK: cookie-based CSRF
app.use(csrf({ cookie: true }));

// BETTER: session-based CSRF
app.use(session({ secret: process.env.SESSION_SECRET, ... }));
app.use(csrf()); // defaults to session storage
```

With `cookie: true`, the CSRF secret is stored in a cookie. An attacker on a sibling subdomain (e.g., `evil.example.com`) can perform cookie tossing — setting the CSRF cookie on the parent domain, then using a known secret to forge valid tokens.

### Issue 2: Open CSRF token endpoint
```javascript
// DANGEROUS: anyone can get a valid token
app.get('/api/csrf-token', (req, res) => {
  res.json({ csrfToken: req.csrfToken() });
});

// BETTER: require authentication, set via cookie instead
app.get('/api/csrf-token', requireAuth, (req, res) => {
  res.cookie('XSRF-TOKEN', req.csrfToken(), {
    httpOnly: false, // JS needs to read it
    secure: true,
    sameSite: 'Strict'
  });
  res.status(204).end();
});
```

### Issue 3: Missing SameSite cookie attribute
The `csurf` cookie should use `SameSite=Strict` or `Lax` as defense-in-depth:
```javascript
app.use(csrf({
  cookie: {
    httpOnly: true,
    secure: true,
    sameSite: 'Strict'
  }
}));
```

### The meta-lesson
Security code that *looks* correct can have subtle interaction vulnerabilities. Each piece (middleware, token endpoint, cookie config) seems fine alone, but the combination creates an exploitable chain. Always threat-model the full flow, not individual components.'''
    ),
    (
        "thinking/meta-error-timing-attack-comparison",
        r'''I wrote this API key validation function:

```python
import hashlib

def validate_api_key(provided_key: str, stored_hash: str) -> bool:
    """Validate an API key against its stored hash."""
    provided_hash = hashlib.sha256(provided_key.encode()).hexdigest()
    return provided_hash == stored_hash
```

Is this secure?''',
        r'''<think>
Let me examine this API key validation...

The function hashes the provided key with SHA-256 and compares the hex digest to a stored hash. Seems straightforward.

Wait — there's a timing attack vulnerability. Python's `==` operator for strings does a byte-by-byte comparison and returns `False` as soon as it finds the first differing byte. This means:
- If the first character differs: returns in ~1 comparison
- If first 10 characters match: returns in ~10 comparisons

An attacker can measure the response time to figure out how many leading characters of the hash match, then brute-force character by character. This is a classic timing side-channel attack.

The fix is to use `hmac.compare_digest()` which does constant-time comparison.

Also, I should question whether SHA-256 alone is appropriate for hashing API keys. API keys are typically high-entropy random strings, so unlike passwords, they don't need bcrypt/argon2. SHA-256 is fine for API keys. So that part is correct.

But there's another subtlety: no salt. For API keys, salting isn't strictly necessary if the keys are high-entropy random strings (they're not vulnerable to rainbow tables like passwords). But it's still good practice.

My main error: the `==` comparison is vulnerable to timing attacks. This is a common mistake because the code looks perfectly logical, and in most contexts `==` is fine. But in security-sensitive comparisons, constant-time comparison is mandatory.
</think>

**The code has a timing attack vulnerability in the string comparison.**

### The vulnerability
```python
# VULNERABLE: == does early-exit comparison
return provided_hash == stored_hash
```

Python's `==` on strings compares byte-by-byte and returns `False` at the first mismatch. An attacker can measure response times to deduce how many leading characters of the hash match, then brute-force the hash incrementally.

### The fix
```python
import hashlib
import hmac

def validate_api_key(provided_key: str, stored_hash: str) -> bool:
    """Validate an API key against its stored hash."""
    provided_hash = hashlib.sha256(provided_key.encode()).hexdigest()
    return hmac.compare_digest(provided_hash, stored_hash)
```

`hmac.compare_digest()` performs constant-time comparison — it always examines every byte regardless of where differences occur, preventing timing side-channels.

### Why SHA-256 is fine here (but wouldn't be for passwords)
API keys are typically 32+ bytes of random data — high entropy. They don't need slow hashing (bcrypt/argon2) because they're not vulnerable to dictionary attacks. SHA-256 is appropriate for API key hashing.

### The meta-lesson
Security code that is *logically* correct can still be vulnerable through side channels. The `==` operator gives the right boolean answer every time — the bug is in the *timing* of that answer, not its correctness. Always use constant-time comparison for security-sensitive values.'''
    ),
    (
        "thinking/meta-error-false-optimization-list-concat",
        r'''I optimized this Python function that builds a result list:

```python
# Original (slow)
def collect_results(items):
    results = []
    for item in items:
        if item.is_valid():
            results.append(item.transform())
    return results

# My "optimized" version
def collect_results_fast(items):
    results = []
    for item in items:
        if item.is_valid():
            results = results + [item.transform()]
    return results
```

I thought using `+` might be faster because it avoids method lookup overhead. Was I right?''',
        r'''<think>
Let me analyze this "optimization"...

The original uses `results.append(item.transform())`.
The "optimized" version uses `results = results + [item.transform()]`.

Wait, this is actually a PESSIMIZATION, not an optimization!

`append()` is O(1) amortized — it modifies the list in place, occasionally resizing the internal array (which is amortized constant time).

`results = results + [item.transform()]` creates a BRAND NEW list every iteration. It:
1. Creates a new single-element list `[item.transform()]` — O(1)
2. Concatenates `results` with this new list — O(n) where n is the current length of results
3. Assigns the new list to `results` — O(1)
4. The old `results` list becomes garbage — GC overhead

So for n valid items, the total cost is O(1 + 2 + 3 + ... + n) = O(n²).

The original `append` version is O(n) total. My "optimization" turned an O(n) algorithm into O(n²)!

The reasoning about "method lookup overhead" is completely wrong in priority. Method lookup is a tiny constant factor — nanoseconds. Creating a new list of growing size each iteration is a massive algorithmic regression.

This is a classic case of micro-optimization thinking (saving nanoseconds on method dispatch) while introducing a macro-pessimization (changing algorithmic complexity).

If I really wanted to optimize, the best version is a list comprehension:
```python
results = [item.transform() for item in items if item.is_valid()]
```
This is faster than even the `append` version because list comprehensions have optimized bytecode in CPython.
</think>

**This is actually a severe pessimization — the "optimized" version is O(n²) instead of O(n).**

### Why it's slower
```python
# O(1) amortized — modifies list in place
results.append(item.transform())

# O(n) per call — creates a NEW list every iteration!
results = results + [item.transform()]
```

Each `results + [new_item]` copies the entire existing list into a new list. As `results` grows, each iteration copies more data:
- Iteration 1: copy 1 element
- Iteration 100: copy 100 elements
- Iteration 10000: copy 10000 elements
- Total: 1 + 2 + ... + n = **O(n²)**

### Benchmark proof
```python
import time

items = list(range(100_000))

# append: ~0.01 seconds
results = []
for x in items:
    results.append(x)

# concatenation: ~30+ seconds (or MemoryError)
results = []
for x in items:
    results = results + [x]
```

### The actually fast version
```python
def collect_results_fast(items):
    return [item.transform() for item in items if item.is_valid()]
```

List comprehensions are faster than even `append` loops because CPython has optimized bytecode (`LIST_APPEND`) for them.

### The meta-lesson
Micro-optimization thinking ("save method lookup overhead") can blind you to macro-pessimizations (changing O(n) to O(n²)). Always reason about algorithmic complexity before worrying about constant factors. A nanosecond saved per call means nothing if you're making n extra calls.'''
    ),
    (
        "thinking/meta-error-cache-without-invalidation",
        r'''I added caching to speed up my user profile endpoint:

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_user_profile(user_id: int) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "last_login": str(user.last_login)
    }

@app.put("/api/users/{user_id}")
def update_user(user_id: int, data: dict):
    user = db.query(User).filter(User.id == user_id).first()
    user.name = data.get("name", user.name)
    user.email = data.get("email", user.email)
    db.commit()
    return {"success": True}
```

Should I be concerned about anything with this caching approach?''',
        r'''<think>
Let me analyze this caching setup...

`@lru_cache` on `get_user_profile` — this caches the result in memory keyed by `user_id`. First call hits the database, subsequent calls return the cached dict.

But look at `update_user` — it updates the user in the database but NEVER invalidates the cache! After an update, `get_user_profile` will keep returning the stale cached data until either:
1. The process restarts
2. The entry gets evicted (LRU when cache is full with 1000 entries)

This means a user changes their name, but the API keeps showing the old name. That's a serious bug.

But there are MORE problems with this approach:

1. `lru_cache` is process-local. If you run multiple workers (gunicorn with 4 workers), each has its own cache. A request that hits worker 1 might see different data than one hitting worker 2.

2. `lru_cache` stores results in memory and has no TTL. The cache entries live forever (until eviction). For a long-running server, this means data can be stale for hours or days.

3. `lru_cache` is not thread-safe for cache operations in all Python versions (it is in CPython 3.8+ due to GIL, but implementation-dependent).

4. The cached dict is mutable. If any caller modifies the returned dict, it modifies the cached copy too, affecting all subsequent calls. This is a subtle shared-state bug.

My error: I treated caching as a simple decorator problem ("just add @lru_cache") without considering cache invalidation, multi-process deployment, TTL, or mutable return values. The famous quote applies: "There are only two hard things in CS: cache invalidation and naming things."
</think>

**This cache has multiple serious issues, the most critical being no invalidation on updates.**

### Issue 1: Stale data after updates (the critical bug)
```python
# update_user modifies DB but never invalidates cache!
def update_user(user_id: int, data: dict):
    user.name = data.get("name", user.name)
    db.commit()
    # get_user_profile(user_id) still returns OLD data!
```

Fix:
```python
def update_user(user_id: int, data: dict):
    user = db.query(User).filter(User.id == user_id).first()
    user.name = data.get("name", user.name)
    user.email = data.get("email", user.email)
    db.commit()
    # Invalidate the cache for this user
    get_user_profile.cache_clear()  # nuclear option
    # Or better: can't selectively invalidate with lru_cache
    return {"success": True}
```

### Issue 2: `lru_cache` can't selectively invalidate
You can only call `cache_clear()` (clears ALL entries) or `cache_info()`. You can't invalidate a single key. For selective invalidation, use a proper cache:

```python
from cachetools import TTLCache

profile_cache = TTLCache(maxsize=1000, ttl=300)  # 5 min TTL

def get_user_profile(user_id: int) -> dict:
    if user_id in profile_cache:
        return profile_cache[user_id].copy()  # return copy!
    user = db.query(User).filter(User.id == user_id).first()
    result = {"id": user.id, "name": user.name, ...}
    profile_cache[user_id] = result
    return result.copy()

def update_user(user_id: int, data: dict):
    # ... update DB ...
    profile_cache.pop(user_id, None)  # selective invalidation
```

### Issue 3: Mutable return value
`lru_cache` caches the exact dict object. If any caller does `profile["name"] = "hacked"`, it mutates the cached copy:
```python
profile = get_user_profile(42)
profile["name"] = "oops"  # corrupts cache for ALL callers!
```

### Issue 4: Process-local cache
With multiple workers (gunicorn, uvicorn), each process has its own `lru_cache`. Worker 1 might cache user A, worker 2 might not. Updates via worker 1 don't invalidate worker 2's cache. For multi-process apps, use Redis or memcached.

### The meta-lesson
Caching is never "just add a decorator." Every cache needs an invalidation strategy, a TTL policy, and consideration for deployment topology (single process vs. multi-process vs. multi-server). The two hardest problems in CS: cache invalidation, naming things, and off-by-one errors.'''
    ),
    (
        "thinking/meta-error-race-condition-check-then-act",
        r'''I wrote this file upload handler that prevents duplicate filenames:

```python
import os
import shutil

def save_upload(upload_file, upload_dir: str) -> str:
    filename = upload_file.filename
    dest_path = os.path.join(upload_dir, filename)

    # Check if file already exists
    if os.path.exists(dest_path):
        # Add number suffix to avoid collision
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(upload_dir, f"{base}_{counter}{ext}")
            counter += 1

    # Save the file
    with open(dest_path, 'wb') as f:
        shutil.copyfileobj(upload_file.file, f)

    return dest_path
```

Is this approach to handling duplicate filenames correct?''',
        r'''<think>
Let me analyze this file upload handler...

The logic is: check if the filename exists, if so keep incrementing a counter until we find an unused name, then write to that path.

This is a classic TOCTOU (Time-of-Check-Time-of-Use) race condition!

Between the `os.path.exists(dest_path)` check returning `False` and the `open(dest_path, 'wb')` call, another concurrent request could:
1. Also check the same `dest_path` and find it doesn't exist
2. Write to it first
3. Then THIS request overwrites it

With a web server handling concurrent uploads, two users uploading "report.pdf" at the same time could both get past the existence check and one silently overwrites the other.

The fix is to use atomic file creation — `os.open()` with `O_CREAT | O_EXCL` flags, which atomically checks for existence AND creates the file in one kernel call. If the file exists, it raises `FileExistsError`.

There's also a minor issue: the counter loop itself has the same TOCTOU problem. Even with the incrementing counter, two concurrent requests could both find `report_1.pdf` doesn't exist and both try to write to it.

Another concern: `upload_file.filename` comes from user input. A malicious user could send `../../etc/passwd` as the filename, leading to path traversal. The code doesn't sanitize the filename at all.

So there are actually two bugs:
1. TOCTOU race condition on file creation
2. Path traversal vulnerability via unsanitized filename
</think>

**This code has a TOCTOU race condition and a path traversal vulnerability.**

### Bug 1: Race condition (TOCTOU)
```python
# Thread A: os.path.exists("report.pdf") → False
# Thread B: os.path.exists("report.pdf") → False  (concurrent!)
# Thread A: open("report.pdf", 'wb') → creates file
# Thread B: open("report.pdf", 'wb') → OVERWRITES Thread A's file!
```

There's a gap between checking `os.path.exists()` and `open()`. Concurrent requests can both pass the check and one silently overwrites the other.

**Fix with atomic file creation:**
```python
import os
import uuid
from werkzeug.utils import secure_filename

def save_upload(upload_file, upload_dir: str) -> str:
    # Sanitize filename to prevent path traversal
    filename = secure_filename(upload_file.filename)
    if not filename:
        filename = "unnamed"

    base, ext = os.path.splitext(filename)
    dest_path = os.path.join(upload_dir, filename)

    # Atomic create — fails if file exists, no race window
    for attempt in range(100):
        try:
            fd = os.open(dest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, 'wb') as f:
                shutil.copyfileobj(upload_file.file, f)
            return dest_path
        except FileExistsError:
            dest_path = os.path.join(upload_dir, f"{base}_{attempt + 1}{ext}")

    # Fallback: UUID guarantees uniqueness
    dest_path = os.path.join(upload_dir, f"{base}_{uuid.uuid4().hex[:8]}{ext}")
    with open(dest_path, 'wb') as f:
        shutil.copyfileobj(upload_file.file, f)
    return dest_path
```

`O_CREAT | O_EXCL` atomically creates the file only if it doesn't exist — the check and creation happen in a single kernel syscall with no race window.

### Bug 2: Path traversal
```python
# Attacker uploads with filename: "../../etc/cron.d/backdoor"
filename = upload_file.filename  # UNSANITIZED!
dest_path = os.path.join(upload_dir, filename)
# dest_path = "/uploads/../../etc/cron.d/backdoor" = "/etc/cron.d/backdoor"
```

Always sanitize with `secure_filename()` or at minimum strip path separators and verify the resolved path is within `upload_dir`.

### The meta-lesson
"Check-then-act" patterns are almost always race conditions when concurrent access is possible. Any time you see `if not exists → create` or `if not locked → lock`, look for the TOCTOU window. The fix is always atomic operations: `O_EXCL` for files, `SETNX` for Redis, `INSERT ... ON CONFLICT` for databases.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
