# Hive Layer 2 Skill File (Hive-Engine, HAF, Splinterlands, VSC)

## Hive-Engine

### Overview
- Sidechain platform running smart contracts on top of Hive
- Contracts are JavaScript code executed in a sandboxed VM
- All operations are broadcast as `custom_json` with id `ssc-mainnet-hive`
- BEE is the native token (required to create new tokens, ~100 BEE per token)
- Maintains its own state database, queryable via JSON-RPC API

### API Endpoints

**Main RPC endpoint:** `https://api.hive-engine.com/rpc/contracts`
**Alternative nodes:**
- `https://herpc.dtools.dev/contracts`
- `https://engine.rishipanthee.com/contracts`
- `https://herpc.kanibot.com/contracts`

**Account history API:** `https://history.hive-engine.com/`

### Querying Data (JSON-RPC)

#### findOne - Get a single record

```bash
curl -s -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "findOne",
    "params": {
      "contract": "tokens",
      "table": "balances",
      "query": {"account": "username", "symbol": "BEE"}
    },
    "id": 1
  }' https://api.hive-engine.com/rpc/contracts
```

#### find - Get multiple records

```bash
curl -s -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "find",
    "params": {
      "contract": "tokens",
      "table": "balances",
      "query": {"account": "username"},
      "limit": 1000,
      "offset": 0,
      "indexes": []
    },
    "id": 1
  }' https://api.hive-engine.com/rpc/contracts
```

#### Common Contracts and Tables

| Contract | Table | Description |
|----------|-------|-------------|
| `tokens` | `balances` | Token balances per account |
| `tokens` | `tokens` | Token metadata (supply, precision, etc.) |
| `tokens` | `pendingUnstakes` | Pending unstake operations |
| `tokens` | `delegations` | Active delegations |
| `market` | `buyBook` | Open buy orders |
| `market` | `sellBook` | Open sell orders |
| `market` | `tradesHistory` | Recent trade history |
| `nft` | `nfts` | NFT collection definitions |
| `nft` | `[SYMBOL]instances` | NFT instances (e.g., `PACKinstances`) |
| `mining` | `miningPower` | Mining power per account |
| `mining` | `pools` | Mining pool configurations |

### Token Operations via custom_json

All token operations use:
```json
{
    "required_auths": ["username"],
    "required_posting_auths": [],
    "id": "ssc-mainnet-hive",
    "json": "{\"contractName\":\"tokens\",\"contractAction\":\"...\",\"contractPayload\":{...}}"
}
```

#### Python (beem) Examples

```python
from beem import Hive
import json

hive = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])

# Transfer tokens
hive.custom_json(
    id="ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "transfer",
        "contractPayload": {
            "symbol": "BEE",
            "to": "recipient",
            "quantity": "10",
            "memo": "payment"
        }
    },
    required_auths=["myaccount"]
)

# Stake tokens
hive.custom_json(
    id="ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "stake",
        "contractPayload": {
            "to": "myaccount",
            "symbol": "BEE",
            "quantity": "100"
        }
    },
    required_auths=["myaccount"]
)

# Place a market buy order
hive.custom_json(
    id="ssc-mainnet-hive",
    json_data={
        "contractName": "market",
        "contractAction": "buy",
        "contractPayload": {
            "symbol": "BEE",
            "quantity": "10",
            "price": "0.50"
        }
    },
    required_auths=["myaccount"]
)
```

#### JavaScript (dhive) Examples

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const client = new Client(["https://api.hive.blog"]);
const activeKey = PrivateKey.fromString("5Jxxxxxxxxx_ACTIVE_WIF");

// Transfer tokens
await client.broadcast.json({
    required_auths: ["myaccount"],
    required_posting_auths: [],
    id: "ssc-mainnet-hive",
    json: JSON.stringify({
        contractName: "tokens",
        contractAction: "transfer",
        contractPayload: {
            symbol: "BEE",
            to: "recipient",
            quantity: "10",
            memo: "payment"
        }
    })
}, activeKey);
```

### Querying Hive-Engine from Python

```python
import requests

HE_API = "https://api.hive-engine.com/rpc/contracts"

def he_find(contract, table, query, limit=1000, offset=0):
    payload = {
        "jsonrpc": "2.0",
        "method": "find",
        "params": {
            "contract": contract,
            "table": table,
            "query": query,
            "limit": limit,
            "offset": offset,
            "indexes": []
        },
        "id": 1
    }
    resp = requests.post(HE_API, json=payload)
    return resp.json().get("result", [])

def he_find_one(contract, table, query):
    payload = {
        "jsonrpc": "2.0",
        "method": "findOne",
        "params": {
            "contract": contract,
            "table": table,
            "query": query
        },
        "id": 1
    }
    resp = requests.post(HE_API, json=payload)
    return resp.json().get("result")

