# Hive Economics & Resource Credits Skill File

## Resource Credits (RC) System

### How RC Works
- RC is the "gas" system for Hive, but transactions are feeless to end users
- Every account gets RC proportional to their Hive Power (HP)
- RC regenerates linearly over **5 days** (20% per day)
- RC is **non-transferable** but can be **delegated** (since HF26)
- Operations consume RC based on three resource costs:
  1. **Blockchain size** (history_bytes) - how much storage the operation uses
  2. **Compute time** (execution_time) - CPU cycles to process
  3. **State size** (state_bytes) - impact on shared memory state

### RC Cost Factors by Operation Type
| Operation | Relative Cost | Notes |
|-----------|--------------|-------|
| Vote | Very low | Minimal state change |
| Comment/Post | Medium | Body stored in block |
| Custom JSON | Low-Medium | Up to 8KB payload |
| Transfer | Low | Simple state update |
| Account Creation | Very high | New state entry |
| Claim Account | Very high | Pre-pays account creation |
| Power Up/Down | Low | State update |

### Checking RC with beem (Python)

```python
from beem import Hive
from beem.account import Account
from beem.rc import RC

hive = Hive()
acc = Account("username", blockchain_instance=hive)

# Get current RC status
manabar = acc.get_rc_manabar()
print(f"Current RC: {manabar['current_mana']:,.0f}")
print(f"Max RC: {manabar['max_mana']:,.0f}")
print(f"RC percentage: {manabar['current_mana_pct']:.2f}%")
print(f"Time to full recharge: {manabar['estimated_pct']}")

# Calculate operation costs
rc = RC(blockchain_instance=hive)
print(f"Comment cost: {rc.comment():,.0f} RC")
print(f"Vote cost: {rc.vote():,.0f} RC")
print(f"Transfer cost: {rc.transfer():,.0f} RC")
print(f"Custom JSON cost: {rc.custom_json():,.0f} RC")

# How many operations can this account do?
current = manabar['current_mana']
print(f"Possible comments: {int(current / rc.comment())}")
print(f"Possible votes: {int(current / rc.vote())}")
print(f"Possible custom_json: {int(current / rc.custom_json())}")
```

### Checking RC via API (Direct)

```bash
# Using rc_api.find_rc_accounts
curl -s -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"rc_api.find_rc_accounts","params":{"accounts":["username"]},"id":1}' \
  https://api.hive.blog

# Response structure:
# {
#   "rc_accounts": [{
#     "account": "username",
#     "rc_manabar": {
#       "current_mana": "12345678900",
#       "last_update_time": 1700000000
#     },
#     "max_rc_creation_adjustment": {"amount": "...", "precision": 6, "nai": "@@000000037"},
#     "max_rc": "50000000000"
#   }]
# }

# Get resource parameters (cacheable - only changes with hived upgrades)
curl -s -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"rc_api.get_resource_params","params":{},"id":1}' \
  https://api.hive.blog
```

### RC Delegation

```python
from beem import Hive

hive = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])

# Delegate RC to another account (requires active key)
hive.custom_json(
    id="rc",
    json_data=["delegate_rc", {
        "from": "myaccount",
        "delegatees": ["newuser"],
        "max_rc": 5000000000  # amount of RC to delegate
    }],
    required_auths=["myaccount"]
)
```

---

## Voting Mechanics

### Voting Power (Mana)
- Each account has a **voting mana** pool (similar to RC mana)
- Full voting mana = 100%
- A 100% upvote consumes **2% of current voting mana**
- Mana regenerates linearly over **5 days** (20% per day)
- At 100% mana, you can cast ~10 full-power votes per day
- Voting at less than 100% weight uses proportionally less mana

### Vote Weight
- Weight range: **-10000 to +10000** (representing -100% to +100%)
- Positive = upvote, Negative = downvote
- Accounts with < 50 HP cannot adjust vote weight (always 100%)
- Vote value = f(voter_HP, voting_mana, vote_weight, reward_fund)

