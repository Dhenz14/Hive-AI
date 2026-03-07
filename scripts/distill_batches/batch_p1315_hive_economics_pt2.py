"""Hive economics training pairs (part 2a): delegation ROI, analytics, advanced tokenomics."""

PAIRS = [
    (
        "hive_economics/delegation-roi-calculator",
        r'''How do I calculate delegation ROI on Hive? I want to compare delegating to different curation services.''',
        r'''<think>
Delegation ROI depends on the daily rewards returned by the delegatee.
Need to track outgoing delegation amount in HP, then measure incoming
liquid HIVE/HBD payments over time. Compare annualized return against
the HP delegated. Should fetch account history to find transfer memos
referencing delegation payouts and compute APR.
</think>

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta

def delegation_roi(delegator: str, delegatee: str, days: int = 30):
    acc = Account(delegator)
    cutoff = datetime.utcnow() - timedelta(days=days)
    # find active delegation amount
    delegated_hp = 0.0
    for d in acc.get_vesting_delegations():
        if d["delegatee"] == delegatee:
            delegated_hp = float(acc.blockchain.vests_to_hp(d["vesting_shares"]))
    if delegated_hp == 0:
        return {"error": "No active delegation found"}
    # sum payouts from delegatee
    total_earned = 0.0
    for op in acc.history(start=cutoff, only_ops=["transfer"]):
        if op["from"] == delegatee:
            amt, symbol = op["amount"].split()
            total_earned += float(amt)
    daily_avg = total_earned / days
    apr = (daily_avg * 365 / delegated_hp) * 100
    return {"delegated_hp": delegated_hp, "earned_30d": total_earned,
            "daily_avg": daily_avg, "apr_pct": round(apr, 2)}
```'''
    ),
    (
        "hive_economics/curation-apr-estimation",
        r'''Write a script to estimate my curation APR on Hive based on recent curation rewards.''',
        r'''<think>
Curation APR = (annualized curation rewards / effective HP) * 100.
Pull recent curation_reward ops from account history, sum the vesting
payout over a window (e.g. 7 days), convert VESTS to HP, then
annualize. Effective HP includes own HP plus any received delegations
minus outgoing delegations.
</think>

```python
from beem.account import Account
from datetime import datetime, timedelta

def curation_apr(username: str, window_days: int = 7):
    acc = Account(username)
    cutoff = datetime.utcnow() - timedelta(days=window_days)
    total_vests = 0.0
    for op in acc.history(start=cutoff, only_ops=["curation_reward"]):
        vests = float(op["reward"].split()[0])
        total_vests += vests
    earned_hp = float(acc.blockchain.vests_to_hp(total_vests))
    effective_hp = acc.get_steem_power(onlyOwnSP=False)
    if effective_hp == 0:
        return 0.0
    apr = (earned_hp / window_days * 365 / effective_hp) * 100
    return round(apr, 2)

# Usage: print(f"Curation APR: {curation_apr('myaccount')}%")
```'''
    ),
    (
        "hive_economics/optimal-voting-strategy",
        r'''How should I optimize my Hive voting to maximize curation returns? Show the math behind vote timing and mana usage.''',
        r'''<think>
Curation rewards follow a square-root convergence curve — early voters
get more if the post gains value, but risk zero on flops. Vote value
scales linearly with voting mana (recharges 20% per day from current
level). Optimal strategy: avoid draining below ~80% mana, vote on
posts likely to attract larger votes after you. The vote's rshares
depend on effective_vests * (current_mana/max_mana) * weight/10000.
</think>

```python
def vote_value_at_mana(hp: float, mana_pct: float, weight_pct: float,
                       reward_fund_rshares: float, reward_balance_hive: float,
                       hive_price_usd: float) -> float:
    """Estimate vote value in USD given current mana level."""
    vests_per_hp = 1805.0  # approximate, fetch from dynamic props
    eff_vests = hp * vests_per_hp * 1e6
    rshares = eff_vests * (mana_pct / 100) * (weight_pct / 100) * 0.02
    vote_val = (rshares / reward_fund_rshares) * reward_balance_hive * hive_price_usd
    return round(vote_val, 4)

def daily_votes_at_target_mana(min_mana: float = 80.0, weight: float = 100.0):
    """Max full votes per day to stay above min_mana threshold."""
    # each 100% vote costs 2% of max mana, recharge is 20%/day
    cost_per_vote = 2.0 * (weight / 100)
    usable_mana = 100.0 - min_mana + 20.0  # daily recharge headroom
    return int(usable_mana / cost_per_vote)

# 10 full votes/day keeps mana ~80%: daily_votes_at_target_mana() == 10
```'''
    ),
    (
        "hive_economics/post-payout-prediction",
        r'''Can you build a simple model to predict Hive post payouts based on early votes?''',
        r'''<think>
Early vote data (first N minutes) correlates with final payout. We can
fetch active_votes on a post, sum rshares, then convert to pending HBD
using the reward fund and price feed. A simple linear extrapolation
from votes received in the first hour vs historical final payouts gives
a rough predictor. Key inputs: recent_claims, reward_balance, base price.
</think>

```python
from beem.comment import Comment
from beem import Hive

def predict_payout(author: str, permlink: str) -> dict:
    hive = Hive()
    post = Comment(f"@{author}/{permlink}", blockchain_instance=hive)
    fund = hive.get_reward_funds()["recent_claims"]
    reward_bal = float(hive.get_reward_funds()["reward_balance"].split()[0])
    price = float(hive.get_current_median_history()["base"].split()[0])
    rshares = int(post["net_rshares"])
    estimated_hbd = (rshares / int(fund)) * reward_bal * price
    # author gets 50%, curators 50%
    return {
        "total_pending": round(estimated_hbd, 3),
        "author_hbd": round(estimated_hbd * 0.5, 3),
        "curator_share": round(estimated_hbd * 0.5, 3),
        "vote_count": len(post.get("active_votes", []))
    }
```'''
    ),
    (
        "hive_economics/reward-pool-depletion-model",
        r'''Model how the Hive reward pool gets depleted and replenished over a cycle. Show the math.''',
        r'''<think>
The reward pool (reward_balance) is refilled from inflation at ~1.5%
annually, allocated to content rewards. The pool depletes as posts pay
out after 7 days. recent_claims tracks total rshares claimed. The pool
targets equilibrium: high claiming drains it (lower per-vote value),
low activity lets it accumulate. We can model daily inflow from
inflation vs outflow from payouts to see net pool trajectory.
</think>

```python
def reward_pool_model(current_pool: float, daily_posts: int,
                      avg_rshares_per_post: float, total_supply: float,
                      inflation_rate: float = 0.015, days: int = 30):
    """Simulate reward pool balance over N days."""
    content_share = 0.65  # 65% of inflation to content rewards
    daily_inflow = (total_supply * inflation_rate / 365) * content_share
    trajectory = []
    pool = current_pool
    for day in range(1, days + 1):
        # posts from 7 days ago pay out today
        daily_outflow = min(pool * 0.08, daily_posts * avg_rshares_per_post * pool / 1e15)
        pool = pool + daily_inflow - daily_outflow
        trajectory.append({"day": day, "pool": round(pool, 2),
                           "inflow": round(daily_inflow, 2),
                           "outflow": round(daily_outflow, 2)})
    return trajectory

# Equilibrium: when daily_inflow == daily_outflow
```'''
    ),
    (
        "hive_economics/hp-to-usd-conversion",
        r'''Write a function that converts Hive Power to USD using live chain data.''',
        r'''<think>
HP is stored as VESTS on-chain. Conversion path: HP -> VESTS using
dynamic global properties (total_vesting_shares / total_vesting_fund),
then VESTS -> HIVE, then HIVE -> USD via the internal price feed or an
external API like CoinGecko. The median price feed on-chain only gives
HIVE/HBD, so for true USD we need an external source.
</think>

```python
import requests
from beem import Hive

def hp_to_usd(hp_amount: float) -> dict:
    hive = Hive()
    props = hive.get_dynamic_global_properties()
    total_vests = float(props["total_vesting_shares"].split()[0])
    total_fund = float(props["total_vesting_fund_hive"].split()[0])
    hive_per_hp = total_fund / total_vests * 1e6
    hive_amount = hp_amount * hive_per_hp
    # external USD price
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": "hive", "vs_currencies": "usd"}, timeout=10)
    usd_price = r.json()["hive"]["usd"]
    return {"hp": hp_amount, "hive": round(hive_amount, 3),
            "usd_price": usd_price, "usd_value": round(hive_amount * usd_price, 2)}
```'''
    ),
    (
        "hive_economics/witness-roi-analysis",
        r'''How do I analyze the ROI of running a Hive witness node? Include costs vs block production revenue.''',
        r'''<think>
Witnesses earn per block produced. Top 20 produce every round (21 blocks),
backup witnesses produce proportionally to votes. Revenue = blocks/day *
block_reward. Costs include server (~$40-100/mo), price feed updates, and
time. Need to fetch witness data: total_missed, last_confirmed_block_num,
and calculate production rate. ROI = (annual_revenue - annual_cost) / cost.
A backup witness may only produce a few blocks per day.
</think>

```python
from beem.witness import Witness
from beem import Hive

def witness_roi(witness_name: str, monthly_server_cost: float = 50.0):
    w = Witness(witness_name)
    props = Hive().get_dynamic_global_properties()
    head_block = props["head_block_number"]
    block_reward = 0.395  # HIVE per block (approximate from inflation)
    # estimate blocks/day from ranking
    rank = w.get("rank", 100)
    if rank <= 20:
        blocks_per_day = 1371  # ~21 rounds/hr * 24
    else:
        blocks_per_day = max(1, int(200 / rank))  # rough estimate
    daily_revenue = blocks_per_day * block_reward
    annual_revenue = daily_revenue * 365
    annual_cost = monthly_server_cost * 12
    roi_pct = ((annual_revenue - annual_cost) / annual_cost) * 100
    return {"rank": rank, "blocks_day": blocks_per_day,
            "daily_hive": round(daily_revenue, 2),
            "annual_hive": round(annual_revenue, 2),
            "annual_cost_usd": annual_cost, "roi_pct": round(roi_pct, 1)}
```'''
    ),
    (
        "hive_economics/dhf-proposal-roi-tracking",
        r'''Write code to track DHF (Decentralized Hive Fund) proposal spending vs deliverables for ROI analysis.''',
        r'''<think>
DHF proposals request daily HBD pay. To track ROI, fetch proposal details
via list_proposals API: daily_pay, total_paid, start/end dates, status.
Then compare funding received against deliverable milestones (manual
input or scraped from proposal updates). Automated part: calculate
burn rate, runway, and cost-per-day. ROI judgment requires qualitative
assessment of deliverables against spend.
</think>

```python
from beem import Hive

def dhf_proposal_analysis(proposal_id: int):
    hive = Hive()
    proposals = hive.rpc.list_proposals(
        [proposal_id], 1, "by_proposal_id", "ascending", "all")
    if not proposals:
        return {"error": "Proposal not found"}
    p = proposals[0]
    daily_pay = float(p["daily_pay"]["amount"]) / 1000  # HBD
    total_days = (p["end_date"] - p["start_date"]).days if hasattr(p["end_date"], 'days') else 365
    max_funding = daily_pay * total_days
    total_votes_hp = float(p.get("total_net_votes", 0)) / 1e6
    return {
        "subject": p["subject"],
        "daily_hbd": daily_pay,
        "total_days": total_days,
        "max_funding_hbd": round(max_funding, 2),
        "status": p["status"],
        "net_votes": total_votes_hp,
        "burn_rate_monthly": round(daily_pay * 30, 2)
    }
```'''
    ),
    (
        "hive_economics/inflation-impact-model",
        r'''Model how Hive's decreasing inflation rate impacts token value over time.''',
        r'''<think>
Hive inflation starts at ~0.97% (was 9.5% at launch, decreases 0.01%
per 250k blocks, ~0.5%/year). Inflation splits: 65% content rewards,
15% staking (HP interest), 10% witnesses, 10% DHF. Model: project
supply growth over years, compare to hypothetical demand scenarios.
Lower inflation reduces sell pressure, but actual price depends on
demand. Stock-to-flow ratio improves as inflation drops.
</think>

```python
def inflation_projection(current_supply: float = 420_000_000,
                         current_rate: float = 0.97,
                         years: int = 10):
    """Project HIVE supply and inflation metrics over N years."""
    results = []
    supply = current_supply
    rate = current_rate
    for year in range(1, years + 1):
        new_tokens = supply * (rate / 100)
        supply += new_tokens
        stock_to_flow = supply / new_tokens
        results.append({
            "year": year, "inflation_pct": round(rate, 3),
            "supply": int(supply), "new_tokens": int(new_tokens),
            "stock_to_flow": round(stock_to_flow, 1)
        })
        rate = max(0.095, rate - 0.5)  # floor at 0.095%
    return results

# After 10 years, inflation approaches sub-0.1%, very low dilution
```'''
    ),
    (
        "hive_economics/power-down-opportunity-cost",
        r'''Calculate the opportunity cost of powering down HIVE — what curation/staking rewards am I giving up?''',
        r'''<think>
Power down converts HP to liquid HIVE over 13 weekly installments.
During power down, HP decreases each week so curation rewards and
vote influence decline progressively. Opportunity cost = sum of
foregone curation APR on each week's reduced HP balance, plus lost
HP interest (~3% APR on staked HP). Compare against what you could
earn deploying the liquid HIVE elsewhere (e.g. HBD savings at 15%).
</think>

```python
def powerdown_opportunity_cost(hp_amount: float, curation_apr: float = 8.0,
                               staking_apr: float = 3.0, hbd_savings_apr: float = 15.0):
    """Compare keeping HP staked vs powering down to HBD savings."""
    weekly_installment = hp_amount / 13
    # scenario A: keep staked
    annual_curation = hp_amount * (curation_apr / 100)
    annual_staking = hp_amount * (staking_apr / 100)
    keep_staked_annual = annual_curation + annual_staking
    # scenario B: power down, move to HBD savings weekly
    powerdown_earnings = 0.0
    for week in range(13):
        remaining_hp = hp_amount - (weekly_installment * week)
        weekly_curation = remaining_hp * (curation_apr / 100) / 52
        released = weekly_installment * (13 - week) / 52
        weekly_hbd_yield = released * (hbd_savings_apr / 100) / 52
        powerdown_earnings += weekly_curation + weekly_hbd_yield
    annual_powerdown = powerdown_earnings + hp_amount * (hbd_savings_apr / 100) * (39 / 52)
    return {"keep_staked_annual": round(keep_staked_annual, 2),
            "powerdown_annual": round(annual_powerdown, 2),
            "opportunity_cost": round(keep_staked_annual - annual_powerdown, 2)}
```'''
    ),
    (
        "hive_economics/hbd-peg-stability-analysis",
        r'''Analyze HBD peg stability by tracking the deviation from $1 USD over time.''',
        r'''<think>
HBD is designed to track $1 USD. The peg is maintained by: conversion
mechanism (3.5-day convert to HIVE at feed price), HBD stabilizer
(DHF-funded market buys/sells), and haircut rule (HBD supply capped
at 30% of HIVE mcap). Fetch historical HBD prices, compute deviation
stats (mean, std, max deviation), and flag periods where the peg
broke significantly. Internal price feed is the witness median.
</think>

```python
import requests
import statistics

def hbd_peg_analysis(days: int = 90):
    """Analyze HBD price deviation from $1 peg using CoinGecko data."""
    url = "https://api.coingecko.com/api/v3/coins/hive_dollar/market_chart"
    r = requests.get(url, params={"vs_currency": "usd", "days": days}, timeout=15)
    prices = [p[1] for p in r.json()["prices"]]
    deviations = [abs(p - 1.0) for p in prices]
    peg_breaks = sum(1 for d in deviations if d > 0.05)  # >5% deviation
    return {
        "data_points": len(prices),
        "mean_price": round(statistics.mean(prices), 4),
        "std_dev": round(statistics.stdev(prices), 4),
        "max_deviation_pct": round(max(deviations) * 100, 2),
        "peg_break_count": peg_breaks,
        "peg_hold_pct": round((1 - peg_breaks / len(prices)) * 100, 1),
        "min_price": round(min(prices), 4),
        "max_price": round(max(prices), 4)
    }
```'''
    ),
    (
        "hive_economics/internal-market-hive-hbd-trading",
        r'''Show me how to interact with the Hive internal market for HIVE/HBD trading programmatically.''',
        r'''<think>
The Hive internal market is an on-chain order book for HIVE<->HBD.
Use limit_order_create to place orders, limit_order_cancel to remove.
The order book can be fetched via get_order_book API. Key: orders
fill at the limit price or better. Expiration defaults to 28 days.
For market-making or arbitrage, monitor the spread between top bid
and ask, then place orders to capture the spread.
</think>

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Limit_order_create

def get_spread():
    """Fetch internal market top bid/ask spread."""
    hive = Hive()
    book = hive.rpc.get_order_book(1)
    top_bid = float(book["bids"][0]["real_price"]) if book["bids"] else 0
    top_ask = float(book["asks"][0]["real_price"]) if book["asks"] else 999
    spread_pct = ((top_ask - top_bid) / top_ask) * 100
    return {"bid": top_bid, "ask": top_ask, "spread_pct": round(spread_pct, 3)}

def place_buy_order(account: str, hbd_amount: float, price: float, wif: str):
    """Place limit buy order: spend HBD to get HIVE at price."""
    hive = Hive(keys=[wif])
    hive_to_receive = round(hbd_amount / price, 3)
    hive.limit_order_create(
        hbd_amount, "HBD", hive_to_receive, "HIVE",
        expiration=3600 * 24 * 7, account=account)
```'''
    ),
    (
        "hive_economics/effective-voting-power-calculator",
        r'''Build a calculator that shows my effective voting power on Hive, accounting for delegations and mana regeneration.''',
        r'''<think>
Effective voting power combines own HP + received delegations - outgoing
delegations, scaled by current voting mana percentage. Mana regenerates
linearly at 20% per day (full recharge in 5 days). Current mana is
stored as last_vote_time and voting_manabar.current_mana in account
data. Must calculate time-adjusted mana from last update timestamp.
</think>

```python
from beem.account import Account
from datetime import datetime

def effective_voting_power(username: str) -> dict:
    acc = Account(username)
    own_hp = acc.get_steem_power(onlyOwnSP=True)
    effective_hp = acc.get_steem_power(onlyOwnSP=False)
    delegated_in = effective_hp - own_hp + acc.get_delegated_steem_power()
    delegated_out = acc.get_delegated_steem_power()
    # voting mana calculation
    manabar = acc["voting_manabar"]
    last_update = datetime.strptime(manabar["last_update_time"], "%Y-%m-%dT%H:%M:%S")
    elapsed_sec = (datetime.utcnow() - last_update).total_seconds()
    max_mana = int(acc["post_voting_power"]["amount"])
    current_mana = min(max_mana,
        int(manabar["current_mana"]) + int(max_mana * elapsed_sec / 432000))
    mana_pct = (current_mana / max_mana * 100) if max_mana else 0
    vote_value_hp = effective_hp * (mana_pct / 100) * 0.02  # full weight vote
    return {"own_hp": round(own_hp, 2), "delegated_in": round(delegated_in, 2),
            "delegated_out": round(delegated_out, 2),
            "effective_hp": round(effective_hp, 2),
            "mana_pct": round(mana_pct, 2),
            "full_vote_hp_impact": round(vote_value_hp, 4)}
```'''
    ),
]
