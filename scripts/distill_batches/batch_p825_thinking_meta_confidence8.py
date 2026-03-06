"""Phase 3C: Metacognition — Confidence in Security vs Performance Recommendations (Part 8)

Training the model to calibrate confidence differently when giving security
advice (where being wrong has catastrophic consequences) versus performance
advice (where being wrong wastes time but is recoverable).
"""

PAIRS = [
    (
        "thinking/meta-confidence-security-vs-perf-auth",
        r'''Should I use JWT or session cookies for authentication? I need good performance for our mobile API.''',
        r'''<think>
This question spans both security and performance domains. I need to calibrate my confidence differently for each aspect.

Security aspects (I should be MORE conservative, flag uncertainty):
- JWT security pitfalls (algorithm confusion, token theft, no revocation)
- Cookie security (CSRF, SameSite, Secure flag)
- Token storage on mobile (secure storage vs plain storage)
- Being wrong about security = data breach

Performance aspects (I can be more speculative):
- JWT avoids DB lookups for validation (stateless)
- Sessions require server-side storage (Redis/DB)
- Performance difference is measurable but usually small
- Being wrong about performance = slightly slower app (fixable)

I should present both perspectives but clearly weight security considerations higher, and be explicit about what's a security requirement (non-negotiable) vs a performance optimization (tradeoff).
</think>

This involves both security and performance considerations. I'll be explicit about my confidence level for each, because **getting security wrong is catastrophic while getting performance wrong is fixable.**

**Security analysis (HIGH confidence — these are well-established):**

Both JWT and sessions can be secure IF implemented correctly. The security risks differ:

```
JWT risks:                          Session risks:
- No built-in revocation            - CSRF (if using cookies)
- Token theft = full access          - Session fixation
  until expiry                       - Server-side storage failure
- Algorithm confusion attacks        - Session ID prediction
- Payload is readable (not private)
```

**Non-negotiable security requirements (regardless of your choice):**

```
JWT:
  ✓ Use RS256 or ES256 (NOT HS256 with a weak secret)
  ✓ Set short expiry (15-60 minutes) + refresh tokens
  ✓ Store in secure storage on mobile (Keychain/Keystore, NOT AsyncStorage)
  ✓ Validate ALL claims (iss, aud, exp, nbk)
  ✓ Plan for token revocation (blacklist or short expiry)

Sessions:
  ✓ Cryptographically random session IDs (128+ bits)
  ✓ HttpOnly, Secure, SameSite cookies
  ✓ Server-side session storage (Redis with TTL)
  ✓ Regenerate session ID on login
  ✓ CSRF protection if browser-accessible
```

**Performance analysis (MEDIUM confidence — varies by architecture):**

```
JWT (stateless):
  + No database lookup to validate token → faster per-request
  + Scales horizontally without shared session store
  - Token is larger (1-2KB vs 32-byte session ID)
  - Can't revoke without additional infrastructure

Sessions (stateful):
  + Tiny cookie (session ID only)
  + Easy revocation (delete from store)
  - Requires Redis/DB lookup per request (~1ms)
  - Shared session store is a dependency
```

**For mobile API specifically:**

JWT is the common choice because:
1. Mobile apps naturally manage tokens (no cookie handling)
2. Stateless validation is simpler across API servers
3. Refresh token flow maps well to mobile app lifecycle

```
Recommended pattern:
  Access token:  JWT, 15-minute expiry, stored in memory
  Refresh token: Opaque token, 30-day expiry, stored in secure storage
  Revocation:    Revoke refresh token → access token expires naturally
```

**My confidence summary:**
- Security recommendations above: HIGH confidence, follow them strictly
- Performance claims: MEDIUM confidence, benchmark for your specific case
- The performance difference between JWT and sessions is almost always negligible compared to your actual API logic time'''
    ),
    (
        "thinking/meta-confidence-security-vs-perf-cors",
        r'''Our CORS configuration is blocking some legitimate requests. Can I just set Access-Control-Allow-Origin to * to fix it?''',
        r'''<think>
This is a question where the "easy fix" (wildcard CORS) has real security implications. I need to be very direct about the security risk while helping them solve the actual problem.

Security confidence: HIGH — CORS wildcard risks are well-documented
- Wildcard allows any website to make requests to your API
- If users are authenticated, this enables cross-site request forgery variants
- Wildcard + credentials is actually blocked by browsers (can't use * with cookies/auth headers)

Performance/convenience confidence: HIGH — I know CORS well
- The actual fix is usually listing specific allowed origins
- Dynamic origin checking is the standard pattern

The key insight: the user wants to fix a problem (legitimate requests being blocked) and is reaching for the easiest solution. I need to help them fix the actual problem without introducing a security hole.
</think>

**Short answer: No.** This is a case where the easy fix creates a security vulnerability. Let me explain why and give you the correct fix.

**Why wildcard CORS is dangerous (HIGH confidence — this is security-critical):**

```
Access-Control-Allow-Origin: *
```

This means: "Any website on the internet can make requests to our API."

If your API uses authentication (cookies, tokens):
```
Malicious site evil.com can:
1. User visits evil.com while logged into your app
2. evil.com makes fetch() requests to your API
3. If credentials are sent, evil.com reads authenticated data

Note: browsers block `*` with credentials, but attackers can work around
this by reflecting the Origin header — a common misconfiguration.
```

**The correct fix (HIGH confidence):**

Instead of wildcard, allow specific origins:

```python
# Flask-CORS
from flask_cors import CORS

CORS(app, origins=[
    "https://yourapp.com",
    "https://staging.yourapp.com",
    "https://admin.yourapp.com",
])

# Express
const cors = require('cors');
app.use(cors({
    origin: [
        'https://yourapp.com',
        'https://staging.yourapp.com',
    ],
    credentials: true,
}));
```

**If you have many origins or dynamic subdomains:**

```python
# Dynamic origin validation (check against allowlist)
ALLOWED_ORIGINS = {
    "https://yourapp.com",
    "https://staging.yourapp.com",
}

def check_origin(origin):
    # Exact match
    if origin in ALLOWED_ORIGINS:
        return origin
    # Or pattern match for subdomains
    if origin and origin.endswith('.yourapp.com') and origin.startswith('https://'):
        return origin
    return None

@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin')
    allowed = check_origin(origin)
    if allowed:
        response.headers['Access-Control-Allow-Origin'] = allowed
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response
```

**Diagnose the actual CORS error first:**

What does the browser console say? Common fixes:
```
"No 'Access-Control-Allow-Origin' header"
  → Add the requesting origin to your allowlist

"Method PUT is not allowed"
  → Add Access-Control-Allow-Methods: GET, POST, PUT, DELETE

"Header 'Authorization' is not allowed"
  → Add Access-Control-Allow-Headers: Authorization, Content-Type

"Preflight response is not successful"
  → Handle OPTIONS requests (preflight) in your server
```

Tell me the exact error message and I'll give you the specific fix that doesn't compromise security.'''
    ),
    (
        "thinking/meta-confidence-security-vs-perf-caching",
        r'''We're caching API responses in Redis for performance. Should we cache the authentication/authorization results too? It would save a lot of database queries.''',
        r'''<think>
This is a case where performance optimization directly conflicts with security. I need to be very careful about my confidence levels.

Security implications (HIGH confidence, conservative):
- Caching auth results means a revoked user can still access the system
- Permission changes won't take effect until cache expires
- An attacker who compromises Redis gets all the auth decisions
- In regulated industries (healthcare, finance), stale auth is a compliance issue

Performance implications (HIGH confidence):
- Auth queries CAN be expensive if they involve multiple table joins
- Auth is called on every request, so optimizing it has high leverage
- Redis lookup (~1ms) vs DB query (~5-20ms) is meaningful at scale

The nuanced answer: you CAN cache some auth data, but you need to understand exactly what you're trading off and make the cache TTL very short for security-critical decisions.

I should be more cautious/conservative on this recommendation than I would be for a pure performance question.
</think>

This is a case where performance optimization can create security vulnerabilities. I'll be more conservative in my recommendation than I would for a pure performance question.

**The security risk (HIGH confidence — take this seriously):**

```
Without cache:
  User revoked at 10:00:00 → Next request at 10:00:01 is denied ✓

With cache (5 minute TTL):
  User revoked at 10:00:00 → Requests until 10:05:00 still succeed ✗
  For 5 minutes, a fired employee / compromised account has full access
```

**What's safe to cache (with caveats):**

```
SAFE to cache (LOW security impact):
  - User profile data (name, email, preferences)
  - Feature flags
  - Non-sensitive configuration
  TTL: 5-15 minutes is fine

CACHE WITH CAUTION (MEDIUM security impact):
  - User roles/permissions
  - Rate limit counters
  TTL: 30-60 seconds maximum
  Must support explicit invalidation

NEVER CACHE (HIGH security impact):
  - Authentication decisions (is this token valid?)
  - Password/credential verification
  - MFA verification results
  - Session validity checks
```

**If you DO cache auth decisions, the safe pattern:**

```python
import redis
import json

class CachedAuthService:
    def __init__(self, db, redis_client):
        self.db = db
        self.redis = redis_client
        self.CACHE_TTL = 30  # 30 seconds MAX for auth data

    def get_user_permissions(self, user_id):
        cache_key = f"perms:{user_id}"

        # Try cache
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # Fall back to DB
        perms = self.db.query_permissions(user_id)
        self.redis.setex(cache_key, self.CACHE_TTL, json.dumps(perms))
        return perms

    def revoke_user(self, user_id):
        # CRITICAL: Explicitly invalidate cache on revocation
        self.redis.delete(f"perms:{user_id}")
        self.db.revoke_user(user_id)

    def update_permissions(self, user_id, new_perms):
        # CRITICAL: Invalidate cache on permission change
        self.redis.delete(f"perms:{user_id}")
        self.db.update_permissions(user_id, new_perms)
```

**The performance fix that avoids the security tradeoff:**

Often the auth query is slow because of poor indexing, not because caching is needed:

```sql
-- If this is slow:
SELECT p.* FROM permissions p
JOIN role_permissions rp ON p.id = rp.permission_id
JOIN user_roles ur ON rp.role_id = ur.role_id
WHERE ur.user_id = $1;

-- Add an index:
CREATE INDEX idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX idx_role_permissions_role_id ON role_permissions(role_id);

-- This might make the query fast enough (< 5ms) that caching is unnecessary
```

**My recommendation:**
1. First, optimize the auth query (indexes, denormalization)
2. If still slow, cache with 30-second TTL maximum
3. Always support explicit cache invalidation on auth changes
4. Never cache the authentication step itself (token validation)
5. In regulated industries (healthcare, finance), consult compliance before caching any auth data'''
    ),
    (
        "thinking/meta-confidence-security-vs-perf-logging",
        r'''We want to log all API requests for debugging. Should we log the full request body including POST data?''',
        r'''<think>
This is another security vs operability tradeoff. Logging request bodies is extremely useful for debugging but can expose sensitive data.

Security risks (HIGH confidence):
- Request bodies contain passwords, tokens, credit card numbers, PII
- Logs are often less protected than databases
- Log aggregation services (Splunk, ELK, Datadog) may store data in additional locations
- PII in logs violates GDPR and other privacy regulations
- Log files may be accessible to more team members than the database
- Log retention policies may keep sensitive data longer than necessary

Operational benefits (HIGH confidence):
- Full request bodies make debugging much easier
- Without them, reproducing issues is harder
- Incomplete logs often mean multiple back-and-forth debugging cycles

The right answer is: log request bodies BUT redact sensitive fields. I'm confident in this recommendation.
</think>

**Do not log full request bodies without redaction.** This is a security and compliance issue, not just a best practice.

**Why full request logging is dangerous (HIGH confidence):**

```
POST /api/login
Body: {"email": "alice@example.com", "password": "MyS3cretP@ss!"}
  → Password in plain text in your logs

POST /api/payment
Body: {"card_number": "4111111111111111", "cvv": "123", "amount": 99.99}
  → Credit card data in your logs → PCI DSS violation

POST /api/users
Body: {"name": "Alice", "ssn": "123-45-6789", "dob": "1990-01-01"}
  → PII in your logs → GDPR violation
```

**Logs are typically LESS secure than your database:**
- More people have log access (all developers, ops, support)
- Log aggregation services (Datadog, Splunk) copy data to third parties
- Log retention may exceed data retention policies
- Logs may be stored unencrypted

**The correct approach — log with redaction (HIGH confidence):**

```python
SENSITIVE_FIELDS = {
    'password', 'token', 'secret', 'authorization',
    'credit_card', 'card_number', 'cvv', 'ssn',
    'social_security', 'api_key', 'access_token',
    'refresh_token',
}

def redact_body(body: dict, sensitive=SENSITIVE_FIELDS) -> dict:
    """Deep-redact sensitive fields from request body for logging."""
    if not isinstance(body, dict):
        return body
    redacted = {}
    for key, value in body.items():
        if key.lower() in sensitive:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_body(value, sensitive)
        elif isinstance(value, list):
            redacted[key] = [redact_body(item, sensitive) if isinstance(item, dict) else item for item in value]
        else:
            redacted[key] = value
    return redacted

# Middleware example
@app.before_request
def log_request():
    body = request.get_json(silent=True) or {}
    logger.info("API Request", extra={
        "method": request.method,
        "path": request.path,
        "body": redact_body(body),
        "ip": request.remote_addr,
        "user_id": get_current_user_id(),
    })
```

**What SHOULD be logged (safe and useful):**
```
- Request method and path
- Response status code and latency
- User ID (not credentials)
- Request ID for correlation
- Query parameters (redact tokens)
- Error messages and stack traces
- Redacted request body
```

**What MUST NOT be logged:**
```
- Passwords (even hashed ones — don't normalize this)
- API keys and tokens
- Credit card numbers
- Social security numbers / government IDs
- Full authentication headers
- Session tokens
```

**Performance note (MEDIUM confidence):** Logging full bodies with redaction adds minimal overhead (microseconds of JSON processing). The security benefit far outweighs the performance cost. If logging volume is a concern, sample non-error requests rather than removing redaction.'''
    ),
    (
        "thinking/meta-confidence-security-vs-perf-env-vars",
        r'''Is it safe to put database credentials in environment variables? I've seen some people say this is insecure. What should I use instead?''',
        r'''<think>
This is an interesting question where the security community has nuanced opinions. Let me calibrate carefully.

HIGH confidence:
- Environment variables are BETTER than hardcoded credentials in code
- Environment variables are BETTER than config files committed to git
- Environment variables are the 12-factor app recommendation
- Environment variables can leak through: process listings, error logs, child processes, core dumps

MEDIUM confidence:
- For most applications, environment variables are "good enough"
- Secrets managers (Vault, AWS Secrets Manager) are more secure
- The threat model matters — what are you protecting against?
- Docker/Kubernetes secrets are essentially files/env vars with extra access control

The nuanced view:
- Saying "env vars are insecure" without context is misleading
- They're on a security spectrum: hardcoded < env vars < secrets manager < HSM
- The right choice depends on your threat model and compliance requirements

I should present this as a spectrum, not a binary good/bad, and help them choose based on their context.
</think>

The "env vars are insecure" claim is overly simplistic. Let me present the security spectrum with honest confidence levels.

**The security hierarchy (HIGH confidence):**

```
WORST:  Hardcoded in source code (committed to git)
        → Anyone with repo access sees credentials
        → Credentials in git history forever

BAD:    Config files in the deployment directory
        → Better, but often accidentally committed

OK:     Environment variables
        → The 12-factor app standard
        → Better than the above, but with caveats

GOOD:   Secrets manager (Vault, AWS Secrets Manager)
        → Centralized, audited, rotatable
        → Access-controlled per service

BEST:   Short-lived credentials from identity federation
        → No static secrets at all
        → IAM roles, workload identity, OIDC
```

**Environment variables — the honest assessment:**

Pros (HIGH confidence):
```
+ Better than hardcoded secrets (far better)
+ Easy to use, no additional infrastructure
+ Supported by every language and platform
+ Different values per environment (dev/staging/prod)
+ The standard for Heroku, Docker, Kubernetes, etc.
```

Known risks (HIGH confidence):
```
- Visible in /proc/[pid]/environ on Linux (requires local access)
- Inherited by child processes (may leak to subprocesses)
- May appear in error logs or crash dumps
- Visible in container inspection (docker inspect)
- Some frameworks log all env vars on startup
```

**My recommendation based on context:**

```
Startup / small team / non-regulated:
  → Environment variables are fine
  → Focus on: don't commit .env files, use .env.example templates
  → This is your biggest risk: credentials in git history

Growing company / multiple services:
  → Use a secrets manager (AWS Secrets Manager, GCP Secret Manager)
  → $0.40/secret/month — cheap for the security benefit
  → Provides audit logging and rotation

Regulated industry (healthcare, finance):
  → Secrets manager is likely required by compliance
  → Consider short-lived credentials (IAM roles, workload identity)
  → Audit trail for secret access is often mandatory
```

**Practical steps right now (HIGH confidence):**

```bash
# 1. Make sure .env is in .gitignore
echo ".env" >> .gitignore

# 2. Provide a template without real values
cp .env .env.example
# Edit .env.example to have placeholder values

# 3. Check if credentials are already in git history
git log --all --oneline -- .env
# If yes, they're compromised — rotate them immediately

# 4. Don't log environment variables
# Check your startup code for console.log(process.env) or similar
```

**If you want to upgrade from env vars:**
```python
# AWS Secrets Manager example
import boto3
import json

def get_secret(name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=name)
    return json.loads(response['SecretString'])

# Usage
secrets = get_secret('myapp/production/db')
db_url = f"postgresql://{secrets['username']}:{secrets['password']}@{secrets['host']}/mydb"
```

For most teams, env vars with proper hygiene (.gitignore, no logging, rotation) are adequate. Upgrade to a secrets manager when your compliance requirements or threat model demands it.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
