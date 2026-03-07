"""
Multi-turn conversation training pairs - Debugging Sessions
Realistic debugging conversations with iterative error resolution
"""

pairs = [
    {
        "instruction": r'''[Previous conversation]
User: I am getting a circular import error in Python. email_service.py imports from template_engine.py, and template_engine.py imports EmailConfig from email_service.py.
Assistant: That is a circular import. Move EmailConfig to a separate config.py file that both modules can import from, or use a lazy import inside the function instead of at module level.

[Current message]
User: I moved EmailConfig to config.py and the circular import is fixed. But now I get:

AttributeError: 'NoneType' object has no attribute 'send'

My code:

```python
class EmailService:
    def __init__(self):
        self.client = None

    def connect(self):
        self.client = SMTPClient(host=config.SMTP_HOST, port=config.SMTP_PORT)

    def send_email(self, to, subject, body):
        self.client.send(to=to, subject=subject, body=body)
```

I call send_email but self.client is None because connect() was never called.''',
        "output": r'''The circular import fix looks good. The new error is straightforward -- self.client is None because connect() was never called before send_email(). Best fix is a lazy-connect property:

```python
class EmailService:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = SMTPClient(
                host=config.SMTP_HOST,
                port=config.SMTP_PORT,
            )
        return self._client

    def send_email(self, to, subject, body):
        # self.client triggers auto-connect via the property
        self.client.send(to=to, subject=subject, body=body)

    def disconnect(self):
        if self._client is not None:
            self._client.close()
            self._client = None
```

This avoids the "forgot to call connect()" problem entirely. The property creates the connection on first use and caches it. You can also add a reconnect method or have the property check if the connection is still alive before returning it.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My JavaScript app crashes with: TypeError: Cannot read properties of undefined (reading 'map'). The code is:

```javascript
async function getUsers() {
    const response = await fetch('/api/users');
    const data = await response.json();
    return data.users.map(u => u.name);
}
```
Assistant: The API might be returning a different shape than expected. data.users could be undefined. Add a console.log(data) before the map call to see the actual response shape.

[Current message]
User: I added the console.log and the API returns this:

```json
{"data": [{"name": "Alice"}, {"name": "Bob"}], "total": 2}
```

So it is data.data not data.users. But also sometimes the API returns an error:

```json
{"error": "unauthorized", "data": null}
```

How do I handle both cases?''',
        "output": r'''Now that you can see the actual response shape, the fix is to check for errors and use the correct field name. Here is a robust version:

```javascript
async function getUsers() {
    const response = await fetch('/api/users');

    // Check HTTP status first
    if (!response.ok) {
        throw new Error('API request failed with status ' + response.status);
    }

    const data = await response.json();

    // Check for API-level errors
    if (data.error) {
        throw new Error('API error: ' + data.error);
    }

    // Guard against null/undefined data array
    if (!Array.isArray(data.data)) {
        throw new Error('Unexpected response: data.data is not an array');
    }

    return data.data.map(u => u.name);
}

// Usage with error handling
async function displayUsers() {
    try {
        const names = await getUsers();
        console.log('Users:', names);
    } catch (err) {
        console.error('Failed to load users:', err.message);
        // Show error UI to user
    }
}
```

The key fixes: (1) use data.data instead of data.users to match the actual API response, (2) check response.ok for HTTP errors, (3) check data.error for API-level errors, (4) validate that data.data is actually an array before calling map on it. This way you get clear error messages instead of cryptic TypeErrors.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My PostgreSQL query is very slow. It takes 15 seconds to run:

```sql
SELECT u.name, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE o.created_at > '2024-01-01'
GROUP BY u.name
ORDER BY order_count DESC;
```

The users table has 50,000 rows and orders has 2 million rows.
Assistant: Run EXPLAIN ANALYZE on the query and share the output. Also check if you have an index on orders.user_id and orders.created_at.

[Current message]
User: Here is the EXPLAIN ANALYZE output:

```
Sort  (cost=89234.. rows=50000)
  ->  HashAggregate  (cost=85000.. rows=50000)
        ->  Hash Left Join  (cost=80000.. rows=1500000)
              Hash Cond: (o.user_id = u.id)
              ->  Seq Scan on orders o  (cost=0.. rows=2000000)
                    Filter: (created_at > '2024-01-01')
                    Rows Removed by Filter: 500000
              ->  Hash  (cost=1000.. rows=50000)
                    ->  Seq Scan on users u  (cost=0.. rows=50000)
```

I see "Seq Scan on orders" -- there is no index on created_at. But I do have an index on orders.user_id.''',
        "output": r'''The EXPLAIN output confirms the problem -- PostgreSQL is doing a sequential scan on all 2 million order rows to filter by created_at. Since you already have an index on user_id, you need a composite index that covers both the join and the filter:

```sql
-- Best index for this query: covers both the WHERE filter and the JOIN
CREATE INDEX CONCURRENTLY idx_orders_created_user
ON orders (created_at, user_id);

-- Alternative: if you query by user_id more often than created_at
CREATE INDEX CONCURRENTLY idx_orders_user_created
ON orders (user_id, created_at);
```

Use CONCURRENTLY to avoid locking the table during index creation on production.

After creating the index, the query plan should show an Index Scan instead of a Seq Scan. But there is also a logic bug in your query: the WHERE clause on o.created_at effectively turns your LEFT JOIN into an INNER JOIN because NULL values from the left join will fail the WHERE filter. If you want users with zero orders to appear with order_count = 0, move the date filter into the JOIN condition:

```sql
SELECT u.name, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON o.user_id = u.id AND o.created_at > '2024-01-01'
GROUP BY u.name
ORDER BY order_count DESC;
```

This should bring the query from 15 seconds down to under 1 second with the new index. Run EXPLAIN ANALYZE again after adding the index to confirm it is being used.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Docker build is failing with this error:

```
Step 6/10 : RUN pip install -r requirements.txt
 ---> Running in abc123
ERROR: Could not find a version that satisfies the requirement torch==2.1.0
ERROR: No matching distribution found for torch==2.1.0
```

My Dockerfile:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```
Assistant: The torch package for the slim image might need specific platform flags. Try adding --extra-index-url for the PyTorch repository. Also check if you are building for the right platform (arm64 vs amd64).

[Current message]
User: I added the extra index URL and torch installs now. But the image is 8 GB! That is way too big for deployment. Can I slim it down?''',
        "output": r'''An 8 GB image with PyTorch is unfortunately common. Since you got torch installing with the extra index URL, here are the strategies to shrink it:

**1. Use CPU-only torch (biggest win -- saves ~4 GB):**

If you do not need GPU in the container, install the CPU-only version:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.1.0+cpu     --extra-index-url https://download.pytorch.org/whl/cpu &&     pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

**2. Multi-stage build (saves another ~1 GB):**

```dockerfile
# Build stage
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install     torch==2.1.0+cpu     --extra-index-url https://download.pytorch.org/whl/cpu &&     pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage -- no pip, no build tools
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
CMD ["python", "app.py"]
```

**3. Add a .dockerignore file:**

```
.git
__pycache__
*.pyc
.env
tests/
docs/
*.md
```

**4. Use --no-cache-dir** on all pip install commands (already shown above) to avoid storing the pip cache in the image layer.

With CPU-only torch and a multi-stage build, you should get the image down to around 2-3 GB. If that is still too large, consider using ONNX Runtime instead of PyTorch for inference -- it is much smaller.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have an async Python function that is supposed to run tasks concurrently but they run one at a time:

```python
import asyncio

async def fetch_data(url):
    print(f"Fetching {url}")
    await asyncio.sleep(2)  # simulating network call
    return f"data from {url}"

async def main():
    urls = ["url1", "url2", "url3", "url4", "url5"]
    results = []
    for url in urls:
        result = await fetch_data(url)
        results.append(result)
    print(results)

asyncio.run(main())
```

This takes 10 seconds instead of 2.
Assistant: The problem is you are awaiting each fetch sequentially in the for loop. Use asyncio.gather() to run them concurrently:

```python
async def main():
    urls = ["url1", "url2", "url3", "url4", "url5"]
    results = await asyncio.gather(*[fetch_data(url) for url in urls])
    print(results)
```

[Current message]
User: That works, it is much faster now. But in production I have 500 URLs and I do not want to fire off 500 network requests at the same time. How do I limit concurrency to, say, 20 at a time?''',
        "output": r'''Since you are already using asyncio.gather for concurrent execution, you can add concurrency control with asyncio.Semaphore:

```python
import asyncio
import aiohttp

async def fetch_data(session, url, semaphore):
    async with semaphore:
        print(f"Fetching {url}")
        async with session.get(url) as response:
            return await response.text()

async def main():
    urls = [f"https://api.example.com/items/{i}" for i in range(500)]

    # Limit to 20 concurrent requests
    semaphore = asyncio.Semaphore(20)

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_data(session, url, semaphore) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Separate successes from failures
    successes = []
    failures = []
    for url, result in zip(urls, results):
        if isinstance(result, Exception):
            failures.append((url, str(result)))
        else:
            successes.append(result)

    print(f"Fetched {len(successes)} successfully, {len(failures)} failed")

asyncio.run(main())
```

The Semaphore acts as a gate -- at most 20 coroutines can enter the `async with semaphore` block at once. The rest wait until a slot opens up. All 500 tasks are created immediately but only 20 run at any given time.

I also added `return_exceptions=True` to gather() so one failed request does not cancel all the others. And I switched from asyncio.sleep to aiohttp for real HTTP requests -- you want to reuse a single ClientSession for connection pooling rather than creating a new one per request.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Node.js Express server keeps crashing with "FATAL ERROR: CALL_AND_RETRY_LAST Allocation failed - JavaScript heap out of memory" after running for a few hours.
Assistant: That is a memory leak. Common causes: growing arrays/maps that never get cleaned up, event listeners being added repeatedly, or unclosed database connections. Try running with --max-old-space-size=4096 as a temporary fix and use the --inspect flag with Chrome DevTools to take heap snapshots.

User: I took two heap snapshots 30 minutes apart. The second one shows 500 MB more retained memory, mostly in "(object properties)" linked to a Map object.

[Current message]
User: I found the leaking Map. It is a session cache:

```javascript
const sessionCache = new Map();

app.use((req, res, next) => {
    const sessionId = req.cookies.session_id;
    if (sessionId && !sessionCache.has(sessionId)) {
        const userData = db.getUserBySession(sessionId);
        sessionCache.set(sessionId, userData);
    }
    req.user = sessionCache.get(sessionId);
    next();
});
```

Sessions get added to the Map but never removed. How do I fix this?''',
        "output": r'''You found the leak -- the Map grows forever because entries are never removed. There are several approaches depending on your needs:

**Option 1 -- Use a TTL cache (recommended):**

```javascript
// npm install lru-cache
const { LRUCache } = require('lru-cache');

const sessionCache = new LRUCache({
    max: 10000,           // Max 10,000 entries
    ttl: 1000 * 60 * 30,  // Expire after 30 minutes
    updateAgeOnGet: true,  // Reset TTL on access (session stays alive while active)
});

app.use(async (req, res, next) => {
    const sessionId = req.cookies.session_id;
    if (!sessionId) {
        return next();
    }
    let userData = sessionCache.get(sessionId);
    if (!userData) {
        userData = await db.getUserBySession(sessionId);
        if (userData) {
            sessionCache.set(sessionId, userData);
        }
    }
    req.user = userData || null;
    next();
});
```

**Option 2 -- Manual cleanup with a timer (no extra dependency):**

```javascript
const sessionCache = new Map();
const SESSION_TTL = 30 * 60 * 1000; // 30 minutes

app.use(async (req, res, next) => {
    const sessionId = req.cookies.session_id;
    if (!sessionId) return next();

    const cached = sessionCache.get(sessionId);
    if (cached && Date.now() - cached.timestamp < SESSION_TTL) {
        req.user = cached.data;
    } else {
        const userData = await db.getUserBySession(sessionId);
        if (userData) {
            sessionCache.set(sessionId, { data: userData, timestamp: Date.now() });
        }
        req.user = userData || null;
    }
    next();
});

// Clean up expired entries every 5 minutes
setInterval(() => {
    const now = Date.now();
    for (const [key, value] of sessionCache) {
        if (now - value.timestamp > SESSION_TTL) {
            sessionCache.delete(key);
        }
    }
}, 5 * 60 * 1000);
```

The LRU cache is better because it also caps the maximum number of entries. Even with TTL, if you get a burst of 100,000 unique sessions in 30 minutes, a plain Map with TTL would still hold them all. The LRU cache evicts the least recently used entries when it hits the max size. You can also remove the --max-old-space-size flag once the leak is fixed.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Python unit test is failing because it tries to call a real external API:

```python
class PaymentService:
    def __init__(self, api_key):
        self.client = StripeClient(api_key=api_key)

    def charge(self, amount, currency, card_token):
        result = self.client.charges.create(
            amount=amount,
            currency=currency,
            source=card_token,
        )
        return {"id": result.id, "status": result.status}
```

```python
def test_charge():
    service = PaymentService("EXAMPLE_KEY_123")
    result = service.charge(1000, "usd", "tok_test")
    assert result["status"] == "succeeded"
```
Assistant: You need to mock the Stripe client so the test does not make real API calls. Use unittest.mock.patch to replace the StripeClient.

[Current message]
User: I tried mocking it but I am getting this error:

```
AttributeError: <MagicMock name='StripeClient().charges.create' id='...'> does not have the attribute 'id'
```

My test:

```python
from unittest.mock import patch, MagicMock

@patch('payment_service.StripeClient')
def test_charge(mock_stripe_cls):
    service = PaymentService("EXAMPLE_KEY_123")
    result = service.charge(1000, "usd", "tok_test")
    assert result["status"] == "succeeded"
```

The mock does not know about .id and .status on the return value.''',
        "output": r'''The issue is that MagicMock auto-creates attributes when accessed, but they return more MagicMock objects instead of the strings you expect. You need to configure the return value of charges.create to have the right attributes:

```python
from unittest.mock import patch, MagicMock

@patch('payment_service.StripeClient')
def test_charge_success(mock_stripe_cls):
    # Configure the mock chain: StripeClient() -> instance -> charges -> create()
    mock_client = MagicMock()
    mock_stripe_cls.return_value = mock_client

    # Set up the return value of charges.create()
    mock_charge_result = MagicMock()
    mock_charge_result.id = "ch_test_123"
    mock_charge_result.status = "succeeded"
    mock_client.charges.create.return_value = mock_charge_result

    service = PaymentService("EXAMPLE_KEY_123")
    result = service.charge(1000, "usd", "tok_test")

    # Verify the result
    assert result["id"] == "ch_test_123"
    assert result["status"] == "succeeded"

    # Verify the mock was called correctly
    mock_client.charges.create.assert_called_once_with(
        amount=1000,
        currency="usd",
        source="tok_test",
    )

@patch('payment_service.StripeClient')
def test_charge_failure(mock_stripe_cls):
    mock_client = MagicMock()
    mock_stripe_cls.return_value = mock_client

    # Simulate API error
    mock_client.charges.create.side_effect = Exception("Card declined")

    service = PaymentService("EXAMPLE_KEY_123")
    try:
        service.charge(1000, "usd", "tok_bad")
        assert False, "Should have raised"
    except Exception as e:
        assert "Card declined" in str(e)
```

The key was setting `mock_client.charges.create.return_value` to a MagicMock with explicit `.id` and `.status` attributes. Without that, the auto-generated MagicMock attributes are just more mock objects, not strings, so your dict construction fails. I also added a failure test case -- always test the error path too.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Docker Compose setup has a web app and a PostgreSQL database, but the app cannot connect to the database. It says "connection refused".

```yaml
version: "3.8"
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: "postgresql://user:pass@localhost:5432/mydb"
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: mydb
    ports:
      - "5432:5432"
```
Assistant: The problem is DATABASE_URL uses localhost. In Docker Compose, each service runs in its own container, so localhost inside the web container refers to itself, not the db container. Change localhost to the service name "db":

DATABASE_URL: "postgresql://user:pass@db:5432/mydb"

[Current message]
User: I changed it to db and now I get a different error:

```
psycopg2.OperationalError: could not connect to server: Connection refused
    Is the server running on host "db" (172.18.0.2) and accepting connections on port 5432?
```

But it resolves to the right IP. The db container shows as "Up" when I run docker compose ps.''',
        "output": r'''The hostname resolves correctly (you can see it found 172.18.0.2) but the connection is still refused. This is a timing issue -- your web container starts before PostgreSQL is ready to accept connections. The db container might show as "Up" but Postgres needs a few seconds to initialize.

**Fix 1 -- Add a healthcheck and depends_on condition:**

```yaml
version: "3.8"
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: "postgresql://user:pass@db:5432/mydb"
    depends_on:
      db:
        condition: service_healthy
    restart: on-failure

  db:
    image: postgres:15
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: mydb
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d mydb"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s
```

**Fix 2 -- Add retry logic in your app (recommended in addition):**

```python
import time
import psycopg2

def connect_with_retry(database_url, max_retries=5, delay=2):
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(database_url)
            print("Database connected")
            return conn
        except psycopg2.OperationalError:
            if attempt < max_retries - 1:
                print(f"DB not ready, retrying in {delay}s (attempt {attempt + 1})")
                time.sleep(delay)
            else:
                raise
```

Use both approaches together. The healthcheck prevents Docker from starting the web service until Postgres is ready. The retry logic in your app handles cases where the connection drops later (network blip, Postgres restart). The `restart: on-failure` policy also helps if the app crashes during startup before retries succeed.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I keep getting TypeErrors in my Python data processing pipeline. The latest:

```
TypeError: unsupported operand type(s) for +: 'float' and 'NoneType'
```

The code:

```python
def calculate_total(items):
    total = 0.0
    for item in items:
        total += item.get("price") * item.get("quantity")
    return total
```

Some items have missing price or quantity fields.
Assistant: The dict.get() method returns None when the key is missing. You need to handle the None case. Quick fix: use a default value: item.get("price", 0).

[Current message]
User: I used defaults and it works. But now my boss says we should not silently default to 0 because that hides data quality issues. If price or quantity is missing, we should log a warning and skip that item. How do I restructure this?''',
        "output": r'''Good call from your boss -- silently defaulting to 0 can mask real problems. Since you are already iterating through items, here is a version that validates, logs, and reports:

```python
import logging

logger = logging.getLogger(__name__)

def calculate_total(items):
    total = 0.0
    skipped = []

    for i, item in enumerate(items):
        price = item.get("price")
        quantity = item.get("quantity")
        item_id = item.get("id", f"index-{i}")

        # Validate both fields
        missing = []
        if price is None:
            missing.append("price")
        if quantity is None:
            missing.append("quantity")

        if missing:
            logger.warning(
                "Skipping item %s: missing fields: %s",
                item_id,
                ", ".join(missing),
            )
            skipped.append({"item_id": item_id, "missing": missing})
            continue

        # Type check
        if not isinstance(price, (int, float)) or not isinstance(quantity, (int, float)):
            logger.warning("Skipping item %s: non-numeric price or quantity", item_id)
            skipped.append({"item_id": item_id, "reason": "non-numeric"})
            continue

        total += price * quantity

    if skipped:
        logger.warning(
            "Skipped %d of %d items due to data quality issues",
            len(skipped),
            len(items),
        )

    return {
        "total": total,
        "items_processed": len(items) - len(skipped),
        "items_skipped": len(skipped),
        "skip_details": skipped,
    }
```

This returns a dict with both the total and details about what was skipped, so the caller can decide how to handle data quality issues. You could also add a `strict` parameter that raises an exception instead of skipping, for batch jobs where you want to halt on bad data. The logging gives you visibility without silently hiding problems.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Django app is really slow on the orders page. It takes 5 seconds to load 100 orders.
Assistant: That is likely an N+1 query problem. Django's ORM lazy-loads related objects, so if you access order.customer or order.items in a loop, it fires a separate query for each one. Use select_related for foreign keys and prefetch_related for many-to-many or reverse foreign keys.

User: I added select_related('customer') and the page loads much faster for customer data. But I also need to show the items in each order, and that is still slow. Each order has multiple items through an OrderItem model.
Assistant: For the many side (OrderItem), use prefetch_related:

```python
orders = Order.objects.select_related('customer').prefetch_related('orderitem_set').all()
```

[Current message]
User: That helped a lot but now I also need to show the product name for each order item. OrderItem has a foreign key to Product. I tried:

```python
orders = Order.objects.select_related('customer').prefetch_related('orderitem_set').all()
```

But accessing item.product.name in the template still fires extra queries. How do I prefetch the nested relationship?''',
        "output": r'''Since you already have select_related for customer and prefetch_related for orderitem_set, you need to add the nested Product lookup to the prefetch. Use a Prefetch object to customize the queryset:

```python
from django.db.models import Prefetch

orders = Order.objects.select_related(
    'customer'
).prefetch_related(
    Prefetch(
        'orderitem_set',
        queryset=OrderItem.objects.select_related('product'),
    )
).all()[:100]
```

This results in exactly 3 queries regardless of how many orders you have:
1. SELECT orders with customer (JOIN)
2. SELECT order_items WHERE order_id IN (...) with product (JOIN)
3. That is it -- no N+1

In your template you can now safely do:

```
{% for order in orders %}
  Customer: {{ order.customer.name }}
  {% for item in order.orderitem_set.all %}
    Product: {{ item.product.name }} x {{ item.quantity }}
  {% endfor %}
{% endfor %}
```

You can verify the query count in development using django-debug-toolbar, or in tests:

```python
from django.test.utils import override_settings

def test_order_list_query_count(self):
    with self.assertNumQueries(2):
        orders = list(
            Order.objects.select_related('customer')
            .prefetch_related(
                Prefetch(
                    'orderitem_set',
                    queryset=OrderItem.objects.select_related('product'),
                )
            )
            .all()[:100]
        )
        # Force evaluation of prefetch
        for order in orders:
            list(order.orderitem_set.all())
```

The Prefetch object is the key -- it lets you attach select_related to the prefetched queryset, which is how you handle nested relationships without extra queries.'''
    },
]
