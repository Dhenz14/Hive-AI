"""Hive blockchain training pairs: analytics and dashboards."""

PAIRS = [
    (
        "hive/whale-tracking",
        r'''How do I build a whale tracker that monitors large HIVE and HBD transfers in real-time?''',
        r'''<think>
Whale tracking on Hive... my first thought is to just query account history for large transfers, but wait -- that only gives you historical data for one account at a time. The user wants real-time monitoring across the entire network, so streaming all transfer operations from the blockchain and filtering by amount is the right approach.

Now, what threshold defines a "whale" transfer? This could be 1,000 HIVE, or maybe 100,000. Hmm, I considered setting it very high to reduce noise, but actually 10,000+ HIVE is a reasonable default because it catches meaningful moves without flooding alerts. For HBD, the threshold should be lower (maybe 5,000) since HBD has lower total supply and therefore each unit represents a larger fraction of the market.

I also need to think about what data to capture. Just logging the raw transfer is not enough -- since whale watchers care about patterns, the tracker should aggregate volumes per account over time. That way you can spot accumulation or distribution trends. And because alerts are only useful if they reach someone, the system should support notification callbacks for Discord or Telegram webhooks. I initially thought about building the Discord integration inline, but actually a callback pattern is cleaner because it decouples the tracking logic from the delivery mechanism.
</think>

Here is a complete whale tracking system for the Hive blockchain:

```python
from beem import Hive
from beem.blockchain import Blockchain
import json
import time
import logging
from collections import defaultdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("whale_tracker")

class WhaleTracker:
    def __init__(self, hive_threshold=10000, hbd_threshold=5000, nodes=None):
        self.hive = Hive(node=nodes or ["https://api.hive.blog"])
        self.hive_threshold = hive_threshold
        self.hbd_threshold = hbd_threshold
        self.transfer_log = []
        self.account_volumes = defaultdict(lambda: {"sent": 0, "received": 0})
        self.callbacks = []

    def add_callback(self, fn):
        """Add a notification callback."""
        self.callbacks.append(fn)

    def _notify(self, transfer):
        for cb in self.callbacks:
            try:
                cb(transfer)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _parse_amount(self, amount_str):
        parts = amount_str.split()
        return float(parts[0]), parts[1] if len(parts) > 1 else "HIVE"

    def _is_whale_transfer(self, amount, asset):
        if asset in ("HIVE", "TESTS"):
            return amount >= self.hive_threshold
        elif asset in ("HBD", "TBD"):
            return amount >= self.hbd_threshold
        return False

    def process_transfer(self, op):
        amount, asset = self._parse_amount(op.get("amount", "0 HIVE"))
        if not self._is_whale_transfer(amount, asset):
            return

        transfer = {
            "from": op["from"],
            "to": op["to"],
            "amount": amount,
            "asset": asset,
            "memo": op.get("memo", "")[:100],
            "block": op.get("block_num", 0),
            "timestamp": op.get("timestamp", "")
        }

        self.transfer_log.append(transfer)
        self.account_volumes[op["from"]]["sent"] += amount
        self.account_volumes[op["to"]]["received"] += amount

        logger.info(
            f"WHALE: @{op['from']} -> @{op['to']}: "
            f"{amount:,.3f} {asset}"
        )
        if op.get("memo"):
            logger.info(f"  Memo: {transfer['memo']}")

        self._notify(transfer)

    def stream(self):
        blockchain = Blockchain(hive_instance=self.hive)
        logger.info(f"Tracking whales (HIVE >= {self.hive_threshold}, "
                     f"HBD >= {self.hbd_threshold})")

        stream = blockchain.stream(
            opNames=["transfer"],
            raw_ops=False,
            threading=False
        )
        for op in stream:
            self.process_transfer(op)

    def get_top_senders(self, limit=10):
        sorted_accounts = sorted(
            self.account_volumes.items(),
            key=lambda x: x[1]["sent"], reverse=True
        )
        print(f"\nTop {limit} senders:")
        for acct, vol in sorted_accounts[:limit]:
            print(f"  @{acct:20s}: {vol['sent']:>14,.3f} sent")

    def get_top_receivers(self, limit=10):
        sorted_accounts = sorted(
            self.account_volumes.items(),
            key=lambda x: x[1]["received"], reverse=True
        )
        print(f"\nTop {limit} receivers:")
        for acct, vol in sorted_accounts[:limit]:
            print(f"  @{acct:20s}: {vol['received']:>14,.3f} received")

# Discord webhook notification
def discord_notify(transfer):
    import requests
    webhook_url = "https://discord.com/api/webhooks/YOUR_WEBHOOK"
    message = (f"**Whale Alert** @{transfer['from']} -> "
               f"@{transfer['to']}: "
               f"{transfer['amount']:,.3f} {transfer['asset']}")
    requests.post(webhook_url, json={"content": message}, timeout=5)

tracker = WhaleTracker(hive_threshold=10000, hbd_threshold=5000)
# tracker.add_callback(discord_notify)
# tracker.stream()
```

This tracker streams all transfers, filters by configurable thresholds, maintains volume statistics per account, and supports notification callbacks for alerting. Run it continuously for real-time monitoring or periodically for batch analysis.
'''
    ),
    (
        "hive/reward-pool-analysis",
        r'''How do I analyze the Hive reward pool to understand reward distribution and inflation?''',
        r'''The Hive reward pool determines how much HIVE and HBD is distributed to content creators and curators. Here is how to analyze it:

```python
from beem import Hive
from beem.account import Account
import json
import requests

hive = Hive(node=["https://api.hive.blog"])

def get_reward_pool_info():
    """Get current reward pool state."""
    props = hive.rpc.get_dynamic_global_properties()
    reward_fund = hive.rpc.get_reward_fund("post", api="condenser_api")

    reward_balance = float(str(reward_fund["reward_balance"]).split()[0])
    recent_claims = int(reward_fund["recent_claims"])
    median_price = float(str(props.get("current_median_history", {}).get(
        "base", "0.001 HBD")).split()[0])

    # Value per rshare
    if recent_claims > 0:
        hive_per_rshare = reward_balance / recent_claims
        usd_per_rshare = hive_per_rshare * median_price
    else:
        hive_per_rshare = 0
        usd_per_rshare = 0

    print("=== Hive Reward Pool ===")
    print(f"Reward balance:  {reward_balance:,.3f} HIVE")
    print(f"Recent claims:   {recent_claims:,}")
    print(f"HIVE per rshare: {hive_per_rshare:.15f}")
    print(f"Median price:    ${median_price:.3f}")
    print(f"USD per rshare:  {usd_per_rshare:.15f}")

    # Supply info
    current_supply = float(str(props["current_supply"]).split()[0])
    hbd_supply = float(str(props["current_hbd_supply"]).split()[0])
    virtual_supply = float(str(props["virtual_supply"]).split()[0])
    hbd_print_rate = props.get("hbd_print_rate", 10000)

    print(f"\n=== Supply Metrics ===")
    print(f"HIVE supply:     {current_supply:,.3f}")
    print(f"HBD supply:      {hbd_supply:,.3f}")
    print(f"Virtual supply:  {virtual_supply:,.3f}")
    print(f"HBD print rate:  {hbd_print_rate / 100}%")

    # Annual inflation estimate
    # Hive inflation starts at ~8% and decreases 0.01% every 250k blocks
    head_block = props["head_block_number"]
    inflation_rate = max(1.0, 9.78 - head_block / 250000 * 0.01)
    annual_new_hive = current_supply * inflation_rate / 100

    print(f"\n=== Inflation ===")
    print(f"Current rate:    ~{inflation_rate:.2f}%")
    print(f"Annual new HIVE: ~{annual_new_hive:,.0f}")
    print(f"  65% to reward pool")
    print(f"  15% to HP holders (vesting)")
    print(f"  10% to DHF (proposal fund)")
    print(f"  10% to witnesses")

    return {
        "reward_balance": reward_balance,
        "recent_claims": recent_claims,
        "hive_per_rshare": hive_per_rshare,
        "median_price": median_price,
        "inflation_rate": inflation_rate
    }

def estimate_post_rewards(rshares):
    """Estimate rewards for given rshares value."""
    info = get_reward_pool_info()
    total_reward = rshares * info["hive_per_rshare"]
    total_usd = total_reward * info["median_price"]
    author_share = total_usd * 0.5  # 50% to author
    curation_share = total_usd * 0.5  # 50% to curators

    print(f"\nEstimated rewards for {rshares:,} rshares:")
    print(f"  Total: ${total_usd:.4f}")
    print(f"  Author: ${author_share:.4f}")
    print(f"  Curators: ${curation_share:.4f}")

get_reward_pool_info()
```

The reward pool is filled by inflation (65% of new HIVE) and drained by post payouts every 7 days. The "recent_claims" value represents total rshares competing for rewards. When more people vote, the reward per rshare decreases, creating a fixed-supply distribution mechanism.
'''
    ),
    (
        "hive/witness-reliability-scoring",
        r'''How do I build a witness reliability scoring system that tracks performance over time?''',
        r'''Here is a witness reliability scoring system that tracks missed blocks, feed freshness, version updates, and uptime:

```python
from beem import Hive
from beem.witness import Witness, WitnessesRankedByVote
from datetime import datetime, timedelta
import json

hive = Hive(node=["https://api.hive.blog"])

class WitnessScorer:
    def __init__(self, hive_instance):
        self.hive = hive_instance

    def score_witness(self, witness_name):
        """Calculate a reliability score (0-100) for a witness."""
        try:
            w = Witness(witness_name, hive_instance=self.hive)
        except Exception:
            return {"name": witness_name, "score": 0, "error": "Not found"}

        score = 100
        details = {}

        # Factor 1: Missed blocks (max -30 points)
        missed = w.get("total_missed", 0)
        if missed > 100:
            penalty = min(30, missed / 10)
            score -= penalty
            details["missed_blocks"] = f"-{penalty:.0f} ({missed} total missed)"
        else:
            details["missed_blocks"] = f"OK ({missed} missed)"

        # Factor 2: Price feed freshness (max -25 points)
        last_feed = w.get("last_hbd_exchange_update", "")
        if last_feed:
            try:
                feed_time = datetime.strptime(last_feed, "%Y-%m-%dT%H:%M:%S")
                age_hours = (datetime.utcnow() - feed_time).total_seconds() / 3600
                if age_hours > 24:
                    score -= 25
                    details["feed"] = f"-25 (stale: {age_hours:.0f}h old)"
                elif age_hours > 6:
                    penalty = (age_hours - 6) / 18 * 15
                    score -= penalty
                    details["feed"] = f"-{penalty:.0f} ({age_hours:.0f}h old)"
                else:
                    details["feed"] = f"OK ({age_hours:.1f}h old)"
            except (ValueError, TypeError):
                score -= 10
                details["feed"] = "-10 (parse error)"
        else:
            score -= 25
            details["feed"] = "-25 (no feed)"

        # Factor 3: Signing key active (max -20 points)
        null_key = "STM1111111111111111111111111111111114T1Anm"
        if w["signing_key"] == null_key:
            score -= 20
            details["status"] = "-20 (DISABLED)"
        else:
            details["status"] = "OK (active)"

        # Factor 4: Running version (max -15 points)
        version = w.get("running_version", "0.0.0")
        schedule = self.hive.rpc.get_witness_schedule(api="database_api")
        majority = schedule.get("majority_version", "0.0.0")
        if version != majority:
            score -= 15
            details["version"] = f"-15 ({version} vs majority {majority})"
        else:
            details["version"] = f"OK ({version})"

        # Factor 5: HBD interest rate reasonableness (max -10)
        rate = w.get("props", {}).get("hbd_interest_rate", 0)
        if rate == 0:
            score -= 10
            details["hbd_rate"] = "-10 (0% rate)"
        else:
            details["hbd_rate"] = f"OK ({rate/100}%)"

        score = max(0, min(100, score))

        return {
            "name": witness_name,
            "score": round(score),
            "details": details,
            "votes_mvests": int(w["votes"]) / 1e12,
        }

    def score_top_witnesses(self, limit=50):
        """Score all top witnesses."""
        witnesses = WitnessesRankedByVote(limit=limit, hive_instance=self.hive)
        scores = []

        for w in witnesses:
            result = self.score_witness(w["owner"])
            scores.append(result)

        scores.sort(key=lambda x: -x["score"])

        print(f"{'Rank':>4} {'Score':>5} {'Witness':20s} {'Votes (MV)':>10}")
        print("-" * 45)
        for i, s in enumerate(scores):
            print(f"{i+1:>4} {s['score']:>5} @{s['name']:20s} "
                  f"{s['votes_mvests']:>9.1f}M")

        return scores

scorer = WitnessScorer(hive)
# result = scorer.score_witness("blocktrades")
# print(json.dumps(result, indent=2))
# scorer.score_top_witnesses(30)
```

This scoring system penalizes: missed blocks (indicates hardware/network issues), stale price feeds (indicates negligence), disabled signing key (witness offline), outdated node version (not following consensus), and unreasonable parameter votes. Run it periodically to track witness reliability trends over time.
'''
    ),
    (
        "hive/network-statistics",
        r'''How do I build a network statistics dashboard for the Hive blockchain?''',
        r'''Here is a comprehensive network statistics collector that gathers key metrics for a Hive dashboard:

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.witness import WitnessesRankedByVote
import json
import time
from datetime import datetime
from collections import Counter

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

class HiveNetworkStats:
    def __init__(self, hive_instance):
        self.hive = hive_instance

    def get_chain_stats(self):
        """Get core blockchain statistics."""
        props = self.hive.rpc.get_dynamic_global_properties()
        config = self.hive.rpc.get_config(api="condenser_api")

        head = props["head_block_number"]
        lib = props["last_irreversible_block_num"]
        supply = props["current_supply"]
        hbd_supply = props["current_hbd_supply"]
        virtual = props["virtual_supply"]

        return {
            "head_block": head,
            "irreversible_block": lib,
            "block_interval": config.get("HIVE_BLOCK_INTERVAL", 3),
            "current_witness": props["current_witness"],
            "hive_supply": str(supply),
            "hbd_supply": str(hbd_supply),
            "virtual_supply": str(virtual),
            "hbd_interest_rate": props.get("hbd_interest_rate", 0) / 100,
            "hbd_print_rate": props.get("hbd_print_rate", 10000) / 100,
            "participation_pct": props.get("participation_count", 0) / 128 * 100,
        }

    def get_recent_activity(self, blocks=100):
        """Analyze recent blockchain activity."""
        blockchain = Blockchain(hive_instance=self.hive)
        head = blockchain.get_current_block_num()
        start = head - blocks

        op_counts = Counter()
        tx_count = 0
        total_ops = 0
        unique_accounts = set()

        for block_num in range(start, head + 1):
            block = blockchain.get_block(block_num)
            if not block:
                continue
            for tx in block.get("transactions", []):
                tx_count += 1
                for op in tx.get("operations", []):
                    if isinstance(op, list):
                        op_type = op[0]
                        op_data = op[1]
                    else:
                        op_type = op.get("type", "").replace("_operation", "")
                        op_data = op.get("value", op)
                    op_counts[op_type] += 1
                    total_ops += 1
                    for field in ["author", "voter", "from", "account"]:
                        if field in op_data:
                            unique_accounts.add(op_data[field])

        duration_sec = blocks * 3
        return {
            "blocks_analyzed": blocks,
            "duration_seconds": duration_sec,
            "transactions": tx_count,
            "operations": total_ops,
            "unique_accounts": len(unique_accounts),
            "tx_per_second": tx_count / duration_sec,
            "ops_per_second": total_ops / duration_sec,
            "top_operations": op_counts.most_common(10)
        }

    def get_witness_stats(self):
        """Get witness network statistics."""
        witnesses = WitnessesRankedByVote(limit=100, hive_instance=self.hive)
        active = [w for w in witnesses
                  if w["signing_key"] != "STM1111111111111111111111111111111114T1Anm"]
        disabled = len(witnesses) - len(active)
        versions = Counter(w.get("running_version", "?") for w in active)

        return {
            "total_tracked": len(witnesses),
            "active": len(active),
            "disabled": disabled,
            "version_distribution": dict(versions.most_common()),
            "total_missed": sum(w["total_missed"] for w in active),
        }

    def full_dashboard(self):
        """Generate a complete dashboard snapshot."""
        print("=== Hive Network Dashboard ===")
        print(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

        chain = self.get_chain_stats()
        print("Chain Status:")
        print(f"  Head block:      {chain['head_block']:,}")
        print(f"  Irreversible:    {chain['irreversible_block']:,}")
        print(f"  Current witness: @{chain['current_witness']}")
        print(f"  HIVE supply:     {chain['hive_supply']}")
        print(f"  HBD supply:      {chain['hbd_supply']}")
        print(f"  HBD interest:    {chain['hbd_interest_rate']}%")
        print(f"  HBD print rate:  {chain['hbd_print_rate']}%")

        activity = self.get_recent_activity(blocks=100)
        print(f"\nRecent Activity (last {activity['blocks_analyzed']} blocks):")
        print(f"  Transactions:    {activity['transactions']:,}")
        print(f"  Operations:      {activity['operations']:,}")
        print(f"  Unique accounts: {activity['unique_accounts']:,}")
        print(f"  TPS:             {activity['tx_per_second']:.2f}")
        print(f"  Top operations:")
        for op, count in activity["top_operations"][:5]:
            print(f"    {op:30s}: {count:,}")

        witness = self.get_witness_stats()
        print(f"\nWitness Network:")
        print(f"  Active:          {witness['active']}")
        print(f"  Disabled:        {witness['disabled']}")
        print(f"  Versions:        {json.dumps(witness['version_distribution'])}")

        return {"chain": chain, "activity": activity, "witnesses": witness}

stats = HiveNetworkStats(hive)
stats.full_dashboard()
```

This dashboard collects chain state, recent activity metrics (TPS, operation distribution, unique accounts), and witness network health. For a production dashboard, store these snapshots in a time-series database and visualize with Grafana or a custom web UI. Run the collection every 5-15 minutes for trending data.
'''
    ),
    (
        "hive/dashboard-building",
        r'''How do I build a real-time Hive blockchain dashboard using Python and a web framework?''',
        r'''Here is a lightweight real-time dashboard using Flask and Server-Sent Events (SSE) for live updates:

```python
from flask import Flask, Response, jsonify, render_template_string
from beem import Hive
from beem.blockchain import Blockchain
import json
import time
import threading

app = Flask(__name__)
hive = Hive(node=["https://api.hive.blog"])

# Shared state for real-time data
dashboard_data = {
    "head_block": 0,
    "tps": 0,
    "last_transfers": [],
    "op_counts": {},
    "updated_at": ""
}
data_lock = threading.Lock()

def background_updater():
    """Background thread to update dashboard data."""
    blockchain = Blockchain(hive_instance=hive)
    while True:
        try:
            props = hive.rpc.get_dynamic_global_properties()
            head = props["head_block_number"]
            block = blockchain.get_block(head)

            tx_count = len(block.get("transactions", [])) if block else 0
            transfers = []

            if block:
                for tx in block["transactions"]:
                    for op in tx["operations"]:
                        op_type = op[0] if isinstance(op, list) else op.get("type", "")
                        op_data = op[1] if isinstance(op, list) else op.get("value", {})
                        if op_type == "transfer":
                            transfers.append({
                                "from": op_data.get("from", ""),
                                "to": op_data.get("to", ""),
                                "amount": op_data.get("amount", ""),
                            })

            with data_lock:
                dashboard_data["head_block"] = head
                dashboard_data["tps"] = tx_count / 3.0
                dashboard_data["last_transfers"] = transfers[:5]
                dashboard_data["updated_at"] = time.strftime("%H:%M:%S")

        except Exception as e:
            print(f"Update error: {e}")
        time.sleep(3)

# Start background updater
updater_thread = threading.Thread(target=background_updater, daemon=True)
updater_thread.start()

@app.route("/api/stats")
def api_stats():
    with data_lock:
        return jsonify(dashboard_data)

@app.route("/stream")
def stream():
    """Server-Sent Events endpoint for real-time updates."""
    def generate():
        while True:
            with data_lock:
                data = json.dumps(dashboard_data)
            yield f"data: {data}\n\n"
            time.sleep(3)
    return Response(generate(), mimetype="text/event-stream")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Hive Dashboard</title>
<style>
body { font-family: monospace; background: #1a1a2e; color: #eee; padding: 20px; }
.card { background: #16213e; padding: 15px; margin: 10px; border-radius: 8px; display: inline-block; min-width: 200px; }
.value { font-size: 24px; color: #e94560; }
.label { color: #888; font-size: 12px; }
#transfers { margin-top: 20px; }
.transfer { padding: 5px; border-bottom: 1px solid #333; }
</style>
</head>
<body>
<h1>Hive Blockchain Dashboard</h1>
<div>
  <div class="card"><div class="label">Head Block</div><div class="value" id="block">-</div></div>
  <div class="card"><div class="label">TPS</div><div class="value" id="tps">-</div></div>
  <div class="card"><div class="label">Updated</div><div class="value" id="time">-</div></div>
</div>
<div id="transfers"><h3>Recent Transfers</h3></div>
<script>
const es = new EventSource("/stream");
es.onmessage = function(e) {
    const data = JSON.parse(e.data);
    document.getElementById("block").textContent = data.head_block.toLocaleString();
    document.getElementById("tps").textContent = data.tps.toFixed(2);
    document.getElementById("time").textContent = data.updated_at;
    const div = document.getElementById("transfers");
    let html = "<h3>Recent Transfers</h3>";
    for (const t of data.last_transfers) {
        html += '<div class="transfer">@' + t.from + " -> @" + t.to + ": " + t.amount + "</div>";
    }
    div.innerHTML = html;
};
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
```

This dashboard uses a background thread to fetch blockchain data every 3 seconds, SSE for real-time browser updates (no polling), and a minimal dark-themed UI. Extend it by adding charts (Chart.js), more metrics (reward pool, witness status), and historical data storage. For production, use gunicorn with multiple workers and a proper database for time-series storage.
'''
    ),
]
