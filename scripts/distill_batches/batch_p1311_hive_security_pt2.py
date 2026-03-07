"""Hive security training pairs (part 2): advanced security, monitoring, signing."""

PAIRS = [
    (
        "hive_security/witness-signing-key-rotation",
        r'''How do I rotate the signing key for my Hive witness node without missing blocks?''',
        r'''<think>
Witness signing key rotation requires updating the chain before restarting the node.
The flow: generate a new key pair, broadcast witness_update with the new public key,
then update the node config and restart. Timing matters — if you update the chain
first but the node still uses the old key, you miss blocks until restart. Best
practice is to prepare everything, broadcast, then restart immediately. Use a
backup node if available to avoid any gap.
</think>

Here is how to safely rotate your witness signing key:

```python
from beem import Hive
from beem.witness import Witness
from beemgraphenebase.account import PrivateKey

# Generate a new signing key pair
new_private = PrivateKey()
new_public = str(new_private.pubkey)
print(f"New private signing key (store securely): {str(new_private)}")
print(f"New public signing key: {new_public}")

# Connect with your active key (NOT the signing key)
hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5Jactive_key_here"]
)

# Update witness with the new signing key on-chain
witness = Witness("yourwitness", blockchain_instance=hive)
witness.update(
    signing_key=new_public,
    url=witness["url"],
    props=witness["props"]
)
print("Witness update broadcast — now restart your node immediately")

# After broadcast, update your witness node config.ini:
# witness = "yourwitness"
# private-key = <new_private_key>
# Then restart hived. The gap between broadcast and restart should
# be as short as possible to avoid missing blocks.

# Verify the rotation took effect
import time
time.sleep(6)  # wait one block
w = Witness("yourwitness", blockchain_instance=hive)
assert w["signing_key"] == new_public, "Key rotation failed!"
print(f"Signing key is now: {w['signing_key']}")
```

Key points:
- Never reuse old signing keys — generate fresh each rotation
- Keep the signing private key **only** on the witness node
- Your active key (used to broadcast) should be stored separately
- Schedule rotations regularly (e.g., monthly) as a security practice'''
    ),
    (
        "hive_security/multi-authority-transaction",
        r'''How do I build a Hive transaction that requires signatures from multiple accounts?''',
        r'''<think>
Multi-authority transactions on Hive occur when an operation references multiple
accounts whose authorities must approve. For example, a multi-sig account where
the authority threshold requires 2 of 3 keys. Or a transaction with multiple
operations each requiring different account signatures. The TransactionBuilder
in beem lets you append operations and sign with multiple keys. The key insight
is that all required signatures must be present before broadcast.
</think>

Build and sign a transaction requiring multiple account authorities:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer, Custom_json

# Connect with multiple signing keys
hive = Hive(
    node=["https://api.hive.blog"],
    keys=[
        "5Jalice_active_key",
        "5Jbob_active_key",
    ]
)

tx = TransactionBuilder(blockchain_instance=hive)

# Operation 1: Alice sends to Carol
tx.appendOps(Transfer(**{
    "from": "alice",
    "to": "carol",
    "amount": "1.000 HIVE",
    "memo": "From Alice"
}))

# Operation 2: Bob sends to Carol
tx.appendOps(Transfer(**{
    "from": "bob",
    "to": "carol",
    "amount": "2.000 HIVE",
    "memo": "From Bob"
}))

# Sign with all required authorities
tx.appendSigner("alice", "active")
tx.appendSigner("bob", "active")
tx.sign()

# Broadcast as a single atomic transaction
result = tx.broadcast()
print(f"Multi-auth tx: {result}")

# --- Multi-sig account example ---
# If "team-fund" has a 2-of-3 active authority:
# weight_threshold: 2
# account_auths: [["alice", 1], ["bob", 1], ["carol", 1]]

hive_multisig = Hive(
    node=["https://api.hive.blog"],
    keys=["5Jalice_active", "5Jbob_active"]  # 2 of 3 needed
)

tx2 = TransactionBuilder(blockchain_instance=hive_multisig)
tx2.appendOps(Transfer(**{
    "from": "team-fund",
    "to": "vendor",
    "amount": "100.000 HIVE",
    "memo": "Invoice #42"
}))
tx2.appendSigner("alice", "active")
tx2.appendSigner("bob", "active")
tx2.sign()
tx2.broadcast()
```

Both Alice and Bob must sign before the transaction will be accepted by the network.'''
    ),
    (
        "hive_security/phishing-link-detection",
        r'''I want to build a phishing link detector that scans Hive posts and comments for suspicious URLs mimicking real Hive sites. How would I approach this?''',
        r'''<think>
Phishing detection for Hive URLs involves: checking for lookalike domains of known
Hive services (hive.blog, peakd.com, ecency.com, hivesigner.com, etc.), detecting
homoglyph attacks (cyrillic chars that look latin), checking for suspicious subdomains,
and flagging URLs that request key input. A scoring approach works well — each
suspicious signal adds weight, and a threshold triggers an alert. This is an
intermediate-to-advanced pattern useful for front-ends and moderation bots.
</think>

```python
import re
from urllib.parse import urlparse
from typing import NamedTuple

LEGIT_DOMAINS = {
    "hive.blog", "peakd.com", "ecency.com", "hivesigner.com",
    "hive-engine.com", "splinterlands.com", "leofinance.io",
    "hive.io", "hiveblocks.com", "ausbit.dev",
}

# Characters commonly used in homoglyph attacks
HOMOGLYPHS = {
    '\u0430': 'a', '\u0435': 'e', '\u043e': 'o', '\u0440': 'p',
    '\u0441': 'c', '\u0443': 'y', '\u0445': 'x', '\u04bb': 'h',
    '\u0456': 'i', '\u0455': 's', '\u0460': 'o',
}

class PhishingResult(NamedTuple):
    url: str
    score: float  # 0.0 = safe, 1.0 = certain phish
    reasons: list[str]

def _normalize_homoglyphs(text: str) -> str:
    return "".join(HOMOGLYPHS.get(c, c) for c in text)

def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return _levenshtein(b, a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j] + (ca != cb), prev[j+1] + 1, curr[j] + 1))
        prev = curr
    return prev[-1]

def check_url(url: str) -> PhishingResult:
    reasons = []
    score = 0.0

    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.hostname or ""
    except Exception:
        return PhishingResult(url, 0.8, ["Malformed URL"])

    normalized = _normalize_homoglyphs(domain)

    # Check for homoglyph substitution
    if normalized != domain:
        reasons.append(f"Homoglyph chars detected: {domain!r} -> {normalized!r}")
        score += 0.6

    # Check for near-miss of legitimate domains
    base_domain = ".".join(domain.rsplit(".", 2)[-2:])
    for legit in LEGIT_DOMAINS:
        if base_domain == legit:
            break
        dist = _levenshtein(base_domain, legit)
        if 0 < dist <= 2:
            reasons.append(f"Lookalike of {legit} (distance={dist})")
            score += 0.5
            break

    # Suspicious subdomain patterns (e.g., hive.blog.evil.com)
    for legit in LEGIT_DOMAINS:
        legit_base = legit.replace(".", "-")
        if legit_base in domain and base_domain not in LEGIT_DOMAINS:
            reasons.append(f"Uses '{legit_base}' as subdomain camouflage")
            score += 0.4

    # Path-based phishing (login/keys/import pages)
    path = (parsed.path or "").lower()
    if any(kw in path for kw in ["login", "import-key", "active-key", "unlock"]):
        reasons.append(f"Suspicious path: {parsed.path}")
        score += 0.3

    score = min(score, 1.0)
    return PhishingResult(url, score, reasons)

def scan_post_body(body: str, threshold: float = 0.4) -> list[PhishingResult]:
    """Extract URLs from post markdown and check each."""
    url_pattern = re.compile(r'https?://[^\s\)\]>"]+')
    urls = url_pattern.findall(body)
    return [r for url in set(urls) if (r := check_url(url)).score >= threshold]

# Usage
results = scan_post_body("Check out https://h1ve.blog/login to claim free HIVE!")
for r in results:
    print(f"PHISHING ({r.score:.0%}): {r.url} - {r.reasons}")
```'''
    ),
    (
        "hive_security/account-authority-diff-monitoring",
        r'''How can I monitor Hive accounts for unexpected authority changes and get alerted?''',
        r'''<think>
Authority changes on Hive (account_update or account_update2 operations) modify
who can control an account. Monitoring these is critical for detecting compromises.
The approach: periodically fetch account authority data, compare against a known-good
snapshot, and alert on any diff. Key fields are owner, active, posting authorities
and their account_auths/key_auths. We should also watch for memo_key changes which
could indicate an attacker trying to intercept encrypted memos.
</think>

```python
import json
import time
import hashlib
from dataclasses import dataclass, field
from beem import Hive
from beem.account import Account

@dataclass
class AuthSnapshot:
    owner_keys: list[str]
    owner_accounts: list[str]
    active_keys: list[str]
    active_accounts: list[str]
    posting_keys: list[str]
    posting_accounts: list[str]
    memo_key: str
    fingerprint: str = ""

    def __post_init__(self):
        raw = json.dumps(self.__dict__, sort_keys=True)
        self.fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:16]

def snapshot_authority(account_name: str, hive: Hive) -> AuthSnapshot:
    acc = Account(account_name, blockchain_instance=hive)
    return AuthSnapshot(
        owner_keys=[k[0] for k in acc["owner"]["key_auths"]],
        owner_accounts=[a[0] for a in acc["owner"]["account_auths"]],
        active_keys=[k[0] for k in acc["active"]["key_auths"]],
        active_accounts=[a[0] for a in acc["active"]["account_auths"]],
        posting_keys=[k[0] for k in acc["posting"]["key_auths"]],
        posting_accounts=[a[0] for a in acc["posting"]["account_auths"]],
        memo_key=acc["memo_key"],
    )

def diff_authorities(old: AuthSnapshot, new: AuthSnapshot) -> list[str]:
    changes = []
    for role in ("owner", "active", "posting"):
        for kind in ("keys", "accounts"):
            attr = f"{role}_{kind}"
            old_set = set(getattr(old, attr))
            new_set = set(getattr(new, attr))
            for added in new_set - old_set:
                changes.append(f"ADDED {role} {kind}: {added}")
            for removed in old_set - new_set:
                changes.append(f"REMOVED {role} {kind}: {removed}")
    if old.memo_key != new.memo_key:
        changes.append(f"MEMO KEY CHANGED: {old.memo_key[:20]}... -> {new.memo_key[:20]}...")
    return changes

def alert(account: str, changes: list[str]):
    """Replace with your notification system (email, Discord, etc.)."""
    print(f"ALERT for @{account}:")
    for c in changes:
        print(f"  {c}")

def monitor_loop(accounts: list[str], interval: int = 60):
    hive = Hive(node=["https://api.hive.blog"])
    snapshots: dict[str, AuthSnapshot] = {}

    # Initial snapshot
    for acc in accounts:
        snapshots[acc] = snapshot_authority(acc, hive)
        print(f"Baseline for @{acc}: {snapshots[acc].fingerprint}")

    while True:
        time.sleep(interval)
        for acc in accounts:
            try:
                current = snapshot_authority(acc, hive)
                if current.fingerprint != snapshots[acc].fingerprint:
                    changes = diff_authorities(snapshots[acc], current)
                    if changes:
                        alert(acc, changes)
                    snapshots[acc] = current
            except Exception as e:
                print(f"Error checking @{acc}: {e}")

# monitor_loop(["myaccount", "team-fund"], interval=30)
```

This catches owner/active/posting key additions/removals and memo key swaps in near real-time.'''
    ),
    (
        "hive_security/secure-signing-without-wif",
        r'''How do I sign Hive transactions securely without exposing the WIF (private key) in source code or environment variables?''',
        r'''<think>
Hardcoding WIF keys or even putting them in env vars is risky — env vars leak
via process inspection, logs, crash dumps. Better approaches: (1) use an encrypted
keystore file that requires a passphrase at runtime, (2) use OS keyring/credential
manager, (3) use a signing service that holds keys in memory only. For server apps,
a dedicated signing microservice with locked-down access is ideal. For CLI tools,
OS keyring (via the `keyring` library) works well. The key should never touch disk
in plaintext or appear in process arguments.
</think>

```python
import keyring
import getpass
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64
import os
import json
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer

# --- Option 1: OS Keyring (simplest for CLI tools) ---

def store_key_in_keyring(account: str, role: str, wif: str):
    """Store WIF in OS credential manager (Windows Credential Locker, macOS Keychain, etc.)."""
    keyring.set_password(f"hive-{role}", account, wif)

def get_key_from_keyring(account: str, role: str) -> str:
    wif = keyring.get_password(f"hive-{role}", account)
    if not wif:
        raise ValueError(f"No {role} key found for @{account} in keyring")
    return wif

# Usage:
# store_key_in_keyring("myaccount", "active", "5J...")  # one-time setup
# wif = get_key_from_keyring("myaccount", "active")

# --- Option 2: Encrypted keystore file ---

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))

def create_keystore(path: str, keys: dict[str, str], passphrase: str):
    """Encrypt keys dict to file. keys = {"active": "5J...", "posting": "5J..."}"""
    salt = os.urandom(16)
    fernet = Fernet(_derive_key(passphrase, salt))
    encrypted = fernet.encrypt(json.dumps(keys).encode())
    with open(path, "wb") as f:
        f.write(salt + encrypted)
    os.chmod(path, 0o600)  # owner-only read/write

def load_keystore(path: str, passphrase: str) -> dict[str, str]:
    with open(path, "rb") as f:
        data = f.read()
    salt, encrypted = data[:16], data[16:]
    fernet = Fernet(_derive_key(passphrase, salt))
    return json.loads(fernet.decrypt(encrypted))

# --- Signing with loaded key (key never in source) ---

def sign_transfer(from_acc: str, to_acc: str, amount: str):
    passphrase = getpass.getpass("Keystore passphrase: ")
    keys = load_keystore("keys.enc", passphrase)

    hive = Hive(node=["https://api.hive.blog"], keys=[keys["active"]])
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Transfer(**{
        "from": from_acc, "to": to_acc,
        "amount": amount, "memo": ""
    }))
    tx.appendSigner(from_acc, "active")
    tx.sign()
    result = tx.broadcast()
    # Key is only in memory, garbage collected after function exits
    return result
```

The WIF never appears in source code, env vars, logs, or shell history.'''
    ),
    (
        "hive_security/hardware-wallet-integration",
        r'''What are the concepts and flow for integrating a hardware wallet (like Ledger) with Hive transaction signing?''',
        r'''<think>
Hardware wallets keep private keys on a secure element — keys never leave the device.
The signing flow is: app builds an unsigned transaction, serializes it, sends it to
the hardware device via USB/Bluetooth, the device displays details for user confirmation,
signs on-device, and returns the signature. For Hive, the Ledger Nano has a Hive app.
The challenge is that Hive uses a custom serialization format, so the device needs
to understand Hive operation types to display meaningful confirmation info. The
integration layer handles USB communication via HID protocol.
</think>

```python
"""
Hardware wallet integration flow for Hive.
This shows the conceptual architecture — actual USB HID
communication requires the ledgercomm or ledgerhq libraries.
"""
from dataclasses import dataclass
from abc import ABC, abstractmethod
from beem.transactionbuilder import TransactionBuilder
from beem import Hive
from beembase.operations import Transfer
import struct

# Abstract interface for any hardware signer
class HardwareSigner(ABC):
    @abstractmethod
    def get_public_key(self, derivation_path: str) -> str:
        """Retrieve the public key from the device."""
        ...

    @abstractmethod
    def sign_transaction(self, tx_bytes: bytes, derivation_path: str) -> bytes:
        """Send serialized tx to device, user confirms, returns signature."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

# Ledger implementation sketch
@dataclass
class LedgerHiveSigner(HardwareSigner):
    """
    Communicates with the Hive app on Ledger Nano S/X.
    Derivation path for Hive: m/44'/13'/0'/0/0
    """
    HIVE_DERIVATION = "m/44'/13'/0'/0/0"
    CLA = 0xD4  # Hive app CLA byte

    def is_connected(self) -> bool:
        try:
            # In practice: open USB HID, send ping APDU
            # from ledgercomm import Transport
            # transport = Transport.create()
            return True
        except Exception:
            return False

    def get_public_key(self, derivation_path: str = HIVE_DERIVATION) -> str:
        # APDU: CLA=0xD4, INS=0x02 (GET_PUBLIC_KEY)
        # Device returns compressed public key bytes
        # Convert to STM/Hive public key format
        raise NotImplementedError("Requires ledgercomm Transport")

    def sign_transaction(self, tx_bytes: bytes, derivation_path: str = HIVE_DERIVATION) -> bytes:
        # APDU: CLA=0xD4, INS=0x04 (SIGN_TX)
        # Send tx in chunks (max 255 bytes per APDU)
        # Device displays: operation type, amount, recipient
        # User presses both buttons to confirm
        # Returns 65-byte signature (recovery_id + r + s)
        raise NotImplementedError("Requires ledgercomm Transport")

# Integration with beem
def transfer_with_hardware(signer: HardwareSigner, from_acc: str, to: str, amount: str):
    hive = Hive(node=["https://api.hive.blog"])

    # Step 1: Build unsigned transaction
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Transfer(**{
        "from": from_acc, "to": to,
        "amount": amount, "memo": ""
    }))

    # Step 2: Serialize for the device
    tx_bytes = bytes(tx)

    # Step 3: Sign on hardware (user confirms on screen)
    if not signer.is_connected():
        raise RuntimeError("Connect your Ledger and open the Hive app")

    signature = signer.sign_transaction(tx_bytes)

    # Step 4: Attach signature and broadcast
    tx.appendSignature(signature)
    return tx.broadcast()

# Key benefit: private key NEVER exists on the computer.
# Even malware cannot extract it.
```'''
    ),
    (
        "hive_security/rate-limiting-api-abuse",
        r'''How do I implement rate limiting in a Hive API wrapper to prevent key abuse and excessive broadcasting?''',
        r'''<think>
Rate limiting for Hive API wrappers serves two purposes: protecting against
accidental broadcast floods (which waste RC) and preventing API key abuse in
multi-user services. A token bucket algorithm works well — allows bursts but
enforces a sustained rate. We should limit both API reads (node queries) and
writes (broadcasts) separately, since broadcasts have real costs. Per-account
limiting is important for services handling multiple users.
</think>

```python
import time
import threading
from collections import defaultdict
from functools import wraps
from dataclasses import dataclass, field

@dataclass
class TokenBucket:
    rate: float         # tokens per second
    capacity: float     # max burst
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def consume(self, n: float = 1.0) -> bool:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False

    def wait_and_consume(self, n: float = 1.0):
        while not self.consume(n):
            time.sleep(0.05)

class HiveRateLimiter:
    """Per-account rate limiting for Hive API operations."""

    def __init__(
        self,
        read_rate: float = 10.0,    # reads/sec
        read_burst: int = 30,
        write_rate: float = 0.5,    # broadcasts/sec (1 every 2s)
        write_burst: int = 3,
    ):
        self.read_rate = read_rate
        self.read_burst = read_burst
        self.write_rate = write_rate
        self.write_burst = write_burst
        self._read_buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(read_rate, read_burst)
        )
        self._write_buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(write_rate, write_burst)
        )
        self._global_write = TokenBucket(write_rate * 5, write_burst * 5)

    def check_read(self, account: str) -> bool:
        return self._read_buckets[account].consume()

    def check_write(self, account: str) -> bool:
        if not self._global_write.consume():
            return False
        return self._write_buckets[account].consume()

    def wait_read(self, account: str):
        self._read_buckets[account].wait_and_consume()

    def wait_write(self, account: str):
        self._global_write.wait_and_consume()
        self._write_buckets[account].wait_and_consume()

# Decorator for rate-limited API functions
limiter = HiveRateLimiter()

def rate_limited(op_type: str = "read"):
    def decorator(func):
        @wraps(func)
        def wrapper(account: str, *args, **kwargs):
            if op_type == "write":
                if not limiter.check_write(account):
                    raise RuntimeError(f"Rate limit exceeded for @{account} (write)")
            else:
                if not limiter.check_read(account):
                    raise RuntimeError(f"Rate limit exceeded for @{account} (read)")
            return func(account, *args, **kwargs)
        return wrapper
    return decorator

@rate_limited("read")
def get_account_info(account: str) -> dict:
    from beem.account import Account
    return Account(account).json()

@rate_limited("write")
def broadcast_vote(account: str, author: str, permlink: str, weight: int):
    from beem.comment import Comment
    c = Comment(f"@{author}/{permlink}")
    c.upvote(weight, voter=account)
```'''
    ),
    (
        "hive_security/permission-escalation-detection",
        r'''How can I detect if someone is trying to escalate permissions on a Hive account, e.g., adding their key to active or owner authority?''',
        r'''<think>
Permission escalation on Hive happens via account_update or account_update2
operations. An attacker who compromises the active key can add their own key to
the owner authority if the account doesn't have proper recovery set up. We need to
stream operations in real-time and flag any authority changes — especially additions
of unknown keys/accounts to higher-privilege roles. Comparing against a whitelist
of expected keys is the core detection mechanism.
</think>

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.account import Account
from datetime import datetime
import json

class EscalationDetector:
    def __init__(self, watched_accounts: dict[str, dict]):
        """
        watched_accounts format:
        {
            "myaccount": {
                "expected_owner_keys": ["STM..."],
                "expected_active_keys": ["STM..."],
                "expected_active_accounts": [],  # no account auths expected
            }
        }
        """
        self.watched = watched_accounts
        self.hive = Hive(node=["https://api.hive.blog"])

    def analyze_op(self, op: dict) -> list[str]:
        alerts = []
        op_type = op.get("type", "")
        op_value = op.get("value", op)

        if op_type not in ("account_update", "account_update2"):
            return alerts

        account = op_value.get("account", "")
        if account not in self.watched:
            return alerts

        config = self.watched[account]

        # Check each authority level for unexpected additions
        for role in ("owner", "active", "posting"):
            auth = op_value.get(role)
            if not auth:
                continue

            expected_keys = set(config.get(f"expected_{role}_keys", []))
            expected_accounts = set(config.get(f"expected_{role}_accounts", []))

            actual_keys = {k[0] for k in auth.get("key_auths", [])}
            actual_accounts = {a[0] for a in auth.get("account_auths", [])}

            unknown_keys = actual_keys - expected_keys
            unknown_accounts = actual_accounts - expected_accounts

            if unknown_keys:
                alerts.append(
                    f"ESCALATION: Unknown {role} key(s) added to @{account}: "
                    f"{unknown_keys}"
                )
            if unknown_accounts:
                alerts.append(
                    f"ESCALATION: Unknown {role} account auth(s) added to @{account}: "
                    f"{unknown_accounts}"
                )

            # Threshold lowering is also suspicious
            threshold = auth.get("weight_threshold", 1)
            if threshold < 1:
                alerts.append(
                    f"ESCALATION: {role} weight_threshold set to {threshold} on @{account}"
                )

        return alerts

    def stream_monitor(self):
        """Monitor the blockchain in real-time for authority changes."""
        chain = Blockchain(blockchain_instance=self.hive)
        print(f"Monitoring {len(self.watched)} accounts for escalation...")

        for op in chain.stream(opNames=["account_update", "account_update2"]):
            alerts = self.analyze_op(op)
            for alert_msg in alerts:
                ts = datetime.utcnow().isoformat()
                print(f"[{ts}] {alert_msg}")
                # In production: send to Discord/Telegram/email
                notify_security_team(alert_msg)

def notify_security_team(message: str):
    """Replace with actual notification (webhook, email, etc.)."""
    print(f"SECURITY ALERT: {message}")

# Usage
detector = EscalationDetector({
    "myaccount": {
        "expected_owner_keys": ["STM6...myowner"],
        "expected_active_keys": ["STM7...myactive"],
        "expected_active_accounts": [],
        "expected_posting_keys": ["STM8...myposting"],
        "expected_posting_accounts": ["ecency.app"],
    }
})
# detector.stream_monitor()
```'''
    ),
    (
        "hive_security/safe-delegation-patterns",
        r'''What are safe patterns for delegating Hive Power or posting authority to apps while limiting exposure?''',
        r'''<think>
Delegation on Hive comes in two forms: HP delegation (delegate_vesting_shares)
and posting authority (adding app account to posting account_auths). Both carry
risk. For HP delegation, the delegator's tokens are locked but the delegatee can
use the RC/voting power — if the app misbehaves, you lose nothing but must wait
to undelegate. For posting authority, the app can post/vote as you — scope it
carefully. Best practice: never delegate active authority, use minimum HP needed,
monitor delegation usage, and set up alerts for unusual activity.
</think>

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta

class SafeDelegationManager:
    """Manage HP and authority delegations with safety limits."""

    def __init__(self, account: str, active_key: str):
        self.account = account
        self.hive = Hive(
            node=["https://api.hive.blog"],
            keys=[active_key]
        )

    def delegate_hp_safely(
        self,
        delegatee: str,
        hp_amount: float,
        max_percent: float = 10.0,
    ):
        """Delegate HP with a cap on percentage of total HP."""
        acc = Account(self.account, blockchain_instance=self.hive)
        total_hp = float(acc.get_hive_power())

        if hp_amount / total_hp * 100 > max_percent:
            raise ValueError(
                f"Refusing to delegate {hp_amount:.3f} HP — exceeds "
                f"{max_percent}% of total ({total_hp:.3f} HP)"
            )

        acc.delegate_vesting_shares(delegatee, hp_amount)
        print(f"Delegated {hp_amount:.3f} HP to @{delegatee}")

    def grant_posting_authority(self, app_account: str):
        """Grant posting authority to an app (NEVER active/owner)."""
        acc = Account(self.account, blockchain_instance=self.hive)
        current_auths = [a[0] for a in acc["posting"]["account_auths"]]

        if app_account in current_auths:
            print(f"@{app_account} already has posting authority")
            return

        acc.allow(
            foreign=app_account,
            weight=1,
            permission="posting",  # NEVER "active" or "owner"
            threshold=1,
        )
        print(f"Granted posting authority to @{app_account}")

    def revoke_posting_authority(self, app_account: str):
        acc = Account(self.account, blockchain_instance=self.hive)
        acc.disallow(foreign=app_account, permission="posting")
        print(f"Revoked posting authority from @{app_account}")

    def audit_delegations(self) -> dict:
        """List all outgoing delegations and posting auths."""
        acc = Account(self.account, blockchain_instance=self.hive)
        delegations = list(acc.get_vesting_delegations())
        posting_auths = [a[0] for a in acc["posting"]["account_auths"]]

        report = {
            "hp_delegations": [
                {"to": d["delegatee"], "hp": float(d["vesting_shares"])}
                for d in delegations
            ],
            "posting_auths": posting_auths,
            "active_auths": [a[0] for a in acc["active"]["account_auths"]],
        }

        # Flag any active authority delegations as dangerous
        if report["active_auths"]:
            print(f"WARNING: Active authority granted to: {report['active_auths']}")
            print("This is dangerous — consider revoking immediately!")

        return report

    def undelegate_all(self):
        """Emergency: remove all HP delegations."""
        acc = Account(self.account, blockchain_instance=self.hive)
        for d in acc.get_vesting_delegations():
            acc.delegate_vesting_shares(d["delegatee"], 0)
            print(f"Undelegated from @{d['delegatee']}")

# Usage
mgr = SafeDelegationManager("myaccount", "5Jactive...")
# mgr.delegate_hp_safely("ecency.app", 50.0, max_percent=5.0)
# mgr.grant_posting_authority("ecency.app")
# print(mgr.audit_delegations())
```

Rules: never delegate active authority, cap HP delegations, audit regularly.'''
    ),
    (
        "hive_security/secure-custom-json-signing",
        r'''How do I securely sign and broadcast custom_json operations on Hive, choosing the right authority level?''',
        r'''<think>
custom_json is one of the most used operations on Hive — apps like Splinterlands,
Hive Engine, and social apps all use it. The security choice is between
required_posting_auths (social, game actions) and required_auths (financial, tokens).
Using the wrong level is a common mistake: signing with active when posting would
suffice exposes the more powerful key unnecessarily. The id field determines which
app processes it. Always validate the JSON payload before signing.
</think>

```python
import json
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json

def sign_custom_json(
    account: str,
    json_id: str,
    payload: dict,
    key_type: str = "posting",
    wif: str = "",
) -> dict:
    """
    Securely sign and broadcast a custom_json operation.

    key_type: "posting" for social/game actions, "active" for financial.
    """
    # Validate inputs
    if key_type not in ("posting", "active"):
        raise ValueError("key_type must be 'posting' or 'active'")
    if not json_id or len(json_id) > 32:
        raise ValueError("json_id must be 1-32 characters")

    serialized = json.dumps(payload, separators=(",", ":"))
    if len(serialized) > 8192:
        raise ValueError(f"Payload too large: {len(serialized)} > 8192 bytes")

    hive = Hive(node=["https://api.hive.blog"], keys=[wif])
    tx = TransactionBuilder(blockchain_instance=hive)

    op_data = {
        "required_auths": [account] if key_type == "active" else [],
        "required_posting_auths": [account] if key_type == "posting" else [],
        "id": json_id,
        "json": serialized,
    }
    tx.appendOps(Custom_json(**op_data))
    tx.appendSigner(account, key_type)
    tx.sign()
    return tx.broadcast()

# --- Authority level guide ---

# POSTING key (lower risk):
# Social follows
sign_custom_json(
    "myaccount", "follow",
    ["follow", {"follower": "myaccount", "following": "alice", "what": ["blog"]}],
    key_type="posting", wif="5Jposting..."
)

# Splinterlands game action
sign_custom_json(
    "myaccount", "sm_submit_team",
    {"trx_id": "abc123", "team": [...]},
    key_type="posting", wif="5Jposting..."
)

# ACTIVE key (financial — use only when required):
# Hive Engine token transfer
sign_custom_json(
    "myaccount", "ssc-mainnet-hive",
    {"contractName": "tokens", "contractAction": "transfer",
     "contractPayload": {"symbol": "BEE", "to": "bob", "quantity": "10"}},
    key_type="active", wif="5Jactive..."
)

# --- Payload validation before signing ---
def validate_hive_engine_payload(payload: dict) -> bool:
    """Validate Hive Engine payloads before signing with active key."""
    required = {"contractName", "contractAction", "contractPayload"}
    if not required.issubset(payload.keys()):
        return False
    # Whitelist allowed contract actions
    safe_actions = {
        ("tokens", "transfer"),
        ("tokens", "stake"),
        ("market", "buy"),
        ("market", "sell"),
    }
    pair = (payload["contractName"], payload["contractAction"])
    if pair not in safe_actions:
        print(f"WARNING: Unrecognized action {pair} — review carefully")
        return False
    return True
```'''
    ),
    (
        "hive_security/account-blacklist-whitelist",
        r'''How do I implement an account blacklist/whitelist system for a Hive dApp that filters interactions?''',
        r'''<think>
A blacklist/whitelist system for Hive dApps controls which accounts can interact
with the service. Common use cases: blocking spam accounts, restricting access to
known users, preventing abuse. The system should be efficient for lookups, support
both approaches, and integrate with the app's transaction processing. Using
@hivewatchers or @spaminator lists as seed data is practical. Store lists in a
database with reason/timestamp for auditing.
</think>

```python
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class ListAction(Enum):
    ALLOW = "allow"
    DENY = "deny"

@dataclass
class ListEntry:
    account: str
    action: ListAction
    reason: str
    added_by: str
    timestamp: float = field(default_factory=time.time)
    expires: Optional[float] = None

class AccountFilter:
    """Blacklist/whitelist system for Hive dApp interactions."""

    def __init__(self, default_action: ListAction = ListAction.ALLOW):
        self.default = default_action
        self._entries: dict[str, ListEntry] = {}
        self._on_chain_lists: set[str] = set()

    def add(self, account: str, action: ListAction, reason: str,
            added_by: str = "system", ttl_hours: float = 0):
        expires = time.time() + ttl_hours * 3600 if ttl_hours > 0 else None
        self._entries[account] = ListEntry(
            account=account, action=action, reason=reason,
            added_by=added_by, expires=expires,
        )

    def remove(self, account: str):
        self._entries.pop(account, None)

    def check(self, account: str) -> tuple[ListAction, str]:
        """Returns (action, reason). Respects expiry."""
        entry = self._entries.get(account)
        if entry:
            if entry.expires and time.time() > entry.expires:
                del self._entries[account]
            else:
                return entry.action, entry.reason

        # Check on-chain blacklists
        if account in self._on_chain_lists:
            return ListAction.DENY, "On-chain blacklist"

        return self.default, "default policy"

    def load_on_chain_blacklist(self, list_account: str = "hivewatchers"):
        """Seed from on-chain blacklist via muted list."""
        from beem.account import Account
        acc = Account(list_account)
        for muted in acc.get_muted():
            self._on_chain_lists.add(muted)
        print(f"Loaded {len(self._on_chain_lists)} accounts from @{list_account}")

    def is_allowed(self, account: str) -> bool:
        action, _ = self.check(account)
        return action == ListAction.ALLOW

    def get_denied(self) -> list[ListEntry]:
        return [e for e in self._entries.values()
                if e.action == ListAction.DENY
                and (not e.expires or time.time() <= e.expires)]

# --- Integration with request handling ---
acl = AccountFilter(default_action=ListAction.ALLOW)

# Block known spammers
acl.add("spammer123", ListAction.DENY, "Comment spam", added_by="admin")
# Temporary ban (24 hours)
acl.add("abuser456", ListAction.DENY, "Vote abuse", ttl_hours=24)
# Load community blacklists
# acl.load_on_chain_blacklist("hivewatchers")

# Whitelist mode (deny by default)
strict_acl = AccountFilter(default_action=ListAction.DENY)
strict_acl.add("trusteduser", ListAction.ALLOW, "Verified member")

# In your API handler:
def handle_request(account: str, action: str):
    if not acl.is_allowed(account):
        _, reason = acl.check(account)
        return {"error": f"Account blocked: {reason}"}
    # Process normally
    return {"status": "ok"}
```'''
    ),
    (
        "hive_security/memo-key-encrypted-dms",
        r'''How do I use the Hive memo key to send and receive encrypted private messages?''',
        r'''<think>
Hive's memo key enables end-to-end encrypted messages via transfer memos. When a
memo starts with '#', it's encrypted using ECIES (shared secret from sender's memo
private key + recipient's memo public key). Only the sender and recipient can
decrypt. This can be used beyond transfers — you can build a DM system by sending
0.001 HIVE transfers with encrypted memos, or use custom_json with encrypted payloads.
The beem library handles the crypto transparently.
</think>

```python
from beem import Hive
from beem.account import Account
from beem.memo import Memo
from beemgraphenebase.account import PrivateKey
from beemgraphenebase.ecdasig import shared_secret
import hashlib
import json

# --- Basic encrypted memo via transfer ---

def send_encrypted_message(
    sender: str,
    recipient: str,
    message: str,
    memo_private_key: str,
    active_key: str,
):
    """Send an encrypted message as a transfer memo (prefix with #)."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[active_key, memo_private_key]
    )
    acc = Account(sender, blockchain_instance=hive)
    # Prefix '#' triggers encryption
    acc.transfer(recipient, 0.001, "HIVE", memo=f"#{message}")
    print(f"Encrypted message sent to @{recipient}")

def read_encrypted_memos(
    account: str,
    memo_private_key: str,
    limit: int = 20,
):
    """Decrypt incoming transfer memos."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[memo_private_key]
    )
    acc = Account(account, blockchain_instance=hive)
    memo = Memo(blockchain_instance=hive)

    history = acc.get_account_history(-1, limit, only_ops=["transfer"])
    messages = []
    for op in history:
        raw_memo = op["memo"]
        if raw_memo.startswith("#"):
            try:
                decrypted = memo.decrypt(raw_memo)
                messages.append({
                    "from": op["from"],
                    "to": op["to"],
                    "message": decrypted,
                    "timestamp": op.get("timestamp", ""),
                })
            except Exception:
                messages.append({
                    "from": op["from"],
                    "message": "[unable to decrypt]",
                })
    return messages

# --- DM system using custom_json (no transfer needed) ---

def send_dm_custom_json(
    sender: str,
    recipient: str,
    message: str,
    memo_private_key: str,
    posting_key: str,
):
    """
    Encrypt a DM using memo keys and send as custom_json.
    Avoids the 0.001 HIVE cost of transfers.
    """
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[posting_key, memo_private_key]
    )
    memo = Memo(blockchain_instance=hive)
    memo.hive = hive
    encrypted = memo.encrypt(f"#{message}")

    from beem.transactionbuilder import TransactionBuilder
    from beembase.operations import Custom_json
    import json as _json

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [sender],
        "id": "encrypted_dm",
        "json": _json.dumps({
            "to": recipient,
            "msg": encrypted,
            "v": 1,
        }),
    }))
    tx.appendSigner(sender, "posting")
    tx.sign()
    tx.broadcast()

# --- Read DMs ---
messages = read_encrypted_memos("myaccount", "5Jmemo_private_key...")
for m in messages:
    print(f"From @{m['from']}: {m['message']}")
```

Only the sender and recipient can decrypt — not even Hive nodes/witnesses can read the content.'''
    ),
    (
        "hive_security/witness-key-security",
        r'''What are best practices for securing witness signing keys used in Hive block production?''',
        r'''<think>
Witness signing keys are used every time a witness produces a block (every 63
seconds in top 20). Compromise means an attacker can sign invalid blocks or double-
produce, leading to missed blocks and potential removal. Best practices: use a
dedicated key (not owner/active), run the key only on the block-producing node,
use a failover setup with different keys, rotate keys regularly, and never expose
the signing key in backups or config management systems without encryption.
</think>

```python
"""
Witness signing key security checklist and automation.
"""
from beem import Hive
from beem.witness import Witness
from beemgraphenebase.account import PrivateKey
import os
import json
import hashlib

class WitnessKeySecurity:
    def __init__(self, witness_name: str, active_key: str):
        self.witness = witness_name
        self.hive = Hive(
            node=["https://api.hive.blog"],
            keys=[active_key]
        )

    def generate_signing_keypair(self) -> tuple[str, str]:
        """Generate a fresh signing key pair. Private key for config.ini only."""
        priv = PrivateKey()
        pub = str(priv.pubkey)
        return str(priv), pub

    def rotate_key(self, new_public_key: str):
        """Update the signing key on-chain. Restart node immediately after."""
        w = Witness(self.witness, blockchain_instance=self.hive)
        w.update(signing_key=new_public_key, url=w["url"], props=w["props"])
        print(f"Signing key updated on-chain to {new_public_key[:20]}...")

    def disable_witness(self):
        """Emergency: set signing key to null (STM1111...) to stop producing."""
        NULL_KEY = "STM1111111111111111111111111111111114T1Anm"
        w = Witness(self.witness, blockchain_instance=self.hive)
        w.update(signing_key=NULL_KEY, url=w["url"], props=w["props"])
        print("Witness DISABLED — signing key set to null")

    def verify_current_key(self, expected_public: str) -> bool:
        w = Witness(self.witness, blockchain_instance=self.hive)
        actual = w["signing_key"]
        match = actual == expected_public
        if not match:
            print(f"KEY MISMATCH! Expected: {expected_public[:20]}...")
            print(f"             Actual:   {actual[:20]}...")
        return match

    def check_missed_blocks(self, threshold: int = 5) -> bool:
        """Alert if missed blocks exceed threshold (possible key compromise)."""
        w = Witness(self.witness, blockchain_instance=self.hive)
        missed = w["total_missed"]
        if missed > threshold:
            print(f"WARNING: {missed} total missed blocks")
            return True
        return False

def generate_secure_config(witness_name: str, signing_key: str) -> str:
    """Generate a config.ini snippet — NEVER commit this to version control."""
    config = f"""# --- Witness config (CONFIDENTIAL) ---
# Generated: keep this file chmod 600 and off version control
witness = "{witness_name}"
private-key = {signing_key}

# Security hardening
enable-stale-production = false
required-participation = 33
p2p-max-connections = 100
webserver-http-endpoint = 127.0.0.1:8091
webserver-ws-endpoint = 127.0.0.1:8090
"""
    return config

# --- Security checklist ---
CHECKLIST = [
    "Signing key is NOT the same as owner/active/posting key",
    "Signing private key exists ONLY on the witness node",
    "config.ini has chmod 600 (owner read/write only)",
    "config.ini is NOT in version control (.gitignore)",
    "Failover node uses a DIFFERENT signing key",
    "Key rotation scheduled (monthly minimum)",
    "Missed block monitoring is active",
    "Emergency disable procedure documented and tested",
    "Node API is bound to 127.0.0.1 (not 0.0.0.0)",
    "SSH access to witness node uses key auth only (no passwords)",
]

for i, item in enumerate(CHECKLIST, 1):
    print(f"  [{' '}] {i}. {item}")
```'''
    ),
    (
        "hive_security/secure-node-api-config",
        r'''How do I secure a Hive API node so only authorized clients can access write endpoints?''',
        r'''<think>
Public Hive API nodes expose both read (condenser_api, database_api) and write
(network_broadcast_api) endpoints. For a private or semi-private node, you want
to restrict who can broadcast transactions while keeping reads open (or restricted
too). Options: bind to localhost + reverse proxy with auth, API plugin selection
(don't load broadcast plugin if read-only), IP whitelisting in the proxy, and
API key authentication at the proxy layer. NGINX is the standard reverse proxy.
</think>

```python
"""
Secure Hive node API configuration patterns.
Includes config.ini settings and NGINX reverse proxy config.
"""

# --- config.ini: minimize exposed API plugins ---
HIVE_CONFIG_READONLY = """
# Read-only node — no broadcast capability
plugin = condenser_api database_api block_api
plugin = account_history_api account_history_rocksdb
# DO NOT include: network_broadcast_api, wallet_bridge_api

# Bind to localhost only — NGINX handles external access
webserver-http-endpoint = 127.0.0.1:8091
webserver-ws-endpoint = 127.0.0.1:8090

# Disable P2P if this is purely an API node
p2p-endpoint = 0.0.0.0:0
"""

HIVE_CONFIG_FULL = """
# Full node with broadcast — protect with reverse proxy
plugin = condenser_api database_api block_api
plugin = network_broadcast_api
plugin = account_history_api account_history_rocksdb

webserver-http-endpoint = 127.0.0.1:8091
webserver-ws-endpoint = 127.0.0.1:8090
"""

# --- NGINX reverse proxy with API key auth ---
NGINX_CONFIG = r"""
upstream hive_node {
    server 127.0.0.1:8091;
}

# Rate limiting zones
limit_req_zone $binary_remote_addr zone=hive_read:10m rate=30r/s;
limit_req_zone $binary_remote_addr zone=hive_write:10m rate=2r/s;

server {
    listen 443 ssl;
    server_name api.myhivenode.com;

    ssl_certificate /etc/letsencrypt/live/api.myhivenode.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.myhivenode.com/privkey.pem;

    # Read endpoints — open with rate limiting
    location / {
        limit_req zone=hive_read burst=10 nodelay;

        # Block broadcast methods at the proxy level
        if ($request_body ~* "network_broadcast_api") {
            return 403;
        }

        proxy_pass http://hive_node;
        proxy_set_header Host $host;
    }

    # Write endpoint — API key required
    location /broadcast {
        limit_req zone=hive_write burst=3 nodelay;

        # Require API key header
        if ($http_x_api_key = "") {
            return 401;
        }
        if ($http_x_api_key != "YOUR_SECRET_API_KEY_HERE") {
            return 403;
        }

        proxy_pass http://hive_node;
        proxy_set_header Host $host;
    }
}
"""

# --- Python client for authenticated broadcast ---
import requests

class SecureHiveClient:
    def __init__(self, node_url: str, api_key: str = ""):
        self.node_url = node_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()

    def api_call(self, method: str, params: list) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }

        headers = {"Content-Type": "application/json"}
        is_broadcast = "broadcast" in method

        url = self.node_url
        if is_broadcast:
            url = f"{self.node_url}/broadcast"
            if self.api_key:
                headers["X-API-Key"] = self.api_key

        resp = self.session.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_account(self, name: str) -> dict:
        return self.api_call("condenser_api.get_accounts", [[name]])

    def broadcast_tx(self, signed_tx: dict) -> dict:
        return self.api_call(
            "condenser_api.broadcast_transaction",
            [signed_tx]
        )

# Usage
client = SecureHiveClient("https://api.myhivenode.com", api_key="secret123")
```'''
    ),
    (
        "hive_security/secure-account-creation",
        r'''How do I create a new Hive account with securely generated keys?''',
        r'''<think>
Account creation on Hive requires generating 4 key pairs (owner, active, posting,
memo) from a master password or independently. The secure approach: generate a
strong random master password, derive keys deterministically, or generate 4
independent keys. Never transmit the master password or private keys over the
network. The account creation itself requires either paying the account creation
fee or using account creation tokens (claimed via RC). Keys should be shown to
the user once and never stored server-side.
</think>

```python
from beemgraphenebase.account import PasswordKey, PrivateKey
import secrets
import string
from beem import Hive
from beem.account import Account

def generate_master_password(length: int = 52) -> str:
    """Generate a cryptographically secure master password."""
    alphabet = string.ascii_letters + string.digits
    return "P5" + "".join(secrets.choice(alphabet) for _ in range(length))

def derive_keys(account_name: str, master_password: str) -> dict:
    """Derive all 4 key pairs from master password (Hive standard derivation)."""
    keys = {}
    for role in ("owner", "active", "posting", "memo"):
        pk = PasswordKey(account_name, master_password, role=role)
        private = pk.get_private_key()
        public = pk.get_public_key()
        keys[role] = {
            "private": str(private),  # WIF format
            "public": str(public),    # STM... format
        }
    return keys

def create_account_with_fee(
    creator: str,
    creator_active_key: str,
    new_account: str,
    fee: str = "3.000 HIVE",
) -> dict:
    """Create a new account using the account creation fee."""
    master_password = generate_master_password()
    keys = derive_keys(new_account, master_password)

    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[creator_active_key]
    )
    creator_acc = Account(creator, blockchain_instance=hive)

    creator_acc.create_account(
        new_account,
        owner_key=keys["owner"]["public"],
        active_key=keys["active"]["public"],
        posting_key=keys["posting"]["public"],
        memo_key=keys["memo"]["public"],
        password=None,  # We provide keys directly
        creator=creator,
        storekeys=False,  # NEVER store keys server-side
    )

    # Return keys to the user — display ONCE, never store
    return {
        "account": new_account,
        "master_password": master_password,
        "keys": keys,
        "WARNING": "Save these keys NOW. They cannot be recovered.",
    }

def create_account_with_token(
    creator: str,
    creator_active_key: str,
    new_account: str,
) -> dict:
    """Create account using claimed account creation tokens (free, costs RC)."""
    master_password = generate_master_password()
    keys = derive_keys(new_account, master_password)

    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[creator_active_key]
    )

    # First claim a token (if not already claimed)
    creator_acc = Account(creator, blockchain_instance=hive)
    pending_tokens = creator_acc.get("pending_claimed_accounts", 0)

    if pending_tokens < 1:
        creator_acc.claim_account()  # Spends RC to claim a token
        print("Claimed 1 account creation token")

    creator_acc.create_claimed_account(
        new_account,
        owner_key=keys["owner"]["public"],
        active_key=keys["active"]["public"],
        posting_key=keys["posting"]["public"],
        memo_key=keys["memo"]["public"],
    )

    return {
        "account": new_account,
        "master_password": master_password,
        "keys": keys,
    }

# --- Security best practices for key display ---
def display_keys_securely(result: dict):
    print("=" * 60)
    print(f"Account created: @{result['account']}")
    print("=" * 60)
    print(f"Master Password: {result['master_password']}")
    print()
    for role, kp in result["keys"].items():
        print(f"{role.upper():>8} (private): {kp['private']}")
        print(f"{role.upper():>8} (public):  {kp['public']}")
    print()
    print("SAVE THESE KEYS IMMEDIATELY.")
    print("They will NOT be shown again and cannot be recovered.")
    print("=" * 60)
```'''
    ),
    (
        "hive_security/two-factor-auth-patterns",
        r'''How can I implement two-factor authentication for a Hive dApp since the blockchain itself has no 2FA?''',
        r'''<think>
Hive has no native 2FA — transactions are authorized by key signatures alone. But
dApps can add a 2FA layer at the application level. The pattern: the app holds a
co-signing key added to the user's posting or active authority (multi-sig), and
only co-signs after the user provides a TOTP code. This way, even if the user's
key is stolen, the attacker also needs the TOTP. The user's authority threshold
is set to 2, with their key weight 1 and the app's key weight 1.
</think>

```python
import pyotp
import time
import hashlib
from dataclasses import dataclass
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer

@dataclass
class TwoFactorUser:
    account: str
    totp_secret: str  # base32 encoded secret
    app_cosign_key: str  # app's private key added to user's authority
    enabled: bool = True

class HiveTwoFactor:
    """2FA for Hive dApps using multi-sig + TOTP."""

    def __init__(self, app_account: str, app_active_key: str):
        self.app_account = app_account
        self.hive = Hive(
            node=["https://api.hive.blog"],
            keys=[app_active_key]
        )
        self.users: dict[str, TwoFactorUser] = {}

    def enroll_user(self, account: str) -> dict:
        """Generate TOTP secret and set up multi-sig authority."""
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=f"@{account}",
            issuer_name="MyHiveDApp"
        )

        # Store enrollment (in production: encrypted database)
        self.users[account] = TwoFactorUser(
            account=account,
            totp_secret=secret,
            app_cosign_key=self.hive.wallet.getActiveKeyForAccount(self.app_account),
        )

        return {
            "secret": secret,
            "qr_uri": provisioning_uri,
            "instructions": (
                "1. Scan QR code in your authenticator app\n"
                "2. Add our app to your active authority (threshold=2)\n"
                "3. Your key weight=1, our co-sign key weight=1\n"
                "4. Both signatures needed = 2FA"
            ),
        }

    def verify_totp(self, account: str, code: str) -> bool:
        user = self.users.get(account)
        if not user or not user.enabled:
            return False
        totp = pyotp.TOTP(user.totp_secret)
        return totp.verify(code, valid_window=1)  # 30s window

    def co_sign_transaction(
        self,
        account: str,
        totp_code: str,
        tx_builder: TransactionBuilder,
    ) -> dict:
        """Co-sign a user's transaction after TOTP verification."""
        if not self.verify_totp(account, totp_code):
            raise PermissionError("Invalid 2FA code")

        # User already signed with their key (weight=1)
        # App co-signs to reach threshold (weight=2)
        tx_builder.appendSigner(self.app_account, "active")
        tx_builder.sign()
        result = tx_builder.broadcast()
        return result

# --- Client-side usage flow ---
def send_with_2fa(user_account: str, user_key: str, to: str, amount: str,
                  totp_code: str, tfa_service: HiveTwoFactor):
    # Step 1: User builds and signs with their key
    hive = Hive(node=["https://api.hive.blog"], keys=[user_key])
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Transfer(**{
        "from": user_account, "to": to,
        "amount": amount, "memo": ""
    }))
    tx.appendSigner(user_account, "active")
    tx.sign()

    # Step 2: App verifies TOTP and co-signs
    result = tfa_service.co_sign_transaction(user_account, totp_code, tx)
    return result

# Setup
# tfa = HiveTwoFactor("myapp", "5Japp_active_key")
# enrollment = tfa.enroll_user("alice")
# print(enrollment["qr_uri"])  # User scans this
```

The key insight: blockchain sees a valid multi-sig transaction. The 2FA layer is enforced by the app refusing to co-sign without a valid TOTP code.'''
    ),
    (
        "hive_security/secure-transfer-validation",
        r'''How do I build a transfer confirmation system that validates and shows details to the user before broadcasting?''',
        r'''<think>
Transfer validation is critical for preventing accidental or malicious fund loss.
The system should: parse and display all operation details, verify the recipient
exists, check the amount against safety limits, validate memo format, and require
explicit user confirmation before broadcast. This is especially important in CLI
tools and backend services where a bug could drain accounts. Never auto-broadcast
transfers without human review.
</think>

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer
from dataclasses import dataclass

@dataclass
class TransferValidation:
    valid: bool
    warnings: list[str]
    errors: list[str]
    display: str

class SecureTransferBuilder:
    """Build and validate transfers with confirmation before broadcast."""

    def __init__(self, account: str, active_key: str,
                 daily_limit: float = 100.0):
        self.account = account
        self.daily_limit = daily_limit
        self.hive = Hive(
            node=["https://api.hive.blog"],
            keys=[active_key]
        )
        self._daily_sent: float = 0.0

    def validate(self, to: str, amount: str, memo: str = "") -> TransferValidation:
        errors = []
        warnings = []

        # Parse amount
        parts = amount.split()
        if len(parts) != 2 or parts[1] not in ("HIVE", "HBD"):
            errors.append(f"Invalid amount format: {amount!r} (expected '1.000 HIVE')")
            return TransferValidation(False, warnings, errors, "")

        value = float(parts[0])
        asset = parts[1]

        # Check recipient exists
        try:
            recipient = Account(to, blockchain_instance=self.hive)
        except Exception:
            errors.append(f"Recipient @{to} does not exist")
            return TransferValidation(False, warnings, errors, "")

        # Check sender balance
        sender = Account(self.account, blockchain_instance=self.hive)
        balance_key = "balance" if asset == "HIVE" else "hbd_balance"
        available = float(sender[balance_key].amount)
        if value > available:
            errors.append(f"Insufficient {asset}: have {available:.3f}, need {value:.3f}")

        # Daily limit check
        if self._daily_sent + value > self.daily_limit:
            warnings.append(
                f"Daily limit warning: {self._daily_sent + value:.3f} / "
                f"{self.daily_limit:.3f} {asset}"
            )

        # Large transfer warning
        if value > 50:
            warnings.append(f"Large transfer: {value:.3f} {asset}")

        # Memo warnings
        if memo and not memo.startswith("#"):
            warnings.append("Memo is NOT encrypted (visible to everyone)")
        if any(kw in memo.lower() for kw in ["private key", "password", "wif", "5j", "5k"]):
            errors.append("Memo appears to contain a private key — BLOCKED")

        # Account age check (new accounts may be scam accounts)
        created = recipient["created"]
        warnings_text = "\n".join(f"  WARNING: {w}" for w in warnings)
        errors_text = "\n".join(f"  ERROR: {e}" for e in errors)

        display = (
            f"{'=' * 50}\n"
            f"  TRANSFER CONFIRMATION\n"
            f"{'=' * 50}\n"
            f"  From:   @{self.account}\n"
            f"  To:     @{to} (created: {created})\n"
            f"  Amount: {amount}\n"
            f"  Memo:   {memo or '(none)'}\n"
            f"{'=' * 50}\n"
            f"{warnings_text}\n{errors_text}\n"
            f"{'=' * 50}"
        )

        return TransferValidation(
            valid=len(errors) == 0,
            warnings=warnings,
            errors=errors,
            display=display,
        )

    def send_with_confirmation(self, to: str, amount: str, memo: str = "") -> dict:
        validation = self.validate(to, amount, memo)
        print(validation.display)

        if not validation.valid:
            print("Transfer BLOCKED due to errors above.")
            return {"status": "blocked", "errors": validation.errors}

        confirm = input("Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            print("Transfer cancelled.")
            return {"status": "cancelled"}

        acc = Account(self.account, blockchain_instance=self.hive)
        result = acc.transfer(to, float(amount.split()[0]), amount.split()[1], memo)
        self._daily_sent += float(amount.split()[0])
        print("Transfer broadcast successfully.")
        return {"status": "sent", "result": result}

# Usage
# builder = SecureTransferBuilder("myaccount", "5Jactive...", daily_limit=100)
# builder.send_with_confirmation("bob", "10.000 HIVE", "Payment for services")
```'''
    ),
    (
        "hive_security/account-authority-audit",
        r'''How do I audit the full history of authority changes on a Hive account to detect past compromises?''',
        r'''<think>
To audit authority history, we scan account_update and account_update2 operations
in the account's history. Each one records what the authorities were changed to.
By replaying these chronologically, we can see every key addition, removal, and
threshold change. This is essential for forensics after a suspected compromise —
you can identify exactly when an attacker key was added and what actions occurred
between the injection and recovery.
</think>

```python
from beem import Hive
from beem.account import Account
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class AuthChange:
    timestamp: str
    block_num: int
    op_type: str
    changes: list[str] = field(default_factory=list)

def audit_authority_history(account_name: str) -> list[AuthChange]:
    """Scan full account history for authority changes."""
    hive = Hive(node=["https://api.hive.blog"])
    acc = Account(account_name, blockchain_instance=hive)

    auth_changes = []
    prev_state = None

    ops = acc.get_account_history(
        -1, 10000,
        only_ops=["account_update", "account_update2"]
    )

    for op in ops:
        change = AuthChange(
            timestamp=op.get("timestamp", "unknown"),
            block_num=op.get("block", 0),
            op_type=op["type"],
        )

        for role in ("owner", "active", "posting"):
            if role in op:
                auth = op[role]
                keys = [k[0][:20] + "..." for k in auth.get("key_auths", [])]
                accs = [a[0] for a in auth.get("account_auths", [])]
                threshold = auth.get("weight_threshold", 1)
                change.changes.append(
                    f"{role}: threshold={threshold}, "
                    f"keys={keys}, account_auths={accs}"
                )

        if "memo_key" in op:
            change.changes.append(f"memo_key: {op['memo_key'][:20]}...")

        if "json_metadata" in op:
            change.changes.append("json_metadata updated")

        auth_changes.append(change)

    return auth_changes

def print_audit_report(account_name: str):
    changes = audit_authority_history(account_name)

    print(f"Authority Audit Report for @{account_name}")
    print(f"Total authority changes found: {len(changes)}")
    print("=" * 70)

    for i, change in enumerate(changes, 1):
        print(f"\n[{i}] {change.timestamp} (block {change.block_num})")
        print(f"    Operation: {change.op_type}")
        for detail in change.changes:
            print(f"    {detail}")

    # Flag suspicious patterns
    print("\n" + "=" * 70)
    print("SUSPICIOUS PATTERN CHECK:")

    if len(changes) > 10:
        print(f"  [!] High number of authority changes: {len(changes)}")

    # Check for rapid consecutive changes (possible attack + recovery)
    for i in range(1, len(changes)):
        t1 = changes[i-1].timestamp
        t2 = changes[i].timestamp
        try:
            dt1 = datetime.fromisoformat(t1.replace("Z", "+00:00"))
            dt2 = datetime.fromisoformat(t2.replace("Z", "+00:00"))
            delta = (dt2 - dt1).total_seconds()
            if delta < 3600:
                print(f"  [!] Rapid changes at {t1} and {t2} ({delta:.0f}s apart)")
        except (ValueError, TypeError):
            pass

    if not changes:
        print("  No authority changes found — account may use original keys")

# print_audit_report("someaccount")
```'''
    ),
    (
        "hive_security/stolen-account-detection",
        r'''How can I build heuristics to detect if a Hive account has been stolen or compromised?''',
        r'''<think>
Stolen account detection relies on behavioral anomalies: sudden authority changes,
large transfers to unknown accounts, voting pattern shifts, powerdown initiation
right after key change, and activity from new IP/location (if app-level data
available). Chain-level heuristics include: authority change followed immediately
by transfers, powerdown started within hours of key change, transfer to an account
that was recently created, and transfer amounts draining the full balance.
</think>

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class CompromiseIndicator:
    severity: str  # "high", "medium", "low"
    description: str
    timestamp: str
    evidence: str

class StolenAccountDetector:
    def __init__(self):
        self.hive = Hive(node=["https://api.hive.blog"])

    def analyze(self, account_name: str, days: int = 7) -> list[CompromiseIndicator]:
        indicators = []
        acc = Account(account_name, blockchain_instance=self.hive)

        # Gather recent operations
        history = list(acc.get_account_history(
            -1, 1000,
            only_ops=[
                "account_update", "account_update2",
                "transfer", "withdraw_vesting",
                "transfer_to_vesting",
            ]
        ))

        cutoff = datetime.utcnow() - timedelta(days=days)

        auth_changes = []
        transfers_out = []
        powerdowns = []

        for op in history:
            ts_str = op.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00").replace("+00:00", ""))
            except (ValueError, TypeError):
                continue

            if ts < cutoff:
                continue

            if op["type"] in ("account_update", "account_update2"):
                auth_changes.append((ts, op))
            elif op["type"] == "transfer" and op.get("from") == account_name:
                transfers_out.append((ts, op))
            elif op["type"] == "withdraw_vesting":
                powerdowns.append((ts, op))

        # Heuristic 1: Authority change followed by transfers within 1 hour
        for auth_ts, auth_op in auth_changes:
            for xfer_ts, xfer_op in transfers_out:
                delta = (xfer_ts - auth_ts).total_seconds()
                if 0 < delta < 3600:
                    indicators.append(CompromiseIndicator(
                        severity="high",
                        description="Transfer within 1h of authority change",
                        timestamp=str(xfer_ts),
                        evidence=f"Auth change at {auth_ts}, transfer of "
                                 f"{xfer_op.get('amount', '?')} to @{xfer_op.get('to', '?')} "
                                 f"at {xfer_ts} ({delta:.0f}s later)",
                    ))

        # Heuristic 2: Powerdown initiated near authority change
        for auth_ts, _ in auth_changes:
            for pd_ts, pd_op in powerdowns:
                delta = abs((pd_ts - auth_ts).total_seconds())
                if delta < 86400:  # within 24 hours
                    indicators.append(CompromiseIndicator(
                        severity="high",
                        description="Powerdown started within 24h of key change",
                        timestamp=str(pd_ts),
                        evidence=f"Powerdown of {pd_op.get('vesting_shares', '?')}",
                    ))

        # Heuristic 3: Balance-draining transfer
        balance = float(acc["balance"].amount)
        for xfer_ts, xfer_op in transfers_out:
            amount = float(str(xfer_op.get("amount", "0")).split()[0])
            if amount > 0 and balance < 1.0:
                indicators.append(CompromiseIndicator(
                    severity="medium",
                    description="Account balance near zero after transfers",
                    timestamp=str(xfer_ts),
                    evidence=f"Current balance: {balance:.3f} HIVE",
                ))
                break

        # Heuristic 4: Multiple authority changes in short period
        if len(auth_changes) >= 3:
            indicators.append(CompromiseIndicator(
                severity="medium",
                description=f"{len(auth_changes)} authority changes in {days} days",
                timestamp=str(auth_changes[-1][0]),
                evidence="Possible attack + recovery cycle",
            ))

        return indicators

# Usage
detector = StolenAccountDetector()
results = detector.analyze("suspicious_account", days=7)
for r in results:
    print(f"[{r.severity.upper()}] {r.description}")
    print(f"  Time: {r.timestamp}")
    print(f"  Evidence: {r.evidence}")
```'''
    ),
    (
        "hive_security/emergency-key-change",
        r'''My Hive account may be compromised. What is the emergency procedure to change all keys immediately?''',
        r'''<think>
Emergency key change requires the owner key (or account recovery if owner key is
compromised). The procedure: generate new keys immediately, broadcast account_update
with new owner/active/posting/memo keys using the current owner key, then verify
the change took effect. If the owner key is also compromised, initiate account
recovery through the recovery account (usually the account creator). Time is
critical — the attacker may be trying to change keys too. Cancel any pending
powerdowns after securing the account.
</think>

```python
from beem import Hive
from beem.account import Account
from beemgraphenebase.account import PasswordKey, PrivateKey
import secrets
import string
import sys

def emergency_key_change(
    account_name: str,
    current_owner_key: str,
):
    """
    EMERGENCY: Change ALL keys on a Hive account immediately.
    Requires the current owner key.
    """
    print("=" * 60)
    print("  EMERGENCY KEY CHANGE PROCEDURE")
    print(f"  Account: @{account_name}")
    print("=" * 60)

    # Step 1: Generate new master password and derive all keys
    alphabet = string.ascii_letters + string.digits
    new_password = "P5" + "".join(secrets.choice(alphabet) for _ in range(52))

    new_keys = {}
    for role in ("owner", "active", "posting", "memo"):
        pk = PasswordKey(account_name, new_password, role=role)
        new_keys[role] = {
            "private": str(pk.get_private_key()),
            "public": str(pk.get_public_key()),
        }

    # Step 2: Connect with OWNER key and change everything
    hive = Hive(
        node=[
            "https://api.hive.blog",
            "https://api.deathwing.me",  # backup node
        ],
        keys=[current_owner_key]
    )

    try:
        acc = Account(account_name, blockchain_instance=hive)

        # Change all keys in a single account_update
        acc.update_account_keys(
            new_keys["owner"]["public"],
            new_keys["active"]["public"],
            new_keys["posting"]["public"],
            new_keys["memo"]["public"],
        )
        print("[OK] All keys changed on-chain")

    except Exception as e:
        print(f"[FAIL] Key change failed: {e}")
        print("If owner key is compromised, use account recovery instead.")
        print("Contact your recovery account partner immediately.")
        sys.exit(1)

    # Step 3: Cancel any pending powerdowns
    try:
        hive2 = Hive(
            node=["https://api.hive.blog"],
            keys=[new_keys["active"]["private"]]
        )
        acc2 = Account(account_name, blockchain_instance=hive2)
        # Set withdraw to 0 to cancel powerdown
        acc2.withdraw_vesting(0)
        print("[OK] Pending powerdown cancelled")
    except Exception:
        print("[INFO] No pending powerdown to cancel")

    # Step 4: Revoke all posting authorities (app permissions)
    try:
        posting_auths = [a[0] for a in acc2["posting"]["account_auths"]]
        for app in posting_auths:
            acc2.disallow(foreign=app, permission="posting")
            print(f"[OK] Revoked posting auth from @{app}")
    except Exception as e:
        print(f"[WARN] Could not revoke posting auths: {e}")

    # Step 5: Display new keys (SAVE IMMEDIATELY)
    print("\n" + "=" * 60)
    print("  NEW KEYS — SAVE THESE IMMEDIATELY")
    print("=" * 60)
    print(f"  Master Password: {new_password}")
    for role, kp in new_keys.items():
        print(f"  {role.upper():>8}: {kp['private']}")
    print("=" * 60)
    print("  WRITE THESE DOWN. They will NOT be shown again.")
    print("  Old keys are now INVALID.")
    print("=" * 60)

    return new_keys

def initiate_account_recovery(
    account_to_recover: str,
    recovery_account: str,
    recovery_active_key: str,
    new_owner_public: str,
):
    """
    If the owner key is compromised, the recovery account can
    initiate recovery. The user must prove they held the old
    owner key within the last 30 days.
    """
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[recovery_active_key]
    )
    # request_account_recovery operation
    from beem.transactionbuilder import TransactionBuilder
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps({
        "type": "request_account_recovery",
        "recovery_account": recovery_account,
        "account_to_recover": account_to_recover,
        "new_owner_authority": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[new_owner_public, 1]],
        },
        "extensions": [],
    })
    tx.appendSigner(recovery_account, "active")
    tx.sign()
    tx.broadcast()
    print(f"Recovery requested for @{account_to_recover}")
    print("The account owner must now complete recovery within 24 hours")

# emergency_key_change("myaccount", "5Jowner_key_here")
```

Act fast. Every second counts if keys are compromised.'''
    ),
    (
        "hive_security/secure-multi-account-management",
        r'''How do I securely manage multiple Hive accounts from a single application without cross-contaminating keys?''',
        r'''<think>
Managing multiple accounts requires strict key isolation — each account's keys
must be stored and accessed independently. Risks include: accidentally signing
with the wrong account's key, a breach of one account exposing all, and key
confusion in config. The pattern: use a per-account keystore with separate
encryption, load only the needed key into memory for the operation, and clear
it afterward. A vault abstraction with account-scoped access works well.
</think>

```python
import json
import os
from dataclasses import dataclass, field
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64
import getpass
from beem import Hive
from contextlib import contextmanager

@dataclass
class AccountVault:
    """Isolated key storage for multiple Hive accounts."""
    vault_dir: str

    def __post_init__(self):
        os.makedirs(self.vault_dir, mode=0o700, exist_ok=True)

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32,
            salt=salt, iterations=480_000,
        )
        return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))

    def _account_path(self, account: str) -> str:
        # Sanitize account name for filesystem
        safe = "".join(c for c in account if c.isalnum() or c in "-.")
        return os.path.join(self.vault_dir, f"{safe}.vault")

    def store_keys(self, account: str, keys: dict[str, str], passphrase: str):
        """Store keys for a single account with unique encryption."""
        salt = os.urandom(16)
        fernet = Fernet(self._derive_key(passphrase, salt))
        encrypted = fernet.encrypt(json.dumps(keys).encode())
        path = self._account_path(account)
        with open(path, "wb") as f:
            f.write(salt + encrypted)
        os.chmod(path, 0o600)

    def load_keys(self, account: str, passphrase: str) -> dict[str, str]:
        path = self._account_path(account)
        with open(path, "rb") as f:
            data = f.read()
        salt, encrypted = data[:16], data[16:]
        fernet = Fernet(self._derive_key(passphrase, salt))
        return json.loads(fernet.decrypt(encrypted))

    def list_accounts(self) -> list[str]:
        return [
            f.replace(".vault", "")
            for f in os.listdir(self.vault_dir)
            if f.endswith(".vault")
        ]

    @contextmanager
    def scoped_hive(self, account: str, role: str, passphrase: str):
        """Context manager: load ONE key, create Hive instance, clean up."""
        keys = self.load_keys(account, passphrase)
        wif = keys.get(role)
        if not wif:
            raise KeyError(f"No {role} key stored for @{account}")

        hive = Hive(node=["https://api.hive.blog"], keys=[wif])
        try:
            yield hive, account
        finally:
            # Clear key from memory (best effort)
            wif = None
            keys.clear()

# --- Usage ---
vault = AccountVault("/secure/hive_vault")

# One-time setup per account (different passphrases!)
vault.store_keys("main-account", {
    "posting": "5Jposting...",
    "active": "5Jactive...",
}, passphrase="passphrase-for-main")

vault.store_keys("bot-account", {
    "posting": "5Jposting...",
}, passphrase="passphrase-for-bot")

# Scoped access — only one key in memory at a time
with vault.scoped_hive("main-account", "active", "passphrase-for-main") as (hive, acc):
    from beem.account import Account
    a = Account(acc, blockchain_instance=hive)
    a.transfer("vendor", 5.0, "HIVE", memo="Invoice payment")
# Key is cleared when context exits

# Bot uses only posting — CANNOT accidentally use active
with vault.scoped_hive("bot-account", "posting", "passphrase-for-bot") as (hive, acc):
    from beem.comment import Comment
    c = Comment("@author/post", blockchain_instance=hive)
    c.upvote(50, voter=acc)

print("Managed accounts:", vault.list_accounts())
```

Each account has its own encrypted vault file and passphrase. Keys never cross-contaminate.'''
    ),
    (
        "hive_security/token-permission-scoping",
        r'''How do I scope token permissions in a Hive dApp so that different API tokens grant different levels of access?''',
        r'''<think>
Hive itself has key-based auth (posting/active/owner), but dApps often need
finer-grained permission scoping for API tokens — e.g., a token that can only
vote but not post, or one that can transfer up to X amount. This is an app-layer
concern. The pattern: issue JWT or opaque tokens with embedded permission scopes,
validate scopes before performing any chain operation, and use the minimum
required Hive key for each scope. This prevents a leaked API token from having
full posting or active access.
</think>

```python
import jwt
import time
import secrets
from enum import Flag, auto
from dataclasses import dataclass
from functools import wraps

class HiveScope(Flag):
    """Fine-grained permission scopes for Hive dApp API tokens."""
    VOTE = auto()
    COMMENT = auto()
    POST = auto()
    FOLLOW = auto()
    TRANSFER_SMALL = auto()   # transfers < 1 HIVE
    TRANSFER = auto()         # any transfer
    DELEGATE = auto()
    CUSTOM_JSON = auto()
    ADMIN = auto()

    # Common bundles
    SOCIAL = VOTE | COMMENT | POST | FOLLOW
    READ_ONLY = 0

# Map scopes to required Hive key level
SCOPE_KEY_LEVEL: dict[HiveScope, str] = {
    HiveScope.VOTE: "posting",
    HiveScope.COMMENT: "posting",
    HiveScope.POST: "posting",
    HiveScope.FOLLOW: "posting",
    HiveScope.CUSTOM_JSON: "posting",
    HiveScope.TRANSFER_SMALL: "active",
    HiveScope.TRANSFER: "active",
    HiveScope.DELEGATE: "active",
}

JWT_SECRET = secrets.token_hex(32)

@dataclass
class ScopedToken:
    account: str
    scopes: HiveScope
    token: str
    expires_at: float

def issue_token(
    account: str,
    scopes: HiveScope,
    ttl_hours: float = 24,
) -> ScopedToken:
    """Issue a scoped API token for a Hive account."""
    expires = time.time() + ttl_hours * 3600
    payload = {
        "sub": account,
        "scopes": scopes.value,
        "exp": expires,
        "jti": secrets.token_hex(8),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return ScopedToken(account, scopes, token, expires)

def validate_token(token: str) -> tuple[str, HiveScope]:
    """Validate and decode a scoped token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise PermissionError("Token expired")
    except jwt.InvalidTokenError:
        raise PermissionError("Invalid token")
    return payload["sub"], HiveScope(payload["scopes"])

def require_scope(required: HiveScope):
    """Decorator to enforce scope on API endpoints."""
    def decorator(func):
        @wraps(func)
        def wrapper(token: str, *args, **kwargs):
            account, scopes = validate_token(token)
            if not (required & scopes):
                raise PermissionError(
                    f"Token lacks required scope: {required.name}. "
                    f"Has: {scopes}"
                )
            return func(account, *args, **kwargs)
        return wrapper
    return decorator

# --- API endpoints with scope enforcement ---

@require_scope(HiveScope.VOTE)
def api_vote(account: str, author: str, permlink: str, weight: int):
    print(f"@{account} voting on @{author}/{permlink} weight={weight}")
    # Use posting key to execute

@require_scope(HiveScope.TRANSFER)
def api_transfer(account: str, to: str, amount: str):
    print(f"@{account} transferring {amount} to @{to}")
    # Use active key to execute

@require_scope(HiveScope.TRANSFER_SMALL)
def api_small_transfer(account: str, to: str, amount: float):
    if amount >= 1.0:
        raise PermissionError("TRANSFER_SMALL scope limited to < 1 HIVE")
    print(f"@{account} micro-transfer {amount:.3f} HIVE to @{to}")

# Issue tokens with different scopes
social_token = issue_token("alice", HiveScope.SOCIAL, ttl_hours=24)
transfer_token = issue_token("alice", HiveScope.TRANSFER, ttl_hours=1)

# Works: social token has VOTE scope
api_vote(social_token.token, "bob", "my-post", 10000)

# Fails: social token lacks TRANSFER scope
try:
    api_transfer(social_token.token, "bob", "10.000 HIVE")
except PermissionError as e:
    print(f"Blocked: {e}")
```'''
    ),
    (
        "hive_security/cross-app-authority-isolation",
        r'''How do I ensure that granting posting authority to one Hive app doesn't let other apps use it?''',
        r'''<think>
When you add an app to your posting account_auths, that app account can sign any
posting-level operation as you. There is no native per-app scoping on Hive — if
app A and app B both have posting authority, either can post/vote as you. The
isolation must happen at the app level. Patterns: use HiveSigner with specific
scope parameters, use Hive Keychain which prompts per-action, or create dedicated
sub-accounts per app with delegated HP. The sub-account pattern gives true
on-chain isolation.
</think>

```python
"""
Cross-app authority isolation patterns for Hive.
"""
from beem import Hive
from beem.account import Account

# --- Pattern 1: Sub-account per app (true isolation) ---

def create_app_sub_account(
    main_account: str,
    app_name: str,
    active_key: str,
    delegate_hp: float = 10.0,
):
    """
    Create a dedicated sub-account for each app.
    e.g., main.splinterlands, main.ecency
    The sub-account has its own keys, and only the needed HP is delegated.
    """
    sub_name = f"{main_account[:11]}.{app_name[:4]}"  # Hive: max 16 chars
    hive = Hive(node=["https://api.hive.blog"], keys=[active_key])
    main = Account(main_account, blockchain_instance=hive)

    # Create the sub-account (you control its keys)
    from beemgraphenebase.account import PasswordKey
    import secrets, string
    password = "P5" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(40))

    keys = {}
    for role in ("owner", "active", "posting", "memo"):
        pk = PasswordKey(sub_name, password, role=role)
        keys[role] = str(pk.get_public_key())

    main.create_account(
        sub_name,
        owner_key=keys["owner"],
        active_key=keys["active"],
        posting_key=keys["posting"],
        memo_key=keys["memo"],
    )

    # Delegate minimum HP for RC
    main.delegate_vesting_shares(sub_name, delegate_hp)

    # Grant posting authority to the specific app only on the sub-account
    sub = Account(sub_name, blockchain_instance=hive)
    sub.allow(foreign=app_name, weight=1, permission="posting")

    return {
        "sub_account": sub_name,
        "password": password,
        "delegated_hp": delegate_hp,
        "app_authorized": app_name,
        # Main account is NOT exposed to the app at all
    }

# --- Pattern 2: Audit and enforce isolation ---

class AuthorityAuditor:
    def __init__(self):
        self.hive = Hive(node=["https://api.hive.blog"])

    def list_app_authorities(self, account: str) -> dict:
        acc = Account(account, blockchain_instance=self.hive)
        return {
            "posting_apps": [a[0] for a in acc["posting"]["account_auths"]],
            "active_apps": [a[0] for a in acc["active"]["account_auths"]],
        }

    def check_isolation(self, account: str, expected_apps: dict[str, str]) -> list[str]:
        """
        expected_apps: {"ecency.app": "posting", "hive.engine": "active"}
        Returns list of violations.
        """
        violations = []
        auths = self.list_app_authorities(account)

        for app in auths["posting_apps"]:
            if app not in expected_apps:
                violations.append(f"Unexpected posting auth: @{app}")
            elif expected_apps[app] != "posting":
                violations.append(f"@{app} has posting but expected {expected_apps[app]}")

        for app in auths["active_apps"]:
            if app not in expected_apps:
                violations.append(f"CRITICAL: Unexpected active auth: @{app}")
            elif expected_apps[app] != "active":
                violations.append(f"@{app} has active but expected {expected_apps[app]}")

        return violations

# Usage
auditor = AuthorityAuditor()
violations = auditor.check_isolation("myaccount", {
    "ecency.app": "posting",
})
for v in violations:
    print(f"  [!] {v}")

# Best practice: use sub-accounts for true isolation
# result = create_app_sub_account("myaccount", "splinterlands", "5Jactive...")
```

True isolation requires separate accounts. On-chain posting authority cannot be scoped per-app.'''
    ),
    (
        "hive_security/secure-webhook-verification",
        r'''How do I verify that incoming webhook events about Hive blockchain activity are authentic and not spoofed?''',
        r'''<think>
Webhook verification for Hive events is important when building services that
react to chain events via a push model (e.g., a notification service sends you
a webhook when a transfer arrives). The sender should sign the payload with a
shared secret (HMAC) or use asymmetric signatures. The receiver verifies the
signature before processing. Additionally, you should verify against the chain
itself — never trust a webhook alone for financial operations. Replay protection
via timestamp and nonce is also essential.
</think>

```python
import hmac
import hashlib
import time
import json
from dataclasses import dataclass
from flask import Flask, request, abort

WEBHOOK_SECRET = "your-shared-secret-change-this"  # shared with sender

@dataclass
class WebhookEvent:
    event_type: str   # "transfer", "vote", "custom_json"
    account: str
    payload: dict
    block_num: int
    timestamp: float
    nonce: str

# --- Sender side (webhook producer) ---

def sign_webhook_payload(payload: dict, secret: str) -> str:
    """Create HMAC-SHA256 signature for webhook payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        secret.encode(), canonical.encode(), hashlib.sha256
    ).hexdigest()

def send_webhook(url: str, event: WebhookEvent, secret: str):
    """Send a signed webhook event."""
    import requests as req

    payload = {
        "event_type": event.event_type,
        "account": event.account,
        "payload": event.payload,
        "block_num": event.block_num,
        "timestamp": event.timestamp,
        "nonce": event.nonce,
    }
    signature = sign_webhook_payload(payload, secret)

    req.post(url, json=payload, headers={
        "X-Hive-Signature": signature,
        "X-Hive-Timestamp": str(int(event.timestamp)),
    }, timeout=10)

# --- Receiver side (webhook consumer) ---

app = Flask(__name__)
_seen_nonces: set[str] = set()

def verify_webhook(payload: dict, signature: str, timestamp: str) -> bool:
    """Verify webhook authenticity."""
    # Check timestamp (reject if older than 5 minutes)
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    if abs(time.time() - ts) > 300:
        return False  # too old or too far in future

    # Check nonce for replay protection
    nonce = payload.get("nonce", "")
    if nonce in _seen_nonces:
        return False  # replay
    _seen_nonces.add(nonce)

    # Verify HMAC signature
    expected = sign_webhook_payload(payload, WEBHOOK_SECRET)
    return hmac.compare_digest(signature, expected)

def verify_on_chain(event_payload: dict) -> bool:
    """Double-check the event against the actual blockchain."""
    from beem import Hive
    from beem.blockchain import Blockchain

    hive = Hive(node=["https://api.hive.blog"])
    block_num = event_payload.get("block_num", 0)
    if not block_num:
        return False

    chain = Blockchain(blockchain_instance=hive)
    block = chain.get_block(block_num)

    # Verify the operation exists in the block
    for tx in block.get("transactions", []):
        for op in tx.get("operations", []):
            if op[0] == event_payload.get("event_type"):
                if op[1].get("from") == event_payload.get("account"):
                    return True
    return False

@app.route("/webhook/hive", methods=["POST"])
def receive_webhook():
    signature = request.headers.get("X-Hive-Signature", "")
    timestamp = request.headers.get("X-Hive-Timestamp", "")
    payload = request.get_json()

    if not verify_webhook(payload, signature, timestamp):
        abort(401, "Invalid webhook signature")

    # For financial events, ALWAYS verify on-chain
    if payload.get("event_type") == "transfer":
        if not verify_on_chain(payload):
            abort(422, "Event not found on chain")

    # Process the verified event
    print(f"Verified event: {payload['event_type']} for @{payload['account']}")
    return {"status": "ok"}, 200
```

Golden rule: never trust webhooks alone for financial operations — always verify on-chain.'''
    ),
    (
        "hive_security/dapp-launch-checklist",
        r'''Give me a comprehensive security checklist for launching a Hive dApp, covering key management, API security, and common pitfalls.''',
        r'''<think>
A Hive dApp launch checklist covers: key management (never store user keys server-
side), API security (rate limiting, input validation), authority handling (minimum
privilege), frontend security (XSS prevention for markdown rendering), transaction
validation, monitoring/alerting, incident response, and common Hive-specific
pitfalls. This is expert-level — combining blockchain-specific and general web
security. The checklist should be actionable with code examples for the most
critical items.
</think>

```python
"""
Hive dApp Security Launch Checklist — with verification code.
Run this before going live.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

@dataclass
class CheckItem:
    category: str
    description: str
    severity: Severity
    check_fn: Optional[Callable] = None
    passed: bool = False
    notes: str = ""

class HiveDAppSecurityAudit:
    def __init__(self, app_config: dict):
        self.config = app_config
        self.checks: list[CheckItem] = self._build_checklist()

    def _build_checklist(self) -> list[CheckItem]:
        return [
            # --- KEY MANAGEMENT ---
            CheckItem(
                "Key Management",
                "No private keys in source code or env vars",
                Severity.CRITICAL,
                check_fn=self._check_no_keys_in_source,
            ),
            CheckItem(
                "Key Management",
                "User keys signed client-side only (Keychain/HiveSigner)",
                Severity.CRITICAL,
            ),
            CheckItem(
                "Key Management",
                "App only requests minimum key level needed",
                Severity.HIGH,
            ),
            CheckItem(
                "Key Management",
                "Owner key never used in application",
                Severity.CRITICAL,
            ),
            # --- API SECURITY ---
            CheckItem(
                "API Security",
                "Rate limiting on all endpoints",
                Severity.HIGH,
                check_fn=self._check_rate_limiting,
            ),
            CheckItem(
                "API Security",
                "Input validation on account names and amounts",
                Severity.HIGH,
                check_fn=self._check_input_validation,
            ),
            CheckItem(
                "API Security",
                "HTTPS enforced (no HTTP)",
                Severity.CRITICAL,
            ),
            CheckItem(
                "API Security",
                "CORS configured (not wildcard in production)",
                Severity.HIGH,
            ),
            CheckItem(
                "API Security",
                "Node endpoints not exposed to public",
                Severity.MEDIUM,
            ),
            # --- TRANSACTION SAFETY ---
            CheckItem(
                "Transactions",
                "Transfer amounts validated before broadcast",
                Severity.CRITICAL,
            ),
            CheckItem(
                "Transactions",
                "Memo content checked for accidental key leaks",
                Severity.HIGH,
            ),
            CheckItem(
                "Transactions",
                "Transaction expiration set (not indefinite)",
                Severity.MEDIUM,
            ),
            CheckItem(
                "Transactions",
                "Recipient account verified to exist before transfer",
                Severity.HIGH,
            ),
            # --- FRONTEND ---
            CheckItem(
                "Frontend",
                "Markdown rendered with XSS sanitization",
                Severity.HIGH,
            ),
            CheckItem(
                "Frontend",
                "External links have rel='noopener noreferrer'",
                Severity.MEDIUM,
            ),
            CheckItem(
                "Frontend",
                "Phishing URL detection on user-generated links",
                Severity.MEDIUM,
            ),
            # --- MONITORING ---
            CheckItem(
                "Monitoring",
                "Authority change alerts configured",
                Severity.HIGH,
            ),
            CheckItem(
                "Monitoring",
                "Failed transaction logging enabled",
                Severity.MEDIUM,
            ),
            CheckItem(
                "Monitoring",
                "Anomalous transfer detection active",
                Severity.HIGH,
            ),
            # --- INCIDENT RESPONSE ---
            CheckItem(
                "Incident Response",
                "Emergency key rotation procedure documented",
                Severity.HIGH,
            ),
            CheckItem(
                "Incident Response",
                "Account recovery partner configured",
                Severity.HIGH,
            ),
            CheckItem(
                "Incident Response",
                "Kill switch to disable broadcasts",
                Severity.HIGH,
            ),
        ]

    def _check_no_keys_in_source(self) -> tuple[bool, str]:
        import re
        # Check config for patterns that look like WIF keys
        config_str = str(self.config)
        wif_pattern = re.compile(r'5[HJK][1-9A-HJ-NP-Za-km-z]{49,50}')
        matches = wif_pattern.findall(config_str)
        if matches:
            return False, f"Found {len(matches)} possible WIF key(s) in config!"
        return True, "No WIF keys found in config"

    def _check_rate_limiting(self) -> tuple[bool, str]:
        has_rl = self.config.get("rate_limiting_enabled", False)
        return has_rl, "Rate limiting " + ("enabled" if has_rl else "NOT configured")

    def _check_input_validation(self) -> tuple[bool, str]:
        import re
        # Valid Hive account: 3-16 chars, lowercase, alphanumeric + dots/hyphens
        valid = re.compile(r'^[a-z][a-z0-9\-.]{2,15}$')
        test_cases = ["valid.user", "x", "UPPER", "a" * 20, "good-name"]
        results = [(t, bool(valid.match(t))) for t in test_cases]
        expected = [True, False, False, False, True]
        actual = [r[1] for r in results]
        ok = actual == expected
        return ok, "Account name validation " + ("correct" if ok else "has gaps")

    def run_audit(self) -> dict:
        total = len(self.checks)
        passed = 0
        critical_fails = []

        print("=" * 60)
        print("  HIVE dAPP SECURITY AUDIT")
        print("=" * 60)

        current_category = ""
        for check in self.checks:
            if check.category != current_category:
                current_category = check.category
                print(f"\n[{current_category}]")

            if check.check_fn:
                check.passed, check.notes = check.check_fn()
            status = "PASS" if check.passed else "FAIL"
            icon = "+" if check.passed else "!"
            print(f"  [{icon}] [{check.severity.value:>8}] {check.description}")
            if check.notes:
                print(f"      -> {check.notes}")

            if check.passed:
                passed += 1
            elif check.severity == Severity.CRITICAL:
                critical_fails.append(check.description)

        print(f"\n{'=' * 60}")
        print(f"  Result: {passed}/{total} passed")
        if critical_fails:
            print(f"  BLOCKED: {len(critical_fails)} critical failures:")
            for f in critical_fails:
                print(f"    - {f}")
            print("  DO NOT LAUNCH until critical issues are resolved.")
        else:
            print("  No critical failures. Review HIGH/MEDIUM items.")
        print("=" * 60)

        return {"passed": passed, "total": total, "critical_fails": critical_fails}

# Run the audit
audit = HiveDAppSecurityAudit({
    "rate_limiting_enabled": True,
    "api_keys": ["not-a-wif-key"],
})
audit.run_audit()
```

Run this audit before every release. No critical failures = cleared for launch.'''
    ),
]
