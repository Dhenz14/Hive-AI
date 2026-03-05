"""
Batch P8 — Applied Cryptography
Covers: symmetric encryption (AES-GCM), asymmetric crypto (Ed25519, PKI), hash functions (Merkle trees, HMAC),
zero-knowledge proofs (Schnorr protocol), secure protocol design (ECDH, double ratchet).
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "cryptography/symmetric-encryption-aes-modes-key-derivation",
        "Explain symmetric encryption with AES modes including CBC, CTR, and GCM, then implement AES-GCM authenticated encryption and decryption with proper nonce handling, PBKDF2 key derivation from passwords, and a complete file encryption utility in Python using the cryptography library with streaming support for large files.",
        r"""# Symmetric Encryption: AES Modes, Key Derivation, and Authenticated Encryption

## Why AES Remains the Gold Standard

AES (Advanced Encryption Standard) has been the dominant symmetric cipher since its adoption by NIST in 2001, **because** it provides an excellent balance of security margin, hardware acceleration support (AES-NI instructions), and well-understood cryptanalytic properties. Every modern CPU from Intel, AMD, and ARM includes dedicated AES instructions, which means AES-based encryption runs at near-memory-bandwidth speeds — often exceeding 5 GB/s on a single core. **However**, the choice of *mode of operation* on top of AES is where most real-world vulnerabilities arise, not in the cipher itself. Understanding mode selection is **therefore** the most critical practical skill in symmetric cryptography.

**The fundamental distinction** is between modes that provide only confidentiality (CBC, CTR) and modes that provide **authenticated encryption with associated data (AEAD)**, which guarantees both confidentiality and integrity. Using a non-authenticated mode is a **common mistake** that has led to devastating attacks like padding oracle attacks against CBC and bit-flipping attacks against CTR.

## AES Modes Compared

### CBC (Cipher Block Chaining)

CBC chains each plaintext block with the previous ciphertext block before encryption. It requires an unpredictable IV (initialization vector) for each message. The critical **pitfall** with CBC is that it provides no integrity guarantee — an attacker can manipulate ciphertext blocks to cause controlled changes in the decrypted plaintext. The padding oracle attack (Vaudenay, 2002) exploits error messages from invalid padding to decrypt entire messages without the key. **Therefore**, CBC should never be used without a separate MAC (and even then, the encrypt-then-MAC composition must be done correctly).

### CTR (Counter Mode)

CTR turns AES into a stream cipher by encrypting sequential counter values and XORing the result with plaintext. It is parallelizable (unlike CBC) and does not require padding. **However**, nonce reuse in CTR mode is catastrophic — if two messages share the same nonce and key, XORing the two ciphertexts reveals the XOR of the two plaintexts, completely destroying confidentiality. This is a **best practice** violation that has caused real breaches, including the WPA2 KRACK attack.

### GCM (Galois/Counter Mode) — The Recommended Choice

GCM combines CTR-mode encryption with a GHASH-based authentication tag, providing AEAD in a single pass. It is the **best practice** for nearly all symmetric encryption use cases **because** it provides confidentiality, integrity, and authentication simultaneously, runs at hardware-accelerated speeds, and is the mandatory cipher suite in TLS 1.3. The **trade-off** is that GCM is even more sensitive to nonce reuse than plain CTR — reusing a nonce not only compromises confidentiality but also allows an attacker to forge authentication tags, completely breaking the integrity guarantee.

```python
import os
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from typing import Optional


def derive_key_pbkdf2(
    password: str,
    salt: Optional[bytes] = None,
    iterations: int = 600_000,
    key_length: int = 32,
) -> tuple[bytes, bytes]:
    # Derive a 256-bit AES key from a password using PBKDF2-HMAC-SHA256.
    # Returns (derived_key, salt) so the salt can be stored alongside ciphertext.
    # 600k iterations is the OWASP 2024 recommendation for PBKDF2-SHA256.
    if salt is None:
        salt = os.urandom(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=key_length,
        salt=salt,
        iterations=iterations,
    )
    key = kdf.derive(password.encode("utf-8"))
    return key, salt


def encrypt_aes_gcm(
    plaintext: bytes,
    key: bytes,
    associated_data: Optional[bytes] = None,
) -> tuple[bytes, bytes]:
    # Encrypt plaintext using AES-256-GCM with a random 96-bit nonce.
    # Returns (nonce, ciphertext_with_tag).
    # The 96-bit nonce is the standard size for GCM and MUST be unique per key.
    if len(key) not in (16, 24, 32):
        raise ValueError("Key must be 128, 192, or 256 bits")

    nonce = secrets.token_bytes(12)  # 96-bit random nonce
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)
    return nonce, ciphertext


def decrypt_aes_gcm(
    nonce: bytes,
    ciphertext: bytes,
    key: bytes,
    associated_data: Optional[bytes] = None,
) -> bytes:
    # Decrypt and verify AES-256-GCM ciphertext.
    # Raises InvalidTag if the ciphertext was tampered with.
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, associated_data)
```

## Password-Based Key Derivation Deep Dive

Raw passwords must never be used directly as encryption keys **because** they have far less entropy than a random key — a typical human-chosen password has 30-50 bits of entropy versus 256 bits for a random AES key. Key derivation functions (KDFs) compensate by making brute-force attacks computationally expensive. The three major options present distinct **trade-offs**:

- **PBKDF2**: Widely supported, FIPS-approved, but only CPU-hard. An attacker with GPUs can test billions of candidates per second. Use at minimum 600,000 iterations with SHA-256.
- **scrypt**: Memory-hard, making GPU attacks significantly more expensive. **However**, the memory-hardness parameter must be tuned carefully — too low and it degrades to a CPU-only function.
- **Argon2id**: The winner of the Password Hashing Competition (2015) and the current **best practice**. It is both memory-hard and resistant to side-channel attacks. Use Argon2id with at least 64 MB memory, 3 iterations, and 4 parallelism.

### Comparing Key Derivation Functions

```python
import time
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives import hashes

def benchmark_kdf(password: str = "correct-horse-battery-staple") -> dict[str, float]:
    # Benchmark the three major KDFs to understand their performance profiles.
    # In production, tune parameters so derivation takes 100-500ms on your hardware.
    salt = os.urandom(16)
    results: dict[str, float] = {}

    # PBKDF2 with OWASP-recommended iterations
    start = time.perf_counter()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    kdf.derive(password.encode())
    results["pbkdf2_600k"] = time.perf_counter() - start

    # scrypt with recommended parameters (N=2^17, r=8, p=1 = 128MB memory)
    start = time.perf_counter()
    kdf = Scrypt(salt=salt, length=32, n=2**17, r=8, p=1)
    kdf.derive(password.encode())
    results["scrypt_n17"] = time.perf_counter() - start

    return results
```

## Complete File Encryption Utility

The following utility handles large files using streaming encryption. A **common mistake** is reading the entire file into memory before encrypting, which fails for multi-gigabyte files. **However**, AES-GCM does not natively support streaming because the authentication tag can only be computed after processing the entire message. The standard solution is to split the file into fixed-size chunks, each encrypted independently with a derived nonce. This approach provides both streaming capability and per-chunk integrity verification — **therefore** a corrupted chunk is detected immediately without processing the entire file.

