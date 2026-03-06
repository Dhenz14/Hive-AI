"""
Hive blockchain DeFi training pairs: liquidity pools, swap operations,
yield farming, HBD savings strategies, tribaldex integration.
"""

PAIRS = [
    (
        "hive-defi-liquidity-pools",
        r'''How do I provide liquidity to a Hive Engine token pool on Tribaldex, and how do liquidity pool mechanics work on Hive's sidechain?''',
        r'''<think>
Hive Engine liquidity pools -- this could be similar to Uniswap on Ethereum, but wait, there are important differences since Hive Engine is a sidechain with its own smart contract layer rather than an EVM chain. The operations go through custom_json on Hive layer-1 using the "ssc-mainnet-hive" id, and the sidechain processes them via the marketpools contract.

I initially assumed you would need the posting key for this, but actually adding liquidity modifies token balances, so it requires the active key and goes through required_auths, not required_posting_auths. Getting this wrong would cause the transaction to fail silently on the sidechain.

Hmm, how do LP tokens work here? I considered that they might be issued as separate tradeable tokens like on Uniswap, but actually Hive Engine tracks LP positions in a liquidityPositions table rather than issuing transferable LP tokens. Therefore you cannot trade your LP position directly -- you have to remove liquidity to exit. The user also needs to understand that depositing unbalanced amounts does not revert; instead the sidechain partially fills and refunds the excess, which can be confusing if you do not match the current pool ratio.
</think>

Hive Engine liquidity pools operate through the **marketpools** contract on the sidechain. Tribaldex is the primary DEX interface. When you add liquidity, you deposit a pair of tokens (e.g., SWAP.HIVE:BEE) and receive LP tokens representing your share of the pool. Fees from swaps (typically 0.25%) are distributed proportionally to LP holders.

Here is a Python example using beem to add liquidity to a Hive Engine pool:

```python
from beem import Hive
from beem.account import Account
import json

hive = Hive(keys=["5KactiveKeyHere"], node=["https://api.hive.blog"])

def add_liquidity(account, token_pair, base_quantity, quote_quantity):
    """
    Add liquidity to a Hive Engine pool.
    token_pair: e.g. "SWAP.HIVE:BEE"
    base_quantity and quote_quantity must match pool ratio or you get
    partial fills and refunds.
    """
    payload = {
        "contractName": "marketpools",
        "contractAction": "addLiquidity",
        "contractPayload": {
            "tokenPair": token_pair,
            "baseQuantity": str(base_quantity),
            "quoteQuantity": str(quote_quantity),
        }
    }
    hive.custom_json(
        "ssc-mainnet-hive",
        json.dumps(payload),
        required_auths=[account],
        required_posting_auths=[]
    )
    print(f"Added liquidity: {base_quantity} base + {quote_quantity} quote to {token_pair}")

def get_pool_info(token_pair):
    """Query current pool state from Hive Engine RPC."""
    import requests
    rpc = "https://engine.rishipanthee.com/contracts"
    query = {
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {
            "contract": "marketpools",
            "table": "pools",
            "query": {"tokenPair": token_pair},
            "limit": 1
        }
    }
    resp = requests.post(rpc, json=query)
    pools = resp.json().get("result", [])
    if pools:
        pool = pools[0]
        print(f"Pool: {pool['tokenPair']}")
        print(f"  Base: {pool['baseQuantity']} | Quote: {pool['quoteQuantity']}")
        print(f"  Total shares: {pool['totalShares']}")
        return pool
    return None

def remove_liquidity(account, token_pair, shares_pct=100):
    """Remove liquidity - specify percentage of your LP shares to withdraw."""
    # First query your LP position
    import requests
    rpc = "https://engine.rishipanthee.com/contracts"
    pos_query = {
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {
            "contract": "marketpools",
            "table": "liquidityPositions",
            "query": {"tokenPair": token_pair, "account": account},
            "limit": 1
        }
    }
    resp = requests.post(rpc, json=pos_query)
    positions = resp.json().get("result", [])
    if not positions:
        print("No liquidity position found")
        return
    my_shares = float(positions[0]["shares"])
    withdraw_shares = my_shares * (shares_pct / 100.0)
    payload = {
        "contractName": "marketpools",
        "contractAction": "removeLiquidity",
        "contractPayload": {
            "tokenPair": token_pair,
            "sharesOut": f"{withdraw_shares:.8f}",
        }
    }
    hive.custom_json(
        "ssc-mainnet-hive",
        json.dumps(payload),
        required_auths=[account],
        required_posting_auths=[]
    )
    print(f"Removed {shares_pct}% liquidity from {token_pair}")

# Usage
pool = get_pool_info("SWAP.HIVE:BEE")
if pool:
    base = float(pool["baseQuantity"])
    quote = float(pool["quoteQuantity"])
    ratio = quote / base
    my_base = 10.0
    my_quote = round(my_base * ratio, 8)
    add_liquidity("myaccount", "SWAP.HIVE:BEE", my_base, my_quote)
```

Key points: always match the current pool ratio when adding liquidity to avoid slippage refunds, LP tokens are tracked on-chain via the liquidityPositions table, and impermanent loss applies just like on Ethereum AMMs. Pool fees accumulate automatically in your LP position value.'''
    ),
    (
        "hive-defi-swap-operations",
        r'''Show me how to perform token swaps on Hive Engine using code, including calculating expected output with slippage protection.''',
        r'''Token swaps on Hive Engine use the **marketpools** contract with the `swapTokens` action. The pools use a constant-product (x*y=k) AMM formula. You must calculate expected output off-chain and set a minimum to protect against slippage.

Here is a complete JavaScript example using dhive and axios:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const axios = require("axios");

const client = new Client(["https://api.hive.blog", "https://api.deathwing.me"]);
const ENGINE_RPC = "https://engine.rishipanthee.com/contracts";

async function getPool(tokenPair) {
    const resp = await axios.post(ENGINE_RPC, {
        jsonrpc: "2.0", id: 1, method: "find",
        params: {
            contract: "marketpools", table: "pools",
            query: { tokenPair }, limit: 1
        }
    });
    return resp.data.result[0] || null;
}

function calculateSwapOutput(pool, tokenSymbol, amountIn) {
    // Constant product AMM: (x + dx) * (y - dy) = x * y
    // Fee is 0.25% on Hive Engine pools
    const fee = 0.0025;
    const amountAfterFee = amountIn * (1 - fee);
    const baseQty = parseFloat(pool.baseQuantity);
    const quoteQty = parseFloat(pool.quoteQuantity);
    const pair = pool.tokenPair.split(":");
    let reserveIn, reserveOut;
    if (tokenSymbol === pair[0]) {
        reserveIn = baseQty;
        reserveOut = quoteQty;
    } else {
        reserveIn = quoteQty;
        reserveOut = baseQty;
    }
    const amountOut = (reserveOut * amountAfterFee) / (reserveIn + amountAfterFee);
    const priceImpact = amountAfterFee / (reserveIn + amountAfterFee);
    return { amountOut, priceImpact, effectivePrice: amountIn / amountOut };
}

async function swapTokens(account, activeKey, tokenPair, tokenSymbol, amount, slippagePct = 1.0) {
    const pool = await getPool(tokenPair);
    if (!pool) throw new Error("Pool not found: " + tokenPair);
    const calc = calculateSwapOutput(pool, tokenSymbol, amount);
    const minAmountOut = calc.amountOut * (1 - slippagePct / 100);
    console.log(`Swap ${amount} ${tokenSymbol}`);
    console.log(`  Expected output: ${calc.amountOut.toFixed(8)}`);
    console.log(`  Min output (${slippagePct}% slippage): ${minAmountOut.toFixed(8)}`);
    console.log(`  Price impact: ${(calc.priceImpact * 100).toFixed(4)}%`);
    if (calc.priceImpact > 0.05) {
        console.warn("WARNING: Price impact exceeds 5%, consider smaller trade");
    }
    const payload = JSON.stringify({
        contractName: "marketpools",
        contractAction: "swapTokens",
        contractPayload: {
            tokenPair: tokenPair,
            tokenSymbol: tokenSymbol,
            tokenAmount: amount.toFixed(8),
            tradeType: "exactInput",
            minAmountOut: minAmountOut.toFixed(8)
        }
    });
    const key = PrivateKey.fromString(activeKey);
    const result = await client.broadcast.json(
        { required_auths: [account], required_posting_auths: [], id: "ssc-mainnet-hive", json: payload },
        key
    );
    console.log("Broadcast tx:", result.id);
    return result;
}

// Multi-hop swap through intermediate pool
async function multiHopSwap(account, activeKey, path, amountIn, slippagePct = 2.0) {
    // path example: [{pair: "SWAP.HIVE:BEE", symbol: "SWAP.HIVE"},
    //                {pair: "BEE:SPS", symbol: "BEE"}]
    let currentAmount = amountIn;
    for (const hop of path) {
        const pool = await getPool(hop.pair);
        const calc = calculateSwapOutput(pool, hop.symbol, currentAmount);
        currentAmount = calc.amountOut;
        console.log(`Hop ${hop.pair}: ${calc.amountOut.toFixed(8)} out`);
    }
    // Execute first hop (second hop must wait for sidechain confirmation)
    await swapTokens(account, activeKey, path[0].pair, path[0].symbol, amountIn, slippagePct);
    console.log("First hop executed. Execute second hop after sidechain confirms (~3-6 seconds).");
}

// Example usage
(async () => {
    await swapTokens("myaccount", "5KactiveKey", "SWAP.HIVE:BEE", "SWAP.HIVE", 5.0, 1.0);
})();
```

The `minAmountOut` parameter is your slippage guard -- if the pool moves between calculation and execution, the transaction reverts if output falls below your minimum. For large trades, split into multiple smaller swaps to reduce price impact. Hive Engine sidechain blocks are roughly 3 seconds, so pool state can change between your query and broadcast.'''
    ),
    (
        "hive-defi-yield-farming",
        r'''How can I build a yield farming strategy on Hive that combines multiple income streams like curation, HBD savings, and diesel pool rewards?''',
        r'''<think>
A yield farming strategy on Hive... my first thought was to focus on diesel pool LP rewards since those tend to have the highest advertised APRs, but wait -- those high APRs come with impermanent loss risk and sidechain trust assumptions. Actually, a proper strategy needs to balance multiple income streams with different risk profiles.

Let me map out what is available. HBD savings pays 20% APR set by witness consensus -- this is protocol-level, so the risk is very low (essentially Hive platform risk only). Curation rewards come from the inflation-funded reward pool and typically yield 8-12% APR on staked HP. Diesel pools offer variable yields but carry impermanent loss. Hmm, I considered treating these as independent choices, but since the user asked about combining them, the real value is in building a manager that tracks all three simultaneously and shows the aggregate yield.

One thing I almost overlooked: HBD savings interest accrues continuously but is only paid out when you initiate a withdrawal, and withdrawals have a 3-day lock. Therefore compounding is not free -- you lose 3 days of earning each cycle. The strategy manager should account for this when projecting effective yields.
</think>

Hive offers multiple concurrent yield sources that can be combined into a diversified farming strategy. The major streams are: HBD savings (currently 20% APR set by witness consensus), curation rewards (variable, typically 8-12% APR on staked HP), and Hive Engine diesel pool LP rewards. Here is a Python strategy manager:

```python
from beem import Hive
from beem.account import Account
from beem.amount import Amount
import requests
import json
from datetime import datetime, timedelta

class HiveYieldManager:
    def __init__(self, account_name, keys, nodes=None):
        self.nodes = nodes or ["https://api.hive.blog", "https://api.deathwing.me"]
        self.hive = Hive(keys=keys, node=self.nodes)
        self.account_name = account_name
        self.account = Account(account_name, blockchain_instance=self.hive)
        self.engine_rpc = "https://engine.rishipanthee.com/contracts"

    def get_hbd_savings_yield(self):
        """Calculate current HBD savings position and projected yield."""
        savings_hbd = float(self.account["savings_hbd_balance"].amount)
        # HBD interest rate is set by witnesses, currently 20%
        props = self.hive.get_dynamic_global_properties()
        hbd_interest_rate = int(props.get("hbd_interest_rate", 2000)) / 100
        annual_yield = savings_hbd * (hbd_interest_rate / 100)
        return {
            "source": "HBD Savings",
            "principal": savings_hbd,
            "apr": hbd_interest_rate,
            "projected_annual": annual_yield,
            "compound_frequency": "monthly",
            "risk": "low - protocol guaranteed"
        }

    def get_curation_yield(self, days_lookback=30):
        """Estimate curation APR from recent reward history."""
        hp_staked = float(self.account.get_steem_power())
        history = self.account.history_reverse(
            only_ops=["curation_reward"],
            batch_size=500
        )
        cutoff = datetime.utcnow() - timedelta(days=days_lookback)
        total_vests = 0
        count = 0
        for op in history:
            ts = datetime.strptime(op["timestamp"], "%Y-%m-%dT%H:%M:%S")
            if ts < cutoff:
                break
            vests = float(op["reward"].split()[0])
            total_vests += vests
            count += 1
        # Convert VESTS to HP
        props = self.hive.get_dynamic_global_properties()
        total_vesting = float(props["total_vesting_fund_hive"].amount)
        total_vests_supply = float(props["total_vesting_shares"].amount)
        hp_earned = total_vests * (total_vesting / total_vests_supply)
        annualized = hp_earned * (365 / days_lookback)
        apr = (annualized / hp_staked * 100) if hp_staked > 0 else 0
        return {
            "source": "Curation Rewards",
            "principal_hp": hp_staked,
            "earned_hp_period": hp_earned,
            "apr": round(apr, 2),
            "projected_annual_hp": round(annualized, 3),
            "votes_cast": count,
            "risk": "low - protocol inflation"
        }

    def get_diesel_pool_positions(self):
        """Query all LP positions on Hive Engine diesel pools."""
        query = {
            "jsonrpc": "2.0", "id": 1, "method": "find",
            "params": {
                "contract": "marketpools",
                "table": "liquidityPositions",
                "query": {"account": self.account_name},
                "limit": 100
            }
        }
        resp = requests.post(self.engine_rpc, json=query)
        positions = resp.json().get("result", [])
        results = []
        for pos in positions:
            pool_query = {
                "jsonrpc": "2.0", "id": 1, "method": "find",
                "params": {
                    "contract": "marketpools", "table": "pools",
                    "query": {"tokenPair": pos["tokenPair"]}, "limit": 1
                }
            }
            pool_resp = requests.post(self.engine_rpc, json=pool_query)
            pool = pool_resp.json().get("result", [None])[0]
            if pool:
                share_pct = float(pos["shares"]) / float(pool["totalShares"]) * 100
                results.append({
                    "source": f"Diesel Pool: {pos['tokenPair']}",
                    "shares": pos["shares"],
                    "pool_share_pct": round(share_pct, 4),
                    "risk": "medium - impermanent loss + sidechain risk"
                })
        return results

    def deposit_hbd_savings(self, amount):
        """Move HBD to savings for interest."""
        self.hive.transfer_to_savings(amount, "HBD", "", self.account_name)
        print(f"Deposited {amount} HBD to savings")

    def compound_hbd_interest(self):
        """Withdraw HBD interest and redeposit for compounding."""
        # HBD interest is paid on withdrawal from savings
        savings = float(self.account["savings_hbd_balance"].amount)
        if savings > 0:
            # Withdraw triggers interest calc, then redeposit after 3-day wait
            self.hive.transfer_from_savings(0.001, "HBD", "", self.account_name)
            print("Initiated HBD savings withdrawal to trigger interest payment")

    def print_yield_summary(self):
        """Print complete yield farming dashboard."""
        print("=" * 60)
        print(f"HIVE YIELD FARMING DASHBOARD - {self.account_name}")
        print(f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        print("=" * 60)
        hbd = self.get_hbd_savings_yield()
        print(f"\n{hbd['source']}:")
        print(f"  Principal: {hbd['principal']:.3f} HBD")
        print(f"  APR: {hbd['apr']}%")
        print(f"  Projected annual: {hbd['projected_annual']:.3f} HBD")
        curation = self.get_curation_yield()
        print(f"\n{curation['source']}:")
        print(f"  Staked HP: {curation['principal_hp']:.3f}")
        print(f"  APR: {curation['apr']}%")
        print(f"  Projected annual: {curation['projected_annual_hp']:.3f} HP")
        pools = self.get_diesel_pool_positions()
        for p in pools:
            print(f"\n{p['source']}:")
            print(f"  Shares: {p['shares']}")
            print(f"  Pool share: {p['pool_share_pct']}%")
        print("\n" + "=" * 60)

# Usage
ym = HiveYieldManager("myaccount", ["5Kposting", "5Kactive"])
ym.print_yield_summary()
```

This combines the three major yield sources on Hive. HBD savings is the safest at 20% APR with no impermanent loss. Curation requires active voting or delegation to a curation service. Diesel pools offer higher variable yields but carry impermanent loss risk. A balanced strategy might allocate 40% to HBD savings, 40% to HP curation, and 20% to high-volume diesel pools like SWAP.HIVE:SPS.'''
    ),
    (
        "hive-defi-hbd-strategies",
        r'''What are the best strategies for maximizing HBD savings yield on Hive, including compounding and the 3-day withdrawal window?''',
        r'''HBD savings on Hive pay interest set by witness consensus (currently 20% APR). Interest accrues continuously but is only calculated and paid when you initiate a withdrawal. Withdrawals have a mandatory 3-day waiting period. Here are strategies to maximize yield:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta
import math

class HBDSavingsOptimizer:
    def __init__(self, account_name, active_key, nodes=None):
        self.nodes = nodes or ["https://api.hive.blog"]
        self.hive = Hive(keys=[active_key], node=self.nodes)
        self.account_name = account_name

    def get_current_hbd_rate(self):
        """Get current HBD interest rate from chain parameters."""
        props = self.hive.get_dynamic_global_properties()
        # Rate is in basis points, e.g. 2000 = 20%
        return int(props.get("hbd_interest_rate", 2000)) / 10000

    def calculate_compound_advantage(self, principal, rate, years=1):
        """Compare simple vs compound interest on HBD savings."""
        simple = principal * rate * years
        # Monthly compounding (realistic given 3-day withdrawal delay)
        monthly = principal * ((1 + rate / 12) ** (12 * years)) - principal
        # Weekly compounding (aggressive, requires frequent operations)
        weekly = principal * ((1 + rate / 52) ** (52 * years)) - principal
        return {
            "simple_interest": round(simple, 3),
            "monthly_compound": round(monthly, 3),
            "weekly_compound": round(weekly, 3),
            "monthly_advantage_pct": round((monthly - simple) / simple * 100, 2),
            "weekly_advantage_pct": round((weekly - simple) / simple * 100, 2)
        }

    def auto_compound_cycle(self):
        """
        Execute a compounding cycle:
        1. Withdraw all from savings (triggers interest calculation)
        2. Wait 3 days for withdrawal to complete
        3. Redeposit full balance (principal + interest) to savings
        """
        account = Account(self.account_name, blockchain_instance=self.hive)
        savings_hbd = float(account["savings_hbd_balance"].amount)
        if savings_hbd <= 0:
            print("No HBD in savings to compound")
            return
        # Initiate withdrawal - this triggers interest payment
        request_id = int(datetime.utcnow().timestamp()) % 2**32
        self.hive.transfer_from_savings(
            savings_hbd, "HBD", "compound",
            account=self.account_name,
            request_id=request_id
        )
        completion = datetime.utcnow() + timedelta(days=3)
        print(f"Withdrawal initiated: {savings_hbd} HBD")
        print(f"Will complete at: {completion.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"Request ID: {request_id}")
        print("Run redeposit() after 3-day window completes")
        return request_id

    def redeposit_after_withdrawal(self):
        """Redeposit all liquid HBD back to savings after withdrawal completes."""
        account = Account(self.account_name, blockchain_instance=self.hive)
        liquid_hbd = float(account["hbd_balance"].amount)
        if liquid_hbd <= 0.001:
            print("No liquid HBD to redeposit (withdrawal may not have completed)")
            return
        self.hive.transfer_to_savings(liquid_hbd, "HBD", "", self.account_name)
        print(f"Redeposited {liquid_hbd} HBD to savings (includes accrued interest)")

    def optimal_compound_schedule(self, principal, rate=None):
        """
        Calculate optimal compounding frequency considering the 3-day lock.
        More frequent = more time funds are in transit (not earning).
        """
        if rate is None:
            rate = self.get_current_hbd_rate()
        results = []
        for period_days in [7, 14, 30, 60, 90, 180, 365]:
            transit_days = 3  # funds earn nothing during withdrawal
            earning_days = period_days - transit_days
            if earning_days <= 0:
                continue
            earning_ratio = earning_days / period_days
            compounds_per_year = 365 / period_days
            effective_rate_per_period = rate * (earning_days / 365)
            # Account for 3 days of lost interest each cycle
            final = principal
            for _ in range(int(compounds_per_year)):
                interest = final * effective_rate_per_period
                final += interest
            net_yield = final - principal
            effective_apr = net_yield / principal * 100
            results.append({
                "period_days": period_days,
                "compounds_per_year": round(compounds_per_year, 1),
                "effective_apr": round(effective_apr, 2),
                "annual_yield": round(net_yield, 3)
            })
        best = max(results, key=lambda x: x["effective_apr"])
        print(f"Optimal compound period: every {best['period_days']} days")
        print(f"Effective APR: {best['effective_apr']}%")
        for r in results:
            marker = " <-- BEST" if r == best else ""
            print(f"  {r['period_days']:>3}d: {r['effective_apr']:>6.2f}% APR, "
                  f"~{r['annual_yield']:.3f} HBD/year{marker}")
        return results

# Usage
opt = HBDSavingsOptimizer("myaccount", "5KactiveKey")
print("Compound advantage on 1000 HBD at 20%:")
print(opt.calculate_compound_advantage(1000, 0.20))
print()
opt.optimal_compound_schedule(1000)
```

Key insights: (1) The 3-day withdrawal window means very frequent compounding is counterproductive because funds earn nothing in transit. (2) Monthly compounding is usually the sweet spot -- roughly 21% effective vs 20% simple. (3) You can use `cancel_transfer_from_savings` if you change your mind during the 3-day window. (4) HBD in savings counts toward the HBD debt limit (currently 30% of HIVE market cap), so large holders should monitor the haircut rule. (5) Convert HIVE to HBD via `convert` (3.5-day median price) when you want to increase savings principal.'''
    ),
    (
        "hive-defi-tribaldex-integration",
        r'''How do I integrate Tribaldex trading features into a custom application, including market orders, limit orders, and pool analytics?''',
        r'''Tribaldex is the primary DEX for Hive Engine tokens. All operations are custom_json transactions on Hive layer-1 that the sidechain processes. You can integrate its full trading functionality into any application. Here is a comprehensive integration module:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const axios = require("axios");

const client = new Client(["https://api.hive.blog"]);
const ENGINE_RPC = "https://engine.rishipanthee.com/contracts";
const ENGINE_HISTORY = "https://accounts.hive-engine.com/accountHistory";

class TribaldexIntegration {
    constructor(account, activeKey) {
        this.account = account;
        this.key = PrivateKey.fromString(activeKey);
    }

    async engineQuery(contract, table, query, limit = 1000, offset = 0) {
        const resp = await axios.post(ENGINE_RPC, {
            jsonrpc: "2.0", id: 1, method: "find",
            params: { contract, table, query, limit, offset }
        });
        return resp.data.result || [];
    }

    async broadcast(contractName, contractAction, contractPayload) {
        const json = JSON.stringify({ contractName, contractAction, contractPayload });
        return client.broadcast.json(
            { required_auths: [this.account], required_posting_auths: [],
              id: "ssc-mainnet-hive", json },
            this.key
        );
    }

    // --- Market Orders (order book trading) ---
    async placeBuyOrder(symbol, quantity, price) {
        return this.broadcast("market", "buy", {
            symbol, quantity: quantity.toFixed(8), price: price.toFixed(8)
        });
    }

    async placeSellOrder(symbol, quantity, price) {
        return this.broadcast("market", "sell", {
            symbol, quantity: quantity.toFixed(8), price: price.toFixed(8)
        });
    }

    async cancelOrder(type, orderId) {
        return this.broadcast("market", "cancel", { type, id: orderId });
    }

    async getOrderBook(symbol, limit = 50) {
        const buyOrders = await this.engineQuery("market", "buyBook",
            { symbol }, limit);
        const sellOrders = await this.engineQuery("market", "sellBook",
            { symbol }, limit);
        buyOrders.sort((a, b) => parseFloat(b.price) - parseFloat(a.price));
        sellOrders.sort((a, b) => parseFloat(a.price) - parseFloat(b.price));
        const bestBid = buyOrders[0] ? parseFloat(buyOrders[0].price) : 0;
        const bestAsk = sellOrders[0] ? parseFloat(sellOrders[0].price) : 0;
        const spread = bestAsk > 0 ? ((bestAsk - bestBid) / bestAsk * 100) : 0;
        return { buyOrders, sellOrders, bestBid, bestAsk,
                 spread: spread.toFixed(2) + "%" };
    }

    // --- Pool (AMM) Operations ---
    async swapTokens(tokenPair, tokenSymbol, amount, maxSlippagePct = 1.0) {
        const pools = await this.engineQuery("marketpools", "pools",
            { tokenPair });
        if (!pools.length) throw new Error("Pool not found");
        const pool = pools[0];
        const pair = pool.tokenPair.split(":");
        const baseQty = parseFloat(pool.baseQuantity);
        const quoteQty = parseFloat(pool.quoteQuantity);
        const fee = 0.0025;
        const amtAfterFee = amount * (1 - fee);
        let reserveIn, reserveOut;
        if (tokenSymbol === pair[0]) {
            reserveIn = baseQty; reserveOut = quoteQty;
        } else {
            reserveIn = quoteQty; reserveOut = baseQty;
        }
        const expectedOut = (reserveOut * amtAfterFee) / (reserveIn + amtAfterFee);
        const minOut = expectedOut * (1 - maxSlippagePct / 100);
        return this.broadcast("marketpools", "swapTokens", {
            tokenPair, tokenSymbol,
            tokenAmount: amount.toFixed(8),
            tradeType: "exactInput",
            minAmountOut: minOut.toFixed(8)
        });
    }

    // --- Analytics ---
    async getPoolAnalytics(tokenPair) {
        const pools = await this.engineQuery("marketpools", "pools",
            { tokenPair });
        if (!pools.length) return null;
        const pool = pools[0];
        const baseQty = parseFloat(pool.baseQuantity);
        const quoteQty = parseFloat(pool.quoteQuantity);
        const price = quoteQty / baseQty;
        const tvl = baseQty * 2;  // Approximate TVL in base token terms
        return {
            tokenPair: pool.tokenPair,
            baseQuantity: baseQty, quoteQuantity: quoteQty,
            price: price.toFixed(8),
            totalShares: pool.totalShares,
            estimatedTVL_base: tvl.toFixed(2),
            precision: pool.precision || 8
        };
    }

    async getTopPools(limit = 10) {
        const allPools = await this.engineQuery("marketpools", "pools", {}, 100);
        // Sort by base quantity as proxy for TVL
        allPools.sort((a, b) =>
            parseFloat(b.baseQuantity) - parseFloat(a.baseQuantity));
        return allPools.slice(0, limit).map(p => ({
            pair: p.tokenPair,
            base: parseFloat(p.baseQuantity).toFixed(2),
            quote: parseFloat(p.quoteQuantity).toFixed(2),
            providers: p.totalShares
        }));
    }

    async getMyOpenOrders(symbol = null) {
        const query = { account: this.account };
        if (symbol) query.symbol = symbol;
        const buys = await this.engineQuery("market", "buyBook", query, 100);
        const sells = await this.engineQuery("market", "sellBook", query, 100);
        return { buyOrders: buys, sellOrders: sells,
                 totalOpen: buys.length + sells.length };
    }

    async getTokenBalance(symbol) {
        const balances = await this.engineQuery("tokens", "balances",
            { account: this.account, symbol });
        if (!balances.length) return { balance: 0, stake: 0, delegatedIn: 0 };
        const b = balances[0];
        return {
            balance: parseFloat(b.balance || 0),
            stake: parseFloat(b.stake || 0),
            delegatedIn: parseFloat(b.delegationsIn || 0)
        };
    }
}

// Usage
(async () => {
    const tdx = new TribaldexIntegration("myaccount", "5KactiveKey");
    const book = await tdx.getOrderBook("BEE");
    console.log("BEE Order Book:", book.bestBid, "/", book.bestAsk, "spread:", book.spread);
    const tops = await tdx.getTopPools(5);
    console.log("Top pools:", JSON.stringify(tops, null, 2));
    const analytics = await tdx.getPoolAnalytics("SWAP.HIVE:BEE");
    console.log("Pool analytics:", analytics);
})();
```

This integration covers both order-book trading (buy/sell limit orders via the market contract) and AMM swaps (via marketpools contract). Order book trades settle against SWAP.HIVE as the quote currency. Pool swaps use constant-product pricing. For production use, add retry logic since Hive Engine RPC nodes can occasionally lag behind the sidechain head block. You can also listen for sidechain transaction confirmations by polling the block API at `https://engine.rishipanthee.com/blockchain` to verify your operations completed successfully.'''
    ),
]
