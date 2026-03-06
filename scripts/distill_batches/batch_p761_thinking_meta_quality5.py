"""Phase 3F: Metacognition — Code Quality Judgment (Part 5)

Scenario 7: Rate error handling completeness.
Scenario 8: Rate API design quality (DX perspective).
"""

PAIRS = [
    (
        "thinking/meta-quality-error-handling-payment-flow",
        r'''Rate the error handling completeness of this payment flow (1-10):

```python
def process_payment(order_id, payment_token):
    order = db.query(Order).get(order_id)
    charge = stripe.Charge.create(
        amount=int(order.total * 100),
        currency='usd',
        source=payment_token
    )
    order.status = 'paid'
    order.charge_id = charge.id
    db.commit()
    send_receipt_email(order)
    return {"success": True, "charge_id": charge.id}
```''',
        r'''<think>
Let me enumerate all failure modes:

1. `db.query(Order).get(order_id)` — order_id doesn't exist → returns None → next line crashes with AttributeError on `None.total`. NOT HANDLED.

2. `stripe.Charge.create()` can raise:
   - `stripe.CardError` — card declined, insufficient funds
   - `stripe.RateLimitError` — too many API calls
   - `stripe.InvalidRequestError` — invalid parameters
   - `stripe.AuthenticationError` — bad API key
   - `stripe.APIConnectionError` — network failure to Stripe
   - `stripe.StripeError` — catch-all
   NONE HANDLED.

3. `db.commit()` can fail (connection lost, constraint violation). If it fails AFTER Stripe charged but BEFORE recording the charge_id, we've charged the customer but lost the reference. CRITICAL data loss scenario. NOT HANDLED.

4. `send_receipt_email()` can fail (SMTP error, template error). If it fails, the function crashes even though payment succeeded. NOT HANDLED.

5. Order could already be paid (`order.status == 'paid'`). Double-charging. NOT CHECKED.

6. `int(order.total * 100)` — floating point precision issue. `19.99 * 100` might give `1998.9999...` → `1998` instead of `1999`. NOT HANDLED.

Count: 0 out of 6+ failure modes handled. Score: 1/10.
</think>

**Error handling: 1/10 — Zero failure modes handled.**

**Failure modes enumerated:**
| # | Failure | Consequence | Handled? |
|---|---------|-------------|----------|
| 1 | Order not found | `AttributeError: NoneType has no attribute 'total'` | ❌ |
| 2 | Card declined | Unhandled `stripe.CardError` → 500 error | ❌ |
| 3 | Stripe network error | Unhandled exception → 500 error | ❌ |
| 4 | db.commit fails after charge | Customer charged, no record saved | ❌ |
| 5 | Email fails | Function crashes despite successful payment | ❌ |
| 6 | Double payment | No idempotency check | ❌ |
| 7 | Float precision | `19.99 * 100 = 1998` not `1999` | ❌ |

**Fixed version:**
```python
def process_payment(order_id, payment_token):
    order = db.query(Order).get(order_id)
    if not order:
        return {"error": "Order not found"}, 404
    if order.status == "paid":
        return {"error": "Order already paid"}, 409

    # Fix float precision
    amount_cents = int(round(order.total * 100))

    try:
        charge = stripe.Charge.create(
            amount=amount_cents,
            currency='usd',
            source=payment_token,
            idempotency_key=f"order-{order_id}",  # Prevent double charges
        )
    except stripe.CardError as e:
        return {"error": f"Card declined: {e.user_message}"}, 402
    except stripe.StripeError as e:
        logger.exception(f"Stripe error for order {order_id}")
        return {"error": "Payment service unavailable"}, 503

    # Record charge BEFORE committing — this is the critical section
    order.status = 'paid'
    order.charge_id = charge.id
    try:
        db.commit()
    except Exception:
        logger.critical(f"DB commit failed after charge {charge.id} for order {order_id}")
        # Charge succeeded but DB failed — needs manual reconciliation
        raise

    # Email is non-critical — don't fail the payment if email fails
    try:
        send_receipt_email(order)
    except Exception:
        logger.warning(f"Receipt email failed for order {order_id}")

    return {"success": True, "charge_id": charge.id}
```'''
    ),
    (
        "thinking/meta-quality-error-handling-file-pipeline",
        r'''Rate the error handling completeness of this file processing pipeline (1-10):

```python
def process_csv_upload(filepath):
    with open(filepath) as f:
        reader = csv.DictReader(f)
        results = []
        for row in reader:
            user = User(
                name=row['name'],
                email=row['email'],
                age=int(row['age']),
            )
            db.add(user)
            results.append(user.email)
        db.commit()
    os.remove(filepath)
    return {"imported": len(results), "emails": results}
```''',
        r'''<think>
Failure modes:

1. `open(filepath)` — file doesn't exist, permission denied. NOT HANDLED.
2. `csv.DictReader` — file isn't valid CSV, wrong encoding. NOT HANDLED.
3. `row['name']` — column 'name' doesn't exist in CSV. NOT HANDLED (KeyError).
4. `int(row['age'])` — age isn't a number ("twenty", "", "N/A"). NOT HANDLED (ValueError).
5. `db.add(user)` — could fail on constraint violations (duplicate email). NOT HANDLED.
6. `db.commit()` — if any row is invalid, the entire batch fails. No partial success handling.
7. `os.remove(filepath)` — if processing fails, file is never cleaned up. If processing succeeds but remove fails (permissions), function crashes after successful import.
8. Bad rows: One bad row kills the entire import. No skip-bad-rows behavior.
9. Large files: Loads all results into memory. For 1M rows, this could OOM.
10. No progress reporting or logging for long imports.
11. Encoding: if file has non-UTF-8 characters, `open()` may fail or corrupt data.

Count: 0 out of 8+ failure modes handled. Score: 1/10.
</think>

**Error handling: 1/10**

**Failure modes:**
| # | Failure | Consequence | Handled? |
|---|---------|-------------|----------|
| 1 | File not found | Unhandled FileNotFoundError | ❌ |
| 2 | Wrong CSV format | Unhandled KeyError or empty data | ❌ |
| 3 | Missing columns | KeyError crashes entire import | ❌ |
| 4 | Invalid age ("N/A") | ValueError crashes entire import | ❌ |
| 5 | Duplicate email | IntegrityError crashes, no rows imported | ❌ |
| 6 | One bad row | Entire batch fails, no partial success | ❌ |
| 7 | File cleanup | Not cleaned up on error | ❌ |
| 8 | Encoding | Non-UTF-8 corrupts or crashes | ❌ |

**Fixed version:**
```python
def process_csv_upload(filepath):
    required_columns = {'name', 'email', 'age'}
    results = {"imported": 0, "errors": []}

    try:
        with open(filepath, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            if not required_columns.issubset(set(reader.fieldnames or [])):
                missing = required_columns - set(reader.fieldnames or [])
                return {"error": f"Missing columns: {missing}"}, 400

            for line_num, row in enumerate(reader, start=2):
                try:
                    user = User(
                        name=row['name'].strip(),
                        email=row['email'].strip().lower(),
                        age=int(row['age']),
                    )
                    db.add(user)
                    db.flush()  # Check constraints per row
                    results["imported"] += 1
                except (ValueError, KeyError) as e:
                    results["errors"].append(f"Row {line_num}: {e}")
                    db.rollback()
                except IntegrityError:
                    results["errors"].append(f"Row {line_num}: duplicate email {row.get('email')}")
                    db.rollback()

        db.commit()
    except FileNotFoundError:
        return {"error": "File not found"}, 404
    except UnicodeDecodeError:
        return {"error": "File encoding error, expected UTF-8"}, 400
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

    return results
```

**Key improvements:** skip-bad-rows behavior, column validation, encoding handling, guaranteed cleanup via `finally`, per-row error reporting.'''
    ),
    (
        "thinking/meta-quality-error-handling-robust-api",
        r'''Rate the error handling completeness of this API client wrapper (1-10):

```python
class WeatherClient:
    def __init__(self, api_key: str, base_url: str = "https://api.weather.com/v1"):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        self.base_url = base_url
        self.session.timeout = 10

    def get_forecast(self, city: str) -> dict:
        try:
            response = self.session.get(f"{self.base_url}/forecast", params={"city": city})
            response.raise_for_status()
            return response.json()
        except requests.ConnectionError:
            raise WeatherAPIError("Cannot connect to weather service")
        except requests.Timeout:
            raise WeatherAPIError("Weather service timed out")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                raise CityNotFoundError(f"City '{city}' not found")
            elif e.response.status_code == 429:
                retry_after = e.response.headers.get("Retry-After", "60")
                raise RateLimitError(f"Rate limited, retry after {retry_after}s")
            elif e.response.status_code >= 500:
                raise WeatherAPIError(f"Weather service error: {e.response.status_code}")
            else:
                raise WeatherAPIError(f"Unexpected error: {e.response.status_code}")
        except ValueError:
            raise WeatherAPIError("Invalid JSON response from weather service")
```''',
        r'''<think>
Let me analyze error handling coverage:

1. **Connection error** — handled, wraps in WeatherAPIError ✓
2. **Timeout** — handled, wraps in WeatherAPIError ✓
3. **404 Not Found** — handled, specific CityNotFoundError ✓
4. **429 Rate Limited** — handled with retry-after header ✓
5. **5xx Server Error** — handled ✓
6. **Other HTTP errors (400, 401, 403)** — handled, generic message ✓
7. **Invalid JSON response** — handled (ValueError from response.json()) ✓
8. **SSL/TLS errors** — not explicitly handled, but caught by ConnectionError ✓
9. **DNS resolution failure** — caught by ConnectionError ✓
10. **Redirect loops** — caught by requests internally (TooManyRedirects) — NOT HANDLED ✗
11. **Empty response body** — response.json() on empty body raises ValueError → caught ✓
12. **API key invalid/expired** — would be a 401, caught by "Unexpected error" branch. Could be more specific. MINOR ✗

Custom exception hierarchy with specific types (CityNotFoundError, RateLimitError) is good design — callers can handle specific cases.

The timeout is set on the session, not per-request, which is fine.

Score: 8/10. Very good coverage. Missing TooManyRedirects and specific 401 handling, but overall solid.
</think>

**Error handling: 8/10 — Solid coverage with good exception hierarchy.**

**Coverage:**
| Failure mode | Handled? | Exception raised |
|-------------|----------|-----------------|
| Connection failed | ✅ | WeatherAPIError |
| Timeout | ✅ | WeatherAPIError |
| City not found (404) | ✅ | CityNotFoundError |
| Rate limited (429) | ✅ | RateLimitError (with retry-after) |
| Server error (5xx) | ✅ | WeatherAPIError |
| Invalid JSON | ✅ | WeatherAPIError |
| DNS failure | ✅ | WeatherAPIError (via ConnectionError) |
| Redirect loop | ❌ | Unhandled TooManyRedirects |
| Auth failure (401) | ⚠️ | Generic "Unexpected error" |

**What's done well:**
- Custom exception hierarchy (callers can handle specific cases)
- Rate limit includes retry-after header
- Session with default timeout
- Clean separation of HTTP errors by status code

**Minor improvements (-2 points):**
```python
except requests.TooManyRedirects:
    raise WeatherAPIError("Too many redirects")
except requests.HTTPError as e:
    if e.response.status_code == 401:
        raise WeatherAuthError("Invalid or expired API key")
    # ... rest of handling
```

**This is a good template for API client error handling.** The key pattern: catch requests exceptions → wrap in domain-specific exceptions → let callers handle specific cases (retry on RateLimitError, show user message on CityNotFoundError).'''
    ),
    (
        "thinking/meta-quality-api-design-inconsistent",
        r'''Rate the API design quality of these endpoints (1-10):

```
POST /api/createUser          {"userName": "alice", "e_mail": "alice@example.com"}
GET  /api/user/get?id=123
PUT  /api/update-user/123     {"user_name": "alice", "email": "alice@example.com"}
DELETE /api/users/remove/123
GET  /api/getAllUsers?page_num=1&items_per_page=20
GET  /api/user/123/orders
POST /api/order/create        {"userId": 123, "productID": 456}
```''',
        r'''<think>
Let me evaluate on API design axes:

**Consistency:**
- URL patterns: `/createUser`, `/user/get`, `/update-user/123`, `/users/remove/123` — 4 different naming conventions for the same resource
- Casing: camelCase (`createUser`), kebab-case (`update-user`), slash-separated (`users/remove`)
- Parameter casing: `userName`, `e_mail`, `user_name`, `email`, `userId`, `productID` — 4+ different casing styles in one API
- Resource naming: sometimes `/user`, sometimes `/users`, sometimes verb-in-path

**RESTfulness:**
- `POST /api/createUser` — verb in URL (should be `POST /api/users`)
- `GET /api/user/get?id=123` — verb in URL + ID in query (should be `GET /api/users/123`)
- `DELETE /api/users/remove/123` — verb in URL (should be `DELETE /api/users/123`)
- `POST /api/order/create` — verb in URL (should be `POST /api/orders`)

**Discoverability:**
- No consistent pattern to guess endpoints
- Can't predict URL structure from one endpoint to another

**Pagination:**
- `page_num` and `items_per_page` — non-standard. Most APIs use `page`/`per_page` or `offset`/`limit`.

Score: 2/10. Wildly inconsistent naming, verbs in URLs, mixed casing, unpredictable structure.
</think>

**API Design: 2/10 — Wildly inconsistent.**

**Issues:**

| Problem | Examples |
|---------|---------|
| Verbs in URLs | `createUser`, `user/get`, `users/remove`, `order/create` |
| Inconsistent casing | `userName`, `e_mail`, `user_name`, `userId`, `productID` |
| Inconsistent pluralization | `/user/123` vs `/users/remove/123` |
| ID placement | query param `?id=123` vs path `/123` |
| Non-standard pagination | `page_num`, `items_per_page` |

**Fixed — consistent REST API:**
```
POST   /api/users              {"username": "alice", "email": "alice@example.com"}
GET    /api/users/123
PUT    /api/users/123          {"username": "alice", "email": "alice@example.com"}
DELETE /api/users/123
GET    /api/users?page=1&per_page=20
GET    /api/users/123/orders
POST   /api/orders             {"user_id": 123, "product_id": 456}
```

**Rules applied:**
1. **Nouns, not verbs**: `/users` not `/createUser`
2. **Plural resources**: `/users` not `/user`
3. **HTTP methods ARE the verbs**: POST=create, GET=read, PUT=update, DELETE=delete
4. **Consistent casing**: `snake_case` everywhere (JSON fields and query params)
5. **IDs in path**: `/users/123` not `?id=123`
6. **Standard pagination**: `page` + `per_page`

**The test: can a new developer guess the endpoint?** If they know `GET /api/users/123` exists, they should be able to guess `DELETE /api/users/123` and `GET /api/users/123/orders`. With the original API, they can't.'''
    ),
    (
        "thinking/meta-quality-api-design-well-designed",
        r'''Rate the API design quality of these endpoints (1-10):

```
GET    /api/v1/projects                          → 200 {"data": [...], "meta": {"total": 42, "page": 1, "per_page": 20}}
POST   /api/v1/projects                          → 201 {"data": {"id": 1, ...}} | 422 {"errors": [{"field": "name", "message": "is required"}]}
GET    /api/v1/projects/1                         → 200 {"data": {...}} | 404 {"error": {"code": "not_found", "message": "Project not found"}}
PUT    /api/v1/projects/1                         → 200 {"data": {...}} | 422 {"errors": [...]}
DELETE /api/v1/projects/1                         → 204 | 404
GET    /api/v1/projects/1/tasks                   → 200 {"data": [...], "meta": {...}}
POST   /api/v1/projects/1/tasks                   → 201 {"data": {...}}
GET    /api/v1/projects/1/tasks?status=open&sort=-created_at&page=2  → 200 {"data": [...], "meta": {...}}
```''',
        r'''<think>
Let me evaluate:

**Consistency:** 5/5
- All endpoints follow the same pattern: `/api/v1/{resource}/{id}/{sub-resource}`
- All responses wrapped in `{"data": ...}` envelope
- All list responses include `{"meta": ...}` for pagination
- All errors follow the same structure

**RESTfulness:** 5/5
- Proper HTTP methods (GET/POST/PUT/DELETE)
- Proper status codes (200, 201, 204, 404, 422)
- Resources are nouns, HTTP methods are verbs
- Nested resources for relationships (`/projects/1/tasks`)

**Discoverability:** 5/5
- Predictable URL structure
- From `/projects` you can guess `/projects/1`, `/projects/1/tasks`
- Consistent query parameter patterns (`status`, `sort`, `page`)

**Error handling:** 5/5
- Validation errors (422) include field-level details
- Not found (404) has machine-readable code + human message
- Different error structures for different error types (field errors vs resource errors)

**Pagination:** 5/5
- Standard `page`/`per_page` parameters
- Response includes `total`, `page`, `per_page` in meta
- Sort with `-` prefix for descending (convention)

**Versioning:** Present (`/v1/`)

**Only minor concerns:**
- No HATEOAS links (but that's overkill for most APIs)
- No rate limit headers shown (X-RateLimit-*)
- No ETag/caching headers mentioned

Score: 9/10. Excellent API design following REST best practices.
</think>

**API Design: 9/10 — Excellent REST API.**

| Axis | Score | Notes |
|------|-------|-------|
| Consistency | 5/5 | Same patterns everywhere |
| RESTfulness | 5/5 | Proper methods, status codes, resource structure |
| Discoverability | 5/5 | Predictable from any single endpoint |
| Error handling | 5/5 | Field-level validation + machine-readable codes |
| Pagination | 5/5 | Standard params, meta in response |

**What's done right:**
- **Envelope pattern**: `{"data": ...}` for all responses — room for metadata without breaking changes
- **Consistent errors**: Validation errors have `field` + `message` array, not-found has `code` + `message`
- **Versioning**: `/v1/` from day one
- **Sort syntax**: `-created_at` for descending (widely adopted convention)
- **Proper status codes**: 201 for created, 204 for deleted, 422 for validation

**Why 9 and not 10:**
- No rate limit headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`)
- No cache headers (ETag, Cache-Control) for GET responses
- No `Link` header for pagination (nice to have, not required)

**This API passes the "new developer test":** Given one endpoint, you can predict the rest. That's the hallmark of good API design.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
