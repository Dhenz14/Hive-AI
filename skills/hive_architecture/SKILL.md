# Hive Architecture — Protocol, Consensus & APIs

## Consensus: Delegated Proof of Stake (DPoS)

### How It Works
- **21 witnesses** produce blocks in round-robin schedule
- **Top 20** elected by HP-weighted stake voting + **1 backup** rotated in
- **3-second block time** — each witness gets a 3-second slot per round (~63 seconds per full round)
- **Irreversibility**: ~45 seconds (15 blocks × 2/3 supermajority confirmation)

### Witness Voting
```python
# Vote for a witness (max 30 votes per account)
h.approve_witness("witness_name", account="voter")

# Set a voting proxy (delegate all witness votes to another account)
h.set_proxy("proxy_account", account="voter")
```

## Block Structure
```json
{
  "block_id": "004c4b40...",
  "previous": "004c4b3f...",
  "timestamp": "2024-01-15T10:30:00",
  "witness": "blocktrades",
  "transaction_merkle_root": "abcd1234...",
  "transactions": [
    {
      "ref_block_num": 19264,
      "ref_block_prefix": 1234567890,
      "expiration": "2024-01-15T10:31:00",
      "operations": [
        ["vote", {"voter": "alice", "author": "bob", "permlink": "post", "weight": 10000}],
        ["custom_json", {"id": "follow", "json": "...", ...}]
      ],
      "signatures": ["1f3a5b..."]
    }
  ]
}
```

### Transaction Rules
- **Expiration**: Max 1 hour in the future (typically 30-60 seconds)
- **ref_block_num/prefix**: References a recent block (prevents replay on forks)
- **Duplicate detection**: Same transaction hash rejected within expiration window
- **Max transaction size**: 65,536 bytes

## API Layer

### API Categories
| API | Purpose | Examples |
|-----|---------|---------|
| `condenser_api` | Legacy Steem-compatible API | `get_content`, `get_accounts`, `get_block` |
| `database_api` | Low-level chain queries | `find_accounts`, `list_witnesses` |
| `block_api` | Block data | `get_block`, `get_block_range` |
| `rc_api` | Resource credits | `find_rc_accounts`, `get_resource_params` |
| `account_history_api` | Account operation history | `get_account_history` |
| `network_broadcast_api` | Transaction broadcasting | `broadcast_transaction` |

### Making RPC Calls
```python
import requests

# JSON-RPC 2.0 format
resp = requests.post("https://api.hive.blog", json={
    "jsonrpc": "2.0", "id": 1,
    "method": "condenser_api.get_accounts",
    "params": [["username"]]
})
account = resp.json()["result"][0]
```

```javascript
// Using dhive (handles RPC internally)
const acc = await client.database.getAccounts(["username"]);

// Raw RPC
const resp = await fetch("https://api.hive.blog", {
  method: "POST",
  body: JSON.stringify({
    jsonrpc: "2.0", id: 1,
    method: "condenser_api.get_content",
    params: ["author", "permlink"]
  })
});
```

### Useful Queries
```python
# Get dynamic global properties (chain state)
props = h.get_dynamic_global_properties()
# head_block_number, current_supply, total_vesting_fund_hive, etc.

# Get current price feed (HIVE/USD median)
feed = h.get_current_median_history()
# {"base": "0.400 HBD", "quote": "1.000 HIVE"} → HIVE = $0.40

# Get reward fund
fund = h.get_reward_funds()
# reward_balance, recent_claims, content_constant

# Get witness schedule
schedule = h.get_witness_schedule()
# current_shuffled_witnesses, median_props
```

## Hivemind (Social Consensus Layer)

### What It Is
A separate process that indexes social data (posts, communities, follows, reblogs) from the blockchain into PostgreSQL. Provides the social API layer.

### What Hivemind Handles
- Post/comment threading and rendering
- Community membership and moderation
- Follow/mute relationships
- Trending/hot post ranking algorithms
- Post metadata and tags

### APIs Served by Hivemind
```python
# These go through Hivemind, not hived directly
h.rpc.get_discussions_by_trending({"tag": "hive", "limit": 10})
h.rpc.get_discussions_by_created({"tag": "dev", "limit": 10})
h.rpc.get_content("author", "permlink")  # enriched with community data
```

## Node Types
| Type | Disk | RAM | Use Case |
|------|------|-----|----------|
| **Consensus (witness)** | ~50 GB | 16 GB | Block production only |
| **API node (full)** | ~500 GB+ | 64 GB+ | All APIs, full history |
| **API node (minimal)** | ~100 GB | 32 GB | Basic APIs, limited history |
| **Hivemind** | ~200 GB | 32 GB | Social APIs (runs alongside hived) |
| **HAF** | ~1 TB+ | 64 GB+ | SQL-based app framework |

### Running Your Own Node
```bash
# Docker (recommended)
docker pull hiveio/hive
docker run -d --name hived \
  -v hive_data:/hive/datadir \
  -p 8091:8091 \
  hiveio/hive

# Config (config.ini)
plugin = condenser_api database_api block_api
plugin = account_history_api account_history_rocksdb
webserver-http-endpoint = 0.0.0.0:8091
```

## Key Architecture Decisions

### Why No Smart Contracts on L1
- Hive L1 is optimized for **social operations** and **speed** (3s blocks)
- Smart contracts add execution complexity and attack surface
- L2 solutions (Hive-Engine, VSC) handle programmable logic
- This keeps L1 fast, simple, and secure

### Why Feeless (RC System)
- Fees create friction for social apps (imagine paying $0.01 per upvote)
- RC system: stake once, transact forever (proportional to stake)
- Prevents spam via rate-limiting, not economic barriers
- New users get RC delegation to bootstrap

### Fork History
- **Steem → Hive** (March 2020): Community fork after Steemit Inc acquisition by Justin Sun
- All Steem accounts/balances mirrored to Hive at fork block
- Hive Decentralized Fund (DHF) replaced Steem's SPS
- Community governance model vs corporate control
