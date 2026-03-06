"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 6/6)
Try wrong approach first, hit the wall, recover with better solution:
hardcoded to plugin architecture, REST to event-driven, naive cron to distributed scheduler,
manual testing to property-based testing."""

PAIRS = [
    (
        "thinking/backtrack-hardcoded-to-plugins",
        "I need to support multiple payment providers (Stripe, PayPal, Square). Right now everything is Stripe-specific. When I try to add PayPal, my code becomes a massive if/else chain. What's the pattern?",
        r'''<think>
Let me trace through the obvious approach and see why it fails.

First attempt: if/else for each provider.

```python
def process_payment(provider, amount, card_token):
    if provider == "stripe":
        stripe.Charge.create(amount=amount, source=card_token)
    elif provider == "paypal":
        paypal.Payment.create({"amount": amount, "token": card_token})
    elif provider == "square":
        square.payments.create_payment(amount=amount, source_id=card_token)
```

This "works" for 3 providers. But:
1. Every function that touches payments needs the same if/else
2. process_payment, refund_payment, get_payment_status, create_customer, add_card...
3. Each has 3+ branches, each growing with every new provider
4. Testing requires mocking all providers in every test
5. Adding provider #4 means editing 10+ functions

Second attempt: separate modules per provider.

```python
# stripe_payments.py
def process(amount, token): ...
def refund(payment_id): ...

# paypal_payments.py
def process(amount, token): ...
def refund(payment_id): ...
```

Better separation, but:
- How does calling code know which module to use? Still needs if/else
- No guarantee that all modules have the same functions
- If paypal_payments is missing `refund()`, you get a runtime error

Let me backtrack. The real problem is: I need a CONTRACT (interface) that all providers implement, and the calling code should work with ANY provider without knowing which one.

This is the Strategy Pattern / Plugin Architecture:
1. Define an interface (what all providers must implement)
2. Each provider implements the interface
3. Calling code depends on the interface, not the provider
4. Provider is selected at configuration time, not in business logic
</think>

The if/else chain is a dead end that gets worse with every new provider. Let me show you why the obvious fix also fails, then the clean solution.

**Why if/else chains and separate modules both fail:**

```python
# Attempt 1: if/else everywhere (doesn't scale)
def process_payment(provider, amount, token):
    if provider == "stripe": ...
    elif provider == "paypal": ...  # Every function needs this

def refund_payment(provider, payment_id):
    if provider == "stripe": ...
    elif provider == "paypal": ...  # Duplicated in every function

# Adding Square: edit 10 functions. Adding Braintree: edit 10 more.
# This is O(providers × functions) code changes.

# Attempt 2: Separate modules (no contract enforcement)
import stripe_payments
import paypal_payments
# Calling code STILL needs if/else to pick the right module
# No guarantee both modules have the same functions
```

**The clean solution — Strategy Pattern:**

```python
from abc import ABC, abstractmethod

# Step 1: Define the contract (what ALL providers must implement)
class PaymentProvider(ABC):
    @abstractmethod
    def charge(self, amount_cents: int, token: str) -> str:
        """Charge the customer. Returns payment_id."""
        ...

    @abstractmethod
    def refund(self, payment_id: str, amount_cents: int = None) -> str:
        """Refund a payment. Returns refund_id."""
        ...

    @abstractmethod
    def get_status(self, payment_id: str) -> str:
        """Get payment status: 'succeeded', 'pending', 'failed'."""
        ...


# Step 2: Each provider implements the contract
class StripeProvider(PaymentProvider):
    def __init__(self, api_key: str):
        import stripe
        stripe.api_key = api_key

    def charge(self, amount_cents: int, token: str) -> str:
        charge = stripe.Charge.create(amount=amount_cents, source=token)
        return charge.id

    def refund(self, payment_id: str, amount_cents: int = None) -> str:
        refund = stripe.Refund.create(
            charge=payment_id,
            amount=amount_cents,
        )
        return refund.id

    def get_status(self, payment_id: str) -> str:
        charge = stripe.Charge.retrieve(payment_id)
        return charge.status


class PayPalProvider(PaymentProvider):
    def __init__(self, client_id: str, secret: str):
        self.client = PayPalClient(client_id, secret)

    def charge(self, amount_cents: int, token: str) -> str:
        result = self.client.create_payment(
            amount=amount_cents / 100,
            token=token,
        )
        return result["id"]

    def refund(self, payment_id: str, amount_cents: int = None) -> str:
        result = self.client.refund_payment(
            payment_id=payment_id,
            amount=amount_cents / 100 if amount_cents else None,
        )
        return result["refund_id"]

    def get_status(self, payment_id: str) -> str:
        result = self.client.get_payment(payment_id)
        status_map = {"COMPLETED": "succeeded", "PENDING": "pending"}
        return status_map.get(result["status"], "failed")


# Step 3: Business logic uses the interface, not the provider
class OrderService:
    def __init__(self, payment: PaymentProvider):  # Injected!
        self.payment = payment

    def checkout(self, order, token: str):
        payment_id = self.payment.charge(order.total_cents, token)
        order.payment_id = payment_id
        order.status = "paid"
        db.save(order)

    def refund_order(self, order):
        refund_id = self.payment.refund(order.payment_id)
        order.refund_id = refund_id
        order.status = "refunded"
        db.save(order)

    # ZERO if/else. Works with ANY provider.
    # Adding Square: write SquareProvider, change nothing here.


# Step 4: Wire up at configuration time (one place)
def create_payment_provider() -> PaymentProvider:
    provider_name = settings.PAYMENT_PROVIDER  # "stripe" or "paypal"
    if provider_name == "stripe":
        return StripeProvider(settings.STRIPE_API_KEY)
    elif provider_name == "paypal":
        return PayPalProvider(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")

# The ONLY if/else is here — in the factory function.
# Business logic has zero conditional branches.
```

**Testing is now trivial:**

```python
class FakeProvider(PaymentProvider):
    """Test double — no real API calls."""
    def __init__(self):
        self.charges = []

    def charge(self, amount_cents, token):
        self.charges.append((amount_cents, token))
        return f"fake_payment_{len(self.charges)}"

    def refund(self, payment_id, amount_cents=None):
        return f"fake_refund_{payment_id}"

    def get_status(self, payment_id):
        return "succeeded"

def test_checkout():
    fake = FakeProvider()
    service = OrderService(payment=fake)
    service.checkout(order, "tok_test")
    assert len(fake.charges) == 1
    assert order.status == "paid"
    # No Stripe/PayPal API calls. No mocking. Fast and reliable.
```

Adding a new provider: create one new class, implement the interface, add one line to the factory. Zero changes to business logic or tests.'''
    ),
    (
        "thinking/backtrack-rest-to-eventdriven",
        "Service A needs to notify Services B, C, and D when an order is created. I'm making HTTP POST calls to each one, but if Service C is down, the whole flow fails. How do I make this reliable?",
        r'''<think>
Let me trace through the incremental fixes and see where they hit walls.

Current approach: synchronous HTTP calls.
```python
def create_order(data):
    order = save_to_db(data)
    requests.post("http://service-b/notify", json=order_data)  # Inventory
    requests.post("http://service-c/notify", json=order_data)  # Email
    requests.post("http://service-d/notify", json=order_data)  # Analytics
    return order
```

Problem: Service C is down → request fails → entire order creation fails.
But the user's order was already saved! And Service B was already notified!
Inconsistent state.

First fix attempt: try/except around each call.
```python
def create_order(data):
    order = save_to_db(data)
    try:
        requests.post("http://service-b/notify", json=order_data)
    except:
        pass  # Silently ignore
    try:
        requests.post("http://service-c/notify", json=order_data)
    except:
        pass  # Service C will never know about this order!
    ...
```

Problems:
1. If Service C is down, it NEVER gets notified. Data loss.
2. No retry mechanism.
3. Still synchronous — user waits for all 3 calls even on success.
4. "pass" on exception = silent data loss.

Second fix attempt: add retries.
```python
for attempt in range(3):
    try:
        requests.post("http://service-c/notify", json=order_data)
        break
    except:
        time.sleep(2 ** attempt)
```

Better, but:
1. User now waits even longer (retries add seconds to response time)
2. If Service C is down for hours, 3 retries don't help
3. What if Service A crashes during retries? Lost notification.

Third fix attempt: background thread for retries.
```python
import threading
def notify_with_retry(url, data):
    threading.Thread(target=_retry_loop, args=(url, data)).start()
```

Problems:
1. If Service A restarts, all in-memory threads and pending retries are lost
2. No persistence — crash = lost notifications
3. Thread management gets complex at scale

Let me backtrack completely. The fundamental issue:
- Direct HTTP calls create TEMPORAL COUPLING (both services must be up at the same time)
- I need to DECOUPLE the notification from the order creation
- The notification should be PERSISTENT (survive crashes)
- The notification should be RETRIED until successful

This is what a message queue solves. Service A puts a message on a queue. Services B, C, D read from the queue at their own pace. If C is down, the message waits in the queue until C comes back.
</think>

Each incremental fix for synchronous HTTP notifications hits a new wall. Let me show the progression to the real solution.

**Why retries and try/except are dead ends:**

```python
# Fix 1: try/except (silent data loss)
try:
    requests.post("http://service-c/notify", json=data)
except:
    pass  # Service C NEVER learns about this order. Data lost.

# Fix 2: retries (user waits longer, still fails if service is down for hours)
for i in range(3):
    try:
        requests.post("http://service-c/notify", json=data, timeout=5)
        break
    except:
        time.sleep(2 ** i)  # User waits 1s + 2s + 4s = 7s extra

# Fix 3: background thread (lost on crash)
threading.Thread(target=notify_with_retry, args=(url, data)).start()
# If your server restarts → thread dies → notification lost
```

**The real solution — event-driven with a message queue:**

```python
# Service A: publish event, don't call services directly
def create_order(data):
    order = save_to_db(data)

    # Publish ONE event — don't know or care who listens
    message_broker.publish("order.created", {
        "order_id": order.id,
        "user_id": order.user_id,
        "items": [item.to_dict() for item in order.items],
        "total": str(order.total),
    })

    return order  # Returns immediately — user doesn't wait for B, C, D

# Service B (Inventory): subscribes independently
@consumer("order.created")
def handle_order(event):
    reserve_inventory(event["items"])

# Service C (Email): subscribes independently
@consumer("order.created")
def handle_order(event):
    send_confirmation(event["user_id"], event["order_id"])

# Service D (Analytics): subscribes independently
@consumer("order.created")
def handle_order(event):
    track_purchase(event)
```

**What happens when Service C is down:**

```
BEFORE (HTTP):
  A → B ✓ → C ✗ (down!) → User gets error, D never notified

AFTER (Message Queue):
  A → publishes event → returns to user immediately ✓

  Queue: [order.created: {order_id: 42, ...}]
         ↓ delivered to B → B processes ✓
         ↓ delivered to C → C is down → message stays in queue
         ↓ delivered to D → D processes ✓
         ... 2 hours later ...
         ↓ C comes back → message delivered → C processes ✓

  Nobody lost data. Nobody waited. Nobody even noticed C was down.
```

**Implementation with Redis Streams (simple):**

```python
import redis
import json

r = redis.Redis()

# Publisher (Service A)
def publish_event(event_type: str, data: dict):
    r.xadd(event_type, {"data": json.dumps(data)})

# Consumer (Service B — any service)
def consume_events(stream: str, group: str, consumer: str):
    # Create consumer group (once)
    try:
        r.xgroup_create(stream, group, id="0", mkstream=True)
    except redis.exceptions.ResponseError:
        pass

    while True:
        messages = r.xreadgroup(group, consumer, {stream: ">"}, count=10, block=5000)
        for _, entries in messages:
            for msg_id, fields in entries:
                try:
                    data = json.loads(fields[b"data"])
                    process_event(data)
                    r.xack(stream, group, msg_id)  # Acknowledge success
                except Exception:
                    pass  # Don't ack — message will be retried
```

**Or with RabbitMQ (more features):**

```python
import pika
import json

# Publisher
def publish_event(event_type: str, data: dict):
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel = connection.channel()
    channel.exchange_declare(exchange='events', exchange_type='fanout')
    channel.basic_publish(
        exchange='events',
        routing_key='',
        body=json.dumps({"type": event_type, **data}),
        properties=pika.BasicProperties(delivery_mode=2),  # Persistent!
    )
    connection.close()

# Consumer (each service has its own queue)
def start_consumer(queue_name: str, handler):
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel = connection.channel()
    channel.exchange_declare(exchange='events', exchange_type='fanout')
    channel.queue_declare(queue=queue_name, durable=True)
    channel.queue_bind(exchange='events', queue=queue_name)

    def callback(ch, method, properties, body):
        try:
            event = json.loads(body)
            handler(event)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    channel.basic_consume(queue=queue_name, on_message_callback=callback)
    channel.start_consuming()
```

**The key properties you get:**

| Property | HTTP Calls | Message Queue |
|---|---|---|
| Service C is down | Order fails or data lost | Message waits in queue |
| User wait time | Sum of all calls | Just the publish (~5ms) |
| Adding Service E | Edit Service A | E subscribes (A unchanged!) |
| Retry on failure | Manual implementation | Built into the queue |
| Message persistence | Lost on crash | Survives restarts |

The fundamental insight: **temporal coupling** (both services must be up simultaneously) is the root cause. A message queue decouples the timing — publisher and consumer don't need to be alive at the same time.'''
    ),
    (
        "thinking/backtrack-manual-to-propertybased",
        "I'm writing tests for a function that sorts a list of objects by multiple fields. I keep finding edge cases I didn't think of. Is there a better way to test this?",
        r'''<think>
Let me trace through the manual testing approach and see where it falls short.

The function: sort objects by multiple fields (e.g., sort users by last_name, then first_name, then age).

Manual test approach:
```python
def test_sort_basic():
    users = [
        {"name": "Bob", "age": 30},
        {"name": "Alice", "age": 25},
    ]
    result = multi_sort(users, ["name"])
    assert result == [{"name": "Alice", "age": 25}, {"name": "Bob", "age": 30}]

def test_sort_by_two_fields():
    users = [
        {"name": "Alice", "age": 30},
        {"name": "Alice", "age": 25},
    ]
    result = multi_sort(users, ["name", "age"])
    assert result == [
        {"name": "Alice", "age": 25},
        {"name": "Alice", "age": 30},
    ]
```

This catches the basic cases. But edge cases I didn't think of:
- Empty list
- One-element list
- All elements are equal
- None values in sort fields
- Mixed types (int vs string in same field)
- Very large lists (performance)
- Stability (do equal elements keep their relative order?)
- Duplicate entries
- Field that doesn't exist in some objects
- Unicode characters in string fields
- Negative numbers
- Descending order vs ascending

I could write a test for each... but there are infinitely many combinations. And each time I think I'm done, a user finds another edge case.

Second attempt: test more manually.
I write 20 test cases covering the above. But:
1. I'm still limited by what I can imagine
2. The tests are brittle (assert exact output = break if implementation changes)
3. I'm testing specific examples, not general properties

Let me backtrack. Instead of testing SPECIFIC inputs and outputs, what if I test PROPERTIES that should ALWAYS be true, regardless of input?

Properties of any correct sort:
1. Output has the same elements as input (nothing added or removed)
2. Output is in sorted order (for the given fields)
3. Output length equals input length
4. Sort is stable (equal elements maintain relative order)
5. Sorting an already-sorted list returns the same list

These properties hold for ANY input. If I generate RANDOM inputs and check these properties, I test millions of edge cases I'd never think of manually.

This is property-based testing (Hypothesis in Python, QuickCheck in Haskell).
</think>

Manual testing for combinatorial code is like playing whack-a-mole with edge cases. Let me show why, then the approach that finds bugs automatically.

**Why manual tests plateau:**

```python
# You write these tests:
def test_basic_sort(): ...           # Happy path
def test_empty_list(): ...           # Edge case
def test_single_element(): ...       # Edge case
def test_duplicate_values(): ...     # Edge case
def test_two_sort_fields(): ...      # Feature test

# You think you're done. Then a user finds:
# - None values in a field → crash
# - Mixed int/string comparison → crash
# - 100K elements → timeout
# - Unicode sort order → wrong results
# Each new bug = new manual test = always one step behind
```

**The insight: test PROPERTIES, not examples**

```python
# Instead of "given THIS input, expect THAT output"
# Test "for ANY input, these properties are ALWAYS true"

# Properties of a correct sort function:
# 1. Same elements (nothing added or removed)
# 2. Correct order (each element <= next element)
# 3. Same length
# 4. Idempotent (sorting a sorted list changes nothing)
```

**Property-based testing with Hypothesis:**

```python
from hypothesis import given, settings
from hypothesis import strategies as st

# Your function under test
def multi_sort(items: list[dict], sort_keys: list[str],
               reverse: bool = False) -> list[dict]:
    return sorted(items, key=lambda x: tuple(x.get(k) for k in sort_keys),
                  reverse=reverse)

# Generate random test data
user_strategy = st.fixed_dictionaries({
    "name": st.text(min_size=0, max_size=50),
    "age": st.integers(min_value=0, max_value=150),
    "score": st.floats(allow_nan=False, allow_infinity=False),
})

@given(
    items=st.lists(user_strategy, min_size=0, max_size=100),
    sort_keys=st.lists(
        st.sampled_from(["name", "age", "score"]),
        min_size=1, max_size=3, unique=True,
    ),
)
def test_sort_preserves_elements(items, sort_keys):
    """Property 1: Sort doesn't add or remove elements."""
    result = multi_sort(items, sort_keys)
    assert len(result) == len(items)
    # Same elements (as multiset)
    assert sorted(result, key=id) == sorted(items, key=id)

