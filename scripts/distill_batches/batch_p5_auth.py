"""
Batch P5 -- Authentication & Authorization: OAuth 2.0/OIDC, JWT security,
RBAC/ABAC, passkeys/WebAuthn, API key management.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. OAuth 2.0 and OIDC Deep Dive ---
    (
        "oauth2_oidc_authorization_code_pkce_python",
        "Explain OAuth 2.0 and OpenID Connect in depth -- the authorization code flow with PKCE, "
        "token refresh mechanics, ID token validation, state and nonce parameter security, "
        "and how to implement a secure OAuth 2.0 client in Python with proper CSRF protection "
        "and token storage. Include complete production-ready code with type hints.",
        r"""
# OAuth 2.0 and OpenID Connect: Secure Authorization Code Flow with PKCE

## Understanding the Protocol Stack

OAuth 2.0 is an **authorization** framework -- it lets a user grant a third-party application limited access to a resource server without sharing their password. OpenID Connect (OIDC) is an **authentication** layer built on top of OAuth 2.0 that adds identity verification through ID tokens. A common mistake is conflating the two: OAuth 2.0 alone tells you *what a user can access*, while OIDC tells you *who the user is*.

The **authorization code flow with PKCE** (Proof Key for Code Exchange) is the recommended grant type for all clients -- public and confidential alike. The original authorization code flow relied on a `client_secret` to exchange the authorization code for tokens, but this is insufficient for public clients (SPAs, mobile apps) where the secret cannot be kept confidential. PKCE eliminates this vulnerability by binding the authorization request to the token exchange through a cryptographic challenge, therefore making authorization code interception attacks useless even without a client secret.

**Best practice**: As of OAuth 2.1 (draft), PKCE is required for **all** authorization code grants, not just public clients. This is because even confidential clients benefit from the additional protection against authorization code injection attacks.

## The PKCE Flow in Detail

The flow proceeds through these steps:

1. The client generates a random `code_verifier` (43-128 characters, URL-safe)
2. The client computes `code_challenge = BASE64URL(SHA256(code_verifier))`
3. The client redirects the user to the authorization endpoint with `code_challenge` and `code_challenge_method=S256`
4. The user authenticates and consents
5. The authorization server redirects back with an `authorization_code`
6. The client exchanges the code + `code_verifier` at the token endpoint
7. The server verifies `SHA256(code_verifier) == code_challenge` before issuing tokens

## Core Implementation: OAuth 2.0 Client with PKCE

```python
import hashlib
import secrets
import base64
import time
import json
from urllib.parse import urlencode, urlparse, parse_qs
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
import httpx
from cryptography.fernet import Fernet

# Configuration for the OAuth 2.0 / OIDC client
@dataclass(frozen=True)
class OAuthConfig:
    # Identity provider endpoints
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    jwks_uri: str
    issuer: str

    # Client registration details
    client_id: str
    client_secret: Optional[str]  # None for public clients
    redirect_uri: str
    scopes: Tuple[str, ...] = ("openid", "profile", "email")

    # Security settings
    token_encryption_key: bytes = field(default_factory=lambda: Fernet.generate_key())


@dataclass
class PKCEChallenge:
    # PKCE parameters bound to a single authorization request
    code_verifier: str
    code_challenge: str
    code_challenge_method: str = "S256"


@dataclass
class TokenSet:
    # Tokens returned from the token endpoint
    access_token: str
    token_type: str
    expires_at: float
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    scope: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        # Add a 30-second buffer to account for clock skew and network latency
        return time.time() >= (self.expires_at - 30)


class PKCEGenerator:
    # Generates cryptographically secure PKCE challenges

    @staticmethod
    def generate(length: int = 64) -> PKCEChallenge:
        # code_verifier: 43-128 unreserved characters (RFC 7636 Section 4.1)
        if not (43 <= length <= 128):
            raise ValueError("code_verifier length must be between 43 and 128")
        code_verifier = secrets.token_urlsafe(length)[:length]

        # code_challenge: BASE64URL(SHA256(code_verifier))
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        return PKCEChallenge(
            code_verifier=code_verifier,
            code_challenge=code_challenge,
        )
```

The `PKCEGenerator` creates a high-entropy verifier using `secrets.token_urlsafe`, which is backed by the OS CSPRNG. A **pitfall** here is using `random.random()` or similar non-cryptographic PRNGs -- an attacker who can predict the verifier can bypass PKCE entirely.

## State and Nonce Management for CSRF Protection

```python
import hmac
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
import time
import secrets

@dataclass
class AuthorizationState:
    # Binds an authorization request to the session that initiated it
    state: str
    nonce: str
    pkce: PKCEChallenge
    created_at: float
    redirect_target: str  # where to send the user after authentication

    def is_valid(self, max_age_seconds: int = 600) -> bool:
        # States older than 10 minutes are rejected to prevent replay
        return (time.time() - self.created_at) < max_age_seconds


class StateStore:
    # In-memory state store; use Redis or a database in production
    # because server restarts would lose all pending authorization flows

    def __init__(self, max_pending: int = 1000) -> None:
        self._states: Dict[str, AuthorizationState] = {}
        self._max_pending = max_pending

    def create(self, redirect_target: str = "/") -> AuthorizationState:
        # Evict expired states to prevent memory exhaustion
        self._evict_expired()
        if len(self._states) >= self._max_pending:
            raise RuntimeError("Too many pending authorization flows")

        state_value = secrets.token_urlsafe(32)
        nonce_value = secrets.token_urlsafe(32)
        pkce = PKCEGenerator.generate()

        auth_state = AuthorizationState(
            state=state_value,
            nonce=nonce_value,
            pkce=pkce,
            created_at=time.time(),
            redirect_target=redirect_target,
        )
        self._states[state_value] = auth_state
        return auth_state

    def consume(self, state_value: str) -> Optional[AuthorizationState]:
        # Pop-and-validate: each state can only be used once
        auth_state = self._states.pop(state_value, None)
        if auth_state is None:
            return None
        if not auth_state.is_valid():
            return None  # expired
        return auth_state

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._states.items() if not v.is_valid()]
        for k in expired:
            del self._states[k]
```

The `state` parameter prevents **CSRF attacks**: an attacker cannot craft a redirect URI that would bind their authorization code to the victim's session because the state is unpredictable and validated on callback. The `nonce` parameter prevents **replay attacks** on ID tokens: the nonce is embedded in the ID token by the authorization server, and the client verifies it matches what was sent in the authorization request.

## Token Exchange and ID Token Validation

