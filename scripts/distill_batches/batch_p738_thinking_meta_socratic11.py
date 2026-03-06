"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 11)

Final 3C batch — additional scenarios to reach 60 pairs.
"""

PAIRS = [
    (
        "thinking/meta-socratic-overengineering-dry",
        r'''I noticed these two functions share some similar logic:

```python
def get_active_users(db):
    users = db.query(User).filter(User.active == True).all()
    result = []
    for user in users:
        result.append({
            'id': user.id,
            'name': user.name,
            'email': user.email,
        })
    return result

def get_active_admins(db):
    users = db.query(User).filter(User.active == True, User.role == 'admin').all()
    result = []
    for user in users:
        result.append({
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'role': user.role,
        })
    return result
```

I want to extract a generic `query_users` function that takes filters and field lists as parameters. Should I?''',
        r'''<think>
Q: Am I over-engineering this? Let me examine the "duplication."

Q: How similar are these functions really?
A: They share:
  - active == True filter
  - Same loop pattern
  - Similar dict construction

They differ:
  - Additional filter (role == 'admin')
  - Different output fields (admins include 'role')

Q: What would a "generic" version look like?
A:
```python
def query_users(db, filters=None, fields=None):
    query = db.query(User)
    for f in (filters or []):
        query = query.filter(f)
    users = query.all()
    return [{field: getattr(u, field) for field in (fields or ['id', 'name', 'email'])} for u in users]
```

Q: Is the generic version actually better?
A: It's:
  - Harder to read — need to understand the filter/field abstraction
  - Harder to extend — what if admins need a computed field?
  - Over-generalized — we have exactly 2 callers
  - Less discoverable — "how do I get active users?" → search for query_users with specific params

Q: What's the rule for DRY?
A: DRY says "don't repeat knowledge." These two functions represent DIFFERENT business concepts (active users vs active admins). They happen to have similar implementation, but they're likely to diverge over time.

Q: What if they diverge later?
A: Active users might need "last_login" but admins need "permissions." With a generic function, you'd start adding if/else for different use cases, making it worse than the original.

Q: Is 2 instances enough to justify abstraction?
A: No. The rule of three: wait for 3 similar cases before abstracting. With 2, you don't know enough about the pattern to generalize correctly.

The duplication is actually fine here. Two similar but distinct functions.
</think>

**Don't extract yet.** Two similar functions is not enough to justify an abstraction.

**Why the "duplication" is okay:**
- These represent **different business concepts** (active users vs active admins)
- They will likely **diverge over time** (admins might need permissions, users might need last_login)
- Two instances is not a pattern — it's a coincidence
- Each function is **5 lines, immediately understandable**

**Why the generic version would be worse:**
```python
# Generic: harder to read, harder to extend
result = query_users(db,
    filters=[User.active == True, User.role == 'admin'],
    fields=['id', 'name', 'email', 'role']
)
# What does this return? Need to read query_users to understand.

# Original: self-documenting
result = get_active_admins(db)
# Immediately clear what this does.
```

**The Rule of Three:**
1. **First time**: Just write it
2. **Second time**: Notice the similarity, but don't abstract yet
3. **Third time**: NOW you have enough examples to extract a good abstraction

**When to extract:**
```python
# If you later add:
def get_active_managers(db): ...
def get_active_support(db): ...
def get_active_by_department(db, dept): ...

# NOW you have a pattern worth extracting:
def get_active_users_by(db, **filters):
    return db.query(User).filter(User.active == True).filter_by(**filters).all()
```

**Quick improvement without abstraction:**
```python
def get_active_users(db):
    users = db.query(User).filter(User.active == True).all()
    return [{'id': u.id, 'name': u.name, 'email': u.email} for u in users]

def get_active_admins(db):
    users = db.query(User).filter(User.active == True, User.role == 'admin').all()
    return [{'id': u.id, 'name': u.name, 'email': u.email, 'role': u.role} for u in users]
```

Simplified to list comprehensions — same logic, less boilerplate, still separate.'''
    ),
    (
        "thinking/meta-socratic-blind-spots-docker",
        r'''Here's my Dockerfile for a Python Flask app:

```dockerfile
FROM python:3.11

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

EXPOSE 5000
CMD ["python", "app.py"]
```

Simple Dockerfile. Ready for production?''',
        r'''<think>
Q: What am I not considering? Let me check for blind spots.

Q: Is `python:3.11` the right base image?
A: `python:3.11` is based on Debian and is ~900MB. `python:3.11-slim` is ~150MB. `python:3.11-alpine` is ~50MB. Larger images = slower pulls, more attack surface.

Q: `COPY . .` — what does this copy?
A: EVERYTHING — including .git, __pycache__, .env files, test data, node_modules if any. Need a .dockerignore.

Q: Is the secret .env file being copied into the image?
A: If .env exists, yes. Now anyone with access to the Docker image has your secrets. Images are often pushed to registries. Secrets in images = secrets exposed.

Q: `RUN pip install` — is the cache layer efficient?
A: No. `COPY . .` copies all source code, then installs dependencies. Any code change invalidates the pip cache. Should copy requirements.txt first, install, then copy source.

Q: Is it running as root?
A: Yes, by default Docker runs as root. If the app has a vulnerability (RCE), the attacker gets root in the container.

Q: `CMD ["python", "app.py"]` — is this production-ready?
A: Flask's development server is not for production. Should use gunicorn.

Q: No health check?
A: Docker/Kubernetes can't know if the app is healthy without a HEALTHCHECK instruction.

Multiple production issues.
</think>

**Several production issues.** Here's the fixed version:

```dockerfile
# Use slim image (150MB vs 900MB)
FROM python:3.11-slim

# Create non-root user
RUN useradd --create-home appuser

WORKDIR /app

# Copy requirements first (better cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Don't run as root
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:8000/health || exit 1

# Production WSGI server, not Flask dev server
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
```

**And add `.dockerignore`:**
```
.git
.env
__pycache__
*.pyc
.pytest_cache
tests/
docs/
*.md
.vscode
node_modules
```

**Issues fixed:**

| Issue | Original | Fixed |
|-------|----------|-------|
| Image size | 900MB (full) | 150MB (slim) |
| Running as | root | appuser (non-root) |
| Cache efficiency | Every code change reinstalls deps | requirements.txt cached |
| Secrets | .env copied into image | .dockerignore excludes |
| Server | Flask dev server | gunicorn (production) |
| Health check | None | /health endpoint |
| Junk files | .git, __pycache__ copied | .dockerignore |'''
    ),
    (
        "thinking/meta-socratic-premature-optimization-index",
        r'''I'm setting up a new PostgreSQL database for my app. I want to add indexes on every column that might be used in a WHERE clause or JOIN. Here are the indexes I'm planning:

```sql
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_name ON users(name);
CREATE INDEX idx_users_created_at ON users(created_at);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_last_login ON users(last_login);
CREATE INDEX idx_users_city ON users(city);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at);
CREATE INDEX idx_orders_total ON orders(total);
CREATE INDEX idx_orders_product_id ON orders(product_id);
```

Better safe than sorry, right?''',
        r'''<think>
Q: Is this premature optimization?

Q: What's the cost of an index?
A:
  - Write overhead: every INSERT, UPDATE, DELETE must update EVERY index
  - Storage: each index takes disk space
  - Maintenance: VACUUM must maintain indexes, autovacuum takes longer
  - Planning: query planner considers all indexes, more indexes = slower planning (marginal)

Q: Do I know which queries will actually run?
A: No. The app isn't built yet. I'm guessing which columns will be queried. Some indexes might never be used.

Q: Which indexes are almost certainly needed?
A: - `users(email)` — for login lookup, should be UNIQUE index
   - `orders(user_id)` — for foreign key JOINs, almost always needed
   - Maybe `orders(created_at)` if you sort by date frequently

Q: Which indexes are probably wasteful?
A: - `users(name)` — name lookups are usually LIKE '%name%' which doesn't use B-tree index anyway
   - `users(status)` — if status has low cardinality (active/inactive), index barely helps
   - `users(role)` — low cardinality (admin/user/moderator), index barely helps
   - `users(city)` — rarely used in WHERE without other conditions
   - `orders(total)` — when do you query by exact total amount?

Q: What's the right approach?
A: Start with the obvious foreign key and unique indexes. Add others based on actual slow query log analysis. `EXPLAIN ANALYZE` tells you exactly which queries need indexes.

"Better safe than sorry" doesn't apply — excess indexes actively hurt write performance.
</think>

**This is premature indexing.** You're guessing which queries will be slow before writing any queries. Some of these indexes will hurt performance, not help.

**Start with only these (almost always needed):**
```sql
-- Unique constraint on email (for login)
CREATE UNIQUE INDEX idx_users_email ON users(email);

-- Foreign key indexes (for JOINs)
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_product_id ON orders(product_id);
```

**Why many of your indexes are wasteful:**

| Index | Problem |
|-------|---------|
| `users(name)` | Text search uses `LIKE '%name%'` → B-tree index not used |
| `users(status)` | Low cardinality (2-3 values) → index barely helps, full scan is fine |
| `users(role)` | Low cardinality → same problem |
| `users(city)` | Rarely queried alone |
| `orders(total)` | When do you `WHERE total = 49.99`? Almost never |

**Cost of excess indexes:**
```
12 indexes on 2 tables →
- Every INSERT updates 12 index structures
- Every UPDATE potentially updates multiple indexes
- Storage: each index ≈ 10-30% of table size
- With 1M orders: 12 indexes could be 2-5GB of index storage
```

**The right approach — add indexes based on evidence:**
```sql
-- Step 1: Enable slow query logging
ALTER SYSTEM SET log_min_duration_statement = '100';  -- Log queries > 100ms

-- Step 2: Find slow queries, analyze them
EXPLAIN ANALYZE SELECT * FROM orders WHERE status = 'pending' AND created_at > '2024-01-01';

-- Step 3: Add targeted indexes
-- If this query is slow AND frequent:
CREATE INDEX idx_orders_status_created ON orders(status, created_at);
-- Composite index is much better than two single-column indexes
```

**Rule**: Index foreign keys and unique columns at creation. Add others when `EXPLAIN ANALYZE` shows sequential scans on large tables.'''
    ),
    (
        "thinking/meta-socratic-simplest-solution-monitoring",
        r'''I want to add monitoring to my Flask app. I'm planning to set up Prometheus, Grafana, AlertManager, Jaeger for distributed tracing, and a custom metrics exporter. The app runs on a single server with about 50 users. Should I set all this up?''',
        r'''<think>
Q: Is this the simplest monitoring solution?

Q: What problem am I trying to solve?
A: I want to know:
  - Is the app running?
  - Are there errors?
  - Is performance acceptable?
  - When something breaks, can I diagnose it?

Q: Does a single-server app with 50 users need Prometheus + Grafana + Jaeger?
A: That's an observability stack for a distributed system with 50 services. For 1 server, it's massive overkill.

Q: What's the minimal monitoring that answers my questions?
A:
  1. Is it running? → Health check endpoint + uptime monitor (UptimeRobot, free)
  2. Are there errors? → Python logging to a file + error alerts
  3. Performance? → Request timing in logs
  4. Diagnosis? → Application logs with context

Q: What does the Prometheus stack cost?
A:
  - Prometheus server: ~200MB RAM, storage for metrics
  - Grafana: ~200MB RAM, needs its own database
  - AlertManager: another service to configure
  - Jaeger: ~500MB RAM, storage for traces
  - Total: 4 additional services for a single Flask app

Q: When would I need this full stack?
A: Multiple services, microservices architecture, need SLO dashboards, need to trace requests across services. NOT for one app, one server.

The simplest monitoring is good logging + uptime monitoring.
</think>

**Way overkill.** You need monitoring, not an observability platform. For 1 server with 50 users:

**What you actually need (costs $0, takes 30 minutes):**

```python
# 1. Structured logging (you already need this)
import logging
logging.basicConfig(
    filename='/var/log/myapp/app.log',
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO
)

# 2. Health check endpoint
@app.route('/health')
def health():
    try:
        db.session.execute(text('SELECT 1'))
        return {'status': 'healthy'}, 200
    except Exception:
        return {'status': 'unhealthy'}, 500

# 3. Request timing (simple middleware)
@app.before_request
def start_timer():
    g.start = time.time()

@app.after_request
def log_request(response):
    duration = time.time() - g.start
    logger.info(f"{request.method} {request.path} {response.status_code} {duration:.3f}s")
    if duration > 1.0:
        logger.warning(f"Slow request: {request.path} took {duration:.1f}s")
    return response

# 4. Error alerts
@app.errorhandler(500)
def handle_500(e):
    logger.exception("Internal server error")
    # Send alert (Slack, email, PagerDuty)
    requests.post(SLACK_WEBHOOK, json={'text': f'500 error: {request.path}'})
    return {'error': 'Internal error'}, 500
```

**Plus:** Sign up for UptimeRobot (free) → monitors your `/health` endpoint every 5 minutes → emails you if the site is down.

**Your proposed stack vs what you need:**

| Tool | When needed | Your case |
|------|------------|-----------|
| Prometheus | Multiple services, custom metrics | 1 server → overkill |
| Grafana | Dashboard visualization | 50 users → check logs |
| AlertManager | Complex alert routing | Slack webhook → done |
| Jaeger | Distributed tracing | 1 service → no distributed traces |

**Scaling path:**
1. **50 users**: Logging + UptimeRobot + Slack alerts (now)
2. **5,000 users**: Add Sentry for error tracking ($0 free tier)
3. **50,000 users**: Consider Datadog or self-hosted Prometheus
4. **500,000+ users**: Full observability stack (Prometheus, Grafana, Jaeger)'''
    ),
    (
        "thinking/meta-socratic-data-assumption-date-format",
        r'''I'm parsing dates from a CSV file:

```python
from datetime import datetime

def parse_date(date_str):
    return datetime.strptime(date_str, "%m/%d/%Y")

# Usage with CSV:
for row in csv_reader:
    order_date = parse_date(row['date'])
```

The CSV comes from our US-based sales team. Simple date parsing. Any issues?''',
        r'''<think>
Q: Does my assumption about the data hold?

Q: Is every date in the CSV really in MM/DD/YYYY format?
A: Assumptions about date formats from human-entered data are almost always wrong at scale. Issues:
  - "1/5/2024" — is this January 5 or May 1? Format-dependent
  - "01/05/2024" — padded vs unpadded
  - "1/5/24" — two-digit year
  - "January 5, 2024" — written out
  - Empty cells — "" or "N/A" or "TBD"
  - "2024-01-05" — ISO format mixed in
  - Excel date serial numbers (44927)

Q: What if the CSV is generated by Excel?
A: Excel silently reformats dates based on locale. A US Excel might output "1/5/2024" while a UK colleague's Excel outputs "05/01/2024" for the same date. Same spreadsheet, different date strings depending on who opens it.

Q: What happens when strptime fails?
A: ValueError with an unhelpful message. No indication of which row or what the actual value was.

Q: Is there a more robust approach?
A: dateutil.parser.parse() handles multiple formats automatically. But even that can be ambiguous for dates like "01/02/2024" (Jan 2 or Feb 1?).

Q: What's the best practice?
A: 1. Validate a sample of the data first
   2. Use dateutil.parser with dayfirst=False for US dates
   3. Handle parsing errors gracefully with the row context
   4. Ideally, request ISO format dates from the source

Human-entered dates are one of the most unreliable data formats.
</think>

**Fragile.** Human-entered dates from CSV files almost never follow a consistent format.

**What will actually be in the CSV:**
```
01/05/2024     ← January 5 or May 1?
1/5/2024       ← No zero padding
1/5/24         ← Two-digit year
January 5 2024 ← Written out
2024-01-05     ← ISO format (from automated export)
N/A            ← No date available
              ← Empty cell
44927          ← Excel date serial number
```

**Robust version:**
```python
from dateutil import parser as dateparser
from datetime import datetime

def parse_date(date_str, row_num=None):
    if not date_str or date_str.strip() in ('', 'N/A', 'TBD', 'null'):
        return None

    try:
        # dayfirst=False for US dates (MM/DD/YYYY)
        return dateparser.parse(date_str, dayfirst=False)
    except (ValueError, TypeError) as e:
        context = f" (row {row_num})" if row_num else ""
        logger.warning(f"Unparseable date{context}: '{date_str}'")
        return None

# Usage:
for i, row in enumerate(csv_reader, start=2):  # start=2 (header is row 1)
    order_date = parse_date(row['date'], row_num=i)
    if order_date is None:
        skipped += 1
        continue
```

**Even better — validate before processing:**
```python
# Check a sample before committing to a format
sample = [row['date'] for row in list(csv_reader)[:20]]
print("Sample dates:", sample)
# Visually inspect: are they consistent? What format?
```

**Best practice: request ISO format from the source**
```
# Ask the sales team to export dates as:
2024-01-05  # ISO 8601 — unambiguous, sortable, universal
```

**Date parsing checklist:**
- Use `dateutil.parser` instead of `strptime` for human-entered data
- Set `dayfirst` explicitly based on source locale
- Handle empty/null values
- Log unparseable dates with row context
- Validate a sample before processing the full file'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
