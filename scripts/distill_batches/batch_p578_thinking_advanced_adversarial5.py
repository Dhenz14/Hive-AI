"""Phase 2B: Advanced Reasoning — Adversarial Self-Testing (Part 5/6)
Write solution, systematically attack it, fix what breaks:
JWT implementation, GraphQL query, caching layer, webhook handler, search endpoint."""

PAIRS = [
    (
        "thinking/adversarial-jwt-implementation",
        "I'm implementing JWT authentication for my API. Here's my code:\n\n```python\nimport jwt\n\ndef create_token(user_id):\n    return jwt.encode({'user_id': user_id}, SECRET_KEY, algorithm='HS256')\n\ndef verify_token(token):\n    return jwt.decode(token, SECRET_KEY, algorithms=['HS256'])\n```\n\nIs this secure?",
        r'''<think>
Let me systematically attack this JWT implementation.

Attack 1: No expiration
- Token lives forever once issued
- Stolen token = permanent access
- Even after user changes password, old token still works
- Fix: add 'exp' claim

Attack 2: No issuer/audience validation
- A JWT from another service using the same secret could be accepted
- If you use the same SECRET_KEY for multiple purposes, tokens are interchangeable
- Fix: add 'iss' and 'aud' claims, validate them

Attack 3: Algorithm confusion (critical!)
- If SECRET_KEY is an RSA public key and you accept HS256:
  - Attacker uses the PUBLIC key (which is public) as the HMAC secret
  - Signs a forged token with HS256 using the public key
  - Server verifies with the same public key → accepts!
- The code specifies algorithms=['HS256'] which is good (prevents 'none' attack)
- But if they ever switch to RS256, they need to be careful
- Fix: always explicitly specify allowed algorithms (already done, but document why)

Attack 4: Weak SECRET_KEY
- If SECRET_KEY is something like "secret" or "myapp123"
- Attacker can brute-force it (hashcat can crack weak JWT secrets in minutes)
- Fix: use a cryptographically random key, minimum 256 bits

Attack 5: No token revocation
- User logs out → token still valid until expiry
- User is deactivated by admin → token still valid
- Fix: token blocklist or short-lived tokens + refresh tokens

Attack 6: Sensitive data in payload
- JWT payload is base64-encoded, NOT encrypted
- Anyone can decode it: base64.b64decode(token.split('.')[1])
- If user_id contains email, PII, or role info → information disclosure
- Fix: only store non-sensitive IDs, or use JWE (encrypted JWT)

Attack 7: Token replay
- Attacker captures a valid token from network traffic
- Replays it to authenticate as the victim
- Fix: HTTPS (prevents capture), short expiry + refresh tokens

Attack 8: No 'not before' (nbf) claim
- Token is valid immediately upon creation
- Usually not a problem, but for scheduled access it could be

The most critical issues: no expiration (Attack 1) and potentially weak secret (Attack 4). These are the most commonly exploited JWT vulnerabilities.
</think>

This implementation has several critical vulnerabilities. Let me attack it and build a secure version.

**Attacks that work against your code:**

```python
# Attack 1: Token lives forever (no expiration)
token = create_token(42)
# 5 years later... still valid. Stolen token = permanent access.

# Attack 2: Decode the payload (JWT is NOT encrypted)
import base64
payload = token.split('.')[1]
payload += '=' * (4 - len(payload) % 4)  # Fix padding
print(base64.b64decode(payload))
# b'{"user_id": 42}' — anyone can read this

# Attack 3: Brute-force a weak secret
# hashcat -m 16500 -a 3 jwt.txt ?a?a?a?a?a?a
# If SECRET_KEY is "secret" → cracked in seconds
# Attacker can now forge tokens for ANY user

# Attack 4: Token still valid after password change
# User changes password → all old tokens should be invalid
# Your code: old tokens still work until... forever
```

**Secure implementation:**

```python
import jwt
import os
from datetime import datetime, timedelta

# Use a strong, random secret (minimum 256 bits)
SECRET_KEY = os.environ["JWT_SECRET"]
# Generate: python -c "import secrets; print(secrets.token_hex(32))"

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(minutes=15)   # Short-lived
REFRESH_TOKEN_EXPIRE = timedelta(days=7)

def create_access_token(user_id: int, roles: list = None) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),       # Subject (who)
        "iat": now,                 # Issued at
        "exp": now + ACCESS_TOKEN_EXPIRE,  # Expires in 15 min
        "iss": "myapp",            # Issuer
        "aud": "myapp-api",        # Audience
        "type": "access",          # Token type
    }
    if roles:
        payload["roles"] = roles
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: int) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + REFRESH_TOKEN_EXPIRE,
        "iss": "myapp",
        "aud": "myapp-api",
        "type": "refresh",
        "jti": str(uuid.uuid4()),  # Unique ID for revocation
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],    # Explicit — prevents algorithm confusion
            issuer="myapp",            # Validates iss claim
            audience="myapp-api",      # Validates aud claim
            options={
                "require": ["exp", "iss", "aud", "sub"],  # All required
            },
        )
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Not an access token")
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token expired")
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {e}")
```

**Token refresh flow (prevents stealing long-lived tokens):**

```python
@app.post("/auth/refresh")
def refresh_token(refresh_token: str):
    try:
        payload = jwt.decode(
            refresh_token, SECRET_KEY,
            algorithms=[ALGORITHM], issuer="myapp", audience="myapp-api",
        )
        if payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid token type")

        # Check if refresh token has been revoked
        if is_token_revoked(payload["jti"]):
            raise HTTPException(401, "Token revoked")

        # Issue new access token
        new_access = create_access_token(int(payload["sub"]))
        return {"access_token": new_access}

    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid refresh token")

# Revoke on logout
@app.post("/auth/logout")
def logout(token_payload: dict = Depends(get_current_token)):
    # Add refresh token JTI to blocklist
    revoke_token(token_payload.get("jti"))
    return {"message": "Logged out"}

# Redis-based revocation (fast lookup, auto-expires)
def revoke_token(jti: str):
    r.setex(f"revoked:{jti}", REFRESH_TOKEN_EXPIRE.total_seconds(), "1")

def is_token_revoked(jti: str) -> bool:
    return r.exists(f"revoked:{jti}")
```

**Security checklist for JWT:**

| Check | Your code | Fixed code |
|---|---|---|
| Expiration (exp) | Missing | 15 min access, 7 day refresh |
| Strong secret | Unknown | 256-bit random |
| Algorithm pinned | Yes (good!) | Yes + explicit require |
| Issuer/audience | Missing | Validated |
| Token type | Missing | access vs refresh |
| Revocation | Missing | Redis blocklist |
| Refresh flow | Missing | Short access + long refresh |
| Payload privacy | user_id exposed | Only non-sensitive IDs |'''
    ),
    (
        "thinking/adversarial-webhook-handler",
        "I'm receiving webhooks from Stripe. Here's my handler:\n\n```python\n@app.post('/webhooks/stripe')\nasync def stripe_webhook(request: Request):\n    event = await request.json()\n    if event['type'] == 'payment_intent.succeeded':\n        order_id = event['data']['object']['metadata']['order_id']\n        mark_order_paid(order_id)\n    return {'received': True}\n```\n\nAnything wrong with this?",
        r'''<think>
Let me systematically attack this webhook handler.

Attack 1: No signature verification (CRITICAL)
- Anyone can send a POST to /webhooks/stripe with a fake payload
- Attacker: POST {"type": "payment_intent.succeeded", "data": {"object": {"metadata": {"order_id": "123"}}}}
- Result: order 123 marked as paid without actual payment!
- This is essentially free products — the most critical vulnerability
- Fix: verify Stripe's webhook signature using the signing secret

Attack 2: Replay attack
- Attacker captures a legitimate webhook and replays it
- Even with signature verification, the same valid webhook could be replayed
- Fix: use Stripe's timestamp checking (built into their verification), or track processed event IDs

Attack 3: No idempotency
- Stripe may send the same webhook multiple times (they retry on failure)
- mark_order_paid(order_id) runs multiple times
- If it triggers email + inventory update, customer gets 3 confirmation emails, inventory decremented 3 times
- Fix: track processed event IDs, skip duplicates

Attack 4: Missing event type handling
- What about refunds? payment_intent.payment_failed? charge.dispute.created?
- If payment fails after initial success, this handler doesn't revert
- Fix: handle all relevant event types

Attack 5: No error handling
- If mark_order_paid() throws an exception, the endpoint returns 500
- Stripe sees 500, retries the webhook
- But order might be partially processed (marked paid but email failed)
- Fix: handle errors, return 200 to Stripe even on partial failure (process async)

Attack 6: Information disclosure
- The handler returns 200 for any event type (no validation)
- But if it returns different responses for valid vs invalid events, attacker can probe
- Fix: always return 200 (Stripe expects this)

Attack 7: Missing metadata
- What if event['data']['object']['metadata']['order_id'] doesn't exist?
- KeyError → 500 → Stripe retries forever
- Fix: validate payload structure before processing

The most critical issue by far is Attack 1 — no signature verification. This means anyone can forge webhooks and get free products.
</think>

**Critical vulnerability: no signature verification.** Anyone can forge a webhook and mark orders as paid without paying.

**The attack:**

```bash
# Attacker sends a fake webhook — gets free products
curl -X POST https://yourapp.com/webhooks/stripe \
  -H "Content-Type: application/json" \
  -d '{
    "type": "payment_intent.succeeded",
    "data": {"object": {"metadata": {"order_id": "expensive-order-123"}}}
  }'
# Your code: marks order 123 as paid. No payment was made.
```

**Secure implementation:**

```python
import stripe
from fastapi import Request, HTTPException

STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    # 1. VERIFY SIGNATURE — reject forged webhooks
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(400, "Missing signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")
    except ValueError:
        raise HTTPException(400, "Invalid payload")

    # 2. IDEMPOTENCY — don't process the same event twice
    event_id = event["id"]
    if await is_event_processed(event_id):
        return {"received": True}  # Already handled — skip

    # 3. HANDLE RELEVANT EVENTS
    try:
        if event["type"] == "payment_intent.succeeded":
            intent = event["data"]["object"]
            order_id = intent.get("metadata", {}).get("order_id")
            if order_id:
                await mark_order_paid(order_id, payment_id=intent["id"])

        elif event["type"] == "payment_intent.payment_failed":
            intent = event["data"]["object"]
            order_id = intent.get("metadata", {}).get("order_id")
            if order_id:
                await mark_order_failed(order_id, reason=intent.get("last_payment_error"))

        elif event["type"] == "charge.refunded":
            charge = event["data"]["object"]
            await process_refund(charge["payment_intent"], charge["amount_refunded"])

        elif event["type"] == "charge.dispute.created":
            dispute = event["data"]["object"]
            await flag_dispute(dispute["payment_intent"])

    except Exception as e:
        # Log the error but return 200 — don't make Stripe retry
        logger.error("webhook_processing_error", event_id=event_id,
                     event_type=event["type"], error=str(e))

    # 4. MARK AS PROCESSED (for idempotency)
    await mark_event_processed(event_id)

    # Always return 200 — Stripe retries on non-2xx
    return {"received": True}

# Idempotency tracking
async def is_event_processed(event_id: str) -> bool:
    return await r.exists(f"stripe_event:{event_id}")

async def mark_event_processed(event_id: str):
    await r.setex(f"stripe_event:{event_id}", 86400 * 7, "1")  # 7 day TTL
```

**All fixes summarized:**

| Vulnerability | Impact | Fix |
|---|---|---|
| No signature check | Forge payments (CRITICAL) | `stripe.Webhook.construct_event()` |
| No idempotency | Duplicate processing | Track event IDs in Redis |
| Missing event types | Missed refunds/disputes | Handle all relevant types |
| No error handling | Infinite retries on crash | Catch exceptions, return 200 |
| No payload validation | KeyError crashes | `.get()` with defaults |
| Replay attacks | Re-trigger old events | Stripe's timestamp validation (built into signature check) |

The signature verification is the #1 fix. Without it, your webhook endpoint is essentially a "mark any order as paid" API that anyone on the internet can call.'''
    ),
    (
        "thinking/adversarial-search-endpoint",
        "I built a search endpoint for my e-commerce site. Users type a query, and I search products:\n\n```python\n@app.get('/search')\ndef search(q: str):\n    results = db.execute(f\"SELECT * FROM products WHERE name LIKE '%{q}%'\")\n    return results\n```\n\nHow can I improve this?",
        r'''<think>
This code has MULTIPLE critical vulnerabilities. Let me attack it systematically.

Attack 1: SQL Injection (CRITICAL)
```
q = "'; DROP TABLE products; --"
Query becomes: SELECT * FROM products WHERE name LIKE '%'; DROP TABLE products; --%'
```
The entire products table is deleted. This is the textbook SQL injection.

Attack 2: Data exfiltration via UNION
```
q = "' UNION SELECT id, email, password_hash, '', '' FROM users --"
Query: SELECT * FROM products WHERE name LIKE '%' UNION SELECT id, email, password_hash, '', '' FROM users --%'
```
Attacker gets all usernames and password hashes.

Attack 3: Blind SQL injection (even if errors are hidden)
```
q = "' AND 1=1 --"  (returns results → table structure confirmed)
q = "' AND (SELECT COUNT(*) FROM users) > 0 --"  (confirms users table exists)
q = "' AND (SELECT SUBSTRING(password_hash,1,1) FROM users WHERE id=1) = 'a' --"
```
Character by character, attacker extracts any data from the database.

Attack 4: Performance attack (DoS via slow query)
```
q = "%"  → LIKE '%%' → full table scan, returns everything
q = "a%a%a%a%a%a%a%a%a%a"  → catastrophic backtracking in LIKE pattern
```
Attacker can tie up the database with expensive queries.

Attack 5: No pagination
- Returns ALL matching results
- Query for common term returns 100K rows → huge response, memory exhaustion

Attack 6: No rate limiting
- Attacker can scrape entire product catalog via search
- Automated price monitoring bots

Attack 7: No input sanitization
- LIKE special characters: %, _, [, ] have special meaning
- User searching for "50%" would match "50" followed by any character

This code needs to be completely rewritten. The SQL injection alone makes it one of the most dangerous patterns in web development.
</think>

**This code is critically vulnerable to SQL injection.** An attacker can read, modify, or delete your entire database.

**The attacks:**

```bash
# Attack 1: Delete the entire products table
curl "https://yourapp.com/search?q=%27%3B%20DROP%20TABLE%20products%3B%20--"
# q = "'; DROP TABLE products; --"

# Attack 2: Extract all user passwords
curl "https://yourapp.com/search?q=%27%20UNION%20SELECT%20email%2Cpassword_hash%20FROM%20users--"
# Returns user credentials mixed in with product results

# Attack 3: Dump the entire database
# Using sqlmap (automated SQL injection tool):
sqlmap -u "https://yourapp.com/search?q=test" --dump
# Extracts every table, every column, every row
```

**The fix — parameterized queries (eliminates SQL injection):**

```python
from sqlalchemy import text

@app.get("/search")
def search(
    q: str = Query(min_length=1, max_length=100),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    # PARAMETERIZED QUERY — user input is NEVER in the SQL string
    offset = (page - 1) * per_page
    results = db.execute(
        text("""
            SELECT id, name, price, image_url
            FROM products
            WHERE name ILIKE :query
            ORDER BY relevance_score DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            "query": f"%{q}%",  # Parameter — safely escaped by the driver
            "limit": per_page,
            "offset": offset,
        },
    ).fetchall()

    return {
        "query": q,
        "page": page,
        "results": [dict(r._mapping) for r in results],
    }
```

**Even better — use PostgreSQL full-text search:**

```python
@app.get("/search")
def search(
    q: str = Query(min_length=1, max_length=200),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    offset = (page - 1) * per_page

    # Full-text search: faster, handles stemming, ranking
    results = db.execute(
        text("""
            SELECT id, name, price, image_url,
                   ts_rank(search_vector, query) AS rank
            FROM products,
                 plainto_tsquery('english', :q) AS query
            WHERE search_vector @@ query
            ORDER BY rank DESC
            LIMIT :limit OFFSET :offset
        """),
        {"q": q, "limit": per_page, "offset": offset},
    ).fetchall()

    total = db.execute(
        text("""
            SELECT COUNT(*)
            FROM products
            WHERE search_vector @@ plainto_tsquery('english', :q)
        """),
        {"q": q},
    ).scalar()

    return {
        "query": q,
        "page": page,
        "total": total,
        "results": [dict(r._mapping) for r in results],
    }
```

**Additional protections:**

```python
# Rate limiting on search (prevent scraping)
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@app.get("/search")
@limiter.limit("30/minute")  # 30 searches per minute per IP
def search(request: Request, q: str = Query(min_length=1, max_length=200)):
    ...

# Input sanitization for LIKE queries (escape special chars)
import re
def escape_like(s: str) -> str:
    """Escape LIKE special characters."""
    return re.sub(r'([%_\\])', r'\\\1', s)

# Use in query:
"query": f"%{escape_like(q)}%"
```

**The vulnerability severity matrix:**

| Issue | Severity | Fixed by |
|---|---|---|
| SQL injection | CRITICAL (RCE-equivalent) | Parameterized queries |
| No pagination | HIGH (DoS) | LIMIT/OFFSET with max |
| No input length limit | MEDIUM (DoS) | Query(max_length=200) |
| LIKE special chars | LOW (wrong results) | escape_like() |
| No rate limiting | MEDIUM (scraping) | Rate limiter |

**Rule: NEVER put user input in a SQL string.** Use parameterized queries (`:param` with SQLAlchemy, `%s` with psycopg2, `?` with sqlite3). This single rule prevents the most dangerous web vulnerability.'''
    ),
    (
        "thinking/adversarial-caching-layer",
        "I added Redis caching to speed up my API. Here's my approach:\n\n```python\ndef get_user(user_id):\n    cached = redis.get(f'user:{user_id}')\n    if cached:\n        return json.loads(cached)\n    user = db.query(User).get(user_id)\n    redis.set(f'user:{user_id}', json.dumps(user.to_dict()))\n    return user.to_dict()\n```\n\nWhat could go wrong?",
        r'''<think>
Let me systematically attack this caching implementation.

Attack 1: Cache stampede (thundering herd)
- Cache expires for a popular user (e.g., the admin user displayed on every page)
- 1000 concurrent requests all see cache miss at the same time
- All 1000 hit the database simultaneously
- DB overloaded → cascade failure
- Fix: lock during cache rebuild (only one request hits DB, others wait)

Attack 2: No cache expiration (stale data forever)
- redis.set() without TTL → data cached forever
- User changes their name → cache still has old name
- User is deactivated → cache still shows them as active
- Fix: set TTL on every cached value

Attack 3: Cache invalidation inconsistency
- User updates profile → database updated, cache NOT updated
- Next request reads stale data from cache
- "There are only two hard things in CS: cache invalidation and naming things"
- Fix: invalidate cache on write, or use write-through caching

Attack 4: Cache poisoning
- What if user_id = "../../admin:1"?
- Cache key: "user:../../admin:1" → could potentially overwrite another cache entry
- More realistically: user_id = "\r\nSET admin_key hacked\r\n" (CRLF injection in Redis)
- Fix: validate/sanitize the cache key

Attack 5: Serialization issues
- json.dumps(user.to_dict()) might not handle all types (datetime, Decimal, etc.)
- Or: if user.to_dict() includes sensitive data (password_hash), it's cached in Redis
- Fix: explicitly control what gets cached, handle serialization edge cases

Attack 6: No cache for missing users (cache penetration)
- get_user(999999999) → cache miss → DB query → user not found → nothing cached
- Attacker repeatedly queries non-existent user IDs
- Every request hits the DB (cache never helps)
- Fix: cache the absence too (cache "null" results with short TTL)

Attack 7: Memory exhaustion
- No max memory limit on Redis → caching everything forever
- 10M users × 1KB each = 10GB of cached user data
- Redis runs out of memory, starts evicting or crashes
- Fix: set maxmemory + eviction policy in Redis config

Attack 8: Race condition on write
- Thread A: reads user from DB
- Thread B: updates user in DB AND invalidates cache
- Thread A: writes STALE user to cache (after B's invalidation)
- Cache now has old data
- Fix: use cache-aside with TTL (eventually consistent), or use write-through

Let me design a proper caching implementation.
</think>

This caching code has at least 6 problems. Let me attack each one and build a robust version.

**The attacks:**

```python
# Attack 1: Cache stampede — 1000 requests hit DB simultaneously
# Popular user's cache expires → everyone hits DB at once → DB crashes

# Attack 2: Stale data forever — no TTL
redis.set(f'user:{user_id}', data)  # No expiry = cached forever
# User changes name → cache still shows old name

# Attack 3: Cache penetration — non-existent users
get_user(99999999)  # Not found → nothing cached → always hits DB
# Attacker loops over random IDs → every request hits DB

# Attack 4: Sensitive data cached
user.to_dict()  # Might include password_hash, SSN, etc.
# Redis compromise → all sensitive data exposed
```

**Robust caching implementation:**

```python
import json
import hashlib
import redis
import threading
from typing import Optional

r = redis.Redis()
CACHE_TTL = 300  # 5 minutes
NULL_TTL = 60    # Cache "not found" for 1 minute

class CacheService:
    def __init__(self, redis_client):
        self.redis = redis_client
        self._locks = {}

    def get_user(self, user_id: int) -> Optional[dict]:
        cache_key = f"user:{int(user_id)}"  # Sanitize: force integer

        # 1. Try cache first
        cached = self.redis.get(cache_key)
        if cached is not None:
            data = json.loads(cached)
            if data is None:
                return None  # Cached "not found" (prevents cache penetration)
            return data

        # 2. Cache miss — fetch from DB with stampede protection
        lock_key = f"lock:{cache_key}"
        lock = self.redis.lock(lock_key, timeout=10)

        if lock.acquire(blocking=True, blocking_timeout=5):
            try:
                # Double-check: another thread may have populated cache
                cached = self.redis.get(cache_key)
                if cached is not None:
                    return json.loads(cached)

                # Actually hit the database
                user = db.query(User).get(user_id)

                if user:
                    # Cache ONLY safe fields (no password_hash!)
                    safe_data = {
                        "id": user.id,
                        "name": user.name,
                        "email": user.email,
                        "avatar_url": user.avatar_url,
                        "created_at": user.created_at.isoformat(),
                    }
                    self.redis.setex(cache_key, CACHE_TTL, json.dumps(safe_data))
                    return safe_data
                else:
                    # Cache the absence (prevents cache penetration)
                    self.redis.setex(cache_key, NULL_TTL, json.dumps(None))
                    return None
            finally:
                lock.release()
        else:
            # Couldn't acquire lock — another thread is loading
            # Wait briefly and retry from cache
            import time
            time.sleep(0.5)
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
            # Fallback: hit DB directly (shouldn't happen often)
            user = db.query(User).get(user_id)
            return user.to_safe_dict() if user else None

    def invalidate_user(self, user_id: int):
        """Call this whenever user data changes."""
        self.redis.delete(f"user:{int(user_id)}")
```

**Cache invalidation on writes:**

```python
# Every place that modifies a user MUST invalidate the cache
class UserService:
    def __init__(self, cache: CacheService):
        self.cache = cache

    def update_user(self, user_id: int, data: dict):
        user = db.query(User).get(user_id)
        for key, value in data.items():
            setattr(user, key, value)
        db.commit()

        # Invalidate cache — next read will fetch fresh data
        self.cache.invalidate_user(user_id)

    def deactivate_user(self, user_id: int):
        user = db.query(User).get(user_id)
        user.is_active = False
        db.commit()
        self.cache.invalidate_user(user_id)
```

**Redis configuration (prevent memory exhaustion):**

```
# redis.conf
maxmemory 256mb
maxmemory-policy allkeys-lru
# When memory is full, evict least-recently-used keys
# This prevents Redis from crashing on memory exhaustion
```

**All fixes summarized:**

| Problem | Impact | Fix |
|---|---|---|
| No TTL | Stale data forever | `setex()` with TTL |
| Cache stampede | DB overload on popular key expiry | Lock during rebuild |
| Cache penetration | DB hit for non-existent keys | Cache null results |
| Sensitive data | Data exposure if Redis compromised | Only cache safe fields |
| No invalidation | Stale data after writes | Delete cache on update |
| Memory exhaustion | Redis crashes | maxmemory + LRU eviction |
| Key injection | Cache poisoning | Sanitize cache keys (force int) |
| Race on write | Stale data re-cached after invalidation | Short TTL makes this eventually consistent |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
