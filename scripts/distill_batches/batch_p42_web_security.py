"""Web security — XSS prevention, CSRF, CSP, password hashing, and security headers."""

PAIRS = [
    (
        "security/web-security-checklist",
        "Show web security implementation: XSS prevention, CSRF tokens, Content Security Policy, password hashing, and security headers in Python.",
        '''Web security implementation checklist:

```python
import hashlib
import hmac
import secrets
from typing import Optional
from datetime import datetime, timezone

# --- Password hashing (use argon2 or bcrypt) ---

# Option 1: argon2 (recommended)
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher(
    time_cost=3,        # Number of iterations
    memory_cost=65536,  # 64MB memory
    parallelism=4,      # Parallel threads
    hash_len=32,        # Output length
    salt_len=16,        # Salt length
)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hash: str) -> bool:
    try:
        return ph.verify(hash, password)
    except VerifyMismatchError:
        return False

# Check if rehash needed (params changed)
def needs_rehash(hash: str) -> bool:
    return ph.check_needs_rehash(hash)


# --- CSRF token generation and validation ---

class CSRFProtection:
    def __init__(self, secret: str):
        self.secret = secret

    def generate_token(self, session_id: str) -> str:
        """Generate CSRF token tied to session."""
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        message = f"{session_id}:{timestamp}"
        signature = hmac.new(
            self.secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return f"{timestamp}:{signature}"

    def validate_token(self, token: str, session_id: str,
                       max_age: int = 3600) -> bool:
        """Validate CSRF token."""
        try:
            timestamp, signature = token.split(":", 1)
            # Check expiry
            token_time = int(timestamp)
            now = int(datetime.now(timezone.utc).timestamp())
            if now - token_time > max_age:
                return False

            # Verify signature
            message = f"{session_id}:{timestamp}"
            expected = hmac.new(
                self.secret.encode(), message.encode(), hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(signature, expected)
        except (ValueError, AttributeError):
            return False


# --- Input sanitization ---

import html
import re

def sanitize_html(text: str) -> str:
    """Escape HTML entities to prevent XSS."""
    return html.escape(text, quote=True)

def sanitize_url(url: str) -> Optional[str]:
    """Validate and sanitize URL (prevent javascript: protocol)."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https", ""):
            return None
        return url
    except Exception:
        return None

def sanitize_filename(filename: str) -> str:
    """Prevent path traversal in file uploads."""
    # Remove path separators and null bytes
    filename = filename.replace("/", "").replace("\\\\", "").replace("\\0", "")
    # Remove leading dots (hidden files)
    filename = filename.lstrip(".")
    # Only allow safe characters
    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    return filename[:255]  # Limit length


# --- Security headers middleware (FastAPI) ---

from fastapi import FastAPI, Request

app = FastAPI()

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # XSS protection (legacy browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # HTTPS enforcement
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self' https://api.example.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    # Permissions policy
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )

    return response


# --- Rate limiting for brute force prevention ---

class LoginRateLimiter:
    def __init__(self, store, max_attempts: int = 5,
                 lockout_seconds: int = 900):
        self.store = store
        self.max_attempts = max_attempts
        self.lockout = lockout_seconds

    async def check_and_record(self, identifier: str) -> tuple[bool, int]:
        """Check if login attempt is allowed. Returns (allowed, remaining)."""
        key = f"login_attempts:{identifier}"
        attempts = int(await self.store.get(key) or 0)

        if attempts >= self.max_attempts:
            ttl = await self.store.ttl(key)
            return False, ttl

        await self.store.incr(key)
        if attempts == 0:
            await self.store.expire(key, self.lockout)

        return True, self.max_attempts - attempts - 1

    async def reset(self, identifier: str):
        """Reset after successful login."""
        await self.store.delete(f"login_attempts:{identifier}")


# --- Secure token generation ---

def generate_reset_token() -> str:
    """Generate URL-safe password reset token."""
    return secrets.token_urlsafe(32)

def generate_api_key() -> str:
    """Generate API key with prefix for identification."""
    prefix = "sk_live"
    key = secrets.token_hex(32)
    return f"{prefix}_{key}"
```

Security checklist:
1. **Password hashing** — argon2id with high memory cost, never SHA/MD5
2. **CSRF tokens** — HMAC-signed, session-bound, time-limited
3. **Input sanitization** — escape HTML, validate URLs, sanitize filenames
4. **Security headers** — CSP, HSTS, X-Frame-Options, nosniff
5. **Rate limiting** — brute force prevention on login endpoints
6. **Constant-time comparison** — `hmac.compare_digest` prevents timing attacks'''
    ),
    (
        "security/api-security",
        "Show API security patterns: API key management, request signing, input validation, and audit logging.",
        '''API security patterns for production:

```python
import hmac
import hashlib
import time
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel, validator, Field
import re

# --- API key authentication ---

class APIKeyAuth:
    """API key validation with scoping and rate limiting."""

    def __init__(self, store):
        self.store = store

    async def validate_key(self, api_key: str) -> dict:
        """Validate API key and return metadata."""
        # Hash the key for lookup (don't store raw keys)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = await self.store.get(f"api_key:{key_hash}")

        if not key_data:
            raise HTTPException(401, "Invalid API key")

        if key_data.get("revoked"):
            raise HTTPException(401, "API key has been revoked")

        if key_data.get("expires_at"):
            if datetime.fromisoformat(key_data["expires_at"]) < datetime.now(timezone.utc):
                raise HTTPException(401, "API key expired")

        return key_data

    async def check_scope(self, key_data: dict, required_scope: str) -> bool:
        scopes = key_data.get("scopes", [])
        return required_scope in scopes or "*" in scopes


# --- Request signing (HMAC) ---

class RequestSigner:
    """Sign and verify API requests (webhook-style)."""

    def __init__(self, secret: str):
        self.secret = secret

    def sign_request(self, method: str, path: str,
                     body: bytes, timestamp: str) -> str:
        """Create HMAC signature for request."""
        message = f"{method}\\n{path}\\n{timestamp}\\n".encode()
        message += body

        return hmac.new(
            self.secret.encode(),
            message,
            hashlib.sha256,
        ).hexdigest()

    def verify_request(self, method: str, path: str,
                       body: bytes, timestamp: str,
                       signature: str, max_age: int = 300) -> bool:
        """Verify request signature and freshness."""
        # Check timestamp freshness (prevent replay attacks)
        try:
            req_time = int(timestamp)
            now = int(time.time())
            if abs(now - req_time) > max_age:
                return False
        except ValueError:
            return False

        expected = self.sign_request(method, path, body, timestamp)
        return hmac.compare_digest(expected, signature)


# --- Input validation with Pydantic ---

class CreateUserRequest(BaseModel):
    email: str = Field(..., max_length=255)
    name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)

    @validator("email")
    def validate_email(cls, v):
        if not re.match(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", v):
            raise ValueError("Invalid email format")
        return v.lower()

    @validator("name")
    def validate_name(cls, v):
        if not re.match(r"^[a-zA-Z\\s'-]+$", v):
            raise ValueError("Name contains invalid characters")
        return v.strip()

    @validator("password")
    def validate_password(cls, v):
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain lowercase letter")
        if not re.search(r"\\d", v):
            raise ValueError("Password must contain digit")
        return v


# --- Audit logging ---

class AuditLogger:
    """Log security-relevant events for compliance."""

    def __init__(self, store):
        self.store = store

    async def log(self, event_type: str, actor: str,
                  resource: str, action: str,
                  details: dict = None, ip: str = None):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "actor": actor,
            "resource": resource,
            "action": action,
            "ip_address": ip,
            "details": details or {},
        }
        await self.store.append_to_stream("audit_log", event)

# Usage:
# await audit.log(
#     event_type="auth",
#     actor=user_id,
#     resource="session",
#     action="login",
#     details={"method": "password", "mfa": True},
#     ip=request.client.host,
# )
```

API security layers:
1. **Authentication** — API keys (hashed), JWT, or OAuth2
2. **Request signing** — HMAC for webhook/API integrity verification
3. **Input validation** — Pydantic models with strict validators
4. **Rate limiting** — per-key and per-IP limits
5. **Audit logging** — record who did what, when, from where
6. **Replay protection** — timestamp validation prevents request reuse'''
    ),
]
"""
