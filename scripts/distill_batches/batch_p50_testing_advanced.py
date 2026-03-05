"""Advanced testing — E2E, property-based, load testing, and test architecture."""

PAIRS = [
    (
        "testing/playwright-e2e",
        "Show Playwright E2E testing patterns: page objects, fixtures, assertions, and CI integration.",
        '''Playwright E2E testing patterns:

```python
import pytest
from playwright.sync_api import Page, expect, BrowserContext
from dataclasses import dataclass


# --- Page Object Model ---

class LoginPage:
    URL = "/login"

    def __init__(self, page: Page):
        self.page = page
        self.email_input = page.locator('[data-testid="email"]')
        self.password_input = page.locator('[data-testid="password"]')
        self.submit_button = page.locator('[data-testid="login-submit"]')
        self.error_message = page.locator('[data-testid="login-error"]')

    def navigate(self):
        self.page.goto(self.URL)
        return self

    def login(self, email: str, password: str):
        self.email_input.fill(email)
        self.password_input.fill(password)
        self.submit_button.click()
        return self

    def expect_error(self, message: str):
        expect(self.error_message).to_contain_text(message)
        return self

    def expect_redirect_to(self, path: str):
        expect(self.page).to_have_url(f"**{path}")
        return self


class DashboardPage:
    URL = "/dashboard"

    def __init__(self, page: Page):
        self.page = page
        self.welcome = page.locator('[data-testid="welcome"]')
        self.nav_items = page.locator("nav a")
        self.user_menu = page.locator('[data-testid="user-menu"]')

    def expect_welcome(self, name: str):
        expect(self.welcome).to_contain_text(f"Welcome, {name}")
        return self

    def navigate_to(self, section: str):
        self.page.locator(f'nav a:has-text("{section}")').click()
        return self

    def logout(self):
        self.user_menu.click()
        self.page.locator('text=Logout').click()
        return LoginPage(self.page)


class ProductsPage:
    def __init__(self, page: Page):
        self.page = page
        self.search_input = page.locator('[data-testid="search"]')
        self.product_cards = page.locator('[data-testid="product-card"]')
        self.add_to_cart_buttons = page.locator('[data-testid="add-to-cart"]')

    def search(self, query: str):
        self.search_input.fill(query)
        self.search_input.press("Enter")
        self.page.wait_for_load_state("networkidle")
        return self

    def expect_product_count(self, count: int):
        expect(self.product_cards).to_have_count(count)
        return self

    def add_first_to_cart(self):
        self.add_to_cart_buttons.first.click()
        return self


# --- Fixtures ---

@pytest.fixture
def authenticated_page(page: Page) -> Page:
    """Login and return authenticated page."""
    login = LoginPage(page).navigate()
    login.login("test@example.com", "password123")
    page.wait_for_url("**/dashboard")
    return page


# --- Tests ---

class TestLogin:
    def test_successful_login(self, page: Page):
        login = LoginPage(page).navigate()
        login.login("user@example.com", "correct_password")
        login.expect_redirect_to("/dashboard")

    def test_invalid_credentials(self, page: Page):
        login = LoginPage(page).navigate()
        login.login("user@example.com", "wrong_password")
        login.expect_error("Invalid email or password")

    def test_empty_form_validation(self, page: Page):
        login = LoginPage(page).navigate()
        login.submit_button.click()
        expect(page.locator("text=Email is required")).to_be_visible()


class TestProductSearch:
    def test_search_returns_results(self, authenticated_page: Page):
        products = ProductsPage(authenticated_page)
        products.page.goto("/products")
        products.search("widget").expect_product_count(3)

    def test_add_to_cart(self, authenticated_page: Page):
        products = ProductsPage(authenticated_page)
        products.page.goto("/products")
        products.add_first_to_cart()

        # Verify cart badge
        cart_badge = authenticated_page.locator('[data-testid="cart-count"]')
        expect(cart_badge).to_have_text("1")

    def test_visual_regression(self, page: Page):
        page.goto("/products")
        expect(page).to_have_screenshot("products-page.png", max_diff_pixels=100)


class TestAccessibility:
    def test_login_page_accessible(self, page: Page):
        page.goto("/login")
        # Check tab navigation
        page.keyboard.press("Tab")
        expect(page.locator('[data-testid="email"]')).to_be_focused()
        page.keyboard.press("Tab")
        expect(page.locator('[data-testid="password"]')).to_be_focused()

    def test_no_axe_violations(self, page: Page):
        from axe_playwright_python.sync_playwright import Axe
        page.goto("/login")
        results = Axe().run(page)
        assert len(results.violations) == 0, (
            f"Accessibility violations: {results.violations}"
        )
```

E2E testing patterns:
1. **Page Object Model** — encapsulate selectors and actions per page
2. **`data-testid`** — stable selectors that don't break with styling changes
3. **Fixtures** — reusable setup (authenticated state, seeded data)
4. **Visual regression** — screenshot comparison catches UI regressions
5. **`expect`** — auto-waiting assertions (no manual `sleep` or `waitFor`)'''
    ),
    (
        "testing/property-based",
        "Show property-based testing with Hypothesis: strategies, stateful testing, and finding edge cases.",
        '''Property-based testing with Hypothesis:

```python
from hypothesis import given, assume, settings, example, HealthCheck
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant, initialize
import pytest


# --- Basic property tests ---

@given(st.lists(st.integers()))
def test_sort_idempotent(xs):
    """Sorting twice gives same result as sorting once."""
    assert sorted(sorted(xs)) == sorted(xs)

@given(st.lists(st.integers(), min_size=1))
def test_sort_preserves_length(xs):
    assert len(sorted(xs)) == len(xs)

@given(st.lists(st.integers(), min_size=1))
def test_sort_min_is_first(xs):
    assert sorted(xs)[0] == min(xs)


# --- Custom strategies ---

@st.composite
def valid_email(draw):
    local = draw(st.from_regex(r"[a-z][a-z0-9._]{1,20}", fullmatch=True))
    domain = draw(st.from_regex(r"[a-z]{2,10}\.[a-z]{2,4}", fullmatch=True))
    return f"{local}@{domain}"

@st.composite
def money_amount(draw):
    """Generate valid money amounts (2 decimal places)."""
    amount = draw(st.decimals(min_value=0, max_value=99999,
                              places=2, allow_nan=False, allow_infinity=False))
    return float(amount)

@st.composite
def user_data(draw):
    return {
        "name": draw(st.text(min_size=1, max_size=50,
                             alphabet=st.characters(whitelist_categories=("L",)))),
        "email": draw(valid_email()),
        "age": draw(st.integers(min_value=18, max_value=120)),
    }


# --- Testing with custom strategies ---

@given(user_data())
def test_user_creation_roundtrip(data):
    """Create user and verify all fields preserved."""
    user = User.from_dict(data)
    result = user.to_dict()
    assert result["name"] == data["name"]
    assert result["email"] == data["email"]
    assert result["age"] == data["age"]


@given(st.text(), st.text())
def test_json_roundtrip(key, value):
    """JSON encode/decode preserves data."""
    import json
    assume(key)  # Skip empty keys
    original = {key: value}
    assert json.loads(json.dumps(original)) == original


@given(money_amount(), money_amount())
def test_money_addition_commutative(a, b):
    """a + b == b + a for money."""
    assert abs(Money(a) + Money(b) - (Money(b) + Money(a))) < 0.01


# --- Stateful testing (finds sequence bugs) ---

class ShoppingCartStateMachine(RuleBasedStateMachine):
    """Test shopping cart with random operation sequences."""

    @initialize()
    def init_cart(self):
        self.cart = ShoppingCart()
        self.expected_items: dict[str, int] = {}

    @rule(product_id=st.text(min_size=1, max_size=10,
                             alphabet="abcdef"),
          quantity=st.integers(min_value=1, max_value=10))
    def add_item(self, product_id, quantity):
        self.cart.add(product_id, quantity)
        self.expected_items[product_id] = (
            self.expected_items.get(product_id, 0) + quantity
        )

    @rule(data=st.data())
    def remove_item(self, data):
        if not self.expected_items:
            return
        product_id = data.draw(st.sampled_from(list(self.expected_items.keys())))
        self.cart.remove(product_id)
        del self.expected_items[product_id]

    @invariant()
    def items_match(self):
        """Cart contents always match expected state."""
        for product_id, qty in self.expected_items.items():
            assert self.cart.get_quantity(product_id) == qty

    @invariant()
    def count_is_correct(self):
        assert self.cart.total_items() == sum(self.expected_items.values())

TestShoppingCart = ShoppingCartStateMachine.TestCase


# --- Settings for CI ---

@settings(
    max_examples=500,          # More examples in CI
    deadline=1000,             # 1 second per example
    suppress_health_check=[HealthCheck.too_slow],
)
@given(st.lists(st.integers(), max_size=10000))
def test_sort_large_lists(xs):
    result = sorted(xs)
    # Verify sorted property
    for i in range(len(result) - 1):
        assert result[i] <= result[i + 1]


# --- Example annotations (always test specific cases) ---

@given(st.integers(), st.integers())
@example(0, 0)
@example(1, -1)
@example(2**31, 2**31)
def test_addition_commutative(a, b):
    assert a + b == b + a
```

Property-based testing patterns:
1. **Property assertions** — verify invariants that hold for ALL inputs
2. **Custom strategies** — `@st.composite` for domain-specific data generation
3. **`assume()`** — filter invalid inputs without failing
4. **Stateful testing** — find bugs from random operation sequences
5. **Shrinking** — Hypothesis automatically finds minimal failing input'''
    ),
    (
        "testing/load-testing",
        "Show load testing patterns with Locust: user scenarios, custom shapes, and performance assertions.",
        '''Load testing with Locust:

```python
from locust import HttpUser, task, between, events, tag
from locust import LoadTestShape
import json
import random
import time
import logging

logger = logging.getLogger(__name__)


# --- User behavior scenarios ---

class WebsiteUser(HttpUser):
    """Simulates typical website user behavior."""
    wait_time = between(1, 5)  # Think time between requests

    def on_start(self):
        """Login on start."""
        response = self.client.post("/api/auth/login", json={
            "email": f"user{random.randint(1, 1000)}@test.com",
            "password": "testpass123",
        })
        if response.ok:
            self.token = response.json()["token"]
            self.client.headers["Authorization"] = f"Bearer {self.token}"

    @task(5)  # Weight: 5x more likely than weight-1 tasks
    @tag("read")
    def browse_products(self):
        page = random.randint(1, 10)
        self.client.get(f"/api/products?page={page}&limit=20",
                       name="/api/products?page=[N]")

    @task(3)
    @tag("read")
    def view_product(self):
        product_id = random.randint(1, 100)
        self.client.get(f"/api/products/{product_id}",
                       name="/api/products/[id]")

    @task(2)
    @tag("read")
    def search_products(self):
        queries = ["widget", "gadget", "tool", "sensor", "cable"]
        query = random.choice(queries)
        self.client.get(f"/api/products/search?q={query}",
                       name="/api/products/search")

    @task(1)
    @tag("write")
    def add_to_cart(self):
        product_id = random.randint(1, 100)
        self.client.post("/api/cart/items", json={
            "product_id": product_id,
            "quantity": random.randint(1, 3),
        })

    @task(1)
    @tag("write")
    def checkout(self):
        with self.client.post("/api/orders", json={
            "shipping_address": {
                "street": "123 Test St",
                "city": "Portland",
                "state": "OR",
                "zip": "97201",
            }
        }, catch_response=True) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 400:
                response.failure("Cart was empty")
            else:
                response.failure(f"Unexpected: {response.status_code}")


class APIUser(HttpUser):
    """Simulates API integration partner."""
    wait_time = between(0.1, 0.5)  # Faster than human users

    def on_start(self):
        self.client.headers["X-API-Key"] = "test-api-key-123"

    @task
    def batch_query(self):
        ids = random.sample(range(1, 1000), 20)
        self.client.post("/api/products/batch", json={"ids": ids})


# --- Custom load shape ---

class StepLoadShape(LoadTestShape):
    """Gradually increase load in steps."""

    stages = [
        {"duration": 60, "users": 10, "spawn_rate": 2},
        {"duration": 120, "users": 50, "spawn_rate": 5},
        {"duration": 180, "users": 100, "spawn_rate": 10},
        {"duration": 300, "users": 200, "spawn_rate": 20},
        {"duration": 360, "users": 50, "spawn_rate": 50},  # Scale down
        {"duration": 420, "users": 0, "spawn_rate": 50},   # Stop
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None


class SpikeLoadShape(LoadTestShape):
    """Simulate traffic spike."""

    def tick(self):
        run_time = self.get_run_time()

        if run_time < 30:
            return (10, 5)      # Warm up
        elif run_time < 60:
            return (200, 100)   # Spike!
        elif run_time < 120:
            return (10, 50)     # Drop back
        elif run_time < 150:
            return (200, 100)   # Second spike
        elif run_time < 210:
            return (10, 50)     # Cool down
        return None


# --- Performance assertions (for CI) ---

@events.quitting.add_listener
def check_results(environment, **kwargs):
    """Assert performance SLOs after test."""
    stats = environment.runner.stats

    # Overall stats
    total = stats.total
    fail_ratio = total.fail_ratio

    # P95 response time
    p95 = total.get_response_time_percentile(0.95) or 0
    p99 = total.get_response_time_percentile(0.99) or 0
    avg = total.avg_response_time

    logger.info(f"Results: avg={avg:.0f}ms p95={p95:.0f}ms "
                f"p99={p99:.0f}ms errors={fail_ratio:.1%}")

    # SLO checks
    if fail_ratio > 0.01:  # Error rate < 1%
        environment.process_exit_code = 1
        logger.error(f"FAIL: Error rate {fail_ratio:.1%} > 1%")

    if p95 > 500:  # P95 < 500ms
        environment.process_exit_code = 1
        logger.error(f"FAIL: P95 {p95:.0f}ms > 500ms")

    if p99 > 2000:  # P99 < 2s
        environment.process_exit_code = 1
        logger.error(f"FAIL: P99 {p99:.0f}ms > 2000ms")


# Run: locust -f locustfile.py --host=http://localhost:8000
# Headless: locust -f locustfile.py --headless -u 100 -r 10 --run-time 5m
```

Load testing patterns:
1. **Weighted tasks** — `@task(weight)` for realistic traffic distribution
2. **Parameterized URLs** — `name=` parameter to group similar endpoints
3. **Custom shapes** — step ramp, spike, or custom traffic patterns
4. **`catch_response`** — validate response content, not just status code
5. **CI assertions** — fail pipeline if P95, error rate exceed SLOs'''
    ),
]
"""
