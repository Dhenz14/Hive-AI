"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 5)

Scenarios: "Am I confusing correlation with causation?" (more),
"What am I not considering?", "Is this premature optimization?" (more)
"""

PAIRS = [
    (
        "thinking/meta-socratic-correlation-deploy-regression",
        r'''We deployed a new feature on Monday. On Tuesday, error rates spiked 3x. We reverted the feature and errors went back to normal on Wednesday. Clearly the new feature caused the errors. Our PM wants us to debug the feature code. Should we?''',
        r'''<think>
My initial approach: Feature deployed Monday → errors Tuesday → reverted Wednesday → errors gone. Seems conclusive.

Q: Am I confusing correlation with causation? The timeline is suspicious but let me think harder.

Q: What ELSE happened between Monday and Wednesday?
A: In a typical production environment:
  - Other teams may have deployed their own changes
  - A database migration might have run
  - Traffic patterns differ by day of week (Tuesday vs Monday)
  - A dependent service may have had issues
  - DNS changes, certificate renewals, infrastructure updates
  - The revert deployment itself may have triggered a restart that cleared a resource leak

Q: Did the errors correlate with the new feature's code paths?
A: That's the key question nobody asked. If the errors are in the new feature's endpoints → yes, likely caused by the feature. If the errors are in UNRELATED endpoints → something else is going on.

Q: Could the revert have fixed the issue for a different reason?
A: Possible. If the server had a memory leak, ANY deployment (including a revert) restarts the process and temporarily fixes it. The revert might have been coincidental.

Q: How do I distinguish causation from correlation here?
A: Check:
  1. Are the errors in the new feature's code paths?
  2. Did the error messages reference the new feature's classes/functions?
  3. Did the errors start EXACTLY at deploy time or gradually?
  4. Were there any OTHER changes between Monday and Wednesday?
  5. Can we reproduce the errors in staging with the new feature?

Q: What should we actually do?
A: Don't just "debug the feature code" blindly. First correlate the specific errors with the specific change. The PM's conclusion might be right, but it's not proven yet.
</think>

**The timeline is suggestive but not proof.** Before spending days debugging the feature, spend 30 minutes verifying causation.

**Quick checks to confirm or rule out the feature:**

1. **Check error locations**: Are errors in the new feature's code paths?
   ```bash
   # Filter error logs by the new feature's module
   grep "new_feature" error_logs_tuesday.log | wc -l
   grep -v "new_feature" error_logs_tuesday.log | wc -l
   ```
   If errors are in UNRELATED code → feature isn't the cause.

2. **Check error timing**: Did errors start at deploy time or later?
   - At deploy time → likely deploy-related
   - Hours after deploy → likely traffic/load related, may be coincidental

3. **Check what else changed**: Were there other deployments, config changes, or infra updates?

4. **Check if the revert "fix" was really a restart fix**:
   - Did memory/CPU drop after revert? → Might have been a resource leak in old code, masked by restart

**Common false attributions:**
- **Tuesday traffic spike**: Monday is light, Tuesday is peak → errors under load aren't caused by the feature
- **Deployment restart**: Any deploy restarts servers, clearing memory leaks, stale connections
- **Dependent service**: A downstream API had issues Tuesday, recovered Wednesday

**What to tell the PM:** "I'll verify the connection in 30 minutes before spending days debugging. If the errors aren't in the new feature's code paths, we're looking at the wrong thing."

**If it IS the feature:** Deploy to staging, run the same traffic pattern, reproduce the errors. Then debug with evidence, not assumptions.'''
    ),
    (
        "thinking/meta-socratic-not-considering-timezone",
        r'''I'm building a scheduling feature where users can set reminders. Here's my approach:

```python
from datetime import datetime

class Reminder:
    def __init__(self, user_id, message, remind_at):
        self.user_id = user_id
        self.message = message
        self.remind_at = remind_at  # datetime

    def is_due(self):
        return datetime.now() >= self.remind_at

def create_reminder(user_id, message, date_str):
    remind_at = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    return Reminder(user_id, message, remind_at)
```

This works for me locally. Ship it?''',
        r'''<think>
My initial approach: Simple reminder system — parse datetime, check if current time >= reminder time.

Q: What am I not considering? Let me systematically check blind spots.

Q: Timezones — what timezone is this operating in?
A: datetime.now() returns LOCAL time. datetime.strptime() creates a NAIVE datetime (no timezone info). This means:
  - A user in New York creates a reminder for "2024-03-15 09:00"
  - The server is in UTC (or US-West)
  - The reminder fires at the WRONG TIME for the user
  - With naive datetimes, there's no way to know what timezone the user intended

Q: What about daylight saving time?
A: During DST transitions, "2024-03-10 02:30" doesn't exist in US timezones (clocks skip from 2:00 to 3:00). datetime.strptime happily creates this impossible time.

Q: What happens when the server moves to a different timezone?
A: If you deploy from a US server to an EU server, all reminder times shift. Naive datetimes are implicitly tied to the server's timezone.

Q: What if the user travels across timezones?
A: If a user in New York sets a reminder for "9 AM meeting" and then flies to London, should it fire at 9 AM New York time or 9 AM London time? This is a product decision that needs to be explicit.

Q: What about the check frequency?
A: is_due() only works if something calls it. There's no scheduler. If the app checks every 5 minutes, reminders could fire up to 5 minutes late.

Q: What if two reminders are due at the same time?
A: Sequential processing — second reminder fires late.

Q: Is the date format user-friendly?
A: "%Y-%m-%d %H:%M" requires exact format. "March 15, 2024 9am" would fail.

Timezone handling is the critical missing piece. Naive datetimes in production are a well-known source of bugs.
</think>

**Don't ship this.** The timezone handling will cause reminders to fire at wrong times for every user not in the server's timezone.

**Critical fixes needed:**

```python
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

class Reminder:
    def __init__(self, user_id, message, remind_at_utc):
        self.user_id = user_id
        self.message = message
        self.remind_at_utc = remind_at_utc  # Always UTC

    def is_due(self):
        return datetime.now(ZoneInfo("UTC")) >= self.remind_at_utc

def create_reminder(user_id, message, date_str, user_timezone):
    # Parse in user's timezone, then convert to UTC for storage
    user_tz = ZoneInfo(user_timezone)
    local_time = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    aware_time = local_time.replace(tzinfo=user_tz)
    utc_time = aware_time.astimezone(ZoneInfo("UTC"))
    return Reminder(user_id, message, utc_time)

def display_reminder(reminder, user_timezone):
    # Convert from UTC to user's timezone for display
    user_tz = ZoneInfo(user_timezone)
    return reminder.remind_at_utc.astimezone(user_tz)
```

**The problems you didn't consider:**

| Issue | Impact |
|-------|--------|
| No timezone on datetimes | Reminders fire at server time, not user time |
| `datetime.now()` vs `datetime.now(tz)` | Naive vs aware — can't compare safely |
| DST transitions | "2:30 AM" may not exist on spring-forward day |
| Server migration | Moving servers changes all reminder times |
| No scheduler | `is_due()` needs something to call it periodically |

**Rules for datetime in production:**
1. **Store in UTC** — always, no exceptions
2. **Convert to user timezone for display** only
3. **Use aware datetimes** — never create naive datetimes
4. **Use `zoneinfo`** (Python 3.9+) or `pytz` — not manual offsets
5. **Accept user's timezone** with every time input'''
    ),
    (
        "thinking/meta-socratic-premature-optimization-orm",
        r'''I'm replacing all our SQLAlchemy ORM queries with raw SQL because "ORMs are slow." Here's an example of what I'm changing:

```python
# Before (SQLAlchemy ORM):
users = User.query.filter_by(active=True).order_by(User.created_at.desc()).limit(20).all()

# After (raw SQL):
users = db.engine.execute(
    "SELECT id, name, email, created_at FROM users WHERE active = true ORDER BY created_at DESC LIMIT 20"
).fetchall()
```

This should make our app much faster, right?''',
        r'''<think>
My initial approach: Raw SQL is faster than ORM...

Q: Is this premature optimization? Let me check the actual performance difference.
A: For a simple query like this:
  - ORM overhead: query building + object mapping ≈ 1-5ms
  - Database query time: depends on table size, but typically 1-50ms
  - Network latency to database: 1-5ms

The ORM overhead is a TINY fraction of the total request time. If the DB query takes 20ms, saving 3ms of ORM overhead is a 15% improvement — not noticeable to users.

Q: What's the actual bottleneck in the app?
A: Almost certainly not ORM overhead. Common bottlenecks:
  - N+1 queries (100 queries instead of 2)
  - Missing indexes (full table scan)
  - Unoptimized queries (unnecessary JOINs, SELECT *)
  - Network latency
  - Large responses

Q: What do we LOSE by switching to raw SQL?
A: A lot:
  - SQL injection protection (ORM parameterizes automatically)
  - Type safety and IDE autocomplete
  - Relationship loading (joinedload, subqueryload)
  - Database portability (PostgreSQL → MySQL)
  - Migration tracking (Alembic knows about models)
  - Result as objects vs tuples (user.name vs user[1])

Q: Is there a security risk?
A: Yes! The raw SQL example uses string formatting. If someone later adds a filter:
  `f"WHERE active = true AND name = '{user_input}'"` → SQL injection.
  ORM queries are parameterized by default.

Q: Have we measured the ORM overhead?
A: "ORMs are slow" is a meme, not a measurement. Has anyone profiled the app and identified ORM query building as the bottleneck? Almost certainly not.

Q: When IS raw SQL justified?
A: Complex aggregations, window functions, CTEs, database-specific features that ORM can't express. NOT for simple CRUD queries.
</think>

**This is premature optimization that makes your code worse.** The ORM overhead on simple queries is 1-5ms — invisible to users.

**What you're actually gaining:**
```
ORM query build time:  ~3ms
DB execution time:    ~20ms
Total with ORM:       ~23ms
Total with raw SQL:   ~20ms

User perception difference: zero
```

**What you're losing:**

| Feature | ORM | Raw SQL |
|---------|-----|---------|
| SQL injection protection | Automatic | Manual (dangerous) |
| IDE autocomplete | Yes | No |
| Type-safe results | `user.name` | `user[1]` (what's index 1?) |
| Relationship loading | `joinedload()` | Manual JOINs |
| Database portability | Yes | No |
| Alembic migrations | Knows models | Out of sync |

**The real performance fixes (that actually matter):**

```python
# Fix N+1 queries (saves SECONDS, not milliseconds):
users = User.query.options(joinedload(User.orders)).all()

# Add missing indexes (saves seconds):
# CREATE INDEX idx_users_active_created ON users(active, created_at DESC);

# Select only needed columns (reduces memory):
users = db.session.query(User.id, User.name).filter_by(active=True).all()
```

**When raw SQL IS justified:**
```python
# Complex analytics query that ORM can't express well:
result = db.engine.execute(text("""
    WITH monthly AS (
        SELECT date_trunc('month', created_at) AS month,
               COUNT(*) as signups,
               LAG(COUNT(*)) OVER (ORDER BY date_trunc('month', created_at)) as prev
        FROM users
        GROUP BY 1
    )
    SELECT month, signups,
           ROUND((signups - prev)::numeric / prev * 100, 1) as growth_pct
    FROM monthly
