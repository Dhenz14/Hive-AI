"""Phase 1F: Foundation Thinking — Testing Strategy (Part 2/4)
Integration testing, end-to-end testing, API testing, database testing."""

PAIRS = [
    (
        "thinking/testing-api-testing-patterns",
        "How should I structure API tests for a REST API? I want to test beyond just 'does it return 200'.",
        r'''<think>
Good API testing needs to cover:
1. Happy path — correct request → correct response
2. Validation — invalid inputs → proper error responses
3. Authentication/Authorization — unauthenticated → 401, unauthorized → 403
4. Edge cases — empty lists, max pagination, special characters
5. Idempotency — repeated requests don't cause duplicate side effects
6. Response format — correct status codes, headers, content type

Let me structure this as a practical test organization pattern.
</think>

Structure API tests in layers — each layer catches different bugs:

## Layer 1: Happy Path + Response Contract

```python
class TestCreateOrder:
    def test_creates_order_successfully(self, client, auth_headers):
        response = client.post('/api/orders', json={
            'product_id': 1,
            'quantity': 2,
        }, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()

        # Response contract — structure is correct
        assert 'id' in data
        assert data['product_id'] == 1
        assert data['quantity'] == 2
        assert data['status'] == 'pending'
        assert 'created_at' in data

        # Side effect — actually persisted
        order = Order.query.get(data['id'])
        assert order is not None
```

## Layer 2: Validation Errors

```python
    def test_rejects_missing_product_id(self, client, auth_headers):
        response = client.post('/api/orders', json={
            'quantity': 2,
        }, headers=auth_headers)
        assert response.status_code == 400
        assert 'product_id' in response.json()['errors'][0]['field']

    def test_rejects_zero_quantity(self, client, auth_headers):
        response = client.post('/api/orders', json={
            'product_id': 1, 'quantity': 0,
        }, headers=auth_headers)
        assert response.status_code == 400

    def test_rejects_nonexistent_product(self, client, auth_headers):
        response = client.post('/api/orders', json={
            'product_id': 99999, 'quantity': 1,
        }, headers=auth_headers)
        assert response.status_code == 404
```

## Layer 3: Auth

```python
    def test_unauthenticated_returns_401(self, client):
        response = client.post('/api/orders', json={
            'product_id': 1, 'quantity': 1,
        })
        assert response.status_code == 401

    def test_cannot_view_other_users_orders(self, client, user_b_headers):
        response = client.get('/api/orders/1', headers=user_b_headers)
        assert response.status_code == 403
```

## Layer 4: Edge Cases

```python
    def test_empty_order_list(self, client, auth_headers):
        response = client.get('/api/orders', headers=auth_headers)
        assert response.status_code == 200
        assert response.json()['data'] == []
        assert response.json()['meta']['total'] == 0

    def test_pagination_beyond_last_page(self, client, auth_headers):
        response = client.get('/api/orders?page=999', headers=auth_headers)
        assert response.status_code == 200
        assert response.json()['data'] == []

    def test_special_characters_in_search(self, client, auth_headers):
        response = client.get(
            "/api/orders?q=test%27%3B+DROP+TABLE",
            headers=auth_headers,
        )
        assert response.status_code == 200  # Doesn't crash
```

## Layer 5: Idempotency

```python
    def test_create_is_idempotent_with_key(self, client, auth_headers):
        payload = {'product_id': 1, 'quantity': 1}
        headers = {**auth_headers, 'Idempotency-Key': 'unique-123'}

        r1 = client.post('/api/orders', json=payload, headers=headers)
        r2 = client.post('/api/orders', json=payload, headers=headers)

        assert r1.status_code == 201
        assert r2.status_code == 200  # Returns existing, doesn't create duplicate
        assert r1.json()['id'] == r2.json()['id']
        assert Order.query.count() == 1
```

Every endpoint should have tests in at least layers 1-3. Add layer 4-5 for critical endpoints.'''
    ),
    (
        "thinking/testing-database-testing",
        "How do I test complex database queries and migrations? My queries involve joins, aggregations, and window functions that SQLite can't handle, so I need a real PostgreSQL database.",
        r'''<think>
Testing complex DB queries requires:
1. A real PostgreSQL instance (Docker is standard)
2. Migration testing (schema changes work)
3. Query correctness (joins, aggregations return right data)
4. Performance testing (queries don't degrade)

Let me cover the practical setup.
</think>

Use a real PostgreSQL in Docker for CI, with transaction rollback for speed:

## Setup: Docker PostgreSQL for Tests

```yaml
# docker-compose.test.yml
services:
  test-db:
    image: postgres:16
    environment:
      POSTGRES_DB: test_db
      POSTGRES_PASSWORD: test
    ports:
      - "5433:5432"
    tmpfs:
      - /var/lib/postgresql/data  # RAM disk = fast
```

```python
# conftest.py
import pytest
from sqlalchemy import create_engine

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("postgresql://postgres:test@localhost:5433/test_db")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()  # Instant cleanup
    connection.close()
```

## Testing Complex Queries

```python
def test_top_customers_by_revenue(db_session):
    # Setup
    alice = make_user(db_session, name='Alice')
    bob = make_user(db_session, name='Bob')
    make_order(db_session, user=alice, total=Decimal('500'))
    make_order(db_session, user=alice, total=Decimal('300'))
    make_order(db_session, user=bob, total=Decimal('200'))

    # Execute the actual query being tested
    results = get_top_customers(db_session, limit=10)

    assert len(results) == 2
    assert results[0].user_name == 'Alice'
    assert results[0].total_revenue == Decimal('800')
    assert results[1].user_name == 'Bob'
    assert results[1].total_revenue == Decimal('200')

def test_monthly_revenue_window_function(db_session):
    """Test query with window functions — impossible in SQLite."""
    make_order(db_session, created=date(2024, 1, 15), total=100)
    make_order(db_session, created=date(2024, 1, 20), total=200)
    make_order(db_session, created=date(2024, 2, 10), total=150)

    results = get_monthly_revenue_with_running_total(db_session, year=2024)

    assert results[0].month == 1
    assert results[0].revenue == Decimal('300')
    assert results[0].running_total == Decimal('300')
    assert results[1].month == 2
    assert results[1].revenue == Decimal('150')
    assert results[1].running_total == Decimal('450')
```

## Testing Migrations

```python
from alembic.command import upgrade, downgrade
from alembic.config import Config

def test_migration_roundtrip():
    """Every migration can go up AND back down."""
    alembic_cfg = Config("alembic.ini")

    # Apply all migrations
    upgrade(alembic_cfg, "head")

    # Rollback all migrations
    downgrade(alembic_cfg, "base")

    # Apply again — should work cleanly
    upgrade(alembic_cfg, "head")

def test_migration_with_data():
    """Migration handles existing data correctly."""
    alembic_cfg = Config("alembic.ini")

    # Apply up to the migration before the one we're testing
    upgrade(alembic_cfg, "abc123")

    # Insert test data in old schema
    db.execute("INSERT INTO users (name) VALUES ('Alice')")

    # Apply the migration we're testing
    upgrade(alembic_cfg, "def456")

    # Verify data was migrated correctly
    result = db.execute("SELECT full_name FROM users").fetchone()
    assert result[0] == 'Alice'  # name → full_name migration worked
```

## Query Performance Testing

```python
def test_search_query_uses_index(db_session):
    """Ensure the query uses an index, not a sequential scan."""
    # Insert enough data for the planner to prefer index scan
    for i in range(10000):
        make_product(db_session, name=f'Product {i}')

    result = db_session.execute(text(
        "EXPLAIN ANALYZE SELECT * FROM products WHERE name = 'Product 5000'"
    )).fetchall()
    plan = '\n'.join(row[0] for row in result)

    assert 'Index Scan' in plan or 'Index Only Scan' in plan
    assert 'Seq Scan' not in plan
```'''
    ),
    (
        "thinking/testing-e2e-strategies",
        "Our E2E tests with Playwright are slow and flaky. They take 20 minutes and fail 30% of the time. Should we just delete them?",
        r'''<think>
Don't delete E2E tests — reduce them to only the critical paths, and fix the flakiness.

The typical problems with E2E suites:
1. Too many E2E tests (testing things that should be unit/integration tests)
2. Flaky selectors (CSS classes change, element not found)
3. Timing issues (waiting for elements that load async)
4. Shared state between tests
5. External dependencies (APIs, emails)

The fix: keep only critical user journeys, use data-testid selectors, proper waiting strategies, and test isolation.
</think>

Don't delete them — **shrink and stabilize** them.

## Step 1: Keep Only Critical Journeys (Cut 80%)

You don't need E2E for everything. Keep only the paths that would cost real money if broken:

```
✅ Keep:
  - User registration → email verification → first login
  - Add to cart → checkout → payment → order confirmation
  - Password reset flow

❌ Delete (use unit/integration tests instead):
  - Form validation errors (test at API level)
  - Sorting and filtering (test at component level)
  - Edge cases (test at unit level)
```

**Target**: 5-10 E2E tests, not 200.

## Step 2: Fix Flaky Selectors

```python
# FLAKY: CSS class changes break the test
page.click('.btn-primary.submit-form')

# FLAKY: Text changes break the test
page.click('text=Submit Your Order Now!')

# STABLE: data-testid never changes
page.click('[data-testid="checkout-submit"]')
```

## Step 3: Fix Timing Issues

```python
# FLAKY: Arbitrary sleep
page.click('[data-testid="submit"]')
time.sleep(3)  # Maybe 3 seconds is enough?
assert page.text_content('.result') == 'Success'

# STABLE: Wait for the actual condition
page.click('[data-testid="submit"]')
page.wait_for_selector('[data-testid="success-message"]', timeout=10000)
assert page.text_content('[data-testid="success-message"]') == 'Success'
```

## Step 4: Isolate Each Test

```python
# FLAKY: Tests depend on each other's data
def test_create_order():  # Creates order #1
    ...
def test_view_orders():   # Expects order #1 to exist
    ...

# STABLE: Each test sets up its own state via API
def test_view_orders(api_client):
    # Seed data through the API, not the UI
    api_client.post('/api/orders', json={'product_id': 1, 'quantity': 1})

    page.goto('/orders')
    page.wait_for_selector('[data-testid="order-row"]')
    assert page.locator('[data-testid="order-row"]').count() >= 1
```

## Step 5: Parallelize

```python
# playwright.config.ts
export default defineConfig({
  workers: 4,           # Run 4 tests in parallel
  retries: 1,           # One retry for flaky network
  timeout: 30_000,
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',  # Capture trace only on failure
  },
});
```

## Result

| Before | After |
|--------|-------|
| 200 E2E tests | 8 E2E tests |
| 20 minutes | 2 minutes |
| 30% failure rate | <5% failure rate |
| Flaky selectors | data-testid attributes |
| Sleep-based waits | Condition-based waits |'''
    ),
    (
        "thinking/testing-testing-microservices",
        "We're transitioning from a monolith to microservices. How do we test the interactions between services without running everything together?",
        r'''<think>
The microservice testing challenge: services communicate over the network, so you can't just import and call functions. The testing strategy needs to cover:

1. Individual service tests (unit + integration within service)
2. Service contract tests (API compatibility)
3. Limited E2E tests (critical cross-service flows)

The key insight: test as much as possible within each service, and use contract testing to verify the interfaces between services.
</think>

## The Microservice Testing Strategy

```
                    ┌─────────────┐
                    │  E2E Tests  │  ← 2-3 critical flows only
                    │  (minutes)  │
                    └──────┬──────┘
              ┌────────────┴────────────┐
              │   Contract Tests (Pact)  │  ← Verify API compatibility
              │       (seconds)          │
              └────────────┬─────────────┘
    ┌──────────────────────┴──────────────────────┐
    │         Integration Tests per Service        │
    │              (seconds each)                  │
    └──────────────────────┬───────────────────────┘
    ┌──────────────────────┴──────────────────────┐
    │           Unit Tests per Service             │
    │             (milliseconds)                   │
    └─────────────────────────────────────────────┘
```

## Level 1: Test Each Service in Isolation

```python
# Order Service tests — mock external services
class TestOrderService:
    def test_create_order(self, db, mock_inventory_client):
        mock_inventory_client.check_stock.return_value = StockResult(
            available=True, quantity=100
        )

        order = order_service.create_order(
            user_id=1, product_id=42, quantity=2
        )

        assert order.status == 'pending'
        mock_inventory_client.check_stock.assert_called_once_with(
            product_id=42, quantity=2
        )

    def test_create_order_out_of_stock(self, db, mock_inventory_client):
        mock_inventory_client.check_stock.return_value = StockResult(
            available=False, quantity=0
        )

        with pytest.raises(OutOfStockError):
            order_service.create_order(user_id=1, product_id=42, quantity=2)
```

## Level 2: Contract Tests Between Services

```python
# Order Service (consumer) defines what it expects from Inventory Service
@pact_consumer("OrderService")
@pact_provider("InventoryService")
def test_check_stock_contract(pact):
    pact.given("product 42 has 100 units in stock")
    pact.upon_receiving("a stock check for product 42")
    pact.with_request("GET", "/api/inventory/42/stock")
    pact.will_respond_with(200, body={
        "product_id": Like(42),
        "available": Like(True),
        "quantity": Like(100),
    })

    with pact:
        result = inventory_client.check_stock(42, quantity=2)
        assert result.available is True

# Inventory Service (provider) verifies it meets the contract
def test_verify_order_service_contract():
    verifier = Verifier(provider="InventoryService")
    verifier.verify_pacts("pacts/OrderService-InventoryService.json")
```

## Level 3: Minimal E2E (Critical Flows Only)

```python
# Docker Compose spins up all services
# Test the complete purchase flow
def test_purchase_flow(live_services):
    # Register user
    user = api.post('/auth/register', json={...})

    # Add to cart
    api.post('/cart/items', json={'product_id': 1, 'qty': 2},
             headers=auth(user))

    # Checkout
    order = api.post('/orders/checkout', json={'payment_method': 'test'},
                     headers=auth(user))
    assert order.status_code == 201

    # Verify order status (async — poll)
    wait_until(
        lambda: api.get(f'/orders/{order.json()["id"]}',
                       headers=auth(user)).json()['status'] == 'confirmed',
        timeout=30,
    )
```

## Key Rules
1. **90% of tests run within each service** (fast, reliable)
2. **Contract tests verify API shapes** between services (no runtime dependency)
3. **E2E tests: 5 max** — only flows that cross 3+ services and involve money
4. **Mock external services in unit tests**, use contracts to verify mocks are accurate'''
    ),
    (
        "thinking/testing-testing-async-code",
        "I'm struggling to test async code properly. My tests either hang, pass when they shouldn't, or have race conditions:\n\n```python\nasync def process_batch(items):\n    results = []\n    async with aiohttp.ClientSession() as session:\n        tasks = [fetch_and_transform(session, item) for item in items]\n        results = await asyncio.gather(*tasks, return_exceptions=True)\n    \n    successes = [r for r in results if not isinstance(r, Exception)]\n    failures = [r for r in results if isinstance(r, Exception)]\n    \n    if failures:\n        logger.warning(f'{len(failures)} items failed')\n    \n    return successes\n\nasync def fetch_and_transform(session, item):\n    async with session.get(item.url, timeout=aiohttp.ClientTimeout(total=5)) as resp:\n        data = await resp.json()\n    return transform(data)\n```",
        r'''<think>
Testing async code challenges:
1. Need an async test runner (pytest-asyncio)
2. Need to mock async context managers (aiohttp session)
3. Need to test gather behavior (partial failures)
4. Need to avoid real HTTP calls

Let me show how to test each aspect properly.
</think>

Use `pytest-asyncio` with proper async mocking:

## Setup

```bash
pip install pytest-asyncio aioresponses
```

```ini
# pytest.ini
[pytest]
asyncio_mode = auto
```

## Test Happy Path

```python
from aioresponses import aioresponses

@pytest.mark.asyncio
async def test_process_batch_success():
    items = [
        Item(url='http://api.example.com/1'),
        Item(url='http://api.example.com/2'),
    ]

    with aioresponses() as mocked:
        mocked.get('http://api.example.com/1', payload={'value': 10})
        mocked.get('http://api.example.com/2', payload={'value': 20})

        results = await process_batch(items)

    assert len(results) == 2
    assert results[0] == transform({'value': 10})
    assert results[1] == transform({'value': 20})
```

## Test Partial Failures (gather with return_exceptions)

```python
@pytest.mark.asyncio
async def test_process_batch_partial_failure():
    items = [
        Item(url='http://api.example.com/1'),
        Item(url='http://api.example.com/2'),
        Item(url='http://api.example.com/3'),
    ]

    with aioresponses() as mocked:
        mocked.get('http://api.example.com/1', payload={'value': 10})
        mocked.get('http://api.example.com/2', status=500)  # Server error
        mocked.get('http://api.example.com/3', payload={'value': 30})

        results = await process_batch(items)

    # Only successful items returned
    assert len(results) == 2
```

## Test Timeout Handling

```python
@pytest.mark.asyncio
async def test_process_batch_timeout():
    items = [Item(url='http://api.example.com/slow')]

    with aioresponses() as mocked:
        mocked.get('http://api.example.com/slow',
                    exception=asyncio.TimeoutError())

        results = await process_batch(items)

    assert len(results) == 0  # Timeout treated as failure
```

## Test All Items Fail

```python
@pytest.mark.asyncio
async def test_process_batch_all_fail(caplog):
    items = [
        Item(url='http://api.example.com/1'),
        Item(url='http://api.example.com/2'),
    ]

    with aioresponses() as mocked:
        mocked.get('http://api.example.com/1', status=500)
        mocked.get('http://api.example.com/2', status=500)

        results = await process_batch(items)

    assert len(results) == 0
    assert '2 items failed' in caplog.text
```

## Common Async Testing Mistakes

```python
# WRONG: Forgetting to await
async def test_bad():
    result = process_batch(items)  # Returns coroutine, not result!
    assert result  # Truthy because coroutine object exists

# RIGHT:
async def test_good():
    result = await process_batch(items)
    assert result

# WRONG: Blocking call in async test
async def test_bad():
    time.sleep(1)  # Blocks the event loop!

# RIGHT:
async def test_good():
    await asyncio.sleep(1)  # Yields to event loop
```'''
    ),
    (
        "thinking/testing-testing-error-scenarios",
        "How do I systematically test error handling? I usually test the happy path but forget edge cases. Is there a framework for thinking about what can go wrong?",
        r'''<think>
Let me provide a systematic framework for identifying error scenarios. The FAILURE mnemonic or similar.

Categories of things that can go wrong:
1. Input errors — invalid, missing, wrong type, too large
2. External dependencies — down, slow, returning errors
3. Resource exhaustion — memory, disk, connections
4. Concurrency — race conditions, deadlocks
5. State errors — wrong order of operations, stale data
6. Security — unauthorized, injection, replay

For each function, go through these categories and ask "what if?"
</think>

Use the **FATES** framework — five categories of failures to test for every function:

## F - Format / Input Failures

```python
# For any function that accepts input, test:
@pytest.mark.parametrize("bad_input", [
    None,                    # Null
    "",                      # Empty
    " ",                     # Whitespace only
    "x" * 1_000_000,        # Very large
    "<script>alert(1)</script>",  # Malicious
    "'; DROP TABLE--",      # Injection
    "\x00\xff",             # Binary data
    -1,                     # Negative number
    0,                      # Zero
    float('inf'),           # Infinity
    float('nan'),           # NaN
])
def test_handles_bad_input(bad_input):
    # Should raise ValidationError, not crash
    with pytest.raises((ValidationError, TypeError, ValueError)):
        process(bad_input)
```

## A - Availability Failures (External Dependencies)

```python
# For any function that calls external services:

def test_database_timeout():
    mock_db.get.side_effect = TimeoutError()
    with pytest.raises(ServiceUnavailable):
        get_user(1)

def test_api_returns_500():
    mock_api.fetch.side_effect = HttpError(500)
    result = fetch_data()
    assert result.fallback_used is True

def test_api_returns_malformed_json():
    mock_api.fetch.return_value = "not json {"
    with pytest.raises(DataError):
        fetch_data()

def test_connection_refused():
    mock_client.connect.side_effect = ConnectionRefusedError()
    with pytest.raises(ServiceUnavailable):
        process_payment()
```

## T - Timing / State Failures

```python
# For any function with state transitions:

def test_cancel_already_shipped_order():
    order = make_order(status='shipped')
    with pytest.raises(InvalidTransition):
        order.cancel()

def test_concurrent_stock_update():
    """Two threads try to buy the last item."""
    product = make_product(stock=1)
    with concurrent_execute(
        lambda: buy(product, qty=1),
        lambda: buy(product, qty=1),
    ) as results:
        successes = [r for r in results if not isinstance(r, Exception)]
        assert len(successes) == 1  # Only one should succeed

def test_expired_token():
    token = generate_token(expires_in=timedelta(seconds=-1))
    with pytest.raises(TokenExpired):
        verify_token(token)
```

## E - Edge / Boundary Cases

```python
# For any function with numeric inputs or limits:

def test_exact_boundary():
    assert shipping_cost(Decimal('100.00')) == Decimal(0)    # Exact threshold
    assert shipping_cost(Decimal('99.99')) == Decimal('5.99') # Just below
    assert shipping_cost(Decimal('100.01')) == Decimal(0)    # Just above

def test_empty_collection():
    assert average([]) is None       # Empty list
    assert average([42]) == 42       # Single item
    assert average([1, 2]) == 1.5    # Two items

def test_max_values():
    create_user(name="x" * 255)      # Max varchar length
    with pytest.raises(ValidationError):
        create_user(name="x" * 256)  # Exceeds max
```

## S - Security Failures

```python
def test_cannot_access_other_users_data():
    response = client.get('/api/users/2/orders',
                          headers=user_1_auth)
    assert response.status_code == 403

def test_rate_limited_after_threshold():
    for _ in range(100):
        client.post('/api/login', json={'email': 'x', 'password': 'y'})
    response = client.post('/api/login', json={'email': 'x', 'password': 'y'})
    assert response.status_code == 429

def test_sql_injection_prevented():
    response = client.get("/api/users?name='; DROP TABLE users--")
    assert response.status_code in (200, 400)  # Not 500
    assert User.query.count() > 0  # Table still exists
```

## Apply FATES to Every Function

For each function, ask:
- **F**ormat: What if inputs are wrong/missing/huge/malicious?
- **A**vailability: What if dependencies are down/slow/broken?
- **T**iming: What if state changed between check and action?
- **E**dge: What about boundaries, empty, single, max values?
- **S**ecurity: Can unauthorized users trigger this?'''
    ),
    (
        "thinking/testing-test-readability",
        "Our tests are hard to understand. New team members can't figure out what's being tested. How do we write more readable tests?\n\n```python\ndef test_1():\n    u = User(n='A', e='a@b.c', t='g')\n    o = Order(u=u, i=[Item(p=10, q=2), Item(p=5, q=1)])\n    o.ad(Coupon('X', 10))\n    assert o.t == 13.5\n\ndef test_2():\n    u = User(n='B', e='b@c.d', t='f')\n    o = Order(u=u, i=[Item(p=100, q=1)])\n    assert o.t == 100\n```",
        r'''<think>
These tests are unreadable because:
1. Single-letter variables
2. Abbreviated method/property names
3. No test names that describe what's being tested
4. No comments or structure
5. Hard to tell what the assertion is actually verifying

The fix: use the AAA pattern (Arrange/Act/Assert), descriptive names, and the "should" naming convention.
</think>

Tests should read like specifications. Use the **AAA pattern** and descriptive names:

## The AAA Pattern: Arrange → Act → Assert

```python
# BEFORE: Unreadable
def test_1():
    u = User(n='A', e='a@b.c', t='g')
    o = Order(u=u, i=[Item(p=10, q=2), Item(p=5, q=1)])
    o.ad(Coupon('X', 10))
    assert o.t == 13.5

# AFTER: Self-documenting
def test_gold_member_gets_coupon_discount_on_order_total():
    # Arrange: set up the scenario
    user = make_user(tier='gold')
    order = make_order(
        user=user,
        items=[
            make_item(price=Decimal('10'), quantity=2),  # $20
            make_item(price=Decimal('5'), quantity=1),   # $5
        ],
    )
    # Subtotal: $25, Gold discount: 10% = $22.50

    # Act: perform the action being tested
    order.apply_coupon(Coupon(code='SAVE10', percent_off=10))

    # Assert: verify the expected outcome
    assert order.total == Decimal('13.50')
    # $22.50 after gold discount, then 10% coupon = $13.50?
    # Wait — is that right? Now we can actually REASON about the test
```

## Test Naming Convention

```python
# Pattern: test_[scenario]_[expected_outcome]

def test_empty_cart_has_zero_total():
    ...

def test_expired_coupon_is_rejected():
    ...

def test_free_shipping_applied_above_threshold():
    ...

def test_out_of_stock_prevents_checkout():
    ...
```

Each test name is a specification. Running `pytest -v` produces documentation:

```
tests/test_orders.py::test_empty_cart_has_zero_total PASSED
tests/test_orders.py::test_expired_coupon_is_rejected PASSED
tests/test_orders.py::test_free_shipping_applied_above_threshold PASSED
tests/test_orders.py::test_out_of_stock_prevents_checkout PASSED
```

## Rules for Readable Tests

1. **Full words, no abbreviations** — `user` not `u`, `order` not `o`
2. **Blank line between Arrange/Act/Assert** — visual separation
3. **One assertion concept per test** — even if it's multiple assert statements
4. **Test name = specification** — should read like English
5. **Comments explain WHY, not WHAT** — `# Gold discount: 10%` not `# create user`
6. **Magic numbers get labels** — `make_item(price=Decimal('10'))` not `Item(p=10)`'''
    ),
    (
        "thinking/testing-legacy-code-testing",
        "I inherited a codebase with zero tests and the code is full of tightly coupled classes, global state, and side effects. I can't refactor it because I have no tests, and I can't write tests because the code isn't testable. How do I break this chicken-and-egg problem?",
        r'''<think>
This is the classic legacy code testing dilemma from Michael Feathers' "Working Effectively with Legacy Code."

The approach:
1. Start with characterization tests (pin current behavior, even if buggy)
2. Use the "Sprout Method" technique (write new code in testable functions, call from legacy code)
3. Use "Wrap Method" (wrap untestable code with a testable layer)
4. Gradually build a safety net

Key principle: you don't need to understand the code perfectly to write a characterization test. Just call it and assert what it returns.
</think>

Use Michael Feathers' legacy code techniques. Start with **characterization tests**, then extract.

## Step 1: Characterization Tests (Pin Current Behavior)

You don't need to understand the code. Just call it and assert what happens:

```python
# The untestable legacy function
def calculate_invoice(customer_id):
    # 200 lines of spaghetti with database calls,
    # global config, file writes, etc.
    ...

# Characterization test: pin whatever it does RIGHT NOW
def test_characterize_calculate_invoice(legacy_db):
    """I don't know if this is correct, but this is what it does."""
    # Seed database with known state
    legacy_db.execute("INSERT INTO customers VALUES (1, 'Acme', 'gold')")
    legacy_db.execute("INSERT INTO orders VALUES (1, 1, 500.00, '2024-01-01')")

    result = calculate_invoice(customer_id=1)

    # Assert whatever it returns — this is the CURRENT behavior
    assert result['total'] == 450.00  # Apparently gold gets 10% off
    assert result['tax'] == 36.00
    assert result['line_items'][0]['amount'] == 500.00
```

Now you have a safety net. If you change something and this test breaks, you know you changed behavior.

## Step 2: Sprout Method (New Code Is Testable)

```python
# BEFORE: Adding validation to the legacy function
def calculate_invoice(customer_id):
    customer = db.get_customer(customer_id)  # Untestable
    # ... 200 lines of legacy code
    # You need to add: reject invoices over credit limit
    if total > customer.credit_limit:  # Where to add this?
        raise CreditLimitExceeded()

# AFTER: Sprout a new testable function
def check_credit_limit(total: Decimal, credit_limit: Decimal) -> None:
    """New code, fully testable, no dependencies."""
    if total > credit_limit:
        raise CreditLimitExceeded(
            f"Invoice {total} exceeds limit {credit_limit}"
        )

# Call it from legacy code
def calculate_invoice(customer_id):
    customer = db.get_customer(customer_id)
    # ... 200 lines of legacy code
    check_credit_limit(total, customer.credit_limit)  # New testable code

# Test the new function easily
def test_credit_limit_exceeded():
    with pytest.raises(CreditLimitExceeded):
        check_credit_limit(Decimal('1000'), Decimal('500'))

def test_credit_limit_ok():
    check_credit_limit(Decimal('500'), Decimal('1000'))  # No exception
```

## Step 3: Wrap Method (Wrap Untestable Code)

```python
# Legacy code with side effects baked in
def save_order(order_data):
    # Validates, saves to DB, sends email, updates inventory
    # ALL in one function — can't test validation without saving
    ...

# Wrap it: extract the testable logic
class OrderSaver:
    def save(self, order_data):
        validated = self.validate(order_data)   # Testable
        record = self.to_record(validated)       # Testable
        self._legacy_save(record)                # Untestable (for now)

    def validate(self, order_data):
        """Extracted from legacy code — now independently testable."""
        if not order_data.get('items'):
            raise ValidationError('No items')
        if order_data['total'] < 0:
            raise ValidationError('Negative total')
        return order_data

    def to_record(self, data):
        """Pure transformation — easy to test."""
        return OrderRecord(
            customer_id=data['customer_id'],
            total=Decimal(str(data['total'])),
            items=[...],
        )

    def _legacy_save(self, record):
        """The old untestable code, isolated."""
        save_order_legacy(record)
```

## The Progression

```
Week 1:  Characterization tests on critical paths
Week 2:  Sprout new features as testable functions
Week 3:  Wrap legacy code, extract pure logic
Week 4+: Gradually replace legacy internals
```

**Never do a big rewrite.** Incremental extraction with a growing test safety net.'''
    ),
    (
        "thinking/testing-approval-testing",
        "I need to test a function that generates complex HTML email templates. Writing assertions for every element is impractical. What's the best approach?",
        r'''<think>
For complex text/HTML output, approval testing (also called golden master testing) is ideal:
1. Run the function, save the output to a file
2. Human reviews and "approves" it
3. Future runs compare against the approved output
4. Any change shows a diff for review

This is like snapshot testing but for larger, more complex outputs like emails, reports, PDFs.
</think>

Use **approval testing** — generate the output, review it once, then auto-compare on future runs:

```python
import approvaltests
from approvaltests.approvals import verify

def test_welcome_email_template():
    user = make_user(name='Alice', tier='premium')
    html = render_welcome_email(user)
    verify(html)

def test_invoice_email():
    order = make_order(
        items=[
            make_item(name='Widget', price=Decimal('29.99'), quantity=2),
            make_item(name='Gadget', price=Decimal('49.99'), quantity=1),
        ],
        discount=Decimal('10.00'),
        shipping=Decimal('5.99'),
    )
    html = render_invoice_email(order)
    verify(html)
```

## How It Works

**First run**: Creates `test_welcome_email_template.approved.html` — you review and approve it.

**Future runs**: Compares output against approved file. If different, test fails and shows a diff:

```diff
- <h1>Welcome, Alice!</h1>
+ <h1>Welcome Alice!</h1>    ← Missing comma — intentional or bug?
- <p>Your Premium benefits:</p>
+ <p>Your premium benefits:</p>  ← Capitalization changed
```

## When to Use Approval Testing vs Unit Tests

| Approval Testing | Unit Testing |
|-----------------|--------------|
| Complex HTML/text output | Simple return values |
| Reports, emails, PDFs | Calculations, logic |
| Serialized data structures | Boolean conditions |
| Output too complex for assertions | Small, focused checks |

## Combining Both

```python
def test_invoice_email_content():
    """Approval test: full output looks right."""
    html = render_invoice_email(order)
    verify(html)

def test_invoice_email_contains_total():
    """Unit test: critical business value is correct."""
    html = render_invoice_email(order)
    assert '$105.97' in html  # Exact total must be right
```

Use approval testing for "does it look right?" and unit tests for "is the critical value correct?"'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
