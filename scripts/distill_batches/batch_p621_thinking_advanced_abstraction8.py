"""Phase 2G: Advanced Reasoning — Abstraction Laddering (Part 8/8)"""

PAIRS = [
    (
        "thinking/abstraction-api-gateway-to-edge-computing",
        "We need to add authentication, rate limiting, and request logging to all our microservices. Should I add this logic to each service?",
        r'''<think>
Cross-cutting concerns across microservices. Let me ladder from concrete to abstract.

**Concrete: Adding auth/rate-limiting/logging to each service**
- Copy-paste the same middleware to 10 services
- Every service has auth logic, rate limit logic, logging logic
- When auth changes, update 10 services
- When rate limit rules change, deploy 10 services

This is the wrong approach. These are CROSS-CUTTING CONCERNS — they apply to all services equally.

**Pattern level: API Gateway**
Put a single entry point in front of all services. It handles the concerns once:
- Authentication → API Gateway verifies JWT, adds user info to headers
- Rate limiting → API Gateway counts requests, rejects excess
- Logging → API Gateway logs all requests
- Services → only implement business logic

**Principle level: Edge computing / edge enforcement**
The gateway pattern is an instance of a broader principle: enforce policies at the EDGE, not in every service.

This applies beyond just API gateways:
- CDN (edge caching): cache responses close to the user
- WAF (edge security): block attacks before they reach services
- Service mesh (edge networking): manage service-to-service communication at the network layer
- Edge functions (Cloudflare Workers, Lambda@Edge): run custom logic at the edge

**Policy level: Separation of infrastructure concerns from business logic**
Services should contain BUSINESS LOGIC only. Infrastructure concerns (auth, rate limiting, observability, TLS, retries) belong in the infrastructure layer.

This is the "sidecar" philosophy: attach infrastructure capabilities to services without modifying them.
</think>

No — don't add the same logic to each service. Let me build up from the concrete fix to the broader principle.

## Level 1: Concrete — API Gateway

```
WITHOUT GATEWAY:
  Client → Auth → RateLimit → Log → Service A
  Client → Auth → RateLimit → Log → Service B
  Client → Auth → RateLimit → Log → Service C
  (Same logic copy-pasted into EVERY service)

WITH GATEWAY:
  Client → [API Gateway: Auth + RateLimit + Log] → Service A
                                                  → Service B
                                                  → Service C
  (Logic implemented ONCE)
```

```nginx
# Practical: Nginx as API Gateway

upstream users_service { server users:8001; }
upstream orders_service { server orders:8002; }

server {
    listen 443 ssl;

    # CROSS-CUTTING: Rate limiting (once, for all services)
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;

    # CROSS-CUTTING: Logging (once)
    access_log /var/log/nginx/api_access.log json_format;

    # CROSS-CUTTING: Auth (via auth subrequest)
    location = /_auth {
        internal;
        proxy_pass http://auth-service:8000/verify;
        proxy_pass_request_body off;
        proxy_set_header X-Original-URI $request_uri;
    }

    # Route to services (services only have business logic)
    location /api/users/ {
        auth_request /_auth;
        limit_req zone=api burst=20;
        proxy_pass http://users_service;
    }

    location /api/orders/ {
        auth_request /_auth;
        limit_req zone=api burst=20;
        proxy_pass http://orders_service;
    }
}
```

## Level 2: Pattern — Cross-Cutting Concerns at the Edge

```
The API Gateway is one instance of a broader pattern:
ENFORCE POLICIES AT THE EDGE, NOT IN EVERY SERVICE.

WHAT BELONGS AT THE EDGE:             WHAT BELONGS IN THE SERVICE:
  Authentication                        Business logic
  Authorization (coarse-grained)        Domain validation
  Rate limiting                         Data access
  Request/response logging              Business rules
  CORS handling                         Domain events
  SSL termination
  Request transformation
  Response caching
  API versioning routing
```

```python
# Services become clean — only business logic:

# ❌ Before: every service has infrastructure code
@app.post("/orders")
def create_order(request):
    # Auth (infrastructure)
    token = request.headers.get("Authorization")
    user = verify_jwt(token)
    if not user:
        return 401

    # Rate limit (infrastructure)
    if rate_limiter.is_exceeded(user.id):
        return 429

    # Logging (infrastructure)
    logger.info(f"Creating order for {user.id}")

    # Business logic (the only part this service should handle)
    order = Order.create(user_id=user.id, items=request.json["items"])
    return {"id": order.id}, 201


# ✅ After: service only has business logic
@app.post("/orders")
def create_order(request):
    # Auth, rate limiting, logging all handled by gateway
    # User info passed in headers by gateway
    user_id = request.headers["X-User-ID"]

    order = Order.create(user_id=user_id, items=request.json["items"])
    return {"id": order.id}, 201
```

## Level 3: Principle — Infrastructure Concerns as Layers

```
The edge enforcement principle extends beyond API gateways:

LAYER 1: CDN / Edge (Cloudflare, CloudFront)
  - Static content caching
  - DDoS protection
  - Geographic routing
  - Edge functions (Cloudflare Workers)

LAYER 2: API Gateway (Kong, Nginx, AWS API Gateway)
  - Authentication
  - Rate limiting
  - Request routing
  - API versioning

LAYER 3: Service Mesh (Istio, Linkerd)
  - Service-to-service auth (mTLS)
  - Retries and circuit breaking
  - Traffic shaping
  - Distributed tracing

LAYER 4: Your Service
  - Business logic ONLY
  - Domain validation
  - Data access

Each layer handles its concerns. Services stay focused.
```

## Level 4: Policy — Separation of Concerns as Architecture

```
ARCHITECTURAL RULE:
  A microservice should contain ZERO infrastructure code.

Infrastructure belongs in:
  - API Gateway configuration
  - Service mesh configuration
  - Sidecar containers
  - Platform-provided middleware

When you find yourself copy-pasting the same code across services:
  1. Identify it as a cross-cutting concern
  2. Extract it to the appropriate infrastructure layer
  3. Services get it "for free" by being behind that layer

This principle is why Kubernetes, service meshes, and API gateways exist:
to SEPARATE infrastructure concerns from business logic so teams can
focus on what their service actually does.
```'''
    ),
    (
        "thinking/abstraction-retry-to-resilience-strategy",
        "Our API calls to a payment provider sometimes fail with 503 errors. I added a retry with exponential backoff but it still fails sometimes. What else should I do?",
        r'''<think>
Retry for 503 errors — let me ladder this up.

**Concrete: retry with backoff**
They have this. Good start. But not enough.

**Pattern: retry is one part of a resilience strategy**
A retry handles: transient failures (temporary blips).
It doesn't handle: sustained outages, cascading failures, or degraded performance.

The full resilience toolkit:
1. Retry with backoff → handle transient failures
2. Circuit breaker → stop retrying when provider is DOWN (not just slow)
3. Timeout → don't wait forever
4. Fallback → degrade gracefully when provider is unavailable
5. Idempotency → ensure retries don't cause duplicate charges

**Principle: resilience = preparing for failure at every level**
Not just "retry if it fails" but "what's the user experience when it fails?"

**Policy: every external dependency needs a resilience strategy**
</think>

Retry is step one. Let me build the complete resilience strategy.

## Level 1: Concrete — Your Current Retry (Good Start)

```python
# What you have:
import time

def charge_customer(amount, customer_id):
    for attempt in range(3):
        try:
            return payment_api.charge(amount, customer_id)
        except ServiceUnavailable:
            wait = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait)
    raise PaymentError("Payment provider unavailable after 3 retries")
```

```
This handles: temporary blip → retry → succeeds on attempt 2 or 3
This DOESN'T handle:
  ✗ Provider is down for 10 minutes (all retries fail, user waits 7 seconds)
  ✗ Provider is slow (30-second response times eat your thread pool)
  ✗ Retry causes duplicate charge (charge went through, but response was lost)
  ✗ 1000 users retrying simultaneously → you DDoS the provider
```

## Level 2: Pattern — Complete Resilience Stack

```python
import time
import random
from functools import wraps

# 1. TIMEOUT — don't wait forever
def charge_customer(amount, customer_id):
    try:
        return payment_api.charge(
            amount, customer_id,
            timeout=5  # 5 second max — give up if slower
        )
    except Timeout:
        raise PaymentError("Payment provider too slow")


# 2. RETRY WITH JITTER — avoid thundering herd
def retry_with_jitter(max_attempts=3, base_delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (ServiceUnavailable, Timeout) as e:
                    if attempt == max_attempts - 1:
                        raise
                    # Jitter prevents 1000 clients retrying at the same moment
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
        return wrapper
    return decorator


# 3. CIRCUIT BREAKER — stop trying when provider is down
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failures = 0
        self.threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure = None
        self.is_open = False

    def call(self, func, *args, **kwargs):
        if self.is_open:
            if time.time() - self.last_failure < self.recovery_timeout:
                raise CircuitOpenError("Payment provider circuit open")
            # Try one request to test recovery
            self.is_open = False

        try:
            result = func(*args, **kwargs)
            self.failures = 0
            return result
        except Exception:
            self.failures += 1
            self.last_failure = time.time()
            if self.failures >= self.threshold:
                self.is_open = True
            raise


# 4. IDEMPOTENCY — prevent duplicate charges on retry
def charge_customer_safe(amount, customer_id):
    idempotency_key = generate_idempotency_key(customer_id, amount)
    # Payment provider uses this key to deduplicate
    # If the same key is sent twice, it returns the original result
    return payment_api.charge(
        amount, customer_id,
        idempotency_key=idempotency_key,
        timeout=5
    )


# 5. FALLBACK — degrade gracefully
def charge_with_fallback(amount, customer_id):
    try:
        return payment_breaker.call(charge_customer_safe, amount, customer_id)
    except (PaymentError, CircuitOpenError):
        # Queue for later processing instead of failing immediately
        payment_queue.enqueue({
            "amount": amount,
            "customer_id": customer_id,
            "status": "pending",
            "queued_at": datetime.utcnow(),
        })
        return {"status": "pending", "message": "Payment will be processed shortly"}
```

## Level 3: Principle — Resilience as User Experience Design

```
The question isn't "how do I handle the 503?"
The question is "what does the USER experience when the provider is down?"

OPTION A: User sees error immediately
  → Bad UX but honest. User might retry or leave.

OPTION B: User sees "processing..." → background retry
  → Good UX. User isn't blocked. Payment processes when provider recovers.

OPTION C: User sees nothing different → queue + webhook
  → Best UX. "Order confirmed! Payment processing."
  → Background worker retries until success.
  → If it ultimately fails, notify user (email/notification).

Most payment systems use OPTION C in production.
```

## Level 4: Policy — Resilience Strategy Checklist

```
For EVERY external dependency, define:

  DEPENDENCY: Payment Provider
  ├── Timeout: 5 seconds
  ├── Retry: 3 attempts, exponential backoff + jitter
  ├── Circuit breaker: 5 failures → open for 60 seconds
  ├── Fallback: queue for background processing
  ├── Idempotency: key based on customer_id + order_id
  ├── Monitoring: alert when circuit breaker opens
  └── SLA: 99.9% availability, 200ms p95 latency

  DEPENDENCY: Email Service
  ├── Timeout: 10 seconds
  ├── Retry: 5 attempts over 1 hour (not time-critical)
  ├── Circuit breaker: 10 failures → open for 5 minutes
  ├── Fallback: queue in dead letter queue for manual review
  └── SLA: 99% availability (emails can be delayed)

  DEPENDENCY: Analytics API
  ├── Timeout: 2 seconds
  ├── Retry: none (fire and forget)
  ├── Circuit breaker: 3 failures → open for 30 seconds
  ├── Fallback: drop the event (analytics loss is acceptable)
  └── SLA: best effort
```

Different dependencies need different resilience strategies. A payment failure needs retry and queue. An analytics failure can be silently dropped. Match the strategy to the business impact.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