"""))
```

**Rule**: Profile first, optimize the actual bottleneck (usually N+1 queries or missing indexes), keep ORM for CRUD.'''
    ),
    (
        "thinking/meta-socratic-not-considering-concurrency",
        r'''I built a simple counter API for tracking page views:

```python
from flask import Flask

app = Flask(__name__)
page_views = {}

@app.route('/track/<page>')
def track(page):
    if page not in page_views:
        page_views[page] = 0
    page_views[page] += 1
    return {'page': page, 'views': page_views[page]}

@app.route('/stats/<page>')
def stats(page):
    return {'page': page, 'views': page_views.get(page, 0)}
```

Works great in development. Good to go?''',
        r'''<think>
My initial approach: Simple dict counter, increment on each request.

Q: What am I not considering? Let me check for blind spots.

Q: What happens with concurrent requests?
A: `page_views[page] += 1` is NOT atomic. With multiple threads (or gunicorn workers):
  Thread A reads page_views["home"] = 100
  Thread B reads page_views["home"] = 100
  Thread A writes page_views["home"] = 101
  Thread B writes page_views["home"] = 101
  Lost update! Should be 102.

Q: Does Flask use threads?
A: The development server is single-threaded. But production (gunicorn, uwsgi) uses multiple workers — each with SEPARATE memory. The page_views dict isn't shared between workers at all!

Q: So with 4 gunicorn workers, what happens?
A: Each worker has its own page_views dict. Worker 1 says 50 views, Worker 2 says 48 views, Worker 3 says 52 views. The numbers are meaningless. And requests are load-balanced randomly.

Q: What happens when the app restarts?
A: page_views = {} — all counts are lost. Deploy = reset all analytics.

Q: What about memory?
A: Every unique page path goes into the dict. An attacker can hit /track/random123, /track/random456, etc. — unbounded memory growth.

Q: Does this scale?
A: No. In-memory state doesn't work for stateless web apps.

Multiple fundamental issues, all invisible in single-process development.
</think>

**This fails completely in production.** Multiple critical issues:

**Issue 1: Data lost between workers**
```
gunicorn -w 4 app:app  # 4 workers, 4 separate page_views dicts

Request 1 → Worker A: {"home": 1}
Request 2 → Worker B: {"home": 1}  # Doesn't see Worker A's count
Request 3 → Worker A: {"home": 2}
GET /stats  → Worker C: {"home": 0}  # Never saw any requests!
```

**Issue 2: Data lost on restart**
Every deploy, restart, or crash resets all counts to zero.

**Issue 3: Race conditions**
Even with threads, `dict[key] += 1` is not atomic.

**Issue 4: Unbounded memory**
Attackers can create infinite unique pages: `/track/abc123`, `/track/def456`...

**Fix — use Redis (the right tool):**

```python
from flask import Flask
import redis

app = Flask(__name__)
r = redis.Redis()

@app.route('/track/<page>')
def track(page):
    # INCR is atomic — no race conditions
    # Shared across all workers
    # Survives restarts
    views = r.incr(f'pageviews:{page}')
    return {'page': page, 'views': views}

@app.route('/stats/<page>')
def stats(page):
    views = r.get(f'pageviews:{page}')
    return {'page': page, 'views': int(views or 0)}
```

**Why Redis fixes everything:**

| Problem | In-memory dict | Redis |
|---------|---------------|-------|
| Multi-worker | Separate copies | Shared |
| Restarts | Data lost | Persistent |
| Race conditions | Lost updates | Atomic INCR |
| Memory growth | Unbounded in app | Managed by Redis |

**For high-traffic analytics**, consider batching writes or using a proper analytics service instead of per-request Redis calls.'''
    ),
    (
        "thinking/meta-socratic-overengineering-validation",
        r'''I'm writing input validation for a REST API. I want to create a generic validation framework with:
- A DSL for defining validation rules
- Composable validators with AND/OR logic
- Custom error message templates with i18n
- Validation middleware that auto-validates all endpoints
- A schema registry for version management

The API has 5 endpoints. Is this a good approach?''',
        r'''<think>
My initial approach: A validation framework sounds thorough...

Q: Am I over-engineering this? 5 endpoints.
A: Five. Endpoints. For 5 endpoints, a custom validation framework with a DSL, registry, and i18n is like building a CMS to write a shopping list.

Q: What's the simplest validation that works?
A: Pydantic. Define 5 models. Done.

```python
class CreateUser(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    age: int = Field(ge=0, le=150)
```

That IS the validation. No framework, no DSL, no registry.

Q: How long would the custom framework take to build?
A: DSL + composable validators + i18n + middleware + registry = probably 2-4 weeks of work. For 5 endpoints that could be validated in 1 hour with Pydantic.

Q: Will the framework actually be better than Pydantic?
A: No. Pydantic is maintained by a team, has hundreds of contributors, handles edge cases tested by millions of users. A custom framework will have bugs.

Q: But what if the API grows to 50 endpoints?
A: Pydantic still handles 50 endpoints. And 500. It's used by FastAPI which serves APIs with thousands of endpoints. There's no scale where Pydantic stops working.

Q: What about i18n for error messages?
A: Only add i18n when you have users who speak multiple languages AND those users see raw validation error messages. For a 5-endpoint API, this is YAGNI.

Q: What would the next maintainer think?
A: They'd see a custom validation DSL and think "why didn't they just use Pydantic?" Then they'd have to learn the custom DSL instead of using industry-standard tooling.

This is a severe case of over-engineering.
</think>

**Massively over-engineered.** You're building a validation framework for 5 endpoints. Use Pydantic — it does everything you described, already exists, and works in 10 minutes.

**What you need (15 minutes of work):**

```python
from pydantic import BaseModel, EmailStr, Field

class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    age: int = Field(ge=0, le=150)

class UpdateTaskRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    status: Literal["todo", "in_progress", "done"] | None = None
    priority: int | None = Field(None, ge=1, le=5)

# In your endpoint:
@app.route('/users', methods=['POST'])
def create_user():
    try:
        data = CreateUserRequest(**request.json)
    except ValidationError as e:
        return {'errors': e.errors()}, 422
    # data is validated and typed
```

**Your proposed framework vs Pydantic:**

| Feature | Your framework | Pydantic |
|---------|---------------|----------|
| Build time | 2-4 weeks | Already exists |
| Composable rules | Custom DSL | Field() + validators |
| Error messages | Custom i18n | Automatic, customizable |
| Schema generation | Custom registry | JSON Schema built-in |
| API framework support | DIY | FastAPI native |
| Bugs | Many (new code) | Battle-tested |
| Learning curve | Custom (only you know it) | Industry standard |

**If using FastAPI, validation is literally free:**
```python
@app.post("/users")
def create_user(user: CreateUserRequest):
    # Already validated, typed, and documented
    return {"id": save_user(user)}
```

5 Pydantic models for 5 endpoints. Ship it today, not in a month.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
