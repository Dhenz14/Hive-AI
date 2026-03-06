"""Phase 3F: Metacognition -- Code Quality Judgment (Part 9)

Rate error handling completeness and code testability across real-world
systems: webhook receivers, migration runners, Django views, data pipelines,
and event-driven architectures.
"""

PAIRS = [
    # ------------------------------------------------------------------ 1
    (
        "thinking/meta-quality-error-handling-webhook",
        r'''Rate the error handling completeness of this Stripe webhook receiver (1-10):

```python
from flask import Flask, request, jsonify
import stripe

app = Flask(__name__)

@app.route("/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, "whsec_xxx")
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user = db.users.find_one({"email": session["customer_email"]})
        user["plan"] = "pro"
        db.users.update_one({"_id": user["_id"]}, {"$set": user})
        send_welcome_email(user["email"])

    return jsonify({"status": "ok"}), 200
```''',
        r'''<think>
Let me evaluate this Stripe webhook receiver across multiple error-handling dimensions.

Signature verification: The code does verify the Stripe signature and catches both ValueError and SignatureVerificationError. That is correct and present. However, it does not handle the case where Stripe-Signature header is missing entirely -- sig_header would be None, which may or may not raise SignatureVerificationError depending on the library version.

Idempotency / duplicate events: There is no check for duplicate event IDs. Stripe explicitly documents that webhooks can be delivered multiple times. If checkout.session.completed fires twice, the user gets two welcome emails. There is no event log or deduplication mechanism.

Partial processing failure: The handler does two things -- updates the user plan and sends a welcome email. If update_one succeeds but send_welcome_email raises an exception, the webhook returns a 500, Stripe retries, and the user record is already updated but they may get a duplicate email on retry (or not, depending on failure mode). There is no transactional boundary or compensation logic.

Missing user: If db.users.find_one returns None, the next line user["plan"] = "pro" raises a TypeError. No null check exists.

Unhandled event types: Non-checkout events silently return 200, which is actually fine for webhooks you don't care about. But there is no logging to help debug unexpected event types.

No logging at all: There is zero logging anywhere -- not on success, not on failure, not on unknown events. In production this is a serious observability gap.

Hardcoded secret: The webhook secret is hardcoded as "whsec_xxx" rather than loaded from environment or config.

Score: 3/10 -- Signature verification is present but nearly every other failure mode is unhandled.
</think>

**Error Handling Completeness: 3/10**

| Criterion                  | Status | Notes                                        |
|----------------------------|--------|----------------------------------------------|
| Signature verification     | Partial| Catches errors but no check for missing header|
| Idempotency / dedup        | Missing| No event ID tracking; duplicates cause issues |
| Partial failure handling   | Missing| DB update + email not atomic; no compensation |
| Null/missing data guards   | Missing| `find_one` returning None causes TypeError    |
| Logging / observability    | Missing| Zero logging anywhere in the handler          |
| Secret management          | Bad    | Webhook secret hardcoded in source            |
| Unhandled event types      | OK     | Silently returns 200, acceptable pattern      |

**What works:**
- Stripe signature verification is present with correct exception types
- Returns appropriate HTTP status codes for signature failures

**Critical gaps:**

1. **No idempotency** -- Stripe retries on failure and can deliver duplicates. You need an event log:
2. **No null check** -- `find_one` can return `None`, crashing the handler
3. **Non-atomic operations** -- DB write + email send can partially fail with no rollback

**Improved version:**

```python
@app.route("/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    if not sig_header:
        logger.warning("Missing Stripe-Signature header")
        return jsonify({"error": "Missing signature"}), 400

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ["STRIPE_WEBHOOK_SECRET"]
        )
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.warning("Webhook verification failed: %s", e)
        return jsonify({"error": "Verification failed"}), 400

    # Idempotency: skip already-processed events
    if db.processed_events.find_one({"event_id": event["id"]}):
        logger.info("Duplicate event %s, skipping", event["id"])
        return jsonify({"status": "duplicate"}), 200

    try:
        if event["type"] == "checkout.session.completed":
            _handle_checkout_completed(event["data"]["object"])
        else:
            logger.debug("Unhandled event type: %s", event["type"])
    except Exception:
        logger.exception("Failed processing event %s", event["id"])
        return jsonify({"error": "Processing failed"}), 500

    db.processed_events.insert_one({"event_id": event["id"], "processed_at": datetime.utcnow()})
    return jsonify({"status": "ok"}), 200
```'''
    ),
    # ------------------------------------------------------------------ 2
    (
        "thinking/meta-quality-error-handling-migration",
        r'''Rate the error handling completeness of this database migration runner (1-10):

```python
import os
import psycopg2

class MigrationRunner:
    def __init__(self, db_url):
        self.conn = psycopg2.connect(db_url)
        self.migrations_dir = "migrations/"

    def get_pending(self):
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM applied_migrations")
        applied = {row[0] for row in cur.fetchall()}
        all_files = sorted(os.listdir(self.migrations_dir))
        return [f for f in all_files if f not in applied]

    def run_all(self):
        pending = self.get_pending()
        for migration_file in pending:
            path = os.path.join(self.migrations_dir, migration_file)
            with open(path) as f:
                sql = f.read()
            cur = self.conn.cursor()
            cur.execute(sql)
            cur.execute(
                "INSERT INTO applied_migrations (name) VALUES (%s)",
                (migration_file,)
            )
            self.conn.commit()
        print(f"Applied {len(pending)} migrations")

if __name__ == "__main__":
    runner = MigrationRunner(os.environ["DATABASE_URL"])
    runner.run_all()
```''',
        r'''<think>
Let me evaluate this migration runner against the failure modes that matter in production.

Mid-migration failure: If cur.execute(sql) fails partway through a multi-statement SQL file, the cursor has already executed some statements. The code does commit per migration file which is good -- but within a single migration file containing multiple statements, a failure mid-file leaves the database in a partially migrated state. There is no explicit transaction wrapping per file, and psycopg2 auto-begins transactions, so a failure would leave the transaction open but not committed. The connection state after the exception is unhandled.

Rollback support: There is zero rollback capability. No down migrations, no reverse SQL, no way to undo a migration that was applied. If something goes wrong, the operator has no automated path back.

State tracking: The applied_migrations table tracks names but not timestamps, checksums, or status. If a migration partially applied and the process crashed before the INSERT, the migration would be re-attempted on next run, potentially failing on already-created objects.

Locking / concurrent runs: No advisory lock or mutex. Two instances running simultaneously could apply the same migration twice.

applied_migrations table bootstrap: If the table does not exist, get_pending crashes. There is no CREATE TABLE IF NOT EXISTS or bootstrap step.

Error propagation: Exceptions from cur.execute bubble up unhandled, printing a traceback. No structured error reporting, no indication of which migration failed.

Connection management: The connection is never closed. No context manager, no finally block.

File ordering: Relies on sorted() of filenames which works if files are named with numeric prefixes, but there is no validation of this convention.

Score: 3/10 -- Per-file commit is the only real safeguard present.
</think>

**Error Handling Completeness: 3/10**

| Criterion                        | Status  | Notes                                          |
|----------------------------------|---------|------------------------------------------------|
| Per-migration transactions       | Partial | Commits per file, but no explicit BEGIN/ROLLBACK|
| Mid-statement failure recovery   | Missing | Multi-statement SQL files can partially apply   |
| Rollback / down migrations       | Missing | No reverse migration support at all             |
| State tracking integrity         | Weak    | No checksums, no status field, no timestamps    |
| Concurrent execution safety      | Missing | No advisory lock; dual runs cause conflicts     |
| Table bootstrap                  | Missing | Crashes if applied_migrations does not exist    |
| Connection lifecycle             | Missing | Connection never closed; no context manager     |
| Error reporting                  | Missing | Raw exceptions; no indication of which file failed|

**What works:**
- Commits after each migration file, so successfully applied migrations persist
- Sorts files for deterministic ordering
- Checks applied set to skip already-run migrations

**Critical gaps:**

1. **No transaction safety within a migration** -- A file with `CREATE TABLE ...; INSERT ...;` can fail on the INSERT, leaving the table created but migration not recorded
2. **No concurrency control** -- Two deploys running simultaneously will corrupt state
3. **No bootstrap** -- First run crashes because `applied_migrations` table does not exist

**Improved version (key changes):**

```python
class MigrationRunner:
    def __init__(self, db_url):
        self.conn = psycopg2.connect(db_url)
        self._bootstrap()

    def _bootstrap(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS applied_migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT now(),
                    checksum TEXT
                )
            """)
            self.conn.commit()

    def run_all(self):
        with self.conn.cursor() as cur:
            # Advisory lock prevents concurrent runs
            cur.execute("SELECT pg_advisory_lock(12345)")

        pending = self.get_pending()
        for migration_file in pending:
            path = os.path.join(self.migrations_dir, migration_file)
            with open(path) as f:
                sql = f.read()
            try:
                with self.conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO applied_migrations (name, checksum) VALUES (%s, %s)",
                        (migration_file, hashlib.sha256(sql.encode()).hexdigest())
                    )
                self.conn.commit()
                logger.info("Applied %s", migration_file)
            except Exception:
                self.conn.rollback()
                logger.exception("FAILED on %s -- stopping", migration_file)
                raise
            finally:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(12345)")
```'''
    ),
    # ------------------------------------------------------------------ 3
    (
        "thinking/meta-quality-testability-django-view",
        r'''Rate the testability of this Django view (1-10):

```python
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views import View

class DashboardView(View):
    def get(self, request):
        # Check auth from session
        if not request.session.get("user_id"):
            return JsonResponse({"error": "unauthorized"}, status=401)

        user_id = request.session["user_id"]

        # Fetch analytics from external service
        resp = requests.get(
            f"{settings.ANALYTICS_API_URL}/users/{user_id}/stats",
            headers={"Authorization": f"Bearer {settings.ANALYTICS_API_KEY}"},
            timeout=10,
        )
        analytics = resp.json()

        # Fetch billing info
        billing_resp = requests.get(
            f"{settings.BILLING_API_URL}/customers/{user_id}",
            headers={"Authorization": f"Bearer {settings.BILLING_API_KEY}"},
            timeout=10,
        )
        billing = billing_resp.json()

        # Build response
        request.session["last_dashboard_visit"] = str(datetime.now())
        return JsonResponse({
            "analytics": analytics,
            "billing": billing,
            "user_id": user_id,
        })
```''',
        r'''<think>
Let me analyze the testability of this Django view by looking at how hard it would be to write isolated, fast, reliable unit tests.

External API calls: The view directly calls requests.get twice -- once for analytics, once for billing. These are hard dependencies on external HTTP services. To test this view, you must either mock requests.get (patching at the module level), use a library like responses or httpretty, or actually hit the services. None of this is injected, so there is no clean seam for substitution.

Settings dependency: The view reads four settings values directly (ANALYTICS_API_URL, ANALYTICS_API_KEY, BILLING_API_URL, BILLING_API_KEY). In tests you need to use @override_settings or modify settings directly. This works in Django but it is an implicit global dependency.

Session dependency: The view reads from and writes to request.session. Django's test client does support sessions, so this is testable but adds ceremony. The auth check and the session write are both embedded in the same method.

No separation of concerns: The view does authentication, two external API calls, data assembly, and session writes all in one method. There are no helper methods, no service classes, no dependency injection. You cannot test the data assembly logic without also dealing with the API calls.

Side effects mixed with reads: The view mutates request.session["last_dashboard_visit"] as a side effect during what is semantically a read operation. This is surprising and makes testing the GET idempotent behavior harder.

Positive: It is a single method in a class-based view, so you can at least instantiate it and call get() with a RequestFactory. The response is JSON, which is easy to assert against.

Score: 3/10 -- Testable only with heavy mocking; no dependency injection or separation of concerns.
</think>

**Testability: 3/10**

| Criterion                     | Score | Notes                                           |
|-------------------------------|-------|-------------------------------------------------|
| Dependency injection          | 0/3   | No injectable dependencies; all hardcoded        |
| Separation of concerns        | 0/2   | Auth + 2 API calls + session write in one method |
| External service isolation    | 1/2   | Mockable via `unittest.mock`, but no clean seam  |
| Side-effect predictability    | 0/1   | Mutates session during a GET request             |
| Data logic separability       | 1/2   | JSON response is easy to assert against          |

**What makes testing painful:**
- Every test must patch `requests.get` at the module level (or use `responses` library)
- Two different APIs in one method means mock setup is complex and fragile
- `@override_settings` needed to control URLs and keys
- Session must be set up with the test client or RequestFactory

**Improved testable version:**

```python
class AnalyticsClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    def get_user_stats(self, user_id: str) -> dict:
        resp = requests.get(
            f"{self.base_url}/users/{user_id}/stats",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()


class BillingClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    def get_customer(self, user_id: str) -> dict:
        resp = requests.get(
            f"{self.base_url}/customers/{user_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()


class DashboardView(View):
    analytics_client: AnalyticsClient = None
    billing_client: BillingClient = None

    def get(self, request):
        if not request.session.get("user_id"):
            return JsonResponse({"error": "unauthorized"}, status=401)

        user_id = request.session["user_id"]
        analytics = self.analytics_client.get_user_stats(user_id)
        billing = self.billing_client.get_customer(user_id)

        return JsonResponse({
            "analytics": analytics,
            "billing": billing,
            "user_id": user_id,
        })
```

Now tests can inject mock clients directly: `view.analytics_client = MockAnalyticsClient()` -- no patching needed.'''
    ),
    # ------------------------------------------------------------------ 4
    (
        "thinking/meta-quality-testability-data-pipeline",
        r'''Rate the testability of this data pipeline function (1-10):

```python
import boto3
import pandas as pd
import psycopg2

def run_daily_etl():
    # Extract
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket="data-lake", Key=f"events/{datetime.now():%Y-%m-%d}.parquet")
    df = pd.read_parquet(obj["Body"])

    # Transform
    df = df[df["event_type"].isin(["purchase", "signup"])]
    df["amount_usd"] = df["amount_cents"] / 100
    df["event_date"] = pd.to_datetime(df["timestamp"]).dt.date
    daily_summary = df.groupby(["event_date", "event_type"]).agg(
        total_amount=("amount_usd", "sum"),
        event_count=("event_type", "count"),
    ).reset_index()

    # Load
    conn = psycopg2.connect(os.environ["REDSHIFT_URL"])
    cur = conn.cursor()
    for _, row in daily_summary.iterrows():
        cur.execute(
            "INSERT INTO daily_metrics VALUES (%s, %s, %s, %s)",
            (row["event_date"], row["event_type"], row["total_amount"], row["event_count"]),
        )
    conn.commit()
    conn.close()
    print(f"Loaded {len(daily_summary)} rows")
```''',
        r'''<think>
Analyzing the testability of this ETL function step by step.

Monolithic function: Extract, transform, and load are all in one function with no separation. You cannot test the transform logic without also dealing with S3 and Redshift. This is the biggest testability problem.

Hardcoded infrastructure: boto3.client("s3") is instantiated inside the function. psycopg2.connect is called inside the function. The S3 bucket name "data-lake" is hardcoded. These cannot be substituted without monkey-patching or using moto/localstack.

Date coupling: The function uses datetime.now() to determine which file to read. This makes it non-deterministic -- you cannot test for a specific date without mocking datetime.

Environment variable dependency: REDSHIFT_URL comes from os.environ, which is an implicit global dependency.

No return value: The function returns None and prints to stdout. There is no way to assert on the output without capturing stdout or querying the database.

The transform logic itself is pure pandas: filter, derive columns, group-by. This is the most valuable part to test, and it is buried inside the function with no way to call it independently.

Row-by-row insert: The load phase iterates with iterrows() and executes individual INSERTs, which is extremely slow for Redshift (columnar store optimized for bulk loads), but that is a performance issue, not a testability issue per se.

Positive: The pandas operations are straightforward and would be easy to test IF they were extracted into a separate function that takes a DataFrame and returns a DataFrame.

Score: 2/10 -- The transform logic is untestable without mocking all of S3 and Redshift.
</think>

**Testability: 2/10**

| Criterion                     | Score | Notes                                           |
|-------------------------------|-------|-------------------------------------------------|
| Function decomposition        | 0/3   | Single monolithic function; no separation of ETL |
| Dependency injection          | 0/2   | S3 client, DB conn, bucket name all hardcoded    |
| Determinism                   | 0/2   | Uses `datetime.now()` for file key               |
| Return value / observability  | 0/1   | Returns None; prints to stdout                   |
| Pure logic separability       | 1/2   | Transform logic is pure pandas but not extracted  |

**Why this is nearly untestable:**
- To test the filtering and aggregation logic (the actual business value), you must mock S3, mock Redshift, and mock datetime
- No function returns anything -- the only observable effect is rows in Redshift
- The S3 bucket and key pattern are hardcoded constants

**Improved testable version:**

```python
def extract_events(s3_client, bucket: str, date: datetime.date) -> pd.DataFrame:
    """Extract: read parquet from S3. Thin I/O wrapper."""
    obj = s3_client.get_object(Bucket=bucket, Key=f"events/{date:%Y-%m-%d}.parquet")
    return pd.read_parquet(obj["Body"])


def transform_events(df: pd.DataFrame) -> pd.DataFrame:
    """Transform: filter, derive, and aggregate. Pure function."""
    df = df[df["event_type"].isin(["purchase", "signup"])].copy()
    df["amount_usd"] = df["amount_cents"] / 100
    df["event_date"] = pd.to_datetime(df["timestamp"]).dt.date
    return df.groupby(["event_date", "event_type"]).agg(
        total_amount=("amount_usd", "sum"),
        event_count=("event_type", "count"),
    ).reset_index()


def load_metrics(conn, summary: pd.DataFrame) -> int:
    """Load: bulk insert into Redshift. Returns rows loaded."""
    # Use COPY or execute_values for performance
    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        execute_values(cur, "INSERT INTO daily_metrics VALUES %s",
                       summary.values.tolist())
    conn.commit()
    return len(summary)
```

Now `transform_events` is a **pure function** testable with a simple DataFrame fixture -- no mocks required:

```python
def test_transform_filters_and_aggregates():
    df = pd.DataFrame({
        "event_type": ["purchase", "signup", "page_view"],
        "amount_cents": [1000, 0, 500],
        "timestamp": ["2025-01-01"] * 3,
    })
    result = transform_events(df)
    assert len(result) == 2  # page_view filtered out
    assert result.loc[result["event_type"] == "purchase", "total_amount"].iloc[0] == 10.0
```'''
    ),
    # ------------------------------------------------------------------ 5
    (
        "thinking/meta-quality-testability-event-decorators",
        r'''Rate the testability of this event-driven system (1-10):

```python
_handlers = {}

def on_event(event_type):
    def decorator(fn):
        _handlers.setdefault(event_type, []).append(fn)
        return fn
    return decorator

def emit(event_type, payload):
    for handler in _handlers.get(event_type, []):
        handler(payload)

# --- handlers registered at import time ---

@on_event("user.created")
def send_welcome_email(payload):
    smtp = smtplib.SMTP(os.environ["SMTP_HOST"])
    smtp.send_message(build_welcome_email(payload["email"]))
    smtp.quit()

@on_event("user.created")
def provision_account(payload):
    requests.post(
        f"{os.environ['PROVISIONING_URL']}/accounts",
        json={"user_id": payload["user_id"]},
    )

@on_event("user.created")
def track_analytics(payload):
    segment.track(payload["user_id"], "User Created")

@on_event("order.completed")
def fulfill_order(payload):
    warehouse_api.create_shipment(payload["order_id"])

@on_event("order.completed")
def send_receipt(payload):
    stripe.invoices.send(payload["invoice_id"])
```''',
        r'''<think>
Let me analyze the testability of this event-driven system systematically.

Global mutable state: _handlers is a module-level dictionary that is mutated at import time by decorators. This is the core testability problem. When you import this module in a test, all handlers are registered as side effects. There is no way to get a clean _handlers dict without reloading the module or manually clearing it.

Test isolation: If test A adds a handler and test B expects a clean state, they interfere. The global registry means test order matters. You would need to save and restore _handlers around every test, which is fragile.

Import-time side effects: The @on_event decorators execute at import time, registering handlers immediately. You cannot import the handler functions without also registering them. This makes it impossible to test a handler in isolation without it being wired into the global system.

Handler testability: Each handler has hardcoded dependencies -- smtplib.SMTP, requests.post, segment.track, warehouse_api, stripe.invoices. None are injected. To test any handler you must mock multiple external services.

No error handling in emit: If one handler raises an exception, subsequent handlers for the same event are skipped. There is no error isolation between handlers.

No return values from emit: emit() returns None, so there is no way to know if handlers succeeded without observing side effects.

Ordering: Handler execution order depends on import order and registration order, which is implicit and fragile.

Positive: The decorator pattern is simple and the emit function itself is clean. The concept of separating event emission from handling is good -- it is the implementation that hurts testability.

Score: 2/10 -- Global mutable state with import-time side effects makes isolated testing extremely difficult.
</think>

**Testability: 2/10**

| Criterion                     | Score | Notes                                            |
|-------------------------------|-------|--------------------------------------------------|
| State isolation                | 0/3   | Global `_handlers` dict mutated at import time   |
| Handler independence           | 0/2   | Each handler has hardcoded I/O dependencies      |
| Test setup/teardown            | 1/2   | Can manually clear `_handlers`, but fragile      |
| Observability of emit()        | 0/1   | Returns None; no way to verify handler results   |
| Error isolation                | 0/2   | One handler exception kills subsequent handlers  |

**Core testability problems:**

1. **Import-time registration** -- You cannot `from events import send_welcome_email` without it being registered globally. Test files that import handlers pollute the global registry.

2. **No dependency injection** -- Every handler reaches out to global/external services (SMTP, HTTP, Segment, Stripe). Testing requires heavy patching.

3. **No test isolation** -- Tests running in parallel or sequence share the same `_handlers` dict.

**Improved testable version:**

```python
class EventBus:
    """Testable event bus with explicit lifecycle."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event_type: str):
        def decorator(fn):
            self._handlers.setdefault(event_type, []).append(fn)
            return fn
        return decorator

    def emit(self, event_type: str, payload: dict) -> list[tuple[Callable, Exception | None]]:
        results = []
        for handler in self._handlers.get(event_type, []):
            try:
                handler(payload)
                results.append((handler, None))
            except Exception as e:
                results.append((handler, e))
        return results

    def clear(self):
        self._handlers.clear()


# Production: single instance created at app startup
bus = EventBus()


# Handlers accept dependencies explicitly
def make_welcome_email_handler(smtp_factory):
    def send_welcome_email(payload):
        smtp = smtp_factory()
        smtp.send_message(build_welcome_email(payload["email"]))
        smtp.quit()
    return send_welcome_email
```

Now tests are clean:

```python
def test_emit_calls_registered_handlers():
    bus = EventBus()  # fresh instance, no global state
    calls = []
    bus.on("user.created")(lambda p: calls.append(p))
    results = bus.emit("user.created", {"email": "a@b.com"})
    assert len(calls) == 1
    assert results[0][1] is None  # no exception

def test_handler_error_does_not_block_others():
    bus = EventBus()
    bus.on("x")(lambda p: 1/0)  # will raise
    bus.on("x")(lambda p: None)  # should still run
    results = bus.emit("x", {})
    assert isinstance(results[0][1], ZeroDivisionError)
    assert results[1][1] is None
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
