"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 26)"""

PAIRS = [
    (
        "thinking/backtrack-shared-database-to-api",
        "Our two microservices share the same database. When Service A changes a table schema, Service B breaks. How do we fix this?",
        r'''<think>
Shared database between microservices — this is a classic anti-pattern that defeats the purpose of microservices.

**Why shared databases are problematic:**
1. Tight coupling — schema changes in one service break others
2. No clear ownership — who controls the schema?
3. Can't independently deploy — both must coordinate schema changes
4. Can't independently scale — both tied to same DB
5. Cross-service joins create hidden dependencies

**The principle:** each microservice should own its data. Other services access that data through the service's API, not directly through the database.

**Backtrack: shared DB → API-mediated data access**

**Migration path:**
1. Identify which service OWNS which tables
2. Create APIs in the owner service for data access
3. Have consumer services call the API instead of querying directly
4. Eventually move tables to separate databases
</think>

A shared database between microservices is the **number one microservices anti-pattern**. It couples the services at the data layer, defeating the entire purpose.

## The Problem

```
CURRENT (shared database):
  Service A ──→ Database ←── Service B
                  ↑
  Both read/write the SAME tables

  Service A: ALTER TABLE users ADD COLUMN middle_name
  Service B: SELECT first_name, last_name FROM users  ← doesn't break
  But:       SELECT * FROM users → now includes middle_name → DTO breaks
  Or:        INSERT INTO users (...) → missing middle_name → nullable? default?

  Every schema change requires coordinating between teams.
  This ISN'T microservices — it's a distributed monolith.
```

## Backtrack: Each Service Owns Its Data

```
TARGET (API-mediated access):
  Service A ──→ Database A    Service B ──→ Database B
       ↑                           ↑
       └───── API calls ───────────┘

  Service A owns the users table → exposes GET /api/users/:id
  Service B needs user data → calls Service A's API
  Service A changes schema → only Service A's code changes
  Service B sees the same API response → doesn't break
```

## Migration Path (Step by Step)

```python
# STEP 1: Identify ownership
# Which service OWNS which tables?

# Service A (User Service):  users, user_profiles, user_preferences
# Service B (Order Service): orders, order_items, payments

# SHARED TABLE: addresses (both services read/write)
# → Decide: addresses belongs to User Service
# → Order Service stores a COPY of the shipping address (denormalized)


# STEP 2: Create APIs in the owner service
# User Service exposes an API:
@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    user = await db.query("SELECT * FROM users WHERE id = %s", user_id)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        # API response is a CONTRACT — you control what's exposed
        # Adding middle_name to the DB doesn't change the API response
        # until you explicitly add it to the API
    }


# STEP 3: Order Service calls the API instead of querying directly
# ❌ BEFORE: direct database query
def create_order(user_id, items):
    user = db.query("SELECT * FROM users WHERE id = %s", user_id)  # Direct DB access!
    order = db.insert("orders", {"user_id": user_id, ...})

# ✅ AFTER: API call
import httpx

async def create_order(user_id, items):
    user = await httpx.get(f"http://user-service/api/users/{user_id}")
    user_data = user.json()
    order = await db.insert("orders", {
        "user_id": user_id,
        "user_name": user_data["name"],  # Store a copy, not a FK
        ...
    })


# STEP 4: Gradually remove cross-service table access
# Monitor: which queries does Service B make to Service A's tables?
# Replace each with an API call
# When all cross-service queries are gone → move tables to separate databases
```

## Handling the "But APIs Are Slower" Concern

```
"Direct DB query: 1ms. API call: 10ms. Why make it slower?"

ANSWERS:
1. CACHING: Cache user data in Order Service (Redis, in-memory)
   → First call: 10ms. Subsequent calls: 0.1ms.

2. DATA DUPLICATION: Store what you need locally
   → Order table stores user_name, shipping_address (snapshot at order time)
   → Don't need to look up user on every order query

3. EVENTS: publish changes, don't query
   → User Service publishes: "user.updated" event
   → Order Service listens, updates its local copy
   → No API calls needed for reads

4. INDEPENDENCE > SPEED:
   → If User Service is down, Order Service still works (has local data)
   → With shared DB, if DB is down, BOTH services are down
```

## The End State

```
BEFORE (distributed monolith):
  User Service → [Shared DB] ← Order Service
  Tightly coupled. Schema changes break things.
  Can't deploy independently. Can't scale independently.

AFTER (true microservices):
  User Service → [User DB]
       ↓ events / API
  Order Service → [Order DB]
  Loosely coupled. Schema changes are internal.
  Deploy independently. Scale independently.
```

**Rule:** if two services share a database, they're not microservices — they're a distributed monolith with extra network latency.'''
    ),
    (
        "thinking/causal-cors-errors-not-an-api-bug",
        "I'm getting CORS errors in the browser when calling my API. But when I test the API with curl or Postman, it works perfectly. Why does it only fail in the browser?",
        r'''<think>
CORS only affects browsers — this is a very common source of confusion.

**Why CORS exists:**
CORS is a BROWSER security policy. It prevents malicious websites from making requests to your API using the user's cookies/session. It's enforced by the BROWSER, not the server.

**Why curl/Postman works but browser doesn't:**
- curl and Postman are NOT browsers. They don't enforce CORS.
- curl sends the request directly and shows the response. Period.
- The browser checks: "Is the API at api.example.com allowing requests from my-app.com?"
  - If yes (CORS headers present) → browser allows the response
  - If no → browser BLOCKS the response (even though the server sent it!)
  - The server DID respond. The browser just won't let your JavaScript see it.

**The confusing part:**
The request actually reaches the server and the server responds. The BROWSER throws away the response because the CORS headers are missing.

So it's not an API bug — it's a browser security feature doing its job.
</think>

CORS is a **browser-only** security feature. Curl and Postman don't enforce it — only browsers do.

## Why It's Not an API Bug

```
CURL / POSTMAN:
  Your machine → sends request → server responds → you see the response
  No security checks. Direct HTTP. Works always.

BROWSER:
  Your JavaScript → sends request → server responds
  Browser checks: "Does the response have CORS headers allowing my-app.com?"
  NO → browser BLOCKS the response
  → Your JavaScript gets an error
  → Even though the server successfully responded!

  The request REACHED the server.
  The server DID respond.
  The browser threw away the response to protect the user.
```

## What the Browser Actually Does

```
STEP 1: Your JavaScript on my-app.com calls api.example.com
  fetch('https://api.example.com/data')

STEP 2: Browser sends a PREFLIGHT request (for non-simple requests)
  OPTIONS /data HTTP/1.1
  Origin: https://my-app.com
  Access-Control-Request-Method: GET

STEP 3: Server responds to preflight
  HTTP/1.1 200 OK
  Access-Control-Allow-Origin: https://my-app.com  ← "yes, this origin is allowed"
  Access-Control-Allow-Methods: GET, POST           ← "these methods are allowed"

  If this header is MISSING or doesn't match:
  → Browser: "CORS policy: No 'Access-Control-Allow-Origin' header"
  → Your JavaScript gets an opaque error
  → The actual API response is hidden from you

STEP 4 (if preflight passed): Browser sends the actual request
  GET /data HTTP/1.1
  Origin: https://my-app.com

STEP 5: Server responds with data + CORS headers
  HTTP/1.1 200 OK
  Access-Control-Allow-Origin: https://my-app.com
  Content-Type: application/json
  {"users": [...]}
  → Browser: "CORS headers match → allow JavaScript to see the response"
```

## The Fix

```python
# Your API needs to include CORS headers in responses

# Flask
from flask_cors import CORS
app = Flask(__name__)
CORS(app, origins=["https://my-app.com"])

# FastAPI
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://my-app.com"],  # Your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Express.js
const cors = require('cors');
app.use(cors({ origin: 'https://my-app.com' }));

# Django
# pip install django-cors-headers
INSTALLED_APPS = [..., 'corsheaders']
MIDDLEWARE = ['corsheaders.middleware.CorsMiddleware', ...]
CORS_ALLOWED_ORIGINS = ['https://my-app.com']
```

## Common CORS Mistakes

```python
# ❌ MISTAKE 1: allowing all origins in production
CORS(app, origins=["*"])  # Any website can call your API
# Fine for public APIs. Dangerous if you use cookies/sessions.

# ❌ MISTAKE 2: forgetting credentials
fetch('https://api.example.com/data', { credentials: 'include' })
# Browser: "CORS error: credentials flag, but Allow-Origin is *"
# Fix: set specific origin, not *

# ❌ MISTAKE 3: not handling preflight OPTIONS requests
# Some frameworks don't automatically respond to OPTIONS requests
# The preflight fails → actual request never sent

# ❌ MISTAKE 4: CORS headers only on success responses
# If your API returns 500, does it still include CORS headers?
# If not → browser shows "CORS error" instead of the actual error
# Add CORS headers to ALL responses, including errors
```

## Key Insight

```
CORS is NOT a server security feature.
CORS is a BROWSER security feature.

The server just says: "These origins are allowed."
The BROWSER enforces it.

That's why:
  curl works    → no browser → no CORS enforcement
  Postman works → no browser → no CORS enforcement
  Browser fails → browser enforces CORS → blocks the response

If you're having CORS issues, the fix is always on the SERVER
(add the right headers), but the enforcement is in the BROWSER.
```'''
    ),
    (
        "thinking/firstprinciples-why-ci-cd",
        "Why do I need CI/CD? I just run my tests manually and deploy with a script. It works fine.",
        r'''<think>
CI/CD from first principles. Why automate what works manually?

**The human error problem:**
Manual processes rely on humans remembering to do things correctly every time:
- "Did you run the tests before deploying?"
- "Did you run ALL the tests, or just the ones for your changes?"
- "Did you deploy to staging first?"
- "Did you update the environment variables?"
- "Did you run the database migration?"

**Murphy's law of manual deployment:**
The one time you forget a step is Friday at 5pm when there's a critical hotfix and you're rushing.

**What CI/CD actually provides:**
1. Consistency — same steps every time, no human variation
2. Speed — automated tests run while you work on other things
3. Confidence — if it passes CI, it's tested
4. Documentation — the pipeline IS the deployment process documentation
5. Accountability — who deployed what, when (audit trail)
6. Fast feedback — know if your code breaks something within minutes
</think>

Your manual process works **until it doesn't**. CI/CD exists because humans forget steps under pressure.

## The Problem With Manual Processes

```
YOUR MANUAL DEPLOY:
  1. Run tests                    ← "I'll skip, nothing changed much"
  2. Build the project            ← forgot to pull latest from main
  3. Deploy to staging            ← "just push to prod, it's a small change"
  4. Check staging               ← skipped (see step 3)
  5. Deploy to production        ← deployed, but forgot step 1 had a failing test
  6. Run database migration      ← forgot this step entirely
  7. Verify production            ← "it'll be fine" → goes home → gets paged at 2am

  THIS WORKS 95% OF THE TIME.
  The 5% is always Friday at 5pm during a critical hotfix
  when you're rushing and under pressure.

CI/CD:
  git push → tests run automatically → build runs automatically
  → deploys to staging automatically → deploys to production automatically
  → database migration runs automatically → health check verifies automatically

  Same steps. Every time. No human variation. No forgetting.
```

## What CI/CD Actually Does

```
CI (Continuous Integration):
  "Verify every code change automatically"

  Developer pushes code to GitHub
    → CI server pulls the code
    → Installs dependencies
    → Runs linter (code style)
    → Runs unit tests
    → Runs integration tests
    → Reports: ✅ all passed / ❌ test_payment failed

  WITHOUT CI:
    Developer: "I think I ran the tests... they probably passed"

  WITH CI:
    PR shows: ✅ 342 tests passed, 0 failed, 87% coverage
    → You KNOW it works. Confidence to merge.

CD (Continuous Deployment):
  "Deploy every verified change automatically"

  CI passes on main branch
    → Build Docker image
    → Deploy to staging
    → Run smoke tests on staging
    → Deploy to production (if smoke tests pass)
    → Health check production
    → Alert if health check fails

  WITHOUT CD:
    "Hey, can someone deploy? Who has the SSH key? What's the deploy script?"
    "Wait, which commit are we deploying? Is the migration included?"

  WITH CD:
    Merge PR → deployed in 5 minutes. No human intervention.
```

## A Simple CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml — your entire deployment process
name: Deploy

on:
  push:
    branches: [main]  # Run on every push to main

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest                        # Run ALL tests
      - run: flake8                        # Check code style

  deploy:
    needs: test                            # Only deploy if tests pass
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t myapp .       # Build
      - run: docker push registry/myapp    # Push to registry
      - run: ssh server "cd /app && docker pull registry/myapp && docker compose up -d"
      - run: curl -f https://myapp.com/health  # Verify it's up

# That's it. Push to main → tests → build → deploy → verify.
# Same steps, every time, automatically.
```

## The Real Benefits (Beyond Automation)

```
1. FAST FEEDBACK
   Push code → know in 5 minutes if you broke something
   vs: find out days later when someone else's code fails

2. CONFIDENCE TO MERGE
   PR shows green ✅ → you know ALL tests pass
   vs: "I think it works, I ran some tests locally"

3. DOCUMENTATION
   The CI/CD pipeline IS the deployment process
   New team member: "How do we deploy?" → "Look at .github/workflows/"
   vs: tribal knowledge that lives in one person's head

4. ACCOUNTABILITY
   git log shows who merged what, when
   CI shows which build was deployed to production
   vs: "Who deployed yesterday? What changed?"

5. ROLLBACK
   Automated deploy → automated rollback to previous version
   vs: "Uh... which version were we running before? Where's the backup?"
```

**Your script works. CI/CD makes sure it runs the same way every time, even when you're tired, rushed, or someone else deploys.**'''
    ),
    (
        "thinking/analogy-load-balancer-restaurant-host",
        "What does a load balancer actually do? I know it distributes traffic but I don't understand why I need one or how it decides where to send requests.",
        r'''<think>
Load balancer — the restaurant host analogy works well.

A restaurant host (maître d') does exactly what a load balancer does:
- Multiple tables (servers) can seat guests (handle requests)
- Host decides which table to send each guest to
- If one table is full (server overloaded), send to another
- If a table is closed (server down), don't send guests there
- Some tables are bigger (more powerful servers) — send more guests there

Key load balancing algorithms:
1. Round robin — table 1, table 2, table 3, table 1, table 2...
2. Least connections — send to the table with fewest guests
3. Random — pick a random table
4. Weighted — bigger tables get more guests
5. IP hash — same guest always goes to the same table (sticky sessions)
</think>

A load balancer is like a **restaurant host** who decides which table to seat each guest at.

## The Analogy

```
RESTAURANT WITHOUT A HOST (one table):
  All guests → one table
  Table can seat 10 people
  Guest #11 arrives → "Sorry, we're full" → guest leaves (lost customer)

  = One server
  Server can handle 1000 requests/second
  Request #1001 → server overloaded → timeout → user sees error

RESTAURANT WITH A HOST (multiple tables):
  Host stands at the door
  Guest arrives → host checks which tables have space
  → "Table 2 has room, right this way"
  → Next guest → "Table 3, please"
  → Table 1 is closed (cleaning) → host stops sending guests there

  = Load balancer
  Request arrives → load balancer checks which servers are healthy
  → Routes to server 2 → next request to server 3
  → Server 1 is down → load balancer stops sending traffic there
```

## How It Decides Where to Send Requests

```
ROUND ROBIN (simplest):
  Guest 1 → Table 1
  Guest 2 → Table 2
  Guest 3 → Table 3
  Guest 4 → Table 1  (back to start)
  Guest 5 → Table 2
  ...
  Simple, fair, doesn't consider how busy each table is.

LEAST CONNECTIONS (smartest for most cases):
  Table 1: 3 guests
  Table 2: 1 guest
  Table 3: 5 guests
  → Next guest → Table 2 (fewest current guests)
  Considers actual load. Best for requests with varying duration.

WEIGHTED (for different server sizes):
  Table 1: big table (seats 20) → gets 50% of guests
  Table 2: small table (seats 5) → gets 12.5% of guests
  Table 3: big table (seats 20) → gets 37.5% of guests
  Matches traffic to server capacity.

HEALTH CHECKS (essential):
  Host periodically asks each table: "Are you still open?"
  Table 2: "Yes!" ✓
  Table 3: no response... ✗
  → Stop sending guests to Table 3 → all guests go to Tables 1 and 2
  → When Table 3 responds again → resume sending guests there
```

## In Practice

```nginx
# Nginx as a load balancer
upstream backend {
    # Three application servers
    server app1.internal:8080;
    server app2.internal:8080;
    server app3.internal:8080;
}

server {
    listen 80;

    location / {
        proxy_pass http://backend;  # Nginx distributes across all 3
    }
}

# With health checks and weights:
upstream backend {
    least_conn;  # Use least-connections algorithm

    server app1.internal:8080 weight=3;  # Gets 3x traffic (bigger server)
    server app2.internal:8080 weight=1;
    server app3.internal:8080 weight=1 backup;  # Only used if others are down
}
```

## Why You Need One

```
WITHOUT LOAD BALANCER:
  1 server handles everything
  → Server goes down → entire site is down
  → Traffic spike → server overloaded → everyone affected
  → Can't update → downtime during deploy

WITH LOAD BALANCER:
  3 servers behind load balancer
  → Server 1 goes down → traffic goes to servers 2 and 3 → site stays up
  → Traffic spike → load spread across 3 servers → everyone served
  → Update → take server 1 out → deploy → put back → repeat for 2 and 3
     → ZERO downtime deployment

WHEN DO YOU NEED ONE?
  □ You need zero-downtime deployments
  □ You need to handle more traffic than one server can
  □ You need redundancy (site stays up if a server dies)
  □ You want to scale horizontally (add more servers = more capacity)
```

At its core: a load balancer ensures no single server becomes a bottleneck, and no single server failure takes down your service.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