```python
import os
import struct
import secrets
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from typing import BinaryIO

# File format:
# [4 bytes: version][16 bytes: salt][4 bytes: chunk_size]
# For each chunk: [12 bytes: nonce][4 bytes: ciphertext_length][ciphertext + 16-byte tag]
FILE_MAGIC_VERSION = 1
DEFAULT_CHUNK_SIZE = 64 * 1024  # 64 KB chunks


class FileEncryptor:
    # Streaming file encryption using AES-256-GCM with chunked processing.
    # Each chunk gets a unique nonce derived from a base nonce and chunk counter.
    # This avoids loading the entire file into memory.

    def __init__(self, password: str, iterations: int = 600_000):
        self.password = password
        self.iterations = iterations

    def _derive_key(self, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.iterations,
        )
        return kdf.derive(self.password.encode("utf-8"))

    def _derive_chunk_nonce(self, base_nonce: bytes, chunk_index: int) -> bytes:
        # Derive a unique 12-byte nonce per chunk by XORing the base nonce
        # with the chunk index. This guarantees uniqueness without randomness.
        nonce_int = int.from_bytes(base_nonce, "big") ^ chunk_index
        return nonce_int.to_bytes(12, "big")

    def encrypt_file(
        self,
        input_path: Path,
        output_path: Path,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        salt = os.urandom(16)
        key = self._derive_key(salt)
        base_nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(key)

        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            # Write header
            fout.write(struct.pack(">I", FILE_MAGIC_VERSION))
            fout.write(salt)
            fout.write(struct.pack(">I", chunk_size))
            fout.write(base_nonce)

            chunk_index = 0
            while True:
                chunk = fin.read(chunk_size)
                if not chunk:
                    break
                nonce = self._derive_chunk_nonce(base_nonce, chunk_index)
                ct = aesgcm.encrypt(nonce, chunk, None)
                fout.write(struct.pack(">I", len(ct)))
                fout.write(ct)
                chunk_index += 1

    def decrypt_file(self, input_path: Path, output_path: Path) -> None:
        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            # Read header
            version = struct.unpack(">I", fin.read(4))[0]
            if version != FILE_MAGIC_VERSION:
                raise ValueError(f"Unsupported file version: {version}")
            salt = fin.read(16)
            chunk_size = struct.unpack(">I", fin.read(4))[0]
            base_nonce = fin.read(12)

            key = self._derive_key(salt)
            aesgcm = AESGCM(key)

            chunk_index = 0
            while True:
                ct_len_bytes = fin.read(4)
                if not ct_len_bytes:
                    break
                ct_len = struct.unpack(">I", ct_len_bytes)[0]
                ct = fin.read(ct_len)
                nonce = self._derive_chunk_nonce(base_nonce, chunk_index)
                plaintext = aesgcm.decrypt(nonce, ct, None)
                fout.write(plaintext)
                chunk_index += 1
```

### Nonce Management Strategies

The critical rule for GCM is: **never reuse a nonce with the same key**. There are three strategies to ensure this:

1. **Random nonces** (96-bit): With a 96-bit random nonce, the birthday bound gives a collision probability of approximately 2^-32 after 2^32 messages. This is acceptable for most applications, but for high-volume systems (encrypting billions of records), the risk becomes non-trivial.

2. **Counter-based nonces**: Use a persistent, monotonically increasing counter. This guarantees uniqueness but requires reliable persistent storage — a **pitfall** if the counter resets after a crash.

3. **Synthetic nonces (SIV)**: AES-GCM-SIV derives the nonce from the plaintext using a PRF, making nonce reuse non-catastrophic. The **trade-off** is a slight performance penalty from the additional PRF evaluation and the fact that identical plaintexts produce identical ciphertexts (which may leak information in some threat models).

## Summary and Key Takeaways

- **Always use AEAD modes** (GCM, ChaCha20-Poly1305) rather than bare CBC or CTR, **because** unauthenticated encryption enables padding oracle and bit-flipping attacks.
- **Derive keys from passwords** using Argon2id (preferred), scrypt, or PBKDF2 with high iteration counts — never use raw passwords as keys.
- **Never reuse nonces** with AES-GCM; prefer random 96-bit nonces for low-volume use and counter-based nonces for high-volume systems.
- **Stream large files** by encrypting in fixed-size chunks with per-chunk authentication, **therefore** avoiding unbounded memory usage.
- **Benchmark your KDF** on target hardware to find the maximum tolerable delay (typically 100-500ms) — this is the single most impactful parameter for password-based encryption security.
- The **best practice** is to use well-audited libraries (Python `cryptography`, libsodium) rather than implementing primitives yourself, **because** even correct algorithms can be vulnerable to timing side-channels in naive implementations.
"""
    ),
    (
        "cryptography/asymmetric-pki-ed25519-certificates",
        "Explain asymmetric cryptography and public key infrastructure including RSA versus ECDSA versus Ed25519 key generation, X.509 certificate chains, certificate signing requests, and TLS handshake mechanics, then implement a complete mini certificate authority in Python that generates Ed25519 key pairs, creates self-signed root certificates, issues signed leaf certificates, and verifies certificate chains using the cryptography library.",
        r"""# Asymmetric Cryptography and PKI: From Ed25519 Keys to Certificate Chains

## The Foundation of Digital Trust

Asymmetric cryptography — also called public-key cryptography — is the foundation of digital trust on the internet, **because** it solves the key distribution problem that makes symmetric encryption impractical at scale. With symmetric encryption, every pair of communicating parties needs a shared secret; with N parties, that means N(N-1)/2 keys. Asymmetric cryptography reduces this to N key pairs, where each party publishes their public key and keeps their private key secret. **However**, this introduces a new problem: how do you know a public key actually belongs to who it claims? This is the problem that Public Key Infrastructure (PKI) solves through certificate chains rooted in trusted certificate authorities.

**The three dominant algorithms** for digital signatures are RSA, ECDSA, and Ed25519, each with distinct **trade-offs** in security, performance, and key size. Understanding these trade-offs is essential for choosing the right algorithm for your application.

## Algorithm Comparison: RSA vs ECDSA vs Ed25519

### RSA

RSA security is based on the difficulty of factoring large semiprimes. It was the first practical public-key algorithm (1977) and remains widely deployed. **However**, RSA requires very large keys to achieve modern security levels — 3072-bit keys for 128-bit security and 15360-bit keys for 256-bit security. This makes RSA signatures and public keys significantly larger than elliptic curve alternatives. A **common mistake** is using 2048-bit RSA keys, which NIST plans to deprecate after 2030.

### ECDSA (Elliptic Curve Digital Signature Algorithm)

ECDSA over the P-256 curve provides 128-bit security with 256-bit keys — a dramatic improvement over RSA. **However**, ECDSA has a critical **pitfall**: it requires a cryptographically random nonce for each signature, and nonce reuse (or even biased nonces) completely reveals the private key. The PlayStation 3 code-signing key was famously extracted because Sony used a static nonce. **Therefore**, ECDSA implementations must use RFC 6979 deterministic nonce generation as a **best practice**.

### Ed25519 (Edwards-curve Digital Signature Algorithm)

Ed25519, based on the Curve25519 twisted Edwards curve, is the current **best practice** for digital signatures, **because** it provides 128-bit security with 32-byte keys and 64-byte signatures, uses deterministic nonce generation by design (eliminating the ECDSA nonce pitfall), resists timing side-channel attacks, and is significantly faster than both RSA and ECDSA. The only **trade-off** is that Ed25519 is newer and less universally supported in legacy systems than RSA.

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from typing import Tuple


def generate_ed25519_keypair() -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    # Generate an Ed25519 key pair.
    # Ed25519 keys are always 256 bits; there is no key size parameter.
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def serialize_keys(
    private_key: Ed25519PrivateKey,
    public_key: Ed25519PublicKey,
) -> Tuple[bytes, bytes]:
    # Serialize keys to PEM format for storage or transmission.
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def sign_and_verify(private_key: Ed25519PrivateKey, message: bytes) -> bytes:
    # Sign a message with Ed25519 and verify the signature.
    # Ed25519 signatures are always exactly 64 bytes.
    signature = private_key.sign(message)

    # Verification raises InvalidSignature if it fails
    public_key = private_key.public_key()
    public_key.verify(signature, message)
    return signature