```python
import jwt  # PyJWT
from jwt import PyJWKClient
from typing import Optional, Dict, Any

class OAuthClient:
    # Full OAuth 2.0 / OIDC client with PKCE, state, and nonce validation

    def __init__(self, config: OAuthConfig) -> None:
        self._config = config
        self._state_store = StateStore()
        self._http = httpx.AsyncClient(timeout=10.0)
        self._jwks_client = PyJWKClient(config.jwks_uri, cache_keys=True)

    def build_authorization_url(self, redirect_target: str = "/") -> Tuple[str, str]:
        # Returns (authorization_url, state) -- store state in session cookie
        auth_state = self._state_store.create(redirect_target)
        params = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "scope": " ".join(self._config.scopes),
            "state": auth_state.state,
            "nonce": auth_state.nonce,
            "code_challenge": auth_state.pkce.code_challenge,
            "code_challenge_method": auth_state.pkce.code_challenge_method,
        }
        url = f"{self._config.authorization_endpoint}?{urlencode(params)}"
        return url, auth_state.state

    async def handle_callback(
        self, code: str, state: str, expected_state: str
    ) -> Tuple[TokenSet, Dict[str, Any]]:
        # Validate state to prevent CSRF
        if not hmac.compare_digest(state, expected_state):
            raise SecurityError("State mismatch -- possible CSRF attack")

        auth_state = self._state_store.consume(state)
        if auth_state is None:
            raise SecurityError("Unknown or expired state parameter")

        # Exchange authorization code for tokens
        token_data = await self._exchange_code(code, auth_state.pkce.code_verifier)
        token_set = self._parse_token_response(token_data)

        # Validate ID token if present (required for OIDC)
        id_claims: Dict[str, Any] = {}
        if token_set.id_token:
            id_claims = self._validate_id_token(token_set.id_token, auth_state.nonce)

        return token_set, id_claims

    async def _exchange_code(self, code: str, code_verifier: str) -> Dict[str, Any]:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._config.redirect_uri,
            "client_id": self._config.client_id,
            "code_verifier": code_verifier,
        }
        if self._config.client_secret:
            payload["client_secret"] = self._config.client_secret

        response = await self._http.post(
            self._config.token_endpoint,
            data=payload,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return response.json()

    async def refresh_tokens(self, refresh_token: str) -> TokenSet:
        # Refresh token rotation: the server should issue a new refresh token
        # and invalidate the old one on each use
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._config.client_id,
        }
        if self._config.client_secret:
            payload["client_secret"] = self._config.client_secret

        response = await self._http.post(self._config.token_endpoint, data=payload)
        response.raise_for_status()
        return self._parse_token_response(response.json())

    def _validate_id_token(self, id_token: str, expected_nonce: str) -> Dict[str, Any]:
        # Fetch the signing key from the JWKS endpoint (cached)
        signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=self._config.client_id,
            issuer=self._config.issuer,
            options={"require": ["exp", "iat", "nonce", "sub"]},
        )
        # Validate nonce to prevent replay attacks
        if not hmac.compare_digest(claims.get("nonce", ""), expected_nonce):
            raise SecurityError("Nonce mismatch -- possible ID token replay")
        return claims

    @staticmethod
    def _parse_token_response(data: Dict[str, Any]) -> TokenSet:
        return TokenSet(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_at=time.time() + data.get("expires_in", 3600),
            refresh_token=data.get("refresh_token"),
            id_token=data.get("id_token"),
            scope=data.get("scope"),
        )


class SecurityError(Exception):
    pass
```

**However**, there is an important trade-off with ID token validation: verifying the signature requires fetching the JWKS (JSON Web Key Set) from the authorization server. You should cache these keys aggressively (PyJWT's `PyJWKClient` does this by default), but you must also handle key rotation -- if verification fails with a cached key, refetch the JWKS once before giving up.

## Summary and Key Takeaways

- **Always use PKCE** for authorization code flow, regardless of client type -- it is mandatory in OAuth 2.1
- **State prevents CSRF**, **nonce prevents replay** -- both are essential and must be cryptographically random
- **Consume state values exactly once** (pop-and-validate) to prevent reuse attacks
- **Use constant-time comparison** (`hmac.compare_digest`) for all security-sensitive string comparisons to prevent timing attacks
- **Validate ID tokens fully**: check signature, issuer, audience, expiration, and nonce
- **Refresh token rotation** means each refresh request returns a new refresh token and invalidates the old one -- detect reuse as a signal of token theft
- **Never store tokens in localStorage** for browser clients; use HttpOnly, Secure, SameSite cookies or a backend-for-frontend (BFF) pattern instead
- The **best practice** is to keep access token lifetimes short (5-15 minutes) and rely on refresh tokens for session continuity
"""
    ),

    # --- 2. JWT Security Best Practices ---
    (
        "jwt_security_signing_algorithms_rotation_python",
        "Cover JWT security best practices in depth -- token structure and claims, signing "
        "algorithm selection between RS256, ES256, and EdDSA, refresh token rotation with "
        "reuse detection, token revocation strategies, and a complete Python implementation "
        "for issuing and verifying JWTs securely with proper key management and type hints.",
        r"""
# JWT Security Best Practices: Signing, Rotation, and Revocation

## JWT Structure and Security Implications

A JSON Web Token consists of three Base64URL-encoded parts separated by dots: **header.payload.signature**. The header specifies the signing algorithm (`alg`) and key identifier (`kid`). The payload contains claims -- registered claims like `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, and custom claims for your application. The signature binds the header and payload together cryptographically.

**Common mistake**: Treating JWTs as encrypted. JWTs are **signed**, not encrypted -- anyone can decode the header and payload. If you need confidentiality, use JWE (JSON Web Encryption) or avoid putting sensitive data in the token entirely. Because the payload is merely Base64URL-encoded, never include passwords, SSNs, or other secrets in JWT claims.

A critical **pitfall** is the `alg: "none"` attack. Early JWT libraries accepted tokens with `alg` set to `"none"`, meaning no signature verification was performed. Modern libraries reject this by default, but you should **always** specify an explicit `algorithms` list when verifying -- never let the token tell you which algorithm to use.

## Signing Algorithm Selection: RS256 vs ES256 vs EdDSA

The choice of signing algorithm involves trade-offs between security, performance, and key size:

| Algorithm | Type | Key Size | Signature Size | Verify Speed | Best For |
|-----------|------|----------|----------------|--------------|----------|
| RS256 | RSA | 2048-4096 bit | 256 bytes | Fast | Legacy compatibility |
| ES256 | ECDSA P-256 | 256 bit | 64 bytes | Fast | Compact tokens, broad support |
| EdDSA (Ed25519) | EdDSA | 256 bit | 64 bytes | Fastest | Modern systems, best security margin |

**Therefore**, for new systems, **EdDSA with Ed25519** is the best practice. It offers the highest security margin, deterministic signatures (no nonce-related vulnerabilities like ECDSA), the fastest verification, and compact keys. However, if you need broad compatibility with older libraries and services, **ES256** is the pragmatic choice -- it is widely supported and offers excellent performance with small token sizes.

RS256 remains relevant because many identity providers (Auth0, Azure AD, Okta) default to it, and its verification is fast even though signing is slower. The **trade-off** is that RS256 produces larger tokens (adding ~170 bytes over ES256) and requires larger keys.

## Complete JWT Service Implementation

```python
import time
import uuid
import hashlib
import secrets
from typing import Optional, Dict, Any, Set, List
from dataclasses import dataclass, field
from enum import Enum
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    PrivateFormat,
    NoEncryption,
)
import jwt  # PyJWT


class SigningAlgorithm(Enum):
    RS256 = "RS256"
    ES256 = "ES256"
    EdDSA = "EdDSA"


@dataclass
class KeyPair:
    # Represents a signing key with metadata for rotation
    kid: str  # Key ID -- included in JWT header for key selection
    algorithm: SigningAlgorithm
    private_key: Any  # cryptography private key object
    public_key: Any  # cryptography public key object
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at


class KeyManager:
    # Manages signing keys with support for rotation
    # In production, keys should be stored in a HSM or vault (e.g., AWS KMS, HashiCorp Vault)

    def __init__(self) -> None:
        self._keys: Dict[str, KeyPair] = {}
        self._active_kid: Optional[str] = None

    def generate_ed25519_key(self, ttl_seconds: int = 86400 * 90) -> KeyPair:
        # Generate a new Ed25519 key pair (90-day default rotation)
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        kid = secrets.token_urlsafe(16)

        key_pair = KeyPair(
            kid=kid,
            algorithm=SigningAlgorithm.EdDSA,
            private_key=private_key,
            public_key=public_key,
            expires_at=time.time() + ttl_seconds,
        )
        self._keys[kid] = key_pair
        self._active_kid = kid
        return key_pair

    def get_signing_key(self) -> KeyPair:
        # Returns the current active key; rotates if expired
        if self._active_kid is None or self._keys[self._active_kid].is_expired:
            self.generate_ed25519_key()
        return self._keys[self._active_kid]  # type: ignore[index]

    def get_verification_key(self, kid: str) -> Optional[KeyPair]:
        # Allows verification with any non-expired key (supports graceful rotation)
        return self._keys.get(kid)

    def get_jwks(self) -> Dict[str, List[Dict[str, str]]]:
        # Export public keys in JWKS format for external verification
        keys = []
        for kp in self._keys.values():
            if not kp.is_expired:
                pub_bytes = kp.public_key.public_bytes(
                    Encoding.Raw, PublicFormat.Raw
                )
                import base64
                keys.append({
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "kid": kp.kid,
                    "x": base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode(),
                    "use": "sig",
                    "alg": "EdDSA",
                })
        return {"keys": keys}
