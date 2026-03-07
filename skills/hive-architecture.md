# Hive Architecture Skill File

## Block Structure

### Block Timing
- **Block interval**: 3 seconds
- **Blocks per day**: ~28,800
- **Block size limit**: 65,536 bytes (64 KB)
- **Irreversibility**: ~45 seconds (15 blocks, confirmed by 2/3+ witnesses)

### Block Format

```json
{
    "block_id": "0123456789abcdef0123456789abcdef01234567",
    "previous": "0123456789abcdef0123456789abcdef01234566",
    "timestamp": "2025-01-15T12:00:00",
    "witness": "blocktrades",
    "transaction_merkle_root": "abcdef1234567890abcdef1234567890abcdef12",
    "extensions": [],
    "witness_signature": "2000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "transactions": [
        {
            "ref_block_num": 12345,
            "ref_block_prefix": 3456789012,
            "expiration": "2025-01-15T12:01:00",
            "operations": [
                ["vote", {
                    "voter": "alice",
                    "author": "bob",
                    "permlink": "my-post",
                    "weight": 10000
                }]
            ],
            "extensions": [],
            "signatures": ["2000000000..."]
        }
    ]
}
```

### Transaction Format

```json
{
    "ref_block_num": 12345,          // lower 16 bits of recent block number
    "ref_block_prefix": 3456789012,  // first 4 bytes of block ID (prevents replay)
    "expiration": "2025-01-15T12:01:00",  // max 1 hour in the future
    "operations": [                  // array of [op_type, op_data] pairs
        ["transfer", {
            "from": "alice",
            "to": "bob",
            "amount": "1.000 HIVE",
            "memo": "payment"
        }]
    ],
    "extensions": [],
    "signatures": ["hex_signature"]  // ECDSA signatures
}
```

### Key Transaction Rules
- `ref_block_num` and `ref_block_prefix` must reference a recent block (prevents replay)
- `expiration` must be within 1 hour of head block time
- Transactions are validated against the TaPoS (Transaction as Proof of Stake) mechanism
- A transaction can contain multiple operations (different types allowed)
- All operations in a transaction succeed or fail atomically

---

## Operation Types

### Common Operations (by type ID)

| ID | Name | Key Required | Description |
|---|---|---|---|
| 0 | `vote` | Posting | Vote on content |
| 1 | `comment` | Posting | Post or reply |
| 2 | `transfer` | Active | Transfer HIVE/HBD |
| 3 | `transfer_to_vesting` | Active | Power up (HIVE to HP) |
| 4 | `withdraw_vesting` | Active | Power down (HP to HIVE) |
| 5 | `limit_order_create` | Active | Create market order |
| 6 | `limit_order_cancel` | Active | Cancel market order |
| 7 | `feed_publish` | Active | Witness price feed |
| 8 | `convert` | Active | Convert HBD to HIVE |
| 9 | `account_create` | Active | Create new account |
| 10 | `account_update` | Owner/Active | Update account auth |
| 12 | `witness_update` | Active | Update witness params |
| 13 | `account_witness_vote` | Active | Vote for witness |
| 14 | `account_witness_proxy` | Active | Set witness vote proxy |
| 18 | `custom_json` | Posting/Active | Custom JSON data |
| 19 | `comment_options` | Posting | Set post payout options |
| 22 | `claim_account` | Active | Claim discounted account token |
| 23 | `create_claimed_account` | Active | Use claimed token |
| 32 | `transfer_to_savings` | Active | Move to savings |
| 33 | `transfer_from_savings` | Active | Withdraw from savings |
| 39 | `claim_reward_balance` | Posting | Claim pending rewards |
| 40 | `delegate_vesting_shares` | Active | Delegate HP |
| 45 | `create_proposal` | Active | Create DHF proposal |
| 46 | `update_proposal_votes` | Active | Vote on DHF proposal |
| 47 | `remove_proposal` | Active | Remove own proposal |
| 48 | `update_proposal` | Active | Edit own proposal |
| 49 | `collateralized_convert` | Active | HIVE to HBD conversion |
| 50 | `recurrent_transfer` | Active | Recurring payments |

---

## Consensus: DPoS (Delegated Proof of Stake)

### Witness System
- **Top 20 witnesses**: Elected by HP-weighted votes, produce blocks in round-robin
- **21st slot**: Rotates among backup witnesses, weighted by votes
- **Round**: 21 blocks = 63 seconds (each of 21 slots produces 1 block)
- **Schedule**: Shuffled each round to prevent prediction

### Witness Responsibilities
1. Produce blocks on schedule (miss = skip, no penalty but hurts reputation)
2. Set chain parameters:
   - `account_creation_fee`: Minimum HP to create an account
   - `maximum_block_size`: Max block size (up to hard limit)
   - `hbd_interest_rate`: Interest rate on HBD savings (basis points)
   - `hbd_exchange_rate`: Price feed for HBD/HIVE conversion
