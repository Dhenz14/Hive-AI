"""Phase 2G: Advanced Reasoning — Abstraction Laddering (Part 1/3)
Move between concrete details and abstract principles. Specific bug → general class →
prevention strategy. One slow query → query pattern → indexing strategy."""

PAIRS = [
    (
        "thinking/abstraction-bug-to-pattern-to-policy",
        "We had a bug where a user's cart total showed $0.30000000000000004 instead of $0.30. Can you help fix it and prevent similar issues?",
        r'''<think>
Let me move up and down the abstraction ladder on this.

CONCRETE LEVEL (the specific bug):
- 0.1 + 0.2 = 0.30000000000000004 in IEEE 754 floating point
- The cart displays this raw float value to the user
- Fix: use round() or Decimal for display

ZOOMING OUT (the pattern):
- This isn't just about 0.1 + 0.2 — it's about floating point representation
- ANY sum of decimal fractions can produce these artifacts
- Tax calculations, discount percentages, currency conversions — all affected
- The pattern is: "using float for exact decimal values"

ZOOMING OUT FURTHER (the principle):
- This is a type system problem: using the wrong type for the domain
- Money is exact decimal arithmetic, not approximate floating point
- The principle: "choose data types that match domain semantics"
- Other instances of this principle:
  - Using int for IDs that might be UUIDs later
  - Using string for dates
  - Using float for anything that needs exact comparison

ZOOMING OUT TO POLICY (prevention):
- Code review checklist: "Is float used for money anywhere?"
- Linting rule: flag float usage in financial calculations
- Standard library: create a Money type that enforces Decimal
- Testing: property-based tests that check arithmetic properties

Now let me zoom back in to give the concrete fix, informed by all these levels.
</think>

Let me walk up the abstraction ladder from this specific bug to a prevention policy:

**Level 1 — The specific bug** (fix it now):
```python
# Bug: 0.1 + 0.2 = 0.30000000000000004
cart_total = sum(item.price for item in items)  # float arithmetic
display(f"${cart_total}")  # Shows $0.30000000000000004

# Immediate fix:
display(f"${cart_total:.2f}")  # Shows $0.30 — but only hides the problem!
```

**Level 2 — The general class of bugs** (understand the pattern):
```python
# This isn't just 0.1 + 0.2. It's EVERY decimal-to-binary conversion:
0.1 + 0.2 == 0.3         # False
1.1 + 2.2 == 3.3         # False
0.07 * 100 == 7.0        # False (gives 7.000000000000001)

# It affects:
# - Cart totals
# - Tax calculations (8.25% tax on $19.99)
# - Discount applications (15% off)
# - Currency conversions
# - Refund calculations
# - Invoice reconciliation
# ANYTHING with money and float is a ticking time bomb
```

**Level 3 — The underlying principle** (why it happens):
```
The root principle: USE DATA TYPES THAT MATCH DOMAIN SEMANTICS.

Money is exact decimal arithmetic. float is approximate binary arithmetic.
They serve different purposes:

float: good for physics, graphics, ML — approximate values are fine
Decimal: good for money, accounting — exact values are required
int (cents): good for money stored as smallest unit — always exact

This principle applies beyond money:
- Dates: don't use strings, use datetime
- IDs: don't use int if they can be UUID
- Booleans: don't use int (0/1) if you mean true/false
- Coordinates: don't use float if you need precision (use fixed-point)
```

**Level 4 — Prevention policy** (never have this bug again):
```python
# 1. Create a Money type (enforces correct arithmetic everywhere)
from decimal import Decimal, ROUND_HALF_UP

class Money:
    def __init__(self, amount: str | Decimal):
        if isinstance(amount, float):
            raise TypeError("Cannot create Money from float — use string or Decimal")
        self.amount = Decimal(str(amount))

    def __add__(self, other: 'Money') -> 'Money':
        return Money(self.amount + other.amount)

    def __mul__(self, factor: int | Decimal) -> 'Money':
        result = self.amount * Decimal(str(factor))
        return Money(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def __str__(self) -> str:
        return f"${self.amount:.2f}"

# 2. Lint rule: flag float in financial code
# pyproject.toml or custom flake8 rule:
# "float literal in module matching *price*, *cost*, *total*, *payment*"

# 3. Code review checklist item:
# □ Money calculations use Decimal or int-cents, never float

# 4. Property-based test:
from hypothesis import given, strategies as st

@given(
    a=st.decimals(min_value=0, max_value=10000, places=2),
    b=st.decimals(min_value=0, max_value=10000, places=2),
)
def test_money_addition_is_exact(a, b):
    result = Money(a) + Money(b)
    assert result.amount == a + b  # Exact — no floating point error
```

**The abstraction ladder summary**:
```
$0.30000000000000004  ← specific bug (Level 1: fix it)
        ↓
"float for money"     ← bug pattern (Level 2: understand it)
        ↓
"wrong type for domain" ← principle (Level 3: generalize it)
        ↓
"enforce types in code" ← policy (Level 4: prevent it)
```'''
    ),
    (
        "thinking/abstraction-slow-query-to-strategy",
        "This query takes 8 seconds:\n```sql\nSELECT * FROM orders WHERE customer_email = 'alice@example.com' ORDER BY created_at DESC;\n```\nThe orders table has 5 million rows. How do I fix it?",
        r'''<think>
Let me ladder up from this specific slow query to a general indexing strategy.

CONCRETE (this query):
- WHERE customer_email = '...' → needs an index on customer_email
- ORDER BY created_at DESC → needs the index to include created_at
- SELECT * → fetches all columns, even if we only need a few
- 5M rows full scan = slow

PATTERN (what kind of query is this?):
- Equality filter + sort = very common pattern
- Composite index (customer_email, created_at DESC) would be ideal
- The covering index pattern: if we only need a few columns, include them in the index

PRINCIPLE (when and how to index):
- Index columns that appear in WHERE, JOIN, ORDER BY
- Composite indexes: most selective column first
- Don't over-index: each index slows down writes
- The database can only use one index per table scan (usually)
- Covering indexes avoid table lookups entirely

STRATEGY (how to approach indexing systematically):
- Monitor pg_stat_statements for slowest queries
- Add indexes based on actual query patterns, not guesses
- Review indexes periodically for unused ones
- Use partial indexes for filtered queries

Let me provide the concrete fix and then zoom out to the strategy.
</think>

Let me fix this specific query, then zoom out to a general indexing strategy:

**Level 1 — Fix this specific query** (immediate):
```sql
-- The query: WHERE customer_email = X ORDER BY created_at DESC
-- Optimal index: composite on both columns
CREATE INDEX CONCURRENTLY idx_orders_email_created
ON orders(customer_email, created_at DESC);

-- Before: Seq Scan on orders (5M rows) → 8 seconds
-- After:  Index Scan → 2 milliseconds

-- Also: don't SELECT * if you only need a few columns
SELECT id, customer_email, total, status, created_at
FROM orders
WHERE customer_email = 'alice@example.com'
ORDER BY created_at DESC
LIMIT 20;  -- Do you really need ALL orders? Add LIMIT.
```

**Level 2 — The query pattern** (recognize it when you see it):
```
Pattern: EQUALITY FILTER + SORT + LIMIT

This is the most common query shape in web applications:
- "Show user's recent orders" → WHERE user_id = X ORDER BY created_at DESC LIMIT 20
- "Show latest posts in category" → WHERE category = X ORDER BY published_at DESC LIMIT 50
- "Show active tickets for agent" → WHERE agent_id = X AND status = 'open' ORDER BY priority

Index recipe for this pattern:
  CREATE INDEX ON table(equality_column, sort_column [DESC]);
  The equality column goes FIRST (narrows the search).
  The sort column goes SECOND (avoids a separate sort step).
```

**Level 3 — The indexing principle** (apply to any table):
```
RULE 1: Index columns in WHERE, JOIN ON, ORDER BY
  - But ONLY for queries that run frequently (check pg_stat_statements)

RULE 2: Column order in composite index matters
  - Most selective (fewest matches) FIRST
  - Sort column LAST
  - WHERE a = X AND b = Y ORDER BY c →  INDEX ON (a, b, c)

RULE 3: Covering index avoids table lookup
  - If you only SELECT (a, b, c) and index is ON (a, b, c),
    PostgreSQL never reads the actual table row → 2x faster

RULE 4: Each index costs write performance
  - 5 indexes on a table: every INSERT updates 5 B-trees
  - Don't index "just in case" — index for actual queries

RULE 5: Partial indexes for filtered subsets
  - WHERE status = 'active' (99% of queries filter by active)
  - CREATE INDEX ON orders(customer_email) WHERE status = 'active';
  - Smaller index, same speed, less write overhead
```

**Level 4 — Systematic indexing strategy** (team policy):
```sql
-- Step 1: Find your actual slow queries (not guesses)
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- Step 2: Check which existing indexes are unused (candidates for removal)
SELECT indexrelname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
WHERE idx_scan = 0 AND indexrelname NOT LIKE '%pkey%';

-- Step 3: Check for missing indexes (sequential scans on large tables)
SELECT relname, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch
FROM pg_stat_user_tables
WHERE seq_scan > 100 AND pg_relation_size(relid) > 10000000;

-- Step 4: Review quarterly
-- - Remove unused indexes (from Step 2)
-- - Add indexes for new slow queries (from Step 1)
-- - Check index bloat and reindex if needed
```

**The ladder**:
```
8-second query          ← symptom    (fix THIS query)
        ↓
equality + sort pattern ← pattern    (recognize this shape)
        ↓
indexing principles     ← principles (apply to any table)
        ↓
quarterly index review  ← strategy   (systematic prevention)
```'''
    ),
    (
        "thinking/abstraction-vuln-to-threat-model",
        "A security audit found that our API endpoint `/api/users/{id}` returns full user profiles to any authenticated user, not just their own profile. This is an IDOR vulnerability. How do I fix it and prevent similar issues?",
        r'''<think>
Let me ladder from this specific IDOR to a comprehensive authorization strategy.

CONCRETE (this specific bug):
- GET /api/users/42 returns user 42's full profile to ANY authenticated user
- An attacker can enumerate all users by incrementing the ID
- Fix: check that the requesting user is authorized to view the profile

PATTERN (what type of vulnerability is this?):
- Insecure Direct Object Reference (IDOR)
- The user supplies an ID, the server trusts it without checking authorization
- This affects any endpoint that takes a resource ID: /orders/{id}, /invoices/{id}, etc.
- It's not just read — IDOR on PUT/DELETE lets attackers modify/delete others' data

PRINCIPLE (the root cause):
- The application confuses AUTHENTICATION (who are you?) with AUTHORIZATION (what can you do?)
- Just because you're logged in doesn't mean you can access everything
- Authorization must be checked at the resource level, not just the route level
- The principle: "every access to every resource must be authorized"

STRATEGY (prevention):
- Authorization middleware that checks ownership/permissions before handlers run
- UUIDs instead of sequential IDs (harder to enumerate, but NOT a security fix)
- Integration tests that verify access control
- Automated IDOR scanning in CI/CD
</think>

Let me ladder from the specific IDOR to a comprehensive authorization strategy:

**Level 1 — Fix this specific endpoint** (today):
```python
# BEFORE (broken): any authenticated user can view any profile
@app.get("/api/users/{user_id}")
async def get_user(user_id: int, current_user: User = Depends(get_current_user)):
    return await user_repo.get(user_id)  # No authorization check!

# AFTER (fixed): verify the requesting user is authorized
@app.get("/api/users/{user_id}")
async def get_user(user_id: int, current_user: User = Depends(get_current_user)):
    if user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(403, "Not authorized to view this profile")
    return await user_repo.get(user_id)
```

**Level 2 — The IDOR pattern** (recognize it everywhere):
```python
# This pattern is vulnerable ANYWHERE a user-supplied ID accesses a resource:
GET /api/orders/{order_id}        # Can I see other people's orders?
PUT /api/posts/{post_id}          # Can I edit other people's posts?
DELETE /api/comments/{comment_id} # Can I delete other people's comments?
GET /api/invoices/{invoice_id}    # Can I download other people's invoices?

# The pattern: endpoint takes an ID, doesn't verify the requester owns that resource
```

**Level 3 — Authorization principle** (apply everywhere):
```python
# The principle: EVERY resource access must check authorization
# Don't just check "is user logged in" — check "does this user own this resource"

# Implement as reusable middleware/dependency:
class ResourceAuthorizer:
    """Check resource ownership before handler runs."""

    async def verify_ownership(
        self,
        resource_type: str,
        resource_id: int,
        user: User,
        action: str = "read",
    ) -> None:
        # Check ownership based on resource type
        if resource_type == "order":
            order = await order_repo.get(resource_id)
            if order is None:
                raise HTTPException(404)
            if order.user_id != user.id and not user.has_permission(f"orders:{action}"):
                raise HTTPException(403)

        elif resource_type == "post":
            post = await post_repo.get(resource_id)
            if post is None:
                raise HTTPException(404)
            if post.author_id != user.id and not user.has_permission(f"posts:{action}"):
                raise HTTPException(403)

# Usage — clean and consistent
authorizer = ResourceAuthorizer()

@app.get("/api/orders/{order_id}")
async def get_order(order_id: int, user: User = Depends(get_current_user)):
    await authorizer.verify_ownership("order", order_id, user, "read")
    return await order_repo.get(order_id)

@app.delete("/api/posts/{post_id}")
async def delete_post(post_id: int, user: User = Depends(get_current_user)):
    await authorizer.verify_ownership("post", post_id, user, "delete")
    await post_repo.delete(post_id)
```

**Level 4 — Systematic authorization strategy** (team policy):
```python
# 1. Automated IDOR testing in CI
@pytest.mark.security
async def test_idor_users():
    """Verify users can't access other users' data."""
    user_a = await create_test_user()
    user_b = await create_test_user()

    # User A tries to access User B's data
    resp = await client.get(
        f"/api/users/{user_b.id}",
        headers=auth_headers(user_a)
    )
    assert resp.status_code == 403  # Must be forbidden

@pytest.mark.security
async def test_idor_all_endpoints():
    """Scan ALL resource endpoints for IDOR."""
    user_a = await create_test_user()
    user_b = await create_test_user()

    # Create resources owned by user_b
    order = await create_order(user_b)
    post = await create_post(user_b)

    # User A tries every endpoint with user_b's resource IDs
    idor_tests = [
        ("GET", f"/api/orders/{order.id}"),
        ("PUT", f"/api/orders/{order.id}"),
        ("DELETE", f"/api/orders/{order.id}"),
        ("GET", f"/api/posts/{post.id}"),
        ("PUT", f"/api/posts/{post.id}"),
        ("DELETE", f"/api/posts/{post.id}"),
    ]

    for method, path in idor_tests:
        resp = await client.request(method, path, headers=auth_headers(user_a))
        assert resp.status_code in (403, 404), f"IDOR on {method} {path}: got {resp.status_code}"

# 2. Code review checklist:
# □ Every endpoint with a resource ID checks authorization
# □ Authorization is checked BEFORE any data modification
# □ 404 for resources that don't exist (don't leak existence info)
# □ Separate authentication (who) from authorization (what)

# 3. Use UUIDs instead of sequential IDs (reduces enumeration, NOT a security fix)
# Sequential: /api/users/1, /api/users/2, /api/users/3 — trivial to enumerate
# UUID: /api/users/f47ac10b-58cc-4372-a567-0e02b2c3d479 — hard to guess
```

**The ladder**:
```
/api/users/{id} IDOR         ← specific vulnerability
        ↓
"check ownership on all       ← pattern (recognize it)
 resource endpoints"
        ↓
"authentication ≠ authorization" ← principle (understand it)
        ↓
"automated IDOR testing + code   ← strategy (prevent it)
 review checklist"
```'''
    ),
    (
        "thinking/abstraction-incident-to-process",
        "We had a 2-hour outage because a developer ran a database migration that locked a table for 15 minutes during peak hours. How do we prevent this?",
        r'''<think>
Let me ladder from this specific incident to a process improvement.

CONCRETE (what happened):
- Developer ran ALTER TABLE ... ADD COLUMN with a default value
- In PostgreSQL < 11, this locks the entire table (requires full table rewrite)
- During peak hours, all queries to that table blocked
- 15 minutes of lock + recovery time = 2 hours total outage

PATTERN (what type of incident is this?):
- Schema migration that's unsafe under load
- Not all migrations are equal: some are online (ADD COLUMN without default), some are blocking (ADD COLUMN with DEFAULT on old PG versions, changing column types, adding NOT NULL without default)
- The pattern: "unsafe database operation performed without understanding its locking behavior"

PRINCIPLE (the root cause):
- The developer didn't know this migration would lock the table
- There was no review process for migrations
- There was no staging environment test under load
- There was no deployment window policy
- The system had a single point of failure: one locked table = full outage

STRATEGY (prevention):
- Migration safety checklist
- Automated linting for unsafe migrations
- Deployment windows for schema changes
- Shadow testing of migrations on production-sized data
- Blue-green deployment for schema changes
</think>

**Laddering from incident to prevention**:

**Level 1 — The specific incident** (what went wrong):
```sql
-- The developer ran this during peak hours:
ALTER TABLE orders ADD COLUMN discount_code VARCHAR(50) DEFAULT '';

-- In PostgreSQL < 11, this REWRITES THE ENTIRE TABLE
-- Holds an ACCESS EXCLUSIVE lock for the duration
-- Every query to the orders table blocks until rewrite completes
-- 5M rows × rewrite = 15 minutes of downtime
```

**Level 2 — The class of dangerous migrations** (what to watch for):
```sql
-- SAFE migrations (minimal/no locking):
ALTER TABLE orders ADD COLUMN discount_code VARCHAR(50);  -- NULL default, no rewrite
CREATE INDEX CONCURRENTLY idx_name ON orders(name);       -- CONCURRENTLY = no lock
ALTER TABLE orders DROP COLUMN old_field;                 -- Metadata only in PG 11+

-- DANGEROUS migrations (locks table, blocks queries):
ALTER TABLE orders ADD COLUMN code VARCHAR(50) DEFAULT ''; -- Full rewrite (PG < 11)
ALTER TABLE orders ALTER COLUMN price TYPE NUMERIC(12,2);  -- Full rewrite
ALTER TABLE orders ADD CONSTRAINT fk FOREIGN KEY ...;      -- Validates all rows
CREATE INDEX idx_name ON orders(name);                     -- Without CONCURRENTLY!
ALTER TABLE orders ALTER COLUMN name SET NOT NULL;         -- Scans all rows
```

**Level 3 — The principle** (why this happened):
```
Root causes (not the developer — the system):
1. No migration review process → unsafe migrations slip through
2. No staging test under load → locking behavior not discovered
3. No deployment windows → schema changes during peak hours
4. No documentation → developer didn't know ADD COLUMN + DEFAULT locks
5. No automated safety checks → no guardrails
```

**Level 4 — Prevention strategy** (systematic):
```python
# 1. AUTOMATED MIGRATION LINTING (catches unsafe patterns)
# Use `squawk` (PostgreSQL migration linter) in CI:
# pip install squawk-cli

# In CI pipeline:
# squawk check migrations/*.sql
# Flags:
# - ADD COLUMN with DEFAULT (suggest: add column, then backfill)
# - CREATE INDEX without CONCURRENTLY
# - ALTER COLUMN TYPE (suggest: add new column, migrate data, drop old)
# - ADD CONSTRAINT without NOT VALID

# 2. MIGRATION REVIEW CHECKLIST
MIGRATION_REVIEW = """
□ Does this migration acquire locks? (check with: SELECT * FROM pg_locks)
□ Tested on production-sized dataset? (not just dev with 100 rows)
□ Can it run in under 1 second? (if not, needs special deployment)
□ Is it backward-compatible? (old code can run with new schema?)
□ Is it reversible? (migration down works?)
□ CREATE INDEX uses CONCURRENTLY?
□ ADD COLUMN uses nullable instead of DEFAULT?
"""

# 3. SAFE MIGRATION PATTERNS
# Instead of:
#   ALTER TABLE orders ADD COLUMN code VARCHAR DEFAULT '';
# Do:
#   Step 1 (fast, no lock):
#     ALTER TABLE orders ADD COLUMN code VARCHAR;
#   Step 2 (background, no lock):
#     UPDATE orders SET code = '' WHERE code IS NULL;  -- in batches!
#   Step 3 (optional, after backfill):
#     ALTER TABLE orders ALTER COLUMN code SET DEFAULT '';
#     ALTER TABLE orders ALTER COLUMN code SET NOT NULL;  -- only after all rows filled

# 4. DEPLOYMENT WINDOWS FOR SCHEMA CHANGES
class MigrationPolicy:
    SAFE_HOURS = range(2, 6)    # 2-6 AM only for schema changes
    MAX_TABLE_SIZE_FOR_ONLINE = 1_000_000  # Tables > 1M rows need review

    @staticmethod
    def can_run_now(migration_type: str) -> bool:
        hour = datetime.utcnow().hour
        if migration_type == "schema_change":
            return hour in MigrationPolicy.SAFE_HOURS
        return True  # Data-only migrations can run anytime

# 5. POST-INCIDENT: ADD MONITORING
# Alert if any query is blocked for > 5 seconds
# Alert if pg_locks shows ACCESS EXCLUSIVE held > 10 seconds
# Alert if migration runs during peak hours
```

**The ladder**:
```
Table locked for 15 min       ← incident (what happened)
        ↓
"unsafe migration patterns"    ← pattern (recognize the category)
        ↓
"no guardrails on schema       ← principle (why it happened)
 changes"
        ↓
"automated linting + review    ← strategy (prevent forever)
 + deployment windows"
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
