"""Phase 2F: Advanced Reasoning — Uncertainty Calibration (Part 4/5)
Explicit confidence levels and conditions that change the answer:
performance optimization advice, library choice, when to rewrite, migration timing."""

PAIRS = [
    (
        "thinking/uncertainty-performance-optimization",
        "Our web app is slow. Where should we focus our optimization efforts?",
        r'''<think>
This is highly uncertain without specific data. I need to reason about what's LIKELY to be slow and be explicit about my confidence.

"Web app is slow" could mean many things:
- Slow page load (frontend)
- Slow API responses (backend)
- Slow under load (scaling)
- Slow for specific operations

Without profiling data, I'm essentially guessing. But I can give calibrated guesses based on common patterns.

Most likely bottlenecks (based on frequency across web apps):

1. Database queries — 70% confident this is the #1 bottleneck
   - N+1 queries, missing indexes, full table scans
   - This is the single most common performance issue in web apps
   - Easy to check: Django Debug Toolbar, pg_stat_statements
   - Conditions that change: if they're already using ORM efficiently, it might not be this

2. No caching — 60% confident this is a factor
   - Recalculating the same data on every request
   - Not caching database results, API responses, or computed values
   - Easy to add: Redis cache for frequently-read, rarely-changed data

3. Frontend bundle size / render blocking — 50% confident
   - Large JavaScript bundle blocking page render
   - Unoptimized images
   - No lazy loading
   - This is the bottleneck if "slow" means "slow initial page load"

4. External API calls in the request path — 40% confident
   - Calling Stripe, SendGrid, or other APIs synchronously
   - Each call adds 100-500ms to response time
   - Fix: make non-critical calls async

5. Missing HTTP caching — 35% confident
   - No Cache-Control headers
   - Browser re-fetches static assets on every page
   - CDN not configured

6. Inefficient code (algorithm/data structure) — 15% confident
   - Despite being a common suggestion, purely algorithmic slowness is rare in web apps
   - Most web apps are I/O bound, not CPU bound
   - Only relevant for: search, sorting large datasets, complex calculations

The key insight: 80% of web app performance issues are I/O related (database, network), not CPU. "Optimize your algorithm" is usually the wrong advice.

What would change my confidence:
- If they show me profiling data → I can be much more precise
- If it's a data-heavy app (analytics, reporting) → DB is 90% likely
- If it's a media app (images, video) → CDN/frontend is 80% likely
- If it's an API-only service → DB + external calls are 85% likely
- If it's slow only under load → scaling/connection pooling is the issue
</think>

Without profiling data, I'm estimating based on common patterns. Here's where I'd bet, with explicit confidence levels.

**Where the bottleneck probably is:**

| Likely cause | Confidence | Check in |
|---|---|---|
| Database queries (N+1, missing indexes) | 70% | 5 minutes |
| No caching (recalculating on every request) | 60% | 10 minutes |
| Frontend bundle / render blocking | 50% | 2 minutes |
| Synchronous external API calls | 40% | 5 minutes |
| No HTTP/CDN caching | 35% | 2 minutes |
| Inefficient algorithm | 15% | Last resort |

**Step 1 — Measure before optimizing (5 minutes):**

```python
# Backend: Where is time being spent?
# Add timing middleware
import time

@app.middleware("http")
async def timing(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - start) * 1000
    response.headers["Server-Timing"] = f"total;dur={duration:.0f}"
    if duration > 500:
        logger.warning(f"Slow request: {request.method} {request.url.path} {duration:.0f}ms")
    return response
```

```bash
# Frontend: Where is time being spent?
# Chrome DevTools → Performance tab → Record page load
# Or: Lighthouse audit
npx lighthouse https://yourapp.com --output=html
```

**Step 2 — Check the most likely cause first (database):**

```sql
-- PostgreSQL: Find the slowest queries
SELECT query, calls, mean_exec_time AS avg_ms,
       total_exec_time / 1000 AS total_sec
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- If you see queries taking > 100ms → add indexes or fix N+1
-- If all queries are < 10ms → database probably isn't the bottleneck
```

```python
# Django: Count queries per request
# pip install django-debug-toolbar
# If a page makes 50+ queries → N+1 problem → fix with select_related/prefetch_related
```

**Step 3 — Apply the fix for what you found:**

```python
# If database (70% likely):
# Fix N+1 queries and add missing indexes
# Usually turns 500ms → 50ms

# If no caching (60% likely):
# Add Redis caching for expensive queries
@lru_cache(maxsize=1000)  # Simple in-memory cache
def get_categories():
    return list(Category.objects.all())

# If frontend (50% likely):
# Lazy load routes, optimize images, add CDN
# Usually turns 4s load → 1.5s load

# If external APIs (40% likely):
# Move to background tasks
# Usually turns 800ms → 100ms
```

**What would make me change my answer:**

```
If you tell me...                      My confidence shifts:
────────────────────────────────────────────────────────
"It's slow on first load"             Frontend: 80%, DB: 30%
"API responses are 2+ seconds"        DB: 85%, External APIs: 60%
"It's fast with few users, slow       Scaling: 80%, Connection pool: 70%
 with many"
"Specific page is slow, others OK"    That page's queries: 90%
"Everything is slow"                  Infrastructure: 60%, DB: 50%
"Mobile is slow, desktop is fine"     Bundle size: 85%, images: 75%
```

**The meta-advice (95% confident):**

```
1. MEASURE before optimizing (never guess)
2. Fix the biggest bottleneck first (don't micro-optimize)
3. Database queries are the most likely bottleneck
4. A single missing index can turn 2s → 20ms
5. Caching eliminates the query entirely: 20ms → 0ms (cache hit)
```

Start with `EXPLAIN ANALYZE` on your slowest API endpoint's queries. That single command tells you more than any amount of speculation.'''
    ),
    (
        "thinking/uncertainty-when-to-rewrite",
        "We have a 5-year-old Python 2 codebase that's getting harder to maintain. Some team members want to rewrite it in a modern framework. Others want to incrementally upgrade. What should we do?",
        r'''<think>
The rewrite vs. incremental upgrade question is one of the most consequential decisions in software engineering. Joel Spolsky's "Things You Should Never Do" argues rewrites are almost always wrong. But Python 2 end-of-life makes this more nuanced.

Let me assess with calibrated uncertainty.

Factors favoring incremental upgrade:
1. Working code has years of bug fixes and edge case handling baked in
   - A rewrite loses all of this institutional knowledge
   - Bugs that were fixed over 5 years WILL reappear in the rewrite
   - 80% confident this is a serious risk

2. Business continues during upgrade
   - Incremental: ship features AND upgrade simultaneously
   - Rewrite: feature freeze for months (business suffers)
   - 75% confident feature freeze is unacceptable for most businesses

3. Lower risk of catastrophic failure
   - Incremental: if one upgraded module has issues, the rest still works
   - Rewrite: big-bang launch, everything can go wrong at once
   - 85% confident incremental is lower risk

Factors favoring rewrite:
1. Python 2 → Python 3 can be painful incrementally
   - Unicode handling changed fundamentally
   - Some libraries don't support both versions
   - BUT: 2to3 tool handles 90% of syntax changes automatically
   - 40% confident this is a valid argument for rewrite

2. The codebase might have deep architectural problems
   - If the architecture is fundamentally wrong, incremental improvement is polishing rust
   - But: you can refactor architecture incrementally too (strangler fig pattern)
   - 30% confident the architecture is bad enough to warrant rewrite

3. Team motivation
   - Developers hate working on old code
   - A rewrite is exciting and motivating
   - But: the excitement wears off after month 3 of rewriting boring business logic
   - 50% confident morale is a valid factor

Historical evidence:
- Netscape rewrote their browser → nearly killed the company
- Basecamp rewrites have been successful (but they're small team, simple product)
- Most successful "rewrites" are actually incremental replacements (strangler fig)

My assessment:
- 75% confident: incremental upgrade is the right choice
- 15% confident: rewrite is justified (if architecture is truly broken)
- 10% confident: it doesn't matter (team will succeed or fail regardless)

Conditions that would flip my answer:
- If the codebase is < 10K lines → rewrite is easy enough, go for it (70%)
- If the codebase is > 100K lines → incremental, no question (90%)
- If Python 2 dependencies have no Python 3 equivalent → might need rewrite for those modules
- If the team has already attempted incremental and failed → consider rewrite
</think>

This is one of the highest-stakes decisions in engineering. Let me give you my honest assessment with uncertainty spelled out.

**My baseline recommendation:**

| Approach | Confidence | When it's right |
|---|---|---|
| Incremental upgrade | 75% | Most cases, especially > 50K lines |
| Rewrite | 15% | Small codebase, broken architecture |
| Hybrid (strangler fig) | 10% | Large codebase with clear module boundaries |

**Why incremental wins (75% confident):**

```
The rewrite trap (Spolsky's Law):
  Year 1-2: "This is great! Clean code!"
  Year 3:   "Why are we rebuilding the same edge cases?"
  Year 4:   "The old system did this... how did it work?"
  Year 5:   "We've rewritten the same bugs differently"

What you lose in a rewrite:
  ✗ 5 years of bug fixes (they WILL re-surface)
  ✗ Edge cases discovered in production
  ✗ Domain knowledge embedded in code comments and weird if-statements
  ✗ Customer trust during the "feature freeze" period
  ✗ Team morale in month 6 of rewriting boring business logic

What you keep in an incremental upgrade:
  ✓ Working code stays working
  ✓ Ship features AND upgrade simultaneously
  ✓ Each step is independently verifiable
  ✓ Can stop at any point (partial upgrade is still useful)
```

**The incremental path for Python 2 → 3:**

```bash
# Phase 1: Automated conversion (handles 80% of changes)
pip install future
futurize --stage1 --write .  # Non-breaking Python 2+3 compatibility
futurize --stage2 --write .  # Python 3 style with compatibility

# Or use 2to3:
2to3 --write --nobackups .

# Phase 2: Fix what the tools can't
# Main issues:
# - Unicode: str vs bytes (the big one)
# - print() function vs statement
# - dict.keys() returns a view, not a list
# - Integer division: 3/2 = 1.5, not 1
```

```python
# Phase 3: Module-by-module verification
# Start with leaf modules (no dependencies), work inward

# Create a compatibility layer for the transition:
import sys
if sys.version_info[0] >= 3:
    string_types = (str,)
    text_type = str
else:
    string_types = (str, unicode)
    text_type = unicode
```

**When I'd recommend a rewrite (15% confident — specific conditions):**

```
Rewrite IF ALL of these are true:
  □ Codebase is < 20K lines (manageable to rewrite)
  □ Architecture is fundamentally wrong (not just messy code)
  □ Key dependencies have no Python 3 equivalent
  □ Team has < 6 months of business-critical deadlines
  □ You can keep the old system running during the rewrite

If even ONE of these is false → incremental is safer.
```

**The hybrid approach (strangler fig) — if the codebase is large:**

```
Old System (Python 2)              New System (Python 3)
┌────────────────────┐            ┌────────────────────┐
│ Users module       │──migrate──→│ Users module (new)  │
│ Orders module      │            │                     │
│ Payments module    │            │                     │
│ Reports module     │            │                     │
└────────────────────┘            └────────────────────┘

Step 1: New "Users" service in Python 3
Step 2: Route user requests to new service
Step 3: Old system calls new Users service
Step 4: Repeat for Orders, then Payments...
Step 5: Old system eventually has nothing left → decommission

Each step is independently deployable and reversible.
```

**What would change my recommendation:**

```
If you tell me...                    My confidence shifts:
────────────────────────────────────────────────────────
"Codebase is 5K lines"              Rewrite: 60% (small enough)
"Codebase is 200K lines"            Incremental: 90% (too big to rewrite)
"Architecture is MVC, just old"      Incremental: 85% (good bones)
"It's a ball of mud, no structure"   Rewrite: 35% (but strangler fig is still safer)
"We tried incremental, it failed"    Rewrite: 50% (evidence that incremental doesn't work here)
"Business can't pause features"      Incremental: 95% (rewrite = feature freeze)
"We have 6 months of runway"         Incremental: 99% (can't afford rewrite risk)
```

My honest advice: the boring answer (incremental) is almost always the right one. The exciting answer (rewrite) feels better but has a much higher failure rate. Start with `futurize`, fix module by module, ship Python 3 code alongside Python 2, and cut over when ready.'''
    ),
    (
        "thinking/uncertainty-library-choice",
        "I need an HTTP client library for Python. Should I use requests, httpx, aiohttp, or urllib3?",
        r'''<think>
This is a question where the right answer depends on context. Let me assess each option with confidence levels based on different scenarios.

The libraries:
- requests: the classic, everyone knows it, synchronous only
- httpx: modern, supports async AND sync, requests-compatible API
- aiohttp: async-only, mature, higher performance
- urllib3: low-level, used internally by requests, not usually used directly

My default recommendation: httpx (70% confident for most projects)
Why:
- Supports both sync and async (future-proof)
- API is nearly identical to requests (easy migration)
- HTTP/2 support built in
- Modern, actively maintained
- Type hints included

But context changes this significantly:

Scenario 1: Existing project using requests
- 85% confident: keep using requests (unless adding async)
- Switching libraries for no reason adds risk and work
- Only switch if you're adding async support

Scenario 2: New async project (FastAPI, etc.)
- 75% confident: httpx
- 20% confident: aiohttp
- httpx is simpler, aiohttp has more features for high-throughput

Scenario 3: High-throughput scraping/crawling
- 60% confident: aiohttp (best raw performance for async I/O)
- 30% confident: httpx (simpler, good enough for most volumes)
- aiohttp has been battle-tested for high-concurrency scenarios

Scenario 4: Simple script, not a long-term project
- 80% confident: requests (simplest, everyone knows it)
- No need for async, no need for modern features

Scenario 5: Library/package that others will use
- 60% confident: httpx (modern, well-typed)
- 30% confident: requests (largest user base, most familiar)
- Consider: which dependency is more acceptable to your users?

Conditions that change my answer:
- "We need HTTP/2" → httpx or aiohttp (requests doesn't support it)
- "We need connection pooling with fine control" → urllib3 or aiohttp
- "We need streaming uploads/downloads" → httpx or aiohttp
- "Team is unfamiliar with async" → requests or httpx (sync mode)
</think>

The right choice depends on your project type. Here's my calibrated recommendation.

**Quick answer by scenario:**

| Your situation | Recommendation | Confidence |
|---|---|---|
| New project, might need async later | httpx | 70% |
| Existing project using requests | Keep requests | 85% |
| New async project (FastAPI) | httpx | 75% |
| High-throughput scraping | aiohttp | 60% |
| Quick script / prototype | requests | 80% |
| Library other devs will import | httpx | 60% |

**Why httpx is my default (70% confident):**

```python
# httpx gives you everything requests does + async + HTTP/2

# Synchronous (same API as requests):
import httpx
response = httpx.get("https://api.example.com/users")
data = response.json()

# Async (same API, just add async/await):
async with httpx.AsyncClient() as client:
    response = await client.get("https://api.example.com/users")
    data = response.json()

# HTTP/2 (just flip a flag):
async with httpx.AsyncClient(http2=True) as client:
    response = await client.get("https://api.example.com/users")

# Migration from requests → httpx is usually find-and-replace
# requests.get() → httpx.get()
# requests.Session() → httpx.Client()
```

**When I'd recommend something else:**

```python
# requests (80% confident for scripts):
# The simplest. Everyone knows it. But sync-only.
import requests
r = requests.get("https://api.example.com/data")
# Pro: 10+ years of stability, every tutorial uses it
# Con: No async, no HTTP/2, no connection pooling by default

# aiohttp (60% confident for high-throughput):
# Most battle-tested for massive concurrent connections
import aiohttp
async with aiohttp.ClientSession() as session:
    async with session.get("https://api.example.com/data") as resp:
        data = await resp.json()
# Pro: Highest throughput, handles 10K+ concurrent connections
# Con: Different API from requests, async-only, more verbose

# urllib3 (rarely used directly):
# Low-level. Only use if you're building a library on top.
# requests and httpx both use urllib3 internally.
```

**Decision tree:**

```
Need async? ─── No ──→ requests (simple) or httpx (future-proof)
    │
    Yes
    │
Need maximum throughput? ─── Yes ──→ aiohttp
    │
    No ──→ httpx (simplest async API)
```

**What would change my answer:**

```
"We're making 100K+ requests/minute"  → aiohttp (60%) or httpx (35%)
"Team has never used async"           → requests (80%)
"We need WebSocket support too"       → aiohttp (70%) has it built in
"Minimizing dependencies matters"     → urllib3 (already installed) or stdlib urllib
"We need HTTP/2 for performance"      → httpx (85%)
```

For most Python web projects in 2024+: start with httpx. It's the modern default — sync when you want simplicity, async when you need performance, and a migration path from requests that's nearly free.'''
    ),
    (
        "thinking/uncertainty-migration-timing",
        "We need to migrate from MongoDB to PostgreSQL. When should we do it? We're about to enter a busy season (3 months).",
        r'''<think>
Timing a major database migration is critically important. Let me assess the options with uncertainty.

The constraints:
1. Busy season in ~3 months (presumably important for revenue/users)
2. MongoDB → PostgreSQL is a significant migration (schema changes, query rewriting, data transfer)
3. Need to consider: how long will the migration take?

Timeline estimation:
- Small app (< 10 collections, < 1M docs): 2-4 weeks
- Medium app (10-50 collections, 1-100M docs): 1-3 months
- Large app (50+ collections, 100M+ docs): 3-6 months

The timing options:

Option A: Start now, finish before busy season
- 85% confident this is risky if the migration is medium-large
- 3 months is tight for a major DB migration
- If it goes wrong during busy season → catastrophic
- Murphy's Law: migrations always take longer than estimated

Option B: Wait until after busy season
- 70% confident this is the safer choice
- Continue on MongoDB for 3 more months (painful but known)
- Start migration after busy season with proper time buffer
- Risk: MongoDB problems during busy season (but they're known problems)

Option C: Start preparation now, migrate after busy season
- 90% confident this is the best approach
- Use the 3 months to prepare: design schemas, write migration scripts, build adapters
- Dry-run the migration in staging
- Actually cut over after busy season when there's less pressure
- This is the "sharpen the axe before cutting the tree" approach

Option D: Gradual migration using the strangler fig pattern
- 75% confident this is viable but complex
- New features write to PostgreSQL, old features still use MongoDB
- Eventually migrate old data
- Risk: maintaining two databases during busy season adds operational complexity

What would change my answer:
- If MongoDB is actively causing outages → may need to migrate sooner (urgent)
- If the migration is small (< 2 weeks) → could do it before busy season
- If they have a dedicated DBA/platform team → can handle parallel systems
- If the busy season is critical (Black Friday for e-commerce) → definitely wait

My recommendation: Option C (prepare now, migrate after).
</think>

**90% confident: prepare now, migrate after busy season.** Here's why each timing option is risky or wise.

**The options:**

| Option | Risk | Confidence |
|---|---|---|
| A: Migrate now (before busy season) | High — tight timeline, Murphy's Law | 15% good idea |
| B: Wait, migrate after | Medium — known MongoDB pain continues | 70% good idea |
| C: Prepare now, migrate after | Low — best of both worlds | 90% good idea |
| D: Gradual migration starting now | Medium-High — two DBs during busy season | 40% good idea |

**Why rushing before busy season is dangerous (85% confident):**

```
Migration timeline reality:
  Estimated: 4 weeks
  Actual (with surprises): 6-10 weeks

  Week 1-2: Schema design, migration scripts ✓
  Week 3:   Data migration, discover edge cases ⚠️
  Week 4:   Fix edge cases, re-migrate, test ⚠️
  Week 5:   "Found another edge case in production data" ⚠️
  Week 6:   Performance issues with new schema ⚠️
  Week 7:   Busy season starts tomorrow 😱

  Risk: You're debugging a new database during your highest-traffic period.
  This is how outages happen.
```

**The recommended approach (prepare now, migrate after):**

```
NOW (3 months before busy season):
┌─────────────────────────────────────────────────┐
│ Month 1: Design & Plan                          │
│  - Design PostgreSQL schema                     │
│  - Map MongoDB collections → PG tables          │
│  - Identify query translation needs             │
│  - Write migration scripts                      │
│                                                 │
│ Month 2: Build & Test                           │
│  - Create dual-write adapter (writes to both)   │
│  - Run full migration on staging with prod data │
│  - Performance test PostgreSQL with real queries │
│  - Fix all issues found                         │
│                                                 │
│ Month 3 (busy season starts): Freeze            │
│  - DO NOT migrate during busy season            │
│  - Keep running on MongoDB (known stable)       │
│  - Continue testing migration in staging         │
│  - Build confidence and fix edge cases           │
└─────────────────────────────────────────────────┘

AFTER busy season:
┌─────────────────────────────────────────────────┐
│ Week 1: Enable dual-write in production         │
│  - Both MongoDB and PostgreSQL get all writes   │
│  - Read from MongoDB (source of truth)          │
│                                                 │
│ Week 2: Migrate historical data                 │
│  - Backfill PostgreSQL with existing data       │
│  - Verify data consistency                      │
│                                                 │
│ Week 3: Switch reads to PostgreSQL              │
│  - Read from PG, write to both (safety net)     │
│  - Monitor for discrepancies                    │
│                                                 │
│ Week 4: Remove MongoDB writes                   │
│  - PostgreSQL is sole database                  │
│  - Keep MongoDB as read-only backup for 2 weeks │
│  - Decommission MongoDB after verification      │
└─────────────────────────────────────────────────┘
```

**What you can do NOW that reduces migration risk later:**

```python
# 1. Create a database abstraction layer
# Instead of MongoDB calls scattered everywhere, centralize them
class UserRepository:
    def get_user(self, user_id: str):
        # Currently uses MongoDB
        return self.mongo_db.users.find_one({"_id": user_id})

    def create_user(self, data: dict):
        return self.mongo_db.users.insert_one(data)

# When migration time comes, you only change this one class:
class UserRepository:
    def get_user(self, user_id: str):
        # Now uses PostgreSQL
        return self.pg_db.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

```python
# 2. Write migration scripts and TEST them on staging
import pymongo
import psycopg2

def migrate_users():
    mongo = pymongo.MongoClient()
    pg = psycopg2.connect(PG_URL)

    for doc in mongo.mydb.users.find():
        pg.cursor().execute("""
            INSERT INTO users (id, email, name, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (str(doc['_id']), doc['email'], doc.get('name'), doc.get('created_at')))

    pg.commit()

# Run this on staging with a copy of production data
# Find and fix all the edge cases NOW
```

**What would change my timing recommendation:**

```
"MongoDB is causing weekly outages"     → Consider emergency migration (50%)
"Migration is small (2 collections)"    → Could finish before busy season (65%)
"We have a platform team to handle it"  → Gradual migration during season (55%)
"Busy season is Black Friday (e-comm)"  → Definitely wait (95%)
"Busy season is mild (10% traffic inc)" → Could start gradual now (50%)
```

Bottom line: use the 3 months to prepare, not to rush. A well-prepared migration after busy season takes 2-3 weeks. A rushed migration during busy season can take months of firefighting.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
