# Hive Security — Keys, Authorities & Account Safety

## Key Hierarchy (Most to Least Privileged)

| Key | What It Controls | When to Use | Compromise Impact |
|-----|-----------------|-------------|-------------------|
| **Owner** | Change all other keys, recover account | Almost never — cold storage only | Total account loss |
| **Active** | Transfers, power up/down, witness votes, conversions | Financial operations | Funds at risk |
| **Posting** | Post, comment, vote, reblog, follow, custom_json (social) | Daily social usage | Spam/reputation damage |
| **Memo** | Encrypt/decrypt transfer memos | Reading private memos | Memo privacy lost |

### Key Format
- **Private keys**: WIF format, starts with `5` (51 chars): `5K...` or `5J...`
- **Public keys**: Starts with `STM` (53 chars): `STM7...`
- **Master password**: Used to derive all 4 key pairs — NEVER store or transmit

```python
# Derive keys from master password
from beemgraphenebase.account import PasswordKey

master = "P5K..."  # master password
for role in ["owner", "active", "posting", "memo"]:
    pk = PasswordKey("username", master, role)
    print(f"{role}: {pk.get_private_key()}")   # WIF private
    print(f"{role}: {pk.get_public_key()}")    # STM... public
```

## Authority System

### Weight-Based Multi-Sig
```json
{
  "owner": {
    "weight_threshold": 2,
    "account_auths": [["recovery_partner", 1]],
    "key_auths": [["STM7...", 1], ["STM8...", 1]]
  }
}
```
- **weight_threshold**: Total weight needed to authorize an operation
- **key_auths**: `[public_key, weight]` pairs
- **account_auths**: `[account_name, weight]` pairs (that account's active key can sign)

### Multi-Sig Setup
```python
from beem.account import Account

# 2-of-3 multi-sig on active key
acc = Account("multisig_account", blockchain_instance=h)
h.update_account(
    account="multisig_account",
    active={
        "weight_threshold": 2,
        "key_auths": [
            ["STM_pubkey1", 1],
            ["STM_pubkey2", 1],
            ["STM_pubkey3", 1],
        ],
        "account_auths": []
    }
)
```

## Account Recovery

### How It Works
1. Account has a **recovery partner** (set at creation, changeable by owner)
2. If keys are compromised, owner contacts recovery partner
3. Recovery partner initiates recovery request on-chain
4. Account owner proves identity to recovery partner
5. Owner confirms with a recent owner key (used within last 30 days)
6. **30-day window**: Must use a key that was valid within the last 30 days

### Recovery Process
```python
# Step 1: Recovery partner creates recovery request
h.request_account_recovery(
    recovery_account="recovery_partner",
    account_to_recover="compromised_user",
    new_owner_authority={
        "weight_threshold": 1,
        "key_auths": [["STM_new_owner_pubkey", 1]],
        "account_auths": []
    }
)

# Step 2: Account owner confirms (signs with recent owner key)
h.recover_account(
    account_to_recover="compromised_user",
    recent_owner_authority={"key_auths": [["STM_old_owner_pubkey", 1]], ...},
    new_owner_authority={"key_auths": [["STM_new_owner_pubkey", 1]], ...}
)
```

### Critical Rule
> If you lose your owner key AND it's been >30 days since it was valid, **recovery is impossible**. The account is permanently lost.

## Security Best Practices

### Key Storage
```
DO:
  - Store owner key offline (paper, hardware wallet, encrypted USB)
  - Use posting key for daily app usage (HiveSigner, Keychain)
  - Use active key only when needed, never leave in browser storage
  - Use Hive Keychain browser extension (keys never leave the extension)

DON'T:
  - Store master password in any app
  - Put private keys in environment variables on shared servers
  - Use owner key for posting operations
  - Store keys in plaintext config files committed to git
  - Share keys via Discord, email, or any messaging platform
```

### App Development Security
```python
# NEVER hardcode keys
import os
posting_key = os.environ.get("HIVE_POSTING_KEY")

# NEVER log keys
logger.info(f"Connecting as {username}")  # OK
# logger.info(f"Using key {key}")         # NEVER

# Validate authorities before processing custom_json
def process_transfer(op):
    if "required_auths" not in op or not op["required_auths"]:
        raise SecurityError("Transfer requires active authority")
    # Verify the signer matches the expected account
    if op["required_auths"][0] != expected_sender:
        raise SecurityError("Unauthorized signer")

# Use HiveSigner for web apps (OAuth-style delegation)
# Users approve specific operations without exposing keys
```

### Phishing Prevention
- **Verify URLs**: Only use official sites (hive.blog, peakd.com, ecency.com)
- **Check authorities**: Before signing, verify what operation you're approving
- **Hive Keychain**: Shows exactly what you're signing before confirmation
- **Never enter master password**: Apps should only request the specific key level needed

## Common Security Mistakes
1. **Using owner key for daily operations** — Use posting key instead
2. **Not setting a recovery account** — Default is `steem` (useless). Change to a trusted friend/service
3. **Storing keys in .env committed to git** — Use secrets management
4. **Not validating authority level in custom_json processors** — An active-key operation signed with posting key should be rejected by your L2
5. **Trusting memo field blindly** — Memos can contain phishing links. Never auto-execute memo contents
6. **Single point of failure** — Use multi-sig for high-value accounts
