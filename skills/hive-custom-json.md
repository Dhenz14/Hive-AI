# Hive Custom JSON Operations Skill File

## Operation Structure

Every custom_json operation has exactly four fields:

```json
{
    "required_auths": [],              // array of account names requiring ACTIVE key
    "required_posting_auths": ["user"],// array of account names requiring POSTING key
    "id": "app_identifier",           // string, max 32 chars, identifies the application
    "json": "{\"key\":\"value\"}"     // stringified JSON payload, max 8192 bytes
}
```

**Rules:**
- Exactly one of `required_auths` or `required_posting_auths` must be non-empty
- Both can be non-empty (different accounts with different auth levels)
- The `id` field is a plain string, not JSON
- The `json` field MUST be a stringified JSON string (not a raw object)
- Maximum `json` payload size: **8,192 bytes** (characters)
- Maximum block size: **65,536 bytes**
- Maximum **5 custom_json operations per transaction** per account

## Required Authorities

### Posting Authority (`required_posting_auths`)
Used for social/non-financial operations:
- Social app interactions (likes, follows, reblogs)
- Game actions that don't involve token transfers
- Content metadata updates
- Community operations

### Active Authority (`required_auths`)
Used for financial/security-sensitive operations:
- Hive-Engine token operations (transfers, staking, market orders)
- Operations that move value
- Smart contract interactions requiring trust

### Example: Posting vs Active

```python
# Posting authority - social action
hive.custom_json(
    id="follow",
    json_data=["follow", {"follower": "alice", "following": "bob", "what": ["blog"]}],
    required_posting_auths=["alice"]
)

# Active authority - token transfer on Hive-Engine
hive.custom_json(
    id="ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "transfer",
        "contractPayload": {"symbol": "BEE", "to": "bob", "quantity": "100", "memo": ""}
    },
    required_auths=["alice"]
)
```

## Common Custom JSON IDs

### Core Hive Operations

| ID | Authority | Purpose |
|---|---|---|
| `follow` | Posting | Follow/unfollow/mute accounts, reblog posts |
| `community` | Posting | Community operations (subscribe, pin, mute) |
| `notify` | Posting | Notification preferences |
| `reblog` | Posting | Reblog/resteem a post |

#### Follow Operation Examples

```json
// Follow a user
{"id": "follow", "json": "[\"follow\",{\"follower\":\"alice\",\"following\":\"bob\",\"what\":[\"blog\"]}]"}

// Unfollow
{"id": "follow", "json": "[\"follow\",{\"follower\":\"alice\",\"following\":\"bob\",\"what\":[]}]"}

// Mute
{"id": "follow", "json": "[\"follow\",{\"follower\":\"alice\",\"following\":\"bob\",\"what\":[\"ignore\"]}]"}

// Reblog
{"id": "follow", "json": "[\"reblog\",{\"account\":\"alice\",\"author\":\"bob\",\"permlink\":\"great-post\"}]"}
```

### Hive-Engine (Layer 2 Tokens)

| ID | Authority | Purpose |
|---|---|---|
| `ssc-mainnet-hive` | Active | All Hive-Engine sidechain operations |

#### Hive-Engine Operation Structure

All Hive-Engine operations use the same wrapper:

```json
{
    "required_auths": ["username"],
    "required_posting_auths": [],
    "id": "ssc-mainnet-hive",
    "json": "{\"contractName\":\"...\",\"contractAction\":\"...\",\"contractPayload\":{...}}"
}
```

#### Common Hive-Engine Actions

```json
// Token transfer
{"contractName":"tokens","contractAction":"transfer","contractPayload":{"symbol":"BEE","to":"recipient","quantity":"10","memo":"payment"}}

// Token stake
{"contractName":"tokens","contractAction":"stake","contractPayload":{"to":"myaccount","symbol":"BEE","quantity":"100"}}

// Token unstake (starts cooldown)
{"contractName":"tokens","contractAction":"unstake","contractPayload":{"symbol":"BEE","quantity":"50"}}

// Cancel pending unstake
{"contractName":"tokens","contractAction":"cancelUnstake","contractPayload":{"txID":"txid_from_unstake"}}

// Delegate tokens
{"contractName":"tokens","contractAction":"delegate","contractPayload":{"to":"recipient","symbol":"BEE","quantity":"100"}}

// Undelegate
{"contractName":"tokens","contractAction":"undelegate","contractPayload":{"from":"recipient","symbol":"BEE","quantity":"100"}}

// Market buy order
{"contractName":"market","contractAction":"buy","contractPayload":{"symbol":"BEE","quantity":"10","price":"0.5"}}

// Market sell order
{"contractName":"market","contractAction":"sell","contractPayload":{"symbol":"BEE","quantity":"10","price":"0.5"}}

// Cancel market order
{"contractName":"market","contractAction":"cancel","contractPayload":{"type":"buy","id":"order_id"}}

// Create a new token (requires BEE fee)
{"contractName":"tokens","contractAction":"create","contractPayload":{"symbol":"MYTOKEN","name":"My Token","precision":8,"maxSupply":"1000000","url":"https://myapp.com","isSignedWithActiveKey":true}}

// Issue tokens (token creator only)
{"contractName":"tokens","contractAction":"issue","contractPayload":{"symbol":"MYTOKEN","to":"recipient","quantity":"1000","isSignedWithActiveKey":true}}

// NFT create
{"contractName":"nft","contractAction":"create","contractPayload":{"symbol":"MYNFT","name":"My NFT Collection","maxSupply":10000,"isSignedWithActiveKey":true}}
```

