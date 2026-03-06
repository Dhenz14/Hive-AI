"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 1)

The model asks ITSELF probing questions during reasoning to challenge
assumptions, check blind spots, and improve solution quality.
"""

PAIRS = [
    (
        "thinking/meta-socratic-right-problem-csv-parser",
        r'''I need to parse a CSV file with 10 million rows in Python. Can you write a fast CSV parser?''',
        r'''<think>
My initial approach: Write a custom CSV parser using string splitting for maximum speed.

Wait — let me challenge my assumptions:

Q: Am I solving the right problem? The user said "parse a CSV file" — do they actually need a custom parser?
A: Python has csv.reader and pandas.read_csv. Writing a custom parser is almost certainly wrong — these libraries handle quoting, escaping, encoding issues that a naive split(",") will miss. The user probably wants to PROCESS a large CSV, not write a parser from scratch.

Q: What does "fast" actually mean here? Is the bottleneck parsing or processing?
A: For 10M rows, the bottleneck is usually memory (loading all rows at once) and I/O (disk read speed), not the parsing logic itself. A "fast parser" that loads everything into memory will crash on a 32GB machine if rows are wide.

Q: Should I even load all 10M rows at once?
A: Probably not. Streaming/chunked reading is almost always the right approach for large files. pandas.read_csv has a chunksize parameter for this.

Q: What about the data types? Does the user need all columns?
A: Selecting only needed columns (usecols) and specifying dtypes can reduce memory 5-10x. This matters more than parser speed.

So the real problem isn't "write a fast parser" — it's "efficiently process a large CSV with appropriate memory management."
</think>

You don't need a custom parser — Python's existing tools handle this well. The key is **memory management**, not parsing speed.

**For processing 10M rows efficiently:**

```python
import pandas as pd

# Option 1: Chunked processing (constant memory)
for chunk in pd.read_csv('large.csv', chunksize=100_000):
    process(chunk)  # Only 100K rows in memory at a time

# Option 2: Select only needed columns + optimize dtypes
df = pd.read_csv('large.csv',
    usecols=['id', 'amount', 'status'],  # Skip unneeded columns
    dtype={'id': 'int32', 'amount': 'float32', 'status': 'category'}
)
```

**If you don't need pandas:**

```python
import csv

with open('large.csv') as f:
    reader = csv.reader(f)
    header = next(reader)
    for row in reader:  # Streams — constant memory
        process(row)
```

**What actually makes CSV processing fast:**
1. **Read only needed columns** — `usecols` skips parsing unused data
2. **Specify dtypes** — avoids expensive type inference on 10M rows
3. **Stream, don't load** — `chunksize` or `csv.reader` iterator
4. **Consider Polars** — `polars.read_csv()` is 5-10x faster than pandas for large files

Writing a custom CSV parser would be slower, buggier, and miss edge cases (quoted fields, embedded newlines, encoding).'''
    ),
    (
        "thinking/meta-socratic-right-problem-rate-limiter",
        r'''Our API is getting too many requests. Can you implement a rate limiter middleware for our Flask app?''',
        r'''<think>
My initial approach: Build a token bucket rate limiter in Flask middleware using Redis.

Wait — let me challenge my assumptions:

Q: Am I solving the right problem? WHY is the API getting too many requests?
A: "Too many requests" could mean several different things:
  - Legitimate traffic growth → need to scale, not rate limit
  - A single abusive client → need per-client rate limiting
  - A DDoS attack → need infrastructure-level protection (WAF, CDN), not app-level
  - Poorly designed client retry logic → need backoff, not rate limiting
  - A bot scraping → need bot detection + rate limiting

The solution depends entirely on which scenario this is.

Q: Should rate limiting happen at the application level at all?
A: For DDoS or high-volume abuse, app-level rate limiting is too late — requests already hit your server. Nginx, Cloudflare, or AWS WAF should handle this. App-level rate limiting is for business logic limits (API quotas, per-user fairness).

Q: Is there an existing solution I should use instead of building from scratch?
A: flask-limiter is a well-maintained library that handles all the edge cases. Building a custom rate limiter means handling: distributed state (multiple app instances), race conditions, sliding windows vs fixed windows, header responses (429 + Retry-After), and per-route vs per-user limits.

Q: If I build it, what storage backend should I use?
A: Redis is the standard choice for distributed rate limiting. In-memory (dict) fails with multiple app instances. But do they even have multiple instances? If it's a single server, in-memory works.

Let me refocus: recommend the right tool for the scenario, not jump to building a custom solution.
</think>

Before building a rate limiter, let's identify the right solution for your situation:

**If it's a DDoS or high-volume attack** — don't solve this in Flask:
- Use Cloudflare, AWS WAF, or Nginx rate limiting
- App-level rate limiting can't protect you if requests saturate your server

**If you need API quotas / per-user fairness** — use flask-limiter:

```python
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per minute"],
    storage_uri="redis://localhost:6379"  # Required for multi-instance
)

@app.route("/api/data")
@limiter.limit("30 per minute")  # Stricter limit for expensive endpoint
def get_data():
    return {"data": "..."}

@app.route("/api/search")
@limiter.limit("10 per minute")
def search():
    return {"results": []}
```

**Why flask-limiter over custom code:**
- Handles Redis/Memcached backends for distributed deployments
- Proper 429 responses with `Retry-After` headers
- Multiple rate limit strategies (fixed window, sliding window, token bucket)
- Per-route, per-user, and global limits
- Well-tested edge cases you'd otherwise miss

**If a single client is abusing your API:**
```python
# Identify and block the specific client
@limiter.limit("5 per minute", key_func=lambda: request.headers.get("X-API-Key"))
```

**Quick wins before building anything:**
1. Check your logs — is it one IP or many?
2. If one IP: block it at Nginx/firewall level
3. If a retry storm: fix the client's retry logic (exponential backoff)
4. If legitimate growth: scale your infrastructure'''
    ),
    (
        "thinking/meta-socratic-data-assumption-sort",
        r'''I need to find the top 10 most expensive products from our database. Should I sort all products by price and take the first 10?''',
        r'''<think>
My initial approach: SELECT * FROM products ORDER BY price DESC LIMIT 10

Wait — let me challenge my assumptions:

Q: Does my assumption about the data hold? What if there are NULL prices?
A: If price can be NULL, ORDER BY behavior varies by database. In PostgreSQL, NULLs sort last in DESC by default, which is fine. In MySQL, NULLs sort first, which would put NULL-priced items in the "top 10." Need to check or use NULLS LAST.

Q: What does "most expensive" mean? Current price? Historical highest? Including discounts?
A: The user said "most expensive products" which probably means current listed price. But if there's a sale_price or discount column, we might want the effective price, not the sticker price.

Q: Should I sort ALL products to get the top 10?
A: In SQL, ORDER BY + LIMIT is fine — the database optimizer handles this efficiently with a top-N sort (no need to sort the entire table). But in application code, sorting a list of 1M products to get top 10 is wasteful — use heapq.nlargest or a partial sort.

Q: Is there an index on price?
A: If there's an index on price, the query is instant — just read 10 rows from the index. Without an index, it's a full table scan + sort. For a products table that's queried this way regularly, an index is worth adding.

Q: Are there ties? What if 5 products have the same highest price?
A: Need a tiebreaker. ORDER BY price DESC, id ASC gives deterministic results. Without a tiebreaker, results can vary between queries.

Q: What about products that shouldn't be shown — deleted, draft, out of stock?
A: Need WHERE is_active = true or similar filter. "Top 10" presumably means top 10 visible, purchasable products.

These data assumption checks changed my answer significantly.
</think>

Yes, `ORDER BY price DESC LIMIT 10` is the right SQL approach — but there are important details:

```sql
SELECT id, name, price
FROM products
WHERE is_active = true           -- Don't include draft/deleted products
  AND price IS NOT NULL           -- Exclude products without prices
ORDER BY price DESC, id ASC       -- Tiebreaker for deterministic results
LIMIT 10;
```

**Key considerations I checked:**

1. **NULL prices**: Without `price IS NOT NULL`, NULLs may appear in your top 10 (database-dependent)
2. **Inactive products**: Filter to only show purchasable items
3. **Tiebreaker**: `id ASC` ensures consistent results when prices are equal
4. **Index**: Add one if this query runs frequently:
   ```sql
   CREATE INDEX idx_products_price ON products (price DESC) WHERE is_active = true;
   ```

**If doing this in Python** (not SQL), don't sort the full list:

```python
import heapq

# O(n log 10) instead of O(n log n) full sort
top_10 = heapq.nlargest(10, products, key=lambda p: p.price)
```

**If you need "effective price" after discounts:**
```sql
SELECT id, name, price, sale_price,
       COALESCE(sale_price, price) AS effective_price
FROM products
WHERE is_active = true
ORDER BY effective_price DESC
LIMIT 10;
```'''
    ),
    (
        "thinking/meta-socratic-data-assumption-user-input",
        r'''I'm building a registration form. I need to validate that the user's age is between 18 and 120. Here's my code:

```python
def validate_age(age_str):
    age = int(age_str)
    if age < 18 or age > 120:
        raise ValueError("Age must be between 18 and 120")
    return age
```

Is this correct?''',
        r'''<think>
My initial approach: The logic looks right — converts to int, checks range 18-120.

Wait — let me challenge my assumptions:

Q: Does my assumption about the input data hold? What if age_str isn't a number?
A: int("abc") throws ValueError, but with a confusing message like "invalid literal for int()". The user would see a Python error, not a friendly validation message. Need to catch the conversion error separately.

Q: What if the input is a float like "25.5"?
A: int("25.5") raises ValueError too. Should we accept it and truncate, or reject it? For age, truncating seems reasonable — int(float("25.5")) = 25.

Q: What if the input is empty or None?
A: int("") raises ValueError. int(None) raises TypeError. Both cases need handling.

Q: What if there are leading/trailing spaces? "  25  "?
A: Actually, int("  25  ") works fine in Python — it strips whitespace. So this is handled.

Q: What about negative numbers or zero?
A: int("-5") = -5, which is caught by the < 18 check. But the error message "between 18 and 120" is misleading for negative input — "please enter a valid age" would be better.

Q: Is 120 the right upper bound?
A: The oldest verified person was 122. 120 is reasonable but arbitrary. More importantly — does the business logic actually require age validation? Many services just need "18 or older" verification, not exact age.

Q: What about leading zeros? "007"?
A: int("007") = 7, which works correctly.

Q: Security concern — could this be used for injection?
A: int() conversion is safe against injection. But if this value goes into a database, make sure it's parameterized.

Multiple issues found with the "correct-looking" code.
</think>

The range logic is correct, but the input handling has several gaps:

```python
def validate_age(age_str):
    if age_str is None:
        raise ValueError("Age is required")

    # Handle string input safely
    try:
        age = int(age_str)
    except (ValueError, TypeError):
        raise ValueError("Age must be a whole number")

    if age < 18:
        raise ValueError("You must be at least 18 years old")
    if age > 120:
        raise ValueError("Please enter a valid age")

    return age
```

**Issues in the original:**

1. **`int("abc")` crashes** with an unhelpful Python error instead of a user-friendly message
2. **`int(None)` raises TypeError** — not caught by the implicit conversion
3. **`int("")` raises ValueError** — same confusing error
4. **Single error message** for all failures — "between 18 and 120" is unhelpful for "abc" input
5. **`int("25.5")` fails** — may want to handle decimal input:
   ```python
   age = int(float(age_str))  # Accept "25.5" as 25
   ```

**The fix addresses each input scenario:**
- None/empty → "Age is required"
- Non-numeric → "Age must be a whole number"
- Under 18 → "You must be at least 18"
- Over 120 → "Please enter a valid age"

The range logic was fine — it's the boundary between untrusted input and your code that needed hardening.'''
    ),
    (
        "thinking/meta-socratic-simplest-solution-cache",
        r'''I need to cache API responses in my Flask app. I'm thinking of using Redis with a decorator pattern, custom serialization, cache invalidation on writes, and a TTL-based eviction policy. Can you help me implement this?''',
        r'''<think>
My initial approach: Build a Redis caching decorator with JSON serialization, key generation from function args, TTL, and invalidation hooks.

Wait — let me challenge my assumptions:

Q: Is this the simplest solution? Does this Flask app actually need Redis caching?
A: The user jumped straight to a complex architecture. Let me ask: How much traffic does this app get? What's the response time of the API calls being cached? Is the app running on a single server?

Q: What if a simple in-memory cache is enough?
A: For a single-server Flask app, functools.lru_cache or cachetools.TTLCache gives you caching with zero infrastructure. Redis adds a network dependency, connection management, serialization overhead, and operational burden.

Q: When does Redis become necessary?
A: Only when:
  - Multiple app instances need to share the cache
  - Cache needs to survive app restarts
  - Cache is large enough that it would bloat app memory
  - You need fine-grained invalidation across instances

Q: Is the custom serialization necessary?
A: flask-caching handles all of this already — Redis backend, TTL, decorators. Building custom serialization is reinventing the wheel.

Q: Am I anchored on the user's complex solution?
A: Yes. The user described a solution, not a problem. Let me focus on what they're trying to achieve (faster API responses) and recommend the simplest thing that works.

Q: What's the simplest progression?
A: 1. In-memory TTL cache (zero deps) → 2. flask-caching with simple backend → 3. flask-caching with Redis → 4. Custom Redis solution. Start at step 1, only advance when you hit a real limitation.

The user is over-engineering. Start simple.
</think>

Before building a Redis caching system, let's start with the simplest thing that works and scale up only if needed.

**Level 1 — In-memory TTL cache (zero dependencies):**

```python
from cachetools import TTLCache

cache = TTLCache(maxsize=1000, ttl=300)  # 1000 items, 5 min TTL

@app.route("/api/products")
def get_products():
    if "products" in cache:
        return cache["products"]
    result = fetch_from_external_api()
    cache["products"] = result
    return result
```

This is enough if:
- Single server instance
- Cache fits in memory (< 100MB)
- Cache loss on restart is acceptable

**Level 2 — flask-caching (if you need more):**

```python
from flask_caching import Cache

cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})  # In-memory
# OR: config={'CACHE_TYPE': 'RedisCache', 'CACHE_REDIS_URL': 'redis://...'}

@app.route("/api/products")
@cache.cached(timeout=300)
def get_products():
    return fetch_from_external_api()

# Invalidation:
@app.route("/api/products", methods=["POST"])
def create_product():
    save_product(request.json)
    cache.delete("view//api/products")
    return {"status": "created"}, 201
```

**Level 3 — Redis (only when needed):**
Switch `CACHE_TYPE` to `RedisCache` — same code, just a config change.

**You need Redis caching when:**
- Multiple app instances (load balancer)
- Cache > 100MB
- Cache must survive deploys
- Need cache sharing between services

**You DON'T need Redis when:**
- Single instance Flask app
- Small cache (< 1000 items)
- Short TTLs (minutes, not hours)

Start at Level 1. Promote to Redis only when you hit a real limitation.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
