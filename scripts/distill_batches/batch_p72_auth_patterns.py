"""Security — authentication patterns: OAuth2, JWT, RBAC, and session management."""

PAIRS = [
    (
        "security/oauth2-implementation",
        "Show OAuth2 implementation patterns: authorization code flow, PKCE, token refresh, and scope validation.",
        '''OAuth2 implementation patterns:

```python
import secrets
import hashlib
import base64
import time
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


# --- OAuth2 Authorization Code Flow with PKCE ---

@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    redirect_uri: str
    scopes: list[str] = field(default_factory=list)


class OAuthClient:
    """OAuth2 Authorization Code flow with PKCE."""

    def __init__(self, config: OAuthConfig):
        self.config = config
        self._state_store: dict[str, dict] = {}

    def get_authorization_url(self) -> tuple[str, str]:
        """Generate authorization URL with PKCE."""
        # State: CSRF protection
        state = secrets.token_urlsafe(32)

        # PKCE: code verifier and challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()

        # Store for verification later
        self._state_store[state] = {
            "code_verifier": code_verifier,
            "created_at": time.time(),
        }

        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        url = f"{self.config.authorize_url}?{urlencode(params)}"
        return url, state

    async def exchange_code(self, code: str, state: str) -> dict:
        """Exchange authorization code for tokens."""
        # Verify state (CSRF protection)
        state_data = self._state_store.pop(state, None)
        if not state_data:
            raise ValueError("Invalid state parameter")

        # Check expiry (state valid for 10 minutes)
        if time.time() - state_data["created_at"] > 600:
            raise ValueError("Authorization request expired")

        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.config.redirect_uri,
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "code_verifier": state_data["code_verifier"],
                },
            )
            response.raise_for_status()
            return response.json()

    async def refresh_token(self, refresh_token: str) -> dict:
        """Refresh expired access token."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                },
            )
            response.raise_for_status()
            return response.json()


# --- Token management ---

@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str = "Bearer"
    scopes: list[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at - 60  # 60s buffer

    @classmethod
    def from_response(cls, data: dict) -> 'TokenPair':
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=time.time() + data.get("expires_in", 3600),
            token_type=data.get("token_type", "Bearer"),
            scopes=data.get("scope", "").split(),
        )


class TokenManager:
    """Auto-refresh tokens before expiry."""

    def __init__(self, oauth_client: OAuthClient):
        self.client = oauth_client
        self._tokens: Optional[TokenPair] = None

    async def get_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        if not self._tokens:
            raise ValueError("No tokens available. Authenticate first.")

        if self._tokens.is_expired:
            logger.info("Token expired, refreshing...")
            data = await self.client.refresh_token(
                self._tokens.refresh_token
            )
            self._tokens = TokenPair.from_response(data)

        return self._tokens.access_token

    def set_tokens(self, data: dict):
        self._tokens = TokenPair.from_response(data)


# --- Scope validation ---

def require_scopes(*required: str):
    """Decorator to validate OAuth scopes on endpoints."""
    def decorator(fn):
        import functools
        @functools.wraps(fn)
        async def wrapper(request, *args, **kwargs):
            token_scopes = request.state.scopes  # Set by auth middleware
            missing = set(required) - set(token_scopes)
            if missing:
                raise HTTPException(
                    403,
                    f"Insufficient scopes. Required: {required}, "
                    f"missing: {missing}"
                )
            return await fn(request, *args, **kwargs)
        return wrapper
    return decorator

# @app.get("/api/admin/users")
# @require_scopes("admin:read", "users:list")
# async def list_users(request): ...
```

OAuth2 patterns:
1. **PKCE** — code_verifier/challenge prevents authorization code interception
2. **State parameter** — random token prevents CSRF on callback
3. **Token auto-refresh** — refresh before expiry with 60s buffer
4. **Scope validation** — decorator checks required scopes per endpoint
5. **State expiry** — authorization requests expire after 10 minutes'''
    ),
    (
        "security/rbac-implementation",
        "Show RBAC implementation patterns: roles, permissions, hierarchies, and policy evaluation.",
        '''RBAC (Role-Based Access Control) patterns:

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any
from functools import wraps
import logging

logger = logging.getLogger(__name__)


# --- Permission definitions ---

class Permission(Enum):
    # Users
    USERS_READ = "users:read"
    USERS_CREATE = "users:create"
    USERS_UPDATE = "users:update"
    USERS_DELETE = "users:delete"

    # Orders
    ORDERS_READ = "orders:read"
    ORDERS_CREATE = "orders:create"
    ORDERS_UPDATE = "orders:update"
    ORDERS_CANCEL = "orders:cancel"

    # Admin
    ADMIN_SETTINGS = "admin:settings"
    ADMIN_AUDIT = "admin:audit"
    ADMIN_ROLES = "admin:roles"


# --- Role definitions with hierarchy ---

@dataclass
class Role:
    name: str
    permissions: set[Permission]
    parent: Optional['Role'] = None
    description: str = ""

    @property
    def all_permissions(self) -> set[Permission]:
        """Get permissions including inherited from parent roles."""
        perms = set(self.permissions)
        if self.parent:
            perms |= self.parent.all_permissions
        return perms

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.all_permissions


# Role hierarchy: admin inherits from manager, manager from user
VIEWER = Role(
    name="viewer",
    permissions={Permission.USERS_READ, Permission.ORDERS_READ},
    description="Read-only access",
)

USER = Role(
    name="user",
    permissions={Permission.ORDERS_CREATE, Permission.ORDERS_UPDATE},
    parent=VIEWER,
    description="Standard user",
)

MANAGER = Role(
    name="manager",
    permissions={
        Permission.USERS_CREATE, Permission.USERS_UPDATE,
        Permission.ORDERS_CANCEL,
    },
    parent=USER,
    description="Team manager",
)

ADMIN = Role(
    name="admin",
    permissions={
        Permission.USERS_DELETE,
        Permission.ADMIN_SETTINGS, Permission.ADMIN_AUDIT,
        Permission.ADMIN_ROLES,
    },
    parent=MANAGER,
    description="Full administrator",
)

ROLES = {r.name: r for r in [VIEWER, USER, MANAGER, ADMIN]}


# --- Policy engine ---

@dataclass
class PolicyContext:
    """Context for policy evaluation."""
    user_id: str
    user_roles: list[str]
    resource_type: str
    resource_id: Optional[str] = None
    action: str = ""
    resource_owner_id: Optional[str] = None
    attributes: dict = field(default_factory=dict)


class PolicyEngine:
    """Evaluate access policies with RBAC + ABAC."""

    def __init__(self):
        self._policies: list = []

    def add_policy(self, policy):
        self._policies.append(policy)

    def evaluate(self, context: PolicyContext) -> bool:
        """Evaluate all policies. Deny by default."""
        # Check role-based permissions first
        permission_str = f"{context.resource_type}:{context.action}"
        try:
            required_perm = Permission(permission_str)
        except ValueError:
            logger.warning("Unknown permission: %s", permission_str)
            return False

        # Check if any role grants the permission
        has_role_permission = any(
            ROLES[role].has_permission(required_perm)
            for role in context.user_roles
            if role in ROLES
        )

        if not has_role_permission:
            return False

        # Apply attribute-based policies
        for policy in self._policies:
            result = policy(context)
            if result is False:
                return False  # Explicit deny

        return True


# --- Attribute-based policies ---

def owner_only_policy(context: PolicyContext) -> Optional[bool]:
    """Only allow owners to update/delete their own resources."""
    if context.action in ("update", "delete"):
        if context.resource_owner_id:
            # Admins can override
            if "admin" in context.user_roles:
                return None  # Continue evaluation
            return context.user_id == context.resource_owner_id
    return None  # No opinion


def business_hours_policy(context: PolicyContext) -> Optional[bool]:
    """Restrict destructive actions to business hours."""
    from datetime import datetime
    if context.action == "delete":
        hour = datetime.now().hour
        if not (9 <= hour <= 17):
            logger.warning("Delete blocked outside business hours")
            return False
    return None


# --- Decorator for FastAPI ---

def require_permission(permission: Permission):
    """FastAPI dependency for permission checking."""
    def decorator(fn):
        @wraps(fn)
        async def wrapper(request, *args, **kwargs):
            user = request.state.user
            roles = [ROLES[r] for r in user.roles if r in ROLES]

            if not any(role.has_permission(permission) for role in roles):
                raise HTTPException(
                    403, f"Missing permission: {permission.value}"
                )
            return await fn(request, *args, **kwargs)
        return wrapper
    return decorator


# Usage:
# engine = PolicyEngine()
# engine.add_policy(owner_only_policy)
# engine.add_policy(business_hours_policy)
#
# can_delete = engine.evaluate(PolicyContext(
#     user_id="user123",
#     user_roles=["manager"],
#     resource_type="orders",
#     action="cancel",
#     resource_owner_id="user123",
# ))
```

RBAC patterns:
1. **Role hierarchy** — admin inherits manager inherits user permissions
2. **`all_permissions`** — traverse parent chain for inherited permissions
3. **Policy engine** — combine RBAC + attribute-based policies
4. **Owner policy** — restrict update/delete to resource owner (unless admin)
5. **Deny by default** — require explicit permission grant, any deny wins'''
    ),
]
