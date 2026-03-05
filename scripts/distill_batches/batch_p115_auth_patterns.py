"""Authentication — OAuth2, JWT, session management, and RBAC patterns."""

PAIRS = [
    (
        "security/jwt-auth",
        "Show JWT authentication patterns: token generation, refresh tokens, middleware, and token rotation.",
        '''JWT authentication patterns:

```python
import jwt
import secrets
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel


# --- Token configuration ---

@dataclass
class TokenConfig:
    secret_key: str
    algorithm: str = "HS256"
    access_token_ttl: timedelta = timedelta(minutes=15)
    refresh_token_ttl: timedelta = timedelta(days=30)


# --- Token service ---

class TokenService:
    def __init__(self, config: TokenConfig):
        self.config = config

    def create_access_token(self, user_id: str, roles: list[str]) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "roles": roles,
            "type": "access",
            "iat": now,
            "exp": now + self.config.access_token_ttl,
            "jti": secrets.token_urlsafe(16),  # Unique token ID
        }
        return jwt.encode(payload, self.config.secret_key, self.config.algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "type": "refresh",
            "iat": now,
            "exp": now + self.config.refresh_token_ttl,
            "jti": secrets.token_urlsafe(16),
        }
        return jwt.encode(payload, self.config.secret_key, self.config.algorithm)

    def decode_token(self, token: str) -> dict:
        try:
            return jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

    def create_token_pair(self, user_id: str, roles: list[str]) -> dict:
        return {
            "access_token": self.create_access_token(user_id, roles),
            "refresh_token": self.create_refresh_token(user_id),
            "token_type": "bearer",
            "expires_in": int(self.config.access_token_ttl.total_seconds()),
        }


# --- Token refresh with rotation ---

class RefreshTokenStore:
    """Track refresh tokens for rotation and revocation."""

    def __init__(self, redis):
        self.redis = redis

    async def store(self, user_id: str, jti: str, ttl: timedelta):
        key = f"refresh:{user_id}:{jti}"
        await self.redis.set(key, "valid", ex=int(ttl.total_seconds()))

    async def validate_and_revoke(self, user_id: str, jti: str) -> bool:
        """Use-once: validate then revoke (token rotation)."""
        key = f"refresh:{user_id}:{jti}"
        result = await self.redis.getdel(key)
        return result is not None

    async def revoke_all(self, user_id: str):
        """Revoke all refresh tokens for a user (logout everywhere)."""
        pattern = f"refresh:{user_id}:*"
        keys = []
        async for key in self.redis.scan_iter(pattern):
            keys.append(key)
        if keys:
            await self.redis.delete(*keys)


# --- FastAPI middleware ---

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token_service = TokenService(get_config())
    payload = token_service.decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    return {
        "user_id": payload["sub"],
        "roles": payload.get("roles", []),
    }


def require_role(*roles: str):
    """Dependency that checks user has at least one of the specified roles."""
    async def check_role(user: dict = Depends(get_current_user)):
        user_roles = set(user.get("roles", []))
        if not user_roles.intersection(roles):
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {', '.join(roles)}",
            )
        return user
    return check_role


# --- API endpoints ---

app = FastAPI()

@app.post("/auth/login")
async def login(email: str, password: str):
    user = await authenticate(email, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token_service = TokenService(get_config())
    tokens = token_service.create_token_pair(user.id, user.roles)

    # Store refresh token JTI
    payload = token_service.decode_token(tokens["refresh_token"])
    await refresh_store.store(user.id, payload["jti"], get_config().refresh_token_ttl)

    return tokens


@app.post("/auth/refresh")
async def refresh(refresh_token: str):
    token_service = TokenService(get_config())
    payload = token_service.decode_token(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Rotate: revoke old, issue new
    valid = await refresh_store.validate_and_revoke(payload["sub"], payload["jti"])
    if not valid:
        # Token reuse detected — revoke all tokens (possible theft)
        await refresh_store.revoke_all(payload["sub"])
        raise HTTPException(status_code=401, detail="Token reuse detected")

    user = await get_user(payload["sub"])
    tokens = token_service.create_token_pair(user.id, user.roles)

    new_payload = token_service.decode_token(tokens["refresh_token"])
    await refresh_store.store(user.id, new_payload["jti"], get_config().refresh_token_ttl)

    return tokens


@app.get("/admin/users")
async def list_users(user: dict = Depends(require_role("admin"))):
    return await get_all_users()

@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_role("admin"))):
    return await remove_user(user_id)
```

JWT auth patterns:
1. **Short-lived access tokens** — 15 min TTL, stateless verification
2. **Refresh token rotation** — each refresh token is single-use, prevents replay
3. **Token reuse detection** — if revoked token is reused, revoke all (theft signal)
4. **`require_role()`** — dependency-based RBAC that composes with `Depends()`
5. **`jti` claim** — unique token ID enables per-token revocation'''
    ),
    (
        "security/oauth2-flow",
        "Show OAuth2 implementation patterns: authorization code flow with PKCE, token exchange, and social login.",
        '''OAuth2 authorization code flow with PKCE:

```python
import secrets
import hashlib
import base64
import httpx
from urllib.parse import urlencode
from dataclasses import dataclass
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse


# --- OAuth2 provider configuration ---

@dataclass
class OAuthProvider:
    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str]


PROVIDERS = {
    "google": OAuthProvider(
        name="google",
        client_id="your-client-id",
        client_secret="your-client-secret",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
        scopes=["openid", "email", "profile"],
    ),
    "github": OAuthProvider(
        name="github",
        client_id="your-client-id",
        client_secret="your-client-secret",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        userinfo_url="https://api.github.com/user",
        scopes=["read:user", "user:email"],
    ),
}


# --- PKCE helpers ---

def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# --- OAuth2 flow ---

app = FastAPI()


@app.get("/auth/{provider}/login")
async def oauth_login(provider: str, request: Request):
    """Step 1: Redirect user to OAuth provider."""
    config = PROVIDERS.get(provider)
    if not config:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    # Generate state and PKCE
    state = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce()

    # Store in session (Redis or signed cookie)
    await store_oauth_state(state, {
        "provider": provider,
        "verifier": verifier,
        "redirect_to": request.query_params.get("redirect", "/"),
    })

    params = {
        "client_id": config.client_id,
        "redirect_uri": f"{request.base_url}auth/{provider}/callback",
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }

    return RedirectResponse(f"{config.authorize_url}?{urlencode(params)}")


@app.get("/auth/{provider}/callback")
async def oauth_callback(provider: str, code: str, state: str, request: Request):
    """Step 2: Exchange authorization code for tokens."""
    config = PROVIDERS.get(provider)
    if not config:
        raise HTTPException(status_code=400, detail="Unknown provider")

    # Validate state (CSRF protection)
    session = await get_oauth_state(state)
    if not session or session["provider"] != provider:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            config.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"{request.base_url}auth/{provider}/callback",
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "code_verifier": session["verifier"],
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        tokens = token_response.json()

    # Get user info
    async with httpx.AsyncClient() as client:
        userinfo_response = await client.get(
            config.userinfo_url,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

    # Find or create user
    user = await find_or_create_oauth_user(
        provider=provider,
        provider_id=str(userinfo.get("id") or userinfo.get("sub")),
        email=userinfo.get("email"),
        name=userinfo.get("name"),
        avatar=userinfo.get("picture") or userinfo.get("avatar_url"),
    )

    # Issue our own JWT tokens
    token_service = TokenService(get_config())
    app_tokens = token_service.create_token_pair(user.id, user.roles)

    # Redirect to frontend with token
    redirect_to = session.get("redirect_to", "/")
    return RedirectResponse(
        f"{redirect_to}?token={app_tokens['access_token']}"
    )


# --- Account linking ---

async def find_or_create_oauth_user(
    provider: str,
    provider_id: str,
    email: str | None,
    name: str | None,
    avatar: str | None,
):
    """Find existing user or create new one from OAuth profile."""
    # Check for existing OAuth link
    link = await db.get_oauth_link(provider, provider_id)
    if link:
        return await db.get_user(link.user_id)

    # Check if email matches existing account
    if email:
        existing = await db.get_user_by_email(email)
        if existing:
            # Link OAuth to existing account
            await db.create_oauth_link(existing.id, provider, provider_id)
            return existing

    # Create new user
    user = await db.create_user(email=email, name=name, avatar=avatar)
    await db.create_oauth_link(user.id, provider, provider_id)
    return user
```

OAuth2 patterns:
1. **PKCE** — `code_verifier` + `code_challenge` prevents authorization code interception
2. **`state` parameter** — CSRF protection, ties callback to original request
3. **Token exchange** — trade authorization code for access/refresh tokens server-side
4. **Account linking** — match OAuth profiles to existing users by email
5. **Issue own JWTs** — after OAuth verification, use your own token system internally'''
    ),
    (
        "security/rbac-permissions",
        "Show role-based access control patterns: permission models, policy enforcement, and attribute-based access.",
        '''RBAC and permission patterns:

```python
from enum import Flag, auto
from dataclasses import dataclass, field
from typing import Callable, Any
from functools import wraps


# --- Permission flags (bitwise combinable) ---

class Permission(Flag):
    NONE = 0
    READ = auto()       # 1
    CREATE = auto()     # 2
    UPDATE = auto()     # 4
    DELETE = auto()     # 8
    MANAGE = auto()     # 16 (manage settings, invite users)
    ADMIN = auto()      # 32

    # Composite permissions
    WRITE = CREATE | UPDATE | DELETE
    EDITOR = READ | CREATE | UPDATE
    FULL = READ | WRITE | MANAGE | ADMIN


# --- Role definitions ---

@dataclass
class Role:
    name: str
    permissions: dict[str, Permission]  # resource -> permissions
    description: str = ""

ROLES = {
    "viewer": Role(
        name="viewer",
        description="Read-only access",
        permissions={
            "projects": Permission.READ,
            "documents": Permission.READ,
            "settings": Permission.NONE,
        },
    ),
    "editor": Role(
        name="editor",
        description="Can create and edit content",
        permissions={
            "projects": Permission.READ | Permission.CREATE | Permission.UPDATE,
            "documents": Permission.EDITOR,
            "settings": Permission.READ,
        },
    ),
    "admin": Role(
        name="admin",
        description="Full access to everything",
        permissions={
            "projects": Permission.FULL,
            "documents": Permission.FULL,
            "settings": Permission.FULL,
        },
    ),
}


# --- Permission checker ---

class PermissionChecker:
    """Check permissions with role hierarchy and resource ownership."""

    def __init__(self, roles: dict[str, Role]):
        self.roles = roles

    def has_permission(
        self,
        user_role: str,
        resource: str,
        action: Permission,
    ) -> bool:
        role = self.roles.get(user_role)
        if not role:
            return False

        resource_perms = role.permissions.get(resource, Permission.NONE)
        return bool(action & resource_perms)

    def check_or_raise(self, user_role: str, resource: str, action: Permission):
        if not self.has_permission(user_role, resource, action):
            raise PermissionError(
                f"Role '{user_role}' lacks {action.name} on '{resource}'"
            )


checker = PermissionChecker(ROLES)
# checker.has_permission("editor", "documents", Permission.CREATE)  # True
# checker.has_permission("viewer", "documents", Permission.DELETE)  # False


# --- Attribute-Based Access Control (ABAC) ---

@dataclass
class AccessContext:
    user_id: str
    user_role: str
    resource_owner_id: str | None = None
    resource_type: str = ""
    ip_address: str = ""
    is_business_hours: bool = True

Policy = Callable[[AccessContext], bool]

class PolicyEngine:
    """Evaluate access policies with composable rules."""

    def __init__(self):
        self._policies: list[tuple[str, Policy]] = []

    def add_policy(self, name: str, policy: Policy) -> "PolicyEngine":
        self._policies.append((name, policy))
        return self

    def evaluate(self, context: AccessContext) -> tuple[bool, list[str]]:
        denied_by = []
        for name, policy in self._policies:
            if not policy(context):
                denied_by.append(name)

        return len(denied_by) == 0, denied_by


# Define policies
engine = PolicyEngine()
engine.add_policy(
    "role_check",
    lambda ctx: checker.has_permission(ctx.user_role, ctx.resource_type, Permission.READ),
)
engine.add_policy(
    "owner_or_admin",
    lambda ctx: ctx.user_id == ctx.resource_owner_id or ctx.user_role == "admin",
)
engine.add_policy(
    "business_hours_only",
    lambda ctx: ctx.is_business_hours or ctx.user_role == "admin",
)


# --- FastAPI integration ---

from fastapi import FastAPI, Depends, HTTPException

app = FastAPI()

def require_permission(resource: str, action: Permission):
    """FastAPI dependency for permission checking."""
    async def check(user: dict = Depends(get_current_user)):
        if not checker.has_permission(user["role"], resource, action):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions for {action.name} on {resource}",
            )
        return user
    return check


@app.get("/api/projects")
async def list_projects(
    user: dict = Depends(require_permission("projects", Permission.READ)),
):
    return await get_projects_for_user(user["user_id"])

@app.post("/api/projects")
async def create_project(
    user: dict = Depends(require_permission("projects", Permission.CREATE)),
):
    return await create_project(owner_id=user["user_id"])

@app.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str,
    user: dict = Depends(require_permission("projects", Permission.DELETE)),
):
    # Additional ownership check
    project = await get_project(project_id)
    if project.owner_id != user["user_id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not the project owner")
    return await remove_project(project_id)
```

RBAC patterns:
1. **`Flag` enum** — bitwise combinable permissions (`READ | WRITE | DELETE`)
2. **Resource-scoped roles** — different permissions per resource type
3. **`PermissionChecker`** — centralized permission evaluation with role lookup
4. **ABAC `PolicyEngine`** — attribute-based rules (ownership, time, IP) for fine-grained access
5. **`require_permission()` dependency** — composable FastAPI permission guards'''
    ),
]
