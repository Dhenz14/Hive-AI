r"""Thinking-trace pairs: test code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this test code and identify issues:

```python
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from app.services import UserService, EmailService
from app.models import User, db

class TestUserService(unittest.TestCase):
    def setUp(self):
        self.user_service = UserService()
        self.db = db
        self.db.create_all()
        user = User(
            username="testuser",
            email="test@example.com",
            password="password123",
            created_at=datetime(2024, 1, 1)
        )
        self.db.session.add(user)
        self.db.session.commit()

    def test_create_user(self):
        result = self.user_service.create_user(
            "newuser", "new@example.com", "pass123"
        )
        self.assertTrue(result)

    def test_create_duplicate_user(self):
        try:
            self.user_service.create_user(
                "testuser", "test@example.com", "pass123"
            )
        except:
            pass

    def test_get_user(self):
        user = self.user_service.get_user_by_email("test@example.com")
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.password, "password123")
        self.assertEqual(user.created_at, datetime(2024, 1, 1))

    def test_update_user(self):
        self.user_service.update_user(1, {"username": "updated"})
        user = self.user_service.get_user_by_id(1)
        assert user.username == "updated"

    def test_delete_user(self):
        self.user_service.delete_user(1)
        user = self.user_service.get_user_by_id(1)
        self.assertIsNone(user)

    def test_login(self):
        result = self.user_service.login("test@example.com", "password123")
        self.assertIsNotNone(result)

    @patch('app.services.EmailService')
    def test_send_welcome_email(self, mock_email):
        self.user_service.create_user(
            "emailuser", "email@example.com", "pass123"
        )
        mock_email.send.assert_called_once()

    def test_list_users(self):
        users = self.user_service.list_users()
        self.assertEqual(len(users), 1)

    def test_search_users(self):
        result = self.user_service.search_users("test")
        self.assertTrue(len(result) > 0)

    def test_everything(self):
        user = self.user_service.create_user("a", "a@b.com", "x")
        self.assertTrue(user)
        fetched = self.user_service.get_user_by_email("a@b.com")
        self.assertIsNotNone(fetched)
        self.user_service.update_user(fetched.id, {"username": "b"})
        updated = self.user_service.get_user_by_id(fetched.id)
        self.assertEqual(updated.username, "b")
        self.user_service.delete_user(fetched.id)
        deleted = self.user_service.get_user_by_id(fetched.id)
        self.assertIsNone(deleted)
```''', r'''<think>
Let me analyze this test code for testing best practices violations.

Test isolation:
- setUp uses a real database (db.create_all, session.add, commit). Tests are coupled to database state. No tearDown to clean up - each test leaves data behind, affecting subsequent tests.
- Tests depend on hardcoded IDs (get_user_by_id(1)) which assumes auto-increment starts at 1 and no other tests have inserted records.
- No database rollback between tests.

Test quality:
- test_create_duplicate_user has a bare except that catches everything and does nothing. The test passes whether the method raises an exception, returns None, or succeeds. It asserts nothing.
- test_create_user only checks assertTrue(result) - does not verify the user was actually created correctly with the right fields.
- test_get_user asserts on password field directly - implies password is stored in plaintext, and the test is verifying this bad behavior.
- test_update_user uses assert (pytest style) instead of self.assertEqual (unittest style) - mixing assertion styles.
- test_login is a thin check (assertIsNotNone) - does not verify the token/session, expiry, or any login side effects.

Mock issues:
- test_send_welcome_email patches EmailService at the class level but the mock may not be properly injected into UserService. The mock replaces the class but the assertion calls mock_email.send which may not be the instance method that was called.
- The mock is not configured with expected arguments - just asserts it was called once, not with what arguments.

Bad patterns:
- test_everything is a "god test" that tests create, read, update, and delete in a single test. If any step fails, you cannot tell which operation is broken. This should be separate tests.
- test_search_users uses assertTrue(len(result) > 0) which gives no useful error message on failure. Should use assertGreater.
- test_list_users depends on setUp having inserted exactly one user, and no other test having added users. This is fragile.
- No negative test cases (invalid email, empty password, nonexistent user).
- No edge case testing (very long username, special characters, SQL injection attempts).

Missing tearDown:
- Database is created in setUp but never torn down. Tests pollute each other.
</think>

## Code Review: User Service Test Suite

### CRITICAL - test_create_duplicate_user Asserts Nothing
This test catches all exceptions silently and has no assertions. It passes regardless of what happens - whether the method raises the correct exception, raises the wrong exception, or succeeds without error.

**Fix:**
```python
def test_create_duplicate_user(self):
    with self.assertRaises(DuplicateUserError):
        self.user_service.create_user(
            "testuser", "test@example.com", "pass123"
        )
```

### CRITICAL - No Test Isolation (Missing tearDown)
`setUp` creates database tables and inserts data, but there is no `tearDown` to clean up. Each test leaves its data behind, contaminating subsequent tests. Test execution order becomes significant, making tests brittle and non-deterministic.

**Fix:**
```python
def setUp(self):
    self.db.create_all()
    # ... setup code

def tearDown(self):
    self.db.session.rollback()
    self.db.drop_all()
```
Better yet, wrap each test in a transaction that rolls back automatically.

### HIGH - Tests Depend on Hardcoded Auto-Increment IDs
`test_update_user` and `test_delete_user` use `get_user_by_id(1)`, assuming the user created in setUp got ID 1. If tests run in a different order, or the database does not reset auto-increment counters, these tests fail.

**Fix:** Store the created user's ID in setUp:
```python
def setUp(self):
    # ...
    self.db.session.add(user)
    self.db.session.commit()
    self.test_user_id = user.id
```

### HIGH - test_get_user Asserts on Plaintext Password
`self.assertEqual(user.password, "password123")` implies passwords are stored in plaintext. This test codifies a security vulnerability as expected behavior. Even if the test is correct about current behavior, it should not validate plaintext password storage.

### HIGH - test_everything Is a God Test
This single test covers create, read, update, and delete operations. If the update step fails, you cannot tell whether the issue is in update_user or get_user_by_id. Each operation should be its own test case.

### MEDIUM - Mock Not Properly Connected
`@patch('app.services.EmailService')` replaces the class, but `mock_email.send.assert_called_once()` checks the class mock, not the instance. The actual code probably calls `EmailService().send(...)`, meaning the instance method call is on `mock_email.return_value.send`, not `mock_email.send`.

**Fix:**
```python
mock_email.return_value.send.assert_called_once_with(
    "email@example.com", subject="Welcome!"
)
```

### MEDIUM - Mixing Assertion Styles
`test_update_user` uses bare `assert` while other tests use `self.assertEqual`. Bare assert provides no useful message on failure and is inconsistent with the unittest framework.

### MEDIUM - Weak Assertions
`assertTrue(result)` in test_create_user only checks truthiness. It does not verify the created user has the correct username, email, or hashed password. `assertTrue(len(result) > 0)` in test_search_users gives an unhelpful "False is not true" error message.

### LOW - No Negative or Edge Case Tests
No tests for: invalid email format, empty password, nonexistent user lookup, unauthorized access, SQL injection strings, or Unicode usernames.'''),

    ("thinking/code-review", r'''Review this test code with fixtures and mocks:

```python
import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.payment import PaymentProcessor, PaymentGateway
from app.models import Order, PaymentResult

@pytest.fixture
def payment_processor():
    gateway = Mock(spec=PaymentGateway)
    gateway.charge.return_value = {"status": "success", "transaction_id": "tx_123"}
    gateway.refund.return_value = {"status": "success"}
    processor = PaymentProcessor(gateway=gateway)
    return processor

@pytest.fixture
def sample_order():
    return Order(
        id=1,
        user_id=42,
        total=99.99,
        currency="USD",
        items=[
            {"product_id": 1, "quantity": 2, "price": 29.99},
            {"product_id": 2, "quantity": 1, "price": 40.01}
        ]
    )

class TestPaymentProcessor:
    def test_process_payment(self, payment_processor, sample_order):
        result = payment_processor.process_payment(sample_order)
        assert result.success == True
        assert result.transaction_id == "tx_123"

    def test_process_payment_declined(self, payment_processor, sample_order):
        payment_processor.gateway.charge.return_value = {
            "status": "declined",
            "error": "Insufficient funds"
        }
        result = payment_processor.process_payment(sample_order)
        assert result.success == False

    def test_process_payment_gateway_error(self, payment_processor, sample_order):
        payment_processor.gateway.charge.side_effect = Exception("Connection timeout")
        result = payment_processor.process_payment(sample_order)
        assert result.success == False

    def test_refund(self, payment_processor):
        result = payment_processor.refund("tx_123", 50.00)
        assert result.success == True

    def test_refund_more_than_original(self, payment_processor):
        result = payment_processor.refund("tx_123", 1000000.00)

    def test_process_zero_amount(self, payment_processor):
        order = Order(id=2, user_id=42, total=0, currency="USD", items=[])
        result = payment_processor.process_payment(order)

    def test_process_negative_amount(self, payment_processor):
        order = Order(id=3, user_id=42, total=-50, currency="USD", items=[])
        result = payment_processor.process_payment(order)

    def test_currency_conversion(self, payment_processor, sample_order):
        sample_order.currency = "EUR"
        result = payment_processor.process_payment(sample_order)
        assert result.success == True
        payment_processor.gateway.charge.assert_called_once()

    def test_idempotency(self, payment_processor, sample_order):
        result1 = payment_processor.process_payment(sample_order)
        result2 = payment_processor.process_payment(sample_order)
        assert result1.transaction_id == result2.transaction_id

    @patch('app.payment.logger')
    def test_logging(self, mock_logger, payment_processor, sample_order):
        payment_processor.process_payment(sample_order)
        mock_logger.info.assert_called()

    def test_concurrent_payments(self, payment_processor):
        import threading
        results = []
        def process():
            order = Order(id=1, user_id=42, total=10, currency="USD", items=[])
            result = payment_processor.process_payment(order)
            results.append(result)

        threads = [threading.Thread(target=process) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 10
```''', r'''<think>
Let me analyze this test code for testing quality issues.

Missing assertions:
- test_refund_more_than_original: No assertion at all. The test calls the method but never checks the result. Should verify that an over-refund is either rejected or handled appropriately.
- test_process_zero_amount: No assertion. Should verify zero-amount orders are rejected.
- test_process_negative_amount: No assertion. Should verify negative amounts are rejected.

Mock issues:
- The gateway mock always returns success by default. Tests that should verify error handling (like zero/negative amounts) will incorrectly pass because the mock happily accepts any input.
- test_idempotency: The gateway mock returns the same transaction_id for every call, so the test always passes. It does not actually test idempotency - it tests that the mock returns the same value twice. Real idempotency testing needs to verify the gateway is NOT called twice for the same order.
- test_currency_conversion: Asserts success but doesn't verify the currency was actually converted or that the correct amount was charged. The mock doesn't care about currency.

Fixture design:
- payment_processor fixture mutates the gateway mock's return value inside tests (test_process_payment_declined). This is fine for individual tests but can be confusing. The fixture could provide a factory instead.
- sample_order has hardcoded item prices that sum to 99.99 (29.99*2 + 40.01 = 99.99). This is coincidentally correct but the relationship between items and total is not validated.

Concurrency test:
- test_concurrent_payments uses a mock gateway, so it's not actually testing concurrency issues (race conditions, double-charging). The mock is thread-safe by default. This test only verifies that threading.Thread works.
- Appending to a list from multiple threads is actually not thread-safe in general (though CPython's GIL makes it safe in practice).

Comparison issues:
- assert result.success == True should be assert result.success is True or just assert result.success
- assert result.success == False should be assert result.success is False or assert not result.success

Test naming:
- test_logging is testing implementation detail (that logger.info was called) rather than behavior. If the logging format changes, the test breaks without any functional regression.

Missing tests:
- No test for partial refunds
- No test for network timeout handling
- No test for invalid payment method
- No test for webhook/callback handling
- No test for retry behavior
</think>

## Code Review: Payment Processor Test Suite

### CRITICAL - Three Tests Have No Assertions
`test_refund_more_than_original`, `test_process_zero_amount`, and `test_process_negative_amount` call methods but never assert anything. These tests always pass, giving false confidence. They are particularly dangerous because they cover critical edge cases (over-refund, zero/negative charges) that a payment system must handle correctly.

**Fix:**
```python
def test_refund_more_than_original(self, payment_processor):
    with pytest.raises(RefundExceedsOriginalError):
        payment_processor.refund("tx_123", 1000000.00)

def test_process_zero_amount(self, payment_processor):
    order = Order(id=2, user_id=42, total=0, currency="USD", items=[])
    with pytest.raises(InvalidAmountError):
        payment_processor.process_payment(order)

def test_process_negative_amount(self, payment_processor):
    order = Order(id=3, user_id=42, total=-50, currency="USD", items=[])
    with pytest.raises(InvalidAmountError):
        payment_processor.process_payment(order)
```

### HIGH - test_idempotency Tests the Mock, Not the Code
The gateway mock returns `{"transaction_id": "tx_123"}` for every call regardless of input. The test asserts both results have the same transaction_id, which is trivially true because the mock always returns the same value. This does not test idempotency at all.

**Fix:** Verify the gateway is called only once for duplicate requests:
```python
def test_idempotency(self, payment_processor, sample_order):
    result1 = payment_processor.process_payment(sample_order)
    result2 = payment_processor.process_payment(sample_order)
    assert result1.transaction_id == result2.transaction_id
    # The key assertion: gateway should only be called once
    payment_processor.gateway.charge.assert_called_once()
```

### HIGH - test_concurrent_payments Does Not Test Concurrency
The test uses a mock gateway, which is inherently thread-safe and stateless. Running 10 threads against a mock only tests that Python threads work, not that the PaymentProcessor handles concurrent access correctly. Real concurrency testing requires a stateful gateway mock that can detect race conditions.

### MEDIUM - test_currency_conversion Asserts Nothing Meaningful
The test sets currency to "EUR" and asserts success, but the mock gateway ignores currency entirely. The test does not verify that currency conversion occurred, that the correct converted amount was charged, or that the exchange rate was applied.

**Fix:**
```python
def test_currency_conversion(self, payment_processor, sample_order):
    sample_order.currency = "EUR"
    result = payment_processor.process_payment(sample_order)
    assert result.success
    call_args = payment_processor.gateway.charge.call_args
    assert call_args[1]["currency"] == "EUR"
    # Or verify converted amount if conversion happens before gateway call
```

### MEDIUM - Boolean Comparison Style
`assert result.success == True` and `== False` should use `is True`/`is False` or idiomatic `assert result.success` / `assert not result.success`. The `==` form can pass for truthy/falsy values that are not actually boolean.

### MEDIUM - test_logging Tests Implementation Details
Asserting that `logger.info` was called is a brittle test that breaks when log messages change but no functional behavior has regressed. Test observable behavior (return values, side effects) rather than internal implementation details.

### LOW - Fixture Could Use Factory Pattern
Tests that need to modify the gateway mock (like test_process_payment_declined) mutate the shared fixture. A factory fixture would be cleaner:
```python
@pytest.fixture
def make_processor():
    def _make(charge_result=None):
        gateway = Mock(spec=PaymentGateway)
        gateway.charge.return_value = charge_result or {"status": "success", "transaction_id": "tx_123"}
        return PaymentProcessor(gateway=gateway)
    return _make
```'''),

    ("thinking/code-review", r'''Review this integration test setup and identify issues:

```python
import pytest
import requests
import psycopg2
import time
import os
import subprocess

BASE_URL = "http://localhost:8000"
DB_URL = "postgresql://test:test@localhost:5432/testdb"

@pytest.fixture(scope="session")
def app_server():
    proc = subprocess.Popen(
        ["python", "manage.py", "runserver", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(5)  # Wait for server to start
    yield proc
    proc.kill()

@pytest.fixture(scope="session")
def db_connection():
    conn = psycopg2.connect(DB_URL)
    yield conn
    conn.close()

@pytest.fixture
def clean_db(db_connection):
    cursor = db_connection.cursor()
    cursor.execute("DELETE FROM order_items")
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM users")
    db_connection.commit()

@pytest.fixture
def test_user(clean_db):
    response = requests.post(f"{BASE_URL}/api/users", json={
        "username": "testuser",
        "email": "test@test.com",
        "password": "test123"
    })
    return response.json()

@pytest.fixture
def auth_token(test_user):
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "test@test.com",
        "password": "test123"
    })
    return response.json()["token"]

class TestOrderAPI:
    def test_create_order(self, auth_token, test_user):
        response = requests.post(
            f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"items": [{"product_id": 1, "quantity": 2}]}
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"

    def test_get_order(self, auth_token):
        response = requests.get(
            f"{BASE_URL}/api/orders/1",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200

    def test_list_orders(self, auth_token):
        response = requests.get(
            f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_cancel_order(self, auth_token):
        response = requests.post(
            f"{BASE_URL}/api/orders/1/cancel",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200

    def test_unauthorized_access(self):
        response = requests.get(f"{BASE_URL}/api/orders")
        assert response.status_code == 401

    def test_create_order_validation(self, auth_token):
        response = requests.post(
            f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"items": []}
        )
        assert response.status_code == 400

    def test_order_flow(self, auth_token):
        # Create
        r1 = requests.post(f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"items": [{"product_id": 1, "quantity": 1}]})
        order_id = r1.json()["id"]

        # Pay
        r2 = requests.post(f"{BASE_URL}/api/orders/{order_id}/pay",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"payment_method": "card", "card_token": "tok_test"})
        assert r2.status_code == 200

        # Ship
        r3 = requests.post(f"{BASE_URL}/api/orders/{order_id}/ship",
            headers={"Authorization": f"Bearer {auth_token}"})
        assert r3.status_code == 200
```''', r'''<think>
Let me analyze this integration test setup for reliability, isolation, and design issues.

Server startup:
- time.sleep(5) to wait for server startup is fragile. The server may not be ready in 5 seconds (especially if running migrations), or it may be ready in 1 second (wasting 4 seconds).
- No health check to verify the server is actually accepting connections.
- Using Django's runserver in tests - this is the dev server, not representative of production.
- subprocess.Popen captures stdout/stderr but never reads them. If the output buffer fills up, the process will block.

Database issues:
- DB_URL with credentials hardcoded in the test file.
- clean_db deletes from tables in a specific order to avoid FK violations, but this is fragile. If new tables with foreign keys are added, this fixture breaks silently (leaves dirty data).
- clean_db uses DELETE (not TRUNCATE) which is slower and does not reset sequences/auto-increment.
- session-scoped db_connection means one connection is shared across all tests - no isolation.

Test ordering dependencies:
- test_get_order uses hardcoded order ID 1, assuming test_create_order ran first and created an order with ID 1. Tests should be independent.
- test_cancel_order also uses hardcoded order ID 1 - same problem.
- test_list_orders depends on data created by previous tests.
- If test_create_order fails, test_get_order and test_cancel_order will fail for the wrong reason.

Fixture chain:
- auth_token depends on test_user depends on clean_db depends on db_connection.
- But auth_token has function scope while db_connection has session scope. If clean_db runs for one test, it wipes data that other tests depend on.
- The fixture chain creates side effects through HTTP calls (creating user via API, logging in via API) - if the API is down, all tests fail with confusing connection errors.

Missing:
- No timeout on requests calls - a hung server blocks tests forever.
- No cleanup of created orders (only users, order_items, and orders are cleaned).
- No parallel test safety (tests share the same database and server).
- No response body validation beyond status codes in several tests.
- test_order_flow does not verify the final state of the order.
- No error message validation on 400/401 responses.
- Product with id=1 is assumed to exist but never created in fixtures.
</think>

## Code Review: Integration Test Setup

### CRITICAL - Tests Depend on Execution Order
`test_get_order` and `test_cancel_order` use hardcoded order ID 1, assuming `test_create_order` ran first. pytest does not guarantee test execution order. If tests run in a different order or in parallel, these tests fail for the wrong reason.

**Fix:** Each test should create its own data:
```python
def test_get_order(self, auth_token):
    # Create the order first
    create_resp = requests.post(
        f"{BASE_URL}/api/orders",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"items": [{"product_id": 1, "quantity": 1}]}
    )
    order_id = create_resp.json()["id"]

    response = requests.get(
        f"{BASE_URL}/api/orders/{order_id}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
```

### CRITICAL - Sleep-Based Server Startup
`time.sleep(5)` is unreliable. The server may not be ready (e.g., running migrations takes longer) or the sleep wastes time if it starts quickly. No verification that the server is actually accepting connections.

**Fix:** Poll the health endpoint:
```python
@pytest.fixture(scope="session")
def app_server():
    proc = subprocess.Popen(...)
    for _ in range(30):
        try:
            requests.get(f"{BASE_URL}/health", timeout=1)
            break
        except requests.ConnectionError:
            time.sleep(1)
    else:
        proc.kill()
        raise RuntimeError("Server failed to start")
    yield proc
    proc.kill()
```

### HIGH - Incomplete Database Cleanup
`clean_db` deletes from three tables in a hardcoded order. If the schema adds new tables with foreign key references, the fixture silently leaves dirty data. Using DELETE instead of TRUNCATE is also slower and does not reset auto-increment counters.

**Fix:**
```python
@pytest.fixture
def clean_db(db_connection):
    cursor = db_connection.cursor()
    cursor.execute(
        "TRUNCATE TABLE order_items, orders, users RESTART IDENTITY CASCADE"
    )
    db_connection.commit()
```

### HIGH - Product Fixture Missing
Tests create orders referencing `product_id: 1`, but no fixture creates this product. If the test database is clean, the order creation will fail with a foreign key violation or a "product not found" error. The test failure message will be misleading.

### HIGH - No Request Timeouts
All `requests.post()` and `requests.get()` calls have no timeout parameter. If the server hangs, the test suite blocks indefinitely.

**Fix:** Add timeout to every request or create a helper:
```python
def api_get(self, path, **kwargs):
    kwargs.setdefault("timeout", 10)
    return requests.get(f"{BASE_URL}{path}", **kwargs)
```

### MEDIUM - Subprocess Output Buffer Deadlock
`subprocess.Popen` captures stdout and stderr but never reads from them. If the server produces enough output to fill the OS pipe buffer (typically 64KB), the process will block on write and the tests will hang.

**Fix:** Redirect to DEVNULL or to a file:
```python
proc = subprocess.Popen(
    ["python", "manage.py", "runserver", "8000"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)
```

### MEDIUM - Hardcoded Credentials and URLs
`BASE_URL` and `DB_URL` are hardcoded. Tests cannot run against different environments or in CI where ports may differ.

**Fix:** Read from environment variables with defaults:
```python
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
DB_URL = os.environ.get("TEST_DB_URL", "postgresql://test:test@localhost:5432/testdb")
```

### LOW - test_order_flow Does Not Verify Final State
The flow test creates, pays, and ships an order, but never checks the final order state. After shipping, it should verify the order status is "shipped" and the payment is recorded.'''),

    ("thinking/code-review", r'''Review this test helper and assertion utilities:

```python
import json
import time
import random
import string
from functools import wraps
from unittest.mock import MagicMock

def retry_test(max_retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except AssertionError:
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator

def random_email():
    chars = string.ascii_lowercase + string.digits
    username = ''.join(random.choice(chars) for _ in range(10))
    return f"{username}@test.com"

def random_user():
    return {
        "username": ''.join(random.choice(string.ascii_lowercase) for _ in range(8)),
        "email": random_email(),
        "password": "password123",
        "age": random.randint(1, 100)
    }

class APITestMixin:
    base_url = "http://localhost:8000/api"

    def get(self, path, **kwargs):
        import requests
        return requests.get(f"{self.base_url}{path}", **kwargs)

    def post(self, path, data=None, **kwargs):
        import requests
        return requests.post(f"{self.base_url}{path}", json=data, **kwargs)

    def assert_status(self, response, expected):
        assert response.status_code == expected, \
            f"Expected {expected}, got {response.status_code}: {response.text}"

    def assert_json_contains(self, response, key, value=None):
        data = response.json()
        assert key in data, f"Key '{key}' not found in response: {data}"
        if value is not None:
            assert data[key] == value

    def assert_list_length(self, response, expected_length):
        data = response.json()
        assert len(data) == expected_length

    def assert_created(self, response):
        self.assert_status(response, 201)
        data = response.json()
        assert "id" in data
        return data["id"]

    def assert_error(self, response, status_code, message=None):
        self.assert_status(response, status_code)
        if message:
            data = response.json()
            assert message in str(data)

def create_mock_service(**overrides):
    service = MagicMock()
    for method_name, return_value in overrides.items():
        getattr(service, method_name).return_value = return_value
    return service

def load_fixture(filename):
    with open(f"tests/fixtures/{filename}") as f:
        return json.load(f)

def wait_for_condition(condition_fn, timeout=10, interval=0.5):
    start = time.time()
    while time.time() - start < timeout:
        if condition_fn():
            return True
        time.sleep(interval)
    return False

class DatabaseSeeder:
    def __init__(self, db):
        self.db = db

    def seed_users(self, count=10):
        users = []
        for _ in range(count):
            user = random_user()
            self.db.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (user["username"], user["email"], user["password"])
            )
            users.append(user)
        self.db.commit()
        return users

    def seed_products(self, count=10):
        products = []
        for i in range(count):
            product = {
                "name": f"Product {i}",
                "price": round(random.uniform(1, 100), 2),
                "stock": random.randint(0, 1000)
            }
            self.db.execute(
                "INSERT INTO products (name, price, stock) VALUES (%s, %s, %s)",
                (product["name"], product["price"], product["stock"])
            )
            products.append(product)
        self.db.commit()
        return products
```''', r'''<think>
Let me analyze these test helper utilities for design issues, correctness, and potential problems.

retry_test decorator:
- Retrying flaky tests hides real failures. If a test sometimes fails, the underlying code has a bug or the test has a race condition. Retrying papers over these issues.
- Only catches AssertionError - other exceptions (ConnectionError, TimeoutError) will fail immediately even though they are more likely to be transient.
- time.sleep in tests slows down the suite.
- No logging of retries - failures are invisible.

random_email / random_user:
- random.choice is not seeded, so tests are non-deterministic. A test might pass locally but fail in CI (or vice versa) because different random data triggers different code paths.
- random_user always uses "password123" - not actually random for the password field. Tests cannot catch password validation issues.
- random_user includes age with random.randint(1, 100) - includes edge cases (age=1) randomly, meaning edge case testing is probabilistic, not guaranteed.

APITestMixin:
- Imports requests inside methods - this is a pattern used to avoid import errors, but it means the import happens on every call. Should be a module-level import.
- No timeout on requests calls.
- base_url is hardcoded as class variable.
- assert_error checks message with `assert message in str(data)` - this is a string containment check on the string representation of the entire response dict. It could match field names, not just values.
- assert_list_length does not handle non-list responses (will throw TypeError instead of a clear assertion error).

wait_for_condition:
- Returns False on timeout instead of raising an exception. Callers might forget to check the return value, making the test pass even though the condition was never met.
- Should raise TimeoutError on failure.

DatabaseSeeder:
- seed_users stores plaintext passwords in the database. If the application expects hashed passwords, these seeded users cannot log in.
- seed_products uses random prices - tests using these products will have non-deterministic totals.
- No return of database-generated IDs (auto-increment). The returned dicts lack the id field, making them less useful for subsequent test steps.
- Direct SQL execution bypasses application validation logic. Seeded data might violate business rules.
- self.db.execute suggests a raw connection, not an ORM. Cursor management unclear.

create_mock_service:
- Uses MagicMock without spec, so any attribute access returns a mock without raising AttributeError. Tests cannot catch typos in method names.

load_fixture:
- Relative path "tests/fixtures/" assumes the working directory is the project root. Will fail if tests are run from a subdirectory.
</think>

## Code Review: Test Helper and Assertion Utilities

### HIGH - retry_test Masks Real Test Failures
The retry decorator hides flaky tests instead of fixing them. A test that fails intermittently indicates a race condition, timing dependency, or non-deterministic behavior in the code under test. Retrying 3 times with delays makes the test suite slower and gives false confidence.

**Additional issue:** Only `AssertionError` is caught. Transient errors like `ConnectionError` or `TimeoutError` (which are the most legitimate reasons to retry) are not retried.

**Fix:** Remove the retry decorator. Fix the underlying flakiness. If retries are truly needed for integration tests, log each retry:
```python
except (AssertionError, ConnectionError) as e:
    logger.warning(f"Test retry {attempt + 1}/{max_retries}: {e}")
```

### HIGH - Non-Deterministic Random Data
`random_email()` and `random_user()` use unseeded `random.choice`, making tests non-reproducible. A test might pass locally but fail in CI because different random data triggers different validation paths.

**Fix:** Use a fixed seed or deterministic factories:
```python
class UserFactory:
    _counter = 0

    @classmethod
    def create(cls):
        cls._counter += 1
        return {
            "username": f"testuser_{cls._counter}",
            "email": f"testuser_{cls._counter}@test.com",
            "password": "ValidP@ssw0rd!",
            "age": 25
        }
```

### HIGH - wait_for_condition Returns False Instead of Raising
When the condition is never met, `wait_for_condition` silently returns `False`. If a caller forgets to check the return value (which is easy to do), the test continues with a false positive.

**Fix:**
```python
def wait_for_condition(condition_fn, timeout=10, interval=0.5):
    start = time.time()
    while time.time() - start < timeout:
        if condition_fn():
            return True
        time.sleep(interval)
    raise TimeoutError(
        f"Condition not met within {timeout}s"
    )
```

### HIGH - DatabaseSeeder Stores Plaintext Passwords
`seed_users` inserts "password123" directly into the database without hashing. If the application expects bcrypt/argon2 hashed passwords, seeded users cannot authenticate. This creates a divergence between test data and real application behavior.

**Fix:** Use the application's password hashing function:
```python
from app.auth import hash_password

def seed_users(self, count=10):
    for _ in range(count):
        user = random_user()
        hashed = hash_password(user["password"])
        self.db.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (user["username"], user["email"], hashed)
        )
```

### MEDIUM - No Request Timeouts in APITestMixin
`get()` and `post()` methods do not set a timeout. A hung server blocks the entire test suite indefinitely.

**Fix:**
```python
def get(self, path, timeout=10, **kwargs):
    import requests
    return requests.get(f"{self.base_url}{path}", timeout=timeout, **kwargs)
```

### MEDIUM - create_mock_service Has No Spec
`MagicMock()` without `spec` accepts any attribute access. Tests using this helper cannot detect typos in method names - `service.proccess_payment()` (note typo) returns a mock instead of raising `AttributeError`.

**Fix:**
```python
def create_mock_service(spec_class, **overrides):
    service = MagicMock(spec=spec_class)
    for method_name, return_value in overrides.items():
        getattr(service, method_name).return_value = return_value
    return service
```

### MEDIUM - load_fixture Uses Relative Path
`"tests/fixtures/{filename}"` assumes the current working directory is the project root. Tests run from a subdirectory or by an IDE with a different CWD will fail with FileNotFoundError.

**Fix:**
```python
def load_fixture(filename):
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    with open(os.path.join(fixtures_dir, filename)) as f:
        return json.load(f)
```

### LOW - DatabaseSeeder Does Not Return IDs
Seeded records lack database-generated IDs, making them difficult to reference in subsequent test steps. Return the inserted IDs by using RETURNING clauses or cursor.lastrowid.'''),

    ("thinking/code-review", r'''Review this test configuration and conftest:

```python
# conftest.py
import pytest
import os
import sys
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.models import Base

TEST_DB = "sqlite:///test.db"

@pytest.fixture(scope="session")
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = TEST_DB
    app.config["SECRET_KEY"] = "test-secret"
    app.config["DEBUG"] = True
    return app

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DB)
    Base.metadata.create_all(engine)
    yield engine
    os.remove("test.db")

@pytest.fixture(scope="session")
def Session(engine):
    return sessionmaker(bind=engine)

@pytest.fixture
def session(Session):
    session = Session()
    yield session
    session.close()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/register", json={
        "username": "testadmin",
        "email": "admin@test.com",
        "password": "admin123"
    })
    login_response = client.post("/api/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123"
    })
    token = login_response.json["token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def sample_data(session):
    from app.models import User, Product, Category

    cat = Category(name="Electronics")
    session.add(cat)
    session.flush()

    for i in range(50):
        product = Product(
            name=f"Product {i}",
            price=i * 10.0 + 0.99,
            category_id=cat.id,
            stock=100
        )
        session.add(product)

    user = User(
        username="datauser",
        email="data@test.com",
        password="hashed_password"
    )
    session.add(user)
    session.commit()

    return {"category": cat, "user": user}

logging.basicConfig(level=logging.DEBUG)

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks integration tests")

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-slow", default=False):
        skip_slow = pytest.mark.skip(reason="need --run-slow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
```''', r'''<think>
Let me analyze this conftest.py for test configuration issues.

Database setup:
- TEST_DB = "sqlite:///test.db" uses SQLite for testing while the app likely uses PostgreSQL in production. SQLite has different behavior for: constraints, concurrent access, JSON fields, date handling, and many SQL features. Tests will pass on SQLite but fail on PostgreSQL.
- The file path "sqlite:///test.db" is relative and will be created wherever pytest is run from. Multiple concurrent test runs will conflict on the same file.
- os.remove("test.db") in the engine fixture teardown will fail if any other fixture or test still has the database open.

Session management:
- session fixture creates a session and closes it but does NOT rollback. Data created by tests persists across tests. Each test pollutes the database for subsequent tests.
- Session is session-scoped (sessionmaker), but individual sessions are function-scoped. However, since the database is file-based and session-scoped (create_all once), there is no isolation.

App configuration:
- app fixture is session-scoped but sets SQLALCHEMY_DATABASE_URI to TEST_DB. If the app was already configured during import, this override may not take effect.
- DEBUG = True in tests may expose different behavior than production (different error handling, etc.).
- SECRET_KEY = "test-secret" is fine for tests.

auth_headers fixture:
- Function-scoped but creates a user via API every time it is used. If clean_db is not run between tests, the second test using auth_headers will fail because "admin@test.com" already exists.
- Uses weak password "admin123".
- Depends on the registration and login endpoints working correctly. If those endpoints have bugs, all authenticated tests fail with confusing errors.

sample_data fixture:
- Creates 50 products - this is a lot for unit tests and will slow them down.
- Commits to the database but never cleans up. Since session fixture does not rollback, this data persists.
- The password "hashed_password" is stored directly - not actually hashed.

sys.path manipulation:
- sys.path.insert(0, ...) is a hack to make imports work. Should use proper package installation (pip install -e .) or configure pytest paths in pyproject.toml.

Logging:
- logging.basicConfig(level=logging.DEBUG) at module level means DEBUG logging is always enabled, even in CI where it creates excessive output.

pytest_collection_modifyitems:
- Uses config.getoption("--run-slow") but never registers this option with addoption. This will raise an error.
</think>

## Code Review: Test Configuration (conftest.py)

### CRITICAL - SQLite for Tests vs PostgreSQL in Production
`TEST_DB = "sqlite:///test.db"` uses SQLite while the application almost certainly uses PostgreSQL. SQLite has fundamentally different behavior: no ENUM types, different constraint enforcement, no concurrent writes, different JSON handling, and missing many PostgreSQL functions. Tests that pass on SQLite will fail on PostgreSQL.

**Fix:** Use PostgreSQL for tests:
```python
TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://test:test@localhost:5432/testdb"
)
```
Or use testcontainers to spin up a PostgreSQL container.

### CRITICAL - No Transaction Rollback Between Tests
The `session` fixture closes the session but never rolls back. Data created by one test persists and affects subsequent tests. Combined with the session-scoped engine and database, this means tests are not isolated.

**Fix:**
```python
@pytest.fixture
def session(Session):
    session = Session()
    session.begin_nested()  # Start a savepoint
    yield session
    session.rollback()  # Roll back to savepoint
    session.close()
```

### HIGH - auth_headers Creates Duplicate Users
`auth_headers` is function-scoped and registers "admin@test.com" via the API on every invocation. Without database cleanup between tests, the second test using this fixture will get a duplicate email error from the registration endpoint.

**Fix:** Either make auth_headers session-scoped or ensure database cleanup happens before user creation:
```python
@pytest.fixture
def auth_headers(client, clean_db):
    # clean_db runs first
    response = client.post("/api/auth/register", json={...})
```

### HIGH - Unregistered CLI Option
`pytest_collection_modifyitems` calls `config.getoption("--run-slow")` but this option is never registered with `pytest_addoption`. This will raise a `ValueError: no option named '--run-slow'`.

**Fix:**
```python
def pytest_addoption(parser):
    parser.addoption(
        "--run-slow", action="store_true", default=False,
        help="run slow tests"
    )
```

### HIGH - Relative Database File Path
`"sqlite:///test.db"` creates the database file in whichever directory pytest is invoked from. Running tests from different directories creates the file in different locations. Multiple concurrent test runs (e.g., in CI) will conflict on the same file.

**Fix:** Use an in-memory database or a tempfile:
```python
import tempfile
TEST_DB = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
```

### MEDIUM - sys.path Manipulation
`sys.path.insert(0, ...)` is a fragile hack. It breaks when the project structure changes and can cause subtle import ordering issues.

**Fix:** Install the package in development mode: `pip install -e .` and configure pytest in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

### MEDIUM - sample_data Creates Excessive Records
50 products for every test that uses this fixture is excessive for unit tests. Most tests need 1-3 records. This slows down test execution and makes debugging harder.

### MEDIUM - DEBUG Mode Enabled
`app.config["DEBUG"] = True` causes different error handling behavior than production. Exceptions that would return 500 in production display detailed tracebacks in test mode, potentially hiding error handling bugs.

### LOW - Module-Level DEBUG Logging
`logging.basicConfig(level=logging.DEBUG)` at module level floods test output with debug messages. Use WARNING level by default and allow override via environment variable.'''),
]
