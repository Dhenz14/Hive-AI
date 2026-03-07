"""
Code explanation training pairs - Auth flows, encryption, JWT validation, CSRF protection
"""

pairs = [
    {
        "instruction": r'''Walk me through this JWT validation middleware:

```python
import jwt
from functools import wraps
from flask import request, jsonify, g

def require_auth(roles=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = None
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:]

            if not token:
                return jsonify({"error": "Missing token"}), 401

            try:
                payload = jwt.decode(
                    token,
                    current_app.config['JWT_SECRET'],
                    algorithms=['HS256'],
                    options={"require": ["exp", "sub", "iat"]}
                )
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "Invalid token"}), 401

            if roles and payload.get('role') not in roles:
                return jsonify({"error": "Insufficient permissions"}), 403

            g.current_user = payload
            return f(*args, **kwargs)
        return wrapper
    return decorator
```''',
        "output": r'''This is a Flask authentication decorator that validates JWT tokens and optionally checks role-based permissions.

**Token extraction:**

Reads the `Authorization` header and expects the format `Bearer <token>`. The `[7:]` slice strips the "Bearer " prefix. If no valid header exists, returns 401 immediately.

**Token validation (`jwt.decode`):**

- `algorithms=['HS256']` -- explicitly specifies the allowed algorithm. This is critical security. Without it, an attacker could forge a token using the "none" algorithm or switch to RS256 using the public key as the secret (the "algorithm confusion" attack).
- `options={"require": ["exp", "sub", "iat"]}` -- requires these claims to be present. `exp` is expiration time (the library auto-checks this), `sub` is the subject (user ID), `iat` is issued-at time.
- The secret key comes from app config, not hardcoded.

**Error handling:**

- `ExpiredSignatureError` is caught separately from `InvalidTokenError` to give specific error messages. Both return 401 (Unauthorized), which is correct -- the client should re-authenticate.
- `InvalidTokenError` catches tampered tokens, malformed tokens, wrong algorithm, and missing required claims.

**Role checking:**

If `roles` is specified (e.g., `@require_auth(roles=["admin", "editor"])`), the token's `role` claim must be in that list. A 403 (Forbidden) is returned if not -- the user IS authenticated but lacks permission. This distinction between 401 and 403 is important.

**`g.current_user = payload`** stores the decoded token on Flask's request-scoped `g` object. Downstream route handlers can access `g.current_user['sub']` to get the user ID.

**Security note:** HS256 uses a symmetric secret. Anyone with the secret can both create and verify tokens. For services where token creation and verification happen on different servers, RS256 (asymmetric) is safer.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a password hashing implementation. I should cover why bcrypt is used and explain the salt handling.
</think>

Explain this password handling code:

```python
import bcrypt
import secrets
import hashlib

def hash_password(password: str) -> str:
    normalized = password.encode('utf-8')
    if len(normalized) > 72:
        normalized = hashlib.sha256(normalized).digest()
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(normalized, salt)
    return hashed.decode('utf-8')

def verify_password(password: str, stored_hash: str) -> bool:
    normalized = password.encode('utf-8')
    if len(normalized) > 72:
        normalized = hashlib.sha256(normalized).digest()
    return bcrypt.checkpw(normalized, stored_hash.encode('utf-8'))

def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)
```''',
        "output": r'''<think>
This handles password hashing with bcrypt including the 72-byte limit workaround, and generates secure reset tokens.
</think>

This handles secure password storage using bcrypt, with a workaround for bcrypt's input length limitation.

**`hash_password`:**

1. Encodes the password as UTF-8 bytes.
2. The 72-byte check is important: bcrypt silently truncates input beyond 72 bytes. Without this check, "aaaa....(72 a's)....bbbb" and "aaaa....(72 a's)....cccc" would hash identically. The SHA-256 pre-hash compresses long passwords to 32 bytes while preserving their uniqueness.
3. `bcrypt.gensalt(rounds=12)` generates a random salt with a work factor of 12. Each increment roughly doubles the computation time. 12 is a reasonable default in 2024 -- it takes about 250ms on modern hardware.
4. `bcrypt.hashpw` produces a string containing the algorithm identifier, cost factor, salt, AND hash all in one -- so you only need to store a single string.

**`verify_password`:**

Applies the same normalization (including the 72-byte pre-hash) and uses `bcrypt.checkpw`. Internally, bcrypt extracts the salt from the stored hash and re-hashes the candidate password to compare. This is a constant-time comparison to prevent timing attacks.

**`generate_reset_token`:**

`secrets.token_urlsafe(32)` generates 32 random bytes and base64-encodes them into a URL-safe string (~43 characters). The `secrets` module uses a cryptographically secure random source, unlike `random` which is predictable.

**Why bcrypt over SHA-256 for passwords?** SHA-256 is fast by design -- an attacker with a GPU can try billions of hashes per second. bcrypt is intentionally slow and memory-hard, making brute-force attacks impractical. The adjustable `rounds` parameter lets you increase cost as hardware gets faster.

**The pre-hash approach has a trade-off:** It reduces entropy for passwords under 72 bytes to 256 bits (SHA-256 output). In practice this does not matter since 256 bits of entropy is astronomically large.'''
    },
    {
        "instruction": r'''What does this CSRF protection code do?

```javascript
const crypto = require('crypto');

function csrfProtection() {
  return {
    generateToken(session) {
      const secret = session.csrfSecret || (session.csrfSecret = crypto.randomBytes(32).toString('hex'));
      const salt = crypto.randomBytes(8).toString('hex');
      const token = salt + '-' + crypto
        .createHmac('sha256', secret)
        .update(salt)
        .digest('hex');
      return token;
    },

    validateToken(session, token) {
      if (!token || !session.csrfSecret) return false;
      const [salt, hash] = token.split('-');
      if (!salt || !hash) return false;
      const expected = crypto
        .createHmac('sha256', session.csrfSecret)
        .update(salt)
        .digest('hex');
      return crypto.timingSafeEqual(
        Buffer.from(hash, 'hex'),
        Buffer.from(expected, 'hex')
      );
    }
  };
}
```''',
        "output": r'''This implements CSRF (Cross-Site Request Forgery) protection using the "double-submit with HMAC" pattern.

**The problem CSRF solves:** A malicious site can trick a user's browser into sending requests to your site, and the browser automatically includes cookies (including session cookies). Without CSRF protection, the server cannot tell if the request came from your app or from a malicious page.

**`generateToken`:**

1. Gets or creates a per-session secret (64 hex chars = 32 bytes of entropy). This secret is stored in the session (server-side) and never sent to the client.
2. Generates a random salt (8 bytes) for this specific token.
3. Creates an HMAC-SHA256 of the salt using the session secret.
4. The token format is `salt-hmac`. The salt is included so validation can recompute the HMAC.

**`validateToken`:**

1. Splits the token back into salt and hash.
2. Recomputes the HMAC using the session secret and the salt from the token.
3. Compares the recomputed HMAC against the one in the token.

**`crypto.timingSafeEqual`** is critical here. A normal `===` comparison returns false as soon as it finds a mismatched byte, which leaks information about how many bytes matched (timing side-channel). `timingSafeEqual` always takes the same time regardless of where the mismatch is.

**Why this is secure:** An attacker on a different site does not know the session secret (it never leaves the server). They cannot forge a valid token because they cannot compute the HMAC. Even though they can see tokens in the HTML (if they can read the page via XSS, you have bigger problems), each token has a unique salt -- but that is fine because the security comes from the HMAC, not from token secrecy.

**Why salt the tokens?** It makes each generated token unique, even for the same session. This prevents token replay tracking.'''
    },
    {
        "instruction": r'''Explain this OAuth2 authorization code flow implementation:

```python
import httpx
import secrets
from urllib.parse import urlencode

class OAuth2Client:
    def __init__(self, client_id, client_secret, redirect_uri,
                 authorize_url, token_url):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.authorize_url = authorize_url
        self.token_url = token_url

    def get_authorization_url(self, scope, session):
        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': scope,
            'state': state,
        }
        return f"{self.authorize_url}?{urlencode(params)}"

    async def exchange_code(self, code, state, session):
        if state != session.get('oauth_state'):
            raise ValueError("State mismatch - possible CSRF")
        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_url, data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': self.redirect_uri,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
            })
            response.raise_for_status()
            return response.json()
```''',
        "output": r'''This implements the OAuth2 Authorization Code flow -- the standard way for web apps to authenticate users via third-party providers (Google, GitHub, etc.).

**The flow has two phases:**

**Phase 1 -- `get_authorization_url`:**

Builds a URL that redirects the user to the provider's login page. The key parameters:
- `client_id` identifies your app to the provider.
- `redirect_uri` is where the provider sends the user back after login.
- `response_type=code` requests an authorization code (not a token directly).
- `scope` specifies what permissions you are requesting (e.g., "email profile").
- `state` is a random anti-CSRF token stored in the user's session.

**Phase 2 -- `exchange_code`:**

After the user logs in, the provider redirects them back to your `redirect_uri` with a `code` and the `state` parameter.

1. **State validation** is the first check. If the returned `state` does not match what was stored in the session, someone may be attempting a CSRF attack -- tricking the user into linking the attacker's account. This check is essential.

2. **Code exchange**: The authorization code is sent to the provider's token endpoint along with the `client_secret`. This happens server-to-server (not in the browser), so the client secret stays confidential. The provider responds with an access token (and usually a refresh token).

**Why the code exchange instead of getting the token directly?** The authorization code is exposed in the browser's URL bar (via the redirect). If that were an access token, it could be intercepted. The code is useless without the client secret, which only the server knows.

**Security note:** The `client_secret` is sent in the POST body. Some providers prefer it in an Authorization header as Basic auth. The body method is simpler but slightly less conventional.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain rate limiting middleware with a sliding window counter algorithm.
</think>

What does this rate limiting code do?

```python
import time
from collections import defaultdict
import threading

class SlidingWindowRateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window = window_seconds
        self._counters = defaultdict(lambda: {'prev': 0, 'curr': 0, 'start': 0})
        self._lock = threading.Lock()

    def allow(self, key):
        now = time.time()
        with self._lock:
            bucket = self._counters[key]
            window_start = now - (now % self.window)

            if bucket['start'] < window_start - self.window:
                bucket['prev'] = 0
                bucket['curr'] = 0
                bucket['start'] = window_start
            elif bucket['start'] < window_start:
                bucket['prev'] = bucket['curr']
                bucket['curr'] = 0
                bucket['start'] = window_start

            elapsed = now - window_start
            weight = 1 - (elapsed / self.window)
            estimate = bucket['prev'] * weight + bucket['curr']

            if estimate >= self.max_requests:
                return False

            bucket['curr'] += 1
            return True
```''',
        "output": r'''<think>
This is a sliding window counter rate limiter -- a hybrid between fixed window and true sliding window. Let me explain the weighted estimation.
</think>

This implements a sliding window counter rate limiter -- a memory-efficient approximation of a true sliding window that avoids the burst problems of fixed-window counters.

**The problem with fixed windows:** If you allow 100 requests per minute using fixed windows (e.g., 00:00-01:00), a client could send 100 requests at 00:59 and 100 more at 01:01 -- 200 requests in 2 seconds, defeating the limit.

**How the sliding window counter works:**

It maintains two counters per key: the previous window's count and the current window's count. The trick is using a weighted combination to estimate the request rate in a sliding window.

**The `allow` method step by step:**

1. Calculates the current fixed window start time by rounding down to the nearest window boundary.

2. Window rotation: if the stored window is two or more windows behind, both counters are reset. If it is one window behind, the current count becomes the previous count, and current resets to 0.

3. The weighted estimate: `prev * weight + curr` where `weight = 1 - (elapsed / window)`. If you are 30% into the current window, the previous window counts for 70% and the current window counts fully. This smoothly slides the window without storing individual request timestamps.

4. If the estimate meets or exceeds the limit, the request is denied. Otherwise, the current counter increments.

**Example:** With max_requests=10 per 60s window. Previous window had 8 requests. Current window has 3. We are 20 seconds into the current window. Weight = 1 - (20/60) = 0.67. Estimate = 8 * 0.67 + 3 = 8.36. Since 8.36 < 10, the request is allowed.

**The `threading.Lock`** makes this thread-safe. Without it, concurrent requests could read stale counters and exceed the limit.

**Trade-off:** This uses O(1) memory per key (just two counters), compared to O(n) for a true sliding window log that stores every request timestamp.'''
    },
]
