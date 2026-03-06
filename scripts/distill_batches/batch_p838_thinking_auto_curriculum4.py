"""Phase 4C: Self-Improvement — Curriculum Design (Part 4)

Designing security learning paths for developers.
"""

PAIRS = [
    (
        "thinking/auto-curriculum-security-web-fundamentals",
        r'''Design a security learning path for web developers. They build web apps but have never thought about security beyond "use HTTPS." What should they learn and in what order?''',
        r'''<think>
Most web developers lack security awareness because it's rarely taught in tutorials or bootcamps. The curriculum needs to:

1. Make security concrete (not theoretical)
2. Show real attacks (not just say "be careful")
3. Prioritize by impact (OWASP Top 10 order)
4. Provide actionable checklists they can apply immediately

**Ordering:** Start with the most common and impactful vulnerabilities, show how they work, then teach prevention.
</think>

**Web Security Learning Path**

*For developers who build web apps but haven't studied security.*

**Phase 1: The Threat Model — Understanding WHY Security Matters (Week 1)**

```
Goal: Shift from "it won't happen to me" to "I need to defend against this"

Day 1: Real-world breaches (motivation)
  - Equifax breach (unpatched vulnerability, 147M records)
  - Capital One breach (SSRF, 100M records)
  - npm event-stream attack (supply chain)
  - Read 3 post-mortems and note the root cause of each

Day 2: How attackers think
  - Reconnaissance: finding your tech stack, endpoints, error pages
  - The attack surface of a typical web app
  - Why "security through obscurity" doesn't work
  - Use Burp Suite or browser DevTools to inspect your own app

Day 3: OWASP Top 10 overview
  1. Broken Access Control
  2. Cryptographic Failures
  3. Injection (SQL, XSS, Command)
  4. Insecure Design
  5. Security Misconfiguration
  6. Vulnerable Components
  7. Authentication Failures
  8. Data Integrity Failures
  9. Logging Failures
  10. Server-Side Request Forgery (SSRF)

  The rest of this curriculum covers each in depth.

Milestone: Can explain why security matters with 3 real examples,
and can list the OWASP Top 10 from memory.
```

**Phase 2: Injection Attacks (Weeks 2-3)**

```
Goal: Understand and prevent SQL injection, XSS, and command injection.

Week 2: SQL Injection
  1. How SQL injection works:
     Input: ' OR '1'='1' --
     Query: SELECT * FROM users WHERE email = '' OR '1'='1' --'
     Result: Returns ALL users

  2. Hands-on: Exploit SQL injection on a practice app
     (use DVWA or WebGoat — intentionally vulnerable apps)

  3. Prevention:
     - Parameterized queries (ALWAYS)
     - ORM usage (usually safe, but verify raw queries)
     - Input validation (defense in depth)
     - Principle of least privilege for database accounts

  4. Exercise: Audit your own code for string-formatted SQL queries

Week 3: Cross-Site Scripting (XSS)
  1. Stored XSS: Attacker saves <script> in your database
  2. Reflected XSS: Malicious URL reflects script in response
  3. DOM-based XSS: Client-side JavaScript processes untrusted data

  4. Hands-on: Inject a script tag into a form field that steals cookies

  5. Prevention:
     - Output encoding (escape HTML entities)
     - Content Security Policy (CSP) headers
     - Use framework auto-escaping (React, Jinja2)
     - Never use innerHTML with user data
     - Sanitize HTML if you must allow it (DOMPurify)

  6. Exercise: Add CSP headers to your application and verify XSS
     payloads are blocked

Milestone: Can demonstrate SQL injection and XSS on a practice app,
and can prevent both in your own code.
```

**Phase 3: Authentication and Authorization (Weeks 4-5)**

```
Goal: Build secure login systems and access controls.

Week 4: Authentication
  1. Password storage:
     - NEVER: plaintext, MD5, SHA-256
     - ALWAYS: bcrypt (cost 12+) or Argon2
     - Timing-safe comparison

  2. Session management:
     - Secure session IDs (cryptographically random)
     - httpOnly, Secure, SameSite cookie flags
     - Session expiration and rotation
     - Session fixation prevention

  3. Multi-factor authentication:
     - TOTP (Google Authenticator)
     - WebAuthn/passkeys
     - SMS is weak (SIM swapping) — use as fallback only

  4. Common authentication mistakes:
     - User enumeration (different messages for "user not found" vs "wrong password")
     - No brute-force protection (add rate limiting)
     - Password reset tokens that don't expire
     - Predictable password reset URLs

  Exercise: Implement login with bcrypt, rate limiting, and secure sessions.

Week 5: Authorization
  1. Broken access control (OWASP #1):
     - IDOR: /api/users/123/orders — can user 456 access this?
     - Horizontal escalation: accessing other users' data
     - Vertical escalation: accessing admin functionality

  2. Prevention:
     - Check authorization on EVERY endpoint (not just the frontend)
     - Never trust client-side access control alone
     - Verify the authenticated user owns the requested resource
     - Use middleware/decorators for consistent enforcement

  3. Testing for broken access control:
     - Log in as User A, copy request
     - Change session to User B, replay request
     - Can User B see User A's data? → IDOR vulnerability!

  Exercise: Audit all your API endpoints for IDOR vulnerabilities.

Milestone: Can implement secure authentication and test for IDOR.
```

**Phase 4: Data Protection (Weeks 6-7)**

```
Goal: Protect sensitive data at rest, in transit, and in logs.

Week 6: Encryption and secrets
  1. HTTPS everywhere:
     - TLS certificate setup (Let's Encrypt)
     - HSTS header (force HTTPS)
     - Redirect HTTP to HTTPS

  2. Secrets management:
     - Never commit secrets to git
     - Use environment variables or secrets managers
     - Rotate secrets regularly
     - Scan git history for leaked secrets (trufflehog, gitleaks)

  3. Data at rest:
     - Encrypt sensitive database columns
     - Encrypt backups
     - PII handling requirements (GDPR, CCPA)

Week 7: Secure headers and configuration
  1. Security headers checklist:
     - Content-Security-Policy (prevent XSS)
     - X-Content-Type-Options: nosniff
     - X-Frame-Options: DENY (prevent clickjacking)
     - Strict-Transport-Security (force HTTPS)
     - Referrer-Policy: no-referrer

  2. Configuration security:
     - Disable debug mode in production
     - Remove default admin accounts
     - Disable directory listing
     - Remove version headers (Server, X-Powered-By)

  3. Dependency security:
     - npm audit / pip audit / bundler audit
     - Dependabot or Snyk for automated alerts
     - Review dependency licenses

  Exercise: Run a security header scan (securityheaders.com) on your
  deployed app and fix all warnings.

Milestone: Can pass a security header scan with A+ rating and
configure secrets management properly.
```

**Phase 5: Advanced Threats (Weeks 8-9)**

```
Goal: Understand and prevent SSRF, CSRF, and supply chain attacks.

Week 8: SSRF and CSRF
  1. CSRF (Cross-Site Request Forgery):
     - How it works: trick a logged-in user into making a request
     - Prevention: CSRF tokens, SameSite cookies
     - Why SPAs with JWT are less vulnerable (no cookies)

  2. SSRF (Server-Side Request Forgery):
     - How it works: trick the server into making internal requests
     - The Capital One breach: SSRF to access AWS metadata
     - Prevention: validate/whitelist URLs, block internal IPs
     - Never fetch user-provided URLs without validation

Week 9: Supply chain and operational security
  1. Dependency attacks:
     - Typosquatting (loadash instead of lodash)
     - Compromised maintainer accounts
     - Lock files (package-lock.json, Pipfile.lock)
     - Pin dependency versions

  2. Logging and monitoring:
     - Log security events (failed logins, privilege escalations)
     - Never log passwords, tokens, or PII
     - Monitor for anomalies (sudden spike in 401 errors)
     - Incident response plan

Milestone: Can explain SSRF/CSRF attacks, implement CSRF protection,
and set up security event logging.
```

**Phase 6: Security Practice (Weeks 10-12)**

```
Goal: Build security into your development workflow.

Week 10: Security testing
  - SAST (Static Application Security Testing): Bandit for Python, ESLint security plugin
  - DAST (Dynamic Application Security Testing): OWASP ZAP
  - Add security scanning to CI/CD pipeline
  - Penetration testing basics

Week 11: Security code review checklist
  For every PR, check:
  - [ ] No SQL string formatting (use parameterized queries)
  - [ ] All user input validated and sanitized
  - [ ] Authentication checked on new endpoints
  - [ ] Authorization checked (user owns the resource?)
  - [ ] No secrets in code or config files
  - [ ] Sensitive data not logged
  - [ ] Dependencies audited for known vulnerabilities
  - [ ] Error messages don't expose internal details

Week 12: Capstone
  - Run OWASP ZAP against your own application
  - Fix all findings
  - Document your security architecture
  - Set up automated security scanning in CI/CD

Milestone: Can perform a basic security audit on a web application
and fix the most common vulnerabilities.
```'''
    ),
    (
        "thinking/auto-curriculum-security-api-hardening",
        r'''Design a focused curriculum for hardening an existing API. The developer has a working API in production but recently had a security incident (credential stuffing attack on their login endpoint). What should they learn and implement?''',
        r'''<think>
This is an urgent, practical situation — they need actionable fixes, not theory. The curriculum should be ordered by impact and urgency:

1. Stop the immediate bleeding (rate limiting, monitoring)
2. Harden authentication
3. Protect the API surface
4. Set up ongoing security practices

Each step should produce a deployable improvement.
</think>

**API Hardening Curriculum — Post-Incident Response**

*Priority-ordered: most critical fixes first.*

**Week 1: Stop the Bleeding (URGENT)**

```
Day 1-2: Rate limiting on authentication endpoints
  Implement immediately:
  - Login: 5 attempts per minute per IP
  - Password reset: 3 requests per hour per email
  - Registration: 10 per hour per IP

  Implementation:
  - Flask-Limiter, express-rate-limit, or nginx rate limiting
  - Use IP + user identifier as rate limit key
  - Return 429 Too Many Requests with Retry-After header
  - Log all rate-limited requests (they indicate attacks)

  Test: Verify you can't make more than 5 login attempts per minute

Day 3: Account lockout
  - Lock account after 10 failed login attempts
  - Require email verification to unlock
  - Notify user of suspicious activity
  - Don't reveal whether the account exists (same error for bad username/password)

Day 4-5: Monitoring and alerting
  - Set up alerts for:
    - >50 failed logins per minute (attack in progress)
    - >10 failed logins for a single account (targeted attack)
    - Successful login from new IP/country (account compromise)
  - Dashboard showing authentication events in real time
  - Integrate with Slack/PagerDuty for immediate notification

Milestone: Login endpoint protected against credential stuffing.
Active monitoring detects ongoing attacks.
```

**Week 2: Strengthen Authentication**

```
Day 1-2: Password policy review
  Implement:
  - Minimum 8 characters (NIST recommends no max limit)
  - Check against breached password databases (Have I Been Pwned API)
  - Don't require arbitrary complexity rules (users create worse passwords)
  - Hash with bcrypt cost 12 or Argon2

  API endpoint for password validation:
  POST /api/auth/check-password
  - Check against HaveIBeenPwned k-anonymity API
  - Return whether password has been in a breach

Day 3: Session hardening
  - Rotate session ID on login (prevent session fixation)
  - Set session timeout (30 minutes idle, 8 hours absolute)
  - Bind sessions to IP or user agent (detect hijacking)
  - Cookie flags: httpOnly, Secure, SameSite=Strict

Day 4-5: Optional but recommended — add MFA
  - TOTP-based MFA (Google Authenticator compatible)
  - Recovery codes for account recovery
  - Require MFA for admin accounts (enforce, not optional)
  - Allow users to opt-in for regular accounts

Milestone: Authentication system follows current best practices.
```

**Week 3: API Surface Hardening**

```
Day 1: Security headers
  Add to every response:
  - Strict-Transport-Security: max-age=31536000; includeSubDomains
  - Content-Security-Policy: default-src 'self'
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Cache-Control: no-store (for sensitive endpoints)
  - Remove: Server, X-Powered-By headers

Day 2: Input validation on all endpoints
  - Schema validation on every endpoint (Pydantic, Marshmallow)
  - Maximum request body size (prevent DoS with huge payloads)
  - Content-Type enforcement (reject unexpected content types)
  - Parameter pollution prevention

Day 3: Error handling review
  - Don't expose stack traces in production
  - Don't reveal database structure in errors
  - Use generic error messages for security-sensitive operations
  - Include request_id for debugging (user can share with support)

Day 4: CORS review
  - Whitelist specific origins (never use * in production)
  - Restrict methods and headers
  - Don't allow credentials with wildcard origin

Day 5: Endpoint audit
  - List ALL endpoints
  - Verify each has: authentication, authorization, input validation, rate limiting
  - Remove unused endpoints
  - Add authentication to any unprotected endpoints

Milestone: All API endpoints hardened with headers, validation, CORS,
and authentication. No information leakage in errors.
```

**Week 4: Ongoing Security Practices**

```
Day 1-2: Automated security scanning
  Set up in CI/CD pipeline:
  - Dependency scanning (npm audit, pip audit, Snyk)
  - Static analysis (Bandit for Python, ESLint security)
  - Secret scanning (gitleaks, trufflehog)
  - Block deploys that introduce known vulnerabilities

Day 3: Logging and audit trail
  Log all security-relevant events:
  - Login success/failure (with IP, user agent)
  - Password changes
  - Permission changes
  - Admin actions
  - API key creation/deletion
  - Rate limit triggers

  Log retention: 90 days minimum (check compliance requirements)
  Log storage: separate from application logs, tamper-resistant

Day 4: Incident response plan
  Document:
  1. How to detect an attack (monitoring alerts)
  2. How to stop it (block IPs, disable accounts, rate limit)
  3. How to investigate (review logs, identify scope)
  4. How to notify affected users
  5. How to prevent recurrence (fix root cause)
  6. Post-incident review template

Day 5: Security review cadence
  Schedule recurring:
  - Weekly: review security alerts from scanning tools
  - Monthly: review authentication logs for anomalies
  - Quarterly: full API endpoint audit
  - Annually: penetration test by external security firm

Milestone: Automated security scanning in CI/CD, comprehensive
logging, and a documented incident response plan.
```'''
    ),
    (
        "thinking/auto-curriculum-security-secure-coding",
        r'''Design a secure coding training program for a development team of 10 developers. They have mixed experience levels and limited time (max 2 hours per week for security training). The goal is to reduce security vulnerabilities in their code by 80% within 3 months.''',
        r'''<think>
Constraints:
- 10 developers, mixed experience
- 2 hours per week maximum
- 3-month timeline
- Goal: 80% reduction in vulnerabilities

**Strategy:**
- Can't do deep training in 2 hours/week — focus on high-impact, practical skills
- Use checklists and automated tools to scale
- Make security part of the workflow, not a separate activity
- Measure progress with metrics (vulnerability counts)

**The 80/20 of security vulnerabilities:**
Most web app vulnerabilities come from a small number of categories:
1. SQL injection / injection attacks (~25%)
2. Broken authentication (~20%)
3. XSS (~15%)
4. Broken access control (~15%)
5. Security misconfiguration (~10%)
6. Everything else (~15%)

Fixing categories 1-4 would achieve the 80% goal.
</think>

**Secure Coding Training Program — 3 Months, 2 Hours/Week**

**Program Design Principles:**
- Each session: 30 min learning, 30 min hands-on, 60 min applying to real code
- Focus on the 4 vulnerability categories that cause 80% of issues
- Automate detection where possible (don't rely on memory)
- Measure with before/after vulnerability scans

---

**Month 1: The Big Four Vulnerabilities**

```
Week 1: SQL Injection (2 hours)
  30 min: Live demo — exploit SQL injection on a test app
    (Nothing motivates security like seeing your app get hacked)
  30 min: Hands-on — each developer finds and fixes SQLi in sample code
  60 min: Each developer audits their own codebase for string-formatted SQL

  Deliverable: Zero string-formatted SQL queries in the codebase.
  All queries use parameterized statements.

  Automated enforcement:
    - Add Bandit (Python) or ESLint security plugin to CI/CD
    - Block PRs with SQL string formatting

Week 2: XSS — Cross-Site Scripting (2 hours)
  30 min: Demo — inject a script tag that steals session cookies
  30 min: Hands-on — find and fix XSS in sample code
  60 min: Audit templates/frontend for unescaped user output

  Deliverable: All user input is escaped before rendering.
  CSP headers added to all responses.

  Automated enforcement:
    - CSP header in middleware (blocks inline scripts)
    - Template linter that warns on unescaped output

Week 3: Broken Authentication (2 hours)
  30 min: Demo — crack weak password hashes, session fixation
  30 min: Review team's auth implementation against checklist:
    - [ ] Passwords hashed with bcrypt/Argon2 (not SHA/MD5)
    - [ ] Rate limiting on login endpoint
    - [ ] Session rotation on login
    - [ ] Secure cookie flags (httpOnly, Secure, SameSite)
    - [ ] Account lockout after failed attempts
  60 min: Fix any checklist items that fail

  Deliverable: Authentication passes all checklist items.

Week 4: Broken Access Control / IDOR (2 hours)
  30 min: Demo — access another user's data by changing the ID in the URL
  30 min: Group exercise — list all endpoints and check authorization
  60 min: Add authorization checks to any unprotected endpoints

  Deliverable: Every endpoint verifies the requesting user owns
  the requested resource.

  Test: Log in as User A, try to access User B's data via API.
  Should return 403 for every endpoint.
```

**Month 2: Secure Development Workflow**

```
Week 5: Security headers and configuration (2 hours)
  30 min: Run securityheaders.com scan, review results as team
  30 min: Implement all recommended headers in middleware
  60 min: Review production configuration:
    - Debug mode off
    - Default credentials changed
    - Unnecessary ports closed
    - Error messages don't expose internals

Week 6: Input validation (2 hours)
  30 min: Demo — send malformed input to endpoints, show crashes
  30 min: Team defines validation schemas for all endpoints
  60 min: Implement schema validation (Pydantic, Marshmallow, Joi)

  Rule: Every endpoint must validate every input field.
  No raw request.form or request.body without validation.

Week 7: Dependency security (2 hours)
  30 min: Demo — show known CVEs in common packages
  30 min: Run dependency audit, review findings
  60 min: Set up Dependabot/Snyk, fix critical vulnerabilities

  Automated enforcement:
    - CI/CD blocks deploys with critical dependency vulnerabilities
    - Weekly Slack notification of new vulnerability alerts

Week 8: Secure code review checklist (2 hours)
  30 min: Introduce the team security review checklist
  30 min: Practice — review 3 PRs using the checklist
  60 min: Each developer reviews one of their own recent PRs

  PR Security Checklist:
  - [ ] No SQL string formatting
  - [ ] All user input validated
  - [ ] Auth/authz checked on new endpoints
  - [ ] No secrets in code
  - [ ] Sensitive data not logged
  - [ ] Error messages don't expose internals
  - [ ] Dependencies audited
```

**Month 3: Testing and Measurement**

```
Week 9: Security testing (2 hours)
  30 min: Intro to OWASP ZAP (automated vulnerability scanner)
  30 min: Run ZAP against the application, review findings
  60 min: Fix the top 5 findings from the scan

Week 10: Writing security tests (2 hours)
  30 min: How to write tests for security:
    - Test that unauthorized users get 403
    - Test that SQL injection payloads don't work
    - Test that XSS payloads are escaped
    - Test rate limiting works
  60 min: Each developer writes 3 security tests for their code
  30 min: Review tests as a team

Week 11: Measure improvement (2 hours)
  30 min: Run OWASP ZAP again, compare to Week 9 results
  30 min: Run static analysis, compare to Month 1 baseline
  60 min: Document remaining vulnerabilities and prioritize fixes

  Expected results:
  - OWASP ZAP findings: 80% reduction
  - Static analysis warnings: 90% reduction
  - Manual audit: no critical vulnerabilities

Week 12: Sustain and improve (2 hours)
  30 min: Retrospective — what worked, what didn't
  30 min: Set up ongoing cadence:
    - Security review checklist required for all PRs
    - Monthly ZAP scan with tracked metrics
    - Quarterly dependency audit
    - Annual penetration test
  60 min: Document the team's security standards and onboarding guide

Milestone: 80% reduction in detected vulnerabilities.
Security checks integrated into CI/CD and PR review process.
```

**Measurement framework:**
| Metric | Baseline (Week 0) | Target (Week 12) |
|--------|-------------------|-------------------|
| OWASP ZAP findings (critical/high) | Measure | 80% reduction |
| Static analysis warnings | Measure | 90% reduction |
| Unprotected endpoints | Audit count | 0 |
| PRs with security review | 0% | 100% |
| Dependency vulnerabilities (critical) | Measure | 0 |'''
    ),
    (
        "thinking/auto-curriculum-security-threat-modeling",
        r'''Teach me how to do threat modeling for a web application. I want a practical approach I can use on my current project, not an academic exercise.''',
        r'''<think>
Most threat modeling guides are overly academic (STRIDE, DREAD, attack trees). For a developer who wants to apply it TODAY, I need a practical approach:

1. Map the system
2. List the entry points
3. For each entry point, ask "what could go wrong?"
4. Prioritize and fix

I'll use a real web app as the example throughout.
</think>

**Practical Threat Modeling for Web Developers**

*A 4-step process you can apply to your project today.*

**Step 1: Map Your System (30 minutes)**

```
Draw every component and data flow:

Example — e-commerce application:

[Browser] ──HTTPS──> [Load Balancer]
                         │
                    [Web Server (Flask)]
                    /    │       \
              [PostgreSQL] [Redis]  [S3]
                    │               │
              [User data,    [Product images,
               Orders,       Invoices]
               Payments]
                    │
              [Stripe API] ──> [Payment processing]
                    │
              [SendGrid] ──> [Transactional emails]

For each component, note:
- What data does it store?
- Who can access it?
- How does data flow in and out?
```

**Step 2: List Entry Points (15 minutes)**

```
Every place external input enters your system:

1. Authentication endpoints:
   - POST /login (username, password)
   - POST /register (email, name, password)
   - POST /forgot-password (email)
   - POST /reset-password (token, new password)

2. User data endpoints:
   - GET/PUT /api/profile (user data)
   - POST /api/upload (profile picture)
   - GET /api/orders (user's orders)

3. Public endpoints:
   - GET /api/products (product catalog)
   - GET /api/search?q=... (search)

4. Payment endpoints:
   - POST /api/checkout (card info via Stripe)
   - POST /api/webhook/stripe (Stripe webhook)

5. Admin endpoints:
   - GET/PUT/DELETE /admin/* (admin panel)

6. Infrastructure:
   - Database connection string
   - Redis connection
   - S3 bucket permissions
   - API keys for Stripe, SendGrid
```

**Step 3: Ask "What Could Go Wrong?" (1-2 hours)**

```
For each entry point, ask these 4 questions:

Q1: Can someone ACCESS something they shouldn't?
  - /api/orders → Can User A see User B's orders? (IDOR)
  - /admin/* → Can non-admin users access admin pages?
  - S3 bucket → Is it publicly accessible?
  - Database → Can the web server access all tables? (least privilege)

Q2: Can someone MODIFY something they shouldn't?
  - PUT /api/profile → Can User A modify User B's profile?
  - POST /api/checkout → Can someone change the price client-side?
  - Stripe webhook → Can someone forge a webhook?
  - Database → Can SQL injection modify data?

Q3: Can someone BREAK or DOS the system?
  - POST /login → Can someone brute-force passwords?
  - POST /api/upload → Can someone upload a 10GB file?
  - GET /api/search → Can a complex query slow the database?
  - POST /register → Can someone create millions of accounts?

Q4: Can someone STEAL sensitive data?
  - Error pages → Do they expose stack traces or database info?
  - Logs → Do they contain passwords or credit card numbers?
  - S3 → Are invoice PDFs publicly accessible?
  - Database backups → Are they encrypted?

Organize findings in a table:

| Entry point | Threat | Likelihood | Impact | Priority |
|-------------|--------|-----------|--------|----------|
| POST /login | Credential stuffing | High | High | P0 |
| GET /api/orders | IDOR — view others' orders | Medium | High | P0 |
| POST /api/upload | Unrestricted file upload | Medium | Critical | P0 |
| S3 bucket | Public access to invoices | Low | Critical | P1 |
| POST /api/checkout | Price manipulation | Low | High | P1 |
| GET /api/search | Search DoS via complex queries | Medium | Medium | P2 |
| Error pages | Stack trace exposure | High | Low | P2 |
```

**Step 4: Prioritize and Fix (ongoing)**

```
Priority matrix:

                    High Impact    Low Impact
High Likelihood     P0 (fix NOW)   P1 (fix soon)
Low Likelihood      P1 (fix soon)  P2 (fix when possible)

For the example above:

P0 (fix this week):
  1. Rate limit login endpoint (credential stuffing)
  2. Add authorization check on /api/orders (IDOR)
  3. Validate file uploads (type, size, filename)

P1 (fix this month):
  4. Make S3 bucket private, use signed URLs
  5. Verify price server-side in checkout
  6. Validate Stripe webhooks with signature verification

P2 (fix this quarter):
  7. Add query timeout/complexity limits for search
  8. Remove stack traces from production error pages
  9. Audit log contents for sensitive data

Track progress:
- Run this process on every major feature
- Re-run every quarter for the full application
- Update when architecture changes
```

**Template you can copy:**

```markdown
## Threat Model: [Feature/System Name]
Date: YYYY-MM-DD
Author: [name]

### System Map
[diagram or description]

### Entry Points
1. [endpoint/input] — [what data it handles]

### Threats Found
| # | Entry Point | Threat | L | I | Priority | Status |
|---|------------|--------|---|---|----------|--------|
| 1 | POST /login | Credential stuffing | H | H | P0 | Fixed |

### Mitigations Applied
- [ ] Threat 1: [what was done]
- [ ] Threat 2: [what was done]

### Next Review Date: YYYY-MM-DD
```

**When to threat model:**
- New feature with user input or data access
- New third-party integration
- Architecture change
- After a security incident
- Quarterly review of the full system'''
    ),
    (
        "thinking/auto-curriculum-security-devops-security",
        r'''Design a learning path for securing the deployment pipeline and infrastructure. The team deploys to AWS using GitHub Actions and Docker but has never done a security review of their infrastructure.''',
        r'''<think>
DevOps security (DevSecOps) has specific concerns:
1. CI/CD pipeline security (secrets in builds, supply chain)
2. Container security (image scanning, runtime)
3. Cloud infrastructure security (IAM, network, storage)
4. Monitoring and incident response

Priority order: secrets management > IAM > container security > network > monitoring
</think>

**DevOps Security Learning Path**

*For teams deploying to AWS with GitHub Actions and Docker.*

**Phase 1: Secrets and CI/CD Security (Week 1-2)**

```
Week 1: Secrets management (highest priority)

  Audit current state:
  - Are any secrets in git? (Run: gitleaks detect --source .)
  - Are secrets in Dockerfiles or docker-compose.yml?
  - Are secrets in GitHub Actions workflow files?
  - Are secrets hardcoded in application code?

  Fix:
  1. Move all secrets to GitHub Secrets (for CI/CD)
  2. Use AWS Secrets Manager or SSM Parameter Store (for runtime)
  3. Never pass secrets as build args in Docker
  4. Add pre-commit hook to detect secrets before they're committed

  GitHub Actions secrets:
    # BAD: Secret in workflow file
    env:
      DATABASE_URL: postgresql://admin:password@db:5432/app

    # GOOD: Use GitHub Secrets
    env:
      DATABASE_URL: ${{ secrets.DATABASE_URL }}

  Docker secrets:
    # BAD: Secret in Dockerfile
    ENV API_KEY=sk_test_abc123

    # GOOD: Pass at runtime
    docker run -e API_KEY=$API_KEY myimage

Week 2: CI/CD pipeline hardening

  1. Pin GitHub Actions versions (prevent supply chain attacks):
     # BAD: uses latest version (could be compromised)
     uses: actions/checkout@main

     # GOOD: pin to specific SHA
     uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11

  2. Add security scanning to pipeline:
     - Dependency scanning: npm audit, pip audit
     - Container image scanning: trivy, snyk container
     - Static analysis: bandit (Python), eslint-plugin-security (JS)
     - Secret scanning: gitleaks

  3. Least privilege for CI/CD:
     - GitHub Actions GITHUB_TOKEN: minimum required permissions
     - AWS credentials: specific IAM role, not admin
     - Don't give CI/CD access to production database

  4. Branch protection:
     - Require PR reviews before merge to main
     - Require status checks (tests + security scan) to pass
     - No force pushes to main
     - Signed commits (optional but recommended)
```

**Phase 2: Container Security (Weeks 3-4)**

```
Week 3: Docker image hardening

  1. Use minimal base images:
     # BAD: Full Ubuntu with unnecessary tools
     FROM ubuntu:latest

     # GOOD: Minimal image
     FROM python:3.11-slim
     # BETTER: Distroless (no shell, no package manager)
     FROM gcr.io/distroless/python3

  2. Don't run as root:
     RUN adduser --disabled-password appuser
     USER appuser

  3. Multi-stage builds (smaller, fewer vulnerabilities):
     FROM python:3.11-slim AS builder
     COPY requirements.txt .
     RUN pip install --target=/deps -r requirements.txt

     FROM python:3.11-slim
     COPY --from=builder /deps /deps
     COPY app/ /app/
     USER appuser
     CMD ["python", "/app/main.py"]

  4. Scan images for vulnerabilities:
     trivy image myapp:latest
     # Fix: update base image, update dependencies

Week 4: Container runtime security

  1. Read-only filesystem:
     docker run --read-only --tmpfs /tmp myapp

  2. Drop capabilities:
     docker run --cap-drop ALL --cap-add NET_BIND_SERVICE myapp

  3. Resource limits:
     docker run --memory=512m --cpus=1 myapp

  4. No privileged mode:
     # NEVER in production:
     docker run --privileged myapp
```

**Phase 3: AWS Security (Weeks 5-7)**

```
Week 5: IAM — Identity and Access Management

  1. Principle of least privilege:
     - Each service gets its own IAM role
     - Each role has minimum required permissions
     - No IAM user with AdministratorAccess for applications

  2. Review existing IAM:
     - List all IAM users and roles
     - Check for unused credentials (AWS Credential Report)
     - Remove any access keys older than 90 days
     - Enable MFA on all human IAM users

  3. Service roles (not access keys):
     # BAD: Access keys in environment variables
     AWS_ACCESS_KEY_ID=AKIA...
     AWS_SECRET_ACCESS_KEY=...

     # GOOD: IAM role attached to EC2/ECS/Lambda
     # No credentials to manage or rotate

Week 6: Network security

  1. VPC design:
     - Public subnet: only load balancer
     - Private subnet: application servers
     - Private subnet: database (no internet access)
     - NAT gateway for private subnet outbound traffic

  2. Security groups:
     - App server: allow port 443 from load balancer only
     - Database: allow port 5432 from app server security group only
     - No security group with 0.0.0.0/0 on database ports
     - Review: aws ec2 describe-security-groups

  3. S3 bucket security:
     - Block public access (account-level setting)
     - Use bucket policies for fine-grained access
     - Enable access logging
     - Enable server-side encryption

Week 7: Monitoring and alerting

  1. AWS CloudTrail:
     - Enable for all regions
     - Log all API calls
     - Alert on: root account login, IAM changes, security group changes

  2. AWS GuardDuty:
     - Enable threat detection
     - Alerts for: compromised credentials, crypto mining, unusual API calls

  3. Application logging:
     - CloudWatch Logs for application logs
     - Set up alerts for error rate spikes
     - Log retention policy (90 days for security, longer for compliance)

  4. Cost monitoring (security indicator):
     - Unexpected cost spikes often indicate compromised resources
     - Set billing alerts at 150% of normal spend
```

**Phase 4: Ongoing Security (Week 8)**

```
Establish recurring security practices:

Daily:
  - CI/CD security scans run on every commit (automated)
  - Review any GuardDuty alerts

Weekly:
  - Review dependency vulnerability alerts
  - Check for new CVEs affecting your stack

Monthly:
  - IAM access review (remove unused credentials)
  - Review CloudTrail logs for anomalies
  - Update base Docker images
  - Run container image scan on all production images

Quarterly:
  - Full infrastructure security review
  - Rotate all long-lived credentials
  - Review and update security group rules
  - Test disaster recovery procedures

Annually:
  - External penetration test
  - Review compliance requirements
  - Update security policies and documentation
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
