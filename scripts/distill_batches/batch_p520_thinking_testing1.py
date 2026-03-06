"""Phase 1F: Foundation Thinking — Testing Strategy (Part 1/4)
Unit testing principles, test design, mocking strategies, test doubles."""

PAIRS = [
    (
        "thinking/testing-unit-vs-integration",
        "Our team debates whether to write unit tests or integration tests. We have limited time — which should we prioritize and why?",
        r'''<think>
This is the classic testing pyramid debate. Let me think about what actually catches bugs in practice.

Unit tests:
- Fast (milliseconds each)
- Test logic in isolation
- Catch algorithmic bugs, edge cases, off-by-one errors
- Don't catch integration issues (wrong DB query, HTTP serialization, config)
- Can be brittle if they test implementation details

Integration tests:
- Slower (seconds each)
- Test components working together
- Catch wiring bugs, serialization, database queries
- More realistic but harder to pinpoint failures
- Fewer needed because each test covers more surface area

The answer isn't either/or — it's about ROI. Different kinds of code benefit from different test types.

The testing trophy (Kent C. Dodds) and testing pyramid (Google) both agree:
- Logic-heavy code → unit tests
- Glue/wiring code → integration tests
- User-facing flows → a few E2E tests
</think>

It's not either/or — different code needs different test types.

## The Testing Pyramid (Practical Version)

```
        /  E2E  \        ← Few: critical user journeys
       / Integr.  \      ← Medium: API endpoints, DB queries
      /   Unit     \     ← Many: business logic, algorithms
```

## What to Unit Test (fast, many)

Code with **logic, conditions, calculations**:
```python
# This HAS complex logic → unit test it
def calculate_shipping(weight, distance, tier):
    if tier == 'prime' and weight < 50:
        return Decimal(0)
    base = weight * Decimal('0.5')
    if distance > 1000:
        base *= Decimal('1.5')
    return base.quantize(Decimal('0.01'))

# Unit test: test every branch
def test_prime_free_shipping():
    assert calculate_shipping(10, 500, 'prime') == Decimal(0)

def test_heavy_prime_not_free():
    assert calculate_shipping(60, 500, 'prime') == Decimal('30.00')

def test_long_distance_surcharge():
    assert calculate_shipping(10, 1500, 'standard') == Decimal('7.50')
```

## What to Integration Test (slower, fewer)

Code that **wires components together**:
```python
# This is mostly glue → integration test it
def create_order_endpoint(request):
    data = OrderSchema().load(request.json)
    order = order_service.create(data)
    return jsonify(OrderSchema().dump(order)), 201

# Integration test: does the wiring work?
def test_create_order_endpoint(client, db):
    response = client.post('/api/orders', json={
        'product_id': 1, 'quantity': 2
    })
    assert response.status_code == 201
    assert Order.query.count() == 1
```

## Decision Framework

| Code Type | Test Type | Why |
|-----------|-----------|-----|
| Business rules, calculations | Unit | Many edge cases, fast feedback |
| Data transformations | Unit | Pure functions, easy to test |
| API endpoints | Integration | Tests serialization + routing + DB |
| Database queries | Integration | SQL correctness needs real DB |
| Third-party API calls | Unit (mocked) | Can't hit real APIs in CI |
| Critical user flows | E2E | Catches full-stack regressions |

## If You Only Have Time for One

Integration tests at the API level give the best ROI for web applications. One test covers routing, validation, business logic, database, and serialization. But add unit tests for any code with >3 branches.'''
    ),
    (
        "thinking/testing-what-to-mock",
        "I'm confused about mocking. Some people say 'mock everything', others say 'never mock'. When should I actually use mocks?\n\n```python\n# Should I mock the database? The email service? The clock? The filesystem?\ndef process_order(order_id):\n    order = db.get_order(order_id)           # Database\n    if order.created_at < datetime.now() - timedelta(days=30):\n        raise OrderExpired(order_id)          # Clock\n    receipt = generate_receipt(order)          # Pure function\n    save_receipt(receipt, f'/receipts/{order_id}.pdf')  # Filesystem\n    send_confirmation(order.user.email, receipt)  # Email\n    return order\n```",
        r'''<think>
The key insight: mock at boundaries, not at implementation details.

What to mock:
- Things you don't own (external APIs, email services)
- Things that are slow (databases in unit tests)
- Things that are non-deterministic (clocks, random)
- Things with side effects (file system, network, email)

What NOT to mock:
- Your own classes/functions (tests become tautological)
- Pure functions (no reason to mock — they're easy to call)
- Value objects and data structures

For this function:
- `db.get_order()` — mock in unit tests (slow), real in integration tests
- `datetime.now()` — freeze it (non-deterministic)
- `generate_receipt()` — DON'T mock (pure function, test the real thing)
- `save_receipt()` — mock (filesystem side effect)
- `send_confirmation()` — mock (external side effect)
</think>

**Mock at boundaries, never mock your own logic.**

## Decision Table for Your Code

```python
def process_order(order_id):
    order = db.get_order(order_id)           # ✅ MOCK — I/O, slow
    if order.created_at < datetime.now() - timedelta(days=30):
        raise OrderExpired(order_id)          # ✅ FREEZE — non-deterministic
    receipt = generate_receipt(order)          # ❌ DON'T MOCK — pure function
    save_receipt(receipt, f'/receipts/{order_id}.pdf')  # ✅ MOCK — side effect
    send_confirmation(order.user.email, receipt)  # ✅ MOCK — external service
    return order
```

## When to Mock

| Situation | Mock? | Why |
|-----------|-------|-----|
| External API (Stripe, S3) | Yes | Can't call real service in tests |
| Database | Sometimes | Mock in unit tests, real in integration |
| Email/SMS | Yes | Don't send real emails in tests |
| Clock (`datetime.now()`) | Yes | Tests must be deterministic |
| File system | Yes | Side effects, cleanup needed |
| Your own classes | **No** | Tests become implementation-coupled |
| Pure functions | **No** | Just call them — that's the point |
| Data objects | **No** | Just construct them |

## How to Mock Well

```python
# GOOD: Mock the boundary, test real logic
@freeze_time("2024-01-15")
def test_order_not_expired(mock_db, mock_email, mock_fs):
    mock_db.get_order.return_value = Order(
        id=1,
        created_at=datetime(2024, 1, 1),  # 14 days ago, not expired
        user=User(email='test@example.com'),
        items=[...],
    )

    result = process_order(1)

    assert result.id == 1
    mock_email.send_confirmation.assert_called_once()  # Email sent
    mock_fs.save_receipt.assert_called_once()           # Receipt saved

# BAD: Mocking your own function
def test_order_bad(mock_generate_receipt):
    mock_generate_receipt.return_value = "fake receipt"
    # Now you're testing that your code calls your code
    # You haven't tested that the receipt is actually correct
```

## The Golden Rule

> Mock things you don't control. Don't mock things you do.

If you mock `generate_receipt()`, you've tested that `process_order` calls it — but not that it works. When `generate_receipt` has a bug, this test still passes.'''
    ),
    (
        "thinking/testing-fixtures-factories",
        "Our tests are full of duplicated setup code. Every test creates the same objects slightly differently:\n\n```python\ndef test_order_total():\n    user = User(id=1, name='Alice', email='a@b.com', tier='gold')\n    product1 = Product(id=1, name='Widget', price=10.00, category='tools')\n    product2 = Product(id=2, name='Gadget', price=25.00, category='tools')\n    order = Order(user=user, items=[\n        OrderItem(product=product1, quantity=2),\n        OrderItem(product=product2, quantity=1),\n    ])\n    assert order.total == 45.00\n\ndef test_order_discount():\n    user = User(id=1, name='Bob', email='b@c.com', tier='platinum')\n    product = Product(id=1, name='Widget', price=100.00, category='electronics')\n    order = Order(user=user, items=[\n        OrderItem(product=product, quantity=1),\n    ])\n    order.apply_discount(10)\n    assert order.total == 90.00\n\ndef test_order_empty():\n    user = User(id=1, name='Charlie', email='c@d.com', tier='free')\n    order = Order(user=user, items=[])\n    assert order.total == 0\n\n# 200+ more tests with similar setup...\n```",
        r'''<think>
The solution is factories — functions or classes that create test objects with sensible defaults, allowing overrides for the specific things each test cares about.

Two approaches:
1. Simple factory functions
2. Factory libraries (factory_boy, faker)

For most cases, simple factory functions are sufficient and clearer.
</think>

Use **factory functions** with sensible defaults. Each test only specifies what it cares about:

```python
# conftest.py or factories.py

def make_user(**overrides):
    defaults = {
        'id': 1,
        'name': 'Test User',
        'email': 'test@example.com',
        'tier': 'free',
    }
    return User(**(defaults | overrides))

def make_product(**overrides):
    defaults = {
        'id': 1,
        'name': 'Test Product',
        'price': Decimal('10.00'),
        'category': 'general',
    }
    return Product(**(defaults | overrides))

def make_order(user=None, items=None, **overrides):
    return Order(
        user=user or make_user(),
        items=items or [make_order_item()],
        **overrides,
    )

def make_order_item(product=None, quantity=1):
    return OrderItem(
        product=product or make_product(),
        quantity=quantity,
    )
```

Now tests are focused and readable:

```python
def test_order_total():
    order = make_order(items=[
        make_order_item(product=make_product(price=Decimal('10.00')), quantity=2),
        make_order_item(product=make_product(price=Decimal('25.00')), quantity=1),
    ])
    assert order.total == Decimal('45.00')

def test_order_discount():
    order = make_order(
        user=make_user(tier='platinum'),
        items=[make_order_item(product=make_product(price=Decimal('100.00')))],
    )
    order.apply_discount(10)
    assert order.total == Decimal('90.00')

def test_order_empty():
    order = make_order(items=[])
    assert order.total == Decimal('0')
```

## Key Principles

1. **Defaults for everything** — tests only specify what they're testing
2. **Composable** — `make_order` uses `make_user` and `make_order_item` internally
3. **Readable** — `make_user(tier='platinum')` is clearer than 4 lines of User()
4. **One source of truth** — when `User` gets a new required field, update one factory

For larger projects, use `factory_boy`:
```python
class UserFactory(factory.Factory):
    class Meta:
        model = User
    id = factory.Sequence(lambda n: n)
    name = factory.Faker('name')
    email = factory.Faker('email')
    tier = 'free'
```'''
    ),
    (
        "thinking/testing-property-based",
        "I keep finding edge cases that my unit tests miss. For example, my string sanitizer passed all my hand-written tests but broke on Unicode input, empty strings, and strings with only whitespace. Is there a better way to find these edge cases?",
        r'''<think>
Property-based testing (PBT) with Hypothesis — instead of hand-picking inputs, define properties that should always hold and let the framework generate thousands of inputs to find counterexamples.

Key concepts:
- You define invariants/properties, not specific test cases
- The framework generates random inputs, including edge cases
- When it finds a failure, it shrinks the input to the minimal failing case
- It covers: empty strings, Unicode, very long strings, special characters, null bytes, etc.
</think>

**Property-based testing** — instead of hand-picking inputs, define properties that must always hold and let the framework find counterexamples:

```python
from hypothesis import given, strategies as st

# Your sanitizer
def sanitize(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()

# BEFORE: Hand-picked tests (miss edge cases)
def test_sanitize():
    assert sanitize('<b>hello</b>') == 'hello'
    assert sanitize('no tags') == 'no tags'
    assert sanitize('') == ''
    # Looks good... but what about Unicode? Null bytes? Nested tags?

# AFTER: Property-based tests (framework finds edge cases)
@given(st.text())
def test_sanitize_never_contains_tags(text):
    result = sanitize(text)
    assert '<' not in result or '>' not in result  # No complete tags

@given(st.text())
def test_sanitize_is_idempotent(text):
    once = sanitize(text)
    twice = sanitize(once)
    assert once == twice  # Sanitizing twice gives same result

@given(st.text())
def test_sanitize_preserves_plain_text(text):
    # If input has no tags, output should equal stripped input
    if '<' not in text:
        assert sanitize(text) == text.strip()

@given(st.text(min_size=1, alphabet=st.characters(blacklist_categories=('Cs',))))
def test_sanitize_never_crashes(text):
    # Should handle ANY valid string without exceptions
    result = sanitize(text)
    assert isinstance(result, str)
```

Hypothesis will try:
- Empty string `""`
- Single characters: `"<"`, `">"`, `"\x00"`, `"\n"`
- Unicode: `"こんにちは"`, `"🎉"`, RTL text, zero-width joiners
- Adversarial: `"<scrip"`, `"<>>"`, `"<<<>>>"`
- Very long strings, strings with only whitespace

## When to Use Property-Based Testing

| Scenario | Properties to Test |
|----------|-------------------|
| Serialization | `deserialize(serialize(x)) == x` (roundtrip) |
| Sorting | Output is ordered, same length, same elements |
| Encoding | Output is valid encoding, decode gives original |
| Sanitization | Idempotent, no forbidden patterns in output |
| Parsers | Never crashes, valid input → valid output |
| Math functions | Known mathematical properties hold |

```python
# Roundtrip property for JSON serialization
@given(st.dictionaries(st.text(), st.integers()))
def test_json_roundtrip(data):
    assert json.loads(json.dumps(data)) == data

# Sorting properties
@given(st.lists(st.integers()))
def test_sort_properties(lst):
    result = sorted(lst)
    assert len(result) == len(lst)           # Same length
    assert all(a <= b for a, b in zip(result, result[1:]))  # Ordered
    assert sorted(result) == result          # Idempotent
```

Install: `pip install hypothesis`. It finds bugs your hand-written tests never will.'''
    ),
    (
        "thinking/testing-tdd-workflow",
        "My team wants to try TDD but we struggle with the workflow. We either write too many tests upfront or skip to writing code first. Show me the actual TDD cycle with a real example.",
        r'''<think>
TDD's Red-Green-Refactor cycle with a concrete example. Let me pick something practical — implementing a password strength validator, step by step.

Key TDD principles:
1. Write ONE failing test
2. Write MINIMAL code to pass it
3. Refactor if needed
4. Repeat

Common mistakes:
- Writing all tests first (that's not TDD)
- Writing more code than needed to pass the test
- Skipping the refactor step
</think>

TDD = **Red → Green → Refactor**, one test at a time. Here's a real example: building a password strength checker.

## Cycle 1: Simplest Case

```python
# RED: Write one failing test
def test_empty_password_is_weak():
    assert check_strength('') == 'weak'

# Run: FAIL — check_strength doesn't exist
```

```python
# GREEN: Minimal code to pass
def check_strength(password):
    return 'weak'

# Run: PASS ✅
```

## Cycle 2: Next Requirement

```python
# RED: Strong password
def test_strong_password():
    assert check_strength('MyP@ssw0rd!') == 'strong'

# Run: FAIL — returns 'weak' for everything
```

```python
# GREEN: Add just enough logic
def check_strength(password):
    if len(password) >= 8 and any(c.isupper() for c in password) \
       and any(c.isdigit() for c in password) and any(c in '!@#$%' for c in password):
        return 'strong'
    return 'weak'

# Run: PASS ✅
```

## Cycle 3: Medium Strength

```python
# RED
def test_medium_password():
    assert check_strength('Password1') == 'medium'

# Run: FAIL — no 'medium' path
```

```python
# GREEN
def check_strength(password):
    if len(password) < 8:
        return 'weak'

    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in '!@#$%^&*' for c in password)

    score = sum([has_upper, has_digit, has_special])

    if score >= 3:
        return 'strong'
    elif score >= 2:
        return 'medium'
    return 'weak'

# Run: PASS ✅
```

## Cycle 4: Refactor (Code Smells)

```python
# REFACTOR: Extract the criteria
CRITERIA = [
    lambda p: any(c.isupper() for c in p),
    lambda p: any(c.islower() for c in p),
    lambda p: any(c.isdigit() for c in p),
    lambda p: any(c in '!@#$%^&*()' for c in p),
]

def check_strength(password):
    if len(password) < 8:
        return 'weak'
    score = sum(1 for check in CRITERIA if check(password))
    if score >= 4:
        return 'strong'
    if score >= 2:
        return 'medium'
    return 'weak'

# Run all tests: PASS ✅ — refactoring didn't break anything
```

## Cycle 5-N: Add Edge Cases

```python
def test_short_password_with_special_chars():
    assert check_strength('A1!') == 'weak'  # Too short

def test_only_lowercase():
    assert check_strength('abcdefgh') == 'weak'  # Only 1 criterion

def test_common_password():
    assert check_strength('Password1!') == 'strong'  # Wait, should common passwords be rejected?
    # This test makes us THINK about the requirement before coding it
```

## TDD Rules

1. **Never write code without a failing test first** — if all tests pass, you're not doing TDD
2. **Write the MINIMUM code** to pass the current test — resist adding "obvious" features
3. **One test at a time** — don't write 10 tests then implement
4. **Refactor only when green** — all tests pass before you restructure
5. **Tests drive the design** — if it's hard to test, the design needs to change'''
    ),
    (
        "thinking/testing-snapshot-testing",
        "We have complex API responses and HTML templates. Writing assertions for every field is tedious and brittle. Is there a better approach?\n\n```python\ndef test_user_profile_response():\n    response = client.get('/api/users/1/profile')\n    data = response.json()\n    assert data['id'] == 1\n    assert data['name'] == 'Alice'\n    assert data['email'] == 'alice@example.com'\n    assert data['profile']['bio'] == 'Developer'\n    assert data['profile']['avatar_url'] == 'https://...'\n    assert data['stats']['posts'] == 42\n    assert data['stats']['followers'] == 100\n    assert data['stats']['following'] == 50\n    assert len(data['recent_posts']) == 5\n    assert data['recent_posts'][0]['title'] == 'My First Post'\n    # ... 30 more assertions\n```",
        r'''<think>
Snapshot testing — save the expected output once, then compare against the snapshot on future runs. Good for complex outputs where manual assertions are tedious.

But there are caveats:
- Snapshots can become "golden master" tests that nobody reviews
- Dynamic fields (timestamps, IDs) need to be handled
- Large snapshots are hard to review in PRs

The right approach: use snapshots for structure, manual assertions for behavior.
</think>

**Snapshot testing** — save the expected output once, auto-compare on future runs:

## With pytest + syrupy

```python
# First run: creates snapshot file automatically
def test_user_profile_response(snapshot, client, fixed_user):
    response = client.get('/api/users/1/profile')
    assert response.json() == snapshot

# Snapshot stored in __snapshots__/test_api.ambr:
# {
#   "id": 1,
#   "name": "Alice",
#   "email": "alice@example.com",
#   "profile": {"bio": "Developer", "avatar_url": "..."},
#   "stats": {"posts": 42, "followers": 100, "following": 50},
#   "recent_posts": [...]
# }
```

When the response changes, the test fails and shows a diff. Update with `pytest --snapshot-update`.

## Handle Dynamic Fields

```python
# Problem: timestamps and IDs change every run
def test_user_response(snapshot, client):
    response = client.get('/api/users/1')
    data = response.json()

    # Replace dynamic fields before snapshot comparison
    data['created_at'] = 'TIMESTAMP'
    data['session_id'] = 'SESSION_ID'
    assert data == snapshot

# OR use a custom matcher:
from syrupy.matchers import path_type

def test_user_response(snapshot, client):
    assert client.get('/api/users/1').json() == snapshot(
        matcher=path_type({
            "created_at": (str,),
            "session_id": (str,),
        })
    )
```

## When to Use Snapshots vs Manual Assertions

| Use Snapshots | Use Manual Assertions |
|---------------|----------------------|
| Complex API responses (20+ fields) | Simple return values |
| HTML/email templates | Business logic results |
| Serialized data structures | Calculated values |
| Error message formats | State transitions |
| GraphQL responses | Counts and aggregates |

## Snapshot Testing Rules

1. **Review snapshot diffs in PRs** — don't blindly `--snapshot-update`
2. **Handle dynamic values** — timestamps, UUIDs, random values
3. **Keep snapshots small** — if a snapshot is 500 lines, you're testing too much at once
4. **Combine with behavior tests** — snapshots test structure, manual assertions test logic

```python
# GOOD: Snapshot for structure + assertion for behavior
def test_order_response(snapshot, client):
    response = client.post('/api/orders', json={...})
    assert response.status_code == 201          # Behavior
    assert response.json() == snapshot           # Structure

# BAD: Only snapshot, no behavior test
def test_order_response(snapshot, client):
    assert client.post('/api/orders', json={...}).json() == snapshot
    # If the snapshot is wrong, the test still "passes"
```'''
    ),
    (
        "thinking/testing-mutation-testing",
        "Our test suite has 95% code coverage but we keep finding bugs in production. How is that possible?",
        r'''<think>
Code coverage measures which lines are EXECUTED, not which behaviors are VERIFIED. A test can run every line without asserting anything meaningful.

Example:
```python
def test_calculate():
    result = calculate(10, 5)  # Lines executed = 100% coverage
    # No assertion! Or: assert result is not None (meaningless)
```

Mutation testing fixes this — it modifies the source code (introduces bugs) and checks if the tests catch them. If a mutation survives (tests still pass), your tests are weak.
</think>

**Code coverage lies.** It measures lines *executed*, not behaviors *verified*. Example:

```python
def calculate_discount(price, is_member):
    if is_member:
        return price * 0.9
    return price

# "100% coverage" but terrible test:
def test_discount():
    result = calculate_discount(100, True)
    assert result is not None  # Passes even if discount is wrong!
```

Every line runs. Coverage says 100%. But if you change `0.9` to `0.5`, the test still passes.

## Mutation Testing Finds This

Mutation testing modifies your source code and checks if tests catch the change:

```python
# Mutation 1: Change 0.9 → 0.5
def calculate_discount(price, is_member):
    if is_member:
        return price * 0.5  # MUTANT
    return price

# If tests still pass → SURVIVED → your tests are weak

# Mutation 2: Change 0.9 → 1.0
# Mutation 3: Remove the if branch
# Mutation 4: Change * to +
# Mutation 5: Return 0 instead
```

## Using mutmut (Python)

```bash
pip install mutmut
mutmut run --paths-to-mutate=src/pricing.py --tests-dir=tests/
mutmut results
```

Output:
```
Survived:  3  ← Tests don't catch these mutations (WEAK TESTS)
Killed:   12  ← Tests caught these mutations (STRONG TESTS)
Timeout:   1
Score: 80% (want >90%)

Survived mutants:
  Line 3: changed * to + in calculate_discount
  Line 5: changed return price to return 0
  Line 3: changed 0.9 to 0.95
```

## Fixing Survived Mutants

```python
# ADD specific assertions that kill the mutants:
def test_member_gets_10_percent_off():
    assert calculate_discount(100, True) == 90  # Kills 0.9→0.5, *→+

def test_non_member_pays_full_price():
    assert calculate_discount(100, False) == 100  # Kills return 0

def test_discount_is_proportional():
    assert calculate_discount(200, True) == 180  # Kills 0.9→0.95
```

## When to Use Mutation Testing

| Good candidates | Not worth it |
|----------------|--------------|
| Business logic (pricing, permissions) | UI rendering |
| Security-critical code (auth, validation) | Glue/wiring code |
| Financial calculations | Third-party API wrappers |
| Algorithms | Configuration |

**Rule**: High coverage + low mutation score = tests that run code without checking it. Mutation testing tells you if your tests actually *verify* behavior.'''
    ),
    (
        "thinking/testing-flaky-tests",
        "About 10% of our CI runs fail with flaky tests. We re-run and they pass. It's slowing us down and eroding trust in the test suite. How do we fix this?",
        r'''<think>
Common causes of flaky tests:
1. Time-dependent tests (use real clock)
2. Test ordering dependencies (shared state between tests)
3. Async/timing issues (race conditions in tests)
4. External service dependencies (APIs, databases)
5. Resource exhaustion (ports, file handles)
6. Non-deterministic data (random, UUID-based ordering)
7. Shared database state (tests don't clean up)

The fix isn't "add retries" — that hides the problem. You need to find and fix the root causes.
</think>

Flaky tests have root causes. Here's how to find and fix each type:

## 1. Time-Dependent Tests

```python
# FLAKY: Passes at 11:59, fails at 12:00
def test_greeting():
    assert get_greeting() == "Good morning"

# FIXED: Freeze time
@freeze_time("2024-01-15 09:00:00")
def test_greeting():
    assert get_greeting() == "Good morning"
```

## 2. Test Order Dependencies

```python
# FLAKY: test_B depends on test_A's side effects
def test_create_user():
    db.create_user(email='alice@test.com')

def test_list_users():
    users = db.list_users()
    assert len(users) == 1  # Fails if test_create_user didn't run first

# FIXED: Each test sets up its own state
def test_list_users():
    db.create_user(email='alice@test.com')  # Own setup
    users = db.list_users()
    assert len(users) >= 1  # Doesn't assume exact count
```

**Detect**: Run tests in random order with `pytest-randomly`.

## 3. Async/Timing Issues

```python
# FLAKY: Background task might not finish in time
def test_async_processing():
    submit_job(data)
    time.sleep(2)  # Sometimes 2 seconds isn't enough
    assert job_is_complete(data)

# FIXED: Poll with timeout
def test_async_processing():
    submit_job(data)
    wait_until(lambda: job_is_complete(data), timeout=10, interval=0.1)
```

## 4. Shared Database State

```python
# FLAKY: Previous test's data leaks into this test
def test_unique_email():
    create_user('alice@test.com')  # Fails if 'alice' already exists

# FIXED: Transaction rollback per test
@pytest.fixture(autouse=True)
def db_transaction(db):
    db.begin()
    yield
    db.rollback()  # Every test starts with clean state
```

## 5. Non-Deterministic Ordering

```python
# FLAKY: Set/dict ordering is arbitrary
def test_get_tags():
    tags = get_item_tags(item_id=1)
    assert tags == ['python', 'testing', 'ci']
    # Sometimes returns ['testing', 'python', 'ci']

# FIXED: Sort or use set comparison
def test_get_tags():
    tags = get_item_tags(item_id=1)
    assert set(tags) == {'python', 'testing', 'ci'}
```

## Systematic Fix Process

```bash
# Step 1: Identify flaky tests
pytest --count=10 -x  # Run 10 times, stop on first failure

# Step 2: Run in random order
pytest -p randomly --randomly-seed=last

# Step 3: Run in isolation
pytest tests/test_orders.py::test_specific -x  # Works alone?

# Step 4: Check for shared state
pytest --forked  # Each test in its own process
```

## Never Do This

```yaml
# WRONG: This hides flakiness, doesn't fix it
- run: pytest || pytest --lf || pytest --lf  # Just retry until it passes
```

Retries mask the bug. Fix the root cause instead.'''
    ),
    (
        "thinking/testing-test-boundaries",
        "I'm testing a service that calls an external payment API. I want to test error handling without hitting the real API. What are my options and which is best?\n\n```python\nclass PaymentService:\n    def __init__(self, api_client):\n        self.api = api_client\n    \n    def charge(self, amount, card_token):\n        try:\n            result = self.api.create_charge(\n                amount=amount, \n                currency='usd',\n                source=card_token\n            )\n            return PaymentResult(success=True, charge_id=result['id'])\n        except ApiRateLimitError:\n            raise RetryableError('Rate limited, try again')\n        except ApiCardDeclined as e:\n            return PaymentResult(success=False, error=str(e))\n        except ApiError as e:\n            logger.exception('Payment API error')\n            raise PaymentFailedError(str(e))\n```",
        r'''<think>
Options for testing external API interactions:
1. Mock the API client (mock object)
2. Fake implementation (in-memory fake)
3. Record/replay (VCR cassettes)
4. Contract tests

For this specific case, the API client is already injected (good design), so we can easily substitute test doubles.

The best approach depends on what we're testing:
- Unit testing the PaymentService logic → mock the api_client
- Testing our API client works with the real API → contract test / VCR
</think>

Your service already has the API client injected — that's the right design for testability. Here are your options:

## Option 1: Mock (Best for Unit Testing Logic)

```python
def test_successful_charge():
    mock_api = Mock()
    mock_api.create_charge.return_value = {'id': 'ch_123', 'status': 'succeeded'}

    service = PaymentService(mock_api)
    result = service.charge(1000, 'tok_visa')

    assert result.success is True
    assert result.charge_id == 'ch_123'
    mock_api.create_charge.assert_called_once_with(
        amount=1000, currency='usd', source='tok_visa'
    )

def test_card_declined():
    mock_api = Mock()
    mock_api.create_charge.side_effect = ApiCardDeclined('Card declined')

    service = PaymentService(mock_api)
    result = service.charge(1000, 'tok_declined')

    assert result.success is False
    assert 'declined' in result.error

def test_rate_limit_is_retryable():
    mock_api = Mock()
    mock_api.create_charge.side_effect = ApiRateLimitError()

    service = PaymentService(mock_api)
    with pytest.raises(RetryableError):
        service.charge(1000, 'tok_visa')

def test_api_error_raises_payment_failed():
    mock_api = Mock()
    mock_api.create_charge.side_effect = ApiError('Server error')

    service = PaymentService(mock_api)
    with pytest.raises(PaymentFailedError):
        service.charge(1000, 'tok_visa')
```

## Option 2: Fake (Best for Integration-Style Tests)

```python
class FakePaymentApi:
    """In-memory fake that simulates real API behavior."""
    def __init__(self):
        self.charges = {}
        self._next_id = 1
        self.decline_cards = {'tok_declined', 'tok_stolen'}

    def create_charge(self, amount, currency, source):
        if source in self.decline_cards:
            raise ApiCardDeclined('Card declined')
        if amount <= 0:
            raise ApiError('Invalid amount')

        charge_id = f'ch_fake_{self._next_id}'
        self._next_id += 1
        self.charges[charge_id] = {
            'id': charge_id, 'amount': amount,
            'currency': currency, 'status': 'succeeded',
        }
        return self.charges[charge_id]

def test_full_payment_flow():
    fake_api = FakePaymentApi()
    service = PaymentService(fake_api)

    result = service.charge(5000, 'tok_visa')
    assert result.success
    assert result.charge_id in fake_api.charges  # Can inspect state
```

## Option 3: VCR/Record-Replay (Best for API Client Testing)

```python
import vcr

@vcr.use_cassette('tests/cassettes/successful_charge.yaml')
def test_real_api_response_format():
    """First run hits real API and records. Future runs replay."""
    api = StripeApiClient(api_key='sk_test_...')
    result = api.create_charge(amount=1000, currency='usd', source='tok_visa')
    assert 'id' in result
    assert result['status'] == 'succeeded'
```

## When to Use What

| Approach | Use When | Don't Use When |
|----------|----------|----------------|
| Mock | Testing YOUR code's logic around the API | Testing the API client itself |
| Fake | Complex interactions, multi-step flows | Simple one-call tests |
| VCR | Verifying real API response format | Testing error handling logic |
| Contract test | API you own is changing | Third-party stable API |'''
    ),
    (
        "thinking/testing-parametrize",
        "I have a lot of similar tests that test the same function with different inputs. There's too much duplication:\n\n```python\ndef test_validate_email_valid():\n    assert validate_email('user@example.com') is True\n\ndef test_validate_email_subdomain():\n    assert validate_email('user@sub.example.com') is True\n\ndef test_validate_email_plus():\n    assert validate_email('user+tag@example.com') is True\n\ndef test_validate_email_no_at():\n    assert validate_email('userexample.com') is False\n\ndef test_validate_email_no_domain():\n    assert validate_email('user@') is False\n\ndef test_validate_email_spaces():\n    assert validate_email('user @example.com') is False\n\ndef test_validate_email_empty():\n    assert validate_email('') is False\n\ndef test_validate_email_none():\n    with pytest.raises(TypeError):\n        validate_email(None)\n```",
        r'''<think>
Use `pytest.mark.parametrize` to combine these into a compact, readable table. Group valid and invalid cases separately.
</think>

Use `@pytest.mark.parametrize` — one test function, many cases:

```python
@pytest.mark.parametrize("email", [
    "user@example.com",
    "user@sub.example.com",
    "user+tag@example.com",
    "firstname.lastname@example.com",
    "user@123.123.123.com",
])
def test_valid_emails(email):
    assert validate_email(email) is True

@pytest.mark.parametrize("email,reason", [
    ("userexample.com",     "missing @"),
    ("user@",               "missing domain"),
    ("user @example.com",   "contains space"),
    ("",                    "empty string"),
    ("@example.com",        "missing local part"),
    ("user@.com",           "domain starts with dot"),
    ("user@exam ple.com",   "space in domain"),
])
def test_invalid_emails(email, reason):
    assert validate_email(email) is False, f"Should reject: {reason}"

def test_validate_email_none_raises():
    with pytest.raises(TypeError):
        validate_email(None)
```

pytest output:
```
test_email.py::test_valid_emails[user@example.com] PASSED
test_email.py::test_valid_emails[user@sub.example.com] PASSED
test_email.py::test_invalid_emails[userexample.com-missing @] PASSED
test_email.py::test_invalid_emails[user@-missing domain] PASSED
```

Each case shows up as a separate test result — you can see exactly which input failed.

## Advanced: Parametrize Multiple Axes

```python
@pytest.mark.parametrize("amount", [0, 1, 100, 999, 1000])
@pytest.mark.parametrize("currency", ["usd", "eur", "gbp"])
def test_format_price(amount, currency):
    result = format_price(amount, currency)
    assert isinstance(result, str)
    assert len(result) > 0
# Generates 5 × 3 = 15 test cases
```

**Rule**: If you have 3+ tests with the same structure and different data, parametrize them.'''
    ),
    (
        "thinking/testing-contract-testing",
        "We have 5 microservices that communicate via REST APIs. Every sprint, service A deploys a change that breaks service B because the API response format changed. How do we prevent this?",
        r'''<think>
This is the classic microservice integration testing problem. The options are:
1. End-to-end tests (slow, brittle, hard to maintain)
2. Contract testing (fast, catches interface changes)
3. API versioning + schema validation

Contract testing with Pact is the industry standard for this. The consumer defines what it expects, the provider verifies it can deliver.
</think>

**Contract testing** — each consumer defines what it expects from the provider, and the provider verifies it can deliver:

## The Problem

```
Service A (consumer) expects:
  GET /api/users/1 → {"id": 1, "name": "Alice", "email": "..."}

Service B (provider) deploys change:
  GET /api/users/1 → {"id": 1, "full_name": "Alice", "email_address": "..."}
  # Renamed fields → Service A breaks in production
```

## The Solution: Pact Consumer-Driven Contracts

### Step 1: Consumer Writes What It Expects

```python
# Service A's test (consumer side)
import pact

@pact.consumer("ServiceA")
@pact.provider("ServiceB")
def test_get_user(pact_mock):
    # Define expected interaction
    pact_mock.given("user 1 exists")
    pact_mock.upon_receiving("a request for user 1")
    pact_mock.with_request("GET", "/api/users/1")
    pact_mock.will_respond_with(200, body={
        "id": pact.Like(1),           # Any integer
        "name": pact.Like("Alice"),    # Any string
        "email": pact.Like("a@b.com"), # Any string matching pattern
    })

    # Test consumer code against mock
    with pact_mock:
        user = user_client.get_user(1)
        assert user.name is not None

    # Pact file generated: serviceA-serviceB.json
```

### Step 2: Provider Verifies the Contract

```python
# Service B's test (provider side)
def test_pact_verification():
    verifier = Verifier(
        provider="ServiceB",
        provider_base_url="http://localhost:8000",
    )
    # Verify against all consumer contracts
    verifier.verify_pacts(
        "pacts/serviceA-serviceB.json",
        provider_states_setup_url="http://localhost:8000/_pact/setup",
    )
```

### Step 3: CI/CD Integration

```yaml
# Service B's CI pipeline
provider-contract-tests:
  steps:
    - name: Run provider
      run: python manage.py runserver &
    - name: Fetch consumer contracts
      run: pact-broker fetch --provider ServiceB
    - name: Verify contracts
      run: pytest tests/contracts/
    # If this fails → Service B's change would break consumers
    # Block the deployment
```

## How It Catches the Bug

```
1. Service A's contract says: expect field "name"
2. Service B renames "name" → "full_name"
3. Service B's CI runs contract verification
4. Verification FAILS: "Consumer ServiceA expects field 'name' but it's missing"
5. Deployment blocked → bug caught before production
```

## Contract Testing vs E2E Testing

| Contract Testing | E2E Testing |
|-----------------|-------------|
| Tests interface, not behavior | Tests full workflow |
| Runs in milliseconds | Takes minutes |
| Each service tested independently | All services must be running |
| Catches API format changes | Catches workflow bugs |
| Easy to maintain | Brittle, expensive |

Use both: contracts for API compatibility, E2E for a few critical user journeys.'''
    ),
    (
        "thinking/testing-test-isolation-patterns",
        "Our tests are slow because each one sets up a full database with test data. Setup takes 2 seconds per test, and we have 500 tests. That's 16 minutes just for setup. How do we speed this up?",
        r'''<think>
Options for speeding up database test setup:
1. Transaction rollback — wrap each test in a transaction, rollback after
2. Database fixtures loaded once — shared setup for all tests
3. In-memory database (SQLite) — fast but may have dialect differences
4. Test-specific factories that create minimal data
5. Parallelize tests across multiple databases

Transaction rollback is the biggest win — setup your shared data once, each test runs in a transaction that's rolled back.
</think>

**Transaction rollback** is the biggest win — set up data once, each test runs in a transaction that's rolled back:

## Before: 16 Minutes

```python
# Each test creates a full database from scratch
def test_order_total(db):
    # 2 seconds of setup PER TEST
    user = User.objects.create(name='Alice', ...)
    product = Product.objects.create(name='Widget', price=10, ...)
    category = Category.objects.create(...)
    # ... 20 more objects

    order = create_order(user, product, 1)
    assert order.total == 10

# 500 tests × 2 seconds = 1000 seconds (16+ minutes)
```

## After: 30 Seconds

### Strategy 1: Transaction Rollback (Best ROI)

```python
# conftest.py
@pytest.fixture(autouse=True)
def db_transaction(db_session):
    """Every test runs in a transaction that's rolled back."""
    db_session.begin_nested()  # Savepoint
    yield
    db_session.rollback()      # Instant cleanup, no DELETE queries

# Base data loaded once for the entire test suite
@pytest.fixture(scope="session")
def db_base_data(db_engine):
    """Create shared reference data once."""
    with db_engine.begin() as conn:
        conn.execute(text("INSERT INTO categories ..."))
        conn.execute(text("INSERT INTO tax_rates ..."))
        conn.execute(text("INSERT INTO shipping_zones ..."))
    yield
    # Cleanup at end of session
```

Each test starts with a clean savepoint, modifies data freely, and rollback takes <1ms.

### Strategy 2: Factory Functions (Create Only What You Need)

```python
# Instead of creating 20 objects, create only what the test needs
def test_order_total():
    order = make_order(items=[
        make_item(price=Decimal('10'), quantity=2),
    ])
    assert order.total == Decimal('20')

# Factory creates minimal required objects, nothing more
```

### Strategy 3: Parallelize

```bash
# Run tests across 4 workers, each with its own database
pytest -n 4 --dist=loadgroup

# conftest.py
@pytest.fixture(scope="session")
def db_url(worker_id):
    return f"postgresql://localhost/test_db_{worker_id}"
```

### Combined Approach (Maximum Speed)

```
Transaction rollback: 2000ms → 1ms per test  (2000x faster)
Minimal factories:   2000ms → 50ms per test  (40x faster)
4 workers parallel:  divide total by 4

500 tests × 50ms / 4 workers = 6 seconds
```

## Speed Comparison

| Approach | Per Test | 500 Tests |
|----------|----------|-----------|
| Full setup/teardown | 2000ms | 16 min |
| Transaction rollback | 50ms | 25 sec |
| Rollback + parallel (4x) | 50ms | 6 sec |
| In-memory SQLite | 10ms | 5 sec |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
