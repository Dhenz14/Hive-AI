# Hive Economics & Resource Credits

## Token System
| Token | Purpose | Decimal | Notes |
|-------|---------|---------|-------|
| HIVE | Governance, transfers, staking | 3 (`1.000`) | Inflationary (~1%/yr, decreasing) |
| HBD | Stablecoin pegged to ~$1 USD | 3 (`1.000`) | 20% APR in savings |
| VESTS | Internal unit for Hive Power | 6 (`1.000000`) | Not directly tradeable |
| HP (Hive Power) | Staked HIVE (displayed as HP) | — | HP = VESTS converted at current ratio |

### Conversions
```python
# VESTS ↔ HP (changes over time as new HIVE is printed)
hp = hive.vests_to_hp(vests)  # beem
vests = hive.hp_to_vests(hp)

# HBD → HIVE conversion (3.5 day delay, uses median price feed)
hive.convert("username", amount=10.0)  # 10 HBD → ~10 USD worth of HIVE

# Collateralized conversion: HIVE → HBD (also 3.5 day delay)
hive.collateralized_convert("username", amount=10.0)  # 10 HIVE → HBD
```

## Resource Credits (RC) — Feeless Transaction System
Hive has NO transaction fees. Instead, staked HP grants Resource Credits that regenerate over time.

### How RC Works
- **RC = bandwidth quota** tied to your HP stake
- **Regenerates**: 20% per day (full recharge in 5 days), linear
- **Each operation costs RC** proportional to its size and type
- **Zero HP = zero RC** = can't transact (new accounts get delegated RC)

### RC Costs (approximate)
| Operation | RC Cost | Notes |
|-----------|---------|-------|
| Comment/Post | ~1.2B RC | ~6 HP covers a few posts/day |
| Vote | ~100M RC | Very cheap |
| Transfer | ~400M RC | |
| Custom JSON | ~200M-1B RC | Depends on payload size |
| Claim account | ~5T RC | Free account creation token |

### Check RC
```python
acc = Account("username", blockchain_instance=hive)
rc = acc.get_rc_manabar()
print(f"RC: {rc['current_mana']:,} / {rc['max_mana']:,}")
print(f"Percentage: {rc['current_pct']:.1f}%")
```

```javascript
const rc = await client.rc.getRCMana("username");
console.log(`RC: ${rc.current_mana} / ${rc.max_mana}`);
console.log(`Pct: ${(rc.percentage / 100).toFixed(1)}%`);
```

### RC Delegation
```python
# Delegate RC without delegating HP (since HF26)
h.custom_json("rc", json_data={
    "action": "delegate_rc",
    "delegatees": ["newuser"],
    "max_rc": 5000000000  # 5 billion RC
}, required_posting_auths=["delegator"])
```

## Voting & Curation

### Voting Power
- **100% VP** = full-strength vote. Decays 2% per full-strength vote
- **Regenerates**: 20% per day (same as RC)
- **Vote weight**: -100% to +100% (accounts with <500 HP: fixed 100% only)
- **Dust threshold**: Votes worth < ~$0.02 are ignored by the reward system

### Curation Rewards
- **50/50 split**: Author gets 50%, curators get 50% of post rewards
- **Curation window**: Vote in first 24 hours. Earlier votes on posts that become popular earn more
- **Reverse auction removed** (since HF25): No penalty for voting early
- **Self-voting**: Allowed but earns curation on own post (community norms discourage excessive self-voting)

### Reward Calculation
```python
# Get current reward fund
from beem.steem import Steem  # same API
reward_fund = hive.get_reward_funds()
# reward_balance: total HIVE in reward pool
# recent_claims: sum of all rshares recently claimed

# Post payout estimate
rshares = vote_weight * vesting_shares  # simplified
payout_hive = rshares * reward_balance / recent_claims
payout_usd = payout_hive * hive_price
```

### Reward Timing
- **Payout window**: 7 days after posting
- **Author can choose**: 50/50 (HP + HBD) or 100% HP
- **Declined payouts**: Author can set max_accepted_payout to 0
- **Beneficiaries**: Route % of rewards to other accounts (set at post time, immutable)

```python
# Post with beneficiaries
h.post("Title", "Body", author="author", tags=["hive"],
       beneficiaries=[
           {"account": "app_fee", "weight": 500},   # 5%
           {"account": "curator", "weight": 1000},   # 10%
       ])
```

## Power Up / Power Down
- **Power Up**: HIVE → HP (instant, minimum 0.001 HIVE)
- **Power Down**: HP → HIVE (13 weekly payments over ~13 weeks)
- **Cancel power down**: Anytime, remaining HP stays staked

```python
hive.power_up(10.0, account="username")         # Instant
hive.power_down(1000.0, account="username")     # 13-week schedule
hive.power_down(0, account="username")          # Cancel
```

## HBD Savings (20% APR)
```python
hive.transfer_to_savings("username", 100.0, "HBD", memo="savings")
# Interest accrues continuously, paid on any savings operation
# Withdrawal: 3-day wait
hive.transfer_from_savings("username", request_id=1, amount=50.0, asset="HBD")
```

## Delegation
```python
# Delegate HP to another account (they get voting/RC power, you keep ownership)
hive.delegate_vesting_shares("delegatee", vesting_shares="1000.000000 VESTS",
                              account="delegator")
# Undelegate (5-day cooldown before VESTS return)
hive.delegate_vesting_shares("delegatee", vesting_shares="0.000000 VESTS",
                              account="delegator")
```