3. Run a reliable full node
4. Apply blockchain updates (hard forks)

### Block Production Flow

```
Round N:
  [witness_1] -> Block 1 (3s)
  [witness_2] -> Block 2 (3s)
  ...
  [witness_20] -> Block 20 (3s)
  [backup_witness_X] -> Block 21 (3s)

Round N+1:
  [shuffled order of same 20 + 1 backup]
  ...
```

### Irreversibility
- A block becomes **irreversible** when 2/3 of active witnesses have built on top of it
- Typically ~15 blocks (~45 seconds)
- Irreversible blocks can never be reverted (safe for confirmed transactions)

### Hard Forks
- Protocol upgrades activated when 17/21 top witnesses signal support
- Major recent hard forks:
  - **HF24**: Hive genesis (fork from Steem, March 2020)
  - **HF25**: Linear curation, collateralized conversions, recurring transfers
  - **HF26**: RC delegations, faster powerdowns for small accounts
  - **HF27**: Witness scheduling improvements
  - **HF28**: Latest protocol updates

---

## API Architecture

### API Namespaces

Hive nodes expose multiple API namespaces, each serving different data:

| Namespace | Methods | Purpose |
|-----------|---------|---------|
| `condenser_api` | ~85 | Legacy API, easiest to use, broadest compatibility |
| `database_api` | ~46 | Direct database access, more structured responses |
| `block_api` | ~3 | Fetch blocks and block ranges |
| `account_history_api` | ~3 | Account operation history |
| `account_by_key_api` | ~1 | Look up accounts by public key |
| `network_broadcast_api` | ~1 | Broadcast transactions |
| `rc_api` | ~4 | Resource credit queries |
| `market_history_api` | ~4 | Internal HIVE/HBD market data |
| `follow_api` | ~5 | Follows, reblogs (deprecated, use hivemind) |
| `tags_api` | ~8 | Tag/trending queries (deprecated, use hivemind) |
| `wallet_bridge_api` | ~20+ | Wallet-focused API methods |
| `jsonrpc` | ~2 | List available methods |

### Making API Calls

All APIs use JSON-RPC 2.0 format:

```bash
# condenser_api style (positional params)
curl -s -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"condenser_api.get_accounts","params":[["username"]],"id":1}' \
  https://api.hive.blog

# database_api style (named params)
curl -s -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"database_api.find_accounts","params":{"accounts":["username"]},"id":1}' \
  https://api.hive.blog
```

### Key condenser_api Methods

```bash
# Account info
condenser_api.get_accounts                    # [["user1","user2"]]
condenser_api.get_account_history             # ["user", -1, 1000]
condenser_api.get_account_reputations          # ["user", 10]

# Content
condenser_api.get_content                     # ["author", "permlink"]
condenser_api.get_content_replies             # ["author", "permlink"]
condenser_api.get_discussions_by_blog         # [{"tag":"user","limit":10}]
condenser_api.get_discussions_by_trending     # [{"tag":"hive","limit":10}]

# Blockchain state
condenser_api.get_dynamic_global_properties   # []
condenser_api.get_block                       # [block_num]
condenser_api.get_block_header                # [block_num]
condenser_api.get_active_witnesses            # []
condenser_api.get_reward_fund                 # ["post"]
condenser_api.get_current_median_history_price # []
condenser_api.get_feed_history                # []

# Witnesses
condenser_api.get_witnesses_by_vote           # ["", 100]
condenser_api.get_witness_by_account          # ["witnessname"]

# Market
condenser_api.get_order_book                  # [limit]
condenser_api.get_ticker                      # []

# RC
condenser_api.find_rc_accounts                # [["user1","user2"]]

# Broadcast
condenser_api.broadcast_transaction_synchronous  # [signed_tx]
```

### Key database_api Methods

```bash
database_api.get_dynamic_global_properties    # {}
database_api.find_accounts                    # {"accounts":["user"]}
database_api.find_comments                    # {"comments":[["author","permlink"]]}
database_api.find_votes                       # {"author":"user","permlink":"post"}
database_api.get_reward_funds                 # {}
database_api.list_witnesses                   # {"start":"","limit":100,"order":"by_vote_name"}
database_api.find_rc_accounts                 # {"accounts":["user"]}
```

### Key rc_api Methods

```bash
rc_api.find_rc_accounts          # {"accounts":["user"]}
rc_api.get_resource_params       # {}  (cacheable, only changes with hived updates)
rc_api.get_resource_pool         # {}
rc_api.get_rc_stats              # {}
```

---

## Public API Nodes

### Current Public Nodes (2025-2026)

| Node | Operator | Full/Light |
|------|----------|------------|
| `https://api.hive.blog` | Hive community | Full |
| `https://api.openhive.network` | OpenHive | Full |
| `https://anyx.io` | @anyx | Full |
| `https://api.deathwing.me` | @deathwing | Full |
| `https://hive-api.arcange.eu` | @arcange | Full |
| `https://rpc.ecency.com` | Ecency | Full |
| `https://api.hive.blue` | Community | Full |
| `https://techcoderx.com` | @techcoderx | Full |

