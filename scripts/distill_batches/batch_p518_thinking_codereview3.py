"""Phase 1E: Foundation Thinking — Code Review & Refactoring (Part 3/4)
Concurrency code review, async patterns, error handling review, logging review."""

PAIRS = [
    (
        "thinking/review-async-antipatterns",
        "Review this async Python code. It works but feels wrong:\n\n```python\nasync def fetch_user_dashboard(user_id: int):\n    user = await db.fetch_user(user_id)\n    orders = await db.fetch_orders(user_id)\n    notifications = await db.fetch_notifications(user_id)\n    recommendations = await ml_service.get_recommendations(user_id)\n    weather = await weather_api.get_local(user.zip_code)\n    \n    unread_count = 0\n    for n in notifications:\n        if not n.read:\n            unread_count += 1\n    \n    return {\n        'user': user,\n        'orders': orders,\n        'notifications': notifications,\n        'unread_count': unread_count,\n        'recommendations': recommendations,\n        'weather': weather,\n    }\n```",
        r'''<think>
Two main problems:

1. **Sequential awaits** — Each `await` waits for the previous to finish. These are independent queries that should run concurrently with `asyncio.gather()`. If each takes 100ms, this is 500ms sequential vs ~100ms concurrent.

2. **Manual counting loop** — `for n in notifications: if not n.read: unread_count += 1` should be `sum(1 for n in notifications if not n.read)` — but even better, this could be a DB query `COUNT(*) WHERE read = false` to avoid fetching all notifications just to count unread ones.

Let me also check: are there any dependencies between the calls? `weather` depends on `user.zip_code`, so `user` must be fetched first. The rest are independent.
</think>

Two issues: **sequential awaits** for independent operations, and an **unnecessary data fetch**.

## Problem 1: Sequential Awaits

Each `await` blocks until complete. These are independent queries running one after another:
```
fetch_user:          |████| 100ms
fetch_orders:              |████| 100ms
fetch_notifications:             |████| 100ms
get_recommendations:                   |████| 100ms
get_local:                                   |████| 100ms
Total:                                              500ms
```

## Problem 2: Fetching All Notifications to Count

You load every notification into memory just to count unread ones. That's a `SELECT COUNT(*)` query, not a full fetch.

## Fixed

```python
async def fetch_user_dashboard(user_id: int):
    # User must be fetched first (weather depends on zip_code)
    user = await db.fetch_user(user_id)

    # Everything else runs concurrently
    orders, notifications, unread_count, recommendations, weather = (
        await asyncio.gather(
            db.fetch_orders(user_id),
            db.fetch_notifications(user_id, limit=20),
            db.count_unread_notifications(user_id),
            ml_service.get_recommendations(user_id),
            weather_api.get_local(user.zip_code),
        )
    )

    return {
        'user': user,
        'orders': orders,
        'notifications': notifications,
        'unread_count': unread_count,
        'recommendations': recommendations,
        'weather': weather,
    }
```

```
fetch_user:          |████| 100ms
gather:                    |████| 100ms (all 5 concurrent)
Total:                           200ms (60% faster)
```

**Rules for async code**:
- Independent awaits → `asyncio.gather()`
- Count queries → do them in the database, not in Python
- If one call depends on another's result, keep those sequential'''
    ),
    (
        "thinking/review-callback-hell",
        "This JavaScript code handles a multi-step checkout. Review it:\n\n```javascript\nfunction processCheckout(cart, paymentInfo, callback) {\n  validateCart(cart, function(err, validCart) {\n    if (err) {\n      callback(err);\n      return;\n    }\n    calculateTax(validCart, function(err, taxedCart) {\n      if (err) {\n        callback(err);\n        return;\n      }\n      processPayment(taxedCart, paymentInfo, function(err, payment) {\n        if (err) {\n          callback(err);\n          return;\n        }\n        createOrder(taxedCart, payment, function(err, order) {\n          if (err) {\n            rollbackPayment(payment.id, function(rollbackErr) {\n              if (rollbackErr) {\n                logCritical('Payment rollback failed', payment.id, rollbackErr);\n              }\n              callback(err);\n            });\n            return;\n          }\n          sendConfirmation(order, function(err) {\n            if (err) {\n              logWarning('Confirmation email failed', order.id, err);\n            }\n            callback(null, order);\n          });\n        });\n      });\n    });\n  });\n}\n```",
        r'''<think>
Classic callback hell / pyramid of doom. Problems:
1. 6 levels of nesting — impossible to follow
2. Error handling duplicated at every level
3. Rollback logic is buried deep in the nesting
4. Hard to add steps or reorder

Fix: convert to async/await. The rollback logic becomes a try/catch. Confirmation email failure is non-critical so it shouldn't block success.
</think>

**Callback hell** — 6 levels deep, duplicated error handling, and rollback logic buried in the pyramid. Convert to async/await:

```javascript
async function processCheckout(cart, paymentInfo) {
  const validCart = await validateCart(cart);
  const taxedCart = await calculateTax(validCart);
  const payment = await processPayment(taxedCart, paymentInfo);

  let order;
  try {
    order = await createOrder(taxedCart, payment);
  } catch (err) {
    await rollbackPayment(payment.id).catch(rollbackErr => {
      logCritical('Payment rollback failed', payment.id, rollbackErr);
    });
    throw err;
  }

  // Non-critical: don't fail checkout if email fails
  sendConfirmation(order).catch(err => {
    logWarning('Confirmation email failed', order.id, err);
  });

  return order;
}
```

## What Changed

| Before | After |
|--------|-------|
| 6 levels of nesting | Flat sequential flow |
| 12 lines of `if (err)` boilerplate | Errors propagate automatically |
| Rollback buried at level 5 | Rollback in clear try/catch |
| Callback `(err, result)` convention | Native return values and exceptions |
| `sendConfirmation` blocks completion | Fire-and-forget (intentionally) |

**Key insight**: `sendConfirmation` is intentionally not awaited — checkout success shouldn't depend on email delivery. The `.catch()` logs the failure without blocking.'''
    ),
    (
        "thinking/review-error-swallowing",
        "Our app has mysterious silent failures. Review our error handling:\n\n```python\ndef sync_inventory(products):\n    for product in products:\n        try:\n            stock = warehouse_api.get_stock(product.sku)\n            product.quantity = stock.available\n            product.save()\n        except Exception:\n            pass  # Don't crash the sync\n\ndef process_webhook(request):\n    try:\n        event = json.loads(request.body)\n        handler = WEBHOOK_HANDLERS.get(event['type'])\n        if handler:\n            handler(event['data'])\n        return HttpResponse(status=200)\n    except Exception as e:\n        logger.error(f'Webhook failed: {e}')\n        return HttpResponse(status=200)  # Always return 200\n\ndef send_batch_emails(users, template):\n    failed = []\n    for user in users:\n        try:\n            rendered = template.render(user=user)\n            mailer.send(user.email, rendered)\n        except Exception:\n            failed.append(user)\n    if failed:\n        logger.warning(f'{len(failed)} emails failed')\n    # Never raises, never retries\n```",
        r'''<think>
Three flavors of error swallowing:

1. `sync_inventory`: bare `except: pass` — the worst. If the API is down, ALL products silently fail to sync, and nobody knows.

2. `process_webhook`: catches everything, always returns 200. The webhook provider thinks delivery succeeded, so it won't retry. If the handler crashes, the event is lost forever.

3. `send_batch_emails`: catches everything, logs a count, but loses the actual errors. Which users failed? Why? Was it a template error (all will fail) or a transient SMTP error (retry would fix it)?

Each needs different treatment based on the error's nature and the operation's criticality.
</think>

Three patterns of **error swallowing** causing your silent failures:

## 1. The Silent Killer: `except: pass`

```python
# BEFORE: Product quantities silently become stale
except Exception:
    pass

# AFTER: Log, track, alert
except WarehouseUnavailable:
    logger.warning(f"Warehouse API down, skipping {product.sku}")
    failed_skus.append(product.sku)
except Exception:
    logger.exception(f"Unexpected error syncing {product.sku}")
    failed_skus.append(product.sku)

# After the loop:
if failed_skus:
    alert_ops(f"Inventory sync: {len(failed_skus)}/{len(products)} failed")
```

## 2. The Data Loser: Always-200 Webhook

```python
# BEFORE: Provider thinks delivery succeeded, never retries
except Exception as e:
    logger.error(f'Webhook failed: {e}')
    return HttpResponse(status=200)  # Event lost forever

# AFTER: Return 500 so the provider retries
except json.JSONDecodeError:
    return HttpResponse(status=400)  # Bad payload, don't retry
except Exception:
    logger.exception(f"Webhook processing failed")
    return HttpResponse(status=500)  # Provider will retry
```

**Webhook rule**: Return 200 only if you've successfully processed the event. Return 500 to trigger retry. Return 400 for malformed payloads.

## 3. The Mystery Logger: Count Without Context

```python
# BEFORE: "47 emails failed" — but why?
except Exception:
    failed.append(user)

# AFTER: Distinguish transient vs permanent failures
except smtplib.SMTPRecipientsRefused:
    permanent_failures.append((user, "invalid address"))
except smtplib.SMTPServerDisconnected:
    transient_failures.append(user)  # Queue for retry
except TemplateRenderError as e:
    # Template bug = ALL remaining will fail too
    logger.exception(f"Template error for {user.id}")
    raise  # Abort the batch, fix the template

# After loop:
if transient_failures:
    retry_queue.extend(transient_failures)
if permanent_failures:
    report_undeliverable(permanent_failures)
```

## Error Handling Rules

1. **Never `except: pass`** — at minimum log with `logger.exception()`
2. **Catch specific exceptions** — different errors need different responses
3. **Distinguish transient vs permanent** — retry the former, report the latter
4. **Preserve context** — log which item failed and why, not just a count
5. **Consider blast radius** — one bad template will fail ALL emails; detect and abort early'''
    ),
    (
        "thinking/review-logging-antipatterns",
        "Review our logging practices:\n\n```python\nimport logging\nlogger = logging.getLogger(__name__)\n\ndef process_order(order_id):\n    print(f'Processing order {order_id}')  # 1\n    \n    order = db.get_order(order_id)\n    logger.debug(f'Got order: {order}')  # 2\n    \n    logger.info(f'Order {order_id} for user {order.user.email} '\n                f'with card ending {order.user.card[-4:]} '\n                f'total ${order.total}')  # 3\n    \n    try:\n        payment = charge(order)\n    except PaymentError as e:\n        logger.error(f'Payment failed')  # 4\n        raise\n    \n    logger.info(f'Payment {payment.id} succeeded for '\n                f'order {order_id}')  # 5 - good\n    \n    try:\n        ship(order)\n    except ShippingError as e:\n        logger.error(f'Shipping failed: ' + str(e))  # 6\n        raise\n    \n    logger.info('Done')  # 7\n```\n\nWhat's wrong with our logging?",
        r'''<think>
Let me identify each problem:

1. `print()` instead of logging — won't go to log files, no level/timestamp
2. `f'Got order: {order}'` — debug log stringifies the entire order object (may be expensive, may leak PII, may be huge)
3. Logs user email AND card digits — PII leak in logs!
4. `'Payment failed'` — no context. Which order? What error? This is useless in production.
5. Good — has both payment ID and order ID for correlation
6. String concatenation instead of structured logging / `logger.exception()`
7. `'Done'` — meaningless. Done with what?
</think>

Seven problems, annotated:

```python
print(f'Processing order {order_id}')
# ❌ #1: print() not logging — no level, no timestamp, not in log files

logger.debug(f'Got order: {order}')
# ❌ #2: Stringifies entire order even if debug is disabled.
#    May dump huge objects, PII, or trigger lazy-loaded DB queries.

logger.info(f'Order {order_id} for user {order.user.email} '
            f'with card ending {order.user.card[-4:]} ...')
# ❌ #3: PII in logs! Email AND card digits. Violates GDPR/PCI-DSS.

logger.error(f'Payment failed')
# ❌ #4: No context — which order? What error? Useless at 3AM.

logger.error(f'Shipping failed: ' + str(e))
# ❌ #6: String concat loses the traceback. Use logger.exception().

logger.info('Done')
# ❌ #7: "Done" — done with what? Useless in a stream of log lines.
```

## Fixed Version

```python
import logging
import structlog  # Or use logging with structured formatters

logger = structlog.get_logger(__name__)

def process_order(order_id: str):
    log = logger.bind(order_id=order_id)  # Context follows all log calls
    log.info("order_processing_started")

    order = db.get_order(order_id)
    log = log.bind(user_id=order.user.id)  # Add context, NOT PII

    try:
        payment = charge(order)
    except PaymentError:
        log.exception("payment_failed")  # Includes traceback + context
        raise

    log.info("payment_succeeded", payment_id=payment.id)

    try:
        ship(order)
    except ShippingError:
        log.exception("shipping_failed")
        raise

    log.info("order_processing_completed", total=float(order.total))
```

## Rules

| Rule | Why |
|------|-----|
| Never `print()` in production code | No levels, no routing, no timestamps |
| Never log PII (emails, cards, names) | Legal liability, compliance violations |
| Use `logger.exception()` in except blocks | Preserves the traceback |
| Use structured key-value logging | Machine-parseable, searchable, filterable |
| Bind context (IDs) early | Every log line carries correlation data |
| Use event names, not sentences | `"payment_failed"` is searchable; `"Oh no the payment didn't work"` isn't |
| Use lazy formatting: `logger.debug("x=%s", x)` | String not built if debug disabled |'''
    ),
    (
        "thinking/review-thread-safety",
        "Review this cache implementation for thread safety:\n\n```python\nclass InMemoryCache:\n    def __init__(self, max_size=1000, ttl=300):\n        self._cache = {}\n        self._access_times = {}\n        self._max_size = max_size\n        self._ttl = ttl\n    \n    def get(self, key):\n        if key in self._cache:\n            if time.time() - self._access_times[key] > self._ttl:\n                del self._cache[key]\n                del self._access_times[key]\n                return None\n            self._access_times[key] = time.time()\n            return self._cache[key]\n        return None\n    \n    def set(self, key, value):\n        if len(self._cache) >= self._max_size:\n            self._evict()\n        self._cache[key] = value\n        self._access_times[key] = time.time()\n    \n    def _evict(self):\n        oldest_key = min(self._access_times, key=self._access_times.get)\n        del self._cache[oldest_key]\n        del self._access_times[oldest_key]\n\n# Used in a Flask app with threads:\ncache = InMemoryCache()\n\n@app.route('/api/data/<key>')\ndef get_data(key):\n    result = cache.get(key)\n    if result is None:\n        result = expensive_db_query(key)\n        cache.set(key, result)\n    return jsonify(result)\n```",
        r'''<think>
Multiple thread-safety issues:

1. **Check-then-act race in `get()`**: Thread A checks `key in self._cache` → True, Thread B deletes the key (TTL expired or eviction), Thread A tries `self._cache[key]` → KeyError.

2. **Check-then-act race in `set()`**: Two threads both see `len >= max_size`, both evict, now cache is below max_size by 2 (or worse, both try to delete the same oldest key).

3. **Non-atomic `get()`**: Between checking TTL and updating access time, another thread could evict the key.

4. **Cache stampede**: Multiple threads miss the cache for the same key simultaneously, all run `expensive_db_query(key)`, all set the result.

5. **`_cache` and `_access_times` are not atomically consistent**: A key could exist in one but not the other during concurrent operations.

Fixes: threading.Lock or use a proper LRU cache like `functools.lru_cache` or `cachetools.TTLCache`.
</think>

Multiple **thread-safety bugs** in this cache:

## Race Conditions

### 1. Check-Then-Act in `get()`
```
Thread A: key in self._cache → True
Thread B: TTL expires, deletes key
Thread A: self._cache[key] → KeyError 💥
```

### 2. Double Eviction in `set()`
```
Thread A: len(cache) >= max_size → True, starts evict
Thread B: len(cache) >= max_size → True, starts evict
Both delete the same oldest key → KeyError 💥
```

### 3. Cache Stampede
```
Thread A: cache.get("hot_key") → None
Thread B: cache.get("hot_key") → None
Thread C: cache.get("hot_key") → None
All three run expensive_db_query("hot_key") simultaneously
```

### 4. Inconsistent Dual Dicts
`_cache` and `_access_times` can get out of sync during concurrent mutations.

## Fixed Version

```python
import threading
from collections import OrderedDict

class InMemoryCache:
    def __init__(self, max_size=1000, ttl=300):
        self._cache = OrderedDict()  # Single dict, maintains insertion order
        self._expiry = {}
        self._max_size = max_size
        self._ttl = ttl
        self._lock = threading.Lock()
        self._pending = {}  # For stampede prevention

    def get(self, key):
        with self._lock:
            if key not in self._cache:
                return None
            if time.time() > self._expiry[key]:
                del self._cache[key]
                del self._expiry[key]
                return None
            self._cache.move_to_end(key)  # LRU update
            return self._cache[key]

    def set(self, key, value):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self._max_size:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
                del self._expiry[oldest]
            self._cache[key] = value
            self._expiry[key] = time.time() + self._ttl

    def get_or_compute(self, key, compute_fn):
        """Stampede-safe: only one thread computes per key."""
        result = self.get(key)
        if result is not None:
            return result

        with self._lock:
            # Double-check after acquiring lock
            if key in self._cache and time.time() <= self._expiry[key]:
                return self._cache[key]

            if key in self._pending:
                event = self._pending[key]
            else:
                event = threading.Event()
                self._pending[key] = event

        if not event.is_set():
            try:
                result = compute_fn()
                self.set(key, result)
            finally:
                with self._lock:
                    self._pending.pop(key, None)
                event.set()
        else:
            result = self.get(key)

        return result

# Usage:
@app.route('/api/data/<key>')
def get_data(key):
    result = cache.get_or_compute(key, lambda: expensive_db_query(key))
    return jsonify(result)
```

Or just use `cachetools.TTLCache` with a lock — don't reinvent caching.'''
    ),
    (
        "thinking/review-exception-hierarchy",
        "Code review on our exception handling:\n\n```python\n# Our custom exceptions\nclass AppError(Exception):\n    pass\n\n# In our API views:\ndef create_user(request):\n    try:\n        data = parse_request(request)\n        user = User.create(**data)\n        send_welcome_email(user)\n        return Response({'id': user.id}, status=201)\n    except KeyError as e:\n        return Response({'error': f'Missing field: {e}'}, status=400)\n    except ValueError as e:\n        return Response({'error': str(e)}, status=400)\n    except IntegrityError:\n        return Response({'error': 'Email already exists'}, status=409)\n    except SMTPError:\n        return Response({'error': 'Could not send email'}, status=500)\n    except AppError as e:\n        return Response({'error': str(e)}, status=400)\n    except Exception as e:\n        logger.exception('Unexpected error')\n        return Response({'error': 'Internal error'}, status=500)\n```\n\nEvery view has this same try/except tower. Is there a better way?",
        r'''<think>
Problems:
1. Every view repeats the same try/except tower — massive duplication
2. Generic exceptions (KeyError, ValueError) used for business logic — hard to distinguish "missing field" KeyError from a bug
3. All errors return string messages — no error codes for clients to handle programmatically
4. `IntegrityError` caught and assumed to be "email already exists" — could be any constraint violation

Fix:
1. Create a proper exception hierarchy with HTTP status codes built in
2. Use middleware/decorator to handle exceptions centrally
3. Each exception carries its own status code and error code
</think>

Two problems: **duplicated error handling** in every view, and **generic exceptions** used for domain errors.

## Fix: Exception Hierarchy + Central Handler

```python
# exceptions.py — each exception knows its HTTP status
class AppError(Exception):
    status_code = 500
    error_code = "internal_error"

    def __init__(self, message: str = None):
        self.message = message or self.__class__.__doc__ or "An error occurred"

class ValidationError(AppError):
    """Invalid input data"""
    status_code = 400
    error_code = "validation_error"

class NotFoundError(AppError):
    """Resource not found"""
    status_code = 404
    error_code = "not_found"

class ConflictError(AppError):
    """Resource already exists"""
    status_code = 409
    error_code = "conflict"

class AuthenticationError(AppError):
    """Invalid credentials"""
    status_code = 401
    error_code = "unauthorized"

class RateLimitError(AppError):
    """Too many requests"""
    status_code = 429
    error_code = "rate_limited"
```

```python
# middleware.py — ONE place handles all errors
class ErrorHandlerMiddleware:
    def process_exception(self, request, exception):
        if isinstance(exception, AppError):
            return Response(
                {'error': exception.error_code, 'message': exception.message},
                status=exception.status_code,
            )
        # Unexpected errors
        logger.exception("Unhandled exception")
        return Response(
            {'error': 'internal_error', 'message': 'Internal error'},
            status=500,
        )
```

```python
# views.py — clean, no try/except towers
def create_user(request):
    data = parse_and_validate(request)  # Raises ValidationError
    user = User.create(**data)          # Raises ConflictError if duplicate
    send_welcome_email(user)            # Non-critical, handled internally
    return Response({'id': user.id}, status=201)

# service layer raises domain exceptions
def parse_and_validate(request):
    email = request.json.get('email')
    if not email:
        raise ValidationError("Email is required")
    if User.exists(email=email):
        raise ConflictError(f"Email {email} already registered")
    return {'email': email, ...}
```

## Benefits
1. **Views are clean** — business logic only, no error plumbing
2. **Consistent error format** — every error has `error_code` + `message`
3. **One place to change** — add logging, metrics, or error formatting in the middleware
4. **No generic exceptions** — `ValidationError("Missing email")` instead of `KeyError("email")`'''
    ),
    (
        "thinking/review-mutable-default-traps",
        "We've had three production bugs this quarter all related to the same pattern. Can you review and explain what's going on?\n\n```python\n# Bug 1: Users getting other users' notifications\nclass NotificationService:\n    def __init__(self, channels=[]):\n        self.channels = channels\n    \n    def add_channel(self, channel):\n        self.channels.append(channel)\n\n# Bug 2: Stale data in API responses\ndef build_response(data, metadata={}):\n    metadata['timestamp'] = time.time()\n    metadata['version'] = 'v2'\n    return {'data': data, **metadata}\n\n# Bug 3: Cache that never expires\nclass QueryCache:\n    def __init__(self, store: dict = {}):\n        self.store = store\n    \n    def set(self, key, value):\n        self.store[key] = value\n    \n    def get(self, key):\n        return self.store.get(key)\n```",
        r'''<think>
The classic mutable default argument trap in Python. All three share the same bug.

In Python, default argument values are evaluated ONCE when the function/class is defined, not each time it's called. So:
- `channels=[]` — the SAME list object is shared by all instances that use the default
- `metadata={}` — the SAME dict accumulates keys across calls
- `store: dict = {}` — the SAME dict is shared by all QueryCache instances

Bug 1: All NotificationService instances without explicit channels share the same list. Adding a channel to one adds it to all.
Bug 2: metadata dict accumulates keys from previous calls. Random extra fields appear.
Bug 3: All QueryCache instances share one dict. One cache's data appears in another.
</think>

All three are the same bug: **mutable default arguments**.

## How Python Defaults Work

```python
def f(x=[]):  # This [] is created ONCE at function definition
    x.append(1)
    return x

f()  # [1]
f()  # [1, 1]    ← same list!
f()  # [1, 1, 1] ← still the same list
```

Default values are evaluated **once** when the function is defined, not per call. Mutable defaults (lists, dicts, sets) are shared across all calls/instances.

## Your Bugs Explained

**Bug 1**: All `NotificationService()` instances share ONE list. Adding a channel to user A's service adds it to user B's.

**Bug 2**: `metadata` dict accumulates across calls. By the 100th call, it contains `timestamp` and `version` from all previous calls (overwritten each time, but any other keys added anywhere persist).

**Bug 3**: All `QueryCache()` instances share ONE dict. Query results leak between caches.

## The Fix: `None` Sentinel

```python
# Bug 1
class NotificationService:
    def __init__(self, channels=None):
        self.channels = channels if channels is not None else []

# Bug 2
def build_response(data, metadata=None):
    metadata = metadata if metadata is not None else {}
    metadata['timestamp'] = time.time()
    metadata['version'] = 'v2'
    return {'data': data, **metadata}

# Bug 3
class QueryCache:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
```

**Rule**: Never use mutable objects (`[]`, `{}`, `set()`) as default arguments. Use `None` and create the object inside the function. This is Python's single most common gotcha — add it to your team's linter rules:

```toml
# pyproject.toml — ruff/flake8
[tool.ruff.lint]
select = ["B006"]  # mutable-argument-default
```'''
    ),
    (
        "thinking/review-resource-leak",
        "Our app slowly consumes all memory over a few days. Review these patterns:\n\n```python\n# Pattern 1: Event listeners\nclass EventBus:\n    _listeners = {}  # Class-level dict\n    \n    @classmethod\n    def on(cls, event_name, callback):\n        cls._listeners.setdefault(event_name, []).append(callback)\n\nclass UserDashboard:\n    def __init__(self, user):\n        self.user = user\n        EventBus.on('price_update', self.refresh)\n        EventBus.on('news_update', self.refresh)\n    \n    def refresh(self, data):\n        # Update dashboard display\n        pass\n\n# Pattern 2: Accumulating history  \nclass MetricsCollector:\n    def __init__(self):\n        self.history = []\n    \n    def record(self, metric_name, value):\n        self.history.append({\n            'name': metric_name,\n            'value': value,\n            'timestamp': time.time()\n        })\n    \n    def get_average(self, metric_name):\n        values = [m['value'] for m in self.history if m['name'] == metric_name]\n        return sum(values) / len(values) if values else 0\n\n# Pattern 3: Caching without bounds\nclass TemplateRenderer:\n    _cache = {}\n    \n    def render(self, template_name, context):\n        cache_key = f'{template_name}:{hash(frozenset(context.items()))}'\n        if cache_key not in self._cache:\n            self._cache[cache_key] = self._compile(template_name, context)\n        return self._cache[cache_key]\n```",
        r'''<think>
Three memory leak patterns:

1. **Event listener leak**: `UserDashboard` registers callbacks (`self.refresh`) on the global `EventBus`. The callback holds a reference to `self`, preventing garbage collection of `UserDashboard` instances even after they're no longer needed. Classic listener leak.

2. **Unbounded accumulation**: `self.history` grows forever. In a long-running service recording metrics every second, after a week that's 600k+ entries. `get_average` scans ALL history every time.

3. **Unbounded cache**: `_cache` is a class-level dict that grows with every unique context. Each user request with slightly different context creates a new cache entry. Never evicted.

Fixes:
1. Use `weakref` for callbacks, or implement `unsubscribe`/context manager
2. Use a bounded deque or time-windowed storage
3. Use `functools.lru_cache` or `cachetools.LRUCache` with a max size
</think>

Three memory leaks, each with a different root cause:

## Leak 1: Event Listener References

```python
EventBus.on('price_update', self.refresh)
# self.refresh is a bound method → holds strong reference to self
# UserDashboard can NEVER be garbage collected while EventBus exists
```

**Fix**: Weak references or explicit cleanup:
```python
import weakref

class EventBus:
    _listeners = {}

    @classmethod
    def on(cls, event_name, callback):
        ref = weakref.WeakMethod(callback,
            lambda r: cls._listeners[event_name].discard(r))
        cls._listeners.setdefault(event_name, set()).add(ref)

# Or simpler: explicit unsubscribe
class UserDashboard:
    def __init__(self, user):
        self.user = user
        EventBus.on('price_update', self.refresh)

    def close(self):
        EventBus.off('price_update', self.refresh)

    def __del__(self):
        self.close()
```

## Leak 2: Unbounded History

```python
self.history.append(...)  # Grows forever — 600K entries/week at 1/sec
```

**Fix**: Bounded window:
```python
from collections import deque

class MetricsCollector:
    def __init__(self, max_samples=10_000):
        self.history = deque(maxlen=max_samples)  # Auto-evicts oldest
```

## Leak 3: Unbounded Cache

```python
self._cache[cache_key] = ...  # New entry for every unique context
# Each user request with different data = new cache entry, forever
```

**Fix**: Bounded cache:
```python
from functools import lru_cache

class TemplateRenderer:
    @lru_cache(maxsize=512)
    def render(self, template_name, context_key):
        return self._compile(template_name, context_key)
```

## Memory Leak Detection Checklist
- Global/class-level dicts that only grow → needs max size or TTL
- Event listeners on long-lived objects → needs weak refs or unsubscribe
- Lists that `.append()` without `.pop()` → needs bounded container
- Caches without eviction → needs LRU/TTL bounds'''
    ),
    (
        "thinking/review-coupling-to-framework",
        "We're struggling to test our business logic because it's tightly coupled to Django. Here's a typical service:\n\n```python\nfrom django.conf import settings\nfrom django.core.mail import send_mail\nfrom django.core.cache import cache\nfrom django.db import transaction\nfrom myapp.models import Order, OrderItem, Product\n\nclass OrderService:\n    def create_order(self, request):\n        user = request.user  # Django request object\n        cart = request.session['cart']  # Django session\n        \n        with transaction.atomic():\n            order = Order.objects.create(\n                user=user,\n                shipping_address=request.POST['address'],\n            )\n            \n            for item in cart:\n                product = Product.objects.get(id=item['product_id'])\n                if product.stock < item['quantity']:\n                    raise ValueError(f'{product.name} out of stock')\n                OrderItem.objects.create(\n                    order=order,\n                    product=product,\n                    quantity=item['quantity'],\n                    price=product.price,\n                )\n                product.stock -= item['quantity']\n                product.save()\n        \n        cache.delete(f'user_orders_{user.id}')\n        \n        if order.total > settings.FREE_SHIPPING_THRESHOLD:\n            order.shipping_cost = 0\n        else:\n            order.shipping_cost = settings.SHIPPING_RATE\n        order.save()\n        \n        send_mail(\n            'Order Confirmation',\n            f'Your order {order.id} has been placed.',\n            settings.DEFAULT_FROM_EMAIL,\n            [user.email],\n        )\n        \n        return order\n```\n\nTo test this, we need: Django test client, test database, cache backend, email backend, session middleware. How do we decouple this?",
        r'''<think>
The service is directly coupled to:
- `request` object (HTTP concern)
- `request.session` (HTTP session)
- `request.POST` (form data)
- `Product.objects.get()` (Django ORM)
- `Order.objects.create()` (Django ORM)
- `transaction.atomic()` (database)
- `cache.delete()` (caching layer)
- `settings.FREE_SHIPPING_THRESHOLD` (config)
- `send_mail()` (email)

Fix: separate the concerns:
1. View layer handles HTTP (request/session/POST) and calls service with plain data
2. Service accepts plain data and uses injected dependencies
3. Side effects (email, cache) are decoupled via events or injected interfaces
</think>

The service is a ball of Django imports — HTTP, ORM, cache, email, settings all mixed into business logic. Here's how to decouple:

## Layer 1: View Handles HTTP

```python
# views.py — thin, handles HTTP only
def create_order_view(request):
    cart_items = request.session.get('cart', [])
    address = request.POST['address']

    order = order_service.create_order(
        user_id=request.user.id,
        shipping_address=address,
        cart_items=cart_items,
    )
    return JsonResponse({'order_id': order.id})
```

## Layer 2: Service Has Pure Business Logic

```python
# services.py
@dataclass
class CartItem:
    product_id: int
    quantity: int

class OrderService:
    def __init__(self, order_repo, product_repo, mailer, config):
        self._orders = order_repo
        self._products = product_repo
        self._mailer = mailer
        self._config = config

    def create_order(self, user_id: int, shipping_address: str,
                     cart_items: list[CartItem]) -> Order:
        # Validate stock
        line_items = []
        for item in cart_items:
            product = self._products.get(item.product_id)
            if product.stock < item.quantity:
                raise InsufficientStock(product.name)
            line_items.append((product, item.quantity))

        # Create order
        order = self._orders.create_order(
            user_id=user_id,
            shipping_address=shipping_address,
            line_items=line_items,
        )

        # Business rule: free shipping threshold
        if order.total > self._config.free_shipping_threshold:
            order.shipping_cost = Decimal(0)
        else:
            order.shipping_cost = self._config.shipping_rate

        self._orders.save(order)

        # Side effect: notification
        self._mailer.send_order_confirmation(order)

        return order
```

## Layer 3: Repos Wrap Django ORM

```python
# repos.py
class DjangoOrderRepo:
    def create_order(self, user_id, shipping_address, line_items):
        with transaction.atomic():
            order = Order.objects.create(user_id=user_id, ...)
            for product, qty in line_items:
                OrderItem.objects.create(order=order, product=product, ...)
                product.stock -= qty
                product.save()
            cache.delete(f'user_orders_{user_id}')
        return order
```

## Now Testing Is Easy

```python
def test_free_shipping():
    orders = FakeOrderRepo()
    products = FakeProductRepo(stock=100)
    mailer = FakeMailer()
    config = Config(free_shipping_threshold=50, shipping_rate=10)

    service = OrderService(orders, products, mailer, config)
    order = service.create_order(
        user_id=1,
        shipping_address="123 Main St",
        cart_items=[CartItem(product_id=1, quantity=1)],
    )
    assert order.shipping_cost == 0  # No Django needed!
```

**The boundary rule**: Business logic should never import from `django.*`. If it does, you have a coupling problem.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
