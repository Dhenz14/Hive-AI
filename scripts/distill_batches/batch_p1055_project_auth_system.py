PAIRS = [
    ("projects/auth-system", r'''<think>
A production auth system needs secure JWT token generation with access/refresh
token pairs. I need to implement proper key management, token rotation,
and secure storage of refresh tokens. Using HMAC-SHA256 for simplicity
but noting that RS256 is preferred in production.
</think>
Build an authentication system with JWT access tokens and refresh token flow.''', r'''import hashlib
import hmac
import json
import base64
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass
class TokenConfig:
    """Configuration for token generation."""
    secret_key: str = field(default_factory=lambda: secrets.token_hex(32))
    access_token_ttl: int = 900  # 15 minutes
    refresh_token_ttl: int = 604800  # 7 days
    issuer: str = "auth-service"
    algorithm: str = "HS256"


class TokenService:
    """Handles JWT token creation and verification."""

    def __init__(self, config: Optional[TokenConfig] = None):
        self._config = config or TokenConfig()
        self._revoked_tokens: set = set()

    def _b64_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    def _b64_decode(self, data: str) -> bytes:
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)

    def _sign(self, message: str) -> str:
        signature = hmac.new(
            self._config.secret_key.encode(),
            message.encode(),
            hashlib.sha256,
        ).digest()
        return self._b64_encode(signature)

    def create_token(self, payload: dict, ttl: int) -> str:
        """Create a signed JWT token."""
        header = {"alg": self._config.algorithm, "typ": "JWT"}
        now = int(time.time())
        claims = {
            **payload,
            "iat": now,
            "exp": now + ttl,
            "iss": self._config.issuer,
            "jti": secrets.token_hex(16),
        }
        header_b64 = self._b64_encode(json.dumps(header).encode())
        payload_b64 = self._b64_encode(json.dumps(claims).encode())
        message = f"{header_b64}.{payload_b64}"
        signature = self._sign(message)
        return f"{message}.{signature}"

    def verify_token(self, token: str) -> dict:
        """Verify and decode a JWT token."""
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Malformed token")

        header_b64, payload_b64, signature = parts
        message = f"{header_b64}.{payload_b64}"
        expected_sig = self._sign(message)

        if not hmac.compare_digest(expected_sig, signature):
            raise ValueError("Invalid signature")

        payload = json.loads(self._b64_decode(payload_b64))

        if payload.get("jti") in self._revoked_tokens:
            raise ValueError("Token has been revoked")

        if payload.get("exp", 0) < time.time():
            raise ValueError("Token has expired")

        return payload

    def create_token_pair(self, user_id: str, role: str, extra: Optional[dict] = None) -> dict:
        """Create an access/refresh token pair."""
        base_payload = {"sub": user_id, "role": role}
        if extra:
            base_payload.update(extra)

        access_token = self.create_token(
            {**base_payload, "type": "access"},
            self._config.access_token_ttl,
        )
        refresh_token = self.create_token(
            {"sub": user_id, "type": "refresh"},
            self._config.refresh_token_ttl,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": self._config.access_token_ttl,
        }

    def refresh_access_token(self, refresh_token: str, role: str) -> dict:
        """Use a refresh token to get a new access token."""
        payload = self.verify_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")

        # Revoke old refresh token (rotation)
        self.revoke_token(refresh_token)

        return self.create_token_pair(payload["sub"], role)

    def revoke_token(self, token: str) -> None:
        """Revoke a token by adding its JTI to the revocation set."""
        try:
            payload = json.loads(
                self._b64_decode(token.split(".")[1])
            )
            jti = payload.get("jti")
            if jti:
                self._revoked_tokens.add(jti)
        except Exception:
            pass

    def decode_without_verify(self, token: str) -> dict:
        """Decode token payload without verification (for debugging)."""
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Malformed token")
        return json.loads(self._b64_decode(parts[1]))
'''),
    ("projects/auth-system", r'''Implement role-based access control (RBAC) with permissions, role hierarchy, and policy enforcement.''', r'''from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set


class Permission(str, Enum):
    """System permissions."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    VIEW_REPORTS = "view_reports"
    EXPORT_DATA = "export_data"


class Role:
    """Represents a role with a set of permissions."""

    def __init__(self, name: str, permissions: Optional[Set[str]] = None, parent: Optional["Role"] = None):
        self.name = name
        self._permissions: Set[str] = permissions or set()
        self.parent = parent

    @property
    def all_permissions(self) -> Set[str]:
        """Get all permissions including inherited ones."""
        perms = set(self._permissions)
        if self.parent:
            perms.update(self.parent.all_permissions)
        return perms

    def has_permission(self, permission: str) -> bool:
        """Check if this role has a specific permission."""
        return permission in self.all_permissions

    def add_permission(self, permission: str) -> None:
        self._permissions.add(permission)

    def remove_permission(self, permission: str) -> None:
        self._permissions.discard(permission)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "permissions": sorted(self._permissions),
            "parent": self.parent.name if self.parent else None,
            "all_permissions": sorted(self.all_permissions),
        }


class RBACManager:
    """Manages roles, permissions, and access control policies."""

    def __init__(self):
        self._roles: Dict[str, Role] = {}
        self._user_roles: Dict[str, Set[str]] = {}  # user_id -> set of role names
        self._resource_policies: Dict[str, dict] = {}

    def create_role(self, name: str, permissions: Optional[Set[str]] = None, parent_name: Optional[str] = None) -> Role:
        """Create a new role, optionally inheriting from a parent role."""
        parent = self._roles.get(parent_name) if parent_name else None
        if parent_name and not parent:
            raise ValueError(f"Parent role '{parent_name}' not found")

        role = Role(name=name, permissions=permissions, parent=parent)
        self._roles[name] = role
        return role

    def delete_role(self, name: str) -> bool:
        """Delete a role. Fails if other roles inherit from it."""
        children = [r for r in self._roles.values() if r.parent and r.parent.name == name]
        if children:
            raise ValueError(f"Cannot delete role '{name}': inherited by {[c.name for c in children]}")
        return self._roles.pop(name, None) is not None

    def assign_role(self, user_id: str, role_name: str) -> None:
        """Assign a role to a user."""
        if role_name not in self._roles:
            raise ValueError(f"Role '{role_name}' not found")
        if user_id not in self._user_roles:
            self._user_roles[user_id] = set()
        self._user_roles[user_id].add(role_name)

    def revoke_role(self, user_id: str, role_name: str) -> None:
        """Revoke a role from a user."""
        if user_id in self._user_roles:
            self._user_roles[user_id].discard(role_name)

    def get_user_permissions(self, user_id: str) -> Set[str]:
        """Get all permissions for a user across all their roles."""
        permissions = set()
        role_names = self._user_roles.get(user_id, set())
        for role_name in role_names:
            role = self._roles.get(role_name)
            if role:
                permissions.update(role.all_permissions)
        return permissions

    def check_permission(self, user_id: str, permission: str) -> bool:
        """Check if a user has a specific permission."""
        return permission in self.get_user_permissions(user_id)

    def check_access(self, user_id: str, resource: str, action: str) -> bool:
        """Check if a user can perform an action on a resource."""
        policy = self._resource_policies.get(resource)
        if not policy:
            return False  # Default deny

        required_perms = policy.get(action, set())
        user_perms = self.get_user_permissions(user_id)
        return bool(required_perms & user_perms) or "admin" in user_perms

    def define_resource_policy(self, resource: str, action_permissions: Dict[str, Set[str]]) -> None:
        """Define which permissions are needed for actions on a resource."""
        self._resource_policies[resource] = action_permissions

    def setup_default_roles(self) -> None:
        """Set up a standard role hierarchy."""
        viewer = self.create_role("viewer", {Permission.READ, Permission.VIEW_REPORTS})
        editor = self.create_role("editor", {Permission.WRITE, Permission.EXPORT_DATA}, parent_name="viewer")
        moderator = self.create_role("moderator", {Permission.DELETE}, parent_name="editor")
        admin = self.create_role("admin", {Permission.ADMIN, Permission.MANAGE_USERS, Permission.MANAGE_ROLES}, parent_name="moderator")

    def get_role_hierarchy(self) -> List[dict]:
        """Get the complete role hierarchy."""
        return [role.to_dict() for role in self._roles.values()]
'''),
    ("projects/auth-system", r'''<think>
Password hashing needs to use a slow hash function (bcrypt or argon2).
I will implement a password service that handles hashing, verification,
and password strength validation. For portability, I will use hashlib
with PBKDF2 as a fallback when bcrypt is not available.
</think>
Implement secure password hashing with PBKDF2, password strength validation, and breach checking.''', r'''import hashlib
import os
import re
import secrets
import string
from typing import Optional, Tuple


class PasswordHasher:
    """Secure password hashing using PBKDF2-SHA256.

    Uses a high iteration count and random salt for each password.
    Format: algorithm$iterations$salt$hash
    """

    DEFAULT_ITERATIONS = 600000  # OWASP recommended minimum for PBKDF2-SHA256
    SALT_LENGTH = 32
    HASH_LENGTH = 32

    def hash_password(self, password: str, iterations: Optional[int] = None) -> str:
        """Hash a password with a random salt."""
        iters = iterations or self.DEFAULT_ITERATIONS
        salt = os.urandom(self.SALT_LENGTH)
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iters,
            dklen=self.HASH_LENGTH,
        )
        salt_hex = salt.hex()
        hash_hex = dk.hex()
        return f"pbkdf2_sha256${iters}${salt_hex}${hash_hex}"

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against a stored hash."""
        try:
            algorithm, iterations_str, salt_hex, hash_hex = hashed.split("$")
        except ValueError:
            return False

        if algorithm != "pbkdf2_sha256":
            return False

        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected_hash),
        )

        return secrets.compare_digest(dk, expected_hash)

    def needs_rehash(self, hashed: str) -> bool:
        """Check if a hash needs to be upgraded (e.g., more iterations)."""
        try:
            _, iterations_str, _, _ = hashed.split("$")
            return int(iterations_str) < self.DEFAULT_ITERATIONS
        except (ValueError, IndexError):
            return True


class PasswordValidator:
    """Validates password strength with configurable rules."""

    def __init__(
        self,
        min_length: int = 8,
        max_length: int = 128,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digit: bool = True,
        require_special: bool = True,
        min_unique_chars: int = 4,
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digit = require_digit
        self.require_special = require_special
        self.min_unique_chars = min_unique_chars

        # Common passwords to reject
        self._common_passwords = {
            "password", "123456", "12345678", "qwerty", "abc123",
            "password1", "admin", "letmein", "welcome", "monkey",
            "dragon", "master", "login", "princess", "football",
        }

    def validate(self, password: str) -> Tuple[bool, list]:
        """Validate a password. Returns (is_valid, list_of_errors)."""
        errors = []

        if len(password) < self.min_length:
            errors.append(f"Password must be at least {self.min_length} characters")

        if len(password) > self.max_length:
            errors.append(f"Password must be at most {self.max_length} characters")

        if self.require_uppercase and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")

        if self.require_lowercase and not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")

        if self.require_digit and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")

        if self.require_special:
            special = set(string.punctuation)
            if not any(c in special for c in password):
                errors.append("Password must contain at least one special character")

        unique_chars = len(set(password))
        if unique_chars < self.min_unique_chars:
            errors.append(f"Password must contain at least {self.min_unique_chars} unique characters")

        if password.lower() in self._common_passwords:
            errors.append("This password is too common")

        # Check for sequential characters
        if self._has_sequential(password, 4):
            errors.append("Password contains sequential characters")

        return len(errors) == 0, errors

    def _has_sequential(self, password: str, length: int) -> bool:
        """Check for sequential character runs."""
        for i in range(len(password) - length + 1):
            chunk = password[i:i + length]
            # Check ascending
            if all(ord(chunk[j + 1]) - ord(chunk[j]) == 1 for j in range(length - 1)):
                return True
            # Check descending
            if all(ord(chunk[j]) - ord(chunk[j + 1]) == 1 for j in range(length - 1)):
                return True
            # Check repeated
            if len(set(chunk)) == 1:
                return True
        return False

    def get_strength_score(self, password: str) -> int:
        """Calculate password strength on a 0-4 scale."""
        score = 0
        if len(password) >= 8:
            score += 1
        if len(password) >= 12:
            score += 1
        if re.search(r"[A-Z]", password) and re.search(r"[a-z]", password):
            score += 1
        if re.search(r"\d", password) and re.search(r"[^a-zA-Z\d]", password):
            score += 1
        return score

    def generate_password(self, length: int = 16) -> str:
        """Generate a secure random password that passes validation."""
        chars = string.ascii_letters + string.digits + "!@#$%&*"
        while True:
            password = "".join(secrets.choice(chars) for _ in range(length))
            is_valid, _ = self.validate(password)
            if is_valid:
                return password
'''),
    ("projects/auth-system", r'''Implement session management with secure session tokens, expiration, and concurrent session limits.''', r'''import hashlib
import secrets
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Session:
    """Represents an active user session."""
    session_id: str
    user_id: str
    token_hash: str  # We store hash, not the actual token
    created_at: float
    last_active: float
    expires_at: float
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True
    metadata: Dict = field(default_factory=dict)

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "expires_at": self.expires_at,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "is_active": self.is_active,
        }


class SessionManager:
    """Manages user sessions with expiration and concurrency limits."""

    def __init__(
        self,
        session_ttl: int = 86400,  # 24 hours
        max_sessions_per_user: int = 5,
        idle_timeout: int = 3600,  # 1 hour
    ):
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[str, List[str]] = {}  # user_id -> [session_ids]
        self._token_index: Dict[str, str] = {}  # token_hash -> session_id
        self._lock = threading.Lock()
        self._session_ttl = session_ttl
        self._max_sessions = max_sessions_per_user
        self._idle_timeout = idle_timeout

    def _hash_token(self, token: str) -> str:
        """Hash a session token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    def create_session(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> tuple:
        """Create a new session. Returns (session_token, session)."""
        with self._lock:
            # Enforce max sessions per user
            user_session_ids = self._user_sessions.get(user_id, [])
            active_sessions = [
                sid for sid in user_session_ids
                if sid in self._sessions and self._sessions[sid].is_active
                and not self._sessions[sid].is_expired()
            ]

            if len(active_sessions) >= self._max_sessions:
                # Evict oldest session
                oldest_sid = active_sessions[0]
                self._invalidate_session(oldest_sid)

            # Generate secure token
            token = secrets.token_urlsafe(48)
            token_hash = self._hash_token(token)
            now = time.time()

            session = Session(
                session_id=secrets.token_hex(16),
                user_id=user_id,
                token_hash=token_hash,
                created_at=now,
                last_active=now,
                expires_at=now + self._session_ttl,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata=metadata or {},
            )

            self._sessions[session.session_id] = session
            self._token_index[token_hash] = session.session_id

            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = []
            self._user_sessions[user_id].append(session.session_id)

            return token, session

    def validate_session(self, token: str) -> Optional[Session]:
        """Validate a session token and return the session if valid."""
        token_hash = self._hash_token(token)
        session_id = self._token_index.get(token_hash)
        if not session_id:
            return None

        session = self._sessions.get(session_id)
        if not session or not session.is_active:
            return None

        if session.is_expired():
            self._invalidate_session(session_id)
            return None

        # Check idle timeout
        if (time.time() - session.last_active) > self._idle_timeout:
            self._invalidate_session(session_id)
            return None

        # Update last active
        session.last_active = time.time()
        return session

    def invalidate_session(self, token: str) -> bool:
        """Invalidate a session by its token (logout)."""
        token_hash = self._hash_token(token)
        session_id = self._token_index.get(token_hash)
        if session_id:
            with self._lock:
                return self._invalidate_session(session_id)
        return False

    def _invalidate_session(self, session_id: str) -> bool:
        """Internal method to invalidate a session by ID."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.is_active = False
        self._token_index.pop(session.token_hash, None)
        return True

    def invalidate_all_user_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a user (e.g., password change)."""
        count = 0
        with self._lock:
            session_ids = self._user_sessions.get(user_id, [])
            for sid in session_ids:
                if self._invalidate_session(sid):
                    count += 1
        return count

    def get_user_sessions(self, user_id: str) -> List[dict]:
        """List all active sessions for a user."""
        session_ids = self._user_sessions.get(user_id, [])
        result = []
        for sid in session_ids:
            session = self._sessions.get(sid)
            if session and session.is_active and not session.is_expired():
                result.append(session.to_dict())
        return result

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        removed = 0
        with self._lock:
            expired_ids = [
                sid for sid, s in self._sessions.items()
                if s.is_expired() or not s.is_active
            ]
            for sid in expired_ids:
                session = self._sessions.pop(sid, None)
                if session:
                    self._token_index.pop(session.token_hash, None)
                    user_sessions = self._user_sessions.get(session.user_id, [])
                    if sid in user_sessions:
                        user_sessions.remove(sid)
                    removed += 1
        return removed

    def get_stats(self) -> dict:
        """Get session statistics."""
        active = sum(1 for s in self._sessions.values() if s.is_active and not s.is_expired())
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": active,
            "unique_users": len(self._user_sessions),
        }
'''),
    ("projects/auth-system", r'''Build the complete auth flow: user registration, login, token refresh, logout, and password reset endpoints.''', r'''import time
import secrets
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class UserRecord:
    """Stored user data."""
    user_id: str
    email: str
    username: str
    password_hash: str
    role: str = "user"
    is_active: bool = True
    email_verified: bool = False
    created_at: float = 0.0


class AuthService:
    """Complete authentication service with registration, login, and password reset."""

    def __init__(self, token_service, password_hasher, session_manager):
        self._tokens = token_service
        self._hasher = password_hasher
        self._sessions = session_manager
        self._users: Dict[str, UserRecord] = {}
        self._email_index: Dict[str, str] = {}  # email -> user_id
        self._reset_tokens: Dict[str, dict] = {}  # token -> {user_id, expires_at}
        self._verification_tokens: Dict[str, str] = {}  # token -> user_id

    def register(self, email: str, username: str, password: str) -> dict:
        """Register a new user account."""
        email_lower = email.lower()
        if email_lower in self._email_index:
            raise ValueError("Email already registered")

        # Validate password strength
        from .password import PasswordValidator
        validator = PasswordValidator()
        is_valid, errors = validator.validate(password)
        if not is_valid:
            raise ValueError(f"Password too weak: {'; '.join(errors)}")

        user_id = secrets.token_hex(16)
        password_hash = self._hasher.hash_password(password)

        user = UserRecord(
            user_id=user_id,
            email=email_lower,
            username=username,
            password_hash=password_hash,
            created_at=time.time(),
        )

        self._users[user_id] = user
        self._email_index[email_lower] = user_id

        # Generate email verification token
        verify_token = secrets.token_urlsafe(32)
        self._verification_tokens[verify_token] = user_id

        return {
            "user_id": user_id,
            "email": email_lower,
            "username": username,
            "verification_token": verify_token,
        }

    def verify_email(self, token: str) -> bool:
        """Verify a user's email address."""
        user_id = self._verification_tokens.pop(token, None)
        if not user_id:
            return False
        user = self._users.get(user_id)
        if user:
            user.email_verified = True
            return True
        return False

    def login(self, email: str, password: str, ip_address: Optional[str] = None) -> dict:
        """Authenticate a user and return tokens."""
        email_lower = email.lower()
        user_id = self._email_index.get(email_lower)
        if not user_id:
            raise ValueError("Invalid email or password")

        user = self._users[user_id]
        if not user.is_active:
            raise ValueError("Account is deactivated")

        if not self._hasher.verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")

        # Check if password needs rehashing
        if self._hasher.needs_rehash(user.password_hash):
            user.password_hash = self._hasher.hash_password(password)

        # Create session
        session_token, session = self._sessions.create_session(
            user_id=user_id,
            ip_address=ip_address,
        )

        # Create JWT tokens
        tokens = self._tokens.create_token_pair(user_id, user.role)

        return {
            "user": {
                "user_id": user_id,
                "email": user.email,
                "username": user.username,
                "role": user.role,
            },
            "tokens": tokens,
            "session_token": session_token,
        }

    def refresh_token(self, refresh_token: str) -> dict:
        """Refresh an access token using a refresh token."""
        payload = self._tokens.verify_token(refresh_token)
        user_id = payload.get("sub")
        user = self._users.get(user_id)
        if not user or not user.is_active:
            raise ValueError("User not found or deactivated")

        return self._tokens.refresh_access_token(refresh_token, user.role)

    def logout(self, session_token: str) -> bool:
        """Log out by invalidating the session."""
        return self._sessions.invalidate_session(session_token)

    def logout_all(self, user_id: str) -> int:
        """Log out all sessions for a user."""
        return self._sessions.invalidate_all_user_sessions(user_id)

    def request_password_reset(self, email: str) -> Optional[str]:
        """Generate a password reset token."""
        email_lower = email.lower()
        user_id = self._email_index.get(email_lower)
        if not user_id:
            return None  # Do not reveal if email exists

        token = secrets.token_urlsafe(32)
        self._reset_tokens[token] = {
            "user_id": user_id,
            "expires_at": time.time() + 3600,  # 1 hour
        }
        return token

    def reset_password(self, token: str, new_password: str) -> bool:
        """Reset a user's password using a reset token."""
        reset_data = self._reset_tokens.pop(token, None)
        if not reset_data:
            return False

        if time.time() > reset_data["expires_at"]:
            return False

        user = self._users.get(reset_data["user_id"])
        if not user:
            return False

        user.password_hash = self._hasher.hash_password(new_password)
        # Invalidate all sessions after password change
        self._sessions.invalidate_all_user_sessions(user.user_id)
        return True

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """Change a user's password (requires current password)."""
        user = self._users.get(user_id)
        if not user:
            return False

        if not self._hasher.verify_password(old_password, user.password_hash):
            raise ValueError("Current password is incorrect")

        user.password_hash = self._hasher.hash_password(new_password)
        self._sessions.invalidate_all_user_sessions(user_id)
        return True

    def deactivate_account(self, user_id: str) -> bool:
        """Deactivate a user account."""
        user = self._users.get(user_id)
        if not user:
            return False
        user.is_active = False
        self._sessions.invalidate_all_user_sessions(user_id)
        return True
'''),
]
