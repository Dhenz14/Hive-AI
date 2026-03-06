"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 18)"""

PAIRS = [
    (
        "thinking/firstprinciples-why-version-control",
        "I'm a solo developer. Do I really need Git? I just keep copies of my project folder like project_v1, project_v2, project_final, project_final_FINAL.",
        r'''<think>
Version control from first principles for a solo developer.

**The problems with folder copies:**
1. Which folder has the bug fix from Tuesday? Was it v3 or v3_fixed?
2. project_final_FINAL_v2_USE_THIS — which is actually latest?
3. You can't see WHAT changed between versions
4. You can't undo a specific change without undoing everything after it
5. The folders waste enormous disk space (full copies every time)
6. No way to experiment safely ("I'll try this risky refactor... oops, now I don't remember what I changed")

**What Git actually provides (from first principles):**
1. TIME TRAVEL — go back to any previous state
2. CHANGE TRACKING — see exactly what changed, when, and why
3. BRANCHING — experiment without risking working code
4. SELECTIVE UNDO — revert one specific change without affecting others
5. EFFICIENCY — stores only differences, not full copies

Even for a solo developer, these are valuable. Git isn't about collaboration — it's about managing change over time.
</think>

Even solo, you need Git. Here's why, derived from the problems you'll inevitably hit.

## The Problems With Folder Copies

```
Your filesystem right now:
  project_v1/
  project_v2/
  project_v2_fixed/
  project_v3/
  project_final/
  project_final_FINAL/
  project_final_REAL/
  project_final_USE_THIS_ONE/

Questions you CAN'T answer:
  "What did I change between v2 and v3?"          → diff every file manually
  "When did I introduce the payment bug?"          → check each folder one by one
  "I want to undo the CSS change from last week    → which folder? what changed?
   but KEEP the database changes from yesterday"
  "I want to try a risky experiment without        → copy the whole folder AGAIN
   breaking what works"
```

## What Git Actually Does (From First Principles)

```
Git doesn't store copies of your project.
Git stores CHANGES (diffs) over time.

Think of it as an infinite UNDO HISTORY for your entire project:

  Time ──────────────────────────────────────────→
  commit 1    commit 2    commit 3    commit 4
  "init"      "add login" "fix bug"   "new feature"
  ────────────────────────────────────────────────
  You can:
  - Jump to ANY point: git checkout commit2
  - See what changed: git diff commit2 commit3
  - Undo ONE change: git revert commit3 (keeps commit4)
  - Experiment safely: git branch experiment
```

## The 5 Things You Get (Even Solo)

```bash
# 1. TIME TRAVEL — go back to any previous state
git log --oneline
# a1b2c3d Add payment processing
# e4f5g6h Fix login bug
# i7j8k9l Initial project setup

git checkout e4f5g6h  # Go back to "Fix login bug" state
# Your entire project is now exactly as it was then
git checkout main     # Come back to present

# 2. CHANGE TRACKING — what changed, when, why
git log --oneline -- payment.py
# Shows every change ever made to payment.py, with dates and messages

git diff HEAD~3      # What changed in the last 3 commits?
git blame auth.py    # Who wrote each line? (even solo — "past me at 2am")

# 3. SAFE EXPERIMENTATION
git branch try-new-database
git checkout try-new-database
# Make risky changes... doesn't work? No problem:
git checkout main    # Your working code is untouched
git branch -d try-new-database  # Delete the failed experiment

# 4. SELECTIVE UNDO
# "The CSS change from commit abc broke mobile layout,
#  but the API changes from commit def are fine"
git revert abc       # Undo ONLY that commit. Everything else stays.

# 5. DISASTER RECOVERY
# Accidentally deleted a file? Reset your machine? Laptop stolen?
# If you pushed to GitHub:
git clone https://github.com/you/project.git  # Everything recovered
```

## Getting Started (5 Minutes)

```bash
# One-time setup
cd your-project
git init
git add .
git commit -m "Initial project"

# Daily workflow (30 seconds)
# 1. Work on your code normally
# 2. When something works:
git add .
git commit -m "Add user registration feature"

# 3. That's it. Repeat.

# Optional but recommended: push to GitHub for backup
git remote add origin https://github.com/you/project.git
git push -u origin main
```

## Folder Copies vs Git

```
                    FOLDER COPIES          GIT
Disk space          Full copy each time    Only stores diffs
                    10 copies = 10x size   10 commits ≈ 1.1x size

Find what changed   Diff every file        git diff (instant)

Undo one change     Impossible (all or     git revert (surgical)
                    nothing)

Experiment safely   Copy entire folder     git branch (instant, no copy)

When did bug start  Check each folder      git bisect (binary search,
                    manually               finds it in minutes)

Backup/recovery     Hope you copied to     git push (backed up on
                    USB drive              GitHub/GitLab)
```

You don't need Git because you work with others. You need Git because you work with **future you**, who won't remember what past you changed or why.'''
    ),
    (
        "thinking/causal-database-connection-pool-exhaustion",
        "Our app randomly starts returning 500 errors that say 'connection pool exhausted'. Restarting the app fixes it temporarily but it comes back after a few hours. What's happening?",
        r'''<think>
Connection pool exhaustion — connections are being checked out but never returned.

**Causal chain:**
1. App starts → pool has N connections available (e.g., 10)
2. Each request checks out a connection → does work → returns connection
3. Something causes connections to NOT be returned
4. Pool gradually shrinks: 10 → 9 → 8 → ... → 0
5. New requests can't get a connection → 500 error
6. Restart → pool reset to 10 → works again → same leak

**What causes connections to not be returned?**

1. **Missing finally/close in error paths** — most common
   - Code gets a connection, starts a query
   - Query throws an exception
   - Exception handling doesn't release the connection
   - Connection is "checked out" forever

2. **Long-running queries with no timeout**
   - A slow query holds a connection for minutes
   - All connections get stuck on slow queries
   - New requests queue up and eventually timeout

3. **Leaked connections in application code**
   - Getting a raw connection instead of using context manager
   - Forgetting to close/release in some code path

4. **Transaction not committed or rolled back**
   - BEGIN TRANSACTION → do work → exception
   - Transaction never closed → connection can't be reused

**The "few hours" timeline suggests a slow leak** — one or two connections leak per some operation, and it takes hours to exhaust the pool of ~10-20 connections.
</think>

Connections are being checked out and never returned. It's a **connection leak** — like a memory leak but for database connections.

## Causal Chain

```
Pool starts: 10 available connections
  ↓
Request A: checks out connection, does query, returns connection → 10 available
Request B: checks out connection, query FAILS, connection NOT returned → 9 available
Request C: normal → 9 available
Request D: query fails, leaked → 8 available
  ↓ (repeat over hours)
0 available connections
  ↓
All new requests: "Connection pool exhausted" → 500 error
  ↓
Restart app → pool reset to 10 → works again → same leak starts over
```

## Most Likely Cause: Missing Cleanup in Error Paths

```python
# ❌ LEAKS: connection not returned when query fails
def get_user(user_id):
    conn = pool.getconn()          # Check out connection
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    pool.putconn(conn)             # Return connection
    return result
    # IF cursor.execute() throws → pool.putconn() never called
    # → connection leaked forever

# ✅ FIXED: use try/finally or context manager
def get_user(user_id):
    conn = pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()
    except Exception:
        conn.rollback()            # Clean up any partial transaction
        raise
    finally:
        pool.putconn(conn)         # ALWAYS returns connection, even on error

# ✅ BEST: context manager (impossible to forget)
def get_user(user_id):
    with pool.connection() as conn:  # Auto-returns on exit
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cursor.fetchone()
    # Connection automatically returned, even if exception thrown
```

## SQLAlchemy Example (Most Common in Python)

```python
# ❌ LEAKS: session not closed on error
def create_order(data):
    session = Session()
    order = Order(**data)
    session.add(order)
    session.commit()     # If this fails → session/connection leaked
    return order

# ✅ FIXED: scoped session with proper cleanup
def create_order(data):
    session = Session()
    try:
        order = Order(**data)
        session.add(order)
        session.commit()
        return order
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()  # ALWAYS close

# ✅ BEST: use a context manager or middleware
from contextlib import contextmanager

@contextmanager
def get_session():
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def create_order(data):
    with get_session() as session:
        order = Order(**data)
        session.add(order)
        return order  # Auto-commits on success, rollback on error, close always
```

## Diagnosis

```python
# Add monitoring to find the leak
import logging

# Log pool status on every request
@app.before_request
def log_pool_status():
    pool = db.engine.pool
    logging.info(
        "Pool status: size=%d, checked_out=%d, overflow=%d",
        pool.size(),
        pool.checkedout(),
        pool.overflow(),
    )
    # Watch for checkedout() growing over time → leak confirmed

# Set pool timeout so leaked connections eventually error instead of hanging
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,     # Wait max 30s for a connection
    pool_recycle=1800,   # Recycle connections every 30 min
    pool_pre_ping=True,  # Verify connections are alive before using
)
```

## Quick Fixes While You Find the Leak

```python
# 1. Increase pool size (buys time, doesn't fix the leak)
pool_size=20  # Instead of 10

# 2. Add pool_recycle to reclaim stale connections
pool_recycle=1800  # Recycle every 30 minutes

# 3. Search codebase for leak patterns
```

```bash
# Find potential leaks in your code:
# Raw connections without context managers
grep -rn "getconn\|get_connection\|\.connect()" --include="*.py" | grep -v "with "

# Sessions without close
grep -rn "Session()" --include="*.py" | grep -v "with \|finally"

# Missing try/finally around database operations
grep -rn "\.execute(" --include="*.py" -A5 | grep -v "finally\|with "
```'''
    ),
    (
        "thinking/adversarial-cors-misconfiguration",
        "I set Access-Control-Allow-Origin to * in my API to fix CORS errors during development. Is that okay for production?",
        r'''<think>
CORS wildcard in production — this is a very common security mistake.

**What CORS actually protects:**
CORS prevents malicious websites from making requests to your API using a user's browser credentials (cookies, auth headers). Without CORS, any website could make requests to your API as if they were the logged-in user.

**Why * is dangerous with credentials:**
Actually, `*` alone isn't the worst case — browsers won't send credentials (cookies) with `*` origin. The REAL danger is:
1. `Access-Control-Allow-Origin: *` + `Access-Control-Allow-Credentials: true` — browsers reject this combination
2. But the common "fix" is to dynamically reflect the Origin header — which is equivalent to `*` but DOES allow credentials
3. This means any website can make authenticated requests to your API

**Attack scenario:**
1. User is logged into your app (has auth cookies)
2. User visits malicious site evil.com
3. evil.com's JavaScript makes fetch() to your API
4. Browser sends the user's cookies along (because origin is allowed)
5. Your API processes the request as if the user made it
6. evil.com reads the response (user's private data, account info, etc.)

This is essentially a CSRF attack facilitated by CORS misconfiguration.

**The correct approach:**
Whitelist specific origins that should be allowed.
</think>

**No. `Access-Control-Allow-Origin: *` in production is a security risk.** Here's what an attacker can do with it.

## What CORS Actually Protects

```
WITHOUT CORS:
  1. User logs into your-app.com (gets auth cookie)
  2. User visits evil.com (in another tab)
  3. evil.com runs: fetch("https://your-api.com/account", {credentials: "include"})
  4. Browser sends request WITH user's cookies
  5. evil.com reads user's private data

  CORS exists to PREVENT step 4-5.
  The browser checks: "Is evil.com allowed to call your-api.com?"
  If not → browser blocks the response.
```

## The Danger

```python
# ❌ DANGEROUS: reflects any origin (common "fix" for CORS errors)
@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin')
    response.headers['Access-Control-Allow-Origin'] = origin  # Reflects ANY origin
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

# This is equivalent to "any website can make authenticated requests to your API"
```

## Attack Scenario

```javascript
// ATTACKER'S SITE: evil.com
// User is logged into your-app.com in another tab

// Step 1: Steal user's data
const response = await fetch('https://your-api.com/api/me', {
    credentials: 'include',  // Sends user's cookies
});
const userData = await response.json();
// → {name: "Dan", email: "dan@...", ssn: "123-45-6789"}
// Attacker now has the user's private data

// Step 2: Perform actions as the user
await fetch('https://your-api.com/api/transfer', {
    method: 'POST',
    credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({to: 'attacker-account', amount: 10000}),
});
// → Money transferred using victim's session
```

## The Correct Configuration

```python
# ✅ CORRECT: whitelist specific origins
from flask_cors import CORS

ALLOWED_ORIGINS = [
    "https://your-app.com",
    "https://admin.your-app.com",
]

# Development only:
if app.config['ENV'] == 'development':
    ALLOWED_ORIGINS.append("http://localhost:3000")

CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)
```

```python
# ✅ CORRECT: Express.js
const cors = require('cors');

const allowedOrigins = [
    'https://your-app.com',
    'https://admin.your-app.com',
];

app.use(cors({
    origin: (origin, callback) => {
        // Allow requests with no origin (server-to-server, mobile apps)
        if (!origin) return callback(null, true);

        if (allowedOrigins.includes(origin)) {
            callback(null, true);
        } else {
            callback(new Error('CORS not allowed'));
        }
    },
    credentials: true,
}));
```

## When `*` IS Okay

```
Access-Control-Allow-Origin: * is SAFE when:
  □ Your API is truly public (no authentication)
  □ You don't use cookies or session headers
  □ The data is non-sensitive (public weather API, etc.)
  □ You DON'T set Access-Control-Allow-Credentials: true

  Example: a public REST API that uses API keys in headers
  (not cookies) — * is fine because browsers don't send
  API keys automatically.

Access-Control-Allow-Origin: * is DANGEROUS when:
  □ Your API uses cookies for authentication
  □ Your API uses session tokens
  □ Any endpoint returns user-specific data
  □ Any endpoint modifies data
```

## CORS Security Checklist

```
□ Never reflect the Origin header without validation
□ Whitelist specific origins, don't use wildcards
□ Never combine * with Access-Control-Allow-Credentials: true
□ Restrict Access-Control-Allow-Methods to only what's needed
□ Restrict Access-Control-Allow-Headers to only what's needed
□ Set Access-Control-Max-Age to cache preflight requests
□ Use different CORS configs for dev vs production
□ Audit: search codebase for "Allow-Origin" and verify each one
```'''
    ),
    (
        "thinking/uncertainty-monolith-vs-microservices-startup",
        "We're starting a new SaaS product. Should we build microservices from day one to 'do it right', or start with a monolith?",
        r'''<think>
Monolith vs microservices for a NEW SaaS — this is one of the clearest recommendations in software architecture.

**Almost always start with a monolith.** Confidence: 90%.

**Why:**
1. You don't know your domain boundaries yet. Microservices require clear bounded contexts. In a new product, you'll discover boundaries as you build — you'll get them wrong if you guess upfront.

2. Speed of iteration. In a monolith: change code, restart, test. In microservices: change code across 3 services, update contracts, deploy all 3, debug distributed failure.

3. Operational complexity. Microservices need: service discovery, distributed tracing, API gateways, deployment pipelines per service, inter-service auth, eventual consistency handling. That's a LOT of infrastructure for a product that might not find product-market fit.

4. Team size. Microservices solve the TEAM scaling problem (multiple teams can deploy independently). A small team doesn't have this problem.

**The 10% uncertainty:**
- If the team has extensive microservices experience and tooling
- If specific components have radically different scaling needs (e.g., ML inference vs CRUD API)
- If regulatory requirements mandate service isolation

**The "modular monolith" is the right middle ground** — monolith deployment with clear internal module boundaries, so you CAN extract services later when you actually need them.
</think>

**90% confidence: start with a monolith.** Microservices from day one is one of the most common and costly architectural mistakes for startups.

## Why Monolith First

```
THE FUNDAMENTAL PROBLEM WITH MICROSERVICES ON DAY ONE:

You don't know your domain boundaries yet.

  Day 1: "Users, Orders, and Payments are separate services"
  Month 3: "Actually, creating an order requires user preferences,
            payment validation, and inventory check... now every
            operation needs 4 service calls"
  Month 6: "We need to refactor the boundaries. But now we have
            4 separate databases, API contracts, and deployment
            pipelines to change."

  A monolith lets you MOVE CODE FREELY between modules.
  Microservices turn a code refactor into a distributed systems problem.
```

## The Real Cost Comparison

```
MONOLITH FOR 3 DEVELOPERS:
  Deployment: git push → deployed
  Debugging: stack trace shows the whole flow
  Refactoring: move function from module A to module B
  Local dev: run one process
  New feature: change code, restart, test
  Time to first feature: days

MICROSERVICES FOR 3 DEVELOPERS:
  Deployment: 5 CI pipelines, service mesh, container orchestration
  Debugging: distributed tracing across 5 services, log aggregation
  Refactoring: change API contracts, update 3 services, coordinate deploy
  Local dev: docker-compose with 8 containers, 16GB RAM minimum
  New feature: update 3 services, test integration, deploy in order
  Time to first feature: weeks

  You're spending 40% of your time on INFRASTRUCTURE
  instead of PRODUCT. For a startup, this is fatal.
```

## The Right Approach: Modular Monolith

```python
# Structure your monolith with clear module boundaries
# so you CAN extract services later IF needed

project/
  app/
    users/              # User module
      models.py
      services.py       # Business logic
      api.py            # Routes/endpoints
    orders/             # Order module
      models.py
      services.py
      api.py
    payments/           # Payment module
      models.py
      services.py
      api.py
    shared/             # Shared utilities
      auth.py
      database.py

# Rules:
# 1. Modules communicate through defined interfaces (service layer)
# 2. No direct database queries across modules
# 3. No importing models from other modules directly

# users/services.py
class UserService:
    def get_user(self, user_id): ...
    def create_user(self, data): ...

# orders/services.py
class OrderService:
    def __init__(self, user_service: UserService):
        self.users = user_service  # Depends on interface, not implementation

    def create_order(self, user_id, items):
        user = self.users.get_user(user_id)  # Through the interface
        # NOT: db.query(User).get(user_id)   # Don't reach into user's DB
```

## When You'll ACTUALLY Need Microservices

```
EXTRACT A SERVICE WHEN (not before):
  □ A module has radically different scaling needs
    "The image processing is maxing out CPU while the API is idle"
    → Extract image processing as a separate service

  □ A module needs independent deployment
    "We deploy the payment service 10x/day but the rest weekly"
    → Extract payment service

  □ Teams need to work independently
    "Team A keeps breaking Team B's code"
    → Extract into separate services with contracts

  □ A module needs different technology
    "This ML pipeline needs Python/GPU but the API is Node.js"
    → Extract the ML pipeline

  NONE of these apply on day one of a new SaaS.
```

## The Progression

```
STAGE 1: Monolith (0-50 engineers, finding product-market fit)
  → One deployable, modular code, fast iteration

STAGE 2: Modular monolith (10-50 engineers, scaling product)
  → Clear module boundaries, could be extracted but aren't yet

STAGE 3: Selective extraction (30-100 engineers, specific scaling needs)
  → Extract 1-3 services that NEED to be separate
  → Keep the rest as a monolith

STAGE 4: Microservices (100+ engineers, multiple teams)
  → Many services with clear ownership
  → Platform team manages infrastructure

Companies that started as monoliths and evolved:
  Shopify, GitHub, Basecamp, Stack Overflow
  → Still mostly monoliths at massive scale

Companies that regretted microservices early:
  Almost every startup that tried it before product-market fit.
```

**The 10% where microservices might be right from day one:** team has extensive microservices experience AND existing platform tooling, components have fundamentally different scaling profiles (ML + CRUD), or regulatory requirements mandate service isolation.'''
    ),
    (
        "thinking/analogy-api-rate-limiting-highway",
        "Why do APIs have rate limits? It feels like they're just being mean and preventing me from using their service.",
        r'''<think>
Rate limiting explanation via highway/traffic analogy.

**Why rate limits exist (from the API provider's perspective):**
1. Protect shared infrastructure from one user hogging everything
2. Ensure fair access for all users
3. Prevent accidental or intentional abuse/DDoS
4. Manage costs (each request costs money to serve)
5. Maintain quality of service (response times degrade under heavy load)

**Highway analogy:**
A highway has capacity. If too many cars enter at once:
- Traffic slows for everyone
- Eventually gridlock — nobody moves
- Emergency vehicles can't get through

Rate limits = on-ramp meters (those traffic lights on highway on-ramps)
- They don't prevent you from using the highway
- They control how FAST cars enter
- Result: highway flows smoothly for everyone

This maps well:
- Highway capacity = server capacity
- Cars = API requests
- Gridlock = server overload
- On-ramp meter = rate limiter
- Carpool lane = premium tier (higher rate limits)
</think>

Think of it like **highway traffic management**.

## The Analogy

```
AN API SERVER IS A HIGHWAY:
  Capacity: 1,000 cars (requests) per minute can flow smoothly

  WITHOUT RATE LIMITS (no traffic control):
    Developer A sends 10,000 requests/minute (data migration)
    → Highway is gridlocked
    → Developer B's 1 request takes 30 seconds instead of 100ms
    → Developer C's requests time out entirely
    → The API is effectively DOWN for everyone
    → One user ruined it for thousands

  WITH RATE LIMITS (on-ramp metering):
    Each developer: max 100 requests/minute
    → Developer A: 100 req/min (plenty for normal use)
    → Developer B: 100 req/min
    → Developer C: 100 req/min
    → Highway flows smoothly for everyone
    → Total: well within 1,000 capacity

  PREMIUM TIER (carpool/HOV lane):
    Free tier: 100 req/min
    Paid tier: 1,000 req/min
    Enterprise: 10,000 req/min with dedicated capacity
    → Pay more = higher limit, just like toll lanes
```

## Why Each Limit Exists

```
RATE LIMIT (requests per time window):
  "100 requests per minute"
  = On-ramp meter: controls how fast you enter the highway
  = Prevents any single user from flooding the system

CONCURRENCY LIMIT:
  "Max 10 simultaneous requests"
  = Only 10 of your cars on the highway at once
  = Prevents hogging all lanes

DAILY QUOTA:
  "10,000 requests per day"
  = Your monthly toll pass has a daily mile limit
  = Manages total resource consumption and costs

BURST LIMIT:
  "10 requests per second, 100 per minute"
  = You can sprint briefly but can't sustain it
  = Allows short bursts while preventing sustained overload
```

## How to Work With Rate Limits (Not Against Them)

```python
import time
from functools import wraps

# 1. Respect rate limit headers
def call_api(url):
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"})

    # Most APIs tell you their limits in response headers:
    remaining = int(response.headers.get('X-RateLimit-Remaining', 100))
    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))

    if remaining < 5:
        wait = reset_time - time.time()
        print(f"Rate limit almost reached, waiting {wait:.0f}s")
        time.sleep(max(wait, 0))

    return response

# 2. Handle 429 (Too Many Requests) with backoff
def call_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url)

        if response.status_code == 429:
            # API says "slow down" — respect the Retry-After header
            wait = int(response.headers.get('Retry-After', 2 ** attempt))
            print(f"Rate limited. Waiting {wait}s before retry.")
            time.sleep(wait)
            continue

        return response

# 3. Batch requests instead of individual ones
# ❌ 1000 individual requests:
for user_id in user_ids:
    get_user(user_id)  # 1000 API calls → rate limited

# ✅ 1 batch request:
get_users(user_ids)    # 1 API call → returns all 1000
```

## The Bottom Line

```
Rate limits aren't punishment. They're traffic management.

Without them:
  One runaway script → API down for everyone → your app breaks too

With them:
  Everyone gets fair access → API stays fast and reliable → your app works

You benefit FROM rate limits even when they limit YOU,
because they prevent OTHER users from degrading YOUR experience.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
