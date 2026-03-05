"""Advanced testing patterns — property-based, mutation, contract, snapshot, load testing."""

PAIRS = [
    (
        "testing/property-based-testing",
        "Explain property-based testing with Hypothesis in Python. Show how to define strategies, use @given, and find edge cases that unit tests miss.",
        '''Property-based testing generates random inputs to verify invariants rather than testing specific examples:

```python
from hypothesis import given, settings, assume, example
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, precondition
import json

# --- Basic property-based tests ---

@given(st.lists(st.integers()))
def test_sort_idempotent(xs):
    """Sorting twice gives same result as sorting once."""
    assert sorted(sorted(xs)) == sorted(xs)

@given(st.lists(st.integers(), min_size=1))
def test_sort_preserves_length(xs):
    assert len(sorted(xs)) == len(xs)

@given(st.lists(st.integers(), min_size=1))
def test_sort_min_first(xs):
    assert sorted(xs)[0] == min(xs)

# --- Custom strategies ---

@st.composite
def json_documents(draw):
    """Generate valid JSON-like nested structures."""
    key = draw(st.text(min_size=1, max_size=10,
                       alphabet=st.characters(whitelist_categories=("L", "N"))))
    value = draw(st.one_of(
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=50),
        st.booleans(),
        st.none(),
    ))
    return {key: value}

@given(json_documents())
def test_json_roundtrip(doc):
    """JSON serialize then deserialize preserves structure."""
    assert json.loads(json.dumps(doc)) == doc

# --- Testing with assume() for preconditions ---

@given(st.integers(), st.integers())
def test_division_inverse(x, y):
    assume(y != 0)
    assume(x % y == 0)  # Only test clean divisions
    assert (x // y) * y == x

# --- Explicit examples + fuzzing ---

@example("", "")
@example("hello", "hello")
@given(st.text(), st.text())
def test_string_concat_length(a, b):
    assert len(a + b) == len(a) + len(b)

# --- Stateful testing (model-based) ---

class SetModel(RuleBasedStateMachine):
    """Test a set implementation against a known-good model."""

    def __init__(self):
        super().__init__()
        self.model = set()       # Known-good
        self.actual = set()      # System under test

    @rule(value=st.integers())
    def add_element(self, value):
        self.model.add(value)
        self.actual.add(value)
        assert self.model == self.actual

    @rule(value=st.integers())
    def discard_element(self, value):
        self.model.discard(value)
        self.actual.discard(value)
        assert self.model == self.actual

    @rule()
    def check_length(self):
        assert len(self.model) == len(self.actual)

TestSetModel = SetModel.TestCase

# --- Settings and profiles ---

from hypothesis import Phase, HealthCheck

@settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
    phases=[Phase.explicit, Phase.generate, Phase.shrink],
)
@given(st.binary(min_size=1, max_size=1024))
def test_compression_roundtrip(data):
    import zlib
    assert zlib.decompress(zlib.compress(data)) == data
```

Key properties to test:
- **Roundtrip**: encode(decode(x)) == x (JSON, compression, serialization)
- **Idempotency**: f(f(x)) == f(x) (sorting, normalization, formatting)
- **Invariants**: sorted output length == input length, all elements present
- **Commutativity**: f(a, b) == f(b, a) where applicable
- **Model-based**: compare implementation against simple reference

Hypothesis shines at finding edge cases: empty inputs, large numbers, Unicode surrogates,
boundary values that hand-written tests miss. The shrinking phase minimizes failing examples
to the simplest reproduction case.'''
    ),
    (
        "testing/mutation-testing",
        "Explain mutation testing concepts and how to use mutmut in Python. Show how it measures test suite quality beyond code coverage.",
        '''Mutation testing injects small bugs (mutants) into your code and checks if tests catch them:

```python
# --- Source code: calculator.py ---
def discount_price(price: float, discount_pct: float) -> float:
    """Apply percentage discount, minimum price is 0."""
    if discount_pct < 0 or discount_pct > 100:
        raise ValueError("Discount must be 0-100")
    result = price * (1 - discount_pct / 100)
    return max(result, 0.0)

def categorize_age(age: int) -> str:
    if age < 0:
        raise ValueError("Age cannot be negative")
    if age < 13:
        return "child"
    elif age < 18:
        return "teenager"
    elif age < 65:
        return "adult"
    else:
        return "senior"

# --- Tests that look good but have gaps ---
# test_calculator.py

def test_discount_basic():
    assert discount_price(100, 10) == 90.0

def test_discount_zero():
    assert discount_price(100, 0) == 100.0

def test_age_child():
    assert categorize_age(5) == "child"

def test_age_adult():
    assert categorize_age(30) == "adult"

# Coverage: 100% line coverage! But...
# Mutation testing reveals:
#   - Mutant: change `< 0` to `<= 0` in discount — SURVIVES (no test for 0%)
#   - Mutant: change `< 13` to `< 14` — SURVIVES (no boundary test at 12/13)
#   - Mutant: change `< 18` to `< 17` — SURVIVES (no test at 17/18)
#   - Mutant: change `max(result, 0.0)` to `result` — SURVIVES (no test for >100%)

# --- Improved tests that kill mutants ---

import pytest

def test_discount_full():
    assert discount_price(100, 100) == 0.0

def test_discount_boundary():
    assert discount_price(100, 50) == 50.0

def test_discount_negative_rejected():
    with pytest.raises(ValueError):
        discount_price(100, -1)

def test_discount_over_100_rejected():
    with pytest.raises(ValueError):
        discount_price(100, 101)

def test_discount_zero_discount():
    # Kills the <= vs < mutant
    assert discount_price(100, 0) == 100.0

# Boundary tests for age categories
def test_age_boundary_child_teen():
    assert categorize_age(12) == "child"
    assert categorize_age(13) == "teenager"

def test_age_boundary_teen_adult():
    assert categorize_age(17) == "teenager"
    assert categorize_age(18) == "adult"

def test_age_boundary_adult_senior():
    assert categorize_age(64) == "adult"
    assert categorize_age(65) == "senior"
```

Using mutmut:
```bash
# Install
pip install mutmut

# Run mutation testing
mutmut run --paths-to-mutate=calculator.py --tests-dir=tests/

# View results
mutmut results
# Survived: 2  Killed: 15  Timeout: 1

# Inspect surviving mutants
mutmut show 3
# --- calculator.py
# -    if age < 13:
# +    if age < 14:

# Apply a mutant to understand it
mutmut apply 3
# ... fix tests, then:
mutmut run --rerun-surviving
```

Common mutation operators:
- **Boundary**: `<` → `<=`, `>` → `>=`
- **Negate conditionals**: `==` → `!=`, `<` → `>=`
- **Arithmetic**: `+` → `-`, `*` → `/`
- **Remove statements**: delete return, delete method call
- **Constants**: `0` → `1`, `True` → `False`

Mutation score = killed mutants / total mutants. Aim for >80%.
100% line coverage with 60% mutation score means your tests verify the code runs
but don't assert correct behavior at boundaries.'''
    ),
    (
        "testing/contract-testing",
        "Explain consumer-driven contract testing for microservices using Pact. Show how to define contracts, verify providers, and handle breaking changes.",
        '''Contract testing verifies API agreements between services without full integration tests:

```python
# Consumer side — defines expectations
# test_consumer_contract.py

import atexit
import unittest
from pact import Consumer, Provider

pact = Consumer("OrderService").has_pact_with(
    Provider("UserService"),
    pact_dir="./pacts",
    log_dir="./logs",
)
pact.start_service()
atexit.register(pact.stop_service)

class TestUserServiceContract(unittest.TestCase):

    def test_get_user(self):
        """OrderService expects UserService to return user details."""
        expected = {
            "id": 123,
            "name": "Alice",
            "email": "alice@example.com",
            "tier": "premium",
        }

        (pact
         .given("user 123 exists")
         .upon_receiving("a request for user 123")
         .with_request("GET", "/users/123",
                       headers={"Accept": "application/json"})
         .will_respond_with(200,
                            headers={"Content-Type": "application/json"},
                            body={
                                "id": 123,         # Exact match
                                "name": "Alice",    # Exact match
                                "email": Like("alice@example.com"),  # Type match
                                "tier": Term(r"free|premium|enterprise", "premium"),
                            }))

        with pact:
            # Your actual HTTP client code
            import requests
            result = requests.get(pact.uri + "/users/123",
                                  headers={"Accept": "application/json"})
            assert result.status_code == 200
            data = result.json()
            assert data["id"] == 123
            assert data["tier"] in ("free", "premium", "enterprise")

    def test_user_not_found(self):
        (pact
         .given("user 999 does not exist")
         .upon_receiving("a request for non-existent user")
         .with_request("GET", "/users/999")
         .will_respond_with(404,
                            body={"error": Like("not found")}))

        with pact:
            result = requests.get(pact.uri + "/users/999")
            assert result.status_code == 404

# --- Provider side verification ---
# test_provider_verify.py

from pact import Verifier

def test_user_service_honors_contracts():
    verifier = Verifier(
        provider="UserService",
        provider_base_url="http://localhost:8080",
    )

    # Provider states setup
    verifier.provider_states_setup_url = "http://localhost:8080/_pact/setup"

    output, logs = verifier.verify_pacts(
        "./pacts/orderservice-userservice.json",
        enable_pending=True,      # New contracts don't break CI
        include_wip_pacts_since="2024-01-01",
    )
    assert output == 0

# --- Provider state handler (in your test server) ---
# Flask example

from flask import Flask, request, jsonify

app = Flask(__name__)
test_users = {}

@app.route("/_pact/setup", methods=["POST"])
def provider_state():
    state = request.json
    if state["state"] == "user 123 exists":
        test_users[123] = {
            "id": 123, "name": "Alice",
            "email": "alice@example.com", "tier": "premium"
        }
    elif state["state"] == "user 999 does not exist":
        test_users.pop(999, None)
    return jsonify({"status": "ok"})

@app.route("/users/<int:user_id>")
def get_user(user_id):
    user = test_users.get(user_id)
    if not user:
        return jsonify({"error": "not found"}), 404
    return jsonify(user)
```

Workflow:
1. **Consumer writes contract** → generates Pact JSON
2. **Publish to Pact Broker** → `pact-broker publish ./pacts --consumer-app-version=$(git rev-parse HEAD)`
3. **Provider verifies** → runs against real provider with test data
4. **Can I Deploy?** → `pact-broker can-i-deploy --pacticipant=OrderService --version=$(git rev-parse HEAD)`

Handling breaking changes:
- Provider adds field → safe (consumers ignore unknown fields)
- Provider removes field → BREAKING (check `can-i-deploy` first)
- Provider changes type → BREAKING (contract verification catches it)
- Use `pending pacts` for new consumers to avoid blocking provider deploys'''
    ),
    (
        "testing/load-testing",
        "Show how to do load testing with Locust in Python. Include user behavior modeling, custom shapes, and result analysis.",
        '''Locust enables load testing with Python-defined user behaviors:

```python
# locustfile.py
from locust import HttpUser, task, between, events, tag
from locust import LoadTestShape
import json
import random
import logging

class WebsiteUser(HttpUser):
    """Simulates realistic user browsing patterns."""
    wait_time = between(1, 3)  # Think time between requests
    host = "http://localhost:8000"

    def on_start(self):
        """Login when user starts."""
        resp = self.client.post("/auth/login", json={
            "username": f"user_{random.randint(1, 1000)}",
            "password": "testpass123",
        })
        if resp.status_code == 200:
            self.token = resp.json()["token"]
            self.client.headers["Authorization"] = f"Bearer {self.token}"
        else:
            logging.warning(f"Login failed: {resp.status_code}")

    @task(10)
    @tag("browse")
    def browse_products(self):
        """Most common action — browse product list."""
        page = random.randint(1, 10)
        with self.client.get(
            f"/api/products?page={page}&limit=20",
            name="/api/products?page=[n]",  # Group in stats
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if len(data["items"]) == 0:
                    resp.failure("Empty product list")
            else:
                resp.failure(f"Status {resp.status_code}")

    @task(5)
    @tag("browse")
    def view_product_detail(self):
        product_id = random.randint(1, 500)
        self.client.get(
            f"/api/products/{product_id}",
            name="/api/products/[id]",
        )

    @task(2)
    @tag("purchase")
    def add_to_cart(self):
        self.client.post("/api/cart/items", json={
            "product_id": random.randint(1, 500),
            "quantity": random.randint(1, 3),
        })

    @task(1)
    @tag("purchase")
    def checkout(self):
        """Least common but most critical path."""
        self.client.post("/api/checkout", json={
            "payment_method": "card",
            "shipping": "standard",
        })

# --- Custom load shape ---

class StepLoadShape(LoadTestShape):
    """Step-up load: increase users every 30 seconds."""
    step_time = 30      # Seconds per step
    step_load = 10      # Users added per step
    spawn_rate = 10     # Users spawned per second
    time_limit = 300    # Total test duration

    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.time_limit:
            return None  # Stop test

        current_step = run_time // self.step_time + 1
        return (current_step * self.step_load, self.spawn_rate)

class SpikeLoadShape(LoadTestShape):
    """Simulate traffic spike — normal, spike, normal."""
    stages = [
        {"duration": 60, "users": 50, "spawn_rate": 10},    # Warm up
        {"duration": 30, "users": 500, "spawn_rate": 50},   # Spike!
        {"duration": 60, "users": 50, "spawn_rate": 10},    # Recovery
        {"duration": 30, "users": 500, "spawn_rate": 50},   # Second spike
        {"duration": 120, "users": 50, "spawn_rate": 10},   # Cool down
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
            run_time -= stage["duration"]
        return None

# --- Event hooks for custom metrics ---

from locust import events
import time

@events.request.add_listener
def on_request(request_type, name, response_time, response_length,
               response, exception, context, **kwargs):
    if response_time > 2000:  # Log slow requests
        logging.warning(f"SLOW: {request_type} {name} took {response_time}ms")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.runner.stats
    total = stats.total
    print(f"\\nResults Summary:")
    print(f"  Requests: {total.num_requests}")
    print(f"  Failures: {total.num_failures}")
    print(f"  Median response: {total.median_response_time}ms")
    print(f"  95th percentile: {total.get_response_time_percentile(0.95)}ms")
    print(f"  99th percentile: {total.get_response_time_percentile(0.99)}ms")
    print(f"  RPS: {total.total_rps:.1f}")

    if total.fail_ratio > 0.01:
        logging.error(f"Failure rate {total.fail_ratio:.2%} exceeds 1% threshold!")
```

Running:
```bash
# Web UI mode (interactive)
locust -f locustfile.py --host=http://localhost:8000

# Headless mode (CI/CD)
locust -f locustfile.py --headless \\
    --users 100 --spawn-rate 10 --run-time 5m \\
    --csv=results --html=report.html

# Distributed mode
locust -f locustfile.py --master
locust -f locustfile.py --worker --master-host=master-ip

# Run only tagged tests
locust -f locustfile.py --tags purchase
```

Key metrics to watch:
- **p95/p99 latency** — more important than average
- **Error rate** — should stay <1% under expected load
- **Throughput** — requests/second at target user count
- **Response time distribution** — bimodal = caching issue'''
    ),
    (
        "testing/snapshot-testing",
        "Explain snapshot testing patterns in Python. Show how to implement snapshot tests for API responses, HTML rendering, and data transformations.",
        '''Snapshot testing captures expected output and detects regressions automatically:

```python
# Using syrupy (pytest snapshot plugin)
# pip install syrupy

import pytest
import json
from datetime import datetime
from unittest.mock import patch

# --- API response snapshot testing ---

def test_user_api_response(snapshot, client):
    """Snapshot entire API response structure."""
    response = client.get("/api/users/1")
    data = response.json()

    # Exclude volatile fields
    data.pop("created_at", None)
    data.pop("request_id", None)

    assert data == snapshot

# --- Snapshot with custom serializer ---

from syrupy.extensions.json import JSONSnapshotExtension

@pytest.fixture
def snapshot_json(snapshot):
    return snapshot.use_extension(JSONSnapshotExtension)

def test_product_catalog(snapshot_json, db_session):
    products = get_catalog(category="electronics", limit=5)
    serialized = [
        {
            "name": p.name,
            "price": str(p.price),
            "in_stock": p.in_stock,
            "tags": sorted(p.tags),
        }
        for p in products
    ]
    assert serialized == snapshot_json

# --- HTML rendering snapshot ---

def test_email_template(snapshot):
    html = render_email_template(
        template="welcome",
        context={
            "user_name": "Alice",
            "activation_url": "https://example.com/activate/abc123",
        },
    )
    assert html == snapshot

# --- Data transformation snapshots ---

def test_csv_to_report(snapshot, tmp_path):
    csv_data = """name,sales,region
Alice,150,North
Bob,200,South
Carol,175,North"""

    input_file = tmp_path / "sales.csv"
    input_file.write_text(csv_data)

    report = generate_sales_report(str(input_file))
    assert report == snapshot

# --- Custom snapshot matcher for partial matching ---

from syrupy.matchers import path_type, path_value

def test_order_response_partial(snapshot):
    """Match structure but allow dynamic values."""
    order = create_order(items=[{"sku": "ABC", "qty": 2}])

    assert order == snapshot(
        matcher=path_type({
            "id": (str,),
            "created_at": (str,),
            "total": (float, int),
        })
    )

# --- Manual snapshot testing (no framework) ---

import hashlib
from pathlib import Path

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"

def assert_snapshot(data, name: str, update: bool = False):
    """Simple DIY snapshot testing."""
    snapshot_file = SNAPSHOT_DIR / f"{name}.json"
    serialized = json.dumps(data, indent=2, sort_keys=True, default=str)

    if update or not snapshot_file.exists():
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        snapshot_file.write_text(serialized)
        return

    expected = snapshot_file.read_text()
    if serialized != expected:
        # Show diff
        import difflib
        diff = difflib.unified_diff(
            expected.splitlines(keepends=True),
            serialized.splitlines(keepends=True),
            fromfile=f"snapshot/{name}",
            tofile="actual",
        )
        raise AssertionError(
            f"Snapshot mismatch for '{name}':\\n" + "".join(diff)
        )

# Usage:
def test_data_pipeline():
    result = transform_pipeline(raw_data)
    assert_snapshot(result, "pipeline_output")

# Update snapshots:
# pytest --snapshot-update   (syrupy)
# UPDATE_SNAPSHOTS=1 pytest  (custom)
```

When to use snapshot tests:
- **API contracts** — detect unintended response changes
- **Rendered output** — HTML, emails, PDF text content
- **Data transformations** — ETL pipeline outputs
- **Serialization** — config file generation, SQL query building
- **CLI output** — command-line tool formatted output

When NOT to use snapshots:
- Highly dynamic output (timestamps, random IDs) — filter them first
- Simple assertions where explicit checks are clearer
- Performance-sensitive tests (snapshot comparison adds overhead)'''
    ),
]
