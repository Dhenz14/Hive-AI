# Hive Security Skill File

## Key Hierarchy

Hive uses a hierarchical key system with four levels. Each account has four key pairs (public + private). Keys are derived from the master password but can be changed independently.

### Key Levels (Highest to Lowest Authority)

```
Owner Key (most powerful)
  |
  +-- Active Key (financial operations)
  |     |
  |     +-- Posting Key (social operations)
  |           |
  |           +-- Memo Key (encryption only)
```

### Owner Key
- **Can do**: Change ALL other keys, recover account, everything active/posting can do
- **Use case**: Emergency recovery, key rotation
- **Store**: Offline, in a safe, never on a server
- **Format**: WIF starting with `5J...` or `5K...`
- **When needed**: Almost never - only for key changes or recovery

### Active Key
- **Can do**: Transfer HIVE/HBD, power up/down, place market orders, vote for witnesses, update active/posting authorities, everything posting can do
- **Use case**: Financial operations, wallet interactions
- **Store**: Encrypted wallet, never in plaintext configs
- **When needed**: Any operation that moves value

### Posting Key
- **Can do**: Post, comment, vote, reblog, follow/mute, custom_json with posting auth
- **Cannot do**: Transfer funds, change keys, vote for witnesses
- **Use case**: Social interactions, dApp logins, game actions
- **Store**: Can be stored in browser extensions (Hive Keychain), apps
- **When needed**: Daily social blockchain interactions

### Memo Key
- **Can do**: Encrypt/decrypt private memos in transfers
- **Cannot do**: Anything else
- **Use case**: Private messaging via transfer memos
- **Store**: Apps that need to read encrypted memos
- **When needed**: Reading/sending encrypted transfer memos

### Key Format

```
# Master password (used to derive all keys)
P5Jxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Private keys (WIF format, start with 5)
5Jxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  (Owner)
5Kxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  (Active)
5Jxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  (Posting)
5Kxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  (Memo)

# Public keys (start with STM)
STM7xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  (Owner Public)
STM8xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  (Active Public)
STM6xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  (Posting Public)
STM5xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  (Memo Public)
```

### Checking Key Type in Code

```python
from beem import Hive
from beem.account import Account

hive = Hive()
acc = Account("username", blockchain_instance=hive)

# Get public keys for each authority level
print("Owner:", acc["owner"]["key_auths"])
print("Active:", acc["active"]["key_auths"])
print("Posting:", acc["posting"]["key_auths"])
print("Memo:", acc["memo_key"])
```

---

## Account Recovery

### How Recovery Works
1. When an account's owner key is changed, there is a **30-day window** for recovery
2. The **recovery account** (set at account creation, changeable) must initiate
3. The rightful owner proves identity by signing with the **previous owner key** (used within the last 30 days)
4. After recovery request, there is a **24-hour waiting period** before it takes effect

### Recovery Process

```
Day 0: Thief changes owner key
  |
  +--> 30-day window starts
  |
Day 1-30: Recovery possible
  |
  1. Recovery account creates recovery request
  2. Rightful owner signs with OLD owner key
  3. 24-hour waiting period
  4. Account recovered with new owner key
  |
Day 31+: Recovery no longer possible
```

### Recovery via beem (Python)

```python
from beem import Hive
from beem.account import Account

# Step 1: Recovery partner requests recovery
hive_recovery = Hive(keys=["5Jxxxxxxx_RECOVERY_ACCOUNT_ACTIVE_KEY"])
hive_recovery.request_account_recovery(
    "account_to_recover",
    recovery_account="recovery_partner",
    new_owner_authority={
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [["STM_NEW_OWNER_PUBLIC_KEY", 1]]
    }
)

# Step 2: Rightful owner confirms recovery (needs OLD owner key)
hive_victim = Hive(keys=[
    "5Jxxxxxxx_OLD_OWNER_KEY",      # previous owner key (within 30 days)
    "5Jxxxxxxx_NEW_OWNER_KEY"       # the new owner key from step 1
])
hive_victim.recover_account(
    "account_to_recover",
    recent_owner_authority={
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [["STM_OLD_OWNER_PUBLIC_KEY", 1]]
    },
    new_owner_authority={
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [["STM_NEW_OWNER_PUBLIC_KEY", 1]]
    }
)

# After 24-hour waiting period, the recovery takes effect
```

