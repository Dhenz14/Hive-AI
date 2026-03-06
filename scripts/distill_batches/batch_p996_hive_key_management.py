"""Hive blockchain training pairs: key management and authority."""

PAIRS = [
    (
        "hive/key-derivation",
        r'''How does Hive key derivation work? How are the different key types (owner, active, posting, memo) derived from a master password?''',
        r'''<think>
The user is asking about key derivation on Hive. Let me think through how this actually works. My initial assumption might be that each key is generated independently, but actually all four keys derive from a single master password -- that is the whole point of the hierarchical system.

The derivation seed is account_name + role + master_password, which then gets SHA-256 hashed. Wait, is the order role + account_name + password, or account_name + role + password? Let me think... it is account_name + role + password. This matters because getting the concatenation order wrong would produce completely different keys.

Now, could the memo key sign transactions? I considered that possibility since it is derived the same way as the others, but no -- the memo key is special. It is only used for ECDH shared-secret derivation (encrypting/decrypting memos). The blockchain consensus rules simply do not accept the memo key as valid authorization for any operation. So even though it is technically a valid secp256k1 keypair, it has no signing authority.

One thing that might confuse people: changing the master password does not automatically update keys on-chain. Since the derivation is purely client-side, you would need to broadcast an account_update operation with the new public keys. Therefore the on-chain keys and the derived keys can get out of sync if someone changes their password without updating the chain.

The hierarchy goes owner > active > posting, where each higher level can do everything the lower levels can. The memo key sits outside this hierarchy entirely because it serves a fundamentally different purpose.
</think>

Hive uses a deterministic key derivation system where all four key types are derived from a single master password combined with the account name and role. Here is how it works:

```python
from beemgraphenebase.account import PasswordKey, PrivateKey, PublicKey
import hashlib

def derive_keys(account_name, master_password):
    """Derive all four key types from a master password."""
    roles = ["owner", "active", "posting", "memo"]
    keys = {}

    for role in roles:
        # PasswordKey handles the derivation internally:
        # seed = account_name + role + master_password
        # private_key = sha256(seed)
        pk = PasswordKey(account_name, master_password, role=role)
        private_wif = str(pk.get_private_key())
        public_key = str(pk.get_public_key())

        keys[role] = {
            "private": private_wif,
            "public": public_key
        }

    return keys

def manual_derivation(account_name, master_password, role):
    """Show the manual derivation process for educational purposes."""
    # Step 1: Create the seed string
    seed = account_name + role + master_password

    # Step 2: SHA-256 hash the seed
    seed_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    print(f"Seed: {account_name}{role}***")
    print(f"Hash: {seed_hash}")

    # Step 3: The hash becomes the private key bytes
    # Step 4: Derive public key from private key using secp256k1
    pk = PasswordKey(account_name, master_password, role=role)
    private = pk.get_private_key()
    public = pk.get_public_key()

    print(f"Private (WIF): {str(private)}")
    print(f"Public:        {str(public)}")
    return private, public

# Derive all keys for an account
account = "testuser"
password = "P5JsomeRandomMasterPassword123"
keys = derive_keys(account, password)

for role, key_pair in keys.items():
    print(f"\n{role.upper()} key:")
    print(f"  Private: {key_pair['private']}")
    print(f"  Public:  {key_pair['public']}")

# What each key can do:
authority_map = {
    "owner": [
        "Change owner/active/posting/memo keys",
        "Account recovery",
        "Decline voting rights",
        "All active key operations"
    ],
    "active": [
        "Transfer HIVE/HBD",
        "Power up/down",
        "Place market orders",
        "Vote for witnesses",
        "Update profile (active level)",
        "All posting key operations"
    ],
    "posting": [
        "Vote on posts/comments",
        "Post and comment",
        "Follow/mute accounts",
        "Reblog posts",
        "Custom JSON (posting auth)"
    ],
    "memo": [
        "Encrypt/decrypt private memos",
        "Cannot sign any transactions"
    ]
}

print("\n\nKey Authority Hierarchy:")
for role, permissions in authority_map.items():
    print(f"\n{role.upper()}:")
    for p in permissions:
        print(f"  - {p}")
```

Important security notes:
- Never share your master password -- derive individual keys and use only what is needed
- Most dApps should only request the posting key
- The memo key cannot authorize any transactions; it is only for encryption
- Store owner key offline; you should rarely need it
- Each key type is independent once derived -- changing the master password requires updating all keys on-chain
'''
    ),
    (
        "hive/multi-authority-transactions",
        r'''How do I create transactions that require multiple authorities on Hive? For example, operations needing both posting and active keys, or multi-sig setups.''',
        r'''Hive supports multi-authority transactions where different operations in the same transaction require different key types, and also multi-signature authority where an account requires multiple keys to authorize a single operation.

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Transfer, Vote, Custom_json, Account_update
)
import json

# Multi-key transaction: operations requiring different authority levels
def multi_authority_transaction():
    """Single transaction with both posting and active operations."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[
            "5YourPostingKey",
            "5YourActiveKey"
        ]
    )

    tx = TransactionBuilder(hive_instance=hive)

    # This operation needs posting authority
    vote_op = Vote(**{
        "voter": "myaccount",
        "author": "someauthor",
        "permlink": "some-post",
        "weight": 10000
    })
    tx.appendOps(vote_op)

    # This operation needs active authority
    transfer_op = Transfer(**{
        "from": "myaccount",
        "to": "recipient",
        "amount": "1.000 HIVE",
        "memo": "payment"
    })
    tx.appendOps(transfer_op)

    # Sign with both keys
    tx.appendSigner("myaccount", "posting")
    tx.appendSigner("myaccount", "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Multi-auth tx: {result['id']}")
    return result


# Multi-signature authority setup
def setup_multisig_account(account, signers, threshold):
    """Configure an account to require multiple signatures.

    Args:
        account: The account to configure
        signers: List of (account_name, weight) tuples
        threshold: Minimum weight needed to authorize
    """
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=["5YourOwnerKey"]
    )

    # Build the authority structure
    # authority = {weight_threshold, account_auths, key_auths}
    account_auths = [[name, weight] for name, weight in signers]

    update_op = Account_update(**{
        "account": account,
        "active": {
            "weight_threshold": threshold,
            "account_auths": account_auths,
            "key_auths": []  # Can also mix key_auths and account_auths
        },
        "memo_key": "",  # empty string means do not change
        "json_metadata": ""
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(update_op)
    tx.appendSigner(account, "owner")
    tx.sign()
    result = tx.broadcast()
    print(f"Multisig setup: {result['id']}")

# Example: 2-of-3 multisig
# setup_multisig_account("treasury", [
#     ("signer1", 1),
#     ("signer2", 1),
#     ("signer3", 1),
# ], threshold=2)


# Signing a multisig transaction
def sign_multisig_transfer(from_account, to, amount, memo, signer_keys):
    """Create and sign a transfer from a multisig account."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=signer_keys  # Multiple active keys
    )

    tx = TransactionBuilder(hive_instance=hive)
    transfer_op = Transfer(**{
        "from": from_account,
        "to": to,
        "amount": f"{amount:.3f} HIVE",
        "memo": memo
    })
    tx.appendOps(transfer_op)

    # Each signer appends their signature
    for key in signer_keys:
        tx.appendWif(key)

    tx.sign()
    result = tx.broadcast()
    print(f"Multisig transfer: {result['id']}")
    return result
```

Key points about multi-authority on Hive:
- A transaction can contain operations requiring different authority levels
- The transaction must be signed with all required key types
- For multi-sig, the weight_threshold determines how many signatures are needed
- account_auths allow other accounts to sign on behalf of yours
- key_auths allow specific public keys to sign (useful for hardware wallets)
- The owner key can always override active authority, and active can override posting
'''
    ),
    (
        "hive/account-recovery",
        r'''How does account recovery work on Hive? How do I set a recovery account and recover a compromised account?''',
        r'''Account recovery on Hive is a unique security feature. Each account has a designated recovery account (set at creation time) that can help restore access if the owner key is compromised. Here is the complete process:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Change_recovery_account, Request_account_recovery,
    Recover_account
)
from beemgraphenebase.account import PasswordKey
import json

# Step 1: Check your current recovery account
def check_recovery_account(account_name):
    hive = Hive(node=["https://api.hive.blog"])
    acct = Account(account_name, hive_instance=hive)
    recovery = acct.get("recovery_account", "steem")
    print(f"Account: {account_name}")
    print(f"Recovery account: {recovery}")
    print(f"(This account can initiate recovery for you)")
    return recovery

# Step 2: Change your recovery account (takes 30 days to activate)
def change_recovery_account(account_name, new_recovery, owner_key):
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[owner_key]
    )
    op = Change_recovery_account(**{
        "account_to_recover": account_name,
        "new_recovery_account": new_recovery,
        "extensions": []
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(account_name, "owner")
    tx.sign()
    result = tx.broadcast()
    print(f"Recovery account change requested: {result['id']}")
    print("WARNING: Change takes 30 days to become effective!")
    return result

# Step 3: Recovery process (when an account is compromised)
# The recovery account initiates the recovery request

def initiate_recovery(recovery_account, account_to_recover, new_owner_public_key, recovery_active_key):
    """The recovery partner initiates the recovery.

    The new_owner_public_key should be a key that the real owner
    controls but the hacker does not know about.
    """
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[recovery_active_key]
    )

    # The new owner authority the legitimate owner wants
    new_owner_authority = {
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [[new_owner_public_key, 1]]
    }

    op = Request_account_recovery(**{
        "recovery_account": recovery_account,
        "account_to_recover": account_to_recover,
        "new_owner_authority": new_owner_authority,
        "extensions": []
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(recovery_account, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Recovery request submitted: {result['id']}")
    return result

# Step 4: The account owner completes the recovery
def complete_recovery(account_name, old_owner_key, new_owner_key, new_owner_public):
    """The legitimate owner completes recovery by proving
    they know both the old AND new owner key.
    """
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[old_owner_key, new_owner_key]
    )

    new_owner_authority = {
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [[new_owner_public, 1]]
    }

    # Must provide a recent owner authority (within last 30 days)
    recent_owner_authority = {
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [[str(PasswordKey(account_name, old_owner_key, "owner").get_public_key()), 1]]
    }

    op = Recover_account(**{
        "account_to_recover": account_name,
        "new_owner_authority": new_owner_authority,
        "recent_owner_authority": recent_owner_authority,
        "extensions": []
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.sign()
    result = tx.broadcast()
    print(f"Account recovered: {result['id']}")
    return result

# Check recovery status
check_recovery_account("myaccount")
```

Critical rules for account recovery:
- You must have set a recovery account before getting compromised
- The old owner key must have been valid within the last 30 days
- The recovery request expires after 24 hours if not completed
- The recovery account change has a 30-day waiting period (security measure)
- Both the recovery partner and the legitimate owner must participate
- This is why it is important to choose a trusted recovery account at creation time
'''
    ),
    (
        "hive/posting-authority-management",
        r'''How do I grant and revoke posting authority to a dApp on Hive so it can post and vote on my behalf?''',
        r'''Posting authority management is how dApps get permission to perform social operations on your behalf without needing your posting key directly. You add the dApp's account to your posting authority's account_auths list.

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_update2
import json

def get_current_posting_authority(account_name):
    """Display current posting authority configuration."""
    hive = Hive(node=["https://api.hive.blog"])
    acct = Account(account_name, hive_instance=hive)
    posting = acct["posting"]

    print(f"Posting authority for {account_name}:")
    print(f"  Weight threshold: {posting['weight_threshold']}")
    print(f"  Key auths:")
    for key, weight in posting["key_auths"]:
        print(f"    {key} (weight: {weight})")
    print(f"  Account auths (dApps):")
    for acc, weight in posting["account_auths"]:
        print(f"    @{acc} (weight: {weight})")
    return posting

def grant_posting_authority(account_name, dapp_account, active_key):
    """Grant posting authority to a dApp account."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[active_key]
    )
    acct = Account(account_name, hive_instance=hive)
    current_posting = acct["posting"]

    # Check if already authorized
    existing = [a[0] for a in current_posting["account_auths"]]
    if dapp_account in existing:
        print(f"@{dapp_account} already has posting authority")
        return None

    # Add the dApp to account_auths
    new_account_auths = list(current_posting["account_auths"])
    new_account_auths.append([dapp_account, 1])
    # Must be sorted alphabetically
    new_account_auths.sort(key=lambda x: x[0])

    new_posting = {
        "weight_threshold": current_posting["weight_threshold"],
        "account_auths": new_account_auths,
        "key_auths": current_posting["key_auths"]
    }

    op = Account_update2(**{
        "account": account_name,
        "posting": new_posting,
        "extensions": []
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(account_name, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Granted posting authority to @{dapp_account}: {result['id']}")
    return result

def revoke_posting_authority(account_name, dapp_account, active_key):
    """Revoke posting authority from a dApp account."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[active_key]
    )
    acct = Account(account_name, hive_instance=hive)
    current_posting = acct["posting"]

    new_account_auths = [
        [a, w] for a, w in current_posting["account_auths"]
        if a != dapp_account
    ]

    if len(new_account_auths) == len(current_posting["account_auths"]):
        print(f"@{dapp_account} does not have posting authority")
        return None

    new_posting = {
        "weight_threshold": current_posting["weight_threshold"],
        "account_auths": new_account_auths,
        "key_auths": current_posting["key_auths"]
    }

    op = Account_update2(**{
        "account": account_name,
        "posting": new_posting,
        "extensions": []
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(account_name, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Revoked posting authority from @{dapp_account}: {result['id']}")
    return result

# Usage examples
get_current_posting_authority("myaccount")
# grant_posting_authority("myaccount", "peakd.app", "5ActiveKey")
# revoke_posting_authority("myaccount", "peakd.app", "5ActiveKey")
```

Important notes:
- Granting posting authority requires your active key (not posting key)
- The dApp can then sign posting-level operations using its own key
- This is safer than giving your posting key to the dApp directly
- Always review which accounts have your posting authority periodically
- Revoking authority is immediate and also requires your active key
- The account_auths list must be sorted alphabetically when submitting
'''
    ),
    (
        "hive/memo-encryption",
        r'''How do I encrypt and decrypt memo messages on Hive transfers? Show both the sending and receiving sides.''',
        r'''Hive supports encrypted memos on transfer operations. When a memo starts with "#", it is encrypted using a shared secret derived from the sender's memo private key and the recipient's memo public key (Diffie-Hellman key exchange).

```python
from beem import Hive
from beem.account import Account
from beem.memo import Memo
from beemgraphenebase.account import PrivateKey, PublicKey
import json

# Sending an encrypted memo
def send_encrypted_transfer(sender, recipient, amount, asset, message, active_key, memo_key):
    """Send a transfer with an encrypted memo."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[active_key, memo_key]  # Need both active (for transfer) and memo (for encryption)
    )

    # The "#" prefix signals encryption
    encrypted_memo = f"#{message}"

    # beem handles encryption automatically when memo key is provided
    result = hive.transfer(
        to=recipient,
        amount=amount,
        asset=asset,
        memo=encrypted_memo,
        account=sender
    )
    print(f"Encrypted transfer sent: {result}")
    return result

# Reading encrypted memos
def read_encrypted_memos(account_name, memo_private_key, limit=20):
    """Decrypt incoming memos for an account."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[memo_private_key]
    )

    acct = Account(account_name, hive_instance=hive)
    history = acct.get_account_history(
        index=-1,
        limit=limit,
        only_ops=["transfer"]
    )

    memo_obj = Memo(hive_instance=hive)

    for entry in history:
        op = entry["op"]
        if isinstance(op, list):
            op_data = op[1]
        else:
            op_data = op

        raw_memo = op_data.get("memo", "")
        if not raw_memo:
            continue

        if raw_memo.startswith("#"):
            try:
                decrypted = memo_obj.decrypt(raw_memo)
                print(f"From @{op_data['from']} -> @{op_data['to']}")
                print(f"  Amount: {op_data['amount']}")
                print(f"  Memo (decrypted): {decrypted}")
            except Exception as e:
                print(f"  Could not decrypt: {e}")
        else:
            print(f"From @{op_data['from']} -> @{op_data['to']}")
            print(f"  Amount: {op_data['amount']}")
            print(f"  Memo (plaintext): {raw_memo}")

# Manual encryption/decryption for understanding the process
def explain_memo_encryption():
    """Show how memo encryption works under the hood."""
    # Both parties have memo keys on their account
    # Sender: knows their own memo private key + recipient's memo public key
    # Recipient: knows their own memo private key + sender's memo public key

    # The shared secret is computed using ECDH:
    # shared_secret = sender_private * recipient_public
    # shared_secret = recipient_private * sender_public
    # Both produce the same result (Diffie-Hellman property)

    # The message is then AES encrypted with the shared secret
    # The encrypted memo is prefixed with the sender's public key
    # so the recipient knows which key pair to use for decryption

    hive = Hive(node=["https://api.hive.blog"])
    sender_acct = Account("alice", hive_instance=hive)
    recipient_acct = Account("bob", hive_instance=hive)

    sender_memo_pub = sender_acct["memo_key"]
    recipient_memo_pub = recipient_acct["memo_key"]

    print(f"Alice memo public key: {sender_memo_pub}")
    print(f"Bob memo public key:   {recipient_memo_pub}")
    print()
    print("Encryption: AES(shared_secret, message)")
    print("  shared_secret = ECDH(alice_memo_private, bob_memo_public)")
    print("Decryption: AES(shared_secret, ciphertext)")
    print("  shared_secret = ECDH(bob_memo_private, alice_memo_public)")

# Example usage
send_encrypted_transfer(
    sender="alice",
    recipient="bob",
    amount=0.001,
    asset="HIVE",
    message="Secret message: meet at the usual place",
    active_key="5AliceActiveKey",
    memo_key="5AliceMemoKey"
)

read_encrypted_memos("bob", "5BobMemoKey", limit=5)
```

Key points about memo encryption:
- Only memos starting with "#" are encrypted; others are plaintext and visible to everyone
- Encryption uses the memo key pair, not posting or active keys
- The memo key cannot sign transactions; it is solely for encryption
- Both sender and recipient can decrypt (symmetric shared secret)
- Encrypted memos are stored on-chain in encrypted form; only key holders can read them
'''
    ),
]
