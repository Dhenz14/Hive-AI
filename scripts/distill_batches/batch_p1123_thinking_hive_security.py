"""
Hive blockchain thinking pairs - security decisions
"""

pairs = [
    {
        "instruction": r'''I am building a Hive wallet app. When should I use the posting key vs active key vs owner key? I want to minimize the risk if keys are compromised.''',
        "output": r'''<think>
Key hierarchy on Hive is critical for security. Let me think through each key type and what it controls.

Owner key: the "master" key. Can change all other keys, recover the account, and do everything the active key can do. This should almost never be used by applications. If compromised, the attacker owns the account permanently (unless account recovery is set up).

Active key: financial operations -- transfers, power ups/downs, conversions, witness voting, and also custom_json with required_auths. If compromised, the attacker can drain funds but the owner key can recover the account and change the active key.

Posting key: social operations -- voting, posting, commenting, custom_json with required_posting_auths, and following. If compromised, the attacker can spam votes and posts but cannot steal funds.

Memo key: only for encrypting/decrypting memo messages on transfers. Cannot sign any transactions. If compromised, the attacker can read private memos but cannot do anything else.

Hmm, for a wallet app specifically, the user needs to sign transfers and power operations, which require the active key. But I should never store the owner key. Wait, actually, should I even store the active key? Best practice is to sign transactions client-side and never send private keys to a server.

I initially thought about storing encrypted keys server-side, but that is a huge liability. If the server is breached, all user keys are exposed. The better pattern is what Hive Keychain does -- keys stay in the browser extension and the app requests signatures.

The tradeoff is: storing keys server-side = simpler UX but catastrophic breach risk. Client-side signing = more complex UX (user needs Keychain or similar) but keys never leave the user's device. For a wallet app, client-side signing is the only responsible choice.
</think>

For a wallet app, follow the principle of least privilege and never store keys server-side. Here is the security architecture:

```python
# === Key Hierarchy Reference ===
# Owner key:   Account recovery, change other keys
#              NEVER use in apps. Store offline/paper.
# Active key:  Transfers, power up/down, conversions
#              Use only for financial operations.
# Posting key: Vote, post, comment, social custom_json
#              Use for all social features.
# Memo key:    Encrypt/decrypt transfer memos only
#              Cannot sign transactions.

# === Server-Side: NEVER handle private keys ===
# The server prepares unsigned transactions and the client signs them.

import json
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer, Vote
from beem import Hive

# Server creates unsigned transaction
def prepare_transfer(from_account, to_account, amount, memo=""):
    """Build an unsigned transfer for client-side signing."""
    hive = Hive(node=["https://api.hive.blog"])
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Transfer(**{
        "from": from_account,
        "to": to_account,
        "amount": amount,
        "memo": memo
    }))
    # Return the serialized unsigned transaction
    # Client will sign with their active key
    return tx.json()


# === Client-Side: Use Hive Keychain or local signing ===
# For a desktop/CLI wallet where keys ARE on the device:

class SecureLocalWallet:
    """Local wallet that uses keys from environment or keyring."""

    def __init__(self, account):
        self.account = account
        # Keys loaded from OS keyring, not hardcoded or in config files
        self._posting_key = None
        self._active_key = None
        # Owner key is NEVER loaded into the app

    def load_keys_from_keyring(self):
        """Load keys from OS-level secure storage."""
        import keyring
        self._posting_key = keyring.get_password(
            "hive-wallet", f"{self.account}_posting"
        )
        self._active_key = keyring.get_password(
            "hive-wallet", f"{self.account}_active"
        )

    def _get_hive(self, key_type):
        """Get Hive instance with appropriate key only."""
        if key_type == "posting":
            if not self._posting_key:
                raise ValueError("Posting key not loaded")
            keys = [self._posting_key]
        elif key_type == "active":
            if not self._active_key:
                raise ValueError("Active key not loaded")
            keys = [self._active_key]
        else:
            raise ValueError(f"Invalid key type: {key_type}")

        return Hive(
            node=["https://api.hive.blog", "https://api.deathwing.me"],
            keys=keys
        )

    def vote(self, author, permlink, weight=10000):
        """Vote on a post -- uses POSTING key."""
        hive = self._get_hive("posting")
        tx = TransactionBuilder(blockchain_instance=hive)
        tx.appendOps(Vote(**{
            "voter": self.account,
            "author": author,
            "permlink": permlink,
            "weight": weight
        }))
        tx.appendSigner(self.account, "posting")
        tx.sign()
        return tx.broadcast()

    def transfer(self, to, amount, memo=""):
        """Transfer HIVE/HBD -- uses ACTIVE key."""
        hive = self._get_hive("active")
        tx = TransactionBuilder(blockchain_instance=hive)
        tx.appendOps(Transfer(**{
            "from": self.account,
            "to": to,
            "amount": amount,
            "memo": memo
        }))
        tx.appendSigner(self.account, "active")
        tx.sign()
        return tx.broadcast()

    def clear_keys(self):
        """Clear keys from memory when done."""
        self._posting_key = None
        self._active_key = None


# === Key Compromise Response ===

def handle_key_compromise(compromised_key_type, account):
    """Guide for responding to a compromised key."""
    if compromised_key_type == "posting":
        print("1. Use ACTIVE key to change posting key immediately")
        print("2. Revoke any posting authorities granted to apps")
        print("3. Low urgency -- funds are safe")
    elif compromised_key_type == "active":
        print("1. Use OWNER key to change active key IMMEDIATELY")
        print("2. Transfer funds to a safe account first if possible")
        print("3. HIGH urgency -- funds are at risk")
    elif compromised_key_type == "owner":
        print("1. Use account recovery through your recovery partner")
        print("2. This must be done within 30 days")
        print("3. CRITICAL urgency -- full account takeover possible")
```

Golden rules: never store the owner key in any application. Use the posting key for all social operations. Only use the active key for financial operations. Sign client-side whenever possible. Use OS keyring for local key storage, never config files.'''
    },
    {
        "instruction": r'''How do I safely sign and broadcast transactions in a Hive bot that runs unattended on a server? I need to keep keys available but secure.''',
        "output": r'''<think>
Server-side key management for an unattended bot -- this is a common challenge. The bot needs keys available to sign transactions automatically, but the server could be compromised.

Options I can think of:
1. Environment variables -- keys in env vars, not in code or config files. Better than hardcoded but still readable by anyone with server access.
2. Encrypted config file -- keys encrypted at rest, decrypted on startup with a passphrase. But where does the passphrase come from? Still needs to be provided somehow.
3. Secrets manager (AWS Secrets Manager, HashiCorp Vault) -- keys stored in a dedicated secrets service, fetched at runtime. Good security but adds infrastructure dependency.
4. Hardware security module (HSM) -- overkill for most Hive bots.

Hmm, wait, I should also think about minimizing what keys the bot has. A curation bot only needs the posting key. A reward-claiming bot needs the active key but only for claim_reward_balance. Can I limit the bot's authority?

I initially thought about using Hive's account authority system to create a limited-authority sub-account, but actually Hive does not have fine-grained permissions per operation type. You either have posting authority or you do not. But you CAN grant posting authority to a separate bot account, so if the bot account is compromised, you revoke its authority rather than changing your main account's keys.

The tradeoff is: env vars (simple, moderate security) vs secrets manager (secure, complex infrastructure) vs authority delegation (good security model, Hive-native). For most bots, env vars plus authority delegation is a good balance.

Actually, the authority delegation pattern is really important. Let me explain that carefully. You can grant posting authority of your main account to a bot account. The bot only holds the bot account's posting key. If compromised, revoke the bot's authority -- your main keys remain safe.
</think>

Use a combination of authority delegation (Hive-native security) and environment-based key management. This limits blast radius if the server is compromised:

```python
import os
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Account_update, Custom_json, Vote
)
import json

# === Step 1: Set Up Authority Delegation (run once, manually) ===
# Grant your bot account posting authority on your main account
# This way the bot only needs its OWN posting key, not yours

def grant_posting_authority(main_account, bot_account, active_key):
    """Grant bot_account posting authority on main_account.

    Run this ONCE from a secure machine with your active key.
    """
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[active_key]
    )
    acc = Account(main_account, blockchain_instance=hive)

    # Get current posting authority
    posting_auth = acc["posting"]

    # Add bot account if not already authorized
    existing = [a[0] for a in posting_auth["account_auths"]]
    if bot_account not in existing:
        posting_auth["account_auths"].append([bot_account, 1])
        posting_auth["account_auths"].sort(key=lambda x: x[0])

        tx = TransactionBuilder(blockchain_instance=hive)
        tx.appendOps(Account_update(**{
            "account": main_account,
            "posting": posting_auth,
            "memo_key": acc["memo_key"],
            "json_metadata": acc.get("json_metadata", ""),
        }))
        tx.appendSigner(main_account, "active")
        tx.sign()
        tx.broadcast()
        print(f"Granted {bot_account} posting authority on {main_account}")


# === Step 2: Server-Side Bot with Env Var Keys ===

class SecureHiveBot:
    """Bot that uses environment variables for keys."""

    def __init__(self):
        # Keys from environment -- NEVER hardcoded
        posting_key = os.environ.get("HIVE_BOT_POSTING_KEY")
        if not posting_key:
            raise RuntimeError(
                "HIVE_BOT_POSTING_KEY environment variable not set"
            )

        self.bot_account = os.environ.get("HIVE_BOT_ACCOUNT", "mybotaccount")
        self.main_account = os.environ.get("HIVE_MAIN_ACCOUNT", "mymainaccount")

        self.hive = Hive(
            node=[
                "https://api.hive.blog",
                "https://api.deathwing.me",
                "https://api.openhive.network"
            ],
            keys=[posting_key]
        )

    def vote_as_main(self, author, permlink, weight=10000):
        """Vote using main account's delegated authority.

        The bot signs with its own posting key, but the vote
        is from the main account because of authority delegation.
        """
        tx = TransactionBuilder(blockchain_instance=self.hive)
        tx.appendOps(Vote(**{
            "voter": self.main_account,
            "author": author,
            "permlink": permlink,
            "weight": weight
        }))
        # Sign with bot account's key (has delegated authority)
        tx.appendSigner(self.bot_account, "posting")
        tx.sign()
        return tx.broadcast()

    def broadcast_custom_json(self, op_id, data):
        """Broadcast custom_json as main account via delegation."""
        tx = TransactionBuilder(blockchain_instance=self.hive)
        tx.appendOps(Custom_json(**{
            "required_auths": [],
            "required_posting_auths": [self.main_account],
            "id": op_id,
            "json": json.dumps(data, separators=(",", ":"))
        }))
        tx.appendSigner(self.bot_account, "posting")
        tx.sign()
        return tx.broadcast()


# === Step 3: Revoke Authority on Compromise ===

def revoke_posting_authority(main_account, bot_account, active_key):
    """Immediately revoke bot's authority if server is compromised."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[active_key]
    )
    acc = Account(main_account, blockchain_instance=hive)
    posting_auth = acc["posting"]

    posting_auth["account_auths"] = [
        a for a in posting_auth["account_auths"]
        if a[0] != bot_account
    ]

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Account_update(**{
        "account": main_account,
        "posting": posting_auth,
        "memo_key": acc["memo_key"],
        "json_metadata": acc.get("json_metadata", ""),
    }))
    tx.appendSigner(main_account, "active")
    tx.sign()
    tx.broadcast()
    print(f"Revoked {bot_account} authority. Bot is now powerless.")


# === Deployment: systemd service file ===
# Store keys in a root-owned environment file:
# /etc/hive-bot/env (chmod 600, owned by root)
#   HIVE_BOT_POSTING_KEY=5K...
#   HIVE_BOT_ACCOUNT=mybotaccount
#   HIVE_MAIN_ACCOUNT=mymainaccount
#
# systemd service references it with EnvironmentFile=
```

Security layers: authority delegation means the bot never holds your main account's keys. Environment variables keep keys out of code and config files. If the server is compromised, revoke the bot's authority in one transaction -- your main keys remain safe and unchanged.'''
    },
    {
        "instruction": r'''I am worried about transaction replay attacks on Hive. Can someone take a transaction I broadcast and replay it to double-spend or duplicate operations?''',
        "output": r'''<think>
Transaction replay attacks -- let me think about how Hive protects against these.

First, what is a replay attack? Someone captures a valid signed transaction and rebroadcasts it. On a naive system, the second broadcast would execute the same operations again (double transfer, double vote, etc.).

Hive has several built-in protections. Let me remember... Every transaction has a ref_block_num and ref_block_prefix, which tie it to a recent block. The transaction also has an expiration time. The chain rejects transactions that reference blocks too old or that have expired.

Wait, but the more important protection is that Hive nodes track recently processed transaction IDs. If a transaction with the same ID is broadcast again within the expiration window, nodes reject it as a duplicate. The transaction ID is a hash of the transaction content including the ref_block, so it is unique.

Hmm, but what about cross-chain replay? When Hive forked from Steem, the same keys worked on both chains. A transaction signed for Hive could theoretically be replayed on Steem (or vice versa) if both chains accept the same transaction format. Hive addressed this with chain_id in the transaction signing process -- each chain has a unique chain_id that is mixed into the signature.

I initially thought the expiration window was the main protection, but actually it is the combination of: (1) chain_id prevents cross-chain replay, (2) ref_block ties to a specific recent block, (3) expiration prevents old replays, (4) transaction deduplication prevents within-window replays.

Could there be edge cases? If a transaction expires without being included (network issue), can someone replay it? No, because once it expires, nodes reject it. The sender would need to create and sign a new transaction.

Actually, there is one scenario to be careful about: if your app generates multiple identical transactions (same sender, receiver, amount, memo) in quick succession, they would have different ref_blocks and therefore different transaction IDs. Each one is valid and would execute. This is not a replay attack per se, but a bug in the app sending duplicates.
</think>

Hive has robust built-in replay protection through multiple mechanisms. Here is how they work and what you still need to watch for:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer
import time
import hashlib
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

# === Hive's Built-in Replay Protection ===

# 1. Chain ID -- prevents cross-chain replay (Hive vs Steem)
#    Hive chain_id: beeab0de00000000000000000000000000000000000000000000000000000000
#    Steem has a different chain_id
#    The chain_id is mixed into transaction signatures

# 2. Reference block -- ties transaction to recent chain state
#    ref_block_num + ref_block_prefix reference a specific recent block
#    Nodes reject if the referenced block is too old

# 3. Expiration -- transactions have a time-to-live
#    Default is 30 seconds, max is 3600 seconds (1 hour)
#    After expiration, the transaction can never be included

# 4. Transaction deduplication
#    Nodes track recently included transaction IDs
#    Same tx ID rebroadcast = rejected as duplicate

# beem handles all of this automatically:
def safe_transfer(sender, receiver, amount, memo=""):
    """beem automatically sets ref_block, expiration, and chain_id."""
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Transfer(**{
        "from": sender,
        "to": receiver,
        "amount": amount,
        "memo": memo
    }))
    tx.appendSigner(sender, "active")
    tx.sign()
    result = tx.broadcast()

    # The tx now has replay protection via:
    # - ref_block_num/prefix (set during signing)
    # - expiration (30s from now by default)
    # - unique tx ID (hash of signed tx content)
    return result


# === What You DO Need to Protect Against ===
# App-level duplicate submissions (not replay attacks, but similar effect)

class IdempotentTransactionSender:
    """Prevent your own app from sending duplicate transactions."""

    def __init__(self, blockchain_instance):
        self.hive = blockchain_instance
        self.sent_transactions = {}  # dedup_key -> tx_id

    def _make_dedup_key(self, op_type, params):
        """Create a deterministic key for deduplication."""
        raw = json.dumps([op_type, params], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def send_transfer_once(self, sender, receiver, amount, memo="",
                           dedup_id=None):
        """Send a transfer, preventing duplicate sends.

        dedup_id: optional caller-provided idempotency key.
        If not provided, auto-generated from params.
        """
        if dedup_id is None:
            dedup_id = self._make_dedup_key("transfer", {
                "from": sender, "to": receiver,
                "amount": amount, "memo": memo
            })

        if dedup_id in self.sent_transactions:
            prev_tx = self.sent_transactions[dedup_id]
            print(f"Duplicate detected. Already sent as tx {prev_tx}")
            return {"duplicate": True, "original_tx": prev_tx}

        tx = TransactionBuilder(blockchain_instance=self.hive)
        tx.appendOps(Transfer(**{
            "from": sender,
            "to": receiver,
            "amount": amount,
            "memo": memo
        }))
        tx.appendSigner(sender, "active")
        tx.sign()
        result = tx.broadcast()

        self.sent_transactions[dedup_id] = result["id"]
        return result

    def send_with_nonce(self, sender, receiver, amount, nonce):
        """Use a nonce in the memo to make each transfer unique.

        Useful when you legitimately need to send the same amount
        to the same person multiple times (e.g., recurring payments).
        """
        memo = f"payment-{nonce}"
        return self.send_transfer_once(
            sender, receiver, amount, memo,
            dedup_id=f"payment-{nonce}"
        )


# Usage
sender = IdempotentTransactionSender(hive)

# First call sends the transfer
sender.send_transfer_once("alice", "bob", "10.000 HIVE", "payment 1")

# Second identical call is blocked by dedup
sender.send_transfer_once("alice", "bob", "10.000 HIVE", "payment 1")
# Output: "Duplicate detected. Already sent as tx abc123..."

# Recurring payments use nonces to differentiate
sender.send_with_nonce("alice", "bob", "10.000 HIVE", nonce="2024-03-01")
sender.send_with_nonce("alice", "bob", "10.000 HIVE", nonce="2024-04-01")
```

Summary: Hive's protocol-level protections (chain_id, ref_block, expiration, tx dedup) prevent external replay attacks. What you need to guard against is your own app accidentally sending the same logical operation twice due to retries, double-clicks, or race conditions. Use application-level idempotency keys for that.'''
    },
    {
        "instruction": r'''My Hive dApp lets users grant posting authority to the app account. How do I verify that the authority grant is legitimate and handle it securely?''',
        "output": r'''<think>
Posting authority grants -- this is how apps like Splinterlands and PeakD get permission to act on behalf of users. The user adds the app's account to their posting authority list. Then the app can sign posting-level operations for the user using the app account's key.

Let me think about the security considerations. First, verifying the grant: the app needs to check the user's account to confirm that the app account actually has posting authority. You should never assume the grant exists just because the user says so.

Hmm, but there is a subtlety. When should you check? You could check once when the user "connects" and cache the result. But the user could revoke authority at any time. So you should re-verify periodically or before important operations.

I initially thought checking before every operation would be best, but that adds an API call per operation. For a bot doing hundreds of operations per hour, that doubles the API calls. Maybe check once per session and catch the broadcast error if authority was revoked?

Wait, actually, if the authority was revoked and you try to broadcast, the transaction will fail with an "insufficient authority" error. So you could optimistically try and handle the error. That is more efficient than pre-checking every time.

The tradeoff is: pre-check every time (correct but expensive) vs optimistic broadcast with error handling (efficient, same end result). For most apps, optimistic broadcast is fine. Pre-check only on user login/connection.

Another security consideration: the app should request ONLY posting authority, never active. And the app should be transparent about what operations it will perform. Users should be able to see exactly what the app does with their authority.

There is also the question of how the user grants authority. The app should generate the exact transaction and have the user sign it via Keychain or similar. The app should NEVER ask for the user's private keys to set up the authority.
</think>

Verify authority grants on connection, then use optimistic broadcasting with proper error handling. Here is a secure implementation:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Vote, Custom_json
import json

APP_ACCOUNT = "myapp"

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5AppPostingKey"]  # the app account's posting key
)


class AuthorityManager:
    """Manage posting authority grants from users to the app."""

    def __init__(self, app_account, blockchain_instance):
        self.app_account = app_account
        self.hive = blockchain_instance
        self.verified_users = {}  # account -> last_verified_timestamp

    def verify_authority(self, user_account):
        """Check if the app has posting authority on user's account."""
        try:
            acc = Account(user_account, blockchain_instance=self.hive)
            posting_auth = acc["posting"]

            # Check account_auths for our app
            authorized_accounts = [
                a[0] for a in posting_auth.get("account_auths", [])
            ]
            has_authority = self.app_account in authorized_accounts

            if has_authority:
                import time
                self.verified_users[user_account] = time.time()

            return has_authority

        except Exception as e:
            print(f"Error checking authority for {user_account}: {e}")
            return False

    def generate_grant_transaction(self, user_account):
        """Generate the transaction for the user to sign.

        The user signs this via Keychain or their own tools.
        We NEVER handle their keys.
        """
        acc = Account(user_account, blockchain_instance=self.hive)
        posting_auth = acc["posting"]

        # Check if already granted
        existing = [a[0] for a in posting_auth.get("account_auths", [])]
        if self.app_account in existing:
            return {"status": "already_granted"}

        # Build the authority update
        # User will sign this themselves
        new_auth = dict(posting_auth)
        new_auth["account_auths"] = list(posting_auth.get("account_auths", []))
        new_auth["account_auths"].append([self.app_account, 1])
        new_auth["account_auths"].sort(key=lambda x: x[0])

        # Return the operation for the user to sign
        return {
            "status": "needs_signature",
            "operation": ["account_update", {
                "account": user_account,
                "posting": new_auth,
                "memo_key": acc["memo_key"],
                "json_metadata": acc.get("json_metadata", ""),
            }],
            "required_key": "active",
            "instructions": (
                "Sign this transaction with your active key "
                "to grant posting authority to the app. "
                "This allows the app to vote and post on your behalf. "
                "You can revoke this at any time."
            )
        }

    def act_on_behalf(self, user_account, operation):
        """Broadcast an operation on behalf of a user.

        Uses optimistic approach -- broadcast and handle auth errors.
        """
        tx = TransactionBuilder(blockchain_instance=self.hive)
        tx.appendOps(operation)
        tx.appendSigner(self.app_account, "posting")
        tx.sign()

        try:
            result = tx.broadcast()
            return {"success": True, "tx_id": result["id"]}
        except Exception as e:
            error_msg = str(e).lower()
            if "authority" in error_msg or "missing" in error_msg:
                # Authority was revoked -- clean up
                self.verified_users.pop(user_account, None)
                return {
                    "success": False,
                    "error": "authority_revoked",
                    "message": (
                        f"@{user_account} has revoked posting authority. "
                        "Please re-authorize the app."
                    )
                }
            return {"success": False, "error": "broadcast_failed",
                    "message": str(e)}


# === Usage ===

auth_mgr = AuthorityManager(APP_ACCOUNT, hive)

# On user connection: verify authority
user = "someuser"
if auth_mgr.verify_authority(user):
    print(f"@{user} has granted authority -- ready to act")

    # Vote on behalf of user
    vote_op = Vote(**{
        "voter": user,
        "author": "goodauthor",
        "permlink": "great-post",
        "weight": 5000  # 50%
    })
    result = auth_mgr.act_on_behalf(user, vote_op)

    if result["success"]:
        print(f"Voted successfully: {result['tx_id']}")
    elif result["error"] == "authority_revoked":
        print(result["message"])
else:
    # Generate grant transaction for user to sign
    grant_tx = auth_mgr.generate_grant_transaction(user)
    print("User needs to sign this to authorize the app:")
    print(json.dumps(grant_tx, indent=2))
```

Security principles: never touch user private keys (generate unsigned tx for them to sign via Keychain). Verify authority on connection but use optimistic broadcasting for efficiency. Handle authority revocation gracefully. Only request posting authority, never active. Log all operations performed on behalf of users for transparency.'''
    },
    {
        "instruction": r'''How do I encrypt memo messages on Hive transfers so only the recipient can read them? And what are the security implications?''',
        "output": r'''<think>
Encrypted memos on Hive use the memo keys of the sender and recipient. The encryption is based on shared-secret ECDH (Elliptic Curve Diffie-Hellman) -- the sender uses their memo private key and the recipient's memo public key to derive a shared secret, then encrypts the memo with that.

Let me think about how this works in beem. When you prefix a memo with "#", beem automatically encrypts it using the sender's memo key (which must be in the keys list) and the recipient's memo public key (fetched from the chain).

Hmm, but there are security implications I should think about. First, the encrypted memo is stored on-chain forever. If the memo key is ever compromised (now or in the future), all past memos can be decrypted. This is unlike forward-secret protocols like Signal.

Wait, actually, there is a more immediate concern. The memo key is often the same across services. Many users have the same memo key they got when they created the account and never changed it. If an app leaks the memo key, all their encrypted memos become readable.

I initially thought memo encryption was solid, but it has several limitations: no forward secrecy, no key rotation without losing access to old memos, and the memo key cannot be changed independently (it requires the owner key via account_update).

Actually, wait -- you CAN change the memo key with the active key via account_update. But once you change it, you lose the ability to decrypt old memos unless you keep the old key. There is no key rotation protocol that preserves access.

The tradeoff is: encrypted memos are convenient and built-in, but they lack modern encryption properties. For sensitive data, you might want to use a separate encryption scheme and just put the ciphertext in the memo, or use IPFS with encryption and put the link in the memo.
</think>

Hive memos use ECDH encryption with the sender/recipient memo keys. Here is how to use them and the caveats to be aware of:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer
from beem.memo import Memo

# === Sending Encrypted Memos ===

# The memo key MUST be in the keys list for encryption
hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=[
        "5YourActiveKey",   # for signing the transfer
        "5YourMemoKey"      # for encrypting the memo
    ]
)


def send_encrypted_transfer(sender, recipient, amount, secret_message):
    """Send a transfer with an encrypted memo.

    Prefix the memo with '#' to trigger encryption.
    beem handles the ECDH key exchange automatically.
    """
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Transfer(**{
        "from": sender,
        "to": recipient,
        "amount": amount,
        "memo": f"#{secret_message}"  # '#' prefix = encrypt
    }))
    tx.appendSigner(sender, "active")
    tx.sign()
    return tx.broadcast()


# === Decrypting Received Memos ===

def read_encrypted_memo(encrypted_memo_text):
    """Decrypt a memo received in a transfer.

    The hive instance must have your memo private key loaded.
    """
    memo = Memo(blockchain_instance=hive)
    try:
        decrypted = memo.decrypt(encrypted_memo_text)
        return decrypted
    except Exception as e:
        return f"Could not decrypt: {e}"


def get_recent_transfers_decrypted(account_name, limit=20):
    """Fetch recent transfers and decrypt any encrypted memos."""
    acc = Account(account_name, blockchain_instance=hive)
    history = acc.get_account_history(-1, limit,
                                      only_ops=["transfer"])
    transfers = []
    for entry in history:
        op = entry[1]["op"]
        if isinstance(op, list):
            op_data = op[1]
        else:
            op_data = op

        memo = op_data.get("memo", "")

        # Encrypted memos start with '#'
        if memo.startswith("#"):
            try:
                m = Memo(blockchain_instance=hive)
                memo = m.decrypt(memo)
            except Exception:
                memo = "[encrypted - cannot decrypt without memo key]"

        transfers.append({
            "from": op_data["from"],
            "to": op_data["to"],
            "amount": op_data["amount"],
            "memo": memo,
        })

    return transfers


# === Security Considerations ===

# 1. NO FORWARD SECRECY
#    If your memo key is compromised in the future, ALL past
#    encrypted memos can be decrypted. The ciphertext is on-chain
#    forever.

# 2. KEY ROTATION IS LOSSY
#    Changing your memo key means old memos encrypted with the
#    old key cannot be decrypted with the new key. Keep old keys
#    to read old memos.

# 3. MEMO KEY != SIGNING KEY
#    The memo key cannot sign transactions. Compromising it
#    only exposes encrypted memos, not account control.

# 4. For HIGH-SECURITY messaging, use a separate encryption layer:

from cryptography.fernet import Fernet
import base64

def send_double_encrypted(sender, recipient, amount, message,
                          shared_app_secret):
    """Encrypt with app-level key PLUS Hive memo encryption.

    Even if memo keys are compromised, app-level encryption
    still protects the content.
    """
    # Layer 1: App-level encryption (you control key rotation)
    fernet = Fernet(shared_app_secret)
    app_encrypted = fernet.encrypt(message.encode()).decode()

    # Layer 2: Hive memo encryption (ECDH with memo keys)
    # The '#' prefix triggers Hive-level encryption on top
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Transfer(**{
        "from": sender,
        "to": recipient,
        "amount": amount,
        "memo": f"#ENC:{app_encrypted}"
    }))
    tx.appendSigner(sender, "active")
    tx.sign()
    return tx.broadcast()


# Usage
send_encrypted_transfer(
    "alice", "bob", "0.001 HIVE",
    "This message is encrypted on-chain"
)
```

Encrypted memos are fine for casual privacy (hiding transfer reasons from public view). For high-security messaging, add application-level encryption on top, so you control key rotation independently of Hive memo keys. Never rely on memo encryption alone for sensitive data that must remain confidential long-term.'''
    },
]
