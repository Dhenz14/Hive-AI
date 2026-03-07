"""Hive economics training pairs (part 2b): dust threshold, downvotes, dashboards."""

PAIRS = [
    (
        "hive_economics/dust-threshold-minimum-payout",
        r'''What is the dust threshold on Hive and how can I check if a post will receive a payout?''',
        r'''<think>
The dust threshold on Hive is the minimum pending payout below which rewards are
forfeited entirely -- both author and curator rewards return to the reward pool.
The threshold is defined in terms of rshares, not HBD directly. The chain constant
HIVE_VOTE_DUST_THRESHOLD is currently set to about 50M rshares, which translates
to roughly 0.02 HBD depending on the reward fund balance and price feed. This
particularly affects comments (which get fewer votes) and new users with low HP.
To check properly, I should convert rshares to HBD using the reward fund ratio,
not just rely on pending_payout_value which can lag.
</think>

The dust threshold is the minimum reward below which a post/comment receives **zero payout** -- the rewards return to the pool instead.

```python
from beem import Hive
from beem.comment import Comment
import requests

DUST_THRESHOLD_RSHARES = 50_000_000  # ~50M rshares (chain constant)

def get_reward_fund_ratio():
    """Get current rshares-to-HBD conversion ratio."""
    resp = requests.post("https://api.hive.blog", json={
        "jsonrpc": "2.0", "method": "condenser_api.get_reward_fund",
        "params": ["post"], "id": 1
    }).json()["result"]
    reward_balance = float(resp["reward_balance"].split()[0])
    recent_claims = int(resp["recent_claims"])
    h = Hive()
    price = float(h.get_median_price())
    return (reward_balance / recent_claims) * price  # HBD per rshare

def check_dust(author, permlink):
    """Check if a post will clear the dust threshold."""
    c = Comment(f"@{author}/{permlink}")
    pending = float(c["pending_payout_value"].amount)
    net_rshares = int(c["net_rshares"])
    ratio = get_reward_fund_ratio()
    dust_hbd = DUST_THRESHOLD_RSHARES * ratio

    print(f"Post: @{author}/{permlink}")
    print(f"  Pending payout: {pending:.3f} HBD")
    print(f"  Net rshares: {net_rshares:,}")
    print(f"  Dust threshold: ~{dust_hbd:.4f} HBD ({DUST_THRESHOLD_RSHARES:,} rshares)")
    if net_rshares < DUST_THRESHOLD_RSHARES:
        print(f"  STATUS: BELOW DUST -- will receive $0.000 at payout")
    else:
        print(f"  STATUS: Above dust -- will pay out normally")
    return net_rshares >= DUST_THRESHOLD_RSHARES

check_dust("alice", "my-post-permlink")
```

Key points:
- Dust threshold is **~0.02 HBD** but varies with reward fund state
- Comments are most vulnerable -- a single small vote often isn't enough
- Both author AND curator rewards are lost (returned to pool)
- Self-voting below dust is a net loss (you spend voting mana for nothing)
- Strategy: consolidate votes on fewer posts rather than spreading thin'''
    ),
    (
        "hive_economics/comment-vs-post-reward-economics",
        r'''How do comment rewards differ from post rewards on Hive? Show me how to compare them.''',
        r'''<think>
Posts and comments share the same reward pool but behave differently in
practice. Comments typically earn less, have no beneficiary splits by default,
and are more susceptible to dust. The reward split (author/curator) is the
same 50/50 rule. I'll query recent activity for a user and compare average
post vs comment rewards to illustrate the economics.
</think>

```python
from beem.account import Account

def compare_rewards(username, limit=50):
    acc = Account(username)
    posts, comments = [], []
    for entry in acc.history_reverse(only_ops=["author_reward"], batch_size=200):
        bucket = comments if entry["permlink"].startswith("re-") else posts
        bucket.append(float(entry["hbd_payout"].amount) + float(entry["vesting_payout"].amount))
        if len(posts) + len(comments) >= limit:
            break
    avg_p = sum(posts) / max(len(posts), 1)
    avg_c = sum(comments) / max(len(comments), 1)
    print(f"Posts  — count: {len(posts)}, avg reward: {avg_p:.3f}")
    print(f"Comments — count: {len(comments)}, avg reward: {avg_c:.3f}")
    print(f"Post/Comment ratio: {avg_p / max(avg_c, 0.001):.1f}x")

compare_rewards("alice")
```

Comments typically earn 5-20x less than posts. Many fall below dust threshold, making strategic commenting important for ROI.'''
    ),
    (
        "hive_economics/multi-voter-reward-simulation",
        r'''Simulate how curation rewards are split among multiple voters on a Hive post. I want to understand early vs late voting.''',
        r'''<think>
Hive curation uses a weight-squared model where earlier voters get more
curation reward. Each vote's curation share is proportional to its rshares
relative to total rshares, but early voters benefit from the curve. The
first 24h window matters most. I'll simulate multiple voters at different
times with different HP and show the reward split. The curve is linear
now (post-HF25), so share = voter_rshares / total_rshares.
</think>

```python
def simulate_curation(voters, total_post_reward_hbd=10.0):
    """voters: list of (name, rshares, minute_voted)"""
    curation_pool = total_post_reward_hbd * 0.5  # 50% to curators
    cumulative = 0
    results = []
    for name, rshares, minute in sorted(voters, key=lambda v: v[2]):
        # Linear curve (HF25+): share proportional to sqrt contribution
        weight = rshares
        cumulative += weight
        results.append((name, weight, minute))

    total_weight = sum(r[1] for r in results)
    print(f"{'Voter':<10} {'Share':>8} {'Reward':>10} {'Minute':>6}")
    for name, weight, minute in results:
        share = weight / total_weight
        reward = share * curation_pool
        print(f"{name:<10} {share:>7.1%} {reward:>9.3f}  {minute:>5}m")

voters = [
    ("early1", 5000, 1), ("early2", 3000, 3),
    ("mid1", 8000, 30), ("late1", 2000, 120),
]
simulate_curation(voters, total_post_reward_hbd=20.0)
```

Larger stakes dominate, but voting early on quality content before whales is the key curation strategy.'''
    ),
    (
        "hive_economics/downvote-pool-mechanics",
        r'''Explain the Hive downvote pool. How much free downvote mana do I have and how does it regenerate?''',
        r'''<think>
Hive gives each account a separate downvote mana pool equal to 25% of their
upvote mana. Downvotes from this pool don't consume upvote mana. Once the
downvote pool is depleted, further downvotes draw from regular voting mana.
Regeneration follows the same 5-day full recharge rate. I'll show how to
query current downvote mana percentage.
</think>

```python
from beem.account import Account
from beem.utils import reputation_to_score
import time

def downvote_status(username):
    acc = Account(username)
    dv = acc.json()["downvote_manabar"]
    last = int(dv["last_update_time"])
    current = int(dv["current_mana"])
    max_mana = acc.get_voting_power_resource()  # approximate
    # Regenerate: 5 days = 432000 seconds for full recharge
    elapsed = time.time() - last
    regen = elapsed / 432000
    pct = min((current / max(max_mana * 0.25, 1)) + regen, 1.0) * 100
    print(f"@{username} downvote mana: ~{pct:.1f}%")
    print(f"Free downvotes: 25% of upvote pool")
    print(f"Full recharge: 5 days (same as upvote mana)")

downvote_status("alice")
```

The 25% free downvote pool (HF21) encourages policing abuse without sacrificing curation income.'''
    ),
    (
        "hive_economics/content-discovery-trending-algorithm",
        r'''How does Hive's trending algorithm work? Can I calculate a post's trending score?''',
        r'''<think>
Hive trending is based on pending payout (rshares converted to HBD) with
a time-decay component. Higher-paying posts trend higher. The algorithm
is simpler than Reddit's — it's primarily reward-weighted, not
engagement-weighted. Promoted posts use a burn mechanism. I'll show how
to approximate trending scores and fetch current trending.
</think>

```python
from beem.discussions import Query, Discussions_by_trending
import math, time

def trending_score(pending_payout_hbd, created_timestamp):
    """Approximate Hive trending: reward-dominant, slight time bonus."""
    age_hours = (time.time() - created_timestamp) / 3600
    # Higher payout = higher trend; newer posts get slight boost
    score = math.log10(max(pending_payout_hbd, 0.001)) - (age_hours / 168)
    return score

def fetch_trending(tag="hive", limit=5):
    q = Query(tag=tag, limit=limit)
    posts = Discussions_by_trending(q)
    print(f"{'Author':<16} {'Pending':>8} {'Votes':>5} Title")
    for p in posts:
        pend = float(p["pending_payout_value"].amount)
        votes = p["net_votes"]
        title = p["title"][:40]
        print(f"{p['author']:<16} {pend:>7.2f}$ {votes:>5} {title}")

fetch_trending("hive", limit=10)
```

Trending is essentially a leaderboard by pending payout. Whale votes dominate visibility, which is why community curation initiatives exist.'''
    ),
    (
        "hive_economics/account-value-calculator",
        r'''Build a function that calculates total account value on Hive including all asset types (HIVE, HBD, HP, savings).''',
        r'''<think>
Total account value must include: liquid HIVE, liquid HBD, HIVE Power
(vesting shares converted to HIVE), HBD in savings, HIVE in savings,
and any pending HBD interest. Need to convert everything to USD using
the HIVE market price. Vesting shares to HP conversion uses the
global dynamic properties total_vesting_fund / total_vesting_shares ratio.
</think>

```python
from beem import Hive
from beem.account import Account

def account_value(username):
    h = Hive()
    acc = Account(username, blockchain_instance=h)
    props = h.get_dynamic_global_properties()
    tvf = float(props["total_vesting_fund_hive"].amount)
    tvs = float(props["total_vesting_shares"].amount)
    vests_to_hive = tvf / tvs

    bal = {
        "liquid_hive": float(acc["balance"].amount),
        "liquid_hbd": float(acc["hbd_balance"].amount),
        "hp_hive": float(acc["vesting_shares"].amount) * vests_to_hive,
        "savings_hive": float(acc["savings_balance"].amount),
        "savings_hbd": float(acc["savings_hbd_balance"].amount),
    }
    total_hive = bal["liquid_hive"] + bal["hp_hive"] + bal["savings_hive"]
    total_hbd = bal["liquid_hbd"] + bal["savings_hbd"]
    # Use internal median price for USD estimate
    price = float(h.get_median_price())
    total_usd = total_hive * price + total_hbd
    for k, v in bal.items():
        print(f"  {k}: {v:.3f}")
    print(f"  Total: ~${total_usd:.2f} USD")
    return total_usd

account_value("alice")
```'''
    ),
    (
        "hive_economics/historical-reward-data-analysis",
        r'''How can I analyze historical author reward trends on Hive over time to find earning patterns?''',
        r'''<think>
Author rewards are recorded as `author_reward` operations in account
history. I need to iterate history, extract HBD and vesting payouts,
bucket them by week or month, and show trends. This helps creators
understand which periods or content types earned most. The vesting
payout needs conversion to HIVE equivalent for accurate totals.
</think>

```python
from beem.account import Account
from collections import defaultdict
from datetime import datetime

def reward_trends(username, months=3):
    acc = Account(username)
    monthly = defaultdict(lambda: {"hbd": 0.0, "hp": 0.0, "count": 0})
    for op in acc.history_reverse(only_ops=["author_reward"], batch_size=500):
        ts = datetime.strptime(op["timestamp"], "%Y-%m-%dT%H:%M:%S")
        cutoff = datetime.utcnow().replace(day=1)
        for _ in range(months):
            cutoff = cutoff.replace(month=cutoff.month - 1 if cutoff.month > 1 else 12,
                                     year=cutoff.year if cutoff.month > 1 else cutoff.year - 1)
        if ts < cutoff:
            break
        key = ts.strftime("%Y-%m")
        monthly[key]["hbd"] += float(op["hbd_payout"].amount)
        monthly[key]["hp"] += float(op["vesting_payout"].amount)
        monthly[key]["count"] += 1

    print(f"{'Month':<10} {'Posts':>5} {'HBD':>8} {'HP(vests)':>10}")
    for m in sorted(monthly):
        d = monthly[m]
        print(f"{m:<10} {d['count']:>5} {d['hbd']:>8.2f} {d['hp']:>10.2f}")

reward_trends("alice", months=6)
```

Tracking monthly trends reveals seasonal patterns and helps optimize posting frequency and timing.'''
    ),
    (
        "hive_economics/witness-vote-decay",
        r'''How does witness vote decay work on Hive? Show me how to calculate decayed vote weight for a witness.''',
        r'''<think>
Witness votes on Hive decay over time if the voter doesn't update their
votes. Governance vote expiration was introduced to prevent stale votes
from indefinitely securing witness positions. Votes expire after ~1 year
if not refreshed. The decay is binary (active or expired), not gradual.
Accounts must re-vote periodically to keep their witness votes active.
I'll show how to check vote freshness.
</think>

```python
from beem.account import Account
from beem.witness import Witness
from datetime import datetime, timedelta

GOVERNANCE_VOTE_EXPIRY_DAYS = 365

def witness_vote_health(username):
    acc = Account(username)
    last_vote = datetime.strptime(acc["governance_vote_expiration_ts"],
                                   "%Y-%m-%dT%H:%M:%S")
    now = datetime.utcnow()
    days_left = (last_vote - now).days
    expired = days_left <= 0
    print(f"@{username} witness vote status:")
    print(f"  Expires: {last_vote.strftime('%Y-%m-%d')}")
    print(f"  Days remaining: {max(days_left, 0)}")
    print(f"  Status: {'EXPIRED - votes inactive!' if expired else 'Active'}")
    if days_left < 30 and not expired:
        print(f"  WARNING: Expiring soon, re-vote to refresh!")
    return not expired

def witness_voter_analysis(witness_name, limit=20):
    w = Witness(witness_name)
    print(f"Witness @{witness_name} — votes: {w['votes']}")
    # Top voters by HP would require iterating all voter accounts

witness_vote_health("alice")
```

Voters must refresh witness votes annually. Expired votes don't count, which keeps governance active and prevents zombie consensus.'''
    ),
    (
        "hive_economics/recurrent-transfer-economics",
        r'''How do recurrent transfers work on Hive and what are their economic use cases?''',
        r'''<think>
Recurrent transfers (HF25) let users schedule automatic repeated payments
in HIVE or HBD. They specify amount, recipient, interval (hours), and
number of executions. Use cases: subscriptions, salary payments, DCA
strategies, recurring donations. Each execution is a normal transfer
that hits the blockchain automatically. I'll show how to set one up
and list active recurrent transfers.
</think>

```python
from beem import Hive
from beem.account import Account

def setup_recurrent_transfer(sender, recipient, amount, asset,
                              recurrence_hours, executions):
    """Create a recurring payment schedule."""
    h = Hive(keys=["active_key_here"])
    op = h.recurrent_transfer(
        sender, recipient, f"{amount:.3f} {asset}",
        recurrence=recurrence_hours, executions=executions
    )
    cost_total = amount * executions
    print(f"Scheduled: {amount} {asset} every {recurrence_hours}h")
    print(f"Total commitment: {cost_total:.3f} {asset} over "
          f"{recurrence_hours * executions / 24:.0f} days")
    return op

def list_recurrent(username):
    acc = Account(username)
    transfers = acc.get_recurrent_transfers()
    print(f"Active recurrent transfers for @{username}:")
    for t in transfers:
        print(f"  -> @{t['to']}: {t['amount']} every {t['recurrence']}h "
              f"({t['remaining_executions']} left)")

# Example: DCA 10 HIVE weekly to savings account
# setup_recurrent_transfer("alice", "bob", 10.0, "HIVE", 168, 52)
list_recurrent("alice")
```

Recurrent transfers enable DCA strategies and subscription models natively on-chain without smart contracts.'''
    ),
    (
        "hive_economics/savings-withdrawal-timing",
        r'''What's the optimal strategy for Hive savings withdrawals given the 3-day delay? Show the timing math.''',
        r'''<think>
Hive savings have a 3-day (72-hour) withdrawal delay for security. HBD
in savings earns ~20% APR interest. Strategy involves balancing liquidity
needs against interest earnings. Multiple staggered withdrawals can
create a rolling liquidity pipeline. I need to show the interest
calculation and a staggering strategy for regular cash flow.
</think>

```python
from datetime import datetime, timedelta

HBD_SAVINGS_APR = 0.20  # 20% APR (check current rate)
WITHDRAWAL_DELAY_DAYS = 3

def savings_interest(principal_hbd, days):
    """HBD savings interest (compounds monthly on-chain)."""
    daily_rate = HBD_SAVINGS_APR / 365
    earned = principal_hbd * daily_rate * days
    return earned

def staggered_withdrawal_plan(total_hbd, num_tranches, interval_days=7):
    """Plan staggered withdrawals for rolling liquidity."""
    per_tranche = total_hbd / num_tranches
    print(f"Staggered withdrawal: {total_hbd} HBD in {num_tranches} tranches")
    print(f"{'Tranche':<10} {'Initiate':<14} {'Available':<14} {'Interest Lost':<14}")
    now = datetime.utcnow()
    total_lost = 0
    for i in range(num_tranches):
        init = now + timedelta(days=i * interval_days)
        avail = init + timedelta(days=WITHDRAWAL_DELAY_DAYS)
        # Interest lost = what this tranche would have earned if kept
        remaining_days = (num_tranches - i) * interval_days
        lost = savings_interest(per_tranche, remaining_days)
        total_lost += lost
        print(f"  #{i+1:<6} {init.strftime('%Y-%m-%d'):<14} "
              f"{avail.strftime('%Y-%m-%d'):<14} {lost:>8.2f} HBD")
    print(f"Total interest cost of early withdrawal: {total_lost:.2f} HBD")

staggered_withdrawal_plan(1000, num_tranches=4, interval_days=7)
```

Keep as much HBD in savings as possible for the 20% APR. Use staggered withdrawals to maintain liquidity without pulling everything at once.'''
    ),
    (
        "hive_economics/token-distribution-top-holders",
        r'''How can I analyze HIVE token distribution and find the top holders to understand wealth concentration?''',
        r'''<think>
Analyzing token distribution requires querying accounts sorted by vesting
shares (HP). The Gini coefficient or top-N concentration ratios reveal
wealth distribution. Beem can fetch richlist data. I should calculate
concentration metrics: top 10/100 holder share, and a basic Gini
approximation. This is expert-level economic analysis of the chain.
</think>

```python
from beem import Hive
import requests

def top_holders_analysis(limit=100):
    """Analyze HP distribution among top accounts."""
    # Use condenser API for ranked accounts
    h = Hive()
    props = h.get_dynamic_global_properties()
    tvf = float(props["total_vesting_fund_hive"].amount)
    tvs = float(props["total_vesting_shares"].amount)
    ratio = tvf / tvs

    resp = requests.post("https://api.hive.blog", json={
        "jsonrpc": "2.0", "method": "condenser_api.lookup_accounts",
        "params": ["", limit], "id": 1
    }).json()
    names = resp["result"]

    balances = []
    for name in names[:limit]:
        r = requests.post("https://api.hive.blog", json={
            "jsonrpc": "2.0", "method": "condenser_api.get_accounts",
            "params": [[name]], "id": 1
        }).json()
        acc = r["result"][0]
        hp = float(acc["vesting_shares"].split()[0]) * ratio
        balances.append((name, hp))

    balances.sort(key=lambda x: -x[1])
    total_hp = sum(b[1] for b in balances)
    top10 = sum(b[1] for b in balances[:10])
    print(f"Top {limit} holders: {total_hp:,.0f} HP total")
    print(f"Top 10 concentration: {top10/total_hp*100:.1f}%")
    for name, hp in balances[:10]:
        print(f"  @{name}: {hp:,.0f} HP ({hp/total_hp*100:.1f}%)")

top_holders_analysis(100)
```

High concentration in top accounts is typical for DPoS chains. Tracking distribution over time reveals whether stake is decentralizing.'''
    ),
    (
        "hive_economics/economic-dashboard-realtime",
        r'''Build a real-time Hive economic dashboard that shows key chain metrics: supply, inflation, reward pool, HBD debt ratio.''',
        r'''<think>
A Hive economic dashboard needs: current/virtual supply, HBD print rate,
reward fund balance, HBD debt ratio (must stay under 10% haircut rule),
median price feed, and inflation rate (~0.97% annually, decreasing 0.01%
per 250k blocks). These come from dynamic global properties and reward
fund API calls. The HBD debt ratio is critical for chain health.
</think>

```python
from beem import Hive
import requests, json

def hive_dashboard():
    h = Hive()
    props = h.get_dynamic_global_properties()
    rf = requests.post("https://api.hive.blog", json={
        "jsonrpc": "2.0", "method": "condenser_api.get_reward_fund",
        "params": ["post"], "id": 1
    }).json()["result"]

    supply = float(props["current_supply"].amount)
    virtual = float(props["virtual_supply"].amount)
    hbd_supply = float(props["current_hbd_supply"].amount)
    hbd_print = props.get("hbd_print_rate", 10000) / 100
    reward_balance = float(rf["reward_balance"].split()[0])
    median = float(h.get_median_price())

    # HBD debt ratio: hbd_supply * feed_price / virtual_supply
    debt_ratio = (hbd_supply / median / virtual) * 100 if median > 0 else 0
    # Inflation: starts 0.978%, decreases 0.01% every 250k blocks
    head_block = props["head_block_number"]
    inflation = max(0.978 - (head_block // 250000) * 0.01, 0.095)

    print("=== HIVE ECONOMIC DASHBOARD ===")
    print(f"  HIVE Supply:     {supply:>14,.0f}")
    print(f"  Virtual Supply:  {virtual:>14,.0f}")
    print(f"  HBD Supply:      {hbd_supply:>14,.0f}")
    print(f"  HBD Print Rate:  {hbd_print:>13.1f}%")
    print(f"  HBD Debt Ratio:  {debt_ratio:>13.2f}% (haircut at 10%)")
    print(f"  Reward Pool:     {reward_balance:>14,.0f} HIVE")
    print(f"  Median Price:    ${median:>13.3f}")
    print(f"  Inflation Rate:  {inflation:>13.3f}%")
    print(f"  Head Block:      {head_block:>14,}")

hive_dashboard()
```

The HBD debt ratio is the most critical metric. If it exceeds 10%, HBD printing stops (haircut) to protect the peg. Monitor this alongside the print rate for chain health.'''
    ),
]
