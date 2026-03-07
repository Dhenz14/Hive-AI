"""
Real-world project help training pairs - Production debugging
"""

pairs = [
    {
        "instruction": r'''Our FastAPI app started returning 500 errors about 2 hours ago. It works fine locally. Logs show "sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) could not connect to server: Connection refused". But Postgres is running -- I can connect to it with psql from the server. What could be going on?''',
        "output": r'''<think>
Postgres is running and accessible via psql locally, but the app can't connect. This is almost always a connection pool exhaustion problem, not Postgres being down. Let me walk through the diagnosis.

Key clues:
- Started 2 hours ago (not a deploy, something accumulated)
- psql works (Postgres is accepting connections, just not from the app)
- "Connection refused" specifically
</think>

If psql works but the app can't connect, the most likely causes are:

1. Connection pool exhaustion (most common). Check active connections:

```sql
-- Run this in psql
SELECT count(*) FROM pg_stat_activity;
SELECT max_connections FROM pg_settings WHERE name = 'max_connections';

-- See what's holding connections
SELECT pid, state, query, query_start, now() - query_start AS duration
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC;
```

If active connections are near max_connections (default 100), that's your problem. Common causes:
- SQLAlchemy pool creating too many connections
- Long-running queries holding connections
- A code path that opens connections without closing them

Quick fix -- kill idle connections and increase the limit:

```sql
-- Kill connections idle for more than 5 minutes
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle' AND now() - state_change > interval '5 minutes';
```

2. Check your SQLAlchemy pool settings:

```python
# Check what you have now
engine = create_engine(
    DATABASE_URL,
    pool_size=5,          # default is 5
    max_overflow=10,      # default is 10
    pool_timeout=30,      # how long to wait for a connection
    pool_recycle=1800,    # recycle connections after 30 min
    pool_pre_ping=True,   # verify connections before using
)
```

`pool_pre_ping=True` is critical -- it tests connections before use, which prevents the app from using stale connections after a Postgres restart.

3. If it's not connection exhaustion, check if the app is connecting to the right host. In production, DATABASE_URL might point to a different host than localhost:

```bash
# Check what the app actually sees
echo $DATABASE_URL
# Compare with what psql uses
```

4. Check if a firewall rule changed or a security group was modified (common in cloud environments).

To prevent this in the future, add connection monitoring:

```python
from sqlalchemy import event

@event.listens_for(engine, "checkout")
def check_connection(dbapi_conn, connection_rec, connection_proxy):
    logging.info(f"Pool checkout. Pool size: {engine.pool.size()}, "
                 f"Checked out: {engine.pool.checkedout()}")
```

Start with #1 -- connection exhaustion explains 80% of "Postgres works but app can't connect" situations.'''
    },
    {
        "instruction": r'''We deployed a new feature yesterday and now users are reporting that the app is "sometimes slow" -- some requests take 30+ seconds while others are fine. Same endpoints, same users. The slow requests seem random. We're running 4 gunicorn workers behind nginx. Where do I look?''',
        "output": r'''Intermittent slowness with "random" affected requests usually means one worker is blocked and requests that land on it queue up.

Diagnostic steps, in order:

1. Check if one worker is stuck. Add request timing to your logs:

```python
# middleware.py
import time
import logging

logger = logging.getLogger("performance")

class TimingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            start = time.time()
            await self.app(scope, receive, send)
            duration = time.time() - start
            if duration > 5:
                logger.warning(
                    f"SLOW REQUEST: {scope['method']} {scope['path']} "
                    f"took {duration:.1f}s pid={os.getpid()}"
                )
```

If all slow requests show the same PID, that worker is the problem.

2. Check for lock contention. A common cause after new deploys:

```bash
# Check Postgres for locks
psql -c "SELECT pid, wait_event_type, wait_event, query
FROM pg_stat_activity WHERE wait_event IS NOT NULL;"
```

3. Check for a synchronous call in async context. If your new feature does something blocking in an async endpoint:

```python
# THIS BLOCKS THE ENTIRE WORKER:
@app.get("/api/report")
async def generate_report():
    result = requests.get("https://slow-api.example.com/data")  # sync call!
    return result.json()

# FIX -- either remove async or use httpx:
@app.get("/api/report")
def generate_report():  # sync endpoint gets its own thread
    result = requests.get("https://slow-api.example.com/data")
    return result.json()
```

This is the #1 cause of "random slowness after deploy" in FastAPI apps. If any async endpoint does a blocking call, it blocks the event loop and every request queued on that worker waits.

4. Check nginx access logs for the pattern:

```bash
# Find slow requests
awk '$NF > 5' /var/log/nginx/access.log | tail -20

# Check if they cluster on specific upstream ports (workers)
awk '$NF > 5 {print $0}' /var/log/nginx/access.log | grep -o 'upstream.*' | sort | uniq -c
```

5. Increase gunicorn workers as a temporary relief while you debug:

```bash
gunicorn app:app -w 8 --timeout 60
```

My bet is on #3 -- a sync HTTP call or file I/O in an async endpoint. Check the new feature's code for any `requests.*`, `open()`, or `subprocess.*` calls in async functions.'''
    },
    {
        "instruction": r'''Our background job (Celery task) that sends daily digest emails started failing silently. The task shows as SUCCESS in Flower but users aren't getting emails. No errors in the logs. This worked fine for months. How do I debug this?''',
        "output": r'''<think>
Task shows SUCCESS but emails aren't sent. Silent failures are the worst. The task is completing without errors but something in the email path changed. Let me think about common causes:

1. Email provider config changed or credentials expired
2. The task is succeeding but operating on an empty queryset (no users match)
3. Email is being sent but going to spam or being rejected
4. A code change made the task exit early without processing
</think>

Silent success means the task runs but either skips the work or the email delivery itself silently fails. Here's how to find it:

Step 1: Add observability to the task immediately:

```python
@celery_app.task
def send_daily_digest():
    users = User.objects.filter(
        digest_enabled=True,
        is_active=True,
    )
    logger.info(f"Daily digest: found {users.count()} users to email")

    sent = 0
    failed = 0
    for user in users:
        try:
            content = build_digest(user)
            if not content:
                logger.info(f"Skipping {user.email}: no content")
                continue
            send_email(user.email, "Your Daily Digest", content)
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send to {user.email}: {e}")
            failed += 1

    logger.info(f"Daily digest complete: {sent} sent, {failed} failed")

    if sent == 0:
        # Alert -- something is wrong
        logger.critical("Daily digest sent 0 emails!")

    return {"sent": sent, "failed": failed}
```

Step 2: Check the most common silent killers:

```python
# Is the queryset empty? Maybe a filter changed.
from django.core.management import call_command

# Run in shell:
User.objects.filter(digest_enabled=True, is_active=True).count()
# If this is 0, someone changed the data or a migration reset the field
```

Step 3: Check if your email backend is silently swallowing errors:

```python
# In settings.py, is this set?
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# Temporarily switch to console backend to verify emails are generated:
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
```

Step 4: Check SMTP credentials. Providers rotate API keys or passwords expire:

```python
# Test email sending directly
from django.core.mail import send_mail
try:
    send_mail("Test", "Body", "from@example.com", ["you@example.com"],
              fail_silently=False)  # KEY: fail_silently must be False
except Exception as e:
    print(f"Email broken: {e}")
```

Check if your code has `fail_silently=True` somewhere -- that's usually the culprit. Django's `send_mail` defaults to `fail_silently=False`, but if someone set it to True, SMTP failures are swallowed.

Step 5: Check your email provider's dashboard (SendGrid, SES, etc.) for:
- Bounced emails
- Quota exceeded
- API key disabled
- Sending domain verification expired

Most likely cause: either `fail_silently=True` hiding SMTP errors, or expired API credentials. The email provider dashboard will confirm which.'''
    },
    {
        "instruction": r'''I'm getting "MemoryError" crashes in production about once a day. It's a Django app processing CSV uploads. The CSV files can be up to 500MB. I'm reading the whole file into memory with pandas. How do I fix this without a complete rewrite of the processing logic?''',
        "output": r'''You need chunked processing. Pandas supports this natively -- minimal code changes required.

The problem:

```python
# This loads the entire 500MB CSV into memory
# Pandas needs 3-5x the file size in RAM, so 1.5-2.5GB per upload
df = pd.read_csv(uploaded_file)
process_dataframe(df)
```

The fix -- read in chunks:

```python
def process_csv_upload(uploaded_file):
    chunk_size = 10_000  # rows per chunk
    results = []

    for chunk in pd.read_csv(uploaded_file, chunksize=chunk_size):
        # Process each chunk exactly like you processed the full df
        chunk_result = process_dataframe(chunk)
        results.append(chunk_result)

    # Combine results
    return combine_results(results)
```

The key question is what `process_dataframe` does. Here are the common patterns:

If you're inserting rows into the database:

```python
def process_csv_upload(uploaded_file):
    chunk_size = 10_000
    total_inserted = 0

    for chunk in pd.read_csv(uploaded_file, chunksize=chunk_size):
        records = chunk.to_dict("records")
        MyModel.objects.bulk_create(
            [MyModel(**r) for r in records],
            ignore_conflicts=True,
        )
        total_inserted += len(records)

    return total_inserted
```

If you're computing aggregations:

```python
def process_csv_upload(uploaded_file):
    running_sum = 0
    running_count = 0

    for chunk in pd.read_csv(uploaded_file, chunksize=chunk_size):
        running_sum += chunk["amount"].sum()
        running_count += len(chunk)

    return {"average": running_sum / running_count, "total": running_count}
```

If you need to deduplicate or group across the whole file, use a dict as accumulator:

```python
def process_csv_upload(uploaded_file):
    totals_by_category = {}

    for chunk in pd.read_csv(uploaded_file, chunksize=chunk_size):
        for cat, group in chunk.groupby("category"):
            if cat not in totals_by_category:
                totals_by_category[cat] = 0
            totals_by_category[cat] += group["amount"].sum()

    return totals_by_category
```

Also, save the uploaded file to disk first instead of keeping it in Django's in-memory upload handler:

```python
# settings.py
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB; anything larger goes to disk
FILE_UPLOAD_TEMP_DIR = "/tmp/uploads"
```

This ensures Django streams large files to disk instead of holding them in RAM. Combined with chunked pandas reading, your memory usage drops from 2.5GB to about 50MB regardless of file size.'''
    },
    {
        "instruction": r'''We just got paged -- our Redis instance is at 98% memory and the app is throwing "OOM command not allowed" errors. We use Redis for caching, sessions, and as a Celery broker. I need to fix this NOW without losing active sessions. What do I do?''',
        "output": r'''Immediate triage -- do these in order:

Step 1: See what's eating the memory (30 seconds):

```bash
redis-cli info memory
redis-cli info keyspace

# Find the biggest keys
redis-cli --bigkeys

# Check key distribution by prefix
redis-cli --scan --pattern "celery*" | wc -l
redis-cli --scan --pattern "session*" | wc -l
redis-cli --scan --pattern "cache*" | wc -l
```

Step 2: Emergency relief -- flush the cache namespace (sessions survive):

```bash
# If you're using key prefixes (you should be), flush only cache keys:
redis-cli --scan --pattern "cache:*" | xargs redis-cli del

# If keys don't have prefixes, check TTLs -- keys with no expiry are the problem:
redis-cli --scan | while read key; do
    ttl=$(redis-cli ttl "$key")
    if [ "$ttl" = "-1" ]; then echo "NO EXPIRY: $key"; fi
done | head -20
```

Step 3: Set a maxmemory policy so this never causes OOM again:

```bash
# Allow Redis to evict cache keys when memory is full
redis-cli config set maxmemory-policy allkeys-lru
redis-cli config set maxmemory 1gb  # or whatever your limit should be

# Make it persist across restarts
redis-cli config rewrite
```

Step 4: After the fire is out, separate your Redis usage. Running cache + sessions + Celery on one instance is the root cause:

```python
# settings.py -- use separate Redis databases (or separate instances)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://localhost:6379/0",  # DB 0 for cache
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "sessions"
CACHES["sessions"] = {
    "BACKEND": "django_redis.cache.RedisCache",
    "LOCATION": "redis://localhost:6379/1",  # DB 1 for sessions
}

CELERY_BROKER_URL = "redis://localhost:6379/2"  # DB 2 for Celery
```

Step 5: Audit your caching code for missing TTLs:

```python
# BAD -- no timeout, lives forever
cache.set("user_profile_123", data)

# GOOD -- always set a timeout
cache.set("user_profile_123", data, timeout=3600)
```

The most common cause: Celery result backend storing task results forever without TTL. Add this:

```python
CELERY_RESULT_EXPIRES = 3600  # delete results after 1 hour
```'''
    },
]
