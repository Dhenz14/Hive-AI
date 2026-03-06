"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 2/4)
Database schema design, test coverage targets, dependency management,
microservice boundaries, technical debt decisions."""

PAIRS = [
    (
        "thinking/multiperspective-db-schema",
        "We're designing the schema for an e-commerce product catalog. Products can have variants (size, color), belong to multiple categories, have dynamic attributes (electronics have 'battery life', clothing has 'material'), and support multiple currencies. How should we model this?",
        r'''<think>
Let me evaluate from multiple perspectives:

QUERY PERFORMANCE:
- Product listing pages need: name, price, image, category → frequently joined
- Product detail needs: all attributes, variants, reviews → deep fetches
- Search/filter needs: filter by any attribute → EAV is slow for this
- Category browsing: products in category X → many-to-many join

DATA INTEGRITY:
- Prices must be consistent (no $-1 products)
- Variants must reference valid products
- Categories should form a valid tree/DAG
- Dynamic attributes need type validation

FLEXIBILITY:
- New product types = new attributes (can't ALTER TABLE every time)
- New categories appear frequently
- New currencies for international expansion
- Marketing wants to add custom fields without engineering

DEVELOPER EXPERIENCE:
- ORM compatibility: how well does this map to Django/SQLAlchemy models?
- Query complexity: can a junior dev write correct queries?
- Migration complexity: how painful are schema changes?

SCALABILITY:
- Product count: 100K now, 10M eventually?
- Query volume: how many reads vs writes?
- Full-text search needs: will PostgreSQL FTS suffice or need Elasticsearch?

TENSIONS:
- Flexibility (EAV/JSONB) vs Query Performance (normalized)
- Normalization (data integrity) vs Read Speed (denormalization)
- ORM-friendly schema vs Optimal SQL schema
</think>

**Multi-perspective analysis — there's no single "right" schema:**

**QUERY PERFORMANCE perspective** (what will be fast/slow):
```sql
-- Products table: the core, optimized for listing pages
CREATE TABLE products (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    product_type VARCHAR(50) NOT NULL,  -- 'electronics', 'clothing', etc.
    base_price_cents INTEGER NOT NULL,  -- Store in cents (no float!)
    currency VARCHAR(3) DEFAULT 'USD',
    primary_image_url VARCHAR(500),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- JSONB for dynamic attributes (flexibility + queryable)
    attributes JSONB DEFAULT '{}',
    -- Electronics: {"battery_life": "8h", "weight_grams": 340}
    -- Clothing: {"material": "cotton", "care": "machine wash"}
    -- No ALTER TABLE needed for new product types!
);

-- GIN index on JSONB — makes attribute queries fast
CREATE INDEX idx_products_attributes ON products USING GIN (attributes);
-- Query: WHERE attributes->>'material' = 'cotton'

-- Variants: size/color combinations
CREATE TABLE product_variants (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT REFERENCES products(id) ON DELETE CASCADE,
    sku VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255),  -- "Large / Blue"
    price_cents_override INTEGER,  -- NULL = use base price
    stock_quantity INTEGER DEFAULT 0,
    attributes JSONB DEFAULT '{}',  -- {"size": "L", "color": "blue"}
    is_active BOOLEAN DEFAULT true
);
CREATE INDEX idx_variants_product ON product_variants(product_id);

-- Categories: many-to-many with hierarchy
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES categories(id),
    sort_order INTEGER DEFAULT 0,
    -- Materialized path for efficient tree queries
    path LTREE  -- PostgreSQL ltree extension: 'root.electronics.phones'
);
CREATE INDEX idx_categories_path ON categories USING GIST (path);

CREATE TABLE product_categories (
    product_id BIGINT REFERENCES products(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (product_id, category_id)
);

-- Multi-currency pricing
CREATE TABLE product_prices (
    product_id BIGINT REFERENCES products(id) ON DELETE CASCADE,
    currency VARCHAR(3) NOT NULL,
    price_cents INTEGER NOT NULL,
    PRIMARY KEY (product_id, currency)
);
```

**FLEXIBILITY perspective** (JSONB vs EAV vs wide table):
```
Approach        | Add new attribute | Query by attribute | ORM friendly | Type safety
JSONB column    | Instant (no DDL)  | Fast (GIN index)   | Moderate     | None (runtime)
EAV table       | Instant (no DDL)  | Slow (pivot query) | Poor         | None
Wide table      | ALTER TABLE       | Fast (column index)| Excellent    | Strong
Type-specific   | New table         | Fast               | Good         | Strong

Winner for dynamic product attributes: JSONB
  → No schema change for new product types
  → Queryable with GIN indexes
  → PostgreSQL validates JSON structure
  → Can add JSON Schema validation for type safety
```

**DATA INTEGRITY perspective** (what could go wrong):
```sql
-- Constraint: price must be positive
ALTER TABLE products ADD CONSTRAINT chk_price_positive CHECK (base_price_cents > 0);
ALTER TABLE product_variants ADD CONSTRAINT chk_variant_price CHECK (price_cents_override > 0 OR price_cents_override IS NULL);

-- Constraint: validate JSONB attributes per product type
-- Use a trigger or application-level validation:
CREATE OR REPLACE FUNCTION validate_product_attributes()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.product_type = 'electronics' THEN
        IF NOT (NEW.attributes ? 'weight_grams') THEN
            RAISE EXCEPTION 'Electronics must have weight_grams attribute';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_attributes
BEFORE INSERT OR UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION validate_product_attributes();
```

**The key tension resolution**:
```
Tension: Flexibility vs Performance vs Integrity

Resolution: HYBRID approach
  Core fields (name, price, status) → COLUMNS (fast, typed, indexed)
  Dynamic fields (attributes)       → JSONB (flexible, queryable)
  Relationships (categories)        → NORMALIZED TABLES (integrity)
  Search/filter                     → DENORMALIZED VIEW or search index

This gives 80% of each benefit without 100% of any downside.
```'''
    ),
    (
        "thinking/multiperspective-tech-debt",
        "Our tech lead says we need to spend 2 sprints paying down technical debt before building new features. The PM says we can't afford to stop shipping for a month. Who's right?",
        r'''<think>
Both have valid points. Let me analyze from multiple perspectives:

BUSINESS perspective (PM's view):
- Revenue depends on new features
- Competitors are shipping while we pause
- Customers don't see "tech debt reduction" as value
- 2 sprints (1 month) of zero features is a hard sell to stakeholders
- Every sprint without features = potential customer churn
- Valid concern: stopping all feature work is risky

ENGINEERING perspective (tech lead's view):
- Tech debt is slowing down feature development
- Bugs from tech debt cost engineering time
- Developer morale suffers when codebase is painful
- The debt compounds: every feature built on bad foundations makes it worse
- Eventually, velocity drops to near-zero
- Valid concern: not addressing debt will kill velocity long-term

WHAT I'M UNCERTAIN ABOUT:
- How bad is the tech debt really? "We need 2 sprints" is vague.
  - Is it "tests are slow" or "the whole architecture is wrong"?
  - Different debts have different payoff curves
- Is the PM's deadline real or artificial?
- What's the team's current velocity? Has it been declining?
- Can the team handle the context switch between debt and features?

COMPROMISE approaches:
1. 20% rule: 20% of each sprint = tech debt (continuous)
2. Prioritize by ROI: fix the debt that slows features the MOST
3. "Boy scout rule": improve code you touch while building features
4. Tech debt sprint every quarter (not all at once)
5. Embed debt work IN feature work (refactor as part of the feature)
</think>

**Both are partially right. The answer is neither "stop everything" nor "ignore the debt."**

**The false dichotomy**:
```
Tech Lead's plan:    2 sprints of pure debt work → 1 month zero features
PM's alternative:    Ignore debt → velocity keeps declining

Neither is optimal.

Better: continuous debt reduction embedded in feature work.
```

**Multi-perspective analysis**:

```
BUSINESS LENS (PM is right that...):
────────────────────────────────────
- 1 month of zero features IS risky for a competitive product
- Customers don't see "cleaner code" as value
- Tech debt work often takes longer than estimated (scope creep)
- The team may lose momentum after a month of refactoring

ENGINEERING LENS (Tech Lead is right that...):
──────────────────────────────────────────────
- Compounding debt eventually stops feature development entirely
- Developers working in painful code = slower, buggier, demoralized
- "We'll fix it later" is a lie teams tell themselves
- Some debt genuinely blocks feature development

DATA YOU NEED:
──────────────
□ Has sprint velocity been declining? (trend line)
□ What % of sprints are spent on bug fixes from tech debt?
□ Which specific debt items block which upcoming features?
□ What's the estimated velocity improvement from fixing each item?
```

**The approach I'd recommend (80% confident)**:

```python
# Step 1: Categorize tech debt by ROI, not by "how bad it is"
tech_debt_items = [
    {
        "item": "Migrate from callbacks to async/await",
        "effort_days": 10,
        "velocity_improvement": "20% faster feature dev",
        "blocks_features": ["real-time notifications", "bulk import"],
        "roi": "HIGH",  # High improvement, blocks features
    },
    {
        "item": "Rewrite ORM queries to raw SQL",
        "effort_days": 15,
        "velocity_improvement": "5% faster feature dev",
        "blocks_features": [],
        "roi": "LOW",  # Lots of effort, minimal impact
    },
    {
        "item": "Add CI/CD pipeline",
        "effort_days": 3,
        "velocity_improvement": "30% faster deployments",
        "blocks_features": [],
        "roi": "VERY HIGH",  # Low effort, high impact
    },
    {
        "item": "Refactor database schema",
        "effort_days": 20,
        "velocity_improvement": "15% faster feature dev",
        "blocks_features": ["multi-tenancy", "data export"],
        "roi": "MEDIUM",  # High effort, medium impact
    },
]

# Step 2: Do HIGH ROI items first, embedded in sprint work
# Sprint plan: 80% features, 20% debt (not separate sprints)

# Step 3: Attach debt work TO feature work where possible
# "Build real-time notifications" naturally includes "migrate to async/await"
# The feature justifies the refactoring — PM sees it as feature work, eng sees it as debt work
```

**The compromise that usually works**:
```
Sprint 1:  3 days CI/CD pipeline (VERY HIGH ROI) + normal features
Sprint 2:  Async migration (included in notification feature work)
Sprint 3:  Normal features + boy scout rule (improve what you touch)
Sprint 4:  Normal features + 2 days schema improvements
Sprint 5:  Tech debt review — has velocity improved?

Result: Continuous improvement without stopping feature development.
The PM gets features every sprint. The tech lead gets debt reduction.
Nobody gets everything they want. That's compromise.
```

**When to actually stop everything for debt** (the 10% case):
```
□ Velocity has dropped 50%+ in the last 3 months (measurable decline)
□ The team literally cannot build the next feature on the current codebase
□ Security vulnerabilities that can't be patched without refactoring
□ Regulatory deadline that requires architectural changes
```'''
    ),
    (
        "thinking/multiperspective-dependency-mgmt",
        "We're debating whether to pin our dependencies to exact versions (==1.2.3) or use ranges (>=1.2,<2.0). The security team wants the latest patches, but the dev team wants reproducible builds. What's the right approach?",
        r'''<think>
Let me analyze from both sides:

SECURITY perspective (wants latest):
- Security patches are released as minor/patch versions
- Pinning to ==1.2.3 means you miss 1.2.4 which fixes a CVE
- Every day you run an unpatched version = exposure window
- Automated tools (Dependabot, Renovate) can help but need reviews
- Supply chain attacks are real (typosquatting, malicious updates)

STABILITY perspective (wants pinning):
- An unexpected update can introduce breaking changes
- Even "patch" versions sometimes break (semver violations)
- If tests pass locally but CI installs a different version → flaky builds
- "It worked yesterday, what changed?" → dependency update
- Production incidents from unexpected dependency changes are common

The answer depends on:
1. Application vs Library (different rules!)
2. How good their test coverage is
3. Whether they have CI/CD
4. How critical the application is

For APPLICATIONS: pin everything (lockfile). Update deliberately.
For LIBRARIES: use ranges. Don't force your consumers onto specific versions.
</think>

**Both teams are right for different reasons. The answer depends on whether you're building an APPLICATION or a LIBRARY.**

**Applications (your deployed service): PIN everything**:
```toml
# pyproject.toml — specify ranges for flexibility
[project]
dependencies = [
    "fastapi>=0.100,<1.0",
    "sqlalchemy>=2.0,<3.0",
    "pydantic>=2.0,<3.0",
]

# poetry.lock / requirements.txt — pin EXACT versions for reproducibility
# This file is auto-generated and committed to git
fastapi==0.109.2
sqlalchemy==2.0.27
pydantic==2.6.1
httpx==0.27.0
uvicorn==0.27.1
# ... every transitive dependency pinned too
```

```
Why: Reproducible builds. The same code + same lockfile = same behavior.
The lockfile gives you stability. Update it DELIBERATELY with testing.
```

**Libraries (package others install): USE RANGES**:
```toml
# If you're publishing a library to PyPI
[project]
dependencies = [
    "requests>=2.25,<3.0",  # Range — don't force consumers onto exact version
]
# NO lockfile published — consumers resolve their own dependencies
```

```
Why: If your library pins requests==2.28 and another library pins requests==2.31,
the consumer gets a dependency conflict. Ranges avoid this.
```

**The security + stability compromise**:
```python
# STRATEGY: Pin in lockfile + automated update PRs + CI tests

# 1. Lockfile committed to git (stability)
# Every build uses identical dependencies

# 2. Dependabot/Renovate creates weekly PRs (security)
# Automatically proposes updates with changelogs

# 3. CI runs full test suite on update PRs (safety)
# If tests pass → merge. If tests fail → review the breaking change.

# 4. Monthly security audit (compliance)
# pip-audit or safety check for known CVEs

# GitHub Actions example:
# .github/dependabot.yml
# version: 2
# updates:
#   - package-ecosystem: "pip"
#     directory: "/"
#     schedule:
#       interval: "weekly"
#     open-pull-requests-limit: 10
```

**Perspective tensions resolved**:
```
Security team wants:     Dev team wants:          Resolution:
──────────────────────   ──────────────────────   ──────────────────────
Latest patches always    Reproducible builds      Lockfile + weekly update PRs
                                                  Tests gate every update

Auto-update in prod      No surprises             Updates only through CI/CD
                                                  Never auto-deploy without tests

Audit every dependency   Don't slow development   Automated pip-audit in CI
                                                  Flag CVEs, don't block all PRs
```

**The 4 rules that satisfy both teams**:
```
1. Always use a lockfile (pip freeze, poetry.lock, package-lock.json)
2. Never manually edit the lockfile — use tooling to update
3. Every dependency update goes through CI before merge
4. Run security audits weekly (pip-audit, npm audit)
```'''
    ),
    (
        "thinking/multiperspective-code-review-depth",
        "Our code reviews are taking too long — PRs sit for 2-3 days before getting reviewed, and reviewers leave 50+ comments. Developers are frustrated. Should we lower our review standards to move faster?",
        r'''<think>
This is a genuine tension between quality and velocity. Let me analyze from multiple angles.

QUALITY perspective:
- Thorough reviews catch bugs before production
- Reviews share knowledge across the team
- Reviews enforce coding standards
- 50+ comments might indicate real quality issues
- Lowering standards = more bugs in production

VELOCITY perspective:
- 2-3 day review cycles = features ship a week late
- Developers context-switch away from PRs while waiting
- Review feedback requires rework, extending the cycle further
- Frustration = lower morale = lower productivity
- "Perfectionist" reviews block incremental progress

TEAM DYNAMICS:
- 50+ comments might be nitpicking (style, naming) vs substantial (logic, security)
- Some reviewers might be gatekeeping or showing off
- Author might not be addressing known issues before requesting review
- Large PRs are inherently harder to review

The real question isn't "should we lower standards" — it's:
1. Are the 50 comments SUBSTANTIVE or NITPICKY?
2. Are the PRs too LARGE?
3. Is the review process EFFICIENT?

The solution is usually: smaller PRs + automated style checks + prioritized review focus.
</think>

**Don't lower standards — make reviews more efficient.** 50 comments and 2-3 day delays usually indicate process problems, not quality problems.

**Diagnose the real issue first**:
```
If 50 comments are mostly about...    Then the fix is...
────────────────────────────────      ──────────────────────────
Style (naming, formatting, imports)   Automate with linters/formatters
Nitpicks (optional improvements)      Differentiate "must fix" vs "nit"
Real bugs and logic issues            PRs are too large — break them up
Architectural disagreements           Discuss design BEFORE coding
Knowledge sharing ("FYI" comments)    Use a separate review channel
```

**5 fixes that reduce review time without reducing quality**:

```python
# FIX 1: Automate style enforcement (eliminates 30-60% of comments)
# pyproject.toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]

[tool.black]
line-length = 100

# CI blocks PRs that fail formatting/linting
# Zero human time spent on style comments

# FIX 2: Categorize comments (not all comments are equal)
# Convention:
# "nit: consider renaming this" → optional, author's choice
# "suggestion: this could use a set for O(1) lookup" → recommended
# "blocker: this has a SQL injection vulnerability" → must fix
# Only BLOCKERS prevent merge. Nits and suggestions are author's choice.

# FIX 3: Smaller PRs (most impactful change)
# Before: 1 PR with 500 lines, 50 comments, 3 days to review
# After: 3 PRs with ~150 lines each, 5-10 comments each, reviewed in hours

# PR size → review time (approximately):
# < 100 lines:  15 min review, same-day approval
# 100-300 lines: 30-60 min review, next-day approval
# 300-500 lines: 2+ hours, 2-3 day cycle
# 500+ lines:   Nobody reviews thoroughly, rubber-stamp risk

# FIX 4: Review SLA (set expectations)
# Agreement: reviews completed within 4 business hours
# If reviewer is blocked, tag a backup reviewer
# Track review time as a team metric

# FIX 5: Self-review checklist (author catches own issues)
PR_CHECKLIST = """
Before requesting review, verify:
□ I've reviewed my own diff (caught obvious issues)
□ Tests pass locally and in CI
□ Linter/formatter has been run
□ PR description explains WHY, not just WHAT
□ PR is under 300 lines (if larger, explain why or split)
□ No debug code, console.log, or TODO comments
"""
```

**The tension resolution**:
```
QUALITY advocates say:              VELOCITY advocates say:
"Thorough reviews prevent bugs"     "3-day cycles kill momentum"

RESOLUTION:
→ Automate the easily-automatable (style, formatting)
→ Focus human review on logic, security, architecture
→ Make PRs small enough to review in 30 minutes
→ Set a review SLA (4 hours, not 3 days)
→ Categorize comments (blocker vs nit)
→ Result: FASTER reviews that catch MORE important issues
          because reviewers aren't wasting time on formatting
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
