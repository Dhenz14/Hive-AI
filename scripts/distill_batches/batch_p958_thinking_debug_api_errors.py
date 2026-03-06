PAIRS = [
    ("thinking/debugging", r'''Our microservice is returning 502 Bad Gateway errors intermittently. Nginx logs:

```
2024/03/15 14:23:45 [error] 1234#0: *5678 upstream prematurely closed connection while reading response header from upstream, client: 10.0.1.50, server: api.example.com, request: "POST /api/process HTTP/1.1", upstream: "http://127.0.0.1:8000/api/process"
```

The backend (Gunicorn + Flask) logs show no errors. The requests that get 502s take 30+ seconds. Nginx config:

```nginx
upstream backend {
    server 127.0.0.1:8000;
}

server {
    location /api/ {
        proxy_pass http://backend;
    }
}
```

The 502s only happen on slow endpoints. Fast endpoints work fine.''', r'''<think>
The error "upstream prematurely closed connection while reading response header" combined with the fact that only slow endpoints (30+ seconds) fail points to a timeout issue.

Nginx has a default `proxy_read_timeout` of 60 seconds. But Gunicorn also has a worker timeout (default 30 seconds). If a Gunicorn worker takes longer than 30 seconds to process a request, Gunicorn's master process kills the worker, which closes the connection. Nginx then sees "upstream prematurely closed connection" and returns 502.

The fact that the backend logs show no errors makes sense -- the worker is killed by a signal, so it does not get a chance to log an error. The Gunicorn master might log a worker timeout, but the user might not be checking those logs.

The fix: increase both Gunicorn's worker timeout and Nginx's proxy timeouts.
</think>

The 502 errors are caused by Gunicorn killing slow workers before they can send a response to Nginx. Here is the chain of events:

```
1. Client sends POST to Nginx
2. Nginx forwards to Gunicorn (127.0.0.1:8000)
3. Gunicorn worker starts processing (takes 30+ seconds)
4. Gunicorn master: "Worker hasn't sent a heartbeat in 30s, it's hung!"
5. Gunicorn master sends SIGKILL to the worker
6. Worker dies, TCP connection to Nginx is closed
7. Nginx: "upstream prematurely closed connection" -> 502 Bad Gateway
```

**Why there are no backend logs:** The worker is killed by SIGKILL, which cannot be caught. The worker has no opportunity to log anything. Check the Gunicorn master process logs -- you should see:

```
[CRITICAL] WORKER TIMEOUT (pid:1234)
```

**Fix 1: Increase Gunicorn's worker timeout**

```bash
gunicorn app:app --timeout 120 --workers 4
```

The default `--timeout` is 30 seconds. Increase it to accommodate your slowest endpoint.

**Fix 2: Increase Nginx proxy timeouts**

```nginx
location /api/ {
    proxy_pass http://backend;
    proxy_read_timeout 120s;
    proxy_connect_timeout 10s;
    proxy_send_timeout 120s;

    # Also important for POST requests:
    proxy_buffering on;
    proxy_buffer_size 16k;
    proxy_buffers 4 32k;
}
```

**Fix 3: Use async workers for long-running requests**

```bash
gunicorn app:app --worker-class gevent --timeout 120 --workers 4
```

Gevent workers can handle multiple concurrent requests per worker, so a slow request does not block other requests. The worker sends heartbeats even while waiting on I/O.

**Fix 4: Move slow work to a background task queue**

```python
from celery import Celery

celery = Celery('tasks', broker='redis://localhost:6379')

@app.route('/api/process', methods=['POST'])
def process():
    task = process_data.delay(request.json)
    return jsonify({'task_id': task.id, 'status': 'processing'}), 202

@celery.task
def process_data(data):
    # Long-running work happens here, outside the request cycle
    result = expensive_computation(data)
    store_result(result)
```

The client gets an immediate 202 response and can poll for the result. This eliminates timeout issues entirely.

**Prevention tips:**
- Set Gunicorn timeout to 2x your slowest expected endpoint duration
- Add request timeout middleware that logs slow requests before they hit the Gunicorn timeout
- Use `proxy_read_timeout` in Nginx slightly higher than Gunicorn timeout (so Gunicorn handles the timeout, not Nginx)
- Move any operation taking more than 10 seconds to a background task queue
- Add health check endpoints that respond quickly to verify the service is alive
- Monitor worker restart frequency as a signal of timeout issues'''),

    ("thinking/debugging", r'''My React SPA gets CORS errors when calling my API from localhost:

```
Access to XMLHttpRequest at 'https://api.example.com/data' from origin 'http://localhost:3000'
has been blocked by CORS policy: Response to preflight request doesn't pass access control check:
No 'Access-Control-Allow-Origin' header is present on the requested response.
```

My Flask backend has CORS configured:

```python
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})

@app.route('/data')
def get_data():
    return jsonify({"result": "hello"})
```

The route is /data but CORS is configured for /api/*. But even after fixing that, OPTIONS requests return 404.''', r'''<think>
Multiple issues here:

1. The CORS configuration uses `r"/api/*"` but the route is `/data`. The pattern does not match, so CORS headers are not applied to `/data`.

2. Even if fixed, the browser sends an OPTIONS preflight request for cross-origin requests (especially with custom headers or non-simple methods). If the server does not handle OPTIONS requests, it returns 404 and the preflight fails.

3. The URL mismatch: the frontend calls `https://api.example.com/data` but CORS is set for `http://localhost:3000`. The origin must match exactly (protocol + host + port).

Let me address all of these.
</think>

There are multiple issues causing the CORS failure:

**Issue 1: Route pattern mismatch**

Your CORS config uses `r"/api/*"` but the route is `/data`. The CORS headers are only applied to routes matching `/api/*`, so `/data` gets no CORS headers.

**Issue 2: OPTIONS preflight not handled**

The browser sends an OPTIONS request before the actual request (the "preflight"). If your server returns 404 for OPTIONS, the preflight fails and the browser blocks the actual request.

**Issue 3: Origin mismatch matters**

CORS compares origins exactly: `http://localhost:3000` is different from `http://127.0.0.1:3000` or `https://localhost:3000`.

**Complete fix:**

```python
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Match ALL routes, or be specific about each one
CORS(app, resources={
    r"/*": {
        "origins": [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://your-production-domain.com",
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
    }
})

@app.route('/data')
def get_data():
    return jsonify({"result": "hello"})
```

**If flask-cors is not handling OPTIONS properly, add explicit handling:**

```python
@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    allowed_origins = ['http://localhost:3000', 'https://your-domain.com']

    if origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '3600'

    return response
```

**Understanding preflight requests:**

The browser sends an OPTIONS preflight when the request has:
- Methods other than GET, HEAD, POST
- Custom headers (like Authorization, X-Custom-Header)
- Content-Type other than application/x-www-form-urlencoded, multipart/form-data, or text/plain

The preflight asks: "Is this cross-origin request allowed?" The server must respond with appropriate `Access-Control-Allow-*` headers.

**Debugging CORS issues:**

```bash
# Simulate a preflight request
curl -X OPTIONS https://api.example.com/data \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  -v

# Check response headers:
# Access-Control-Allow-Origin: http://localhost:3000
# Access-Control-Allow-Methods: POST
# Access-Control-Allow-Headers: Content-Type
```

**Prevention tips:**
- Always test CORS with curl before deploying -- browser DevTools can be misleading
- Use environment-based origin configuration (do not hardcode localhost in production)
- Set `Access-Control-Max-Age` to cache preflight responses and reduce OPTIONS traffic
- Never use `Access-Control-Allow-Origin: *` with credentials -- browsers reject this
- Use a reverse proxy in development to avoid CORS entirely (Vite/webpack proxy config)'''),

    ("thinking/debugging", r'''Our API client is hitting rate limits and the retry logic is making it worse:

```
429 Too Many Requests
Retry-After: 60

But our retry code:
```python
import requests
import time

def api_call(url, max_retries=5):
    for attempt in range(max_retries):
        response = requests.get(url)
        if response.status_code == 429:
            time.sleep(1)  # wait 1 second and retry
            continue
        return response
    raise Exception("Max retries exceeded")
```

The server says "wait 60 seconds" but we wait 1 second and immediately retry, getting another 429, and quickly burn through all retries. Worse, with 20 concurrent workers doing this, we're hammering the API and getting IP-banned.''', r'''<think>
Multiple problems:
1. Ignoring the Retry-After header
2. Fixed 1-second backoff instead of exponential
3. All workers retry at the same time (thundering herd)
4. No jitter to spread out retries

The fix needs to respect Retry-After, use exponential backoff with jitter, and ideally use a shared rate limiter across workers.
</think>

The retry logic has several critical flaws that compound to make the rate limiting situation worse:

1. **Ignoring Retry-After header** -- the server explicitly says "wait 60 seconds" but you wait 1 second
2. **No exponential backoff** -- retries happen at the same interval, hammering the server
3. **No jitter** -- with 20 workers, all retries happen simultaneously
4. **Aggressive retry count** -- 5 rapid retries against a rate-limited API just wastes your quota

**Proper retry implementation:**

```python
import requests
import time
import random

def api_call(url, max_retries=5):
    for attempt in range(max_retries):
        response = requests.get(url, timeout=30)

        if response.status_code == 429:
            # Respect the Retry-After header
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                try:
                    wait_time = int(retry_after)
                except ValueError:
                    # Retry-After can be a date string
                    from email.utils import parsedate_to_datetime
                    retry_date = parsedate_to_datetime(retry_after)
                    wait_time = max(0, (retry_date - datetime.utcnow()).total_seconds())
            else:
                # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                wait_time = (2 ** attempt)

            # Add jitter: +/- 25% to avoid thundering herd
            jitter = wait_time * random.uniform(-0.25, 0.25)
            actual_wait = wait_time + jitter

            print(f"Rate limited. Waiting {actual_wait:.1f}s (attempt {attempt + 1})")
            time.sleep(actual_wait)
            continue

        if response.status_code >= 500:
            # Server error: exponential backoff
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait_time)
            continue

        return response

    raise Exception(f"Max retries ({max_retries}) exceeded for {url}")
```

**Better: Use a rate limiter across all workers**

```python
import threading
import time

class RateLimiter:
    def __init__(self, calls_per_second=10):
        self.interval = 1.0 / calls_per_second
        self.lock = threading.Lock()
        self.last_call = 0
        self.backoff_until = 0

    def wait(self):
        with self.lock:
            now = time.monotonic()

            # If we got a 429, respect the backoff period
            if now < self.backoff_until:
                sleep_time = self.backoff_until - now
                time.sleep(sleep_time)

            # Enforce rate limit
            elapsed = now - self.last_call
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)

            self.last_call = time.monotonic()

    def set_backoff(self, seconds):
        with self.lock:
            self.backoff_until = time.monotonic() + seconds

# Shared across all workers
limiter = RateLimiter(calls_per_second=10)

def api_call(url):
    for attempt in range(5):
        limiter.wait()  # wait for rate limiter
        response = requests.get(url, timeout=30)

        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            limiter.set_backoff(retry_after)  # all workers respect this
            continue

        return response
```

**Even better: Use the tenacity library**

```python
from tenacity import retry, wait_exponential, retry_if_result, stop_after_attempt

def is_rate_limited(response):
    return response.status_code == 429

@retry(
    retry=retry_if_result(is_rate_limited),
    wait=wait_exponential(multiplier=1, min=1, max=120),
    stop=stop_after_attempt(5),
)
def api_call(url):
    return requests.get(url, timeout=30)
```

**Prevention tips:**
- Always read and respect Retry-After headers
- Use exponential backoff with jitter for all retry logic
- Share rate limiting state across workers/threads
- Pre-throttle requests to stay below the API rate limit
- Monitor your API usage and set alerts at 80% of quota
- Use circuit breaker pattern to stop all requests when error rate exceeds a threshold'''),

    ("thinking/debugging", r'''Our auth token refresh is creating a race condition with concurrent API requests:

```
Thread-1: GET /api/data -> 401 Unauthorized (token expired)
Thread-1: POST /auth/refresh -> 200 (new token: token_B)
Thread-2: GET /api/data -> 401 Unauthorized (token_A was revoked by Thread-1's refresh)
Thread-2: POST /auth/refresh -> 400 Bad Request (refresh token already used!)
Thread-3: GET /api/data -> 401 Unauthorized
Thread-3: POST /auth/refresh -> 400 Bad Request (refresh token already used!)
```

The refresh token is single-use. When Thread-1 uses it to get a new token, Threads 2 and 3 also detect the expired token and try to refresh, but the old refresh token is already consumed.''', r'''<think>
This is a common concurrency issue with OAuth token refresh. Multiple threads detect an expired access token, and all try to refresh simultaneously. Since refresh tokens are single-use (for security), only the first refresh succeeds.

The solution is to ensure only one thread performs the refresh, and all other threads wait for and use the result.

This can be done with:
1. A lock around the refresh operation
2. A "refresh in progress" flag with a condition variable
3. An atomic compare-and-swap pattern
</think>

This is a classic token refresh race condition. Multiple threads detect the expired token simultaneously and all attempt to use the single-use refresh token. Only the first succeeds; the rest fail because the refresh token is invalidated after one use.

**Fix: Use a lock to serialize token refresh**

```python
import threading
import time
import requests

class TokenManager:
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.refresh_token = refresh_token
        self.token_expiry = 0
        self._refresh_lock = threading.Lock()
        self._refresh_in_progress = threading.Event()
        self._refresh_in_progress.set()  # not refreshing initially

    def get_token(self):
        """Get a valid access token, refreshing if necessary."""
        if time.time() < self.token_expiry - 30:  # 30s buffer
            return self.access_token

        # Try to acquire the refresh lock
        if self._refresh_lock.acquire(blocking=False):
            # This thread will do the refresh
            try:
                self._refresh_in_progress.clear()
                self._do_refresh()
            finally:
                self._refresh_in_progress.set()
                self._refresh_lock.release()
        else:
            # Another thread is refreshing -- wait for it
            self._refresh_in_progress.wait(timeout=30)

        return self.access_token

    def _do_refresh(self):
        response = requests.post('https://auth.example.com/token', data={
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        })
        response.raise_for_status()
        data = response.json()
        self.access_token = data['access_token']
        self.refresh_token = data['refresh_token']  # new refresh token
        self.token_expiry = time.time() + data['expires_in']


class APIClient:
    def __init__(self, token_manager):
        self.token_manager = token_manager
        self.session = requests.Session()

    def request(self, method, url, **kwargs):
        # Get a valid token
        token = self.token_manager.get_token()
        self.session.headers['Authorization'] = f'Bearer {token}'

        response = self.session.request(method, url, **kwargs)

        if response.status_code == 401:
            # Token was rejected -- force refresh
            self.token_manager.token_expiry = 0  # mark as expired
            token = self.token_manager.get_token()
            self.session.headers['Authorization'] = f'Bearer {token}'
            response = self.session.request(method, url, **kwargs)

        return response
```

**How this solves the race condition:**

```
Thread-1: GET -> 401 -> acquires refresh lock -> refreshes -> gets token_B
Thread-2: GET -> 401 -> lock taken, waits -> gets token_B (already refreshed)
Thread-3: GET -> 401 -> lock taken, waits -> gets token_B (already refreshed)
```

Only one thread performs the refresh. All others wait for the result and use the new token.

**Proactive token refresh (even better):**

```python
def _schedule_proactive_refresh(self):
    """Refresh the token before it expires."""
    refresh_time = self.token_expiry - 60  # refresh 60s before expiry
    delay = max(0, refresh_time - time.time())
    timer = threading.Timer(delay, self.get_token)
    timer.daemon = True
    timer.start()
```

This refreshes the token proactively, so no request ever encounters an expired token.

**Prevention tips:**
- Always use a mutex or similar mechanism around token refresh
- Refresh tokens proactively before they expire (use a timer)
- Add a buffer to token expiry checks (30-60 seconds before actual expiry)
- Consider using a dedicated token management service in microservice architectures
- Log token refresh events to debug authentication flows
- Use the `requests-oauthlib` library which handles some of these patterns automatically'''),

    ("thinking/debugging", r'''Our paginated API returns duplicate items when data is modified during pagination:

```python
# Client code:
def fetch_all_items():
    items = []
    page = 1
    while True:
        response = requests.get(f'/api/items?page={page}&per_page=50&sort=created_at')
        data = response.json()
        if not data['items']:
            break
        items.extend(data['items'])
        page += 1
    return items
```

Result: 2847 items fetched, but 23 are duplicates and 15 items are missing.

This happens because new items are inserted while we're paginating. When a new item is inserted on page 1, all subsequent items shift by one position, causing the item at the page boundary to appear on both page 2 and page 3.''', r'''<think>
This is the classic offset-based pagination problem. When using LIMIT/OFFSET (which page-based pagination translates to), any insert or delete shifts the result set. An insert before the current offset means you see a duplicate; a delete before the current offset means you skip an item.

Solutions:
1. Cursor-based pagination (keyset pagination) -- use the last item's ID or timestamp as the cursor
2. Timestamp-based filtering -- only fetch items created before the pagination started
3. Snapshot isolation at the database level
</think>

This is a fundamental flaw with offset-based pagination. When data changes during pagination, offsets shift:

**How duplicates appear:**
```
Page 1 fetch: items at positions 1-50
New item inserted at position 5
Page 2 fetch: items at positions 51-100
  -> But what was position 50 is now position 51 (shifted by the insert)
  -> Item that was position 50 appears in BOTH page 1 and page 2
```

**How items are missed:**
```
Page 1 fetch: items at positions 1-50
Item at position 30 is deleted
Page 2 fetch: items at positions 51-100
  -> What was position 51 is now position 50 (shifted by the delete)
  -> That item was already past page 1 but is now before page 2's offset
  -> It appears in NEITHER page
```

**Fix 1: Cursor-based pagination (keyset pagination)**

Instead of page numbers, use the last item's sort key as a cursor:

```python
# Server-side (SQL)
# First page:
SELECT * FROM items ORDER BY created_at DESC, id DESC LIMIT 50;

# Next page (using cursor from last item):
SELECT * FROM items
WHERE (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

```python
# Client-side:
def fetch_all_items():
    items = []
    cursor = None
    while True:
        params = {'per_page': 50}
        if cursor:
            params['cursor'] = cursor
        response = requests.get('/api/items', params=params)
        data = response.json()
        if not data['items']:
            break
        items.extend(data['items'])
        cursor = data['next_cursor']
    return items
```

**Server implementation:**

```python
@app.route('/api/items')
def list_items():
    per_page = int(request.args.get('per_page', 50))
    cursor = request.args.get('cursor')

    query = Item.query.order_by(Item.created_at.desc(), Item.id.desc())

    if cursor:
        # Decode cursor: "timestamp|id"
        cursor_time, cursor_id = cursor.split('|')
        query = query.filter(
            db.or_(
                Item.created_at < cursor_time,
                db.and_(
                    Item.created_at == cursor_time,
                    Item.id < int(cursor_id),
                ),
            )
        )

    items = query.limit(per_page + 1).all()  # fetch one extra to detect more pages
    has_more = len(items) > per_page
    items = items[:per_page]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = f"{last.created_at.isoformat()}|{last.id}"

    return jsonify({
        'items': [item.to_dict() for item in items],
        'next_cursor': next_cursor,
        'has_more': has_more,
    })
```

**Why cursor-based pagination is stable:**

The cursor points to a specific item in the sort order. New inserts before or after the cursor do not affect which items come next. The query always asks "give me 50 items after this specific point," which is deterministic regardless of concurrent modifications.

**Fix 2: Snapshot timestamp (simpler but less precise)**

```python
# First request: capture a snapshot timestamp
first_response = requests.get('/api/items?per_page=50')
snapshot_time = first_response.headers['X-Snapshot-Time']

# Subsequent requests: only see items from before the snapshot
response = requests.get(f'/api/items?page=2&per_page=50&before={snapshot_time}')
```

**Prevention tips:**
- Always use cursor-based pagination for APIs where data changes frequently
- Use compound cursors (timestamp + ID) to handle items with identical timestamps
- Never expose offset-based pagination in public APIs
- Add a `has_more` flag instead of relying on empty pages to detect the end
- Include total count only when explicitly requested (it requires a separate COUNT query)'''),
]
