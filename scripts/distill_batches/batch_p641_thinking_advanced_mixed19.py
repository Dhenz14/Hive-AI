"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 19)"""

PAIRS = [
    (
        "thinking/multiperspective-static-vs-dynamic-typing",
        "Our team is split on whether to use TypeScript or stay with plain JavaScript. The TypeScript advocates say it catches bugs, but the JS advocates say it slows development. Who's right?",
        r'''<think>
TypeScript vs JavaScript debate — a genuine multi-perspective analysis.

**TypeScript advocates' perspective:**
- Types catch bugs at compile time (undefined is not a function, property doesn't exist)
- IDE support is dramatically better (autocomplete, refactoring, go-to-definition)
- Types serve as documentation (function signatures tell you what to pass)
- Refactoring is safer (rename a field → compiler shows every usage)
- Catches API contract mismatches early

**JavaScript advocates' perspective:**
- TypeScript adds overhead: writing types, fixing type errors, configuring tsconfig
- For small projects/prototypes, types slow you down
- Type gymnastics: sometimes fighting the type system to express valid JS patterns
- Build step required (compilation)
- Third-party library types can be wrong or missing
- Learning curve for team members unfamiliar with type systems

**My analysis:**
Both are right — it depends on project characteristics:
- Small scripts, prototypes, POCs → JS is fine
- Large codebase, multiple developers, long-lived → TypeScript's ROI is very high
- The break-even point is roughly: if the project will live >6 months AND have >2 developers, TypeScript wins

**The often-missed nuance:**
TypeScript's biggest value isn't catching type errors — it's enabling IDE tooling. Autocomplete, inline documentation, safe refactoring — these compound over time.
</think>

Both sides are partially right. The answer depends on your project's characteristics.

## Each Perspective's Strongest Argument

```
TYPESCRIPT ADVOCATES:
  Strongest: "When we renamed the 'userId' field to 'user_id' in the
  API response, TypeScript showed us every place in the frontend that
  needed updating. In JS, we'd have found them via runtime crashes."

  This is real. Refactoring a large JS codebase is terrifying.
  Refactoring a TS codebase is routine.

JAVASCRIPT ADVOCATES:
  Strongest: "We spent 2 hours fighting the type system to express a
  perfectly valid pattern. The JS version was 3 lines. The TS version
  was 20 lines of generics and type assertions."

  This is also real. TypeScript's type system has sharp edges,
  especially with dynamic patterns, HOCs, and metaprogramming.
```

## When Each Wins

```
JAVASCRIPT WINS:
  ✓ Quick scripts and automation (< 500 lines)
  ✓ Prototypes and proof-of-concepts (might be thrown away)
  ✓ Solo developer who knows the codebase intimately
  ✓ Highly dynamic code (metaprogramming, code generation)
  ✓ Team has no TypeScript experience and deadline is tight

TYPESCRIPT WINS:
  ✓ Codebase > 5,000 lines (complexity justifies the investment)
  ✓ Multiple developers (types communicate intent between people)
  ✓ Long-lived project (>6 months — ROI compounds over time)
  ✓ API boundaries (types catch contract mismatches at compile time)
  ✓ Refactoring is frequent (types make it safe)

THE BREAK-EVEN POINT:
  Project will live > 6 months AND has > 2 developers → TypeScript
  Quick prototype OR solo dev → JavaScript (or gradual TS adoption)
```

## The Often-Missed Argument

```
TypeScript's biggest value ISN'T catching type errors.
It's enabling IDE TOOLING:

  JavaScript IDE experience:
    - Autocomplete: maybe, often wrong
    - "Go to definition": sometimes works
    - Refactoring: find-and-replace, hope for the best
    - Function signature: read the source code or docs

  TypeScript IDE experience:
    - Autocomplete: always accurate, shows all available methods
    - "Go to definition": always works
    - Refactoring: rename symbol → every usage updated correctly
    - Function signature: inline, with all parameter types
    - Error on save: "Property 'nmae' doesn't exist, did you mean 'name'?"

  This compounds over time:
    Day 1: "TypeScript is slower, I have to write types"
    Month 1: "TypeScript is about the same speed"
    Month 6: "I can't believe we ever worked without types"
    Year 1: "TypeScript SAVED us when we refactored the user model"
```

## The Practical Path: Gradual Adoption

```jsonc
// tsconfig.json — start permissive, tighten over time
{
  "compilerOptions": {
    "allowJs": true,           // Mix JS and TS files
    "checkJs": false,          // Don't type-check JS files yet
    "strict": false,           // Permissive to start
    "noImplicitAny": false,    // Allow 'any' everywhere initially
    "outDir": "./dist",
    "target": "ES2020"
  }
}

// Phase 1: Rename .js → .ts for new files only
// Phase 2: Add types to critical paths (API boundaries, data models)
// Phase 3: Enable "strict": true gradually
// Phase 4: Convert remaining JS files as you touch them

// This gives you IMMEDIATE benefits (IDE support for .ts files)
// without the cost of converting everything at once.
```

## My Recommendation

```
For your situation (team split, existing JS codebase):

1. Don't force a big rewrite to TypeScript
2. Adopt TypeScript for NEW code
3. Enable allowJs so old JS and new TS coexist
4. Convert existing files when you're already modifying them
5. Start with strict: false and tighten over 3-6 months

This way:
  - JS advocates keep writing JS (for now)
  - TS advocates use TS for new code
  - The team sees benefits gradually
  - No big-bang migration risk
```'''
    ),
    (
        "thinking/firstprinciples-why-caching",
        "Why do we need caching? Can't we just make our database faster?",
        r'''<think>
Caching from first principles. Why does it exist?

**The fundamental physics problem:**
Different storage media have different speed/cost tradeoffs:
- CPU register: 0.3 ns (fastest, tiny)
- L1 cache: 1 ns
- L2 cache: 3 ns
- L3 cache: 10 ns
- RAM: 100 ns
- SSD: 100,000 ns (100 μs)
- Network (database): 1,000,000 ns (1 ms)
- Network (external API): 100,000,000 ns (100 ms)

The fastest database query is ~1ms. RAM access is ~100ns. That's a 10,000x difference. No amount of database optimization can close this gap — it's a physics limitation.

**The key insight:** most data is read far more than it's written. If 95% of requests are reads, you can serve 95% of requests from RAM instead of hitting the database.

**What caching trades:**
- Speed: much faster (10,000x for RAM vs database)
- Cost: RAM is expensive, but you only cache HOT data
- Correctness: cached data might be STALE (the fundamental trade-off)

Caching is fundamentally about exploiting the temporal locality of data access — recently accessed data is likely to be accessed again soon.
</think>

You can't make a database faster than physics allows. Caching exists because of a fundamental speed gap between storage tiers.

## The Physics Problem

```
ACCESS TIME BY STORAGE TIER:
  CPU register:     0.3 ns
  L1 cache:         1 ns
  L2 cache:         3 ns
  RAM:              100 ns          ← application cache lives here
  SSD:              100,000 ns      ← database storage lives here
  Database query:   1,000,000 ns    ← network + query + disk
  External API:     100,000,000 ns  ← internet round trip

  RAM vs Database = 100 ns vs 1,000,000 ns = 10,000x faster

  No amount of database optimization can close a 10,000x gap.
  You could have the fastest database in the world and RAM is
  still 10,000x faster. This is physics, not engineering.
```

## The Insight: Read/Write Ratio

```
Most applications: 95% reads, 5% writes

WITHOUT CACHING:
  100 requests → 100 database queries
  Each query: ~5ms
  Total database load: 500ms of query time

WITH CACHING:
  100 requests → 5 database queries (cache misses) + 95 cache hits
  Each cache hit: ~0.1ms (from RAM)
  Each cache miss: ~5ms (from database)
  Total: 95 × 0.1 + 5 × 5 = 9.5 + 25 = 34.5ms
  → 14x less total time
  → 20x less database load
  → Database has capacity for growth
```

## Caching in Practice

```python
# The simplest cache: dictionary in memory
user_cache = {}

def get_user(user_id):
    if user_id in user_cache:
        return user_cache[user_id]  # ~0.1ms (RAM)

    user = db.query("SELECT * FROM users WHERE id = %s", user_id)  # ~5ms
    user_cache[user_id] = user
    return user

# Problem: cache grows forever, never updates
# Solution: TTL (time to live) + bounded size

# Using Redis (shared cache, production-ready)
import redis
import json

cache = redis.Redis()

def get_user(user_id):
    cached = cache.get(f"user:{user_id}")
    if cached:
        return json.loads(cached)  # ~1ms (Redis, network)

    user = db.query("SELECT * FROM users WHERE id = %s", user_id)  # ~5ms
    cache.setex(f"user:{user_id}", 300, json.dumps(user))  # Cache for 5 min
    return user
```

## The Fundamental Trade-off: Speed vs Freshness

```
CACHING TRADES FRESHNESS FOR SPEED:

  Database: always current, but slow
  Cache: possibly stale, but fast

  The question is: how stale is acceptable?

  EXAMPLES:
  User's profile picture:    cache 1 hour  (rarely changes)
  Product price:             cache 5 min   (changes occasionally)
  Stock price:               cache 1 sec   (changes constantly)
  Account balance:           don't cache   (must be current)

  STRATEGIES:
  TTL (Time To Live):     "This data expires after 5 minutes"
  Write-through:          "Update cache when database updates"
  Cache invalidation:     "Delete cache entry when data changes"
  Event-driven:           "Publish event on change → clear cache"
```

## When NOT to Cache

```
DON'T CACHE:
  - Data that must be real-time (financial balances, inventory counts)
  - Data that's unique per request (never reused)
  - Data that changes every request (counters, timestamps)
  - When cache adds complexity but little benefit (low traffic)

ALWAYS CACHE:
  - Database queries that run identically many times
  - Computed results that are expensive to regenerate
  - External API responses (slow + rate limited)
  - Static assets (images, CSS, JS)
```

**"Can't we just make the database faster?"** — you can, and you should. But a fast database serving 1,000 queries/second is still slower than a cache serving 100,000 reads/second. Caching doesn't replace optimization — it complements it.'''
    ),
    (
        "thinking/causal-git-merge-conflicts-every-day",
        "Our team gets merge conflicts on almost every pull request. We're only 4 developers. What's causing this and how do we fix it?",
        r'''<think>
Daily merge conflicts for a 4-person team. This is a process/workflow problem, not a git problem.

**Causal analysis — why do merge conflicts happen?**
Two people modify the same lines in the same file. The more this happens:
1. Long-lived branches (days or weeks) → more divergence → more conflicts
2. Large files that everyone touches (e.g., one huge models.py)
3. No clear code ownership → everyone edits everything
4. Auto-generated files in git (package-lock.json, migrations)
5. Poor code architecture → too many things in one file

**For a 4-person team getting DAILY conflicts:**
The most likely cause is long-lived branches. If branches live for days, they diverge significantly from main. When two long-lived branches both modify common files → conflict.

**Second likely cause:** a few "god files" that everyone touches — one giant app.py, one shared utility file, one huge test file.

**Solutions:**
1. Short-lived branches (merge within 1 day)
2. Small PRs (fewer files changed → fewer potential conflicts)
3. Trunk-based development
4. Break up large files
5. Rebase frequently (keep your branch up to date with main)
</think>

For 4 developers, daily conflicts means your **branches live too long** and/or you have **files that everyone touches**.

## Root Cause Analysis

```
MERGE CONFLICTS HAPPEN WHEN:
  Two people modify the SAME LINES in the SAME FILE.

FOR A 4-PERSON TEAM, THIS MEANS:
  1. Branches live too long (days/weeks → massive divergence)
  2. "God files" that everyone edits (shared models.py, utils.py, config)
  3. Auto-generated files in git (migrations, lock files)
  4. Large PRs that touch many files

DIAGNOSIS:
  Which files cause the most conflicts? → likely your "god files"
  How long do branches live? → likely too long
```

```bash
# Find which files cause the most conflicts
git log --all --oneline --diff-filter=M --name-only -- '*.py' \
  | sort | uniq -c | sort -rn | head -20
# Files at the top are your "conflict magnets"
```

## Fix 1: Short-Lived Branches (Most Important)

```
BEFORE (long-lived branches):
  main:  ─────────────────────────────────────────→
  Alice:  ──branch──────────5 days───────────merge→  ← BIG divergence
  Bob:    ────branch──────4 days──────────merge→     ← conflicts guaranteed

AFTER (short-lived branches):
  main:  ──A──B──A──B──A──B──────→
  Alice:  ─┘  └─┘  └─┘  └─      ← branch lives < 1 day
  Bob:    ────┘  └─┘  └─┘       ← merge before significant divergence

RULES:
  □ Branches should live < 1 day (ideally hours)
  □ If a feature takes 3 days, break it into 3 PRs
  □ Merge to main at LEAST once per day
  □ Rebase your branch on main before opening PR
```

## Fix 2: Smaller PRs

```
LARGE PR (touches 20 files):
  Probability of conflict with ANY other PR = very high
  Time to review = 2 hours → sits in queue → more divergence

SMALL PR (touches 3-5 files):
  Probability of conflict = low
  Time to review = 15 minutes → merged quickly → less divergence

BREAKING UP LARGE FEATURES:
  Feature: "Add user profile page with avatar upload"

  ❌ One PR: model + API + upload + frontend + tests (20 files, 800 lines)

  ✅ Three PRs:
    PR 1: Add profile model and API endpoint (5 files, 150 lines)
    PR 2: Add avatar upload service (4 files, 200 lines)
    PR 3: Add frontend profile page (6 files, 250 lines)

  Each PR: reviewed and merged within hours, not days
```

## Fix 3: Break Up God Files

```python
# ❌ BEFORE: one models.py with 50 models (everyone edits this file)
# models.py — 2000 lines, touched by every PR

# ✅ AFTER: separate files per domain
# models/user.py — only changed when working on users
# models/order.py — only changed when working on orders
# models/product.py — only changed when working on products
# models/__init__.py — re-exports for backward compatibility

# Same applies to:
# utils.py (500 lines) → utils/string.py, utils/date.py, utils/auth.py
# tests.py (1000 lines) → tests/test_user.py, tests/test_order.py
# routes.py (800 lines) → routes/user_routes.py, routes/order_routes.py
```

## Fix 4: Handle Auto-Generated Files

```bash
# package-lock.json, poetry.lock, migration files cause many conflicts

# For lock files: always regenerate rather than manually resolving
# In .gitattributes:
package-lock.json merge=ours
poetry.lock merge=ours
# Then regenerate: npm install / poetry lock

# For migrations: use a linear migration strategy
# Django: python manage.py makemigrations --merge
# Alembic: ensure one migration chain (rebase if branched)
```

## Fix 5: Rebase Before PR

```bash
# Before opening a PR, update your branch:
git fetch origin
git rebase origin/main

# This puts YOUR changes on top of the latest main
# If there's a conflict, YOU resolve it (you know your code best)
# vs: resolving it during merge (might be someone who doesn't know your code)

# Team rule: "Always rebase on main before opening a PR"
```

## The Checklist

```
□ Branches live < 1 day
□ PRs touch < 10 files
□ Rebase on main before opening PR
□ Break up files that everyone touches
□ Handle lock file conflicts with regeneration
□ Review PRs within 2-4 hours (don't let them queue)
```'''
    ),
    (
        "thinking/adversarial-environment-variable-security",
        "We store all our secrets in environment variables. Our DevOps lead says this is secure because env vars aren't in the code. But I'm not sure. Is it really secure?",
        r'''<think>
Environment variables for secrets — this is a common misconception that env vars are inherently secure.

**Why people think env vars are secure:**
- "Not in code" = "not in git" = "secure" (incomplete reasoning)
- 12-factor app recommends env vars for config
- Better than hardcoding secrets, which is the actual bar being compared to

**Why env vars are NOT inherently secure:**

1. **Process listing** — `ps auxe` or `/proc/PID/environ` shows env vars of any process (same user)
2. **Child processes inherit** — every subprocess, shell command, log statement that dumps env gets ALL secrets
3. **Error reporting/crash dumps** — many error trackers capture env vars by default (Sentry, Datadog)
4. **Docker inspect** — `docker inspect container` shows all env vars in plaintext
5. **CI/CD logs** — env vars often leak in build logs
6. **Debugging tools** — debuggers, profilers can read process env
7. **Shared hosting** — other processes on same server can potentially read
8. **No access control** — can't give one service access to only its secrets
9. **No audit trail** — no log of who accessed which secret
10. **No rotation** — changing a secret requires restarting all services

**What's actually secure:**
Secret management tools: HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, GCP Secret Manager. These provide:
- Encryption at rest
- Access control (who can read which secret)
- Audit logging (who accessed what, when)
- Rotation (change secrets without restart)
- Dynamic secrets (temporary credentials)

For small teams/projects, env vars are a reasonable starting point but they should not be considered "secure" — just "better than hardcoding."
</think>

Environment variables are **better than hardcoding secrets in code**, but they are **not inherently secure**. Here's what can go wrong.

## How Env Vars Leak

```bash
# 1. PROCESS LISTING — any user on the same machine
ps auxe | grep your-app
# Shows ALL environment variables of your process
cat /proc/$(pgrep your-app)/environ | tr '\0' '\n'
# Reads env vars directly from the process

# 2. CHILD PROCESSES INHERIT EVERYTHING
# Your app runs a shell command:
import subprocess
subprocess.run(["some-tool", "--flag"])
# some-tool now has access to DATABASE_URL, API_KEY, JWT_SECRET, etc.
# If some-tool is compromised, all secrets are exposed

# 3. DOCKER INSPECT
docker inspect your-container | jq '.[0].Config.Env'
# Output: ["DATABASE_URL=postgres://user:password@host/db",
#          "API_KEY=sk-1234567890abcdef",
#          "JWT_SECRET=super-secret-value"]
# Anyone with Docker access sees all secrets in plaintext
```

## More Subtle Leaks

```python
# 4. ERROR REPORTING captures env vars by default
import sentry_sdk
sentry_sdk.init(dsn="...")
# Sentry captures os.environ on every error
# Your API keys are now in a third-party service's dashboard
# Fix: sentry_sdk.init(dsn="...", send_default_pii=False)

# 5. DEBUG LOGGING
import os
logger.debug(f"Starting app with config: {os.environ}")
# Congratulations, all secrets are now in your log files
# And log files get shipped to Datadog/ELK/CloudWatch

# 6. CI/CD BUILD LOGS
# GitHub Actions:
- run: echo "Deploying with $DATABASE_URL"
# This prints the secret in plain text in build logs
# GitHub masks secrets it knows about, but not all CI systems do

# 7. ENVIRONMENT FILE COMMITTED TO GIT
# .env file in the repo root — even in .gitignore,
# it was in the git history before being gitignored
git log --all --full-history -- .env
# If it was EVER committed, the secret is in git history forever
```

## The Security Ladder

```
LEVEL 0: Hardcoded in source code
  secrets = {"api_key": "sk-1234"}  ← WORST: in git forever
  Risk: anyone with repo access has all secrets

LEVEL 1: Environment variables (you are here)
  os.environ["API_KEY"]
  ← Better: not in git
  ← Still visible: process listing, docker inspect, crash dumps, child processes

LEVEL 2: Encrypted environment files
  .env.encrypted → decrypted at deploy time
  ← Better: encrypted at rest
  ← Still decrypted in process memory during runtime

LEVEL 3: Secret management service
  AWS Secrets Manager / HashiCorp Vault / Azure Key Vault
  ← Best: encrypted, access-controlled, audited, rotatable
```

## What a Secret Manager Provides (That Env Vars Don't)

```
                        ENV VARS    SECRET MANAGER
Encrypted at rest?      No          Yes
Access control?         No*         Yes (per-secret permissions)
Audit trail?            No          Yes (who accessed what, when)
Rotation?               Restart     Automatic, no restart
Dynamic secrets?        No          Yes (temporary DB credentials)
Centralized?            No          Yes (one source of truth)
Versioned?              No          Yes (roll back secret changes)

* "No" because anyone with server access can read all env vars
```

## Practical Recommendations

```
FOR SMALL TEAMS / EARLY STAGE:
  Environment variables are OK as a starting point, but:
  □ Never log os.environ or process.env
  □ Sanitize env vars in error reporting (Sentry, etc.)
  □ Don't pass secrets to child processes (clear env before subprocess)
  □ Use .env files only for development (never commit to git)
  □ Rotate secrets periodically (even manually)
  □ Limit who has SSH access to production servers

FOR GROWING TEAMS:
  Move to a secret manager:
  □ AWS Secrets Manager ($0.40/secret/month)
  □ HashiCorp Vault (free self-hosted)
  □ Doppler, 1Password Secrets Automation
  □ Even GitHub/GitLab CI secret variables (encrypted, masked in logs)

MINIMUM IMPROVEMENT TODAY:
  # Instead of raw env vars, at least use a library that:
  # 1. Validates required secrets exist at startup
  # 2. Masks secrets in logs
  # 3. Doesn't pass secrets to child processes
```

Env vars are better than hardcoding, but calling them "secure" is like saying "a screen door is secure because it's not an open doorway." It's a step up, but it's not the destination.'''
    ),
    (
        "thinking/backtrack-polling-to-webhooks-to-streaming",
        "I'm polling an API every 5 seconds to check for updates. It works but feels wrong. Is there a better way?",
        r'''<think>
Polling every 5 seconds — this works but is inefficient. Let me trace the evolution of real-time data patterns.

**Why polling feels wrong:**
- 95% of polls return "no new data" — wasted requests
- Adds latency (up to 5 seconds delay for new data)
- Wastes server resources processing empty polls
- Rate limiting risk from the API provider
- Doesn't scale (100 users × 12 polls/min = 1200 requests/min for nothing)

**Evolution:**
1. Polling → simplest, most wasteful
2. Long polling → better (server holds request until data available)
3. Webhooks → server pushes to you (event-driven, most efficient)
4. Server-Sent Events (SSE) → persistent one-way stream
5. WebSockets → persistent bidirectional connection

**Which to use depends on:**
- Do you control the API? (webhooks/SSE need server changes)
- Is it one-way or bidirectional?
- Is it third-party? (limited to what they offer)
</think>

Yes — polling is the worst approach for real-time updates. Let me show the evolution.

## Why Polling Is Wasteful

```
YOUR CURRENT APPROACH: poll every 5 seconds

  Client: "Any updates?"    Server: "No."
  Client: "Any updates?"    Server: "No."
  Client: "Any updates?"    Server: "No."
  Client: "Any updates?"    Server: "No."
  Client: "Any updates?"    Server: "Yes! Here's the data."
  Client: "Any updates?"    Server: "No."
  Client: "Any updates?"    Server: "No."
  ...

  Results: 95% of requests return nothing
  At scale: 1000 users × 12 polls/min = 12,000 requests/min
  Most of which return "no data"
```

## The Better Approaches (In Order)

### 1. Webhooks (Best for Third-Party APIs)

```python
# Instead of YOU asking "any updates?",
# the server TELLS YOU when something changes.

# You register a URL:
# POST /webhooks/register
# { "url": "https://your-app.com/webhook/orders", "events": ["order.created"] }

# When an event happens, THEY call YOUR endpoint:
@app.post("/webhook/orders")
async def handle_order_webhook(request):
    event = await request.json()

    # Verify webhook signature (prevent spoofing)
    signature = request.headers.get("X-Signature")
    if not verify_signature(event, signature, WEBHOOK_SECRET):
        return Response(status_code=401)

    if event["type"] == "order.created":
        process_new_order(event["data"])

    return Response(status_code=200)  # Always return 200 quickly

# Result: ZERO wasted requests. You only hear when something happens.
# Like a doorbell vs repeatedly opening the door to check.
```

### 2. Server-Sent Events (Best for One-Way Streaming)

```python
# Server pushes updates to client over a persistent HTTP connection
# Client just listens — no repeated requests

# SERVER (FastAPI/Starlette)
from sse_starlette.sse import EventSourceResponse

@app.get("/events/orders")
async def order_events(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            # Check for new events (from DB, queue, etc.)
            events = await get_new_events()
            for event in events:
                yield {"event": "order_update", "data": json.dumps(event)}
            await asyncio.sleep(1)  # Small delay between checks

    return EventSourceResponse(event_generator())

# CLIENT (JavaScript — built into browsers, no library needed)
const events = new EventSource('/events/orders');

events.addEventListener('order_update', (e) => {
    const order = JSON.parse(e.data);
    updateUI(order);
});

events.onerror = () => {
    // EventSource automatically reconnects!
    console.log('Connection lost, reconnecting...');
};
```

### 3. WebSockets (Best for Bidirectional Communication)

```python
# Both client and server can send messages at any time
# Use when client ALSO needs to send data (chat, collaboration, gaming)

# SERVER
from fastapi import WebSocket

@app.websocket("/ws/updates")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Server can push updates
            events = await get_new_events()
            for event in events:
                await websocket.send_json(event)

            # Client can also send messages
            data = await asyncio.wait_for(
                websocket.receive_json(), timeout=5.0
            )
            await handle_client_message(data)
    except WebSocketDisconnect:
        pass
```

## Decision Guide

```
DO YOU CONTROL THE SERVER?
  No  → Does the API offer webhooks?
        Yes → Use webhooks ✓
        No  → You're stuck with polling (but use long polling)

  Yes → Is communication one-way (server → client)?
        Yes → Use Server-Sent Events (SSE) ✓
              Simpler than WebSockets, auto-reconnect, works with HTTP/2

        No  → Use WebSockets ✓
              Chat, collaboration, gaming, anything bidirectional

QUICK REFERENCE:
  Polling:    Simple, wasteful, works everywhere
  Webhooks:   Event-driven, efficient, server pushes to YOUR endpoint
  SSE:        One-way stream, auto-reconnect, simple client
  WebSocket:  Bidirectional, lowest latency, more complex
```

If you can't change anything and must poll, at least use **exponential backoff** — poll every 5s when expecting updates, slow to every 30s during quiet periods.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
