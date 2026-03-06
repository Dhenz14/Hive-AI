"""Thinking-trace pairs: testing from devs who don't test enough."""

PAIRS = [
    (
        "thinking/practical",
        r'''I know I should write tests but I don't know where to start with this codebase

class OrderService:
    def __init__(self, db, payment_gateway, inventory_service, email_service, logger):
        self.db = db
        self.payment_gateway = payment_gateway
        self.inventory = inventory_service
        self.email = email_service
        self.logger = logger

    def place_order(self, user_id, items, payment_info):
        # validate items
        for item in items:
            stock = self.inventory.check_stock(item['product_id'])
            if stock < item['quantity']:
                raise InsufficientStockError(item['product_id'], stock, item['quantity'])

        # calculate total
        total = sum(item['price'] * item['quantity'] for item in items)
        if total <= 0:
            raise ValueError("Order total must be positive")

        # apply discount
        user = self.db.get_user(user_id)
        if user.is_premium:
            total *= 0.9  # 10% discount

        # charge payment
        charge = self.payment_gateway.charge(payment_info, total)
        if not charge.success:
            raise PaymentFailedError(charge.error_message)

        # create order record
        order = self.db.create_order(user_id=user_id, items=items, total=total, charge_id=charge.id)

        # reserve inventory
        for item in items:
            self.inventory.reserve(item['product_id'], item['quantity'])

        # send confirmation email
        try:
            self.email.send_order_confirmation(user.email, order)
        except Exception as e:
            self.logger.warning(f"Failed to send confirmation email: {e}")

        return order''',
        r'''<think>
The user has a complex service class with 5 dependencies and a multi-step place_order method. They are overwhelmed and do not know where to start testing. That is actually a very common feeling -- the codebase feels too big and interconnected to test.

My first instinct was to suggest testing every method individually, but wait -- that would produce dozens of tests that mostly verify mock wiring. Instead, I should focus on what actually matters.

The key insight is: you do not need 100% coverage on day one. Start with the tests that protect against the most damaging bugs. Let me think about what could go wrong with this specific code:
- Payment charged but order not created (money taken, no product) -- this is the worst case
- Order created but payment not charged (product given, no money)
- Stock validation bypassed (overselling)
- Premium discount applied incorrectly (revenue loss)

Hmm, I also notice the code has a subtle issue: if inventory.reserve() fails after payment is charged, the payment is not refunded. That is a real bug I should highlight in the tests.

I initially considered using integration tests with a real database, but actually that is not the right starting point for someone who has zero tests. Mocked unit tests are faster to write, faster to run, and the service already has good dependency injection (constructor injection), which makes testing straightforward. They can add integration tests later once they have the basics.

Let me write tests in priority order, starting with the most critical business logic. The tests should read like documentation of the business rules, not like a mirror of the implementation.
</think>

You do not need to test everything at once. Start with the tests that protect against the most expensive bugs. Here is a prioritized approach for your OrderService.

**Priority 1: The happy path (does the basic flow work?)**

```python
# tests/test_order_service.py
import pytest
from unittest.mock import Mock, patch, call
from decimal import Decimal
from orders.service import OrderService, InsufficientStockError, PaymentFailedError


@pytest.fixture
def mock_deps():
    """Create mock dependencies. Each test gets fresh mocks."""
    return {
        "db": Mock(),
        "payment_gateway": Mock(),
        "inventory_service": Mock(),
        "email_service": Mock(),
        "logger": Mock(),
    }


@pytest.fixture
def service(mock_deps):
    return OrderService(**mock_deps)


@pytest.fixture
def sample_items():
    return [
        {"product_id": "WIDGET-1", "quantity": 2, "price": 25.00},
        {"product_id": "GADGET-3", "quantity": 1, "price": 50.00},
    ]


@pytest.fixture
def sample_payment():
    return {"card_token": "tok_test_123", "billing_zip": "90210"}


class TestPlaceOrderHappyPath:
    """The most important tests: does the core flow work correctly?"""

    def test_successful_order_returns_order_object(
        self, service, mock_deps, sample_items, sample_payment
    ):
        # Arrange: set up mocks to simulate a successful flow
        mock_deps["inventory_service"].check_stock.return_value = 100  # plenty of stock
        mock_deps["db"].get_user.return_value = Mock(is_premium=False, email="user@test.com")
        mock_deps["payment_gateway"].charge.return_value = Mock(success=True, id="ch_123")
        mock_deps["db"].create_order.return_value = Mock(id="order_456")

        # Act
        order = service.place_order("user_1", sample_items, sample_payment)

        # Assert: order was created and returned
        assert order.id == "order_456"

    def test_payment_charged_correct_amount(
        self, service, mock_deps, sample_items, sample_payment
    ):
        mock_deps["inventory_service"].check_stock.return_value = 100
        mock_deps["db"].get_user.return_value = Mock(is_premium=False, email="user@test.com")
        mock_deps["payment_gateway"].charge.return_value = Mock(success=True, id="ch_123")
        mock_deps["db"].create_order.return_value = Mock(id="order_456")

        service.place_order("user_1", sample_items, sample_payment)

        # Total should be (2 * 25) + (1 * 50) = 100.00
        mock_deps["payment_gateway"].charge.assert_called_once_with(
            sample_payment, 100.00
        )

    def test_premium_user_gets_10_percent_discount(
        self, service, mock_deps, sample_items, sample_payment
    ):
        mock_deps["inventory_service"].check_stock.return_value = 100
        mock_deps["db"].get_user.return_value = Mock(is_premium=True, email="vip@test.com")
        mock_deps["payment_gateway"].charge.return_value = Mock(success=True, id="ch_123")
        mock_deps["db"].create_order.return_value = Mock(id="order_456")

        service.place_order("user_1", sample_items, sample_payment)

        # Premium discount: 100.00 * 0.9 = 90.00
        mock_deps["payment_gateway"].charge.assert_called_once_with(
            sample_payment, 90.00
        )

    def test_inventory_reserved_for_each_item(
        self, service, mock_deps, sample_items, sample_payment
    ):
        mock_deps["inventory_service"].check_stock.return_value = 100
        mock_deps["db"].get_user.return_value = Mock(is_premium=False, email="user@test.com")
        mock_deps["payment_gateway"].charge.return_value = Mock(success=True, id="ch_123")
        mock_deps["db"].create_order.return_value = Mock(id="order_456")

        service.place_order("user_1", sample_items, sample_payment)

        # Verify inventory was reserved for both items
        mock_deps["inventory_service"].reserve.assert_any_call("WIDGET-1", 2)
        mock_deps["inventory_service"].reserve.assert_any_call("GADGET-3", 1)
        assert mock_deps["inventory_service"].reserve.call_count == 2
```

**Priority 2: Error handling (what happens when things go wrong?)**

```python
class TestPlaceOrderStockValidation:
    """Prevent overselling -- one of the most damaging bugs."""

    def test_rejects_order_when_insufficient_stock(
        self, service, mock_deps, sample_payment
    ):
        mock_deps["inventory_service"].check_stock.return_value = 1  # only 1 in stock

        items = [{"product_id": "WIDGET-1", "quantity": 5, "price": 25.00}]

        with pytest.raises(InsufficientStockError) as exc_info:
            service.place_order("user_1", items, sample_payment)

        # Verify NO payment was attempted (critical: do not charge for unfulfillable orders)
        mock_deps["payment_gateway"].charge.assert_not_called()
        # Verify NO order was created
        mock_deps["db"].create_order.assert_not_called()

    def test_checks_stock_for_every_item(self, service, mock_deps, sample_payment):
        """Even if the first item has stock, check all items before proceeding."""
        def stock_by_product(product_id):
            return {"WIDGET-1": 100, "GADGET-3": 0}[product_id]

        mock_deps["inventory_service"].check_stock.side_effect = stock_by_product

        items = [
            {"product_id": "WIDGET-1", "quantity": 1, "price": 25.00},
            {"product_id": "GADGET-3", "quantity": 1, "price": 50.00},
        ]

        with pytest.raises(InsufficientStockError):
            service.place_order("user_1", items, sample_payment)


class TestPlaceOrderPaymentFailure:
    """What happens when payment fails -- make sure we do not create orphan orders."""

    def test_payment_failure_raises_error(
        self, service, mock_deps, sample_items, sample_payment
    ):
        mock_deps["inventory_service"].check_stock.return_value = 100
        mock_deps["db"].get_user.return_value = Mock(is_premium=False, email="user@test.com")
        mock_deps["payment_gateway"].charge.return_value = Mock(
            success=False, error_message="Card declined"
        )

        with pytest.raises(PaymentFailedError):
            service.place_order("user_1", sample_items, sample_payment)

        # CRITICAL: no order should be created if payment fails
        mock_deps["db"].create_order.assert_not_called()
        # CRITICAL: no inventory should be reserved
        mock_deps["inventory_service"].reserve.assert_not_called()


class TestPlaceOrderEmailFailure:
    """Email failure should NOT fail the order (it is logged, not raised)."""

    def test_email_failure_does_not_fail_the_order(
        self, service, mock_deps, sample_items, sample_payment
    ):
        mock_deps["inventory_service"].check_stock.return_value = 100
        mock_deps["db"].get_user.return_value = Mock(is_premium=False, email="user@test.com")
        mock_deps["payment_gateway"].charge.return_value = Mock(success=True, id="ch_123")
        mock_deps["db"].create_order.return_value = Mock(id="order_456")
        mock_deps["email_service"].send_order_confirmation.side_effect = ConnectionError("SMTP down")

        # Order should still succeed
        order = service.place_order("user_1", sample_items, sample_payment)
        assert order.id == "order_456"

        # But the failure should be logged
        mock_deps["logger"].warning.assert_called_once()
```

**Priority 3: Edge cases and validation**

```python
class TestPlaceOrderValidation:
    def test_rejects_zero_total(self, service, mock_deps, sample_payment):
        mock_deps["inventory_service"].check_stock.return_value = 100
        items = [{"product_id": "FREE-1", "quantity": 1, "price": 0.00}]

        with pytest.raises(ValueError, match="positive"):
            service.place_order("user_1", items, sample_payment)

    def test_rejects_negative_total(self, service, mock_deps, sample_payment):
        mock_deps["inventory_service"].check_stock.return_value = 100
        items = [{"product_id": "REFUND-1", "quantity": 1, "price": -10.00}]

        with pytest.raises(ValueError, match="positive"):
            service.place_order("user_1", items, sample_payment)

    def test_empty_items_list(self, service, mock_deps, sample_payment):
        # Depending on business rules, this might raise or return total of 0
        # Test documents the expected behavior either way
        with pytest.raises(ValueError):
            service.place_order("user_1", [], sample_payment)
```

**How to run these tests and what to do next:**

```bash
# Run the tests
pytest tests/test_order_service.py -v

# See coverage to find what you missed
pytest tests/test_order_service.py --cov=orders --cov-report=term-missing
```

**The testing priority framework for any codebase:**
1. Test the code that handles money (payments, billing, discounts)
2. Test the code that handles authorization (who can do what)
3. Test the code with complex business rules (stock validation, pricing)
4. Test error handling paths (what happens when dependencies fail)
5. Everything else

You do not need 100% coverage to get value from tests. These ~12 tests cover the most critical behaviors and will catch the most expensive bugs. Add more as you find bugs or add features.'''
    ),
    (
        "thinking/practical",
        r'''our tests break every time we refactor anything''',
        r'''<think>
This is a classic symptom of tests that are coupled to implementation details rather than testing behavior. But what specifically makes tests fragile? Let me think through the patterns:

The user is probably doing one or more of these:
- Testing private methods directly -- these change constantly during refactoring
- Asserting exact mock call sequences -- "assert mock.called_with(x, y, z)" breaks if you change parameter order or add a default
- Using deep mocking that mirrors the internal structure -- if you mock three layers deep, any structural change breaks everything
- Testing HOW something works rather than WHAT it does

I initially thought the fix was "just use fewer mocks," but actually that is only part of it. The deeper fix is to refactor tests to test the public interface and observable behavior. Let me think about what "observable" means here... it means outputs, return values, state changes, and side effects that matter to the caller -- not internal method calls.

The pattern is:
- BAD: testing that method A calls method B with specific args (this is testing the wiring, not the behavior)
- GOOD: testing that given input X, the output is Y and side effect Z occurred

Wait, I should also address the common objection: "but if I do not test the internals, how do I know my code is correct?" The answer is that you test behavior through the public API. If refactoring changes the internals but produces the same results, your tests should still pass. If they do not, your tests are too tightly coupled.

I should show before/after examples of fragile tests becoming resilient tests, because concrete examples are much more convincing than abstract principles.
</think>

Your tests are probably coupled to implementation details instead of testing behavior. Here is how to diagnose and fix this.

**The symptom:** You rename a private method, change the order of operations, or extract a helper function -- and tests break even though the feature still works correctly.

**The root cause: tests that mirror your code structure instead of testing outcomes.**

**Example: A fragile test (BEFORE)**

```python
# BAD: This test breaks if you change ANY internal detail
class TestUserRegistration:
    def test_register_user(self, mock_db, mock_hasher, mock_emailer):
        service = UserService(mock_db, mock_hasher, mock_emailer)

        service.register("alice@test.com", "password123")

        # Testing internal implementation details:
        mock_hasher.hash.assert_called_once_with("password123")
        mock_db.insert.assert_called_once_with(
            "users",
            {"email": "alice@test.com", "password_hash": mock_hasher.hash.return_value}
        )
        mock_emailer.send.assert_called_once_with(
            to="alice@test.com",
            template="welcome",
            context={"name": "alice"},
        )

    # If you:
    # - Rename hash() to hash_password() -> TEST BREAKS
    # - Change DB method from insert() to create() -> TEST BREAKS
    # - Change email template name -> TEST BREAKS
    # - Add a validation step before hashing -> TEST BREAKS
    # - Extract name from email differently -> TEST BREAKS
```

**The same test, written to test BEHAVIOR (AFTER)**

```python
# GOOD: This test survives refactoring because it tests WHAT happens, not HOW
class TestUserRegistration:
    def test_new_user_can_log_in_after_registration(self, service, db):
        """Test the actual behavior: registered users can authenticate."""
        service.register("alice@test.com", "password123")

        # Test the OUTCOME, not the internals
        user = db.query(User).filter_by(email="alice@test.com").first()
        assert user is not None
        assert service.authenticate("alice@test.com", "password123") is True

    def test_registration_sends_welcome_email(self, service, fake_emailer):
        """Test that an email was sent, not the exact API call."""
        service.register("alice@test.com", "password123")

        # Check the observable outcome: an email was sent to the right address
        assert len(fake_emailer.sent_emails) == 1
        assert fake_emailer.sent_emails[0]["to"] == "alice@test.com"
        # Do NOT assert the exact template, context, or internal method calls

    def test_duplicate_email_rejected(self, service):
        """Test business rule, not implementation."""
        service.register("alice@test.com", "password123")

        with pytest.raises(DuplicateEmailError):
            service.register("alice@test.com", "different_password")

    def test_password_not_stored_in_plaintext(self, service, db):
        """Security behavior test -- does not care HOW it is hashed."""
        service.register("alice@test.com", "password123")

        user = db.query(User).filter_by(email="alice@test.com").first()
        assert user.password_hash != "password123"
        assert len(user.password_hash) > 20  # some kind of hash was applied
```

**The key differences:**

| Fragile Test | Resilient Test |
|-------------|----------------|
| Asserts mock method was called with exact args | Asserts the outcome is correct |
| Tests private methods directly | Tests only the public API |
| Verifies call order | Verifies end state |
| Uses deep mocking | Uses fakes or real lightweight dependencies |
| Breaks on refactor | Only breaks when behavior changes |

**Replace mocks with fakes for better tests:**

```python
# Instead of Mock(), build simple fakes that behave like the real thing
# Fakes are more resilient because they do not care about call signatures

class FakeEmailService:
    """A fake that records sent emails without actually sending them."""
    def __init__(self):
        self.sent_emails = []

    def send_order_confirmation(self, to_email, order):
        self.sent_emails.append({
            "to": to_email,
            "type": "order_confirmation",
            "order_id": order.id,
        })

    def send_welcome(self, to_email):
        self.sent_emails.append({"to": to_email, "type": "welcome"})


class FakePaymentGateway:
    """A fake that simulates payment processing."""
    def __init__(self, should_succeed=True):
        self.should_succeed = should_succeed
        self.charges = []

    def charge(self, payment_info, amount):
        charge = Mock(
            success=self.should_succeed,
            id=f"fake_ch_{len(self.charges)}",
            amount=amount,
            error_message=None if self.should_succeed else "Declined",
        )
        self.charges.append(charge)
        return charge


class InMemoryDatabase:
    """A fake database for testing -- fast, no setup, no cleanup."""
    def __init__(self):
        self._users = {}
        self._orders = {}

    def get_user(self, user_id):
        return self._users.get(user_id)

    def create_order(self, user_id, items, total, charge_id):
        order_id = f"order_{len(self._orders)}"
        order = Mock(id=order_id, user_id=user_id, items=items, total=total)
        self._orders[order_id] = order
        return order

    def seed_user(self, user_id, **kwargs):
        """Test helper: add a user for test setup."""
        self._users[user_id] = Mock(id=user_id, **kwargs)


# Now tests read like specifications:
class TestOrderPlacement:
    @pytest.fixture
    def fake_db(self):
        db = InMemoryDatabase()
        db.seed_user("user_1", is_premium=False, email="test@example.com")
        return db

    @pytest.fixture
    def fake_payments(self):
        return FakePaymentGateway(should_succeed=True)

    @pytest.fixture
    def fake_email(self):
        return FakeEmailService()

    def test_order_charges_correct_amount(self, fake_db, fake_payments, fake_email):
        service = OrderService(
            db=fake_db,
            payment_gateway=fake_payments,
            inventory_service=Mock(check_stock=Mock(return_value=100)),
            email_service=fake_email,
            logger=Mock(),
        )

        items = [{"product_id": "A", "quantity": 2, "price": 30.00}]
        service.place_order("user_1", items, {"card": "tok_123"})

        # Check outcome, not implementation
        assert len(fake_payments.charges) == 1
        assert fake_payments.charges[0].amount == 60.00

    def test_confirmation_email_sent_to_user(self, fake_db, fake_payments, fake_email):
        service = OrderService(
            db=fake_db,
            payment_gateway=fake_payments,
            inventory_service=Mock(check_stock=Mock(return_value=100)),
            email_service=fake_email,
            logger=Mock(),
        )

        items = [{"product_id": "A", "quantity": 1, "price": 10.00}]
        service.place_order("user_1", items, {"card": "tok_123"})

        assert len(fake_email.sent_emails) == 1
        assert fake_email.sent_emails[0]["to"] == "test@example.com"
```

**Rules for tests that survive refactoring:**
1. Test behavior through the public API only
2. Never test private/internal methods directly
3. Assert outcomes (return values, state changes, side effects), not implementation steps
4. Use fakes instead of mocks when possible
5. If a refactor breaks a test but the feature still works, the test was wrong
6. Each test should read like a specification: "given X, when Y, then Z"'''
    ),
    (
        "thinking/practical",
        r'''how do I test this function that calls an external API?

def get_weather(city: str) -> dict:
    response = requests.get(
        f"https://api.weather.com/v1/current",
        params={"city": city, "key": os.environ["WEATHER_API_KEY"]},
        timeout=5,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "temperature": data["main"]["temp"],
        "humidity": data["main"]["humidity"],
        "description": data["weather"][0]["description"],
    }''',
        r'''<think>
The user has a function that calls an external API and does not know how to test it. This is one of the most common testing questions, and the answer is not straightforward because there are multiple valid approaches.

My first thought was "just mock requests.get" -- and that works, but it couples your tests to the HTTP library you use. If you switch from requests to httpx, all your tests break. Hmm, is that actually a problem? For a small project, probably not. For a larger project, it matters.

Let me think through the approaches:

1. Mock requests.get at the test level (quick, but couples tests to the requests library)
2. Use responses library or httpx mock (cleaner mocking of HTTP layer, but still library-specific)
3. Refactor to inject the HTTP client (best for testability -- but wait, is this over-engineering for a simple API call?)
4. Use VCR.py to record real responses and replay them (good for complex APIs with large payloads)
5. Contract testing (verify your code handles the API's actual response format)

I initially wanted to recommend only approach 3 (dependency injection) since it is the "clean" answer, but actually different situations call for different strategies. A quick script that calls one API endpoint does not need a full DI architecture. I should show multiple approaches and let the user choose.

The key insight: unit tests mock the external API to test YOUR code's logic (data transformation, error handling). Integration tests actually hit the API (in a controlled way) to verify the contract has not changed. These are different concerns and need different test strategies.
</think>

There are three levels of testing for code that calls external APIs. You need all three for solid coverage.

**Level 1: Unit tests with mocked HTTP (test YOUR logic, not the API)**

```python
# tests/test_weather.py
import pytest
from unittest.mock import patch, Mock
from weather import get_weather


class TestGetWeather:
    """Unit tests: mock the HTTP layer to test our data transformation logic."""

    @patch("weather.requests.get")
    def test_extracts_weather_data_from_response(self, mock_get):
        # Simulate what the real API returns
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "main": {"temp": 72.5, "humidity": 65, "pressure": 1013},
                "weather": [{"description": "partly cloudy", "icon": "02d"}],
                "name": "San Francisco",
            }),
        )
        mock_get.return_value.raise_for_status = Mock()

        result = get_weather("San Francisco")

        assert result == {
            "temperature": 72.5,
            "humidity": 65,
            "description": "partly cloudy",
        }

    @patch("weather.requests.get")
    def test_passes_correct_parameters(self, mock_get, monkeypatch):
        monkeypatch.setenv("WEATHER_API_KEY", "test_key_123")
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "main": {"temp": 70, "humidity": 50},
                "weather": [{"description": "clear"}],
            }),
        )
        mock_get.return_value.raise_for_status = Mock()

        get_weather("London")

        mock_get.assert_called_once_with(
            "https://api.weather.com/v1/current",
            params={"city": "London", "key": "test_key_123"},
            timeout=5,
        )

    @patch("weather.requests.get")
    def test_raises_on_http_error(self, mock_get):
        from requests.exceptions import HTTPError
        mock_get.return_value.raise_for_status.side_effect = HTTPError("404 Not Found")

        with pytest.raises(HTTPError):
            get_weather("NonexistentCity")

    @patch("weather.requests.get")
    def test_raises_on_timeout(self, mock_get):
        from requests.exceptions import Timeout
        mock_get.side_effect = Timeout("Connection timed out")

        with pytest.raises(Timeout):
            get_weather("Tokyo")
```

**Level 2: Better architecture -- inject the HTTP client for easier testing**

```python
# weather.py (refactored)
"""Refactored to accept an HTTP client, making testing cleaner."""
import os
from typing import Protocol
import requests


class HTTPClient(Protocol):
    """Protocol so any HTTP client works (requests, httpx, fake)."""
    def get(self, url: str, params: dict = None, timeout: int = None) -> "Response": ...


class WeatherService:
    def __init__(self, http_client: HTTPClient = None, api_key: str = None):
        self.client = http_client or requests
        self.api_key = api_key or os.environ["WEATHER_API_KEY"]
        self.base_url = "https://api.weather.com/v1"

    def get_current(self, city: str) -> dict:
        response = self.client.get(
            f"{self.base_url}/current",
            params={"city": city, "key": self.api_key},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "temperature": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "description": data["weather"][0]["description"],
        }

    def get_forecast(self, city: str, days: int = 5) -> list[dict]:
        response = self.client.get(
            f"{self.base_url}/forecast",
            params={"city": city, "key": self.api_key, "days": days},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return [
            {
                "date": day["dt_txt"],
                "temperature": day["main"]["temp"],
                "description": day["weather"][0]["description"],
            }
            for day in data["list"]
        ]
```

```python
# tests/test_weather_service.py
"""Tests using a fake HTTP client -- no mocking framework needed."""
import pytest
from weather import WeatherService


class FakeResponse:
    """A simple fake HTTP response."""
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests.exceptions import HTTPError
            raise HTTPError(f"{self.status_code} Error")


class FakeHTTPClient:
    """Records all requests and returns preconfigured responses."""
    def __init__(self):
        self.requests = []
        self.responses = {}  # url_pattern -> FakeResponse

    def register(self, url_contains: str, response_data: dict, status_code: int = 200):
        self.responses[url_contains] = FakeResponse(response_data, status_code)

    def get(self, url, params=None, timeout=None):
        self.requests.append({"url": url, "params": params, "timeout": timeout})
        for pattern, response in self.responses.items():
            if pattern in url:
                return response
        return FakeResponse({}, 404)


class TestWeatherServiceCurrent:
    @pytest.fixture
    def client(self):
        fake = FakeHTTPClient()
        fake.register("/current", {
            "main": {"temp": 68.0, "humidity": 72},
            "weather": [{"description": "sunny"}],
        })
        return fake

    @pytest.fixture
    def service(self, client):
        return WeatherService(http_client=client, api_key="test_key")

    def test_returns_formatted_weather(self, service):
        result = service.get_current("Portland")
        assert result["temperature"] == 68.0
        assert result["humidity"] == 72
        assert result["description"] == "sunny"

    def test_sends_api_key(self, service, client):
        service.get_current("Portland")
        assert client.requests[0]["params"]["key"] == "test_key"

    def test_sends_city_parameter(self, service, client):
        service.get_current("Portland")
        assert client.requests[0]["params"]["city"] == "Portland"

    def test_sets_timeout(self, service, client):
        service.get_current("Portland")
        assert client.requests[0]["timeout"] == 5


class TestWeatherServiceErrors:
    def test_http_error_propagates(self):
        fake = FakeHTTPClient()
        fake.register("/current", {"error": "not found"}, status_code=404)
        service = WeatherService(http_client=fake, api_key="key")

        from requests.exceptions import HTTPError
        with pytest.raises(HTTPError):
            service.get_current("Atlantis")

    def test_missing_data_raises_key_error(self):
        """What if the API changes its response format?"""
        fake = FakeHTTPClient()
        fake.register("/current", {"unexpected": "format"})
        service = WeatherService(http_client=fake, api_key="key")

        with pytest.raises(KeyError):
            service.get_current("Portland")
```

**Level 3: Integration test (verify the real API contract, run occasionally)**

```python
# tests/integration/test_weather_api.py
"""Integration tests that hit the real API.
Run these in CI on a schedule (daily), not on every commit.
Mark with pytest marker so they can be skipped easily."""

import os
import pytest
from weather import WeatherService

# Skip if no API key available (local dev, PR builds)
pytestmark = pytest.mark.skipif(
    "WEATHER_API_KEY" not in os.environ,
    reason="WEATHER_API_KEY not set -- skipping integration tests",
)


class TestWeatherAPIContract:
    """These tests verify the real API still returns data in the format we expect.
    If these fail, the API changed its response format."""

    @pytest.fixture
    def service(self):
        return WeatherService()

    def test_current_weather_returns_expected_fields(self, service):
        result = service.get_current("London")

        # Verify the shape of the response -- not exact values
        assert isinstance(result["temperature"], (int, float))
        assert isinstance(result["humidity"], (int, float))
        assert isinstance(result["description"], str)
        assert len(result["description"]) > 0

    def test_unknown_city_raises_error(self, service):
        from requests.exceptions import HTTPError
        with pytest.raises(HTTPError):
            service.get_current("ThisCityDoesNotExist12345")
```

**Which tests to run when:**

```ini
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
markers = [
    "integration: tests that hit real external services (run daily in CI)",
]

# Run only unit tests (fast, every commit):
# pytest -m "not integration"

# Run everything including integration (daily CI job):
# pytest
```

**Summary of the three approaches:**
1. **unittest.mock.patch** -- Quick and dirty, good for simple functions. Couples to import paths.
2. **Dependency injection + fakes** -- Better architecture, tests survive refactoring. Recommended.
3. **Integration tests** -- Verify the real API contract. Run on schedule, not every commit.

Use approach 2 for new code. Use approach 1 to quickly add tests to existing code without refactoring. Add approach 3 for any external API your business depends on.'''
    ),
    (
        "thinking/practical",
        r'''we have 90% code coverage but still find bugs in production''',
        r'''<think>
This is a great question that reveals a common misconception. My first reaction is: coverage measures which lines EXECUTED during tests, not whether those lines were tested CORRECTLY. You can have 100% coverage with zero useful assertions.

But wait, is that the whole story? Let me think deeper about why high coverage fails to catch bugs:

1. Tests assert nothing meaningful (they run the code but do not check results) -- I have seen test suites where half the tests just call functions without asserting anything. Coverage is 100%, tests are worthless.
2. Tests only cover the happy path (errors, edge cases, race conditions untested)
3. No tests for integration points (each unit works alone, fails when combined) -- hmm, this is actually the most common source of production bugs in well-tested codebases. The units all pass, but the system fails.
4. State-dependent bugs (works in test env with clean state, fails in prod with accumulated state)
5. Missing boundary testing (off-by-one, empty inputs, null values)
6. No concurrency testing (race conditions, deadlocks) -- coverage tools cannot even detect these gaps
7. Mock-heavy tests that do not reflect real behavior -- this is subtle. If your mock returns "success" but the real API returns a different format, your test passes and production crashes.

I considered recommending just "write better assertions" but actually the fundamental problem is that coverage is a quantity metric, not a quality metric. The real question is: would this test FAIL if I introduced a bug? That is exactly what mutation testing measures.

I should show them:
1. How to audit their existing tests for quality (not just quantity)
2. Mutation testing (the real test of test quality -- because it measures whether tests catch injected bugs)
3. Property-based testing (finds edge cases humans miss)
4. How to identify coverage gaps that metrics miss
</think>

Coverage measures which lines **ran**, not whether your tests actually **verify correct behavior**. Here is how to find and fix the gaps.

**Why 90% coverage can still miss bugs:**

```python
# This function has a subtle bug
def calculate_discount(price, quantity, is_member):
    if quantity >= 10:
        discount = 0.15
    elif quantity >= 5:
        discount = 0.10
    else:
        discount = 0.0

    if is_member:
        discount += 0.05

    # BUG: discount can exceed 0.20 (15% + 5% = 20%)
    # but there is no cap, and the business rule says max 18%
    return price * quantity * (1 - discount)


# This test gives 100% line coverage but misses the bug:
def test_discount():
    result = calculate_discount(10.0, 10, True)
    assert result > 0  # Passes! But does not check the actual amount
```

**Tool 1: Mutation testing (the best way to find weak tests)**

Mutation testing modifies your source code (introduces bugs) and checks if your tests catch them. If a mutant survives (tests still pass), your tests are missing something.

```bash
# Install mutmut
pip install mutmut

# Run mutation testing against your test suite
mutmut run --paths-to-mutate=src/

# See which mutations survived (tests did NOT catch these bugs)
mutmut results

# Example output:
# Survived mutants:
#   src/pricing.py:45 - changed >= to > (boundary bug not caught)
#   src/pricing.py:52 - changed 0.15 to 0.16 (exact value not asserted)
#   src/auth.py:23 - removed if statement (error path not tested)
```

```python
# Fix: write tests that catch the mutations

def test_discount_exact_values():
    """Test exact amounts, not just 'greater than zero'."""
    # No discount
    assert calculate_discount(10.0, 1, False) == 10.0

    # 5+ quantity discount only
    assert calculate_discount(10.0, 5, False) == 45.0  # 50 * 0.90

    # 10+ quantity discount only
    assert calculate_discount(10.0, 10, False) == 85.0  # 100 * 0.85

    # Member discount stacks
    assert calculate_discount(10.0, 10, True) == 80.0  # 100 * 0.80

    # Boundary: exactly at threshold
    assert calculate_discount(10.0, 5, False) != calculate_discount(10.0, 4, False)
    assert calculate_discount(10.0, 10, False) != calculate_discount(10.0, 9, False)
```

**Tool 2: Property-based testing (finds edge cases humans miss)**

```python
# tests/test_pricing_properties.py
from hypothesis import given, strategies as st, assume
from pricing import calculate_discount


class TestDiscountProperties:
    """Property-based tests: define rules that must ALWAYS hold,
    then let Hypothesis generate thousands of test cases."""

    @given(
        price=st.floats(min_value=0.01, max_value=10000.0),
        quantity=st.integers(min_value=1, max_value=1000),
        is_member=st.booleans(),
    )
    def test_result_is_never_negative(self, price, quantity, is_member):
        """No matter what inputs, the total should never be negative."""
        result = calculate_discount(price, quantity, is_member)
        assert result >= 0

    @given(
        price=st.floats(min_value=0.01, max_value=10000.0),
        quantity=st.integers(min_value=1, max_value=1000),
        is_member=st.booleans(),
    )
    def test_result_never_exceeds_undiscounted_price(self, price, quantity, is_member):
        """Discounted total should never exceed the full price."""
        result = calculate_discount(price, quantity, is_member)
        full_price = price * quantity
        assert result <= full_price + 0.01  # small epsilon for floating point

    @given(
        price=st.floats(min_value=0.01, max_value=10000.0),
        quantity=st.integers(min_value=1, max_value=1000),
    )
    def test_member_always_pays_less_or_equal(self, price, quantity):
        """Members should never pay MORE than non-members."""
        member_price = calculate_discount(price, quantity, True)
        regular_price = calculate_discount(price, quantity, False)
        assert member_price <= regular_price + 0.01

    @given(
        price=st.floats(min_value=0.01, max_value=10000.0),
        is_member=st.booleans(),
    )
    def test_more_quantity_means_lower_or_equal_per_unit_price(self, price, is_member):
        """Buying more should never increase the per-unit price."""
        price_1 = calculate_discount(price, 1, is_member) / 1
        price_10 = calculate_discount(price, 10, is_member) / 10
        price_100 = calculate_discount(price, 100, is_member) / 100
        assert price_10 <= price_1 + 0.01
        assert price_100 <= price_10 + 0.01

    @given(
        price=st.floats(min_value=0.01, max_value=10000.0),
        quantity=st.integers(min_value=1, max_value=1000),
        is_member=st.booleans(),
    )
    def test_discount_never_exceeds_max_policy(self, price, quantity, is_member):
        """Business rule: maximum discount is 18%."""
        result = calculate_discount(price, quantity, is_member)
        full_price = price * quantity
        min_allowed = full_price * (1 - 0.18)
        # THIS WILL FAIL -- revealing the 20% discount bug!
        assert result >= min_allowed - 0.01
```

**Tool 3: Coverage quality audit (find tests with weak assertions)**

```python
# scripts/audit_test_quality.py
"""Find tests that are likely to have weak assertions.
Run: python scripts/audit_test_quality.py tests/"""

import ast
import sys
from pathlib import Path


def audit_test_file(filepath: Path) -> list[dict]:
    """Find tests with suspicious patterns."""
    issues = []
    tree = ast.parse(filepath.read_text())

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            # Count assertions in this test
            asserts = sum(
                1 for child in ast.walk(node)
                if isinstance(child, ast.Assert)
                or (isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr.startswith("assert"))
            )

            if asserts == 0:
                issues.append({
                    "file": str(filepath),
                    "test": node.name,
                    "line": node.lineno,
                    "issue": "NO ASSERTIONS - test runs code but checks nothing",
                })

            # Check for weak assertions like "assert result" or "assert result is not None"
            for child in ast.walk(node):
                if isinstance(child, ast.Assert):
                    if isinstance(child.test, ast.Name):
                        issues.append({
                            "file": str(filepath),
                            "test": node.name,
                            "line": child.lineno,
                            "issue": f"WEAK ASSERTION: 'assert {child.test.id}' - only checks truthiness",
                        })

    return issues


if __name__ == "__main__":
    test_dir = Path(sys.argv[1])
    all_issues = []
    for f in test_dir.rglob("test_*.py"):
        all_issues.extend(audit_test_file(f))

    if all_issues:
        print(f"Found {len(all_issues)} test quality issues:\n")
        for issue in all_issues:
            print(f"  {issue['file']}:{issue['line']} [{issue['test']}]")
            print(f"    {issue['issue']}\n")
    else:
        print("No obvious test quality issues found.")
```

**Types of bugs that coverage misses (and how to catch them):**

| Bug Type | Why Coverage Misses It | How to Catch It |
|----------|----------------------|-----------------|
| Wrong calculation | Line runs but result not checked | Mutation testing, exact assertions |
| Boundary errors (off-by-one) | Both branches covered, but boundary not tested | Property-based testing |
| Race conditions | Single-threaded tests cannot hit them | Stress tests, thread-safety tests |
| State corruption | Tests start with clean state | Test with accumulated state, fuzz inputs |
| Integration failures | Each unit mocked/tested alone | Integration tests with real dependencies |
| Error handling gaps | Happy path covered, errors not | Fault injection, chaos testing |

**Action plan:**
1. Run `mutmut` on your codebase -- it will show you exactly which "bugs" your tests would miss
2. Add Hypothesis property-based tests for your core business logic (pricing, permissions, validation)
3. Run the assertion audit script to find tests with no assertions or weak assertions
4. Replace `assert result` with `assert result == expected_value` everywhere
5. Add integration tests for the 3-5 most critical user flows'''
    ),
    (
        "thinking/practical",
        r'''how do I test async code? my tests keep hanging or passing when they shouldn't''',
        r'''<think>
Async testing problems are notoriously frustrating because the failure modes are so confusing. Let me think through the common ones:

1. Tests hang because they await something that never completes (missing mock, deadlock) -- this is the worst, because the test just sits there and you have no idea why
2. Tests pass because the assertion runs before the async operation completes -- wait, this is particularly sneaky. The test looks correct, runs green, but the assertion never actually executed because it was racing with the coroutine
3. Tests pass because exceptions in async code are silently swallowed -- hmm, this happens when you forget to await a coroutine that raises. The exception goes to the event loop's exception handler, not to the test
4. Incorrect use of pytest-asyncio (missing marks, wrong event loop)

My first thought was to show how to use unittest.mock with async code, but actually the bigger problem is the testing framework setup. If pytest-asyncio is not configured correctly, nothing else matters.

The user is probably using pytest and needs to know:
- How to properly set up pytest-asyncio -- there are two modes (strict and auto) and picking the wrong one causes confusing failures
- How to write async tests that actually wait for results
- How to add timeouts so tests fail instead of hanging (because a hanging test blocks your entire CI pipeline)
- How to test that async exceptions are properly raised
- How to test concurrent async code

I initially considered covering trio and anyio testing too, but that would dilute the focus. Let me stick with asyncio + pytest-asyncio since that is what 90% of Python async code uses.
</think>

Async tests fail in subtle ways because of timing, event loop issues, and silently swallowed exceptions. Here are the patterns that fix each problem.

**Setup: Configure pytest-asyncio properly**

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"  # all async tests run automatically, no per-test markers needed

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-timeout>=2.2",  # prevents hanging tests
]
```

**Problem 1: Tests hang forever (missing await, deadlock, unyielded future)**

```python
# tests/conftest.py
import pytest

# Global timeout: no test should run longer than 10 seconds
# If it does, something is wrong (hanging await, deadlock, etc.)
@pytest.fixture(autouse=True)
def test_timeout():
    """Fail tests that take too long instead of hanging CI."""
    # pytest-timeout handles this via config:
    pass

# In pyproject.toml:
# [tool.pytest.ini_options]
# timeout = 10
# timeout_method = "signal"  # or "thread" on Windows
```

```python
# tests/test_async_service.py
import asyncio
import pytest


# WRONG: This test hangs if fetch_data never returns
async def test_hangs_forever_bad():
    result = await some_service.fetch_data()  # hangs if mock is wrong
    assert result is not None


# RIGHT: Use asyncio.wait_for to add explicit timeouts
async def test_with_timeout():
    try:
        result = await asyncio.wait_for(
            some_service.fetch_data(),
            timeout=2.0,
        )
        assert result is not None
    except asyncio.TimeoutError:
        pytest.fail("fetch_data() did not complete within 2 seconds")


# EVEN BETTER: Create a helper for this pattern
async def await_with_timeout(coro, timeout=2.0, message="Operation timed out"):
    """Await a coroutine with a timeout that produces a clear test failure."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        pytest.fail(f"{message} (waited {timeout}s)")


async def test_clean_timeout():
    result = await await_with_timeout(
        some_service.fetch_data(),
        timeout=2.0,
        message="fetch_data did not return",
    )
    assert result["status"] == "ok"
```

**Problem 2: Tests pass when they should fail (fire-and-forget coroutines)**

```python
# WRONG: This test ALWAYS passes because the exception is in a task
# that nobody awaits
async def test_silently_passes_bad():
    service = MyService()
    # This creates a task but does not await it
    # If the task raises an exception, pytest never sees it
    asyncio.create_task(service.process_item(bad_data))
    # Test ends before the task finishes -> passes!


# RIGHT: Always await the things you are testing
async def test_awaits_result():
    service = MyService()
    with pytest.raises(ValueError):
        await service.process_item(bad_data)


# RIGHT: If you must test background tasks, use TaskGroup
async def test_background_task_errors_propagate():
    service = MyService()
    with pytest.raises(ValueError):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(service.process_item(bad_data))
    # TaskGroup ensures the exception is raised when the group exits


# RIGHT: If you need to test fire-and-forget behavior,
# capture unhandled exceptions
async def test_unhandled_task_exception():
    exceptions = []
    loop = asyncio.get_event_loop()
    original_handler = loop.get_exception_handler()

    def capture_exception(loop, context):
        exceptions.append(context.get("exception"))

    loop.set_exception_handler(capture_exception)
    try:
        service = MyService()
        task = asyncio.create_task(service.process_item(bad_data))
        await asyncio.sleep(0.1)  # give the task time to fail

        assert len(exceptions) == 1
        assert isinstance(exceptions[0], ValueError)
    finally:
        loop.set_exception_handler(original_handler)
```

**Problem 3: Testing concurrent async code**

```python
# Testing that your code handles concurrent access correctly

async def test_concurrent_counter_increment():
    """Verify that concurrent increments do not lose updates."""
    counter = AsyncCounter()  # your class under test

    async def increment_many(n):
        for _ in range(n):
            await counter.increment()

    # Run 10 concurrent incrementors, each doing 100 increments
    async with asyncio.TaskGroup() as tg:
        for _ in range(10):
            tg.create_task(increment_many(100))

    # If there is a race condition, the count will be less than 1000
    assert counter.value == 1000


async def test_rate_limiter_under_concurrent_load():
    """Test that the rate limiter actually limits under concurrent requests."""
    limiter = RateLimiter(max_requests=5, window_seconds=1)
    results = []

    async def make_request(i):
        allowed = await limiter.check("user_1")
        results.append({"request": i, "allowed": allowed})

    # Fire 20 requests concurrently
    async with asyncio.TaskGroup() as tg:
        for i in range(20):
            tg.create_task(make_request(i))

    allowed_count = sum(1 for r in results if r["allowed"])
    assert allowed_count == 5  # only 5 should be allowed


async def test_connection_pool_limits_concurrent_connections():
    """Test that the pool does not exceed max connections."""
    max_active = 0
    current_active = 0
    lock = asyncio.Lock()

    class FakeConnection:
        async def __aenter__(self):
            nonlocal current_active, max_active
            async with lock:
                current_active += 1
                max_active = max(max_active, current_active)
            await asyncio.sleep(0.05)  # simulate work
            return self

        async def __aexit__(self, *args):
            nonlocal current_active
            async with lock:
                current_active -= 1

    pool = ConnectionPool(max_size=3, connection_factory=FakeConnection)

    # Run 10 concurrent operations through a pool of 3
    async with asyncio.TaskGroup() as tg:
        for _ in range(10):
            tg.create_task(pool.execute(lambda conn: None))

    assert max_active <= 3  # pool should never exceed max size
```

**Problem 4: Mocking async functions**

```python
# Mocking async methods requires AsyncMock, not Mock

from unittest.mock import AsyncMock, Mock, patch

# WRONG: Mock() for async function -- returns a Mock, not a coroutine
# This causes "object Mock can't be used in 'await' expression"

# RIGHT: Use AsyncMock
async def test_with_async_mock():
    service = OrderService()
    service.payment_client = AsyncMock()
    service.payment_client.charge.return_value = {"status": "success", "id": "ch_123"}

    result = await service.process_payment(amount=50.0, token="tok_test")
    assert result["status"] == "success"
    service.payment_client.charge.assert_awaited_once_with(50.0, "tok_test")


# Patching async methods
async def test_with_async_patch():
    with patch.object(
        PaymentClient, "charge",
        new_callable=AsyncMock,
        return_value={"status": "success"},
    ) as mock_charge:
        service = OrderService()
        result = await service.process_payment(amount=50.0, token="tok_test")

        assert result["status"] == "success"
        mock_charge.assert_awaited_once()


# Testing async iterators / generators
async def test_async_iterator():
    async def fake_stream():
        for item in [{"id": 1}, {"id": 2}, {"id": 3}]:
            yield item

    processor = StreamProcessor()
    results = await processor.process_stream(fake_stream())

    assert len(results) == 3
    assert results[0]["id"] == 1
```

**Problem 5: Testing async context managers and cleanup**

```python
async def test_resource_cleanup_on_error():
    """Verify that resources are properly cleaned up even when async code raises."""
    cleanup_called = False

    class FakeResource:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            nonlocal cleanup_called
            cleanup_called = True
            return False  # do not suppress the exception

        async def do_work(self):
            raise RuntimeError("something broke")

    with pytest.raises(RuntimeError):
        async with FakeResource() as resource:
            await resource.do_work()

    assert cleanup_called, "Cleanup should run even when do_work() raises"
```

**Quick reference for common async test mistakes:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| Test hangs forever | Awaiting something that never completes | Add `asyncio.wait_for` timeout |
| Test passes but should fail | Exception in un-awaited task | Always await, use TaskGroup |
| "can't be used in await" | Using Mock instead of AsyncMock | Use `AsyncMock()` |
| Test fails randomly | Race condition in test setup | Use locks, proper synchronization |
| Different results on each run | Timing-dependent assertions | Use events/conditions, not `sleep` |'''
    ),
]
