"""Phase 2H: Advanced Reasoning — First Principles Derivation (Part 9)"""

PAIRS = [
    (
        "thinking/firstprinciples-why-logging-matters",
        "Why is logging important? I know I 'should' add logging but I don't understand what to log, where, or how much. My app prints to console and that seems fine.",
        r'''<think>
Logging from first principles. Why does it exist?

**The root problem: observability after deployment**
During development, you can step through code with a debugger. In production, you can't attach a debugger to a server handling 1000 requests per second. Logging is your ONLY window into what the production system is doing.

**Without logging:**
- "Users report the checkout is broken"
- "When did it start?"
- "What error are they seeing?"
- "Which requests are affected?"
- "Is it all users or specific ones?"
- Answer to all: "We don't know. Let me try to reproduce it locally."

This could take hours or days. With logging, you search the logs and have answers in minutes.

**What logging provides:**
1. Debugging: what happened before the error?
2. Auditing: who did what, when?
3. Monitoring: how many errors per minute? Is the rate increasing?
4. Performance: which requests are slow? Why?
5. Business intelligence: how many users signed up today? Which features are used?

**What to log (the principle):**
Log the things you'll WISH you had when something goes wrong at 3 AM:
- Request/response metadata (not bodies)
- Error details with context
- Business-significant events
- Performance timing for external calls

**What NOT to log:**
- Sensitive data (passwords, tokens, PII)
- Every successful operation in detail (noise)
- Large payloads (expensive, fills storage)

**Log levels derive from urgency:**
- ERROR: something failed, needs attention now
- WARN: something unexpected, might become a problem
- INFO: significant business events (user registered, order placed)
- DEBUG: detailed technical info (query executed, cache hit/miss)
</think>

Let me derive logging from the problem it solves: **you can't attach a debugger to production**.

## The Root Problem

```
DEVELOPMENT:
  Bug happens → set breakpoint → step through code → see every variable
  → find the bug → fix it. Takes minutes.

PRODUCTION:
  Bug happens → "Users report checkout is broken"
  → "When?" "Don't know"
  → "What error?" "Don't know"
  → "Which users?" "Don't know"
  → "Can you reproduce it?" "I'll try on my machine..."
  → Takes hours or days.

WITH LOGGING:
  Bug happens → search logs: "level=error path=/checkout"
  → "Started at 14:32, affecting 12% of requests"
  → "Error: payment provider returning 503"
  → "Only users with promo codes are affected"
  → Root cause found in 5 minutes.
```

## What to Log (Derived from What You'll Need)

```python
import logging
import time

logger = logging.getLogger(__name__)

# LEVEL: ERROR — something FAILED, needs attention
# Log when: an operation that should succeed didn't
@app.post("/orders")
async def create_order(data: OrderRequest):
    try:
        order = await order_service.create(data)
    except PaymentError as e:
        logger.error(
            "Payment failed",
            extra={
                "user_id": data.user_id,
                "amount": data.total,
                "error": str(e),
                "payment_provider": "stripe",
            }
        )
        raise

# LEVEL: WARNING — something UNEXPECTED, might become a problem
# Log when: degraded but still working
async def get_user_profile(user_id):
    try:
        return await cache.get(f"user:{user_id}")
    except ConnectionError:
        logger.warning(
            "Cache unavailable, falling back to database",
            extra={"user_id": user_id}
        )
        return await db.get_user(user_id)  # Still works, just slower

# LEVEL: INFO — significant BUSINESS events
# Log when: something worth knowing about happened
async def register_user(email, name):
    user = await User.create(email=email, name=name)
    logger.info("User registered", extra={"user_id": user.id, "email": email})
    return user

# LEVEL: DEBUG — technical DETAILS for deep investigation
# Log when: tracking the exact flow for debugging
async def process_payment(order_id, amount):
    logger.debug("Starting payment", extra={"order_id": order_id, "amount": amount})
    result = await stripe.charge(amount)
    logger.debug("Payment result", extra={"order_id": order_id, "status": result.status})
    return result
```

## What NOT to Log

```python
# ❌ DON'T log sensitive data
logger.info(f"Login attempt: {username} / {password}")      # NEVER log passwords
logger.info(f"Token: {jwt_token}")                           # NEVER log tokens
logger.info(f"Credit card: {card_number}")                   # NEVER log PII
logger.info(f"Request body: {request.json()}")               # Might contain sensitive data

# ❌ DON'T log every successful trivial operation
for item in items:
    logger.info(f"Processing item {item.id}")  # 10,000 log lines per request
# Log the batch instead:
logger.info(f"Processed {len(items)} items", extra={"order_id": order.id})

# ❌ DON'T log large payloads
logger.debug(f"Response: {json.dumps(huge_api_response)}")  # 10MB per log line
# Log a summary:
logger.debug(f"API response: {len(results)} results, {response.status_code}")
```

## Structured Logging (The Right Format)

```python
# ❌ Unstructured: hard to search, hard to parse
logger.info("User 42 created order 789 for $99.99")
# How do you find all orders over $50? grep with regex? Fragile.

# ✅ Structured (JSON): searchable, parseable, filterable
import structlog

logger = structlog.get_logger()

logger.info("order_created",
    user_id=42,
    order_id=789,
    amount=99.99,
    currency="usd",
    item_count=3,
)
# Output: {"event": "order_created", "user_id": 42, "order_id": 789,
#          "amount": 99.99, "currency": "usd", "item_count": 3,
#          "timestamp": "2024-03-05T14:32:01Z"}

# Now you can:
# - Search: user_id=42 AND amount>50
# - Aggregate: count by event type per hour
# - Alert: error rate > 5% in last 5 minutes
# - Dashboard: orders per minute, average amount, error rate
```

## Log Levels in Practice

```
PRODUCTION servers: LOG_LEVEL=INFO
  Shows: errors, warnings, business events
  Hides: debug details (too noisy, too expensive)

DEBUGGING an issue: LOG_LEVEL=DEBUG (temporarily)
  Shows: everything, including detailed technical flow
  Warning: generates 10-100x more log volume

  ERROR   ████████████████████████  Always log. Page someone.
  WARNING ████████████████████      Always log. Review daily.
  INFO    ████████████████          Production default. Business events.
  DEBUG   ████████████              Development + debugging. Technical details.
```

## The Minimum Logging for Any Web App

```python
# Every web app should log AT MINIMUM:

# 1. Request metadata (not bodies)
@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    logger.info("request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration * 1000),
        user_id=getattr(request.state, 'user_id', None),
    )
    return response

# 2. Errors with context
@app.exception_handler(Exception)
async def log_errors(request, exc):
    logger.error("unhandled_error",
        method=request.method,
        path=request.url.path,
        error=str(exc),
        error_type=type(exc).__name__,
        user_id=getattr(request.state, 'user_id', None),
    )

# 3. Business events
logger.info("user_registered", user_id=user.id)
logger.info("order_created", order_id=order.id, amount=order.total)
logger.info("payment_failed", order_id=order.id, error=str(e))

# 4. External service calls
logger.info("external_api_call",
    service="stripe",
    endpoint="/v1/charges",
    duration_ms=150,
    status=200,
)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
