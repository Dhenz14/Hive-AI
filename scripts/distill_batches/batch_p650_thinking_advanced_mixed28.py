"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 28)"""

PAIRS = [
    (
        "thinking/backtrack-premature-abstraction",
        "I refactored my code to use a generic DataProcessor<T> with Strategy pattern, Factory, and Observer. Now nobody on my team can understand it. Was this the right call?",
        r'''<think>
Over-engineering / premature abstraction. The user turned simple code into a complex generic framework that nobody understands.

**The classic trap:**
"This might need to handle different types in the future"
→ Generic DataProcessor<T>
→ Strategy pattern for processing algorithms
→ Factory for creating processors
→ Observer for notifications
→ 500 lines of framework for what was 50 lines of code

**Backtrack: simplify**
If the generic framework is only used with ONE type, it's not a generic — it's unnecessary complexity.

Rules for when to abstract:
- Rule of Three: don't abstract until you have 3 concrete cases
- YAGNI: You Aren't Gonna Need It
- The best code is code your team can understand and modify
</think>

No. If nobody can understand it, the abstraction is wrong — regardless of how "correct" the patterns are.

## The Problem

```python
# ❌ OVER-ENGINEERED: patterns for patterns' sake
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List
from enum import Enum

T = TypeVar('T')

class ProcessingStrategy(ABC, Generic[T]):
    @abstractmethod
    def process(self, data: T) -> T: ...

class ValidationStrategy(ProcessingStrategy[T]):
    def process(self, data: T) -> T: ...

class TransformationStrategy(ProcessingStrategy[T]):
    def process(self, data: T) -> T: ...

class ProcessorFactory:
    _strategies: dict = {}
    @classmethod
    def register(cls, name: str, strategy_cls): ...
    @classmethod
    def create(cls, name: str) -> ProcessingStrategy: ...

class ProcessingObserver(ABC):
    @abstractmethod
    def on_start(self, data): ...
    @abstractmethod
    def on_complete(self, result): ...
    @abstractmethod
    def on_error(self, error): ...

class DataProcessor(Generic[T]):
    def __init__(self, strategies: List[ProcessingStrategy[T]],
                 observers: List[ProcessingObserver]): ...
    def process(self, data: T) -> T: ...

# ... 300 more lines of framework

# ACTUAL USAGE (the only concrete implementation):
processor = ProcessorFactory.create("csv")
result = processor.process(csv_data)

# This is 500 lines of framework to do what could be:
```

```python
# ✅ SIMPLE: does the same thing in 20 lines
def process_csv(filepath):
    data = read_csv(filepath)
    validated = validate_records(data)
    transformed = transform_records(validated)
    return transformed

# When you ACTUALLY need a second processor (JSON? XML?):
def process_json(filepath):
    data = read_json(filepath)
    validated = validate_records(data)  # Reuse validation
    transformed = transform_records(validated)  # Reuse transformation
    return transformed

# Now you have TWO concrete cases. Maybe extract shared logic:
def process_file(filepath, reader):
    data = reader(filepath)
    validated = validate_records(data)
    return transform_records(validated)

# Usage:
process_file("data.csv", read_csv)
process_file("data.json", read_json)

# Three lines of code replaced 500 lines of framework.
# Everyone on the team understands this immediately.
```

## The Rules

```
RULE OF THREE:
  1 case: just write the code
  2 cases: notice the duplication but don't abstract yet
  3 cases: NOW extract the common pattern
  → You need 3 concrete examples to know WHAT to abstract

YAGNI (You Aren't Gonna Need It):
  "This might need to handle different types someday"
  → Don't build for someday. Build for today.
  → When someday comes, you'll know the real requirements
  → Your premature abstraction probably won't match anyway

THE READABILITY TEST:
  Can a new team member understand this code in 5 minutes?
  YES → good abstraction
  NO → over-abstracted (or wrong abstraction)

THE SIMPLICITY METRIC:
  Simple code that's slightly duplicated > complex code that's DRY
  Three similar 10-line functions > one 50-line generic framework
```

## When Patterns ARE Worth It

```
USE PATTERNS WHEN:
  □ You have 3+ concrete implementations that share logic
  □ The pattern makes the code MORE readable (not less)
  □ The team understands the pattern
  □ The added complexity solves a REAL problem (not a hypothetical one)

DON'T USE PATTERNS WHEN:
  □ You have only 1 implementation
  □ "We might need it later" (YAGNI)
  □ The pattern makes simple code harder to understand
  □ You're using the pattern because it sounds impressive
  □ The straightforward version is < 50 lines
```

**Refactoring advice:** remove the generic framework. Replace with simple functions. When you have 3 concrete processor types, THEN extract the common pattern — and it'll be the RIGHT pattern because you'll know what actually varies.'''
    ),
    (
        "thinking/causal-intermittent-502-errors",
        "We get random 502 Bad Gateway errors from Nginx about 1% of the time. The app logs don't show any errors. Where are these coming from?",
        r'''<think>
502 Bad Gateway from Nginx with no application errors. 1% of the time.

**What 502 means:**
Nginx received an invalid response from the upstream server (your app). This means:
1. The request reached Nginx
2. Nginx tried to forward it to your app
3. Your app either: closed the connection, sent an incomplete response, or wasn't listening

**Why app logs don't show errors:**
The app didn't generate the error — it happened at the connection level between Nginx and the app.

**Possible causes:**

1. **App restart/reload** — during a deploy or auto-restart, there's a brief moment where the app isn't listening. Requests during that window get 502.

2. **Worker timeout** — if using gunicorn/uwsgi, a worker times out and is killed mid-request. Nginx gets a broken connection → 502.

3. **Connection limit** — app has max connections (e.g., gunicorn workers). All workers busy → Nginx sends request → app can't accept → 502.

4. **Keep-alive race condition** — Nginx and app have different keep-alive timeouts. App closes the connection while Nginx is sending a request on it.

5. **OOM kill** — a worker process is killed by the OOM killer (out of memory) during request processing.

**The 1% rate suggests:** keep-alive race condition or worker exhaustion (all workers busy during peak load). If it were deploys, it would be clustered around deploy times.
</think>

502 means **Nginx forwarded the request but your app didn't respond properly**. The app didn't crash — the connection between Nginx and your app broke.

## Most Likely Cause: Keep-Alive Race Condition

```
THE RACE CONDITION:

  Nginx and your app have a persistent connection (keep-alive).
  Nginx keeps connections open to reuse them (faster).

  Timeline:
  T=0:   Connection established, idle
  T=59s: App's keep-alive timeout is 60s → app starts closing connection
  T=59s: Nginx sends a NEW request on this connection (doesn't know it's closing)
  T=59s: App receives request on a half-closed connection → drops it
  T=59s: Nginx: "I sent a request but got no valid response" → 502 Bad Gateway

  This happens randomly, about 1% of the time, exactly matching your symptom.

FIX: Make the app's keep-alive timeout LONGER than Nginx's

  # Nginx (default keep-alive to upstream: 60s)
  upstream backend {
      server app:8000;
      keepalive 32;
  }
  location / {
      proxy_pass http://backend;
      proxy_http_version 1.1;
      proxy_set_header Connection "";
  }

  # Gunicorn: set keepalive higher than Nginx
  gunicorn app:app --keep-alive 75  # 75 > Nginx's 60 → no race condition
```

## Other Common Causes

```python
# CAUSE 2: All workers busy (worker exhaustion)
# Gunicorn has 4 workers. 4 slow requests → all workers busy.
# Request #5: Nginx sends it but no worker available → 502

# Diagnosis:
gunicorn --workers 4 --timeout 30 --access-logfile -
# Look for: requests taking > 30s (timeout kills worker → 502)

# Fix: increase workers OR reduce request time
gunicorn --workers 8 --timeout 60  # More workers + longer timeout

# Better fix: find and fix the slow requests


# CAUSE 3: Deploy-related (connection drops during restart)
# During deploy: old process stops, new process starts
# Brief moment where nothing is listening → 502

# Fix: graceful reload
kill -HUP $(cat /var/run/gunicorn.pid)  # Graceful reload (no downtime)
# Or use --graceful-timeout with gunicorn
# Or use a preload strategy


# CAUSE 4: Upstream socket file/port mismatch
# Nginx config points to wrong socket or port
# Usually constant 502, not intermittent

# Verify:
# nginx.conf: proxy_pass http://127.0.0.1:8000
# gunicorn actually running on: 127.0.0.1:8000  ← must match
```

## Diagnosis

```bash
# 1. Check Nginx error logs (they tell you WHY)
tail -f /var/log/nginx/error.log | grep 502

# Common messages:
# "upstream prematurely closed connection" → keep-alive race or app crash
# "connect() failed: Connection refused" → app not running on that port
# "no live upstreams" → all backends marked unhealthy
# "upstream timed out" → app too slow (this is 504, not 502)

# 2. Check if it correlates with deploys
grep "502" /var/log/nginx/access.log | awk '{print $4}' | sort | uniq -c
# Clustered around deploy times? → deploy-related
# Spread evenly? → keep-alive race or worker exhaustion

# 3. Check worker status
# If using gunicorn, check how many workers are busy:
ps aux | grep gunicorn | wc -l
```

## The Fix (Summary)

```nginx
# In nginx.conf:
upstream backend {
    server 127.0.0.1:8000;
    keepalive 32;                  # Keep persistent connections
}

location / {
    proxy_pass http://backend;
    proxy_http_version 1.1;        # Required for keepalive
    proxy_set_header Connection "";  # Required for keepalive

    proxy_connect_timeout 5s;
    proxy_read_timeout 60s;
    proxy_send_timeout 60s;

    proxy_next_upstream error timeout http_502;  # Retry on 502
    proxy_next_upstream_tries 2;                  # Try 2 backends
}
```

```bash
# In gunicorn:
gunicorn app:app \
    --workers 4 \
    --keep-alive 75 \      # Higher than Nginx's upstream keepalive
    --timeout 60 \
    --graceful-timeout 30
```'''
    ),
    (
        "thinking/abstraction-feature-flags-to-configuration",
        "We have feature flags scattered throughout our codebase with if/else blocks everywhere. It's getting hard to manage. How should I organize this?",
        r'''<think>
Scattered feature flags — let me ladder from concrete cleanup to a proper configuration management pattern.

**Concrete: if/else scattered everywhere**
```python
if os.environ.get('ENABLE_NEW_CHECKOUT') == 'true':
    new_checkout()
else:
    old_checkout()
```
Repeated 50 times across the codebase with different env vars.

**Pattern: centralized feature flag service**
Single source of truth for all flags. Clean API. Type-safe access.

**Principle: feature flags as a configuration system**
Feature flags are just runtime configuration. They should be:
- Centralized (one place to see all flags)
- Typed (boolean, percentage, user-targeted)
- Observable (which flags are on, for whom)
- Cleanable (remove old flags, don't accumulate)

**Policy: feature flag lifecycle management**
Flags have a lifecycle: created → tested → rolled out → permanent OR removed.
</think>

Scattered feature flags become technical debt fast. Let me build from cleanup to a proper system.

## Level 1: Concrete — Clean Up the Mess

```python
# ❌ SCATTERED: flags checked via env vars everywhere
# In checkout.py:
if os.environ.get('NEW_CHECKOUT') == 'true':
    ...
# In payment.py:
if os.environ.get('ENABLE_STRIPE_V2') == '1':
    ...
# In email.py:
if os.getenv('USE_SENDGRID', 'false').lower() == 'true':
    ...
# Different patterns, different env var names, different boolean parsing

# ✅ CENTRALIZED: one module for all flags
# feature_flags.py
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class FeatureFlags:
    new_checkout: bool = False
    stripe_v2: bool = False
    sendgrid_email: bool = False
    dark_mode: bool = False
    ai_recommendations: bool = False

    @classmethod
    def from_env(cls):
        return cls(
            new_checkout=os.getenv('FF_NEW_CHECKOUT', '').lower() == 'true',
            stripe_v2=os.getenv('FF_STRIPE_V2', '').lower() == 'true',
            sendgrid_email=os.getenv('FF_SENDGRID', '').lower() == 'true',
            dark_mode=os.getenv('FF_DARK_MODE', '').lower() == 'true',
            ai_recommendations=os.getenv('FF_AI_RECS', '').lower() == 'true',
        )

# Initialize once at startup
flags = FeatureFlags.from_env()

# Usage: clean, typed, IDE-autocomplete
# checkout.py
from feature_flags import flags

if flags.new_checkout:
    new_checkout_flow(order)
else:
    old_checkout_flow(order)
```

## Level 2: Pattern — Feature Flag Service

```python
# Support different flag types: boolean, percentage rollout, user-targeted

class FeatureFlagService:
    def __init__(self):
        self._flags = {}

    def register(self, name: str, default=False, rollout_pct=None, allowed_users=None):
        self._flags[name] = {
            'default': default,
            'rollout_pct': rollout_pct,
            'allowed_users': allowed_users or set(),
        }

    def is_enabled(self, name: str, user_id: str = None) -> bool:
        flag = self._flags.get(name)
        if not flag:
            return False

        # Check user-specific targeting
        if user_id and user_id in flag['allowed_users']:
            return True

        # Check percentage rollout
        if flag['rollout_pct'] is not None and user_id:
            return (hash(f"{name}:{user_id}") % 100) < flag['rollout_pct']

        return flag['default']

    @property
    def all_flags(self):
        return {name: flag['default'] for name, flag in self._flags.items()}


# Configuration
ff = FeatureFlagService()
ff.register('new_checkout', default=True)                    # On for everyone
ff.register('ai_recommendations', rollout_pct=10)            # 10% of users
ff.register('beta_dashboard', allowed_users={'user-42'})     # Specific users
ff.register('dark_mode', default=False)                       # Off for now

# Usage
if ff.is_enabled('new_checkout'):
    new_checkout(order)

if ff.is_enabled('ai_recommendations', user_id=current_user.id):
    show_recommendations()
```

## Level 3: Principle — Flag Lifecycle Management

```
FEATURE FLAGS HAVE A LIFECYCLE:

  CREATED     → flag added to codebase, default OFF
  TESTING     → enabled for specific users (QA, beta testers)
  ROLLING OUT → enabled for 5% → 25% → 50% → 100% of users
  PERMANENT   → flag is on for everyone, remove the flag + old code path
  OR
  REMOVED     → feature abandoned, remove the flag + new code path

THE CRITICAL STEP: CLEANUP
  Flags accumulate if you don't clean them up.
  Every flag adds an if/else branch = two code paths to maintain.
  100 flags = 100 if/else branches = 200 code paths = unmaintainable

  RULE: when a flag reaches 100% rollout and you're confident,
  REMOVE the flag and the old code path within 2 weeks.
```

```python
# Track flag age — flags older than 30 days at 100% should be cleaned up
import logging
from datetime import datetime

FLAG_METADATA = {
    'new_checkout': {
        'created': '2024-01-15',
        'status': 'rolling_out',
        'owner': 'checkout-team',
        'cleanup_by': '2024-04-15',
    },
    'old_search': {
        'created': '2023-06-01',
        'status': 'permanent',  # This should have been cleaned up months ago!
        'owner': 'search-team',
    },
}

# In CI: warn about stale flags
for name, meta in FLAG_METADATA.items():
    if meta.get('cleanup_by') and datetime.now() > datetime.fromisoformat(meta['cleanup_by']):
        logging.warning(f"Feature flag '{name}' is past its cleanup date! Owner: {meta['owner']}")
```

The ladder: scattered env var checks → centralized flag module → typed flag service with rollout support → lifecycle management with cleanup tracking.'''
    ),
    (
        "thinking/analogy-event-driven-architecture-dominoes",
        "What is event-driven architecture? How is it different from normal request/response?",
        r'''<think>
Event-driven architecture — the domino chain analogy works well.

**Request/response (normal):**
You ask someone to do something and WAIT for the answer.
Like calling a restaurant to ask if they have a table, waiting on hold until they check, then deciding based on the answer.

**Event-driven:**
Something HAPPENS → interested parties REACT.
Like dominos falling — one event triggers a chain of reactions.
Nobody is waiting on hold. Things happen in response to events.

Real-world analogy:
- Request/response: "Hey warehouse, do we have this item in stock?" (wait for answer)
- Event-driven: item sold → warehouse automatically gets notified → warehouse checks stock → if low, purchasing department automatically gets notified → purchasing automatically orders more
</think>

Think of it as the difference between **making phone calls** (request/response) and **setting up dominos** (event-driven).

## The Analogy

```
REQUEST/RESPONSE (phone calls):
  You're a store manager. Customer buys an item.
  → Call warehouse: "Reduce inventory by 1" (wait...)
  → Warehouse: "Done"
  → Call shipping: "Ship item to customer" (wait...)
  → Shipping: "Label created"
  → Call accounting: "Record this sale" (wait...)
  → Accounting: "Recorded"
  → Call email service: "Send confirmation" (wait...)
  → Email: "Sent"

  You made 4 phone calls, waited for 4 responses.
  If accounting's phone is busy → you're stuck waiting.

EVENT-DRIVEN (dominos):
  Customer buys an item.
  You announce: "ORDER PLACED!" (and walk away)
  → Warehouse hears it → reduces inventory (on their own time)
  → Shipping hears it → creates shipping label
  → Accounting hears it → records the sale
  → Email service hears it → sends confirmation

  You made ONE announcement.
  You didn't wait for anyone.
  If accounting is slow → everyone else still proceeds.
  You don't even know (or care) who's listening.
```

## In Code

```python
# REQUEST/RESPONSE: you call each service and wait
class OrderService:
    def place_order(self, order):
        self.save_order(order)

        # Call each service sequentially, wait for each response
        self.inventory_service.reduce_stock(order.items)     # Wait...
        self.shipping_service.create_shipment(order)         # Wait...
        self.accounting_service.record_sale(order)           # Wait...
        self.email_service.send_confirmation(order)          # Wait...
        self.analytics_service.track_purchase(order)         # Wait...
        # If email service is down → whole checkout fails
        # Adding a new service → modify this function

        return order

# EVENT-DRIVEN: you announce what happened, others react
class OrderService:
    def place_order(self, order):
        self.save_order(order)

        # Publish one event — done
        self.event_bus.publish("order.placed", {
            "order_id": order.id,
            "items": order.items,
            "user_email": order.user_email,
        })
        # Don't know who's listening. Don't care. Don't wait.

        return order

# Each service subscribes independently:
event_bus.subscribe("order.placed", inventory_service.on_order_placed)
event_bus.subscribe("order.placed", shipping_service.on_order_placed)
event_bus.subscribe("order.placed", email_service.on_order_placed)
# Adding analytics → just subscribe. OrderService never changes:
event_bus.subscribe("order.placed", analytics_service.on_order_placed)
```

## When to Use Each

```
REQUEST/RESPONSE:
  ✓ You NEED the answer to continue
    "Is this coupon valid?" → must know before calculating total
    "Does this user exist?" → must verify before proceeding
  ✓ The operation must complete before responding to the user
    "Charge the credit card" → user needs to know if it worked

EVENT-DRIVEN:
  ✓ Multiple services need to react to the same thing
    "Order placed" → 5 services need to know
  ✓ You DON'T need to wait for the downstream work
    "Send confirmation email" → user doesn't wait for email delivery
  ✓ Services should be independent
    "Email service is down" → shouldn't prevent placing orders
  ✓ You want to add new reactions without modifying existing code

MOST REAL SYSTEMS USE BOTH:
  Checkout:
    SYNC: validate cart → check inventory → charge payment (user waits)
    ASYNC EVENT: "order.placed" → email, shipping, analytics (user doesn't wait)
```

## The Key Properties

```
REQUEST/RESPONSE:        EVENT-DRIVEN:
  Tight coupling           Loose coupling
  Synchronous             Asynchronous
  Easy to understand       Harder to trace flow
  Caller knows callee      Publisher doesn't know subscribers
  Failure cascades         Failures are isolated
  Simple debugging          Distributed debugging
```

Event-driven architecture is powerful but adds complexity. Use it where its benefits (decoupling, scalability, resilience) outweigh its costs (complexity, eventual consistency, debugging difficulty).'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