### Node Selection Best Practices

```python
# Always specify multiple nodes for failover
from beem import Hive
hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.openhive.network",
    "https://anyx.io",
    "https://api.deathwing.me"
])
```

```javascript
// dhive failover configuration
const client = new Client([
    "https://api.hive.blog",
    "https://api.openhive.network",
    "https://anyx.io",
    "https://api.deathwing.me"
], {
    timeout: 10000,           // 10s timeout
    failoverThreshold: 3,     // switch after 3 failures
    rebindInterval: 60000     // retry failed node after 60s
});
```

### Full vs Light Nodes
- **Full nodes**: Store complete blockchain history, support all APIs
- **Light (consensus) nodes**: Store only recent blocks, limited API support
- **Account history nodes**: Full nodes with `account_history_api` enabled (resource-intensive)
- Most public nodes are full nodes; verify with `jsonrpc.get_methods`

### Checking Node Capabilities

```bash
# List all available API methods on a node
curl -s -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"jsonrpc.get_methods","params":{},"id":1}' \
  https://api.hive.blog
```

---

## Hivemind (Social Layer)

### Overview
- Microservice that provides social features API on top of Hive
- Processes blockchain data and maintains its own PostgreSQL database
- Handles: post feeds, follows, communities, notifications, trending
- Reduces load on `hived` by offloading social queries
- Processes only **irreversible blocks**

### What Hivemind Provides
- **Follows/mutes**: Social graph data
- **Communities**: Community membership, roles, moderation
- **Post feeds**: Blog, feed, trending, hot, created, promoted
- **Reputation**: Account reputation scores
- **Notifications**: Mentions, replies, follows, votes

### Hivemind vs hived API

| Query Type | Use Hivemind | Use hived |
|------------|-------------|-----------|
| Get trending posts | Yes | No |
| Get user's blog | Yes | No |
| Get followers/following | Yes | No |
| Community data | Yes | No |
| Transfer history | No | Yes |
| Account balances | No | Yes |
| Block data | No | Yes |
| Dynamic properties | No | Yes |
| RC data | No | Yes |
| Witness data | No | Yes |

### Hivemind API Calls (via bridge_api)

```bash
# Get post by author/permlink
curl -s -d '{"jsonrpc":"2.0","method":"bridge.get_post","params":{"author":"user","permlink":"post","observer":""},"id":1}' \
  https://api.hive.blog

# Get account posts (blog)
curl -s -d '{"jsonrpc":"2.0","method":"bridge.get_account_posts","params":{"sort":"blog","account":"user","limit":10},"id":1}' \
  https://api.hive.blog

# Get ranked posts (trending, hot, created)
curl -s -d '{"jsonrpc":"2.0","method":"bridge.get_ranked_posts","params":{"sort":"trending","tag":"hive","limit":10,"observer":""},"id":1}' \
  https://api.hive.blog

# Get community info
curl -s -d '{"jsonrpc":"2.0","method":"bridge.get_community","params":{"name":"hive-174578","observer":""},"id":1}' \
  https://api.hive.blog

# List communities
curl -s -d '{"jsonrpc":"2.0","method":"bridge.list_communities","params":{"limit":10,"sort":"rank"},"id":1}' \
  https://api.hive.blog

# Get followers
curl -s -d '{"jsonrpc":"2.0","method":"bridge.get_followers","params":{"account":"user","start":"","limit":50,"type":"blog"},"id":1}' \
  https://api.hive.blog

# Get notifications
curl -s -d '{"jsonrpc":"2.0","method":"bridge.account_notifications","params":{"account":"user","limit":20},"id":1}' \
  https://api.hive.blog
```

### Python Examples with Hivemind

```python
from beem import Hive

hive = Hive()

# Get trending posts
trending = hive.rpc.get_ranked_posts(
    {"sort": "trending", "tag": "", "limit": 10, "observer": ""},
    api="bridge"
)

# Get a specific post with full metadata
post = hive.rpc.get_post(
    {"author": "username", "permlink": "my-post", "observer": ""},
    api="bridge"
)

# Get community details
community = hive.rpc.get_community(
    {"name": "hive-174578", "observer": ""},
    api="bridge"
)
```

---

## Architecture Summary

```
                    [Users / dApps]
                         |
              [Hive Keychain / SDKs]
                    (beem, dhive)
                         |
                   [API Layer]
          +---------+---------+---------+
          |         |         |         |
     [hived]   [Hivemind]  [HAF]   [Hive-Engine]
     (core)    (social)   (SQL)    (L2 sidechain)
          |         |         |         |
     [Block     [PostgreSQL] [PostgreSQL] [MongoDB]
      Log]
          |
     [P2P Network]
     (21 witnesses)
```