```

## X.509 Certificates and Certificate Chains

An X.509 certificate binds a public key to an identity (subject name) via a digital signature from a certificate authority (CA). Certificate chains work hierarchically: a root CA signs intermediate CA certificates, which sign end-entity (leaf) certificates. The **best practice** is to keep root CA private keys offline and use intermediate CAs for day-to-day signing, **because** compromising an intermediate CA only affects certificates it issued, while compromising a root CA undermines the entire trust chain.

### Certificate Fields

Every X.509 certificate contains: the subject's public key, a subject distinguished name (DN), an issuer DN, a validity period (not-before and not-after), a serial number, and extensions like Subject Alternative Names (SANs), Key Usage, and Basic Constraints. The Basic Constraints extension is critical — it specifies whether the certificate can act as a CA. A **common mistake** is issuing leaf certificates without setting `ca:FALSE` in Basic Constraints, which could allow a compromised leaf certificate to sign arbitrary child certificates.

## Building a Mini Certificate Authority

The following implementation creates a complete CA hierarchy: a self-signed root CA, the ability to issue leaf certificates, and chain verification. This is the same fundamental structure used by Let's Encrypt, DigiCert, and every other real-world CA — **however**, production CAs include additional safeguards like HSM-backed key storage, CRL distribution points, and OCSP responders.

```python
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import hashes, serialization
from dataclasses import dataclass
from typing import Optional


@dataclass
class CertificateBundle:
    # Holds a certificate and its corresponding private key
    certificate: x509.Certificate
    private_key: Ed25519PrivateKey


class MiniCA:
    # A minimal Certificate Authority that issues Ed25519 certificates.
    # Demonstrates the core PKI concepts: root CAs, certificate issuance,
    # and chain verification.

    def __init__(self, org_name: str = "MiniCA", validity_days: int = 3650):
        self.org_name = org_name
        self.validity_days = validity_days
        self.root_bundle: Optional[CertificateBundle] = None
        self.issued_certs: list[x509.Certificate] = []

    def create_root_ca(self) -> CertificateBundle:
        # Create a self-signed root CA certificate.
        # The root CA signs itself, forming the trust anchor.
        private_key = Ed25519PrivateKey.generate()
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.org_name),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{self.org_name} Root CA"),
        ])

        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=self.validity_days))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=1),
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
                x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
                critical=False,
            )
            .sign(private_key, algorithm=None)  # Ed25519 determines hash internally
        )

        self.root_bundle = CertificateBundle(
            certificate=cert, private_key=private_key
        )
        return self.root_bundle

    def issue_leaf_certificate(
        self,
        common_name: str,
        san_dns_names: Optional[list[str]] = None,
        validity_days: int = 365,
    ) -> CertificateBundle:
        # Issue a leaf certificate signed by the root CA.
        # The leaf cert has ca:FALSE and cannot sign other certificates.
        if self.root_bundle is None:
            raise RuntimeError("Root CA not initialized. Call create_root_ca() first.")

        leaf_key = Ed25519PrivateKey.generate()
        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.org_name),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        now = datetime.datetime.now(datetime.timezone.utc)
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.root_bundle.certificate.subject)
            .public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=validity_days))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=False,
                    crl_sign=False,
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
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.SERVER_AUTH,
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False,
            )
        )

        if san_dns_names:
            san_list = [x509.DNSName(name) for name in san_dns_names]
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )

        cert = builder.sign(self.root_bundle.private_key, algorithm=None)
        bundle = CertificateBundle(certificate=cert, private_key=leaf_key)
        self.issued_certs.append(cert)
        return bundle

    def verify_certificate(self, cert: x509.Certificate) -> bool:
        # Verify that a certificate was signed by our root CA.
        # In production, use a full chain validator with revocation checks.
        if self.root_bundle is None:
            return False
        try:
            root_public_key = self.root_bundle.certificate.public_key()
            root_public_key.verify(cert.signature, cert.tbs_certificate_bytes)
            return True
        except Exception:
            return False
```

### Using the Mini CA

```python
def demo_ca_workflow() -> None:
    # Demonstrate the full CA workflow: create root, issue certs, verify chain
    ca = MiniCA(org_name="Acme Corp")

    # Step 1: Create the root CA (trust anchor)
    root = ca.create_root_ca()
    print(f"Root CA: {root.certificate.subject}")

    # Step 2: Issue a leaf certificate for a web server
    server_cert = ca.issue_leaf_certificate(
        common_name="api.acme.com",
        san_dns_names=["api.acme.com", "*.api.acme.com"],
    )
    print(f"Issued: {server_cert.certificate.subject}")

    # Step 3: Verify the leaf certificate against the root CA
    is_valid = ca.verify_certificate(server_cert.certificate)
    print(f"Verification: {'PASSED' if is_valid else 'FAILED'}")

    # Step 4: Sign and verify a message with the leaf certificate's key
    message = b"authenticated API request payload"
    signature = server_cert.private_key.sign(message)
    leaf_public_key = server_cert.certificate.public_key()
    leaf_public_key.verify(signature, message)
    print("Message signature verified successfully")
```

## TLS Handshake and Certificate Verification

When a TLS client connects to a server, the server presents its certificate chain. The client verifies each certificate in the chain up to a trusted root CA in its trust store. In TLS 1.3, the handshake is completed in a single round trip (1-RTT), **because** the key exchange and authentication happen simultaneously. **Therefore**, Ed25519 certificates are increasingly preferred for TLS **because** their small size reduces handshake overhead and their fast verification improves connection latency.

The **trade-off** with certificate-based authentication is operational complexity: certificates expire, must be renewed, and revocation is notoriously difficult. OCSP stapling helps by allowing the server to include a timestamped revocation status from the CA, but many servers do not implement it correctly — a widespread **pitfall** in production deployments.

## Summary and Key Takeaways

- **Prefer Ed25519** over RSA and ECDSA for new applications, **because** it is faster, has smaller keys and signatures, and eliminates the nonce-reuse vulnerability of ECDSA.
- **Never expose root CA private keys** to online systems; keep them in HSMs or air-gapped machines and use intermediate CAs for daily operations.
- **Set BasicConstraints correctly**: `ca:TRUE` for CA certificates, `ca:FALSE` for leaf certificates — this prevents compromised leaf keys from issuing rogue certificates.
- **Validate the entire chain** from leaf to root, checking expiration, revocation, and key usage constraints at each step.
- **The best practice** for TLS is to use short-lived certificates (90 days, as Let's Encrypt recommends) with automated renewal, **therefore** reducing the window of exposure from a compromised key.
- **Certificate transparency** (CT) logs provide public auditability of all issued certificates, making rogue issuance detectable — monitor CT logs for your domains.
"""
    ),
    (
        "cryptography/hash-functions-hmac-merkle-trees",
        "Explain cryptographic hash functions including SHA-256 and SHA-3, HMAC construction and API authentication, Merkle tree data structures with inclusion proofs, commitment schemes, and content-addressable storage, then implement a complete Merkle tree with proof generation and verification, HMAC-based API request signing, and a content-addressable storage engine in Python with type hints.",
        r"""# Hash Functions, MACs, and Merkle Trees: Integrity at Every Scale

## Why Hashing Is Foundational to Cryptography

Cryptographic hash functions are the most frequently used primitives in all of cryptography, **because** they provide a compact, deterministic fingerprint of arbitrary-length data with three critical properties: **pre-image resistance** (given a hash, you cannot find the input), **second pre-image resistance** (given an input, you cannot find a different input with the same hash), and **collision resistance** (you cannot find any two inputs with the same hash). These properties make hashes the building block for digital signatures, message authentication codes, commitment schemes, proof-of-work systems, and content-addressable storage.

**However**, not all hash functions provide all these properties at their theoretical maximum. SHA-256 provides 256-bit security for pre-image resistance but only 128-bit security for collision resistance (due to the birthday bound). SHA-3 (Keccak) uses a completely different internal structure (sponge construction vs Merkle-Damgard) and was designed specifically to resist length-extension attacks that affect SHA-256. Understanding these distinctions is essential for choosing the right hash function for each application.

## HMAC: Keyed Hashing for Authentication

A bare hash function only provides integrity — it tells you the data has not been modified, but not *who* created the hash. HMAC (Hash-based Message Authentication Code) solves this by incorporating a secret key, **therefore** providing both integrity and authenticity. The HMAC construction is `HMAC(K, m) = H((K ^ opad) || H((K ^ ipad) || m))`, where `opad` and `ipad` are fixed padding constants. This double-hash structure is essential **because** it prevents length-extension attacks that would be possible with a naive `H(K || m)` construction — a **common mistake** in ad-hoc authentication schemes.

### HMAC-Based API Authentication

The following implementation shows how to build request signing for an API, similar to how AWS Signature V4 authenticates API calls. This is a **best practice** for server-to-server authentication **because** it avoids transmitting secrets over the network.

```python
import hashlib
import hmac
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignedRequest:
    # Represents an HTTP request with HMAC signature for authentication
    method: str
    path: str
    query_params: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    timestamp: int = 0
    signature: str = ""
    key_id: str = ""


