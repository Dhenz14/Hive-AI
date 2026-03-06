"""Hive blockchain training pairs: delegation (HP and RC)."""

PAIRS = [
    (
        "hive/vesting-delegation",
        r'''How do I delegate Hive Power (HP) to another account using beem? Show delegation, checking, and removal.''',
        r'''HP delegation allows you to share your staking weight with another account without transferring ownership. The delegatee gets the voting power and RC from the delegated HP.

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Delegate_vesting_shares
from beem.amount import Amount
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

ACCOUNT = "myaccount"

def hp_to_vests(hp_amount):
    """Convert Hive Power to VESTS."""
    props = hive.rpc.get_dynamic_global_properties()
    total_vesting_hive = float(str(props["total_vesting_fund_hive"]).split()[0])
    total_vesting_shares = float(str(props["total_vesting_shares"]).split()[0])
    vests_per_hp = total_vesting_shares / total_vesting_hive
    return hp_amount * vests_per_hp

def vests_to_hp(vests_amount):
    """Convert VESTS to Hive Power."""
    props = hive.rpc.get_dynamic_global_properties()
    total_vesting_hive = float(str(props["total_vesting_fund_hive"]).split()[0])
    total_vesting_shares = float(str(props["total_vesting_shares"]).split()[0])
    hp_per_vest = total_vesting_hive / total_vesting_shares
    return vests_amount * hp_per_vest

def delegate_hp(delegatee, hp_amount):
    """Delegate HP to another account."""
    vests = hp_to_vests(hp_amount)

    op = Delegate_vesting_shares(**{
        "delegator": ACCOUNT,
        "delegatee": delegatee,
        "vesting_shares": f"{vests:.6f} VESTS"
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Delegated {hp_amount:.3f} HP ({vests:.6f} VESTS) to @{delegatee}")
    return result

def remove_delegation(delegatee):
    """Remove a delegation (set to 0 VESTS)."""
    op = Delegate_vesting_shares(**{
        "delegator": ACCOUNT,
        "delegatee": delegatee,
        "vesting_shares": "0.000000 VESTS"
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Delegation to @{delegatee} removed (returns in 5 days)")
    return result

def get_outgoing_delegations(account_name):
    """List all outgoing HP delegations."""
    result = hive.rpc.find_vesting_delegations(
        {"account": account_name},
        api="database_api"
    )
    delegations = result.get("delegations", [])

    total_vests = 0
    print(f"Outgoing delegations from @{account_name}:")
    for d in delegations:
        vests = float(str(d["vesting_shares"]).split()[0])
        hp = vests_to_hp(vests)
        total_vests += vests
        print(f"  -> @{d['delegatee']:20s}: {hp:>10.3f} HP ({vests:.6f} VESTS)")

    total_hp = vests_to_hp(total_vests)
    print(f"Total delegated: {total_hp:.3f} HP")
    return delegations

def get_incoming_delegations(account_name):
    """List HP delegations received by an account."""
    result = hive.rpc.find_vesting_delegation_expirations(
        {"account": account_name},
        api="database_api"
    )
    # For incoming, use account object
    acct = Account(account_name, hive_instance=hive)
    received_vests = float(str(acct["received_vesting_shares"]).split()[0])
    received_hp = vests_to_hp(received_vests)
    print(f"@{account_name} received: {received_hp:.3f} HP in delegations")
    return received_hp

# Usage
# delegate_hp("newuser", 15.0)
# remove_delegation("newuser")
get_outgoing_delegations(ACCOUNT)
```

Important delegation rules:
- Delegating HP is instant; the delegatee can use it immediately
- Removing delegation has a 5-day cooldown before the HP returns to the delegator
- During cooldown, neither party can use the delegated HP
- Delegated HP counts for voting power and RC for the delegatee
- The delegator retains ownership and can remove the delegation anytime
- You cannot delegate more HP than your own balance minus minimum requirement
'''
    ),
    (
        "hive/delegation-tracking",
        r'''How do I build a delegation tracking system that monitors all incoming and outgoing HP delegations for multiple accounts?''',
        r'''Here is a comprehensive delegation tracking system that monitors delegations in real-time and provides summary reports:

```python
from beem import Hive
from beem.account import Account
from beem.blockchain import Blockchain
import json
import time
from datetime import datetime

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

class DelegationTracker:
    def __init__(self, hive_instance):
        self.hive = hive_instance
        self._vests_ratio = None
        self._ratio_time = 0

    def _get_vests_ratio(self):
        """Cache the VESTS/HP ratio (refreshes every 5 min)."""
        if self._vests_ratio is None or time.time() - self._ratio_time > 300:
            props = self.hive.rpc.get_dynamic_global_properties()
            total_hive = float(str(props["total_vesting_fund_hive"]).split()[0])
            total_vests = float(str(props["total_vesting_shares"]).split()[0])
            self._vests_ratio = total_hive / total_vests
            self._ratio_time = time.time()
        return self._vests_ratio

    def vests_to_hp(self, vests):
        return vests * self._get_vests_ratio()

    def get_full_delegation_report(self, account_name):
        """Get complete delegation report for an account."""
        acct = Account(account_name, hive_instance=self.hive)

        # Own HP
        own_vests = float(str(acct["vesting_shares"]).split()[0])
        own_hp = self.vests_to_hp(own_vests)

        # Received delegations
        received_vests = float(str(acct["received_vesting_shares"]).split()[0])
        received_hp = self.vests_to_hp(received_vests)

        # Delegated out
        delegated_vests = float(str(acct["delegated_vesting_shares"]).split()[0])
        delegated_hp = self.vests_to_hp(delegated_vests)

        # Effective HP
        effective_hp = own_hp - delegated_hp + received_hp

        report = {
            "account": account_name,
            "own_hp": own_hp,
            "received_hp": received_hp,
            "delegated_hp": delegated_hp,
            "effective_hp": effective_hp,
            "outgoing": [],
            "expiring": []
        }

        # Get outgoing delegation details
        out_result = self.hive.rpc.find_vesting_delegations(
            {"account": account_name},
            api="database_api"
        )
        for d in out_result.get("delegations", []):
            vests = float(str(d["vesting_shares"]).split()[0])
            report["outgoing"].append({
                "delegatee": d["delegatee"],
                "hp": self.vests_to_hp(vests),
                "vests": vests,
                "min_delegation_time": d.get("min_delegation_time", "")
            })

        # Get expiring delegations (being returned)
        exp_result = self.hive.rpc.find_vesting_delegation_expirations(
            {"account": account_name},
            api="database_api"
        )
        for e in exp_result.get("delegations", []):
            vests = float(str(e["vesting_shares"]).split()[0])
            report["expiring"].append({
                "hp": self.vests_to_hp(vests),
                "expiration": e.get("expiration", "")
            })

        return report

    def print_report(self, report):
        """Pretty-print a delegation report."""
        print(f"\n=== Delegation Report: @{report['account']} ===")
        print(f"Own HP:       {report['own_hp']:>12.3f}")
        print(f"Received HP:  {report['received_hp']:>12.3f}")
        print(f"Delegated HP: {report['delegated_hp']:>12.3f}")
        print(f"Effective HP: {report['effective_hp']:>12.3f}")

        if report["outgoing"]:
            print(f"\nOutgoing delegations ({len(report['outgoing'])}):")
            for d in sorted(report["outgoing"], key=lambda x: -x["hp"]):
                print(f"  -> @{d['delegatee']:20s}: {d['hp']:>10.3f} HP")

        if report["expiring"]:
            print(f"\nExpiring (returning) delegations:")
            for e in report["expiring"]:
                print(f"  {e['hp']:>10.3f} HP expires {e['expiration']}")

    def stream_delegation_changes(self, callback):
        """Stream real-time delegation changes."""
        blockchain = Blockchain(hive_instance=self.hive)
        stream = blockchain.stream(
            opNames=["delegate_vesting_shares"],
            raw_ops=False,
            threading=False
        )
        for op in stream:
            vests = float(str(op.get("vesting_shares", "0")).split()[0])
            hp = self.vests_to_hp(vests)
            event = {
                "delegator": op["delegator"],
                "delegatee": op["delegatee"],
                "hp": hp,
                "vests": vests,
                "is_removal": vests == 0,
                "block": op.get("block_num"),
                "timestamp": op.get("timestamp")
            }
            callback(event)

# Usage
tracker = DelegationTracker(hive)
report = tracker.get_full_delegation_report("blocktrades")
tracker.print_report(report)

# Stream delegation changes in real-time
# tracker.stream_delegation_changes(lambda e:
#     print(f"{'REMOVED' if e['is_removal'] else 'DELEGATED'}: "
#           f"@{e['delegator']} -> @{e['delegatee']}: {e['hp']:.3f} HP"))
```

This tracker provides a complete view of delegation status including own HP, received delegations, outgoing delegations, and expiring (returning) delegations. The streaming function lets you monitor delegation changes network-wide in real-time.
'''
    ),
    (
        "hive/rc-delegation-patterns",
        r'''When should I use RC delegation vs HP delegation on Hive? What are the tradeoffs?''',
        r'''<think>
The user is asking about RC delegation vs HP delegation. Let me think about this carefully because these two mechanisms are easy to confuse.

My first instinct was that RC delegation is just a lighter version of HP delegation -- but wait, that is not quite right. They are fundamentally different operations. HP delegation shares both voting power and RC, while RC delegation shares only bandwidth. So RC delegation is not a subset of HP delegation; it serves a completely separate purpose.

I considered whether RC delegation uses the active key like HP delegation does, but actually it uses the posting key. That makes sense because you are not moving any stake or financial value -- you are just sharing transaction bandwidth. Since the posting key is lower-privilege, this means RC delegation carries less security risk. Therefore, for use cases where you only need to give someone the ability to transact (like onboarding or running a bot), RC delegation is strictly safer.

Hmm, what about removal cooldowns? HP delegation has a 5-day cooldown when you remove it, because the chain needs time to recalculate voting weights and prevent abuse. But RC delegation has no cooldown at all -- you can revoke it instantly. That is a big deal for situations where you might need to cut off a misbehaving bot or revoke access quickly.

So the key tradeoff comes down to: do you want to share just transaction capacity, or also governance and curation weight? For onboarding new users who just need to post and comment, RC delegation is the right choice. For curation partnerships or community accounts that need to vote with your stake, HP delegation is necessary.
</think>

RC delegation and HP delegation serve different use cases on Hive. Here is a detailed comparison with code showing when to use each:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Delegate_vesting_shares, Delegate_rc
import json

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5ActiveKey", "5PostingKey"]
)

ACCOUNT = "myaccount"

# RC Delegation: share bandwidth only
def delegate_rc_only(to_account, max_rc):
    """Delegate RC without giving voting power.

    Advantages:
    - Only costs posting key (lower security risk)
    - No cooldown on removal (instant)
    - Does not affect voting power
    - Can be used for temporary bandwidth needs
    """
    op = Delegate_rc(**{
        "from": ACCOUNT,
        "delegatees": [to_account],
        "max_rc": max_rc,
        "extensions": []
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "posting")  # Posting key!
    tx.sign()
    return tx.broadcast()

# HP Delegation: share voting power + RC
def delegate_hp(to_account, vests_amount):
    """Delegate HP giving both voting power and RC.

    Advantages:
    - Delegatee gets full voting weight
    - Useful for curation partnerships
    - Delegatee earns curation rewards

    Disadvantages:
    - Requires active key
    - 5-day cooldown on removal
    - Reduces your own voting power
    """
    op = Delegate_vesting_shares(**{
        "delegator": ACCOUNT,
        "delegatee": to_account,
        "vesting_shares": f"{vests_amount:.6f} VESTS"
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")  # Active key!
    tx.sign()
    return tx.broadcast()

# Decision helper
def recommend_delegation_type(use_case):
    """Recommend RC vs HP delegation based on use case."""
    rc_cases = {
        "new_user_onboarding": (
            "RC delegation: New users need to transact but "
            "should not have your voting weight"
        ),
        "bot_operations": (
            "RC delegation: Bots need bandwidth for custom_json "
            "but should not vote with your stake"
        ),
        "temporary_access": (
            "RC delegation: No cooldown means you can revoke instantly"
        ),
        "dapp_account": (
            "RC delegation: App accounts broadcast many transactions "
            "but do not need to curate"
        ),
    }

    hp_cases = {
        "curation_partner": (
            "HP delegation: Partner curates content and earns "
            "curation rewards from your stake"
        ),
        "community_account": (
            "HP delegation: Community accounts need voting weight "
            "to distribute rewards"
        ),
        "investment_return": (
            "HP delegation: Delegatee uses your voting power and "
            "may share curation returns"
        ),
        "witness_support": (
            "HP delegation: Increases their influence in governance"
        ),
    }

    if use_case in rc_cases:
        print(f"Recommendation: {rc_cases[use_case]}")
        return "rc"
    elif use_case in hp_cases:
        print(f"Recommendation: {hp_cases[use_case]}")
        return "hp"
    else:
        print("Unknown use case. Default: RC delegation (safer)")
        return "rc"

# Comparison table
def print_comparison():
    print("""
Feature              | RC Delegation      | HP Delegation
---------------------|--------------------|-----------------
Voting power shared  | No                 | Yes
RC shared            | Yes                | Yes
Key required         | Posting            | Active
Removal cooldown     | None (instant)     | 5 days
Curation rewards     | Delegatee: No      | Delegatee: Yes
Security risk        | Lower              | Higher
Introduced           | HF26               | Original
Best for             | Onboarding, bots   | Curation, community
""")

print_comparison()
recommend_delegation_type("new_user_onboarding")
recommend_delegation_type("curation_partner")
```

Summary: Use RC delegation for bandwidth-only needs (onboarding, bots, dApp accounts). Use HP delegation when you want to share voting power and the delegatee should earn curation rewards. RC delegation is strictly safer since it uses the posting key and has no removal cooldown.
'''
    ),
    (
        "hive/delegation-bot",
        r'''How do I build an automated delegation bot that manages HP delegations based on configurable rules?''',
        r'''Here is a delegation bot that automatically manages HP delegations based on rules like staking requirements, activity levels, and time limits:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Delegate_vesting_shares
import json
import time
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("delegation_bot")

class DelegationBot:
    def __init__(self, bot_account, active_key, nodes=None):
        self.account = bot_account
        self.hive = Hive(
            node=nodes or ["https://api.hive.blog"],
            keys=[active_key]
        )
        self.rules = []
        self.active_delegations = {}

    def add_rule(self, name, check_fn, hp_amount, duration_days=None):
        """Add a delegation rule.

        Args:
            name: Rule identifier
            check_fn: Function(account_name) -> bool
            hp_amount: HP to delegate when rule matches
            duration_days: Auto-remove after N days (None = permanent)
        """
        self.rules.append({
            "name": name,
            "check": check_fn,
            "hp": hp_amount,
            "duration": duration_days
        })

    def _hp_to_vests(self, hp):
        props = self.hive.rpc.get_dynamic_global_properties()
        total_hive = float(str(props["total_vesting_fund_hive"]).split()[0])
        total_vests = float(str(props["total_vesting_shares"]).split()[0])
        return hp * (total_vests / total_hive)

    def delegate(self, to_account, hp_amount):
        """Execute a delegation."""
        vests = self._hp_to_vests(hp_amount)
        op = Delegate_vesting_shares(**{
            "delegator": self.account,
            "delegatee": to_account,
            "vesting_shares": f"{vests:.6f} VESTS"
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        result = tx.broadcast()
        logger.info(f"Delegated {hp_amount:.3f} HP to @{to_account}")
        return result

    def remove_delegation(self, to_account):
        """Remove a delegation."""
        op = Delegate_vesting_shares(**{
            "delegator": self.account,
            "delegatee": to_account,
            "vesting_shares": "0.000000 VESTS"
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        result = tx.broadcast()
        logger.info(f"Removed delegation to @{to_account}")
        return result

    def process_request(self, account_name):
        """Check rules and delegate if eligible."""
        if account_name in self.active_delegations:
            logger.info(f"@{account_name} already has active delegation")
            return False

        for rule in self.rules:
            try:
                if rule["check"](account_name):
                    logger.info(f"@{account_name} matched rule '{rule['name']}'")
                    self.delegate(account_name, rule["hp"])
                    self.active_delegations[account_name] = {
                        "rule": rule["name"],
                        "hp": rule["hp"],
                        "started": datetime.utcnow().isoformat(),
                        "expires": (
                            (datetime.utcnow() + timedelta(days=rule["duration"])).isoformat()
                            if rule["duration"] else None
                        )
                    }
                    return True
            except Exception as e:
                logger.error(f"Rule check error for @{account_name}: {e}")
        return False

    def check_expirations(self):
        """Remove expired delegations."""
        now = datetime.utcnow()
        expired = []
        for acct, info in self.active_delegations.items():
            if info["expires"] and datetime.fromisoformat(info["expires"]) < now:
                expired.append(acct)

        for acct in expired:
            self.remove_delegation(acct)
            del self.active_delegations[acct]
            logger.info(f"Expired delegation to @{acct} removed")

    def run(self, check_interval=3600):
        """Main bot loop."""
        logger.info(f"Delegation bot started for @{self.account}")
        while True:
            try:
                self.check_expirations()
            except Exception as e:
                logger.error(f"Expiration check error: {e}")
            time.sleep(check_interval)

# Rule functions
def is_new_account(account_name):
    """Check if account was created within the last 30 days."""
    hive = Hive(node=["https://api.hive.blog"])
    acct = Account(account_name, hive_instance=hive)
    created = datetime.strptime(acct["created"], "%Y-%m-%dT%H:%M:%S")
    return (datetime.utcnow() - created).days <= 30

def has_introduction_post(account_name):
    """Check if user posted an introduction."""
    hive = Hive(node=["https://api.hive.blog"])
    acct = Account(account_name, hive_instance=hive)
    return acct["post_count"] > 0

# Setup bot
bot = DelegationBot("delegationbot", "5ActiveKey")
bot.add_rule("new_user", is_new_account, hp_amount=15.0, duration_days=30)
bot.add_rule("active_user", has_introduction_post, hp_amount=25.0, duration_days=60)
# bot.process_request("newuser123")
# bot.run()
```

This bot framework supports configurable rules, automatic expiration, and multiple delegation tiers. You can extend it with rules based on reputation, token holdings, community membership, or any custom criteria.
'''
    ),
    (
        "hive/redelegate-patterns",
        r'''What are the best patterns for managing redelegation on Hive? How do I handle the cooldown period when changing delegation amounts?''',
        r'''Redelegation on Hive requires understanding the 5-day cooldown and how the chain handles delegation changes. Here are the key patterns:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Delegate_vesting_shares
from datetime import datetime, timedelta
import json
import time

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5ActiveKey"]
)

ACCOUNT = "myaccount"

def hp_to_vests(hp):
    props = hive.rpc.get_dynamic_global_properties()
    total_hive = float(str(props["total_vesting_fund_hive"]).split()[0])
    total_vests = float(str(props["total_vesting_shares"]).split()[0])
    return hp * total_vests / total_hive

def vests_to_hp(vests):
    props = hive.rpc.get_dynamic_global_properties()
    total_hive = float(str(props["total_vesting_fund_hive"]).split()[0])
    total_vests = float(str(props["total_vesting_shares"]).split()[0])
    return vests * total_hive / total_vests

class DelegationManager:
    """Manage delegations with awareness of cooldown periods."""

    def __init__(self, account, hive_instance):
        self.account = account
        self.hive = hive_instance

    def get_available_hp(self):
        """Calculate HP available for delegation."""
        acct = Account(self.account, hive_instance=self.hive)
        own_vests = float(str(acct["vesting_shares"]).split()[0])
        delegated_vests = float(str(acct["delegated_vesting_shares"]).split()[0])
        own_hp = vests_to_hp(own_vests)
        delegated_hp = vests_to_hp(delegated_vests)
        # Keep minimum 5 HP for own operations
        available = own_hp - delegated_hp - 5.0
        return max(0, available)

    def increase_delegation(self, delegatee, new_hp_total):
        """Increase an existing delegation (no cooldown penalty).

        Increasing is instant -- the delegatee gets more HP immediately.
        """
        vests = hp_to_vests(new_hp_total)
        op = Delegate_vesting_shares(**{
            "delegator": self.account,
            "delegatee": delegatee,
            "vesting_shares": f"{vests:.6f} VESTS"
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        result = tx.broadcast()
        print(f"Increased delegation to @{delegatee}: {new_hp_total:.3f} HP")
        return result

    def decrease_delegation(self, delegatee, new_hp_total):
        """Decrease a delegation (triggers 5-day cooldown on the difference).

        The DECREASED amount goes into cooldown. The remaining delegation
        stays active for the delegatee.
        """
        if new_hp_total <= 0:
            return self.remove_delegation(delegatee)

        vests = hp_to_vests(new_hp_total)
        op = Delegate_vesting_shares(**{
            "delegator": self.account,
            "delegatee": delegatee,
            "vesting_shares": f"{vests:.6f} VESTS"
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        result = tx.broadcast()

        return_date = datetime.utcnow() + timedelta(days=5)
        print(f"Decreased delegation to @{delegatee}: {new_hp_total:.3f} HP")
        print(f"Difference returns: {return_date.strftime('%Y-%m-%d %H:%M')} UTC")
        return result

    def remove_delegation(self, delegatee):
        """Fully remove a delegation (entire amount enters 5-day cooldown)."""
        op = Delegate_vesting_shares(**{
            "delegator": self.account,
            "delegatee": delegatee,
            "vesting_shares": "0.000000 VESTS"
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        return tx.broadcast()

    def redistribute_delegations(self, new_distribution):
        """Redistribute HP across multiple delegatees.

        Args:
            new_distribution: dict of {account: hp_amount}

        Note: Decreases trigger cooldowns! Plan redistribution carefully.
        """
        # Get current delegations
        result = self.hive.rpc.find_vesting_delegations(
            {"account": self.account},
            api="database_api"
        )
        current = {}
        for d in result.get("delegations", []):
            vests = float(str(d["vesting_shares"]).split()[0])
            current[d["delegatee"]] = vests_to_hp(vests)

        # Calculate changes
        increases = []
        decreases = []
        removals = []

        for acct, new_hp in new_distribution.items():
            old_hp = current.get(acct, 0)
            if new_hp > old_hp:
                increases.append((acct, new_hp, new_hp - old_hp))
            elif new_hp < old_hp and new_hp > 0:
                decreases.append((acct, new_hp, old_hp - new_hp))

        # Accounts to fully undelegate
        for acct in current:
            if acct not in new_distribution:
                removals.append((acct, current[acct]))

        # Apply increases first (no cooldown)
        for acct, hp, diff in increases:
            print(f"  Increase @{acct}: +{diff:.3f} HP -> {hp:.3f} HP")

        # Apply decreases (triggers cooldown)
        for acct, hp, diff in decreases:
            print(f"  Decrease @{acct}: -{diff:.3f} HP -> {hp:.3f} HP "
                  f"(5-day cooldown on {diff:.3f} HP)")

        for acct, hp in removals:
            print(f"  Remove @{acct}: -{hp:.3f} HP "
                  f"(5-day cooldown on {hp:.3f} HP)")

        total_cooldown = sum(d for _, _, d in decreases) + sum(h for _, h in removals)
        print(f"\nTotal HP entering cooldown: {total_cooldown:.3f}")
        print("HP in cooldown is unavailable for 5 days")

# Usage
mgr = DelegationManager(ACCOUNT, hive)
available = mgr.get_available_hp()
print(f"Available HP for delegation: {available:.3f}")
```

Key redelegation rules:
- Increasing delegation is instant and free (no cooldown)
- Decreasing triggers a 5-day cooldown on the reduced amount
- The chain stores one delegation per delegator-delegatee pair
- Each new delegation operation replaces the previous one for that pair
- Plan redistributions to minimize the amount entering cooldown
'''
    ),
]
