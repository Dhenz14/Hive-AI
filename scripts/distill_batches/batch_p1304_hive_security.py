"""Hive security training pairs (part 1): key hierarchy, account recovery, permissions."""

PAIRS = [
    (
        "hive_security/key-hierarchy",
        r'''Explain the Hive blockchain key hierarchy and what each key level can do.''',
        r'''<think>
Hive uses a hierarchical key system with four levels: owner, active, posting, and memo.
Each level has different permissions - owner can do everything including changing other keys,
active handles financial operations, posting handles social operations, and memo is only
for encrypting/decrypting private messages. This design limits damage if a key is compromised.
The hierarchy is strictly enforced at the consensus level.
</think>

Hive uses a **4-level key hierarchy**, each with distinct permissions:

```
Owner Key (highest authority)
├── Change owner/active/posting/memo keys
├── Set recovery account
├── Decline voting rights
└── Everything active key can do

Active Key
├── Transfer HIVE/HBD
├── Power up/down
├── Convert HBD
├── Place market orders
├── Vote for witnesses
├── Update profile (account_update)
└── Everything posting key can do

Posting Key
├── Vote / upvote / downvote
├── Post and comment
├── Reblog (custom_json with posting auth)
├── Follow / mute
└── Claim rewards

Memo Key (lowest - special purpose)
└── Encrypt / decrypt transfer memos
```

**Key security best practices:**

```python
from beem import Hive
from beem.account import Account

hive = Hive(node="https://api.hive.blog")
acct = Account("myaccount", blockchain_instance=hive)

# Inspect authority thresholds and key weights
owner = acct["owner"]
active = acct["active"]
posting = acct["posting"]

print(f"Owner threshold: {owner['weight_threshold']}")
for auth in owner["key_auths"]:
    print(f"  Key: {auth[0][:10]}... weight: {auth[1]}")

print(f"Active threshold: {active['weight_threshold']}")
print(f"Posting threshold: {posting['weight_threshold']}")

# NEVER use owner key in hot wallets or bots
# NEVER use active key for social operations
# ONLY use posting key for dApp integrations
```

**Rule of thumb:** always use the **lowest authority** key that can perform the operation. A compromised posting key cannot steal funds; a compromised active key cannot change the owner key.'''
    ),
    (
        "hive_security/key-derivation-beem",
        r'''How do I derive all four Hive keys from a master password using beem in Python?''',
        r'''<think>
Beem provides PasswordKey class for deterministic key derivation from a master password.
The derivation uses the account name + role + master password to generate unique keys
for each authority level. This is based on BIP-like derivation specific to Graphene chains.
The master password itself is never stored on-chain - only the derived public keys are.
Must emphasize never storing the master password in code.
</think>

Use beem's `PasswordKey` to derive all four keys deterministically:

```python
from beem.account import Account
from beemgraphenebase.account import PasswordKey

def derive_keys(account_name: str, master_password: str) -> dict:
    """Derive all 4 Hive keys from master password.

    The master password + account name + role are hashed together,
    so the same password on different accounts yields different keys.
    """
    roles = ["owner", "active", "posting", "memo"]
    keys = {}

    for role in roles:
        pk = PasswordKey(account_name, master_password, role=role)
        private_wif = str(pk.get_private_key())
        public_key = str(pk.get_public_key())
        keys[role] = {
            "private": private_wif,
            "public": public_key,
        }

    return keys


# Usage
account = "myaccount"
master = "P5some-very-long-master-password-here"

derived = derive_keys(account, master)
for role, keypair in derived.items():
    print(f"{role}:")
    print(f"  Public:  {keypair['public']}")
    # NEVER log private keys in production
    print(f"  Private: {keypair['private'][:8]}...")


def verify_keys_match_chain(account_name: str, derived_keys: dict) -> dict:
    """Check which derived keys match what's on-chain."""
    from beem import Hive
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account_name, blockchain_instance=hive)

    results = {}
    for role in ["owner", "active", "posting"]:
        on_chain_pubkeys = [k[0] for k in acct[role]["key_auths"]]
        results[role] = derived_keys[role]["public"] in on_chain_pubkeys

    # Memo key is stored differently
    results["memo"] = derived_keys["memo"]["public"] == acct["memo_key"]
    return results

match = verify_keys_match_chain(account, derived)
print(f"Keys match chain: {match}")
# e.g. {'owner': True, 'active': True, 'posting': True, 'memo': True}
```

**Security notes:**
- The master password starting with `P5` is a Hive convention, not enforced
- Never store the master password in source code or env vars in production
- If any derived key is changed on-chain independently, the master password will no longer derive matching keys for that role'''
    ),
    (
        "hive_security/key-derivation-dhive",
        r'''Show me how to derive Hive keys from a master password using dhive in JavaScript/TypeScript.''',
        r'''<think>
In dhive, PrivateKey.fromLogin() handles the key derivation from account + password + role.
This mirrors beem's PasswordKey. The derivation is deterministic and uses SHA-256 internally.
The pattern is the same: account name, master password, and role string are combined
and hashed to produce the private key, from which the public key is derived.
Need to show TypeScript types for proper dhive usage.
</think>

```typescript
import { PrivateKey, PublicKey } from "@hiveio/dhive";

interface DerivedKeys {
  owner: { private: PrivateKey; public: PublicKey };
  active: { private: PrivateKey; public: PublicKey };
  posting: { private: PrivateKey; public: PublicKey };
  memo: { private: PrivateKey; public: PublicKey };
}

function deriveKeysFromPassword(
  account: string,
  masterPassword: string
): DerivedKeys {
  const roles = ["owner", "active", "posting", "memo"] as const;
  const keys = {} as DerivedKeys;

  for (const role of roles) {
    // PrivateKey.fromLogin deterministically derives key from
    // SHA256(account + role + password)
    const privateKey = PrivateKey.fromLogin(account, masterPassword, role);
    keys[role] = {
      private: privateKey,
      public: privateKey.createPublic(),
    };
  }

  return keys;
}

// Usage
const account = "myaccount";
const master = "P5my-secure-master-password";
const keys = deriveKeysFromPassword(account, master);

for (const [role, keypair] of Object.entries(keys)) {
  console.log(`${role}:`);
  console.log(`  Public: ${keypair.public.toString()}`);
  // NEVER log private keys in production
}

// Verify against chain
import { Client } from "@hiveio/dhive";

async function verifyKeysOnChain(
  account: string,
  derived: DerivedKeys
): Promise<Record<string, boolean>> {
  const client = new Client(["https://api.hive.blog"]);
  const [acct] = await client.database.getAccounts([account]);

  const results: Record<string, boolean> = {};
  for (const role of ["owner", "active", "posting"] as const) {
    const chainPubkeys = acct[role].key_auths.map(
      ([k]: [string, number]) => k
    );
    results[role] = chainPubkeys.includes(derived[role].public.toString());
  }
  results.memo = acct.memo_key === derived.memo.public.toString();
  return results;
}
```

**Key point:** `PrivateKey.fromLogin()` and beem's `PasswordKey` use the same derivation algorithm, so keys are cross-compatible between JS and Python.'''
    ),
    (
        "hive_security/account-recovery-request",
        r'''How do I create an account recovery request on Hive? Show the process with beem.''',
        r'''<think>
Account recovery on Hive requires the recovery account (set at account creation) to initiate
a request_account_recovery operation. The compromised account owner then has 24 hours to
respond with a recover_account operation proving they know a recent owner key.
The recovery partner specifies the new owner authority the account should get.
This is a critical security feature unique to Hive/Graphene chains.
The recovery account must use its active key to sign the request.
</think>

Account recovery is a two-step process involving the **recovery account partner**:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Request_account_recovery
from beemgraphenebase.account import PasswordKey

def create_recovery_request(
    recovery_account: str,
    account_to_recover: str,
    new_owner_public_key: str,
    recovery_active_key: str,
):
    """Step 1: Recovery partner requests recovery.

    The recovery_account (set at account creation) initiates this.
    The new_owner_public_key is what the victim wants as their new owner key.
    This must be coordinated out-of-band (email, chat, etc).
    """
    hive = Hive(
        node="https://api.hive.blog",
        keys=[recovery_active_key],  # recovery partner's ACTIVE key
    )

    new_owner_authority = {
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [[new_owner_public_key, 1]],
    }

    op = Request_account_recovery(**{
        "recovery_account": recovery_account,
        "account_to_recover": account_to_recover,
        "new_owner_authority": new_owner_authority,
        "extensions": [],
    })

    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(recovery_account, "active")
    tb.sign()
    result = tb.broadcast()
    print(f"Recovery request broadcast: {result}")
    return result


# Example: @hive.blog (the default recovery account) helps @alice
# Alice generates a NEW owner key she wants to use:
new_key = PasswordKey("alice", "new-secure-master-password", role="owner")
new_owner_pub = str(new_key.get_public_key())

create_recovery_request(
    recovery_account="hive.blog",
    account_to_recover="alice",
    new_owner_public_key=new_owner_pub,
    recovery_active_key="5K...",  # hive.blog's active key
)
```

**Important constraints:**
- The recovery account was set when the account was created (default: `@hive.blog` for most accounts)
- The recovery request expires after **24 hours** if not completed
- The victim must complete step 2 (`recover_account`) within that window
- The victim must prove knowledge of an owner key used in the **last 30 days**'''
    ),
    (
        "hive_security/account-recovery-execution",
        r'''Show me how to complete the account recovery process on Hive (the second step, within the 30-day window).''',
        r'''<think>
After the recovery partner creates the request, the compromised account must broadcast
a recover_account operation. This requires TWO owner keys: the new owner key (matching
what was in the request) and a recent owner key (used within the last 30 days).
This proves the real owner is doing the recovery, not the attacker.
The 30-day window refers to the recent owner key validity; the request itself expires in 24h.
This is the most security-critical operation on Hive.
</think>

Step 2: The account owner completes recovery by proving they know a **recent** owner key:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Recover_account

def complete_account_recovery(
    account_to_recover: str,
    recent_owner_private_key: str,  # owner key used in last 30 days
    new_owner_private_key: str,     # matches key in recovery request
    new_owner_public_key: str,
    recent_owner_public_key: str,
):
    """Step 2: Victim completes recovery.

    Must provide:
    - new_owner_authority: matches what recovery partner specified
    - recent_owner_authority: an owner key active on-chain in last 30 days
    Both keys must sign the transaction.
    """
    hive = Hive(
        node="https://api.hive.blog",
        keys=[recent_owner_private_key, new_owner_private_key],
    )

    new_owner_authority = {
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [[new_owner_public_key, 1]],
    }

    recent_owner_authority = {
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [[recent_owner_public_key, 1]],
    }

    op = Recover_account(**{
        "account_to_recover": account_to_recover,
        "new_owner_authority": new_owner_authority,
        "recent_owner_authority": recent_owner_authority,
        "extensions": [],
    })

    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    # Both keys must sign
    tb.appendWif(recent_owner_private_key)
    tb.appendWif(new_owner_private_key)
    tb.sign()
    result = tb.broadcast()
    print(f"Account recovered: {result}")
    return result


# After recovery, immediately change ALL other keys:
from beem.account import Account

def rotate_all_keys_after_recovery(
    account_name: str,
    new_master_password: str,
    new_owner_key: str,  # private key
):
    """After recovery, rotate active, posting, and memo keys."""
    from beemgraphenebase.account import PasswordKey

    hive = Hive(node="https://api.hive.blog", keys=[new_owner_key])
    acct = Account(account_name, blockchain_instance=hive)

    # Derive fresh keys from a NEW master password
    new_keys = {}
    for role in ["active", "posting", "memo"]:
        pk = PasswordKey(account_name, new_master_password, role=role)
        new_keys[role] = str(pk.get_public_key())

    acct.update_account_keys(
        new_keys,
        account=account_name,
    )
    print("All keys rotated. Store new master password securely!")
```

**Critical timeline:**
1. Attacker changes owner key at time T
2. Recovery request must be created within **24 hours** of request (not of attack)
3. Victim must prove knowledge of owner key used within **30 days before the change**
4. After 30 days, the old owner key is no longer valid for recovery'''
    ),
    (
        "hive_security/change-recovery-account",
        r'''How do I change my recovery account on Hive? What are the security implications?''',
        r'''<think>
The change_recovery_account operation lets you designate a different trusted account
as your recovery partner. This is important because the default is usually @hive.blog.
The change takes effect after 30 days for security - prevents an attacker from
immediately changing the recovery account and then using it.
This requires the owner key to broadcast.
</think>

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Change_recovery_account

def change_recovery_account(
    account: str,
    new_recovery_account: str,
    owner_private_key: str,
):
    """Change which account can initiate recovery for you.

    IMPORTANT: Takes effect after a 30-day delay!
    This delay prevents an attacker who has your owner key from
    immediately switching recovery to their own account.
    """
    hive = Hive(
        node="https://api.hive.blog",
        keys=[owner_private_key],
    )

    op = Change_recovery_account(**{
        "account_to_recover": account,
        "new_recovery_account": new_recovery_account,
        "extensions": [],
    })

    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(account, "owner")
    tb.sign()
    result = tb.broadcast()
    print(f"Recovery account change initiated: {result}")
    print(f"New recovery account '{new_recovery_account}' takes effect in 30 days")
    return result


# Check current recovery account
from beem.account import Account
from beem import Hive

def get_recovery_info(account_name: str) -> dict:
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account_name, blockchain_instance=hive)

    return {
        "account": account_name,
        "recovery_account": acct["recovery_account"],
        # Check for pending recovery account changes
        "pending_changes": check_pending_recovery_change(account_name),
    }

def check_pending_recovery_change(account_name: str) -> list:
    """Check if there's a pending recovery account change."""
    from beem import Hive
    hive = Hive(node="https://api.hive.blog")
    result = hive.rpc.find_change_recovery_account_requests(
        {"accounts": [account_name]},
        api="database"
    )
    return result.get("requests", [])


# Recommended: change from default "hive.blog" to a trusted friend
info = get_recovery_info("myaccount")
print(f"Current recovery account: {info['recovery_account']}")

# change_recovery_account("myaccount", "trustedfriend", "5K...")
```

**Security recommendations:**
- Change from default `hive.blog` to a trusted friend or alt account you control
- The 30-day delay is a security feature, not a bug
- Choose someone you can contact out-of-band (phone, in-person)
- Consider a multisig account as your recovery partner for maximum security'''
    ),
    (
        "hive_security/multisig-transaction",
        r'''How do I set up and execute a multisig transaction on Hive?''',
        r'''<think>
Hive supports multisig natively through the authority/weight system. You set multiple
key_auths or account_auths with weights that must sum to meet the weight_threshold.
For example, 2-of-3 multisig means three keys each with weight 1 and threshold 2.
The transaction must be signed by enough keys to meet the threshold.
This is configured via account_update and uses the TransactionBuilder for partial signing.
</think>

Hive has **native multisig** via the authority weight system - no smart contracts needed:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_update, Transfer

def setup_2_of_3_multisig(
    account: str,
    pubkey_1: str,
    pubkey_2: str,
    pubkey_3: str,
    owner_private_key: str,
):
    """Configure active authority as 2-of-3 multisig.

    Any 2 of the 3 keys can authorize active-level operations
    (transfers, power ups, witness votes, etc).
    """
    hive = Hive(node="https://api.hive.blog", keys=[owner_private_key])

    new_active_authority = {
        "weight_threshold": 2,  # need combined weight >= 2
        "account_auths": [],
        "key_auths": [
            [pubkey_1, 1],  # weight 1
            [pubkey_2, 1],  # weight 1
            [pubkey_3, 1],  # weight 1
        ],
    }

    op = Account_update(**{
        "account": account,
        "active": new_active_authority,
        "memo_key": Account(account, blockchain_instance=hive)["memo_key"],
        "json_metadata": "",
    })

    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(account, "owner")  # owner key required to change active
    tb.sign()
    return tb.broadcast()


def create_multisig_transfer(
    sender: str,
    receiver: str,
    amount: str,
    signer_keys: list[str],  # provide at least 2 of 3 private keys
):
    """Execute a transfer requiring 2-of-3 active key signatures."""
    hive = Hive(node="https://api.hive.blog", keys=signer_keys)

    op = Transfer(**{
        "from": sender,
        "to": receiver,
        "amount": amount,
        "memo": "multisig transfer",
    })

    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    # Add each signer's key
    for key in signer_keys:
        tb.appendWif(key)
    tb.sign()
    return tb.broadcast()


# Setup: configure @treasury as 2-of-3
# setup_2_of_3_multisig("treasury", pub1, pub2, pub3, owner_wif)

# Execute: 2 of 3 keyholders sign a transfer
# create_multisig_transfer("treasury", "vendor", "100.000 HIVE", [key_a, key_b])
```

For **offline/asynchronous multisig** (signers not online simultaneously), serialize the partially-signed transaction and pass it between signers:

```python
import json

def create_unsigned_tx(sender: str, receiver: str, amount: str) -> str:
    """Create transaction for offline signing."""
    hive = Hive(node="https://api.hive.blog")
    op = Transfer(**{"from": sender, "to": receiver,
                     "amount": amount, "memo": ""})
    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    return json.dumps(tb.json())

def add_signature(tx_json: str, private_key: str) -> str:
    """Add one signature to a partially signed transaction."""
    hive = Hive(node="https://api.hive.blog", keys=[private_key])
    tb = TransactionBuilder(tx=json.loads(tx_json), blockchain_instance=hive)
    tb.appendWif(private_key)
    tb.sign()
    return json.dumps(tb.json())
```'''
    ),
    (
        "hive_security/threshold-authority",
        r'''Explain how Hive's threshold-based authority system works and show advanced configurations.''',
        r'''<think>
Hive authorities use a weight-threshold model where each key or account in the authority
has a weight, and the combined weight of signers must meet the threshold.
This allows flexible configurations: weighted voting, hierarchical delegation,
account-based authorities (one account can authorize for another).
Advanced patterns include mixed key+account authorities and asymmetric weights.
</think>

Hive's authority system is a **weight-threshold model** - far more flexible than simple multisig:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_update

def configure_weighted_authority(
    account: str,
    owner_key: str,
):
    """Advanced authority configurations."""
    hive = Hive(node="https://api.hive.blog", keys=[owner_key])
    acct = Account(account, blockchain_instance=hive)

    # Pattern 1: Weighted voting (CEO has veto power)
    # CEO key alone (weight 3) meets threshold 3
    # Any 2 board members (weight 2 each) also meet threshold 3
    board_authority = {
        "weight_threshold": 3,
        "account_auths": [],
        "key_auths": [
            ["STM_CEO_PUBLIC_KEY", 3],      # CEO: solo authority
            ["STM_BOARD1_PUBLIC_KEY", 2],    # Board: need 2 of 3
            ["STM_BOARD2_PUBLIC_KEY", 2],
            ["STM_BOARD3_PUBLIC_KEY", 2],
        ],
    }

    # Pattern 2: Mixed key + account authority
    # An account can authorize on behalf of another account
    # Useful for DAOs where a multisig account controls sub-accounts
    mixed_authority = {
        "weight_threshold": 2,
        "account_auths": [
            ["dao-multisig", 2],  # dao-multisig account alone can authorize
        ],
        "key_auths": [
            ["STM_BACKUP_KEY", 1],  # backup key needs a partner
            ["STM_ADMIN_KEY", 1],
        ],
    }

    # Pattern 3: Hierarchical with escape hatch
    # Normal ops need either the org account OR 2 individual keys
    # But a single emergency key can also authorize
    escape_hatch = {
        "weight_threshold": 10,
        "account_auths": [
            ["org-account", 10],     # org alone: full authority
        ],
        "key_auths": [
            ["STM_PERSON_A", 5],     # A+B together: full authority
            ["STM_PERSON_B", 5],
            ["STM_EMERGENCY", 10],   # emergency key: solo override
        ],
    }

    return board_authority, mixed_authority, escape_hatch


def inspect_authority(account_name: str):
    """Analyze an account's authority configuration."""
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account_name, blockchain_instance=hive)

    for role in ["owner", "active", "posting"]:
        auth = acct[role]
        print(f"\n{role.upper()} (threshold: {auth['weight_threshold']}):")

        total_weight = 0
        for pub_key, weight in auth["key_auths"]:
            print(f"  Key {pub_key[:15]}... weight={weight}")
            total_weight += weight

        for acct_name, weight in auth["account_auths"]:
            print(f"  Account @{acct_name} weight={weight}")
            total_weight += weight

        print(f"  Total available weight: {total_weight}")
        if total_weight < auth["weight_threshold"]:
            print(f"  WARNING: impossible to reach threshold!")

inspect_authority("myaccount")
```

**Key insights:**
- `account_auths` lets one Hive account authorize on behalf of another (delegation chains)
- Weights are integers 1-65535; threshold must be reachable by some combination
- If total available weight < threshold, the authority is permanently locked
- Authority changes require the **next higher** level (changing active needs owner)'''
    ),
    (
        "hive_security/custom-authority",
        r'''How do I create a custom authority on Hive that restricts a key to only specific operations?''',
        r'''<think>
Hive added custom authorities (HF26+) that let you create named authorities restricted
to specific operation types. For example, you can create an authority that can ONLY
do transfer operations but not vote for witnesses. This is done via custom_authority
operations. The authority specifies which operation IDs are allowed and has its own
key/account/threshold configuration. This is more granular than posting/active.
</think>

Custom authorities (added in HF26) allow **operation-level access control**:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder

def create_custom_authority(
    account: str,
    auth_name: str,
    allowed_operation_id: int,
    authorized_public_key: str,
    active_private_key: str,
    valid_days: int = 365,
):
    """Create a custom authority that restricts a key to specific operations.

    Operation IDs (common ones):
      2  = transfer
      4  = account_update
      5  = witness_update
      6  = account_witness_vote
      13 = custom_json
      18 = custom_json (posting variant)
    """
    from datetime import datetime, timedelta

    hive = Hive(node="https://api.hive.blog", keys=[active_private_key])

    valid_from = datetime.utcnow()
    valid_to = valid_from + timedelta(days=valid_days)

    op = {
        "type": "create_claimed_account_operation",  # pseudo - use raw op
    }

    # Using raw transaction builder for custom_authority
    custom_auth_op = [
        "create_proposal",  # This is conceptual - actual op below
    ]

    # The actual approach via beem's built-in support:
    from beembase.operations import Custom_json
    import json

    # Create custom authority via account_update2 or direct op
    tb = TransactionBuilder(blockchain_instance=hive)

    # Raw operation for create_custom_authority (not yet in all beem versions)
    raw_op = {
        "type": "create_custom_authority_operation",
        "value": {
            "account": account,
            "auth_name": auth_name,
            "enabled": True,
            "valid_from": valid_from.strftime("%Y-%m-%dT%H:%M:%S"),
            "valid_to": valid_to.strftime("%Y-%m-%dT%H:%M:%S"),
            "operation_id": allowed_operation_id,
            "authority": {
                "weight_threshold": 1,
                "account_auths": [],
                "key_auths": [[authorized_public_key, 1]],
            },
            "restrictions": [],
        },
    }

    tb.appendOps(raw_op)
    tb.appendSigner(account, "active")
    tb.sign()
    return tb.broadcast()


# Example: create "transfer-only" key for a payment bot
# This key can ONLY do transfers, nothing else
# create_custom_authority(
#     account="myshop",
#     auth_name="payment-bot",
#     allowed_operation_id=2,  # transfer only
#     authorized_public_key="STM...",
#     active_private_key="5K...",
# )
```

**Using dhive for custom authorities** (often more up-to-date):

```typescript
import { Client, PrivateKey } from "@hiveio/dhive";

const client = new Client(["https://api.hive.blog"]);

async function createCustomAuthority(
  account: string,
  authName: string,
  operationId: number,
  authorizedPubKey: string,
  activeKey: PrivateKey
) {
  const op = [
    "create_custom_authority",
    {
      account,
      auth_name: authName,
      enabled: true,
      valid_from: new Date().toISOString().split(".")[0],
      valid_to: new Date(Date.now() + 365 * 86400000)
        .toISOString()
        .split(".")[0],
      operation_id: operationId,
      authority: {
        weight_threshold: 1,
        account_auths: [],
        key_auths: [[authorizedPubKey, 1]],
      },
      restrictions: [],
    },
  ];

  return client.broadcast.sendOperations([op], activeKey);
}
```

**Use cases:** payment bots (transfer only), social bots (custom_json only), witnesses (witness_update only).'''
    ),
    (
        "hive_security/posting-authority-grant",
        r'''How do I grant posting authority to a dApp on Hive so it can post on my behalf?''',
        r'''<think>
Granting posting authority to a dApp means adding the dApp's account to your posting
authority's account_auths list. This lets the dApp sign posting-level operations
(votes, comments, custom_json) on your behalf without knowing your private key.
This is the standard pattern used by apps like PeakD, Ecency, Splinterlands.
Done via account_update with the owner or active key.
</think>

```python
from beem import Hive
from beem.account import Account

def grant_posting_authority(
    your_account: str,
    dapp_account: str,
    active_private_key: str,
):
    """Grant a dApp posting authority on your account.

    This lets the dApp's active key sign posting-level operations
    (votes, posts, comments, custom_json) as you.
    The dApp CANNOT do transfers or key changes.
    """
    hive = Hive(node="https://api.hive.blog", keys=[active_private_key])
    acct = Account(your_account, blockchain_instance=hive)

    # Get current posting authority
    posting_auth = acct["posting"]

    # Check if already granted
    existing_accounts = [a[0] for a in posting_auth["account_auths"]]
    if dapp_account in existing_accounts:
        print(f"@{dapp_account} already has posting authority")
        return

    # Add dApp with weight 1 (sufficient for threshold 1)
    posting_auth["account_auths"].append([dapp_account, 1])
    # Must be sorted! Hive requires sorted account_auths
    posting_auth["account_auths"].sort(key=lambda x: x[0])

    acct.update_account_profile(
        posting=posting_auth,
    )
    print(f"Granted posting authority to @{dapp_account}")


def list_posting_authorities(account_name: str) -> list[str]:
    """List all accounts that have posting authority."""
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account_name, blockchain_instance=hive)

    posting = acct["posting"]
    authorized = []

    print(f"Posting authority for @{account_name}:")
    print(f"  Threshold: {posting['weight_threshold']}")

    for pub_key, weight in posting["key_auths"]:
        print(f"  Key: {pub_key[:20]}... (weight {weight})")

    for acct_name, weight in posting["account_auths"]:
        print(f"  Account: @{acct_name} (weight {weight})")
        authorized.append(acct_name)

    return authorized


# Common dApps that request posting authority:
# - peakd.app / ecency / hive.blog (social frontends)
# - splinterlands (gaming)
# - liketu (photo sharing)
# - 3speak (video)

auths = list_posting_authorities("myaccount")
# grant_posting_authority("myaccount", "peakd.app", "5K...")
```

**Security notes:**
- Posting authority only covers: votes, posts, comments, reblogs, custom_json with posting auth
- It does NOT grant: transfers, power up/down, witness votes, key changes
- Always verify the dApp account name is correct (typosquatting risk)
- Periodically audit and revoke unused posting authorities'''
    ),
    (
        "hive_security/revoke-posting-authority",
        r'''How do I revoke posting authority from a Hive dApp that I previously authorized?''',
        r'''<think>
Revoking posting authority means removing the dApp account from the posting authority's
account_auths list. This is done via account_update, removing the specific entry.
Requires the active key. Should periodically audit and clean up unused authorizations.
Important to show how to check current auths first before revoking.
</think>

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_update

def revoke_posting_authority(
    your_account: str,
    dapp_account: str,
    active_private_key: str,
):
    """Revoke posting authority from a dApp."""
    hive = Hive(node="https://api.hive.blog", keys=[active_private_key])
    acct = Account(your_account, blockchain_instance=hive)

    posting_auth = acct["posting"]

    # Find and remove the dApp
    original_count = len(posting_auth["account_auths"])
    posting_auth["account_auths"] = [
        [name, weight]
        for name, weight in posting_auth["account_auths"]
        if name != dapp_account
    ]

    if len(posting_auth["account_auths"]) == original_count:
        print(f"@{dapp_account} doesn't have posting authority")
        return None

    op = Account_update(**{
        "account": your_account,
        "posting": posting_auth,
        "memo_key": acct["memo_key"],
        "json_metadata": acct["json_metadata"],
    })

    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(your_account, "active")
    tb.sign()
    result = tb.broadcast()
    print(f"Revoked posting authority from @{dapp_account}")
    return result


def audit_and_cleanup_authorities(
    account: str,
    known_good_apps: list[str],
    active_private_key: str,
    dry_run: bool = True,
):
    """Audit posting authorities and optionally revoke unknown ones."""
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account, blockchain_instance=hive)

    posting = acct["posting"]
    authorized = [name for name, _ in posting["account_auths"]]

    unknown = [a for a in authorized if a not in known_good_apps]

    print(f"Authorized apps: {authorized}")
    print(f"Known good: {known_good_apps}")
    print(f"Unknown/suspicious: {unknown}")

    if unknown and not dry_run:
        for app in unknown:
            revoke_posting_authority(account, app, active_private_key)
            print(f"  Revoked: @{app}")

    return unknown


# Audit: only keep apps you actively use
unknown = audit_and_cleanup_authorities(
    account="myaccount",
    known_good_apps=["peakd.app", "ecency", "splinterlands"],
    active_private_key="5K...",
    dry_run=True,  # set False to actually revoke
)
```

**Best practice:** run `audit_and_cleanup_authorities` monthly to remove stale dApp authorizations.'''
    ),
    (
        "hive_security/authority-weight-deep-dive",
        r'''Give me a deep dive on Hive's authority weight system - edge cases, pitfalls, and advanced patterns.''',
        r'''<think>
The authority weight system has subtle edge cases: locked accounts (threshold unreachable),
weight overflow, account_auth chains (transitive authority), and the interaction between
key_auths and account_auths. Need to cover the resolution algorithm - how Hive
determines if a transaction is properly authorized. Also the difference between
how owner/active/posting authorities cascade and the special role of account_auths
creating delegation chains.
</think>

Deep dive into Hive's authority resolution engine:

```python
from beem import Hive
from beem.account import Account
from dataclasses import dataclass

@dataclass
class AuthorityAnalysis:
    threshold: int
    total_key_weight: int
    total_account_weight: int
    min_signers: int
    is_locked: bool
    is_single_signer: bool
    delegation_depth: int

def analyze_authority(account_name: str, role: str = "active") -> AuthorityAnalysis:
    """Deep analysis of an account's authority configuration."""
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account_name, blockchain_instance=hive)
    auth = acct[role]

    threshold = auth["weight_threshold"]
    key_weights = [w for _, w in auth["key_auths"]]
    acct_weights = [w for _, w in auth["account_auths"]]

    total_key = sum(key_weights)
    total_acct = sum(acct_weights)
    total = total_key + total_acct

    # Edge case 1: locked account (threshold unreachable)
    is_locked = total < threshold

    # Edge case 2: single signer possible
    max_single = max(key_weights + acct_weights) if (key_weights + acct_weights) else 0
    is_single = max_single >= threshold

    # Calculate minimum signers needed (greedy: largest weights first)
    sorted_weights = sorted(key_weights + acct_weights, reverse=True)
    cumulative = 0
    min_signers = 0
    for w in sorted_weights:
        cumulative += w
        min_signers += 1
        if cumulative >= threshold:
            break

    # Check delegation depth (account_auths can chain)
    depth = _measure_delegation_depth(account_name, role, hive, visited=set())

    return AuthorityAnalysis(
        threshold=threshold,
        total_key_weight=total_key,
        total_account_weight=total_acct,
        min_signers=min_signers if not is_locked else -1,
        is_locked=is_locked,
        is_single_signer=is_single,
        delegation_depth=depth,
    )


def _measure_delegation_depth(
    account: str, role: str, hive: Hive, visited: set, depth: int = 0
) -> int:
    """Recursively measure account_auth delegation chains.

    Pitfall: circular references! A->B->A creates infinite loop.
    Hive consensus limits recursion depth to prevent this.
    """
    if account in visited or depth > 4:  # Hive max depth ~4
        return depth
    visited.add(account)

    try:
        acct = Account(account, blockchain_instance=hive)
        auth = acct[role]
        max_depth = depth
        for delegated_account, _ in auth["account_auths"]:
            d = _measure_delegation_depth(
                delegated_account, role, hive, visited, depth + 1
            )
            max_depth = max(max_depth, d)
        return max_depth
    except Exception:
        return depth


# PITFALL EXAMPLES:

# 1. Accidentally locked account (can never sign active-level ops)
locked_auth = {
    "weight_threshold": 10,
    "account_auths": [],
    "key_auths": [
        ["STM_KEY_A", 3],
        ["STM_KEY_B", 3],
        ["STM_KEY_C", 3],
    ],  # max total = 9, threshold = 10 -> LOCKED
}

# 2. Asymmetric veto: one key has disproportionate power
veto_auth = {
    "weight_threshold": 51,
    "account_auths": [],
    "key_auths": [
        ["STM_MAJORITY", 51],   # can act alone
        ["STM_MINORITY1", 25],  # needs 3 to override
        ["STM_MINORITY2", 25],
    ],
}

# 3. account_auth weight does NOT cascade multiplicatively
# If @dao has threshold=2 with two keys weight=1 each,
# and @myaccount gives @dao weight=5 in its active auth,
# then @dao's keys still need to satisfy @dao's OWN threshold
# before the weight=5 is applied to @myaccount's threshold.

result = analyze_authority("hive.blog", "active")
print(f"Locked: {result.is_locked}")
print(f"Min signers: {result.min_signers}")
print(f"Delegation depth: {result.delegation_depth}")
```

**Critical edge cases to remember:**
- `weight_threshold` of 0 means **anyone can authorize** (never do this)
- Maximum weight per entry: 65535; maximum threshold: 65535
- `account_auths` resolution is recursive but depth-limited (~4 levels)
- Circular `account_auths` references are handled by the depth limit'''
    ),
    (
        "hive_security/encrypted-memo-beem",
        r'''How do I send and receive encrypted memos on Hive using beem?''',
        r'''<think>
Encrypted memos on Hive use shared-secret encryption via ECIES (Elliptic Curve Integrated
Encryption Scheme). The sender encrypts with their memo private key and the recipient's
memo public key. The recipient decrypts with their memo private key and sender's memo
public key. Encrypted memos start with '#' on-chain. Beem handles this transparently
when memo key is provided.
</think>

```python
from beem import Hive
from beem.account import Account
from beem.memo import Memo

def send_encrypted_memo(
    sender: str,
    recipient: str,
    message: str,
    amount: str,
    sender_memo_key: str,  # private memo key of sender
):
    """Send a transfer with an encrypted memo.

    Encrypted memos use ECIES: sender's memo private key +
    recipient's memo public key = shared secret.
    Prefix message with '#' to trigger encryption.
    """
    hive = Hive(
        node="https://api.hive.blog",
        keys=[sender_memo_key],  # memo key for encryption
    )

    # The '#' prefix tells beem to encrypt the memo
    encrypted_message = f"#{message}"

    acct = Account(sender, blockchain_instance=hive)
    result = acct.transfer(
        to=recipient,
        amount=float(amount.split()[0]),
        asset=amount.split()[1],
        memo=encrypted_message,
    )
    print(f"Sent encrypted transfer: {result['trx_id']}")
    return result


def decrypt_memo(
    encrypted_memo: str,
    your_memo_key: str,
):
    """Decrypt a received memo.

    The encrypted memo on-chain looks like:
    '#EncryptedBase58EncodedData...'
    """
    hive = Hive(
        node="https://api.hive.blog",
        keys=[your_memo_key],
    )
    memo = Memo(blockchain_instance=hive)
    decrypted = memo.decrypt(encrypted_memo)
    return decrypted


def read_encrypted_transfers(
    account: str,
    memo_private_key: str,
    limit: int = 10,
):
    """Read recent transfers and decrypt any encrypted memos."""
    hive = Hive(
        node="https://api.hive.blog",
        keys=[memo_private_key],
    )
    acct = Account(account, blockchain_instance=hive)
    memo = Memo(blockchain_instance=hive)

    history = acct.get_account_history(
        index=-1,
        limit=limit,
        only_ops=["transfer"],
    )

    for op in history:
        transfer = op
        raw_memo = transfer.get("memo", "")

        if raw_memo.startswith("#"):
            try:
                decrypted = memo.decrypt(raw_memo)
                print(f"From: {transfer['from']} | Amount: {transfer['amount']}")
                print(f"  Decrypted: {decrypted}")
            except Exception as e:
                print(f"  Could not decrypt (not for us?): {e}")
        elif raw_memo:
            print(f"From: {transfer['from']} | Memo (plain): {raw_memo}")


# Send encrypted memo
# send_encrypted_memo("alice", "bob", "secret meeting at 3pm", "0.001 HIVE", "5K_memo...")

# Read and decrypt received transfers
# read_encrypted_transfers("bob", "5K_bob_memo_key...")
```

**Security notes:**
- Only the sender and recipient can decrypt (shared ECIES secret)
- The `#` prefix is what triggers encryption - without it, memo is plaintext on-chain
- Memo keys are separate from posting/active/owner - compromising memo key only affects message privacy
- Encrypted memos are stored encrypted on-chain forever - if memo key leaks later, old memos can be decrypted'''
    ),
    (
        "hive_security/encrypted-memo-dhive",
        r'''How do I send and read encrypted memos on Hive using dhive (JavaScript)?''',
        r'''<think>
In dhive, encrypted memos work similarly to beem. The Memo class or crypto utilities
handle ECIES encryption. The sender needs their memo private key and the recipient's
memo public key. Dhive's client.broadcast.transfer can handle memo encryption
if configured with the memo key. Need to show both sending and decrypting.
</think>

```typescript
import { Client, PrivateKey, Memo, PublicKey } from "@hiveio/dhive";

const client = new Client(["https://api.hive.blog"]);

async function sendEncryptedMemo(
  sender: string,
  recipient: string,
  amount: string,
  message: string,
  senderActiveKey: PrivateKey,   // for signing the transfer
  senderMemoKey: PrivateKey,     // for encrypting the memo
): Promise<void> {
  // Fetch recipient's memo public key from chain
  const [recipientAcct] = await client.database.getAccounts([recipient]);
  const recipientMemoPub = PublicKey.fromString(recipientAcct.memo_key);

  // Encrypt the memo using ECIES
  const encrypted = Memo.encode(senderMemoKey, recipientMemoPub, `#${message}`);

  const result = await client.broadcast.transfer(
    { from: sender, to: recipient, amount, memo: encrypted },
    senderActiveKey
  );
  console.log(`Encrypted transfer sent: ${result.id}`);
}

async function decryptMemo(
  encryptedMemo: string,
  senderPublicMemoKey: string,
  yourMemoPrivateKey: PrivateKey
): Promise<string> {
  // Decrypt using your memo private key + sender's memo public key
  const senderPub = PublicKey.fromString(senderPublicMemoKey);
  return Memo.decode(yourMemoPrivateKey, encryptedMemo);
}

async function readEncryptedTransfers(
  account: string,
  memoPrivateKey: PrivateKey,
  limit: number = 20
): Promise<void> {
  const history = await client.database.getAccountHistory(
    account, -1, limit,
    // Filter to only transfer operations
    ...([4, 4] as [number, number])  // operation_filter_low, operation_filter_high
  );

  for (const [, op] of history) {
    if (op.op[0] !== "transfer") continue;
    const transfer = op.op[1] as {
      from: string; to: string; amount: string; memo: string;
    };

    if (transfer.memo.startsWith("#")) {
      try {
        // Need sender's memo public key to decrypt
        const [senderAcct] = await client.database.getAccounts([transfer.from]);
        const decrypted = Memo.decode(memoPrivateKey, transfer.memo);
        console.log(
          `From: ${transfer.from} | ${transfer.amount} | Memo: ${decrypted}`
        );
      } catch (e) {
        console.log(`From: ${transfer.from} | Could not decrypt`);
      }
    } else {
      console.log(
        `From: ${transfer.from} | ${transfer.amount} | Memo: ${transfer.memo}`
      );
    }
  }
}

// Usage:
// const activeKey = PrivateKey.fromString("5K_active...");
// const memoKey = PrivateKey.fromString("5K_memo...");
// await sendEncryptedMemo("alice", "bob", "0.001 HIVE", "secret msg", activeKey, memoKey);
// await readEncryptedTransfers("bob", memoKey);
```

**Important:** you need the **active key** to sign the transfer operation and the **memo key** to encrypt/decrypt the memo content. These are two separate keys serving different purposes.'''
    ),
    (
        "hive_security/bot-key-management",
        r'''What are the best patterns for managing Hive keys in a bot or server application?''',
        r'''<think>
Bot key management on Hive requires careful security practices. The main patterns are:
environment variables, encrypted key files, hardware security modules, and the
custom authority approach where the bot gets a restricted key. Should cover
the principle of least privilege - bots should only have the minimum key level needed.
Also need to address key rotation, monitoring, and emergency revocation.
</think>

```python
import os
import json
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from cryptography.fernet import Fernet

class KeyLevel(Enum):
    POSTING = "posting"   # social bots (voting, commenting)
    ACTIVE = "active"     # financial bots (transfers, market)
    MEMO = "memo"         # message bots (encrypted memos)


@dataclass
class BotKeyConfig:
    account: str
    key_level: KeyLevel
    private_key: str


# Pattern 1: Environment variables (simplest, good for containers)
def load_key_from_env(account_env: str = "HIVE_ACCOUNT",
                       key_env: str = "HIVE_POSTING_KEY") -> BotKeyConfig:
    account = os.environ.get(account_env)
    key = os.environ.get(key_env)
    if not account or not key:
        raise EnvironmentError(f"Missing {account_env} or {key_env}")
    return BotKeyConfig(account=account, key_level=KeyLevel.POSTING, private_key=key)


# Pattern 2: Encrypted key file (good for VPS deployments)
class EncryptedKeyStore:
    """Store keys encrypted at rest, decrypt only when needed."""

    def __init__(self, keyfile: Path, encryption_key: Optional[bytes] = None):
        self.keyfile = keyfile
        # Encryption key from env var or hardware token
        self.cipher = Fernet(
            encryption_key or os.environ["BOT_ENCRYPTION_KEY"].encode()
        )

    def store_key(self, account: str, level: str, private_key: str):
        data = json.dumps({
            "account": account, "level": level, "key": private_key,
        }).encode()
        encrypted = self.cipher.encrypt(data)
        self.keyfile.write_bytes(encrypted)
        os.chmod(str(self.keyfile), 0o600)  # owner read/write only

    def load_key(self) -> BotKeyConfig:
        encrypted = self.keyfile.read_bytes()
        data = json.loads(self.cipher.decrypt(encrypted))
        return BotKeyConfig(
            account=data["account"],
            key_level=KeyLevel(data["level"]),
            private_key=data["key"],
        )


# Pattern 3: Delegated authority (RECOMMENDED for bots)
def setup_bot_with_delegated_auth(
    main_account: str,
    bot_account: str,
    main_active_key: str,
):
    """Instead of giving the bot YOUR key, create a bot account
    and grant it posting authority on your main account.

    Benefits:
    - Bot never has your actual keys
    - You can revoke instantly by removing account_auth
    - Bot account can have its own rate limits
    """
    from beem import Hive
    from beem.account import Account

    hive = Hive(node="https://api.hive.blog", keys=[main_active_key])
    acct = Account(main_account, blockchain_instance=hive)

    posting = acct["posting"]
    posting["account_auths"].append([bot_account, 1])
    posting["account_auths"].sort(key=lambda x: x[0])

    acct.update_account_profile(posting=posting)
    print(f"Bot @{bot_account} can now post as @{main_account}")


# Pattern 4: Key hierarchy for multi-function bots
class HiveBotKeyManager:
    """Manage multiple keys with least-privilege principle."""

    def __init__(self):
        self._keys: dict[KeyLevel, str] = {}

    def load_from_env(self):
        """Load only the keys the bot needs."""
        mapping = {
            KeyLevel.POSTING: "HIVE_POSTING_KEY",
            KeyLevel.ACTIVE: "HIVE_ACTIVE_KEY",
            KeyLevel.MEMO: "HIVE_MEMO_KEY",
        }
        for level, env_var in mapping.items():
            key = os.environ.get(env_var)
            if key:
                self._keys[level] = key

    def get_key(self, level: KeyLevel) -> str:
        if level not in self._keys:
            raise PermissionError(
                f"Bot does not have {level.value} key. "
                f"Available: {[k.value for k in self._keys]}"
            )
        return self._keys[level]

    def get_hive_instance(self, level: KeyLevel):
        from beem import Hive
        return Hive(
            node="https://api.hive.blog",
            keys=[self.get_key(level)],
        )


# NEVER do this:
# POSTING_KEY = "5KxxxNeverHardcodeKeysInSource"

# DO this:
# export HIVE_ACCOUNT=mybot
# export HIVE_POSTING_KEY=5K...
# export BOT_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

**Key management rules:**
1. **Least privilege:** voting bot needs posting key only, never active
2. **Never commit keys** to git (use `.gitignore` for key files)
3. **Prefer delegated authority** (Pattern 3) over sharing raw keys
4. **Rotate keys** if any team member leaves or key exposure is suspected
5. **Monitor** your account for unexpected operations (see audit logging)'''
    ),
    (
        "hive_security/key-rotation",
        r'''What are the best practices for rotating keys on Hive? Show me a safe key rotation procedure.''',
        r'''<think>
Key rotation on Hive involves changing keys at each authority level. The order matters:
you must change keys from the bottom up (posting first, then active, then owner) because
changing a higher-level key doesn't invalidate lower-level keys. The owner key is needed
to change active, and active is needed to change posting. After rotation, all services
using the old keys must be updated. Must emphasize the 30-day recovery window implication.
</think>

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_update
from beemgraphenebase.account import PasswordKey
from datetime import datetime
import json


def rotate_all_keys(
    account: str,
    new_master_password: str,
    current_owner_key: str,
):
    """Full key rotation procedure.

    Order: derive new keys -> update on-chain -> verify -> update services.
    Uses owner key because it can change all other keys atomically.
    """
    # Step 1: Derive new keys from new master password
    new_keys = {}
    for role in ["owner", "active", "posting", "memo"]:
        pk = PasswordKey(account, new_master_password, role=role)
        new_keys[role] = {
            "private": str(pk.get_private_key()),
            "public": str(pk.get_public_key()),
        }

    # Step 2: Build the account_update operation
    hive = Hive(node="https://api.hive.blog", keys=[current_owner_key])
    acct = Account(account, blockchain_instance=hive)

    # Preserve existing account_auths (dApp authorizations)
    current_posting = acct["posting"]
    existing_posting_auths = current_posting.get("account_auths", [])

    op = Account_update(**{
        "account": account,
        "owner": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[new_keys["owner"]["public"], 1]],
        },
        "active": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[new_keys["active"]["public"], 1]],
        },
        "posting": {
            "weight_threshold": 1,
            "account_auths": existing_posting_auths,  # keep dApp auths
            "key_auths": [[new_keys["posting"]["public"], 1]],
        },
        "memo_key": new_keys["memo"]["public"],
        "json_metadata": acct["json_metadata"],
    })

    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(account, "owner")
    tb.sign()
    result = tb.broadcast()

    print(f"Keys rotated at {datetime.utcnow().isoformat()}")
    print(f"TX: {result.get('trx_id', 'unknown')}")

    # Step 3: Verify new keys work
    verify_new_keys(account, new_keys)

    return new_keys


def verify_new_keys(account: str, new_keys: dict):
    """Verify new keys match what's on-chain after rotation."""
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account, blockchain_instance=hive)

    for role in ["owner", "active", "posting"]:
        chain_keys = [k[0] for k in acct[role]["key_auths"]]
        expected = new_keys[role]["public"]
        status = "OK" if expected in chain_keys else "MISMATCH"
        print(f"  {role}: {status}")

    memo_status = "OK" if acct["memo_key"] == new_keys["memo"]["public"] else "MISMATCH"
    print(f"  memo: {memo_status}")


def rotation_checklist(account: str):
    """Pre-rotation checklist."""
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account, blockchain_instance=hive)

    print(f"=== Pre-Rotation Checklist for @{account} ===")

    # Check pending recovery
    print(f"Recovery account: {acct['recovery_account']}")
    print("  -> Ensure you can contact them within 30 days")

    # Check posting auths to preserve
    posting_auths = acct["posting"]["account_auths"]
    if posting_auths:
        print(f"Posting auths to preserve: {[a[0] for a in posting_auths]}")

    # Check for active orders
    open_orders = hive.rpc.get_open_orders(account)
    if open_orders:
        print(f"WARNING: {len(open_orders)} open market orders (cancel first!)")

    # Check for pending power downs
    vesting = float(acct["vesting_withdraw_rate"].split()[0])
    if vesting > 0:
        print(f"WARNING: Active power down ({vesting} VESTS/week)")

    print("\nAfter rotation, update keys in:")
    print("  - All bot configurations")
    print("  - HiveKeychain")
    print("  - Any CLI tools or scripts")
    print("  - Password manager")


# rotation_checklist("myaccount")
# new_keys = rotate_all_keys("myaccount", "P5new-ultra-secure-password", "5K_old_owner...")
```

**Rotation schedule recommendations:**
- **Owner key:** rotate yearly or after any security incident
- **Active key:** rotate quarterly for high-value accounts
- **Posting key:** rotate if any authorized dApp is compromised
- **After any team member departure:** rotate all keys they had access to'''
    ),
    (
        "hive_security/keychain-integration",
        r'''How do I integrate HiveKeychain browser extension into a web dApp for secure transaction signing?''',
        r'''<think>
HiveKeychain is a browser extension that stores keys locally and signs transactions
without exposing private keys to the dApp. It provides a JavaScript API injected
into the page via window.hive_keychain. The dApp requests operations, Keychain shows
a popup for user approval, and returns the signed result. This is the most common
auth pattern for Hive web dApps.
</think>

```typescript
// HiveKeychain injects window.hive_keychain into the page

interface KeychainResponse {
  success: boolean;
  error?: string;
  result?: any;
  data?: {
    username: string;
    type: string;
    message?: string;
  };
}

// Check if Keychain is installed
function isKeychainInstalled(): boolean {
  return typeof window.hive_keychain !== "undefined";
}

// Wait for Keychain to load (it injects async)
function waitForKeychain(timeout = 3000): Promise<boolean> {
  return new Promise((resolve) => {
    if (isKeychainInstalled()) return resolve(true);

    let elapsed = 0;
    const interval = setInterval(() => {
      elapsed += 100;
      if (isKeychainInstalled()) {
        clearInterval(interval);
        resolve(true);
      } else if (elapsed >= timeout) {
        clearInterval(interval);
        resolve(false);
      }
    }, 100);
  });
}

// Login / verify identity
async function keychainLogin(username: string): Promise<string | null> {
  return new Promise((resolve) => {
    const challenge = crypto.randomUUID(); // random challenge string
    window.hive_keychain.requestSignBuffer(
      username,
      challenge,
      "Posting", // key level
      (response: KeychainResponse) => {
        if (response.success) {
          // Verify signature server-side for real auth
          resolve(response.result);
        } else {
          console.error("Login failed:", response.error);
          resolve(null);
        }
      }
    );
  });
}

// Vote on a post
async function keychainVote(
  voter: string,
  author: string,
  permlink: string,
  weight: number // -10000 to 10000
): Promise<boolean> {
  return new Promise((resolve) => {
    window.hive_keychain.requestVote(
      voter, permlink, author, weight,
      (response: KeychainResponse) => {
        resolve(response.success);
      }
    );
  });
}

// Transfer with Keychain (user confirms in popup)
async function keychainTransfer(
  from: string,
  to: string,
  amount: string,
  memo: string,
  currency: "HIVE" | "HBD"
): Promise<boolean> {
  return new Promise((resolve) => {
    window.hive_keychain.requestTransfer(
      from, to, amount, memo, currency,
      (response: KeychainResponse) => {
        if (response.success) {
          console.log("Transfer confirmed by user");
          resolve(true);
        } else {
          console.error("Transfer rejected:", response.error);
          resolve(false);
        }
      }
    );
  });
}

// Broadcast custom_json (for layer-2 protocols)
async function keychainCustomJson(
  username: string,
  id: string,
  jsonData: object,
  keyType: "Posting" | "Active" = "Posting"
): Promise<boolean> {
  return new Promise((resolve) => {
    window.hive_keychain.requestCustomJson(
      username,
      id,
      keyType,
      JSON.stringify(jsonData),
      `Confirm ${id} operation`,
      (response: KeychainResponse) => {
        resolve(response.success);
      }
    );
  });
}

// Full integration example
async function initApp() {
  const hasKeychain = await waitForKeychain();
  if (!hasKeychain) {
    document.getElementById("status")!.textContent =
      "Please install HiveKeychain extension";
    return;
  }

  const loginBtn = document.getElementById("login")!;
  loginBtn.addEventListener("click", async () => {
    const username = (document.getElementById("username") as HTMLInputElement).value;
    const sig = await keychainLogin(username);
    if (sig) {
      console.log(`Logged in as @${username}`);
      // Send signature to backend for verification
    }
  });
}
```

**Security benefits of Keychain:**
- Private keys never leave the extension's secure storage
- User explicitly approves each operation in a popup
- dApp JavaScript cannot extract keys
- Works with any Hive operation type'''
    ),
    (
        "hive_security/hivesigner-oauth",
        r'''Show me how to implement HiveSigner OAuth flow for a Hive web application.''',
        r'''<think>
HiveSigner is an OAuth2-like authentication service for Hive. It allows dApps to
request posting authority without users sharing their keys. The flow is:
1. Redirect user to HiveSigner with requested scope
2. User approves on HiveSigner
3. HiveSigner redirects back with access token
4. dApp uses access token to broadcast operations via HiveSigner API
This is server-side friendly, unlike Keychain which is client-side only.
</think>

```typescript
// HiveSigner OAuth2-like flow for server-rendered or SPA apps

// Step 1: Generate authorization URL
function getHiveSignerAuthUrl(config: {
  clientId: string;       // your dApp account name
  redirectUri: string;
  scope: string[];        // e.g., ["vote", "comment", "custom_json"]
  state?: string;         // CSRF protection
}): string {
  const params = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    scope: config.scope.join(","),
    state: config.state || crypto.randomUUID(),
  });
  return `https://hivesigner.com/oauth2/authorize?${params}`;
}

// Step 2: Handle callback (server-side, e.g., Express)
import express from "express";
const app = express();

app.get("/auth/callback", async (req, res) => {
  const { access_token, username, expires_in, state } = req.query;

  // Verify state matches what you sent (CSRF protection)
  if (state !== req.session?.oauthState) {
    return res.status(403).send("Invalid state parameter");
  }

  // Store token securely (encrypted in session or DB)
  req.session!.hiveToken = access_token as string;
  req.session!.hiveUser = username as string;

  res.redirect("/dashboard");
});

// Step 3: Use access token to broadcast operations
async function hiveSignerBroadcast(
  accessToken: string,
  operations: any[]
): Promise<any> {
  const response = await fetch("https://hivesigner.com/api/broadcast", {
    method: "POST",
    headers: {
      "Authorization": accessToken as string,
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    body: JSON.stringify({ operations }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`HiveSigner error: ${error.error_description}`);
  }
  return response.json();
}

// Vote via HiveSigner
async function voteViaHiveSigner(
  token: string,
  voter: string,
  author: string,
  permlink: string,
  weight: number
) {
  return hiveSignerBroadcast(token, [
    ["vote", { voter, author, permlink, weight }],
  ]);
}

// Post comment via HiveSigner
async function commentViaHiveSigner(
  token: string,
  author: string,
  parentAuthor: string,
  parentPermlink: string,
  permlink: string,
  title: string,
  body: string,
) {
  return hiveSignerBroadcast(token, [
    [
      "comment",
      {
        parent_author: parentAuthor,
        parent_permlink: parentPermlink,
        author,
        permlink,
        title,
        body,
        json_metadata: JSON.stringify({ app: "myapp/1.0" }),
      },
    ],
  ]);
}

// Verify token and get user info
async function verifyHiveSignerToken(
  accessToken: string
): Promise<{ user: string; scope: string[] } | null> {
  const response = await fetch("https://hivesigner.com/api/me", {
    headers: { Authorization: accessToken },
  });

  if (!response.ok) return null;

  const data = await response.json();
  return { user: data.user, scope: data.scope };
}

// Usage in your app:
// const authUrl = getHiveSignerAuthUrl({
//   clientId: "myapp",
//   redirectUri: "https://myapp.com/auth/callback",
//   scope: ["vote", "comment", "custom_json"],
// });
// res.redirect(authUrl);  // send user to HiveSigner
```

**HiveSigner vs Keychain:**
- HiveSigner: works without browser extension, server-side compatible, OAuth2 flow
- Keychain: client-side only, lower latency, no server dependency
- Best practice: support both and let users choose'''
    ),
    (
        "hive_security/hiveauth-qr",
        r'''How does HiveAuth work for QR-based authentication on Hive? Show an implementation.''',
        r'''<think>
HiveAuth is a newer auth protocol that uses QR codes and WebSocket communication.
The flow is: dApp generates a challenge, displays QR code, user scans with HiveAuth
mobile app, approves the request, and the dApp receives the signed response via
WebSocket. This is particularly useful for mobile-first or cross-device auth.
It uses PKSA (Public Key Signing App) protocol.
</think>

```typescript
// HiveAuth: QR-based authentication via WebSocket relay

import HiveAuth from "hiveauth-wrapper"; // npm install hiveauth-wrapper

interface HiveAuthConfig {
  appName: string;
  appDescription: string;
  appIcon: string;
}

class HiveAuthClient {
  private config: HiveAuthConfig;
  private authKey: string | null = null;
  private username: string | null = null;
  private expiry: number | null = null;

  constructor(config: HiveAuthConfig) {
    this.config = config;
  }

  /**
   * Start authentication flow.
   * Returns QR code data for user to scan with HiveAuth app.
   */
  async authenticate(
    username: string,
    onQrCode: (qrData: string) => void,
    onSuccess: (token: string) => void,
    onError: (error: string) => void,
    keyType: "posting" | "active" = "posting"
  ): Promise<void> {
    const auth = {
      username,
      expire: Math.floor(Date.now() / 1000) + 86400, // 24h
      key: HiveAuth.generateKey(),
    };

    try {
      const challenge = {
        key_type: keyType,
        challenge: JSON.stringify({
          login: true,
          ts: Date.now(),
          app: this.config.appName,
        }),
      };

      // This generates the QR code payload and opens WebSocket
      const result = await HiveAuth.authenticate(
        auth,
        this.config.appName,
        challenge,
        (evt: { qr: string }) => {
          // Display this QR code to the user
          onQrCode(evt.qr);
        }
      );

      if (result && result.success) {
        this.authKey = auth.key;
        this.username = username;
        this.expiry = auth.expire;
        onSuccess(auth.key);
      }
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    }
  }

  /**
   * Sign a transaction via HiveAuth after authentication.
   */
  async signTransaction(
    username: string,
    operations: any[],
    keyType: "posting" | "active",
    onWaiting: () => void
  ): Promise<any> {
    if (!this.authKey) throw new Error("Not authenticated");

    onWaiting();

    const auth = {
      username,
      key: this.authKey,
      expire: this.expiry,
    };

    return HiveAuth.broadcast(
      auth,
      keyType,
      operations,
      (evt: any) => {
        console.log("Broadcast event:", evt);
      }
    );
  }
}

// React component example
/*
function HiveAuthLogin() {
  const [qrData, setQrData] = useState<string | null>(null);
  const client = useRef(new HiveAuthClient({
    appName: "MyDApp",
    appDescription: "A Hive application",
    appIcon: "https://myapp.com/icon.png",
  }));

  const handleLogin = async (username: string) => {
    await client.current.authenticate(
      username,
      (qr) => setQrData(qr),          // show QR code
      (token) => { setQrData(null); }, // success
      (err) => console.error(err)       // error
    );
  };

  return (
    <div>
      <input id="user" placeholder="Hive username" />
      <button onClick={() => handleLogin(
        (document.getElementById('user') as HTMLInputElement).value
      )}>
        Login with HiveAuth
      </button>
      {qrData && <QRCode value={qrData} size={256} />}
    </div>
  );
}
*/
```

**HiveAuth advantages:**
- No browser extension required (mobile-friendly)
- Keys stay on the user's phone (PKSA app)
- Cross-device: scan QR on phone, authorize on desktop
- WebSocket relay means no direct connection between dApp and user's keys'''
    ),
    (
        "hive_security/detect-unauthorized-key-changes",
        r'''How do I monitor a Hive account for unauthorized key changes and set up alerts?''',
        r'''<think>
Monitoring for unauthorized key changes is critical security. The approach is to watch
the blockchain for account_update and account_update2 operations targeting your account.
You can do this by streaming operations via the Hive API or polling account history.
Should compare current authorities against known-good state and alert on any mismatch.
This is an expert-level security monitoring pattern.
</think>

```python
import json
import time
import hashlib
from datetime import datetime
from beem import Hive
from beem.account import Account
from beem.blockchain import Blockchain
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class AccountSecurityState:
    """Snapshot of an account's security-critical fields."""
    owner_keys: list[str]
    active_keys: list[str]
    posting_keys: list[str]
    posting_account_auths: list[str]
    memo_key: str
    recovery_account: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def fingerprint(self) -> str:
        """Hash of all security-critical fields for quick comparison."""
        data = json.dumps({
            "owner": sorted(self.owner_keys),
            "active": sorted(self.active_keys),
            "posting": sorted(self.posting_keys),
            "posting_auths": sorted(self.posting_account_auths),
            "memo": self.memo_key,
            "recovery": self.recovery_account,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


def capture_security_state(account_name: str) -> AccountSecurityState:
    """Capture current security state of an account."""
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account_name, blockchain_instance=hive)

    return AccountSecurityState(
        owner_keys=[k[0] for k in acct["owner"]["key_auths"]],
        active_keys=[k[0] for k in acct["active"]["key_auths"]],
        posting_keys=[k[0] for k in acct["posting"]["key_auths"]],
        posting_account_auths=[a[0] for a in acct["posting"]["account_auths"]],
        memo_key=acct["memo_key"],
        recovery_account=acct["recovery_account"],
    )


class AccountSecurityMonitor:
    """Monitor accounts for unauthorized security changes."""

    def __init__(
        self,
        accounts: list[str],
        alert_callback: Callable[[str, str, dict], None],
        check_interval: int = 60,
    ):
        self.accounts = accounts
        self.alert = alert_callback
        self.interval = check_interval
        self.known_states: dict[str, AccountSecurityState] = {}

        # Capture initial state
        for account in accounts:
            self.known_states[account] = capture_security_state(account)
            print(f"Baseline for @{account}: {self.known_states[account].fingerprint()}")

    def check_for_changes(self):
        """Compare current state against known-good baseline."""
        for account in self.accounts:
            current = capture_security_state(account)
            baseline = self.known_states[account]

            if current.fingerprint() == baseline.fingerprint():
                continue

            # Determine what changed
            changes = {}
            if current.owner_keys != baseline.owner_keys:
                changes["owner_keys"] = {
                    "old": baseline.owner_keys,
                    "new": current.owner_keys,
                }
            if current.active_keys != baseline.active_keys:
                changes["active_keys"] = {
                    "old": baseline.active_keys,
                    "new": current.active_keys,
                }
            if current.posting_keys != baseline.posting_keys:
                changes["posting_keys"] = {
                    "old": baseline.posting_keys,
                    "new": current.posting_keys,
                }
            if current.posting_account_auths != baseline.posting_account_auths:
                changes["posting_account_auths"] = {
                    "added": [a for a in current.posting_account_auths
                              if a not in baseline.posting_account_auths],
                    "removed": [a for a in baseline.posting_account_auths
                                if a not in current.posting_account_auths],
                }
            if current.memo_key != baseline.memo_key:
                changes["memo_key"] = {"old": baseline.memo_key, "new": current.memo_key}
            if current.recovery_account != baseline.recovery_account:
                changes["recovery_account"] = {
                    "old": baseline.recovery_account,
                    "new": current.recovery_account,
                }

            severity = "CRITICAL" if "owner_keys" in changes or "active_keys" in changes else "WARNING"
            self.alert(account, severity, changes)

    def run(self):
        """Continuous monitoring loop."""
        print(f"Monitoring {len(self.accounts)} accounts every {self.interval}s")
        while True:
            try:
                self.check_for_changes()
            except Exception as e:
                print(f"Monitor error: {e}")
            time.sleep(self.interval)


# Alert implementations
def console_alert(account: str, severity: str, changes: dict):
    print(f"\n{'='*60}")
    print(f"[{severity}] Security change detected on @{account}")
    print(f"Time: {datetime.utcnow().isoformat()}")
    for field, detail in changes.items():
        print(f"  {field}: {json.dumps(detail, indent=4)}")
    print(f"{'='*60}\n")

def webhook_alert(account: str, severity: str, changes: dict):
    import requests
    requests.post("https://your-webhook.example.com/alerts", json={
        "account": account, "severity": severity,
        "changes": changes, "timestamp": datetime.utcnow().isoformat(),
    }, timeout=10)


# Usage:
# monitor = AccountSecurityMonitor(
#     accounts=["myaccount", "mybot"],
#     alert_callback=console_alert,
#     check_interval=30,
# )
# monitor.run()
```

**Real-time alternative:** stream `account_update` operations from the blockchain instead of polling for lower latency detection.'''
    ),
    (
        "hive_security/audit-logging",
        r'''How do I build an audit log system that tracks all key usage and operations for a Hive account?''',
        r'''<think>
Audit logging for Hive accounts means tracking all operations in account history,
categorizing them by key level used, and storing structured logs. This is useful
for security audits, compliance, and detecting anomalies. The approach uses
get_account_history to pull all operations and classifies them by type and
required authority level. Should include persistence and anomaly detection.
</think>

```python
import json
import sqlite3
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from enum import Enum
from beem import Hive
from beem.account import Account


class AuthLevel(Enum):
    OWNER = "owner"
    ACTIVE = "active"
    POSTING = "posting"
    MEMO = "memo"


# Map operation types to required authority level
OP_AUTH_LEVEL = {
    "account_update": AuthLevel.OWNER,
    "account_update2": AuthLevel.OWNER,
    "change_recovery_account": AuthLevel.OWNER,
    "recover_account": AuthLevel.OWNER,
    "transfer": AuthLevel.ACTIVE,
    "transfer_to_vesting": AuthLevel.ACTIVE,
    "withdraw_vesting": AuthLevel.ACTIVE,
    "convert": AuthLevel.ACTIVE,
    "limit_order_create": AuthLevel.ACTIVE,
    "limit_order_cancel": AuthLevel.ACTIVE,
    "account_witness_vote": AuthLevel.ACTIVE,
    "account_witness_proxy": AuthLevel.ACTIVE,
    "vote": AuthLevel.POSTING,
    "comment": AuthLevel.POSTING,
    "custom_json": AuthLevel.POSTING,  # can be active too
    "delete_comment": AuthLevel.POSTING,
    "claim_reward_balance": AuthLevel.POSTING,
}


@dataclass
class AuditEntry:
    timestamp: str
    op_type: str
    auth_level: str
    details: dict
    trx_id: str
    block_num: int


class HiveAuditLogger:
    """Track all operations on a Hive account for security auditing."""

    def __init__(self, db_path: str = "hive_audit.db"):
        self.db = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                op_type TEXT NOT NULL,
                auth_level TEXT NOT NULL,
                trx_id TEXT,
                block_num INTEGER,
                details TEXT,
                flagged BOOLEAN DEFAULT 0
            )
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_account_time
            ON audit_log(account, timestamp)
        """)
        self.db.commit()

    def ingest_history(
        self,
        account_name: str,
        limit: int = 1000,
        since: Optional[datetime] = None,
    ):
        """Pull account history and store as audit entries."""
        hive = Hive(node="https://api.hive.blog")
        acct = Account(account_name, blockchain_instance=hive)

        batch_size = min(limit, 1000)
        history = acct.get_account_history(
            index=-1,
            limit=batch_size,
        )

        entries = []
        for op in history:
            op_type = op["type"]
            timestamp = op.get("timestamp", "")

            if since and datetime.fromisoformat(timestamp) < since:
                continue

            auth_level = OP_AUTH_LEVEL.get(op_type, AuthLevel.POSTING).value

            # For custom_json, check if active auth was used
            if op_type == "custom_json":
                if op.get("required_auths"):
                    auth_level = AuthLevel.ACTIVE.value

            entry = AuditEntry(
                timestamp=timestamp,
                op_type=op_type,
                auth_level=auth_level,
                details=dict(op),
                trx_id=op.get("trx_id", ""),
                block_num=op.get("block", 0),
            )
            entries.append(entry)

        # Store in database
        for e in entries:
            self.db.execute(
                """INSERT OR IGNORE INTO audit_log
                   (account, timestamp, op_type, auth_level, trx_id, block_num, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account_name, e.timestamp, e.op_type, e.auth_level,
                 e.trx_id, e.block_num, json.dumps(e.details)),
            )
        self.db.commit()
        print(f"Ingested {len(entries)} operations for @{account_name}")

    def detect_anomalies(self, account: str) -> list[dict]:
        """Flag suspicious patterns in audit log."""
        anomalies = []

        # 1. Owner-level operations (should be rare)
        cursor = self.db.execute(
            """SELECT timestamp, op_type, details FROM audit_log
               WHERE account=? AND auth_level='owner'
               ORDER BY timestamp DESC""",
            (account,),
        )
        owner_ops = cursor.fetchall()
        if owner_ops:
            anomalies.append({
                "type": "owner_key_usage",
                "severity": "HIGH",
                "count": len(owner_ops),
                "operations": [(ts, op) for ts, op, _ in owner_ops],
            })

        # 2. Unusual transfer volume
        cursor = self.db.execute(
            """SELECT COUNT(*), details FROM audit_log
               WHERE account=? AND op_type='transfer'
               AND timestamp > datetime('now', '-24 hours')""",
            (account,),
        )
        transfer_count = cursor.fetchone()[0]
        if transfer_count > 20:
            anomalies.append({
                "type": "high_transfer_volume",
                "severity": "MEDIUM",
                "count": transfer_count,
                "window": "24h",
            })

        # 3. New posting authorities added
        cursor = self.db.execute(
            """SELECT timestamp, details FROM audit_log
               WHERE account=? AND op_type IN ('account_update', 'account_update2')
               ORDER BY timestamp DESC LIMIT 10""",
            (account,),
        )
        for ts, details_json in cursor.fetchall():
            details = json.loads(details_json)
            if "posting" in details:
                anomalies.append({
                    "type": "authority_change",
                    "severity": "HIGH",
                    "timestamp": ts,
                })

        return anomalies

    def generate_report(self, account: str, days: int = 30) -> str:
        """Generate a human-readable audit report."""
        cursor = self.db.execute(
            """SELECT auth_level, op_type, COUNT(*) as cnt
               FROM audit_log
               WHERE account=? AND timestamp > datetime('now', ?)
               GROUP BY auth_level, op_type
               ORDER BY auth_level, cnt DESC""",
            (account, f"-{days} days"),
        )

        lines = [f"Audit Report for @{account} (last {days} days)", "=" * 50]
        for level, op, count in cursor.fetchall():
            lines.append(f"  [{level:8s}] {op:30s} x{count}")

        anomalies = self.detect_anomalies(account)
        if anomalies:
            lines.append(f"\nAnomalies detected: {len(anomalies)}")
            for a in anomalies:
                lines.append(f"  [{a['severity']}] {a['type']}: {a.get('count', 'N/A')}")

        return "\n".join(lines)


# Usage:
# logger = HiveAuditLogger("audit.db")
# logger.ingest_history("myaccount", limit=2000)
# print(logger.generate_report("myaccount", days=30))
```'''
    ),
    (
        "hive_security/cold-storage-keys",
        r'''What are the best patterns for cold storage of Hive keys?''',
        r'''<think>
Cold storage for Hive keys means keeping owner and active keys completely offline.
Patterns include: paper wallets, encrypted USB drives, hardware wallets (if supported),
split-key approaches (Shamir's Secret Sharing), and air-gapped signing machines.
The key insight for Hive specifically is that you can change the owner key to a cold-storage
key and keep only the posting key online. Need to show practical implementations.
</think>

```python
import json
import hashlib
import secrets
from pathlib import Path
from typing import Optional


class HiveColdStorage:
    """Patterns for offline key storage on Hive."""

    @staticmethod
    def generate_paper_wallet(account: str, master_password: str) -> str:
        """Generate a printable paper wallet with all keys.

        Print this, store in a safe. Never photograph or scan it.
        """
        from beemgraphenebase.account import PasswordKey

        lines = [
            "=" * 60,
            f"HIVE PAPER WALLET - @{account}",
            f"Generated: {__import__('datetime').datetime.utcnow().isoformat()}",
            "=" * 60,
            f"Master Password: {master_password}",
            "",
        ]

        for role in ["owner", "active", "posting", "memo"]:
            pk = PasswordKey(account, master_password, role=role)
            lines.append(f"{role.upper()} KEY:")
            lines.append(f"  Private (WIF): {str(pk.get_private_key())}")
            lines.append(f"  Public:        {str(pk.get_public_key())}")
            lines.append("")

        lines.extend([
            "INSTRUCTIONS:",
            "1. Store this in a fireproof safe or safety deposit box",
            "2. NEVER photograph, scan, or digitize this document",
            "3. Make exactly 2 copies, store in different locations",
            "4. Test recovery with the posting key before storing",
            "=" * 60,
        ])

        return "\n".join(lines)

    @staticmethod
    def shamir_split_key(
        private_key_wif: str,
        threshold: int = 2,
        num_shares: int = 3,
    ) -> list[bytes]:
        """Split a private key using Shamir's Secret Sharing.

        Any `threshold` shares can reconstruct the key.
        Distribute shares to trusted parties in separate locations.
        """
        from hashlib import sha256

        # Using a simple SSS implementation
        # In production, use: pip install shamir-mnemonic
        try:
            from shamir_mnemonic import shamir
            # Convert WIF key to bytes
            key_bytes = private_key_wif.encode("utf-8")
            groups = shamir.generate_mnemonics(
                group_threshold=1,
                groups=[(threshold, num_shares)],
                master_secret=key_bytes.ljust(32, b"\0")[:32],
            )
            return groups[0]  # list of mnemonic strings
        except ImportError:
            # Fallback: manual split (less secure, use proper SSS in production)
            print("WARNING: Install shamir-mnemonic for proper SSS")
            print("pip install shamir-mnemonic")
            raise

    @staticmethod
    def create_encrypted_backup(
        keys: dict,
        backup_passphrase: str,
        output_path: Path,
    ):
        """Create an AES-encrypted key backup file.

        Store on USB drive in a safe. The passphrase should be
        memorized or stored separately from the encrypted file.
        """
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.fernet import Fernet
        import base64

        # Derive encryption key from passphrase
        salt = secrets.token_bytes(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600_000,  # high iteration count for brute-force resistance
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(backup_passphrase.encode()))

        cipher = Fernet(derived_key)
        plaintext = json.dumps(keys).encode()
        encrypted = cipher.encrypt(plaintext)

        # Store salt + encrypted data
        backup = {
            "version": 1,
            "salt": salt.hex(),
            "iterations": 600_000,
            "data": encrypted.decode(),
            "checksum": hashlib.sha256(plaintext).hexdigest()[:8],
        }

        output_path.write_text(json.dumps(backup, indent=2))
        # Set restrictive permissions
        import os
        os.chmod(str(output_path), 0o400)  # read-only, owner only

        print(f"Encrypted backup written to {output_path}")
        print(f"Checksum: {backup['checksum']}")

    @staticmethod
    def restore_from_encrypted_backup(
        backup_path: Path,
        passphrase: str,
    ) -> dict:
        """Restore keys from encrypted backup."""
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.fernet import Fernet
        import base64

        backup = json.loads(backup_path.read_text())
        salt = bytes.fromhex(backup["salt"])

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=backup["iterations"],
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))

        cipher = Fernet(derived_key)
        decrypted = cipher.decrypt(backup["data"].encode())

        # Verify checksum
        checksum = hashlib.sha256(decrypted).hexdigest()[:8]
        if checksum != backup["checksum"]:
            raise ValueError("Checksum mismatch - data corrupted or wrong passphrase")

        return json.loads(decrypted)


# Recommended cold storage strategy:
# 1. Generate strong master password (24+ random words)
# 2. Create paper wallet -> store in safe
# 3. Create encrypted USB backup -> store in different location
# 4. Shamir-split the owner key (2-of-3) -> distribute to trusted parties
# 5. Keep ONLY the posting key on any internet-connected device
# 6. Test recovery before relying on backups
```'''
    ),
    (
        "hive_security/key-backup-recovery",
        r'''What is the proper procedure for backing up and recovering Hive keys?''',
        r'''<think>
Key backup and recovery on Hive requires a systematic approach. The backup should cover
all four key levels, use strong encryption, and include verification steps.
Recovery procedures should be tested periodically. Need to cover the relationship
between master password and individual keys, and what happens if only some keys
are backed up. Also important: the backup must include account metadata like
recovery account setting.
</think>

```python
import json
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from beem import Hive
from beem.account import Account
from beemgraphenebase.account import PasswordKey


@dataclass
class AccountBackup:
    """Complete backup of all account security information."""
    account: str
    backup_date: str
    recovery_account: str
    master_password: str  # if known
    keys: dict  # role -> {private, public}
    posting_auths: list  # dApp authorizations
    witness_votes: list
    proxy: str
    notes: str = ""


def create_full_backup(
    account: str,
    master_password: str,
    output_dir: Path,
) -> AccountBackup:
    """Create a comprehensive account backup."""
    hive = Hive(node="https://api.hive.blog")
    acct = Account(account, blockchain_instance=hive)

    # Derive all keys
    keys = {}
    for role in ["owner", "active", "posting", "memo"]:
        pk = PasswordKey(account, master_password, role=role)
        keys[role] = {
            "private_wif": str(pk.get_private_key()),
            "public": str(pk.get_public_key()),
        }

    # Verify keys match chain
    mismatches = []
    for role in ["owner", "active", "posting"]:
        chain_keys = [k[0] for k in acct[role]["key_auths"]]
        if keys[role]["public"] not in chain_keys:
            mismatches.append(role)

    if acct["memo_key"] != keys["memo"]["public"]:
        mismatches.append("memo")

    if mismatches:
        print(f"WARNING: Keys don't match chain for: {mismatches}")
        print("Master password may have been changed or keys rotated individually")

    backup = AccountBackup(
        account=account,
        backup_date=datetime.utcnow().isoformat(),
        recovery_account=acct["recovery_account"],
        master_password=master_password,
        keys=keys,
        posting_auths=[a[0] for a in acct["posting"]["account_auths"]],
        witness_votes=acct.get("witness_votes", []),
        proxy=acct.get("proxy", ""),
    )

    # Save encrypted
    from cryptography.fernet import Fernet

    enc_key = Fernet.generate_key()
    cipher = Fernet(enc_key)

    backup_data = json.dumps(asdict(backup)).encode()
    encrypted = cipher.encrypt(backup_data)

    output_dir.mkdir(parents=True, exist_ok=True)
    backup_file = output_dir / f"{account}_backup_{datetime.utcnow():%Y%m%d}.enc"
    keyfile = output_dir / f"{account}_backup_{datetime.utcnow():%Y%m%d}.key"

    backup_file.write_bytes(encrypted)
    keyfile.write_bytes(enc_key)

    # Restrictive permissions
    os.chmod(str(backup_file), 0o400)
    os.chmod(str(keyfile), 0o400)

    print(f"Backup saved to: {backup_file}")
    print(f"Encryption key: {keyfile}")
    print("IMPORTANT: Store .key file SEPARATELY from .enc file!")

    return backup


def restore_from_backup(
    backup_file: Path,
    key_file: Path,
) -> AccountBackup:
    """Restore account info from encrypted backup."""
    from cryptography.fernet import Fernet

    enc_key = key_file.read_bytes()
    cipher = Fernet(enc_key)

    encrypted = backup_file.read_bytes()
    decrypted = cipher.decrypt(encrypted)
    data = json.loads(decrypted)

    backup = AccountBackup(**data)
    print(f"Restored backup for @{backup.account}")
    print(f"Backup date: {backup.backup_date}")
    print(f"Recovery account: {backup.recovery_account}")
    return backup


def test_backup_validity(backup: AccountBackup) -> dict:
    """Verify a backup is still valid against the chain."""
    hive = Hive(node="https://api.hive.blog")
    acct = Account(backup.account, blockchain_instance=hive)

    results = {
        "account_exists": True,
        "recovery_account_unchanged": (
            acct["recovery_account"] == backup.recovery_account
        ),
        "key_matches": {},
    }

    for role in ["owner", "active", "posting"]:
        chain_keys = [k[0] for k in acct[role]["key_auths"]]
        results["key_matches"][role] = (
            backup.keys[role]["public"] in chain_keys
        )

    results["key_matches"]["memo"] = (
        acct["memo_key"] == backup.keys["memo"]["public"]
    )

    all_match = all(results["key_matches"].values())
    results["all_keys_valid"] = all_match

    if not all_match:
        print("WARNING: Some backed-up keys no longer match the chain!")
        print("Keys were rotated since this backup was created.")
        for role, matches in results["key_matches"].items():
            if not matches:
                print(f"  MISMATCH: {role}")

    return results


# Backup procedure:
# 1. backup = create_full_backup("myaccount", "P5master...", Path("./backups"))
# 2. Copy .enc to USB drive A, .key to USB drive B
# 3. Store drives in separate physical locations
# 4. Quarterly: test_backup_validity(restore_from_backup(...))
```

**Recovery scenarios:**
- **Lost posting key only:** derive from master password, no chain ops needed
- **Lost all keys, have master password:** derive all keys, verify against chain
- **Master password compromised:** use owner key to rotate all keys immediately
- **Owner key compromised:** initiate account recovery via recovery partner within 30 days'''
    ),
    (
        "hive_security/secure-rpc-communication",
        r'''How do I ensure secure RPC communication with Hive nodes, including TLS verification and node validation?''',
        r'''<think>
Secure RPC communication with Hive nodes involves TLS certificate verification,
node reputation checking, response validation, and failover strategies.
MITM attacks on RPC could lead to transaction manipulation or data falsification.
Should cover: verifying TLS certs, comparing responses across multiple nodes,
checking block signatures, and configuring beem/dhive for secure connections.
This is expert-level operational security.
</think>

```python
import ssl
import json
import hashlib
import requests
from urllib.parse import urlparse
from typing import Optional
from dataclasses import dataclass


@dataclass
class NodeHealth:
    url: str
    reachable: bool
    tls_valid: bool
    head_block: int
    version: str
    latency_ms: float


class SecureHiveRPC:
    """Secure RPC client with TLS verification and multi-node consensus."""

    # Trusted Hive API nodes (verify these independently)
    TRUSTED_NODES = [
        "https://api.hive.blog",
        "https://api.deathwing.me",
        "https://anyx.io",
        "https://hive-api.arcange.eu",
        "https://api.openhive.network",
    ]

    def __init__(
        self,
        nodes: Optional[list[str]] = None,
        verify_tls: bool = True,
        consensus_threshold: int = 2,
    ):
        self.nodes = nodes or self.TRUSTED_NODES
        self.verify_tls = verify_tls
        self.consensus_threshold = consensus_threshold
        self.session = requests.Session()

        if verify_tls:
            self.session.verify = True  # uses system CA bundle
            # For pinned certificates:
            # self.session.verify = "/path/to/hive-ca-bundle.pem"

    def check_node_tls(self, url: str) -> dict:
        """Verify TLS certificate of a Hive node."""
        import socket

        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or 443

        context = ssl.create_default_context()
        try:
            with socket.create_connection((hostname, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    return {
                        "valid": True,
                        "subject": dict(x[0] for x in cert.get("subject", ())),
                        "issuer": dict(x[0] for x in cert.get("issuer", ())),
                        "expires": cert.get("notAfter"),
                        "protocol": ssock.version(),
                    }
        except ssl.SSLCertVerificationError as e:
            return {"valid": False, "error": str(e)}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def rpc_call(self, method: str, params: dict, node: Optional[str] = None) -> dict:
        """Make a single RPC call with TLS verification."""
        url = node or self.nodes[0]
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }

        response = self.session.post(
            url,
            json=payload,
            timeout=10,
            verify=self.verify_tls,
        )
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            raise RuntimeError(f"RPC error: {result['error']}")

        return result.get("result", {})

    def consensus_call(self, method: str, params: dict) -> dict:
        """Query multiple nodes and return result only if they agree.

        Protects against a single compromised node returning false data.
        """
        results = {}
        errors = []

        for node in self.nodes[:self.consensus_threshold + 1]:
            try:
                result = self.rpc_call(method, params, node=node)
                result_hash = hashlib.sha256(
                    json.dumps(result, sort_keys=True).encode()
                ).hexdigest()
                results.setdefault(result_hash, []).append((node, result))
            except Exception as e:
                errors.append((node, str(e)))

        # Find consensus (most common result)
        if not results:
            raise RuntimeError(f"All nodes failed: {errors}")

        best_hash = max(results, key=lambda h: len(results[h]))
        agreeing_nodes = results[best_hash]

        if len(agreeing_nodes) < self.consensus_threshold:
            raise RuntimeError(
                f"No consensus: {len(agreeing_nodes)} agree, "
                f"need {self.consensus_threshold}. "
                f"Possible MITM or node desync."
            )

        return agreeing_nodes[0][1]

    def health_check(self) -> list[NodeHealth]:
        """Check health and TLS status of all configured nodes."""
        import time
        results = []

        for url in self.nodes:
            tls_info = self.check_node_tls(url)
            start = time.monotonic()
            try:
                props = self.rpc_call(
                    "condenser_api.get_dynamic_global_properties", {}, node=url
                )
                latency = (time.monotonic() - start) * 1000
                results.append(NodeHealth(
                    url=url,
                    reachable=True,
                    tls_valid=tls_info.get("valid", False),
                    head_block=props.get("head_block_number", 0),
                    version=props.get("head_block_id", "")[:8],
                    latency_ms=round(latency, 1),
                ))
            except Exception:
                results.append(NodeHealth(
                    url=url, reachable=False, tls_valid=tls_info.get("valid", False),
                    head_block=0, version="", latency_ms=-1,
                ))

        return results


# Usage with beem
def create_secure_hive_instance():
    """Configure beem with TLS verification and multiple nodes."""
    from beem import Hive

    # beem uses requests internally, which verifies TLS by default
    hive = Hive(
        node=[
            "https://api.hive.blog",
            "https://api.deathwing.me",
            "https://anyx.io",
        ],
        # num_retries=3 and auto-failover are beem defaults
    )
    return hive


# Run health check
rpc = SecureHiveRPC()
for node in rpc.health_check():
    status = "OK" if node.reachable and node.tls_valid else "WARN"
    print(f"[{status}] {node.url} block={node.head_block} latency={node.latency_ms}ms")
```

**Key security measures:**
- Always use HTTPS nodes (never plain HTTP)
- Verify TLS certificates (default in requests/beem)
- Use consensus across multiple nodes for critical reads (balances, authorities)
- Monitor for certificate changes that could indicate MITM'''
    ),
    (
        "hive_security/transaction-expiration-replay",
        r'''How does Hive prevent transaction replay attacks, and how should I handle transaction expiration?''',
        r'''<think>
Hive prevents replay attacks through transaction expiration and TaPoS (Transaction as
Proof of Stake). Each transaction includes a ref_block_num and ref_block_prefix that
reference a recent block, plus an expiration time. Transactions are invalid if:
1. They reference a block older than ~65535 blocks
2. They've passed their expiration time (max 1 hour)
3. The same transaction ID has already been included in a block
This is consensus-level protection. Need to show how to handle expiration in code.
</think>

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer
from datetime import datetime, timedelta
import hashlib
import json
import time


class ReplayProtectedTransactions:
    """Understanding and handling Hive's replay attack prevention."""

    def __init__(self, node: str = "https://api.hive.blog"):
        self.hive = Hive(node=node)

    def explain_tapos(self):
        """Transaction as Proof of Stake (TaPoS) fields.

        Every Hive transaction contains:
        - ref_block_num: lower 16 bits of a recent block number
        - ref_block_prefix: first 4 bytes of that block's ID
        - expiration: UTC timestamp when tx becomes invalid

        This ties the transaction to a specific fork of the chain.
        If the chain reorganizes past the reference block, the
        transaction becomes invalid on the new fork.
        """
        props = self.hive.rpc.get_dynamic_global_properties()
        head_block = props["head_block_number"]
        head_block_id = props["head_block_id"]

        # TaPoS fields are derived from a recent block
        ref_block_num = head_block & 0xFFFF  # lower 16 bits
        ref_block_prefix = int(head_block_id[8:16], 16)  # bytes 4-8 of block ID

        print(f"Head block: {head_block}")
        print(f"ref_block_num: {ref_block_num}")
        print(f"ref_block_prefix: {ref_block_prefix}")
        print(f"Valid reference range: blocks {head_block - 65535} to {head_block}")

    def build_transaction_with_expiration(
        self,
        operations: list,
        private_key: str,
        expiration_seconds: int = 60,
    ) -> dict:
        """Build a transaction with explicit expiration control.

        Default expiration is 60 seconds. Maximum is 3600 (1 hour).
        Shorter expiration = smaller replay window.
        """
        if expiration_seconds > 3600:
            raise ValueError("Max expiration is 3600 seconds (1 hour)")
        if expiration_seconds < 1:
            raise ValueError("Expiration must be at least 1 second")

        hive = Hive(
            node="https://api.hive.blog",
            keys=[private_key],
            expiration=expiration_seconds,
        )

        tb = TransactionBuilder(blockchain_instance=hive)
        for op in operations:
            tb.appendOps(op)
        tb.appendWif(private_key)
        tb.sign()

        tx = tb.json()
        print(f"Transaction expiration: {tx['expiration']}")
        print(f"ref_block_num: {tx['ref_block_num']}")
        return tx

    def safe_broadcast_with_retry(
        self,
        operations: list,
        private_key: str,
        max_retries: int = 3,
        expiration_seconds: int = 30,
    ) -> dict:
        """Broadcast with retry logic that handles expiration correctly.

        CRITICAL: On retry, you MUST rebuild the transaction because
        the old one may have expired. Never retry with a stale tx.
        """
        for attempt in range(max_retries):
            try:
                # Always build fresh transaction on each attempt
                hive = Hive(
                    node="https://api.hive.blog",
                    keys=[private_key],
                    expiration=expiration_seconds,
                )

                tb = TransactionBuilder(blockchain_instance=hive)
                for op in operations:
                    tb.appendOps(op)
                tb.appendWif(private_key)
                tb.sign()
                result = tb.broadcast()

                return result

            except Exception as e:
                error_msg = str(e).lower()

                if "expired" in error_msg or "tapos" in error_msg:
                    print(f"Attempt {attempt + 1}: tx expired, rebuilding...")
                    time.sleep(1)  # wait for next block
                    continue

                if "duplicate" in error_msg:
                    # Transaction already included - this is actually success
                    print("Transaction already included in a block")
                    return {"status": "already_included"}

                raise  # unknown error, don't retry

        raise RuntimeError(f"Failed after {max_retries} attempts")


def detect_replay_attack(account: str, hours: int = 24):
    """Check for potential replay attacks by looking for duplicate operations.

    A replay attack on Hive would show identical operations in quick succession.
    """
    hive = Hive(node="https://api.hive.blog")
    from beem.account import Account
    acct = Account(account, blockchain_instance=hive)

    history = list(acct.get_account_history(
        index=-1,
        limit=500,
        only_ops=["transfer"],
    ))

    # Group by operation fingerprint
    op_fingerprints: dict[str, list] = {}
    for op in history:
        fp = hashlib.md5(json.dumps({
            "to": op.get("to"),
            "amount": str(op.get("amount")),
            "memo": op.get("memo", ""),
        }, sort_keys=True).encode()).hexdigest()

        op_fingerprints.setdefault(fp, []).append(op)

    # Flag duplicates within short time windows
    suspicious = []
    for fp, ops in op_fingerprints.items():
        if len(ops) > 1:
            timestamps = [op.get("timestamp", "") for op in ops]
            suspicious.append({
                "fingerprint": fp,
                "count": len(ops),
                "timestamps": timestamps,
                "details": ops[0],
            })

    if suspicious:
        print(f"Found {len(suspicious)} groups of duplicate operations:")
        for s in suspicious:
            print(f"  {s['count']}x transfer to {s['details'].get('to')} "
                  f"amount={s['details'].get('amount')}")
    else:
        print("No duplicate operations detected")

    return suspicious


# Usage:
# rpt = ReplayProtectedTransactions()
# rpt.explain_tapos()
#
# # Short-lived transaction for sensitive operations:
# op = Transfer(**{"from": "alice", "to": "bob",
#                  "amount": "1.000 HIVE", "memo": "payment"})
# rpt.safe_broadcast_with_retry([op], "5K...", expiration_seconds=15)
```

**Key takeaways:**
- Hive transactions expire after at most 1 hour (configurable, shorter is safer)
- TaPoS binds transactions to a specific chain fork
- The blockchain rejects duplicate transaction IDs within the expiration window
- On broadcast retry, always rebuild the transaction from scratch
- For high-value transfers, use short expiration (15-30 seconds)'''
    ),
]