# Get all token balances for an account
balances = he_find("tokens", "balances", {"account": "username"})
for b in balances:
    print(f"{b['symbol']}: {b['balance']} (staked: {b.get('stake', '0')})")

# Get token info
token = he_find_one("tokens", "tokens", {"symbol": "BEE"})
print(f"BEE supply: {token['supply']}, max: {token['maxSupply']}")

# Get market orders
buy_orders = he_find("market", "buyBook", {"symbol": "BEE"}, limit=10)
sell_orders = he_find("market", "sellBook", {"symbol": "BEE"}, limit=10)

# Get trade history
trades = he_find("market", "tradesHistory", {"symbol": "BEE"}, limit=20)
```

### Depositing/Withdrawing HIVE to Hive-Engine

```python
# Deposit HIVE to Hive-Engine (regular transfer to @hive-engine)
from beem import Hive
from beem.account import Account

hive = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])
acc = Account("myaccount", blockchain_instance=hive)
acc.transfer("hive-engine", 10.0, "HIVE", memo="myaccount")  # memo = your HE account

# Withdraw HIVE from Hive-Engine (custom_json)
hive.custom_json(
    id="ssc-mainnet-hive",
    json_data={
        "contractName": "hivepegged",
        "contractAction": "withdraw",
        "contractPayload": {
            "quantity": "10"
        }
    },
    required_auths=["myaccount"]
)
```

---

## HAF (Hive Application Framework)

### Overview
- Framework for building scalable apps on Hive using **PostgreSQL**
- A `hived` node with `sql_serializer` plugin pushes blocks into a Postgres database
- Apps are written in SQL (stored procedures) + any language with SQL bindings
- Built-in micro-fork handling via `hive_fork_manager`
- Apps only process **irreversible blocks** by default

### Architecture

```
[Hive P2P Network]
        |
    [hived node]
        |  (sql_serializer plugin)
        v
  [PostgreSQL Database]
   (HAF database with blockchain data)
        |
   [hive_fork_manager]
        |
  [HAF Application]
   (SQL stored procedures + Python/C++/any language)
        |
   [REST API / Web Frontend]
```

### Key Concepts

1. **sql_serializer**: hived plugin that writes every block, transaction, and operation to PostgreSQL tables
2. **hive_fork_manager**: Handles blockchain micro-forks by rewinding app state when forked-out blocks are detected
3. **Irreversible blocks**: HAF apps typically process only irreversible blocks (confirmed by 2/3+ witnesses)
4. **Contexts**: Each HAF app registers a "context" that tracks which block it has processed up to

### Database Schema (Key Tables)

```sql
-- Core blockchain data (read-only, maintained by hived)
hive.blocks               -- Block headers
hive.transactions         -- All transactions
hive.operations           -- All operations (decoded)
hive.accounts             -- Account data

-- Application-specific tables (created by your app)
-- Your app creates its own tables in its own schema
CREATE SCHEMA myapp;
CREATE TABLE myapp.state (...);
```

### Building a HAF App (Conceptual)

```sql
-- Register your app context
SELECT hive.app_create_context('myapp', 'myapp');

-- Process new blocks
CREATE OR REPLACE FUNCTION myapp.process_block(block_num INT)
RETURNS VOID AS $$
DECLARE
    op RECORD;
BEGIN
    -- Iterate through operations in this block
    FOR op IN
        SELECT * FROM hive.operations
        WHERE block_num = $1
        AND op_type_id = 18  -- custom_json operation type
    LOOP
        -- Parse and process the operation
        -- Insert into your app-specific tables
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Main processing loop
CREATE OR REPLACE FUNCTION myapp.main()
RETURNS VOID AS $$
DECLARE
    last_block INT;
    current_block INT;
BEGIN
    SELECT hive.app_get_current_block_num('myapp') INTO last_block;
    SELECT hive.app_get_irreversible_block('myapp') INTO current_block;

    FOR b IN last_block..current_block LOOP
        PERFORM myapp.process_block(b);
        PERFORM hive.app_set_current_block_num('myapp', b);
    END LOOP;
END;
$$ LANGUAGE plpgsql;
```

### HAF Advantages
- **SQL-native**: Build blockchain apps with standard SQL knowledge
- **Fork-resilient**: Automatic rewind on micro-forks
- **Scalable**: PostgreSQL handles indexing, querying, and scaling
- **No custom sync**: hived pushes data automatically
- **Replayable**: Can rebuild app state from genesis

### Existing HAF Apps
- **Hivemind**: Social features API (follows, feeds, communities)
- **HAfAH**: Account history API
- **Balance Tracker**: Token balance tracking

---

## Splinterlands Custom JSON Patterns

### Overview
- Largest dApp on Hive by transaction volume
- All game actions are custom_json operations
- Some operations go on-chain, others are signed but sent to game servers
- Uses posting key for gameplay, active key for financial ops

### Common Operations

```python
from beem import Hive
import json