```

## Refresh Token Rotation with Reuse Detection

```python
@dataclass
class RefreshTokenRecord:
    # Database record for a refresh token
    token_hash: str  # SHA-256 hash -- never store the raw token
    user_id: str
    token_family: str  # groups all tokens in a rotation chain
    created_at: float
    expires_at: float
    is_used: bool = False
    replaced_by: Optional[str] = None  # hash of the next token in the chain


class TokenService:
    # Issues, verifies, and rotates JWTs with refresh token reuse detection

    def __init__(self, key_manager: KeyManager, issuer: str, audience: str) -> None:
        self._key_manager = key_manager
        self._issuer = issuer
        self._audience = audience
        # In production, use a database (PostgreSQL, Redis) instead of in-memory
        self._refresh_tokens: Dict[str, RefreshTokenRecord] = {}
        self._revoked_families: Set[str] = set()
        self._revoked_jtis: Set[str] = set()  # for individual access token revocation

    def issue_access_token(
        self, subject: str, claims: Optional[Dict[str, Any]] = None, ttl: int = 900
    ) -> str:
        # Short-lived access token (15 minutes default)
        key_pair = self._key_manager.get_signing_key()
        now = time.time()
        payload = {
            "iss": self._issuer,
            "sub": subject,
            "aud": self._audience,
            "iat": int(now),
            "exp": int(now + ttl),
            "jti": str(uuid.uuid4()),  # unique token ID for revocation
            **(claims or {}),
        }
        return jwt.encode(
            payload,
            key_pair.private_key,
            algorithm=key_pair.algorithm.value,
            headers={"kid": key_pair.kid},
        )

    def issue_refresh_token(self, user_id: str, family: Optional[str] = None) -> str:
        # Long-lived refresh token (7 days); starts a new family if none given
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        token_family = family or str(uuid.uuid4())

        record = RefreshTokenRecord(
            token_hash=token_hash,
            user_id=user_id,
            token_family=token_family,
            created_at=time.time(),
            expires_at=time.time() + 86400 * 7,
        )
        self._refresh_tokens[token_hash] = record
        return raw_token

    def rotate_refresh_token(self, raw_refresh_token: str) -> tuple[str, str]:
        # Returns (new_access_token, new_refresh_token)
        # Implements rotation with reuse detection (RFC best practice)
        token_hash = hashlib.sha256(raw_refresh_token.encode()).hexdigest()
        record = self._refresh_tokens.get(token_hash)

        if record is None:
            raise InvalidTokenError("Refresh token not found")

        # REUSE DETECTION: if this token was already used, the entire family
        # is compromised -- an attacker replayed a stolen token
        if record.is_used:
            self._revoke_family(record.token_family)
            raise TokenReuseError(
                f"Refresh token reuse detected for family {record.token_family}. "
                "All tokens in the family have been revoked."
            )

        if record.token_family in self._revoked_families:
            raise InvalidTokenError("Token family has been revoked")

        if time.time() >= record.expires_at:
            raise InvalidTokenError("Refresh token expired")

        # Mark old token as used and issue new pair
        record.is_used = True
        new_refresh = self.issue_refresh_token(record.user_id, record.token_family)
        new_refresh_hash = hashlib.sha256(new_refresh.encode()).hexdigest()
        record.replaced_by = new_refresh_hash

        new_access = self.issue_access_token(record.user_id)
        return new_access, new_refresh

    def verify_access_token(self, token: str) -> Dict[str, Any]:
        # Decode and verify; check revocation list
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise InvalidTokenError("Missing kid in token header")

        key_pair = self._key_manager.get_verification_key(kid)
        if key_pair is None:
            raise InvalidTokenError(f"Unknown signing key: {kid}")

        claims = jwt.decode(
            token,
            key_pair.public_key,
            algorithms=[key_pair.algorithm.value],
            audience=self._audience,
            issuer=self._issuer,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )

        if claims["jti"] in self._revoked_jtis:
            raise InvalidTokenError("Token has been revoked")

        return claims

    def _revoke_family(self, family: str) -> None:
        self._revoked_families.add(family)


class InvalidTokenError(Exception):
    pass

class TokenReuseError(Exception):
    pass
```

The refresh token rotation pattern is essential **because** it limits the damage of a stolen refresh token. When the legitimate user and the attacker both try to use the same refresh token, one of them will trigger the reuse detection, revoking the entire family and forcing re-authentication.

## Token Revocation Strategies

There are several approaches to revoking JWTs, each with trade-offs:

1. **Short-lived access tokens + refresh token rotation** (recommended): Access tokens expire in 5-15 minutes; revoke the refresh token to prevent new access tokens. The trade-off is that access tokens remain valid until expiry.
2. **Token blacklist (JTI-based)**: Store revoked `jti` values in a fast store (Redis). Every verification checks the blacklist. This adds latency but provides immediate revocation.
3. **Token versioning**: Store a `token_version` per user; increment it on logout/password change. Tokens with an older version are rejected.

**Best practice**: Combine short-lived access tokens (15 minutes) with refresh token rotation and a small JTI blacklist for emergency revocation (admin forcing logout, detected compromise).

## Summary and Key Takeaways

- **Never use `alg: "none"`** and always specify allowed algorithms explicitly in verification
- **EdDSA (Ed25519)** is the best modern signing algorithm: deterministic, fast, compact, and high security margin
- **Hash refresh tokens** with SHA-256 before storage -- a database breach should not yield usable tokens
- **Refresh token rotation with reuse detection** catches token theft: if a used token is replayed, revoke the entire family
- **Keep access tokens short-lived** (5-15 minutes) so revocation is rarely needed
- **Include `jti` in every token** to enable targeted revocation when necessary
- **Key rotation** with `kid` headers allows graceful rollover -- old tokens remain verifiable with the old key while new tokens use the new key
- **Never store JWTs in localStorage** in browser contexts; prefer HttpOnly cookies to prevent XSS-based token theft
"""
    ),

    # --- 3. RBAC and ABAC Authorization ---
    (
        "rbac_abac_authorization_middleware_policy_engine_python",
        "Explain RBAC and ABAC authorization models in depth -- role hierarchies, attribute-based "
        "policies, policy evaluation engines, combining both models, and implement a complete "
        "authorization middleware in Python with role inheritance, resource-level permissions, "
        "audit logging, and policy decision caching with proper type hints throughout.",
        r"""
# RBAC and ABAC Authorization: Building a Complete Policy Engine

## Authorization Models: From Simple to Expressive

Authorization answers the question: "Is this **subject** allowed to perform this **action** on this **resource**?" The answer depends on which authorization model you use, and each model makes different trade-offs between simplicity and expressiveness.

**Role-Based Access Control (RBAC)** assigns permissions to roles, and roles to users. It is simple to understand and audit: "Editors can update articles." However, RBAC struggles with context-dependent rules -- it cannot express "Editors can update articles, but only in their department, and only during business hours."

**Attribute-Based Access Control (ABAC)** evaluates policies based on attributes of the subject, resource, action, and environment. It is maximally expressive but harder to audit and reason about because policies can reference arbitrary attributes.

**Best practice**: Use RBAC as the foundation for coarse-grained access control, then layer ABAC policies on top for fine-grained, context-dependent decisions. This gives you the auditability of roles with the expressiveness of attributes.

## Core Domain Model

```python
from __future__ import annotations
import time
import logging
import functools
from enum import Enum, auto
from typing import Optional, Dict, Any, Set, FrozenSet, Callable, List, TypeVar
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

logger = logging.getLogger("authorization")

