"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 6/8)"""

PAIRS = [
    (
        "thinking/multiperspective-documentation-strategy",
        "Our team argues about documentation constantly. Some want detailed docs for everything, others say 'the code is the documentation.' We have a 200K-line Python codebase with poor documentation. What's the right approach?",
        r'''<think>
Documentation strategy — this is a perennial debate. Let me analyze from multiple perspectives.

**The "code is documentation" perspective:**
Valid points:
- Good code with clear naming IS self-documenting for WHAT it does
- Doc comments that restate the code are worse than useless (they go stale)
- Tests ARE executable documentation for behavior
- Time spent writing docs could be spent improving code clarity

Invalid assumptions:
- Code explains WHAT, not WHY
- Code doesn't explain architectural decisions
- Code doesn't explain what was tried and rejected
- New developers can't read 200K lines to understand the system

**The "document everything" perspective:**
Valid points:
- New developers need onboarding material
- Architecture decisions need to be recorded before people leave
- API consumers need contract documentation
- Compliance may require documentation

Invalid assumptions:
- More documentation ≠ better documentation
- Documentation maintenance is free (it's not — stale docs are harmful)
- Everyone reads documentation (they usually search for specific answers)

**The product manager perspective:**
Documentation is a product. Like any product:
- Who is the audience? (new dev, API consumer, future maintainer?)
- What problem does it solve? (onboarding, API integration, troubleshooting?)
- What's the minimum viable documentation?

**The economics perspective:**
Documentation has a cost-benefit ratio:
- Writing cost: developer time
- Maintenance cost: keeping it updated
- Benefit: time saved by readers
- ROI = (readers × time_saved) / (writing_time + maintenance_time)

High ROI: API docs (many readers, high value)
Low ROI: internal function docstrings (few readers, code is clearer)

**The pragmatic synthesis:**
Document at the boundaries: the edges where knowledge transfer happens.
Don't document internals that only the author touches.
</think>

Both extremes are wrong. The right answer: **document at the boundaries** — where knowledge transfers between people, teams, or systems.

## The Documentation Pyramid

```
                    ╱╲
                   ╱ADR╲          Architecture Decision Records
                  ╱──────╲        (WHY we chose X over Y)
                 ╱ README ╲       System-level overview
                ╱──────────╲      (HOW things fit together)
               ╱  API Docs  ╲     Public interface contracts
              ╱──────────────╲    (WHAT the API accepts/returns)
             ╱   Code + Tests ╲   The code itself + test cases
            ╱──────────────────╲  (WHAT the code does — self-evident)

  Top: High value, rarely changes, few documents
  Bottom: Low value to document, changes constantly, self-documenting
```

## What to Document (and What NOT to)

### YES: Architecture Decision Records (Highest ROI)

```markdown
# ADR-007: Use PostgreSQL over MongoDB for order data

## Status: Accepted (2024-03-15)

## Context
We need to store order data with complex relationships (orders → items →
products → categories). The team debated SQL vs NoSQL.

## Decision
PostgreSQL, because:
- Order data is highly relational (joins are essential)
- We need ACID transactions for payment processing
- Our team has strong SQL experience

## Consequences
- Must manage migrations carefully
- JSON fields available for semi-structured data (product metadata)
- Need connection pooling for high concurrency (use pgbouncer)

## Alternatives Considered
- MongoDB: rejected because order data is relational, and we'd end up
  denormalizing everything, leading to consistency issues
- DynamoDB: rejected because of vendor lock-in and complex querying
```

### YES: System README (How Things Fit Together)

```markdown
# Order Processing System

## Architecture
Browser → API Gateway → Order Service → PostgreSQL
                                      → Payment Service (Stripe)
                                      → Queue (Redis) → Email Worker
                                                      → Inventory Worker

## Key Design Decisions
- See ADR-007 for database choice
- See ADR-012 for async processing approach

## Local Development
make setup && make dev  # That's it.
```

### YES: API Documentation (Contract for Consumers)

```python
# Use your framework's built-in doc generation
from fastapi import FastAPI

@app.post("/orders", response_model=OrderResponse, status_code=201)
async def create_order(order: OrderCreate):
    """
    Create a new order.

    - Validates inventory availability
    - Charges payment via Stripe
    - Returns order with tracking number
    - Sends confirmation email asynchronously

    Raises:
        422: Invalid order data
        402: Payment declined
        409: Item out of stock
    """
```

### NO: Don't Document Obvious Code

```python
# ❌ USELESS: restates the code
def get_user_by_id(user_id: int) -> User:
    """Get a user by their ID.

    Args:
        user_id: The ID of the user.

    Returns:
        The user with the given ID.
    """
    return db.query(User).get(user_id)

# ✅ USEFUL: explains WHY, not WHAT
def get_user_by_id(user_id: int) -> User:
    """Fetches from read replica for performance.
    Falls back to primary if replica is behind (lag > 5s)."""
    return db.read_replica.query(User).get(user_id)
```

### NO: Don't Write Comprehensive Internal Docs

```python
# ❌ Nobody will maintain this:
# "The OrderProcessor class handles order processing. It first validates
#  the order, then checks inventory, then processes payment..."

# ✅ Instead: write clear code with good names
class OrderProcessor:
    async def process(self, order: Order) -> ProcessedOrder:
        self.validate(order)
        await self.check_inventory(order.items)
        payment = await self.charge_payment(order)
        return ProcessedOrder(order=order, payment=payment)
    # The code IS the documentation. Method names tell the story.
```

## Decision Matrix for Your Team

| Type | Write it? | Maintain it? | Format |
|------|-----------|-------------|--------|
| ADRs | Yes, always | No (they're historical records) | Markdown in repo |
| System README | Yes | Update when architecture changes | Markdown in repo |
| API docs | Yes | Auto-generated from code | OpenAPI/Swagger |
| Runbooks | Yes (on-call procedures) | Update after incidents | Wiki |
| Code comments | Only for WHY, never for WHAT | Delete when code changes | Inline |
| Function docstrings | Only for public APIs | With the code | Inline |

The rule: if it explains WHY or HOW THINGS CONNECT, document it. If it restates WHAT THE CODE DOES, don't.'''
    ),
    (
        "thinking/multiperspective-async-architecture",
        "We have a synchronous Django application that's hitting performance limits. Some requests take 10-30 seconds because they call multiple external APIs sequentially. Should we switch to async (like FastAPI) or keep Django and use background tasks?",
        r'''<think>
Async vs background tasks for slow API-calling Django app. Let me evaluate from multiple perspectives.

**The performance perspective:**
The problem: requests call multiple external APIs sequentially.
```
Request → API A (3s) → API B (2s) → API C (5s) → Response (10s)
```
Two solutions:
1. Async: call APIs concurrently
```
Request → [API A (3s) + API B (2s) + API C (5s) in parallel] → Response (5s)
```
2. Background tasks: return immediately, process later
```
Request → Queue job → Response (200ms) → Worker processes APIs
```

These solve DIFFERENT problems:
- If the user NEEDS the result: async (concurrent API calls)
- If the user CAN wait for email/notification: background task

**The migration perspective:**
Switching from Django to FastAPI:
- Rewrite all views, middleware, auth, ORM usage
- Lose Django admin, ecosystem, battle-tested security
- Async Python has different debugging patterns
- Training team on async/await concepts
- 3-6 month migration for a large app

Using background tasks with existing Django:
- Add Celery + Redis (1-2 days setup)
- Move slow API calls to tasks
- No rewrite needed
- Team already knows Django

**The team capability perspective:**
Async Python has gotchas:
- Can't use synchronous database drivers (Django ORM is sync)
- async_to_sync / sync_to_async wrappers are confusing
- Debugging async code is harder
- One blocking call in an async handler blocks the entire event loop

**The Django 4.1+ perspective:**
Django now has async support:
- Async views, middleware, ORM queries (gradually)
- You can use async views in Django WITHOUT switching frameworks
- Still not 100% async (ORM uses sync_to_async internally)

**My recommendation:**
Don't rewrite to FastAPI. Use a combination:
1. Background tasks (Celery) for things that don't need immediate response
2. Django async views for things that need concurrent API calls
3. Keep the rest of Django synchronous (it's fine)
</think>

Don't rewrite to FastAPI. You can solve this without leaving Django, using **two complementary approaches** depending on whether the user needs the result immediately.

## Decision: Does the User Need the Result NOW?

```
User NEEDS the result immediately?
  YES → Use async Django views (concurrent API calls)
  NO  → Use Celery background tasks (return fast, process later)
```

## Approach 1: Background Tasks (User Can Wait)

Best for: email sending, report generation, data syncing, webhook processing

```python
# 1. Install: pip install celery redis
# 2. Configure: config/celery.py

import celery

app = celery.Celery('myapp', broker='redis://localhost:6379/0')

# 3. Move slow work to tasks
@app.task(bind=True, max_retries=3)
def sync_customer_data(self, customer_id):
    """Runs in background worker, not in request."""
    try:
        crm_data = crm_api.get_customer(customer_id)    # 3s
        billing = billing_api.get_account(customer_id)    # 2s
        analytics = analytics_api.get_usage(customer_id)  # 5s
        db.update_customer(customer_id, crm_data, billing, analytics)
    except APIError as e:
        self.retry(exc=e, countdown=60)

# 4. Call from view — return immediately
def update_customer(request, customer_id):
    sync_customer_data.delay(customer_id)  # Queued, returns instantly
    return JsonResponse({"status": "syncing", "message": "Data update in progress"})
```

**Setup time: 1-2 days.** No rewrite needed. Immediate win.

## Approach 2: Async Views (User Needs Result NOW)

Best for: aggregation endpoints, search across multiple sources, real-time dashboards

```python
# Django 4.1+ supports async views natively
import asyncio
import httpx

# Async view — calls APIs concurrently
async def get_dashboard(request, customer_id):
    async with httpx.AsyncClient() as client:
        # All three API calls run CONCURRENTLY
        crm_task = client.get(f"https://crm.api/customers/{customer_id}")
        billing_task = client.get(f"https://billing.api/accounts/{customer_id}")
        analytics_task = client.get(f"https://analytics.api/usage/{customer_id}")

        crm, billing, analytics = await asyncio.gather(
            crm_task, billing_task, analytics_task
        )

    return JsonResponse({
        "customer": crm.json(),
        "billing": billing.json(),
        "usage": analytics.json(),
    })
    # Total time: max(3s, 2s, 5s) = 5s instead of 10s

# urls.py — async views work like regular views
urlpatterns = [
    path("dashboard/<int:customer_id>/", get_dashboard),
]
```

**Important:** Run with an ASGI server for async views:
```bash
# Instead of: gunicorn myapp.wsgi
# Use: uvicorn myapp.asgi:application --workers 4
# Or: daphne myapp.asgi:application
```

## Why NOT Rewrite to FastAPI

| Factor | Rewrite to FastAPI | Stay with Django |
|--------|-------------------|-----------------|
| Time to fix perf issue | 3-6 months | 1-2 weeks |
| Risk | High (rewrite everything) | Low (additive changes) |
| Django admin | Lost | Kept |
| Auth/security | Rebuild from scratch | Already battle-tested |
| ORM | Need SQLAlchemy (different patterns) | Keep Django ORM |
| Team productivity | 2-3 months learning curve | Already productive |
| Async benefit | Full async | 90% of benefit, 10% of effort |

## The Combined Architecture

```
Django Application (mostly synchronous — that's fine)
│
├── Regular views (95% of endpoints)
│   └── Synchronous Django views, Django ORM
│   └── These are FAST already — no changes needed
│
├── Async views (5% — external API aggregation)
│   └── async def + httpx for concurrent API calls
│   └── User gets result in 5s instead of 15s
│
└── Celery tasks (background processing)
    └── Reports, syncing, emails, webhooks
    └── User gets instant response, work happens later
```

This gives you **90% of the performance benefit with 10% of the migration effort**. Rewrite to FastAPI only if you're starting a NEW service from scratch.'''
    ),
    (
        "thinking/multiperspective-incident-postmortem",
        "We had a major outage last week — 4 hours of downtime. Management wants a postmortem but the team is worried it'll turn into a blame session. How do we run an effective blameless postmortem?",
        r'''<think>
Blameless postmortem — let me think about this from multiple perspectives.

**The engineering team's perspective:**
They're worried about:
- Being personally blamed for the outage
- Punitive consequences (bad reviews, being fired)
- Having to justify their decisions under pressure
- The exercise being performative rather than useful

What they want:
- Acknowledgment that systems are complex and failures are inevitable
- Focus on systemic improvements, not individual mistakes
- A safe space to be honest about what happened

**Management's perspective:**
They want:
- Assurance this won't happen again
- Understanding of the business impact
- Action items and timelines
- To show customers/stakeholders they're taking action

What they might accidentally do:
- Ask "who did this?" (blame)
- Demand "make sure this NEVER happens again" (impossible)
- Skip the learning and jump to punishment

**The customer's perspective:**
They want:
- Transparent communication about what happened
- Confidence that the company is learning from it
- Specific steps being taken to prevent recurrence

**The SRE/reliability perspective:**
Postmortems are the #1 tool for improving reliability:
- Every outage is a learning opportunity
- Blame kills learning (people hide information if they fear punishment)
- The goal is to make the SYSTEM more resilient, not people more careful
- "More careful" is not a sustainable reliability strategy

**The organizational culture perspective:**
How you handle postmortems defines your engineering culture:
- Blame culture → people hide mistakes → learn nothing → repeat
- Blameless culture → people share openly → learn everything → improve

Google, Netflix, Etsy all practice blameless postmortems and have among the highest reliability in the industry.
</think>

Here's a complete blameless postmortem framework that protects the team while delivering what management needs.

## The Ground Rules (Establish Before the Meeting)

```markdown
## Postmortem Ground Rules

1. **We examine the SYSTEM, not the person.**
   Instead of: "Why did you push that change without testing?"
   Ask: "What about our deployment process allowed an untested change to reach production?"

2. **Assume everyone made the best decision with the information they had.**
   The person who deployed the change didn't intend to cause an outage.
   They had reasons. Understanding those reasons prevents recurrence.

3. **No punitive actions result from postmortem findings.**
   If people fear punishment, they'll hide information. Hidden information
   means we can't fix the real problems. We NEED honesty.

4. **"More careful" is not an action item.**
   Humans make mistakes. Systems should be designed to tolerate mistakes.
   Every action item must be a SYSTEMIC change.
```

## The Template

```markdown
# Postmortem: [Service Name] Outage — [Date]

## Summary
[One paragraph: what happened, how long, who was affected]

## Impact
- Duration: 4 hours (10:15 AM — 2:15 PM EST)
- Users affected: ~15,000 (all customers in US region)
- Revenue impact: ~$45,000 in lost transactions
- SLA impact: 99.5% monthly SLA → now at 98.7%

## Timeline (UTC)
| Time | Event |
|------|-------|
| 14:00 | Engineer A deploys config change to payment service |
| 14:05 | Error rate rises from 0.1% to 5% |
| 14:15 | Automated alert fires: "payment-service error rate > 2%" |
| 14:18 | On-call engineer B acknowledges alert, begins investigation |
| 14:30 | Engineer B identifies config change as likely cause |
| 14:35 | Rollback attempted — fails due to database migration |
| 14:45 | Incident escalated to senior engineer C |
| 15:30 | Root cause identified: config change exposed race condition |
| 16:00 | Fix deployed: race condition patched |
| 16:15 | Error rate returns to normal, monitoring confirms recovery |

## Root Cause
The config change reduced the payment processing timeout from 30s to 5s.
This exposed a pre-existing race condition in the payment retry logic that
had been dormant because retries previously completed within the 30s window.
With the 5s timeout, retries were cut off mid-processing, causing duplicate
charges and errors.

**The config change was not the root cause — the race condition was.**
The config change merely revealed it. This race condition would have been
triggered by any increase in payment processing latency.

## Contributing Factors
(Not "who to blame" — what systemic factors allowed this to happen)

1. **No config change review process** — config changes deployed without
   the same review as code changes
2. **Missing integration test** — no test covered concurrent payment
   retries with short timeouts
3. **Rollback coupled to migrations** — couldn't roll back code without
   rolling back the database
4. **Alert threshold too high** — 2% error rate threshold delayed detection
   by 10 minutes (should be 0.5%)

## What Went Well
- On-call engineer responded within 3 minutes of alert
- Incident communication to customers was clear and timely
- Team collaborated effectively during the incident

## Action Items
| Action | Owner | Priority | Due Date |
|--------|-------|----------|----------|
| Add config changes to PR review process | Team Lead | P1 | Next sprint |
| Write integration test for concurrent retries | Engineer D | P1 | Next sprint |
| Decouple code deploys from migrations | DevOps | P2 | This quarter |
| Lower error rate alert threshold to 0.5% | SRE | P1 | This week |
| Add payment idempotency keys to prevent duplicate charges | Engineer A | P1 | Next sprint |
```

## How to Facilitate the Meeting

**Duration:** 60-90 minutes max.

```
Minute 0-5:   Read ground rules aloud. Remind: blameless.
Minute 5-20:  Walk through the timeline together.
              Ask: "What did you see? What did you know at this point?"
              NOT: "Why did you do X?"
Minute 20-40: Identify contributing factors.
              For each factor, ask: "What systemic change would prevent this?"
              NOT: "Who should have caught this?"
Minute 40-55: Agree on action items with owners and deadlines.
              Each action item must be a PROCESS or SYSTEM change.
Minute 55-60: Review what went well. End on a positive note.
```

**Facilitator phrases:**

| Instead of... | Say... |
|--------------|--------|
| "Why did you push without testing?" | "What would have caught this before production?" |
| "Who approved this change?" | "What does our approval process look like for this type of change?" |
| "This should never happen again" | "How do we make the system resilient to this class of failure?" |
| "Be more careful next time" | "What guardrails can we add?" |

## The External Communication

```markdown
# Incident Report — [Date]

## What happened
On [date], our payment processing system experienced 4 hours of degraded
service. During this period, some customers experienced failed transactions.

## What we've done
- Identified and resolved the root cause (a race condition in payment retry logic)
- Compensated affected customers with [refunds/credits]
- Implemented 5 specific improvements to prevent recurrence (details below)

## Improvements made
1. Enhanced monitoring to detect issues 10x faster
2. Added automated testing for the failure scenario
3. Implemented payment idempotency to prevent duplicate charges
4. Added config change review process
5. Decoupled deployment from database changes for faster rollbacks

We take reliability seriously and are committed to learning from every incident.
```

The postmortem isn't about finding who to blame — it's about finding which systems to improve so that human error doesn't reach production.'''
    ),
    (
        "thinking/multiperspective-code-review-culture",
        "Code reviews are becoming a bottleneck. PRs sit for 2-3 days waiting for review. When reviews happen, they're either rubber stamps or nitpick fests about style. How do we fix our code review process?",
        r'''<think>
Code review bottleneck — let me analyze from multiple perspectives.

**The PR author's perspective:**
- Context-switches away from the PR while waiting 2-3 days
- By the time review comes, they've forgotten the details
- Nitpick reviews feel disrespectful ("I spent 2 days on this and you're arguing about variable names?")
- Discouraging to get 50 style comments and no architectural feedback

**The reviewer's perspective:**
- Already busy with their own work
- Reviewing is unrecognized work (doesn't show up in sprint metrics)
- Large PRs are daunting (500+ line diffs take hours to review properly)
- Easier to comment on style than think deeply about correctness
- Rubber stamping happens because deep review is exhausting

**The team lead's perspective:**
- Reviews are critical for code quality and knowledge sharing
- But slow reviews slow delivery
- Hard to enforce review quality without micromanaging
- Want reviews to catch bugs, not debate preferences

**The organizational perspective:**
- Review bottleneck = delivery bottleneck
- 2-3 day review wait on a 2-week sprint = 15-20% of sprint capacity lost to waiting
- Knowledge silos form when only one person can review certain code

**Root causes:**
1. PRs are too large (hard to review deeply)
2. No response time expectation
3. Style debates aren't automated
4. Deep review isn't valued/rewarded
5. No review guidelines (what to look for)

**Solutions:**
1. Small PRs (easier to review = faster review)
2. SLA on review response time
3. Automate style (linters, formatters)
4. Review guidelines (what matters, what doesn't)
5. Rotate reviewers (spread knowledge)
</think>

The fix is a combination of smaller PRs, automated style enforcement, and clear review guidelines. Here's the complete system:

## Fix 1: Kill Style Debates (Day 1)

Automate everything subjective. If a linter or formatter can enforce it, humans shouldn't discuss it.

```yaml
# .pre-commit-config.yaml — runs before every commit
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff          # Linting (replaces flake8, isort, etc.)
        args: [--fix]
      - id: ruff-format   # Formatting (replaces black)

  - repo: https://github.com/pre-commit/mirrors-mypy
    hooks:
      - id: mypy          # Type checking
```

**Team agreement:** If it's not in the linter config, it's not worth commenting on. No style comments in code reviews. Period.

## Fix 2: Small PRs (The Most Important Fix)

```markdown
## PR Size Limits

| PR Size | Lines Changed | Review Time | Policy |
|---------|--------------|-------------|--------|
| Small   | < 200 lines  | < 30 min    | ✅ Ideal |
| Medium  | 200-400 lines | 30-60 min  | ⚠️ Acceptable |
| Large   | 400+ lines   | 60+ min     | ❌ Split it |

### How to Split Large Features

Instead of one 800-line PR:

PR 1: Database models + migrations (100 lines)
PR 2: Service layer / business logic (150 lines)
PR 3: API endpoints (100 lines)
PR 4: Tests (200 lines)
PR 5: Frontend integration (150 lines)

Each PR is reviewable in 15-30 minutes.
Each can be merged independently (use feature flags if needed).
```

## Fix 3: Review Response SLA

```markdown
## Review SLA

- Acknowledge PR within 4 business hours (comment, approve, or request changes)
- Complete review within 1 business day
- If you can't review in time, say so and reassign

### How to Make This Work
- Set a daily "review slot" (e.g., 9-10 AM) for all developers
- GitHub/GitLab notifications → Slack channel
- Auto-assign reviewers (round-robin or CODEOWNERS)
```

```yaml
# .github/CODEOWNERS — auto-assign reviewers
/src/payments/    @payments-team
/src/auth/        @security-team
/src/api/         @backend-team
```

## Fix 4: Review Guidelines (What to Actually Look For)

```markdown
## Code Review Checklist

### MUST check (blocking):
- [ ] Does the logic handle edge cases? (null, empty, boundary values)
- [ ] Are there security issues? (injection, auth bypass, data exposure)
- [ ] Will this break existing functionality? (backwards compatibility)
- [ ] Are error paths handled? (what happens when this fails?)
- [ ] Is the database migration safe? (backwards compatible, no locks)

### SHOULD check (non-blocking):
- [ ] Is there a simpler way to do this?
- [ ] Are the tests meaningful? (not just testing mocks)
- [ ] Is the naming clear?

### DON'T check (automated):
- ~~Formatting~~ → ruff-format
- ~~Import ordering~~ → ruff
- ~~Line length~~ → ruff
- ~~Type annotations~~ → mypy
```

## Fix 5: Review Quality Feedback

```markdown
## Good Review Comment Examples

✅ "This SQL query doesn't use parameterized values — it's vulnerable
   to SQL injection. Use `db.execute(query, params)` instead."
   → Specific, actionable, catches a real bug

✅ "What happens if `user` is None here? The next line will throw
   AttributeError. Should we return 404 instead?"
   → Identifies an edge case the author missed

✅ "This works, but have you considered using a JOIN instead of N+1
   queries? With 1000 users, this will generate 1001 queries."
   → Performance insight with specific reasoning

❌ "Maybe rename this variable?"
   → Subjective, low value

❌ "I would have done this differently."
   → Not actionable without specifics

❌ "LGTM" (on a 500-line PR)
   → Rubber stamp, no value
```

## Measuring Improvement

Track these metrics weekly:

| Metric | Current | Target |
|--------|---------|--------|
| PR review time (first response) | 2-3 days | < 4 hours |
| PR review time (to merge) | 3-5 days | < 1 day |
| Average PR size | 500+ lines | < 200 lines |
| Style comments per PR | 5-10 | 0 (automated) |
| Bugs caught in review | ? | Track this |

The single biggest lever: **smaller PRs**. A 100-line PR gets reviewed in 15 minutes. A 500-line PR sits for 3 days because nobody wants to start it.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
