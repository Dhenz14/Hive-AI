"""Phase 1F: Foundation Thinking — Testing Strategy (Part 3/4)
Test architecture, coverage strategy, refactoring for testability, testing anti-patterns."""

PAIRS = [
    (
        "thinking/testing-testing-pure-functions",
        "My colleague says we should make more code 'pure functions' for testability. What does that mean practically and how do I refactor impure code?",
        r'''<think>
Pure functions:
- Same input → always same output
- No side effects (no DB, no I/O, no mutation of external state)
- No dependency on external state (no reading globals, env vars, clock)

The practical benefit: pure functions are trivially testable — no mocking, no setup, no teardown.

Strategy: separate the pure logic from the impure I/O. "Functional core, imperative shell" pattern.
</think>

A **pure function** always returns the same output for the same input and has no side effects. They're trivially testable — no mocking needed.

## Impure → Pure Refactoring

```python
# IMPURE: Hard to test (needs DB, clock, file system)
def generate_monthly_report():
    orders = db.query("SELECT * FROM orders WHERE month = %s", datetime.now().month)
    total = sum(o.amount for o in orders)
    tax = total * get_tax_rate(os.environ['REGION'])
    report = f"Total: ${total}, Tax: ${tax}, Net: ${total - tax}"
    with open(f'/reports/report_{datetime.now().strftime("%Y%m")}.txt', 'w') as f:
        f.write(report)
    return report

# To test this, you need: database, environment variables,
# frozen clock, writable filesystem. Nightmare.
```

```python
# PURE CORE: Easy to test
def calculate_report(orders: list, tax_rate: Decimal, month_label: str) -> str:
    total = sum(o.amount for o in orders)
    tax = total * tax_rate
    return f"Total: ${total}, Tax: ${tax}, Net: ${total - tax}"

# IMPURE SHELL: Thin, just wires things together
def generate_monthly_report():
    now = datetime.now()
    orders = db.query("SELECT * FROM orders WHERE month = %s", now.month)
    tax_rate = get_tax_rate(os.environ['REGION'])
    month_label = now.strftime("%Y%m")

    report = calculate_report(orders, tax_rate, month_label)  # Pure!

    with open(f'/reports/report_{month_label}.txt', 'w') as f:
        f.write(report)
    return report

# Test the pure function — no mocking, no setup
def test_report_calculation():
    orders = [Order(amount=Decimal('100')), Order(amount=Decimal('200'))]
    report = calculate_report(orders, Decimal('0.1'), '202401')
    assert 'Total: $300' in report
    assert 'Tax: $30' in report
    assert 'Net: $270' in report

def test_report_empty_orders():
    report = calculate_report([], Decimal('0.1'), '202401')
    assert 'Total: $0' in report
```

## The Pattern: Functional Core, Imperative Shell

```
┌─────────────────────────────┐
│     Imperative Shell        │  ← Thin: reads DB, env, clock
│  (I/O, side effects, wiring)│     Writes files, sends emails
│                             │     Minimal logic
│  ┌───────────────────────┐  │
│  │    Functional Core     │  │  ← Thick: all business logic
│  │  (pure, no side effects│  │     Easy to test
│  │   deterministic)       │  │     No mocking needed
│  └───────────────────────┘  │
└─────────────────────────────┘
```

**Push I/O to the edges, keep logic in the center.**'''
    ),
    (
        "thinking/testing-coverage-strategy",
        "Our manager wants 100% code coverage. Is that a good goal? What coverage percentage should we actually target?",
        r'''<think>
100% coverage is almost always a bad goal because:
1. It incentivizes writing worthless tests just to hit numbers
2. Some code is genuinely not worth testing (boilerplate, generated code)
3. Coverage measures lines executed, not behavior verified
4. Diminishing returns after ~80%

The right approach: coverage as a minimum floor, not a target. Focus on high-value areas.
</think>

100% coverage is a **counterproductive goal**. Here's why and what to do instead.

## Why 100% Is Harmful

```python
# Tests written just to hit coverage numbers:
def test_str_representation():
    user = User(name='Alice')
    assert str(user)  # Covers __str__ but tests nothing useful

def test_init():
    config = Config()
    assert config is not None  # Covers __init__ but verifies nothing
```

These tests add maintenance cost with zero bug-catching value.

## The Right Coverage Strategy

### Set a Floor, Not a Target

```yaml
# pytest-cov configuration
[tool.pytest.ini_options]
addopts = "--cov=src --cov-fail-under=80"
```

**80% overall minimum**, but enforce higher coverage on critical code:

```python
# Coverage by module priority:
# 95%+ : Payment processing, authentication, authorization
# 85%+ : Business logic, data transformations
# 80%+ : API endpoints, serialization
# 60%+ : Admin views, management commands
# Skip : Generated code, migrations, __repr__
```

### What to Exclude from Coverage

```ini
# .coveragerc
[run]
omit =
    */migrations/*
    */tests/*
    */admin.py
    */__repr__*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    if TYPE_CHECKING:
    raise NotImplementedError
    pass
```

### Measure What Matters: Mutation Score

```bash
# Coverage says 95% — but are the tests actually checking anything?
mutmut run  # Mutation testing

# Mutation score 60% — meaning 40% of bugs in tested code
# would NOT be caught. That's the real quality metric.
```

## Coverage Rules

1. **80% floor** — below this, you're flying blind
2. **Never target 100%** — diminishing returns past 90%
3. **Coverage can go down** — if you delete bad tests, coverage drops but quality improves
4. **Branch coverage > line coverage** — `--cov-branch` catches untested if/else paths
5. **New code must be covered** — use `diff-cover` to enforce coverage on changed lines

```bash
# Enforce coverage on PR diff only
diff-cover coverage.xml --compare-branch=main --fail-under=90
```'''
    ),
    (
        "thinking/testing-dependency-injection-testing",
        "I keep hearing that dependency injection makes code testable, but my team thinks it's over-engineering. Show me the simplest form of DI that actually helps testing.",
        r'''<think>
DI doesn't need frameworks or containers. The simplest form is just passing dependencies as function arguments or constructor parameters instead of creating them inside the function.

Let me show the progression from untestable to testable with minimal DI.
</think>

DI is just **passing things in instead of creating them inside**. No frameworks needed:

## Level 0: Untestable (Hardcoded Dependencies)

```python
def send_order_confirmation(order_id):
    order = Order.objects.get(id=order_id)      # Creates its own dependency
    template = open('templates/order.html').read()  # Creates its own dependency
    html = render(template, order=order)
    smtp = smtplib.SMTP('smtp.gmail.com', 587)  # Creates its own dependency
    smtp.send(order.user.email, html)
```

To test this: need a real database, a real file, and a real SMTP server.

## Level 1: Simple DI (Just Pass It In)

```python
def send_order_confirmation(order, template, mailer):
    html = render(template, order=order)
    mailer.send(order.user.email, html)

# Production:
send_order_confirmation(
    order=Order.objects.get(id=order_id),
    template=open('templates/order.html').read(),
    mailer=SmtpMailer('smtp.gmail.com', 587),
)

# Test:
def test_send_order_confirmation():
    order = make_order(user=make_user(email='test@example.com'))
    template = '<h1>Order {{order.id}}</h1>'
    mailer = FakeMailer()

    send_order_confirmation(order, template, mailer)

    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == 'test@example.com'
```

## Level 2: Constructor DI (For Classes)

```python
class OrderService:
    def __init__(self, order_repo, mailer, template_loader):
        self._orders = order_repo
        self._mailer = mailer
        self._templates = template_loader

    def confirm(self, order_id):
        order = self._orders.get(order_id)
        template = self._templates.load('order_confirmation')
        html = render(template, order=order)
        self._mailer.send(order.user.email, html)

# Test with fakes:
def test_confirm_sends_email():
    orders = FakeOrderRepo([make_order(id=1)])
    mailer = FakeMailer()
    templates = FakeTemplateLoader({'order_confirmation': '<h1>{{order.id}}</h1>'})

    service = OrderService(orders, mailer, templates)
    service.confirm(1)

    assert mailer.sent[0].to == orders.get(1).user.email
```

## Level 3: Default Arguments (Best of Both Worlds)

```python
class OrderService:
    def __init__(self, order_repo=None, mailer=None):
        self._orders = order_repo or DjangoOrderRepo()
        self._mailer = mailer or SmtpMailer()

# Production: just use defaults
service = OrderService()

# Test: inject fakes
service = OrderService(order_repo=FakeOrderRepo(), mailer=FakeMailer())
```

That's it. No Spring, no containers, no `@Inject` decorators. Just pass dependencies as arguments.'''
    ),
    (
        "thinking/testing-test-antipatterns",
        "What are the most common testing anti-patterns that make test suites more harmful than helpful?",
        r'''<think>
Common testing anti-patterns that waste time and create false confidence:

1. Ice cream cone (too many E2E, too few unit tests)
2. Testing implementation instead of behavior
3. Shared mutable state between tests
4. Assertion-free tests
5. Overly specific assertions
6. Test interdependence
7. Slow tests that nobody runs
8. Testing private methods

Let me describe each with concrete examples.
</think>

## The 8 Deadliest Testing Anti-Patterns

### 1. The Ice Cream Cone (Inverted Pyramid)

```
    ╱▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔╲
   ╱   500 E2E Tests    ╲     ← Slow, flaky
  ╱   200 Integration     ╲
 ╱      50 Unit Tests      ╲   ← Should be the biggest layer
╱▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁╲
```

**Fix**: Invert it. 500 unit, 200 integration, 10 E2E.

### 2. Testing Implementation, Not Behavior

```python
# BAD: Tests HOW, not WHAT
def test_get_users():
    service.get_users()
    mock_repo.find_all.assert_called_once()     # Who cares how it gets them?
    mock_cache.get.assert_called_with('users')  # Brittle if caching changes

# GOOD: Tests WHAT
def test_get_users_returns_all_active_users():
    create_user(active=True, name='Alice')
    create_user(active=False, name='Bob')
    result = service.get_users()
    assert len(result) == 1
    assert result[0].name == 'Alice'
```

### 3. The Liar (Assertion-Free Tests)

```python
# BAD: Test runs code but verifies nothing
def test_process_order():
    order = make_order()
    process(order)  # No assertion! Always "passes"

# GOOD: Verify the outcome
def test_process_order():
    order = make_order()
    process(order)
    assert order.status == 'processed'
```

### 4. The Slow Suite Nobody Runs

```bash
# If the test suite takes 20 minutes, developers skip it
$ pytest  # ... 20 minutes later ...
# "I'll just push and let CI catch it"
```

**Fix**: Tests must run in < 2 minutes locally. Parallelize, use transaction rollback, mock I/O.

### 5. Test Interdependence

```python
# BAD: test_B depends on test_A's side effects
def test_A_create_user():
    db.create(User(name='Alice'))

def test_B_find_user():
    user = db.find('Alice')  # Fails if test_A didn't run first
    assert user.name == 'Alice'
```

**Fix**: Each test sets up and tears down its own state.

### 6. Testing Private Methods

```python
# BAD: Testing internal implementation
def test_parse_internal_format():
    result = service._parse_raw_data(raw_bytes)  # Private method!
    assert result == expected

# Refactoring _parse_raw_data breaks this test even if behavior is unchanged
```

**Fix**: Test through the public interface. If private logic is complex enough to test directly, extract it to its own class.

### 7. Excessive Mocking

```python
# BAD: Everything is mocked — what are you even testing?
def test_create_order(mock_db, mock_cache, mock_email,
                      mock_inventory, mock_payment, mock_analytics):
    mock_db.get.return_value = mock_user
    mock_inventory.check.return_value = True
    mock_payment.charge.return_value = mock_result

    service.create_order(data)

    # You're testing that your code calls mocks in the right order
    # If the real DB/payment/inventory behaves differently, this test is useless
```

**Fix**: Use fakes (in-memory implementations) instead of mocks for complex interactions.

### 8. Copy-Paste Tests

```python
# BAD: 50 tests that are 95% identical
def test_admin_can_view_users(): ...    # 20 lines, differs by 1 line
def test_admin_can_view_orders(): ...   # 20 lines, differs by 1 line
def test_admin_can_view_products(): ... # 20 lines, differs by 1 line
```

**Fix**: `@pytest.mark.parametrize` or shared fixtures.'''
    ),
    (
        "thinking/testing-testing-datetime",
        "Our tests break every time daylight saving time changes or when run in different timezones. How do we properly test time-dependent code?",
        r'''<think>
Time-related test failures come from:
1. Using `datetime.now()` directly (tied to wall clock)
2. Using `date.today()` (changes at midnight)
3. Timezone-naive comparisons
4. DST transitions
5. Hardcoded dates that expire

Solution: inject time as a dependency, use freezegun, always use UTC internally.
</think>

## Rule 1: Never Call `datetime.now()` in Business Logic

```python
# BAD: Untestable, timezone-dependent
def is_trial_expired(user):
    return datetime.now() > user.trial_end

# GOOD: Time is a parameter
def is_trial_expired(user, now=None):
    now = now or datetime.now(timezone.utc)
    return now > user.trial_end

# Test: deterministic
def test_trial_not_expired():
    user = make_user(trial_end=datetime(2024, 6, 1, tzinfo=timezone.utc))
    now = datetime(2024, 5, 15, tzinfo=timezone.utc)
    assert is_trial_expired(user, now=now) is False
```

## Rule 2: Use freezegun for Integration Tests

```python
from freezegun import freeze_time

@freeze_time("2024-01-15 10:00:00")
def test_order_created_at():
    order = create_order(product_id=1, quantity=1)
    assert order.created_at == datetime(2024, 1, 15, 10, 0, 0)

@freeze_time("2024-03-10 01:59:00")  # Just before DST spring forward
def test_dst_transition():
    """Ensure scheduling works across DST boundaries."""
    task = schedule_task(run_in=timedelta(hours=2))
    assert task.scheduled_for == datetime(2024, 3, 10, 3, 59, 0)  # Skips 2AM
```

## Rule 3: Always Use UTC Internally

```python
# BAD: Local time — breaks across timezones
created_at = datetime.now()

# GOOD: UTC always
created_at = datetime.now(timezone.utc)

# Convert to local only for display
def display_time(utc_time, user_tz):
    return utc_time.astimezone(ZoneInfo(user_tz))
```

## Rule 4: Never Hardcode Dates That Expire

```python
# BAD: This test will fail after 2025
def test_coupon_valid():
    coupon = Coupon(expires=datetime(2025, 12, 31))
    assert coupon.is_valid()  # Fails on Jan 1, 2026

# GOOD: Relative dates
@freeze_time("2024-01-15")
def test_coupon_valid():
    coupon = Coupon(expires=datetime(2024, 12, 31, tzinfo=timezone.utc))
    assert coupon.is_valid()

# OR: Future-proof
def test_coupon_valid():
    future = datetime.now(timezone.utc) + timedelta(days=365)
    coupon = Coupon(expires=future)
    assert coupon.is_valid()
```

## Common Time Testing Pitfalls

| Pitfall | Fix |
|---------|-----|
| `datetime.now()` in code | Pass time as parameter or use freezegun |
| Comparing naive vs aware datetimes | Always use timezone-aware |
| Tests that assume local timezone | Use UTC everywhere |
| Hardcoded future dates | Use relative dates or freeze time |
| DST-sensitive tests | Test explicitly around transition times |'''
    ),
    (
        "thinking/testing-bdd-gherkin",
        "My product manager can't understand our test files. They want to verify that tests match the requirements. Should we use BDD with Gherkin?",
        r'''<think>
BDD with Gherkin (Given/When/Then) can bridge the gap between non-technical stakeholders and tests. But there are trade-offs:

Pros:
- Requirements are executable
- PM can read and verify scenarios
- Forces clear specification before coding
- Living documentation

Cons:
- Extra abstraction layer (step definitions)
- Maintenance overhead
- Not worth it for purely technical tests
- Can become verbose

Best used for: acceptance tests, user-facing features
Overkill for: unit tests, technical infrastructure
</think>

BDD is valuable **when non-technical people need to verify test coverage matches requirements**. But only for user-facing features.

## When BDD Fits

```gherkin
# features/checkout.feature — PM can read and verify this
Feature: Checkout
  As a customer
  I want to complete a purchase
  So that I receive my ordered items

  Scenario: Successful checkout with credit card
    Given I have a product "Widget" priced at $29.99 in my cart
    And I am logged in as "alice@example.com"
    When I proceed to checkout
    And I enter valid credit card details
    And I confirm the order
    Then I should see "Order confirmed"
    And I should receive a confirmation email
    And my cart should be empty

  Scenario: Checkout fails with insufficient stock
    Given I have 5 units of "Widget" in my cart
    And only 3 units are in stock
    When I proceed to checkout
    Then I should see "Only 3 units available"
    And my cart should still contain 5 units
```

```python
# Step definitions (pytest-bdd)
from pytest_bdd import given, when, then, scenario

@scenario('checkout.feature', 'Successful checkout with credit card')
def test_successful_checkout():
    pass

@given('I have a product "Widget" priced at $29.99 in my cart')
def cart_with_widget(cart, product_factory):
    product = product_factory(name='Widget', price=Decimal('29.99'))
    cart.add(product, quantity=1)

@when('I proceed to checkout')
def proceed_to_checkout(page):
    page.click('[data-testid="checkout-button"]')

@then('I should see "Order confirmed"')
def see_confirmation(page):
    assert page.text_content('[data-testid="status"]') == 'Order confirmed'
```

## When BDD Is Overkill

```python
# DON'T use Gherkin for unit tests
# This is absurd:
"""
Feature: String utility
  Scenario: Trim whitespace
    Given a string "  hello  "
    When I trim it
    Then the result should be "hello"
"""

# Just write a normal test:
def test_trim():
    assert trim("  hello  ") == "hello"
```

## Decision Guide

| Use BDD/Gherkin | Use Regular Tests |
|-----------------|-------------------|
| Acceptance criteria for user stories | Unit tests |
| Cross-team requirements verification | Technical infrastructure |
| Regulated industries (audit trail) | Internal services |
| PM actively reviews test scenarios | Only developers touch tests |

## Alternative: Descriptive Test Names

If BDD is too heavy, just write tests that PM can read from `pytest -v`:

```
tests/test_checkout.py::test_customer_can_complete_purchase_with_credit_card PASSED
tests/test_checkout.py::test_checkout_fails_when_product_out_of_stock PASSED
tests/test_checkout.py::test_expired_coupon_shows_error_message PASSED
tests/test_checkout.py::test_free_shipping_applied_for_orders_over_50 PASSED
```

**This is often enough** — readable test names without Gherkin overhead.'''
    ),
    (
        "thinking/testing-testcontainers",
        "We're using a mock Redis in tests but it doesn't behave exactly like real Redis. Our sorted set operations work in tests but fail in production. How do I test against real infrastructure without slowing down CI?",
        r'''<think>
Testcontainers — spin up real Docker containers (Redis, PostgreSQL, Kafka, etc.) for tests. They start fast, are isolated per test session, and clean up automatically.

This solves the "mock doesn't match real behavior" problem while keeping tests fast and isolated.
</think>

Use **Testcontainers** — real infrastructure in Docker, managed automatically:

```python
import pytest
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7") as redis:
        yield redis

@pytest.fixture
def redis_client(redis_container):
    import redis
    client = redis.Redis(
        host=redis_container.get_container_host_ip(),
        port=redis_container.get_exposed_port(6379),
    )
    yield client
    client.flushall()  # Clean between tests

# Now test against REAL Redis
def test_sorted_set_ranking(redis_client):
    redis_client.zadd('leaderboard', {'alice': 100, 'bob': 85, 'charlie': 92})
    top = redis_client.zrevrange('leaderboard', 0, 1, withscores=True)
    assert top[0] == (b'alice', 100.0)
    assert top[1] == (b'charlie', 92.0)

def test_sorted_set_increment(redis_client):
    redis_client.zadd('scores', {'player1': 50})
    redis_client.zincrby('scores', 10, 'player1')
    score = redis_client.zscore('scores', 'player1')
    assert score == 60.0  # Real Redis behavior, not mock approximation
```

## Supported Containers

```python
from testcontainers.postgres import PostgresContainer
from testcontainers.mysql import MySqlContainer
from testcontainers.kafka import KafkaContainer
from testcontainers.elasticsearch import ElasticSearchContainer
from testcontainers.mongodb import MongoDbContainer
from testcontainers.localstack import LocalStackContainer  # AWS services
```

## CI Configuration

```yaml
# GitHub Actions
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests with real infrastructure
        run: |
          pip install testcontainers pytest
          pytest tests/
    # Docker is available on GitHub Actions by default
```

## Speed Tips

```python
# Session-scoped: container starts once, shared across all tests
@pytest.fixture(scope="session")
def postgres(request):
    with PostgresContainer("postgres:16") as pg:
        yield pg

# Use transaction rollback per test (fast cleanup)
@pytest.fixture
def db_session(postgres):
    engine = create_engine(postgres.get_connection_url())
    conn = engine.connect()
    trans = conn.begin()
    yield Session(bind=conn)
    trans.rollback()  # Instant cleanup
    conn.close()
```

Container startup: ~2-5 seconds (once per session). Individual tests: milliseconds.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