# Actions follow a resource:verb convention for clarity
class Action(Enum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ADMIN = "admin"  # superuser action -- implies all others


@dataclass(frozen=True)
class Permission:
    # A permission is a (resource_type, action) pair
    resource_type: str  # e.g., "article", "user", "billing"
    action: Action

    def __str__(self) -> str:
        return f"{self.resource_type}:{self.action.value}"


@dataclass
class Role:
    # A role with direct permissions and parent roles for inheritance
    name: str
    permissions: Set[Permission] = field(default_factory=set)
    parents: Set[str] = field(default_factory=set)  # parent role names
    description: str = ""

    def add_permission(self, resource_type: str, action: Action) -> None:
        self.permissions.add(Permission(resource_type, action))


class RoleRegistry:
    # Manages roles and resolves inheritance hierarchies
    # Supports DAG-based role inheritance (not just trees)

    def __init__(self) -> None:
        self._roles: Dict[str, Role] = {}

    def register(self, role: Role) -> None:
        # Validate that all parent roles exist to prevent dangling references
        for parent_name in role.parents:
            if parent_name not in self._roles:
                raise ValueError(
                    f"Parent role '{parent_name}' not registered. "
                    f"Register parent roles before children."
                )
        self._roles[role.name] = role

    def get_effective_permissions(self, role_name: str) -> FrozenSet[Permission]:
        # Resolves all permissions including those inherited from parent roles
        # Uses BFS to handle diamond inheritance correctly
        if role_name not in self._roles:
            return frozenset()

        all_permissions: Set[Permission] = set()
        visited: Set[str] = set()
        queue: List[str] = [role_name]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            role = self._roles.get(current)
            if role is None:
                continue
            all_permissions.update(role.permissions)
            queue.extend(role.parents)

        return frozenset(all_permissions)

    def get_role(self, name: str) -> Optional[Role]:
        return self._roles.get(name)
```

Role hierarchies form a **directed acyclic graph** (DAG), not a tree. This is important because a role like `department_admin` might inherit from both `editor` and `user_manager` -- diamond inheritance. The BFS traversal handles this correctly by tracking visited roles.

## ABAC Policy Engine

```python
@dataclass(frozen=True)
class PolicyContext:
    # All attributes available for policy evaluation
    subject_id: str
    subject_roles: FrozenSet[str]
    subject_attrs: Dict[str, Any]  # department, clearance_level, etc.
    resource_type: str
    resource_id: Optional[str]
    resource_attrs: Dict[str, Any]  # owner_id, department, classification, etc.
    action: Action
    environment: Dict[str, Any]  # ip_address, time_of_day, is_vpn, etc.


class PolicyEffect(Enum):
    ALLOW = auto()
    DENY = auto()
    ABSTAIN = auto()  # policy does not apply to this request


@dataclass
class PolicyResult:
    effect: PolicyEffect
    policy_name: str
    reason: str


class Policy(ABC):
    # Base class for ABAC policies
    # Each policy evaluates a context and returns allow/deny/abstain

    def __init__(self, name: str, priority: int = 0) -> None:
        self.name = name
        self.priority = priority  # higher priority policies are evaluated first

    @abstractmethod
    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        ...


class OwnerPolicy(Policy):
    # Resource owners can perform any action on their own resources

    def __init__(self) -> None:
        super().__init__("owner_access", priority=100)

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        owner_id = ctx.resource_attrs.get("owner_id")
        if owner_id and owner_id == ctx.subject_id:
            return PolicyResult(
                PolicyEffect.ALLOW, self.name,
                f"Subject {ctx.subject_id} owns resource {ctx.resource_id}"
            )
        return PolicyResult(PolicyEffect.ABSTAIN, self.name, "Not the owner")


class DepartmentPolicy(Policy):
    # Users can only access resources within their own department

    def __init__(self) -> None:
        super().__init__("department_isolation", priority=90)

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        user_dept = ctx.subject_attrs.get("department")
        resource_dept = ctx.resource_attrs.get("department")
        # If either lacks a department attribute, this policy does not apply
        if not user_dept or not resource_dept:
            return PolicyResult(PolicyEffect.ABSTAIN, self.name, "No department context")
        if user_dept != resource_dept:
            return PolicyResult(
                PolicyEffect.DENY, self.name,
                f"Cross-department access denied: user={user_dept}, resource={resource_dept}"
            )
        return PolicyResult(PolicyEffect.ABSTAIN, self.name, "Same department")


class TimeWindowPolicy(Policy):
    # Restrict write operations to business hours (configurable)

    def __init__(self, start_hour: int = 6, end_hour: int = 22) -> None:
        super().__init__("business_hours", priority=50)
        self._start = start_hour
        self._end = end_hour

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        if ctx.action == Action.READ:
            return PolicyResult(PolicyEffect.ABSTAIN, self.name, "Reads are unrestricted")
        current_hour = ctx.environment.get("hour_of_day", time.localtime().tm_hour)
        if not (self._start <= current_hour < self._end):
            return PolicyResult(
                PolicyEffect.DENY, self.name,
                f"Write operations restricted outside {self._start}:00-{self._end}:00"
            )
        return PolicyResult(PolicyEffect.ABSTAIN, self.name, "Within business hours")
```

## Combined Authorization Engine with Audit Trail

```python
from collections import OrderedDict

class LRUCache:
    # Simple LRU cache for policy decisions
    # In production, use Redis with TTL for distributed caching

    def __init__(self, maxsize: int = 1024) -> None:
        self._cache: OrderedDict[int, tuple[bool, str]] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: int) -> Optional[tuple[bool, str]]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: int, value: tuple[bool, str]) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
        self._cache[key] = value


@dataclass
class AuditEntry:
    timestamp: float
    subject_id: str
    action: str
    resource_type: str
    resource_id: Optional[str]
    allowed: bool
    reason: str
    policies_evaluated: List[str]


class AuthorizationEngine:
    # Combines RBAC role checks with ABAC policy evaluation
    # Decision strategy: deny-overrides -- any DENY from a policy results in denial

    def __init__(self, role_registry: RoleRegistry) -> None:
        self._role_registry = role_registry
        self._policies: List[Policy] = []
        self._audit_log: List[AuditEntry] = []
        self._cache = LRUCache(maxsize=2048)

    def add_policy(self, policy: Policy) -> None:
        self._policies.append(policy)
        # Re-sort by priority descending so high-priority policies run first
        self._policies.sort(key=lambda p: p.priority, reverse=True)

    def authorize(self, ctx: PolicyContext) -> bool:
        # Step 1: Check decision cache
        cache_key = hash((
            ctx.subject_id, ctx.action, ctx.resource_type,
            ctx.resource_id, frozenset(ctx.subject_roles),
        ))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached[0]

        # Step 2: RBAC check -- does any of the user's roles grant this permission?
        rbac_allowed = False
        required_perm = Permission(ctx.resource_type, ctx.action)
        for role_name in ctx.subject_roles:
            effective = self._role_registry.get_effective_permissions(role_name)
            # ADMIN permission implies all actions on that resource type
            admin_perm = Permission(ctx.resource_type, Action.ADMIN)
            if required_perm in effective or admin_perm in effective:
                rbac_allowed = True
                break

        # Step 3: ABAC policy evaluation (deny-overrides)
        evaluated_policies: List[str] = []
        abac_denied = False
        abac_allowed = False
        deny_reason = ""

        for policy in self._policies:
            result = policy.evaluate(ctx)
            evaluated_policies.append(f"{policy.name}:{result.effect.name}")
            if result.effect == PolicyEffect.DENY:
                abac_denied = True
                deny_reason = result.reason
                break  # deny-overrides: stop on first deny
            elif result.effect == PolicyEffect.ALLOW:
                abac_allowed = True

        # Final decision: RBAC must allow AND no ABAC policy must deny
        # An explicit ABAC ALLOW can also grant access even without RBAC
        allowed = (rbac_allowed or abac_allowed) and not abac_denied
        reason = deny_reason if abac_denied else (
            "RBAC grant" if rbac_allowed else (
                "ABAC grant" if abac_allowed else "No matching permission or policy"
            )
        )

        # Step 4: Audit log
        self._audit_log.append(AuditEntry(
            timestamp=time.time(),
            subject_id=ctx.subject_id,
            action=ctx.action.value,
            resource_type=ctx.resource_type,
            resource_id=ctx.resource_id,
            allowed=allowed,
            reason=reason,
            policies_evaluated=evaluated_policies,
        ))

        # Step 5: Cache the decision
        self._cache.put(cache_key, (allowed, reason))

        if not allowed:
            logger.warning(
                "Access denied: subject=%s action=%s resource=%s:%s reason=%s",
                ctx.subject_id, ctx.action.value,
                ctx.resource_type, ctx.resource_id, reason,
            )

        return allowed

    def get_audit_log(self, subject_id: Optional[str] = None) -> List[AuditEntry]:
        if subject_id:
            return [e for e in self._audit_log if e.subject_id == subject_id]
        return list(self._audit_log)
