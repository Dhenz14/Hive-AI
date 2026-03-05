"""Security deep dive — OWASP, cryptography, secure coding, threat modeling."""

PAIRS = [
    (
        "security/owasp-top10-prevention",
        "Show practical prevention techniques for OWASP Top 10 vulnerabilities in Python web applications with code examples.",
        '''Preventing OWASP Top 10 in Python web apps:

```python
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel, validator, Field
import hashlib
import hmac
import secrets
import re
import html
from typing import Annotated

app = FastAPI()

# --- A01: Broken Access Control ---

def check_resource_access(user_id: str, resource_owner_id: str):
    """Prevent IDOR — always verify ownership."""
    if user_id != resource_owner_id:
        raise HTTPException(status_code=403, detail="Access denied")

@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str, current_user = Depends(get_current_user)):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404)
    check_resource_access(current_user.id, doc.owner_id)  # Always check!
    return doc

# --- A02: Cryptographic Failures ---

import bcrypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64
import os

def hash_password(password: str) -> str:
    """Use bcrypt with automatic salting."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def derive_encryption_key(password: str, salt: bytes) -> bytes:
    """Derive encryption key from password with PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,  # OWASP 2024 recommendation
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def encrypt_sensitive_field(data: str, key: bytes) -> str:
    """Encrypt PII/sensitive data at rest."""
    f = Fernet(key)
    return f.encrypt(data.encode()).decode()

# --- A03: Injection ---

# SQL Injection prevention — parameterized queries ALWAYS
async def get_user_safe(username: str):
    # GOOD: parameterized
    query = "SELECT * FROM users WHERE username = $1"
    return await db.fetchrow(query, username)

    # BAD: string formatting — NEVER do this
    # query = f"SELECT * FROM users WHERE username = '{username}'"

# Command injection prevention
import subprocess

def safe_command(filename: str):
    # Validate input
    if not re.match(r'^[a-zA-Z0-9._-]+$', filename):
        raise ValueError("Invalid filename")
    # Use list form (no shell)
    result = subprocess.run(
        ['file', '--mime-type', filename],
        capture_output=True, text=True,
        timeout=10,
    )
    return result.stdout

# --- A04: Insecure Design ---

class TransferRequest(BaseModel):
    """Input validation at the boundary."""
    to_account: str = Field(..., regex=r'^[A-Z]{2}\\d{10,30}$')
    amount: float = Field(..., gt=0, le=50000)
    currency: str = Field(..., regex=r'^[A-Z]{3}$')

    @validator('amount')
    def validate_amount(cls, v):
        if round(v, 2) != v:
            raise ValueError('Amount must have at most 2 decimal places')
        return v

# Rate limiting
from fastapi_limiter.depends import RateLimiter

@app.post("/api/transfer",
          dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def transfer(req: TransferRequest, user = Depends(get_current_user)):
    # Business logic checks
    if req.amount > user.daily_limit:
        raise HTTPException(400, "Exceeds daily limit")
    # Additional verification for large amounts
    if req.amount > 10000:
        await require_2fa_verification(user)
    return await process_transfer(req)

# --- A05: Security Misconfiguration ---

# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    # Remove server identification
    response.headers.pop("server", None)
    return response

# --- A07: Authentication Failures ---

def generate_session_token() -> str:
    """Cryptographically secure session token."""
    return secrets.token_urlsafe(32)  # 256 bits of entropy

def constant_time_compare(a: str, b: str) -> bool:
    """Prevent timing attacks on token comparison."""
    return hmac.compare_digest(a.encode(), b.encode())

# --- A08: Software and Data Integrity ---

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook came from trusted source."""
    expected = hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

# --- CSRF protection ---

def generate_csrf_token(session_id: str, secret: str) -> str:
    return hmac.new(
        secret.encode(),
        session_id.encode(),
        hashlib.sha256,
    ).hexdigest()
```

Security checklist:
1. **Authentication** — bcrypt/argon2, MFA, session management
2. **Authorization** — check ownership on every request
3. **Input validation** — allowlist patterns, parameterized queries
4. **Output encoding** — context-aware (HTML, URL, JS)
5. **Security headers** — CSP, HSTS, X-Frame-Options
6. **Secrets** — env vars or vault, never in code
7. **Dependencies** — audit regularly, pin versions
8. **Logging** — security events, never log secrets'''
    ),
    (
        "security/cryptography-practical",
        "Show practical cryptography in Python: symmetric encryption, asymmetric keys, digital signatures, and secure key management.",
        '''Practical cryptography patterns for developers:

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.x509 import CertificateBuilder, NameOID
import os
import json
import base64
from datetime import datetime, timedelta, timezone

# --- Symmetric Encryption (AES-256-GCM) ---

class SymmetricEncryption:
    """AES-256-GCM authenticated encryption."""

    def __init__(self, key: bytes = None):
        self.key = key or AESGCM.generate_key(bit_length=256)

    def encrypt(self, plaintext: bytes, associated_data: bytes = None) -> bytes:
        """Encrypt with authentication. Returns nonce + ciphertext."""
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext  # Prepend nonce

    def decrypt(self, data: bytes, associated_data: bytes = None) -> bytes:
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(self.key)
        return aesgcm.decrypt(nonce, ciphertext, associated_data)

# Usage:
cipher = SymmetricEncryption()
encrypted = cipher.encrypt(b"sensitive data", b"context")
decrypted = cipher.decrypt(encrypted, b"context")

# --- Key Derivation (HKDF for multiple keys from one secret) ---

def derive_keys(master_secret: bytes, context: str, num_keys: int = 2) -> list[bytes]:
    """Derive multiple purpose-specific keys from one master key."""
    keys = []
    for i in range(num_keys):
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"{context}-key-{i}".encode(),
        )
        keys.append(hkdf.derive(master_secret))
    return keys

# --- Asymmetric Encryption (RSA) ---

def generate_rsa_keypair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )
    return private_key, private_key.public_key()

def rsa_encrypt(public_key, plaintext: bytes) -> bytes:
    return public_key.encrypt(
        plaintext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

def rsa_decrypt(private_key, ciphertext: bytes) -> bytes:
    return private_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

# --- Digital Signatures (Ed25519 / ECDSA) ---

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def create_signing_keypair():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key

def sign_message(private_key, message: bytes) -> bytes:
    return private_key.sign(message)

def verify_signature(public_key, message: bytes, signature: bytes) -> bool:
    try:
        public_key.verify(signature, message)
        return True
    except Exception:
        return False

# --- Envelope Encryption (for large data) ---

class EnvelopeEncryption:
    """Encrypt data with a data key, then encrypt the data key with a master key."""

    def __init__(self, master_key: bytes):
        self.master = SymmetricEncryption(master_key)

    def encrypt(self, plaintext: bytes) -> dict:
        # Generate random data encryption key (DEK)
        dek = AESGCM.generate_key(bit_length=256)
        data_cipher = SymmetricEncryption(dek)

        # Encrypt data with DEK
        encrypted_data = data_cipher.encrypt(plaintext)

        # Encrypt DEK with master key
        encrypted_dek = self.master.encrypt(dek)

        return {
            "encrypted_data": base64.b64encode(encrypted_data).decode(),
            "encrypted_dek": base64.b64encode(encrypted_dek).decode(),
        }

    def decrypt(self, envelope: dict) -> bytes:
        # Decrypt DEK with master key
        encrypted_dek = base64.b64decode(envelope["encrypted_dek"])
        dek = self.master.decrypt(encrypted_dek)

        # Decrypt data with DEK
        encrypted_data = base64.b64decode(envelope["encrypted_data"])
        data_cipher = SymmetricEncryption(dek)
        return data_cipher.decrypt(encrypted_data)

# --- Secure Key Serialization ---

def serialize_private_key(private_key, password: bytes = None) -> bytes:
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password else serialization.NoEncryption()
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )

def serialize_public_key(public_key) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
```

Algorithm selection guide:
- **Symmetric**: AES-256-GCM (general) or ChaCha20-Poly1305 (no hardware AES)
- **Key derivation**: HKDF (from key material) or Argon2id (from passwords)
- **Asymmetric encryption**: RSA-4096-OAEP or ECIES
- **Digital signatures**: Ed25519 (fast) or ECDSA P-256 (compatibility)
- **Hashing**: SHA-256 (general), BLAKE2b (speed), SHA-3 (NIST)
- **Password hashing**: Argon2id > bcrypt > PBKDF2'''
    ),
    (
        "security/threat-modeling",
        "Explain threat modeling methodologies: STRIDE, attack trees, and how to systematically identify and prioritize security risks in software systems.",
        '''Systematic threat modeling for software systems:

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

# --- STRIDE Threat Categories ---

class StrideCategory(Enum):
    SPOOFING = "Spoofing identity"
    TAMPERING = "Tampering with data"
    REPUDIATION = "Repudiation of actions"
    INFORMATION_DISCLOSURE = "Information disclosure"
    DENIAL_OF_SERVICE = "Denial of service"
    ELEVATION_OF_PRIVILEGE = "Elevation of privilege"

class Severity(Enum):
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1

@dataclass
class Threat:
    id: str
    category: StrideCategory
    description: str
    affected_component: str
    severity: Severity
    likelihood: Severity
    mitigations: list[str] = field(default_factory=list)
    status: str = "identified"  # identified, mitigated, accepted, transferred

    @property
    def risk_score(self) -> int:
        return self.severity.value * self.likelihood.value

@dataclass
class DataFlow:
    source: str
    destination: str
    data_type: str
    protocol: str
    crosses_trust_boundary: bool = False

# --- Threat Model for a Web Application ---

def model_web_application():
    """Example: E-commerce application threat model."""

    # Step 1: Identify components and data flows
    components = [
        "Browser (client)",
        "CDN / WAF",
        "API Gateway",
        "Auth Service",
        "Order Service",
        "Payment Service (external)",
        "PostgreSQL Database",
        "Redis Cache",
        "S3 Object Storage",
    ]

    data_flows = [
        DataFlow("Browser", "API Gateway", "HTTP requests", "HTTPS",
                 crosses_trust_boundary=True),
        DataFlow("API Gateway", "Auth Service", "JWT tokens", "gRPC"),
        DataFlow("API Gateway", "Order Service", "Order data", "gRPC"),
        DataFlow("Order Service", "Payment Service", "Payment details", "HTTPS",
                 crosses_trust_boundary=True),
        DataFlow("Order Service", "PostgreSQL", "SQL queries", "TLS"),
        DataFlow("Order Service", "Redis", "Session data", "TLS"),
    ]

    # Step 2: Apply STRIDE to each data flow crossing trust boundaries
    threats = [
        Threat(
            id="T001",
            category=StrideCategory.SPOOFING,
            description="Attacker steals JWT and impersonates user",
            affected_component="Auth Service",
            severity=Severity.CRITICAL,
            likelihood=Severity.MEDIUM,
            mitigations=[
                "Short JWT expiry (15 min) with refresh tokens",
                "Bind tokens to client fingerprint",
                "Token revocation via Redis blacklist",
                "Detect concurrent sessions from different IPs",
            ],
        ),
        Threat(
            id="T002",
            category=StrideCategory.TAMPERING,
            description="SQL injection modifies order prices in database",
            affected_component="Order Service → PostgreSQL",
            severity=Severity.CRITICAL,
            likelihood=Severity.LOW,
            mitigations=[
                "Parameterized queries (ORM with SQLAlchemy)",
                "Input validation with Pydantic models",
                "Database user with minimal privileges",
                "WAF SQL injection rules",
            ],
        ),
        Threat(
            id="T003",
            category=StrideCategory.INFORMATION_DISCLOSURE,
            description="Payment card data leaked from logs or error messages",
            affected_component="Order Service → Payment Service",
            severity=Severity.CRITICAL,
            likelihood=Severity.MEDIUM,
            mitigations=[
                "Never log card numbers (PCI DSS requirement)",
                "Tokenize payment data via payment processor",
                "Structured logging with sensitive field filtering",
                "Error messages never expose internal details",
            ],
        ),
        Threat(
            id="T004",
            category=StrideCategory.DENIAL_OF_SERVICE,
            description="API flood overwhelms order processing",
            affected_component="API Gateway",
            severity=Severity.HIGH,
            likelihood=Severity.HIGH,
            mitigations=[
                "Rate limiting per user and per IP",
                "API Gateway throttling (Kong/Envoy)",
                "CDN/WAF DDoS protection (Cloudflare/AWS Shield)",
                "Circuit breaker on downstream services",
                "Autoscaling with max instance limits",
            ],
        ),
        Threat(
            id="T005",
            category=StrideCategory.ELEVATION_OF_PRIVILEGE,
            description="Regular user accesses admin API endpoints",
            affected_component="API Gateway → Order Service",
            severity=Severity.CRITICAL,
            likelihood=Severity.MEDIUM,
            mitigations=[
                "RBAC with role claims in JWT",
                "Authorization check on every endpoint (not just auth)",
                "Admin endpoints on separate internal network",
                "Audit logging for all admin actions",
            ],
        ),
        Threat(
            id="T006",
            category=StrideCategory.REPUDIATION,
            description="User disputes they placed an order",
            affected_component="Order Service",
            severity=Severity.MEDIUM,
            likelihood=Severity.MEDIUM,
            mitigations=[
                "Immutable audit log with timestamps",
                "Order confirmation emails with transaction ID",
                "IP address and device fingerprint logging",
                "Digital signature on order confirmation",
            ],
        ),
    ]

    # Step 3: Prioritize by risk score
    sorted_threats = sorted(threats, key=lambda t: t.risk_score, reverse=True)

    print("\\nThreat Priority List:")
    print("-" * 70)
    for t in sorted_threats:
        status = "MITIGATED" if t.mitigations else "OPEN"
        print(f"  [{t.id}] Risk={t.risk_score:2d} | {t.category.value}")
        print(f"         {t.description}")
        print(f"         Component: {t.affected_component}")
        if t.mitigations:
            print(f"         Mitigations: {len(t.mitigations)} defined")
        print()

    return threats

# --- Attack Tree (decompose complex threats) ---

@dataclass
class AttackNode:
    description: str
    is_or: bool = True  # OR = any child succeeds; AND = all children needed
    cost: Optional[int] = None       # Estimated attacker cost
    difficulty: Optional[str] = None  # low/medium/high
    children: list["AttackNode"] = field(default_factory=list)

def build_account_takeover_tree() -> AttackNode:
    return AttackNode("Take over user account", is_or=True, children=[
        AttackNode("Steal credentials", is_or=True, children=[
            AttackNode("Phishing email", cost=100, difficulty="low"),
            AttackNode("Credential stuffing (leaked DB)", cost=50, difficulty="low"),
            AttackNode("Keylogger malware", cost=500, difficulty="medium"),
        ]),
        AttackNode("Bypass authentication", is_or=True, children=[
            AttackNode("Exploit password reset flow", cost=0, difficulty="medium"),
            AttackNode("Session fixation", cost=0, difficulty="medium"),
            AttackNode("JWT algorithm confusion (none/HS256)", cost=0, difficulty="high"),
        ]),
        AttackNode("Social engineering support staff", is_or=False, children=[
            AttackNode("Gather personal info from social media", cost=0, difficulty="low"),
            AttackNode("Call support with convincing story", cost=0, difficulty="medium"),
        ]),
    ])
```

Threat modeling process:
1. **Decompose** — identify components, data flows, trust boundaries
2. **Identify threats** — apply STRIDE to each flow crossing boundaries
3. **Rate** — severity x likelihood = risk score
4. **Mitigate** — design countermeasures for high-risk threats
5. **Validate** — verify mitigations through security testing
6. **Iterate** — update model when architecture changes'''
    ),
]
