"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Analysis (Part 6/8)"""

PAIRS = [
    (
        "thinking/causal-database-connection-exhaustion",
        "Our Django app started throwing 'too many connections' errors to PostgreSQL after we added a new Celery worker pool. We have max_connections=100 in PostgreSQL, and the errors happen during peak traffic. We have 4 web workers, 8 Celery workers, and 2 Celery beat schedulers. What's happening?",
        r'''<think>
Connection exhaustion. Let me trace the causal chain by counting connections.

**Connection math:**
Each Django process (web or Celery) creates connections to PostgreSQL. By default, Django creates a NEW connection per request/task and closes it after.

But wait — if Django is configured with `CONN_MAX_AGE`, it keeps connections open. Let me consider both cases.

**Case 1: CONN_MAX_AGE = 0 (default, no pooling)**
- Each request/task opens and closes a connection
- Under load, concurrent requests = concurrent connections
- 4 web workers × multiple threads? If using gunicorn with threads:
  - `gunicorn --workers 4 --threads 4` = 16 potential concurrent connections for web
- 8 Celery workers: each task uses 1 connection = 8 concurrent connections
- 2 Celery beat schedulers: each has 1 connection = 2 connections
- Django management connections (migrations, etc): ~2
- Total: ~28 concurrent connections

That's well under 100. So this shouldn't cause exhaustion... unless:
- Workers have higher concurrency (prefork with concurrency > 1)
- CONN_MAX_AGE > 0 causing connection leak

**Case 2: CONN_MAX_AGE > 0 (connection reuse)**
This is where it gets tricky. With CONN_MAX_AGE, Django keeps connections open for reuse. But each THREAD in each PROCESS maintains its own connection.

If Celery workers use concurrency (prefork or eventlet/gevent):
- 8 workers × 4 prefork processes = 32 connections
- Or 8 workers × 1000 greenlets (gevent) = 8000 potential connections!

Wait — that's it. If they're using gevent or eventlet with Celery, each greenlet gets its own connection. 8 workers × default concurrency of 1000 = 8000 connection attempts.

But even with prefork:
- 8 Celery workers × 4 child processes each = 32 Celery processes
- 4 gunicorn workers × 4 threads = 16 web threads
- 2 beat schedulers = 2 connections
- Total: 50 processes × 1 connection each = 50 connections (if each keeps 1)

But if CONN_MAX_AGE is set, Django creates connections per-thread and keeps them. If threads don't close cleanly, connections leak.

**Most likely root cause:**
The "new Celery worker pool" is the trigger. Before: 4 web + old Celery. After: 4 web + 8 new Celery workers. The total connection count jumped.

Key question: what concurrency model do the Celery workers use?
- `celery worker --concurrency=4 --pool=prefork` → 4 child processes per worker → 8 × 4 = 32 processes
- `celery worker --concurrency=100 --pool=gevent` → 100 greenlets per worker → 8 × 100 = 800 connections

**Counterfactual analysis:**
- If we hadn't added Celery workers → connection count stays under 100 → no error
- If PostgreSQL max_connections was higher → delays the problem but doesn't fix the leak
- If we used connection pooling (pgbouncer) → connections multiplexed → problem solved
</think>

The root cause is that your new Celery workers multiplied the connection count beyond PostgreSQL's limit. Let me show the math:

## Connection Count Analysis

```
BEFORE (worked fine):
  4 gunicorn workers × 1 conn each              =  4
  Old Celery setup (few workers)                 = ~8
  Celery beat                                    =  2
  Total:                                         ~14 connections (well under 100)

AFTER (broken):
  4 gunicorn workers × 4 threads × 1 conn       = 16
  8 Celery workers × ?? concurrency × 1 conn     = ??
  2 Celery beat schedulers                       =  2
  Total:                                         ??
```

**The critical question:** What's your Celery worker concurrency?

```bash
# Check your Celery startup command:
celery -A myapp worker --concurrency=???  --pool=???

# prefork (default): 8 workers × 4 concurrency = 32 child processes
# gevent/eventlet:   8 workers × 100 concurrency = 800 greenlets!
```

## Most Likely Scenario

```python
# If using prefork (default):
# 8 workers × 4 processes each = 32 Celery processes
# + 16 gunicorn threads + 2 beat = 50 connections
# Add CONN_MAX_AGE > 0: connections persist → 50 connections held open
# Peak traffic: some processes hold 2+ connections → exceeds 100

# If using gevent/eventlet:
# 8 workers × 100 greenlets = 800 potential connections
# Far exceeds max_connections=100 → immediate failure
```

## The Fix: Connection Pooling with PgBouncer

```
BEFORE (every process connects directly):
  Process 1 ──→ PostgreSQL (conn 1)
  Process 2 ──→ PostgreSQL (conn 2)
  ...
  Process 50 ──→ PostgreSQL (conn 50)

AFTER (PgBouncer multiplexes):
  Process 1 ──→ PgBouncer ──→ PostgreSQL (10 actual connections)
  Process 2 ──→ PgBouncer ──/
  ...                      /
  Process 50 ──→ PgBouncer ─/

  50 application connections → 10-20 actual PostgreSQL connections
```

```ini
# pgbouncer.ini
[databases]
myapp = host=localhost port=5432 dbname=myapp

[pgbouncer]
listen_port = 6432
pool_mode = transaction  # Release connection after each transaction
max_client_conn = 200    # Accept up to 200 app connections
default_pool_size = 20   # Only use 20 actual PostgreSQL connections
```

```python
# Django settings — point at PgBouncer, not PostgreSQL directly
DATABASES = {
    'default': {
        'HOST': 'localhost',
        'PORT': 6432,         # PgBouncer port, not 5432
        'NAME': 'myapp',
        'CONN_MAX_AGE': 0,    # Let PgBouncer handle pooling
    }
}
```

## Quick Fix (Without PgBouncer)

If you need an immediate fix before setting up PgBouncer:

```python
# 1. Set CONN_MAX_AGE = 0 (close connections after each request/task)
DATABASES = {
    'default': {
        'CONN_MAX_AGE': 0,  # Don't keep connections open
    }
}

# 2. Reduce Celery concurrency
# celery -A myapp worker --concurrency=2  (instead of 4)

# 3. Close connections explicitly in Celery tasks
from django.db import close_old_connections

@app.task
def my_task():
    close_old_connections()  # Close stale connections before work
    try:
        # ... task logic
        pass
    finally:
        close_old_connections()  # Close after work too
```

## Preventing This in the Future

```python
# Add monitoring for connection count
# Run this periodically (e.g., in a health check):
from django.db import connection

def check_connection_count():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = %s",
            [connection.settings_dict['NAME']]
        )
        count = cursor.fetchone()[0]
        if count > 80:  # 80% of max_connections
            alert(f"PostgreSQL connection count high: {count}/100")
        return count
```

The causal chain: new Celery workers → more processes → more connections → exceeded max_connections. The fix: either reduce connections (quick) or pool them with PgBouncer (proper).'''
    ),
    (
        "thinking/causal-cors-errors-after-deploy",
        "After deploying to production, our React frontend gets CORS errors when calling our API. It works perfectly in development. The API is on api.example.com and the frontend is on app.example.com. We have CORS headers configured. What's going wrong?",
        r'''<think>
CORS errors after deploy but works in dev. Let me trace through the possible causes.

**First, understand what's different between dev and prod:**
- Dev: likely same origin (localhost:3000 → localhost:8000) or CORS allows all origins
- Prod: different subdomains (app.example.com → api.example.com)

**Common CORS failure causes after deploy:**

1. **Wildcard origin with credentials**
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```
Browsers REJECT this combination. If you need credentials (cookies, auth headers), the origin must be SPECIFIC, not `*`.

2. **Missing origin in allowed list**
Dev config: `CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]`
Prod config forgot: `"https://app.example.com"` — didn't add the prod domain.

3. **HTTP vs HTTPS mismatch**
`http://app.example.com` ≠ `https://app.example.com`
Origins include the protocol. If the frontend is HTTPS but CORS allows HTTP, it fails.

4. **Preflight requests (OPTIONS) not handled**
For non-simple requests (with custom headers like `Authorization`), browsers send an OPTIONS preflight. If the API doesn't respond to OPTIONS with proper headers, the actual request is blocked.

5. **Reverse proxy stripping headers**
nginx, CloudFront, or a CDN in front of the API might strip the CORS headers from the response.

6. **Missing headers in CORS response**
`Access-Control-Allow-Headers` must include every custom header the frontend sends. Common missing one: `Authorization`, `Content-Type` for JSON.

**Most likely cause for "works in dev, fails in prod":**
Either #2 (forgot to add prod domain to allowed origins) or #1 (using wildcard with credentials) or #5 (reverse proxy stripping headers).

Let me provide a diagnostic approach.
</think>

CORS in dev vs prod — the issue is almost certainly one of these three causes. Here's how to diagnose:

## Step 1: Check the Actual Error (Browser Console)

```
Open DevTools → Console tab. The error message tells you exactly what's wrong:

Error A: "has been blocked by CORS policy: No 'Access-Control-Allow-Origin'
          header is present on the requested resource"
→ CORS headers are missing entirely (proxy stripping them, or misconfigured)

Error B: "has been blocked by CORS policy: The value of the
          'Access-Control-Allow-Origin' header must not be the wildcard '*'
          when the request's credentials mode is 'include'"
→ Using * with credentials (cookies/auth)

Error C: "has been blocked by CORS policy: Request header field
          'authorization' is not allowed by Access-Control-Allow-Headers"
→ Missing header in allowed headers list

Error D: "Response to preflight request doesn't pass access control check"
→ OPTIONS request not handled properly
```

## Step 2: Check From the Command Line

```bash
# Test the actual CORS headers your API returns
curl -v -X OPTIONS https://api.example.com/api/endpoint \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Authorization, Content-Type"

# Look for these headers in the response:
# Access-Control-Allow-Origin: https://app.example.com
# Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
# Access-Control-Allow-Headers: Authorization, Content-Type
# Access-Control-Allow-Credentials: true  (if using cookies)

# If these headers are MISSING → your proxy or server isn't sending them
```

## The Three Most Likely Fixes

### Fix 1: Production Domain Not in Allowed Origins (Most Common)

```python
# ❌ Only has dev origins
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]

# ✅ Include production domains
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",           # Local dev
    "https://app.example.com",         # Production
    "https://staging.example.com",     # Staging
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "authorization",
    "content-type",
    "x-request-id",
]
```

### Fix 2: Wildcard With Credentials (Common)

```python
# ❌ Browsers reject * with credentials
CORS_ALLOW_ALL_ORIGINS = True  # Sets Access-Control-Allow-Origin: *
CORS_ALLOW_CREDENTIALS = True  # Sets Access-Control-Allow-Credentials: true
# → Browser error: can't use * with credentials

# ✅ Explicitly list origins when using credentials
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = ["https://app.example.com"]
CORS_ALLOW_CREDENTIALS = True
```

### Fix 3: Reverse Proxy Stripping CORS Headers (Sneaky)

```nginx
# nginx in front of API — must pass through CORS headers
# OR handle CORS at the nginx level:

server {
    server_name api.example.com;

    location / {
        # Handle preflight
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' 'https://app.example.com';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type';
            add_header 'Access-Control-Allow-Credentials' 'true';
            add_header 'Access-Control-Max-Age' 86400;
            return 204;
        }

        # Pass to app server — make sure CORS headers aren't duplicated
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # If your app also adds CORS headers, you might get duplicates
        # which some browsers reject. Choose ONE place to set them.
    }
}
```

## Complete Django CORS Setup

```python
# settings.py
import os

INSTALLED_APPS = [
    'corsheaders',  # pip install django-cors-headers
    # ... other apps
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # MUST be before CommonMiddleware
    'django.middleware.common.CommonMiddleware',
    # ... other middleware
]

# Environment-specific CORS config
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:3000"
).split(",")

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "x-csrftoken",
    "x-request-id",
]
```

```bash
# .env.production
CORS_ORIGINS=https://app.example.com,https://www.example.com
```

The root cause pattern: CORS works in dev because everything is on localhost (same origin, no CORS needed). In production, different subdomains trigger CORS and you need explicit configuration. The fix is always: specific origins, correct headers, and making sure no proxy strips them.'''
    ),
    (
        "thinking/causal-slow-docker-builds",
        "Our Docker builds went from 2 minutes to 25 minutes. Nothing obvious changed. We're using a multi-stage Dockerfile for a Python app. What could cause this?",
        r'''<think>
Docker build time regression: 2 min → 25 min. Let me think about what could cause a 10x slowdown.

**Docker build caching is the key.** A fast Docker build = most layers are cached. A slow build = cache is being invalidated early, causing downstream layers to rebuild.

**Common causes of cache invalidation:**

1. **COPY . . before pip install**
If the Dockerfile copies ALL source code before installing dependencies, ANY code change invalidates the dependency installation cache:
```dockerfile
COPY . .                    # Invalidated by ANY file change
RUN pip install -r requirements.txt  # Rebuilds every time
```
Fix: COPY requirements.txt first, install, THEN copy code.

2. **A new file in the build context**
If someone added a large file (logs, data, .git) to the directory, the build context transfer is slow AND cache is invalidated.

3. **BuildKit cache changes**
Maybe Docker BuildKit was disabled (or enabled), changing caching behavior.

4. **New dependency that takes long to build**
A newly added pip package that requires compilation (numpy, scipy, cryptography) can add minutes.

5. **.dockerignore missing or changed**
If .dockerignore was removed or changed, Docker sends a larger build context (including node_modules, .git, venv, etc.)

6. **Base image changed**
If using `FROM python:3.11` without a specific tag, a new base image version forces rebuild of ALL layers.

7. **Docker daemon running out of cache space**
Docker prune happened, or disk was full, clearing cached layers.

**Most likely for "nothing obvious changed":**
- .dockerignore issue (someone committed or deleted it)
- A file change that invalidates the cache early in the Dockerfile
- Build context size grew (large file added to repo)

The 2→25 minute jump suggests either cache is fully invalidated (rebuilding everything) or the build context transfer is huge.
</think>

The 2→25 minute jump means Docker's layer cache is being invalidated early, forcing a full rebuild. Here's the diagnostic approach:

## Step 1: Check Build Context Size

```bash
# See how much data Docker is sending to the build daemon
docker build . 2>&1 | head -5
# "Sending build context to Docker daemon  2.5GB"
# If this is large (>100MB), you have a context problem

# Check what's in the context
du -sh --exclude=.git .
ls -la .dockerignore  # Does it exist?
```

If the build context is huge, check `.dockerignore`:

```bash
# .dockerignore — MUST exist, MUST exclude large files
.git
.venv
venv
__pycache__
*.pyc
node_modules
*.log
data/
*.sqlite3
.env
.coverage
htmlcov
```

## Step 2: Check Layer Cache Invalidation

```dockerfile
# ❌ COMMON BUG: cache invalidated too early
FROM python:3.11-slim

WORKDIR /app
COPY . .                              # ANY file change invalidates this
RUN pip install -r requirements.txt   # Rebuilds EVERY TIME (12 min)
RUN python manage.py collectstatic    # Also rebuilds every time

# ✅ FIX: copy requirements first, then code
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .              # Only invalidated when deps change
RUN pip install -r requirements.txt  # CACHED unless requirements.txt changes

COPY . .                             # Only code — fast copy
RUN python manage.py collectstatic   # Rebuilds, but it's fast
```

## Step 3: Check for Heavy New Dependencies

```bash
# See what pip is building from source (slow)
docker build . 2>&1 | grep "Building wheel"
# If you see packages like numpy, scipy, cryptography being compiled...

# Fix: use pre-built wheels
RUN pip install --no-cache-dir -r requirements.txt
# Or use a base image with pre-compiled packages
FROM python:3.11-slim  # slim has fewer build tools
# vs
FROM python:3.11       # full image, more build tools, larger
```

## Step 4: Check for Base Image Changes

```dockerfile
# ❌ Unpinned base image — can change any time
FROM python:3.11

# ✅ Pin the digest for reproducible builds
FROM python:3.11-slim@sha256:abc123...

# Or at minimum, pin the variant
FROM python:3.11.7-slim-bookworm
```

## The Optimized Dockerfile

```dockerfile
# Stage 1: Build dependencies (cached aggressively)
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# System dependencies (rarely changes — cached)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && rm -rf /var/lib/apt/lists/*

# Python dependencies (changes when requirements.txt changes)
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Stage 2: Runtime image (small and fast)
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install pre-built wheels (fast, no compilation)
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application code LAST (changes most frequently)
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "myapp.wsgi", "--bind", "0.0.0.0:8000"]
```

## Diagnostic Summary

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Sending build context...2GB" | Missing .dockerignore | Add .dockerignore |
| pip install runs every build | COPY . . before pip install | Copy requirements.txt first |
| "Building wheel for numpy" | New dep needs compilation | Use pre-built wheels |
| ALL layers rebuild | Base image tag changed | Pin base image version |
| First build after prune is slow | Cache was cleared | Expected, subsequent builds fast |

The causal chain is almost always: something invalidated the cache early → all downstream layers rebuild → pip install runs from scratch (15+ minutes). Fix the cache ordering and the build drops back to 2 minutes.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
