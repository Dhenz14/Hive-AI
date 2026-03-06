"""Phase 3F: Metacognition — Code Quality Judgment (Part 6)

Scenario 9: Rate overall code review: approve, request changes, or block.
Scenario 10: Rate technical design doc quality.
"""

PAIRS = [
    (
        "thinking/meta-quality-code-review-approve",
        r'''Code review: Should I approve, request changes, or block this PR?

The PR adds a retry mechanism to our HTTP client:

```python
import time
import random
from functools import wraps

class RetryConfig:
    def __init__(self, max_retries=3, base_delay=1.0, max_delay=30.0,
                 retryable_status_codes=(429, 500, 502, 503, 504)):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retryable_status_codes = set(retryable_status_codes)

def with_retry(config: RetryConfig = RetryConfig()):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(config.max_retries + 1):
                try:
                    response = func(*args, **kwargs)
                    if response.status_code not in config.retryable_status_codes:
                        return response
                    if attempt == config.max_retries:
                        return response
                except ConnectionError as e:
                    last_exception = e
                    if attempt == config.max_retries:
                        raise

                delay = min(config.base_delay * (2 ** attempt), config.max_delay)
                jitter = random.uniform(0, delay * 0.25)
                time.sleep(delay + jitter)

            raise last_exception
        return wrapper
    return decorator
```

Tests pass, includes unit tests with mocked time.sleep.''',
        r'''<think>
Let me do a comprehensive review:

**Correctness:**
- Exponential backoff with jitter ✓
- Max delay cap ✓
- Retryable status codes configurable ✓
- ConnectionError handling ✓
- Last attempt returns response even if status is retryable ✓
- `@wraps` preserves function metadata ✓

**Potential issues:**
- Default mutable argument: `config: RetryConfig = RetryConfig()` — this creates one shared default instance, but since RetryConfig is immutable (no methods that modify it), this is fine.
- `last_exception` could be None if the first call returns a retryable status code and all retries do too — but in that case the function returns the response, not raises. Actually wait: the loop returns response on last attempt, so `raise last_exception` is only reached if a ConnectionError happened on a non-last attempt... let me trace: if all attempts get ConnectionError, last attempt raises in the except block. If some get ConnectionError and the last returns a response, it returns. The `raise last_exception` after the loop is dead code unless there's a logic error. Actually no — if the for loop completes normally (no break/return), it falls through to `raise last_exception`. This can happen if...let me think...no, every iteration either returns or raises on the last attempt. The for loop always exits via return or raise, never falls through. The `raise last_exception` is dead code. Not a bug but slightly misleading.

**Security:** No issues. Status codes are integers, no injection vectors.

**Performance:** `time.sleep` blocks. Acknowledged in async codebases this should use `asyncio.sleep`. But for sync HTTP clients, this is correct.

**API design:** Clean decorator pattern with configurable RetryConfig. Easy to use:
```python
@with_retry(RetryConfig(max_retries=5))
def call_api(): ...
```

**Testing:** Tests pass with mocked time.sleep. Good.

Verdict: Approve with minor comments. The dead code after the loop is a nit, not a blocker.
</think>

**Verdict: APPROVE** (with one minor comment)

**What's good:**
- ✅ Exponential backoff with jitter (prevents thundering herd)
- ✅ Max delay cap (prevents absurd wait times)
- ✅ Configurable retryable status codes
- ✅ ConnectionError handling (network failures)
- ✅ `@wraps` preserves function metadata
- ✅ Last attempt returns response regardless (no infinite retry)
- ✅ Clean decorator API with sensible defaults
- ✅ Tests with mocked time.sleep

**One minor comment (not blocking):**
```python
# The `raise last_exception` after the for loop appears to be dead code.
# Every loop iteration either returns a response or raises on the final attempt.
# Consider removing it or adding a comment explaining when it's reached.
```

**Optional suggestions for a follow-up PR:**
- Add logging: `logger.warning(f"Retry {attempt}/{config.max_retries} after {response.status_code}")"`
- Add async version for `asyncio`/`httpx` users
- Add `Retry-After` header support for 429 responses

**Why approve and not request changes:**
The code is correct, well-structured, tested, and solves a real problem. The dead code is a nit that doesn't affect behavior. Blocking good PRs for nits slows the team down.'''
    ),
    (
        "thinking/meta-quality-code-review-request-changes",
        r'''Code review: Should I approve, request changes, or block this PR?

The PR adds an admin endpoint to delete users:

```python
@app.route('/api/admin/users/<user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    user = db.query(User).get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404

    # Delete user and all related data
    db.query(Order).filter_by(user_id=user_id).delete()
    db.query(Comment).filter_by(user_id=user_id).delete()
    db.query(Session).filter_by(user_id=user_id).delete()
    db.delete(user)
    db.commit()

    return jsonify({"deleted": True})
```

Tests verify that the user is deleted and related data is cleaned up.''',
        r'''<think>
Let me review:

**Critical issues:**
1. **No admin authorization check.** `@login_required` verifies the user is logged in, but ANY logged-in user can delete ANY other user. There's no check for admin role/permission. MUST FIX.

2. **No soft delete.** Hard-deleting a user and all their orders/comments is destructive and irreversible. If done accidentally, there's no way to recover. Orders especially should be preserved for legal/financial records. SHOULD FIX.

3. **No confirmation or audit trail.** Deleting all of a user's data with a single API call and no logging/auditing is dangerous. No record of who deleted whom or when. SHOULD FIX.

**Medium issues:**
4. **Cascade delete is manual.** Manually querying and deleting Orders, Comments, Sessions is fragile — if a new related table is added, this code won't know to clean it up. Should use ON DELETE CASCADE or a centralized deletion service.

5. **No transaction safety.** If the delete of Comments succeeds but the delete of the User fails, you've orphaned the comment deletions. Should be wrapped in a transaction (the `db.commit()` at the end helps, but if any intermediate query fails, the state is inconsistent until rollback).

**Minor issues:**
6. **No rate limiting.** An attacker (or bug) could call this in a loop and delete all users.

Verdict: REQUEST CHANGES. The missing authorization is critical. The hard delete is a design concern.
</think>

**Verdict: REQUEST CHANGES** — Critical authorization missing.

**Must fix (blocking):**

**1. No admin authorization check:**
```python
@app.route('/api/admin/users/<user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    # BUG: Any logged-in user can delete any other user!
    # Missing: if not current_user.is_admin: return 403
```
`@login_required` ≠ `@admin_required`. This is an authorization vulnerability.

**Should fix (strong recommendation):**

**2. Use soft delete instead of hard delete:**
```python
# Don't destroy data — mark as deleted
user.deleted_at = datetime.utcnow()
user.email = f"deleted_{user.id}@deleted.local"
# Keep orders for financial records (may be legally required)
```

**3. Add audit logging:**
```python
logger.info(f"User {user_id} deleted by admin {current_user.id}")
AuditLog.create(action="user_deleted", target_id=user_id, admin_id=current_user.id)
```

**4. Fragile cascade — use database constraints:**
```python
# Instead of manual deletion of each table,
# configure ON DELETE CASCADE or use a dedicated service
```

**Why request changes, not block:**
The feature works correctly for its intended use. But the authorization bug makes it dangerous to merge — any user could delete any other user. That must be fixed before merging.'''
    ),
    (
        "thinking/meta-quality-code-review-block",
        r'''Code review: Should I approve, request changes, or block this PR?

The PR "improves" our authentication by storing passwords differently:

```python
import base64

def hash_password(password: str) -> str:
    """Encode password for storage."""
    return base64.b64encode(password.encode()).decode()

def verify_password(password: str, stored: str) -> bool:
    """Check if password matches stored hash."""
    return base64.b64encode(password.encode()).decode() == stored

# Migration to update existing bcrypt hashes:
def migrate_passwords():
    for user in db.query(User).all():
        # Decode old bcrypt hash and re-encode with base64
        # (Can't decode bcrypt, so reset all passwords to "changeme")
        user.password_hash = hash_password("changeme")
    db.commit()
```

PR description says: "Simplified our auth. Bcrypt was slow and causing login timeouts."''',
        r'''<think>
This is catastrophically bad. Let me enumerate:

1. **Base64 is NOT hashing — it's encoding.** Base64 is reversible. Anyone who reads the database can decode every password instantly: `base64.b64decode(stored).decode()`. This eliminates ALL password security.

2. **The migration resets ALL user passwords to "changeme".** Every single user account is now accessible with the password "changeme". This is a complete security breach.

3. **The bcrypt "slowness" is a FEATURE, not a bug.** Bcrypt is intentionally slow to prevent brute-force attacks. If logins are timing out, the solution is to reduce the work factor, not to remove hashing entirely.

4. **Compliance violations.** Storing passwords in a reversible encoding (base64) likely violates GDPR, PCI-DSS, SOC2, and other regulations.

This PR must be BLOCKED immediately. It's not a matter of "request changes" — the entire approach is wrong and dangerous.

Verdict: BLOCK. Do not merge under any circumstances.
</think>

**Verdict: BLOCK — Do not merge. This is a critical security regression.**

**This PR eliminates all password security:**

| Issue | Severity | Impact |
|-------|----------|--------|
| Base64 is reversible encoding, not hashing | **Critical** | Anyone with DB access can read all passwords |
| Migration resets all passwords to "changeme" | **Critical** | Every account is compromised |
| Removes bcrypt (intentionally slow) | **Critical** | Enables brute-force attacks |
| Likely compliance violation | **High** | GDPR, PCI-DSS, SOC2 violations |

**Base64 is NOT a hash:**
```python
import base64
stored = base64.b64encode(b"hunter2").decode()  # "aHVudGVyMg=="
password = base64.b64decode(stored).decode()     # "hunter2" ← trivially reversible
```

**The "bcrypt is slow" complaint:**
Bcrypt is intentionally slow — that's its security property. If logins are timing out:
```python
# Don't do this:
hash_password = base64.b64encode  # WRONG

# Do this — reduce bcrypt work factor:
bcrypt.hashpw(password, bcrypt.gensalt(rounds=10))  # Instead of rounds=12
# Or move hashing to a background worker
# Or use argon2id with tuned parameters
```

**The migration is a data breach:**
Resetting every user's password to "changeme" means every account is accessible to anyone who knows (or guesses) this fact.

**Action items:**
1. Close this PR immediately
2. Do NOT deploy to any environment
3. If already deployed, roll back and force password resets
4. Investigate the login timeout — likely a configuration issue, not a bcrypt problem
5. Schedule a security training session for the team'''
    ),
    (
        "thinking/meta-quality-design-doc-incomplete",
        r'''Rate this technical design doc (1-10):

## Design Doc: Add Caching Layer

### Problem
Our API is slow.

### Solution
Add Redis caching to all endpoints.

### Implementation
1. Install Redis
2. Add caching decorators to endpoints
3. Set TTL to 5 minutes

### Timeline
1 week''',
        r'''<think>
Let me evaluate this design doc:

**Problem statement:** 1/5 — "Our API is slow" tells us nothing. Which endpoints? How slow? What's the SLA? Is the bottleneck database queries, computation, external APIs? No data, no metrics, no user impact.

**Proposed solution:** 1/5 — "Add Redis caching to all endpoints" is vague and potentially wrong. Caching everything with the same TTL is rarely correct. POST/PUT/DELETE endpoints shouldn't be cached. Some data is user-specific and can't be shared across requests.

**Alternatives considered:** 0/5 — No alternatives mentioned. Could database query optimization solve the problem? Could we add database indexes? Is the issue actually in the network layer? No discussion.

**Technical detail:** 1/5 — "Add caching decorators" with no detail on cache invalidation, cache keys, cache warming, or handling stale data. Cache invalidation is the hard part and it's not mentioned.

**Risks and tradeoffs:** 0/5 — No mention of stale data, cache stampede, increased complexity, Redis availability as a new dependency, memory usage.

**Metrics/success criteria:** 0/5 — No definition of what "fast enough" means. No before/after benchmarks planned.

Score: 2/10. This is a sketch, not a design doc.
</think>

**Design doc quality: 2/10 — This is a rough sketch, not a design doc.**

**Missing sections:**
| Section | Status | Issue |
|---------|--------|-------|
| Problem statement | Vague | "API is slow" — which endpoints? How slow? |
| Current metrics | Missing | No latency data, no bottleneck analysis |
| Root cause analysis | Missing | Why is it slow? DB? Computation? Network? |
| Proposed solution | Vague | "Cache everything" with no detail |
| Cache invalidation | Missing | The hardest part, not mentioned at all |
| Alternatives considered | Missing | Indexes? Query optimization? CDN? |
| Risks and tradeoffs | Missing | Stale data, complexity, Redis dependency |
| Success criteria | Missing | What does "fast enough" mean? |
| Rollback plan | Missing | What if Redis goes down? |

**What a good design doc looks like:**
```markdown
## Problem
The /api/products endpoint has p99 latency of 2.3s (SLA: 500ms).
Root cause: each request runs 5 SQL queries averaging 400ms total.
Impact: 15% of users see timeout errors during peak hours.

## Proposed Solution
Cache the product catalog query in Redis with a 60s TTL.
Only cache GET /api/products (read-heavy, changes infrequently).

## Alternatives Considered
1. **Database indexes** — Already optimized. Main query does a full table scan
   that can't be further indexed without schema changes.
2. **Materialized view** — Would work but adds complexity. Prefer Redis for
   simpler operational model.
3. **CDN caching** — Not suitable, responses vary by user's region.

## Cache Invalidation Strategy
- TTL-based: 60s for product listings
- Event-based: Invalidate on product create/update/delete
- Cache key: `products:{category}:{page}:{sort}`

## Risks
- Stale data for up to 60s after product updates
- Redis as new infrastructure dependency
- Cache stampede on TTL expiry (mitigate with lock-based rebuild)

## Success Criteria
- p99 latency < 500ms (currently 2.3s)
- Cache hit rate > 90% within first week
```'''
    ),
    (
        "thinking/meta-quality-design-doc-good",
        r'''Rate this technical design doc (1-10):

## Design Doc: Migrate from REST to Event-Driven Order Processing

### Author: @alice | Reviewers: @bob, @carol | Status: Draft

### Problem
Our synchronous order processing pipeline fails under load:
- POST /api/orders takes 4.2s average (payment + inventory + email in sequence)
- Under Black Friday load (10x normal), 23% of orders time out at 30s
- Failed orders require manual intervention ($12K lost revenue last year)

### Current Architecture
```
Client → API → [validate → charge_stripe → update_inventory → send_email] → Response
```
All steps are synchronous. If Stripe is slow (p99: 3s), the entire request is slow.

### Proposed Solution
Decouple payment, inventory, and email into async event-driven steps:
```
Client → API → [validate → publish OrderCreated event] → Response (< 200ms)
                         ↓
              OrderCreated event → [charge_stripe → publish OrderPaid]
              OrderPaid event → [update_inventory]
              OrderPaid event → [send_email]
```

### Alternatives Considered
1. **Increase timeout to 60s** — Masks the problem. Users still wait.
2. **Background Celery tasks** — Simpler but no guaranteed delivery. Lost tasks = lost orders.
3. **Event sourcing** — Overkill for our scale. We don't need full event replay.

Chose event-driven with SQS because: guaranteed delivery, dead-letter queue for failures, decoupled scaling.

### Technical Design

**Event schema:**
```json
{"event": "OrderCreated", "order_id": 123, "user_id": 456, "items": [...], "total": 99.50, "idempotency_key": "uuid"}
```

**Idempotency:** Each consumer checks `processed_events` table before processing. Duplicate events are safely ignored.

**Failure handling:**
- Consumer fails → message returns to queue (SQS visibility timeout)
- 3 failures → message moves to dead-letter queue
- DLQ alarm → on-call investigates within 1 hour

**Rollback on payment failure:**
- OrderPaid event not published → inventory not deducted, email not sent
- Stripe charge fails → publish OrderFailed event → notify user

### Risks
| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Event ordering | Medium | Idempotency keys, no ordering dependency between inventory and email |
| SQS outage | Low | Multi-AZ SQS, fallback to sync processing |
| Debugging complexity | High | Structured logging with correlation_id across all events |
| Data consistency | Medium | Eventual consistency acceptable for email; inventory uses optimistic locking |

### Migration Plan
1. Week 1: Deploy event infrastructure (SQS queues, consumers)
2. Week 2: Dual-write (sync + async) with feature flag, compare results
3. Week 3: Switch to async-only for 10% of traffic
4. Week 4: Full rollout

### Success Criteria
- POST /api/orders p99 < 500ms (currently 4.2s average)
- Order completion rate > 99.5% (currently 77% under load)
- Zero lost orders (DLQ processing within 1 hour)
- No increase in customer support tickets

### Monitoring
- Dashboard: Order event flow (created → paid → fulfilled)
- Alert: DLQ depth > 0 for > 15 minutes
- Alert: Order completion rate < 95% over 5 minutes''',
        r'''<think>
Let me evaluate:

**Problem statement:** 5/5 — Specific metrics (4.2s latency, 23% timeout, $12K revenue loss). Clear impact on the business.

**Current state:** 5/5 — Architecture diagram showing the synchronous bottleneck. Easy to understand the problem.

**Proposed solution:** 5/5 — Clear before/after architecture. Event schema defined. Shows how the response time drops to < 200ms by decoupling.

**Alternatives considered:** 5/5 — Three alternatives with clear reasoning for rejection. Not just "we chose X" but "we chose X because Y doesn't work for Z reason."

**Technical detail:** 5/5 — Event schema, idempotency handling, failure/retry strategy, rollback behavior. The hard questions are addressed.

**Risks:** 5/5 — Tabular format with likelihood and mitigation for each risk. Acknowledges debugging complexity honestly.

**Migration plan:** 5/5 — Phased rollout with dual-write and percentage-based traffic shifting. Not a big-bang migration.

**Success criteria:** 5/5 — Specific, measurable metrics. Latency, completion rate, zero lost orders.

**Monitoring:** 4/5 — Good alerts and dashboard. Could include rollback criteria (at what failure rate do we revert?)

Score: 9/10. This is an excellent design doc that addresses all the important questions.
</think>

**Design doc quality: 9/10 — Excellent.**

| Section | Score | Notes |
|---------|-------|-------|
| Problem statement | 5/5 | Specific metrics, business impact, revenue numbers |
| Current architecture | 5/5 | Clear diagram showing the bottleneck |
| Proposed solution | 5/5 | Before/after architecture, event schema |
| Alternatives | 5/5 | Three alternatives with clear rejection reasoning |
| Technical detail | 5/5 | Idempotency, failure handling, rollback |
| Risks | 5/5 | Tabular with likelihood and mitigation |
| Migration plan | 5/5 | Phased rollout, not big-bang |
| Success criteria | 5/5 | Measurable targets for latency, reliability |
| Monitoring | 4/5 | Good alerts, could add rollback criteria |

**What makes this excellent:**
1. **Data-driven**: Every claim has a number ($12K, 23% timeout, 4.2s)
2. **Honest about risks**: Debugging complexity rated "High" — not hidden
3. **Phased migration**: Dual-write → 10% → full rollout (safe, reversible)
4. **Failure handling detailed**: DLQ, idempotency, rollback on payment failure
5. **Success is measurable**: Clear before/after metrics to validate the change

**Only missing (-1 point):**
- Rollback criteria: "If order completion < X% after full rollout, revert to sync within Y hours"
- Cost estimate: SQS, additional compute for consumers
- Load testing plan before production rollout'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
