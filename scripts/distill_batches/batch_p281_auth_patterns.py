"""Authentication patterns — JWT, OAuth2, session management, RBAC."""

PAIRS = [
    (
        "architecture/jwt-auth",
        "Show JWT authentication: token generation, validation, refresh tokens, and middleware-based auth in FastAPI.",
        '''JWT authentication system:

```python
import jwt
import time
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel


class TokenPayload(BaseModel):
    sub: str          # User ID
    exp: float        # Expiration timestamp
    iat: float        # Issued at
    roles: list[str]  # User roles
    jti: str          # Unique token ID (for revocation)


class JWTAuth:
    def __init__(self, secret: str, algorithm: str = "HS256",
                 access_ttl: int = 900, refresh_ttl: int = 604800):
        self.secret = secret
        self.algorithm = algorithm
        self.access_ttl = access_ttl    # 15 minutes
        self.refresh_ttl = refresh_ttl  # 7 days
        self.revoked_tokens: set = set()  # Use Redis in production

    def create_access_token(self, user_id: str, roles: list[str]) -> str:
        now = time.time()
        payload = {
            "sub": user_id, "roles": roles,
            "exp": now + self.access_ttl, "iat": now,
            "jti": secrets.token_hex(16), "type": "access",
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        now = time.time()
        payload = {
            "sub": user_id, "exp": now + self.refresh_ttl,
            "iat": now, "jti": secrets.token_hex(16), "type": "refresh",
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def verify_token(self, token: str) -> TokenPayload:
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid token")

        if payload.get("jti") in self.revoked_tokens:
            raise HTTPException(401, "Token revoked")

        return TokenPayload(**payload)

    def revoke_token(self, jti: str):
        self.revoked_tokens.add(jti)

    def refresh(self, refresh_token: str) -> dict:
        payload = self.verify_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(400, "Not a refresh token")

        # Revoke old refresh token (rotation)
        self.revoke_token(payload.jti)

        return {
            "access_token": self.create_access_token(payload.sub, []),
            "refresh_token": self.create_refresh_token(payload.sub),
        }


# FastAPI dependency
auth = JWTAuth(secret="your-secret-key")
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    return auth.verify_token(credentials.credentials)


def require_role(*roles: str):
    async def role_checker(user: TokenPayload = Depends(get_current_user)):
        if not any(r in user.roles for r in roles):
            raise HTTPException(403, "Insufficient permissions")
        return user
    return role_checker


# Usage
app = FastAPI()

@app.get("/admin/users")
async def admin_users(user=Depends(require_role("admin"))):
    return {"users": []}

@app.get("/profile")
async def profile(user=Depends(get_current_user)):
    return {"user_id": user.sub}
```

Key patterns:
1. **Short-lived access tokens** — 15 min TTL; limits window of compromise
2. **Refresh token rotation** — old refresh token revoked when new one issued
3. **JTI for revocation** — unique token ID enables individual token revocation
4. **Role-based middleware** — `require_role("admin")` as FastAPI dependency
5. **Token type field** — distinguish access vs refresh; prevent misuse'''
    ),
    (
        "architecture/rbac",
        "Show Role-Based Access Control: permission hierarchies, resource-based authorization, and policy evaluation.",
        '''RBAC with resource-based authorization:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Permission(Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"


@dataclass
class Role:
    name: str
    permissions: set[Permission]
    inherits_from: list[str] = field(default_factory=list)


@dataclass
class ResourcePolicy:
    resource_type: str
    resource_id: str
    role: str
    user_id: Optional[str] = None  # None = applies to all with role


class AuthorizationEngine:
    """Evaluate access policies for resource-based authorization."""

    def __init__(self):
        self.roles: dict[str, Role] = {}
        self.user_roles: dict[str, set[str]] = {}  # user_id -> role names
        self.policies: list[ResourcePolicy] = []

    def define_role(self, role: Role):
        self.roles[role.name] = role

    def assign_role(self, user_id: str, role_name: str):
        self.user_roles.setdefault(user_id, set()).add(role_name)

    def add_policy(self, policy: ResourcePolicy):
        self.policies.append(policy)

    def get_effective_permissions(self, role_name: str) -> set[Permission]:
        """Resolve permissions including inherited roles."""
        role = self.roles.get(role_name)
        if not role:
            return set()

        permissions = set(role.permissions)
        for parent_name in role.inherits_from:
            permissions |= self.get_effective_permissions(parent_name)
        return permissions

    def check_access(self, user_id: str, resource_type: str,
                      resource_id: str, permission: Permission) -> bool:
        """Check if user has permission on specific resource."""
        user_role_names = self.user_roles.get(user_id, set())

        for role_name in user_role_names:
            perms = self.get_effective_permissions(role_name)
            if Permission.ADMIN in perms:
                return True  # Admin has all permissions
            if permission in perms:
                # Check resource-specific policies
                if self._has_resource_access(user_id, role_name,
                                               resource_type, resource_id):
                    return True
        return False

    def _has_resource_access(self, user_id: str, role_name: str,
                               resource_type: str, resource_id: str) -> bool:
        for policy in self.policies:
            if policy.resource_type != resource_type:
                continue
            if policy.resource_id not in (resource_id, "*"):
                continue
            if policy.role != role_name:
                continue
            if policy.user_id and policy.user_id != user_id:
                continue
            return True
        # No specific policy = role-level permission applies
        return True


# Setup example
engine = AuthorizationEngine()
engine.define_role(Role("viewer", {Permission.READ}))
engine.define_role(Role("editor", {Permission.READ, Permission.WRITE},
                         inherits_from=["viewer"]))
engine.define_role(Role("admin", {Permission.ADMIN}))

engine.assign_role("user-1", "editor")
engine.add_policy(ResourcePolicy("project", "proj-1", "editor", "user-1"))

# user-1 can write to proj-1
assert engine.check_access("user-1", "project", "proj-1", Permission.WRITE)
# user-1 cannot delete (editor doesn't have delete)
assert not engine.check_access("user-1", "project", "proj-1", Permission.DELETE)
```

Key patterns:
1. **Role hierarchy** — editor inherits from viewer; avoid permission duplication
2. **Resource-level policies** — permissions bound to specific resources, not just global
3. **Admin shortcut** — ADMIN permission bypasses all checks; single super-role
4. **Wildcard resources** — `resource_id="*"` grants access to all instances of a type
5. **Effective permissions** — recursively resolve inherited roles for complete permission set'''
    ),
]
