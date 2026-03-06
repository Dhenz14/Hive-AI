"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 7)

Scenarios: Additional coverage for remaining 3C scenarios —
"Am I anchored on my first idea?", "What would a code reviewer flag?",
"Could this fail silently?" (more), "Am I introducing tight coupling?" (more)
"""

PAIRS = [
    (
        "thinking/meta-socratic-anchored-nosql",
        r'''I'm building a social media app with user profiles, posts, comments, likes, and follower relationships. I want to use MongoDB because "social data is unstructured." Is MongoDB the right choice?''',
        r'''<think>
My initial approach: Social media data, MongoDB...

Q: Am I anchored on "social data is unstructured"? Is that actually true?
A: Let me examine each entity:
  - Users: name, email, bio, joined_date — structured
  - Posts: author, content, timestamp, tags — structured
  - Comments: author, post_id, content, timestamp — structured
  - Likes: user_id, post_id, timestamp — structured
  - Followers: follower_id, following_id — structured

This data is actually HIGHLY structured with clear relationships. "Social" doesn't mean "unstructured."

Q: What queries does a social media app need?
A:
  - "Show me posts from people I follow" → follower JOIN posts, ordered by time
  - "Show all comments on this post" → comments WHERE post_id = X
  - "How many likes does this post have?" → COUNT likes WHERE post_id = X
  - "Who likes this post?" → likes JOIN users WHERE post_id = X
  - "Mutual friends" → followers INTERSECT followers

These are ALL relational queries. JOINs, aggregations, counting.

Q: How would MongoDB handle "posts from people I follow"?
A: Either:
  1. Denormalize: embed followers in user document → updating is a nightmare
  2. Application-level join: fetch follower IDs, then fetch posts for each → N+1 problem
  3. $lookup: MongoDB's JOIN equivalent → slower than SQL JOIN

Q: When IS MongoDB good?
A: When data is genuinely schema-less (CMS with varying content types), deeply nested (JSON documents), or write-heavy with simple reads.

Q: What do successful social media platforms use?
A: Twitter: MySQL (later Manhattan). Facebook: MySQL. Instagram: PostgreSQL. Reddit: PostgreSQL. They all chose relational databases for social data.

The "social = NoSQL" meme is misleading. Social data is highly relational.
</think>

**MongoDB is the wrong choice.** Social media data is highly relational, not unstructured.

**Your data IS structured:**
```
Users ←→ Posts (one-to-many)
Posts ←→ Comments (one-to-many)
Users ←→ Likes ←→ Posts (many-to-many)
Users ←→ Followers ←→ Users (many-to-many, self-referential)
```

**Core social queries need JOINs:**
```sql
-- "Posts from people I follow" — the #1 social media query
SELECT p.* FROM posts p
JOIN followers f ON p.author_id = f.following_id
WHERE f.follower_id = :current_user
ORDER BY p.created_at DESC
LIMIT 20;

-- "Mutual friends" — requires self-join
SELECT f1.following_id FROM followers f1
JOIN followers f2 ON f1.following_id = f2.follower_id
WHERE f1.follower_id = :user_a AND f2.following_id = :user_a;
```

**In MongoDB, the same "timeline" query:**
```javascript
// Step 1: Get who I follow
const following = await db.followers.find({follower: userId}).toArray();
const followingIds = following.map(f => f.following);

// Step 2: Get their posts (application-level "JOIN")
const posts = await db.posts.find({author: {$in: followingIds}})
    .sort({created_at: -1}).limit(20).toArray();

// Two queries, followingIds could be thousands of IDs
```

**Use PostgreSQL.** Successful social platforms agree:
- Twitter: MySQL
- Instagram: PostgreSQL
- Reddit: PostgreSQL
- Facebook: MySQL
- LinkedIn: Oracle → moved to Espresso (custom, but relational)

**When MongoDB IS right:**
- Content with varying schemas (CMS, product catalogs with different attributes)
- IoT event streams (write-heavy, simple reads)
- Caching/session storage
- Document storage (literally documents)'''
    ),
    (
        "thinking/meta-socratic-code-review-env-handling",
        r'''Here's how I handle different environments in my Python app:

```python
import os

ENV = os.environ.get('ENV', 'development')

if ENV == 'production':
    DATABASE_URL = 'postgresql://prod_user:prod_pass@prod-db:5432/myapp'
    REDIS_URL = 'redis://prod-redis:6379'
    SECRET_KEY = 'super-secret-production-key-123'
    DEBUG = False
elif ENV == 'staging':
    DATABASE_URL = 'postgresql://staging_user:staging_pass@staging-db:5432/myapp'
    REDIS_URL = 'redis://staging-redis:6379'
    SECRET_KEY = 'staging-secret-key-456'
    DEBUG = True
else:
    DATABASE_URL = 'sqlite:///dev.db'
    REDIS_URL = 'redis://localhost:6379'
    SECRET_KEY = 'dev-secret'
    DEBUG = True
```

Simple and clear, right?''',
        r'''<think>
My initial approach: Environment-based config with if/elif/else.

Q: What would a code reviewer flag here?

Q: Are those production credentials in the source code?!
A: YES. `prod_user:prod_pass` and `super-secret-production-key-123` are hardcoded in a file that gets committed to git. Anyone with repo access sees production database credentials. This is a critical security vulnerability.

Q: What if the repo is compromised or leaked?
A: Attacker gets production database credentials, Redis access, and the ability to forge sessions (SECRET_KEY). Game over.

Q: What if a developer accidentally runs with ENV=production locally?
A: They connect directly to the production database. One wrong query and production data is corrupted.

Q: Is DEBUG = True in staging safe?
A: Staging often has production-like data. Debug mode in staging still exposes the interactive debugger.

Q: What about when credentials need to rotate?
A: Every password change requires a code change, PR review, and deployment. Credentials should be managed separately from code.

Q: What would a code reviewer say?
A: "STOP. Do not merge this. Credentials must never be in source code. Use environment variables or a secrets manager."
</think>

**A code reviewer would reject this immediately.** Production credentials are hardcoded in source code.

**Critical issues:**

1. **Production passwords in source code** — anyone with repo access gets your database
2. **SECRET_KEY in source code** — anyone can forge sessions
3. **Committed to git** — credentials in git history FOREVER (even if you delete them later)
4. **Staging DEBUG = True** — exposes debugger on staging

**Fix — use environment variables:**

```python
import os

# All secrets come from environment, never from code
DATABASE_URL = os.environ['DATABASE_URL']
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
SECRET_KEY = os.environ['SECRET_KEY']
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
```

```bash
# .env (gitignored — NEVER committed)
DATABASE_URL=sqlite:///dev.db
SECRET_KEY=dev-only-key-not-secret
DEBUG=true
```

```bash
# Production: set in deployment platform (Heroku, AWS, systemd)
export DATABASE_URL=postgresql://user:pass@db:5432/myapp
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export DEBUG=false
```

**Your `.gitignore` must include:**
```
.env
*.env
.env.*
```

**If credentials were already committed:**
```bash
# They're in git history FOREVER. You must:
# 1. Rotate ALL credentials immediately
# 2. Consider using git-filter-repo to remove from history
# 3. Never commit credentials again
```

**Rule**: Code tells the app WHAT config it needs. Environment tells it the VALUES. Never mix the two.'''
    ),
    (
        "thinking/meta-socratic-silent-failure-webhook",
        r'''I built a webhook handler for Stripe payment events:

```python
@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    event = request.get_json()

    if event['type'] == 'payment_intent.succeeded':
        order_id = event['data']['object']['metadata']['order_id']
        order = Order.query.get(order_id)
        order.status = 'paid'
        db.session.commit()

    return '', 200
```

Straightforward webhook handler. Any issues?''',
        r'''<think>
My initial approach: Receives Stripe event, updates order status.

Q: Could this fail silently?

Q: Is the webhook verified?
A: NO. Anyone can POST fake JSON to this endpoint pretending to be Stripe. An attacker could send `{"type": "payment_intent.succeeded", "data": {"object": {"metadata": {"order_id": 123}}}}` and mark any order as "paid" without paying. This is a critical security vulnerability.

Q: What if the order doesn't exist?
A: `Order.query.get(order_id)` returns None. Then `None.status = 'paid'` raises AttributeError → 500 response → Stripe retries → infinite retry loop.

Q: What if the event is a duplicate?
A: Stripe can send the same event multiple times (at-least-once delivery). The code processes it every time. For this simple case it's idempotent (setting paid to paid), but for other operations (like sending a notification), duplicates would be a problem.

Q: What about other event types?
A: The handler silently ignores all events except `payment_intent.succeeded`. What about `payment_intent.payment_failed`? `charge.refunded`? `charge.dispute.created`? These are ignored with a 200 OK, which tells Stripe everything is fine.

Q: What if the metadata doesn't have order_id?
A: `event['data']['object']['metadata']['order_id']` — if any of these keys are missing, KeyError → 500 → Stripe retries forever.

Q: What if the database is temporarily down?
A: db.session.commit() fails → 500 → Stripe retries (good), but no logging of the failure.

Q: Always returning 200 — is that right?
A: For unhandled event types, yes (Stripe recommends 200 for events you don't process). But for handled events that FAIL, returning 200 tells Stripe "all good" when it's not.

Multiple critical issues, the most serious being no webhook signature verification.
</think>

**Critical security vulnerability: no webhook signature verification.** Anyone can fake payment events and mark orders as paid.

**Issue 1: No signature verification (critical)**
```python
# ANYONE can mark orders as "paid" by sending fake JSON
curl -X POST https://yourapp.com/webhook/stripe \
  -d '{"type":"payment_intent.succeeded","data":{"object":{"metadata":{"order_id":"123"}}}}'
```

**Issue 2: No error handling — crashes cause infinite retries**

**Issue 3: Ignores important event types silently**

**Fixed version:**

```python
import stripe

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    # VERIFY the webhook signature
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        logger.warning("Invalid webhook signature")
        return '', 400

    # Handle events with proper error handling
    try:
        if event['type'] == 'payment_intent.succeeded':
            handle_payment_success(event)
        elif event['type'] == 'payment_intent.payment_failed':
            handle_payment_failure(event)
        elif event['type'] == 'charge.refunded':
            handle_refund(event)
        else:
            logger.info(f"Unhandled event type: {event['type']}")
    except Exception as e:
        logger.exception(f"Webhook processing failed: {event['type']}")
        return '', 500  # Tell Stripe to retry

    return '', 200

def handle_payment_success(event):
    order_id = event['data']['object']['metadata'].get('order_id')
    if not order_id:
        logger.error("Payment event missing order_id metadata")
        return

    order = Order.query.get(order_id)
    if not order:
        logger.error(f"Order {order_id} not found for payment event")
        return

    if order.status == 'paid':  # Idempotency check
        logger.info(f"Order {order_id} already paid, skipping duplicate")
        return

    order.status = 'paid'
    order.paid_at = datetime.utcnow()
    db.session.commit()
    logger.info(f"Order {order_id} marked as paid")
```

**Key fixes:**
- **Signature verification** — rejects forged webhooks
- **Error handling** — returns 500 for Stripe to retry on failures
- **Idempotency** — handles duplicate events safely
- **Logging** — every decision is logged for debugging
- **Multiple event types** — handles failures and refunds too'''
    ),
    (
        "thinking/meta-socratic-simplest-solution-queue",
        r'''I need to process uploaded CSV files asynchronously. The user uploads a CSV, and we need to parse it and import the data. I'm thinking of setting up RabbitMQ with Celery workers, a dead letter queue for failed jobs, retry policies, and a monitoring dashboard. We get about 5 CSV uploads per day. Sound good?''',
        r'''<think>
My initial approach: Celery + RabbitMQ for async CSV processing...

Q: Is this the simplest solution? 5 uploads per DAY?
A: Five. Per. Day. That's one upload every ~5 hours. The processing infrastructure would be idle 99.9% of the time.

Q: What's the simplest async processing for 5/day?
A: A background thread. Or even simpler — just process it synchronously if it takes < 30 seconds.

Q: How long does parsing a CSV take?
A: Depends on size, but:
  - 1,000 rows: < 1 second
  - 10,000 rows: < 5 seconds
  - 100,000 rows: < 30 seconds

If the CSVs are under 100K rows, synchronous processing is fine — the user waits 5-30 seconds and sees the result immediately.

Q: What if the CSV is genuinely large (1M+ rows)?
A: A simple threading.Thread is sufficient:
  ```python
  thread = Thread(target=process_csv, args=(filepath,))
  thread.start()
  ```
  Return immediately, process in background.

Q: When does Celery + RabbitMQ become justified?
A: When you have:
  - Hundreds or thousands of jobs per hour
  - Multiple types of background tasks
  - Need for retry policies and dead letter queues
  - Multiple worker machines
  - Complex job dependencies (chains, groups)

For 5/day, this infrastructure costs more to maintain than it saves.

Q: What about reliability?
A: If a CSV import fails, the user re-uploads. At 5/day, the "dead letter queue" is an email notification saying "your import failed, please try again." Human-scale problems need human-scale solutions.
</think>

**Massively overkill for 5 uploads per day.** That's one upload every 5 hours. Celery + RabbitMQ would be idle 99.9% of the time.

**Level 1 — Synchronous (if CSV < 100K rows):**
```python
@app.route('/upload', methods=['POST'])
def upload_csv():
    file = request.files['csv']
    rows = parse_csv(file)
    imported = import_rows(rows)
    return {'imported': imported, 'status': 'complete'}
# User waits 5-30 seconds. Done.
```

**Level 2 — Background thread (if CSV is large):**
```python
import threading
import uuid

jobs = {}  # In production, use database

@app.route('/upload', methods=['POST'])
def upload_csv():
    file = request.files['csv']
    filepath = save_upload(file)
    job_id = str(uuid.uuid4())
    jobs[job_id] = 'processing'

    thread = threading.Thread(target=process_csv, args=(job_id, filepath))
    thread.start()
    return {'job_id': job_id, 'status': 'processing'}, 202

@app.route('/jobs/<job_id>')
def job_status(job_id):
    return {'status': jobs.get(job_id, 'unknown')}

def process_csv(job_id, filepath):
    try:
        import_csv(filepath)
        jobs[job_id] = 'complete'
    except Exception as e:
        jobs[job_id] = f'failed: {str(e)}'
        logger.exception(f"CSV import failed: {job_id}")
```

**When to upgrade to Celery:**
- Hundreds of jobs per hour
- Multiple job types with different priorities
- Need distributed workers across machines
- Complex retry policies (exponential backoff, max retries)
- Job result persistence and querying

**Your "dead letter queue" at 5/day:**
```python
except Exception as e:
    send_email_to_admin(f"CSV import failed: {e}")
    # Admin fixes it manually — that's fine at this volume
```

**Rule**: Match infrastructure complexity to actual load. 5/day ≠ enterprise job queue.'''
    ),
    (
        "thinking/meta-socratic-right-problem-memory-leak",
        r'''Our Python web app's memory usage keeps growing. After a few hours, it uses 4GB and the OOM killer restarts it. My colleague says we should increase the server RAM from 4GB to 16GB. Should we?''',
        r'''<think>
Q: Am I solving the right problem? Is the problem insufficient RAM or a memory leak?

Q: Does a healthy web app grow to 4GB?
A: No. A typical Flask/Django app with reasonable traffic should stabilize at a few hundred MB. Continuous growth = memory leak. Adding RAM just delays the OOM kill from hours to days.

Q: What are common causes of memory leaks in Python web apps?
A:
  1. Accumulating data in global/module-level collections (lists, dicts)
  2. Caching without eviction (unbounded cache)
  3. Database session/connection not closed properly
  4. Circular references preventing garbage collection
  5. Large objects held by debugger/profiler
  6. File handles not closed
  7. Event listeners registered repeatedly

Q: How do we diagnose the leak?
A:
  - tracemalloc: Python's built-in memory tracer
  - objgraph: Shows which objects are growing
  - memory_profiler: Line-by-line memory usage
  - Check for global collections that grow with each request

Q: Would 16GB actually fix it?
A: If the app leaks at ~1GB/hour:
  - 4GB RAM → OOM after ~4 hours
  - 16GB RAM → OOM after ~16 hours
  Still crashes, just later. The leak is still there.

Q: What's the right approach?
A: Find and fix the leak. The app should have stable memory usage regardless of how long it runs.

This is a classic case of "throw hardware at a software bug." It masks the problem, doesn't fix it.
</think>

**No.** Increasing RAM from 4GB to 16GB means the app crashes after 16 hours instead of 4. The leak is still there.

**Find the leak instead:**

```python
# Quick diagnosis — add to your app temporarily:
import tracemalloc
tracemalloc.start()

@app.route('/debug/memory')
def memory_stats():
    snapshot = tracemalloc.take_snapshot()
    top = snapshot.statistics('lineno')[:10]
    return {'top_allocations': [
        {'file': str(s.traceback), 'size_mb': s.size / 1024 / 1024}
        for s in top
    ]}
```

```python
# Or use objgraph to find growing objects:
import objgraph

@app.route('/debug/objects')
def object_stats():
    return {'growing': objgraph.show_growth(limit=10)}
```

**Most common Python web app memory leaks:**

| Leak pattern | How to detect |
|-------------|--------------|
| Global list/dict growing per request | `len(my_global_list)` grows over time |
| Unbounded cache | `sys.getsizeof(cache)` grows forever |
| DB sessions not closed | `db.session` count in connection pool |
| File handles not closed | `len(os.listdir('/proc/self/fd'))` (Linux) |
| Circular references | `gc.garbage` list grows |

**Example leak (very common):**
```python
# LEAK: global list grows with every request
request_log = []

@app.before_request
def log_request():
    request_log.append({  # Never cleared!
        'path': request.path,
        'time': datetime.now(),
        'data': request.get_data()  # Could be MB per request
    })
```

**Immediate mitigation (while finding the leak):**
```bash
# Restart workers periodically (gunicorn)
gunicorn --max-requests 1000 --max-requests-jitter 50 app:app
# Workers restart after ~1000 requests, preventing OOM
```

**The right answer is always: find and fix the leak.** Hardware can't fix software bugs.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
