"""Phase 3A: Metacognition — Detecting Circular Reasoning and Logical Fallacies (Part 7)

Training the model to identify circular reasoning, begging the question,
and other logical fallacies in technical arguments.
"""

PAIRS = [
    (
        "thinking/meta-reasoning-circular-best-practices",
        r'''Why should we use Docker for deployment? Because it's an industry best practice. And why is it a best practice? Because everyone uses it for deployment.''',
        r'''<think>
This is a textbook circular reasoning pattern. Let me identify the structure:

"We should use Docker" → "Because it's best practice"
"Why is it best practice?" → "Because everyone uses it"
"Why does everyone use it?" → (implied: because it's best practice)

The argument is: X is good because people do X, and people do X because X is good. No actual justification for the initial claim is ever provided.

This is also an argumentum ad populum (appeal to popularity) — the fact that something is widely used doesn't make it the right choice for a specific situation.

I should:
1. Name the fallacy clearly
2. Show why "best practice" is not an argument
3. Provide the ACTUAL reasons Docker might or might not be appropriate
4. Teach how to evaluate tools on their merits
</think>

You've identified your own circular reasoning, which is great. Let me break down the fallacy and replace it with sound reasoning.

**The circular structure:**
```
"Use Docker" → "It's best practice" → "Everyone uses it" → "Use Docker"
     ↑                                                          |
     └──────────── No actual justification enters here ─────────┘
```

**"Best practice" is not an argument.** It's an appeal to authority/popularity that skips the actual analysis. What you need is:

**Actual reasons Docker might be right for you:**
```
Problem Docker solves          │ Your situation?
──────────────────────────────┼─────────────────────
"Works on my machine" issues   │ Do you have env parity problems?
Dependency isolation           │ Do services need different runtimes?
Reproducible builds            │ Are builds inconsistent today?
Easy scaling with orchestration│ Do you need horizontal scaling?
Standardized deployment        │ Is deployment currently painful?
```

**Actual reasons Docker might be wrong for you:**
```
Concern                        │ Your situation?
──────────────────────────────┼─────────────────────
Added complexity               │ Is your current deploy simple enough?
Resource overhead              │ Are you resource-constrained?
Learning curve                 │ Does your team know Docker?
Single binary deploys          │ Go/Rust binaries are already portable
Debugging is harder            │ Can your team debug containerized apps?
```

**Sound reasoning structure:**
```
1. What specific problem are we trying to solve?
2. Does Docker solve that problem better than alternatives?
3. What does Docker cost us (complexity, learning, overhead)?
4. Is the benefit > the cost for OUR specific situation?
```

Replace "it's best practice" with "it solves X problem for us because Y." If you can't fill in X and Y, you don't have a reason to adopt it.'''
    ),
    (
        "thinking/meta-reasoning-circular-testing",
        r'''How do we know our test suite is good? Because our code coverage is 90%. And how do we know 90% is good? Because our tests cover 90% of the code.''',
        r'''<think>
Another circular reasoning pattern, but this one is more subtle and very common in practice.

The circular structure:
- "Test suite is good" → "Because 90% coverage"
- "Why is 90% good?" → "Because we cover 90% of the code"

This is circular because it defines "good" as "high coverage" and then points to high coverage as proof of goodness. Coverage is being used as both the metric and the justification.

The deeper problem: code coverage measures HOW MUCH code is executed by tests, not whether the tests actually verify correct behavior. You can have 100% coverage with tests that assert nothing meaningful.

Let me provide a concrete example of the gap between coverage and quality, and then explain what actually makes a test suite good.
</think>

This is circular reasoning, and it's extremely common in practice. The metric is being used to define AND prove quality simultaneously.

**The circularity:**
```
"Tests are good" → "90% coverage" → "Coverage is high" → "Tests are good"
                    ↑ This never proves test QUALITY ↑
```

**Why coverage alone means nothing — a concrete proof:**

```python
# 100% code coverage, ZERO test quality:
def calculate_discount(price, is_member):
    if is_member:
        return price * 0.8   # 20% discount
    return price

# This test achieves 100% branch coverage:
def test_discount():
    calculate_discount(100, True)
    calculate_discount(100, False)
    # No assertions! We never check the results.
    # Coverage: 100%. Bugs caught: 0.
```

**What actually makes a test suite good (non-circular criteria):**

1. **Mutation testing** — does changing the code break the tests?
```bash
# Mutant: change "price * 0.8" to "price * 0.9"
# If no test fails → your tests are weak regardless of coverage
mutmut run --paths-to-mutate=src/
```

2. **Fault detection rate** — do tests catch real bugs?
```
Track: How many production bugs WOULD have been caught by the test suite?
If a bug reaches production, write a test that catches it, then ask:
"Why didn't our existing tests catch this?"
```

3. **Assertion density** — are tests actually checking things?
```python
# Weak: high coverage, no real assertions
def test_process_order():
    result = process_order(order)
    assert result is not None  # Proves almost nothing

# Strong: verifies specific behavior
def test_process_order_applies_member_discount():
    order = Order(items=[Item(price=100)], member=True)
    result = process_order(order)
    assert result.total == 80.0
    assert result.discount_applied == 20.0
    assert result.discount_reason == "member"
```

4. **Boundary testing** — are edge cases covered?
```python
# Coverage doesn't distinguish between testing the happy path
# and testing the boundaries where bugs live
def test_discount_edge_cases():
    assert calculate_discount(0, True) == 0         # Zero price
    assert calculate_discount(0.01, True) == 0.008   # Tiny price
    assert calculate_discount(-10, True) == ...      # Negative? Error?
```

**Replace circular reasoning with measurable criteria:**
```
Old: "Our tests are good because coverage is 90%"
New: "Our mutation score is 75%, meaning 75% of code changes
     are detected by our tests. We're improving from 60% last quarter."
```

Coverage tells you what code runs. It does not tell you what code is tested.'''
    ),
    (
        "thinking/meta-reasoning-fallacy-authority",
        r'''My senior developer says we should never use ORMs because they wrote raw SQL for 20 years and ORMs always generate bad queries. Should we follow this advice?''',
        r'''<think>
This involves several potential fallacies:

1. Appeal to authority — "senior developer says so" is not inherently valid reasoning. Experience is valuable but doesn't make someone right about everything.

2. Hasty generalization — "ORMs always generate bad queries" generalizes from personal experience to an absolute claim. Modern ORMs have improved significantly.

3. Anchoring bias — 20 years of raw SQL creates a strong preference and comfort zone. The senior dev may be comparing their expert-level SQL to a beginner's use of an ORM.

4. However, there IS legitimate experience behind the claim. ORMs DO sometimes generate inefficient queries. The claim isn't entirely baseless — it's overgeneralized.

The right approach is:
- Acknowledge the legitimate experience and concerns
- Challenge the absolute framing ("never" / "always")
- Present evidence for when ORMs are and aren't appropriate
- Help the person make a context-dependent decision rather than following an absolute rule
</think>

This advice contains real experience but is expressed as an absolute rule, which makes it unreliable. Let me separate the valid insight from the logical errors.

**The fallacies present:**

1. **Appeal to authority:** "I have 20 years of experience" doesn't make "never use ORMs" correct. Experience creates expertise AND blind spots.

2. **Hasty generalization:** "ORMs always generate bad queries" is an absolute claim based on personal experience. It ignores cases where ORMs work well.

3. **Anchoring bias:** After 20 years of raw SQL, everything else looks inferior. This person compares their expert SQL to a typical developer's ORM usage — an unfair comparison.

**The legitimate kernel of truth:**

Your senior dev is right that ORMs CAN generate bad queries:
```python
# ORM N+1 problem (legitimate concern):
users = User.objects.all()
for user in users:
    print(user.orders.count())  # Executes N additional queries!

# The senior dev's raw SQL does this in one query:
# SELECT u.id, COUNT(o.id) FROM users u LEFT JOIN orders o ON ...
```

**But the conclusion "never use ORMs" doesn't follow:**

```python
# Modern ORMs handle this fine when used correctly:
users = User.objects.annotate(order_count=Count('orders'))  # One query

# ORMs also provide:
# - SQL injection protection by default
# - Database-agnostic code
# - Migration management
# - Type safety (in typed ORMs like Prisma, SQLAlchemy)
```

**Sound reasoning — when to use what:**

| Situation | Best approach |
|-----------|--------------|
| CRUD operations, standard queries | ORM — safer, faster to develop |
| Complex reporting/analytics | Raw SQL or query builder |
| Performance-critical hot paths | Profile first, raw SQL if needed |
| Batch operations on millions of rows | Raw SQL or bulk ORM operations |
| Rapid prototyping | ORM |

**The nuanced answer to give your team:**
```
Use the ORM for 90% of queries (safer, faster development)
Drop to raw SQL for the 10% that need it (complex joins, performance)
Monitor generated queries in development (Django debug toolbar, etc.)
Never follow "always" or "never" rules without context
```

Respect the senior dev's experience but evaluate the claim on its merits, not on the authority of who said it.'''
    ),
    (
        "thinking/meta-reasoning-fallacy-sunk-cost",
        r'''We've spent 8 months building our custom authentication system. It has some security issues but we can't switch to Auth0/Cognito now because we've invested too much time in it.''',
        r'''<think>
This is a classic sunk cost fallacy. Let me analyze it.

The sunk cost fallacy: Continuing an endeavor because of previously invested resources (time, money, effort) rather than evaluating the future costs and benefits.

The reasoning structure:
- "We spent 8 months" — sunk cost, cannot be recovered regardless of decision
- "It has security issues" — current problem that affects future outcomes
- "Can't switch because of investment" — future decision based on past cost

The correct reasoning framework:
- The 8 months are gone regardless of what you choose now
- The only relevant question is: "From today forward, what's the best path?"
- Compare: cost of fixing security issues vs cost of migrating to Auth0/Cognito
- Consider: ongoing maintenance burden of custom auth vs managed service
- Consider: risk of security breach with known security issues

This is especially dangerous for authentication because:
- Security vulnerabilities in auth have catastrophic consequences
- Custom auth systems are notoriously hard to get right
- Managed auth services are maintained by security specialists
- The cost of a breach likely dwarfs the migration cost

I should name the fallacy, reframe the decision correctly, and help them evaluate based on forward-looking costs.
</think>

This is the sunk cost fallacy — one of the most common and dangerous reasoning errors in software projects, and especially dangerous when applied to security infrastructure.

**The fallacy:**
```
Past investment (8 months) → Should not influence → Future decision
         ↓                                              ↓
    Already spent,                              "From today, what's
    cannot be recovered                          the best path forward?"
```

**The correct decision framework:**

Ignore the 8 months. They're gone regardless. Compare only forward-looking costs:

```
Option A: Fix and maintain custom auth
  - Fix known security issues:        2-4 weeks
  - Future security patches:          Ongoing (indefinite)
  - Keeping up with auth standards:   Ongoing (OIDC, FIDO2, etc.)
  - Security audit:                   $20-50K per audit
  - Risk of undiscovered vulns:       HIGH (custom code = unique attack surface)
  - Opportunity cost:                 Engineer time not spent on core product

Option B: Migrate to managed auth (Auth0/Cognito)
  - Migration effort:                 4-8 weeks (estimate; measure this)
  - Ongoing cost:                     $$/month (but saves engineer time)
  - Security maintained by:           Dedicated security team
  - Compliance certifications:        SOC2, HIPAA, etc. included
  - Risk of custom vulnerabilities:   Near zero
  - Your engineers freed up for:      Core product features
```

**Why this is ESPECIALLY dangerous for authentication:**

```
Custom auth with known security issues =
    Known vulnerabilities × Time until exploited × Breach cost

Average cost of a data breach: $4.45M (IBM 2023 report)
Auth is the #1 attack vector for most applications
"We'll fix it later" in security often means "after the breach"
```

**Questions that reveal the right decision:**
1. Can your team fix the security issues AND keep up with evolving auth standards?
2. How many engineers-hours per month does the custom system consume?
3. What's the cost of a security breach to your business?
4. Would those engineers create more value working on your core product?

**The honest reframe:**
```
Wrong question: "Should we throw away 8 months of work?"
Right question: "Should we continue investing in custom auth, given what
                we know about its security issues and maintenance burden?"
```

If the answer to the right question is "migrate," the 8 months don't change that. Continuing to invest in a flawed system because of past investment just increases the total loss.'''
    ),
    (
        "thinking/meta-reasoning-fallacy-composition",
        r'''Each of our microservices has 99.9% uptime individually. Therefore our system as a whole has 99.9% uptime.''',
        r'''<think>
This is the fallacy of composition — assuming that what's true of the parts is true of the whole. In distributed systems, this is particularly dangerous because reliability math works against you as you add components.

The actual math:
- If each service has 99.9% uptime (independently)
- And you have N services in series (all must be up for the system to work)
- System uptime = 0.999^N

For common microservice counts:
- 5 services: 0.999^5 = 99.5% (4.38 hours downtime/year)
- 10 services: 0.999^10 = 99.0% (87.6 hours downtime/year!)
- 20 services: 0.999^20 = 98.0% (175 hours downtime/year!)

This is a well-known problem in reliability engineering. The solution involves redundancy, circuit breakers, graceful degradation, and understanding which service failures are critical vs tolerable.

I should present the math clearly, name the fallacy, and show how to actually reason about system reliability.
</think>

This is the **fallacy of composition** — assuming what's true for individual parts is true for the whole. In distributed systems, the math works against you.

**The actual math:**

If a request must traverse N services (all must be up):
```
System availability = Service1 × Service2 × ... × ServiceN

Individual service: 99.9% (8.76 hours downtime/year)

5 services in series:  0.999^5  = 99.5%  →  43.8 hours downtime/year
10 services in series: 0.999^10 = 99.0%  →  87.6 hours downtime/year
20 services in series: 0.999^20 = 98.0%  → 175.2 hours downtime/year
```

**Your 99.9% per service with 10 services gives you 99.0% system uptime — that's 10x worse than any individual service.**

**Visual:**
```
Request → [API Gateway] → [Auth] → [User Service] → [Product] → [Pricing] → [Inventory]
              99.9%        99.9%      99.9%           99.9%       99.9%       99.9%

System availability: 0.999^6 = 99.4%  (52.6 hours downtime/year)

Any ONE service down = user-facing failure
```

**How to actually achieve high system reliability:**

1. **Redundancy** — don't put services in series:
```
Service with 2 redundant instances:
Availability = 1 - (1 - 0.999)^2 = 99.9999%

Multiple replicas behind a load balancer dramatically improve per-service reliability.
```

2. **Graceful degradation** — not every service is critical:
```
Product page loads without personalization if Recommendation Service is down
Search returns cached results if Search Index is temporarily unavailable
Order accepted into queue even if Email Service is down
```

3. **Circuit breakers** — prevent cascade failures:
```
If Pricing Service is down:
  → Show cached prices (stale but available)
  → Don't let every request time out waiting for it
  → Alert and recover independently
```

4. **Distinguish critical path from optional:**
```
Critical (all must work):     Auth → Order → Payment
Optional (degrade gracefully): Recommendations, Analytics, Email
```

**Sound reliability reasoning:**
```
1. Map the critical request path (which services MUST be up?)
2. Calculate: 0.999^(critical services) = actual availability
3. Add redundancy to each critical service
4. Make non-critical services optional (circuit breaker + fallback)
5. Measure system availability end-to-end, not per-service
```

Never multiply individual reliability numbers and assume the result applies to the system.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