@given(
    items=st.lists(user_strategy, min_size=0, max_size=100),
    sort_keys=st.lists(
        st.sampled_from(["name", "age", "score"]),
        min_size=1, max_size=3, unique=True,
    ),
)
def test_sort_is_ordered(items, sort_keys):
    """Property 2: Result is actually in sorted order."""
    result = multi_sort(items, sort_keys)
    for i in range(len(result) - 1):
        key_a = tuple(result[i].get(k) for k in sort_keys)
        key_b = tuple(result[i + 1].get(k) for k in sort_keys)
        assert key_a <= key_b, f"Not sorted at index {i}: {key_a} > {key_b}"

@given(
    items=st.lists(user_strategy, min_size=0, max_size=100),
    sort_keys=st.lists(
        st.sampled_from(["name", "age", "score"]),
        min_size=1, max_size=3, unique=True,
    ),
)
def test_sort_is_idempotent(items, sort_keys):
    """Property 3: Sorting an already-sorted list doesn't change it."""
    once = multi_sort(items, sort_keys)
    twice = multi_sort(once, sort_keys)
    assert once == twice

# Hypothesis generates hundreds of random inputs:
# - Empty lists ✓
# - Single elements ✓
# - All duplicates ✓
# - Unicode strings ✓
# - Negative numbers ✓
# - Lists with 100 elements ✓
# - Combinations you'd NEVER think to test manually ✓
```

**What Hypothesis finds that you wouldn't:**

```python
# Hypothesis runs your test with random data and finds:
#
# FAILED: test_sort_is_ordered
# Falsifying example:
#   items = [{"name": "", "age": 5, "score": 0.0},
#            {"name": "", "age": 3, "score": float('nan')}]
#   sort_keys = ["score"]
#
# NaN comparison: float('nan') < float('nan') is False!
# Your sort function doesn't handle NaN correctly.
# You would NEVER have written a test with NaN manually.
```

**When to use property-based testing:**

```
✅ Great for:
  - Pure functions (sort, filter, transform, serialize/deserialize)
  - Parsers (parse(format(x)) == x)
  - Encoders (decode(encode(x)) == x)
  - Data structures (insert then contains == True)
  - Mathematical properties (associative, commutative, distributive)

