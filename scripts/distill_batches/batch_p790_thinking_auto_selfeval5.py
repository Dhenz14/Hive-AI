"""Phase 4B: Self-Improvement — Self-Evaluation (Part 5)

Additional self-evaluation pairs for calibrating output quality.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-verify-performance-claims",
        r'''I'm about to claim "Redis is 100x faster than PostgreSQL for reads." Let me verify this claim before presenting it.''',
        r'''<think>
Let me fact-check my own performance claim:

**The claim:** Redis is 100x faster than PostgreSQL for reads.

**What I know about Redis performance:**
- Redis is in-memory, single-threaded, key-value store
- Typical GET latency: ~0.1ms (100 microseconds)
- Can handle ~100,000+ operations/second on a single instance

**What I know about PostgreSQL performance:**
- PostgreSQL stores data on disk (with buffer cache)
- Simple indexed SELECT: ~1-5ms for warm cache, ~10-50ms for cold cache
- Can handle ~10,000+ simple queries/second

**Is 100x accurate?**
- Best case: Redis 0.1ms vs PostgreSQL cold cache 10ms → 100x ✓
- Typical case: Redis 0.1ms vs PostgreSQL warm cache 1ms → 10x
- With connection pooling: Redis 0.1ms vs PostgreSQL 0.5ms → 5x
- For complex queries: Redis doesn't support them, comparison is invalid

**The claim is misleading because:**
1. "100x" is the best-case scenario, not typical
2. It compares different things (key-value lookup vs SQL query)
3. PostgreSQL with warm buffer pool is much faster than cold
4. The comparison ignores that PostgreSQL does things Redis can't (joins, transactions, complex queries)

**Corrected claim:** "Redis is 5-100x faster than PostgreSQL for simple key-value lookups, depending on whether PostgreSQL's buffer cache is warm. For complex queries, the comparison doesn't apply — Redis doesn't support SQL."
</think>

**Claim verification: "Redis is 100x faster" — MISLEADING.**

| Scenario | Redis | PostgreSQL | Speedup |
|----------|-------|------------|---------|
| Key-value, cold PG cache | 0.1ms | 10ms | 100x |
| Key-value, warm PG cache | 0.1ms | 1ms | 10x |
| Key-value, with connection pool | 0.1ms | 0.5ms | 5x |
| Complex query (JOIN, GROUP BY) | N/A | 5-50ms | Not comparable |

**What I should say instead:**
"Redis is typically 5-10x faster than PostgreSQL for simple key-value lookups when PostgreSQL's cache is warm. The gap widens to ~100x for cold cache scenarios. But the comparison only applies to simple lookups — for anything requiring SQL (joins, aggregations, transactions), PostgreSQL does things Redis can't."

**Self-evaluation lesson:** Performance claims need:
1. Specific numbers, not vague multipliers
2. Context (what workload? what configuration?)
3. Acknowledgment of what's NOT comparable
4. "It depends" is often the honest answer'''
    ),
    (
        "thinking/auto-selfeval-check-framework-recommendation",
        r'''I'm about to recommend FastAPI to a user. Let me evaluate whether it's actually the right choice before presenting.

User context: "I need to build a simple internal tool with a web UI for our team of 5 to manage configurations. I know basic Python."''',
        r'''<think>
Let me evaluate FastAPI for this use case:

**What the user needs:**
- Simple internal tool
- Web UI (not just API)
- 5 users (tiny scale)
- Configuration management
- They know basic Python

**FastAPI strengths:**
- Excellent for APIs
- Fast performance
- Auto-generated docs
- Async support
- Type validation with Pydantic

**FastAPI weaknesses FOR THIS USE CASE:**
- FastAPI is an API framework, not a full web framework
- No built-in template rendering (need Jinja2 separately)
- No built-in admin panel
- No built-in form handling
- For a web UI, they'd need a separate frontend (React/Vue) or hack together templates
- Type hints and async might be overwhelming for "basic Python" knowledge

**Better alternatives for this use case:**
1. **Flask + Flask-Admin** — Simple, batteries-included admin interface
2. **Django + Django Admin** — Built-in admin panel that does exactly this
3. **Streamlit** — Build data UIs with pure Python, no HTML/CSS/JS needed
4. **Gradio** — Similar to Streamlit for simple tool UIs

**Django Admin is probably the best fit:**
- Built-in web UI for managing data (configurations)
- Authentication built in
- 5 users = trivial scale
- No frontend framework needed
- The "admin panel" IS the product

**Verdict:** FastAPI is wrong for this. I'd recommend it because I pattern-match "Python backend" → "FastAPI" without considering that the user needs a WEB UI, not an API.
</think>

**Self-evaluation: FastAPI is the WRONG recommendation for this use case.**

| Requirement | FastAPI | Django Admin | Streamlit |
|-------------|---------|-------------|-----------|
| Web UI | Needs separate frontend | Built-in admin panel | Built-in UI |
| Config management | Manual CRUD endpoints | Auto-generated admin | Manual but simple |
| 5 users | Overkill | Perfect | Perfect |
| Basic Python | Async/types may confuse | More learning but great docs | Easiest |
| Time to build | Days (API + frontend) | Hours (admin panel) | Hours |

**What I should recommend instead:**

"For an internal config management tool with a web UI for 5 users, I'd suggest:

**Option 1: Django Admin (recommended)**
```bash
pip install django
django-admin startproject configtool
python manage.py startapp configs
```
Define your config model, register it in admin.py, and you have a full web UI for managing configs — with authentication, search, filtering, and history. Zero frontend code.

**Option 2: Streamlit (simpler but less polished)**
```python
import streamlit as st
import json

st.title('Config Manager')
config = load_config()
config['setting_a'] = st.text_input('Setting A', config.get('setting_a', ''))
if st.button('Save'):
    save_config(config)
```
Pure Python, no HTML/CSS/JS, runs in browser."

**Why I almost recommended FastAPI:** I default to "latest popular framework" without checking if it matches the actual requirements. A web UI for 5 people is a different problem than a scalable API.'''
    ),
    (
        "thinking/auto-selfeval-verify-debugging-steps",
        r'''A user's Flask app returns 500 errors. I'm about to suggest debugging steps. Let me verify my suggested order is efficient:

My draft:
1. Check the Flask logs
2. Add try/except around each route
3. Check the database connection
4. Restart the server
5. Check if all dependencies are installed''',
        r'''<think>
Let me evaluate my debugging steps for efficiency:

**Step 1: Check the Flask logs** — CORRECT first step. The 500 error usually includes a traceback that tells you exactly what's wrong. This should solve 80% of cases immediately.

**Step 2: Add try/except around each route** — WRONG as step 2. This is a code change that hides the problem rather than diagnosing it. Also, Flask already shows tracebacks in debug mode. This should not be step 2.

**Step 3: Check the database connection** — PREMATURE. Only check this if the traceback points to a database error. Don't guess at causes before reading the error.

**Step 4: Restart the server** — TOO LATE. This should be step 0 or 1 (maybe it's a stale process). But also: restarting without understanding the error just temporarily masks issues.

**Step 5: Check dependencies** — TOO LATE. ImportError would be obvious in the traceback. Should only check if the traceback suggests a missing module.

**Better ordering:**
1. Read the actual error message/traceback (the answer is usually right there)
2. Enable debug mode if not already (`FLASK_DEBUG=1`)
3. Reproduce the error (which route? which input?)
4. Fix based on the traceback
5. If no traceback: check logs, then check configuration

**My original steps are GUESS-BASED, not EVIDENCE-BASED debugging.**
</think>

**Self-evaluation: My debugging steps are inefficient — guessing instead of reading the error.**

**Original order (guess-based):**
1. Check logs ← OK but should be more specific
2. Add try/except ← WRONG (hides errors, doesn't fix them)
3. Check database ← PREMATURE guess
4. Restart server ← Doesn't fix anything
5. Check dependencies ← Random guess

**Corrected order (evidence-based):**

```
Step 1: Read the error
  FLASK_DEBUG=1 python app.py
  → The traceback tells you EXACTLY what's wrong in 80% of cases

Step 2: Reproduce the error
  Which URL? Which HTTP method? Which data?
  curl -v http://localhost:5000/the-failing-route

Step 3: Fix based on the traceback
  TypeError → wrong argument types
  ImportError → missing package
  OperationalError → database issue
  KeyError → missing dict key / form field
  AttributeError → wrong object type or None

Step 4: If no clear traceback, check:
  - Is debug mode on? (FLASK_DEBUG=1)
  - Is there a try/except swallowing the real error?
  - Check application logs (not just console)

Step 5: Only if above fails:
  - Check database connectivity
  - Check environment variables
  - Check recent code changes (git diff)
```

**The principle: Read the error before guessing at causes.** The traceback is the most efficient debugging tool. My original steps skipped it entirely.'''
    ),
    (
        "thinking/auto-selfeval-check-answer-accessibility",
        r'''A user asked "What is Docker?" and I wrote a technical answer. Let me check if it's accessible to someone who might be a beginner:

My draft: "Docker is a containerization platform that uses Linux namespaces and cgroups to create isolated environments. It leverages a layered filesystem (OverlayFS) with copy-on-write semantics to efficiently share base images across containers."''',
        r'''<think>
Let me evaluate this for a beginner who asked "What is Docker?":

**Jargon check:**
- "containerization platform" — assumes they know what containerization is
- "Linux namespaces" — kernel-level concept, way too advanced
- "cgroups" — kernel-level, way too advanced
- "isolated environments" — vague without context
- "layered filesystem" — storage implementation detail
- "OverlayFS" — Linux filesystem, way too advanced
- "copy-on-write semantics" — CS concept, way too advanced

**Accessibility score:** 1/10. This answer is for someone who already understands Docker and wants to know HOW it works internally.

**The user asked "What is Docker?" which means:**
- They don't know what Docker is
- They need a CONCEPTUAL explanation, not an implementation explanation
- They need an analogy to something they already know
- They need to understand WHY they'd use it, not HOW it works internally

**A good answer for "What is Docker?" should:**
1. Start with a relatable analogy
2. Explain the PROBLEM it solves (works on my machine but not in production)
3. Explain WHAT it does in simple terms
4. Give a concrete example
5. Skip all implementation details (namespaces, cgroups, OverlayFS)
</think>

**Self-evaluation: WAY too technical for someone asking "What is Docker?" Rating: 1/10 for accessibility.**

**My answer assumes the reader already knows:** containerization, Linux kernel internals, filesystem concepts. A beginner knows none of these.

**Corrected answer:**

"Docker lets you package your application with everything it needs (code, libraries, system tools) into a **container** that runs the same everywhere.

**The problem it solves:** 'It works on my machine but not on the server.' Docker eliminates this by packaging the exact environment your app needs.

**Analogy:** Think of a shipping container. Before containers, cargo was loaded loosely onto ships — different sizes, different handling. Shipping containers standardized this: any container fits on any ship, truck, or train. Docker does the same for software — any Docker container runs on any machine with Docker installed.

**Quick example:**
```bash
# Package your app into a container:
docker build -t my-app .

# Run it anywhere:
docker run my-app
# Works the same on your laptop, your colleague's laptop, and the server
```

**When to use Docker:**
- Setting up consistent development environments
- Deploying applications to servers
- Running multiple apps on the same server without conflicts"

**What I changed:**
- Removed ALL jargon (namespaces, cgroups, OverlayFS)
- Added a relatable analogy (shipping containers)
- Focused on the PROBLEM it solves, not HOW it works
- Added a concrete example'''
    ),
    (
        "thinking/auto-selfeval-check-completeness-security",
        r'''A user asked about securing their Express.js API. I listed 3 things. Let me check if I covered enough:

My draft:
"To secure your Express API:
1. Use HTTPS
2. Add rate limiting
3. Validate input"

Is this complete enough?''',
        r'''<think>
Let me evaluate completeness against a security checklist:

**What I mentioned (3 items):**
1. HTTPS — correct, important ✓
2. Rate limiting — correct ✓
3. Input validation — correct ✓

**What I'm missing (critical):**
4. Authentication — WHO can access the API? JWT, session, API keys?
5. Authorization — WHAT can each user do? Role-based access?
6. CORS configuration — which origins can call the API?
7. Helmet.js — security headers (XSS protection, content type sniffing, etc.)
8. SQL injection / NoSQL injection prevention — parameterized queries
9. Dependency security — npm audit, no known vulnerabilities

**What I'm missing (important):**
10. Error handling — don't expose stack traces in production
11. Logging — audit trail for security events
12. Environment variables — no secrets in code
13. Cookie security — httpOnly, secure, sameSite flags

**Completeness assessment:**
- I listed 3 out of ~13 important security measures
- Missing critical items: authentication, authorization, CORS
- My answer covers maybe 25% of what's needed

**Verdict:** Dangerously incomplete. A user following only my 3 points would have an API that's better than nothing but still has major security gaps.
</think>

**Self-evaluation: INCOMPLETE. 3 out of ~13 critical security measures. Rating: 3/10.**

**Complete Express.js API security checklist:**

```javascript
const express = require('express');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const cors = require('cors');

const app = express();

// 1. Security headers (XSS, sniffing, clickjacking)
app.use(helmet());

// 2. CORS — restrict to known origins
app.use(cors({ origin: 'https://myapp.com' }));

// 3. Rate limiting
app.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 100 }));

// 4. Body parsing with size limits
app.use(express.json({ limit: '10kb' }));

// 5. HTTPS (enforce in production)
if (process.env.NODE_ENV === 'production') {
  app.use((req, res, next) => {
    if (req.headers['x-forwarded-proto'] !== 'https')
      return res.redirect(`https://${req.headers.host}${req.url}`);
    next();
  });
}

// 6. Authentication middleware
app.use('/api', authenticateJWT);

// 7. Input validation (per route)
app.post('/api/users', validateInput(userSchema), createUser);

// 8. Error handling (don't expose internals)
app.use((err, req, res, next) => {
  logger.error(err);
  res.status(500).json({ error: 'Internal server error' });
  // NOT: res.status(500).json({ error: err.stack })
});
```

**Also needed (not shown in code):**
- `npm audit` regularly for dependency vulnerabilities
- Environment variables for secrets (`process.env.JWT_SECRET`)
- Parameterized queries for database access
- Cookie flags: `httpOnly: true, secure: true, sameSite: 'strict'`
- Security logging for authentication events

**My original 3 items were correct but dangerously incomplete.** Security requires defense in depth — multiple layers, not just a few.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
