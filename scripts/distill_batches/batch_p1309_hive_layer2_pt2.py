"""Hive Layer 2 training pairs (part 2a): Splinterlands, DeFi, advanced Hive Engine."""

PAIRS = [
    (
        "hive_layer2/splinterlands-card-api",
        r'''How do I query the Splinterlands API to get card details and collection info for a player using Python?''',
        r'''<think>
Splinterlands exposes a public REST API at api.splinterlands.com. Key endpoints:
- /cards/get_details returns all card templates with stats, editions, rarities.
- /cards/collection/{player} returns a player's owned cards with UIDs, level, gold foil status.
The response is JSON. I should show fetching both card details and a player collection,
then cross-referencing owned cards with template data for readable output.
No auth needed for read-only queries.
</think>

```python
import requests

API = "https://api2.splinterlands.com"

def get_card_details():
    """Fetch all card templates (stats, mana, editions)."""
    resp = requests.get(f"{API}/cards/get_details")
    resp.raise_for_status()
    return {c["id"]: c for c in resp.json()}

def get_collection(player: str):
    """Fetch a player's card collection."""
    resp = requests.get(f"{API}/cards/collection/{player}")
    resp.raise_for_status()
    return resp.json()["cards"]

# Usage
templates = get_card_details()
cards = get_collection("splinterlands")
for card in cards[:5]:
    t = templates.get(card["card_detail_id"], {})
    print(f"{t.get('name','?')} | Lvl {card['level']} | Gold: {card['gold']}")
```'''
    ),
    (
        "hive_layer2/splinterlands-battle-history",
        r'''Write Python to fetch and analyze a Splinterlands player's recent battle history — win rate, most-used summoner, etc.''',
        r'''<think>
The battle history endpoint is /battle/history?player={name}&limit={n}.
Each battle result contains winner, player1, player2, summoner info, mana cap, and ruleset.
I need to iterate results, count wins, and tally summoner usage.
Using collections.Counter for summoner frequency is clean.
The limit param caps at 50 per request typically.
</think>

```python
import requests
from collections import Counter

def battle_stats(player: str, limit: int = 50):
    url = "https://api2.splinterlands.com/battle/history"
    resp = requests.get(url, params={"player": player, "limit": limit})
    resp.raise_for_status()
    battles = resp.json()["battles"]

    wins, summoners = 0, Counter()
    for b in battles:
        if b.get("winner") == player:
            wins += 1
        # Find which side this player was on
        side = "1" if b.get("player_1") == player else "2"
        summoner_id = b.get(f"player_{side}_summoner_id")
        if summoner_id:
            summoners[summoner_id] += 1

    total = len(battles)
    print(f"Record: {wins}W / {total - wins}L ({wins/total*100:.1f}% win rate)")
    print(f"Top summoners: {summoners.most_common(3)}")
    return {"wins": wins, "total": total, "top_summoners": summoners.most_common(5)}

battle_stats("splinterlands")
```'''
    ),
    (
        "hive_layer2/splinterlands-market-bot",
        r'''Build a simple Splinterlands market bot that watches card prices and buys when a card drops below a target price using the market API and Hive custom_json.''',
        r'''<think>
Splinterlands market listings come from /market/for_sale_grouped or /market/for_sale_by_card.
Buying a card requires broadcasting a custom_json on Hive with id="sm_market_purchase"
and a JSON payload containing the market listing IDs.
I need beem for the Hive broadcast. The bot should poll periodically, compare
lowest listing vs target, and execute the purchase custom_json if price is right.
This is advanced — requires active key for custom_json posting.
Must warn about risk and rate limiting.
</think>

```python
import time, json, requests
from beem import Hive
from beem.transactionbuilder import TransactionBuilder

API = "https://api2.splinterlands.com"
HIVE = Hive(keys=["5Jyour_active_key"])
ACCOUNT = "youraccount"

TARGETS = {"Djinn Oshannus": 2.50}  # card_name -> max USD price

def get_cheapest(card_detail_id: int):
    resp = requests.get(f"{API}/market/for_sale_by_card",
                        params={"card_detail_id": card_detail_id})
    resp.raise_for_status()
    listings = sorted(resp.json(), key=lambda x: float(x["buy_price"]))
    return listings[0] if listings else None

def buy_card(listing_id: str):
    op = ["custom_json", {
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "sm_market_purchase",
        "json": json.dumps({"items": [listing_id], "price": None, "currency": "DEC"})
    }]
    tx = TransactionBuilder(blockchain_instance=HIVE)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()

# Main loop (card_detail_id 330 = Djinn Oshannus)
while True:
    listing = get_cheapest(330)
    if listing and float(listing["buy_price"]) <= TARGETS["Djinn Oshannus"]:
        print(f"Buying at ${listing['buy_price']}")
        buy_card(listing["market_id"])
    time.sleep(30)  # respect rate limits
```'''
    ),
    (
        "hive_layer2/hive-engine-witness-nodes",
        r'''How do Hive Engine witness nodes work? Show me how to query the current witness list and check a witness node's status.''',
        r'''<think>
Hive Engine runs its own sidechain with a DPoS witness system separate from Hive L1.
Witnesses run sidechain nodes and validate blocks. The witness list is queryable
via the Hive Engine RPC contracts API using the "witnesses" table in the "witnesses" contract.
I can use the standard SSC JSON-RPC endpoint to find active witnesses, their signing keys,
approval weights, and whether they're enabled. This is intermediate-level knowledge.
</think>

```python
import requests

HE_API = "https://api.hive-engine.com/rpc/contracts"

def query_he(contract, table, query=None, limit=100, offset=0):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {"contract": contract, "table": table,
                   "query": query or {}, "limit": limit, "offset": offset}
    }
    return requests.post(HE_API, json=payload).json()["result"]

# Get all witnesses sorted by approval weight
witnesses = query_he("witnesses", "witnesses")
witnesses.sort(key=lambda w: float(w.get("approvalWeight", "0")), reverse=True)

print(f"{'Rank':<5} {'Account':<20} {'Approval Weight':<20} {'Enabled'}")
for i, w in enumerate(witnesses[:20], 1):
    print(f"{i:<5} {w['account']:<20} {w['approvalWeight']:<20} {w['enabled']}")

# Check specific witness
def check_witness(name):
    results = query_he("witnesses", "witnesses", {"account": name})
    if results:
        w = results[0]
        print(f"\n{name}: enabled={w['enabled']}, "
              f"missedRounds={w.get('missedRounds', 0)}, "
              f"signingKey={w.get('signingKey', 'N/A')[:20]}...")
    else:
        print(f"{name} not found in witness list")

check_witness("primersion")
```'''
    ),
    (
        "hive_layer2/sidechain-custom-json",
        r'''How do I broadcast custom_json operations to Hive Engine's sidechain? Show examples for token transfers and contract interactions.''',
        r'''<think>
Hive Engine operations are broadcast as Hive L1 custom_json with id="ssc-mainnet-hive".
The JSON payload specifies contractName, contractAction, and contractPayload.
Common operations: tokens/transfer, tokens/stake, tokens/delegate, market/buy, market/sell.
Using beem to broadcast is standard. The sidechain picks up the custom_json from L1 blocks
and processes it. Active key is needed for financial operations.
</think>

```python
import json
from beem import Hive
from beem.transactionbuilder import TransactionBuilder

hive = Hive(keys=["5Jyour_active_key"])
ACCOUNT = "youraccount"

def sidechain_op(contract: str, action: str, payload: dict):
    """Broadcast a Hive Engine sidechain operation."""
    op = ["custom_json", {
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({
            "contractName": contract,
            "contractAction": action,
            "contractPayload": payload
        })
    }]
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()

# Transfer tokens
sidechain_op("tokens", "transfer", {
    "symbol": "BEE", "to": "recipient", "quantity": "10", "memo": "payment"
})

# Stake tokens
sidechain_op("tokens", "stake", {
    "to": ACCOUNT, "symbol": "WORKERBEE", "quantity": "100"
})

# Place market sell order
sidechain_op("market", "sell", {
    "symbol": "LEO", "quantity": "50", "price": "0.15"
})
```'''
    ),
    (
        "hive_layer2/token-governance-voting",
        r'''Show me how to implement token-based governance voting on Hive Engine — creating proposals and casting weighted votes.''',
        r'''<think>
Hive Engine doesn't have a built-in governance contract for arbitrary DAOs, so tribes
typically use the tokenfunds contract or custom approaches. The tokenfunds contract
supports proposals and voting weighted by staked token balance.
Key actions: tokenfunds/createProposal, tokenfunds/approveProposal, with voting
power proportional to staked holdings. I'll show both creating proposals and
voting, plus querying proposal status. This is advanced territory.
</think>

```python
import json, requests
from beem import Hive
from beem.transactionbuilder import TransactionBuilder

HE_API = "https://api.hive-engine.com/rpc/contracts"
hive = Hive(keys=["5Jactive_key"])
ACCOUNT = "youraccount"

def he_broadcast(contract, action, payload):
    op = ["custom_json", {
        "required_auths": [ACCOUNT], "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({"contractName": contract,
                            "contractAction": action,
                            "contractPayload": payload})
    }]
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()

# Create a DAO proposal (requires tokenfunds config for the token)
he_broadcast("tokenfunds", "createProposal", {
    "fundId": "LEO_DAO",
    "title": "Fund new frontend feature",
    "startDate": "2026-04-01T00:00:00.000Z",
    "endDate": "2026-04-15T00:00:00.000Z",
    "amountPerDay": "100",
    "payout": {"type": "user", "name": "devaccount"}
})

# Vote on a proposal (weight = staked token balance)
he_broadcast("tokenfunds", "approveProposal", {
    "id": "LEO_DAO:7"  # fundId:proposalId
})

# Query active proposals
def get_proposals(fund_id):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "find",
               "params": {"contract": "tokenfunds", "table": "proposals",
                           "query": {"fundId": fund_id}, "limit": 20}}
    return requests.post(HE_API, json=payload).json()["result"]

for p in get_proposals("LEO_DAO"):
    print(f"#{p['_id']}: {p['title']} | Approvals: {p.get('approvalWeight', '0')}")
```'''
    ),
    (
        "hive_layer2/tribe-reward-pool",
        r'''Explain how tribe reward pool distribution works on Hive Engine and write code to calculate a post's pending tribe rewards.''',
        r'''<think>
Tribe tokens (like LEO, POB, NEOXAG) have their own reward pools modeled after Hive's.
Each tribe has a reward pool with a daily emission rate. Votes on posts allocate
rshares proportional to staked tribal token. The scotbot processes votes and
distributes rewards from the pool. Pending rewards can be queried via the
scot API at scot-api.hive-engine.com. The reward curve (linear or convergent)
and author/curation split are configured per tribe.
</think>

```python
import requests

SCOT_API = "https://scot-api.hive-engine.com"
HE_API = "https://api.hive-engine.com/rpc/contracts"

def get_tribe_config(symbol: str):
    """Get tribe reward pool config."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "findOne",
               "params": {"contract": "comments", "table": "rewardPools",
                           "query": {"symbol": symbol}}}
    return requests.post(HE_API, json=payload).json()["result"]

def get_post_rewards(author: str, permlink: str, symbol: str = "LEO"):
    """Fetch pending tribe rewards for a post."""
    url = f"{SCOT_API}/@{author}/{permlink}"
    resp = requests.get(url, params={"hive": "1"})
    resp.raise_for_status()
    data = resp.json()
    if symbol in data:
        info = data[symbol]
        pending = float(info.get("pending_token", 0)) / (10 ** info.get("precision", 3))
        author_pct = info.get("author_payout_pct", 50) / 100
        return {
            "total_pending": pending,
            "author_reward": pending * author_pct,
            "curation_reward": pending * (1 - author_pct),
            "votes": info.get("total_votes", 0),
            "rshares": info.get("total_rshares", 0)
        }
    return None

rewards = get_post_rewards("leofinance", "some-permlink", "LEO")
if rewards:
    print(f"Pending: {rewards['total_pending']:.3f} LEO")
    print(f"Author: {rewards['author_reward']:.3f} | Curation: {rewards['curation_reward']:.3f}")
```'''
    ),
    (
        "hive_layer2/diesel-pool-impermanent-loss",
        r'''Write a calculator for impermanent loss in Hive Engine diesel pools, comparing LP position value against simply holding.''',
        r'''<think>
Diesel pools are Hive Engine's AMM (constant product x*y=k). Impermanent loss (IL)
occurs when token prices diverge from the ratio at deposit time. The IL formula is:
IL = 2*sqrt(r)/(1+r) - 1, where r = new_price_ratio / initial_price_ratio.
I should also fetch real pool data from the "marketpools" contract to get current
reserves and compute actual price ratios. This helps LPs evaluate whether
swap fees earned offset the IL. Advanced DeFi concept.
</think>

```python
import requests, math

HE_API = "https://api.hive-engine.com/rpc/contracts"

def impermanent_loss(price_ratio_change: float) -> float:
    """Calculate IL given ratio of new price / entry price. Returns negative %."""
    r = price_ratio_change
    return 2 * math.sqrt(r) / (1 + r) - 1

def get_pool(pair: str):
    """Fetch diesel pool info (e.g., 'SWAP.HIVE:LEO')."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "findOne",
               "params": {"contract": "marketpools", "table": "pools",
                           "query": {"tokenPair": pair}}}
    return requests.post(HE_API, json=payload).json()["result"]

def analyze_lp_position(pair: str, entry_price: float, investment_usd: float):
    pool = get_pool(pair)
    base_qty = float(pool["baseQuantity"])
    quote_qty = float(pool["quoteQuantity"])
    current_price = base_qty / quote_qty

    ratio = current_price / entry_price
    il = impermanent_loss(ratio)

    hold_value = investment_usd  # simplified: half in each token
    lp_value = investment_usd * (1 + il)

    print(f"Pool: {pair}")
    print(f"Entry price: {entry_price:.4f} | Current: {current_price:.4f}")
    print(f"Price change: {(ratio - 1) * 100:+.2f}%")
    print(f"Impermanent loss: {il * 100:.2f}%")
    print(f"LP value: ${lp_value:.2f} vs Hold: ${investment_usd:.2f}")
    print(f"IL cost: ${investment_usd * abs(il):.2f}")

analyze_lp_position("SWAP.HIVE:SPS", entry_price=0.05, investment_usd=1000)
```'''
    ),
    (
        "hive_layer2/multi-token-portfolio-tracker",
        r'''Build a Hive Engine multi-token portfolio tracker that shows balances, USD values, and 24h changes for all tokens a user holds.''',
        r'''<think>
I need to combine two data sources: the user's token balances from the "tokens" contract
"balances" table, and token market prices from the "market" contract "metrics" table.
For USD conversion, I can use SWAP.HIVE as the bridge currency and get HIVE/USD from
CoinGecko or a similar API. The metrics table has lastPrice, priceChangePercent,
and volume. I'll aggregate into a clean portfolio view.
</think>

```python
import requests

HE_API = "https://api.hive-engine.com/rpc/contracts"

def he_find(contract, table, query, limit=1000):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "find",
               "params": {"contract": contract, "table": table,
                           "query": query, "limit": limit}}
    return requests.post(HE_API, json=payload).json()["result"]

def get_hive_usd():
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": "hive", "vs_currencies": "usd"})
    return r.json()["hive"]["usd"]

def portfolio(account: str):
    hive_usd = get_hive_usd()
    balances = he_find("tokens", "balances", {"account": account})
    metrics = {m["symbol"]: m for m in he_find("market", "metrics", {})}

    holdings = []
    for b in balances:
        bal = float(b["balance"]) + float(b.get("stake", "0"))
        if bal < 0.001:
            continue
        m = metrics.get(b["symbol"], {})
        price_hive = float(m.get("lastPrice", 0))
        change_24h = float(m.get("priceChangePercent", "0").replace("%", "") or 0)
        value_usd = bal * price_hive * hive_usd
        holdings.append((b["symbol"], bal, value_usd, change_24h))

    holdings.sort(key=lambda x: x[2], reverse=True)
    total = sum(h[2] for h in holdings)
    print(f"{'Token':<12} {'Balance':>12} {'USD':>10} {'24h':>8}")
    print("-" * 44)
    for sym, bal, usd, chg in holdings[:20]:
        print(f"{sym:<12} {bal:>12.3f} ${usd:>8.2f} {chg:>+7.1f}%")
    print(f"\nTotal portfolio: ${total:.2f}")

portfolio("leofinance")
```'''
    ),
    (
        "hive_layer2/event-streaming",
        r'''How can I stream Hive Engine sidechain events in real-time to react to token transfers, market trades, and pool swaps as they happen?''',
        r'''<think>
Hive Engine processes L1 blocks and produces sidechain blocks. There's no native
WebSocket stream, so the approach is to poll the sidechain block API at
/blockchain with getLatestBlockInfo and getBlockInfo. Each sidechain block
contains transactions with logs/events. I should track the last processed block
number and poll for new blocks, parsing transaction logs for relevant events.
The block interval matches Hive L1 (3 seconds). This is an advanced pattern.
</think>

```python
import requests, time, json

HE_API = "https://api.hive-engine.com/rpc/blockchain"

def rpc_call(method, params=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return requests.post(HE_API, json=payload).json()["result"]

def get_latest_block():
    return rpc_call("getLatestBlockInfo")

def get_block(num):
    return rpc_call("getBlockInfo", {"blockNumber": num})

def parse_events(block):
    """Extract notable events from a sidechain block."""
    events = []
    for tx in block.get("transactions", []):
        logs = json.loads(tx.get("logs", "{}"))
        for event in logs.get("events", []):
            data = event.get("data", {})
            etype = f"{event.get('contract')}.{event.get('event')}"
            events.append({"type": etype, "data": data, "sender": tx.get("sender")})
    return events

def stream_events(filter_types=None):
    """Stream sidechain events, optionally filtering by type."""
    last_block = get_latest_block()["blockNumber"]
    print(f"Starting stream from block {last_block}")

    while True:
        latest = get_latest_block()["blockNumber"]
        while last_block < latest:
            last_block += 1
            block = get_block(last_block)
            if not block:
                continue
            for ev in parse_events(block):
                if filter_types is None or ev["type"] in filter_types:
                    print(f"[{last_block}] {ev['type']}: {ev['data']}")
        time.sleep(2)

# Stream token transfers and market trades
stream_events({"tokens.transfer", "market.buy", "market.sell", "marketpools.swapTokens"})
```'''
    ),
    (
        "hive_layer2/token-price-oracle",
        r'''Build a token price oracle for Hive Engine that aggregates prices from multiple sources (order book, diesel pools, recent trades) and publishes a weighted median.''',
        r'''<think>
A price oracle needs multiple price feeds to resist manipulation. On Hive Engine,
price sources include: 1) market metrics (last trade), 2) order book midpoint
(best bid + ask / 2), 3) diesel pool implied price (reserve ratio).
The weighted median is more robust than mean against outliers. The oracle can
publish via custom_json for on-chain consumption. This is expert-level work
combining DeFi and oracle design patterns.
</think>

```python
import requests, json, statistics
from beem import Hive
from beem.transactionbuilder import TransactionBuilder

HE_API = "https://api.hive-engine.com/rpc/contracts"
hive = Hive(keys=["5Jactive_key"])
ACCOUNT = "oracle-bot"

def he_find(contract, table, query, limit=10):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "find",
               "params": {"contract": contract, "table": table,
                           "query": query, "limit": limit}}
    return requests.post(HE_API, json=payload).json()["result"]

def get_prices(symbol: str) -> list[float]:
    prices = []
    # Source 1: last trade from metrics
    metrics = he_find("market", "metrics", {"symbol": symbol})
    if metrics:
        prices.append(float(metrics[0].get("lastPrice", 0)))

    # Source 2: order book midpoint
    buys = he_find("market", "buyBook", {"symbol": symbol})
    sells = he_find("market", "sellBook", {"symbol": symbol})
    if buys and sells:
        best_bid = max(float(b["price"]) for b in buys)
        best_ask = min(float(s["price"]) for s in sells)
        prices.append((best_bid + best_ask) / 2)

    # Source 3: diesel pool implied price
    pools = he_find("marketpools", "pools", {"tokenPair": f"SWAP.HIVE:{symbol}"})
    if pools:
        p = pools[0]
        prices.append(float(p["baseQuantity"]) / float(p["quoteQuantity"]))

    return [p for p in prices if p > 0]

def publish_oracle(symbol: str):
    prices = get_prices(symbol)
    if len(prices) < 2:
        print(f"Insufficient sources for {symbol}: {len(prices)}")
        return
    median_price = statistics.median(prices)
    print(f"{symbol} oracle: {median_price:.6f} HIVE (from {len(prices)} sources)")

    op = ["custom_json", {
        "required_auths": [ACCOUNT], "required_posting_auths": [],
        "id": "hive-engine-oracle",
        "json": json.dumps({"symbol": symbol, "price": str(median_price),
                            "sources": len(prices), "timestamp": "auto"})
    }]
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()

publish_oracle("LEO")
```'''
    ),
    (
        "hive_layer2/order-book-depth",
        r'''Write code to analyze order book depth for a Hive Engine token, calculating support/resistance levels and slippage for large orders.''',
        r'''<think>
Order book depth analysis requires fetching the full buy and sell books from
the market contract. Support levels are clusters of buy orders; resistance levels
are sell order clusters. Slippage calculation walks the book to determine the
average execution price for a given order size vs the current best price.
This is key for algorithmic trading and market making on Hive Engine.
The buy/sell book tables can be queried with sorting by price.
</think>

```python
import requests

HE_API = "https://api.hive-engine.com/rpc/contracts"

def he_find(contract, table, query, limit=200):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "find",
               "params": {"contract": contract, "table": table,
                           "query": query, "limit": limit}}
    return requests.post(HE_API, json=payload).json()["result"]

def analyze_depth(symbol: str, order_size_hive: float = 100):
    buys = he_find("market", "buyBook", {"symbol": symbol})
    sells = he_find("market", "sellBook", {"symbol": symbol})
    buys.sort(key=lambda x: float(x["price"]), reverse=True)
    sells.sort(key=lambda x: float(x["price"]))

    def calc_slippage(orders, size):
        filled, cost = 0.0, 0.0
        for o in orders:
            price = float(o["price"])
            qty = float(o["quantity"])
            take = min(qty * price, size - cost)
            cost += take
            filled += take / price
            if cost >= size:
                break
        avg_price = cost / filled if filled else 0
        best = float(orders[0]["price"]) if orders else 0
        slip = abs(avg_price - best) / best * 100 if best else 0
        return {"filled": filled, "avg_price": avg_price, "slippage_pct": slip}

    buy_depth = sum(float(b["price"]) * float(b["quantity"]) for b in buys)
    sell_depth = sum(float(s["price"]) * float(s["quantity"]) for s in sells)

    print(f"=== {symbol} Order Book ===")
    print(f"Buy depth: {buy_depth:.2f} HIVE ({len(buys)} orders)")
    print(f"Sell depth: {sell_depth:.2f} HIVE ({len(sells)} orders)")
    print(f"Spread: {float(sells[0]['price']) - float(buys[0]['price']):.6f}" if buys and sells else "")

    slip = calc_slippage(sells, order_size_hive)
    print(f"\nBuying {order_size_hive} HIVE worth:")
    print(f"  Avg price: {slip['avg_price']:.6f} | Slippage: {slip['slippage_pct']:.2f}%")

analyze_depth("LEO", order_size_hive=500)
```'''
    ),
    (
        "hive_layer2/liquidity-mining-rewards",
        r'''Create a liquidity mining rewards calculator for Hive Engine diesel pools that shows APR based on pool share and reward distribution.''',
        r'''<think>
Hive Engine diesel pools can have mining rewards distributed via the "marketpools"
contract's reward system. LPs earn a share of daily token emissions proportional
to their pool share. To calculate APR, I need: pool total liquidity, user's LP
token balance, daily reward emission, and token price. The APR formula is
(daily_rewards * 365 * token_price) / (user_liquidity_usd) * 100.
I'll fetch real pool data and compute projected returns. Expert-level DeFi.
</think>

```python
import requests

HE_API = "https://api.hive-engine.com/rpc/contracts"

def he_find(contract, table, query, limit=100):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "find",
               "params": {"contract": contract, "table": table,
                           "query": query, "limit": limit}}
    return requests.post(HE_API, json=payload).json()["result"]

def get_hive_usd():
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": "hive", "vs_currencies": "usd"})
    return r.json()["hive"]["usd"]

def calc_lp_rewards(pair: str, account: str):
    hive_usd = get_hive_usd()

    # Get pool data
    pools = he_find("marketpools", "pools", {"tokenPair": pair})
    if not pools:
        print(f"Pool {pair} not found"); return
    pool = pools[0]
    total_shares = float(pool.get("totalShares", 1))
    base_qty = float(pool["baseQuantity"])
    pool_value_usd = base_qty * 2 * hive_usd  # both sides ~equal in value

    # Get user's LP balance
    lp_symbol = pool.get("lpToken", f"{pair.replace(':', '_')}_LP")
    user_bal = he_find("tokens", "balances",
                       {"account": account, "symbol": lp_symbol})
    user_shares = float(user_bal[0]["balance"]) if user_bal else 0
    share_pct = user_shares / total_shares * 100 if total_shares else 0
    user_value = pool_value_usd * (user_shares / total_shares) if total_shares else 0

    # Get reward config (mining pools linked to LP)
    rewards = he_find("mining", "pools", {"minedToken": pair.split(":")[1]})
    daily_emission = 0
    for r in rewards:
        daily_emission += float(r.get("tokenPerBlock", 0)) * 28800  # ~28800 blocks/day

    metrics = he_find("market", "metrics", {"symbol": pair.split(":")[1]})
    token_price_hive = float(metrics[0]["lastPrice"]) if metrics else 0
    daily_usd = daily_emission * token_price_hive * hive_usd
    user_daily = daily_usd * (share_pct / 100)
    apr = (user_daily * 365 / user_value * 100) if user_value else 0

    print(f"Pool: {pair}")
    print(f"TVL: ${pool_value_usd:,.2f} | Your share: {share_pct:.2f}% (${user_value:,.2f})")
    print(f"Daily rewards: ${user_daily:.2f} | APR: {apr:.1f}%")
    print(f"Monthly est: ${user_daily * 30:.2f} | Yearly est: ${user_daily * 365:.2f}")

calc_lp_rewards("SWAP.HIVE:SPS", "youraccount")
```'''
    ),
]
