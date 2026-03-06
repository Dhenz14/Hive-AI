"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 3/5)
Evaluate decisions from 5+ stakeholder or technical perspectives:
monorepo vs polyrepo, build vs buy analytics, API pagination strategy,
database migration strategy, incident response process."""

PAIRS = [
    (
        "thinking/multiperspective-monorepo-polyrepo",
        "Our company has 8 microservices maintained by 4 teams. We're debating monorepo vs polyrepo. Each team has strong opinions. Help us decide.",
        r'''<think>
Let me analyze monorepo vs polyrepo from each stakeholder's perspective, since different teams will experience this decision very differently.

Perspective 1: Platform/Infrastructure Team
- Monorepo: STRONG PREFER
  - One CI/CD pipeline to maintain
  - Shared tooling, linting, formatting — enforce once
  - Atomic commits across services (API change + client update in one PR)
  - Easier to maintain shared libraries
- Polyrepo pain:
  - 8 separate CI pipelines to maintain
  - Each repo drifts (different linting, different Python versions)
  - "Diamond dependency" problem — shared library v2 in service A, v1 in service B
- Tension: Platform team wants consistency, but bears the monorepo tooling cost

Perspective 2: Individual Service Team (let's say Team Alpha owns 2 services)
- Polyrepo: PREFER
  - Full ownership — merge without coordinating with other teams
  - Own release cadence — deploy when ready, not when monorepo is green
  - Smaller repo = faster git operations, easier to understand
  - Clear blast radius — my change can't break your service
- Monorepo pain:
  - Someone else's broken test blocks my deploy
  - PRs need review from other teams if touching shared code
  - Large repo = slow clone, slow IDE indexing
- Tension: Autonomy vs consistency

Perspective 3: New Developer (onboarding experience)
- Monorepo: SLIGHT PREFER
  - One repo to clone, one setup process
  - Can see how services interact by reading code
  - Shared conventions = learn once, apply everywhere
- Polyrepo benefit:
  - Smaller scope = less overwhelming
  - Clear boundaries = easier to understand one service

Perspective 4: Security/Compliance
- Monorepo: MIXED
  - Single set of access controls (simpler in theory)
  - But: everyone can see all code (might be an issue for sensitive services)
  - Security patches can be applied atomically across all services
- Polyrepo: MIXED
  - Fine-grained access control (team sees only their repo)
  - But: security patches need 8 separate PRs and deploys
  - Harder to audit across repos

Perspective 5: Tech Lead / Architect
- Monorepo: PREFER (if tooling exists)
  - Can refactor across service boundaries
  - See the full system in one place
  - Prevent API drift between services
  - Dependency upgrades (e.g., log4j) in one PR
- Concern: monorepo REQUIRES good tooling (Nx, Bazel, Pants)
  - Without it, CI runs ALL tests for every change = 2-hour builds
  - With it, CI runs only affected tests = fast builds
  - Tooling investment is non-trivial

Perspective 6: Release/Ops Team
- Polyrepo: SLIGHT PREFER
  - Independent deployment per service (already the case with microservices)
  - Clear artifact per repo → clear deployment unit
- Monorepo concern:
  - Need sophisticated "what changed?" logic to deploy only affected services
  - Tagging releases is more complex

My synthesis:
- 8 services, 4 teams → medium scale
- At this scale, the tooling cost of a monorepo is justified IF the platform team invests in it
- The key factor: how coupled are the services?
  - Highly coupled (shared APIs, shared libraries, frequent cross-service changes) → monorepo wins
  - Loosely coupled (independent features, independent deployments) → polyrepo wins
  - Most teams are in between → monorepo with good CI is the better default

The real answer: it depends on coupling and tooling investment. But I'll give a recommendation.
</think>

This is one of those decisions where every perspective is valid. Let me lay out how each stakeholder experiences this differently, then give you a recommendation.

**The perspective matrix:**

| Stakeholder | Monorepo | Polyrepo | Strongest concern |
|---|---|---|---|
| Platform/Infra team | Strong prefer | Pain | CI/CD maintenance × 8 |
| Service team (Alpha) | Pain | Prefer | Autonomy, own release cadence |
| New developers | Slight prefer | OK | One setup vs. 8 repos |
| Security/Compliance | Mixed | Mixed | Access control granularity |
| Tech Lead/Architect | Prefer (with tooling) | OK | Cross-service refactoring |
| Release/Ops | Concern | Slight prefer | Deployment unit clarity |

**The key decision factor you're actually debating:**

```
How coupled are your 8 services?

Highly coupled:                       Loosely coupled:
- Shared protobuf/API schemas         - Independent APIs
- Shared libraries used by 5+ svcs    - Each team owns their dependencies
- Cross-service changes are weekly     - Cross-service changes are monthly
- Teams frequently review each other   - Teams rarely interact on code
         ↓                                       ↓
    MONOREPO WINS                         POLYREPO WINS
```

**If you go monorepo — the non-negotiable investment:**

```
# You MUST have affected-only CI, or builds become unbearable

# With Nx (JavaScript/TypeScript):
npx nx affected --target=test  # Only test what changed

# With Pants (Python):
pants test ::  # Pants knows the dependency graph

# With Turborepo:
turbo run test --filter='...[origin/main]'

# WITHOUT these tools:
# Every PR runs ALL 8 services' tests → 45 min builds → everyone hates monorepo
```

```yaml
# .github/workflows/ci.yml — monorepo CI with path filtering
jobs:
  detect-changes:
    outputs:
      services: ${{ steps.changes.outputs.services }}
    steps:
      - uses: dorny/paths-filter@v3
        id: changes
        with:
          filters: |
            user-service: ['services/user/**', 'libs/shared/**']
            order-service: ['services/order/**', 'libs/shared/**']
            payment-service: ['services/payment/**', 'libs/shared/**']

  test:
    needs: detect-changes
    strategy:
      matrix:
        service: ${{ fromJson(needs.detect-changes.outputs.services) }}
    steps:
      - run: cd services/${{ matrix.service }} && pytest
```

**If you go polyrepo — the non-negotiable investment:**

```
# You MUST have shared tooling, or repos drift apart

# Shared CI templates (GitHub reusable workflows):
# .github/workflows/shared-test.yml in a central repo
# Each service repo references it:
jobs:
  test:
    uses: myorg/shared-workflows/.github/workflows/python-test.yml@v1

# Shared linting/formatting config:
# Central repo with pyproject.toml, .eslintrc, Dockerfile templates
# Each repo pulls from it (git submodule or package dependency)

# Dependency update automation:
# Renovate/Dependabot configured across ALL repos
# Central dashboard to track which repos are behind
```

**My recommendation for 4 teams, 8 services:**

```
If your services share significant code/schemas:
  → Monorepo with Nx/Pants/Turborepo
  → Platform team owns the build system
  → Teams get subdirectories with CODEOWNERS

If services are truly independent:
  → Polyrepo with shared CI templates
  → Central tooling repo for consistency
  → Invest in a service catalog (Backstage)

If you're unsure (most teams):
  → Start with monorepo
  → It's easier to split later than to merge later
  → The tooling investment pays for itself in cross-cutting changes
```

The honest truth: monorepo vs polyrepo is 20% technical, 80% organizational. The best choice is the one your teams will actually maintain the tooling for. A monorepo with bad CI is worse than polyrepo. A polyrepo with no shared standards drifts into chaos.'''
    ),
    (
        "thinking/multiperspective-api-pagination",
        "I need to add pagination to my REST API that returns a list of products. What's the best approach? I've seen offset/limit, cursor-based, and keyset pagination mentioned.",
        r'''<think>
Let me analyze pagination strategies from multiple perspectives: developer experience, database performance, user experience, consistency, and operational complexity.

Perspective 1: Frontend Developer (DX)
- Offset/limit: EASIEST
  - `GET /products?offset=20&limit=10` → page 3
  - Can jump to any page directly: "Go to page 7"
  - Simple to implement pagination controls (page 1, 2, 3... N)
  - Familiar from SQL: OFFSET 20 LIMIT 10
- Cursor-based: HARDER
  - `GET /products?cursor=eyJpZCI6MTAwfQ==&limit=10`
  - Can only go forward/backward (no "jump to page 7")
  - Must store opaque cursor from previous response
  - Harder to build page number navigation
- Keyset: MEDIUM
  - `GET /products?after_id=100&limit=10`
  - Similar to cursor but transparent (you can see it's id-based)
  - Still no random page access

Perspective 2: Database Performance (DBA)
- Offset/limit: BAD AT SCALE
  - `OFFSET 10000` means DB reads AND DISCARDS 10000 rows
  - Page 1 is fast, page 1000 is slow
  - O(offset + limit) for every query
  - With 1M products, page 100000 is unusable
- Cursor/keyset: CONSISTENTLY FAST
  - `WHERE id > 100 ORDER BY id LIMIT 10`
  - Uses index efficiently — reads exactly 10 rows
  - O(limit) regardless of which "page" you're on
  - Page 1 and page 100000 have identical performance

Perspective 3: Data Consistency (Architect)
- Offset/limit: INCONSISTENT
  - User is on page 5 (offset=40)
  - New product inserted at position 3
  - Page 5 now has different items — user might see duplicates or miss items
  - Especially bad for real-time data (feeds, transactions)
- Cursor/keyset: CONSISTENT
  - "Give me items after this one" — position is anchored to a specific record
  - Insertions/deletions don't cause duplicates or missed items
  - Crucial for financial data, audit logs, activity feeds

Perspective 4: Mobile/API Consumer Experience
- Offset/limit:
  - ✓ Simple to understand
  - ✗ Breaks with real-time data
  - ✗ No way to resume after app restart (offset is meaningless)
- Cursor-based:
  - ✓ "Load more" infinite scroll is natural
  - ✓ Resume from where you left off (store cursor)
  - ✗ No "jump to page" (but mobile rarely needs this)
  - ✓ What Facebook, Twitter, Stripe APIs all use

Perspective 5: Operational Complexity
- Offset/limit: SIMPLEST to implement, hardest to scale
- Cursor/keyset: Medium to implement, trivial to scale
- If sort order changes (sort by price instead of id), keyset becomes more complex
  - Need compound cursor: (price, id) for stable sort

My synthesis:
- Small dataset (<10K items) that rarely changes → offset/limit is fine
- Large dataset, real-time data, or API for mobile → cursor-based
- The "best" depends on: dataset size, update frequency, and UI requirements

For a product catalog:
- If it's a small shop (500 products): offset/limit, simple
- If it's a marketplace (1M products): cursor-based, necessary for performance
- If products update frequently (prices, stock): cursor avoids consistency bugs
</think>

Each pagination approach wins in different dimensions. Here's how they compare from every angle.

**The three approaches side by side:**

```python
# 1. Offset/Limit
GET /products?offset=20&limit=10
# SQL: SELECT * FROM products ORDER BY id LIMIT 10 OFFSET 20

# 2. Cursor-based
GET /products?cursor=eyJpZCI6MzB9&limit=10
# SQL: SELECT * FROM products WHERE id > 30 ORDER BY id LIMIT 10

# 3. Keyset (transparent cursor)
GET /products?after_id=30&limit=10
# SQL: same as cursor, but the parameter is readable
```

**Multi-perspective comparison:**

| Dimension | Offset/Limit | Cursor/Keyset |
|---|---|---|
| **Frontend DX** | Easy (page 1,2,3..N) | Harder (no page jumping) |
| **DB Performance** | Degrades with depth | Constant O(limit) |
| **Data consistency** | Duplicates/gaps on insert | Stable across changes |
| **Mobile/infinite scroll** | Awkward | Natural |
| **Implementation** | Trivial | Medium |
| **Sorting flexibility** | Any sort | Needs index-backed sort |

**When each wins:**

```
Offset/Limit:
  ✓ Admin dashboards with page numbers
  ✓ Small datasets (< 10K items)
  ✓ Static data (rarely inserted/deleted)
  ✓ When users need "jump to page 50"

Cursor-based:
  ✓ Public APIs (Stripe, GitHub, Slack all use this)
  ✓ Large datasets (100K+ items)
  ✓ Real-time data (feeds, transactions, logs)
  ✓ Mobile apps with infinite scroll
  ✓ When consistency matters
```

**Implementation — offset/limit (the simple case):**

```python
@app.get("/products")
def list_products(offset: int = 0, limit: int = Query(default=20, le=100)):
    products = (
        db.query(Product)
        .order_by(Product.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(func.count(Product.id)).scalar()

    return {
        "data": products,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + limit < total,
        },
    }
# Problem: at offset=100000, PostgreSQL reads 100000 rows then discards them
```

**Implementation — cursor-based (the scalable case):**

```python
import base64
import json

def encode_cursor(product_id: int) -> str:
    return base64.urlsafe_b64encode(
        json.dumps({"id": product_id}).encode()
    ).decode()

def decode_cursor(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor))

@app.get("/products")
def list_products(
    cursor: str = None,
    limit: int = Query(default=20, le=100),
):
    query = db.query(Product).order_by(Product.id)

    if cursor:
        decoded = decode_cursor(cursor)
        query = query.filter(Product.id > decoded["id"])

    products = query.limit(limit + 1).all()  # Fetch one extra to check has_more

    has_more = len(products) > limit
    if has_more:
        products = products[:limit]  # Remove the extra

    return {
        "data": products,
        "pagination": {
            "next_cursor": encode_cursor(products[-1].id) if has_more else None,
            "has_more": has_more,
            "limit": limit,
        },
    }
# Performance: WHERE id > X uses the primary key index — always fast
```

**Cursor with custom sorting (the tricky part):**

```python
# Sorting by price (non-unique field) requires a tiebreaker
@app.get("/products")
def list_products(
    cursor: str = None,
    sort_by: str = "price",
    limit: int = 20,
):
    query = db.query(Product)

    if cursor:
        decoded = decode_cursor(cursor)
        # Compound condition: (price, id) > (cursor_price, cursor_id)
        query = query.filter(
            or_(
                Product.price > decoded["price"],
                and_(
                    Product.price == decoded["price"],
                    Product.id > decoded["id"],  # Tiebreaker
                ),
            )
        )

    query = query.order_by(Product.price, Product.id)
    products = query.limit(limit + 1).all()

    has_more = len(products) > limit
    if has_more:
        products = products[:limit]

    next_cursor = None
    if has_more:
        last = products[-1]
        next_cursor = encode_cursor({"price": float(last.price), "id": last.id})

    return {
        "data": products,
        "pagination": {"next_cursor": next_cursor, "has_more": has_more},
    }

# Required index for performance:
# CREATE INDEX idx_products_price_id ON products(price, id);
```

**My recommendation for a product catalog:**

If you're building a public API or mobile app, use cursor-based. If it's an internal admin dashboard with page numbers, offset/limit is fine but add a maximum offset cap (e.g., `offset <= 10000`) to prevent performance problems.'''
    ),
    (
        "thinking/multiperspective-incident-response",
        "We had a production outage that took 4 hours to resolve. Leadership wants to make sure it doesn't happen again. How should we structure our incident response process?",
        r'''<think>
Let me analyze incident response from multiple stakeholder perspectives, because "don't let it happen again" means different things to different people.

Perspective 1: Engineering Team (the people who fix things)
Needs:
- Clear escalation path (who to call at 3am?)
- Runbooks for common failures (don't problem-solve under pressure)
- Access to production systems during incidents
- Blameless postmortem culture (fix systems, not blame people)
- Reduced alert fatigue (every page should be actionable)
Biggest fear: being blamed for an outage caused by systemic issues

Perspective 2: Engineering Management
Needs:
- MTTR metrics (mean time to recovery) — trending down
- Incident severity classification (not everything is P0)
- On-call rotation that doesn't burn out the team
- Postmortem action items that actually get completed
Biggest fear: repeated outages causing team attrition

Perspective 3: Product/Business Leadership
Needs:
- SLA/uptime numbers to report to customers/board
- Financial impact assessment of outages
- Confidence that "it won't happen again"
- Customer communication plan during outages
Biggest fear: losing customers/revenue/trust

Perspective 4: Customer Support
Needs:
- Real-time status updates to share with customers
- ETA for resolution (even rough estimates)
- Post-incident customer communication templates
- Knowledge of which customers are affected
Biggest fear: facing angry customers with no information

Perspective 5: SRE/Operations
Needs:
- Monitoring that catches issues before customers do
- Automated remediation for known failure modes
- Capacity planning data from incident trends
- Chaos engineering to find problems proactively
Biggest fear: alert storms with no clear priority

The key insight: the 4-hour MTTR breaks down into components:
- Time to detect (TTD): how long before someone noticed?
- Time to engage (TTE): how long to get the right person?
- Time to diagnose (TTDiag): how long to find the root cause?
- Time to fix (TTF): how long to implement and deploy the fix?

A 4-hour outage might have been: 45min to detect + 30min to engage + 2hr to diagnose + 45min to fix.
Each phase has different improvement levers.
</think>

A 4-hour outage isn't just a technical failure — it's a process failure at multiple stages. Let me break down what each stakeholder needs and give you a practical framework.

**First: decompose those 4 hours**

```
Most outages follow this timeline:

[--- Detect ---][--- Engage ---][--- Diagnose ---][--- Fix ---]
   ??? min          ??? min          ??? min         ??? min    = 4 hours

Ask your team: How much time was spent in each phase?
The longest phase is where you invest first.
```

**Phase 1: Detection — catch it before customers do**

```yaml
# Monitoring stack: metrics → alerts → on-call notification
# The 3 layers:

# Layer 1: Synthetic monitoring (catches outages in < 1 min)
- name: health-check
  url: https://api.myapp.com/health
  interval: 30s
  alert_if: status != 200 for 2 checks

# Layer 2: Business metric monitoring (catches degradation)
- name: order-rate-drop
  query: rate(orders_total[5m])
  alert_if: value < 50% of same_time_last_week
  # "Orders dropped by half" = something is very wrong

# Layer 3: Error rate monitoring (catches bugs)
- name: error-rate-spike
  query: rate(http_5xx_total[5m]) / rate(http_requests_total[5m])
  alert_if: value > 0.01 for 5m  # > 1% error rate
```

**Phase 2: Engagement — get the right person, fast**

```markdown
## On-Call Rotation
- Primary on-call: responds within 5 minutes
- Secondary on-call: backup if primary doesn't acknowledge in 10 min
- Escalation to engineering manager: after 15 min with no response

## Severity Levels (align expectations across stakeholders)
| Severity | Definition | Response Time | Who's Involved |
|----------|-----------|---------------|----------------|
| P0 | Service down, all users affected | 5 min | On-call + manager + all hands |
| P1 | Major feature broken, many users | 15 min | On-call + relevant team |
| P2 | Minor feature broken, workaround exists | 1 hour | On-call during business hours |
| P3 | Cosmetic or edge case | Next sprint | Ticket created |
```

```python
# PagerDuty/Opsgenie escalation policy (as code)
escalation_policy = {
    "name": "production-incidents",
    "rules": [
        {"delay_minutes": 0, "targets": ["primary-oncall"]},
        {"delay_minutes": 10, "targets": ["secondary-oncall"]},
        {"delay_minutes": 20, "targets": ["engineering-manager"]},
        {"delay_minutes": 30, "targets": ["vp-engineering"]},
    ],
}
```

**Phase 3: Diagnosis — runbooks eliminate guesswork**

```markdown
## Runbook: API Response Time > 5s

### Quick checks (do these first, < 5 minutes):
1. Check deployment: `Was there a deploy in the last hour?`
   - Yes → Rollback: `kubectl rollout undo deployment/api`
   - No → Continue

2. Check database: `SELECT count(*) FROM pg_stat_activity WHERE state = 'active';`
   - > 50 active queries → Check for lock contention or slow queries
   - Normal → Continue

3. Check resources: `kubectl top pods -n production`
   - CPU > 90% → Scale: `kubectl scale deployment/api --replicas=6`
   - Memory > 90% → Check for memory leak, restart pods

4. Check external dependencies:
   - Stripe status: https://status.stripe.com
   - AWS status: https://health.aws.amazon.com

### If none of the above: escalate to P0, pull in senior engineer
```

**Phase 4: Fix and Communicate**

```markdown
## During the incident:

### Internal communication (Slack #incidents channel)
Every 15 minutes, incident commander posts:
- Current status (investigating / identified / fixing / monitoring)
- What we know
- What we're trying next
- ETA (or "unknown")

### External communication (status page)
Template for customer support:
"We are currently experiencing [description]. Our team is actively
working on a resolution. We will provide updates every 30 minutes.
We apologize for the inconvenience."
```

**After the incident: Blameless postmortem**

```markdown
## Postmortem Template

### Summary
- Duration: 4 hours (14:00 - 18:00 UTC)
- Impact: 100% of users unable to place orders
- Root cause: Database migration took exclusive lock on orders table

### Timeline
- 14:00 - Deploy triggered migration
- 14:15 - First customer complaint to support
- 14:30 - On-call paged (detection took 30 min → FIX THIS)
- 14:45 - On-call engaged, began investigation
- 15:30 - Root cause identified (migration lock)
- 16:00 - Attempted rollback, failed (migration partially applied)
- 17:30 - Manual fix applied, service recovering
- 18:00 - Fully recovered

### 5 Whys
1. Why did the outage happen? → Migration locked the orders table
2. Why did the lock last so long? → Table has 10M rows, ALTER TABLE took hours
3. Why wasn't this caught? → No migration review process for large tables
4. Why did detection take 30 min? → No alert on order rate drop
5. Why couldn't we rollback quickly? → No tested rollback procedure for migrations

### Action Items (MUST have owners and deadlines)
| Action | Owner | Deadline | Status |
|--------|-------|----------|--------|
| Add order-rate-drop alert | @alice | Jan 15 | ✅ Done |
| Add migration size check to CI | @bob | Jan 20 | 🔄 In progress |
| Write runbook for DB lock issues | @charlie | Jan 25 | ⬜ Pending |
| Test rollback procedures monthly | @team | Ongoing | ⬜ Pending |
```

**The leadership answer:**

You can't promise "it won't happen again" — novel failures will always occur. What you CAN promise:
1. **Faster detection** — alerts catch issues in minutes, not when customers complain
2. **Faster resolution** — runbooks guide diagnosis, rollback is one command
3. **Continuous improvement** — every incident produces action items that prevent recurrence
4. **Measured progress** — track MTTR monthly, show it trending down

The goal isn't zero outages (impossible). It's reducing MTTR from 4 hours to 30 minutes, and ensuring the same root cause never causes an outage twice.'''
    ),
    (
        "thinking/multiperspective-database-migration",
        "We need to change a column type in our production database from VARCHAR(50) to VARCHAR(255). The table has 50 million rows and serves 500 requests/second. How do we do this safely?",
        r'''<think>
Let me analyze this from multiple perspectives because this seemingly simple change can cause a major outage if done wrong.

Perspective 1: DBA / Database Performance
- ALTER TABLE ... ALTER COLUMN on PostgreSQL:
  - Changing VARCHAR length to a LARGER value is actually safe in PostgreSQL!
  - PostgreSQL stores VARCHAR lengths as a constraint, not a physical format
  - `ALTER TABLE t ALTER COLUMN c TYPE VARCHAR(255)` — does NOT rewrite the table
  - This is nearly instant, just a metadata change
  - Wait... is this PostgreSQL or MySQL?
  - MySQL: ALTER TABLE DOES rewrite the entire table → hours-long operation → table locked
  - PostgreSQL >= 9.2: increasing VARCHAR size is metadata-only → instant
  - This distinction is CRITICAL

- But if they're on MySQL:
  - pt-online-schema-change or gh-ost needed
  - Creates shadow table, copies data, swaps names
  - Takes hours but doesn't lock the table

Perspective 2: Application Developer
- Is anything in the code assuming max 50 characters?
- Validation rules? Form inputs? API schemas?
- If we allow 255 chars but the frontend only shows 50 chars of space, UX breaks
- Need to update: input validation, API docs, frontend form lengths
- Also: if this is an indexed column, longer values = larger index = possibly slower queries

Perspective 3: Operations / SRE
- What's the rollback plan if something goes wrong?
- Can we test this on a staging environment with similar data volume?
- Need to coordinate: when? maintenance window or online?
- Monitor query performance before and after

Perspective 4: Product Owner
- Why do we need 255 chars? Is this a customer request?
- Could we solve the actual problem differently (separate field, text field)?
- What's the risk/benefit trade-off of this change?

Perspective 5: QA / Testing
- Need to test with maximum-length values (255 chars)
- Edge cases: exactly 50 chars (old limit), 51 chars (first new), 255 chars (new limit)
- Test all code paths that read/write this column

Let me give a practical answer that depends on the database:

For PostgreSQL: this is nearly instant and safe. Just do it.
For MySQL: this requires careful online schema migration.

I should cover both but ask which database they use.
</think>

This answer depends critically on your database. What seems like a simple change has very different risk profiles.

**If PostgreSQL — good news, this is nearly instant:**

```sql
-- PostgreSQL: Increasing VARCHAR length is a METADATA-ONLY change
-- Does NOT rewrite the table. Does NOT lock. Takes milliseconds.
ALTER TABLE products ALTER COLUMN name TYPE VARCHAR(255);
-- That's it. Safe to run during peak traffic.

-- Why? PostgreSQL stores VARCHAR as varlena — the length constraint
-- is just a check, not a physical storage format.
-- Going 50 → 255 just updates the constraint. Zero I/O.
```

```sql
-- VERIFY it won't rewrite (check for AccessExclusiveLock):
-- In a transaction, see the lock type:
BEGIN;
ALTER TABLE products ALTER COLUMN name TYPE VARCHAR(255);
SELECT mode FROM pg_locks WHERE relation = 'products'::regclass;
-- Should show: AccessExclusiveLock (but held for milliseconds)
COMMIT;
```

**If MySQL — this requires careful migration:**

```bash
# MySQL ALTER TABLE rewrites ALL 50M rows. On a live table:
# - Locks the table (or takes hours with ALGORITHM=INPLACE)
# - 500 req/s during rewrite = potential OOM or timeout cascade

# Option 1: gh-ost (GitHub's Online Schema Tool)
gh-ost \
  --host=db-primary \
  --database=myapp \
  --table=products \
  --alter="MODIFY COLUMN name VARCHAR(255)" \
  --execute \
  --allow-on-master \
  --chunk-size=1000 \
  --max-load="Threads_running=25"

# What gh-ost does:
# 1. Creates shadow table: _products_gho with new schema
# 2. Copies data in small chunks (1000 rows at a time)
# 3. Captures binlog events to keep shadow in sync
# 4. When done: atomic rename swap
# 5. Zero downtime, minimal performance impact

# Option 2: pt-online-schema-change (Percona)
pt-online-schema-change \
  --alter "MODIFY COLUMN name VARCHAR(255)" \
  D=myapp,t=products \
  --execute \
  --chunk-size=1000 \
  --max-lag=1
```

**Application-level changes (needed regardless of database):**

```python
# 1. Update validation BEFORE the migration
# (accept up to 255 chars even while DB still has 50 limit = harmless error)
class ProductSchema(BaseModel):
    name: str = Field(max_length=255)  # Was max_length=50

# 2. Update API documentation
# OpenAPI/Swagger will reflect the new max_length automatically

# 3. Check for any hardcoded assumptions
grep -rn "50" --include="*.py" | grep -i "name\|varchar\|max_len"
# Fix any: name[:50], truncation logic, test assertions
```

**From each perspective:**

```
DBA:
  PostgreSQL: "Just ALTER it. It's instant."
  MySQL: "Schedule gh-ost during low traffic. Monitor replication lag."

Developer:
  "Update all validation (API, frontend forms, tests) to allow 255."
  "Check indexes — if 'name' is indexed, verify performance doesn't degrade."

Ops:
  "Test on staging with 50M row copy first."
  "Monitor p99 latency during and after migration."
  "Have rollback ready: ALTER ... TYPE VARCHAR(50) (ensure no data > 50 chars first)"

QA:
  "Test with 51-char, 255-char, and empty inputs."
  "Verify display truncation in UI if needed."
```

**The safe execution order:**

```
1. Update application code to accept 255 chars (deploy first)
   → Old DB still limits to 50, but validation is ready

2. Run migration
   → PostgreSQL: instant ALTER
   → MySQL: gh-ost (may take hours, but online)

3. Verify
   → Insert a 100-char value, query it back
   → Check query performance on indexed lookups

4. Update frontend (if applicable)
   → Increase input field maxlength
   → Adjust display width/truncation
```

The key insight: in PostgreSQL, increasing VARCHAR length is not dangerous at all — it's a sub-second metadata change. In MySQL, it's a major operation requiring online schema change tooling. Know your database before planning.'''
    ),
    (
        "thinking/multiperspective-build-vs-buy-analytics",
        "We need an analytics dashboard for our SaaS product. Should we build our own or use a third-party tool like Mixpanel, Amplitude, or Metabase? Our team is 5 engineers.",
        r'''<think>
Let me analyze build vs buy for analytics from multiple perspectives.

Perspective 1: Engineering Team (builders)
Build:
- Full control over data model and queries
- Can customize exactly to our needs
- Fun/interesting technical challenge
- BUT: analytics is a solved problem — we'd be reinventing the wheel
- Time estimate: 2-4 months for MVP dashboard, ongoing maintenance forever
- That's 1-2 engineers (20-40% of the team!) dedicated to analytics infrastructure
Buy:
- Drop in a SDK, get dashboards immediately
- Focus engineering time on core product
- BUT: limited by what the tool offers (can't always get exact query we want)

Perspective 2: Product Manager
Build:
- Can get exactly the metrics and views we need
- No dependency on third-party roadmap
- BUT: every new chart/metric requires engineering time
Buy:
- Self-service: PM can create dashboards without engineers
- Pre-built funnels, cohort analysis, retention charts
- BUT: might not support our specific data model perfectly
- Mixpanel/Amplitude: event-based analytics (user behavior)
- Metabase: SQL-based analytics (business metrics)
- These are very different tools for different needs!

Perspective 3: Finance/Business
Build:
- No recurring subscription cost
- BUT: engineering salaries are $150K+, 2 months of 1 engineer = $25K in salary
- Plus ongoing maintenance: $10K+/year in engineer time
Buy:
- Mixpanel: $0-$25K/year depending on volume
- Metabase: free (self-hosted) or $85/user/month (cloud)
- Amplitude: $0-$50K/year
- Clear, predictable cost
- ROI: if it saves even 1 engineer-month/year, it's worth it

Perspective 4: Data Privacy/Security
Build:
- Data stays in our systems
- Full control over data retention and deletion
- Easier GDPR compliance (no third-party data sharing)
Buy:
- Data sent to third-party servers (Mixpanel, Amplitude)
- Must review their DPA and security practices
- Some customers (enterprise, healthcare) may object to third-party analytics
- Self-hosted options (Metabase, PostHog) mitigate this

Perspective 5: Growth/Scale
Build:
- Must scale infrastructure ourselves (Elasticsearch, ClickHouse, etc.)
- At high volume (millions of events/day), this is a real engineering challenge
Buy:
- Handles scaling for us (that's what we're paying for)
- BUT: costs scale with data volume — can get expensive at scale

My synthesis for a 5-person team:
- 5 engineers is SMALL. Dedicating 1-2 to build analytics = 20-40% of capacity
- The opportunity cost is enormous — what features WON'T you build?
- Buy for now, build later IF the third-party tool becomes a bottleneck

The nuance: WHAT kind of analytics?
- User behavior (funnels, retention, A/B tests) → Mixpanel/Amplitude/PostHog
- Business metrics (revenue, SQL queries) → Metabase/Redash on your own DB
- Product analytics + privacy concerns → PostHog (self-hosted)

Best for a 5-person team: PostHog (self-hosted, free tier, covers both product analytics and business metrics) or Metabase (free, self-hosted, SQL-based) + a simple event tracker.
</think>

With 5 engineers, this isn't really a build-vs-buy question — it's a "what should you NOT build" question. Let me break it down.

**The cost calculation that settles most debates:**

```
Building analytics in-house:
  2 months to MVP × 1 engineer           = $25K in salary
  Ongoing maintenance: 20% of 1 engineer  = $30K/year
  Infrastructure (ClickHouse, etc.)       = $5K/year
  Total Year 1: ~$60K
  Total Year 2: ~$35K
  + Opportunity cost: features you DIDN'T build

Buying:
  PostHog (self-hosted): $0
  Metabase (self-hosted): $0
  Mixpanel: $0-25K/year
  Amplitude: $0-50K/year
  Setup time: 1-3 days
  Maintenance: ~0
```

**From each perspective:**

| Stakeholder | Build | Buy | Verdict |
|---|---|---|---|
| **Engineers (5 total)** | Fun but 20-40% of team capacity | 1 day integration | Buy — you can't spare 1-2 engineers |
| **Product Manager** | Custom but requires eng for every chart | Self-service dashboards | Buy — PM independence is huge |
| **Finance** | $60K yr1 + opportunity cost | $0-25K/year | Buy — cheaper AND faster |
| **Security/Privacy** | Data stays internal | Data to 3rd party (or self-host) | Tie — PostHog self-hosted wins |
| **Scale** | Must build infrastructure | Handled for you | Buy — until very high volume |

**My recommendation for a 5-person team:**

```
Tier 1 (do this today, free):
  Metabase (self-hosted) on your existing PostgreSQL
  → SQL-based dashboards for business metrics
  → Revenue, signups, churn, active users
  → Anyone who knows SQL can build dashboards

Tier 2 (add when you need product analytics):
  PostHog (self-hosted) — open source, free
  → Funnels, session replay, feature flags, A/B tests
  → Drop-in JavaScript SDK
  → Data stays on your servers (privacy win)

Tier 3 (only if you outgrow the above):
  Build custom analytics on ClickHouse
  → When you have 100M+ events/day
  → When you need analysis that no tool provides
  → When you have a dedicated data team (not at 5 engineers)
```

**Quick setup — Metabase in 5 minutes:**

```yaml
# docker-compose.yml — add to your existing stack
services:
  metabase:
    image: metabase/metabase:latest
    ports: ["3000:3000"]
    environment:
      MB_DB_TYPE: postgres
      MB_DB_HOST: your-db-host
      MB_DB_PORT: 5432
      MB_DB_DBNAME: myapp  # Point at your existing database
      MB_DB_USER: metabase_readonly  # Read-only user!
      MB_DB_PASS: ${METABASE_DB_PASSWORD}
```

```sql
-- Create a read-only user for Metabase (security best practice)
CREATE USER metabase_readonly WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE myapp TO metabase_readonly;
GRANT USAGE ON SCHEMA public TO metabase_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_readonly;
```

**Quick setup — PostHog for product analytics:**

```bash
# Self-hosted PostHog
git clone https://github.com/PostHog/posthog.git
cd posthog
docker compose -f docker-compose.hobby.yml up -d
```

```javascript
// Frontend integration (2 lines):
posthog.init('your-project-key', { api_host: 'https://posthog.yourdomain.com' });

// Track events:
posthog.capture('order_completed', { amount: 49.99, items: 3 });
posthog.capture('feature_used', { feature: 'dark_mode' });
```

**When to reconsider building:**

```
✗ "We need a custom chart" → Metabase supports custom SQL queries
✗ "We need real-time" → PostHog has live dashboards
✗ "We need ML-based cohorts" → Amplitude does this out of the box

✓ "We need to join analytics with ML model output" → Maybe build
✓ "We process 500M events/day" → Outgrow hosted tools, consider building
✓ "We have a 3-person data team" → Now you have capacity to build
```

For 5 engineers building a SaaS product: buy (or self-host free tools). Every hour spent building analytics is an hour NOT spent on the product your customers pay for.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
