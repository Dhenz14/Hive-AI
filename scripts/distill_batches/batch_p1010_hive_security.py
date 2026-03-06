"""Hive blockchain training pairs: security best practices."""

PAIRS = [
    (
        "hive/key-storage-best-practices",
        r'''What are the best practices for storing Hive private keys in different environments (web, mobile, server)?''',
        r'''<think>
Key storage is the most critical security concern for Hive applications. The key hierarchy (owner > active > posting > memo) means different keys need different protection levels. Owner keys should be cold-stored, active keys need hardware security on servers, posting keys can be more accessible but still need protection.

Key principles:
1. Never store keys in source code or environment variables in plaintext
2. Use the minimum required key type for each operation
3. Owner key should never be on a connected device
4. Consider using posting authority delegation instead of sharing keys
</think>

Secure key storage depends on your deployment environment. Here are best practices for each:

```python
# === Server-side key management ===

# Option 1: Encrypted keystore file
import json
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

class SecureKeyStore:
    """Encrypted keystore for Hive private keys."""

    def __init__(self, keystore_path, master_password):
        self.path = keystore_path
        self.cipher = self._derive_cipher(master_password)

    def _derive_cipher(self, password):
        # Use PBKDF2 to derive encryption key from password
        salt_path = self.path + ".salt"
        if os.path.exists(salt_path):
            with open(salt_path, "rb") as f:
                salt = f.read()
        else:
            salt = os.urandom(16)
            with open(salt_path, "wb") as f:
                f.write(salt)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return Fernet(key)

    def store_key(self, account, role, private_key):
        """Store an encrypted private key."""
        keys = self._load_all()
        keys.setdefault(account, {})[role] = self.cipher.encrypt(
            private_key.encode()
        ).decode()
        with open(self.path, "w") as f:
            json.dump(keys, f)

    def get_key(self, account, role):
        """Retrieve a decrypted private key."""
        keys = self._load_all()
        encrypted = keys.get(account, {}).get(role)
        if encrypted:
            return self.cipher.decrypt(encrypted.encode()).decode()
        return None

    def _load_all(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                return json.load(f)
        return {}

# Option 2: Environment-based with validation
class EnvKeyProvider:
    """Load keys from environment with validation."""

    @staticmethod
    def get_posting_key(account):
        key_var = f"HIVE_POSTING_KEY_{account.upper()}"
        key = os.environ.get(key_var)
        if not key:
            raise ValueError(f"Missing env var: {key_var}")
        if not key.startswith("5") or len(key) != 51:
            raise ValueError(f"Invalid WIF format for {key_var}")
        return key

    @staticmethod
    def get_active_key(account):
        key_var = f"HIVE_ACTIVE_KEY_{account.upper()}"
        key = os.environ.get(key_var)
        if not key:
            raise ValueError(f"Missing env var: {key_var}")
        return key

# Option 3: HashiCorp Vault integration
class VaultKeyProvider:
    """Load keys from HashiCorp Vault."""

    def __init__(self, vault_addr, vault_token):
        self.addr = vault_addr
        self.token = vault_token

    def get_key(self, account, role):
        import requests
        resp = requests.get(
            f"{self.addr}/v1/secret/data/hive/{account}",
            headers={"X-Vault-Token": self.token},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()["data"]["data"]
        return data.get(f"{role}_key")

# Security checklist for Hive key management
SECURITY_CHECKLIST = """
Key Storage Security Checklist:
1. Owner key: OFFLINE ONLY (paper wallet or hardware wallet)
2. Active key: Encrypted at rest, only on servers that need it
3. Posting key: Can be in app config, still encrypted
4. Memo key: Stored alongside posting key
5. Never commit keys to git (use .gitignore)
6. Never log private keys (scrub from error messages)
7. Use posting authority delegation instead of sharing keys
8. Rotate keys periodically
9. Monitor account authority changes
10. Set up account recovery before you need it
"""
print(SECURITY_CHECKLIST)

# Usage
# keystore = SecureKeyStore("/secure/hive_keys.enc", "master_password")
# keystore.store_key("mybot", "posting", "5JPrivateKeyHere")
# key = keystore.get_key("mybot", "posting")
```

The golden rule: use the minimum required key type. If your bot only votes and posts, it only needs the posting key. Never store the active key unless absolutely necessary (for transfers). The owner key should never touch a server.
'''
    ),
    (
        "hive/transaction-signing-security",
        r'''How do I ensure transaction signing is secure in my Hive dApp? What attack vectors should I protect against?''',
        r'''Transaction signing security involves protecting against replay attacks, man-in-the-middle attacks, and unauthorized signing. Here are the key protections:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer
import time
import json
import hashlib

class SecureTransactionSigner:
    """Secure transaction signing with protection against common attacks."""

    def __init__(self, hive_instance):
        self.hive = hive_instance

    def sign_transfer(self, from_acct, to_acct, amount, asset, memo=""):
        """Sign a transfer with security checks."""

        # Security check 1: Validate amount
        amount_float = float(amount)
        if amount_float <= 0:
            raise ValueError("Amount must be positive")
        if amount_float > 1000000:
            raise ValueError("Amount exceeds safety limit")

        # Security check 2: Validate account names
        if not self._is_valid_account(to_acct):
            raise ValueError(f"Invalid account name: {to_acct}")

        # Security check 3: Format amount properly
        formatted = f"{amount_float:.3f} {asset}"

        op = Transfer(**{
            "from": from_acct,
            "to": to_acct,
            "amount": formatted,
            "memo": memo
        })

        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(from_acct, "active")

        # Security check 4: Verify transaction before signing
        # The transaction includes the ref_block which prevents replay
        # on other chains or after expiration
        tx.sign()

        # Security check 5: Log the transaction for audit
        self._audit_log(from_acct, to_acct, formatted, tx)

        return tx.broadcast()

    def _is_valid_account(self, name):
        """Validate account name format."""
        import re
        if not name or len(name) < 3 or len(name) > 16:
            return False
        return bool(re.match(r'^[a-z][a-z0-9\-\.]*[a-z0-9]$', name))

    def _audit_log(self, from_acct, to_acct, amount, tx):
        """Log transaction for security auditing."""
        import logging
        logger = logging.getLogger("tx_audit")
        # Never log private keys!
        logger.info(json.dumps({
            "action": "transfer",
            "from": from_acct,
            "to": to_acct,
            "amount": amount,
            "timestamp": int(time.time()),
            "tx_digest": hashlib.sha256(
                str(tx).encode()
            ).hexdigest()[:16]
        }))


# Protection against common attack vectors
class TransactionGuard:
    """Guards against common transaction attacks."""

    def __init__(self):
        self.daily_limits = {}  # {account: {asset: amount}}
        self.rate_limits = {}   # {account: [timestamps]}
        self.whitelist = set()

    def set_daily_limit(self, account, asset, max_amount):
        self.daily_limits.setdefault(account, {})[asset] = max_amount

    def set_whitelist(self, accounts):
        self.whitelist = set(accounts)

    def check_transfer(self, from_acct, to_acct, amount, asset):
        """Check if a transfer passes all security guards."""
        errors = []

        # Guard 1: Whitelist check
        if self.whitelist and to_acct not in self.whitelist:
            errors.append(f"@{to_acct} not in whitelist")

        # Guard 2: Daily limit check
        limit = self.daily_limits.get(from_acct, {}).get(asset)
        if limit and amount > limit:
            errors.append(f"Exceeds daily limit of {limit} {asset}")

        # Guard 3: Rate limiting (max 10 transfers per minute)
        now = time.time()
        recent = self.rate_limits.get(from_acct, [])
        recent = [t for t in recent if now - t < 60]
        if len(recent) >= 10:
            errors.append("Rate limit exceeded (10/min)")
        recent.append(now)
        self.rate_limits[from_acct] = recent

        # Guard 4: Check for suspicious patterns
        if to_acct == from_acct:
            errors.append("Self-transfer detected")

        if errors:
            raise SecurityError(
                f"Transfer blocked: {'; '.join(errors)}"
            )
        return True

class SecurityError(Exception):
    pass


# Built-in Hive transaction security features
HIVE_SECURITY_FEATURES = """
Hive's built-in transaction security:

1. Reference block: Each transaction references a recent block,
   preventing replay after ~65535 blocks (~54 hours)

2. Expiration time: Transactions expire (default 60 seconds),
   preventing delayed replay

3. Chain ID: Transactions are signed for a specific chain,
   preventing cross-chain replay

4. Hierarchical keys: Operations are validated against the
   correct authority level (posting/active/owner)

5. Transaction tapos: The ref_block_num and ref_block_prefix
   fields bind transactions to a specific chain state

6. No nonce/sequence: Unlike Ethereum, Hive transactions
   do not use nonces, so ordering is by block inclusion
"""
print(HIVE_SECURITY_FEATURES)

# Usage
# guard = TransactionGuard()
# guard.set_daily_limit("mybot", "HIVE", 1000)
# guard.set_whitelist(["trusted1", "trusted2"])
# guard.check_transfer("mybot", "trusted1", 100, "HIVE")
```

Key security principles: validate all inputs before signing, enforce rate and daily limits, maintain audit logs (without private keys), use whitelists for automated transfers, and leverage Hive's built-in protections (reference blocks, expiration, chain ID binding).
'''
    ),
    (
        "hive/phishing-prevention",
        r'''How do I protect users from phishing attacks targeting Hive accounts? What should my dApp implement?''',
        r'''Phishing is the biggest security threat to Hive accounts. Here are protection measures your dApp should implement:

```python
import re
import json
from urllib.parse import urlparse

class PhishingProtection:
    """Anti-phishing measures for Hive dApps."""

    def __init__(self):
        # Known legitimate Hive domains
        self.trusted_domains = {
            "hive.blog", "peakd.com", "ecency.com",
            "hivesigner.com", "hive-keychain.com",
            "3speak.tv", "splinterlands.com",
            "tribaldex.com", "beeswap.dcity.io"
        }
        self.phishing_patterns = [
            r"h[i1]ve[\-_]?b[l1]og",    # hive-blog typosquatting
            r"peak[dt][\.\-]",            # peakd typosquatting
            r"key.?chain.?update",        # fake keychain update
            r"claim.?your.?reward",       # fake reward claim
            r"verify.?your.?account",     # verification phishing
            r"free.?hive.?power",         # free HP scam
        ]
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.phishing_patterns
        ]

    def check_url(self, url):
        """Check if a URL is potentially a phishing link."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www prefix
            if domain.startswith("www."):
                domain = domain[4:]

            # Check against trusted domains
            if domain in self.trusted_domains:
                return {"safe": True, "domain": domain}

            # Check for typosquatting
            for trusted in self.trusted_domains:
                if self._levenshtein(domain, trusted) <= 2 and domain != trusted:
                    return {
                        "safe": False,
                        "reason": f"Typosquatting of {trusted}",
                        "domain": domain
                    }

            # Check for suspicious patterns in URL
            full_url = url.lower()
            for pattern in self.compiled_patterns:
                if pattern.search(full_url):
                    return {
                        "safe": False,
                        "reason": f"Phishing pattern detected",
                        "domain": domain
                    }

            return {"safe": None, "domain": domain, "reason": "Unknown domain"}

        except Exception:
            return {"safe": False, "reason": "Invalid URL"}

    def check_memo(self, memo):
        """Check if a transfer memo contains phishing content."""
        if not memo:
            return {"safe": True}

        memo_lower = memo.lower()

        # Check for phishing URLs in memos
        urls = re.findall(r'https?://\S+', memo)
        for url in urls:
            result = self.check_url(url)
            if result.get("safe") is False:
                return {
                    "safe": False,
                    "reason": f"Phishing URL in memo: {result['reason']}",
                    "url": url
                }

        # Check for social engineering phrases
        danger_phrases = [
            "update your keys", "verify your account",
            "claim your reward", "you have won",
            "enter your password", "login to receive",
            "active key required", "owner key needed",
            "send hive to receive", "double your hive"
        ]
        for phrase in danger_phrases:
            if phrase in memo_lower:
                return {
                    "safe": False,
                    "reason": f"Social engineering: '{phrase}'"
                }

        return {"safe": True}

    def check_authority_request(self, requesting_account, permission_level):
        """Warn about suspicious authority requests."""
        warnings = []

        # Active/owner authority requests are dangerous
        if permission_level in ("active", "owner"):
            warnings.append(
                f"WARNING: @{requesting_account} is requesting "
                f"{permission_level} authority. This grants access to "
                f"your funds. Only approve if you fully trust this account."
            )

        # Check account age and reputation
        # (In production, query the blockchain)

        return warnings

    def _levenshtein(self, s1, s2):
        """Simple Levenshtein distance for typo detection."""
        if len(s1) < len(s2):
            return self._levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (c1 != c2)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row
        return prev_row[-1]

# Usage
guard = PhishingProtection()

# Check URLs
print(guard.check_url("https://peakd.com/@author/post"))
print(guard.check_url("https://peakd-login.com/verify"))
print(guard.check_url("https://h1ve-blog.com/claim"))

# Check memos
print(guard.check_memo("Thanks for the trade!"))
print(guard.check_memo("Claim your reward at https://fake-hive.com/claim"))
print(guard.check_memo("Please update your keys at this link"))
```

Implement these protections in your dApp: URL validation in all user-facing content, memo scanning for phishing links in transfers, warnings on authority requests, and education about key safety. The most common attack vectors are phishing memos in transfers and fake front-end websites that steal keys.
'''
    ),
    (
        "hive/authority-checking",
        r'''How do I properly check account authorities before performing operations on behalf of users in my Hive dApp?''',
        r'''Proper authority checking prevents unauthorized operations and ensures your dApp operates safely. Here is a comprehensive authority verification system:

```python
from beem import Hive
from beem.account import Account
import json

hive = Hive(node=["https://api.hive.blog"])

class AuthorityChecker:
    """Verify account authorities before operations."""

    def __init__(self, dapp_account, hive_instance):
        self.dapp = dapp_account
        self.hive = hive_instance

    def has_posting_authority(self, user_account):
        """Check if our dApp has posting authority over a user."""
        try:
            acct = Account(user_account, hive_instance=self.hive)
            posting = acct["posting"]
            authorized = [a[0] for a in posting.get("account_auths", [])]
            return self.dapp in authorized
        except Exception:
            return False

    def has_active_authority(self, user_account):
        """Check if our dApp has active authority (dangerous, rarely needed)."""
        try:
            acct = Account(user_account, hive_instance=self.hive)
            active = acct["active"]
            authorized = [a[0] for a in active.get("account_auths", [])]
            return self.dapp in authorized
        except Exception:
            return False

    def get_authority_details(self, user_account):
        """Get detailed authority information."""
        try:
            acct = Account(user_account, hive_instance=self.hive)
        except Exception:
            return None

        result = {
            "account": user_account,
            "posting": {
                "threshold": acct["posting"]["weight_threshold"],
                "key_auths": acct["posting"]["key_auths"],
                "account_auths": acct["posting"]["account_auths"],
                "our_access": self.has_posting_authority(user_account)
            },
            "active": {
                "threshold": acct["active"]["weight_threshold"],
                "key_auths": acct["active"]["key_auths"],
                "account_auths": acct["active"]["account_auths"],
                "our_access": self.has_active_authority(user_account)
            },
            "owner": {
                "threshold": acct["owner"]["weight_threshold"],
                "key_auths": acct["owner"]["key_auths"],
                "account_auths": acct["owner"]["account_auths"]
            },
            "recovery_account": acct.get("recovery_account", ""),
        }
        return result

    def verify_operation_authority(self, user_account, operation_type):
        """Verify we can perform a specific operation type."""
        posting_ops = {
            "vote", "comment", "custom_json_posting",
            "follow", "reblog", "claim_reward_balance"
        }
        active_ops = {
            "transfer", "delegate_vesting_shares",
            "transfer_to_savings", "transfer_from_savings",
            "limit_order_create", "convert", "power_up",
            "custom_json_active"
        }

        if operation_type in posting_ops:
            has_auth = self.has_posting_authority(user_account)
            key_type = "posting"
        elif operation_type in active_ops:
            has_auth = self.has_active_authority(user_account)
            key_type = "active"
        else:
            return {
                "authorized": False,
                "reason": f"Unknown operation type: {operation_type}"
            }

        return {
            "authorized": has_auth,
            "key_type": key_type,
            "reason": "" if has_auth else (
                f"@{user_account} has not granted {key_type} "
                f"authority to @{self.dapp}"
            )
        }

    def audit_all_authorized_users(self, known_users):
        """Audit which users have granted us authority."""
        report = {"posting": [], "active": [], "none": []}

        for user in known_users:
            if self.has_active_authority(user):
                report["active"].append(user)
            elif self.has_posting_authority(user):
                report["posting"].append(user)
            else:
                report["none"].append(user)

        print(f"Authority audit for @{self.dapp}:")
        print(f"  Posting authority: {len(report['posting'])} users")
        print(f"  Active authority:  {len(report['active'])} users")
        print(f"  No authority:      {len(report['none'])} users")

        if report["active"]:
            print("\n  WARNING: Users with active authority granted:")
            for u in report["active"]:
                print(f"    @{u}")

        return report

# Usage
checker = AuthorityChecker("myapp", hive)

# Verify before every operation
auth = checker.verify_operation_authority("someuser", "vote")
if auth["authorized"]:
    print("Can proceed with vote")
else:
    print(f"Cannot vote: {auth['reason']}")

# Get detailed authority info
details = checker.get_authority_details("someuser")
if details:
    print(json.dumps(details, indent=2, default=str))
```

Always verify authority before every operation, not just once at login. Authority can be revoked at any time by the user. Cache authority status for performance but set a short TTL (e.g., 5 minutes). Log all authority checks for security auditing.
'''
    ),
    (
        "hive/memo-encryption-security",
        r'''How does memo encryption work securely on Hive, and what are the security considerations?''',
        r'''Memo encryption on Hive uses ECIES (Elliptic Curve Integrated Encryption Scheme) based on the secp256k1 curve. Here are the security details and considerations:

```python
from beem import Hive
from beem.account import Account
from beem.memo import Memo
import json

hive = Hive(node=["https://api.hive.blog"])

class SecureMemoHandler:
    """Handle encrypted memos with security best practices."""

    def __init__(self, account, memo_private_key, hive_instance):
        self.account = account
        self.hive = Hive(
            node=hive_instance.rpc.nodes,
            keys=[memo_private_key]
        )
        self.memo = Memo(hive_instance=self.hive)

    def encrypt_memo(self, recipient, message):
        """Encrypt a memo for a specific recipient.

        How it works:
        1. Fetch recipient's memo public key from the chain
        2. Generate ephemeral key pair
        3. Compute shared secret via ECDH
        4. AES encrypt the message with the shared secret
        5. Prepend with '#' to signal encryption
        """
        # Validate recipient exists
        try:
            acct = Account(recipient, hive_instance=self.hive)
            memo_pub = acct["memo_key"]
        except Exception:
            raise ValueError(f"Cannot find memo key for @{recipient}")

        # Check for null memo key
        null_key = "STM1111111111111111111111111111111114T1Anm"
        if memo_pub == null_key:
            raise ValueError(
                f"@{recipient} has a null memo key. "
                "Cannot encrypt memos to this account."
            )

        # Encrypt (beem handles the ECIES automatically)
        encrypted = self.memo.encrypt(message)
        return f"#{encrypted}" if not encrypted.startswith("#") else encrypted

    def decrypt_memo(self, encrypted_memo):
        """Decrypt a received memo."""
        if not encrypted_memo.startswith("#"):
            # Not encrypted, return as-is
            return encrypted_memo

        try:
            decrypted = self.memo.decrypt(encrypted_memo)
            return decrypted
        except Exception as e:
            return f"[Decryption failed: {e}]"

    def is_encrypted(self, memo):
        """Check if a memo is encrypted."""
        return memo.startswith("#") if memo else False

# Security considerations for memo encryption
SECURITY_NOTES = """
Memo Encryption Security Considerations:

1. FORWARD SECRECY: Hive memo encryption does NOT provide
   forward secrecy. If your memo key is compromised, ALL
   past encrypted memos can be decrypted.

2. METADATA LEAKAGE: While memo content is encrypted, the
   sender, recipient, amount, and timing are all public.
   This metadata can reveal patterns.

3. KEY ROTATION: If you change your memo key, you lose the
   ability to decrypt old memos sent to your previous key.
   Back up old keys if you need access to old memos.

4. MEMO KEY IS NOT FOR SIGNING: The memo key cannot sign
   transactions. It is exclusively for encryption/decryption.
   Do not confuse it with the posting key.

5. SHARED SECRET: Both sender and recipient can decrypt the
   memo (symmetric ECDH). You cannot send a memo that only
   the recipient can read if the sender's key is compromised.

6. NO GROUP ENCRYPTION: Memos are encrypted for exactly one
   recipient. There is no way to encrypt for multiple parties.

7. ON-CHAIN STORAGE: Encrypted memos are stored on-chain
   permanently. Even after "deleting" a transfer, the
   encrypted memo persists in the block log.

8. PLAINTEXT ATTACKS: Do not encrypt predictable content
   (like "thank you") as patterns could be used to verify
   key guesses in a brute-force attack.
"""
print(SECURITY_NOTES)

def scan_encrypted_memos(account_name, memo_key, limit=100):
    """Scan account history and decrypt all encrypted memos."""
    hive_with_key = Hive(
        node=["https://api.hive.blog"],
        keys=[memo_key]
    )
    acct = Account(account_name, hive_instance=hive_with_key)
    memo_handler = Memo(hive_instance=hive_with_key)

    history = acct.get_account_history(
        index=-1, limit=limit, only_ops=["transfer"]
    )

    encrypted_count = 0
    decrypted_count = 0

    for entry in history:
        op = entry["op"]
        op_data = op[1] if isinstance(op, list) else op
        raw_memo = op_data.get("memo", "")

        if raw_memo.startswith("#"):
            encrypted_count += 1
            try:
                decrypted = memo_handler.decrypt(raw_memo)
                decrypted_count += 1
                from_acct = op_data.get("from", "?")
                to_acct = op_data.get("to", "?")
                amount = op_data.get("amount", "?")
                print(f"@{from_acct} -> @{to_acct} ({amount})")
                print(f"  Decrypted: {decrypted[:100]}")
            except Exception as e:
                print(f"  Failed to decrypt: {e}")

    print(f"\nFound {encrypted_count} encrypted memos, "
          f"decrypted {decrypted_count}")

# scan_encrypted_memos("myaccount", "5MemoPrivateKey", limit=50)
```

The most important security advice: treat your memo key like any other private key. If compromised, an attacker can read all your past and future encrypted memos. Consider using external encryption (like PGP) for highly sensitive communications rather than relying solely on Hive memo encryption.
'''
    ),
]
