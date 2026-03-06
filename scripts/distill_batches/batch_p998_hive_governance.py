"""Hive blockchain training pairs: governance and DHF proposals."""

PAIRS = [
    (
        "hive/dhf-proposal-creation",
        r'''How do I create a DHF (Decentralized Hive Fund) proposal on Hive? Show the complete process including the creation fee and post requirement.''',
        r'''<think>
The user is asking about DHF proposals on Hive. I initially thought this could be a simple transfer operation with some metadata... but wait, the DHF is its own dedicated system with a specific on-chain operation type. Let me think through the actual workflow.

The DHF (Decentralized Hive Fund), also known as the Hive Proposal System (HPS) or Hive DAO, allows anyone to request funding from the community treasury. I considered whether you could just submit a proposal directly with all details inline, but actually that is not how it works -- the proposal operation itself only references a permlink. Therefore you need a published post first, since the chain stores the proposal metadata separately from the full description.

The process involves:
1. Write a proposal post explaining your project
2. Broadcast a create_proposal operation -- hmm, what is the fee here? I recall seeing 10 HBD somewhere, but could be higher now. Actually checking the chain constants, it is 10 HBD burned plus 1 HBD additional fee, so 11 HBD total commitment.
3. Community votes on your proposal
4. If your proposal has more votes than the "return proposal", it gets funded daily

Wait, the receiver field is interesting -- I almost assumed it must match the creator, but actually the receiver can be a different account entirely. This matters because a project lead could create the proposal while funds go to a multisig or team account.

Key parameters:
- creator: who creates the proposal
- receiver: who receives the funds (can be different from creator, since the system separates authorship from payment)
- start_date / end_date: funding period
- daily_pay: how much HBD per day
- subject: title shown in proposal listings
- permlink: the post with full proposal details
</think>

Creating a DHF proposal on Hive involves writing a detailed post and then broadcasting a create_proposal operation. Here is the complete workflow:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Create_proposal, Update_proposal_votes
from beem.comment import Comment
import json
import time

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey", "5YourPostingKey"]
)

ACCOUNT = "myaccount"

# Step 1: Create the proposal post (regular Hive post)
def create_proposal_post(title, body):
    """Create a blog post describing the proposal."""
    permlink = title.lower().replace(" ", "-").replace(":", "")[:200]

    result = hive.post(
        title=title,
        body=body,
        author=ACCOUNT,
        permlink=permlink,
        tags=["hive-proposal", "dhf", "funding"],
        json_metadata=json.dumps({
            "app": "myapp/1.0",
            "tags": ["hive-proposal", "dhf", "funding"]
        })
    )
    print(f"Proposal post created: @{ACCOUNT}/{permlink}")
    return permlink

# Step 2: Create the proposal on-chain
def create_dhf_proposal(permlink, subject, receiver, daily_pay_hbd,
                         start_date, end_date):
    """Create a DHF proposal.

    Requirements:
    - 10 HBD creation fee (burned)
    - 1 HBD additional fee
    - A published post with the proposal details
    """
    op = Create_proposal(**{
        "creator": ACCOUNT,
        "receiver": receiver,
        "start_date": start_date,
        "end_date": end_date,
        "daily_pay": f"{daily_pay_hbd:.3f} HBD",
        "subject": subject,
        "permlink": permlink,
        "extensions": []
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Proposal created: {result['id']}")
    print(f"  Subject: {subject}")
    print(f"  Daily pay: {daily_pay_hbd:.3f} HBD")
    print(f"  Period: {start_date} to {end_date}")
    print(f"  Receiver: @{receiver}")
    print(f"  Fee: 10 HBD (burned)")
    return result

# Step 3: List proposals and check status
def list_proposals(order="by_total_votes", status="votable", limit=20):
    """List DHF proposals."""
    result = hive.rpc.list_proposals(
        {
            "start": [""],
            "limit": limit,
            "order": order,
            "order_direction": "descending",
            "status": status
        },
        api="database_api"
    )

    proposals = result.get("proposals", [])
    print(f"\n{'ID':>6} {'Daily HBD':>10} {'Votes (MVests)':>15} Subject")
    print("-" * 70)

    for p in proposals:
        pid = p["id"]
        daily = p["daily_pay"]
        votes = int(p["total_votes"]) / 1e12
        subject = p["subject"][:40]
        creator = p["creator"]
        print(f"{pid:>6} {daily:>10} {votes:>14.1f}M @{creator}: {subject}")

    return proposals

# Full workflow example
proposal_body = """
# My Hive Development Proposal

## Summary
Building an open-source tool for the Hive ecosystem.

## Budget
- Development: 50 HBD/day for 90 days
- Total: 4,500 HBD

## Milestones
1. Month 1: Core development
2. Month 2: Testing and documentation
3. Month 3: Launch and community feedback

## Team
@myaccount - Lead developer
"""

# permlink = create_proposal_post("My Hive Development Proposal", proposal_body)
# create_dhf_proposal(
#     permlink=permlink,
#     subject="My Hive Development Proposal",
#     receiver=ACCOUNT,
#     daily_pay_hbd=50.0,
#     start_date="2025-02-01T00:00:00",
#     end_date="2025-05-01T00:00:00"
# )

list_proposals()
```

Proposals are funded if they receive more votes (by stake weight) than the "return proposal" (proposal #0). The return proposal acts as a funding threshold -- any proposal below it does not receive funds. Daily payments come from the DHF treasury account @hive.fund.
'''
    ),
    (
        "hive/witness-voting",
        r'''How do I vote for witnesses and manage witness votes on Hive? Show both direct voting and proxy voting.''',
        r'''Witness voting is a core governance mechanism on Hive. Each account can vote for up to 30 witnesses, and votes are weighted by the voter's Hive Power (HP). Here is how to manage witness votes:

```python
from beem import Hive
from beem.account import Account
from beem.witness import Witness, WitnessesRankedByVote
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_witness_vote, Account_witness_proxy
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

ACCOUNT = "myaccount"

def vote_for_witness(witness_name, approve=True):
    """Vote or unvote a witness."""
    op = Account_witness_vote(**{
        "account": ACCOUNT,
        "witness": witness_name,
        "approve": approve
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    action = "Voted for" if approve else "Unvoted"
    print(f"{action} witness @{witness_name}: {result['id']}")
    return result

def set_voting_proxy(proxy_account):
    """Set a proxy for all witness and proposal votes.
    The proxy account's votes will count as yours.
    Set to empty string to remove proxy."""
    op = Account_witness_proxy(**{
        "account": ACCOUNT,
        "proxy": proxy_account
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    if proxy_account:
        print(f"Set voting proxy to @{proxy_account}: {result['id']}")
    else:
        print(f"Removed voting proxy: {result['id']}")
    return result

def get_my_witness_votes(account_name):
    """Get the list of witnesses an account has voted for."""
    acct = Account(account_name, hive_instance=hive)
    votes = acct.get("witness_votes", [])
    proxy = acct.get("proxy", "")

    print(f"Witness votes for @{account_name}:")
    if proxy:
        print(f"  PROXY: All votes delegated to @{proxy}")
    else:
        print(f"  Direct votes ({len(votes)}/30):")
        for w in sorted(votes):
            try:
                witness = Witness(w, hive_instance=hive)
                rank_votes = int(witness["votes"]) / 1e12
                version = witness.get("running_version", "?")
                print(f"    @{w:20s} ({rank_votes:.1f}M VESTS, v{version})")
            except Exception:
                print(f"    @{w}")
    return votes

def get_top_witnesses(limit=30):
    """Get the top witnesses ranked by votes."""
    witnesses = WitnessesRankedByVote(limit=limit, hive_instance=hive)

    print(f"\n{'Rank':>4} {'Witness':20s} {'Votes (MVests)':>15} {'Version':>12} {'Missed':>7}")
    print("-" * 65)

    for i, w in enumerate(witnesses):
        name = w["owner"]
        votes = int(w["votes"]) / 1e12
        version = w.get("running_version", "?")
        missed = w.get("total_missed", 0)
        disabled = w["signing_key"] == "STM1111111111111111111111111111111114T1Anm"
        status = " (disabled)" if disabled else ""
        print(f"{i+1:>4} @{name:20s} {votes:>14.1f}M {version:>12} {missed:>7}{status}")

# View and manage votes
get_my_witness_votes(ACCOUNT)
get_top_witnesses(30)

# Vote for specific witnesses
# vote_for_witness("blocktrades", approve=True)
# vote_for_witness("badwitness", approve=False)  # unvote

# Or set a proxy to let someone else vote for you
# set_voting_proxy("trustedaccount")
# set_voting_proxy("")  # remove proxy
```

Key governance facts:
- Each account can vote for up to 30 witnesses
- Votes are weighted by Hive Power (not one-account-one-vote)
- Setting a proxy delegates both witness and DHF proposal votes
- The top 21 witnesses produce blocks; backup witnesses produce occasionally
- Witness votes do not expire -- review and update periodically
- Voting requires the active key
'''
    ),
    (
        "hive/proposal-voting",
        r'''How do I vote on DHF (Decentralized Hive Fund) proposals programmatically? Show how to approve and remove approval for proposals.''',
        r'''Voting on DHF proposals determines which projects receive funding from the community treasury. Here is how to manage proposal votes programmatically:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Update_proposal_votes
from beem.account import Account
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

ACCOUNT = "myaccount"

def vote_proposal(proposal_ids, approve=True):
    """Vote to approve or remove approval for proposals.

    Args:
        proposal_ids: List of proposal IDs to vote on
        approve: True to approve, False to remove approval
    """
    op = Update_proposal_votes(**{
        "voter": ACCOUNT,
        "proposal_ids": proposal_ids,
        "approve": approve,
        "extensions": []
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    action = "Approved" if approve else "Removed approval for"
    print(f"{action} proposals {proposal_ids}: {result['id']}")
    return result

def list_proposals_with_votes(status="votable", limit=50):
    """List proposals with vote counts and funding status."""
    result = hive.rpc.list_proposals(
        {
            "start": [""],
            "limit": limit,
            "order": "by_total_votes",
            "order_direction": "descending",
            "status": status
        },
        api="database_api"
    )
    proposals = result.get("proposals", [])

    # Find the return proposal threshold
    return_proposal_votes = 0
    for p in proposals:
        if p["id"] == 0:
            return_proposal_votes = int(p["total_votes"])
            break

    print(f"Return proposal threshold: {return_proposal_votes / 1e12:.1f}M VESTS\n")

    funded = []
    unfunded = []
    for p in proposals:
        votes = int(p["total_votes"])
        is_funded = votes > return_proposal_votes and p["id"] != 0
        entry = {
            "id": p["id"],
            "subject": p["subject"][:50],
            "creator": p["creator"],
            "daily_pay": p["daily_pay"],
            "votes_mvests": votes / 1e12,
            "funded": is_funded,
            "start": p["start_date"][:10],
            "end": p["end_date"][:10]
        }
        if is_funded:
            funded.append(entry)
        else:
            unfunded.append(entry)

    print("FUNDED proposals (above return proposal):")
    for p in funded:
        print(f"  #{p['id']:>4} {p['daily_pay']:>10} {p['votes_mvests']:>8.1f}M "
              f"@{p['creator']:16s} {p['subject']}")

    print(f"\nUNFUNDED proposals (below return proposal):")
    for p in unfunded[:10]:
        print(f"  #{p['id']:>4} {p['daily_pay']:>10} {p['votes_mvests']:>8.1f}M "
              f"@{p['creator']:16s} {p['subject']}")

    return funded, unfunded

def get_my_proposal_votes(account_name, limit=100):
    """Get which proposals an account has voted for."""
    result = hive.rpc.list_proposal_votes(
        {
            "start": [account_name],
            "limit": limit,
            "order": "by_voter_proposal",
            "order_direction": "ascending",
            "status": "votable"
        },
        api="database_api"
    )
    votes = result.get("proposal_votes", [])
    my_votes = [v for v in votes if v["voter"] == account_name]

    print(f"Proposal votes by @{account_name}:")
    for v in my_votes:
        pid = v["proposal"]["id"]
        subject = v["proposal"]["subject"][:50]
        print(f"  #{pid}: {subject}")

    return my_votes

# Usage
funded, unfunded = list_proposals_with_votes()
get_my_proposal_votes(ACCOUNT)

# Approve proposals
# vote_proposal([42, 43, 44], approve=True)

# Remove approval
# vote_proposal([42], approve=False)
```

How DHF funding works:
- Proposals are ranked by total vote weight (Hive Power of voters)
- The "return proposal" (ID 0) is a threshold -- proposals above it get funded
- Funding is paid daily in HBD from the @hive.fund treasury
- If the treasury cannot cover all funded proposals, they are paid in order of votes
- Votes can be added or removed at any time; rankings update immediately
- Setting a proxy (for witness voting) also proxies your proposal votes
'''
    ),
    (
        "hive/governance-chain-parameters",
        r'''What chain parameters do Hive witnesses vote on, and how do they affect the blockchain? How do I check current parameter values?''',
        r'''Hive witnesses collectively determine several critical chain parameters through their witness_update operations. The blockchain uses the median of all active witnesses' votes for each parameter.

```python
from beem import Hive
from beem.witness import Witness, WitnessesRankedByVote
from collections import Counter
import json

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

def get_chain_parameters():
    """Get current chain parameters and their meaning."""
    props = hive.rpc.get_dynamic_global_properties()
    config = hive.rpc.get_config(api="condenser_api")

    print("=== Current Chain Parameters ===\n")

    # Parameters set by witness votes
    params = {
        "HBD Interest Rate": {
            "value": f"{props.get('hbd_interest_rate', 0) / 100}%",
            "desc": "Annual interest rate on HBD savings",
            "set_by": "Witness median vote (hbd_interest_rate)"
        },
        "Account Creation Fee": {
            "value": "see witness props",
            "desc": "Minimum fee to create a new account",
            "set_by": "Witness median vote (account_creation_fee)"
        },
        "Maximum Block Size": {
            "value": f"{props.get('maximum_block_size', 65536)} bytes",
            "desc": "Maximum size of a single block",
            "set_by": "Witness median vote (maximum_block_size)"
        },
        "HBD Print Rate": {
            "value": f"{props.get('hbd_print_rate', 10000) / 100}%",
            "desc": "Percentage of rewards paid in HBD (vs HIVE)",
            "set_by": "Automatic based on HBD debt ratio"
        },
    }

    for name, info in params.items():
        print(f"{name}:")
        print(f"  Current: {info['value']}")
        print(f"  {info['desc']}")
        print(f"  Set by: {info['set_by']}")
        print()

    # Chain constants (not votable, set at hardfork level)
    constants = {
        "Block Interval": f"{config.get('HIVE_BLOCK_INTERVAL', 3)} seconds",
        "Max Witnesses": str(config.get("HIVE_MAX_WITNESSES", 21)),
        "Power Down Period": "3 days (since HF28)",
        "Cashout Window": f"{config.get('HIVE_CASHOUT_WINDOW_SECONDS', 604800) / 86400:.0f} days",
        "Max Vote Changes": str(config.get("HIVE_MAX_VOTE_CHANGES", 5)),
        "Reverse Auction Window": "0 seconds (since HF25)",
    }

    print("=== Chain Constants (hardfork-level) ===\n")
    for name, value in constants.items():
        print(f"  {name}: {value}")

    return props

def analyze_witness_parameter_votes():
    """Analyze how witnesses are voting on chain parameters."""
    witnesses = WitnessesRankedByVote(limit=50, hive_instance=hive)

    fees = []
    block_sizes = []
    interest_rates = []

    for w in witnesses:
        if w["signing_key"] == "STM1111111111111111111111111111111114T1Anm":
            continue  # Skip disabled witnesses
        props = w.get("props", {})
        fee_str = str(props.get("account_creation_fee", "3.000 HIVE"))
        fee = float(fee_str.split()[0])
        fees.append((w["owner"], fee))
        block_sizes.append((w["owner"], props.get("maximum_block_size", 65536)))
        interest_rates.append((w["owner"], props.get("hbd_interest_rate", 2000)))

    print("\n=== Witness Parameter Votes (Top 50) ===\n")

    # Account creation fee distribution
    fee_counter = Counter(f for _, f in fees)
    print("Account Creation Fee votes:")
    for fee, count in fee_counter.most_common():
        print(f"  {fee:.3f} HIVE: {count} witnesses")

    # Block size distribution
    size_counter = Counter(s for _, s in block_sizes)
    print("\nMax Block Size votes:")
    for size, count in size_counter.most_common():
        print(f"  {size} bytes: {count} witnesses")

    # HBD interest rate distribution
    rate_counter = Counter(r for _, r in interest_rates)
    print("\nHBD Interest Rate votes:")
    for rate, count in rate_counter.most_common():
        print(f"  {rate / 100}%: {count} witnesses")

    # Calculate medians (what the chain actually uses)
    sorted_fees = sorted(f for _, f in fees)
    sorted_rates = sorted(r for _, r in interest_rates)
    if sorted_fees:
        median_fee = sorted_fees[len(sorted_fees) // 2]
        print(f"\nMedian account creation fee: {median_fee:.3f} HIVE")
    if sorted_rates:
        median_rate = sorted_rates[len(sorted_rates) // 2]
        print(f"Median HBD interest rate: {median_rate / 100}%")

get_chain_parameters()
analyze_witness_parameter_votes()
```

The key governance mechanism is that the blockchain takes the median of all active top-21 witness votes for each parameter. This means any parameter change requires at least 11 of the 21 witnesses to adjust their votes. This makes the system resistant to sudden changes by a minority of witnesses. For protocol-level changes (hardforks), 17 of 21 witnesses must signal readiness.
'''
    ),
    (
        "hive/decentralized-governance-patterns",
        r'''What design patterns should I follow when building decentralized governance systems on Hive using custom_json?''',
        r'''Building decentralized governance on Hive leverages custom_json operations for proposals, voting, and execution. Here are proven patterns:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import hashlib
import time
from datetime import datetime, timedelta

GOVERNANCE_ID = "mygov"

class DAOGovernance:
    """On-chain governance system using custom_json operations."""

    def __init__(self, account, hive_instance):
        self.account = account
        self.hive = hive_instance

    def _broadcast(self, action, data, use_active=False):
        payload = {
            "app": f"{GOVERNANCE_ID}/1.0",
            "action": action,
            "data": data,
            "ts": int(time.time())
        }
        auth_key = "active" if use_active else "posting"
        auths = {
            "required_auths": [self.account] if use_active else [],
            "required_posting_auths": [] if use_active else [self.account],
            "id": GOVERNANCE_ID,
            "json": json.dumps(payload)
        }
        result = self.hive.custom_json(**auths)
        return result

    # Pattern 1: Proposal lifecycle
    def create_proposal(self, title, description, proposal_type,
                        voting_period_hours=168):
        """Create a governance proposal with time-bound voting."""
        proposal_id = hashlib.sha256(
            f"{self.account}{title}{time.time()}".encode()
        ).hexdigest()[:16]

        return self._broadcast("create_proposal", {
            "id": proposal_id,
            "title": title,
            "description": description,
            "type": proposal_type,
            "voting_ends": int(time.time()) + voting_period_hours * 3600,
            "quorum_pct": 10,  # 10% of token holders must vote
            "pass_threshold": 66,  # 66% approval needed
        })

    # Pattern 2: Stake-weighted voting
    def cast_vote(self, proposal_id, vote, weight=10000):
        """Cast a stake-weighted vote.

        In the backend, the vote weight is multiplied by the
        voter's token balance at the snapshot time.
        """
        return self._broadcast("vote", {
            "proposal_id": proposal_id,
            "vote": vote,  # "yes", "no", "abstain"
            "weight": weight  # 0-10000 (percentage in basis points)
        })

    # Pattern 3: Commit-reveal voting (for privacy)
    def commit_vote(self, proposal_id, secret_vote, salt):
        """Phase 1: Submit a hash of the vote (hidden)."""
        vote_hash = hashlib.sha256(
            f"{secret_vote}{salt}{self.account}".encode()
        ).hexdigest()

        return self._broadcast("commit_vote", {
            "proposal_id": proposal_id,
            "vote_hash": vote_hash
        })

    def reveal_vote(self, proposal_id, vote, salt):
        """Phase 2: Reveal the actual vote (after voting ends)."""
        return self._broadcast("reveal_vote", {
            "proposal_id": proposal_id,
            "vote": vote,
            "salt": salt
        })

    # Pattern 4: Multi-sig execution
    def propose_action(self, action_type, action_data, required_sigs=3):
        """Propose an action that requires multiple signers."""
        action_id = hashlib.sha256(
            json.dumps(action_data, sort_keys=True).encode()
        ).hexdigest()[:16]

        return self._broadcast("propose_action", {
            "action_id": action_id,
            "action_type": action_type,
            "action_data": action_data,
            "required_sigs": required_sigs,
            "expires": int(time.time()) + 7 * 86400
        })

    def sign_action(self, action_id):
        """Add your signature to a proposed action."""
        return self._broadcast("sign_action", {
            "action_id": action_id
        })

    # Pattern 5: Delegation and proxy
    def delegate_vote(self, delegate_to):
        """Delegate your voting power to another account."""
        return self._broadcast("delegate_vote", {
            "delegate": delegate_to
        })

    def remove_delegation(self):
        """Remove vote delegation."""
        return self._broadcast("undelegate_vote", {})


# Backend: Process governance operations
class GovernanceEngine:
    """Replay custom_json to build governance state."""

    def __init__(self):
        self.proposals = {}
        self.votes = {}
        self.delegations = {}

    def process_op(self, account, data):
        action = data["action"]
        payload = data["data"]

        if action == "create_proposal":
            self.proposals[payload["id"]] = {
                "creator": account,
                "title": payload["title"],
                "voting_ends": payload["voting_ends"],
                "votes_for": 0,
                "votes_against": 0,
                "status": "active"
            }
        elif action == "vote":
            pid = payload["proposal_id"]
            if pid in self.proposals:
                self.votes.setdefault(pid, {})[account] = payload["vote"]

    def tally_results(self, proposal_id, get_balance_fn):
        """Tally votes weighted by token balance."""
        votes = self.votes.get(proposal_id, {})
        total_for = 0
        total_against = 0
        for voter, vote in votes.items():
            # Check for delegation
            effective_voter = self.delegations.get(voter, voter)
            balance = get_balance_fn(effective_voter)
            if vote == "yes":
                total_for += balance
            elif vote == "no":
                total_against += balance
        return total_for, total_against

# Usage
hive = Hive(node=["https://api.hive.blog"], keys=["5PostingKey"])
gov = DAOGovernance("myaccount", hive)
# gov.create_proposal("Upgrade Token Contract", "Details...", "upgrade")
# gov.cast_vote("abc123", "yes", weight=10000)
```

These patterns -- time-bound proposals, stake-weighted voting, commit-reveal, multi-sig execution, and delegation -- form the building blocks for any decentralized governance system on Hive. All state is derived by replaying custom_json operations, making it fully verifiable and auditable.
'''
    ),
]
