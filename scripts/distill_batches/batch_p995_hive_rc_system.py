"""Hive blockchain training pairs: Resource Credits (RC) system."""

PAIRS = [
    (
        "hive/rc-calculate-costs",
        r'''How do I calculate the Resource Credit (RC) cost of different operations on the Hive blockchain?''',
        r'''<think>
The user wants to calculate RC costs for different operations. My first thought was that RC works like a simple gas fee system, but actually it is more nuanced than that. There are three separate resource pools -- state memory, history size, and execution time -- and each operation draws differently from each pool.

Let me think about which operations are expensive vs cheap. A transfer is mostly just updating two balances in state, so it should be cheap. But hmm, what about account_create? That adds a permanent entry to the chain state that can never be pruned, so it must be much more expensive. Wait, I initially assumed custom_json would be cheap since it does not modify core state, but it still writes to the block log (history size), so it depends heavily on payload size.

The regeneration period is... 3 days? No, actually it is 5 days (432000 seconds) for a full 0-to-100% regeneration. This is important because it means an account effectively has a "bandwidth budget" over a rolling 5-day window. Since more Hive Power means more max RC, accounts with very little HP can get stuck unable to transact at all.

I should use the rc_api endpoints to show concrete cost numbers, because abstract explanations are less useful than seeing "a vote costs X RC while a comment costs Y RC." The beem RC class already wraps these calculations nicely.
</think>

The Resource Credits system on Hive is a bandwidth allocation mechanism that replaces transaction fees. Here is how to query and calculate RC costs:

```python
from beem import Hive
from beem.account import Account
from beem.rc import RC
import json

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

def get_rc_info(account_name):
    """Get current RC status for an account."""
    result = hive.rpc.find_rc_accounts(
        {"accounts": [account_name]},
        api="rc_api"
    )
    rc_account = result["rc_accounts"][0]

    max_rc = int(rc_account["max_rc"])
    current_mana = int(rc_account["rc_manabar"]["current_mana"])
    last_update = int(rc_account["rc_manabar"]["last_update_time"])

    # RC regenerates linearly over 5 days (432000 seconds)
    import time
    now = int(time.time())
    elapsed = now - last_update
    regen_rate = max_rc / 432000  # RC per second
    regenerated = min(elapsed * regen_rate, max_rc - current_mana)
    effective_rc = min(current_mana + regenerated, max_rc)

    pct = (effective_rc / max_rc * 100) if max_rc > 0 else 0

    print(f"Account: {account_name}")
    print(f"Max RC:      {max_rc:>20,}")
    print(f"Current RC:  {effective_rc:>20,.0f} ({pct:.1f}%)")
    print(f"Regen rate:  {regen_rate:>20,.0f} RC/sec")
    return effective_rc, max_rc

def estimate_operation_costs():
    """Estimate RC costs for common operations."""
    rc = RC(hive_instance=hive)

    # Get current resource parameters
    params = hive.rpc.get_resource_params(api="rc_api")
    pool = hive.rpc.get_resource_pool(api="rc_api")

    operations = {
        "comment": rc.comment(tx_size=300, permlink_length=50,
                              parent_permlink_length=0),
        "vote": rc.vote(tx_size=210),
        "transfer": rc.transfer(tx_size=210, market_op_count=1),
        "custom_json": rc.custom_json(tx_size=500),
    }

    print("\nEstimated RC costs per operation:")
    print("-" * 45)
    for op_name, cost in operations.items():
        print(f"  {op_name:20s}: {cost:>15,} RC")

    return operations

def how_many_operations(account_name, operation_type="vote"):
    """Calculate how many operations an account can do."""
    effective_rc, max_rc = get_rc_info(account_name)
    costs = estimate_operation_costs()
    cost = costs.get(operation_type, costs["vote"])

    if cost > 0:
        count = int(effective_rc / cost)
        print(f"\n{account_name} can perform ~{count:,} {operation_type} operations")
        return count
    return 0

# Check RC for an account
get_rc_info("hiveio")
estimate_operation_costs()
how_many_operations("hiveio", "comment")
```

Key facts about RC:
- RC regenerates linearly over 5 days from 0% to 100%
- More Hive Power (HP) means more max RC
- RC is not transferable, but RC delegation exists since HF26
- New accounts start with very limited RC unless delegated HP
- If RC hits 0, the account cannot transact until it regenerates
'''
    ),
    (
        "hive/rc-delegation",
        r'''How do I delegate Resource Credits (RC) to another account on Hive? Show the code for creating and managing RC delegations.''',
        r'''RC delegation was introduced in Hive hardfork 26. It allows accounts to share their RC capacity without delegating Hive Power (HP). This is especially useful for onboarding new users who have little HP.

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Delegate_rc
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingPrivateKey"]
)

def delegate_rc(from_account, to_account, max_rc_amount):
    """Delegate RC to another account.

    Args:
        from_account: The delegator's account name
        to_account: The delegatee's account name
        max_rc_amount: Maximum RC to delegate (in RC units)
    """
    op = Delegate_rc(**{
        "from": from_account,
        "delegatees": [to_account],
        "max_rc": max_rc_amount,
        "extensions": []
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(from_account, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"RC delegation broadcast: {result['id']}")
    return result

def remove_rc_delegation(from_account, to_account):
    """Remove an RC delegation by setting max_rc to 0."""
    return delegate_rc(from_account, to_account, 0)

def get_rc_delegations(account_name):
    """List all outgoing RC delegations for an account."""
    result = hive.rpc.list_rc_direct_delegations(
        {"start": [account_name, ""], "limit": 100},
        api="rc_api"
    )
    delegations = result.get("rc_direct_delegations", [])

    print(f"RC delegations from {account_name}:")
    total_delegated = 0
    for d in delegations:
        delegated = int(d["delegated_rc"])
        total_delegated += delegated
        print(f"  -> {d['to']:20s}: {delegated:>15,} RC")

    print(f"Total delegated: {total_delegated:,} RC")
    return delegations

def estimate_rc_for_daily_usage(votes=10, comments=5, transfers=2, custom_json=20):
    """Estimate how much RC to delegate for a user's daily needs."""
    from beem.rc import RC
    rc = RC(hive_instance=hive)

    vote_cost = rc.vote(tx_size=210)
    comment_cost = rc.comment(tx_size=300, permlink_length=50,
                               parent_permlink_length=0)
    transfer_cost = rc.transfer(tx_size=210, market_op_count=1)
    cj_cost = rc.custom_json(tx_size=500)

    daily_rc = (
        votes * vote_cost +
        comments * comment_cost +
        transfers * transfer_cost +
        custom_json * cj_cost
    )

    # Account for 5-day regen: to sustain daily usage,
    # user needs max_rc = daily_rc * 5
    recommended_delegation = daily_rc * 5

    print(f"Daily RC needed:          {daily_rc:>15,}")
    print(f"Recommended delegation:   {recommended_delegation:>15,}")
    print(f"  ({votes} votes, {comments} comments, "
          f"{transfers} transfers, {custom_json} custom_json/day)")

    return recommended_delegation

# Example: delegate enough RC for a new user's daily activity
needed = estimate_rc_for_daily_usage(votes=10, comments=5, transfers=2, custom_json=20)
delegate_rc("myaccount", "newuser", needed)

# Check delegations
get_rc_delegations("myaccount")
```

RC delegation uses the posting key (not active), making it lightweight. The delegation is instant and can be removed at any time. Unlike HP delegation, removing RC delegation has no cooldown period. This makes it ideal for temporary onboarding where you want to give new users enough bandwidth to get started.
'''
    ),
    (
        "hive/rc-monitoring-alerts",
        r'''How do I build an RC monitoring system that alerts me when accounts are running low on Resource Credits?''',
        r'''Here is a complete RC monitoring system that tracks multiple accounts and sends alerts when RC drops below configurable thresholds:

```python
from beem import Hive
from beem.account import Account
import time
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("rc_monitor")

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

class RCMonitor:
    def __init__(self, accounts, warn_pct=20, critical_pct=5):
        self.accounts = accounts
        self.warn_pct = warn_pct
        self.critical_pct = critical_pct
        self.alert_history = {}
        self.alert_cooldown = 3600  # 1 hour between repeated alerts

    def get_rc_status(self, account_name):
        """Get current RC percentage for an account."""
        try:
            result = hive.rpc.find_rc_accounts(
                {"accounts": [account_name]},
                api="rc_api"
            )
            rc_data = result["rc_accounts"][0]
            max_rc = int(rc_data["max_rc"])
            if max_rc == 0:
                return 0.0, 0, 0

            current = int(rc_data["rc_manabar"]["current_mana"])
            last_update = int(rc_data["rc_manabar"]["last_update_time"])

            now = int(time.time())
            elapsed = now - last_update
            regen_rate = max_rc / 432000
            effective = min(current + elapsed * regen_rate, max_rc)
            pct = effective / max_rc * 100

            return pct, int(effective), max_rc
        except Exception as e:
            logger.error(f"Failed to get RC for {account_name}: {e}")
            return -1, 0, 0

    def should_alert(self, account_name, level):
        """Check if we should send an alert (respects cooldown)."""
        key = f"{account_name}:{level}"
        last_alert = self.alert_history.get(key, 0)
        if time.time() - last_alert > self.alert_cooldown:
            self.alert_history[key] = time.time()
            return True
        return False

    def send_alert(self, account_name, level, pct, effective_rc):
        """Send an alert via your preferred method."""
        msg = (f"[{level.upper()}] {account_name} RC at {pct:.1f}% "
               f"({effective_rc:,} RC)")
        logger.warning(msg)

        # Webhook example (Discord, Slack, etc.)
        # import requests
        # requests.post(WEBHOOK_URL, json={"content": msg})

        # You could also broadcast a custom_json alert on-chain
        # or send a Hive transfer with memo as notification

    def check_all(self):
        """Check all monitored accounts."""
        results = []
        for account in self.accounts:
            pct, effective, max_rc = self.get_rc_status(account)
            status = "ok"

            if pct < 0:
                status = "error"
            elif pct < self.critical_pct:
                status = "critical"
                if self.should_alert(account, "critical"):
                    self.send_alert(account, "critical", pct, effective)
            elif pct < self.warn_pct:
                status = "warning"
                if self.should_alert(account, "warning"):
                    self.send_alert(account, "warning", pct, effective)

            results.append({
                "account": account,
                "rc_pct": round(pct, 2),
                "effective_rc": effective,
                "max_rc": max_rc,
                "status": status
            })
            logger.info(f"{account}: {pct:.1f}% RC ({status})")

        return results

    def run(self, interval=300):
        """Run the monitor in a loop."""
        logger.info(f"Monitoring {len(self.accounts)} accounts "
                    f"(warn={self.warn_pct}%, critical={self.critical_pct}%)")
        while True:
            try:
                self.check_all()
            except Exception as e:
                logger.error(f"Monitor error: {e}")
            time.sleep(interval)

# Configure and run
monitor = RCMonitor(
    accounts=["mybot", "myaccount", "newuser1", "newuser2"],
    warn_pct=20,
    critical_pct=5
)
monitor.run(interval=300)
```

This monitors accounts every 5 minutes, sends alerts when RC drops below 20% (warning) or 5% (critical), and includes a cooldown to avoid alert fatigue. You can extend the send_alert method to integrate with Discord webhooks, email, or other notification systems.
'''
    ),
    (
        "hive/rc-optimization",
        r'''What strategies can I use to optimize Resource Credit usage for a Hive dApp that processes many transactions?''',
        r'''Optimizing RC usage is critical for dApps that broadcast many transactions. Here are practical strategies with code examples:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json, Vote
import json
import time

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourPostingKey", "5YourActiveKey"]
)

# Strategy 1: Batch multiple operations into a single transaction
# A transaction has a fixed overhead. Batching amortizes this cost.

def batch_custom_json(account, operations_data, dapp_id="myapp"):
    """Batch multiple logical operations into one custom_json."""
    # Instead of N separate custom_json ops, combine into one payload
    batch_payload = {
        "app": f"{dapp_id}/1.0",
        "batch": True,
        "operations": operations_data
    }
    serialized = json.dumps(batch_payload)

    # Check payload size (max 8192 bytes)
    if len(serialized.encode("utf-8")) > 8192:
        # Split into multiple transactions
        chunks = []
        current_chunk = []
        current_size = 100  # overhead estimate
        for op in operations_data:
            op_size = len(json.dumps(op).encode("utf-8"))
            if current_size + op_size > 7500:
                chunks.append(current_chunk)
                current_chunk = [op]
                current_size = 100 + op_size
            else:
                current_chunk.append(op)
                current_size += op_size
        if current_chunk:
            chunks.append(current_chunk)
        return chunks
    return [operations_data]

# Strategy 2: Use multiple operations in a single transaction
def multi_op_transaction(account, ops_list):
    """Put multiple distinct operations in one transaction."""
    tx = TransactionBuilder(hive_instance=hive)
    for op in ops_list:
        tx.appendOps(op)
    tx.appendSigner(account, "posting")
    tx.sign()
    return tx.broadcast()

# Example: vote + custom_json in one tx
def vote_and_log(voter, author, permlink, weight):
    vote_op = Vote(**{
        "voter": voter,
        "author": author,
        "permlink": permlink,
        "weight": weight
    })
    log_op = Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [voter],
        "id": "myapp",
        "json": json.dumps({"action": "vote_log", "author": author,
                            "permlink": permlink})
    })
    return multi_op_transaction(voter, [vote_op, log_op])

# Strategy 3: Minimize transaction size
def compact_json(data):
    """Minimize JSON size to reduce RC cost."""
    # Use short keys
    key_map = {
        "action": "a", "username": "u", "timestamp": "t",
        "amount": "m", "token": "k", "recipient": "r"
    }
    compact = {}
    for k, v in data.items():
        new_key = key_map.get(k, k)
        compact[new_key] = v
    return compact

# Strategy 4: Rate limiting and queuing
class RCThrottledQueue:
    def __init__(self, account, min_rc_pct=10):
        self.account = account
        self.min_rc_pct = min_rc_pct
        self.queue = []

    def add(self, operation):
        self.queue.append(operation)

    def process(self):
        while self.queue:
            # Check RC before each broadcast
            rc_info = hive.rpc.find_rc_accounts(
                {"accounts": [self.account]}, api="rc_api"
            )
            rc_data = rc_info["rc_accounts"][0]
            max_rc = int(rc_data["max_rc"])
            current = int(rc_data["rc_manabar"]["current_mana"])
            pct = (current / max_rc * 100) if max_rc > 0 else 0

            if pct < self.min_rc_pct:
                wait_secs = int((self.min_rc_pct - pct) / 100 * 432000)
                print(f"RC low ({pct:.1f}%), waiting {wait_secs}s")
                time.sleep(min(wait_secs, 300))
                continue

            op = self.queue.pop(0)
            try:
                result = hive.custom_json(**op)
                print(f"Broadcast OK: {result}")
            except Exception as e:
                print(f"Broadcast failed: {e}")
                self.queue.insert(0, op)
                time.sleep(10)

# Strategy 5: Use posting authority whenever possible
# Posting key operations cost less RC than active key operations
```

Summary of RC optimization strategies:
- Batch logical operations into fewer custom_json payloads
- Combine multiple operation types in a single transaction
- Minimize JSON payload size with short keys
- Implement RC-aware rate limiting and queuing
- Prefer posting authority over active authority when possible
- Monitor RC regeneration rates and adjust throughput accordingly
'''
    ),
    (
        "hive/rc-api-queries",
        r'''Show me all the available RC API endpoints on Hive and how to query them.''',
        r'''The rc_api plugin provides several endpoints for querying Resource Credit information. Here is a comprehensive guide to all available endpoints:

```python
from beem import Hive
import json
import requests

hive = Hive(node=["https://api.hive.blog"])

# You can also use direct RPC calls for more control
API_NODE = "https://api.hive.blog"

def rpc_call(method, params=None):
    """Make a direct JSON-RPC call to the rc_api."""
    payload = {
        "jsonrpc": "2.0",
        "method": f"rc_api.{method}",
        "params": params or {},
        "id": 1
    }
    resp = requests.post(API_NODE, json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if "error" in result:
        raise Exception(f"RPC error: {result['error']}")
    return result["result"]

# 1. find_rc_accounts - Get RC info for specific accounts
def find_rc_accounts(accounts):
    """Get RC mana, max RC, and delegation info."""
    result = rpc_call("find_rc_accounts", {"accounts": accounts})
    for acct in result["rc_accounts"]:
        print(f"\n--- {acct['account']} ---")
        print(f"  Max RC:        {int(acct['max_rc']):>20,}")
        print(f"  Current mana:  {int(acct['rc_manabar']['current_mana']):>20,}")
        print(f"  Last update:   {acct['rc_manabar']['last_update_time']}")
        # RC delegation info (HF26+)
        rcda = acct.get("delegated_rc", 0)
        rcra = acct.get("received_delegated_rc", 0)
        print(f"  Delegated out: {int(rcda):>20,}")
        print(f"  Received:      {int(rcra):>20,}")
    return result

# 2. list_rc_accounts - List RC accounts with pagination
def list_rc_accounts(start="", limit=10):
    """Paginate through RC accounts."""
    result = rpc_call("list_rc_accounts", {
        "start": start,
        "limit": limit
    })
    for acct in result["rc_accounts"]:
        max_rc = int(acct["max_rc"])
        print(f"  {acct['account']:20s}: {max_rc:>20,} max RC")
    return result

# 3. list_rc_direct_delegations - Get RC delegations
def list_rc_delegations(account, limit=100):
    """List outgoing RC delegations from an account."""
    result = rpc_call("list_rc_direct_delegations", {
        "start": [account, ""],
        "limit": limit
    })
    delegations = result.get("rc_direct_delegations", [])
    print(f"RC delegations from {account}:")
    for d in delegations:
        if d["from"] == account:
            print(f"  -> {d['to']:20s}: {int(d['delegated_rc']):>15,} RC")
    return delegations

# 4. get_resource_params - Get current resource pricing parameters
def get_resource_params():
    """Get the parameters used to calculate RC costs."""
    result = rpc_call("get_resource_params")
    params = result["resource_params"]
    print("Resource parameters:")
    for resource_name, config in params.items():
        decay = config.get("decay_params", {})
        budget = config.get("resource_dynamics_params", {})
        print(f"\n  {resource_name}:")
        print(f"    Budget per block: {budget.get('budget_per_time_unit', 'N/A')}")
        print(f"    Pool max:         {budget.get('pool_eq', 'N/A')}")
    return result

# 5. get_resource_pool - Get current resource pool levels
def get_resource_pool():
    """Get current state of resource pools."""
    result = rpc_call("get_resource_pool")
    pool = result["resource_pool"]
    print("Current resource pools:")
    for name, data in pool.items():
        current = int(data.get("current_pool", 0))
        print(f"  {name}: {current:>20,}")
    return result

# Run all queries
print("=== RC Account Info ===")
find_rc_accounts(["hiveio", "blocktrades"])

print("\n=== Resource Parameters ===")
get_resource_params()

print("\n=== Resource Pools ===")
get_resource_pool()

print("\n=== RC Delegations ===")
list_rc_delegations("hiveio")
```

These five endpoints cover all RC-related queries. The find_rc_accounts endpoint is the most commonly used, as it provides the mana bar data needed to calculate an account's current available RC and whether they can transact. The resource_params and resource_pool endpoints are used together to calculate precise operation costs.
'''
    ),
]
