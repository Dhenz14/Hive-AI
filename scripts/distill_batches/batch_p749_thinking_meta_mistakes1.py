"""Phase 3E: Metacognition — Learning From Mistakes (Part 1)

After identifying an error, extract the GENERALIZABLE lesson that
prevents the entire CLASS of errors, not just this specific instance.
"""

PAIRS = [
    (
        "thinking/meta-mistakes-off-by-one-pagination",
        r'''I wrote pagination for our API and users are seeing duplicate items between pages. Here's the code:

```python
def get_page(items, page, per_page):
    start = page * per_page
    end = start + per_page
    return items[start:end]
```

With page=0, per_page=10: items[0:10] ✓
With page=1, per_page=10: items[10:20] ✓

But users report duplicates. What's wrong?''',
        r'''<think>
I made an error: Let me look at this more carefully. The slicing logic actually looks correct for 0-indexed pages. But wait — the user said users report duplicates. Let me think about what could cause duplicates even with correct slicing.

The mistake was: I initially thought the slicing was wrong, but the real issue is likely that the function is called with 1-indexed pages from the API:

If the API sends page=1 (first page):
  start = 1 * 10 = 10
  end = 20
  Returns items[10:20] — SKIPS the first 10 items!

If the frontend then requests page=0 to try to get "previous" items:
  Returns items[0:10] — these overlap with what was expected on page 1

The root cause was: An off-by-one error in the page numbering convention. The function uses 0-indexed pages, but REST APIs typically use 1-indexed pages (page=1 is the first page). The mismatch between API convention and implementation causes items to be skipped or duplicated.

Generalizable lesson: **Always test boundary values.** Specifically, test page=0, page=1, and the last page. Off-by-one errors are caught by testing the boundaries, not the middle.

Checklist item: When implementing pagination, explicitly document whether pages are 0-indexed or 1-indexed, and test both the first and last page.

Similar situations where this lesson applies:
1. Array indexing (0-based vs 1-based in different languages)
2. Date ranges (is the end date inclusive or exclusive?)
3. Database OFFSET (OFFSET 0 = first row, not OFFSET 1)
4. Loop bounds (< vs <=, range(n) excludes n)
</think>

The function uses **0-indexed pages** but REST APIs typically use **1-indexed pages**. When the API sends `page=1`, the function calculates `start = 10`, skipping the first 10 items.

**Fix:**
```python
def get_page(items, page, per_page):
    start = (page - 1) * per_page  # 1-indexed: page 1 starts at 0
    end = start + per_page
    return items[start:end]
```

**The generalizable lesson: Always test boundary values.**

Off-by-one errors are the most common programming mistake, and they're always caught by testing the boundaries:
- Test page=1 (first page) — does it start at item 0?
- Test page=last (last page) — does it include the final items?
- Test page=0 — does it return an error or empty?

**Checklist for ANY pagination/slicing:**
1. Is the index 0-based or 1-based? Document it.
2. Are ranges inclusive or exclusive? Document it.
3. Test the FIRST and LAST page/slice explicitly.
4. Test with 0, 1, and total items as edge cases.

**Where this same mistake appears:**
- `OFFSET` in SQL (0-based, but page numbers are usually 1-based)
- `range(1, n)` — excludes n (is that intended?)
- Date ranges: "from Monday to Friday" — does Friday include 23:59:59?
- String slicing: `s[0:5]` includes index 0 through 4, not 5'''
    ),
    (
        "thinking/meta-mistakes-sql-injection-format",
        r'''I wrote a search endpoint and found that special characters break it. Here's the code:

```python
@app.route('/search')
def search():
    query = request.args.get('q', '')
    results = db.execute(
        f"SELECT * FROM products WHERE name LIKE '%{query}%'"
    )
    return jsonify([dict(r) for r in results])
```

A user searched for "it's" and got a SQL error. What happened?''',
        r'''<think>
I made an error: The query string is directly interpolated into SQL using f-string formatting.

The mistake was: Using string formatting (f-string) to build SQL queries instead of parameterized queries. When the user searches for "it's", the generated SQL becomes:
```sql
SELECT * FROM products WHERE name LIKE '%it's%'
```
The apostrophe in "it's" closes the SQL string, causing a syntax error. But worse — this is a SQL injection vulnerability.

The root cause was: Treating user input as trusted data that can be directly embedded in SQL. This is fundamentally a trust boundary violation — data crossing from untrusted (user input) to trusted (SQL) without sanitization.

Generalizable lesson: **Never interpolate user input into structured queries.** This applies to SQL, shell commands, HTML, LDAP queries, and any other structured language. Always use the language's parameterized/escaped mechanism.

Checklist item: Any time you build a string that will be interpreted by another system (database, shell, browser), check: is user input parameterized or interpolated?

Similar situations where this lesson applies:
1. Shell command injection: `os.system(f"ls {user_path}")`
2. HTML injection (XSS): `f"<div>{user_comment}</div>"`
3. LDAP injection: `f"(uid={username})"`
4. Template injection: `Template(user_string).render()`
5. Header injection: `f"Location: {user_url}"`
</think>

This is a **SQL injection vulnerability**. The user's apostrophe breaks the SQL, but an attacker could do much worse:

```
Search: ' OR 1=1; DROP TABLE products; --
SQL:    SELECT * FROM products WHERE name LIKE '%' OR 1=1; DROP TABLE products; --%'
```

**Fix — always use parameterized queries:**
```python
@app.route('/search')
def search():
    query = request.args.get('q', '')
    results = db.execute(
        "SELECT * FROM products WHERE name LIKE :pattern",
        {"pattern": f"%{query}%"}
    )
    return jsonify([dict(r) for r in results])
```

**The generalizable lesson: Never interpolate user input into structured queries or commands.**

This principle applies everywhere data crosses a trust boundary:

| Context | Vulnerable | Safe |
|---------|-----------|------|
| SQL | `f"WHERE name = '{input}'"` | `WHERE name = :param` |
| Shell | `os.system(f"ls {path}")` | `subprocess.run(["ls", path])` |
| HTML | `f"<div>{comment}</div>"` | Template auto-escaping |
| URLs | `f"https://api.com/{input}"` | `urllib.parse.quote(input)` |

**Checklist for every trust boundary:**
1. Is user input being embedded in a structured language?
2. Is parameterization/escaping used?
3. If building strings dynamically, does the input pass through a sanitizer?

**The root cause is always the same:** Confusing DATA with CODE. User input is data; SQL is code. When data is treated as code, injection happens.'''
    ),
    (
        "thinking/meta-mistakes-race-condition-counter",
        r'''I built a like counter for posts and users reported that likes sometimes don't register. Here's the code:

```python
def like_post(post_id, user_id):
    post = Post.query.get(post_id)
    post.like_count += 1
    db.session.commit()
    Like.create(post_id=post_id, user_id=user_id)
    db.session.commit()
```

After investigation, we found that when 50 users like a post simultaneously, only 30-40 likes are recorded. Why?''',
        r'''<think>
I made an error: This is a classic lost update race condition.

The mistake was: Reading the current count, incrementing in application code, then writing back. With concurrent requests:
  Thread A reads like_count = 100
  Thread B reads like_count = 100
  Thread A writes like_count = 101
  Thread B writes like_count = 101 (should be 102!)

10-20 likes are lost because concurrent threads overwrite each other.

The root cause was: Not identifying shared mutable state. `like_count` is shared (multiple users modify it) and mutable (it changes). Any shared mutable state needs synchronization.

Generalizable lesson: **Identify shared mutable state FIRST.** Before writing code that modifies shared data, ask: "Can two processes/threads modify this simultaneously?" If yes, use atomic operations or locks.

Checklist item: For any increment/decrement operation on shared data, use a database-level atomic operation (UPDATE SET x = x + 1) instead of read-modify-write in application code.

Similar situations where this lesson applies:
1. Inventory decrement (two users buy the last item)
2. Account balance updates (concurrent transfers)
3. Sequence number generation (duplicate IDs)
4. Rate limiter counters (undercounting)
5. Any counter, gauge, or accumulator in a concurrent system
</think>

This is a **lost update race condition**. The read-modify-write pattern loses updates under concurrency.

```
Thread A: reads like_count = 100
Thread B: reads like_count = 100 (same stale value)
Thread A: writes like_count = 101
Thread B: writes like_count = 101  ← Should be 102! Lost update.
```

**Fix — use atomic database operations:**
```python
def like_post(post_id, user_id):
    # Atomic increment — database handles concurrency
    db.session.execute(
        text("UPDATE posts SET like_count = like_count + 1 WHERE id = :id"),
        {"id": post_id}
    )
    Like.create(post_id=post_id, user_id=user_id)
    db.session.commit()
```

Or with SQLAlchemy:
```python
Post.query.filter_by(id=post_id).update(
    {Post.like_count: Post.like_count + 1}
)
```

**The generalizable lesson: Identify shared mutable state FIRST.**

Before writing any code that modifies data, ask:
1. Can two users/threads/processes modify this simultaneously?
2. If yes: use atomic operations, locks, or transactions
3. **Never** read-modify-write shared state in application code

**The pattern that ALWAYS causes this bug:**
```python
# BAD: Read-Modify-Write in application code
value = db.read()        # Read
new_value = value + 1     # Modify (in app memory)
db.write(new_value)      # Write (may overwrite another thread's write)

# GOOD: Atomic operation in database
db.execute("UPDATE SET value = value + 1")  # Atomic
```

**Where this same mistake appears:**
- Inventory management (overselling)
- Account balances (double-spending)
- Rate limiting counters (undercounting allows bypass)
- Any counter in a multi-user or multi-worker system'''
    ),
    (
        "thinking/meta-mistakes-wrong-abstraction-early",
        r'''I created a generic DataProcessor class to handle CSV, JSON, and XML parsing. After 3 months, every new file format requires modifying 5 methods and the class is 800 lines long. What went wrong?

```python
class DataProcessor:
    def __init__(self, format_type):
        self.format_type = format_type

    def parse(self, data):
        if self.format_type == 'csv':
            return self._parse_csv(data)
        elif self.format_type == 'json':
            return self._parse_json(data)
        elif self.format_type == 'xml':
            return self._parse_xml(data)
        elif self.format_type == 'parquet':
            # Added later, required changes to parse, validate, transform, load, export
            return self._parse_parquet(data)

    def validate(self, data):
        if self.format_type == 'csv':
            # CSV validation logic...
        elif self.format_type == 'json':
            # JSON validation logic (completely different)...
        # ... 5 methods × 4 formats = 20 code paths
```''',
        r'''<think>
I made an error: I created a wrong abstraction — a single class trying to handle all formats through if/elif chains.

The mistake was: Abstracting too early and choosing the wrong abstraction boundary. The assumption was "all file formats share the same interface," but in reality, CSV, JSON, and XML have fundamentally different parsing, validation, and transformation needs. The "shared interface" is superficial — the implementations share almost no code.

The root cause was: Premature abstraction. I created the generic class after seeing only 2-3 formats and assumed the pattern would hold. But each new format required touching every method because the formats don't actually share behavior — they just share method names.

Generalizable lesson: **Wait for 3 concrete examples before abstracting, and only abstract shared BEHAVIOR, not shared NAMES.** If the implementations are completely different inside each method, the abstraction is wrong — you just have a big switch statement.

Checklist item: Before creating a generic/abstract class, check: do the implementations actually SHARE code, or do they just share method signatures? If they share only signatures, use separate classes.

Similar situations:
1. Generic "NotificationService" with if/elif for email, SMS, push (completely different implementations)
2. Universal "PaymentProcessor" for Stripe, PayPal, crypto (nothing shared)
3. Generic "DatabaseAdapter" for SQL, MongoDB, Redis (fundamentally different paradigms)
</think>

The problem is a **wrong abstraction**. You created a single class that pretends formats are similar when they're fundamentally different.

**What you have:** A big switch statement pretending to be a class.
```python
# Every method is just:
if csv: do_csv_thing()
elif json: do_completely_different_json_thing()
elif xml: do_yet_another_xml_thing()
# No shared behavior — just shared method names
```

**What you should have:** Separate classes per format.
```python
class CsvProcessor:
    def parse(self, data): ...   # CSV-specific
    def validate(self, data): ... # CSV-specific

class JsonProcessor:
    def parse(self, data): ...   # JSON-specific
    def validate(self, data): ... # JSON-specific

# Adding Parquet: create ParquetProcessor. Touch ZERO existing code.
```

**The generalizable lesson: Wait for 3 examples before abstracting. Only abstract shared BEHAVIOR, not shared NAMES.**

**How to tell your abstraction is wrong:**
- Adding a new variant requires changing multiple existing methods
- Each method has a big if/elif chain
- The implementations inside each branch share no code
- The class grows linearly with each new variant

**How to tell your abstraction is right:**
- Adding a new variant means adding ONE new class
- Existing code is untouched
- The implementations genuinely share behavior (not just method names)

**The Rule of Three:**
1. First implementation: just write it
2. Second implementation: notice the similarity, resist abstracting
3. Third implementation: NOW you have enough examples to see what's actually shared

**Where this mistake recurs:**
- Generic "handler" classes with format/type switches
- Universal "adapter" classes for unrelated external services
- "Base" classes where subclasses override everything'''
    ),
    (
        "thinking/meta-mistakes-premature-opt-cache",
        r'''I added Redis caching to every database query in our app before launch. After launch, we discovered that cached data was causing bugs — users would update their profile but see old data for up to an hour. We spent weeks debugging cache invalidation issues. What lesson should we take from this?''',
        r'''<think>
I made an error: Adding caching everywhere before measuring whether it was needed.

The mistake was: Premature optimization. I assumed all database queries would be slow and added caching proactively. But most queries were already fast (< 5ms), and the caching introduced cache invalidation bugs that took weeks to find and fix.

The root cause was: Optimizing based on ASSUMPTIONS instead of MEASUREMENTS. The cost of cache invalidation complexity far exceeded the (tiny) performance benefit of caching queries that were already fast.

Generalizable lesson: **Profile before optimizing. Measure the actual bottleneck before adding complexity to fix an assumed one.**

Checklist item: Before adding a performance optimization, ask: "Have I measured that this is actually slow? What's the actual number?" If you can't answer with specific milliseconds, you haven't profiled yet.

Similar situations:
1. Pre-sharding a database before it's needed
2. Adding a CDN before measuring load times
3. Rewriting Python code in C before profiling
4. Adding message queues for "scalability" before measuring throughput
5. Choosing a "fast" framework over a productive one without benchmarking
</think>

**The generalizable lesson: Profile before optimizing.**

**What went wrong:**
- Added caching to ALL queries (including fast ones that didn't need it)
- Cache invalidation bugs caused stale data for users
- Weeks spent debugging cache consistency instead of building features
- The performance "problem" being solved didn't actually exist

**The cost-benefit:**
```
Caching a 3ms query:
  Benefit:  Save ~2ms per request
  Cost:     Cache invalidation logic in every write path
            Stale data bugs
            Weeks of debugging
            Extra infrastructure (Redis)

Not caching a 3ms query:
  Benefit:  Zero bugs, zero complexity
  Cost:     3ms per request (invisible to users)
```

**Checklist before optimizing:**
1. **Measure first**: What's the actual response time? (`django-debug-toolbar`, `EXPLAIN ANALYZE`)
2. **Is it actually slow?** <50ms is fast. <200ms is acceptable. >500ms needs investigation.
3. **How often is it called?** A slow query called once/hour doesn't need caching.
4. **What's the simplest fix?** Maybe an index, not a cache.
5. **What's the invalidation cost?** Every cached query needs invalidation on every write.

**The principle that prevents this class of error:**
> "Premature optimization is the root of all evil" — Donald Knuth

But more practically: **Never add complexity to solve a problem you haven't measured.** Measure → identify bottleneck → fix bottleneck → measure again.

**Where this mistake recurs:**
- Adding message queues "for scalability" before measuring throughput
- Choosing microservices "for performance" before profiling the monolith
- Denormalizing database tables before measuring query performance
- Adding CDNs before measuring page load times'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
