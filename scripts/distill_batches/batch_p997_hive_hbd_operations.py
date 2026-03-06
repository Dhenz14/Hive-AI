"""Hive blockchain training pairs: HBD (Hive Backed Dollars) operations."""

PAIRS = [
    (
        "hive/hbd-savings-operations",
        r'''How do I deposit and withdraw HBD from savings on Hive to earn the 20% APR interest? Show the code.''',
        r'''<think>
The user wants to work with HBD savings for the 20% APR. Let me think about the mechanics here. The deposit should be instant... but what about withdrawals? Could they be instant too? No, wait -- withdrawals have a 3-day waiting period, and that is a deliberate security feature. If someone compromises your active key, you have 3 days to recover your account before they can drain your savings. That is actually quite clever.

Now, how does interest work exactly? I was initially thinking it compounds daily like a traditional savings account, but actually the blockchain calculates interest continuously and only pays it out when you perform a savings operation (deposit, withdrawal, etc.). Hmm, so if you never touch your savings, does the interest just accumulate invisibly? Yes -- it accrues but is not credited to your balance until the next savings operation triggers the interest payment. Therefore making periodic small deposits can force interest collection and improve compounding.

The APR itself -- is it hardcoded at 20%? No, it is set by witness consensus through the hbd_interest_rate parameter. Each witness votes on a rate, and the blockchain uses the median. So the 20% could change if witnesses decide to adjust it.

Which key do these operations need? I considered posting key since savings feel like a "personal" action, but actually all savings operations require the active key because they involve moving funds. Makes sense -- you would not want a compromised posting key to be able to initiate withdrawals.
</think>

HBD (Hive Backed Dollars) savings earn 20% APR interest, set by witness consensus. Here is how to manage savings operations:

```python
from beem import Hive
from beem.account import Account
from beem.amount import Amount
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Transfer_to_savings, Transfer_from_savings,
    Cancel_transfer_from_savings
)
from datetime import datetime, timedelta
import time

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

ACCOUNT = "myaccount"

def deposit_to_savings(amount_hbd):
    """Deposit HBD into savings to earn interest."""
    op = Transfer_to_savings(**{
        "from": ACCOUNT,
        "to": ACCOUNT,  # Can deposit to your own or another account
        "amount": f"{amount_hbd:.3f} HBD",
        "memo": "Earning 20% APR"
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Deposited {amount_hbd:.3f} HBD to savings: {result['id']}")
    return result

def withdraw_from_savings(amount_hbd, request_id=None):
    """Initiate withdrawal from savings (3-day waiting period)."""
    if request_id is None:
        request_id = int(time.time()) % 2**32

    op = Transfer_from_savings(**{
        "from": ACCOUNT,
        "request_id": request_id,
        "to": ACCOUNT,
        "amount": f"{amount_hbd:.3f} HBD",
        "memo": "Withdrawal"
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()

    complete_date = datetime.utcnow() + timedelta(days=3)
    print(f"Withdrawal initiated: {amount_hbd:.3f} HBD")
    print(f"Request ID: {request_id}")
    print(f"Available on: {complete_date.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    return result, request_id

def cancel_withdrawal(request_id):
    """Cancel a pending savings withdrawal."""
    op = Cancel_transfer_from_savings(**{
        "from": ACCOUNT,
        "request_id": request_id
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Cancelled withdrawal request {request_id}: {result['id']}")
    return result

def check_savings_balance(account_name):
    """Check savings balance and pending withdrawals."""
    acct = Account(account_name, hive_instance=hive)
    savings_hbd = acct["savings_hbd_balance"]
    savings_hive = acct["savings_balance"]
    last_interest = acct.get("savings_hbd_last_interest_payment", "")

    print(f"Savings for @{account_name}:")
    print(f"  HBD in savings: {savings_hbd}")
    print(f"  HIVE in savings: {savings_hive}")
    print(f"  Last interest payment: {last_interest}")

    # Check pending withdrawals
    withdrawals = acct.get("savings_withdraws", [])
    if withdrawals:
        print(f"  Pending withdrawals: {len(withdrawals)}")
        for w in withdrawals:
            print(f"    Request {w['request_id']}: {w['amount']} "
                  f"(completes: {w['complete']})")

def estimate_interest(principal_hbd, days=365, apr=20.0):
    """Estimate interest earnings."""
    daily_rate = apr / 100 / 365
    earned = principal_hbd * daily_rate * days
    print(f"Principal: {principal_hbd:.3f} HBD")
    print(f"APR: {apr}%")
    print(f"After {days} days: {principal_hbd + earned:.3f} HBD")
    print(f"Interest earned: {earned:.3f} HBD")
    return earned

# Usage
check_savings_balance(ACCOUNT)
estimate_interest(1000.0, days=365)
# deposit_to_savings(100.0)
# withdraw_from_savings(50.0)
```

The 3-day withdrawal delay is a security feature -- if your keys are compromised, you have time to recover your account before savings are drained. Interest compounds whenever you perform any savings operation (deposit or withdrawal), so periodic small deposits can help maximize compounding.
'''
    ),
    (
        "hive/hbd-conversions",
        r'''How do the HBD conversion mechanisms work on Hive? Explain both convert and collateralized_convert with code examples.''',
        r'''Hive has two conversion mechanisms between HIVE and HBD, each serving different purposes in the stability system:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Convert, Collateralized_convert
from beem.account import Account
import time

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourActiveKey"]
)

ACCOUNT = "myaccount"

def convert_hbd_to_hive(amount_hbd, request_id=None):
    """Convert HBD to HIVE (3.5-day delay, uses median price).

    This operation:
    - Takes your HBD immediately
    - After 3.5 days, gives you HIVE at the median price
    - The median price is calculated at conversion completion time
    - This creates new HIVE (inflationary if HBD > $1)
    - Risk: HIVE price could change during the 3.5-day wait
    """
    if request_id is None:
        request_id = int(time.time()) % 2**32

    op = Convert(**{
        "owner": ACCOUNT,
        "requestid": request_id,
        "amount": f"{amount_hbd:.3f} HBD"
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"HBD->HIVE conversion initiated: {amount_hbd:.3f} HBD")
    print(f"Request ID: {request_id}")
    print("Completes in 3.5 days at the median price at that time")
    return result

def collateralized_convert_hive_to_hbd(amount_hive, request_id=None):
    """Convert HIVE to HBD instantly (collateralized, HF25+).

    This operation:
    - Takes HIVE as collateral (you send more than the HBD value)
    - Gives you HBD immediately at the current median price
    - After 3.5 days, returns excess HIVE collateral
    - Minimum collateral is typically 2x the HBD value
    - This burns HIVE (deflationary if HBD < $1)
    """
    if request_id is None:
        request_id = int(time.time()) % 2**32

    op = Collateralized_convert(**{
        "owner": ACCOUNT,
        "requestid": request_id,
        "amount": f"{amount_hive:.3f} HIVE"
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"HIVE->HBD collateralized conversion: {amount_hive:.3f} HIVE")
    print(f"Request ID: {request_id}")
    print("HBD delivered immediately, excess HIVE returned in 3.5 days")
    return result

def check_conversion_requests(account_name):
    """Check pending conversion requests."""
    acct = Account(account_name, hive_instance=hive)

    # Regular conversions (HBD -> HIVE)
    conversions = acct.get("conversion_requests", [])
    print(f"Pending HBD->HIVE conversions for @{account_name}:")
    for c in conversions:
        print(f"  ID {c['requestid']}: {c['amount']} "
              f"(completes: {c['conversion_date']})")

    # Collateralized conversions (HIVE -> HBD)
    coll = acct.get("collateralized_convert_requests", [])
    print(f"Pending HIVE->HBD conversions for @{account_name}:")
    for c in coll:
        print(f"  ID {c['requestid']}: {c['collateral_amount']} collateral, "
              f"{c['converted_amount']} HBD "
              f"(completes: {c['conversion_date']})")

def check_hbd_metrics():
    """Check current HBD stability metrics."""
    props = hive.rpc.get_dynamic_global_properties()
    current_supply = props["current_supply"]
    hbd_supply = props["current_hbd_supply"]
    virtual_supply = props["virtual_supply"]
    hbd_print_rate = props.get("hbd_print_rate", 10000)

    print(f"HIVE supply:     {current_supply}")
    print(f"HBD supply:      {hbd_supply}")
    print(f"Virtual supply:  {virtual_supply}")
    print(f"HBD print rate:  {hbd_print_rate / 100}%")
    print("(Print rate < 100% means HBD debt ratio is approaching the cap)")

check_hbd_metrics()
```

Summary of the two conversion types:
- convert (HBD->HIVE): Burns HBD, creates HIVE after 3.5 days at median price. Used when HBD trades above $1.
- collateralized_convert (HIVE->HBD): Locks HIVE collateral, gives HBD immediately. Used when HBD trades below $1. Excess collateral returned after 3.5 days.

Together, these two mechanisms form an arbitrage loop that keeps HBD close to $1.
'''
    ),
    (
        "hive/hbd-interest-calculation",
        r'''How is HBD savings interest calculated on the Hive blockchain? Show me the exact formula and how to verify interest payments.''',
        r'''HBD savings interest on Hive is calculated using a simple interest formula applied continuously. Here is the exact mechanism and how to verify it:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta
import json

hive = Hive(node=["https://api.hive.blog"])

def get_hbd_interest_rate():
    """Get the current HBD interest rate from chain properties."""
    props = hive.rpc.get_dynamic_global_properties()
    # hbd_interest_rate is in basis points (1/100 of a percent)
    rate_bps = props.get("hbd_interest_rate", 2000)
    rate_pct = rate_bps / 100
    print(f"Current HBD interest rate: {rate_pct}% APR ({rate_bps} basis points)")
    return rate_bps

def calculate_interest(principal, rate_bps, seconds_elapsed):
    """Calculate HBD interest using the blockchain formula.

    The blockchain uses this formula:
    interest = principal * rate * seconds / (SECONDS_PER_YEAR * 10000)

    Where:
    - principal is in satoshis (1 HBD = 1000 satoshis)
    - rate is in basis points (2000 = 20%)
    - SECONDS_PER_YEAR = 60 * 60 * 24 * 365 = 31536000
    """
    SECONDS_PER_YEAR = 31536000
    # Convert to satoshi precision
    principal_sat = int(principal * 1000)
    interest_sat = (principal_sat * rate_bps * seconds_elapsed) // (SECONDS_PER_YEAR * 10000)
    interest_hbd = interest_sat / 1000

    print(f"Principal:        {principal:.3f} HBD")
    print(f"Rate:             {rate_bps / 100}% APR")
    print(f"Time elapsed:     {seconds_elapsed} seconds "
          f"({seconds_elapsed / 86400:.1f} days)")
    print(f"Interest earned:  {interest_hbd:.3f} HBD")
    return interest_hbd

def verify_interest_payments(account_name, limit=50):
    """Check account history for interest payment operations."""
    acct = Account(account_name, hive_instance=hive)
    history = acct.get_account_history(
        index=-1,
        limit=limit,
        only_ops=["interest"]
    )

    payments = []
    for entry in history:
        op = entry["op"]
        if isinstance(op, list):
            op_data = op[1]
        else:
            op_data = op

        payments.append({
            "block": entry.get("block"),
            "timestamp": entry.get("timestamp"),
            "owner": op_data.get("owner"),
            "interest": op_data.get("interest"),
            "is_saved_into_hbd_balance": op_data.get("is_saved_into_hbd_balance", True)
        })

    print(f"\nInterest payments for @{account_name}:")
    for p in payments:
        print(f"  {p['timestamp']}: {p['interest']}")

    return payments

def project_annual_earnings(account_name):
    """Project annual HBD earnings from savings."""
    acct = Account(account_name, hive_instance=hive)
    savings_str = str(acct["savings_hbd_balance"])
    # Parse "123.456 HBD" format
    savings_amount = float(savings_str.split()[0])

    rate_bps = get_hbd_interest_rate()
    rate_decimal = rate_bps / 10000

    annual_interest = savings_amount * rate_decimal
    monthly_interest = annual_interest / 12
    daily_interest = annual_interest / 365

    print(f"\nProjected earnings for @{account_name}:")
    print(f"  Savings balance:   {savings_amount:.3f} HBD")
    print(f"  Daily interest:    {daily_interest:.3f} HBD")
    print(f"  Monthly interest:  {monthly_interest:.3f} HBD")
    print(f"  Annual interest:   {annual_interest:.3f} HBD")

    return {
        "principal": savings_amount,
        "daily": daily_interest,
        "monthly": monthly_interest,
        "annual": annual_interest
    }

# Run analysis
rate = get_hbd_interest_rate()
calculate_interest(1000.0, rate, 86400 * 30)  # 30 days on 1000 HBD
verify_interest_payments("hiveio")
project_annual_earnings("hiveio")
```

Key details about interest calculation:
- Interest accrues continuously but is only paid out when a savings operation occurs
- The interest operation is generated automatically by the blockchain
- Interest rate is the median of all witness votes for hbd_interest_rate
- The calculation uses integer arithmetic with satoshi precision (0.001 HBD)
- Interest is paid directly into the savings balance (compounds)
- There is no minimum balance requirement for earning interest
'''
    ),
    (
        "hive/hbd-stabilizer-mechanics",
        r'''How does the HBD stabilizer work on Hive, and how does it interact with the DHF (Decentralized Hive Fund)?''',
        r'''The HBD Stabilizer is a key mechanism that helps maintain the HBD peg to $1 USD. It operates through the Decentralized Hive Fund (DHF) and the internal market. Here is how it works and how to monitor it:

```python
from beem import Hive
from beem.account import Account
from beem.blockchain import Blockchain
import requests
import json

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

def explain_stabilizer_mechanics():
    """The HBD stabilizer mechanism explained."""
    print("""
HBD Stabilizer Flow:
====================

1. The DHF (Decentralized Hive Fund) holds a large HIVE treasury
2. The @hbd.funder proposal receives daily HIVE from the DHF
3. The stabilizer converts this HIVE to HBD on the internal market
4. If HBD > $1: sells HBD on the market, pushing price down
5. If HBD < $1: buys HBD on the market, pushing price up
6. Profits (from arbitrage) are returned to the DHF

This creates a continuous arbitrage loop:
- When HBD > $1: sell HBD -> buy HIVE -> return to DHF
- When HBD < $1: sell HIVE -> buy HBD -> hold until parity

The stabilizer also uses the conversion mechanisms:
- collateralized_convert (HIVE->HBD) when HBD is scarce
- convert (HBD->HIVE) when HBD is oversupplied
""")

def get_internal_market_price():
    """Get the current HBD/HIVE price on the internal market."""
    orders = hive.rpc.get_order_book({"limit": 10}, api="condenser_api")

    if orders["bids"]:
        top_bid = orders["bids"][0]
        bid_price = float(top_bid["real_price"])
        print(f"Top bid (buy HBD): {bid_price:.4f} HIVE/HBD")

    if orders["asks"]:
        top_ask = orders["asks"][0]
        ask_price = float(top_ask["real_price"])
        print(f"Top ask (sell HBD): {ask_price:.4f} HIVE/HBD")

    return orders

def monitor_stabilizer_activity(limit=20):
    """Monitor recent stabilizer account activity."""
    stabilizer_accounts = ["hbd.funder", "hbdstabilizer"]

    for acct_name in stabilizer_accounts:
        try:
            acct = Account(acct_name, hive_instance=hive)
            print(f"\n=== @{acct_name} ===")
            print(f"HIVE balance: {acct['balance']}")
            print(f"HBD balance:  {acct['hbd_balance']}")
            print(f"Savings HBD:  {acct['savings_hbd_balance']}")

            history = acct.get_account_history(
                index=-1,
                limit=limit,
                only_ops=["transfer", "fill_order", "convert",
                          "collateralized_convert"]
            )

            print(f"\nRecent operations:")
            for entry in history:
                op = entry["op"]
                if isinstance(op, list):
                    op_type = op[0]
                    op_data = op[1]
                else:
                    op_type = op["type"].replace("_operation", "")
                    op_data = op.get("value", op)

                ts = entry.get("timestamp", "?")
                if op_type == "transfer":
                    print(f"  [{ts}] transfer: {op_data.get('amount')} "
                          f"from @{op_data.get('from')} to @{op_data.get('to')}")
                elif op_type == "fill_order":
                    print(f"  [{ts}] fill_order: "
                          f"paid {op_data.get('current_pays')} "
                          f"for {op_data.get('open_pays')}")
                elif op_type in ("convert", "collateralized_convert"):
                    print(f"  [{ts}] {op_type}: {op_data.get('amount')}")
        except Exception as e:
            print(f"  Error reading @{acct_name}: {e}")

def check_hbd_debt_ratio():
    """Check the HBD debt ratio (critical for print rate)."""
    props = hive.rpc.get_dynamic_global_properties()
    hbd_supply = props["current_hbd_supply"]
    virtual_supply = props["virtual_supply"]
    hbd_print_rate = props.get("hbd_print_rate", 10000)

    hbd_val = float(str(hbd_supply).split()[0])
    virtual_val = float(str(virtual_supply).split()[0])

    # Approximate debt ratio
    median_price = float(props.get("current_median_history", {}).get("base", "0.001 HBD").split()[0])
    debt_ratio = hbd_val / (virtual_val * median_price) * 100 if median_price > 0 else 0

    print(f"\nHBD Debt Metrics:")
    print(f"  HBD supply:    {hbd_supply}")
    print(f"  Virtual supply:{virtual_supply}")
    print(f"  Median price:  ${median_price:.3f}")
    print(f"  Debt ratio:    ~{debt_ratio:.2f}%")
    print(f"  Print rate:    {hbd_print_rate / 100}%")
    print(f"  (If debt ratio > 10%, HBD printing stops)")

explain_stabilizer_mechanics()
get_internal_market_price()
check_hbd_debt_ratio()
monitor_stabilizer_activity()
```

The stabilizer is a proposal-funded bot, not a consensus-level mechanism. Its effectiveness depends on continued community funding through DHF proposal votes. The combination of the stabilizer, conversion mechanisms, and the 20% savings APR creates strong incentives to keep HBD near its $1 peg.
'''
    ),
    (
        "hive/hbd-defi-strategies",
        r'''What DeFi-like strategies can I implement with HBD on the Hive blockchain? Show me practical code for yield optimization.''',
        r'''HBD offers several DeFi-like strategies on Hive. Here are practical implementations for yield optimization:

```python
from beem import Hive
from beem.account import Account
from beem.amount import Amount
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Transfer_to_savings, Transfer_from_savings,
    Limit_order_create, Limit_order_cancel
)
import time
import json

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourActiveKey"]
)
ACCOUNT = "myaccount"

# Strategy 1: Auto-compound savings interest
class SavingsCompounder:
    """Periodically trigger interest collection by cycling savings."""

    def __init__(self, account, hive_instance):
        self.account = account
        self.hive = hive_instance

    def trigger_interest_payment(self):
        """Any savings operation triggers accrued interest payment.
        We deposit a tiny amount to force interest collection."""
        acct = Account(self.account, hive_instance=self.hive)
        hbd_balance = float(str(acct["hbd_balance"]).split()[0])

        if hbd_balance >= 0.001:
            # Deposit dust to trigger interest
            op = Transfer_to_savings(**{
                "from": self.account,
                "to": self.account,
                "amount": "0.001 HBD",
                "memo": "auto-compound"
            })
            tx = TransactionBuilder(hive_instance=self.hive)
            tx.appendOps(op)
            tx.appendSigner(self.account, "active")
            tx.sign()
            result = tx.broadcast()
            print(f"Interest triggered: {result['id']}")

    def run_monthly(self):
        """Run compounding once per month."""
        while True:
            self.trigger_interest_payment()
            time.sleep(30 * 86400)

# Strategy 2: Internal market arbitrage
class InternalMarketTrader:
    """Trade on the HIVE/HBD internal market."""

    def __init__(self, account, hive_instance):
        self.account = account
        self.hive = hive_instance

    def get_market_price(self):
        """Get current internal market bid/ask."""
        book = self.hive.rpc.get_order_book(
            {"limit": 5}, api="condenser_api"
        )
        top_bid = float(book["bids"][0]["real_price"]) if book["bids"] else 0
        top_ask = float(book["asks"][0]["real_price"]) if book["asks"] else 0
        spread = (top_ask - top_bid) / top_bid * 100 if top_bid > 0 else 0
        return top_bid, top_ask, spread

    def place_limit_order(self, sell_amount, sell_asset, buy_amount, buy_asset,
                          expiration=86400):
        """Place a limit order on the internal market."""
        order_id = int(time.time()) % 2**32
        op = Limit_order_create(**{
            "owner": self.account,
            "orderid": order_id,
            "amount_to_sell": f"{sell_amount:.3f} {sell_asset}",
            "min_to_receive": f"{buy_amount:.3f} {buy_asset}",
            "fill_or_kill": False,
            "expiration": int(time.time()) + expiration
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        result = tx.broadcast()
        print(f"Order placed (ID {order_id}): "
              f"sell {sell_amount:.3f} {sell_asset} "
              f"for {buy_amount:.3f} {buy_asset}")
        return order_id

    def cancel_order(self, order_id):
        """Cancel an open limit order."""
        op = Limit_order_cancel(**{
            "owner": self.account,
            "orderid": order_id
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        return tx.broadcast()

# Strategy 3: Dollar-cost averaging into HBD savings
class DCAStrategy:
    """Regularly convert HIVE to HBD and deposit to savings."""

    def __init__(self, account, hive_instance, weekly_hive_amount=10.0):
        self.account = account
        self.hive = hive_instance
        self.weekly_amount = weekly_hive_amount

    def execute_weekly_dca(self):
        """Buy HBD on internal market and deposit to savings."""
        trader = InternalMarketTrader(self.account, self.hive)
        bid, ask, spread = trader.get_market_price()

        if ask <= 0 or spread > 5.0:
            print(f"Market conditions unfavorable (spread: {spread:.1f}%)")
            return

        # Buy HBD at a slight premium to ensure fill
        hive_to_sell = self.weekly_amount
        hbd_to_receive = hive_to_sell * bid * 0.99  # 1% slippage buffer

        order_id = trader.place_limit_order(
            hive_to_sell, "HIVE",
            hbd_to_receive, "HBD",
            expiration=3600
        )
        print(f"DCA order placed: {hive_to_sell:.3f} HIVE -> "
              f"~{hbd_to_receive:.3f} HBD")

# Usage
compounder = SavingsCompounder(ACCOUNT, hive)
trader = InternalMarketTrader(ACCOUNT, hive)
dca = DCAStrategy(ACCOUNT, hive, weekly_hive_amount=10.0)

bid, ask, spread = trader.get_market_price()
print(f"Market: bid={bid:.4f} ask={ask:.4f} spread={spread:.2f}%")
```

These strategies combine HBD's built-in 20% APR with internal market trading to optimize yield. The auto-compounder ensures interest is collected regularly, the market trader exploits spread opportunities, and the DCA strategy builds savings positions over time. All operations are on-chain, trustless, and require no third-party protocols.
'''
    ),
]