```

A **common mistake** is caching authorization decisions too aggressively. If a user's role changes or a resource's attributes change, stale cache entries can grant unauthorized access. Therefore, always invalidate the cache on role assignment changes and keep cache TTLs short (30-60 seconds).

## Summary and Key Takeaways

- **RBAC provides the foundation**: roles, permissions, and inheritance cover 80% of authorization needs with clear auditability
- **ABAC adds expressiveness**: attribute-based policies handle context-dependent rules (department isolation, time windows, IP restrictions) that RBAC cannot
- **Deny-overrides** is the safest combination strategy -- a single DENY from any policy blocks access regardless of other ALLOWs
- **Role hierarchies should be DAGs**, not trees -- use BFS traversal to correctly resolve diamond inheritance
- **Always audit authorization decisions** with enough context (who, what, when, why) to support forensic analysis
- **Cache decisions carefully**: invalidate on role/attribute changes and use short TTLs to prevent stale grants
- **Separate authentication from authorization**: the auth middleware should receive an already-authenticated identity and only decide access
- **Best practice**: make authorization decisions at the service boundary (API gateway or middleware), not scattered throughout business logic
"""
    ),

    # --- 4. Passkeys and WebAuthn ---
    (
        "passkeys_webauthn_fido2_relying_party_python",
        "Explain passkeys and WebAuthn in depth -- the FIDO2 protocol stack, registration and "
        "authentication ceremonies, resident credentials vs non-resident credentials, platform "
        "authenticators vs roaming authenticators, and implement a complete Python relying party "
        "server for WebAuthn with proper challenge management, credential storage, and attestation "
        "verification using type hints throughout.",
        r"""
# Passkeys and WebAuthn: Implementing Phishing-Resistant Authentication

## The FIDO2 Protocol Stack

FIDO2 is a set of standards that enables **passwordless, phishing-resistant authentication** using public key cryptography. It consists of two specifications:

1. **WebAuthn** (W3C): The browser JavaScript API that web applications use to create and use credentials
2. **CTAP2** (FIDO Alliance): The protocol between the browser and the authenticator device (hardware key, platform biometric, phone)

The key insight is that FIDO2 binds credentials to the **origin** (scheme + host + port) of the relying party. An attacker running a phishing site at `evil.com` cannot use credentials created for `bank.com` because the browser enforces origin binding at the protocol level. This is why WebAuthn is considered **phishing-resistant** -- it is not merely phishing-*resistant* by policy, but phishing-*proof* by construction.

**Common mistake**: Confusing passkeys with FIDO2 security keys. A **passkey** is a FIDO2 credential that is **synced** across devices via the platform credential manager (iCloud Keychain, Google Password Manager, 1Password). A traditional FIDO2 credential on a hardware security key (YubiKey) is device-bound and not synced. Both use the same WebAuthn protocol, but passkeys prioritize usability (no hardware to carry) while hardware keys prioritize security (credentials never leave the device).

## Registration and Authentication Ceremonies

The **registration ceremony** (also called attestation) creates a new credential:

1. The relying party generates a random **challenge** and sends it with user info and RP info
2. The authenticator creates a new key pair, stores the private key, and returns the public key + credential ID + attestation
3. The relying party verifies the attestation and stores the public key + credential ID

The **authentication ceremony** (also called assertion) verifies identity:

1. The relying party generates a random **challenge** and optionally sends a list of allowed credential IDs
2. The authenticator signs the challenge with the private key and returns the signature + authenticator data
3. The relying party verifies the signature against the stored public key

## Core Data Models and Challenge Management

```python
import os
import time
import secrets
import hashlib
import json
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import base64
import cbor2  # CBOR decoding for attestation objects

# WebAuthn data structures following the W3C specification

class AttestationConveyance(Enum):
    NONE = "none"  # no attestation -- recommended for most use cases
    INDIRECT = "indirect"
    DIRECT = "direct"
    ENTERPRISE = "enterprise"


class AuthenticatorAttachment(Enum):
    PLATFORM = "platform"  # built-in biometric (TouchID, Windows Hello)
    CROSS_PLATFORM = "cross-platform"  # USB/NFC security key


class UserVerification(Enum):
    REQUIRED = "required"  # biometric or PIN must be used
    PREFERRED = "preferred"
    DISCOURAGED = "discouraged"


class ResidentKeyRequirement(Enum):
    REQUIRED = "required"  # discoverable credential (passkey)
    PREFERRED = "preferred"
    DISCOURAGED = "discouraged"


@dataclass
class StoredCredential:
    # Server-side credential record stored after registration
    credential_id: bytes
    public_key: bytes  # COSE-encoded public key
    sign_count: int  # monotonic counter to detect cloned authenticators
    user_id: str
    aaguid: bytes  # authenticator model identifier
    created_at: float = field(default_factory=time.time)
    last_used_at: Optional[float] = None
    friendly_name: str = ""
    is_discoverable: bool = False  # true for passkeys / resident credentials
    transports: List[str] = field(default_factory=list)  # usb, ble, nfc, internal


@dataclass
class WebAuthnChallenge:
    # Ephemeral challenge bound to a session
    challenge: bytes
    created_at: float
    purpose: str  # "registration" or "authentication"
    user_id: Optional[str] = None  # set for registration

    def is_valid(self, max_age_seconds: int = 300) -> bool:
        return (time.time() - self.created_at) < max_age_seconds


class ChallengeStore:
    # In-memory challenge store; use Redis with TTL in production
    # Challenges are single-use and expire after 5 minutes

    def __init__(self) -> None:
        self._challenges: Dict[str, WebAuthnChallenge] = {}

    def create(self, purpose: str, user_id: Optional[str] = None) -> bytes:
        challenge_bytes = secrets.token_bytes(32)
        key = base64.urlsafe_b64encode(challenge_bytes).decode()
        self._challenges[key] = WebAuthnChallenge(
            challenge=challenge_bytes,
            created_at=time.time(),
            purpose=purpose,
            user_id=user_id,
        )
        return challenge_bytes

    def consume(self, challenge_bytes: bytes, expected_purpose: str) -> bool:
        key = base64.urlsafe_b64encode(challenge_bytes).decode()
        record = self._challenges.pop(key, None)
        if record is None:
            return False
        if not record.is_valid():
            return False
        if record.purpose != expected_purpose:
            return False
        return True
```

A **pitfall** in challenge management is allowing challenge reuse. Each challenge must be consumed exactly once -- if an attacker captures a valid authentication response, they cannot replay it because the challenge has already been consumed.

## Relying Party Implementation

```python
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA,
    EllipticCurvePublicKey,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.exceptions import InvalidSignature

# COSE algorithm identifiers
COSE_ALG_ES256 = -7
COSE_ALG_EDDSA = -8
COSE_ALG_RS256 = -257


