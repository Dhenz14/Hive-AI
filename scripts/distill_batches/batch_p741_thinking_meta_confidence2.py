"""Phase 3D: Metacognition — Confidence Calibration Under Pressure (Part 2)

Scenarios: Performance prediction without profiling, compatibility
questions, security assessment with incomplete info.
"""

PAIRS = [
    (
        "thinking/meta-confidence-performance-prediction",
        r'''I'm building a Python API that needs to handle 10,000 requests per second. Is Flask fast enough, or should I use FastAPI?''',
        r'''<think>
I'm uncertain about the right answer here because performance predictions without profiling data are unreliable. Let me be honest about what I know and don't know.

What I'm confident about:
- Flask with gunicorn can handle ~1,000-3,000 simple requests/second per worker (varies hugely by what the request does)
- FastAPI with uvicorn can handle ~5,000-15,000 simple requests/second (async I/O helps for I/O-bound work)
- 10,000 req/s is substantial but achievable with either framework + proper infrastructure
- The framework is almost NEVER the bottleneck — database queries, network calls, and business logic dominate response time

What I'm uncertain about:
- What "handle" means — 10K req/s at what latency? p50? p99?
- What these requests DO — a JSON echo is different from a DB query + computation
- Whether this is sustained or burst traffic
- How many server instances they're planning to run

What I definitely don't know:
- The request complexity (simple GET vs complex computation)
- Database query patterns (the real bottleneck)
- Infrastructure budget
- Current performance baseline

I should give conditional answers rather than a definitive "use X."
</think>

**I can't give a definitive answer without knowing what the requests do.** The framework choice matters far less than what happens inside each request.

**What I'm confident about:**

The framework overhead is typically <5% of total request time:
```
Framework processing:  0.1-1ms
Database query:        5-50ms
Business logic:        1-20ms
Network calls:         10-100ms
```

Switching from Flask to FastAPI saves ~0.5ms per request. If your requests take 30ms, that's a 1.7% improvement.

**Rough benchmarks** (simple JSON responses, I/O-bound):

| Setup | Requests/sec (per instance) |
|-------|---------------------------|
| Flask + gunicorn (4 workers) | 2,000-4,000 |
| FastAPI + uvicorn (4 workers) | 5,000-15,000 |
| Flask + gunicorn (4 instances) | 8,000-16,000 |

**What I'm uncertain about:**
- Your actual request complexity (benchmarks above are for trivial responses)
- Whether async I/O (FastAPI's advantage) matters for your workload
- Whether 10K req/s is sustained or peak

**Conditional recommendations:**

| If your requests are... | Recommendation |
|------------------------|----------------|
| I/O-bound (DB, API calls) | FastAPI's async helps significantly |
| CPU-bound (computation) | Neither — use workers + scaling |
| Simple (cache hit, static response) | Either works, add instances |
| Complex (multiple DB queries + logic) | Framework doesn't matter — optimize the queries |

**What actually gets you to 10K req/s:**
1. **Optimize database queries** (this matters 10x more than framework choice)
2. **Add caching** (Redis for hot data)
3. **Horizontal scaling** (3-5 instances behind a load balancer)
4. **Connection pooling** (pgbouncer, Redis pool)
5. **Then** consider async framework if I/O-bound

**My honest advice:** Start with Flask if your team knows it. Profile under load. If the framework is actually the bottleneck (unlikely), migrate to FastAPI. The migration is straightforward.'''
    ),
    (
        "thinking/meta-confidence-compatibility-versions",
        r'''Will SQLAlchemy 2.0 work with my existing Flask-SQLAlchemy 2.5 code? I want to upgrade.''',
        r'''<think>
I'm not fully certain about the specific compatibility details. Let me assess what I know.

What I'm confident about:
- SQLAlchemy 2.0 introduced significant API changes from 1.4 (new query syntax, removal of deprecated patterns)
- Flask-SQLAlchemy versions have specific SQLAlchemy version requirements
- SQLAlchemy 2.0 deprecated the "legacy" query style (session.query(Model)) in favor of select() statements
- This means existing code using Model.query or session.query() might need changes

What I'm uncertain about:
- The EXACT version of Flask-SQLAlchemy that supports SQLAlchemy 2.0 (I believe it's Flask-SQLAlchemy 3.0+, but I should verify)
- Whether Model.query (Flask-SQLAlchemy's convenience) still works with SQLAlchemy 2.0
- Whether all Flask-SQLAlchemy extensions (Flask-Migrate, etc.) are compatible with the new versions
- The full list of breaking changes that would affect typical Flask-SQLAlchemy usage

What I definitely don't know:
- Which specific SQLAlchemy patterns your code uses
- Whether you use legacy-style queries, the new style, or a mix
- Which other extensions depend on SQLAlchemy in your project
- Your Python version (SQLAlchemy 2.0 requires Python 3.7+)

I should tell the user to verify specific compatibility rather than guessing.
</think>

**I'm not certain about the exact compatibility matrix.** Here's what I know and what you should verify:

**What I'm fairly confident about:**
- Flask-SQLAlchemy 2.5 was designed for SQLAlchemy 1.x
- Flask-SQLAlchemy 3.0+ is needed for SQLAlchemy 2.0 support
- SQLAlchemy 2.0 deprecated `session.query(Model)` style queries
- Flask-SQLAlchemy's `Model.query` convenience is affected

**What I'm uncertain about:**
- Whether Flask-SQLAlchemy 3.x maintains full backwards compatibility with your code patterns
- The exact interaction between Flask-Migrate and SQLAlchemy 2.0
- Whether all your query patterns need updating

**Before upgrading, verify these yourself:**

```bash
# 1. Check current versions
pip show flask-sqlalchemy sqlalchemy flask-migrate alembic

# 2. Check compatibility requirements
pip index versions flask-sqlalchemy  # See available versions

# 3. Read the actual migration guides:
# - SQLAlchemy 1.4 → 2.0: https://docs.sqlalchemy.org/en/20/changelog/migration_20.html
# - Flask-SQLAlchemy 3.0: https://flask-sqlalchemy.palletsprojects.com/en/3.1.x/changes/
```

**Common changes you'll likely need (but verify):**
```python
# Old style (may need updating):
users = User.query.filter_by(active=True).all()

# New SQLAlchemy 2.0 style:
from sqlalchemy import select
users = db.session.execute(select(User).filter_by(active=True)).scalars().all()

# Flask-SQLAlchemy 3.x may still support Model.query — check the docs
```

**My recommended upgrade path:**
1. Read both migration guides (linked above)
2. Upgrade in a branch, run your test suite
3. Fix deprecation warnings first (SQLAlchemy 1.4 shows them)
4. Then upgrade to 2.0

**I'd rather you check the docs than trust my potentially outdated version knowledge.** Dependency compatibility is one of those things where being 90% right is the same as being wrong.'''
    ),
    (
        "thinking/meta-confidence-security-incomplete",
        r'''I'm storing user passwords with MD5 hashing. Is this secure enough for an internal company tool?''',
        r'''<think>
I am very confident about this one — this is a clear security issue with no ambiguity.

What I'm confident about:
- MD5 is NOT secure for password hashing. This is not debatable.
- MD5 can be cracked at billions of hashes per second on modern GPUs
- "Internal company tool" doesn't change the security requirements for passwords
- bcrypt, scrypt, or argon2 are the correct choices for password hashing
- This has been well-established security knowledge for 15+ years

What I'm less certain about:
- The specific threat model for this internal tool (who has access to the database?)
- Whether they're using salted MD5 (still bad, but marginally better than unsalted)
- Whether the tool handles any sensitive data beyond passwords

What I don't need to know to answer:
- This is one of the rare cases where I can be nearly 100% confident in my recommendation. MD5 for passwords is unambiguously wrong regardless of context.

I should be direct and not hedge excessively. Confidence calibration means being confident when you SHOULD be confident, not just being uncertain about everything.
</think>

**No. MD5 is not secure for passwords. This is not a close call — there's no scenario where MD5 is acceptable.**

I'm highly confident about this:

**Why MD5 fails for passwords:**
```
# MD5 cracking speed on a modern GPU:
# ~40 BILLION hashes per second (RTX 4090)
# A typical 8-character password: cracked in seconds
# The entire English dictionary: cracked in milliseconds
```

**"Internal tool" doesn't change this:**
- Internal employees reuse passwords across systems
- Database backups get stolen, drives get recycled
- Employees leave the company (and might take data)
- Internal tools become external tools (happens constantly)
- Compliance audits flag this regardless

**Fix (takes 10 minutes):**
```python
# Replace MD5:
import hashlib
password_hash = hashlib.md5(password.encode()).hexdigest()  # WRONG

# With bcrypt:
from bcrypt import hashpw, gensalt, checkpw

# Hashing
password_hash = hashpw(password.encode(), gensalt())

# Verification
is_valid = checkpw(password.encode(), stored_hash)
```

**Migration for existing users:**
```python
# On next login, re-hash with bcrypt:
def login(username, password):
    user = get_user(username)

    if user.hash_type == 'md5':
        # Verify old MD5 hash
        if hashlib.md5(password.encode()).hexdigest() == user.password_hash:
            # Re-hash with bcrypt
            user.password_hash = hashpw(password.encode(), gensalt())
            user.hash_type = 'bcrypt'
            save_user(user)
            return True
    else:
        return checkpw(password.encode(), user.password_hash)
```

**Password hashing hierarchy:**
1. **argon2** (best, winner of Password Hashing Competition)
2. **bcrypt** (excellent, widely supported)
3. **scrypt** (good, memory-hard)
4. **PBKDF2** (acceptable, used by Django)
5. ~~MD5, SHA1, SHA256~~ — **never for passwords** (too fast to compute)'''
    ),
    (
        "thinking/meta-confidence-scale-without-numbers",
        r'''Will my Django app scale to handle our growth? We're growing fast.''',
        r'''<think>
I'm very uncertain here. "Growing fast" and "scale" are too vague to give a meaningful answer.

What I'm confident about:
- Django itself can scale — Instagram runs on Django and serves billions of requests
- Scaling is almost never about the framework — it's about database queries, caching, and infrastructure
- Without specific numbers, any scaling advice is speculation

What I'm uncertain about:
- What "growing fast" means (10 → 100 users? 10K → 100K? 1M → 10M?)
- What the current traffic is
- What the bottleneck would be
- Their infrastructure setup (single server? cloud? managed DB?)

What I definitely don't know:
- Current request rate
- Database query patterns
- Response times
- Infrastructure budget
- When they expect to hit "not scaling"

I need to ask for specifics rather than give vague reassurance or unfounded warnings.
</think>

**I can't answer this without numbers.** "Growing fast" could mean anything from 100 to 10 million users. Here's what I need to give useful advice:

**Questions I need answered:**

1. **Current scale:**
   - How many daily active users?
   - How many requests per second at peak?
   - Current average response time?

2. **Growth rate:**
   - What's "fast"? 10% month-over-month? 10x in 6 months?
   - What's the target in 6 months? 1 year?

3. **Infrastructure:**
   - Single server or cloud?
   - Managed database (RDS) or self-hosted?
   - Using any caching?

**What I CAN tell you — conditional answers:**

| Your current scale | When to worry | What to do |
|-------------------|---------------|------------|
| < 1,000 users | Not yet | Focus on product, not scaling |
| 1,000-10,000 | Monitor response times | Add caching, optimize queries |
| 10,000-100,000 | Soon | Read replicas, CDN, horizontal scaling |
| 100,000-1,000,000 | Now | Caching layer, async tasks, possibly microservices |
| > 1,000,000 | Yesterday | Dedicated scaling team |

**Universal Django scaling steps (order matters):**
1. Add `django-debug-toolbar` → find slow queries (free, immediate)
2. Add database indexes for slow queries (free, minutes)
3. Add Redis caching for hot data ($0-10/mo)
4. Add a CDN for static assets ($0-10/mo)
5. Upgrade database instance ($$)
6. Add read replicas ($$$)
7. Horizontal app scaling behind load balancer ($$$)

**The honest truth:** Django scales to millions of users. The question isn't whether Django can handle it — it's whether your queries, infrastructure, and architecture are designed for your specific load. That requires actual numbers, not "growing fast."'''
    ),
    (
        "thinking/meta-confidence-debugging-no-repro",
        r'''One of our users reported that they can't log in. They say it just shows a blank white page. No other users have reported this issue. What's wrong?''',
        r'''<think>
I'm very uncertain here. A single user report with "blank white page" has dozens of possible causes.

What I'm confident about:
- "Blank white page" usually means a JavaScript error crashed the frontend before rendering
- OR the server returned an empty response
- OR the user has a browser extension blocking content
- A single user report (no other complaints) suggests it's user-specific, not a system-wide issue

What I'm uncertain about:
- Whether "blank white page" means truly blank, or a loading spinner, or an error message
- Whether it's a frontend or backend issue
- Whether the user's browser/device/network is the factor
- Whether it happens on every login attempt or was a one-time occurrence

What I definitely don't know:
- The user's browser and version
- Whether the user has ad blockers or privacy extensions
- The user's network conditions
- Server-side logs for this user's login attempts
- Whether the user's account has any special state (locked, unverified email, etc.)

With this little information, I should present multiple hypotheses ranked by likelihood rather than diagnosing a single cause.
</think>

**Too little information to diagnose.** A single "blank white page" report from one user has many possible causes. Here are hypotheses ranked by likelihood:

**Most likely — user-specific issues:**

| Hypothesis | Likelihood | How to verify |
|------------|-----------|---------------|
| Browser extension blocking JS | High | Ask user to try incognito mode |
| Outdated browser | High | Ask user for browser + version |
| JavaScript error in their browser | High | Ask for browser console screenshot |
| Cached stale frontend assets | Medium | Ask user to hard refresh (Ctrl+Shift+R) |
| Corporate firewall/proxy blocking | Medium | Ask if on office network |
| Account-specific issue | Medium | Check user's account state in DB |

**Less likely — system issues:**

| Hypothesis | Likelihood | How to verify |
|------------|-----------|---------------|
| Frontend deployment served partial assets | Low | Check CDN/static files |
| CSP header blocking inline scripts | Low | Check Content-Security-Policy |
| API returning empty response for this user | Low | Check server logs for their user ID |

**My recommended diagnostic steps:**

```
1. Check server logs for this user's IP/user_id (1 min)
   → Did the login endpoint return 200? 500? Anything?

2. Ask the user to try in incognito/private mode (1 min)
   → If it works in incognito: browser extension issue

3. Ask for browser console output (Ctrl+F12 → Console tab)
   → JavaScript errors will appear here

4. Check user's account state
   → Is the account locked? Email unverified? Unusual data?

5. Try logging in AS the user (in a test environment)
   → Can you reproduce it?
```

**What to tell the user right now:**
"Can you try logging in using an incognito/private browser window? If that works, a browser extension is likely interfering. If not, can you share your browser name and version, and a screenshot of any error messages?"

**I can't diagnose this further without more information.**'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
