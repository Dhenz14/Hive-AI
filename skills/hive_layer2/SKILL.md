# Hive Layer 2 — Hive-Engine, HAF, VSC

## Hive-Engine (Sidechain Token Platform)

### What It Is
A sidechain that processes custom_json operations (id: `ssc-mainnet-hive`) to run smart contracts, create tokens, NFTs, and DeFi pools on top of Hive.

### API Endpoints
| Endpoint | URL | Purpose |
|----------|-----|---------|
| Main RPC | `https://api.hive-engine.com/rpc` | Contract queries |
| History | `https://history.hive-engine.com` | Transaction history |
| Prices | `https://api.hive-engine.com/rpc/contracts` | Market data |

### Query Tokens
```python
import requests

# Get token balance
resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "tokens",
        "table": "balances",
        "query": {"account": "username", "symbol": "BEE"},
        "limit": 1
    }
})
balance = resp.json()["result"][0]  # {"account", "symbol", "balance", "stake", ...}

# Get token info
resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
    "jsonrpc": "2.0", "id": 1, "method": "findOne",
    "params": {
        "contract": "tokens",
        "table": "tokens",
        "query": {"symbol": "BEE"}
    }
})
token = resp.json()["result"]  # {symbol, name, precision, maxSupply, supply, ...}

# Get market orders
resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "market",
        "table": "buyBook",
        "query": {"symbol": "BEE"},
        "limit": 10, "offset": 0,
        "indexes": [{"index": "priceDec", "descending": True}]
    }
})
```

### Broadcast Operations (via Hive custom_json)
```python
from beem import Hive
h = Hive(keys=["5K..active_wif"])

# Transfer token
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "tokens",
    "contractAction": "transfer",
    "contractPayload": {
        "symbol": "BEE", "to": "recipient",
        "quantity": "10.000", "memo": "payment"
    }
}, required_auths=["sender"])

# Create a new token
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "tokens",
    "contractAction": "create",
    "contractPayload": {
        "symbol": "MYTOKEN",
        "name": "My Token",
        "precision": 3,
        "maxSupply": "1000000.000",
        "url": "https://myapp.com",
        "isSignedWithActiveKey": True
    }
}, required_auths=["creator"])
# Cost: 100 BEE to create a token

# Stake token
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "tokens",
    "contractAction": "stake",
    "contractPayload": {"symbol": "BEE", "to": "username", "quantity": "50.000"}
}, required_auths=["username"])

# Place market buy order (price in SWAP.HIVE per token)
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "market",
    "contractAction": "buy",
    "contractPayload": {
        "symbol": "BEE", "quantity": "100.000",
        "price": "0.500"  # 0.5 SWAP.HIVE per BEE
    }
}, required_auths=["buyer"])
```

### Key Concepts
- **SWAP.HIVE**: Hive-Engine's wrapped HIVE (deposit HIVE → get SWAP.HIVE for trading)
- **Precision**: Token decimal places (set at creation, immutable)
- **Staking**: Lock tokens for governance/rewards (configurable unstake period)
- **Delegation**: Delegate staked tokens to other accounts
- **NFTs**: `nft` contract for creating and managing non-fungible tokens

## HAF (Hive Application Framework)

### What It Is
SQL-based framework for building Hive apps. A HAF node replays the blockchain into PostgreSQL tables, letting you query chain data with standard SQL.

### Architecture
```
Hive Node → HAF (hived with SQL plugin) → PostgreSQL
                                              ↓
                                    Your App (SQL queries)
```

### Key Tables
```sql
-- All operations ever broadcast
SELECT * FROM hive.operations
WHERE op_type_id = 72  -- custom_json
AND block_num > 80000000
LIMIT 100;

-- Account data
SELECT * FROM hive.accounts WHERE name = 'username';

-- Blocks
SELECT * FROM hive.blocks WHERE num = 80000000;

-- Transactions in a block
SELECT * FROM hive.transactions WHERE block_num = 80000000;
```

### Building a HAF App
```sql
-- Register your app context
SELECT hive.app_create_context('myapp', 'myapp_schema');

-- Create your app tables in your schema
CREATE TABLE myapp_schema.user_actions (
    id SERIAL PRIMARY KEY,
    block_num INTEGER NOT NULL,
    actor VARCHAR(16) NOT NULL,
    action JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Process blocks in your app's event loop
-- HAF handles block tracking, reversible blocks, and forks for you
```

### Why HAF over Direct API
- **Speed**: SQL queries on indexed data vs JSON-RPC calls
- **Reliability**: No rate limits, no network dependency after sync
- **Flexibility**: Complex joins, aggregations, full-text search
- **Fork handling**: HAF automatically manages reversible blocks

## VSC (Virtual Smart Chain)

### What It Is
Smart contract platform on Hive — run WASM smart contracts anchored to the Hive blockchain.

### Key Concepts
- **Contracts**: Written in AssemblyScript/Rust → compiled to WASM
- **State**: Anchored to Hive via custom_json references
- **Consensus**: Nodes validate contract execution deterministically
- **Interop**: Can read Hive state, trigger Hive operations

### Status
VSC is newer/evolving — check [vsc.eco](https://vsc.eco) for current documentation. Core concepts:
- Deploy contracts as WASM to the network
- Contract calls via Hive custom_json
- Deterministic execution across all nodes
- Gas-like system for computation limits

## Common Mistakes
- **SWAP.HIVE vs HIVE**: You can't trade raw HIVE on Hive-Engine — must deposit to get SWAP.HIVE first
- **Token precision**: Must match exactly what was set at creation. "10.00" fails if precision is 3
- **isSignedWithActiveKey**: Required for token creation and other privileged ops — easy to forget
- **HAF sync time**: Initial sync takes days. Plan for it
- **Rate limiting**: Hive-Engine API has rate limits — cache aggressively, batch queries
