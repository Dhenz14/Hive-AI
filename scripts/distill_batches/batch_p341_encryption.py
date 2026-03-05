"""Encryption: AES-GCM, RSA, key derivation (Argon2, scrypt), envelope encryption, TLS certificates."""

PAIRS = [
    (
        "security/aes-gcm-encryption",
        "How do I implement AES-GCM encryption and decryption in Python for secure data at rest?",
        '''AES-GCM (Galois/Counter Mode) provides authenticated encryption, meaning it ensures both confidentiality and integrity in a single operation. It is the standard choice for symmetric encryption in modern applications.

Here is a production-grade implementation:

```python
"""AES-256-GCM encryption with proper key management and authenticated data."""

import os
import struct
import base64
import secrets
import logging
from typing import Optional
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)

# Constants
AES_KEY_SIZE = 32    # 256 bits
NONCE_SIZE = 12      # 96 bits (recommended for GCM)
TAG_SIZE = 16        # 128-bit authentication tag (appended by AESGCM)
VERSION_BYTE = b"\\x01"  # Ciphertext format version for future upgrades


@dataclass
class EncryptedPayload:
    """Structured ciphertext with metadata for safe storage/transport."""
    version: int
    nonce: bytes
    ciphertext: bytes  # Includes GCM auth tag
    key_id: str        # Which key encrypted this (for key rotation)

    def serialize(self) -> bytes:
        """Serialize to a binary format: version(1) + key_id_len(2) + key_id + nonce(12) + ciphertext."""
        key_id_bytes = self.key_id.encode("utf-8")
        return (
            struct.pack("B", self.version)
            + struct.pack(">H", len(key_id_bytes))
            + key_id_bytes
            + self.nonce
            + self.ciphertext
        )

    @classmethod
    def deserialize(cls, data: bytes) -> "EncryptedPayload":
        """Deserialize binary format back to EncryptedPayload."""
        offset = 0
        version = struct.unpack_from("B", data, offset)[0]
        offset += 1

        key_id_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2

        key_id = data[offset:offset + key_id_len].decode("utf-8")
        offset += key_id_len

        nonce = data[offset:offset + NONCE_SIZE]
        offset += NONCE_SIZE

        ciphertext = data[offset:]

        return cls(version=version, nonce=nonce, ciphertext=ciphertext, key_id=key_id)

    def to_base64(self) -> str:
        """Encode serialized payload as URL-safe base64."""
        return base64.urlsafe_b64encode(self.serialize()).decode("ascii")

    @classmethod
    def from_base64(cls, encoded: str) -> "EncryptedPayload":
        """Decode from URL-safe base64."""
        return cls.deserialize(base64.urlsafe_b64decode(encoded))


class KeyStore:
    """Manages encryption keys with versioning for rotation.

    In production, replace with AWS KMS, HashiCorp Vault, or Azure Key Vault.
    """

    def __init__(self):
        self._keys: dict[str, bytes] = {}
        self._active_key_id: Optional[str] = None

    def add_key(self, key_id: str, key: bytes, make_active: bool = False):
        """Register an encryption key."""
        if len(key) != AES_KEY_SIZE:
            raise ValueError(f"Key must be {AES_KEY_SIZE} bytes, got {len(key)}")
        self._keys[key_id] = key
        if make_active or self._active_key_id is None:
            self._active_key_id = key_id
        logger.info("Registered key: %s (active=%s)", key_id, make_active)

    def get_key(self, key_id: str) -> bytes:
        """Retrieve a key by ID."""
        if key_id not in self._keys:
            raise KeyError(f"Unknown key ID: {key_id}")
        return self._keys[key_id]

    @property
    def active_key_id(self) -> str:
        if self._active_key_id is None:
            raise RuntimeError("No active encryption key configured")
        return self._active_key_id

    @property
    def active_key(self) -> bytes:
        return self.get_key(self.active_key_id)

    @staticmethod
    def generate_key() -> bytes:
        """Generate a cryptographically secure AES-256 key."""
        return secrets.token_bytes(AES_KEY_SIZE)


class AESGCMEncryptor:
    """High-level AES-256-GCM encryption with key rotation support."""

    def __init__(self, key_store: KeyStore):
        self.key_store = key_store

    def encrypt(
        self,
        plaintext: bytes,
        associated_data: Optional[bytes] = None,
    ) -> EncryptedPayload:
        """Encrypt data with AES-256-GCM.

        Args:
            plaintext: Data to encrypt.
            associated_data: Additional authenticated data (AAD) that is
                authenticated but NOT encrypted. Useful for binding ciphertext
                to context (e.g., user ID, record ID).
        """
        key_id = self.key_store.active_key_id
        key = self.key_store.active_key

        # Generate a unique nonce for every encryption operation
        # CRITICAL: Never reuse a nonce with the same key
        nonce = os.urandom(NONCE_SIZE)

        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)

        return EncryptedPayload(
            version=1,
            nonce=nonce,
            ciphertext=ciphertext,
            key_id=key_id,
        )

    def decrypt(
        self,
        payload: EncryptedPayload,
        associated_data: Optional[bytes] = None,
    ) -> bytes:
        """Decrypt an AES-256-GCM encrypted payload.

        Args:
            payload: The encrypted payload with metadata.
            associated_data: Must match what was provided during encryption.

        Raises:
            InvalidTag: If ciphertext was tampered with or AAD mismatch.
        """
        key = self.key_store.get_key(payload.key_id)
        aesgcm = AESGCM(key)

        try:
            plaintext = aesgcm.decrypt(payload.nonce, payload.ciphertext, associated_data)
        except InvalidTag:
            logger.warning(
                "Decryption failed: authentication tag mismatch (key_id=%s)",
                payload.key_id,
            )
            raise ValueError("Decryption failed: data integrity check failed")

        return plaintext

    def encrypt_string(self, text: str, associated_data: Optional[str] = None) -> str:
        """Convenience: encrypt a string and return base64."""
        aad = associated_data.encode("utf-8") if associated_data else None
        payload = self.encrypt(text.encode("utf-8"), aad)
        return payload.to_base64()

    def decrypt_string(self, encoded: str, associated_data: Optional[str] = None) -> str:
        """Convenience: decrypt a base64-encoded payload to string."""
        aad = associated_data.encode("utf-8") if associated_data else None
        payload = EncryptedPayload.from_base64(encoded)
        return self.decrypt(payload, aad).decode("utf-8")

    def re_encrypt(
        self,
        payload: EncryptedPayload,
        associated_data: Optional[bytes] = None,
    ) -> EncryptedPayload:
        """Re-encrypt data with the current active key (for key rotation)."""
        plaintext = self.decrypt(payload, associated_data)
        return self.encrypt(plaintext, associated_data)


# Usage example
def demo():
    # Setup key store
    store = KeyStore()
    store.add_key("key-2025-01", KeyStore.generate_key(), make_active=True)

    encryptor = AESGCMEncryptor(store)

    # Encrypt with AAD binding
    user_id = "user-42"
    ssn = "123-45-6789"

    encrypted = encryptor.encrypt_string(
        ssn,
        associated_data=user_id,  # Binds ciphertext to this user
    )
    print(f"Encrypted SSN: {encrypted}")

    # Decrypt (must provide same AAD)
    decrypted = encryptor.decrypt_string(encrypted, associated_data=user_id)
    assert decrypted == ssn

    # Attempting to decrypt with wrong AAD fails
    try:
        encryptor.decrypt_string(encrypted, associated_data="user-99")
    except ValueError as e:
        print(f"Tamper detected: {e}")

    # Key rotation: add new key, re-encrypt
    store.add_key("key-2026-01", KeyStore.generate_key(), make_active=True)
    payload = EncryptedPayload.from_base64(encrypted)
    rotated = encryptor.re_encrypt(payload, associated_data=user_id.encode())
    print(f"Re-encrypted with new key: {rotated.key_id}")


if __name__ == "__main__":
    demo()
```

AES-GCM security requirements:

| Requirement | Value | Why |
|-------------|-------|-----|
| Key size | 256 bits | Maximum security margin |
| Nonce size | 96 bits (12 bytes) | GCM recommended size |
| Nonce uniqueness | Must NEVER repeat per key | Nonce reuse completely breaks GCM security |
| Auth tag size | 128 bits | Full security; never truncate |
| Max data per key | 2^32 encryptions | After this, nonce collision probability is unacceptable |
| AAD | Optional but recommended | Binds ciphertext to context, prevents substitution attacks |

Key patterns:

- Always use a fresh random nonce for every encryption; nonce reuse with the same key is catastrophic
- Use authenticated associated data (AAD) to bind ciphertext to its context
- Store key IDs alongside ciphertext to support key rotation
- Version your ciphertext format for future algorithm upgrades
- Never store raw encryption keys in code; use a KMS or vault
- Implement re-encryption for key rotation without downtime
- Use the cryptography library, not PyCryptodome, for modern Python'''
    ),
    (
        "security/rsa-encryption-signing",
        "How do I use RSA for encryption, signing, and key management in Python?",
        '''RSA is used for asymmetric encryption (small data or key wrapping) and digital signatures. Modern best practice uses RSA-OAEP for encryption and RSA-PSS for signing. Here is a complete implementation:

```python
"""RSA encryption, signing, and key management with modern padding schemes."""

import base64
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding, utils
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, BestAvailableEncryption, NoEncryption,
)


class RSAKeyManager:
    """RSA key pair generation, storage, and loading."""

    @staticmethod
    def generate_key_pair(key_size: int = 4096) -> tuple[RSAPrivateKey, RSAPublicKey]:
        """Generate an RSA key pair.

        Args:
            key_size: 2048 minimum, 4096 recommended for long-term security.
        """
        if key_size < 2048:
            raise ValueError("Key size must be at least 2048 bits")

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )
        return private_key, private_key.public_key()

    @staticmethod
    def save_private_key(
        key: RSAPrivateKey,
        path: str,
        passphrase: Optional[str] = None,
    ):
        """Save private key to PEM file with optional encryption."""
        encryption = (
            BestAvailableEncryption(passphrase.encode())
            if passphrase
            else NoEncryption()
        )
        pem = key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )
        Path(path).write_bytes(pem)

    @staticmethod
    def load_private_key(
        path: str,
        passphrase: Optional[str] = None,
    ) -> RSAPrivateKey:
        """Load private key from PEM file."""
        pem = Path(path).read_bytes()
        pwd = passphrase.encode() if passphrase else None
        return serialization.load_pem_private_key(pem, password=pwd)

    @staticmethod
    def save_public_key(key: RSAPublicKey, path: str):
        """Save public key to PEM file."""
        pem = key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        )
        Path(path).write_bytes(pem)

    @staticmethod
    def load_public_key(path: str) -> RSAPublicKey:
        """Load public key from PEM file."""
        pem = Path(path).read_bytes()
        return serialization.load_pem_public_key(pem)

    @staticmethod
    def public_key_to_pem(key: RSAPublicKey) -> str:
        """Export public key as PEM string."""
        return key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")

    @staticmethod
    def public_key_fingerprint(key: RSAPublicKey) -> str:
        """Compute SHA-256 fingerprint of public key (for identification)."""
        der = key.public_bytes(
            encoding=Encoding.DER,
            format=PublicFormat.SubjectPublicKeyInfo,
        )
        digest = hashes.Hash(hashes.SHA256())
        digest.update(der)
        fingerprint = digest.finalize()
        return fingerprint.hex()


class RSAEncryptor:
    """RSA-OAEP encryption for small data and key wrapping."""

    def __init__(self, public_key: RSAPublicKey):
        self.public_key = public_key
        # Max plaintext size for RSA-OAEP with SHA-256:
        # key_size_bytes - 2 * hash_size - 2
        key_size_bytes = public_key.key_size // 8
        self.max_plaintext_size = key_size_bytes - 2 * 32 - 2

    def encrypt(self, plaintext: bytes, label: Optional[bytes] = None) -> bytes:
        """Encrypt data with RSA-OAEP (SHA-256).

        Note: Max plaintext size is limited by key size.
        For 4096-bit key: 446 bytes max.
        Use envelope encryption for larger data.
        """
        if len(plaintext) > self.max_plaintext_size:
            raise ValueError(
                f"Plaintext too large for RSA ({len(plaintext)} > {self.max_plaintext_size}). "
                f"Use envelope encryption for larger data."
            )

        return self.public_key.encrypt(
            plaintext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=label,
            ),
        )

    def encrypt_base64(self, plaintext: bytes) -> str:
        """Encrypt and return as base64."""
        return base64.b64encode(self.encrypt(plaintext)).decode("ascii")


class RSADecryptor:
    """RSA-OAEP decryption."""

    def __init__(self, private_key: RSAPrivateKey):
        self.private_key = private_key

    def decrypt(self, ciphertext: bytes, label: Optional[bytes] = None) -> bytes:
        """Decrypt RSA-OAEP ciphertext."""
        return self.private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=label,
            ),
        )

    def decrypt_base64(self, encoded: str) -> bytes:
        """Decrypt from base64."""
        return self.decrypt(base64.b64decode(encoded))


class RSASigner:
    """RSA-PSS digital signatures."""

    def __init__(self, private_key: RSAPrivateKey):
        self.private_key = private_key

    def sign(self, message: bytes) -> bytes:
        """Sign a message with RSA-PSS (SHA-256)."""
        return self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

    def sign_base64(self, message: bytes) -> str:
        """Sign and return base64-encoded signature."""
        return base64.b64encode(self.sign(message)).decode("ascii")

    def sign_digest(self, digest: bytes) -> bytes:
        """Sign a pre-computed SHA-256 digest."""
        return self.private_key.sign(
            digest,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            utils.Prehashed(hashes.SHA256()),
        )


class RSAVerifier:
    """RSA-PSS signature verification."""

    def __init__(self, public_key: RSAPublicKey):
        self.public_key = public_key

    def verify(self, message: bytes, signature: bytes) -> bool:
        """Verify an RSA-PSS signature. Returns True if valid."""
        try:
            self.public_key.verify(
                signature,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except InvalidSignature:
            return False

    def verify_base64(self, message: bytes, signature_b64: str) -> bool:
        """Verify a base64-encoded signature."""
        return self.verify(message, base64.b64decode(signature_b64))


# Usage example
def demo():
    # Generate keys
    private_key, public_key = RSAKeyManager.generate_key_pair(4096)
    fingerprint = RSAKeyManager.public_key_fingerprint(public_key)
    print(f"Key fingerprint: {fingerprint}")

    # Encryption
    encryptor = RSAEncryptor(public_key)
    decryptor = RSADecryptor(private_key)

    secret = b"AES-256 key material to wrap"
    ciphertext = encryptor.encrypt(secret)
    recovered = decryptor.decrypt(ciphertext)
    assert recovered == secret

    # Signing
    signer = RSASigner(private_key)
    verifier = RSAVerifier(public_key)

    message = b"Transfer $1000 to account 12345"
    signature = signer.sign(message)

    assert verifier.verify(message, signature) is True
    assert verifier.verify(b"Transfer $9999 to account 12345", signature) is False

    # Save/load keys
    RSAKeyManager.save_private_key(private_key, "/tmp/key.pem", passphrase="secret")
    RSAKeyManager.save_public_key(public_key, "/tmp/key.pub")

    loaded_priv = RSAKeyManager.load_private_key("/tmp/key.pem", passphrase="secret")
    loaded_pub = RSAKeyManager.load_public_key("/tmp/key.pub")


if __name__ == "__main__":
    demo()
```

RSA algorithm comparison:

| Purpose | Algorithm | Padding | When to Use |
|---------|-----------|---------|-------------|
| Encryption | RSA-OAEP | SHA-256 + MGF1 | Encrypting small data or wrapping symmetric keys |
| Signing | RSA-PSS | SHA-256 + MGF1 | Digital signatures with probabilistic security |
| Legacy encryption | PKCS1v15 | Deterministic | NEVER use for new systems (padding oracle attacks) |
| Legacy signing | PKCS1v15 | Deterministic | Only for legacy compatibility |

Key patterns:

- Use RSA-OAEP for encryption and RSA-PSS for signatures; never PKCS1v15 for new code
- Use 4096-bit keys for long-term security; 2048 is the minimum
- RSA can only encrypt data smaller than the key minus padding overhead
- Use envelope encryption for data larger than a few hundred bytes
- Always protect private keys with a passphrase when stored on disk
- Use key fingerprints (SHA-256 of DER public key) for key identification
- Prefer ECDSA or Ed25519 for new signing use cases (smaller keys, faster)'''
    ),
    (
        "security/key-derivation-argon2-scrypt",
        "How do I properly hash passwords and derive encryption keys using Argon2 and scrypt?",
        '''Key derivation functions (KDFs) transform passwords or other low-entropy inputs into cryptographic keys. Argon2id is the current gold standard for password hashing, while scrypt remains a solid alternative. Both are designed to be memory-hard to resist GPU and ASIC attacks.

Here is a comprehensive implementation:

```python
"""Password hashing and key derivation with Argon2id and scrypt."""

import os
import time
import hmac
import base64
import hashlib
import secrets
import logging
from dataclasses import dataclass
from typing import Optional

import argon2
from argon2 import PasswordHasher, Type
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)


# ─── Argon2id Password Hashing ──────────────────────────────────────

class Argon2PasswordHasher:
    """Production-grade Argon2id password hasher.

    Argon2id is the recommended variant: it combines Argon2i (resistance to
    side-channel attacks) and Argon2d (resistance to GPU cracking).
    """

    def __init__(
        self,
        time_cost: int = 3,         # Number of iterations
        memory_cost: int = 65536,   # 64 MiB
        parallelism: int = 4,       # Number of threads
        hash_len: int = 32,         # Output hash length in bytes
        salt_len: int = 16,         # Salt length in bytes
        type: Type = Type.ID,       # Argon2id
    ):
        self.hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
            type=type,
        )

    def hash(self, password: str) -> str:
        """Hash a password. Returns the full Argon2 encoded string.

        The encoded string contains the algorithm parameters, salt, and hash,
        so you do not need to store them separately.
        Example: $argon2id$v=19$m=65536,t=3,p=4$salt$hash
        """
        return self.hasher.hash(password)

    def verify(self, stored_hash: str, password: str) -> bool:
        """Verify a password against a stored hash.

        Returns True if the password matches.
        Raises argon2.exceptions.VerifyMismatchError if it does not.
        """
        try:
            return self.hasher.verify(stored_hash, password)
        except argon2.exceptions.VerifyMismatchError:
            return False
        except argon2.exceptions.InvalidHashError:
            logger.error("Invalid hash format encountered")
            return False

    def needs_rehash(self, stored_hash: str) -> bool:
        """Check if a hash was created with outdated parameters.

        Call this after successful verification to upgrade hashes
        when you increase security parameters.
        """
        return self.hasher.check_needs_rehash(stored_hash)


class PasswordService:
    """High-level password management with upgrade support."""

    def __init__(self):
        self.hasher = Argon2PasswordHasher()

    def hash_password(self, password: str) -> str:
        """Hash a new password."""
        self._validate_password_policy(password)
        return self.hasher.hash(password)

    def verify_password(self, stored_hash: str, password: str) -> tuple[bool, bool]:
        """Verify password and check if rehash is needed.

        Returns:
            (is_valid, needs_rehash) tuple
        """
        is_valid = self.hasher.verify(stored_hash, password)
        needs_rehash = False

        if is_valid:
            needs_rehash = self.hasher.needs_rehash(stored_hash)
            if needs_rehash:
                logger.info("Password hash needs upgrade to current parameters")

        return is_valid, needs_rehash

    def _validate_password_policy(self, password: str):
        """Enforce minimum password requirements."""
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(password) > 128:
            raise ValueError("Password must not exceed 128 characters")
        # Check against common passwords list in production
        # Check for sufficient entropy/complexity as needed


# ─── scrypt Key Derivation ──────────────────────────────────────────

class ScryptKeyDeriver:
    """scrypt-based key derivation for encryption keys.

    scrypt is memory-hard and suitable for deriving encryption keys
    from passwords. Use when Argon2 is not available.
    """

    def __init__(
        self,
        salt_length: int = 32,
        key_length: int = 32,  # AES-256
        n: int = 2**17,        # CPU/memory cost (131072)
        r: int = 8,            # Block size
        p: int = 1,            # Parallelism
    ):
        self.salt_length = salt_length
        self.key_length = key_length
        self.n = n
        self.r = r
        self.p = p

    def derive_key(self, password: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
        """Derive an encryption key from a password.

        Args:
            password: The password to derive from.
            salt: Optional salt; generated if not provided.

        Returns:
            (derived_key, salt) tuple. Store the salt alongside encrypted data.
        """
        if salt is None:
            salt = os.urandom(self.salt_length)

        kdf = Scrypt(
            salt=salt,
            length=self.key_length,
            n=self.n,
            r=self.r,
            p=self.p,
        )
        key = kdf.derive(password.encode("utf-8"))
        return key, salt

    def verify_key(self, password: str, salt: bytes, expected_key: bytes) -> bool:
        """Verify that a password produces the expected key."""
        kdf = Scrypt(
            salt=salt,
            length=self.key_length,
            n=self.n,
            r=self.r,
            p=self.p,
        )
        try:
            kdf.verify(password.encode("utf-8"), expected_key)
            return True
        except Exception:
            return False


# ─── HKDF for Key Expansion ─────────────────────────────────────────

class KeyExpander:
    """HKDF-based key expansion for deriving multiple keys from one master.

    Use HKDF when you already have high-entropy key material and need
    to derive multiple purpose-specific keys.
    """

    def __init__(self, master_key: bytes):
        self.master_key = master_key

    def derive(
        self,
        purpose: str,
        key_length: int = 32,
        context: bytes = b"",
    ) -> bytes:
        """Derive a purpose-specific key from the master key.

        Args:
            purpose: String label for the key purpose (e.g., "encryption", "signing").
            key_length: Desired output key length.
            context: Additional context to bind key to specific usage.
        """
        info = purpose.encode("utf-8") + b"\\x00" + context

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=key_length,
            salt=None,  # Optional; the master key should already be high-entropy
            info=info,
        )
        return hkdf.derive(self.master_key)

    def derive_key_pair(self, purpose: str) -> tuple[bytes, bytes]:
        """Derive separate encryption and HMAC keys for a purpose."""
        enc_key = self.derive(f"{purpose}:encryption")
        mac_key = self.derive(f"{purpose}:authentication")
        return enc_key, mac_key


# ─── Benchmarking and Tuning ─────────────────────────────────────────

def benchmark_argon2(target_ms: int = 500) -> dict:
    """Tune Argon2 parameters for your hardware.

    Goal: hashing should take 250-1000ms for interactive logins,
    1-5 seconds for high-security scenarios.
    """
    test_password = "benchmark_password_123"

    configs = [
        {"time_cost": 2, "memory_cost": 32768, "parallelism": 2},
        {"time_cost": 3, "memory_cost": 65536, "parallelism": 4},
        {"time_cost": 4, "memory_cost": 65536, "parallelism": 4},
        {"time_cost": 3, "memory_cost": 131072, "parallelism": 4},
        {"time_cost": 4, "memory_cost": 131072, "parallelism": 8},
    ]

    results = []
    for config in configs:
        hasher = PasswordHasher(**config, type=Type.ID)
        start = time.perf_counter()
        for _ in range(3):
            hasher.hash(test_password)
        elapsed_ms = ((time.perf_counter() - start) / 3) * 1000

        results.append({
            **config,
            "elapsed_ms": round(elapsed_ms, 1),
            "suitable": abs(elapsed_ms - target_ms) < target_ms * 0.5,
        })
        print(
            f"  t={config['time_cost']} m={config['memory_cost']//1024}MiB "
            f"p={config['parallelism']}: {elapsed_ms:.0f}ms"
        )

    return min(results, key=lambda r: abs(r["elapsed_ms"] - target_ms))


# Usage
def demo():
    # Password hashing
    svc = PasswordService()
    hashed = svc.hash_password("my-secure-password-42")
    print(f"Hash: {hashed}")

    is_valid, needs_rehash = svc.verify_password(hashed, "my-secure-password-42")
    print(f"Valid: {is_valid}, Needs rehash: {needs_rehash}")

    # Key derivation from password
    deriver = ScryptKeyDeriver()
    key, salt = deriver.derive_key("user-passphrase")
    print(f"Derived key: {key.hex()[:32]}...")

    # Key expansion
    master = secrets.token_bytes(32)
    expander = KeyExpander(master)
    enc_key = expander.derive("database-encryption")
    api_key = expander.derive("api-signing")
    print(f"Encryption key: {enc_key.hex()[:32]}...")
    print(f"API signing key: {api_key.hex()[:32]}...")


if __name__ == "__main__":
    demo()
```

KDF comparison:

| Algorithm | Best For | Memory-Hard | Parameters |
|-----------|----------|-------------|------------|
| Argon2id | Password hashing | Yes | time, memory, parallelism |
| scrypt | Password-based key derivation | Yes | N, r, p |
| HKDF | Key expansion from high-entropy input | No | salt, info |
| bcrypt | Legacy password hashing | No (fixed 4KB) | cost factor |
| PBKDF2 | Legacy/FIPS compliance only | No | iterations, salt |

Key patterns:

- Use Argon2id for password hashing, not bcrypt or PBKDF2 for new systems
- Tune Argon2 parameters to take 250-1000ms on your production hardware
- The encoded hash string contains all parameters, so no separate storage needed
- Implement needs_rehash() to upgrade hashes when you increase parameters
- Use scrypt or Argon2 when deriving encryption keys from passwords
- Use HKDF only for high-entropy inputs, never directly for passwords
- Derive separate keys for separate purposes from the same master key
- Cap password length at 128 chars to prevent DoS via very long inputs'''
    ),
    (
        "security/envelope-encryption",
        "How do I implement envelope encryption for securing large datasets with key rotation support?",
        '''Envelope encryption is the standard pattern used by cloud KMS services (AWS KMS, Google Cloud KMS, Azure Key Vault). You encrypt data with a unique data encryption key (DEK), then encrypt the DEK with a key encryption key (KEK). This allows you to rotate the KEK without re-encrypting all data.

```python
"""Envelope encryption with DEK/KEK hierarchy and key rotation."""

import os
import json
import time
import struct
import hashlib
import secrets
import logging
from typing import Optional, Protocol
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

logger = logging.getLogger(__name__)

DEK_SIZE = 32  # AES-256
NONCE_SIZE = 12


class KEKProvider(Protocol):
    """Interface for key encryption key providers."""

    def encrypt_dek(self, dek: bytes, key_id: str) -> bytes:
        """Encrypt a DEK with the KEK identified by key_id."""
        ...

    def decrypt_dek(self, encrypted_dek: bytes, key_id: str) -> bytes:
        """Decrypt a DEK using the KEK identified by key_id."""
        ...

    @property
    def active_key_id(self) -> str:
        """The currently active KEK ID for new encryptions."""
        ...


class LocalKEKProvider:
    """Local KEK provider using AES-256-GCM for DEK wrapping.

    In production, replace with AWS KMS, Google Cloud KMS, etc.
    """

    def __init__(self):
        self._keys: dict[str, bytes] = {}
        self._active_id: Optional[str] = None

    def add_key(self, key_id: str, key: Optional[bytes] = None, active: bool = False):
        """Register a KEK. Generate if not provided."""
        if key is None:
            key = secrets.token_bytes(32)
        self._keys[key_id] = key
        if active or self._active_id is None:
            self._active_id = key_id
        logger.info("KEK registered: %s (active=%s)", key_id, active)

    @property
    def active_key_id(self) -> str:
        if not self._active_id:
            raise RuntimeError("No active KEK")
        return self._active_id

    def encrypt_dek(self, dek: bytes, key_id: str) -> bytes:
        kek = self._keys[key_id]
        nonce = os.urandom(NONCE_SIZE)
        aesgcm = AESGCM(kek)
        encrypted = aesgcm.encrypt(nonce, dek, key_id.encode())
        return nonce + encrypted  # nonce || ciphertext+tag

    def decrypt_dek(self, encrypted_dek: bytes, key_id: str) -> bytes:
        kek = self._keys[key_id]
        nonce = encrypted_dek[:NONCE_SIZE]
        ciphertext = encrypted_dek[NONCE_SIZE:]
        aesgcm = AESGCM(kek)
        return aesgcm.decrypt(nonce, ciphertext, key_id.encode())


@dataclass
class EncryptedEnvelope:
    """Complete envelope: encrypted DEK + encrypted data + metadata."""
    version: int
    kek_id: str
    encrypted_dek: bytes
    nonce: bytes
    ciphertext: bytes
    created_at: float = field(default_factory=time.time)

    def to_bytes(self) -> bytes:
        """Serialize envelope to binary format."""
        kek_id_bytes = self.kek_id.encode()
        parts = [
            struct.pack("B", self.version),
            struct.pack(">d", self.created_at),
            struct.pack(">H", len(kek_id_bytes)),
            kek_id_bytes,
            struct.pack(">H", len(self.encrypted_dek)),
            self.encrypted_dek,
            self.nonce,
            self.ciphertext,
        ]
        return b"".join(parts)

    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedEnvelope":
        """Deserialize envelope from binary format."""
        offset = 0

        version = struct.unpack_from("B", data, offset)[0]
        offset += 1

        created_at = struct.unpack_from(">d", data, offset)[0]
        offset += 8

        kek_id_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        kek_id = data[offset:offset + kek_id_len].decode()
        offset += kek_id_len

        edek_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        encrypted_dek = data[offset:offset + edek_len]
        offset += edek_len

        nonce = data[offset:offset + NONCE_SIZE]
        offset += NONCE_SIZE

        ciphertext = data[offset:]

        return cls(
            version=version,
            kek_id=kek_id,
            encrypted_dek=encrypted_dek,
            nonce=nonce,
            ciphertext=ciphertext,
            created_at=created_at,
        )


class EnvelopeEncryption:
    """Envelope encryption engine with key hierarchy management."""

    def __init__(self, kek_provider: KEKProvider):
        self.kek_provider = kek_provider

    def encrypt(
        self,
        plaintext: bytes,
        associated_data: Optional[bytes] = None,
    ) -> EncryptedEnvelope:
        """Encrypt data using envelope encryption.

        1. Generate a random DEK
        2. Encrypt the data with the DEK (AES-256-GCM)
        3. Encrypt the DEK with the active KEK
        4. Return envelope containing encrypted DEK + encrypted data
        """
        # Step 1: Generate unique DEK for this encryption
        dek = secrets.token_bytes(DEK_SIZE)
        nonce = os.urandom(NONCE_SIZE)

        # Step 2: Encrypt data with DEK
        aesgcm = AESGCM(dek)
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)

        # Step 3: Encrypt DEK with KEK
        kek_id = self.kek_provider.active_key_id
        encrypted_dek = self.kek_provider.encrypt_dek(dek, kek_id)

        # Step 4: Securely wipe the plaintext DEK from memory
        # (Python does not guarantee this, but we overwrite the reference)
        dek = b"\\x00" * DEK_SIZE

        return EncryptedEnvelope(
            version=1,
            kek_id=kek_id,
            encrypted_dek=encrypted_dek,
            nonce=nonce,
            ciphertext=ciphertext,
        )

    def decrypt(
        self,
        envelope: EncryptedEnvelope,
        associated_data: Optional[bytes] = None,
    ) -> bytes:
        """Decrypt data from an envelope.

        1. Decrypt the DEK using the KEK identified in the envelope
        2. Decrypt the data with the DEK
        """
        # Step 1: Decrypt DEK
        dek = self.kek_provider.decrypt_dek(
            envelope.encrypted_dek,
            envelope.kek_id,
        )

        # Step 2: Decrypt data
        aesgcm = AESGCM(dek)
        plaintext = aesgcm.decrypt(envelope.nonce, envelope.ciphertext, associated_data)

        # Wipe DEK
        dek = b"\\x00" * DEK_SIZE

        return plaintext

    def rotate_kek(
        self,
        envelope: EncryptedEnvelope,
    ) -> EncryptedEnvelope:
        """Re-wrap the DEK with the current active KEK.

        This rotates the KEK without re-encrypting the data.
        Much faster than full re-encryption for large datasets.
        """
        old_kek_id = envelope.kek_id
        new_kek_id = self.kek_provider.active_key_id

        if old_kek_id == new_kek_id:
            return envelope  # Already using the active key

        # Decrypt DEK with old KEK
        dek = self.kek_provider.decrypt_dek(envelope.encrypted_dek, old_kek_id)

        # Re-encrypt DEK with new KEK
        new_encrypted_dek = self.kek_provider.encrypt_dek(dek, new_kek_id)

        # Wipe DEK
        dek = b"\\x00" * DEK_SIZE

        logger.info(
            "Rotated KEK from %s to %s for envelope",
            old_kek_id, new_kek_id,
        )

        return EncryptedEnvelope(
            version=envelope.version,
            kek_id=new_kek_id,
            encrypted_dek=new_encrypted_dek,
            nonce=envelope.nonce,
            ciphertext=envelope.ciphertext,
            created_at=envelope.created_at,
        )


class EncryptedFileStore:
    """File storage with envelope encryption."""

    def __init__(self, envelope_enc: EnvelopeEncryption, base_dir: str):
        self.enc = envelope_enc
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, data: bytes, metadata: Optional[str] = None):
        """Write encrypted file."""
        aad = metadata.encode() if metadata else None
        envelope = self.enc.encrypt(data, associated_data=aad)
        path = self.base_dir / f"{name}.enc"
        path.write_bytes(envelope.to_bytes())
        logger.info("Wrote encrypted file: %s (kek=%s)", name, envelope.kek_id)

    def read(self, name: str, metadata: Optional[str] = None) -> bytes:
        """Read and decrypt file."""
        aad = metadata.encode() if metadata else None
        path = self.base_dir / f"{name}.enc"
        envelope = EncryptedEnvelope.from_bytes(path.read_bytes())
        return self.enc.decrypt(envelope, associated_data=aad)

    def rotate_all(self) -> int:
        """Re-wrap all files with the current active KEK."""
        count = 0
        for path in self.base_dir.glob("*.enc"):
            envelope = EncryptedEnvelope.from_bytes(path.read_bytes())
            rotated = self.enc.rotate_kek(envelope)
            if rotated is not envelope:
                path.write_bytes(rotated.to_bytes())
                count += 1
        logger.info("Rotated %d files to new KEK", count)
        return count


# Usage
def demo():
    # Setup KEK provider
    kek_provider = LocalKEKProvider()
    kek_provider.add_key("kek-2025-01", active=True)

    enc = EnvelopeEncryption(kek_provider)

    # Encrypt data
    data = b"Sensitive patient medical record..." * 100
    envelope = enc.encrypt(data, associated_data=b"patient:12345")

    # Decrypt
    recovered = enc.decrypt(envelope, associated_data=b"patient:12345")
    assert recovered == data

    # KEK rotation (fast: only re-wraps the DEK)
    kek_provider.add_key("kek-2026-01", active=True)
    rotated = enc.rotate_kek(envelope)
    assert rotated.kek_id == "kek-2026-01"

    # Data is still accessible
    recovered2 = enc.decrypt(rotated, associated_data=b"patient:12345")
    assert recovered2 == data

    print("Envelope encryption demo complete")


if __name__ == "__main__":
    demo()
```

Envelope encryption key hierarchy:

| Layer | Key | Stored | Rotated | Protects |
|-------|-----|--------|---------|----------|
| L0: Master Key | Root of trust | HSM/KMS only | Rarely | KEKs |
| L1: KEK | Key Encryption Key | KMS or vault | Periodically | DEKs |
| L2: DEK | Data Encryption Key | Encrypted (with KEK) | Per-record | Actual data |

Key patterns:

- Generate a unique DEK per record/file; never reuse DEKs across records
- KEK rotation only re-wraps DEKs (milliseconds), not re-encrypts data (expensive)
- Use AAD to bind encrypted data to its context (e.g., record ID, table name)
- In production, use cloud KMS for KEK management (AWS KMS, GCP KMS, etc.)
- Version your envelope format for future algorithm upgrades
- Store the KEK ID in the envelope so you know which key to use for decryption
- Wipe DEK from memory after use (best effort in Python)
- Implement bulk rotate_all for periodic KEK rotation maintenance'''
    ),
    (
        "security/tls-certificate-management",
        "How do I programmatically generate and manage TLS certificates for internal services?",
        '''For internal services, you often need to create a private CA and issue certificates for mTLS, service mesh communication, or development environments. Here is a complete certificate management system:

```python
"""TLS certificate generation and management for internal PKI."""

import ipaddress
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption, BestAvailableEncryption,
)

logger = logging.getLogger(__name__)


class CertificateAuthority:
    """Internal Certificate Authority for issuing TLS certificates."""

    def __init__(
        self,
        ca_cert: x509.Certificate,
        ca_key,
        cert_dir: str = "./certs",
    ):
        self.ca_cert = ca_cert
        self.ca_key = ca_key
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create_root_ca(
        cls,
        common_name: str = "Internal Root CA",
        organization: str = "MyCompany",
        validity_days: int = 3650,  # 10 years
        key_type: str = "ec",       # "ec" (P-256) or "rsa" (4096)
        cert_dir: str = "./certs",
    ) -> "CertificateAuthority":
        """Create a new self-signed root CA certificate."""
        # Generate CA key
        if key_type == "ec":
            ca_key = ec.generate_private_key(ec.SECP256R1())
            sign_algo = hashes.SHA256()
        else:
            ca_key = rsa.generate_private_key(
                public_exponent=65537, key_size=4096,
            )
            sign_algo = hashes.SHA256()

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        now = datetime.now(timezone.utc)
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
                critical=False,
            )
            .sign(ca_key, sign_algo)
        )

        ca = cls(ca_cert, ca_key, cert_dir)
        ca.save_ca()
        logger.info("Created root CA: %s", common_name)
        return ca

    def issue_server_certificate(
        self,
        common_name: str,
        san_dns: list[str] | None = None,
        san_ips: list[str] | None = None,
        validity_days: int = 365,
        key_type: str = "ec",
    ) -> tuple[x509.Certificate, any]:
        """Issue a server TLS certificate signed by this CA."""
        san_dns = san_dns or [common_name]
        san_ips = san_ips or []

        # Generate server key
        if key_type == "ec":
            server_key = ec.generate_private_key(ec.SECP256R1())
        else:
            server_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048,
            )

        # Build Subject Alternative Names
        san_entries = [x509.DNSName(dns) for dns in san_dns]
        san_entries.extend(
            x509.IPAddress(ipaddress.ip_address(ip)) for ip in san_ips
        )

        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ]))
            .issuer_name(self.ca_cert.subject)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.SERVER_AUTH,
                ]),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    self.ca_key.public_key()
                ),
                critical=False,
            )
            .sign(self.ca_key, hashes.SHA256())
        )

        # Save certificate and key
        self._save_cert(common_name, cert, server_key)
        logger.info("Issued server cert: %s (SANs: %s)", common_name, san_dns)
        return cert, server_key

    def issue_client_certificate(
        self,
        common_name: str,
        organization: str = "",
        validity_days: int = 365,
    ) -> tuple[x509.Certificate, any]:
        """Issue a client certificate for mTLS authentication."""
        client_key = ec.generate_private_key(ec.SECP256R1())

        name_attrs = [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
        if organization:
            name_attrs.insert(0, x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization))

        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name(name_attrs))
            .issuer_name(self.ca_cert.subject)
            .public_key(client_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False,
            )
            .sign(self.ca_key, hashes.SHA256())
        )

        self._save_cert(f"client-{common_name}", cert, client_key)
        logger.info("Issued client cert: %s", common_name)
        return cert, client_key

    def save_ca(self):
        """Save CA certificate and key to disk."""
        ca_cert_path = self.cert_dir / "ca.crt"
        ca_key_path = self.cert_dir / "ca.key"

        ca_cert_path.write_bytes(
            self.ca_cert.public_bytes(Encoding.PEM)
        )
        ca_key_path.write_bytes(
            self.ca_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        )
        # Restrict key file permissions
        ca_key_path.chmod(0o600)

    def _save_cert(self, name: str, cert: x509.Certificate, key):
        """Save certificate and private key to PEM files."""
        cert_path = self.cert_dir / f"{name}.crt"
        key_path = self.cert_dir / f"{name}.key"

        cert_path.write_bytes(cert.public_bytes(Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        )
        key_path.chmod(0o600)

    @classmethod
    def load(cls, cert_dir: str = "./certs") -> "CertificateAuthority":
        """Load existing CA from disk."""
        cert_dir = Path(cert_dir)
        ca_cert = x509.load_pem_x509_certificate(
            (cert_dir / "ca.crt").read_bytes()
        )
        ca_key = serialization.load_pem_private_key(
            (cert_dir / "ca.key").read_bytes(), password=None,
        )
        return cls(ca_cert, ca_key, str(cert_dir))


def verify_certificate(cert: x509.Certificate, ca_cert: x509.Certificate) -> dict:
    """Verify a certificate against the CA and return info."""
    now = datetime.now(timezone.utc)
    info = {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "serial": hex(cert.serial_number),
        "not_before": cert.not_valid_before_utc.isoformat(),
        "not_after": cert.not_valid_after_utc.isoformat(),
        "is_expired": now > cert.not_valid_after_utc,
        "days_remaining": (cert.not_valid_after_utc - now).days,
    }

    # Check SANs
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        info["dns_names"] = san.value.get_values_for_type(x509.DNSName)
        info["ip_addresses"] = [
            str(ip) for ip in san.value.get_values_for_type(x509.IPAddress)
        ]
    except x509.ExtensionNotFound:
        info["dns_names"] = []
        info["ip_addresses"] = []

    # Verify signature
    try:
        ca_cert.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            ec.ECDSA(hashes.SHA256()) if isinstance(ca_cert.public_key(), ec.EllipticCurvePublicKey)
            else cert.signature_hash_algorithm,
        )
        info["signature_valid"] = True
    except Exception:
        info["signature_valid"] = False

    return info


# Usage
def demo():
    # Create internal CA
    ca = CertificateAuthority.create_root_ca(
        common_name="MyCompany Internal CA",
        organization="MyCompany",
    )

    # Issue server certificates
    server_cert, server_key = ca.issue_server_certificate(
        common_name="api.internal",
        san_dns=["api.internal", "*.api.internal", "localhost"],
        san_ips=["127.0.0.1", "10.0.0.1"],
        validity_days=365,
    )

    # Issue client certificate for mTLS
    client_cert, client_key = ca.issue_client_certificate(
        common_name="service-a",
        organization="Platform Team",
    )

    # Verify
    info = verify_certificate(server_cert, ca.ca_cert)
    print(f"Server cert: {info['subject']}")
    print(f"SANs: {info['dns_names']}")
    print(f"Valid: {info['signature_valid']}, Expires in {info['days_remaining']} days")


if __name__ == "__main__":
    demo()
```

Certificate types and their key usage:

| Certificate Type | Key Usage | Extended Key Usage | Use Case |
|-----------------|-----------|-------------------|----------|
| Root CA | keyCertSign, cRLSign | (none) | Signs intermediate CAs or end-entity certs |
| Server TLS | digitalSignature, keyEncipherment | serverAuth | HTTPS endpoints, gRPC servers |
| Client mTLS | digitalSignature | clientAuth | Service-to-service authentication |
| Code Signing | digitalSignature | codeSigning | Signing binaries and packages |

Key patterns:

- Use ECDSA P-256 for new certificates (smaller, faster than RSA)
- Always include Subject Alternative Names (SANs); CN is deprecated for host matching
- Set BasicConstraints ca=False on all end-entity certificates
- Restrict key file permissions to 0o600 (owner read/write only)
- Use short validity periods (90-365 days) for end-entity certificates
- Implement certificate rotation before expiration (at 2/3 of lifetime)
- Store CA private key in an HSM or vault in production
- Include both DNS names and IP addresses in server SANs'''
    ),
]
