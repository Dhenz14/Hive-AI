"""Python testing — pytest advanced, fixtures, mocking, and parametrize patterns."""

PAIRS = [
    (
        "testing/pytest-advanced",
        "Show advanced pytest patterns: fixtures, parametrize, markers, conftest, and plugin hooks.",
        '''Advanced pytest patterns:

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import AsyncGenerator


# --- Fixtures with scope and teardown ---

@pytest.fixture(scope="session")
def db_engine():
    """Create DB engine once per test session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Fresh DB session per test with rollback."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()  # Undo all changes
    connection.close()


@pytest.fixture
async def async_client(app):
    """Async HTTP test client."""
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# --- Factory fixtures ---

@pytest.fixture
def make_user(db_session):
    """Factory fixture — create users with custom attributes."""
    created = []

    def _make_user(name="Test User", email=None, **kwargs):
        email = email or f"{name.lower().replace(' ', '.')}@test.com"
        user = User(name=name, email=email, **kwargs)
        db_session.add(user)
        db_session.flush()
        created.append(user)
        return user

    yield _make_user

    # Cleanup
    for user in created:
        db_session.delete(user)


# --- Parametrize ---

@pytest.mark.parametrize("input_val,expected", [
    ("hello", "HELLO"),
    ("World", "WORLD"),
    ("", ""),
    ("123abc", "123ABC"),
])
def test_uppercase(input_val, expected):
    assert input_val.upper() == expected


# Parametrize with IDs
@pytest.mark.parametrize("status_code,should_retry", [
    pytest.param(200, False, id="success"),
    pytest.param(429, True, id="rate-limited"),
    pytest.param(500, True, id="server-error"),
    pytest.param(400, False, id="client-error"),
], ids=str)
def test_retry_logic(status_code, should_retry):
    assert should_retry_request(status_code) == should_retry


# Parametrize fixtures
@pytest.fixture(params=["sqlite", "postgres"])
def database(request):
    if request.param == "sqlite":
        return SQLiteDB(":memory:")
    return PostgresDB("postgresql://test@localhost/test")


# --- Markers ---

@pytest.mark.slow
def test_full_pipeline():
    """Run with: pytest -m slow"""
    ...

@pytest.mark.integration
async def test_external_api():
    """Run with: pytest -m integration"""
    ...

@pytest.mark.skipif(
    not os.environ.get("REDIS_URL"),
    reason="Redis not available",
)
def test_redis_cache():
    ...

@pytest.mark.xfail(reason="Known bug #123")
def test_edge_case():
    ...


# --- conftest.py (shared fixtures) ---

# tests/conftest.py
@pytest.fixture(autouse=True)
def reset_state():
    """Auto-run before each test."""
    cache.clear()
    yield
    cache.clear()

@pytest.fixture
def mock_time():
    """Freeze time for deterministic tests."""
    with patch("time.time", return_value=1700000000.0):
        yield


# --- Async testing ---

@pytest.mark.asyncio
async def test_async_endpoint(async_client, make_user):
    user = make_user(name="Alice")

    response = await async_client.get(f"/api/users/{user.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Alice"


# --- Mocking ---

async def test_service_with_mock():
    # Mock external dependency
    mock_repo = AsyncMock()
    mock_repo.get.return_value = {"id": "1", "name": "Alice"}

    service = UserService(repo=mock_repo)
    user = await service.get_user("1")

    assert user["name"] == "Alice"
    mock_repo.get.assert_called_once_with("1")


def test_with_patch():
    with patch("myapp.services.send_email") as mock_email:
        mock_email.return_value = True
        result = register_user("alice@test.com", "password123")
        assert result["success"]
        mock_email.assert_called_once()


# --- Custom assertion helpers ---

def assert_valid_user(data: dict):
    """Reusable assertion for user shape."""
    assert "id" in data
    assert "name" in data
    assert "email" in data
    assert "@" in data["email"]

def assert_api_error(response, status: int, error_code: str):
    assert response.status_code == status
    body = response.json()
    assert body["error"] == error_code
```

Pytest patterns:
1. **Factory fixtures** — `make_user()` creates test data with custom attributes
2. **`parametrize`** — run same test with multiple inputs (table-driven)
3. **Scoped fixtures** — `session` scope for expensive setup, `function` for isolation
4. **`autouse=True`** — auto-run fixture for every test (reset state)
5. **`AsyncMock`** — mock async methods, assert `await` calls'''
    ),
    (
        "testing/property-based",
        "Show property-based testing with Hypothesis: strategies, stateful testing, and shrinking.",
        '''Property-based testing with Hypothesis:

```python
from hypothesis import given, assume, settings, example, note
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize
import json


# --- Basic property tests ---

@given(st.lists(st.integers()))
def test_sort_preserves_length(xs):
    """Sorting never changes the number of elements."""
    assert len(sorted(xs)) == len(xs)


@given(st.lists(st.integers(), min_size=1))
def test_sort_is_ordered(xs):
    """Every element is <= the next one."""
    result = sorted(xs)
    for a, b in zip(result, result[1:]):
        assert a <= b


@given(st.text())
def test_json_roundtrip(s):
    """Encoding then decoding JSON preserves the string."""
    assert json.loads(json.dumps(s)) == s


# --- Custom strategies ---

@st.composite
def user_strategy(draw):
    """Generate valid User objects."""
    name = draw(st.text(min_size=1, max_size=100,
                        alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))))
    email = draw(st.emails())
    age = draw(st.integers(min_value=0, max_value=150))
    return {"name": name.strip(), "email": email, "age": age}


@given(user_strategy())
def test_user_validation(user_data):
    """Valid user data always passes validation."""
    assume(len(user_data["name"].strip()) > 0)  # Skip empty names
    result = validate_user(user_data)
    assert result.is_valid


# --- Testing with examples ---

@given(st.integers(), st.integers())
@example(0, 0)        # Always test edge case
@example(-1, 1)       # Negative + positive
@example(2**31, 1)    # Large number
def test_addition_commutative(a, b):
    assert a + b == b + a


# --- Stateful testing ---

class StackMachine(RuleBasedStateMachine):
    """Test stack implementation against a model."""

    def __init__(self):
        super().__init__()
        self.stack = Stack()    # Implementation under test
        self.model = []         # Simple list as model

    @rule(value=st.integers())
    def push(self, value):
        self.stack.push(value)
        self.model.append(value)
        assert self.stack.size() == len(self.model)

    @rule()
    def pop(self):
        if not self.model:
            return  # Skip when empty
        actual = self.stack.pop()
        expected = self.model.pop()
        assert actual == expected

    @rule()
    def peek(self):
        if not self.model:
            return
        assert self.stack.peek() == self.model[-1]

    @rule()
    def check_size(self):
        assert self.stack.size() == len(self.model)

    @rule()
    def check_empty(self):
        assert self.stack.is_empty() == (len(self.model) == 0)


# Run: TestStack = StackMachine.TestCase


# --- Settings and profiles ---

@settings(
    max_examples=500,          # More examples (default 100)
    deadline=None,             # No per-example timeout
    suppress_health_check=[],  # Keep all health checks
)
@given(st.dictionaries(st.text(), st.integers()))
def test_dictionary_operations(d):
    # Test with many generated dicts
    assert len(d) == len(list(d.keys()))


# --- Useful strategies ---

# Numbers
st.integers(min_value=0, max_value=1000)
st.floats(allow_nan=False, allow_infinity=False)
st.decimals(min_value=0, max_value=10000, places=2)

# Strings
st.text(min_size=1, max_size=50)
st.from_regex(r"[A-Z]{2,4}-\\d{4}", fullmatch=True)  # "AB-1234"

# Collections
st.lists(st.integers(), min_size=1, max_size=100)
st.dictionaries(st.text(min_size=1), st.integers())
st.sets(st.integers(), min_size=1)

# Dates
st.dates()
st.datetimes()

# Composite
st.one_of(st.none(), st.integers(), st.text())  # Union type
st.tuples(st.text(), st.integers())
st.fixed_dictionaries({"name": st.text(), "age": st.integers(0, 150)})
```

Property-based testing:
1. **`@given`** — auto-generate hundreds of test inputs per run
2. **Shrinking** — on failure, Hypothesis finds minimal reproducing example
3. **`@st.composite`** — build custom generators from simpler strategies
4. **`RuleBasedStateMachine`** — test stateful systems against a model
5. **`@example()`** — always include specific edge cases alongside random inputs'''
    ),
    (
        "testing/integration-patterns",
        "Show integration testing patterns: test containers, API testing, and database testing.",
        '''Integration testing patterns:

```python
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


# --- Testcontainers (real services in Docker) ---

@pytest.fixture(scope="session")
def postgres():
    """Start PostgreSQL in Docker for tests."""
    with PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def redis():
    """Start Redis in Docker for tests."""
    with RedisContainer("redis:7") as r:
        yield r.get_connection_url()


@pytest.fixture(scope="session")
def app(postgres, redis):
    """Create app with real services."""
    from myapp import create_app
    return create_app(
        database_url=postgres,
        redis_url=redis,
    )


# --- API integration tests ---

@pytest.fixture
async def client(app) -> AsyncGenerator:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def auth_client(client) -> AsyncClient:
    """Client with authentication token."""
    response = await client.post("/api/auth/login", json={
        "email": "admin@test.com",
        "password": "testpassword123",
    })
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


class TestUserAPI:
    """Integration tests for user endpoints."""

    async def test_create_user(self, auth_client):
        response = await auth_client.post("/api/users", json={
            "name": "Alice",
            "email": "alice@test.com",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Alice"
        assert "id" in data

    async def test_create_user_duplicate_email(self, auth_client):
        # Create first user
        await auth_client.post("/api/users", json={
            "name": "Alice",
            "email": "alice@test.com",
        })

        # Duplicate should fail
        response = await auth_client.post("/api/users", json={
            "name": "Alice 2",
            "email": "alice@test.com",
        })
        assert response.status_code == 409

    async def test_list_users_pagination(self, auth_client):
        # Create 25 users
        for i in range(25):
            await auth_client.post("/api/users", json={
                "name": f"User {i}",
                "email": f"user{i}@test.com",
            })

        # First page
        response = await auth_client.get("/api/users?limit=10")
        data = response.json()
        assert len(data["items"]) == 10
        assert data["has_more"] is True

        # Second page
        cursor = data["next_cursor"]
        response = await auth_client.get(f"/api/users?limit=10&cursor={cursor}")
        data = response.json()
        assert len(data["items"]) == 10

    async def test_unauthenticated_returns_401(self, client):
        response = await client.get("/api/users")
        assert response.status_code == 401


# --- Database integration tests ---

class TestOrderRepository:
    """Test repository against real database."""

    @pytest.fixture(autouse=True)
    async def setup(self, db_session):
        self.repo = OrderRepository(db_session)
        self.user = await create_test_user(db_session)

    async def test_create_and_retrieve(self, db_session):
        order = await self.repo.create({
            "user_id": self.user.id,
            "total": 99.99,
            "items": [{"product_id": "p1", "quantity": 2}],
        })

        retrieved = await self.repo.get(order.id)
        assert retrieved is not None
        assert retrieved.total == 99.99
        assert len(retrieved.items) == 1

    async def test_filter_by_status(self, db_session):
        await self.repo.create({"user_id": self.user.id, "total": 10, "status": "active"})
        await self.repo.create({"user_id": self.user.id, "total": 20, "status": "completed"})
        await self.repo.create({"user_id": self.user.id, "total": 30, "status": "active"})

        active = await self.repo.list(status="active")
        assert len(active) == 2
        assert all(o.status == "active" for o in active)

    async def test_concurrent_updates(self, db_session):
        """Test optimistic locking."""
        order = await self.repo.create({
            "user_id": self.user.id, "total": 100,
        })

        # Simulate concurrent update conflict
        with pytest.raises(OptimisticLockError):
            await asyncio.gather(
                self.repo.update(order.id, {"total": 200}, version=1),
                self.repo.update(order.id, {"total": 300}, version=1),
            )
```

Integration testing patterns:
1. **Testcontainers** — real Postgres/Redis in Docker, auto-cleanup
2. **`auth_client` fixture** — authenticated client for protected endpoints
3. **Test classes** — group related tests with shared setup
4. **Pagination testing** — verify cursor navigation across pages
5. **Concurrency tests** — verify optimistic locking handles race conditions'''
    ),
]
"""
