"""Hive blockchain training pairs: witness operations."""

PAIRS = [
    (
        "hive/witness-price-feed",
        r'''How do I publish a price feed as a Hive witness using Python? What are the best practices for feed publishing?''',
        r'''<think>
Hive witnesses are required to publish a price feed that reports the HIVE/USD exchange rate. This feed is used to:
1. Calculate the conversion rate for HBD (Hive Backed Dollars)
2. Determine the median price used by the blockchain for conversions
3. Affect the HBD print rate and debt ratio calculations

Best practices:
- Publish every hour or when price changes significantly (>3%)
- Use multiple price sources to avoid manipulation
- Add a bias/discount for safety (typically 0-5%)
- Handle API failures gracefully with fallback sources
</think>

Publishing a price feed is one of the core responsibilities of a Hive witness. The blockchain uses the median of all active witness feeds to determine the HIVE/USD price for HBD conversions.

```python
from beem import Hive
from beem.witness import Witness
from beem.amount import Amount
import requests
import time
import statistics

WITNESS_ACCOUNT = "yourwitness"
ACTIVE_KEY = "5YourActivePrivateKey"

def get_hive_price_coingecko():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "hive", "vs_currencies": "usd"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()["hive"]["usd"]

def get_hive_price_binance():
    url = "https://api.binance.com/api/v3/ticker/price"
    params = {"symbol": "HIVEUSDT"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return float(resp.json()["price"])

def get_hive_price_upbit():
    url = "https://api.upbit.com/v1/ticker"
    params = {"markets": "USDT-HIVE"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()[0]["trade_price"]

def get_median_price():
    """Get median price from multiple sources for reliability."""
    prices = []
    sources = [
        ("CoinGecko", get_hive_price_coingecko),
        ("Binance", get_hive_price_binance),
        ("Upbit", get_hive_price_upbit),
    ]
    for name, func in sources:
        try:
            price = func()
            prices.append(price)
            print(f"  {name}: ${price:.4f}")
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    if len(prices) < 2:
        raise ValueError("Not enough price sources available")
    return statistics.median(prices)

def publish_feed(hive_instance, price_usd, bias=0.0):
    """Publish the price feed with optional bias."""
    adjusted = price_usd * (1 + bias)
    base = Amount(f"{adjusted:.3f} HBD")
    quote = Amount("1.000 HIVE")

    witness = Witness(WITNESS_ACCOUNT, hive_instance=hive_instance)
    result = hive_instance.witness_feed_publish(
        base=base,
        quote=quote,
        account=WITNESS_ACCOUNT
    )
    print(f"Published feed: {base}/{quote} (raw: ${price_usd:.4f})")
    return result

def feed_loop(interval=3600, bias=0.0):
    hive = Hive(
        node=["https://api.hive.blog", "https://api.deathwing.me"],
        keys=[ACTIVE_KEY]
    )
    last_price = None
    while True:
        try:
            price = get_median_price()
            pct_change = (abs(price - last_price) / last_price * 100
                          if last_price else 100)
            if pct_change > 3 or last_price is None:
                publish_feed(hive, price, bias)
                last_price = price
            else:
                print(f"Price stable ({pct_change:.1f}%), skipping")
        except Exception as e:
            print(f"Feed error: {e}")
        time.sleep(interval)

if __name__ == "__main__":
    feed_loop(interval=3600, bias=0.0)
```

The feed is published using the active key. The base/quote format means "1 HIVE is worth X HBD." The blockchain takes the median of the top 21 witnesses' feeds to determine the official price used for HBD conversions and the virtual supply calculation.
'''
    ),
    (
        "hive/witness-setup",
        r'''How do I set up a new Hive witness node and register as a witness? Walk me through the complete process.''',
        r'''Setting up a Hive witness involves running a node, generating signing keys, and broadcasting the witness_update operation. Here is the complete process:

**Step 1: Generate a signing key pair**

```python
from beem import Hive
from beemgraphenebase.account import PasswordKey, PrivateKey

# Generate a new key pair for block signing
# NEVER use your owner/active/posting key for block signing
signing_private = PrivateKey()
signing_public = str(signing_private.pubkey)

print(f"Private signing key: {str(signing_private)}")
print(f"Public signing key:  {signing_public}")
# Save the private key securely -- you need it in config.ini
```

**Step 2: Configure the witness node (config.ini)**

```ini
# Minimal witness config.ini
# Place in your hived data directory

# P2P seed nodes
p2p-seed-node = seed.hive.blog:2001
p2p-seed-node = seed.openhive.network:2001
p2p-seed-node = hive-seed.roelandp.nl:2001

# Witness name and signing key
witness = "yourwitness"
private-key = 5YourSigningPrivateKey

# Required plugins for witness
plugin = witness
plugin = p2p
plugin = webserver
plugin = condenser_api
plugin = database_api
plugin = block_api
plugin = rc_api

# Shared memory size (adjust based on your RAM)
shared-file-size = 24G

# WebServer settings (for API access)
webserver-http-endpoint = 0.0.0.0:8091
webserver-ws-endpoint = 0.0.0.0:8090
```

**Step 3: Register as a witness on-chain**

```python
from beem import Hive
from beem.witness import Witness
from beem.amount import Amount

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourActivePrivateKey"]
)

WITNESS = "yourwitness"
SIGNING_PUBLIC_KEY = "STM7abc..."  # from Step 1

# Broadcast witness_update to register
result = hive.witness_update(
    signing_key=SIGNING_PUBLIC_KEY,
    url="https://peakd.com/@yourwitness/witness-post",
    props={
        "account_creation_fee": Amount("3.000 HIVE"),
        "maximum_block_size": 65536,
        "hbd_interest_rate": 2000,  # 20.00% APR in basis points
    },
    account=WITNESS
)
print(f"Witness registered: {result}")

# Verify your witness is registered
w = Witness(WITNESS, hive_instance=hive)
print(f"Witness info: {w.json()}")
print(f"Signing key: {w['signing_key']}")
print(f"Total votes: {w['votes']}")
```

**Step 4: Start the node**

```bash
# Build hived from source or use Docker
docker pull hiveio/hive:latest
docker run -d --name hive-witness \
    -v /data/hive:/hive/data \
    -p 2001:2001 -p 8090:8090 -p 8091:8091 \
    hiveio/hive:latest \
    --data-dir=/hive/data

# Monitor logs
docker logs -f hive-witness
```

After registration, ask the community for witness votes. You need enough votes to get into the top 100+ to have a chance at producing blocks. The top 21 witnesses produce blocks in round-robin order, while backup witnesses produce occasional blocks based on their ranking.
'''
    ),
    (
        "hive/witness-version-tracking",
        r'''How do I track which Hive node version witnesses are running and detect when a hardfork is approaching?''',
        r'''Tracking witness versions is important for monitoring hardfork readiness and network health. Here is a complete solution:

```python
from beem import Hive
from beem.witness import Witness, ListWitnesses
from beem.blockchain import Blockchain
import json
from collections import Counter
from datetime import datetime, timedelta

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

def get_all_witness_versions():
    """Get version info for all active witnesses."""
    # Get top witnesses by vote
    result = hive.rpc.list_witnesses(
        {"start": "", "limit": 100, "order": "by_vote_name"},
        api="database_api"
    )

    witnesses = []
    for w in result.get("witnesses", []):
        witnesses.append({
            "name": w["owner"],
            "version": w.get("running_version", "unknown"),
            "hardfork_version": w.get("hardfork_version_vote", "unknown"),
            "hardfork_time": w.get("hardfork_time_vote", ""),
            "signing_key": w["signing_key"],
            "is_disabled": w["signing_key"] == "STM1111111111111111111111111111111114T1Anm",
            "total_missed": w["total_missed"],
            "votes_mv": int(w["votes"]) / 1e12,
            "last_confirmed_block": w.get("last_confirmed_block_num", 0),
            "feed_age_hours": _feed_age_hours(w),
        })
    return witnesses

def _feed_age_hours(witness_data):
    """Calculate how old the witness price feed is."""
    last_update = witness_data.get("last_hbd_exchange_update", "")
    if not last_update:
        return 999
    try:
        update_time = datetime.strptime(last_update, "%Y-%m-%dT%H:%M:%S")
        age = datetime.utcnow() - update_time
        return age.total_seconds() / 3600
    except (ValueError, TypeError):
        return 999

def hardfork_readiness_report():
    """Generate a hardfork readiness report."""
    witnesses = get_all_witness_versions()
    active = [w for w in witnesses if not w["is_disabled"]]

    # Top 21 consensus witnesses
    top21 = sorted(active, key=lambda x: x["votes_mv"], reverse=True)[:21]

    print("=== Hardfork Readiness Report ===\n")

    # Version distribution for top 21
    version_counts = Counter(w["version"] for w in top21)
    print("Top 21 witness versions:")
    for ver, count in version_counts.most_common():
        pct = count / 21 * 100
        print(f"  {ver}: {count}/21 ({pct:.0f}%)")

    # HF version votes
    hf_votes = Counter(w["hardfork_version"] for w in top21)
    print("\nHardfork version votes (top 21):")
    for ver, count in hf_votes.most_common():
        print(f"  {ver}: {count}/21")
        if count >= 17:
            print(f"  ** HF {ver} has supermajority ({count}/21) **")

    # Witnesses with stale feeds
    stale = [w for w in top21 if w["feed_age_hours"] > 24]
    if stale:
        print(f"\nWARNING: {len(stale)} top-21 witnesses have stale feeds:")
        for w in stale:
            print(f"  {w['name']}: {w['feed_age_hours']:.0f}h old")

    # Missed blocks
    print("\nMissed blocks (top 21):")
    for w in sorted(top21, key=lambda x: x["total_missed"], reverse=True)[:5]:
        print(f"  {w['name']}: {w['total_missed']} missed")

    return top21

# Run the report
report = hardfork_readiness_report()
```

A hardfork activates when 17 of the top 21 witnesses (supermajority) signal the new hardfork version. This code helps you monitor that threshold and identify witnesses that might need to upgrade. Stale price feeds (older than 24 hours) also indicate witnesses that may be offline or misconfigured.
'''
    ),
    (
        "hive/witness-signing-key-rotation",
        r'''How do I safely rotate a witness signing key without missing blocks on Hive?''',
        r'''Rotating your witness signing key is a critical security practice. The process must be done carefully to avoid missing blocks during the transition. Here is the safe approach:

```python
from beem import Hive
from beem.witness import Witness
from beem.amount import Amount
from beemgraphenebase.account import PrivateKey
import time

WITNESS = "yourwitness"
ACTIVE_KEY = "5YourActivePrivateKey"
OLD_SIGNING_KEY = "5OldSigningPrivateKey"

def rotate_signing_key():
    hive = Hive(
        node=["https://api.hive.blog", "https://api.deathwing.me"],
        keys=[ACTIVE_KEY]
    )

    # Step 1: Generate new signing key pair
    new_private = PrivateKey()
    new_public = str(new_private.pubkey)
    print(f"New signing private key: {str(new_private)}")
    print(f"New signing public key:  {new_public}")
    print("SAVE THE PRIVATE KEY SECURELY BEFORE PROCEEDING!")
    print()

    # Step 2: Check current witness state
    w = Witness(WITNESS, hive_instance=hive)
    old_public = w["signing_key"]
    print(f"Current signing key: {old_public}")
    print(f"Last confirmed block: {w['last_confirmed_block_num']}")
    print()

    # Step 3: Update the signing key in your node's config.ini FIRST
    print("ACTION REQUIRED:")
    print("1. Update config.ini with the new private signing key")
    print("2. Restart your witness node")
    print("3. Verify the node is synced and producing blocks")
    print("4. Press Enter to broadcast the key update on-chain")
    input("Press Enter when ready...")

    # Step 4: Broadcast the witness_update with the new key
    # The node must already be using the new key before this broadcast
    result = hive.witness_update(
        signing_key=new_public,
        url=w.get("url", ""),
        props={
            "account_creation_fee": Amount(w["props"]["account_creation_fee"]),
            "maximum_block_size": w["props"]["maximum_block_size"],
            "hbd_interest_rate": w["props"]["hbd_interest_rate"],
        },
        account=WITNESS
    )
    print(f"Key rotation broadcast: {result}")

    # Step 5: Verify the update took effect
    time.sleep(6)  # Wait for 2 blocks
    w_updated = Witness(WITNESS, hive_instance=hive)
    if w_updated["signing_key"] == new_public:
        print("SUCCESS: Signing key updated on-chain!")
    else:
        print("WARNING: Key not yet updated, may need another block")

    return new_public

def emergency_disable_witness():
    """Disable witness immediately (set null signing key)."""
    hive = Hive(
        node=["https://api.hive.blog"],
        keys=[ACTIVE_KEY]
    )
    NULL_KEY = "STM1111111111111111111111111111111114T1Anm"
    w = Witness(WITNESS, hive_instance=hive)

    result = hive.witness_update(
        signing_key=NULL_KEY,
        url=w.get("url", ""),
        props={
            "account_creation_fee": Amount(w["props"]["account_creation_fee"]),
            "maximum_block_size": w["props"]["maximum_block_size"],
            "hbd_interest_rate": w["props"]["hbd_interest_rate"],
        },
        account=WITNESS
    )
    print(f"Witness DISABLED: {result}")

# Safe rotation procedure
rotate_signing_key()
```

Critical timing notes:
- Update the node config and restart BEFORE broadcasting the on-chain update
- The node will use the new key to sign blocks once restarted
- The chain will accept blocks signed with the new key only after the witness_update is in a block
- This means there is a brief window where blocks could be missed -- aim for rotation during a time when you are unlikely to be scheduled
- Backup witnesses (outside top 21) can rotate with zero risk since they rarely produce blocks
- Keep the old key available as a fallback until the rotation is confirmed
'''
    ),
    (
        "hive/witness-scheduling",
        r'''How does witness block scheduling work on Hive, and how can I monitor when my witness is scheduled to produce a block?''',
        r'''Hive uses a deterministic scheduling algorithm for witness block production. The top 21 witnesses each produce one block per round (63 seconds total), and one backup witness slot is included per round. Here is how to monitor scheduling:

```python
from beem import Hive
from beem.witness import Witness
from beem.blockchain import Blockchain
import time
from datetime import datetime, timedelta

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

def get_witness_schedule():
    """Get the current witness schedule from the chain."""
    schedule = hive.rpc.get_witness_schedule(api="database_api")
    if "current_shuffled_witnesses" in schedule:
        witnesses = schedule["current_shuffled_witnesses"]
    else:
        # Some API nodes return differently
        witnesses = schedule.get("current_shuffled_witnesses", [])

    print("=== Current Witness Schedule ===")
    print(f"Num scheduled witnesses: {schedule.get('num_scheduled_witnesses', 'N/A')}")
    print(f"Median props: {schedule.get('median_props', {})}")
    print(f"Majority version: {schedule.get('majority_version', 'N/A')}")
    print()

    blockchain = Blockchain(hive_instance=hive)
    head_block = blockchain.get_current_block_num()
    head_time = datetime.utcnow()

    print(f"Head block: {head_block}")
    print(f"Time (UTC): {head_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Each round is 21 blocks (top 21 witnesses) + 1 backup = 22 slots
    # But actually its 21 witnesses producing in shuffled order
    round_size = len(witnesses) if witnesses else 21

    print("Scheduled order (this round):")
    for i, w in enumerate(witnesses):
        blocks_away = i - (head_block % round_size)
        if blocks_away < 0:
            blocks_away += round_size
        est_time = head_time + timedelta(seconds=blocks_away * 3)
        marker = " <-- NEXT" if blocks_away == 0 else ""
        print(f"  Slot {i:2d}: {w:20s} (~{est_time.strftime('%H:%M:%S')}){marker}")

    return witnesses

def monitor_witness_blocks(witness_name, duration_minutes=60):
    """Monitor a specific witness's block production."""
    blockchain = Blockchain(hive_instance=hive)
    start = time.time()
    blocks_produced = 0
    blocks_missed_before = Witness(witness_name, hive_instance=hive)["total_missed"]

    print(f"Monitoring {witness_name} for {duration_minutes} minutes...")
    print(f"Starting missed blocks: {blocks_missed_before}")

    for block in blockchain.stream(raw_ops=False, threading=False):
        elapsed = (time.time() - start) / 60
        if elapsed > duration_minutes:
            break

        if block.get("witness") == witness_name:
            blocks_produced += 1
            block_num = block.get("block_num", block.get("block_id", "?"))
            ts = block.get("timestamp", "?")
            tx_count = len(block.get("transactions", []))
            print(f"  Block {block_num} at {ts} ({tx_count} txs)")

    blocks_missed_after = Witness(witness_name, hive_instance=hive)["total_missed"]
    new_misses = blocks_missed_after - blocks_missed_before

    print(f"\nResults for {witness_name}:")
    print(f"  Blocks produced: {blocks_produced}")
    print(f"  Blocks missed:   {new_misses}")
    print(f"  Reliability:     {blocks_produced}/{blocks_produced + new_misses}")

def check_next_block_time(witness_name):
    """Estimate when a witness will next produce a block."""
    schedule = hive.rpc.get_witness_schedule(api="database_api")
    witnesses = schedule.get("current_shuffled_witnesses", [])

    if witness_name in witnesses:
        pos = witnesses.index(witness_name)
        blockchain = Blockchain(hive_instance=hive)
        head = blockchain.get_current_block_num()
        current_pos = head % len(witnesses)
        blocks_until = (pos - current_pos) % len(witnesses)
        seconds_until = blocks_until * 3
        print(f"{witness_name} produces in ~{seconds_until}s ({blocks_until} blocks)")
    else:
        print(f"{witness_name} is not in the current schedule")
        print("(Backup witnesses are scheduled less frequently)")

# Run
get_witness_schedule()
```

The schedule shuffles every round. Top 21 witnesses each get exactly one slot per round. Backup witnesses share one additional slot per round, weighted by their votes. A round completes in about 63 seconds (21 blocks at 3 seconds each). If a witness misses their slot, the block is simply skipped and the next witness produces after 3 seconds.
'''
    ),
]
