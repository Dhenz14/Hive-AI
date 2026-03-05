"""Testing — contract testing, snapshot testing, fuzzing, and test architecture."""

PAIRS = [
    (
        "testing/contract-testing",
        "Show contract testing patterns: Pact consumer/provider tests, schema validation, and API compatibility.",
        '''Contract testing patterns:

```python
# --- Consumer-driven contract test with Pact ---

import pytest
from pact import Consumer, Provider
from pact.matchers import Like, EachLike, Term
import requests


# Consumer side: define expected interactions

@pytest.fixture(scope="session")
def pact():
    """Set up Pact mock provider."""
    pact = Consumer("OrderService").has_pact_with(
        Provider("UserService"),
        host_name="localhost",
        port=1234,
    )
    pact.start_service()
    yield pact
    pact.stop_service()


def test_get_user(pact):
    """Consumer test: OrderService expects this response from UserService."""

    # Define expected interaction
    (pact
     .given("user 123 exists")
     .upon_receiving("a request for user 123")
     .with_request("GET", "/api/users/123")
     .will_respond_with(200, body={
         "id": Like("123"),
         "name": Like("John Doe"),
         "email": Term(r".+@.+\\..+", "john@example.com"),
         "tier": Term(r"free|pro|enterprise", "pro"),
         "addresses": EachLike({
             "street": Like("123 Main St"),
             "city": Like("Seattle"),
             "zip": Like("98101"),
         }),
     }))

    # Consumer code under test
    with pact:
        result = requests.get(f"{pact.uri}/api/users/123")
        assert result.status_code == 200
        user = result.json()
        assert "id" in user
        assert "@" in user["email"]

    # Pact file generated: orderservice-userservice.json
    # Ship this to provider for verification


# --- Provider verification ---

# Provider side: verify against consumer contracts

# @pytest.fixture
# def provider_states():
#     """Set up provider states for verification."""
#     return {
#         "user 123 exists": lambda: create_test_user(id="123"),
#         "no users exist": lambda: clear_all_users(),
#     }

# def test_provider_honors_contracts():
#     verifier = Verifier(provider="UserService",
#                         provider_base_url="http://localhost:8000")
#     output, _ = verifier.verify_pacts(
#         "./pacts/orderservice-userservice.json",
#         provider_states_setup_url="http://localhost:8000/_pact/setup",
#     )
#     assert output == 0


# --- Schema-based contract validation ---

from pydantic import BaseModel
from typing import Optional
import json


class UserContractV1(BaseModel):
    """API contract — breaking changes need major version bump."""
    id: str
    name: str
    email: str


class UserContractV2(UserContractV1):
    """V2 adds optional fields (backward compatible)."""
    tier: Optional[str] = None
    avatar_url: Optional[str] = None


def validate_response_contract(response_data: dict, version: int = 1):
    """Validate API response matches contract."""
    contracts = {1: UserContractV1, 2: UserContractV2}
    contract = contracts.get(version, UserContractV2)
    return contract.model_validate(response_data)


# --- Breaking change detection ---

def check_backward_compatibility(old_schema: dict, new_schema: dict) -> list[str]:
    """Check if schema change is backward compatible."""
    breaking_changes = []

    old_required = set(old_schema.get("required", []))
    new_required = set(new_schema.get("required", []))

    # New required fields = breaking
    added_required = new_required - old_required
    if added_required:
        breaking_changes.append(
            f"New required fields: {added_required}"
        )

    # Removed fields = breaking
    old_props = set(old_schema.get("properties", {}).keys())
    new_props = set(new_schema.get("properties", {}).keys())
    removed = old_props - new_props
    if removed:
        breaking_changes.append(f"Removed fields: {removed}")

    # Type changes = breaking
    for field in old_props & new_props:
        old_type = old_schema["properties"][field].get("type")
        new_type = new_schema["properties"][field].get("type")
        if old_type != new_type:
            breaking_changes.append(
                f"Type change for '{field}': {old_type} -> {new_type}"
            )

    return breaking_changes
```

Contract testing patterns:
1. **Consumer-driven contracts** — consumer defines expectations, provider verifies
2. **Pact matchers** — `Like` (type matching), `Term` (regex), `EachLike` (array)
3. **Provider states** — set up test data matching consumer expectations
4. **Schema evolution** — new optional fields are safe, new required fields break
5. **Breaking change detection** — automated checks for removed fields, type changes'''
    ),
    (
        "testing/snapshot-testing",
        "Show snapshot testing patterns: pytest-snapshot, API response snapshots, and update workflows.",
        '''Snapshot testing patterns:

```python
import pytest
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Any


# --- Snapshot fixture ---

@dataclass
class SnapshotManager:
    """Manage test snapshots with auto-update support."""

    snapshot_dir: Path
    update: bool = False  # Set via --update-snapshots flag

    def assert_match(self, name: str, actual: Any,
                     serializer: str = "json") -> None:
        """Assert actual matches stored snapshot."""
        snapshot_file = self.snapshot_dir / f"{name}.snap"

        # Serialize actual value
        if serializer == "json":
            actual_str = json.dumps(actual, indent=2, sort_keys=True,
                                     default=str)
        elif serializer == "text":
            actual_str = str(actual)
        else:
            raise ValueError(f"Unknown serializer: {serializer}")

        if self.update or not snapshot_file.exists():
            # Create or update snapshot
            snapshot_file.parent.mkdir(parents=True, exist_ok=True)
            snapshot_file.write_text(actual_str, encoding="utf-8")
            if self.update:
                pytest.skip(f"Snapshot updated: {name}")
            return

        # Compare with stored snapshot
        expected_str = snapshot_file.read_text(encoding="utf-8")
        if actual_str != expected_str:
            # Show diff
            import difflib
            diff = difflib.unified_diff(
                expected_str.splitlines(keepends=True),
                actual_str.splitlines(keepends=True),
                fromfile=f"snapshot/{name}",
                tofile="actual",
            )
            diff_str = "".join(diff)
            pytest.fail(
                f"Snapshot mismatch for '{name}'.\\n"
                f"Run with --update-snapshots to update.\\n\\n"
                f"{diff_str}"
            )


@pytest.fixture
def snapshot(request, tmp_path_factory):
    """Snapshot fixture for tests."""
    test_dir = Path(request.fspath).parent / "__snapshots__"
    update = request.config.getoption("--update-snapshots", default=False)
    return SnapshotManager(snapshot_dir=test_dir, update=update)


# conftest.py:
# def pytest_addoption(parser):
#     parser.addoption("--update-snapshots", action="store_true")


# --- Usage in tests ---

class TestUserAPI:
    def test_list_users_response(self, client, snapshot):
        response = client.get("/api/users")
        assert response.status_code == 200

        # Snapshot the response structure (ignore dynamic fields)
        data = response.json()
        for user in data["users"]:
            user["id"] = "<UUID>"
            user["created_at"] = "<TIMESTAMP>"

        snapshot.assert_match("list_users", data)

    def test_user_detail_response(self, client, snapshot):
        response = client.get("/api/users/test-user-1")
        data = response.json()
        data["id"] = "<UUID>"
        data["created_at"] = "<TIMESTAMP>"

        snapshot.assert_match("user_detail", data)


    def test_error_response_format(self, client, snapshot):
        response = client.get("/api/users/nonexistent")
        assert response.status_code == 404
        snapshot.assert_match("user_not_found_error", response.json())


# --- HTML snapshot testing ---

def test_rendered_template(snapshot):
    from jinja2 import Template
    template = Template("<h1>{{ title }}</h1><p>{{ body }}</p>")
    rendered = template.render(title="Hello", body="World")
    snapshot.assert_match("rendered_template", rendered, serializer="text")


# --- Snapshot for complex objects ---

def normalize_for_snapshot(data: dict, ignore_keys: set = None) -> dict:
    """Remove dynamic fields before snapshot comparison."""
    ignore = ignore_keys or {"id", "created_at", "updated_at", "timestamp"}
    result = {}
    for key, value in data.items():
        if key in ignore:
            result[key] = f"<{key.upper()}>"
        elif isinstance(value, dict):
            result[key] = normalize_for_snapshot(value, ignore)
        elif isinstance(value, list):
            result[key] = [
                normalize_for_snapshot(v, ignore) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            result[key] = value
    return result
```

Snapshot testing patterns:
1. **First run creates** — snapshot auto-created on first test run
2. **Diff on mismatch** — unified diff shows exactly what changed
3. **`--update-snapshots`** — explicit flag to update all snapshots
4. **Normalize dynamic fields** — replace UUIDs/timestamps with placeholders
5. **Separate snapshot files** — stored in `__snapshots__/` for easy review in PRs'''
    ),
    (
        "testing/fuzzing-python",
        "Show fuzzing patterns in Python: Hypothesis property testing, structured fuzzing, and crash reproduction.",
        '''Fuzzing and property-based testing:

```python
import pytest
from hypothesis import given, settings, example, assume, HealthCheck
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize
import json
import re


# --- Property-based testing with Hypothesis ---

# Test that encode/decode are inverses
@given(st.text())
def test_json_roundtrip(text):
    """Any string can be JSON-encoded and decoded back."""
    encoded = json.dumps(text)
    decoded = json.loads(encoded)
    assert decoded == text


# Test with structured data
@given(st.dictionaries(
    keys=st.text(min_size=1, max_size=50),
    values=st.one_of(
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=200),
        st.booleans(),
        st.none(),
    ),
    max_size=20,
))
def test_dict_json_roundtrip(data):
    assert json.loads(json.dumps(data)) == data


# --- Testing parser with edge cases ---

def parse_email(email: str) -> tuple[str, str]:
    """Parse email into (local, domain)."""
    match = re.match(r'^([^@]+)@([^@]+)$', email)
    if not match:
        raise ValueError(f"Invalid email: {email}")
    return match.group(1), match.group(2)


@given(
    local=st.from_regex(r'[a-zA-Z0-9._%+-]+', fullmatch=True),
    domain=st.from_regex(r'[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}', fullmatch=True),
)
def test_parse_email_valid(local, domain):
    """Generated valid emails should parse correctly."""
    email = f"{local}@{domain}"
    parsed_local, parsed_domain = parse_email(email)
    assert parsed_local == local
    assert parsed_domain == domain


@given(st.text())
def test_parse_email_no_crash(text):
    """Parser should never crash — either return result or raise ValueError."""
    try:
        result = parse_email(text)
        assert isinstance(result, tuple)
        assert len(result) == 2
    except ValueError:
        pass  # Expected for invalid input


# --- Testing numeric functions ---

@given(st.lists(st.integers(min_value=-10**9, max_value=10**9), min_size=1))
def test_sort_properties(lst):
    """Sorted list should have specific properties."""
    sorted_lst = sorted(lst)
    # Same length
    assert len(sorted_lst) == len(lst)
    # Same elements
    assert sorted(lst) == sorted(sorted_lst)
    # Actually sorted
    for i in range(len(sorted_lst) - 1):
        assert sorted_lst[i] <= sorted_lst[i + 1]


@given(
    st.integers(min_value=0, max_value=10**6),
    st.integers(min_value=1, max_value=100),
)
def test_pagination_math(total, page_size):
    """Pagination should cover all items exactly once."""
    total_pages = (total + page_size - 1) // page_size
    items_covered = sum(
        min(page_size, total - i * page_size)
        for i in range(total_pages)
    )
    assert items_covered == total


# --- Stateful testing (test sequences of operations) ---

class ShoppingCartMachine(RuleBasedStateMachine):
    """Test shopping cart with random operation sequences."""

    @initialize()
    def init_cart(self):
        self.cart = {}  # product_id -> quantity
        self.model = {}  # Simple dict model for comparison

    @rule(product=st.text(min_size=1, max_size=10),
          qty=st.integers(min_value=1, max_value=100))
    def add_item(self, product, qty):
        self.cart[product] = self.cart.get(product, 0) + qty
        self.model[product] = self.model.get(product, 0) + qty
        assert self.cart == self.model

    @rule(product=st.text(min_size=1, max_size=10))
    def remove_item(self, product):
        self.cart.pop(product, None)
        self.model.pop(product, None)
        assert self.cart == self.model

    @rule()
    def check_total(self):
        assert sum(self.cart.values()) == sum(self.model.values())

    @rule()
    def clear_cart(self):
        self.cart.clear()
        self.model.clear()
        assert self.cart == self.model

TestShoppingCart = ShoppingCartMachine.TestCase


# --- Custom strategies ---

email_strategy = st.builds(
    lambda local, domain: f"{local}@{domain}",
    local=st.from_regex(r'[a-z]{1,20}', fullmatch=True),
    domain=st.sampled_from(["example.com", "test.org", "mail.co"]),
)

user_strategy = st.fixed_dictionaries({
    "name": st.text(min_size=1, max_size=50,
                    alphabet=st.characters(whitelist_categories=("L", "Zs"))),
    "email": email_strategy,
    "age": st.integers(min_value=13, max_value=150),
})

@given(user=user_strategy)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_user_creation(user):
    """Any valid user data should create successfully."""
    result = create_user(**user)
    assert result["name"] == user["name"]
    assert result["email"] == user["email"].lower()
```

Fuzzing patterns:
1. **Roundtrip testing** — encode then decode should return original value
2. **No-crash testing** — function should never crash on any input
3. **Stateful testing** — `RuleBasedStateMachine` tests random operation sequences
4. **Custom strategies** — compose domain-specific generators from primitives
5. **`@example()`** — pin specific edge cases while still fuzzing randomly'''
    ),
]
