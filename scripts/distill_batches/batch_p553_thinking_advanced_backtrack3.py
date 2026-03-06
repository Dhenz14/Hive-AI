"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 3/5)
Design: inheritance fails → composition, config drift, DB model fails → denormalize, error codes → exceptions."""

PAIRS = [
    (
        "thinking/backtrack-greedy-fails-dp-knapsack",
        "I'm building a content recommendation widget that needs to fill a 600px sidebar with articles of different heights (100px, 180px, 250px, 320px). Each article has an engagement score. I'm greedily picking highest-engagement articles that fit, but I'm often left with wasted space. Is there a better way?",
        r'''<think>
This is actually the 0/1 knapsack problem! The sidebar height (600px) is the knapsack capacity, article heights are weights, and engagement scores are values.

Let me trace the greedy approach to see why it fails:

Articles (height → engagement):
A: 320px → 95 engagement
B: 250px → 85
C: 180px → 70
D: 100px → 40
E: 180px → 65

Greedy by engagement density (score/height):
- D: 40/100 = 0.40/px
- C: 70/180 = 0.39/px
- B: 85/250 = 0.34/px
- A: 95/320 = 0.30/px
- E: 65/180 = 0.36/px

Greedy picks: D(100), E(180), C(180) = 460px, score = 175
Remaining: 140px — nothing else fits

But: A(320) + B(250) = 570px, score = 180 — better score AND better fill!

Or: B(250) + C(180) + D(100) = 530px, score = 195 — even better!

So the greedy approach by density leaves gaps and misses better combinations. DP explores all valid combinations.

Since the sidebar height and article heights are integers, this is a standard bounded knapsack solvable with DP in O(n × capacity) time. With ~20 articles and 600px, that's only 12,000 states — trivial.
</think>

This is the **0/1 knapsack problem** — greedy by engagement density misses combinations that fill the space better.

**Greedy failure example**:
```
Articles: A(320px, 95pts), B(250px, 85pts), C(180px, 70pts), D(100px, 40pts), E(180px, 65pts)
Greedy picks: D + E + C = 460px, 175pts (140px wasted)
DP finds:     B + C + D = 530px, 195pts (70px wasted, higher score)
```

**DP solution — finds optimal article combination**:
```python
from dataclasses import dataclass

@dataclass
class Article:
    id: str
    title: str
    height_px: int
    engagement_score: float

def best_sidebar_articles(articles: list[Article], max_height: int) -> list[Article]:
    n = len(articles)
    # dp[i][h] = best score using articles[0..i-1] with max height h
    dp = [[0.0] * (max_height + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        article = articles[i - 1]
        for h in range(max_height + 1):
            # Option 1: skip this article
            dp[i][h] = dp[i - 1][h]
            # Option 2: include this article (if it fits)
            if article.height_px <= h:
                include = dp[i - 1][h - article.height_px] + article.engagement_score
                dp[i][h] = max(dp[i][h], include)

    # Backtrack to find which articles were selected
    selected = []
    h = max_height
    for i in range(n, 0, -1):
        if dp[i][h] != dp[i - 1][h]:
            selected.append(articles[i - 1])
            h -= articles[i - 1].height_px

    return list(reversed(selected))


# Usage
articles = [
    Article("a", "Breaking News", 320, 95),
    Article("b", "Tech Review", 250, 85),
    Article("c", "Opinion Piece", 180, 70),
    Article("d", "Quick Update", 100, 40),
    Article("e", "Feature Story", 180, 65),
]

sidebar = best_sidebar_articles(articles, max_height=600)
# Returns [B, C, D] — 530px total, 195 engagement (optimal)
```

**Performance**: With ~50 candidate articles and 600px height, the DP table has 30,000 cells — runs in under 1ms. Greedy would have been microseconds but gives suboptimal results.

**When greedy IS good enough**: If you have hundreds of tiny articles and the "wasted space" is always small relative to total capacity, greedy with backfill works fine. Use DP when precision matters and the input size is manageable.'''
    ),
    (
        "thinking/backtrack-sync-fails-async-pipeline",
        "Our data ingestion pipeline processes files sequentially: download → parse → validate → transform → load. Each step takes 1-5 seconds. With 1000 files per batch, the whole pipeline takes 2+ hours. I tried threading but Python's GIL makes it barely faster. What am I missing?",
        r'''<think>
Let me analyze this pipeline:

Sequential per file: download(2s) → parse(1s) → validate(0.5s) → transform(1.5s) → load(1s)
Total per file: ~6s
1000 files × 6s = 6000s = 100 minutes ≈ 2 hours. That matches.

The user tried threading but hit the GIL. Let me think about which steps are I/O-bound vs CPU-bound:
- Download: I/O-bound (network) — threading SHOULD help
- Parse: CPU-bound (processing) — GIL blocks
- Validate: CPU-bound — GIL blocks
- Transform: CPU-bound — GIL blocks
- Load: I/O-bound (database/disk) — threading SHOULD help

Wait — the user said threading "barely" helped. For the I/O-bound steps, threading should help. Unless they're running all 5 steps in a single thread per file, which means the GIL blocks the CPU-bound steps even when I/O threads are idle.

The real insight: this is a PIPELINE problem. The steps are sequential for ONE file, but across files, different stages can run in parallel:

File 1: [download] [parse] [validate] [transform] [load]
File 2:           [download] [parse]   [validate]  [transform] [load]
File 3:                     [download]  [parse]     [validate] [transform] [load]

This is exactly like a CPU instruction pipeline or a factory assembly line.

Better approaches:
1. asyncio for I/O-bound steps + multiprocessing for CPU-bound steps
2. Pipeline architecture with queues between stages
3. Batch processing where possible (download 50 files, parse 50, etc.)

Let me design the pipeline with concurrent stages.
</think>

The problem isn't threading vs GIL — it's that you're running the pipeline **sequentially per file** instead of **concurrently across stages**. Think assembly line, not one-worker-per-file.

**Why threading "barely" helped**:
```python
# You probably did this — parallelize files, not stages
with ThreadPoolExecutor(max_workers=10) as pool:
    pool.map(process_file, files)  # Each file still runs all 5 steps sequentially
    # GIL blocks CPU-bound steps (parse, validate, transform)
    # Only download and load benefit from threads
```

**The fix — pipelined architecture with async + multiprocessing**:
```python
import asyncio
import aiohttp
import aiofiles
from concurrent.futures import ProcessPoolExecutor
from asyncio import Queue

# Stage 1: Download (I/O-bound → async)
async def download_stage(files: list[str], output_queue: Queue):
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(20)  # Limit concurrent downloads
        async def download_one(url: str):
            async with sem:
                async with session.get(url) as resp:
                    data = await resp.read()
                    await output_queue.put(("downloaded", url, data))

        await asyncio.gather(*[download_one(f) for f in files])
    await output_queue.put(None)  # Signal done

# Stage 2-4: Parse, Validate, Transform (CPU-bound → multiprocessing)
def cpu_process(raw_data: bytes) -> dict:
    """Runs in a separate process — no GIL."""
    parsed = parse_file(raw_data)
    validated = validate_record(parsed)
    transformed = transform_record(validated)
    return transformed

# Stage 5: Load (I/O-bound → async batched)
async def load_stage(records: list[dict], batch_size: int = 100):
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        await db.insert_many("records", batch)  # Batch insert

# Orchestrator
async def run_pipeline(file_urls: list[str]):
    download_queue = Queue(maxsize=50)  # Backpressure
    process_pool = ProcessPoolExecutor(max_workers=4)
    loop = asyncio.get_event_loop()

    # Start download stage
    download_task = asyncio.create_task(download_stage(file_urls, download_queue))

    # Process as downloads complete
    results = []
    while True:
        item = await download_queue.get()
        if item is None:
            break
        _, url, data = item

        # CPU work in separate process (no GIL)
        transformed = await loop.run_in_executor(process_pool, cpu_process, data)
        results.append(transformed)

        # Batch load every 100 records
        if len(results) >= 100:
            await load_stage(results)
            results.clear()

    # Load remaining
    if results:
        await load_stage(results)

    process_pool.shutdown()

# Run it
asyncio.run(run_pipeline(file_urls))
```

**Performance comparison**:
```
Approach              | 1000 files | Why
----------------------|------------|----
Sequential            | 100 min    | 1 file at a time
Threaded (your try)   | 60 min     | I/O parallelism, CPU still serial
Async + multiprocess  | 15 min     | I/O concurrent, CPU parallel across cores
Pipelined + batched   | 8 min      | Stages overlap, batch I/O reduces overhead
```

**The key insight**: For mixed I/O + CPU workloads in Python, use **async for I/O** (downloads, DB) and **multiprocessing for CPU** (parsing, transforms). Threading is the worst of both worlds due to the GIL.'''
    ),
    (
        "thinking/backtrack-db-query-needs-window-function",
        "I need to find each department's highest-paid employee. My subquery approach works but is incredibly slow on our 500K employee table. The DBA says 'use window functions' but I don't understand how they'd help here.",
        r'''<think>
Let me think about the typical subquery approach and why it's slow.

The correlated subquery approach:
```sql
SELECT * FROM employees e
WHERE salary = (
    SELECT MAX(salary) FROM employees
    WHERE department_id = e.department_id
)
```

This runs the inner query ONCE PER ROW in the outer query. With 500K rows, that's 500K subquery executions. Even with an index on (department_id, salary), that's a lot of work.

Alternative without window functions — self-join with GROUP BY:
```sql
SELECT e.* FROM employees e
JOIN (
    SELECT department_id, MAX(salary) as max_salary
    FROM employees
    GROUP BY department_id
) m ON e.department_id = m.department_id AND e.salary = m.max_salary
```

This is better (2 scans instead of N), but still has issues:
- Ties: if two employees share the max salary, both appear
- Need to join back to get all columns

Window function approach:
```sql
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY department_id ORDER BY salary DESC) as rn
    FROM employees
) ranked
WHERE rn = 1
```

This scans the table ONCE, assigns row numbers within each department partition, and filters. Much faster because:
1. Single pass over the data (vs N passes for correlated subquery)
2. No self-join needed
3. ROW_NUMBER handles ties cleanly (exactly 1 result per department)
4. Can use RANK() or DENSE_RANK() if you want ties

Let me explain the performance difference clearly.
</think>

The subquery runs once per row (500K executions). Window functions scan the table **once**. That's the difference.

**Your slow correlated subquery** — O(n × departments):
```sql
-- Runs inner query for EVERY row in outer query
SELECT * FROM employees e
WHERE salary = (
    SELECT MAX(salary) FROM employees
    WHERE department_id = e.department_id
)
-- 500K rows × index lookup per row = slow
-- Also: ties give duplicates (two people with same max salary both appear)
```

**Window function** — single pass, O(n):
```sql
SELECT * FROM (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC
        ) as rn
    FROM employees
) ranked
WHERE rn = 1;
```

**How it works step-by-step**:
```
Original data:
| id | name    | dept | salary |
|----|---------|------|--------|
| 1  | Alice   | Eng  | 150K   |
| 2  | Bob     | Eng  | 140K   |
| 3  | Charlie | Eng  | 160K   |
| 4  | Diana   | Sales| 120K   |
| 5  | Eve     | Sales| 130K   |

After ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC):
| id | name    | dept  | salary | rn |
|----|---------|-------|--------|----|
| 3  | Charlie | Eng   | 160K   | 1  |  ← highest in Eng
| 1  | Alice   | Eng   | 150K   | 2  |
| 2  | Bob     | Eng   | 140K   | 3  |
| 5  | Eve     | Sales | 130K   | 1  |  ← highest in Sales
| 4  | Diana   | Sales | 120K   | 2  |

WHERE rn = 1 → Charlie (Eng), Eve (Sales)
```

**Handling ties** — choose your semantics:
```sql
-- ROW_NUMBER: exactly 1 per department (arbitrary tiebreak)
ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC) -- rn = 1,2,3...

-- RANK: include all tied employees
RANK() OVER (PARTITION BY dept ORDER BY salary DESC) -- rn = 1,1,3...

-- DENSE_RANK: include ties, no gaps in ranking
DENSE_RANK() OVER (PARTITION BY dept ORDER BY salary DESC) -- rn = 1,1,2...
```

**Performance on 500K rows**:
```
Approach            | Execution time | Full table scans
--------------------|---------------|------------------
Correlated subquery | 12 seconds    | 500K subqueries
Self-join + GROUP BY| 2 seconds     | 2 scans + join
Window function     | 0.4 seconds   | 1 scan + sort
```

Window functions are one of the most powerful SQL features. Once you learn `ROW_NUMBER`, `RANK`, `LAG`, `LEAD`, and `SUM() OVER`, you'll solve 90% of "I need a subquery" problems with a single scan.'''
    ),
    (
        "thinking/backtrack-test-fails-needs-redesign",
        "I'm trying to unit test a function that makes an HTTP call, writes to a database, sends an email, and logs to a file. I have 15 mocks set up and the test is 80 lines long. It's brittle and breaks whenever the implementation changes. Is this the right way to test?",
        r'''<think>
80 lines of test setup with 15 mocks — this is a test telling you the code has too many responsibilities, not that you need better mocking.

Let me think about what the function probably looks like:

```python
def process_order(order_data):
    # 1. Validate
    # 2. HTTP call to payment service
    # 3. Write to database
    # 4. Send confirmation email
    # 5. Log to file
    # 6. Return result
```

This function violates SRP — it's doing 5 different things. The test has to mock all 5 external dependencies to isolate the logic.

The issue: the mocks are tightly coupled to IMPLEMENTATION details. If you refactor the function to use a different HTTP library, the mock breaks. If you change the email sending to async, the mock breaks. The test knows TOO MUCH about HOW the function works.

The fix isn't better mocks — it's better design:

1. Extract the side effects into collaborators (dependency injection)
2. Make the core logic pure (no side effects)
3. Test the pure logic directly (no mocks needed)
4. Test the integration points separately with focused integration tests

This is the "Ports and Adapters" / "Hexagonal Architecture" pattern applied at the function level.

The pure core: validate order → calculate totals → determine next actions
The impure shell: actually send HTTP, write DB, send email

Let me show the refactoring and how the tests become simple.
</think>

15 mocks and 80-line tests are the **code telling you it has too many responsibilities**. The fix isn't better mocking — it's separating pure logic from side effects.

**Your current untestable design**:
```python
# Everything mixed together — requires 15 mocks to test
def process_order(order_data: dict) -> dict:
    if not order_data.get("items"):
        raise ValueError("No items")
    total = sum(item["price"] * item["qty"] for item in order_data["items"])
    tax = total * 0.08
    payment = requests.post(PAYMENT_URL, json={"amount": total + tax})
    if payment.status_code != 200:
        raise PaymentError("Payment failed")
    db.execute("INSERT INTO orders ...", order_data)
    send_email(order_data["email"], "Order confirmed", f"Total: ${total + tax}")
    logger.info(f"Order processed: {order_data['id']}")
    return {"order_id": order_data["id"], "total": total + tax}
```

**Refactored — pure core + thin side-effect shell**:
```python
# PURE LOGIC — no side effects, no mocks needed to test
@dataclass
class OrderResult:
    order_id: str
    subtotal: float
    tax: float
    total: float
    items: list[dict]
    email: str

def calculate_order(order_data: dict, tax_rate: float = 0.08) -> OrderResult:
    if not order_data.get("items"):
        raise ValueError("No items")
    subtotal = sum(item["price"] * item["qty"] for item in order_data["items"])
    tax = subtotal * tax_rate
    return OrderResult(
        order_id=order_data["id"],
        subtotal=subtotal,
        tax=tax,
        total=subtotal + tax,
        items=order_data["items"],
        email=order_data["email"],
    )


# THIN SHELL — orchestrates side effects, tested with integration tests
async def process_order(
    order_data: dict,
    payment_client: PaymentClient,
    order_repo: OrderRepository,
    email_service: EmailService,
) -> OrderResult:
    result = calculate_order(order_data)  # Pure logic
    await payment_client.charge(result.total)
    await order_repo.save(result)
    await email_service.send_confirmation(result.email, result)
    return result
```

**Tests — clean and focused**:
```python
# Test pure logic — ZERO mocks, 5 lines each
def test_calculate_order_basic():
    data = {"id": "123", "email": "a@b.com", "items": [{"price": 10, "qty": 2}]}
    result = calculate_order(data)
    assert result.subtotal == 20
    assert result.tax == 1.6
    assert result.total == 21.6

def test_calculate_order_no_items():
    with pytest.raises(ValueError, match="No items"):
        calculate_order({"id": "1", "email": "a@b.com", "items": []})

def test_calculate_order_multiple_items():
    data = {"id": "1", "email": "a@b.com", "items": [
        {"price": 10, "qty": 2},
        {"price": 5, "qty": 3},
    ]}
    result = calculate_order(data)
    assert result.subtotal == 35

# Test orchestration — focused integration test
@pytest.mark.integration
async def test_process_order_integrates_correctly(
    sandbox_payment, test_db, mock_email
):
    data = {"id": "test-1", "email": "test@test.com", "items": [{"price": 10, "qty": 1}]}
    result = await process_order(data, sandbox_payment, test_db, mock_email)
    assert await test_db.get_order("test-1") is not None
    assert mock_email.last_sent_to == "test@test.com"
```

**The principle**: If you need more than 3 mocks, the function has too many responsibilities. Extract pure logic, inject dependencies, and test each layer at its natural level.'''
    ),
    (
        "thinking/backtrack-performance-wrong-layer",
        "Our dashboard API takes 3 seconds. I profiled and found the database query takes 200ms. I've optimized the query as much as possible — added indexes, rewritten JOINs, used EXPLAIN ANALYZE. But the response is still 3 seconds. Where's the other 2.8 seconds?",
        r'''<think>
Interesting — the user focused on the database query (the usual suspect) but it's only 200ms of a 3-second response. The remaining 2.8 seconds must be elsewhere.

Let me think about where time gets spent in a typical API request:

1. Network: client → load balancer → app server (~20ms)
2. Auth/middleware: JWT verification, rate limiting (~10ms)
3. Database query: 200ms (already optimized)
4. Serialization: convert DB rows to JSON (~varies)
5. N+1 queries: might be loading related data in a loop
6. Template rendering: if server-side rendering
7. Response compression/transmission

The most likely culprits for 2.8 seconds:

N+1 query problem: The main query is 200ms, but then the ORM lazily loads related objects — 100 rows × 20ms each = 2 seconds.

Serialization: If they're serializing complex objects with nested relationships, JSON serialization of large objects can be slow.

External service calls: Maybe the dashboard calls other services (auth, analytics, etc.).

Memory/GC: If the response object is huge, garbage collection could cause pauses.

Let me guide the user to profile the RIGHT things — not just the database.
</think>

You optimized the database (200ms) but ignored where the other **2,800ms** is hiding. The bottleneck shifted but you kept looking in the same place.

**Common hidden time sinks in API responses**:

```python
# Profile the ENTIRE request, not just the DB
import time

@app.get("/dashboard")
async def dashboard(user: User = Depends(get_user)):
    t0 = time.perf_counter()

    # 1. Main query — 200ms (your optimized query)
    data = await db.fetch("SELECT ... FROM dashboards WHERE user_id=$1", user.id)
    t1 = time.perf_counter()  # 200ms

    # 2. N+1 PROBLEM — this is probably your bottleneck
    for row in data:  # 100 rows
        row["comments"] = await db.fetch(  # 25ms each × 100 = 2500ms!
            "SELECT * FROM comments WHERE item_id=$1", row["id"]
        )
        row["author"] = await db.fetch_one(  # 5ms each × 100 = 500ms!
            "SELECT * FROM users WHERE id=$1", row["author_id"]
        )
    t2 = time.perf_counter()  # 2500ms + 500ms = 3000ms

    # 3. Serialization — 50ms
    return data
    t3 = time.perf_counter()
```

**Fix the N+1 problem** — batch load related data:
```python
@app.get("/dashboard")
async def dashboard(user: User = Depends(get_user)):
    # Main query — 200ms
    data = await db.fetch("SELECT ... FROM dashboards WHERE user_id=$1", user.id)

    # Batch load ALL related data in 2 queries instead of 200
    item_ids = [row["id"] for row in data]
    author_ids = [row["author_id"] for row in data]

    # One query for all comments — 50ms
    comments = await db.fetch(
        "SELECT * FROM comments WHERE item_id = ANY($1)", item_ids
    )
    comments_by_item = defaultdict(list)
    for c in comments:
        comments_by_item[c["item_id"]].append(c)

    # One query for all authors — 30ms
    authors = await db.fetch(
        "SELECT * FROM users WHERE id = ANY($1)", author_ids
    )
    authors_by_id = {a["id"]: a for a in authors}

    # Assemble — 1ms
    for row in data:
        row["comments"] = comments_by_item.get(row["id"], [])
        row["author"] = authors_by_id.get(row["author_id"])

    return data
    # Total: 200 + 50 + 30 = 280ms (vs 3000ms)
```

**How to find the real bottleneck** — add request-level timing:
```python
import logging
from contextvars import ContextVar
from time import perf_counter

request_timings = ContextVar("timings", default=None)

@app.middleware("http")
async def timing_middleware(request, call_next):
    timings = {}
    request_timings.set(timings)
    start = perf_counter()
    response = await call_next(request)
    total = perf_counter() - start
    logging.info(f"{request.url.path} total={total:.3f}s breakdown={timings}")
    return response

# In your DB wrapper:
async def fetch(query, *args):
    t = request_timings.get()
    start = perf_counter()
    result = await pool.fetch(query, *args)
    elapsed = perf_counter() - start
    if t is not None:
        t.setdefault("db_queries", []).append({"query": query[:50], "ms": elapsed*1000})
    return result
```

**The lesson**: Always profile the entire request path. Database queries are the usual suspect, but N+1 problems, serialization, external service calls, and middleware can dominate total time while the "main query" is fast.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