❌ Not great for:
  - UI testing (hard to define properties)
  - Integration tests (too many external dependencies)
  - Simple CRUD (not enough interesting properties)
```

```python
# Another powerful pattern: roundtrip testing
@given(data=st.dictionaries(st.text(), st.integers()))
def test_json_roundtrip(data):
    """Anything we serialize can be deserialized back."""
    assert json.loads(json.dumps(data)) == data

@given(dt=st.datetimes())
def test_datetime_roundtrip(dt):
    """Formatted datetime can be parsed back."""
    formatted = dt.isoformat()
    parsed = datetime.fromisoformat(formatted)
    assert parsed == dt
```

Property-based testing finds the edge cases you don't know about. Write 3 property tests instead of 20 example tests — and get better coverage.'''
    ),
    (
        "thinking/backtrack-naive-cron-to-scheduler",
        "I have 15 cron jobs doing various tasks (cleanup, reports, sync). They keep overlapping, some fail silently, and I have no visibility. How do I fix this?",
        r'''<think>
Let me trace through the incremental fixes.

Current state: 15 crontab entries, chaos.
```
*/5 * * * * python /app/scripts/sync_users.py
0 * * * * python /app/scripts/cleanup_temp.py
0 3 * * * python /app/scripts/generate_report.py
*/10 * * * * python /app/scripts/check_payments.py
... 11 more
```

Problems:
1. Jobs overlap (sync_users takes 8 min, runs every 5 min → two instances running)
2. Silent failures (cron doesn't alert on failure)
3. No visibility (which jobs ran? how long? did they succeed?)
4. No dependency management (report needs data from sync, but they run independently)

First fix attempt: Add a lock file to prevent overlap.
```bash
*/5 * * * * flock -n /tmp/sync_users.lock python /app/scripts/sync_users.py
```

This prevents overlap but:
1. Still no failure alerting
2. Still no visibility
3. If the job crashes and leaves the lock file, it never runs again
4. Managing 15 lock files is messy

Second fix attempt: Wrap each job in a shell script with logging and error handling.
```bash
#!/bin/bash
exec 2>>/var/log/cron_errors.log
flock -n /tmp/sync_users.lock python /app/scripts/sync_users.py || echo "FAILED" | mail admin@company.com
```

Better, but:
1. 15 shell script wrappers to maintain
2. Still no centralized monitoring (need to check 15 log files)
3. Still no dependency management
4. Email alerting for 15 jobs = email overload

Third fix attempt: Use a scheduling library with monitoring.

This is the right direction. For Python apps, the options are:
- Celery Beat (task scheduler + worker)
- APScheduler (lightweight, in-process)
- Airflow (if complex workflows with dependencies)
- Prefect / Dagster (modern alternatives to Airflow)

For 15 background tasks without complex dependencies: Celery Beat.
For complex workflows with dependencies: Airflow or Prefect.

Let me show the Celery approach since it solves all their problems with minimal setup.
</think>

Each incremental fix (lock files, wrapper scripts, email alerts) adds complexity without solving the core problem. Let me show the progression.

**Why incremental cron fixes are dead ends:**

```bash
# Fix 1: Lock files (prevents overlap, nothing else)
flock -n /tmp/job.lock command
# Still: no alerting, no logging, lock files can get orphaned

