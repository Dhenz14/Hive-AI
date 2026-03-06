"""Phase 4F: Self-Improvement — Quality Assurance (Part 3)"""

PAIRS = [
    (
        "thinking/auto-qa-e2e-code-review",
        r'''I completed a multi-step task: set up a Flask app with authentication. Here's what I built:

app.py — Flask app with login/register routes
models.py — User model with password stored as plaintext
routes.py — API routes with no CSRF protection
templates/ — Login and register HTML forms
requirements.txt — flask, sqlite3
config.py — SECRET_KEY = "dev" and DEBUG = True

Run a full quality review.''',
        r'''<think>
Let me do a systematic end-to-end quality review covering security, correctness, completeness, and production readiness.

SECURITY REVIEW:
1. Plaintext passwords in models.py — CRITICAL. Passwords must be hashed. If the database is compromised, all user credentials are exposed. Must use bcrypt or werkzeug.security.generate_password_hash.
2. No CSRF protection — HIGH. Forms are vulnerable to cross-site request forgery. Flask-WTF provides CSRF out of the box.
3. SECRET_KEY = "dev" — CRITICAL. A predictable secret key means session cookies can be forged. Anyone can impersonate any user.
4. DEBUG = True — HIGH. Exposes the Werkzeug debugger, which allows arbitrary code execution on the server. Never in production.
5. No mention of HTTPS, secure cookie flags, or session configuration.

CORRECTNESS REVIEW:
6. sqlite3 in requirements.txt — sqlite3 is part of Python's standard library, doesn't need to be in requirements.txt. Also, SQLite is not suitable for production with concurrent users.
7. No ORM mentioned — if using raw SQL, are queries parameterized? Risk of SQL injection.
8. No mention of input validation on register form.

COMPLETENESS REVIEW:
9. No password reset functionality.
10. No email verification.
11. No logout route mentioned.
12. No session timeout configuration.
13. No rate limiting on login (brute force vulnerability).
14. No error handling or custom error pages.

PRODUCTION READINESS:
15. No WSGI server — Flask's built-in server is development only.
16. No database migrations setup.
17. No logging configuration.
18. No environment-based configuration (dev vs prod).
</think>

**End-to-End Quality Review — Flask Auth Application**

**Overall Score: 2/10 — NOT safe to deploy**

---

**CRITICAL Issues (must fix before any deployment):**

**1. Plaintext password storage** (`models.py`)
This is the most severe vulnerability. If the database is accessed by an attacker — via SQL injection, backup exposure, or server compromise — every user's password is immediately compromised. Users who reuse passwords (most people) are now vulnerable across all their accounts.

```python
# WRONG: password stored as-is
user.password = request.form['password']

# CORRECT: hash with bcrypt
from werkzeug.security import generate_password_hash, check_password_hash
user.password_hash = generate_password_hash(request.form['password'])
```

**2. Hardcoded SECRET_KEY = "dev"** (`config.py`)
Flask session cookies are signed with this key. A known key means anyone can forge session cookies and impersonate any user, including admins. Generate a random key: `python -c "import secrets; print(secrets.token_hex(32))"` and load it from an environment variable.

**3. DEBUG = True** (`config.py`)
The Werkzeug debugger allows arbitrary Python code execution from the browser. This is a remote code execution vulnerability. Set `DEBUG = False` in production and use environment variables to toggle.

---

**HIGH Issues (fix before user-facing deployment):**

**4. No CSRF protection** (`routes.py`) — Login and register forms can be exploited via cross-site request forgery. Add `Flask-WTF` which provides CSRF tokens automatically.

**5. No rate limiting on login** — An attacker can brute-force passwords. Add `Flask-Limiter` with a limit like 5 attempts per minute per IP on the login route.

**6. SQLite for production** — SQLite does not handle concurrent writes. Under load, users will see "database is locked" errors. Use PostgreSQL for any multi-user deployment.

---

**MEDIUM Issues (fix for production quality):**

| # | Issue | Fix |
|---|-------|-----|
| 7 | No WSGI server | Use gunicorn or waitress, not Flask's dev server |
| 8 | No input validation | Validate email format, password strength on register |
| 9 | No logout route | Add session clearing endpoint |
| 10 | No session timeout | Configure `PERMANENT_SESSION_LIFETIME` |
| 11 | No secure cookie flags | Set `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY` |
| 12 | No error handling | Add custom 404/500 handlers, never expose tracebacks |
| 13 | No logging | Configure Python logging for auth events |
| 14 | No env-based config | Use python-dotenv, separate dev/prod configs |

**Minimum viable fix order:** Items 1, 2, 3, then 4, 5, 6, then 7-14. The first three are actively dangerous; nothing else matters until those are resolved.'''
    ),
    (
        "thinking/auto-qa-tutorial-verification",
        r'''I wrote a tutorial on deploying a Node.js app to AWS. Verify it's complete and accurate.

My tutorial steps:
1. Create an EC2 instance (Ubuntu, t2.micro)
2. SSH into the instance
3. Install Node.js with "sudo apt install nodejs"
4. Clone your repo with git
5. Run "npm install" to install dependencies
6. Run "node app.js" to start the server
7. Open port 3000 in the EC2 security group
8. Access your app at http://<public-ip>:3000

"That's it! Your app is now deployed to production."''',
        r'''<think>
Let me verify this tutorial step by step against completeness and accuracy criteria.

ACCURACY CHECK (step by step):

Step 1: Create EC2 instance, Ubuntu t2.micro — Accurate. t2.micro is free tier eligible. Good starting point. But no mention of selecting a key pair for SSH.

Step 2: SSH into instance — Missing: how to use the .pem key file, the correct username (ubuntu@), chmod 400 on the key.

Step 3: "sudo apt install nodejs" — PROBLEM. Ubuntu's default repo has very old Node.js versions (often v12 or v14, years out of support). The correct approach is to use NodeSource repo or nvm for a current LTS version. Also missing: apt update before install, and npm is often a separate package on Ubuntu (nodejs doesn't include npm by default in some versions).

Step 4: Clone repo — Needs git installed first (may not be on base Ubuntu AMI). Also, if it's a private repo, authentication needs to be set up (SSH key or token).

Step 5: npm install — Assumes npm is installed (see step 3 issue). Otherwise fine.

Step 6: "node app.js" — MAJOR PROBLEM. This runs in the foreground of the SSH session. When the user disconnects SSH, the process dies. The app is not actually deployed — it's temporarily running. Need a process manager (PM2, systemd).

Step 7: Open port 3000 — Accurate step, but exposing a raw Node.js process on a non-standard port is not production practice.

Step 8: HTTP access — Works but: HTTP not HTTPS (no TLS), non-standard port, no domain name.

COMPLETENESS CHECK:
Missing critical elements:
- Process manager (PM2/systemd) to keep app running
- Reverse proxy (nginx) to handle HTTPS, port 80/443, and load
- SSL/TLS certificate (Let's Encrypt)
- Environment variables and secrets management
- Firewall configuration (ufw)
- Monitoring and logging
- Auto-restart on crash/reboot
- Database setup (if needed)
- Updates and security patches

The tutorial claims "your app is now deployed to production" but this setup will die when SSH disconnects and has no HTTPS, no monitoring, and no resilience.
</think>

**Tutorial Verification Report — Node.js AWS Deployment**

**Verdict: INCOMPLETE and MISLEADING — Not production-ready despite claiming to be**

---

**Step-by-Step Accuracy Audit:**

| Step | Accuracy | Issue |
|------|----------|-------|
| 1. Create EC2 | Partial | Missing: key pair creation, security group setup, IAM role |
| 2. SSH in | Partial | Missing: `chmod 400 key.pem`, `ssh -i key.pem ubuntu@ip` syntax |
| 3. Install Node.js | **Wrong** | `apt install nodejs` gives an ancient version (v12-14). Use NodeSource or nvm for LTS |
| 4. Clone repo | Partial | Missing: `apt install git`, private repo auth setup |
| 5. npm install | Partial | npm may not be installed (separate package on Ubuntu) |
| 6. `node app.js` | **Wrong** | Runs in foreground — dies when SSH disconnects. Not a deployment. |
| 7. Open port 3000 | Correct | But non-standard port exposed directly is not best practice |
| 8. HTTP access | Correct | But HTTP only — no encryption in transit |

**Critical Missing Steps:**

**1. Process management (the tutorial's fatal flaw).** When the user closes their terminal, `node app.js` receives SIGHUP and terminates. The "deployment" lasts exactly as long as the SSH session. Fix:

```bash
# Install PM2
npm install -g pm2
pm2 start app.js
pm2 startup    # auto-restart on reboot
pm2 save
```

**2. Reverse proxy.** Exposing Node.js directly on port 3000 is fragile. Node.js should sit behind nginx, which handles TLS termination, static file serving, request buffering, and port 80/443 routing.

**3. HTTPS/TLS.** The tutorial serves over plain HTTP. Any data (passwords, tokens, personal information) is transmitted in cleartext. Let's Encrypt with certbot provides free certificates in minutes.

**4. Node.js version.** The `apt install nodejs` command installs a version that is likely end-of-life. Correct approach:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**5. Environment configuration.** No mention of environment variables (PORT, DATABASE_URL, secrets). Hardcoded values in code or missing env vars will cause runtime failures.

**Missing sections the tutorial needs:**

- Firewall setup (`ufw allow 22,80,443`)
- nginx reverse proxy configuration
- SSL certificate with Let's Encrypt
- Environment variable management (`.env` file or AWS Parameter Store)
- Log management (PM2 logs or CloudWatch)
- Basic monitoring (uptime checks at minimum)
- Deployment updates strategy (how to deploy new versions)

**Corrected tutorial claim:** "Your app is now running temporarily for testing. See the next sections for making this production-ready." The tutorial in its current form is a valid development/testing guide but dangerously incomplete as a production deployment guide.'''
    ),
    (
        "thinking/auto-qa-requirements-verification",
        r'''I designed a system for a user who asked: "Build me an e-commerce checkout system."

My design:
- Shopping cart stored in the user's session
- Single "Place Order" button that charges the credit card and creates the order
- Orders stored in a PostgreSQL table
- Email confirmation sent after successful charge

Check my design for missing requirements.''',
        r'''<think>
Let me systematically check this design against the full lifecycle of an e-commerce checkout, identifying missing requirements.

The user asked for a "checkout system." Let me enumerate what a checkout system needs to handle:

FUNCTIONAL REQUIREMENTS CHECK:

1. Cart management — "stored in session"
   - What happens if the session expires mid-shopping? Cart lost.
   - What about logged-in users switching devices? Cart not synced.
   - What about cart item validation (is the item still in stock when they check out)?

2. Payment processing — "charges the credit card"
   - No mention of a payment gateway (Stripe, PayPal). Direct credit card handling requires PCI DSS compliance.
   - No mention of payment intent / two-step capture (authorize then capture).
   - What if the charge succeeds but order creation fails? Money taken, no order record. CRITICAL.
   - No mention of idempotency — double-clicking "Place Order" could charge twice.
   - No support for multiple payment methods.

3. Order creation — "stored in PostgreSQL"
   - No order status workflow (pending, confirmed, shipped, delivered, cancelled).
   - No order items table (just an orders table?).
   - No price snapshotting — if product price changes after order, what price is recorded?

4. Confirmation — "email sent after successful charge"
   - What if email sending fails? Is the order still valid? Yes, but user doesn't know.
   - No order confirmation page/receipt shown to user.
   - No order tracking or status page.

MISSING REQUIREMENTS:

5. Inventory management — No stock checking. Overselling possible.
6. Tax calculation — No mention of tax.
7. Shipping — No shipping address, options, or cost calculation.
8. Discounts/coupons — No promo code support.
9. Transaction atomicity — Charge + order creation must be atomic or have compensation.
10. Address validation — No shipping/billing address handling.
11. Guest checkout vs authenticated — Unclear.
12. Refunds/cancellations — No reverse flow.
13. Failed payment handling — No retry or alternative payment.
14. Price consistency — Cart prices could change between adding and checkout.
15. Concurrent purchases — Race condition on last-in-stock item.
</think>

**Requirements Verification Report — E-commerce Checkout System**

**Coverage Score: 3/10 — Covers the happy path only, missing critical failure and edge case handling**

---

**What the design covers:**
The design addresses the simplest possible happy path: user has items in cart, pays with credit card, order is created, email is sent. This is roughly 20% of what a checkout system must handle.

**CRITICAL Missing Requirements:**

**1. Payment-Order Atomicity**
The design says "charge credit card AND create order" as one step. What happens when the charge succeeds but the database insert fails (network error, constraint violation, server crash)? The customer's money is taken but no order exists. This is the single most important problem in checkout design. Solution: create the order in "pending" state first, then charge, then update to "confirmed." If the charge fails, mark the order as "payment_failed."

**2. Idempotency / Double-Submit Protection**
No protection against the user clicking "Place Order" twice. Two charges, two orders. This happens constantly in production — users double-click, browsers retry on timeout, network glitches cause duplicates. Solution: generate an idempotency key before the charge, reject duplicate submissions.

**3. Inventory Verification**
No stock check at checkout time. Two users can simultaneously buy the last item, resulting in overselling. The cart was created minutes or hours ago — stock could have changed. Solution: verify and reserve inventory atomically at checkout time, using database-level locking.

**4. Shipping and Tax**
An e-commerce checkout that collects no shipping address, calculates no shipping cost, and computes no tax is incomplete for any physical goods scenario. Even digital goods require tax calculation in many jurisdictions.

**IMPORTANT Missing Requirements:**

| # | Requirement | Impact of Omission |
|---|------------|-------------------|
| 5 | Price snapshot at order time | Product price changes retroactively alter past orders |
| 6 | Order status workflow | No way to track pending/shipped/delivered/refunded |
| 7 | Refund/cancellation flow | No way to reverse a transaction |
| 8 | Session-based cart expiry | Users lose carts unexpectedly; no persistent cart for logged-in users |
| 9 | Payment gateway integration | Direct card handling requires PCI DSS Level 1 compliance — use Stripe/PayPal |
| 10 | Failed payment UX | No retry flow, no alternative payment method option |
| 11 | Order confirmation page | User sees nothing after purchase; relies entirely on email delivery |
| 12 | Guest vs authenticated checkout | Unclear if login is required |

**Minimum Viable Checkout Design Should Include:**

```
1. Cart: persistent (DB-backed for logged-in users), with price locking
2. Checkout flow: address -> shipping method -> tax calc -> payment -> confirm
3. Payment: Stripe/PayPal (handles PCI), idempotency keys, authorize-then-capture
4. Order: pending -> confirmed -> shipped -> delivered state machine
5. Inventory: reserve on checkout, release on failure/cancellation
6. Confirmation: page + email (email failure must not block order)
7. Error handling: payment failure, stock unavailable, timeout recovery
```'''
    ),
    (
        "thinking/auto-qa-refactoring-verification",
        r'''I refactored code for a user. Verify the refactoring preserved behavior.

Original:
def process_data(items):
    result = []
    for item in items:
        if item['type'] == 'A':
            val = item['value'] * 2
            if val > 100:
                val = 100
            result.append({'name': item['name'], 'value': val})
        elif item['type'] == 'B':
            val = item['value'] * 3
            if val > 100:
                val = 100
            result.append({'name': item['name'], 'value': val})
    return result

Refactored:
def process_data(items):
    multipliers = {'A': 2, 'B': 3}
    return [
        {'name': item['name'], 'value': min(item['value'] * multipliers[item['type']], 100)}
        for item in items
        if item['type'] in multipliers
    ]''',
        r'''<think>
Let me systematically verify that the refactored code preserves the original behavior by analyzing edge cases and logical equivalence.

LOGICAL EQUIVALENCE ANALYSIS:

Original logic for type 'A':
1. val = item['value'] * 2
2. if val > 100: val = 100
3. append {'name': item['name'], 'value': val}

Refactored logic for type 'A':
1. min(item['value'] * 2, 100)
2. Produces {'name': item['name'], 'value': result}

Is min(x, 100) equivalent to "if x > 100: x = 100"?
- When x > 100: both produce 100. Correct.
- When x == 100: original keeps 100 (condition is >100, not >=). min(100, 100) = 100. Correct.
- When x < 100: both keep x. Correct.
- When x is negative: original keeps negative (not > 100). min(negative, 100) = negative. Correct.

Same analysis applies to type 'B' with multiplier 3.

EDGE CASE ANALYSIS:

1. item['type'] not 'A' or 'B' (e.g., 'C'):
   - Original: skips (no elif/else match, nothing appended).
   - Refactored: `if item['type'] in multipliers` filters it out. Correct.

2. item['type'] is missing (KeyError):
   - Original: item['type'] would raise KeyError at the if statement.
   - Refactored: item['type'] would raise KeyError at `multipliers[item['type']]`... wait, actually the `if item['type'] in multipliers` check comes first in the list comprehension. Actually no — in the list comprehension, the `if` clause is evaluated first (it's a filter), then the expression. So item['type'] is accessed in the filter. If item has no 'type' key, both raise KeyError. Same behavior.

3. item['value'] is missing:
   - Original: raises KeyError at `item['value'] * 2`.
   - Refactored: raises KeyError at `item['value'] * multipliers[...]`. Same behavior.

4. item['name'] is missing:
   - Both raise KeyError at item['name']. Same behavior.

5. Empty list:
   - Original returns []. Refactored returns []. Same.

6. item['value'] is None:
   - Original: None * 2 raises TypeError.
   - Refactored: None * multipliers['A'] raises TypeError. Same.

7. item['value'] is a float:
   - Original: float * 2 = float, comparison with 100 works.
   - Refactored: min(float, 100) works. But wait — min(float, int) returns... the smaller one, preserving type. So if value is 40.5, type A: original gives 81.0, refactored gives min(81.0, 100) = 81.0. Same.

8. Order of items in output:
   - Original: iterates in order, appending matches.
   - Refactored: list comprehension iterates in order. Same order.

WAIT — I need to check one subtle thing. In the original, when type is not 'A' or 'B', the item is silently skipped. In the refactored version, `if item['type'] in multipliers` also skips it. But what if someone later adds type 'C' to the multipliers dict but forgets to handle it in the original? That's a future maintenance concern, not a current behavior difference.

VERDICT: The refactoring preserves behavior exactly. But let me check one more thing...

Actually, I realize there could be a difference with the `multipliers[item['type']]` lookup. If item['type'] is in the filter check but then the dict is somehow mutated between the check and the lookup... no, that's impossible in a single-threaded list comprehension.

The refactoring is correct.
</think>

**Refactoring Verification Report**

**Verdict: PASS — Behavior is preserved in all cases**

---

**Methodology:** I verified equivalence by analyzing the logical transformation, then testing against edge cases covering type matching, value boundaries, missing keys, and type coercion.

**Core Transformation Analysis:**

| Aspect | Original | Refactored | Equivalent? |
|--------|----------|------------|-------------|
| Type A multiplier | `* 2` | `multipliers['A']` = 2 | Yes |
| Type B multiplier | `* 3` | `multipliers['B']` = 3 | Yes |
| Capping at 100 | `if val > 100: val = 100` | `min(..., 100)` | Yes |
| Unknown type handling | Falls through if/elif (skipped) | `if item['type'] in multipliers` (filtered) | Yes |
| Output structure | `{'name': ..., 'value': ...}` | `{'name': ..., 'value': ...}` | Yes |
| Output ordering | Sequential append | List comprehension (same order) | Yes |

**Boundary value verification for `min(x, 100)` vs `if x > 100: x = 100`:**

- `x = 101`: original caps to 100, `min(101, 100)` = 100. Match.
- `x = 100`: original keeps 100 (condition is strictly `> 100`), `min(100, 100)` = 100. Match.
- `x = 99`: both keep 99. Match.
- `x = -50`: both keep -50. Match. (Note: negative values pass through uncapped in both versions — this may be an existing bug in the business logic, but the refactoring did not introduce it.)

**Edge case verification:**

| Edge Case | Original Behavior | Refactored Behavior | Match? |
|-----------|-------------------|---------------------|--------|
| Empty list `[]` | Returns `[]` | Returns `[]` | Yes |
| Type 'C' item | Silently skipped | Filtered out | Yes |
| Missing 'type' key | `KeyError` | `KeyError` | Yes |
| Missing 'value' key | `KeyError` | `KeyError` | Yes |
| Missing 'name' key | `KeyError` | `KeyError` | Yes |
| `value = None` | `TypeError` | `TypeError` | Yes |
| Float values | Preserved as float | Preserved as float | Yes |

**Quality Assessment of the Refactoring:**

The refactoring is well-executed. It reduces 10 lines to 4, eliminates code duplication (the capping logic was repeated), and makes it trivial to add new types (just add to the `multipliers` dict). The use of `min()` is a clean replacement for the cap pattern.

**One observation (not a bug):** The refactored code will raise `KeyError` if a new type is added to `multipliers` but the item is somehow missing the `'type'` key. This is identical to the original behavior, but worth noting that neither version validates input defensively. Both versions also allow negative values through the cap — if the business rule intends values to be in `[0, 100]`, a `max(0, min(..., 100))` clamp would be more correct. This is a pre-existing concern, not introduced by the refactoring.'''
    ),
    (
        "thinking/auto-qa-session-retrospective",
        r'''I answered 5 questions in a session. Do a retrospective on answer quality.

Q1: "What's the best programming language?" → I said "Python, because it's the most popular."
Q2: "How do I center a div in CSS?" → I gave 3 methods: flexbox, grid, and margin auto.
Q3: "Is MongoDB or PostgreSQL better?" → I said "MongoDB is better because it's newer."
Q4: "How do I handle errors in async JavaScript?" → I showed try/catch with async/await.
Q5: "Should I use microservices?" → I said "Yes, microservices are the modern best practice."''',
        r'''<think>
Let me do a quality retrospective on each answer, evaluating accuracy, helpfulness, and whether common pitfalls were avoided.

Q1: "What's the best programming language?" → "Python, because it's the most popular."
- This is a classic "it depends" question. Answering with a single language is reductive.
- "Most popular" is not the same as "best." Best for what? Web frontend (JavaScript), systems (Rust/C++), mobile (Swift/Kotlin), data science (Python/R), embedded (C).
- The answer should have asked about the use case, or explained that different languages excel at different things.
- Quality: POOR — oversimplified, no nuance, false premise accepted.

Q2: "How do I center a div in CSS?" → 3 methods: flexbox, grid, margin auto.
- This is a good, practical answer. Three methods cover most situations.
- Flexbox is the modern standard, grid works too, margin auto is the classic approach.
- Could be improved by noting which to prefer (flexbox is usually the go-to).
- Quality: GOOD — practical, multiple options, actionable.

Q3: "Is MongoDB or PostgreSQL better?" → "MongoDB is better because it's newer."
- Another "it depends" question answered with a definitive. Worse: "newer" is not a valid criterion for database selection.
- MongoDB is better for: document-oriented data, flexible schemas, horizontal scaling.
- PostgreSQL is better for: relational data, complex queries, ACID transactions, joins.
- The answer should discuss use cases, data model fit, and consistency requirements.
- Quality: POOR — false reasoning ("newer = better"), no context consideration.

Q4: "How do I handle errors in async JavaScript?" → try/catch with async/await.
- Correct and practical. try/catch is the standard pattern for async/await.
- Could be improved by also showing .catch() for promise chains, and discussing unhandled rejection handling.
- Quality: GOOD — correct, actionable, could be more complete.

Q5: "Should I use microservices?" → "Yes, microservices are the modern best practice."
- Another "it depends" answered definitively. Microservices are NOT a universal best practice.
- For small teams, startups, simple apps: monolith is usually better.
- The answer should ask about team size, system complexity, operational maturity.
- Quality: POOR — blanket recommendation without context, could lead to serious over-engineering.

Pattern I'm noticing: I handled specific technical questions well (Q2, Q4) but handled "should I" / "what's best" questions poorly (Q1, Q3, Q5) by giving definitive answers instead of exploring context.
</think>

**Session Quality Retrospective**

**Overall Session Score: 4.4/10**

---

**Per-Answer Breakdown:**

| # | Question | Score | Verdict |
|---|----------|-------|---------|
| Q1 | Best programming language | 2/10 | Oversimplified, false premise accepted |
| Q2 | Center a div in CSS | 8/10 | Good — practical, multiple methods |
| Q3 | MongoDB vs PostgreSQL | 1/10 | Wrong reasoning, no context |
| Q4 | Async error handling | 7/10 | Correct but could be more thorough |
| Q5 | Should I use microservices | 2/10 | Blanket recommendation, no context |

---

**Detailed Analysis:**

**Q1 (2/10): "Python because it's most popular."** Popularity is not the criterion for "best." The correct response is to ask what the user is building: web frontend demands JavaScript, systems programming demands Rust or C++, mobile needs Swift or Kotlin, data science favors Python. Answering "best language" with a single choice is like answering "best vehicle" with "Toyota Camry" — it ignores whether the person needs to haul lumber, race on a track, or cross an ocean.

**Q2 (8/10): Three CSS centering methods.** Solid answer. Flexbox (`display: flex; justify-content: center; align-items: center`), Grid (`display: grid; place-items: center`), and margin auto all work. Minor improvement: note that flexbox is the recommended default for most cases, and clarify that margin auto only centers horizontally (vertical centering requires a known height or flexbox).

**Q3 (1/10): "MongoDB is better because it's newer."** This is the session's worst answer. "Newer" is irrelevant to database selection. PostgreSQL (1996) is mature and actively developed with cutting-edge features (JSONB, CTEs, window functions). The correct approach: ask about the data model (relational vs document), consistency needs (ACID vs eventual), query complexity (joins vs denormalized reads), and scaling pattern (vertical vs horizontal).

**Q4 (7/10): try/catch with async/await.** Correct primary pattern. Could be strengthened by showing the `.catch()` alternative for promise chains, mentioning `Promise.allSettled()` for parallel operations, and noting the importance of global unhandled rejection handlers (`process.on('unhandledRejection', ...)` in Node.js).

**Q5 (2/10): "Yes, microservices are modern best practice."** This recommendation could cost a small team months of wasted effort. Microservices add network complexity, distributed debugging, deployment overhead, and operational burden. For most teams, a well-structured monolith is the correct starting point. The right response: ask about team size, current system complexity, and operational maturity before recommending an architecture.

---

**Pattern Identified:**

Specific technical "how-to" questions (Q2, Q4) were answered well. Open-ended "what's best" / "should I" questions (Q1, Q3, Q5) were answered poorly — with definitive recommendations instead of context-dependent guidance.

**Root cause:** Failing to recognize that advisory questions require understanding the user's context before giving recommendations. The model defaulted to giving a single "answer" when the correct response is to ask clarifying questions or present a decision framework.

**Corrective action for future sessions:**
1. When a question contains "best," "better," or "should I" — always ask about context or present a decision matrix, never give a single answer.
2. Avoid "newer is better" or "popular is better" reasoning — these are logical fallacies.
3. For technology comparisons, always frame as trade-offs, not rankings.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
