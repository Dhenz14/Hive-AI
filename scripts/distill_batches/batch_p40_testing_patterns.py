"""Testing patterns — pytest fixtures, mocking, parametrize, test organization."""

PAIRS = [
    (
        "testing/pytest-patterns",
        "Show pytest patterns: fixtures, parametrize, markers, conftest organization, and test architecture.",
        '''Production pytest patterns and architecture:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from dataclasses import dataclass

# --- conftest.py: shared fixtures ---

@pytest.fixture
def sample_user():
    """Simple fixture returning test data."""
    return {
        "id": "user-123",
        "name": "Alice",
        "email": "alice@test.com",
        "roles": ["user"],
    }

@pytest.fixture
async def db_session(tmp_path):
    """Database session with automatic cleanup."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()

@pytest.fixture
def mock_redis():
    """In-memory mock Redis for testing."""
    store = {}

    class FakeRedis:
        async def get(self, key):
            return store.get(key)
        async def set(self, key, value, ex=None):
            store[key] = value
        async def delete(self, key):
            store.pop(key, None)
        async def exists(self, key):
            return key in store

    return FakeRedis()

@pytest.fixture
def api_client(db_session, mock_redis):
    """FastAPI test client with injected dependencies."""
    from httpx import AsyncClient, ASGITransport
    from app.main import create_app
    from app.deps import get_db, get_redis

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: mock_redis

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# --- Parametrize: test multiple cases ---

@pytest.mark.parametrize("input_email,expected_valid", [
    ("user@example.com", True),
    ("user+tag@example.com", True),
    ("user@sub.domain.com", True),
    ("", False),
    ("no-at-sign", False),
    ("@no-local.com", False),
    ("user@", False),
    ("user@.com", False),
])
def test_email_validation(input_email, expected_valid):
    assert validate_email(input_email) == expected_valid

# Parametrize with IDs for readable output
@pytest.mark.parametrize("status_code,should_retry", [
    pytest.param(200, False, id="success-no-retry"),
    pytest.param(429, True, id="rate-limited-retry"),
    pytest.param(500, True, id="server-error-retry"),
    pytest.param(502, True, id="bad-gateway-retry"),
    pytest.param(404, False, id="not-found-no-retry"),
    pytest.param(401, False, id="unauthorized-no-retry"),
])
def test_retry_logic(status_code, should_retry):
    assert should_retry_request(status_code) == should_retry


# --- Markers: categorize tests ---

# pyproject.toml:
# [tool.pytest.ini_options]
# markers = ["slow", "integration", "smoke"]

@pytest.mark.slow
def test_full_pipeline():
    """Runs full ETL pipeline, takes ~30 seconds."""
    ...

@pytest.mark.integration
async def test_database_connection(db_session):
    """Requires real database."""
    ...

@pytest.mark.smoke
def test_health_check(api_client):
    """Quick sanity check."""
    response = api_client.get("/health")
    assert response.status_code == 200

# Run: pytest -m "not slow"  # Skip slow tests
# Run: pytest -m "smoke"     # Only smoke tests


# --- Mocking patterns ---

async def test_send_notification(mock_redis):
    """Mock external services."""
    with patch("app.services.email.send_email") as mock_send:
        mock_send.return_value = {"message_id": "abc123"}

        service = NotificationService(redis=mock_redis)
        result = await service.notify_user("user-123", "Welcome!")

        mock_send.assert_called_once_with(
            to="alice@test.com",
            subject="Notification",
            body="Welcome!",
        )
        assert result["status"] == "sent"

# AsyncMock for async functions
async def test_async_dependency():
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = {"id": "123", "name": "Alice"}

    service = UserService(repo=mock_repo)
    user = await service.get_user("123")

    assert user["name"] == "Alice"
    mock_repo.get_by_id.assert_awaited_once_with("123")


# --- Exception testing ---

def test_validation_error():
    with pytest.raises(ValueError, match="Invalid email"):
        validate_email("not-an-email")

async def test_not_found():
    with pytest.raises(NotFoundError) as exc_info:
        await service.get_user("nonexistent")
    assert exc_info.value.status_code == 404


# --- Snapshot testing (with syrupy) ---

def test_api_response_format(api_client, snapshot):
    response = api_client.get("/api/users/123")
    assert response.json() == snapshot
```

Test organization:
```
tests/
├── conftest.py           # Shared fixtures
├── unit/
│   ├── test_models.py    # Pure logic, no I/O
│   └── test_services.py  # Mocked dependencies
├── integration/
│   ├── conftest.py       # DB fixtures
│   ├── test_api.py       # Full API tests
│   └── test_repos.py     # Real database queries
└── e2e/
    └── test_workflows.py # Full user workflows
```

Patterns:
1. **Fixture composition** — small fixtures composed into larger ones
2. **Dependency injection** — override FastAPI deps for testing
3. **Parametrize** — data-driven tests with readable IDs
4. **Markers** — categorize tests for selective running
5. **Mock boundaries** — mock at service boundaries, not internal details'''
    ),
    (
        "testing/mocking-patterns",
        "Show Python mocking patterns: unittest.mock, monkeypatch, freezegun, responses, and when to mock vs not mock.",
        '''Mocking patterns and anti-patterns:

```python
from unittest.mock import Mock, MagicMock, AsyncMock, patch, call
from datetime import datetime, timezone
import pytest

# --- Basic mocking ---

# Mock object with spec (type-safe mocking)
mock_repo = Mock(spec=UserRepository)
mock_repo.get_by_id.return_value = User(id="1", name="Alice")

# Verify calls
mock_repo.get_by_id.assert_called_once_with("1")
mock_repo.get_by_id.assert_called()
mock_repo.save.assert_not_called()

# Side effects
mock_repo.get_by_id.side_effect = [
    User(id="1", name="Alice"),    # First call
    User(id="2", name="Bob"),      # Second call
    NotFoundError("No user"),       # Third call raises
]

# Side effect as function
def fake_get(user_id):
    users = {"1": User(id="1", name="Alice")}
    if user_id not in users:
        raise NotFoundError(f"User {user_id} not found")
    return users[user_id]

mock_repo.get_by_id.side_effect = fake_get


# --- patch: replace imports ---

# Patch where it's USED, not where it's DEFINED
# If app/services.py imports: from app.email import send_email
# Patch: app.services.send_email (not app.email.send_email)

@patch("app.services.user_service.send_email")
@patch("app.services.user_service.generate_id", return_value="user-abc")
async def test_create_user(mock_gen_id, mock_email):
    service = UserService(repo=mock_repo)
    user = await service.create_user("Alice", "alice@test.com")

    assert user.id == "user-abc"
    mock_email.assert_called_once()

# Context manager form
async def test_with_context():
    with patch("app.services.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await service.create_order(items=[])
        assert result.created_at == datetime(2024, 1, 1, tzinfo=timezone.utc)


# --- monkeypatch (pytest-native) ---

def test_with_env_vars(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key-123")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("SECRET", raising=False)

    config = load_config()
    assert config.api_key == "test-key-123"

def test_with_replaced_function(monkeypatch):
    # Replace function
    monkeypatch.setattr("app.utils.get_current_time",
                        lambda: datetime(2024, 6, 15, tzinfo=timezone.utc))

    # Replace attribute
    monkeypatch.setattr(settings, "MAX_RETRIES", 1)


# --- Time mocking with freezegun ---

from freezegun import freeze_time

@freeze_time("2024-06-15 12:00:00")
def test_time_dependent():
    now = datetime.now(timezone.utc)
    assert now.year == 2024
    assert now.month == 6

@freeze_time("2024-06-15")
async def test_token_expiry():
    token = create_token(expires_in=3600)
    assert not is_expired(token)

    with freeze_time("2024-06-15 02:00:00"):
        assert is_expired(token)


# --- HTTP mocking with respx ---

import respx
import httpx

@respx.mock
async def test_external_api():
    respx.get("https://api.example.com/users/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "Alice"})
    )
    respx.post("https://api.example.com/notify").mock(
        return_value=httpx.Response(202)
    )

    result = await external_service.get_and_notify("1")
    assert result["notified"] is True


# --- When NOT to mock ---

# DON'T mock:
# - Simple data transformations (test the real logic)
# - Value objects and dataclasses
# - Standard library functions (unless testing error paths)
# - The thing you're testing (obviously)

# DO mock:
# - External HTTP APIs
# - Databases (in unit tests; use real DB in integration tests)
# - File system (when testing logic, not I/O)
# - Time/randomness (for deterministic tests)
# - Email/SMS/notification services

# PREFER fakes over mocks when possible:
class FakeUserRepository:
    """In-memory implementation (more realistic than Mock)."""
    def __init__(self):
        self.users = {}

    async def save(self, user):
        self.users[user.id] = user
        return user

    async def get_by_id(self, user_id):
        return self.users.get(user_id)
```

Rules:
1. **Patch where used** — not where defined
2. **Use spec** — `Mock(spec=Class)` catches typos in attribute names
3. **Fakes > Mocks** — in-memory implementations are more realistic
4. **Mock at boundaries** — external services, not internal implementation
5. **Don't over-mock** — if everything is mocked, you're testing nothing'''
    ),
]
"""
