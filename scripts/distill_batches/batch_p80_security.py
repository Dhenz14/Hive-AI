"""Security — CORS, CSP, OWASP patterns, and secure coding practices."""

PAIRS = [
    (
        "security/cors-csp",
        "Show CORS and Content Security Policy patterns: headers, middleware, and common configurations.",
        '''CORS and Content Security Policy:

```python
# --- CORS middleware (FastAPI) ---

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Development: permissive CORS
# app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Production: strict CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://myapp.com",
        "https://admin.myapp.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
    max_age=3600,  # Preflight cache: 1 hour
)


# --- Custom CORS for complex cases ---

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """CORS with dynamic origin validation."""

    ALLOWED_PATTERN = r"^https://.*\\.myapp\\.com$"

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")

        import re
        if re.match(self.ALLOWED_PATTERN, origin):
            if request.method == "OPTIONS":
                # Handle preflight
                return Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
                        "Access-Control-Allow-Headers": "Authorization, Content-Type",
                        "Access-Control-Max-Age": "3600",
                    },
                )

            response = await call_next(request)
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

        return await call_next(request)


# --- Content Security Policy ---

CSP_POLICY = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "https://cdn.example.com"],
    "style-src": ["'self'", "'unsafe-inline'"],  # Needed for some CSS-in-JS
    "img-src": ["'self'", "data:", "https:"],
    "font-src": ["'self'", "https://fonts.gstatic.com"],
    "connect-src": ["'self'", "https://api.example.com"],
    "frame-ancestors": ["'none'"],         # Prevent clickjacking
    "base-uri": ["'self'"],                # Prevent base tag injection
    "form-action": ["'self'"],             # Restrict form submissions
    "object-src": ["'none'"],              # Block plugins
    "upgrade-insecure-requests": [],       # Force HTTPS
}


def build_csp_header(policy: dict) -> str:
    """Build CSP header string from policy dict."""
    directives = []
    for directive, sources in policy.items():
        if sources:
            directives.append(f"{directive} {' '.join(sources)}")
        else:
            directives.append(directive)
    return "; ".join(directives)


# --- Security headers middleware ---

from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Clickjacking protection
        response.headers["X-Frame-Options"] = "DENY"

        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS (force HTTPS)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # CSP
        response.headers["Content-Security-Policy"] = build_csp_header(CSP_POLICY)

        # Permissions policy (disable unused browser features)
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(self), payment=()"
        )

        return response
```

Security header patterns:
1. **CORS `allow_origins`** — whitelist specific domains, never `*` with credentials
2. **CSP `default-src 'self'`** — block all external resources by default
3. **`frame-ancestors 'none'`** — prevent clickjacking (CSP replacement for X-Frame-Options)
4. **HSTS** — force HTTPS with `Strict-Transport-Security` header
5. **`X-Content-Type-Options: nosniff`** — prevent MIME type sniffing attacks'''
    ),
    (
        "security/input-validation",
        "Show secure input validation patterns: SQL injection prevention, XSS prevention, and OWASP top 10 mitigations.",
        '''Input validation and OWASP mitigations:

```python
import re
import html
import secrets
import hashlib
import hmac
from typing import Annotated
from pydantic import BaseModel, field_validator, Field
from fastapi import FastAPI, Depends, HTTPException, Header, Request


# --- Input validation with Pydantic ---

class CreateUserRequest(BaseModel):
    """Strict input validation prevents injection attacks."""

    username: Annotated[str, Field(
        min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_-]+$"
    )]
    email: Annotated[str, Field(max_length=254)]
    password: Annotated[str, Field(min_length=12, max_length=128)]
    bio: Annotated[str, Field(max_length=500)] = ""

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        # Basic email validation (use email-validator lib for production)
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", v):
            raise ValueError("Invalid email format")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Must contain uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Must contain lowercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Must contain digit")
        return v

    @field_validator("bio")
    @classmethod
    def sanitize_bio(cls, v: str) -> str:
        # Sanitize HTML to prevent stored XSS
        return html.escape(v)


# --- SQL injection prevention (parameterized queries) ---

# BAD — SQL injection vulnerable:
# cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
# cursor.execute("SELECT * FROM users WHERE name = '%s'" % name)

# GOOD — parameterized queries:
# cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
# cursor.execute("SELECT * FROM users WHERE name = ?", (name,))

# GOOD — ORM (SQLAlchemy):
# session.query(User).filter(User.id == user_id).first()


# --- CSRF protection ---

class CSRFProtection:
    """Double-submit cookie CSRF protection."""

    def __init__(self, secret: str):
        self.secret = secret

    def generate_token(self) -> str:
        """Generate CSRF token."""
        token = secrets.token_urlsafe(32)
        signature = hmac.new(
            self.secret.encode(), token.encode(), hashlib.sha256,
        ).hexdigest()
        return f"{token}.{signature}"

    def validate_token(self, token: str) -> bool:
        """Validate CSRF token."""
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        raw, signature = parts
        expected = hmac.new(
            self.secret.encode(), raw.encode(), hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)


# --- Rate limiting ---

from collections import defaultdict
import time

class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate: float, burst: int):
        self.rate = rate      # Tokens per second
        self.burst = burst    # Max tokens
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (self.burst, now))

        # Add tokens based on elapsed time
        elapsed = now - last
        tokens = min(self.burst, tokens + elapsed * self.rate)

        if tokens >= 1:
            self._buckets[key] = (tokens - 1, now)
            return True
        return False


# --- Secure file upload ---

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def validate_upload(filename: str, content: bytes) -> str:
    """Validate file upload — prevent path traversal and malicious files."""
    from pathlib import PurePosixPath
    import uuid

    # Prevent path traversal
    safe_name = PurePosixPath(filename).name
    if not safe_name or safe_name.startswith("."):
        raise ValueError("Invalid filename")

    # Check extension
    ext = PurePosixPath(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extension {ext} not allowed")

    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise ValueError("File too large")

    # Check magic bytes (not just extension)
    MAGIC_BYTES = {
        b"\\xff\\xd8\\xff": ".jpg",
        b"\\x89PNG": ".png",
        b"GIF8": ".gif",
        b"%PDF": ".pdf",
    }
    detected = None
    for magic, expected_ext in MAGIC_BYTES.items():
        if content[:len(magic)] == magic:
            detected = expected_ext
            break

    if detected and detected != ext:
        raise ValueError("File extension does not match content")

    # Generate safe filename (never use user-provided name for storage)
    return f"{uuid.uuid4().hex}{ext}"
```

Security patterns:
1. **Pydantic validation** — type + regex + length constraints on all inputs
2. **Parameterized queries** — never interpolate user input into SQL strings
3. **`html.escape()`** — sanitize user content before storing/displaying
4. **CSRF double-submit** — HMAC-signed tokens prevent cross-site request forgery
5. **Magic byte checking** — verify file content matches extension on upload'''
    ),
    (
        "security/secrets-management",
        "Show secrets management patterns: environment variables, secret stores, key rotation, and secure configuration.",
        '''Secrets management patterns:

```python
import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import SecretStr, Field


# --- Pydantic settings (type-safe env vars) ---

class AppSettings(BaseSettings):
    """Load config from environment with validation."""

    # Required secrets (fail fast if missing)
    database_url: SecretStr
    jwt_secret: SecretStr
    api_key: SecretStr

    # Optional with defaults
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: list[str] = ["https://myapp.com"]

    # Nested prefix
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: SecretStr = SecretStr("")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "",          # No prefix
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> AppSettings:
    """Singleton settings — loaded once, cached."""
    return AppSettings()


# Usage:
# settings = get_settings()
# db_url = settings.database_url.get_secret_value()  # Explicit unwrap


# --- .env file (NEVER commit to git) ---

# .env
# DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
# JWT_SECRET=super-secret-key-here
# API_KEY=sk-abc123...

# .gitignore
# .env
# .env.*
# !.env.example


# --- .env.example (commit this as template) ---

# .env.example
# DATABASE_URL=postgresql://user:password@localhost:5432/dbname
# JWT_SECRET=change-me-in-production
# API_KEY=your-api-key-here


# --- Secret rotation pattern ---

class RotatingSecret:
    """Support two active secrets during rotation."""

    def __init__(self):
        self.current = os.environ["JWT_SECRET"]
        self.previous = os.environ.get("JWT_SECRET_PREVIOUS", "")

    def sign(self, data: str) -> str:
        """Always sign with current secret."""
        import hmac, hashlib
        return hmac.new(
            self.current.encode(), data.encode(), hashlib.sha256,
        ).hexdigest()

    def verify(self, data: str, signature: str) -> bool:
        """Verify against current OR previous secret."""
        import hmac
        for secret in [self.current, self.previous]:
            if not secret:
                continue
            expected = hmac.new(
                secret.encode(), data.encode(), hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(expected, signature):
                return True
        return False


# --- Encryption at rest ---

from cryptography.fernet import Fernet

class FieldEncryptor:
    """Encrypt sensitive fields before storage."""

    def __init__(self, key: bytes | None = None):
        self.key = key or Fernet.generate_key()
        self.fernet = Fernet(self.key)

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self.fernet.decrypt(ciphertext.encode()).decode()


# Usage:
# enc = FieldEncryptor(os.environ["ENCRYPTION_KEY"].encode())
# encrypted_ssn = enc.encrypt("123-45-6789")
# db.store(user_id=1, ssn=encrypted_ssn)
# plaintext_ssn = enc.decrypt(db.get_ssn(user_id=1))


# --- Docker secrets ---

def read_docker_secret(name: str) -> str:
    """Read secret from Docker/Kubernetes secret mount."""
    secret_path = Path(f"/run/secrets/{name}")
    if secret_path.exists():
        return secret_path.read_text().strip()
    # Fall back to environment variable
    value = os.environ.get(name.upper())
    if value is None:
        raise ValueError(f"Secret {name} not found")
    return value


# --- Secure comparison ---

import hmac

def constant_time_compare(a: str, b: str) -> bool:
    """Prevent timing attacks on secret comparison."""
    return hmac.compare_digest(a.encode(), b.encode())
```

Secrets management patterns:
1. **`SecretStr`** — Pydantic type that hides values in logs/repr
2. **`.env` + `.gitignore`** — never commit secrets, commit `.env.example`
3. **Secret rotation** — verify against current + previous key during rollover
4. **`Fernet` encryption** — encrypt PII before database storage
5. **`hmac.compare_digest()`** — constant-time comparison prevents timing attacks'''
    ),
]
