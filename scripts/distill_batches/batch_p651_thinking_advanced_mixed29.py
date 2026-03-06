"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 29)"""

PAIRS = [
    (
        "thinking/adversarial-path-traversal",
        "I let users specify a filename to download: /download?file=report.pdf. I serve it from a static directory. Is this safe?",
        r'''<think>
Path traversal vulnerability. If the user controls the filename and it's used to read from the filesystem, they can escape the intended directory.

**The attack:**
/download?file=../../../etc/passwd
→ Server reads: /static/files/../../../etc/passwd = /etc/passwd
→ Attacker gets the system's password file

/download?file=../../.env
→ Server reads: /static/files/../../.env = project root .env
→ Attacker gets database credentials, API keys

**Variations:**
- ../ → basic path traversal
- ..\ → Windows path traversal
- %2e%2e%2f → URL-encoded ../
- ....// → double encoding to bypass naive filters
- /download?file=/etc/passwd → absolute path
</think>

**No. This is a path traversal vulnerability.** An attacker can read ANY file on your server.

## The Attack

```
YOUR CODE:
  /download?file=report.pdf
  → Server reads: /static/files/report.pdf → serves it ✓

ATTACKER'S REQUEST:
  /download?file=../../../etc/passwd
  → Server reads: /static/files/../../../etc/passwd
  → Resolves to: /etc/passwd
  → Attacker gets system user list

  /download?file=../../.env
  → Resolves to: /app/.env
  → Attacker gets: DATABASE_URL, SECRET_KEY, API keys

  /download?file=../../app/settings.py
  → Attacker gets: your source code, configuration, secrets

  /download?file=../../../home/deploy/.ssh/id_rsa
  → Attacker gets: SSH private key → can access your servers
```

## The Fix

```python
import os
from pathlib import Path

STATIC_DIR = Path("/app/static/files").resolve()

# ❌ VULNERABLE: no validation
@app.get("/download")
def download(file: str):
    return send_file(f"/app/static/files/{file}")

# ✅ FIXED: resolve path and verify it's within the allowed directory
@app.get("/download")
def download(file: str):
    # Resolve the full path (follows ../ etc.)
    requested_path = (STATIC_DIR / file).resolve()

    # Check that the resolved path is still within STATIC_DIR
    if not requested_path.is_relative_to(STATIC_DIR):
        raise HTTPException(403, "Access denied")

    # Check the file exists
    if not requested_path.is_file():
        raise HTTPException(404, "File not found")

    return send_file(requested_path)
```

## Bypass Attempts Attackers Will Try

```python
# Attacker tries to bypass naive filters:

file = "../../../etc/passwd"       # Basic traversal
file = "..\\..\\..\\etc\\passwd"   # Windows-style
file = "%2e%2e%2f%2e%2e%2f"        # URL-encoded
file = "....//....//etc/passwd"    # Double dots
file = "/etc/passwd"               # Absolute path
file = "report.pdf%00.jpg"         # Null byte injection (older systems)

# ❌ WRONG FIX: string filtering (always bypassable)
def unsafe_filter(filename):
    return filename.replace("../", "")
# "....//etc/passwd" → after replacing "../" → "../etc/passwd" → still works!

# ✅ RIGHT FIX: resolve the full path and check containment
# The .resolve() approach handles ALL bypass attempts
# because it resolves the ACTUAL filesystem path
```

## Safest Approach: Don't Use User Input as Filenames

```python
# ✅ SAFEST: map user input to an ID, not a filename
# Store files with UUIDs, map display names in database

@app.get("/download/{file_id}")
def download(file_id: str):
    # Look up the actual filename from database
    record = db.query("SELECT filepath FROM files WHERE id = %s AND user_id = %s",
                      file_id, current_user.id)
    if not record:
        raise HTTPException(404)

    # filepath is set by YOUR code, not user input
    return send_file(record.filepath)

# User never controls the actual filesystem path
# URL: /download/abc-123 → database lookup → /static/files/report.pdf
```

**Rule:** never use user input directly in filesystem paths. Either resolve and verify containment, or use a database lookup to map user input to actual file paths.'''
    ),
    (
        "thinking/uncertainty-redis-caching-strategy",
        "Should we use Redis for caching or just use our application's in-memory cache? We have a single Django server.",
        r'''<think>
Redis vs in-memory cache for a single-server Django app.

**In-memory cache (e.g., Django's LocMemCache, functools.lru_cache):**
Pros:
- Zero latency (same process, no network)
- No additional infrastructure
- Simple to set up
- No serialization overhead

Cons:
- Lost on restart
- Per-process (if running multiple gunicorn workers, each has its own cache)
- Limited by process memory
- No sharing between services

**Redis:**
Pros:
- Shared across all workers/processes
- Survives app restarts
- Can share between services
- Rich data structures (sorted sets, pub/sub, etc.)
- Built-in expiration

Cons:
- Extra infrastructure (~1ms network latency)
- Serialization overhead
- More complex setup

**For a SINGLE Django server:**
If using a single gunicorn worker: in-memory might be fine
If using multiple gunicorn workers (typical): Redis is better (shared cache)

**Confidence: 65% Redis, 35% in-memory**
Depends heavily on whether they run multiple workers.
</think>

**65% Redis, especially if you run multiple gunicorn workers.** With a single worker, in-memory could be fine.

## The Key Question

```
HOW MANY GUNICORN WORKERS DO YOU RUN?

  gunicorn app:app --workers 1
  → In-memory cache works fine (one process, one cache)

  gunicorn app:app --workers 4  (typical)
  → Each worker has its OWN in-memory cache
  → Cache hit rate drops (same data cached 4 times or not cached at all)
  → User hits worker 1 (cache miss) → cache filled
  → Next request hits worker 3 (different cache) → cache miss again

  WITH REDIS:
  → All 4 workers share ONE cache
  → Cache hit rate is high
  → Data cached once, available to all workers
```

## Comparison

```
                        IN-MEMORY           REDIS
Latency:                ~0.001ms            ~1ms
Extra infrastructure:   None                Redis server
Shared across workers:  No                  Yes
Survives restart:       No                  Yes (with persistence)
Memory limit:           Process RAM         Redis server RAM
Setup complexity:       None                pip install django-redis
Best for:               Single worker,      Multiple workers,
                        simple caching      shared state
```

## Django Configuration

```python
# settings.py

# OPTION 1: In-memory cache (single worker only)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'TIMEOUT': 300,  # 5 minutes default
    }
}

# OPTION 2: Redis (recommended for production)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'TIMEOUT': 300,
    }
}

# Usage is identical for both:
from django.core.cache import cache

# Set
cache.set('user:42', user_data, timeout=300)

# Get
data = cache.get('user:42')
if data is None:
    data = expensive_query()
    cache.set('user:42', data, timeout=300)

# Decorator
from django.views.decorators.cache import cache_page

@cache_page(60 * 5)  # Cache entire page for 5 minutes
def product_list(request):
    ...
```

## My Recommendation

```
SINGLE SERVER + SINGLE WORKER:
  Start with in-memory. It's the simplest.
  Switch to Redis when you add more workers.

SINGLE SERVER + MULTIPLE WORKERS (most common):
  Use Redis. It's $0 extra if running on the same server.
  pip install django-redis, add 3 lines to settings, done.

MULTIPLE SERVERS:
  Redis is mandatory (in-memory cache is per-server).
```

The 35% case for in-memory: you have a single worker, the cached data is small, and you want zero additional dependencies. For everything else, Redis is worth the minimal setup cost.'''
    ),
    (
        "thinking/causal-slow-page-load-waterfall",
        "Our web page takes 8 seconds to load even though the API responds in 200ms. The HTML loads fast but then nothing happens for several seconds before content appears. What's going on?",
        r'''<think>
Page loads fast (HTML in 200ms) but content takes 8 seconds. This is a frontend waterfall problem — the browser is downloading resources sequentially.

**Causal analysis:**
HTML loads fast → so the server is fine
Content appears late → something in the BROWSER is slow
The gap between HTML and content = JavaScript/CSS download + parsing + API calls

**Common causes (in order):**

1. **Large JavaScript bundle** — 5MB of JS that must download and parse before rendering
2. **Render-blocking CSS/JS** — CSS files in <head> block rendering
3. **Waterfall API calls** — component loads → makes API call → child component loads → makes another API call → chain of sequential requests
4. **No code splitting** — entire app downloaded even for one page
5. **Third-party scripts** — analytics, chat widgets, ad scripts blocking rendering
</think>

The page HTML loads in 200ms but content takes 8 seconds → the problem is in the **browser**, not the server. You have a **resource waterfall**.

## The Waterfall Problem

```
WHAT'S HAPPENING IN THE BROWSER:

T=0ms:     Browser receives HTML (fast, 200ms)
T=200ms:   Browser starts parsing HTML
T=200ms:   Finds <link href="styles.css"> → downloads (blocks rendering)
T=500ms:   Finds <script src="bundle.js"> → downloads (blocks rendering)
T=3000ms:  bundle.js downloaded (2.5MB!) → starts executing
T=3500ms:  React initializes → renders loading skeleton
T=3500ms:  Component calls API: fetch('/api/products')
T=3700ms:  API responds → component renders → triggers child components
T=3700ms:  Child component calls API: fetch('/api/categories')
T=3900ms:  Categories loaded → triggers another fetch('/api/reviews')
T=4100ms:  Reviews loaded → page fully rendered
T=4100ms:  Google Fonts download finishes → text appears (FOUT)
T=5000ms:  Analytics, chat widget, social scripts finish loading
T=8000ms:  All third-party scripts done → page feels "ready"

TOTAL: 8 seconds, even though your API is 200ms fast.
```

## Fix 1: Reduce JavaScript Bundle Size

```bash
# Check your bundle size
npx webpack-bundle-analyzer stats.json
# or
npx next build && npx next analyze

# Common findings:
# moment.js: 300KB → use date-fns (20KB) or dayjs (2KB)
# lodash: 70KB → import only what you use: import debounce from 'lodash/debounce'
# Entire icon library: 500KB → import only used icons
# Duplicate dependencies: 2 versions of React in the bundle
```

```javascript
// CODE SPLITTING: load only what the current page needs
// ❌ BEFORE: everything in one bundle
import AdminDashboard from './AdminDashboard'; // 500KB, loaded for ALL users
import Charts from './Charts';                  // 300KB, loaded on every page

// ✅ AFTER: load on demand
const AdminDashboard = React.lazy(() => import('./AdminDashboard'));
const Charts = React.lazy(() => import('./Charts'));
// Downloaded only when the component is actually rendered
```

## Fix 2: Parallelize API Calls

```javascript
// ❌ WATERFALL: sequential API calls
async function loadPage() {
    const products = await fetch('/api/products');   // Wait 200ms
    const categories = await fetch('/api/categories'); // Wait 200ms
    const reviews = await fetch('/api/reviews');       // Wait 200ms
    // Total: 600ms (sequential)
}

// ✅ PARALLEL: all at once
async function loadPage() {
    const [products, categories, reviews] = await Promise.all([
        fetch('/api/products'),      // 200ms  } All three
        fetch('/api/categories'),    // 200ms  } run at the
        fetch('/api/reviews'),       // 200ms  } same time
    ]);
    // Total: 200ms (parallel, limited by slowest)
}
```

## Fix 3: Remove Render-Blocking Resources

```html
<!-- ❌ RENDER-BLOCKING: nothing renders until these download -->
<head>
    <link rel="stylesheet" href="huge-framework.css">  <!-- 200KB, blocks rendering -->
    <script src="analytics.js"></script>                <!-- Blocks parsing -->
    <script src="bundle.js"></script>                   <!-- 2MB, blocks everything -->
</head>

<!-- ✅ OPTIMIZED: critical CSS inline, defer everything else -->
<head>
    <style>
        /* Critical CSS inlined — above-the-fold styles only */
        body { font-family: system-ui; margin: 0; }
        .header { background: #fff; padding: 1rem; }
    </style>
    <link rel="stylesheet" href="styles.css" media="print" onload="this.media='all'">
    <script src="bundle.js" defer></script>   <!-- defer: don't block parsing -->
    <script src="analytics.js" async></script> <!-- async: load independently -->
</head>
```

## Fix 4: Audit Third-Party Scripts

```
THIRD-PARTY SCRIPTS ARE OFTEN THE BIGGEST OFFENDER:

Check your page with: chrome DevTools → Network tab → sort by size

Common culprits:
  Google Analytics:    45KB (async, usually fine)
  Intercom chat:       300KB (loads entire chat framework)
  Hotjar:              100KB (records user sessions)
  Google Tag Manager:  Loads MORE scripts dynamically
  Social embeds:       500KB+ (Facebook, Twitter widgets)

SOLUTIONS:
  - Load third-party scripts AFTER page content renders
  - Use facades (show a "Load Chat" button instead of loading Intercom on every page)
  - Audit: do you actually USE all these services?
```

## Quick Diagnostic

```
Chrome DevTools → Network tab → Disable cache → Reload

Look for:
1. Large files (sort by Size) → code split or optimize
2. Long chains (waterfall view) → parallelize
3. Render-blocking (blue/purple bars before first paint) → defer/async
4. Third-party domains → audit necessity, lazy-load
```'''
    ),
    (
        "thinking/firstprinciples-why-idempotency",
        "My API sometimes processes the same request twice because of network retries. A customer got charged twice. How do I prevent this?",
        r'''<think>
Double processing / double charging — this is the idempotency problem.

**Why it happens:**
1. Client sends payment request
2. Server processes it (charges card)
3. Response gets lost (network timeout, server crash during response)
4. Client doesn't get confirmation → retries
5. Server processes it again → double charge

**The fundamental problem:**
The client can't distinguish between "server never received my request" and "server processed my request but the response was lost." Both look like a timeout.

**The solution: idempotency keys**
Client sends a unique key with each request. Server checks: "Have I already processed this key?" If yes, return the original result without processing again.

This makes the operation IDEMPOTENT — doing it twice has the same effect as doing it once.

**From first principles:**
In a distributed system, messages can be: lost, duplicated, or reordered. You can't prevent retries (they're necessary for reliability). So you make retries SAFE by making operations idempotent.
</think>

This is the **idempotency problem**: networks are unreliable, retries are necessary, and your server must handle duplicate requests safely.

## Why It Happens

```
HAPPY PATH:
  Client: "Charge $99.99"  →  Server: processes → "OK, charged"
  ✓ Works fine

THE PROBLEM (network timeout):
  Client: "Charge $99.99"  →  Server: processes, charges $99.99
                              Server: sends response...
                              ... response lost in transit (timeout)
  Client: "No response, I'll retry"
  Client: "Charge $99.99"  →  Server: processes AGAIN, charges $99.99 AGAIN
                              → Customer charged $199.98

THE CLIENT CAN'T TELL THE DIFFERENCE:
  A) Server never received the request → should retry ✓
  B) Server processed it but response was lost → should NOT retry ✗
  Both look the same to the client: timeout with no response.
```

## The Fix: Idempotency Keys

```python
# Client sends a unique key with each request
# Server checks: "Did I already process this key?"

# CLIENT:
import uuid

idempotency_key = str(uuid.uuid4())  # Generate ONCE per logical operation

# First attempt:
response = requests.post("/api/charge", json={
    "amount": 99.99,
    "idempotency_key": idempotency_key,  # "abc-123-def"
})

# Retry (same key):
response = requests.post("/api/charge", json={
    "amount": 99.99,
    "idempotency_key": idempotency_key,  # Same key: "abc-123-def"
})
# Server recognizes the key → returns original result → no double charge


# SERVER:
@app.post("/api/charge")
async def charge(data: ChargeRequest):
    # Check if we already processed this key
    existing = await db.query(
        "SELECT response FROM idempotency_keys WHERE key = %s",
        data.idempotency_key
    )

    if existing:
        return existing.response  # Return original result, don't process again

    # Process the charge
    result = await payment_provider.charge(data.amount)

    # Store the key + result (atomically with the charge)
    await db.execute(
        "INSERT INTO idempotency_keys (key, response, created_at) VALUES (%s, %s, NOW())",
        data.idempotency_key, json.dumps(result)
    )

    return result

# Key is stored for 24-48 hours, then cleaned up
# Same key within that window → same response, no reprocessing
```

## The Principle: Idempotency

```
AN OPERATION IS IDEMPOTENT IF:
  Doing it once = doing it twice = doing it N times
  Same result every time, no additional side effects.

NATURALLY IDEMPOTENT:
  GET /users/42          → always returns user 42 (safe to retry)
  PUT /users/42 {name: "Dan"} → sets name to "Dan" (same result if repeated)
  DELETE /users/42       → deletes user 42 (already deleted = no change)

NOT NATURALLY IDEMPOTENT:
  POST /charges {amount: 99.99}  → creates a NEW charge each time
  POST /emails {to: "dan@..."}   → sends a NEW email each time

FOR NON-IDEMPOTENT OPERATIONS → ADD IDEMPOTENCY KEYS
  POST /charges {amount: 99.99, idempotency_key: "abc-123"}
  → First call: charge created
  → Second call (same key): original charge returned, no new charge
```

## Database Schema

```sql
CREATE TABLE idempotency_keys (
    key VARCHAR(255) PRIMARY KEY,
    response JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Clean up old keys periodically
DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL '48 hours';
```

**The rule:** any operation that creates resources or has side effects (charges, emails, orders) should support idempotency keys. Retries are inevitable in distributed systems — make them safe.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
