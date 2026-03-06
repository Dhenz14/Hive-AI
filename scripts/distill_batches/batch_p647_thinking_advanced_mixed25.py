"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 25)"""

PAIRS = [
    (
        "thinking/causal-api-timeout-cascade",
        "Our checkout endpoint sometimes takes 30+ seconds and times out. Everything else in the app is fast. The checkout logic itself is simple — it just calls a few internal services. Why is it so slow?",
        r'''<think>
Checkout endpoint slow (30s+) while everything else is fast. The checkout calls "a few internal services" — this is likely a cascading timeout problem.

**Causal analysis:**
If checkout calls services A, B, and C sequentially:
- A responds in 200ms
- B calls external payment API which is slow (10s timeout)
- C calls shipping API which is slow (10s timeout)
- Total: 200ms + 10s + 10s = ~20s just waiting

If these have default timeouts (Python requests default: no timeout!):
- A responds in 200ms
- B hangs waiting for payment API... 30s... 60s... still waiting
- The request has no overall timeout → hangs until the client gives up

**Key insight:** without explicit timeouts, one slow dependency makes the entire request slow. And "a few internal services" can each have their own slow dependencies.

**The cascade:**
- Checkout → Service B → Payment API (slow)
- Service B has no timeout → waits 30s
- Checkout has no timeout on its call to Service B → also waits 30s
- User sees 30s timeout

**Fixes:**
1. Add explicit timeouts to every HTTP call
2. Add an overall request deadline
3. Make independent calls parallel (not sequential)
4. Add circuit breaker for slow dependencies
</think>

This is a **cascading timeout problem**. Your checkout calls services sequentially, and one slow downstream dependency blocks the entire chain.

## Root Cause

```
YOUR CHECKOUT FLOW:
  Checkout endpoint
    → calls Inventory Service (200ms) ✓
    → calls Payment Service (this calls Stripe... Stripe is slow today)
       └→ Stripe API: no response for 30 seconds
    → calls Shipping Service (never reached — still waiting for Payment)
    → calls Email Service (never reached)

  Total: 200ms + 30s (waiting for Stripe) = 30.2s timeout

THE FUNDAMENTAL PROBLEM:
  No timeouts set → one slow dependency blocks everything
  Sequential calls → total time = sum of all call times
```

## Fix 1: Add Timeouts to Every Call

```python
# ❌ NO TIMEOUT: will wait forever
response = requests.post("https://payment-service/charge", json=data)
# If payment-service hangs → your checkout hangs → your user waits → your server thread is blocked

# ✅ EXPLICIT TIMEOUT: fail fast
response = requests.post(
    "https://payment-service/charge",
    json=data,
    timeout=(3, 10)  # (connect_timeout, read_timeout) in seconds
)
# If no response in 10 seconds → raises requests.Timeout → you handle it

# Python requests DEFAULT timeout is NONE (waits forever)
# ALWAYS set a timeout. ALWAYS.
```

## Fix 2: Parallelize Independent Calls

```python
import asyncio

# ❌ SEQUENTIAL: total time = A + B + C
async def checkout_sequential(order):
    inventory = await check_inventory(order)      # 200ms
    payment = await charge_payment(order)          # 2000ms
    shipping = await create_shipment(order)        # 500ms
    email = await send_confirmation(order)         # 300ms
    # Total: 3000ms (even when nothing is slow)

# ✅ PARALLEL: total time = max(independent calls)
async def checkout_parallel(order):
    # Step 1: Check inventory (must happen first)
    inventory = await check_inventory(order)       # 200ms

    # Step 2: Payment (must happen before shipping/email)
    payment = await charge_payment(order)          # 2000ms

    # Step 3: Shipping + Email can happen in parallel
    shipping, email = await asyncio.gather(
        create_shipment(order),                    # 500ms } run
        send_confirmation(order),                  # 300ms } simultaneously
    )
    # Total: 200 + 2000 + 500 = 2700ms (saved 300ms)
    # More importantly: shipping delay doesn't add to email delay

    # Step 3 could also be fire-and-forget (don't wait at all):
    asyncio.create_task(send_confirmation(order))  # Non-blocking
```

## Fix 3: Request Deadline Pattern

```python
import time

async def checkout(order):
    deadline = time.time() + 15  # Total budget: 15 seconds for entire checkout

    async def call_with_deadline(func, *args):
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("Checkout deadline exceeded")
        return await asyncio.wait_for(func(*args), timeout=remaining)

    try:
        inventory = await call_with_deadline(check_inventory, order)
        payment = await call_with_deadline(charge_payment, order)
        shipping = await call_with_deadline(create_shipment, order)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Checkout timed out. Please try again.")

    # Even if Payment takes 14 seconds, Shipping only gets 1 second
    # The total can NEVER exceed 15 seconds
```

## Fix 4: Make Non-Critical Steps Async

```python
async def checkout(order):
    # CRITICAL PATH (user waits for these):
    inventory = await check_inventory(order)  # Must verify stock
    payment = await charge_payment(order)     # Must charge before confirming

    # Return to user immediately
    order = await save_order(order, payment)

    # NON-CRITICAL (handle in background):
    await message_queue.publish("order.completed", {
        "order_id": order.id,
        "user_email": order.email,
    })
    # Shipping, email, analytics happen asynchronously
    # If email service is slow → user doesn't care, they already got their confirmation

    return {"order_id": order.id, "status": "confirmed"}
```

**The rule:** every HTTP call needs a timeout. Sequential calls should be parallelized where possible. Non-critical steps should be async. And set an overall deadline for the entire operation.'''
    ),
    (
        "thinking/adversarial-sql-injection-modern",
        "I use an ORM so I don't need to worry about SQL injection, right?",
        r'''<think>
ORMs and SQL injection — mostly safe but with important exceptions.

**When ORMs protect you:**
- Standard queries through the ORM API (filter, get, create, etc.)
- Parameterized queries generated by the ORM
- Most normal usage

**When ORMs DON'T protect you:**

1. **Raw SQL methods** — every ORM has a way to write raw SQL
   - Django: `Model.objects.raw()`, `connection.cursor().execute()`
   - SQLAlchemy: `session.execute(text())`, `engine.execute()`
   - If you use string formatting in these → SQL injection

2. **Extra/annotate with user input** — some ORM methods accept raw expressions
   - Django: `.extra(where=[...])`, `.annotate()` with raw SQL fragments
   - SQLAlchemy: `column.op(user_input)`

3. **Order by user input** — passing user input directly to `.order_by()`
   - Django: `Model.objects.order_by(request.GET['sort'])` — can inject SQL in some cases

4. **Search/filter with raw expressions**
   - Some ORMs allow raw WHERE clauses
   - If user input goes into these → injectable

5. **JSON/JSONB queries** — ORM support for JSON is often less mature, may use raw fragments

**The answer: ORMs greatly reduce the attack surface but don't eliminate it entirely. You still need to be aware.**
</think>

ORMs **greatly reduce** the risk but **don't eliminate it entirely**. Here are the cases where you're still vulnerable.

## Where ORMs Protect You (99% of Usage)

```python
# ✅ SAFE: ORM generates parameterized queries
# Django
User.objects.filter(email=user_input)
# Generates: SELECT * FROM users WHERE email = %s  (parameterized)
# Even if user_input = "' OR '1'='1" → treated as a literal string, not SQL

# SQLAlchemy
session.query(User).filter(User.email == user_input)
# Same: parameterized, safe from injection
```

## Where You're Still Vulnerable

```python
# 1. RAW SQL WITH STRING FORMATTING
# ❌ VULNERABLE: string formatting in raw SQL
def search_users(query):
    return User.objects.raw(f"SELECT * FROM users WHERE name LIKE '%{query}%'")
    # If query = "'; DROP TABLE users; --"
    # → SELECT * FROM users WHERE name LIKE '%'; DROP TABLE users; --%'
    # → Your users table is gone

# ✅ SAFE: parameterized raw SQL
def search_users(query):
    return User.objects.raw(
        "SELECT * FROM users WHERE name LIKE %s",
        [f"%{query}%"]
    )


# 2. ORDER BY FROM USER INPUT
# ❌ VULNERABLE: user controls sort column
def list_users(request):
    sort_by = request.GET.get('sort', 'name')
    return User.objects.order_by(sort_by)
    # If sort_by = "name; DELETE FROM users"
    # Django may protect against this, but some ORMs don't
    # NEVER pass raw user input to order_by

# ✅ SAFE: whitelist allowed sort fields
ALLOWED_SORTS = {'name', 'email', 'created_at', '-name', '-email', '-created_at'}

def list_users(request):
    sort_by = request.GET.get('sort', 'name')
    if sort_by not in ALLOWED_SORTS:
        sort_by = 'name'
    return User.objects.order_by(sort_by)


# 3. EXTRA() WITH USER INPUT (Django-specific)
# ❌ VULNERABLE: .extra() accepts raw SQL fragments
def search(request):
    query = request.GET['q']
    return Product.objects.extra(
        where=[f"name LIKE '%%{query}%%'"]  # Raw SQL with user input!
    )

# ✅ SAFE: use ORM filter methods instead
def search(request):
    query = request.GET['q']
    return Product.objects.filter(name__icontains=query)


# 4. DYNAMIC TABLE/COLUMN NAMES
# ❌ VULNERABLE: user controls table or column name
def get_data(request):
    table = request.GET['table']
    cursor.execute(f"SELECT * FROM {table}")  # Table name can't be parameterized!
    # If table = "users; DROP TABLE orders" → disaster

# ✅ SAFE: whitelist allowed table names
ALLOWED_TABLES = {'products', 'categories', 'reviews'}

def get_data(request):
    table = request.GET['table']
    if table not in ALLOWED_TABLES:
        raise ValueError("Invalid table")
    cursor.execute(f"SELECT * FROM {table}")  # Safe: whitelist-validated


# 5. JSONB/JSON QUERIES WITH RAW EXPRESSIONS
# ❌ VULNERABLE: raw JSON path from user input (in some ORMs)
def search_json(request):
    field = request.GET['field']
    cursor.execute(f"SELECT * FROM products WHERE metadata->>'{field}' = 'true'")

# ✅ SAFE: parameterize or whitelist
ALLOWED_FIELDS = {'color', 'size', 'brand'}

def search_json(request):
    field = request.GET['field']
    if field not in ALLOWED_FIELDS:
        raise ValueError("Invalid field")
    cursor.execute(
        "SELECT * FROM products WHERE metadata->>%s = %s",
        [field, 'true']
    )
```

## The Rule

```
ORM SAFE ZONE (use normally):
  .filter()  .get()  .create()  .update()  .delete()
  .annotate()  .aggregate()  (with ORM expressions)
  .select_related()  .prefetch_related()

DANGER ZONE (review carefully):
  .raw()           → must use parameterized queries
  .extra()         → avoid entirely, use ORM methods instead
  .order_by()      → whitelist allowed values
  cursor.execute() → must use parameterized queries
  Any f-string or .format() near SQL → almost certainly vulnerable

GOLDEN RULE:
  Never put user input into SQL via string formatting.
  Always use parameterized queries or ORM methods.
  When in doubt, whitelist allowed values.
```'''
    ),
    (
        "thinking/analogy-middleware-airport-security",
        "What is middleware in web frameworks? I see it mentioned everywhere but don't understand what it does or when I'd need it.",
        r'''<think>
Middleware — the airport security analogy works well here.

**Middleware is like airport security checkpoints:**
Every passenger (request) must go through a series of checkpoints before reaching their gate (route handler). And after boarding (response), they go through customs/baggage claim on the way out.

Each checkpoint has one specific job:
- ID check (authentication)
- Bag scan (input validation)
- Metal detector (security check)
- Boarding pass scan (authorization)

Middleware in web frameworks works the same way:
- Each middleware has one specific job
- Every request passes through ALL middleware in order
- Middleware can modify the request, block it, or let it through
- On the response side, middleware runs in reverse order
</think>

Think of middleware as **airport security checkpoints** that every request passes through before reaching your code.

## The Analogy

```
AIRPORT:
  Passenger arrives
    → Checkpoint 1: Check ID (authentication)
    → Checkpoint 2: Scan bags (input validation)
    → Checkpoint 3: Metal detector (security)
    → Checkpoint 4: Scan boarding pass (authorization)
    → Gate: board the plane (your route handler)
    ← Return: collect baggage (response processing)
    ← Customs: declare items (response headers)

WEB SERVER:
  Request arrives
    → Middleware 1: Parse cookies/headers (request parsing)
    → Middleware 2: Check auth token (authentication)
    → Middleware 3: Log the request (logging)
    → Middleware 4: Check rate limits (rate limiting)
    → Route handler: process the request (your code)
    ← Middleware 4: add rate limit headers
    ← Middleware 3: log the response
    ← Middleware 2: nothing (auth already done)
    ← Middleware 1: set cookies
```

## In Code

```python
# Express.js middleware — functions that run on every request
const express = require('express');
const app = express();

// MIDDLEWARE 1: Log every request
app.use((req, res, next) => {
    console.log(`${req.method} ${req.path}`);
    next();  // Pass to next middleware
});

// MIDDLEWARE 2: Parse JSON body
app.use(express.json());

// MIDDLEWARE 3: Check authentication
app.use((req, res, next) => {
    const token = req.headers.authorization;
    if (!token && req.path !== '/login') {
        return res.status(401).json({ error: 'Not authenticated' });
        // BLOCKED: request never reaches the route handler
    }
    req.user = verifyToken(token);  // Attach user to request
    next();
});

// MIDDLEWARE 4: Rate limiting
app.use(rateLimit({ windowMs: 60000, max: 100 }));

// ROUTE HANDLER: your actual code (only reached if all middleware passes)
app.get('/api/users', (req, res) => {
    // By this point:
    // ✓ Request was logged
    // ✓ Body was parsed
    // ✓ User is authenticated (req.user exists)
    // ✓ Rate limit hasn't been exceeded
    const users = getUsers();
    res.json(users);
});
```

```python
# Django middleware — same concept, Python style
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',       # Security headers
    'django.contrib.sessions.middleware.SessionMiddleware', # Session handling
    'django.middleware.common.CommonMiddleware',            # URL normalization
    'django.middleware.csrf.CsrfViewMiddleware',           # CSRF protection
    'django.contrib.auth.middleware.AuthenticationMiddleware', # Auth
    'myapp.middleware.RequestLoggingMiddleware',            # Custom logging
]

# Custom middleware
class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # BEFORE the view (request going in)
        start = time.time()

        response = self.get_response(request)  # Call the next middleware/view

        # AFTER the view (response going out)
        duration = time.time() - start
        logger.info(f"{request.method} {request.path} → {response.status_code} ({duration:.0f}ms)")

        return response
```

## Common Middleware Uses

```
WHAT MIDDLEWARE IS GOOD FOR:
  ✓ Authentication — verify token/session on every request
  ✓ Logging — log every request and response
  ✓ CORS — add cross-origin headers to every response
  ✓ Rate limiting — enforce request limits
  ✓ Error handling — catch exceptions, return clean error responses
  ✓ Request parsing — parse JSON, form data, cookies
  ✓ Compression — gzip responses
  ✓ Security headers — add X-Frame-Options, CSP, etc.
  ✓ Request ID — add unique ID for tracing

WHAT MIDDLEWARE IS NOT FOR:
  ✗ Business logic (that goes in route handlers)
  ✗ Database queries (too broad, runs on every request)
  ✗ Route-specific validation (use route-level middleware instead)
```

Middleware is code that runs on **every request**, handling cross-cutting concerns (auth, logging, security) so your route handlers can focus on business logic.'''
    ),
    (
        "thinking/multiperspective-trunk-based-vs-gitflow",
        "Our team uses Git Flow with develop, release, and hotfix branches. It feels heavyweight. Should we switch to trunk-based development?",
        r'''<think>
Git Flow vs Trunk-Based Development. Both have strong advocates.

**Git Flow perspective:**
- Clear separation of concerns (feature → develop → release → main)
- Good for versioned software (desktop apps, SDKs, libraries)
- Release branches allow stabilization
- Hotfix branches allow emergency fixes
- But: complex, long-lived branches, merge conflicts, slow release cadence

**Trunk-Based Development perspective:**
- Everyone commits to main (or very short-lived branches)
- CI/CD deploys from main automatically
- Feature flags instead of feature branches
- Fast feedback, continuous deployment
- But: requires strong CI, feature flags, mature engineering culture

**When each fits:**
- Git Flow: versioned releases (mobile apps, libraries), less mature CI, multiple supported versions
- Trunk-Based: web apps, continuous deployment, strong CI/CD, feature flags

**For most web teams today:** Trunk-Based is the better default. Git Flow was designed for a different era (before CI/CD was common, when releases were ceremonies).
</think>

For most web teams, **trunk-based development is better**. Git Flow was designed for a different era. Here's the analysis.

## Each Approach's Strengths

```
GIT FLOW:
  Strength: "We support 3 versions simultaneously (v1.x, v2.x, v3.x).
  Each needs independent bug fixes. Git Flow gives us clear release branches."
  → Perfect for versioned software: mobile apps, libraries, SDKs

  Weakness: long-lived branches → merge conflicts → slow releases
  "We can't ship this feature because the release branch isn't cut yet"

TRUNK-BASED:
  Strength: "We deploy to production 10 times a day. Any commit to main
  that passes CI goes straight to users. Features ship in hours, not weeks."
  → Perfect for web apps, SaaS, continuous deployment

  Weakness: requires discipline (CI must be fast and reliable,
  feature flags needed for incomplete features)
  "An incomplete feature was accidentally deployed because CI passed"
```

## Visual Comparison

```
GIT FLOW:
  main:     ──M1────────────M2──────────────────M3────
  develop:  ──D1──D2──D3──D4──D5──D6──D7──D8──D9──D10─
  feature:    └─F1─F2─┘    └──F3──F4──F5──┘
  release:              └─R1─R2─┘
  hotfix:                          └─H1─┘

  → 5 branch types, complex merging, release ceremonies
  → Feature branches live for days/weeks
  → "Which branch has the latest code?" → depends on context

TRUNK-BASED:
  main:     ──C1──C2──C3──C4──C5──C6──C7──C8──C9──C10─
  feature:    └─F1─┘  └─F2─┘        └──F3─┘
                ↑ hours, not days

  → 1 main branch, short-lived feature branches (< 1 day)
  → Every commit to main is deployable
  → "Which branch has the latest code?" → main. Always main.
```

## When Each Is Right

```
USE GIT FLOW WHEN:
  □ You ship versioned releases (v1.0, v2.0, v3.0)
  □ You support multiple versions simultaneously
  □ Releases need stabilization periods (QA, regression testing)
  □ Mobile apps (App Store review process = release cycle)
  □ Libraries/SDKs (consumers pin to versions)

USE TRUNK-BASED WHEN:
  □ You deploy continuously (web apps, SaaS, APIs)
  □ You have CI/CD that deploys automatically
  □ You want to ship features fast (hours, not weeks)
  □ You have 2-20 developers
  □ You use feature flags for incomplete work

MOST WEB TEAMS: trunk-based. You're building a web app deployed
from main. Git Flow adds ceremony without value.
```

## How to Switch

```
FROM GIT FLOW → TRUNK-BASED:

1. Stop creating new feature branches off develop
   → Create short-lived branches off main instead

2. Merge directly to main (via PR, < 1 day old)
   → Delete develop branch

3. Deploy from main on every merge
   → CI/CD pipeline: main → test → deploy

4. Use feature flags for incomplete features
   if feature_flag('new_checkout'):
       show_new_checkout()
   else:
       show_old_checkout()

5. Delete release branches
   → Every commit to main IS a release

6. Hotfixes go to main (same as any other fix)
   → No special hotfix process needed
```

## Feature Flags (The Key Enabler)

```python
# Feature flags let you merge incomplete code to main safely

# Simple implementation:
FEATURE_FLAGS = {
    'new_checkout': True,      # Enabled for everyone
    'dark_mode': False,        # Disabled (in development)
    'ai_recommendations': 0.1, # Enabled for 10% of users (gradual rollout)
}

def is_enabled(flag, user=None):
    value = FEATURE_FLAGS.get(flag, False)
    if isinstance(value, float):  # Percentage rollout
        return hash(user.id) % 100 < value * 100
    return bool(value)

# In your code:
if is_enabled('new_checkout', user):
    return new_checkout_flow(order)
else:
    return old_checkout_flow(order)

# Incomplete feature merged to main → flag is off → users see old behavior
# When ready → turn flag on → users see new behavior
# If something breaks → turn flag off → instant rollback
```

For a web team that deploys continuously, trunk-based development with feature flags gives you faster shipping, fewer merge conflicts, and simpler git history.'''
    ),
    (
        "thinking/firstprinciples-why-containerized-databases",
        "Should I run my production database in Docker? I currently run PostgreSQL directly on the server and it works fine.",
        r'''<think>
Production databases in Docker — this is a common question with a nuanced answer.

**Why people want to containerize databases:**
- Consistency with the rest of the stack (everything in Docker)
- Easy to spin up identical environments
- Infrastructure as code

**Why production databases in Docker is risky:**
1. Data persistence: containers are ephemeral by design. Database data must persist.
2. Performance: Docker adds a small overhead for I/O. Databases are I/O-heavy.
3. Resource management: databases need careful CPU/memory tuning. Container limits add complexity.
4. Storage: Docker volumes have subtle behavior differences from direct filesystem.
5. Networking: extra network hop through Docker bridge.
6. Upgrade complexity: upgrading a containerized database is more complex than native.

**The principle:**
Databases are STATEFUL. Containers are designed for STATELESS workloads. There's a fundamental tension.

**The practical answer:**
- Development/testing: Docker is great (docker-compose up → database ready)
- Production: use managed database services (RDS, Cloud SQL) or native installation
- If you MUST self-host: native installation is simpler and more reliable

For small-scale production with a single server, PostgreSQL installed directly is fine and simpler.
</think>

**Keep PostgreSQL running directly.** Containerizing production databases adds complexity without proportional benefit for most cases.

## The Fundamental Tension

```
CONTAINERS are designed for: STATELESS workloads
  - Spin up, process request, can be destroyed and recreated
  - Ephemeral by design
  - Easy to scale horizontally (run 10 copies)

DATABASES are inherently: STATEFUL
  - Data must persist across restarts, crashes, upgrades
  - Can't just destroy and recreate (you'd lose all data)
  - Scaling is complex (replication, not just "run more copies")

Putting stateful things in stateless containers creates friction.
It's possible, but you're fighting the abstraction.
```

## Risks of Dockerized Production Databases

```
1. DATA LOSS RISK:
   docker rm my-postgres  # Oops. If volume wasn't configured correctly → data gone.
   docker-compose down -v # The -v flag removes volumes. Seen in production incidents.

   Native install: data is in /var/lib/postgresql. Hard to accidentally delete.

2. PERFORMANCE:
   Docker adds I/O overhead (copy-on-write filesystem layers).
   Databases are I/O-intensive.
   Benchmark: 5-15% slower I/O in Docker vs native (varies by storage driver).
   For most apps: negligible. For high-performance databases: matters.

3. UPGRADE COMPLEXITY:
   Native: apt upgrade postgresql → done (data stays in place)
   Docker: pull new image → make sure volumes are correct →
           handle major version upgrades (pg_upgrade) →
           pray the volume mounts are right

4. DEBUGGING:
   Native: psql, pg_stat_activity, filesystem access to WAL/logs
   Docker: docker exec → another layer → log rotation different →
           can't easily access data directory from host
```

## When Docker Databases Make Sense

```
✅ DOCKER IS GREAT FOR:
  Development: docker-compose up → database ready in seconds
  Testing/CI: fresh database per test run, tear down after
  Staging: replicate production-like environment
  Short-lived databases: data processing, migrations, one-off tasks

✅ KUBERNETES + OPERATORS:
  If you're already running Kubernetes at scale,
  database operators (CloudNativePG, Crunchy, Zalando)
  handle the complexity for you. But this is a LOT of infrastructure.

❌ DOCKER IS RISKY FOR:
  Single-server production with no orchestration
  When you don't have deep Docker volume expertise
  When the database is your most critical component
```

## What to Do Instead

```
OPTION 1: NATIVE INSTALL (your current setup — keep it)
  Good for: single server, simple setup, full control
  → apt install postgresql
  → Configure, tune, backup
  → Simple, proven, reliable

OPTION 2: MANAGED DATABASE SERVICE (best for most teams)
  Good for: any production workload, offloads maintenance
  → AWS RDS, Google Cloud SQL, DigitalOcean Managed DB
  → Automatic backups, failover, monitoring, upgrades
  → $15-50/month for small instances
  → You focus on your app, they manage the database

OPTION 3: DOCKER + VOLUME (if you must containerize)
  Good for: when everything MUST be in containers
  → Use named volumes (not bind mounts)
  → Backup the volume regularly
  → Test your backup restore process
  → Document the exact volume configuration
```

**Your PostgreSQL running directly on the server is the simplest, most reliable setup for a single-server deployment.** Don't fix what isn't broken. When you outgrow a single server, consider a managed service — not Docker.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
