# Hive Engine Token Operations API (JavaScript)

A complete REST API for interacting with Hive Engine, the Layer 2 sidechain for custom tokens on the Hive blockchain.

## What is Hive Engine?

**Hive Engine** is a Layer 2 (L2) sidechain built on top of the Hive blockchain (Layer 1). It enables:

- **Custom Fungible Tokens**: Create your own tokens with configurable supply, precision, and staking
- **Non-Fungible Tokens (NFTs)**: Unique digital assets with custom properties
- **Decentralized Exchange (DEX)**: A limit-order book DEX where all tokens trade against SWAP.HIVE
- **Staking & Governance**: Lock tokens for voting power and reward eligibility
- **Smart Contracts**: Custom contracts that extend the sidechain's functionality

### The Layer 1 / Layer 2 Bridge

This is the key architectural concept to understand:

```
User Action (e.g., "Transfer 10 BEE to alice")
       |
       v
+------------------+
| This App         |  Constructs a JSON payload describing the operation
| (server.js)      |  and signs it with the user's active key
+------------------+
       |
       v  custom_json operation with id="ssc-mainnet-hive"
+------------------+
| Hive Layer 1     |  Includes the custom_json in the next block (~3 seconds)
| (hived nodes)    |  This is the immutable, trustless transport layer
+------------------+
       |
       v  Hive Engine nodes watch L1 for custom_json with id="ssc-mainnet-hive"
+------------------+
| Hive Engine L2   |  Parses the JSON, validates the operation, and executes it
| (sidechain)      |  Updates token balances, market orders, staking state, etc.
+------------------+
```

**Layer 1** is the **transport** (immutable, trustless, censorship-resistant).
**Layer 2** is the **execution engine** (fast, feature-rich, indexed).

### Token Types

| Type | Contract | Examples | Description |
|------|----------|----------|-------------|
| Fungible | `tokens` | BEE, DEC, SPS, LEO | Standard tokens with divisible supply |
| NFT | `nft` | Splinterlands cards | Unique assets with custom properties |
| Wrapped | `tokens` | SWAP.HIVE, SWAP.HBD | 1:1 wrapped versions of L1 assets |

### How custom_json Bridges L1 and L2

Every Hive Engine operation is a `custom_json` transaction on Hive Layer 1:

```json
{
  "type": "custom_json",
  "required_auths": ["youraccount"],
  "required_posting_auths": [],
  "id": "ssc-mainnet-hive",
  "json": "{\"contractName\":\"tokens\",\"contractAction\":\"transfer\",\"contractPayload\":{\"symbol\":\"BEE\",\"to\":\"alice\",\"quantity\":\"10.000\",\"memo\":\"payment\"}}"
}
```

- `id`: Must be `"ssc-mainnet-hive"` for Hive Engine to process it
- `required_auths`: Active key authorization (financial operations)
- `json`: Stringified contract call with `contractName`, `contractAction`, and `contractPayload`

## Setup

### Prerequisites

