PAIRS = [
    ("thinking/debugging", r'''Users are randomly getting logged out of our application. It happens inconsistently -- sometimes after 5 minutes, sometimes after 2 hours. Our JWT setup:

```python
import jwt
from datetime import datetime, timedelta

SECRET_KEY = "my-secret-key"

def create_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["user_id"]
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
```

Server logs show tokens expiring at unexpected times:
```
10:00:00 Token created for user 42, exp=11:00:00
10:05:23 Token verified OK for user 42
10:31:15 Token verified OK for user 42
10:45:02 ExpiredSignatureError for user 42  <-- 45 minutes early!
```

We are running 4 app server instances behind a load balancer.''', r'''<think>
Tokens expiring 15 minutes early on some requests but working on others. They have 4 server instances behind a load balancer. This is a classic clock skew issue.

When you have multiple servers, each server's system clock might be slightly different. The JWT was created on Server A with its clock, but verified on Server B whose clock is ahead by 15+ minutes. So Server B thinks the token has expired.

Wait, but 15 minutes is a LOT of clock skew. That is unusual for modern NTP-synced servers. Let me think of other causes.

Actually, the more common cause with multiple servers: different SECRET_KEYs. If the secret key is hardcoded but different between deployments (e.g., one server was deployed with an older config), the token would fail with InvalidTokenError, not ExpiredSignatureError.

But the error is specifically ExpiredSignatureError, so it IS about time. Could there be a timezone issue? `datetime.utcnow()` returns a naive datetime. The `jwt` library compares `exp` against `datetime.utcnow()` internally. But if one server is configured with a different timezone and somehow that leaks in...

Actually, the most likely cause: `datetime.utcnow()` returns the current UTC time BUT as a naive datetime. The `jwt` library uses `timegm(datetime.utcnow().utctimetuple())` for comparison. If the server's system clock is wrong (not synced with NTP), this will be off.

But 15 minutes of clock skew is extreme. More likely: one or more servers have their clock set to a different timezone and are NOT using UTC. If a server's local time is 15 minutes ahead of actual UTC...

Actually wait, I just realized: `datetime.utcnow()` always returns UTC regardless of the server's timezone setting. So timezone config should not matter.

Let me reconsider: could it be that one of the 4 servers was recently restarted and its clock did not sync yet? Cloud VMs sometimes have clock drift after suspend/resume.

Or: the PyJWT library has a `leeway` parameter. Without leeway, even 1 second of clock drift can cause ExpiredSignatureError right at the boundary. But the log shows 45 minutes before the token should expire, which is way more than a few seconds.

I think the most likely explanation is genuine clock skew on one or more servers. The inconsistency (sometimes 5 min, sometimes 2 hours) maps to which server handles the verification request.
</think>

Tokens randomly expiring early across 4 server instances is almost always **clock skew between servers**. The JWT `exp` claim is set using one server's clock, but verified against a different server's clock.

**Diagnose clock skew:**

```bash
# SSH into each server and check the time
for server in app-1 app-2 app-3 app-4; do
    echo "$server: $(ssh $server date -u '+%Y-%m-%d %H:%M:%S UTC')"
done

# Output might reveal:
# app-1: 2026-03-06 10:00:00 UTC
# app-2: 2026-03-06 10:00:01 UTC
# app-3: 2026-03-06 10:15:23 UTC  <-- 15 minutes ahead!
# app-4: 2026-03-06 10:00:02 UTC
```

**Why it happens:**
- Cloud VM clocks drift after suspend/resume or live migration
- NTP daemon is not running or is misconfigured on some instances
- Container clocks inherit from the host -- if the host drifts, all containers drift

**Fix 1: Sync all server clocks with NTP:**

```bash
# Install and enable NTP synchronization on all servers
sudo timedatectl set-ntp true

# Or install chrony (better for cloud VMs)
sudo apt install chrony
sudo systemctl enable --now chrony

# Verify sync status
chronyc tracking
# Check "System time" offset -- should be microseconds, not minutes
```

**Fix 2: Add clock skew tolerance (leeway) to JWT verification:**

```python
def verify_token(token):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"],
            leeway=timedelta(seconds=30)  # Allow 30 seconds of clock skew
        )
        return payload["user_id"]
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
```

**Fix 3: Use timezone-aware datetimes (Python 3.11+ deprecation):**

```python
from datetime import datetime, timedelta, timezone

def create_token(user_id):
    now = datetime.now(timezone.utc)  # timezone-aware, not naive
    payload = {
        "user_id": user_id,
        "exp": now + timedelta(hours=1),
        "iat": now
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

**Fix 4: Use integer timestamps to avoid datetime confusion:**

```python
import time

def create_token(user_id):
    now = int(time.time())  # Unix timestamp -- no timezone ambiguity
    payload = {
        "user_id": user_id,
        "exp": now + 3600,  # 1 hour from now
        "iat": now
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

**Prevention tips:**
- Always run NTP or chrony on every server in your fleet
- Add a JWT leeway of 30-60 seconds as defense against minor clock drift
- Monitor clock skew between servers as an infrastructure metric
- Use `time.time()` (Unix timestamps) instead of `datetime.utcnow()` for JWT claims
- Add the server hostname to logs so you can correlate which server created vs verified the token
- Alert if any server clock drifts more than 5 seconds from NTP'''),

    ("thinking/debugging", r'''Our OAuth2 login flow is vulnerable to CSRF. An attacker can trick a logged-in user into linking the attacker's account:

```python
# Our OAuth callback handler
@app.route("/auth/callback")
def oauth_callback():
    code = request.args.get("code")

    # Exchange code for token
    token_response = requests.post("https://provider.com/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI
    })

    access_token = token_response.json()["access_token"]

    # Get user info from OAuth provider
    user_info = requests.get("https://provider.com/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}).json()

    # Link OAuth account to current session user
    current_user = get_current_user()
    if current_user:
        link_oauth_account(current_user.id, user_info["sub"])
        return redirect("/settings")

    return redirect("/login")
```

The attack: Attacker starts OAuth flow, gets a valid authorization code, then sends the victim a link to `/auth/callback?code=ATTACKER_CODE`. The victim's browser follows it, and the attacker's OAuth account gets linked to the victim's session.''', r'''<think>
This is a classic OAuth CSRF attack. The callback endpoint does not verify that the OAuth flow was initiated by the same user who is completing it. The state parameter is the standard defense against this.

The OAuth2 spec (RFC 6749) recommends using a `state` parameter that is:
1. Generated when the authorization request is initiated
2. Stored in the user's session
3. Verified when the callback is received
4. Unique and unpredictable (cryptographically random)

Without the state parameter, an attacker can:
1. Start an OAuth flow themselves (getting a valid authorization code)
2. Trick the victim into visiting the callback URL with the attacker's code
3. The victim's session now has the attacker's OAuth account linked

This is exactly the Login CSRF variant described in the OAuth security BCP.
</think>

This is a textbook OAuth CSRF vulnerability. The callback handler does not verify that the user who initiated the OAuth flow is the same user completing it. The fix is the **state parameter** -- a cryptographic nonce that ties the OAuth request to the user's session.

**The attack flow:**
```
1. Attacker visits /auth/login -> redirected to provider.com
2. Attacker logs in with their own OAuth account
3. Attacker copies the callback URL: /auth/callback?code=ATTACKER_CODE
4. Attacker sends this URL to the victim (phishing email, hidden iframe, etc.)
5. Victim clicks the link while logged in
6. Victim's session now has attacker's OAuth account linked
7. Attacker can now log in as the victim via OAuth
```

**Fix: Implement the state parameter:**

```python
import secrets
from flask import session

@app.route("/auth/login")
def oauth_login():
    # Generate cryptographically random state
    state = secrets.token_urlsafe(32)

    # Store in the user's session (server-side)
    session["oauth_state"] = state

    # Include state in the authorization URL
    auth_url = (
        f"https://provider.com/oauth/authorize?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&state={state}"
        f"&scope=openid profile"
    )
    return redirect(auth_url)


@app.route("/auth/callback")
def oauth_callback():
    # CRITICAL: Verify state parameter before anything else
    state = request.args.get("state")
    expected_state = session.pop("oauth_state", None)

    if not state or not expected_state or state != expected_state:
        # State mismatch -- possible CSRF attack
        abort(403, "Invalid OAuth state parameter. Please try logging in again.")

    code = request.args.get("code")
    if not code:
        abort(400, "Missing authorization code")

    # Exchange code for token (only after state verification)
    token_response = requests.post("https://provider.com/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI
    })

    if token_response.status_code != 200:
        abort(502, "Token exchange failed")

    access_token = token_response.json()["access_token"]

    user_info = requests.get("https://provider.com/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}).json()

    current_user = get_current_user()
    if current_user:
        link_oauth_account(current_user.id, user_info["sub"])
        return redirect("/settings")

    return redirect("/login")
```

**Why this prevents the attack:**
- The attacker cannot forge the state parameter because it is stored in the VICTIM's server-side session
- The attacker's crafted callback URL either has no state parameter or has the attacker's state, which does not match the victim's session
- `session.pop()` ensures each state is single-use (prevents replay attacks)

**Additional hardening:**

```python
# Add state expiration to prevent stale states
import time

@app.route("/auth/login")
def oauth_login():
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session["oauth_state_created"] = time.time()
    # ... redirect to provider

@app.route("/auth/callback")
def oauth_callback():
    state = request.args.get("state")
    expected_state = session.pop("oauth_state", None)
    created = session.pop("oauth_state_created", 0)

    # State must match AND be less than 10 minutes old
    if not state or state != expected_state or time.time() - created > 600:
        abort(403, "Invalid or expired OAuth state")
    # ... continue
```

**Prevention tips:**
- ALWAYS use the state parameter in OAuth2 flows -- it is required by the spec for CSRF protection
- Use `secrets.token_urlsafe()` for state generation, not predictable values
- Store state server-side (session), not in a cookie where it can be manipulated
- Pop the state from the session after use to prevent replay attacks
- Add a timestamp to expire stale state values
- Consider PKCE (RFC 7636) for additional security, especially for public clients'''),

    ("thinking/debugging", r'''We discovered a session fixation vulnerability in our login system. An attacker can set a session ID before the victim logs in, then hijack the session afterward:

```python
from flask import Flask, session, request, redirect

app = Flask(__name__)
app.secret_key = "supersecret"

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    user = authenticate(username, password)
    if user:
        # Store user info in the existing session
        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role
        return redirect("/dashboard")

    return "Invalid credentials", 401

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect("/login")
```

Attack scenario:
1. Attacker visits the site and gets session cookie: session=abc123
2. Attacker tricks victim into using that same session (e.g., via a crafted link with the session cookie set)
3. Victim logs in successfully
4. Attacker uses session=abc123 to access victim's account

How do we fix this?''', r'''<think>
Session fixation is a classic attack where the attacker sets the session ID before authentication, then uses that same session ID after the victim authenticates. The key vulnerability is that the session ID does NOT change after login -- the same session that was anonymous before login becomes authenticated after login with the same identifier.

The fix is simple in concept: regenerate the session ID after successful authentication. This way, even if the attacker knew the old session ID, the new authenticated session has a different ID that the attacker does not know.

In Flask, session regeneration is not built-in like it is in frameworks like Django or Rails. Flask uses client-side signed cookies by default (not server-side sessions). With Flask's default cookie sessions, session fixation works differently because the session data is stored in the cookie itself, signed with the secret key. An attacker cannot set arbitrary session data without knowing the secret key.

However, if you are using server-side session storage (Flask-Session with Redis, database, etc.), session fixation is a real concern because the session ID references server-side data.

The fix depends on the session backend:
1. Flask default (signed cookie): Less vulnerable since the attacker cannot forge the cookie, but still best practice to regenerate
2. Flask-Session (server-side): Must regenerate session ID after login
</think>

Session fixation exploits the fact that the session ID stays the same before and after authentication. The fix is to **regenerate the session ID upon successful login** so the attacker's pre-set session ID becomes useless.

**The vulnerability timeline:**
```
1. Attacker gets session cookie: session=abc123
2. Attacker tricks victim into using session=abc123
   (via URL parameter, XSS, or subdomain cookie injection)
3. Victim logs in -> session=abc123 now has user_id, role, etc.
4. Attacker uses session=abc123 -> has full access to victim's account
```

**Fix 1: Regenerate session on login (Flask with server-side sessions):**

```python
from flask import Flask, session, request, redirect

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    user = authenticate(username, password)
    if user:
        # CRITICAL: Regenerate session BEFORE storing auth data
        # Save any data you need to preserve across regeneration
        old_data = dict(session)
        session.clear()

        # Force Flask-Session to create a new session ID
        # This depends on your session backend:

        # For Flask-Session with server-side storage:
        from flask import _request_ctx_stack
        if hasattr(session, 'sid'):
            session.sid = None  # Force new SID generation

        # Or the most reliable approach:
        session.modified = True

        # Restore non-sensitive data (e.g., CSRF tokens, locale preferences)
        if "locale" in old_data:
            session["locale"] = old_data["locale"]

        # NOW set the authenticated user info
        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role
        session["login_time"] = time.time()
        session["login_ip"] = request.remote_addr

        return redirect("/dashboard")

    return "Invalid credentials", 401
```

**Fix 2: Complete session regeneration with Flask-Session:**

```python
import secrets
from flask_session import Session

def regenerate_session():
    """Create a completely new session, preserving selected data."""
    # Capture data to preserve
    preserve_keys = ["csrf_token", "locale"]
    preserved = {k: session[k] for k in preserve_keys if k in session}

    # Clear the old session entirely
    session.clear()

    # If using Flask-Session, delete the old server-side session data
    if hasattr(session, 'sid'):
        # The old session data will be orphaned in Redis/DB
        # Some backends handle this; others need manual cleanup
        pass

    # Restore preserved data into the new session
    session.update(preserved)
    session.modified = True

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    user = authenticate(username, password)
    if user:
        regenerate_session()  # New session ID!
        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role
        return redirect("/dashboard")
    return "Invalid credentials", 401
```

**Fix 3: Also fix the logout to fully destroy the session:**

```python
@app.route("/logout")
def logout():
    # Do NOT just pop individual keys -- clear the entire session
    session.clear()
    # Force a new session ID for the anonymous session too
    session.modified = True
    return redirect("/login")
```

**Fix 4: Add additional session binding for defense in depth:**

```python
@app.route("/login", methods=["POST"])
def login():
    user = authenticate(request.form["username"], request.form["password"])
    if user:
        regenerate_session()
        session["user_id"] = user.id
        session["username"] = user.username
        # Bind session to client fingerprint
        session["bound_ip"] = request.remote_addr
        session["bound_ua"] = request.headers.get("User-Agent", "")
        return redirect("/dashboard")
    return "Invalid credentials", 401

@app.before_request
def validate_session_binding():
    if "user_id" in session:
        if session.get("bound_ip") != request.remote_addr:
            session.clear()
            return redirect("/login?reason=ip_changed")
```

**Prevention tips:**
- Always regenerate the session ID after any privilege change (login, role elevation, password change)
- Use `session.clear()` on logout, not selective `session.pop()`
- Set secure cookie flags: `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_SAMESITE="Lax"`
- Bind sessions to client characteristics (IP, User-Agent) as defense in depth
- Set session expiry both server-side (TTL in Redis) and client-side (cookie max-age)
- Do not accept session IDs from URL parameters -- only from cookies'''),

    ("thinking/debugging", r'''Our PKCE OAuth flow is failing with an "invalid_grant" error. The authorization works fine, but the token exchange always fails:

```python
import hashlib
import base64
import secrets
import requests

def start_pkce_flow():
    # Generate PKCE code verifier and challenge
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode()

    # Store verifier for later
    session["code_verifier"] = code_verifier

    auth_url = (
        f"https://auth.provider.com/authorize?"
        f"client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&scope=openid profile"
    )
    return redirect(auth_url)


def handle_callback(authorization_code):
    code_verifier = session.get("code_verifier")

    response = requests.post("https://auth.provider.com/token", data={
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier
    })

    print(f"Token response: {response.status_code}")
    print(f"Body: {response.json()}")
    # Output:
    # Token response: 400
    # Body: {"error": "invalid_grant", "error_description": "code_verifier does not match code_challenge"}
```

The verifier is correctly stored and retrieved from the session. What is wrong?''', r'''<think>
The error says "code_verifier does not match code_challenge." This means the authorization server received a code_challenge during the /authorize request that does not match the hash of the code_verifier sent during the /token request.

Let me look at the PKCE implementation carefully:

```python
code_verifier = secrets.token_urlsafe(32)
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).decode()
```

The PKCE spec (RFC 7636) says:
- code_challenge = BASE64URL(SHA256(code_verifier))

BASE64URL encoding is base64 with URL-safe characters (+/ replaced with -_) AND with padding (=) stripped.

But `base64.urlsafe_b64encode()` in Python includes the padding `=` characters. The URL-safe base64 output will have `=` or `==` at the end.

When this is placed in the URL:
```
code_challenge=abc123def456==
```

The `=` characters might be URL-encoded as `%3D` by the browser or requests library. But the authorization server stores the raw challenge value. Then when verifying, it computes BASE64URL-NOPAD(SHA256(verifier)) and compares -- the padding causes a mismatch.

Actually, let me re-check: the challenge is sent as a URL parameter. URL encoding should handle the `=` signs. But the PKCE spec specifically requires BASE64URL encoding WITHOUT padding (RFC 4648 Section 5 with padding removed per RFC 7636 Appendix B).

So the bug is: the code_challenge includes padding characters (`=`), but the authorization server expects unpadded BASE64URL encoding per the PKCE spec.
</think>

The bug is in the base64 encoding of the code challenge. PKCE (RFC 7636) requires **BASE64URL encoding without padding**, but Python's `base64.urlsafe_b64encode()` includes padding (`=` characters).

**The mismatch:**

```python
# Your code produces (with padding):
code_challenge = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk="
#                                                              ^
#                                                     This = is the problem

# The auth server expects (without padding, per RFC 7636):
code_challenge = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
```

When the auth server receives the code_verifier, it computes `BASE64URL-NOPAD(SHA256(verifier))` and compares it against the stored challenge. Your padded challenge does not match.

**The fix -- strip padding from the base64 output:**

```python
import hashlib
import base64
import secrets

def start_pkce_flow():
    code_verifier = secrets.token_urlsafe(32)

    # PKCE requires BASE64URL encoding WITHOUT padding
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")  # <-- Strip padding!

    session["code_verifier"] = code_verifier

    auth_url = (
        f"https://auth.provider.com/authorize?"
        f"client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&scope=openid profile"
    )
    return redirect(auth_url)
```

**Also verify the code_verifier length:**

```python
# RFC 7636 requires code_verifier to be 43-128 characters
# secrets.token_urlsafe(32) produces 43 characters -- just at the minimum
# Using 48 bytes gives a more comfortable 64-character verifier
code_verifier = secrets.token_urlsafe(48)  # 64 characters

# Verify length
assert 43 <= len(code_verifier) <= 128, f"Invalid verifier length: {len(code_verifier)}"
```

**Complete corrected PKCE implementation:**

```python
import hashlib
import base64
import secrets
import requests
from urllib.parse import urlencode

def generate_pkce_pair():
    """Generate a PKCE code verifier and challenge pair."""
    # 48 bytes -> 64 URL-safe characters
    code_verifier = secrets.token_urlsafe(48)

    # SHA256 hash, then BASE64URL without padding (per RFC 7636)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    return code_verifier, code_challenge


def start_pkce_flow():
    code_verifier, code_challenge = generate_pkce_pair()
    session["code_verifier"] = code_verifier

    params = urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": "openid profile",
        "state": secrets.token_urlsafe(32),  # Don't forget CSRF protection
    })
    return redirect(f"https://auth.provider.com/authorize?{params}")


def handle_callback(authorization_code):
    code_verifier = session.pop("code_verifier", None)
    if not code_verifier:
        abort(400, "Missing PKCE code verifier")

    response = requests.post("https://auth.provider.com/token", data={
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
    })

    if response.status_code != 200:
        abort(502, f"Token exchange failed: {response.json()}")

    return response.json()
```

**Prevention tips:**
- Always strip `=` padding from base64 when implementing PKCE -- the RFC requires unpadded BASE64URL
- Use `urlencode()` for building query strings to properly escape special characters
- Test your PKCE implementation against the RFC 7636 Appendix B test vectors
- Use `session.pop()` to consume the verifier (single-use)
- Combine PKCE with the state parameter for both CSRF protection and code interception defense
- Consider using an OAuth library (authlib, oauthlib) instead of implementing PKCE manually'''),

    ("thinking/debugging", r'''We have a token refresh deadlock in our API client. When multiple concurrent requests detect an expired access token, they all try to refresh simultaneously, causing a cascade of 401 errors:

```python
import requests
import threading

class APIClient:
    def __init__(self, base_url, refresh_token):
        self.base_url = base_url
        self.refresh_token = refresh_token
        self.access_token = None
        self.session = requests.Session()

    def _refresh_access_token(self):
        response = self.session.post(f"{self.base_url}/auth/refresh", json={
            "refresh_token": self.refresh_token
        })
        data = response.json()
        self.access_token = data["access_token"]
        # Server invalidates old refresh token and returns new one
        self.refresh_token = data["refresh_token"]

    def request(self, method, path, **kwargs):
        if not self.access_token:
            self._refresh_access_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = self.session.request(method, f"{self.base_url}{path}",
                                         headers=headers, **kwargs)

        if response.status_code == 401:
            # Token expired, refresh and retry
            self._refresh_access_token()
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = self.session.request(method, f"{self.base_url}{path}",
                                             headers=headers, **kwargs)
        return response

# Usage with concurrent requests:
client = APIClient("https://api.example.com", "initial_refresh_token")
threads = []
for i in range(10):
    t = threading.Thread(target=client.request, args=("GET", f"/data/{i}"))
    threads.append(t)
    t.start()
```

Logs show:
```
Thread-1: 401 -> refreshing token
Thread-2: 401 -> refreshing token
Thread-3: 401 -> refreshing token
Thread-1: refresh succeeded, new access_token=tok_abc
Thread-2: refresh FAILED - refresh_token already used (invalidated by Thread-1)
Thread-3: refresh FAILED - refresh_token already used (invalidated by Thread-1)
Thread-2: 401 on retry -> refreshing again -> FAILED (refresh_token invalid)
Thread-3: 401 on retry -> refreshing again -> FAILED (refresh_token invalid)
```''', r'''<think>
This is a classic token refresh race condition. Multiple threads detect the expired access token simultaneously, and they all try to refresh. The server uses rotating refresh tokens (each refresh invalidates the old refresh token). So Thread-1 refreshes successfully and gets a new refresh_token. But Thread-2 and Thread-3 are still using the OLD refresh_token which is now invalid.

The solution: use a lock to ensure only ONE thread refreshes the token at a time. Other threads should wait for the refresh to complete and then use the new access token.

This needs:
1. A threading Lock around the refresh operation
2. A way for waiting threads to detect that someone else already refreshed (so they do not refresh again)
3. Proper error handling for the race condition
</think>

This is a classic token refresh race condition with rotating refresh tokens. Thread-1 refreshes successfully and invalidates the old refresh token. Threads 2 and 3 then try to use the now-invalid refresh token and fail permanently.

**The race condition timeline:**
```
t=0: All 10 threads get 401 (access token expired)
t=1: All 10 threads call _refresh_access_token() concurrently
t=2: Thread-1 succeeds, server rotates refresh_token
t=2: Threads 2-10 fail because old refresh_token is invalidated
t=3: Threads 2-10 retry refresh -> fail again (refresh_token permanently invalid)
Result: 9 out of 10 requests fail permanently
```

**Fix: Use a lock so only one thread refreshes at a time:**

```python
import requests
import threading
import time

class APIClient:
    def __init__(self, base_url, refresh_token):
        self.base_url = base_url
        self.refresh_token = refresh_token
        self.access_token = None
        self.session = requests.Session()
        self._refresh_lock = threading.Lock()
        self._token_version = 0  # Track token generation

    def _refresh_access_token(self, failed_token):
        """Refresh token with deduplication.

        Only refreshes if the current access_token matches the one that
        failed. If another thread already refreshed, this is a no-op.
        """
        with self._refresh_lock:
            # Check if another thread already refreshed while we waited
            if self.access_token != failed_token:
                # Token was already refreshed by another thread
                return True

            try:
                response = self.session.post(
                    f"{self.base_url}/auth/refresh",
                    json={"refresh_token": self.refresh_token},
                    timeout=10
                )

                if response.status_code != 200:
                    return False

                data = response.json()
                self.access_token = data["access_token"]
                self.refresh_token = data["refresh_token"]
                self._token_version += 1
                return True

            except requests.RequestException:
                return False

    def request(self, method, path, **kwargs):
        # Initial token fetch if needed
        if not self.access_token:
            with self._refresh_lock:
                if not self.access_token:
                    self._refresh_access_token(None)

        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = self.session.request(
            method, f"{self.base_url}{path}",
            headers=headers, **kwargs
        )

        if response.status_code == 401:
            failed_token = self.access_token  # Capture the token that failed
            if self._refresh_access_token(failed_token):
                # Retry with new token
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = self.session.request(
                    method, f"{self.base_url}{path}",
                    headers=headers, **kwargs
                )

        return response
```

**Key design decisions:**

1. **Token comparison as dedup key**: `_refresh_access_token` takes the `failed_token` as a parameter. If the current token has already changed (another thread refreshed), it skips the refresh.

2. **Lock scope**: The lock covers only the refresh operation, not the entire request. Requests can proceed in parallel; only the refresh is serialized.

3. **Double-check locking**: Before refreshing, check if the token was already updated by another thread that held the lock first.

**How it works with 10 concurrent threads:**
```
t=0: All 10 threads get 401, all capture failed_token="tok_expired"
t=1: Thread-1 acquires lock, refreshes successfully
     access_token changes from "tok_expired" to "tok_new"
t=2: Thread-2 acquires lock, sees access_token != failed_token
     -> skips refresh, uses the new token
t=2: Threads 3-10 same as Thread-2 -> all skip refresh
Result: 1 refresh call, all 10 threads succeed
```

**Even more robust: use an Event for waiting threads:**

```python
class APIClient:
    def __init__(self, base_url, refresh_token):
        self.base_url = base_url
        self.refresh_token = refresh_token
        self.access_token = None
        self._refresh_lock = threading.Lock()
        self._refreshing = threading.Event()
        self._refreshing.set()  # Not refreshing initially

    def _ensure_valid_token(self, failed_token):
        # Wait if another thread is already refreshing
        self._refreshing.wait(timeout=30)

        with self._refresh_lock:
            if self.access_token != failed_token:
                return True  # Already refreshed

            self._refreshing.clear()  # Signal: refresh in progress
            try:
                response = self.session.post(
                    f"{self.base_url}/auth/refresh",
                    json={"refresh_token": self.refresh_token}
                )
                data = response.json()
                self.access_token = data["access_token"]
                self.refresh_token = data["refresh_token"]
                return True
            finally:
                self._refreshing.set()  # Signal: refresh complete
```

**Prevention tips:**
- Always serialize token refresh operations with a lock when using rotating refresh tokens
- Use the "failed token" pattern to deduplicate refresh attempts
- Add a timeout to the lock acquisition to prevent indefinite blocking
- Log token refresh events with thread IDs for debugging race conditions
- Consider using a single-use refresh token queue on the server side that allows a grace period for concurrent uses
- If the server supports it, use non-rotating refresh tokens to eliminate this class of bugs entirely'''),
]
