"""Hive economics training pairs (part 1): reward pool, HBD, vesting, inflation."""

PAIRS = [
    (
        "hive_economics/reward-pool-mechanics",
        r'''How does the Hive reward pool work? I want to understand where post rewards come from and how the pool is replenished.''',
        r'''<think>
The Hive reward pool is funded by inflation. Each block generates new HIVE tokens,
a portion of which flows into the reward fund. The "recent claims" value tracks
total rshares claimed, and the "reward balance" is the pending HIVE available.
A post's payout is proportional to its rshares relative to recent_claims.
The pool continuously refills every block (~3 seconds) so it never fully depletes.
I should show how to query the reward fund and calculate a pending payout estimate.
</think>

The reward pool is a continuously replenished fund of HIVE that pays out content creators and curators. Here's how to query and estimate payouts:

```python
from beem import Hive
from beem.account import Account

hive = Hive()

# Query the reward fund
reward_fund = hive.get_reward_funds()[0]  # "post" fund
reward_balance = float(reward_fund["reward_balance"].split()[0])
recent_claims = int(reward_fund["recent_claims"])

# Get the current median price feed
price_feed = hive.get_current_median_history()
base = float(price_feed["base"].split()[0])       # HBD per HIVE
quote = float(price_feed["quote"].split()[0])      # typically 1.000 HIVE

hbd_per_hive = base / quote

def estimate_payout(rshares: int) -> dict:
    """Estimate pending payout from a post's net rshares."""
    # Each post's share of the pool
    hive_payout = (rshares / recent_claims) * reward_balance
    hbd_value = hive_payout * hbd_per_hive

    # 50/50 split: half to author, half to curators
    return {
        "total_hive": round(hive_payout, 3),
        "total_hbd_value": round(hbd_value, 3),
        "author_share_hbd": round(hbd_value / 2, 3),
        "curator_share_hbd": round(hbd_value / 2, 3),
    }

# Example: a post with 50 billion rshares
print(estimate_payout(50_000_000_000))
print(f"Reward balance: {reward_balance:.3f} HIVE")
print(f"Recent claims:  {recent_claims}")
```

Key mechanics:
- **Inflation feeds the pool** every block (~3 sec), so `reward_balance` is always replenishing.
- **recent_claims** is a rolling sum of all rshares claimed in the recent window — it acts as the denominator.
- A post's payout = `(post_rshares / recent_claims) * reward_balance`.
- The pool is shared across all posts in their 7-day payout window.'''
    ),
    (
        "hive_economics/author-curation-reward-split",
        r'''Can you explain the 50/50 author/curation split on Hive? How exactly are author rewards and curation rewards divided?''',
        r'''<think>
After HF25 (June 2021), Hive uses a fixed 50/50 split between author and curators.
The author's half can be taken as 50% HBD + 50% HP, or 100% HP (author choice).
Curation rewards are always paid in HP (VESTS). Beneficiaries come out of the
author's portion. If an author sets 10% beneficiary, the author gets 40% of total
and the beneficiary gets 10%. The curation half is distributed to voters
proportional to their rshares and timing. I should demonstrate the math.
</think>

Since HF25, Hive enforces a **fixed 50/50 split** — half to the author, half to curators. Here's the breakdown:

```python
def calculate_reward_split(total_payout_hbd: float,
                           author_hbd_percent: int = 50,
                           beneficiaries: list[dict] = None):
    """
    Calculate author vs curation reward split.

    Args:
        total_payout_hbd: Total post payout in HBD value.
        author_hbd_percent: Author's choice — 50 (default) or 0 (100% power up).
        beneficiaries: List of {"account": str, "weight": int} (weight in bp, 10000=100%).
    """
    beneficiaries = beneficiaries or []

    curation_total = total_payout_hbd * 0.50  # always 50%
    author_total = total_payout_hbd * 0.50

    # Beneficiaries come out of the author's share
    beneficiary_payouts = {}
    for b in beneficiaries:
        pct = b["weight"] / 10000
        amount = author_total * pct
        beneficiary_payouts[b["account"]] = round(amount, 3)

    author_after_bene = author_total - sum(beneficiary_payouts.values())

    # Author chooses HBD vs HP split for their remaining share
    author_hbd = author_after_bene * (author_hbd_percent / 100)
    author_hp = author_after_bene - author_hbd

    return {
        "curation_rewards_hp": round(curation_total, 3),
        "author_hbd": round(author_hbd, 3),
        "author_hp": round(author_hp, 3),
        "beneficiaries": beneficiary_payouts,
    }

# Post worth 10 HBD, default 50/50, one beneficiary at 5%
result = calculate_reward_split(
    total_payout_hbd=10.0,
    author_hbd_percent=50,
    beneficiaries=[{"account": "hive.fund", "weight": 500}]
)
print(result)
# {'curation_rewards_hp': 5.0, 'author_hbd': 2.375, 'author_hp': 2.375, 'beneficiaries': {'hive.fund': 0.25}}
```

- **Curation (50%)**: Distributed as HP to voters based on their vote rshares and timing.
- **Author (50%)**: Split between HBD and HP per author preference; beneficiaries deducted first.
- **Beneficiaries**: Taken from the author half only — curators are unaffected.'''
    ),
    (
        "hive_economics/curation-reward-timing-window",
        r'''How does the curation reward timing window work on Hive? I heard voting early gets you more curation rewards.''',
        r'''<think>
After HF25, the early-vote penalty was removed entirely. Before HF25, there was
a 5-minute window where curation rewards were partially burned. Now on Hive,
all votes within the 7-day window receive curation proportional to their rshares.
The order still matters though — earlier voters with the same stake get slightly
more because curation is distributed in a "first come, better ratio" curve.
The convergent-linear curve means the first voters on a post that later becomes
popular earn more per rshares than latecomers. I'll demonstrate the math.
</think>

Since **HF25**, the early-vote penalty (formerly 5 minutes) was **removed**. However, vote order still matters because of how curation rewards are distributed:

```python
def simulate_curation_distribution(votes: list[dict], total_curation_hbd: float):
    """
    Simulate curation reward distribution among voters.

    Curation uses a square-root-weighted first-come model:
    each voter's curation weight = sqrt(cumulative_rshares_after) - sqrt(cumulative_rshares_before)

    Args:
        votes: List of {"voter": str, "rshares": int} in chronological order.
        total_curation_hbd: Total HBD-equivalent curation pool for this post.
    """
    import math

    cumulative = 0
    curation_weights = []

    for v in votes:
        before = cumulative
        cumulative += v["rshares"]
        weight = math.sqrt(cumulative) - math.sqrt(before)
        curation_weights.append({
            "voter": v["voter"],
            "rshares": v["rshares"],
            "weight": weight,
        })

    total_weight = sum(c["weight"] for c in curation_weights)

    results = []
    for c in curation_weights:
        share = (c["weight"] / total_weight) * total_curation_hbd
        results.append({
            "voter": c["voter"],
            "rshares": c["rshares"],
            "curation_hbd": round(share, 4),
            "pct_of_pool": round(c["weight"] / total_weight * 100, 2),
        })
    return results

votes = [
    {"voter": "alice", "rshares": 1_000_000_000},   # votes first
    {"voter": "bob",   "rshares": 1_000_000_000},   # same stake, votes second
    {"voter": "carol", "rshares": 5_000_000_000},   # big vote, votes last
]

for r in simulate_curation_distribution(votes, total_curation_hbd=5.0):
    print(r)
# alice gets a larger share per rshares than bob (earlier), carol brings
# the most rshares but the sqrt curve reduces her per-rshare reward.
```

Key points:
- **No time penalty** post-HF25 — vote at 1 second or 6 days, no curation is burned.
- **Earlier voters earn more per rshares** due to the `sqrt(cumulative)` weighting.
- This incentivizes discovering good content early rather than piling onto trending posts.'''
    ),
    (
        "hive_economics/comment-reward-curves",
        r'''What reward curves does Hive use for posts and comments? How do linear vs convergent-linear curves work?''',
        r'''<think>
Hive currently uses the convergent-linear reward curve (since HF25). The formula
is: reward = rshares^2 / (rshares + 2*s) where s is a constant from the reward
fund's "content_constant". This means small posts get almost linear rewards, but
very large posts see diminishing returns. Before this, HF17-HF24 used plain linear.
The convergent-linear curve discourages stake concentration on single posts and
spreads rewards more broadly. I'll show both curves for comparison.
</think>

Hive uses the **convergent-linear** reward curve (since HF25). Here's how it compares to plain linear:

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

def linear_reward(rshares: np.ndarray) -> np.ndarray:
    """Pre-HF25 linear curve: reward proportional to rshares."""
    return rshares

def convergent_linear_reward(rshares: np.ndarray, content_constant: float) -> np.ndarray:
    """
    HF25+ convergent-linear curve.
    reward = rshares^2 / (rshares + 2 * content_constant)

    - Small rshares: behaves ~linearly (rshares << 2*s, so ≈ rshares^2 / 2s)
    - Large rshares: converges toward rshares (diminishing marginal return)
    """
    s = content_constant
    return (rshares * rshares) / (rshares + 2 * s)

# content_constant from reward fund (typical value ~2e12)
CONTENT_CONSTANT = 2_000_000_000_000

rshares = np.linspace(0, 50_000_000_000_000, 1000)

linear = linear_reward(rshares)
convergent = convergent_linear_reward(rshares, CONTENT_CONSTANT)

fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(rshares / 1e12, linear / 1e12, label="Linear (pre-HF25)", linestyle="--")
ax.plot(rshares / 1e12, convergent / 1e12, label="Convergent-Linear (HF25+)")
ax.set_xlabel("Net rshares (trillions)")
ax.set_ylabel("Reward weight (trillions)")
ax.set_title("Hive Reward Curves Comparison")
ax.legend()
ax.grid(True, alpha=0.3)
fig.savefig("reward_curves.png", dpi=100)
print("Saved reward_curves.png")

# Show the diminishing returns effect
for rs in [1e9, 1e10, 1e11, 1e12, 1e13]:
    cl = convergent_linear_reward(np.array([rs]), CONTENT_CONSTANT)[0]
    efficiency = cl / rs * 100
    print(f"rshares={rs:.0e}  reward_weight={cl:.2e}  efficiency={efficiency:.1f}%")
```

The convergent-linear curve:
- **Small posts**: Near-linear scaling, so minnow votes still matter.
- **Whale-dominated posts**: Diminishing returns — adding more rshares yields less reward per unit.
- **Effect**: Distributes rewards more broadly across many posts rather than concentrating on a few.'''
    ),
    (
        "hive_economics/hbd-stabilizer-mechanism",
        r'''How does the HBD stabilizer work on Hive? What keeps HBD pegged to $1 USD?''',
        r'''<think>
The HBD stabilizer is a DHF-funded bot (run via the @hbdstabilizer account) that
performs market operations. When HBD trades above $1 on the internal market, the
stabilizer sells HBD for HIVE (pushing HBD price down). When below $1, it buys HBD
with HIVE. The protocol also has a built-in conversion mechanism: you can convert
HBD to HIVE (3.5 days) at the feed price, creating a $1 floor. The haircut rule
limits HBD supply to 30% of market cap. Together these create a soft peg.
I'll show how to monitor the stabilizer and the conversion arbitrage math.
</think>

HBD's $1 peg is maintained by **three mechanisms**: protocol conversions, the HBD stabilizer bot, and the haircut rule.

```python
from beem import Hive
from beem.market import Market

hive = Hive()
market = Market(blockchain_instance=hive)

# 1. Check current internal market price of HBD
ticker = market.ticker()
hbd_price = float(ticker["latest"])
print(f"Internal market HBD price: ${hbd_price:.4f}")

# 2. Stabilizer arbitrage logic
def stabilizer_action(hbd_market_price: float, tolerance: float = 0.01):
    """
    Simplified HBD stabilizer logic (@hbdstabilizer DHF proposal).

    - Above $1 + tolerance: sell HBD for HIVE on internal market
    - Below $1 - tolerance: buy HBD with HIVE on internal market
    - Profits returned to DHF, creating a virtuous funding loop
    """
    if hbd_market_price > 1.0 + tolerance:
        spread = hbd_market_price - 1.0
        return {
            "action": "SELL_HBD",
            "reason": f"HBD at ${hbd_market_price:.3f}, selling to push toward $1",
            "spread_captured": f"${spread:.3f} per HBD",
        }
    elif hbd_market_price < 1.0 - tolerance:
        spread = 1.0 - hbd_market_price
        return {
            "action": "BUY_HBD",
            "reason": f"HBD at ${hbd_market_price:.3f}, buying to push toward $1",
            "spread_captured": f"${spread:.3f} per HBD",
        }
    return {"action": "HOLD", "reason": "HBD within tolerance band"}

print(stabilizer_action(hbd_price))

# 3. Conversion arbitrage (protocol level)
def conversion_arbitrage(hbd_market_price: float, feed_price: float):
    """
    Protocol conversions create hard floor/ceiling:
    - HBD -> HIVE conversion: 3.5 days, at median feed price (floor at $1)
    - HIVE -> HBD conversion: 3.5 days, at median feed price (ceiling at $1)
    """
    # If HBD < $1, buy cheap HBD on market, convert to $1 worth of HIVE
    if hbd_market_price < 1.0:
        profit_pct = ((1.0 / hbd_market_price) - 1) * 100
        return f"Buy HBD at ${hbd_market_price:.3f}, convert to $1 HIVE → {profit_pct:.1f}% profit"
    # If HBD > $1, convert HIVE to HBD at $1, sell HBD on market
    elif hbd_market_price > 1.0:
        profit_pct = (hbd_market_price - 1.0) * 100
        return f"Convert HIVE→HBD at $1, sell at ${hbd_market_price:.3f} → {profit_pct:.1f}% profit"
    return "No arbitrage opportunity"

print(conversion_arbitrage(hbd_price, feed_price=0.30))
```

Peg mechanisms summary:
- **Protocol conversions**: 3.5-day HBD↔HIVE conversions at feed price create arbitrage floor/ceiling.
- **HBD Stabilizer**: DHF-funded bot that actively trades on the internal market, returning profits to the DAO.
- **Haircut rule**: If HBD supply exceeds 30% of HIVE market cap, conversions pay less than $1, preventing runaway debt.'''
    ),
    (
        "hive_economics/hbd-interest-rate-savings",
        r'''How does HBD interest work on Hive? How do I put HBD into savings and calculate the interest earned?''',
        r'''<think>
HBD in savings earns interest set by witness consensus (currently around 15% APR
as of late 2025, but it fluctuates). The interest is compounded when you make any
savings operation or claim it. You deposit HBD into savings with transfer_to_savings
and withdraw with transfer_from_savings (3-day delay). Interest accrues continuously
but is only applied/credited on certain triggers. The rate is the median of witness
published rates. I'll show how to check the rate and calculate earnings.
</think>

HBD in savings earns interest at a rate set by witness consensus. Here's how to use it:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta

hive = Hive()

# Check current HBD interest rate (set by witness median)
props = hive.get_dynamic_global_properties()
hbd_interest_rate = int(props.get("hbd_interest_rate", 0)) / 100  # basis points → percent
print(f"Current HBD interest rate: {hbd_interest_rate:.1f}% APR")

def calculate_hbd_savings_interest(
    principal_hbd: float,
    apr_percent: float,
    days: int
) -> dict:
    """Calculate HBD savings interest (simple interest model)."""
    daily_rate = apr_percent / 100 / 365
    interest = principal_hbd * daily_rate * days
    return {
        "principal": principal_hbd,
        "apr": f"{apr_percent}%",
        "days": days,
        "interest_earned": round(interest, 3),
        "total_balance": round(principal_hbd + interest, 3),
        "monthly_estimate": round(principal_hbd * daily_rate * 30, 3),
    }

# Example: 1000 HBD at 15% APR for 365 days
result = calculate_hbd_savings_interest(1000, 15.0, 365)
print(result)
# {'principal': 1000, 'apr': '15%', 'days': 365, 'interest_earned': 150.0, ...}

# To deposit and withdraw HBD savings (requires active key)
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer_to_savings, Transfer_from_savings

def deposit_to_savings(account_name: str, amount: str):
    """Broadcast transfer_to_savings operation."""
    hive_auth = Hive(keys=["5Jyour_active_key_here"])
    hive_auth.broadcast({
        "type": "transfer_to_savings",
        "from": account_name,
        "to": account_name,
        "amount": f"{amount} HBD",
        "memo": "",
    })

def withdraw_from_savings(account_name: str, amount: str, request_id: int = 0):
    """Withdraw from savings — 3 day delay before funds arrive."""
    hive_auth = Hive(keys=["5Jyour_active_key_here"])
    hive_auth.broadcast({
        "type": "transfer_from_savings",
        "from": account_name,
        "to": account_name,
        "amount": f"{amount} HBD",
        "memo": "",
        "request_id": request_id,
    })

# Check an account's savings balance
acct = Account("your-account", blockchain_instance=hive)
print(f"HBD savings: {acct['savings_hbd_balance']}")
```

Key points:
- **Interest rate**: Set by witness median, typically 15-20% APR (varies by consensus).
- **Deposits**: Instant via `transfer_to_savings`.
- **Withdrawals**: 3-day mandatory delay via `transfer_from_savings`.
- **Interest accrual**: Continuous, but credited on savings operations or every 30 days.'''
    ),
    (
        "hive_economics/hbd-to-hive-conversion",
        r'''How does HBD to HIVE conversion work? What's the 3.5-day delay and how is the conversion rate calculated?''',
        r'''<think>
The convert_hbd operation converts HBD to HIVE over 3.5 days. The conversion uses
the median price feed over that 3.5-day window (not the spot price at the time
of request). This prevents gaming via flash price manipulation. The output HIVE
amount = HBD_amount / median_feed_price. For example, converting 100 HBD at a
feed price of $0.30/HIVE yields 100/0.30 = 333.33 HIVE. This creates a price
floor for HBD — if HBD trades below $1, you can convert and get $1 worth of HIVE.
</think>

HBD-to-HIVE conversion is a protocol-level operation with a 3.5-day settlement delay:

```python
from beem import Hive
from datetime import datetime, timedelta

hive = Hive()

def estimate_hbd_to_hive_conversion(hbd_amount: float) -> dict:
    """
    Estimate HIVE received from converting HBD.

    The conversion uses the MEDIAN feed price over the 3.5-day window,
    NOT the spot price at the time of the request.
    """
    # Current median price feed
    price = hive.get_current_median_history()
    base = float(price["base"].split()[0])    # HBD per HIVE
    quote = float(price["quote"].split()[0])  # 1.000 HIVE

    hive_per_hbd = quote / base  # invert: HIVE per HBD

    estimated_hive = hbd_amount * hive_per_hbd
    completion = datetime.utcnow() + timedelta(hours=84)  # 3.5 days

    return {
        "hbd_input": hbd_amount,
        "feed_price": f"${base:.3f}/HIVE",
        "estimated_hive_output": round(estimated_hive, 3),
        "settlement_time": completion.isoformat() + "Z",
        "warning": "Actual output uses median feed over 3.5-day window",
    }

print(estimate_hbd_to_hive_conversion(100.0))

# Broadcast the conversion (requires active key)
def convert_hbd_to_hive(account: str, hbd_amount: float, request_id: int = 0):
    """
    Submit HBD → HIVE conversion. Settles in 3.5 days at median feed price.
    """
    hive_auth = Hive(keys=["5Jyour_active_key_here"])
    op = {
        "type": "convert",
        "owner": account,
        "amount": f"{hbd_amount:.3f} HBD",
        "requestid": request_id,
    }
    hive_auth.broadcast(op)
    print(f"Conversion submitted: {hbd_amount} HBD → HIVE (settles in 3.5 days)")

# Check pending conversions
from beem.account import Account
acct = Account("your-account", blockchain_instance=hive)
conversions = hive.rpc.get_conversion_requests(acct.name)
for c in conversions:
    print(f"  ID={c['requestid']}  amount={c['amount']}  completes={c['conversion_date']}")
```

Key details:
- **3.5-day median**: Protects against short-term price manipulation; uses the average feed over the settlement window.
- **Arbitrage floor**: If HBD < $1, converting to HIVE yields > $1 of value, creating buy pressure on HBD.
- **One-way**: This is the original `convert` operation — for the reverse, see `collateralized_convert`.'''
    ),
    (
        "hive_economics/hive-to-hbd-conversion",
        r'''How do I convert HIVE to HBD? What is the collateralized_convert operation and how does it differ from the regular convert?''',
        r'''<think>
The collateralized_convert operation (added in HF25) converts HIVE to HBD. It requires
overcollateralization — you put up HIVE worth more than the HBD you receive. The
conversion takes 3.5 days and uses the median feed over that window. You get back
HBD at a slight discount (excess HIVE is returned). This creates a ceiling on HBD
price — if HBD > $1, users convert HIVE→HBD and sell. The overcollateralization
(typically 2x) protects against price drops during the 3.5-day window.
</think>

HIVE-to-HBD conversion uses the `collateralized_convert` operation (HF25+), which requires overcollateralization:

```python
from beem import Hive

hive = Hive()

def estimate_hive_to_hbd_conversion(hive_amount: float) -> dict:
    """
    Estimate HBD received from collateralized HIVE → HBD conversion.

    The protocol takes 2x collateral in HIVE. After 3.5 days:
    - You receive HBD equal to half the HIVE value (at median feed)
    - Excess HIVE collateral is returned
    """
    price = hive.get_current_median_history()
    base = float(price["base"].split()[0])    # HBD per HIVE
    quote = float(price["quote"].split()[0])

    hbd_per_hive = base / quote
    # You put up hive_amount, but only ~half the value converts
    # The rest is collateral returned after settlement
    hbd_output = hive_amount * hbd_per_hive / 2  # conservative estimate
    hive_returned = hive_amount / 2                # excess collateral

    return {
        "hive_input": hive_amount,
        "feed_price": f"${hbd_per_hive:.4f} HBD/HIVE",
        "estimated_hbd_output": round(hbd_output, 3),
        "estimated_hive_returned": round(hive_returned, 3),
        "note": "Actual amounts depend on median feed over 3.5-day window",
    }

print(estimate_hive_to_hbd_conversion(1000.0))

# Broadcast collateralized conversion
def collateralized_convert(account: str, hive_amount: float, request_id: int = 0):
    """
    Convert HIVE → HBD with overcollateralization.
    Excess HIVE returned after 3.5-day settlement.
    """
    hive_auth = Hive(keys=["5Jyour_active_key_here"])
    op = {
        "type": "collateralized_convert",
        "owner": account,
        "amount": f"{hive_amount:.3f} HIVE",
        "requestid": request_id,
    }
    hive_auth.broadcast(op)
    print(f"Collateralized conversion: {hive_amount} HIVE submitted")

# Comparison table
comparison = """
| Feature              | convert (HBD→HIVE)       | collateralized_convert (HIVE→HBD) |
|----------------------|--------------------------|-----------------------------------|
| Direction            | HBD → HIVE               | HIVE → HBD                        |
| Settlement           | 3.5 days                 | 3.5 days                          |
| Collateral           | None (HBD destroyed)     | 2x overcollateralized             |
| Price used           | Median feed over window  | Median feed over window           |
| Excess returned      | N/A                      | Yes, surplus HIVE returned        |
| Peg effect           | Creates $1 floor for HBD | Creates $1 ceiling for HBD        |
| Added in             | Original                 | HF25 (June 2021)                  |
"""
print(comparison)
```

The overcollateralization (2x) protects the blockchain: if HIVE price drops during the 3.5-day window, there's enough collateral to still issue the correct HBD amount.'''
    ),
    (
        "hive_economics/hive-to-vests-conversion-math",
        r'''How do I convert between HIVE and VESTS? What's the math behind the HIVE/VESTS ratio?''',
        r'''<think>
VESTS are the internal unit of Hive Power. The conversion ratio changes over time
due to inflation. The formula is: HP = VESTS * total_vesting_fund_hive / total_vesting_shares.
Both values come from dynamic global properties. For example, if total_vesting_fund
is 200M HIVE and total_vesting_shares is 400T VESTS, then 1M VESTS = 0.5 HIVE.
The ratio only goes up (more HIVE per VEST) as inflation adds HIVE to the vesting fund.
This is important for calculating delegation amounts, witness votes, etc.
</think>

VESTS are the internal staking unit; Hive Power (HP) is the human-readable equivalent. The ratio shifts with inflation:

```python
from beem import Hive

hive = Hive()

def get_hive_per_vest() -> float:
    """Get the current HIVE-per-VEST conversion ratio."""
    props = hive.get_dynamic_global_properties()
    total_vesting_fund = float(props["total_vesting_fund_hive"].split()[0])
    total_vesting_shares = float(props["total_vesting_shares"].split()[0])
    return total_vesting_fund / total_vesting_shares

def vests_to_hp(vests: float) -> float:
    """Convert VESTS to Hive Power (HP)."""
    return vests * get_hive_per_vest()

def hp_to_vests(hp: float) -> float:
    """Convert Hive Power (HP) to VESTS."""
    return hp / get_hive_per_vest()

# Current ratio
ratio = get_hive_per_vest()
print(f"1 MVESTS = {ratio * 1_000_000:.3f} HP")
print(f"1 HP = {1 / ratio:,.6f} VESTS")

# Practical examples
print(f"\n--- Conversions ---")
print(f"5,000,000 VESTS = {vests_to_hp(5_000_000):.3f} HP")
print(f"1,000 HP = {hp_to_vests(1000):,.6f} VESTS")
print(f"100 HP = {hp_to_vests(100):,.6f} VESTS")

# Show why the ratio changes over time
def explain_ratio_drift():
    """
    The ratio increases because inflation adds HIVE to the vesting fund
    without creating new VESTS. Only power-up operations create VESTS.

    total_vesting_fund_hive grows from:
      - Inflation allocated to vesting (curation rewards, author HP payouts)
      - Power-up operations

    total_vesting_shares grows ONLY from:
      - Power-up operations (new VESTS minted)

    Since inflation adds HIVE to the fund without always minting VESTS,
    the ratio (HIVE/VESTS) increases over time.
    """
    props = hive.get_dynamic_global_properties()
    print(f"Total vesting fund: {props['total_vesting_fund_hive']}")
    print(f"Total vesting shares: {props['total_vesting_shares']}")

explain_ratio_drift()
```

The key insight: **1 VEST represents an ever-increasing amount of HIVE** because inflation adds to the vesting fund. When you power up 100 HIVE today, you get fewer VESTS than you would have a year ago — but each VEST is worth more.'''
    ),
    (
        "hive_economics/power-up-operation",
        r'''How do I power up HIVE to get Hive Power? Can you show me the code to perform a power up operation?''',
        r'''<think>
Power up converts liquid HIVE to HP (VESTS). The operation is called
transfer_to_vesting. It's instant — the HIVE is converted to VESTS at the
current ratio and added to the account's vesting_shares. You can power up
to yourself or to another account. The VESTS received = HIVE_amount / hive_per_vest.
Once powered up, the HP is locked and can only be retrieved via a 13-week
power down. HP grants governance weight, resource credits, and curation influence.
</think>

Power up converts liquid HIVE into Hive Power (VESTS) instantly:

```python
from beem import Hive
from beem.account import Account

hive = Hive()

def preview_power_up(hive_amount: float, target_account: str = None) -> dict:
    """Preview how much HP/VESTS a power-up will yield."""
    props = hive.get_dynamic_global_properties()
    total_fund = float(props["total_vesting_fund_hive"].split()[0])
    total_shares = float(props["total_vesting_shares"].split()[0])

    hive_per_vest = total_fund / total_shares
    vests_received = hive_amount / hive_per_vest

    return {
        "hive_input": hive_amount,
        "vests_received": round(vests_received, 6),
        "hp_equivalent": round(hive_amount, 3),  # 1:1 by definition
        "current_ratio": f"1 MVESTS = {hive_per_vest * 1e6:.3f} HP",
        "note": "Power up is instant. Power down takes 13 weeks.",
    }

print(preview_power_up(500.0))

# Broadcast power up (requires active key)
def power_up(from_account: str, to_account: str, hive_amount: float):
    """
    Power up HIVE → HP (VESTS).
    Can power up to yourself or to another account.
    """
    hive_auth = Hive(keys=["5Jyour_active_key_here"])
    op = {
        "type": "transfer_to_vesting",
        "from": from_account,
        "to": to_account,
        "amount": f"{hive_amount:.3f} HIVE",
    }
    hive_auth.broadcast(op)
    print(f"Powered up {hive_amount} HIVE to {to_account}")

# Check account HP after power up
def show_account_power(account_name: str):
    acct = Account(account_name, blockchain_instance=hive)
    props = hive.get_dynamic_global_properties()
    total_fund = float(props["total_vesting_fund_hive"].split()[0])
    total_shares = float(props["total_vesting_shares"].split()[0])

    own_vests = float(acct["vesting_shares"].split()[0])
    delegated_out = float(acct["delegated_vesting_shares"].split()[0])
    received_in = float(acct["received_vesting_shares"].split()[0])

    ratio = total_fund / total_shares
    own_hp = own_vests * ratio
    effective_hp = (own_vests - delegated_out + received_in) * ratio

    print(f"Account: {account_name}")
    print(f"  Own HP:       {own_hp:,.3f}")
    print(f"  Delegated out: {delegated_out * ratio:,.3f} HP")
    print(f"  Received in:   {received_in * ratio:,.3f} HP")
    print(f"  Effective HP:  {effective_hp:,.3f}")

show_account_power("blocktrades")
```

Benefits of powering up:
- **Governance**: Vote for witnesses and proposals with more weight.
- **Curation**: Earn curation rewards proportional to your HP.
- **Resource Credits**: More HP = more free transactions.
- **Influence**: Higher HP means larger vote values on content.'''
    ),
    (
        "hive_economics/power-down-schedule",
        r'''How does the Hive power down process work? I want to understand the 13-week schedule and how to calculate weekly payouts.''',
        r'''<think>
Power down converts VESTS back to liquid HIVE over 13 weekly installments.
When you initiate a power down, 1/13th of your vesting shares converts each
week. The operation is withdraw_vesting. You can cancel anytime, or start a
new power down (which replaces the current one). Each weekly payout is
vesting_shares / 13 VESTS converted to HIVE at the current ratio at the time
of each installment. The first payment comes 7 days after initiating.
</think>

Power down converts HP (VESTS) back to liquid HIVE in **13 equal weekly payments**:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta

hive = Hive()

def plan_power_down(account_name: str, hp_to_powerdown: float) -> list[dict]:
    """
    Calculate the 13-week power down schedule.
    Each week, 1/13th of the total VESTS is converted to HIVE.
    """
    props = hive.get_dynamic_global_properties()
    total_fund = float(props["total_vesting_fund_hive"].split()[0])
    total_shares = float(props["total_vesting_shares"].split()[0])
    ratio = total_fund / total_shares

    total_vests = hp_to_powerdown / ratio
    weekly_vests = total_vests / 13
    weekly_hp = hp_to_powerdown / 13

    schedule = []
    start = datetime.utcnow()
    for week in range(1, 14):
        payout_date = start + timedelta(weeks=week)
        schedule.append({
            "week": week,
            "date": payout_date.strftime("%Y-%m-%d"),
            "vests": round(weekly_vests, 6),
            "hp_approx": round(weekly_hp, 3),
            "cumulative_hp": round(weekly_hp * week, 3),
        })

    return schedule

# Example: Power down 10,000 HP
schedule = plan_power_down("example-user", 10_000.0)
for week in schedule:
    print(f"Week {week['week']:2d} ({week['date']}): "
          f"{week['hp_approx']:,.3f} HP  "
          f"[cumulative: {week['cumulative_hp']:,.3f} HP]")

# Broadcast power down (requires active key)
def start_power_down(account: str, vesting_shares: float):
    """Start or replace a power down."""
    hive_auth = Hive(keys=["5Jyour_active_key_here"])
    op = {
        "type": "withdraw_vesting",
        "account": account,
        "vesting_shares": f"{vesting_shares:.6f} VESTS",
    }
    hive_auth.broadcast(op)

def cancel_power_down(account: str):
    """Cancel power down by setting withdraw to 0."""
    start_power_down(account, 0.0)

# Check existing power down status
acct = Account("your-account", blockchain_instance=hive)
withdrawing = float(acct["vesting_withdraw_rate"].split()[0])
if withdrawing > 0:
    ratio_val = float(hive.get_dynamic_global_properties()["total_vesting_fund_hive"].split()[0]) / \
                float(hive.get_dynamic_global_properties()["total_vesting_shares"].split()[0])
    print(f"Currently powering down: {withdrawing * ratio_val:.3f} HP/week")
    print(f"Next payout: {acct['next_vesting_withdrawal']}")
else:
    print("No active power down")
```

Important notes:
- **First payment**: 7 days after initiating, then every 7 days.
- **Replacing**: Starting a new power down cancels and replaces the current one.
- **Cancellation**: Set `vesting_shares` to 0 VESTS to cancel.
- **HIVE/VESTS ratio**: Each weekly HIVE amount varies slightly as the ratio changes.'''
    ),
    (
        "hive_economics/delegation-math-effective-hp",
        r'''How does Hive Power delegation work? How do I calculate effective HP considering delegations in and out?''',
        r'''<think>
Delegation transfers the influence of VESTS to another account without transferring
ownership. The delegator's effective HP decreases, the delegatee's increases.
Effective HP = own_vests - delegated_vesting_shares + received_vesting_shares.
Delegation is measured in VESTS internally. When you delegate, you specify VESTS
(or HP which gets converted). The minimum delegation must be meaningful (dust
threshold applies). Delegation can be removed, but there's a 5-day return period.
</think>

Delegation lends your HP influence to another account without transferring ownership:

```python
from beem import Hive
from beem.account import Account

hive = Hive()

def get_delegation_breakdown(account_name: str) -> dict:
    """Calculate effective HP accounting for all delegations."""
    acct = Account(account_name, blockchain_instance=hive)
    props = hive.get_dynamic_global_properties()

    total_fund = float(props["total_vesting_fund_hive"].split()[0])
    total_shares = float(props["total_vesting_shares"].split()[0])
    ratio = total_fund / total_shares

    own_vests = float(acct["vesting_shares"].split()[0])
    delegated_out = float(acct["delegated_vesting_shares"].split()[0])
    received_in = float(acct["received_vesting_shares"].split()[0])

    own_hp = own_vests * ratio
    delegated_out_hp = delegated_out * ratio
    received_in_hp = received_in * ratio
    effective_hp = (own_vests - delegated_out + received_in) * ratio

    return {
        "account": account_name,
        "own_hp": round(own_hp, 3),
        "delegated_out_hp": round(delegated_out_hp, 3),
        "received_in_hp": round(received_in_hp, 3),
        "effective_hp": round(effective_hp, 3),
        "own_vests": round(own_vests, 6),
    }

info = get_delegation_breakdown("blocktrades")
for k, v in info.items():
    print(f"  {k}: {v}")

# List active outgoing delegations
def list_outgoing_delegations(account_name: str):
    delegations = hive.rpc.get_vesting_delegations(account_name, "", 100)
    props = hive.get_dynamic_global_properties()
    ratio = float(props["total_vesting_fund_hive"].split()[0]) / \
            float(props["total_vesting_shares"].split()[0])

    for d in delegations:
        vests = float(d["vesting_shares"].split()[0])
        hp = vests * ratio
        print(f"  → {d['delegatee']}: {hp:,.3f} HP ({vests:,.0f} VESTS)")

list_outgoing_delegations("blocktrades")

# Delegate HP to another account (requires active key)
def delegate_hp(delegator: str, delegatee: str, hp_amount: float):
    """Delegate HP. Set to 0 to remove delegation (5-day return)."""
    props = hive.get_dynamic_global_properties()
    ratio = float(props["total_vesting_fund_hive"].split()[0]) / \
            float(props["total_vesting_shares"].split()[0])
    vests = hp_amount / ratio

    hive_auth = Hive(keys=["5Jyour_active_key_here"])
    op = {
        "type": "delegate_vesting_shares",
        "delegator": delegator,
        "delegatee": delegatee,
        "vesting_shares": f"{vests:.6f} VESTS",
    }
    hive_auth.broadcast(op)
    print(f"Delegated {hp_amount:.3f} HP ({vests:.6f} VESTS) to {delegatee}")
```

Key mechanics:
- **Effective HP** = Own HP - Delegated Out + Received In.
- **Delegation**: Transfers voting influence and RC, not token ownership.
- **Removal**: Set delegation to 0 VESTS; HP returns after **5-day** cooldown.
- **No stacking**: New delegation to same account replaces previous (not additive).'''
    ),
    (
        "hive_economics/delegation-return-period",
        r'''When I remove a delegation on Hive, how long does it take to get my HP back? How does the 5-day return period work?''',
        r'''<think>
When you remove or reduce a delegation, the VESTS enter a "cooling down" period
of 5 days (HIVE_DELEGATION_RETURN_PERIOD). During this time, the HP is neither
available to the delegator nor the delegatee — it's in limbo. After 5 days, it
automatically returns to the delegator's effective HP. You can check pending
returns via get_expiring_vesting_delegations API call. This prevents abuse where
someone could delegate, vote, then immediately undelegate.
</think>

When you remove a delegation, the HP enters a **5-day cooldown** before returning to you:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta

hive = Hive()

DELEGATION_RETURN_DAYS = 5  # HIVE_DELEGATION_RETURN_PERIOD

def check_expiring_delegations(account_name: str):
    """Check pending delegation returns (HP in cooldown)."""
    now = datetime.utcnow()
    # Query expiring delegations from now backwards through the return window
    start = (now - timedelta(days=DELEGATION_RETURN_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")

    expiring = hive.rpc.get_expiring_vesting_delegations(
        account_name, start, 100
    )

    props = hive.get_dynamic_global_properties()
    ratio = float(props["total_vesting_fund_hive"].split()[0]) / \
            float(props["total_vesting_shares"].split()[0])

    total_returning = 0.0
    for e in expiring:
        vests = float(e["vesting_shares"].split()[0])
        hp = vests * ratio
        expiry = e["expiration"]
        total_returning += hp
        print(f"  {hp:,.3f} HP returning on {expiry}")

    if not expiring:
        print("  No pending delegation returns")
    else:
        print(f"  Total HP in cooldown: {total_returning:,.3f}")

check_expiring_delegations("your-account")

def simulate_delegation_lifecycle(hp_amount: float):
    """Show the full lifecycle of a delegation."""
    now = datetime.utcnow()
    timeline = [
        ("Delegate", now, f"Delegatee gains {hp_amount} HP influence"),
        ("Remove delegation", now + timedelta(days=30), "HP enters 5-day cooldown"),
        ("Cooldown active", now + timedelta(days=30, hours=1),
         f"{hp_amount} HP unusable by either party"),
        ("HP returns", now + timedelta(days=35),
         f"{hp_amount} HP back in delegator's effective HP"),
    ]

    print(f"\n--- Delegation Lifecycle for {hp_amount} HP ---")
    for event, date, desc in timeline:
        print(f"  {date.strftime('%Y-%m-%d %H:%M')} | {event}: {desc}")

    print(f"\nDuring cooldown ({DELEGATION_RETURN_DAYS} days):")
    print("  - Delegator: HP NOT counted in effective HP")
    print("  - Delegatee: HP NOT counted in effective HP")
    print("  - Neither party can vote or earn RC with these VESTS")

simulate_delegation_lifecycle(1000.0)
```

The 5-day return period prevents **delegation cycling attacks** — without it, an attacker could delegate to an account, cast votes, then immediately reclaim HP and delegate elsewhere to vote again.'''
    ),
    (
        "hive_economics/witness-pay-calculation",
        r'''How are Hive witnesses compensated? How do I calculate witness block pay and the difference between top 20 and backup witnesses?''',
        r'''<think>
Witnesses are paid per block they produce. Top 20 witnesses produce 1 block per
round (21 blocks per round: 20 top + 1 rotating backup). Backup witnesses are
selected by stake-weighted probability. Witness pay comes from inflation — each
block generates a fixed amount of HIVE. The block reward = virtual_supply * inflation_rate
/ (blocks_per_year). Top 20 produce ~1/21 of all blocks each. Backup witnesses
collectively produce ~1/21 of blocks. I'll calculate actual pay rates.
</think>

Witnesses earn HIVE for producing blocks. Top 20 and backup witnesses earn differently:

```python
from beem import Hive

hive = Hive()

def calculate_witness_pay() -> dict:
    """Calculate witness block reward and annual pay estimates."""
    props = hive.get_dynamic_global_properties()

    virtual_supply = float(props["virtual_supply"].split()[0])
    current_inflation = int(props.get("current_inflation_rate", 975))  # basis points
    head_block = int(props["head_block_number"])

    # Inflation rate in percentage
    inflation_pct = current_inflation / 10000

    # HIVE generated per year from inflation
    annual_new_hive = virtual_supply * inflation_pct

    # Witnesses get 10% of inflation (witnesses=10%, staking=65%, DHF=10%, reward pool=15%)
    # Actually: witness pay is 1 HIVE per block produced (simplified)
    blocks_per_day = 28800  # 1 block per 3 seconds
    blocks_per_year = blocks_per_day * 365

    # Witness reward per block (from inflation allocation)
    witness_inflation_share = 0.10  # 10% of inflation to witnesses
    witness_pool_annual = annual_new_hive * witness_inflation_share
    reward_per_block = witness_pool_annual / blocks_per_year

    # Top 20: each produces 1 of every 21 blocks
    blocks_per_round = 21  # 20 top witnesses + 1 backup slot
    top20_blocks_per_day = blocks_per_day / blocks_per_round
    top20_annual_pay = top20_blocks_per_day * 365 * reward_per_block

    # Backup: share 1/21 of blocks among all backup witnesses
    backup_slot_annual = top20_annual_pay  # total for the backup slot
    estimated_backup_witnesses = 100  # active backup witnesses competing
    avg_backup_annual = backup_slot_annual / estimated_backup_witnesses

    return {
        "virtual_supply": f"{virtual_supply:,.0f} HIVE",
        "inflation_rate": f"{inflation_pct * 100:.2f}%",
        "reward_per_block": round(reward_per_block, 4),
        "top_20_witness": {
            "blocks_per_day": round(top20_blocks_per_day, 1),
            "daily_pay": round(top20_blocks_per_day * reward_per_block, 2),
            "annual_pay": round(top20_annual_pay, 0),
        },
        "backup_witness_avg": {
            "note": f"Shared among ~{estimated_backup_witnesses} backups",
            "annual_pay_estimate": round(avg_backup_annual, 0),
        },
    }

pay = calculate_witness_pay()
import json
print(json.dumps(pay, indent=2))

# Check a specific witness's recent production
from beem.witness import Witness

def witness_stats(witness_name: str):
    w = Witness(witness_name, blockchain_instance=hive)
    print(f"\nWitness: {witness_name}")
    print(f"  Votes (VESTS): {w['votes']}")
    print(f"  Missed blocks: {w['total_missed']}")
    print(f"  Last block: {w['last_confirmed_block_num']}")
    print(f"  Running version: {w['running_version']}")
    print(f"  HBD interest rate: {int(w['props']['hbd_interest_rate']) / 100}%")

witness_stats("blocktrades")
```

Key points:
- **Top 20**: Produce 20 of every 21 blocks — consistent, predictable income.
- **Backup**: Share 1 of every 21 blocks, selected by stake-weighted lottery.
- **Pay is in HP**: Block rewards are paid as VESTS (powered-up HIVE).
- **Missed blocks**: Witnesses who miss blocks lose that round's pay permanently.'''
    ),
    (
        "hive_economics/inflation-schedule-virtual-supply",
        r'''How does Hive's inflation schedule work? What is virtual supply and how does inflation decrease over time?''',
        r'''<think>
Hive started with ~9.5% annual inflation at HF16 (Dec 2016) and decreases by
0.01% every 250,000 blocks (~0.5% per year). The floor is 0.95% where it stays
forever. Virtual supply = liquid HIVE + HP (as HIVE) + HBD (converted to HIVE
at feed price). Inflation is split: 65% to vesting (curation/staking), 15% to
reward pool (authors), 10% to witnesses, 10% to DHF. The current inflation rate
is stored in dynamic global properties. Let me calculate the schedule.
</think>

Hive's inflation starts at ~9.5% and decreases by 0.01% every 250,000 blocks until it hits the 0.95% floor:

```python
from beem import Hive
from datetime import datetime, timedelta

hive = Hive()

# Current state
props = hive.get_dynamic_global_properties()
virtual_supply = float(props["virtual_supply"].split()[0])
head_block = int(props["head_block_number"])

def get_inflation_at_block(block_num: int) -> float:
    """
    Calculate inflation rate at a given block.
    Starts at 9.5% (block ~7M at HF16), decreases 0.01% per 250k blocks.
    Floor is 0.95%.
    """
    INITIAL_INFLATION = 978  # basis points (~9.78% at genesis adjustment)
    INFLATION_FLOOR = 95     # 0.95%
    DECREASE_INTERVAL = 250_000

    # Blocks since inflation started decreasing
    reduction_steps = block_num // DECREASE_INTERVAL
    inflation_bp = max(INITIAL_INFLATION - reduction_steps, INFLATION_FLOOR)
    return inflation_bp / 100  # as percentage

# Inflation allocation breakdown
def inflation_breakdown(block_num: int, virtual_supply: float) -> dict:
    rate = get_inflation_at_block(block_num)
    annual_new = virtual_supply * (rate / 100)

    return {
        "block": block_num,
        "inflation_rate": f"{rate:.2f}%",
        "annual_new_hive": round(annual_new, 0),
        "allocation": {
            "vesting_staking_65pct": round(annual_new * 0.65, 0),
            "reward_pool_15pct": round(annual_new * 0.15, 0),
            "witness_pay_10pct": round(annual_new * 0.10, 0),
            "dhf_dao_10pct": round(annual_new * 0.10, 0),
        },
    }

import json
print("=== Current Inflation ===")
print(json.dumps(inflation_breakdown(head_block, virtual_supply), indent=2))

# Project future inflation milestones
print("\n=== Inflation Schedule Projection ===")
blocks_per_year = 365 * 24 * 3600 // 3
for years_ahead in range(0, 30, 5):
    future_block = head_block + (blocks_per_year * years_ahead)
    rate = get_inflation_at_block(future_block)
    year = datetime.utcnow().year + years_ahead
    status = " (FLOOR)" if rate <= 0.95 else ""
    print(f"  {year}: block ~{future_block:,}  inflation={rate:.2f}%{status}")

# Time until floor
current_rate_bp = int(get_inflation_at_block(head_block) * 100)
steps_remaining = max(0, current_rate_bp - 95)
blocks_remaining = steps_remaining * 250_000
years_to_floor = blocks_remaining / blocks_per_year
print(f"\nYears until 0.95% floor: ~{years_to_floor:.1f}")
```

Inflation split:
- **65%** → Vesting rewards (curators, stakers via HP payouts)
- **15%** → Content reward pool (authors)
- **10%** → Witness pay (block production)
- **10%** → DHF/DAO (Decentralized Hive Fund for proposals)'''
    ),
    (
        "hive_economics/dhf-dao-proposal-funding",
        r'''How does the Hive DHF (Decentralized Hive Fund) work? How are proposals funded and how does the daily budget get calculated?''',
        r'''<think>
The DHF (also called the DAO or SPS - Steem Proposal System, carried over) receives
10% of Hive's inflation. Proposals request daily HBD payments. To be funded, a
proposal must receive more HP votes than the "return proposal" (a special proposal
that acts as a threshold). The DHF pays out daily in HBD. Proposals are ranked by
total HP votes, and the fund pays from top to bottom until the daily budget is
exhausted. The return proposal can be moved to cut off lower-ranked proposals.
</think>

The DHF (Decentralized Hive Fund) is Hive's on-chain treasury, funded by 10% of inflation:

```python
from beem import Hive
from beem.account import Account

hive = Hive()

def get_dhf_status() -> dict:
    """Query DHF treasury balance and daily budget."""
    treasury = Account("hive.fund", blockchain_instance=hive)

    # Treasury balances
    hbd_balance = treasury["hbd_balance"]
    hive_balance = treasury["balance"]

    # Get dynamic props for inflation calculation
    props = hive.get_dynamic_global_properties()
    virtual_supply = float(props["virtual_supply"].split()[0])

    # DHF receives 10% of inflation, paid in HBD
    price = hive.get_current_median_history()
    hbd_per_hive = float(price["base"].split()[0]) / float(price["quote"].split()[0])

    inflation_rate = int(props.get("current_inflation_rate", 975)) / 10000
    annual_inflation = virtual_supply * inflation_rate
    dhf_annual_hive = annual_inflation * 0.10
    dhf_daily_hbd_inflow = (dhf_annual_hive / 365) * hbd_per_hive

    return {
        "treasury_hbd": str(hbd_balance),
        "treasury_hive": str(hive_balance),
        "daily_hbd_inflow": round(dhf_daily_hbd_inflow, 2),
        "annual_dhf_budget_hbd": round(dhf_daily_hbd_inflow * 365, 0),
    }

import json
print("=== DHF Treasury Status ===")
print(json.dumps(get_dhf_status(), indent=2))

def list_funded_proposals():
    """List proposals, showing which are above the return proposal threshold."""
    proposals = hive.rpc.list_proposals(
        [-1], 50, "by_total_votes", "descending", "all"
    )

    # Find the return proposal (ID 0)
    return_proposal_votes = 0
    for p in proposals:
        if int(p["id"]) == 0:
            return_proposal_votes = int(p["total_votes"])
            break

    print(f"\nReturn proposal threshold: {return_proposal_votes:,} VESTS")
    print(f"{'ID':>4} | {'Daily HBD':>12} | {'Votes':>18} | {'Funded':>7} | Subject")
    print("-" * 80)

    for p in proposals[:20]:
        votes = int(p["total_votes"])
        funded = votes > return_proposal_votes and int(p["id"]) != 0
        daily = p["daily_pay"]
        status = "YES" if funded else "no"
        subject = p["subject"][:35]
        print(f"{p['id']:>4} | {daily:>12} | {votes:>18,} | {status:>7} | {subject}")

list_funded_proposals()
```

How funding works:
1. **10% inflation** flows into `@hive.fund` as HBD daily.
2. Proposals are **ranked by total HP votes** (descending).
3. The **return proposal** (ID 0) acts as a threshold — only proposals with more votes get funded.
4. Funded proposals receive their `daily_pay` in HBD each day.
5. If the daily budget is exhausted, lower-ranked (but still above threshold) proposals may be partially funded.'''
    ),
    (
        "hive_economics/proposal-threshold-daily-pay",
        r'''How does the return proposal threshold work in the Hive DHF? How do I check if a proposal will be funded?''',
        r'''<think>
The return proposal (ID 0) is a special proposal that returns any unspent funds
back to the DHF. Its total_votes acts as a funding cutoff line. Any proposal with
more votes than the return proposal gets funded; below it, no funding. Stakeholders
vote on the return proposal to set the bar — voting for it means "don't fund proposals
with less support than this." A proposal's daily_pay is paid in HBD each day it's
active and above the threshold. I'll show how to check this programmatically.
</think>

The **return proposal** (ID 0) is the funding threshold — proposals need more votes than it to receive daily HBD:

```python
from beem import Hive

hive = Hive()

def check_proposal_funding(proposal_id: int) -> dict:
    """
    Check if a specific proposal is funded by comparing its votes
    to the return proposal threshold.
    """
    # Get the target proposal
    proposals = hive.rpc.list_proposals([proposal_id - 1], 5, "by_total_votes",
                                         "descending", "all")
    target = None
    for p in proposals:
        if int(p["id"]) == proposal_id:
            target = p
            break

    if not target:
        # Try fetching by ID directly
        all_props = hive.rpc.find_proposals([proposal_id])
        target = all_props[0] if all_props else None

    if not target:
        return {"error": f"Proposal {proposal_id} not found"}

    # Get return proposal votes
    return_props = hive.rpc.find_proposals([0])
    return_votes = int(return_props[0]["total_votes"])
    target_votes = int(target["total_votes"])

    # Convert VESTS to HP for readability
    props = hive.get_dynamic_global_properties()
    ratio = float(props["total_vesting_fund_hive"].split()[0]) / \
            float(props["total_vesting_shares"].split()[0])

    is_funded = target_votes > return_votes
    vote_margin = (target_votes - return_votes) * ratio

    daily_pay = target["daily_pay"]
    total_days = 0
    if target["start_date"] and target["end_date"]:
        from datetime import datetime
        start = datetime.strptime(target["start_date"], "%Y-%m-%dT%H:%M:%S")
        end = datetime.strptime(target["end_date"], "%Y-%m-%dT%H:%M:%S")
        total_days = (end - start).days

    return {
        "proposal_id": proposal_id,
        "subject": target["subject"],
        "daily_pay": daily_pay,
        "total_budget": f"{float(daily_pay.split()[0]) * total_days:.3f} HBD" if total_days else "N/A",
        "duration_days": total_days,
        "proposal_votes_hp": f"{target_votes * ratio:,.0f} HP",
        "return_threshold_hp": f"{return_votes * ratio:,.0f} HP",
        "funded": is_funded,
        "margin_hp": f"{'+' if vote_margin > 0 else ''}{vote_margin:,.0f} HP",
        "status": target["status"],
    }

import json
# Check proposal #250 (example)
result = check_proposal_funding(250)
print(json.dumps(result, indent=2, default=str))
```

How stakeholders control funding:
- **Voting FOR return proposal**: Raises the bar — fewer proposals get funded, more HBD stays in treasury.
- **Voting AGAINST return proposal**: Lowers the bar — more proposals funded.
- **Net effect**: The return proposal is a community-controlled spending thermostat.
- Only **active** proposals (within start/end date) receive daily payouts.'''
    ),
    (
        "hive_economics/vote-weight-calculation-from-hp",
        r'''How is vote weight (rshares) calculated from HP on Hive? I want to understand the math behind how HP translates into vote impact.''',
        r'''<think>
Vote rshares = effective_vests * vote_weight_percent * (current_mana / max_mana).
Effective vests = own vests - delegated_out + received_in. The vote_weight_percent
ranges from 1-10000 (0.01% to 100%). The mana fraction represents current voting
power (recharges 20% per day from last vote). Max rshares at 100% weight and full
mana is simply effective_vests (in VESTS * 1e6 precision). This determines the
post's reward contribution. I should show the full calculation chain.
</think>

Vote impact (rshares) is calculated from your effective VESTS, vote weight, and current mana:

```python
from beem import Hive
from beem.account import Account

hive = Hive()

def calculate_vote_rshares(account_name: str, vote_weight_pct: float = 100.0) -> dict:
    """
    Calculate the rshares a vote would produce right now.

    rshares = effective_vests * (vote_weight / 10000) * (current_mana / max_mana)
    """
    acct = Account(account_name, blockchain_instance=hive)
    props = hive.get_dynamic_global_properties()

    ratio = float(props["total_vesting_fund_hive"].split()[0]) / \
            float(props["total_vesting_shares"].split()[0])

    # Effective VESTS
    own_vests = float(acct["vesting_shares"].split()[0])
    delegated_out = float(acct["delegated_vesting_shares"].split()[0])
    received_in = float(acct["received_vesting_shares"].split()[0])
    effective_vests = own_vests - delegated_out + received_in

    # Voting mana (0 to max)
    # Max mana = effective_vests * 1,000,000 (HIVE uses 1e6 precision)
    max_mana = effective_vests * 1_000_000
    current_mana = int(acct["voting_manabar"]["current_mana"])
    last_update = int(acct["voting_manabar"]["last_update_time"])

    # Regenerate mana: 100% in 5 days (432000 seconds)
    import time
    now = int(time.time())
    elapsed = now - last_update
    regenerated = max_mana * elapsed / 432000
    current_mana = min(current_mana + regenerated, max_mana)
    mana_pct = (current_mana / max_mana * 100) if max_mana > 0 else 0

    # Vote weight in basis points (100% = 10000)
    weight_bp = int(vote_weight_pct * 100)

    # rshares calculation
    used_mana = current_mana * weight_bp // 10000
    rshares = used_mana

    # Estimate HBD value of this vote
    reward_fund = hive.get_reward_funds()[0]
    reward_balance = float(reward_fund["reward_balance"].split()[0])
    recent_claims = int(reward_fund["recent_claims"])
    price = hive.get_current_median_history()
    hbd_per_hive = float(price["base"].split()[0])

    vote_value_hive = (rshares / recent_claims) * reward_balance
    vote_value_hbd = vote_value_hive * hbd_per_hive

    return {
        "account": account_name,
        "effective_hp": round(effective_vests * ratio, 3),
        "effective_vests": round(effective_vests, 6),
        "mana_pct": round(mana_pct, 2),
        "vote_weight": f"{vote_weight_pct}%",
        "rshares": int(rshares),
        "vote_value_hbd": round(vote_value_hbd, 4),
    }

import json
result = calculate_vote_rshares("blocktrades", vote_weight_pct=100.0)
print(json.dumps(result, indent=2))

# Compare different vote weights
for w in [100, 50, 25, 10, 1]:
    r = calculate_vote_rshares("blocktrades", w)
    print(f"  {w:3d}% weight → ${r['vote_value_hbd']:.4f} HBD  ({r['rshares']:,} rshares)")
```

The formula chain:
1. **Effective VESTS** = own - delegated_out + received_in
2. **Max mana** = effective_vests * 1,000,000
3. **Current mana** = regenerates 100% over 5 days (linear)
4. **rshares** = current_mana * (weight_bp / 10000)
5. **HBD value** = (rshares / recent_claims) * reward_balance * hbd_per_hive'''
    ),
    (
        "hive_economics/voting-mana-regeneration",
        r'''How does voting mana work on Hive? How fast does it regenerate and how does a vote deplete it?''',
        r'''<think>
Voting mana (formerly "voting power") regenerates linearly from 0 to 100% over
5 days (432,000 seconds). Each 100% upvote consumes 2% of current mana (so at
full mana you can make 10 full votes per day to maintain ~80% mana, or about 40
full votes to drain completely). Partial votes consume proportionally less. The
mana is tracked as an integer with last_update_time. Downvote mana is separate
and has its own pool (25% of upvote mana regeneration). I'll show the math.
</think>

Voting mana regenerates linearly over 5 days and each vote consumes a proportional amount:

```python
import time
from beem import Hive
from beem.account import Account

hive = Hive()

MANA_REGEN_SECONDS = 432_000  # 5 days = 100% regen
VOTE_DUST_THRESHOLD = 50_000_000  # minimum rshares to count

def get_current_mana(account_name: str) -> dict:
    """Calculate current upvote and downvote mana with regeneration."""
    acct = Account(account_name, blockchain_instance=hive)
    props = hive.get_dynamic_global_properties()
    ratio = float(props["total_vesting_fund_hive"].split()[0]) / \
            float(props["total_vesting_shares"].split()[0])

    own = float(acct["vesting_shares"].split()[0])
    out = float(acct["delegated_vesting_shares"].split()[0])
    rcv = float(acct["received_vesting_shares"].split()[0])
    effective = own - out + rcv
    max_mana = effective * 1_000_000

    now = int(time.time())

    # Upvote mana
    up_mana = int(acct["voting_manabar"]["current_mana"])
    up_last = int(acct["voting_manabar"]["last_update_time"])
    up_regen = max_mana * (now - up_last) / MANA_REGEN_SECONDS
    up_current = min(up_mana + up_regen, max_mana)

    # Downvote mana (separate pool, 25% of upvote max)
    max_dv_mana = max_mana * 0.25
    dv_mana = int(acct["downvote_manabar"]["current_mana"])
    dv_last = int(acct["downvote_manabar"]["last_update_time"])
    dv_regen = max_dv_mana * (now - dv_last) / MANA_REGEN_SECONDS
    dv_current = min(dv_mana + dv_regen, max_dv_mana)

    return {
        "account": account_name,
        "effective_hp": round(effective * ratio, 3),
        "upvote_mana_pct": round(up_current / max_mana * 100, 2) if max_mana else 0,
        "downvote_mana_pct": round(dv_current / max_dv_mana * 100, 2) if max_dv_mana else 0,
        "full_recharge_hours": round((max_mana - up_current) / max_mana * 120, 1),
    }

import json
print(json.dumps(get_current_mana("blocktrades"), indent=2))

def simulate_voting_session(start_mana_pct: float, votes: list[float]) -> list[dict]:
    """
    Simulate mana depletion over a series of votes.
    Each 100% vote costs 2% of MAX mana (1/50th).

    Args:
        start_mana_pct: Starting mana percentage (0-100).
        votes: List of vote weight percentages (e.g., [100, 50, 25]).
    """
    max_mana = 1_000_000  # normalized
    current = max_mana * (start_mana_pct / 100)
    results = []

    for i, weight in enumerate(votes):
        mana_cost = max_mana * (weight / 100) * 0.02  # 2% of max per 100% vote
        current = max(0, current - mana_cost)
        results.append({
            "vote": i + 1,
            "weight": f"{weight}%",
            "mana_cost_pct": round(mana_cost / max_mana * 100, 2),
            "mana_after": round(current / max_mana * 100, 2),
        })

    return results

# 10 full-power votes starting at 100% mana
session = simulate_voting_session(100.0, [100] * 10)
for v in session:
    print(f"  Vote #{v['vote']}: {v['weight']} → mana after: {v['mana_after']}%")
```

Key mechanics:
- **Regen**: 100% over 5 days (20% per day, linear).
- **Cost**: A 100% vote costs 2% of max mana; a 50% vote costs 1%.
- **Optimal cadence**: ~10 full votes per day maintains ~80% mana.
- **Downvote mana**: Separate pool at 25% of upvote capacity — free downvotes up to that limit.'''
    ),
    (
        "hive_economics/resource-credit-calculation",
        r'''How are resource credits (RC) calculated on Hive? How does HP translate into available RC for transactions?''',
        r'''<think>
Resource credits are Hive's rate-limiting mechanism. Each account gets RC proportional
to its effective HP. Every transaction (post, comment, transfer, custom_json) costs
a certain amount of RC based on its size and type. RC regenerates over 5 days, same
as voting mana. The cost depends on the "resource budget" which is dynamically
adjusted based on blockchain usage. RC replaced the old bandwidth system. Accounts
with more HP can do more transactions. This is what makes Hive feeless — you stake
HP to get transaction capacity rather than paying per-tx fees.
</think>

Resource Credits (RC) are Hive's feeless rate-limiting system — your HP determines your transaction capacity:

```python
import time
from beem import Hive
from beem.account import Account
from beem.rc import RC

hive = Hive()

def get_rc_status(account_name: str) -> dict:
    """Get current RC status including regeneration estimate."""
    acct = Account(account_name, blockchain_instance=hive)

    rc_manabar = acct.get_rc_manabar()
    rc_max = int(rc_manabar["max_rc"])
    rc_current = int(rc_manabar["current_mana"])
    rc_pct = (rc_current / rc_max * 100) if rc_max > 0 else 0

    return {
        "account": account_name,
        "max_rc": rc_max,
        "current_rc": rc_current,
        "rc_pct": round(rc_pct, 2),
        "recharge_hours": round((rc_max - rc_current) / rc_max * 120, 1) if rc_max else 0,
    }

print(get_rc_status("blocktrades"))

def estimate_rc_costs() -> dict:
    """Estimate RC cost for common operations."""
    rc = RC(blockchain_instance=hive)

    costs = {
        "comment_post": rc.comment(tx_size=300, permlink_length=50,
                                     parent_permlink_length=0),
        "comment_reply": rc.comment(tx_size=200, permlink_length=50,
                                      parent_permlink_length=50),
        "vote": rc.vote(tx_size=120),
        "transfer": rc.transfer(tx_size=200, market_op_count=1),
        "custom_json": rc.custom_json(tx_size=500),
        "claim_account": rc.claim_account(tx_size=200),
    }

    return {op: f"{cost:,.0f} RC" for op, cost in costs.items()}

import json
print("\n=== RC Cost Estimates ===")
print(json.dumps(estimate_rc_costs(), indent=2))

def transactions_available(account_name: str) -> dict:
    """Estimate how many of each operation the account can perform."""
    status = get_rc_status(account_name)
    rc = RC(blockchain_instance=hive)

    current = status["current_rc"]
    ops = {
        "posts": rc.comment(tx_size=300, permlink_length=50, parent_permlink_length=0),
        "votes": rc.vote(tx_size=120),
        "transfers": rc.transfer(tx_size=200, market_op_count=1),
        "custom_json": rc.custom_json(tx_size=500),
    }

    return {
        "account": account_name,
        "rc_pct": status["rc_pct"],
        "available_ops": {name: int(current / cost) if cost > 0 else 0
                          for name, cost in ops.items()},
    }

print(json.dumps(transactions_available("blocktrades"), indent=2))
```

Key points:
- **RC = HP-based**: More HP → more RC capacity. Delegated HP includes RC.
- **Regeneration**: 100% over 5 days, same as voting mana.
- **Dynamic pricing**: RC costs adjust based on blockchain load — busier chain = higher costs.
- **Feeless model**: Users stake HP once and transact for free within their RC budget.'''
    ),
    (
        "hive_economics/account-creation-token-cost",
        r'''How does account creation work on Hive? What is the cost of creating a new account using tokens vs RC?''',
        r'''<think>
There are two ways to create accounts on Hive: (1) claim_account using RC (free
account creation tokens), then create_claimed_account, or (2) account_create with
a HIVE fee (currently 3 HIVE). The RC-based method requires a large amount of RC
(proportional to demand). You first claim a "pending account creation token" by
spending RC, then later use that token to create the account. The HIVE fee method
pays the fee which goes to the new account as HP. Each account needs a minimum
HP balance for RC to function.
</think>

Hive offers two account creation methods: RC-based (free tokens) and direct HIVE fee:

```python
from beem import Hive
from beem.account import Account
from beem.rc import RC

hive = Hive()

def account_creation_costs() -> dict:
    """Compare the two account creation methods."""
    props = hive.get_dynamic_global_properties()

    # Method 1: HIVE fee (account_create operation)
    creation_fee = props.get("account_creation_fee", "3.000 HIVE")

    # Method 2: RC-based (claim_account + create_claimed_account)
    rc = RC(blockchain_instance=hive)
    claim_rc_cost = rc.claim_account(tx_size=200)

    # How much HP needed to claim one account token per day
    # RC regens 20% per day, so max_rc * 0.2 = daily RC budget
    # HP needed = claim_cost / 0.2 / rc_per_vest_factor
    daily_rc = claim_rc_cost / 0.20  # need this as max RC
    # Rough estimate: max_rc ≈ effective_vests * 1e6 (same as mana)
    ratio = float(props["total_vesting_fund_hive"].split()[0]) / \
            float(props["total_vesting_shares"].split()[0])
    hp_needed = (daily_rc / 1_000_000) * ratio

    return {
        "method_1_hive_fee": {
            "operation": "account_create",
            "cost": str(creation_fee),
            "note": "Fee goes to new account as HP (initial delegation)",
        },
        "method_2_rc_claim": {
            "step_1": "claim_account (costs RC, produces pending token)",
            "step_2": "create_claimed_account (uses pending token, free)",
            "rc_cost": f"{claim_rc_cost:,.0f} RC",
            "hp_needed_estimate": f"~{hp_needed:,.0f} HP to claim 1/day",
        },
    }

import json
print(json.dumps(account_creation_costs(), indent=2))

# Check pending claimed accounts
def check_pending_accounts(account_name: str):
    acct = Account(account_name, blockchain_instance=hive)
    pending = acct.json().get("pending_claimed_accounts", 0)
    print(f"{account_name}: {pending} pending account creation tokens")

check_pending_accounts("blocktrades")

# Broadcast: claim a free account token (requires active key + enough RC)
def claim_account_token(creator: str):
    hive_auth = Hive(keys=["5Jyour_active_key_here"])
    op = {
        "type": "claim_account",
        "creator": creator,
        "fee": "0.000 HIVE",  # 0 = use RC instead of HIVE
        "extensions": [],
    }
    hive_auth.broadcast(op)
    print(f"Claimed 1 account creation token for {creator}")

# Broadcast: create account from claimed token
def create_claimed_account(creator: str, new_account: str,
                            owner_key: str, active_key: str,
                            posting_key: str, memo_key: str):
    hive_auth = Hive(keys=["5Jyour_active_key_here"])
    key_auth = lambda k: {"weight_threshold": 1, "account_auths": [],
                           "key_auths": [[k, 1]]}
    op = {
        "type": "create_claimed_account",
        "creator": creator,
        "new_account_name": new_account,
        "owner": key_auth(owner_key),
        "active": key_auth(active_key),
        "posting": key_auth(posting_key),
        "memo_key": memo_key,
        "json_metadata": "{}",
        "extensions": [],
    }
    hive_auth.broadcast(op)
    print(f"Created account @{new_account}")
```

Key points:
- **HIVE fee method**: Simple, costs ~3 HIVE, the fee becomes the new account's starting HP.
- **RC claim method**: Free (no HIVE cost) but requires significant HP for the RC expenditure.
- **Pending tokens**: Claimed tokens don't expire — claim during low demand, create later.
- **RC cost is dynamic**: Increases when many accounts are being created (demand-based pricing).'''
    ),
    (
        "hive_economics/witness-price-feed-mechanism",
        r'''How does the Hive witness price feed work? How do witnesses publish the HIVE/USD price and how is the median calculated?''',
        r'''<think>
Witnesses publish price feeds (HIVE/USD) using the feed_publish operation. The
protocol takes the median of all active witness feeds to determine the "current
median history price." This median price is used for HBD conversions, reward
calculations, and the haircut rule. Feeds are published as base/quote where
base is HBD amount and quote is HIVE amount (so base/quote = HBD per HIVE = USD
price of HIVE). Witnesses should update every hour or when price moves significantly.
The median protects against any single witness publishing a bad price.
</think>

Witnesses publish HIVE/USD price feeds, and the protocol uses the **median** for all economic calculations:

```python
from beem import Hive
from beem.witness import Witness, WitnessesRankedByVote

hive = Hive()

def get_price_feeds(limit: int = 21) -> list[dict]:
    """Fetch price feeds from top witnesses."""
    witnesses = WitnessesRankedByVote(limit=limit, blockchain_instance=hive)

    feeds = []
    for w in witnesses:
        try:
            props = w.json()
            if "hbd_exchange_rate" in props:
                rate = props["hbd_exchange_rate"]
                base = float(rate["base"].split()[0])    # HBD
                quote = float(rate["quote"].split()[0])   # HIVE
                price = base / quote if quote > 0 else 0
                last_update = props.get("last_hbd_exchange_update", "unknown")
                feeds.append({
                    "witness": w.account.name,
                    "price_usd": round(price, 4),
                    "base": rate["base"],
                    "quote": rate["quote"],
                    "last_update": last_update,
                })
        except Exception:
            continue

    feeds.sort(key=lambda f: f["price_usd"])
    return feeds

# Display feeds and identify the median
feeds = get_price_feeds()
median_idx = len(feeds) // 2

print("=== Witness Price Feeds (sorted) ===")
for i, f in enumerate(feeds):
    marker = " ← MEDIAN" if i == median_idx else ""
    print(f"  {f['witness']:20s}  ${f['price_usd']:.4f}  "
          f"(updated: {f['last_update'][:10]}){marker}")

# Current protocol median
median_price = hive.get_current_median_history()
print(f"\nProtocol median price: {median_price['base']} / {median_price['quote']}")

# Publish a price feed (witness active key required)
def publish_feed(witness_name: str, hive_usd_price: float):
    """
    Publish a HIVE/USD price feed.
    base = HBD amount, quote = HIVE amount
    Convention: base = price * 1000, quote = 1000 HIVE
    """
    hive_auth = Hive(keys=["5Jyour_active_key_here"])

    base_amount = round(hive_usd_price * 1000, 3)
    op = {
        "type": "feed_publish",
        "publisher": witness_name,
        "exchange_rate": {
            "base": f"{base_amount:.3f} HBD",
            "quote": "1000.000 HIVE",
        },
    }
    hive_auth.broadcast(op)
    print(f"Published feed: ${hive_usd_price:.4f}/HIVE")

# Detect stale feeds (>24 hours old)
from datetime import datetime, timedelta
now = datetime.utcnow()
for f in feeds:
    try:
        updated = datetime.strptime(f["last_update"][:19], "%Y-%m-%dT%H:%M:%S")
        age_hours = (now - updated).total_seconds() / 3600
        if age_hours > 24:
            print(f"  WARNING: {f['witness']} feed is {age_hours:.0f}h old!")
    except ValueError:
        pass
```

The median protects the network:
- **No single witness** can manipulate the price — you'd need to compromise 11+ of the top 21.
- **HBD conversions** use this median over a 3.5-day window for even more protection.
- **Stale feeds** are a concern — witnesses should update at least hourly.'''
    ),
    (
        "hive_economics/beneficiary-rewards-setup",
        r'''How do I set up beneficiary rewards on Hive posts? Can you show me how to add beneficiaries to a post so they receive a percentage of rewards?''',
        r'''<think>
Beneficiary rewards are set via the comment_options operation, which must be
broadcast alongside or immediately after the comment (post) operation. Beneficiaries
are specified as an array of {account, weight} where weight is in basis points
(10000 = 100%). The total beneficiary weight cannot exceed 10000. Beneficiaries
come out of the author's 50% share — curators are unaffected. The extension type
is comment_payout_beneficiaries. Once set, beneficiaries cannot be changed.
</think>

Beneficiaries are set via the `comment_options` operation, broadcast with or right after the post:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
import json

def create_post_with_beneficiaries(
    author: str,
    title: str,
    body: str,
    tags: list[str],
    beneficiaries: list[dict],
):
    """
    Create a post with beneficiary rewards.

    Args:
        beneficiaries: [{"account": "user1", "weight": 1000}]
                       weight in basis points (1000 = 10%, 10000 = 100%)
    """
    # Validate beneficiaries
    total_weight = sum(b["weight"] for b in beneficiaries)
    if total_weight > 10000:
        raise ValueError(f"Total beneficiary weight {total_weight} exceeds 10000 (100%)")

    # Must be sorted alphabetically by account name (protocol requirement)
    beneficiaries_sorted = sorted(beneficiaries, key=lambda b: b["account"])

    permlink = title.lower().replace(" ", "-").replace(".", "")[:256]
    json_metadata = json.dumps({"tags": tags, "app": "hiveai/1.0"})

    hive_auth = Hive(keys=["5Jyour_posting_key_here"])

    # Operation 1: The post itself
    comment_op = {
        "type": "comment",
        "parent_author": "",
        "parent_permlink": tags[0] if tags else "general",
        "author": author,
        "permlink": permlink,
        "title": title,
        "body": body,
        "json_metadata": json_metadata,
    }

    # Operation 2: Comment options with beneficiaries
    comment_options_op = {
        "type": "comment_options",
        "author": author,
        "permlink": permlink,
        "max_accepted_payout": "1000000.000 HBD",
        "percent_hbd": 10000,  # 50% HBD (10000 = default)
        "allow_votes": True,
        "allow_curation_rewards": True,
        "extensions": [
            [0, {"beneficiaries": beneficiaries_sorted}]
        ],
    }

    # Broadcast both operations in a single transaction
    hive_auth.broadcast([comment_op, comment_options_op])
    print(f"Post created with {len(beneficiaries)} beneficiaries")

# Example: Post with 3 beneficiaries
create_post_with_beneficiaries(
    author="your-account",
    title="My Post With Beneficiaries",
    body="This post shares rewards with contributors.",
    tags=["hive", "development"],
    beneficiaries=[
        {"account": "dev-fund", "weight": 500},     # 5%
        {"account": "referrer", "weight": 300},      # 3%
        {"account": "hive.fund", "weight": 200},     # 2% to DHF
    ],
)

# Calculate actual payout distribution with beneficiaries
def payout_breakdown(total_hbd: float, beneficiaries: list[dict]):
    curation = total_hbd * 0.50
    author_pool = total_hbd * 0.50

    bene_payouts = {}
    for b in beneficiaries:
        pct = b["weight"] / 10000
        bene_payouts[b["account"]] = round(author_pool * pct, 3)

    author_remaining = author_pool - sum(bene_payouts.values())

    print(f"Total payout: {total_hbd} HBD")
    print(f"  Curators:  {curation:.3f} HBD (50%)")
    print(f"  Author:    {author_remaining:.3f} HBD")
    for acct, amt in bene_payouts.items():
        print(f"  Bene @{acct}: {amt:.3f} HBD ({amt/total_hbd*100:.1f}%)")

payout_breakdown(20.0, [
    {"account": "dev-fund", "weight": 500},
    {"account": "referrer", "weight": 300},
])
```

Important rules:
- **Beneficiaries are immutable** — once set, they cannot be changed or removed.
- **Alphabetical order** — the beneficiary array must be sorted by account name.
- **Author's share only** — beneficiaries reduce the author's 50%, not the curation 50%.
- **Must be set at post time** — `comment_options` must be in the same transaction or the very next one before any votes.'''
    ),
    (
        "hive_economics/decline-voting-rights",
        r'''What does the decline_voting_rights operation do on Hive? When would someone use it and can it be reversed?''',
        r'''<think>
The decline_voting_rights operation permanently removes an account's ability to
vote on content, witnesses, and proposals. It takes 30 days to activate (cooldown
period) and can be cancelled during that window. Once active, it's IRREVERSIBLE.
Use cases include: exchange accounts (to prove they won't use customer funds for
governance), burn accounts, and bot accounts that should not have governance power.
The account retains its HP and can still earn curation as a delegatee but cannot
cast votes. It also cannot vote on DHF proposals or witnesses.
</think>

The `decline_voting_rights` operation permanently removes an account's ability to vote — a serious, irreversible action:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta

hive = Hive()

def check_voting_rights(account_name: str) -> dict:
    """Check if an account has declined voting rights."""
    acct = Account(account_name, blockchain_instance=hive)
    data = acct.json()

    can_vote = data.get("can_vote", True)

    # Check for pending decline (30-day cooldown)
    # This would appear in account's pending operations
    return {
        "account": account_name,
        "can_vote": can_vote,
        "status": "Active voter" if can_vote else "VOTING RIGHTS DECLINED (permanent)",
    }

# Check some well-known accounts
for name in ["blocktrades", "steem", "null"]:
    try:
        result = check_voting_rights(name)
        print(f"  @{result['account']}: {result['status']}")
    except Exception as e:
        print(f"  @{name}: {e}")

def decline_voting_rights(account_name: str, decline: bool = True):
    """
    Decline (or cancel pending decline) voting rights.

    WARNING: Once the 30-day cooldown completes, this is IRREVERSIBLE.

    Args:
        account_name: The account to modify.
        decline: True to start decline, False to cancel during cooldown.
    """
    hive_auth = Hive(keys=["5Jyour_owner_key_here"])  # Requires OWNER key

    op = {
        "type": "decline_voting_rights",
        "account": account_name,
        "decline": decline,
    }
    hive_auth.broadcast(op)

    if decline:
        effective_date = datetime.utcnow() + timedelta(days=30)
        print(f"⚠ Voting rights decline initiated for @{account_name}")
        print(f"  Effective: {effective_date.isoformat()}Z (30-day cooldown)")
        print(f"  Cancel before then with decline=False")
        print(f"  AFTER activation, this is PERMANENT and IRREVERSIBLE")
    else:
        print(f"Decline cancelled for @{account_name}")

# What the account loses:
consequences = """
=== Consequences of Declining Voting Rights ===
LOST permanently:
  - Content voting (upvotes/downvotes)
  - Witness voting
  - DHF/DAO proposal voting
  - Proxy setting

RETAINED:
  - HP ownership and power down ability
  - Receiving delegations
  - Transfers and trading
  - Posting and commenting
  - RC for transactions
  - Earning HP from curation (if delegated to)

USE CASES:
  - Exchange accounts (prove no governance influence with customer funds)
  - Burn/null accounts
  - Service accounts that should remain governance-neutral
"""
print(consequences)
```

Critical details:
- **Owner key required** — this is a high-security operation.
- **30-day cooldown** — can cancel during this window with `decline: false`.
- **Irreversible after activation** — there is no operation to restore voting rights.
- **Governance neutrality** — primarily used by exchanges to demonstrate they won't use customer stake for governance.'''
    ),
    (
        "hive_economics/virtual-supply-market-cap",
        r'''How do I calculate Hive's virtual supply and market cap? What's the difference between current supply and virtual supply?''',
        r'''<think>
Current supply is the actual HIVE in existence (liquid + staked). Virtual supply
adds the HIVE-equivalent of all outstanding HBD at the current feed price. So
virtual_supply = current_supply + (hbd_supply * feed_price_hive_per_hbd). This
matters because HBD represents a claim on HIVE — if all HBD holders converted,
that's how much HIVE would exist. Market cap can be calculated using either
measure. The haircut rule kicks in when HBD > 30% of virtual supply by HIVE-equivalent
value. I'll show how to pull and calculate all of these.
</think>

Virtual supply accounts for all HIVE that would exist if every HBD were converted — it's the "true" total supply:

```python
from beem import Hive
import json

hive = Hive()

def calculate_supply_metrics() -> dict:
    """Calculate all Hive supply metrics and market cap estimates."""
    props = hive.get_dynamic_global_properties()
    price = hive.get_current_median_history()

    # Raw values
    current_supply = float(props["current_supply"].split()[0])
    virtual_supply = float(props["virtual_supply"].split()[0])
    current_hbd_supply = float(props["current_hbd_supply"].split()[0])

    # Vesting
    total_vesting_fund = float(props["total_vesting_fund_hive"].split()[0])
    liquid_hive = current_supply - total_vesting_fund

    # Price
    hbd_per_hive = float(price["base"].split()[0]) / float(price["quote"].split()[0])
    hive_per_hbd = 1 / hbd_per_hive if hbd_per_hive > 0 else 0

    # Virtual supply verification
    # virtual_supply ≈ current_supply + (hbd_supply * hive_per_hbd)
    calculated_virtual = current_supply + (current_hbd_supply * hive_per_hbd)

    # HBD debt ratio (haircut triggers at 30%)
    hbd_value_in_hive = current_hbd_supply * hive_per_hbd
    debt_ratio = (hbd_value_in_hive / virtual_supply * 100) if virtual_supply > 0 else 0

    # Market cap estimates (need external HIVE/USD price for real market cap)
    hive_usd = hbd_per_hive  # approximation: 1 HBD ≈ 1 USD

    return {
        "supply": {
            "current_supply": f"{current_supply:,.3f} HIVE",
            "virtual_supply": f"{virtual_supply:,.3f} HIVE",
            "hbd_supply": f"{current_hbd_supply:,.3f} HBD",
            "liquid_hive": f"{liquid_hive:,.3f} HIVE",
            "staked_hive": f"{total_vesting_fund:,.3f} HIVE",
            "staked_pct": f"{total_vesting_fund / current_supply * 100:.1f}%",
        },
        "virtual_supply_check": {
            "protocol_value": round(virtual_supply, 3),
            "calculated": round(calculated_virtual, 3),
            "match": abs(virtual_supply - calculated_virtual) < 1,
        },
        "hbd_debt": {
            "hbd_as_hive": f"{hbd_value_in_hive:,.3f} HIVE",
            "debt_ratio": f"{debt_ratio:.2f}%",
            "haircut_threshold": "30%",
            "haircut_active": debt_ratio >= 30,
        },
        "market_cap_estimate": {
            "hive_price_usd": f"${hive_usd:.4f}",
            "market_cap_current": f"${current_supply * hive_usd:,.0f}",
            "market_cap_virtual": f"${virtual_supply * hive_usd:,.0f}",
            "fully_diluted": "N/A (no max supply, inflationary)",
        },
    }

metrics = calculate_supply_metrics()
print(json.dumps(metrics, indent=2))

# Monitor HBD debt ratio over time (important for stability)
def haircut_warning(debt_ratio_pct: float):
    """
    When HBD debt > 30% of virtual supply:
    - HBD→HIVE conversions pay less than $1 of HIVE per HBD
    - This protects HIVE from hyperinflation via HBD printing
    - Effectively caps HBD supply relative to HIVE market cap
    """
    if debt_ratio_pct >= 30:
        discount = (30 / debt_ratio_pct)
        print(f"HAIRCUT ACTIVE: HBD conversions pay ${discount:.2f} instead of $1.00")
    elif debt_ratio_pct >= 25:
        print(f"WARNING: Debt ratio {debt_ratio_pct:.1f}% approaching 30% haircut")
    else:
        print(f"Debt ratio {debt_ratio_pct:.1f}% — healthy (< 30%)")

haircut_warning(float(metrics["hbd_debt"]["debt_ratio"].rstrip("%")))
```

Key distinctions:
- **Current supply**: Actual HIVE tokens in existence (liquid + staked).
- **Virtual supply**: Current supply + HIVE-equivalent of all HBD — the "worst case" supply.
- **Debt ratio**: HBD-as-HIVE / virtual_supply — triggers haircut at 30% to prevent death spiral.
- **Market cap**: Use virtual supply for conservative valuation since HBD represents potential HIVE.'''
    ),
]
