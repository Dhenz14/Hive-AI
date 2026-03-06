"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Reasoning (Part 2/4)
Security breach forensics, deployment failure analysis, 'works on my machine'
resolution, distributed system failure cascade."""

PAIRS = [
    (
        "thinking/causal-security-breach-forensics",
        "We found that someone accessed our admin panel and exported all customer data at 2 AM last night. The access came from a legitimate admin account. How do we investigate what happened?",
        r'''<think>
Let me work through this like a forensic investigation — systematically eliminating hypotheses.

The symptom: Admin account accessed the admin panel at 2 AM and exported customer data.

Possible causes:
1. The admin actually did it (insider threat)
2. Admin's credentials were compromised (phishing, credential stuffing, stolen session)
3. Admin's device was compromised (malware, RAT)
4. Session hijacking (XSS, session fixation)
5. Account takeover via password reset exploit
6. Shared credentials (multiple people use the same admin account)
7. API key or token leak (hardcoded in code, exposed in logs)

Causal chain analysis — what evidence would distinguish each cause?

Cause 1 (insider):
- Would login from admin's usual IP/device
- Might have escalated privileges recently
- Access pattern matches their normal behavior
Evidence to check: IP address, device fingerprint, recent privilege changes

Cause 2 (credential compromise):
- Login from unusual IP/location/device
- Multiple failed login attempts before success (brute force)
- Or no failed attempts but from new IP (phished credentials)
Evidence to check: Login history, IP geolocation, device fingerprint

Cause 3 (compromised device):
- Login from admin's usual device/IP
- But at unusual time (2 AM) for that admin
- Other unusual activity from that device
Evidence to check: Admin's device logs, antivirus alerts, other activity from same device

Cause 4 (session hijacking):
- Legitimate login at normal time, then activity continues from different IP
- Or session token appearing from a new IP without login
Evidence to check: Session creation vs usage IPs, referrer headers for XSS

Cause 5 (password reset):
- Password reset requested before the 2 AM access
- Reset might have gone to a different email (email compromise)
Evidence to check: Password reset logs, email delivery logs

Cause 6 (shared credentials):
- Multiple IPs use the same account
- Admin denies being online at 2 AM
Evidence to check: Login history for this account, interview the admin

Investigation order: Start with what we know, eliminate causes systematically.
</think>

**Forensic investigation framework — systematic cause elimination:**

**Step 1: Preserve evidence immediately**
```bash
# Capture logs before rotation
cp /var/log/app/audit.log /forensics/audit_$(date +%Y%m%d).log
cp /var/log/nginx/access.log /forensics/nginx_$(date +%Y%m%d).log

# Capture active sessions
redis-cli KEYS "session:*" > /forensics/active_sessions.txt

# Capture DB state
pg_dump --table=audit_log --where="created_at > '2024-01-14 00:00'" > /forensics/audit_db.sql

# DO NOT: restart services, clear logs, reset passwords yet
# Restarting destroys in-memory session data
```

**Step 2: Analyze the access pattern**
```sql
-- Who accessed what, when, from where?
SELECT
    timestamp,
    user_id,
    action,
    ip_address,
    user_agent,
    request_path,
    response_status
FROM audit_log
WHERE user_id = 'admin_42'
  AND timestamp BETWEEN '2024-01-15 00:00' AND '2024-01-15 06:00'
ORDER BY timestamp;

-- Compare to admin's normal pattern
SELECT
    DATE_TRUNC('hour', timestamp) AS hour,
    ip_address,
    COUNT(*) AS actions
FROM audit_log
WHERE user_id = 'admin_42'
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY hour, ip_address
ORDER BY hour;
```

**Step 3: Eliminate causes systematically**
```
Hypothesis                  | Evidence to check              | Verdict
----------------------------|-------------------------------|--------
1. Insider (admin did it)   | IP matches admin's usual IP?  | If YES → investigate further
                            | Time matches their patterns?   | 2 AM is unusual → suspicious
                            | Device fingerprint matches?    |

2. Credential compromise    | IP geolocation?               | If different country → likely
   (phishing/stuffing)      | Failed login attempts before? | Brute force evidence?
                            | Password found in breach DBs? | Check haveibeenpwned

3. Session hijacking        | Login from IP A, data export  | If different IPs → session
                            | from IP B?                     | was stolen
                            | XSS vulnerability in admin?   |

4. Compromised device       | Login from admin's IP but     | Malware remote control
                            | admin was asleep?              |

5. Shared credentials       | Other logins from different   | Multiple people, one account
                            | IPs using same account?        |

6. Password reset exploit   | Was password recently reset?  | Check password_reset_log
```

**Likely causal chain based on 2 AM access from unusual IP**:
```
Phase 1: Credential Acquisition
  Attacker obtains admin credentials via:
  a) Phishing email sent to admin → admin enters password on fake login page
  b) Credential stuffing (admin reused password from breached site)
  c) Social engineering → IT helpdesk resets password

Phase 2: Access
  Attacker logs in from their own IP at 2 AM (when monitoring is minimal)
  Uses admin panel normally — doesn't need to exploit anything

Phase 3: Exfiltration
  Downloads customer data export (built-in admin feature)
  Feature exists for legitimate business use — attacker uses it as intended

Phase 4: Exit
  Logs out or session expires
```

**Counterfactual — what would have prevented each step**:
```
If we had MFA:                    → Stolen password alone insufficient (Phase 1 blocked)
If we had IP allowlist for admin: → Login from unknown IP rejected (Phase 2 blocked)
If we had anomaly detection:      → 2 AM login from new IP flagged (Phase 2 detected)
If we had export rate limiting:   → Bulk export requires approval (Phase 3 blocked)
If we had per-admin audit alerts: → Admin notified of own login (Phase 2 detected)
```

**Immediate actions after investigation**:
```python
# 1. Contain — revoke all sessions for the compromised account
await session_store.delete_all(user_id="admin_42")

# 2. Rotate — force password reset for the admin
await user_repo.force_password_reset("admin_42")

# 3. Assess — determine scope of data exposure
exported_data = await audit_log.get_exported_data(
    user_id="admin_42",
    start=datetime(2024, 1, 15, 0, 0),
    end=datetime(2024, 1, 15, 6, 0),
)

# 4. Notify — if customer PII was exposed, legal/compliance notification required
if contains_pii(exported_data):
    await notify_compliance_team(exported_data)
    # GDPR: 72-hour notification requirement for data breaches

# 5. Remediate — add the missing controls
# → Enable MFA for all admin accounts
# → Add IP allowlisting for admin panel
# → Add anomaly detection on admin actions
# → Add approval workflow for bulk data exports
```'''
    ),
    (
        "thinking/causal-works-on-my-machine",
        "A developer says 'it works on my machine' but the feature is broken in CI and staging. They've verified the code is identical. What's different?",
        r'''<think>
"Works on my machine" is almost always caused by environment differences, not code differences. Let me systematically enumerate what can differ:

1. Runtime versions
   - Python 3.11 locally vs 3.9 in CI (walrus operator, match statement)
   - Node 20 locally vs 18 in CI (import assertions, structuredClone)
   - Different patch versions with different bug fixes

2. Dependencies
   - Local has pinned versions from lockfile
   - CI might have different package versions (missing lockfile commit)
   - Local has extra dev dependencies installed globally
   - OS-level packages differ (libssl, libc version)

3. Environment variables
   - .env file exists locally but not in CI
   - Different DATABASE_URL, API_KEY, etc.
   - Feature flags set differently

4. Data state
   - Local database has seed data or previous test artifacts
   - CI starts with empty database
   - Different data in different environments

5. File system
   - Case sensitivity: macOS is case-insensitive, Linux is case-sensitive
   - "import MyModule" works on macOS, fails on Linux if file is mymodule.py
   - Path separators: Windows \ vs Linux /
   - Line endings: CRLF vs LF

6. Network
   - Local can reach internal services
   - CI is in a different network (no access to internal APIs)
   - DNS resolution differs
   - Docker network configurations differ

7. Timing
   - Local machine is faster → race conditions don't manifest
   - CI runs tests in parallel → shared state conflicts
   - Different timezone configuration

8. OS differences
   - macOS vs Linux in CI
   - Different kernel version, system libraries
   - Locale settings (date formatting, string sorting)

9. Permissions
   - Running as root locally, non-root in CI
   - File permissions differ

10. Docker
    - Different Docker version
    - Docker Desktop vs Docker Engine
    - Volume mounting differences

The most common causes in my experience:
1. Missing environment variable (50%)
2. Dependency version mismatch (20%)
3. Case sensitivity (10%)
4. Runtime version difference (10%)
5. Other (10%)
</think>

**The code is identical. The ENVIRONMENT is not.** Here's how to systematically diff environments:

**Checklist — check in this order (most common causes first):**

```bash
# 1. ENVIRONMENT VARIABLES (50% of "works on my machine")
# Developer's .env file has values that CI doesn't have

# Local:
env | sort > /tmp/local_env.txt

# CI: add this step to your pipeline
env | sort > /tmp/ci_env.txt

# Compare:
diff /tmp/local_env.txt /tmp/ci_env.txt
# Missing: DATABASE_URL, API_KEY, FEATURE_FLAG_X

# Fix: Ensure all required env vars are set in CI configuration


# 2. DEPENDENCY VERSIONS (20% of cases)
# Local has newer packages than CI

# Check if lockfile is committed:
git status | grep "lock"  # poetry.lock, package-lock.json, Pipfile.lock

# Compare installed versions:
pip freeze > /tmp/local_deps.txt  # local
pip freeze > /tmp/ci_deps.txt     # CI
diff /tmp/local_deps.txt /tmp/ci_deps.txt

# Common: local has requests==2.31 but CI has requests==2.28
# Fix: Commit your lockfile. Always.


# 3. RUNTIME VERSION (10% of cases)
# Python 3.11 locally, Python 3.9 in CI

# Check:
python --version  # Local: 3.11.5
python --version  # CI: 3.9.7

# Python 3.10+ features that break on 3.9:
match x:           # match/case (3.10+)
x | y              # Union type syntax (3.10+)
(x := expr)        # Walrus operator (3.8+, but sometimes still the issue)

# Fix: Pin the runtime version in CI to match local
# pyproject.toml: python = "^3.11"
# Dockerfile: FROM python:3.11-slim


# 4. CASE SENSITIVITY (10% of cases — macOS → Linux)
# macOS: case-insensitive (import MyModule → finds mymodule.py)
# Linux: case-sensitive (import MyModule → FileNotFoundError)

# Find case mismatches:
git ls-files | sort -f | uniq -di
# If this shows files → you have case conflicts

# Check imports match actual filenames:
grep -r "from.*import\|import" src/ | grep -i "[A-Z]"
# Verify each import matches the EXACT filename case


# 5. FILE SYSTEM / PATH DIFFERENCES
# Windows: \ separators, CRLF line endings
# Linux: / separators, LF line endings

# Check for hardcoded paths:
grep -r "C:\\\\" src/          # Windows paths in code
grep -r "/home/" src/          # Hardcoded Linux home directories

# Check line endings:
file src/*.py | grep CRLF      # CRLF files will fail some parsers on Linux
```

**Systematic resolution script**:
```python
# Add this to your CI pipeline as a debugging step
import sys, os, platform, importlib.metadata

def environment_report():
    """Print everything that might differ between environments."""
    print("=== ENVIRONMENT REPORT ===")
    print(f"Python: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print(f"CWD: {os.getcwd()}")
    print(f"User: {os.getenv('USER', 'unknown')}")
    print(f"Timezone: {os.getenv('TZ', 'not set')}")

    # Critical env vars
    critical_vars = ['DATABASE_URL', 'API_KEY', 'NODE_ENV', 'DEBUG']
    for var in critical_vars:
        val = os.getenv(var)
        print(f"${var}: {'SET' if val else 'NOT SET'}")

    # Installed packages
    print("\n=== KEY PACKAGES ===")
    for pkg in ['django', 'fastapi', 'sqlalchemy', 'requests', 'pydantic']:
        try:
            version = importlib.metadata.version(pkg)
            print(f"  {pkg}=={version}")
        except importlib.metadata.PackageNotFoundError:
            print(f"  {pkg}: NOT INSTALLED")

environment_report()
```

**Counterfactual**: If the team used Docker for local development (same container as CI), this class of bug would be impossible — identical environment everywhere. The "works on my machine" problem is fundamentally about environment drift.'''
    ),
    (
        "thinking/causal-cascade-failure",
        "Our system had a cascading failure: the payment service went down, then the order service, then the API gateway, then the entire site. Each service has health checks and restarts automatically. How did one service take down everything?",
        r'''<think>
Cascade failures happen when services are coupled in ways that amplify a single failure. Let me trace the causal chain.

Typical cascade failure timeline:

T=0: Payment service encounters a database connection issue
T=1: Payment requests start timing out (5 second timeout)
T=2: Order service calls payment service → waits 5 seconds per request
T=3: Order service's thread pool fills up (all threads waiting on payment)
T=4: Order service can't accept new requests → health check fails → restart
T=5: API gateway retries failed order requests → 3x amplification
T=6: Order service restarts, gets hammered by retry storm → goes down again
T=7: API gateway's connection pool to order service fills up
T=8: API gateway starts returning 503 to ALL routes (not just orders)
T=9: Health check for API gateway fails → Kubernetes restarts it
T=10: DNS or load balancer detects all instances unhealthy
T=11: Site is completely down

The root cause: payment database hiccup (maybe 30 seconds of unavailability)
The amplification mechanism:
1. Long timeouts → thread pool exhaustion
2. No circuit breaker → keeps calling dead service
3. Retries amplify load
4. Shared thread pool → payment failure affects ALL endpoints
5. Auto-restart under load → restart loop (never catches up)

Each of these amplification steps could have been prevented:

1. Short timeouts → fail fast, don't hold threads
2. Circuit breaker → stop calling payment after N failures
3. Retry budget → limit total retries
4. Bulkhead → isolate payment calls from other endpoints
5. Backoff on restart → don't restart immediately under load
</think>

**Tracing the cascade — how a 30-second database blip killed the entire site:**

```
T=0:   Payment DB has brief connection issue (30 seconds)
       ┌─────────────────────────────────────────────────────────┐
T=1:   │ Payment Service: requests start timing out (5s each)   │
       │ Thread pool: 50 threads, all waiting on DB timeout     │
       │ Health check: still "healthy" (app is running)         │
       └──────────────────────┬──────────────────────────────────┘
                              │ timeout timeout timeout...
       ┌──────────────────────▼──────────────────────────────────┐
T=3:   │ Order Service: waiting for payment responses            │
       │ 50 threads × 5s timeout = all threads blocked          │
       │ Can't accept ANY new requests (even non-payment)       │
       │ Health check: FAILS (can't respond)                    │
       └──────────────────────┬──────────────────────────────────┘
                              │ 503 503 503...
       ┌──────────────────────▼──────────────────────────────────┐
T=5:   │ API Gateway: Order service is returning 503s            │
       │ Gateway RETRIES each failed request 3 times            │
       │ 1000 req/sec × 3 retries = 3000 req/sec to Order      │
       │ Connection pool fills up for ALL backends              │
       │ ALL routes affected (not just /orders)                 │
       └──────────────────────┬──────────────────────────────────┘
                              │ everything down
       ┌──────────────────────▼──────────────────────────────────┐
T=8:   │ COMPLETE OUTAGE: All services restarting in a loop     │
       │ Each restart gets immediately overwhelmed              │
       │ Retry storms prevent recovery                          │
       └────────────────────────────────────────────────────────┘
```

**5 amplification points — each is a missing defense:**

```python
# DEFENSE 1: Short timeouts → fail fast, don't block threads
# BEFORE: 5-second timeout holds a thread for 5 seconds
# AFTER: 500ms timeout — if payment is slow, it's BROKEN
payment_response = await httpx.post(
    f"{PAYMENT_URL}/charge",
    timeout=httpx.Timeout(0.5, connect=0.2),  # 500ms total, 200ms connect
)

# DEFENSE 2: Circuit breaker → stop calling dead services
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=30)
async def charge_payment(amount):
    return await httpx.post(f"{PAYMENT_URL}/charge", json={"amount": amount})
# After 5 failures: immediately returns error for 30 seconds
# Doesn't waste threads on a service we KNOW is down

# DEFENSE 3: Retry budget → limit total retries
# BEFORE: every client retries 3x → 3x amplification
# AFTER: retry budget of 10% — if 10% of requests are retries, stop retrying
class RetryBudget:
    def __init__(self, budget_pct: float = 0.1):
        self.total_requests = 0
        self.retry_requests = 0

    def should_retry(self) -> bool:
        self.total_requests += 1
        if self.retry_requests / max(self.total_requests, 1) > 0.1:
            return False  # Budget exceeded — stop amplifying
        self.retry_requests += 1
        return True

# DEFENSE 4: Bulkhead → isolate failures
# BEFORE: one shared thread pool for all endpoints
# AFTER: separate pools per dependency
payment_semaphore = asyncio.Semaphore(10)   # Max 10 concurrent payment calls
order_semaphore = asyncio.Semaphore(20)     # Max 20 concurrent order calls

async def charge_payment_isolated(amount):
    async with payment_semaphore:  # Only 10 threads can wait for payment
        return await charge_payment(amount)
    # Other 40 threads are FREE to serve non-payment endpoints

# DEFENSE 5: Graceful degradation → serve partial results
@app.post("/orders")
async def create_order(order: Order):
    try:
        payment = await charge_payment_isolated(order.total)
    except (CircuitBreakerError, httpx.TimeoutException):
        # Payment is down — don't fail the entire order!
        # Queue the payment for later processing
        await payment_queue.enqueue(order.id, order.total)
        return {"status": "pending_payment", "order_id": order.id}
```

**The counterfactual chain**:
```
If we had short timeouts:      Thread pool wouldn't exhaust → order service stays up
If we had circuit breakers:    Order service stops calling payment → stays responsive
If we had retry budgets:       API gateway doesn't amplify → manageable load
If we had bulkheads:           Payment failure isolated → other endpoints work
If we had graceful degradation: Users can still browse/order → revenue continues
```

**The root cause** was a 30-second database hiccup. The **real failure** was 5 missing defenses that turned a minor issue into a site-wide outage.'''
    ),
    (
        "thinking/causal-api-behavior-change",
        "After updating the `requests` library from 2.28 to 2.31, some of our API calls to a third-party service started failing with SSL errors. The third-party API hasn't changed. What happened?",
        r'''<think>
SSL errors after a library update — let me trace the causal chain.

The symptom: API calls fail with SSL errors. Only after upgrading `requests`.

Possible causes:
1. `requests` 2.31 bundles a newer version of `certifi` (CA certificate bundle)
   - The third-party API uses a certificate signed by a CA that was removed from the bundle
   - Or the CA was distrusted (like DigiNotar, Symantec)

2. `requests` 2.31 uses a newer `urllib3` which enforces stricter SSL
   - Might enforce TLS 1.2 minimum (old API uses TLS 1.0)
   - Might reject certain cipher suites
   - Might enforce hostname matching more strictly

3. The third-party API's certificate is self-signed or expired
   - Old `requests` was more lenient
   - New version is stricter

4. System CA certificates changed during the same update
   - If `requests` uses system certs instead of bundled ones

5. The API certificate chain is incomplete (missing intermediate cert)
   - Old urllib3 tried harder to complete the chain
   - New version requires the full chain

Let me think about which is most likely...

The most common cause when upgrading requests is #1 or #2:
- certifi update removed/distrusted a CA
- Or urllib3 strictness increase

The investigation is: check what SSL version and certificate the third-party uses, then check what changed in the requests/urllib3/certifi upgrade.
</think>

**Causal chain: the library upgrade changed SSL behavior, not the API.**

**Most likely cause** (tracing the dependency chain):
```
requests 2.28 → urllib3 1.26.x → certifi 2023.05 → OpenSSL behavior X
requests 2.31 → urllib3 2.0.x  → certifi 2024.02 → OpenSSL behavior Y

urllib3 2.0 was a MAJOR version change with breaking SSL changes:
- Dropped TLS 1.0 and TLS 1.1 support (only TLS 1.2+)
- Stricter certificate validation
- Changed default cipher suites
- Removed deprecated SSL options
```

**Investigation steps**:
```bash
# Step 1: Identify what ACTUALLY changed
pip show requests urllib3 certifi  # Current versions
pip install requests==2.28
pip show requests urllib3 certifi  # Old versions
# Compare the version jumps — especially urllib3

# Step 2: Check the third-party API's SSL configuration
openssl s_client -connect api.thirdparty.com:443 -tls1_2
# If this fails → they don't support TLS 1.2 → that's the problem

openssl s_client -connect api.thirdparty.com:443 -showcerts
# Shows certificate chain — check for:
# - Expired certs
# - Missing intermediate certs
# - Self-signed certs
# - CA that was recently distrusted

# Step 3: Check the specific SSL error
python -c "
import requests
try:
    requests.get('https://api.thirdparty.com/health')
except Exception as e:
    print(type(e).__name__, e)
"
# Common errors:
# SSLError: certificate verify failed — CA not trusted
# SSLError: tlsv1 alert protocol version — TLS version mismatch
# SSLError: CERTIFICATE_VERIFY_FAILED — expired or self-signed cert
```

**The fix depends on the root cause**:
```python
# If the API uses TLS 1.0/1.1 (deprecated):
# TEMPORARY workaround (not recommended long-term):
import urllib3
urllib3.util.ssl_.DEFAULT_CIPHERS += ":HIGH:!DH:!aNULL"

# Or pin urllib3 < 2.0 (buys time):
# pip install "urllib3<2.0"

# PERMANENT fix: ask the third-party to upgrade to TLS 1.2+

# ───────────────────────────────────────────────

# If the API has an untrusted/self-signed certificate:
# TEMPORARY workaround (DANGEROUS — disables verification):
response = requests.get(url, verify=False)  # Never in production!

# PERMANENT fix: get the correct CA bundle
response = requests.get(url, verify="/path/to/their-ca-bundle.pem")

# ───────────────────────────────────────────────

# If the API has an incomplete certificate chain:
# The API server is misconfigured — missing intermediate certs
# Ask them to fix their server configuration
# Or manually provide the full chain:
response = requests.get(url, verify="/path/to/full-chain.pem")
```

**Counterfactual**: If we had pinned our transitive dependencies (`urllib3`, `certifi`) separately from `requests`, we could have upgraded `requests` without the SSL behavior change. Better: if we had SSL connection tests in CI, we'd have caught this before deploy.

**Prevention**:
```python
# Add SSL connectivity test to CI
@pytest.mark.integration
def test_thirdparty_ssl():
    """Catch SSL issues before they hit production."""
    response = requests.get("https://api.thirdparty.com/health", timeout=5)
    assert response.status_code == 200
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
