"""Hive blockchain training pairs: Hive Engine tokens and sidechain."""

PAIRS = [
    (
        "hive/hive-engine-token-creation",
        r'''How do I create a custom token on Hive Engine? Show the complete process including configuration and issuance.''',
        r'''<think>
The user wants to create a custom token on Hive Engine. I could be thinking of this as a base-layer Hive operation... but wait, Hive Engine is a sidechain, not part of the Hive base layer. Token operations are broadcast to the Hive blockchain as custom_json, but they are interpreted by the Hive Engine sidechain nodes, not by Hive witnesses.

Hmm, what custom_json id does Hive Engine use? I considered "ssc-mainnet" which was the old Steem Engine id, but actually on Hive it is "ssc-mainnet-hive". That distinction matters because using the wrong id means the sidechain nodes will not pick up your transaction at all.

Now for the creation process itself. My first thought was that creating a token is a single operation, but actually it involves multiple steps: first you create the token (which costs 100 BEE as a sidechain fee), then you configure optional properties like staking and delegation, and finally you issue the initial supply. The order matters here -- you cannot enable staking on a token that does not exist yet, and you cannot issue tokens before creation. Therefore, the workflow is: create, then configure, then issue.

Wait, what about NFTs? Those use a separate "nft" contract rather than the "tokens" contract. Since the user specifically asked about custom token creation, I should focus on fungible tokens via the "tokens" contract and its actions like "create", "issue", "enableStaking", and "enableDelegation".
</think>

Creating a token on Hive Engine involves broadcasting custom_json operations to the sidechain. Here is the complete workflow:

```javascript
const dhive = require("@hiveio/dhive");

const client = new dhive.Client(["https://api.hive.blog"]);
const activeKey = dhive.PrivateKey.fromString("5YourActiveKey");

const ACCOUNT = "myaccount";
const HE_ID = "ssc-mainnet-hive";

async function broadcastHE(payload) {
    const op = {
        required_auths: [ACCOUNT],
        required_posting_auths: [],
        id: HE_ID,
        json: JSON.stringify(payload)
    };
    return await client.broadcast.json(op, activeKey);
}

// Step 1: Create the token (costs 100 BEE)
async function createToken(symbol, name, precision, maxSupply) {
    const payload = {
        contractName: "tokens",
        contractAction: "create",
        contractPayload: {
            symbol: symbol,             // 3-10 uppercase letters
            name: name,                 // Display name
            precision: precision,       // Decimal places (0-8)
            maxSupply: maxSupply.toString(),
            url: "https://mytoken.com",
            orgName: "My Organization",
            productName: name
        }
    };

    const result = await broadcastHE(payload);
    console.log(`Token ${symbol} created: ${result.id}`);
    return result;
}

// Step 2: Issue tokens to an account
async function issueTokens(symbol, to, quantity) {
    const payload = {
        contractName: "tokens",
        contractAction: "issue",
        contractPayload: {
            symbol: symbol,
            to: to,
            quantity: quantity.toString()
        }
    };
    return await broadcastHE(payload);
}

// Step 3: Enable staking on the token
async function enableStaking(symbol, unstakingCooldown, numberTransactions) {
    const payload = {
        contractName: "tokens",
        contractAction: "enableStaking",
        contractPayload: {
            symbol: symbol,
            unstakingCooldown: unstakingCooldown,  // Days
            numberTransactions: numberTransactions  // Split unstake into N txs
        }
    };
    return await broadcastHE(payload);
}

// Step 4: Enable delegation for the token
async function enableDelegation(symbol, undelegationCooldown) {
    const payload = {
        contractName: "tokens",
        contractAction: "enableDelegation",
        contractPayload: {
            symbol: symbol,
            undelegationCooldown: undelegationCooldown  // Days
        }
    };
    return await broadcastHE(payload);
}

// Step 5: Transfer tokens
async function transferToken(to, symbol, quantity, memo) {
    const payload = {
        contractName: "tokens",
        contractAction: "transfer",
        contractPayload: {
            symbol: symbol,
            to: to,
            quantity: quantity.toString(),
            memo: memo || ""
        }
    };
    return await broadcastHE(payload);
}

// Query token info from Hive Engine API
async function getTokenInfo(symbol) {
    const resp = await fetch("https://api.hive-engine.com/rpc/contracts", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            method: "find",
            params: {
                contract: "tokens",
                table: "tokens",
                query: {symbol: symbol}
            }
        })
    });
    const data = await resp.json();
    const token = data.result[0];
    if (token) {
        console.log(`Token: ${token.symbol} (${token.name})`);
        console.log(`  Supply: ${token.supply} / ${token.maxSupply}`);
        console.log(`  Precision: ${token.precision}`);
        console.log(`  Staking: ${token.stakingEnabled}`);
        console.log(`  Delegation: ${token.delegationEnabled}`);
    }
    return token;
}

// Full workflow
async function main() {
    // Create token (costs 100 BEE)
    await createToken("MYTKN", "My Token", 3, 1000000);

    // Enable staking (7-day unstake, split into 4 transactions)
    await enableStaking("MYTKN", 7, 4);

    // Enable delegation (3-day undelegation cooldown)
    await enableDelegation("MYTKN", 3);

    // Issue initial supply
    await issueTokens("MYTKN", ACCOUNT, 100000);

    // Transfer some tokens
    await transferToken("recipient", "MYTKN", "1000", "Welcome bonus");
}

// main().catch(console.error);
```

Token creation costs 100 BEE tokens. Symbols must be 3-10 uppercase letters, unique on the sidechain. Precision determines decimal places (e.g., 3 means 1.000). Staking and delegation are optional features that add DeFi-like functionality to your token.
'''
    ),
    (
        "hive/hive-engine-market-orders",
        r'''How do I place buy and sell orders on the Hive Engine token market?''',
        r'''Hive Engine has a built-in decentralized exchange where tokens can be traded against SWAP.HIVE (wrapped HIVE on the sidechain). Here is how to interact with the market:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import requests

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourActiveKey"]
)

ACCOUNT = "myaccount"
HE_API = "https://api.hive-engine.com/rpc/contracts"

def he_broadcast(payload):
    """Broadcast a Hive Engine operation."""
    op = Custom_json(**{
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps(payload)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()

def he_query(contract, table, query, limit=100, offset=0):
    """Query the Hive Engine sidechain."""
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "find",
        "params": {
            "contract": contract,
            "table": table,
            "query": query,
            "limit": limit,
            "offset": offset
        }
    }, timeout=15)
    return resp.json().get("result", [])

# Place a buy order (buying tokens with SWAP.HIVE)
def place_buy_order(symbol, quantity, price):
    """Place a buy order on the Hive Engine market.

    Args:
        symbol: Token to buy (e.g., "BEE")
        quantity: Amount of tokens to buy
        price: Price per token in SWAP.HIVE
    """
    payload = {
        "contractName": "market",
        "contractAction": "buy",
        "contractPayload": {
            "symbol": symbol,
            "quantity": str(quantity),
            "price": str(price)
        }
    }
    result = he_broadcast(payload)
    total_cost = float(quantity) * float(price)
    print(f"Buy order: {quantity} {symbol} at {price} SWAP.HIVE each "
          f"(total: {total_cost:.8f} SWAP.HIVE)")
    return result

# Place a sell order (selling tokens for SWAP.HIVE)
def place_sell_order(symbol, quantity, price):
    """Place a sell order on the Hive Engine market."""
    payload = {
        "contractName": "market",
        "contractAction": "sell",
        "contractPayload": {
            "symbol": symbol,
            "quantity": str(quantity),
            "price": str(price)
        }
    }
    result = he_broadcast(payload)
    total_value = float(quantity) * float(price)
    print(f"Sell order: {quantity} {symbol} at {price} SWAP.HIVE each "
          f"(total: {total_value:.8f} SWAP.HIVE)")
    return result

# Cancel an order
def cancel_order(order_type, order_id):
    """Cancel an open order.

    Args:
        order_type: "buy" or "sell"
        order_id: The order ID from the sidechain
    """
    payload = {
        "contractName": "market",
        "contractAction": "cancel",
        "contractPayload": {
            "type": order_type,
            "id": order_id
        }
    }
    return he_broadcast(payload)

# Get order book for a token
def get_order_book(symbol, limit=20):
    """Get buy and sell orders for a token."""
    buy_orders = he_query("market", "buyBook", {"symbol": symbol}, limit)
    sell_orders = he_query("market", "sellBook", {"symbol": symbol}, limit)

    # Sort: buys descending by price, sells ascending
    buy_orders.sort(key=lambda x: float(x["price"]), reverse=True)
    sell_orders.sort(key=lambda x: float(x["price"]))

    print(f"\n=== Order Book: {symbol} ===")
    print(f"\n{'Price':>14} {'Quantity':>14} {'Total':>14}")
    print("--- SELL ORDERS ---")
    for o in sell_orders[:10]:
        qty = float(o["quantity"])
        price = float(o["price"])
        print(f"{price:>14.8f} {qty:>14.3f} {qty*price:>14.8f}")

    print("--- BUY ORDERS ---")
    for o in buy_orders[:10]:
        qty = float(o["quantity"])
        price = float(o["price"])
        print(f"{price:>14.8f} {qty:>14.3f} {qty*price:>14.8f}")

    if buy_orders and sell_orders:
        spread = float(sell_orders[0]["price"]) - float(buy_orders[0]["price"])
        print(f"\nSpread: {spread:.8f} SWAP.HIVE")

    return buy_orders, sell_orders

# Get my open orders
def get_my_orders(symbol=None):
    """Get open orders for my account."""
    query = {"account": ACCOUNT}
    if symbol:
        query["symbol"] = symbol

    buys = he_query("market", "buyBook", query)
    sells = he_query("market", "sellBook", query)

    print(f"\nOpen orders for @{ACCOUNT}:")
    for o in buys:
        print(f"  BUY  {o['quantity']} {o['symbol']} at {o['price']} "
              f"(ID: {o.get('_id', 'N/A')})")
    for o in sells:
        print(f"  SELL {o['quantity']} {o['symbol']} at {o['price']} "
              f"(ID: {o.get('_id', 'N/A')})")

    return buys, sells

# Usage
get_order_book("BEE")
# place_buy_order("BEE", "100", "0.01000000")
# place_sell_order("BEE", "50", "0.02000000")
```

The Hive Engine market trades all tokens against SWAP.HIVE (wrapped HIVE on the sidechain). To get SWAP.HIVE, you deposit HIVE to the @honey-swap account. Orders are matched on the sidechain nodes, not on the Hive base layer.
'''
    ),
    (
        "hive/hive-engine-staking",
        r'''How do I stake and unstake tokens on Hive Engine? Show the staking, delegation, and reward distribution mechanisms.''',
        r'''Staking on Hive Engine locks tokens for governance, rewards, and other token-specific benefits. Here is how to manage staking operations:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import requests

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourActiveKey"]
)

ACCOUNT = "myaccount"
HE_API = "https://api.hive-engine.com/rpc/contracts"

def he_broadcast(payload):
    op = Custom_json(**{
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps(payload)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()

def he_query(contract, table, query, limit=100):
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {"contract": contract, "table": table,
                   "query": query, "limit": limit}
    }, timeout=15)
    return resp.json().get("result", [])

# Stake tokens
def stake_tokens(symbol, to_account, quantity):
    """Stake tokens to an account (can stake to yourself or others)."""
    payload = {
        "contractName": "tokens",
        "contractAction": "stake",
        "contractPayload": {
            "to": to_account,
            "symbol": symbol,
            "quantity": str(quantity)
        }
    }
    result = he_broadcast(payload)
    print(f"Staked {quantity} {symbol} to @{to_account}")
    return result

# Unstake tokens (starts cooldown)
def unstake_tokens(symbol, quantity):
    """Begin unstaking tokens (subject to cooldown period)."""
    payload = {
        "contractName": "tokens",
        "contractAction": "unstake",
        "contractPayload": {
            "symbol": symbol,
            "quantity": str(quantity)
        }
    }
    result = he_broadcast(payload)
    print(f"Unstaking {quantity} {symbol} (cooldown started)")
    return result

# Cancel an unstake in progress
def cancel_unstake(txID):
    """Cancel a pending unstake operation."""
    payload = {
        "contractName": "tokens",
        "contractAction": "cancelUnstake",
        "contractPayload": {
            "txID": txID
        }
    }
    return he_broadcast(payload)

# Delegate staked tokens
def delegate_staked(symbol, to_account, quantity):
    """Delegate staked tokens to another account."""
    payload = {
        "contractName": "tokens",
        "contractAction": "delegate",
        "contractPayload": {
            "to": to_account,
            "symbol": symbol,
            "quantity": str(quantity)
        }
    }
    result = he_broadcast(payload)
    print(f"Delegated {quantity} staked {symbol} to @{to_account}")
    return result

# Undelegate staked tokens
def undelegate_staked(symbol, from_account, quantity):
    """Remove a staking delegation."""
    payload = {
        "contractName": "tokens",
        "contractAction": "undelegate",
        "contractPayload": {
            "from": from_account,
            "symbol": symbol,
            "quantity": str(quantity)
        }
    }
    return he_broadcast(payload)

# Check staking balances
def get_staking_info(account, symbol=None):
    """Get staking balances for an account."""
    query = {"account": account}
    if symbol:
        query["symbol"] = symbol

    balances = he_query("tokens", "balances", query)

    print(f"\nToken balances for @{account}:")
    print(f"{'Symbol':>10} {'Balance':>14} {'Staked':>14} "
          f"{'Delegated In':>14} {'Delegated Out':>14}")
    print("-" * 70)

    for b in balances:
        sym = b["symbol"]
        bal = b.get("balance", "0")
        staked = b.get("stake", "0")
        deleg_in = b.get("delegationsIn", "0")
        deleg_out = b.get("delegationsOut", "0")
        if float(bal) > 0 or float(staked) > 0:
            print(f"{sym:>10} {bal:>14} {staked:>14} "
                  f"{deleg_in:>14} {deleg_out:>14}")

    # Check pending unstakes
    unstakes = he_query("tokens", "pendingUnstakes", {"account": account})
    if unstakes:
        print(f"\nPending unstakes:")
        for u in unstakes:
            print(f"  {u['quantity']} {u['symbol']} "
                  f"(tx: {u.get('txID', 'N/A')[:20]}...)")

    return balances

# Usage
get_staking_info(ACCOUNT)
# stake_tokens("BEE", ACCOUNT, "100")
# delegate_staked("BEE", "friend", "50")
# unstake_tokens("BEE", "25")
```

Hive Engine staking mechanics:
- Staking locks tokens and may provide governance weight or reward multipliers
- Unstaking has a cooldown (set by token creator, e.g., 7 days)
- Unstaking can be split into multiple transactions (gradual release)
- Staked tokens can be delegated to other accounts
- Undelegation also has a cooldown period
- Token creators define staking parameters at token creation time
'''
    ),
    (
        "hive/hive-engine-queries",
        r'''How do I query token balances, market history, and contract data from the Hive Engine sidechain API?''',
        r'''The Hive Engine sidechain exposes a JSON-RPC API for querying contracts, balances, market data, and transaction history. Here is a comprehensive query library:

```python
import requests
import json
from datetime import datetime

HE_API = "https://api.hive-engine.com/rpc/contracts"
HE_HISTORY = "https://history.hive-engine.com"

def he_find(contract, table, query, limit=1000, offset=0):
    """Query a Hive Engine contract table."""
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "find",
        "params": {
            "contract": contract,
            "table": table,
            "query": query,
            "limit": limit,
            "offset": offset
        }
    }, timeout=15)
    return resp.json().get("result", [])

def he_findOne(contract, table, query):
    """Query a single record from Hive Engine."""
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "findOne",
        "params": {
            "contract": contract,
            "table": table,
            "query": query
        }
    }, timeout=15)
    return resp.json().get("result", None)

# Token queries
def get_token_details(symbol):
    """Get full token configuration."""
    token = he_findOne("tokens", "tokens", {"symbol": symbol})
    if token:
        print(f"=== {token['symbol']} ({token['name']}) ===")
        print(f"  Issuer:        @{token['issuer']}")
        print(f"  Supply:        {token['supply']}")
        print(f"  Max Supply:    {token['maxSupply']}")
        print(f"  Precision:     {token['precision']}")
        print(f"  Staking:       {token.get('stakingEnabled', False)}")
        print(f"  Delegation:    {token.get('delegationEnabled', False)}")
    return token

def get_all_balances(account):
    """Get all token balances for an account."""
    balances = he_find("tokens", "balances", {"account": account})
    non_zero = [b for b in balances
                if float(b.get("balance", "0")) > 0
                or float(b.get("stake", "0")) > 0]

    print(f"\nAll tokens held by @{account} ({len(non_zero)} tokens):")
    for b in sorted(non_zero, key=lambda x: -float(x.get("balance", "0"))):
        bal = float(b.get("balance", "0"))
        stk = float(b.get("stake", "0"))
        if bal > 0 or stk > 0:
            print(f"  {b['symbol']:>10}: {bal:>14.{3}f} liquid, "
                  f"{stk:>14.{3}f} staked")

    return non_zero

# Market queries
def get_market_metrics(symbol):
    """Get market metrics for a token."""
    metrics = he_findOne("market", "metrics", {"symbol": symbol})
    if metrics:
        print(f"\nMarket metrics for {symbol}:")
        print(f"  Last price:  {metrics.get('lastPrice', 'N/A')}")
        print(f"  Highest bid: {metrics.get('highestBid', 'N/A')}")
        print(f"  Lowest ask:  {metrics.get('lowestAsk', 'N/A')}")
        print(f"  Volume (24h):{metrics.get('volume', 'N/A')}")
        print(f"  Volume HIVE: {metrics.get('volumeExpiration', 'N/A')}")
    return metrics

def get_trade_history(symbol, limit=50):
    """Get recent trades for a token."""
    trades = he_find("market", "tradesHistory",
                     {"symbol": symbol}, limit)
    trades.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

    print(f"\nRecent trades for {symbol}:")
    for t in trades[:20]:
        ts = datetime.fromtimestamp(t.get("timestamp", 0))
        qty = t.get("quantity", "0")
        price = t.get("price", "0")
        buyer = t.get("buyer", "?")
        seller = t.get("seller", "?")
        print(f"  [{ts}] {qty} @ {price} "
              f"({buyer} <- {seller})")

    return trades

# Top token holders (rich list)
def get_rich_list(symbol, limit=20):
    """Get top holders of a token."""
    balances = he_find("tokens", "balances",
                       {"symbol": symbol}, limit=limit)
    # Sort by total holdings (liquid + staked)
    for b in balances:
        b["_total"] = float(b.get("balance", "0")) + float(b.get("stake", "0"))
    balances.sort(key=lambda x: -x["_total"])

    print(f"\nTop {limit} holders of {symbol}:")
    for i, b in enumerate(balances[:limit]):
        print(f"  {i+1:>3}. @{b['account']:20s}: "
              f"{b['_total']:>14.3f} total "
              f"({b.get('balance', '0')} liquid, {b.get('stake', '0')} staked)")

    return balances

# Usage
get_token_details("BEE")
get_all_balances("splinterlands")
get_market_metrics("SPS")
get_rich_list("BEE", limit=10)
```

The Hive Engine API uses a contract-based query model. Each contract (tokens, market, nft) has its own tables. The "find" method is the primary query tool, supporting MongoDB-style queries with filters, limits, and offsets. For production use, consider running your own Hive Engine node for better performance and reliability.
'''
    ),
    (
        "hive/hive-engine-nft-marketplace",
        r'''How do I build an NFT marketplace on Hive Engine? Show listing, buying, and querying NFTs.''',
        r'''Hive Engine's NFT contract supports creating, listing, and trading non-fungible tokens. Here is how to build marketplace interactions:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import requests

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourActiveKey"]
)

ACCOUNT = "myaccount"
HE_API = "https://api.hive-engine.com/rpc/contracts"

def he_broadcast(payload):
    op = Custom_json(**{
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps(payload)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()

def he_query(contract, table, query, limit=100):
    resp = requests.post(HE_API, json={
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {"contract": contract, "table": table,
                   "query": query, "limit": limit}
    }, timeout=15)
    return resp.json().get("result", [])

# List an NFT for sale
def list_nft_for_sale(nft_symbol, nft_id, price, price_symbol="BEE"):
    """List an NFT on the marketplace."""
    payload = {
        "contractName": "nftmarket",
        "contractAction": "sell",
        "contractPayload": {
            "symbol": nft_symbol,
            "nfts": [nft_id],
            "price": str(price),
            "priceSymbol": price_symbol,
            "fee": 500  # 5% marketplace fee (in basis points)
        }
    }
    result = he_broadcast(payload)
    print(f"Listed NFT {nft_symbol}#{nft_id} for {price} {price_symbol}")
    return result

# Buy an NFT from the marketplace
def buy_nft(nft_symbol, order_id, marketplace_account=""):
    """Buy a listed NFT."""
    payload_data = {
        "symbol": nft_symbol,
        "order": order_id,
    }
    if marketplace_account:
        payload_data["marketplace"] = marketplace_account

    payload = {
        "contractName": "nftmarket",
        "contractAction": "buy",
        "contractPayload": payload_data
    }
    result = he_broadcast(payload)
    print(f"Bought NFT from order {order_id}")
    return result

# Cancel a listing
def cancel_nft_listing(nft_symbol, order_id):
    """Cancel an NFT marketplace listing."""
    payload = {
        "contractName": "nftmarket",
        "contractAction": "cancel",
        "contractPayload": {
            "symbol": nft_symbol,
            "order": order_id
        }
    }
    return he_broadcast(payload)

# Query NFTs owned by an account
def get_my_nfts(nft_symbol, account=None):
    """Get NFTs owned by an account."""
    owner = account or ACCOUNT
    nfts = he_query("nft", f"{nft_symbol}instances",
                    {"account": owner}, limit=100)

    print(f"\n@{owner}'s {nft_symbol} NFTs ({len(nfts)}):")
    for nft in nfts:
        nft_id = nft.get("_id")
        props = nft.get("properties", {})
        print(f"  #{nft_id}: {json.dumps(props)[:80]}")

    return nfts

# Query marketplace listings
def get_marketplace_listings(nft_symbol, limit=20):
    """Get active marketplace listings for an NFT collection."""
    listings = he_query("nftmarket", f"{nft_symbol}sellBook",
                        {}, limit=limit)

    # Sort by price
    for l in listings:
        l["_price_float"] = float(l.get("price", "0"))
    listings.sort(key=lambda x: x["_price_float"])

    print(f"\nMarketplace listings for {nft_symbol}:")
    for l in listings[:limit]:
        nft_id = l.get("nftId", "?")
        price = l.get("price", "0")
        symbol = l.get("priceSymbol", "BEE")
        seller = l.get("account", "?")
        order_id = l.get("_id", "?")
        print(f"  #{nft_id} by @{seller}: {price} {symbol} "
              f"(order: {order_id})")

    return listings

# Get NFT collection statistics
def get_nft_collection_stats(nft_symbol):
    """Get statistics for an NFT collection."""
    # Get total supply
    instances = he_query("nft", f"{nft_symbol}instances", {}, limit=1)

    # Get collection info
    collection = he_query("nft", "nfts", {"symbol": nft_symbol})

    if collection:
        c = collection[0]
        print(f"\n=== {nft_symbol} Collection ===")
        print(f"  Name:      {c.get('name', 'N/A')}")
        print(f"  Issuer:    @{c.get('issuer', 'N/A')}")
        print(f"  Max supply:{c.get('maxSupply', 'N/A')}")
        print(f"  Circulating: {c.get('circulatingSupply', 'N/A')}")

    # Floor price from listings
    listings = he_query("nftmarket", f"{nft_symbol}sellBook", {}, limit=100)
    if listings:
        prices = [float(l["price"]) for l in listings]
        floor = min(prices)
        avg = sum(prices) / len(prices)
        print(f"  Floor price: {floor:.3f}")
        print(f"  Avg listing: {avg:.3f}")
        print(f"  Active listings: {len(listings)}")

    return collection

# Usage
# list_nft_for_sale("MYART", "1", "10.000", "BEE")
# get_marketplace_listings("MYART")
# get_my_nfts("MYART")
# get_nft_collection_stats("MYART")
```

Hive Engine NFT marketplace supports fixed-price listings with configurable marketplace fees. The fee system allows third-party marketplaces to earn revenue by facilitating trades. All NFT operations use the active key since they involve asset transfers.
'''
    ),
]