class RelyingParty:
    # WebAuthn Relying Party server implementation
    # Handles registration and authentication ceremonies

    def __init__(
        self,
        rp_id: str,  # e.g., "example.com" -- must match the origin's effective domain
        rp_name: str,
        origin: str,  # e.g., "https://example.com"
    ) -> None:
        self._rp_id = rp_id
        self._rp_name = rp_name
        self._origin = origin
        self._challenges = ChallengeStore()
        # In production, this is your database
        self._credentials: Dict[str, List[StoredCredential]] = {}  # user_id -> credentials

    def generate_registration_options(
        self,
        user_id: str,
        user_name: str,
        user_display_name: str,
        authenticator_attachment: Optional[AuthenticatorAttachment] = None,
        resident_key: ResidentKeyRequirement = ResidentKeyRequirement.PREFERRED,
    ) -> Dict[str, Any]:
        # Generate options for navigator.credentials.create()
        challenge = self._challenges.create("registration", user_id)

        # Exclude credentials already registered to prevent duplicate registration
        exclude_credentials = []
        for cred in self._credentials.get(user_id, []):
            exclude_credentials.append({
                "type": "public-key",
                "id": base64.urlsafe_b64encode(cred.credential_id).rstrip(b"=").decode(),
                "transports": cred.transports,
            })

        options: Dict[str, Any] = {
            "challenge": base64.urlsafe_b64encode(challenge).rstrip(b"=").decode(),
            "rp": {"id": self._rp_id, "name": self._rp_name},
            "user": {
                "id": base64.urlsafe_b64encode(user_id.encode()).rstrip(b"=").decode(),
                "name": user_name,
                "displayName": user_display_name,
            },
            "pubKeyCredParams": [
                {"type": "public-key", "alg": COSE_ALG_ES256},
                {"type": "public-key", "alg": COSE_ALG_EDDSA},
                {"type": "public-key", "alg": COSE_ALG_RS256},
            ],
            "timeout": 300000,  # 5 minutes
            "attestation": AttestationConveyance.NONE.value,
            "excludeCredentials": exclude_credentials,
            "authenticatorSelection": {
                "residentKey": resident_key.value,
                "userVerification": UserVerification.REQUIRED.value,
            },
        }

        if authenticator_attachment:
            options["authenticatorSelection"]["authenticatorAttachment"] = (
                authenticator_attachment.value
            )

        return options

    def verify_registration(
        self,
        credential_id_b64: str,
        attestation_object_b64: str,
        client_data_json_b64: str,
        user_id: str,
    ) -> StoredCredential:
        # Verify the registration response from the authenticator
        client_data_json = base64.urlsafe_b64decode(
            client_data_json_b64 + "=="  # pad for base64
        )
        client_data = json.loads(client_data_json)

        # Step 1: Verify the challenge
        challenge_bytes = base64.urlsafe_b64decode(client_data["challenge"] + "==")
        if not self._challenges.consume(challenge_bytes, "registration"):
            raise WebAuthnError("Invalid or expired challenge")

        # Step 2: Verify origin
        if client_data["origin"] != self._origin:
            raise WebAuthnError(
                f"Origin mismatch: expected {self._origin}, got {client_data['origin']}"
            )

        # Step 3: Verify type
        if client_data["type"] != "webauthn.create":
            raise WebAuthnError("Invalid ceremony type")

        # Step 4: Decode attestation object (CBOR-encoded)
        attestation_object = base64.urlsafe_b64decode(attestation_object_b64 + "==")
        attestation = cbor2.loads(attestation_object)
        auth_data = attestation["authData"]

        # Step 5: Parse authenticator data
        rp_id_hash = auth_data[:32]
        expected_rp_id_hash = hashlib.sha256(self._rp_id.encode()).digest()
        if rp_id_hash != expected_rp_id_hash:
            raise WebAuthnError("RP ID hash mismatch")

        flags = auth_data[32]
        user_present = bool(flags & 0x01)
        user_verified = bool(flags & 0x04)
        attested_cred_data = bool(flags & 0x40)

        if not user_present:
            raise WebAuthnError("User presence flag not set")

        if not attested_cred_data:
            raise WebAuthnError("No attested credential data in registration")

        # Step 6: Extract credential public key from authenticator data
        sign_count = int.from_bytes(auth_data[33:37], "big")
        aaguid = auth_data[37:53]
        cred_id_len = int.from_bytes(auth_data[53:55], "big")
        credential_id = auth_data[55:55 + cred_id_len]
        public_key_cbor = auth_data[55 + cred_id_len:]

        credential = StoredCredential(
            credential_id=credential_id,
            public_key=public_key_cbor,
            sign_count=sign_count,
            user_id=user_id,
            aaguid=aaguid,
            is_discoverable=True,
            transports=["internal", "hybrid"],
        )

        if user_id not in self._credentials:
            self._credentials[user_id] = []
        self._credentials[user_id].append(credential)

        return credential

    def generate_authentication_options(
        self, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        # Generate options for navigator.credentials.get()
        # If user_id is None, this is a discoverable credential flow (passkey)
        challenge = self._challenges.create("authentication", user_id)

        options: Dict[str, Any] = {
            "challenge": base64.urlsafe_b64encode(challenge).rstrip(b"=").decode(),
            "timeout": 300000,
            "rpId": self._rp_id,
            "userVerification": UserVerification.REQUIRED.value,
        }

        # For non-discoverable flow, provide allowed credential IDs
        if user_id and user_id in self._credentials:
            options["allowCredentials"] = [
                {
                    "type": "public-key",
                    "id": base64.urlsafe_b64encode(c.credential_id).rstrip(b"=").decode(),
                    "transports": c.transports,
                }
                for c in self._credentials[user_id]
            ]

        return options


class WebAuthnError(Exception):
    pass
```

## Authenticator Data Verification and Sign Count

```python
class SignCountVerifier:
    # Detects cloned authenticators by monitoring the signature counter
    # Each authenticator increments its counter on every operation;
    # if the counter goes backward, the authenticator may have been cloned

    @staticmethod
    def verify_and_update(
        credential: StoredCredential,
        new_sign_count: int,
    ) -> bool:
        if new_sign_count == 0 and credential.sign_count == 0:
            # Some authenticators (especially passkeys) always report 0
            # This is acceptable but provides no clone detection
            return True

        if new_sign_count <= credential.sign_count:
            # Counter went backward or stayed the same -- possible clone!
            # Best practice: flag the credential but do not automatically
            # block the user (could be a legitimate platform sync issue)
            return False

        # Counter advanced as expected -- update stored value
        credential.sign_count = new_sign_count
        credential.last_used_at = time.time()
        return True


class AuthenticationVerifier:
    # Verifies authentication assertions
    # This completes the authentication ceremony server-side

    def __init__(self, rp_id: str, origin: str) -> None:
        self._rp_id = rp_id
        self._origin = origin

    def verify(
        self,
        auth_data: bytes,
        client_data_json: bytes,
        signature: bytes,
        credential: StoredCredential,
    ) -> bool:
        # Parse and verify client data
        client_data = json.loads(client_data_json)
        if client_data["type"] != "webauthn.get":
            raise WebAuthnError("Invalid ceremony type for authentication")
        if client_data["origin"] != self._origin:
            raise WebAuthnError("Origin mismatch")

        # Verify RP ID hash in authenticator data
        rp_id_hash = auth_data[:32]
        if rp_id_hash != hashlib.sha256(self._rp_id.encode()).digest():
            raise WebAuthnError("RP ID hash mismatch")

        # Verify user presence flag
        flags = auth_data[32]
        if not (flags & 0x01):
            raise WebAuthnError("User not present")

        # Verify signature over (authData || SHA-256(clientDataJSON))
        client_data_hash = hashlib.sha256(client_data_json).digest()
        signed_data = auth_data + client_data_hash

        # Decode the COSE public key and verify
        cose_key = cbor2.loads(credential.public_key)
        alg = cose_key.get(3)  # COSE key algorithm

        if alg == COSE_ALG_ES256:
            # P-256 ECDSA verification
            from cryptography.hazmat.primitives.asymmetric.ec import (
                EllipticCurvePublicNumbers,
                SECP256R1,
            )
            x = int.from_bytes(cose_key[-2], "big")
            y = int.from_bytes(cose_key[-3], "big")
            pub_numbers = EllipticCurvePublicNumbers(x, y, SECP256R1())
            public_key = pub_numbers.public_key()
            try:
                public_key.verify(signature, signed_data, ECDSA(SHA256()))
                return True
            except InvalidSignature:
                return False

        raise WebAuthnError(f"Unsupported COSE algorithm: {alg}")
```

The **trade-off** with passkeys versus hardware security keys is clear: passkeys are synced across devices (great UX, easier recovery), but the private key exists on multiple devices and in cloud backups. Hardware security keys never export the private key (stronger security), but losing the key means losing access. **Best practice** for high-security applications: accept passkeys as a first factor but require a hardware key for sensitive operations (admin actions, financial transfers).

## Summary and Key Takeaways

- **WebAuthn is phishing-proof by construction** -- credentials are origin-bound at the protocol level, not by policy
- **Passkeys are synced FIDO2 credentials**: they trade device-binding for cross-device convenience and account recovery
- **Challenges must be single-use and short-lived** (5 minutes max) to prevent replay attacks
- **Always verify**: origin, RP ID hash, user presence flag, and signature in the authentication ceremony
- **Sign count monitoring** detects cloned authenticators, but some platforms (notably passkey implementations) always report zero -- handle this gracefully
- **Prefer `attestation: "none"`** unless you have a specific compliance requirement -- attestation reveals the authenticator model, which is a privacy concern
- **Resident credentials** (discoverable credentials) enable username-less login -- the authenticator stores the user handle and presents available credentials
- **Best practice** for account recovery: register multiple credentials (passkey + hardware key + recovery codes) so a single lost device does not lock out the user
"""
    ),

    # --- 5. API Key Management ---
    (
        "api_key_management_hashing_rotation_rate_limiting_python",
        "Explain API key management in depth -- secure key generation, hashing and storage, "
        "key rotation strategies with zero-downtime transitions, rate limiting per key, scoped "
        "permissions for fine-grained access control, and implement a complete database-backed "
        "API key management system in Python with proper security practices and type hints.",
        r"""
# API Key Management: Secure Generation, Storage, and Lifecycle

## Why API Key Management Matters

API keys are the most common authentication mechanism for machine-to-machine communication, yet they are frequently mismanaged. **Common mistakes** include storing keys in plaintext, never rotating them, granting full access to every key, and providing no mechanism for revocation. A single leaked API key with unrestricted permissions can compromise an entire system.

The fundamental challenge is that API keys are **bearer tokens** -- whoever possesses the key can use it. There is no additional factor, no session binding, and no origin verification. Therefore, every other aspect of key management must compensate for this inherent weakness: short lifetimes, minimal permissions, usage monitoring, and immediate revocability.

**Best practice**: Treat API keys as passwords for machines. Hash them before storage, scope them to minimum required permissions, rotate them on a schedule, and monitor them for anomalous usage.

## Key Generation: Entropy and Format

```python
import secrets
import hashlib
import hmac
import time
import re
from typing import Optional, Dict, Any, List, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum, Flag, auto
from datetime import datetime, timedelta, timezone
import base64


class KeyPrefix(Enum):
    # Prefixes identify key type and enable quick lookups without hashing
    # Following the convention used by Stripe, GitHub, and others
    LIVE = "hv_live"    # production key
    TEST = "hv_test"    # sandbox/test key
    ADMIN = "hv_admin"  # administrative key

    def validate(self, raw_key: str) -> bool:
        return raw_key.startswith(f"{self.value}_")


class APIKeyGenerator:
    # Generates cryptographically secure API keys with type-identifying prefixes
    # Format: {prefix}_{random_bytes_base62}
    # Example: hv_live_a3Bf9kLm2xYz7Wq...

    BASE62_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

    @classmethod
    def generate(cls, prefix: KeyPrefix, byte_length: int = 32) -> Tuple[str, str]:
        # Returns (raw_key, key_hash)
        # The raw key is shown to the user ONCE; only the hash is stored
        random_bytes = secrets.token_bytes(byte_length)
        # Base62 encoding for URL-safe, copy-paste friendly keys
        key_body = cls._base62_encode(random_bytes)
        raw_key = f"{prefix.value}_{key_body}"

        # SHA-256 hash for storage -- fast enough for per-request lookups
        # We do NOT use bcrypt/scrypt because API keys have high entropy
        # (256 bits) unlike passwords, so brute-force is infeasible
        key_hash = cls._hash_key(raw_key)

        return raw_key, key_hash

    @classmethod
    def _base62_encode(cls, data: bytes) -> str:
        # Convert bytes to a base62 string
        num = int.from_bytes(data, "big")
        if num == 0:
            return cls.BASE62_CHARS[0]
        chars: list[str] = []
        while num > 0:
            num, remainder = divmod(num, 62)
            chars.append(cls.BASE62_CHARS[remainder])
        return "".join(reversed(chars))

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def extract_prefix(raw_key: str) -> Optional[KeyPrefix]:
        # Extract the prefix to determine key type without hashing
        for prefix in KeyPrefix:
            if raw_key.startswith(f"{prefix.value}_"):
                return prefix
        return None
```

Using SHA-256 for hashing API keys (instead of bcrypt) is intentional and correct. **Because** API keys have 256 bits of entropy (compared to ~30 bits for typical passwords), brute-force attacks are computationally infeasible even against fast hashes. Using bcrypt would add unnecessary latency to every API request -- a **trade-off** that makes no sense when the input has sufficient entropy.

## Permission Scoping: Fine-Grained Access Control

```python
class Permission(Flag):
    # Bitfield permissions for efficient storage and checking
    NONE = 0
    READ = auto()        # GET requests
    WRITE = auto()       # POST/PUT/PATCH requests
    DELETE = auto()      # DELETE requests
    ADMIN = auto()       # Administrative operations
    # Common combinations
    READ_WRITE = READ | WRITE
    FULL = READ | WRITE | DELETE | ADMIN


@dataclass
class ResourceScope:
    # Defines which resources and actions a key can access
    resource_pattern: str  # glob-like pattern: "projects/*", "billing", "users/self"
    permissions: Permission

    def matches(self, resource: str) -> bool:
        # Simple glob matching for resource patterns
        # In production, consider using a proper path matcher
        import fnmatch
        return fnmatch.fnmatch(resource, self.resource_pattern)


@dataclass
class APIKeyRecord:
    # Database record for a stored API key
    key_id: str  # unique identifier (UUID)
    key_hash: str  # SHA-256 hash of the raw key
    key_prefix: str  # first 8 chars of raw key for identification in logs
    owner_id: str  # user or organization that owns this key
    name: str  # human-readable label ("CI/CD Pipeline", "Billing Service")
    scopes: List[ResourceScope]
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    last_used_at: Optional[float] = None
    last_used_ip: Optional[str] = None
    is_revoked: bool = False
    revoked_at: Optional[float] = None
    revoked_reason: Optional[str] = None
    # Rate limit overrides (None = use default)
    rate_limit_rpm: Optional[int] = None  # requests per minute
    rate_limit_rpd: Optional[int] = None  # requests per day
    allowed_ips: Optional[List[str]] = None  # IP allowlist (None = any IP)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at

    @property
    def is_active(self) -> bool:
        return not self.is_revoked and not self.is_expired

    def has_permission(self, resource: str, action: Permission) -> bool:
        # Check if any scope grants the required permission on the resource
        for scope in self.scopes:
            if scope.matches(resource) and (scope.permissions & action):
                return True
        return False
```

## Rate Limiting Per Key: Token Bucket Algorithm

```python
from collections import defaultdict
from threading import Lock

@dataclass
class RateLimitState:
    # Token bucket state for a single API key
    tokens: float
    last_refill: float
    request_count_minute: int = 0
    request_count_day: int = 0
    minute_window_start: float = field(default_factory=time.time)
    day_window_start: float = field(default_factory=time.time)


class RateLimiter:
    # Per-key rate limiting using a sliding window counter
    # In production, use Redis with MULTI/EXEC for atomic operations

    DEFAULT_RPM = 60   # requests per minute
    DEFAULT_RPD = 10000  # requests per day

    def __init__(self) -> None:
        self._states: Dict[str, RateLimitState] = {}
        self._lock = Lock()

    def check_and_consume(
        self,
        key_id: str,
        rpm_limit: Optional[int] = None,
        rpd_limit: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        # Returns (allowed, rate_limit_info)
        # rate_limit_info contains headers for the HTTP response
        rpm = rpm_limit or self.DEFAULT_RPM
        rpd = rpd_limit or self.DEFAULT_RPD
        now = time.time()

        with self._lock:
            state = self._states.get(key_id)
            if state is None:
                state = RateLimitState(tokens=float(rpm), last_refill=now)
                self._states[key_id] = state

            # Reset minute window if expired
            if now - state.minute_window_start >= 60:
                state.request_count_minute = 0
                state.minute_window_start = now

            # Reset day window if expired
            if now - state.day_window_start >= 86400:
                state.request_count_day = 0
                state.day_window_start = now

            # Check limits
            minute_remaining = rpm - state.request_count_minute
            day_remaining = rpd - state.request_count_day

            headers = {
                "X-RateLimit-Limit": str(rpm),
                "X-RateLimit-Remaining": str(max(0, minute_remaining - 1)),
                "X-RateLimit-Reset": str(int(state.minute_window_start + 60)),
                "X-RateLimit-Limit-Day": str(rpd),
                "X-RateLimit-Remaining-Day": str(max(0, day_remaining - 1)),
            }

            if minute_remaining <= 0 or day_remaining <= 0:
                retry_after = int(state.minute_window_start + 60 - now) + 1
                headers["Retry-After"] = str(max(1, retry_after))
                return False, headers

            state.request_count_minute += 1
            state.request_count_day += 1
            return True, headers


class APIKeyManager:
    # Complete API key lifecycle management system
    # Handles creation, validation, rotation, and revocation

    def __init__(self) -> None:
        # In production, replace with database queries
        self._keys_by_hash: Dict[str, APIKeyRecord] = {}
        self._keys_by_id: Dict[str, APIKeyRecord] = {}
        self._rate_limiter = RateLimiter()

    def create_key(
        self,
        owner_id: str,
        name: str,
        scopes: List[ResourceScope],
        key_type: KeyPrefix = KeyPrefix.LIVE,
        expires_in_days: Optional[int] = 90,
        rate_limit_rpm: Optional[int] = None,
        allowed_ips: Optional[List[str]] = None,
    ) -> Tuple[str, APIKeyRecord]:
        # Returns (raw_key, record)
        # IMPORTANT: raw_key is returned ONCE and never stored
        import uuid
        raw_key, key_hash = APIKeyGenerator.generate(key_type)
        key_id = str(uuid.uuid4())

        record = APIKeyRecord(
            key_id=key_id,
            key_hash=key_hash,
            key_prefix=raw_key[:12],  # store prefix for identification
            owner_id=owner_id,
            name=name,
            scopes=scopes,
            expires_at=(
                time.time() + expires_in_days * 86400 if expires_in_days else None
            ),
            rate_limit_rpm=rate_limit_rpm,
            allowed_ips=allowed_ips,
        )

        self._keys_by_hash[key_hash] = record
        self._keys_by_id[key_id] = record
        return raw_key, record

    def validate_request(
        self,
        raw_key: str,
        resource: str,
        action: Permission,
        client_ip: Optional[str] = None,
    ) -> Tuple[bool, Optional[APIKeyRecord], Dict[str, Any]]:
        # Full validation pipeline: authenticate -> authorize -> rate limit
        # Returns (allowed, record_if_valid, response_headers)

        # Step 1: Authenticate -- find the key by hash
        key_hash = APIKeyGenerator._hash_key(raw_key)
        record = self._keys_by_hash.get(key_hash)
        if record is None:
            return False, None, {"X-Error": "Invalid API key"}

        # Step 2: Check key status
        if not record.is_active:
            reason = "revoked" if record.is_revoked else "expired"
            return False, record, {"X-Error": f"API key is {reason}"}

        # Step 3: IP allowlist check
        if record.allowed_ips and client_ip:
            if client_ip not in record.allowed_ips:
                return False, record, {"X-Error": "IP not in allowlist"}

        # Step 4: Authorization -- check scoped permissions
        if not record.has_permission(resource, action):
            return False, record, {"X-Error": "Insufficient permissions"}

        # Step 5: Rate limiting
        allowed, headers = self._rate_limiter.check_and_consume(
            record.key_id, record.rate_limit_rpm, record.rate_limit_rpd,
        )
        if not allowed:
            return False, record, headers

        # Update last-used metadata
        record.last_used_at = time.time()
        record.last_used_ip = client_ip

        return True, record, headers

    def rotate_key(
        self,
        key_id: str,
        grace_period_hours: int = 24,
    ) -> Tuple[str, APIKeyRecord]:
        # Zero-downtime rotation:
        # 1. Create a new key with the same scopes
        # 2. Keep the old key active for a grace period
        # 3. The old key auto-expires after the grace period
        old_record = self._keys_by_id.get(key_id)
        if old_record is None:
            raise KeyError(f"Key {key_id} not found")

        # Create new key with same configuration
        prefix = APIKeyGenerator.extract_prefix(
            f"{old_record.key_prefix}_dummy"
        ) or KeyPrefix.LIVE
        raw_key, new_record = self.create_key(
            owner_id=old_record.owner_id,
            name=f"{old_record.name} (rotated)",
            scopes=old_record.scopes,
            key_type=prefix,
            rate_limit_rpm=old_record.rate_limit_rpm,
            allowed_ips=old_record.allowed_ips,
        )

        # Set grace period on old key
        old_record.expires_at = time.time() + grace_period_hours * 3600

        return raw_key, new_record

    def revoke_key(self, key_id: str, reason: str = "manual revocation") -> bool:
        record = self._keys_by_id.get(key_id)
        if record is None:
            return False
        record.is_revoked = True
        record.revoked_at = time.time()
        record.revoked_reason = reason
        return True

    def list_keys(self, owner_id: str) -> List[Dict[str, Any]]:
        # List keys for an owner -- never include the hash or raw key
        results = []
        for record in self._keys_by_id.values():
            if record.owner_id == owner_id:
                results.append({
                    "key_id": record.key_id,
                    "prefix": record.key_prefix,
                    "name": record.name,
                    "created_at": record.created_at,
                    "expires_at": record.expires_at,
                    "last_used_at": record.last_used_at,
                    "is_active": record.is_active,
                    "scopes": [
                        f"{s.resource_pattern}:{s.permissions.name}"
                        for s in record.scopes
                    ],
                })
        return results
```

**However**, there is an important operational consideration with key rotation. The grace period approach works well for planned rotations, but compromised keys need **immediate revocation** with no grace period. Therefore, your key management system needs both: scheduled rotation with overlap and emergency revocation without delay.

A **pitfall** many teams fall into is logging raw API keys. Even partial key logging can be dangerous -- if the first 20 characters are logged, an attacker with the logs needs to brute-force far fewer bits. **Best practice**: only log the key prefix (first 8-12 characters) for debugging, and the key ID for audit trails. Never log the full key or its hash.

## Key Rotation Strategies

There are three primary approaches to key rotation, each with trade-offs:

1. **Overlapping rotation** (recommended): Generate a new key, notify the consumer, keep both active during a grace period, then expire the old key. Zero downtime, but requires coordination.
2. **Versioned keys**: Each key has a version number. The server accepts version N and N-1 simultaneously. Simpler than overlapping but limits you to two active keys per consumer.
3. **Automatic rotation with discovery**: Keys are fetched dynamically from a secrets manager (AWS Secrets Manager, HashiCorp Vault). The rotation happens in the vault, and consumers always fetch the latest version. Best for fully automated environments.

## Summary and Key Takeaways

- **Generate keys with high entropy** (256 bits minimum) using `secrets.token_bytes` -- never use predictable sources
- **Use typed prefixes** (`hv_live_`, `hv_test_`) to identify key types at a glance and route to the correct validation logic
- **Hash with SHA-256**, not bcrypt -- API keys have sufficient entropy to make brute-force infeasible, and bcrypt adds unnecessary latency to every request
- **Scope permissions narrowly**: every key should have the minimum permissions needed for its intended use case
- **Rate limit per key** to contain the blast radius of a compromised key -- a leaked key with 60 RPM limits causes far less damage than one with unlimited throughput
- **Rotate on a schedule** (every 90 days) with a grace period, and support immediate revocation for compromised keys
- **Never log raw keys** -- log only the prefix (for debugging) and the key ID (for audit trails)
- **IP allowlisting** adds defense-in-depth: even if a key is stolen, it cannot be used from an unauthorized network
- **Best practice**: show the raw key to the user exactly once at creation time, then only display the prefix in the dashboard. If the user loses the key, they must create a new one
"""
    ),
]