hive = Hive(keys=["5Jxxxxxxxxx_POSTING_WIF"])

# Find a match
hive.custom_json(
    id="sm_find_match",
    json_data={
        "match_type": "Ranked",
        "app": "splinterlands/0.7.139",
        "n": "unique_nonce_string"
    },
    required_posting_auths=["player"]
)

# Submit team (hashed, before reveal)
hive.custom_json(
    id="sm_submit_team",
    json_data={
        "trx_id": "abc123...",  # transaction ID from sm_find_match
        "team_hash": "md5_hash_of_team_plus_secret",
        "app": "splinterlands/0.7.139"
    },
    required_posting_auths=["player"]
)

# Reveal team (after both players submit)
hive.custom_json(
    id="sm_team_reveal",
    json_data={
        "trx_id": "abc123...",
        "team_hash": "md5_hash",
        "summoner": "C1-123-ABCDEF",
        "monsters": ["C2-456-GHIJKL", "C3-789-MNOPQR"],
        "secret": "random_secret_used_in_hash",
        "app": "splinterlands/0.7.139"
    },
    required_posting_auths=["player"]
)
```

### Financial Operations (Active Key)

```python
hive_active = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])

# Token transfer (SPS, DEC, etc.)
hive_active.custom_json(
    id="sm_token_transfer",
    json_data={
        "token": "SPS",
        "qty": 100,
        "to": "recipient",
        "app": "splinterlands/0.7.139"
    },
    required_auths=["player"]
)

# Sell cards on market
hive_active.custom_json(
    id="sm_sell_cards",
    json_data={
        "cards": ["C1-123-ABCDEF"],
        "currency": "DEC",
        "price": 5000,
        "fee_pct": 600,  # 6% marketplace fee
        "app": "splinterlands/0.7.139"
    },
    required_auths=["player"]
)

# Buy from market
hive_active.custom_json(
    id="sm_market_purchase",
    json_data={
        "items": ["market_listing_id"],
        "price": 5000,
        "currency": "DEC",
        "app": "splinterlands/0.7.139"
    },
    required_auths=["player"]
)

# Stake SPS
hive_active.custom_json(
    id="sm_stake_tokens",
    json_data={
        "token": "SPS",
        "qty": 1000,
        "app": "splinterlands/0.7.139"
    },
    required_auths=["player"]
)
```

### Splinterlands Custom JSON ID Reference

| ID | Key | Description |
|---|---|---|
| `sm_find_match` | Posting | Queue for battle |
| `sm_submit_team` | Posting | Submit hashed team |
| `sm_team_reveal` | Posting | Reveal team cards |
| `sm_token_transfer` | Active | Transfer game tokens |
| `sm_sell_cards` | Active | List cards for sale |
| `sm_market_purchase` | Active | Buy cards from market |
| `sm_delegate_cards` | Posting | Delegate cards |
| `sm_undelegate_cards` | Posting | Remove delegation |
| `sm_stake_tokens` | Active | Stake SPS |
| `sm_unstake_tokens` | Active | Unstake SPS |
| `sm_claim_reward` | Posting | Claim rewards |
| `sm_open_pack` | Posting | Open card pack |
| `sm_combine_cards` | Posting | Level up cards |
| `sm_gift_cards` | Active | Gift cards to another player |
| `sm_enter_tournament` | Active | Enter a tournament |
| `sm_leave_tournament` | Posting | Leave a tournament |

---

## VSC (Virtual Smart Chain)

### Overview
- Layer 2 smart contract platform built on Hive
- Enables smart contract execution (not just token operations like Hive-Engine)
- Zero-fee smart contract experience
- Cross-chain interoperability (Bitcoin, Ethereum, Solana)
- Uses WASM-based smart contracts
- Validators stake HIVE as economic collateral
- Currently in active development (2025-2026)

### Architecture
- Custom_json operations on Hive L1 serve as the data availability layer
- VSC nodes process these operations and execute smart contracts
- Cross-chain assets deposited into on-chain vaults secured by validators
- No native token required for consensus (unique "no token" model)

### Key Features
- **Smart contracts**: Full programmable contracts (not just token transfers)
- **Cross-chain**: Assets from BTC, ETH, SOL can interact with VSC contracts
- **Composability**: Contracts can call other contracts
- **Hive-native**: Inherits Hive's fast block times and feeless transactions

### Resources
- Documentation: https://docs.vsc.eco/
- GitHub: https://github.com/vsc-eco
- Uses Hive custom_json for data anchoring

### Current Status (2026)
- Active development with Golang and TypeScript node implementations
- Testnet operational
- Mainnet launch pending
- Smart contract SDK in development