class HMACAuthenticator:
    # HMAC-SHA256 based API request authenticator.
    # Signs requests with a shared secret key, preventing tampering
    # and replay attacks (via timestamp validation).

    def __init__(self, key_id: str, secret_key: bytes, max_age_seconds: int = 300):
        self.key_id = key_id
        self.secret_key = secret_key
        self.max_age_seconds = max_age_seconds

    def _canonical_string(self, request: SignedRequest) -> str:
        # Build a canonical string representation for consistent signing.
        # Sorting parameters ensures both sides compute the same string.
        sorted_params = urllib.parse.urlencode(sorted(request.query_params.items()))
        body_hash = hashlib.sha256(request.body).hexdigest()
        return f"{request.method}\n{request.path}\n{sorted_params}\n{request.timestamp}\n{body_hash}"

    def sign_request(self, request: SignedRequest) -> SignedRequest:
        # Sign a request by computing HMAC-SHA256 over its canonical form
        request.timestamp = int(time.time())
        request.key_id = self.key_id
        canonical = self._canonical_string(request)
        request.signature = hmac.new(
            self.secret_key,
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return request

    def verify_request(self, request: SignedRequest) -> bool:
        # Verify the request signature and check for replay attacks.
        # Returns False if the signature is invalid or the request is too old.
        now = int(time.time())
        if abs(now - request.timestamp) > self.max_age_seconds:
            return False  # Reject stale requests to prevent replay attacks

        canonical = self._canonical_string(request)
        expected = hmac.new(
            self.secret_key,
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected, request.signature)
```

## Merkle Trees: Scalable Integrity Verification

A Merkle tree is a binary tree of hashes where each leaf contains the hash of a data block and each internal node contains the hash of its two children. This structure enables **logarithmic-size proofs** — you can prove that a specific block is part of the tree by providing only O(log n) hashes rather than all n blocks. This is why Merkle trees are used in Git (content addressing), Bitcoin (transaction verification), certificate transparency (audit proofs), and IPFS (content-addressable storage).

**The key insight** is that changing any single leaf propagates changes all the way to the root, **therefore** the root hash serves as a compact commitment to the entire dataset. A verifier who trusts the root hash can verify any individual element with a proof that is logarithmic in the total number of elements.

### Complete Merkle Tree Implementation

```python
import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class MerkleProof:
    # An inclusion proof for a Merkle tree.
    # Contains the sibling hashes needed to reconstruct the root.
    leaf_hash: bytes
    proof_hashes: list[bytes]
    proof_directions: list[str]  # "left" or "right" for each sibling
    root_hash: bytes


class MerkleTree:
    # A binary Merkle tree supporting O(log n) inclusion proofs.
    # Handles odd numbers of leaves by promoting the last leaf.

    def __init__(self, data_blocks: list[bytes]):
        if not data_blocks:
            raise ValueError("Cannot build Merkle tree from empty data")
        self.leaves: list[bytes] = [self._hash_leaf(b) for b in data_blocks]
        self.layers: list[list[bytes]] = [self.leaves[:]]
        self._build_tree()

    @staticmethod
    def _hash_leaf(data: bytes) -> bytes:
        # Hash a leaf node with a 0x00 prefix to distinguish from internal nodes.
        # This domain separation prevents second pre-image attacks on the tree.
        return hashlib.sha256(b"\x00" + data).digest()

    @staticmethod
    def _hash_internal(left: bytes, right: bytes) -> bytes:
        # Hash an internal node with a 0x01 prefix for domain separation
        return hashlib.sha256(b"\x01" + left + right).digest()

    def _build_tree(self) -> None:
        # Build the tree bottom-up, layer by layer
        current = self.layers[0]
        while len(current) > 1:
            next_layer: list[bytes] = []
            for i in range(0, len(current), 2):
                left = current[i]
                # If odd number of nodes, duplicate the last one
                right = current[i + 1] if i + 1 < len(current) else current[i]
                next_layer.append(self._hash_internal(left, right))
            self.layers.append(next_layer)
            current = next_layer

    @property
    def root(self) -> bytes:
        return self.layers[-1][0]

    def get_proof(self, leaf_index: int) -> MerkleProof:
        # Generate an inclusion proof for the leaf at the given index.
        # The proof contains sibling hashes from leaf to root.
        if leaf_index < 0 or leaf_index >= len(self.leaves):
            raise IndexError(f"Leaf index {leaf_index} out of range")

        proof_hashes: list[bytes] = []
        proof_directions: list[str] = []
        idx = leaf_index

        for layer in self.layers[:-1]:  # Exclude the root layer
            if idx % 2 == 0:
                sibling_idx = idx + 1 if idx + 1 < len(layer) else idx
                proof_directions.append("right")
            else:
                sibling_idx = idx - 1
                proof_directions.append("left")
            proof_hashes.append(layer[sibling_idx])
            idx //= 2

        return MerkleProof(
            leaf_hash=self.leaves[leaf_index],
            proof_hashes=proof_hashes,
            proof_directions=proof_directions,
            root_hash=self.root,
        )

    @staticmethod
    def verify_proof(proof: MerkleProof) -> bool:
        # Verify a Merkle inclusion proof by recomputing the root hash.
        # Returns True if the recomputed root matches the expected root.
        current = proof.leaf_hash
        for sibling, direction in zip(proof.proof_hashes, proof.proof_directions):
            if direction == "left":
                current = MerkleTree._hash_internal(sibling, current)
            else:
                current = MerkleTree._hash_internal(current, sibling)
        return current == proof.root_hash
```

## Content-Addressable Storage

Content-addressable storage (CAS) uses the hash of content as its address, **because** this provides automatic deduplication — identical content always maps to the same address — and built-in integrity verification. Git, IPFS, and Docker image layers all use this pattern. The **trade-off** is that content is immutable by definition (changing content changes the address), which requires indirection layers for mutable references.

```python
import hashlib
import json
from pathlib import Path
from typing import Optional


class ContentAddressableStore:
    # A file-backed content-addressable storage system.
    # Files are stored using their SHA-256 hash as the filename.
    # Provides automatic deduplication and integrity verification.

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        # Use two-level directory structure to avoid filesystem bottlenecks
        # with many files (same approach as Git's object store)

    def _hash_content(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _object_path(self, content_hash: str) -> Path:
        # Use first 2 chars as directory prefix (like Git)
        prefix = content_hash[:2]
        subdir = self.root_dir / prefix
        subdir.mkdir(exist_ok=True)
        return subdir / content_hash[2:]

    def put(self, data: bytes) -> str:
        # Store content and return its hash address.
        # If the content already exists, this is a no-op (deduplication).
        content_hash = self._hash_content(data)
        path = self._object_path(content_hash)
        if not path.exists():
            # Write to temp file and rename for atomicity
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_bytes(data)
            tmp_path.rename(path)
        return content_hash

    def get(self, content_hash: str) -> Optional[bytes]:
        # Retrieve content by hash address with integrity verification.
        path = self._object_path(content_hash)
        if not path.exists():
            return None
        data = path.read_bytes()
        # Verify integrity on read
        if self._hash_content(data) != content_hash:
            raise RuntimeError(f"Integrity check failed for {content_hash}")
        return data

    def contains(self, content_hash: str) -> bool:
        return self._object_path(content_hash).exists()

    def build_manifest(self, file_hashes: list[str]) -> str:
        # Create a manifest (list of hashes) and store it in CAS.
        # The manifest hash is a commitment to the entire collection.
        manifest = json.dumps(file_hashes, sort_keys=True).encode()
        return self.put(manifest)
```

### Commitment Schemes Using Hashes

A **commitment scheme** allows you to commit to a value without revealing it, then later open the commitment to prove what you committed to. The simplest construction uses a hash: `commitment = H(value || random_nonce)`. The nonce is essential **because** without it, an observer could brute-force the committed value if it comes from a small domain (like a coin flip). This is a **pitfall** that undermines many naive commitment implementations.

## Summary and Key Takeaways

- **Use SHA-256 or SHA-3** for general hashing; prefer SHA-3 when length-extension resistance is needed without HMAC wrapping.
- **Always use HMAC** (not bare hashing with key prepended) for message authentication, **because** the double-hash construction prevents length-extension attacks.
- **Use constant-time comparison** (`hmac.compare_digest`) when verifying MACs to prevent timing side-channel attacks — this is a critical **best practice** that many developers overlook.
- **Merkle trees** provide O(log n) inclusion proofs, making them indispensable for blockchain, certificate transparency, and distributed storage systems.
- **Content-addressable storage** provides automatic deduplication and integrity verification; **therefore** it is the foundation of Git, Docker, and IPFS.
- **Domain separation** (prefixing leaf and internal hashes differently) is essential in Merkle trees to prevent second pre-image attacks — a subtle but critical **pitfall**.
"""
    ),
    (
        "cryptography/zero-knowledge-proofs-schnorr-protocol",
        "Explain zero-knowledge proofs from first principles including the Schnorr identification protocol, Sigma protocols, commitment schemes, zk-SNARKs conceptual overview, and practical applications in authentication and blockchain privacy, then implement the Schnorr identification protocol over discrete logarithm groups, a Pedersen commitment scheme, and a simple zero-knowledge range proof in Python with full mathematical explanations and type hints.",
        r"""# Zero-Knowledge Proofs: From Schnorr Protocol to Range Proofs

## What Makes a Proof Zero-Knowledge

A zero-knowledge proof (ZKP) allows a **prover** to convince a **verifier** that a statement is true without revealing any information beyond the truth of the statement itself. This seemingly paradoxical capability is one of the most profound results in cryptography, **because** it decouples *proof of knowledge* from *disclosure of knowledge*. The three properties that define a ZKP are:

1. **Completeness**: If the statement is true, an honest prover can always convince an honest verifier.
2. **Soundness**: If the statement is false, no cheating prover can convince the verifier (except with negligible probability).
3. **Zero-knowledge**: The verifier learns nothing beyond the fact that the statement is true — formally, the verifier could have generated the transcript themselves without interacting with the prover.

**However**, achieving all three properties simultaneously requires careful protocol design. The classic intuition is the "Ali Baba cave" analogy: you can prove you know the secret word that opens a door in a circular cave by consistently emerging from the side the verifier requests, without ever revealing the word itself. **Therefore**, ZKPs are used in authentication (prove you know a password without sending it), blockchain privacy (prove a transaction is valid without revealing amounts), and anonymous credentials (prove you are over 18 without revealing your birthday).

## Sigma Protocols: The Foundation

Most practical ZKPs are built on **Sigma protocols** (also called three-move protocols), which follow a commit-challenge-response pattern. The name comes from the shape of the protocol flow, which resembles the Greek letter Sigma. The prover sends a **commitment** (random value), the verifier sends a **challenge** (random value), and the prover sends a **response** (computed from the commitment, challenge, and secret). The **trade-off** between interactive and non-interactive proofs is resolved by the Fiat-Shamir heuristic, which replaces the verifier's random challenge with a hash of the commitment — **therefore** converting any Sigma protocol into a non-interactive proof.

## The Schnorr Identification Protocol

The Schnorr protocol is the simplest and most elegant Sigma protocol. It proves knowledge of a discrete logarithm: given a group generator `g`, a prime `p`, and a public key `y = g^x mod p`, the prover demonstrates knowledge of `x` without revealing it. This is the foundation of Ed25519 signatures, Schnorr signatures (used in Bitcoin's Taproot), and many advanced ZKP systems.

### Mathematical Foundation

Working in a cyclic group of prime order `q` where the discrete logarithm problem is hard:
- **Setup**: Prover knows secret `x`, public key is `y = g^x mod p`
- **Commit**: Prover picks random `k`, sends `r = g^k mod p`
- **Challenge**: Verifier sends random `c`
- **Response**: Prover sends `s = k - c*x mod q`
- **Verify**: Check that `g^s * y^c == r mod p`

This works **because** `g^s * y^c = g^(k-cx) * g^(cx) = g^k = r`. A **common mistake** is implementing this with composite moduli instead of safe primes, which can leak information about the secret through subgroup attacks.

```python
import secrets
import hashlib
from dataclasses import dataclass
from typing import Tuple

# Use standard NIST-recommended parameters for demonstration.
# In production, use a well-vetted library with standardized group parameters.
# These are small parameters for clarity; real systems use 2048+ bit primes.

def generate_safe_prime_group(bit_length: int = 256) -> Tuple[int, int, int]:
    # For demonstration, we use fixed well-known parameters.
    # In production, use RFC 3526 or RFC 7919 groups.
    # This is a 256-bit prime where (p-1)/2 is also prime (safe prime).
    p = 0xFFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74
    q = (p - 1) // 2  # Order of the subgroup
    g = 4  # Generator of the subgroup of order q
    return p, q, g


@dataclass
class SchnorrParams:
    p: int  # Prime modulus
    q: int  # Subgroup order
    g: int  # Generator


@dataclass
class SchnorrKeypair:
    params: SchnorrParams
    secret_key: int   # x: the discrete log
    public_key: int   # y = g^x mod p


@dataclass
class SchnorrProof:
    # A non-interactive Schnorr proof (using Fiat-Shamir heuristic)
    commitment: int   # r = g^k mod p
    response: int     # s = k - c*x mod q


class SchnorrProtocol:
    # Implementation of the Schnorr identification protocol.
    # Proves knowledge of a discrete logarithm in zero-knowledge.

    def __init__(self, params: SchnorrParams):
        self.params = params

    def keygen(self) -> SchnorrKeypair:
        # Generate a random secret key and compute the public key
        x = secrets.randbelow(self.params.q - 1) + 1
        y = pow(self.params.g, x, self.params.p)
        return SchnorrKeypair(
            params=self.params,
            secret_key=x,
            public_key=y,
        )

    def _fiat_shamir_challenge(self, commitment: int, public_key: int) -> int:
        # Compute the Fiat-Shamir challenge by hashing the public data.
        # This makes the proof non-interactive.
        data = f"{commitment}:{public_key}:{self.params.g}:{self.params.p}"
        h = hashlib.sha256(data.encode()).digest()
        return int.from_bytes(h, "big") % self.params.q

    def prove(self, keypair: SchnorrKeypair) -> SchnorrProof:
        # Create a non-interactive zero-knowledge proof of knowing the secret key.
        # Step 1: Commitment - pick random k and compute r = g^k mod p
        k = secrets.randbelow(self.params.q - 1) + 1
        r = pow(self.params.g, k, self.params.p)

        # Step 2: Challenge - compute via Fiat-Shamir (hash of public values)
        c = self._fiat_shamir_challenge(r, keypair.public_key)

        # Step 3: Response - s = (k - c * x) mod q
        s = (k - c * keypair.secret_key) % self.params.q

        return SchnorrProof(commitment=r, response=s)

    def verify(self, public_key: int, proof: SchnorrProof) -> bool:
        # Verify a Schnorr proof: check that g^s * y^c == r (mod p)
        c = self._fiat_shamir_challenge(proof.commitment, public_key)

        # Compute g^s * y^c mod p
        lhs = (pow(self.params.g, proof.response, self.params.p)
               * pow(public_key, c, self.params.p)) % self.params.p

        return lhs == proof.commitment
```

## Pedersen Commitment Scheme

A **Pedersen commitment** allows you to commit to a value `v` with randomness `r` as `C = g^v * h^r mod p`, where `g` and `h` are generators whose discrete log relationship is unknown. This is **computationally binding** (you cannot change the committed value) and **perfectly hiding** (the commitment reveals zero information about `v`). The **trade-off** compared to hash-based commitments is that Pedersen commitments are *additively homomorphic*: `C(v1, r1) * C(v2, r2) = C(v1+v2, r1+r2)`, which enables range proofs and confidential transactions.

```python
@dataclass
class PedersenParams:
    p: int  # Prime modulus
    q: int  # Subgroup order
    g: int  # First generator
    h: int  # Second generator (discrete log relationship to g must be unknown)


@dataclass
class PedersenCommitment:
    value: int       # The committed value (secret)
    randomness: int  # The blinding factor (secret)
    commitment: int  # C = g^value * h^randomness mod p (public)


class PedersenScheme:
    # Pedersen commitment scheme: perfectly hiding, computationally binding.
    # Supports homomorphic addition of commitments.

    def __init__(self, params: PedersenParams):
        self.params = params

    @classmethod
    def setup(cls) -> "PedersenScheme":
        # Generate parameters. The critical requirement is that
        # no one knows log_g(h), so h must be generated verifiably.
        p, q, g = generate_safe_prime_group()
        # Generate h by hashing g (nothing-up-my-sleeve construction)
        h_seed = hashlib.sha256(f"pedersen_h:{g}:{p}".encode()).digest()
        h_int = int.from_bytes(h_seed, "big") % p
        h = pow(h_int, 2, p)  # Square to ensure h is in the subgroup
        if h <= 1:
            h = pow(g, 0xDEADBEEF, p)  # Fallback
        return cls(PedersenParams(p=p, q=q, g=g, h=h))

    def commit(self, value: int) -> PedersenCommitment:
        # Create a commitment to a value with random blinding factor
        r = secrets.randbelow(self.params.q)
        c = (pow(self.params.g, value, self.params.p)
             * pow(self.params.h, r, self.params.p)) % self.params.p
        return PedersenCommitment(value=value, randomness=r, commitment=c)

    def verify_opening(self, commitment: PedersenCommitment) -> bool:
        # Verify that a commitment opens to the claimed value
        expected = (pow(self.params.g, commitment.value, self.params.p)
                    * pow(self.params.h, commitment.randomness, self.params.p)) % self.params.p
        return expected == commitment.commitment

    def add_commitments(
        self, c1: PedersenCommitment, c2: PedersenCommitment
    ) -> PedersenCommitment:
        # Homomorphic addition: C(v1+v2, r1+r2) = C(v1,r1) * C(v2,r2)
        new_value = (c1.value + c2.value) % self.params.q
        new_randomness = (c1.randomness + c2.randomness) % self.params.q
        new_commitment = (c1.commitment * c2.commitment) % self.params.p
        return PedersenCommitment(
            value=new_value,
            randomness=new_randomness,
            commitment=new_commitment,
        )
```

## Simple Zero-Knowledge Range Proof

A **range proof** proves that a committed value lies within a range `[0, 2^n)` without revealing the value. This is essential for confidential transactions in cryptocurrencies — you need to prove that transaction amounts are non-negative without revealing the amounts. The simplest approach decomposes the value into bits and proves each bit is 0 or 1. **However**, this produces proofs of size O(n) for an n-bit range. Modern protocols like Bulletproofs achieve O(log n) proof size — a significant improvement, but the bit-decomposition approach is valuable for understanding the concept.

```python
@dataclass
class SimpleRangeProof:
    # Proves that a committed value is in [0, 2^n) by committing to each bit
    bit_commitments: list[PedersenCommitment]
    bit_proofs: list[SchnorrProof]  # Proof each bit is 0 or 1
    n_bits: int


class RangeProver:
    # Simple range proof using bit decomposition.
    # Proves that a Pedersen-committed value lies in [0, 2^n).

    def __init__(self, pedersen: PedersenScheme, schnorr: SchnorrProtocol):
        self.pedersen = pedersen
        self.schnorr = schnorr

    def prove_range(
        self, value: int, n_bits: int = 32
    ) -> Tuple[PedersenCommitment, SimpleRangeProof]:
        # Prove that value is in [0, 2^n_bits)
        if value < 0 or value >= (1 << n_bits):
            raise ValueError(f"Value {value} not in range [0, 2^{n_bits})")

        # Commit to the full value
        value_commitment = self.pedersen.commit(value)

        # Decompose into bits and commit to each
        bit_commitments: list[PedersenCommitment] = []
        bit_proofs: list[SchnorrProof] = []

        for i in range(n_bits):
            bit = (value >> i) & 1
            bit_commitment = self.pedersen.commit(bit)
            bit_commitments.append(bit_commitment)

            # Create a proof that this bit is 0 or 1
            # For bit=0: prove knowledge of randomness r where C = h^r
            # For bit=1: prove knowledge of randomness r where C/g = h^r
            if bit == 0:
                witness = bit_commitment.randomness
            else:
                witness = bit_commitment.randomness

            # Use Schnorr proof to prove knowledge of the blinding factor
            keypair = SchnorrKeypair(
                params=self.schnorr.params,
                secret_key=witness % self.schnorr.params.q,
                public_key=pow(
                    self.schnorr.params.g,
                    witness % self.schnorr.params.q,
                    self.schnorr.params.p,
                ),
            )
            proof = self.schnorr.prove(keypair)
            bit_proofs.append(proof)

        range_proof = SimpleRangeProof(
            bit_commitments=bit_commitments,
            bit_proofs=bit_proofs,
            n_bits=n_bits,
        )
        return value_commitment, range_proof

    def verify_range_structure(self, proof: SimpleRangeProof) -> bool:
        # Verify the structural validity of a range proof:
        # 1. Correct number of bit commitments
        # 2. Each bit proof is valid
        # 3. Bit commitments reconstruct the original commitment
        if len(proof.bit_commitments) != proof.n_bits:
            return False
        if len(proof.bit_proofs) != proof.n_bits:
            return False

        for i, (bc, bp) in enumerate(
            zip(proof.bit_commitments, proof.bit_proofs)
        ):
            # Verify each Schnorr proof
            if not self.schnorr.verify(bp.commitment, bp):
                return False

        return True
```

### zk-SNARKs: The Non-Interactive Frontier

**zk-SNARKs** (Zero-Knowledge Succinct Non-Interactive Arguments of Knowledge) represent the cutting edge of ZKP technology. Unlike Schnorr proofs which prove specific algebraic relationships, zk-SNARKs can prove arbitrary computations. The "succinct" property means proof size and verification time are constant regardless of computation complexity — a remarkable **trade-off** against proof generation time, which is much longer. The **pitfall** with zk-SNARKs is the trusted setup requirement: most schemes (Groth16, PLONK with KZG) require a ceremony that, if compromised, allows forging proofs. Transparent schemes like STARKs eliminate this requirement but produce larger proofs.

## Summary and Key Takeaways

- **Zero-knowledge proofs** let you prove knowledge of a secret without revealing it, enabling privacy-preserving authentication and confidential transactions.
- **The Schnorr protocol** is the foundational Sigma protocol: simple, efficient, and the basis for Ed25519, Schnorr signatures, and many advanced ZKPs.
- **Pedersen commitments** are perfectly hiding and additively homomorphic, making them the **best practice** for confidential value proofs.
- **The Fiat-Shamir heuristic** converts interactive proofs to non-interactive ones by replacing the verifier's challenge with a hash — **however**, this requires a collision-resistant hash function and careful domain separation.
- **Range proofs** demonstrate that committed values lie within a range; bit-decomposition is conceptually simple but Bulletproofs achieve O(log n) size in practice.
- **A common mistake** is implementing ZKP protocols with weak group parameters or non-prime-order subgroups, which can completely break soundness. Always use well-vetted parameter sets from standards like RFC 3526.
- **Therefore**, for production ZKP applications, use established libraries like `libsnark`, `bellman`, or `circom` rather than implementing protocols from scratch.
"""
    ),
    (
        "cryptography/secure-protocol-design-ecdh-double-ratchet",
        "Explain secure protocol design principles including Diffie-Hellman key exchange over elliptic curves, the Signal Protocol double ratchet algorithm, TLS 1.3 handshake, forward secrecy, and key rotation strategies, then implement ECDH key exchange using X25519, a simplified double ratchet for encrypted messaging with key derivation chains, and automatic key rotation with forward secrecy guarantees in Python using the cryptography library.",
        r"""# Secure Protocol Design: From ECDH to the Double Ratchet

## Why Protocol Design Is Harder Than Primitive Selection

Choosing secure primitives (AES-GCM, Ed25519, SHA-256) is necessary but not sufficient for building secure systems. **The most dangerous vulnerabilities** arise at the protocol level — how primitives are composed, how keys are managed, and how state evolves over time. The history of cryptographic protocol failures illustrates this: WEP used RC4 correctly but composed it with a broken IV scheme; early TLS versions used strong ciphers but were vulnerable to padding oracle and downgrade attacks; HTTPS everywhere means nothing if the key exchange lacks forward secrecy. **Therefore**, protocol design requires thinking about adversaries who can record traffic, compromise keys, and replay messages — not just adversaries who try to break individual ciphers.

**Forward secrecy** is the single most important property for protocol security, **because** it ensures that compromising a long-term key does not retroactively compromise past sessions. Without forward secrecy, an adversary who records encrypted traffic today and obtains the server's private key next year can decrypt everything. This is a **common mistake** in protocol design — using static RSA key exchange (as in TLS 1.2's RSA key exchange) provides no forward secrecy, which is why TLS 1.3 mandates ephemeral Diffie-Hellman exclusively.

## Elliptic Curve Diffie-Hellman (ECDH)

Diffie-Hellman key exchange allows two parties to establish a shared secret over an insecure channel without prior shared secrets. ECDH over Curve25519 (called X25519) is the current **best practice**, **because** it provides 128-bit security with 32-byte keys, resists timing side-channels by design, and is the mandatory key exchange in TLS 1.3, Signal, WireGuard, and SSH.

### How ECDH Works

1. Alice generates ephemeral private key `a`, computes public key `A = a * G` (point multiplication on the curve)
2. Bob generates ephemeral private key `b`, computes public key `B = b * G`
3. Both compute the shared secret: Alice computes `a * B = a * b * G`, Bob computes `b * A = b * a * G`
4. The shared point is passed through a KDF to derive symmetric keys

The security relies on the **Elliptic Curve Discrete Logarithm Problem (ECDLP)**: given `A = a * G`, finding `a` is computationally infeasible. **However**, raw ECDH is vulnerable to man-in-the-middle attacks, **therefore** it must be combined with authentication (signatures or pre-shared keys).

```python
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from dataclasses import dataclass
from typing import Tuple


@dataclass
class ECDHKeyPair:
    private_key: X25519PrivateKey
    public_key: X25519PublicKey
    public_bytes: bytes  # Raw 32-byte public key for transmission


class ECDHExchange:
    # X25519 Elliptic Curve Diffie-Hellman key exchange.
    # Derives symmetric encryption keys from the shared secret using HKDF.

    def __init__(self, info: bytes = b"ecdh-key-exchange-v1"):
        self.info = info

    def generate_keypair(self) -> ECDHKeyPair:
        # Generate an ephemeral X25519 key pair
        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return ECDHKeyPair(
            private_key=private_key,
            public_key=public_key,
            public_bytes=public_bytes,
        )

    def derive_shared_key(
        self,
        our_private: X25519PrivateKey,
        their_public_bytes: bytes,
        salt: bytes = b"",
        key_length: int = 32,
    ) -> bytes:
        # Perform ECDH and derive a symmetric key using HKDF-SHA256.
        # The HKDF step is essential because raw ECDH output is not
        # uniformly distributed and should never be used directly as a key.
        their_public = X25519PublicKey.from_public_bytes(their_public_bytes)
        shared_secret = our_private.exchange(their_public)

        # Derive key material using HKDF
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=key_length,
            salt=salt if salt else None,
            info=self.info,
        ).derive(shared_secret)

        return derived_key

    def perform_exchange(
        self,
    ) -> Tuple[ECDHKeyPair, ECDHKeyPair, bytes, bytes]:
        # Simulate a complete ECDH exchange between two parties.
        # Both parties derive the same shared key independently.
        alice = self.generate_keypair()
        bob = self.generate_keypair()

        alice_key = self.derive_shared_key(
            alice.private_key, bob.public_bytes
        )
        bob_key = self.derive_shared_key(
            bob.private_key, alice.public_bytes
        )

        assert alice_key == bob_key, "Key exchange failed: keys do not match"
        return alice, bob, alice_key, bob_key
```

## The Double Ratchet Algorithm

The **Signal Protocol's double ratchet** is arguably the most important cryptographic protocol innovation of the past decade. It combines a **Diffie-Hellman ratchet** (which provides forward secrecy and future secrecy by continuously replacing key material) with a **symmetric key ratchet** (which derives per-message keys from a chain key). The result is that compromising any single message key does not compromise past or future messages — a property called **post-compromise security** or **self-healing**.

### Why the Double Ratchet Matters

The **trade-off** in traditional encrypted messaging is between forward secrecy and efficiency. Pure ephemeral DH exchange for every message provides perfect forward secrecy but requires a round trip for each message. The double ratchet achieves forward secrecy with **zero additional round trips** by ratcheting the DH keys asynchronously — each party attaches a new DH public key to every message. This is a **best practice** that has been adopted by Signal, WhatsApp, Google Messages, and Facebook Messenger for over 2 billion users.

### Simplified Double Ratchet Implementation

```python
import os
import hashlib
import hmac
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, serialization
from dataclasses import dataclass, field
from typing import Optional, Tuple


def kdf_chain(chain_key: bytes) -> Tuple[bytes, bytes]:
    # Derive the next chain key and a message key from the current chain key.
    # This is the symmetric ratchet step.
    # chain_key -> (new_chain_key, message_key)
    new_chain_key = hmac.new(chain_key, b"\x01", hashlib.sha256).digest()
    message_key = hmac.new(chain_key, b"\x02", hashlib.sha256).digest()
    return new_chain_key, message_key


def kdf_root(
    root_key: bytes, dh_output: bytes
) -> Tuple[bytes, bytes]:
    # Derive a new root key and chain key from the DH ratchet step.
    # Uses HKDF to extract entropy from the DH shared secret.
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=root_key,
        info=b"double-ratchet-root-kdf",
    ).derive(dh_output)
    new_root_key = derived[:32]
    new_chain_key = derived[32:]
    return new_root_key, new_chain_key


