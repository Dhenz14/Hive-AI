"""Phase 3E: Metacognition — Learning From Mistakes (Part 3)

Additional pairs for scenarios 1-3: off-by-one, SQL injection, race conditions.
"""

PAIRS = [
    (
        "thinking/meta-mistakes-off-by-one-sliding-window",
        r'''I'm implementing a sliding window of size k over an array. My function returns wrong results for some inputs:

```python
def max_sliding_window(nums, k):
    result = []
    for i in range(len(nums) - k):
        window = nums[i:i+k]
        result.append(max(window))
    return result

# max_sliding_window([1,3,-1,-3,5,3,6,7], 3)
# Returns [3,3,5,5,6] but expected [3,3,5,5,6,7]
```''',
        r'''<think>
I made an error: the loop upper bound is `len(nums) - k` but it should be `len(nums) - k + 1`.

The mistake was: using an exclusive upper bound that's off by one. With nums of length 8 and k=3, `range(8-3)` = `range(5)` gives indices 0-4, but we need 0-5 to include the last window [6,7,...wait, nums[5:8] = [3,6,7]].

The root cause was: I confused "number of windows" with "last index". There are `n - k + 1` windows in total, so the range should go to `n - k + 1`, not `n - k`. This is the classic fencepost error — I was counting gaps instead of posts.

Generalizable lesson: When a loop iterates over "all positions" of a sliding window, the count is `n - k + 1`, not `n - k`. More broadly: always derive loop bounds from the COUNT of items you need to process, not from intuition about indices.

Checklist item: For any sliding window or substring iteration, verify: does my loop produce exactly `n - k + 1` iterations?

Similar situations where this lesson applies:
1. Substring enumeration: iterating over all substrings of length k in a string
2. Convolution: sliding a kernel across an array or image
3. Moving average: computing rolling averages over a fixed window size
</think>

**The bug: your loop runs one iteration too few.**

```python
# Bug: range(len(nums) - k) produces 5 iterations, need 6
for i in range(len(nums) - k):      # indices 0,1,2,3,4

# Fix: range(len(nums) - k + 1) produces 6 iterations
for i in range(len(nums) - k + 1):  # indices 0,1,2,3,4,5
```

**Why this happens:** There are `n - k + 1` possible windows of size `k` in an array of size `n`. With 8 elements and k=3: `8 - 3 + 1 = 6` windows.

**The lesson: always derive loop bounds from the count formula.** For sliding windows, that count is always `n - k + 1`. Don't eyeball it — compute it.

**Quick sanity check:** The last window starts at index `n - k`. Your loop should include that index. `range(n - k)` excludes it; `range(n - k + 1)` includes it.'''
    ),
    (
        "thinking/meta-mistakes-off-by-one-binary-search",
        r'''My binary search sometimes enters an infinite loop:

```python
def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if arr[mid] < target:
            lo = mid  # Move right
        else:
            hi = mid  # Move left
    return lo if arr[lo] == target else -1
```

It hangs when searching for the last element in the array.''',
        r'''<think>
I made an error: `lo = mid` instead of `lo = mid + 1` in the left-move case.

The mistake was: when `arr[mid] < target`, we know `mid` is not the answer, so we should set `lo = mid + 1`. Setting `lo = mid` means we might revisit the same mid repeatedly.

The root cause was: symmetric thinking — I assumed that since `hi = mid` is correct for the right-move case, `lo = mid` must be correct for the left-move case. But floor division makes these asymmetric. When `lo` and `hi` differ by 1, `mid = (lo + hi) // 2 = lo`, so `lo = mid` doesn't advance the search.

Generalizable lesson: Binary search invariants are NOT symmetric. Floor division biases `mid` toward `lo`, so `lo = mid` can stall but `hi = mid` cannot. The fix is always `lo = mid + 1` when using floor division. Alternatively, use ceiling division `mid = (lo + hi + 1) // 2` if you need `hi = mid - 1` and `lo = mid`.

Checklist item: In any binary search, verify: does the loop ALWAYS shrink the [lo, hi] interval? Test with lo = hi - 1.

Similar situations where this lesson applies:
1. Bisecting a sorted range (e.g., bisect_left / bisect_right)
2. Parametric binary search ("find smallest x where f(x) is true")
3. Any divide-and-conquer where you pick a midpoint and recurse on one half
</think>

**The bug: `lo = mid` doesn't advance when `mid == lo`.**

When `lo = 4, hi = 5`: `mid = (4+5)//2 = 4`, so `lo = mid = 4` — infinite loop.

```python
def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if arr[mid] < target:
            lo = mid + 1  # FIX: skip mid, it's too small
        else:
            hi = mid      # Correct: mid might be the answer
    return lo if arr[lo] == target else -1
```

**Why this is asymmetric:** Floor division `(lo + hi) // 2` biases toward `lo`. So:
- `hi = mid` always shrinks the range (mid < hi when lo < hi)
- `lo = mid` does NOT always shrink the range (mid == lo when hi == lo + 1)

**The lesson:** Binary search updates are NOT symmetric. Always verify: does every branch reduce the interval by at least 1? Test with the smallest possible interval (lo = hi - 1).'''
    ),
    (
        "thinking/meta-mistakes-off-by-one-chunk-processing",
        r'''I'm splitting a list into chunks of size n for batch processing. Some items are being dropped:

```python
def chunk_list(items, chunk_size):
    chunks = []
    for i in range(0, len(items), chunk_size):
        chunks.append(items[i:i+chunk_size])
    return chunks

# Wait, actually this works. The real problem is my batch processor:
def process_in_batches(items, batch_size=100):
    total = len(items)
    num_batches = total // batch_size
    for batch_num in range(num_batches):
        start = batch_num * batch_size
        batch = items[start:start + batch_size]
        process(batch)
    print(f"Processed {num_batches * batch_size} of {total} items")
```

We have 250 items with batch_size=100, and the last 50 items never get processed.''',
        r'''<think>
I made an error: `num_batches = total // batch_size` gives 2 for 250//100, so only batches 0 and 1 are processed (items 0-199). Items 200-249 are dropped.

The mistake was: integer division truncates the remainder. I needed ceiling division to account for a partial final batch.

The root cause was: I thought "250 items / 100 per batch = 2.5 batches" and integer division gave me 2. I forgot to handle the remainder. This is the same class of error as the sliding window bug — computing counts with division always risks truncating a partial unit.

Generalizable lesson: Whenever you divide to get a count of "groups" or "batches", ask: is there a remainder? Use ceiling division `(total + batch_size - 1) // batch_size` or just handle the remainder explicitly.

Checklist item: When computing batch/page/chunk counts via division, always test with a total that's NOT a clean multiple of the divisor.

Similar situations where this lesson applies:
1. Pagination: total_pages = ceil(total_items / page_size)
2. Thread pool work distribution: dividing N tasks among M workers
3. File upload chunking: splitting a file into fixed-size parts
</think>

**The bug: integer division drops the partial final batch.**

`250 // 100 = 2`, so items 200-249 are never processed.

**Fix — use ceiling division:**
```python
def process_in_batches(items, batch_size=100):
    total = len(items)
    num_batches = (total + batch_size - 1) // batch_size  # Ceiling division
    for batch_num in range(num_batches):
        start = batch_num * batch_size
        batch = items[start:start + batch_size]
        process(batch)
```

**Or simpler — just iterate with a step:**
```python
def process_in_batches(items, batch_size=100):
    for i in range(0, len(items), batch_size):
        process(items[i:i + batch_size])
```

Python's slice `items[i:i+batch_size]` naturally handles the short final batch.

**The lesson: division for counting groups always risks dropping the remainder.** Either use ceiling division or avoid division entirely by using `range(0, total, step)`.

**Test with:** a total that's NOT evenly divisible. If your code works for 200 items but not 250, you have this bug.'''
    ),
    (
        "thinking/meta-mistakes-sql-injection-search",
        r'''I wrote a search endpoint for our internal admin tool:

```python
@app.route('/admin/search')
def admin_search():
    query = request.args.get('q', '')
    conn = get_db()
    results = conn.execute(
        f"SELECT * FROM users WHERE name LIKE '%{query}%' OR email LIKE '%{query}%'"
    ).fetchall()
    return jsonify([dict(r) for r in results])
```

It works fine for searching. Is there anything wrong with it?''',
        r'''<think>
I made an error: this is a textbook SQL injection vulnerability, even though it's an "internal admin tool."

The mistake was: using f-string interpolation to put user input directly into a SQL query. The `query` parameter comes from the URL query string and is completely user-controlled.

The root cause was: two cognitive biases at work:
1. "It's internal" — assuming internal tools don't need security. But admin tools often have MORE access to sensitive data, and internal networks get compromised.
2. "It's just a search" — LIKE clauses feel read-only and harmless, but SQL injection in a SELECT can still: dump entire tables, extract password hashes, and in some databases execute system commands.

Generalizable lesson: NEVER interpolate user input into SQL, regardless of the context. This applies to internal tools, read-only queries, admin panels — everything. Use parameterized queries always.

Checklist item: Search every query for f-strings, format(), %, or + concatenation with user-supplied values. If found, replace with parameterized queries.

Similar situations where this lesson applies:
1. Logging user input into queries ("just for debugging")
2. Building dynamic WHERE clauses for filters
3. Any ORM .raw() or .execute() call with string formatting
</think>

**Yes — this is SQL injection.** An attacker can send:

```
GET /admin/search?q=' UNION SELECT password,email,name,id FROM users --
```

This would dump all passwords. Worse attacks are possible: `'; DROP TABLE users; --`

**Fix — use parameterized queries:**
```python
@app.route('/admin/search')
def admin_search():
    query = request.args.get('q', '')
    conn = get_db()
    results = conn.execute(
        "SELECT * FROM users WHERE name LIKE ? OR email LIKE ?",
        (f'%{query}%', f'%{query}%')
    ).fetchall()
    return jsonify([dict(r) for r in results])
```

**Why "it's internal" doesn't matter:**
- Internal networks get compromised (phishing, VPN access, contractor accounts)
- Admin tools have MORE database access, not less
- A SQL injection in an admin tool is the worst-case scenario

**The lesson: never interpolate user input into SQL.** Not for internal tools. Not for read-only queries. Not for "simple searches." Always parameterize. The rule has zero exceptions.'''
    ),
    (
        "thinking/meta-mistakes-sql-injection-dynamic-columns",
        r'''I need to let users sort our product listing by different columns. Here's my approach:

```python
@app.get("/products")
def list_products(sort_by: str = "name", order: str = "asc"):
    query = f"SELECT * FROM products ORDER BY {sort_by} {order}"
    return db.execute(query).fetchall()
```

I can't use parameterized queries for column names — the database rejects `ORDER BY ?`. How do I handle this safely?''',
        r'''<think>
I made an error: even though parameterized queries can't be used for identifiers (column names, table names), I still can't just interpolate user input. Both `sort_by` and `order` are injectable.

The mistake was: assuming that because parameterization doesn't work for identifiers, there's no safe alternative. The solution is allowlisting — only permit known-valid column names and sort directions.

The root cause was: seeing parameterized queries as the ONLY defense against SQL injection. When they don't apply (identifiers, ORDER BY, table names), developers sometimes give up on safety entirely. But there's always an alternative: validate against a whitelist.

Generalizable lesson: When parameterized queries can't be used (identifiers, ORDER BY, LIMIT), validate input against a strict allowlist of known-valid values. Never pass unvalidated user input into any part of a SQL query.

Checklist item: For dynamic column/table names, ask: "Is this value from a fixed set I control?" If yes, allowlist it. If no, reject the request.

Similar situations where this lesson applies:
1. Dynamic table names in multi-tenant systems
2. Dynamic GROUP BY clauses in analytics dashboards
3. Dynamic LIMIT/OFFSET (should still be validated as integers)
</think>

**Both `sort_by` and `order` are SQL injection vectors.** An attacker could send `sort_by=name; DROP TABLE products--`.

**You're right that you can't parameterize column names. The fix is allowlisting:**

```python
ALLOWED_SORT_COLUMNS = {"name", "price", "created_at", "rating"}
ALLOWED_ORDER = {"asc", "desc"}

@app.get("/products")
def list_products(sort_by: str = "name", order: str = "asc"):
    if sort_by not in ALLOWED_SORT_COLUMNS:
        raise HTTPException(400, f"Invalid sort column: {sort_by}")
    if order.lower() not in ALLOWED_ORDER:
        raise HTTPException(400, f"Invalid order: {order}")

    query = f"SELECT * FROM products ORDER BY {sort_by} {order}"
    return db.execute(query).fetchall()
```

**Why allowlisting works:** The user's input never reaches the query — only values from your predefined set do. Even if someone sends `sort_by=; DROP TABLE products--`, it fails the allowlist check.

**The lesson: when parameterization isn't possible, allowlist instead.** There are only two safe patterns for user input in SQL:
1. **Values** → parameterized queries (`WHERE name = ?`)
2. **Identifiers** → allowlist validation (`ORDER BY {validated_column}`)

There is no third option. String interpolation without either of these is always a vulnerability.'''
    ),
    (
        "thinking/meta-mistakes-sql-injection-orm-raw",
        r'''I'm using SQLAlchemy ORM but needed a complex query so I used raw SQL:

```python
def get_user_orders(user_id, status_filter=None):
    query = "SELECT o.*, p.name FROM orders o JOIN products p ON o.product_id = p.id WHERE o.user_id = :user_id"

    if status_filter:
        query += f" AND o.status = '{status_filter}'"

    return db.session.execute(text(query), {"user_id": user_id}).fetchall()
```

I used parameterized query for user_id. Is the status_filter safe since it's an optional filter?''',
        r'''<think>
I made an error: I parameterized `user_id` correctly but then used f-string interpolation for `status_filter`. One safe parameter doesn't make the whole query safe.

The mistake was: partial parameterization — treating some inputs as safe and others as unsafe. Every user-controlled value needs the same treatment.

The root cause was: inconsistent application of a security principle. I "knew" about parameterized queries (used one correctly!) but then fell back to string interpolation for the conditional clause. This often happens when building dynamic queries — the base query is safe, but the dynamic parts added later aren't.

Generalizable lesson: Security measures must be applied consistently. One parameterized value doesn't protect against injection through another unparameterized value. Every user input in a query must be parameterized, no exceptions.

Checklist item: After writing a query, check EVERY dynamic value — not just the first one. If you add a conditional clause, it needs parameterization too.

Similar situations where this lesson applies:
1. XSS: escaping some outputs but not others in a template
2. Authentication: checking permissions on some endpoints but not others
3. Input validation: validating some form fields but not others
</think>

**No — `status_filter` is injectable.** You parameterized `user_id` but then used f-string for `status_filter`:

```python
# Attacker sends status_filter = "'; DROP TABLE orders; --"
query += f" AND o.status = '{status_filter}'"
# Becomes: AND o.status = ''; DROP TABLE orders; --'
```

**Fix — parameterize ALL dynamic values:**
```python
def get_user_orders(user_id, status_filter=None):
    query = "SELECT o.*, p.name FROM orders o JOIN products p ON o.product_id = p.id WHERE o.user_id = :user_id"
    params = {"user_id": user_id}

    if status_filter:
        query += " AND o.status = :status"
        params["status"] = status_filter

    return db.session.execute(text(query), params).fetchall()
```

**Or better — use SQLAlchemy ORM and avoid raw SQL entirely:**
```python
def get_user_orders(user_id, status_filter=None):
    q = db.session.query(Order, Product.name).join(Product).filter(Order.user_id == user_id)
    if status_filter:
        q = q.filter(Order.status == status_filter)
    return q.all()
```

**The lesson: security must be applied consistently.** One parameterized value doesn't protect the query — every dynamic value needs parameterization. When building dynamic queries, check every conditional clause you append.'''
    ),
    (
        "thinking/meta-mistakes-race-condition-balance",
        r'''Users are occasionally getting negative balances in our payment system despite our check:

```python
def withdraw(user_id, amount):
    user = db.query(User).get(user_id)
    if user.balance >= amount:
        user.balance -= amount
        db.commit()
        transfer_funds(user_id, amount)
        return {"success": True}
    return {"error": "Insufficient funds"}
```

The balance check looks correct. What's going wrong?''',
        r'''<think>
I made an error: this is a classic TOCTOU (time-of-check-time-of-use) race condition. Between reading the balance and writing the new balance, another request can also read the same balance.

The mistake was: assuming that reading and writing within the same function means they're atomic. They're not — another request/thread can interleave between the read and write.

The root cause was: not recognizing that "check then act" on shared mutable state is inherently racy without a lock or atomic operation. Two concurrent withdrawal requests can both see balance=100, both pass the `>= amount` check, and both subtract.

Generalizable lesson: Any "read → check → write" sequence on shared data is a race condition unless protected by a lock, transaction isolation, or atomic operation. In databases specifically, use SELECT FOR UPDATE or atomic UPDATE with a WHERE clause.

Checklist item: Whenever you read a value, make a decision based on it, then write back — ask: "What if another request reads the same value between my read and write?"

Similar situations where this lesson applies:
1. Inventory systems: checking stock then decrementing
2. Seat reservation: checking availability then booking
3. Rate limiting: checking counter then incrementing
</think>

**This is a race condition (TOCTOU).** Two simultaneous withdrawals both read the same balance:

```
Request A: reads balance = 100, checks 100 >= 80 ✓
Request B: reads balance = 100, checks 100 >= 80 ✓
Request A: balance = 100 - 80 = 20, commits
Request B: balance = 100 - 80 = 20, commits  ← WRONG, should be -60 or rejected
```

**Fix 1 — Atomic UPDATE with WHERE clause (best):**
```python
def withdraw(user_id, amount):
    result = db.execute(
        text("UPDATE users SET balance = balance - :amount WHERE id = :id AND balance >= :amount"),
        {"id": user_id, "amount": amount}
    )
    db.commit()
    if result.rowcount == 0:
        return {"error": "Insufficient funds"}
    transfer_funds(user_id, amount)
    return {"success": True}
```

This is atomic — the database checks and updates in a single operation.

**Fix 2 — SELECT FOR UPDATE (row lock):**
```python
def withdraw(user_id, amount):
    user = db.query(User).with_for_update().get(user_id)  # Locks the row
    if user.balance >= amount:
        user.balance -= amount
        db.commit()
        transfer_funds(user_id, amount)
        return {"success": True}
    return {"error": "Insufficient funds"}
```

**The lesson: "read, check, write" on shared data is always a race condition.** Use atomic operations or locks. For money, prefer the atomic UPDATE — it's simpler and impossible to get wrong.'''
    ),
    (
        "thinking/meta-mistakes-race-condition-file-check",
        r'''My file processing pipeline occasionally crashes with "file not found" even though I check if the file exists first:

```python
import os

def process_upload(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            data = f.read()
        process(data)
        os.remove(filepath)
    else:
        log.warning(f"File not found: {filepath}")
```

Multiple workers can process uploads concurrently. Why does this fail?''',
        r'''<think>
I made an error: this is another TOCTOU race. `os.path.exists()` returns True, but by the time `open()` runs, another worker may have already processed and deleted the file.

The mistake was: checking existence separately from the operation that needs the file. The check provides no guarantee by the time you act on it.

The root cause was: treating file system operations as if they're single-user. With concurrent workers, the gap between "check" and "use" is a window for another worker to grab the same file.

Generalizable lesson: File existence checks are inherently racy in concurrent environments. Instead of "check then act," use atomic operations: try to open/rename the file and handle the exception. This is the EAFP (Easier to Ask Forgiveness than Permission) principle.

Checklist item: If you see `os.path.exists()` followed by `open()` or `os.remove()`, ask: "Can another process touch this file between my check and my action?"

Similar situations where this lesson applies:
1. Lock files: checking if a lock file exists then creating it
2. Temp files: checking for a unique name then creating the file
3. Directory creation: checking if dir exists then calling mkdir
</think>

**Another TOCTOU race.** Two workers both see the file, both try to process it:

```
Worker A: os.path.exists() → True
Worker B: os.path.exists() → True
Worker A: opens file, reads, removes
Worker B: opens file → FileNotFoundError (already deleted by A)
```

**Fix — don't check, just try (EAFP):**
```python
def process_upload(filepath):
    try:
        with open(filepath) as f:
            data = f.read()
    except FileNotFoundError:
        log.info(f"Already processed: {filepath}")
        return

    process(data)

    try:
        os.remove(filepath)
    except FileNotFoundError:
        pass  # Another worker already cleaned up
```

**Even better — use atomic rename to "claim" the file:**
```python
def process_upload(filepath):
    claimed_path = filepath + f".processing.{os.getpid()}"
    try:
        os.rename(filepath, claimed_path)  # Atomic on same filesystem
    except FileNotFoundError:
        return  # Another worker claimed it

    try:
        with open(claimed_path) as f:
            data = f.read()
        process(data)
    finally:
        os.remove(claimed_path)
```

Renaming is atomic — only one worker succeeds, the rest get `FileNotFoundError`.

**The lesson: `os.path.exists()` + action is always a race condition in concurrent code.** Use try/except (EAFP) or atomic file operations like rename. Never check-then-act on the filesystem with concurrent workers.'''
    ),
    (
        "thinking/meta-mistakes-race-condition-cache-stampede",
        r'''Our API has a caching layer but during high traffic, when the cache expires, we see massive spikes in database load. The database sometimes goes down during these spikes:

```python
def get_popular_products():
    cached = redis.get("popular_products")
    if cached:
        return json.loads(cached)

    # Cache miss — query database
    products = db.execute("SELECT * FROM products ORDER BY sales DESC LIMIT 100").fetchall()
    result = [dict(p) for p in products]

    redis.setex("popular_products", 300, json.dumps(result))  # Cache for 5 min
    return result
```''',
        r'''<think>
I made an error: this is a cache stampede (also called thundering herd). When the cache expires, ALL concurrent requests see a cache miss simultaneously and ALL hit the database at the same time.

The mistake was: not considering what happens when many requests hit during the brief window between cache expiry and cache repopulation. Each request independently decides to query the database.

The root cause was: thinking about caching as a single-request optimization without considering the concurrent case. With 1000 req/s, the moment the cache key expires, potentially hundreds of requests all try to rebuild the cache simultaneously.

Generalizable lesson: Cache expiry with concurrent traffic creates a thundering herd problem. Protect cache rebuilds with a lock (only one request rebuilds while others wait) or use stale-while-revalidate (serve stale data while one request refreshes).

Checklist item: For any cache with TTL under high traffic, ask: "What happens when N requests all hit a cache miss at the same time?"

Similar situations where this lesson applies:
1. DNS cache expiry causing a surge of DNS lookups
2. Connection pool exhaustion when all connections expire at once
3. Rate limiter reset causing a burst of requests
</think>

**This is a cache stampede (thundering herd).** When the cache expires, every concurrent request hits the database simultaneously.

With 1000 req/s and a cache miss, hundreds of requests all execute that expensive query at once.

**Fix 1 — Lock-based cache rebuild (recommended):**
```python
def get_popular_products():
    cached = redis.get("popular_products")
    if cached:
        return json.loads(cached)

    # Only one request rebuilds the cache
    lock = redis.lock("lock:popular_products", timeout=10)
    if lock.acquire(blocking=False):
        try:
            # Double-check after acquiring lock
            cached = redis.get("popular_products")
            if cached:
                return json.loads(cached)

            products = db.execute("SELECT * FROM products ORDER BY sales DESC LIMIT 100").fetchall()
            result = [dict(p) for p in products]
            redis.setex("popular_products", 300, json.dumps(result))
            return result
        finally:
            lock.release()
    else:
        # Another request is rebuilding — wait briefly and retry
        import time
        time.sleep(0.1)
        cached = redis.get("popular_products")
        return json.loads(cached) if cached else []
```

**Fix 2 — Stale-while-revalidate (simpler):**
```python
def get_popular_products():
    cached = redis.get("popular_products")
    ttl = redis.ttl("popular_products")

    if cached and ttl > 30:
        return json.loads(cached)  # Fresh enough

    if cached and ttl <= 30:
        # Serve stale data, trigger async refresh
        refresh_cache_async.delay()  # Celery task
        return json.loads(cached)

    # True cache miss — rebuild synchronously
    return rebuild_popular_products_cache()
```

**The lesson: caching isn't just about single-request performance — consider what happens at cache boundaries under concurrent load.** Always protect expensive cache rebuilds with a lock or stale-while-revalidate pattern.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
