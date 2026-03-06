"""Phase 4F: Self-Improvement — Quality Assurance (Part 1)"""

PAIRS = [
    (
        "thinking/auto-qa-code-checklist",
        r'''Before sending this Python function, run it through my quality checklist:

def calculate_discount(price, customer_type, loyalty_years):
    if customer_type == "premium":
        discount = 0.2
    elif customer_type == "standard":
        discount = 0.1
    else:
        discount = 0
    if loyalty_years > 5:
        discount += 0.05
    if loyalty_years > 10:
        discount += 0.05
    final_price = price - (price * discount)
    return final_price''',
        r'''<think>
Let me run this function through a structured code quality checklist.

1. CORRECTNESS
- Logic: Premium gets 20%, standard 10%, else 0%. Loyalty >5 adds 5%, >10 adds another 5%. So max discount is 30%. That seems intentional but I should flag: a customer with >10 years gets BOTH the >5 and >10 bonuses (total 10% extra). Is that intended? It appears so since the conditions are not elif.
- Edge cases: What if price is negative? No guard. What if loyalty_years is negative? No guard. What if customer_type is None? Falls to else branch, gets 0 — acceptable but silent.
- Discount could theoretically exceed 1.0 if someone added more tiers carelessly. No cap.

2. TYPE SAFETY
- No type hints on return value. Parameters lack validation. price could be a string and would crash at the multiplication step with a confusing error.

3. NAMING AND READABILITY
- Function name is clear. Parameter names are descriptive. Variable names are good.
- Magic numbers: 0.2, 0.1, 0.05, 5, 10 are all unnamed constants.

4. ERROR HANDLING
- No input validation at all. No exceptions raised for bad inputs.

5. TESTABILITY
- Pure function with no side effects — good. Easy to test.
- But no docstring explaining the discount rules.

6. PERFORMANCE
- Simple arithmetic, no issues.

Issues found: missing type hints, no input validation, magic numbers, no docstring, no discount cap.
</think>

**Code Quality Checklist Report**

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | Correctness | PASS (with note) | Logic works but loyalty bonuses stack (>10yr gets both +5% bonuses). Confirm this is intentional. |
| 2 | Type safety | FAIL | No type hints on return. No runtime validation of inputs. Passing `price="50"` would crash with an unhelpful TypeError at the multiplication line. |
| 3 | Edge case handling | FAIL | Negative prices produce negative discounts (price increases). Negative loyalty years are silently accepted. No guard rails. |
| 4 | Naming/readability | PASS (with note) | Names are clear, but magic numbers (0.2, 0.1, 0.05, 5, 10) should be named constants like `PREMIUM_DISCOUNT_RATE`. |
| 5 | Documentation | FAIL | No docstring. The stacking loyalty bonus logic is non-obvious and must be documented. |
| 6 | Error handling | FAIL | No validation, no custom exceptions. Unknown customer types silently get zero discount instead of raising an error. |
| 7 | Testability | PASS | Pure function, no side effects, easy to unit test. |
| 8 | Performance | PASS | Simple arithmetic, O(1). |
| 9 | Security | PASS | No injection vectors in a pure calculation. |
| 10 | Maintainability | FAIL | Magic numbers and implicit stacking logic make future changes error-prone. |

**Score: 5/10** — Functionally correct for happy paths but missing defensive coding practices.

**Recommended fixes before sending:**

```python
PREMIUM_DISCOUNT = 0.20
STANDARD_DISCOUNT = 0.10
LOYALTY_TIER1_BONUS = 0.05  # >5 years
LOYALTY_TIER2_BONUS = 0.05  # >10 years
MAX_DISCOUNT = 0.30

def calculate_discount(price: float, customer_type: str, loyalty_years: int) -> float:
    """Calculate discounted price based on customer tier and loyalty.

    Discounts stack: base tier rate + loyalty bonuses (capped at 30%).
    """
    if not isinstance(price, (int, float)) or price < 0:
        raise ValueError(f"Price must be a non-negative number, got {price}")
    if loyalty_years < 0:
        raise ValueError(f"Loyalty years must be non-negative, got {loyalty_years}")

    base_discounts = {"premium": PREMIUM_DISCOUNT, "standard": STANDARD_DISCOUNT}
    if customer_type not in base_discounts:
        raise ValueError(f"Unknown customer type: {customer_type!r}")

    discount = base_discounts[customer_type]
    if loyalty_years > 5:
        discount += LOYALTY_TIER1_BONUS
    if loyalty_years > 10:
        discount += LOYALTY_TIER2_BONUS

    discount = min(discount, MAX_DISCOUNT)
    return round(price * (1 - discount), 2)
```'''
    ),
    (
        "thinking/auto-qa-api-checklist",
        r'''Before presenting this API design, verify it against REST best practices:

POST /api/getUsers          — fetch all users
POST /api/deleteUser/123    — delete a user
GET  /api/user/create?name=John&email=john@example.com — create user
PUT  /api/users/123         — full update
GET  /api/users/123/orders  — get user's orders
POST /api/searchOrders      — search with body params''',
        r'''<think>
Let me apply a REST API quality checklist to each endpoint.

Checklist categories:
1. HTTP method correctness (GET for reads, POST for creates, PUT/PATCH for updates, DELETE for deletes)
2. URI naming (nouns not verbs, plural resources, lowercase, hyphens not camelCase)
3. Resource hierarchy (proper nesting)
4. Idempotency expectations
5. Status code conventions
6. Query params vs body usage

Evaluating each endpoint:

POST /api/getUsers — MULTIPLE VIOLATIONS. Using POST for a read operation (should be GET). Verb in URI ("get"). Should be GET /api/users.

POST /api/deleteUser/123 — MULTIPLE VIOLATIONS. Using POST for deletion (should be DELETE). Verb in URI ("delete"). Singular noun. Should be DELETE /api/users/123.

GET /api/user/create?name=John&email=john@example.com — SEVERE VIOLATIONS. Using GET for a create operation (should be POST). Verb in URI ("create"). Sensitive data in query string (email visible in logs). Singular noun. Not idempotent despite using GET. Should be POST /api/users with JSON body.

PUT /api/users/123 — CORRECT. Proper method, plural noun, resource identifier.

GET /api/users/123/orders — CORRECT. Proper nesting, GET for read, plural nouns.

POST /api/searchOrders — DEBATABLE. Search with complex body params is a common REST compromise. camelCase violates conventions though. Better: GET /api/orders?search=... or POST /api/orders/search if body is complex.
</think>

**REST API Quality Checklist Report**

| # | Endpoint | Method | URI | Severity |
|---|----------|--------|-----|----------|
| 1 | `POST /api/getUsers` | FAIL — use GET | FAIL — verb in URI | Critical |
| 2 | `POST /api/deleteUser/123` | FAIL — use DELETE | FAIL — verb, singular | Critical |
| 3 | `GET /api/user/create?name=...` | FAIL — use POST | FAIL — verb, singular, data in URL | Critical |
| 4 | `PUT /api/users/123` | PASS | PASS | None |
| 5 | `GET /api/users/123/orders` | PASS | PASS | None |
| 6 | `POST /api/searchOrders` | Acceptable | FAIL — camelCase | Minor |

**Detailed findings:**

**Critical: Endpoints 1-3 violate fundamental REST semantics.** The design uses HTTP methods as mere transport, ignoring their semantic meaning. GET must be safe (no side effects), POST should create resources, DELETE should remove them.

**Critical: GET with creation side effects (endpoint 3)** is the most dangerous issue. Browser prefetch, crawlers, and caching proxies will all replay GET requests, potentially creating duplicate users. Sensitive data (email) in query strings gets logged by proxies, web servers, and browser history.

**Corrected API design:**

```
GET    /api/users              — list all users (with pagination)
POST   /api/users              — create a user (JSON body)
GET    /api/users/123          — get single user
PUT    /api/users/123          — full update of user
PATCH  /api/users/123          — partial update of user
DELETE /api/users/123          — delete user
GET    /api/users/123/orders   — list user's orders (unchanged)
GET    /api/orders?q=keyword   — search orders (simple filters)
POST   /api/orders/search      — search orders (complex body)
```

**Additional recommendations:** Add `Accept: application/json` headers, version the API (`/api/v1/`), use proper HTTP status codes (201 for creation, 204 for deletion), and implement pagination with `Link` headers for list endpoints.

**Score: 3/10** — Two of six endpoints are correct. Fundamental REST principles are misunderstood in the original design.'''
    ),
    (
        "thinking/auto-qa-schema-checklist",
        r'''Before recommending this database schema, check it against normalization rules:

CREATE TABLE orders (
    id INT PRIMARY KEY,
    customer_name VARCHAR(100),
    customer_email VARCHAR(100),
    customer_address VARCHAR(255),
    product_name VARCHAR(100),
    product_price DECIMAL(10,2),
    product_category VARCHAR(50),
    quantity INT,
    order_date DATE,
    total_price DECIMAL(10,2),
    discount_percent DECIMAL(5,2),
    discounted_total DECIMAL(10,2)
);''',
        r'''<think>
Let me check this schema against normalization rules systematically.

1NF — First Normal Form:
- All columns are atomic (single values)? Yes, each column holds a single value.
- Primary key exists? Yes, id.
- No repeating groups? There's only one product per row. But what if an order has multiple products? There's no separate line items table. This means either each row is an order-line (then "order" is misnamed) or multi-product orders require duplicate customer info rows.
- Verdict: Marginal 1NF pass, but the design implies one product per order which is limiting.

2NF — Second Normal Form:
- No partial dependencies on a composite key? Key is single column (id), so 2NF is technically satisfied. But the design is still problematic because...

3NF — Third Normal Form:
- No transitive dependencies? MULTIPLE VIOLATIONS:
  - customer_name, customer_email, customer_address all depend on a customer_id (not present), not on order id directly. These are transitive.
  - product_name, product_price, product_category depend on a product_id (not present). Transitive.
  - total_price = product_price * quantity — this is a derived/calculated column.
  - discounted_total = total_price * (1 - discount_percent/100) — also derived.

Denormalization issues:
- If a customer changes their email, every order row must be updated.
- If a product price changes, historical orders would show wrong prices (actually you might WANT to freeze the price at order time — but that should be explicit, like "unit_price_at_purchase").
- Two derived columns store values that can be computed.

Missing entities: customers table, products table, order_items table.
</think>

**Schema Normalization Checklist Report**

| Rule | Status | Violations Found |
|------|--------|-----------------|
| 1NF (atomic values, PK) | PASS | Atomic values, PK present |
| 2NF (no partial deps) | PASS | Single-column PK, N/A |
| 3NF (no transitive deps) | **FAIL** | 4 transitive dependency groups |
| BCNF | **FAIL** | Inherited from 3NF failures |
| Derived data | **FAIL** | 2 computed columns stored |
| Referential integrity | **FAIL** | No foreign keys at all |

**3NF Violations Detailed:**

1. **Customer data** (`customer_name`, `customer_email`, `customer_address`) depends on an implicit customer identity, not on `order.id`. If customer "Alice" places 500 orders, her address is stored 500 times. One address change requires 500 updates — a classic update anomaly.

2. **Product data** (`product_name`, `product_price`, `product_category`) depends on an implicit product identity. Same duplication and update anomaly problem.

3. **Derived column** `total_price` = `product_price * quantity`. Storing computed values risks inconsistency if any source value is updated without recalculating.

4. **Derived column** `discounted_total` = `total_price * (1 - discount_percent / 100)`. Same risk, now two layers of derivation.

**Recommended normalized schema:**

```sql
CREATE TABLE customers (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    address VARCHAR(255)
);

CREATE TABLE products (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    category VARCHAR(50)
);

CREATE TABLE orders (
    id INT PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id),
    order_date DATE NOT NULL,
    discount_percent DECIMAL(5,2) DEFAULT 0
);

CREATE TABLE order_items (
    id INT PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(id),
    product_id INT NOT NULL REFERENCES products(id),
    unit_price_at_purchase DECIMAL(10,2) NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0)
);
```

Note: `unit_price_at_purchase` intentionally freezes the price at order time — this is acceptable denormalization for auditability. Totals should be computed via queries or views, not stored.

**Score: 3/10** — Violates 3NF with significant update anomaly risk and no referential integrity.'''
    ),
    (
        "thinking/auto-qa-docker-checklist",
        r'''Before suggesting this Docker configuration, verify security best practices:

FROM ubuntu:latest
RUN apt-get update && apt-get install -y python3 python3-pip curl wget
COPY . /app
WORKDIR /app
RUN pip3 install -r requirements.txt
EXPOSE 8080
ENV DATABASE_URL=postgres://admin:secretpass123@db:5432/myapp
ENV SECRET_KEY=my-super-secret-key-2024
CMD ["python3", "app.py"]''',
        r'''<think>
Let me run this Dockerfile through a Docker security best practices checklist.

1. BASE IMAGE
- Using ubuntu:latest — two issues: "latest" tag is mutable (builds not reproducible), and ubuntu is a full OS image (large attack surface). Should use a slim or distroless image with a pinned version.

2. RUNNING AS ROOT
- No USER directive. The container runs as root by default. If the app is compromised, the attacker has root inside the container. Critical issue.

3. SECRETS IN IMAGE
- DATABASE_URL contains plaintext credentials (admin:secretpass123). This is baked into the image layer and visible to anyone with docker history or image access.
- SECRET_KEY is hardcoded. Same problem.
- These should be runtime environment variables or Docker secrets.

4. COPY SCOPE
- COPY . /app copies EVERYTHING including .git, .env files, test data, potentially SSH keys or other secrets. No .dockerignore mentioned.

5. LAYER CACHING
- apt-get update and install in one RUN is good. But pip install is after COPY . which means any code change invalidates the pip cache. Should copy requirements.txt first, install, then copy code.

6. APT CLEANUP
- No cleanup of apt cache after install. Adds unnecessary size.

7. NO HEALTHCHECK
- No HEALTHCHECK instruction.

8. EXPOSED PORT
- EXPOSE 8080 is fine, just documentation.

9. NO SIGNAL HANDLING
- CMD with array form is good (exec form, no shell wrapping). But python3 may not handle SIGTERM properly without signal handling in the app.

Severity: The secrets in ENV are the most critical issue. Running as root is second.
</think>

**Docker Security Checklist Report**

| # | Check | Status | Severity |
|---|-------|--------|----------|
| 1 | Pinned base image | FAIL | High |
| 2 | Minimal base image | FAIL | Medium |
| 3 | Non-root user | FAIL | Critical |
| 4 | No secrets in image | FAIL | Critical |
| 5 | .dockerignore | FAIL | High |
| 6 | Layer cache optimization | FAIL | Low |
| 7 | Apt cache cleanup | FAIL | Low |
| 8 | HEALTHCHECK present | FAIL | Medium |
| 9 | Exec form CMD | PASS | — |
| 10 | Minimal packages | FAIL | Medium |

**Critical Issues (fix immediately):**

**1. Hardcoded secrets in ENV.** `DATABASE_URL` with plaintext password and `SECRET_KEY` are baked into the image. Anyone who pulls this image can run `docker history --no-trunc` or `docker inspect` and read these credentials. These persist in image layers even if you delete them in a later layer.

**2. Running as root.** No `USER` directive means the application runs as UID 0. A remote code execution vulnerability gives the attacker root access inside the container, enabling container escape attacks.

**Secured Dockerfile:**

```dockerfile
FROM python:3.12-slim-bookworm AS base

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python3", "app.py"]
# Pass secrets at runtime: docker run -e DATABASE_URL=... -e SECRET_KEY=...
```

**Key changes:** Pinned slim base image, non-root user, no secrets in image (pass at runtime via `-e` or Docker secrets), apt cache cleaned, layer caching optimized, healthcheck added, unnecessary packages removed.

**Score: 2/10** — Two critical security vulnerabilities make this unsafe for any environment.'''
    ),
    (
        "thinking/auto-qa-workflow-checklist",
        r'''Before presenting this Git workflow, check it handles common edge cases:

Our team workflow:
1. Everyone works on main branch
2. Before pushing, do "git pull" then "git push"
3. If there's a conflict, fix it and push again
4. For releases, we tag main with a version number
5. Hotfixes go directly to main
6. Code review happens in Slack — paste your diff there''',
        r'''<think>
Let me evaluate this Git workflow against common edge cases and team collaboration best practices.

CHECKLIST:
1. Branch isolation — Does the workflow prevent broken code from reaching production?
2. Conflict management — Is the merge strategy clear and safe?
3. Code review — Is review enforced before merge?
4. CI/CD integration — Can automated tests run before merge?
5. Rollback capability — Can you quickly undo bad changes?
6. Concurrent work — Can multiple features be developed simultaneously?
7. Release management — Are releases stable and reproducible?
8. Hotfix process — Can urgent fixes bypass the normal flow safely?

Evaluation:

1. Branch isolation: FAIL. Everyone on main means any push of broken code immediately affects the entire team. One bad push blocks everyone.

2. Conflict management: PARTIAL. "git pull then push" works for simple cases, but with many developers, you get a race condition — by the time you resolve conflict A, someone else pushed, creating conflict B. Also, git pull with default merge strategy creates ugly merge commits. No mention of rebase strategy.

3. Code review: FAIL. Slack-based review is not enforceable. Nothing prevents pushing unreviewed code. Diffs pasted in Slack lose context, can't be commented line-by-line, and have no record tied to the commit.

4. CI/CD: FAIL. No mention of any CI. With direct pushes to main, there's no pre-merge testing gate.

5. Rollback: PARTIAL. You can revert commits on main, but if multiple people pushed after a bad commit, reverting is messy.

6. Concurrent work: FAIL. Everyone on main means everyone's half-finished work interferes with everyone else.

7. Release management: PARTIAL. Tags on main work but you can't stabilize a release while new features keep landing.

8. Hotfix: N/A. Since everything is on main, there's no distinction between hotfix and normal flow. But also no way to hotfix a release without including unreleased features.

This workflow only works for a solo developer or a very small team with extremely good communication.
</think>

**Git Workflow Quality Checklist Report**

| # | Edge Case / Practice | Status | Risk |
|---|---------------------|--------|------|
| 1 | Branch isolation | FAIL | Critical |
| 2 | Broken code protection | FAIL | Critical |
| 3 | Enforceable code review | FAIL | High |
| 4 | CI/CD gate before merge | FAIL | High |
| 5 | Concurrent feature work | FAIL | High |
| 6 | Conflict race conditions | FAIL | Medium |
| 7 | Release stabilization | FAIL | Medium |
| 8 | Selective hotfix ability | FAIL | Medium |
| 9 | Rollback strategy | PARTIAL | Medium |
| 10 | Audit trail | FAIL | Low |

**Critical edge cases NOT handled:**

**Someone pushes broken code to main.** With no branches and no CI gate, a syntax error or failing test in a push immediately breaks the build for the entire team. There is zero protection against this.

**Two developers editing the same file.** Developer A pulls, works for 2 hours, tries to push. Developer B pushed 30 minutes ago. A must now merge under time pressure. Meanwhile Developer C pushes, creating another conflict for A. This "push race" scales terribly beyond 2-3 developers.

**Release needs a hotfix but main has unreleased features.** You tag v1.0 on Monday. Tuesday you add a half-finished feature. Wednesday production has a critical bug. You cannot hotfix v1.0 without either including the half-finished feature or cherry-picking, which this workflow has no process for.

**Recommended workflow (GitHub Flow):**

```
1. main is always deployable (protected branch)
2. Create feature branch: git checkout -b feature/login-page
3. Push branch, open Pull Request
4. CI runs automated tests on the PR
5. Team reviews in PR (line-by-line comments, approval required)
6. Merge to main only after CI passes + 1 approval
7. Deploy from main (automated)
8. Hotfix: branch from the release tag, fix, PR, merge, tag
```

**What this fixes:** Broken code never reaches main (CI gate). Reviews are enforced and auditable (PR approvals). Concurrent work is isolated (branches). Hotfixes can target specific releases. Rollback is simple (revert a merge commit).

**Score: 2/10** — This workflow has no safety nets and will cause increasing pain as the team grows beyond 2 people.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