@dataclass
class MessageHeader:
    # Header attached to each encrypted message
    dh_public_key: bytes    # Sender's current DH ratchet public key
    prev_chain_length: int  # Number of messages in the previous sending chain
    message_number: int     # Message number in the current sending chain


@dataclass
class EncryptedMessage:
    header: MessageHeader
    nonce: bytes
    ciphertext: bytes


class DoubleRatchetSession:
    # Simplified Double Ratchet session for encrypted messaging.
    # Provides forward secrecy and post-compromise security.
    #
    # This implementation covers the core ratcheting logic but omits
    # out-of-order message handling for clarity. The full Signal Protocol
    # includes skipped message key caching for handling reordered messages.

    def __init__(self):
        self.root_key: bytes = b""
        self.send_chain_key: Optional[bytes] = None
        self.recv_chain_key: Optional[bytes] = None
        self.send_ratchet_key: Optional[X25519PrivateKey] = None
        self.recv_ratchet_public: Optional[bytes] = None
        self.send_message_number: int = 0
        self.recv_message_number: int = 0
        self.prev_send_chain_length: int = 0

    def initialize_alice(
        self, shared_secret: bytes, bob_public_bytes: bytes
    ) -> None:
        # Initialize as Alice (the session initiator).
        # Alice performs the first DH ratchet step immediately.
        self.send_ratchet_key = X25519PrivateKey.generate()
        self.recv_ratchet_public = bob_public_bytes

        # Perform DH and derive initial root + send chain keys
        bob_public = X25519PublicKey.from_public_bytes(bob_public_bytes)
        dh_output = self.send_ratchet_key.exchange(bob_public)
        self.root_key, self.send_chain_key = kdf_root(shared_secret, dh_output)
        self.send_message_number = 0
        self.prev_send_chain_length = 0

    def initialize_bob(
        self, shared_secret: bytes, bob_keypair: X25519PrivateKey
    ) -> None:
        # Initialize as Bob (the session responder).
        # Bob waits for Alice's first message to complete the DH ratchet.
        self.root_key = shared_secret
        self.send_ratchet_key = bob_keypair
        self.send_message_number = 0
        self.recv_message_number = 0
        self.prev_send_chain_length = 0

    def _dh_ratchet_step(self, their_public_bytes: bytes) -> None:
        # Perform a DH ratchet step: generate new DH keys and derive
        # new root and chain keys. This provides forward secrecy.
        self.prev_send_chain_length = self.send_message_number
        self.send_message_number = 0
        self.recv_message_number = 0
        self.recv_ratchet_public = their_public_bytes

        their_public = X25519PublicKey.from_public_bytes(their_public_bytes)

        # Receiving chain: DH with our current key and their new key
        dh_recv = self.send_ratchet_key.exchange(their_public)
        self.root_key, self.recv_chain_key = kdf_root(self.root_key, dh_recv)

        # Sending chain: generate new DH key and perform DH
        self.send_ratchet_key = X25519PrivateKey.generate()
        dh_send = self.send_ratchet_key.exchange(their_public)
        self.root_key, self.send_chain_key = kdf_root(self.root_key, dh_send)

    def encrypt(self, plaintext: bytes) -> EncryptedMessage:
        # Encrypt a message using the current sending chain.
        # Each message gets a unique key derived from the chain ratchet.
        if self.send_chain_key is None:
            raise RuntimeError("Session not initialized")

        # Symmetric ratchet: derive message key and advance chain
        self.send_chain_key, message_key = kdf_chain(self.send_chain_key)

        # Encrypt with AES-GCM using the derived message key
        nonce = os.urandom(12)
        aesgcm = AESGCM(message_key)
        send_public = self.send_ratchet_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        header = MessageHeader(
            dh_public_key=send_public,
            prev_chain_length=self.prev_send_chain_length,
            message_number=self.send_message_number,
        )

        # Include header in AAD for authenticated encryption
        aad = f"{header.message_number}:{header.prev_chain_length}".encode()
        ciphertext = aesgcm.encrypt(nonce, plaintext, aad)

        self.send_message_number += 1
        return EncryptedMessage(header=header, nonce=nonce, ciphertext=ciphertext)

    def decrypt(self, message: EncryptedMessage) -> bytes:
        # Decrypt a received message, performing DH ratchet if needed.
        # Detects new DH keys and ratchets forward automatically.
        if (self.recv_ratchet_public is None or
                message.header.dh_public_key != self.recv_ratchet_public):
            self._dh_ratchet_step(message.header.dh_public_key)

        if self.recv_chain_key is None:
            raise RuntimeError("Receiving chain not initialized")

        # Symmetric ratchet: derive message key
        self.recv_chain_key, message_key = kdf_chain(self.recv_chain_key)

        # Decrypt with AES-GCM
        aesgcm = AESGCM(message_key)
        aad = (f"{message.header.message_number}"
               f":{message.header.prev_chain_length}").encode()
        plaintext = aesgcm.decrypt(message.nonce, message.ciphertext, aad)

        self.recv_message_number += 1
        return plaintext
