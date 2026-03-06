"""Phase 3E: Metacognition — Learning From Mistakes (Part 2)

Scenarios: Missing error handling, broken tests, memory leaks,
API breaking changes, config bugs.
"""

PAIRS = [
    (
        "thinking/meta-mistakes-error-handling-swallowed",
        r'''Our payment processing silently fails for some users. They click "Pay" and nothing happens — no error message, no charge, no receipt. After investigating, we found this code:

```python
def process_payment(user_id, amount):
    try:
        stripe.Charge.create(amount=amount, customer=user_id)
        send_receipt_email(user_id, amount)
        update_order_status(user_id, 'paid')
    except Exception:
        pass
```

What's the lesson here?''',
        r'''<think>
I made an error: The except Exception: pass swallows ALL errors silently.

The mistake was: Using a bare except with pass to "handle" errors. When Stripe fails (declined card, invalid customer, network timeout), the exception is caught, ignored, and the user sees nothing. The payment fails silently.

The root cause was: Error handling laziness — using try/except as a way to prevent crashes instead of as a way to handle specific failure modes. The developer was afraid of unhandled exceptions and used pass to make them "go away."

Generalizable lesson: **Trace every error path.** For every line that can fail, ask: "What happens when this fails? Does the user know? Does the developer know? Can the system recover?"

Checklist item: Never write except: pass or except Exception: pass without logging. For every except block, answer: (1) Is the error logged? (2) Is the user notified? (3) Is the state consistent?

Similar situations:
1. except Exception: pass in any critical path
2. Ignoring return values from functions that can fail
3. Not checking HTTP response status codes
4. Database operations without error handling
5. Fire-and-forget async operations with no error callback
</think>

**The lesson: Trace every error path.**

`except Exception: pass` is the worst pattern in software — it makes bugs invisible.

**What happens with this code:**
- Card declined → user sees nothing, thinks they paid
- Network timeout → no charge, no error, no retry
- Invalid customer → silent failure, order stuck forever
- Stripe outage → no one knows until users complain

**Fix — handle each error specifically:**
```python
def process_payment(user_id, amount):
    try:
        charge = stripe.Charge.create(amount=amount, customer=user_id)
    except stripe.error.CardError as e:
        logger.warning(f"Card declined for user {user_id}: {e}")
        return {"error": "Your card was declined. Please try another card."}
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error for user {user_id}: {e}")
        return {"error": "Payment service temporarily unavailable. Please try again."}

    try:
        update_order_status(user_id, 'paid')
    except Exception as e:
        logger.critical(f"Payment succeeded but order update failed: {user_id}, charge={charge.id}")
        # Alert the team — this needs manual intervention
        alert_ops(f"Orphaned payment: charge {charge.id}, user {user_id}")
        raise

    send_receipt_email(user_id, amount)  # Non-critical, let it fail loudly
    return {"success": True, "charge_id": charge.id}
```

**The generalizable principle:**
For every line that can fail, answer:
1. **Is the error logged?** (Can developers diagnose it?)
2. **Is the user notified?** (Do they know what happened?)
3. **Is the state consistent?** (Payment charged but order not updated = data corruption)

**Checklist: Never write `except: pass` without:**
- Logging the error
- Notifying the user
- Ensuring state consistency

**Where this mistake recurs:**
- Background jobs that silently fail
- Webhook handlers that return 200 on error
- Import/migration scripts that skip bad records silently
- Async operations with no error callback'''
    ),
    (
        "thinking/meta-mistakes-broken-test-passes",
        r'''We had 100% test coverage on our user registration, but a critical bug slipped through: duplicate email addresses were allowed. Looking at the tests:

```python
def test_register_duplicate_email(client, db):
    # Register first user
    client.post('/register', json={
        'email': 'alice@test.com', 'password': 'pass123'
    })
    # Register second user with same email
    response = client.post('/register', json={
        'email': 'alice@test.com', 'password': 'pass456'
    })
    # Should return 409 Conflict
    assert response.status_code  # BUG: this just checks truthiness!
```

What's the lesson?''',
        r'''<think>
I made an error: The assertion checks that status_code is truthy, not that it equals 409.

The mistake was: `assert response.status_code` checks that the status code is a truthy value. ANY HTTP status code (200, 201, 409, 500) is truthy in Python. The assertion ALWAYS passes regardless of what the server returns. The test appears to verify duplicate email rejection but actually verifies nothing.

The root cause was: Not applying the mutation test: "If I break the code, does this test fail?" If the registration endpoint allows duplicates (returns 201), the test still passes because 201 is truthy.

Generalizable lesson: **A test should fail when the code is wrong.** After writing a test, mentally break the code and verify the test would catch it. If the test passes regardless of the implementation, it's not testing anything.

Checklist item: For every assertion, apply the mutation test: "If I change the expected behavior, does this specific assertion fail?"

Similar situations:
1. `assert result` instead of `assert result == expected_value`
2. `assert len(items)` instead of `assert len(items) == 5`
3. Tests with no assertions (just running the code)
4. Assertions on the wrong variable
5. Tests that mock everything and test the mocks, not the code
</think>

**The lesson: A test should fail when the code is wrong.**

**The bug:**
```python
assert response.status_code       # Checks truthiness — 200 is truthy, so this ALWAYS passes
assert response.status_code == 409 # Checks the actual value — catches the bug
```

Every HTTP status code (200, 201, 404, 409, 500) is a non-zero integer, which is truthy in Python. This test passes no matter what the server does.

**The mutation test principle:**
After writing a test, mentally break the code and ask: "Would this test catch it?"

```python
# Mental mutation: What if registration allows duplicates?
# Code returns 201 (success) for duplicate email
# Test: assert response.status_code → 201 is truthy → PASSES ← Bug not caught!
# Test: assert response.status_code == 409 → 201 != 409 → FAILS ← Bug caught!
```

**Fixed test:**
```python
def test_register_duplicate_email(client, db):
    client.post('/register', json={
        'email': 'alice@test.com', 'password': 'pass123'
    })
    response = client.post('/register', json={
        'email': 'alice@test.com', 'password': 'pass456'
    })
    assert response.status_code == 409  # Specific assertion
    assert 'already registered' in response.json.get('error', '')

    # Verify only one user exists
    users = User.query.filter_by(email='alice@test.com').count()
    assert users == 1  # Double-check at the data level
```

**The generalizable principle:**
Every assertion should be SPECIFIC enough that it fails when the code is wrong.

| Weak assertion (always passes) | Strong assertion (catches bugs) |
|-------------------------------|-------------------------------|
| `assert response.status_code` | `assert response.status_code == 409` |
| `assert result` | `assert result == expected` |
| `assert len(items)` | `assert len(items) == 5` |
| `assert response.json` | `assert response.json['name'] == 'Alice'` |

**Checklist for every test:**
1. Does the test have assertions? (Not just running code)
2. Are assertions specific? (Exact values, not truthiness)
3. Would the test fail if I break the code? (Mutation test)
4. Does the test verify at the RIGHT level? (Check DB, not just API response)'''
    ),
    (
        "thinking/meta-mistakes-memory-leak-listener",
        r'''Our Node.js server's memory grows until it crashes every few days. We traced it to this pattern in our WebSocket handler:

```javascript
io.on('connection', (socket) => {
    const user = getUser(socket.handshake.auth.token);

    // Subscribe to user's events
    eventBus.on('notification', (data) => {
        if (data.userId === user.id) {
            socket.emit('notification', data);
        }
    });

    socket.on('disconnect', () => {
        console.log(`${user.name} disconnected`);
    });
});
```

What went wrong?''',
        r'''<think>
I made an error: The event listener is registered but never removed.

The mistake was: Each new WebSocket connection adds a listener to eventBus. When the socket disconnects, the listener remains registered. After 10,000 connections, there are 10,000 listeners on the event bus, each holding a reference to the socket and user objects, preventing garbage collection.

The root cause was: Not tracking object ownership. The eventBus listener holds references to `socket` and `user`, but nobody removes the listener when the socket disconnects. The disconnect handler logs a message but doesn't clean up.

Generalizable lesson: **Track object ownership explicitly.** For every resource you create (listeners, timers, connections, file handles), ensure there's a corresponding cleanup. If you register, you must unregister.

Checklist item: For every addEventListener/on/subscribe, ensure there's a corresponding removeEventListener/off/unsubscribe in the teardown/disconnect/cleanup path.

Similar situations:
1. setInterval without clearInterval
2. Database connections opened without closing
3. File handles opened without closing
4. Thread pools created without shutdown
5. Subscriptions created without unsubscription
</think>

**The event listener is never removed.** Each connection adds a listener, disconnection doesn't remove it. After thousands of connections, thousands of orphaned listeners accumulate.

**The leak:**
```
Connection 1: eventBus.on('notification', handler1) ← never removed
Connection 2: eventBus.on('notification', handler2) ← never removed
...
Connection 10000: eventBus.on('notification', handler10000)
// 10,000 listeners, each holding references to socket + user
// GC can't collect any of them
```

**Fix — remove listener on disconnect:**
```javascript
io.on('connection', (socket) => {
    const user = getUser(socket.handshake.auth.token);

    const handler = (data) => {
        if (data.userId === user.id) {
            socket.emit('notification', data);
        }
    };

    eventBus.on('notification', handler);

    socket.on('disconnect', () => {
        eventBus.off('notification', handler);  // CLEANUP!
        console.log(`${user.name} disconnected`);
    });
});
```

**The generalizable lesson: Track object ownership explicitly.**

For every resource you acquire, ensure cleanup:

| Acquire | Release | Missing cleanup = |
|---------|---------|------------------|
| `eventBus.on()` | `eventBus.off()` | Memory leak |
| `setInterval()` | `clearInterval()` | CPU leak |
| `db.connect()` | `connection.close()` | Connection leak |
| `open(file)` | `file.close()` | File handle leak |
| `new Worker()` | `worker.terminate()` | Thread leak |

**Checklist for resource management:**
1. For every `on/addEventListener/subscribe`, is there a matching `off/removeEventListener/unsubscribe`?
2. For every `open/create/connect`, is there a matching `close/destroy/disconnect`?
3. Is cleanup triggered by the right event (disconnect, error, AND success)?
4. Use language patterns that automate cleanup: `with` in Python, `try-finally` in JS, RAII in C++

**Where this exact mistake appears:**
- React: `useEffect` without cleanup function
- Python: `signal.signal()` without removing old handlers
- Java: Thread pools created without `shutdown()`
- Any publish/subscribe system without unsubscribe'''
    ),
    (
        "thinking/meta-mistakes-api-breaking-change-rename",
        r'''We renamed a JSON field in our API from `user_name` to `username` and deployed. Within an hour, our mobile app crashed for all users, our partner integrations broke, and we had to do an emergency rollback. What's the lesson?''',
        r'''<think>
I made an error: Deploying a breaking API change without a migration path.

The mistake was: Renaming a field that external consumers depend on. The mobile app expects `user_name` — getting `undefined` for `user_name` crashed the app. Partner integrations expected `user_name` — getting it missing broke their data pipelines.

The root cause was: Not considering API consumers as stakeholders. The API is a contract — changing it unilaterally breaks everyone who depends on it. Unlike internal code where you can update all callers, API consumers are external and can't be updated simultaneously.

Generalizable lesson: **Version from day one. Treat every API response field as a contract.** Adding fields is non-breaking. Removing or renaming fields is breaking. Breaking changes require a migration period with both old and new fields.

Checklist item: Before modifying any API response, ask: "Who consumes this? Can they be updated simultaneously? If not, provide a migration path."

Similar situations:
1. Changing database column names that ORMs depend on
2. Renaming function parameters in a library's public API
3. Changing message format in a message queue
4. Changing environment variable names in deployment scripts
5. Renaming CSS class names that external stylesheets target
</think>

**The lesson: Version from day one. Every API response field is a contract.**

**What should have happened:**

```python
# Step 1: Add new field alongside old (non-breaking)
return {
    'user_name': user.name,  # Keep for existing consumers
    'username': user.name,   # New canonical name
}

# Step 2: Notify consumers, add deprecation headers
response.headers['Deprecation'] = 'true'

# Step 3: Monitor old field usage
# When no consumers use user_name → remove in next major version

# Step 4 (months later): Remove old field in v2
return {'username': user.name}
```

**The generalizable principle:** API changes fall into two categories:

| Change type | Examples | Impact |
|------------|---------|--------|
| Non-breaking (safe) | Adding a field, adding an endpoint | No consumer impact |
| Breaking (dangerous) | Removing a field, renaming a field, changing a type | Breaks consumers |

**Checklist before any API change:**
1. Is this additive (new field/endpoint)? → Ship it
2. Does it remove or rename anything? → Breaking change, needs migration
3. Who are the consumers? → Mobile apps can't be force-updated
4. Can all consumers be updated simultaneously? → If not, need a transition period
5. Do you have an API versioning strategy? → If not, create one now

**The migration pattern:**
```
v1 (current):   {"user_name": "Alice"}
Transition:     {"user_name": "Alice", "username": "Alice"}
v2 (future):    {"username": "Alice"}
```

**Where this same mistake appears:**
- Database schema changes (column renames break ORM mappings)
- Library API changes (renamed functions break callers)
- Message queue format changes (producers and consumers out of sync)
- Configuration key renames (deployment scripts break)'''
    ),
    (
        "thinking/meta-mistakes-config-bug-startup",
        r'''Our app worked in development but crashed in production with a cryptic error about an invalid database URL. The environment variable DATABSE_URL (typo!) was set correctly, but the app was reading DATABASE_URL (correct spelling) which was empty. It took us 3 hours to find this typo. What's the lesson?''',
        r'''<think>
I made an error: The environment variable name had a typo, and the app didn't validate config at startup.

The mistake was: The app silently accepted an empty DATABASE_URL and only crashed later when trying to connect to the database. If the app had validated that DATABASE_URL was present and non-empty at startup, the error would have been caught immediately with a clear message.

The root cause was: Validating configuration at the point of USE instead of at STARTUP. The typo existed the entire time, but the app started successfully and only failed when the first database query ran — which happened under user traffic, in production.

Generalizable lesson: **Validate config at startup, not at use.** Check all required environment variables, file paths, API keys, and connection strings when the app starts. Fail fast with clear error messages.

Checklist item: Before deployment, the app should validate every required config value at startup and fail immediately with a specific error message if any are missing.

Similar situations:
1. API key typo discovered only when the first API call fails (possibly hours after deploy)
2. File path misconfigured, discovered only when the first upload/read happens
3. Redis URL wrong, discovered only when the first cache operation runs
4. Feature flag misconfigured, discovered only when the feature is triggered
</think>

**The lesson: Validate config at startup, not at use.**

**What should have happened:**
```python
# At app startup — BEFORE handling any requests:
import os
import sys

REQUIRED_CONFIG = {
    'DATABASE_URL': 'PostgreSQL connection string',
    'REDIS_URL': 'Redis connection string',
    'SECRET_KEY': 'Application secret key',
    'STRIPE_API_KEY': 'Stripe payment API key',
}

def validate_config():
    missing = []
    for key, description in REQUIRED_CONFIG.items():
        value = os.environ.get(key)
        if not value:
            missing.append(f"  {key}: {description}")

    if missing:
        print("FATAL: Missing required environment variables:")
        print('\n'.join(missing))
        sys.exit(1)

validate_config()  # Called at import time — app won't start without config
```

**With this in place:**
```
$ python app.py
FATAL: Missing required environment variables:
  DATABASE_URL: PostgreSQL connection string
# App never starts. Error is obvious. Fixed in 30 seconds.
```

**Without validation:**
```
$ python app.py
# App starts successfully
# ...
# 15 minutes later, first user hits a page:
# sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) could not connect to server: Connection refused
# 3 hours of debugging
```

**The generalizable principle:**
> Fail fast, fail obviously, fail at startup.

**Checklist for config management:**
1. List ALL required config values
2. Validate presence at startup (not at first use)
3. Validate FORMAT where possible (URL format, numeric range, valid enum)
4. Fail with specific error messages ("DATABASE_URL is missing" not "connection refused")
5. Log the config keys (not values!) at startup for debugging

**Where this same mistake appears:**
- API keys with typos (fails on first API call, not at startup)
- File paths that don't exist (fails on first read, not at startup)
- Invalid port numbers (fails on first connection)
- SSL cert paths that are wrong (fails on first HTTPS request)'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