### Changing Recovery Account

```python
from beem import Hive

hive = Hive(keys=["5Jxxxxxxx_OWNER_KEY"])
hive.change_recovery_account("myaccount", "new_recovery_partner")
# Takes effect after 30 days (prevents attacker from changing it)
```

### Key Points About Recovery
- Default recovery account is the account that created yours (e.g., `@hive.io`)
- Recovery requires BOTH the recovery partner AND the old owner key
- The old owner key must have been valid within the last 30 days
- After 30 days, if no recovery is initiated, the thief's keys become permanent
- You cannot recover an account if you've lost ALL keys (no password = no recovery)

---

## Authority & Multisig Patterns

### Authority Structure

Each authority level (owner, active, posting) has:
- `weight_threshold`: Minimum total weight required to authorize
- `key_auths`: Array of [public_key, weight] pairs
- `account_auths`: Array of [account_name, weight] pairs

### Single-Sig (Default)

```json
{
    "owner": {
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [["STM_OWNER_PUBLIC_KEY", 1]]
    },
    "active": {
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [["STM_ACTIVE_PUBLIC_KEY", 1]]
    },
    "posting": {
        "weight_threshold": 1,
        "account_auths": [],
        "key_auths": [["STM_POSTING_PUBLIC_KEY", 1]]
    }
}
```

### Multi-Sig Setup

```python
from beem import Hive
from beembase.operations import Account_update

hive = Hive(keys=["5Jxxxxxxx_OWNER_KEY"])  # need owner key to change authorities

# 2-of-3 multisig on active authority
hive.broadcast({
    "operations": [["account_update", {
        "account": "multisig_account",
        "active": {
            "weight_threshold": 2,     # need weight >= 2 to authorize
            "account_auths": [],
            "key_auths": [
                ["STM_KEY_A", 1],      # each key has weight 1
                ["STM_KEY_B", 1],      # so any 2 of 3 can authorize
                ["STM_KEY_C", 1]
            ]
        },
        "json_metadata": ""
    }]]
})
```

### Account-Based Authority (Granting Posting Permission)

```python
from beem import Hive
from beem.account import Account

hive = Hive(keys=["5Jxxxxxxx_ACTIVE_KEY"])
acc = Account("myaccount", blockchain_instance=hive)

# Grant posting authority to a dApp account
# This allows the dApp to post on your behalf using their key
acc.allow(
    foreign="dapp_account",
    weight=1,
    permission="posting",
    threshold=1
)

# Revoke posting authority
acc.disallow(
    foreign="dapp_account",
    permission="posting"
)
```

### Authority Limits
- Maximum **40 authorities** (keys + accounts combined) per role
- Weight and threshold are uint16 (0-65535)
- Account auths are checked recursively but with a depth limit

### JavaScript Example

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const client = new Client(["https://api.hive.blog"]);
const activeKey = PrivateKey.fromString("5Jxxxxxxx_ACTIVE_KEY");

// Grant posting authority to an app
const [account] = await client.database.getAccounts(["myaccount"]);
const posting = account.posting;

// Add new account authority
posting.account_auths.push(["dapp_account", 1]);
posting.account_auths.sort((a, b) => a[0].localeCompare(b[0])); // must be sorted!

await client.broadcast.updateAccount({
    account: "myaccount",
    posting: posting,
    memo_key: account.memo_key,
    json_metadata: account.json_metadata
}, activeKey);
```

---

## Common Security Mistakes

### 1. Exposing Private Keys in Code
```python
# WRONG: Never hardcode keys
hive = Hive(keys=["5JrealPrivateKeyHere"])

