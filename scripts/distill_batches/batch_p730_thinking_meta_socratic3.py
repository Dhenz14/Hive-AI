"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 3)

Scenarios: "Is this premature optimization?", "Am I over-engineering this?",
"What would the next maintainer think?"
"""

PAIRS = [
    (
        "thinking/meta-socratic-premature-optimization-db",
        r'''I'm building a blog with Flask and PostgreSQL. I'm planning to use read replicas, connection pooling with PgBouncer, query caching with Redis, and materialized views for the post listing page. The blog will have about 100 posts. Should I set all this up before launch?''',
        r'''<think>
My initial approach: These are all legitimate performance techniques for PostgreSQL.

Q: Is this premature optimization? Let's check the numbers.
A: 100 blog posts. ONE HUNDRED. Let me think about what PostgreSQL can handle:
  - PostgreSQL can serve a simple SELECT on 100 rows in under 1ms
  - A single PostgreSQL instance can handle thousands of queries per second
  - 100 blog posts with full-text search would be instant
  - Even without any indexing, a sequential scan of 100 rows is negligible

Q: What traffic would justify this infrastructure?
A: Read replicas: needed at 10,000+ queries/second. A blog with 100 posts probably gets... 10 requests/minute?
Connection pooling: needed when you have hundreds of concurrent connections. A blog has maybe 5.
Redis caching: needed when DB queries are slow or frequent. Neither applies here.
Materialized views: needed when aggregation queries are expensive. Listing 100 posts is not expensive.

Q: What's the actual cost of this infrastructure?
A:
  - Read replicas: Extra database instance to manage, replication lag, read-after-write consistency issues
  - PgBouncer: Another service to deploy, configure, monitor, debug connection issues
  - Redis: Cache invalidation logic, another service, stale data bugs
  - Materialized views: Refresh scheduling, stale data until refreshed

Q: Am I solving a problem that doesn't exist?
A: Yes. This is textbook premature optimization. The blog could run on SQLite and be fast. PostgreSQL alone is massive overkill for 100 posts, let alone read replicas and caching layers.

Q: What should they focus on instead?
A: Writing good content, getting users, making the site look good. Performance optimization should happen when there's a measured performance problem, not before launch.
</think>

**This is extreme premature optimization.** For 100 blog posts, a basic PostgreSQL setup will handle thousands of requests per second with no additional infrastructure.

**Reality check:**

| Technology | When it's needed | Your blog |
|-----------|-----------------|-----------|
| Read replicas | 10,000+ queries/sec | ~10 queries/min |
| PgBouncer | 100+ concurrent connections | ~5 concurrent |
| Redis caching | Slow or frequent queries | <1ms query time |
| Materialized views | Expensive aggregations | SELECT on 100 rows |

**What your blog actually needs:**

```python
@app.route('/posts')
def list_posts():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('posts.html', posts=posts)
```

That's it. This query on 100 rows takes <1ms. No caching needed. No read replicas. No PgBouncer.

**What to do instead before launch:**
1. Add a basic index on `created_at` (though 100 rows doesn't even need it)
2. Focus on content, design, and SEO
3. Set up basic monitoring (so you KNOW if there's a problem later)

**When to add each optimization:**
- **Connection pooling**: When you see "too many connections" errors
- **Query caching**: When a specific query is slow AND called frequently
- **Read replicas**: When your single DB can't handle the read load
- **Materialized views**: When aggregation queries take >1 second

**Measure first, optimize second.** You might run this blog for years and never need any of these.'''
    ),
    (
        "thinking/meta-socratic-overengineering-config",
        r'''I'm building a Python CLI tool that reads a config file. I want to support JSON, YAML, TOML, INI, and environment variables as config sources, with a priority system, schema validation, hot-reloading, and encrypted secrets. The tool is an internal deployment script used by our team of 3 developers. Should I build this config system?''',
        r'''<think>
My initial approach: A flexible config system supporting multiple formats sounds useful.

Q: Am I over-engineering this? Let's evaluate against the actual requirements.
A: Internal tool, 3 developers, deployment script. This is a script that runs once, does its job, and exits. It doesn't need:
  - Hot-reloading (runs once, doesn't stay running)
  - 5 config formats (team can agree on ONE)
  - Encrypted secrets (use environment variables or a vault)
  - Schema validation (3 developers can read the README)

Q: What's the simplest thing that works?
A: A single TOML or YAML file with os.environ fallback. Maybe 20 lines of code total.

Q: What would the next maintainer think of a custom config system?
A: They'd have to understand the priority system, the schema validation, the encryption layer — all for a deployment script. They'd think "why didn't they just use a config file?"

Q: How long would the config system take to build vs the actual deployment logic?
A: The config system as described (5 formats, priority, schema, hot-reload, encryption) is probably MORE code than the deployment script itself. The meta-tooling shouldn't exceed the actual tool.

Q: What problem is each feature actually solving?
A:
  - Multiple formats: "Flexibility" — but who's asking for it? Just pick one.
  - Priority system: Useful for env var overrides — but os.environ.get(key, default) does this.
  - Schema validation: Useful for large teams with complex config — overkill for 3 devs.
  - Hot-reloading: Only for long-running services — a deploy script isn't one.
  - Encrypted secrets: Use environment variables or a secrets manager — don't build your own.

This is a classic case of building framework-level infrastructure for a script-level problem.
</think>

**Massively over-engineered.** You're building a configuration framework for a deployment script used by 3 people.

**What you actually need:**

```python
import tomllib
import os
from pathlib import Path

def load_config():
    config_path = Path("deploy.toml")
    config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}

    # Env vars override file config
    return {
        "target": os.environ.get("DEPLOY_TARGET", config.get("target", "staging")),
        "version": os.environ.get("DEPLOY_VERSION", config.get("version")),
        "notify": config.get("notify", True),
    }
```

```toml
# deploy.toml
target = "staging"
notify = true
```

**That's it. 15 lines.** Handles file config + env var overrides.

**Why each proposed feature is unnecessary:**

| Feature | Why you don't need it |
|---------|----------------------|
| 5 config formats | Pick one. Your team of 3 can agree on TOML |
| Priority system | `os.environ.get(key, file_value)` — done |
| Schema validation | 3 devs can read a 5-line config file |
| Hot-reloading | Script runs once and exits |
| Encrypted secrets | Use `$DEPLOY_TOKEN` env var or a vault |

**Rule of thumb**: If the config system has more code than the tool it configures, you've over-engineered it.

**If you later need more:**
- Schema validation: Add Pydantic model (10 lines)
- Multiple environments: `deploy.staging.toml`, `deploy.production.toml`
- Secrets: `export DEPLOY_TOKEN=...` in your shell profile'''
    ),
    (
        "thinking/meta-socratic-next-maintainer-clever-code",
        r'''I wrote this Python function and I'm quite proud of it. It processes a list of orders and calculates total revenue by category:

```python
def revenue_by_category(orders):
    return {
        k: sum(v)
        for k, v in __import__('itertools').groupby(
            sorted(
                ((o['category'], o['price'] * o['quantity']) for o in orders),
                key=lambda x: x[0]
            ),
            key=lambda x: x[0]
        )
        for k, v in [(k, [i[1] for i in v])]
    }
```

Is this good code?''',
        r'''<think>
My initial approach: Let me parse what this does... it's a dict comprehension with nested generator, sorted, groupby, and a list comprehension inside.

Q: What would the next maintainer think of this?
A: They would:
  1. Spend 5 minutes trying to understand what it does
  2. Be afraid to modify it (might break the clever logic)
  3. Not be sure if it's correct (hard to verify visually)
  4. Probably rewrite it anyway

Q: Is this actually correct?
A: Let me trace through it... Actually, this has a bug. The nested `for k, v in [(k, [i[1] for i in v])]` is using a weird pattern to rebind k and v inside the dict comprehension. And itertools.groupby requires the input to be sorted by the key — which it is here, but that's not immediately obvious.

Wait, there's another issue: `__import__('itertools')` inside a dict comprehension? That's called on every invocation. It should be a top-level import.

Q: Is there a simpler way to achieve this?
A: Yes, collections.defaultdict does this clearly:

```python
from collections import defaultdict
totals = defaultdict(float)
for order in orders:
    totals[order['category']] += order['price'] * order['quantity']
return dict(totals)
```

Three lines, immediately understandable, same result.

Q: Is the clever version faster?
A: No. The sorted() is O(n log n). The defaultdict version is O(n). The clever version is slower AND harder to read.

Q: What would a code reviewer flag?
A: Everything. __import__ in a comprehension, unnecessary sorting, single-expression-at-all-costs mentality, no variable names that explain intent.

This is a case where "clever" actively harms the codebase.
</think>

**No, this is bad code.** It's clever but harmful. The next developer (including future-you) will struggle to understand, verify, or modify it.

**Problems:**
1. **`__import__('itertools')` in a comprehension** — should be a top-level import
2. **O(n log n)** due to unnecessary sorting — defaultdict is O(n)
3. **Nested comprehension with rebinding** — the `for k, v in [(k, ...)]` trick is obscure
4. **Unreadable** — takes minutes to parse what should be instantly clear
5. **Fragile** — modifying this without breaking it requires deep understanding

**The clear version (same result, faster, 3 lines):**

```python
from collections import defaultdict

def revenue_by_category(orders):
    totals = defaultdict(float)
    for order in orders:
        totals[order['category']] += order['price'] * order['quantity']
    return dict(totals)
```

**Or with Counter (if you prefer functional style):**

```python
from collections import Counter

def revenue_by_category(orders):
    revenue = Counter()
    for o in orders:
        revenue[o['category']] += o['price'] * o['quantity']
    return dict(revenue)
```

**Why the simple version wins:**
- **Readable**: Anyone understands it in 5 seconds
- **Faster**: O(n) vs O(n log n) — no sorting needed
- **Modifiable**: Want to add a filter? Add an `if` in the loop
- **Debuggable**: Can add print/breakpoint inside the loop

**Rule**: Code is read 10x more often than written. Optimize for the reader, not for showing off.'''
    ),
    (
        "thinking/meta-socratic-testing-what-matters",
        r'''I wrote tests for my user registration endpoint. Are these good tests?

```python
def test_register_user(client):
    response = client.post('/register', json={
        'username': 'alice',
        'email': 'alice@example.com',
        'password': 'password123'
    })
    assert response.status_code == 201

def test_register_returns_json(client):
    response = client.post('/register', json={
        'username': 'bob',
        'email': 'bob@example.com',
        'password': 'password123'
    })
    assert response.content_type == 'application/json'

def test_register_has_id(client):
    response = client.post('/register', json={
        'username': 'carol',
        'email': 'carol@example.com',
        'password': 'password123'
    })
    assert 'id' in response.json
```''',
        r'''<think>
My initial approach: Three tests that cover the happy path — status code, content type, response body.

Q: Am I testing what matters or what's easy to test?
A: These tests only verify the happy path. Registration has critical behavior that isn't tested:
  - What happens with a duplicate email? (most common real-world issue)
  - What happens with an empty password?
  - What happens with an invalid email?
  - Is the password hashed before storage? (security-critical)
  - Is a confirmation email sent?
  - Does it prevent SQL injection in the username?

Q: Are these three tests really three distinct tests?
A: Not really. They all make the same request with the same data and check different aspects of the same response. This could be ONE test with three assertions. Splitting them doesn't add value — it adds 3x the setup time.

Q: What would actually break in production that these tests wouldn't catch?
A:
  - Duplicate email registration → 500 error (not tested)
  - Password stored in plaintext → data breach (not tested)
  - Missing validation → garbage data in DB (not tested)
  - Registration during DB downtime → unhandled error (not tested)

Q: What's the highest-value test I could write?
A: Testing that duplicate emails are rejected, passwords are hashed, and invalid input returns proper errors. These are the scenarios that actually cause production incidents.

These tests provide false confidence — they pass but don't verify anything important.
</think>

**These tests only cover the easy happy path and miss everything that actually breaks in production.**

**What's tested:** Successful registration returns 201 with JSON containing an ID.
**What's NOT tested:** Everything that actually causes production bugs.

**High-value tests you're missing:**

```python
def test_register_success(client):
    """Happy path — combine your three tests into one."""
    response = client.post('/register', json={
        'username': 'alice',
        'email': 'alice@example.com',
        'password': 'SecureP@ss123'
    })
    assert response.status_code == 201
    assert 'id' in response.json
    assert 'password' not in response.json  # Never expose password

def test_register_duplicate_email_rejected(client):
    """Most common real-world registration bug."""
    client.post('/register', json={
        'username': 'alice', 'email': 'alice@example.com', 'password': 'Pass123!'
    })
    response = client.post('/register', json={
        'username': 'alice2', 'email': 'alice@example.com', 'password': 'Pass456!'
    })
    assert response.status_code == 409  # Conflict

def test_register_password_is_hashed(client, db_session):
    """Security-critical: passwords must never be stored in plaintext."""
    client.post('/register', json={
        'username': 'alice', 'email': 'alice@example.com', 'password': 'MyPassword'
    })
    user = db_session.query(User).filter_by(email='alice@example.com').first()
    assert user.password != 'MyPassword'  # Must be hashed

def test_register_invalid_email_rejected(client):
    response = client.post('/register', json={
        'username': 'alice', 'email': 'not-an-email', 'password': 'Pass123!'
    })
    assert response.status_code == 422

def test_register_empty_password_rejected(client):
    response = client.post('/register', json={
        'username': 'alice', 'email': 'alice@example.com', 'password': ''
    })
    assert response.status_code == 422

def test_register_missing_fields(client):
    response = client.post('/register', json={'username': 'alice'})
    assert response.status_code == 422
```

**Testing priority for registration:**
1. Duplicate prevention (most common bug)
2. Password hashing (security-critical)
3. Input validation (data integrity)
4. Happy path (basic sanity)
5. Edge cases (unicode names, long inputs)

Test what breaks, not what works.'''
    ),
    (
        "thinking/meta-socratic-silent-failure-background",
        r'''Here's my background job processor for sending emails:

```python
import threading
import queue

email_queue = queue.Queue()

def email_worker():
    while True:
        task = email_queue.get()
        try:
            send_email(task['to'], task['subject'], task['body'])
        except Exception:
            pass
        email_queue.task_done()

# Start worker thread
threading.Thread(target=email_worker, daemon=True).start()

def queue_email(to, subject, body):
    email_queue.put({'to': to, 'subject': subject, 'body': body})
```

This works in development. Any concerns?''',
        r'''<think>
My initial approach: Simple queue + worker thread pattern for async email sending.

Q: Could this fail silently?
A: YES. The `except Exception: pass` swallows ALL errors. If the email server is down, SMTP credentials are wrong, or the email address is invalid — the error disappears completely. No logging, no retry, no notification. Emails silently vanish.

Q: How would you even know emails are failing?
A: You wouldn't. Users would complain "I never got the email" and you'd have no logs to investigate. This is the worst kind of bug — invisible.

Q: What happens when the app restarts?
A: daemon=True means the thread dies when the main process exits. Any emails in the queue are LOST. No persistence, no recovery.

Q: What happens if send_email hangs?
A: The worker thread blocks forever on one email. All subsequent emails queue up but never send. Single worker = single point of failure.

Q: Is queue.Queue bounded?
A: No, it's unbounded. If emails fail (silently) and new ones keep queuing, memory grows unbounded. Eventually OOM.

Q: What about the email content — is it safe?
A: The task dict has 'to', 'subject', 'body' but no validation. What if 'to' is None? What if 'body' contains unescaped HTML?

Q: What would happen under load?
A: Single worker thread processes one email at a time. 1000 users register simultaneously? The last user gets their welcome email hours later.

This code has at least 6 silent failure modes. It "works" in dev because dev sends 2 emails and the SMTP server is always up.
</think>

**This has multiple silent failure modes.** It "works" in dev but will lose emails in production with no way to know.

**Critical issues:**

1. **`except Exception: pass`** — emails silently vanish on any error
2. **Daemon thread** — queued emails lost on app restart
3. **No retry** — transient SMTP errors permanently lose the email
4. **Single worker** — one hanging email blocks all subsequent emails
5. **Unbounded queue** — memory grows if emails can't be sent
6. **No monitoring** — no way to know emails are failing

**Minimum viable fix:**

```python
import threading
import queue
import logging
import time

logger = logging.getLogger(__name__)
email_queue = queue.Queue(maxsize=1000)  # Bounded queue

def email_worker():
    while True:
        task = email_queue.get()
        for attempt in range(3):  # Retry up to 3 times
            try:
                send_email(task['to'], task['subject'], task['body'])
                logger.info(f"Email sent to {task['to']}")
                break
            except Exception as e:
                logger.error(f"Email failed (attempt {attempt+1}): {task['to']}: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)  # Exponential backoff
        else:
            logger.critical(f"Email permanently failed: {task['to']}")
            # TODO: save to dead letter table for manual retry
        email_queue.task_done()

threading.Thread(target=email_worker, daemon=True).start()
```

**For production, use a proper task queue instead:**

```python
# Celery — handles retry, persistence, monitoring
@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, to, subject, body):
    try:
        send_email(to, subject, body)
    except Exception as e:
        self.retry(exc=e)
```

**Why Celery/RQ over DIY:**
- Persistent queue (survives restarts)
- Automatic retries with backoff
- Dead letter queue for permanently failed tasks
- Monitoring dashboard (Flower)
- Multiple workers for throughput

**Rule**: If losing a task silently is unacceptable, don't use in-memory queues with `except: pass`.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