# Fix 2: Wrapper scripts (one per job = 15 scripts to maintain)
#!/bin/bash
start=$(date +%s)
flock -n /tmp/job.lock python script.py 2>>/var/log/job.log
status=$?
end=$(date +%s)
echo "Job took $((end-start))s, status=$status" >> /var/log/job.log
[ $status -ne 0 ] && echo "FAILED" | mail admin@co.com
# Now maintain 15 of these. Plus check 15 log files daily. Fun.

# Fix 3: Monitoring per-job (still scattered, still manual)
```

**The real solution — Celery Beat (scheduling + workers + monitoring):**

```python
# tasks.py — define all your jobs as Celery tasks
from celery import Celery

app = Celery('myapp', broker='redis://localhost:6379/0')

@app.task(bind=True, max_retries=3)
def sync_users(self):
    """Sync users from external system."""
    try:
        count = do_user_sync()
        logger.info(f"Synced {count} users")
    except Exception as e:
        raise self.retry(exc=e, countdown=60)

@app.task(bind=True)
def cleanup_temp_files(self):
    """Remove temporary files older than 24 hours."""
    count = remove_old_temp_files(hours=24)
    logger.info(f"Cleaned up {count} files")

@app.task(bind=True, max_retries=2)
def generate_daily_report(self):
    """Generate and email the daily business report."""
    report = build_report(date.today() - timedelta(days=1))
    send_report_email(report)