### Downvote Mana Pool
- Separate mana pool specifically for downvotes
- **25% of total voting mana** available as free downvotes
- Downvotes beyond the free pool consume regular voting mana
- Regenerates at the same 5-day rate

### Calculating Vote Value

```python
from beem import Hive
from beem.account import Account

hive = Hive()
acc = Account("username", blockchain_instance=hive)

# Get voting value at current mana
vp = acc.get_voting_power()  # percentage 0-100
print(f"Voting Power: {vp:.2f}%")

# Estimate vote value in USD
vote_value = acc.get_voting_value_SBD()  # returns estimated $ value of 100% upvote
print(f"Full vote value: ${vote_value:.4f}")

# Get dynamic global properties for manual calculation
props = hive.get_dynamic_global_properties()
reward_fund = hive.get_reward_funds()
price_feed = hive.get_current_median_history()
```

### Manual Vote Value Formula
```
rshares = vesting_shares * voting_power * vote_weight / (10000 * 50)
vote_value = rshares * reward_balance / recent_claims * price_feed
```

Where:
- `vesting_shares`: Account's vesting shares (HP in VESTS)
- `voting_power`: Current mana percentage (0-10000)
- `vote_weight`: Vote weight (-10000 to 10000)
- `reward_balance`: Current reward fund balance
- `recent_claims`: Total recent claims against the reward fund
- `price_feed`: Median HBD price feed from witnesses

---

## Curation Rewards

### How Curation Works (Post-HF25)
- **50/50 split**: Author gets 50%, curators get 50% of post rewards
- **No early voting penalty**: Since HF25, there is no reverse auction window
  (previously voting in the first 5 minutes penalized curators)
- **Linear curation**: Rewards are distributed proportionally to rshares
- Curation rewards are paid in **Hive Power (HP)**

### Curation Reward Distribution
- Each curator's share = their rshares / total rshares on the post
- Earlier voters do NOT get a bonus over later voters (post-HF25)
- Downvotes reduce total post rewards but earn no curation

### Maximizing Curation
- Vote on content likely to receive more votes after you
- Maintain consistent voting to keep mana around 80%
- Use vote weight wisely - don't drain mana on low-value votes

---

## Reward Pool Mechanics

### How the Reward Pool Works
- A fixed amount of HIVE is added to the reward pool each block (~3 seconds)
- The pool is called the **reward fund** (`get_reward_fund` API)
- Key fields:
  - `reward_balance`: Total HIVE available for distribution
  - `recent_claims`: Sum of all rshares² claims in the recent window
  - `content_constant`: Constant used in reward curve calculation

### Reward Curve
- **Convergent linear** reward curve (since HF25)
- Small posts earn proportionally to their rshares
- Very large posts see diminishing returns
- Prevents extreme concentration of rewards

### Payout Windows
- Posts pay out **after 7 days**
- After payout, no more votes can change rewards
- Authors can choose payout options:
  - 50% HP / 50% HBD (default)
  - 100% HP (Power Up)
  - Decline payout

### Checking Reward Fund

```python
from beem import Hive

hive = Hive()

# Get reward fund info
reward_fund = hive.get_reward_funds()
print(f"Reward balance: {reward_fund['reward_balance']}")
print(f"Recent claims: {reward_fund['recent_claims']}")
print(f"Content constant: {reward_fund['content_constant']}")

# Get current price feed
price = hive.get_current_median_history()
print(f"Base: {price['base']}")       # e.g., "0.350 HBD"
print(f"Quote: {price['quote']}")     # e.g., "1.000 HIVE"
```

---

## HBD (Hive Backed Dollars)

### Interest on Savings
- HBD in **savings** earns interest (currently ~15% APR, set by witness median)
- HBD in liquid balance earns **no interest**
- Interest rate is the **median** of top 20 witnesses' settings
- Interest compounds and is paid when any savings operation occurs

### Savings Mechanics
- 3-day withdrawal delay for security
- No delay for deposits
- Transfer between own liquid and savings balance

### HBD Conversions

