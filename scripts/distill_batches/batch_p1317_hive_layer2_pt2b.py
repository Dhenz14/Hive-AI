"""Hive Layer 2 training pairs (part 2b): bridges, NFTs, advanced DeFi."""

PAIRS = [
    (
        "hive_layer2/wrapped-token-bridge",
        r'''How do I build a wrapped token bridge between Hive Engine and an EVM chain?''',
        r'''<think>
A wrapped token bridge needs a custodian that locks tokens on one side and mints
equivalents on the other. On Hive Engine side, tokens are sent to a bridge account
with a memo containing the destination EVM address. A relay service monitors those
deposits, then calls a mint function on the EVM smart contract. For redemptions,
the EVM contract burns tokens and emits an event the relay picks up to issue
Hive Engine tokens back. Security requires multisig or threshold signatures.
</think>

Here is a bridge relay service that watches Hive Engine deposits and triggers EVM mints:

```python
import time
import json
from hiveengine.api import Api as HEApi
from web3 import Web3

BRIDGE_ACCOUNT = "mybridge"
HE_SYMBOL = "MYTOK"
EVM_RPC = "https://polygon-rpc.com"
CONTRACT_ADDR = "0xYourBridgeContract"
RELAY_KEY = "0xRelayPrivateKey"
MINT_ABI = [{"name": "mint", "type": "function",
             "inputs": [{"name": "to", "type": "address"},
                        {"name": "amount", "type": "uint256"}]}]

he = HEApi()
w3 = Web3(Web3.HTTPProvider(EVM_RPC))
contract = w3.eth.contract(address=CONTRACT_ADDR, abi=MINT_ABI)
last_block = he.get_latest_block_info()["blockNumber"]

def process_deposits():
    global last_block
    history = he.get_history(BRIDGE_ACCOUNT, HE_SYMBOL, limit=50)
    for tx in history:
        if tx["to"] != BRIDGE_ACCOUNT or tx["blockNumber"] <= last_block:
            continue
        evm_dest = tx.get("memo", "").strip()
        if not Web3.is_address(evm_dest):
            print(f"Skipping invalid memo: {evm_dest}")
            continue
        amt_wei = int(float(tx["quantity"]) * 10**18)
        mint_tx = contract.functions.mint(evm_dest, amt_wei).build_transaction({
            "from": w3.eth.account.from_key(RELAY_KEY).address,
            "nonce": w3.eth.get_transaction_count(
                w3.eth.account.from_key(RELAY_KEY).address),
            "gas": 100_000,
        })
        signed = w3.eth.account.sign_transaction(mint_tx, RELAY_KEY)
        w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"Minted {tx['quantity']} wrapped tokens to {evm_dest}")
        last_block = tx["blockNumber"]

while True:
    process_deposits()
    time.sleep(6)
```

Key considerations:
- Use a multisig relay to prevent single-key compromise
- Store processed transaction IDs to avoid double-minting on restart
- Add rate limits and max-amount caps as safety rails'''
    ),
    (
        "hive_layer2/defi-yield-aggregator",
        r'''How can I build a yield aggregator that auto-compounds Hive Engine diesel pool rewards?''',
        r'''<think>
Diesel pools on Hive Engine distribute rewards to LP providers. A yield aggregator
would claim pending rewards, swap them back into the pool's token pair, and re-add
liquidity. The flow: check pending rewards via the marketpools contract, claim them,
swap half into each token of the pair, then add liquidity. This must run periodically.
Using sscjs or hiveengine Python lib to broadcast custom_json operations for each step.
</think>

Auto-compounding aggregator for Hive Engine diesel pools:

```python
import json
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
from hiveengine.api import Api as HEApi

hive = Hive(keys=["5Jactive_key"])
ACCOUNT = "myaggregator"
POOL = "SWAP.HIVE:BEE"
he = HEApi()

def get_pending_rewards():
    pools = he.find("marketpools", "liquidityPositions",
                    {"account": ACCOUNT, "tokenPair": POOL})
    return pools[0] if pools else None

def broadcast_he_action(contract, action, payload):
    op = Custom_json(**{
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({"contractName": contract,
                            "contractAction": action,
                            "contractPayload": payload}),
    })
    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(ACCOUNT, "active")
    tb.broadcast()

def compound():
    pos = get_pending_rewards()
    if not pos or float(pos.get("pendingRewards", "0")) < 0.01:
        print("No rewards to compound")
        return
    # Claim pending rewards
    broadcast_he_action("distribution", "claim", {"tokenPair": POOL})
    # Swap half reward into the other token of the pair
    base, quote = POOL.split(":")
    reward_amt = float(pos["pendingRewards"]) / 2
    broadcast_he_action("market", "buy", {
        "symbol": quote, "quantity": f"{reward_amt:.8f}",
        "pair": POOL,
    })
    # Add liquidity with both tokens
    broadcast_he_action("marketpools", "addLiquidity", {
        "tokenPair": POOL,
        "baseQuantity": f"{reward_amt:.8f}",
        "quoteQuantity": f"{reward_amt:.8f}",
    })
    print(f"Compounded {pos['pendingRewards']} rewards into {POOL}")

compound()
```

Run this on a cron (e.g., every 12 hours) to auto-compound LP rewards.'''
    ),
    (
        "hive_layer2/token-swap-router",
        r'''How do I implement a multi-hop token swap router for Hive Engine diesel pools?''',
        r'''<think>
Not all token pairs have direct pools. A swap router finds the best path through
intermediate pools. For example, swapping TOKEN_A to TOKEN_C might go through
TOKEN_A->SWAP.HIVE then SWAP.HIVE->TOKEN_C. The router needs to: fetch all
available pools, build a graph, find shortest/cheapest paths using BFS or
Dijkstra with slippage as edge weight, then execute swaps sequentially.
This is intermediate-to-advanced graph routing plus DeFi execution.
</think>

Multi-hop swap router that finds optimal paths through Hive Engine pools:

```python
from collections import defaultdict, deque
from hiveengine.api import Api as HEApi

he = HEApi()

def build_pool_graph():
    """Build adjacency graph from all diesel pools."""
    pools = he.find("marketpools", "pools", {})
    graph = defaultdict(list)
    for p in pools:
        base, quote = p["tokenPair"].split(":")
        liq = float(p.get("baseQuantity", 0))
        graph[base].append((quote, p["tokenPair"], liq))
        graph[quote].append((base, p["tokenPair"], liq))
    return graph

def find_swap_path(graph, src, dst, max_hops=3):
    """BFS to find shortest path, preferring high-liquidity routes."""
    queue = deque([(src, [src], [])])
    visited = {src}
    best = None
    while queue:
        node, path, pools = queue.popleft()
        if len(path) > max_hops + 1:
            continue
        if node == dst:
            if best is None or len(path) < len(best[0]):
                best = (path, pools)
            continue
        for neighbor, pair, liq in sorted(graph[node], key=lambda x: -x[2]):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor], pools + [pair]))
    return best

def estimate_output(pools_path, amount_in):
    """Estimate output using constant-product formula per hop."""
    amt = amount_in
    for pair in pools_path:
        pool = he.find("marketpools", "pools", {"tokenPair": pair})[0]
        reserve_in = float(pool["baseQuantity"])
        reserve_out = float(pool["quoteQuantity"])
        fee = 1 - float(pool.get("tradeFee", "0.01"))
        amt = (reserve_out * amt * fee) / (reserve_in + amt * fee)
    return amt

# Example: swap DEC -> BEE via SWAP.HIVE
graph = build_pool_graph()
result = find_swap_path(graph, "DEC", "BEE")
if result:
    path, pools = result
    est = estimate_output(pools, 1000.0)
    print(f"Route: {' -> '.join(path)}")
    print(f"Pools: {pools}")
    print(f"1000 DEC -> ~{est:.4f} BEE")
```'''
    ),
    (
        "hive_layer2/market-maker-bot",
        r'''How do I build a basic market maker bot for a Hive Engine token?''',
        r'''<think>
A market maker places buy and sell orders around a mid price to earn the spread.
On Hive Engine, orders are placed via custom_json to the market contract. The bot
needs to: fetch the current order book, calculate a fair mid price, place bids
below and asks above with a configurable spread, and periodically cancel stale
orders. Risk management includes position limits and inventory skew adjustment.
This is an advanced strategy requiring careful balance management.
</think>

Simple spread-based market maker for Hive Engine tokens:

```python
import json
import time
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
from hiveengine.api import Api as HEApi

hive = Hive(keys=["5Jactive_key"])
ACCOUNT = "mmbot"
SYMBOL = "BEE"
SPREAD = 0.02  # 2% total spread
ORDER_SIZE = "50.000"
he = HEApi()

def he_action(action, payload):
    op = Custom_json(**{
        "required_auths": [ACCOUNT], "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({"contractName": "market",
                            "contractAction": action,
                            "contractPayload": payload}),
    })
    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(ACCOUNT, "active")
    tb.broadcast()

def get_mid_price():
    book = he.find("market", "buyBook", {"symbol": SYMBOL}, limit=1)
    best_bid = float(book[0]["price"]) if book else 0
    book = he.find("market", "sellBook", {"symbol": SYMBOL}, limit=1)
    best_ask = float(book[0]["price"]) if book else 0
    if best_bid and best_ask:
        return (best_bid + best_ask) / 2
    return best_bid or best_ask

def cancel_open_orders():
    for side in ["buyBook", "sellBook"]:
        orders = he.find("market", side,
                         {"symbol": SYMBOL, "account": ACCOUNT})
        for o in orders:
            action = "cancel" if side == "buyBook" else "cancel"
            he_action(action, {"type": side.replace("Book", ""),
                               "id": o["_id"]})

def place_orders():
    mid = get_mid_price()
    if not mid:
        print("No price data available")
        return
    bid_price = f"{mid * (1 - SPREAD / 2):.8f}"
    ask_price = f"{mid * (1 + SPREAD / 2):.8f}"
    cancel_open_orders()
    he_action("buy", {"symbol": SYMBOL, "quantity": ORDER_SIZE,
                      "price": bid_price})
    he_action("sell", {"symbol": SYMBOL, "quantity": ORDER_SIZE,
                       "price": ask_price})
    print(f"Placed bid={bid_price} ask={ask_price} mid={mid:.8f}")

while True:
    place_orders()
    time.sleep(60)
```

Enhancements for production: inventory skew (shift quotes when holding too much),
minimum profit thresholds, and circuit breakers for sudden price moves.'''
    ),
    (
        "hive_layer2/nft-collection-analytics",
        r'''How do I pull analytics for an NFT collection on Hive Engine — floor price, volume, holder distribution?''',
        r'''<think>
Hive Engine NFTs use the nft contract. To get collection analytics, query the
nft instances for a given symbol, then aggregate: floor price from the lowest
listed sell order, holder distribution by grouping instances by account, and
volume from recent market history. The nft find endpoint returns instances,
and the market contract has NFT sell books. This is an intermediate data
aggregation task combining multiple API queries.
</think>

NFT collection analytics dashboard using Hive Engine API:

```python
from collections import Counter
from hiveengine.api import Api as HEApi

he = HEApi()
NFT_SYMBOL = "SPTS"  # e.g., Splinterlands card NFTs

def get_holder_distribution(symbol, limit=1000):
    instances = he.find("nft", f"{symbol}instances", {}, limit=limit)
    holders = Counter(inst["account"] for inst in instances)
    return holders

def get_floor_price(symbol):
    sell_book = he.find("nftmarket", "sellBook",
                        {"symbol": symbol, "priceSymbol": "SWAP.HIVE"},
                        limit=500)
    if not sell_book:
        return None
    prices = [float(o["price"]) for o in sell_book]
    return min(prices)

def get_volume_24h(symbol):
    history = he.find("nftmarket", "tradesHistory",
                      {"symbol": symbol}, limit=200)
    # Filter last 24h trades
    import time
    cutoff = time.time() - 86400
    recent = [t for t in history
              if t.get("timestamp", 0) / 1000 > cutoff]
    vol = sum(float(t.get("price", 0)) for t in recent)
    return vol, len(recent)

holders = get_holder_distribution(NFT_SYMBOL)
floor = get_floor_price(NFT_SYMBOL)
vol_24h, trades_24h = get_volume_24h(NFT_SYMBOL)

print(f"=== {NFT_SYMBOL} Collection Analytics ===")
print(f"Unique holders: {len(holders)}")
print(f"Total NFTs tracked: {sum(holders.values())}")
print(f"Floor price: {floor} SWAP.HIVE")
print(f"24h volume: {vol_24h:.3f} SWAP.HIVE ({trades_24h} trades)")
print(f"\nTop 10 holders:")
for acct, count in holders.most_common(10):
    print(f"  {acct}: {count} NFTs")
```'''
    ),
    (
        "hive_layer2/nft-royalty-system",
        r'''How do I implement an NFT royalty system on Hive Engine that pays creators on secondary sales?''',
        r'''<think>
Hive Engine NFTs don't have built-in royalty enforcement at the protocol level,
so royalties must be handled by a monitoring service. The approach: watch the
nftmarket tradesHistory for sales of NFTs from a specific collection, calculate
the royalty percentage, and send payment to the creator automatically. This
requires a relay bot with active key access. The bot checks trade history
periodically, tracks which trades have been processed, and transfers the
royalty cut from a collection escrow account.
</think>

Royalty enforcement bot that monitors secondary NFT sales and pays creators:

```python
import json
import time
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
from hiveengine.api import Api as HEApi

hive = Hive(keys=["5Jactive_key"])
ROYALTY_ACCOUNT = "nft-royalties"
CREATOR = "nft-artist"
COLLECTION = "MYART"
ROYALTY_PCT = 0.05  # 5%
he = HEApi()
processed_trades = set()

def send_he_tokens(to, symbol, qty, memo=""):
    op = Custom_json(**{
        "required_auths": [ROYALTY_ACCOUNT], "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({"contractName": "tokens",
                            "contractAction": "transfer",
                            "contractPayload": {
                                "symbol": symbol, "to": to,
                                "quantity": f"{qty:.8f}", "memo": memo
                            }}),
    })
    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(ROYALTY_ACCOUNT, "active")
    tb.broadcast()

def check_and_pay_royalties():
    trades = he.find("nftmarket", "tradesHistory",
                     {"symbol": COLLECTION}, limit=100)
    for trade in trades:
        tid = trade.get("_id")
        if tid in processed_trades:
            continue
        price = float(trade.get("price", 0))
        price_symbol = trade.get("priceSymbol", "SWAP.HIVE")
        royalty = price * ROYALTY_PCT
        if royalty < 0.001:
            continue
        send_he_tokens(CREATOR, price_symbol, royalty,
                       f"Royalty for {COLLECTION} #{trade.get('nftId')}")
        processed_trades.add(tid)
        print(f"Paid {royalty:.4f} {price_symbol} royalty to {CREATOR}")

while True:
    check_and_pay_royalties()
    time.sleep(30)
```

Important: the royalty account must hold sufficient token balances. Persist
`processed_trades` to disk/DB to survive restarts.'''
    ),
    (
        "hive_layer2/sidechain-tx-verification",
        r'''How do I verify that a Hive Engine transaction was actually included and confirmed on the sidechain?''',
        r'''<think>
Hive Engine transactions are custom_json ops on Hive L1, but their execution
result lives on the sidechain. A tx can be included on L1 but fail on the
sidechain (e.g., insufficient balance). To verify: get the L1 transaction ID,
then query the Hive Engine RPC for the transaction status using the blockchain
endpoint. The response includes logs and errors showing whether the sidechain
actually executed the action. This is critical for any automated system.
</think>

Verify Hive Engine sidechain execution after broadcasting a custom_json:

```python
import time
import requests
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json

HE_API = "https://api.hive-engine.com/rpc"
hive = Hive(keys=["5Jactive_key"])

def broadcast_he_op(account, contract, action, payload):
    """Broadcast and return the L1 transaction ID."""
    op = Custom_json(**{
        "required_auths": [account], "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({"contractName": contract,
                            "contractAction": action,
                            "contractPayload": payload}),
    })
    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(account, "active")
    result = tb.broadcast()
    return result["id"]

def verify_sidechain_tx(trx_id, retries=10, delay=3):
    """Poll sidechain until tx is confirmed or failed."""
    for attempt in range(retries):
        resp = requests.post(HE_API, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getTransactionInfo",
            "params": {"txid": trx_id}
        })
        data = resp.json().get("result")
        if data is None:
            time.sleep(delay)
            continue
        logs = json.loads(data.get("logs", "{}"))
        errors = logs.get("errors", [])
        if errors:
            return {"success": False, "errors": errors, "block": data["blockNumber"]}
        return {"success": True, "block": data["blockNumber"], "logs": logs}
    return {"success": False, "errors": ["Timeout: tx not found after retries"]}

# Example: transfer tokens and verify
trx_id = broadcast_he_op("myaccount", "tokens", "transfer", {
    "symbol": "BEE", "to": "recipient", "quantity": "10.000",
    "memo": "test transfer"
})
print(f"L1 tx: {trx_id}")
result = verify_sidechain_tx(trx_id)
print(f"Sidechain result: {result}")
```

Always verify sidechain execution — L1 inclusion does NOT guarantee L2 success.'''
    ),
    (
        "hive_layer2/smart-contract-testing",
        r'''How do I write tests for a Hive Engine smart contract before deploying?''',
        r'''<think>
Hive Engine smart contracts are JavaScript-based and run in a sandboxed VM.
Testing locally requires simulating the contract environment. The approach is
to mock the HE API/database layer, load the contract code, and call its actions
with test payloads. For integration testing, use the Hive Engine testnet. The
contract receives an api object with db access methods. We can mock that to
verify state transitions without deploying. This is expert-level work since
the contract runtime is not well documented publicly.
</think>

Testing framework for Hive Engine smart contracts using mocked runtime:

```python
import json
import subprocess
import requests

# --- Unit testing with mocked JS runtime ---
MOCK_TEST_JS = \"\"\"
// mock_test.js - Run with: node mock_test.js
const contract = require('./mycontract.js');

// Mock the Hive Engine API object
const mockDb = {};
const api = {
  db: {
    findOne: (table, query) => mockDb[table]?.find(r =>
      Object.entries(query).every(([k,v]) => r[k] === v)) || null,
    find: (table, query) => mockDb[table]?.filter(r =>
      Object.entries(query).every(([k,v]) => r[k] === v)) || [],
    insert: (table, record) => {
      if (!mockDb[table]) mockDb[table] = [];
      mockDb[table].push(record);
    },
    update: (table, query, record) => {
      const idx = mockDb[table]?.findIndex(r =>
        Object.entries(query).every(([k,v]) => r[k] === v));
      if (idx >= 0) mockDb[table][idx] = {...mockDb[table][idx], ...record};
    },
  },
  sender: 'testuser',
  assert: (cond, msg) => { if (!cond) throw new Error(msg); },
};

// Test: create action
contract.actions.create(api, {symbol: 'TEST', maxSupply: '1000'});
const token = api.db.findOne('tokens', {symbol: 'TEST'});
console.assert(token !== null, 'Token should exist after create');
console.assert(token.maxSupply === '1000', 'Max supply should match');

// Test: transfer with insufficient balance should fail
try {
  contract.actions.transfer(api, {to: 'bob', symbol: 'TEST', quantity: '999'});
  console.assert(false, 'Should have thrown');
} catch (e) {
  console.log('Correctly rejected insufficient balance:', e.message);
}
console.log('All tests passed!');
\"\"\"

def run_contract_tests():
    """Write and execute the mock test."""
    with open("/tmp/mock_test.js", "w") as f:
        f.write(MOCK_TEST_JS)
    result = subprocess.run(["node", "/tmp/mock_test.js"],
                            capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"FAILED: {result.stderr}")
    return result.returncode == 0

# --- Integration test on testnet ---
HE_TESTNET = "https://testapi.hive-engine.com/rpc"

def deploy_to_testnet(contract_code, contract_name):
    """Deploy contract to HE testnet for integration testing."""
    from beem import Hive
    hive = Hive(node=["https://testnet.openhive.network"],
                keys=["5Jtestnet_active_key"])
    # Contract deployment is a special custom_json
    payload = {"name": contract_name, "code": contract_code}
    # ... broadcast via ssc-testnet1 sidechain ID
    print(f"Deployed {contract_name} to testnet")

run_contract_tests()
```'''
    ),
    (
        "hive_layer2/token-launch-checklist",
        r'''Can you automate a token launch checklist for Hive Engine — create token, set up pool, airdrop to holders?''',
        r'''<think>
Launching a token on Hive Engine involves several sequential steps: create the
token via the tokens contract, issue initial supply, create a diesel pool with
SWAP.HIVE pairing, seed initial liquidity, and optionally airdrop to existing
holders of another token. Each step is a custom_json broadcast. Automating this
as a pipeline ensures nothing is missed. The BEE fee for token creation must
be in the account. This is intermediate-level orchestration.
</think>

Automated token launch pipeline for Hive Engine:

```python
import json
import time
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
from hiveengine.api import Api as HEApi

hive = Hive(keys=["5Jactive_key"])
ACCOUNT = "tokenlaunch"
he = HEApi()

def he_broadcast(contract, action, payload):
    op = Custom_json(**{
        "required_auths": [ACCOUNT], "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({"contractName": contract,
                            "contractAction": action,
                            "contractPayload": payload}),
    })
    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(ACCOUNT, "active")
    tb.broadcast()
    time.sleep(4)  # wait for sidechain confirmation

def launch_token(symbol, name, max_supply, initial_liq_hive, initial_liq_token):
    steps = []
    # Step 1: Create token (costs 100 BEE)
    he_broadcast("tokens", "create", {
        "symbol": symbol, "name": name,
        "precision": 8, "maxSupply": max_supply,
    })
    steps.append(f"Created {symbol}")

    # Step 2: Issue initial supply to self
    he_broadcast("tokens", "issue", {
        "symbol": symbol, "to": ACCOUNT,
        "quantity": initial_liq_token,
    })
    steps.append(f"Issued {initial_liq_token} {symbol}")

    # Step 3: Create diesel pool (costs 1000 BEE)
    pair = f"SWAP.HIVE:{symbol}"
    he_broadcast("marketpools", "createPool", {"tokenPair": pair})
    steps.append(f"Created pool {pair}")

    # Step 4: Add initial liquidity
    he_broadcast("marketpools", "addLiquidity", {
        "tokenPair": pair,
        "baseQuantity": initial_liq_hive,
        "quoteQuantity": initial_liq_token,
    })
    steps.append(f"Seeded liquidity")

    print("Launch complete:")
    for s in steps:
        print(f"  [OK] {s}")

def airdrop_to_holders(source_symbol, new_symbol, ratio=1.0):
    """Airdrop new_symbol to holders of source_symbol at given ratio."""
    holders = he.find("tokens", "balances",
                      {"symbol": source_symbol}, limit=1000)
    for h in holders:
        if h["account"].startswith("null"):
            continue
        qty = f"{float(h['balance']) * ratio:.8f}"
        he_broadcast("tokens", "transfer", {
            "symbol": new_symbol, "to": h["account"],
            "quantity": qty, "memo": f"Airdrop for holding {source_symbol}!"
        })
    print(f"Airdropped to {len(holders)} holders")

launch_token("MYNEW", "My New Token", "1000000", "100.00000000", "50000.00000000")
```'''
    ),
    (
        "hive_layer2/community-token-migration",
        r'''How do I migrate a community token from one Hive Engine symbol to another with a snapshot and swap mechanism?''',
        r'''<think>
Token migration requires: snapshot all current holders and balances, create the
new token, then offer a swap mechanism where users send old tokens to a burn
account and receive new tokens. The migration bot watches for incoming old tokens,
burns them (sends to null), and issues new tokens to the sender. A deadline
encourages timely migration. The snapshot ensures we can verify the total
supply matches. This is advanced due to the coordination and verification needed.
</think>

Token migration system with snapshot, swap bot, and verification:

```python
import json
import time
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
from hiveengine.api import Api as HEApi

hive = Hive(keys=["5Jactive_key"])
MIGRATION_ACCOUNT = "token-migrator"
OLD_SYMBOL = "OLDTOK"
NEW_SYMBOL = "NEWTOK"
SWAP_RATIO = 1.0  # 1:1
he = HEApi()

def he_action(contract, action, payload):
    op = Custom_json(**{
        "required_auths": [MIGRATION_ACCOUNT], "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({"contractName": contract,
                            "contractAction": action,
                            "contractPayload": payload}),
    })
    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(MIGRATION_ACCOUNT, "active")
    tb.broadcast()

def take_snapshot():
    """Snapshot all holders of the old token."""
    holders = he.find("tokens", "balances",
                      {"symbol": OLD_SYMBOL}, limit=1000)
    snapshot = {h["account"]: h["balance"] for h in holders
                if float(h["balance"]) > 0}
    with open("migration_snapshot.json", "w") as f:
        json.dump(snapshot, f, indent=2)
    total = sum(float(v) for v in snapshot.values())
    print(f"Snapshot: {len(snapshot)} holders, {total:.3f} total supply")
    return snapshot

def run_swap_bot():
    """Watch for old token deposits and issue new tokens."""
    processed = set()
    while True:
        history = he.find("tokens", "transferHistory",
                          {"symbol": OLD_SYMBOL, "to": MIGRATION_ACCOUNT},
                          limit=50)
        for tx in history:
            tid = tx.get("_id")
            if tid in processed:
                continue
            sender = tx["from"]
            qty = tx["quantity"]
            new_qty = f"{float(qty) * SWAP_RATIO:.8f}"
            # Burn old tokens
            he_action("tokens", "transfer", {
                "symbol": OLD_SYMBOL, "to": "null",
                "quantity": qty, "memo": "migration burn"
            })
            # Send new tokens
            he_action("tokens", "transfer", {
                "symbol": NEW_SYMBOL, "to": sender,
                "quantity": new_qty, "memo": f"Migration: {OLD_SYMBOL} -> {NEW_SYMBOL}"
            })
            processed.add(tid)
            print(f"Swapped {qty} {OLD_SYMBOL} -> {new_qty} {NEW_SYMBOL} for {sender}")
        time.sleep(6)

# Step 1: Snapshot
snapshot = take_snapshot()
# Step 2: Create new token and issue supply to migration account (done separately)
# Step 3: Run swap bot
run_swap_bot()
```'''
    ),
    (
        "hive_layer2/performance-monitoring",
        r'''How do I build a monitoring dashboard for Hive Engine sidechain performance — block times, pending transactions, API latency?''',
        r'''<think>
Monitoring Hive Engine health involves tracking: sidechain block production rate
and delays, API response latency, pending transaction queue depth, and comparing
L1 head block vs L2 processed block to detect sync lag. We can poll multiple HE
API nodes and the blockchain info endpoint periodically, log metrics, and alert
on anomalies. This is an intermediate ops/devops task combining API polling
with time-series analysis.
</think>

Hive Engine sidechain performance monitor:

```python
import time
import json
import requests
from datetime import datetime

HE_NODES = [
    "https://api.hive-engine.com/rpc",
    "https://herpc.dtools.dev/rpc",
    "https://engine.rishipanthee.com/rpc",
]
POLL_INTERVAL = 30  # seconds
metrics_log = []

def query_node(url, method, params=None):
    start = time.time()
    try:
        resp = requests.post(url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": method, "params": params or {}
        }, timeout=10)
        latency = time.time() - start
        return resp.json().get("result"), latency
    except Exception as e:
        return None, time.time() - start

def check_block_production(url):
    info, latency = query_node(url, "getStatus")
    if not info:
        return None
    return {
        "node": url.split("//")[1].split("/")[0],
        "he_block": info.get("lastBlockNumber"),
        "hive_block": info.get("lastParsedHiveBlockNumber"),
        "latency_ms": round(latency * 1000, 1),
        "version": info.get("SSCnodeVersion", "unknown"),
    }

def detect_sync_lag(statuses):
    blocks = [s["he_block"] for s in statuses if s]
    if len(blocks) < 2:
        return 0
    return max(blocks) - min(blocks)

def monitor_loop():
    prev_block = None
    while True:
        ts = datetime.utcnow().isoformat()
        statuses = [check_block_production(node) for node in HE_NODES]
        active = [s for s in statuses if s is not None]

        if active:
            best = max(active, key=lambda s: s["he_block"])
            lag = detect_sync_lag(active)
            block_delta = (best["he_block"] - prev_block) if prev_block else 0
            prev_block = best["he_block"]

            print(f"[{ts}] HE Block: {best['he_block']} | "
                  f"Hive Block: {best['hive_block']} | "
                  f"Nodes up: {len(active)}/{len(HE_NODES)} | "
                  f"Sync lag: {lag} blocks | "
                  f"Best latency: {min(s['latency_ms'] for s in active)}ms")

            if lag > 5:
                print(f"  WARNING: Node sync lag is {lag} blocks!")
            if any(s["latency_ms"] > 5000 for s in active):
                print(f"  WARNING: High latency detected!")
        else:
            print(f"[{ts}] ALL NODES DOWN!")

        time.sleep(POLL_INTERVAL)

monitor_loop()
```'''
    ),
    (
        "hive_layer2/splinterlands-guild-management",
        r'''How do I build a Splinterlands guild management tool that tracks member contributions and automates building upgrades?''',
        r'''<think>
Splinterlands guild data is accessible via their API. Guild management involves
tracking member DEC contributions, brawl participation, and building levels.
The tool can query the Splinterlands API for guild info, member stats, and
building status. Automating upgrades requires broadcasting custom_json ops
for guild building contributions when thresholds are met. This combines
Splinterlands-specific API knowledge with Hive L1 broadcasting.
</think>

Guild management tool with contribution tracking and upgrade automation:

```python
import requests
import json
from datetime import datetime
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json

SL_API = "https://api2.splinterlands.com"
hive = Hive(keys=["5Jactive_key"])
GUILD_ID = "your_guild_id"
GUILD_LEADER = "guildleader"

def get_guild_info():
    resp = requests.get(f"{SL_API}/guilds/find", params={"id": GUILD_ID})
    return resp.json()

def get_guild_members():
    resp = requests.get(f"{SL_API}/guilds/members",
                        params={"guild_id": GUILD_ID})
    return resp.json()

def get_member_brawl_stats(members):
    """Summarize each member's contribution and activity."""
    stats = []
    for m in members:
        stats.append({
            "player": m["player"],
            "contribution": int(m.get("contribution", 0)),
            "lodge_contribution": int(m.get("lodge_contribution", 0)),
            "battles": m.get("guild_battles", 0),
            "joined": m.get("join_date", ""),
        })
    return sorted(stats, key=lambda x: -x["contribution"])

def check_upgrade_ready(guild_info, building):
    """Check if a building has enough contributions for next level."""
    buildings = guild_info.get("buildings", {})
    b = buildings.get(building, {})
    current = b.get("level", 0)
    contributed = b.get("contributed", 0)
    required = b.get("required", float("inf"))
    return contributed >= required, current, contributed, required

def trigger_upgrade(building):
    """Broadcast guild building upgrade via custom_json."""
    op = Custom_json(**{
        "required_auths": [GUILD_LEADER], "required_posting_auths": [],
        "id": "sm_guild_upgrade",
        "json": json.dumps({"building": building, "guild_id": GUILD_ID}),
    })
    tb = TransactionBuilder(blockchain_instance=hive)
    tb.appendOps(op)
    tb.appendSigner(GUILD_LEADER, "active")
    tb.broadcast()
    print(f"Upgrade triggered for {building}!")

# --- Run report ---
guild = get_guild_info()
members = get_guild_members()
stats = get_member_brawl_stats(members)

print(f"=== Guild: {guild['name']} (Level {guild.get('level', '?')}) ===")
print(f"Members: {len(members)}/{guild.get('max_members', '?')}\n")

print("Member Contributions:")
for s in stats:
    print(f"  {s['player']:20s}  DEC: {s['contribution']:>10,}  "
          f"Lodge: {s['lodge_contribution']:>8,}  Battles: {s['battles']}")

# Check buildings for auto-upgrade
for building in ["guild_hall", "quest_lodge", "arena", "barracks"]:
    ready, lvl, contrib, req = check_upgrade_ready(guild, building)
    status = "READY" if ready else f"{contrib}/{req}"
    print(f"\n{building}: Level {lvl} [{status}]")
    if ready:
        trigger_upgrade(building)
```

Low-contribution members can be flagged for review by setting a minimum
threshold (e.g., require 1000 DEC/month contribution).'''
    ),
]
