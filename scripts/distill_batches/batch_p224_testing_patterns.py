"""Advanced testing patterns — test doubles, snapshot testing, data builders, flaky test detection, and CI testing strategies."""

PAIRS = [
    (
        "testing/test-doubles",
        "Show how to use test doubles including mocks, stubs, fakes, and spies with practical examples and when to use each.",
        '''Test doubles — mocks, stubs, fakes, and spies with practical patterns:

```python
# --- test_doubles.py --- All four test double types ---

from __future__ import annotations

import abc
import time
from typing import Any, Optional, Protocol
from dataclasses import dataclass, field
from unittest.mock import Mock, MagicMock, patch, call


# === Domain interfaces ===

class EmailSender(Protocol):
    """Interface for sending emails."""
    def send(self, to: str, subject: str, body: str) -> bool: ...


class PaymentGateway(Protocol):
    """Interface for processing payments."""
    def charge(self, amount: float, token: str) -> dict: ...
    def refund(self, transaction_id: str, amount: float) -> dict: ...


class UserRepository(Protocol):
    """Interface for user persistence."""
    def find_by_id(self, user_id: int) -> Optional[dict]: ...
    def find_by_email(self, email: str) -> Optional[dict]: ...
    def save(self, user: dict) -> dict: ...
    def delete(self, user_id: int) -> bool: ...


# === 1. STUB — Returns pre-configured responses, no behavior verification ===

class StubPaymentGateway:
    """Stub: always returns a successful charge result.

    Use when: you need a dependency to return specific data
    but don't care if/how it was called.
    """

    def __init__(self, should_succeed: bool = True):
        self.should_succeed = should_succeed

    def charge(self, amount: float, token: str) -> dict:
        if self.should_succeed:
            return {"transaction_id": "TXN-STUB-001", "status": "approved"}
        return {"transaction_id": "", "status": "declined", "error": "insufficient_funds"}

    def refund(self, transaction_id: str, amount: float) -> dict:
        return {"refund_id": "REF-STUB-001", "status": "refunded"}


def test_order_total_with_payment_stub():
    """Stub lets us test order logic without real payment processing."""
    gateway = StubPaymentGateway(should_succeed=True)
    order_service = OrderService(gateway)

    result = order_service.place_order(user_id=1, items=[{"sku": "A", "price": 10}])

    assert result["status"] == "confirmed"
    assert result["total"] == 10.0
    # We don't verify gateway.charge was called — that's not the point


# === 2. MOCK — Verifies interactions (was it called? with what args?) ===

def test_order_sends_confirmation_email():
    """Mock verifies the email sender was called correctly."""
    email_sender = Mock(spec=EmailSender)
    email_sender.send.return_value = True

    order_service = OrderService(email_sender=email_sender)
    order_service.place_order(
        user_id=1,
        items=[{"sku": "A", "price": 25.0}],
        email="alice@example.com",
    )

    # Verify the interaction
    email_sender.send.assert_called_once_with(
        to="alice@example.com",
        subject="Order Confirmation",
        body=Mock(),  # any body
    )


def test_payment_retry_on_failure():
    """Mock verifies retry behavior."""
    gateway = Mock(spec=PaymentGateway)
    # First call fails, second succeeds
    gateway.charge.side_effect = [
        {"status": "declined", "error": "timeout"},
        {"status": "approved", "transaction_id": "TXN-002"},
    ]

    order_service = OrderService(gateway)
    result = order_service.place_order_with_retry(
        user_id=1, items=[{"sku": "A", "price": 50}], max_retries=3
    )

    assert result["status"] == "confirmed"
    assert gateway.charge.call_count == 2  # called twice


# === 3. FAKE — Working implementation with shortcuts ===

class FakeUserRepository:
    """Fake: in-memory implementation of UserRepository.

    Use when: you need realistic behavior but don't want a real database.
    Has real logic (find, save, delete) but stores data in a dict.
    """

    def __init__(self):
        self._users: dict[int, dict] = {}
        self._next_id: int = 1

    def find_by_id(self, user_id: int) -> Optional[dict]:
        return self._users.get(user_id)

    def find_by_email(self, email: str) -> Optional[dict]:
        for user in self._users.values():
            if user["email"] == email:
                return user
        return None

    def save(self, user: dict) -> dict:
        if "id" not in user:
            user["id"] = self._next_id
            self._next_id += 1
        self._users[user["id"]] = user
        return user

    def delete(self, user_id: int) -> bool:
        if user_id in self._users:
            del self._users[user_id]
            return True
        return False

    def count(self) -> int:
        return len(self._users)


def test_user_registration_with_fake_repo():
    """Fake repo lets us test full registration flow without a database."""
    repo = FakeUserRepository()
    service = UserService(repo)

    user = service.register("alice@example.com", "Alice")

    assert user["id"] == 1
    assert repo.find_by_email("alice@example.com") is not None
    assert repo.count() == 1

    # Test duplicate email detection
    with pytest.raises(ValueError, match="already registered"):
        service.register("alice@example.com", "Alice2")


# === 4. SPY — Records calls for later assertion ===

class SpyEmailSender:
    """Spy: wraps a real (or fake) sender and records all calls.

    Use when: you want to verify interactions AND have the real behavior run.
    """

    def __init__(self, real_sender: Optional[EmailSender] = None):
        self.calls: list[dict[str, Any]] = []
        self._real_sender = real_sender

    def send(self, to: str, subject: str, body: str) -> bool:
        self.calls.append({"to": to, "subject": subject, "body": body})
        if self._real_sender:
            return self._real_sender.send(to, subject, body)
        return True  # default success

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def was_called_with(self, **kwargs) -> bool:
        return any(
            all(call.get(k) == v for k, v in kwargs.items())
            for call in self.calls
        )


def test_bulk_notification_sends_to_all_users():
    """Spy records all emails sent during bulk notification."""
    spy = SpyEmailSender()
    notification_service = NotificationService(spy)

    notification_service.notify_all(
        user_emails=["a@test.com", "b@test.com", "c@test.com"],
        message="System maintenance tonight",
    )

    assert spy.call_count == 3
    assert spy.was_called_with(to="a@test.com")
    assert spy.was_called_with(to="b@test.com")
    assert spy.was_called_with(to="c@test.com")
    assert all("maintenance" in c["body"] for c in spy.calls)
```

```python
# --- unittest_mock_patterns.py --- Python unittest.mock patterns ---

from unittest.mock import Mock, MagicMock, patch, PropertyMock, AsyncMock
import pytest


# --- patch decorator (replace imports) ---

@patch("myapp.services.requests.get")
def test_external_api_call(mock_get):
    """Patch replaces the requests.get used inside myapp.services."""
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"data": "test"}

    result = my_service.fetch_external_data()

    assert result == {"data": "test"}
    mock_get.assert_called_once_with("https://api.example.com/data", timeout=10)


# --- patch as context manager ---

def test_with_context_manager():
    with patch("myapp.services.datetime") as mock_dt:
        mock_dt.utcnow.return_value = datetime(2024, 1, 15, 12, 0, 0)
        result = my_service.get_timestamp()
        assert result == "2024-01-15T12:00:00"


# --- AsyncMock for async code ---

@pytest.mark.asyncio
async def test_async_service():
    mock_client = AsyncMock()
    mock_client.fetch.return_value = {"status": "ok"}

    service = AsyncService(client=mock_client)
    result = await service.process()

    mock_client.fetch.assert_awaited_once()


# --- spec= for type-safe mocks ---

def test_spec_prevents_typos():
    mock_repo = Mock(spec=UserRepository)

    # This works — find_by_id exists on the spec
    mock_repo.find_by_id.return_value = {"id": 1, "name": "Alice"}

    # This raises AttributeError — find_by_nam doesn't exist
    # mock_repo.find_by_nam(1)  # AttributeError!
```

```python
# --- choosing_test_doubles.py --- Decision framework ---

from enum import Enum
from dataclasses import dataclass


class DoubleType(Enum):
    STUB = "stub"
    MOCK = "mock"
    FAKE = "fake"
    SPY = "spy"


@dataclass
class TestDoubleDecision:
    scenario: str
    recommended: DoubleType
    reason: str


DECISIONS = [
    TestDoubleDecision(
        "Need a dependency to return specific data",
        DoubleType.STUB,
        "Stubs provide canned responses without behavior verification",
    ),
    TestDoubleDecision(
        "Need to verify a method was called with specific arguments",
        DoubleType.MOCK,
        "Mocks verify interactions (call count, arguments, order)",
    ),
    TestDoubleDecision(
        "Need realistic behavior without infrastructure",
        DoubleType.FAKE,
        "Fakes are working implementations with shortcuts (in-memory DB)",
    ),
    TestDoubleDecision(
        "Need to observe calls while keeping real behavior",
        DoubleType.SPY,
        "Spies record calls and delegate to the real implementation",
    ),
    TestDoubleDecision(
        "Testing error handling paths",
        DoubleType.STUB,
        "Configure stub to return error responses or raise exceptions",
    ),
    TestDoubleDecision(
        "Testing a side-effect (email sent, event published)",
        DoubleType.MOCK,
        "Mock verifies the side-effect occurred without actually executing it",
    ),
    TestDoubleDecision(
        "Integration-style test without external services",
        DoubleType.FAKE,
        "Fakes let you test realistic flows (save then retrieve)",
    ),
]
```

| Double | Behavior | Verification | Complexity | When to use |
|--------|----------|-------------|-----------|-------------|
| Stub | Canned responses | None | Low | Return test data from dependencies |
| Mock | Configurable responses | Calls, args, order | Medium | Verify side effects occurred |
| Fake | Real logic, no infra | Via state inspection | High | Realistic flows without databases |
| Spy | Delegates to real impl | Records calls | Medium | Observe real behavior without changing it |

Key patterns:
1. Prefer stubs over mocks — test behavior (outputs), not implementation (calls)
2. Use mocks only for verifying important side effects (email sent, event published)
3. Use fakes for repositories and data stores — they enable realistic test flows
4. Use `spec=` with unittest.mock to get type-safe mocks that catch typos
5. Keep test doubles close to the interface — if the interface changes, doubles should break too'''
    ),
    (
        "testing/snapshot-testing",
        "Show snapshot testing and golden file patterns for validating complex outputs like HTML, JSON, and API responses.",
        '''Snapshot testing and golden file patterns:

```python
# --- snapshot.py --- Snapshot testing framework ---

from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass
import difflib


@dataclass
class SnapshotResult:
    passed: bool
    snapshot_path: str
    diff: Optional[str] = None
    is_new: bool = False


class SnapshotManager:
    """Manage golden file snapshots for test assertions.

    Snapshots are stored as files and compared on subsequent runs.
    Set UPDATE_SNAPSHOTS=1 to regenerate all snapshots.
    """

    def __init__(self, snapshot_dir: str = "__snapshots__"):
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.update_mode = os.environ.get("UPDATE_SNAPSHOTS", "0") == "1"

    def assert_match(
        self,
        name: str,
        actual: str,
        extension: str = ".txt",
    ) -> SnapshotResult:
        """Compare actual output against stored snapshot.

        If no snapshot exists or UPDATE_SNAPSHOTS=1, creates/updates it.
        """
        snapshot_path = self.snapshot_dir / f"{name}{extension}"

        if not snapshot_path.exists() or self.update_mode:
            # Create or update snapshot
            snapshot_path.write_text(actual, encoding="utf-8")
            return SnapshotResult(
                passed=True,
                snapshot_path=str(snapshot_path),
                is_new=not snapshot_path.exists(),
            )

        # Compare with existing snapshot
        expected = snapshot_path.read_text(encoding="utf-8")

        if actual == expected:
            return SnapshotResult(passed=True, snapshot_path=str(snapshot_path))

        # Generate diff
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile=f"snapshot: {name}",
                tofile="actual output",
                lineterm="",
            )
        )

        return SnapshotResult(
            passed=False,
            snapshot_path=str(snapshot_path),
            diff=diff,
        )

    def assert_json_match(self, name: str, actual: Any) -> SnapshotResult:
        """Snapshot test for JSON-serializable data."""
        actual_str = json.dumps(actual, indent=2, sort_keys=True, default=str)
        return self.assert_match(name, actual_str, extension=".json")

    def assert_html_match(self, name: str, actual: str) -> SnapshotResult:
        """Snapshot test for HTML content."""
        return self.assert_match(name, actual, extension=".html")


# Global instance
snapshots = SnapshotManager()
```

```python
# --- test_snapshots.py --- Snapshot tests with pytest ---

import pytest
import json
from snapshot import SnapshotManager


@pytest.fixture
def snap(request, tmp_path):
    """Pytest fixture for snapshot testing."""
    # Use test-specific snapshot directory
    snap_dir = Path(request.fspath).parent / "__snapshots__"
    return SnapshotManager(str(snap_dir))


class TestAPIResponseSnapshots:
    """Snapshot tests for API response shapes."""

    def test_user_list_response(self, snap, client):
        """Verify the user list API response structure."""
        response = client.get("/api/users?page=1&limit=5")
        data = response.json()

        # Normalize dynamic fields before snapshotting
        for user in data.get("users", []):
            user["id"] = "<ID>"
            user["created_at"] = "<TIMESTAMP>"

        result = snap.assert_json_match("user_list_response", data)
        assert result.passed, f"Snapshot mismatch:\n{result.diff}"

    def test_error_response_format(self, snap, client):
        """Verify error responses have consistent structure."""
        response = client.get("/api/users/99999")
        assert response.status_code == 404

        result = snap.assert_json_match("error_404_response", response.json())
        assert result.passed, f"Snapshot mismatch:\n{result.diff}"

    def test_html_email_template(self, snap):
        """Verify email template rendering."""
        from email_templates import render_welcome_email

        html = render_welcome_email(
            name="Alice",
            activation_url="https://example.com/activate/TOKEN",
        )

        # Normalize dynamic content
        html = html.replace("TOKEN", "<TOKEN>")

        result = snap.assert_html_match("welcome_email", html)
        assert result.passed, f"Snapshot mismatch:\n{result.diff}"


class TestSerializationSnapshots:
    """Snapshot tests for serialization formats."""

    def test_config_serialization(self, snap):
        """Verify config YAML output hasn't changed unexpectedly."""
        from config import AppConfig

        config = AppConfig(
            database_url="postgresql://localhost/test",
            redis_url="redis://localhost",
            log_level="INFO",
            feature_flags={"new_checkout": True, "dark_mode": False},
        )

        result = snap.assert_json_match("app_config", config.to_dict())
        assert result.passed, f"Snapshot mismatch:\n{result.diff}"

    def test_migration_sql(self, snap):
        """Verify SQL migration output is stable."""
        from migrations import generate_migration

        sql = generate_migration("add_users_table")

        result = snap.assert_match("migration_add_users", sql, extension=".sql")
        assert result.passed, f"Snapshot mismatch:\n{result.diff}"


# --- Inline snapshot alternative (using syrupy pytest plugin) ---
# pip install syrupy

def test_user_serialization(snapshot):
    """Using syrupy for inline snapshot testing."""
    user = {"id": 1, "name": "Alice", "email": "alice@example.com"}
    assert user == snapshot  # auto-generates/compares snapshot

# Update: pytest --snapshot-update
```

```python
# --- golden_file.py --- Golden file testing pattern ---

from pathlib import Path
from typing import Callable
import subprocess


class GoldenFileTest:
    """Golden file testing for CLI tools and code generators.

    Compares program output against a known-good "golden" file.
    """

    def __init__(self, golden_dir: str = "testdata/golden"):
        self.golden_dir = Path(golden_dir)
        self.golden_dir.mkdir(parents=True, exist_ok=True)

    def assert_output(
        self,
        name: str,
        actual: str,
        update: bool = False,
    ) -> None:
        """Compare actual output against golden file."""
        golden_path = self.golden_dir / name

        if update or not golden_path.exists():
            golden_path.write_text(actual, encoding="utf-8")
            return

        expected = golden_path.read_text(encoding="utf-8")
        if actual != expected:
            diff = "\n".join(
                difflib.unified_diff(
                    expected.splitlines(),
                    actual.splitlines(),
                    fromfile=str(golden_path),
                    tofile="actual",
                    lineterm="",
                )
            )
            raise AssertionError(
                f"Golden file mismatch for {name}.\n"
                f"Run with UPDATE_GOLDEN=1 to update.\n"
                f"Diff:\n{diff}"
            )

    def assert_command_output(
        self,
        name: str,
        command: list[str],
        update: bool = False,
    ) -> None:
        """Run a command and compare stdout against golden file."""
        result = subprocess.run(command, capture_output=True, text=True)
        self.assert_output(f"{name}.stdout", result.stdout, update)
        if result.stderr:
            self.assert_output(f"{name}.stderr", result.stderr, update)


# Usage in tests
import difflib

golden = GoldenFileTest("tests/testdata/golden")

def test_cli_help_output():
    golden.assert_command_output(
        "help",
        ["python", "-m", "myapp", "--help"],
    )

def test_code_generation():
    from codegen import generate_model

    code = generate_model("User", fields={"name": "str", "email": "str"})
    golden.assert_output("user_model.py", code)
```

| Approach | Storage | Update command | Best for |
|----------|---------|---------------|----------|
| File snapshots | `__snapshots__/*.json` | `UPDATE_SNAPSHOTS=1 pytest` | JSON/HTML/SQL outputs |
| Inline snapshots (syrupy) | Inside test file | `pytest --snapshot-update` | Small, inline values |
| Golden files | `testdata/golden/` | `UPDATE_GOLDEN=1 pytest` | CLI output, code generators |
| pytest-regtest | `_regtest_outputs/` | `pytest --regtest-reset` | stdout/stderr capture |

Key patterns:
1. Normalize dynamic fields (IDs, timestamps, tokens) before snapshotting
2. Review snapshot diffs in PRs like code changes — snapshot updates should be intentional
3. Use golden files for code generators and CLI tools where exact output matters
4. Store snapshots in version control — they ARE the expected output specification
5. Use `UPDATE_SNAPSHOTS=1` as an explicit opt-in to regenerate, never auto-update'''
    ),
    (
        "testing/test-data-builders",
        "Show test data builder and fixture patterns for creating complex test objects with sensible defaults and customization.",
        '''Test data builders and fixture patterns:

```python
# --- builders.py --- Builder pattern for test data ---

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Optional, TypeVar, Generic
from dataclasses import dataclass, field
from copy import deepcopy

T = TypeVar("T")


# === Builder pattern (fluent API) ===

@dataclass
class User:
    id: int
    name: str
    email: str
    tier: str
    is_active: bool
    created_at: datetime
    metadata: dict[str, Any]


class UserBuilder:
    """Builder for User test objects with sensible defaults.

    Usage:
        user = UserBuilder().with_name("Alice").with_tier("pro").build()
    """

    _counter: int = 0

    def __init__(self):
        UserBuilder._counter += 1
        n = UserBuilder._counter
        self._id = n
        self._name = f"User {n}"
        self._email = f"user{n}@test.com"
        self._tier = "free"
        self._is_active = True
        self._created_at = datetime(2024, 1, 1, 12, 0, 0)
        self._metadata: dict[str, Any] = {}

    def with_id(self, id: int) -> UserBuilder:
        self._id = id
        return self

    def with_name(self, name: str) -> UserBuilder:
        self._name = name
        return self

    def with_email(self, email: str) -> UserBuilder:
        self._email = email
        return self

    def with_tier(self, tier: str) -> UserBuilder:
        self._tier = tier
        return self

    def inactive(self) -> UserBuilder:
        self._is_active = False
        return self

    def with_metadata(self, **kwargs) -> UserBuilder:
        self._metadata.update(kwargs)
        return self

    def created_days_ago(self, days: int) -> UserBuilder:
        self._created_at = datetime.utcnow() - timedelta(days=days)
        return self

    def build(self) -> User:
        return User(
            id=self._id,
            name=self._name,
            email=self._email,
            tier=self._tier,
            is_active=self._is_active,
            created_at=self._created_at,
            metadata=self._metadata,
        )

    def build_dict(self) -> dict[str, Any]:
        user = self.build()
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "tier": user.tier,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
            "metadata": user.metadata,
        }


@dataclass
class Order:
    id: str
    user_id: int
    items: list[dict]
    total: float
    status: str
    created_at: datetime


class OrderBuilder:
    """Builder for Order test objects."""

    def __init__(self):
        self._id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        self._user_id = 1
        self._items: list[dict] = [
            {"sku": "ITEM-001", "name": "Widget", "price": 9.99, "quantity": 1},
        ]
        self._status = "pending"
        self._created_at = datetime.utcnow()

    def with_user(self, user: User | UserBuilder) -> OrderBuilder:
        if isinstance(user, UserBuilder):
            user = user.build()
        self._user_id = user.id
        return self

    def with_items(self, *items: dict) -> OrderBuilder:
        self._items = list(items)
        return self

    def with_item(self, sku: str, price: float, quantity: int = 1) -> OrderBuilder:
        self._items.append({
            "sku": sku,
            "name": f"Product {sku}",
            "price": price,
            "quantity": quantity,
        })
        return self

    def confirmed(self) -> OrderBuilder:
        self._status = "confirmed"
        return self

    def cancelled(self) -> OrderBuilder:
        self._status = "cancelled"
        return self

    @property
    def _total(self) -> float:
        return sum(i["price"] * i["quantity"] for i in self._items)

    def build(self) -> Order:
        return Order(
            id=self._id,
            user_id=self._user_id,
            items=deepcopy(self._items),
            total=self._total,
            status=self._status,
            created_at=self._created_at,
        )
```

```python
# --- fixtures.py --- Pytest fixtures with factories ---

import pytest
from builders import UserBuilder, OrderBuilder, User, Order
from typing import Callable


# --- Factory fixtures: return a builder function ---

@pytest.fixture
def make_user() -> Callable[..., User]:
    """Factory fixture: creates users with sensible defaults.

    Usage in tests:
        def test_something(make_user):
            alice = make_user(name="Alice", tier="pro")
            bob = make_user(name="Bob")
    """
    def _make(**overrides) -> User:
        builder = UserBuilder()
        for key, value in overrides.items():
            method = getattr(builder, f"with_{key}", None)
            if method:
                method(value)
            elif key == "inactive":
                builder.inactive()
        return builder.build()

    return _make


@pytest.fixture
def make_order(make_user) -> Callable[..., Order]:
    """Factory fixture for orders with auto-created users."""
    def _make(user: User | None = None, **overrides) -> Order:
        if user is None:
            user = make_user()
        builder = OrderBuilder().with_user(user)
        for key, value in overrides.items():
            method = getattr(builder, f"with_{key}", None)
            if method:
                method(value)
        return builder.build()

    return _make


# --- Scenario fixtures: pre-built test scenarios ---

@pytest.fixture
def pro_user_with_orders(make_user, make_order) -> dict:
    """Complete scenario: pro user with multiple orders."""
    user = make_user(name="Alice", tier="pro")
    orders = [
        make_order(user=user),
        make_order(user=user),
        make_order(user=user),
    ]
    return {"user": user, "orders": orders}


@pytest.fixture
def empty_store(db_session) -> None:
    """Scenario: fresh database with no data."""
    db_session.execute("DELETE FROM orders")
    db_session.execute("DELETE FROM users")
    db_session.commit()


# --- Database-backed fixtures ---

@pytest.fixture
def persisted_user(db_session, make_user) -> User:
    """Create and persist a user to the database."""
    user = make_user(name="DB User")
    db_session.execute(
        "INSERT INTO users (id, name, email, tier) VALUES (:id, :name, :email, :tier)",
        {"id": user.id, "name": user.name, "email": user.email, "tier": user.tier},
    )
    db_session.commit()
    return user


# --- Usage in tests ---

class TestOrderWorkflow:
    def test_place_order_for_new_user(self, make_user, make_order):
        user = make_user(name="Charlie", tier="free")
        order = make_order(user=user)
        assert order.user_id == user.id
        assert order.status == "pending"

    def test_pro_discount(self, pro_user_with_orders):
        scenario = pro_user_with_orders
        assert scenario["user"].tier == "pro"
        assert len(scenario["orders"]) == 3

    def test_different_users_independent(self, make_user):
        alice = make_user(name="Alice")
        bob = make_user(name="Bob")
        assert alice.id != bob.id
        assert alice.email != bob.email
```

```python
# --- mother.py --- Object Mother pattern (alternative to builders) ---

from datetime import datetime, timedelta
from typing import Any
import uuid


class TestUsers:
    """Object Mother: named factory methods for common test personas.

    Simpler than builders for common cases.
    """

    @staticmethod
    def alice(**overrides) -> dict:
        """Standard pro user."""
        base = {
            "id": 1,
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "tier": "pro",
            "is_active": True,
            "created_at": datetime(2023, 6, 1).isoformat(),
        }
        base.update(overrides)
        return base

    @staticmethod
    def bob(**overrides) -> dict:
        """Standard free user."""
        base = {
            "id": 2,
            "name": "Bob Smith",
            "email": "bob@example.com",
            "tier": "free",
            "is_active": True,
            "created_at": datetime(2024, 1, 1).isoformat(),
        }
        base.update(overrides)
        return base

    @staticmethod
    def inactive_user(**overrides) -> dict:
        """Deactivated user for testing access control."""
        base = {
            "id": 99,
            "name": "Inactive User",
            "email": "inactive@example.com",
            "tier": "free",
            "is_active": False,
            "created_at": datetime(2022, 1, 1).isoformat(),
        }
        base.update(overrides)
        return base

    @staticmethod
    def enterprise_admin(**overrides) -> dict:
        """Enterprise admin user."""
        base = {
            "id": 100,
            "name": "Enterprise Admin",
            "email": "admin@corp.example.com",
            "tier": "enterprise",
            "is_active": True,
            "role": "admin",
            "created_at": datetime(2023, 1, 1).isoformat(),
        }
        base.update(overrides)
        return base


class TestOrders:
    """Object Mother for orders."""

    @staticmethod
    def simple(**overrides) -> dict:
        base = {
            "id": f"ORD-{uuid.uuid4().hex[:8]}",
            "user_id": 1,
            "items": [{"sku": "ITEM-001", "price": 9.99, "quantity": 1}],
            "total": 9.99,
            "status": "pending",
        }
        base.update(overrides)
        return base

    @staticmethod
    def multi_item(**overrides) -> dict:
        base = {
            "id": f"ORD-{uuid.uuid4().hex[:8]}",
            "user_id": 1,
            "items": [
                {"sku": "ITEM-001", "price": 9.99, "quantity": 2},
                {"sku": "ITEM-002", "price": 24.99, "quantity": 1},
                {"sku": "ITEM-003", "price": 4.99, "quantity": 5},
            ],
            "total": 69.92,
            "status": "pending",
        }
        base.update(overrides)
        return base


# Usage
def test_with_object_mother():
    alice = TestUsers.alice()
    order = TestOrders.multi_item(user_id=alice["id"])
    assert order["total"] == 69.92
```

| Pattern | API style | Complexity | Best for |
|---------|-----------|-----------|----------|
| Builder | `UserBuilder().with_name("A").build()` | Medium | Complex objects with many fields |
| Factory fixture | `make_user(name="A")` | Low | Pytest integration, simple customization |
| Object Mother | `TestUsers.alice()` | Low | Named personas, shared test data |
| Factory Boy | `UserFactory(name="A")` | Medium | Django/SQLAlchemy model generation |
| Dataclass defaults | `User(name="A")` | Lowest | Simple dataclasses with defaults |

Key patterns:
1. Builders give sensible defaults — tests only specify fields relevant to the test case
2. Factory fixtures (`make_user`) provide fresh, unique instances per call (unique IDs, emails)
3. Object Mothers (`TestUsers.alice()`) are best for well-known personas used across many tests
4. Keep fixture setup local to the test — avoid shared mutable state between tests
5. Auto-increment IDs and unique emails in builders to prevent test interference'''
    ),
    (
        "testing/flaky-test-detection",
        "Show how to detect, quarantine, and fix flaky tests including common causes and CI strategies.",
        '''Flaky test detection, quarantine, and remediation:

```python
# --- flaky_detector.py --- Automated flaky test detection ---

from __future__ import annotations

import json
import time
import subprocess
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    test_id: str          # e.g., "tests/test_api.py::TestOrders::test_create"
    passed: bool
    duration_ms: float
    error: Optional[str] = None
    run_number: int = 0


@dataclass
class FlakyTestReport:
    test_id: str
    total_runs: int
    pass_count: int
    fail_count: int
    pass_rate: float
    is_flaky: bool
    avg_duration_ms: float
    errors: list[str]
    first_seen: str
    category: str = ""    # timing, ordering, state, network, concurrency


class FlakyTestDetector:
    """Detect flaky tests by running them multiple times."""

    def __init__(
        self,
        test_dir: str = "tests/",
        reruns: int = 5,
        flaky_threshold: float = 0.8,  # <80% pass rate = flaky
    ):
        self.test_dir = test_dir
        self.reruns = reruns
        self.flaky_threshold = flaky_threshold

    def detect(self, test_pattern: str = "") -> list[FlakyTestReport]:
        """Run tests multiple times and identify flaky ones."""
        all_results: dict[str, list[TestResult]] = {}

        for run in range(self.reruns):
            logger.info(f"Run {run + 1}/{self.reruns}")
            results = self._run_tests(test_pattern, run)

            for result in results:
                if result.test_id not in all_results:
                    all_results[result.test_id] = []
                all_results[result.test_id].append(result)

        # Analyze results
        reports = []
        for test_id, results in all_results.items():
            pass_count = sum(1 for r in results if r.passed)
            fail_count = len(results) - pass_count
            pass_rate = pass_count / len(results) if results else 0

            is_flaky = 0 < pass_rate < self.flaky_threshold

            reports.append(FlakyTestReport(
                test_id=test_id,
                total_runs=len(results),
                pass_count=pass_count,
                fail_count=fail_count,
                pass_rate=pass_rate,
                is_flaky=is_flaky,
                avg_duration_ms=sum(r.duration_ms for r in results) / len(results),
                errors=[r.error for r in results if r.error],
                first_seen=datetime.utcnow().isoformat(),
                category=self._categorize_flakiness(results),
            ))

        flaky = [r for r in reports if r.is_flaky]
        logger.info(f"Found {len(flaky)} flaky tests out of {len(reports)} total")
        return reports

    def _run_tests(self, pattern: str, run_number: int) -> list[TestResult]:
        """Run pytest and parse results."""
        cmd = [
            "python", "-m", "pytest",
            self.test_dir,
            f"--json-report",
            f"--json-report-file=.flaky_run_{run_number}.json",
            "-x" if run_number == 0 else "",  # fail fast only on first run
            "--tb=short",
            "-q",
        ]
        if pattern:
            cmd.extend(["-k", pattern])

        subprocess.run([c for c in cmd if c], capture_output=True)

        results = []
        report_path = Path(f".flaky_run_{run_number}.json")
        if report_path.exists():
            data = json.loads(report_path.read_text())
            for test in data.get("tests", []):
                results.append(TestResult(
                    test_id=test["nodeid"],
                    passed=test["outcome"] == "passed",
                    duration_ms=test.get("duration", 0) * 1000,
                    error=test.get("call", {}).get("longrepr"),
                    run_number=run_number,
                ))
            report_path.unlink()

        return results

    def _categorize_flakiness(self, results: list[TestResult]) -> str:
        """Attempt to categorize the type of flakiness."""
        errors = [r.error for r in results if r.error]
        if not errors:
            return "unknown"

        error_text = " ".join(errors).lower()

        if any(kw in error_text for kw in ["timeout", "timed out", "deadline"]):
            return "timing"
        if any(kw in error_text for kw in ["connection", "refused", "network"]):
            return "network"
        if any(kw in error_text for kw in ["race", "concurrent", "lock"]):
            return "concurrency"
        if any(kw in error_text for kw in ["order", "depend", "fixture"]):
            return "ordering"
        if any(kw in error_text for kw in ["state", "already exists", "duplicate"]):
            return "state_leak"
        return "unknown"
```

```python
# --- quarantine.py --- Flaky test quarantine system ---

import pytest
import json
from pathlib import Path
from typing import Set


QUARANTINE_FILE = Path("tests/quarantined_tests.json")


def load_quarantine() -> dict:
    """Load the quarantine list."""
    if QUARANTINE_FILE.exists():
        return json.loads(QUARANTINE_FILE.read_text())
    return {"quarantined": [], "reason": {}}


def save_quarantine(data: dict) -> None:
    QUARANTINE_FILE.write_text(json.dumps(data, indent=2))


def quarantine_test(test_id: str, reason: str) -> None:
    """Add a test to the quarantine list."""
    data = load_quarantine()
    if test_id not in data["quarantined"]:
        data["quarantined"].append(test_id)
        data["reason"][test_id] = reason
        save_quarantine(data)


def unquarantine_test(test_id: str) -> None:
    """Remove a test from quarantine after fixing."""
    data = load_quarantine()
    if test_id in data["quarantined"]:
        data["quarantined"].remove(test_id)
        data["reason"].pop(test_id, None)
        save_quarantine(data)


# --- pytest plugin for quarantine ---

class QuarantinePlugin:
    """Pytest plugin that handles quarantined tests.

    In CI: quarantined tests are xfail (don't break the build).
    Locally: quarantined tests run normally (for debugging).
    """

    def __init__(self):
        self.quarantine_data = load_quarantine()
        self.quarantined_ids: set[str] = set(self.quarantine_data["quarantined"])

    def pytest_collection_modifyitems(self, items):
        """Mark quarantined tests as xfail in CI."""
        import os
        is_ci = os.environ.get("CI", "false").lower() == "true"

        for item in items:
            if item.nodeid in self.quarantined_ids:
                reason = self.quarantine_data["reason"].get(item.nodeid, "Flaky test")
                if is_ci:
                    item.add_marker(pytest.mark.xfail(
                        reason=f"QUARANTINED: {reason}",
                        strict=False,
                    ))
                else:
                    # Locally, add a warning but run normally
                    item.add_marker(pytest.mark.filterwarnings(
                        f"always::UserWarning"
                    ))


# Register plugin in conftest.py:
# def pytest_configure(config):
#     config.pluginmanager.register(QuarantinePlugin())


# --- conftest.py entry ---
# @pytest.fixture(autouse=True)
# def _warn_quarantined(request):
#     quarantine = load_quarantine()
#     if request.node.nodeid in quarantine["quarantined"]:
#         import warnings
#         reason = quarantine["reason"].get(request.node.nodeid, "unknown")
#         warnings.warn(f"Test is quarantined: {reason}", UserWarning)
```

```python
# --- flaky_fixes.py --- Common fixes for flaky test patterns ---

import pytest
import time
import threading
from typing import Generator
from unittest.mock import patch


# === Fix 1: Timing-dependent tests ===

# BAD: depends on wall clock time
def test_cache_expiry_flaky():
    cache.set("key", "value", ttl=1)
    time.sleep(1.1)  # flaky: might not expire in exactly 1.1s
    assert cache.get("key") is None

# GOOD: use freezegun or mock time
@pytest.fixture
def frozen_time():
    """Control time for deterministic tests."""
    import freezegun
    with freezegun.freeze_time("2024-01-15 12:00:00") as frozen:
        yield frozen

def test_cache_expiry_fixed(frozen_time):
    cache.set("key", "value", ttl=60)
    frozen_time.tick(timedelta(seconds=61))  # advance time deterministically
    assert cache.get("key") is None


# === Fix 2: Test ordering dependency ===

# BAD: depends on test execution order
class TestBadOrdering:
    shared_state = []

    def test_add(self):
        self.shared_state.append("item")

    def test_check(self):
        assert "item" in self.shared_state  # fails if test_add runs after

# GOOD: each test sets up its own state
class TestGoodOrdering:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.state = []

    def test_add(self):
        self.state.append("item")
        assert "item" in self.state

    def test_check(self):
        self.state.append("other")
        assert "other" in self.state


# === Fix 3: Database state leaks ===

# BAD: leftover data from other tests
def test_user_count_flaky(db):
    db.execute("INSERT INTO users (name) VALUES ('Alice')")
    count = db.execute("SELECT COUNT(*) FROM users").scalar()
    assert count == 1  # fails if other tests left data

# GOOD: transactional isolation
@pytest.fixture
def clean_db(db_engine) -> Generator:
    """Each test runs in a transaction that gets rolled back."""
    connection = db_engine.connect()
    transaction = connection.begin()
    yield connection
    transaction.rollback()
    connection.close()

def test_user_count_fixed(clean_db):
    clean_db.execute("INSERT INTO users (name) VALUES ('Alice')")
    count = clean_db.execute("SELECT COUNT(*) FROM users").scalar()
    assert count == 1  # always starts clean


# === Fix 4: Port conflicts ===

# BAD: hardcoded port
def test_server_flaky():
    server = start_server(port=8080)  # fails if port in use

# GOOD: random available port
def test_server_fixed():
    import socket
    with socket.socket() as s:
        s.bind(("", 0))
        port = s.getsockname()[1]
    server = start_server(port=port)  # guaranteed available


# === Fix 5: Async race conditions ===

# BAD: no synchronization
def test_async_flaky():
    result = []
    thread = threading.Thread(target=lambda: result.append(compute()))
    thread.start()
    assert len(result) == 1  # race: thread might not finish

# GOOD: proper synchronization
def test_async_fixed():
    result = []
    thread = threading.Thread(target=lambda: result.append(compute()))
    thread.start()
    thread.join(timeout=10)  # wait for completion
    assert len(result) == 1
```

| Flaky Category | Root Cause | Fix |
|---------------|------------|-----|
| Timing | `time.sleep()`, wall clock | Mock time with freezegun, use monotonic clock |
| Ordering | Shared mutable state | Isolate state per test, use fixtures |
| State leak | Database/cache not cleaned | Transactional rollback, fresh fixtures |
| Network | External service dependency | Use mocks/stubs, container test doubles |
| Concurrency | Race conditions, no sync | Use `join()`, `Event`, or `asyncio.wait_for()` |
| Port conflict | Hardcoded ports | Use random available ports |
| Resource | File handles, memory | Proper cleanup in fixtures/finalizers |

Key patterns:
1. Run tests 5-10 times to detect flakiness — a 90% pass rate means 1-in-10 CI runs fail
2. Quarantine flaky tests with `xfail` in CI to unblock the pipeline while fixing
3. Categorize flakiness (timing, state, network) to apply the right fix pattern
4. Use transactional test isolation to prevent database state leaks between tests
5. Track quarantine age — tests quarantined for >2 weeks should be fixed or deleted'''
    ),
    (
        "testing/ci-testing-strategies",
        "Show CI testing strategies including test parallelization, test splitting, coverage gates, and test result reporting.",
        '''CI testing strategies — parallelization, splitting, coverage gates, and reporting:

```yaml
# --- .github/workflows/test.yml --- Comprehensive CI test pipeline ---

name: Test Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  # === Job 1: Fast checks (lint, type check, unit tests) ===
  fast-checks:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Lint
        run: ruff check .

      - name: Type check
        run: mypy src/ --strict

      - name: Unit tests (fast)
        run: |
          pytest tests/unit/ \
            -x \
            --timeout=30 \
            -n auto \
            --dist loadgroup \
            --cov=src \
            --cov-report=xml:coverage-unit.xml \
            --junitxml=results-unit.xml

      - name: Upload coverage
        uses: actions/upload-artifact@v4
        with:
          name: coverage-unit
          path: coverage-unit.xml

  # === Job 2: Integration tests (parallelized across matrix) ===
  integration-tests:
    needs: fast-checks
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        shard: [1, 2, 3, 4]    # 4 parallel shards
        total-shards: [4]
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Split tests by timing
        id: split
        run: |
          # Use pytest-split for intelligent test splitting
          pytest tests/integration/ \
            --collect-only -q \
            --splitting-algorithm least_duration \
            --splits ${{ matrix.total-shards }} \
            --group ${{ matrix.shard }} \
            > test_list.txt
          echo "test_count=$(wc -l < test_list.txt)" >> $GITHUB_OUTPUT

      - name: Run integration tests (shard ${{ matrix.shard }})
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/testdb
          REDIS_URL: redis://localhost:6379
        run: |
          pytest tests/integration/ \
            --splitting-algorithm least_duration \
            --splits ${{ matrix.total-shards }} \
            --group ${{ matrix.shard }} \
            --timeout=120 \
            --reruns 2 \
            --reruns-delay 5 \
            --cov=src \
            --cov-report=xml:coverage-integration-${{ matrix.shard }}.xml \
            --junitxml=results-integration-${{ matrix.shard }}.xml

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results-shard-${{ matrix.shard }}
          path: |
            results-integration-${{ matrix.shard }}.xml
            coverage-integration-${{ matrix.shard }}.xml

  # === Job 3: Coverage gate ===
  coverage-gate:
    needs: [fast-checks, integration-tests]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download all coverage artifacts
        uses: actions/download-artifact@v4
        with:
          pattern: coverage-*
          merge-multiple: true

      - name: Merge coverage reports
        run: |
          pip install coverage
          coverage combine
          coverage xml -o coverage-merged.xml
          coverage report --fail-under=80 --show-missing

      - name: Coverage diff check
        uses: orgoro/coverage@v3
        with:
          coverageFile: coverage-merged.xml
          token: ${{ secrets.GITHUB_TOKEN }}
          thresholdAll: 80      # overall minimum 80%
          thresholdNew: 90      # new code must be 90%+
          thresholdModified: 85 # modified code must be 85%+

  # === Job 4: Report results ===
  report:
    needs: [integration-tests]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download all test results
        uses: actions/download-artifact@v4
        with:
          pattern: test-results-*
          merge-multiple: true

      - name: Publish test results
        uses: EnricoMi/publish-unit-test-result-action@v2
        with:
          files: results-*.xml
          check_name: "Test Results"
          comment_mode: always
```

```python
# --- conftest.py --- Test infrastructure for CI ---

import os
import pytest
import logging
from typing import Generator

logger = logging.getLogger(__name__)


# --- Test markers ---

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (no I/O)")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Tests that take >30 seconds")
    config.addinivalue_line("markers", "flaky: Known flaky tests")


# --- Auto-mark tests based on directory ---

def pytest_collection_modifyitems(config, items):
    """Auto-apply markers based on test file location."""
    for item in items:
        # Auto-mark by directory
        if "/unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)

    # In CI, skip e2e unless explicitly requested
    if os.environ.get("CI") and not config.getoption("-m", default=""):
        skip_e2e = pytest.mark.skip(reason="E2E tests skipped in CI (use -m e2e)")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)


# --- Test timing for split optimization ---

@pytest.fixture(autouse=True)
def _log_test_timing(request):
    """Log test duration for pytest-split timing data."""
    start = __import__("time").monotonic()
    yield
    duration = __import__("time").monotonic() - start
    if duration > 5:
        logger.warning(
            f"Slow test: {request.node.nodeid} took {duration:.1f}s"
        )


# --- Database fixtures with isolation ---

@pytest.fixture(scope="session")
def db_engine():
    """Create database engine once per test session."""
    from sqlalchemy import create_engine
    url = os.environ.get("DATABASE_URL", "sqlite:///test.db")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator:
    """Per-test transactional isolation."""
    connection = db_engine.connect()
    transaction = connection.begin()

    from sqlalchemy.orm import Session
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

```ini
# --- pytest.ini --- pytest configuration ---

[pytest]
minversion = 7.0
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Default options
addopts =
    -v
    --strict-markers
    --strict-config
    --tb=short
    -p no:warnings

# Timeout (per test)
timeout = 60
timeout_method = thread

# Parallelization
# -n auto uses all CPU cores
# --dist loadgroup groups tests by @pytest.mark.group

# Coverage
# --cov=src --cov-report=term-missing --cov-fail-under=80

# Markers
markers =
    unit: Unit tests (no I/O, no network)
    integration: Integration tests (needs database, services)
    e2e: End-to-end tests (needs full stack)
    slow: Tests that take >30 seconds
    flaky: Known flaky tests (quarantined in CI)

# Filter warnings
filterwarnings =
    error
    ignore::DeprecationWarning:third_party_lib.*

# Log configuration for test output
log_cli = true
log_cli_level = WARNING
log_cli_format = %(asctime)s [%(levelname)8s] %(message)s
```

| Strategy | Tool | Speedup | Tradeoff |
|----------|------|---------|----------|
| Parallelization | `pytest-xdist -n auto` | 3-8x | Needs test isolation |
| Test splitting | `pytest-split --splits N` | Nx with N shards | CI matrix complexity |
| Fail fast | `pytest -x` | Skips after first fail | Misses other failures |
| Test selection | `pytest-changed` | Only changed tests | May miss regressions |
| Reruns | `pytest-rerunfailures --reruns 2` | Reduces false fails | Hides real flakiness |
| Caching | `pytest-cache --lf` | Reruns last failures | Needs cache persistence |
| Timeout | `pytest-timeout --timeout 60` | Prevents hanging | May kill slow tests |

Key patterns:
1. Layer CI tests: fast checks (lint, type, unit) first, then integration in parallel shards
2. Use `pytest-split` with timing data for even distribution across shards
3. Set coverage gates: 80% overall, 90% for new code, 85% for modified code
4. Auto-mark tests by directory (`/unit/`, `/integration/`) to simplify filtering
5. Use transactional rollback for database test isolation — faster than truncating tables'''
    ),
]
