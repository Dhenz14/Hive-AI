"""Thinking-trace pairs: security tasks from non-security developers."""

PAIRS = [
    (
        "thinking/practical",
        r'''we just store passwords with sha256, is that bad?''',
        r'''<think>
Yes, this is bad, but I need to explain WHY clearly so they understand the risk and do not make similar mistakes in the future.

Problems with SHA-256 for passwords:
1. No salt: If two users have the same password, they have the same hash. An attacker with the database can find all users with the same password instantly. Rainbow tables (precomputed hash lookup tables) also work against unsalted hashes.

2. Too fast: SHA-256 is designed to be fast. A modern GPU can compute billions of SHA-256 hashes per second. An attacker with a leaked database can brute-force common passwords in minutes. A 6-character password can be cracked in under a second.

3. Not designed for passwords: SHA-256 is a general-purpose hash. Password hashing needs to be deliberately slow and memory-hard to make brute force expensive.

The right approach: bcrypt, scrypt, or Argon2id. These are:
- Salted automatically (unique salt per password)
- Deliberately slow (configurable work factor)
- Memory-hard (Argon2id) making GPU attacks expensive

I should show them:
1. Why their current approach is dangerous (with concrete attack numbers)
2. How to implement proper password hashing
3. How to migrate existing users without forcing everyone to reset
</think>

Yes, this is a serious vulnerability. Here is why, and how to fix it with a zero-downtime migration.

**Why SHA-256 is dangerous for passwords:**

```
Attack scenario: your database gets leaked (SQL injection, backup exposed, etc.)

SHA-256 speed on a single modern GPU (RTX 4090): ~22 billion hashes/second

Time to crack passwords:
- 6-char lowercase:    308 million combos  -> instant (0.01 seconds)
- 8-char lowercase:    208 billion combos  -> 9 seconds
- 8-char mixed case:   53 trillion combos  -> 40 minutes
- Common passwords:    top 10 million list  -> instant

With bcrypt (cost=12): ~5,000 hashes/second on same GPU
- 8-char mixed case: 53 trillion combos -> 336,000 YEARS
```

The difference is not incremental -- it is the difference between "cracked during lunch" and "heat death of the universe."

**Two additional problems with your current approach:**
1. **No salt** -- if two users have the password "hunter2", they have identical hashes. An attacker finds all of them at once.
2. **Rainbow tables** -- precomputed lookup tables exist for SHA-256. Common passwords are cracked by table lookup, not even brute force.

**Step 1: Implement proper password hashing**

```python
# auth/password.py
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

# Argon2id is the current best practice (winner of the Password Hashing Competition)
# These parameters target ~250ms hash time on a modern server CPU
_hasher = PasswordHasher(
    time_cost=3,        # number of iterations
    memory_cost=65536,  # 64 MB of memory per hash (makes GPU attacks expensive)
    parallelism=4,      # number of threads
    hash_len=32,        # output hash length
    salt_len=16,        # salt length (auto-generated per hash)
)


def hash_password(password: str) -> str:
    """Hash a password for storage. Returns a string containing the
    algorithm, parameters, salt, and hash -- everything needed to verify later."""
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash. Returns True if matches."""
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Check if a stored hash uses outdated parameters and needs rehashing.
    Call this on every successful login to gradually upgrade hash strength."""
    return _hasher.check_needs_rehash(stored_hash)


# Example stored hash looks like:
# $argon2id$v=19$m=65536,t=3,p=4$randomsalthere$hashoutputhere
# Contains: algorithm, version, params, salt, hash -- all in one string
```

**Step 2: Migrate existing SHA-256 hashes without forcing password resets**

```python
# auth/migration.py
"""Strategy: wrap the old SHA-256 hash inside the new Argon2 hash.
This way existing users can log in without resetting their password.
On next login, we rehash with just Argon2."""

import hashlib
from auth.password import hash_password, verify_password, _hasher
from argon2.exceptions import VerifyMismatchError


# During migration, wrap old hashes: argon2(sha256(password))
# This is safe because argon2 provides the salt and slowness

def migrate_hash_in_database(old_sha256_hash: str) -> str:
    """One-time migration: wrap existing SHA-256 hash in Argon2.
    Run this as a database migration script."""
    return _hasher.hash(old_sha256_hash)


def verify_password_during_migration(
    password: str, stored_hash: str
) -> tuple[bool, str | None]:
    """Verify password and return new hash if migration is needed.

    Returns:
        (is_valid, new_hash_or_none)
        - If password is correct with migrated hash: (True, fresh_argon2_hash)
        - If password is correct with modern hash: (True, None)
        - If password is wrong: (False, None)
    """
    # Case 1: Modern Argon2 hash (starts with $argon2)
    if stored_hash.startswith("$argon2"):
        valid = verify_password(password, stored_hash)
        if valid and _hasher.check_needs_rehash(stored_hash):
            return True, hash_password(password)
        return valid, None

    # Case 2: Old SHA-256 hash (64 hex chars, no $ prefix)
    if len(stored_hash) == 64:
        sha256_of_input = hashlib.sha256(password.encode()).hexdigest()
        if sha256_of_input == stored_hash:
            # Password matches old hash -- upgrade to Argon2
            new_hash = hash_password(password)
            return True, new_hash
        return False, None

    # Case 3: Wrapped hash from bulk migration (argon2 of sha256)
    # The stored hash is argon2(old_sha256_hash), so we need to
    # compute sha256(password) and verify that against argon2
    sha256_of_input = hashlib.sha256(password.encode()).hexdigest()
    try:
        _hasher.verify(stored_hash, sha256_of_input)
        # Matches via wrapped hash -- upgrade to direct argon2
        new_hash = hash_password(password)
        return True, new_hash
    except VerifyMismatchError:
        return False, None
```

**Step 3: Integration with your login flow**

```python
# auth/service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from auth.migration import verify_password_during_migration
from auth.password import hash_password
from models.user import User


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def login(self, email: str, password: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        if not user:
            # Constant-time comparison to prevent timing attacks
            # Hash the password anyway so the response time is the same
            # whether the user exists or not
            hash_password(password)
            return None

        is_valid, new_hash = verify_password_during_migration(
            password, user.password_hash
        )

        if not is_valid:
            return None

        # Transparently upgrade the hash on successful login
        if new_hash:
            await self.db.execute(
                update(User)
                .where(User.id == user.id)
                .values(password_hash=new_hash)
            )
            await self.db.commit()

        return user

    async def change_password(self, user_id: int, new_password: str) -> None:
        """Always uses modern Argon2 for new passwords."""
        hashed = hash_password(new_password)
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=hashed)
        )
        await self.db.commit()
```

**Step 4: Database migration script**

```python
# migrations/upgrade_password_hashes.py
"""Bulk-wrap all SHA-256 hashes in Argon2. Run once.
Users can still log in with their current passwords afterward."""

import asyncio
from sqlalchemy import text
from auth.migration import migrate_hash_in_database

async def bulk_migrate():
    # Find all users with old-style SHA-256 hashes (64 hex chars, no $)
    result = await session.execute(text(
        "SELECT id, password_hash FROM users "
        "WHERE password_hash NOT LIKE '$argon2%' "
        "AND length(password_hash) = 64"
    ))

    count = 0
    for row in result.fetchall():
        new_hash = migrate_hash_in_database(row.password_hash)
        await session.execute(
            text("UPDATE users SET password_hash = :hash WHERE id = :id"),
            {"hash": new_hash, "id": row.id},
        )
        count += 1
        if count % 1000 == 0:
            await session.commit()
            print(f"Migrated {count} users...")

    await session.commit()
    print(f"Done. Migrated {count} total users.")
```

**Migration is fully transparent:** existing users log in normally, their hash gets upgraded on next successful login. No password reset emails needed.'''
    ),
    (
        "thinking/practical",
        r'''how do I handle file uploads safely?''',
        r'''<think>
File uploads are a common attack vector. The user probably has a basic file upload that accepts whatever the user sends. Let me think about all the things that can go wrong:

1. File type validation: Users can rename malware.exe to photo.jpg. Checking the extension is not enough -- you need to check the actual file content (magic bytes).

2. File size: Without limits, an attacker can exhaust disk space or memory with a huge upload.

3. Path traversal: If the filename contains "../../../etc/passwd", a naive implementation might write outside the upload directory.

4. Filename injection: Filenames can contain shell metacharacters, null bytes, or very long strings.

5. Image-specific attacks: Images can contain embedded scripts (polyglot files), or be crafted to exploit image processing libraries (ImageTragick).

6. Storage location: Files should never be served from the same domain as your app (prevents XSS via uploaded HTML/SVG). Store in a separate bucket/CDN.

7. Virus scanning: For user-facing platforms, scanning uploads with ClamAV or similar.

8. Denial of service: Slowloris-style attacks where the upload is sent very slowly to tie up server resources.

I should give them a complete, secure upload handler that addresses all of these.
</think>

File uploads are one of the most dangerous features to implement. Here is a secure implementation that handles the major attack vectors.

**The threats and defenses:**

| Attack | Defense |
|--------|---------|
| Malware disguised as image | Validate magic bytes, not just extension |
| Disk exhaustion | Enforce file size limits |
| Path traversal (../../etc/passwd) | Generate random filenames, never use user input |
| XSS via uploaded HTML/SVG | Serve from separate domain, set Content-Disposition |
| Image processing exploits | Validate and re-encode images |
| Filename injection | Strip and replace all filenames |

**Complete secure upload handler:**

```python
# uploads/service.py
import hashlib
import uuid
import magic  # python-magic library for content detection
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from PIL import Image
from fastapi import UploadFile, HTTPException

# Configuration
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
UPLOAD_DIR = Path("/var/uploads")  # outside web root!
ALLOWED_TYPES = {
    # MIME type -> allowed extensions
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/gif": [".gif"],
    "image/webp": [".webp"],
    "application/pdf": [".pdf"],
}
# Maximum image dimensions (prevent decompression bombs)
MAX_IMAGE_DIMENSION = 8192


@dataclass
class UploadResult:
    file_id: str
    original_name: str
    stored_path: str
    mime_type: str
    size_bytes: int
    checksum: str


class SecureUploadService:
    def __init__(self, upload_dir: Path = UPLOAD_DIR):
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def handle_upload(self, file: UploadFile) -> UploadResult:
        """Process an uploaded file with full security validation."""

        # Step 1: Check file size BEFORE reading the whole thing into memory
        content = await self._read_with_size_limit(file)

        # Step 2: Detect actual content type from magic bytes (not the extension)
        detected_type = magic.from_buffer(content, mime=True)
        if detected_type not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{detected_type}' is not allowed. "
                f"Accepted types: {', '.join(ALLOWED_TYPES.keys())}",
            )

        # Step 3: Verify extension matches content type
        original_name = file.filename or "unknown"
        ext = self._safe_extension(original_name, detected_type)

        # Step 4: Additional validation for images
        if detected_type.startswith("image/"):
            content = self._validate_and_sanitize_image(content, detected_type)

        # Step 5: Generate safe filename (NEVER use the original filename)
        file_id = str(uuid.uuid4())
        checksum = hashlib.sha256(content).hexdigest()
        # Organize by date and first 2 chars of ID to avoid too many files per directory
        stored_name = f"{file_id}{ext}"
        subdir = self.upload_dir / file_id[:2]
        subdir.mkdir(exist_ok=True)
        stored_path = subdir / stored_name

        # Step 6: Write file
        stored_path.write_bytes(content)

        return UploadResult(
            file_id=file_id,
            original_name=self._sanitize_filename(original_name),
            stored_path=str(stored_path),
            mime_type=detected_type,
            size_bytes=len(content),
            checksum=checksum,
        )

    async def _read_with_size_limit(self, file: UploadFile) -> bytes:
        """Read file content with a hard size limit to prevent memory exhaustion."""
        chunks = []
        total_size = 0

        while True:
            chunk = await file.read(8192)  # Read in 8KB chunks
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is "
                    f"{MAX_FILE_SIZE // (1024 * 1024)} MB.",
                )
            chunks.append(chunk)

        return b"".join(chunks)

    def _safe_extension(self, filename: str, mime_type: str) -> str:
        """Get file extension, verifying it matches the detected MIME type."""
        allowed_exts = ALLOWED_TYPES.get(mime_type, [])
        # Extract extension from original filename
        ext = Path(filename).suffix.lower()

        if ext in allowed_exts:
            return ext

        # Extension does not match content type -- use the first allowed extension
        # This prevents files like "malware.exe" that contain JPEG data
        return allowed_exts[0] if allowed_exts else ""

    def _sanitize_filename(self, filename: str) -> str:
        """Clean the original filename for storage in metadata (NOT for disk storage).
        We never use this for the actual file path."""
        # Remove path separators (path traversal prevention)
        name = filename.replace("/", "_").replace("\\", "_")
        # Remove null bytes and control characters
        name = "".join(c for c in name if c.isprintable() and ord(c) > 31)
        # Truncate
        if len(name) > 255:
            name = name[:255]
        return name or "unnamed"

    def _validate_and_sanitize_image(self, content: bytes, mime_type: str) -> bytes:
        """Validate image dimensions and re-encode to strip embedded scripts."""
        from io import BytesIO

        try:
            img = Image.open(BytesIO(content))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid or corrupt image file.")

        # Check for decompression bombs (e.g., a 1x1 pixel header with 1 TB of data)
        width, height = img.size
        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            raise HTTPException(
                status_code=400,
                detail=f"Image too large: {width}x{height}. "
                f"Maximum dimension is {MAX_IMAGE_DIMENSION}px.",
            )

        # Re-encode the image to strip any embedded payloads
        # This removes EXIF data, embedded scripts, polyglot payloads
        output = BytesIO()
        format_map = {
            "image/jpeg": "JPEG",
            "image/png": "PNG",
            "image/gif": "GIF",
            "image/webp": "WEBP",
        }
        img_format = format_map.get(mime_type, "PNG")

        # Convert RGBA to RGB for JPEG (JPEG does not support alpha)
        if img_format == "JPEG" and img.mode == "RGBA":
            img = img.convert("RGB")

        img.save(output, format=img_format, quality=90)
        return output.getvalue()
```

**API endpoint with secure serving:**

```python
# uploads/routes.py
from fastapi import APIRouter, UploadFile, File, Depends
from fastapi.responses import FileResponse
from uploads.service import SecureUploadService

router = APIRouter(prefix="/files", tags=["uploads"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    service: SecureUploadService = Depends(),
):
    result = await service.handle_upload(file)
    return {
        "file_id": result.file_id,
        "filename": result.original_name,
        "size": result.size_bytes,
        "type": result.mime_type,
    }


@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
    service: SecureUploadService = Depends(),
):
    """Serve files with security headers."""
    # Validate file_id format (prevent path traversal)
    if not file_id.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid file ID")

    # Look up file metadata from database (not shown)
    metadata = await get_file_metadata(file_id)
    if not metadata:
        raise HTTPException(status_code=404)

    return FileResponse(
        path=metadata.stored_path,
        filename=metadata.original_name,
        media_type=metadata.mime_type,
        headers={
            # Force download instead of inline rendering (prevents XSS)
            "Content-Disposition": f'attachment; filename="{metadata.original_name}"',
            # Prevent MIME sniffing
            "X-Content-Type-Options": "nosniff",
            # Block any scripts
            "Content-Security-Policy": "default-src 'none'",
        },
    )
```

**Production recommendation:** For anything beyond a small internal app, store files in S3/GCS/R2 with signed URLs instead of local disk. This gives you CDN delivery, no disk management, and the files are on a different domain (which prevents XSS from uploaded content automatically).'''
    ),
    (
        "thinking/practical",
        r'''our admin panel is just behind a login, is that enough?''',
        r'''<think>
Almost certainly no. A login is the bare minimum, but admin panels are high-value targets and need defense in depth. Let me think about what they are probably missing:

1. Authorization (not just authentication): Does every admin have full access? They probably need role-based access control. An intern should not be able to delete the production database.

2. Audit logging: If someone does something destructive, can you tell who did it and when? Compliance requires this.

3. Rate limiting on login: Without it, attackers can brute-force admin credentials.

4. Session management: How long do admin sessions last? Are they invalidated on password change?

5. CSRF protection: If an admin visits a malicious page while logged in, can that page make requests to the admin panel?

6. IP restriction: Admin panels usually should not be accessible from the whole internet.

7. Two-factor authentication: For admin access, this should be mandatory.

8. Content Security Policy: Prevent XSS in the admin panel from becoming a full compromise.

I should give them a prioritized checklist and implement the most impactful items.
</think>

No, a login alone is not enough for an admin panel. Admin panels are high-value targets -- if compromised, an attacker has full control of your application. Here is what you need, in priority order.

**The security layers you are probably missing:**

```
Layer 1: Authentication (you have this)
Layer 2: Multi-factor authentication (probably missing)
Layer 3: Role-based access control (probably missing)
Layer 4: Audit logging (probably missing)
Layer 5: Rate limiting (probably missing)
Layer 6: Network restrictions (probably missing)
Layer 7: Session hardening (probably missing)
Layer 8: CSRF + CSP headers (probably missing)
```

**Layer 2: Enforce MFA for admin accounts**

```python
# auth/mfa.py
import pyotp
import qrcode
from io import BytesIO
from base64 import b64encode


def generate_mfa_secret() -> str:
    """Generate a new TOTP secret for a user."""
    return pyotp.random_base32()


def get_provisioning_uri(secret: str, email: str, app_name: str = "MyApp Admin") -> str:
    """Generate the URI for QR code scanning with authenticator app."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=app_name)


def generate_qr_code_base64(uri: str) -> str:
    """Generate a QR code image as base64 for displaying in the browser."""
    img = qrcode.make(uri)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return b64encode(buffer.getvalue()).decode()


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code. Allows 1 period of clock drift."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
```

**Layer 3: Role-based access control**

```python
# auth/rbac.py
from enum import Enum
from typing import Optional
from functools import wraps
from fastapi import HTTPException, Request, Depends


class Permission(str, Enum):
    # User management
    USERS_VIEW = "users:view"
    USERS_EDIT = "users:edit"
    USERS_DELETE = "users:delete"

    # Content management
    CONTENT_VIEW = "content:view"
    CONTENT_EDIT = "content:edit"
    CONTENT_PUBLISH = "content:publish"

    # System administration
    SYSTEM_SETTINGS = "system:settings"
    SYSTEM_LOGS = "system:logs"
    SYSTEM_DANGER = "system:danger"  # destructive operations


# Define roles as sets of permissions
ROLES = {
    "viewer": {
        Permission.USERS_VIEW,
        Permission.CONTENT_VIEW,
    },
    "editor": {
        Permission.USERS_VIEW,
        Permission.CONTENT_VIEW,
        Permission.CONTENT_EDIT,
    },
    "admin": {
        Permission.USERS_VIEW,
        Permission.USERS_EDIT,
        Permission.CONTENT_VIEW,
        Permission.CONTENT_EDIT,
        Permission.CONTENT_PUBLISH,
        Permission.SYSTEM_SETTINGS,
        Permission.SYSTEM_LOGS,
    },
    "superadmin": set(Permission),  # all permissions
}


def require_permission(*permissions: Permission):
    """FastAPI dependency that checks if the current user has required permissions."""
    async def check(request: Request):
        user = request.state.user
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        user_permissions = ROLES.get(user.role, set())
        missing = set(permissions) - user_permissions
        if missing:
            # Log the denied access attempt
            await log_access_denied(user, permissions, request)
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions",
            )
        return user

    return Depends(check)


# Usage in routes:
# @router.delete("/users/{user_id}", dependencies=[require_permission(Permission.USERS_DELETE)])
# async def delete_user(user_id: int): ...
```

**Layer 4: Audit logging (every admin action recorded)**

```python
# audit/logger.py
import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    user_email = Column(String(255), nullable=False)
    action = Column(String(100), nullable=False, index=True)  # e.g., "user.delete"
    resource_type = Column(String(100))  # e.g., "user"
    resource_id = Column(String(100))    # e.g., "42"
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    details = Column(Text)  # JSON blob with before/after values
    risk_level = Column(String(20), default="normal")  # normal, elevated, critical


class AuditLogger:
    def __init__(self, db):
        self.db = db

    async def log(
        self,
        request,
        action: str,
        resource_type: str = None,
        resource_id: str = None,
        details: dict = None,
        risk_level: str = "normal",
    ):
        user = request.state.user
        entry = AuditLog(
            user_id=user.id,
            user_email=user.email,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            ip_address=request.client.host,
            user_agent=request.headers.get("User-Agent", "")[:500],
            details=json.dumps(details) if details else None,
            risk_level=risk_level,
        )
        self.db.add(entry)
        await self.db.commit()

        # Alert on critical actions
        if risk_level == "critical":
            await self._send_alert(entry)

    async def _send_alert(self, entry: AuditLog):
        """Send immediate notification for critical admin actions."""
        # Integrate with your alerting system (Slack, PagerDuty, email)
        print(
            f"CRITICAL ADMIN ACTION: {entry.user_email} performed "
            f"{entry.action} on {entry.resource_type}/{entry.resource_id} "
            f"from {entry.ip_address}"
        )
```

**Layer 5-8: Middleware stack for rate limiting, IP restriction, session hardening, headers**

```python
# admin/middleware.py
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI()

# --- Rate limiting on login ---
_login_attempts = defaultdict(list)  # IP -> list of timestamps

class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    MAX_ATTEMPTS = 5
    WINDOW_SECONDS = 300  # 5 minutes

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/admin/login" and request.method == "POST":
            ip = request.client.host
            now = datetime.utcnow()
            cutoff = now - timedelta(seconds=self.WINDOW_SECONDS)

            # Clean old attempts
            _login_attempts[ip] = [
                t for t in _login_attempts[ip] if t > cutoff
            ]

            if len(_login_attempts[ip]) >= self.MAX_ATTEMPTS:
                raise HTTPException(
                    status_code=429,
                    detail="Too many login attempts. Try again in 5 minutes.",
                )

            _login_attempts[ip].append(now)

        return await call_next(request)


# --- IP restriction (allow only office/VPN IPs) ---
ALLOWED_ADMIN_CIDRS = [
    "10.0.0.0/8",       # Internal network
    "192.168.1.0/24",   # Office network
    # Add your VPN CIDR here
]

class AdminIPRestrictionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/admin"):
            from ipaddress import ip_address, ip_network
            client_ip = ip_address(request.client.host)
            allowed = any(
                client_ip in ip_network(cidr)
                for cidr in ALLOWED_ADMIN_CIDRS
            )
            if not allowed:
                raise HTTPException(status_code=403, detail="Access denied")

        return await call_next(request)


# --- Security headers ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.url.path.startswith("/admin"):
            # Prevent clickjacking
            response.headers["X-Frame-Options"] = "DENY"
            # Prevent MIME sniffing
            response.headers["X-Content-Type-Options"] = "nosniff"
            # XSS protection (legacy browsers)
            response.headers["X-XSS-Protection"] = "1; mode=block"
            # Strict CSP for admin panel
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "frame-ancestors 'none';"
            )
            # Force HTTPS
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response


# Apply all middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AdminIPRestrictionMiddleware)
app.add_middleware(LoginRateLimitMiddleware)
```

**Priority checklist for hardening your admin panel:**
1. Add MFA for all admin accounts (biggest single improvement)
2. Implement RBAC -- not every admin needs delete access
3. Add audit logging for every admin action
4. Rate limit login attempts (5 per 5 minutes)
5. Restrict admin panel to office/VPN IPs if possible
6. Add security headers (CSP, X-Frame-Options, HSTS)
7. Set admin session timeout to 30 minutes of inactivity
8. Invalidate all sessions on password change
9. Require re-authentication for destructive operations ("confirm your password to delete")'''
    ),
    (
        "thinking/practical",
        r'''a security researcher found an XSS bug, how do I fix it and prevent more?''',
        r'''<think>
The user got a responsible disclosure (good!) and needs to fix the specific bug AND prevent future XSS. They probably do not have deep security expertise, so I need to explain the defense-in-depth approach.

XSS defense has multiple layers:
1. Output encoding (the primary defense) -- encode user data before inserting it into HTML
2. Content Security Policy (CSP) -- even if XSS gets through encoding, CSP blocks inline script execution
3. Input sanitization -- for cases where you MUST allow HTML (rich text editors)
4. HttpOnly cookies -- even if XSS executes, it cannot steal session cookies
5. Framework-level protections -- most modern frameworks auto-escape by default

The most impactful fix is implementing a strict CSP, because it is a blanket defense that works even when individual developers make encoding mistakes.

I should show:
1. How to identify and fix the specific XSS type (reflected, stored, DOM)
2. CSP implementation
3. Output encoding patterns
4. How to use DOMPurify for rich text
5. Testing for XSS in CI
</think>

Good that a researcher found it (and not an attacker). Here is how to fix the immediate bug and build defenses so this class of bug cannot happen again.

**Understanding the three XSS types (figure out which one you have):**

```
Reflected XSS:  User input in URL -> reflected in page without encoding
                Example: /search?q=<script>alert(1)</script>
                Fix: encode output

Stored XSS:    User input saved to DB -> rendered to other users without encoding
                Example: comment field containing <script> tags
                Fix: encode on output, sanitize on input for rich text

DOM XSS:       JavaScript reads URL/input and inserts it into DOM unsafely
                Example: document.innerHTML = location.hash.slice(1)
                Fix: use textContent instead of innerHTML, or sanitize
```

**Defense Layer 1: Content Security Policy (most impactful single fix)**

CSP tells the browser to refuse to execute inline scripts, which blocks most XSS even if your encoding has gaps:

```python
# middleware/security.py
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
import hashlib
import secrets


class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate a unique nonce for this request
        # Only scripts with this nonce will execute
        nonce = secrets.token_urlsafe(32)
        request.state.csp_nonce = nonce

        response = await call_next(request)

        # Strict CSP that blocks inline scripts unless they have the nonce
        csp = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic'; "
            f"style-src 'self' 'nonce-{nonce}'; "
            f"img-src 'self' data: https:; "
            f"font-src 'self'; "
            f"connect-src 'self'; "
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'; "
            f"object-src 'none';"
        )

        response.headers["Content-Security-Policy"] = csp
        # Report violations to your monitoring endpoint
        response.headers["Content-Security-Policy-Report-Only"] = (
            csp + " report-uri /api/csp-report;"
        )

        return response


# CSP violation reporting endpoint
@app.post("/api/csp-report")
async def csp_report(request: Request):
    """Log CSP violations -- these indicate XSS attempts or encoding issues."""
    body = await request.json()
    report = body.get("csp-report", {})
    print(
        f"CSP VIOLATION: {report.get('violated-directive')} "
        f"on {report.get('document-uri')} "
        f"blocked: {report.get('blocked-uri')}"
    )
    # Send to your logging/alerting system
    return {"status": "received"}
```

**In your HTML templates, use the nonce for legitimate scripts:**

```html
<!-- Only scripts with the correct nonce will execute -->
<script nonce="{{ csp_nonce }}">
    // This runs because it has the nonce
    initializeApp();
</script>

<!-- An attacker's injected script has no nonce, so the browser blocks it -->
<!-- <script>stealCookies()</script>  BLOCKED by CSP -->
```

**Defense Layer 2: Output encoding (fix the specific bug)**

```python
# templates/encoding.py
"""Output encoding utilities. Use these when rendering user data in HTML."""
from markupsafe import escape as html_escape
import json
import re


def encode_for_html(value: str) -> str:
    """Encode user input for safe insertion into HTML body.
    Converts < > & " ' to HTML entities."""
    return str(html_escape(value))


def encode_for_attribute(value: str) -> str:
    """Encode for insertion into HTML attribute values.
    Always quote your attributes: <div title="ENCODED_VALUE">"""
    return str(html_escape(value))


def encode_for_javascript(value: str) -> str:
    """Encode for insertion into JavaScript string literals.
    Use this when you MUST inject server data into JS."""
    # json.dumps handles escaping for JS string context
    return json.dumps(value)


def encode_for_url(value: str) -> str:
    """Encode for insertion into URL parameters."""
    from urllib.parse import quote
    return quote(value, safe="")


# Example: the WRONG way and the RIGHT way

# WRONG (the bug the researcher found):
# return f"<div class='greeting'>Hello, {user_input}</div>"

# RIGHT:
# return f"<div class='greeting'>Hello, {encode_for_html(user_input)}</div>"

# WRONG in JavaScript context:
# return f"<script>var name = '{user_input}';</script>"

# RIGHT in JavaScript context:
# return f"<script nonce='{nonce}'>var name = {encode_for_javascript(user_input)};</script>"
```

**Defense Layer 3: Sanitize rich text (when you MUST allow HTML)**

```python
# If you have a rich text editor (comments, blog posts, etc.),
# you need server-side sanitization. Never trust client-side sanitization alone.

# Option A: Python server-side with bleach
import bleach

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "s",
    "h1", "h2", "h3", "h4",
    "ul", "ol", "li",
    "a", "img",
    "blockquote", "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(dirty_html: str) -> str:
    """Remove all dangerous HTML while preserving safe formatting."""
    clean = bleach.clean(
        dirty_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    # Also linkify bare URLs
    clean = bleach.linkify(clean)
    return clean
```

```javascript
// Option B: Client-side sanitization with DOMPurify (in addition to server-side)
// Install: npm install dompurify
import DOMPurify from "dompurify";

// Configure allowed tags
const PURIFY_CONFIG = {
    ALLOWED_TAGS: [
        "p", "br", "strong", "em", "u", "s",
        "h1", "h2", "h3", "h4",
        "ul", "ol", "li",
        "a", "img",
        "blockquote", "pre", "code",
    ],
    ALLOWED_ATTR: ["href", "src", "alt", "title", "width", "height"],
    ALLOW_DATA_ATTR: false,
};

function renderUserContent(htmlString, container) {
    // NEVER do: container.innerHTML = htmlString;
    // ALWAYS do:
    container.innerHTML = DOMPurify.sanitize(htmlString, PURIFY_CONFIG);
}
```

**Defense Layer 4: HttpOnly + SameSite cookies**

```python
# Even if XSS executes, prevent it from stealing session cookies
from fastapi.responses import JSONResponse


def set_session_cookie(response: JSONResponse, session_id: str) -> None:
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,      # JavaScript cannot read this cookie
        secure=True,        # Only sent over HTTPS
        samesite="strict",  # Not sent with cross-origin requests (prevents CSRF too)
        max_age=3600,       # 1 hour
        path="/",
    )
```

**Defense Layer 5: Automated XSS scanning in CI**

```yaml
# .github/workflows/security.yml
name: Security Scan
on: [push, pull_request]

jobs:
  xss-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Static analysis for common XSS patterns
      - name: Check for unsafe patterns
        run: |
          # Fail if any template uses |safe or innerHTML without sanitization
          echo "Checking for unsafe template patterns..."
          ! grep -rn '|safe\b' templates/ --include='*.html' || \
            echo "WARNING: Found |safe filter usage - verify each is intentional"
          ! grep -rn 'innerHTML\s*=' src/ --include='*.ts' --include='*.js' | \
            grep -v 'DOMPurify' || \
            echo "WARNING: Found innerHTML without DOMPurify"
          ! grep -rn 'v-html' src/ --include='*.vue' || \
            echo "WARNING: Found v-html directive"

      # Dynamic scanning with OWASP ZAP
      - name: ZAP Scan
        uses: zaproxy/action-baseline@v0.10.0
        with:
          target: "http://localhost:8000"
```

**Immediate action items:**
1. Fix the reported XSS bug with proper output encoding
2. Deploy Content-Security-Policy header (start with report-only mode)
3. Set cookies to HttpOnly + Secure + SameSite=Strict
4. Audit all templates for missing encoding (search for raw user data insertion)
5. Add DOMPurify where you use innerHTML
6. Thank the researcher and update them when the fix is deployed'''
    ),
    (
        "thinking/practical",
        r'''we need to be SOC2 compliant, where do we start with our codebase?''',
        r'''<think>
SOC 2 compliance is a big topic. The user is asking specifically about their codebase, not the full organizational compliance process. SOC 2 has five Trust Service Criteria: Security, Availability, Processing Integrity, Confidentiality, and Privacy. Most companies start with Security (which is required) plus Availability and Confidentiality.

From a codebase perspective, the key areas are:
1. Audit logging - every data access and mutation must be logged
2. Access controls - RBAC, least privilege, MFA
3. Encryption - at rest and in transit
4. Change management - code review, CI/CD controls
5. Vulnerability management - dependency scanning, SAST
6. Data retention and deletion - ability to purge user data
7. Monitoring and alerting - detect anomalies
8. Incident response - automated alerting pipelines

I should focus on the concrete code changes they need to make, not the policy/process side (they will need a compliance consultant for that). Let me give them a prioritized technical checklist with implementation examples.
</think>

SOC 2 compliance touches your codebase in specific, concrete ways. Here is what you need to implement, prioritized by audit impact.

**The SOC 2 areas that require code changes:**

```
1. Audit Logging          - WHO did WHAT to WHICH data and WHEN
2. Access Controls         - RBAC, MFA, least privilege
3. Encryption             - TLS everywhere, encrypt sensitive data at rest
4. Change Management      - PR reviews, CI checks, deploy controls
5. Vulnerability Scanning - Dependency audits, SAST in CI
6. Data Lifecycle         - Retention policies, deletion capabilities
7. Monitoring + Alerting  - Anomaly detection, incident triggers
```

**1. Audit Logging (this is the single most important SOC 2 code requirement)**

```python
# audit/structured_logger.py
"""Structured audit logging that satisfies SOC 2 audit trail requirements.
Every data access and mutation must be recorded with:
- WHO (user ID, email, IP, role)
- WHAT (action performed)
- WHICH (resource type and ID)
- WHEN (timestamp, immutable)
- OUTCOME (success/failure)
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Optional, Any

# Context variable for request-scoped audit data
_audit_context: ContextVar[dict] = ContextVar("audit_context", default={})

# Dedicated audit logger -- writes to append-only storage
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)


class AuditEvent:
    """Structured audit event for SOC 2 compliance."""

    def __init__(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        outcome: str = "success",
        details: Optional[dict] = None,
        risk_level: str = "standard",
    ):
        ctx = _audit_context.get()
        self.event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": {
                "user_id": ctx.get("user_id"),
                "email": ctx.get("email"),
                "role": ctx.get("role"),
                "ip_address": ctx.get("ip_address"),
                "session_id": ctx.get("session_id"),
            },
            "action": action,
            "resource": {
                "type": resource_type,
                "id": resource_id,
            },
            "outcome": outcome,
            "risk_level": risk_level,
            "details": details or {},
            "environment": ctx.get("environment", "production"),
        }

    def emit(self):
        # Write to structured log (ship to immutable storage like S3/CloudWatch)
        audit_logger.info(json.dumps(self.event))
        # For critical events, also write to database for querying
        if self.event["risk_level"] in ("elevated", "critical"):
            _write_to_audit_db(self.event)


def audit_log(
    action: str,
    resource_type: str,
    resource_id: str = None,
    outcome: str = "success",
    details: dict = None,
    risk_level: str = "standard",
):
    """Convenience function for logging audit events."""
    AuditEvent(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        details=details,
        risk_level=risk_level,
    ).emit()


# Middleware to set audit context from request
async def audit_middleware(request, call_next):
    token = _audit_context.set({
        "user_id": getattr(request.state, "user_id", None),
        "email": getattr(request.state, "user_email", None),
        "role": getattr(request.state, "user_role", None),
        "ip_address": request.client.host,
        "session_id": request.cookies.get("session_id"),
        "environment": "production",
    })
    try:
        response = await call_next(request)
        return response
    finally:
        _audit_context.reset(token)


# Example usage in business logic:
#
# async def delete_user(user_id: int):
#     audit_log(
#         action="user.delete",
#         resource_type="user",
#         resource_id=str(user_id),
#         risk_level="critical",
#         details={"reason": "account_closure_request"},
#     )
#     await db.execute(delete(User).where(User.id == user_id))
```

**2. Encryption at rest for sensitive data**

```python
# security/encryption.py
"""Field-level encryption for sensitive data (PII, credentials, etc.)
SOC 2 requires encryption of sensitive data at rest."""

import os
import base64
from cryptography.fernet import Fernet, MultiFernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


class FieldEncryption:
    """Encrypt/decrypt individual database fields.
    Supports key rotation via MultiFernet."""

    def __init__(self):
        # Load encryption keys from environment (NEVER hardcode)
        current_key = os.environ["ENCRYPTION_KEY_CURRENT"]
        previous_keys = os.environ.get("ENCRYPTION_KEY_PREVIOUS", "").split(",")

        # MultiFernet encrypts with the first key, decrypts with any key
        # This enables key rotation without re-encrypting all data at once
        keys = [Fernet(current_key)]
        for key in previous_keys:
            if key.strip():
                keys.append(Fernet(key.strip()))

        self.cipher = MultiFernet(keys)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string value for database storage."""
        if not plaintext:
            return plaintext
        encrypted = self.cipher.encrypt(plaintext.encode("utf-8"))
        return base64.urlsafe_b64encode(encrypted).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a stored value."""
        if not ciphertext:
            return ciphertext
        raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        return self.cipher.decrypt(raw).decode("utf-8")

    def rotate(self, ciphertext: str) -> str:
        """Re-encrypt with the current key. Use during key rotation."""
        raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        rotated = self.cipher.rotate(raw)
        return base64.urlsafe_b64encode(rotated).decode("ascii")


# SQLAlchemy column type for transparent encryption
from sqlalchemy import TypeDecorator, String

_encryptor = None

def get_encryptor() -> FieldEncryption:
    global _encryptor
    if _encryptor is None:
        _encryptor = FieldEncryption()
    return _encryptor


class EncryptedString(TypeDecorator):
    """SQLAlchemy column type that auto-encrypts/decrypts.

    Usage:
        class User(Base):
            ssn = Column(EncryptedString(500))
            # Stored encrypted in DB, decrypted when accessed in Python
    """
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return get_encryptor().encrypt(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return get_encryptor().decrypt(value)
        return value
```

**3. CI/CD security gates (change management controls)**

```yaml
# .github/workflows/security-gates.yml
# SOC 2 requires: code review, automated testing, vulnerability scanning
name: Security Gates

on:
  pull_request:
    branches: [main]

jobs:
  # Gate 1: All PRs require review (configure in GitHub branch protection rules)

  # Gate 2: Dependency vulnerability scanning
  dependency-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check Python dependencies for known vulnerabilities
        run: |
          pip install pip-audit
          pip-audit --requirement requirements.txt --strict

      - name: Check npm dependencies
        run: |
          npm audit --audit-level=high
        if: hashFiles('package-lock.json') != ''

  # Gate 3: Static security analysis
  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Bandit (Python security linter)
        run: |
          pip install bandit
          bandit -r src/ -c pyproject.toml -f json -o bandit-report.json || true
          bandit -r src/ -c pyproject.toml --severity-level high

      - name: Run Semgrep
        uses: returntocorp/semgrep-action@v1
        with:
          config: >-
            p/python
            p/owasp-top-ten
            p/secrets

  # Gate 4: Check for secrets in code
  secret-scanning:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history for scanning

      - name: Run Gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  # Gate 5: Container security (if using Docker)
  container-scan:
    runs-on: ubuntu-latest
    if: hashFiles('Dockerfile') != ''
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t app:scan .
      - name: Scan with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: "app:scan"
          severity: "CRITICAL,HIGH"
          exit-code: "1"
```

**4. Data retention and deletion (right to erasure)**

```python
# data/retention.py
"""Data lifecycle management for SOC 2 compliance.
Must be able to: retain data for required period, delete on request, prove deletion."""

from datetime import datetime, timedelta
from sqlalchemy import text


# Define retention policies per data type
RETENTION_POLICIES = {
    "audit_log": {"retention_days": 365, "deletable": False},  # audit logs must be kept
    "user_data": {"retention_days": None, "deletable": True},  # deleted on request
    "session_tokens": {"retention_days": 30, "deletable": True},
    "api_logs": {"retention_days": 90, "deletable": True},
    "payment_records": {"retention_days": 2555, "deletable": False},  # 7 years for financial
}


async def handle_deletion_request(db, user_id: int) -> dict:
    """Process a data deletion request (GDPR/CCPA/SOC2).
    Returns a manifest of what was deleted and what was retained (with reason)."""
    manifest = {
        "request_id": str(uuid.uuid4()),
        "user_id": user_id,
        "requested_at": datetime.utcnow().isoformat(),
        "actions": [],
    }

    # Delete user profile data
    await db.execute(text(
        "DELETE FROM user_profiles WHERE user_id = :uid"
    ), {"uid": user_id})
    manifest["actions"].append({
        "table": "user_profiles",
        "action": "deleted",
    })

    # Anonymize data we must retain (e.g., order history for accounting)
    await db.execute(text(
        "UPDATE orders SET user_email = 'redacted', "
        "user_name = 'redacted', shipping_address = 'redacted' "
        "WHERE user_id = :uid"
    ), {"uid": user_id})
    manifest["actions"].append({
        "table": "orders",
        "action": "anonymized",
        "reason": "financial_record_retention",
    })

    # Audit logs are NEVER deleted (SOC 2 requirement)
    manifest["actions"].append({
        "table": "audit_log",
        "action": "retained",
        "reason": "soc2_audit_trail_requirement",
    })

    # Log the deletion itself
    audit_log(
        action="user.data_deletion",
        resource_type="user",
        resource_id=str(user_id),
        risk_level="elevated",
        details={"manifest": manifest},
    )

    await db.commit()
    return manifest
```

**SOC 2 codebase checklist (prioritized):**

```
MUST HAVE (auditors will check these):
[1] Audit logging for all data access and mutations
[2] Encryption in transit (TLS/HTTPS everywhere)
[3] Encryption at rest for sensitive fields (PII, credentials)
[4] Access controls (RBAC, MFA for admin)
[5] PR-based code review (branch protection rules)
[6] Automated vulnerability scanning in CI
[7] Secret scanning (no credentials in code)
[8] Data deletion/anonymization capability

SHOULD HAVE (strengthens your audit):
[9]  Dependency pinning with lockfiles
[10] Container image scanning
[11] Automated backup testing
[12] Incident response runbooks
[13] Data retention automation
[14] Session timeout and invalidation
[15] Rate limiting on authentication endpoints
```

Start with items 1-4 (the code changes). Items 5-7 are CI configuration. Items 8+ are operational. A typical engineering team can implement the code changes in 2-4 weeks. The full SOC 2 process (policies, vendor reviews, auditor engagement) takes 3-6 months on top of that.'''
    ),
]