### Splinterlands Game

| ID | Authority | Purpose |
|---|---|---|
| `sm_find_match` | Posting | Queue for a battle |
| `sm_submit_team` | Posting | Submit team hash for battle |
| `sm_team_reveal` | Posting | Reveal team after both submit |
| `sm_token_transfer` | Active | Transfer in-game tokens |
| `sm_sell_cards` | Active | List cards for sale on market |
| `sm_market_purchase` | Active | Buy cards from market |
| `sm_delegate_cards` | Posting | Delegate cards to another player |
| `sm_undelegate_cards` | Posting | Remove card delegation |
| `sm_stake_tokens` | Active | Stake SPS tokens |
| `sm_claim_reward` | Posting | Claim earned rewards |

#### Splinterlands Examples

```json
// Find a match
{"id":"sm_find_match","json":"{\"match_type\":\"Ranked\",\"app\":\"splinterlands/0.7.139\",\"n\":\"unique_nonce\"}"}

// Submit team (hashed)
{"id":"sm_submit_team","json":"{\"trx_id\":\"match_trx_id\",\"team_hash\":\"md5hash\",\"app\":\"splinterlands/0.7.139\"}"}

// Reveal team
{"id":"sm_team_reveal","json":"{\"trx_id\":\"match_trx_id\",\"team_hash\":\"md5hash\",\"summoner\":\"C1-123-abc\",\"monsters\":[\"C2-456-def\",\"C3-789-ghi\"],\"secret\":\"random_secret\",\"app\":\"splinterlands/0.7.139\"}"}

// Token transfer
{"id":"sm_token_transfer","json":"{\"token\":\"SPS\",\"qty\":100,\"to\":\"recipient\",\"app\":\"splinterlands/0.7.139\"}"}
```

### Other Notable IDs

| ID | Authority | Purpose |
|---|---|---|
| `rc` | Active | RC delegation operations |
| `witness` | Active | Witness-related custom ops |
| `podping` | Posting | Podcast ping notifications (Podping protocol) |
| `hivemind` | Posting | Hivemind social layer operations |
| `spkcc` | Active/Posting | SPK Network operations |

## Best Practices

1. **Choose the right authority**: Use posting key unless the operation involves value transfer
2. **Minimize payload size**: Stay well under 8,192 bytes; compress if needed
3. **Use consistent ID naming**: Follow `appname` or `appname_action` convention
4. **Include app version**: Add `"app": "myapp/1.0"` in your JSON for attribution
5. **Validate JSON before broadcast**: Invalid JSON in the `json` field will still be stored on-chain but will waste RC
6. **Batch operations**: You can include up to 5 custom_json ops in a single transaction
7. **Idempotency**: Design operations to be safely replayable (blockchain may fork)
8. **Nonce for uniqueness**: Include a random nonce field to prevent duplicate detection issues

## Python (beem) Complete Example

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.openhive.network"],
    keys=["5Jxxxxxxxxx_POSTING_WIF"]
)

# Single custom_json
hive.custom_json(
    id="myapp",
    json_data={"action": "update_profile", "data": {"bio": "Hello world"}},
    required_posting_auths=["myaccount"]
)

# Multiple custom_json in one transaction
tx = TransactionBuilder(blockchain_instance=hive)
for i in range(5):  # max 5 per tx
    op = Custom_json(**{
        "required_auths": [],
        "required_posting_auths": ["myaccount"],
        "id": "myapp",
        "json": json.dumps({"action": "batch_item", "index": i})
    })
    tx.appendOps(op)
tx.appendWif("5Jxxxxxxxxx_POSTING_WIF")
tx.sign()
tx.broadcast()
```

## JavaScript (dhive) Complete Example

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client(["https://api.hive.blog", "https://api.openhive.network"]);
const postingKey = PrivateKey.fromString("5Jxxxxxxxxx_POSTING_WIF");

// Single custom_json
await client.broadcast.json({
    required_auths: [],
    required_posting_auths: ["myaccount"],
    id: "myapp",
    json: JSON.stringify({ action: "update_profile", data: { bio: "Hello world" } })
}, postingKey);

// Multiple operations in one transaction (using sendOperations)
const ops = [];
for (let i = 0; i < 5; i++) {
    ops.push(["custom_json", {
        required_auths: [],
        required_posting_auths: ["myaccount"],
        id: "myapp",
        json: JSON.stringify({ action: "batch_item", index: i })
    }]);
}
await client.broadcast.sendOperations(ops, postingKey);
```
