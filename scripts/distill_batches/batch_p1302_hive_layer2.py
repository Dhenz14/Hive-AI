"""Hive Layer 2 training pairs (part 1): Hive Engine, sidechain tokens, smart contracts on Hive."""

PAIRS = [
    # --- 1. Hive Engine API basics ---
    (
        "hive_layer2/he-api-basics",
        r'''How do I query the Hive Engine API? I want to look up token info and account balances using Python.''',
        r'''<think>
Hive Engine exposes a JSON-RPC API at https://api.hive-engine.com/rpc/contracts.
Two main methods: "find" for multiple records, "findOne" for a single record.
Key params: contract, table, query, limit, offset, indexes.
Common contracts: "tokens" (balances, tokens tables), "market" (buyBook, sellBook).
I should build a reusable helper and show practical examples.
</think>

Hive Engine uses a JSON-RPC API. Here is a reusable Python client covering the core query patterns:

```python
import requests
from typing import Any

HE_API = "https://api.hive-engine.com/rpc/contracts"

# Alternative nodes for failover:
# "https://herpc.dtools.dev/contracts"
# "https://engine.rishipanthee.com/contracts"


def he_find(contract: str, table: str, query: dict,
            limit: int = 1000, offset: int = 0,
            indexes: list | None = None) -> list[dict]:
    """Query multiple records from a Hive Engine contract table."""
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {
            "contract": contract,
            "table": table,
            "query": query,
            "limit": limit,
            "offset": offset,
            "indexes": indexes or [],
        },
    }
    resp = requests.post(HE_API, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", [])


def he_find_one(contract: str, table: str, query: dict) -> dict | None:
    """Query a single record from a Hive Engine contract table."""
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "findOne",
        "params": {"contract": contract, "table": table, "query": query},
    }
    resp = requests.post(HE_API, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result")


# --- Token info ---
token = he_find_one("tokens", "tokens", {"symbol": "BEE"})
if token:
    print(f"BEE  supply: {token['supply']}  max: {token['maxSupply']}  "
          f"precision: {token['precision']}")

# --- Account balances ---
balances = he_find("tokens", "balances", {"account": "aggroed"})
for b in balances:
    sym = b["symbol"]
    bal = b["balance"]
    staked = b.get("stake", "0")
    print(f"  {sym}: {bal}  (staked: {staked})")
```

Key points:
- All queries go to the `/rpc/contracts` endpoint via POST.
- `find` returns a list (up to `limit`); `findOne` returns one dict or `None`.
- Common contract/table combos: `tokens/tokens` (metadata), `tokens/balances` (holdings), `market/buyBook`, `market/sellBook`, `market/tradesHistory`.
- Always set a `timeout` — the public API can be slow under load.'''
    ),

    # --- 2. Token creation ---
    (
        "hive_layer2/token-creation",
        r'''How do I create a new token on Hive Engine? Walk me through the full process including costs and configuration options.''',
        r'''<think>
Creating a token on Hive Engine costs 100 BEE (the platform's native token).
The operation is broadcast as a custom_json on Hive L1 with id "ssc-mainnet-hive".
Key payload fields: symbol, name, precision, maxSupply, url, isSignedWithActiveKey.
Precision is immutable after creation. Must use active key authority.
After creation, you issue (mint) tokens separately with the "issue" action.
</think>

Creating a Hive Engine token requires **100 BEE** and is done by broadcasting a `custom_json` operation on Hive with the sidechain id `ssc-mainnet-hive`.

```python
from beem import Hive

hive = Hive(keys=["5K...your_active_wif"])

# Step 1: Create the token (costs 100 BEE, burned automatically)
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "create",
        "contractPayload": {
            "symbol": "MYTOKEN",           # 3-10 uppercase letters
            "name": "My Project Token",    # human-readable name
            "precision": 3,                # decimal places (IMMUTABLE)
            "maxSupply": "1000000.000",    # must match precision
            "url": "https://myproject.io",
            "isSignedWithActiveKey": True,  # required for create
        },
    },
    required_auths=["myaccount"],
)

# Step 2: Issue (mint) tokens to yourself or others
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "issue",
        "contractPayload": {
            "symbol": "MYTOKEN",
            "to": "myaccount",
            "quantity": "500000.000",  # must match precision
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=["myaccount"],
)

# Optional: Enable staking on the token
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "enableStaking",
        "contractPayload": {
            "symbol": "MYTOKEN",
            "unstakingCooldown": 7,       # days to unstake
            "numberTransactions": 7,       # unstake paid over N txs
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=["myaccount"],
)
```

Important details:
- **Precision is immutable** — choose carefully (3 is typical, 8 for micro-transactions).
- **Symbol rules**: 3-10 uppercase ASCII letters, must be unique on the sidechain.
- You must hold 100 BEE in your account before creating; the fee is deducted automatically.
- `maxSupply` string must have exactly as many decimal places as `precision`.
- After creation, tokens exist but have zero circulating supply until you `issue` them.'''
    ),

    # --- 3. Token transfer ---
    (
        "hive_layer2/token-transfer",
        r'''Show me how to transfer Hive Engine tokens between accounts in both Python and JavaScript.''',
        r'''<think>
Token transfers on Hive Engine use the tokens contract with the "transfer" action.
Broadcast as custom_json with id "ssc-mainnet-hive".
Need active key authority (required_auths, not posting).
Quantity string must match the token's precision.
I'll show both beem (Python) and dhive (JS) examples.
</think>

Hive Engine token transfers are `custom_json` operations broadcast on Hive L1. The sidechain picks them up and processes the balance change.

**Python (beem):**

```python
from beem import Hive

hive = Hive(keys=["5K...active_wif"])

hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "transfer",
        "contractPayload": {
            "symbol": "BEE",
            "to": "recipient",
            "quantity": "10.000",   # must match token precision (BEE = 3)
            "memo": "payment for services",
        },
    },
    required_auths=["sender"],
)
print("Transfer broadcast. Check Hive Engine explorer to confirm.")
```

**JavaScript (dhive):**

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");

const client = new Client(["https://api.hive.blog"]);
const activeKey = PrivateKey.fromString("5K...active_wif");

async function transferToken(from, to, symbol, quantity, memo) {
  const result = await client.broadcast.json(
    {
      required_auths: [from],
      required_posting_auths: [],
      id: "ssc-mainnet-hive",
      json: JSON.stringify({
        contractName: "tokens",
        contractAction: "transfer",
        contractPayload: { symbol, to, quantity, memo },
      }),
    },
    activeKey
  );
  console.log("Tx ID:", result.id);
  return result;
}

transferToken("sender", "recipient", "BEE", "10.000", "payment");
```

Common pitfalls:
- **Precision mismatch**: `"10.00"` will fail if the token has precision 3. Always check the token's precision first.
- **Active key required**: Transfers use `required_auths`, not `required_posting_auths`.
- **SWAP.HIVE vs HIVE**: You cannot transfer raw HIVE on Hive Engine. Deposit HIVE to `@hive-engine` first to get SWAP.HIVE.'''
    ),

    # --- 4. Market buy/sell orders ---
    (
        "hive_layer2/market-buy-sell",
        r'''How do I place buy and sell orders on the Hive Engine DEX? Show me both sides with Python.''',
        r'''<think>
Hive Engine has a built-in DEX. The market contract handles buy/sell.
All prices are in SWAP.HIVE per token.
Buy order: you spend SWAP.HIVE to acquire tokens.
Sell order: you offer tokens and receive SWAP.HIVE.
Cancel is also available via the market contract.
Need active key for all market operations.
</think>

The Hive Engine DEX uses the `market` contract. All prices are denominated in **SWAP.HIVE** per token.

```python
from beem import Hive

hive = Hive(keys=["5K...active_wif"])
ACCOUNT = "myaccount"

# --- Place a BUY order ---
# "I want to buy 100 BEE at 0.50 SWAP.HIVE each"
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "market",
        "contractAction": "buy",
        "contractPayload": {
            "symbol": "BEE",
            "quantity": "100.000",    # how many tokens to buy
            "price": "0.50000000",   # SWAP.HIVE per token (8 decimals)
        },
    },
    required_auths=[ACCOUNT],
)

# --- Place a SELL order ---
# "I want to sell 50 BEE at 0.60 SWAP.HIVE each"
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "market",
        "contractAction": "sell",
        "contractPayload": {
            "symbol": "BEE",
            "quantity": "50.000",
            "price": "0.60000000",
        },
    },
    required_auths=[ACCOUNT],
)

# --- Cancel an open order ---
# You need the order ID from the buyBook or sellBook table
import requests

HE_API = "https://api.hive-engine.com/rpc/contracts"

# Find your open orders
resp = requests.post(HE_API, json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "market",
        "table": "buyBook",
        "query": {"account": ACCOUNT, "symbol": "BEE"},
        "limit": 50,
    },
})
my_orders = resp.json().get("result", [])

if my_orders:
    order_id = my_orders[0]["_id"]
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": "market",
            "contractAction": "cancel",
            "contractPayload": {
                "type": "buy",     # "buy" or "sell"
                "id": str(order_id),
            },
        },
        required_auths=[ACCOUNT],
    )
    print(f"Cancelled order {order_id}")
```

Key details:
- **Price precision**: Market prices use 8 decimal places regardless of token precision.
- Orders that match existing orders fill immediately (like a limit order that crosses the spread).
- You must hold enough SWAP.HIVE for buys or enough tokens for sells — no margin.
- Cancel requires the internal `_id` from the order book query, not a transaction ID.'''
    ),

    # --- 5. Querying token balances ---
    (
        "hive_layer2/query-balances",
        r'''Write a Python script that fetches all Hive Engine token balances for a given account and displays them in a formatted table, including staked and delegated amounts.''',
        r'''<think>
Query the tokens/balances table with the account filter.
Each balance record has: account, symbol, balance, stake, pendingUnstake, delegatedStake, receivedStake.
I'll format it nicely with tabulate or manual formatting.
Should handle pagination since an account could hold many tokens.
</think>

```python
import requests
from typing import Iterator

HE_API = "https://api.hive-engine.com/rpc/contracts"


def get_all_balances(account: str) -> Iterator[dict]:
    """Fetch all HE token balances, handling pagination."""
    offset = 0
    limit = 1000
    while True:
        resp = requests.post(HE_API, json={
            "jsonrpc": "2.0", "id": 1, "method": "find",
            "params": {
                "contract": "tokens",
                "table": "balances",
                "query": {"account": account},
                "limit": limit,
                "offset": offset,
            },
        }, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get("result", [])
        if not rows:
            break
        yield from rows
        if len(rows) < limit:
            break
        offset += limit


def display_balances(account: str) -> None:
    balances = list(get_all_balances(account))
    if not balances:
        print(f"No Hive Engine tokens found for @{account}")
        return

    # Filter to non-zero holdings
    active = [b for b in balances if any(
        float(b.get(f, "0")) > 0
        for f in ("balance", "stake", "pendingUnstake",
                   "delegatedStake", "receivedStake")
    )]
    active.sort(key=lambda b: float(b.get("balance", "0")), reverse=True)

    header = f"{'Symbol':<12} {'Liquid':>14} {'Staked':>14} {'Delegated':>14} {'Received':>14}"
    print(f"\nHive Engine balances for @{account}  ({len(active)} tokens)\n")
    print(header)
    print("-" * len(header))

    for b in active:
        sym = b["symbol"]
        liquid = float(b.get("balance", "0"))
        staked = float(b.get("stake", "0"))
        deleg = float(b.get("delegatedStake", "0"))
        recv = float(b.get("receivedStake", "0"))
        print(f"{sym:<12} {liquid:>14.3f} {staked:>14.3f} {deleg:>14.3f} {recv:>14.3f}")

    print()


if __name__ == "__main__":
    import sys
    account = sys.argv[1] if len(sys.argv) > 1 else "aggroed"
    display_balances(account)
```

The `pendingUnstake` field (omitted from the display for brevity) tracks tokens currently in the unstaking cooldown period. Add it as another column if needed.'''
    ),

    # --- 6. Staking tokens ---
    (
        "hive_layer2/staking-tokens",
        r'''How do I stake and delegate Hive Engine tokens? Explain the mechanics and show Python code.''',
        r'''<think>
Staking locks liquid tokens. Not all tokens support staking — the issuer must enable it.
Staking uses tokens/stake action. Delegation uses tokens/delegate.
Staked tokens can be delegated to another account (they get the "receivedStake").
Both require active key. The "to" field on stake can be self or another account.
</think>

Staking on Hive Engine locks liquid tokens, typically granting governance power or reward weight. The token issuer must have enabled staking first (`enableStaking` action).

```python
from beem import Hive

hive = Hive(keys=["5K...active_wif"])
ACCOUNT = "myaccount"

# --- Stake tokens to yourself ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "stake",
        "contractPayload": {
            "to": ACCOUNT,          # can stake to yourself or another user
            "symbol": "BEE",
            "quantity": "100.000",
        },
    },
    required_auths=[ACCOUNT],
)

# --- Delegate staked tokens to another account ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "delegate",
        "contractPayload": {
            "to": "another_user",
            "symbol": "BEE",
            "quantity": "50.000",
        },
    },
    required_auths=[ACCOUNT],
)

# --- Undelegate (returns after cooldown) ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "undelegate",
        "contractPayload": {
            "from": "another_user",  # who you delegated TO
            "symbol": "BEE",
            "quantity": "50.000",
        },
    },
    required_auths=[ACCOUNT],
)
```

**How staking works mechanically:**
- Staked tokens move from `balance` to `stake` in the balances table.
- Delegated tokens move from your `stake` to `delegatedStake`, and appear as `receivedStake` on the target account.
- Unstaking cooldown is set by the token creator (e.g., 7 days for BEE), paid out in N equal installments.
- During unstaking, tokens are in `pendingUnstake` and cannot be used.
- Not all tokens support staking — check the token's `stakingEnabled` property.'''
    ),

    # --- 7. Unstaking tokens ---
    (
        "hive_layer2/unstaking-tokens",
        r'''How does unstaking work on Hive Engine? I want to unstake some tokens and need to understand the cooldown mechanics. Show me how to initiate an unstake and check pending unstakes.''',
        r'''<think>
Unstaking uses the tokens/unstake action. Once initiated, tokens enter a cooldown.
The cooldown duration and number of transactions are set by the token creator.
For example, BEE has 7-day cooldown with 7 transactions (one per day).
Pending unstakes can be queried from the tokens/pendingUnstakes table.
You can cancel a pending unstake with cancelUnstake.
</think>

Unstaking on Hive Engine is not instant. Tokens enter a cooldown period and are released in installments.

```python
from beem import Hive
import requests

hive = Hive(keys=["5K...active_wif"])
ACCOUNT = "myaccount"
HE_API = "https://api.hive-engine.com/rpc/contracts"

# --- Initiate unstake ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "unstake",
        "contractPayload": {
            "symbol": "BEE",
            "quantity": "50.000",
        },
    },
    required_auths=[ACCOUNT],
)

# --- Check pending unstakes ---
resp = requests.post(HE_API, json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "tokens",
        "table": "pendingUnstakes",
        "query": {"account": ACCOUNT},
        "limit": 100,
    },
}, timeout=10)

pending = resp.json().get("result", [])
for p in pending:
    print(f"Symbol: {p['symbol']}  "
          f"Quantity: {p['quantity']}  "
          f"Remaining: {p['quantityLeft']}  "
          f"Next release: {p['nextTransactionTimestamp']}  "
          f"Txs left: {p['numberTransactionsLeft']}")

# --- Cancel a pending unstake ---
if pending:
    unstake_id = pending[0]["_id"]
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": "tokens",
            "contractAction": "cancelUnstake",
            "contractPayload": {
                "txID": str(unstake_id),
            },
        },
        required_auths=[ACCOUNT],
    )
    print(f"Cancelled unstake {unstake_id} — tokens returned to stake")
```

**Cooldown mechanics:**
- The token creator sets `unstakingCooldown` (days) and `numberTransactions` (installments).
- Example: 28-day cooldown with 4 transactions = one release every 7 days.
- During cooldown, tokens sit in `pendingUnstake` — not liquid, not staked.
- Cancelling returns all remaining tokens back to staked balance immediately.'''
    ),

    # --- 8. Diesel pool swaps ---
    (
        "hive_layer2/diesel-pool-swap",
        r'''How do I perform a token swap on a Hive Engine diesel pool (liquidity pool)? Show me how to query pool info and execute a swap.''',
        r'''<think>
Diesel pools are Hive Engine's AMM liquidity pools (similar to Uniswap).
The contract is "marketpools". Swaps use the "swapTokens" action.
Need to query the pool first to calculate expected output.
Pools are identified by tokenPair (e.g., "BEE:SWAP.HIVE").
Slippage protection via minAmountOut.
</think>

Diesel pools are Hive Engine's automated market maker (AMM), similar to Uniswap. They use the `marketpools` contract.

```python
import requests
from decimal import Decimal
from beem import Hive

HE_API = "https://api.hive-engine.com/rpc/contracts"

# --- Query available pools ---
def get_pool(token_pair: str) -> dict | None:
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0", "id": 1, "method": "findOne",
        "params": {
            "contract": "marketpools",
            "table": "pools",
            "query": {"tokenPair": token_pair},
        },
    }, timeout=10)
    return resp.json().get("result")


# Check a pool's reserves
pool = get_pool("BEE:SWAP.HIVE")
if pool:
    base_qty = Decimal(pool["baseQuantity"])     # BEE side
    quote_qty = Decimal(pool["quoteQuantity"])    # SWAP.HIVE side
    print(f"Pool: {pool['tokenPair']}")
    print(f"  BEE reserve:        {base_qty}")
    print(f"  SWAP.HIVE reserve:  {quote_qty}")
    print(f"  Price (SWAP.HIVE/BEE): {quote_qty / base_qty:.8f}")

# --- Calculate expected output (constant product) ---
def estimate_swap(pool: dict, token_in: str, amount_in: Decimal,
                  fee_pct: Decimal = Decimal("0.0025")) -> Decimal:
    """Estimate output using x*y=k with trading fee."""
    base = Decimal(pool["baseQuantity"])
    quote = Decimal(pool["quoteQuantity"])

    amount_after_fee = amount_in * (1 - fee_pct)

    if token_in == pool["tokenPair"].split(":")[0]:  # base -> quote
        new_base = base + amount_after_fee
        new_quote = (base * quote) / new_base
        return quote - new_quote
    else:  # quote -> base
        new_quote = quote + amount_after_fee
        new_base = (base * quote) / new_quote
        return base - new_base


# --- Execute a swap ---
hive = Hive(keys=["5K...active_wif"])

amount_in = "10.000"
min_out = "0.00000001"  # set realistic slippage protection!

hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "marketpools",
        "contractAction": "swapTokens",
        "contractPayload": {
            "tokenPair": "BEE:SWAP.HIVE",
            "tokenSymbol": "BEE",            # token you are SENDING
            "tokenAmount": amount_in,
            "tradeType": "exactInput",
            "minAmountOut": min_out,          # slippage protection
        },
    },
    required_auths=["myaccount"],
)
```

Always calculate `minAmountOut` from the pool reserves before swapping to avoid being frontrun or getting a bad rate. A typical slippage tolerance is 1-3%.'''
    ),

    # --- 9. Liquidity pool creation ---
    (
        "hive_layer2/liquidity-pool-creation",
        r'''How do I create a new diesel pool (liquidity pool) on Hive Engine and add liquidity to it?''',
        r'''<think>
Creating a diesel pool uses the marketpools contract with "createPool" action.
Costs BEE to create. Must specify the token pair.
Adding liquidity uses "addLiquidity" — you supply both sides of the pair.
The pool mints LP tokens representing your share.
Need to own both tokens in sufficient quantities.
</think>

Creating a liquidity pool on Hive Engine uses the `marketpools` contract. There is a BEE fee for pool creation.

```python
from beem import Hive

hive = Hive(keys=["5K...active_wif"])
ACCOUNT = "myaccount"

# --- Step 1: Create the pool (one-time, costs 1000 BEE) ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "marketpools",
        "contractAction": "createPool",
        "contractPayload": {
            "tokenPair": "MYTOKEN:SWAP.HIVE",  # base:quote
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- Step 2: Add initial liquidity ---
# You must hold both MYTOKEN and SWAP.HIVE.
# The ratio you supply sets the initial price.
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "marketpools",
        "contractAction": "addLiquidity",
        "contractPayload": {
            "tokenPair": "MYTOKEN:SWAP.HIVE",
            "baseQuantity": "10000.000",    # MYTOKEN amount
            "quoteQuantity": "100.00000000",  # SWAP.HIVE amount
            # Initial price = 100/10000 = 0.01 SWAP.HIVE per MYTOKEN
            "maxPriceImpact": "5",          # max % price change tolerance
            "maxDeviation": "10",           # max % deviation from current price
        },
    },
    required_auths=[ACCOUNT],
)

# --- Remove liquidity ---
# First query your LP token balance, then remove
import requests

HE_API = "https://api.hive-engine.com/rpc/contracts"
resp = requests.post(HE_API, json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "marketpools",
        "table": "liquidityPositions",
        "query": {"account": ACCOUNT, "tokenPair": "MYTOKEN:SWAP.HIVE"},
        "limit": 1,
    },
}, timeout=10)

positions = resp.json().get("result", [])
if positions:
    shares = positions[0]["shares"]
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": "marketpools",
            "contractAction": "removeLiquidity",
            "contractPayload": {
                "tokenPair": "MYTOKEN:SWAP.HIVE",
                "sharesOut": shares,  # remove all, or a portion
            },
        },
        required_auths=[ACCOUNT],
    )
```

Key points:
- Pool creation costs **1000 BEE** (check current fee on Hive Engine docs).
- The first liquidity addition sets the initial price ratio.
- Subsequent LPs must add at the current ratio or within `maxDeviation`.
- You receive LP shares proportional to your contribution — these are NOT tradeable tokens.'''
    ),

    # --- 10. NFT creation on Hive Engine ---
    (
        "hive_layer2/nft-creation",
        r'''How do I create an NFT collection on Hive Engine and mint individual NFTs? Show the full workflow.''',
        r'''<think>
Hive Engine NFTs use the "nft" contract.
Step 1: Create an NFT definition (collection) — costs 100 BEE.
Step 2: Add data properties to define the schema.
Step 3: Issue (mint) individual NFT instances.
Each instance can have unique properties.
NFTs are stored in a table named [SYMBOL]instances.
</think>

Hive Engine NFTs use the `nft` contract. Creating a collection, defining properties, and minting are separate operations.

```python
from beem import Hive

hive = Hive(keys=["5K...active_wif"])
ACCOUNT = "myaccount"

# --- Step 1: Create the NFT collection (costs 100 BEE) ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nft",
        "contractAction": "create",
        "contractPayload": {
            "symbol": "MYART",
            "name": "My Art Collection",
            "maxSupply": 1000,          # 0 = unlimited
            "url": "https://myart.io",
            "authorizedIssuingAccounts": [ACCOUNT],
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- Step 2: Define data properties (schema) ---
# Each property costs 100 BEE
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nft",
        "contractAction": "addProperty",
        "contractPayload": {
            "symbol": "MYART",
            "name": "rarity",
            "type": "string",          # string, number, or boolean
            "isReadOnly": True,        # immutable after mint
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nft",
        "contractAction": "addProperty",
        "contractPayload": {
            "symbol": "MYART",
            "name": "image_url",
            "type": "string",
            "isReadOnly": True,
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- Step 3: Mint NFT instances ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nft",
        "contractAction": "issue",
        "contractPayload": {
            "symbol": "MYART",
            "to": "collector_account",
            "feeSymbol": "BEE",        # fee token for minting
            "properties": {
                "rarity": "legendary",
                "image_url": "https://myart.io/pieces/001.png",
            },
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- Query minted NFTs ---
import requests

resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "nft",
        "table": "MYARTinstances",    # table = {SYMBOL}instances
        "query": {"account": "collector_account"},
        "limit": 100,
    },
}, timeout=10)
nfts = resp.json().get("result", [])
for nft in nfts:
    print(f"ID: {nft['_id']}  Rarity: {nft['properties']['rarity']}")
```

Costs summary:
- Create collection: **100 BEE**
- Add property: **100 BEE** each
- Minting: small BEE fee per instance (varies)'''
    ),

    # --- 11. NFT transfers ---
    (
        "hive_layer2/nft-transfer",
        r'''How do I transfer NFTs on Hive Engine between accounts? Show single and batch transfers.''',
        r'''<think>
NFT transfers use the nft contract with "transfer" action.
Can transfer one or multiple NFTs in a single operation.
Need the NFT instance IDs (from the instances table).
Must use active key. Can only transfer NFTs you own.
Batch transfer uses "transferMultiple" or just an array of IDs.
</think>

```python
from beem import Hive

hive = Hive(keys=["5K...active_wif"])
ACCOUNT = "myaccount"

# --- Single NFT transfer ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nft",
        "contractAction": "transfer",
        "contractPayload": {
            "to": "recipient",
            "nfts": [
                {"symbol": "MYART", "ids": ["1"]},
            ],
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- Batch transfer (multiple NFTs, possibly different collections) ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nft",
        "contractAction": "transfer",
        "contractPayload": {
            "to": "recipient",
            "nfts": [
                {"symbol": "MYART", "ids": ["2", "3", "5"]},
                {"symbol": "CARDS", "ids": ["101", "102"]},
            ],
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- Burn NFTs (send to null) ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nft",
        "contractAction": "burn",
        "contractPayload": {
            "nfts": [
                {"symbol": "MYART", "ids": ["4"]},
            ],
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)
```

Notes:
- The `nfts` array lets you transfer across multiple collections in one tx.
- IDs are strings (the `_id` field from the instances table).
- Burning permanently destroys the NFT and decrements the collection's supply.
- You can only transfer NFTs where `account` matches your username.'''
    ),

    # --- 12. NFT market listing ---
    (
        "hive_layer2/nft-market-listing",
        r'''How do I list an NFT for sale on the Hive Engine NFT market, and how do I buy one?''',
        r'''<think>
The nftmarket contract handles NFT sales on Hive Engine.
Selling: use "sell" action with the NFT symbol, id, price, and price symbol.
Buying: use "buy" action with the order ID.
Can also cancel listings. The market must be enabled for the NFT collection.
Price is typically in SWAP.HIVE or BEE.
</think>

The Hive Engine NFT marketplace uses the `nftmarket` contract for listing, buying, and cancelling NFT sales.

```python
from beem import Hive
import requests

hive = Hive(keys=["5K...active_wif"])
ACCOUNT = "myaccount"
HE_API = "https://api.hive-engine.com/rpc/contracts"

# --- Enable the market for your collection (one-time, by issuer) ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nftmarket",
        "contractAction": "enableMarket",
        "contractPayload": {
            "symbol": "MYART",
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- List an NFT for sale ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nftmarket",
        "contractAction": "sell",
        "contractPayload": {
            "symbol": "MYART",
            "nfts": ["1"],               # NFT instance IDs
            "price": "50.00000000",      # price per NFT
            "priceSymbol": "SWAP.HIVE",  # payment token
            "fee": 500,                  # marketplace fee in basis points (5%)
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- Query listed NFTs ---
resp = requests.post(HE_API, json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "nftmarket",
        "table": "MYARTsellBook",  # table = {SYMBOL}sellBook
        "query": {},
        "limit": 20,
    },
}, timeout=10)
listings = resp.json().get("result", [])
for item in listings:
    print(f"NFT #{item['nftId']}  Price: {item['price']} {item['priceSymbol']}  "
          f"Seller: {item['account']}")

# --- Buy an NFT from the market ---
if listings:
    order_id = listings[0]["_id"]
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": "nftmarket",
            "contractAction": "buy",
            "contractPayload": {
                "symbol": "MYART",
                "marketAccount": listings[0]["account"],
                "order": str(order_id),
                "isSignedWithActiveKey": True,
            },
        },
        required_auths=["buyer_account"],
    )

# --- Cancel a listing ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "nftmarket",
        "contractAction": "cancel",
        "contractPayload": {
            "symbol": "MYART",
            "nfts": ["1"],
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)
```

The sell book table is named `{SYMBOL}sellBook` — note the case-sensitive symbol prefix.'''
    ),

    # --- 13. Token airdrops ---
    (
        "hive_layer2/token-airdrop",
        r'''How do I airdrop a Hive Engine token to multiple accounts efficiently? I want to send tokens to a list of holders.''',
        r'''<think>
Hive Engine doesn't have a built-in airdrop action in the tokens contract.
Airdrops are done by broadcasting multiple transfer custom_json operations.
Best approach: batch transfers, one per tx, but pace them to avoid rate limits.
Can also snapshot holders from the balances table first.
Must account for Hive's 5-second block time and RC costs.
</think>

Hive Engine doesn't have a native airdrop action, so airdrops are executed as batched individual transfers. Here's a production-ready airdrop script:

```python
import time
import requests
from decimal import Decimal, ROUND_DOWN
from beem import Hive
from beem.account import Account

HE_API = "https://api.hive-engine.com/rpc/contracts"


def get_token_holders(symbol: str, min_balance: float = 0.0) -> list[dict]:
    """Fetch all holders of a token, with pagination."""
    holders = []
    offset = 0
    while True:
        resp = requests.post(HE_API, json={
            "jsonrpc": "2.0", "id": 1, "method": "find",
            "params": {
                "contract": "tokens", "table": "balances",
                "query": {"symbol": symbol},
                "limit": 1000, "offset": offset,
            },
        }, timeout=15)
        batch = resp.json().get("result", [])
        if not batch:
            break
        for b in batch:
            total = float(b.get("balance", "0")) + float(b.get("stake", "0"))
            if total >= min_balance:
                holders.append({"account": b["account"], "balance": total})
        offset += len(batch)
    return holders


def airdrop(sender: str, active_wif: str, symbol: str,
            recipients: list[dict], precision: int = 3,
            delay: float = 3.0, dry_run: bool = True):
    """
    Airdrop tokens to a list of recipients.

    recipients: [{"account": "user1", "amount": "10.000"}, ...]
    """
    hive = Hive(keys=[active_wif])
    total_sent = Decimal("0")

    for i, r in enumerate(recipients):
        account = r["account"]
        amount = r["amount"]
        total_sent += Decimal(amount)

        if dry_run:
            print(f"[DRY RUN] Would send {amount} {symbol} to @{account}")
            continue

        try:
            hive.custom_json(
                "ssc-mainnet-hive",
                json_data={
                    "contractName": "tokens",
                    "contractAction": "transfer",
                    "contractPayload": {
                        "symbol": symbol,
                        "to": account,
                        "quantity": amount,
                        "memo": f"Airdrop: Thank you for holding {symbol}!",
                    },
                },
                required_auths=[sender],
            )
            print(f"[{i+1}/{len(recipients)}] Sent {amount} {symbol} -> @{account}")
        except Exception as e:
            print(f"[ERROR] Failed for @{account}: {e}")

        time.sleep(delay)  # avoid hitting RC limits or API rate limits

    print(f"\nTotal distributed: {total_sent} {symbol}")


# --- Example: proportional airdrop to all holders of MYTOKEN ---
holders = get_token_holders("MYTOKEN", min_balance=1.0)
airdrop_pool = Decimal("50000.000")

total_held = sum(Decimal(str(h["balance"])) for h in holders)
recipients = []
for h in holders:
    share = (Decimal(str(h["balance"])) / total_held) * airdrop_pool
    amount = share.quantize(Decimal("0.001"), rounding=ROUND_DOWN)
    if amount > 0:
        recipients.append({"account": h["account"], "amount": str(amount)})

# Dry run first, then set dry_run=False
airdrop("myaccount", "5K...wif", "MYTOKEN", recipients, dry_run=True)
```

Tips:
- Always dry-run first to verify amounts and recipient count.
- Space transfers 3+ seconds apart to conserve Resource Credits.
- For large airdrops (1000+ recipients), consider running overnight.'''
    ),

    # --- 14. Mining pool setup ---
    (
        "hive_layer2/mining-pool-setup",
        r'''How do mining pools work on Hive Engine? Show me how to set up a mining token and configure a mining pool.''',
        r'''<think>
Hive Engine has a "mining" contract that lets token issuers create mining pools.
Users stake a "mining token" and earn rewards from a "reward token".
The pool distributes rewards on a schedule (e.g., every N Hive blocks).
Setup involves creating a mining pool with createPool, then users stake.
Mining power can be boosted by NFTs (optional).
</think>

Hive Engine's `mining` contract allows token issuers to create Proof-of-Stake-like mining pools where users stake a mining token to earn rewards.

```python
from beem import Hive
import requests

hive = Hive(keys=["5K...active_wif"])
ACCOUNT = "myaccount"
HE_API = "https://api.hive-engine.com/rpc/contracts"

# --- Create a mining pool ---
# Prerequisites: both mining token and reward token must exist
# and the mining token must have staking enabled.
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "mining",
        "contractAction": "createPool",
        "contractPayload": {
            "lotteryWinners": 1,           # winners per round
            "lotteryIntervalHours": 1,     # draw every N hours
            "lotteryAmount": "10.000",     # reward per round
            "minedToken": "MYREWARD",      # token distributed as reward
            "tokenMiners": [
                {
                    "symbol": "MYMINER",   # token users stake
                    "multiplier": 1,       # weight multiplier
                },
            ],
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- Users participate by staking the mining token ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "stake",
        "contractPayload": {
            "to": ACCOUNT,
            "symbol": "MYMINER",
            "quantity": "500.000",
        },
    },
    required_auths=[ACCOUNT],
)

# --- Query mining pool info ---
resp = requests.post(HE_API, json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "mining",
        "table": "pools",
        "query": {"minedToken": "MYREWARD"},
        "limit": 10,
    },
}, timeout=10)
pools = resp.json().get("result", [])
for pool in pools:
    print(f"Pool ID: {pool['_id']}")
    print(f"  Reward: {pool['lotteryAmount']} {pool['minedToken']} "
          f"every {pool['lotteryIntervalHours']}h")
    print(f"  Total power: {pool.get('totalPower', 'N/A')}")

# --- Query your mining power ---
resp = requests.post(HE_API, json={
    "jsonrpc": "2.0", "id": 1, "method": "findOne",
    "params": {
        "contract": "mining",
        "table": "miningPower",
        "query": {"account": ACCOUNT, "id": pools[0]["_id"]},
    },
}, timeout=10)
power = resp.json().get("result")
if power:
    print(f"Your mining power: {power['power']}")
```

How it works:
- Mining is lottery-based: each round, `lotteryWinners` accounts are selected, weighted by staked mining power.
- More staked tokens = higher probability of winning each round.
- The reward token must have enough supply issued to the pool creator to fund distributions.
- NFT-boosted mining is also possible (add `nftTokenMiner` to the pool config).'''
    ),

    # --- 15. Token burning ---
    (
        "hive_layer2/token-burning",
        r'''How do I burn Hive Engine tokens to permanently reduce the circulating supply?''',
        r'''<think>
Burning uses the tokens contract "transfer" to the null account,
or there's a dedicated "burn" action depending on the token setup.
The standard approach is to send to "null" — but Hive Engine uses a
different mechanism. The contractAction is actually "transfer" to "null"
which removes tokens from circulation. Some implementations also have
a burn action directly.
</think>

There are two ways to burn Hive Engine tokens, depending on whether you are the token issuer or a regular holder:

```python
from beem import Hive
import requests

hive = Hive(keys=["5K...active_wif"])
ACCOUNT = "myaccount"

# --- Method 1: Transfer to null (anyone can do this) ---
# Sending to "null" permanently removes tokens from circulation
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "transfer",
        "contractPayload": {
            "symbol": "MYTOKEN",
            "to": "null",
            "quantity": "1000.000",
            "memo": "burn: reducing supply",
        },
    },
    required_auths=[ACCOUNT],
)

# --- Method 2: Issuer-only burn action ---
# Token issuers can burn from their own balance, which also
# reduces the tracked 'supply' field on the token metadata.
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "burn",
        "contractPayload": {
            "symbol": "MYTOKEN",
            "quantity": "500.000",
            "isSignedWithActiveKey": True,
        },
    },
    required_auths=[ACCOUNT],
)

# --- Verify the burn by checking supply ---
HE_API = "https://api.hive-engine.com/rpc/contracts"
resp = requests.post(HE_API, json={
    "jsonrpc": "2.0", "id": 1, "method": "findOne",
    "params": {
        "contract": "tokens",
        "table": "tokens",
        "query": {"symbol": "MYTOKEN"},
    },
}, timeout=10)
token = resp.json().get("result")
if token:
    print(f"Current supply: {token['supply']}")
    print(f"Max supply: {token['maxSupply']}")
    print(f"Burned (approx): {float(token['maxSupply']) - float(token['supply']):.3f}")
```

Key distinction:
- **Transfer to "null"**: Tokens leave circulation but `supply` may not update in token metadata on all implementations.
- **Burn action**: Explicitly decrements the `supply` field. Only the token issuer can use this.
- Burns are irreversible — there is no way to recover burned tokens.'''
    ),

    # --- 16. Market history queries ---
    (
        "hive_layer2/market-history",
        r'''How do I query trade history and build OHLCV candle data for a Hive Engine token?''',
        r'''<think>
Trade history is in the market/tradesHistory table.
Each record has: type, buyer, seller, symbol, quantity, price, volume, timestamp.
To build OHLCV candles, I need to aggregate by time intervals.
Can also use the Hive Engine history API for some endpoints.
I'll show querying raw trades and building candles with pandas.
</think>

```python
import requests
from datetime import datetime, timedelta
import pandas as pd

HE_API = "https://api.hive-engine.com/rpc/contracts"


def get_trade_history(symbol: str, limit: int = 500) -> list[dict]:
    """Fetch recent trades for a token, newest first."""
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {
            "contract": "market",
            "table": "tradesHistory",
            "query": {"symbol": symbol},
            "limit": limit,
            "offset": 0,
            "indexes": [{"index": "timestamp", "descending": True}],
        },
    }, timeout=15)
    resp.raise_for_status()
    return resp.json().get("result", [])


def build_ohlcv(trades: list[dict], interval: str = "1h") -> pd.DataFrame:
    """Build OHLCV candles from raw trade data.

    interval: pandas frequency string ('1h', '4h', '1D', etc.)
    """
    if not trades:
        return pd.DataFrame()

    df = pd.DataFrame(trades)
    df["price"] = df["price"].astype(float)
    df["quantity"] = df["quantity"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    df = df.set_index("timestamp").sort_index()

    ohlcv = df["price"].resample(interval).ohlc()
    ohlcv["volume"] = df["volume"].resample(interval).sum()
    ohlcv = ohlcv.dropna()

    return ohlcv


# --- Fetch and display ---
trades = get_trade_history("BEE", limit=1000)
print(f"Fetched {len(trades)} trades")

if trades:
    # Show recent trades
    for t in trades[:5]:
        ts = datetime.fromtimestamp(t["timestamp"])
        print(f"  {ts}  {t['type']}  {t['quantity']} @ {t['price']}  "
              f"vol: {t['volume']} SWAP.HIVE")

    # Build hourly candles
    candles = build_ohlcv(trades, "1h")
    print(f"\nHourly candles (last 5):")
    print(candles.tail().to_string())

    # Build daily candles
    daily = build_ohlcv(trades, "1D")
    print(f"\nDaily candles:")
    print(daily.to_string())
```

The `tradesHistory` table fields:
- `type`: "buy" or "sell" (from taker's perspective)
- `buyer` / `seller`: account names
- `symbol`: token symbol
- `quantity`: amount of tokens traded
- `price`: SWAP.HIVE per token
- `volume`: total SWAP.HIVE value of the trade
- `timestamp`: Unix epoch seconds'''
    ),

    # --- 17. Token metadata/properties ---
    (
        "hive_layer2/token-metadata",
        r'''How do I query and update token metadata and properties on Hive Engine? I want to check precision, supply, staking settings, and update the URL.''',
        r'''<think>
Token metadata is in the tokens/tokens table.
Fields: symbol, name, precision, maxSupply, supply, circulatingSupply, url,
stakingEnabled, unstakingCooldown, numberTransactions, issuer, etc.
Only the issuer can update certain properties like url and metadata.
The updateUrl and updateMetadata actions allow changes.
</think>

```python
import requests
from beem import Hive

HE_API = "https://api.hive-engine.com/rpc/contracts"


def get_token_info(symbol: str) -> dict | None:
    """Fetch full token metadata."""
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0", "id": 1, "method": "findOne",
        "params": {
            "contract": "tokens",
            "table": "tokens",
            "query": {"symbol": symbol},
        },
    }, timeout=10)
    return resp.json().get("result")


# --- Query token metadata ---
token = get_token_info("BEE")
if token:
    print(f"Symbol:          {token['symbol']}")
    print(f"Name:            {token['name']}")
    print(f"Issuer:          {token['issuer']}")
    print(f"Precision:       {token['precision']}")
    print(f"Max supply:      {token['maxSupply']}")
    print(f"Current supply:  {token['supply']}")
    print(f"Circ. supply:    {token.get('circulatingSupply', 'N/A')}")
    print(f"URL:             {token.get('url', 'N/A')}")
    print(f"Staking enabled: {token.get('stakingEnabled', False)}")
    if token.get("stakingEnabled"):
        print(f"  Unstake cooldown: {token.get('unstakingCooldown')} days")
        print(f"  Unstake txs:      {token.get('numberTransactions')}")
    print(f"Delegation:      {token.get('delegationEnabled', False)}")

# --- Update token URL (issuer only) ---
hive = Hive(keys=["5K...active_wif"])

hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "updateUrl",
        "contractPayload": {
            "symbol": "MYTOKEN",
            "url": "https://newsite.io",
        },
    },
    required_auths=["issuer_account"],
)

# --- Update token metadata (issuer only) ---
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "updateMetadata",
        "contractPayload": {
            "symbol": "MYTOKEN",
            "metadata": {
                "url": "https://newsite.io",
                "icon": "https://newsite.io/icon.png",
                "desc": "A community governance token",
            },
        },
    },
    required_auths=["issuer_account"],
)
```

Key facts about token properties:
- **precision** is set at creation and can never be changed.
- **maxSupply** can be decreased but never increased after creation.
- Only the **issuer** account can update URL, metadata, and enable features.
- `circulatingSupply` = `supply` minus tokens held by `null` (burned).'''
    ),

    # --- 18. Sidechain block explorer ---
    (
        "hive_layer2/block-explorer-queries",
        r'''How do I programmatically explore Hive Engine sidechain blocks and transactions? I want to verify that my custom_json operations were processed correctly.''',
        r'''<think>
Hive Engine processes custom_json ops from Hive L1 blocks.
The sidechain has its own block structure with transaction results.
The history API at history.hive-engine.com provides transaction lookup.
Can also query the blockchain contract for block-level data.
Key: after broadcasting a custom_json, check the sidechain tx status.
</think>

After broadcasting a `custom_json` to Hive L1, the Hive Engine sidechain processes it asynchronously. Here is how to verify transaction status and explore sidechain data:

```python
import requests
import time

HE_API = "https://api.hive-engine.com/rpc/contracts"
HE_HISTORY = "https://history.hive-engine.com"


def get_transaction_info(trx_id: str) -> dict | None:
    """Look up a Hive Engine transaction by its L1 transaction ID."""
    resp = requests.get(
        f"{HE_HISTORY}/accountHistory",
        params={"trx_id": trx_id},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data[0] if data else None


def get_account_history(account: str, symbol: str = None,
                        limit: int = 50, offset: int = 0) -> list[dict]:
    """Fetch Hive Engine transaction history for an account."""
    params = {"account": account, "limit": limit, "offset": offset}
    if symbol:
        params["symbol"] = symbol
    resp = requests.get(
        f"{HE_HISTORY}/accountHistory",
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def wait_for_confirmation(trx_id: str, timeout: int = 30,
                          poll_interval: float = 3.0) -> dict | None:
    """Poll until a transaction appears in Hive Engine history."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = get_transaction_info(trx_id)
        if result:
            return result
        time.sleep(poll_interval)
    return None


# --- Usage after broadcasting a custom_json ---
from beem import Hive

hive = Hive(keys=["5K...active_wif"])
result = hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "transfer",
        "contractPayload": {
            "symbol": "BEE", "to": "recipient",
            "quantity": "5.000", "memo": "test",
        },
    },
    required_auths=["sender"],
)
trx_id = result["trx_id"]
print(f"Broadcast L1 tx: {trx_id}")

# Wait for sidechain to process it
confirmed = wait_for_confirmation(trx_id, timeout=30)
if confirmed:
    print(f"Confirmed! Block: {confirmed.get('blockNumber')}")
    print(f"  Operation: {confirmed.get('operation')}")
    print(f"  Logs: {confirmed.get('logs')}")
else:
    print("Transaction not confirmed within timeout — check manually")

# --- Browse recent account activity ---
history = get_account_history("aggroed", symbol="BEE", limit=10)
for tx in history:
    print(f"  Block {tx.get('blockNumber')}  {tx.get('operation')}  "
          f"qty: {tx.get('quantity', 'N/A')}  {tx.get('timestamp', '')}")
```

The `logs` field in the transaction result is critical — it contains error messages if the operation failed on the sidechain (e.g., insufficient balance, wrong precision).'''
    ),

    # --- 19. ScotBot/tribe tokens basics ---
    (
        "hive_layer2/scotbot-tribe-tokens",
        r'''What are ScotBot tribe tokens on Hive? How do they work and how do I query tribe-specific reward data?''',
        r'''<think>
ScotBot (Smart Contract on Tribe) is a Hive Engine service that creates
tokenized communities (tribes) on Hive. Each tribe has its own token
distributed via Proof of Brain — authors earn tribe tokens when their
posts are upvoted with staked tribe tokens.
Tribes have their own frontends (e.g., leofinance.io uses LEO token).
ScotBot configuration determines reward curves, curation splits, etc.
Query via the scotbot API or Hive Engine directly.
</think>

ScotBot (Smart Contract on Tribe) creates **tokenized communities** on Hive. Each tribe has its own token that is distributed through Proof of Brain — meaning upvotes from users with staked tribe tokens generate new tribe tokens for authors and curators.

```python
import requests

HE_API = "https://api.hive-engine.com/rpc/contracts"
SCOT_API = "https://scot-api.hive-engine.com"


def get_scot_info(token: str) -> dict | None:
    """Get ScotBot configuration for a tribe token."""
    resp = requests.get(f"{SCOT_API}/info", params={"token": token}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get(token)


def get_scot_post_rewards(author: str, token: str,
                          limit: int = 10) -> list[dict]:
    """Get tribe-specific rewards for an author's posts."""
    resp = requests.get(
        f"{SCOT_API}/@{author}",
        params={"token": token, "limit": limit},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# --- Query tribe configuration ---
leo_config = get_scot_info("LEO")
if leo_config:
    print(f"Token: LEO")
    print(f"  Author reward %:    {leo_config.get('author_reward_percentage', 'N/A')}")
    print(f"  Curation reward %:  {leo_config.get('curation_reward_percentage', 'N/A')}")
    print(f"  Reward pool:        {leo_config.get('reward_pool', 'N/A')}")
    print(f"  Pending claims:     {leo_config.get('pending_rshares', 'N/A')}")
    print(f"  Tags:               {leo_config.get('tags', [])}")

# --- Check stake-weighted vote value ---
def get_vote_value(account: str, token: str) -> dict:
    """Estimate an account's vote value for a tribe token."""
    resp = requests.get(
        f"{SCOT_API}/@{account}",
        params={"token": token, "hive": 1},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

# --- Query which tribes a post earned rewards in ---
def get_post_scot_data(author: str, permlink: str) -> dict:
    """Get all tribe reward data for a specific post."""
    resp = requests.get(
        f"{SCOT_API}/@{author}/{permlink}",
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()  # dict keyed by token symbol

post_data = get_post_scot_data("leofinance", "some-permlink")
for token, data in post_data.items():
    pending = data.get("pending_token", 0) / (10 ** data.get("precision", 3))
    print(f"  {token}: pending {pending:.3f}")
```

Key concepts:
- **Tags routing**: Posts with specific tags (e.g., `#leofinance`) earn the tribe's token.
- **Staking**: Users must stake the tribe token to have vote weight in that tribe.
- **Reward curve**: Each tribe configures its own curve (linear, convergent-linear, etc.).
- **Curation/author split**: Configurable per tribe (typically 50/50).
- Popular tribes: LEO (LeoFinance), POB (Proof of Brain), NEOXAG (Neoxian City), SPT (Splintertalk).'''
    ),

    # --- 20. Proof of Brain distribution ---
    (
        "hive_layer2/proof-of-brain-distribution",
        r'''Explain how Proof of Brain token distribution works on Hive Engine tribes and show me how to calculate pending rewards for a post.''',
        r'''<think>
Proof of Brain (PoB) on Hive Engine mirrors Hive L1's reward mechanism.
When someone with staked tribe tokens votes on a post, it assigns rshares.
After the payout window (usually 7 days), rewards are calculated from the
reward pool proportional to rshares. The pool inflates at a set rate.
Author/curation split is configurable. I need to show the math and API queries.
</think>

Proof of Brain on Hive Engine tribes works similarly to Hive L1 rewards but with per-tribe token pools. Each vote with staked tribe tokens allocates `rshares` (reward shares) to a post. After the payout window, the post's share of the reward pool determines the payout.

```python
import requests
from decimal import Decimal

SCOT_API = "https://scot-api.hive-engine.com"


def calculate_pending_payout(author: str, permlink: str,
                             token: str) -> dict:
    """Calculate estimated pending payout for a post in a given tribe."""
    # Get tribe reward pool info
    resp = requests.get(f"{SCOT_API}/info", params={"token": token}, timeout=10)
    tribe = resp.json().get(token, {})

    reward_pool = Decimal(str(tribe.get("reward_pool", 0)))
    pending_rshares = Decimal(str(tribe.get("pending_rshares", 1)))
    author_pct = Decimal(str(tribe.get("author_reward_percentage", 50))) / 100
    precision = tribe.get("precision", 3)

    # Get post-specific data
    resp = requests.get(
        f"{SCOT_API}/@{author}/{permlink}",
        timeout=10,
    )
    post_data = resp.json().get(token, {})

    post_rshares = Decimal(str(post_data.get("total_payout_value", 0)))
    vote_rshares = Decimal(str(post_data.get("vote_rshares", 0)))
    pending_token = Decimal(str(post_data.get("pending_token", 0)))

    # The sidechain pre-calculates pending_token, but the formula is:
    # post_payout = (post_rshares / total_pending_rshares) * reward_pool
    # author_payout = post_payout * author_percentage
    # curator_payout = post_payout * (1 - author_percentage)

    if pending_rshares > 0 and vote_rshares > 0:
        estimated_total = (vote_rshares / pending_rshares) * reward_pool
        estimated_author = estimated_total * author_pct
        estimated_curator = estimated_total * (1 - author_pct)
    else:
        estimated_total = Decimal(0)
        estimated_author = Decimal(0)
        estimated_curator = Decimal(0)

    return {
        "token": token,
        "post_rshares": vote_rshares,
        "reward_pool": reward_pool,
        "total_pending_rshares": pending_rshares,
        "estimated_total": round(estimated_total, precision),
        "estimated_author": round(estimated_author, precision),
        "estimated_curator": round(estimated_curator, precision),
        "pre_calculated": pending_token / (10 ** precision),
    }


# --- Usage ---
result = calculate_pending_payout("leofinance", "weekly-report", "LEO")
print(f"Token: {result['token']}")
print(f"Reward pool:     {result['reward_pool']}")
print(f"Post rshares:    {result['post_rshares']}")
print(f"Est. total:      {result['estimated_total']} {result['token']}")
print(f"Est. author:     {result['estimated_author']} {result['token']}")
print(f"Est. curator:    {result['estimated_curator']} {result['token']}")
print(f"Pre-calculated:  {result['pre_calculated']} {result['token']}")
```

Key mechanics:
- **Inflation**: Each tribe has a daily token emission rate that feeds the reward pool.
- **Rshares**: Vote weight calculated from staked tokens and voting power (0-100%).
- **Payout window**: Typically 7 days, configurable per tribe.
- **Convergent-linear curve**: Most tribes use this — small posts earn proportionally less, discouraging vote farming.
- **Beneficiary rewards**: A percentage can go to the tribe's dev fund automatically.'''
    ),

    # --- 21. Community token economics ---
    (
        "hive_layer2/community-token-economics",
        r'''I want to design the token economics for a Hive Engine community token. What are the best practices and common configurations? Show me a complete setup script.''',
        r'''<think>
This is about designing a community token's economics on Hive Engine.
Key decisions: supply, precision, staking parameters, inflation/mining,
reward distribution, and diesel pool for liquidity.
I should cover the full lifecycle: create, enable staking, set up mining,
create a pool, and configure ScotBot for PoB rewards.
Expert-level topic combining multiple contracts.
</think>

Designing community token economics on Hive Engine requires decisions across supply, staking, rewards, and liquidity. Here is a complete setup script with commentary on each trade-off:

```python
from beem import Hive
import time

hive = Hive(keys=["5K...active_wif"])
ISSUER = "mycommunity"
SYMBOL = "TRIBE"
PAUSE = 4  # seconds between broadcasts to stay within RC limits


def broadcast(contract, action, payload):
    """Helper to broadcast and pause."""
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": contract,
            "contractAction": action,
            "contractPayload": payload,
        },
        required_auths=[ISSUER],
    )
    print(f"  {contract}.{action} broadcast")
    time.sleep(PAUSE)


# === 1. CREATE TOKEN (100 BEE cost) ===
# Decision: precision=3 is standard for community tokens.
# maxSupply should account for years of inflation.
broadcast("tokens", "create", {
    "symbol": SYMBOL,
    "name": "My Tribe Token",
    "precision": 3,
    "maxSupply": "10000000.000",  # 10M max
    "url": "https://mytribe.io",
    "isSignedWithActiveKey": True,
})

# === 2. ISSUE INITIAL SUPPLY ===
# Common split: 20% team/treasury, 80% reserved for mining/rewards
broadcast("tokens", "issue", {
    "symbol": SYMBOL,
    "to": ISSUER,
    "quantity": "2000000.000",  # 2M to treasury
    "isSignedWithActiveKey": True,
})

# === 3. ENABLE STAKING ===
# Short cooldown (7 days) encourages participation.
# Long cooldown (28+ days) encourages commitment but deters new users.
broadcast("tokens", "enableStaking", {
    "symbol": SYMBOL,
    "unstakingCooldown": 7,
    "numberTransactions": 7,  # 1 installment per day
    "isSignedWithActiveKey": True,
})

# === 4. ENABLE DELEGATION ===
# Lets large holders delegate to curators without unstaking.
broadcast("tokens", "enableDelegation", {
    "symbol": SYMBOL,
    "undelegationCooldown": 7,
    "isSignedWithActiveKey": True,
})

# === 5. CREATE MINING TOKEN (optional, 100 BEE) ===
# A separate token users stake to mine the reward token.
broadcast("tokens", "create", {
    "symbol": f"{SYMBOL}M",  # e.g., TRIBEM
    "name": f"{SYMBOL} Miner",
    "precision": 3,
    "maxSupply": "100000.000",
    "url": "https://mytribe.io",
    "isSignedWithActiveKey": True,
})

broadcast("tokens", "enableStaking", {
    "symbol": f"{SYMBOL}M",
    "unstakingCooldown": 14,
    "numberTransactions": 7,
    "isSignedWithActiveKey": True,
})

# === 6. SET UP MINING POOL ===
# Issue enough reward tokens to fund the pool
broadcast("tokens", "issue", {
    "symbol": SYMBOL,
    "to": ISSUER,
    "quantity": "3000000.000",  # 3M for mining rewards
    "isSignedWithActiveKey": True,
})

broadcast("mining", "createPool", {
    "lotteryWinners": 1,
    "lotteryIntervalHours": 1,
    "lotteryAmount": "50.000",  # 50 TRIBE per hour = 1200/day
    "minedToken": SYMBOL,
    "tokenMiners": [
        {"symbol": f"{SYMBOL}M", "multiplier": 1},
        {"symbol": SYMBOL, "multiplier": 2},  # staking TRIBE itself also mines
    ],
    "isSignedWithActiveKey": True,
})

# === 7. CREATE DIESEL POOL FOR LIQUIDITY ===
# Seed with initial liquidity to set the price
broadcast("marketpools", "createPool", {
    "tokenPair": f"{SYMBOL}:SWAP.HIVE",
    "isSignedWithActiveKey": True,
})

broadcast("marketpools", "addLiquidity", {
    "tokenPair": f"{SYMBOL}:SWAP.HIVE",
    "baseQuantity": "100000.000",     # 100K TRIBE
    "quoteQuantity": "1000.00000000", # 1000 SWAP.HIVE
    # Initial price: 0.01 SWAP.HIVE per TRIBE
    "maxPriceImpact": "50",
    "maxDeviation": "50",
})

print(f"\n{SYMBOL} token economics setup complete!")
print(f"  Max supply:      10,000,000")
print(f"  Treasury:        2,000,000 (20%)")
print(f"  Mining rewards:  3,000,000 (30%)")
print(f"  Unissued:        5,000,000 (50%) — future growth")
print(f"  Mining rate:     1,200/day (~438K/year)")
print(f"  Initial price:   0.01 SWAP.HIVE")
```

Best practices:
- **Leave 50%+ unissued** for future flexibility.
- **Mining rate** should sustain 3-5 years before hitting max supply.
- **Staking multiplier > 1** for the main token incentivizes holding over selling.
- **7-day unstaking** is the sweet spot — short enough to not scare users, long enough to prevent dump-and-run.'''
    ),

    # --- 22. Hive Engine smart contract basics ---
    (
        "hive_layer2/smart-contract-basics",
        r'''Explain how Hive Engine smart contracts work internally. How are they different from Ethereum smart contracts? Can I write my own?''',
        r'''<think>
Hive Engine smart contracts are JavaScript code running in a sandboxed VM.
Very different from Ethereum's Solidity/EVM model.
Contracts are executed by the sidechain nodes when processing custom_json ops.
Built-in contracts: tokens, market, nft, mining, marketpools, etc.
Custom contracts can be deployed but require BEE and approval.
No gas fees — operations are free (paid by Hive RC).
</think>

Hive Engine smart contracts are fundamentally different from Ethereum contracts. They are **JavaScript code** executed in a sandboxed environment on sidechain nodes.

```
Architecture Comparison:

Ethereum                          Hive Engine
─────────                         ───────────
Solidity / Vyper                  JavaScript
EVM bytecode                     JS sandbox (VM2)
Gas fees (ETH)                   Free (uses Hive RC for broadcast)
On-chain state (expensive)       Sidechain MongoDB state (cheap)
Deterministic EVM execution      Deterministic JS execution
Deploy via transaction            Deploy via custom_json + approval
```

**How a Hive Engine contract works internally:**

```javascript
// Simplified structure of a Hive Engine smart contract
// (This is how the built-in contracts are structured)

actions.create = async (payload) => {
  const { symbol, name, precision, maxSupply, url } = payload;

  // Validation
  if (!api.assert(symbol && typeof symbol === 'string', 'symbol required')) return;
  if (!api.assert(precision >= 0 && precision <= 8, 'invalid precision')) return;

  // Check if token already exists
  const existing = await api.db.findOne('tokens', { symbol });
  if (api.assert(existing === null, 'symbol already exists')) {
    // Deduct creation fee
    const fee = await api.db.findOne('params', {});
    // ... fee logic ...

    // Create the token record
    await api.db.insert('tokens', {
      issuer: api.sender,
      symbol,
      name,
      precision,
      maxSupply,
      supply: '0',
      circulatingSupply: '0',
      url,
      stakingEnabled: false,
      delegationEnabled: false,
    });

    api.emit('create', { symbol, name, precision });
  }
};

actions.transfer = async (payload) => {
  const { to, symbol, quantity, memo } = payload;

  // Load sender balance
  const balance = await api.db.findOne('balances', {
    account: api.sender, symbol
  });

  if (api.assert(balance !== null, 'balance not found')
      && api.assert(parseFloat(balance.balance) >= parseFloat(quantity),
                    'insufficient balance')) {
    // Debit sender
    balance.balance = (parseFloat(balance.balance) - parseFloat(quantity)).toFixed(precision);
    await api.db.update('balances', balance);

    // Credit recipient (create balance record if needed)
    let recipientBalance = await api.db.findOne('balances', { account: to, symbol });
    if (!recipientBalance) {
      recipientBalance = { account: to, symbol, balance: '0', stake: '0' };
      await api.db.insert('balances', recipientBalance);
    }
    recipientBalance.balance = (parseFloat(recipientBalance.balance)
                                + parseFloat(quantity)).toFixed(precision);
    await api.db.update('balances', recipientBalance);

    api.emit('transfer', { from: api.sender, to, symbol, quantity, memo });
  }
};
```

**Interacting with contracts from Python:**

```python
from beem import Hive

hive = Hive(keys=["5K...active_wif"])

# All contract interactions follow this pattern:
hive.custom_json(
    "ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",       # which contract
        "contractAction": "transfer",   # which function
        "contractPayload": {            # function arguments
            "symbol": "BEE",
            "to": "recipient",
            "quantity": "10.000",
            "memo": "test",
        },
    },
    required_auths=["sender"],
)
```

Key differences from Ethereum:
- **No gas**: Operations cost Hive Resource Credits only (free for most users).
- **JavaScript, not Solidity**: Lower barrier but less formal verification tooling.
- **MongoDB-backed state**: Fast reads via JSON-RPC, but no on-chain state proofs.
- **Custom contracts**: Deploying your own requires BEE stake and community review — the system is permissioned, not permissionless like Ethereum.'''
    ),

    # --- 23. Token distribution vesting ---
    (
        "hive_layer2/token-vesting-distribution",
        r'''How do I implement a token vesting schedule on Hive Engine? I want to distribute tokens to team members on a time-locked schedule.''',
        r'''<think>
Hive Engine doesn't have a native vesting contract.
Vesting must be implemented using staking mechanics or an off-chain scheduler.
Approach 1: Stake tokens to team members with long unstaking cooldown.
Approach 2: Build a Python scheduler that issues/transfers tokens on schedule.
I'll show the scheduler approach since it's more flexible and common.
</think>

Hive Engine lacks a native vesting contract, so vesting is typically implemented with an off-chain scheduler. Here is a production-ready vesting system:

```python
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from beem import Hive

VESTING_FILE = "vesting_schedule.json"


def create_vesting_schedule(beneficiaries: list[dict],
                            total_amount: float,
                            start_date: str,
                            duration_months: int,
                            cliff_months: int = 3,
                            symbol: str = "MYTOKEN",
                            precision: int = 3) -> dict:
    """
    Create a vesting schedule.

    beneficiaries: [{"account": "alice", "share_pct": 40}, ...]
    """
    start = datetime.fromisoformat(start_date)
    schedule = {
        "symbol": symbol,
        "precision": precision,
        "total_amount": total_amount,
        "start_date": start_date,
        "cliff_months": cliff_months,
        "duration_months": duration_months,
        "beneficiaries": [],
    }

    for b in beneficiaries:
        account = b["account"]
        share = total_amount * (b["share_pct"] / 100.0)
        monthly_amount = share / duration_months

        releases = []
        for month in range(duration_months):
            release_date = start + timedelta(days=30 * (month + 1))
            is_after_cliff = (month + 1) >= cliff_months

            # During cliff, tokens accrue but aren't released
            if is_after_cliff and month + 1 == cliff_months:
                # First release after cliff includes all accrued months
                amount = monthly_amount * cliff_months
            elif is_after_cliff:
                amount = monthly_amount
            else:
                amount = 0

            if amount > 0:
                releases.append({
                    "date": release_date.isoformat()[:10],
                    "amount": round(amount, precision),
                    "distributed": False,
                })

        schedule["beneficiaries"].append({
            "account": account,
            "total_share": round(share, precision),
            "releases": releases,
        })

    Path(VESTING_FILE).write_text(json.dumps(schedule, indent=2))
    print(f"Vesting schedule saved to {VESTING_FILE}")
    return schedule


def run_vesting_distributions(issuer: str, active_wif: str,
                              dry_run: bool = True):
    """Process pending vesting distributions."""
    schedule = json.loads(Path(VESTING_FILE).read_text())
    symbol = schedule["symbol"]
    today = datetime.now().strftime("%Y-%m-%d")
    hive = Hive(keys=[active_wif])

    distributed = 0
    for b in schedule["beneficiaries"]:
        account = b["account"]
        for release in b["releases"]:
            if release["distributed"] or release["date"] > today:
                continue

            amount = f"{release['amount']:.{schedule['precision']}f}"

            if dry_run:
                print(f"[DRY RUN] {amount} {symbol} -> @{account} "
                      f"(due: {release['date']})")
            else:
                hive.custom_json(
                    "ssc-mainnet-hive",
                    json_data={
                        "contractName": "tokens",
                        "contractAction": "transfer",
                        "contractPayload": {
                            "symbol": symbol,
                            "to": account,
                            "quantity": amount,
                            "memo": f"Vesting release: {release['date']}",
                        },
                    },
                    required_auths=[issuer],
                )
                release["distributed"] = True
                distributed += 1
                print(f"Sent {amount} {symbol} -> @{account}")
                time.sleep(4)

    if not dry_run and distributed > 0:
        Path(VESTING_FILE).write_text(json.dumps(schedule, indent=2))
        print(f"\nDistributed {distributed} vesting releases")


# --- Setup ---
create_vesting_schedule(
    beneficiaries=[
        {"account": "alice", "share_pct": 40},
        {"account": "bob", "share_pct": 35},
        {"account": "carol", "share_pct": 25},
    ],
    total_amount=300000.0,
    start_date="2026-01-01",
    duration_months=12,
    cliff_months=3,
    symbol="MYTOKEN",
)

# --- Run daily via cron ---
# Dry run first:
run_vesting_distributions("issuer_account", "5K...wif", dry_run=True)
# Then for real:
# run_vesting_distributions("issuer_account", "5K...wif", dry_run=False)
```

Run this script daily via cron or a scheduled task. The JSON file tracks which releases have been distributed, making it safe to run repeatedly.'''
    ),

    # --- 24. Pack opening mechanics ---
    (
        "hive_layer2/pack-opening-mechanics",
        r'''How do pack opening mechanics work on Hive Engine? Show me how to implement a card pack system where users buy packs and open them to receive random NFTs.''',
        r'''<think>
Pack opening on Hive Engine is used by games like Splinterlands.
The general pattern: NFT packs are fungible tokens, opening them burns
the pack token and mints random NFTs based on a rarity distribution.
On Hive Engine, this is typically done with a combination of the nft contract
and an off-chain oracle/server that handles randomness.
For a self-contained system, I'll show the pattern with custom_json
and a server-side pack opener.
</think>

Pack opening on Hive Engine combines fungible pack tokens with NFT minting. Since smart contract randomness is limited, most systems use a server-side oracle to determine pack contents.

```python
"""
Pack system architecture:
1. Pack tokens are fungible HE tokens (e.g., MYPACK)
2. User broadcasts custom_json to "open" a pack (burns the token)
3. Server watches for open events, generates random NFTs, mints them
"""
import hashlib
import json
import random
import time
import requests
from beem import Hive
from beem.blockchain import Blockchain

HE_API = "https://api.hive-engine.com/rpc/contracts"

# === RARITY DISTRIBUTION CONFIG ===
RARITY_TABLE = {
    "common":    {"weight": 60, "count_range": (3, 4)},
    "rare":      {"weight": 25, "count_range": (1, 2)},
    "epic":      {"weight": 10, "count_range": (1, 1)},
    "legendary": {"weight": 5,  "count_range": (0, 1)},
}
CARDS_PER_PACK = 5
NFT_SYMBOL = "MYCARD"
PACK_SYMBOL = "MYPACK"


def generate_pack_contents(seed: str) -> list[dict]:
    """Deterministic pack generation from a seed (tx hash)."""
    rng = random.Random(seed)
    cards = []

    # Guarantee at least 1 rare+
    rarities = list(RARITY_TABLE.keys())
    weights = [RARITY_TABLE[r]["weight"] for r in rarities]

    while len(cards) < CARDS_PER_PACK:
        rarity = rng.choices(rarities, weights=weights, k=1)[0]
        card_id = rng.randint(1, 200)  # card pool per rarity
        cards.append({
            "rarity": rarity,
            "card_template": f"{rarity}_{card_id:03d}",
            "properties": {
                "rarity": rarity,
                "template_id": str(card_id),
                "edition": "genesis",
            },
        })

    return cards


# === USER SIDE: Open a pack ===
def open_pack(account: str, active_wif: str):
    """User burns a pack token and requests opening."""
    hive = Hive(keys=[active_wif])

    # Burn the pack token
    hive.custom_json(
        "ssc-mainnet-hive",
        json_data={
            "contractName": "tokens",
            "contractAction": "transfer",
            "contractPayload": {
                "symbol": PACK_SYMBOL,
                "to": "null",              # burn
                "quantity": "1.000",
                "memo": "open_pack",
            },
        },
        required_auths=[account],
    )
    print(f"Pack burned by @{account} — awaiting NFT minting")


# === SERVER SIDE: Watch for opens and mint NFTs ===
def process_pack_opening(trx_id: str, account: str, issuer_wif: str,
                         issuer_account: str):
    """Server processes a pack opening event."""
    # Use transaction hash as deterministic seed
    seed = hashlib.sha256(trx_id.encode()).hexdigest()
    cards = generate_pack_contents(seed)

    hive = Hive(keys=[issuer_wif])

    minted = []
    for card in cards:
        hive.custom_json(
            "ssc-mainnet-hive",
            json_data={
                "contractName": "nft",
                "contractAction": "issue",
                "contractPayload": {
                    "symbol": NFT_SYMBOL,
                    "to": account,
                    "feeSymbol": "BEE",
                    "properties": card["properties"],
                    "isSignedWithActiveKey": True,
                },
            },
            required_auths=[issuer_account],
        )
        minted.append(card["card_template"])
        time.sleep(3)

    print(f"Minted {len(minted)} cards for @{account}: {minted}")
    return minted
```

Key design decisions:
- **Deterministic seed**: Using the transaction hash ensures reproducible results and prevents manipulation.
- **Burn-to-open**: Transferring to `null` is irreversible proof the pack was consumed.
- **Server-side minting**: The issuer account watches for burn events and mints NFTs. This requires the server to hold the active key.
- **Rarity weights**: Adjust `RARITY_TABLE` to control drop rates. Publish rates for transparency.'''
    ),

    # --- 25. Cross-token arbitrage bot ---
    (
        "hive_layer2/cross-token-arbitrage",
        r'''Build me a cross-token arbitrage bot for Hive Engine that finds price discrepancies between the order book and diesel pools for the same token pair.''',
        r'''<think>
Arbitrage between the HE order book (market contract) and diesel pools (marketpools).
The order book has discrete buy/sell orders; diesel pools use AMM pricing.
Strategy: compare best ask on order book vs. pool sell price, and vice versa.
If pool price < order book ask, buy from pool and sell on order book.
Need to account for trading fees on both sides.
This is expert-level — need careful slippage and fee calculations.
</think>

This bot compares prices between Hive Engine's **order book** (market contract) and **diesel pools** (AMM) to find arbitrage opportunities.

```python
import requests
import time
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass
from beem import Hive

HE_API = "https://api.hive-engine.com/rpc/contracts"
POOL_FEE = Decimal("0.0025")    # 0.25% diesel pool trading fee
MARKET_FEE = Decimal("0.0025")  # 0.25% order book trading fee
MIN_PROFIT_PCT = Decimal("0.5") # minimum 0.5% profit to execute


@dataclass
class ArbitrageOpportunity:
    symbol: str
    direction: str         # "pool_to_book" or "book_to_pool"
    buy_price: Decimal
    sell_price: Decimal
    max_quantity: Decimal
    gross_profit_pct: Decimal
    net_profit_pct: Decimal


def he_query(contract: str, table: str, query: dict,
             limit: int = 50, indexes: list = None) -> list:
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {
            "contract": contract, "table": table,
            "query": query, "limit": limit,
            "indexes": indexes or [],
        },
    }, timeout=10)
    return resp.json().get("result", [])


def get_best_orders(symbol: str) -> tuple[Decimal | None, Decimal | None,
                                          Decimal, Decimal]:
    """Get best bid/ask from the order book. Returns (bid, ask, bid_qty, ask_qty)."""
    bids = he_query("market", "buyBook", {"symbol": symbol}, limit=1,
                    indexes=[{"index": "priceDec", "descending": True}])
    asks = he_query("market", "sellBook", {"symbol": symbol}, limit=1,
                    indexes=[{"index": "priceDec", "descending": False}])

    best_bid = Decimal(bids[0]["price"]) if bids else None
    best_ask = Decimal(asks[0]["price"]) if asks else None
    bid_qty = Decimal(bids[0]["quantity"]) if bids else Decimal(0)
    ask_qty = Decimal(asks[0]["quantity"]) if asks else Decimal(0)

    return best_bid, best_ask, bid_qty, ask_qty


def get_pool_price(symbol: str) -> tuple[Decimal | None, Decimal, Decimal]:
    """Get effective price from the diesel pool. Returns (price, base_reserve, quote_reserve)."""
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0", "id": 1, "method": "findOne",
        "params": {
            "contract": "marketpools", "table": "pools",
            "query": {"tokenPair": f"{symbol}:SWAP.HIVE"},
        },
    }, timeout=10)
    pool = resp.json().get("result")
    if not pool:
        return None, Decimal(0), Decimal(0)

    base = Decimal(pool["baseQuantity"])
    quote = Decimal(pool["quoteQuantity"])
    price = quote / base if base > 0 else None
    return price, base, quote


def calc_pool_output(base_reserve: Decimal, quote_reserve: Decimal,
                     amount_in: Decimal, selling_base: bool) -> Decimal:
    """Calculate AMM output with fee."""
    amount_after_fee = amount_in * (1 - POOL_FEE)
    if selling_base:  # selling token for SWAP.HIVE
        new_base = base_reserve + amount_after_fee
        return quote_reserve - (base_reserve * quote_reserve) / new_base
    else:  # buying token with SWAP.HIVE
        new_quote = quote_reserve + amount_after_fee
        return base_reserve - (base_reserve * quote_reserve) / new_quote


def find_arbitrage(symbol: str) -> ArbitrageOpportunity | None:
    """Find arbitrage between order book and diesel pool."""
    best_bid, best_ask, bid_qty, ask_qty = get_best_orders(symbol)
    pool_price, base_res, quote_res = get_pool_price(symbol)

    if not all([best_bid, best_ask, pool_price]):
        return None

    opportunities = []

    # Strategy 1: Buy from pool, sell on order book
    # Pool effective buy price vs order book best bid
    test_qty = min(bid_qty, base_res * Decimal("0.01"))  # max 1% of pool
    if test_qty > 0:
        swap_hive_needed = test_qty * pool_price / (1 - POOL_FEE)
        effective_buy = swap_hive_needed / test_qty
        sell_price = best_bid * (1 - MARKET_FEE)

        if sell_price > effective_buy:
            profit_pct = ((sell_price - effective_buy) / effective_buy) * 100
            if profit_pct >= MIN_PROFIT_PCT:
                opportunities.append(ArbitrageOpportunity(
                    symbol=symbol, direction="pool_to_book",
                    buy_price=effective_buy, sell_price=best_bid,
                    max_quantity=test_qty,
                    gross_profit_pct=((best_bid - effective_buy) / effective_buy) * 100,
                    net_profit_pct=profit_pct,
                ))

    # Strategy 2: Buy from order book, sell to pool
    test_qty = min(ask_qty, base_res * Decimal("0.01"))
    if test_qty > 0:
        buy_cost = best_ask * (1 + MARKET_FEE)
        pool_output = calc_pool_output(base_res, quote_res, test_qty, True)
        effective_sell = pool_output / test_qty

        if effective_sell > buy_cost:
            profit_pct = ((effective_sell - buy_cost) / buy_cost) * 100
            if profit_pct >= MIN_PROFIT_PCT:
                opportunities.append(ArbitrageOpportunity(
                    symbol=symbol, direction="book_to_pool",
                    buy_price=best_ask, sell_price=effective_sell,
                    max_quantity=test_qty,
                    gross_profit_pct=((effective_sell - best_ask) / best_ask) * 100,
                    net_profit_pct=profit_pct,
                ))

    return max(opportunities, key=lambda o: o.net_profit_pct) if opportunities else None


def execute_arbitrage(opp: ArbitrageOpportunity, account: str, wif: str):
    """Execute an arbitrage trade (use with caution)."""
    hive = Hive(keys=[wif])
    qty = str(opp.max_quantity.quantize(Decimal("0.001"), ROUND_DOWN))

    if opp.direction == "pool_to_book":
        # Buy from pool
        hive.custom_json("ssc-mainnet-hive", json_data={
            "contractName": "marketpools",
            "contractAction": "swapTokens",
            "contractPayload": {
                "tokenPair": f"{opp.symbol}:SWAP.HIVE",
                "tokenSymbol": "SWAP.HIVE",
                "tokenAmount": str(opp.buy_price * opp.max_quantity),
                "tradeType": "exactInput",
                "minAmountOut": qty,
            },
        }, required_auths=[account])
        time.sleep(4)
        # Sell on order book
        hive.custom_json("ssc-mainnet-hive", json_data={
            "contractName": "market",
            "contractAction": "sell",
            "contractPayload": {
                "symbol": opp.symbol,
                "quantity": qty,
                "price": str(opp.sell_price),
            },
        }, required_auths=[account])
    print(f"Executed {opp.direction} arb: {qty} {opp.symbol} "
          f"@ {opp.net_profit_pct:.2f}% profit")


# === MAIN LOOP ===
WATCH_TOKENS = ["BEE", "DEC", "SPS", "LEO", "POB"]

if __name__ == "__main__":
    print("Scanning for arbitrage opportunities...")
    while True:
        for symbol in WATCH_TOKENS:
            opp = find_arbitrage(symbol)
            if opp:
                print(f"\n[ARB] {opp.symbol} {opp.direction}")
                print(f"  Buy:  {opp.buy_price:.8f} SWAP.HIVE")
                print(f"  Sell: {opp.sell_price:.8f} SWAP.HIVE")
                print(f"  Qty:  {opp.max_quantity}")
                print(f"  Net profit: {opp.net_profit_pct:.2f}%")
                # Uncomment to auto-execute:
                # execute_arbitrage(opp, "myaccount", "5K...wif")
        time.sleep(6)  # one Hive block
```

Risk warnings:
- **Slippage**: Large trades move the pool price. Keep trade size under 1% of pool reserves.
- **Execution risk**: The two legs are not atomic. The order book order could fill between your pool swap and sell.
- **RC costs**: Each custom_json costs Resource Credits. High-frequency trading drains RC fast.
- **Front-running**: Other bots watch the same pools. Speed matters.'''
    ),
]
