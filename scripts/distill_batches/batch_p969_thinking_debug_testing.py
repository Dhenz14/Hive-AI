PAIRS = [
    ("thinking/debugging", r'''Our test suite has flaky tests that pass individually but fail when run together:

```
$ pytest tests/test_user.py::test_create_user -v
PASSED

$ pytest tests/test_user.py -v
test_list_users PASSED
test_create_user FAILED
test_delete_user PASSED
```

The test:
```python
# tests/test_user.py
users_db = []  # module-level shared state!

def test_list_users():
    users_db.clear()
    users_db.extend([{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}])
    assert len(users_db) == 2

def test_create_user():
    assert len(users_db) == 0  # FAILS! users_db still has 2 items from test_list_users
    users_db.append({'id': 3, 'name': 'Charlie'})
    assert len(users_db) == 1

def test_delete_user():
    users_db.clear()
    users_db.append({'id': 1, 'name': 'Alice'})
    users_db.pop(0)
    assert len(users_db) == 0
```

Tests share mutable module-level state. How do I fix this?''', r'''<think>
The issue is clear: `users_db` is a module-level mutable list shared between all tests. `test_list_users` adds 2 items, and when `test_create_user` runs next, the list still has those 2 items. `test_create_user` expects an empty list.

When run individually, `test_create_user` starts with an empty list because the module is freshly loaded.

The fix: use pytest fixtures to provide fresh state for each test.
</think>

The root cause is mutable module-level state (`users_db = []`) shared between tests. Each test modifies the list, and the mutations persist into subsequent tests. Test execution order determines which tests see what state, making results dependent on ordering.

**Why it passes individually:** When running a single test, the module is freshly imported and `users_db` starts empty. When running all tests together, they share the same module instance.

**Fix 1: Use pytest fixtures for isolated state**

```python
import pytest

@pytest.fixture
def users_db():
    """Provide a fresh empty list for each test."""
    db = []
    yield db
    db.clear()  # cleanup after test

def test_list_users(users_db):
    users_db.extend([{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}])
    assert len(users_db) == 2

def test_create_user(users_db):
    assert len(users_db) == 0  # fresh list every time!
    users_db.append({'id': 3, 'name': 'Charlie'})
    assert len(users_db) == 1

def test_delete_user(users_db):
    users_db.append({'id': 1, 'name': 'Alice'})
    users_db.pop(0)
    assert len(users_db) == 0
```

Each test receives its own fresh `users_db` list from the fixture.

**Fix 2: Use setup/teardown for class-based tests**

```python
class TestUsers:
    def setup_method(self):
        """Runs before each test method."""
        self.users_db = []

    def teardown_method(self):
        """Runs after each test method."""
        self.users_db.clear()

    def test_list_users(self):
        self.users_db.extend([{'id': 1}, {'id': 2}])
        assert len(self.users_db) == 2

    def test_create_user(self):
        assert len(self.users_db) == 0
```

**Fix 3: For database-backed tests, use transactions**

```python
@pytest.fixture
def db_session():
    """Each test runs in a transaction that gets rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()  # undo all changes made during the test
    connection.close()

def test_create_user(db_session):
    user = User(name='Alice')
    db_session.add(user)
    db_session.flush()
    assert db_session.query(User).count() == 1
    # Transaction rolls back after test -- database is clean for next test
```

**Detecting shared state issues:**

```bash
# Run tests in random order to expose state dependencies
pip install pytest-randomly
pytest --randomly-seed=12345

# Run tests in reverse order
pytest --reversed

# Run each test in a separate process (slow but guarantees isolation)
pip install pytest-forked
pytest --forked
```

**Common sources of shared state:**

```python
# Module-level mutable variables
cache = {}
counter = 0

# Class-level mutable attributes
class MyService:
    _instances = []  # shared across all tests

# Singletons
_instance = None
def get_instance():
    global _instance
    if _instance is None:
        _instance = create_instance()
    return _instance

# Environment variables
os.environ['API_KEY'] = 'test-key'  # affects all subsequent tests
```

**Prevention tips:**
- Never use module-level mutable state in tests
- Use fixtures with appropriate scope (function, class, module, session)
- Use `pytest-randomly` to detect ordering dependencies
- Use database transactions that roll back after each test
- Mock external services to avoid shared side effects
- Use `monkeypatch` fixture for environment variables (auto-reverts after test)
- Run `pytest -x --randomly-seed=random` in CI to catch flaky tests early'''),

    ("thinking/debugging", r'''My mocked function is not being called -- the test uses the real implementation:

```python
# myapp/services.py
from myapp.clients import ExternalAPI

def process_order(order_id):
    api = ExternalAPI()
    result = api.submit(order_id)
    return result['status']
```

```python
# tests/test_services.py
from unittest.mock import patch, MagicMock

@patch('myapp.clients.ExternalAPI')
def test_process_order(mock_api_class):
    mock_instance = MagicMock()
    mock_instance.submit.return_value = {'status': 'completed'}
    mock_api_class.return_value = mock_instance

    from myapp.services import process_order
    result = process_order('order-123')

    assert result == 'completed'
    mock_instance.submit.assert_called_once_with('order-123')
```

The test makes a real API call instead of using the mock. The mock is applied to the wrong module path.''', r'''<think>
The classic mock patching error. You must patch the name WHERE IT IS USED, not where it is defined.

`myapp/services.py` imports ExternalAPI with `from myapp.clients import ExternalAPI`. This creates a reference to ExternalAPI in the `myapp.services` namespace.

`@patch('myapp.clients.ExternalAPI')` patches ExternalAPI in `myapp.clients`, but `myapp.services` already has its own reference to the class. Patching the original does not affect the imported reference.

The fix: patch `myapp.services.ExternalAPI` instead.
</think>

The mock is patching the wrong location. You are patching `myapp.clients.ExternalAPI` (where it is defined), but you need to patch `myapp.services.ExternalAPI` (where it is used).

**Why this happens:**

When `myapp/services.py` executes `from myapp.clients import ExternalAPI`, Python creates a NEW reference named `ExternalAPI` in the `myapp.services` module namespace. This reference points to the original class object.

When you `@patch('myapp.clients.ExternalAPI')`, you replace the reference in `myapp.clients`, but `myapp.services` still has its own reference to the original class. The mock has no effect on `myapp.services`.

```
Before patching:
  myapp.clients.ExternalAPI  --> [Real ExternalAPI class]
  myapp.services.ExternalAPI --> [Real ExternalAPI class]

After @patch('myapp.clients.ExternalAPI'):
  myapp.clients.ExternalAPI  --> [Mock]
  myapp.services.ExternalAPI --> [Real ExternalAPI class]  <-- STILL REAL!
```

**Fix: Patch where it is USED, not where it is defined**

```python
@patch('myapp.services.ExternalAPI')  # patch in the USING module
def test_process_order(mock_api_class):
    mock_instance = MagicMock()
    mock_instance.submit.return_value = {'status': 'completed'}
    mock_api_class.return_value = mock_instance

    from myapp.services import process_order
    result = process_order('order-123')

    assert result == 'completed'
    mock_instance.submit.assert_called_once_with('order-123')
```

Now:
```
After @patch('myapp.services.ExternalAPI'):
  myapp.clients.ExternalAPI  --> [Real ExternalAPI class]
  myapp.services.ExternalAPI --> [Mock]  <-- process_order uses this!
```

**The rule: Patch where a name is LOOKED UP, not where it is DEFINED.**

```python
# If services.py uses: from myapp.clients import ExternalAPI
# Patch: @patch('myapp.services.ExternalAPI')

# If services.py uses: import myapp.clients
#   and calls: myapp.clients.ExternalAPI()
# Patch: @patch('myapp.clients.ExternalAPI')  (this IS where it's looked up)
```

**Alternative: Use dependency injection to avoid patching issues**

```python
# myapp/services.py
def process_order(order_id, api_client=None):
    if api_client is None:
        api_client = ExternalAPI()
    result = api_client.submit(order_id)
    return result['status']

# tests/test_services.py
def test_process_order():
    mock_api = MagicMock()
    mock_api.submit.return_value = {'status': 'completed'}

    result = process_order('order-123', api_client=mock_api)

    assert result == 'completed'
    mock_api.submit.assert_called_once_with('order-123')
```

No patching needed -- just pass the mock directly.

**Prevention tips:**
- Always patch at the usage site, not the definition site
- Use `import module` style (not `from module import name`) to make patching simpler
- Prefer dependency injection over monkey-patching mocks
- Use `@patch.object(module, 'name')` for clarity about what is being patched
- Add a print statement in the real function during debugging to verify if the mock is working
- Read the mock documentation section on "where to patch"'''),

    ("thinking/debugging", r'''Tests that pass locally fail in CI because of timezone differences:

```python
from datetime import datetime, date

def test_event_is_today():
    event_time = datetime(2024, 3, 15, 23, 30, 0)  # 11:30 PM
    assert is_today(event_time)

def is_today(dt):
    return dt.date() == date.today()
```

Locally (US/Eastern, UTC-4): test runs at 11:30 PM on March 15. `date.today()` returns March 15. PASS.
In CI (UTC): test runs at 3:30 AM on March 16. `date.today()` returns March 16. FAIL.

How do I make the test timezone-independent?''', r'''<think>
The test depends on the system timezone via `date.today()`. In UTC, "11:30 PM Eastern" is "3:30 AM UTC the next day." The test compares dates in the local timezone, which differs between local development (Eastern) and CI (UTC).

The fix: either freeze time in tests, or make the code timezone-aware and test with explicit timezones.
</think>

The test relies on `date.today()` which uses the system's local timezone. Your CI server runs in UTC, where 11:30 PM Eastern is already the next day. This is a common source of CI-only test failures.

**Fix 1: Use freezegun to freeze time (best for existing code)**

```python
from freezegun import freeze_time
from datetime import datetime, date

@freeze_time("2024-03-15 23:30:00")  # freezes date.today() and datetime.now()
def test_event_is_today():
    event_time = datetime(2024, 3, 15, 23, 30, 0)
    assert is_today(event_time)

@freeze_time("2024-03-16 00:30:00")
def test_event_is_not_today():
    event_time = datetime(2024, 3, 15, 23, 30, 0)
    assert not is_today(event_time)
```

`freezegun` replaces `datetime.now()`, `date.today()`, and `time.time()` with a fixed value, making tests deterministic regardless of timezone.

**Fix 2: Make the code timezone-aware**

```python
from datetime import datetime, timezone

def is_today(dt, tz=timezone.utc):
    """Check if datetime is today in the specified timezone."""
    now = datetime.now(tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz).date() == now.date()

# Tests:
from datetime import timezone, timedelta

EST = timezone(timedelta(hours=-5))

def test_event_is_today_utc():
    event_time = datetime(2024, 3, 15, 23, 30, tzinfo=timezone.utc)
    with freeze_time("2024-03-15 23:45:00+00:00"):
        assert is_today(event_time, tz=timezone.utc)

def test_event_is_today_eastern():
    event_time = datetime(2024, 3, 15, 23, 30, tzinfo=EST)
    with freeze_time("2024-03-15 23:45:00-05:00"):
        assert is_today(event_time, tz=EST)
```

**Fix 3: Inject the clock as a dependency**

```python
from datetime import date

def is_today(dt, today=None):
    if today is None:
        today = date.today()
    return dt.date() == today

# Test:
def test_event_is_today():
    event_time = datetime(2024, 3, 15, 23, 30, 0)
    assert is_today(event_time, today=date(2024, 3, 15))

def test_event_is_not_today():
    event_time = datetime(2024, 3, 15, 23, 30, 0)
    assert not is_today(event_time, today=date(2024, 3, 16))
```

**Set timezone in CI as a safety net:**

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      TZ: America/New_York  # or UTC for consistency
    steps:
      - run: pytest
```

But this is a band-aid -- the code should be timezone-explicit.

**Common timezone-dependent test failures:**

```python
# FRAGILE: depends on system timezone
date.today()
datetime.now()
time.time()

# ROBUST: explicit timezone
datetime.now(timezone.utc)
datetime.now(tz=ZoneInfo('America/New_York'))
```

**Prevention tips:**
- Always use `freezegun` or `time-machine` to control time in tests
- Make all date/time code explicitly timezone-aware
- Set `TZ=UTC` in CI environment as a baseline
- Never compare naive and aware datetimes
- Test edge cases: midnight, DST transitions, end of month, leap years
- Inject time dependencies rather than calling `datetime.now()` directly'''),

    ("thinking/debugging", r'''My pytest fixture teardown is running in the wrong order, causing database cleanup to fail:

```python
@pytest.fixture
def db_connection():
    conn = create_connection()
    yield conn
    conn.close()  # This runs AFTER db_session teardown? Or before?

@pytest.fixture
def db_session(db_connection):
    session = Session(bind=db_connection)
    yield session
    session.rollback()  # FAILS! Connection is already closed!
    session.close()
```

Error:
```
sqlalchemy.exc.ResourceClosedError: This Connection is closed
```

The connection is being closed before the session can rollback.''', r'''<think>
Pytest fixtures are torn down in the REVERSE order of their creation (LIFO). Since `db_session` depends on `db_connection`:

Setup order: db_connection (first) -> db_session (second)
Teardown order: db_session (first) -> db_connection (second)

Wait, that is the correct order. db_session should tear down first, then db_connection. The session rollback should happen before the connection closes.

Unless... there is something else going on. Let me reconsider.

Actually, pytest DOES tear down in reverse order of setup. So db_session teardown runs before db_connection teardown. This should work correctly.

But the error says the connection is already closed when session.rollback() runs. That means something else is closing the connection, or the fixture dependencies are not set up the way the user thinks.

Maybe the user has another fixture or conftest that is interfering, or maybe the fixtures have different scopes (e.g., db_connection is function-scoped but db_session is module-scoped or vice versa).

Let me present the general case of fixture teardown order and the common pitfalls.
</think>

Pytest fixtures tear down in reverse order of their setup (LIFO -- Last In, First Out). Since `db_session` depends on `db_connection`, the expected order is:

```
Setup:    db_connection -> db_session
Teardown: db_session -> db_connection
```

This should work correctly -- the session tears down before the connection. But there are several scenarios where this goes wrong:

**Cause 1: Different fixture scopes**

```python
@pytest.fixture(scope='module')  # lives for entire module
def db_connection():
    conn = create_connection()
    yield conn
    conn.close()

@pytest.fixture(scope='function')  # lives for one test
def db_session(db_connection):
    session = Session(bind=db_connection)
    yield session
    session.rollback()
    session.close()
```

If `db_connection` is module-scoped and `db_session` is function-scoped, the connection lives longer. But if a previous test's session committed and the connection has autocommit behavior, the state might be unexpected.

**Cause 2: Another fixture or finalizer closes the connection**

Check your `conftest.py` files for additional fixtures that might interact:

```python
# conftest.py -- might be closing the connection!
@pytest.fixture(autouse=True)
def cleanup():
    yield
    close_all_connections()  # kills the connection before session teardown!
```

**Cause 3: Exception during session teardown**

If `session.rollback()` itself raises an exception, `session.close()` never runs. This can cascade into the next test.

**Fix: Use a single fixture that manages both lifecycle stages**

```python
@pytest.fixture
def db_session():
    """Provide a transactional session that rolls back after each test."""
    conn = create_connection()
    transaction = conn.begin()
    session = Session(bind=conn)

    yield session

    # Teardown in explicit order:
    session.close()
    transaction.rollback()
    conn.close()
```

**Fix 2: Use nested transactions (savepoints)**

```python
@pytest.fixture(scope='session')
def db_connection():
    """Single connection for all tests."""
    conn = engine.connect()
    yield conn
    conn.close()

@pytest.fixture
def db_session(db_connection):
    """Each test gets a savepoint that rolls back."""
    transaction = db_connection.begin_nested()  # SAVEPOINT
    session = Session(bind=db_connection)

    yield session

    session.close()
    transaction.rollback()  # rolls back to SAVEPOINT, connection stays open
```

This is the recommended pattern for SQLAlchemy test isolation. The outer connection stays open across tests, while each test's changes are rolled back via SAVEPOINT.

**Fix 3: Use addfinalizer for explicit ordering**

```python
@pytest.fixture
def db_session(request, db_connection):
    session = Session(bind=db_connection)

    def cleanup():
        session.rollback()
        session.close()

    request.addfinalizer(cleanup)
    return session
```

`addfinalizer` runs during teardown but gives you explicit control over the cleanup order.

**Debugging fixture teardown:**

```python
@pytest.fixture
def db_connection():
    print("SETUP: db_connection")
    conn = create_connection()
    yield conn
    print("TEARDOWN: db_connection")
    conn.close()

@pytest.fixture
def db_session(db_connection):
    print("SETUP: db_session")
    session = Session(bind=db_connection)
    yield session
    print("TEARDOWN: db_session")
    session.close()
```

Run with `pytest -s` to see print output and verify the order.

**Prevention tips:**
- Keep fixture scopes consistent when fixtures depend on each other
- Use a single fixture for tightly coupled resources (connection + session)
- Use `request.addfinalizer` when you need explicit cleanup ordering
- Print or log fixture setup/teardown during debugging
- Use `pytest --setup-show` to visualize fixture setup and teardown order
- Never use `autouse=True` fixtures that modify shared state unpredictably'''),

    ("thinking/debugging", r'''My snapshot tests keep showing diffs that don't represent real changes:

```
FAILED tests/test_api.py::test_user_response - AssertionError: snapshot changed

-  Snapshot
+  Received

  {
      "id": 42,
      "name": "Alice",
-     "created_at": "2024-03-15T10:00:00Z",
+     "created_at": "2024-03-16T14:23:45Z",
      "last_login": null,
-     "session_id": "abc123def456",
+     "session_id": "xyz789ghi012",
  }
```

The snapshot was recorded on March 15 but the test runs on March 16 with different dynamic values. How do I handle dynamic data in snapshots?''', r'''<think>
Snapshot tests compare the current output to a saved "golden" output. Dynamic values like timestamps, UUIDs, and session IDs change every run, causing false failures.

The fix: either mask dynamic values before comparison, or use a snapshot library that supports matchers for dynamic fields.
</think>

Snapshot tests fail when output contains dynamic values that change between runs (timestamps, IDs, session tokens). You need to either normalize these values before comparison or use matchers that allow certain fields to vary.

**Fix 1: Normalize dynamic fields before snapshot**

```python
import re
from datetime import datetime

def normalize_response(data):
    """Replace dynamic values with stable placeholders."""
    normalized = data.copy()
    if 'created_at' in normalized:
        normalized['created_at'] = '<TIMESTAMP>'
    if 'session_id' in normalized:
        normalized['session_id'] = '<SESSION_ID>'
    if 'id' in normalized and isinstance(normalized['id'], int):
        # Keep IDs if they're deterministic from fixtures
        pass
    return normalized

def test_user_response(snapshot):
    response = client.get('/api/users/42')
    data = response.json()
    normalized = normalize_response(data)
    assert normalized == snapshot
```

Snapshot:
```json
{
    "id": 42,
    "name": "Alice",
    "created_at": "<TIMESTAMP>",
    "session_id": "<SESSION_ID>",
    "last_login": null
}
```

**Fix 2: Use inline snapshot matchers (pytest-snapshot or syrupy)**

```python
# Using syrupy with custom serializer
from syrupy.matchers import path_type

def test_user_response(snapshot):
    response = client.get('/api/users/42')
    data = response.json()

    assert data == snapshot(matcher=path_type({
        "created_at": (str,),       # any string is OK
        "session_id": (str,),       # any string is OK
    }))
```

**Fix 3: Use freezegun to control time**

```python
from freezegun import freeze_time

@freeze_time("2024-03-15T10:00:00Z")
def test_user_response(snapshot):
    response = client.get('/api/users/42')
    assert response.json() == snapshot
```

This makes timestamps deterministic, but you still need to handle session IDs.

**Fix 4: Use regex-based snapshot comparison**

```python
def assert_matches_snapshot(actual, snapshot_dict):
    """Compare with regex patterns for dynamic fields."""
    for key, expected in snapshot_dict.items():
        if isinstance(expected, str) and expected.startswith('REGEX:'):
            pattern = expected[6:]
            assert re.match(pattern, str(actual[key])), \
                f"Field '{key}': '{actual[key]}' does not match pattern '{pattern}'"
        else:
            assert actual[key] == expected, \
                f"Field '{key}': expected {expected}, got {actual[key]}"

def test_user_response():
    response = client.get('/api/users/42')
    data = response.json()

    assert_matches_snapshot(data, {
        'id': 42,
        'name': 'Alice',
        'created_at': 'REGEX:\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z',
        'session_id': 'REGEX:[a-z0-9]{12}',
        'last_login': None,
    })
```

**Fix 5: Seed random generators for deterministic IDs**

```python
import random
import uuid

@pytest.fixture(autouse=True)
def deterministic_ids():
    random.seed(42)
    # For UUIDs, mock the uuid module
    with patch('uuid.uuid4', side_effect=[
        uuid.UUID('12345678-1234-1234-1234-123456789abc'),
        uuid.UUID('87654321-4321-4321-4321-987654321cba'),
    ]):
        yield
```

**Best practices for snapshot testing:**

```python
# DO: snapshot the shape and static data
assert normalize(response.json()) == snapshot

# DO: validate dynamic fields separately
data = response.json()
assert data['name'] == 'Alice'
assert isinstance(data['created_at'], str)
assert len(data['session_id']) == 12

# DON'T: snapshot raw output with dynamic values
assert response.json() == snapshot  # will break every time!
```

**Prevention tips:**
- Always normalize dynamic values before snapshot comparison
- Use `freezegun` or `time-machine` to control timestamps
- Seed random number generators for deterministic test data
- Use snapshot matchers that support wildcards or type checking
- Review snapshot updates carefully -- `--snapshot-update` can mask real regressions
- Keep snapshot files in version control and review diffs in PRs'''),
]
