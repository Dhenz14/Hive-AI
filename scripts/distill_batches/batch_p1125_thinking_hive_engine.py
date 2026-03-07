"""
Hive blockchain thinking pairs - Hive Engine / Layer 2 decisions
"""

pairs = [
    {
        "instruction": r'''I want to create a token on Hive Engine for my community. What design decisions should I consider for the token economics and configuration?''',
        "output": r'''<think>
Token design on Hive Engine -- there are several important configuration choices that are hard or impossible to change after creation. Let me think through them.

First, the basics: creating a token on Hive Engine costs BEE (the native Hive Engine token). As of my knowledge, it costs 100 BEE to create a token, plus additional BEE for enabling features like staking or delegation.

Key design decisions:
1. Supply: fixed supply vs inflationary. Once you set the max supply, you cannot increase it. But you do not have to issue all tokens at creation -- you can issue (mint) them over time up to the max supply.

2. Precision: how many decimal places. This affects minimum transaction size. Most tokens use 3-8 decimal places. Once set, cannot be changed.

3. Staking: should the token be stakeable? Staking is a common feature for governance tokens. Enabling staking costs extra BEE. The unstaking period (cooldown) is configurable.

Hmm, wait -- I should think about what happens if I make wrong choices. Since Hive Engine is a sidechain, the token contract is immutable once deployed. If I set max supply too low, I am stuck. If I set precision too low, I cannot have small transactions.

I initially thought I should set max supply very high to leave room for growth, but actually a very high supply means low per-token price which can look "cheap" psychologically. The tradeoff is flexibility vs perception.

For staking, the unstaking period is critical. Too short (1 day) and there is no commitment. Too long (30 days) and users feel locked in. Hive itself uses a 13-week power-down period. Most successful Hive Engine tokens use 3-7 days.

Another decision: should the token have delegation? This allows staked tokens to be delegated to other accounts (like HP delegation on Hive). It adds complexity but enables interesting use cases like vote weight delegation.
</think>

Here is a comprehensive token creation setup with the key design decisions annotated:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]  # active key for Hive Engine operations
)

ACCOUNT = "mytokenaccount"

# === Token Design Decisions ===

TOKEN_CONFIG = {
    "symbol": "MYTOKEN",
    "name": "My Community Token",
    "precision": 8,        # decimal places (CANNOT change later)
                           # 8 = like Bitcoin, good for divisibility
                           # 3 = like HIVE/HBD, simpler amounts
    "maxSupply": "10000000",  # 10 million max (CANNOT increase later)
                              # Tip: do not over-inflate, but leave room
    "url": "https://myproject.com",
    "orgName": "My Project",
}

# Staking configuration
STAKING_CONFIG = {
    "unstakingCooldown": 7,   # days to unstake (1-365)
                              # 7 days = good balance of commitment
                              # vs user flexibility
    "numberTransactions": 4,  # unstaking is split into N payments
                              # 4 payments over 7 days = partial
                              # liquidity during unstaking
}


def create_token():
    """Create a new Hive Engine token.

    Cost: 100 BEE for token creation.
    Additional costs for enabling staking, delegation, etc.
    """
    # Step 1: Create the token
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({
            "contractName": "tokens",
            "contractAction": "create",
            "contractPayload": TOKEN_CONFIG
        }, separators=(",", ":"))
    }))
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Token created: {result['id']}")
    return result


def enable_staking():
    """Enable staking for the token. Cost: 100 BEE."""
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({
            "contractName": "tokens",
            "contractAction": "enableStaking",
            "contractPayload": {
                "symbol": TOKEN_CONFIG["symbol"],
                **STAKING_CONFIG
            }
        }, separators=(",", ":"))
    }))
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()


def enable_delegation():
    """Enable delegation for staked tokens. Cost: 1000 BEE."""
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({
            "contractName": "tokens",
            "contractAction": "enableDelegation",
            "contractPayload": {
                "symbol": TOKEN_CONFIG["symbol"],
                "undelegationCooldown": 7  # days to undelegate
            }
        }, separators=(",", ":"))
    }))
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()


def issue_tokens(to_account, quantity):
    """Mint tokens to an account (up to maxSupply)."""
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [ACCOUNT],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({
            "contractName": "tokens",
            "contractAction": "issue",
            "contractPayload": {
                "symbol": TOKEN_CONFIG["symbol"],
                "to": to_account,
                "quantity": str(quantity)
            }
        }, separators=(",", ":"))
    }))
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    return tx.broadcast()


# === Token Distribution Strategy ===

def distribute_initial_tokens():
    """Example initial distribution plan."""
    distributions = [
        # Community rewards pool (60%)
        ("community-rewards", "6000000"),
        # Team allocation (15%)
        ("team-multisig", "1500000"),
        # Development fund (15%)
        ("dev-fund", "1500000"),
        # Initial airdrop (10%)
        ("airdrop-account", "1000000"),
    ]

    for to_account, quantity in distributions:
        result = issue_tokens(to_account, quantity)
        print(f"Issued {quantity} {TOKEN_CONFIG['symbol']} to {to_account}")
```

Decision checklist: precision 8 for maximum divisibility, 10M max supply for perceived scarcity with growth room, 7-day unstaking with 4 partial payments for user-friendly commitment mechanics, delegation enabled for governance flexibility. All of these except delegation are immutable after creation.'''
    },
    {
        "instruction": r'''How do I interact with Hive Engine smart contracts from Python? I want to query token balances and market data.''',
        "output": r'''<think>
Hive Engine has its own API separate from the Hive blockchain API. The sidechain data is queried through the Hive Engine RPC nodes, not through the standard Hive API nodes.

Let me think about the architecture. Hive Engine operations are broadcast as custom_json on the Hive mainchain with id "ssc-mainnet-hive". But reading state (balances, market orders, etc.) requires querying the Hive Engine sidechain nodes directly.

The main Hive Engine API endpoint was historically at api.hive-engine.com, but there are also alternative nodes. The API uses a JSON-RPC style with contract-specific endpoints.

Hmm, should I use a library or raw API calls? There is a Python library called "hiveengine" but I am not sure how well-maintained it is. Using requests directly gives more control and transparency.

Wait, actually I think the endpoints use a specific query format. You post to /contracts with a method, contract name, table name, and query parameters. Let me think about the common queries:

- Token balances: contracts endpoint, contract "tokens", table "balances"
- Token info: contract "tokens", table "tokens"
- Market orders: contract "market", tables "buyBook" and "sellBook"

I initially thought there would be a REST API, but it is actually a POST-based RPC. Each query specifies the contract and table to query, with MongoDB-style query operators for filtering.

The tradeoff for using raw requests vs a library is: raw requests = more verbose but no dependency, library = cleaner but another dependency to manage. For a focused use case, raw requests with a thin wrapper is fine.
</think>

Hive Engine has its own RPC API separate from Hive mainchain. Here is a Python client for common queries:

```python
import requests
import json
from typing import Optional

# Hive Engine API nodes
HE_NODES = [
    "https://api.hive-engine.com/rpc",
    "https://herpc.dtools.dev",
    "https://engine.rishipanthee.com",
]


class HiveEngineClient:
    """Client for querying Hive Engine sidechain data."""

    def __init__(self, node=None):
        self.node = node or HE_NODES[0]
        self.session = requests.Session()

    def _query(self, contract, table, query, offset=0, limit=1000):
        """Query a Hive Engine contract table."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "find",
            "params": {
                "contract": contract,
                "table": table,
                "query": query,
                "limit": limit,
                "offset": offset,
            }
        }
        resp = self.session.post(
            f"{self.node}/contracts",
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("result", [])

    def _query_one(self, contract, table, query):
        """Query for a single result."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "findOne",
            "params": {
                "contract": contract,
                "table": table,
                "query": query,
            }
        }
        resp = self.session.post(
            f"{self.node}/contracts",
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("result")

    # === Token Queries ===

    def get_token_info(self, symbol):
        """Get token metadata (supply, precision, etc.)."""
        return self._query_one("tokens", "tokens", {"symbol": symbol})

    def get_token_balance(self, account, symbol):
        """Get an account's balance of a specific token."""
        result = self._query_one("tokens", "balances", {
            "account": account,
            "symbol": symbol
        })
        if result:
            return {
                "balance": result.get("balance", "0"),
                "stake": result.get("stake", "0"),
                "delegatedStake": result.get("delegatedStake", "0"),
                "receivedStake": result.get("receivedStake", "0"),
                "pendingUnstake": result.get("pendingUnstake", "0"),
            }
        return None

    def get_all_balances(self, account):
        """Get all token balances for an account."""
        return self._query("tokens", "balances", {"account": account})

    # === Market Queries ===

    def get_buy_orders(self, symbol, limit=50):
        """Get open buy orders for a token (sorted by price desc)."""
        return self._query("market", "buyBook", {
            "symbol": symbol
        }, limit=limit)

    def get_sell_orders(self, symbol, limit=50):
        """Get open sell orders for a token (sorted by price asc)."""
        return self._query("market", "sellBook", {
            "symbol": symbol
        }, limit=limit)

    def get_trade_history(self, symbol, limit=50):
        """Get recent trades for a token."""
        return self._query("market", "tradesHistory", {
            "symbol": symbol
        }, limit=limit)

    def get_market_metrics(self, symbol):
        """Get market metrics (last price, volume, etc.)."""
        return self._query_one("market", "metrics", {"symbol": symbol})

    # === Staking Queries ===

    def get_pending_unstakes(self, account, symbol=None):
        """Get pending unstake operations for an account."""
        query = {"account": account}
        if symbol:
            query["symbol"] = symbol
        return self._query("tokens", "pendingUnstakes", query)

    def get_delegations(self, from_account=None, to_account=None,
                        symbol=None):
        """Get delegation records."""
        query = {}
        if from_account:
            query["from"] = from_account
        if to_account:
            query["to"] = to_account
        if symbol:
            query["symbol"] = symbol
        return self._query("tokens", "delegations", query)


# === Usage Examples ===

he = HiveEngineClient()

# Token info
token = he.get_token_info("BEE")
if token:
    print(f"BEE - Supply: {token.get('supply')} / "
          f"{token.get('maxSupply')}")
    print(f"Precision: {token.get('precision')}")

# Account balances
balances = he.get_all_balances("someaccount")
for bal in balances:
    liquid = float(bal.get("balance", 0))
    staked = float(bal.get("stake", 0))
    if liquid > 0 or staked > 0:
        print(f"  {bal['symbol']}: {liquid:.3f} liquid, "
              f"{staked:.3f} staked")

# Market data
metrics = he.get_market_metrics("BEE")
if metrics:
    print(f"BEE market - Last: {metrics.get('lastPrice')} SWAP.HIVE, "
          f"Volume: {metrics.get('volume')}")
```

The key thing to understand is that Hive Engine state lives on the sidechain nodes, not on Hive mainchain. Write operations go through Hive custom_json (ssc-mainnet-hive), but reads go directly to the Hive Engine API. Always query the sidechain API for current balances and market state.'''
    },
    {
        "instruction": r'''I have tokens on Hive Engine and I want to build a rewards distribution system that pays out stakers weekly. What is the best approach?''',
        "output": r'''<think>
Weekly staking rewards distribution on Hive Engine. Let me think about the approaches.

Option 1: Use Hive Engine's built-in distribution features. I think there are some smart contracts for this, but I am not sure about the exact capabilities. Scotbot used to handle tribe token distributions, but that was more about content rewards.

Option 2: Build a custom distribution script that queries stakers and sends tokens via custom_json operations. More flexible but more work.

Hmm, for option 2, the process would be:
1. Query all accounts with staked tokens
2. Calculate each staker's share based on their stake
3. Send tokens to each staker via Hive Engine transfer operations

But wait, there are several issues to think about. If I have 1000 stakers, that is 1000 transfer operations. Each is a custom_json on Hive mainchain, which costs RC. Batching would help but there is still a lot of operations.

I initially thought I could just query balances and send proportional rewards, but I need to consider: should rewards be based on time-weighted stake? An account that staked 1 day before the snapshot should not get the same as one staked all week. But tracking time-weighted stake is complex.

The tradeoff is: snapshot-based distribution (simple, one query, but gameable by staking right before snapshot) vs time-weighted distribution (fair, but requires tracking daily snapshots). A middle ground is taking multiple snapshots during the week and averaging them.

Another consideration: should rewards compound? If I distribute tokens that are automatically staked, stakers compound. If I distribute liquid tokens, they choose whether to restake or sell. Most projects distribute liquid and let users decide.

Could also consider using Hive Engine's "stakeReward" action instead of "transfer" -- I think this stakes the tokens directly to the recipient. That would auto-compound.
</think>

Build a custom distribution system with multi-snapshot averaging to prevent gaming. Here is a complete implementation:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import requests
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

HE_API = "https://api.hive-engine.com/rpc/contracts"
ISSUER_ACCOUNT = "myproject"
TOKEN_SYMBOL = "MYTOKEN"
WEEKLY_REWARD_POOL = 10000  # tokens to distribute per week
EXCLUDED_ACCOUNTS = {"myproject", "null", "myproject-rewards"}


class StakingRewardsDistributor:
    """Distribute weekly rewards to token stakers."""

    def __init__(self, issuer, symbol, weekly_pool):
        self.issuer = issuer
        self.symbol = symbol
        self.weekly_pool = weekly_pool
        self.snapshots = []  # list of {account: stake_amount} dicts

    def _query_he(self, contract, table, query, limit=1000, offset=0):
        """Query Hive Engine API."""
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "find",
            "params": {
                "contract": contract, "table": table,
                "query": query, "limit": limit, "offset": offset
            }
        }
        resp = requests.post(HE_API, json=payload, timeout=15)
        return resp.json().get("result", [])

    def take_snapshot(self):
        """Capture current staking balances."""
        all_stakers = {}
        offset = 0

        while True:
            results = self._query_he("tokens", "balances", {
                "symbol": self.symbol,
                "stake": {"$gt": "0"}
            }, limit=1000, offset=offset)

            if not results:
                break

            for bal in results:
                account = bal["account"]
                if account not in EXCLUDED_ACCOUNTS:
                    stake = float(bal.get("stake", 0))
                    received = float(bal.get("receivedStake", 0))
                    # Include received delegations in stake weight
                    total = stake + received
                    if total > 0:
                        all_stakers[account] = total

            offset += 1000
            if len(results) < 1000:
                break

        self.snapshots.append({
            "timestamp": datetime.utcnow().isoformat(),
            "stakers": all_stakers,
            "total_staked": sum(all_stakers.values())
        })
        print(f"Snapshot taken: {len(all_stakers)} stakers, "
              f"{sum(all_stakers.values()):.3f} total staked")
        return all_stakers

    def calculate_rewards(self):
        """Calculate rewards using average stake across snapshots.

        Multi-snapshot averaging prevents gaming by staking
        right before the distribution.
        """
        if not self.snapshots:
            raise ValueError("No snapshots taken")

        # Average each account's stake across all snapshots
        account_totals = defaultdict(list)
        for snapshot in self.snapshots:
            all_accounts = set()
            for s in self.snapshots:
                all_accounts.update(s["stakers"].keys())

            for account in all_accounts:
                stake = snapshot["stakers"].get(account, 0)
                account_totals[account].append(stake)

        averaged_stakes = {}
        for account, stakes in account_totals.items():
            avg = sum(stakes) / len(self.snapshots)
            if avg > 0:
                averaged_stakes[account] = avg

        total_weighted = sum(averaged_stakes.values())
        if total_weighted == 0:
            return {}

        # Calculate proportional rewards
        rewards = {}
        for account, avg_stake in averaged_stakes.items():
            share = avg_stake / total_weighted
            reward = self.weekly_pool * share
            # Round to token precision
            reward = round(reward, 8)
            if reward > 0:
                rewards[account] = reward

        return rewards

    def distribute_rewards(self, rewards, batch_size=20):
        """Send reward tokens to stakers in batched transactions."""
        recipients = list(rewards.items())
        total_distributed = 0
        batch_num = 0

        for i in range(0, len(recipients), batch_size):
            batch = recipients[i:i + batch_size]
            batch_num += 1

            tx = TransactionBuilder(blockchain_instance=hive)

            for account, amount in batch:
                tx.appendOps(Custom_json(**{
                    "required_auths": [self.issuer],
                    "required_posting_auths": [],
                    "id": "ssc-mainnet-hive",
                    "json": json.dumps({
                        "contractName": "tokens",
                        "contractAction": "transfer",
                        "contractPayload": {
                            "symbol": self.symbol,
                            "to": account,
                            "quantity": f"{amount:.8f}",
                            "memo": "Weekly staking reward"
                        }
                    }, separators=(",", ":"))
                }))

            tx.appendSigner(self.issuer, "active")
            tx.sign()

            try:
                result = tx.broadcast()
                batch_total = sum(a for _, a in batch)
                total_distributed += batch_total
                print(f"Batch {batch_num}: {len(batch)} recipients, "
                      f"{batch_total:.3f} {self.symbol} | TX: {result['id']}")
            except Exception as e:
                print(f"Batch {batch_num} failed: {e}")
                # Individual fallback for failed batches
                for account, amount in batch:
                    try:
                        single_tx = TransactionBuilder(
                            blockchain_instance=hive)
                        single_tx.appendOps(Custom_json(**{
                            "required_auths": [self.issuer],
                            "required_posting_auths": [],
                            "id": "ssc-mainnet-hive",
                            "json": json.dumps({
                                "contractName": "tokens",
                                "contractAction": "transfer",
                                "contractPayload": {
                                    "symbol": self.symbol,
                                    "to": account,
                                    "quantity": f"{amount:.8f}",
                                    "memo": "Weekly staking reward"
                                }
                            }, separators=(",", ":"))
                        }))
                        single_tx.appendSigner(self.issuer, "active")
                        single_tx.sign()
                        single_tx.broadcast()
                        total_distributed += amount
                    except Exception as inner_e:
                        print(f"  Failed for {account}: {inner_e}")

            time.sleep(4)

        print(f"\nDistribution complete: {total_distributed:.3f} "
              f"{self.symbol} to {len(recipients)} stakers")


# === Weekly Distribution Schedule ===

dist = StakingRewardsDistributor(ISSUER_ACCOUNT, TOKEN_SYMBOL,
                                  WEEKLY_REWARD_POOL)

# Take snapshots throughout the week (run daily via cron)
dist.take_snapshot()
# ... run daily ...

# On distribution day:
rewards = dist.calculate_rewards()
dist.distribute_rewards(rewards)
```

Key design decisions: multi-snapshot averaging prevents last-minute staking to game the distribution. Batched broadcasts reduce RC costs and API load. Fallback to individual transfers if a batch fails. Received delegations count toward stake weight so delegation has utility.'''
    },
    {
        "instruction": r'''I need to bridge HIVE tokens to Hive Engine (as SWAP.HIVE) and back. How does the wrapping/unwrapping process work and how do I automate it?''',
        "output": r'''<think>
SWAP.HIVE is the wrapped version of HIVE on Hive Engine. To get SWAP.HIVE, you deposit HIVE to a specific account, and the Hive Engine sidechain credits you with the equivalent SWAP.HIVE. To unwrap, you use a Hive Engine withdrawal operation.

Let me think about the exact process. For wrapping (HIVE to SWAP.HIVE): you transfer HIVE to the "honey-swap" account (or is it a different account? I think the current deposit account might be different). Actually, I believe you send HIVE to an account like "honey-swap" with a specific memo, and the sidechain picks it up and credits SWAP.HIVE to your account.

Hmm, wait. I need to be more careful here. The deposit mechanism works through the "hivepegged" contract on Hive Engine. You send a regular Hive transfer to a gateway account. The memo might need to be empty or contain a specific format.

I initially thought the gateway account was "honey-swap", but I think for SWAP.HIVE it might be "honey-swap" or a contract-specific account. Let me think... Actually, there are multiple ways this has been implemented. The standard approach is to use the Hive Engine deposit mechanism where you send HIVE to a specific account and the sidechain bridge picks up the transfer and credits SWAP.HIVE.

For unwrapping (SWAP.HIVE back to HIVE): you call the withdraw action on the hivepegged contract via custom_json. The sidechain burns the SWAP.HIVE and the gateway sends HIVE back to your Hive account.

The tradeoff for automating this: you need to trust the bridge. If the bridge is down, your deposit might be delayed. For large amounts, it is worth monitoring the deposit to confirm the SWAP.HIVE credit arrived before proceeding.
</think>

SWAP.HIVE is the wrapped HIVE on Hive Engine. Here is how the wrapping and unwrapping process works:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer, Custom_json
from beem.account import Account
import requests
import json
import time

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

HE_API = "https://api.hive-engine.com/rpc/contracts"
ACCOUNT = "myaccount"

# The deposit account for SWAP.HIVE
# This is the Hive Engine gateway account
DEPOSIT_ACCOUNT = "honey-swap"


# === Wrap: HIVE -> SWAP.HIVE ===

def deposit_hive(account, amount):
    """Deposit HIVE to get SWAP.HIVE on Hive Engine.

    Send a regular HIVE transfer to the gateway account.
    The Hive Engine bridge detects it and credits SWAP.HIVE.
    """
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Transfer(**{
        "from": account,
        "to": DEPOSIT_ACCOUNT,
        "amount": f"{amount:.3f} HIVE",
        "memo": ""  # empty memo for standard deposit
    }))
    tx.appendSigner(account, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Deposit sent: {amount:.3f} HIVE -> {DEPOSIT_ACCOUNT}")
    print(f"TX: {result['id']}")
    print("SWAP.HIVE should appear in ~1-2 minutes")
    return result


# === Unwrap: SWAP.HIVE -> HIVE ===

def withdraw_hive(account, amount):
    """Withdraw SWAP.HIVE back to HIVE.

    Uses the hivepegged contract withdraw action.
    Burns SWAP.HIVE and sends HIVE to your account.
    """
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [account],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({
            "contractName": "hivepegged",
            "contractAction": "withdraw",
            "contractPayload": {
                "quantity": f"{amount:.3f}"
            }
        }, separators=(",", ":"))
    }))
    tx.appendSigner(account, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Withdrawal initiated: {amount:.3f} SWAP.HIVE -> HIVE")
    print(f"TX: {result['id']}")
    print("HIVE should arrive in ~1-5 minutes")
    return result


# === Monitor Balance ===

def get_swap_hive_balance(account):
    """Check SWAP.HIVE balance on Hive Engine."""
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "findOne",
        "params": {
            "contract": "tokens",
            "table": "balances",
            "query": {"account": account, "symbol": "SWAP.HIVE"}
        }
    }
    resp = requests.post(HE_API, json=payload, timeout=10)
    result = resp.json().get("result")
    if result:
        return float(result.get("balance", "0"))
    return 0.0


def wait_for_deposit(account, expected_amount, timeout=300):
    """Wait for SWAP.HIVE deposit to be credited."""
    start = time.time()
    initial_balance = get_swap_hive_balance(account)
    print(f"Initial SWAP.HIVE balance: {initial_balance:.3f}")

    while time.time() - start < timeout:
        current = get_swap_hive_balance(account)
        if current >= initial_balance + expected_amount * 0.99:
            print(f"Deposit confirmed! Balance: {current:.3f}")
            return True
        time.sleep(10)

    print(f"Timeout waiting for deposit. Current: {current:.3f}")
    return False


def wait_for_withdrawal(account, expected_amount, timeout=300):
    """Wait for HIVE withdrawal to arrive."""
    start = time.time()
    acc = Account(account, blockchain_instance=hive)
    initial = float(acc.get_balance("available", "HIVE"))
    print(f"Initial HIVE balance: {initial:.3f}")

    while time.time() - start < timeout:
        acc.refresh()
        current = float(acc.get_balance("available", "HIVE"))
        if current >= initial + expected_amount * 0.99:
            print(f"Withdrawal confirmed! Balance: {current:.3f}")
            return True
        time.sleep(10)

    print("Timeout waiting for withdrawal")
    return False


# === Automated Bridge with Verification ===

def safe_wrap(account, amount):
    """Wrap HIVE to SWAP.HIVE with confirmation."""
    deposit_hive(account, amount)
    success = wait_for_deposit(account, amount)
    if not success:
        print("WARNING: Deposit not confirmed within timeout. "
              "Check Hive Engine explorer.")
    return success


def safe_unwrap(account, amount):
    """Unwrap SWAP.HIVE to HIVE with confirmation."""
    balance = get_swap_hive_balance(account)
    if balance < amount:
        print(f"Insufficient SWAP.HIVE: have {balance:.3f}, "
              f"need {amount:.3f}")
        return False

    withdraw_hive(account, amount)
    success = wait_for_withdrawal(account, amount)
    if not success:
        print("WARNING: Withdrawal not confirmed within timeout. "
              "Check Hive Engine explorer.")
    return success


# Usage
safe_wrap(ACCOUNT, 100.0)    # wrap 100 HIVE -> SWAP.HIVE
safe_unwrap(ACCOUNT, 50.0)   # unwrap 50 SWAP.HIVE -> HIVE
```

Important notes: the bridge has a small fee (typically 0.75-1%). Deposits and withdrawals are not instant -- they depend on the sidechain processing the Hive block containing your transfer. Always verify the deposit/withdrawal completed before proceeding with further operations. For large amounts, test with a small amount first.'''
    },
    {
        "instruction": r'''I want to create an NFT marketplace on Hive Engine. What contract patterns should I use for minting, listing, and trading NFTs?''',
        "output": r'''<think>
NFTs on Hive Engine -- Hive Engine has an NFT smart contract system. Let me think about how it works.

Hive Engine NFTs use the "nft" contract. You create an NFT definition (collection), define properties (metadata schema), and then issue individual tokens. Each NFT instance can have different property values.

For a marketplace, I need to think about several components:
1. Creating the NFT collection
2. Defining properties (rarity, image, description, etc.)
3. Minting individual NFTs
4. Listing for sale
5. Buying/trading

Hmm, the Hive Engine NFT market contract handles listings and trades. You can list an NFT for sale at a fixed price, and buyers purchase it through the market contract. There is also a "transfer" action for direct transfers.

I initially thought I would need to build a custom marketplace contract, but Hive Engine already has a built-in NFT market. The "nftmarket" contract handles listings, cancellations, and purchases. So I just need to interact with the existing contracts.

Wait, but the built-in market is basic -- fixed price only. If I want auctions, bundle sales, or royalties, I would need custom logic. Royalties could be handled by having the marketplace contract take a cut, but that requires a custom contract or off-chain enforcement.

The tradeoff is: use the built-in market (simple, trusted, but limited features) vs build a custom market contract (flexible, but costs BEE to deploy and needs auditing). For starting out, the built-in market is the right choice. Add custom features later.

For the NFT properties, I should think carefully about what goes on-chain vs off-chain. On-chain: rarity, edition number, creator -- things that need verification. Off-chain (IPFS): images, detailed descriptions, animations -- things that are too large for on-chain storage.
</think>

Hive Engine has built-in NFT and marketplace contracts. Here is how to create a collection and manage listings:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import requests
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

HE_API = "https://api.hive-engine.com/rpc/contracts"
CREATOR = "nft-creator"


def he_broadcast(account, contract, action, payload):
    """Helper to broadcast a Hive Engine operation."""
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [account],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps({
            "contractName": contract,
            "contractAction": action,
            "contractPayload": payload
        }, separators=(",", ":"))
    }))
    tx.appendSigner(account, "active")
    tx.sign()
    return tx.broadcast()


# === Step 1: Create NFT Collection ===
# Cost: 100 BEE

def create_nft_collection():
    """Create a new NFT definition (collection)."""
    return he_broadcast(CREATOR, "nft", "create", {
        "name": "MyArtCollection",
        "symbol": "MYART",
        "maxSupply": 10000,    # max NFTs in this collection
        "authorizedIssuingAccounts": [CREATOR],
        "authorizedIssuingContracts": [],
    })


# === Step 2: Define Properties ===
# Properties define what metadata each NFT can have

def add_nft_properties():
    """Add data properties to the NFT collection."""
    properties = [
        {"name": "name", "type": "string", "isReadOnly": True},
        {"name": "rarity", "type": "string", "isReadOnly": True},
        {"name": "edition", "type": "number", "isReadOnly": True},
        {"name": "image_ipfs", "type": "string", "isReadOnly": True},
        {"name": "artist", "type": "string", "isReadOnly": True},
    ]

    results = []
    for prop in properties:
        result = he_broadcast(CREATOR, "nft", "addProperty", {
            "symbol": "MYART",
            **prop
        })
        results.append(result)
        print(f"Added property: {prop['name']}")

    return results


# === Step 3: Mint NFTs ===

def mint_nft(to_account, name, rarity, edition, image_cid, artist):
    """Mint a single NFT to an account."""
    return he_broadcast(CREATOR, "nft", "issue", {
        "symbol": "MYART",
        "to": to_account,
        "feeSymbol": "BEE",  # fee paid in BEE
        "properties": {
            "name": name,
            "rarity": rarity,
            "edition": edition,
            "image_ipfs": image_cid,
            "artist": artist
        }
    })


def mint_edition(name, rarity, artist, image_cid, edition_size,
                 to_account=None):
    """Mint a full edition of an NFT."""
    to = to_account or CREATOR
    results = []
    for i in range(1, edition_size + 1):
        result = mint_nft(to, name, rarity, i, image_cid, artist)
        results.append(result)
        print(f"Minted {name} #{i}/{edition_size}")
    return results


# === Step 4: Marketplace Operations ===

def list_for_sale(account, nft_ids, price, price_symbol="SWAP.HIVE"):
    """List NFTs for sale on the Hive Engine market."""
    return he_broadcast(account, "nftmarket", "sell", {
        "symbol": "MYART",
        "nfts": nft_ids,  # list of NFT instance IDs
        "price": str(price),
        "priceSymbol": price_symbol,
        "fee": 500  # 5% marketplace fee (in basis points)
    })


def cancel_listing(account, order_id):
    """Cancel an NFT listing."""
    return he_broadcast(account, "nftmarket", "cancel", {
        "symbol": "MYART",
        "orderId": order_id
    })


def buy_nft(buyer, order_ids, marketplace_account=None):
    """Buy listed NFTs."""
    payload = {
        "symbol": "MYART",
        "orders": order_ids,  # list of order IDs to purchase
    }
    if marketplace_account:
        payload["marketAccount"] = marketplace_account
    return he_broadcast(buyer, "nftmarket", "buy", payload)


def transfer_nft(from_account, to_account, nft_ids):
    """Direct transfer NFTs (no sale)."""
    return he_broadcast(from_account, "nft", "transfer", {
        "to": to_account,
        "nfts": [{"symbol": "MYART", "ids": nft_ids}]
    })


# === Query NFT Data ===

def query_he(contract, table, query, limit=100):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {
            "contract": contract, "table": table,
            "query": query, "limit": limit
        }
    }
    resp = requests.post(HE_API, json=payload, timeout=10)
    return resp.json().get("result", [])


def get_nfts_owned_by(account):
    """Get all NFTs owned by an account."""
    return query_he("nft", "MYARTinstances", {"account": account})


def get_market_listings(symbol="MYART"):
    """Get active marketplace listings."""
    return query_he("nftmarket", f"{symbol}sellBook", {})


# Usage
# create_nft_collection()
# add_nft_properties()
# mint_nft(CREATOR, "Cosmic Dream #1", "legendary", 1,
#          "QmXyz...abc", "artist1")
# list_for_sale(CREATOR, ["1"], "100.000")
```

Architecture notes: NFT images/media go on IPFS (store the CID on-chain in properties). Read-only properties cannot be changed after minting -- use this for authenticity-critical fields. The built-in nftmarket handles escrow automatically. For royalties, implement them as a fee in your marketplace frontend and enforce via the fee parameter in sell operations.'''
    },
]
