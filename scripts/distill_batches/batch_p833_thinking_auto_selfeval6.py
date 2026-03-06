"""Phase 4B: Self-Improvement — Self-Evaluation (Part 6)

Evaluating own code suggestions for performance issues and optimization opportunities.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-check-query-performance",
        r'''I'm about to suggest this database query to a user who needs to find inactive users. Let me evaluate it for performance:

My draft query:
SELECT * FROM users WHERE id NOT IN (SELECT user_id FROM logins WHERE login_date > NOW() - INTERVAL '90 days');

The users table has 2 million rows and logins has 50 million rows.''',
        r'''<think>
Let me evaluate my query for performance issues:

**The query:** Find users who haven't logged in for 90 days using NOT IN with a subquery.

**Performance analysis:**

1. **NOT IN with subquery is dangerous at scale:**
   - The subquery `SELECT user_id FROM logins WHERE login_date > ...` scans 50M rows
   - NOT IN must compare each of the 2M users against the entire subquery result
   - If the subquery returns NULL values, NOT IN returns UNKNOWN, causing incorrect results
   - Estimated time: minutes, possibly timing out

2. **SELECT * is wasteful:**
   - Fetches all columns when the user probably needs just a few
   - Forces a table lookup even if an index covers the query

3. **No index consideration:**
   - I didn't mention that logins needs an index on (user_id, login_date)
   - Without indexes, this query will do full table scans on both tables

**Better alternatives:**
- LEFT JOIN with NULL check (more predictable performance)
- NOT EXISTS (usually optimized better by the planner)
- Batch processing for 2M users

**Verdict:** My query would likely crash or time out on tables this size. I need to suggest a performant alternative.
</think>

**Self-evaluation: My query will likely TIME OUT or crash on 2M + 50M row tables. Rating: 2/10.**

**Problems with my suggestion:**

| Issue | Impact |
|-------|--------|
| NOT IN with subquery | O(n*m) comparison, possible NULL bugs |
| SELECT * | Fetches unnecessary data |
| No index guidance | Full table scan on 50M rows |
| No pagination | Returns potentially millions of rows at once |

**What I should suggest instead:**

```sql
-- Option 1: NOT EXISTS (usually best for this pattern)
SELECT u.id, u.email, u.name
FROM users u
WHERE NOT EXISTS (
    SELECT 1 FROM logins l
    WHERE l.user_id = u.id
    AND l.login_date > NOW() - INTERVAL '90 days'
);

-- Required index:
CREATE INDEX idx_logins_user_date ON logins(user_id, login_date);

-- Option 2: LEFT JOIN (equivalent, sometimes faster)
SELECT u.id, u.email, u.name
FROM users u
LEFT JOIN logins l ON l.user_id = u.id
    AND l.login_date > NOW() - INTERVAL '90 days'
WHERE l.user_id IS NULL;

-- For 2M results, add pagination:
-- ... ORDER BY u.id LIMIT 1000 OFFSET 0;
```

**Performance comparison on 2M + 50M rows:**
| Approach | Estimated time | Safe? |
|----------|---------------|-------|
| NOT IN (my original) | Minutes / timeout | No (NULL bug risk) |
| NOT EXISTS | 2-10 seconds | Yes |
| LEFT JOIN | 2-10 seconds | Yes |
| LEFT JOIN + batch | <1 second per batch | Yes |

**Self-evaluation lesson:** Always consider table sizes before suggesting queries. A query that works on 1000 rows can destroy a database with millions.'''
    ),
    (
        "thinking/auto-selfeval-check-loop-performance",
        r'''I wrote this Python code to process a large CSV file. Let me evaluate it for performance before suggesting it:

My draft:
```python
import csv

def process_csv(filename):
    results = []
    with open(filename) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['status'] == 'active':
                email = row['email'].lower().strip()
                if email not in [r['email'] for r in results]:
                    results.append({'email': email, 'name': row['name']})
    return results
```

The CSV file has 5 million rows.''',
        r'''<think>
Let me analyze my code for performance issues on a 5 million row file:

**Issue 1: O(n^2) duplicate check**
`if email not in [r['email'] for r in results]` — This creates a NEW list every iteration and does a linear scan. For 5M rows, this is O(n^2) = 25 trillion operations. This alone would take hours.

**Issue 2: List comprehension recreated each iteration**
`[r['email'] for r in results]` builds a new list from scratch every time through the loop. As results grows, this gets catastrophically slow.

**Issue 3: Appending to list for deduplication**
Using a list for membership testing is O(n). A set would be O(1).

**Issue 4: Loading all results into memory**
5M rows * ~100 bytes each = ~500MB in memory. Could work but is wasteful.

**Issue 5: csv.DictReader overhead**
DictReader creates a new dict for every row. For 5M rows, csv.reader with index access is faster.

**Verdict:** This code will effectively never finish on 5M rows due to the O(n^2) deduplication. The fix is simple — use a set.
</think>

**Self-evaluation: This code has an O(n^2) bug that makes it unusable on 5M rows. Rating: 1/10 for performance.**

**The critical problem:**
```python
# This line is O(n) and runs n times = O(n^2):
if email not in [r['email'] for r in results]:  # Rebuilds list EVERY iteration!
```

For 5M rows: ~12.5 trillion operations. Estimated time: **hours to days.**

**Corrected version:**
```python
import csv

def process_csv(filename):
    seen_emails = set()  # O(1) lookup instead of O(n)
    results = []

    with open(filename) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['status'] == 'active':
                email = row['email'].lower().strip()
                if email not in seen_emails:  # O(1) set lookup!
                    seen_emails.add(email)
                    results.append({'email': email, 'name': row['name']})

    return results
```

**Even better for 5M rows (streaming with generators):**
```python
import csv

def process_csv(filename):
    seen_emails = set()

    with open(filename) as f:
        reader = csv.reader(f)  # Faster than DictReader
        header = next(reader)
        email_idx = header.index('email')
        name_idx = header.index('name')
        status_idx = header.index('status')

        for row in reader:
            if row[status_idx] == 'active':
                email = row[email_idx].lower().strip()
                if email not in seen_emails:
                    seen_emails.add(email)
                    yield {'email': email, 'name': row[name_idx]}
```

**Performance comparison on 5M rows:**
| Version | Time estimate | Memory |
|---------|--------------|--------|
| My original (O(n^2)) | Hours/days | 500MB+ |
| Set-based dedup | ~10 seconds | 500MB |
| Generator + csv.reader | ~5 seconds | ~50MB |
| pandas (if fits in memory) | ~3 seconds | 1-2GB |

**Self-evaluation lesson:** Always check for O(n^2) patterns before suggesting code for large datasets. The most common form: membership testing on a list inside a loop.'''
    ),
    (
        "thinking/auto-selfeval-check-memory-usage",
        r'''I'm about to suggest this code to load and process a JSON file. Let me check if it will work for the user's case:

My draft:
```python
import json

def analyze_logs(filename):
    with open(filename) as f:
        data = json.load(f)

    errors = [entry for entry in data if entry['level'] == 'ERROR']
    error_counts = {}
    for error in errors:
        msg = error['message']
        error_counts[msg] = error_counts.get(msg, 0) + 1

    return sorted(error_counts.items(), key=lambda x: -x[1])[:10]
```

The user mentioned their log file is 15GB.''',
        r'''<think>
Let me evaluate this for a 15GB JSON file:

**Problem 1: json.load() loads the ENTIRE file into memory**
- A 15GB JSON file will require roughly 30-45GB of RAM (JSON objects in Python use 2-3x the file size in memory)
- This will crash with MemoryError on most machines

**Problem 2: List comprehension creates another copy**
- `[entry for entry in data if entry['level'] == 'ERROR']` creates a second list of all error entries
- Even if only 10% are errors, that is 1.5GB more data in memory

**Problem 3: No streaming**
- We only need the top 10 error messages
- We don't need to hold all entries in memory simultaneously
- This is a streaming/aggregation problem, not a "load everything" problem

**Problem 4: JSON format for 15GB is questionable**
- 15GB of JSON is unusual; the user might have JSONL (one JSON object per line) which is much easier to stream

**Verdict:** This code will crash immediately on a 15GB file. I need to suggest a streaming approach.
</think>

**Self-evaluation: This code will CRASH with MemoryError on a 15GB file. Rating: 0/10.**

**The fundamental problem:**
```python
data = json.load(f)  # Tries to load 15GB into memory → needs 30-45GB RAM → crash
```

**What I should suggest instead:**

**If the file is JSONL (one JSON object per line — most likely for logs):**
```python
import json
from collections import Counter

def analyze_logs(filename):
    error_counts = Counter()

    with open(filename) as f:
        for line in f:  # Reads ONE line at a time — constant memory!
            try:
                entry = json.loads(line)
                if entry.get('level') == 'ERROR':
                    error_counts[entry['message']] += 1
            except json.JSONDecodeError:
                continue  # Skip malformed lines

    return error_counts.most_common(10)

# Memory usage: ~constant (a few MB regardless of file size)
# Time: Single pass through the file, ~2-5 minutes for 15GB
```

**If the file is a single JSON array (less likely but possible):**
```python
import ijson  # pip install ijson — streaming JSON parser

def analyze_logs(filename):
    error_counts = Counter()

    with open(filename, 'rb') as f:
        for entry in ijson.items(f, 'item'):  # Parses one item at a time
            if entry.get('level') == 'ERROR':
                error_counts[entry['message']] += 1

    return error_counts.most_common(10)
```

**Comparison:**
| Approach | Memory | Time (15GB) | Works? |
|----------|--------|-------------|--------|
| json.load() (my original) | 30-45GB | Crash | No |
| JSONL line-by-line | ~5MB | 2-5 min | Yes |
| ijson streaming | ~50MB | 5-10 min | Yes |
| pandas chunked | ~500MB | 3-5 min | Yes |

**Self-evaluation lesson:** Before suggesting file processing code, ALWAYS ask about file size. Any approach that loads the entire file fails for files larger than available RAM. The streaming approach (process one record at a time) should be the default for log analysis.'''
    ),
    (
        "thinking/auto-selfeval-check-api-response-time",
        r'''I built an API endpoint that fetches user data with their recent orders and recommendations. Let me evaluate the response time before deploying:

My implementation:
```python
@app.route('/api/users/<int:user_id>/profile')
def get_user_profile(user_id):
    user = db.query("SELECT * FROM users WHERE id = %s", user_id)
    orders = db.query("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC", user_id)
    for order in orders:
        order['items'] = db.query("SELECT * FROM order_items WHERE order_id = %s", order['id'])
        for item in order['items']:
            item['product'] = db.query("SELECT * FROM products WHERE id = %s", item['product_id'])
    recommendations = requests.get(f"http://rec-service/users/{user_id}").json()
    reviews = db.query("SELECT * FROM reviews WHERE user_id = %s", user_id)
    return jsonify({"user": user, "orders": orders, "recommendations": recommendations, "reviews": reviews})
```''',
        r'''<think>
Let me analyze the performance of this endpoint:

**Counting database queries:**
1. 1 query for user
2. 1 query for all orders
3. N queries for order items (one per order)
4. N*M queries for products (one per item per order)
5. 1 HTTP call to recommendation service
6. 1 query for reviews

If a user has 20 orders with 3 items each:
- User: 1 query
- Orders: 1 query
- Order items: 20 queries (N+1!)
- Products: 60 queries (N+1 within N+1!)
- Recommendations: 1 HTTP call (200ms+)
- Reviews: 1 query

**Total: 84 database queries + 1 HTTP call**

At 5ms per query: 84 * 5ms = 420ms for DB alone
Plus 200ms for recommendation service
**Total: ~620ms minimum**

For a user with 50 orders and 5 items each:
- 1 + 1 + 50 + 250 + 1 + 1 = 304 queries = 1.5 seconds for DB
- Plus 200ms HTTP call = 1.7 seconds total

**Problems:**
1. Classic N+1 query problem (nested loops of queries)
2. SELECT * fetches unnecessary columns
3. No pagination on orders (could return thousands)
4. Sequential execution (DB queries then HTTP call)
5. No caching
6. Recommendation service call is blocking

**Verdict:** This endpoint has severe N+1 query problems and will be unacceptably slow for active users.
</think>

**Self-evaluation: This endpoint has 80+ database queries per request. Rating: 2/10.**

**Query count analysis:**
```
User with 20 orders, 3 items each:
  1  (user query)
+ 1  (orders query)
+ 20 (order_items queries — N+1!)
+ 60 (product queries — N+1 within N+1!)
+ 1  (recommendations HTTP call)
+ 1  (reviews query)
= 84 database queries + 1 HTTP call = ~620ms
```

**What I should suggest instead:**

```python
@app.route('/api/users/<int:user_id>/profile')
async def get_user_profile(user_id):
    # 1. Fetch user + orders + items in ONE query using JOINs:
    user = db.query("SELECT id, name, email FROM users WHERE id = %s", user_id)

    orders = db.query("""
        SELECT o.id, o.total, o.created_at,
               oi.quantity, oi.price,
               p.id as product_id, p.name as product_name
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        WHERE o.user_id = %s
        ORDER BY o.created_at DESC
        LIMIT 10
    """, user_id)  # ONE query instead of 81!

    # 2. Run remaining queries CONCURRENTLY:
    reviews_task = db.query_async(
        "SELECT id, rating, comment, created_at FROM reviews WHERE user_id = %s LIMIT 20",
        user_id
    )
    rec_task = httpx.get(f"http://rec-service/users/{user_id}", timeout=2.0)

    reviews, rec_response = await asyncio.gather(reviews_task, rec_task)

    return jsonify({
        "user": user,
        "orders": group_orders(orders),  # Restructure flat JOIN into nested
        "recommendations": rec_response.json(),
        "reviews": reviews
    })
```

**Improvement:**
| Metric | Before | After |
|--------|--------|-------|
| DB queries | 84 | 2 |
| HTTP calls | 1 (sequential) | 1 (concurrent) |
| Estimated time | 620ms | ~60ms |
| Scalability | Breaks with active users | Constant query count |

**Self-evaluation lesson:** Count your queries. If the number depends on the data (N+1), it will get worse as users become more active. Use JOINs and concurrent I/O.'''
    ),
    (
        "thinking/auto-selfeval-check-algorithmic-complexity",
        r'''I'm about to suggest this algorithm for finding duplicates in a list. Let me evaluate its performance:

My draft:
```python
def find_duplicates(items):
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j] and items[i] not in duplicates:
                duplicates.append(items[i])
    return duplicates
```

The user has a list of 500,000 items.''',
        r'''<think>
Let me analyze the algorithmic complexity:

**Time complexity:**
- Outer loop: n iterations
- Inner loop: average n/2 iterations
- `items[i] not in duplicates`: O(d) where d is duplicates found so far
- Total: O(n^2 * d) in the worst case, O(n^2) in the average case

For n = 500,000:
- n^2 = 250,000,000,000 (250 billion comparisons)
- At ~100M comparisons/second in Python: ~2,500 seconds = ~42 minutes
- This is completely unacceptable

**Also:**
- `items[i] not in duplicates` uses a list for membership testing (O(n) per check)
- If there are many duplicates, this adds another O(n) factor

**The optimal approach:**
- Use a Counter or set-based approach: O(n) time, O(n) space
- This is a textbook example of when to use a hash set

**Verdict:** My suggestion is O(n^2) when O(n) is possible. For 500K items, it would take ~42 minutes instead of <1 second.
</think>

**Self-evaluation: O(n^2) algorithm for a problem that has an O(n) solution. Rating: 1/10.**

**Performance on 500,000 items:**
| Approach | Complexity | Estimated time |
|----------|-----------|---------------|
| My nested loop | O(n^2) | ~42 minutes |
| Set-based | O(n) | <0.5 seconds |

**What I should suggest instead:**

```python
from collections import Counter

def find_duplicates(items):
    counts = Counter(items)
    return [item for item, count in counts.items() if count > 1]

# Or without Counter:
def find_duplicates(items):
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    return list(duplicates)
```

**Why the set-based approach is O(n):**
- Single pass through the list: O(n)
- Set lookup (`in seen`): O(1) average
- Set insertion (`seen.add`): O(1) average
- Total: O(n) time, O(n) space

**Benchmark on 500,000 items:**
```python
import time
from collections import Counter

items = list(range(400000)) + list(range(100000))  # 100K duplicates

# O(n^2) approach: ~42 minutes (don't actually run this)

# O(n) approach:
start = time.time()
result = [item for item, count in Counter(items).items() if count > 1]
print(f"Time: {time.time() - start:.3f}s")  # ~0.15 seconds
```

**Self-evaluation lesson:** Before suggesting any algorithm that uses nested loops, check if a hash-based (set/dict) approach exists. The most common interview/code-review optimization is replacing O(n^2) nested loops with O(n) hash lookups.

**Quick reference — common O(n^2) to O(n) upgrades:**
| Problem | O(n^2) approach | O(n) approach |
|---------|----------------|---------------|
| Find duplicates | Nested loop comparison | Set/Counter |
| Two sum | Nested loop | Hash map lookup |
| Check membership | List scan in loop | Convert to set |
| Group by key | Nested filtering | defaultdict |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
