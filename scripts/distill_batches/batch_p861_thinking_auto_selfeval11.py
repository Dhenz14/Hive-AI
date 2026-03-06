"""Phase 4B: Self-Improvement -- Self-Evaluation (Part 11)

Evaluating own testing recommendations for correctness and practicality.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-testing-100-percent-coverage",
        r'''A developer asks how to improve their test suite. I am about to recommend aiming for 100% code coverage. Let me evaluate whether that is good advice:

My draft: "Aim for 100% code coverage. Every line of code should be tested. Use coverage tools to find untested lines and write tests for them until you reach 100%."''',
        r'''<think>
Let me evaluate my testing recommendation:

**My recommendation:** Aim for 100% code coverage.

**Is this good advice? NO. 100% coverage is a misleading target.**

**Problem 1: Coverage measures lines executed, not correctness**
```python
def divide(a, b):
    return a / b

def test_divide():
    assert divide(10, 2) == 5  # 100% coverage!
    # But what about divide(10, 0)? ZeroDivisionError!
    # What about divide(10, 3)? Is 3.333... acceptable or should it be integer division?
    # 100% coverage, 0% confidence in edge cases.
```

**Problem 2: Diminishing returns**
- Going from 0% to 60% coverage is high-value (covers core logic)
- Going from 60% to 80% is good (covers important paths)
- Going from 80% to 95% is expensive (covers edge cases)
- Going from 95% to 100% is very expensive (covers trivial code)

That last 5% often means testing boilerplate, config files, exception messages -- low value.

**Problem 3: Incentivizes bad tests**
When coverage is the goal, developers write tests TO HIT LINES, not to verify behavior:
```python
# Written to increase coverage, not to test anything meaningful:
def test_user_model():
    user = User(name="test")
    assert user.name  # Just accesses the attribute, tests nothing
    str(user)  # Runs __str__ for coverage, does not check the output
```

**What I should have recommended:**
- Focus on testing BEHAVIOR, not lines of code
- Target 70-85% coverage as a reasonable guideline
- Measure what matters: critical paths, edge cases, error handling
- Use coverage to find UNTESTED AREAS, not as a score to maximize

**Verdict:** 100% coverage is a vanity metric that wastes time and produces bad tests. Rating: 3/10.
</think>

**Self-evaluation: 100% coverage is a vanity metric that incentivizes bad tests. Rating: 3/10.**

**What I should recommend instead:**

"Don't aim for 100% coverage. Aim for HIGH-VALUE testing:

**The right coverage strategy:**

```
Priority 1 (MUST test): Business logic, calculations, data validation
  - Payment calculations, discount rules, tax computation
  - User input validation, authorization checks
  - Data transformations, serialization/deserialization

Priority 2 (SHOULD test): Integration points, error handling
  - Database queries return expected results
  - API endpoints handle valid and invalid inputs
  - Error paths behave correctly (timeouts, invalid data)

Priority 3 (NICE TO HAVE): UI rendering, configuration
  - Only if time permits or if bugs have occurred here

Priority 4 (SKIP): Boilerplate, getters/setters, framework code
  - __str__ methods, simple property accessors
  - Framework-generated code (migrations, admin configs)
```

**Coverage as a diagnostic tool (not a score):**
```bash
# Run coverage to find UNTESTED CRITICAL CODE:
pytest --cov=myapp --cov-report=html

# Look at the report and ask:
# 'Is this untested code important?'
#   YES -> Write a meaningful test for it
#   NO  -> Leave it untested, that is fine
```

**Target: 70-85% coverage, with 100% coverage of critical business logic.**"

**Self-evaluation lesson:** Coverage is a diagnostic tool, not a goal. The question is not 'how much code is tested?' but 'are the important things tested well?'"""''',
    ),
    (
        "thinking/auto-selfeval-testing-unit-vs-integration",
        r'''A developer is building a web application and asks what kinds of tests to write. I am about to recommend writing mostly unit tests. Let me evaluate this advice:

My draft: "Follow the testing pyramid: write many unit tests, fewer integration tests, and very few end-to-end tests. Unit tests should make up 70% of your test suite because they are fast and isolated."''',
        r'''<think>
Let me evaluate my testing recommendation:

**My recommendation:** Follow the testing pyramid -- mostly unit tests.

**Is this good advice? PARTIALLY. The traditional pyramid is not always right.**

**When the traditional pyramid works well:**
- Library code with complex algorithms
- Pure functions with clear inputs/outputs
- Code with minimal dependencies
- Math, parsing, data transformation

**When the traditional pyramid FAILS:**
- CRUD web applications (most of the code is integration)
- The unit tests mock everything and test nothing real
- You end up with hundreds of unit tests that pass but the app is broken

**The problem with too many unit tests in web apps:**
```python
# Unit test with mocks:
def test_create_order():
    mock_db = Mock()
    mock_payment = Mock()
    mock_payment.charge.return_value = {"success": True}
    mock_db.insert.return_value = 42

    service = OrderService(db=mock_db, payment=mock_payment)
    result = service.create_order(user_id=1, items=[...])

    assert result.id == 42
    mock_payment.charge.assert_called_once()
    mock_db.insert.assert_called_once()

# This test passes! But...
# - What if the SQL query has a syntax error?
# - What if the payment API expects different parameters?
# - What if the mock returns a shape the real API never returns?
# All mocked, all invisible, all broken in production.
```

**The better model for web apps: Testing trophy or diamond**
```
    /\          End-to-end (few, critical user journeys)
   /  \
  /    \
 / Integ \     Integration tests (most value for web apps!)
/  ration  \
|----------|
|  Unit    |   Unit tests (for complex logic only)
|__________|
```

**Verdict:** The traditional testing pyramid is a useful default but not universal. For CRUD web applications, integration tests provide far more value than unit tests with mocks. Rating: 5/10.
</think>

**Self-evaluation: The testing pyramid is a reasonable default but wrong for many web applications. Rating: 5/10.**

**What I should recommend instead:**

"The right test distribution depends on your application type:

**For CRUD web applications (most common):**
```
Focus on integration tests:

# Integration test -- tests REAL database, REAL route, REAL serialization:
def test_create_user(client, db):
    response = client.post('/api/users', json={
        'name': 'Alice',
        'email': 'alice@example.com'
    })

    assert response.status_code == 201
    assert response.json['name'] == 'Alice'

    # Verify it actually persists:
    user = db.query('SELECT * FROM users WHERE email = %s', ('alice@example.com',))
    assert user is not None
```

**For complex business logic (calculations, rules engines):**
```
Focus on unit tests:

def test_shipping_cost_international_heavy():
    cost = calculate_shipping(weight_kg=15, country='DE', expedited=True)
    assert cost == 89.50  # Tests the actual calculation
```

**Distribution guide:**
| Application type | Unit | Integration | E2E |
|-----------------|------|------------|-----|
| CRUD web app | 20% | 60% | 20% |
| Algorithm library | 80% | 15% | 5% |
| Microservice API | 30% | 50% | 20% |
| Data pipeline | 40% | 50% | 10% |

**The golden rule:** Write the type of test that gives you the most confidence that real users will not encounter bugs."