# RIGHT: Use environment variables
import os
hive = Hive(keys=[os.environ["HIVE_POSTING_KEY"]])

# RIGHT: Use beem's encrypted wallet
from beem import Hive
hive = Hive()
hive.wallet.unlock("wallet_password")  # keys stored encrypted in SQLite
```

### 2. Using Owner/Active Key When Posting Key Suffices
```python
# WRONG: Using active key for voting
hive = Hive(keys=["5Jxxxxxxx_ACTIVE_WIF"])
hive.vote(100, "@author/permlink", account="myaccount")

# RIGHT: Use posting key for social operations
hive = Hive(keys=["5Jxxxxxxx_POSTING_WIF"])
hive.vote(100, "@author/permlink", account="myaccount")
```

### 3. Leaking Keys in Transactions
```python
# WRONG: Accidentally putting private key in memo
acc.transfer("exchange", 10.0, "HIVE", memo="5JmyPrivateKey...")
# This memo is visible on the public blockchain forever!

# RIGHT: Only put transfer notes in memos
acc.transfer("exchange", 10.0, "HIVE", memo="deposit_id_12345")
```

### 4. Not Validating Key Types
```python
# Always verify you have the right key type before broadcasting
from beem.account import Account

acc = Account("myaccount", blockchain_instance=hive)

# Check if a key matches an authority level
from beemgraphenebase.account import PrivateKey as BPrivateKey
pk = BPrivateKey("5Jxxxxxxx")
public_key = str(pk.pubkey)

posting_keys = [k[0] for k in acc["posting"]["key_auths"]]
active_keys = [k[0] for k in acc["active"]["key_auths"]]

if public_key in posting_keys:
    print("This is a posting key")
elif public_key in active_keys:
    print("This is an active key")
```

### 5. Phishing Site Key Entry
- **Never enter keys on unfamiliar websites**
- Verify URLs carefully (hive.blog vs h1ve.blog)
- Use Hive Keychain browser extension instead of pasting keys
- Keychain signs transactions locally; keys never leave the extension

### 6. Not Setting a Custom Recovery Account
```python
# Check your recovery account
from beem.account import Account
acc = Account("myaccount")
print(f"Recovery account: {acc['recovery_account']}")

# Change to a trusted friend/service
hive = Hive(keys=["5Jxxxxxxx_OWNER_KEY"])
hive.change_recovery_account("myaccount", "trusted_friend")
```

### 7. Ignoring Authority Grants
```python
# Regularly audit what accounts have authority over yours
acc = Account("myaccount")

print("Posting auths:", acc["posting"]["account_auths"])
print("Active auths:", acc["active"]["account_auths"])
print("Owner auths:", acc["owner"]["account_auths"])

# Revoke any unknown/unused authorities immediately
```

### 8. Not Using HTTPS for API Nodes
```python
# WRONG: HTTP is insecure
hive = Hive(node=["http://api.hive.blog"])

# RIGHT: Always use HTTPS
hive = Hive(node=["https://api.hive.blog"])
```

---

## Security Checklist for Hive Application Developers

1. **Never store private keys in source code** - use environment variables or encrypted storage
2. **Use the minimum authority level** - posting key for social ops, active only when needed
3. **Never log or print private keys** - even in debug mode
4. **Validate all user input** - especially permlinks, account names, amounts
5. **Use HTTPS for all API calls** - prevent MITM attacks
6. **Implement rate limiting** - respect RC system, don't spam operations
7. **Handle key rotation** - support users changing their keys
8. **Audit authority grants regularly** - check `account_auths` on all levels
9. **Set a trusted recovery account** - don't leave it as the default
10. **Use Hive Keychain for browser apps** - never ask users to paste private keys
11. **Encrypt sensitive memos** - use memo key for private transfer messages
12. **Store master password separately** - from individual key types
13. **Implement proper error handling** - don't expose key information in error messages
14. **Keep beem/dhive updated** - security patches in newer versions
15. **Multiple API nodes** - failover prevents single point of failure/attack
