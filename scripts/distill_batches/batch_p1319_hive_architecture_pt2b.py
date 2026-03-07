"""Hive architecture training pairs (part 2b): governance, testing, deployment."""

PAIRS = [
    (
        "hive_architecture/block-production-miss-detection",
        r'''How do I detect missed blocks by a Hive witness in real time?''',
        r'''<think>
Each Hive block is produced every 3 seconds by a scheduled witness. If a witness
misses their slot, the next block's timestamp will have a gap. We can poll the
dynamic global properties for head_block_number and compare the scheduled witness
against the actual signer. The `get_witness_by_account` RPC returns `total_missed`
which increments on each miss. Polling every 3s and comparing the counter detects
misses immediately.
</think>

Monitor witness misses with a simple polling loop:

```python
import time
from beem import Hive
from beem.witness import Witness

hive = Hive(node="https://api.hive.blog")

def monitor_misses(witness_name: str, interval: float = 3.0):
    w = Witness(witness_name, blockchain_instance=hive)
    last_missed = w["total_missed"]
    print(f"Tracking {witness_name} — current misses: {last_missed}")
    while True:
        w.refresh()
        current = w["total_missed"]
        if current > last_missed:
            delta = current - last_missed
            print(f"ALERT: {witness_name} missed {delta} block(s)! Total: {current}")
            last_missed = current
        time.sleep(interval)

monitor_misses("yourwitness")
```

Key points:
- `total_missed` is cumulative and never resets
- Pair with a notification (email/Discord webhook) on the alert line
- For multi-witness monitoring, track a dict of `{name: last_missed}`'''
    ),
    (
        "hive_architecture/network-fork-detection",
        r'''How can I detect if my Hive node is on a fork versus the main chain?''',
        r'''<think>
A fork occurs when two parts of the network produce conflicting blocks at the same
height. To detect this, compare your node's head block ID against one or more
trusted reference nodes. If the block IDs diverge at the same height, your node is
on a minority fork. Checking `last_irreversible_block_num` is also important since
blocks before that threshold are finalized. Polling multiple nodes and comparing
block IDs every few seconds is the standard approach.
</think>

Compare your node against reference nodes to detect forks:

```python
import requests

NODES = [
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://anyx.io",
]
MY_NODE = "http://localhost:8091"

def get_dgp(node: str) -> dict:
    r = requests.post(node, json={
        "jsonrpc": "2.0", "method": "condenser_api.get_dynamic_global_properties",
        "params": [], "id": 1
    }, timeout=5)
    return r.json()["result"]

def check_fork():
    my = get_dgp(MY_NODE)
    my_block = my["head_block_number"]
    my_id = my["head_block_id"]
    lib = my["last_irreversible_block_num"]
    for node in NODES:
        ref = get_dgp(node)
        if abs(ref["head_block_number"] - my_block) > 5:
            print(f"WARNING: {node} height delta > 5 blocks")
        if ref["head_block_number"] == my_block and ref["head_block_id"] != my_id:
            print(f"FORK DETECTED vs {node} at block {my_block}")
    print(f"LIB: {lib}, head: {my_block}, id: {my_id[:16]}...")

check_fork()
```

- Blocks before `last_irreversible_block_num` are finalized and safe
- Height differences > 10 blocks usually indicate your node is stalled'''
    ),
    (
        "hive_architecture/account-history-api-pagination",
        r'''What is the correct way to paginate through an account's full operation history on Hive?''',
        r'''<think>
The `account_history_api.get_account_history` call takes an account, a start index,
and a limit (max 1000). The index -1 means "most recent." Each result returns
[sequence_number, operation]. To paginate backwards, take the lowest sequence number
from the current batch, subtract 1, and use that as the next start. Continue until
the sequence number reaches 0. This avoids gaps and duplicates.
</think>

Paginate backwards from the most recent operation:

```python
from beem import Hive
from beem.account import Account

hive = Hive(node="https://api.hive.blog")

def iter_full_history(name: str, batch: int = 1000):
    acc = Account(name, blockchain_instance=hive)
    start = -1
    while True:
        history = acc.get_account_history(start, batch)
        history = list(history)
        if not history:
            break
        history.sort(key=lambda h: h["index"])
        for op in history:
            yield op
        earliest = history[0]["index"]
        if earliest == 0:
            break
        start = earliest - 1
        if start < 0:
            break

for op in iter_full_history("hiveio"):
    print(op["index"], op["type"])
```

- Max `limit` per call is 1000
- Always sort results since order is not guaranteed
- For filtered ops, use `operation_filter_low` bitmask parameter'''
    ),
    (
        "hive_architecture/resource-credit-system",
        r'''Explain the Hive resource credit system architecture and how to check RC status programmatically.''',
        r'''<think>
Resource credits replaced bandwidth in HF20. Each account gets RC proportional to
its HP. Every transaction consumes RC based on three resource pools: state bytes
(blockchain state growth), execution time, and history bytes. RC regenerates over
5 days linearly from 0 to 100%. The `rc_api.find_rc_accounts` call returns current
RC mana and max mana. Percentage is current_mana / max_mana * 100. Low RC means
the account cannot transact until it regenerates or delegates more HP.
</think>

Check RC and estimate remaining transactions:

```python
import requests, time

def get_rc(account: str, node: str = "https://api.hive.blog") -> dict:
    r = requests.post(node, json={
        "jsonrpc": "2.0", "method": "rc_api.find_rc_accounts",
        "params": {"accounts": [account]}, "id": 1
    })
    rc = r.json()["result"]["rc_accounts"][0]
    max_mana = int(rc["max_rc"])
    current = int(rc["rc_manabar"]["current_mana"])
    pct = (current / max_mana * 100) if max_mana else 0
    return {"account": account, "rc_pct": round(pct, 2),
            "current": current, "max": max_mana}

def estimate_ops(rc_info: dict, cost_per_op: int = 1_500_000) -> int:
    return rc_info["current"] // cost_per_op

info = get_rc("hiveio")
print(f"{info['account']}: {info['rc_pct']}% RC")
print(f"Estimated comment ops remaining: {estimate_ops(info)}")
```

- RC regenerates linearly over 5 days (20% per day)
- A typical comment costs ~1.5M RC; a transfer ~0.5M RC
- Delegate HP to an account to increase its max RC'''
    ),
    (
        "hive_architecture/witness-reward-calculation",
        r'''How are Hive witness rewards calculated per block produced?''',
        r'''<think>
Hive inflation starts at ~0.97% per year and decreases 0.01% annually to a floor of
0.095%. Of each block's inflation, 10% goes to witnesses. Top 20 witnesses produce
one block per round, and backup witnesses are scheduled proportionally by votes.
The reward per block is calculated from virtual supply, inflation rate, and block
interval. Since there are ~28800 blocks/day, the per-block reward is
(virtual_supply * inflation / 28800 / 10) for the witness portion.
</think>

Calculate witness block reward from chain state:

```python
from beem import Hive
from beem.amount import Amount

hive = Hive(node="https://api.hive.blog")

def witness_block_reward() -> dict:
    dgp = hive.get_dynamic_global_properties()
    virtual_supply = Amount(dgp["virtual_supply"]).amount
    head_block = dgp["head_block_number"]
    # Inflation: starts 9.78%, decreases 0.01% per 250k blocks, floor 0.95%
    inflation = max(978 - head_block // 250_000, 95)
    inflation_pct = inflation / 10_000
    annual_new = virtual_supply * inflation_pct
    blocks_per_year = 365.25 * 24 * 3600 / 3  # ~10_512_000
    witness_share = 0.10  # 10% of inflation
    per_block = annual_new * witness_share / blocks_per_year
    return {"per_block_hive": round(per_block, 3),
            "daily_top20": round(per_block * 28800 / 21, 3),
            "inflation_pct": round(inflation_pct * 100, 3)}

print(witness_block_reward())
```

- Top 20 witnesses each produce 1 block per 21-block round
- Backup witnesses share 1 slot per round, weighted by votes
- Witness pay is in HIVE (vesting), not HBD'''
    ),
    (
        "hive_architecture/governance-voting-mechanics",
        r'''How does witness and proposal voting work on Hive? Show how to cast votes programmatically.''',
        r'''<think>
Hive governance uses stake-weighted voting. Each account can vote for up to 30
witnesses — each vote has weight equal to the voter's HP. Witnesses are ranked by
total approval weight. For proposals (DHF), each account can vote to approve or
remove approval on any number of proposals. Proposals above the "return proposal"
threshold get funded. Votes are cast via `account_witness_vote` and
`update_proposal_votes` operations using the active key.
</think>

Cast witness and proposal votes:

```python
from beem import Hive
from beem.account import Account

hive = Hive(keys=["5JyourActiveKey"], node="https://api.hive.blog")

# Vote for a witness
def vote_witness(voter: str, witness: str, approve: bool = True):
    hive.wallet.setKeys(["5JyourActiveKey"])
    tx = hive.witness_vote(witness, account=voter, approve=approve)
    print(f"{'Voted for' if approve else 'Unvoted'} witness {witness}")
    return tx

# Vote on a DHF proposal
def vote_proposal(voter: str, proposal_ids: list, approve: bool = True):
    op = ["update_proposal_votes", {
        "voter": voter,
        "proposal_ids": proposal_ids,
        "approve": approve,
        "extensions": []
    }]
    tx = hive.finalizeOp(op, voter, "active")
    print(f"{'Approved' if approve else 'Removed'} proposals {proposal_ids}")
    return tx

vote_witness("youraccount", "goodwitness", approve=True)
vote_proposal("youraccount", [123, 456], approve=True)
```

- Max 30 witness votes per account, each at full HP weight
- Proposal votes have no limit on number of approvals
- Both require the **active** key (not posting)'''
    ),
    (
        "hive_architecture/dhf-proposal-system",
        r'''Explain the Hive DHF (Decentralized Hive Fund) proposal system architecture and how to query active proposals.''',
        r'''<think>
The DHF (formerly SPS) accumulates 10% of inflation into a treasury account
(@hive.fund). Anyone can create a proposal requesting daily HBD payments over a date
range. Stakeholders vote to approve proposals. A special "return proposal" (id 0) acts
as a funding threshold — only proposals with more approval weight than the return
proposal receive daily payouts. Proposals are queried via `database_api.list_proposals`
which supports ordering by total_votes, creator, start_date, etc.
</think>

Query funded proposals above the return threshold:

```python
import requests

def list_proposals(node: str = "https://api.hive.blog",
                   order: str = "by_total_votes", status: str = "active"):
    r = requests.post(node, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "database_api.list_proposals",
        "params": {"start": [""], "limit": 100,
                   "order": order, "order_direction": "descending",
                   "status": status}
    })
    return r.json()["result"]["proposals"]

proposals = list_proposals()
# Find return proposal threshold
return_prop = next((p for p in proposals if p["id"] == 0), None)
threshold = int(return_prop["total_votes"]) if return_prop else 0

funded = [p for p in proposals
          if int(p["total_votes"]) > threshold and p["id"] != 0]
for p in funded:
    print(f"#{p['id']} {p['subject'][:40]:40s} "
          f"{p['daily_pay']} — by @{p['creator']}")
print(f"\nFunded: {len(funded)} / {len(proposals)} active proposals")
```

- Treasury receives 10% of HIVE inflation, converted to HBD
- Proposals specify daily HBD pay and a start/end date window
- Creating a proposal costs 10 HBD (burned) + 60 HBD refundable deposit'''
    ),
    (
        "hive_architecture/chain-id-network-identification",
        r'''How do I identify which Hive network (mainnet vs testnet) a node is on using the chain ID?''',
        r'''<think>
Every Hive network has a unique chain ID — a 256-bit hex string baked into the
genesis block. Mainnet's chain ID is beeab0de... and testnet uses a different one.
The chain ID is returned by `database_api.get_config` under HIVE_CHAIN_ID. All
signed transactions include the chain ID to prevent replay across networks. Checking
this value lets you confirm which network a node serves before broadcasting.
</think>

Verify chain identity before transacting:

```python
import requests, sys

KNOWN_CHAINS = {
    "beeab0de00000000000000000000000000000000000000000000000000000000": "mainnet",
    "18dcf0a285365fc58b71f18b3d3fec954aa0c141c44e4e5cb4cf777b9eab274e": "testnet",
}

def identify_chain(node: str) -> str:
    r = requests.post(node, json={
        "jsonrpc": "2.0", "method": "database_api.get_config",
        "params": {}, "id": 1
    })
    chain_id = r.json()["result"]["HIVE_CHAIN_ID"]
    network = KNOWN_CHAINS.get(chain_id, "unknown")
    return chain_id, network

def safe_broadcast(node: str, expected: str = "mainnet"):
    chain_id, network = identify_chain(node)
    if network != expected:
        sys.exit(f"ABORT: node is {network}, expected {expected}")
    print(f"Confirmed {network} (chain_id: {chain_id[:16]}...)")

safe_broadcast("https://api.hive.blog", expected="mainnet")
```

- Chain ID prevents transaction replay between mainnet and testnet
- Always verify chain ID when connecting to an unfamiliar RPC endpoint
- Custom testnets generate a unique chain ID at genesis'''
    ),
    (
        "hive_architecture/testnet-setup",
        r'''How do I set up a local Hive testnet for development and testing?''',
        r'''<think>
A local Hive testnet runs a standalone hived with --testnet flag and a custom
chain ID. The testnet uses an "initminer" account with a known private key to
bootstrap block production. You configure the genesis file and pass witness
parameters. The tinman tool can also snapshot mainnet state into a testnet.
For quick dev work, running a single-witness testnet in Docker is simplest,
with a custom config.ini setting the witness and enabling required plugins.
</think>

Minimal local testnet with Docker:

```bash
# Create testnet config
mkdir -p ~/hive-testnet && cat > ~/hive-testnet/config.ini << 'EOF'
testnet = 1
witness = "initminer"
private-key = 5JNHfZYKGaomSFvd4NUdQ9qMcEAC43kujbfjueTHpVapX1Kzq2n
enable-stale-production = 1
required-participation = 0
plugin = witness condenser_api database_api rc_api account_history_api
webserver-http-endpoint = 0.0.0.0:8091
EOF

# Run testnet node
docker run -d --name hive-testnet \
  -v ~/hive-testnet:/config \
  -p 8091:8091 \
  hiveio/hive:latest \
  --data-dir /config --testnet

# Verify it is producing blocks
sleep 5 && curl -s localhost:8091 -d '{
  "jsonrpc":"2.0","method":"condenser_api.get_dynamic_global_properties",
  "params":[],"id":1}' | python3 -m json.tool | grep head_block
```

- The initminer key above is the well-known testnet key (not secret)
- Use `--testnet` to generate a unique chain ID automatically
- For state-loaded testnets, use `tinman` to snapshot mainnet accounts'''
    ),
    (
        "hive_architecture/docker-hived-deployment",
        r'''What is the recommended way to deploy a production hived node using Docker?''',
        r'''<think>
Production hived in Docker requires careful volume management for the blockchain
data (shared_memory.bin can be 24GB+), proper plugin selection, and resource limits.
The official hiveio/hive image supports passing config via mounted volumes. Key
production settings: disable stale production, set a specific p2p seed list,
enable only needed API plugins to save RAM, and configure shared-file-size.
A docker-compose file with restart policies and health checks is standard.
</think>

Production docker-compose for a full API node:

```yaml
version: "3.8"
services:
  hived:
    image: hiveio/hive:latest
    container_name: hived-prod
    restart: unless-stopped
    ports:
      - "2001:2001"   # p2p
      - "8091:8091"   # http API
    volumes:
      - hive-data:/hive/datadir
      - ./config.ini:/hive/datadir/config.ini:ro
    environment:
      - HIVED_ARGS=--shared-file-size=24G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8091"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 32G

volumes:
  hive-data:
    driver: local
```

Minimal `config.ini` for an API node:

```ini
p2p-endpoint = 0.0.0.0:2001
webserver-http-endpoint = 0.0.0.0:8091
plugin = condenser_api database_api account_history_api rc_api
shared-file-size = 24G
flush-state-interval = 0
```

- Use named volumes so data persists across container recreation
- Set `shared-file-size` to at least 24G for a full node
- For witness nodes, add the witness plugin and private key to config'''
    ),
    (
        "hive_architecture/automated-node-backup",
        r'''How do I set up automated backups for a hived node's block log and shared memory?''',
        r'''<think>
Hived stores data in two main files: block_log (append-only, multi-GB) and
shared_memory.bin (mmap'd state file). The safest backup strategy is to stop
hived, copy the files, then restart. For zero-downtime, you can use filesystem
snapshots (LVM/ZFS) or rsync the block_log while running since it is append-only.
shared_memory.bin must be copied while hived is stopped or from a snapshot.
Incremental block_log backups work because it only grows. Cron scheduling with
retention policy keeps disk usage manageable.
</think>

Automated backup script with rotation:

```bash
#!/bin/bash
set -euo pipefail

HIVE_DATA="/hive/datadir"
BACKUP_DIR="/backups/hive"
RETAIN_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEST="$BACKUP_DIR/$TIMESTAMP"

mkdir -p "$DEST"

# Stop node for consistent snapshot
docker stop hived-prod
echo "Node stopped, copying data..."

# Copy critical files
cp "$HIVE_DATA/shared_memory.bin" "$DEST/"
cp "$HIVE_DATA/blockchain/block_log" "$DEST/"
cp "$HIVE_DATA/blockchain/block_log.artifacts" "$DEST/" 2>/dev/null || true

# Restart immediately
docker start hived-prod
echo "Node restarted. Compressing backup..."

# Compress in background
tar -czf "$DEST.tar.gz" -C "$BACKUP_DIR" "$TIMESTAMP" && rm -rf "$DEST"

# Prune old backups
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETAIN_DAYS -delete
echo "Backup complete: $DEST.tar.gz"
```

Schedule via cron: `0 3 * * * /opt/scripts/hive_backup.sh >> /var/log/hive_backup.log 2>&1`

- block_log can be rsynced incrementally while running (append-only)
- shared_memory.bin requires hived to be stopped for a clean copy
- Consider ZFS snapshots for zero-downtime consistent backups'''
    ),
    (
        "hive_architecture/performance-benchmarking-hived",
        r'''How do I benchmark my hived node's API performance and block sync speed?''',
        r'''<think>
Benchmarking hived involves two aspects: API throughput (requests/sec, latency)
and block sync speed (blocks/sec during replay). For API benchmarks, tools like
wrk or k6 can hammer the RPC endpoint with realistic queries. For sync speed,
measure head_block_number delta over time during a replay. Key metrics: p50/p99
latency, requests per second, and memory usage. Comparing against known baselines
helps identify misconfiguration or hardware bottlenecks.
</think>

API benchmark script and sync speed monitor:

```python
import requests, time, statistics

NODE = "http://localhost:8091"
CALLS = [
    ("condenser_api.get_dynamic_global_properties", []),
    ("condenser_api.get_accounts", [["hiveio"]]),
    ("condenser_api.get_block", [80000000]),
]

def bench_api(rounds: int = 50) -> dict:
    results = {}
    for method, params in CALLS:
        latencies = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            r = requests.post(NODE, json={
                "jsonrpc": "2.0", "method": method,
                "params": params, "id": 1}, timeout=10)
            latencies.append((time.perf_counter() - t0) * 1000)
            r.raise_for_status()
        results[method.split(".")[-1]] = {
            "p50_ms": round(statistics.median(latencies), 1),
            "p99_ms": round(sorted(latencies)[int(rounds * 0.99)], 1),
            "rps": round(1000 / statistics.mean(latencies), 1),
        }
    return results

def bench_sync(duration: int = 60):
    dgp = lambda: requests.post(NODE, json={
        "jsonrpc": "2.0", "method": "condenser_api.get_dynamic_global_properties",
        "params": [], "id": 1}).json()["result"]["head_block_number"]
    start_block = dgp()
    time.sleep(duration)
    end_block = dgp()
    bps = (end_block - start_block) / duration
    print(f"Sync speed: {bps:.1f} blocks/sec over {duration}s")

for name, stats in bench_api().items():
    print(f"{name:40s} p50={stats['p50_ms']}ms p99={stats['p99_ms']}ms "
          f"rps={stats['rps']}")
bench_sync()
```

- Healthy API node: p50 < 50ms, > 100 rps for simple queries
- During replay, expect 500-2000 blocks/sec depending on hardware
- Monitor with `docker stats` for CPU/memory during benchmarks'''
    ),
]