**Self-evaluation lesson:** Don't blindly follow testing dogma. Match your testing strategy to your application type. A CRUD app with 500 unit tests and 0 integration tests is poorly tested.'''
    ),
    (
        "thinking/auto-selfeval-testing-mocking-strategy",
        r'''A developer asks how to test code that depends on external services (database, APIs, file system). I am about to recommend mocking everything. Let me evaluate this approach:

My draft: "Mock all external dependencies. Use unittest.mock to replace the database, API calls, and file system operations. This makes your tests fast and isolated."''',
        r'''<think>
Let me evaluate my mocking recommendation:

**My recommendation:** Mock ALL external dependencies.

**Is this good advice? TOO EXTREME.**

**Problem 1: Over-mocking tests implementation, not behavior**
```python
# Over-mocked test:
def test_get_user():
    mock_db = Mock()
    mock_db.query.return_value = [{"id": 1, "name": "Alice"}]
    user = get_user(mock_db, user_id=1)
    mock_db.query.assert_called_with("SELECT * FROM users WHERE id = %s", (1,))
    assert user.name == "Alice"

# Problem: This test is coupled to the SQL query string!
# If you refactor the query (add a column, change syntax), the test breaks.
# But the behavior (get user by ID) has not changed.
# You are testing HOW the code works, not WHAT it does.
```

**Problem 2: Mocks can lie**
```python
# Mock says the API returns {"status": "ok"}
# But the REAL API returns {"result": "success"}
# Test passes, production breaks.
```

**Problem 3: Not everything needs to be mocked**
- Database: use a test database (SQLite in-memory, or testcontainers)
- File system: use tempfile and temporary directories
- Time: OK to mock (deterministic testing)
- External APIs: mock these (you don't control them)

**The better approach: a mocking spectrum**
- Real dependencies when practical (test database, temp files)
- Fakes for complex dependencies (in-memory implementations)
- Mocks only for things you cannot control (external APIs, email, payment)

**Verdict:** "Mock everything" leads to tests that verify mock behavior, not real behavior. Only mock what you cannot practically use in tests. Rating: 3/10.
</think>

**Self-evaluation: "Mock everything" creates tests that test mocks, not code. Rating: 3/10.**

**What I should recommend instead:**

"Use the right test double for each dependency:

**Dependency decision matrix:**
| Dependency | Strategy | Why |
|-----------|----------|-----|
| Database | Real test database | Tests actual queries and schema |
| File system | tempfile / tmp directories | Easy to use real files in tests |
| External HTTP APIs | Mock or record/replay | You don't control them |
| Email sending | Mock (or use Mailhog) | Don't send real emails in tests |
| Payment processing | Mock (Stripe has test mode) | Don't charge real money |
| Current time | Mock | Need deterministic tests |
| Random numbers | Seed the generator | Need reproducible tests |
| Environment variables | Set in test setup | Use real env mechanism |

**Example: Database (use real, not mock)**
```python
import pytest

@pytest.fixture
def db():
    # Use a real test database
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()

def test_create_and_find_user(db):
    # Tests REAL SQL, REAL ORM, REAL schema
    user = User(name='Alice', email='alice@example.com')
    db.add(user)
    db.commit()

    found = db.query(User).filter_by(email='alice@example.com').first()
    assert found.name == 'Alice'
```

**Example: External API (mock this)**
```python
import responses

@responses.activate
def test_fetch_weather():
    # Mock the external API (we don't control weather.com)
    responses.add(
        responses.GET,
        'https://api.weather.com/current',
        json={'temp': 72, 'condition': 'sunny'},
        status=200
    )

    weather = fetch_current_weather('New York')
    assert weather.temperature == 72
```

**The principle:** Mock at the boundary of your system, not inside it. If you own it and can run it in tests, use the real thing."

**Self-evaluation lesson:** The goal of testing is confidence that the code works correctly. Over-mocking gives you confidence that your mocks work correctly, which is not the same thing.'''
    ),
    (
        "thinking/auto-selfeval-testing-flaky-tests",
        r'''Our test suite has several flaky tests that pass sometimes and fail other times. I am about to recommend deleting them. Let me evaluate this approach:

My draft: "Flaky tests are worse than no tests. Delete them. A test that sometimes fails erodes trust in the entire test suite."''',
        r'''<think>
Let me evaluate my recommendation:

**My recommendation:** Delete flaky tests.

**Is this good advice? PARTIALLY -- the instinct is correct but the response is wrong.**

**Why the instinct is correct:**
- Flaky tests DO erode trust in the test suite
- Developers start ignoring test failures ("oh, that test is flaky")
- Real failures get ignored because "it is probably just the flaky test"
- CI becomes unreliable (merge despite failures)

**Why deleting is wrong:**
- The test was written because something needed testing
- The behavior being tested is probably important
- Flaky tests are a SYMPTOM of a problem, not the problem itself
- Deleting the test removes coverage of important functionality

**The real question: WHY is the test flaky?**
Common causes:
1. Test depends on timing (sleep, timeouts) -> Fix the timing
2. Test depends on external state (database, file system) -> Isolate the state
3. Test depends on test execution order -> Make tests independent
4. Test has a race condition -> Fix the race condition
5. Test depends on random data -> Seed the randomness
6. The CODE being tested has a real intermittent bug -> This is actually valuable information!

**Verdict:** Deleting flaky tests removes coverage. The right approach is to diagnose and fix the flakiness. Rating: 3/10.
</think>

**Self-evaluation: Deleting flaky tests is like unplugging a fire alarm because it keeps going off. Fix the cause, not the symptom. Rating: 3/10.**

**What I should recommend instead:**

"Don't delete flaky tests -- fix them. Here is the process:

**Step 1: Quarantine (immediate)**
```python
# Mark flaky tests so they don't block CI but still run:
@pytest.mark.flaky(reruns=3)  # Auto-retry up to 3 times
def test_sometimes_fails():
    ...

# Or skip with a clear reason:
@pytest.mark.skip(reason='FLAKY: depends on timing, see issue #234')
def test_sometimes_fails():
    ...
```

**Step 2: Diagnose the cause**
| Flaky pattern | Likely cause | Diagnostic |
|--------------|-------------|------------|
| Fails on CI, passes locally | Environment difference | Compare CI and local environments |
| Fails when run with other tests | Shared state or ordering | Run the test in isolation |
| Fails intermittently everywhere | Race condition or timing | Add logging, run 100 times |
| Fails at certain times of day | Time-dependent logic | Check for hardcoded dates/times |
| Fails after other test changes | Implicit dependency | Check for shared state |

**Step 3: Fix by cause**
```python
# Cause: Timing dependency
# BAD:
def test_cache_expiry():
    cache.set('key', 'value', ttl=1)
    time.sleep(1.1)  # Flaky! Sleep duration is unreliable
    assert cache.get('key') is None

# GOOD:
def test_cache_expiry(mock_time):
    cache.set('key', 'value', ttl=1)
    mock_time.advance(2)  # Deterministic time advancement
    assert cache.get('key') is None

# Cause: Shared database state
# BAD:
def test_create_user():
    create_user('alice@test.com')  # Fails if user already exists from another test!

# GOOD:
def test_create_user(clean_db):  # Fixture resets DB before each test
    create_user('alice@test.com')
    assert User.query.count() == 1

# Cause: Random test data
# BAD:
def test_sort_users():
    users = [User(name=fake.name()) for _ in range(10)]  # Random names!
    sorted_users = sort_by_name(users)
    assert sorted_users[0].name < sorted_users[1].name

# GOOD:
def test_sort_users():
    users = [User(name='Charlie'), User(name='Alice'), User(name='Bob')]
    sorted_users = sort_by_name(users)
    assert [u.name for u in sorted_users] == ['Alice', 'Bob', 'Charlie']
```

**Step 4: Prevent future flakiness**
- Run tests in random order regularly (`pytest-randomly`)
- Run each new test 10 times before merging (`pytest --count=10`)
- Set up a flaky test dashboard to track patterns
- Review tests during code review for common flaky patterns"

**Self-evaluation lesson:** Flaky tests are often telling you something important -- either about your test design or about your code. Listen to what they are saying before silencing them.'''
    ),
    (
        "thinking/auto-selfeval-testing-test-organization",
        r'''A developer has a growing test suite with 500 tests in one file. Tests take 10 minutes to run. I am about to recommend splitting tests into smaller files. Let me evaluate whether that addresses the actual problems:

My draft: "Split your tests into smaller files organized by module. This will make them easier to navigate. Also consider running tests in parallel to reduce the 10-minute runtime."''',
        r'''<think>
Let me evaluate my testing recommendation:

**My recommendation:** Split test files + run in parallel.

**Is this advice correct? It addresses organization but misses deeper issues.**

**What I got right:**
- 500 tests in one file IS a maintenance problem
- Splitting by module IS the right organizational approach
- Parallel execution CAN help with runtime

**What I missed:**

**Problem 1: WHY do 500 tests take 10 minutes?**
- 500 tests at 10 minutes = 1.2 seconds average per test
- Fast unit tests should be <10ms each (500 tests = 5 seconds total)
- If tests take 1.2s each, they are likely:
  - Hitting a real database without connection pooling
  - Making HTTP calls to external services
  - Sleeping in tests (timing-dependent tests)
  - Setting up expensive fixtures for every test
- Splitting files does not fix slow tests -- they will still be slow

**Problem 2: Test organization is not just about file splitting**
- How are fixtures managed? (global state vs per-test isolation)
- Are there test helper functions or is there code duplication?
- Is there a clear test naming convention?
- Can developers run a subset of tests easily?

**Problem 3: Parallel execution has prerequisites**
- Tests must be independent (no shared state)
- Database tests need separate test databases per worker
- File-based tests need separate directories
- If tests are not independent, parallel execution causes flakiness

**Verdict:** My advice is surface-level. I should dig deeper into WHY the tests are slow before recommending organizational changes. Rating: 5/10.
</think>

**Self-evaluation: Splitting files and parallelizing are good ideas but they address symptoms, not root causes. Rating: 5/10.**

**What I should recommend instead:**

"Let's fix both the speed AND the organization:

**Step 1: Find out WHY tests are slow**
```bash
# Find the slowest tests:
pytest --durations=20

# Output:
# 45.2s test_order_processing.py::test_full_checkout_flow
# 12.3s test_order_processing.py::test_payment_retry
# 8.7s  test_user_auth.py::test_password_reset_email
# ...
```

**Step 2: Fix the slow tests**
```
Common speed problems and fixes:

| Slow test pattern | Root cause | Fix |
|------------------|-----------|-----|
| Each test takes 1s+ | Real DB without pooling | Use connection pool or in-memory DB |
| Few tests take 30s+ | HTTP calls to external APIs | Mock external calls |
| Tests with time.sleep() | Timing-dependent | Mock time instead of sleeping |
| Heavy fixture setup | Recreating DB schema per test | Use transactions, rollback after each test |
```

```python
# SLOW: Creates and destroys entire DB per test
@pytest.fixture
def db():
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)   # 200ms to create tables
    session = Session(engine)
    yield session
    Base.metadata.drop_all(engine)     # 200ms to drop tables

# FAST: Create tables once, use transaction rollback per test
@pytest.fixture(scope='session')
def db_engine():
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db(db_engine):
    conn = db_engine.connect()
    transaction = conn.begin()
    session = Session(bind=conn)
    yield session
    transaction.rollback()  # Undo all changes, instant cleanup
    conn.close()
```

**Step 3: Organize test files**
```
tests/
    conftest.py           # Shared fixtures
    unit/                 # Fast tests (<100ms)
        test_models.py
        test_validators.py
        test_calculations.py
    integration/          # Medium tests (100ms-2s)
        test_api_users.py
        test_api_orders.py
        test_database.py
    e2e/                  # Slow tests (2s+)
        test_checkout_flow.py
        test_user_registration.py
```

**Step 4: Run subsets efficiently**
```bash
# Run only fast tests during development:
pytest tests/unit/ -x          # Stop at first failure

# Run integration tests before committing:
pytest tests/unit/ tests/integration/

# Run everything in CI:
pytest --parallel-mode=auto    # Parallel execution

# Run tests for one module:
pytest -k 'test_order'         # Pattern matching
```

After fixing slow tests AND organizing properly, your 10-minute suite should run in under 1 minute."

**Self-evaluation lesson:** When tests are slow, the problem is usually the tests themselves (slow fixtures, real HTTP calls, sleep statements), not the file organization. Fix the speed first, then organize.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
