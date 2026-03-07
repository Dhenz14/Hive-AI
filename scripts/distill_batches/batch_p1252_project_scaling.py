"""
Real-world project help training pairs - Scaling problems
"""

pairs = [
    {
        "instruction": r'''Our Django app is getting slow. We have about 50k users and the main dashboard page takes 8 seconds to load. It shows user stats, recent activity, and some aggregated metrics. The page makes about 15 database queries. We're on a single Postgres instance. Where do I start?''',
        "output": r'''<think>
8 seconds for a dashboard with 15 queries at 50k users -- this is almost certainly a query problem, not a scaling problem. Let me help them diagnose before jumping to solutions.

Common culprits:
1. N+1 queries (the #1 cause of slow Django pages)
2. Missing indexes on filter/join columns
3. Aggregations scanning full tables
4. No caching for expensive computed metrics
</think>

8 seconds with 15 queries means some of those queries are very slow. Before adding infrastructure, let's find the bottleneck.

Step 1: Install django-debug-toolbar to see exactly what's happening:

```bash
pip install django-debug-toolbar
```

```python
# settings.py (dev only)
INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE
INTERNAL_IPS = ["127.0.0.1"]
```

Load the dashboard and check the SQL panel. You'll likely see:
- Some queries taking 2-3 seconds each (missing indexes)
- 10+ similar queries (N+1 problem)
- Full table scans for aggregations

Step 2: Fix the N+1 queries. This is almost certainly your biggest win:

```python
# BEFORE -- triggers a query per user for each related object
users = User.objects.filter(is_active=True)
for u in users:
    print(u.profile.company)  # extra query each iteration

# AFTER
users = User.objects.filter(is_active=True).select_related("profile__company")
```

Step 3: Add indexes for your filter columns:

```python
class Activity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField()
    action_type = models.CharField(max_length=50)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["action_type", "-created_at"]),
        ]
```

Step 4: Cache the expensive aggregations. Dashboard metrics that scan large tables should be cached:

```python
from django.core.cache import cache

def get_dashboard_stats(user):
    cache_key = f"dashboard_stats_{user.id}"
    stats = cache.get(cache_key)
    if stats is None:
        stats = {
            "total_orders": Order.objects.filter(user=user).count(),
            "monthly_revenue": Order.objects.filter(
                user=user, created_at__gte=thirty_days_ago
            ).aggregate(total=Sum("amount"))["total"] or 0,
        }
        cache.set(cache_key, stats, timeout=300)  # 5 min cache
    return stats
```

These three fixes (N+1, indexes, caching) typically take a page from 8s to under 500ms. You don't need Redis, read replicas, or horizontal scaling at 50k users -- you need better queries.'''
    },
    {
        "instruction": r'''We have a Flask API that processes image uploads. Users upload photos, we resize them to 3 sizes, and store them in S3. During peak hours we get about 200 uploads/minute and the API becomes unresponsive because the image processing blocks the request. How do we fix this?''',
        "output": r'''The fix is to move image processing out of the request/response cycle. Accept the upload immediately, process async.

Architecture change:

```
Before: Client -> API (upload + resize + S3) -> Response  [10-15 seconds]
After:  Client -> API (upload + queue job) -> Response     [< 1 second]
                  Worker (resize + S3)       -> Done
```

Implementation with Celery + Redis:

```python
# tasks.py
from celery import Celery
from PIL import Image
import boto3
import io

celery_app = Celery("tasks", broker="redis://localhost:6379/0")

SIZES = {"thumb": (150, 150), "medium": (800, 600), "large": (1920, 1080)}

@celery_app.task(bind=True, max_retries=3)
def process_upload(self, upload_id, original_key):
    try:
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket="uploads-raw", Key=original_key)
        img = Image.open(io.BytesIO(obj["Body"].read()))

        for name, size in SIZES.items():
            resized = img.copy()
            resized.thumbnail(size, Image.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            s3.upload_fileobj(buf, "uploads-processed",
                              f"{upload_id}/{name}.jpg")

        # Update DB record
        db.session.query(Upload).filter_by(id=upload_id).update(
            {"status": "complete"}
        )
        db.session.commit()
    except Exception as exc:
        self.retry(exc=exc, countdown=30)
```

```python
# routes.py
@app.route("/upload", methods=["POST"])
def upload_image():
    file = request.files["image"]
    upload = Upload(status="processing", user_id=current_user.id)
    db.session.add(upload)
    db.session.commit()

    # Store original in S3 immediately
    key = f"raw/{upload.id}/{file.filename}"
    s3.upload_fileobj(file, "uploads-raw", key)

    # Queue the processing
    process_upload.delay(upload.id, key)

    return jsonify({"upload_id": upload.id, "status": "processing"}), 202
```

The client gets a 202 response instantly. Add a status endpoint so the frontend can poll:

```python
@app.route("/upload/<int:upload_id>/status")
def upload_status(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    return jsonify({"status": upload.status})
```

Run 2-4 Celery workers depending on your server CPU:

```bash
celery -A tasks worker --concurrency=4 --loglevel=info
```

At 200 uploads/min with 4 workers, each processing takes about 5 seconds, so you can handle ~48/min per worker = 192/min. Scale workers horizontally if you need more.'''
    },
    {
        "instruction": r'''Our Postgres database is at 500GB and growing. The main table (events) has 2 billion rows and queries against it are getting slower even with indexes. We need to query by time range (last 7 days, last 30 days, etc). What's the best approach?''',
        "output": r'''<think>
2 billion rows, time-range queries, growing fast. This is a classic case for table partitioning. Postgres has native partitioning support since v10, and it's the right tool here.

They query by time range, so partition by time. Monthly partitions make sense -- you can drop old ones easily and queries only scan relevant partitions.
</think>

Table partitioning. Postgres will automatically route queries to only the relevant partitions, so a "last 7 days" query scans one partition instead of 2 billion rows.

Step 1: Create the partitioned table (you'll migrate data to it):

```sql
-- New partitioned table matching your existing schema
CREATE TABLE events_partitioned (
    id bigint GENERATED ALWAYS AS IDENTITY,
    event_type varchar(50) NOT NULL,
    payload jsonb,
    user_id bigint,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (id, created_at)  -- partition key must be in PK
) PARTITION BY RANGE (created_at);
```

Step 2: Create monthly partitions:

```sql
-- Create partitions for each month
CREATE TABLE events_y2024m01 PARTITION OF events_partitioned
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE events_y2024m02 PARTITION OF events_partitioned
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
-- ... etc
```

Automate partition creation with a cron job:

```python
# create_partitions.py -- run monthly via cron
from datetime import date, timedelta
import psycopg2

def ensure_partitions(conn, months_ahead=3):
    today = date.today().replace(day=1)
    cur = conn.cursor()
    for i in range(months_ahead):
        start = today + timedelta(days=32 * i)
        start = start.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        name = f"events_y{start.year}m{start.month:02d}"
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {name}
            PARTITION OF events_partitioned
            FOR VALUES FROM ('{start}') TO ('{end}')
        """)
    conn.commit()
```

Step 3: Migrate data. Do this during low traffic, in batches:

```sql
-- Migrate in chunks to avoid locking
INSERT INTO events_partitioned (event_type, payload, user_id, created_at)
SELECT event_type, payload, user_id, created_at
FROM events
WHERE created_at >= '2024-01-01' AND created_at < '2024-02-01';
-- Repeat per month
```

Step 4: Swap tables:

```sql
BEGIN;
ALTER TABLE events RENAME TO events_old;
ALTER TABLE events_partitioned RENAME TO events;
COMMIT;
```

After partitioning, a "last 7 days" query only hits 1-2 partitions instead of the full 500GB table. You also get free data lifecycle management -- drop old partitions instantly instead of slow DELETEs.

Add indexes per partition -- they're smaller and faster to build:

```sql
CREATE INDEX ON events_y2024m01 (user_id, created_at);
```'''
    },
    {
        "instruction": r'''We have a REST API that returns large JSON responses -- sometimes 5MB+ for endpoints that list thousands of items. Mobile clients are complaining about slow load times and data usage. We can't just reduce the data because clients need all those fields. What are our options?''',
        "output": r'''You have several options, and they stack:

1. Pagination (mandatory, do this first):

```python
@app.get("/api/items")
def list_items(page: int = 1, per_page: int = 50):
    offset = (page - 1) * per_page
    items = db.query(Item).offset(offset).limit(per_page).all()
    total = db.query(Item).count()
    return {
        "data": [serialize(i) for i in items],
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    }
```

If clients genuinely need all items at once (e.g., for offline sync), use cursor-based pagination:

```python
@app.get("/api/items")
def list_items(after: int = 0, limit: int = 200):
    items = db.query(Item).filter(Item.id > after).limit(limit).all()
    return {
        "data": [serialize(i) for i in items],
        "next_cursor": items[-1].id if items else None,
    }
```

2. Compression (easy win, huge impact on JSON):

```python
# FastAPI -- add gzip middleware
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

JSON compresses extremely well. A 5MB JSON response typically compresses to 300-500KB with gzip. Mobile clients already support Accept-Encoding: gzip.

3. Sparse fieldsets -- let clients request only the fields they need:

```python
@app.get("/api/items")
def list_items(fields: str = None):
    items = db.query(Item).all()
    if fields:
        allowed = set(fields.split(","))
        return {"data": [
            {k: v for k, v in serialize(i).items() if k in allowed}
            for i in items
        ]}
    return {"data": [serialize(i) for i in items]}
```

Client calls: `GET /api/items?fields=id,name,price,status`

4. ETags for caching -- avoid re-sending unchanged data:

```python
import hashlib

@app.get("/api/items")
def list_items(request: Request):
    data = get_items_data()
    etag = hashlib.md5(json.dumps(data).encode()).hexdigest()

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    return JSONResponse(data, headers={"ETag": etag})
```

Priority order: Pagination + Compression first (covers 90% of the problem), then fieldsets if still needed. ETags help for repeated requests.'''
    },
    {
        "instruction": r'''I'm running a Python web scraper that needs to scrape 100k pages. Currently it's single-threaded and takes 3 days. I need it done in a few hours. The bottleneck is waiting for HTTP responses. What's the fastest approach?''',
        "output": r'''The bottleneck is I/O wait, so you need async HTTP. Use aiohttp with asyncio -- it can handle hundreds of concurrent requests.

```python
import asyncio
import aiohttp
from aiohttp import TCPConnector
import json
import time

CONCURRENCY = 50  # start here, tune up if target allows
TIMEOUT = aiohttp.ClientTimeout(total=30)

async def fetch_page(session, url, semaphore):
    async with semaphore:
        try:
            async with session.get(url, timeout=TIMEOUT) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    return {"url": url, "html": html, "status": 200}
                elif resp.status == 429:
                    # Rate limited -- back off and retry
                    await asyncio.sleep(5)
                    async with session.get(url, timeout=TIMEOUT) as retry:
                        html = await retry.text()
                        return {"url": url, "html": html, "status": retry.status}
                else:
                    return {"url": url, "html": None, "status": resp.status}
        except Exception as e:
            return {"url": url, "html": None, "error": str(e)}

async def scrape_all(urls):
    semaphore = asyncio.Semaphore(CONCURRENCY)
    connector = TCPConnector(limit=CONCURRENCY, ttl_dns_cache=300)
    results = []

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_page(session, url, semaphore) for url in urls]

        # Process in batches to avoid memory issues with 100k tasks
        batch_size = 1000
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            results.extend(batch_results)

            done = min(i + batch_size, len(tasks))
            print(f"Progress: {done}/{len(tasks)}")

    return results

if __name__ == "__main__":
    with open("urls.txt") as f:
        urls = [line.strip() for line in f if line.strip()]

    start = time.time()
    results = asyncio.run(scrape_all(urls))
    elapsed = time.time() - start

    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == 200)
    print(f"Done: {success}/{len(urls)} successful in {elapsed:.0f}s")
```

Key tuning points:

- `CONCURRENCY = 50` -- controls max simultaneous requests. Start at 50, increase to 100-200 if the target handles it. Going too high gets you IP-banned.
- Batch the `gather()` calls -- creating 100k coroutines at once eats memory.
- DNS caching (`ttl_dns_cache=300`) avoids redundant DNS lookups.
- Add a retry for 429s since you will get rate limited at this scale.

With 50 concurrent requests and ~500ms average response time, you get ~100 pages/second = 100k pages in ~17 minutes. Even at conservative settings (20 concurrent, 1s avg), that's ~3 hours vs your current 3 days.

If you need to be polite about it, add a small delay per domain:

```python
# Per-domain rate limiting
domain_locks = {}
async def rate_limited_fetch(session, url, semaphore):
    domain = urlparse(url).netloc
    if domain not in domain_locks:
        domain_locks[domain] = asyncio.Lock()
    async with domain_locks[domain]:
        result = await fetch_page(session, url, semaphore)
        await asyncio.sleep(0.5)  # 500ms between requests per domain
        return result
```'''
    },
]
