"""Phase 3A: Metacognition — Evaluating Completeness of Analysis (Part 8)

Training the model to assess whether its own analysis covers all important
dimensions of a problem, identifying blind spots and missing perspectives.
"""

PAIRS = [
    (
        "thinking/meta-reasoning-completeness-migration",
        r'''We're planning to migrate from MySQL to PostgreSQL. What should we consider?''',
        r'''<think>
This is a broad question where completeness of analysis really matters. Let me systematically think about all dimensions before answering, and then check for blind spots.

Technical dimensions:
- SQL dialect differences (MySQL vs PostgreSQL syntax)
- Data type differences (ENUM, JSON, date handling, AUTO_INCREMENT vs SERIAL/IDENTITY)
- Stored procedures/functions (different PLs)
- Index types and behavior
- Character set/collation handling
- Replication and backup strategy differences

Application dimensions:
- ORM compatibility (does the ORM abstract the differences?)
- Raw SQL queries that use MySQL-specific syntax
- Connection string and driver changes
- Configuration differences (my.cnf vs postgresql.conf)

Data migration:
- Schema conversion tool
- Data transfer method
- Handling of MySQL-specific features during conversion
- Data validation post-migration

Operational dimensions:
- Monitoring and alerting changes
- Backup/restore procedure changes
- Team expertise (MySQL admin skills don't fully transfer)
- Operational tooling differences

Business dimensions:
- Downtime during migration
- Rollback plan
- Testing strategy (parallel running?)
- Timeline and phasing

Wait — am I missing anything? Let me check:
- Performance differences (query optimizer behavior differs)
- Licensing (both open source but PostgreSQL has more permissive licensing)
- Extension ecosystem (PostGIS, pg_trgm, etc. — PostgreSQL advantage)
- Connection pooling (PostgreSQL benefits more from PgBouncer)
- Authentication method differences

Let me also think about what people commonly FORGET:
- Implicit casting differences (MySQL is more lenient, PostgreSQL is stricter)
- Case sensitivity of identifiers (MySQL depends on OS, PostgreSQL folds to lowercase)
- NULL handling differences in certain operations
- Transaction isolation default differences
- LIMIT syntax is the same, but GROUP BY behavior differs

I think I have a reasonably complete picture. Let me organize this.
</think>

This requires comprehensive analysis across multiple dimensions. Let me be systematic and flag areas people commonly miss.

**1. SQL and Data Type Differences (commonly underestimated)**

```sql
-- AUTO_INCREMENT → SERIAL or GENERATED ALWAYS AS IDENTITY
-- MySQL:
CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY);
-- PostgreSQL:
CREATE TABLE users (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);

-- ENUM handling differs
-- MySQL: ENUM is a column type
-- PostgreSQL: CREATE TYPE status AS ENUM ('active', 'inactive');

-- Implicit casting — PostgreSQL is STRICTER
-- MySQL:  SELECT * FROM users WHERE id = '123'   -- works (implicit cast)
-- PostgreSQL: Same query works but can prevent index usage

-- Group BY — PostgreSQL requires all non-aggregate columns
-- MySQL (with default settings): SELECT name, count(*) FROM users
-- PostgreSQL: SELECT name, count(*) FROM users GROUP BY name  -- required

-- Case sensitivity of identifiers
-- MySQL: table names case-sensitive on Linux, insensitive on Windows
-- PostgreSQL: folds unquoted identifiers to lowercase
```

**2. Application Layer Changes**

```
- [ ] Update database driver (mysql2 → pg, mysqlclient → psycopg2)
- [ ] Update connection strings
- [ ] Audit ALL raw SQL queries for MySQL-specific syntax
- [ ] Test ORM-generated queries (some ORMs need dialect configuration)
- [ ] Review stored procedures (MySQL procedures → PL/pgSQL)
- [ ] Check BOOLEAN handling (MySQL uses TINYINT(1), PostgreSQL has native BOOLEAN)
```

**3. Data Migration Strategy**

```
Option A: pgloader (automated, handles most conversions)
  $ pgloader mysql://user:pass@mysql-host/db postgresql://user:pass@pg-host/db

Option B: Dump and transform
  $ mysqldump → convert schema → psql import

Option C: Application-level migration (write to both, compare)
  Most complex but lowest risk
```

**4. Operational Differences (frequently forgotten)**

```
- [ ] Backup strategy: mysqldump → pg_dump / pg_basebackup
- [ ] Monitoring: different metrics, different slow query log format
- [ ] Connection pooling: PostgreSQL benefits greatly from PgBouncer
- [ ] Vacuum: PostgreSQL needs VACUUM (MySQL doesn't have this concept)
- [ ] Configuration tuning: shared_buffers, work_mem, effective_cache_size
- [ ] Team training: PostgreSQL operations differ significantly
```

**5. Business/Process Dimensions**

```
- [ ] Migration window: how much downtime is acceptable?
- [ ] Rollback plan: can you switch back to MySQL if issues arise?
- [ ] Parallel running period: run both and compare results?
- [ ] Data validation: row counts, checksums, spot-check comparisons
- [ ] Performance benchmarking: same queries on both systems
```

**6. Commonly Missed Items (blind spot check)**

- **Transaction isolation**: MySQL InnoDB defaults to REPEATABLE READ; PostgreSQL defaults to READ COMMITTED
- **NULL sorting**: PostgreSQL puts NULLs last by default in ASC order; MySQL puts them first
- **Full-text search**: Different syntax and capabilities (PostgreSQL's is more powerful)
- **JSON support**: Both support it but functions differ (`JSON_EXTRACT` vs `->>/jsonb_extract_path`)
- **Sequence gaps**: PostgreSQL sequences can have gaps after rollback (normal behavior, but may surprise MySQL users)

**Recommended phased approach:**
1. Set up PostgreSQL, run pgloader for initial schema/data
2. Fix all incompatibilities found
3. Run application test suite against PostgreSQL
4. Parallel operation period (read from both, compare)
5. Cutover with rollback plan ready'''
    ),
    (
        "thinking/meta-reasoning-completeness-api-design",
        r'''I'm designing a REST API for a multi-tenant SaaS application. I've planned the CRUD endpoints and authentication. What am I likely missing?''',
        r'''<think>
The question explicitly asks me to find blind spots in their planning. Let me think about all the dimensions of API design and identify what people commonly miss when they focus on CRUD + auth.

What they likely HAVE thought about:
- CRUD endpoints (GET, POST, PUT, DELETE for resources)
- Authentication (JWT, OAuth, API keys)
- Basic resource structure

What they likely HAVEN'T thought about (common blind spots):

Authorization (different from authentication):
- Tenant isolation — ensuring tenant A can't access tenant B's data
- Role-based access within a tenant
- Resource-level permissions

Rate limiting and abuse prevention:
- Per-tenant limits
- Per-endpoint limits
- Burst allowances

Pagination:
- Cursor-based vs offset-based
- Default and maximum page sizes
- Total count performance implications

Versioning:
- How to evolve the API without breaking clients
- URL versioning vs header versioning

Error handling:
- Consistent error response format
- Meaningful error codes
- Not leaking internal details

Multi-tenant data isolation:
- How tenant context is determined (subdomain? header? path?)
- Database strategy (shared DB with tenant_id? schema per tenant? DB per tenant?)
- Preventing cross-tenant data leaks in queries

Idempotency:
- POST requests that shouldn't create duplicates
- Idempotency keys for critical operations

Webhooks/events:
- How tenants receive async notifications
- Retry policies

Let me also think about operational concerns:
- Monitoring and observability
- Documentation (OpenAPI/Swagger)
- SDK generation
- Deprecation strategy

Am I missing anything? Let me think about security specifically for multi-tenant:
- Tenant-scoped API keys
- Audit logging per tenant
- Data residency requirements
- Tenant offboarding (data deletion)

I think this is a comprehensive list. Let me organize by priority.
</think>

Good instinct to ask what you're missing. CRUD + auth covers maybe 30% of API design for multi-tenant SaaS. Here are the dimensions commonly overlooked, roughly in priority order.

**1. Authorization (NOT authentication) — most commonly missed**
```
Authentication: "Who are you?"         ✓ You have this
Authorization:  "What can you access?" ✗ Likely incomplete

Critical for multi-tenant:
- Tenant isolation: EVERY query must be scoped to the tenant
- Role-based access: admin vs member vs viewer within a tenant
- Resource-level permissions: can user X edit resource Y?
```

```python
# DANGEROUS: Relies on the endpoint to filter
GET /api/invoices/123  # Does this check tenant ownership?

# SAFE: Middleware enforces tenant context
def get_invoice(invoice_id, current_tenant):
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.tenant_id == current_tenant.id  # ALWAYS filter by tenant
    ).first()
    if not invoice:
        raise NotFound()  # Don't reveal it exists for another tenant
```

**2. Tenant Context Resolution**
```
How does the API know which tenant? Pick one:
- Subdomain:  acme.yourapp.com/api/...
- Path:       /api/v1/tenants/{tenant_id}/...
- Header:     X-Tenant-ID: acme
- JWT claim:  tenant_id embedded in token

Each has tradeoffs for caching, routing, and security.
```

**3. Pagination (breaks at scale if missing)**
```json
// Cursor-based (recommended for multi-tenant):
GET /api/invoices?cursor=eyJpZCI6MTIzfQ&limit=50

{
    "data": [...],
    "pagination": {
        "next_cursor": "eyJpZCI6MTczfQ",
        "has_more": true
    }
}
// Offset-based breaks when tenants have millions of records
```

**4. Rate Limiting (per-tenant)**
```
Headers to include:
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1710086400

Different limits per:
- Tenant plan (free: 100/min, pro: 1000/min)
- Endpoint type (reads: generous, writes: stricter)
- Specific expensive operations (reports, exports)
```

**5. Idempotency for Write Operations**
```
POST /api/invoices
Idempotency-Key: unique-client-generated-key

Without this: network retry creates duplicate invoices
With this:    server returns the same response for the same key
```

**6. API Versioning Strategy**
```
Pick one before launch (changing later is painful):
- URL:    /api/v1/invoices  (most common, easiest)
- Header: Accept: application/vnd.yourapp.v1+json
- Query:  /api/invoices?version=1
```

**7. Consistent Error Format**
```json
{
    "error": {
        "code": "INVOICE_NOT_FOUND",
        "message": "Invoice not found",
        "details": [{"field": "id", "issue": "No invoice with this ID"}],
        "request_id": "req_abc123"
    }
}
// Never leak: stack traces, SQL queries, internal IDs of other tenants
```

**8. Commonly Forgotten Operational Concerns**
```
- [ ] Audit logging (who did what, when — per tenant)
- [ ] Webhook/event system for async notifications
- [ ] OpenAPI spec (auto-generate client SDKs)
- [ ] Health check endpoint (for load balancers)
- [ ] Bulk operations (import/export for enterprise tenants)
- [ ] Tenant offboarding (GDPR data deletion)
- [ ] Data residency (EU tenants' data stays in EU)
```

Start with items 1-5 before launch. Items 6-8 can follow shortly after.'''
    ),
    (
        "thinking/meta-reasoning-completeness-incident",
        r'''Our production database went down for 2 hours last night. We identified the root cause (disk full) and added monitoring. Is our incident response complete?''',
        r'''<think>
Let me evaluate whether their incident response is complete by checking against established incident response frameworks.

What they've done:
- Identified root cause (disk full)
- Added monitoring

What a complete incident response includes (I'll check against industry practices):

1. Detection: How was it detected? If by users, detection needs improvement.
2. Response: How quickly was it addressed? Who was paged?
3. Root cause analysis: They say "disk full" — but WHY was the disk full?
4. Immediate fix: Did they free disk space? How?
5. Monitoring: Added (good)
6. Prevention: How to prevent recurrence? Monitoring alerts AFTER the fact.
7. Communication: Were stakeholders/customers informed?
8. Post-mortem: Was a formal writeup done?
9. Action items: What specific changes are being made?
10. Follow-up: Who owns each action item? When are they due?

Missing elements I can see:
- "Disk full" is a proximate cause, not a root cause. WHY was the disk full? Log rotation? Growing table? Temp files? Without this, the same thing will happen again.
- Monitoring catches the NEXT occurrence but doesn't PREVENT it
- No mention of customer communication
- No mention of runbook or playbook for future incidents
- No mention of testing the monitoring actually works
- No mention of capacity planning to avoid future disk issues

This is a common pattern: treating the incident as "done" after the immediate fix, missing the deeper systemic improvements.
</think>

No, your incident response is about 40% complete. You've addressed detection but missed prevention, communication, and systemic improvement. Let me walk through what's missing.

**What you've done:**
```
✓ Identified proximate cause (disk full)
✓ Added monitoring
```

**What a complete incident response requires:**

**1. Root cause — go deeper (you stopped too early)**
```
"Disk full" is the PROXIMATE cause. The ROOT cause is:
- WHY was the disk full?
  - Logs not rotating? → Fix log rotation
  - Table growing unbounded? → Add data retention policy
  - Temp files not cleaned up? → Fix cleanup job
  - Unexpected data growth? → Capacity planning failure

Without answering WHY, you'll hit this again on a different disk.
```

**2. Monitoring catches the NEXT incident — it doesn't prevent it**
```
You added:  Alert when disk > 90%
You need:   Automated action to prevent reaching 90%

- Automated log rotation
- Automated temp file cleanup
- Auto-scaling storage (if cloud)
- Data retention policies (delete/archive old data)
```

**3. Missing communication audit**
```
- [ ] Were affected customers notified?
- [ ] Was there a status page update?
- [ ] Was leadership informed with an ETA during the outage?
- [ ] Is there a customer-facing post-mortem?
```

**4. Missing formal post-mortem**

A post-mortem document should include:
```markdown
## Incident: Production DB Outage
**Duration:** 2 hours (00:00 - 02:00)
**Impact:** All users unable to access application
**Severity:** SEV-1

## Timeline
- 00:00 — First user report / alert fired
- 00:15 — On-call engineer paged
- 00:30 — Root cause identified (disk full)
- 01:00 — Disk space freed
- 02:00 — Full recovery confirmed

## Root Cause
[Not just "disk full" — WHY was it full?]

## What went well
- [What worked in the response]

## What went poorly
- Detection: How was it discovered? User report = detection failure
- Response: 2 hours is a long outage — what slowed recovery?

## Action Items
| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add disk monitoring | Alice | Done | ✓ |
| Fix log rotation | Bob | 2024-03-15 | Pending |
| Add auto-scaling | Carol | 2024-03-22 | Pending |
| Capacity planning review | Dave | 2024-03-29 | Pending |
| Test restore procedure | Alice | 2024-03-15 | Pending |
```

**5. Missing resilience improvements**
```
- [ ] Can the DB survive a full disk without corrupting data?
- [ ] Is there a tested backup/restore procedure?
- [ ] How long does restore take? (Was it tested recently?)
- [ ] Can the application degrade gracefully during DB issues?
- [ ] Is there a runbook for "disk full" that on-call can follow at 3 AM?
```

**6. Missing process check**
```
- [ ] Why didn't monitoring catch this BEFORE it caused an outage?
- [ ] Was there an on-call engineer? Were they paged automatically?
- [ ] Is there an incident response process, or was this ad-hoc?
```

**Bottom line:** "Found the cause and added monitoring" is the START of incident response, not the end. Complete the post-mortem, assign action items with owners and due dates, and focus on prevention over detection.'''
    ),
    (
        "thinking/meta-reasoning-completeness-security-review",
        r'''I'm reviewing the security of our new user registration endpoint. I've checked for SQL injection and XSS. What else should I look at?''',
        r'''<think>
The person has checked two of the most well-known vulnerability types. Let me think about what a comprehensive security review of a registration endpoint should cover.

What they've checked:
- SQL injection
- XSS (Cross-Site Scripting)

What a registration endpoint specifically needs (beyond generic security):

Authentication/Identity:
- Password strength requirements
- Password hashing (bcrypt, argon2 — not MD5/SHA1)
- Email verification flow
- Username enumeration (can attackers discover valid accounts?)

Rate limiting / abuse:
- Registration rate limiting (prevent mass account creation)
- CAPTCHA for bot prevention
- Email bombing (sending verification emails as spam tool)

Input validation:
- Email format validation
- Username restrictions (prevent impersonation, control characters)
- Input length limits (prevent huge payloads)
- Character encoding issues

Data handling:
- What data is stored? Minimization principle
- Is PII encrypted at rest?
- GDPR/privacy compliance for collected data
- Logging — are passwords or tokens logged accidentally?

CSRF:
- Is the registration form protected against CSRF?

API-specific:
- Is it a REST API or form-based? Each has different attack surfaces
- Mass assignment / over-posting (extra fields in request body)
- Response data — does the registration response leak information?

Business logic:
- Can someone register with an existing email? What's the behavior?
- Disposable email addresses
- Role assignment on registration (can users set themselves as admin?)
- Referral/invitation code bypass

I should organize this as a checklist they can use systematically.
</think>

SQL injection and XSS are important but cover maybe 20% of the attack surface for a registration endpoint. Here's a comprehensive security checklist.

**Password Handling (critical)**
```
- [ ] Passwords hashed with bcrypt/argon2/scrypt (NOT MD5/SHA1/SHA256)
- [ ] Salt is unique per user (bcrypt does this automatically)
- [ ] Password minimum length (8+ characters)
- [ ] Check against breached password lists (Have I Been Pwned API)
- [ ] Passwords never logged (check your logging middleware!)
- [ ] Passwords never returned in API responses
```
```python
# WRONG
password_hash = hashlib.sha256(password.encode()).hexdigest()

# RIGHT
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
```

**Account Enumeration Prevention**
```
# WRONG: reveals whether email exists
POST /register → "This email is already registered"
POST /login    → "No account with this email"

# RIGHT: same response regardless
POST /register → "If this email is available, you'll receive a verification link"
POST /login    → "Invalid email or password"  (same message for both cases)
```

**Rate Limiting and Bot Prevention**
```
- [ ] Rate limit registrations per IP (e.g., 5/hour)
- [ ] Rate limit registrations per email domain
- [ ] CAPTCHA or proof-of-work for registration
- [ ] Rate limit verification email sends (prevent email bombing)
- [ ] Block disposable email domains (optional, depends on your product)
```

**Mass Assignment / Over-posting**
```python
# VULNERABLE: accepts any field from request body
user = User(**request.json)  # What if they send {"role": "admin"}?

# SAFE: whitelist accepted fields
allowed = ['email', 'password', 'name']
data = {k: request.json[k] for k in allowed if k in request.json}
user = User(**data)
```

**CSRF Protection**
```
- [ ] Registration form includes CSRF token (for browser-based forms)
- [ ] API endpoints use proper CORS configuration
- [ ] SameSite cookie attribute set
```

**Input Validation Beyond SQLi/XSS**
```
- [ ] Email format validation (RFC 5322 or pragmatic regex)
- [ ] Input length limits (prevent multi-MB payloads in name fields)
- [ ] Username restrictions (no control characters, no impersonation)
- [ ] Reject or sanitize Unicode tricks (homoglyph attacks: "admin" vs "аdmin")
```

**Email Verification**
```
- [ ] Verification tokens are random and unguessable (UUID4 or crypto random)
- [ ] Tokens expire (24 hours max)
- [ ] Tokens are single-use
- [ ] Account is not fully active until verified
```

**Data Privacy**
```
- [ ] Collect only necessary data (minimization)
- [ ] PII encrypted at rest
- [ ] Privacy policy link on registration
- [ ] GDPR: consent for data processing, right to deletion
- [ ] Registration data not leaked in error messages or logs
```

**Response Security**
```
- [ ] Don't return the password hash in the response
- [ ] Don't return internal IDs that reveal information
- [ ] Set security headers (Content-Type, X-Content-Type-Options, etc.)
- [ ] Registration response doesn't include a session token
      (require separate login after email verification)
```

Use this as a checklist — work through each item systematically rather than relying on memory.'''
    ),
    (
        "thinking/meta-reasoning-completeness-deploy",
        r'''We're switching from manual deployments to CI/CD. We've set up GitHub Actions to run tests and deploy to production on merge to main. Is this a complete CI/CD pipeline?''',
        r'''<think>
They have the basics: tests run, code deploys on merge. But a production-ready CI/CD pipeline needs much more. Let me think about all the dimensions.

What they have:
- Tests run in CI
- Auto-deploy to production on merge to main

What's likely missing:

Build/Quality:
- Linting and code formatting checks
- Static analysis / SAST
- Dependency vulnerability scanning
- Build artifact caching
- Docker image building and scanning

Testing:
- Are the tests comprehensive? (unit, integration, e2e?)
- Test environment that mirrors production
- Database migration testing
- Performance/load testing

Deployment:
- Staging environment before production?
- Blue/green or canary deployments?
- Database migration strategy during deploy
- Rollback mechanism
- Deployment notifications

Post-deploy:
- Smoke tests after deployment
- Health check verification
- Monitoring integration
- Automatic rollback on health check failure

Security:
- Secrets management
- Container image scanning
- SAST/DAST in pipeline
- License compliance checking

Process:
- Branch protection rules
- Required reviews before merge
- Deploy approvals for production
- Deployment audit trail

This is going from "we can deploy" to "we can deploy safely, reliably, and repeatedly." Big difference.
</think>

You have a deployment pipeline, but not a complete CI/CD pipeline. "Tests pass, deploy to prod" is the starting point. Here's what a production-grade pipeline includes.

**What you have:**
```
Code → Tests → Deploy to Production
```

**What you need:**
```
Code → Lint/Format → SAST → Tests → Build → Staging → Smoke Tests → Production → Health Check → Monitor
  ↑                                                                         |
  └─── Rollback ←──────────────────────────────────────────────────────────┘
```

**1. Pre-test quality gates (add before tests)**
```yaml
# GitHub Actions additions:
jobs:
  lint:
    steps:
      - run: eslint . --max-warnings 0
      - run: prettier --check .

  security-scan:
    steps:
      - uses: github/codeql-action/analyze@v2
      - run: npm audit --audit-level=high
      - uses: aquasecurity/trivy-action@master  # Container scan
```

**2. Test completeness (audit your tests)**
```
- [ ] Unit tests (fast, isolated)
- [ ] Integration tests (database, external services)
- [ ] End-to-end tests (critical user flows)
- [ ] Database migration test (can migrations run cleanly?)
- [ ] Contract tests (if you have multiple services)
```

**3. Staging environment (deploy here first)**
```yaml
deploy-staging:
  needs: [test]
  environment: staging
  steps:
    - run: deploy-to-staging.sh

smoke-test-staging:
  needs: [deploy-staging]
  steps:
    - run: curl -f https://staging.yourapp.com/health
    - run: npm run test:smoke -- --base-url=https://staging.yourapp.com

deploy-production:
  needs: [smoke-test-staging]
  environment: production  # Requires approval in GitHub settings
```

**4. Safe deployment strategy**
```
Choose one:
- Blue/green: Deploy to inactive environment, swap traffic
- Canary: Send 5% of traffic to new version, monitor, expand
- Rolling: Replace instances one at a time

NOT: Deploy everything at once and hope for the best
```

**5. Post-deploy verification**
```yaml
post-deploy:
  steps:
    - name: Health check
      run: |
        for i in {1..10}; do
          curl -f https://yourapp.com/health && exit 0
          sleep 5
        done
        exit 1

    - name: Smoke tests
      run: npm run test:smoke -- --base-url=https://yourapp.com

    - name: Notify
      if: success()
      run: curl -X POST $SLACK_WEBHOOK -d '{"text":"Deploy successful"}'

    - name: Rollback on failure
      if: failure()
      run: rollback-to-previous.sh
```

**6. Missing operational pieces**
```
- [ ] Secrets management (GitHub Secrets, not hardcoded)
- [ ] Branch protection (require PR review before merge)
- [ ] Deploy audit trail (who deployed what, when)
- [ ] Automatic rollback on health check failure
- [ ] Deploy notifications (Slack, email)
- [ ] Artifact versioning (tag Docker images, store build artifacts)
- [ ] Database migration strategy (run before or during deploy?)
```

**Priority order for improvement:**
1. Add staging environment with smoke tests
2. Add health check + automatic rollback
3. Add security scanning (dependency audit, SAST)
4. Add deploy notifications
5. Implement blue/green or canary deployments'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
