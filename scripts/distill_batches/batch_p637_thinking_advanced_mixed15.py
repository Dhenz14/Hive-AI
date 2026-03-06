"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 15)"""

PAIRS = [
    (
        "thinking/uncertainty-typescript-vs-python-backend",
        "We're starting a new backend project. Team is split between TypeScript (Node.js) and Python (FastAPI). Both groups have experience. What should we choose?",
        r'''<think>
TypeScript vs Python for backend — genuinely close decision when the team knows both. Let me think through the factors.

**TypeScript/Node.js advantages:**
- Same language frontend and backend (full-stack JS)
- Strong type system catches bugs at compile time
- npm ecosystem is massive
- Excellent for real-time (WebSocket, event-driven)
- Better concurrency model for I/O-bound work (event loop)

**Python/FastAPI advantages:**
- Cleaner syntax, faster to write
- Better for data science/ML integration
- FastAPI is incredibly productive (auto-docs, validation)
- Python ecosystem for scientific/data work
- Easier to hire Python developers (larger pool)

**For THIS decision:** team knows both equally, so familiarity isn't a differentiator.

Key questions:
1. Does the project involve data/ML? → Python advantage
2. Does it share code with a frontend? → TypeScript advantage
3. Is it heavily I/O bound? → Both handle this well
4. Does it need strong typing? → TypeScript has an edge (Python typing is optional)

**Confidence:** 50/45/5 — this is genuinely close.
- 50% TypeScript (type safety, frontend alignment)
- 45% Python (productivity, ecosystem breadth)
- 5% something else (Go if performance-critical)
</think>

This is a genuinely close call — confidence: **50% TypeScript, 45% Python**.

## Decision Factors

```
FACTOR                    TYPESCRIPT           PYTHON
──────────────────────────────────────────────────────
Type safety               Strong (native)      Good (optional hints)
Web framework maturity     Express/Fastify      FastAPI/Django
API documentation          Manual or codegen    FastAPI auto-generates OpenAPI
Frontend code sharing      Same language ✓      Different language
Data/ML ecosystem          Limited              Excellent (pandas, numpy, sklearn)
Async I/O                  Native (event loop)  Native (asyncio)
Package ecosystem          npm (massive)        PyPI (massive)
Startup speed              Slower (compile)     Faster (interpreted)
Runtime performance        Good (V8 JIT)        Good enough (async I/O bound)
Hiring pool                Large                Larger
```

## When TypeScript Wins

```
Choose TypeScript if:
  ✓ You have a React/Vue/Angular frontend (same language = shared types)
  ✓ Type safety is a priority (catches bugs at compile time)
  ✓ Real-time features (WebSocket, SSE — Node.js excels here)
  ✓ Your team already uses TypeScript on the frontend
  ✓ You want to share validation schemas between frontend and backend

Example: SaaS web app with React frontend + REST API
```

## When Python Wins

```
Choose Python if:
  ✓ Data processing, ML, or analytics involved
  ✓ FastAPI's auto-generated docs are important (B2B API)
  ✓ Rapid prototyping (Python is faster to write)
  ✓ Integration with data science tools (pandas, scikit-learn)
  ✓ Your team is more productive in Python

Example: API with data pipelines, ML features, or heavy business logic
```

## My Honest Take

```
For a standard web API (CRUD + business logic):
  Both are excellent. Pick the one your team is MORE excited about.
  Developer enthusiasm matters more than marginal technical differences.

For a project with ANY data/ML component:
  Python. The ecosystem advantage is overwhelming.

For a project sharing code with a TypeScript frontend:
  TypeScript. Shared types between frontend and backend is a real productivity win.

For "I truly can't decide":
  FastAPI (Python). It has the best developer experience of any
  web framework: auto-docs, auto-validation, async native,
  and your team can ship features on day one.
```'''
    ),
    (
        "thinking/adversarial-logging-sensitive-data",
        "I realized our application logs might contain sensitive data. We log full request/response bodies for debugging. What's the risk and how do I fix it?",
        r'''<think>
Logging sensitive data — this is a common and serious issue. Let me think through the attack vectors.

**What might be in request/response logs:**
- Passwords (login requests)
- API keys / tokens (authorization headers)
- Credit card numbers (payment requests)
- Personal data (addresses, phone numbers, SSN)
- Health information (HIPAA-regulated)
- Session tokens (authentication)

**Risks:**
1. Log files are often less protected than databases
2. Log aggregation services (ELK, Splunk) may be accessible to many employees
3. Log files may be retained for years (data retention violation)
4. Compliance violations (PCI-DSS, HIPAA, GDPR)
5. If logs are breached, attacker gets passwords and tokens

**The fix isn't "stop logging" — it's "log safely":**
1. Redact/mask sensitive fields before logging
2. Never log request bodies for auth endpoints
3. Filter specific header values (Authorization, Cookie)
4. Use structured logging with a sanitization layer
</think>

This is a serious issue. Logs are often the least protected part of a system but can contain the most sensitive data.

## What's Probably in Your Logs Right Now

```python
# If you log full request/response bodies:
logger.info(f"Request: {request.json()}")

# Your logs contain:
# POST /login: {"email": "alice@example.com", "password": "MyP@ssw0rd!"}
# POST /payment: {"card_number": "4111111111111111", "cvv": "123"}
# GET /api/me: Authorization: Bearer eyJhbGciOi...
# POST /profile: {"ssn": "123-45-6789", "address": "123 Main St"}

# Anyone with log access (developers, ops, log aggregation service)
# can see passwords, credit cards, tokens, and personal data.
```

## The Fix: Sanitize Before Logging

```python
# Middleware that sanitizes sensitive data from logs
SENSITIVE_FIELDS = {
    "password", "new_password", "current_password",
    "credit_card", "card_number", "cvv", "cvc",
    "ssn", "social_security",
    "token", "access_token", "refresh_token", "api_key",
    "secret", "private_key",
}

SENSITIVE_HEADERS = {
    "authorization", "cookie", "x-api-key",
}

def sanitize_dict(data: dict) -> dict:
    """Recursively redact sensitive fields."""
    if not isinstance(data, dict):
        return data
    sanitized = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_FIELDS:
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [sanitize_dict(v) if isinstance(v, dict) else v for v in value]
        else:
            sanitized[key] = value
    return sanitized

def sanitize_headers(headers: dict) -> dict:
    return {
        k: "***REDACTED***" if k.lower() in SENSITIVE_HEADERS else v
        for k, v in headers.items()
    }

# Usage in logging middleware:
@app.middleware("http")
async def log_requests(request, call_next):
    body = await request.json() if request.method in ("POST", "PUT") else {}
    safe_body = sanitize_dict(body)
    safe_headers = sanitize_headers(dict(request.headers))

    logger.info("request",
        method=request.method,
        path=request.url.path,
        headers=safe_headers,      # Authorization: ***REDACTED***
        body=safe_body,            # password: ***REDACTED***
    )
    response = await call_next(request)
    return response
```

## Rules for Safe Logging

```
NEVER LOG:
  ✗ Passwords or password hashes
  ✗ Full credit card numbers (log last 4 digits at most)
  ✗ API keys or tokens
  ✗ Social security numbers
  ✗ Session cookies
  ✗ Private keys or secrets
  ✗ Full request bodies on auth/payment endpoints

SAFE TO LOG:
  ✓ Request method, path, status code, duration
  ✓ User ID (not email/name unless needed)
  ✓ Error messages (without user data)
  ✓ Sanitized request bodies (sensitive fields redacted)
  ✓ Request ID for tracing

COMPLIANCE:
  PCI-DSS: must NOT log full card numbers, CVV ever
  HIPAA: must NOT log patient health information
  GDPR: must be able to DELETE user data from logs
  SOC2: must have access controls on log systems
```'''
    ),
    (
        "thinking/causal-memory-pressure-python-large-files",
        "Our Python data processing script crashes with MemoryError when processing a 10GB CSV file. It works fine with small files. Why does it run out of memory and how do I fix it?",
        r'''<think>
Python MemoryError on large CSV. The causal chain is straightforward but important.

**Why it fails:**
Most beginners do: `data = pd.read_csv("large_file.csv")` or `lines = file.readlines()`

Both load the ENTIRE file into memory. A 10GB CSV requires at least 10GB of RAM, plus overhead for Python objects (typically 2-5x the file size in memory).

**Causal chain:**
10GB file → read_csv loads all into memory → 20-50GB memory needed → exceeds available RAM → MemoryError

**Solutions (in order of simplicity):**
1. Stream/iterate instead of loading all at once
2. Use chunked reading (pd.read_csv with chunksize)
3. Use memory-mapped files
4. Use a database (SQLite, DuckDB)
5. Use Dask or Polars (lazy evaluation)

Let me provide practical solutions.
</think>

The problem: you're loading the entire 10GB file into memory at once. Python objects add 2-5x overhead, so you need 20-50GB RAM.

## The Cause

```python
# ❌ Loads ENTIRE file into memory
import pandas as pd
df = pd.read_csv("data.csv")  # 10GB file → 20-50GB in memory → MemoryError

# ❌ Also loads everything into memory
with open("data.csv") as f:
    lines = f.readlines()      # 10GB of strings in a list → MemoryError

# WHY 2-5x overhead:
# "42" as text = 2 bytes
# 42 as Python int = 28 bytes (14x!)
# A row with 50 columns = 50 Python objects + pandas Series overhead
```

## Fix 1: Stream Line by Line (Simplest)

```python
# ✅ Process one line at a time — constant memory usage
import csv

total = 0
count = 0
with open("data.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += float(row["amount"])
        count += 1
        # Only ONE row in memory at a time!

print(f"Average: {total / count}")
# Memory usage: ~10MB regardless of file size
```

## Fix 2: Chunked Pandas (Best for Familiar API)

```python
# ✅ Process in chunks — limited memory, familiar pandas API
import pandas as pd

results = []
for chunk in pd.read_csv("data.csv", chunksize=100_000):
    # Each chunk is 100K rows (~50MB in memory)
    chunk_result = chunk.groupby("category")["amount"].sum()
    results.append(chunk_result)

# Combine chunk results
final = pd.concat(results).groupby(level=0).sum()
# Memory usage: ~50MB per chunk instead of 50GB total
```

## Fix 3: DuckDB (Best for SQL-Like Analysis)

```python
# ✅ DuckDB: processes files larger than RAM using disk
import duckdb

# Reads directly from CSV without loading into memory!
result = duckdb.sql("""
    SELECT category, SUM(amount) as total, COUNT(*) as count
    FROM read_csv_auto('data.csv')
    GROUP BY category
    ORDER BY total DESC
""").fetchdf()

# DuckDB streams the file and uses disk for intermediate results
# Can handle 100GB+ files on a laptop with 8GB RAM
```

## Fix 4: Polars (Best for Performance)

```python
# ✅ Polars: lazy evaluation, processes without loading everything
import polars as pl

result = (
    pl.scan_csv("data.csv")                # Lazy — doesn't read yet
    .group_by("category")
    .agg(pl.col("amount").sum())
    .sort("amount", descending=True)
    .collect()                              # NOW reads + processes efficiently
)
# Polars uses streaming internally — constant memory for large files
# Also 10-100x faster than pandas for large datasets
```

## When to Use Each Approach

```
APPROACH          WHEN TO USE                      MEMORY USAGE
──────────────────────────────────────────────────────────────────
Line-by-line      Simple aggregation/filtering     ~10MB (constant)
Chunked pandas    Need pandas API, moderate files   ~50-200MB
DuckDB            SQL queries on files              ~100MB (uses disk)
Polars            Performance-critical processing   ~100MB (streaming)
SQLite import     Need repeated queries on same data ~10MB + disk
```'''
    ),
    (
        "thinking/abstraction-error-retry-to-resilience-policy",
        "I have retry logic scattered across 15 different API calls in our codebase. Each has slightly different retry counts, delays, and exception handling. How do I standardize this?",
        r'''<think>
Scattered retry logic — let me ladder this from concrete deduplication to policy.

**Concrete:** 15 different retry implementations with inconsistent behavior.
**Pattern:** Extract a generic retry decorator/wrapper.
**Principle:** Define retry policies as configuration, not code.
**Policy:** Every external call should have a declared resilience policy.
</think>

Let me build from deduplication to a proper resilience policy.

## Level 1: Extract a Generic Retry

```python
# ❌ Current: 15 different retry implementations
def call_payment_api(data):
    for i in range(3):
        try:
            return payment.charge(data)
        except ConnectionError:
            time.sleep(2 ** i)
    raise PaymentError("Failed after 3 retries")

def call_email_api(to, body):
    attempts = 0
    while attempts < 5:
        try:
            return email.send(to, body)
        except (Timeout, ConnectionError) as e:
            attempts += 1
            time.sleep(attempts * 2)
    # No final raise — silently fails!

# Each has different: retry count, delay, exceptions, error handling


# ✅ Extract once, use everywhere
import time
import random
from functools import wraps

def retry(
    max_attempts=3,
    base_delay=1.0,
    exceptions=(Exception,),
    on_retry=None,
):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        raise
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    if on_retry:
                        on_retry(func.__name__, attempt + 1, delay, e)
                    time.sleep(delay)
        return wrapper
    return decorator

def log_retry(func_name, attempt, delay, error):
    logger.warning(f"Retrying {func_name} (attempt {attempt}, delay {delay:.1f}s): {error}")
```

## Level 2: Declare Retry Policies as Configuration

```python
# Define policies per service, not per call
RETRY_POLICIES = {
    "payment": {
        "max_attempts": 3,
        "base_delay": 1.0,
        "exceptions": (ConnectionError, Timeout),
    },
    "email": {
        "max_attempts": 5,
        "base_delay": 2.0,
        "exceptions": (ConnectionError, Timeout, SMTPError),
    },
    "analytics": {
        "max_attempts": 2,
        "base_delay": 0.5,
        "exceptions": (ConnectionError,),
    },
}

# Apply declaratively
@retry(**RETRY_POLICIES["payment"], on_retry=log_retry)
def charge_customer(amount, customer_id):
    return payment_api.charge(amount, customer_id)

@retry(**RETRY_POLICIES["email"], on_retry=log_retry)
def send_email(to, subject, body):
    return email_client.send(to, subject, body)

@retry(**RETRY_POLICIES["analytics"], on_retry=log_retry)
def track_event(event_name, data):
    return analytics_api.track(event_name, data)
```

## Level 3: Use a Resilience Library

```python
# For production: use tenacity (Python) — handles edge cases you haven't thought of
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type((ConnectionError, Timeout)),
    before_sleep=lambda state: logger.warning(
        f"Retrying {state.fn.__name__} after {state.outcome.exception()}"
    ),
)
def charge_customer(amount, customer_id):
    return payment_api.charge(amount, customer_id)

# tenacity handles: jitter, max delay cap, callback hooks,
# async support, statistics, and more
```

## Level 4: Policy — Resilience by Default

```
RULE: Every external dependency gets a declared resilience policy.

PAYMENT (critical, money involved):
  Retries: 3, exponential backoff, max 30s
  Circuit breaker: 5 failures → open 60s
  Timeout: 10s
  Fallback: queue for manual processing

EMAIL (important, but delayed OK):
  Retries: 5, exponential backoff, max 5 min
  Timeout: 30s
  Fallback: dead letter queue

ANALYTICS (best effort):
  Retries: 1
  Timeout: 2s
  Fallback: drop silently (analytics loss is acceptable)

These policies are DOCUMENTATION as much as code.
New team members can see exactly how each dependency is handled.
```'''
    ),
    (
        "thinking/multiperspective-code-ownership",
        "Should teams own specific parts of the codebase (strong code ownership) or should anyone be able to change anything (collective ownership)?",
        r'''<think>
Code ownership models — there are legitimate perspectives on both sides.

**Strong ownership (one team owns each component):**
- Deep expertise: team knows their code intimately
- Accountability: clear who to ask, who to fix bugs
- Quality: owners care about long-term code health
- But: bottleneck (need the owning team for any change), silos

**Collective ownership (anyone changes anything):**
- No bottlenecks: any developer can fix any bug
- Knowledge sharing: everyone learns the full codebase
- Flexibility: work isn't blocked by team availability
- But: "everybody's responsibility is nobody's responsibility", inconsistency

**The real-world answer:**
Most successful organizations use a HYBRID: weak code ownership.
- Teams own components (are responsible for them)
- But anyone CAN contribute (via pull request reviewed by owners)
- This gets the accountability of ownership with the flexibility of open contribution
</think>

Both models have legitimate benefits. Here's the analysis.

## Strong Ownership: "This Is Our Code"

```
HOW IT WORKS:
  Auth Service → Team Alpha owns it
  Payment Service → Team Beta owns it
  Search Service → Team Gamma owns it

  Need a change to Auth? Go through Team Alpha.
  Bug in Payment? Team Beta is on call for it.

BENEFITS:
  ✓ Deep expertise (team knows every edge case)
  ✓ Clear accountability (who to page at 3 AM: obvious)
  ✓ Consistent quality (one team's standards, one vision)
  ✓ Faster decisions (team makes their own architectural choices)

PROBLEMS:
  ✗ Bottleneck: need Team Alpha for a 2-line auth fix → wait 3 days
  ✗ Bus factor: Team Alpha all on vacation → nobody can touch Auth
  ✗ Silos: teams don't understand each other's code
  ✗ "Not my problem" mentality at boundaries
```

## Collective Ownership: "It's Everyone's Code"

```
HOW IT WORKS:
  Anyone can change anything. No permission needed.
  Code review by anyone who's available.

BENEFITS:
  ✓ No bottlenecks (any developer can fix any bug)
  ✓ Knowledge sharing (everyone learns everything)
  ✓ Flexibility (assign any developer to any task)
  ✓ No silos

PROBLEMS:
  ✗ "Everyone's responsibility is nobody's responsibility"
  ✗ Inconsistent patterns (10 developers, 10 coding styles)
  ✗ Unclear who to page when things break
  ✗ Changes without context (someone "fixes" code they don't understand)
  ✗ Quality degradation (no one feels personally accountable)
```

## The Hybrid: Weak Code Ownership (What Works)

```
WEAK OWNERSHIP:
  Teams OWN components (responsible for them)
  Anyone CAN contribute (via PR, reviewed by owners)

  Like a house with a homeowner:
    - The homeowner is responsible for maintenance
    - A neighbor CAN help fix the fence
    - But the homeowner reviews the work

IN PRACTICE:

  CODEOWNERS file (GitHub):
    # .github/CODEOWNERS
    /src/auth/**        @team-alpha
    /src/payments/**    @team-beta
    /src/search/**      @team-gamma

  What this means:
    - Anyone can open a PR to any code
    - PRs automatically request review from the owning team
    - Owners must approve before merge
    - Owners are responsible for bugs, quality, on-call

  Result:
    ✓ No bottleneck: anyone can contribute
    ✓ Quality maintained: owners review all changes
    ✓ Accountability clear: owners are on-call
    ✓ Knowledge sharing: contributors learn new code through PRs
```

## Decision Framework

```
TEAM SIZE     RECOMMENDED MODEL
─────────────────────────────────
< 5 devs      Collective ownership (everyone knows everything)
5-15 devs     Weak ownership (teams own areas, anyone can contribute)
15-50 devs    Weak ownership with CODEOWNERS enforced
50+ devs      Strong ownership (necessary at scale)

CODEBASE SIZE
─────────────────────────────────
< 50K LOC     Collective (small enough for everyone to understand)
50K-500K LOC  Weak ownership (too big for one person, needs experts)
> 500K LOC    Strong ownership (must have deep expertise per area)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