@app.task(bind=True, max_retries=3)
def check_pending_payments(self):
    """Check status of pending payments and update orders."""
    pending = get_pending_payments()
    for payment in pending:
        status = payment_provider.check_status(payment.id)
        update_payment_status(payment, status)
```

```python
# celery_app.py — schedule (replaces crontab)
from celery.schedules import crontab

app.conf.beat_schedule = {
    'sync-users': {
        'task': 'tasks.sync_users',
        'schedule': 300.0,  # Every 5 minutes
        'options': {'expires': 240},  # Don't run if > 4 min late
    },
    'cleanup-temp': {
        'task': 'tasks.cleanup_temp_files',
        'schedule': crontab(minute=0),  # Every hour
    },
    'daily-report': {
        'task': 'tasks.generate_daily_report',
        'schedule': crontab(hour=3, minute=0),  # 3 AM
    },
    'check-payments': {
        'task': 'tasks.check_pending_payments',
        'schedule': 600.0,  # Every 10 minutes
    },
}

# Prevent overlap (built-in via Celery's task locking):
app.conf.worker_max_tasks_per_child = 1000  # Recycle workers
app.conf.task_acks_late = True  # Don't lose tasks on crash
```

**What you get vs. cron:**

| Feature | Cron | Celery Beat |
|---|---|---|
| Prevent overlap | Manual (flock) | Built-in (task expires) |
| Failure alerting | Manual (scripts) | Built-in (error handlers) |
| Retry on failure | Manual | `max_retries=3` |
| Centralized logs | 15 log files | One log stream |
| Monitoring UI | None | Flower dashboard |
| Task history | None | Result backend |
| Dependency mgmt | None | Chain/group/chord |

**Monitoring with Flower:**

```bash
# Start Flower — web UI for monitoring all tasks
celery -A celery_app flower --port=5555

# Dashboard shows:
# - All scheduled tasks and their status
# - Execution time per task
# - Failure rate and error messages
# - Worker status and resource usage
# - Task history with full details
```

**Error handling and alerting:**

```python
# Global error handler — alerts on any task failure
from celery.signals import task_failure

@task_failure.connect
def handle_task_failure(sender, task_id, exception, traceback, **kwargs):
    alert_message = f"Task {sender.name} failed: {exception}"
    send_slack_alert(alert_message)
    # Or: send to PagerDuty, email, etc.
```

**Run it:**

```bash
# Terminal 1: Worker (processes tasks)
celery -A celery_app worker --loglevel=info -c 4

# Terminal 2: Beat (triggers scheduled tasks)
celery -A celery_app beat --loglevel=info

# Terminal 3: Flower (monitoring)
celery -A celery_app flower

# That's it. 15 cron jobs → 3 processes with full monitoring.
```

Replace your crontab with Celery Beat in one afternoon. You get automatic retries, overlap prevention, centralized monitoring, and alerting — all problems that cron makes you solve manually for each of 15 jobs.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