**HBD -> HIVE Conversion:**
- `convert` operation: Converts HBD to HIVE
- Uses 3.5-day median price
- Takes **3.5 days** to complete
- No fee on HBD->HIVE conversion
- Result: HIVE at the 3.5-day median price

**HIVE -> HBD Conversion (Collateralized):**
- `collateralized_convert` operation (since HF25)
- Converts HIVE to HBD immediately
- 5% fee burned
- HIVE collateral locked for 3.5 days
- If HIVE price drops, you may get less back

### HBD Stabilization
- If HBD supply exceeds ~10% of HIVE market cap, the blockchain reduces HBD payouts
- Haircut rule: HBD printing stops when debt ratio is too high
- Witnesses set the price feed that anchors HBD to ~$1 USD

```python
from beem import Hive
from beem.account import Account

hive = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])
acc = Account("myaccount", blockchain_instance=hive)

# Transfer HBD to savings (starts earning interest)
acc.transfer_to_savings(100.0, "HBD", memo="earn interest")

# Withdraw from savings (3-day delay)
acc.transfer_from_savings(50.0, "HBD", memo="withdrawal", request_id=1)

# Convert HBD to HIVE (3.5-day process)
acc.convert("50.000 HBD")

# Check savings balance
print(acc["savings_balance"])       # HIVE in savings
print(acc["savings_hbd_balance"])   # HBD in savings
```

---

## Witness Voting & Governance

### Witness System
- Top 20 witnesses produce blocks in round-robin order
- 21st slot rotates among backup witnesses by vote weight
- Each round = 21 blocks (~63 seconds)
- Witnesses set key parameters:
  - HBD interest rate
  - Account creation fee
  - Maximum block size
  - Price feed (HBD/HIVE)

### Voting for Witnesses
- Each account can vote for up to **30 witnesses**
- Votes are weighted by the voter's HP (vesting shares)
- Votes persist until removed (no expiration)
- Proxy voting: delegate your witness votes to another account

```python
from beem import Hive
from beem.account import Account
from beem.witness import Witness

hive = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])
acc = Account("myaccount", blockchain_instance=hive)

# Vote for a witness
acc.approvewitness("witnessname")

# Remove witness vote
acc.disapprovewitness("witnessname")

# Set a proxy (delegate all witness + proposal votes)
acc.set_proxy("proxyaccount")

# Clear proxy
acc.set_proxy("")

# Get witness info
w = Witness("witnessname", blockchain_instance=hive)
print(f"Votes: {w['votes']}")
print(f"HBD interest rate: {w['props']['hbd_interest_rate'] / 100}%")
print(f"Account creation fee: {w['props']['account_creation_fee']}")
print(f"Feed price: {w['hbd_exchange_rate']}")
```

### DHF (Decentralized Hive Fund) / Proposals
- Community treasury funded by a portion of inflation
- Anyone can create proposals requesting HBD funding
- HP holders vote to approve/reject proposals
- Proposals above the "return proposal" threshold receive funding
- Daily payouts to approved proposals

```python
from beem import Hive

hive = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])

# Vote for a proposal
hive.update_proposal_votes([proposal_id], approve=True, account="myaccount")

# Vote against (remove approval)
hive.update_proposal_votes([proposal_id], approve=False, account="myaccount")
```

---

## Token Economics Summary

### HIVE Token
- Governance token, stakeable as Hive Power (HP)
- ~3% annual inflation (decreasing 0.01% per 250k blocks, floor 0.95%)
- Inflation split: 65% reward pool, 15% HP interest, 10% witnesses, 10% DHF

### Hive Power (HP)
- Staked HIVE, represented internally as VESTS
- 13-week power-down period (paid in 13 weekly installments)
- Determines: voting influence, RC generation, governance weight
- Can be delegated to other accounts (instant delegation, 5-day undelegate cooldown)

### HBD (Hive Backed Dollars)
- Algorithmic stablecoin pegged to $1 USD
- Earnable through content rewards or conversions
- Savings earn witness-set interest rate
- Convertible to HIVE via 3.5-day conversion
