"""Phase 2F: Advanced Reasoning — Uncertainty & Confidence Calibration (Part 1/3)
Teach the model to express calibrated uncertainty: what it knows, what depends on context,
what it genuinely doesn't know. 'It depends on...' with specific conditions."""

PAIRS = [
    (
        "thinking/uncertainty-bug-or-feature",
        "This Python function returns None when the input list is empty instead of raising an error. Is this a bug or intentional behavior?\n```python\ndef find_median(values):\n    if not values:\n        return None\n    sorted_vals = sorted(values)\n    mid = len(sorted_vals) // 2\n    if len(sorted_vals) % 2 == 0:\n        return (sorted_vals[mid-1] + sorted_vals[mid]) / 2\n    return sorted_vals[mid]\n```",
        r'''<think>
Let me analyze whether returning None for empty input is a bug or a design choice. I need to be honest about my uncertainty here.

Arguments for "it's a bug":
- The median of an empty set is mathematically undefined
- Returning None silently propagates — the caller might do `result + 5` and get TypeError
- Python convention for "this shouldn't happen" is to raise ValueError
- Statistics libraries (numpy, statistics) raise errors on empty input
- The caller has no way to distinguish "no data" from "there was an error"

Arguments for "it's intentional":
- Maybe the caller checks for None: `result = find_median(data) or default`
- In data pipelines, None signals "no value" and is handled downstream
- Some coding styles prefer returning sentinel values over raising exceptions
- If this is in a loop processing many datasets, raising an exception requires try/except overhead

I genuinely don't know which was intended here because it depends on:
1. The codebase conventions — does this project use None-as-signal or exceptions?
2. The callers — do they check for None or assume a number?
3. The domain — is "no data" a normal case or an error condition?

I'm fairly confident that returning None is a SMELL (potential bug) but I can't be certain it's wrong without context. I'd estimate:
- 70% chance it's unintentional (developer didn't think about empty input)
- 30% chance it's deliberate (project convention to return None for "no result")

The right answer is: I need to check the callers and the project conventions before changing it.
</think>

**Honest answer: I can't tell without more context.** Here's my analysis with calibrated confidence:

**70% likely: it's unintentional** (a bug)
- Returning `None` where a number is expected causes silent propagation failures
- `median_value + 5` → `TypeError` far from the actual problem
- Python's `statistics.median([])` raises `StatisticsError` — this is the community convention
- Most developers don't explicitly handle the empty case; they just forget it

**30% likely: it's intentional** (a design choice)
- Some codebases use `None` as "no value available" consistently
- Data pipeline code often prefers `None` over exceptions for missing data
- If callers already do `if result is not None:`, it's working as designed

**What I'd need to know to be sure**:
```python
# Check 1: How do callers use the result?
# If they do this → it's a bug (they expect a number):
avg = find_median(data) + find_mean(data)  # TypeError on None!

# If they do this → it's intentional (they handle None):
median = find_median(data)
if median is not None:
    report["median"] = median

# Check 2: What do other similar functions in this codebase do?
# find_mean([]) → None?  Then this is a project convention.
# find_mean([]) → ValueError?  Then find_median should too.

# Check 3: Is empty input a normal case or an error?
# Filtering data → might legitimately be empty → None makes sense
# User-provided input → should always have data → ValueError makes sense
```

**My recommendation** (regardless of intent):
```python
def find_median(values: list[float]) -> float:
    """Return the median. Raises ValueError if values is empty."""
    if not values:
        raise ValueError("Cannot compute median of empty list")
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return sorted_vals[mid]
```

If the callers need the `None` behavior, wrap it:
```python
def find_median_or_none(values: list[float]) -> float | None:
    try:
        return find_median(values)
    except ValueError:
        return None
```

This makes the intent explicit — the function that raises is the "correct" one, and the None-returning wrapper is an explicit choice, not an accidental omission.'''
    ),
    (
        "thinking/uncertainty-database-choice",
        "We're building a social media platform for a startup. Expected users: 10K in year 1, hopefully 1M by year 3. Should we use PostgreSQL or MongoDB?",
        r'''<think>
I need to be genuinely honest about uncertainty here instead of just defaulting to "PostgreSQL is better."

What I'm fairly confident about (>90%):
- At 10K users, EITHER database will work fine. The choice barely matters at this scale.
- PostgreSQL has stronger data consistency guarantees
- MongoDB is easier to start with if the schema is truly undefined
- Both scale to 1M users with proper architecture

What I'm moderately confident about (60-80%):
- Social media has a mix of relational and document-like data
- User profiles: slightly better as documents (flexible schema)
- Social graph (followers, likes): much better as relational
- Feed generation: complex queries favor relational
- For a startup, developer velocity matters more than database choice

What I'm uncertain about (<50%):
- Whether this team has more SQL or MongoDB experience (critical factor!)
- Whether the data model will change radically as the product pivots
- Whether they'll need complex aggregations or simple CRUD
- Whether they'll need real-time features that favor one over the other
- Whether they'll actually reach 1M users (most startups don't)

My genuine assessment:
- PostgreSQL is the safer default for social media (70% confident)
- But MongoDB is not WRONG, and if the team knows MongoDB better, that might matter more
- The most dangerous thing is spending 2 weeks debating databases instead of building features

I should express this honestly rather than pretending I know the definitive answer.
</think>

**My honest assessment with calibrated confidence:**

**I'd lean PostgreSQL (70% confident), but it genuinely depends on factors I don't know.**

**What I'm confident about (>90%)**:
- At 10K users, this choice **doesn't matter**. Both handle it trivially.
- At 1M users, both CAN handle it with proper architecture.
- The biggest risk isn't the database — it's spending 2 weeks debating instead of building.

**Why PostgreSQL has the edge for social media (70%)**:
```
Social media feature    | PostgreSQL advantage          | MongoDB advantage
------------------------|------------------------------|--------------------
Social graph            | JOINs, recursive CTEs        | Need $lookup (slower)
(friends, followers)    | Natural fit                   | Awkward in documents
News feed generation    | Complex queries, window funcs | Aggregation pipeline works
Content + metadata      | JSONB for flexible parts      | Natural document fit
Search                  | Full-text search built in     | Need Atlas Search
Transactions            | ACID built in                 | Multi-doc transactions (newer)
Analytics               | Rich SQL aggregations         | Aggregation pipeline
```

**But MongoDB wins IF (30%)**:
```
- Your team has deep MongoDB experience and minimal SQL
- Your data model is truly schema-less (user-generated content with wildly varying structure)
- You need horizontal sharding at scale (MongoDB does this more naturally)
- You're building a content platform more than a social network
```

**What I'd genuinely need to know to give a better answer**:
1. **Team experience** — if everyone knows MongoDB and nobody knows SQL, use MongoDB. Developer velocity beats theoretical database advantages.
2. **Core features** — is it more Instagram (content-heavy, document-like) or more LinkedIn (relationship-heavy, relational)?
3. **Read/write patterns** — 90% reads? PostgreSQL with read replicas. 50/50? Either works.
4. **Will you pivot?** — If the product might become something completely different, MongoDB's schema flexibility helps.

**My actual recommendation**:
```
For most social media startups: PostgreSQL + JSONB
- Relational for core data (users, relationships, posts)
- JSONB columns for flexible parts (user preferences, post metadata)
- You get 90% of MongoDB's flexibility + full SQL power

-- Example: best of both worlds
CREATE TABLE posts (
    id BIGSERIAL PRIMARY KEY,
    author_id BIGINT REFERENCES users(id),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',  -- flexible: tags, location, poll data, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Query the flexible parts naturally
SELECT * FROM posts
WHERE metadata->>'location' = 'New York'
  AND metadata->'tags' ? 'tech';
```

**Bottom line**: If you don't have a strong reason to pick MongoDB, default to PostgreSQL. If you have a strong reason (team expertise, truly schema-less data), MongoDB is fine. Either way, ship features — the database isn't your bottleneck at 10K users.'''
    ),
    (
        "thinking/uncertainty-optimization-help",
        "Our batch processing job takes 45 minutes. Adding an index on the main query column should speed it up, right?",
        r'''<think>
Should I just say "yes, add the index"? No — I genuinely don't know if it will help. Let me think about when indexes DON'T help.

What I'm confident about:
- Indexes speed up lookups (WHERE, JOIN conditions) — this is generally true
- Indexes slow down writes (INSERT, UPDATE) — always true
- If the batch job is read-heavy, an index on the filter column usually helps

What I'm uncertain about:
- Is the batch job actually SLOW because of the query, or because of something else?
  - Maybe it's slow because of network I/O (downloading files)
  - Maybe it's slow because of CPU-bound processing
  - Maybe it's slow because of write throughput (inserting results)
  - An index doesn't help any of these

- Even if the query is the bottleneck, indexes don't always help:
  - If the query reads >20% of the table, the optimizer may choose a full table scan anyway (sequential reads are faster than random index lookups for large result sets)
  - If the batch job does UPDATE or INSERT on the indexed table, the index slows down writes
  - If the column has low cardinality (e.g., boolean), the index is nearly useless

- I don't know the actual query, table size, or current execution plan

I need to express this uncertainty honestly. The answer is "maybe, but we need to check first."
</think>

**Honest answer: maybe, but I'd need to see the query plan before being confident.**

**An index will likely help IF (70% of batch jobs)**:
- The bottleneck is a `SELECT` with a `WHERE` clause on that column
- The query filters to a small percentage of the table (<20%)
- The column has high cardinality (many distinct values)

**An index will NOT help IF**:
```
Scenario                              Why index doesn't help
────────────────────────────          ──────────────────────
The query reads most of the table    Full scan is faster than random index lookups
The bottleneck is INSERT/UPDATE      Index SLOWS writes (must update index on each row)
The column has low cardinality       INDEX ON status ('active'/'inactive') is useless
                                     if 95% of rows are 'active'
The bottleneck isn't the DB query    Network I/O, CPU processing, or memory are the
                                     real bottleneck — index doesn't help
You already HAVE an index            Adding a duplicate doesn't help
The query is already optimized       But the batch loop processes rows one-by-one
                                     instead of in bulk
```

**What to do before adding the index**:
```sql
-- Step 1: Find out WHERE the 45 minutes is spent
-- Is it the query, processing, or writing?

-- Step 2: If it IS the query, look at the execution plan
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM your_table WHERE your_column = 'value';

-- If you see "Seq Scan" → an index MIGHT help
-- If you see "Index Scan" → you already have one
-- If you see "Seq Scan" but rows filtered is >50% → index won't help (full scan is better)

-- Step 3: Check query selectivity
SELECT
    COUNT(*) FILTER (WHERE your_column = 'value') AS matching,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE your_column = 'value') * 100.0 / COUNT(*) AS pct
FROM your_table;
-- If pct > 20% → index may not help. Optimizer prefers full scan for large fractions.
```

**What actually speeds up batch jobs (in order of likelihood)**:
```
Fix                           | Typical speedup | Confidence
------------------------------|-----------------|------------
Process in batches, not rows  | 10-50x          | 95% — almost always helps
Add missing index             | 2-100x          | 70% — if query is the bottleneck
Use COPY instead of INSERT    | 5-20x           | 90% — for bulk writes
Remove unnecessary ORDER BY   | 2-5x            | 80% — sorting is expensive
Parallelize independent work  | 2-8x            | 70% — if CPU is the bottleneck
Increase work_mem             | 2-10x           | 60% — if sorts/hashes spill to disk
```

I'd need to see the actual query and `EXPLAIN ANALYZE` output before recommending the index. The index might help, but it's just as likely that the batch job processes rows one-by-one instead of in bulk — and that's a 10-50x improvement that no index can match.'''
    ),
    (
        "thinking/uncertainty-rewrite-vs-refactor",
        "Our 5-year-old Django monolith has grown to 200K LOC. It works but has lots of technical debt. The CTO wants to know: should we rewrite in a modern framework (FastAPI) or refactor the existing codebase?",
        r'''<think>
This is one of the most consequential technical decisions a team can make, and I should be honest that there's no clear right answer — it genuinely depends on many factors I don't know.

What I'm fairly confident about:
- Full rewrites of 200K LOC systems have a very high failure rate
- "Working code" has enormous embedded business knowledge (edge cases, bug fixes, workarounds)
- Django is not "legacy" — it's actively maintained and used by large companies
- Refactoring preserves working business logic while improving quality
- The "modern framework" appeal often overestimates gains and underestimates migration cost

What I'm less sure about:
- How bad is the technical debt really? "Lots of tech debt" is vague.
  - Slow deploys? Bad test coverage? Spaghetti code? Each has different solutions.
- Is the team frustrated with Django specifically, or with their codebase quality?
- Are there architectural limitations that can't be fixed by refactoring?
- Is the team capable of maintaining discipline during a multi-year refactor?

What I genuinely don't know:
- The team size and skill level
- Whether they're hitting Django's actual limitations or just blaming the framework
- The business timeline — can they afford 12-18 months of reduced velocity?
- Whether the CTO is asking because of real technical problems or because "shiny new thing"

My honest probability assessment:
- 75% chance: refactoring is the right choice
- 15% chance: partial rewrite (strangle fig) is the right choice
- 10% chance: full rewrite is the right choice (only if Django itself is the problem, not the codebase)
</think>

**I'm 75% confident you should refactor, not rewrite.** But let me be transparent about what I'd need to know to be more certain.

**The rewrite temptation vs reality**:
```
What teams imagine:            What actually happens:
─────────────────              ──────────────────────
Clean new codebase             6 months in, same complexity, different framework
Modern tech stack              The mess was in business logic, not the framework
Ship in 6 months               Takes 18-24 months (or never ships)
No tech debt                   New tech debt from time pressure
Team is excited                Team is exhausted after month 12
```

**My uncertainty — the answer genuinely depends on these questions**:

| Question | If YES → Rewrite | If NO → Refactor |
|----------|-----------------|-------------------|
| Is Django itself the bottleneck? (Not the codebase quality) | ✅ Maybe rewrite | ❌ Framework isn't the problem |
| Are you hitting Django's actual scaling limits? | ✅ Consider FastAPI | ❌ Django scales to millions of users |
| Is the codebase completely untested? | ✅ Refactoring is risky without tests | ❌ Add tests first, then refactor |
| Has the data model changed fundamentally? | ✅ May need fresh start | ❌ Evolve the existing schema |
| Is the team < 3 people? | ❌ Too small for parallel rewrite | ✅ Focused refactoring |
| Is the team > 20 people? | ✅ Can afford parallel track | ❌ Coordinate refactoring |
| Can business tolerate 12+ months reduced velocity? | ✅ Rewrite is possible | ❌ Must keep shipping features |

**What I'd recommend in most cases (75%)**:
```python
# Phase 1: Stop the bleeding (1-2 months)
# - Add tests to critical paths (don't rewrite, just add tests)
# - Set up CI/CD if not already there
# - Identify the top 5 pain points (what slows the team down most?)

# Phase 2: Incremental modernization (ongoing)
# - Extract the worst modules into clean internal APIs
# - Introduce Django REST Framework if not using it
# - Add type hints to new code (gradual, don't rewrite existing)
# - Replace jQuery with htmx or a modern frontend (if applicable)

# Phase 3: Selective extraction (if needed)
# - If ONE service is the bottleneck (e.g., real-time notifications),
#   extract it as a separate FastAPI service
# - Keep the monolith for everything else
# - This gives you 80% of the benefit at 20% of the cost

# Django + good code > FastAPI + rushed rewrite
```

**When I'd agree with a rewrite (25%)**:
```
- Django 1.x and upgrading to 4.x is impractical (skipped too many versions)
- The data model is fundamentally wrong (not just messy — wrong)
- The entire team is new (nobody wrote the original code or understands it)
- Regulatory requirements mandate a new architecture (rare but real)
- The business is pivoting to something Django genuinely can't do (real-time game, IoT)
```

**The honest truth**: Most rewrites fail because the complexity was never in the framework — it was in the business logic. Rewriting in FastAPI just relocates the complexity to a new codebase where you'll recreate the same problems in 3 years. The unglamorous truth is: add tests, refactor incrementally, ship features. It's not exciting, but it works.'''
    ),
    (
        "thinking/uncertainty-security-exploitable",
        "We found a reflected XSS vulnerability in our admin panel. The panel is only accessible behind VPN and requires admin credentials. Our security team says it's critical, but the product team says it's low priority because of the access restrictions. Who's right?",
        r'''<think>
This is a genuine tension where both sides have valid points. Let me analyze honestly.

Security team's argument (it's critical):
- XSS can steal admin session cookies
- Admin accounts have the most permissions → highest impact
- VPN access can be compromised (credential stuffing, stolen VPN creds, insider threat)
- Reflected XSS can be delivered via a link in Slack/email to an admin
- "Defense in depth" — VPN is ONE layer, not a guarantee
- If the attacker is inside the VPN (insider, compromised machine), XSS works

Product team's argument (it's low priority):
- Only admins can reach it
- They'd need to be on VPN first
- We have more urgent user-facing bugs
- The attack requires social engineering an admin into clicking a link
- We're a 20-person startup, not a bank

My honest assessment:
- Severity: HIGH (admin compromise = full system compromise)
- Exploitability: MODERATE (requires VPN access + social engineering)
- Combined risk: MEDIUM-HIGH
- Fix effort: Usually LOW for reflected XSS (escape output, CSP header)

The key question: how hard is it to fix? If it's a 2-hour fix, just do it. If it's a 2-week refactor, maybe deprioritize.

I should also consider: regulatory and compliance implications, bug bounty implications, and the psychological effect of leaving known vulnerabilities unpatched.

My honest confidence: 80% it should be fixed soon (within a sprint), but I understand the product team's point about sequencing. It shouldn't block a launch, but it shouldn't sit in the backlog for 6 months either.
</think>

**Both sides have valid points. Here's my calibrated assessment:**

**Severity × Exploitability matrix**:
```
                         Easy to exploit    Hard to exploit
                        ─────────────────  ─────────────────
High impact (admin)    │   CRITICAL       │   HIGH ← YOU ARE HERE
                       │                  │
Low impact (readonly)  │   MEDIUM         │   LOW
                        ─────────────────  ─────────────────

Exploitability: MODERATE (not easy, not hard)
- Requires VPN access (reduces attack surface)
- But VPN credentials can be phished, leaked, or stolen
- Reflected XSS only needs admin to click a crafted link
- Social engineering admins is a well-known attack pattern
- Insider threats already have VPN access

Impact: HIGH
- Admin accounts can read/modify all data
- Session cookie theft → full admin access
- If admin can deploy code → complete system compromise
```

**My honest recommendation (80% confident)**:
```
Priority: FIX WITHIN THE CURRENT SPRINT (not "drop everything," but don't backlog it)

Why not "drop everything": VPN + admin auth = two layers of protection. The
exploitability is real but not trivial. A 1-day delay to finish the current
feature won't matter.

Why not "backlog it": Known vulnerabilities accumulate. If you're aware of an
XSS and ignore it, you're accepting the risk. If there's a breach, "we knew
about it and deprioritized" is a terrible incident report. The fix is usually
small.
```

**The fix is probably trivial** (most reflected XSS):
```python
# Typical fix: 1-2 hours of work

# 1. Escape output (the direct fix)
# BEFORE:
return f"<div>Search results for: {request.args['q']}</div>"
# AFTER:
from markupsafe import escape
return f"<div>Search results for: {escape(request.args['q'])}</div>"

# 2. Add Content-Security-Policy header (defense in depth)
@app.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = "script-src 'self'"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

# 3. Set HttpOnly on session cookies (limits XSS impact)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
```

**What I'm uncertain about**:
- If this is a 2-hour fix → just do it now, debate is more expensive than the fix
- If this requires refactoring the entire template system → phased approach, add CSP headers immediately as mitigation
- Whether your industry has compliance requirements (healthcare, finance) → then it's mandatory regardless of access restrictions

**The resolution**: Fix it this sprint. It's likely a small fix. The debate about priority has probably already taken longer than the fix itself.'''
    ),
    (
        "thinking/uncertainty-scale-prediction",
        "We currently have 1,000 users and our PostgreSQL database handles everything fine. We're projecting 100K users by end of year. Will our current setup handle it, or do we need to re-architect now?",
        r'''<think>
This is a question where I genuinely don't know, and I should be honest about what factors determine the answer.

What I'm fairly confident about:
- PostgreSQL can handle 100K users — it runs Wikipedia, Instagram (early days), many large-scale apps
- 100x user growth doesn't mean 100x database load (depends on how active users are)
- Premature optimization is a real risk at this stage
- Some specific patterns WILL become problems at 100x

What I'd need to know:
- What queries are heavy? Analytics across all users? Feed generation? Search?
- How active are users? 100K users × 1 request/day = trivial. 100K × 100 requests/hour = serious.
- Current table sizes and growth rates
- Whether they're running analytics on the production database
- Connection pooling setup
- Current query performance (any slow queries already?)

What I'm uncertain about:
- Whether their specific data model has scaling issues (denormalization needed?)
- Whether they'll need read replicas at 100K (probably yes) or not
- Whether the app layer will be the bottleneck before the DB
- Whether they'll actually reach 100K (startup projections are often optimistic)

My honest assessment:
- 60% chance: current setup will handle 100K with minor tuning (indexes, connection pooling, caching)
- 30% chance: need read replicas and query optimization, but not a re-architecture
- 10% chance: fundamental data model issue that needs re-architecture now

I should NOT recommend a big re-architecture based on projected growth. But I should recommend PREPARING to scale with low-cost changes now.
</think>

**Honest answer: PostgreSQL almost certainly handles 100K users. But I can't be fully confident without knowing your access patterns.**

**What I'm confident about (90%+)**:
```
PostgreSQL can handle 100K users. It powers:
- Instagram's early growth (millions of users on PostgreSQL)
- GitLab, Reddit (early), Stripe, countless others

100x users ≠ 100x load. Growth is rarely linear:
- 1K users with 100K posts → 100K users might have 500K posts (5x, not 100x)
- Many users are inactive (80/20 rule: 20% generate 80% of traffic)
- Read-heavy apps scale differently from write-heavy apps
```

**Where I need more information**:
```
Question                        | If answer is YES → concern
--------------------------------|-----------------------------
Do you run analytics (GROUP BY, | 90% confident: need read replica or
COUNT, JOIN across full tables)  | separate analytics DB by 50K users
on production DB?               |

Do you have queries that scan   | 80% confident: need indexes or
full tables (no WHERE clause)?  | query redesign before 50K users

Do you use connection pooling   | 95% confident: MUST add PgBouncer
(PgBouncer/pgpool)?             | before 100K (PostgreSQL can't handle
                                | 100K direct connections)

Is your data write-heavy        | 70% confident: may need partitioning
(IoT, logging, events)?        | or TimescaleDB extension

Do you have N+1 query problems  | 85% confident: will be your first
in your ORM?                    | bottleneck, fix before anything else
```

**What to do NOW (low cost, high value)**:
```sql
-- 1. Check for missing indexes (5 minutes)
SELECT schemaname, tablename, indexrelname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
WHERE idx_scan = 0;  -- Unused indexes (remove for write performance)

-- Check for slow queries
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- 2. Add connection pooling if missing (1 hour)
-- PgBouncer in front of PostgreSQL, max_connections per app = 20-50

-- 3. Check table sizes and growth rate
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

**My phased recommendation**:
```
Phase 1 (NOW, regardless of growth):
  ✅ Add connection pooling (PgBouncer)
  ✅ Fix N+1 queries (use Django select_related/prefetch_related)
  ✅ Add missing indexes on frequently filtered columns
  ✅ Monitor slow queries (pg_stat_statements)

Phase 2 (at ~10K users):
  ✅ Add caching for read-heavy endpoints (Redis)
  ✅ Move analytics queries off production DB (read replica)
  ✅ Review query plans for most-used endpoints

Phase 3 (at ~50K users, IF needed):
  ⚠️ Read replicas for horizontal read scaling
  ⚠️ Partition large tables (if any are > 50M rows)
  ⚠️ Consider materialized views for dashboard queries

Phase 4 (at ~500K users, IF you get there):
  🔮 Maybe: connection pooling per service, dedicated analytics DB
  🔮 Maybe: application-level sharding (but probably not — most apps never need this)
```

**What I'd bet money on**: Your first bottleneck will be N+1 queries in the ORM, not PostgreSQL itself. Fix those and you'll easily reach 100K users. Don't re-architect based on projected growth — prepare to scale, but build features.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
