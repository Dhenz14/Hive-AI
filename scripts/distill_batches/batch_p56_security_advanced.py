"""Security — cryptography, zero trust, OAuth implementation, and secure coding."""

PAIRS = [
    (
        "security/cryptography-python",
        "Show Python cryptography patterns: hashing, encryption, signing, key management, and secure tokens.",
        '''Python cryptography patterns:

```python
import secrets
import hashlib
import hmac
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os


# --- Secure token generation ---

def generate_token(nbytes: int = 32) -> str:
    """Cryptographically secure random token."""
    return secrets.token_urlsafe(nbytes)

def generate_api_key() -> tuple[str, str]:
    """Generate API key pair: key_id + secret."""
    key_id = f"key_{secrets.token_hex(8)}"
    secret = secrets.token_urlsafe(48)
    return key_id, secret


# --- Password hashing (use argon2 or bcrypt) ---

# pip install argon2-cffi
from argon2 import PasswordHasher

ph = PasswordHasher(
    time_cost=3,       # Iterations
    memory_cost=65536,  # 64MB
    parallelism=4,
)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hash: str) -> bool:
    try:
        return ph.verify(hash, password)
    except Exception:
        return False

def needs_rehash(hash: str) -> bool:
    return ph.check_needs_rehash(hash)


# --- HMAC signing ---

def sign_message(message: str, secret: str) -> str:
    """Sign a message with HMAC-SHA256."""
    return hmac.new(
        secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()

def verify_signature(message: str, signature: str, secret: str) -> bool:
    """Constant-time signature verification."""
    expected = sign_message(message, secret)
    return hmac.compare_digest(signature, expected)


# --- Symmetric encryption (AES-GCM) ---

def encrypt_aes_gcm(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt with AES-256-GCM (authenticated encryption)."""
    nonce = os.urandom(12)  # 96-bit nonce
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext  # Prepend nonce

def decrypt_aes_gcm(data: bytes, key: bytes) -> bytes:
    """Decrypt AES-256-GCM."""
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)

def derive_key(password: str, salt: bytes = None) -> tuple[bytes, bytes]:
    """Derive encryption key from password."""
    salt = salt or os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600000,
    )
    key = kdf.derive(password.encode())
    return key, salt


# --- Asymmetric encryption (RSA) ---

def generate_rsa_keypair():
    """Generate RSA key pair."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem

def rsa_sign(message: bytes, private_key_pem: bytes) -> bytes:
    """Sign with RSA-PSS."""
    private_key = serialization.load_pem_private_key(private_key_pem, None)
    return private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )

def rsa_verify(message: bytes, signature: bytes,
               public_key_pem: bytes) -> bool:
    """Verify RSA-PSS signature."""
    public_key = serialization.load_pem_public_key(public_key_pem)
    try:
        public_key.verify(
            signature, message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


# --- Secure random choices ---

def generate_otp(length: int = 6) -> str:
    """Generate numeric OTP."""
    return "".join(secrets.choice("0123456789") for _ in range(length))

def generate_password(length: int = 16) -> str:
    """Generate secure random password."""
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^&*" for c in password)):
            return password
```

Cryptography rules:
1. **`secrets` module** — always use for tokens, keys, OTPs (not `random`)
2. **Argon2** — preferred password hashing (resistant to GPU attacks)
3. **AES-GCM** — authenticated encryption (integrity + confidentiality)
4. **`hmac.compare_digest`** — constant-time comparison prevents timing attacks
5. **Key derivation** — PBKDF2 with 600K+ iterations for password-based keys'''
    ),
    (
        "security/input-validation",
        "Show input validation and sanitization patterns: SQL injection, XSS prevention, path traversal, and safe deserialization.",
        '''Input validation and sanitization patterns:

```python
import re
import html
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
import bleach


# --- Pydantic validation models ---

class UserInput(BaseModel):
    email: str = Field(pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    name: str = Field(min_length=1, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    website: Optional[str] = None
    age: int = Field(ge=13, le=150)

    @field_validator('name')
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        # Remove control characters
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        return v.strip()

    @field_validator('bio')
    @classmethod
    def sanitize_bio(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        # Allow safe HTML tags only
        return bleach.clean(
            v,
            tags=['b', 'i', 'em', 'strong', 'a', 'p', 'br'],
            attributes={'a': ['href']},
            protocols=['http', 'https'],
            strip=True,
        )

    @field_validator('website')
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        parsed = urlparse(v)
        if parsed.scheme not in ('http', 'https'):
            raise ValueError('URL must use http or https')
        if not parsed.hostname:
            raise ValueError('Invalid URL')
        # Prevent SSRF: block internal IPs
        import ipaddress
        try:
            ip = ipaddress.ip_address(parsed.hostname)
            if ip.is_private or ip.is_loopback:
                raise ValueError('Internal URLs not allowed')
        except ValueError:
            pass  # Hostname, not IP — OK
        return v


# --- SQL injection prevention ---

# ALWAYS use parameterized queries

# BAD: string formatting (SQL injection)
# query = f"SELECT * FROM users WHERE email = '{email}'"

# GOOD: parameterized query
async def find_user(conn, email: str):
    return await conn.fetchrow(
        "SELECT * FROM users WHERE email = $1", email
    )

# GOOD: SQLAlchemy ORM (auto-parameterized)
# stmt = select(User).where(User.email == email)

# GOOD: SQLAlchemy text with bound params
# stmt = text("SELECT * FROM users WHERE email = :email")
# result = conn.execute(stmt, {"email": email})


# --- XSS prevention ---

def escape_html(text: str) -> str:
    """Escape HTML entities."""
    return html.escape(text, quote=True)

def sanitize_html(untrusted_html: str) -> str:
    """Allow safe subset of HTML."""
    return bleach.clean(
        untrusted_html,
        tags=['p', 'br', 'b', 'i', 'em', 'strong', 'a', 'ul', 'ol', 'li',
              'code', 'pre', 'blockquote', 'h1', 'h2', 'h3'],
        attributes={'a': ['href', 'title']},
        protocols=['http', 'https', 'mailto'],
        strip=True,
    )


# --- Path traversal prevention ---

def safe_file_path(base_dir: str, user_path: str) -> Path:
    """Resolve path safely within base directory."""
    base = Path(base_dir).resolve()
    # Normalize and resolve the user path
    target = (base / user_path).resolve()

    # Ensure it's within the base directory
    if not str(target).startswith(str(base)):
        raise ValueError("Path traversal detected")

    return target

# safe_file_path("/uploads", "../../etc/passwd")  # raises ValueError
# safe_file_path("/uploads", "images/photo.jpg")  # OK


# --- Safe deserialization ---

import json

# NEVER use pickle for untrusted data
# pickle.loads(untrusted_data)  # DANGEROUS: arbitrary code execution

# Use JSON (safe by default)
def safe_parse_json(data: str, max_size: int = 1_000_000) -> dict:
    if len(data) > max_size:
        raise ValueError(f"JSON too large: {len(data)} bytes")
    return json.loads(data)

# Use pydantic for validation after parsing
def parse_and_validate(raw: str, model_class):
    data = safe_parse_json(raw)
    return model_class.model_validate(data)


# --- Rate limit by input ---

def is_valid_search_query(query: str) -> bool:
    """Prevent expensive search patterns."""
    if len(query) > 200:
        return False
    if len(query) < 2:
        return False
    # Block regex-like patterns
    if re.search(r'[.*+?{}()\[\]\\|^$]', query):
        return False
    return True
```

Input validation rules:
1. **Parameterized queries** — never interpolate user input into SQL
2. **Pydantic validators** — validate structure, types, and content
3. **HTML sanitization** — bleach for user-generated HTML content
4. **Path resolution** — always resolve and check against base directory
5. **Never pickle untrusted data** — use JSON + Pydantic for deserialization'''
    ),
]
