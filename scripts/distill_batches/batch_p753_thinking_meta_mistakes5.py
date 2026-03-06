"""Phase 3E: Metacognition — Learning From Mistakes (Part 5)

Additional pairs for scenarios 6-7: missing error handling, broken tests.
"""

PAIRS = [
    (
        "thinking/meta-mistakes-error-handling-async-fire-forget",
        r'''Our notification system silently fails and users don't get emails. No errors in our logs:

```python
async def create_order(order_data):
    order = await db.create(Order, **order_data)

    # Send notifications
    asyncio.create_task(send_order_email(order))
    asyncio.create_task(send_sms_notification(order))
    asyncio.create_task(update_analytics(order))

    return order
```

The order creation works fine but notifications are flaky.''',
        r'''<think>
I made an error: `asyncio.create_task()` fires and forgets — if the task raises an exception, it's silently swallowed (just a warning in debug mode). There's no error handling for the background tasks.

The mistake was: treating async tasks as fire-and-forget without realizing that exceptions in unattended tasks are silently lost. The task fails, nobody notices, and the user doesn't get their email.

The root cause was: not tracing the error path for background tasks. I handled errors in the main flow (order creation) but didn't consider what happens when background tasks fail. The mental model was "create_task = it'll just work" when it should be "create_task = it might fail and I need to handle that."

Generalizable lesson: Every code path that can fail must have explicit error handling. Fire-and-forget async tasks are especially dangerous because failures are silent by default. Either await the tasks, add error callbacks, or wrap them in try/except with logging.

Checklist item: For every `create_task()`, `Thread().start()`, or background job dispatch, ask: "What happens if this fails? Will anyone know?"

Similar situations where this lesson applies:
1. Background threads that crash silently
2. Celery tasks without error callbacks or retry configuration
3. JavaScript Promises without .catch() handlers
</think>

**The problem: `create_task()` silently swallows exceptions.** If `send_order_email` raises, the exception is lost.

**Fix — wrap background tasks with error handling:**
```python
async def safe_task(coro, task_name):
    try:
        await coro
    except Exception:
        logger.exception(f"Background task failed: {task_name}")
        # Optionally: send to error tracking (Sentry, etc.)

async def create_order(order_data):
    order = await db.create(Order, **order_data)

    asyncio.create_task(safe_task(send_order_email(order), "order_email"))
    asyncio.create_task(safe_task(send_sms_notification(order), "sms_notification"))
    asyncio.create_task(safe_task(update_analytics(order), "analytics"))

    return order
```

**Or if notifications must succeed — await them with error handling:**
```python
async def create_order(order_data):
    order = await db.create(Order, **order_data)

    results = await asyncio.gather(
        send_order_email(order),
        send_sms_notification(order),
        update_analytics(order),
        return_exceptions=True  # Don't cancel others if one fails
    )

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Notification {i} failed: {result}")

    return order
```

**The lesson: trace every error path, especially for background work.** If code can fail, you must explicitly decide what happens on failure. "Silently ignore" should be a conscious choice, not an accident.'''
    ),
    (
        "thinking/meta-mistakes-error-handling-retry-no-backoff",
        r'''Our service retries failed API calls but keeps getting rate-limited, making things worse:

```python
def call_external_api(payload, max_retries=5):
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, json=payload, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == max_retries - 1:
                raise
            continue  # Retry immediately
```''',
        r'''<think>
I made an error: retrying immediately without backoff or jitter. When the API is rate-limiting or temporarily overloaded, hammering it with immediate retries makes the problem worse — both for us and for the API.

The mistake was: treating retry as "just try again" instead of "wait and try again." Immediate retries on a rate-limited or overloaded service create a thundering herd effect and can trigger longer rate limits.

The root cause was: not thinking about the retry pattern from the server's perspective. The server is saying "I'm overwhelmed" and our response is to immediately send more requests.

Generalizable lesson: Retries without exponential backoff and jitter are often worse than no retries at all. They amplify load on struggling services and create positive feedback loops (more failures → more retries → more load → more failures).

Checklist item: Every retry loop must have: (1) exponential backoff, (2) jitter, (3) maximum retry count, and (4) specific exception filtering (don't retry 400 Bad Request).

Similar situations where this lesson applies:
1. Database reconnection loops hammering a recovering database
2. Queue consumers retrying failed messages without delay
3. Client-side polling that increases frequency when the server is slow
</think>

**Immediate retries on rate-limited APIs create a death spiral.** More retries → more load → more rate limiting → more retries.

**Fix — exponential backoff with jitter:**
```python
import random
import time

def call_external_api(payload, max_retries=5):
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, json=payload, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise

            # Don't retry client errors (4xx except 429)
            if hasattr(e, 'response') and e.response is not None:
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    raise  # Client error, retrying won't help

            # Exponential backoff with jitter
            base_delay = 2 ** attempt  # 1, 2, 4, 8, 16 seconds
            jitter = random.uniform(0, base_delay * 0.5)
            delay = base_delay + jitter
            time.sleep(delay)
```

**Why each piece matters:**
- **Exponential backoff**: gives the server time to recover
- **Jitter**: prevents synchronized retry storms from multiple clients
- **Exception filtering**: don't retry errors that will always fail (400, 403, 404)
- **Max retries**: prevent infinite retry loops

**The lesson: retries must be gentle.** A retry loop without backoff is an accidental DDoS against a struggling service. Every retry strategy needs backoff + jitter + exception filtering.'''
    ),
    (
        "thinking/meta-mistakes-error-handling-lost-context",
        r'''Our error logging shows generic messages that make debugging impossible:

```python
def process_payment(order):
    try:
        validate_order(order)
        charge = create_stripe_charge(order)
        update_order_status(order, charge)
        send_receipt(order)
    except Exception as e:
        logger.error(f"Payment failed: {e}")
        raise PaymentError("Payment processing failed")
```

When payments fail, all we see is "Payment failed: <some generic message>" and we can't tell which step failed or why.''',
        r'''<think>
I made an error: catching a broad Exception, logging only the message, and then re-raising a new exception that loses all context (stack trace, original exception, which step failed).

The mistake was: three errors compounding:
1. Catching bare Exception instead of specific exceptions
2. Logging only `str(e)` instead of the full traceback
3. Raising a new exception without chaining it to the original (`raise from`)

The root cause was: treating error handling as "something went wrong, log and re-raise" instead of "preserve maximum context for debugging." The handler destroys the information needed to fix the bug.

Generalizable lesson: Error handling should PRESERVE context, not destroy it. Log full tracebacks, chain exceptions with `raise ... from`, and include which operation failed. If you catch an exception, you must either handle it meaningfully or re-raise with full context.

Checklist item: For every except block, check: (1) Does the log include the full traceback? (2) Does the re-raised exception chain to the original? (3) Can I tell which specific operation failed?

Similar situations where this lesson applies:
1. API error responses that return generic "Internal Server Error" with no request ID
2. Catch-all error handlers that transform rich errors into generic ones
3. Error boundaries in React that swallow all context
</think>

**Your error handler destroys debugging information.** Here's the fix:

```python
def process_payment(order):
    try:
        validate_order(order)
    except ValidationError:
        logger.exception(f"Payment validation failed for order {order.id}")
        raise PaymentError(f"Validation failed for order {order.id}") from e

    try:
        charge = create_stripe_charge(order)
    except stripe.StripeError as e:
        logger.exception(f"Stripe charge failed for order {order.id}")
        raise PaymentError(f"Charge failed: {e.user_message}") from e

    try:
        update_order_status(order, charge)
    except DatabaseError as e:
        logger.exception(f"Status update failed for order {order.id}, charge {charge.id}")
        raise PaymentError(f"Status update failed for order {order.id}") from e

    send_receipt(order)  # Non-critical, let it fail naturally
```

**Three fixes applied:**

1. **`logger.exception()` instead of `logger.error()`** — logs the full traceback automatically
2. **Specific exceptions** instead of bare `except Exception` — each step catches what it can actually produce
3. **`raise ... from e`** — chains the original exception so the full cause is visible

**What the old code logged:** `"Payment failed: connection refused"`
**What the new code logs:** Full traceback showing exactly which function failed, on which line, with the complete call stack.

**The lesson: error handling should add context, not remove it.** Every catch block should answer: what were we trying to do, with what data, and what specifically went wrong?'''
    ),
    (
        "thinking/meta-mistakes-broken-test-mock-everything",
        r'''Our tests pass but the code is broken in production. Here's an example:

```python
def test_create_user():
    with patch('app.services.db.create') as mock_create, \
         patch('app.services.send_email') as mock_email, \
         patch('app.services.generate_token') as mock_token:

        mock_create.return_value = User(id=1, email="test@example.com")
        mock_token.return_value = "fake-token"

        result = create_user("test@example.com", "password123")

        mock_create.assert_called_once()
        mock_email.assert_called_once()
        assert result.id == 1
```

The test passes, but in production, `create_user` fails because we recently changed the database schema and `db.create` now requires a `username` field. The test didn't catch it because it mocked the database.''',
        r'''<think>
I made an error: the test mocks every dependency, so it tests nothing but the wiring between mocks. It can't detect real integration issues like schema changes.

The mistake was: over-mocking — replacing every real component with a fake, leaving only the glue code tested. The mock returns a User object regardless of whether the real database call would succeed, so schema changes are invisible to the test.

The root cause was: confusing "isolation" with "usefulness." Unit tests with mocks verify that functions call other functions correctly. But they can't verify that the actual integrations work. When every dependency is mocked, the test becomes a tautology — it tests that the code does what the mocks are configured to allow.

Generalizable lesson: A test should fail when the code is wrong. If a breaking change (like a schema migration) doesn't cause test failures, the tests aren't testing what matters. Use mocks sparingly — mock external services (Stripe, email) but use real databases (via test fixtures or in-memory SQLite).

Checklist item: After writing a test, ask: "If I break the implementation, will this test fail?" If the answer is "only if I change the function's call pattern," the test is too coupled to mocks.

Similar situations where this lesson applies:
1. Mocking HTTP clients when testing API integrations
2. Mocking file system operations when testing file processing
3. Mocking the ORM when testing database query logic
</think>

**Your test tests the mocks, not the code.** It will pass even if `create_user` is completely broken.

**What the test actually verifies:**
- ✅ `db.create` is called (but not that it works)
- ✅ `send_email` is called (but not that it sends)
- ✅ The mock returns what you told it to
- ❌ The actual database schema is compatible
- ❌ The actual email sends correctly
- ❌ The actual token generation works

**Fix — use a real test database, mock only external services:**
```python
@pytest.fixture
def test_db():
    """Use real database with test schema."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()

def test_create_user(test_db):
    with patch('app.services.send_email') as mock_email:  # Mock only external service
        result = create_user("test@example.com", "password123", db=test_db)

        assert result.id is not None
        assert result.email == "test@example.com"

        # Verify it's actually in the database
        saved = test_db.query(User).get(result.id)
        assert saved is not None
        assert saved.email == "test@example.com"

        mock_email.assert_called_once()
```

**Mock hierarchy (what to mock and what not to):**
- **Never mock**: Database, file system, your own code
- **Sometimes mock**: Slow computations, time-dependent operations
- **Always mock**: External APIs (Stripe, email, SMS), network calls

**The lesson: a test should fail when the code is wrong.** If you can break the implementation without breaking the test, the test is worthless. Mock boundaries, not internals.'''
    ),
    (
        "thinking/meta-mistakes-broken-test-not-testing-edge",
        r'''My sort function passes all tests but a user reported it crashes on empty input:

```python
def sort_by_priority(items):
    return sorted(items, key=lambda x: x['priority'])

# Tests:
def test_sort_by_priority():
    items = [
        {"name": "C", "priority": 3},
        {"name": "A", "priority": 1},
        {"name": "B", "priority": 2},
    ]
    result = sort_by_priority(items)
    assert result[0]["name"] == "A"
    assert result[-1]["name"] == "C"

def test_sort_single_item():
    items = [{"name": "A", "priority": 1}]
    result = sort_by_priority(items)
    assert len(result) == 1
```

Production crash: `sort_by_priority([])` works but `sort_by_priority(None)` and items with missing 'priority' key crash.''',
        r'''<think>
I made an error: I only tested the happy path — a well-formed list with valid items. I didn't test boundary cases or invalid inputs.

The mistake was: writing tests that confirm the code works when everything is correct, but not tests that verify behavior when things are wrong. The function is called with None and with items missing the 'priority' key in production — neither case is tested.

The root cause was: testing only what I expected, not what could happen. Good tests should include: empty input, None input, missing keys, invalid types, and extreme values. These are the cases that actually cause production crashes.

Generalizable lesson: Tests must cover boundary conditions and error cases, not just happy paths. The bugs that reach production are almost never "normal input produces wrong output" — they're "unexpected input causes crash." Specifically test: None, empty, missing fields, wrong types, and extreme values.

Checklist item: For every function test, add at least: empty input, None input, and one "malformed" input. If the function processes objects/dicts, test with missing keys.

Similar situations where this lesson applies:
1. API endpoint tests that only send valid JSON
2. Form validation tests that only use valid form data
3. Parser tests that only parse well-formed input
</think>

**Your tests only cover the happy path.** Add edge cases:

```python
def test_sort_empty():
    assert sort_by_priority([]) == []

def test_sort_none_input():
    # Decide: should this return [] or raise TypeError?
    with pytest.raises(TypeError):
        sort_by_priority(None)

def test_sort_missing_priority():
    items = [{"name": "A"}, {"name": "B", "priority": 1}]
    with pytest.raises(KeyError):
        sort_by_priority(items)

def test_sort_none_priority():
    items = [{"name": "A", "priority": None}, {"name": "B", "priority": 1}]
    with pytest.raises(TypeError):
        sort_by_priority(items)

def test_sort_duplicate_priorities():
    items = [
        {"name": "A", "priority": 1},
        {"name": "B", "priority": 1},
    ]
    result = sort_by_priority(items)
    assert len(result) == 2  # Both present, order stable
```

**If you want graceful handling instead of crashes:**
```python
def sort_by_priority(items):
    if not items:
        return []
    return sorted(items, key=lambda x: x.get('priority', float('inf')))
```

**The edge case checklist for any function:**
1. Empty input (`[]`, `""`, `{}`)
2. None/null input
3. Single element
4. Missing fields / keys
5. Invalid types
6. Duplicate values
7. Very large input

**The lesson: production bugs come from edge cases, not happy paths.** Your tests should answer: "What's the worst thing someone could pass to this function?"'''
    ),
    (
        "thinking/meta-mistakes-broken-test-time-dependent",
        r'''This test passes locally but fails intermittently in CI:

```python
def test_token_not_expired():
    token = create_token(user_id=1, expires_in=timedelta(seconds=1))
    assert is_valid_token(token) is True

def test_token_expired():
    token = create_token(user_id=1, expires_in=timedelta(seconds=1))
    time.sleep(2)
    assert is_valid_token(token) is False
```

It fails maybe 10% of the time. Sometimes `test_token_not_expired` fails saying the token is expired, and sometimes `test_token_expired` passes when it shouldn't.''',
        r'''<think>
I made an error: the test depends on real wall-clock time, which is unreliable in CI environments. CI runners are often slower, under load, or have clock skew.

The mistake was: using `time.sleep()` and relying on tight timing margins in tests. A 1-second token expiry with a sleep(2) assumes the test runs instantly up to the sleep, which isn't guaranteed on a loaded CI server.

The root cause was: testing time-dependent behavior with real time instead of controlling time. Slow CI runners, GC pauses, or context switching can make a "1 second" token expire in less than 1 second, or make the 2-second sleep not be enough.

Generalizable lesson: Never depend on real wall-clock time in tests. Use dependency injection or mocking to control time. Tests that use `time.sleep()` with tight margins are inherently flaky.

Checklist item: If a test uses `time.sleep()` or `timedelta`, ask: "Would this test still pass if the system was 10x slower?" If not, mock time instead.

Similar situations where this lesson applies:
1. Tests that check "created less than 5 seconds ago"
2. Tests that verify rate limiting with real delays
3. Tests that check cache expiration timing
</think>

**The test is flaky because it depends on real wall-clock time.** CI runners are slow and timing-sensitive tests break.

**Fix — freeze time instead of sleeping:**
```python
from unittest.mock import patch
from datetime import datetime, timedelta
# Or use freezegun: from freezegun import freeze_time

def test_token_not_expired():
    now = datetime(2024, 1, 1, 12, 0, 0)
    with patch('app.auth.datetime') as mock_dt:
        mock_dt.utcnow.return_value = now
        token = create_token(user_id=1, expires_in=timedelta(hours=1))

        # Still "now" — token is valid
        assert is_valid_token(token) is True

def test_token_expired():
    now = datetime(2024, 1, 1, 12, 0, 0)
    later = now + timedelta(hours=2)

    with patch('app.auth.datetime') as mock_dt:
        mock_dt.utcnow.return_value = now
        token = create_token(user_id=1, expires_in=timedelta(hours=1))

        # Jump forward 2 hours — token is expired
        mock_dt.utcnow.return_value = later
        assert is_valid_token(token) is False
```

**Or with freezegun (cleaner):**
```python
from freezegun import freeze_time

@freeze_time("2024-01-01 12:00:00")
def test_token_not_expired():
    token = create_token(user_id=1, expires_in=timedelta(hours=1))
    assert is_valid_token(token) is True

@freeze_time("2024-01-01 12:00:00")
def test_token_expired():
    token = create_token(user_id=1, expires_in=timedelta(hours=1))
    with freeze_time("2024-01-01 14:00:00"):  # Jump 2 hours
        assert is_valid_token(token) is False
```

**Why this is better:**
- Zero `time.sleep()` — tests run instantly
- Deterministic — passes on any machine, any load
- Tests exact boundaries — can test "1 second before expiry" vs "1 second after"

**The lesson: tests that use `time.sleep()` are almost always flaky.** Mock time instead. Tests should be deterministic and fast.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
