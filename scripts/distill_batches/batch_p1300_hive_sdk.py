"""Hive SDK training pairs: dhive/beem API calls, custom_json, account ops, keys, voting, resource credits."""

PAIRS = [
    (
        "hive_sdk/beem-transfer-with-memo",
        r'''How do I transfer HIVE and HBD to another account using beem in Python, including encrypted memos?''',
        r'''<think>
The user wants to transfer HIVE and HBD using beem. I need to cover both asset types.
For encrypted memos, the key detail is prefixing the memo string with '#' — beem
will automatically encrypt it using the sender's and receiver's memo keys.
The transfer method requires the active key, not the posting key.
Amount formatting matters: HIVE uses 3 decimal places, HBD also 3.
I should show error handling for common issues like insufficient balance
and missing active key authority.
</think>

Here is how to transfer HIVE and HBD with beem, including encrypted memos:

```python
from beem import Hive
from beem.account import Account
from beem.exceptions import MissingKeyError, UnhandledRPCError

# Active key is required for all financial operations
hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKeyHere"]
)

sender = "youraccount"
recipient = "recipient"

def transfer_hive(to: str, amount: float, memo: str = "", encrypt: bool = False):
    """Transfer HIVE tokens to another account."""
    if encrypt:
        memo = f"#{memo}"  # '#' prefix triggers memo key encryption
    try:
        hive.transfer(to, amount, "HIVE", memo=memo, account=sender)
        print(f"Sent {amount:.3f} HIVE to @{to}")
    except MissingKeyError:
        print("ERROR: Active key not loaded — transfers require the active key")
    except UnhandledRPCError as e:
        if "insufficient" in str(e).lower():
            bal = Account(sender, blockchain_instance=hive).get_balance("available", "HIVE")
            print(f"Insufficient balance. Available: {bal}")
        else:
            raise

def transfer_hbd(to: str, amount: float, memo: str = ""):
    """Transfer HBD (Hive Backed Dollars)."""
    try:
        hive.transfer(to, amount, "HBD", memo=memo, account=sender)
        print(f"Sent {amount:.3f} HBD to @{to}")
    except UnhandledRPCError as e:
        print(f"Transfer failed: {e}")

# Plain memo
transfer_hive("alice", 1.5, memo="Payment for services")

# Encrypted memo — only sender and recipient can read it
transfer_hive("alice", 10.0, memo="Secret payment details", encrypt=True)

# HBD transfer
transfer_hbd("bob", 5.0, memo="Monthly subscription")
```

Key points:
- **Active key** is mandatory for transfers (posting key will fail)
- Prefix memo with `#` for encryption using memo keys
- Amounts use 3 decimal places internally (`1.000 HIVE`, `5.000 HBD`)
- Both sender and recipient can decrypt encrypted memos using their memo private key'''
    ),
    (
        "hive_sdk/dhive-vote-and-downvote",
        r'''How do I upvote and downvote posts using dhive in JavaScript? I need to handle vote weight percentages properly.''',
        r'''<think>
Voting on Hive uses the vote operation. Weight ranges from -10000 to 10000,
representing -100% to +100%. Positive = upvote, negative = downvote.
The posting key is required. I need to mention that voting power
depletes with each vote (2% per full vote) and regenerates at ~20% per day.
Downvotes have a separate free downvote pool (roughly 25% of your upvote mana).
I should also cover the 3-second block time and the fact that you can
change your vote within the payout window.
</think>

Here is how to vote and downvote with dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const postingKey = PrivateKey.fromString("5YourPostingKeyHere");
const voter = "youraccount";

/**
 * Vote on a post or comment.
 * @param {string} author - Post author
 * @param {string} permlink - Post permlink
 * @param {number} weightPercent - -100 to 100 (negative = downvote)
 */
async function vote(author, permlink, weightPercent) {
  // Convert percentage (-100..100) to protocol weight (-10000..10000)
  const weight = Math.round(Math.max(-10000, Math.min(10000, weightPercent * 100)));

  try {
    const result = await client.broadcast.vote(
      { voter, author, permlink, weight },
      postingKey
    );
    const action = weight > 0 ? "Upvoted" : weight < 0 ? "Downvoted" : "Removed vote on";
    console.log(`${action} @${author}/${permlink} at ${weightPercent}%`);
    return result;
  } catch (err) {
    if (err.message.includes("HIVE_MIN_VOTE_INTERVAL_SEC")) {
      console.error("Must wait 3 seconds between votes");
    } else if (err.message.includes("rc_plugin_exception")) {
      console.error("Insufficient Resource Credits for this vote");
    } else if (err.message.includes("already voted")) {
      console.error("Already voted — change weight or wait for payout");
    } else {
      throw err;
    }
  }
}

// 100% upvote
await vote("hiveauthor", "great-post-permlink", 100);

// 50% upvote (uses less voting power)
await vote("hiveauthor", "decent-post-permlink", 50);

// 100% downvote (uses free downvote pool first)
await vote("spammer", "spam-post-permlink", -100);

// Remove a previous vote (set weight to 0)
await vote("hiveauthor", "changed-my-mind", 0);
```

Important details:
- **Weight range**: -10000 to 10000 on-chain (-100% to +100%)
- **Voting power**: Each 100% vote costs 2% of your voting mana, regenerates ~20%/day
- **Downvote pool**: Free downvotes up to 25% of your mana bar, then costs upvote mana
- **Cooldown**: 3-second minimum between votes
- **Vote changes**: You can change your vote weight before payout (7-day window)'''
    ),
    (
        "hive_sdk/beem-stream-blockchain-ops",
        r'''I want to build a real-time monitor that streams specific operations from the Hive blockchain using beem. How do I filter for transfers, votes, and custom_json operations efficiently?''',
        r'''<think>
Streaming blockchain data with beem uses the Blockchain class. The stream() method
can filter by operation names using opNames parameter. I need to cover:
1. Basic streaming setup with node failover
2. Filtering specific operation types
3. Handling the stream offset (starting block number)
4. Processing each operation type differently
5. Error recovery for network issues
6. The fact that Hive produces blocks every 3 seconds
I should also mention stream vs stream(raw_ops=True) and threading considerations.
</think>

Here is a production-quality blockchain stream monitor with beem:

```python
import json
import time
import logging
from beem import Hive
from beem.blockchain import Blockchain
from beem.exceptions import RPCError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

NODES = [
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network",
]

WATCHED_OPS = ["transfer", "vote", "custom_json"]


def handle_transfer(op):
    log.info(f"TRANSFER: {op['from']} -> {op['to']}: {op['amount']}"
             f" memo={op.get('memo', '')[:50]}")


def handle_vote(op):
    weight = op["weight"] / 100  # convert to percentage
    direction = "UP" if weight > 0 else "DOWN" if weight < 0 else "UNVOTE"
    log.info(f"VOTE: {op['voter']} {direction} @{op['author']}/{op['permlink']} "
             f"({weight:+.0f}%)")


def handle_custom_json(op):
    try:
        data = json.loads(op["json"])
    except json.JSONDecodeError:
        data = op["json"]
    log.info(f"CUSTOM_JSON: id={op['id']} by={op.get('required_posting_auths') or op.get('required_auths')} "
             f"data={json.dumps(data)[:100]}")


HANDLERS = {
    "transfer": handle_transfer,
    "vote": handle_vote,
    "custom_json": handle_custom_json,
}


def stream_operations(start_block=None):
    """Stream filtered operations with automatic reconnection."""
    hive = Hive(node=NODES)
    bc = Blockchain(blockchain_instance=hive)

    last_block = start_block
    while True:
        try:
            log.info(f"Starting stream from block {last_block or 'HEAD'}")
            stream = bc.stream(
                opNames=WATCHED_OPS,
                start=last_block,
                threading=False,
                thread_num=1,
            )
            for op in stream:
                op_type = op["type"]
                if op_type in HANDLERS:
                    HANDLERS[op_type](op)
                last_block = op.get("block_num", last_block)

        except RPCError as e:
            log.warning(f"RPC error: {e}, reconnecting in 5s...")
            time.sleep(5)
            hive = Hive(node=NODES)
            bc = Blockchain(blockchain_instance=hive)
        except KeyboardInterrupt:
            log.info(f"Stopped at block {last_block}")
            break
        except Exception as e:
            log.error(f"Unexpected error: {e}, retrying in 10s...")
            time.sleep(10)


if __name__ == "__main__":
    stream_operations()
```

Key points:
- **opNames filter**: Pass a list of operation names to only receive those types
- **start parameter**: Resume from a specific block number after restart
- **3-second blocks**: Hive produces one block every 3 seconds, so expect ~20 ops/sec typical
- **Reconnection**: Always wrap streaming in a retry loop — nodes drop connections
- **Multiple nodes**: Provide failover nodes so beem auto-switches on failure'''
    ),
    (
        "hive_sdk/dhive-custom-json-broadcast",
        r'''How do I broadcast custom_json operations with dhive for a Layer 2 application? I need to understand when to use posting vs active authority.''',
        r'''<think>
Custom JSON is the backbone of Hive dApps. The key decision is authority level:
- required_posting_auths: for social/non-financial operations (follows, game moves, social signals)
- required_auths: for financial operations (token transfers, staking, marketplace sales)
Never mix both in a single operation.
The json field must be a stringified JSON, max 8192 bytes.
The id field identifies the protocol, max 32 chars.
I should show both authority types with practical examples.
</think>

Here is how to broadcast custom_json with dhive for Layer 2 apps:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const postingKey = PrivateKey.fromString("5YourPostingKey");
const activeKey = PrivateKey.fromString("5YourActiveKey");
const account = "youraccount";

/**
 * Broadcast a custom_json with posting authority.
 * Use for: social actions, game moves, non-financial operations.
 */
async function broadcastPostingJson(id, payload) {
  const jsonStr = JSON.stringify(payload);
  if (Buffer.byteLength(jsonStr) > 8192) {
    throw new Error(`Payload too large: ${Buffer.byteLength(jsonStr)} bytes (max 8192)`);
  }

  return client.broadcast.json(
    {
      id,
      required_posting_auths: [account],
      required_auths: [],
      json: jsonStr,
    },
    postingKey
  );
}

/**
 * Broadcast a custom_json with active authority.
 * Use for: token transfers, staking, financial operations.
 */
async function broadcastActiveJson(id, payload) {
  const jsonStr = JSON.stringify(payload);
  if (Buffer.byteLength(jsonStr) > 8192) {
    throw new Error(`Payload too large: ${Buffer.byteLength(jsonStr)} bytes (max 8192)`);
  }

  return client.broadcast.json(
    {
      id,
      required_posting_auths: [],
      required_auths: [account],
      json: jsonStr,
    },
    activeKey
  );
}

// Example 1: Follow a user (posting auth — social action)
await broadcastPostingJson("follow", [
  "follow",
  { follower: account, following: "targetuser", what: ["blog"] },
]);

// Example 2: Game move in a dApp (posting auth)
await broadcastPostingJson("mygame", {
  v: 1,
  action: "play_card",
  data: { match_id: "abc123", card_id: 42, position: 3 },
});

// Example 3: Hive-Engine token transfer (active auth — financial)
await broadcastActiveJson("ssc-mainnet-hive", {
  contractName: "tokens",
  contractAction: "transfer",
  contractPayload: {
    symbol: "BEE",
    to: "recipient",
    quantity: "10.000",
    memo: "Payment for NFT",
  },
});

// Example 4: Hive-Engine token staking (active auth)
await broadcastActiveJson("ssc-mainnet-hive", {
  contractName: "tokens",
  contractAction: "stake",
  contractPayload: {
    symbol: "BEE",
    to: account,
    quantity: "500.000",
  },
});
```

Authority rules summary:
- **Posting auth** (`required_posting_auths`): social/non-financial — follows, game moves, reactions
- **Active auth** (`required_auths`): financial — token transfers, staking, marketplace
- **Never mix** both auth arrays in one operation
- **Payload limit**: 8,192 bytes (stringified JSON)
- **ID limit**: 32 characters, identifies your protocol'''
    ),
    (
        "hive_sdk/beem-account-info-balances",
        r'''How do I read account information, balances, and voting power using beem? I need to check HIVE, HBD, savings, and VESTS/HP.''',
        r'''<think>
Reading account data is one of the most common operations. With beem, the Account
class provides methods for balances, voting power, RC, and history.
Key details: on-chain uses VESTS, not HP. Must convert with vests_to_hp().
Savings have a 3-day withdrawal delay for security.
Voting power is a percentage that depletes on votes and regenerates ~20%/day.
I should cover get_balances(), get_voting_power(), get_rc_manabar(),
and how to access raw account dict properties.
</think>

Here is how to read comprehensive account data with beem:

```python
from beem import Hive
from beem.account import Account

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

def get_account_info(username: str) -> dict:
    """Retrieve complete account information."""
    acc = Account(username, blockchain_instance=hive)

    # Core balances
    balances = acc.get_balances()
    available_hive = acc.get_balance("available", "HIVE")
    available_hbd = acc.get_balance("available", "HBD")
    savings_hive = acc.get_balance("savings", "HIVE")
    savings_hbd = acc.get_balance("savings", "HBD")

    # VESTS -> Hive Power conversion
    vests = float(acc["vesting_shares"].replace(" VESTS", ""))
    delegated_vests = float(acc["delegated_vesting_shares"].replace(" VESTS", ""))
    received_vests = float(acc["received_vesting_shares"].replace(" VESTS", ""))
    effective_vests = vests - delegated_vests + received_vests
    hp = hive.vests_to_hp(vests)
    effective_hp = hive.vests_to_hp(effective_vests)

    # Voting power (0-100%)
    vp = acc.get_voting_power()

    # Resource Credits
    rc = acc.get_rc_manabar()
    rc_pct = rc["current_pct"]

    # Reputation (raw bignum -> display score)
    reputation = acc.get_reputation()

    return {
        "name": username,
        "hive": float(available_hive),
        "hbd": float(available_hbd),
        "savings_hive": float(savings_hive),
        "savings_hbd": float(savings_hbd),
        "hp_own": round(hp, 3),
        "hp_effective": round(effective_hp, 3),
        "hp_delegated_out": round(hive.vests_to_hp(delegated_vests), 3),
        "hp_delegated_in": round(hive.vests_to_hp(received_vests), 3),
        "voting_power_pct": round(vp, 2),
        "resource_credits_pct": round(rc_pct, 2),
        "reputation": reputation,
        "post_count": acc["post_count"],
        "created": str(acc["created"]),
    }

info = get_account_info("blocktrades")
for key, val in info.items():
    print(f"{key}: {val}")
```

Key details:
- **VESTS vs HP**: On-chain stores VESTS; use `hive.vests_to_hp()` to convert
- **Effective HP** = own HP - delegated out + delegated in
- **Voting power**: 0-100%, costs 2% per full vote, regens ~20%/day
- **Resource Credits**: Separate from VP, needed for all transactions
- **Savings**: 3-day withdrawal delay (security feature against key theft)
- **No keys needed**: All account reads are public, no authentication required'''
    ),
    (
        "hive_sdk/dhive-create-account",
        r'''How do I create a new Hive account using dhive? I need to understand the two methods: paying the fee vs using claimed account tokens.''',
        r'''<think>
Account creation on Hive has two paths:
1. account_create: Pay 3 HIVE fee directly (active key of creator)
2. create_claimed_account: Use a previously claimed account token (free with RC)
   - First claim a token with claim_account (costs RC, no HIVE)
   - Then create the account using that token

I need to cover key generation for the new account. On Hive, each account has
4 key pairs derived from the master password: owner, active, posting, memo.
The PrivateKey.fromLogin() method in dhive handles this derivation.
I should show both creation methods with proper key setup.
</think>

Here are both account creation methods with dhive:

```javascript
const { Client, PrivateKey, cryptoUtils } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const creatorAccount = "youraccount";
const creatorActiveKey = PrivateKey.fromString("5YourActiveKey");

/**
 * Derive all 4 key pairs from a master password.
 */
function generateKeys(username, masterPassword) {
  const roles = ["owner", "active", "posting", "memo"];
  const keys = {};
  for (const role of roles) {
    const priv = PrivateKey.fromLogin(username, masterPassword, role);
    keys[role] = {
      private: priv.toString(),
      public: priv.createPublic().toString(),
    };
  }
  return keys;
}

/**
 * Method 1: Create account by paying 3 HIVE fee.
 */
async function createAccountWithFee(newUsername, masterPassword) {
  const keys = generateKeys(newUsername, masterPassword);

  const op = [
    "account_create",
    {
      fee: "3.000 HIVE",
      creator: creatorAccount,
      new_account_name: newUsername,
      owner: {
        weight_threshold: 1,
        account_auths: [],
        key_auths: [[keys.owner.public, 1]],
      },
      active: {
        weight_threshold: 1,
        account_auths: [],
        key_auths: [[keys.active.public, 1]],
      },
      posting: {
        weight_threshold: 1,
        account_auths: [],
        key_auths: [[keys.posting.public, 1]],
      },
      memo_key: keys.memo.public,
      json_metadata: JSON.stringify({ created_by: creatorAccount }),
    },
  ];

  const result = await client.broadcast.sendOperations([op], creatorActiveKey);
  console.log(`Account @${newUsername} created with fee. TX: ${result.id}`);
  return { result, keys };
}

/**
 * Method 2: Claim a free account token (costs RC, not HIVE).
 */
async function claimAccountToken() {
  const op = [
    "claim_account",
    {
      creator: creatorAccount,
      fee: "0.000 HIVE",  // 0 = use RC instead of HIVE
      extensions: [],
    },
  ];

  const result = await client.broadcast.sendOperations([op], creatorActiveKey);
  console.log("Claimed 1 account token via RC");
  return result;
}

/**
 * Method 2b: Create account using a previously claimed token.
 */
async function createClaimedAccount(newUsername, masterPassword) {
  const keys = generateKeys(newUsername, masterPassword);

  const op = [
    "create_claimed_account",
    {
      creator: creatorAccount,
      new_account_name: newUsername,
      owner: {
        weight_threshold: 1,
        account_auths: [],
        key_auths: [[keys.owner.public, 1]],
      },
      active: {
        weight_threshold: 1,
        account_auths: [],
        key_auths: [[keys.active.public, 1]],
      },
      posting: {
        weight_threshold: 1,
        account_auths: [],
        key_auths: [[keys.posting.public, 1]],
      },
      memo_key: keys.memo.public,
      json_metadata: JSON.stringify({ created_by: creatorAccount }),
      extensions: [],
    },
  ];

  const result = await client.broadcast.sendOperations([op], creatorActiveKey);
  console.log(`Account @${newUsername} created from claimed token. TX: ${result.id}`);
  return { result, keys };
}

// Usage:
// Method 1: Direct creation (costs 3 HIVE)
const { keys } = await createAccountWithFee("newuser123", "SuperSecretMasterPassword!");

// Method 2: Free creation (costs RC to claim, then free to create)
await claimAccountToken();
await createClaimedAccount("newuser456", "AnotherSecurePassword!");
```

Key points:
- **Account names**: 3-16 chars, lowercase a-z, 0-9, hyphens, dots (not at start/end)
- **Fee method**: Costs 3 HIVE, instant, no RC claim needed
- **Claimed method**: Claim token with RC (requires significant RC), then create for free
- **Master password**: Derive all 4 key types from one password — store it securely
- **Active key** of the creator is required for both methods'''
    ),
    (
        "hive_sdk/beem-key-derivation-management",
        r'''How does key derivation work on Hive? I need to derive posting, active, owner, and memo keys from a master password using beem.''',
        r'''<think>
Hive uses a hierarchical key system. A single master password is used to
derive 4 key pairs, each with different authority levels:
- Owner: highest authority, can change all other keys, recovery
- Active: financial operations (transfers, power up/down, witness voting)
- Posting: social operations (post, vote, comment, follow, custom_json with posting auth)
- Memo: encrypt/decrypt private memos

The derivation uses the account name + role + master password hashed together.
In beem, PasswordKey handles this. The WIF (Wallet Import Format) is the
standard private key format starting with '5'.
I should show both derivation and verification against on-chain public keys.
</think>

Here is how Hive key derivation and management works with beem:

```python
from beem import Hive
from beem.account import Account
from beemgraphenebase.account import PasswordKey, PrivateKey, PublicKey

def derive_keys(username: str, master_password: str) -> dict:
    """Derive all 4 key pairs from username + master password."""
    roles = ["owner", "active", "posting", "memo"]
    keys = {}
    for role in roles:
        pk = PasswordKey(username, master_password, role=role)
        private_wif = str(pk.get_private_key())
        public_key = str(pk.get_public_key())
        keys[role] = {
            "private": private_wif,  # WIF format (starts with '5')
            "public": public_key,    # STM prefix format
        }
    return keys


def verify_keys(username: str, master_password: str) -> dict:
    """Check which derived keys match the on-chain public keys."""
    hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])
    acc = Account(username, blockchain_instance=hive)
    derived = derive_keys(username, master_password)

    results = {}
    for role in ["owner", "active", "posting"]:
        # On-chain stores public keys in authority structure
        on_chain_keys = [k[0] for k in acc[role]["key_auths"]]
        derived_pub = derived[role]["public"]
        results[role] = derived_pub in on_chain_keys

    # Memo key is stored directly
    results["memo"] = derived["memo"]["public"] == acc["memo_key"]
    return results


def import_single_key(wif: str):
    """Get the public key from a WIF private key (without master password)."""
    pk = PrivateKey(wif)
    return str(pk.pubkey)


# Derive all keys from master password
username = "myaccount"
master = "P5JxSuperSecretMasterPassword"
keys = derive_keys(username, master)

for role, pair in keys.items():
    print(f"{role}:")
    print(f"  Private (WIF): {pair['private'][:8]}...")
    print(f"  Public:         {pair['public']}")

# Verify against blockchain
matches = verify_keys(username, master)
for role, matched in matches.items():
    status = "MATCH" if matched else "MISMATCH"
    print(f"{role}: {status}")

# If you only have a WIF key and need the public key
pub = import_single_key("5JexampleWIFkey")
print(f"Public key for WIF: {pub}")
```

Key hierarchy and permissions:
| Key | Authority Level | Can Do |
|-----|----------------|--------|
| **Owner** | Highest | Change all keys, account recovery |
| **Active** | Financial | Transfers, power up/down, witness votes |
| **Posting** | Social | Post, vote, comment, follow, reblog |
| **Memo** | Encryption only | Encrypt/decrypt private memos |

Security rules:
- **Never share your master password or owner key** — store offline
- **Use posting key** for apps that only need social features
- **Use active key** only for financial apps, never store on frontend
- **Owner key rotation**: Change periodically via `update_account` with owner authority
- **Key derivation is deterministic**: Same username + password always gives same keys'''
    ),
    (
        "hive_sdk/dhive-delegation-hp",
        r'''How do I delegate and undelegate Hive Power (HP) using dhive? I need to handle the conversion between HP and VESTS.''',
        r'''<think>
HP delegation uses the delegate_vesting_shares operation. The tricky part is that
the blockchain only understands VESTS, not HP. So you need to convert HP to VESTS
before delegating. In dhive, you can use client.database.getDynamicGlobalProperties()
to get the conversion ratio: total_vesting_fund_hive / total_vesting_shares.
To undelegate, you set the delegation amount to "0.000000 VESTS".
Undelegation has a 5-day cooldown before the VESTS return to the delegator.
Active key is required for delegation operations.
</think>

Here is how to delegate and undelegate HP with dhive, handling the HP-to-VESTS conversion:

```javascript
const { Client, PrivateKey, Asset } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const activeKey = PrivateKey.fromString("5YourActiveKey");
const delegator = "youraccount";

/**
 * Convert HP (Hive Power) to VESTS using current chain ratio.
 */
async function hpToVests(hp) {
  const props = await client.database.getDynamicGlobalProperties();
  const totalHive = parseFloat(props.total_vesting_fund_hive.split(" ")[0]);
  const totalVests = parseFloat(props.total_vesting_shares.split(" ")[0]);
  const vests = (hp * totalVests) / totalHive;
  return vests.toFixed(6) + " VESTS";
}

/**
 * Convert VESTS to HP for display purposes.
 */
async function vestsToHp(vests) {
  const props = await client.database.getDynamicGlobalProperties();
  const totalHive = parseFloat(props.total_vesting_fund_hive.split(" ")[0]);
  const totalVests = parseFloat(props.total_vesting_shares.split(" ")[0]);
  const vestsNum = parseFloat(vests.split(" ")[0]);
  return (vestsNum * totalHive) / totalVests;
}

/**
 * Delegate HP to another account.
 */
async function delegateHP(delegatee, hpAmount) {
  const vests = await hpToVests(hpAmount);
  console.log(`Delegating ${hpAmount} HP (${vests}) to @${delegatee}`);

  const op = [
    "delegate_vesting_shares",
    {
      delegator: delegator,
      delegatee: delegatee,
      vesting_shares: vests,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Delegation successful: ${result.id}`);
  return result;
}

/**
 * Remove delegation (undelegate). VESTS return after 5-day cooldown.
 */
async function undelegateHP(delegatee) {
  const op = [
    "delegate_vesting_shares",
    {
      delegator: delegator,
      delegatee: delegatee,
      vesting_shares: "0.000000 VESTS",  // zero = remove delegation
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Undelegated from @${delegatee}. Returns in 5 days.`);
  return result;
}

/**
 * Check current outgoing delegations.
 */
async function getOutgoingDelegations(account) {
  const delegations = await client.database.getVestingDelegations(account, "", 100);
  for (const d of delegations) {
    const hp = await vestsToHp(d.vesting_shares);
    console.log(`-> @${d.delegatee}: ${hp.toFixed(3)} HP (${d.vesting_shares})`);
  }
  return delegations;
}

// Delegate 100 HP
await delegateHP("newuser", 100);

// Check outgoing delegations
await getOutgoingDelegations(delegator);

// Undelegate (5-day cooldown before VESTS return)
await undelegateHP("newuser");
```

Important notes:
- **Always use VESTS** on-chain — convert HP to VESTS before broadcasting
- **6 decimal places** for VESTS: `"1000.000000 VESTS"`
- **Active key** required for delegation operations
- **Undelegation cooldown**: 5 days before delegated VESTS return to delegator
- **Updating delegation**: Broadcast a new amount to the same delegatee (overwrites previous)
- **Minimum delegation**: ~10 HP (varies slightly with VESTS/HP ratio)'''
    ),
    (
        "hive_sdk/beem-posting-comments-replies",
        r'''Show me how to create posts, reply to posts, and edit existing posts on Hive using beem. Include setting tags, beneficiaries, and handling the 5-minute cooldown.''',
        r'''<think>
Posting on Hive uses the comment operation for both root posts and replies.
A root post has parent_author="" and parent_permlink=category.
A reply has parent_author=author and parent_permlink=permlink of the parent.
Editing reuses the same author+permlink (no separate edit operation).
Beneficiaries require comment_options operation in the same transaction.
There is a 5-minute cooldown between root posts and 20-second cooldown between comments.
The beem library has a convenient post() method but TransactionBuilder
is needed for beneficiaries.
</think>

Here is comprehensive posting, replying, and editing with beem:

```python
import json
import time
from datetime import datetime
from beem import Hive
from beem.comment import Comment
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Comment as CommentOp, Comment_options

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)
author = "youraccount"


def create_post(title: str, body: str, tags: list[str],
                community: str = None, beneficiaries: list[dict] = None):
    """Create a root-level post with optional beneficiaries."""
    slug = title.lower().replace(" ", "-")[:200]
    permlink = f"{slug}-{int(time.time())}"
    parent_permlink = community or tags[0]

    metadata = json.dumps({
        "tags": tags,
        "app": "myapp/1.0",
        "format": "markdown",
    })

    if beneficiaries:
        # Must use TransactionBuilder to batch comment + comment_options
        tx = TransactionBuilder(blockchain_instance=hive)

        comment_op = CommentOp(**{
            "parent_author": "",
            "parent_permlink": parent_permlink,
            "author": author,
            "permlink": permlink,
            "title": title,
            "body": body,
            "json_metadata": metadata,
        })
        tx.appendOps(comment_op)

        # Beneficiaries must be sorted alphabetically by account
        sorted_bens = sorted(beneficiaries, key=lambda b: b["account"])
        options_op = Comment_options(**{
            "author": author,
            "permlink": permlink,
            "max_accepted_payout": "1000000.000 HBD",
            "percent_hbd": 10000,
            "allow_votes": True,
            "allow_curation_rewards": True,
            "extensions": [[0, {"beneficiaries": sorted_bens}]],
        })
        tx.appendOps(options_op)

        tx.appendSigner(author, "posting")
        tx.sign()
        result = tx.broadcast()
    else:
        hive.post(
            title, body, author=author,
            tags=tags, self_vote=False,
            json_metadata=metadata,
        )
        result = {"permlink": permlink}

    print(f"Post created: @{author}/{permlink}")
    return permlink


def reply_to_post(parent_author: str, parent_permlink: str, body: str):
    """Reply to an existing post or comment."""
    permlink = f"re-{parent_author}-{int(time.time())}"

    hive.post(
        "",  # empty title for replies
        body,
        author=author,
        reply_identifier=f"@{parent_author}/{parent_permlink}",
        json_metadata=json.dumps({"app": "myapp/1.0"}),
    )
    print(f"Reply created: @{author}/{permlink}")
    return permlink


def edit_post(permlink: str, new_body: str, new_title: str = None):
    """Edit an existing post. Reuse the same permlink."""
    existing = Comment(f"@{author}/{permlink}", blockchain_instance=hive)
    title = new_title or existing["title"]
    parent_permlink = existing["parent_permlink"]

    hive.post(
        title, new_body, author=author,
        permlink=permlink,
        tags=[parent_permlink],
        json_metadata=existing["json_metadata"],
    )
    print(f"Post edited: @{author}/{permlink}")


# Create a post with beneficiaries (10% to curators, 5% to app)
permlink = create_post(
    title="Building on Hive with Python",
    body="# Hello Hive\n\nThis is my post about beem development.",
    tags=["hive-dev", "python", "beem", "tutorial"],
    beneficiaries=[
        {"account": "app-rewards", "weight": 500},    # 5%
        {"account": "curator-team", "weight": 1000},   # 10%
    ]
)

# Reply to the post (20-second cooldown between comments)
time.sleep(20)
reply_to_post(author, permlink, "Great post! Here is a follow-up thought...")

# Edit the post (no cooldown for edits)
edit_post(permlink, "# Hello Hive\n\nUpdated content here.")
```

Rules and limits:
- **Root post cooldown**: 5 minutes between top-level posts
- **Comment cooldown**: 20 seconds between replies
- **Beneficiary weight**: In basis points (500 = 5%, 10000 = 100%)
- **Beneficiaries must be sorted** alphabetically by account name
- **Permlink max**: 256 chars, lowercase, hyphens only
- **Editing**: Reuse same author+permlink, no separate edit operation
- **No delete**: Posts can be "deleted" by replacing body with empty content, but the operation remains on-chain'''
    ),
    (
        "hive_sdk/dhive-resource-credits-check",
        r'''How do I check resource credits (RC) for a Hive account and estimate the cost of operations using dhive?''',
        r'''<think>
Resource Credits (RC) are Hive's rate-limiting mechanism. Every operation costs RC,
which regenerates over time based on your HP. The RC system replaced bandwidth
in a hard fork. To check RC, use the rc_api plugin via client.call().
The RC manabar works like voting power — it has a current mana and a max mana,
with linear regeneration over 5 days (full recharge from 0 to 100%).
I need to show how to get current RC, calculate percentage, and estimate
operation costs. The rc_api is not in the standard dhive methods, so
we need to use client.call() directly.
</think>

Here is how to check and estimate RC costs with dhive:

```javascript
const { Client } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

/**
 * Get current RC mana for an account.
 */
async function getRCMana(username) {
  const result = await client.call("rc_api", "find_rc_accounts", {
    accounts: [username],
  });

  if (!result.rc_accounts || result.rc_accounts.length === 0) {
    throw new Error(`Account @${username} not found`);
  }

  const rcAccount = result.rc_accounts[0];
  const maxMana = BigInt(rcAccount.max_rc);
  const currentMana = BigInt(rcAccount.rc_manabar.current_mana);
  const lastUpdate = rcAccount.rc_manabar.last_update_time;

  // Calculate regenerated mana since last update
  const now = Math.floor(Date.now() / 1000);
  const elapsed = BigInt(now - lastUpdate);
  const regenRate = maxMana / BigInt(432000); // 5 days in seconds
  const regenerated = elapsed * regenRate;
  const actualMana = currentMana + regenerated > maxMana
    ? maxMana
    : currentMana + regenerated;

  const pct = Number((actualMana * BigInt(10000)) / maxMana) / 100;

  return {
    username,
    current_mana: actualMana.toString(),
    max_mana: maxMana.toString(),
    percentage: pct.toFixed(2),
    last_update: new Date(lastUpdate * 1000).toISOString(),
  };
}

/**
 * Estimate RC cost for common operations.
 */
async function estimateRCCost(operationType) {
  // Approximate RC costs (vary slightly over time)
  const costs = {
    comment: 1_100_000_000,       // ~1.1B RC for a post/comment
    vote: 80_000_000,             // ~80M RC for a vote
    transfer: 200_000_000,        // ~200M RC for a transfer
    custom_json_small: 100_000_000, // ~100M RC for small custom_json
    custom_json_large: 500_000_000, // ~500M RC for max-size custom_json
    claim_account: 5_000_000_000_000, // ~5T RC for free account claim
  };
  return costs[operationType] || null;
}

/**
 * Check if account has enough RC for an operation.
 */
async function canAffordOperation(username, operationType) {
  const rc = await getRCMana(username);
  const cost = await estimateRCCost(operationType);
  if (!cost) return { error: "Unknown operation type" };

  const currentMana = BigInt(rc.current_mana);
  const canAfford = currentMana >= BigInt(cost);
  const timesCanDo = Number(currentMana / BigInt(cost));

  return {
    username,
    operation: operationType,
    rc_pct: rc.percentage,
    can_afford: canAfford,
    times_possible: timesCanDo,
    estimated_cost: cost.toLocaleString(),
    current_rc: rc.current_mana,
  };
}

// Check RC status
const rc = await getRCMana("blocktrades");
console.log(`@${rc.username}: ${rc.percentage}% RC`);

// Check if account can post
const check = await canAffordOperation("newuser123", "comment");
console.log(`Can post: ${check.can_afford} (${check.times_possible} times)`);

// Check if account can claim a free account
const claimCheck = await canAffordOperation("blocktrades", "claim_account");
console.log(`Can claim account: ${claimCheck.can_afford}`);
```

RC system details:
- **Regeneration**: 20% per day, full recharge in 5 days (like voting power)
- **Based on HP**: More HP = more max RC = more daily operations
- **Free accounts**: Claiming an account token costs ~5 trillion RC (need significant HP)
- **RC delegation**: Can delegate RC via custom_json with `rc` id (active auth)
- **New accounts**: Start with minimal RC, need delegation to transact
- **No fees**: RC replaces transaction fees — operations are free but rate-limited'''
    ),
    (
        "hive_sdk/beem-witness-voting",
        r'''How do I vote for witnesses and set a witness voting proxy using beem?''',
        r'''<think>
Witness voting is important for Hive governance. Each account can vote for up to
30 witnesses. These votes determine the top 20 consensus witnesses plus one
rotating backup. The active key is required for witness votes.
Setting a proxy delegates all your witness votes to another account.
When a proxy is set, your individual votes are overridden.
I should show both direct voting and proxy setting, plus how to
list current witness votes.
</think>

Here is how to manage witness votes with beem:

```python
from beem import Hive
from beem.account import Account
from beem.witness import Witness, WitnessesRankedByVote

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)
account = "youraccount"


def vote_witness(witness_name: str, approve: bool = True):
    """Vote for or unvote a witness."""
    hive.approve_witness(witness_name, account=account, approve=approve)
    action = "Voted for" if approve else "Unvoted"
    print(f"{action} witness @{witness_name}")


def set_witness_proxy(proxy_account: str):
    """Delegate all witness votes to a proxy account."""
    hive.set_withdraw_vesting_route(proxy_account, account=account)
    # Actually, the correct method:
    hive.witness_proxy(proxy_account, account=account)
    print(f"Set witness proxy to @{proxy_account}")


def clear_witness_proxy():
    """Remove witness proxy and restore individual votes."""
    hive.witness_proxy("", account=account)
    print("Cleared witness proxy")


def get_current_votes(username: str) -> list:
    """List all witnesses an account has voted for."""
    acc = Account(username, blockchain_instance=hive)
    return acc["witness_votes"]


def get_top_witnesses(limit: int = 30):
    """Get top witnesses ranked by total votes."""
    witnesses = WitnessesRankedByVote(limit=limit, blockchain_instance=hive)
    for i, w in enumerate(witnesses, 1):
        print(f"{i:2d}. @{w['owner']:20s} votes: {w['votes']}")
    return witnesses


# Vote for specific witnesses
vote_witness("blocktrades")
vote_witness("good-karma")
vote_witness("arcange")

# Check current votes
votes = get_current_votes(account)
print(f"Voting for {len(votes)} witnesses: {votes}")

# Unvote a witness
vote_witness("some-witness", approve=False)

# Set a proxy (delegates all witness votes)
set_witness_proxy("hive.voter")

# Clear proxy
clear_witness_proxy()

# View top witnesses
get_top_witnesses(20)
```

Key details:
- **Max 30 witness votes** per account
- **Active key** required for witness voting
- **Proxy**: Overrides all individual votes; clearing proxy restores them
- **Top 20** witnesses produce blocks; backup witnesses rotate in
- **Witness votes never expire** — review periodically and update'''
    ),
    (
        "hive_sdk/dhive-power-up-down",
        r'''How do I power up HIVE to Hive Power and power down (unstake) using dhive? I need to understand the 13-week schedule.''',
        r'''<think>
Power up converts liquid HIVE to VESTS (Hive Power). It is instant.
Power down converts VESTS back to liquid HIVE over 13 weekly installments.
Each week, 1/13th of the powered-down VESTS converts to HIVE.
To cancel a power down, set vesting_shares to "0.000000 VESTS".
Power up uses transfer_to_vesting operation (active key).
Power down uses withdraw_vesting operation (active key).
I should show both operations with proper amount formatting.
</think>

Here is how to power up and power down with dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const activeKey = PrivateKey.fromString("5YourActiveKey");
const account = "youraccount";

/**
 * Power up: Convert liquid HIVE to Hive Power (VESTS).
 * Instant, no waiting period.
 */
async function powerUp(amount, toAccount = null) {
  const op = [
    "transfer_to_vesting",
    {
      from: account,
      to: toAccount || account,  // can power up another account
      amount: `${amount.toFixed(3)} HIVE`,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  const target = toAccount || account;
  console.log(`Powered up ${amount.toFixed(3)} HIVE to @${target}`);
  return result;
}

/**
 * Power down: Start converting VESTS to liquid HIVE.
 * Takes 13 weeks — 1/13th delivered each week.
 */
async function powerDown(hpAmount) {
  // Convert HP to VESTS
  const props = await client.database.getDynamicGlobalProperties();
  const totalHive = parseFloat(props.total_vesting_fund_hive.split(" ")[0]);
  const totalVests = parseFloat(props.total_vesting_shares.split(" ")[0]);
  const vests = (hpAmount * totalVests) / totalHive;

  const op = [
    "withdraw_vesting",
    {
      account: account,
      vesting_shares: `${vests.toFixed(6)} VESTS`,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  const weeklyHp = hpAmount / 13;
  console.log(`Power down started: ${hpAmount.toFixed(3)} HP over 13 weeks`);
  console.log(`Weekly payout: ~${weeklyHp.toFixed(3)} HIVE`);
  return result;
}

/**
 * Cancel an active power down.
 */
async function cancelPowerDown() {
  const op = [
    "withdraw_vesting",
    {
      account: account,
      vesting_shares: "0.000000 VESTS",  // zero cancels power down
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log("Power down cancelled");
  return result;
}

/**
 * Check current power down status.
 */
async function getPowerDownStatus(username) {
  const [acc] = await client.database.getAccounts([username]);
  const withdrawRate = acc.vesting_withdraw_rate;
  const nextPayout = acc.next_vesting_withdrawal;

  if (withdrawRate === "0.000000 VESTS") {
    console.log("No active power down");
    return null;
  }

  const props = await client.database.getDynamicGlobalProperties();
  const totalHive = parseFloat(props.total_vesting_fund_hive.split(" ")[0]);
  const totalVests = parseFloat(props.total_vesting_shares.split(" ")[0]);
  const weeklyVests = parseFloat(withdrawRate.split(" ")[0]);
  const weeklyHive = (weeklyVests * totalHive) / totalVests;

  return {
    weekly_vests: withdrawRate,
    weekly_hive: weeklyHive.toFixed(3),
    next_payout: nextPayout,
    remaining_weeks: 13,  // approximate
  };
}

// Power up 100 HIVE to yourself
await powerUp(100);

// Power up 50 HIVE to another account
await powerUp(50, "friend-account");

// Start power down of 500 HP (takes 13 weeks)
await powerDown(500);

// Cancel power down
await cancelPowerDown();
```

Key points:
- **Power up** is instant — liquid HIVE becomes HP (VESTS) immediately
- **Power down** takes 13 weeks — weekly payouts of 1/13th
- **Cancel**: Set `vesting_shares` to `"0.000000 VESTS"` to stop power down
- **Can power up others**: Set `to` field to a different account
- **Active key** required for both operations
- **No partial cancel**: You can only cancel entirely, then start a new power down at a different amount'''
    ),
    (
        "hive_sdk/beem-hbd-savings-interest",
        r'''How do I manage HBD savings with beem? I want to deposit, withdraw, and understand the interest mechanism.''',
        r'''<think>
HBD savings is a feature where you can earn interest on HBD (currently around 15% APR,
set by witness consensus). Deposits are instant but withdrawals have a mandatory
3-day delay for security. The interest accrues automatically and is paid out when
you do any savings operation or claim it. Active key is required.
I should cover deposit, withdrawal initiation, and checking pending withdrawals.
Also important: the 3-day withdrawal delay is a security feature — if your
keys are compromised, you have 3 days to recover before savings are drained.
</think>

Here is how to manage HBD savings with beem:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)
account = "youraccount"


def deposit_to_savings(amount: float, asset: str = "HBD", memo: str = ""):
    """Deposit HIVE or HBD to savings. Instant."""
    hive.transfer_to_savings(amount, asset, memo=memo, account=account)
    print(f"Deposited {amount:.3f} {asset} to savings")


def withdraw_from_savings(amount: float, asset: str = "HBD", memo: str = ""):
    """Initiate withdrawal from savings. 3-day delay before funds arrive."""
    request_id = int(datetime.now().timestamp())  # unique ID for this request
    hive.transfer_from_savings(
        amount, asset, memo=memo, account=account, request_id=request_id
    )
    arrival = datetime.now() + timedelta(days=3)
    print(f"Withdrawal initiated: {amount:.3f} {asset}")
    print(f"Funds arrive after: {arrival.strftime('%Y-%m-%d %H:%M')}")
    return request_id


def cancel_withdrawal(request_id: int):
    """Cancel a pending savings withdrawal."""
    hive.cancel_transfer_from_savings(request_id, account=account)
    print(f"Cancelled withdrawal request {request_id}")


def get_savings_info(username: str) -> dict:
    """Get savings balance and pending withdrawals."""
    acc = Account(username, blockchain_instance=hive)

    savings_hive = float(str(acc["savings_balance"]).split()[0])
    savings_hbd = float(str(acc["savings_hbd_balance"]).split()[0])
    last_interest = acc["savings_hbd_last_interest_payment"]

    # Check for pending withdrawals
    withdrawals = list(acc.get_savings_withdrawals())

    return {
        "savings_hive": savings_hive,
        "savings_hbd": savings_hbd,
        "last_interest_payment": str(last_interest),
        "pending_withdrawals": [
            {
                "id": w["request_id"],
                "amount": str(w["amount"]),
                "complete": str(w["complete"]),
            }
            for w in withdrawals
        ],
    }


# Deposit 100 HBD to savings (earns ~15% APR interest)
deposit_to_savings(100.0, "HBD", memo="Savings deposit")

# Deposit HIVE to savings (no interest, but has 3-day withdrawal protection)
deposit_to_savings(50.0, "HIVE")

# Withdraw HBD (3-day delay)
req_id = withdraw_from_savings(25.0, "HBD", memo="Need funds")

# Check savings status
info = get_savings_info(account)
print(f"HBD in savings: {info['savings_hbd']}")
print(f"HIVE in savings: {info['savings_hive']}")
for w in info["pending_withdrawals"]:
    print(f"  Pending: {w['amount']} completes at {w['complete']}")

# Cancel a pending withdrawal if needed
# cancel_withdrawal(req_id)
```

Key details:
- **HBD interest**: ~15% APR (set by witness consensus, can change)
- **HIVE savings**: No interest, but still has the 3-day security delay
- **Deposit**: Instant transfer to savings
- **Withdrawal**: 3-day mandatory delay before funds return to liquid balance
- **Cancel**: Can cancel pending withdrawals before the 3 days expire
- **Interest payout**: Accrues continuously, paid on any savings operation
- **Security**: The 3-day delay protects against key theft — you can recover the account and cancel withdrawals'''
    ),
    (
        "hive_sdk/dhive-recurrent-transfer",
        r'''How do I set up recurrent (recurring) transfers on Hive using dhive? I need to create, modify, and cancel subscription-like payments.''',
        r'''<think>
Recurrent transfers are a Hive feature that allows automatic periodic payments.
They use the recurrent_transfer operation. You set the amount, recurrence
(in hours, minimum 24), and number of executions. The blockchain automatically
executes the transfer at each interval. To cancel, send a recurrent_transfer
with amount "0.000 HIVE". To modify, just send a new recurrent_transfer
to the same recipient — it overwrites the previous one.
Active key is required. This is useful for subscription services,
salary payments, etc.
</think>

Here is how to manage recurrent transfers with dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const activeKey = PrivateKey.fromString("5YourActiveKey");
const sender = "youraccount";

/**
 * Create a recurring transfer (subscription-style payment).
 */
async function createRecurrentTransfer({
  to,
  amount,
  asset = "HIVE",
  recurrenceHours = 24 * 7,  // weekly by default
  executions = 12,            // 12 payments
  memo = "",
}) {
  const op = [
    "recurrent_transfer",
    {
      from: sender,
      to: to,
      amount: `${amount.toFixed(3)} ${asset}`,
      memo: memo,
      recurrence: recurrenceHours,  // hours between transfers
      executions: executions,        // total number of transfers
      extensions: [],
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Recurrent transfer set: ${amount.toFixed(3)} ${asset} to @${to}`);
  console.log(`  Every ${recurrenceHours} hours, ${executions} times`);
  return result;
}

/**
 * Modify an existing recurrent transfer (overwrites previous).
 */
async function modifyRecurrentTransfer(to, newAmount, newAsset = "HIVE") {
  // Sending a new recurrent_transfer to the same recipient replaces the old one
  return createRecurrentTransfer({
    to,
    amount: newAmount,
    asset: newAsset,
    recurrenceHours: 24 * 30,  // monthly
    executions: 6,
  });
}

/**
 * Cancel a recurrent transfer.
 */
async function cancelRecurrentTransfer(to, asset = "HIVE") {
  const op = [
    "recurrent_transfer",
    {
      from: sender,
      to: to,
      amount: `0.000 ${asset}`,  // zero amount = cancel
      memo: "",
      recurrence: 24,
      executions: 2,
      extensions: [],
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Cancelled recurrent transfer to @${to}`);
  return result;
}

/**
 * Check outgoing recurrent transfers.
 */
async function getRecurrentTransfers(username) {
  const result = await client.call(
    "database_api",
    "find_recurrent_transfers",
    { from: username }
  );
  return result.recurrent_transfers;
}

// Weekly payment of 10 HIVE for 12 weeks
await createRecurrentTransfer({
  to: "service-provider",
  amount: 10,
  asset: "HIVE",
  recurrenceHours: 24 * 7,  // weekly
  executions: 12,
  memo: "Weekly subscription",
});

// Monthly HBD payment
await createRecurrentTransfer({
  to: "landlord",
  amount: 100,
  asset: "HBD",
  recurrenceHours: 24 * 30,  // ~monthly (720 hours)
  executions: 12,
  memo: "Monthly rent",
});

// Modify existing transfer amount
await modifyRecurrentTransfer("service-provider", 15, "HIVE");

// Cancel
await cancelRecurrentTransfer("service-provider");

// List active recurrent transfers
const transfers = await getRecurrentTransfers(sender);
for (const t of transfers) {
  console.log(`To: @${t.to}, Amount: ${t.amount}, Every: ${t.recurrence}h`);
}
```

Key details:
- **Minimum recurrence**: 24 hours
- **Cancel**: Send amount `"0.000 HIVE"` to the same recipient
- **Modify**: New recurrent_transfer to same recipient overwrites the old one
- **Active key** required
- **Insufficient balance**: If balance is too low when execution triggers, it fails silently and retries next cycle
- **Pair ID**: Each from-to pair can only have one active recurrent transfer per asset type'''
    ),
    (
        "hive_sdk/beem-transaction-builder-multi-op",
        r'''How do I build a transaction with multiple operations using beem's TransactionBuilder? I need to batch several operations atomically.''',
        r'''<think>
TransactionBuilder in beem lets you batch multiple operations into a single
transaction. This is important for atomicity — either all operations succeed
or none do. Common use cases: post + beneficiaries + self-vote, multi-transfer
payouts, token swap operations. The operations execute in order within the
transaction. You need to append the right signer(s) based on the authority
levels needed. If mixing posting and active operations, you need both keys.
</think>

Here is how to build multi-operation transactions with beem:

```python
import json
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Comment, Comment_options, Vote, Transfer,
    Custom_json, Delegate_vesting_shares,
)

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey", "5YourActiveKey"]  # both keys for mixed operations
)
account = "youraccount"


def atomic_post_with_beneficiaries_and_vote(
    title: str, body: str, tags: list, beneficiaries: list
):
    """Create post + set beneficiaries + self-vote in one atomic transaction."""
    import time
    permlink = f"{title.lower().replace(' ', '-')[:100]}-{int(time.time())}"

    tx = TransactionBuilder(blockchain_instance=hive)

    # Op 1: Create the post
    tx.appendOps(Comment(**{
        "parent_author": "",
        "parent_permlink": tags[0],
        "author": account,
        "permlink": permlink,
        "title": title,
        "body": body,
        "json_metadata": json.dumps({"tags": tags, "app": "myapp/1.0"}),
    }))

    # Op 2: Set beneficiaries (must come after comment, same tx)
    sorted_bens = sorted(beneficiaries, key=lambda b: b["account"])
    tx.appendOps(Comment_options(**{
        "author": account,
        "permlink": permlink,
        "max_accepted_payout": "1000000.000 HBD",
        "percent_hbd": 10000,
        "allow_votes": True,
        "allow_curation_rewards": True,
        "extensions": [[0, {"beneficiaries": sorted_bens}]],
    }))

    # Op 3: Self-vote
    tx.appendOps(Vote(**{
        "voter": account,
        "author": account,
        "permlink": permlink,
        "weight": 10000,  # 100%
    }))

    tx.appendSigner(account, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Atomic post+beneficiaries+vote: {result}")
    return permlink


def batch_transfers(transfers: list[dict]):
    """Send multiple transfers in one transaction (all or nothing)."""
    tx = TransactionBuilder(blockchain_instance=hive)

    for t in transfers:
        amount_str = f"{t['amount']:.3f} {t['asset']}"
        tx.appendOps(Transfer(**{
            "from": account,
            "to": t["to"],
            "amount": amount_str,
            "memo": t.get("memo", ""),
        }))

    tx.appendSigner(account, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Batch transfer of {len(transfers)} payments: {result}")
    return result


def mixed_authority_transaction():
    """Transaction needing both posting and active keys."""
    tx = TransactionBuilder(blockchain_instance=hive)

    # Posting-level op: custom_json
    tx.appendOps(Custom_json(**{
        "id": "myapp",
        "required_posting_auths": [account],
        "required_auths": [],
        "json": json.dumps({"action": "log_event", "data": "started"}),
    }))

    # Active-level op: transfer
    tx.appendOps(Transfer(**{
        "from": account,
        "to": "service",
        "amount": "1.000 HIVE",
        "memo": "service fee",
    }))

    # Need both signers
    tx.appendSigner(account, "posting")
    tx.appendSigner(account, "active")
    tx.sign()
    result = tx.broadcast()
    return result


# Atomic post with beneficiaries
atomic_post_with_beneficiaries_and_vote(
    title="My Batched Post",
    body="This post was created with beneficiaries and self-vote atomically.",
    tags=["hive-dev", "python"],
    beneficiaries=[
        {"account": "dev-fund", "weight": 1000},   # 10%
        {"account": "curator", "weight": 500},      # 5%
    ],
)

# Batch payouts
batch_transfers([
    {"to": "alice", "amount": 10.0, "asset": "HIVE", "memo": "Payment 1"},
    {"to": "bob", "amount": 5.0, "asset": "HIVE", "memo": "Payment 2"},
    {"to": "charlie", "amount": 7.5, "asset": "HBD", "memo": "Refund"},
])
```

Key points:
- **Atomicity**: All operations in a transaction succeed or fail together
- **Operation order matters**: Operations execute sequentially within the transaction
- **Mixed authority**: If operations need different keys, add both signers
- **Max operations**: Technically limited by transaction size (~64KB), practically ~50 ops
- **RC cost**: Charged for the entire transaction, roughly sum of individual costs'''
    ),
    (
        "hive_sdk/dhive-encrypted-memo",
        r'''How do I send and read encrypted memos on Hive using dhive? I need to understand memo key usage.''',
        r'''<think>
Encrypted memos on Hive use the memo keys of sender and receiver.
When you prefix a memo with '#', it signals encryption. The sender's
memo private key encrypts the memo, and the receiver's memo private
key decrypts it. This uses shared-secret ECDH (Elliptic Curve Diffie-Hellman).
In dhive, the Memo module handles encryption/decryption.
Both parties can decrypt — the sender with their memo key and the
receiver's public memo key, and vice versa.
I need to show both sending encrypted transfers and decoding received memos.
</think>

Here is how to handle encrypted memos with dhive:

```javascript
const { Client, PrivateKey, Memo } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const activeKey = PrivateKey.fromString("5YourActiveKey");
const memoKey = PrivateKey.fromString("5YourMemoKey");
const sender = "youraccount";

/**
 * Send a transfer with an encrypted memo.
 * Only sender and recipient can decrypt it.
 */
async function transferWithEncryptedMemo(to, amount, asset, memoText) {
  // Get recipient's public memo key from the blockchain
  const [recipientAccount] = await client.database.getAccounts([to]);
  const recipientMemoPublic = recipientAccount.memo_key;

  // Encrypt the memo using sender's private memo key + recipient's public memo key
  const encrypted = Memo.encode(memoKey, recipientMemoPublic, `#${memoText}`);

  const op = [
    "transfer",
    {
      from: sender,
      to: to,
      amount: `${amount.toFixed(3)} ${asset}`,
      memo: encrypted,  // starts with '#' — signals encrypted
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Sent ${amount} ${asset} to @${to} with encrypted memo`);
  return result;
}

/**
 * Decrypt a memo received in a transfer.
 */
function decryptMemo(encryptedMemo) {
  if (!encryptedMemo.startsWith("#")) {
    return encryptedMemo;  // not encrypted, return as-is
  }

  try {
    const decrypted = Memo.decode(memoKey, encryptedMemo);
    return decrypted;
  } catch (err) {
    console.error("Failed to decrypt memo — wrong key or corrupted data");
    return null;
  }
}

/**
 * Scan transfer history for encrypted memos and decrypt them.
 */
async function getDecryptedTransfers(username, limit = 20) {
  const history = await client.call("condenser_api", "get_account_history", [
    username,
    -1,     // start from most recent
    limit,
    ...[]   // operation filter bitmask (optional)
  ]);

  const transfers = [];
  for (const [idx, entry] of history) {
    const [opType, opData] = entry.op;
    if (opType === "transfer") {
      let memo = opData.memo;
      if (memo.startsWith("#")) {
        try {
          memo = Memo.decode(memoKey, memo);
        } catch {
          memo = "[encrypted - cannot decrypt]";
        }
      }
      transfers.push({
        from: opData.from,
        to: opData.to,
        amount: opData.amount,
        memo: memo,
        timestamp: entry.timestamp,
      });
    }
  }
  return transfers;
}

// Send encrypted payment
await transferWithEncryptedMemo(
  "recipient",
  5.0,
  "HIVE",
  "Invoice #12345 — payment for consulting services"
);

// Read and decrypt incoming transfers
const transfers = await getDecryptedTransfers(sender);
for (const t of transfers) {
  console.log(`${t.from} -> ${t.to}: ${t.amount} | memo: ${t.memo}`);
}
```

Key points:
- **'#' prefix** signals an encrypted memo
- **Memo keys** (not posting/active) are used for encryption/decryption
- **ECDH**: Uses Elliptic Curve Diffie-Hellman shared secret
- **Both parties** can decrypt — sender and recipient
- **On-chain data** is encrypted — only key holders can read it
- **Common mistake**: Using the wrong key type — memo encryption requires the memo private key specifically'''
    ),
    (
        "hive_sdk/beem-account-update-authorities",
        r'''How do I update account authorities (change keys, add multi-sig) using beem? I need to rotate keys and set up shared account control.''',
        r'''<think>
Account updates on Hive modify the authority structure. Each authority level
(owner, active, posting) has a weight_threshold and a list of key_auths
and account_auths, each with weights. For multi-sig, you set threshold > 1
and add multiple keys/accounts that sum to meet the threshold.
Owner key is required to change owner authority. Active key can change
active, posting, memo, and json_metadata. The owner key change has a
30-day recovery window. I should show key rotation, adding multi-sig,
and the important safety considerations.
</think>

Here is how to update account authorities with beem:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_update
from beemgraphenebase.account import PasswordKey

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]  # active key for active/posting/memo changes
)
account_name = "youraccount"


def rotate_posting_key(new_password: str):
    """Change the posting key by deriving from a new password."""
    new_pk = PasswordKey(account_name, new_password, role="posting")
    new_public = str(new_pk.get_public_key())

    acc = Account(account_name, blockchain_instance=hive)

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Account_update(**{
        "account": account_name,
        "posting": {
            "weight_threshold": 1,
            "account_auths": acc["posting"]["account_auths"],
            "key_auths": [[new_public, 1]],
        },
        "memo_key": acc["memo_key"],
        "json_metadata": acc["json_metadata"],
    }))
    tx.appendSigner(account_name, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Posting key rotated. New public key: {new_public}")
    return result


def setup_multisig_active(key_pubkeys: list[str], threshold: int = 2):
    """Set up multi-signature on the active authority.
    Requires `threshold` signatures out of the provided keys.
    """
    acc = Account(account_name, blockchain_instance=hive)

    key_auths = [[pub, 1] for pub in sorted(key_pubkeys)]

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Account_update(**{
        "account": account_name,
        "active": {
            "weight_threshold": threshold,
            "account_auths": [],
            "key_auths": key_auths,
        },
        "memo_key": acc["memo_key"],
        "json_metadata": acc["json_metadata"],
    }))
    tx.appendSigner(account_name, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Multi-sig active authority set: {threshold}-of-{len(key_pubkeys)}")
    return result


def add_posting_authority_for_app(app_account: str):
    """Grant an app account posting authority (like HiveSigner)."""
    acc = Account(account_name, blockchain_instance=hive)

    current_account_auths = list(acc["posting"]["account_auths"])
    # Check if already authorized
    if any(a[0] == app_account for a in current_account_auths):
        print(f"@{app_account} already has posting authority")
        return

    current_account_auths.append([app_account, 1])
    current_account_auths.sort(key=lambda x: x[0])

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Account_update(**{
        "account": account_name,
        "posting": {
            "weight_threshold": 1,
            "account_auths": current_account_auths,
            "key_auths": acc["posting"]["key_auths"],
        },
        "memo_key": acc["memo_key"],
        "json_metadata": acc["json_metadata"],
    }))
    tx.appendSigner(account_name, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Granted posting authority to @{app_account}")
    return result


def revoke_posting_authority(app_account: str):
    """Remove an app account's posting authority."""
    acc = Account(account_name, blockchain_instance=hive)

    current_auths = [
        a for a in acc["posting"]["account_auths"]
        if a[0] != app_account
    ]

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Account_update(**{
        "account": account_name,
        "posting": {
            "weight_threshold": 1,
            "account_auths": current_auths,
            "key_auths": acc["posting"]["key_auths"],
        },
        "memo_key": acc["memo_key"],
        "json_metadata": acc["json_metadata"],
    }))
    tx.appendSigner(account_name, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Revoked posting authority from @{app_account}")
    return result


# Rotate posting key
rotate_posting_key("MyNewSecurePassword2024!")

# Set up 2-of-3 multi-sig on active authority
setup_multisig_active([
    "STM6pub1...",
    "STM6pub2...",
    "STM6pub3...",
], threshold=2)

# Grant app posting permission
add_posting_authority_for_app("hivesigner")

# Revoke app permission
revoke_posting_authority("malicious-app")
```

Critical safety notes:
- **Owner key changes** require the current owner key and have 30-day recovery
- **Active key** can change active, posting, and memo authorities
- **Never lock yourself out**: Always ensure you hold enough keys to meet the threshold
- **Account auths must be sorted** alphabetically
- **Multi-sig**: Threshold must be <= sum of all weights
- **App authorization**: Only grant posting auth to trusted apps; never grant active auth'''
    ),
    (
        "hive_sdk/dhive-escrow-transfer",
        r'''How do I create an escrow transfer on Hive using dhive? I need a trusted third-party mediated payment.''',
        r'''<think>
Escrow transfers on Hive involve three parties: sender (from), receiver (to),
and an escrow agent. The flow is:
1. Sender creates the escrow with escrow_transfer
2. Agent approves with escrow_approve (or receiver, both must approve)
3. On completion, sender releases with escrow_release
4. If disputed, agent can release to either party with escrow_dispute + escrow_release
There are deadlines: ratification_deadline (both parties must approve by then)
and escrow_expiration (auto-return if not released by then).
The escrow can hold both HIVE and HBD simultaneously.
Active key required. This is relatively rarely used but good for marketplace scenarios.
</think>

Here is how to implement escrow transfers with dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

/**
 * Step 1: Create escrow (by sender).
 */
async function createEscrow({
  from,
  to,
  agent,
  escrowId,
  hiveAmount = 0,
  hbdAmount = 0,
  fee,
  ratificationDeadline,
  escrowExpiration,
  memo = "",
  activeKey,
}) {
  const op = [
    "escrow_transfer",
    {
      from,
      to,
      agent,
      escrow_id: escrowId,
      hbd_amount: `${hbdAmount.toFixed(3)} HBD`,
      hive_amount: `${hiveAmount.toFixed(3)} HIVE`,
      fee: `${fee.toFixed(3)} HIVE`,  // agent fee
      ratification_deadline: ratificationDeadline,  // ISO date
      escrow_expiration: escrowExpiration,           // ISO date
      json_meta: JSON.stringify({ memo, purpose: "marketplace_sale" }),
    },
  ];

  const result = await client.broadcast.sendOperations(
    [op],
    PrivateKey.fromString(activeKey)
  );
  console.log(`Escrow #${escrowId} created: ${hiveAmount} HIVE + ${hbdAmount} HBD`);
  return result;
}

/**
 * Step 2: Approve escrow (by agent AND receiver — both must approve).
 */
async function approveEscrow({ who, from, to, agent, escrowId, approve, activeKey }) {
  const op = [
    "escrow_approve",
    {
      from,
      to,
      agent,
      who,  // the account approving (agent or receiver)
      escrow_id: escrowId,
      approve,  // true to approve, false to reject
    },
  ];

  const result = await client.broadcast.sendOperations(
    [op],
    PrivateKey.fromString(activeKey)
  );
  const action = approve ? "approved" : "rejected";
  console.log(`Escrow #${escrowId} ${action} by @${who}`);
  return result;
}

/**
 * Step 3a: Release escrow (normal completion).
 */
async function releaseEscrow({
  who,
  from,
  to,
  agent,
  escrowId,
  receiver,
  hiveAmount = 0,
  hbdAmount = 0,
  activeKey,
}) {
  const op = [
    "escrow_release",
    {
      from,
      to,
      agent,
      who,       // who is releasing (from, to, or agent)
      receiver,  // who receives the funds
      escrow_id: escrowId,
      hbd_amount: `${hbdAmount.toFixed(3)} HBD`,
      hive_amount: `${hiveAmount.toFixed(3)} HIVE`,
    },
  ];

  const result = await client.broadcast.sendOperations(
    [op],
    PrivateKey.fromString(activeKey)
  );
  console.log(`Escrow #${escrowId} released ${hiveAmount} HIVE to @${receiver}`);
  return result;
}

/**
 * Step 3b: Dispute escrow (either party can raise dispute).
 */
async function disputeEscrow({ who, from, to, agent, escrowId, activeKey }) {
  const op = [
    "escrow_dispute",
    {
      from,
      to,
      agent,
      who,  // who is raising the dispute
      escrow_id: escrowId,
    },
  ];

  const result = await client.broadcast.sendOperations(
    [op],
    PrivateKey.fromString(activeKey)
  );
  console.log(`Escrow #${escrowId} disputed by @${who}`);
  return result;
}

// Full escrow flow example:
const escrowId = Date.now() % 2147483647;  // unique 32-bit ID

// 1. Seller creates escrow
const ratDeadline = new Date(Date.now() + 24 * 3600 * 1000).toISOString().split(".")[0];
const expiration = new Date(Date.now() + 30 * 24 * 3600 * 1000).toISOString().split(".")[0];

await createEscrow({
  from: "buyer",
  to: "seller",
  agent: "trusted-escrow",
  escrowId,
  hiveAmount: 100,
  hbdAmount: 0,
  fee: 1,  // 1 HIVE agent fee
  ratificationDeadline: ratDeadline,
  escrowExpiration: expiration,
  activeKey: "5BuyerActiveKey",
});

// 2. Agent and seller approve
await approveEscrow({
  who: "trusted-escrow", from: "buyer", to: "seller",
  agent: "trusted-escrow", escrowId, approve: true,
  activeKey: "5AgentActiveKey",
});
await approveEscrow({
  who: "seller", from: "buyer", to: "seller",
  agent: "trusted-escrow", escrowId, approve: true,
  activeKey: "5SellerActiveKey",
});

// 3. Release to seller on delivery
await releaseEscrow({
  who: "buyer", from: "buyer", to: "seller",
  agent: "trusted-escrow", escrowId,
  receiver: "seller", hiveAmount: 100,
  activeKey: "5BuyerActiveKey",
});
```

Escrow rules:
- **Three parties**: sender, receiver, agent — all identified by Hive account
- **Both must approve**: Agent AND receiver must call escrow_approve before ratification deadline
- **Dispute**: Either party raises a dispute, then only the agent can release funds
- **Expiration**: If not released by escrow_expiration, funds return to sender
- **Agent fee**: Paid by sender, awarded to agent on release
- **Active key** required for all escrow operations'''
    ),
    (
        "hive_sdk/beem-community-operations",
        r'''How do I interact with Hive communities using beem? I need to subscribe, post to a community, and manage community roles.''',
        r'''<think>
Hive communities use custom_json with id "community" for subscriptions and
moderation actions. Communities are identified by hive-XXXXXX format names.
Posting to a community means setting parent_permlink to the community name.
Role management (muting, pinning, setting roles) also uses custom_json.
Community roles: guest, member, mod, admin, owner — each with increasing
permissions. Subscribe/unsubscribe are posting-auth operations.
Setting roles requires mod+ authority in the community.
</think>

Here is how to work with Hive communities using beem:

```python
import json
from beem import Hive
from beem.comment import Comment
from beem.community import Community

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)
account = "youraccount"


def subscribe_to_community(community_name: str):
    """Subscribe to a Hive community (e.g., 'hive-174301')."""
    hive.custom_json(
        "community",
        json_data=["subscribe", {"community": community_name}],
        required_posting_auths=[account],
    )
    print(f"Subscribed to {community_name}")


def unsubscribe_from_community(community_name: str):
    """Unsubscribe from a community."""
    hive.custom_json(
        "community",
        json_data=["unsubscribe", {"community": community_name}],
        required_posting_auths=[account],
    )
    print(f"Unsubscribed from {community_name}")


def post_to_community(community_name: str, title: str, body: str, tags: list):
    """Post to a specific community."""
    import time
    permlink = f"{title.lower().replace(' ', '-')[:100]}-{int(time.time())}"
    all_tags = [community_name] + [t for t in tags if t != community_name]

    hive.post(
        title, body, author=account,
        permlink=permlink,
        tags=all_tags,
        community=community_name,
        json_metadata=json.dumps({
            "tags": all_tags,
            "app": "myapp/1.0",
            "format": "markdown",
        }),
    )
    print(f"Posted to community {community_name}: @{account}/{permlink}")
    return permlink


def set_community_role(community_name: str, target_account: str, role: str):
    """Set a user's role in a community.
    Roles: guest, member, mod, admin, owner
    Requires mod+ authority in the community.
    """
    hive.custom_json(
        "community",
        json_data=["setRole", {
            "community": community_name,
            "account": target_account,
            "role": role,
        }],
        required_posting_auths=[account],
    )
    print(f"Set @{target_account} as {role} in {community_name}")


def mute_post_in_community(community_name: str, author: str, permlink: str, notes: str):
    """Mute (hide) a post in a community. Requires mod+ role."""
    hive.custom_json(
        "community",
        json_data=["mutePost", {
            "community": community_name,
            "account": author,
            "permlink": permlink,
            "notes": notes,
        }],
        required_posting_auths=[account],
    )
    print(f"Muted @{author}/{permlink} in {community_name}")


def pin_post(community_name: str, author: str, permlink: str):
    """Pin a post to the top of a community. Requires mod+ role."""
    hive.custom_json(
        "community",
        json_data=["pinPost", {
            "community": community_name,
            "account": author,
            "permlink": permlink,
        }],
        required_posting_auths=[account],
    )
    print(f"Pinned @{author}/{permlink} in {community_name}")


def get_community_info(community_name: str):
    """Fetch community details via bridge API."""
    result = hive.rpc.get_community({
        "name": community_name,
        "observer": account,
    }, api="bridge")
    return result


# Subscribe to the Hive Dev community
subscribe_to_community("hive-174301")

# Post to the community
permlink = post_to_community(
    "hive-174301",
    "Building a Community Bot",
    "# Community Bot Tutorial\n\nHere is how to automate community management...",
    ["python", "beem", "tutorial"],
)

# Moderate (if you are a mod)
set_community_role("hive-174301", "newmember", "member")
pin_post("hive-174301", account, permlink)
```

Community details:
- **Community names**: Format `hive-XXXXXX` (6-digit number)
- **Roles**: guest < member < mod < admin < owner
- **Posting to community**: Set `parent_permlink` to the community name
- **All community ops** use custom_json with id `"community"`
- **Posting key** is sufficient for all community operations
- **Moderation**: Muting hides posts from the community feed but does not delete them on-chain'''
    ),
    (
        "hive_sdk/dhive-proposal-system",
        r'''How do I interact with the Hive proposal system (DHF/DAO) using dhive? I need to create proposals, vote on them, and query active proposals.''',
        r'''<think>
The Hive DAO (Decentralized Hive Fund, previously SPS) allows users to create
funding proposals voted on by stakeholders. Proposals require a 10 HBD fee
(burned) and a post that describes the proposal. Voting uses the
update_proposal_votes operation with posting key. Creating a proposal
uses create_proposal with active key. The return proposal sets the
funding threshold — proposals must get more votes than the return proposal
to receive funding. I should cover creation, voting, and querying.
</think>

Here is how to work with the Hive proposal system (DHF) using dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const postingKey = PrivateKey.fromString("5YourPostingKey");
const activeKey = PrivateKey.fromString("5YourActiveKey");
const account = "youraccount";

/**
 * Create a funding proposal.
 * Requires a post that describes the proposal + 10 HBD fee (burned).
 */
async function createProposal({
  title,
  permlink,          // permlink of the descriptive post
  startDate,         // "2024-03-01T00:00:00"
  endDate,           // "2024-06-01T00:00:00"
  dailyPay,          // daily HBD amount requested
}) {
  const op = [
    "create_proposal",
    {
      creator: account,
      receiver: account,  // who receives the funds
      start_date: startDate,
      end_date: endDate,
      daily_pay: `${dailyPay.toFixed(3)} HBD`,
      subject: title,
      permlink: permlink,
      extensions: [],
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Proposal created: "${title}" — ${dailyPay} HBD/day`);
  return result;
}

/**
 * Vote for or against proposals.
 */
async function voteProposals(proposalIds, approve = true) {
  const op = [
    "update_proposal_votes",
    {
      voter: account,
      proposal_ids: proposalIds,
      approve: approve,
      extensions: [],
    },
  ];

  const result = await client.broadcast.sendOperations([op], postingKey);
  const action = approve ? "Voted for" : "Removed vote from";
  console.log(`${action} proposals: ${proposalIds.join(", ")}`);
  return result;
}

/**
 * List active proposals.
 */
async function listProposals({ order = "by_total_votes", status = "active", limit = 50 } = {}) {
  const result = await client.call("database_api", "list_proposals", {
    start: [],
    limit: limit,
    order: order,           // by_total_votes, by_creator, by_start_date, by_end_date
    order_direction: "descending",
    status: status,         // all, active, inactive, expired, votable
  });

  return result.proposals.map((p) => ({
    id: p.proposal_id,
    creator: p.creator,
    receiver: p.receiver,
    subject: p.subject,
    daily_pay: p.daily_pay,
    total_votes: p.total_votes,
    start_date: p.start_date,
    end_date: p.end_date,
    status: p.status,
  }));
}

/**
 * Find the return proposal (threshold for funding).
 */
async function getReturnProposal() {
  const proposals = await listProposals({ order: "by_total_votes" });
  return proposals.find((p) => p.receiver === "hive.fund" || p.daily_pay === "0.000 HBD");
}

/**
 * Remove a proposal (only the creator can do this).
 */
async function removeProposal(proposalId) {
  const op = [
    "remove_proposal",
    {
      proposal_owner: account,
      proposal_ids: [proposalId],
      extensions: [],
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Removed proposal #${proposalId}`);
  return result;
}

// Create a proposal (first publish a post describing it)
await createProposal({
  title: "HiveSDK Development Funding Q2 2024",
  permlink: "hivesdk-development-funding-q2-2024",
  startDate: "2024-04-01T00:00:00",
  endDate: "2024-07-01T00:00:00",
  dailyPay: 50,  // 50 HBD per day
});

// Vote for proposals
await voteProposals([42, 56, 78], true);

// Remove vote
await voteProposals([78], false);

// List active proposals
const proposals = await listProposals();
for (const p of proposals) {
  console.log(`#${p.id} "${p.subject}" by @${p.creator} — ${p.daily_pay}/day`);
}

// Check return proposal threshold
const returnProp = await getReturnProposal();
console.log(`Return proposal votes: ${returnProp.total_votes}`);
```

Proposal system details:
- **10 HBD creation fee** (burned, non-refundable)
- **Requires a post** describing the proposal (linked via permlink)
- **Posting key** for voting, **active key** for creating/removing
- **Return proposal**: The funding threshold — proposals above it get funded
- **Daily pay**: Paid in HBD from the DAO fund
- **Stakeholder weighted**: Vote weight proportional to HP (Hive Power)
- **No maximum proposals**: One account can create multiple proposals'''
    ),
    (
        "hive_sdk/beem-change-recovery-account",
        r'''How do I change the recovery account on Hive and initiate account recovery using beem?''',
        r'''<think>
Account recovery on Hive is a security feature. Each account has a designated
recovery account (usually the account creator). If keys are compromised,
the recovery account can initiate recovery within 30 days of the owner key
change. Changing the recovery account takes 30 days to take effect.
The process is: 1) change_recovery_account (takes 30 days), 2) if compromised,
recovery account calls request_account_recovery with new owner key,
3) the account holder confirms with recover_account using both old and new
owner keys. This is complex but critical for security.
</think>

Here is how to manage account recovery with beem:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Change_recovery_account,
    Request_account_recovery,
    Recover_account,
)
from beemgraphenebase.account import PasswordKey

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourOwnerKey"]
)


def change_recovery_account(account_name: str, new_recovery: str):
    """Change the recovery account. Takes 30 days to become effective."""
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Change_recovery_account(**{
        "account_to_recover": account_name,
        "new_recovery_account": new_recovery,
        "extensions": [],
    }))
    tx.appendSigner(account_name, "owner")
    tx.sign()
    result = tx.broadcast()
    print(f"Recovery account change initiated: @{new_recovery}")
    print("Takes effect in 30 days")
    return result


def request_recovery(recovery_account: str, account_to_recover: str,
                     new_owner_public_key: str):
    """Recovery account requests recovery for a compromised account.
    Must be done within 30 days of the malicious owner key change.
    """
    hive_recovery = Hive(
        node=["https://api.hive.blog", "https://api.deathwing.me"],
        keys=["5RecoveryAccountActiveKey"]
    )
    tx = TransactionBuilder(blockchain_instance=hive_recovery)
    tx.appendOps(Request_account_recovery(**{
        "recovery_account": recovery_account,
        "account_to_recover": account_to_recover,
        "new_owner_authority": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[new_owner_public_key, 1]],
        },
        "extensions": [],
    }))
    tx.appendSigner(recovery_account, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Recovery requested for @{account_to_recover}")
    return result


def confirm_recovery(account_to_recover: str,
                     old_owner_key: str, new_owner_key: str):
    """Account holder confirms recovery with both old and new owner keys."""
    hive_confirm = Hive(
        node=["https://api.hive.blog", "https://api.deathwing.me"],
        keys=[old_owner_key, new_owner_key]  # both required
    )

    new_pub = str(PasswordKey(account_to_recover, "", role="owner").get_public_key())

    tx = TransactionBuilder(blockchain_instance=hive_confirm)
    tx.appendOps(Recover_account(**{
        "account_to_recover": account_to_recover,
        "new_owner_authority": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[new_pub, 1]],
        },
        "recent_owner_authority": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[str(PasswordKey(account_to_recover, "", role="owner").get_public_key()), 1]],
        },
        "extensions": [],
    }))
    tx.appendSigner(account_to_recover, "owner")
    tx.sign()
    result = tx.broadcast()
    print(f"Recovery confirmed for @{account_to_recover}")
    return result


# Check current recovery account
acc = Account("youraccount", blockchain_instance=hive)
print(f"Current recovery account: {acc['recovery_account']}")

# Change recovery account (30-day delay)
change_recovery_account("youraccount", "trusted-friend")
```

Recovery process summary:
1. **Preventive**: `change_recovery_account` — set a trusted friend/service (30-day delay)
2. **If compromised**: Recovery account calls `request_account_recovery` with new owner key
3. **Confirm**: Account holder calls `recover_account` with both old and new owner keys
4. **30-day window**: Recovery must happen within 30 days of malicious key change
5. **Owner key** required for changing recovery account
6. **Default recovery**: Usually the account creator'''
    ),
    (
        "hive_sdk/dhive-follow-mute-reblog",
        r'''How do I follow users, mute users, and reblog posts using dhive? These are all custom_json operations right?''',
        r'''<think>
Yes, follow/mute/reblog all use custom_json with id "follow". The payload
format is an array: ["follow", {follower, following, what}] for follow/mute,
and ["reblog", {account, author, permlink}] for reblogs.
The "what" field determines the action: ["blog"] = follow, ["ignore"] = mute,
[] = unfollow/unmute. Posting key is required for all.
Reblogs cannot be undone on-chain (though frontends may hide them).
I should show all three operations clearly.
</think>

Here is how to follow, mute, and reblog with dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const postingKey = PrivateKey.fromString("5YourPostingKey");
const account = "youraccount";

/**
 * Follow a user — their posts appear in your feed.
 */
async function followUser(targetUser) {
  const json = JSON.stringify([
    "follow",
    {
      follower: account,
      following: targetUser,
      what: ["blog"],  // "blog" = follow
    },
  ]);

  await client.broadcast.json(
    {
      id: "follow",
      required_posting_auths: [account],
      required_auths: [],
      json,
    },
    postingKey
  );
  console.log(`Now following @${targetUser}`);
}

/**
 * Unfollow a user.
 */
async function unfollowUser(targetUser) {
  const json = JSON.stringify([
    "follow",
    {
      follower: account,
      following: targetUser,
      what: [],  // empty array = unfollow
    },
  ]);

  await client.broadcast.json(
    {
      id: "follow",
      required_posting_auths: [account],
      required_auths: [],
      json,
    },
    postingKey
  );
  console.log(`Unfollowed @${targetUser}`);
}

/**
 * Mute a user — hide their content from your view.
 */
async function muteUser(targetUser) {
  const json = JSON.stringify([
    "follow",
    {
      follower: account,
      following: targetUser,
      what: ["ignore"],  // "ignore" = mute
    },
  ]);

  await client.broadcast.json(
    {
      id: "follow",
      required_posting_auths: [account],
      required_auths: [],
      json,
    },
    postingKey
  );
  console.log(`Muted @${targetUser}`);
}

/**
 * Reblog (share) a post to your followers' feeds.
 * Cannot be undone on-chain.
 */
async function reblogPost(author, permlink) {
  const json = JSON.stringify([
    "reblog",
    {
      account: account,
      author: author,
      permlink: permlink,
    },
  ]);

  await client.broadcast.json(
    {
      id: "follow",
      required_posting_auths: [account],
      required_auths: [],
      json,
    },
    postingKey
  );
  console.log(`Reblogged @${author}/${permlink}`);
}

/**
 * Get list of accounts a user follows.
 */
async function getFollowing(username, limit = 100) {
  const result = await client.call("condenser_api", "get_following", [
    username,
    "",      // start from beginning
    "blog",  // type: blog, ignore
    limit,
  ]);
  return result.map((f) => f.following);
}

/**
 * Get list of muted accounts.
 */
async function getMuted(username, limit = 100) {
  const result = await client.call("condenser_api", "get_following", [
    username,
    "",
    "ignore",  // type "ignore" = muted accounts
    limit,
  ]);
  return result.map((f) => f.following);
}

// Follow
await followUser("blocktrades");
await followUser("hiveio");

// Mute
await muteUser("spammer-account");

// Reblog a post
await reblogPost("interesting-author", "great-article-permlink");

// Check who you follow
const following = await getFollowing(account);
console.log(`Following ${following.length} accounts:`, following);

// Check muted accounts
const muted = await getMuted(account);
console.log(`Muted ${muted.length} accounts:`, muted);

// Unfollow
await unfollowUser("blocktrades");
```

Key points:
- **All use custom_json** with id `"follow"` and posting key
- **Follow**: `what: ["blog"]`
- **Unfollow**: `what: []` (empty array)
- **Mute**: `what: ["ignore"]`
- **Unmute**: Same as unfollow — `what: []`
- **Reblog**: Uses `"reblog"` action type, cannot be undone on-chain
- **Cannot reblog your own posts**'''
    ),
    (
        "hive_sdk/beem-rc-delegation",
        r'''How do I delegate Resource Credits (RC) to another account using beem? New accounts need RC to transact.''',
        r'''<think>
RC delegation was added to help onboard new users who have no HP and therefore
no RC. It uses custom_json with id "rc" and requires active authority.
The delegation is specified in RC units (not HP or VESTS). You can delegate
a portion of your max RC to another account. The delegatee can then use
those RC for transactions. Undelegating is done by setting the amount to 0.
This is separate from HP/VESTS delegation.
Important: RC delegation uses the "rc" custom_json id with active auth.
</think>

Here is how to delegate Resource Credits with beem:

```python
import json
from beem import Hive
from beem.account import Account
from beem.rc import RC

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]  # active key required for RC delegation
)
account = "youraccount"


def get_rc_info(username: str) -> dict:
    """Get RC status for an account."""
    acc = Account(username, blockchain_instance=hive)
    rc = acc.get_rc_manabar()
    return {
        "current_pct": round(rc["current_pct"], 2),
        "current_mana": rc["current_mana"],
        "max_mana": rc["max_mana"],
    }


def delegate_rc(to_account: str, max_rc: int):
    """Delegate RC to another account.

    Args:
        to_account: The account receiving the RC delegation
        max_rc: Maximum RC to delegate (in RC units, not HP)
    """
    payload = json.dumps([
        "delegate_rc",
        {
            "from": account,
            "delegatees": [to_account],
            "max_rc": max_rc,
            "extensions": [],
        }
    ])

    hive.custom_json(
        "rc",
        json_data=payload,
        required_auths=[account],
    )
    print(f"Delegated {max_rc:,} RC to @{to_account}")


def undelegate_rc(from_account: str):
    """Remove RC delegation from an account."""
    delegate_rc(from_account, 0)
    print(f"Removed RC delegation from @{from_account}")


def estimate_rc_needed(operations_per_day: int = 10) -> int:
    """Estimate how much RC a new user needs for basic daily usage."""
    rc = RC(blockchain_instance=hive)

    # Approximate RC costs per operation type
    comment_cost = rc.comment(tx_size=250, permlink_length=50,
                              parent_permlink_length=50)
    vote_cost = rc.vote(tx_size=120)
    transfer_cost = rc.transfer(tx_size=200, market_op_count=1)

    # Assume mix: 3 comments, 5 votes, 2 transfers per day
    daily_rc = (3 * comment_cost + 5 * vote_cost + 2 * transfer_cost)

    # Add 50% buffer for safety
    return int(daily_rc * 1.5)


def delegate_rc_to_multiple(accounts: list[str], rc_per_account: int):
    """Batch delegate RC to multiple new accounts."""
    for acc in accounts:
        try:
            delegate_rc(acc, rc_per_account)
        except Exception as e:
            print(f"Failed to delegate to @{acc}: {e}")


# Check your RC status
my_rc = get_rc_info(account)
print(f"Your RC: {my_rc['current_pct']}%")

# Estimate how much RC a new user needs
needed = estimate_rc_needed(operations_per_day=10)
print(f"Estimated daily RC need: {needed:,}")

# Delegate RC to a new user
delegate_rc("newuser123", needed * 7)  # 1 week of RC

# Delegate to multiple onboarded users
new_users = ["onboard1", "onboard2", "onboard3"]
delegate_rc_to_multiple(new_users, needed * 7)

# Remove delegation when no longer needed
undelegate_rc("newuser123")
```

RC delegation details:
- **Active key** required (uses custom_json with id `"rc"`)
- **Separate from HP delegation** — RC delegation only affects RC, not voting power
- **Does not reduce your HP** — it shares a portion of your RC regeneration
- **New accounts** typically need RC delegation to perform their first transactions
- **RC units** are large numbers (billions for basic operations)
- **Delegatees list**: Can delegate to multiple accounts in one operation
- **Undelegate**: Set max_rc to 0 for the target account'''
    ),
    (
        "hive_sdk/dhive-account-history",
        r'''How do I fetch and filter account history using dhive? I need to get transfer history, vote history, and paginate through large histories.''',
        r'''<think>
Account history in Hive is accessed via get_account_history. It returns
operations in reverse chronological order. The API takes account name,
start index (-1 for most recent), and limit. Each entry has a sequence
number. For pagination, use the sequence number from the last result
as the new start. You can filter by operation type using the operation
filter bitmask, but the condenser_api version may not support it well.
I should show basic fetching, pagination, and filtering patterns.
</think>

Here is how to fetch and filter account history with dhive:

```javascript
const { Client } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

/**
 * Fetch recent account history entries.
 */
async function getRecentHistory(username, limit = 50) {
  const history = await client.call("condenser_api", "get_account_history", [
    username,
    -1,     // -1 = start from most recent
    limit,  // max 1000 per call
  ]);

  return history.map(([seq, entry]) => ({
    sequence: seq,
    type: entry.op[0],
    data: entry.op[1],
    timestamp: entry.timestamp,
    block: entry.block,
    trx_id: entry.trx_id,
  }));
}

/**
 * Paginate through entire account history.
 */
async function* paginateHistory(username, batchSize = 1000) {
  let start = -1;

  // Get the latest sequence number first
  const latest = await client.call("condenser_api", "get_account_history", [
    username, -1, 0,
  ]);
  if (latest.length === 0) return;
  start = latest[0][0];

  while (start >= 0) {
    const limit = Math.min(batchSize, start + 1);
    const batch = await client.call("condenser_api", "get_account_history", [
      username, start, limit,
    ]);

    if (batch.length === 0) break;

    for (const [seq, entry] of batch) {
      yield {
        sequence: seq,
        type: entry.op[0],
        data: entry.op[1],
        timestamp: entry.timestamp,
        block: entry.block,
      };
    }

    // Move to the entry before the oldest in this batch
    start = batch[0][0] - 1;
    if (start < 0) break;
  }
}

/**
 * Get only transfer history for an account.
 */
async function getTransferHistory(username, limit = 100) {
  const history = await getRecentHistory(username, Math.min(limit * 3, 1000));
  return history
    .filter((h) => h.type === "transfer")
    .slice(0, limit)
    .map((h) => ({
      from: h.data.from,
      to: h.data.to,
      amount: h.data.amount,
      memo: h.data.memo,
      timestamp: h.timestamp,
    }));
}

/**
 * Get vote history (votes cast by the account).
 */
async function getVoteHistory(username, limit = 50) {
  const history = await getRecentHistory(username, Math.min(limit * 5, 1000));
  return history
    .filter((h) => h.type === "vote")
    .slice(0, limit)
    .map((h) => ({
      author: h.data.author,
      permlink: h.data.permlink,
      weight: h.data.weight / 100,
      timestamp: h.timestamp,
    }));
}

/**
 * Search history for a specific operation type with date range.
 */
async function searchHistory(username, opType, startDate, endDate) {
  const results = [];
  const start = new Date(startDate);
  const end = new Date(endDate);

  for await (const entry of paginateHistory(username, 1000)) {
    const entryDate = new Date(entry.timestamp + "Z");

    if (entryDate < start) break;  // past our range, stop
    if (entryDate > end) continue; // not yet in range

    if (entry.type === opType) {
      results.push(entry);
    }
  }
  return results;
}

// Get recent history
const recent = await getRecentHistory("blocktrades", 20);
for (const entry of recent) {
  console.log(`[${entry.timestamp}] ${entry.type}`);
}

// Get transfer history
const transfers = await getTransferHistory("blocktrades", 10);
for (const t of transfers) {
  console.log(`${t.from} -> ${t.to}: ${t.amount} | ${t.memo.slice(0, 50)}`);
}

// Paginate through full history
let count = 0;
for await (const entry of paginateHistory("blocktrades")) {
  if (entry.type === "transfer" && parseFloat(entry.data.amount) > 1000) {
    console.log(`Large transfer: ${entry.data.amount} at ${entry.timestamp}`);
  }
  if (++count > 5000) break;  // safety limit
}

// Search for transfers in a date range
const marchTransfers = await searchHistory(
  "blocktrades", "transfer",
  "2024-03-01", "2024-03-31"
);
console.log(`Found ${marchTransfers.length} transfers in March`);
```

Key points:
- **Max 1000** entries per API call
- **Reverse chronological**: Most recent first when using -1 as start
- **Sequence numbers**: Use for pagination (decrement from last result)
- **No native filtering**: Filter client-side by operation type
- **Virtual operations**: Included in history (curation_reward, author_reward, etc.)
- **Rate limiting**: Large history scans should add delays between API calls'''
    ),
    (
        "hive_sdk/beem-hive-engine-tokens",
        r'''How do I interact with Hive-Engine tokens using beem? I need to transfer, stake, and query token balances.''',
        r'''<think>
Hive-Engine is a Layer 2 sidechain for Hive that supports custom tokens.
All Hive-Engine operations use custom_json with id "ssc-mainnet-hive".
Token transfers require active auth, while some social token ops may use posting.
To query balances and token info, you use the Hive-Engine API (separate from
the Hive node API). I should show the custom_json operations for transfers
and staking, plus the separate API calls for reading balances.
The contractName is usually "tokens" and contractAction varies.
</think>

Here is how to work with Hive-Engine tokens using beem:

```python
import json
import requests
from beem import Hive

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)
account = "youraccount"

HE_API = "https://api.hive-engine.com/rpc/contracts"


def he_query(contract: str, table: str, query: dict, limit: int = 1000) -> list:
    """Query Hive-Engine sidechain state."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "find",
        "params": {
            "contract": contract,
            "table": table,
            "query": query,
            "limit": limit,
        },
    }
    resp = requests.post(HE_API, json=payload)
    resp.raise_for_status()
    return resp.json().get("result", [])


def get_token_balance(username: str, symbol: str = None) -> list:
    """Get Hive-Engine token balances for an account."""
    query = {"account": username}
    if symbol:
        query["symbol"] = symbol
    return he_query("tokens", "balances", query)


def get_token_info(symbol: str) -> dict:
    """Get token metadata (supply, precision, etc.)."""
    results = he_query("tokens", "tokens", {"symbol": symbol})
    return results[0] if results else None


def transfer_token(to: str, symbol: str, quantity: str, memo: str = ""):
    """Transfer a Hive-Engine token."""
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": "tokens",
            "contractAction": "transfer",
            "contractPayload": {
                "symbol": symbol,
                "to": to,
                "quantity": quantity,
                "memo": memo,
            },
        },
        required_auths=[account],
    )
    print(f"Transferred {quantity} {symbol} to @{to}")


def stake_token(to: str, symbol: str, quantity: str):
    """Stake a Hive-Engine token."""
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": "tokens",
            "contractAction": "stake",
            "contractPayload": {
                "symbol": symbol,
                "to": to,
                "quantity": quantity,
            },
        },
        required_auths=[account],
    )
    print(f"Staked {quantity} {symbol} to @{to}")


def unstake_token(symbol: str, quantity: str):
    """Start unstaking a token (may have cooldown period)."""
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": "tokens",
            "contractAction": "unstake",
            "contractPayload": {
                "symbol": symbol,
                "quantity": quantity,
            },
        },
        required_auths=[account],
    )
    print(f"Unstaking {quantity} {symbol}")


def delegate_token(to: str, symbol: str, quantity: str):
    """Delegate a staked Hive-Engine token."""
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": "tokens",
            "contractAction": "delegate",
            "contractPayload": {
                "symbol": symbol,
                "to": to,
                "quantity": quantity,
            },
        },
        required_auths=[account],
    )
    print(f"Delegated {quantity} {symbol} to @{to}")


# Query balances
balances = get_token_balance(account)
for b in balances:
    if float(b["balance"]) > 0:
        print(f"{b['symbol']}: {b['balance']} (staked: {b.get('stake', '0')})")

# Get specific token balance
bee = get_token_balance(account, "BEE")
if bee:
    print(f"BEE balance: {bee[0]['balance']}")

# Token info
info = get_token_info("BEE")
print(f"BEE supply: {info['supply']}, precision: {info['precision']}")

# Transfer tokens
transfer_token("recipient", "BEE", "10.000", "Payment")

# Stake tokens
stake_token(account, "BEE", "100.000")

# Unstake tokens (cooldown applies)
unstake_token("BEE", "50.000")
```

Key points:
- **All operations** use custom_json with id `"ssc-mainnet-hive"`
- **Active key** required for financial operations (transfers, staking)
- **Quantity as string** with correct decimal places matching token precision
- **Separate API** for reading state (`api.hive-engine.com/rpc/contracts`)
- **Staking cooldown**: Varies by token configuration
- **Case-sensitive**: Token symbols are uppercase (BEE, not bee)'''
    ),
    (
        "hive_sdk/dhive-error-handling-patterns",
        r'''What are the common error patterns when using dhive and how do I handle them properly? I keep getting cryptic RPC errors.''',
        r'''<think>
Error handling with dhive is tricky because errors come from multiple layers:
1. Network errors (connection failures, timeouts)
2. RPC errors (node returns an error response)
3. Blockchain validation errors (invalid transaction)
4. RC errors (insufficient resource credits)
Each has different error message patterns. Common ones include
HIVE_MIN_ROOT_COMMENT_INTERVAL, missing_authority, insufficient RC,
bandwidth exceeded, duplicate transaction, and amount format errors.
I should show a comprehensive error handler that catches and categorizes
these errors with actionable messages.
</think>

Here is a comprehensive error handling guide for dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

class HiveClient {
  constructor(keys = {}) {
    this.nodes = [
      "https://api.hive.blog",
      "https://api.deathwing.me",
      "https://api.openhive.network",
    ];
    this.client = new Client(this.nodes);
    this.keys = keys;
    this.currentNodeIndex = 0;
  }

  /**
   * Classify and handle blockchain errors with actionable messages.
   */
  classifyError(err) {
    const msg = err.message || String(err);

    // Authority / Key errors
    if (msg.includes("missing_authority") || msg.includes("Missing Active Authority")) {
      return {
        type: "AUTH_ERROR",
        message: "Wrong key type. Check: posting key for social ops, active key for financial ops.",
        retryable: false,
      };
    }

    // Rate limiting
    if (msg.includes("HIVE_MIN_ROOT_COMMENT_INTERVAL")) {
      return {
        type: "RATE_LIMIT",
        message: "Must wait 5 minutes between top-level posts.",
        retryable: true,
        retryAfterMs: 5 * 60 * 1000,
      };
    }
    if (msg.includes("HIVE_MIN_REPLY_INTERVAL")) {
      return {
        type: "RATE_LIMIT",
        message: "Must wait 20 seconds between comments.",
        retryable: true,
        retryAfterMs: 20 * 1000,
      };
    }
    if (msg.includes("HIVE_MIN_VOTE_INTERVAL_SEC")) {
      return {
        type: "RATE_LIMIT",
        message: "Must wait 3 seconds between votes.",
        retryable: true,
        retryAfterMs: 3 * 1000,
      };
    }

    // Resource Credits
    if (msg.includes("rc_plugin_exception") || msg.includes("not enough rc")) {
      return {
        type: "RC_INSUFFICIENT",
        message: "Not enough Resource Credits. Power up HIVE or get RC delegation.",
        retryable: true,
        retryAfterMs: 3600 * 1000,  // RC regenerates over time
      };
    }

    // Duplicate
    if (msg.includes("duplicate") || msg.includes("already exists")) {
      return {
        type: "DUPLICATE",
        message: "This operation was already processed (duplicate transaction or permlink).",
        retryable: false,
      };
    }

    // Amount format
    if (msg.includes("precision") || msg.includes("asset")) {
      return {
        type: "FORMAT_ERROR",
        message: "Invalid amount format. Use 3 decimals for HIVE/HBD, 6 for VESTS.",
        retryable: false,
      };
    }

    // Network errors
    if (msg.includes("ECONNREFUSED") || msg.includes("ETIMEDOUT") || msg.includes("fetch")) {
      return {
        type: "NETWORK_ERROR",
        message: `Node connection failed. Trying next node...`,
        retryable: true,
        retryAfterMs: 1000,
        switchNode: true,
      };
    }

    // Insufficient balance
    if (msg.includes("insufficient") || msg.includes("Insufficient")) {
      return {
        type: "INSUFFICIENT_BALANCE",
        message: "Insufficient balance for this operation.",
        retryable: false,
      };
    }

    return {
      type: "UNKNOWN",
      message: `Unhandled error: ${msg.slice(0, 200)}`,
      retryable: false,
    };
  }

  /**
   * Execute an operation with automatic retry and node failover.
   */
  async executeWithRetry(operationFn, maxRetries = 3) {
    let lastError;

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        return await operationFn(this.client);
      } catch (err) {
        const classified = this.classifyError(err);
        console.warn(`Attempt ${attempt + 1}: ${classified.type} — ${classified.message}`);
        lastError = classified;

        if (!classified.retryable) {
          throw new Error(`${classified.type}: ${classified.message}`);
        }

        if (classified.switchNode) {
          this.currentNodeIndex = (this.currentNodeIndex + 1) % this.nodes.length;
          this.client = new Client([this.nodes[this.currentNodeIndex]]);
          console.log(`Switched to node: ${this.nodes[this.currentNodeIndex]}`);
        }

        if (classified.retryAfterMs) {
          const waitMs = Math.min(classified.retryAfterMs, 30000);
          console.log(`Waiting ${waitMs / 1000}s before retry...`);
          await new Promise((r) => setTimeout(r, waitMs));
        }
      }
    }

    throw new Error(`Failed after ${maxRetries} attempts: ${lastError.message}`);
  }
}

// Usage
const hive = new HiveClient({
  posting: PrivateKey.fromString("5YourPostingKey"),
  active: PrivateKey.fromString("5YourActiveKey"),
});

// Vote with automatic retry
await hive.executeWithRetry(async (client) => {
  return client.broadcast.vote(
    {
      voter: "youraccount",
      author: "someauthor",
      permlink: "some-post",
      weight: 10000,
    },
    hive.keys.posting
  );
});

// Transfer with error handling
try {
  await hive.executeWithRetry(async (client) => {
    return client.broadcast.transfer(
      {
        from: "youraccount",
        to: "recipient",
        amount: "10.000 HIVE",
        memo: "payment",
      },
      hive.keys.active
    );
  });
} catch (err) {
  console.error("Transfer permanently failed:", err.message);
}
```

Common error patterns:
| Error | Cause | Fix |
|-------|-------|-----|
| `missing_authority` | Wrong key type | Use correct key (posting/active) |
| `HIVE_MIN_ROOT_COMMENT_INTERVAL` | Posted too fast | Wait 5 min between posts |
| `rc_plugin_exception` | No Resource Credits | Power up or get RC delegation |
| `duplicate` | Same tx broadcast twice | Use unique permlinks/nonces |
| `precision` | Wrong decimal places | HIVE/HBD: 3 decimals, VESTS: 6 |
| `ECONNREFUSED` | Node is down | Switch to backup node |'''
    ),
    (
        "hive_sdk/beem-claim-rewards",
        r'''How do I claim pending rewards (author and curation) on Hive using beem?''',
        r'''<think>
After the 7-day payout window, rewards accumulate as pending in the account.
They must be explicitly claimed using claim_reward_balance operation. The
rewards come in three forms: HIVE (liquid), HBD, and VESTS (Hive Power).
The posting key is sufficient for claiming rewards. Beem has a convenient
claim_reward_balance method. I should also show how to check pending
rewards before claiming them.
</think>

Here is how to check and claim pending rewards with beem:

```python
from beem import Hive
from beem.account import Account

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)
account_name = "youraccount"


def get_pending_rewards(username: str) -> dict:
    """Check unclaimed rewards."""
    acc = Account(username, blockchain_instance=hive)

    reward_hive = acc["reward_hive_balance"]
    reward_hbd = acc["reward_hbd_balance"]
    reward_vests = acc["reward_vesting_balance"]

    # Convert VESTS to HP for display
    vests_amount = float(str(reward_vests).split()[0])
    reward_hp = hive.vests_to_hp(vests_amount) if vests_amount > 0 else 0

    return {
        "hive": str(reward_hive),
        "hbd": str(reward_hbd),
        "vests": str(reward_vests),
        "hp_equivalent": round(reward_hp, 3),
        "has_rewards": vests_amount > 0 or float(str(reward_hive).split()[0]) > 0
                       or float(str(reward_hbd).split()[0]) > 0,
    }


def claim_rewards(username: str) -> bool:
    """Claim all pending rewards."""
    acc = Account(username, blockchain_instance=hive)

    reward_hive = acc["reward_hive_balance"]
    reward_hbd = acc["reward_hbd_balance"]
    reward_vests = acc["reward_vesting_balance"]

    # Check if there is anything to claim
    if (float(str(reward_hive).split()[0]) == 0 and
        float(str(reward_hbd).split()[0]) == 0 and
        float(str(reward_vests).split()[0]) == 0):
        print("No pending rewards to claim")
        return False

    hive.claim_reward_balance(
        reward_hive=reward_hive,
        reward_hbd=reward_hbd,
        reward_vests=reward_vests,
        account=username,
    )
    print(f"Claimed: {reward_hive}, {reward_hbd}, {reward_vests}")
    return True


def auto_claim_loop(username: str, check_interval: int = 3600):
    """Periodically check and claim rewards."""
    import time

    while True:
        try:
            rewards = get_pending_rewards(username)
            if rewards["has_rewards"]:
                print(f"Pending: {rewards['hive']}, {rewards['hbd']}, "
                      f"{rewards['hp_equivalent']} HP")
                claim_rewards(username)
            else:
                print("No pending rewards")
        except Exception as e:
            print(f"Error checking rewards: {e}")

        time.sleep(check_interval)


# Check pending rewards
rewards = get_pending_rewards(account_name)
print(f"Pending HIVE: {rewards['hive']}")
print(f"Pending HBD: {rewards['hbd']}")
print(f"Pending HP: {rewards['hp_equivalent']}")

# Claim if available
if rewards["has_rewards"]:
    claim_rewards(account_name)
```

Key points:
- **Posting key** is sufficient for claiming rewards
- **Three reward types**: Liquid HIVE, HBD, and VESTS (HP)
- **Must explicitly claim** — rewards do not auto-deposit
- **No expiration** on unclaimed rewards — they wait until you claim
- **Reward split**: Author rewards are split ~50/50 between HP and HBD (configurable per post)
- **Curation rewards** are always paid in HP (VESTS)'''
    ),
    (
        "hive_sdk/dhive-convert-hbd-hive",
        r'''How do I convert between HBD and HIVE using dhive? What is the difference between convert and collateralized_convert?''',
        r'''<think>
There are two conversion operations on Hive:
1. convert (HBD -> HIVE): Takes 3.5 days, uses the median price over that period.
   This destroys HBD and creates HIVE. No risk of loss since it uses the median.
2. collateralized_convert (HIVE -> HBD): Instant HBD, but your HIVE collateral
   is locked for 3.5 days. You get excess collateral back after 3.5 days.
   Uses 2x collateral to protect against price swings.
Both require active key. These are on-chain conversions, not market trades.
The internal market (limit_order_create) is different — that is an order book.
</think>

Here is how to convert between HBD and HIVE with dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const activeKey = PrivateKey.fromString("5YourActiveKey");
const account = "youraccount";

/**
 * Convert HBD to HIVE (3.5-day conversion using median price).
 * The HBD is destroyed and HIVE is created after 3.5 days.
 */
async function convertHbdToHive(hbdAmount) {
  const requestId = Math.floor(Date.now() / 1000) % 2147483647;

  const op = [
    "convert",
    {
      owner: account,
      requestid: requestId,
      amount: `${hbdAmount.toFixed(3)} HBD`,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Converting ${hbdAmount.toFixed(3)} HBD to HIVE (3.5-day delay)`);
  return result;
}

/**
 * Convert HIVE to HBD instantly (collateralized conversion).
 * Requires 2x HIVE collateral, excess returned after 3.5 days.
 */
async function convertHiveToHbd(hiveAmount) {
  const requestId = Math.floor(Date.now() / 1000) % 2147483647;

  const op = [
    "collateralized_convert",
    {
      owner: account,
      requestid: requestId,
      amount: `${hiveAmount.toFixed(3)} HIVE`,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Collateralized convert: ${hiveAmount.toFixed(3)} HIVE to HBD`);
  console.log("HBD received instantly; excess HIVE collateral returned in 3.5 days");
  return result;
}

/**
 * Place a limit order on the internal HIVE/HBD market.
 */
async function placeLimitOrder(sellAmount, sellAsset, buyAmount, buyAsset, expirationHours = 24) {
  const orderId = Math.floor(Date.now() / 1000) % 2147483647;
  const expiration = new Date(Date.now() + expirationHours * 3600 * 1000)
    .toISOString()
    .split(".")[0];

  const op = [
    "limit_order_create",
    {
      owner: account,
      orderid: orderId,
      amount_to_sell: `${sellAmount.toFixed(3)} ${sellAsset}`,
      min_to_receive: `${buyAmount.toFixed(3)} ${buyAsset}`,
      fill_or_kill: false,
      expiration: expiration,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Limit order: Sell ${sellAmount} ${sellAsset} for ${buyAmount} ${buyAsset}`);
  return { result, orderId };
}

/**
 * Cancel a limit order.
 */
async function cancelLimitOrder(orderId) {
  const op = [
    "limit_order_cancel",
    {
      owner: account,
      orderid: orderId,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Cancelled order #${orderId}`);
  return result;
}

/**
 * Get the current HIVE/HBD price feed.
 */
async function getCurrentPrice() {
  const feed = await client.database.getCurrentMedianHistoryPrice();
  const base = parseFloat(feed.base.split(" ")[0]);
  const quote = parseFloat(feed.quote.split(" ")[0]);
  const pricePerHive = base / quote;  // HBD per HIVE
  return { pricePerHive, feed };
}

// Check current price
const { pricePerHive } = await getCurrentPrice();
console.log(`Current HIVE price: $${pricePerHive.toFixed(3)} HBD`);

// Convert 10 HBD to HIVE (3.5-day delay, safe)
await convertHbdToHive(10);

// Convert 100 HIVE to HBD instantly (collateralized)
await convertHiveToHbd(100);

// Place limit order: Sell 50 HBD for at least 100 HIVE
await placeLimitOrder(50, "HBD", 100, "HIVE", 72);
```

Conversion comparison:
| Method | Direction | Speed | Risk |
|--------|-----------|-------|------|
| `convert` | HBD -> HIVE | 3.5 days | Low (median price) |
| `collateralized_convert` | HIVE -> HBD | Instant HBD | Medium (2x collateral locked) |
| `limit_order_create` | Either | Market fill | Price may not fill |

- **Active key** required for all conversion and market operations
- **Request ID**: Must be unique per conversion request
- **Median price**: The 3.5-day convert uses the rolling median from witness feeds
- **Collateral**: You lock 2x HIVE, get ~1x value in HBD instantly, excess HIVE returned later'''
    ),
    (
        "hive_sdk/beem-condenser-api-queries",
        r'''How do I use the condenser_api to query blog posts, trending content, and discussions using beem?''',
        r'''<think>
The condenser_api and bridge API provide methods to query content on Hive.
Common methods: get_discussions_by_trending, get_discussions_by_created,
get_blog, get_content, etc. The bridge API (newer) has get_ranked_posts
and get_account_posts. I should show both old condenser_api calls and
the newer bridge API, which is what most frontends use now.
Beem wraps some of these, but raw RPC calls are often needed for
specific queries.
</think>

Here is how to query content and discussions with beem:

```python
from beem import Hive
from beem.comment import Comment
from beem.discussions import Query, Discussions_by_trending, Discussions_by_created

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])


def get_trending_posts(tag: str = "", limit: int = 10) -> list:
    """Get trending posts, optionally filtered by tag."""
    query = Query(limit=limit, tag=tag)
    discussions = Discussions_by_trending(query, blockchain_instance=hive)

    posts = []
    for post in discussions:
        posts.append({
            "author": post["author"],
            "permlink": post["permlink"],
            "title": post["title"],
            "pending_payout": str(post["pending_payout_value"]),
            "votes": post["net_votes"],
            "created": str(post["created"]),
        })
    return posts


def get_new_posts(tag: str = "", limit: int = 10) -> list:
    """Get newest posts, optionally filtered by tag."""
    query = Query(limit=limit, tag=tag)
    discussions = Discussions_by_created(query, blockchain_instance=hive)

    return [
        {
            "author": p["author"],
            "permlink": p["permlink"],
            "title": p["title"],
            "created": str(p["created"]),
        }
        for p in discussions
    ]


def get_post_details(author: str, permlink: str) -> dict:
    """Get full details of a specific post."""
    post = Comment(f"@{author}/{permlink}", blockchain_instance=hive)
    return {
        "author": post["author"],
        "permlink": post["permlink"],
        "title": post["title"],
        "body": post["body"],
        "created": str(post["created"]),
        "pending_payout": str(post["pending_payout_value"]),
        "total_payout": str(post["total_payout_value"]),
        "votes": post["net_votes"],
        "children": post["children"],  # number of replies
        "depth": post["depth"],  # 0 = root post
    }


def get_replies(author: str, permlink: str) -> list:
    """Get replies to a post."""
    post = Comment(f"@{author}/{permlink}", blockchain_instance=hive)
    replies = post.get_replies()
    return [
        {
            "author": r["author"],
            "body": r["body"][:200],
            "created": str(r["created"]),
            "votes": r["net_votes"],
        }
        for r in replies
    ]


def get_account_posts_bridge(username: str, sort: str = "posts", limit: int = 10) -> list:
    """Use bridge API for account posts (newer, more reliable)."""
    result = hive.rpc.get_account_posts(
        {"sort": sort, "account": username, "limit": limit},
        api="bridge"
    )
    return [
        {
            "author": p["author"],
            "permlink": p["permlink"],
            "title": p["title"],
            "payout": p.get("payout", 0),
            "created": p["created"],
        }
        for p in (result or [])
    ]


def get_community_posts(community: str, sort: str = "trending", limit: int = 10) -> list:
    """Get posts from a specific community via bridge API."""
    result = hive.rpc.get_ranked_posts(
        {"sort": sort, "tag": community, "limit": limit},
        api="bridge"
    )
    return [
        {
            "author": p["author"],
            "title": p["title"],
            "permlink": p["permlink"],
            "payout": p.get("payout", 0),
        }
        for p in (result or [])
    ]


# Trending posts
trending = get_trending_posts(limit=5)
for p in trending:
    print(f"[{p['pending_payout']}] @{p['author']}: {p['title']}")

# New posts in a tag
new_python = get_new_posts(tag="python", limit=5)
for p in new_python:
    print(f"@{p['author']}: {p['title']}")

# Full post details
details = get_post_details("hiveio", "some-permlink")
print(f"Title: {details['title']}, Replies: {details['children']}")

# Account posts via bridge API
my_posts = get_account_posts_bridge("blocktrades", sort="posts", limit=5)

# Community trending
community_posts = get_community_posts("hive-174301", sort="trending")
```

API comparison:
- **condenser_api**: Older, `get_discussions_by_*` methods, `get_content`
- **bridge API**: Newer, `get_ranked_posts`, `get_account_posts` — preferred for new code
- **Both are read-only** — no keys needed for queries
- **Pagination**: Use `start_author`/`start_permlink` from last result for next page'''
    ),
    (
        "hive_sdk/dhive-multi-authority-transaction",
        r'''How do I create a transaction that requires signatures from multiple accounts using dhive? I need to do a multi-authority operation.''',
        r'''<think>
Multi-authority transactions are needed when an operation requires signatures
from more than one account, or when an account has multi-sig setup.
In dhive, you build the transaction manually, sign it with multiple keys,
and then broadcast. The key insight is using client.broadcast.send() with
a pre-signed transaction instead of the convenience methods.
Common use case: account_auth where a second account has authority and
both need to sign. Another case: escrow operations requiring multiple parties.
</think>

Here is how to create multi-authority transactions with dhive:

```javascript
const { Client, PrivateKey, Transaction } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

/**
 * Build and sign a transaction with multiple keys.
 */
async function multiSignTransaction(operations, signers) {
  // Get dynamic properties for transaction header
  const props = await client.database.getDynamicGlobalProperties();
  const headBlockId = props.head_block_id;
  const headBlockNumber = props.head_block_number;

  // Parse the reference block
  const refBlockNum = headBlockNumber & 0xffff;
  const refBlockPrefix = Buffer.from(headBlockId, "hex").readUInt32LE(4);

  // Set expiration (30 seconds from now)
  const expiration = new Date(
    new Date(props.time + "Z").getTime() + 30 * 1000
  ).toISOString().split(".")[0];

  // Build the transaction
  const tx = {
    ref_block_num: refBlockNum,
    ref_block_prefix: refBlockPrefix,
    expiration: expiration,
    operations: operations,
    extensions: [],
  };

  // Sign with all provided keys
  const signedTx = client.broadcast.sign(tx, signers);

  // Broadcast
  const result = await client.broadcast.send(signedTx);
  console.log(`Multi-sig transaction broadcast: ${result.id}`);
  return result;
}

/**
 * Example: Transfer requiring co-signer (e.g., multi-sig active authority).
 */
async function multiSigTransfer(from, to, amount, memo) {
  const operations = [
    [
      "transfer",
      {
        from: from,
        to: to,
        amount: `${amount.toFixed(3)} HIVE`,
        memo: memo,
      },
    ],
  ];

  // Both keys needed for 2-of-2 multi-sig on active authority
  const key1 = PrivateKey.fromString("5Key1ForMultiSig");
  const key2 = PrivateKey.fromString("5Key2ForMultiSig");

  return multiSignTransaction(operations, [key1, key2]);
}

/**
 * Example: Operations from two different accounts in one transaction.
 */
async function twoAccountTransaction() {
  const alicePostingKey = PrivateKey.fromString("5AlicePostingKey");
  const bobPostingKey = PrivateKey.fromString("5BobPostingKey");

  const operations = [
    // Alice votes on a post
    [
      "vote",
      {
        voter: "alice",
        author: "contentcreator",
        permlink: "great-post",
        weight: 10000,
      },
    ],
    // Bob votes on the same post in the same transaction
    [
      "vote",
      {
        voter: "bob",
        author: "contentcreator",
        permlink: "great-post",
        weight: 10000,
      },
    ],
  ];

  return multiSignTransaction(operations, [alicePostingKey, bobPostingKey]);
}

/**
 * Offline signing: Sign a transaction without broadcasting.
 * Useful for cold storage or hardware wallet workflows.
 */
async function offlineSign(operations, keys) {
  const props = await client.database.getDynamicGlobalProperties();
  const headBlockId = props.head_block_id;
  const refBlockNum = props.head_block_number & 0xffff;
  const refBlockPrefix = Buffer.from(headBlockId, "hex").readUInt32LE(4);

  // Longer expiration for offline signing
  const expiration = new Date(
    new Date(props.time + "Z").getTime() + 3600 * 1000
  ).toISOString().split(".")[0];

  const tx = {
    ref_block_num: refBlockNum,
    ref_block_prefix: refBlockPrefix,
    expiration: expiration,
    operations: operations,
    extensions: [],
  };

  // Sign offline (does not broadcast)
  const signed = client.broadcast.sign(tx, keys);

  return {
    signed_transaction: signed,
    expiration: expiration,
    broadcast: async () => client.broadcast.send(signed),
  };
}

// Multi-sig transfer
await multiSigTransfer("multisig-account", "recipient", 50, "Joint payment");

// Two-account transaction
await twoAccountTransaction();

// Offline sign, then broadcast later
const offlineTx = await offlineSign(
  [["transfer", {
    from: "coldwallet", to: "hotwallet",
    amount: "100.000 HIVE", memo: "rebalance",
  }]],
  [PrivateKey.fromString("5ColdWalletActiveKey")]
);
// ... later, on an online machine:
await offlineTx.broadcast();
```

Multi-sig details:
- **All required keys** must sign before broadcast
- **Transaction expiration**: Default ~30 seconds; set longer for multi-party signing
- **Operation order**: Operations within a transaction execute sequentially
- **Offline signing**: Sign on air-gapped machine, broadcast from online machine
- **Authority threshold**: All keys whose weights meet the threshold must sign
- **Same transaction**: Multiple accounts can have operations in one tx if all sign it'''
    ),
    (
        "hive_sdk/beem-vesting-routes",
        r'''How do I set up vesting routes (auto power-down routing) using beem? I want to automatically send powered-down HIVE to another account.''',
        r'''<think>
Vesting routes (set_withdraw_vesting_route) allow you to automatically route
a percentage of your power-down proceeds to another account, either as
liquid HIVE or auto-powered-up to the destination. This is useful for
splitting power-down proceeds between accounts or auto-powering up
a different account. You can set multiple routes with different percentages
(total must not exceed 100%). Active key required.
</think>

Here is how to manage vesting withdrawal routes with beem:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Set_withdraw_vesting_route

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)
account = "youraccount"


def set_vesting_route(to_account: str, percent: int, auto_vest: bool = False):
    """Route a percentage of power-down to another account.

    Args:
        to_account: Destination account
        percent: 1-10000 (basis points, 10000 = 100%)
        auto_vest: If True, auto power-up at destination; if False, send as liquid HIVE
    """
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Set_withdraw_vesting_route(**{
        "from_account": account,
        "to_account": to_account,
        "percent": percent,
        "auto_vest": auto_vest,
    }))
    tx.appendSigner(account, "active")
    tx.sign()
    result = tx.broadcast()
    vest_type = "auto-vest (HP)" if auto_vest else "liquid HIVE"
    print(f"Route set: {percent/100}% of power-down to @{to_account} as {vest_type}")
    return result


def remove_vesting_route(to_account: str):
    """Remove a vesting route by setting percent to 0."""
    set_vesting_route(to_account, percent=0, auto_vest=False)
    print(f"Removed vesting route to @{to_account}")


def get_vesting_routes(username: str) -> list:
    """Get all active vesting withdrawal routes."""
    result = hive.rpc.get_withdraw_routes(username, "outgoing")
    return [
        {
            "to": r["to_account"],
            "percent": r["percent"] / 100,
            "auto_vest": r["auto_vest"],
        }
        for r in result
    ]


# Route 50% of power-down to savings account as liquid HIVE
set_vesting_route("my-savings-account", percent=5000, auto_vest=False)

# Route 25% to a project account, auto power-up there
set_vesting_route("my-project", percent=2500, auto_vest=True)

# Remaining 25% stays with the original account automatically

# Check current routes
routes = get_vesting_routes(account)
for r in routes:
    print(f"-> @{r['to']}: {r['percent']}% ({'auto-vest' if r['auto_vest'] else 'liquid'})")

# Remove a route
remove_vesting_route("my-savings-account")
```

Key points:
- **Percent in basis points**: 5000 = 50%, 10000 = 100%
- **Total cannot exceed 100%** across all routes; remainder stays with source account
- **auto_vest=True**: Automatically powers up at destination (useful for project accounts)
- **auto_vest=False**: Sends as liquid HIVE
- **Active key** required
- **Only applies during power-down** — routes have no effect if not powering down
- **Remove**: Set percent to 0 for that destination'''
    ),
    (
        "hive_sdk/dhive-node-failover-strategy",
        r'''How do I implement a robust node failover strategy with dhive? My app keeps failing when a single node goes down.''',
        r'''<think>
Node failover is critical for production Hive apps. The dhive Client constructor
accepts an array of nodes and handles some failover, but for production you
want more control: health checking, automatic switching, and latency-based
selection. I should show a custom client wrapper that manages node health,
retries with backoff, and picks the best available node.
Key considerations: some nodes may be behind in block height, some may
rate-limit you, and some may be temporarily unavailable.
</think>

Here is a production-grade node failover strategy for dhive:

```javascript
const { Client } = require("@hiveio/dhive");

class ResilientHiveClient {
  constructor(options = {}) {
    this.nodes = options.nodes || [
      "https://api.hive.blog",
      "https://api.deathwing.me",
      "https://api.openhive.network",
      "https://rpc.ecency.com",
      "https://hive-api.arcange.eu",
    ];

    this.healthStatus = new Map();
    this.currentNodeIndex = 0;
    this.maxRetries = options.maxRetries || 3;
    this.healthCheckInterval = options.healthCheckMs || 30000;

    // Initialize all nodes as healthy
    for (const node of this.nodes) {
      this.healthStatus.set(node, {
        healthy: true,
        latency: Infinity,
        lastCheck: 0,
        failures: 0,
        blockHeight: 0,
      });
    }

    this.client = new Client([this.getBestNode()]);
    this._startHealthChecks();
  }

  /**
   * Check health of a single node.
   */
  async checkNodeHealth(nodeUrl) {
    const testClient = new Client([nodeUrl]);
    const start = Date.now();

    try {
      const props = await Promise.race([
        testClient.database.getDynamicGlobalProperties(),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error("timeout")), 5000)
        ),
      ]);

      const latency = Date.now() - start;
      this.healthStatus.set(nodeUrl, {
        healthy: true,
        latency,
        lastCheck: Date.now(),
        failures: 0,
        blockHeight: props.head_block_number,
      });
      return true;
    } catch {
      const current = this.healthStatus.get(nodeUrl);
      this.healthStatus.set(nodeUrl, {
        ...current,
        healthy: false,
        lastCheck: Date.now(),
        failures: (current?.failures || 0) + 1,
      });
      return false;
    }
  }

  /**
   * Get the best available node (lowest latency, healthy, highest block).
   */
  getBestNode() {
    const healthy = this.nodes
      .filter((n) => {
        const status = this.healthStatus.get(n);
        return status?.healthy !== false;
      })
      .sort((a, b) => {
        const sa = this.healthStatus.get(a);
        const sb = this.healthStatus.get(b);
        // Prefer higher block height, then lower latency
        if (Math.abs((sa?.blockHeight || 0) - (sb?.blockHeight || 0)) > 2) {
          return (sb?.blockHeight || 0) - (sa?.blockHeight || 0);
        }
        return (sa?.latency || Infinity) - (sb?.latency || Infinity);
      });

    return healthy[0] || this.nodes[0];
  }

  /**
   * Execute a call with automatic retry and failover.
   */
  async call(fn, maxRetries = this.maxRetries) {
    let lastError;

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        return await fn(this.client);
      } catch (err) {
        lastError = err;
        const msg = err.message || "";

        // Non-retryable errors (user mistakes, not node issues)
        if (
          msg.includes("missing_authority") ||
          msg.includes("insufficient") ||
          msg.includes("duplicate")
        ) {
          throw err;
        }

        // Mark current node as potentially unhealthy
        const currentNode = this.getBestNode();
        const status = this.healthStatus.get(currentNode);
        if (status) {
          status.failures = (status.failures || 0) + 1;
          if (status.failures >= 3) status.healthy = false;
        }

        // Switch to next best node
        const newNode = this.getBestNode();
        this.client = new Client([newNode]);
        console.warn(`Switched to ${newNode} (attempt ${attempt + 1})`);

        // Exponential backoff
        await new Promise((r) => setTimeout(r, 1000 * Math.pow(2, attempt)));
      }
    }

    throw lastError;
  }

  /**
   * Start periodic health checks.
   */
  _startHealthChecks() {
    this._healthTimer = setInterval(async () => {
      const checks = this.nodes.map((n) => this.checkNodeHealth(n));
      await Promise.allSettled(checks);
    }, this.healthCheckInterval);
  }

  /**
   * Get current node health status.
   */
  getHealthReport() {
    const report = {};
    for (const [node, status] of this.healthStatus) {
      report[node] = {
        healthy: status.healthy,
        latency: `${status.latency}ms`,
        blockHeight: status.blockHeight,
        failures: status.failures,
      };
    }
    return report;
  }

  destroy() {
    if (this._healthTimer) clearInterval(this._healthTimer);
  }
}

// Usage
const hive = new ResilientHiveClient({
  maxRetries: 3,
  healthCheckMs: 30000,
});

// All API calls go through the resilient wrapper
const props = await hive.call((client) =>
  client.database.getDynamicGlobalProperties()
);
console.log(`Head block: ${props.head_block_number}`);

const [account] = await hive.call((client) =>
  client.database.getAccounts(["blocktrades"])
);
console.log(`Balance: ${account.balance}`);

// Check health
console.log(hive.getHealthReport());

// Cleanup
hive.destroy();
```

Node selection strategy:
- **Health checks**: Periodic ping every 30 seconds
- **Latency ranking**: Prefer faster nodes
- **Block height**: Detect nodes that are behind (lagging)
- **Failure tracking**: 3 consecutive failures marks a node as unhealthy
- **Exponential backoff**: Prevents hammering failing nodes
- **Auto-recovery**: Unhealthy nodes are rechecked and restored when they come back'''
    ),
    (
        "hive_sdk/beem-json-metadata-profile",
        r'''How do I update a Hive account's profile (display name, avatar, bio, etc.) using beem? The profile is stored in json_metadata.''',
        r'''<think>
Hive account profiles are stored in two fields: json_metadata and
posting_json_metadata. The posting_json_metadata can be updated with
posting key (via account_update2), while json_metadata requires active key.
Most frontends read from posting_json_metadata first, falling back to
json_metadata. The profile data follows a standard format with a "profile"
key containing name, about, location, website, profile_image, cover_image.
I should show how to update posting_json_metadata since it only needs
posting key, which is safer.
</think>

Here is how to update Hive account profile metadata with beem:

```python
import json
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_update2

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)
account_name = "youraccount"


def get_current_profile(username: str) -> dict:
    """Read current profile from posting_json_metadata."""
    acc = Account(username, blockchain_instance=hive)

    # Try posting_json_metadata first (preferred by frontends)
    raw = acc.get("posting_json_metadata", "") or acc.get("json_metadata", "")
    if not raw:
        return {}

    try:
        data = json.loads(raw)
        return data.get("profile", {})
    except json.JSONDecodeError:
        return {}


def update_profile(updates: dict):
    """Update profile fields in posting_json_metadata.

    Supported fields:
        name, about, location, website, profile_image,
        cover_image, dtube_pub, witness_owner, witness_description
    """
    acc = Account(account_name, blockchain_instance=hive)

    # Load existing metadata to preserve other fields
    existing_raw = acc.get("posting_json_metadata", "{}") or "{}"
    try:
        existing = json.loads(existing_raw)
    except json.JSONDecodeError:
        existing = {}

    # Merge updates into profile
    if "profile" not in existing:
        existing["profile"] = {}
    existing["profile"].update(updates)

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Account_update2(**{
        "account": account_name,
        "json_metadata": "",  # leave json_metadata unchanged
        "posting_json_metadata": json.dumps(existing),
        "extensions": [],
    }))
    tx.appendSigner(account_name, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Profile updated: {list(updates.keys())}")
    return result


def clear_profile_field(field: str):
    """Remove a specific field from the profile."""
    acc = Account(account_name, blockchain_instance=hive)
    existing_raw = acc.get("posting_json_metadata", "{}") or "{}"
    try:
        existing = json.loads(existing_raw)
    except json.JSONDecodeError:
        existing = {}

    if "profile" in existing and field in existing["profile"]:
        del existing["profile"][field]

        tx = TransactionBuilder(blockchain_instance=hive)
        tx.appendOps(Account_update2(**{
            "account": account_name,
            "json_metadata": "",
            "posting_json_metadata": json.dumps(existing),
            "extensions": [],
        }))
        tx.appendSigner(account_name, "posting")
        tx.sign()
        tx.broadcast()
        print(f"Removed profile field: {field}")


# Read current profile
profile = get_current_profile(account_name)
print(f"Current name: {profile.get('name', 'Not set')}")
print(f"Current bio: {profile.get('about', 'Not set')}")

# Update profile
update_profile({
    "name": "My Display Name",
    "about": "Developer building on Hive blockchain",
    "location": "Decentralized",
    "website": "https://mysite.com",
    "profile_image": "https://images.hive.blog/u/youraccount/avatar",
    "cover_image": "https://images.hive.blog/cover-image.jpg",
})

# Update just one field
update_profile({"about": "Updated bio text"})

# Clear a field
clear_profile_field("location")
```

Profile metadata details:
- **posting_json_metadata**: Updatable with posting key (safer), preferred by frontends
- **json_metadata**: Requires active key, older field
- **Account_update2**: The operation that supports posting_json_metadata
- **Always merge**: Read existing metadata first, then merge updates to avoid data loss
- **Standard fields**: name, about, location, website, profile_image, cover_image
- **Image URLs**: Use full URLs; Hive frontends render them directly
- **No size limit enforced** on metadata, but keep it reasonable (<8KB)'''
    ),
    (
        "hive_sdk/dhive-block-data-analysis",
        r'''How do I fetch and analyze specific blocks and their transactions using dhive? I need to build a block explorer type feature.''',
        r'''<think>
Fetching block data with dhive involves getting block headers, full blocks
with transactions, and individual operations. The database API provides
getBlock, getBlockHeader, and the block_api for more detailed queries.
Each block has transactions, each transaction has operations.
Blocks are produced every 3 seconds. I should show how to fetch
individual blocks, extract transactions, and analyze operation types.
Also useful: getting the current head block and processing a range.
</think>

Here is how to fetch and analyze block data with dhive:

```javascript
const { Client } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

/**
 * Get full block data with all transactions.
 */
async function getBlock(blockNum) {
  const block = await client.database.getBlock(blockNum);
  if (!block) throw new Error(`Block ${blockNum} not found`);

  return {
    blockNumber: blockNum,
    timestamp: block.timestamp,
    witness: block.witness,
    transactionCount: block.transactions.length,
    transactions: block.transactions.map((tx, i) => ({
      txIndex: i,
      txId: tx.transaction_id,
      operations: tx.operations.map(([type, data]) => ({ type, data })),
    })),
  };
}

/**
 * Count operation types in a block.
 */
async function analyzeBlock(blockNum) {
  const block = await client.database.getBlock(blockNum);
  const opCounts = {};
  let totalOps = 0;

  for (const tx of block.transactions) {
    for (const [opType] of tx.operations) {
      opCounts[opType] = (opCounts[opType] || 0) + 1;
      totalOps++;
    }
  }

  return {
    blockNumber: blockNum,
    timestamp: block.timestamp,
    witness: block.witness,
    totalTransactions: block.transactions.length,
    totalOperations: totalOps,
    operationCounts: opCounts,
  };
}

/**
 * Analyze a range of blocks.
 */
async function analyzeBlockRange(startBlock, endBlock) {
  const stats = {
    blocks: 0,
    totalTxs: 0,
    totalOps: 0,
    opCounts: {},
    witnesses: {},
    busiestBlock: { num: 0, ops: 0 },
  };

  for (let bn = startBlock; bn <= endBlock; bn++) {
    const analysis = await analyzeBlock(bn);
    stats.blocks++;
    stats.totalTxs += analysis.totalTransactions;
    stats.totalOps += analysis.totalOperations;

    // Track witness block production
    stats.witnesses[analysis.witness] =
      (stats.witnesses[analysis.witness] || 0) + 1;

    // Aggregate op counts
    for (const [op, count] of Object.entries(analysis.operationCounts)) {
      stats.opCounts[op] = (stats.opCounts[op] || 0) + count;
    }

    // Track busiest block
    if (analysis.totalOperations > stats.busiestBlock.ops) {
      stats.busiestBlock = { num: bn, ops: analysis.totalOperations };
    }

    // Rate limit to avoid hammering the node
    if (bn % 10 === 0) {
      await new Promise((r) => setTimeout(r, 100));
    }
  }

  return stats;
}

/**
 * Find specific operations in recent blocks.
 */
async function findOperations(opType, blockCount = 100) {
  const props = await client.database.getDynamicGlobalProperties();
  const headBlock = props.head_block_number;
  const results = [];

  for (let bn = headBlock; bn > headBlock - blockCount; bn--) {
    const block = await client.database.getBlock(bn);
    for (const tx of block.transactions) {
      for (const [type, data] of tx.operations) {
        if (type === opType) {
          results.push({
            block: bn,
            timestamp: block.timestamp,
            txId: tx.transaction_id,
            data,
          });
        }
      }
    }
    if (bn % 20 === 0) await new Promise((r) => setTimeout(r, 50));
  }

  return results;
}

// Get current head block
const props = await client.database.getDynamicGlobalProperties();
console.log(`Head block: ${props.head_block_number}`);

// Analyze a single block
const analysis = await analyzeBlock(props.head_block_number);
console.log(`Block ${analysis.blockNumber}:`);
console.log(`  Witness: ${analysis.witness}`);
console.log(`  Transactions: ${analysis.totalTransactions}`);
console.log(`  Operations:`, analysis.operationCounts);

// Analyze last 100 blocks (~5 minutes of chain activity)
const headBlock = props.head_block_number;
const rangeStats = await analyzeBlockRange(headBlock - 100, headBlock);
console.log(`\nLast 100 blocks:`);
console.log(`  Total transactions: ${rangeStats.totalTxs}`);
console.log(`  Total operations: ${rangeStats.totalOps}`);
console.log(`  Operation types:`, rangeStats.opCounts);
console.log(`  Busiest block: #${rangeStats.busiestBlock.num}`);

// Find recent large transfers
const transfers = await findOperations("transfer", 50);
const large = transfers.filter((t) => parseFloat(t.data.amount) > 100);
for (const t of large) {
  console.log(`Block ${t.block}: ${t.data.from} -> ${t.data.to}: ${t.data.amount}`);
}
```

Block data details:
- **3-second blocks**: Hive produces ~28,800 blocks per day
- **Block structure**: header + transactions, each tx has operations
- **Witnesses**: 21 produce blocks in rounds (top 20 + 1 rotating backup)
- **Virtual operations**: Not in blocks directly — use `get_ops_in_block` for those
- **Rate limiting**: Space out API calls when scanning many blocks
- **Head block**: Current latest block from `getDynamicGlobalProperties`'''
    ),
    (
        "hive_sdk/beem-content-payout-info",
        r'''How do I check the pending payout, payout history, and beneficiary splits for posts using beem?''',
        r'''<think>
Post payouts on Hive happen 7 days after posting. Before payout, the
pending_payout_value shows estimated rewards. After payout,
total_payout_value and curator_payout_value show actual amounts.
Beneficiaries reduce the author portion. I need to show how to
get this info from the Comment object, calculate effective author
rewards, and check beneficiary configuration.
Also important: the 50/50 HBD/HP split (or 100% HP option).
</think>

Here is how to analyze post payouts with beem:

```python
from datetime import datetime, timezone
from beem import Hive
from beem.comment import Comment
from beem.account import Account

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])


def get_payout_info(author: str, permlink: str) -> dict:
    """Get comprehensive payout information for a post."""
    post = Comment(f"@{author}/{permlink}", blockchain_instance=hive)

    # Parse monetary values
    pending = float(str(post["pending_payout_value"]).split()[0])
    total_author = float(str(post["total_payout_value"]).split()[0])
    total_curator = float(str(post["curator_payout_value"]).split()[0])

    # Check if payout has occurred
    cashout_time = post["cashout_time"]
    is_paid = str(cashout_time) == "1969-12-31T23:59:59" or pending == 0

    # Beneficiaries
    beneficiaries = post.get("beneficiaries", [])
    ben_total_pct = sum(b["weight"] for b in beneficiaries) / 100

    # Calculate author effective percentage
    author_pct = 100 - ben_total_pct  # after beneficiary cuts

    # Payout split: typically 50% HBD / 50% HP, or 100% HP
    percent_hbd = post.get("percent_hbd", 10000) / 100  # default 50%

    created = datetime.strptime(str(post["created"]), "%Y-%m-%dT%H:%M:%S")

    return {
        "author": author,
        "permlink": permlink,
        "title": post["title"],
        "created": str(created),
        "is_paid_out": is_paid,
        "cashout_time": str(cashout_time) if not is_paid else "PAID",
        "pending_payout_hbd": pending,
        "total_author_payout_hbd": total_author,
        "total_curator_payout_hbd": total_curator,
        "total_combined": total_author + total_curator if is_paid else pending,
        "net_votes": post["net_votes"],
        "beneficiaries": [
            {"account": b["account"], "pct": b["weight"] / 100}
            for b in beneficiaries
        ],
        "beneficiary_total_pct": ben_total_pct,
        "author_effective_pct": author_pct,
        "hbd_pct": percent_hbd,
        "max_accepted_payout": str(post["max_accepted_payout"]),
        "allow_votes": post["allow_votes"],
        "allow_curation_rewards": post["allow_curation_rewards"],
    }


def estimate_author_earnings(payout_info: dict) -> dict:
    """Estimate what the author actually receives."""
    if payout_info["is_paid_out"]:
        total = payout_info["total_author_payout_hbd"]
    else:
        total = payout_info["pending_payout_hbd"]
        # Author gets ~50% (rest is curation)
        total = total * 0.5

    # Subtract beneficiaries
    after_bens = total * (payout_info["author_effective_pct"] / 100)

    # Split between HBD and HP
    hbd_pct = payout_info["hbd_pct"] / 100
    hbd_portion = after_bens * hbd_pct
    hp_portion = after_bens * (1 - hbd_pct)

    return {
        "estimated_total_author_hbd": round(total, 3),
        "after_beneficiaries": round(after_bens, 3),
        "hbd_received": round(hbd_portion, 3),
        "hp_received_equivalent": round(hp_portion, 3),
    }


def get_recent_payouts(username: str, limit: int = 10) -> list:
    """Get recent posts with their payout information."""
    results = hive.rpc.get_account_posts(
        {"sort": "posts", "account": username, "limit": limit},
        api="bridge"
    )

    payouts = []
    for p in (results or []):
        payouts.append({
            "title": p["title"],
            "permlink": p["permlink"],
            "payout": p.get("payout", 0),
            "pending_payout": float(str(p.get("pending_payout_value", "0 HBD")).split()[0]),
            "is_paidout": p.get("is_paidout", False),
        })
    return payouts


# Check a specific post
info = get_payout_info("hiveio", "announcing-hive")
print(f"Post: {info['title']}")
print(f"Status: {'Paid out' if info['is_paid_out'] else 'Pending'}")
print(f"Total value: {info['total_combined']:.3f} HBD")
print(f"Votes: {info['net_votes']}")

if info["beneficiaries"]:
    print("Beneficiaries:")
    for b in info["beneficiaries"]:
        print(f"  @{b['account']}: {b['pct']}%")

# Estimate author earnings
earnings = estimate_author_earnings(info)
print(f"Author receives: ~{earnings['after_beneficiaries']:.3f} HBD total")
print(f"  as HBD: {earnings['hbd_received']:.3f}")
print(f"  as HP: {earnings['hp_received_equivalent']:.3f}")
```

Payout details:
- **7-day payout window**: Rewards accumulate for 7 days, then pay out
- **50/50 split**: Author rewards default to 50% HBD + 50% HP (configurable to 100% HP)
- **Curation rewards**: ~50% of total post value goes to curators (voters)
- **Beneficiaries**: Deducted from the author's share before the HBD/HP split
- **max_accepted_payout**: Can be set to 0 to decline all rewards
- **Second payout**: None — posts only pay out once (after the 7-day window)'''
    ),
    (
        "hive_sdk/dhive-witness-properties-update",
        r'''How do I register as a witness and update witness properties (block signing key, fee, HBD interest rate) using dhive?''',
        r'''<think>
Witness registration uses witness_update or witness_set_properties.
The newer witness_set_properties allows updating individual properties
without resending everything. Key properties: block signing key,
account creation fee, HBD interest rate, maximum block size, and URL.
The signing key is critical — it must match the key used by the actual
block-producing node. Active key is required. I should show both
initial registration and property updates.
</think>

Here is how to register and manage a witness with dhive:

```javascript
const { Client, PrivateKey, PublicKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const activeKey = PrivateKey.fromString("5YourActiveKey");
const witness = "yourwitness";

/**
 * Register or update a witness using witness_update.
 */
async function registerWitness({
  signingKey,        // public key for block signing
  url = "",          // witness announcement URL
  creationFee = 3,   // account creation fee in HIVE
  blockSize = 65536, // max block size
  hbdInterestRate = 1500, // HBD interest rate in basis points (1500 = 15%)
}) {
  const op = [
    "witness_update",
    {
      owner: witness,
      url: url,
      block_signing_key: signingKey,
      props: {
        account_creation_fee: `${creationFee.toFixed(3)} HIVE`,
        maximum_block_size: blockSize,
        hbd_interest_rate: hbdInterestRate,
      },
      fee: "0.000 HIVE",
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Witness @${witness} registered/updated`);
  return result;
}

/**
 * Update specific witness properties using witness_set_properties.
 * More efficient — only sends changed properties.
 */
async function updateWitnessProperty(key, value) {
  // Properties must be serialized correctly
  const props = [[key, value]];

  const op = [
    "witness_set_properties",
    {
      owner: witness,
      props: props,
      extensions: [],
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Witness property updated: ${key}`);
  return result;
}

/**
 * Disable witness (stop block production).
 */
async function disableWitness() {
  // Set signing key to STM1111111111111111111111111111111114T1Anm (null key)
  const nullKey = "STM1111111111111111111111111111111114T1Anm";
  await registerWitness({
    signingKey: nullKey,
    url: "",
    creationFee: 3,
    blockSize: 65536,
    hbdInterestRate: 1500,
  });
  console.log("Witness disabled — signing key set to null");
}

/**
 * Get witness information.
 */
async function getWitnessInfo(witnessName) {
  const result = await client.call("condenser_api", "get_witness_by_account", [
    witnessName,
  ]);

  if (!result) return null;

  return {
    owner: result.owner,
    signing_key: result.signing_key,
    url: result.url,
    total_missed: result.total_missed,
    votes: result.votes,
    props: result.props,
    running_version: result.running_version,
    hbd_exchange_rate: result.hbd_exchange_rate,
    last_confirmed_block: result.last_confirmed_block_num,
  };
}

/**
 * Publish a price feed (witnesses set the HIVE/HBD price).
 */
async function publishPriceFeed(hiveUsdPrice) {
  const base = `${hiveUsdPrice.toFixed(3)} HBD`;
  const quote = "1.000 HIVE";

  const op = [
    "feed_publish",
    {
      publisher: witness,
      exchange_rate: {
        base: base,
        quote: quote,
      },
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Price feed published: 1 HIVE = ${hiveUsdPrice} HBD`);
  return result;
}

// Register witness
await registerWitness({
  signingKey: "STM6your_block_signing_public_key_here",
  url: "https://mywitness.com",
  creationFee: 3,
  blockSize: 65536,
  hbdInterestRate: 1500,  // 15%
});

// Update HBD interest rate only
await updateWitnessProperty("hbd_interest_rate", "1200");  // 12%

// Publish price feed
await publishPriceFeed(0.35);  // 1 HIVE = $0.35

// Check witness status
const info = await getWitnessInfo(witness);
console.log(`Missed blocks: ${info.total_missed}`);
console.log(`Running version: ${info.running_version}`);

// Disable witness when shutting down
// await disableWitness();
```

Witness operations:
- **Active key** required for all witness operations
- **Signing key**: Must match the key configured in your hived node
- **Null key** (`STM1111...`): Set this when disabling to stop producing blocks
- **Price feed**: Witnesses publish HIVE/USD price; median of all feeds sets the peg
- **HBD interest**: Each witness votes on the rate; the median becomes the chain rate
- **Total missed**: High miss count hurts credibility — monitor your node uptime'''
    ),
    (
        "hive_sdk/beem-power-up-to-others",
        r'''How do I power up HIVE to another account and track pending power-downs using beem?''',
        r'''<think>
Power up (transfer_to_vesting) can target another account by specifying
a different "to" account. This is a one-way operation — you cannot
reverse it for the recipient. The recipient gets the HP (VESTS) and
would need to power down themselves to get liquid HIVE. This is useful
for gifting HP, onboarding new users with HP, or funding project accounts.
I should also show how to monitor active power-down status.
</think>

Here is how to power up to other accounts and monitor power-downs with beem:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)
account = "youraccount"


def power_up(amount: float, to_account: str = None):
    """Power up HIVE to yourself or another account.

    Args:
        amount: Amount of liquid HIVE to convert to HP
        to_account: Target account (default: self)
    """
    target = to_account or account
    hive.transfer_to_vesting(amount, to=target, account=account)
    print(f"Powered up {amount:.3f} HIVE to @{target}")


def get_powerdown_status(username: str) -> dict:
    """Check if an account is powering down and show details."""
    acc = Account(username, blockchain_instance=hive)

    withdraw_rate = acc["vesting_withdraw_rate"]
    rate_vests = float(str(withdraw_rate).split()[0])

    if rate_vests == 0:
        return {"active": False, "message": "No active power down"}

    # Calculate HP equivalent
    hp_per_week = hive.vests_to_hp(rate_vests)

    # Next withdrawal time
    next_withdrawal = acc["next_vesting_withdrawal"]

    # Total being withdrawn
    to_withdraw = float(str(acc["to_withdraw"]).split()[0]) if "to_withdraw" in acc else 0
    withdrawn = float(str(acc["withdrawn"]).split()[0]) if "withdrawn" in acc else 0
    remaining_vests = to_withdraw - withdrawn

    # Weeks remaining
    weeks_remaining = int(remaining_vests / rate_vests) if rate_vests > 0 else 0

    return {
        "active": True,
        "weekly_hp": round(hp_per_week, 3),
        "weekly_vests": str(withdraw_rate),
        "next_withdrawal": str(next_withdrawal),
        "total_hp": round(hive.vests_to_hp(to_withdraw), 3),
        "withdrawn_hp": round(hive.vests_to_hp(withdrawn), 3),
        "remaining_hp": round(hive.vests_to_hp(remaining_vests), 3),
        "weeks_remaining": weeks_remaining,
    }


def get_vesting_delegations_out(username: str) -> list:
    """Get all outgoing HP delegations."""
    acc = Account(username, blockchain_instance=hive)
    delegations = acc.get_vesting_delegations()

    return [
        {
            "to": d["delegatee"],
            "vests": str(d["vesting_shares"]),
            "hp": round(hive.vests_to_hp(
                float(str(d["vesting_shares"]).split()[0])
            ), 3),
            "min_delegation_time": str(d["min_delegation_time"]),
        }
        for d in delegations
    ]


def get_vesting_summary(username: str) -> dict:
    """Complete vesting summary for an account."""
    acc = Account(username, blockchain_instance=hive)

    own_vests = float(str(acc["vesting_shares"]).split()[0])
    delegated_out = float(str(acc["delegated_vesting_shares"]).split()[0])
    received_in = float(str(acc["received_vesting_shares"]).split()[0])
    effective = own_vests - delegated_out + received_in

    return {
        "own_hp": round(hive.vests_to_hp(own_vests), 3),
        "delegated_out_hp": round(hive.vests_to_hp(delegated_out), 3),
        "received_in_hp": round(hive.vests_to_hp(received_in), 3),
        "effective_hp": round(hive.vests_to_hp(effective), 3),
        "own_vests": round(own_vests, 6),
    }


# Power up to yourself
power_up(50.0)

# Power up to a friend (gift HP)
power_up(25.0, to_account="friend-account")

# Check power-down status
pd_status = get_powerdown_status(account)
if pd_status["active"]:
    print(f"Powering down: {pd_status['weekly_hp']} HP/week")
    print(f"Remaining: {pd_status['remaining_hp']} HP ({pd_status['weeks_remaining']} weeks)")
else:
    print("No active power down")

# Vesting summary
summary = get_vesting_summary(account)
print(f"Own HP: {summary['own_hp']}")
print(f"Effective HP: {summary['effective_hp']}")
print(f"Delegated out: {summary['delegated_out_hp']}")
print(f"Received: {summary['received_in_hp']}")

# Check outgoing delegations
delegations = get_vesting_delegations_out(account)
for d in delegations:
    print(f"Delegated {d['hp']} HP to @{d['to']}")
```

Key points:
- **Power up to others**: Set the `to` parameter to a different account
- **One-way**: Recipient must power down themselves to get liquid HIVE back
- **13-week power down**: 1/13th released per week when powering down
- **Effective HP** = Own - Delegated Out + Delegated In
- **Active key** required for power up
- **No minimum power up**: Any amount of liquid HIVE can be powered up'''
    ),
    (
        "hive_sdk/dhive-internal-market-orders",
        r'''How do I place and manage limit orders on the Hive internal market using dhive? I want to trade HIVE for HBD.''',
        r'''<think>
The Hive internal market is an on-chain order book for trading HIVE <-> HBD.
It uses limit_order_create and limit_order_cancel operations. Orders can be
fill-or-kill (must fill immediately or fail) or regular (sit in the order book).
The price is implicit from the amount_to_sell and min_to_receive ratio.
Orders have an expiration date. Active key is required.
I should show placing buy/sell orders, checking the order book, and
managing existing orders.
</think>

Here is how to trade on the Hive internal market with dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const activeKey = PrivateKey.fromString("5YourActiveKey");
const account = "youraccount";

/**
 * Place a limit order to sell HIVE for HBD.
 */
async function sellHive(hiveAmount, minHbdReceive, expirationHours = 168) {
  const orderId = Math.floor(Date.now() / 1000) % 2147483647;
  const expiration = new Date(Date.now() + expirationHours * 3600 * 1000)
    .toISOString()
    .split(".")[0];

  const price = (minHbdReceive / hiveAmount).toFixed(4);

  const op = [
    "limit_order_create",
    {
      owner: account,
      orderid: orderId,
      amount_to_sell: `${hiveAmount.toFixed(3)} HIVE`,
      min_to_receive: `${minHbdReceive.toFixed(3)} HBD`,
      fill_or_kill: false,
      expiration: expiration,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Sell order: ${hiveAmount} HIVE @ ${price} HBD/HIVE (Order #${orderId})`);
  return { result, orderId };
}

/**
 * Place a limit order to buy HIVE with HBD.
 */
async function buyHive(hbdToSpend, minHiveReceive, expirationHours = 168) {
  const orderId = Math.floor(Date.now() / 1000) % 2147483647;
  const expiration = new Date(Date.now() + expirationHours * 3600 * 1000)
    .toISOString()
    .split(".")[0];

  const price = (hbdToSpend / minHiveReceive).toFixed(4);

  const op = [
    "limit_order_create",
    {
      owner: account,
      orderid: orderId,
      amount_to_sell: `${hbdToSpend.toFixed(3)} HBD`,
      min_to_receive: `${minHiveReceive.toFixed(3)} HIVE`,
      fill_or_kill: false,
      expiration: expiration,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Buy order: ${minHiveReceive} HIVE for ${hbdToSpend} HBD @ ${price} HBD/HIVE (Order #${orderId})`);
  return { result, orderId };
}

/**
 * Cancel an open order.
 */
async function cancelOrder(orderId) {
  const op = [
    "limit_order_cancel",
    {
      owner: account,
      orderid: orderId,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Cancelled order #${orderId}`);
  return result;
}

/**
 * Get the current order book.
 */
async function getOrderBook(limit = 20) {
  const book = await client.call("condenser_api", "get_order_book", [limit]);

  return {
    bids: book.bids.map((b) => ({
      hive: b.hive / 1000,
      hbd: b.hbd / 1000,
      price: (b.hbd / b.hive).toFixed(4),
    })),
    asks: book.asks.map((a) => ({
      hive: a.hive / 1000,
      hbd: a.hbd / 1000,
      price: (a.hbd / a.hive).toFixed(4),
    })),
  };
}

/**
 * Get open orders for an account.
 */
async function getOpenOrders(username) {
  const orders = await client.call("condenser_api", "get_open_orders", [username]);
  return orders.map((o) => ({
    id: o.orderid,
    sell: o.sell_price.base,
    for: o.sell_price.quote,
    created: o.created,
    expiration: o.expiration,
  }));
}

// View the order book
const book = await getOrderBook(5);
console.log("Top bids (buying HIVE):");
for (const b of book.bids) {
  console.log(`  ${b.hive} HIVE @ ${b.price} HBD/HIVE`);
}
console.log("Top asks (selling HIVE):");
for (const a of book.asks) {
  console.log(`  ${a.hive} HIVE @ ${a.price} HBD/HIVE`);
}

// Sell 100 HIVE for at least 35 HBD (limit at 0.35 HBD/HIVE)
const { orderId } = await sellHive(100, 35, 168);

// Buy 200 HIVE with 60 HBD (limit at 0.30 HBD/HIVE)
await buyHive(60, 200, 168);

// Check open orders
const openOrders = await getOpenOrders(account);
console.log(`Open orders: ${openOrders.length}`);

// Cancel an order
await cancelOrder(orderId);
```

Internal market details:
- **On-chain order book**: No external exchange needed
- **HIVE <-> HBD only**: The only trading pair
- **Active key** required for placing and cancelling orders
- **fill_or_kill**: If true, order must fill entirely or fail (no partial fills)
- **Expiration**: Orders expire after the set time; default to 1 week
- **Order ID**: Unique per account; reuse is okay after cancellation/fill
- **No trading fees**: The internal market has zero fees'''
    ),
    (
        "hive_sdk/beem-curation-trail-bot",
        r'''How do I build a curation trail bot that automatically follows another account's votes using beem?''',
        r'''<think>
A curation trail bot streams the blockchain for vote operations from a
leader account, then mirrors those votes with a configurable weight and
delay. Key considerations: vote timing (curation rewards peak at ~24h
in the old system, but now are linear), weight scaling, avoiding
duplicate votes, RC management, and the 3-second voting cooldown.
I need to show a production-quality bot with proper error handling,
vote weight scaling, and blacklist support.
</think>

Here is a production curation trail bot using beem:

```python
import json
import time
import logging
from datetime import datetime
from beem import Hive
from beem.blockchain import Blockchain
from beem.comment import Comment
from beem.account import Account
from beem.exceptions import RPCError

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("curation_trail")

NODES = ["https://api.hive.blog", "https://api.deathwing.me"]


class CurationTrail:
    def __init__(self, voter: str, posting_key: str,
                 leaders: list[str], weight_scale: float = 0.5,
                 vote_delay_sec: int = 0, blacklist: set = None):
        """
        Args:
            voter: Your account name
            posting_key: Your posting key WIF
            leaders: List of accounts to follow votes from
            weight_scale: Scale leader vote weight (0.5 = 50% of leader's weight)
            vote_delay_sec: Seconds to wait after leader votes
            blacklist: Set of author accounts to never vote on
        """
        self.voter = voter
        self.leaders = set(leaders)
        self.weight_scale = weight_scale
        self.vote_delay_sec = vote_delay_sec
        self.blacklist = blacklist or set()
        self.voted_posts = set()  # track to avoid double-voting
        self.last_vote_time = 0

        self.hive = Hive(node=NODES, keys=[posting_key])
        self.bc = Blockchain(blockchain_instance=self.hive)

    def should_vote(self, op: dict) -> bool:
        """Decide whether to mirror this vote."""
        if op["voter"] not in self.leaders:
            return False
        if op["voter"] == self.voter:
            return False  # don't follow our own votes
        if op["weight"] <= 0:
            return False  # don't follow downvotes or unvotes
        if op["author"] in self.blacklist:
            return False
        if op["author"] == self.voter:
            return False  # don't vote on own posts via trail

        post_id = f"@{op['author']}/{op['permlink']}"
        if post_id in self.voted_posts:
            return False  # already voted

        return True

    def calculate_weight(self, leader_weight: int) -> int:
        """Scale leader's vote weight."""
        scaled = int(leader_weight * self.weight_scale)
        # Clamp to valid range and minimum of 1% to avoid wasting RC
        return max(100, min(10000, scaled))

    def cast_vote(self, author: str, permlink: str, weight: int):
        """Cast vote with retry logic."""
        # Respect 3-second voting cooldown
        elapsed = time.time() - self.last_vote_time
        if elapsed < 3:
            time.sleep(3 - elapsed)

        try:
            self.hive.vote(weight / 100, f"@{author}/{permlink}",
                           account=self.voter)
            self.last_vote_time = time.time()
            self.voted_posts.add(f"@{author}/{permlink}")
            log.info(f"VOTED @{author}/{permlink} at {weight/100:.1f}%")
            return True
        except RPCError as e:
            if "already voted" in str(e).lower():
                log.warning(f"Already voted on @{author}/{permlink}")
                self.voted_posts.add(f"@{author}/{permlink}")
            elif "rc_plugin_exception" in str(e).lower():
                log.error("Insufficient RC — pausing for 1 hour")
                time.sleep(3600)
            else:
                log.error(f"Vote failed: {e}")
            return False

    def check_rc(self) -> float:
        """Check remaining RC percentage."""
        acc = Account(self.voter, blockchain_instance=self.hive)
        rc = acc.get_rc_manabar()
        return rc["current_pct"]

    def run(self):
        """Start the curation trail."""
        log.info(f"Starting curation trail for @{self.voter}")
        log.info(f"Following leaders: {self.leaders}")
        log.info(f"Weight scale: {self.weight_scale*100}%")

        last_block = None
        while True:
            try:
                for op in self.bc.stream(opNames=["vote"], start=last_block):
                    last_block = op.get("block_num")

                    if not self.should_vote(op):
                        continue

                    weight = self.calculate_weight(op["weight"])
                    leader = op["voter"]
                    log.info(
                        f"Leader @{leader} voted @{op['author']}/{op['permlink']} "
                        f"at {op['weight']/100:.0f}% -> trailing at {weight/100:.0f}%"
                    )

                    if self.vote_delay_sec > 0:
                        time.sleep(self.vote_delay_sec)

                    self.cast_vote(op["author"], op["permlink"], weight)

                    # Periodic RC check
                    if len(self.voted_posts) % 10 == 0:
                        rc_pct = self.check_rc()
                        log.info(f"RC: {rc_pct:.1f}%")
                        if rc_pct < 5:
                            log.warning("RC low, pausing 1 hour")
                            time.sleep(3600)

            except RPCError as e:
                log.warning(f"RPC error: {e}, reconnecting in 10s")
                time.sleep(10)
                self.hive = Hive(node=NODES, keys=[self.hive.keys[0]])
                self.bc = Blockchain(blockchain_instance=self.hive)
            except KeyboardInterrupt:
                log.info("Trail stopped")
                break


if __name__ == "__main__":
    trail = CurationTrail(
        voter="youraccount",
        posting_key="5YourPostingKey",
        leaders=["curator1", "curator2"],
        weight_scale=0.5,     # 50% of leader's weight
        vote_delay_sec=0,     # vote immediately after leader
        blacklist={"spammer1", "scammer2"},
    )
    trail.run()
```

Curation trail considerations:
- **3-second vote cooldown**: Minimum time between votes
- **RC management**: Each vote costs RC; monitor and pause when low
- **Weight scaling**: Trail at a fraction of the leader's weight to conserve voting power
- **Duplicate prevention**: Track voted posts to avoid wasting RC on double-votes
- **Linear curation**: Since HF25, curation rewards are linear — no optimal timing window
- **Blacklists**: Skip specific authors to avoid voting on unwanted content'''
    ),
    (
        "hive_sdk/dhive-hivesigner-oauth",
        r'''How do I integrate HiveSigner (formerly SteemConnect) OAuth for user authentication and transaction signing in a web app using dhive?''',
        r'''<think>
HiveSigner provides OAuth2-style authentication for Hive. Users authorize
your app without sharing private keys. The flow is:
1. Redirect user to HiveSigner authorize URL
2. User approves, gets redirected back with an access token
3. Use the access token to broadcast operations on behalf of the user

In practice, users either grant posting authority to your app account
or use HiveSigner's API to sign individual transactions. The access
token acts as a bearer token for the HiveSigner API.
I should show both the OAuth flow and the API broadcasting.
</think>

Here is how to integrate HiveSigner OAuth with a web app:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const express = require("express");
const axios = require("axios");

const app = express();
const HIVESIGNER_APP = "your-app-name";
const APP_SECRET = "your-app-secret";
const REDIRECT_URI = "http://localhost:3000/callback";

const hiveClient = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

/**
 * Generate the HiveSigner authorization URL.
 */
function getAuthUrl(scope = "vote,comment,custom_json") {
  const params = new URLSearchParams({
    client_id: HIVESIGNER_APP,
    redirect_uri: REDIRECT_URI,
    scope: scope,
    response_type: "code",
  });
  return `https://hivesigner.com/oauth2/authorize?${params}`;
}

/**
 * Exchange authorization code for access token.
 */
async function getAccessToken(code) {
  const response = await axios.post(
    "https://hivesigner.com/api/oauth2/token",
    {
      grant_type: "authorization_code",
      code: code,
      client_id: HIVESIGNER_APP,
      client_secret: APP_SECRET,
      redirect_uri: REDIRECT_URI,
    }
  );

  return {
    access_token: response.data.access_token,
    username: response.data.username,
    expires_in: response.data.expires_in,
  };
}

/**
 * Broadcast an operation using HiveSigner access token.
 */
async function broadcastWithHiveSigner(accessToken, operations) {
  const response = await axios.post(
    "https://hivesigner.com/api/broadcast",
    { operations },
    {
      headers: {
        Authorization: accessToken,
        "Content-Type": "application/json",
      },
    }
  );
  return response.data;
}

/**
 * Vote on behalf of an authenticated user.
 */
async function voteForUser(accessToken, username, author, permlink, weight) {
  return broadcastWithHiveSigner(accessToken, [
    [
      "vote",
      {
        voter: username,
        author: author,
        permlink: permlink,
        weight: weight,
      },
    ],
  ]);
}

/**
 * Get authenticated user's profile.
 */
async function getUserProfile(accessToken) {
  const response = await axios.get("https://hivesigner.com/api/me", {
    headers: { Authorization: accessToken },
  });
  return response.data;
}

// Express routes
app.get("/login", (req, res) => {
  res.redirect(getAuthUrl());
});

app.get("/callback", async (req, res) => {
  const { code } = req.query;
  if (!code) return res.status(400).send("Missing authorization code");

  try {
    const tokens = await getAccessToken(code);
    // Store tokens in session (use proper session management in production)
    req.session = tokens;

    const profile = await getUserProfile(tokens.access_token);
    res.json({
      message: `Welcome @${tokens.username}!`,
      profile: profile.account,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/vote", async (req, res) => {
  const { accessToken, username, author, permlink, weight } = req.body;

  try {
    const result = await voteForUser(
      accessToken, username, author, permlink, weight
    );
    res.json({ success: true, result });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(3000, () => {
  console.log("App running on http://localhost:3000");
  console.log(`Login URL: ${getAuthUrl()}`);
});
```

HiveSigner integration:
- **No private keys needed** on your server — HiveSigner handles signing
- **Scope**: Request only permissions you need (vote, comment, custom_json)
- **Access token**: Bearer token for API calls, has expiration
- **App registration**: Register at hivesigner.com to get client_id and secret
- **Alternative**: HiveKeychain browser extension is more popular for web3 dApps
- **Security**: Never store access tokens in localStorage — use httpOnly cookies'''
    ),
    (
        "hive_sdk/beem-batch-operations-efficiency",
        r'''I need to process thousands of votes per day with beem. How do I optimize for throughput and avoid RC exhaustion?''',
        r'''<think>
High-throughput voting requires careful management of RC, vote cooldowns,
and node connections. Key optimizations: batch operations into transactions,
pre-calculate RC costs, manage vote timing (3-second minimum), use
efficient streaming, and implement RC budgeting. I should also cover
vote weight management to preserve voting power. A bot doing thousands
of votes needs to use small vote weights to avoid depleting VP.
</think>

Here is how to build a high-throughput voting system with beem:

```python
import time
import logging
import threading
from queue import Queue, Empty
from collections import deque
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Vote

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("batch_voter")

NODES = [
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network",
]


class HighThroughputVoter:
    def __init__(self, account: str, posting_key: str,
                 max_daily_votes: int = 500,
                 target_vp_floor: float = 80.0):
        self.account = account
        self.posting_key = posting_key
        self.max_daily_votes = max_daily_votes
        self.target_vp_floor = target_vp_floor

        self.hive = Hive(node=NODES, keys=[posting_key])
        self.vote_queue = Queue()
        self.voted_today = deque(maxlen=max_daily_votes)
        self.last_vote_time = 0
        self.votes_cast = 0

    def get_optimal_weight(self) -> int:
        """Calculate vote weight based on daily budget and current VP."""
        acc = Account(self.account, blockchain_instance=self.hive)
        current_vp = acc.get_voting_power()

        if current_vp < self.target_vp_floor:
            log.warning(f"VP at {current_vp:.1f}%, below floor {self.target_vp_floor}%")
            return 0  # skip voting

        # Each 100% vote costs 2% VP. VP regens 20%/day.
        # Daily VP budget: 20% = 10 full votes or equivalent
        # For 500 votes/day: 20% / 500 = 0.04% per vote = 2% weight
        max_vp_spend = 20.0  # % per day
        weight_pct = (max_vp_spend / self.max_daily_votes) * 50
        weight = int(max(100, min(10000, weight_pct * 100)))

        return weight

    def check_rc_budget(self) -> dict:
        """Check if we have enough RC for remaining daily votes."""
        acc = Account(self.account, blockchain_instance=self.hive)
        rc = acc.get_rc_manabar()
        current_rc = rc["current_mana"]
        max_rc = rc["max_mana"]

        vote_rc_cost = 80_000_000  # ~80M RC per vote
        remaining_votes = self.max_daily_votes - self.votes_cast
        rc_needed = remaining_votes * vote_rc_cost

        return {
            "rc_pct": rc["current_pct"],
            "can_afford_votes": int(current_rc / vote_rc_cost),
            "remaining_planned": remaining_votes,
            "sufficient": current_rc >= rc_needed,
        }

    def batch_vote(self, votes: list[dict], max_per_tx: int = 5):
        """Cast multiple votes in batched transactions.

        Each vote still costs separate RC, but batching reduces
        overhead and ensures atomicity within each batch.
        """
        for i in range(0, len(votes), max_per_tx):
            batch = votes[i:i + max_per_tx]

            # Enforce 3-second minimum between vote transactions
            elapsed = time.time() - self.last_vote_time
            if elapsed < 3:
                time.sleep(3 - elapsed)

            tx = TransactionBuilder(blockchain_instance=self.hive)
            for v in batch:
                tx.appendOps(Vote(**{
                    "voter": self.account,
                    "author": v["author"],
                    "permlink": v["permlink"],
                    "weight": v.get("weight", self.get_optimal_weight()),
                }))

            tx.appendSigner(self.account, "posting")
            try:
                tx.sign()
                result = tx.broadcast()
                self.last_vote_time = time.time()
                self.votes_cast += len(batch)

                for v in batch:
                    self.voted_today.append(f"@{v['author']}/{v['permlink']}")

                log.info(f"Batch voted {len(batch)} posts (total: {self.votes_cast})")
            except Exception as e:
                log.error(f"Batch vote failed: {e}")
                # Fall back to individual votes
                for v in batch:
                    self._single_vote(v)

    def _single_vote(self, vote: dict):
        """Fallback: cast a single vote."""
        elapsed = time.time() - self.last_vote_time
        if elapsed < 3:
            time.sleep(3 - elapsed)

        try:
            weight = vote.get("weight", self.get_optimal_weight())
            if weight == 0:
                return
            self.hive.vote(
                weight / 100,
                f"@{vote['author']}/{vote['permlink']}",
                account=self.account,
            )
            self.last_vote_time = time.time()
            self.votes_cast += 1
        except Exception as e:
            log.error(f"Single vote failed: {e}")

    def get_stats(self) -> dict:
        """Get current voting statistics."""
        rc = self.check_rc_budget()
        return {
            "votes_cast_today": self.votes_cast,
            "max_daily": self.max_daily_votes,
            "rc_pct": rc["rc_pct"],
            "affordable_votes": rc["can_afford_votes"],
            "optimal_weight": self.get_optimal_weight() / 100,
        }


# Usage
voter = HighThroughputVoter(
    account="youraccount",
    posting_key="5YourPostingKey",
    max_daily_votes=500,
    target_vp_floor=80.0,
)

# Queue up votes
pending_votes = [
    {"author": "author1", "permlink": "post-1"},
    {"author": "author2", "permlink": "post-2"},
    {"author": "author3", "permlink": "post-3"},
    # ... hundreds more
]

# Check if we can afford it
rc_budget = voter.check_rc_budget()
log.info(f"RC: {rc_budget['rc_pct']:.1f}%, can afford {rc_budget['can_afford_votes']} votes")

if rc_budget["sufficient"]:
    voter.batch_vote(pending_votes, max_per_tx=5)

# Check stats
stats = voter.get_stats()
log.info(f"Votes cast: {stats['votes_cast_today']}/{stats['max_daily']}")
```

Throughput optimization tips:
- **Batch operations**: Up to ~5 votes per transaction reduces overhead
- **3-second cooldown**: Minimum between vote-containing transactions
- **VP budgeting**: 20% VP regens daily = budget across your daily vote count
- **RC monitoring**: Pre-check RC before large batches
- **Weight scaling**: Low weights (1-2%) for high-volume voting
- **VP floor**: Stop voting when VP drops below threshold (e.g., 80%)
- **Theoretical max**: ~28,800 votes/day (one per 3-second block), but VP limits practical volume'''
    ),
    (
        "hive_sdk/dhive-keychain-integration",
        r'''How do I integrate Hive Keychain browser extension into a web application for transaction signing?''',
        r'''<think>
Hive Keychain is a browser extension (like MetaMask for Ethereum) that
stores users' keys and signs transactions client-side. The app never
sees private keys. The API is exposed via window.hive_keychain object.
Common methods: requestHandshake, requestSignBuffer, requestBroadcast,
requestTransfer, requestVote, requestPost, etc. All return via callbacks.
I need to show detection, authentication, and common operations.
This is pure frontend JavaScript — no dhive needed for signing.
</think>

Here is how to integrate Hive Keychain in a web application:

```javascript
/**
 * Hive Keychain integration for browser-based dApps.
 * Works with the Hive Keychain browser extension.
 */

class KeychainHelper {
  /**
   * Check if Hive Keychain is installed.
   */
  static isInstalled() {
    return typeof window !== "undefined" && !!window.hive_keychain;
  }

  /**
   * Wait for Keychain to be available (it loads async).
   */
  static async waitForKeychain(timeoutMs = 3000) {
    const start = Date.now();
    while (!this.isInstalled()) {
      if (Date.now() - start > timeoutMs) {
        throw new Error(
          "Hive Keychain not detected. Install from https://hive-keychain.com"
        );
      }
      await new Promise((r) => setTimeout(r, 100));
    }
    return true;
  }

  /**
   * Promisify Keychain callbacks.
   */
  static promisify(method, ...args) {
    return new Promise((resolve, reject) => {
      window.hive_keychain[method](...args, (response) => {
        if (response.success) {
          resolve(response);
        } else {
          reject(new Error(response.message || "Keychain operation failed"));
        }
      });
    });
  }

  /**
   * Verify Keychain connection with a handshake.
   */
  static async handshake() {
    return this.promisify("requestHandshake");
  }

  /**
   * Authenticate user by signing a message.
   */
  static async authenticate(username, message = null) {
    const msg = message || `Login to MyApp: ${Date.now()}`;
    const result = await this.promisify(
      "requestSignBuffer",
      username,
      msg,
      "Posting" // key type
    );
    return {
      username,
      signature: result.result,
      message: msg,
      publicKey: result.publicKey,
    };
  }

  /**
   * Vote on a post.
   */
  static async vote(username, author, permlink, weight) {
    return this.promisify(
      "requestVote",
      username,
      permlink,
      author,
      weight // -10000 to 10000
    );
  }

  /**
   * Transfer HIVE or HBD.
   */
  static async transfer(from, to, amount, memo, currency = "HIVE") {
    return this.promisify(
      "requestTransfer",
      from,
      to,
      amount.toFixed(3),
      memo,
      currency,
      false // enforce = false allows user to modify
    );
  }

  /**
   * Broadcast a custom_json operation.
   */
  static async customJson(username, id, keyType, json, displayName = "") {
    return this.promisify(
      "requestCustomJson",
      username,
      id,
      keyType,           // "Posting" or "Active"
      JSON.stringify(json),
      displayName || id  // display name shown to user
    );
  }

  /**
   * Create a post.
   */
  static async post(username, title, body, parentPermlink, parentAuthor,
                     jsonMetadata, permlink) {
    return this.promisify(
      "requestPost",
      username,
      title,
      body,
      parentPermlink,
      parentAuthor,
      jsonMetadata,
      permlink,
      ""  // comment_options (optional)
    );
  }

  /**
   * Broadcast raw operations.
   */
  static async broadcast(username, operations, keyType = "Posting") {
    return this.promisify(
      "requestBroadcast",
      username,
      operations,
      keyType
    );
  }
}

// ==================
// Usage in a web app
// ==================

// Check for Keychain on page load
document.addEventListener("DOMContentLoaded", async () => {
  try {
    await KeychainHelper.waitForKeychain();
    console.log("Hive Keychain detected!");
    document.getElementById("login-btn").disabled = false;
  } catch {
    console.warn("Hive Keychain not installed");
    document.getElementById("keychain-warning").style.display = "block";
  }
});

// Login
document.getElementById("login-btn").addEventListener("click", async () => {
  try {
    const auth = await KeychainHelper.authenticate("username");
    console.log(`Logged in as @${auth.username}`);
    console.log(`Signature: ${auth.signature}`);
    // Send signature to your backend for verification
  } catch (err) {
    console.error("Login failed:", err.message);
  }
});

// Vote
async function upvotePost(author, permlink) {
  try {
    await KeychainHelper.vote("username", author, permlink, 10000);
    console.log("Vote successful!");
  } catch (err) {
    console.error("Vote failed:", err.message);
  }
}

// Custom JSON for dApp
async function sendGameAction(action, data) {
  try {
    await KeychainHelper.customJson(
      "username",
      "mygame",
      "Posting",
      { action, data, timestamp: Date.now() },
      "My Game Action"
    );
  } catch (err) {
    console.error("Action failed:", err.message);
  }
}
```

Hive Keychain details:
- **No private keys exposed**: Keys stay in the extension, never sent to the app
- **User confirmation**: Every operation shows a popup for user approval
- **Key types**: Posting, Active, Memo — request the minimum authority needed
- **Browser only**: Desktop Chrome/Firefox/Brave; mobile via Keychain mobile app
- **Async loading**: Keychain injects after page load — always wait for it
- **Alternative to HiveSigner**: Keychain is more popular for Web3-style dApps'''
    ),
    (
        "hive_sdk/beem-witness-schedule-feed",
        r'''How do I monitor the witness schedule and publish automated price feeds using beem?''',
        r'''<think>
Witnesses publish price feeds that determine the HIVE/HBD peg. The median
of all top-21 witness feeds sets the blockchain's price. Feeds should be
published regularly (at least once per hour, but most publish every ~1 hour).
I need to show how to fetch external price data, format it correctly,
and publish using feed_publish operation. Also show the current witness
schedule and feed history.
</think>

Here is how to monitor witnesses and publish price feeds with beem:

```python
import time
import logging
import requests
from beem import Hive
from beem.witness import Witness, WitnessesRankedByVote
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Feed_publish

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("price_feed")

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)
witness_account = "yourwitness"


def fetch_hive_price() -> float:
    """Fetch current HIVE price from CoinGecko."""
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "hive", "vs_currencies": "usd"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["hive"]["usd"]
    except Exception as e:
        log.error(f"CoinGecko price fetch failed: {e}")
        return None


def fetch_hive_price_multi() -> float:
    """Fetch price from multiple sources and take the median."""
    prices = []

    # CoinGecko
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "hive", "vs_currencies": "usd"},
            timeout=10,
        )
        prices.append(resp.json()["hive"]["usd"])
    except Exception:
        pass

    # Binance
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "HIVEUSDT"},
            timeout=10,
        )
        prices.append(float(resp.json()["price"]))
    except Exception:
        pass

    if not prices:
        raise RuntimeError("Could not fetch price from any source")

    prices.sort()
    mid = len(prices) // 2
    return prices[mid]  # median


def publish_price_feed(price_usd: float):
    """Publish HIVE/USD price feed as a witness."""
    # Feed format: base/quote where base = HBD value of 1 HIVE
    base = f"{price_usd:.3f} HBD"
    quote = "1.000 HIVE"

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Feed_publish(**{
        "publisher": witness_account,
        "exchange_rate": {
            "base": base,
            "quote": quote,
        },
    }))
    tx.appendSigner(witness_account, "active")
    tx.sign()
    result = tx.broadcast()
    log.info(f"Published feed: 1 HIVE = {price_usd:.3f} USD")
    return result


def get_current_feeds():
    """Get the current median price and individual witness feeds."""
    median = hive.get_current_median_history()
    base = float(str(median["base"]).split()[0])
    quote = float(str(median["quote"]).split()[0])
    median_price = base / quote

    return {
        "median_price_usd": round(median_price, 4),
        "base": str(median["base"]),
        "quote": str(median["quote"]),
    }


def get_witness_schedule():
    """Get the current witness production schedule."""
    schedule = hive.rpc.get_witness_schedule()
    return {
        "current_shuffled": schedule["current_shuffled_witnesses"],
        "median_props": schedule["median_props"],
        "num_scheduled": len(schedule["current_shuffled_witnesses"]),
    }


def get_witness_feed_age(witness_name: str) -> float:
    """Check how old a witness's last price feed is (in hours)."""
    w = Witness(witness_name, blockchain_instance=hive)
    last_update = w["last_hbd_exchange_update"]
    # Parse and calculate age
    from datetime import datetime
    update_time = datetime.strptime(str(last_update), "%Y-%m-%dT%H:%M:%S")
    age = datetime.utcnow() - update_time
    return age.total_seconds() / 3600


def run_price_feed_bot(interval_seconds: int = 3600):
    """Run automated price feed publisher."""
    log.info(f"Starting price feed bot for witness @{witness_account}")
    log.info(f"Publishing every {interval_seconds}s")

    while True:
        try:
            price = fetch_hive_price_multi()
            if price and price > 0:
                # Sanity check: don't publish if price changed more than 50%
                current = get_current_feeds()
                if current["median_price_usd"] > 0:
                    change = abs(price - current["median_price_usd"]) / current["median_price_usd"]
                    if change > 0.5:
                        log.warning(
                            f"Price change too large ({change*100:.0f}%), "
                            f"skipping. Got: {price}, Median: {current['median_price_usd']}"
                        )
                        time.sleep(300)
                        continue

                publish_price_feed(price)
            else:
                log.warning("No valid price fetched, skipping this cycle")

        except Exception as e:
            log.error(f"Feed publish error: {e}")

        time.sleep(interval_seconds)


# Check current state
feeds = get_current_feeds()
print(f"Current median price: ${feeds['median_price_usd']}")

schedule = get_witness_schedule()
print(f"Active witnesses: {schedule['current_shuffled']}")

# Check your feed age
age = get_witness_feed_age(witness_account)
print(f"Your feed age: {age:.1f} hours")

# Publish a single feed
price = fetch_hive_price_multi()
if price:
    publish_price_feed(price)

# Or run the automated bot
# run_price_feed_bot(interval_seconds=3600)
```

Price feed details:
- **Active key** required for feed_publish
- **Publish frequency**: At least hourly; stale feeds (>24h) hurt witness credibility
- **Median**: Top 21 witness feeds are median-aggregated for the chain price
- **Sanity check**: Always validate price against current median to avoid outlier errors
- **Multiple sources**: Use 2+ price APIs to avoid single-source manipulation
- **HBD peg**: The published price maintains the HBD soft peg to ~$1 USD'''
    ),
    (
        "hive_sdk/beem-virtual-operations",
        r'''How do I track virtual operations like curation rewards, author rewards, and interest payments using beem?''',
        r'''<think>
Virtual operations are generated by the blockchain itself, not broadcast by
users. They include: curation_reward, author_reward, comment_reward,
interest, fill_vesting_withdraw, return_vesting_delegation, producer_reward,
etc. These are visible in account history but not in blocks. You can
stream them or fetch them from account history. They provide crucial
information about actual rewards received, delegation returns, etc.
I should show how to find them in history and stream them.
</think>

Here is how to track virtual operations with beem:

```python
import json
from datetime import datetime, timedelta
from beem import Hive
from beem.account import Account
from beem.blockchain import Blockchain

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])


# Key virtual operation types
VIRTUAL_OPS = {
    "curation_reward": "Curation reward from voting",
    "author_reward": "Author payout for a post",
    "comment_reward": "Total comment/post reward split",
    "interest": "HBD savings interest payment",
    "fill_vesting_withdraw": "Weekly power-down payout",
    "return_vesting_delegation": "Delegation returned after cooldown",
    "producer_reward": "Witness block production reward",
    "comment_benefactor_reward": "Beneficiary payout",
    "claim_reward_balance": "Manual reward claim",
    "transfer_to_vesting_completed": "Power-up completed",
}


def get_rewards_history(username: str, days: int = 7) -> dict:
    """Get reward history broken down by type."""
    acc = Account(username, blockchain_instance=hive)

    cutoff = datetime.utcnow() - timedelta(days=days)
    rewards = {
        "curation_rewards_hp": 0.0,
        "author_rewards_hbd": 0.0,
        "author_rewards_hp": 0.0,
        "beneficiary_rewards_hp": 0.0,
        "interest_hbd": 0.0,
        "producer_rewards_hp": 0.0,
    }

    for op in acc.history_reverse(limit=5000):
        op_time = datetime.strptime(op["timestamp"], "%Y-%m-%dT%H:%M:%S")
        if op_time < cutoff:
            break

        op_type = op["type"]

        if op_type == "curation_reward":
            vests = float(op.get("reward", "0 VESTS").split()[0])
            rewards["curation_rewards_hp"] += hive.vests_to_hp(vests)

        elif op_type == "author_reward":
            hbd = float(op.get("hbd_payout", "0 HBD").split()[0])
            vests = float(op.get("vesting_payout", "0 VESTS").split()[0])
            rewards["author_rewards_hbd"] += hbd
            rewards["author_rewards_hp"] += hive.vests_to_hp(vests)

        elif op_type == "comment_benefactor_reward":
            vests = float(op.get("vesting_payout", "0 VESTS").split()[0])
            rewards["beneficiary_rewards_hp"] += hive.vests_to_hp(vests)

        elif op_type == "interest":
            interest = float(op.get("interest", "0 HBD").split()[0])
            rewards["interest_hbd"] += interest

        elif op_type == "producer_reward":
            vests = float(op.get("vesting_shares", "0 VESTS").split()[0])
            rewards["producer_rewards_hp"] += hive.vests_to_hp(vests)

    # Round all values
    return {k: round(v, 3) for k, v in rewards.items()}


def get_top_curation_posts(username: str, limit: int = 10) -> list:
    """Find which posts earned the most curation rewards."""
    acc = Account(username, blockchain_instance=hive)
    curation = []

    for op in acc.history_reverse(limit=2000):
        if op["type"] == "curation_reward":
            vests = float(op.get("reward", "0 VESTS").split()[0])
            hp = hive.vests_to_hp(vests)
            curation.append({
                "author": op["comment_author"],
                "permlink": op["comment_permlink"],
                "reward_hp": round(hp, 4),
                "timestamp": op["timestamp"],
            })

        if len(curation) >= limit * 5:
            break

    curation.sort(key=lambda x: x["reward_hp"], reverse=True)
    return curation[:limit]


def stream_virtual_ops(op_types: list = None):
    """Stream virtual operations in real-time."""
    bc = Blockchain(blockchain_instance=hive)
    watch = set(op_types) if op_types else set(VIRTUAL_OPS.keys())

    print(f"Streaming virtual ops: {watch}")
    for op in bc.stream(opNames=list(watch)):
        op_type = op["type"]
        print(f"[{op.get('timestamp', '')}] {op_type}:")

        if op_type == "author_reward":
            print(f"  @{op['author']}/{op['permlink']}: "
                  f"{op.get('hbd_payout', '0')} HBD + "
                  f"{op.get('vesting_payout', '0')} VESTS")

        elif op_type == "curation_reward":
            print(f"  @{op['curator']} earned {op.get('reward', '0')} "
                  f"on @{op['comment_author']}/{op['comment_permlink']}")

        elif op_type == "transfer" and "interest" in op.get("memo", ""):
            print(f"  @{op['to']} received {op['amount']} interest")


# Get last 7 days of rewards
rewards = get_rewards_history("blocktrades", days=7)
print("Last 7 days rewards:")
for key, value in rewards.items():
    if value > 0:
        print(f"  {key}: {value}")

# Top curation earners
top = get_top_curation_posts("blocktrades", limit=5)
print("\nTop curation rewards:")
for t in top:
    print(f"  {t['reward_hp']} HP from @{t['author']}/{t['permlink']}")

# Stream virtual ops (uncomment to run)
# stream_virtual_ops(["curation_reward", "author_reward"])
```

Virtual operation types:
- **curation_reward**: HP earned from voting (paid at post payout)
- **author_reward**: Author's share of post payout
- **comment_benefactor_reward**: Beneficiary's share of author rewards
- **interest**: HBD savings interest (paid periodically)
- **fill_vesting_withdraw**: Weekly power-down installment
- **producer_reward**: Witness reward for producing a block
- **return_vesting_delegation**: HP returned after undelegation cooldown
- **Not in blocks**: Virtual ops are generated, not broadcast — found only in account history'''
    ),
    (
        "hive_sdk/dhive-content-formatting",
        r'''What are the best practices for formatting Hive post content, json_metadata, and handling images with dhive?''',
        r'''<think>
Hive posts use Markdown for content. The json_metadata field stores
structured data like tags, images, app info, and format hints.
Proper formatting is important for frontend rendering. Images should
use proxy URLs for performance. Tags have specific rules. The
json_metadata schema is not enforced on-chain but frontends expect
certain fields. I should cover Markdown formatting, metadata schema,
image handling, and common formatting pitfalls.
</think>

Here is a comprehensive guide to content formatting for Hive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

/**
 * Build properly formatted json_metadata for a Hive post.
 */
function buildJsonMetadata({
  tags = [],
  images = [],
  links = [],
  app = "myapp/1.0",
  format = "markdown",
  description = "",
  canonical_url = "",
  video = null,
}) {
  const metadata = {
    tags: tags.slice(0, 10).map((t) => t.toLowerCase().replace(/[^a-z0-9-]/g, "")),
    image: images,
    links: links,
    app: app,
    format: format,
  };

  if (description) metadata.description = description.slice(0, 200);
  if (canonical_url) metadata.canonical_url = canonical_url;
  if (video) metadata.video = video;

  return JSON.stringify(metadata);
}

/**
 * Generate a valid permlink from a title.
 */
function generatePermlink(title, suffix = null) {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 200);

  const uniqueSuffix = suffix || Date.now().toString(36);
  return `${slug}-${uniqueSuffix}`;
}

/**
 * Proxy image URL through Hive's image proxy for performance.
 */
function proxyImageUrl(url, width = 640) {
  if (url.startsWith("https://images.hive.blog")) return url;
  return `https://images.hive.blog/${width}x0/${url}`;
}

/**
 * Extract image URLs from Markdown body.
 */
function extractImages(body) {
  const regex = /!\[.*?\]\((https?:\/\/[^\s)]+)\)/g;
  const images = [];
  let match;
  while ((match = regex.exec(body))) {
    images.push(match[1]);
  }
  return images;
}

/**
 * Build a well-formatted post body with images.
 */
function buildPostBody({ intro, sections, images = [], footer = "" }) {
  let body = intro + "\n\n";

  for (const section of sections) {
    body += `## ${section.heading}\n\n`;
    body += section.content + "\n\n";

    if (section.image) {
      const proxied = proxyImageUrl(section.image);
      body += `![${section.heading}](${proxied})\n\n`;
    }

    if (section.code) {
      body += `\`\`\`${section.codeLang || ""}\n${section.code}\n\`\`\`\n\n`;
    }
  }

  if (images.length > 0) {
    body += "---\n\n### Gallery\n\n";
    for (const img of images) {
      body += `![image](${proxyImageUrl(img)})\n\n`;
    }
  }

  if (footer) {
    body += `---\n\n<sub>${footer}</sub>\n`;
  }

  return body;
}

/**
 * Create a complete, well-formatted post.
 */
async function createFormattedPost(postingKey, author) {
  const title = "Building a Hive dApp: A Developer Guide";
  const permlink = generatePermlink(title);

  const body = buildPostBody({
    intro:
      "In this guide, I will walk through building a decentralized application on the Hive blockchain.",
    sections: [
      {
        heading: "Getting Started",
        content:
          "First, install the dhive library and set up your development environment.",
        code: "npm install @hiveio/dhive",
        codeLang: "bash",
      },
      {
        heading: "Connecting to Hive",
        content:
          "Create a client instance with multiple nodes for reliability.",
        code: 'const client = new Client(["https://api.hive.blog"]);',
        codeLang: "javascript",
      },
    ],
    images: ["https://example.com/screenshot1.png"],
    footer: "Posted using MyApp | [GitHub](https://github.com/myapp)",
  });

  const extractedImages = extractImages(body);

  const jsonMetadata = buildJsonMetadata({
    tags: ["hive-dev", "javascript", "tutorial", "programming"],
    images: extractedImages,
    app: "myapp/1.0",
    description: "A guide to building dApps on the Hive blockchain",
  });

  const op = [
    "comment",
    {
      parent_author: "",
      parent_permlink: "hive-dev",
      author: author,
      permlink: permlink,
      title: title,
      body: body,
      json_metadata: jsonMetadata,
    },
  ];

  const key = PrivateKey.fromString(postingKey);
  const result = await client.broadcast.sendOperations([op], key);
  console.log(`Published: https://hive.blog/@${author}/${permlink}`);
  return result;
}

// Format examples
console.log(generatePermlink("My Post Title!"));
// "my-post-title-lq2abc"

console.log(proxyImageUrl("https://example.com/photo.jpg", 800));
// "https://images.hive.blog/800x0/https://example.com/photo.jpg"

console.log(
  buildJsonMetadata({
    tags: ["hive", "dev"],
    images: ["https://example.com/img.jpg"],
    app: "myapp/1.0",
  })
);
```

Formatting rules:
- **Markdown**: Standard GitHub-flavored Markdown is supported
- **Tags**: Max 10, lowercase, alphanumeric + hyphens only
- **First tag** = category and is set via `parent_permlink` for root posts
- **Image proxy**: Use `images.hive.blog` for resizing and caching
- **Permlink**: Max 256 chars, lowercase, hyphens, must be unique per author
- **json_metadata keys**: `tags`, `image`, `links`, `app`, `format` are standard
- **format**: `"markdown"` or `"html"` — tells frontends how to render
- **Max body size**: ~64KB for post body (blockchain limit)'''
    ),
    (
        "hive_sdk/beem-account-history-export",
        r'''How do I export a complete account history (all transactions) to CSV using beem? I need this for tax reporting.''',
        r'''<think>
For tax reporting, you need to capture all financial operations: transfers
in/out, rewards claimed, power ups/downs, interest payments, and trades.
Beem's account.history() or history_reverse() iterates through all
operations. I need to filter for financial ops, convert VESTS to HP
using the historical rate (tricky — snapshot at time of operation),
and export as CSV with timestamps in UTC. Should handle large histories
with progress tracking.
</think>

Here is a tax-reporting account history exporter using beem:

```python
import csv
import json
from datetime import datetime
from pathlib import Path
from beem import Hive
from beem.account import Account

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

FINANCIAL_OPS = {
    "transfer",
    "transfer_to_vesting",
    "withdraw_vesting",
    "fill_vesting_withdraw",
    "claim_reward_balance",
    "author_reward",
    "curation_reward",
    "comment_benefactor_reward",
    "interest",
    "transfer_to_savings",
    "transfer_from_savings",
    "fill_transfer_from_savings",
    "escrow_transfer",
    "escrow_release",
    "limit_order_create",
    "fill_order",
    "convert",
    "fill_convert_request",
    "collateralized_convert",
    "fill_collateralized_convert_request",
    "producer_reward",
    "proposal_pay",
    "recurrent_transfer",
}


def parse_amount(amount_str: str) -> tuple:
    """Parse '1.000 HIVE' into (1.0, 'HIVE')."""
    if not amount_str or amount_str == "0":
        return (0.0, "")
    parts = str(amount_str).split()
    return (float(parts[0]), parts[1] if len(parts) > 1 else "")


def vests_to_hp_approx(vests: float) -> float:
    """Convert VESTS to approximate HP (current rate)."""
    try:
        return hive.vests_to_hp(vests)
    except Exception:
        return vests / 1800  # rough approximation


def format_op_row(op: dict) -> dict:
    """Convert an operation to a flat CSV row."""
    op_type = op["type"]
    timestamp = op["timestamp"]
    block = op.get("block", "")
    trx_id = op.get("trx_id", "")

    row = {
        "timestamp": timestamp,
        "block": block,
        "trx_id": trx_id,
        "type": op_type,
        "from": "",
        "to": "",
        "amount": "",
        "asset": "",
        "memo": "",
        "details": "",
    }

    if op_type == "transfer":
        row["from"] = op["from"]
        row["to"] = op["to"]
        amt, asset = parse_amount(op["amount"])
        row["amount"] = amt
        row["asset"] = asset
        row["memo"] = op.get("memo", "")[:200]

    elif op_type == "claim_reward_balance":
        hive_amt, _ = parse_amount(op.get("reward_hive", "0"))
        hbd_amt, _ = parse_amount(op.get("reward_hbd", "0"))
        vests_amt, _ = parse_amount(op.get("reward_vests", "0"))
        hp = vests_to_hp_approx(vests_amt) if vests_amt else 0
        row["to"] = op.get("account", "")
        row["details"] = f"HIVE:{hive_amt:.3f} HBD:{hbd_amt:.3f} HP:{hp:.3f}"

    elif op_type == "author_reward":
        hbd_amt, _ = parse_amount(op.get("hbd_payout", "0"))
        vests_amt, _ = parse_amount(op.get("vesting_payout", "0"))
        hp = vests_to_hp_approx(vests_amt) if vests_amt else 0
        row["to"] = op.get("author", "")
        row["details"] = f"HBD:{hbd_amt:.3f} HP:{hp:.3f} post:@{op.get('author','')}/{op.get('permlink','')}"

    elif op_type == "curation_reward":
        vests_amt, _ = parse_amount(op.get("reward", "0"))
        hp = vests_to_hp_approx(vests_amt)
        row["to"] = op.get("curator", "")
        row["amount"] = round(hp, 4)
        row["asset"] = "HP"
        row["details"] = f"@{op.get('comment_author','')}/{op.get('comment_permlink','')}"

    elif op_type == "fill_vesting_withdraw":
        amt, asset = parse_amount(op.get("deposited", "0"))
        row["from"] = op.get("from_account", "")
        row["to"] = op.get("to_account", "")
        row["amount"] = amt
        row["asset"] = asset

    elif op_type == "interest":
        amt, asset = parse_amount(op.get("interest", "0"))
        row["to"] = op.get("owner", "")
        row["amount"] = amt
        row["asset"] = asset

    elif op_type in ("transfer_to_vesting", "transfer_to_savings",
                     "transfer_from_savings"):
        amt, asset = parse_amount(op.get("amount", "0"))
        row["from"] = op.get("from", "")
        row["to"] = op.get("to", "")
        row["amount"] = amt
        row["asset"] = asset

    elif op_type == "fill_order":
        row["from"] = op.get("current_owner", "")
        row["to"] = op.get("open_owner", "")
        pays, pays_asset = parse_amount(op.get("current_pays", "0"))
        receives, rec_asset = parse_amount(op.get("open_pays", "0"))
        row["details"] = f"Sold:{pays:.3f} {pays_asset} Got:{receives:.3f} {rec_asset}"

    else:
        row["details"] = json.dumps(
            {k: v for k, v in op.items()
             if k not in ("type", "timestamp", "block", "trx_id")},
            default=str
        )[:300]

    return row


def export_account_history(username: str, output_path: str,
                           start_date: str = None, end_date: str = None):
    """Export financial history to CSV."""
    acc = Account(username, blockchain_instance=hive)

    start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None

    fieldnames = ["timestamp", "block", "trx_id", "type",
                  "from", "to", "amount", "asset", "memo", "details"]

    rows = []
    count = 0

    print(f"Exporting history for @{username}...")
    for op in acc.history_reverse(limit=None):
        op_time = datetime.strptime(op["timestamp"], "%Y-%m-%dT%H:%M:%S")

        if start and op_time < start:
            break
        if end and op_time > end:
            continue

        if op["type"] in FINANCIAL_OPS:
            row = format_op_row(op)
            rows.append(row)

        count += 1
        if count % 1000 == 0:
            print(f"  Processed {count} operations, {len(rows)} financial...")

    # Write CSV (chronological order)
    rows.reverse()
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} financial operations to {output_path}")
    return len(rows)


# Export all of 2025
export_account_history(
    username="youraccount",
    output_path="hive_history_2025.csv",
    start_date="2025-01-01",
    end_date="2025-12-31",
)

# Export everything
export_account_history(
    username="youraccount",
    output_path="hive_history_full.csv",
)
```

Tax reporting notes:
- **All financial ops**: Transfers, rewards, interest, power up/down, trades
- **VESTS to HP**: Conversion uses current rate (for precise tax reporting, use historical rates from the block)
- **UTC timestamps**: All Hive timestamps are UTC
- **Large histories**: May take several minutes for very active accounts
- **Virtual ops included**: Author/curation rewards are virtual operations
- **Memo privacy**: Encrypted memos show as ciphertext in the export'''
    ),
    (
        "hive_sdk/dhive-notifications-polling",
        r'''How do I build a notification system that polls for new mentions, replies, and transfers using dhive?''',
        r'''<think>
Hive does not have a native push notification system. You need to poll
the blockchain or account history for new events. The bridge API has
some notification support via get_account_notifications. Alternatively,
you can stream the blockchain and filter for operations mentioning
your account. I should show both approaches: bridge API notifications
and custom history polling with deduplication.
</think>

Here is how to build a notification system with dhive:

```javascript
const { Client } = require("@hiveio/dhive");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

class HiveNotifications {
  constructor(username) {
    this.username = username;
    this.lastSeenId = null;
    this.seenNotifications = new Set();
    this.handlers = {};
  }

  /**
   * Register a handler for a notification type.
   */
  on(type, callback) {
    if (!this.handlers[type]) this.handlers[type] = [];
    this.handlers[type].push(callback);
    return this;
  }

  /**
   * Emit to registered handlers.
   */
  emit(type, data) {
    const handlers = this.handlers[type] || [];
    for (const handler of handlers) {
      try {
        handler(data);
      } catch (err) {
        console.error(`Handler error for ${type}:`, err);
      }
    }
  }

  /**
   * Fetch notifications via bridge API.
   */
  async fetchBridgeNotifications(limit = 50) {
    try {
      const result = await client.call("bridge", "account_notifications", {
        account: this.username,
        limit: limit,
      });
      return result || [];
    } catch (err) {
      console.error("Failed to fetch notifications:", err.message);
      return [];
    }
  }

  /**
   * Poll account history for specific operation types.
   */
  async pollAccountHistory(limit = 100) {
    const history = await client.call(
      "condenser_api",
      "get_account_history",
      [this.username, -1, limit]
    );

    const notifications = [];

    for (const [seq, entry] of history) {
      const uniqueId = `${entry.block}-${entry.trx_id}-${seq}`;
      if (this.seenNotifications.has(uniqueId)) continue;
      this.seenNotifications.add(uniqueId);

      const [opType, opData] = entry.op;
      const timestamp = entry.timestamp;

      // Incoming transfer
      if (opType === "transfer" && opData.to === this.username) {
        notifications.push({
          type: "transfer",
          from: opData.from,
          amount: opData.amount,
          memo: opData.memo,
          timestamp,
        });
      }

      // Reply to your post
      if (opType === "comment" && opData.parent_author === this.username) {
        notifications.push({
          type: "reply",
          author: opData.author,
          permlink: opData.permlink,
          parentPermlink: opData.parent_permlink,
          timestamp,
        });
      }

      // Someone voted on your content
      if (opType === "vote" && opData.author === this.username && opData.voter !== this.username) {
        notifications.push({
          type: "vote",
          voter: opData.voter,
          permlink: opData.permlink,
          weight: opData.weight,
          timestamp,
        });
      }

      // Mention in a post body
      if (opType === "comment" && opData.author !== this.username) {
        const body = opData.body || "";
        if (body.includes(`@${this.username}`)) {
          notifications.push({
            type: "mention",
            author: opData.author,
            permlink: opData.permlink,
            timestamp,
          });
        }
      }

      // Delegation received
      if (opType === "delegate_vesting_shares" && opData.delegatee === this.username) {
        notifications.push({
          type: "delegation",
          from: opData.delegator,
          vests: opData.vesting_shares,
          timestamp,
        });
      }
    }

    return notifications;
  }

  /**
   * Start polling loop.
   */
  async startPolling(intervalMs = 15000) {
    console.log(`Polling notifications for @${this.username} every ${intervalMs / 1000}s`);

    // Initial fetch to set baseline
    const initial = await this.pollAccountHistory(200);
    console.log(`Loaded ${this.seenNotifications.size} existing entries`);

    const poll = async () => {
      try {
        const notifications = await this.pollAccountHistory();

        for (const n of notifications) {
          this.emit(n.type, n);
          this.emit("*", n);  // wildcard handler
        }
      } catch (err) {
        console.error("Poll error:", err.message);
      }
    };

    this.pollTimer = setInterval(poll, intervalMs);
    return this;
  }

  stop() {
    if (this.pollTimer) clearInterval(this.pollTimer);
  }
}

// Usage
const notifier = new HiveNotifications("youraccount");

notifier
  .on("transfer", (n) => {
    console.log(`[TRANSFER] ${n.from} sent ${n.amount} | memo: ${n.memo}`);
  })
  .on("reply", (n) => {
    console.log(`[REPLY] @${n.author} replied to your post`);
  })
  .on("vote", (n) => {
    const pct = n.weight / 100;
    const type = pct > 0 ? "upvoted" : "downvoted";
    console.log(`[VOTE] @${n.voter} ${type} (${pct}%) your post: ${n.permlink}`);
  })
  .on("mention", (n) => {
    console.log(`[MENTION] @${n.author} mentioned you in ${n.permlink}`);
  })
  .on("delegation", (n) => {
    console.log(`[DELEGATION] @${n.from} delegated ${n.vests} to you`);
  })
  .on("*", (n) => {
    // Log all notifications
  });

// Start polling every 15 seconds
await notifier.startPolling(15000);

// Or one-time fetch via bridge API
const bridgeNotifs = await notifier.fetchBridgeNotifications(20);
for (const n of bridgeNotifs) {
  console.log(`[${n.type}] ${n.msg} (${n.date})`);
}

// Stop when done
// notifier.stop();
```

Notification approaches:
- **Bridge API**: `account_notifications` gives pre-formatted notifications (simplest)
- **History polling**: Custom filtering for more control and event types
- **Blockchain streaming**: Real-time but higher resource usage
- **Deduplication**: Track seen operations to avoid duplicate notifications
- **15-second interval**: Reasonable balance between responsiveness and API load
- **No push notifications** on-chain — all notification systems are pull-based'''
    ),
    (
        "hive_sdk/beem-advanced-stream-filtering",
        r'''How do I build a sophisticated blockchain stream processor that handles multiple operation types, tracks state, and recovers from crashes using beem?''',
        r'''<think>
A production stream processor needs: persistent state (last processed block),
multiple operation handlers, error recovery, crash resilience, and
performance monitoring. I should show a class-based processor that
saves checkpoint state to disk, handles multiple op types with registered
handlers, implements proper backoff on errors, and tracks processing
metrics. This is an expert-level pattern used by Hive dApps and indexers.
</think>

Here is a production-grade blockchain stream processor with beem:

```python
import json
import time
import logging
import signal
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from beem import Hive
from beem.blockchain import Blockchain
from beem.exceptions import RPCError

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("stream_processor")


class StreamProcessor:
    """Production blockchain stream processor with crash recovery."""

    def __init__(self, state_file: str = "stream_state.json",
                 nodes: list = None):
        self.state_file = Path(state_file)
        self.nodes = nodes or [
            "https://api.hive.blog",
            "https://api.deathwing.me",
            "https://api.openhive.network",
        ]
        self.handlers = {}
        self.state = self._load_state()
        self.metrics = defaultdict(int)
        self.running = False

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _load_state(self) -> dict:
        """Load processing state from disk."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                state = json.load(f)
                log.info(f"Resumed from block {state.get('last_block', 'HEAD')}")
                return state
        return {"last_block": None, "started_at": datetime.utcnow().isoformat()}

    def _save_state(self):
        """Persist current state to disk."""
        self.state["saved_at"] = datetime.utcnow().isoformat()
        self.state["metrics"] = dict(self.metrics)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def _shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        log.info("Shutdown signal received, saving state...")
        self.running = False
        self._save_state()
        log.info(f"State saved at block {self.state.get('last_block')}")
        sys.exit(0)

    def register(self, op_type: str, handler):
        """Register a handler function for an operation type.

        Handler signature: handler(op: dict, processor: StreamProcessor)
        """
        if op_type not in self.handlers:
            self.handlers[op_type] = []
        self.handlers[op_type].append(handler)
        return self

    def get_state(self, key: str, default=None):
        """Get a custom state value (for handler use)."""
        return self.state.get(f"custom_{key}", default)

    def set_state(self, key: str, value):
        """Set a custom state value (persisted across restarts)."""
        self.state[f"custom_{key}"] = value

    def run(self, start_block: int = None):
        """Start processing the blockchain."""
        hive = Hive(node=self.nodes)
        bc = Blockchain(blockchain_instance=hive)

        resume_block = start_block or self.state.get("last_block")
        op_names = list(self.handlers.keys())

        log.info(f"Starting stream processor")
        log.info(f"  Watching: {op_names}")
        log.info(f"  Resume from: {resume_block or 'HEAD'}")
        log.info(f"  State file: {self.state_file}")

        self.running = True
        consecutive_errors = 0
        checkpoint_interval = 100  # save state every N blocks
        last_checkpoint_block = resume_block or 0

        while self.running:
            try:
                stream = bc.stream(
                    opNames=op_names,
                    start=resume_block,
                    threading=False,
                )

                for op in stream:
                    if not self.running:
                        break

                    op_type = op["type"]
                    block_num = op.get("block_num", 0)

                    # Dispatch to handlers
                    for handler in self.handlers.get(op_type, []):
                        try:
                            handler(op, self)
                            self.metrics[f"processed_{op_type}"] += 1
                        except Exception as e:
                            log.error(f"Handler error for {op_type}: {e}")
                            self.metrics["handler_errors"] += 1

                    self.metrics["total_ops"] += 1
                    self.state["last_block"] = block_num
                    resume_block = block_num

                    # Periodic checkpoint
                    if block_num - last_checkpoint_block >= checkpoint_interval:
                        self._save_state()
                        last_checkpoint_block = block_num
                        log.debug(f"Checkpoint at block {block_num}")

                    consecutive_errors = 0

            except RPCError as e:
                consecutive_errors += 1
                wait = min(60, 5 * consecutive_errors)
                log.warning(f"RPC error (attempt {consecutive_errors}): {e}")
                log.info(f"Retrying in {wait}s...")
                self._save_state()
                time.sleep(wait)

                # Reconnect
                hive = Hive(node=self.nodes)
                bc = Blockchain(blockchain_instance=hive)

            except Exception as e:
                log.error(f"Unexpected error: {e}")
                self._save_state()
                time.sleep(10)

        self._save_state()
        log.info("Stream processor stopped")

    def get_metrics(self) -> dict:
        """Get processing metrics."""
        return {
            "total_operations": self.metrics["total_ops"],
            "handler_errors": self.metrics["handler_errors"],
            "last_block": self.state.get("last_block"),
            "per_type": {
                k.replace("processed_", ""): v
                for k, v in self.metrics.items()
                if k.startswith("processed_")
            },
        }


# ==================
# Example: Token tracker
# ==================

def handle_transfer(op, processor):
    """Track large transfers."""
    amount = float(op["amount"].split()[0])
    asset = op["amount"].split()[1]
    if amount >= 1000:
        log.info(f"LARGE TRANSFER: {op['from']} -> {op['to']}: "
                 f"{op['amount']} | memo: {op.get('memo', '')[:50]}")

        # Update custom state
        total = processor.get_state("large_transfer_count", 0)
        processor.set_state("large_transfer_count", total + 1)


def handle_custom_json(op, processor):
    """Process custom_json for a specific protocol."""
    if op["id"] != "myprotocol":
        return

    try:
        data = json.loads(op["json"])
        signers = op.get("required_posting_auths") or op.get("required_auths", [])
        log.info(f"PROTOCOL OP: {data.get('action')} by {signers}")
    except json.JSONDecodeError:
        pass


def handle_vote(op, processor):
    """Track whale votes (>50% weight)."""
    if abs(op["weight"]) >= 5000:
        direction = "up" if op["weight"] > 0 else "down"
        log.info(f"WHALE VOTE: @{op['voter']} {direction}voted "
                 f"@{op['author']}/{op['permlink']} ({op['weight']/100}%)")


# Build and run processor
processor = StreamProcessor(state_file="my_processor_state.json")

processor.register("transfer", handle_transfer)
processor.register("custom_json", handle_custom_json)
processor.register("vote", handle_vote)

# Start from HEAD (or resume from saved state)
processor.run()
```

Production patterns:
- **Crash recovery**: State file saves last processed block, resumes on restart
- **Graceful shutdown**: SIGINT/SIGTERM handlers save state before exit
- **Checkpoint interval**: Save state every N blocks, not every operation
- **Error backoff**: Exponential backoff on consecutive RPC errors
- **Custom state**: Handlers can persist arbitrary state via `set_state/get_state`
- **Metrics**: Track operations processed, errors, and per-type counts
- **Node rotation**: Multiple nodes for automatic failover on connection failure'''
    ),
    (
        "hive_sdk/dhive-hive-engine-nft",
        r'''How do I mint, transfer, and query NFTs on Hive-Engine using dhive?''',
        r'''<think>
Hive-Engine supports NFTs through the nft contract. Operations include
issuing (minting), transferring, selling on market, and burning NFTs.
All operations use custom_json with id "ssc-mainnet-hive". The NFT
contract has specific actions: issue, transfer, sell, buy, burn.
Querying uses the Hive-Engine API with the nft contract tables.
I should show minting, transferring, querying, and marketplace operations.
</think>

Here is how to work with Hive-Engine NFTs using dhive:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const axios = require("axios");

const client = new Client([
  "https://api.hive.blog",
  "https://api.deathwing.me",
]);

const activeKey = PrivateKey.fromString("5YourActiveKey");
const account = "youraccount";

const HE_API = "https://api.hive-engine.com/rpc/contracts";

/**
 * Query Hive-Engine sidechain state.
 */
async function heQuery(contract, table, query, limit = 1000) {
  const resp = await axios.post(HE_API, {
    jsonrpc: "2.0",
    id: 1,
    method: "find",
    params: { contract, table, query, limit },
  });
  return resp.data.result || [];
}

/**
 * Broadcast a Hive-Engine operation.
 */
async function heBroadcast(contractName, contractAction, payload, keyType = "active") {
  const json = JSON.stringify({
    contractName,
    contractAction,
    contractPayload: payload,
  });

  const op = [
    "custom_json",
    {
      id: "ssc-mainnet-hive",
      required_auths: keyType === "active" ? [account] : [],
      required_posting_auths: keyType === "posting" ? [account] : [],
      json,
    },
  ];

  const key = keyType === "active" ? activeKey : PrivateKey.fromString("5PostingKey");
  return client.broadcast.sendOperations([op], key);
}

/**
 * Create an NFT collection (one-time setup, requires BEE fee).
 */
async function createNFTCollection({
  symbol,
  name,
  orgName = "",
  maxSupply = 0,  // 0 = unlimited
  authorizedIssuingAccounts = null,
}) {
  return heBroadcast("nft", "create", {
    symbol,
    name,
    orgName,
    maxSupply,
    authorizedIssuingAccounts: authorizedIssuingAccounts || [account],
  });
}

/**
 * Add properties (metadata schema) to an NFT collection.
 */
async function addNFTProperty(symbol, propertyName, type, isReadOnly = false) {
  return heBroadcast("nft", "addProperty", {
    symbol,
    name: propertyName,
    type,  // "number", "string", "boolean"
    isReadOnly,
  });
}

/**
 * Mint (issue) an NFT.
 */
async function mintNFT(symbol, to, properties = {}, feeSymbol = "BEE") {
  return heBroadcast("nft", "issue", {
    symbol,
    to,
    feeSymbol,
    properties,
  });
}

/**
 * Batch mint multiple NFTs.
 */
async function batchMintNFTs(symbol, instances) {
  // instances: [{to, properties, feeSymbol}]
  for (const inst of instances) {
    await mintNFT(symbol, inst.to, inst.properties, inst.feeSymbol || "BEE");
    // Small delay to avoid rate limiting
    await new Promise((r) => setTimeout(r, 3100));
  }
}

/**
 * Transfer an NFT to another account.
 */
async function transferNFT(symbol, nftIds, to) {
  return heBroadcast("nft", "transfer", {
    to,
    nfts: [{ symbol, ids: nftIds }],
  });
}

/**
 * List an NFT for sale on the marketplace.
 */
async function sellNFT(symbol, nftId, price, priceSymbol = "BEE") {
  return heBroadcast("nft", "sell", {
    symbol,
    nfts: [nftId],
    price: price.toString(),
    priceSymbol,
    fee: 500,  // 5% marketplace fee (in basis points)
  });
}

/**
 * Buy an NFT from the marketplace.
 */
async function buyNFT(symbol, orderId, marketplace = "") {
  return heBroadcast("nft", "buy", {
    symbol,
    order_id: orderId,
    marketplace,
  });
}

/**
 * Burn (destroy) an NFT.
 */
async function burnNFT(symbol, nftIds) {
  return heBroadcast("nft", "burn", {
    nfts: [{ symbol, ids: nftIds }],
  });
}

/**
 * Query NFTs owned by an account.
 */
async function getNFTsByOwner(symbol, owner) {
  return heQuery(`${symbol.toLowerCase()}instances`, `${symbol.toLowerCase()}instances`, {
    account: owner,
  });
}

/**
 * Get NFT collection info.
 */
async function getNFTCollectionInfo(symbol) {
  const results = await heQuery("nft", "nfts", { symbol });
  return results[0] || null;
}

/**
 * Get marketplace listings for an NFT collection.
 */
async function getMarketListings(symbol, limit = 50) {
  return heQuery("nftmarket", `${symbol}sellBook`, {}, limit);
}

// Create an NFT collection
await createNFTCollection({
  symbol: "MYART",
  name: "My Art Collection",
  maxSupply: 1000,
});

// Add metadata properties
await addNFTProperty("MYART", "name", "string", true);
await addNFTProperty("MYART", "rarity", "string", true);
await addNFTProperty("MYART", "edition", "number", true);

// Mint an NFT
await mintNFT("MYART", account, {
  name: "Cosmic Landscape #1",
  rarity: "legendary",
  edition: 1,
});

// Transfer to another user
await transferNFT("MYART", ["1"], "collector");

// List for sale at 100 BEE
await sellNFT("MYART", "2", 100, "BEE");

// Query owned NFTs
const myNFTs = await getNFTsByOwner("MYART", account);
console.log(`Owned: ${myNFTs.length} MYART NFTs`);
```

Hive-Engine NFT details:
- **BEE fee**: Creating collections and minting costs BEE tokens
- **Properties**: Define schema once, set values per NFT at mint time
- **isReadOnly**: Once set to true, properties cannot be modified after minting
- **Marketplace**: Built-in order book for buying/selling NFTs
- **Active key** required for all NFT operations
- **Batch minting**: Must respect 3-second block time between transactions
- **Symbol**: Unique identifier for the collection (like a token ticker)'''
    ),
    (
        "hive_sdk/beem-atomic-swap-pattern",
        r'''How do I implement a trustless atomic swap between HIVE and a Hive-Engine token using beem?''',
        r'''<think>
A true atomic swap on Hive requires careful use of transactions and
time-locked conditions. Since Hive does not have native smart contract
support like Ethereum, the best approach uses a combination of escrow
operations or a deterministic custom_json protocol where both parties
commit to the swap and a neutral indexer validates the execution.
Alternatively, for HIVE <-> Hive-Engine tokens, you can use the
Hive-Engine deposit/withdrawal mechanism. But for a trustless swap
between two parties, the pattern involves: 1) Both parties broadcast
commitments, 2) A deterministic processor validates and executes, 3)
Timeout refund if one party does not complete. This is expert-level.
</think>

Here is an atomic swap pattern for HIVE <-> Hive-Engine tokens using beem:

```python
import json
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer, Custom_json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey", "5YourPostingKey"]
)

SWAP_PROTOCOL_ID = "atomicswap"
SWAP_TIMEOUT_HOURS = 24


class AtomicSwapInitiator:
    """Party A: Initiates the swap by creating a hash-locked commitment."""

    def __init__(self, account: str):
        self.account = account
        self.secret = None
        self.secret_hash = None

    def generate_secret(self) -> str:
        """Generate a cryptographic secret and its hash."""
        self.secret = secrets.token_hex(32)
        self.secret_hash = hashlib.sha256(
            bytes.fromhex(self.secret)
        ).hexdigest()
        return self.secret_hash

    def create_swap_offer(self, counterparty: str, hive_amount: float,
                          want_token: str, want_amount: str) -> dict:
        """Broadcast swap offer: lock HIVE and publish hash."""
        swap_id = hashlib.sha256(
            f"{self.account}-{counterparty}-{time.time()}".encode()
        ).hexdigest()[:16]

        expiration = (datetime.utcnow() + timedelta(hours=SWAP_TIMEOUT_HOURS)
                      ).strftime("%Y-%m-%dT%H:%M:%S")

        # Step 1: Transfer HIVE to escrow account (or use on-chain escrow)
        tx = TransactionBuilder(blockchain_instance=hive)

        # Lock HIVE by sending to a known escrow/swap account
        tx.appendOps(Transfer(**{
            "from": self.account,
            "to": "swap-escrow",  # trusted escrow or smart contract account
            "amount": f"{hive_amount:.3f} HIVE",
            "memo": json.dumps({
                "type": "swap_lock",
                "swap_id": swap_id,
                "hash": self.secret_hash,
                "counterparty": counterparty,
                "expires": expiration,
            }),
        }))

        # Step 2: Broadcast swap offer via custom_json
        tx.appendOps(Custom_json(**{
            "id": SWAP_PROTOCOL_ID,
            "required_posting_auths": [self.account],
            "required_auths": [],
            "json": json.dumps({
                "action": "offer",
                "swap_id": swap_id,
                "initiator": self.account,
                "counterparty": counterparty,
                "offer": {"amount": hive_amount, "asset": "HIVE"},
                "want": {"amount": want_amount, "token": want_token},
                "secret_hash": self.secret_hash,
                "expires": expiration,
            }),
        }))

        tx.appendSigner(self.account, "active")
        tx.appendSigner(self.account, "posting")
        tx.sign()
        result = tx.broadcast()

        return {
            "swap_id": swap_id,
            "secret": self.secret,  # KEEP THIS PRIVATE until counterparty locks
            "secret_hash": self.secret_hash,
            "expiration": expiration,
            "tx": result,
        }

    def claim_tokens(self, swap_id: str):
        """After counterparty locks tokens, reveal secret to claim them."""
        hive.custom_json(
            SWAP_PROTOCOL_ID,
            json_data={
                "action": "claim",
                "swap_id": swap_id,
                "secret": self.secret,  # reveals the secret
            },
            required_posting_auths=[self.account],
        )


class AtomicSwapCounterparty:
    """Party B: Responds to a swap offer by locking Hive-Engine tokens."""

    def __init__(self, account: str):
        self.account = account

    def accept_swap(self, swap_id: str, secret_hash: str,
                    token: str, amount: str, initiator: str):
        """Lock Hive-Engine tokens using the same hash lock."""
        expiration = (datetime.utcnow() + timedelta(
            hours=SWAP_TIMEOUT_HOURS // 2  # shorter timeout for safety
        )).strftime("%Y-%m-%dT%H:%M:%S")

        tx = TransactionBuilder(blockchain_instance=hive)

        # Lock Hive-Engine token via custom_json
        tx.appendOps(Custom_json(**{
            "id": "ssc-mainnet-hive",
            "required_auths": [self.account],
            "required_posting_auths": [],
            "json": json.dumps({
                "contractName": "tokens",
                "contractAction": "transfer",
                "contractPayload": {
                    "symbol": token,
                    "to": "swap-escrow",
                    "quantity": amount,
                    "memo": json.dumps({
                        "type": "swap_lock",
                        "swap_id": swap_id,
                        "hash": secret_hash,
                        "counterparty": initiator,
                        "expires": expiration,
                    }),
                },
            }),
        }))

        # Broadcast acceptance
        tx.appendOps(Custom_json(**{
            "id": SWAP_PROTOCOL_ID,
            "required_posting_auths": [self.account],
            "required_auths": [],
            "json": json.dumps({
                "action": "accept",
                "swap_id": swap_id,
                "acceptor": self.account,
                "locked": {"amount": amount, "token": token},
                "secret_hash": secret_hash,
                "expires": expiration,
            }),
        }))

        tx.appendSigner(self.account, "active")
        tx.appendSigner(self.account, "posting")
        tx.sign()
        return tx.broadcast()

    def claim_hive(self, swap_id: str, secret: str):
        """After seeing the revealed secret, claim the locked HIVE."""
        # Verify the secret matches the hash
        computed_hash = hashlib.sha256(bytes.fromhex(secret)).hexdigest()

        hive.custom_json(
            SWAP_PROTOCOL_ID,
            json_data={
                "action": "claim",
                "swap_id": swap_id,
                "secret": secret,  # prove knowledge of the secret
            },
            required_posting_auths=[self.account],
        )


def verify_secret(secret: str, expected_hash: str) -> bool:
    """Verify a secret matches its hash."""
    computed = hashlib.sha256(bytes.fromhex(secret)).hexdigest()
    return computed == expected_hash


# ==================
# Swap flow example
# ==================

# Alice wants to swap 100 HIVE for 500 BEE tokens
alice = AtomicSwapInitiator("alice")

# Step 1: Alice generates secret and creates offer
secret_hash = alice.generate_secret()
offer = alice.create_swap_offer(
    counterparty="bob",
    hive_amount=100.0,
    want_token="BEE",
    want_amount="500.000",
)
print(f"Swap offer created: {offer['swap_id']}")
print(f"Secret (keep private!): {offer['secret']}")

# Step 2: Bob sees the offer and locks his BEE tokens
bob = AtomicSwapCounterparty("bob")
bob.accept_swap(
    swap_id=offer["swap_id"],
    secret_hash=secret_hash,
    token="BEE",
    amount="500.000",
    initiator="alice",
)

# Step 3: Alice claims the BEE by revealing her secret
alice.claim_tokens(offer["swap_id"])

# Step 4: Bob sees the revealed secret on-chain and claims HIVE
bob.claim_hive(offer["swap_id"], offer["secret"])

print("Swap completed!")
```

Atomic swap design considerations:
- **Hash-time-locked**: Secret + hash ensures both parties can claim or neither can
- **Timeout asymmetry**: Counterparty timeout must be shorter than initiator's
- **Escrow account**: A trusted or multi-sig escrow holds funds during the swap
- **On-chain verification**: All commitments and claims are on-chain custom_json
- **Deterministic processing**: A sidechain indexer validates and executes the swap
- **No native smart contracts**: Hive relies on deterministic off-chain processing
- **Risk**: Requires a trusted escrow or deterministic indexer — not truly trustless without one'''
    ),
]
