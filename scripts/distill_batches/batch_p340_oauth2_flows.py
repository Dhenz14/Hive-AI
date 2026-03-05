"""OAuth2 flows: authorization code + PKCE, client credentials, token introspection, OIDC, social login."""

PAIRS = [
    (
        "security/oauth2-authorization-code-pkce",
        "How do I implement the OAuth2 Authorization Code flow with PKCE in a Python web application?",
        '''The Authorization Code flow with PKCE (Proof Key for Code Exchange) is the recommended OAuth2 flow for public clients (SPAs, mobile apps) and is now best practice even for confidential clients. PKCE prevents authorization code interception attacks by binding the code to the client that requested it.

Here is a complete implementation using FastAPI:

```python
"""OAuth2 Authorization Code + PKCE flow implementation."""

import hashlib
import secrets
import time
import base64
from urllib.parse import urlencode, parse_qs, urlparse
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from itsdangerous import URLSafeTimedSerializer
from redis.asyncio import Redis

app = FastAPI()
redis = Redis(host="localhost", port=6379, decode_responses=True)

# Configuration
OAUTH_CONFIG = {
    "authorization_endpoint": "https://auth.example.com/authorize",
    "token_endpoint": "https://auth.example.com/oauth/token",
    "userinfo_endpoint": "https://auth.example.com/userinfo",
    "client_id": "my-app-client-id",
    "client_secret": "my-app-client-secret",  # Optional for public clients
    "redirect_uri": "https://myapp.com/auth/callback",
    "scopes": ["openid", "profile", "email"],
}

SESSION_SECRET = secrets.token_hex(32)
serializer = URLSafeTimedSerializer(SESSION_SECRET)


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    # code_verifier: 43-128 chars, unreserved URI characters
    code_verifier = secrets.token_urlsafe(64)[:128]

    # code_challenge: BASE64URL(SHA256(code_verifier))
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    return code_verifier, code_challenge


def generate_state_token(session_id: str) -> str:
    """Generate a CSRF-safe state parameter tied to the session."""
    return serializer.dumps({"sid": session_id, "nonce": secrets.token_hex(16)})


def verify_state_token(state: str, max_age: int = 600) -> dict:
    """Verify state token is valid and not expired (10 min default)."""
    try:
        return serializer.loads(state, max_age=max_age)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")


@app.get("/auth/login")
async def login(request: Request):
    """Initiate OAuth2 Authorization Code + PKCE flow."""
    # Create session ID for state binding
    session_id = secrets.token_hex(16)

    # Generate PKCE pair
    code_verifier, code_challenge = generate_pkce_pair()

    # Generate CSRF state token
    state = generate_state_token(session_id)

    # Store code_verifier in Redis (tied to session, 10 min TTL)
    await redis.setex(f"pkce:{session_id}", 600, code_verifier)

    # Build authorization URL
    params = {
        "response_type": "code",
        "client_id": OAUTH_CONFIG["client_id"],
        "redirect_uri": OAUTH_CONFIG["redirect_uri"],
        "scope": " ".join(OAUTH_CONFIG["scopes"]),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        # Optional: force re-consent or select account
        "prompt": "consent",
    }
    auth_url = f"{OAUTH_CONFIG['authorization_endpoint']}?{urlencode(params)}"

    response = RedirectResponse(url=auth_url, status_code=302)
    # Set session cookie (HttpOnly, Secure, SameSite=Lax)
    response.set_cookie(
        key="oauth_session",
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=600,
    )
    return response


@app.get("/auth/callback")
async def callback(request: Request, code: str, state: str):
    """Handle OAuth2 callback and exchange code for tokens."""
    # Verify state parameter (CSRF protection)
    state_data = verify_state_token(state)
    session_id = state_data["sid"]

    # Verify session cookie matches state
    cookie_session = request.cookies.get("oauth_session")
    if cookie_session != session_id:
        raise HTTPException(status_code=400, detail="Session mismatch")

    # Retrieve code_verifier from Redis
    code_verifier = await redis.getdel(f"pkce:{session_id}")
    if not code_verifier:
        raise HTTPException(status_code=400, detail="PKCE verifier not found or expired")

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            OAUTH_CONFIG["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OAUTH_CONFIG["redirect_uri"],
                "client_id": OAUTH_CONFIG["client_id"],
                "client_secret": OAUTH_CONFIG["client_secret"],
                "code_verifier": code_verifier,
            },
            headers={"Accept": "application/json"},
        )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Token exchange failed: {token_response.text}",
        )

    tokens = token_response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)
    id_token = tokens.get("id_token")  # Present if OIDC

    # Store tokens in Redis, keyed by a new session token
    user_session = secrets.token_hex(32)
    await redis.hset(f"session:{user_session}", mapping={
        "access_token": access_token,
        "refresh_token": refresh_token or "",
        "expires_at": str(int(time.time()) + expires_in),
        "id_token": id_token or "",
    })
    await redis.expire(f"session:{user_session}", expires_in)

    # Set secure session cookie
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="session",
        value=user_session,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=expires_in,
    )
    response.delete_cookie("oauth_session")
    return response


async def get_current_user(request: Request) -> dict:
    """Dependency to get the current authenticated user."""
    session_token = request.cookies.get("session")
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await redis.hgetall(f"session:{session_token}")
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")

    # Check if access token is expired
    if int(session.get("expires_at", 0)) < int(time.time()):
        # Attempt token refresh
        if session.get("refresh_token"):
            await refresh_access_token(session_token, session["refresh_token"])
            session = await redis.hgetall(f"session:{session_token}")
        else:
            raise HTTPException(status_code=401, detail="Token expired")

    return {"access_token": session["access_token"], "session": session_token}


async def refresh_access_token(session_key: str, refresh_token: str):
    """Use refresh token to obtain new access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            OAUTH_CONFIG["token_endpoint"],
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": OAUTH_CONFIG["client_id"],
                "client_secret": OAUTH_CONFIG["client_secret"],
            },
        )

    if response.status_code != 200:
        await redis.delete(f"session:{session_key}")
        raise HTTPException(status_code=401, detail="Refresh failed, please re-login")

    tokens = response.json()
    expires_in = tokens.get("expires_in", 3600)

    await redis.hset(f"session:{session_key}", mapping={
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", refresh_token),
        "expires_at": str(int(time.time()) + expires_in),
    })
    await redis.expire(f"session:{session_key}", expires_in)


@app.get("/auth/logout")
async def logout(request: Request):
    """Clear session and revoke tokens."""
    session_token = request.cookies.get("session")
    if session_token:
        session = await redis.hgetall(f"session:{session_token}")
        # Revoke token at the provider if supported
        if session.get("access_token"):
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://auth.example.com/oauth/revoke",
                    data={"token": session["access_token"]},
                    auth=(OAUTH_CONFIG["client_id"], OAUTH_CONFIG["client_secret"]),
                )
        await redis.delete(f"session:{session_token}")

    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session")
    return response


@app.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    """Protected route requiring authentication."""
    return {"message": "Welcome to dashboard", "session": user["session"][:8] + "..."}
```

Key security considerations for PKCE:

| Aspect | Implementation |
|--------|---------------|
| code_verifier | 43-128 chars, cryptographically random |
| code_challenge | BASE64URL(SHA256(verifier)), always use S256 |
| State parameter | Signed token tied to session cookie (CSRF) |
| Token storage | Server-side in Redis, never exposed to client |
| Cookies | HttpOnly + Secure + SameSite=Lax |
| Code verifier storage | Redis with TTL, deleted after use |
| Token refresh | Automatic with refresh_token rotation |

Key patterns to follow:

- Always use S256 for code_challenge_method, never plain
- Bind the state parameter to the session using a signed token
- Store code_verifier server-side, not in browser localStorage
- Delete code_verifier immediately after token exchange (one-time use)
- Use short TTLs for PKCE storage (10 minutes max)
- Implement token refresh to avoid forcing re-authentication
- Revoke tokens on logout when the provider supports it
- Set all cookies with HttpOnly, Secure, and SameSite flags'''
    ),
    (
        "security/oauth2-client-credentials",
        "How do I implement the OAuth2 Client Credentials flow for service-to-service communication?",
        '''The Client Credentials flow is used for machine-to-machine (M2M) authentication where no user context is needed. Common scenarios include microservice communication, background jobs, and API integrations.

Here is a production-grade implementation with token caching and automatic renewal:

```python
"""OAuth2 Client Credentials flow with caching and retry."""

import time
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


@dataclass
class TokenInfo:
    """Cached token with metadata."""
    access_token: str
    expires_at: float
    token_type: str = "Bearer"
    scope: str = ""

    @property
    def is_expired(self) -> bool:
        # Consider expired 60 seconds early to avoid edge cases
        return time.time() >= (self.expires_at - 60)

    @property
    def ttl(self) -> float:
        return max(0, self.expires_at - time.time())


class ClientCredentialsAuth:
    """Thread-safe OAuth2 client credentials manager with token caching."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scopes: list[str] | None = None,
        audience: str | None = None,
        extra_params: dict | None = None,
    ):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes or []
        self.audience = audience
        self.extra_params = extra_params or {}
        self._token: Optional[TokenInfo] = None
        self._lock = asyncio.Lock()
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_connections=10),
            )
        return self._http_client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    )
    async def _fetch_token(self) -> TokenInfo:
        """Fetch a new access token from the authorization server."""
        client = await self._get_http_client()

        payload = {
            "grant_type": "client_credentials",
            **self.extra_params,
        }

        if self.scopes:
            payload["scope"] = " ".join(self.scopes)
        if self.audience:
            payload["audience"] = self.audience

        response = await client.post(
            self.token_url,
            data=payload,
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
        )

        if response.status_code == 401:
            raise PermissionError(
                f"Client authentication failed: {response.text}"
            )
        if response.status_code == 403:
            raise PermissionError(
                f"Insufficient scopes or permissions: {response.text}"
            )

        response.raise_for_status()
        data = response.json()

        token = TokenInfo(
            access_token=data["access_token"],
            expires_at=time.time() + data.get("expires_in", 3600),
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope", ""),
        )

        logger.info(
            "Obtained new access token (scope=%s, ttl=%.0fs)",
            token.scope,
            token.ttl,
        )
        return token

    async def get_token(self) -> str:
        """Get a valid access token, refreshing if necessary (thread-safe)."""
        # Fast path: check without lock
        if self._token and not self._token.is_expired:
            return self._token.access_token

        # Slow path: acquire lock and refresh
        async with self._lock:
            # Double-check after acquiring lock
            if self._token and not self._token.is_expired:
                return self._token.access_token

            self._token = await self._fetch_token()
            return self._token.access_token

    async def get_auth_header(self) -> dict[str, str]:
        """Get Authorization header dict for HTTP requests."""
        token = await self.get_token()
        return {"Authorization": f"Bearer {token}"}

    async def close(self):
        """Clean up HTTP client."""
        if self._http_client:
            await self._http_client.aclose()


class AuthenticatedServiceClient:
    """HTTP client wrapper that automatically handles M2M authentication."""

    def __init__(
        self,
        base_url: str,
        auth: ClientCredentialsAuth,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )

    async def request(
        self,
        method: str,
        path: str,
        retry_on_401: bool = True,
        **kwargs,
    ) -> httpx.Response:
        """Make authenticated request with automatic token refresh on 401."""
        headers = kwargs.pop("headers", {})
        auth_header = await self.auth.get_auth_header()
        headers.update(auth_header)

        response = await self._client.request(
            method, path, headers=headers, **kwargs
        )

        # If 401, force token refresh and retry once
        if response.status_code == 401 and retry_on_401:
            self.auth._token = None  # Force refresh
            auth_header = await self.auth.get_auth_header()
            headers.update(auth_header)
            response = await self._client.request(
                method, path, headers=headers, **kwargs
            )

        return response

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self.request("POST", path, **kwargs)

    async def close(self):
        await self._client.aclose()
        await self.auth.close()


# Usage example
async def main():
    auth = ClientCredentialsAuth(
        token_url="https://auth.example.com/oauth/token",
        client_id="service-a-client-id",
        client_secret="service-a-secret",
        scopes=["read:users", "write:orders"],
        audience="https://api.example.com",
    )

    service_b = AuthenticatedServiceClient(
        base_url="https://api.example.com/v1",
        auth=auth,
    )

    try:
        # Automatic authentication + token caching + retry on 401
        response = await service_b.get("/users/123")
        user = response.json()

        response = await service_b.post(
            "/orders",
            json={"user_id": user["id"], "items": ["item-1", "item-2"]},
        )
        order = response.json()
        print(f"Created order: {order['id']}")
    finally:
        await service_b.close()


if __name__ == "__main__":
    asyncio.run(main())
```

Key patterns for client credentials flow:

- Cache tokens until they expire; avoid fetching a new token per request
- Use a lock to prevent thundering herd on token refresh
- Expire tokens 60 seconds early to avoid clock skew issues
- Retry on 401 with a fresh token exactly once (avoid infinite loops)
- Use HTTP Basic auth (client_id:client_secret) for token requests per RFC 6749
- Implement exponential backoff retry for transient network failures
- Close HTTP clients properly to avoid connection leaks
- Scope tokens to the minimum permissions needed'''
    ),
    (
        "security/oauth2-token-introspection",
        "How do I implement OAuth2 token introspection for a resource server to validate incoming tokens?",
        '''Token introspection (RFC 7662) allows a resource server to query the authorization server to determine whether an access token is active and retrieve its metadata. This is essential when tokens are opaque (not JWTs) or when you need real-time revocation checking.

Here is a complete implementation for a FastAPI resource server:

```python
"""OAuth2 token introspection for resource server validation."""

import time
import hashlib
import logging
from typing import Optional
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from cachetools import TTLCache
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI()
bearer_scheme = HTTPBearer()


class IntrospectionConfig(BaseModel):
    """Configuration for token introspection."""
    introspection_endpoint: str
    client_id: str
    client_secret: str
    cache_ttl: int = 300  # Cache valid tokens for 5 minutes
    cache_maxsize: int = 10000
    required_scopes: list[str] = []
    required_audience: str = ""


config = IntrospectionConfig(
    introspection_endpoint="https://auth.example.com/oauth/introspect",
    client_id="resource-server-client-id",
    client_secret="resource-server-secret",
    required_scopes=["read:data"],
    required_audience="https://api.example.com",
)


@dataclass
class TokenMetadata:
    """Parsed introspection response."""
    active: bool
    scope: str = ""
    client_id: str = ""
    username: str = ""
    token_type: str = ""
    exp: int = 0
    iat: int = 0
    sub: str = ""
    aud: str = ""
    iss: str = ""
    jti: str = ""

    @property
    def scopes(self) -> set[str]:
        return set(self.scope.split()) if self.scope else set()

    @property
    def is_expired(self) -> bool:
        return self.exp > 0 and time.time() > self.exp


class TokenIntrospector:
    """OAuth2 token introspection client with caching."""

    def __init__(self, config: IntrospectionConfig):
        self.config = config
        self._cache: TTLCache = TTLCache(
            maxsize=config.cache_maxsize,
            ttl=config.cache_ttl,
        )
        self._negative_cache: TTLCache = TTLCache(
            maxsize=1000,
            ttl=60,  # Cache invalid tokens for 1 minute only
        )
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
        return self._client

    def _token_hash(self, token: str) -> str:
        """Hash token for use as cache key (never store raw tokens)."""
        return hashlib.sha256(token.encode()).hexdigest()[:32]

    async def introspect(self, token: str) -> TokenMetadata:
        """Introspect a token, using cache when available."""
        token_key = self._token_hash(token)

        # Check positive cache
        cached = self._cache.get(token_key)
        if cached is not None:
            return cached

        # Check negative cache
        if token_key in self._negative_cache:
            return TokenMetadata(active=False)

        # Call introspection endpoint
        client = await self._get_client()
        try:
            response = await client.post(
                self.config.introspection_endpoint,
                data={
                    "token": token,
                    "token_type_hint": "access_token",
                },
                auth=(self.config.client_id, self.config.client_secret),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("Introspection endpoint returned %s: %s", e.response.status_code, e.response.text)
            raise HTTPException(status_code=502, detail="Token validation service unavailable")
        except httpx.TransportError as e:
            logger.error("Introspection endpoint unreachable: %s", e)
            raise HTTPException(status_code=502, detail="Token validation service unavailable")

        data = response.json()
        metadata = TokenMetadata(
            active=data.get("active", False),
            scope=data.get("scope", ""),
            client_id=data.get("client_id", ""),
            username=data.get("username", ""),
            token_type=data.get("token_type", ""),
            exp=data.get("exp", 0),
            iat=data.get("iat", 0),
            sub=data.get("sub", ""),
            aud=data.get("aud", ""),
            iss=data.get("iss", ""),
            jti=data.get("jti", ""),
        )

        if metadata.active:
            self._cache[token_key] = metadata
        else:
            self._negative_cache[token_key] = True

        return metadata

    async def close(self):
        if self._client:
            await self._client.aclose()


introspector = TokenIntrospector(config)


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> TokenMetadata:
    """FastAPI dependency: validate Bearer token via introspection."""
    token = credentials.credentials
    metadata = await introspector.introspect(token)

    if not metadata.active:
        raise HTTPException(
            status_code=401,
            detail="Token is inactive or expired",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Check required scopes
    if config.required_scopes:
        missing = set(config.required_scopes) - metadata.scopes
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required scopes: {', '.join(missing)}",
                headers={
                    "WWW-Authenticate": f'Bearer error="insufficient_scope", scope="{" ".join(config.required_scopes)}"'
                },
            )

    # Check audience
    if config.required_audience and metadata.aud != config.required_audience:
        raise HTTPException(
            status_code=403,
            detail="Token not intended for this resource server",
        )

    return metadata


def require_scopes(*scopes: str):
    """Factory for scope-specific dependency."""
    async def check_scopes(
        metadata: TokenMetadata = Security(require_auth),
    ) -> TokenMetadata:
        missing = set(scopes) - metadata.scopes
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Requires scopes: {', '.join(scopes)}",
            )
        return metadata
    return check_scopes


# Endpoints
@app.get("/api/data")
async def get_data(auth: TokenMetadata = Security(require_auth)):
    """Endpoint protected by introspection."""
    return {
        "data": "sensitive information",
        "accessed_by": auth.sub or auth.client_id,
    }


@app.delete("/api/data/{item_id}")
async def delete_data(
    item_id: str,
    auth: TokenMetadata = Security(require_scopes("write:data", "delete:data")),
):
    """Endpoint requiring specific scopes."""
    return {"deleted": item_id, "by": auth.sub}


@app.on_event("shutdown")
async def shutdown():
    await introspector.close()
```

Comparison of token validation strategies:

| Strategy | Latency | Revocation | Offline | Use When |
|----------|---------|------------|---------|----------|
| JWT local validation | Lowest | Delayed | Yes | High throughput, acceptable revocation delay |
| Token introspection | Medium | Real-time | No | Need real-time revocation |
| Introspection + cache | Low | Near-real-time | Partial | Balance of performance and freshness |
| JWT + introspection | Medium | Real-time | Partial | JWT for claims, introspection for revocation |

Key patterns:

- Hash tokens before using them as cache keys; never store raw tokens in caches
- Use separate TTLs for positive cache (longer) and negative cache (shorter)
- Set cache TTL based on your revocation latency requirements
- Return proper WWW-Authenticate headers per RFC 6750 on 401/403
- Handle introspection endpoint failures gracefully (fail closed)
- Use HTTP Basic auth for resource server credentials
- Check both scopes and audience for proper authorization'''
    ),
    (
        "security/oidc-implementation",
        "How do I implement OpenID Connect (OIDC) for user authentication with ID token validation?",
        '''OpenID Connect builds on OAuth2 to add a standardized identity layer. It introduces the ID Token (a JWT containing user identity claims), a UserInfo endpoint, and discovery metadata. Here is a complete OIDC relying party implementation:

```python
"""OpenID Connect relying party with discovery and ID token validation."""

import time
import secrets
import logging
from typing import Optional, Any

import httpx
import jwt  # PyJWT
from jwt import PyJWKClient
from pydantic import BaseModel, field_validator
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

app = FastAPI()
redis = Redis(host="localhost", port=6379, decode_responses=True)


class OIDCConfig(BaseModel):
    """OIDC provider configuration."""
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str] = ["openid", "profile", "email"]
    # Populated from discovery
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    jwks_uri: str = ""
    end_session_endpoint: str = ""


class IDTokenClaims(BaseModel):
    """Validated ID token claims per OIDC Core spec."""
    iss: str
    sub: str
    aud: str | list[str]
    exp: int
    iat: int
    nonce: str = ""
    auth_time: int = 0
    email: str = ""
    email_verified: bool = False
    name: str = ""
    picture: str = ""

    @field_validator("aud")
    @classmethod
    def normalize_audience(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class OIDCClient:
    """Full-featured OIDC relying party."""

    def __init__(self, issuer: str, client_id: str, client_secret: str, redirect_uri: str):
        self.config = OIDCConfig(
            issuer=issuer,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
        self._jwk_client: Optional[PyJWKClient] = None
        self._discovered = False

    async def discover(self):
        """Fetch OIDC discovery document (RFC 8414)."""
        discovery_url = f"{self.config.issuer}/.well-known/openid-configuration"

        async with httpx.AsyncClient() as client:
            response = await client.get(discovery_url)
            response.raise_for_status()
            metadata = response.json()

        self.config.authorization_endpoint = metadata["authorization_endpoint"]
        self.config.token_endpoint = metadata["token_endpoint"]
        self.config.userinfo_endpoint = metadata["userinfo_endpoint"]
        self.config.jwks_uri = metadata["jwks_uri"]
        self.config.end_session_endpoint = metadata.get("end_session_endpoint", "")

        # Initialize JWKS client for key fetching
        self._jwk_client = PyJWKClient(
            self.config.jwks_uri,
            cache_keys=True,
            lifespan=3600,  # Cache keys for 1 hour
        )
        self._discovered = True
        logger.info("OIDC discovery complete for issuer: %s", self.config.issuer)

    def _ensure_discovered(self):
        if not self._discovered:
            raise RuntimeError("Must call discover() before using OIDC client")

    def build_auth_url(self, state: str, nonce: str, prompt: str = "") -> str:
        """Build OIDC authorization URL."""
        self._ensure_discovered()
        from urllib.parse import urlencode

        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
            "nonce": nonce,
            "response_mode": "query",
        }
        if prompt:
            params["prompt"] = prompt

        return f"{self.config.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        self._ensure_discovered()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.config.redirect_uri,
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                },
            )
            response.raise_for_status()
            return response.json()

    def validate_id_token(
        self,
        id_token: str,
        expected_nonce: str,
        max_age: Optional[int] = None,
    ) -> IDTokenClaims:
        """Validate ID token per OIDC Core Section 3.1.3.7."""
        self._ensure_discovered()

        # Fetch the signing key from JWKS
        signing_key = self._jwk_client.get_signing_key_from_jwt(id_token)

        # Decode and validate
        try:
            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                issuer=self.config.issuer,
                audience=self.config.client_id,
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "require": ["iss", "sub", "aud", "exp", "iat"],
                },
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="ID token has expired")
        except jwt.InvalidAudienceError:
            raise HTTPException(status_code=401, detail="ID token audience mismatch")
        except jwt.InvalidIssuerError:
            raise HTTPException(status_code=401, detail="ID token issuer mismatch")
        except jwt.PyJWTError as e:
            raise HTTPException(status_code=401, detail=f"ID token validation failed: {e}")

        claims = IDTokenClaims(**payload)

        # Validate nonce (prevents replay attacks)
        if expected_nonce and claims.nonce != expected_nonce:
            raise HTTPException(status_code=401, detail="ID token nonce mismatch")

        # Validate auth_time if max_age was requested
        if max_age is not None and claims.auth_time:
            if (time.time() - claims.auth_time) > max_age:
                raise HTTPException(status_code=401, detail="Authentication too old")

        # iat should not be too far in the past
        if (time.time() - claims.iat) > 600:
            logger.warning("ID token iat is more than 10 minutes in the past")

        return claims

    async def get_userinfo(self, access_token: str) -> dict[str, Any]:
        """Fetch user claims from the UserInfo endpoint."""
        self._ensure_discovered()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.config.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()


# Initialize OIDC client
oidc = OIDCClient(
    issuer="https://accounts.google.com",
    client_id="your-client-id.apps.googleusercontent.com",
    client_secret="your-client-secret",
    redirect_uri="https://myapp.com/auth/oidc/callback",
)


@app.on_event("startup")
async def startup():
    await oidc.discover()


@app.get("/auth/oidc/login")
async def oidc_login(request: Request):
    """Initiate OIDC authentication."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    # Store state and nonce server-side
    session_id = secrets.token_hex(16)
    await redis.hset(f"oidc_state:{session_id}", mapping={
        "state": state,
        "nonce": nonce,
    })
    await redis.expire(f"oidc_state:{session_id}", 600)

    auth_url = oidc.build_auth_url(state=state, nonce=nonce)

    response = RedirectResponse(url=auth_url)
    response.set_cookie("oidc_session", session_id, httponly=True, secure=True, max_age=600)
    return response


@app.get("/auth/oidc/callback")
async def oidc_callback(request: Request, code: str, state: str):
    """Handle OIDC callback with ID token validation."""
    session_id = request.cookies.get("oidc_session")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session")

    stored = await redis.hgetall(f"oidc_state:{session_id}")
    if not stored or stored.get("state") != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    await redis.delete(f"oidc_state:{session_id}")

    # Exchange code for tokens
    tokens = await oidc.exchange_code(code)

    # Validate ID token
    claims = oidc.validate_id_token(
        tokens["id_token"],
        expected_nonce=stored["nonce"],
    )

    # Optionally fetch additional claims from UserInfo
    userinfo = await oidc.get_userinfo(tokens["access_token"])

    # Create application session
    app_session = secrets.token_hex(32)
    await redis.hset(f"user_session:{app_session}", mapping={
        "sub": claims.sub,
        "email": userinfo.get("email", claims.email),
        "name": userinfo.get("name", claims.name),
        "picture": userinfo.get("picture", claims.picture),
    })
    await redis.expire(f"user_session:{app_session}", 86400)

    response = RedirectResponse(url="/dashboard")
    response.set_cookie("session", app_session, httponly=True, secure=True, samesite="lax")
    response.delete_cookie("oidc_session")
    return response
```

ID token validation checklist per OIDC Core spec:

| Check | Required | Description |
|-------|----------|-------------|
| Signature | Yes | Verify with provider JWKS key |
| iss | Yes | Must match expected issuer |
| aud | Yes | Must contain your client_id |
| exp | Yes | Must not be expired |
| iat | Yes | Must be present, warn if too old |
| nonce | Yes (if sent) | Must match what you sent in auth request |
| auth_time | Conditional | Check if max_age was requested |
| azp | Conditional | Required if multiple audiences in aud |

Key patterns:

- Always use discovery (/.well-known/openid-configuration) instead of hardcoding endpoints
- Cache JWKS keys (with periodic refresh) to avoid fetching on every validation
- Validate the nonce claim to prevent ID token replay attacks
- Store nonce server-side, never in the browser
- The ID token is for authentication only; use the access token for API calls
- Fetch UserInfo for additional claims not included in the ID token
- Implement front-channel and back-channel logout when supported'''
    ),
    (
        "security/oauth2-social-login",
        "How do I implement social login with multiple providers (Google, GitHub, Microsoft) in a unified system?",
        '''Social login requires supporting multiple OAuth2/OIDC providers with different configurations, claim mappings, and quirks. Here is a provider-agnostic social login system:

```python
"""Unified social login system supporting multiple OAuth2/OIDC providers."""

import secrets
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from pydantic import BaseModel
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

app = FastAPI()
redis = Redis(host="localhost", port=6379, decode_responses=True)


class Provider(str, Enum):
    GOOGLE = "google"
    GITHUB = "github"
    MICROSOFT = "microsoft"


@dataclass
class SocialUser:
    """Normalized user profile from any provider."""
    provider: Provider
    provider_user_id: str
    email: str
    email_verified: bool
    name: str
    avatar_url: str = ""
    raw_data: dict = field(default_factory=dict)


class SocialProvider(ABC):
    """Base class for social login providers."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @property
    @abstractmethod
    def provider_name(self) -> Provider:
        ...

    @abstractmethod
    def get_auth_url(self, state: str) -> str:
        ...

    @abstractmethod
    async def exchange_code(self, code: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def get_user_info(self, tokens: dict) -> SocialUser:
        ...


class GoogleProvider(SocialProvider):
    """Google OAuth2/OIDC provider."""

    provider_name = Provider.GOOGLE
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            return resp.json()

    async def get_user_info(self, tokens: dict) -> SocialUser:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            resp.raise_for_status()
            data = resp.json()

        return SocialUser(
            provider=Provider.GOOGLE,
            provider_user_id=data["sub"],
            email=data.get("email", ""),
            email_verified=data.get("email_verified", False),
            name=data.get("name", ""),
            avatar_url=data.get("picture", ""),
            raw_data=data,
        )


class GitHubProvider(SocialProvider):
    """GitHub OAuth2 provider (not OIDC, has quirks)."""

    provider_name = Provider.GITHUB
    AUTH_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_URL = "https://api.github.com/user"
    EMAILS_URL = "https://api.github.com/user/emails"

    def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_user_info(self, tokens: dict) -> SocialUser:
        headers = {
            "Authorization": f"Bearer {tokens['access_token']}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient() as client:
            # Get user profile
            user_resp = await client.get(self.USER_URL, headers=headers)
            user_resp.raise_for_status()
            user_data = user_resp.json()

            # GitHub may not include email in profile; fetch from emails endpoint
            email = user_data.get("email", "")
            email_verified = False

            if not email:
                emails_resp = await client.get(self.EMAILS_URL, headers=headers)
                emails_resp.raise_for_status()
                emails = emails_resp.json()
                # Find primary verified email
                for e in emails:
                    if e.get("primary") and e.get("verified"):
                        email = e["email"]
                        email_verified = True
                        break
                # Fallback to any verified email
                if not email:
                    for e in emails:
                        if e.get("verified"):
                            email = e["email"]
                            email_verified = True
                            break
            else:
                email_verified = True

        return SocialUser(
            provider=Provider.GITHUB,
            provider_user_id=str(user_data["id"]),
            email=email,
            email_verified=email_verified,
            name=user_data.get("name") or user_data.get("login", ""),
            avatar_url=user_data.get("avatar_url", ""),
            raw_data=user_data,
        )


class MicrosoftProvider(SocialProvider):
    """Microsoft (Entra ID) OIDC provider."""

    provider_name = Provider.MICROSOFT
    TENANT = "common"
    AUTH_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize"
    TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    GRAPH_URL = "https://graph.microsoft.com/v1.0/me"

    def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile User.Read",
            "state": state,
            "response_mode": "query",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            return resp.json()

    async def get_user_info(self, tokens: dict) -> SocialUser:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.GRAPH_URL,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            resp.raise_for_status()
            data = resp.json()

        return SocialUser(
            provider=Provider.MICROSOFT,
            provider_user_id=data["id"],
            email=data.get("mail") or data.get("userPrincipalName", ""),
            email_verified=True,  # Microsoft validates emails
            name=data.get("displayName", ""),
            raw_data=data,
        )


class SocialLoginManager:
    """Manages multiple social login providers."""

    def __init__(self):
        self._providers: dict[Provider, SocialProvider] = {}

    def register(self, provider: SocialProvider):
        self._providers[provider.provider_name] = provider

    def get(self, name: str) -> SocialProvider:
        try:
            return self._providers[Provider(name)]
        except (ValueError, KeyError):
            raise HTTPException(status_code=400, detail=f"Unknown provider: {name}")


# Initialize providers
social = SocialLoginManager()

social.register(GoogleProvider(
    client_id="google-client-id",
    client_secret="google-client-secret",
    redirect_uri="https://myapp.com/auth/social/google/callback",
))
social.register(GitHubProvider(
    client_id="github-client-id",
    client_secret="github-client-secret",
    redirect_uri="https://myapp.com/auth/social/github/callback",
))
social.register(MicrosoftProvider(
    client_id="microsoft-client-id",
    client_secret="microsoft-client-secret",
    redirect_uri="https://myapp.com/auth/social/microsoft/callback",
))


@app.get("/auth/social/{provider_name}/login")
async def social_login(provider_name: str):
    """Initiate social login for any provider."""
    provider = social.get(provider_name)
    state = secrets.token_urlsafe(32)

    # Store state for validation
    await redis.setex(f"social_state:{state}", 600, provider_name)

    auth_url = provider.get_auth_url(state)
    return RedirectResponse(url=auth_url)


@app.get("/auth/social/{provider_name}/callback")
async def social_callback(provider_name: str, code: str, state: str):
    """Handle callback from any social provider."""
    # Verify state
    stored_provider = await redis.getdel(f"social_state:{state}")
    if stored_provider != provider_name:
        raise HTTPException(status_code=400, detail="Invalid state")

    provider = social.get(provider_name)

    # Exchange code and get user info
    tokens = await provider.exchange_code(code)
    social_user = await provider.get_user_info(tokens)

    # Link or create user in your database
    user = await find_or_create_user(social_user)

    # Create session
    session_token = secrets.token_hex(32)
    await redis.hset(f"session:{session_token}", mapping={
        "user_id": str(user["id"]),
        "provider": provider_name,
        "email": social_user.email,
    })
    await redis.expire(f"session:{session_token}", 86400)

    response = RedirectResponse(url="/dashboard")
    response.set_cookie("session", session_token, httponly=True, secure=True, samesite="lax")
    return response


async def find_or_create_user(social_user: SocialUser) -> dict:
    """Link social account to existing user or create new one.

    Account linking strategy:
    1. Check if social account already linked -> return existing user
    2. Check if email matches existing user -> link social account
    3. No match -> create new user + link social account
    """
    # In production, replace with real database queries
    # This is pseudocode showing the linking logic
    linked_user = None  # await db.social_accounts.find(provider, provider_user_id)

    if linked_user:
        return linked_user

    if social_user.email_verified:
        existing_user = None  # await db.users.find_by_email(social_user.email)
        if existing_user:
            # Link new social account to existing user
            # await db.social_accounts.create(user_id, provider, provider_user_id)
            return existing_user

    # Create new user
    new_user = {
        "id": secrets.token_hex(8),
        "email": social_user.email,
        "name": social_user.name,
        "avatar": social_user.avatar_url,
    }
    return new_user
```

Provider comparison and quirks:

| Feature | Google | GitHub | Microsoft |
|---------|--------|--------|-----------|
| Protocol | OIDC | OAuth2 only | OIDC |
| ID Token | Yes | No | Yes |
| Email in profile | Usually | Sometimes | Always |
| Separate email API | No | Yes (required) | No |
| Refresh tokens | With access_type=offline | No expiration | Yes |
| Email verification | Claim in token | Via emails API | Implicit |

Key patterns:

- Normalize user data into a common SocialUser model regardless of provider
- Handle email visibility quirks per provider (GitHub needs a separate API call)
- Always verify email ownership before linking accounts
- Support account linking: allow users to connect multiple social accounts
- Only link by email if the email is verified by the provider
- Store provider-specific user IDs for future lookups
- Use the strategy pattern to keep provider implementations interchangeable
- Store raw provider data for debugging but normalize for your application'''
    ),
    (
        "security/oauth2-token-refresh-rotation",
        "How do I implement secure token refresh with rotation and revocation for an OAuth2 authorization server?",
        '''Token refresh with rotation is a security best practice where each refresh token can only be used once, and a new refresh token is issued with each access token renewal. If a refresh token is reused, it indicates a potential token theft and all tokens in the family should be revoked.

Here is an implementation of a token refresh system with family-based rotation and automatic revocation:

```python
"""OAuth2 token refresh with rotation, family tracking, and revocation."""

import time
import uuid
import hashlib
import secrets
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone

import jwt
from pydantic import BaseModel
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Index, select, update, delete
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger(__name__)

JWT_SECRET = secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = 900       # 15 minutes
REFRESH_TOKEN_TTL = 2592000  # 30 days


class Base(DeclarativeBase):
    pass


class RefreshTokenModel(Base):
    """Refresh token with family tracking for rotation detection."""
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    client_id = Column(String(128), nullable=False)
    scope = Column(String(512), default="")
    family_id = Column(String(36), nullable=False, index=True)
    generation = Column(Integer, default=0)
    is_revoked = Column(Boolean, default=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String(45), default="")
    user_agent = Column(String(512), default="")

    __table_args__ = (
        Index("ix_refresh_family_gen", "family_id", "generation"),
    )


engine = create_async_engine("postgresql+asyncpg://localhost/myapp")
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def hash_token(token: str) -> str:
    """Hash refresh token for storage (never store raw tokens)."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(user_id: str, scope: str, client_id: str) -> str:
    """Generate a signed JWT access token."""
    now = time.time()
    payload = {
        "sub": user_id,
        "client_id": client_id,
        "scope": scope,
        "iat": int(now),
        "exp": int(now) + ACCESS_TOKEN_TTL,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


class TokenService:
    """Manages token lifecycle with rotation and revocation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_token_pair(
        self,
        user_id: str,
        client_id: str,
        scope: str,
        ip_address: str = "",
        user_agent: str = "",
        family_id: Optional[str] = None,
        generation: int = 0,
    ) -> dict:
        """Create a new access + refresh token pair."""
        # Generate tokens
        access_token = create_access_token(user_id, scope, client_id)
        refresh_token_raw = secrets.token_urlsafe(48)

        # Create new family if this is an initial login
        if family_id is None:
            family_id = str(uuid.uuid4())

        # Store hashed refresh token
        token_record = RefreshTokenModel(
            token_hash=hash_token(refresh_token_raw),
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            family_id=family_id,
            generation=generation,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TOKEN_TTL),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(token_record)
        await self.session.flush()

        logger.info(
            "Created token pair for user=%s family=%s gen=%d",
            user_id, family_id, generation,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token_raw,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL,
            "scope": scope,
        }

    async def refresh(
        self,
        refresh_token_raw: str,
        client_id: str,
        ip_address: str = "",
        user_agent: str = "",
    ) -> dict:
        """Rotate refresh token and issue new access token.

        Implements refresh token rotation with reuse detection:
        - Each refresh token can only be used once
        - If a used token is presented, revoke the entire family (theft detected)
        """
        token_hash_value = hash_token(refresh_token_raw)

        # Look up the refresh token
        result = await self.session.execute(
            select(RefreshTokenModel).where(
                RefreshTokenModel.token_hash == token_hash_value,
            )
        )
        token_record = result.scalar_one_or_none()

        if token_record is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Check if token has already been used (REUSE DETECTED = THEFT)
        if token_record.is_used:
            logger.warning(
                "REFRESH TOKEN REUSE DETECTED! family=%s gen=%d user=%s "
                "original_ip=%s reuse_ip=%s",
                token_record.family_id,
                token_record.generation,
                token_record.user_id,
                token_record.ip_address,
                ip_address,
            )
            # Revoke ALL tokens in this family
            await self._revoke_family(token_record.family_id)
            raise HTTPException(
                status_code=401,
                detail="Token reuse detected. All sessions revoked for security.",
            )

        # Check if token is revoked
        if token_record.is_revoked:
            raise HTTPException(status_code=401, detail="Refresh token has been revoked")

        # Check if token is expired
        if token_record.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Refresh token has expired")

        # Check client_id matches
        if token_record.client_id != client_id:
            raise HTTPException(status_code=401, detail="Client mismatch")

        # Mark current token as used (one-time use)
        token_record.is_used = True
        token_record.used_at = datetime.now(timezone.utc)

        # Issue new token pair with incremented generation
        new_tokens = await self.create_token_pair(
            user_id=token_record.user_id,
            client_id=token_record.client_id,
            scope=token_record.scope,
            ip_address=ip_address,
            user_agent=user_agent,
            family_id=token_record.family_id,
            generation=token_record.generation + 1,
        )

        await self.session.commit()
        return new_tokens

    async def _revoke_family(self, family_id: str):
        """Revoke all tokens in a family (used when reuse is detected)."""
        await self.session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.family_id == family_id)
            .values(
                is_revoked=True,
                revoked_at=datetime.now(timezone.utc),
            )
        )
        await self.session.commit()
        logger.info("Revoked all tokens in family=%s", family_id)

    async def revoke_user_tokens(self, user_id: str):
        """Revoke all tokens for a user (e.g., password change, account compromise)."""
        await self.session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.is_revoked == False,
            )
            .values(
                is_revoked=True,
                revoked_at=datetime.now(timezone.utc),
            )
        )
        await self.session.commit()
        logger.info("Revoked all tokens for user=%s", user_id)

    async def revoke_single(self, refresh_token_raw: str):
        """Revoke a single refresh token (logout from one device)."""
        token_hash_value = hash_token(refresh_token_raw)
        await self.session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash_value)
            .values(
                is_revoked=True,
                revoked_at=datetime.now(timezone.utc),
            )
        )
        await self.session.commit()

    async def cleanup_expired(self, batch_size: int = 1000) -> int:
        """Delete expired tokens to keep the table clean."""
        result = await self.session.execute(
            delete(RefreshTokenModel)
            .where(RefreshTokenModel.expires_at < datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        count = result.rowcount
        logger.info("Cleaned up %d expired refresh tokens", count)
        return count


async def get_token_service() -> TokenService:
    async with async_session() as session:
        yield TokenService(session)


@app.post("/oauth/token")
async def token_endpoint(
    grant_type: str,
    client_id: str,
    client_secret: str = "",
    refresh_token: str = "",
    username: str = "",
    password: str = "",
    scope: str = "",
    service: TokenService = Depends(get_token_service),
):
    """OAuth2 token endpoint supporting password and refresh_token grants."""
    if grant_type == "password":
        # Authenticate user (replace with your auth logic)
        user = await authenticate_user(username, password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return await service.create_token_pair(
            user_id=user["id"],
            client_id=client_id,
            scope=scope,
        )
    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Missing refresh_token")
        return await service.refresh(refresh_token, client_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {grant_type}")


async def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Placeholder for user authentication."""
    return {"id": "user-123"}  # Replace with real auth
```

Token rotation security model:

| Scenario | Behavior |
|----------|----------|
| Normal refresh | Old token marked used, new pair issued |
| Stolen token used first | Legitimate user\'s next refresh triggers reuse detection |
| Legitimate user refreshes first | Attacker\'s refresh attempt triggers reuse detection |
| Either reuse scenario | Entire token family revoked, all sessions invalidated |
| Token expired | Rejected, user must re-authenticate |
| Password changed | All user token families revoked |

Key patterns:

- Never store raw refresh tokens; always hash with SHA-256
- Track token families to detect and respond to token theft
- Increment generation counter to detect out-of-order usage
- On reuse detection, revoke the entire family, not just the reused token
- Log reuse events with IP addresses for security investigation
- Periodically clean up expired tokens to prevent table bloat
- Issue refresh tokens with longer TTLs than access tokens (30 days vs 15 min)
- Consider adding device fingerprinting for additional theft detection'''
    ),
]
