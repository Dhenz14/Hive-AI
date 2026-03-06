"""Phase 2F: Advanced Reasoning — Uncertainty Calibration (Part 8/8)"""

PAIRS = [
    (
        "thinking/uncertainty-orm-vs-raw-sql",
        "Our team is debating whether to use an ORM (SQLAlchemy) or write raw SQL queries. Half the team says ORMs are slow and hide what's happening. The other half says raw SQL is unmaintainable. Who's right?",
        r'''<think>
ORM vs raw SQL — classic debate. Let me think about this carefully with calibrated uncertainty.

**ORM advantages:**
- Database-agnostic (can switch from Postgres to MySQL — but how often does anyone actually do this?)
- Type safety and IDE autocompletion
- Automatic parameterization (SQL injection prevention)
- Migrations generated from model changes
- Relationships and lazy loading
- Reduces boilerplate for CRUD operations

**Raw SQL advantages:**
- Full control over query structure and optimization
- No "magic" — you see exactly what's being executed
- Better performance for complex queries (CTEs, window functions, lateral joins)
- No ORM overhead (object instantiation, identity map, unit of work)
- DBAs can review and optimize actual queries

**The reality for most applications:**
- 80% of queries are simple CRUD → ORM handles these perfectly
- 15% need some optimization → ORM can handle with `.options()`, eager loading
- 5% are complex analytics/reporting → raw SQL is genuinely better

**Performance argument analysis:**
"ORMs are slow" — this is partially true but often misattributed:
- ORM overhead per query: ~0.1-1ms (insignificant compared to network + DB time)
- Real perf issues: N+1 queries (fixable with eager loading), selecting too many columns (fixable with .only()), inefficient joins (fixable with custom queries)
- Most ORM performance problems are fixable without abandoning the ORM

**Maintainability argument analysis:**
"Raw SQL is unmaintainable" — this depends on discipline:
- Well-organized SQL with named queries, comments, and consistent formatting IS maintainable
- But: refactoring (rename column) requires finding all SQL strings manually
- ORM: rename model field, migration auto-generates, all queries update

**My confidence assessment:**
- 70% confidence: Use ORM for most work, raw SQL for complex queries (hybrid approach)
- 15%: Pure ORM (if queries are truly all simple CRUD)
- 10%: Mostly raw SQL with thin data access layer (if team has strong SQL skills + complex analytics)
- 5%: Query builder (SQLAlchemy Core, Knex.js) — middle ground between ORM and raw

The "hybrid" approach is what most mature codebases end up with regardless of where they start.
</think>

Both sides are partially right. My recommendation: **use the ORM for most work, drop to raw SQL when needed** — confidence: **70%**.

## The Honest Assessment

```
ORM handles well:               Raw SQL handles better:
  Simple CRUD (80% of queries)     Complex reporting queries
  Relationships and joins          Window functions, CTEs, lateral joins
  Schema migrations                Database-specific optimizations
  Preventing SQL injection         Bulk operations (COPY, UPSERT)
  Refactoring (rename = done)      Queries with 5+ JOINs
  Type safety + autocompletion     Full-text search with ranking
```

## The "ORMs Are Slow" Myth — Calibrated

```
ORM overhead per query: 0.1-1ms
Network round-trip to DB: 1-5ms
Database query execution: 1-500ms

ORM overhead as % of total query time:
  Simple SELECT:  0.5ms ORM + 2ms network + 1ms query = 3.5ms
                  ORM overhead: 14% — noticeable in tight loops
  Complex JOIN:   0.5ms ORM + 2ms network + 50ms query = 52.5ms
                  ORM overhead: 1% — completely irrelevant

The REAL ORM performance problems:
  ❌ N+1 queries:  10ms per user × 100 users = 1000ms
     FIX: .options(joinedload(User.orders))

  ❌ Over-fetching: SELECT * when you need 2 columns
     FIX: .with_entities(User.id, User.name)

  ❌ Lazy loading:  Relationship access triggers hidden queries
     FIX: Explicit eager loading or load_only()

These are USER errors, not ORM problems.
A skilled ORM user matches raw SQL performance for 95% of queries.
```

## The Hybrid Approach (What Mature Codebases Do)

```python
# 80% of code: ORM — simple, safe, maintainable
class OrderRepository:
    def get_by_id(self, order_id: int) -> Order:
        return (
            self.session.query(Order)
            .options(joinedload(Order.items))
            .filter_by(id=order_id)
            .one()
        )

    def get_user_orders(self, user_id: int) -> list[Order]:
        return (
            self.session.query(Order)
            .filter_by(user_id=user_id)
            .order_by(Order.created_at.desc())
            .limit(50)
            .all()
        )

    # 5% of code: raw SQL — when ORM gets in the way
    def get_revenue_report(self, start_date, end_date):
        return self.session.execute(text("""
            WITH daily_revenue AS (
                SELECT
                    DATE_TRUNC('day', o.created_at) AS day,
                    SUM(oi.price * oi.quantity) AS revenue,
                    COUNT(DISTINCT o.id) AS order_count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                WHERE o.created_at BETWEEN :start AND :end
                  AND o.status = 'completed'
                GROUP BY DATE_TRUNC('day', o.created_at)
            )
            SELECT
                day,
                revenue,
                order_count,
                revenue / NULLIF(order_count, 0) AS avg_order_value,
                SUM(revenue) OVER (ORDER BY day) AS cumulative_revenue
            FROM daily_revenue
            ORDER BY day
        """), {"start": start_date, "end": end_date}).fetchall()
```

## Decision Matrix

```
YOUR SITUATION                          RECOMMENDATION
──────────────────────────────────────────────────────
Mostly CRUD web app                     ORM (95%)
Data-heavy analytics platform           Raw SQL or query builder
Mixed (CRUD + some reports)             Hybrid (ORM + raw for complex)
Team has strong SQL, weak Python        Raw SQL with thin wrapper
Team has strong Python, weak SQL        ORM
Frequent schema changes                 ORM (migrations are a killer feature)
Performance-critical hot path           Profile first, then optimize
Microservices with simple data access   ORM (less code to maintain)
```

## Why I'm Not More Confident (the 30% uncertainty)

```
I don't know:
  - Your team's SQL proficiency (strong SQL team → raw SQL is fine)
  - Query complexity distribution (all simple → ORM; all complex → raw SQL)
  - Performance requirements (sub-millisecond → ORM overhead matters)
  - Whether you'll actually switch databases (ORM's portability claim)
  - Your codebase size (small app → either works; large app → ORM's
    refactoring support matters more)

What would shift my confidence:
  "We do heavy analytics" → 60% raw SQL with query builder
  "It's a CRUD API for a mobile app" → 90% ORM
  "We're 3 developers with tight deadlines" → 85% ORM (faster to write)
  "We're a data engineering team" → 70% raw SQL
```'''
    ),
    (
        "thinking/uncertainty-testing-strategy-coverage-target",
        "What's the right code coverage percentage to target? My manager wants 90% and the senior dev says coverage numbers are meaningless. Should we enforce a coverage threshold?",
        r'''<think>
Code coverage targets — genuinely contested topic. Let me think through this carefully.

**The manager's argument (target 90%):**
- Measurable metric that ensures testing discipline
- Higher coverage = fewer bugs reaching production
- Provides accountability ("did you write tests?")
- Industry benchmarks suggest 80-90% as a good target

**The senior dev's argument (coverage is meaningless):**
- Coverage measures lines executed, not correctness
- 100% coverage with bad assertions = false confidence
- Coverage incentivizes testing easy code (getters/setters) over hard code (edge cases)
- Coverage gaming: tests that execute code without asserting anything

**The truth is nuanced:**
Both are partially right.

Coverage is a NECESSARY but INSUFFICIENT metric:
- 20% coverage: almost certainly undertested
- 80% coverage: probably has decent test discipline
- 100% coverage: says nothing about test QUALITY

BUT: enforcing coverage targets has real costs:
- Developers write trivial tests to hit the number
- Constructor/getter/setter tests add zero value
- Time spent reaching 90% on non-critical code could be spent on integration tests for critical paths

**What actually correlates with bug reduction:**
- Mutation testing (did tests catch intentional bugs?) — much better metric
- Integration test coverage of critical paths — more valuable than unit test line coverage
- Test quality (assertions per test, edge case coverage) — hard to measure

**My confidence:**
- 70% confident: Enforce a moderate floor (70-80%) BUT measure what matters
- 20% confident: The senior dev is right — focus on critical path testing without a number
- 10% confident: The manager is right — push for 90% with strict enforcement

The moderate floor prevents "no tests at all" without creating perverse incentives.
</think>

Both your manager and senior dev have valid points. Here's my calibrated take — confidence: **70%** on a nuanced answer.

## What Each Side Gets Right

```
MANAGER (target 90%):
  ✓ Without a target, some developers write zero tests
  ✓ Coverage is the only automated metric for test existence
  ✓ It creates accountability in code review
  ✗ 90% is high enough to incentivize trivial tests
  ✗ Coverage doesn't measure test QUALITY

SENIOR DEV (coverage is meaningless):
  ✓ 100% coverage with bad assertions = false confidence
  ✓ Coverage gaming creates waste (testing getters/setters)
  ✓ Critical path coverage matters more than line count
  ✗ "Meaningless" is too strong — 20% coverage IS worse than 80%
  ✗ Without any metric, testing discipline atrophies
```

## The Problem with Coverage as a Target

```python
# 100% COVERAGE, ZERO VALUE:
def test_user_creation():
    user = User(name="Alice", email="alice@example.com")
    # ... that's it. No assertion.
    # Coverage tool says: User.__init__ covered!

# 100% COVERAGE, MISLEADING:
def test_transfer():
    result = transfer_money(account_a, account_b, 100)
    assert result is not None  # Useless assertion
    # Lines covered! But did we check the balances?

# 30% COVERAGE, HIGH VALUE:
def test_transfer_deducts_and_credits():
    account_a = Account(balance=500)
    account_b = Account(balance=200)
    transfer_money(account_a, account_b, 100)
    assert account_a.balance == 400     # Deducted
    assert account_b.balance == 300     # Credited

def test_transfer_insufficient_funds():
    account_a = Account(balance=50)
    account_b = Account(balance=200)
    with pytest.raises(InsufficientFunds):
        transfer_money(account_a, account_b, 100)
    assert account_a.balance == 50      # Unchanged
    assert account_b.balance == 200     # Unchanged
```

## My Recommendation: Layered Approach

```
LAYER 1: Moderate coverage floor (70-80%)
  - Enforced in CI — PR can't merge below threshold
  - Prevents "zero tests" without incentivizing trivial tests
  - Exclude from coverage: config files, migrations, generated code

LAYER 2: Critical path coverage mandate (near 100%)
  - Authentication, authorization, payment, data validation
  - These MUST have thorough tests regardless of overall coverage
  - Reviewed by humans, not just measured by tools

LAYER 3: Test quality over quantity
  - Code review focuses on: "do tests check behavior, not just execution?"
  - Each test should have at least one meaningful assertion
  - Prefer integration tests for complex flows over unit tests for simple code

LAYER 4: (Advanced) Mutation testing
  - Run periodically (not every PR — it's slow)
  - Mutation testing: inject bugs → do tests catch them?
  - Reveals tests that execute code without actually verifying behavior
  - 60% mutation score is more meaningful than 95% line coverage
```

## Practical CI Configuration

```yaml
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
addopts = "--cov=src --cov-fail-under=75"

# Coverage config
[tool.coverage.run]
omit = [
    "*/migrations/*",      # Auto-generated
    "*/tests/*",           # Test code itself
    "*/config/*",          # Configuration
    "*/admin.py",          # Django admin (auto-generated)
    "*/__init__.py",       # Package markers
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.",
]
```

```
What to tell your manager:
  "We'll enforce 75% coverage floor in CI (below this = PR blocked).
   For critical paths (auth, payments, data integrity), we target
   near-100% with human review. This prevents zero-testing without
   incentivizing coverage gaming."

What to tell your senior dev:
  "Agreed that coverage alone is insufficient. The 75% floor is a
   minimum bar to prevent regression. We'll focus code review on
   test quality and critical path coverage, not the number."
```

## Confidence Breakdown

```
70% confident: Moderate floor (70-80%) + critical path focus
  Why: balances accountability with quality, avoids gaming

20% confident: No number, just cultural discipline
  When: team is small, experienced, and self-motivated
  Risk: discipline fades over time, new hires may not test

10% confident: Strict 90%+ enforcement
  When: regulated industry (medical, financial) where
        comprehensive testing is a compliance requirement
  Risk: trivial test proliferation, developer frustration
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
