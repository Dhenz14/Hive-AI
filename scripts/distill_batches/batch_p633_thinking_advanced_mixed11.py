"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 11)"""

PAIRS = [
    (
        "thinking/adversarial-cors-misconfiguration",
        "I added Access-Control-Allow-Origin: * to fix CORS errors. My colleague says this is a security risk. Is it really? The API is behind authentication anyway.",
        r'''<think>
CORS with wildcard origin + authentication. Let me adversarially test whether this is actually a risk.

The claim: "the API is behind authentication, so * is fine."

**How CORS works:**
CORS is a BROWSER security mechanism. When JavaScript on siteA.com tries to call an API on siteB.com, the browser asks siteB.com: "Do you allow requests from siteA.com?"

If siteB.com responds with Access-Control-Allow-Origin: *, it's saying "any website's JavaScript can call me."

**Attack scenario with CORS * + authentication:**
1. User is logged into yourapi.com (has authentication cookie)
2. User visits evil.com (phishing link, compromised ad, etc.)
3. evil.com's JavaScript calls yourapi.com/api/user/data
4. Browser includes the user's auth cookie (it's a same-site request to yourapi.com from the cookie's perspective... wait, actually)

Hmm, let me think more carefully.

With `Access-Control-Allow-Origin: *`:
- Browser sends the request
- Browser DOES NOT send cookies when origin is * (browser policy: wildcard + credentials = rejected)
- So if auth is via cookies, `*` actually prevents credential sending

BUT if the wildcard is specifically paired with `Access-Control-Allow-Credentials: true`:
- This is REJECTED by browsers. You cannot have `*` + credentials. Browsers enforce this.
- To allow credentials, you must specify the exact origin, not *.

So `*` with cookie-based auth is actually somewhat safe because browsers won't send cookies with wildcard CORS.

BUT:
- If auth is via Authorization header (Bearer token stored in localStorage): XSS on ANY site can read the token from localStorage (well, only same-origin) but malicious JavaScript on evil.com CAN call your API if they have the token. The CORS * means your API allows the cross-origin response to be READ.
- Even without credentials: your API might return sensitive data that doesn't require auth (public endpoints returning user lists, etc.)

**The real risks of CORS *:**
1. Any website's JS can read your API responses (information disclosure for unauthenticated endpoints)
2. If you later add `Access-Control-Allow-Credentials: true`, you'll create a real vulnerability
3. Overly permissive CORS is a code smell — it suggests you haven't thought about who should call your API

**My assessment:**
- For a public API meant to be called by any frontend: `*` is appropriate
- For an internal/private API: specify exact allowed origins
- With cookie-based auth: `*` prevents credential sending, so it's not catastrophic
- With token-based auth: `*` is less risky (tokens aren't auto-sent) but still allows read access from any origin
</think>

Your colleague is partially right, but the risk depends on your authentication method. Let me break it down.

## How CORS Actually Works

```
WITHOUT CORS headers:
  evil.com JavaScript: fetch("https://yourapi.com/data")
  Browser: "No CORS header on response → I won't let evil.com read this."
  evil.com: can't see the response.

WITH Access-Control-Allow-Origin: *
  evil.com JavaScript: fetch("https://yourapi.com/data")
  Browser: "Origin * means anyone can read → here's the response."
  evil.com: CAN read your API responses.

IMPORTANT: CORS doesn't prevent the REQUEST — it prevents
the RESPONSE from being READ by JavaScript on another origin.
```

## The Specific Risk with `*`

```
Access-Control-Allow-Origin: *
  + Access-Control-Allow-Credentials: true
  = REJECTED by browsers (intentionally impossible)

  The browser specification prevents this combination.
  So cookies are NEVER sent with wildcard CORS.

ACCESS-CONTROL-ALLOW-ORIGIN: *   (without credentials)
  ✓ Request is sent
  ✗ Cookies are NOT included
  ✓ Response CAN be read by any website's JavaScript

  This means:
    - Authenticated endpoints (cookie-based): NOT vulnerable
      (no cookie sent → request is unauthenticated → gets 401)
    - Unauthenticated endpoints: EXPOSED
      (any website can read the responses)
    - Token-based auth (Authorization header): partially exposed
      (evil.com needs the token, but if they have it, CORS * lets them use it)
```

## When `*` Is Actually Dangerous

```python
# ❌ DANGEROUS: wildcard + reflecting origin + credentials
# This is the REAL vulnerability — not just `*`

@app.middleware("http")
async def cors_middleware(request, call_next):
    response = await call_next(request)
    origin = request.headers.get("Origin", "")
    # REFLECTING ANY ORIGIN with credentials = vulnerability
    response.headers["Access-Control-Allow-Origin"] = origin  # Reflects attacker's origin!
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

# Attack:
# 1. User logged into yourapi.com (has auth cookie)
# 2. Visits evil.com
# 3. evil.com: fetch("https://yourapi.com/api/me", {credentials: "include"})
# 4. Browser sends cookie (origin is reflected, credentials allowed)
# 5. evil.com reads the response: user's private data!

# ✅ FIXED: whitelist specific origins
ALLOWED_ORIGINS = {"https://yourfrontend.com", "https://admin.yourfrontend.com"}

@app.middleware("http")
async def cors_middleware(request, call_next):
    response = await call_next(request)
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response
```

## The Right CORS Configuration

```python
# For a private API (your frontend only):
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.yourcompany.com"],  # Specific origins ONLY
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# For a public API (any frontend):
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         # Anyone can call
    allow_credentials=False,     # No cookies (explicitly)
    allow_methods=["GET"],       # Read-only for public
    allow_headers=["Authorization"],
)
```

## Summary

```
Access-Control-Allow-Origin: *
  Public API (meant for anyone): ✓ Fine
  Private API with cookie auth:  ~ Somewhat safe (cookies not sent)
  Private API with token auth:   ~ Low risk (attacker needs token)

Access-Control-Allow-Origin: [reflected origin] + Credentials: true
  ALWAYS DANGEROUS. This is the real vulnerability.
  Any website can make authenticated requests as the user.

BEST PRACTICE:
  Private API: whitelist specific origins, never use * or reflect
  Public API: * is fine, but don't allow credentials
```'''
    ),
    (
        "thinking/causal-websocket-disconnections",
        "Our WebSocket connections keep dropping every 60 seconds. Users get disconnected and have to reconnect. The server logs don't show any errors. What's going on?",
        r'''<think>
WebSocket disconnections every exactly 60 seconds with no server errors. Let me think about what causes this.

**Key clue: exactly 60 seconds, no server errors**
This means the server didn't close the connection. Something BETWEEN the client and server is closing it.

**Causal hypotheses:**

1. **Reverse proxy/load balancer timeout**
Most likely! Nginx, HAProxy, AWS ALB all have idle connection timeouts. Default is often 60 seconds.
- If no data flows for 60s, the proxy assumes the connection is dead and closes it.
- Server doesn't log an error because the proxy handled the close.

2. **Firewall/NAT timeout**
Network equipment drops idle connections after a timeout. NAT tables expire.

3. **Client-side timeout**
Browser or WebSocket library might have a default timeout.

**Most likely: proxy idle timeout.**

The fix: implement WebSocket ping/pong (heartbeat) frames to keep the connection alive. Send a ping every 30 seconds → proxy sees activity → doesn't timeout.

Let me also check: is this TCP keepalive vs WebSocket-level ping/pong?
- TCP keepalive: OS-level, typically 2-hour default interval, won't help with 60s proxy timeouts
- WebSocket ping/pong: application-level, configurable, the right solution
</think>

60-second disconnections with no server errors = **your reverse proxy or load balancer is killing idle connections**.

## Root Cause

```
YOUR SETUP:
  Client ←→ [Nginx / ALB / CloudFlare] ←→ Server

What's happening:
  t=0:    WebSocket connected ✓
  t=0-59: No messages sent (idle connection)
  t=60:   Proxy: "This connection has been idle for 60 seconds.
                  It's probably dead. Closing it."
  t=60:   Client: "Connection lost!" (reconnects)
  Server: no error logged (proxy closed the downstream TCP before informing server,
          or server sees a clean close, which isn't an "error")

The proxy has an idle timeout (default 60s in many configs).
WebSocket connections are LONG-LIVED but often IDLE.
The proxy doesn't know the difference between "idle" and "dead."
```

## Fix: WebSocket Heartbeat (Ping/Pong)

```python
# Server-side: send ping every 30 seconds
import asyncio
import websockets

async def handler(websocket):
    # websockets library handles ping/pong automatically
    # Just configure the interval:
    async for message in websocket:
        await process_message(message)

async def main():
    async with websockets.serve(
        handler,
        "0.0.0.0", 8765,
        ping_interval=30,    # Send ping every 30 seconds
        ping_timeout=10,     # Wait 10s for pong before considering dead
    ):
        await asyncio.Future()  # Run forever
```

```javascript
// Client-side: handle reconnection + heartbeat
class WebSocketClient {
    constructor(url) {
        this.url = url;
        this.connect();
    }

    connect() {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            console.log('Connected');
            // Send heartbeat every 30 seconds
            this.heartbeat = setInterval(() => {
                if (this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'ping' }));
                }
            }, 30000);
        };

        this.ws.onclose = () => {
            clearInterval(this.heartbeat);
            console.log('Disconnected, reconnecting in 3s...');
            setTimeout(() => this.connect(), 3000);  // Auto-reconnect
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'pong') return;  // Heartbeat response
            this.handleMessage(data);
        };
    }
}
```

## Also Fix: Proxy Configuration

```nginx
# Nginx: increase WebSocket timeout
location /ws/ {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    # Increase idle timeout for WebSocket connections
    proxy_read_timeout 3600s;    # 1 hour instead of 60 seconds
    proxy_send_timeout 3600s;

    # But STILL use application-level heartbeats
    # because other proxies (CDN, cloud LB) may have their own timeouts
}
```

```
WHY BOTH heartbeat AND proxy config?

  Proxy timeout = safety net (close truly dead connections)
  Heartbeat = keep alive (prevent proxy from closing active connections)

  Set proxy timeout high (1 hour)
  Set heartbeat interval low (30 seconds)
  Heartbeat keeps the connection active; proxy catches truly dead ones.
```

## Diagnostic Checklist

```
WebSocket dropping regularly?

  Every ~60s  → Proxy idle timeout (Nginx default: 60s)
  Every ~120s → AWS ALB idle timeout (default: 60s, but configurable)
  Every ~300s → CloudFlare timeout (default: 100s)
  Random      → Network instability, server crash, or client-side issue

  Steps:
  1. Check proxy logs (not server logs — proxy is closing the connection)
  2. Check proxy timeout configuration
  3. Implement ping/pong heartbeat (30-second interval)
  4. Increase proxy timeout to 1 hour
  5. Implement client-side auto-reconnection
```'''
    ),
    (
        "thinking/analogy-database-sharding-to-library-system",
        "Our single PostgreSQL database is hitting performance limits at 100M rows. Someone suggested sharding. What is database sharding and when does it make sense?",
        r'''<think>
Database sharding — let me use the library system analogy.

**Library analogy:**
- One library (single database) has 100 million books (rows)
- Finding a specific book takes longer as the library grows
- The checkout desk (write operations) has a single queue
- Solution: open multiple branch libraries, each handling a portion of the collection

**Sharding = splitting data across multiple databases**
Each shard holds a subset of the data:
- Shard 1: users A-M
- Shard 2: users N-Z
Or by geography:
- Shard US: American users
- Shard EU: European users

**Where it maps:**
- One big library → one big database
- Multiple branches → multiple shards
- "Which branch has this book?" → shard routing/key
- "Return all books by author X" → cross-shard query (hard!)
- Catalog lookup → shard routing table

**Where it breaks down:**
- Libraries have physical constraints; databases can add RAM/CPU
- Cross-branch lending is easy; cross-shard queries are very hard
- Libraries don't need ACID transactions across branches

**When sharding makes sense:**
- AFTER you've exhausted: indexes, query optimization, connection pooling, read replicas, partitioning
- When a single machine can't handle the write throughput
- When data is naturally partitionable (by tenant, region, or user)
</think>

Think of sharding like **splitting one huge library into multiple branch libraries**, each serving a portion of the collection.

## The Analogy

```
ONE LIBRARY (single database):
  100 million books (rows)
  Finding a book: librarian searches entire catalog → slow
  Checkout desk: one queue, everyone waits → bottleneck
  Building is full: can't add more shelves → no more capacity

SHARDED LIBRARIES (multiple databases):
  Branch A-M: books by authors A through M (50M books)
  Branch N-Z: books by authors N through Z (50M books)

  Finding a book by Author "Smith":
    → Go to Branch N-Z (routing decision based on shard key)
    → Search only 50M books instead of 100M → faster

  Checkout: two separate desks → twice the throughput
  Space: each branch handles its own growth independently
```

## What Sharding Actually Means

```
BEFORE SHARDING (one database):
  [  PostgreSQL: 100M users, all tables  ]

AFTER SHARDING (multiple databases):
  [ Shard 1: users 1-25M       ]
  [ Shard 2: users 25M-50M     ]
  [ Shard 3: users 50M-75M     ]
  [ Shard 4: users 75M-100M    ]

Each shard is a full PostgreSQL instance.
The application routes queries to the correct shard
based on a SHARD KEY (usually user_id).
```

## Before You Shard: Try These First

```
Sharding is COMPLEX and should be the LAST RESORT.
Try these first (in order):

1. INDEXES (minutes to implement)
   Are your slow queries using full table scans?
   One missing index can make a 100M row table 1000x slower.
   EXPLAIN ANALYZE your slow queries.

2. QUERY OPTIMIZATION (hours)
   N+1 queries? Unnecessary JOINs? SELECT * instead of specific columns?

3. CONNECTION POOLING (hours)
   PgBouncer: multiplex 1000 app connections into 50 DB connections.

4. READ REPLICAS (days)
   Primary handles writes. Replicas handle reads.
   Most apps are 90% reads → this 10x's your read capacity.

5. TABLE PARTITIONING (days)
   Split ONE table into partitions within the SAME database.
   PostgreSQL handles this natively:
   CREATE TABLE orders (...)
   PARTITION BY RANGE (created_at);
   -- Queries on recent data only scan recent partitions.

6. VERTICAL SCALING (minutes)
   Bigger instance: more RAM, more CPU, faster disk.
   Often the cheapest and fastest solution.

7. SHARDING (weeks to months)
   Only when ALL above are exhausted AND you need
   more write throughput than one server can handle.
```

## The Hard Parts of Sharding

```
WHAT GETS HARD:

1. CROSS-SHARD QUERIES (the library problem: "list ALL books by author X")
   SELECT * FROM users WHERE email = 'alice@example.com'
   → Which shard is this on? Need to query ALL shards. Slow.
   → Must route by shard key (user_id), not by other columns.

2. CROSS-SHARD JOINS
   SELECT * FROM users JOIN orders ON users.id = orders.user_id
   → If users and orders are on different shards: impossible to JOIN.
   → Must co-locate related data on the same shard.

3. CROSS-SHARD TRANSACTIONS
   Transfer money from User A (shard 1) to User B (shard 2)
   → No single database transaction spans both shards.
   → Need distributed transactions or saga pattern.

4. REBALANCING
   Shard 1 has 50M users, Shard 2 has 10M users (uneven growth)
   → Need to move data between shards. While live. Without downtime.

5. OPERATIONAL COMPLEXITY
   4 databases instead of 1:
   → 4× backup jobs, 4× monitoring, 4× upgrade procedures
   → Every schema migration runs on every shard
```

## When Sharding DOES Make Sense

```
✓ Write throughput exceeds single server capacity
  (> 10,000 writes/second on a large instance)

✓ Data is naturally partitioned
  (multi-tenant SaaS: each tenant's data is independent)
  (geographic: US data, EU data, APAC data)

✓ Dataset exceeds single server storage/RAM
  (> 10TB, can't fit working set in RAM)

✓ Regulatory requirements
  (EU data must stay in EU → geographic sharding)

FOR YOUR 100M ROWS:
  100M rows in PostgreSQL is NOT large enough to require sharding.
  PostgreSQL handles billions of rows with proper indexing.
  Your performance issues are almost certainly:
    → Missing indexes
    → Unoptimized queries
    → Insufficient connection pooling
    → Need for read replicas
  Try these first. You'll likely never need to shard.
```'''
    ),
    (
        "thinking/multiperspective-pair-programming-value",
        "Is pair programming worth it? Half my team thinks it's a waste — two people doing one person's work. The other half says it catches bugs and shares knowledge. How do I decide?",
        r'''<think>
Pair programming debate. Multiple perspectives here.

**Manager perspective (efficiency):**
Two people, one computer = 50% productivity? Not necessarily.
Research shows pairs produce code with fewer bugs, but it takes ~15% more total person-hours.
However, debugging time drops significantly. Net effect depends on the project.

**Senior developer perspective:**
"I can code faster alone. Pairing slows me down."
True for routine work. But for complex, unfamiliar, or critical code, a second brain catches design issues that would take days to find later.

**Junior developer perspective:**
"Pairing with a senior is the fastest way I've ever learned."
Knowledge transfer through pairing is far more effective than documentation.
Junior gets context, patterns, and intuition that can't be written down.

**Team perspective:**
Without pairing: knowledge silos. "Only Alice knows the billing system."
With pairing: shared ownership. Anyone can work on any part of the codebase.
Bus factor improves from 1 to 2+ for every component.

**Quality perspective:**
Pair programming is continuous code review. Bugs caught during writing, not during review (which is hours or days later). This is more effective but also more draining.

The answer isn't "always pair" or "never pair." It's "pair when the benefits outweigh the costs."
</think>

Both sides are right — for different situations. Let me break it down.

## The Perspectives

### "It's Wasteful" Camp

```
Valid points:
  ✓ Routine work (CRUD endpoints, simple bug fixes): one person is enough
  ✓ Tasks with a clear solution: second person adds little value
  ✓ It's mentally exhausting — 8 hours of pairing is unsustainable
  ✓ Some developers think better alone (deep focus, introversion)
  ✓ Raw lines-of-code output is lower when pairing
```

### "It's Valuable" Camp

```
Valid points:
  ✓ Complex/unfamiliar code: second brain catches design issues early
  ✓ Knowledge sharing: eliminates "only Alice knows billing"
  ✓ Fewer bugs: continuous review catches mistakes during writing
  ✓ Onboarding: fastest way to bring new team members up to speed
  ✓ Focus: harder to get distracted when someone is watching
  ✓ Better design: talking through problems leads to simpler solutions
```

## When Pairing Pays Off (And When It Doesn't)

```
PAIR FOR:                              DON'T PAIR FOR:
─────────────────────────────────────────────────────────
Complex design decisions               Routine CRUD endpoints
Critical/risky code (payments, auth)   Simple bug fixes with clear cause
Onboarding new team members            Tasks with a known solution
Unfamiliar codebase/technology         Writing documentation
Debugging a hard-to-reproduce bug      Mechanical refactoring
Code that affects the whole team        Personal side tasks
Cross-team knowledge transfer          Exploratory prototyping (solo first)

Rule of thumb:
  If the task benefits from a SECOND BRAIN → pair
  If the task only needs MORE HANDS → don't pair
```

## Practical Implementation

```
DON'T mandate "pair programming 100% of the time."
DO make pairing an AVAILABLE TOOL with specific use cases.

1. ONBOARDING PAIRS (first 2 weeks of new hire):
   New hire pairs with experienced dev for ~4 hours/day.
   Fastest onboarding method. Knowledge transfer by osmosis.
   Remaining 4 hours: solo exploration, reading docs.

2. COMPLEX FEATURE PAIRS:
   "This payment integration touches 5 services."
   Two developers pair for the design + critical implementation.
   Then split up for the routine parts.

3. BUG INVESTIGATION PAIRS:
   "This bug has been open for 3 days."
   Fresh eyes from a second developer often solve it in 30 minutes.

4. OPTIONAL DAILY PAIRING SLOT:
   "2-4 PM is pairing time. Grab a partner if you want one."
   Not mandatory. But available.

MAX PAIRING: 4-5 hours/day. More than that = burnout.
Alternate: 25 minutes pairing, 5 minutes break (Pomodoro).
```

## The Data

```
Research findings (Cockburn & Williams, 2001 + subsequent studies):

  TIME COST:
    Pairs spend ~15% more total person-hours than solo developers
    (NOT 100% more — the second person adds far less than double)

  QUALITY BENEFIT:
    Pairs produce ~15% fewer bugs
    Bug fixing time reduced by ~50%
    Net effect: roughly equal total cost, but higher quality code

  KNOWLEDGE BENEFIT: (hardest to measure, biggest long-term impact)
    Bus factor improves from 1 to 2+ per component
    Onboarding time reduced by ~40%
    Code consistency improves (shared standards)

  BOTTOM LINE:
    For complex, critical, or knowledge-sharing tasks: pairing is worth it.
    For routine tasks: solo is more efficient.
    The optimal is SELECTIVE pairing, not all-or-nothing.
```'''
    ),
    (
        "thinking/uncertainty-database-migration-zero-downtime",
        "We need to rename a column in our production database from 'user_name' to 'username'. Our app serves 100 requests per second. Can we just run ALTER TABLE RENAME COLUMN?",
        r'''<think>
Column rename on a live production database. Let me think about this carefully.

**Can you just ALTER TABLE RENAME COLUMN?**
In PostgreSQL: ALTER TABLE users RENAME COLUMN user_name TO username;
This takes a brief ACCESS EXCLUSIVE lock. For PostgreSQL, this is metadata-only and very fast (milliseconds). It doesn't rewrite the table.

BUT: the application code still references `user_name`. The moment the column is renamed, all queries using `user_name` will fail. At 100 rps, that's 100 errors per second until you deploy new code.

**The timing problem:**
- If you deploy code first (references `username`): app crashes because column is still `user_name`
- If you rename column first: app crashes because code references `user_name`
- If you do both simultaneously: there's always a gap

**Confidence assessment:**
- 40% "just do it" if your deployment is fast enough (< 1 second gap)
- 50% use the expand-contract pattern (zero downtime, more work)
- 10% use a database view as an alias (clever but adds complexity)

For 100 rps, a 1-second gap = 100 failed requests. Whether that's acceptable depends on your SLA.
</think>

**Don't just rename it** — you'll get errors during the gap between rename and code deploy. Confidence: **50%** for the expand-contract approach.

## The Problem

```
Option 1: Rename column, then deploy code
  t=0:    ALTER TABLE users RENAME COLUMN user_name TO username;
  t=0-30s: Code still references 'user_name' → EVERY query fails
  t=30s:  New code deployed → queries use 'username' → works
  RESULT: 30 seconds × 100 rps = 3,000 failed requests

Option 2: Deploy code, then rename column
  t=0:    New code deployed, references 'username'
  t=0-5s: Column is still 'user_name' → EVERY query fails
  t=5s:   ALTER TABLE RENAME → works
  RESULT: 5 seconds × 100 rps = 500 failed requests

Option 3: Do both at the same moment
  → Impossible. There's always a gap, even if milliseconds.
```

## The Safe Way: Expand-Contract Pattern

```sql
-- STEP 1: ADD new column (non-breaking)
ALTER TABLE users ADD COLUMN username VARCHAR(255);
UPDATE users SET username = user_name;
-- Both columns exist. Old code uses user_name. No errors.

-- STEP 2: Deploy code that writes to BOTH columns
-- Application code:
--   INSERT: writes to BOTH user_name AND username
--   SELECT: reads from user_name (still the source of truth)
-- No errors. Both columns stay in sync.

-- STEP 3: Deploy code that reads from NEW column
-- Application code:
--   INSERT: writes to BOTH
--   SELECT: reads from username (new column is now the source of truth)
-- No errors.

-- STEP 4: Deploy code that ONLY uses new column
-- Application code:
--   INSERT: writes to username only
--   SELECT: reads from username only
-- user_name column is now unused.

-- STEP 5: DROP old column (cleanup)
ALTER TABLE users DROP COLUMN user_name;
-- No code references it. Safe to remove.
```

## The Quick Way (If Downtime Is Acceptable)

```sql
-- For PostgreSQL: column rename is metadata-only (milliseconds, not minutes)
-- If 100-500 errors are acceptable:

-- 1. Prepare the new code but don't deploy yet
-- 2. Put app in maintenance mode (optional, avoids errors)
-- 3. Rename:
ALTER TABLE users RENAME COLUMN user_name TO username;
-- Takes < 100ms in PostgreSQL (no table rewrite)
-- 4. Deploy new code immediately
-- 5. Exit maintenance mode

-- Total downtime: 5-30 seconds
-- Acceptable for many internal apps, not for payment systems
```

## The Clever Way: Database View

```sql
-- Create a view that aliases both names:
CREATE VIEW users_v AS
  SELECT *, user_name AS username FROM users;

-- Code can use either column name through the view.
-- Migrate code at your leisure.
-- Once all code uses 'username', rename the actual column and drop the view.
```

## Decision

```
100 rps, need zero downtime:
  → Expand-contract pattern (3-4 deploys over a few days)

100 rps, 30 seconds of errors is OK:
  → Just rename + deploy quickly (simpler)

100 rps, internal tool, maintenance window available:
  → Maintenance mode + rename + deploy (simplest)

The right choice depends on your SLA and risk tolerance.
```'''
    ),
    (
        "thinking/firstprinciples-why-git-branches",
        "Why do we use git branches? I'm a junior developer and my team uses feature branches, but I don't understand why we can't just all commit to main.",
        r'''<think>
Git branches from first principles. Why not just all commit to main?

**The root problem: concurrent development**
Multiple developers working on the same codebase simultaneously. Without branches:
- Developer A is halfway through a feature (code is broken)
- Developer A commits to main (main is now broken)
- Developer B pulls main to start their work (gets broken code)
- Developer B can't test their changes because main is broken
- Developer C deploys main to production (production is broken)

**What branches solve:**
1. Isolation: your work-in-progress doesn't affect others
2. Code review: changes are reviewed before merging (pull requests)
3. CI/CD: main always works, deploys are safe
4. Experimentation: try an approach without risk

**Without branches:**
- Main is frequently broken
- No code review before changes enter main
- Deploys are risky (who knows what half-finished code is in main?)
- No way to experiment without affecting everyone

**The simple analogy:**
- Main = the published book
- Feature branch = your draft chapter
- Pull request = editor review
- Merge = chapter added to the book

You write drafts privately, get them reviewed, THEN publish. You don't edit the published book directly.
</think>

Let me show you what happens without branches, then why they exist.

## What Happens Without Branches

```
EVERYONE COMMITS TO MAIN:

  Monday 9am: Main works. App deploys fine.

  Monday 10am: Alice starts a new feature.
    Commits half-finished code to main.
    Main is now BROKEN (feature is incomplete).

  Monday 11am: Bob pulls main to start his bug fix.
    Gets Alice's half-finished code. Tests fail.
    "Why is main broken?" → Slack messages, confusion.

  Monday 2pm: Alice finishes and commits.
    Main works again... but Bob's bug fix is based on
    the broken version. His changes conflict.

  Monday 3pm: Carol deploys main to production.
    Alice's feature is included but untested.
    Production breaks. Users are affected.

  RESULT: broken main, blocked developers, risky deploys.
```

## What Branches Fix

```
WITH FEATURE BRANCHES:

  Monday 9am: Main works. Always.

  Monday 10am: Alice creates branch 'feature/user-profiles'
    Commits freely. Her branch, her mess.
    Main is still working. Bob is unaffected.

  Monday 11am: Bob creates branch 'fix/login-bug'
    Starts from working main. Tests pass.
    Works independently of Alice.

  Monday 2pm: Alice finishes. Opens a Pull Request.
    Team reviews her code. CI runs tests.
    Everything passes → merge to main.
    Main still works (tested before merge).

  Monday 3pm: Carol deploys main to production.
    Only reviewed, tested code is in main.
    Production is safe.

  RESULT: main always works, no developer blocking, safe deploys.
```

## Branches = Parallel Universes

```
                    main (always works)
                      │
                      ├── feature/user-profiles (Alice's universe)
                      │     She can break things here.
                      │     Nobody else is affected.
                      │     When ready → merge back to main
                      │
                      ├── fix/login-bug (Bob's universe)
                      │     He fixes independently.
                      │     Doesn't need Alice's code.
                      │     When ready → merge back to main
                      │
                      └── experiment/new-ui (Carol's universe)
                            She tries a wild idea.
                            If it doesn't work → delete the branch.
                            Main was never touched. Zero risk.
```

## The Workflow (Feature Branch + Pull Request)

```bash
# 1. Create a branch for your work
git checkout main
git pull                               # Get latest main
git checkout -b feature/add-search     # Create your branch

# 2. Work on your branch (commit as much as you want)
git add .
git commit -m "Add search input component"
git commit -m "Connect search to API"
git commit -m "Add loading state"
# These commits only exist on YOUR branch.
# Main is untouched.

# 3. Push and open a Pull Request
git push -u origin feature/add-search
# Open PR on GitHub → team reviews your code
# CI runs tests automatically
# Reviewers approve

# 4. Merge to main (after review + tests pass)
# Click "Merge" on GitHub
# Your code is now in main — reviewed, tested, safe.

# 5. Clean up
git checkout main
git pull
git branch -d feature/add-search
```

## Why This Matters

```
Without branches:
  ✗ Main breaks regularly
  ✗ No code review before changes enter main
  ✗ Deploys are risky
  ✗ Can't experiment without affecting everyone
  ✗ Developers block each other

With branches:
  ✓ Main always works (deployable at any time)
  ✓ Code is reviewed before merging (Pull Requests)
  ✓ CI runs tests on every PR (bugs caught before merge)
  ✓ Developers work independently (no blocking)
  ✓ Experiments are risk-free (just delete the branch)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
