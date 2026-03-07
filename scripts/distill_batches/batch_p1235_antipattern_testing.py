"""
Anti-pattern training pairs - Testing anti-patterns
Topics: testing implementation details, no assertions, flaky tests, testing mocks, snapshot overuse
"""

pairs = [
    {
        "instruction": r'''I wrote tests for my user service. They pass but break whenever I refactor. What am I doing wrong?

```python
def test_create_user():
    service = UserService()
    service.create_user("alice", "alice@test.com")

    # Verify internal state
    assert len(service._users_cache) == 1
    assert service._users_cache[0]._email_validated == False
    assert service._db_write_count == 1
    assert service._last_query == "INSERT INTO users (name, email) VALUES (?, ?)"
```''',
        "output": r'''<think>
Testing implementation details anti-pattern. The test reaches into private attributes (_users_cache, _db_write_count, _last_query) instead of testing the public behavior. Any internal refactoring (renaming a field, changing the cache structure, modifying the SQL) breaks this test even if the behavior is correct. Tests should verify WHAT the code does, not HOW it does it.
</think>

Your tests are coupled to the implementation, not the behavior. Every assertion checks a private internal detail:

- `_users_cache` -- what if you switch to Redis?
- `_db_write_count` -- what if you batch writes?
- `_last_query` -- what if you use an ORM instead of raw SQL?

All of these are valid refactors that don't change what the service does, but every one breaks your tests.

**The fix -- test behavior through the public interface:**

```python
def test_create_user():
    service = UserService()

    # Act
    user = service.create_user("alice", "alice@test.com")

    # Assert behavior, not internals
    assert user.name == "alice"
    assert user.email == "alice@test.com"

    # Verify the user can be retrieved (the observable effect)
    found = service.get_user_by_email("alice@test.com")
    assert found is not None
    assert found.name == "alice"

def test_create_duplicate_user_raises():
    service = UserService()
    service.create_user("alice", "alice@test.com")

    with pytest.raises(DuplicateUserError):
        service.create_user("bob", "alice@test.com")
```

**The difference:**
- Old tests answer: "Did the code use a cache list and run a specific SQL query?"
- New tests answer: "Can I create a user and retrieve them? Does it reject duplicates?"

The new tests survive any internal refactoring -- switch databases, change caching, rewrite the SQL -- as long as the behavior stays the same, the tests stay green.

**Rule of thumb:** If your test accesses anything with a leading underscore, you are probably testing implementation details. Test inputs and outputs through the public API.'''
    },
    {
        "instruction": r'''My test suite is all green. Here's one of my tests:

```python
def test_process_order():
    order = Order(id=1, items=["widget"], total=29.99)
    service = OrderService()
    service.process(order)
```''',
        "output": r'''<think>
Test with no assertions. This test calls process() but never checks any result or side effect. It only verifies that process() does not throw an exception. It will pass even if process() is completely broken -- as long as it doesn't crash. This is a false sense of security. The test suite is "green" but proves nothing.
</think>

This test has no assertions -- it only proves that `process()` doesn't throw an exception. It will pass even if:

- `process()` does nothing (empty function body)
- `process()` saves the wrong total
- `process()` marks the order as "cancelled" instead of "completed"
- `process()` charges the customer twice

A test without assertions is not a test. It is a smoke test at best, and a false sense of security at worst.

**The fix -- assert the expected outcomes:**

```python
def test_process_order_marks_completed():
    order = Order(id=1, items=["widget"], total=29.99)
    service = OrderService()

    result = service.process(order)

    assert result.status == "completed"
    assert result.charged_amount == 29.99

def test_process_order_creates_shipment():
    order = Order(id=1, items=["widget"], total=29.99)
    service = OrderService()

    service.process(order)

    shipment = service.get_shipment_for_order(1)
    assert shipment is not None
    assert shipment.items == ["widget"]

def test_process_order_sends_confirmation():
    email_sender = FakeEmailSender()
    service = OrderService(email_sender=email_sender)
    order = Order(id=1, items=["widget"], total=29.99)

    service.process(order)

    assert len(email_sender.sent) == 1
    assert email_sender.sent[0].subject == "Order Confirmed"
```

**Each test should answer a specific question:**
- "Does it mark the order completed?" -- assert status
- "Does it create a shipment?" -- assert shipment exists
- "Does it send a confirmation?" -- assert email was sent

One test per behavior, with clear assertions for each.'''
    },
    {
        "instruction": r'''My tests pass locally but fail randomly in CI. About 1 in 5 runs fails. Here's one of the flaky tests:

```python
def test_cache_expiry():
    cache = Cache(ttl_seconds=1)
    cache.set("key", "value")

    assert cache.get("key") == "value"

    time.sleep(1)

    assert cache.get("key") is None  # sometimes fails!

def test_api_response_time():
    start = time.time()
    response = client.get('/api/health')
    elapsed = time.time() - start

    assert response.status_code == 200
    assert elapsed < 0.1  # fails on slow CI machines
```''',
        "output": r'''<think>
Flaky tests caused by time dependence. The first test uses time.sleep(1) which is unreliable -- under CI load the sleep might not be exactly 1 second, or the TTL might expire slightly early/late. The second test asserts a hard time bound that depends on machine performance. Both tests introduce non-determinism. The fix is to mock time for the first and avoid timing assertions in the second.
</think>

Both tests depend on real-time behavior, which is inherently non-deterministic. CI machines have variable load -- a 1-second sleep might actually be 0.95 or 1.2 seconds, and API response times fluctuate.

**Problem 1: time.sleep() in tests.** The sleep might be slightly short (timer resolution) or the cache's internal clock might differ slightly. On a loaded CI machine, the test thread can be preempted, making the sleep much longer or shorter than expected.

**Fix -- mock time instead of sleeping:**

```python
from unittest.mock import patch
import time as time_module

def test_cache_expiry():
    fake_time = 1000.0

    def mock_time():
        return fake_time

    with patch.object(time_module, 'time', mock_time):
        cache = Cache(ttl_seconds=60)
        cache.set("key", "value")

        assert cache.get("key") == "value"

        # Advance fake clock past TTL
        fake_time = 1061.0
        assert cache.get("key") is None
```

This is instant (no sleeping), deterministic (fake clock is exact), and runs the same on any machine.

**Problem 2: Asserting response time.** Performance varies by machine. A fast dev laptop hits 0.05s, a loaded CI machine hits 0.15s.

**Fix -- test behavior, not performance:**

```python
def test_health_endpoint():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'healthy'

# Put performance tests in a separate suite with generous thresholds
# or use dedicated performance testing tools (locust, k6)
```

**General rule for flaky tests:** If a test uses `time.sleep()`, random data, network calls, or file system timing, it will eventually be flaky. Mock these dependencies or isolate them into a separate non-blocking test suite.'''
    },
    {
        "instruction": r'''I'm testing my PaymentService thoroughly with mocks:

```python
def test_charge_customer():
    mock_gateway = Mock()
    mock_gateway.charge.return_value = {'status': 'success', 'id': 'tx_123'}

    mock_db = Mock()
    mock_db.save_transaction.return_value = True

    mock_emailer = Mock()
    mock_emailer.send.return_value = True

    service = PaymentService(mock_gateway, mock_db, mock_emailer)
    result = service.charge_customer('cust_1', 50.00)

    mock_gateway.charge.assert_called_once_with('cust_1', 50.00)
    mock_db.save_transaction.assert_called_once()
    mock_emailer.send.assert_called_once()
    assert result == True
```

Is this a good test?''',
        "output": r'''<think>
Testing mocks instead of real behavior. Every dependency is mocked, every mock returns success, and the test only verifies that the mocks were called. This test proves the code calls three methods in order -- it does not prove the payment actually works. If the gateway API changes its response format, this test still passes. The mocks encode assumptions that may be wrong. Need at least integration tests with real (or fake) implementations.
</think>

This test has a subtle problem: it verifies that your code calls mocks in the right order, but it does not verify that payments actually work. You are testing the wiring, not the behavior.

**What this test misses:**
- If the real gateway returns `{'success': True}` instead of `{'status': 'success'}`, your mock still returns the old format, and the test passes while production breaks
- If `save_transaction` expects different arguments than what `charge_customer` passes, the mock happily accepts anything
- If the emailer needs a receipt object, not just a call, the mock doesn't care

**You are essentially testing:** "Does my code call three functions?" -- which you can see by reading the source code.

**Better approach -- use fakes with real logic:**

```python
class FakePaymentGateway:
    def __init__(self):
        self.charges = []

    def charge(self, customer_id, amount):
        if amount <= 0:
            return {'status': 'error', 'message': 'Invalid amount'}
        charge_id = f"tx_{len(self.charges) + 1}"
        self.charges.append({'customer': customer_id, 'amount': amount})
        return {'status': 'success', 'id': charge_id}

class FakeDatabase:
    def __init__(self):
        self.transactions = []

    def save_transaction(self, tx):
        self.transactions.append(tx)
        return True

def test_charge_customer():
    gateway = FakePaymentGateway()
    db = FakeDatabase()
    emailer = FakeEmailer()

    service = PaymentService(gateway, db, emailer)
    result = service.charge_customer('cust_1', 50.00)

    # Assert real outcomes, not mock calls
    assert result == True
    assert len(gateway.charges) == 1
    assert gateway.charges[0]['amount'] == 50.00
    assert len(db.transactions) == 1
    assert db.transactions[0]['amount'] == 50.00
```

Fakes have real logic that can catch real bugs. Supplement with a small number of integration tests against the real gateway's sandbox environment.'''
    },
    {
        "instruction": r'''We use snapshot testing for our React components. It catches regressions:

```javascript
test('UserProfile renders correctly', () => {
    const tree = renderer.create(
        <UserProfile user={{name: 'Alice', role: 'admin'}} />
    ).toJSON();
    expect(tree).toMatchSnapshot();
});

test('Dashboard renders correctly', () => {
    const tree = renderer.create(<Dashboard />).toJSON();
    expect(tree).toMatchSnapshot();
});

// We have 200+ snapshot tests like these
```

Lately the team just runs `--updateSnapshot` whenever tests fail. Is that a code smell?''',
        "output": r'''<think>
Snapshot test overuse. The team has 200+ snapshots that capture the entire rendered output. When anything changes (even CSS class names), dozens of snapshots fail. The team blindly updates them because reviewing 500-line snapshot diffs is impractical. At that point snapshots are not testing anything -- they are just rubber-stamped noise. Need targeted assertions instead of full-tree snapshots.
</think>

Yes, that is the snapshot trap. When your team reflexively runs `--updateSnapshot` without reviewing the diffs, the snapshots are providing zero protection. They are just noise that slows down development.

**Why full-component snapshots fail at scale:**
- A CSS class rename breaks 50 snapshots. Nobody reads 50 diffs -- they just update all.
- A new wrapper `<div>` changes every snapshot. Update all.
- Snapshots are 500 lines of HTML. Nobody reviews 500-line diffs in code review.
- The snapshots "pass" after update, so regressions go unnoticed.

**The fix -- replace most snapshots with targeted assertions:**

```javascript
test('UserProfile shows name and role badge', () => {
    render(<UserProfile user={{name: 'Alice', role: 'admin'}} />);

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toHaveClass('badge-admin');
});

test('UserProfile shows edit button for own profile', () => {
    render(<UserProfile user={mockUser} isOwnProfile={true} />);

    expect(screen.getByRole('button', {name: 'Edit Profile'}))
        .toBeInTheDocument();
});

test('UserProfile hides edit button for other profiles', () => {
    render(<UserProfile user={mockUser} isOwnProfile={false} />);

    expect(screen.queryByRole('button', {name: 'Edit Profile'}))
        .not.toBeInTheDocument();
});
```

**These tests are better because:**
- They test what matters to the user (text, buttons, behavior)
- A CSS class rename does not break them
- When they fail, the failure message tells you exactly what is wrong
- They survive refactors that change HTML structure but keep the same behavior

**Keep snapshots only for:** serialized data structures, API response shapes, or configuration objects -- things where the exact structure matters and diffs are short and reviewable.'''
    },
]
