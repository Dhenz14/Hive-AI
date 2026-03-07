"""
Ambiguous request handling pairs - vague testing requests
"""

pairs = [
    {
        "instruction": r'''Add tests to our project.''',
        "output": r'''<think>
"Add tests" -- to what? The whole project? A specific module? What kind of tests -- unit, integration, end-to-end? What language/framework? What testing tools are already set up, if any? What's the most critical code that needs testing first? Without knowing the codebase, I can't write meaningful tests. I need to understand the project structure and priorities.
</think>

Before writing tests, I need to understand a few things:

1. **What's the tech stack?** Language, framework, and any existing test setup (pytest, jest, etc.)?
2. **What's the highest-risk code?** Tests should cover the most critical/fragile parts first. What would be worst to break -- payment processing, user auth, data calculations?
3. **What kind of tests?** Unit tests (fast, isolated), integration tests (with database/APIs), or end-to-end tests (full user flows)?

Here's a testing strategy and starter setup assuming a Python project with pytest (the most common case):

```python
# conftest.py -- shared test fixtures
import pytest
from your_app import create_app
from your_app.database import db as _db

@pytest.fixture(scope="session")
def app():
    """Create app with test config."""
    app = create_app(testing=True)
    return app

@pytest.fixture(scope="function")
def db(app):
    """Fresh database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()

@pytest.fixture
def client(app):
    """Test HTTP client."""
    return app.test_client()


# tests/test_user_service.py -- unit tests for business logic
class TestUserService:
    def test_register_creates_user(self, db):
        service = UserService(db.session)
        user = service.register("test@example.com", "securepassword123")

        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.hashed_password != "securepassword123"  # should be hashed

    def test_register_rejects_duplicate_email(self, db):
        service = UserService(db.session)
        service.register("test@example.com", "password123")

        with pytest.raises(EmailAlreadyTaken):
            service.register("test@example.com", "different_password")

    def test_register_rejects_weak_password(self, db):
        service = UserService(db.session)
        with pytest.raises(ValueError, match="at least 8 characters"):
            service.register("test@example.com", "short")


# tests/test_api.py -- integration tests for API endpoints
class TestOrderAPI:
    def test_create_order_returns_201(self, client, db):
        response = client.post("/api/orders", json={
            "customer_id": 1,
            "items": [{"product_id": 1, "quantity": 2}],
        })
        assert response.status_code == 201
        assert "order_id" in response.json

    def test_create_order_without_items_returns_400(self, client):
        response = client.post("/api/orders", json={
            "customer_id": 1,
            "items": [],
        })
        assert response.status_code == 400
```

```text
Recommended testing priority:
1. Authentication and authorization (security-critical)
2. Payment/billing logic (money-critical)
3. Core business rules (what makes your app valuable)
4. Data validation (input boundaries)
5. Edge cases in complex calculations
6. API contract tests (request/response shapes)
```

Share your project structure and I'll write tests for your most critical module.'''
    },
    {
        "instruction": r'''Improve our test coverage. It's too low.''',
        "output": r'''<think>
"Improve test coverage" -- what's the current coverage? What's the target? Coverage percentage alone is misleading -- 80% coverage with shallow tests is worse than 50% coverage of critical paths. I don't know what's tested and what's not, or what the most important untested code is. I need to see the coverage report to find the gaps.
</think>

A few questions to focus the effort:

1. **What's the current coverage?** And what's your target? (Common targets: 70-80% for most apps)
2. **Can you share the coverage report?** The gaps are more useful than the number -- `pytest --cov=your_app --cov-report=html` shows exactly which lines are untested.
3. **Are critical paths covered?** High coverage with no tests on payment logic is worse than low coverage with solid payment tests.

Here's how to find and fill coverage gaps efficiently:

```bash
# Step 1: Generate a coverage report to find gaps
pytest --cov=your_app --cov-report=term-missing --cov-report=html

# Output shows:
# Name                     Stmts   Miss  Cover   Missing
# your_app/auth.py           50     12    76%     34-38, 52-58
# your_app/orders.py        120     85    29%     15-99, 110-120
# your_app/utils.py          30      2    93%     18, 25

# orders.py at 29% is the priority
```

```python
# Step 2: Write tests for the biggest gaps, focusing on branches

# Common untested patterns to look for:

# A. Error paths -- tests often only cover the happy path
def test_get_user_not_found(client):
    response = client.get("/api/users/99999")
    assert response.status_code == 404

def test_create_order_invalid_product(client):
    response = client.post("/api/orders", json={
        "items": [{"product_id": -1, "quantity": 1}]
    })
    assert response.status_code == 400

# B. Boundary conditions
def test_discount_does_not_go_negative():
    result = apply_discount(total=5.00, discount=10.00)
    assert result == 0.00  # not -5.00

def test_pagination_beyond_last_page(client):
    response = client.get("/api/products?page=9999")
    assert response.status_code == 200
    assert response.json["results"] == []

# C. Authorization checks (often completely untested)
def test_regular_user_cannot_delete_others(client, regular_user_token):
    response = client.delete(
        "/api/users/1",
        headers={"Authorization": f"Bearer {regular_user_token}"}
    )
    assert response.status_code == 403

# D. Conditional branches
def test_coupon_percent_type():
    total = apply_coupon(100.0, {"type": "percent", "value": 20, "active": True})
    assert total == 80.0

def test_coupon_fixed_type():
    total = apply_coupon(100.0, {"type": "fixed", "value": 15, "active": True})
    assert total == 85.0

def test_expired_coupon_ignored():
    total = apply_coupon(100.0, {"type": "percent", "value": 20, "active": False})
    assert total == 100.0
```

Focus on the modules with the lowest coverage AND highest business impact first. Share your coverage report and I'll identify the highest-value tests to add.'''
    },
    {
        "instruction": r'''Our tests are flaky. Some pass, some fail randomly.''',
        "output": r'''<think>
Flaky tests are usually caused by: shared mutable state between tests, time-dependent assertions, external service dependencies, database state leaking between tests, race conditions in async tests, or test ordering dependencies. I don't know the test framework, what kind of tests are flaky, or the failure patterns. I need to understand the symptoms to diagnose the cause.
</think>

Flaky tests are frustrating and erode trust in the test suite. Let me ask:

1. **Which tests are flaky?** Unit tests, integration tests, or end-to-end? A handful or widespread?
2. **Do they fail more in CI than locally?** That usually points to timing issues or resource constraints.
3. **Do they fail together?** If test A fails, does test B also fail? That suggests shared state.

Here's a systematic approach to finding and fixing flaky tests:

```bash
# Step 1: Identify flaky tests by running the suite multiple times
# pytest-repeat plugin makes this easy:
pip install pytest-repeat

# Run the suspect test 50 times
pytest tests/test_orders.py::test_create_order --count=50 -x
# -x stops on first failure so you can see the error

# Step 2: Randomize test order to find state dependencies
pip install pytest-randomly
pytest --randomly-seed=12345  # run in random order, use seed to reproduce
```

```python
# Common flaky test patterns and fixes:

# PROBLEM 1: Tests share database state
# BAD: test A inserts a user, test B assumes the user table is empty
# FIX: Clean up after each test

@pytest.fixture(autouse=True)
def clean_db(db):
    yield
    db.session.rollback()
    # Or truncate tables between tests:
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()


# PROBLEM 2: Time-dependent assertions
# BAD: asserts on datetime.now() -- fails if test runs slowly
# FIX: Freeze time or use approximate comparisons

from freezegun import freeze_time

@freeze_time("2026-03-06 12:00:00")
def test_token_expiry():
    token = create_token(expires_in=3600)
    assert token.expires_at == datetime(2026, 3, 6, 13, 0, 0)

# Or use approximate comparison:
def test_created_at():
    before = datetime.utcnow()
    user = create_user("test@example.com")
    after = datetime.utcnow()
    assert before <= user.created_at <= after


# PROBLEM 3: External service dependency
# BAD: test calls a real API that sometimes times out
# FIX: Mock external calls

from unittest.mock import patch

def test_send_notification():
    with patch("app.email.send_email") as mock_send:
        mock_send.return_value = True
        result = notify_user(user_id=1, message="Hello")
        assert result is True
        mock_send.assert_called_once()


# PROBLEM 4: Async race conditions
# BAD: test checks result before async operation completes
# FIX: Await properly or use retry assertions

import asyncio

async def test_async_processing():
    await submit_job(job_id=1)
    # BAD: result might not be ready yet
    # result = get_job_result(1)

    # GOOD: poll with timeout
    for _ in range(10):
        result = get_job_result(1)
        if result is not None:
            break
        await asyncio.sleep(0.1)
    assert result is not None
```

Share a few examples of failing test output and I'll pinpoint the exact cause for each one.'''
    },
    {
        "instruction": r'''Make our tests faster. The test suite takes too long.''',
        "output": r'''<think>
"Tests are too slow" -- how long is too long? 5 minutes? 2 hours? What kind of tests -- is the whole suite slow or just certain tests? Are there database-heavy integration tests? Browser-based E2E tests? Tests that hit external APIs? Tests that sleep? I need to know the current duration, test count, and what's making them slow.
</think>

A few things I'd want to know:

1. **How long does the suite take?** And how many tests?
2. **What kind of tests are slowest?** Unit tests shouldn't take long -- if they do, something's wrong. Integration and E2E tests are naturally slower.
3. **Are tests hitting real databases/services?** That's usually the biggest time sink.

Here's a systematic approach to speeding up your test suite:

```bash
# Step 1: Find the slowest tests
pytest --durations=20  # shows the 20 slowest tests

# Typical output:
# 15.23s call tests/test_e2e_checkout.py::test_full_checkout
#  8.45s call tests/test_reports.py::test_generate_monthly_report
#  3.12s call tests/test_email.py::test_send_welcome_email
# The top few tests usually account for most of the time
```

```python
# Fix 1: Use in-memory database for unit tests (biggest win)
# Instead of PostgreSQL, use SQLite in-memory for tests that don't need PG features

# conftest.py
@pytest.fixture(scope="session")
def engine():
    # Tests run 10-50x faster with in-memory SQLite
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


# Fix 2: Share expensive setup across tests (scope="session" or "module")
@pytest.fixture(scope="session")
def seed_data(db):
    """Create reference data once, reuse across all tests."""
    db.add_all([
        Category(name="Electronics"),
        Category(name="Books"),
    ])
    db.commit()


# Fix 3: Mock slow external calls (network, email, file I/O)
@pytest.fixture(autouse=True)
def mock_external_services(monkeypatch):
    monkeypatch.setattr("app.email.send", lambda *a, **kw: True)
    monkeypatch.setattr("app.payment.charge", lambda *a, **kw: {"status": "ok"})


# Fix 4: Replace sleep-based waits with event-based
# BAD:
# time.sleep(5)  # wait for background job
# assert get_result() == expected

# GOOD:
# result = wait_for(lambda: get_result() is not None, timeout=5)
# assert result == expected
```

```bash
# Fix 5: Run tests in parallel
pip install pytest-xdist
pytest -n auto  # uses all CPU cores
# or: pytest -n 4  # use 4 workers

# Fix 6: Only run affected tests during development
pytest --lf          # re-run only last failures
pytest --ff          # run failures first, then the rest
pytest -k "order"    # run only tests matching "order"
```

```text
Speed optimization priority:
1. Mock external services (removes network waits)
2. Use in-memory DB for unit tests (removes disk I/O)
3. Run tests in parallel (pytest-xdist)
4. Scope expensive fixtures to session/module
5. Remove unnecessary sleep() calls
6. Split slow E2E tests into a separate CI stage
```

Run `pytest --durations=20` and share the output -- I'll tell you exactly where the time is going and how to fix it.'''
    },
    {
        "instruction": r'''We need integration tests for our system.''',
        "output": r'''<think>
"We need integration tests" -- for what parts of the system? API endpoints against a real database? Service-to-service communication? Third-party API integrations? The whole stack end-to-end? What's the system -- microservices, monolith, serverless? What tools/frameworks are they using? Integration tests need infrastructure setup (test databases, test containers) so the approach varies a lot.
</think>

Integration tests can mean different things. Let me clarify:

1. **What are you integrating?** API endpoints with a real database? Service-to-service calls? Third-party API interactions?
2. **What's the architecture?** Monolith, microservices, serverless?
3. **What test infrastructure do you have?** Docker available in CI? Separate test database?

Here's a practical integration test setup for the most common case -- testing API endpoints against a real database using Docker:

```python
# conftest.py -- integration test setup with a real PostgreSQL via Docker
import pytest
import docker
from sqlalchemy import create_engine
from your_app import create_app
from your_app.models import Base

@pytest.fixture(scope="session")
def postgres_container():
    """Spin up a real PostgreSQL for integration tests."""
    client = docker.from_env()
    container = client.containers.run(
        "postgres:15",
        environment={
            "POSTGRES_DB": "testdb",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
        },
        ports={"5432/tcp": 15432},
        detach=True,
    )
    # Wait for postgres to be ready
    import time
    time.sleep(3)
    yield container
    container.stop()
    container.remove()

@pytest.fixture(scope="session")
def db_engine(postgres_container):
    engine = create_engine("postgresql://test:test@localhost:15432/testdb")
    Base.metadata.create_all(engine)
    return engine

@pytest.fixture
def client(db_engine):
    app = create_app(database_url="postgresql://test:test@localhost:15432/testdb")
    with app.test_client() as client:
        yield client

# tests/integration/test_order_flow.py
class TestOrderIntegration:
    """Tests that exercise the full request -> service -> database -> response path."""

    def test_full_order_lifecycle(self, client):
        # 1. Create a customer
        resp = client.post("/api/customers", json={"name": "Alice", "email": "alice@test.com"})
        assert resp.status_code == 201
        customer_id = resp.json["id"]

        # 2. Create a product
        resp = client.post("/api/products", json={"name": "Widget", "price": 29.99})
        assert resp.status_code == 201
        product_id = resp.json["id"]

        # 3. Place an order
        resp = client.post("/api/orders", json={
            "customer_id": customer_id,
            "items": [{"product_id": product_id, "quantity": 3}],
        })
        assert resp.status_code == 201
        order_id = resp.json["order_id"]
        assert resp.json["total"] > 0

        # 4. Verify the order is retrievable
        resp = client.get(f"/api/orders/{order_id}")
        assert resp.status_code == 200
        assert resp.json["customer_id"] == customer_id
        assert len(resp.json["items"]) == 1

        # 5. Cancel the order
        resp = client.post(f"/api/orders/{order_id}/cancel")
        assert resp.status_code == 200
        assert resp.json["status"] == "cancelled"

    def test_order_with_invalid_product_fails(self, client):
        resp = client.post("/api/orders", json={
            "customer_id": 1,
            "items": [{"product_id": 99999, "quantity": 1}],
        })
        assert resp.status_code == 400
        assert "product" in resp.json["detail"].lower()
```

Tell me your stack and which integration points matter most, and I'll write the specific tests.'''
    },
]