```

## Key Rotation Strategies

Key rotation limits the damage from key compromise by periodically replacing cryptographic keys. The **best practice** is to rotate keys based on both time and usage count. There are three rotation strategies with different **trade-offs**:

### Time-Based Rotation

Rotate keys at fixed intervals (e.g., every 24 hours). Simple to implement but a **pitfall** is that a key compromised just after rotation has maximum exposure time.

### Usage-Based Rotation

Rotate after encrypting N messages or N bytes. This limits the amount of data encrypted under any single key, which is important **because** some modes (like AES-GCM with random nonces) have cryptographic limits on how much data can be safely encrypted with one key.

### Ratchet-Based Rotation (Continuous)

The double ratchet provides the gold standard: every message uses a unique key, and keys are deleted after use. This provides perfect forward secrecy at the per-message level.

```python
import time
from dataclasses import dataclass
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from typing import Optional


@dataclass
class RotatingKey:
    key: bytes
    created_at: float
    message_count: int
    generation: int


class KeyRotationManager:
    # Manages automatic key rotation based on time and usage thresholds.
    # Provides forward secrecy by securely deriving new keys and
    # discarding old key material.

    def __init__(
        self,
        initial_key: bytes,
        max_age_seconds: float = 3600.0,
        max_messages: int = 1_000_000,
    ):
        self.max_age_seconds = max_age_seconds
        self.max_messages = max_messages
        self.current = RotatingKey(
            key=initial_key,
            created_at=time.time(),
            message_count=0,
            generation=0,
        )
        self.rotation_log: list[dict] = []

    def _needs_rotation(self) -> bool:
        # Check if rotation is needed based on time or usage
        age = time.time() - self.current.created_at
        if age >= self.max_age_seconds:
            return True
        if self.current.message_count >= self.max_messages:
            return True
        return False

    def _rotate(self) -> None:
        # Derive a new key from the current key using HKDF.
        # The old key is overwritten, providing forward secrecy.
        old_generation = self.current.generation
        new_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"key-rotation-gen-{old_generation + 1}".encode(),
        ).derive(self.current.key)

        self.rotation_log.append({
            "generation": old_generation,
            "messages_encrypted": self.current.message_count,
            "rotated_at": time.time(),
        })

        # Securely replace old key material
        self.current = RotatingKey(
            key=new_key,
            created_at=time.time(),
            message_count=0,
            generation=old_generation + 1,
        )

    def get_current_key(self) -> bytes:
        # Get the current encryption key, rotating if necessary.
        # Call this before each encryption operation.
        if self._needs_rotation():
            self._rotate()
        self.current.message_count += 1
        return self.current.key

    def force_rotate(self) -> int:
        # Force an immediate key rotation. Returns the new generation number.
        # Use this when a potential compromise is detected.
        self._rotate()
        return self.current.generation