- Node.js 18+ and npm
- A Hive account (create free at [signup.hive.io](https://signup.hive.io))
- Your active private key (find at `https://hive.blog/@youraccount/permissions`)

### Installation

```bash
# Clone or navigate to this directory
cd hive_templates/token_app/js

# Install dependencies
npm install

# Copy environment template and fill in your values
cp .env.example .env

# Edit .env with your account and active key
# IMPORTANT: Never share your active key or commit .env to git!

# Start the server
npm start
```

The server runs on `http://localhost:3002` by default.

## API Reference

### Read Operations (No key required)

These endpoints query the Hive Engine sidechain API directly. No private keys needed.

#### GET /api/tokens
List all registered Hive Engine tokens.

```bash
# Get first 100 tokens
curl http://localhost:3002/api/tokens

# Paginate: get tokens 100-200
curl "http://localhost:3002/api/tokens?limit=100&offset=100"
```

#### GET /api/token/:symbol
Get detailed information about a specific token.

```bash
curl http://localhost:3002/api/token/BEE
```

Response includes: symbol, name, issuer, supply, maxSupply, precision, stakingEnabled, unstakingCooldown, totalStaked, delegationEnabled.

#### GET /api/balance/:account
Get all Hive Engine token balances for an account.

```bash
curl http://localhost:3002/api/balance/splinterlands
```

Note: This returns **Layer 2** balances only. HIVE/HBD (Layer 1) are not included.

#### GET /api/balance/:account/:symbol
Get a specific token balance for an account.

```bash
curl http://localhost:3002/api/balance/splinterlands/DEC
```

#### GET /api/market/:symbol
Get the DEX order book for a token (bids and asks).

```bash
curl "http://localhost:3002/api/market/BEE?limit=20"
```

Returns buy orders (highest bid first) and sell orders (lowest ask first), plus spread calculation.

#### GET /api/history/:account/:symbol
Get transaction history for an account and token.

```bash
curl "http://localhost:3002/api/history/splinterlands/DEC?limit=50"
```

### Write Operations (Active key required)

These endpoints broadcast `custom_json` operations to Hive Layer 1. They require `HIVE_ACCOUNT` and `HIVE_ACTIVE_KEY` in your `.env` file.

#### POST /api/transfer
Transfer tokens to another account.

```bash
curl -X POST http://localhost:3002/api/transfer \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BEE",
    "to": "recipient",
    "quantity": "10.000",
    "memo": "payment for services"
  }'
```

#### POST /api/stake
Stake tokens for governance power and rewards.

```bash
curl -X POST http://localhost:3002/api/stake \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BEE",
    "to": "youraccount",
    "quantity": "100.000"
  }'
```

#### POST /api/unstake
Begin unstaking (tokens enter cooldown period before becoming liquid).

```bash
curl -X POST http://localhost:3002/api/unstake \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BEE",
    "quantity": "50.000"
  }'
```

#### POST /api/market/buy
Place a limit buy order on the DEX.

```bash
curl -X POST http://localhost:3002/api/market/buy \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BEE",
    "quantity": "100.000",
    "price": "0.01000000"
  }'
```

Note: Requires SWAP.HIVE balance. Deposit HIVE at https://tribaldex.com/wallet/

#### POST /api/market/sell
Place a limit sell order on the DEX.

```bash
curl -X POST http://localhost:3002/api/market/sell \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BEE",
    "quantity": "100.000",
    "price": "0.01200000"
  }'
```

## Key Concepts

### HIVE vs Hive Engine Tokens

| Feature | HIVE/HBD (Layer 1) | Hive Engine Tokens (Layer 2) |
|---------|--------------------|-----------------------------|
| Consensus | hived (DPoS) | Sidechain nodes |
| Transfer method | `transfer` operation | `custom_json` operation |
| Creation | Built into protocol | Anyone can create via smart contract |
| Trading | Internal market (HIVE/HBD only) | DEX with all L2 token pairs |
| Staking | Power up → VESTS | Token-specific staking |

### Staking Mechanics

1. **Stake**: Instantly locks tokens from liquid to staked balance
2. **Staked tokens**: Cannot be transferred/sold; provide governance power + reward eligibility
3. **Unstake**: Initiates cooldown period (varies by token, e.g., 3-28 days)
4. **Pending unstake**: Tokens locked during cooldown, no governance power
5. **Liquid**: After cooldown, tokens return to transferable balance

### DEX Order Book

- All tokens trade against **SWAP.HIVE** (wrapped HIVE on Layer 2)
- **Limit orders only** (no AMM/liquidity pools in the core DEX)
- Orders persist until filled or cancelled (no expiration)
- Matching engine fills orders when bid >= ask

### Why Active Key?

Hive uses a hierarchical key system for security:

| Key | Purpose | Risk Level |
|-----|---------|------------|
| Owner | Account recovery | Highest (rarely used) |
| Active | Financial operations | High (transfers, market orders) |
| Posting | Social operations | Low (posts, votes, comments) |
| Memo | Encrypted messages | Low |

Token operations are **financial**, so they require `required_auths` (active key), not `required_posting_auths` (posting key).

## Dependencies

- **@hiveio/dhive**: Official Hive blockchain library for signing and broadcasting transactions to Layer 1
- **sscjs**: Hive Engine sidechain client for querying Layer 2 state
- **express**: HTTP server framework
- **axios**: HTTP client for Hive Engine JSON-RPC requests
- **dotenv**: Environment variable management

## Testing

```bash
npm test
```

Runs validation tests and helper function checks without requiring blockchain connectivity.

## Security Notes

- **Never commit `.env`** — it contains your active private key
- **Active key = wallet access** — treat it like a bank password
- **Test with small amounts first** — use BEE (cheap) before working with valuable tokens
- **Rate limiting** — add rate limiting middleware before production deployment
- **HTTPS** — use a reverse proxy (nginx) with TLS for production

## Resources

- [Hive Engine Documentation](https://hive-engine.com)
- [Hive Developer Portal](https://developers.hive.io)
- [dhive Documentation](https://github.com/openhive-network/dhive)
- [TribalDex](https://tribaldex.com) — Hive Engine DEX web interface
- [Hive Engine Explorer](https://he.dtools.dev) — Block explorer for the sidechain
