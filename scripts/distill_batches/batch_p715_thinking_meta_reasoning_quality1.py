"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 1)
Scenarios: Comparing algorithms, database schemas, error handling
"""

PAIRS = [
    (
        "thinking/meta-reasoning-two-sort-approaches",
        r'''Compare these two approaches for sorting a list of users by their activity score, where ties should be broken by username alphabetically:

Approach A:
```python
def sort_users_a(users):
    return sorted(users, key=lambda u: (-u.score, u.username))
```

Approach B:
```python
def sort_users_b(users):
    by_name = sorted(users, key=lambda u: u.username)
    by_score = sorted(by_name, key=lambda u: u.score, reverse=True)
    return by_score
```

Which is better and why?''',
        r'''<think>
Let me evaluate both approaches on multiple axes.

**Correctness:**
Approach A: Uses a tuple key `(-u.score, u.username)`. Higher scores come first (negation), ties broken by username alphabetically. Single pass. Correct.

Approach B: First sorts by username, then sorts by score (descending). This works because Python's `sorted()` is stable — when two elements have equal sort keys, they maintain their relative order from the input. So after sorting by name, equal-score users are already in name order, and the stable sort by score preserves that. Correct.

Both are correct. Let me check edge cases:
- What if score is a float? Negation works for floats too. Both correct.
- What if username has mixed case? Both use the same comparison. Both correct.

**Performance:**
Approach A: One sort pass. O(n log n).
Approach B: Two sort passes. O(n log n) + O(n log n) = O(n log n). Same big-O, but 2x the constant factor. Also creates an intermediate sorted list (extra memory allocation).

**Readability:**
Approach A: Compact, but the negation trick for reverse sorting is a Python idiom that not everyone knows. The tuple key pattern is well-known to experienced Pythonistas.

Approach B: More explicit about the two-level sort, but requires understanding that sort stability makes this work. The WHY it works is less obvious than Approach A — you need to know that Python sorts are stable and that you sort by secondary key first, primary key second.

**Maintainability:**
Approach A: Easy to extend — add a third sort criterion by extending the tuple. Very clear what the sort order is.

Approach B: Gets complex with 3+ criteria — you'd need 3 separate sorts, in reverse priority order. The sort order is spread across multiple lines, making it harder to understand at a glance.

**Edge case: non-numeric scores:**
If score were a string or a type that doesn't support negation, Approach A's `-u.score` would fail. Approach B handles this with `reverse=True`. But for numeric scores, this isn't an issue.

**Winner:** Approach A. It's more concise, more performant (single pass), more maintainable (easy to extend), and once you know the tuple-key idiom, more readable. But Approach B is useful when the sort key can't be negated (e.g., sorting by string in reverse).
</think>

**Approach A is better: single-pass, more readable, more maintainable, and half the runtime.**

### Evaluation

| Axis | Approach A | Approach B |
|------|-----------|-----------|
| Correctness | Tuple key with negation ✓ | Stable sort chaining ✓ |
| Performance | One sort: O(n log n) | Two sorts: 2× O(n log n) |
| Readability | Sort order visible in one line | Sort order split across two calls |
| Maintainability | Add criteria → extend tuple | Add criteria → add another sort (reverse order!) |
| Memory | One allocation | Two allocations (intermediate list) |

### Why Approach A wins

```python
# Clear, extensible, single-pass:
sorted(users, key=lambda u: (-u.score, u.username, u.join_date))

# vs increasingly confusing:
step1 = sorted(users, key=lambda u: u.join_date)
step2 = sorted(step1, key=lambda u: u.username)
step3 = sorted(step2, key=lambda u: u.score, reverse=True)
# Wait, is the order right? Do I sort primary LAST or FIRST?
```

### When Approach B is better

When you can't negate the primary key:
```python
# Can't negate a string for reverse alphabetical:
# sorted(users, key=lambda u: (-u.name, u.score))  # TypeError!

# Approach B works:
by_score = sorted(users, key=lambda u: u.score)
by_name = sorted(by_score, key=lambda u: u.name, reverse=True)
```

Or use `functools.cmp_to_key` for complex custom ordering.

### The reasoning pattern
When comparing two algorithms for the same task, evaluate: correctness (both handle edge cases?), performance (time and space complexity), readability (can a new developer understand it?), and maintainability (how easily does it extend?). Often one approach dominates on most axes.'''
    ),
    (
        "thinking/meta-reasoning-two-db-schemas",
        r'''Compare these two database schemas for a tagging system (posts can have multiple tags, tags can belong to multiple posts):

Schema A (junction table):
```sql
CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200),
    content TEXT
);

CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE
);

CREATE TABLE post_tags (
    post_id INTEGER REFERENCES posts(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (post_id, tag_id)
);
```

Schema B (array column):
```sql
CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200),
    content TEXT,
    tags TEXT[]  -- PostgreSQL array
);
```

Which is better for a blog platform?''',
        r'''<think>
Let me evaluate both schemas on multiple axes.

**Query patterns for a blog:**
1. Get a post with its tags
2. Find all posts with a specific tag
3. Get all tags (tag cloud)
4. Add/remove tags from a post
5. Find posts with multiple tags (AND/OR)

**Schema A (junction table):**
1. Get post tags: `SELECT t.name FROM tags t JOIN post_tags pt ON pt.tag_id = t.id WHERE pt.post_id = ?` — requires a JOIN
2. Find by tag: `SELECT p.* FROM posts p JOIN post_tags pt ON pt.post_id = p.id JOIN tags t ON t.id = pt.tag_id WHERE t.name = 'python'` — indexed, efficient
3. Tag cloud: `SELECT t.name, COUNT(*) FROM tags t JOIN post_tags pt ON pt.tag_id = t.id GROUP BY t.name` — clean aggregation
4. Add tag: `INSERT INTO post_tags (post_id, tag_id) VALUES (?, ?)` — clean, but need to first ensure tag exists
5. Multiple tags: Standard SQL joins/intersections

**Schema B (array column):**
1. Get post tags: `SELECT tags FROM posts WHERE id = ?` — trivial, no join!
2. Find by tag: `SELECT * FROM posts WHERE 'python' = ANY(tags)` — can use GIN index, but less efficient than B-tree
3. Tag cloud: `SELECT unnest(tags), COUNT(*) FROM posts GROUP BY 1` — uses unnest, works but less natural
4. Add tag: `UPDATE posts SET tags = array_append(tags, 'python') WHERE id = ?` — simple
5. Multiple tags: `WHERE tags @> ARRAY['python', 'web']` — clean with array operators

**Correctness/Integrity:**
- Schema A: Foreign keys enforce tag existence. Can't have orphan references. Tag name uniqueness is guaranteed. Can add metadata to the relationship (e.g., `created_at` on post_tags).
- Schema B: No referential integrity. Typos create "new tags" (`"pythno"` vs `"python"`). Can't enforce tag name consistency. No relationship metadata.

**Performance:**
- Schema A: B-tree indexes on junction table are very fast for lookups. Standard query optimization applies.
- Schema B: GIN indexes on arrays work but are slower to update. Reads for a single post are faster (no join), but queries across posts are slower.

**Portability:**
- Schema A: Standard SQL — works on MySQL, SQLite, SQL Server, etc.
- Schema B: PostgreSQL-specific — `TEXT[]` and array operators are non-standard.

**Winner for a blog:** Schema A. The junction table approach is more normalized, has better data integrity, supports richer queries, and is portable. The array approach is tempting for simplicity but sacrifices too much: no referential integrity, no consistent tag names, and PostgreSQL-only.

BUT if this were a document store pattern (e.g., user preferences, feature flags) where the "tags" are owned entirely by the parent record and don't need independent querying, Schema B would be fine.
</think>

**Schema A (junction table) is better for a blog platform — it provides data integrity, better query performance at scale, and standard SQL portability.**

### Evaluation

| Axis | Schema A (junction) | Schema B (array) |
|------|-------------------|-----------------|
| Data integrity | FK constraints, unique tags ✓ | Typos create duplicates ✗ |
| Query "posts by tag" | JOIN with B-tree index (fast) | ANY() with GIN index (slower) |
| Tag cloud | Standard GROUP BY | Requires unnest() |
| Add metadata to relationship | Easy (add columns to post_tags) | Impossible |
| Portability | Standard SQL (any DB) | PostgreSQL only |
| Simple single-post read | Requires JOIN | Direct array access (faster) |
| Storage | Extra table + indexes | Compact (no extra table) |

### Schema A wins on integrity
```sql
-- Schema A: consistent tags guaranteed
INSERT INTO tags (name) VALUES ('python');  -- tag exists once
INSERT INTO post_tags (post_id, tag_id) VALUES (1, 42);  -- references valid tag

-- Schema B: no consistency
UPDATE posts SET tags = array_append(tags, 'pythno');  -- typo is now a "tag"
UPDATE posts SET tags = array_append(tags, 'Python');  -- case variant is separate
```

### Schema A wins on rich queries
```sql
-- "Posts tagged with BOTH python AND web":
-- Schema A:
SELECT p.* FROM posts p
WHERE p.id IN (
    SELECT post_id FROM post_tags WHERE tag_id IN
    (SELECT id FROM tags WHERE name IN ('python', 'web'))
    GROUP BY post_id HAVING COUNT(*) = 2
);

-- Schema B:
SELECT * FROM posts WHERE tags @> ARRAY['python', 'web'];
-- Simpler SQL, but GIN index scans are slower than B-tree
```

### When Schema B IS better
- Tags are owned by the post (not shared entities)
- No need for tag consistency or tag-level metadata
- Read-heavy workload on individual posts
- PostgreSQL is guaranteed
- Examples: user preferences, feature flags, search keywords

### The reasoning pattern
Database schema decisions depend on: data integrity requirements, query patterns, scale expectations, and portability needs. Many-to-many relationships almost always warrant a junction table unless the "many" side is truly ephemeral or unstructured data.'''
    ),
    (
        "thinking/meta-reasoning-two-error-strategies",
        r'''Compare these two error handling strategies for a payment processing function:

Strategy A (exceptions):
```python
class PaymentError(Exception):
    pass
class InsufficientFunds(PaymentError):
    pass
class CardDeclined(PaymentError):
    pass
class NetworkError(PaymentError):
    pass

def process_payment(amount, card):
    if not validate_card(card):
        raise CardDeclined("Card validation failed")
    if get_balance(card) < amount:
        raise InsufficientFunds(f"Need {amount}, have {get_balance(card)}")
    try:
        result = gateway.charge(card, amount)
    except ConnectionError:
        raise NetworkError("Payment gateway unreachable")
    return result
```

Strategy B (result types):
```python
from dataclasses import dataclass
from typing import Union

@dataclass
class PaymentSuccess:
    transaction_id: str
    amount: float

@dataclass
class PaymentFailure:
    reason: str
    code: str
    retryable: bool

def process_payment(amount, card) -> Union[PaymentSuccess, PaymentFailure]:
    if not validate_card(card):
        return PaymentFailure("Card validation failed", "CARD_DECLINED", False)
    if get_balance(card) < amount:
        return PaymentFailure(f"Insufficient funds", "INSUFFICIENT_FUNDS", False)
    try:
        result = gateway.charge(card, amount)
    except ConnectionError:
        return PaymentFailure("Gateway unreachable", "NETWORK_ERROR", True)
    return PaymentSuccess(result.id, amount)
```

Which approach is better for payment processing?''',
        r'''<think>
Let me evaluate both on multiple axes.

**Correctness (handling all cases):**
Both handle the same error cases. But Strategy B is more EXPLICIT about error handling — the return type `Union[PaymentSuccess, PaymentFailure]` forces callers to consider the failure case. With Strategy A, callers might forget to catch exceptions, leading to unhandled crashes.

However, Strategy A's exception hierarchy is valuable: catching `PaymentError` catches all payment-related errors, while specific catches like `InsufficientFunds` allow targeted handling.

**Caller code:**

Strategy A:
```python
try:
    result = process_payment(100, card)
    # handle success
except InsufficientFunds:
    # handle insufficient funds
except CardDeclined:
    # handle declined
except PaymentError:
    # handle other payment errors
```

Strategy B:
```python
result = process_payment(100, card)
if isinstance(result, PaymentSuccess):
    # handle success
elif result.code == "INSUFFICIENT_FUNDS":
    # handle insufficient funds
elif result.code == "CARD_DECLINED":
    # handle declined
```

Strategy A is more Pythonic. Strategy B is more explicit but relies on string matching for error codes, which is error-prone.

**Composability:**
Strategy A: Exceptions bubble up automatically. If `process_payment` is called deep in a call stack, the error propagates to wherever it's caught — no need to manually propagate.

Strategy B: Each caller MUST check the result and propagate the failure. In a deep call stack, this means EVERY intermediate function must check and forward `PaymentFailure`. This is the "Result type propagation" problem.

**Rich error info:**
Strategy B has `retryable: bool` — this is very useful! Strategy A would need to add this to exception classes or use isinstance checks. Strategy B makes it a first-class concept.

**Type checking:**
Strategy B: mypy can verify that callers handle both `PaymentSuccess` and `PaymentFailure` (with `Union` and exhaustive checking). Strategy A: mypy can't easily check if callers handle all exceptions.

**Python ecosystem:**
Python idiom favors exceptions for errors. The standard library, Django, Flask, SQLAlchemy — all use exceptions. Using result types in Python feels foreign and creates friction with the ecosystem.

**For payment processing specifically:**
Payments have clear success/failure outcomes. The `retryable` field in Strategy B is genuinely valuable — callers need to know whether to retry (network error) or give up (card declined). This is harder to express with exception hierarchies.

**Winner:** For Python specifically, Strategy A (exceptions) is better because it aligns with Python idioms, has automatic propagation, and the exception hierarchy handles different error types cleanly. BUT I'd steal the `retryable` concept from Strategy B and add it to the exceptions.

In languages with algebraic types (Rust, Haskell, TypeScript), Strategy B (result types) would be better.
</think>

**For Python, Strategy A (exceptions) is better — it's more idiomatic, auto-propagates, and aligns with the ecosystem. But Strategy B's `retryable` concept is worth stealing.**

### Evaluation

| Axis | Strategy A (exceptions) | Strategy B (result types) |
|------|------------------------|--------------------------|
| Python idiom | ✓ Standard pattern | ✗ Unusual for Python |
| Auto-propagation | ✓ Bubbles up call stack | ✗ Must check at every level |
| Caller must handle | ✗ Can forget try/except | ✓ Must handle Union type |
| Rich error data | Can add to exception | `retryable` field is great |
| Type checking | mypy limited | mypy can verify exhaustive |
| Ecosystem fit | Django/Flask use exceptions | Requires custom patterns |
| Composability | ✓ Works with middleware | ✗ Every function must forward |

### Why auto-propagation matters for payments
```python
# Strategy A: errors propagate naturally
def checkout(cart, card):
    for item in cart.items:
        process_payment(item.price, card)  # exception bubbles up
    send_confirmation(cart)

# Strategy B: manual propagation at every level
def checkout(cart, card):
    for item in cart.items:
        result = process_payment(item.price, card)
        if isinstance(result, PaymentFailure):
            return result  # must explicitly propagate!
    send_confirmation(cart)
    return CheckoutSuccess(...)
```

### Best of both: exceptions with rich data
```python
class PaymentError(Exception):
    def __init__(self, message, code, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

class InsufficientFunds(PaymentError):
    def __init__(self, message):
        super().__init__(message, "INSUFFICIENT_FUNDS", retryable=False)

class NetworkError(PaymentError):
    def __init__(self, message):
        super().__init__(message, "NETWORK_ERROR", retryable=True)
```

### Context matters: language changes the answer
| Language | Better approach | Why |
|----------|----------------|-----|
| Python | Exceptions (Strategy A) | Ecosystem uses exceptions |
| Rust | Result<T, E> (Strategy B) | No exceptions; Result is idiomatic |
| Go | (value, error) (Strategy B) | Multiple returns are idiomatic |
| TypeScript | Result type (Strategy B) | Union types + exhaustive checking |

### The reasoning pattern
Error handling strategy depends heavily on language idiom. The "right" approach in Rust (Result types) is the "wrong" approach in Python (exceptions), and vice versa. Always prioritize consistency with your language's ecosystem over theoretical purity.'''
    ),
    (
        "thinking/meta-reasoning-two-caching-strategies",
        r'''Compare these two caching strategies for a product catalog API:

Strategy A (cache-aside / lazy loading):
```python
def get_product(product_id):
    cached = redis.get(f"product:{product_id}")
    if cached:
        return json.loads(cached)

    product = db.query(Product).get(product_id)
    redis.setex(f"product:{product_id}", 300, json.dumps(product.to_dict()))
    return product.to_dict()
```

Strategy B (write-through):
```python
def get_product(product_id):
    cached = redis.get(f"product:{product_id}")
    if cached:
        return json.loads(cached)
    # Cache miss — shouldn't happen if write-through is working
    product = db.query(Product).get(product_id)
    return product.to_dict()

def update_product(product_id, data):
    product = db.query(Product).get(product_id)
    product.update(data)
    db.commit()
    # Immediately update cache
    redis.setex(f"product:{product_id}", 300, json.dumps(product.to_dict()))
    return product.to_dict()
```

Which is better for an e-commerce product catalog?''',
        r'''<think>
Let me evaluate both strategies.

**Cache-aside (Strategy A):**
- Cache is populated on first read (lazy loading)
- Cache miss → read from DB → populate cache
- TTL-based expiration (300 seconds)
- Writes go directly to DB; cache is NOT updated on write
- Stale data possible for up to 300 seconds after update

**Write-through (Strategy B):**
- Cache is updated on every write
- Reads always hit cache (after warmup)
- Cache miss only on cold start or TTL expiration
- Writes update DB AND cache atomically
- Less stale data (only stale if cache and DB update are not truly atomic)

**Consistency:**
- Strategy A: After a product price change, the old price is served for up to 300 seconds. For an e-commerce site, this means users could see stale prices — potentially leading to overcharging or undercharging.
- Strategy B: Cache is updated immediately on write. Users see the new price almost instantly. Better consistency.

But wait — Strategy B's `update_product` could fail between `db.commit()` and `redis.setex()`. If the cache update fails, the cache has stale data. You'd need a try/except and cache invalidation fallback.

**Performance:**
- Strategy A: Cold reads are slow (DB + cache write). Subsequent reads are fast. Writes are fast (no cache update overhead).
- Strategy B: Reads are consistently fast (always cached after warmup). Writes are slightly slower (DB + cache update). But for a product catalog, reads vastly outnumber writes.

**Complexity:**
- Strategy A: Simpler — cache logic is only in reads. No need to touch write paths.
- Strategy B: More complex — every write path must update the cache. If you miss one write path (admin UI, bulk import, direct DB update), the cache goes stale.

**For an e-commerce product catalog specifically:**
- Products change infrequently (prices updated a few times a day)
- Products are read constantly (every page view)
- Price consistency matters (legal/financial implications)
- Strategy B is better because price consistency is critical

But the BEST approach might be a hybrid: cache-aside with cache invalidation on writes.
</think>

**For e-commerce, Strategy B (write-through) is better because price consistency is critical. But a hybrid approach is best.**

### Evaluation

| Axis | Cache-aside (A) | Write-through (B) |
|------|----------------|-------------------|
| Read performance | Slow on miss, fast on hit | Consistently fast |
| Write performance | Fast (no cache update) | Slightly slower (DB + cache) |
| Data freshness | Stale up to TTL (300s) | Immediately fresh |
| Implementation complexity | Simple (read-only logic) | Every write must update cache |
| Risk of stale data | 300s window | Only if cache update fails |
| Cold start | Many cache misses | Many cache misses (same) |

### Why consistency matters for e-commerce
```
Strategy A scenario:
1. Admin changes widget price from $10 to $15
2. For 300 seconds, users see $10 (cached)
3. User buys at $10, expects $10 charge
4. System charges $15 (from DB) → customer dispute!

Strategy B scenario:
1. Admin changes widget price from $10 to $15
2. Cache updated immediately
3. Users see $15 within milliseconds
```

### The best approach: cache-aside with invalidation (hybrid)
```python
def get_product(product_id):
    cached = redis.get(f"product:{product_id}")
    if cached:
        return json.loads(cached)
    product = db.query(Product).get(product_id)
    redis.setex(f"product:{product_id}", 3600, json.dumps(product.to_dict()))
    return product.to_dict()

def update_product(product_id, data):
    product = db.query(Product).get(product_id)
    product.update(data)
    db.commit()
    # INVALIDATE (don't update) — next read will repopulate
    redis.delete(f"product:{product_id}")
    return product.to_dict()
```

Invalidation (delete) is safer than update: if the delete fails, the TTL still handles expiration. If a write-through update fails, the cache has permanently stale data until TTL.

### When to use each
| Pattern | Best for |
|---------|----------|
| Cache-aside | Read-heavy, staleness OK (blog posts, static content) |
| Write-through | Consistency critical (prices, inventory, account data) |
| Cache-aside + invalidation | Best of both (hybrid) |
| Write-behind | Write-heavy, eventual consistency OK (analytics, logs) |

### The reasoning pattern
Caching strategy depends on the read/write ratio AND consistency requirements. For data where staleness has financial or legal consequences (prices, inventory, balances), prioritize consistency. For data where eventual consistency is acceptable (blog posts, user profiles), optimize for simplicity.'''
    ),
    (
        "thinking/meta-reasoning-two-testing-approaches",
        r'''Compare these two approaches for testing a UserService:

Approach A (mocking):
```python
from unittest.mock import Mock, patch

class TestUserService:
    def test_create_user(self):
        mock_repo = Mock()
        mock_repo.find_by_email.return_value = None
        mock_repo.save.return_value = User(id=1, name="Alice", email="alice@test.com")

        service = UserService(mock_repo)
        user = service.create_user("Alice", "alice@test.com")

        assert user.name == "Alice"
        mock_repo.find_by_email.assert_called_once_with("alice@test.com")
        mock_repo.save.assert_called_once()

    def test_create_user_duplicate_email(self):
        mock_repo = Mock()
        mock_repo.find_by_email.return_value = User(id=1, name="Bob", email="alice@test.com")

        service = UserService(mock_repo)
        with pytest.raises(DuplicateEmailError):
            service.create_user("Alice", "alice@test.com")
```

Approach B (integration test):
```python
class TestUserService:
    def setup_method(self):
        self.db = create_test_database()
        self.repo = UserRepository(self.db)
        self.service = UserService(self.repo)

    def teardown_method(self):
        self.db.rollback()

    def test_create_user(self):
        user = self.service.create_user("Alice", "alice@test.com")

        assert user.name == "Alice"
        assert user.id is not None
        # Verify in database
        db_user = self.repo.find_by_email("alice@test.com")
        assert db_user.name == "Alice"

    def test_create_user_duplicate_email(self):
        self.service.create_user("Bob", "alice@test.com")
        with pytest.raises(DuplicateEmailError):
            self.service.create_user("Alice", "alice@test.com")
```

Which testing approach is better?''',
        r'''<think>
Let me evaluate both approaches.

**Approach A (mocking):**
Pros:
- Fast (no database, no I/O)
- Tests ONLY the service logic in isolation
- Easy to test edge cases (mock any return value)
- No test infrastructure needed

Cons:
- Tests mock behavior, not real behavior
- If UserRepository.save() changes its interface, tests still pass but production breaks
- Over-mocking: `mock_repo.save.assert_called_once()` tests implementation details, not behavior
- Fragile: refactoring the service's internal calls to the repo requires changing all tests
- False confidence: tests pass even if the SQL in UserRepository is wrong

**Approach B (integration test):**
Pros:
- Tests real behavior end-to-end (service + repo + database)
- Catches integration issues (SQL errors, constraint violations)
- More refactoring-friendly — tests behavior, not implementation
- Higher confidence that the system actually works

Cons:
- Slower (database setup/teardown per test)
- Requires test database infrastructure
- Harder to test edge cases that require specific database states
- Tests might fail for infrastructure reasons (database down)

**What matters most for UserService?**
The service's value is in coordinating between the repository and business rules. If we mock the repository, we're only testing the coordination logic — but the most common bugs are in the repository (wrong SQL) or in the integration (wrong data types, wrong column names). Mocking misses these.

**The assert_called_once pattern is a red flag:**
```python
mock_repo.save.assert_called_once()
```
This tests HOW the service is implemented, not WHAT it does. If someone refactors to call `save_batch` instead of `save`, the test breaks even though behavior is identical.

**Best practice for this case:**
For business logic with clear inputs and outputs, mocking is fine. For data access coordination (which is what UserService does), integration tests are more valuable.

**The ideal:** BOTH. Fast unit tests for business logic (calculation, validation), integration tests for data flow.
</think>

**For a UserService that coordinates data access, Approach B (integration tests) provides higher confidence. But the ideal is both.**

### Evaluation

| Axis | Approach A (mocking) | Approach B (integration) |
|------|---------------------|------------------------|
| Speed | Fast (~ms) | Slower (~100ms per test) |
| Confidence | Tests service logic only | Tests full stack (service + repo + DB) |
| Catches SQL bugs | No | Yes |
| Catches type mismatches | No | Yes |
| Refactoring resilience | Low (tests implementation) | High (tests behavior) |
| Edge case testing | Easy (mock any state) | Harder (must set up DB state) |
| Infrastructure needed | None | Test database |

### Why mocking is risky here
```python
# Test passes with mock:
mock_repo.find_by_email.return_value = None
# But in production, find_by_email might:
# - Use wrong SQL column name
# - Return wrong type
# - Throw unexpected exception
# None of this is caught by the mock test!
```

### The assert_called_once anti-pattern
```python
mock_repo.save.assert_called_once()  # tests HOW, not WHAT

# If someone refactors to use save_batch():
# - Behavior: identical (user is saved)
# - Mock test: FAILS (save not called!)
# - Integration test: PASSES (user is in DB!)
```

### The right approach: testing pyramid
```python
# Unit tests (fast, many): Pure logic without I/O
def test_validate_email_format():
    assert is_valid_email("alice@test.com")
    assert not is_valid_email("not-an-email")

# Integration tests (medium speed, some): Data flow
def test_create_user_persists_to_database():
    service = UserService(UserRepository(test_db))
    user = service.create_user("Alice", "alice@test.com")
    assert test_db.query(User).get(user.id).name == "Alice"

# E2E tests (slow, few): Full HTTP request
def test_create_user_api():
    response = client.post("/api/users", json={"name": "Alice", ...})
    assert response.status_code == 201
```

### When mocking IS appropriate
- External services (payment gateways, email APIs)
- Non-deterministic inputs (time, random)
- Expensive operations (file I/O, network calls)
- Testing error handling for failures you can't easily reproduce

### The reasoning pattern
Choose test strategy based on where bugs actually occur. For pure logic, unit tests are sufficient. For data coordination (services that glue repositories together), integration tests catch the bugs that mocking misses. Mock at system boundaries (external APIs), not at internal boundaries (your own repositories).'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
