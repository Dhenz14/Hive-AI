"""Authentication patterns — JWT, OAuth2, session management, and security."""

PAIRS = [
    (
        "security/jwt-authentication",
        "Show JWT authentication patterns: token generation, refresh tokens, middleware, and security best practices in Python.",
        '''JWT authentication with refresh token rotation:

```python
import jwt
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional
from functools import wraps

# --- Token configuration ---

@dataclass
class TokenConfig:
    secret_key: str
    algorithm: str = "HS256"
    access_token_ttl: timedelta = timedelta(minutes=15)
    refresh_token_ttl: timedelta = timedelta(days=7)
    issuer: str = "myapp"

@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900  # seconds


class AuthService:
    def __init__(self, config: TokenConfig, user_repo, token_store):
        self.config = config
        self.user_repo = user_repo
        self.token_store = token_store  # Redis for refresh tokens

    # --- Token generation ---

    def create_token_pair(self, user_id: str, roles: list[str]) -> TokenPair:
        now = datetime.now(timezone.utc)

        # Access token (short-lived, stateless)
        access_payload = {
            "sub": user_id,
            "roles": roles,
            "type": "access",
            "iat": now,
            "exp": now + self.config.access_token_ttl,
            "iss": self.config.issuer,
            "jti": secrets.token_hex(16),
        }
        access_token = jwt.encode(
            access_payload, self.config.secret_key,
            algorithm=self.config.algorithm
        )

        # Refresh token (long-lived, stored server-side)
        refresh_token = secrets.token_urlsafe(64)
        refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

        # Store refresh token hash (not the token itself)
        self.token_store.set(
            f"refresh:{refresh_hash}",
            {
                "user_id": user_id,
                "roles": roles,
                "created_at": now.isoformat(),
                "family": secrets.token_hex(8),  # Token family for rotation
            },
            ex=int(self.config.refresh_token_ttl.total_seconds()),
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self.config.access_token_ttl.total_seconds()),
        )

    # --- Token verification ---

    def verify_access_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                issuer=self.config.issuer,
                options={"require": ["sub", "exp", "iat", "jti"]},
            )
            if payload.get("type") != "access":
                raise jwt.InvalidTokenError("Not an access token")
            return payload
        except jwt.ExpiredSignatureError:
            raise AuthError("Token expired", code=401)
        except jwt.InvalidTokenError as e:
            raise AuthError(f"Invalid token: {e}", code=401)

    # --- Refresh token rotation ---

    def refresh_tokens(self, refresh_token: str) -> TokenPair:
        """Rotate refresh token — old token invalidated, new pair issued."""
        refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        stored = self.token_store.get(f"refresh:{refresh_hash}")

        if not stored:
            raise AuthError("Invalid refresh token", code=401)

        # Delete used refresh token (rotation)
        self.token_store.delete(f"refresh:{refresh_hash}")

        # Issue new token pair
        return self.create_token_pair(
            user_id=stored["user_id"],
            roles=stored["roles"],
        )

    # --- Logout (invalidate refresh token) ---

    def logout(self, refresh_token: str):
        refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        self.token_store.delete(f"refresh:{refresh_hash}")

    def logout_all_sessions(self, user_id: str):
        """Invalidate all refresh tokens for a user."""
        # Scan and delete all refresh tokens for this user
        for key in self.token_store.scan_iter("refresh:*"):
            data = self.token_store.get(key)
            if data and data.get("user_id") == user_id:
                self.token_store.delete(key)


# --- FastAPI middleware ---

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
):
    payload = auth_service.verify_access_token(credentials.credentials)
    return payload

def require_role(*roles: str):
    """Role-based access control decorator."""
    async def dependency(user: dict = Depends(get_current_user)):
        user_roles = set(user.get("roles", []))
        if not user_roles.intersection(roles):
            raise HTTPException(403, "Insufficient permissions")
        return user
    return Depends(dependency)

# Usage in routes:
# @app.get("/admin/users")
# async def list_users(user=require_role("admin")):
#     ...

# @app.post("/auth/login")
# async def login(credentials: LoginRequest, auth: AuthService = Depends()):
#     user = await auth.user_repo.verify_credentials(
#         credentials.email, credentials.password
#     )
#     return auth.create_token_pair(user.id, user.roles)

# @app.post("/auth/refresh")
# async def refresh(body: RefreshRequest, auth: AuthService = Depends()):
#     return auth.refresh_tokens(body.refresh_token)
```

Security best practices:
1. **Short access tokens** (15min) — limits exposure if stolen
2. **Refresh token rotation** — each refresh invalidates old token
3. **Hash stored tokens** — never store raw refresh tokens
4. **Server-side storage** — refresh tokens in Redis, not just in JWT
5. **Role-based access** — embed roles in JWT for stateless authz
6. **Logout support** — delete refresh token from store'''
    ),
    (
        "security/oauth2-implementation",
        "Show OAuth2 authorization code flow implementation: provider integration, PKCE, state parameter, and token exchange.",
        '''OAuth2 Authorization Code Flow with PKCE:

```python
import httpx
import secrets
import hashlib
import base64
from urllib.parse import urlencode, parse_qs
from dataclasses import dataclass
from typing import Optional

@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str]

# --- Provider configurations ---

GOOGLE_CONFIG = OAuthConfig(
    client_id="...",
    client_secret="...",
    redirect_uri="http://localhost:8000/auth/callback/google",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
    scopes=["openid", "email", "profile"],
)

GITHUB_CONFIG = OAuthConfig(
    client_id="...",
    client_secret="...",
    redirect_uri="http://localhost:8000/auth/callback/github",
    authorize_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
    userinfo_url="https://api.github.com/user",
    scopes=["read:user", "user:email"],
)


class OAuthFlow:
    def __init__(self, config: OAuthConfig, state_store):
        self.config = config
        self.state_store = state_store  # Redis or session

    def get_authorization_url(self) -> tuple[str, str]:
        """Generate authorization URL with PKCE and state."""
        # CSRF protection
        state = secrets.token_urlsafe(32)

        # PKCE: code verifier and challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()

        # Store state -> verifier mapping
        self.state_store.set(
            f"oauth_state:{state}",
            {"code_verifier": code_verifier},
            ex=600,  # 10 min expiry
        )

        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        url = f"{self.config.authorize_url}?{urlencode(params)}"
        return url, state

    async def handle_callback(self, code: str, state: str) -> dict:
        """Exchange authorization code for tokens."""
        # Verify state (CSRF protection)
        stored = self.state_store.get(f"oauth_state:{state}")
        if not stored:
            raise OAuthError("Invalid or expired state parameter")

        self.state_store.delete(f"oauth_state:{state}")
        code_verifier = stored["code_verifier"]

        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                self.config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.config.redirect_uri,
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
            )

            if token_response.status_code != 200:
                raise OAuthError(f"Token exchange failed: {token_response.text}")

            tokens = token_response.json()

            # Fetch user info
            userinfo_response = await client.get(
                self.config.userinfo_url,
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "Accept": "application/json",
                },
            )

            if userinfo_response.status_code != 200:
                raise OAuthError("Failed to fetch user info")

            return {
                "tokens": tokens,
                "user_info": userinfo_response.json(),
            }


# --- FastAPI OAuth routes ---

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

app = FastAPI()
flows = {
    "google": OAuthFlow(GOOGLE_CONFIG, state_store),
    "github": OAuthFlow(GITHUB_CONFIG, state_store),
}

@app.get("/auth/login/{provider}")
async def oauth_login(provider: str):
    flow = flows.get(provider)
    if not flow:
        raise HTTPException(400, f"Unknown provider: {provider}")
    url, state = flow.get_authorization_url()
    return RedirectResponse(url)

@app.get("/auth/callback/{provider}")
async def oauth_callback(provider: str, code: str, state: str):
    flow = flows.get(provider)
    result = await flow.handle_callback(code, state)

    user_info = result["user_info"]
    # Find or create user in database
    user = await find_or_create_oauth_user(
        provider=provider,
        provider_id=str(user_info.get("id") or user_info.get("sub")),
        email=user_info.get("email"),
        name=user_info.get("name"),
    )

    # Issue our own JWT tokens
    token_pair = auth_service.create_token_pair(user.id, user.roles)

    # Redirect to frontend with tokens
    params = urlencode({
        "access_token": token_pair.access_token,
        "refresh_token": token_pair.refresh_token,
    })
    return RedirectResponse(f"http://localhost:3000/auth/callback?{params}")
```

Security checklist:
1. **State parameter** — prevents CSRF attacks on callback
2. **PKCE** — prevents authorization code interception (required for public clients)
3. **Short-lived codes** — authorization codes expire quickly (10 min)
4. **Server-side exchange** — client secret never exposed to browser
5. **Validate redirect_uri** — must match registered URI exactly'''
    ),
    (
        "security/session-management",
        "Show secure session management patterns: cookie-based sessions, session fixation prevention, and concurrent session control.",
        '''Secure session management patterns:

```python
import secrets
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, field

@dataclass
class Session:
    session_id: str
    user_id: str
    ip_address: str
    user_agent: str
    created_at: datetime
    last_active: datetime
    expires_at: datetime
    data: dict = field(default_factory=dict)

class SessionManager:
    def __init__(self, store, max_sessions_per_user: int = 5,
                 session_ttl: timedelta = timedelta(hours=24),
                 idle_timeout: timedelta = timedelta(minutes=30)):
        self.store = store  # Redis
        self.max_sessions = max_sessions_per_user
        self.session_ttl = session_ttl
        self.idle_timeout = idle_timeout

    def create_session(self, user_id: str, ip: str,
                       user_agent: str) -> Session:
        """Create new session with fixation prevention."""
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)

        session = Session(
            session_id=session_id,
            user_id=user_id,
            ip_address=ip,
            user_agent=user_agent,
            created_at=now,
            last_active=now,
            expires_at=now + self.session_ttl,
        )

        # Store session
        session_hash = self._hash_id(session_id)
        self.store.set(
            f"session:{session_hash}",
            self._serialize(session),
            ex=int(self.session_ttl.total_seconds()),
        )

        # Track user's sessions
        self.store.sadd(f"user_sessions:{user_id}", session_hash)
        self._enforce_session_limit(user_id)

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve and validate session."""
        session_hash = self._hash_id(session_id)
        data = self.store.get(f"session:{session_hash}")
        if not data:
            return None

        session = self._deserialize(data)
        now = datetime.now(timezone.utc)

        # Check expiry
        if now > session.expires_at:
            self.destroy_session(session_id)
            return None

        # Check idle timeout
        if now - session.last_active > self.idle_timeout:
            self.destroy_session(session_id)
            return None

        # Update last active
        session.last_active = now
        self.store.set(
            f"session:{session_hash}",
            self._serialize(session),
            ex=int(self.session_ttl.total_seconds()),
        )

        return session

    def regenerate_session(self, old_session_id: str) -> Optional[Session]:
        """Regenerate session ID (fixation prevention)."""
        old_session = self.get_session(old_session_id)
        if not old_session:
            return None

        # Create new session with same data
        new_session = self.create_session(
            user_id=old_session.user_id,
            ip=old_session.ip_address,
            user_agent=old_session.user_agent,
        )
        new_session.data = old_session.data

        # Destroy old session
        self.destroy_session(old_session_id)

        return new_session

    def destroy_session(self, session_id: str):
        session_hash = self._hash_id(session_id)
        data = self.store.get(f"session:{session_hash}")
        if data:
            session = self._deserialize(data)
            self.store.srem(f"user_sessions:{session.user_id}", session_hash)
        self.store.delete(f"session:{session_hash}")

    def destroy_all_sessions(self, user_id: str):
        """Logout from all devices."""
        session_hashes = self.store.smembers(f"user_sessions:{user_id}")
        for session_hash in session_hashes:
            self.store.delete(f"session:{session_hash}")
        self.store.delete(f"user_sessions:{user_id}")

    def get_active_sessions(self, user_id: str) -> list[dict]:
        """List all active sessions for a user."""
        session_hashes = self.store.smembers(f"user_sessions:{user_id}")
        sessions = []
        for sh in session_hashes:
            data = self.store.get(f"session:{sh}")
            if data:
                s = self._deserialize(data)
                sessions.append({
                    "ip": s.ip_address,
                    "user_agent": s.user_agent,
                    "last_active": s.last_active.isoformat(),
                    "created": s.created_at.isoformat(),
                })
        return sessions

    def _enforce_session_limit(self, user_id: str):
        """Remove oldest sessions if over limit."""
        session_hashes = self.store.smembers(f"user_sessions:{user_id}")
        if len(session_hashes) <= self.max_sessions:
            return

        sessions = []
        for sh in session_hashes:
            data = self.store.get(f"session:{sh}")
            if data:
                s = self._deserialize(data)
                sessions.append((sh, s.last_active))
            else:
                self.store.srem(f"user_sessions:{user_id}", sh)

        sessions.sort(key=lambda x: x[1])
        to_remove = len(sessions) - self.max_sessions
        for sh, _ in sessions[:to_remove]:
            self.store.delete(f"session:{sh}")
            self.store.srem(f"user_sessions:{user_id}", sh)

    def _hash_id(self, session_id: str) -> str:
        return hashlib.sha256(session_id.encode()).hexdigest()

    def _serialize(self, session: Session) -> str:
        return json.dumps({
            "session_id": session.session_id,
            "user_id": session.user_id,
            "ip": session.ip_address,
            "ua": session.user_agent,
            "created": session.created_at.isoformat(),
            "active": session.last_active.isoformat(),
            "expires": session.expires_at.isoformat(),
            "data": session.data,
        })

    def _deserialize(self, raw: str) -> Session:
        d = json.loads(raw)
        return Session(
            session_id=d["session_id"], user_id=d["user_id"],
            ip_address=d["ip"], user_agent=d["ua"],
            created_at=datetime.fromisoformat(d["created"]),
            last_active=datetime.fromisoformat(d["active"]),
            expires_at=datetime.fromisoformat(d["expires"]),
            data=d.get("data", {}),
        )
```

```python
# --- Secure cookie settings ---

SESSION_COOKIE_CONFIG = {
    "key": "session_id",
    "httponly": True,     # Not accessible via JavaScript
    "secure": True,       # HTTPS only
    "samesite": "lax",    # CSRF protection
    "max_age": 86400,     # 24 hours
    "path": "/",
    "domain": ".example.com",
}
```

Security measures:
1. **Session fixation** — regenerate ID after login/privilege change
2. **Idle timeout** — expire inactive sessions (30min)
3. **Concurrent limit** — max 5 sessions per user, oldest evicted
4. **Hashed storage** — store SHA-256 of session ID, not raw value
5. **Secure cookies** — httpOnly, secure, sameSite=lax
6. **Logout everywhere** — destroy all sessions for compromised accounts'''
    ),
]
"""