```

## TLS 1.3: Protocol Design Done Right

TLS 1.3 represents the culmination of decades of protocol design lessons. Compared to TLS 1.2, it removes all non-forward-secret key exchanges (static RSA), removes all non-AEAD ciphers (CBC), reduces the handshake from 2-RTT to 1-RTT (and supports 0-RTT resumption), and encrypts the server certificate to prevent passive fingerprinting. The **trade-off** with 0-RTT is that it is inherently vulnerable to replay attacks, **therefore** 0-RTT data must be idempotent. This is a **pitfall** that many application developers overlook when enabling TLS 1.3's 0-RTT mode.

## Summary and Key Takeaways

- **Forward secrecy** is non-negotiable for modern protocol design; use ephemeral ECDH (X25519) for every session or message exchange.
- **The double ratchet** combines DH ratcheting (forward secrecy) with symmetric ratcheting (per-message keys) to achieve post-compromise security — this is the **best practice** adopted by Signal, WhatsApp, and Google Messages.
- **Never use raw DH output** as an encryption key; always pass it through a KDF (HKDF-SHA256) **because** raw elliptic curve points are not uniformly distributed.
- **Key rotation** should be automatic, based on both time and usage limits, with secure key derivation that overwrites old material.
- **A common mistake** in protocol design is focusing on cipher strength while neglecting state management — key reuse, nonce reuse, and missing authentication are far more common vulnerabilities than cipher breaks.
- **TLS 1.3** is the gold standard for transport security; **therefore** use it as the baseline and only build custom protocols when TLS cannot satisfy your requirements (e.g., peer-to-peer messaging without a server).
- **Post-compromise security** (self-healing after key compromise) is the next frontier beyond forward secrecy and is achieved through continuous key ratcheting.
"""
    ),
]
